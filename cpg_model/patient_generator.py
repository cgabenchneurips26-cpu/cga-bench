"""Patient Generator

Generates patient contexts from CPG graph conditional rules to auto-create scenarios.

For each conditional rule:
1. trigger patient: condition == True -> trap scenario
2. normal patient: condition == False -> baseline scenario

Also generates combinatorial patients where 2-3 rules fire simultaneously.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
import itertools
from pathlib import Path
import random
import re
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .constraint_derivation import ConstraintDerivationEngine, DerivedConstraintSet


@dataclass
class GeneratedScenario:
    """A scenario auto-generated from conditional rules."""

    scenario_id: str
    guideline_graph: str
    patient: dict[str, Any]
    derived_constraints: dict[str, Any]
    trap_scenario: bool
    trap_description: str
    triggered_rules: list[str]
    generation_method: str  # "auto:single_rule_trigger", "auto:combinatorial", etc.
    expected_actions: list[str] = field(default_factory=list)
    forbidden_actions: list[str] = field(default_factory=list)
    pathway_id: str = ""
    pathway_description: str = ""


_GRAPH_PREFIX_MAP: dict[str, str] = {
    "ada_dka_management": "dka",
    "aha_chest_pain": "acs",
    "aha_heart_failure": "hf",
    "aha_stroke": "stroke",
    "ssc_sepsis_hour1": "sepsis",
    "atrial_fibrillation": "af",
    "kdigo_aki_full": "aki",
    "kdigo_contrast_aki": "caki",
    "pulmonary_embolism": "pe",
    "cap_pneumonia": "cap",
    "copd_exacerbation": "copd",
    "gi_bleeding": "gib",
    "hypertensive_emergency": "htn",
    "universal_clinical_safety": "safety",
    "anaphylaxis_management": "anaph",
    "acls_cardiac_arrest": "acls",
    "status_epilepticus": "se",
    "gina_asthma_exacerbation": "asthma",
    "idsa_meningitis": "mening",
    "toxicology_management": "tox",
}

MAX_COMBINATORIAL_SIZE = 3
MAX_COMBINATORIAL_PER_GRAPH = 5
MAX_EXPECTED_ACTIONS = 30

# ---------------------------------------------------------------------------
# PathwayAnalyzer
# ---------------------------------------------------------------------------

_SEMANTIC_GROUPS: dict[str, str] = {}
for _val in (
    "acute_ischemic_stroke",
    "ischemic_stroke",
    "intracerebral_hemorrhage",
    "hemorrhagic_stroke",
    "subarachnoid_hemorrhage",
    "wake_up_stroke",
):
    _SEMANTIC_GROUPS[_val] = "stroke_type"
for _val in ("hfref", "hfpef", "hfmref", "adhf", "cardiogenic_shock", "ef_below_40", "ef_41_49", "ef_above_50"):
    _SEMANTIC_GROUPS[_val] = "hf_type"
for _val in ("aki_stage_1", "aki_stage_2", "aki_stage_3", "aki_suspected", "ckd_stage_4", "ckd_stage_5"):
    _SEMANTIC_GROUPS[_val] = "aki_stage"
for _val in ("acute_decompensated", "device_candidate"):
    _SEMANTIC_GROUPS[_val] = "hf_acuity"
for _val in ("contrast_aki_risk", "contrast_aki_prevention", "pre_contrast", "post_contrast"):
    _SEMANTIC_GROUPS[_val] = "contrast_phase"

_CONFLICT_PAIRS: list[tuple[set[str], set[str]]] = [
    # Stroke: tPA/ischemic vs hemorrhagic
    (
        {
            "administer_iv_tpa",
            "tpa_pathway",
            "tpa_eligibility_assessment",
            "post_tpa_monitoring",
            "bp_management_tpa_candidate",
        },
        {
            "hemorrhagic_stroke_management",
            "ich_management",
            "ich_conservative_management",
            "neurosurgical_intervention",
        },
    ),
    # Stroke: tPA (onset <4.5h) vs non-reperfusion (onset >4.5h)
    (
        {"administer_iv_tpa", "post_tpa_monitoring", "bp_management_tpa_candidate"},
        {"non_reperfusion_management", "bp_management_non_tpa"},
    ),
    # HF: HFrEF GDMT vs cardiogenic shock
    ({"hfref_gdmt"}, {"cardiogenic_shock_management"}),
    # HF: HFpEF vs HFrEF (mutually exclusive phenotypes)
    ({"hfpef_classification", "hfpef_treatment"}, {"hfref_classification", "hfref_gdmt"}),
    # HF: HFmrEF vs HFrEF
    ({"hfmref_classification", "hfmref_treatment"}, {"hfref_classification", "hfref_gdmt"}),
    # HF: HFpEF vs HFmrEF
    ({"hfpef_classification", "hfpef_treatment"}, {"hfmref_classification", "hfmref_treatment"}),
]


class PathwayAnalyzer:
    """Analyze CPG graph pathway combinations from patient_activation_condition."""

    def __init__(self, engine: ConstraintDerivationEngine) -> None:
        self.engine = engine

    def find_pathway_combinations(self, graph: dict[str, Any]) -> list[dict[str, Any]]:
        """Find meaningful pathway combinations with patient context overrides."""
        nodes = graph.get("nodes", {})
        conditional_nodes: list[dict[str, Any]] = []
        always_active_nodes: list[str] = []

        for node_id, node in nodes.items():
            cond = str(node.get("patient_activation_condition", "True")).strip()
            if cond in ("True", "", "None"):
                always_active_nodes.append(node_id)
            elif cond == "False":
                continue
            else:
                conditional_nodes.append(
                    {
                        "node_id": node_id,
                        "condition": cond,
                        "description": node.get("description", node_id),
                    }
                )

        if not conditional_nodes:
            return [
                {
                    "pathway_id": "default",
                    "description": "Single pathway",
                    "active_nodes": always_active_nodes,
                    "patient_context_overrides": {},
                }
            ]

        groups = self._group_by_decision_variable(conditional_nodes)
        combinations = self._enumerate_valid_combinations(groups)
        pathways: list[dict[str, Any]] = []
        for combo in combinations:
            pathway = self._combo_to_pathway(combo, always_active_nodes)
            if pathway:
                pathways.append(pathway)
        return pathways

    def _group_by_decision_variable(
        self,
        conditional_nodes: list[dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        """Group conditional nodes by their decision variable."""
        groups: dict[str, list[dict[str, Any]]] = {}
        for cn in conditional_nodes:
            group_key = self._extract_group_key(cn["condition"])
            if group_key not in groups:
                groups[group_key] = []
            groups[group_key].append(cn)
        return groups

    def _extract_group_key(self, condition: str) -> str:
        """Extract decision variable group key from condition string."""
        in_match = re.search(r"'(\w+)'\s+in\s+patient\.(\w+)", condition)
        if in_match:
            value, field_name = in_match.groups()
            semantic = _SEMANTIC_GROUPS.get(value, value)
            return f"{field_name}:{semantic}"

        comp_match = re.search(r"patient\.(\w+(?:\.\w+)*)\s*[<>=]", condition)
        if comp_match:
            return comp_match.group(1)

        return f"other:{hash(condition) % 1000}"

    def _enumerate_valid_combinations(
        self,
        groups: dict[str, list[dict[str, Any]]],
    ) -> list[tuple[dict[str, Any] | None, ...]]:
        """Enumerate valid pathway combinations (one per group, with None option)."""
        group_lists = list(groups.values())
        if not group_lists:
            return [()]

        group_options: list[list[dict[str, Any] | None]] = []
        for group in group_lists:
            group_options.append(group + [None])

        combos = list(itertools.product(*group_options))
        combos = [c for c in combos if any(x is not None for x in c)]

        valid: list[tuple[dict[str, Any] | None, ...]] = []
        for combo in combos:
            active_nodes = [n for n in combo if n is not None]
            if not self._has_logical_conflict(active_nodes):
                valid.append(combo)
        return valid

    def _has_logical_conflict(self, active_nodes: list[dict[str, Any]]) -> bool:
        """Check for logical conflicts between active nodes."""
        node_set = {n["node_id"] for n in active_nodes}
        for group_a, group_b in _CONFLICT_PAIRS:
            if node_set & group_a and node_set & group_b:
                return True
        return False

    def _combo_to_pathway(
        self,
        combo: tuple[dict[str, Any] | None, ...],
        always_active: list[str],
    ) -> dict[str, Any] | None:
        """Convert combination to pathway definition."""
        active_nodes = always_active.copy()
        patient_overrides: dict[str, Any] = {}
        descriptions: list[str] = []

        for node in combo:
            if node is None:
                continue
            active_nodes.append(node["node_id"])
            descriptions.append(node.get("description", node["node_id"]))
            overrides = self._condition_to_patient_context(node["condition"])
            _merge_overrides(patient_overrides, overrides)

        if not descriptions:
            return None

        pathway_id = "_".join(n["node_id"][:15] for n in combo if n is not None)[:60]

        return {
            "pathway_id": pathway_id,
            "description": " + ".join(descriptions[:3]),
            "active_nodes": active_nodes,
            "patient_context_overrides": patient_overrides,
        }

    def _condition_to_patient_context(self, condition: str) -> dict[str, Any]:
        """Reverse-engineer patient context from condition string."""
        overrides: dict[str, Any] = {}

        for match in re.finditer(r"'(\w+)'\s+in\s+patient\.(\w+)", condition):
            value, field_name = match.groups()
            if field_name not in overrides:
                overrides[field_name] = []
            if isinstance(overrides[field_name], list):
                overrides[field_name].append(value)

        # patient.X.Y < N → Y = N * 0.85
        for match in re.finditer(r"patient\.(\w+)\.(\w+)\s*<\s*([\d.]+)", condition):
            field_name, subfield, threshold = match.groups()
            if field_name not in overrides:
                overrides[field_name] = {}
            if isinstance(overrides[field_name], dict):
                overrides[field_name][subfield] = round(float(threshold) * 0.85, 2)

        # patient.X.Y <= N → Y = N * 0.9
        for match in re.finditer(r"patient\.(\w+)\.(\w+)\s*<=\s*([\d.]+)", condition):
            field_name, subfield, threshold = match.groups()
            if field_name not in overrides:
                overrides[field_name] = {}
            if isinstance(overrides[field_name], dict):
                overrides[field_name][subfield] = round(float(threshold) * 0.9, 2)

        # patient.X.Y > N → Y = N * 1.15
        for match in re.finditer(r"patient\.(\w+)\.(\w+)\s*>\s*([\d.]+)", condition):
            field_name, subfield, threshold = match.groups()
            if field_name not in overrides:
                overrides[field_name] = {}
            if isinstance(overrides[field_name], dict):
                overrides[field_name][subfield] = round(float(threshold) * 1.15, 2)

        # patient.X.Y >= N → Y = N * 1.1
        for match in re.finditer(r"patient\.(\w+)\.(\w+)\s*>=\s*([\d.]+)", condition):
            field_name, subfield, threshold = match.groups()
            if field_name not in overrides:
                overrides[field_name] = {}
            if isinstance(overrides[field_name], dict):
                overrides[field_name][subfield] = round(float(threshold) * 1.1, 2)

        return overrides


def _merge_overrides(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Merge two override dicts."""
    for key, value in source.items():
        if key not in target:
            target[key] = value
        elif isinstance(target[key], list) and isinstance(value, list):
            target[key].extend(v for v in value if v not in target[key])
        elif isinstance(target[key], dict) and isinstance(value, dict):
            target[key].update(value)


