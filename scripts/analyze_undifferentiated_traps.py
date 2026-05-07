"""Analyze 83 undifferentiated trap scenarios: classify Root Cause A vs B.

Root Cause A: conditional forbidden actions are all already in unconditional set
Root Cause B: unique conditional exists but still undifferentiated (other reason)
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"
SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"
OUTPUT_FILE = Path(__file__).parent.parent / "evidence_pack" / "undifferentiated_trap_analysis.json"


def load_all_scenarios_raw() -> dict[str, dict]:
    """Load all scenarios from YAML files, preserving triggered_rules."""
    all_scenarios: dict[str, dict] = {}
    for scenario_file in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
        with open(scenario_file, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if not data:
            continue

        scenarios = data.get("scenarios", {})
        if not scenarios:
            continue

        for sid, sconfig in scenarios.items():
            if not isinstance(sconfig, dict):
                continue
            sconfig["_source_file"] = scenario_file.name
            all_scenarios[sid] = sconfig
    return all_scenarios


def get_graph_unconditional_forbidden(graph_path: Path) -> set[str]:
    """Extract unconditional forbidden actions from all nodes in a graph."""
    with open(graph_path, encoding="utf-8") as f:
        graph = yaml.safe_load(f)
    uncond: set[str] = set()
    for _node_id, node in graph.get("nodes", {}).items():
        uncond.update(node.get("forbidden_actions", []))
    return uncond


def get_graph_conditional_rules(graph_path: Path) -> dict[str, dict]:
    """Extract all conditional rules from a graph, keyed by rule_id."""
    with open(graph_path, encoding="utf-8") as f:
        graph = yaml.safe_load(f)
    rules: dict[str, dict] = {}
    for _node_id, node in graph.get("nodes", {}).items():
        for rule in node.get("conditional_rules", []):
            rid = rule.get("rule_id", "")
            rules[rid] = rule
    return rules


def find_graph_path(graph_id: str) -> Path | None:
    """Find graph YAML file by graph_id."""
    for p in GRAPHS_DIR.glob("*.yaml"):
        with open(p, encoding="utf-8") as f:
            g = yaml.safe_load(f)
        if g.get("graph_id") == graph_id:
            return p
    # Fallback: stem match
    candidate = GRAPHS_DIR / f"{graph_id}.yaml"
    if candidate.exists():
        return candidate
    return None


def main() -> None:
    print("Loading all scenarios...")
    all_scenarios = load_all_scenarios_raw()
    print(f"  Total: {len(all_scenarios)}")

    # Classify trap vs normal
    traps: dict[str, dict] = {}
    normals: dict[str, dict] = {}
    for sid, s in all_scenarios.items():
        if s.get("trap_scenario", False):
            traps[sid] = s
        else:
            normals[sid] = s
    print(f"  Traps: {len(traps)}, Normals: {len(normals)}")

    # Normal forbidden by graph
    normal_forbidden_by_graph: dict[str, set[str]] = defaultdict(set)
    for sid, s in normals.items():
        graph = s.get("guideline_graph", "unknown")
        normal_forbidden_by_graph[graph].update(s.get("forbidden_actions", []))

    # Pre-load all graphs
    print("\nLoading graph data...")
    graph_unconditional: dict[str, set[str]] = {}
    graph_conditional_rules: dict[str, dict[str, dict]] = {}
    graph_paths: dict[str, Path] = {}

    for p in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(p, encoding="utf-8") as f:
            g = yaml.safe_load(f)
        gid = g.get("graph_id", p.stem)
        graph_paths[gid] = p
        graph_unconditional[gid] = get_graph_unconditional_forbidden(p)
        graph_conditional_rules[gid] = get_graph_conditional_rules(p)
        print(
            f"  {gid}: {len(graph_unconditional[gid])} unconditional forbidden, "
            f"{len(graph_conditional_rules[gid])} conditional rules"
        )

    # Find undifferentiated traps
    print("\nAnalyzing undifferentiated traps...")
    root_cause_a: list[dict] = []
    root_cause_b: list[dict] = []
    differentiated: list[str] = []

    for sid, s in traps.items():
        graph = s.get("guideline_graph", "unknown")
        trap_forbidden = set(s.get("forbidden_actions", []))
        normal_forbidden = normal_forbidden_by_graph.get(graph, set())
        unique_to_trap = trap_forbidden - normal_forbidden

        if unique_to_trap:
            differentiated.append(sid)
            continue

        # This is an undifferentiated trap - classify root cause
        triggered = s.get("triggered_rules", []) or []

        # Get conditional forbidden actions from triggered rules
        conditional_forbidden: set[str] = set()
        triggered_rule_details: list[dict] = []

        rules_map = graph_conditional_rules.get(graph, {})
        for rule_id in triggered:
            rule = rules_map.get(rule_id)
            if not rule:
                continue
            effect = rule.get("effect", {})
            if effect.get("type") == "FORBIDDEN":
                actions = effect.get("actions", [])
                conditional_forbidden.update(actions)
                triggered_rule_details.append(
                    {
                        "rule_id": rule_id,
                        "condition": rule.get("condition", ""),
                        "forbidden_actions": actions,
                        "evidence": rule.get("evidence", ""),
                        "severity": rule.get("severity", ""),
                    }
                )

        uncond = graph_unconditional.get(graph, set())
        overlap = conditional_forbidden & uncond
        unique_cond = conditional_forbidden - uncond

        entry = {
            "scenario_id": sid,
            "graph": graph,
            "source_file": s.get("_source_file", ""),
            "triggered_rules": triggered,
            "triggered_rule_details": triggered_rule_details,
            "conditional_forbidden": sorted(conditional_forbidden),
            "unconditional_forbidden": sorted(uncond),
            "unconditional_forbidden_count": len(uncond),
            "overlap_with_unconditional": sorted(overlap),
            "unique_conditional": sorted(unique_cond),
            "trap_forbidden": sorted(trap_forbidden),
            "normal_forbidden": sorted(normal_forbidden),
        }

        if not unique_cond:
            root_cause_a.append(entry)
        else:
            root_cause_b.append(entry)

    total_undiff = len(root_cause_a) + len(root_cause_b)
    print(f"\n{'=' * 60}")
    print("=== Root Cause Analysis ===")
    print(f"Differentiated traps: {len(differentiated)}")
    print(f"Undifferentiated traps: {total_undiff}")
    print(f"  Root Cause A (conditional ⊆ unconditional): {len(root_cause_a)}")
    print(f"  Root Cause B (unique conditional exists but still undiff): {len(root_cause_b)}")

    # Root Cause A by graph
    a_by_graph: dict[str, list[dict]] = defaultdict(list)
    for entry in root_cause_a:
        a_by_graph[entry["graph"]].append(entry)

    print(f"\n{'=' * 60}")
    print("=== Root Cause A by Graph ===")
    for g, entries in sorted(a_by_graph.items(), key=lambda x: -len(x[1])):
        rules: set[str] = set()
        for e in entries:
            rules.update(e["triggered_rules"])
        overlapping: set[str] = set()
        for e in entries:
            overlapping.update(e["overlap_with_unconditional"])

        print(f"\n  {g}: {len(entries)} undifferentiated traps")
        print(f"    Rules involved: {sorted(rules)}")
        print(f"    Overlapping forbidden (cond ∩ uncond): {sorted(overlapping)}")
        print(f"    Unconditional count: {entries[0]['unconditional_forbidden_count']}")

        # Show rule details
        seen_rules: set[str] = set()
        for e in entries:
            for rd in e["triggered_rule_details"]:
                if rd["rule_id"] not in seen_rules:
                    seen_rules.add(rd["rule_id"])
                    print(f"    Rule {rd['rule_id']}:")
                    print(f"      condition: {rd['condition']}")
                    print(f"      forbidden: {rd['forbidden_actions']}")
                    print(f"      evidence: {rd['evidence']}")

    # Root Cause B details
    if root_cause_b:
        b_by_graph: dict[str, list[dict]] = defaultdict(list)
        for entry in root_cause_b:
            b_by_graph[entry["graph"]].append(entry)

        print(f"\n{'=' * 60}")
        print("=== Root Cause B by Graph ===")
        for g, entries in sorted(b_by_graph.items(), key=lambda x: -len(x[1])):
            print(f"\n  {g}: {len(entries)} undifferentiated traps")
            for e in entries[:5]:
                print(f"    {e['scenario_id']}:")
                print(f"      unique conditional: {e['unique_conditional']}")
                print(f"      trap forbidden:  {len(e['trap_forbidden'])} actions")
                print(f"      normal forbidden: {len(e['normal_forbidden'])} actions")

    # Save results
    OUTPUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    result = {
        "summary": {
            "total_traps": len(traps),
            "differentiated": len(differentiated),
            "undifferentiated": total_undiff,
            "root_cause_a": len(root_cause_a),
            "root_cause_b": len(root_cause_b),
        },
        "root_cause_a_by_graph": {
            g: {
                "count": len(entries),
                "rules": sorted({r for e in entries for r in e["triggered_rules"]}),
                "scenarios": [e["scenario_id"] for e in entries],
            }
            for g, entries in sorted(a_by_graph.items(), key=lambda x: -len(x[1]))
        },
        "root_cause_a": root_cause_a,
        "root_cause_b": root_cause_b,
    }
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\nResults saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()
