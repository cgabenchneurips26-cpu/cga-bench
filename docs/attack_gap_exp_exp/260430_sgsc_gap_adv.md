1. 오늘 변경분에서 바로 보이는 위험 신호

가장 먼저 잡아야 할 것은 inventory 자체의 불일치입니다. 사용자가 적은 요약은 “9개 신규 + 2개 수정”인데, 표를 그대로 세면 신규는 pilot_14_registry.json 1개, .gitkeep 14개, run_pilot_14.sh/py 2개, 문서 4개로 총 21개 파일성 항목입니다. 수정도 표에는 sgsc/pipeline.py, cpg_model/schemas/base.py, sgsc/schemas/atom.py, sgsc/compilers/graph_compiler.py, tests/test_sgsc/test_pipeline_e2e.py로 5개 파일이 나옵니다. 이건 단순 문서 표현 문제가 아니라, CGA-Bench 본문/아키텍처에서도 690 scenarios vs 706 scenarios, 8 models vs 9 models 같은 count drift가 이미 존재했던 것과 같은 계열의 문제입니다. 기존 아키텍처 문서는 690 scenarios를 적고 있지만, 논문 초안은 706 scenarios, 19,062 episodes를 사용합니다.

따라서 오늘의 첫 번째 조치는 코드 검증이 아니라 artifact inventory freeze입니다.

확인해야 할 것:
  신규 파일 실제 개수
  수정 파일 실제 개수
  git diff --name-status 결과
  pilot_14_registry.json이 참조하는 input/output path 존재 여부
  sgsc_output/14 dirs가 registry와 1:1 매칭되는지
  baseline freeze 문서의 숫자가 논문/data card/manifest와 일치하는지
2. 오늘 생성된 파일별로 무엇을 봐야 하나
D1. configs/sgsc/pilot_14_registry.json

이 파일은 가장 중요합니다. pilot_14가 SGSC 신뢰도 주장의 첫 empirical substrate라면, registry가 대표성 있는 pilot인지 확인해야 합니다.

확인할 것:

항목	봐야 할 질문	실패 신호
domain coverage	14개가 어떤 CPG/domain을 대표하는가	sepsis/stroke 같은 쉬운 guideline만 포함
constraint coverage	MUST/FORBID/BEFORE/WITHIN이 모두 포함되는가	WITHIN/MUST 위주
source quality	각 guideline corpus의 actionable recommendation 수가 충분한가	actionable_count 0 또는 quote fragment
scenario type	manual/auto/held-out이 섞였는가	manual만 또는 auto만
trap coverage	contraindication, timing, ordering trap이 있는가	단순 bundle completion만 있음
SGSC stress coverage	auto-transition을 실제로 쓰는 case가 있는가	auto-transition 코드가 pilot에서 exercised 안 됨
registry integrity	file path, graph_id, scenario_id가 실제 존재하는가	dangling reference

권장 추가 필드:

{
  "pilot_id": "pilot_14_v1",
  "selection_policy": "stratified_by_constraint_type_and_domain",
  "frozen_at_commit": "...",
  "items": [
    {
      "guideline_id": "...",
      "domain": "...",
      "source_corpus_path": "...",
      "expected_constraint_types": ["MUST", "WITHIN", "FORBID"],
      "expected_scenario_count": 12,
      "has_auto_transition": true,
      "has_counterfactual_pair": true,
      "heldout": false,
      "rationale": "covers timing + contraindication"
    }
  ]
}

BetterBench가 benchmark quality를 design, usability, reproducibility 관점에서 평가하고, 46개 best practice lifecycle을 제시한 점을 고려하면, pilot registry도 “우리가 고른 14개”가 아니라 “왜 이 14개가 construct를 대표하는지”를 명시해야 합니다.

D2. sgsc_output/{14 dirs}/.gitkeep

.gitkeep 자체는 문제가 아닙니다. 문제는 빈 output directory가 성공처럼 보이는 것입니다.

