# CGA-Bench 구현팀 전달용 작업 명세

구현팀 전달용 작업 명세다. 전제는 현재 저장소가 이미 cpg_engine, assessor_core, agent_runner, semantic_layer, external, export, env/adapters, tests, run_external_benchmark.py, run_neurips_experiment.py 구조를 갖고 있으므로, 새 시스템을 만드는 것이 아니라 입출력 계약을 고정하고, 검증을 강화하고, 외부 어댑터와 재현성 패키지를 붙이는 방식으로 가는 것이다. README의 아키텍처, 검증 전략 문서, 확장 제안서 모두 이 방향에 맞춰져 있다.

우선순위는 명확하다.

P0: CPG 기반 평가 엔진의 타당성 고정

P1: 외부 벤치마크 확장성과 스트레스 검증

P2: NeurIPS 제출용 재현성/실험 패키지

## ENG-00. 공통 계약 고정 [P0]

목표: 엔진, 평가기, 외부 어댑터, 실험 하네스가 같은 스키마를 사용하도록 강제한다.

구현 항목:
- 아래 스키마를 dataclass 또는 pydantic 중 하나로 고정
  - ConstraintOutput, ActionEvent, EpisodeLog, ViolationRecord, ScoreReport, ExternalParseResult, ExperimentConfig
- 필수 필드
  - 제약: mandatory_actions, forbidden_actions, deadlines, required_prior_actions
  - 로그: timestamp, action_id, normalized_action_id, tool_call, observation, metadata
  - 점수: final_score, action_coverage, compliance_score, peak_risk, aggregate_risk, violations_by_type, sub_scores, safety_gate
  - 출처: source_guideline, source_section, source_page, source_quote
- 모든 설정은 YAML + *Config로 외부 주입. 하드코딩 금지.

수정 대상: cpg_model/schemas/, assessor_core/event_log.py, scenario_loader.py, agent_loader.py, metrics_reporter.py

산출물: 스키마 파일, 샘플 JSON/YAML, 스키마 validation 테스트

완료 기준:
- invalid input은 명시적으로 실패
- valid sample은 round-trip serialize/deserialize 성공
- 보고서 JSON 구조가 고정됨

설계 원칙 자체가 No Hardcoded Defaults, Source Traceability, Action-Centric Evaluation을 요구하고 있다.

## ENG-01. CPG 엔진 출력 계약 완성 [P0]

목표: patient_state -> guideline constraints가 일관되게 계산되도록 만든다.

구현 항목:
- engine.evaluate(patient_state)의 출력 구조 고정
- reachability.py에서 도달 가능한 mandatory 수집
- applicability.py에서 환자별 적용 가능성 필터링
- temporal_constraints.py에서 마감 시각 계산
- stepper.py에서 단계 전이 정의
- 모든 guideline graph에 대해 snapshot 테스트 추가

수정 대상: cga_bench/cpg_engine/engine.py, reachability.py, stepper.py, applicability.py, temporal_constraints.py

산출물: guideline별 constraint snapshot, evaluate() 예제 출력 JSON

완료 기준:
- 엔진 출력 snapshot 일치율 100%
- supported guideline 전부 테스트 통과

## ENG-02. EpisodeLog와 상태 축소 파이프라인 고정 [P0]

목표: 행동 로그가 평가 가능한 불변 데이터 구조로 남고, 필요 시 상태로 환원될 수 있게 만든다.

구현 항목:
- ActionEvent를 immutable로 유지
- CompletedActions/정렬 규칙 고정
- state_reducer.py에서 Action -> PatientState 축소 규칙 명시
- clinical_state_extractor.py의 추출 결과를 로그와 분리 저장
- 시간 단위 정규화: epoch seconds / relative minutes 둘 다 지원하되 내부 표준은 하나로 통일

수정 대상: assessor_core/event_log.py, state_reducer.py, clinical_state_extractor.py

완료 기준:
- 이벤트 정렬 안정성 테스트 통과
- 초/분 단위 혼입 시 정규화 테스트 통과

## ENG-03. 위반 추출기 5종 정확도 확보 [P0]

목표: OMISSION / COMMISSION / TIMING / SEQUENCE / DEVIATION을 정확히 분리한다.

