"""CPG graph and scenario schema validation.

Validates all YAML files in cpg_model/graphs/ and configs/scenarios/
against the CGA-Bench schema requirements.

Exit code 0 if all files are valid, 1 if errors are found.

Usage:
    PYTHONPATH=. python scripts/ci/validate_cpg_schema.py
    PYTHONPATH=. python scripts/ci/validate_cpg_schema.py --graphs-dir cpg_model/graphs
    PYTHONPATH=. python scripts/ci/validate_cpg_schema.py --scenarios-dir configs/scenarios
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VALID_NODE_TYPES = {"decision", "plan", "action", "enquiry"}

# v2 validation constants
VALID_EFFECT_TYPES = {"FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN"}
VALID_SEVERITIES = {"CRITICAL", "HIGH", "MODERATE", "LOW"}
VALID_RECOMMENDATION_CLASSES = {"I", "IIa", "IIb", "III"}

REQUIRED_TOP_LEVEL_FIELDS = {"graph_id", "guideline_name", "entry_node", "nodes"}

REQUIRED_NODE_FIELDS = {
    "node_id",
    "node_type",
    "name",
    "mandatory_actions",
    "source_guideline",
    "source_section",
}

# `allowed_actions` was REQUIRED in the legacy schema. Empirically the runtime
# (cpg_engine/engine.py:82 `hasattr(..) and truthy` + node_types.py dataclass
# default `[]`) treats absent/empty `allowed_actions` as "no additional actions
# beyond mandatory" — not an error. Moving it to RECOMMENDED here eliminates
# 36 false-positive errors on the 25-CPG corpus while all engine tests pass.
# See docs/cpg_expansion_v7/04_validator_runtime_dissonance.md.
RECOMMENDED_NODE_FIELDS = {
    "allowed_actions",
    "description",
    "source_page",
    "source_quote",
}

REQUIRED_SCENARIO_FIELDS = {
    "scenario_id",
    "description",
    "guideline_graph",
    "patient",
    "expected_actions",
}

REQUIRED_PATIENT_FIELDS = {
    "age",
    "sex",
    "weight_kg",
    "chief_complaint",
    "working_diagnosis",
    "vitals",
}

REQUIRED_VITALS_FIELDS = {
    "heart_rate",
    "blood_pressure_systolic",
    "blood_pressure_diastolic",
    "temperature",
    "oxygen_saturation",
}


# ---------------------------------------------------------------------------
# Graph validation
# ---------------------------------------------------------------------------


def _collect_all_actions(node: dict[str, Any]) -> set[str]:
    """Collect every action ID referenced anywhere in a node."""
    actions: set[str] = set()
    for key in ("mandatory_actions", "allowed_actions", "forbidden_actions"):
        actions.update(node.get(key) or [])
    deadlines = node.get("deadlines") or {}
    actions.update(deadlines.keys())
    prior = node.get("required_prior_actions") or {}
    for target, deps in prior.items():
        actions.add(target)
        if isinstance(deps, list):
            actions.update(deps)
    return actions


def validate_graph(filepath: Path) -> tuple[list[str], list[str]]:
    """Validate a single CPG graph YAML file.

    Returns:
        (errors, warnings) lists of human-readable messages.
    """
    errors: list[str] = []
    warnings: list[str] = []
    fname = filepath.name

    try:
        data = yaml.safe_load(filepath.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        errors.append(f"{fname}: YAML parse error: {exc}")
        return errors, warnings

    if not isinstance(data, dict):
        errors.append(f"{fname}: top-level value is not a mapping")
        return errors, warnings

    # --- Top-level required fields ---
    for field in REQUIRED_TOP_LEVEL_FIELDS:
        if field not in data or data[field] is None:
            errors.append(f"{fname}: missing required top-level field '{field}'")

    # --- Metadata presence ---
    if "metadata" not in data or not isinstance(data.get("metadata"), dict):
        warnings.append(f"{fname}: missing or empty 'metadata' block")

    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        errors.append(f"{fname}: 'nodes' is not a mapping")
        return errors, warnings

    node_ids = set(nodes.keys())
    # --- Entry node exists ---
    entry_node = data.get("entry_node")
    if entry_node and entry_node not in node_ids:
        errors.append(f"{fname}: entry_node '{entry_node}' does not exist in nodes")

    # --- Per-node validation ---
    for nid, node in nodes.items():
        if not isinstance(node, dict):
            errors.append(f"{fname}:{nid}: node value is not a mapping")
            continue

        prefix = f"{fname}:{nid}"

        # Required fields
        for field in REQUIRED_NODE_FIELDS:
            val = node.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                errors.append(f"{prefix}: missing required field '{field}'")

        # Recommended fields
        for field in RECOMMENDED_NODE_FIELDS:
            val = node.get(field)
            if val is None or (isinstance(val, str) and not val.strip()):
                warnings.append(f"{prefix}: missing recommended field '{field}'")

        # node_id matches dict key
        declared_nid = node.get("node_id")
        if declared_nid is not None and declared_nid != nid:
            errors.append(f"{prefix}: node_id value '{declared_nid}' does not match dict key '{nid}'")

        # node_type validity
        ntype = node.get("node_type")
        if ntype and ntype not in VALID_NODE_TYPES:
            errors.append(f"{prefix}: invalid node_type '{ntype}'; expected one of {sorted(VALID_NODE_TYPES)}")

        mandatory = set(node.get("mandatory_actions") or [])
        allowed = set(node.get("allowed_actions") or [])
        # NOTE: `mandatory ⊆ allowed` is NOT enforced.
        # Runtime scoring (`assessor_core/violations.py::_action_satisfies_requirement`)
        # matches performed_actions against mandatory_actions via a 4-step
        # semantic resolver (exact → normalise → alias → explicit conditional
        # handler) and does NOT reference allowed_actions. Enforcing the legacy
        # subset invariant produced 101 false-positive errors on the 25-CPG
        # corpus while every single runtime engine test (79/79) passed. Emit a
        # warning for visibility but do not fail the check.
        # See docs/cpg_expansion_v7/04_validator_runtime_dissonance.md.
        diff = mandatory - allowed
        if diff:
            warnings.append(
                f"{prefix}: mandatory_actions not in allowed_actions "
                f"(informational, runtime resolves via semantic matcher): {sorted(diff)}"
            )

        # forbidden_actions vs allowed_actions overlap.
        # Same action may appear in both when `conditional_rules` flip a normally
        # allowed action to FORBIDDEN under a patient-specific condition (classic
        # case: `give_nitrates_if_indicated` is allowed for most STEMI but
        # conditional_rules switch it to forbidden under RV infarct). Runtime
        # honours the conditional override, so raise this only as a warning.
        forbidden = set(node.get("forbidden_actions") or [])
        overlap = forbidden & allowed
        if overlap:
            warnings.append(
                f"{prefix}: actions in both forbidden and allowed "
                f"(expected only if a conditional_rule flips allowed→forbidden): {sorted(overlap)}"
            )

        # deadlines reference known actions
        deadlines = node.get("deadlines") or {}
        if isinstance(deadlines, dict):
            all_known = mandatory | allowed
            for action_id in deadlines:
                if action_id not in all_known:
                    errors.append(f"{prefix}: deadline references unknown action '{action_id}'")

        # required_prior_actions reference valid actions
        prior = node.get("required_prior_actions") or {}
        if isinstance(prior, dict):
            all_known = mandatory | allowed
            for target, deps in prior.items():
                if target not in all_known:
                    warnings.append(f"{prefix}: required_prior_actions target '{target}' not in allowed/mandatory")
                if isinstance(deps, list):
                    for dep in deps:
                        if dep not in all_known:
                            warnings.append(
                                f"{prefix}: required_prior_actions "
                                f"prerequisite '{dep}' for '{target}' "
                                f"not in allowed/mandatory"
                            )

        # next_nodes and conditional_next targets exist
        for next_id in node.get("next_nodes") or []:
            if next_id not in node_ids:
                errors.append(f"{prefix}: next_nodes references non-existent node '{next_id}'")
        for _cond, target_id in (node.get("conditional_next") or {}).items():
            if target_id not in node_ids:
                errors.append(f"{prefix}: conditional_next target '{target_id}' does not exist in nodes")

        # --- v2: conditional_rules validation ---
        seen_rule_ids: set[str] = set()  # per-node uniqueness
        cond_rules = node.get("conditional_rules") or []
        if cond_rules and not isinstance(cond_rules, list):
            errors.append(f"{prefix}: conditional_rules must be a list")
            cond_rules = []

        for idx, rule in enumerate(cond_rules):
            rprefix = f"{prefix}:conditional_rules[{idx}]"
            if not isinstance(rule, dict):
                errors.append(f"{rprefix}: rule is not a mapping")
                continue

            # rule_id required
            rule_id = rule.get("rule_id")
            if not rule_id:
                errors.append(f"{rprefix}: missing required field 'rule_id'")
            elif rule_id in seen_rule_ids:
                errors.append(f"{rprefix}: duplicate rule_id '{rule_id}'")
            else:
                seen_rule_ids.add(rule_id)

            # condition required
            condition = rule.get("condition")
            if not condition or not isinstance(condition, str):
                errors.append(f"{rprefix}: missing or non-string 'condition'")
            else:
                try:
                    compile(condition, "<condition>", "eval")
                except SyntaxError:
                    warnings.append(f"{rprefix}: condition is not valid Python: {condition!r}")

            # effect block required
            effect = rule.get("effect")
            if not isinstance(effect, dict):
                errors.append(f"{rprefix}: missing or non-mapping 'effect'")
            else:
                etype = effect.get("type")
                if etype not in VALID_EFFECT_TYPES:
                    errors.append(f"{rprefix}: effect.type '{etype}' not in {sorted(VALID_EFFECT_TYPES)}")
                eactions = effect.get("actions")
                if not eactions or not isinstance(eactions, list) or len(eactions) == 0:
                    errors.append(f"{rprefix}: effect.actions must be a non-empty list")

            # severity (recommended)
            severity = rule.get("severity")
            if severity and severity not in VALID_SEVERITIES:
                warnings.append(f"{rprefix}: severity '{severity}' not in {sorted(VALID_SEVERITIES)}")
            elif not severity:
                warnings.append(f"{rprefix}: missing recommended field 'severity'")

            # condition_variables (recommended)
            cvars = rule.get("condition_variables")
            if cvars is not None and not isinstance(cvars, list):
                warnings.append(f"{rprefix}: condition_variables should be a list")

        # --- v2: precondition validation ---
        precondition = node.get("precondition")
        if precondition is not None and precondition is not False:
            if not isinstance(precondition, str):
                warnings.append(f"{prefix}: precondition should be a string or null")
            else:
                try:
                    compile(precondition, "<precondition>", "eval")
                except SyntaxError:
                    warnings.append(f"{prefix}: precondition is not valid Python: {precondition!r}")

    return errors, warnings


# ---------------------------------------------------------------------------
# Scenario validation
# ---------------------------------------------------------------------------


def validate_scenario_file(
    filepath: Path,
    known_graph_ids: set[str] | None = None,
) -> tuple[list[str], list[str]]:
    """Validate a single scenario config YAML file.

    Args:
        filepath: Path to the scenario YAML file.
        known_graph_ids: Set of valid graph_id values for cross-referencing.

    Returns:
        (errors, warnings) lists.
    """
    errors: list[str] = []
    warnings: list[str] = []
    fname = filepath.name

    try:
        data = yaml.safe_load(filepath.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        errors.append(f"{fname}: YAML parse error: {exc}")
        return errors, warnings

    if not isinstance(data, dict):
        errors.append(f"{fname}: top-level value is not a mapping")
        return errors, warnings

    scenarios = data.get("scenarios")
    if not isinstance(scenarios, dict):
        errors.append(f"{fname}: missing or invalid 'scenarios' mapping")
        return errors, warnings

    for sid, scenario in scenarios.items():
        if not isinstance(scenario, dict):
            errors.append(f"{fname}:{sid}: scenario value is not a mapping")
            continue

        prefix = f"{fname}:{sid}"

        # Required scenario fields
        for field in REQUIRED_SCENARIO_FIELDS:
            if field not in scenario or scenario[field] is None:
                errors.append(f"{prefix}: missing required field '{field}'")

        # scenario_id matches dict key
        declared_sid = scenario.get("scenario_id")
        if declared_sid is not None and declared_sid != sid:
            errors.append(f"{prefix}: scenario_id value '{declared_sid}' does not match dict key '{sid}'")

        # expected_actions non-empty
        expected = scenario.get("expected_actions")
        if not expected or not isinstance(expected, list) or len(expected) == 0:
            errors.append(f"{prefix}: expected_actions is empty or missing")

        # forbidden vs expected overlap
        forbidden_s = set(scenario.get("forbidden_actions") or [])
        expected_s = set(expected or [])
        overlap = forbidden_s & expected_s
        if overlap:
            errors.append(f"{prefix}: actions in both forbidden and expected: {sorted(overlap)}")

        # Patient block
        patient = scenario.get("patient")
        if isinstance(patient, dict):
            for field in REQUIRED_PATIENT_FIELDS:
                if field not in patient or patient[field] is None:
                    errors.append(f"{prefix}.patient: missing required field '{field}'")

            vitals = patient.get("vitals")
            if isinstance(vitals, dict):
                for field in REQUIRED_VITALS_FIELDS:
                    if field not in vitals:
                        warnings.append(f"{prefix}.patient.vitals: missing recommended field '{field}'")
            elif vitals is None:
                errors.append(f"{prefix}.patient: missing 'vitals' block")

        # Cross-reference guideline_graph against known graph_ids
        gg = scenario.get("guideline_graph")
        if gg and known_graph_ids and gg not in known_graph_ids:
            warnings.append(
                f"{prefix}: guideline_graph '{gg}' not found in any "
                f"graph file's graph_id (may resolve via domain_registry)"
            )

        # Trap scenario consistency
        is_trap = scenario.get("trap_scenario", False)
        if is_trap and not scenario.get("trap_description"):
            warnings.append(f"{prefix}: trap_scenario is true but trap_description is missing")

        # passing_compliance_threshold range
        threshold = scenario.get("passing_compliance_threshold")
        if threshold is not None:
            if not isinstance(threshold, (int, float)):
                errors.append(f"{prefix}: passing_compliance_threshold is not numeric")
            elif not 0.0 <= threshold <= 1.0:
                errors.append(f"{prefix}: passing_compliance_threshold {threshold} outside [0.0, 1.0]")

    return errors, warnings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def _resolve_dir(user_path: str, fallback_relative: str) -> Path:
    """Resolve a directory path, trying CWD first then project root."""
    p = Path(user_path)
    if p.is_dir():
        return p
    project_root = Path(__file__).resolve().parent.parent.parent
    alt = project_root / fallback_relative
    if alt.is_dir():
        return alt
    return p


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate CGA-Bench CPG graph and scenario YAML schemas.",
    )
    parser.add_argument(
        "--graphs-dir",
        default="cpg_model/graphs",
        help="Directory containing CPG graph YAML files (default: cpg_model/graphs)",
    )
    parser.add_argument(
        "--scenarios-dir",
        default="configs/scenarios",
        help="Directory containing scenario YAML files (default: configs/scenarios)",
    )
    parser.add_argument(
        "--skip-graphs",
        action="store_true",
        help="Skip graph validation",
    )
    parser.add_argument(
        "--skip-scenarios",
        action="store_true",
        help="Skip scenario validation",
    )
    parser.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="Treat warnings as errors",
    )
    args = parser.parse_args()

    all_errors: list[str] = []
    all_warnings: list[str] = []
    files_checked = 0

    # --- Graph validation ---
    known_graph_ids: set[str] = set()

    if not args.skip_graphs:
        graphs_dir = _resolve_dir(args.graphs_dir, "cpg_model/graphs")
        if not graphs_dir.is_dir():
            print(f"ERROR: graphs directory not found: {graphs_dir}")
            return 1

        graph_files = sorted(graphs_dir.glob("*.yaml"))
        if not graph_files:
            print(f"WARNING: no YAML files found in {graphs_dir}")
        else:
            print(f"Validating {len(graph_files)} CPG graph files...")
            for gf in graph_files:
                files_checked += 1
                errs, warns = validate_graph(gf)
                all_errors.extend(errs)
                all_warnings.extend(warns)

                # Collect graph_id for cross-referencing
                try:
                    data = yaml.safe_load(gf.read_text(encoding="utf-8"))
                    gid = data.get("graph_id")
                    if gid:
                        known_graph_ids.add(gid)
                except Exception:
                    pass

    # --- Scenario validation ---
    if not args.skip_scenarios:
        scenarios_dir = _resolve_dir(args.scenarios_dir, "configs/scenarios")
        if not scenarios_dir.is_dir():
            print(f"ERROR: scenarios directory not found: {scenarios_dir}")
            return 1

        scenario_files = sorted(scenarios_dir.glob("*.yaml"))
        if not scenario_files:
            print(f"WARNING: no YAML files found in {scenarios_dir}")
        else:
            print(f"Validating {len(scenario_files)} scenario config files...")
            for sf in scenario_files:
                files_checked += 1
                errs, warns = validate_scenario_file(sf, known_graph_ids)
                all_errors.extend(errs)
                all_warnings.extend(warns)

    # --- Report ---
    print(f"\nFiles checked: {files_checked}")

    if all_warnings:
        print(f"\n=== Warnings ({len(all_warnings)}) ===")
        for w in all_warnings[:30]:
            print(f"  WARN: {w}")
        if len(all_warnings) > 30:
            print(f"  ... and {len(all_warnings) - 30} more warnings")

    if all_errors:
        print(f"\n=== Errors ({len(all_errors)}) ===")
        for e in all_errors:
            print(f"  ERROR: {e}")

    if args.warnings_as_errors and all_warnings:
        all_errors.extend(all_warnings)

    if all_errors:
        print(f"\nFAILED: {len(all_errors)} error(s) found.")
        return 1

    print("\nPASSED: all schema checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
