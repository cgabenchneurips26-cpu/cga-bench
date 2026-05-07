# Phase 1: P0 Core (ENG-00 → 05)

이 지시를 따라 ENG-00부터 ENG-05까지 순서대로 구현해라.

## 공통 규칙

- 각 태스크 시작 시 **수정 대상 파일을 반드시 먼저 읽어라** (cat/view). 기존 코드 구조를 모르면 엉뚱한 걸 만든다.
- 게이트 테스트 실패 시 에러를 읽고 수정, **최대 3회 재시도**
- 게이트 통과 후: `git add -A && git commit -m "[ENG-XX] 구현 완료" && git push origin HEAD`
- 게이트 3회 실패: `git add -A && git commit -m "[ENG-XX] WIP" && git push origin HEAD` 후 **멈춰라. 다음 태스크로 가지 마라.**
  - ENG-00~02는 기반이다. 여기서 실패하면 나머지가 전부 깨진다.
  - ENG-03부터는 WIP 커밋 후 다음으로 넘어가도 된다.
- 필요한 패키지가 없으면 `pip install` 해라.

---

## ENG-00. 공통 스키마 계약 고정

**먼저 읽을 것**:
- `docs/specs/engineering_spec.md`의 ENG-00 섹션
- `cga_bench/cpg_model/schemas/` 아래 모든 파일
- `cga_bench/assessor_core/event_log.py`
- `cga_bench/eval_harness/scenario_loader.py`
- `cga_bench/eval_harness/metrics_reporter.py`

**작업**:
기존 스키마가 있으면 pydantic v2 BaseModel로 리팩터링하고, 없으면 신설해라.

7개 스키마:
```python
# cpg_model/schemas/contracts.py (또는 기존 파일에 추가)

class ConstraintOutput(BaseModel):
    mandatory_actions: list[str]
    forbidden_actions: list[str]
    deadlines: dict[str, float]          # action_id → seconds
    required_prior_actions: dict[str, list[str]]  # action_id → [prior_action_ids]

class ActionEvent(BaseModel):
    model_config = ConfigDict(frozen=True)
    timestamp: float                     # epoch seconds
    action_id: str
    normalized_action_id: str | None = None
    tool_call: str | None = None
    observation: str | None = None
    metadata: dict = {}

class ViolationType(str, Enum):
    OMISSION = "OMISSION"
    COMMISSION = "COMMISSION"
    TIMING = "TIMING"
    SEQUENCE = "SEQUENCE"
    DEVIATION = "DEVIATION"

class ViolationRecord(BaseModel):
    violation_type: ViolationType
    action_id: str
    timestamp: float | None = None
    severity: int = 1                    # 1~5
    source_guideline: str = ""
    source_section: str = ""
    source_page: str = ""
    source_quote: str = ""

class ScoreReport(BaseModel):
    final_score: float
    action_coverage: float               # Track A
    compliance_score: float              # Track B
    peak_risk: float
    aggregate_risk: float
    violations_by_type: dict[str, int]
    sub_scores: dict[str, float]         # C1~C5
    safety_gate: bool

class EpisodeLog(BaseModel):
    episode_id: str
    events: list[ActionEvent]
    metadata: dict = {}

class ExternalParseResult(BaseModel):
    source_benchmark: str
    parsed_scenario: dict
    parsed_episode_log: EpisodeLog | None = None
    domain: str = ""
    parse_warnings: list[str] = []

class ExperimentConfig(BaseModel):
    experiment_name: str
    scenarios: list[str]
    agents: list[str]
    budget: dict = {}
    num_runs: int = 1
    seed: int | None = None
```

위는 **참고 뼈대**다. 기존 코드의 필드명/구조와 맞지 않으면 기존 것에 맞춰 조정해라. 핵심은 pydantic v2 + validation이 동작하는 것이다.

**테스트**: `tests/test_schemas/test_contracts.py` 작성
- 각 스키마 valid input → round-trip (model → json → model) 성공
- 각 스키마 invalid input → ValidationError
- `tests/fixtures/schema_samples/` 에 샘플 JSON 1개씩

**게이트**: `PYTHONPATH=. pytest tests/test_schemas/ -v`

---

## ENG-01. CPG 엔진 출력 계약 완성

**먼저 읽을 것**:
- `docs/specs/engineering_spec.md`의 ENG-01 섹션
- `cga_bench/cpg_engine/engine.py` — evaluate() 함수의 현재 시그니처와 반환값
- `cga_bench/cpg_engine/reachability.py`
- `cga_bench/cpg_engine/applicability.py`
- `cga_bench/cpg_engine/temporal_constraints.py`
- `cga_bench/cpg_engine/stepper.py`
- `cga_bench/cpg_model/graphs/` — YAML 파일 1~2개만 구조 파악용으로

**작업**:
- engine.evaluate()가 ENG-00의 `ConstraintOutput`을 반환하도록 수정 (기존 반환 형태를 ConstraintOutput으로 래핑하는 것으로 충분할 수 있다)
- 각 guideline graph에 대해 snapshot 테스트 추가:
  - 예시 patient_state를 만들고 evaluate() 호출
  - 결과를 `tests/snapshots/<graph_id>.json`으로 저장
  - 테스트에서 JSON 비교

**게이트**: `PYTHONPATH=. pytest tests/test_engine/ -v`

---

## ENG-02. EpisodeLog와 상태 축소 파이프라인

**먼저 읽을 것**:
- `cga_bench/assessor_core/event_log.py`
- `cga_bench/assessor_core/state_reducer.py`
- `cga_bench/assessor_core/clinical_state_extractor.py`

