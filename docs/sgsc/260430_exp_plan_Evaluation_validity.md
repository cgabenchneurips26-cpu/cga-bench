현재 evolution report를 보면 SGSC는 baseline의 7-type coverage, optional entailment, private-field scanner 수준에서 벗어나, 13 active coverage types, field-level entailment, validation packet, manifest, batch E2E harness를 갖춘 상태입니다. 특히 entailment_checker.py가 95→412 lines로 확장되어 action, guard, exclusion, timing, sequence, evidence 6개 field를 따로 검사하게 된 점은 핵심 개선입니다.

이 방향은 최신 benchmark 방법론과도 맞습니다. BetterBench는 benchmark quality가 design, usability, reproducibility에 달려 있으며, 많은 benchmark가 통계적 유의성과 재현성을 충분히 제공하지 않는다고 지적합니다. SGSC의 manifest, trust gates, coverage accounting은 이 약점을 줄이는 방향입니다.

다만 “의료 benchmark”에서는 더 엄격한 기준이 필요합니다. Medical LLM benchmark construct validity 논문은 benchmark가 실제 측정하려는 clinical skill을 포착하는지 empirical validation이 필요하다고 주장합니다. SGSC의 현재 evidence는 artifact-level reliability에는 강해졌지만, clinical construct validity까지 닫지는 못했습니다.

2. 지금 더 해야 할 핵심 방향
핵심 전략

앞으로는 다음 3개를 분리해서 증명해야 합니다.

A. Source fidelity:
   guideline source → RecommendationAtom이 맞는가?

B. Compiler fidelity:
   RecommendationAtom → ConstraintAtom/Graph/Scenario가 의미 보존되는가?

C. Evaluation validity:
   generated scenario와 TCC verdict가 실제 clinical guideline adherence construct를 측정하는가?

현재 SGSC는 B는 꽤 강해졌고, A는 개선 중이며, C는 아직 가장 약합니다.

3. P0 Plan: 1주 내 반드시 닫을 항목
P0-1. mandatory_actions runtime leakage 제거 또는 실험군 분리

아키텍처 문서의 Observation에는 available_actions와 함께 mandatory_actions가 agent-visible field로 들어가 있습니다. 이는 public/private scenario split과 별개로, CPG engine-derived 정답 일부가 agent에게 노출될 수 있는 구조입니다.

해야 할 일:

@dataclass
class Observation:
    timestamp_minutes: float
    visible_state: dict
    new_results: list
    alerts: list
    available_actions: list

    # 제거 또는 CDS-assisted arm으로 분리
    # mandatory_actions: list

권장 정책:

experiment_condition:
  cds_assistance: false

기본 benchmark에서는 mandatory_actions를 제거하고, CDS-assisted agent 실험을 별도 appendix로 분리합니다.

Pass 기준:

public scenario file leakage = 0
episode transcript leakage = 0
agent observation mandatory_actions occurrence = 0
private canary token hit = 0
P0-2. Pilot-14 결과를 “source semantic correctness” 기준으로 재평가

현재 Pilot-14는 14/14 guideline 처리, 443 atoms, 283 scenarios, hallucination 0.0%, leakage pass를 보고합니다. 그러나 hallucination_rate=0.0이 quote hash/substring 기준인지, field-level entailment 기준인지, clinician-reviewed correctness 기준인지 분명히 나눠야 합니다.

새로 보고할 지표:

지표	의미	권장 threshold
Exact quote match rate	source quote가 corpus에 exact 존재	≥70%
Field entailment pass rate	6 field 모두 source-supported	≥90%
Contradiction rate	source와 atom 충돌	0% 또는 review
Fuzzy-only accepted atoms	exact 없이 accept된 atom	전수 review
Clinician/manual atom precision	sample review 기준	≥90%
Constraint typing precision	atom→constraint type 정확도	≥90%

중요한 변경:

GROUNDED fuzzy match = accepted가 아니라 review-required
ENTAILED = accepted
CONTRADICTED / UNGROUNDED = rejected

