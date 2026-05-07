"""Audit 10: 실행 가능성 -- Dry Run

ScenarioLoader와 ClinicalEnvironment가 실제로 작동하는지 확인.
1개 시나리오를 로드하고 환경을 생성하여 기본 동작을 검증.
"""

from pathlib import Path
import sys

# Need parent-of-cga_bench on path for cga_bench.* imports used by eval_harness
_cga_bench_root = Path(__file__).parent.parent
sys.path.insert(0, str(_cga_bench_root))
sys.path.insert(0, str(_cga_bench_root.parent))

from eval_harness.scenario_loader import ScenarioLoader

loader = ScenarioLoader()
all_scenarios = loader.load_all_scenarios()

print(f"ScenarioLoader loaded {len(all_scenarios)} scenarios")

# Pick a simple scenario
target_ids = [
    "septic_shock_basic",
    "contrast_aki_prevention_basic",
    "aki_stage1_basic",
]

picked = None
for tid in target_ids:
    if tid in all_scenarios:
        picked = tid
        break

if not picked:
    # Fall back to first available
    picked = next(iter(all_scenarios))

print(f"Dry-run scenario: {picked}")

scenario = all_scenarios[picked]
print(f"  Description: {scenario.description}")
print(f"  Graph: {scenario.guideline_graph}")
print(f"  Trap: {scenario.trap_scenario}")
print(f"  Expected actions: {scenario.expected_actions}")
print(f"  Forbidden actions: {scenario.forbidden_actions}")
print(f"  Patient age: {scenario.patient.age}")
print(f"  Patient sex: {scenario.patient.sex}")

# Try creating environment
try:
    env = loader.create_environment(picked)
    obs = env.reset()
    print("\nEnvironment created successfully!")
    print(f"  Initial timestamp: {obs.timestamp_minutes}")
    print(
        f"  Available actions: {obs.available_actions[:10]}..."
        if len(obs.available_actions) > 10
        else f"  Available actions: {obs.available_actions}"
    )
    print(f"  Mandatory actions: {obs.mandatory_actions}")
    print(f"  Alerts: {obs.alerts}")
    print(f"  Visible state keys: {sorted(obs.visible_state.keys()) if obs.visible_state else 'empty'}")
    print("\nDry-run: OK")
except Exception as e:
    print(f"\nDry-run FAILED: {type(e).__name__}: {e}")

# Also verify all scenarios can at least be loaded without error
print(f"\nValidating all {len(all_scenarios)} scenarios load correctly...")
load_errors = 0
for sid, sdef in all_scenarios.items():
    try:
        assert sdef.scenario_id == sid
        assert sdef.guideline_graph
        assert isinstance(sdef.expected_actions, list)
        assert isinstance(sdef.forbidden_actions, list)
    except (AssertionError, AttributeError) as e:
        load_errors += 1
        print(f"  LOAD ERROR: {sid}: {e}")

print(f"Load errors: {load_errors}/{len(all_scenarios)}")

print(f"\n{'=' * 50}")
print("Audit 10 complete.")
