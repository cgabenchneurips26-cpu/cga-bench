"""Test 3.2: Verify trap vs normal differentiation.

Key question: do trap scenarios have different constraints than normal scenarios?
If not, conditional rules aren't working.
"""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"


def main() -> None:
    all_scenarios: list[dict] = []

    for sf in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
        with open(sf) as f:
            data = yaml.safe_load(f)
        if not data or "scenarios" not in data:
            continue
        for sid, sdata in data["scenarios"].items():
            sdata["_scenario_id"] = sid
            all_scenarios.append(sdata)

    by_graph: dict[str, dict[str, list[dict]]] = defaultdict(lambda: {"trap": [], "normal": []})
    for s in all_scenarios:
        key = "trap" if s.get("trap_scenario") else "normal"
        by_graph[s.get("guideline_graph", "unknown")][key].append(s)

    print("=== Trap vs Normal Differentiation ===\n")
    problems: list[str] = []

    for g in sorted(by_graph.keys()):
        traps = by_graph[g]["trap"]
        normals = by_graph[g]["normal"]

        if not traps or not normals:
            print(f"  {g}: traps={len(traps)}, normals={len(normals)} [SKIP - missing one type]")
            continue

        normal_forbidden_union: set[str] = set()
        for n in normals:
            normal_forbidden_union.update(n.get("forbidden_actions") or [])

        trap_unique_count = 0
        for t in traps:
            trap_forbidden = set(t.get("forbidden_actions") or [])
            unique_to_trap = trap_forbidden - normal_forbidden_union
            if unique_to_trap:
                trap_unique_count += 1

        diff_pct = trap_unique_count / len(traps) * 100 if traps else 0
        status = "OK" if diff_pct > 50 else "PROBLEM"

        print(f"  {g}: {trap_unique_count}/{len(traps)} traps have unique forbidden ({diff_pct:.0f}%) [{status}]")

        if status == "PROBLEM":
            problems.append(g)

    print()
    if problems:
        print(f"PROBLEM GRAPHS (trap not differentiated): {problems}")
        print("These graphs' conditional rules may not be creating meaningful trap scenarios")
    else:
        print("All graphs show adequate trap differentiation")

    # Expected actions comparison
    print("\n=== Expected actions: trap vs normal by graph ===\n")
    for g in sorted(by_graph.keys()):
        traps = by_graph[g]["trap"]
        normals = by_graph[g]["normal"]
        trap_ea = [len(s.get("expected_actions") or []) for s in traps]
        norm_ea = [len(s.get("expected_actions") or []) for s in normals]
        t_mean = sum(trap_ea) / len(trap_ea) if trap_ea else 0
        n_mean = sum(norm_ea) / len(norm_ea) if norm_ea else 0
        print(f"  {g}: trap_expected={t_mean:.1f} ({len(traps)}), normal_expected={n_mean:.1f} ({len(normals)})")


if __name__ == "__main__":
    main()
