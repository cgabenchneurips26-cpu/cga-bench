# Option B 구현: Environment에 CPG State Progression 연결

## 목표

현재 Environment는 agent에게 정적 available_actions를 제공하고, CPG engine은 사후 채점 전용이다.
이것을 **매 step마다 CPG engine의 노드 활성 상태에 따라 available_actions가 동적으로 갱신**되도록 변경한다.

## 핵심 원칙

1. **채점 파이프라인은 건드리지 않는다.** 사후 채점(ViolationExtractor, HarmScorer, CGAScore)은 전체 trace를 보고 독립적으로 동작한다. 이번 변경은 agent 인터페이스에만 영향을 준다.
2. **기존 도메인 15개에서 하드코딩 available_actions와 비교 검증한다.** 에피소드 끝까지 누적된 동적 available_actions의 union이 기존 하드코딩과 대략 일치해야 한다 (superset OK, 큰 차이는 graph 누락).
3. **변경 범위를 최소화한다.** Environment.step() + engine 연결부만 수정. ScenarioLoader, PatientGenerator, ConstraintDerivationEngine 등은 변경하지 않는다.

## 현재 아키텍처 파악 (먼저 읽어야 할 파일)

아래 파일들을 **반드시 먼저 전부 읽고** 현재 구조를 파악한 후 구현을 시작하라:

```
# 1. Environment — step(), _get_available_actions(), agent에게 어떻게 action을 전달하는지
#    특히 _get_available_actions()의 하드코딩 구조를 이해
find . -name "*.py" | xargs grep -l "available_actions\|_get_available_actions" | head -20

# 2. CPG Engine — evaluate(), 노드 구조, state 관련 메서드
cpg_model/engine.py

# 3. CPG Graph YAML — 노드 구조, action 정의 위치, preconditions
cpg_model/graphs/ (아무 graph 2개 열어서 구조 파악)

# 4. Scenario Loader — scenario가 engine에 어떻게 연결되는지
cpg_model/scenario_loader.py

# 5. Episode Runner — Environment와 Agent의 interaction loop
find . -name "*.py" | xargs grep -l "def run_episode\|episode_runner" | head -10

# 6. 기존 하드코딩된 available_actions 목록
#    _get_available_actions()에서 domain별로 어떤 action들이 정의되어 있는지 전부 기록
```

## 구현 단계

### Step 1: Engine의 현재 노드 활성화 로직 파악

CPG engine이 이미 가지고 있는 것:
- 노드별 action 정의 (graph YAML에 있음)
- precondition 평가 (state.* 조건)
- evaluate() — 전체 trace를 받아서 violation 판정

없을 수 있는 것 (확인 필요):
- **점진적 노드 활성화**: 현재 state에서 precondition이 만족된 노드들만 반환하는 메서드
- **advance/progress**: agent action 수행 후 state를 업데이트하고 다음 활성 노드를 계산하는 메서드

**확인 후 판단:**
- 이미 있으면 → 바로 Step 2로
- 없으면 → engine에 `get_active_nodes(patient_state)` 메서드 추가

`get_active_nodes(patient_state)` 로직:
```python
def get_active_nodes(self, patient_state: dict) -> list[str]:
    """현재 patient_state에서 precondition이 만족된 노드들을 반환."""
    active = []
    for node in self.graph.nodes:
        if node.preconditions is None:
            active.append(node)  # 무조건 활성 (entry 노드 등)
        elif self._evaluate_preconditions(node.preconditions, patient_state):
            active.append(node)
    return active

def get_available_actions_for_state(self, patient_state: dict) -> set[str]:
    """현재 state에서 활성 노드의 action union을 반환."""
    active_nodes = self.get_active_nodes(patient_state)
    actions = set()
    for node in active_nodes:
        actions.update(node.actions)  # node.actions의 실제 필드명 확인
    return actions
```

### Step 2: Environment.step()에 연결

```python
# Environment.__init__()에서:
self.cpg_engine = CPGEngineFactory.load_from_file(scenario.graph_path)
self.cpg_engine.set_scenario_forbidden_actions(scenario)  # 기존 로직 유지

# Environment.step() 또는 _get_available_actions()에서:
def _get_available_actions(self) -> list[str]:
    # 기존 하드코딩 삭제 (또는 fallback으로 유지)
    current_state = self._get_current_patient_state()  # 이미 있을 것
    dynamic_actions = self.cpg_engine.get_available_actions_for_state(current_state)
    
    # 항상 기본 action 포함 (diagnose, discharge 등 — 현재 하드코딩에서 공통인 것)
    base_actions = {"diagnose", "discharge", "request_consultation"}  # 확인 필요
    
    return sorted(dynamic_actions | base_actions)
```