확인할 것:

각 14개 output dir에 대해:
  before run: .gitkeep만 존재해야 함
  after run:
    *_atoms.json
    *_constraints.json
    *_graph.json
    *_scenario_seeds.json
    *_scenarios_public.json or yaml
    *_scenarios_private.json or yaml
    *_coverage.json
    *_leakage.json
    *_manifest.json
    *_audit.md

고도화:

.gitkeep만 남아 있는 디렉터리는 run success로 간주 금지.
각 output dir에는 run_status.json을 강제 생성.

예:

{
  "status": "success",
  "guideline_id": "ssc_2021",
  "commit": "...",
  "started_at": "...",
  "finished_at": "...",
  "input_hash": "...",
  "output_hash": "...",
  "artifacts": {
    "atoms": {"count": 31, "path": "...", "sha256": "..."},
    "constraints": {"count": 44, "path": "...", "sha256": "..."},
    "scenarios": {"public": 18, "private": 18}
  },
  "quality_gates": {
    "source_fidelity_pass": true,
    "coverage_pass": true,
    "leakage_pass": true
  }
}
D3. scripts/sgsc/run_pilot_14.sh / run_pilot_14.py

여기는 reproducibility와 fail-fast를 봐야 합니다.

확인할 것:

1. registry를 유일한 input source로 쓰는가?
2. CLI argument가 registry를 override하지 않는가?
3. endpoint, model, temperature, seed, threshold가 log에 남는가?
4. precomputed_atoms 사용 여부가 명확히 분리되는가?
5. 실패한 guideline 하나가 전체 run을 조용히 성공 처리하지 않는가?
6. output hash와 input hash가 manifest에 남는가?
7. run 중간 산출물과 최종 산출물이 분리되는가?
8. shell script가 set -euo pipefail을 쓰는가?
9. PYTHONPATH, venv, dependency version이 freeze되는가?
10. dry-run mode가 있는가?

특히 SGSC 보고서상 E2E pipeline은 precomputed atoms와 mocked LLM을 사용합니다. 이건 unit/integration test로는 좋지만 실제 extraction 신뢰도 증거로는 약합니다. run_pilot_14.py는 반드시 두 모드를 분리해야 합니다.

# artifact correctness test
--mode precomputed

# extraction validity test
--mode live_extraction

그리고 논문에서 사용할 숫자는 live extraction 또는 freeze된 reviewed atom에서만 나와야 합니다.

D4. docs/sgsc/260430_r6_macro_inventory.md

이 문서는 수치 일관성 audit의 핵심입니다.

확인할 것:

scenario count:
  690? 706? 3186?
model count:
  8? 9?
episode formula:
  models × scenarios × runs = reported episodes?
constraint count:
  1049 hard / 0 soft?
manual/auto split:
  107/583? 105/601?

논문 초안은 25 CPG, 706 scenarios, 19,062 episodes, 9 models × 706 × 3을 주장하고, data card도 706 scenarios와 1049 hard / 0 soft constraints를 제시합니다. 반면 아키텍처 문서는 690 scenarios와 16,944 episodes를 함께 적고 있습니다.

고도화:

macro_inventory.md는 사람이 쓰는 문서가 아니라 manifest에서 자동 생성해야 함.

즉, 수동 문서 업데이트를 금지하고 아래처럼 생성합니다.

python scripts/sgsc/build_macro_inventory.py \
  --manifest data_release/sgsc_v1/manifest.json \
  --out docs/sgsc/260430_r6_macro_inventory.md
D5. docs/sgsc/260430_scn012_bridge.md

이 파일은 bridge case로 보입니다. 여기서는 old scenario → SGSC atom/constraint/seed/scenario 변환이 실제로 의미 보존되는지 봐야 합니다.

확인할 것:

기존 scn012의 guideline_graph와 새 graph_id가 같은가?
기존 expected_actions가 새 private expected_actions로만 들어갔는가?
기존 forbidden_actions가 public에 새지 않았는가?
기존 ground_truth가 public patient에 섞이지 않았는가?
기존 trap_description이 public에 없는가?
새 activated_constraint_ids가 CDE에서 실제 activate되는가?
기존 TCC verdict와 새 TCC verdict가 같은가?

bridge 문서는 단순 설명이 아니라 round-trip 증거를 포함해야 합니다.

old_scenario_yaml
  → SGSC ScenarioPublic/Private
  → ClinicalEnvironment(public only)
  → CPGEngine(private/evaluator only)
  → same pass/fail verdict
D6. docs/sgsc/260430_v6_baseline_freeze.md

freeze 문서에서 볼 것은 “무엇을 freeze했는가”입니다. 데이터만 freeze하고 코드가 바뀌면 안 됩니다. 코드만 freeze하고 prompt/model/endpoint가 바뀌어도 안 됩니다.

필수 freeze 대상:

git commit
docker image hash
python dependency lock hash
RAG corpus hash
graph hash
scenario public hash
scenario private hash
prompt hash
model endpoint
model name
temperature
seed
grounding threshold
entailment policy
coverage policy
leakage scanner version

TRIPOD-LLM은 healthcare LLM 연구에서 intended use, human oversight, task-specific performance reporting 등을 포함한 투명 reporting을 요구합니다. SGSC의 freeze 문서도 단순 “baseline frozen”이 아니라, 어떤 artifact와 decision이 고정됐는지 재현 가능하게 적어야 합니다.

C. docs/sgsc/260430_sgsc8_bridge_template.md

template은 나중에 모든 bridge case의 품질을 결정합니다. 여기서 확인할 것은 template이 증거 중심인지입니다.

좋은 template은 다음 필드를 강제해야 합니다.

1. source recommendation quote
2. RecommendationAtom field별 source support
3. ConstraintAtom type 선택 이유
4. ScenarioSeed coverage target
5. old/new scenario diff
6. activated constraint verification
7. public/private leakage check
8. expected trace verdict check
9. reviewer note
10. unresolved risk
3. 수정된 코드에서 특히 위험한 부분
3.1 sgsc/pipeline.py: grounding_threshold 0.4 → 0.5

이 변경은 작아 보이지만 사실 source fidelity claim 전체에 영향을 줍니다. 현재 보고서의 quote verifier는 VERIFIED/GROUNDED/UNGROUNDED 3-tier이고, fuzzy grounding에는 Jaccard 계열이 쓰입니다. threshold를 0.5로 올렸다고 source fidelity가 충분해지는 것은 아닙니다.

확인해야 할 것:

threshold = 0.4, 0.5, 0.6, 0.7에서:
  accepted atoms count
  rejected atoms count
  exact quote rate
  grounded fuzzy rate
  ungrounded rate
  human-labeled false grounding rate
  downstream constraint count
  downstream scenario count
  coverage loss

권장 정책:

Jaccard threshold는 candidate retrieval에만 사용.
acceptance는 field-level entailment로 결정.

Structured output 연구에서도 schema compliance는 충분하지 않고, constrained decoding은 efficiency, schema coverage, output quality를 별도로 평가해야 한다고 봅니다. SGSC에서도 JSON/Pydantic schema 통과와 source semantic correctness를 분리해야 합니다.

3.2 CPGNode.auto_transition_conditions

이건 오늘 변경 중 가장 위험합니다. auto-transition은 graph semantics를 바꿉니다. 잘못 구현되면 scenario가 의도하지 않은 node로 이동하거나, hidden ground truth를 이용해 transition이 발생하거나, 여러 transition이 동시에 fire될 수 있습니다.

확인해야 할 invariant:

Invariant A:
  모든 auto_transition_condition은 source recommendation 또는 explicit graph authoring note를 가진다.

