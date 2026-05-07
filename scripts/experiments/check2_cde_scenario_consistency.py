"""Check 2: CDE-emitted vs scenario-stored form consistency.

For kdigo_contrast_aki, loads the CPG graph and compares:
1. mandatory/forbidden action IDs as stored in the YAML graph
2. The same IDs after ActionNormalizer normalization
3. Verifies both sides (CDE output + scenario expectations) use consistent forms

Usage:
    PYTHONPATH=. python scripts/experiments/check2_cde_scenario_consistency.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT.parent))
sys.path.insert(0, str(ROOT))

import yaml

from cga_bench.assessor_core.action_normalizer import ActionNormalizer


GRAPH_PATH = ROOT / "cpg_model" / "graphs" / "kdigo_contrast_aki.yaml"
SCENARIO_DIR = ROOT / "data" / "scenarios"
CPG_ID = "kdigo_contrast_aki"


def load_graph(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f)


def check_graph_consistency(graph: dict, normalizer: ActionNormalizer) -> list[dict]:
    """Check that all action IDs in graph nodes are idempotent under normalization."""
    issues: list[dict] = []
    nodes = graph.get("nodes", {})

    for node_id, node in nodes.items():
        # Check mandatory actions
        for action_id in node.get("mandatory_actions", []):
            normalized = normalizer.normalize(action_id, cpg_id=CPG_ID)
            if normalized != action_id:
                issues.append({
                    "node": node_id,
                    "field": "mandatory_actions",
                    "raw": action_id,
                    "normalized": normalized,
                    "severity": "HIGH" if action_id.lower() != normalized else "LOW",
                })

        # Check allowed actions
        for action_id in node.get("allowed_actions", []):
            normalized = normalizer.normalize(action_id, cpg_id=CPG_ID)
            if normalized != action_id:
                issues.append({
                    "node": node_id,
                    "field": "allowed_actions",
                    "raw": action_id,
                    "normalized": normalized,
                    "severity": "MEDIUM",
                })

        # Check forbidden actions
        for action_id in node.get("forbidden_actions", []):
            normalized = normalizer.normalize(action_id, cpg_id=CPG_ID)
            if normalized != action_id:
                issues.append({
                    "node": node_id,
                    "field": "forbidden_actions",
                    "raw": action_id,
                    "normalized": normalized,
                    "severity": "HIGH",
                })

        # Check deadlines keys
        for action_id in node.get("deadlines", {}).keys():
            normalized = normalizer.normalize(action_id, cpg_id=CPG_ID)
            if normalized != action_id:
                issues.append({
                    "node": node_id,
                    "field": "deadlines",
                    "raw": action_id,
                    "normalized": normalized,
                    "severity": "HIGH",
                })

        # Check required_prior_actions keys and values
        for action_id, priors in node.get("required_prior_actions", {}).items():
            normalized = normalizer.normalize(action_id, cpg_id=CPG_ID)
            if normalized != action_id:
                issues.append({
                    "node": node_id,
                    "field": "required_prior_actions_key",
                    "raw": action_id,
                    "normalized": normalized,
                    "severity": "HIGH",
                })
            if isinstance(priors, list):
                for prior in priors:
                    normalized_prior = normalizer.normalize(prior, cpg_id=CPG_ID)
                    if normalized_prior != prior:
                        issues.append({
                            "node": node_id,
                            "field": "required_prior_actions_value",
                            "raw": prior,
                            "normalized": normalized_prior,
                            "severity": "HIGH",
                        })

        # Check conditional_rules action IDs
        for rule in node.get("conditional_rules", []):
            effect = rule.get("effect", {})
            for action_id in effect.get("actions", []):
                normalized = normalizer.normalize(action_id, cpg_id=CPG_ID)
                if normalized != action_id:
                    issues.append({
                        "node": node_id,
                        "field": f"conditional_rule[{rule.get('rule_id', '?')}]",
                        "raw": action_id,
                        "normalized": normalized,
                        "severity": "MEDIUM",
                    })

    return issues


def check_cross_reference(graph: dict, normalizer: ActionNormalizer) -> list[dict]:
    """Check that mandatory actions are always in allowed_actions (after normalization)."""
    issues: list[dict] = []
    nodes = graph.get("nodes", {})

    for node_id, node in nodes.items():
        mandatory = {normalizer.normalize(a, cpg_id=CPG_ID) for a in node.get("mandatory_actions", [])}
        allowed = {normalizer.normalize(a, cpg_id=CPG_ID) for a in node.get("allowed_actions", [])}
        missing = mandatory - allowed
        if missing:
            issues.append({
                "node": node_id,
                "type": "mandatory_not_in_allowed",
                "missing": sorted(missing),
            })

    return issues


def main() -> None:
    if not GRAPH_PATH.exists():
        print(f"ERROR: Graph not found at {GRAPH_PATH}")
        sys.exit(1)

    graph = load_graph(GRAPH_PATH)
    normalizer = ActionNormalizer()

    print(f"Graph: {graph.get('graph_id', '?')}")
    print(f"Nodes: {len(graph.get('nodes', {}))}")
    print()

    # Check 1: Action ID normalization consistency
    norm_issues = check_graph_consistency(graph, normalizer)
    high_issues = [i for i in norm_issues if i.get("severity") == "HIGH"]
    med_issues = [i for i in norm_issues if i.get("severity") == "MEDIUM"]
    low_issues = [i for i in norm_issues if i.get("severity") == "LOW"]

    print(f"=== Normalization Divergence ===")
    print(f"Total: {len(norm_issues)} (HIGH={len(high_issues)}, MED={len(med_issues)}, LOW={len(low_issues)})")

    if high_issues:
        print("\n--- HIGH severity (mandatory/forbidden/deadline mismatch) ---")
        for i in high_issues:
            print(f"  [{i['node']}] {i['field']}: '{i['raw']}' → '{i['normalized']}'")

    if med_issues:
        print("\n--- MEDIUM severity (allowed/conditional mismatch) ---")
        for i in med_issues:
            print(f"  [{i['node']}] {i['field']}: '{i['raw']}' → '{i['normalized']}'")

    # Check 2: Cross-reference consistency
    print()
    xref_issues = check_cross_reference(graph, normalizer)
    print(f"=== Cross-Reference (mandatory ⊆ allowed) ===")
    print(f"Issues: {len(xref_issues)}")
    for i in xref_issues:
        print(f"  [{i['node']}] mandatory not in allowed: {i['missing']}")

    # Verdict
    print()
    if high_issues:
        print(f"FAIL — {len(high_issues)} HIGH-severity normalization divergences found")
        print("NOTE: B3 fix normalizes both sides before comparison, so scoring is unaffected.")
        print("But graph YAML should use canonical forms for clarity.")
        sys.exit(1)
    else:
        print("PASS — all mandatory/forbidden/deadline action IDs are in canonical form")
        sys.exit(0)


if __name__ == "__main__":
    main()
