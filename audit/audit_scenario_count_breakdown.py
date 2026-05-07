"""Audit 8: 시나리오 수 변화 추적

시나리오가 어디서 오는지 source별로 분해.
"""

from collections import Counter
from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from audit._helpers import SCENARIOS_DIR, load_raw_scenarios

scenarios = load_raw_scenarios()

# 1. By generation method
source_count: Counter = Counter()
for s in scenarios:
    method = s.get("generation_method", "manual")
    source_count[method] += 1

print(f"Total: {len(scenarios)}")
print("\nBy generation method:")
for m, c in source_count.most_common():
    print(f"  {m}: {c}")

# 2. By trap vs normal
traps = sum(1 for s in scenarios if s.get("trap_scenario"))
normals = len(scenarios) - traps
print(f"\nBy type: traps={traps}, normals={normals}")

# 3. By YAML file
yaml_count: Counter = Counter()
for p in sorted(SCENARIOS_DIR.glob("*_scenarios.yaml")):
    with open(p) as f:
        data = yaml.safe_load(f)
    if not data:
        yaml_count[p.name] = 0
        continue
    if isinstance(data, dict) and "scenarios" in data:
        yaml_count[p.name] = len(data["scenarios"])
    elif isinstance(data, list):
        yaml_count[p.name] = len(data)
    else:
        yaml_count[p.name] = 1 if data else 0

print("\nBy YAML file:")
for f, c in yaml_count.most_common():
    print(f"  {f}: {c}")
print(f"  Sum: {sum(yaml_count.values())}")

# 4. By guideline graph
graph_count: Counter = Counter()
for s in scenarios:
    graph_count[s.get("guideline_graph", "UNKNOWN")] += 1

print("\nBy guideline graph:")
for g, c in graph_count.most_common():
    print(f"  {g}: {c}")

# 5. Cross-tabulation: graph x method
print("\nCross-tabulation (graph x method):")
cross: dict[str, Counter] = {}
for s in scenarios:
    g = s.get("guideline_graph", "UNKNOWN")
    m = s.get("generation_method", "manual")
    if g not in cross:
        cross[g] = Counter()
    cross[g][m] += 1

for g in sorted(cross.keys()):
    methods_str = ", ".join(f"{m}={c}" for m, c in cross[g].most_common())
    print(f"  {g}: {methods_str}")

print(f"\n{'=' * 50}")
print("Audit 8 complete.")
