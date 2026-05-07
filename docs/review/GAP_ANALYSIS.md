# CGA-Bench 스펙-구현 갭 분석

## 분석 범위
- 스펙 기준 문서: `docs/specs/docs_specs_engineering_spec.md`, `docs/specs/docs_specs_verification_framework.md`, `docs/CGA_BENCH_ARCHITECTURE_GUIDE.md`
- 구현 검토 범위: `cpg_model/`, `cpg_engine/`, `assessor_core/`, `env/adapters/`, `eval_harness/`, `tests/`
- 실행 근거:
  - ACL 통일 후 `pytest tests/test_engine/test_engine_snapshots.py tests/test_external/test_adapter_contracts.py tests/test_guards/test_scoring_policy_enhanced.py -q` 결과: 65개 전부 통과

## 한줄 결론
- 현재 코드는 벤치마크의 핵심 뼈대는 갖췄지만, 제출 전 반드시 정리해야 할 구조적 갭은 `점수 스키마 이중화`, `어댑터 인터페이스 불일치`, `violation boundary 비배타성`이다.
- ACL 이슈는 이번 턴에서 해소됐고, 핵심 테스트 65개가 모두 통과했다. 따라서 지금부터의 논점은 권한이 아니라 설계 일관성과 논문 방어력이다.

## 요약 테이블
| 카테고리 | ✅ | ⚠️ | ❌ | ➕ |
|---------|---|---|---|---|
| A. DualTrack 스코링 | 2 | 2 | 0 | 1 |
| B. Violation 타입 체계 | 3 | 2 | 0 | 0 |
| C. 어댑터 구현 | 3 | 3 | 0 | 1 |
| D. 데이터 파이프라인 | 1 | 1 | 1 | 1 |
| E. 평가 파이프라인 | 3 | 2 | 0 | 1 |

## 상세 분석

### A. DualTrack 스코링 ⚠️ 최종 점수 결합
- **스펙 내용**: Track A, Track B, Safety Gate를 고정된 계약으로 결합해야 함.
- **구현 현황**: `assessor_core/dual_track_evaluator.py:98-183`에서 `final_score = 0 if high_severity > 0 else A * B`를 구현함. Safety Gate도 `:150-156`에 존재함.
- **차이점**: 점수 계산은 구현되어 있으나 최종 공통 스키마가 분리되어 있음. `cpg_model/schemas/contracts.py:42-50`의 `ScoreReport`는 `final_score`, `action_coverage`, `safety_gate`를 요구하지만, 실제 주력 점수 모델인 `cpg_model/schemas/base.py:316-352`의 `CGAScore`에는 이 필드들이 없음.
- **영향도**: 보고 포맷이 실행 경로별로 달라져 외부 벤치마크/리더보드/재현 번들에서 일관된 JSON 계약을 보장하기 어렵다.
- **관련 코드**: `assessor_core/dual_track_evaluator.py:98-183`, `cpg_model/schemas/contracts.py:42-50`, `cpg_model/schemas/base.py:316-352`

### A. DualTrack 스코링 ✅ Safety Gate
- **스펙 내용**: 심각 위반 발생 시 최종 점수를 강하게 낮추거나 0으로 게이트해야 함.
- **구현 현황**: `assessor_core/dual_track_evaluator.py:121-156`에서 `severe`/`catastrophic` 위반 수를 세고, 임계치 이상이면 `final_score = 0.0`.
- **차이점**: 없음.
- **영향도**: 안전 중심 평가라는 벤치마크 설계 의도가 살아 있음.
- **관련 코드**: `assessor_core/dual_track_evaluator.py:121-156`

### A. DualTrack 스코링 ✅ 민감도 분석 보조 산출물
- **스펙 내용**: 주 계산식은 고정하되 분석 가능한 부가 지표가 있으면 유리함.
- **구현 현황**: `assessor_core/dual_track_evaluator.py:69-96`에서 F1/F2/산술평균/곱셈식을 별도 계산함.
- **차이점**: 스펙 필수는 아니나 보조 분석용으로 유용함.
- **영향도**: 논문 부록이나 ablation 설명에는 도움이 된다.
- **관련 코드**: `assessor_core/dual_track_evaluator.py:69-96`

