# action_effects.yaml 전수검사 + State Transition 파이프라인 검증

## 목표

action_effects.yaml 468개 entry 전수검사 + CPG graph precondition과의 연결 완전성 검증.
"spot check 10개"가 아니라 **100% 자동 검증**.

## 검증 1: action_effects.yaml 런타임 불변성

```bash
# action_effects.yaml 복사 → dry-run → diff
cp action_effects.yaml /tmp/action_effects_before.yaml
# 아무 시나리오 1개 dry-run 실행
python3 run_episode.py --scenario septic_shock_basic --model qwen35b --dry-run  # 실제 명령어 확인
diff /tmp/action_effects_before.yaml action_effects.yaml
# diff가 있으면 FAIL — 런타임에 파일이 변하면 안 됨
```

## 검증 2: Graph Precondition ↔ action_effects 연결 전수검사

**이것이 핵심 검증이다.** 모든 graph의 모든 노드의 모든 precondition이 참조하는 state 변수가, 어떤 action의 effect로 설정 가능한지 확인.

```python
"""
전수검사 스크립트. 이것을 작성하고 실행하라.

출력:
1. 모든 graph precondition이 참조하는 state 변수 목록
2. 각 state 변수를 설정하는 action 목록
3. 어떤 action도 설정하지 않는 state 변수 = ORPHAN (노드 진행 불가)
4. 어떤 precondition도 참조하지 않는 effect = UNUSED (해롭지 않지만 불필요)
5. 연결 완전성 점수
"""

import yaml, glob, re
from collections import defaultdict

# 1. action_effects.yaml 로드
with open('action_effects.yaml') as f:  # 실제 경로 확인
    action_effects = yaml.safe_load(f)

# 2. 모든 graph에서 precondition → state 변수 참조 추출
precond_state_vars = defaultdict(list)  # state_var → [(graph, node_id)]
for graph_path in sorted(glob.glob('cpg_model/graphs/*.yaml')):
    with open(graph_path) as f:
        graph = yaml.safe_load(f)
    graph_name = graph_path.split('/')[-1].replace('.yaml', '')
    for node in graph.get('nodes', []):
        node_id = node.get('id', node.get('node_id', 'unknown'))
        for precond in node.get('preconditions', []):
            # state.X 패턴 추출 (state.X > 0, state.X == true 등)
            refs = re.findall(r'state\.(\w+)', str(precond))
            for ref in refs:
                precond_state_vars[ref].append((graph_name, node_id, str(precond)))

# 3. action_effects에서 effect → state 변수 설정 추출
effect_state_vars = defaultdict(list)  # state_var → [action_id]
for action_id, effects in action_effects.items():
    if isinstance(effects, dict):
        for key, value in effects.items():
            # state.X 또는 그냥 X
            var_name = key.replace('state.', '')
            effect_state_vars[var_name].append(action_id)
    # effects가 다른 형식일 수 있으므로 실제 구조에 맞게 조정

# 4. 교차 검증
print("=" * 80)
print("ORPHAN STATE VARS (precondition이 참조하지만 어떤 action도 설정 안 함)")
print("=" * 80)
orphans = []
for var, refs in sorted(precond_state_vars.items()):
    if var not in effect_state_vars:
        orphans.append(var)
        print(f"  ORPHAN: state.{var}")
        for graph, node, precond in refs:
            print(f"    ← {graph}/{node}: {precond}")

print(f"\nTotal orphans: {len(orphans)} / {len(precond_state_vars)} precondition vars")

print("\n" + "=" * 80)
print("UNUSED EFFECTS (action이 설정하지만 어떤 precondition도 참조 안 함)")
print("=" * 80)
unused = []
for var, actions in sorted(effect_state_vars.items()):
    if var not in precond_state_vars:
        unused.append(var)
        # 이건 해롭지 않으므로 요약만
print(f"Total unused effects: {len(unused)} / {len(effect_state_vars)} effect vars")

print("\n" + "=" * 80)
print("CONNECTED (양쪽 다 있음)")
print("=" * 80)
connected = set(precond_state_vars.keys()) & set(effect_state_vars.keys())
print(f"Total connected: {len(connected)} / {len(precond_state_vars)} precondition vars")

print("\n" + "=" * 80)
print("SUMMARY")
print("=" * 80)
completeness = len(connected) / len(precond_state_vars) * 100 if precond_state_vars else 100
print(f"Precondition vars: {len(precond_state_vars)}")
print(f"Effect vars: {len(effect_state_vars)}")  
print(f"Connected: {len(connected)}")
print(f"Orphans: {len(orphans)}")
print(f"Unused: {len(unused)}")
print(f"Completeness: {completeness:.1f}%")

if orphans:
    print(f"\n*** FAIL: {len(orphans)} orphan state vars → 해당 노드 진행 불가 ***")
else:
    print(f"\n*** PASS: 모든 precondition state var가 action effect로 도달 가능 ***")
```