구현 항목:
- 위반 추출 로직을 타입별로 분리
- 경계값 케이스 추가: 마감 직전/직후, 선행 조건 뒤집기, 금기 행동 단일 수행, 허용 범위 밖 행동 1개
- DKA 특화 검출기는 core extractor와 interface만 공유하고, 특화 규칙은 분리 유지

수정 대상: assessor_core/violations.py, dka_violation_detector.py, action_normalizer.py

테스트: 위반 유형별 micro fixture 1세트씩, 오탐/미탐을 바로 잡는 최소 로그

완료 기준: 골든 로그 기준 위반 타입/개수/시점 일치율 100%

## ENG-04. HarmScorer / DualTrack / Safety Gate 고정 [P0]

목표: 최종 점수가 정책대로 계산되고, 위험이 올라가면 점수가 내려가도록 만든다.

구현 항목:
- HarmScorer 계산식 고정
- DualTrack = Track A × Track B × Safety Gate 구현 고정
- expected_actions_guard.py와 CPG_OVERSPECIFIC fairness guard 연결
- sub_scores(C1-C5) 계산을 테스트 가능하게 분리
- property-based monotonicity 테스트 추가
  - severity 1단계 증가 → 점수 감소 또는 동일
  - violation_type_weight가 작은 위반으로 바꾸면 점수 증가 또는 동일

수정 대상: harm_scorer.py, dual_track_evaluator.py, expected_actions_guard.py, episode_risk_scorer.py

완료 기준:
- Safety Gate trigger 정확도 100%
- monotonicity violation 0
- final score / sub-scores snapshot 일치

## ENG-05. 골든 테스트 12쌍 구축 [P0]

목표: 리팩터링이나 확장 이후에도 핵심 의미가 깨지지 않게 만든다.

구현 항목:
- tests/test_golden/ 신설
- 6개 guideline/domain × A/B 2쌍 = 최소 12쌍부터 시작
- 각 케이스는 "단 하나의 조건만 변경"

첫 wave에서 반드시 넣을 케이스:
- 흉통 ECG 10분 규칙: 8분 vs 15분
- 패혈증 blood culture → antibiotics 순서
- 패혈증 antibiotics 45분 vs 75분

파일 구조:
tests/test_golden/
  sepsis/
    hour1_sequence/
      graph.yaml, scenario.yaml, episode_A.json, episode_B.json, expected_A.json, expected_B.json
  chest_pain/
    ecg_10min/
    rv_infarct_nitrate/

하네스:
- run_case(case_fixture)
- assert_ab_monotonic(a_res, b_res, expected_new_violation_type)

완료 기준:
- 골든 12쌍 전부 통과
- 각 케이스의 expected violations / expected score JSON 고정

## ENG-06. scorer-agent 격리와 누출 탐지 CI [P0]

목표: 평가 시스템 정보가 에이전트로 새지 않도록 구조적으로 막는다.

구현 항목:
- 2-container 또는 2-venv 분리
  - scorer side: cpg_engine, assessor_core, scoring-side export
  - agent side: agent_runner, tool API, 외부 벤치마크 어댑터
- scorer side network egress 차단
- agent side에 scorer 코드 미설치
- canary 삽입: CGA_CANARY__<uuid>
- leakage_scan() 구현
- agent 입력/출력 전량 수집 후 canary scan
- hit > 0 이면 CI fail

수정 대상: CI workflow, runtime launcher, scripts/ci/leakage_scan.py 신설

완료 기준:
- canary hit 0
- scorer 코드 import 차단 확인
- Mock LLM 경로에서 결정적 테스트 가능

## ENG-07. 외부 벤치마크 어댑터 계약 테스트 [P1]

목표: 외부 입력을 내부 표준 EpisodeLog/Scenario로 안정적으로 변환한다.

공통 인터페이스: load_raw_case(), parse_to_scenario(), parse_to_episode_log(), detect_domain(), normalize_actions()

어댑터별 구현:
- AgentClinic: 대화/도구 호출을 observation -> candidate_action -> chosen_action 이벤트로 직렬화
- MedAgentBench: FHIR API 상호작용을 tool_call 이벤트로 캡처
- MedChain: workflow stage를 순차 행동/결정 이벤트로 변환