Invariant B:
  condition variable은 public visible state인지, hidden ground_truth인지 명시된다.

Invariant C:
  hidden variable 기반 transition은 agent action으로 결과가 reveal된 뒤에만 fire된다.

Invariant D:
  여러 auto-transition이 동시에 true일 때 deterministic priority가 있다.

Invariant E:
  auto-transition graph에 cycle이 있어도 max transition depth로 무한 loop를 막는다.

Invariant F:
  auto-transition 추가 전후로 기존 baseline scenario의 TCC verdict가 의도 없이 바뀌지 않는다.

추가해야 할 테스트:

def test_auto_transition_does_not_use_hidden_ground_truth_before_reveal():
    ...

def test_auto_transition_multi_fire_priority_is_deterministic():
    ...

def test_auto_transition_cycle_is_bounded():
    ...

def test_auto_transition_preserves_existing_baseline_verdicts():
    ...

def test_auto_transition_conditions_have_provenance():
    ...

FHIR PlanDefinition도 particular circumstances에서 수행될 action group, conditional elements, options, decision points를 표현하는 자원이고, action의 trigger/applicability condition을 명시할 수 있습니다. auto-transition도 이와 같은 event-condition-action semantics로 문서화해야 합니다.

3.3 ScenarioHooks.auto_transitions

Scenario hook에 auto transition이 들어가면 “scenario generation hint”와 “clinical guideline semantics”가 섞일 위험이 있습니다.

확인할 것:

ScenarioHooks.auto_transitions가 graph semantics를 새로 만들고 있지는 않은가?
graph_compiler가 hook을 그대로 trust하고 있지는 않은가?
hook이 source-grounded atom에서 유도되는가?
manual scenario convenience가 guideline rule처럼 승격되지 않는가?

권장 분리:

auto_transition:
  source: constraint_atom | author_override | scenario_hint
  provenance_required: true
  agent_visible: false
  activation_policy: after_observable_state_update
3.4 graph_compiler.py: auto-transition encoding

여기서는 round-trip과 CDE activation을 반드시 봐야 합니다.

RecommendationAtom
  → graph_compiler
  → cpg_model graph
  → CPGEngine/CDE
  → DerivedConstraintSet

확인해야 할 것:

1. auto_transition이 YAML schema에 valid하게 들어가는가?
2. CPGNode parser가 해당 field를 실제로 읽는가?
3. CDE가 transition 이후 node constraints를 activate하는가?
4. old graph에는 field가 없어도 backward-compatible한가?
5. transition condition이 conditional_rules와 중복 적용되지 않는가?
3.5 test_pipeline_e2e.py: threshold assertion sync

단순히 threshold expected value를 0.4에서 0.5로 바꾼 것이면 부족합니다. threshold behavior를 검증해야 합니다.

추가할 테스트:

def test_grounding_threshold_controls_fuzzy_acceptance_boundary():
    # score 0.49 should fail at 0.5
    # score 0.50 should pass only as GROUNDED_CANDIDATE, not ENTAILED
    # score 0.51 should pass candidate retrieval
    ...

def test_threshold_change_does_not_hide_ungrounded_atoms():
    ...

def test_threshold_sensitivity_report_is_emitted():
    ...
4. 지금 더 확인해야 할 P0 체크리스트

아래는 “오늘 변경 직후” 바로 돌려야 할 순서입니다.

P0-1. Git/file inventory canonical화
git status --short
git diff --name-status HEAD~1..HEAD
find sgsc_output -name ".gitkeep" | wc -l
find sgsc_output -maxdepth 1 -type d | wc -l

Pass 기준:

reported 신규/수정 파일 수 == git diff 파일 수
registry item 수 == sgsc_output target dir 수
macro_inventory count == manifest count
P0-2. pilot_14_registry.json schema validation
python -m scripts.sgsc.validate_pilot_registry \
  --registry configs/sgsc/pilot_14_registry.json