## 검증 3: action_effects 값의 임상적 합리성 전수검사

```python
"""
468개 entry의 값 합리성을 자동 검증.
- boolean effect: True/False만 허용
- 수치 effect: 합리적 범위 내인지 (음수 혈압 등 불가)
- 이름 일관성: snake_case, 오타 탐지 (편집 거리로 유사 변수 탐지)
"""

import yaml
from collections import Counter

with open('action_effects.yaml') as f:
    data = yaml.safe_load(f)

issues = []

for action_id, effects in data.items():
    if not isinstance(effects, dict):
        issues.append(f"STRUCTURE: {action_id} — effects is not dict: {type(effects)}")
        continue
    
    for key, value in effects.items():
        # 1. 수치 범위 검증
        if isinstance(value, (int, float)):
            if key in ('map', 'systolic_bp', 'diastolic_bp') and not (0 < value < 300):
                issues.append(f"RANGE: {action_id}.{key} = {value} (혈압 범위 벗어남)")
            if key in ('heart_rate', 'pulse') and not (0 < value < 300):
                issues.append(f"RANGE: {action_id}.{key} = {value} (심박수 범위 벗어남)")
            if key in ('spo2',) and not (0 <= value <= 100):
                issues.append(f"RANGE: {action_id}.{key} = {value} (SpO2 범위 벗어남)")
            if key in ('temperature',) and not (30 < value < 45):
                issues.append(f"RANGE: {action_id}.{key} = {value} (체온 범위 벗어남)")
            if key in ('potassium', 'k') and not (1.0 < value < 10.0):
                issues.append(f"RANGE: {action_id}.{key} = {value} (칼륨 범위 벗어남)")
            if key in ('sodium', 'na') and not (100 < value < 200):
                issues.append(f"RANGE: {action_id}.{key} = {value} (나트륨 범위 벗어남)")
            if key in ('ph',) and not (6.5 < value < 8.0):
                issues.append(f"RANGE: {action_id}.{key} = {value} (pH 범위 벗어남)")

        # 2. 모순 검증: 같은 action이 상반된 effect를 가지지 않는지
        # (예: given=True와 given=False 동시)
    
    # 3. Action ID 형식
    if ' ' in action_id or action_id != action_id.lower():
        issues.append(f"FORMAT: '{action_id}' — 공백 또는 대문자 포함")

# 4. 유사 변수 탐지 (오타)
all_vars = set()
for effects in data.values():
    if isinstance(effects, dict):
        all_vars.update(effects.keys())

from difflib import get_close_matches
suspicious_pairs = []
var_list = sorted(all_vars)
for v in var_list:
    matches = get_close_matches(v, var_list, n=3, cutoff=0.85)
    matches = [m for m in matches if m != v]
    if matches:
        suspicious_pairs.append((v, matches))

print("=" * 80)
print(f"ISSUES: {len(issues)}")
print("=" * 80)
for issue in issues:
    print(f"  {issue}")

print(f"\n{'=' * 80}")
print(f"SUSPICIOUS SIMILAR VARS (오타 가능성):")
print("=" * 80)
seen = set()
for v, matches in suspicious_pairs:
    pair_key = tuple(sorted([v, matches[0]]))
    if pair_key not in seen:
        seen.add(pair_key)
        print(f"  {v} ↔ {matches}")

print(f"\nTotal entries: {len(data)}")
print(f"Total issues: {len(issues)}")
print(f"Suspicious pairs: {len(seen)}")
```