### A. DualTrack 스코링 ⚠️ overspecific fairness guard 연결 범위
- **스펙 내용**: `expected_actions_guard.py`와 CPG overspecific fairness guard를 연결해야 함.
- **구현 현황**: `dual_track_evaluator`에는 `modular_compliance` floor가 있음 (`assessor_core/dual_track_evaluator.py:135-148`).
- **차이점**: guard 자체는 있으나 공통 `ScoreReport`와 통합된 고정 산출물에서 직접 드러나지 않고, 현재 핵심 테스트 통과만으로는 모든 실행 경로에서의 일관 적용까지 완전히 입증되지는 않았다.
- **영향도**: 외부 벤치마크 통합 시 overspecific 보정이 적용되는 경로와 적용되지 않는 경로가 혼재할 가능성이 있다.
- **관련 코드**: `assessor_core/dual_track_evaluator.py:135-148`, `tests/test_guards/test_scoring_policy_enhanced.py`

### A. DualTrack 스코링 ➕ divergence/sensitivity 메타데이터
- **스펙 내용**: 필수 아님.
- **구현 현황**: `divergence_type`, `sensitivity`가 결과에 포함됨.
- **차이점**: 스펙 외 확장.
- **영향도**: 분석에는 유익하지만 표준 계약을 더 복잡하게 만든다.
- **관련 코드**: `assessor_core/dual_track_evaluator.py:158-182`

### B. Violation 타입 체계 ✅ 5종 분리 구현
- **스펙 내용**: OMISSION, COMMISSION, TIMING, SEQUENCE, DEVIATION을 분리 검출.
- **구현 현황**: `assessor_core/violations.py:123-175`에서 commission, deviation, sequence, timing, omission을 순차 검사함.
- **차이점**: 없음.
- **영향도**: 5종 taxonomy의 기본 형태는 구현되어 있다.
- **관련 코드**: `assessor_core/violations.py:123-175`

### B. Violation 타입 체계 ✅ 가중치 정의
- **스펙 내용**: 타입별 severity/weight 정책이 있어야 함.
- **구현 현황**: `assessor_core/episode_risk_scorer.py:63-69`에서 타입별 가중치가 정의되어 있음.
- **차이점**: 스펙 문서에 근거 출처까지 요구했지만, 현재 구현은 코드 상수 수준이다.
- **영향도**: 점수 재현은 가능하나 임상적 정당화는 약하다.
- **관련 코드**: `assessor_core/episode_risk_scorer.py:63-69`

### B. Violation 타입 체계 ✅ 골든 테스트 존재
- **스펙 내용**: 유형별 골든 케이스가 필요함.
- **구현 현황**: `tests/test_golden/conftest.py:161-180`, `tests/test_golden/test_golden_pairs.py:22-148`에서 A/B 페어와 스냅샷을 검증함.
- **차이점**: 스펙이 요구한 12쌍 이상 골든 세트 방향과 대체로 일치.
- **영향도**: 리팩터링 회귀 탐지 기반은 마련되어 있다.
- **관련 코드**: `tests/test_golden/conftest.py:161-180`, `tests/test_golden/test_golden_pairs.py:22-148`

### B. Violation 타입 체계 ⚠️ 경계 규칙의 MECE 불명확
- **스펙 내용**: 하나의 행위가 복수 타입에 걸칠 때 처리 규칙이 명세되어야 함.
- **구현 현황**: `assessor_core/violations.py:123-175`는 검사 순서가 commission → deviation → sequence → timing → omission이다.
- **차이점**: 배타 규칙이 없다. 예를 들어 action이 허용 집합 밖이면서 선행 조건도 위반하면 deviation과 sequence가 동시에 추가될 수 있다.
- **영향도**: 논문에서 “5종 위반이 MECE인가”라는 질문에 방어가 어렵고, aggregate risk가 중복 계산될 수 있다.
- **관련 코드**: `assessor_core/violations.py:123-175`, `assessor_core/violations.py:315-354`, `assessor_core/violations.py:431-478`

### B. Violation 타입 체계 ⚠️ omission 판정이 에피소드 종결 시점 중심
- **스펙 내용**: 누락과 지연의 경계가 명확해야 함.
- **구현 현황**: omission은 종료 후 최종 상태에서 한 번에 검사함 (`assessor_core/violations.py:163-175`, `:510-520` 이후).
- **차이점**: 중간 시점에서 “이미 실패한 누락”을 언제 확정하는지 명시가 약하다.
- **영향도**: 온라인 평가나 partial episode 평가에서는 판정이 흔들릴 수 있다.
- **관련 코드**: `assessor_core/violations.py:163-175`, `assessor_core/violations.py:510-520`