# ---------------------------------------------------------------------------
# ValueVariationGenerator
# ---------------------------------------------------------------------------


class ValueVariationGenerator:
    """Generate boundary and extreme value variations for numeric conditional rules."""

    def __init__(self, engine: ConstraintDerivationEngine) -> None:
        self.engine = engine

    def generate_variations(self, rule: dict[str, Any]) -> list[dict[str, Any]]:
        """Generate boundary + extreme-low + extreme-high variations."""
        trigger_range = rule.get("trigger_range", {})
        variations: list[dict[str, Any]] = []

        for var_path, range_spec in trigger_range.items():
            rtype = range_spec.get("type", "float")
            if rtype not in ("float", "int"):
                continue

            rmin = range_spec.get("min")
            rmax = range_spec.get("max")
            if rmin is None or rmax is None:
                continue

            rmin = float(rmin)
            rmax = float(rmax)
            if rmin >= rmax:
                continue

            threshold = self._extract_threshold(rule.get("condition", ""), var_path)
            existing_vals: set[float | int] = set()

            # Boundary value (near threshold)
            if threshold is not None:
                condition = rule.get("condition", "")
                if rtype == "float":
                    boundary_val: float | int = (
                        round(threshold - 0.1, 1) if "<" in condition else round(threshold + 0.1, 1)
                    )
                else:
                    boundary_val = int(threshold - 1) if "<" in condition else int(threshold + 1)
                if rmin <= boundary_val <= rmax:
                    existing_vals.add(boundary_val)
                    variations.append(
                        {
                            "type": "boundary",
                            "var_path": var_path,
                            "value": boundary_val,
                            "description": (f"{var_path.split('.')[-1]}={boundary_val} (near threshold {threshold})"),
                        }
                    )

            # Extreme low (bottom 10% of range)
            if rtype == "float":
                extreme_lo: float | int = round(rmin + (rmax - rmin) * 0.1, 1)
            else:
                extreme_lo = int(rmin)
            if extreme_lo not in existing_vals and rmin <= extreme_lo <= rmax:
                existing_vals.add(extreme_lo)
                variations.append(
                    {
                        "type": "extreme_lo",
                        "var_path": var_path,
                        "value": extreme_lo,
                        "description": (f"{var_path.split('.')[-1]}={extreme_lo} (extreme low)"),
                    }
                )

            # Extreme high (top 10% of range)
            if rtype == "float":
                extreme_hi: float | int = round(rmax - (rmax - rmin) * 0.1, 1)
            else:
                extreme_hi = int(rmax)
            if extreme_hi not in existing_vals and rmin <= extreme_hi <= rmax:
                existing_vals.add(extreme_hi)
                variations.append(
                    {
                        "type": "extreme_hi",
                        "var_path": var_path,
                        "value": extreme_hi,
                        "description": (f"{var_path.split('.')[-1]}={extreme_hi} (extreme high)"),
                    }
                )

        return variations

    def _extract_threshold(self, condition: str, var_path: str) -> float | None:
        """Extract comparison threshold from condition string.

        Handles both direct access and .get() patterns:
        - patient.labs.potassium < 3.3
        - patient.labs.get('potassium', 0) > 5.0
        """
        var_name = var_path.split(".")[-1]
        # Pattern 1: direct access (patient.X.Y op N)
        pattern1 = rf"patient\.\w+\.{re.escape(var_name)}\s*[<>=]+\s*([\d.]+)"
        match = re.search(pattern1, condition)
        if match:
            return float(match.group(1))
        # Pattern 2: .get() style (patient.X.get('Y', default) op N)
        pattern2 = rf"patient\.\w+\.get\('{re.escape(var_name)}'[^)]*\)\s*[<>=]+\s*([\d.]+)"
        match = re.search(pattern2, condition)
        if match:
            return float(match.group(1))
        return None


