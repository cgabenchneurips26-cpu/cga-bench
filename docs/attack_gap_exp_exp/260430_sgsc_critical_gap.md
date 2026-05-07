1. optional entailment를 mandatory field-level entailment로 바꿔라.
2. public/private scenario split과 mandatory_actions 제거로 leakage를 닫아라.
3. clinician-reviewed atom/constraint/scenario validation을 SGSC 기준으로 수행하라.

구현 보고서에서 특히 이상하거나 취약해 보이는 지점
8.1 C-8 hallucination assertion 수정이 의심스럽다

보고서의 P0 fix 중 C-8은 trivially true assertion을 고쳤다고 되어 있습니다. 그런데 한 줄이 이렇게 적혀 있습니다.

hallucination_rate >= 0.0
→ hallucination_rate > 0.5 or len(result.atoms) == 0

이게 실제 positive test인지 negative test인지 문맥을 봐야 하지만, 표면적으로는 “hallucination_rate가 높으면 통과”처럼 보입니다. 같은 섹션에서 다른 assertion은 hallucination_rate < 0.2로 고쳐졌다고 하므로, test intent가 서로 충돌할 가능성이 있습니다. 이건 실제 code audit에서 바로 확인해야 할 항목입니다.

8.2 RecommendationAtom granularity가 모호하다

보고서는 one atom per actionable guideline recommendation이라고 설명하지만, schema에는 singular action과 singular constraint가 있습니다. 실제 guideline recommendation 하나는 여러 action, timing, order, exception을 포함할 수 있습니다. 예를 들어 “혈액배양을 먼저 하고, 1시간 안에 항생제를 투여하라”는 최소 세 개 이상의 atom 또는 constraint로 분해되어야 합니다.

권장 invariant는 이겁니다.

RecommendationAtom은 recommendation 단위가 아니라
atomic action-constraint 단위여야 한다.

즉, 하나의 source recommendation은 여러 RecommendationAtom을 낳을 수 있어야 합니다.

8.3 ALTERNATIVE reserved는 clinical path 평가에서 큰 공백이다

대체 경로가 구현되지 않으면, benchmark는 “한 가지 정답 path”를 과도하게 선호할 수 있습니다. FHIR PlanDefinition도 conditional elements, options, decision points, action relationships를 표현하도록 설계되어 있습니다. SGSC가 clinical guideline compiler라고 주장하려면 alternative branch는 reserved가 아니라 active coverage type이어야 합니다.

8.4 compatibility가 오히려 leakage를 보존할 수 있다