Pass 기준:

all referenced corpora exist
all guideline_id unique
all output_dir unique
all expected constraint types declared
at least one held-out or explicitly justified no held-out
MUST/FORBID/BEFORE/WITHIN all represented
P0-3. Source fidelity threshold sweep
python -m scripts.sgsc.sweep_grounding_threshold \
  --registry configs/sgsc/pilot_14_registry.json \
  --thresholds 0.4 0.5 0.6 0.7 \
  --out sgsc_output/pilot_14_threshold_sweep.json

봐야 할 결과:

0.4→0.5에서 accepted atom이 얼마나 줄었는가?
줄어든 atom이 실제 false grounding인가?
0.5에서 GROUNDED fuzzy가 source entailment 없이 accepted되는가?
threshold가 downstream coverage를 깨는가?
P0-4. Auto-transition semantic audit
python -m scripts.sgsc.audit_auto_transitions \
  --graphs sgsc_output/*/*_graph.json \
  --out sgsc_output/pilot_14_auto_transition_audit.json

Pass 기준:

all auto_transition_conditions have provenance
no hidden variable used before reveal
no unbounded cycle
no ambiguous multi-fire transition
no transition to missing node
P0-5. Runtime leakage canary

기존 보고서의 leakage scanner는 private-field pattern을 잡습니다. 하지만 architecture상 Observation에 mandatory_actions가 포함되어 있어, import boundary가 있어도 engine-derived 정답 일부가 agent-visible observation으로 새는 위험이 있습니다.

Pass 기준:

public scenario file에 expected_actions, forbidden_actions, activated_constraint_ids 없음
agent observation에 mandatory_actions 없음
episode transcript에 private canary token 0건
source_quote/trap_description/deadline oracle 노출 0건

실행 형태:

python -m scripts.ci.runtime_canary_scan \
  --inject-private-canaries 200 \
  --run-pilot configs/sgsc/pilot_14_registry.json \
  --scan sgsc_output/pilot_14_transcripts
P0-6. Old/new verdict preservation

SGSC bridge가 기존 benchmark를 대체하려면, “의도하지 않은 verdict flip”이 없어야 합니다.

python -m scripts.sgsc.compare_old_new_verdicts \
  --old-scenarios configs/scenarios \
  --new-public sgsc_output/pilot_14/scenarios_public \
  --new-private sgsc_output/pilot_14/scenarios_private \
  --out sgsc_output/pilot_14_verdict_delta.json

분류:

expected flip:
  source grounding correction
  explicit transition bug fix
  newly activated constraint

unexpected flip:
  changed action id
  hidden state leakage
  auto-transition overfire
  missing required_prior_actions
  deadline parsing drift
5. 어떻게 고도화할 것인가
5.1 GROUNDED를 accept 상태가 아니라 review 상태로 낮춰라

현재 3-tier quote status는 유용하지만, GROUNDED fuzzy match를 accepted source fidelity로 취급하면 위험합니다. 권장 상태는 다음입니다.

VERIFIED_EXACT:
  exact normalized quote span found
  auto-accept 가능

GROUNDED_CANDIDATE:
  fuzzy quote candidate found
  field-level entailment 필요

ENTAILED:
  source quote entails all atom fields
  accepted 가능

CONTRADICTED:
  reject

UNGROUNDED:
  reject or manual review

field-level entailment schema:

field_entailment:
  action:
    status: entailed
    score: 0.94
  population:
    status: entailed
    score: 0.88
  exclusion:
    status: not_applicable
  timing:
    status: entailed
    score: 0.91
  sequence:
    status: entailed
    score: 0.86
  evidence_strength:
    status: entailed
    score: 0.90
  contradiction:
    score: 0.02
  accept: true
5.2 auto_transition을 first-class IR로 승격하라

지금은 CPGNode.auto_transition_conditions와 ScenarioHooks.auto_transitions가 따로 추가된 형태입니다. 이러면 graph compiler에서 semantics가 흩어질 수 있습니다.

권장 IR:

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
        "after_state_update"
    ]
    priority: int
    provenance: SourceReference
    hidden_state_allowed: bool = False

그리고 compiler는 이 Atom만 graph로 encode해야 합니다.

RecommendationAtom
  → ConstraintAtom
  → AutoTransitionAtom
  → Graph YAML
5.3 coverage를 “7-type”에서 “MC/DC + branch + transition coverage”로 확장하라

현재 보고서의 coverage model은 7-type이지만 ALTERNATIVE는 reserved입니다. 실제 임상 guideline에는 대체 가능한 치료 path가 자주 있고, FHIR PlanDefinition도 options와 decision points를 표현할 수 있습니다.

고도화된 coverage:

1. recommendation coverage
2. constraint coverage
3. guard true/false coverage
4. MC/DC guard coverage
5. boundary low/equal/high coverage
6. timing compliant/violated coverage
7. order compliant/violated coverage
8. forbid triggered/inert matched-pair coverage
9. auto-transition fire/not-fire coverage
10. alternative branch coverage
11. mutation coverage
12. source coverage

특히 auto-transition을 추가했다면 다음 coverage가 필요합니다.

AUTO_TRANSITION_FIRE
AUTO_TRANSITION_NOT_FIRE
AUTO_TRANSITION_MULTI_FIRE_PRIORITY
AUTO_TRANSITION_CYCLE_BOUND
AUTO_TRANSITION_HIDDEN_STATE_BLOCKED
5.4 pilot_14를 “신뢰도 산출 실험”으로 바꿔라

pilot_14는 단순 smoke test가 아니라 다음 지표를 내야 합니다.

지표	의미	권장 pass 기준
exact quote rate	exact source span 비율	≥ 70% 또는 사유 명시
field entailment pass	atom field별 source support	≥ 90%
accepted atom precision	clinician/manual review precision	≥ 90%
constraint activation match	expected constraints actually active	100%
public/private leakage	private token leak	0
transition ambiguity	multi-fire unresolved	0
old/new unintended flip	예상 외 verdict flip	0
coverage target uncovered	uncovered hard target	0
scenario solvability	generated patient state valid	100%

Medical LLM benchmark 쪽 최신 논의는 benchmark가 실제로 측정하려는 construct를 경험적으로 검증해야 한다고 강조합니다. SGSC에서는 “trace-level guideline conformance”라는 construct가 atom, constraint, scenario, trace verdict 단계에서 각각 맞게 구현됐는지를 따로 검증해야 합니다.

5.5 “minimal scenario set” 표현을 바꿔라

greedy weighted set-cover는 실용적으로 좋지만 optimal minimal을 보장하지 않습니다. SGSC 보고서도 greedy set-cover를 사용한다고 합니다.

문서 표현:

피해야 할 표현:
  minimal scenario set

권장 표현:
  coverage-satisfying scenario subset selected by a greedy weighted set-cover heuristic

고도화:

pilot_14에서는 greedy 결과와 ILP exact set cover 결과를 비교.
python -m scripts.sgsc.compare_set_cover \
  --coverage sgsc_output/pilot_14/*_coverage.json \
  --methods greedy ilp \
  --out sgsc_output/pilot_14_setcover_compare.json

SOPBench 같은 trajectory/SOP benchmark도 rule-based verifier와 executable environment를 통해 agent trajectory의 procedure adherence를 평가합니다. SGSC도 “scenario 수 최소화”보다 “verifiable coverage + rule-based verifier” 쪽 주장이 더 강합니다.

6. 크로스체크 매트릭스

아래 matrix를 그대로 운영 문서로 쓰는 것을 권합니다.

Cross-check	입력	비교 대상	실패 시 의미
file inventory check	git diff	오늘 보고서 파일 수	artifact drift
manifest count check	manifest	macro inventory / paper counts	reproducibility risk
registry path check	pilot_14_registry	filesystem	dangling pilot
source quote exact check	atom.source.quote	corpus text	hallucinated quote
field entailment check	atom fields	source quote	semantic grounding failure
graph roundtrip check	SGSC graph	CPGNode parser	schema compatibility failure
CDE activation check	scenario state	private activated constraints	scenario invalid
old/new verdict check	old scenario	new scenario	unintended semantic drift
leakage static check	public files	private token list	artifact leakage
leakage runtime check	transcript	canary tokens	evaluation leakage
auto-transition fire check	patient state	expected node path	transition bug
auto-transition non-fire check	counterfactual state	no transition	over-trigger
boundary check	threshold variable	low/equal/high scenario	missing threshold coverage
MC/DC check	compound guard	predicate-flip pairs	weak guard coverage
mutation check	injected trace	TCC failure	evaluator/compiler failure
set-cover check	greedy selected seeds	ILP or exhaustive small case	overclaim on minimality
clinician spot check	atom/constraint/scenario	reviewer label	clinical validity gap
7. 오늘 변경분 기준 “no-go” 조건

아래 중 하나라도 걸리면 pilot_14 결과를 논문/보고서의 신뢰성 증거로 쓰면 안 됩니다.

NO-GO 1:
  reported file inventory와 git diff가 다름.

NO-GO 2:
  pilot_14_registry item과 sgsc_output directory가 1:1이 아님.

NO-GO 3:
  grounding_threshold 0.5 변경에 대한 sensitivity report가 없음.

NO-GO 4:
  GROUNDED fuzzy atom이 field-level entailment 없이 accepted됨.

NO-GO 5:
  auto_transition_condition이 hidden ground_truth를 reveal 전에 사용함.

NO-GO 6:
  auto-transition multi-fire priority가 deterministic하지 않음.

NO-GO 7:
  public scenario 또는 transcript에 expected_actions, forbidden_actions,
  trap_description, mandatory_actions, activated_constraint_ids가 등장함.

NO-GO 8:
  old/new bridge에서 예상 외 TCC verdict flip이 발생함.

NO-GO 9:
  macro_inventory, baseline_freeze, paper/data card의 scenario/model/episode 수가 다름.

NO-GO 10:
  pilot_14가 MUST/FORBID/BEFORE/WITHIN 중 하나를 전혀 cover하지 않음.
8. 가장 먼저 추가할 스크립트 6개

오늘 변경을 제대로 고도화하려면 아래 6개가 우선입니다.

scripts/sgsc/validate_pilot_registry.py
scripts/sgsc/build_artifact_manifest.py
scripts/sgsc/sweep_grounding_threshold.py
scripts/sgsc/audit_auto_transitions.py
scripts/sgsc/compare_old_new_verdicts.py
scripts/ci/runtime_canary_scan.py

각 스크립트는 pass/fail JSON을 남겨야 합니다.

{
  "check_name": "audit_auto_transitions",
  "status": "fail",
  "failures": [
    {
      "graph_id": "...",
      "transition_id": "...",
      "reason": "hidden variable used before reveal"
    }
  ]
}
9. 논문/리뷰어 관점에서 고도화된 claim

현재 claim:

SGSC provides source-grounded coverage-guaranteed scenario generation.

이 표현은 아직 과합니다. 보고서상 entailment는 optional이고, ALTERNATIVE는 reserved이며, leakage scanner는 제한적입니다.

권장 claim:

SGSC separates LLM-based recommendation proposal from deterministic graph and scenario compilation,
and provides artifact-level source linkage, coverage accounting, transition audits, and leakage scans.

고도화 후 claim:

SGSC compiles guideline recommendations into source-entailed, coverage-accounted,
public/private-separated clinical scenario artifacts, with deterministic transition semantics
and runtime leakage canary validation.