class PatientGenerator:
    """Generates scenarios from CPG graph conditional rules."""

    def __init__(
        self,
        engine: ConstraintDerivationEngine,
        seed: int | None = 42,
    ) -> None:
        self.engine = engine
        self.rng = random.Random(seed)
        self.base_patient_templates = _load_base_templates()
        self.pathway_analyzer = PathwayAnalyzer(engine)
        self.value_generator = ValueVariationGenerator(engine)

    def generate_from_graph(self, graph: dict[str, Any]) -> list[GeneratedScenario]:
        """Generate scenarios from a single graph.

        Returns:
            List of GeneratedScenario (trigger + normal + value variations +
            combinatorial + pathway normals).
        """
        all_rules = _collect_all_rules(graph)
        scenarios: list[GeneratedScenario] = []

        # 1. Single-rule trigger/normal pairs + value variations
        for rule in all_rules:
            trigger = self._make_trigger_scenario(rule, graph)
            if trigger:
                scenarios.append(trigger)

            normal = self._make_normal_scenario(rule, graph)
            if normal:
                scenarios.append(normal)

            # Value boundary/extreme variations
            value_scenarios = self._generate_value_variations(rule, graph)
            scenarios.extend(value_scenarios)

        # 2. Combinatorial (2-3 rules with independent variables)
        combos = self._generate_combinatorial(all_rules, graph)
        scenarios.extend(combos)

        # 3. Pathway-based normal scenarios
        pathway_scenarios = self._generate_pathway_normals(graph)
        scenarios.extend(pathway_scenarios)

        # 4. Deduplicate (v2: expected+forbidden+triggered)
        scenarios = _deduplicate(scenarios)

        return scenarios

    def generate_all(self, graphs_dir: str | Path) -> list[GeneratedScenario]:
        """Generate scenarios from all graphs in a directory."""
        from .constraint_derivation import load_graph

        all_scenarios: list[GeneratedScenario] = []
        graphs_path = Path(graphs_dir)

        for graph_path in sorted(graphs_path.glob("*.yaml")):
            graph = load_graph(graph_path)
            scenarios = self.generate_from_graph(graph)
            all_scenarios.extend(scenarios)

        return all_scenarios

    def _make_trigger_scenario(self, rule: dict[str, Any], graph: dict[str, Any]) -> GeneratedScenario | None:
        """Create a trigger patient (condition == True)."""
        graph_id = graph.get("graph_id", "unknown")
        trigger_range = rule.get("trigger_range", {})
        if not trigger_range:
            return None

        base = self._get_base_patient(graph_id)
        for var_path, range_spec in trigger_range.items():
            value = self._sample_value(range_spec)
            _set_nested(base, var_path.replace("patient.", ""), value)

        # Verify the condition actually fires with this patient.
        # Compound conditions may need more variables than trigger_range provides.
        if not self.engine._evaluate_condition(rule.get("condition", ""), base):
            return None

        derived = self.engine.derive(
            graph,
            base,
            f"{graph_id}_auto_trigger_{rule['rule_id']}",
        )

        expected = _extract_expected(derived)
        forbidden = _extract_forbidden(derived)
        prefix = _graph_prefix(graph_id)
        suffix = _rule_suffix(rule["rule_id"])

        return GeneratedScenario(
            scenario_id=f"{prefix}_trap_{suffix}",
            guideline_graph=graph_id,
            patient=base,
            derived_constraints=derived.to_yaml(),
            trap_scenario=True,
            trap_description=rule.get("description", ""),
            triggered_rules=[rule["rule_id"]],
            generation_method="auto:single_rule_trigger",
            expected_actions=expected,
            forbidden_actions=forbidden,
        )

    def _make_normal_scenario(self, rule: dict[str, Any], graph: dict[str, Any]) -> GeneratedScenario | None:
        """Create a normal patient (condition == False)."""
        graph_id = graph.get("graph_id", "unknown")
        normal_range = rule.get("normal_range", {})
        if not normal_range:
            return None

        base = self._get_base_patient(graph_id)
        for var_path, range_spec in normal_range.items():
            value = self._sample_value(range_spec)
            _set_nested(base, var_path.replace("patient.", ""), value)

        # Verify the condition does NOT fire with this patient
        if self.engine._evaluate_condition(rule.get("condition", ""), base):
            return None

        derived = self.engine.derive(
            graph,
            base,
            f"{graph_id}_auto_normal_{rule['rule_id']}",
        )

        expected = _extract_expected(derived)
        forbidden = _extract_forbidden(derived)
        prefix = _graph_prefix(graph_id)
        suffix = _rule_suffix(rule["rule_id"])

        return GeneratedScenario(
            scenario_id=f"{prefix}_basic_{suffix}",
            guideline_graph=graph_id,
            patient=base,
            derived_constraints=derived.to_yaml(),
            trap_scenario=False,
            trap_description="",
            triggered_rules=[],
            generation_method="auto:single_rule_normal",
            expected_actions=expected,
            forbidden_actions=forbidden,
        )

    def _generate_combinatorial(
        self,
        rules: list[dict[str, Any]],
        graph: dict[str, Any],
    ) -> list[GeneratedScenario]:
        """Generate patients where 2-3 rules fire simultaneously."""
        graph_id = graph.get("graph_id", "unknown")
        results: list[GeneratedScenario] = []

        # Only combine rules with non-overlapping condition_variables
        for size in range(2, MAX_COMBINATORIAL_SIZE + 1):
            combos = list(itertools.combinations(rules, size))
            self.rng.shuffle(combos)

            for combo in combos[:MAX_COMBINATORIAL_PER_GRAPH]:
                if not _variables_independent(combo):
                    continue

                base = self._get_base_patient(graph_id)
                rule_ids: list[str] = []

                for rule in combo:
                    trigger_range = rule.get("trigger_range", {})
                    for var_path, range_spec in trigger_range.items():
                        value = self._sample_value(range_spec)
                        _set_nested(base, var_path.replace("patient.", ""), value)
                    rule_ids.append(rule["rule_id"])

                derived = self.engine.derive(
                    graph,
                    base,
                    f"{graph_id}_auto_combo_{'_'.join(rule_ids)}",
                )

                # Verify all rules actually fired
                triggered_rule_ids = {
                    c.provenance.split(":rule:")[-1]
                    for c in derived.all_constraints()
                    if c.is_conditional and ":rule:" in c.provenance
                }
                if not all(rid in triggered_rule_ids for rid in rule_ids):
                    continue

                expected = _extract_expected(derived)
                forbidden = _extract_forbidden(derived)

                # Skip over-activated combos
                if len(expected) > MAX_EXPECTED_ACTIONS:
                    continue

                prefix = _graph_prefix(graph_id)
                suffix = "_".join(_rule_suffix(rid) for rid in rule_ids)

                results.append(
                    GeneratedScenario(
                        scenario_id=f"{prefix}_combo_{suffix}",
                        guideline_graph=graph_id,
                        patient=base,
                        derived_constraints=derived.to_yaml(),
                        trap_scenario=True,
                        trap_description=("Multi-rule trap: " + ", ".join(rule_ids)),
                        triggered_rules=rule_ids,
                        generation_method="auto:combinatorial",
                        expected_actions=expected,
                        forbidden_actions=forbidden,
                    )
                )

                if len(results) >= MAX_COMBINATORIAL_PER_GRAPH:
                    break

        return results

    def _sample_value(self, range_spec: dict[str, Any]) -> Any:
        """Sample a value from a range specification."""
        rtype = range_spec.get("type", "float")

        if rtype == "float":
            lo = float(range_spec.get("min", 0))
            hi = float(range_spec.get("max", 100))
            return round(self.rng.uniform(lo, hi), 1)
        if rtype == "int":
            lo = int(range_spec.get("min", 0))
            hi = int(range_spec.get("max", 100))
            return self.rng.randint(lo, hi)
        if rtype == "list_contains":
            return range_spec.get("contains")
        if rtype == "list_not_contains":
            return None

        # Fallback: if "contains" key exists, treat as list_contains
        if "contains" in range_spec:
            return range_spec["contains"]
        if "not_contains" in range_spec:
            return None

        return None

    def _get_base_patient(self, graph_id: str) -> dict[str, Any]:
        """Get a deep copy of the base patient template for a graph."""
        template = self.base_patient_templates.get(graph_id, self.base_patient_templates["default"])
        return copy.deepcopy(template)

    # ------------------------------------------------------------------
    # New generation methods
    # ------------------------------------------------------------------

    def _generate_value_variations(
        self,
        rule: dict[str, Any],
        graph: dict[str, Any],
    ) -> list[GeneratedScenario]:
        """Generate boundary + extreme value variation scenarios for one rule."""
        graph_id = graph.get("graph_id", "unknown")
        variations = self.value_generator.generate_variations(rule)
        scenarios: list[GeneratedScenario] = []

        for var in variations:
            base = self._get_base_patient(graph_id)

            trigger_range = rule.get("trigger_range", {})
            for var_path, range_spec in trigger_range.items():
                if var_path == var["var_path"]:
                    _set_nested(base, var_path.replace("patient.", ""), var["value"])
                else:
                    value = self._sample_value(range_spec)
                    if value is not None:
                        _set_nested(base, var_path.replace("patient.", ""), value)

            if not self.engine._evaluate_condition(rule.get("condition", ""), base):
                continue

            derived = self.engine.derive(
                graph,
                base,
                f"{graph_id}_val_{var['type']}_{rule['rule_id']}",
            )
            expected = _extract_expected(derived)
            forbidden = _extract_forbidden(derived)

            prefix = _graph_prefix(graph_id)
            suffix = _rule_suffix(rule["rule_id"])
            var_short = var["var_path"].split(".")[-1][:8]

            scenarios.append(
                GeneratedScenario(
                    scenario_id=f"{prefix}_trap_{suffix}_{var_short}_{var['type']}",
                    guideline_graph=graph_id,
                    patient=base,
                    derived_constraints=derived.to_yaml(),
                    trap_scenario=True,
                    trap_description=(f"{rule.get('description', '')} [{var['description']}]"),
                    triggered_rules=[rule["rule_id"]],
                    generation_method=f"auto:value_{var['type']}",
                    expected_actions=expected,
                    forbidden_actions=forbidden,
                )
            )

        return scenarios

    def _generate_pathway_normals(
        self,
        graph: dict[str, Any],
    ) -> list[GeneratedScenario]:
        """Generate pathway-based normal (baseline) scenarios."""
        graph_id = graph.get("graph_id", "unknown")
        pathways = self.pathway_analyzer.find_pathway_combinations(graph)
        scenarios: list[GeneratedScenario] = []

        for pw in pathways:
            base = self._get_base_patient(graph_id)
            _apply_overrides(base, pw["patient_context_overrides"])

            derived = self.engine.derive(
                graph,
                base,
                f"{graph_id}_pathway_{pw['pathway_id']}",
            )
            expected = _extract_expected(derived)
            forbidden = _extract_forbidden(derived)

            if not expected:
                continue

            # Skip over-activated pathways (mutually exclusive nodes
            # sharing the same patient_activation_condition)
            if len(expected) > MAX_EXPECTED_ACTIONS:
                continue

            prefix = _graph_prefix(graph_id)
            scenarios.append(
                GeneratedScenario(
                    scenario_id=f"{prefix}_pathway_{pw['pathway_id']}",
                    guideline_graph=graph_id,
                    patient=base,
                    derived_constraints=derived.to_yaml(),
                    trap_scenario=False,
                    trap_description="",
                    triggered_rules=[],
                    generation_method="auto:pathway_normal",
                    expected_actions=expected,
                    forbidden_actions=forbidden,
                    pathway_id=pw["pathway_id"],
                    pathway_description=pw["description"],
                )
            )

        return scenarios


