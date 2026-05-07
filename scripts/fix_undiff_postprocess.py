"""Post-process scenarios: strip conditional forbidden actions from normals.

Normal (baseline) scenarios should only contain UNCONDITIONAL forbidden
actions (those on node-level ``forbidden_actions`` lists).  Conditional
FORBIDDEN rules fire opportunistically based on the base-patient template,
leaking their actions into the normal_forbidden_union and erasing the
differentiation signal for trap scenarios.

Fix: collect ALL conditional FORBIDDEN actions per graph, compute the
strip-set (conditional - unconditional), and remove them from every normal
scenario's forbidden_actions.  Trap scenarios remain untouched.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

import yaml

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"
SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"


def collect_all_conditional_forbidden_per_graph() -> dict[str, set[str]]:
    """Collect forbidden actions from ALL conditional FORBIDDEN rules."""
    result: dict[str, set[str]] = defaultdict(set)
    for graph_path in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(graph_path, encoding="utf-8") as f:
            graph = yaml.safe_load(f)
        if not graph:
            continue
        graph_id = graph.get("graph_id", graph_path.stem)
        for _node_id, node in graph.get("nodes", {}).items():
            for rule in node.get("conditional_rules", []):
                effect = rule.get("effect", {})
                if effect.get("type") == "FORBIDDEN":
                    for action in effect.get("actions", []):
                        result[graph_id].add(action)
    return result


def collect_unconditional_forbidden_per_graph() -> dict[str, set[str]]:
    """Collect unconditional (node-level) forbidden actions per graph."""
    result: dict[str, set[str]] = defaultdict(set)
    for graph_path in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(graph_path, encoding="utf-8") as f:
            graph = yaml.safe_load(f)
        if not graph:
            continue
        graph_id = graph.get("graph_id", graph_path.stem)
        for _node_id, node in graph.get("nodes", {}).items():
            for action in node.get("forbidden_actions", []):
                result[graph_id].add(action)
    return result


def process_scenario_file(
    scenario_file: Path,
    conditional_forbidden: dict[str, set[str]],
    unconditional_forbidden: dict[str, set[str]],
) -> int:
    """Remove conditional-only forbidden from normal scenarios.

    Returns number of normal scenarios modified.
    """
    with open(scenario_file, encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not data or "scenarios" not in data:
        return 0

    modified = 0
    for _sid, sconfig in data["scenarios"].items():
        if not isinstance(sconfig, dict):
            continue
        if sconfig.get("trap_scenario", False):
            continue  # leave traps unchanged

        graph_id = sconfig.get("guideline_graph", "unknown")
        cond_actions = conditional_forbidden.get(graph_id, set())
        if not cond_actions:
            continue

        # Strip actions that are EXCLUSIVELY from conditional rules
        uncond = unconditional_forbidden.get(graph_id, set())
        strip_actions = cond_actions - uncond

        forbidden = sconfig.get("forbidden_actions", [])
        original_len = len(forbidden)
        cleaned = [a for a in forbidden if a not in strip_actions]
        if len(cleaned) < original_len:
            sconfig["forbidden_actions"] = cleaned
            modified += 1

    if modified > 0:
        with open(scenario_file, "w", encoding="utf-8") as f:
            yaml.dump(
                data,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )

    return modified


def main() -> None:
    print("Collecting ALL conditional FORBIDDEN actions per graph...")
    conditional_forbidden = collect_all_conditional_forbidden_per_graph()
    for graph_id, actions in sorted(conditional_forbidden.items()):
        print(f"  {graph_id}: {len(actions)} conditional forbidden actions")

    print("\nCollecting unconditional forbidden per graph...")
    unconditional_forbidden = collect_unconditional_forbidden_per_graph()
    for graph_id, actions in sorted(unconditional_forbidden.items()):
        print(f"  {graph_id}: {len(actions)} unconditional forbidden actions")

    print("\nComputing strip sets (conditional - unconditional)...")
    all_graphs = set(conditional_forbidden.keys()) | set(unconditional_forbidden.keys())
    for graph_id in sorted(all_graphs):
        cond = conditional_forbidden.get(graph_id, set())
        uncond = unconditional_forbidden.get(graph_id, set())
        strip = cond - uncond
        if strip:
            print(f"  {graph_id}: {len(strip)} actions to strip from normals")

    print("\nProcessing scenario files...")
    total_modified = 0
    for scenario_file in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
        count = process_scenario_file(
            scenario_file,
            conditional_forbidden,
            unconditional_forbidden,
        )
        if count > 0:
            print(f"  {scenario_file.name}: {count} normal scenarios cleaned")
            total_modified += count

    print(f"\nTotal: {total_modified} normal scenarios had conditional forbidden stripped")


if __name__ == "__main__":
    main()
