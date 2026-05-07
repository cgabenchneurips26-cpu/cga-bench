# 새 도메인 action → _process_action() State Transition 구현

## 배경

CGA-Bench의 Environment._process_action()은 agent action 수행 시 patient state를 업데이트한다.
현재 기존 15개 도메인(sepsis, stemi, dka, stroke, adhf 등)의 action만 처리하고,
새로 추가된 도메인(toxicology, meningitis, anaphylaxis, ACLS, status epilepticus, asthma, burns, transfusion, OB emergency, peds, psych 등)의 action은 처리하지 못한다.

**StateUpdateCoverage = 69.4%** — 나머지 30.6%가 새 도메인 action이다.

## 목표

새 도메인의 action에 대한 state transition을 _process_action()에 추가하여 StateUpdateCoverage ≥ 95%를 달성한다.

## 핵심 원칙

1. **임상적으로 정확해야 한다.** 각 action의 state 변화는 실제 임상 프로토콜을 반영해야 한다. 예: give_vancomycin_iv → state.vancomycin_given = true, state.antibiotic_started = true
2. **기존 도메인을 건드리지 않는다.** 기존 15개 도메인의 _process_action() 로직은 수정하지 않는다.
3. **CPG graph의 precondition과 연결되어야 한다.** Graph YAML의 노드 precondition이 `state.X`를 참조하면, action 수행 시 `state.X`가 업데이트되어야 한다. 이 연결이 없으면 mandatory 동적 진행이 안 된다.

## 작업 순서

### Step 1: 미처리 action 전수 조사

```bash
# 1. 새 도메인의 모든 unique action을 추출
# CPG graph YAML에서 action 필드를 모두 수집
python3 -c "
import yaml, glob, json
all_actions = set()
for f in glob.glob('cpg_model/graphs/*.yaml'):
    with open(f) as fh:
        g = yaml.safe_load(fh)
    for node in g.get('nodes', []):
        for a in node.get('actions', []):
            all_actions.add(a if isinstance(a, str) else a.get('action_id', ''))
print(f'Total unique actions in graphs: {len(all_actions)}')
for a in sorted(all_actions):
    print(a)
"

# 2. _process_action()에서 이미 처리하는 action 추출
# grep 또는 코드 분석으로 현재 if/elif 분기에 있는 action_id를 모두 수집

# 3. diff = graph actions - processed actions = 구현 필요 목록
```

### Step 2: Graph precondition 매핑 추출

**이것이 가장 중요한 단계.** 각 graph YAML에서 노드의 precondition이 어떤 state 변수를 참조하는지 추출한다.

```bash
# 각 graph의 precondition에서 state.* 참조를 추출
python3 -c "
import yaml, glob, re
for f in sorted(glob.glob('cpg_model/graphs/*.yaml')):
    with open(f) as fh:
        g = yaml.safe_load(fh)
    state_refs = set()
    for node in g.get('nodes', []):
        for pre in node.get('preconditions', []):
            refs = re.findall(r'state\.(\w+)', str(pre))
            state_refs.update(refs)
    if state_refs:
        print(f'{f}: {sorted(state_refs)}')
"
```

이 출력을 보면 "action X를 수행하면 state.Y를 True로 설정해야 다음 노드의 precondition state.Y가 만족된다"는 매핑을 만들 수 있다.

### Step 3: Action → State Transition 매핑 작성

매핑을 **데이터로** 정의한다. _process_action()에 수백 줄의 if/elif를 추가하는 대신, 매핑 딕셔너리를 만들어 일괄 처리한다.

```python
# 예시 구조 (실제 action/state 이름은 graph에서 확인)
ACTION_STATE_MAP = {
    # Toxicology
    "assess_decontamination_indication": {
        "state.decontamination_assessed": True,
    },
    "administer_activated_charcoal": {
        "state.charcoal_given": True,
        "state.decontamination_started": True,
    },
    "give_naloxone_iv": {
        "state.naloxone_given": True,
        "state.antidote_administered": True,
    },
    
    # Meningitis
    "give_vancomycin_iv": {
        "state.vancomycin_given": True,
        "state.antibiotic_started": True,
    },
    "give_ceftriaxone_iv": {
        "state.ceftriaxone_given": True,
        "state.antibiotic_started": True,
    },
    "perform_lumbar_puncture": {
        "state.lp_done": True,
        "state.csf_available": True,
    },
    
    # Anaphylaxis
    "give_epinephrine_im": {
        "state.epinephrine_given": True,
        "state.anaphylaxis_treated": True,
    },
    
    # ACLS
    "start_cpr": {
        "state.cpr_initiated": True,
    },
    "defibrillate": {
        "state.defibrillation_done": True,
    },
    "give_epinephrine_iv_acls": {
        "state.epinephrine_given": True,
    },
    "give_amiodarone_iv": {
        "state.amiodarone_given": True,
    },
    
    # ... 나머지 도메인도 동일 패턴
}
```

### Step 4: _process_action()에 통합