### C. 어댑터 구현 ⚠️ 공통 인터페이스가 스펙 계약과 다름
- **스펙 내용**: `load_raw_case()`, `parse_to_scenario()`, `parse_to_episode_log()`, `detect_domain()`, `normalize_actions()` 계약이 필요함.
- **구현 현황**: 실제 `BaseAdapter`는 `load_patient()`, `convert_action()`, `convert_action_log()`, `adapt_episode()`를 추상 메서드로 둠.
- **차이점**: 스펙에서 요구한 공통 어댑터 인터페이스와 메서드 시그니처가 다르다.
- **영향도**: adapter interchangeability가 약하고, 스펙 기반 contract test를 바로 걸기 어렵다.
- **관련 코드**: `env/adapters/base_adapter.py:45-107`, `docs/specs/docs_specs_engineering_spec.md`

### C. 어댑터 구현 ✅ MedAgentBench 어댑터 존재
- **스펙 내용**: MedAgentBench 포맷 변환 지원.
- **구현 현황**: `env/adapters/medagentbench_adapter.py:203-260` 이하에 FHIR 기반 어댑터가 구현되어 있음.
- **차이점**: 존재 자체는 충족.
- **영향도**: FHIR interaction 기반 외부 평가 연결점은 있음.
- **관련 코드**: `env/adapters/medagentbench_adapter.py:203-260`

### C. 어댑터 구현 ✅ MedChain 어댑터 존재
- **스펙 내용**: MedChain sequential workflow 변환 지원.
- **구현 현황**: `env/adapters/medchain_adapter.py:82-239`에서 5-stage workflow를 파싱함.
- **차이점**: 존재 자체는 충족.
- **영향도**: 순차 의사결정 평가 확장성에는 긍정적이다.
- **관련 코드**: `env/adapters/medchain_adapter.py:82-239`

### C. 어댑터 구현 ✅ AgentClinic/외부 normalize 테스트 존재
- **스펙 내용**: 계약 테스트 필요.
- **구현 현황**: `tests/test_external/test_adapter_contracts.py:1-226`가 `NormalizedEpisode` 중심 테스트를 가짐.
- **차이점**: 다만 `env/adapters`가 아니라 `semantic_layer.external.*` 중심이며, 테스트 대상 계약이 스펙의 `ExternalParseResult`보다 느슨하다.
- **영향도**: adapter smoke test는 있으나 고정 계약 보장은 약함.
- **관련 코드**: `tests/test_external/test_adapter_contracts.py:1-226`

### C. 어댑터 구현 ⚠️ 테스트 경로와 실서비스 경로가 이원화
- **스펙 내용**: 어댑터 계약이 단일해야 함.
- **구현 현황**: `env/adapters/*`와 `semantic_layer.external.*`가 병존하고, 테스트는 후자를 더 많이 사용함.
- **차이점**: 실제 공통 어댑터 표준이 두 계층으로 분산되어 있다.
- **영향도**: 새 데이터셋 통합 시 어느 경로가 canonical인지 불명확하다.
- **관련 코드**: `env/adapters/base_adapter.py:45-107`, `tests/test_external/test_adapter_contracts.py:12-27`

### C. 어댑터 구현 ✅ 계약 테스트 실행 가능
- **스펙 내용**: 계약 테스트는 안정적으로 실행 가능해야 함.
- **구현 현황**: ACL 통일 후 `tests/test_external/test_adapter_contracts.py`가 정상 실행되며 통과했다.
- **차이점**: 현재 기준으로는 실행 가능성 문제는 해소되었다.
- **영향도**: adapter regression을 CI에서 다시 잡을 수 있다.
- **관련 코드**: `tests/test_external/test_adapter_contracts.py`, `scenario_engine/environment.py`

### C. 어댑터 구현 ➕ ArchEHR-QA 어댑터
- **스펙 내용**: review 지시에는 없었음.
- **구현 현황**: `env/adapters/archehr_qa_adapter.py:83-240`에 별도 어댑터가 존재한다.
- **차이점**: 스펙 외 확장.
- **영향도**: evidence-grounded QA 축 확장에는 도움되지만, 메인 CGA workflow와 직접 비교 가능한지는 별도 검증이 필요하다.
- **관련 코드**: `env/adapters/archehr_qa_adapter.py:83-240`

