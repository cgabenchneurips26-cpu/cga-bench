"""Constraint Derivation Engine

CPG graph + patient context -> derived constraint set with provenance.

Each constraint carries a provenance chain:
    graph:{graph_id}:node:{node_id}:rule:{rule_id} -> guideline evidence

This engine is the core of the "new CPG graph in -> scenarios out" pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any

import yaml


@dataclass
class DerivedConstraint:
    """A single derived constraint with full provenance."""

    constraint_type: str  # FORBIDDEN, REQUIRED, BEFORE, WITHIN, EXPECTED
    actions: list[str]
    provenance: str  # "graph:{id}:node:{id}:rule:{id}"
    evidence: str  # guideline reference
    severity: str  # CRITICAL, HIGH, MODERATE, LOW
    description: str
    condition_met: str  # human-readable condition evaluation
    is_conditional: bool  # True=from conditional rule, False=unconditional
    # Authority provenance (E9 High-Authority Core Robustness audit)
    recommendation_class: str | None = None  # AHA Class I, IIa, IIb, III
    evidence_level: str | None = None  # GRADE A, B, C
    source_guideline: str | None = None  # IDSA, KDIGO, AABB, AHA, etc.
    authority_tier: str = "unknown"  # "high" | "low" | "unknown"


@dataclass
class DerivedConstraintSet:
    """Complete derived constraint set for a scenario."""

    scenario_id: str
    graph_id: str
    forbidden: list[DerivedConstraint] = field(default_factory=list)
    required: list[DerivedConstraint] = field(default_factory=list)
    before: list[DerivedConstraint] = field(default_factory=list)
    within: list[DerivedConstraint] = field(default_factory=list)
    expected: list[DerivedConstraint] = field(default_factory=list)
    # B-cde-rescoring (v1.1): same-action REQUIRED ∩ FORBIDDEN under co-satisfiable
    # conditions surfaced as CONFLICT instead of silently dropped.
    conflicts: list[DerivedConstraint] = field(default_factory=list)

    total_rules_evaluated: int = 0
    total_rules_triggered: int = 0

    def add(self, constraint: DerivedConstraint) -> None:
        """Add a constraint to the appropriate list."""
        # plural form attribute lookup ("CONFLICT" -> "conflicts", "FORBIDDEN" -> "forbidden")
        ctype = constraint.constraint_type.lower()
        target = getattr(self, ctype, None)
        if target is None and ctype.endswith("s") is False:
            target = getattr(self, ctype + "s", None)
        if target is not None:
            target.append(constraint)

    def all_constraints(self) -> list[DerivedConstraint]:
        """Return all constraints across all types."""
        return (
            self.forbidden
            + self.required
            + self.before
            + self.within
            + self.expected
            + self.conflicts
        )

    def to_yaml(self) -> dict[str, Any]:
        """Serialize to YAML-compatible dict."""
        return {
            "scenario_id": self.scenario_id,
            "graph_id": self.graph_id,
            "total_rules_evaluated": self.total_rules_evaluated,
            "total_rules_triggered": self.total_rules_triggered,
            "forbidden": [_constraint_to_dict(c) for c in self.forbidden],
            "required": [_constraint_to_dict(c) for c in self.required],
            "before": [_constraint_to_dict(c) for c in self.before],
            "within": [_constraint_to_dict(c) for c in self.within],
            "expected": [_constraint_to_dict(c) for c in self.expected],
            "conflicts": [_constraint_to_dict(c) for c in self.conflicts],
        }

    def to_audit_row(self) -> dict[str, Any]:
        """Single row for Rule Coverage Audit Matrix."""
        return {
            "scenario_id": self.scenario_id,
            "graph_id": self.graph_id,
            "num_forbidden": len(self.forbidden),
            "num_required": len(self.required),
            "num_before": len(self.before),
            "num_within": len(self.within),
            "num_expected": len(self.expected),
            "num_conflicts": len(self.conflicts),
            "total_constraints": len(self.all_constraints()),
            "conditional_count": sum(1 for c in self.all_constraints() if c.is_conditional),
            "unconditional_count": sum(1 for c in self.all_constraints() if not c.is_conditional),
        }


def _constraint_to_dict(c: DerivedConstraint) -> dict[str, Any]:
    return {
        "constraint_type": c.constraint_type,
        "actions": c.actions,
        "provenance": c.provenance,
        "evidence": c.evidence,
        "severity": c.severity,
        "description": c.description,
        "condition_met": c.condition_met,
        "is_conditional": c.is_conditional,
        "recommendation_class": c.recommendation_class,
        "evidence_level": c.evidence_level,
        "source_guideline": c.source_guideline,
        "authority_tier": c.authority_tier,
    }


class DotDict(dict):  # type: ignore[type-arg]
    """Dot-notation accessible dict for safe condition evaluation."""

    def __getattr__(self, key: str) -> Any:
        val = self.get(key)
        if isinstance(val, dict):
            return DotDict(val)
        if val is None:
            return DotDict()
        return val

    def __bool__(self) -> bool:
        return len(self) > 0


_ALLERGY_DRUG_MAP_PATH = Path(__file__).parent / "allergy_drug_map.yaml"


# Authority classification (E9 High-Authority Core Robustness audit).
# A constraint is "high" iff (Class I or IIa) AND (LOE A or B), OR
# the source guideline is one of the strong-recommendation taxonomies
# (IDSA, KDIGO, AABB) where the embedded class/LOE already implies strong.
# Source: docs/attack_gap_exp_exp/260430_e9_High-Authority_Core_Robustness.md
_HIGH_AUTHORITY_CLASS = {"I", "IIa", "1", "1a", "1b"}
_HIGH_AUTHORITY_LOE = {"A", "B", "1A", "1B"}
_STRONG_GUIDELINE_KEYWORDS = (
    "idsa",
    "kdigo",
    "aabb",
    "grade 1a",
    "grade 1b",
    "strong recommendation",
)


def _classify_authority(
    recommendation_class: str | None,
    evidence_level: str | None,
    source_guideline: str | None,
) -> str:
    """Return 'high' | 'low' | 'unknown' for a node's authority."""
    rc = (recommendation_class or "").strip()
    el = (evidence_level or "").strip()
    sg = (source_guideline or "").strip().lower()

    if rc and el:
        if rc in _HIGH_AUTHORITY_CLASS and el in _HIGH_AUTHORITY_LOE:
            return "high"
        return "low"

    if sg and any(kw in sg for kw in _STRONG_GUIDELINE_KEYWORDS):
        return "high"

    if rc or el or sg:
        return "low"
    return "unknown"


