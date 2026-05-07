# CGA-Bench 벤치마크 설계 리뷰

## 리뷰어가 바로 물을 포인트
- 5종 violation taxonomy가 정말 MECE인가
- DualTrack가 truly complementary한가, 아니면 coverage의 재표현인가
- adapter 변환 후에도 score comparability가 유지되는가
- artifact가 다른 서버/계정에서도 같은 결과를 내는가

## 1. 스코링 체계의 타당성

### 강점
- DualTrack 분리는 정보량이 있다. `Track A = 원본 benchmark coverage`, `Track B = CPG compliance`를 분리하면 “과제를 수행했는가”와 “올바르게 수행했는가”를 분리해서 볼 수 있다.
- Safety Gate는 임상 안전 관점에서 설득력이 있다. 실제 구현도 고위험 위반이 하나만 있어도 최종 점수를 0으로 만들 수 있어, 단순 평균형 스코어보다 임상적 직관에 더 가깝다.
- 5종 위반 taxonomy는 단순 exact-match보다 풍부하다. omission, commission, timing, sequence, deviation을 분리하면 오류 유형 분석과 failure mode discussion이 가능하다.

### 잠재적 약점
- DualTrack가 완전히 독립 축인지는 아직 불명확하다. Track B가 violation 수와 timing/sequence 위반에 강하게 의존하면, Track A의 action coverage와 통계적으로 중복될 수 있다.
- severity/type weight의 근거가 코드 상수로 보인다. 임상 문헌 기반, 전문가 합의, empirical calibration 중 어느 방식인지 현재 구현만으로는 명확하지 않다.
- 최종 canonical report schema가 단일하지 않다. 이는 논문 표와 artifact 간 일관성 문제를 유발할 수 있다.
- 5종 taxonomy의 MECE 보장이 약하다. 현재 로직은 배타 tie-break를 명시하지 않아 하나의 action이 deviation과 sequence를 동시에 유발할 수 있다.

### 개선 제안
- 논문 본문에서 Track A/B의 상관관계를 정량 보고하라.
  - 예: Pearson/Spearman correlation, partial correlation, disagreement example.
- severity/type weight의 출처를 명시하라.
  - 우선 버전이라도 “expert-initialized, frozen before evaluation”로 고정하고 sensitivity study를 제공하는 편이 낫다.
- type boundary policy를 문서로 박아라.
  - 예: `forbidden > sequence > timing > omission > deviation` 같은 우선순위 또는 multi-label 허용 정책.
- 최종 점수/보고 포맷을 단일 스키마로 통합하라.

### 관련 선행 연구 참조
- R-Judge류 risk-aware evaluation
- CREOLA류 harm-aware clinical evaluation
- 프로세스/순차 의사결정 중심 의료 벤치마크: AgentClinic, MedAgentBench, MedChain

## 2. 평가자 간 신뢰도

### 강점
- 핵심 위반 추출은 규칙 기반이며 결정적이다. 이는 LLM-as-Judge에 비해 재현성이 높다.
- 골든 A/B 테스트와 스냅샷 테스트가 있어 회귀 탐지 구조는 존재한다.

### 잠재적 약점
- post-scoring pipeline에 LLM judge가 opt-in으로 들어가 있다. 이 경로가 본 스코어에 개입하면 모델 변경에 따른 instability가 생길 수 있다.
- human annotation과의 직접 일치도 검증은 저장소에서 충분히 보이지 않는다.
- 현재 확인한 핵심 테스트 65개는 모두 통과했지만, 이 재현성은 ACL 정리를 선행한 상태에서의 결과다.

### 개선 제안
- 메인 결과는 규칙 기반 scorer만 사용하고, LLM judge는 보조 분석으로 분리하라.
- 최소 50~100개 케이스에 대해 clinician adjudication을 붙여 Cohen's kappa 또는 Krippendorff's alpha를 제시하라.
- 현재 ACL은 정리됐으므로, 이 설정이 CI/서버 환경에도 동일하게 유지되도록 고정하라.

## 3. 데이터셋 커버리지

### 강점
- 외부 벤치마크 확장 의도는 분명하다. AgentClinic, MedAgentBench, MedChain, ArchEHR-QA, MedGUIDE 흔적이 모두 있다.
- ArchEHR-QA는 evidence-grounding 축을 보강한다.
- MIMICEL/XES는 스트레스·포맷 회귀 실험에 적합하다.

### 잠재적 약점
- review 지시의 핵심 데이터셋인 MIMIC-IV-ED, ArchEHR-QA, MedGUIDE 중 실제 구현 성숙도는 다르다.
  - ArchEHR-QA: 어댑터 존재
  - MedGUIDE: registry/config 중심
  - MIMIC-IV-ED: 직접 로더보다는 문서상 계획이 더 강함
- 데이터셋들이 동일한 clinical guideline adherence 문제를 측정하는지 불균질하다.
  - ArchEHR-QA는 evidence-grounded QA
  - MedGUIDE는 decision-tree/MCQ 성격
  - MedAgentBench는 interactive FHIR task
- 데이터셋 간 난이도 보정 메커니즘이 명시적으로 보이지 않는다.