### D. 데이터 파이프라인 ❌ MIMIC-IV-ED 전용 로더/전처리기 부재
- **스펙 내용**: MIMIC-IV-ED, ArchEHR-QA, MedGUIDE 파이프라인 점검.
- **구현 현황**: 현 저장소에서는 MIMIC-IV-ED 전용 로더보다 문서상 MIMICEL/XES 스트레스 입력 계획이 더 두드러진다.
- **차이점**: 직접적인 `MIMIC-IV-ED` 로더/전처리기 구현 증거를 찾지 못했다.
- **영향도**: 데이터셋 커버리지 주장과 구현 커버리지 사이에 갭이 있다.
- **관련 코드**: `docs/specs/docs_specs_expansion_proposal.md`, `docs/specs/docs_specs_verification_framework.md`

### D. 데이터 파이프라인 ✅ ArchEHR-QA 어댑터
- **스펙 내용**: 외부 데이터셋 로더/전처리기 필요.
- **구현 현황**: `env/adapters/archehr_qa_adapter.py:120-219`에 데이터 존재 확인, XML 파싱, 답안 키 로딩이 구현되어 있다.
- **차이점**: 구현은 있으나 QA 스타일이라 workflow adherence와 직접 동일하지는 않다.
- **영향도**: evidence-grounding 축은 지원하지만 치료 workflow 평가와는 별도다.
- **관련 코드**: `env/adapters/archehr_qa_adapter.py:120-219`

### D. 데이터 파이프라인 ⚠️ MedGUIDE는 설정/registry 중심
- **스펙 내용**: 데이터셋 로더/전처리기 구현 필요.
- **구현 현황**: `configs/external_datasets.yaml:37-38`, `semantic_layer/external/registry.py` 및 테스트에는 MedGUIDE 흔적이 있으나 `env/adapters/medguide_*` 구현은 보이지 않는다.
- **차이점**: derived/static benchmark support는 있으나 env adapter 수준 구현은 불완전하다.
- **영향도**: 논문에서 “MedGUIDE integrated”라고 주장하면 현재는 PARTIAL이 적절하다.
- **관련 코드**: `configs/external_datasets.yaml:37-38`, `semantic_layer/external/pseudo_episode.py:1-3`

### D. 데이터 파이프라인 ➕ data_release 패키지
- **스펙 내용**: review 지시의 직접 항목은 아님.
- **구현 현황**: `data_release/v1.0/export_data.py`, `data_release/v1.0/croissant.json` 등 릴리스 번들이 존재함.
- **차이점**: 스펙 외 재현성 지원 자산.
- **영향도**: NeurIPS D&B 제출에는 플러스 요소다.
- **관련 코드**: `data_release/v1.0/export_data.py`, `data_release/v1.0/croissant.json`

### E. 평가 파이프라인 ✅ E2E 하네스와 후처리 파이프라인
- **스펙 내용**: 입력 → 추론 → 스코어링 → 리포트 파이프라인 필요.
- **구현 현황**: `eval_harness/runner.py`, `eval_harness/pipeline.py:1-152`에 runner, XES export, LTL 검증, LLM judge, pathway mining이 정리되어 있다.
- **차이점**: 기본 파이프라인은 존재한다.
- **영향도**: 실험 실행기 수준의 구조는 충분히 갖춰져 있다.
- **관련 코드**: `eval_harness/pipeline.py:1-152`, `eval_harness/runner.py`

### E. 평가 파이프라인 ✅ 엔진 snapshot 검증
- **스펙 내용**: 모든 guideline graph에 snapshot 테스트 필요.
- **구현 현황**: `tests/test_engine/test_engine_snapshots.py:15-233`가 14개 그래프를 대상으로 snapshot을 수행한다.
- **차이점**: 존재 자체는 충족.
- **영향도**: 엔진 regression 방어선은 적절하다.
- **관련 코드**: `tests/test_engine/test_engine_snapshots.py:15-233`

