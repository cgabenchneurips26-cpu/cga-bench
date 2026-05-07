"""현재 rule 구조에서 이론적으로 만들 수 있는 최대 시나리오 수 계산."""

from __future__ import annotations

from math import comb
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

print("THEORETICAL MAXIMUM SCENARIOS")
print("=" * 80)

grand_current = 0
grand_combo2 = 0
grand_variation = 0
grand_theoretical = 0

for graph_path in sorted(Path("cpg_model/graphs/").glob("*.yaml")):
    with open(graph_path) as f:
        graph = yaml.safe_load(f)

    graph_id = graph.get("graph_id", graph_path.stem)

    rules: list[dict] = []
    for node in graph.get("nodes", {}).values():
        for rule in node.get("conditional_rules", []):
            rules.append(rule)

    n = len(rules)
    if n == 0:
        continue

    current_single = n * 2
    combo_2 = comb(n, 2)

    numeric_rules = [r for r in rules if any(op in r.get("condition", "") for op in ["<", ">", "<=", ">="])]
    value_variation = len(numeric_rules) * 3

    theoretical_max = current_single + combo_2 + value_variation

    grand_current += current_single
    grand_combo2 += combo_2
    grand_variation += value_variation
    grand_theoretical += theoretical_max

    print(f"\n{graph_id} ({n} rules):")
    print(f"  Current: {current_single} (single trigger+normal)")
    print(f"  + 2-rule combos: {combo_2}")
    print(f"  + value variations: {value_variation} ({len(numeric_rules)} numeric rules x 3)")
    print(f"  = Theoretical max: {theoretical_max}")

print(f"\n{'=' * 80}")
print("GRAND TOTAL")
print(f"  Current single: {grand_current}")
print(f"  + 2-rule combos: {grand_combo2}")
print(f"  + value variations: {grand_variation}")
print(f"  = Theoretical max: {grand_theoretical}")