### 개선 제안
- 각 데이터셋을 하나의 숫자로 합산하지 말고 역할을 분리하라.
  - workflow adherence: MedAgentBench, MedChain
  - evidence grounding: ArchEHR-QA
  - static decision adherence: MedGUIDE
  - process-log scalability: MIMICEL
- 메인 leaderboard와 auxiliary benchmark를 분리하라.
- slice analysis를 공개하라.
  - domain, episode length, tool-call count, timing-critical vs non-critical.

## 4. 어댑터 패턴의 타당성

### 강점
- 서로 다른 형식의 데이터를 CGA 내부 표현으로 변환하려는 방향 자체는 맞다.
- MedChain처럼 sequential workflow를 흡수하는 구조는 CGA-Bench의 강점과 잘 맞는다.

### 잠재적 약점
- 공통 인터페이스가 문서와 코드에서 다르다. 이는 아키텍처 설계가 아직 안정되지 않았다는 신호다.
- `env/adapters`와 `semantic_layer.external`의 이원화는 reviewer 입장에서 “canonical adapter path가 무엇인가?”라는 질문을 부른다.
- adapter consistency 실험이 부족하다. 동일 시나리오를 포맷만 바꿔 넣었을 때 score invariance를 보여줘야 한다.

### 개선 제안
- adapter contract를 단일화하라.
- cross-format invariance 실험을 메인 ablation에 넣어라.
  - same scenario -> AgentClinic-like JSON / MedAgentBench-like tool log / MedChain-like staged flow
  - 비교 지표: violation set overlap, compliance delta, ranking consistency
- information loss audit를 추가하라.
  - 변환 전 필드 수, 변환 후 보존 필드 수, dropped critical field count

## 5. 재현성 및 확장성

### 강점
- `eval_harness/runner.py`에서 environment snapshot, random seed, budget config 저장이 구현되어 있다.
- `data_release/v1.0/croissant.json` 등 D&B 친화적 자산이 존재한다.
- budget matching, XES/OCEL, post-scoring pipeline 등 실험 인프라는 풍부하다.

### 잠재적 약점
- 이번 턴에서 ACL 문제는 해소됐다. 다만 같은 권한 정책이 CI/다른 서버에도 재현되어야 한다.
- 결과 저장 경로가 스펙의 `reports/<date>/<gitsha>/`로 고정되었는지는 확인되지 않았다.
- 외부 benchmark commit hash, dataset DOI, credentialed dataset access path가 실행 결과에 자동으로 남는지 불명확하다.

### 개선 제안
- artifact release 전에 다음을 강제하라.
  - 핵심 파일 권한 정규화
  - one-command smoke test
  - one-command engine/adapter/golden test bundle
  - one-command repro export
- 결과 메타데이터에 반드시 포함시켜라.
  - git SHA
  - dataset version/DOI
  - external benchmark SHA
  - Python/OS
  - seed

## 필요성에 대한 강한 비판
- 현재 문서와 구현만 놓고 보면, CGA-Bench가 “왜 꼭 새로운 벤치마크여야 하는가”에 대한 방어는 아직 약하다. 지금 상태의 서술만으로는 reviewer가 이를 독립 benchmark가 아니라 `meta-evaluator` 혹은 `scoring wrapper`로 읽어도 막기 어렵다.
- 특히 AgentClinic, MedAgentBench, MedChain이 이미 각각 상호작용성, FHIR 도구 사용, 순차 워크플로우를 다루고 있기 때문에, reviewer는 “이 프로젝트가 정말 새로운 평가 문제를 여는가, 아니면 기존 benchmark 결과 위에 추가 점수를 덧붙이는가”를 바로 물을 것이다.
- 따라서 necessity argument는 선택이 아니라 핵심 기여 그 자체다. 논문이 `기존 벤치마크들이 놓치는 failure mode`를 실험적으로 못 박지 못하면, 복잡한 엔지니어링에도 불구하고 incremental하다는 평가를 받을 가능성이 높다.
- 더 직설적으로 말하면, 이 프로젝트가 방어해야 하는 것은 구현 완성도보다 존재 이유다. 새 점수 함수를 제안하는 것만으로는 약하고, `기존 벤치마크로는 측정되지 않는 안전-시간-순서 위반을 포착하는 불가결한 평가층`이라는 주장을 반드시 실증해야 한다.

## 총평
- 설계 방향은 NeurIPS Datasets & Benchmarks 트랙에 맞다. 특히 “정적 QA가 아니라 순차적 임상 행동 준수”를 평가하려는 문제 정의는 충분히 설득력 있다.
- 다만 현재 리뷰어가 가장 먼저 물을 약점도 명확하다.
  - 5종 taxonomy가 정말 MECE인가
  - DualTrack가 truly complementary한가
  - adapter conversion이 비교 가능성을 훼손하지 않는가
  - artifact가 정말 재현 가능한가
- 논문 메시지는 `기존 벤치마크의 빈틈을 메우는 최소 불가결한 평가층`으로 정리돼야 하며, 단순한 scoring add-on처럼 보이는 순간 약해진다. 그 전제하에서 아래 네 축을 함께 묶을 때 가장 강해진다.
  - temporal/sequence-aware guideline evaluation
  - harm-sensitive safety gate
  - cross-benchmark normalization
  - process-log compatible reproducibility package