```python
def _process_action(self, action_id, action_params):
    # 기존 도메인 로직 (수정 안 함)
    if action_id in self._existing_handlers:
        return self._existing_handlers[action_id](action_params)
    
    # 새 도메인: 데이터 기반 state 업데이트
    if action_id in ACTION_STATE_MAP:
        for state_key, value in ACTION_STATE_MAP[action_id].items():
            self._set_state(state_key, value)
        return ActionResult(success=True, action_id=action_id)
    
    # 미인식 action: generic 처리
    # action 수행은 성공으로 처리하되, state 변경은 최소한
    self._set_state(f"state.{action_id}_done", True)
    return ActionResult(success=True, action_id=action_id)
```

### Step 5: 검증

#### 5a. Precondition 연결 검증

```python
# 모든 graph에서:
# 1. 노드 A의 action X를 수행
# 2. 노드 B의 precondition이 state.Y를 요구
# 3. action X의 STATE_MAP에 state.Y가 포함되어 있는지 확인
# 
# 누락이 있으면 mandatory 진행이 막힘

for graph in all_graphs:
    for node_B in graph.nodes:
        for precond in node_B.preconditions:
            state_var = extract_state_var(precond)  # e.g., "state.antibiotic_started"
            # 이 state_var를 설정하는 action이 ACTION_STATE_MAP에 있는지 확인
            producers = [a for a, smap in ACTION_STATE_MAP.items() if state_var in smap]
            if not producers:
                print(f"WARNING: {graph.name}/{node_B.id} needs {state_var} but no action sets it")
```

#### 5b. StateUpdateCoverage 재측정

```bash
# 기존 테스트 재실행 — StateUpdateCoverage ≥ 95% 확인
python -m pytest tests/test_exit_criteria/ -k "StateUpdateCoverage" -v
```

#### 5c. 새 도메인 dry-run

```python
# 새 도메인 대표 시나리오 5개에서:
# 1. 에피소드 끝까지 mandatory 변화 로깅
# 2. 노드 진행이 실제로 일어나는지 확인
# 3. compliance > 0인지 확인 (이전에 구조적으로 0이었던 것이 개선되었는지)

NEW_DOMAIN_SCENARIOS = [
    "aabb_t_basic_cardiac_liberal_threshold",  # Transfusion
    "aba_burn_basic",                           # Burns (이름 확인 필요)
    "acls_cardiac_arrest_basic",                # ACLS
    "idsa_meningitis_basic",                    # Meningitis
    "toxicology_basic",                         # Toxicology
]
```

#### 5d. 기존 도메인 regression

```python
# 기존 5개 시나리오 재실행 — compliance가 이전 dry-run과 동일한지
# sepsis ≥ 0.9, stemi ~0.78, dka ~0.48, adhf ~0.83
```

#### 5e. 전체 테스트

```bash
python -m pytest tests/ -x --tb=short
# 1,680+ pass, StateUpdateCoverage 관련 실패 해소 확인
```

## Vitals/Lab 변화 처리

일부 action은 단순 boolean이 아니라 수치 변화를 일으킨다:
- give_iv_fluid → state.volume_status 변화, blood_pressure 변화
- give_vasopressor → state.map 증가
- intubate → state.airway_secured = true, state.spo2 변화

**이 수준의 정밀도는 이번 scope에 포함하지 않는다.**
논문 Limitation에 "Patient state transitions follow a deterministic state machine"이 이미 있다.
boolean flag 수준의 state 업데이트면 노드 진행에 충분하다.
수치 변화가 precondition에 있으면 (예: `state.map > 65`) 해당 값만 합리적 기본값으로 설정:

```python
"give_vasopressor": {
    "state.vasopressor_given": True,
    "state.map": 70,  # 합리적 반응 값
}
```

## 주의사항

- **ACTION_STATE_MAP은 별도 파일(e.g., action_state_map.yaml)로 분리하라.** 코드에 임베드하면 유지보수 불가.
- **graph YAML의 precondition state 변수와 ACTION_STATE_MAP의 key가 정확히 일치해야 한다.** 오타 한 글자로 노드 진행이 막힘.
- **generic fallback (`state.{action_id}_done = True`)은 최후 수단이다.** graph precondition이 이 패턴을 참조하지 않으므로 노드 진행에 도움이 안 된다. 가능한 한 명시적 매핑을 우선.
- **반복 가능 action(assess_vitals, check_blood_pressure 등)은 ACTION_STATE_MAP에서 별도 표시하라.** 이 action들은 available에서 제거하면 안 된다.
- **기존 _process_action() 로직의 if/elif 분기를 삭제하지 않는다.** 새 매핑은 기존 분기에 해당하지 않는 action에 대해서만 적용.

## 완료 기준

1. [ ] 미처리 action 전수 목록 작성
2. [ ] Graph precondition → state 변수 매핑 추출
3. [ ] ACTION_STATE_MAP 완성 (YAML 파일)
4. [ ] _process_action()에 데이터 기반 처리 통합
5. [ ] StateUpdateCoverage ≥ 95%
6. [ ] 새 도메인 5개 시나리오 dry-run — mandatory 진행 + compliance > 0
7. [ ] 기존 5개 시나리오 regression — compliance 변동 없음
8. [ ] 전체 테스트 pass