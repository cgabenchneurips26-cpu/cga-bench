"""Audit 7: Pathway Normal이 실제로 다른 Expected를 가지는지

같은 graph의 pathway normal 시나리오가 서로 다른 expected_actions를 가지는지.
"""

from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from audit._helpers import load_raw_scenarios

scenarios = load_raw_scenarios()

pathway = [s for s in scenarios if s.get("generation_method") == "auto:pathway_normal"]

print(f"Pathway normal scenarios: {len(pathway)}")

by_graph: dict[str, list[dict]] = defaultdict(list)
for s in pathway:
    by_graph[s["guideline_graph"]].append(s)

problem_count = 0
for g, group in sorted(by_graph.items()):
    if len(group) < 2:
        print(f"SINGLE: {g} -- only 1 pathway scenario")
        continue

    ea_sets = [frozenset(s.get("expected_actions") or []) for s in group]
    unique = len(set(ea_sets))

    if unique == 1:
        problem_count += 1
        print(f"PROBLEM: {g} -- {len(group)} pathways but ALL have identical expected!")
        print(f"  Expected: {sorted(ea_sets[0])}")
    else:
        # pairwise overlap
        overlaps = []
        for i in range(len(ea_sets)):
            for j in range(i + 1, len(ea_sets)):
                inter = len(ea_sets[i] & ea_sets[j])
                union = len(ea_sets[i] | ea_sets[j])
                overlaps.append(inter / union if union else 1.0)
        avg_overlap = sum(overlaps) / len(overlaps) if overlaps else 0
        print(f"OK: {g} -- {len(group)} pathways, {unique} unique, avg Jaccard overlap={avg_overlap:.0%}")
        for s in group:
            ea = s.get("expected_actions") or []
            print(f"    {s['scenario_id']}: {len(ea)} expected -> {sorted(ea)[:5]}...")

print(f"\n{'=' * 50}")
print(f"Problem graphs (identical pathways): {problem_count}")
print(f"Total pathway graphs: {len(by_graph)}")