### Step 3: State Progression

Agent가 action을 수행하면 Environment가 이미 patient state를 업데이트하고 있을 것이다 (vitals 변화, lab 결과 등). 이 업데이트된 state가 다음 step에서 `get_active_nodes()`에 자동 반영되면 별도의 `advance_node()` 호출이 불필요하다.

**확인 포인트**: Environment의 state 업데이트가 CPG graph의 precondition 변수와 연결되는지.
- 예: graph에 `precondition: state.potassium < 3.5`가 있고, Environment에서 lab 결과로 potassium 값이 설정되면 자동 연결
- 연결 안 되면: action 수행 자체를 state 업데이트 트리거로 사용. 예: `administer_insulin` 수행 → `state.insulin_given = true` → insulin 관련 후속 노드 활성화

### Step 4: 검증

#### 4a. 기존 도메인 정합성 (CRITICAL)

```python
# 기존 15개 도메인 각각에서:
# 1. 하드코딩 available_actions 추출
# 2. 에피소드를 끝까지 돌린 후 매 step의 dynamic available_actions를 union
# 3. union과 하드코딩을 비교
# 
# 기대: union ⊇ 하드코딩 (dynamic이 하드코딩을 포함하거나 같아야 함)
# 경고: union ⊂ 하드코딩 (dynamic에 없는데 하드코딩에 있는 action)이면 graph 누락

ORIGINAL_15_SCENARIOS = [
    "septic_shock_basic",
    "stemi_inferior_rv_trap", 
    "dka_hypokalemia_trap",
    "stroke_tpa_eligible",
    "adhf_warm_wet",
    # ... 나머지 10개 추가
]

for scenario in ORIGINAL_15_SCENARIOS:
    hardcoded = get_hardcoded_actions(scenario.domain)
    dynamic_union = run_episode_collect_all_available_actions(scenario)
    
    missing = hardcoded - dynamic_union
    extra = dynamic_union - hardcoded
    
    print(f"{scenario}: missing={len(missing)}, extra={len(extra)}")
    if missing:
        print(f"  MISSING (graph에 추가 필요): {missing}")
    if extra:
        print(f"  EXTRA (engine이 추가 도출): {extra}")
```

#### 4b. 새 도메인 합리성

```python
# 새 도메인 (aabb, aba, acls, 등)에서:
# 매 step의 available_actions 개수가 합리적인지 (최소 3개 이상)
# 에피소드 진행에 따라 action space가 확장되는지
# 에피소드 끝에서 total unique actions ≥ expected_actions의 80%
```

#### 4c. Compliance 비교

```python
# dry-run 5개 시나리오 (sepsis, stemi, dka, stroke, adhf):
# Post-fix compliance와 비교하여 합리적 범위인지
# sepsis: ~1.0 기대
# trap 시나리오: 0.3-0.7 기대 (trap이니까 낮아야 정상)
```

## 주의사항

- **evaluate() 채점 로직은 절대 수정하지 않는다.** 채점은 사후에 전체 trace를 보고 하며, 동적 available_actions와 무관하다.
- **ScenarioLoader, PatientGenerator, ConstraintDerivationEngine은 수정하지 않는다.**
- **하드코딩 _get_available_actions()는 삭제하지 말고 주석 처리하거나 fallback으로 남겨둔다.** 검증 비교에 필요하다.
- **entry 노드에 action이 0개인 graph가 있으면 반드시 수정한다.** Agent에게 빈 action list를 주면 에피소드가 무의미하다.
- **기존 테스트 2,674+개가 모두 통과하는지 확인한다.** `python -m pytest tests/ -x` 실행.
- **companion rules (skip_scenario_generation=true)**: 시나리오는 안 만들지만 derivation 시 forbidden을 추가한다. 이것이 동적 available_actions에 영향을 주는지 확인 (forbidden actions는 available에 포함되되, 수행 시 violation으로 잡혀야 한다).

## 완료 기준

1. [ ] `engine.get_available_actions_for_state(patient_state)` 구현 및 테스트
2. [ ] `Environment.step()`에서 동적 available_actions 사용
3. [ ] 기존 15개 도메인 중 5개 dry-run: 하드코딩 대비 missing < 10%
4. [ ] 새 도메인 5개 dry-run: 매 step available_actions ≥ 3개
5. [ ] 기존 테스트 전체 통과
6. [ ] 전체 688개 시나리오 dry-run (에피소드 없이 초기 available_actions 확인)