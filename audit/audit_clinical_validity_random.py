"""Audit 3: 랜덤 시나리오 5개의 임상적 유효성 직접 검토

689개 중 5개를 랜덤 추출하여 전체 내용을 출력.
사람이 읽고 "이 시나리오가 임상적으로 말이 되는가" 판단할 수 있도록.
"""

from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).parent.parent))

from audit._helpers import load_raw_scenarios

random.seed(123)
scenarios = load_raw_scenarios()

traps = [s for s in scenarios if s.get("trap_scenario")]
normals = [s for s in scenarios if not s.get("trap_scenario")]

print(f"Total scenarios: {len(scenarios)} (traps={len(traps)}, normals={len(normals)})")

# trap 3개 + normal 2개
sample = random.sample(traps, min(3, len(traps))) + random.sample(normals, min(2, len(normals)))

for s in sample:
    p = s.get("patient", {})
    print(f"\n{'=' * 80}")
    print(f"ID: {s['scenario_id']}")
    print(f"Graph: {s.get('guideline_graph', 'N/A')}")
    print(f"Description: {s.get('description', 'N/A')}")
    print(f"Trap: {s.get('trap_scenario', False)}")
    print(f"Generation method: {s.get('generation_method', 'manual')}")
    print(f"Triggered rules: {s.get('triggered_rules', [])}")
    print(f"Source file: {s.get('_source_file', 'N/A')}")

    print("\nPatient:")
    print(f"  Age: {p.get('age')}, Sex: {p.get('sex')}")
    print(f"  Weight: {p.get('weight_kg')} kg")
    print(f"  Chief complaint: {p.get('chief_complaint', 'N/A')}")
    print(f"  Working diagnosis: {p.get('working_diagnosis', 'N/A')}")
    print(f"  Comorbidities: {p.get('comorbidities', [])}")
    print(f"  Allergies: {p.get('allergies', [])}")
    print(f"  Contraindications: {p.get('contraindications', [])}")
    print(f"  Medications: {p.get('medications', p.get('current_medications', []))}")
    print(f"  Labs: {p.get('labs', {})}")
    print(f"  Vitals: {p.get('vitals', {})}")

    ea = s.get("expected_actions") or []
    print(f"\nExpected actions ({len(ea)}):")
    for a in ea:
        print(f"  + {a}")

    fa = s.get("forbidden_actions") or []
    print(f"\nForbidden actions ({len(fa)}):")
    for a in fa:
        print(f"  x {a}")

    gt = s.get("ground_truth", {})
    if gt:
        print("\nGround truth:")
        for k, v in gt.items():
            print(f"  {k}: {v}")

    if s.get("trap_scenario"):
        print(f"\nTrap description: {s.get('trap_description', 'N/A')}")

    sc = s.get("special_considerations", [])
    if sc:
        print("\nSpecial considerations:")
        for c in sc:
            print(f"  - {c}")

print(f"\n{'=' * 80}")
print("Audit 3 complete. Review above scenarios for clinical validity.")
