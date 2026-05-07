"""PatientGenerator의 deduplication이 얼마나 시나리오를 줄이는지 분석."""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

SCENARIOS_DIR = Path(__file__).parent.parent / "configs" / "scenarios"

auto_path = SCENARIOS_DIR / "auto_generated_scenarios.yaml"
with open(auto_path) as f:
    data = yaml.safe_load(f)

scenarios = data.get("scenarios", {})

print(f"Total auto scenarios: {len(scenarios)}")

rule_sets: Counter[tuple[str, ...]] = Counter()
method_counts: Counter[str] = Counter()

for sid, s in scenarios.items():
    rules = tuple(sorted(s.get("triggered_rules", []) or []))
    rule_sets[rules] += 1
    method_counts[s.get("generation_method", "unknown")] += 1

print(f"Unique triggered_rules sets: {len(rule_sets)}")

duplicates = sum(v - 1 for v in rule_sets.values() if v > 1)
print(f"Duplicates (same rule set, multiple scenarios): {duplicates}")

print("\nGeneration method distribution:")
for method, count in method_counts.most_common():
    print(f"  {method}: {count}")

print("\nRule set size distribution:")
size_dist: Counter[int] = Counter()
for rules in rule_sets:
    size_dist[len(rules)] += 1
for size, count in sorted(size_dist.items()):
    label = "baseline (no rules triggered)" if size == 0 else f"{size}-rule trap"
    print(f"  {label}: {count} unique scenarios")

print("\nMost common triggered rule sets:")
for rules, count in rule_sets.most_common(15):
    if not rules:
        print(f"  {count}x: (no rules — baseline)")
    else:
        display = ", ".join(rules[:3])
        if len(rules) > 3:
            display += f"... (+{len(rules) - 3} more)"
        print(f"  {count}x: [{display}]")
