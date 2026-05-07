"""Audit 4: Expected와 Forbidden이 실제로 Derivation Engine에서 나오는지

auto-generated 시나리오 10개에 대해:
1. YAML의 expected/forbidden 읽기
2. engine.derive()로 다시 계산
3. 두 결과가 일치하는지 비교

"YAML에 직접 적었지만 engine이 모르는 constraint"가 있으면 provenance chain이 끊긴 것.
"""

from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from audit._helpers import load_graph, load_raw_scenarios, patient_to_eval_dict
from cpg_model.constraint_derivation import ConstraintDerivationEngine

random.seed(77)
engine = ConstraintDerivationEngine()

all_scenarios = load_raw_scenarios()

# Filter auto-generated only
auto = [s for s in all_scenarios if "auto" in str(s.get("generation_method", ""))]

print(f"Total auto-generated scenarios: {len(auto)}")

sample = random.sample(auto, min(10, len(auto)))

mismatches = 0
for s in sample:
    # YAML에 기록된 것
    yaml_expected = set(s.get("expected_actions") or [])
    yaml_forbidden = set(s.get("forbidden_actions") or [])

    # Engine으로 다시 계산
    graph = load_graph(s["guideline_graph"])
    if not graph:
        print(f"SKIP: {s['scenario_id']} -- graph '{s['guideline_graph']}' not found")
        continue

    patient = patient_to_eval_dict(s.get("patient", {}))
    derived = engine.derive(graph, patient, s["scenario_id"])

    derived_forbidden: set[str] = set()
    for c in derived.forbidden:
        derived_forbidden.update(c.actions)

    derived_expected: set[str] = set()
    for c in derived.expected:
        derived_expected.update(c.actions)
    for c in derived.required:
        derived_expected.update(c.actions)

    # Compare forbidden
    fb_only_yaml = yaml_forbidden - derived_forbidden
    fb_only_derived = derived_forbidden - yaml_forbidden

    # Compare expected
    ea_only_yaml = yaml_expected - derived_expected
    ea_only_derived = derived_expected - yaml_expected

    if fb_only_yaml or fb_only_derived or ea_only_yaml or ea_only_derived:
        mismatches += 1
        print(f"\nMISMATCH: {s['scenario_id']} (method={s.get('generation_method', 'N/A')})")
        if fb_only_yaml:
            print(f"  Forbidden in YAML but NOT in derived: {sorted(fb_only_yaml)}")
        if fb_only_derived:
            print(f"  Forbidden in derived but NOT in YAML: {sorted(fb_only_derived)}")
        if ea_only_yaml:
            print(f"  Expected in YAML but NOT in derived: {sorted(ea_only_yaml)}")
        if ea_only_derived:
            print(f"  Expected in derived but NOT in YAML: {sorted(ea_only_derived)}")
    else:
        print(f"MATCH: {s['scenario_id']} (method={s.get('generation_method', 'N/A')})")

print(f"\n{'=' * 50}")
print(f"Mismatches: {mismatches}/{len(sample)}")