Structured output 관련 최신 연구도 schema compliance만으로 output quality를 보장할 수 없고, efficiency, schema coverage, output quality를 별도로 평가해야 한다고 봅니다. 따라서 Pydantic pass와 semantic entailment pass를 분리해서 보고해야 합니다.

P0-3. Manifest를 single source of truth로 고정

논문 초안은 706 scenarios, 19,062 episodes를 쓰고, 기존 architecture 문서는 690 scenarios와 16,944 episodes를 동시에 포함합니다. 이제 SGSC manifest가 모든 숫자의 원천이어야 합니다.

해야 할 일:

1. docs/sgsc/*inventory*.md 수동 숫자 금지
2. paper table 숫자도 manifest에서 생성
3. Pilot-14 report와 full release report 분리
4. scenario_count, atom_count, constraint_count, episode_count hash 고정

필수 manifest field:

benchmark_version: sgsc_v1
commit: 9d73ee8d
source_corpus_hash: ...
recommendation_atoms:
  count: ...
  accepted: ...
  review_required: ...
constraint_atoms:
  count_by_type:
    MUST: ...
    FORBID: ...
    BEFORE: ...
    WITHIN: ...
scenario_count:
  public: ...
  private: ...
  manual: ...
  auto: ...
episode_formula:
  models: ...
  scenarios: ...
  runs: ...
  expected_episodes: ...
quality_gates:
  field_entailment_pass: ...
  leakage_canary_pass: ...
  cde_activation_pass: ...
  old_new_verdict_delta_pass: ...
P0-4. Auto-transition을 first-class audited object로 승격

최근 변경에서 CPGNode.auto_transition_conditions, ScenarioHooks.auto_transitions, graph_compiler.py auto-transition encoding이 추가되었습니다. 이것은 graph semantics를 바꾸는 변경이므로 가장 강하게 audit해야 합니다.

해야 할 일:

1. AutoTransitionAtom schema 생성
2. source_atom_ids 또는 author_override provenance 강제
3. activation_policy 명시
4. hidden_state_allowed 기본 false
5. multi-fire priority 명시
6. cycle bound 명시

권장 schema:

class AutoTransitionAtom(BaseModel):
    transition_id: str
    guideline_id: str
    source_atom_ids: tuple[str, ...]
    from_node: str
    to_node: str
    guard: PredicateNode
    activation_policy: Literal[
        "after_action",
        "after_result_reveal",
        "after_time",
        "after_state_update",
    ]
    priority: int
    hidden_state_allowed: bool = False
    provenance_quote_hash: str | None

Pass 기준:

no transition to missing node
no hidden ground_truth use before reveal
no ambiguous multi-fire without priority
no unbounded transition cycle
old/new verdict unintended flip = 0

FHIR PlanDefinition은 guideline action, condition, decision point, option을 표현하는 clinical reasoning artifact입니다. SGSC의 auto-transition도 이와 유사하게 condition/action semantics를 명시해야 장기적으로 computable guideline 주장과 연결됩니다.

4. P1 Plan: 2–4주 내 full-scale expansion
P1-1. Pilot-14 → full 25 CPG 확장

현재 Pilot-14는 283 scenarios입니다. 논문 claim은 25 CPG, 706 scenarios, 19,062 episodes입니다. Pilot-14를 smoke test로 남기고, full 25 CPG run을 별도로 실행해야 합니다.

실행 계획:

Week 1:
  Pilot-14 hardening + no-go clear

Week 2:
  remaining 11 CPG live extraction
  sanitizer failure log
  field entailment report

Week 3:
  full 25 CPG scenario generation
  public/private scenario generation
  coverage report
  leakage + canary scan

Week 4:
  old-vs-SGSC verdict comparison
  paper table regeneration
  external audit packet freeze

Full run 보고 지표:

25/25 guideline processed
accepted atom count
review-required atom count
rejected atom count
scenario count public/private
constraint count by type
coverage by type
uncovered hard target count
leakage hit count
runtime failure count

No-go:

uncovered hard WITHIN/FORBID/BEFORE target > 0
public/private scenario count mismatch
field entailment missing for accepted atom
runtime leakage canary hit > 0
P1-2. Pilot-14 대표성 분석

Pilot-14가 “어려운 guideline subset”인지 “쉬운 guideline subset”인지 명확히 해야 합니다.

보고할 stratification:

축	필요성
domain	sepsis/stroke/HF/AKI/ACLS 등 분포
constraint type	MUST/FORBID/BEFORE/WITHIN 모두 포함
conditionality	guard 있는 atom 비율
timing	deadline 있는 atom 비율
alternatives	alternative branch 있는 atom 비율
source quality	exact quote / fuzzy / ungrounded
scenario yield	atom당 scenario 수
transition complexity	auto-transition 사용 여부
held-out status	tuning-frozen graph 포함 여부

현재 Pilot-14 breakdown에서 heart failure와 stroke는 복잡하고, sepsis와 chest pain은 compact합니다. 이 차이를 “domain complexity profile”로 문서화해야 reviewer가 cherry-pick 의심을 줄입니다.

P1-3. Greedy set-cover를 ILP baseline과 비교

현재 baseline은 greedy weighted set-cover이고, evolution report에서도 solver는 그대로입니다. Greedy는 practical하지만 “minimal” claim은 위험합니다.

해야 할 일:

1. small/medium coverage instance에서 ILP exact set cover 실행
2. greedy selected scenario count / ILP optimal count 비율 보고
3. greedy가 coverage를 놓치지 않는지 검증
4. paper에서는 "minimal" 대신 "coverage-satisfying greedy subset" 사용

권장 table:

guideline	targets	greedy scenarios	ILP scenarios	ratio	uncovered
sepsis	...	...	...	1.04	0
stroke	...	...	...	1.11	0
5. P2 Plan: 1–2개월 내 validity evidence 강화
P2-1. Validation packet을 SGSC-native로 재설계

새로 추가된 validation_packet.py는 Cohen’s kappa, Gwet AC1, Krippendorff alpha를 지원합니다. 이제 이걸 실제 reviewer-facing evidence로 써야 합니다.

기존 논문에는 60-episode clinician validation protocol이 진행 중이고, 결과는 아직 claim에 사용하지 않는다고 되어 있습니다. SGSC 이후에는 validation unit을 episode만 보지 말고 4층으로 나눠야 합니다.

권장 validation packet:

A. Atom-level review:
   100 RecommendationAtoms
   질문: source quote가 action/guard/timing/evidence를 지지하는가?

B. Constraint-level review:
   100 ConstraintAtoms
   질문: MUST/FORBID/BEFORE/WITHIN typing이 맞는가?

C. Scenario-level review:
   60 ScenarioPublic/Private pairs
   질문: patient state가 해당 constraint를 실제로 activate하는가?

D. Trace-verdict review:
   60 episode traces
   질문: TCC violation label이 임상적으로 타당한가?

보고 지표:

atom precision
constraint typing precision
guard correctness
timing correctness
scenario activation correctness
trace verdict agreement
Gwet AC1
Krippendorff alpha
adjudication resolution rate

TRIPOD-LLM은 healthcare LLM 연구에서 title부터 discussion까지 19개 main items와 50개 subitems를 포함한 투명 reporting checklist를 제안합니다. SGSC 논문도 validation packet, data generation, human oversight, error analysis를 TRIPOD-LLM 스타일로 정리하면 방어력이 올라갑니다.

P2-2. Construct validity 분석 추가

SGSC가 진짜 측정하려는 construct는 “clinical guideline trace conformance”입니다. 이 construct를 다음 5개 hypothesis로 검증하세요.

H1. Known-violation traces should fail TCC.
H2. Known-clean traces should pass TCC.
H3. Timing/order/context perturbation should flip TCC but not action-set metrics.
H4. Clinician non-adherence judgments should correlate with TCC fail.
H5. Realistic EHR/process traces should activate similar constraint families.

각 hypothesis에 대한 evidence:

Hypothesis	Evidence
H1	mutation compiler kill-rate
H2	null control traces
H3	matched-pair counterfactuals
H4	clinician validation packet
H5	MIMIC/process-mining retrospective calibration

Medical LLM construct validity 논문은 benchmark가 실제 clinical skill을 구분하는지 empirical validation이 필요하다고 주장합니다. SGSC는 이 프레임을 도입해 “우리는 scenario compiler를 만들었다”에서 “우리는 trace-conformance construct를 측정하는 benchmark를 검증했다”로 확장할 수 있습니다.

P2-3. Real-world calibration probe

논문 초안은 engine-synthetic scenario라는 한계를 인정하고, MIMIC-IV re-scoring을 deferred로 두고 있습니다. SGSC 고도화의 다음 큰 leap는 synthetic scenario distribution을 real event log와 비교하는 것입니다.

구체적 plan:

1. MIMIC-IV 또는 내부 de-identified event log에서 domain별 event sequence 추출
2. action alphabet mapping
3. timestamp normalization
4. CDE로 active constraints replay
5. SGSC scenario distribution과 real event-log distribution 비교

비교 지표:

action frequency KL divergence
inter-action time distribution
constraint activation rate
violation type distribution
deadline miss distribution
guard variable distribution

의료 process mining 문헌은 conformance checking을 통해 실제 clinical process가 guideline에 얼마나 부합하는지 평가할 수 있다고 봅니다. SGSC는 이 방법을 benchmark realism calibration에 연결할 수 있습니다.

6. P3 Plan: 2–3개월 내 release/paper hardening
P3-1. FHIR/CQL crosswalk 추가

MedAgentBench는 FHIR-compliant interactive environment와 300 clinically relevant tasks를 내세우고 있습니다. CGA-Bench/SGSC가 의료 benchmark로 방어력을 얻으려면 내부 YAML만이 아니라 FHIR/CQL-compatible mapping을 보여주는 것이 좋습니다.

최소 crosswalk:

SGSC	FHIR/CQL 대응
RecommendationAtom	PlanDefinition.action
ClinicalActionRef	ActivityDefinition
PredicateNode	CQL expression
ScenarioPublic.patient	synthetic FHIR Bundle
ConstraintAtom.WITHIN	timing / relatedAction
EvidenceRef	Citation / Evidence metadata

초기에는 full export가 아니라 fhir_export_preview.json만 있어도 충분합니다.

P3-2. Cross-benchmark positioning 강화

AgentClinic은 simulated clinical environments에서 patient interaction, multimodal data collection, incomplete information, tool use를 포함하는 benchmark로 제시됩니다. MedAgentBench는 FHIR-compliant EHR 환경에서 medical LLM agent capability를 평가합니다.

SGSC/CGA-Bench의 차별점은 “interactive realism” 자체가 아니라 다음입니다.

published CPG source-grounding
typed constraints
deadline/order/context-conditioned trace conformance
public/private scenario separation
coverage-accounted scenario compilation
projection-blindness audit

따라서 paper positioning은 이렇게 가야 합니다.

MedAgentBench / AgentClinic:
  realistic agent environment

CGA-Bench + SGSC:
  source-grounded trace-conformance benchmark compiler
P3-3. Claim 정리

현재 evolution report는 “defense-ready system”이라는 톤이 강합니다. 논문에서는 조금 더 정확히 쓰는 것이 안전합니다.

피해야 할 claim:

SGSC guarantees clinical correctness.
SGSC eliminates hallucination.
SGSC generates minimal scenario sets.
SGSC proves clinical safety.

권장 claim:

SGSC improves artifact-level auditability by separating LLM-based atom proposal
from deterministic graph and scenario compilation.

SGSC provides source-linked, field-entailment-checked, coverage-accounted,
public/private-separated scenario artifacts.

Clinical validity is evaluated separately through clinician adjudication and
real-world calibration probes.
7. 구체적 8주 실행 로드맵
Week 1: P0 trust closure
작업	산출물	Pass 기준
mandatory_actions 제거	observation diff + tests	transcript hit 0
runtime canary scan	canary report	private token hit 0
manifest canonicalization	sgsc_manifest_v1.json	count drift 0
auto-transition audit	transition audit JSON	hidden-before-reveal 0
threshold sensitivity	0.4/0.5/0.6/0.7 report	accepted atom delta 설명 가능
Week 2: Pilot-14 evidence hardening
작업	산출물	Pass 기준
Pilot-14 field entailment audit	per-field CSV/JSON	accepted atom field pass ≥90%
fuzzy-only review queue	review YAML	fuzzy-only accepted 0 또는 전수 review
old/new verdict delta	verdict delta report	unexpected flip 0
CDE activation check	activation report	expected constraint activation 100%
MC/DC coverage check	coverage matrix	hard guard target uncovered 0
Week 3–4: Full 25 CPG expansion
작업	산출물	Pass 기준
remaining 11 CPG run	per-guideline reports	25/25 processed
full scenario generation	public/private scenarios	count match
coverage optimization	coverage report	hard target uncovered 0
full leakage scan	static + runtime scan	hit 0
manifest-driven tables	paper-ready tables	manual number edits 0
Week 5–6: Human validation
작업	산출물	Pass 기준
atom review packet	100 atoms	precision ≥90%
constraint review packet	100 constraints	precision ≥90%
scenario review packet	60 scenarios	activation correctness ≥90%
trace review packet	60 traces	TCC/clinician agreement reported
adjudication	final labels	disagreement protocol fixed
Week 7: Realism and external validity
작업	산출물	Pass 기준
EHR/process trace pilot	event-log mapping	at least 2 domains
distribution comparison	KL/IQR overlap report	deviations documented
FHIR export preview	5 guideline examples	schema-valid
external scorer replay update	MAB/AgentClinic-style table	reproducible
Week 8: Paper/release hardening
작업	산출물	Pass 기준
claim audit	reviewer attack table	overclaim 제거
data card update	SGSC data card	manifest-linked
reproducibility pack	Docker + make reproduce	clean run
appendix tables	source/coverage/leakage/validation	all generated
final no-go checklist	pass/fail sheet	P0 all pass
8. 반드시 추가해야 할 scripts
scripts/sgsc/audit_runtime_observation_leakage.py
scripts/sgsc/check_field_entailment_acceptance.py
scripts/sgsc/audit_auto_transition_semantics.py
scripts/sgsc/compare_old_new_verdicts.py
scripts/sgsc/build_manifest_tables.py
scripts/sgsc/run_full_25.py
scripts/sgsc/clinician_packet_builder.py
scripts/sgsc/fhir_export_preview.py
scripts/sgsc/coverage_greedy_vs_ilp.py
scripts/sgsc/real_eventlog_calibration.py

각 script는 반드시 다음 JSON을 남겨야 합니다.

{
  "check_name": "...",
  "status": "pass|warn|fail",
  "commit": "...",
  "input_hash": "...",
  "output_hash": "...",
  "metrics": {},
  "failures": []
}
9. Reviewer-facing trust table

최종적으로 paper appendix에 다음 표를 넣는 것이 좋습니다.

Trust claim	Evidence	Status
Source-grounded atoms	exact quote + field entailment + review sample	필요
Deterministic compilation	mutation tests + old/new verdict delta	일부 완료
Coverage-accounted scenarios	13-type coverage + MC/DC + alternative	일부 완료
Leakage prevention	public/private + runtime canary + observation audit	필요
Reproducibility	manifest + checksums + Docker	일부 완료
Construct validity	clinician packet + perturbation + real-log calibration	필요
External positioning	MedAgentBench/AgentClinic replay comparison	일부 완료
Clinical safety non-claim	limitation + intended-use clause	필요
최종 우선순위

지금은 기능 추가보다 신뢰성 closure가 우선입니다.

가장 먼저 할 5개는 이것입니다.

1. mandatory_actions runtime leakage 제거
2. accepted atom에 field-level entailment mandatory 적용
3. Pilot-14 threshold/entailment/source-fidelity sensitivity report 생성
4. Full 25 CPG SGSC run으로 706-scenario claim과 연결
5. SGSC-native clinician validation packet 실행