def _extract_expected(derived: DerivedConstraintSet) -> list[str]:
    """Extract expected action IDs from DerivedConstraintSet."""
    actions: list[str] = []
    for c in derived.expected:
        actions.extend(c.actions)
    for c in derived.required:
        actions.extend(c.actions)
    return sorted(set(actions))


def _extract_forbidden(derived: DerivedConstraintSet) -> list[str]:
    """Extract forbidden action IDs from DerivedConstraintSet."""
    actions: list[str] = []
    for c in derived.forbidden:
        actions.extend(c.actions)
    return sorted(set(actions))


def _apply_overrides(patient: dict[str, Any], overrides: dict[str, Any]) -> None:
    """Apply pathway context overrides to patient dict."""
    for key, value in overrides.items():
        if isinstance(value, list):
            existing = patient.get(key, [])
            if isinstance(existing, list):
                patient[key] = existing + [v for v in value if v not in existing]
            else:
                patient[key] = value
        elif isinstance(value, dict):
            existing = patient.get(key, {})
            if isinstance(existing, dict):
                existing.update(value)
                patient[key] = existing
            else:
                patient[key] = value
        else:
            patient[key] = value


def _collect_all_rules(graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Collect conditional_rules from all nodes, skipping companion-only rules.

    Rules with ``skip_scenario_generation: true`` are companion FORBIDDEN
    rules that exist solely to provide differentiation for their parent
    rule's trigger patients.  They participate in constraint derivation
    (so the trap patient picks up unique forbidden actions) but must NOT
    generate their own trigger/normal/value-variation scenarios.
    """
    rules: list[dict[str, Any]] = []
    for node_id, node in graph.get("nodes", {}).items():
        for rule in node.get("conditional_rules", []):
            if rule.get("skip_scenario_generation", False):
                continue
            rule_copy = dict(rule)
            rule_copy["_node_id"] = node_id
            rules.append(rule_copy)
    return rules


def _set_nested(d: dict[str, Any], path: str, value: Any) -> None:
    """Set a nested dict value using dot-separated path.

    Handles list_contains by appending to existing lists.
    """
    keys = path.split(".")
    current = d

    for key in keys[:-1]:
        if key not in current or not isinstance(current[key], dict):
            current[key] = {}
        current = current[key]

    final_key = keys[-1]
    existing = current.get(final_key)

    if isinstance(value, str) and isinstance(existing, list):
        if value not in existing:
            existing.append(value)
    elif value is None:
        pass  # list_not_contains: don't modify
    else:
        current[final_key] = value


def _variables_independent(
    rules: tuple[dict[str, Any], ...],
) -> bool:
    """Check if rules have non-overlapping condition_variables."""
    all_vars: list[set[str]] = []
    for rule in rules:
        cvars = set(rule.get("condition_variables", []))
        all_vars.append(cvars)

    for i, vars_a in enumerate(all_vars):
        for vars_b in all_vars[i + 1 :]:
            if vars_a & vars_b:
                return False
    return True


def _deduplicate(
    scenarios: list[GeneratedScenario],
) -> list[GeneratedScenario]:
    """Remove scenarios with identical (expected, forbidden, triggered, method).

    V2: uses expected_actions + forbidden_actions + generation_method instead of
    just triggered_rules.  Includes generation_method so value variations
    (boundary/extreme) survive even when they share the same expected set as
    the original trigger scenario.
    """
    seen: set[tuple[frozenset[str], frozenset[str], frozenset[str], str]] = set()
    unique: list[GeneratedScenario] = []

    for s in scenarios:
        key = (
            frozenset(s.expected_actions),
            frozenset(s.forbidden_actions),
            frozenset(s.triggered_rules),
            s.generation_method,
        )
        if key not in seen:
            seen.add(key)
            unique.append(s)

    return unique


def _graph_prefix(graph_id: str) -> str:
    return _GRAPH_PREFIX_MAP.get(graph_id, graph_id[:6])


def _rule_suffix(rule_id: str) -> str:
    """Convert rule_id to short suffix.

    "DKA-HYPOK-INSULIN-GATE" -> "hypok_insulin_gate"
    """
    parts = rule_id.lower().split("-")[1:]
    return "_".join(parts)


def _load_base_templates() -> dict[str, dict[str, Any]]:
    """Base patient templates per domain."""
    return {
        "ada_dka_management": {
            "age": 35,
            "sex": "M",
            "chief_complaint": "nausea, vomiting, abdominal pain",
            "labs": {
                "glucose": 450,
                "ph": 7.15,
                "potassium": 4.0,
                "bicarbonate": 10,
                "anion_gap": 24,
            },
            "vitals": {
                "hr": 110,
                "sbp": 100,
                "dbp": 60,
                "rr": 28,
                "spo2": 97,
                "temp": 37.2,
                "map_mmhg": 73,
            },
            "comorbidities": ["type_1_diabetes"],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {},
        },
        "aha_chest_pain": {
            "age": 62,
            "sex": "M",
            "chief_complaint": "chest pain",
            "labs": {"troponin": 0.5, "egfr": 85},
            "vitals": {
                "hr": 88,
                "sbp": 145,
                "dbp": 90,
                "rr": 20,
                "spo2": 96,
                "temp": 37.0,
                "map_mmhg": 108,
            },
            "comorbidities": ["hypertension"],
            "allergies": [],
            "medications": [],
            "history": [],
            "ecg_findings": [],
            "presentation": {"symptom_onset_hours": 2},
        },
        "aha_heart_failure": {
            "age": 68,
            "sex": "M",
            "chief_complaint": "dyspnea, leg edema",
            "labs": {
                "bnp": 1200,
                "potassium": 4.2,
                "creatinine": 1.4,
                "bun_cr_ratio": 15,
            },
            "vitals": {
                "hr": 92,
                "sbp": 110,
                "dbp": 70,
                "rr": 24,
                "spo2": 93,
                "temp": 36.8,
                "map_mmhg": 83,
                "heart_rate": 92,
                "sbp_orthostatic_drop": 5,
            },
            "comorbidities": ["heart_failure", "hypertension"],
            "allergies": [],
            "medications": [],
            "history": [],
            "exam_findings": [],
            "presentation": {},
        },
        "aha_stroke": {
            "age": 72,
            "sex": "F",
            "chief_complaint": "sudden weakness, speech difficulty",
            "labs": {"inr": 1.0, "glucose": 130, "platelets": 200},
            "vitals": {
                "hr": 82,
                "sbp": 170,
                "dbp": 95,
                "rr": 18,
                "spo2": 97,
                "temp": 37.0,
                "map_mmhg": 120,
            },
            "comorbidities": ["hypertension", "atrial_fibrillation"],
            "allergies": [],
            "medications": [],
            "history": [],
            "imaging": [],
            "presentation": {},
        },
        "ssc_sepsis_hour1": {
            "age": 58,
            "sex": "M",
            "chief_complaint": "fever, altered mental status",
            "labs": {
                "lactate": 4.2,
                "wbc": 18.5,
                "creatinine": 2.1,
                "platelets": 120,
            },
            "vitals": {
                "hr": 115,
                "sbp": 85,
                "dbp": 50,
                "rr": 26,
                "spo2": 92,
                "temp": 39.2,
                "map_mmhg": 62,
            },
            "comorbidities": [],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {},
        },
        "atrial_fibrillation": {
            "age": 70,
            "sex": "M",
            "chief_complaint": "palpitations, dizziness",
            "labs": {"egfr": 65, "tsh": 2.0},
            "vitals": {
                "hr": 142,
                "sbp": 130,
                "dbp": 80,
                "rr": 18,
                "spo2": 97,
                "temp": 37.0,
                "map_mmhg": 97,
            },
            "comorbidities": ["hypertension"],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {"af_duration_hours": 6},
        },
        "kdigo_aki_full": {
            "age": 65,
            "sex": "M",
            "chief_complaint": "decreased urine output",
            "labs": {
                "creatinine": 3.5,
                "potassium": 5.2,
                "bun": 45,
                "egfr": 15,
            },
            "vitals": {
                "hr": 88,
                "sbp": 135,
                "dbp": 80,
                "rr": 18,
                "spo2": 96,
                "temp": 37.0,
                "map_mmhg": 98,
            },
            "comorbidities": ["hypertension", "diabetes"],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {},
        },
        "kdigo_contrast_aki": {
            "age": 70,
            "sex": "M",
            "chief_complaint": "cardiac catheterization planned",
            "labs": {"creatinine": 2.0, "egfr": 28},
            "vitals": {
                "hr": 78,
                "sbp": 140,
                "dbp": 85,
                "rr": 16,
                "spo2": 97,
                "temp": 37.0,
                "map_mmhg": 103,
            },
            "comorbidities": ["ckd_stage_4", "diabetes"],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {},
        },
        "pulmonary_embolism": {
            "age": 55,
            "sex": "F",
            "chief_complaint": "acute dyspnea, pleuritic chest pain",
            "labs": {"d_dimer": 2500, "troponin": 0.15, "egfr": 75},
            "vitals": {
                "hr": 110,
                "sbp": 105,
                "dbp": 65,
                "rr": 24,
                "spo2": 91,
                "temp": 37.0,
                "map_mmhg": 78,
            },
            "comorbidities": [],
            "allergies": [],
            "medications": [],
            "history": [],
            "weight_kg": 75,
            "presentation": {},
        },
        "cap_pneumonia": {
            "age": 60,
            "sex": "M",
            "chief_complaint": "cough, fever, dyspnea",
            "labs": {"wbc": 15.2, "procalcitonin": 2.5},
            "vitals": {
                "hr": 100,
                "sbp": 110,
                "dbp": 70,
                "rr": 24,
                "spo2": 93,
                "temp": 38.8,
                "map_mmhg": 83,
            },
            "comorbidities": [],
            "allergies": [],
            "medications": [],
            "history": [],
            "procedures": [],
            "presentation": {},
        },
        "copd_exacerbation": {
            "age": 68,
            "sex": "M",
            "chief_complaint": "worsening dyspnea, increased sputum",
            "labs": {"pco2": 48, "ph": 7.35},
            "vitals": {
                "hr": 95,
                "sbp": 140,
                "dbp": 85,
                "rr": 26,
                "spo2": 89,
                "temp": 37.5,
                "map_mmhg": 103,
            },
            "comorbidities": ["copd"],
            "allergies": [],
            "medications": [],
            "history": [],
            "imaging": [],
            "presentation": {},
        },
        "gi_bleeding": {
            "age": 58,
            "sex": "M",
            "chief_complaint": "hematemesis, melena",
            "labs": {
                "hemoglobin": 8.5,
                "inr": 1.2,
                "platelets": 180,
                "bun": 35,
            },
            "vitals": {
                "hr": 105,
                "sbp": 100,
                "dbp": 60,
                "rr": 20,
                "spo2": 96,
                "temp": 37.0,
                "map_mmhg": 73,
                "heart_rate": 105,
            },
            "comorbidities": [],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {},
        },
        "hypertensive_emergency": {
            "age": 55,
            "sex": "M",
            "chief_complaint": "severe headache, blurred vision",
            "labs": {"creatinine": 1.8, "egfr": 40},
            "vitals": {
                "hr": 90,
                "sbp": 220,
                "dbp": 130,
                "rr": 20,
                "spo2": 97,
                "temp": 37.0,
                "map_mmhg": 160,
            },
            "comorbidities": ["hypertension"],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {},
        },
        "universal_clinical_safety": {
            "age": 55,
            "sex": "M",
            "chief_complaint": "",
            "labs": {"egfr": 85},
            "vitals": {
                "hr": 80,
                "sbp": 130,
                "dbp": 80,
                "rr": 16,
                "spo2": 98,
                "temp": 37.0,
                "map_mmhg": 97,
            },
            "comorbidities": [],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {},
        },
        "anaphylaxis_management": {
            "age": 35,
            "sex": "F",
            "chief_complaint": "acute onset urticaria, dyspnea, hypotension",
            "labs": {},
            "vitals": {
                "hr": 120,
                "sbp": 80,
                "dbp": 50,
                "rr": 28,
                "spo2": 90,
                "temp": 37.0,
                "map_mmhg": 60,
            },
            "comorbidities": [],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {},
        },
        "acls_cardiac_arrest": {
            "age": 60,
            "sex": "M",
            "chief_complaint": "unresponsive, pulseless",
            "labs": {"potassium": 4.5},
            "vitals": {
                "hr": 0,
                "sbp": 0,
                "dbp": 0,
                "rr": 0,
                "spo2": 0,
                "temp": 36.5,
                "map_mmhg": 0,
            },
            "comorbidities": [],
            "allergies": [],
            "medications": [],
            "history": [],
            "rhythm": [],
            "exam_findings": [],
            "presentation": {},
        },
        "status_epilepticus": {
            "age": 45,
            "sex": "M",
            "chief_complaint": "continuous seizure activity >5 minutes",
            "labs": {"glucose": 110, "sodium": 138},
            "vitals": {
                "hr": 110,
                "sbp": 160,
                "dbp": 95,
                "rr": 8,
                "spo2": 88,
                "temp": 38.5,
                "map_mmhg": 117,
            },
            "comorbidities": [],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {},
        },
        "gina_asthma_exacerbation": {
            "age": 30,
            "sex": "F",
            "chief_complaint": "severe wheezing, dyspnea",
            "labs": {},
            "vitals": {
                "hr": 115,
                "sbp": 130,
                "dbp": 80,
                "rr": 30,
                "spo2": 91,
                "temp": 37.0,
                "map_mmhg": 97,
                "pef_percent": 40,
            },
            "comorbidities": ["asthma"],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {},
        },
        "idsa_meningitis": {
            "age": 40,
            "sex": "M",
            "chief_complaint": "severe headache, neck stiffness, fever",
            "labs": {"wbc": 18.0, "glucose": 100},
            "vitals": {
                "hr": 105,
                "sbp": 135,
                "dbp": 85,
                "rr": 22,
                "spo2": 97,
                "temp": 39.5,
                "map_mmhg": 102,
            },
            "comorbidities": [],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {"delay_to_lp_minutes": 15},
        },
        "toxicology_management": {
            "age": 28,
            "sex": "F",
            "chief_complaint": "intentional ingestion",
            "labs": {},
            "vitals": {
                "hr": 95,
                "sbp": 110,
                "dbp": 70,
                "rr": 18,
                "spo2": 97,
                "temp": 37.0,
                "map_mmhg": 83,
                "qrs_ms": 80,
            },
            "comorbidities": [],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {},
        },
        "default": {
            "age": 55,
            "sex": "M",
            "chief_complaint": "",
            "labs": {},
            "vitals": {
                "hr": 80,
                "sbp": 130,
                "dbp": 80,
                "rr": 16,
                "spo2": 98,
                "temp": 37.0,
                "map_mmhg": 97,
            },
            "comorbidities": [],
            "allergies": [],
            "medications": [],
            "history": [],
            "presentation": {},
        },
    }