def _node_authority(node: dict[str, Any]) -> tuple[str | None, str | None, str | None, str]:
    """Extract (recommendation_class, evidence_level, source_guideline, tier) from a node."""
    rc = node.get("recommendation_class")
    el = node.get("evidence_level")
    sg = node.get("source_guideline")
    tier = _classify_authority(rc, el, sg)
    return rc, el, sg, tier


class ConstraintDerivationEngine:
    """Main engine: graph + patient -> DerivedConstraintSet."""

    def __init__(self) -> None:
        self.allergy_drug_map = self._load_allergy_drug_map()

    def derive(
        self,
        graph: dict[str, Any],
        patient: dict[str, Any],
        scenario_id: str = "",
    ) -> DerivedConstraintSet:
        """Derive constraints from graph + patient context.

        Args:
            graph: Loaded graph YAML dict.
            patient: Patient context dict with labs, medications,
                     comorbidities, allergies, vitals, etc.
            scenario_id: For logging/tracking.

        Returns:
            DerivedConstraintSet with full provenance.
        """
        graph_id = graph.get("graph_id", "unknown")
        result = DerivedConstraintSet(scenario_id=scenario_id, graph_id=graph_id)

        nodes = graph.get("nodes", {})
        for node_id, node in nodes.items():
            self._process_unconditional_forbidden(node_id, node, graph_id, result)
            self._process_sequence_rules(node_id, node, graph_id, result)
            self._process_required_prior_actions(node_id, node, graph_id, result)
            self._process_conditional_rules(node_id, node, graph_id, patient, result)

        self._process_allergy_forbidden(patient, result)

        # 5. Expected actions from pathway activation
        self._process_expected_actions(nodes, graph_id, patient, result)

        # 6. B-cde-rescoring (v1.1): surface REQUIRED ∩ FORBIDDEN same-action conflicts
        self._detect_required_forbidden_conflicts(result)

        return result

    def _process_unconditional_forbidden(
        self,
        node_id: str,
        node: dict[str, Any],
        graph_id: str,
        result: DerivedConstraintSet,
    ) -> None:
        rc, el, sg, tier = _node_authority(node)
        for action in node.get("forbidden_actions", []):
            result.add(
                DerivedConstraint(
                    constraint_type="FORBIDDEN",
                    actions=[action],
                    provenance=f"graph:{graph_id}:node:{node_id}:unconditional",
                    evidence=node.get("source_guideline", ""),
                    severity="HARD",
                    description=f"Unconditionally forbidden in {node_id}",
                    condition_met="always",
                    is_conditional=False,
                    recommendation_class=rc,
                    evidence_level=el,
                    source_guideline=sg,
                    authority_tier=tier,
                )
            )

    def _process_sequence_rules(
        self,
        node_id: str,
        node: dict[str, Any],
        graph_id: str,
        result: DerivedConstraintSet,
    ) -> None:
        rc, el, sg, tier = _node_authority(node)
        for seq in node.get("sequence_rules", []):
            # Handle both formats:
            # 1. List format: ["action_a", "action_b"]
            # 2. Dict format: {"before": "action_a", "after": "action_b"}
            if isinstance(seq, dict):
                before_action = seq.get("before", "")
                after_action = seq.get("after", "")
                desc = seq.get("description", f"{before_action} must precede {after_action}")
                if before_action and after_action:
                    result.add(
                        DerivedConstraint(
                            constraint_type="BEFORE",
                            actions=[before_action, after_action],
                            provenance=f"graph:{graph_id}:node:{node_id}:sequence",
                            evidence=node.get("source_guideline", ""),
                            severity="HARD",
                            description=desc,
                            condition_met="always",
                            is_conditional=False,
                            recommendation_class=rc,
                            evidence_level=el,
                            source_guideline=sg,
                            authority_tier=tier,
                        )
                    )
            elif isinstance(seq, list) and len(seq) >= 2:
                result.add(
                    DerivedConstraint(
                        constraint_type="BEFORE",
                        actions=list(seq),
                        provenance=f"graph:{graph_id}:node:{node_id}:sequence",
                        evidence=node.get("source_guideline", ""),
                        severity="HARD",
                        description=f"{seq[0]} must precede {seq[1]}",
                        condition_met="always",
                        is_conditional=False,
                        recommendation_class=rc,
                        evidence_level=el,
                        source_guideline=sg,
                        authority_tier=tier,
                    )
                )

    def _process_required_prior_actions(
        self,
        node_id: str,
        node: dict[str, Any],
        graph_id: str,
        result: DerivedConstraintSet,
    ) -> None:
        """Convert required_prior_actions to BEFORE constraints.

        Format: {action: [prior_action1, prior_action2]}
        Meaning: prior_action must be done BEFORE action.
        """
        rpa = node.get("required_prior_actions", {})
        if not isinstance(rpa, dict):
            return
        rc, el, sg, tier = _node_authority(node)
        for action, priors in rpa.items():
            if not isinstance(priors, list):
                continue
            for prior in priors:
                result.add(
                    DerivedConstraint(
                        constraint_type="BEFORE",
                        actions=[prior, action],
                        provenance=f"graph:{graph_id}:node:{node_id}:required_prior",
                        evidence=node.get("source_guideline", ""),
                        severity="HARD",
                        description=f"{prior} must precede {action}",
                        condition_met="always",
                        is_conditional=False,
                        recommendation_class=rc,
                        evidence_level=el,
                        source_guideline=sg,
                        authority_tier=tier,
                    )
                )

    def _process_conditional_rules(
        self,
        node_id: str,
        node: dict[str, Any],
        graph_id: str,
        patient: dict[str, Any],
        result: DerivedConstraintSet,
    ) -> None:
        node_rc, node_el, node_sg, _ = _node_authority(node)
        for rule in node.get("conditional_rules", []):
            result.total_rules_evaluated += 1
            condition = rule.get("condition", "")

            if self._evaluate_condition(condition, patient):
                result.total_rules_triggered += 1
                effect = rule.get("effect", {})
                condition_met_str = self._format_condition_met(condition, patient)

                rule_rc = rule.get("recommendation_class") or node_rc
                rule_el = rule.get("evidence_level") or node_el
                rule_sg = rule.get("source_guideline") or node_sg
                rule_tier = _classify_authority(rule_rc, rule_el, rule_sg)

                result.add(
                    DerivedConstraint(
                        constraint_type=effect.get("type", "FORBIDDEN"),
                        actions=effect.get("actions", []),
                        provenance=(f"graph:{graph_id}:node:{node_id}:rule:{rule.get('rule_id', 'unknown')}"),
                        evidence=rule.get("evidence", ""),
                        severity=rule.get("severity", "HIGH"),
                        description=rule.get("description", ""),
                        condition_met=condition_met_str,
                        is_conditional=True,
                        recommendation_class=rule_rc,
                        evidence_level=rule_el,
                        source_guideline=rule_sg,
                        authority_tier=rule_tier,
                    )
                )

    def _process_allergy_forbidden(
        self,
        patient: dict[str, Any],
        result: DerivedConstraintSet,
    ) -> None:
        for allergy in patient.get("allergies", []):
            allergy_key = allergy.lower().strip()
            forbidden_drugs = self.allergy_drug_map.get(allergy_key, [])
            for drug in forbidden_drugs:
                # Drug-allergy contraindications are unconditionally high-authority
                # by clinical convention (any guideline + safety standard).
                result.add(
                    DerivedConstraint(
                        constraint_type="FORBIDDEN",
                        actions=[f"give_{drug}"],
                        provenance=f"allergy_map:{allergy_key}",
                        evidence="Standard drug allergy cross-reactivity",
                        severity="CRITICAL",
                        description=(f"Patient allergic to {allergy}, {drug} contraindicated"),
                        condition_met=f"'{allergy}' in patient.allergies",
                        is_conditional=True,
                        recommendation_class="I",
                        evidence_level="A",
                        source_guideline="Drug Allergy Standard",
                        authority_tier="high",
                    )
                )

    def _process_expected_actions(
        self,
        nodes: dict[str, Any],
        graph_id: str,
        patient: dict[str, Any],
        result: DerivedConstraintSet,
    ) -> None:
        """Derive expected actions from activated pathway nodes.

        Strategy:
        1. Nodes with no precondition or precondition=null -> always active
        2. Nodes with patient_activation_condition -> evaluate against patient
        3. Nodes with precondition -> attempt to evaluate
        4. Collect mandatory_actions from all active nodes
        """
        seen_actions: set[str] = set()
        # Forbidden index: action -> list of (provenance, condition_met) for conflict surfacing
        forbidden_index: dict[str, list[tuple[str, str]]] = {}
        for c in result.forbidden:
            for a in c.actions:
                forbidden_index.setdefault(a, []).append((c.provenance, c.condition_met))

        for node_id, node in nodes.items():
            if not self._is_node_active(node, patient):
                continue

            rc, el, sg, tier = _node_authority(node)

            # Collect mandatory_actions as expected
            for action in node.get("mandatory_actions", []):
                if action in forbidden_index:
                    # B-cde-rescoring v1.1: surface as CONFLICT instead of silent drop
                    self._emit_conflict_for_action(
                        action=action,
                        required_provenance=f"graph:{graph_id}:node:{node_id}:mandatory",
                        required_condition="pathway_active",
                        forbidden_entries=forbidden_index[action],
                        result=result,
                    )
                    continue
                if action not in seen_actions:
                    seen_actions.add(action)
                    result.add(
                        DerivedConstraint(
                            constraint_type="EXPECTED",
                            actions=[action],
                            provenance=f"graph:{graph_id}:node:{node_id}:mandatory",
                            evidence=node.get("source_guideline", ""),
                            severity="STANDARD",
                            description=f"Mandatory action from active node {node_id}",
                            condition_met="pathway_active",
                            is_conditional=False,
                            recommendation_class=rc,
                            evidence_level=el,
                            source_guideline=sg,
                            authority_tier=tier,
                        )
                    )

            # Collect expected_actions if present (some graphs use this)
            for action in node.get("expected_actions", []):
                if action in forbidden_index:
                    self._emit_conflict_for_action(
                        action=action,
                        required_provenance=f"graph:{graph_id}:node:{node_id}:expected",
                        required_condition="pathway_active",
                        forbidden_entries=forbidden_index[action],
                        result=result,
                    )
                    continue
                if action not in seen_actions:
                    seen_actions.add(action)
                    result.add(
                        DerivedConstraint(
                            constraint_type="EXPECTED",
                            actions=[action],
                            provenance=f"graph:{graph_id}:node:{node_id}:expected",
                            evidence=node.get("source_guideline", ""),
                            severity="STANDARD",
                            description=f"Expected action from active node {node_id}",
                            condition_met="pathway_active",
                            is_conditional=False,
                            recommendation_class=rc,
                            evidence_level=el,
                            source_guideline=sg,
                            authority_tier=tier,
                        )
                    )

        # Also add REQUIRED actions from conditional rules as expected
        for c in result.required:
            for action in c.actions:
                if action not in seen_actions:
                    seen_actions.add(action)
                    result.add(
                        DerivedConstraint(
                            constraint_type="EXPECTED",
                            actions=[action],
                            provenance=c.provenance,
                            evidence=c.evidence,
                            severity="STANDARD",
                            description="Required by conditional rule -> expected",
                            condition_met=c.condition_met,
                            is_conditional=True,
                            recommendation_class=c.recommendation_class,
                            evidence_level=c.evidence_level,
                            source_guideline=c.source_guideline,
                            authority_tier=c.authority_tier,
                        )
                    )

    def _emit_conflict_for_action(
        self,
        action: str,
        required_provenance: str,
        required_condition: str,
        forbidden_entries: list[tuple[str, str]],
        result: DerivedConstraintSet,
    ) -> None:
        """Emit one CONFLICT constraint per (required, forbidden) pair for a given action.

        Dedups against already-emitted (action, provenance) pairs in result.conflicts.
        """
        existing = {(c.actions[0], c.provenance) for c in result.conflicts if c.actions}
        for forb_provenance, forb_condition in forbidden_entries:
            combined_prov = f"{required_provenance}|{forb_provenance}"
            if (action, combined_prov) in existing:
                continue
            result.conflicts.append(
                DerivedConstraint(
                    constraint_type="CONFLICT",
                    actions=[action],
                    provenance=combined_prov,
                    evidence="REQUIRED ∩ FORBIDDEN under co-satisfiable conditions",
                    severity="CRITICAL",
                    description=(
                        f"Action '{action}' is both required ({required_condition}) "
                        f"and forbidden ({forb_condition})"
                    ),
                    condition_met=f"req={required_condition}; forb={forb_condition}",
                    is_conditional=True,
                )
            )
            existing.add((action, combined_prov))

    def _detect_required_forbidden_conflicts(self, result: DerivedConstraintSet) -> None:
        """Surface CONFLICT for actions that are simultaneously REQUIRED and FORBIDDEN.

        Iterates result.required (from conditional REQUIRED rules) against
        result.forbidden (unconditional + conditional + allergy-derived). Emits
        CRITICAL CONFLICT constraints — caller (CDE-coupled scoring path) decides
        whether to translate them into ViolationType.CONFLICT events.
        """
        forbidden_index: dict[str, list[tuple[str, str]]] = {}
        for c in result.forbidden:
            for a in c.actions:
                forbidden_index.setdefault(a, []).append((c.provenance, c.condition_met))

        for req in result.required:
            for action in req.actions:
                if action in forbidden_index:
                    self._emit_conflict_for_action(
                        action=action,
                        required_provenance=req.provenance,
                        required_condition=req.condition_met,
                        forbidden_entries=forbidden_index[action],
                        result=result,
                    )

    def _is_node_active(self, node: dict[str, Any], patient: dict[str, Any]) -> bool:
        """Determine if a node is active for the given patient.

        Uses patient_activation_condition if present, falls back to
        precondition evaluation, and defaults to True for nodes without
        conditions (entry nodes, always-active assessment nodes).
        """
        # Priority 1: explicit patient_activation_condition
        pac = node.get("patient_activation_condition")
        if pac is not None:
            return self._evaluate_condition(str(pac), patient)

        # Priority 2: precondition (may reference state.X which we can't
        # fully evaluate, so we're conservative and include the node)
        precondition = node.get("precondition")
        if precondition is None:
            return True

        # Try to evaluate; if it references "state." we can't resolve it
        # from patient context alone, so default to True
        precond_str = str(precondition)
        if "state." in precond_str:
            return True

        return self._evaluate_condition(precond_str, patient)

    # Patterns blocked in condition strings to prevent code injection.
    _BLOCKED_PATTERNS = re.compile(
        r"__|lambda|import|exec|eval|compile|open\s*\(|globals|locals|getattr|setattr|delattr|vars\s*\(|dir\s*\(|type\s*\(|__class__|__mro__|__subclasses__|__bases__|__builtins__",
        re.IGNORECASE,
    )

    _MAX_CONDITION_LENGTH = 500

    def _evaluate_condition(self, condition: str, patient: dict[str, Any]) -> bool:
        """Safe evaluation of condition string against patient context.

        Supported patterns:
        - "patient.labs.potassium < 3.3"
        - "'cocaine_use' in patient.comorbidities"
        - "patient.age < 18"
        - compound: "X and Y", "X or Y"
        """
        if len(condition) > self._MAX_CONDITION_LENGTH:
            return False

        if self._BLOCKED_PATTERNS.search(condition):
            return False

        _SAFE_BUILTINS: dict[str, Any] = {
            "__builtins__": {
                "str": str,
                "len": len,
                "int": int,
                "float": float,
                "bool": bool,
                "True": True,
                "False": False,
                "None": None,
                "abs": abs,
                "min": min,
                "max": max,
                "any": any,
                "all": all,
            }
        }
        namespace: dict[str, Any] = {"patient": DotDict(patient)}
        try:
            return bool(
                eval(condition, _SAFE_BUILTINS, namespace)  # noqa: S307
            )
        except (KeyError, AttributeError, TypeError, NameError, SyntaxError):
            return False

    def _format_condition_met(self, condition: str, patient: dict[str, Any]) -> str:
        """Format condition evaluation for human readability.

        Example: "patient.labs.potassium < 3.3"
                 -> "patient.labs.potassium=2.9 < 3.3"
        """
        # Find variable references like patient.xxx.yyy
        var_pattern = re.compile(r"patient(?:\.\w+)+")
        matches = var_pattern.findall(condition)

        result = condition
        for match in matches:
            path = match.replace("patient.", "").split(".")
            val = patient
            try:
                for key in path:
                    val = val[key]  # type: ignore[index]
                result = result.replace(match, f"{match}={val}", 1)
            except (KeyError, TypeError, IndexError):
                pass

        return result

    def _load_allergy_drug_map(self) -> dict[str, list[str]]:
        """Load allergy -> contraindicated drug mapping from YAML."""
        if _ALLERGY_DRUG_MAP_PATH.exists():
            with open(_ALLERGY_DRUG_MAP_PATH) as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                return {k: v for k, v in data.items() if isinstance(v, list)}

        # Fallback built-in mapping
        return {
            "penicillin": [
                "penicillin",
                "amoxicillin",
                "ampicillin",
            ],
            "penicillin_anaphylaxis": [
                "penicillin",
                "amoxicillin",
                "ampicillin",
                "cephalosporin",
                "ceftriaxone",
                "cefepime",
                "cefazolin",
                "ceftazidime",
                "piperacillin_tazobactam",
            ],
            "aspirin": ["aspirin"],
            "nsaids": [
                "ibuprofen",
                "naproxen",
                "ketorolac",
                "celecoxib",
            ],
            "sulfa": [
                "trimethoprim_sulfamethoxazole",
                "sulfasalazine",
            ],
            "ace_inhibitor_angioedema": [
                "enalapril",
                "lisinopril",
                "ramipril",
                "captopril",
            ],
            "heparin_hit": ["heparin", "enoxaparin"],
            "vancomycin_red_man_syndrome": [
                "vancomycin_rapid_infusion",
            ],
            "latex": ["latex_gloves", "latex_equipment"],
            "contrast_dye": [
                "iodinated_contrast",
                "gadolinium",
            ],
            "morphine": ["morphine", "codeine"],
            "fluoroquinolone": [
                "ciprofloxacin",
                "levofloxacin",
                "moxifloxacin",
            ],
        }


def load_graph(graph_path: str | Path) -> dict[str, Any]:
    """Load a CPG graph YAML file."""
    with open(graph_path) as f:
        return yaml.safe_load(f)  # type: ignore[no-any-return]