보고서는 existing ScenarioDefinition과 cpg_model/graphs/*.yaml compatibility를 장점으로 제시합니다. 맞습니다. 하지만 기존 ScenarioDefinition과 Observation 경로가 private/public 분리를 강제하지 않는다면, compatibility는 기존 leakage surface도 함께 유지합니다.

9. 내 판단: 지금 구조의 신뢰도 등급
항목	등급	이유
IR/schema 설계	B+	immutable Pydantic IR, provenance field, atom 중심 구조는 적절함
deterministic compilation	B	LLM 후단 deterministic화는 좋음. 단, compiler semantic correctness는 fixture 중심
source fidelity	C+	quote hash/exact match는 좋지만 fuzzy grounding과 optional entailment가 약함
coverage model	C+	coverage accounting은 있으나 ALTERNATIVE reserved, MC/DC guard coverage 부족
set-cover optimizer	B-	practical하지만 “minimal” claim은 부정확
leakage resistance	C	scanner는 있으나 original observation leakage가 남아 있을 가능성
clinical validity	C-/pending	clinician validation, real-EHR validation이 아직 결과로 제시되지 않음
paper defensibility	B-	방법론 기여로는 강함. validity claim은 더 좁게 써야 함

요약하면:

SGSC는 “기존보다 훨씬 낫다.”
하지만 “이제 믿어도 된다”는 단계는 아니다.
현재는 “source-grounded scenario compiler의 credible prototype”이다.
10. top-tier 제출 전에 반드시 추가해야 할 trust gate
Gate 1. Real-corpus E2E test

mocked/precomputed atom이 아니라 실제 RAG corpus에서 end-to-end로 돌려야 합니다.

Input:
  5 held-out guideline corpora

Required outputs:
  proposed atoms
  accepted atoms
  rejected atoms
  review-required atoms
  generated constraints
  generated scenario seeds
  public/private scenarios
  coverage report
  leakage report

Pass criteria:
  no actionable_count==0 hallucinated graph
  accepted atom source entailment pass ≥ threshold
  clinician-reviewed atom precision ≥ threshold
Gate 2. Field-level entailment mandatory화

optional entailment를 제거해야 합니다.

Reject atom if any of the following fails:
  action not entailed
  guard not entailed
  exclusion not entailed
  timing not entailed
  sequence not entailed
  evidence strength not entailed

Structured output의 schema compliance도 semantic correctness를 보장하지 않습니다. JSONSchemaBench도 structured output 평가를 schema compliance뿐 아니라 constraint coverage와 generated output quality까지 봐야 한다고 설명합니다.

Gate 3. Public/private scenario split 강제

현재 compatibility output만으로는 부족합니다.

scenarios_public/
  agent-visible only

scenarios_private/
  ground_truth
  expected_actions
  forbidden_actions
  activated_constraint_ids
  trap_description
  coverage_targets

그리고 ClinicalEnvironment는 public만 받아야 합니다.

Gate 4. mandatory_actions observation 제거

이건 가장 시급합니다.

@dataclass
class Observation:
    timestamp_minutes: float
    visible_state: dict
    new_results: list
    alerts: list
    available_actions: list

    # 제거:
    # mandatory_actions

CDS-assisted condition을 만들고 싶다면 별도 experimental arm으로 분리해야 합니다.

experiment_condition:
  cds_assistance: true | false

기본 benchmark는 false여야 합니다.

Gate 5. Coverage를 MC/DC 수준으로 확장

현재 coverage type을 다음처럼 보강해야 합니다.

recommendation coverage
constraint coverage
guard true/false coverage
MC/DC guard coverage
boundary low/equal/high coverage
timing compliant/violated coverage
order compliant/violated coverage
forbid triggered/inert matched-pair coverage
alternative branch coverage
mutation coverage
source coverage

특히 ALTERNATIVE는 reserved가 아니라 active가 되어야 합니다.

Gate 6. Compiler mutation testing

현재 SGSC에는 mutation trace compiler가 있지만, compiler 자체의 mutation testing은 충분히 제시되지 않았습니다. 예를 들어 아래 mutation을 주입하고 test가 반드시 실패해야 합니다.

WITHIN deadline +5분 오프셋
BEFORE 방향 반전
FORBIDDEN을 REQUIRED로 오타
exclusion_guard negation 제거
quote_hash mismatch 허용
required_prior_actions merge drop
private field public file 유출

이걸 통과해야 compiler correctness를 좀 더 믿을 수 있습니다.

Gate 7. Clinician validation packet을 SGSC artifact 기준으로 재구성

논문 초안의 clinician validation은 진행 중입니다. SGSC가 새 compiler라면 validation packet도 SGSC-generated atom/constraint/scenario 기준으로 다시 만들어야 합니다.

권장 packet:

60 episodes가 아니라 최소:
  100 atom-level reviews
  100 constraint-level reviews
  60 scenario-level reviews
  60 trace-verdict reviews

Reviewer:
  3 clinicians
  guideline source blinded? no
  SGSC output blinded? yes
  disagreement adjudication protocol fixed

보고 지표:

atom precision
constraint typing precision
guard correctness
timing/window correctness
scenario activation correctness
TCC violation agreement
Gwet's AC1 / Krippendorff's alpha
Gate 8. Dataset manifest drift 제거

기존 문서에는 690 scenarios가 나오고, 논문 초안에는 706 scenarios가 나옵니다. architecture 문서의 canonical numbers도 8 models × 706 scenarios × 3 runs = 16,944처럼 섞여 있습니다.

이건 reviewer가 바로 잡을 수 있는 신뢰도 문제입니다. 반드시 manifest를 single source of truth로 만들어야 합니다.

benchmark_version: sgsc_v1
scenario_count:
  public: 706
  private: 706
  manual: 105
  auto: 601
episode_formula:
  models: 9
  scenarios: 706
  runs: 3
  expected_episodes: 19062
artifact_hashes:
  recommendation_atoms: sha256
  constraint_atoms: sha256
  scenarios_public: sha256
  scenarios_private: sha256