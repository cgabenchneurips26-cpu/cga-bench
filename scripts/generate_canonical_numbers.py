#!/usr/bin/env python3
"""Generate canonical_numbers.json — single source of truth for all paper numbers.

Every number has provenance: which file/computation produced it.
This prevents stale claims and ensures paper-numbers consistency.

Outputs:
  evidence_pack/canonical_numbers.json

Usage:
    PYTHONPATH=. python scripts/generate_canonical_numbers.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.experiments._common import (
    AUTO_SCENARIOS_FILE,
    EVIDENCE_DIR,
    GRAPHS_DIR,
    HELD_OUT_GRAPH_IDS,
    load_all_scenarios,
    save_json,
)

ANALYSIS_DIR = EVIDENCE_DIR / "analysis"
OUTPUT_PATH = EVIDENCE_DIR / "canonical_numbers.json"


# ---------------------------------------------------------------------------
# Counting helpers
# ---------------------------------------------------------------------------


def count_graphs() -> dict[str, Any]:
    """Count CPG graph files and classify as core vs held-out."""
    all_graphs: list[str] = []
    held_out: list[str] = []
    core: list[str] = []

    for gp in sorted(GRAPHS_DIR.glob("*.yaml")):
        try:
            with open(gp) as f:
                data = yaml.safe_load(f)
            gid = data.get("graph_id", gp.stem)
        except (OSError, yaml.YAMLError):
            gid = gp.stem

        all_graphs.append(gid)
        if gid in HELD_OUT_GRAPH_IDS:
            held_out.append(gid)
        else:
            core.append(gid)

    return {
        "total": len(all_graphs),
        "core": len(core),
        "held_out": len(held_out),
        "held_out_ids": held_out,
        "provenance": f"glob({GRAPHS_DIR}/*.yaml)",
    }


def count_conditional_rules() -> dict[str, Any]:
    """Count conditional rules across all graphs."""
    total = 0
    per_graph: dict[str, int] = {}

    for gp in sorted(GRAPHS_DIR.glob("*.yaml")):
        try:
            with open(gp) as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError):
            continue

        gid = data.get("graph_id", gp.stem)
        rules = []
        nodes = data.get("nodes", {})
        if isinstance(nodes, dict):
            nodes = nodes.values()
        for node in nodes:
            if isinstance(node, dict):
                rules.extend(node.get("conditional_rules", []))
        per_graph[gid] = len(rules)
        total += len(rules)

    return {
        "total": total,
        "per_graph": per_graph,
        "provenance": "cpg_model/graphs/*.yaml → nodes[].conditional_rules[]",
    }


def count_scenarios() -> dict[str, Any]:
    """Count scenarios from YAML files."""
    scenarios = load_all_scenarios(tag_source=True)
    manual = [s for s in scenarios if s.get("source_type") == "manual"]
    auto = [s for s in scenarios if s.get("source_type") == "auto"]

    return {
        "total": len(scenarios),
        "manual": len(manual),
        "auto": len(auto),
        "provenance": f"configs/scenarios/*.yaml (manual) + {AUTO_SCENARIOS_FILE.name} (auto)",
    }


def count_constraints_from_audit() -> dict[str, Any] | None:
    """Load constraint counts from v3_constraint_audit.json if available."""
    audit_path = ANALYSIS_DIR / "v3_constraint_audit.json"
    if not audit_path.exists():
        return None

    with open(audit_path) as f:
        data = json.load(f)

    census = data.get("constraint_census", {}).get("totals", {})
    return {
        "hard_total": census.get("hard_total", 0),
        "soft_total": census.get("soft_total", 0),
        "total": census.get("hard_total", 0) + census.get("soft_total", 0),
        "forbidden": census.get("FORBIDDEN", census.get("forbidden", 0)),
        "within": census.get("WITHIN", census.get("within", 0)),
        "before": census.get("BEFORE", census.get("before", 0)),
        "must": census.get("MUST", census.get("must", 0)),
        "n_nodes": census.get("n_nodes", 0),
        "provenance": "evidence_pack/analysis/v3_constraint_audit.json → constraint_census.totals",
    }


def load_evaluator_agreement() -> dict[str, Any] | None:
    """Load evaluator agreement metrics."""
    path = ANALYSIS_DIR / "evaluator_agreement.json"
    if not path.exists():
        return None

    with open(path) as f:
        data = json.load(f)

    return {
        "fleiss_kappa_all6": data.get("fleiss_kappa", 0),
        "fleiss_kappa_4ind": data.get("fleiss_kappa_4independent", 0),
        "n_evaluators": data.get("n_evaluators", 0),
        "n_episodes": data.get("n_episodes", 0),
        "provenance": "evidence_pack/analysis/evaluator_agreement.json",
    }


def load_kappa_debug() -> dict[str, Any] | None:
    """Load corrected kappa from debug analysis."""
    path = ANALYSIS_DIR / "kappa_precision_debug.json"
    if not path.exists():
        return None

    with open(path) as f:
        data = json.load(f)

    issue1 = data.get("issue_1_kappa", {})
    return {
        "fleiss_kappa_all6": issue1.get("fleiss_kappa_all_6", 0),
        "fleiss_kappa_4ind": issue1.get("fleiss_kappa_4_independent", 0),
        "degenerate_evaluators": issue1.get("diagnosis", {}).get("degenerate_evaluators", []),
        "redundant_pairs": issue1.get("diagnosis", {}).get("redundant_pairs", []),
        "provenance": "evidence_pack/analysis/kappa_precision_debug.json → issue_1",
    }


def load_stratified_precision() -> dict[str, Any] | None:
    """Load constraint-type stratified precision."""
    path = ANALYSIS_DIR / "constraint_type_precision.json"
    if not path.exists():
        return None

    with open(path) as f:
        data = json.load(f)

    ct = data.get("cross_type", {})
    fvf = ct.get("forbidden_vs_forbidden", {})
    nvf = ct.get("nonforbidden_vs_expected", {})

    f_total_engine = fvf.get("tp", 0) + fvf.get("fp", 0)
    f_total_manual = fvf.get("tp", 0) + fvf.get("fn", 0)
    nf_total_engine = nvf.get("tp", 0) + nvf.get("fp", 0)
    nf_total_manual = nvf.get("tp", 0) + nvf.get("fn", 0)

    return {
        "n_evaluated": data.get("n_evaluated", 0),
        "overall_engine_actions": f_total_engine + nf_total_engine,
        "overall_manual_actions": f_total_manual + nf_total_manual,
        "forbidden_precision": fvf.get("precision", 0),
        "forbidden_recall": fvf.get("recall", 0),
        "forbidden_expansion": round(f_total_engine / max(f_total_manual, 1), 1),
        "nonforbidden_precision": nvf.get("precision", 0),
        "nonforbidden_recall": nvf.get("recall", 0),
        "nonforbidden_expansion": round(nf_total_engine / max(nf_total_manual, 1), 1),
        "provenance": "evidence_pack/analysis/constraint_type_precision.json → cross_type",
    }


def load_violation_crosstab() -> dict[str, Any] | None:
    """Load evaluator violation sensitivity crosstab."""
    path = ANALYSIS_DIR / "evaluator_violation_crosstab.json"
    if not path.exists():
        return None

    with open(path) as f:
        data = json.load(f)

    miscert = data.get("miscertification", {})
    summary: dict[str, Any] = {}
    for eval_label in ["AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]:
        mc = miscert.get(eval_label, {})
        summary[eval_label] = {
            "miscert_rate": mc.get("miscert_rate", 0),
            "n_miscertified": mc.get("n_miscertified", 0),
        }

    return {
        "n_episodes": data.get("n_episodes", 0),
        "violation_types": data.get("violation_types_observed", []),
        "miscertification": summary,
        "provenance": "evidence_pack/analysis/evaluator_violation_crosstab.json",
    }


def load_verdict_matrix() -> dict[str, Any] | None:
    """Load verdict matrix episode count."""
    path = ANALYSIS_DIR / "verdict_matrix_v6.json"
    if not path.exists():
        return None

    with open(path) as f:
        data = json.load(f)

    episodes = data.get("per_episode", [])
    models = set()
    scenarios = set()
    for ep in episodes:
        models.add(ep.get("model", ""))
        scenarios.add(ep.get("scenario_id", ""))

    return {
        "n_episodes": len(episodes),
        "n_models": len(models),
        "n_scenarios": len(scenarios),
        "models": sorted(models),
        "provenance": "evidence_pack/analysis/verdict_matrix_v6.json → per_episode",
    }


def load_exp_results() -> dict[str, Any]:
    """Load key experiment results (EXP-A through EXP-E)."""
    results: dict[str, Any] = {}

    # EXP-E: difficulty equivalence
    exp_e_path = ANALYSIS_DIR / "exp_e_difficulty_equivalence.json"
    if exp_e_path.exists():
        with open(exp_e_path) as f:
            data = json.load(f)
        results["exp_e_cohens_d"] = {
            "value": data.get("cohens_d", 0),
            "provenance": "evidence_pack/analysis/exp_e_difficulty_equivalence.json",
        }

    # EXP-C: generalizability
    exp_c_path = ANALYSIS_DIR / "exp_c_generalizability.json"
    if exp_c_path.exists():
        with open(exp_c_path) as f:
            data = json.load(f)
        results["exp_c_parse_failures"] = {
            "value": data.get("parse_failures", 0),
            "n_held_out": data.get("n_held_out", 0),
            "provenance": "evidence_pack/analysis/exp_c_generalizability.json",
        }

    # EXP-B: overgeneration
    exp_b_path = ANALYSIS_DIR / "exp_b_derivation_ablation.json"
    if exp_b_path.exists():
        with open(exp_b_path) as f:
            data = json.load(f)
        results["exp_b_overgeneration"] = {
            "value": data.get("unconditional_overgeneration_pct", 0),
            "provenance": "evidence_pack/analysis/exp_b_derivation_ablation.json",
        }

    return results


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Build canonical_numbers.json."""
    print("Generating canonical_numbers.json")
    print("=" * 60)

    numbers: dict[str, Any] = {}

    # 1. Graphs
    graphs = count_graphs()
    numbers["graphs"] = graphs
    print(f"Graphs: {graphs['total']} total ({graphs['core']} core, {graphs['held_out']} held-out)")

    # 2. Conditional rules
    rules = count_conditional_rules()
    numbers["conditional_rules"] = rules
    print(f"Conditional rules: {rules['total']} across {len(rules['per_graph'])} graphs")

    # 3. Scenarios
    scenarios = count_scenarios()
    numbers["scenarios"] = scenarios
    print(f"Scenarios: {scenarios['total']} ({scenarios['manual']} manual, {scenarios['auto']} auto)")

    # 4. Constraints (from audit)
    constraints = count_constraints_from_audit()
    if constraints:
        numbers["constraints"] = constraints
        print(
            f"Constraints: {constraints['total']} (hard={constraints['hard_total']}, soft={constraints['soft_total']})"
        )
    else:
        print("Constraints: SKIP (v3_constraint_audit.json not found)")

    # 5. Evaluator agreement (corrected)
    kappa = load_kappa_debug()
    if kappa:
        numbers["evaluator_agreement"] = kappa
        print(f"Fleiss' kappa (4 ind): {kappa['fleiss_kappa_4ind']}")
    else:
        agreement = load_evaluator_agreement()
        if agreement:
            numbers["evaluator_agreement"] = agreement
            print(f"Fleiss' kappa: {agreement.get('fleiss_kappa_all6', '?')}")

    # 6. Stratified precision
    precision = load_stratified_precision()
    if precision:
        numbers["stratified_precision"] = precision
        print(
            f"Stratified precision: FORBIDDEN P={precision['forbidden_precision']}, "
            f"expansion={precision['forbidden_expansion']}x"
        )

    # 7. Violation crosstab
    crosstab = load_violation_crosstab()
    if crosstab:
        numbers["violation_crosstab"] = crosstab
        print(f"Violation crosstab: {crosstab['n_episodes']} episodes, types={crosstab['violation_types']}")

    # 8. Verdict matrix
    verdict = load_verdict_matrix()
    if verdict:
        numbers["verdict_matrix"] = verdict
        print(f"Verdict matrix: {verdict['n_episodes']} episodes, {verdict['n_models']} models")

    # 9. Experiment results
    exp = load_exp_results()
    if exp:
        numbers["experiments"] = exp
        for k, v in exp.items():
            print(f"  {k}: {v.get('value', '?')}")

    # Save
    save_json(numbers, OUTPUT_PATH)
    print(f"\nCanonical numbers saved to: {OUTPUT_PATH}")
    print(f"Total sections: {len(numbers)}")


if __name__ == "__main__":
    main()
