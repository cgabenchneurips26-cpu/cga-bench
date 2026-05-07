"""Test 3.1: Verify expected actions distribution is reasonable."""

from __future__ import annotations

from collections import Counter, defaultdict
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"


def main() -> None:
    auto_scenarios: list[dict] = []
    manual_scenarios: list[dict] = []

    for sf in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
        with open(sf) as f:
            data = yaml.safe_load(f)
        if not data or "scenarios" not in data:
            continue
        for sid, sdata in data["scenarios"].items():
            sdata["_scenario_id"] = sid
            if sf.name == "auto_generated_scenarios.yaml":
                auto_scenarios.append(sdata)
            else:
                manual_scenarios.append(sdata)

    # Auto-generated stats
    print("=== Auto-generated scenarios ===")
    auto_ea = [len(s.get("expected_actions") or []) for s in auto_scenarios]
    if auto_ea:
        sorted_ea = sorted(auto_ea)
        print(
            f"Expected actions: min={min(auto_ea)}, max={max(auto_ea)}, "
            f"mean={sum(auto_ea) / len(auto_ea):.1f}, "
            f"median={sorted_ea[len(sorted_ea) // 2]}"
        )

        bins: Counter[str] = Counter()
        for ea in auto_ea:
            if ea == 0:
                bins["0"] += 1
            elif ea <= 5:
                bins["1-5"] += 1
            elif ea <= 10:
                bins["6-10"] += 1
            elif ea <= 20:
                bins["11-20"] += 1
            elif ea <= 30:
                bins["21-30"] += 1
            else:
                bins["31+"] += 1
        print(f"Distribution: {dict(sorted(bins.items()))}")
    else:
        print("No auto-generated scenarios found")

    # Manual stats
    print("\n=== Manual scenarios ===")
    manual_ea = [len(s.get("expected_actions") or []) for s in manual_scenarios]
    if manual_ea:
        sorted_mea = sorted(manual_ea)
        print(
            f"Expected actions: min={min(manual_ea)}, max={max(manual_ea)}, "
            f"mean={sum(manual_ea) / len(manual_ea):.1f}, "
            f"median={sorted_mea[len(sorted_mea) // 2]}"
        )

    # Forbidden stats
    print("\n=== Forbidden actions ===")
    auto_fa = [len(s.get("forbidden_actions") or []) for s in auto_scenarios]
    manual_fa = [len(s.get("forbidden_actions") or []) for s in manual_scenarios]
    if auto_fa:
        print(f"Auto forbidden: min={min(auto_fa)}, max={max(auto_fa)}, mean={sum(auto_fa) / len(auto_fa):.1f}")
    if manual_fa:
        print(
            f"Manual forbidden: min={min(manual_fa)}, max={max(manual_fa)}, mean={sum(manual_fa) / len(manual_fa):.1f}"
        )

    # High expected review
    if auto_ea:
        high_ea = [
            (s["_scenario_id"], len(s.get("expected_actions") or []), s.get("guideline_graph", "?"))
            for s in auto_scenarios
            if len(s.get("expected_actions") or []) > 30
        ]
        if high_ea:
            print(f"\n=== Scenarios with >30 expected actions ({len(high_ea)}) ===")
            for sid, ea, g in sorted(high_ea, key=lambda x: -x[1])[:10]:
                print(f"  {sid}: {ea} expected (graph: {g})")
            print("CHECK: Verify these aren't over-activating all nodes")

    # Trap vs normal expected per graph
    by_graph: dict[str, dict[str, list[int]]] = defaultdict(lambda: {"trap": [], "normal": []})
    for s in auto_scenarios:
        key = "trap" if s.get("trap_scenario") else "normal"
        by_graph[s.get("guideline_graph", "unknown")][key].append(len(s.get("expected_actions") or []))

    print("\n=== Expected actions: trap vs normal by graph ===")
    for g in sorted(by_graph.keys()):
        trap_ea_list = by_graph[g]["trap"]
        norm_ea_list = by_graph[g]["normal"]
        t_mean = sum(trap_ea_list) / len(trap_ea_list) if trap_ea_list else 0
        n_mean = sum(norm_ea_list) / len(norm_ea_list) if norm_ea_list else 0
        print(f"  {g}: trap={t_mean:.1f} ({len(trap_ea_list)}), normal={n_mean:.1f} ({len(norm_ea_list)})")


if __name__ == "__main__":
    main()