**작업**:
- ActionEvent가 frozen인지 확인. 아니면 `model_config = ConfigDict(frozen=True)` 추가.
- CompletedActions 정렬: timestamp 기준 stable sort.
- 시간 정규화 유틸:
```python
def normalize_timestamp(value: float, unit: str = "seconds") -> float:
    """relative minutes → epoch seconds 변환. 내부 표준은 seconds."""
    if unit == "minutes":
        return value * 60.0
    return value
```
- tests/test_assessor/test_event_log.py 작성:
  - frozen 불변성 (수정 시도 → 에러)
  - 정렬 안정성 (동일 timestamp 순서 보존)
  - 초/분 혼입 정규화

**게이트**: `PYTHONPATH=. pytest tests/test_assessor/ -v -k "event_log or state_reducer or time"`

---

## ENG-03. 위반 추출기 5종 정확도

**먼저 읽을 것**:
- `cga_bench/assessor_core/violations.py` — 현재 extract 로직 전체
- `cga_bench/assessor_core/dka_violation_detector.py`
- `cga_bench/assessor_core/action_normalizer.py`
- ENG-00에서 만든 ViolationType enum

**작업**:
- violations.py에서 5종 추출이 타입별로 분리되어 있는지 확인. 안 되어 있으면 리팩터링.
- `tests/test_assessor/test_violations.py`에 micro fixture:

```python
# 각 위반 유형별 최소 로그 예시 (기존 코드 구조에 맞게 조정할 것)

# OMISSION: mandatory에 "order_lab_lactate"가 있는데 episode에 없음
# COMMISSION: forbidden에 "give_nitrate"가 있는데 episode에 있음
# TIMING: deadline 60분인데 행동이 61분에 수행됨 (경계: 59분은 통과)
# SEQUENCE: required_prior "blood_culture" before "antibiotics"인데 역순
# DEVIATION: 정의된 allowed_actions에 없는 행동 수행
```

**게이트**: `PYTHONPATH=. pytest tests/test_assessor/test_violations.py -v`

---

## ENG-04. HarmScorer / DualTrack / Safety Gate

**먼저 읽을 것**:
- `cga_bench/assessor_core/harm_scorer.py` — compute_score의 현재 수식
- `cga_bench/assessor_core/dual_track_evaluator.py`
- `cga_bench/assessor_core/expected_actions_guard.py`
- `cga_bench/assessor_core/episode_risk_scorer.py`

**작업**:
- HarmScorer 수식을 docstring에 명시
- DualTrack = Track A × Track B × Safety Gate 확인/고정
- sub_scores(C1-C5) 각각을 개별 메서드로 분리
- `pip install hypothesis` 후 monotonicity 테스트:

```python
from hypothesis import given, strategies as st

@given(base_severity=st.integers(min_value=1, max_value=4))
def test_monotonicity_severity(base_severity):
    """severity 1단계 증가 → 점수 감소 또는 동일"""
    score_low = compute_with_severity(base_severity)
    score_high = compute_with_severity(base_severity + 1)
    assert score_high.final_score <= score_low.final_score
```

- Safety Gate 테스트: 심각 위반(severity=5) 삽입 → safety_gate=False, final_score 대폭 하락

**게이트**: `PYTHONPATH=. pytest tests/test_assessor/ -v -k "scorer or dual_track or safety or monoton"`

---

## ENG-05. 골든 테스트 12쌍

**먼저 읽을 것**:
- `docs/specs/verification_framework.md`의 "A/B 골든 테스트" 섹션
- `cga_bench/cpg_model/graphs/` — 실제 YAML 구조 파악
- `configs/scenarios/` — 시나리오 YAML 구조 파악

**작업**:
`tests/test_golden/` 신설. **핵심: 기존 cpg_model/graphs/ YAML과 configs/scenarios/ YAML의 실제 구조를 그대로 따라야 한다.** 형식을 추측하지 마라, 기존 파일을 복사해서 수정해라.

conftest.py:
```python
def run_case(case_dir: Path) -> dict:
    """기존 engine/violations/scorer 파이프라인을 그대로 호출"""
    # graph.yaml 로드 → engine 생성
    # scenario.yaml 로드 → patient_state 구성
    # episode.json 로드 → EpisodeLog
    # engine.evaluate → violations → score
    ...

def assert_ab_monotonic(a_result, b_result, expected_violation_type: str):
    assert b_result["score"]["final_score"] < a_result["score"]["final_score"]
    diff = find_new_violations(a_result["violations"], b_result["violations"])
    assert len(diff) >= 1
    assert any(v.violation_type.value == expected_violation_type for v in diff)
```

필수 6쌍 (나머지 6쌍은 유사 패턴으로 채워라):
1. sepsis/hour1_sequence — 순서 A/B → SEQUENCE
2. sepsis/antibiotics_timing — 45min vs 75min → TIMING
3. chest_pain/ecg_10min — 8min vs 15min → TIMING
4. dka/potassium_before_insulin — 순서 A/B → SEQUENCE
5. aki/nephrotoxin_commission — 미투여 vs 투여 → COMMISSION
6. stroke/tpa_eligibility — 2h vs 6h → DEVIATION 또는 COMMISSION

**게이트**: `PYTHONPATH=. pytest tests/test_golden/ -v`

---

## Phase 1 완료 체크

모든 태스크 커밋/푸시 후, 최종 확인:

```bash
PYTHONPATH=. pytest tests/test_schemas/ tests/test_engine/ tests/test_assessor/ tests/test_golden/ -v --tb=short
```

이것까지 통과하면:
```bash
git add -A && git commit -m "[Phase1] P0 Core 전체 게이트 통과" && git push origin HEAD
```