### E. 평가 파이프라인 ✅ 재현성 환경 스냅샷
- **스펙 내용**: 환경/seed/결과 메타데이터를 저장해야 함.
- **구현 현황**: `eval_harness/runner.py:566-595`에서 environment snapshot과 주요 config를 함께 저장한다.
- **차이점**: `reports/<date>/<gitsha>/` 경로 고정 여부는 확인되지 않았다.
- **영향도**: 재현성 요구의 상당 부분은 충족한다.
- **관련 코드**: `eval_harness/runner.py:566-595`

### E. 평가 파이프라인 ✅ 핵심 테스트 실행 가능
- **스펙 내용**: 핵심 테스트는 안정적으로 돌아야 함.
- **구현 현황**: ACL 통일 후 `tests/test_engine/test_engine_snapshots.py`, `tests/test_external/test_adapter_contracts.py`, `tests/test_guards/test_scoring_policy_enhanced.py`가 합계 65개 전부 통과했다.
- **차이점**: 이전 권한 이슈는 운영 문제였고 현재는 해소되었다.
- **영향도**: 최소 핵심 smoke/contract/regression 범위는 재현 가능 상태로 돌아왔다.
- **관련 코드**: `tests/test_engine/test_engine_snapshots.py:215-233`, `tests/test_external/test_adapter_contracts.py`, `tests/test_guards/test_scoring_policy_enhanced.py`

### E. 평가 파이프라인 ⚠️ 결과 스키마 이중화
- **스펙 내용**: 보고서 JSON 구조 고정.
- **구현 현황**: `contracts.ScoreReport`와 `base.CGAScore`가 공존하고 필드 셋이 다르다.
- **차이점**: canonical report schema가 단일하지 않다.
- **영향도**: 분석 스크립트와 외부 소비자가 경로별로 다른 필드를 처리해야 한다.
- **관련 코드**: `cpg_model/schemas/contracts.py:42-50`, `cpg_model/schemas/base.py:316-352`

### E. 평가 파이프라인 ➕ XES/LTL/LLM-Judge/Pathway mining
- **스펙 내용**: 일부는 선택 사항.
- **구현 현황**: post-scoring pipeline에서 opt-in 기능으로 제공된다.
- **차이점**: 스펙 최소 요구를 넘어선 확장.
- **영향도**: 논문 부록과 분석력 강화에는 유리하다.
- **관련 코드**: `eval_harness/pipeline.py:1-152`

## necessity를 방어하려면 필요한 증거
- 동일 시나리오에서 기존 benchmark score는 높지만 CGA-Bench에서는 timing/sequence/safety 위반이 드러나는 사례를 보여줘야 한다.
- 반대로 기존 benchmark에서 낮게 보이지만 CGA-Bench fairness guard로 과도한 감점을 막는 사례도 필요하다.
- 즉, necessity는 개념 설명이 아니라 `기존 평가로는 오판되던 사례가 CGA-Bench에서 바로잡힌다`는 before/after 증거로 방어해야 한다.

## 필요성 관점의 리스크
- 구현 갭과 별개로, 가장 큰 논문 리스크는 `왜 기존 벤치마크로는 부족한가`에 대한 실증이 아직 약하다는 점이다.
- 현재 코드베이스는 기존 벤치마크를 많이 흡수하지만, 그만큼 reviewer는 오히려 `이 프로젝트가 독립 벤치마크인지, meta-evaluator인지`를 더 강하게 따질 가능성이 높다.
- 따라서 스펙-구현 정합성 못지않게, necessity를 뒷받침하는 비교 실험이 중요하다.

## 핵심 결론
- 코드베이스는 “엔진 + 위반 추출 + 골든 테스트 + 외부 어댑터 + 실험 하네스”라는 큰 뼈대는 이미 갖추고 있다.
- 가장 큰 갭은 현재 기준으로 `공통 계약 스키마 이중화`, `어댑터 인터페이스 불일치`, `위반 타입 경계 규칙의 비배타성`이다. 권한 이슈는 이번 턴에서 해소했다.
- 제출 전 우선순위는 다음 네 가지다.
  - `contracts.ScoreReport`와 `base.CGAScore`를 단일 canonical schema로 통합
  - `BaseAdapter`를 스펙 계약 기준으로 재정렬하거나, 문서를 현재 계약에 맞게 정정
  - sequence/deviation 등 경계 케이스의 단일 라벨 규칙 또는 우선순위 규칙 명문화
