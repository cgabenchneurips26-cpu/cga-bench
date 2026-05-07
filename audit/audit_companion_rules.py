"""Audit 1: Companion Rule이 실제로 작동하는가?

60개 companion rule 중 5개를 랜덤 추출하여:
1. rule의 condition을 읽고
2. 해당 condition을 만족하는 시나리오를 찾고
3. 그 시나리오의 forbidden에 companion rule의 action이 실제로 포함되어 있는지 확인
"""

from pathlib import Path
import random
import sys

import yaml

sys.path.insert(0, str(Path(__file__).parent.parent))

from audit._helpers import GRAPHS_DIR, load_raw_scenarios, patient_to_eval_dict
from cpg_model.constraint_derivation import ConstraintDerivationEngine

random.seed(42)
engine = ConstraintDerivationEngine()

# 1. Collect all companion rules (skip_scenario_generation=true)
companions: list[dict] = []
for p in sorted(GRAPHS_DIR.glob("*.yaml")):
    with open(p) as f:
        g = yaml.safe_load(f)
    if not g:
        continue
    for nid, node in g.get("nodes", {}).items():
        for rule in node.get("conditional_rules", []):
            if rule.get("skip_scenario_generation"):
                companions.append(
                    {
                        "graph": g["graph_id"],
                        "node": nid,
                        "rule": rule,
                        "graph_path": str(p),
                    }
                )

print(f"Total companion rules: {len(companions)}")

# 2. Sample 5
sample = random.sample(companions, min(5, len(companions)))

# 3. Load all raw scenarios once
all_scenarios = load_raw_scenarios()

for comp in sample:
    print(f"\n{'=' * 70}")
    print(f"Graph: {comp['graph']}")
    print(f"Rule: {comp['rule']['rule_id']}")
    print(f"Condition: {comp['rule']['condition']}")
    print(f"Effect type: {comp['rule']['effect']['type']}")
    print(f"Forbidden actions: {comp['rule']['effect']['actions']}")

    # Find scenarios on this graph where condition fires
    matching_scenarios: list[dict] = []
    for s in all_scenarios:
        if s.get("guideline_graph") != comp["graph"]:
            continue
        patient = patient_to_eval_dict(s.get("patient", {}))
        try:
            fires = engine._evaluate_condition(comp["rule"]["condition"], patient)
        except Exception as e:
            fires = False
            print(f"  EVAL ERROR: {e}")
        if fires:
            matching_scenarios.append(s)

    print(f"Scenarios where condition fires: {len(matching_scenarios)}")

    if matching_scenarios:
        s = matching_scenarios[0]
        forbidden_set = set(s.get("forbidden_actions") or [])
        companion_actions = set(comp["rule"]["effect"]["actions"])
        present = companion_actions & forbidden_set
        missing = companion_actions - forbidden_set

        print(f"  Sample scenario: {s['scenario_id']}")
        print(f"  Scenario trap: {s.get('trap_scenario', False)}")
        print(f"  Scenario forbidden ({len(forbidden_set)}): {sorted(forbidden_set)}")
        print(f"  Companion actions in forbidden: {sorted(present)}")
        print(f"  Companion actions MISSING from forbidden: {sorted(missing)}")

        if missing:
            # Check if it's a trap scenario - companion actions should be in trap forbidden
            if s.get("trap_scenario"):
                print("  *** BUG: Companion rule fires on TRAP but actions not in forbidden! ***")
            else:
                # Normal scenario: companion actions are stripped by design
                print("  NOTE: Normal scenario — companion actions correctly stripped from forbidden")
        else:
            print("  OK: All companion actions present in forbidden")
    else:
        print("  WARNING: No scenario triggers this companion rule")

print(f"\n{'=' * 70}")
print("Audit 1 complete.")
