"""Audit 5: skip_scenario_generation이 정말 시나리오 생성을 막는지

60개 companion rule에 skip_scenario_generation: true를 달았다.
이 rule에서 시나리오가 안 만들어졌는지 확인.

skip_scenario_generation=true인 rule의 rule_id가
어떤 시나리오의 triggered_rules에도 없어야 한다.
"""

from pathlib import Path
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from audit._helpers import GRAPHS_DIR, load_raw_scenarios

# 1. Collect skip rule IDs
skip_rules: set[str] = set()
for p in sorted(GRAPHS_DIR.glob("*.yaml")):
    with open(p) as f:
        g = yaml.safe_load(f)
    if not g:
        continue
    for nid, node in g.get("nodes", {}).items():
        for rule in node.get("conditional_rules", []):
            if rule.get("skip_scenario_generation"):
                skip_rules.add(rule["rule_id"])

print(f"Skip rules: {len(skip_rules)}")
for r in sorted(skip_rules):
    print(f"  {r}")

# 2. Check no scenario was triggered by a skip rule
scenarios = load_raw_scenarios()
violations: list[str] = []
for s in scenarios:
    triggered = set(s.get("triggered_rules") or [])
    overlap = triggered & skip_rules
    if overlap:
        violations.append(f"{s['scenario_id']}: triggered skip rule(s) {sorted(overlap)}")

print(f"\nScenarios checked: {len(scenarios)}")
print(f"Violations: {len(violations)}")
for v in violations[:20]:
    print(f"  {v}")

if not violations:
    print("CONFIRMED: No scenario was generated from a skip_scenario_generation rule")

print(f"\n{'=' * 50}")
print("Audit 5 complete.")