추가 규칙: domain mismatch 시 universal_clinical_safety.yaml fallback, budget_tracker 로그 함께 저장, malformed input robustness 테스트

수정 대상: semantic_layer/external/agentclinic.py, medagentbench.py, medchain.py, normalize.py, extensibility_verification.py, env/adapters/*

완료 기준:
- 계약 테스트 통과
- 정규화 복구율 ≥ 99.5%
- 심각 위반 누락 0
- 예산 편차 ≤ 1%

## ENG-08. XES/OCEL export-import와 스트레스 러너 [P1]

목표: 이벤트 로그 포맷 회귀와 대규모 처리 성능을 계량화한다.

구현 항목:
- XES import → internal log 로드
- internal → XES export → reload 후 동치성 검사
- internal → OCEL 2.0 export(JSON 우선) → reload 후 동치성 검사
- 스트레스 러너: small/medium/large profile
- 측정: events/sec, episodes/min, peak RSS, export/import time
- 1차: Synthea 기반 합성 로그, 2차: MIMICEL 접근 승인 후 대규모 회귀

수정 대상: semantic_layer/export/xes_exporter.py, ocel_exporter.py, scripts/bench/stress_eventlog_roundtrip.py, tests/test_export/, tests/test_correctness/

완료 기준:
- XES/OCEL round-trip 성공률 100%
- 기준선 대비 처리량 10% 이상 하락 시 fail
- peak RSS 15% 이상 증가 시 fail

## ENG-09. 재현성 번들 및 CI 명령 표준화 [P1]

목표: 새 환경에서 같은 결과를 다시 낼 수 있게 만든다.

구현 항목:
- lockfile 하나만 선택해 고정
- Python 버전/OS/커널 기록
- seed 고정 및 로그 저장
- dataset version / DOI / external benchmark commit hash 저장
- 결과 저장 경로 고정: reports/<date>/<gitsha>/
- 실행 명령 5개 표준화: lint/typecheck, engine/assessor, E2E, golden, stress

수정 대상: CI workflow, scripts/repro/, reports/ 저장 정책, run_neurips_experiment.py

완료 기준: 새 환경 clone 후 정해진 커맨드만으로 동일 산출물 생성

## ENG-10. NeurIPS 실험 패키지 [P2]

목표: 논문용 실험을 "기여점이 분리되게" 구성한다.

실험 블록:
- Baseline / upper-lower bounds: Oracle, RAG, Planner, Reflection, 외부 벤치마크 대표 설정
- Ablation: 시간 제약 제거, 순서 제약 제거, 금기 규칙 제거, 위험 점수 완화, DualTrack 제거/완화, fairness guard 제거
- Scalability: data scale, format scale(XES/OCEL), environment scale(FHIR tools/budget)
- Alignment: 3-way safety, Cohen's κ / Fleiss' κ / Spearman ρ / accuracy

완료 기준:
- run_neurips_experiment.py로 전체 패키지 실행 가능
- public MVP와 credentialed 확장 트랙 분리

## ENG-11. 문서와 출처 정합성 정리 [P1]

목표: 논문 제출 전에 source traceability를 깨끗하게 맞춘다.

구현 항목:
- 모든 graph node/action rule에 source_guideline/source_section/source_page/source_quote 채우기
- README와 graph metadata의 guideline citation 대조
- DKA 출처 정합성 재검토: ADA dc24-S015 표기가 DKA/HHS 직접 근거로 부정확할 수 있음

완료 기준:
- graph metadata audit 완료
- citation mismatch 0
- README 예시와 실제 YAML 일치

## 추천 스프린트 배치

주차 1: ENG-00, ENG-01, ENG-02
주차 2: ENG-03, ENG-04, ENG-05
주차 3: ENG-06, ENG-07
주차 4: ENG-08, ENG-09
주차 5: ENG-10, ENG-11

## 최종 승인 기준

엔진 snapshot 100% | 위반 추출 정확도 100% | Safety Gate 100% | monotonicity violation 0 | normalization recovery ≥ 99.5%, severe miss 0 | budget variance ≤ 1% | XES/OCEL round-trip 100% | canary hit 0 | throughput / peak RSS 기준선 통과
