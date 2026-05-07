"""Audit 6: Value Variation이 실제로 다른 값을 가지는지

같은 rule의 boundary/extreme/trigger가 실제로 다른 lab 값을 가지는지.
"""

from collections import defaultdict
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from audit._helpers import load_raw_scenarios

scenarios = load_raw_scenarios()

# generation_method에 'value_'가 포함된 시나리오
value_scenarios = [s for s in scenarios if "value_" in str(s.get("generation_method", ""))]

print(f"Value variation scenarios: {len(value_scenarios)}")

# 같은 rule을 trigger하는 시나리오끼리 묶기
by_rule: dict[tuple, list[dict]] = defaultdict(list)
for s in value_scenarios:
    rules = tuple(sorted(s.get("triggered_rules") or []))
    by_rule[rules].append(s)

# 같은 rule 그룹 내에서 lab 값이 다른지 확인
identical_groups = 0
total_groups = 0
for rules, group in sorted(by_rule.items()):
    if len(group) < 2:
        continue
    total_groups += 1

    labs_list = []
    for s in group:
        p = s.get("patient", {})
        labs_list.append(str(sorted(p.get("labs", {}).items())))

    if len(set(labs_list)) == 1:
        identical_groups += 1
        print(f"IDENTICAL: {[s['scenario_id'] for s in group]} -- same labs: {labs_list[0][:100]}")
    else:
        unique_count = len(set(labs_list))
        print(f"DIVERSE: {[s['scenario_id'] for s in group]} -- {unique_count} unique lab sets out of {len(group)}")
        # Show actual lab differences
        for s in group:
            p = s.get("patient", {})
            method = s.get("generation_method", "")
            print(f"    {s['scenario_id']} ({method}): {p.get('labs', {})}")

print(f"\n{'=' * 50}")
print(f"Total groups with 2+ scenarios: {total_groups}")
print(f"Identical groups (PROBLEM): {identical_groups}")
print(f"Diverse groups (OK): {total_groups - identical_groups}")