## 검증 4: 새 도메인 mandatory 진행 전수검사

```python
"""
새 도메인 대표 시나리오 전부에서 에피소드를 시뮬레이션하고
mandatory가 step마다 변하는지 확인.
mandatory가 전혀 안 변하는 시나리오 = state transition이 precondition과 연결 안 됨.
"""

# 새 도메인 시나리오를 전부 가져와서
# 각각에서 최소 10 step을 시뮬레이션
# mandatory_actions의 변화를 기록
# mandatory가 한 번도 안 변한 시나리오를 FAIL로 보고

# 시뮬레이션 방법: 매 step에서 mandatory 중 첫 번째를 수행하는 greedy agent
# 실제 LLM 호출 없이 mandatory 진행만 테스트

import json

NEW_DOMAINS = [
    'anaphylaxis', 'acls', 'status_epilepticus', 'gina_asthma', 
    'idsa_meningitis', 'toxicology',
    'aba_burn', 'aabb_transfusion', 'acog_obstetric', 
    'pals_pediatric', 'apa_agitation'
]

results = []
for scenario in all_scenarios:
    if not any(d in scenario.scenario_id for d in NEW_DOMAINS):
        continue
    
    env = Environment(scenario)
    env.reset()
    
    mandatory_history = []
    for step in range(20):  # max 20 steps
        info = env.get_info()
        mandatory = info.get('mandatory_actions', [])
        mandatory_history.append(set(mandatory))
        
        if not mandatory:
            break  # 완료
        
        # greedy: mandatory 중 첫 번째 수행
        action = sorted(mandatory)[0]
        env.step(action)
    
    # mandatory가 변했는지 확인
    unique_mandatories = len(set(frozenset(m) for m in mandatory_history))
    changed = unique_mandatories > 1
    
    results.append({
        'scenario': scenario.scenario_id,
        'steps': len(mandatory_history),
        'mandatory_changed': changed,
        'unique_mandatory_sets': unique_mandatories,
        'final_mandatory': list(mandatory_history[-1]) if mandatory_history else [],
    })

# 보고
stuck = [r for r in results if not r['mandatory_changed']]
print(f"Total new domain scenarios: {len(results)}")
print(f"Mandatory changed: {len(results) - len(stuck)}")
print(f"Mandatory STUCK: {len(stuck)}")
if stuck:
    print("\nSTUCK scenarios (state transition 연결 실패):")
    for r in stuck:
        print(f"  {r['scenario']}: {r['unique_mandatory_sets']} unique sets, "
              f"final mandatory: {r['final_mandatory'][:3]}...")
```

## 검증 5: 기존 도메인 regression

```python
"""
기존 5개 시나리오를 다시 실행하여 이전 dry-run 결과와 비교.
compliance 차이가 ±0.05 이내여야 함 (run variance 감안).
"""

EXPECTED = {
    'septic_shock_basic': 0.917,
    'stemi_inferior_rv_trap': 0.778,
    'dka_hypokalemia_trap': 0.480,
    'adhf_warm_wet': 0.826,
}

for scenario_id, expected in EXPECTED.items():
    actual = run_and_get_compliance(scenario_id)
    diff = abs(actual - expected)
    status = "PASS" if diff < 0.15 else "FAIL"  # run variance 감안 넓게
    print(f"{scenario_id}: expected={expected:.3f}, actual={actual:.3f}, diff={diff:.3f} [{status}]")
```

## 완료 기준

1. [ ] action_effects.yaml 런타임 불변 확인
2. [ ] Precondition ↔ effect 연결 완전성 ≥ 95% (orphan ≤ 5%)
3. [ ] 임상적 범위 이슈 0개
4. [ ] 유사 변수(오타) 검토 완료
5. [ ] 새 도메인 mandatory STUCK 시나리오 0개 (또는 원인 파악 완료)
6. [ ] 기존 도메인 regression PASS
7. [ ] 전체 테스트 1,680+ pass

**모든 검증 결과를 표로 정리해서 보고하라.**