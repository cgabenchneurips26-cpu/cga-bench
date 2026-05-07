개선 방향
3.1 Guideline ingestion을 AGREE/RIGHT/GRADE-aware로 바꾸기

현재 PDF parsing은 regex, LLM-assisted extraction, web extraction, custom pattern에 의존합니다. 이 자체는 현실적이지만, guideline source의 질과 recommendation reporting quality를 반영하지 않습니다. AGREE II는 guideline의 투명성, 개발 엄격성, 적용가능성 등을 6개 domain으로 평가하는 도구이며, 명시적 recommendation-evidence linkage, update procedure, implementation advice 등을 평가 항목으로 둡니다. RIGHT statement도 guideline reporting에 필요한 22개 item을 제시합니다.

개선안은 각 CPG source에 guideline_quality_card를 붙이는 것입니다.

guideline_quality_card:
  source_id: ssc_2021
  agree_ii:
    scope_purpose: 6
    rigor_development: 7
    applicability: 5
  right_items_present:
    recommendation_clarity: true
    evidence_linkage: true
    funding_disclosure: true
  extraction_risk:
    layout_complexity: high
    recommendation_tables_present: true
    algorithm_figures_present: true
    paywall_or_web_summary: false
  scenario_policy:
    allow_hard_constraints: true
    require_clinician_review_for_weak_recommendations: true

이 카드는 scenario weight와 review priority를 결정하는 데 사용합니다. 예를 들어 evidence linkage가 약한 source에서 나온 constraint는 hard violation으로 바로 쓰지 않고, soft/advisory 또는 manual review 대상으로 둡니다.

3.2 RecommendationAtom 중간표현을 추가하기

현재 구조는 corpus recommendation에서 바로 YAML graph로 갑니다. 이 단계가 너무 큽니다. CPGPrompt는 narrative guideline을 structured decision tree로 변환해 LLM이 case evaluation에서 navigate하도록 했고, binary referral에서는 F1 0.85–1.00을 보였지만 multiclass pathway assignment는 guideline 구조에 따라 F1 0.47–0.77로 떨어졌으며, negation과 temporal reasoning이 어려운 실패 유형으로 나타났습니다. 이 결과는 guideline을 곧장 graph/scenario로 변환하는 것보다, 더 세밀한 atom 단위가 필요하다는 근거입니다.

권장 중간표현은 다음입니다.

recommendation_atom:
  atom_id: rec_012_atom_03
  source:
    guideline_id: aha_stroke_2019
    section: "IV Alteplase"
    page: "e..."
    quote: "..."
    quote_hash: sha256
  population:
    inclusion:
      - acute_ischemic_stroke
      - time_since_last_known_well <= 4.5h
    exclusion:
      - intracranial_hemorrhage
      - inr > 1.7
  action:
    canonical_id: administer_iv_alteplase
    action_type: medication
    terminology:
      rxnorm: ...
      snomed: ...
  constraint:
    type: WITHIN
    activation_event: stroke_recognition
    deadline_minutes: 60
  sequence:
    before:
      - administer_iv_alteplase
    required_prior:
      - obtain_noncontrast_head_ct
  evidence:
    system: AHA
    class: I
    level: A
  scenario_hooks:
    boundary_variables:
      - time_since_last_known_well
      - inr
      - ct_result
    counterfactual_pairs:
      - eligible_vs_contraindicated

이 atom이 있어야 scenario compiler가 “어떤 condition을 flip하면 어떤 constraint가 바뀌는지”를 알 수 있습니다.

3.3 LLM은 generator가 아니라 proposer로 제한하기

Structured output 문헌은 LLM이 downstream system에 소비되는 출력을 만들 때 schema adherence가 중요하다고 강조합니다. JSONSchemaBench는 constrained decoding을 efficiency, coverage, quality 측면에서 평가했고, real-world JSON schema 지원 범위가 framework마다 크게 다름을 보였습니다. EMNLP Industry 2025의 SLOT도 critical applications와 information extraction에서 structured output이 필수이며, schema accuracy와 content fidelity를 별도로 평가해야 한다고 제안합니다.

따라서 Stage 2–4는 다음처럼 바꾸는 것이 좋습니다.

CPG text
  → section-aware retrieval
  → LLM proposes RecommendationAtoms
  → constrained schema validation
  → source-span entailment / contradiction check
  → multi-model agreement
  → clinician review queue for unstable atoms
  → deterministic graph compiler
  → deterministic scenario compiler

즉, LLM이 최종 scenario를 직접 쓰지 말고, 검증 가능한 atom 후보만 제안하게 합니다. Graph와 scenario는 deterministic compiler가 생성해야 합니다.

3.4 Scenario extraction을 “coverage optimization” 문제로 재정의하기

현재 scenario generator는 다양한 patient profile을 생성하지만, 목표함수가 명확하지 않습니다. 이를 다음 coverage set cover 문제로 바꾸는 것이 핵심입니다.

Minimize |S|
Subject to:
  every recommendation_atom covered ≥ k times
  every hard constraint covered ≥ k times
  every guard predicate has true/false coverage
  every temporal threshold has boundary coverage
  every BEFORE relation has compliant + violated trace
  every FORBID relation has normal + contraindicated matched pair
  every alternative branch has at least one valid path
  every evidence grade stratum represented

구체적으로는 7개 coverage를 추적합니다.

Coverage	의미	예시
Recommendation coverage	각 guideline recommendation이 scenario에 반영됐는가	rec_12 covered by scenario_03
Constraint coverage	MUST/FORBID/BEFORE/WITHIN이 모두 시험되는가	WITHIN(abx, 60m)
Guard coverage	conditional rule의 true/false가 모두 생성됐는가	penicillin allergy yes/no
Boundary coverage	threshold 근처 값이 있는가	lactate 3.9/4.0/4.1
Alternative coverage	clinically equivalent branch가 있는가	PCI vs thrombolysis
Mutation coverage	omission/late/swap/forbid perturbation이 있는가	abx at 95m
Source coverage	scenario가 source quote와 연결되는가	source_quote_hash present

이렇게 하면 690개든 706개든 단순 개수가 아니라 “무엇을 얼마나 덮었는가”를 보고할 수 있습니다.

3.5 Matched-pair counterfactual scenario를 1급 객체로 만들기

현재 논문 초안의 강점은 동일 trace라도 context가 달라지면 verdict가 달라진다는 것을 보여주는 데 있습니다. 이걸 scenario generation의 중심으로 올려야 합니다.

예를 들어 stroke tPA scenario는 단일 vignette가 아니라 다음 pair set으로 생성합니다.

counterfactual_family:
  family_id: stroke_tpa_context_pair_001
  shared_trace_template:
    - t=0: recognize_stroke
    - t=5: obtain_ct_head
    - t=35: administer_iv_alteplase
  scenarios:
    - scenario_id: eligible_tpa
      patient_state:
        last_known_well_min: 120
        inr: 1.0
        ct_result: no_hemorrhage
      expected_verdict: conformant
    - scenario_id: contraindicated_tpa
      patient_state:
        last_known_well_min: 120
        inr: 2.3
        ct_result: no_hemorrhage
      expected_verdict: commission_violation

이 구조는 πnctx/context-free evaluator의 blind spot을 직접 시험합니다. Agent trajectory 분야에서도 final answer보다 tool/action trajectory의 selection, parameterization, ordering을 본다는 흐름이 강해지고 있습니다. TRAJECT-Bench는 final accuracy 외에 tool selection, argument correctness, dependency/order satisfaction 같은 trajectory-level diagnostics를 보고합니다. SOPBench도 SOP/constraint adherence를 executable environment와 rule-based verifier로 평가하는 방향을 제시합니다.

3.6 Real-world EHR/process mining으로 synthetic scenario를 보정하기

JAMA systematic review는 519개 healthcare LLM evaluation 연구 중 real patient care data를 사용한 연구가 5%에 불과했고, 대부분은 QA accuracy 중심이었다고 보고했습니다. CGA-Bench가 synthetic engine 기반이라면, 최소한 scenario distribution을 real cohort/event log와 맞추는 보정 단계가 필요합니다.

Process mining for healthcare 문헌은 병원 event log를 통해 diagnostic, treatment, organizational process를 분석할 수 있지만, healthcare process의 variability와 patient-centered focus를 별도로 고려해야 한다고 말합니다. 2026 JMIR scoping review도 guideline adherence measurement에서 BPMN, ontology, FHIR, hybrid representation이 쓰였고, process mining이 sequence/timing variation을 잡는 데 쓰였지만, 대부분 patient-specific context가 부족하다고 지적합니다.

따라서 scenario extraction에는 두 가지 real-world anchor가 필요합니다.

Guideline-derived normative graph: what should happen
EHR-derived empirical pathway: what commonly happens
Scenario compiler: generate cases covering both normative edges and empirical deviations

ACL Findings 2025의 EMRs2CSP는 기존 clinical pathway extraction이 tests/treatments만 보고 symptoms/diagnosis를 놓치는 문제가 있으며, temporal information, symptoms, diagnosis, tests, treatments를 함께 포함한 clinical status pathway를 제안했습니다. 이 관점은 CGA-Bench scenario의 patient state를 강화하는 데 직접적으로 유용합니다.

4. 제안하는 새 pipeline

현재:

CPG Source → RAG Corpus → YAML Graph → Scenario YAML

개선 후:

CPG Source
  → Source Quality Card
  → Layout-aware Recommendation Corpus
  → RecommendationAtom extraction
  → Multi-model agreement + source entailment
  → ConstraintAtom compiler
  → Graph compiler
  → ScenarioSeed compiler
  → Coverage optimizer
  → Scenario YAML + Counterfactual families
  → Mutation traces
  → Clinical / statistical / leakage validation

핵심은 ScenarioSeed입니다. Scenario YAML을 직접 생성하지 말고, 먼저 “이 scenario가 어떤 constraint와 boundary를 시험하는가”를 선언해야 합니다.

scenario_seed:
  seed_id: sepsis_lactate_abx_boundary_001
  source_atoms:
    - ssc_2021_rec_hour1_lactate
    - ssc_2021_rec_hour1_antibiotics
  coverage_targets:
    constraints:
      - MUST(measure_lactate)
      - WITHIN(administer_broad_spectrum_abx, 60)
      - BEFORE(obtain_blood_cultures, administer_abx)
    boundaries:
      - lactate: [3.9, 4.0, 4.1]
      - abx_time: [55, 60, 65]
  patient_state_constraints:
    diagnosis: sepsis
    suspected_infection: true
    lactate: boundary_sample
    map: "<65 optional"
  observability:
    lactate_hidden_until: order_lactate
    culture_hidden_until: obtain_blood_cultures
  mutation_templates:
    - omit_abx
    - delay_abx_95min
    - give_abx_before_cultures
  private_fields:
    activated_constraint_ids: [...]
    expected_trace_family: [...]

이렇게 하면 scenario는 단순 vignette가 아니라 test specification이 됩니다.