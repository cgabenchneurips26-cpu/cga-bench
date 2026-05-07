# V7 CPG Expansion — Progress Log

Timeline of the v7 expansion work. Log-style entries with timestamps, inputs,
outputs (numbers), decisions, and bugs discovered. Commits referenced by SHA.

---

## 2026-04-22 (UTC)

### 09:00 — Session start

- **Trigger**: 리뷰어 공격 3종 검토 (25 CPG 선정 기준 / 706 시나리오 최대치 / timing 단독성)
- **Initial finding**: 내 timing 주장 "0/11 경쟁 벤치"는 웹 재검증 결과 **틀렸음** (MedAgentBench, PhysioNet Sepsis 2019, MTBBench 반례). scope qualifier 필요.
- Commit `e746be4a`: docs(defense) — v6 공격 3종 재검증 문서

### 09:30 — v7 선정 기준 설계

- 주관적 Tier S/A/B 폐기, M1~M6 정량 rubric 도입:
  - M1 time-sensitivity (deadline ≤60min mandatory action ≥3)
  - M2 sequential dependency (before-constraint ≥1)
  - M3 Tier-1 society (3-part composite)
  - M4 Class I OR required_action ≥10
  - M5 documented source (DOI/URL/ISBN)
  - M6 conditional richness (before+within ≥8 OR nodes ≥7)
- 99 후보 전수 점수화: **6점 54 / 5점 11 / 4점 24 / ≤3점 10 (Tier-valid 89/99)**
- v7 확장 우선순위 = 6점 만점 54개 (옵션 A)
- Commit `d5f8e255`: docs(cpg-expansion) — rubric + rescoring + pipeline spec

### 10:30 — Phase 1.1-1.4 구현

- `semantic_layer/cpg_parser.py` — `ExtractedRecommendation`에 source_guideline/section/quote/page 4 필드 추가
- `semantic_layer/cpg_yaml_generator.py` — ParsedGuideline → CPG YAML 변환 (MVP, category-based node 매핑)
- `scripts/auto_generate_cpg.py` — CLI entry (`--backend {vllm,openai,anthropic,mock,env}`)
- Smoke test: Fake ParsedGuideline → 5 nodes YAML → validator PASS
- Commit `8fef7c81`: feat(cpg-pipeline) — Phase 1.1-1.4 guideline→YAML autogen foundation

### 11:00 — 🚨 Retraction: validator/runtime dissonance

**사용자 지적 ("self 검증 필요 / 뭘 믿고 그냥 가니")에 따른 실증 재검증**

- 초기 단정: "25 CPG 중 6개가 validator에 fail → 파이프라인이 legacy bug 자동 감지 → 방어 증거"
- 실증 재검증: `pytest tests/test_engine/test_ssc_sepsis.py test_ada_dka.py test_aha_chest_pain.py -q`
  → **79 passed in 0.74s** (즉 "broken" YAML이 runtime에서는 정상 동작)
- 근본 원인 발견:
  - `assessor_core/violations.py:610-647` `_action_satisfies_requirement` 4-step matcher
  - `assessor_core/violations.py:642` — `start_vasopressor_if_hypotensive` 명시적 handler
  - `cpg_engine/stepper.py:124` `_action_satisfies`
  - → Runtime은 `allowed_actions`를 참조하지 않는다. `mandatory ⊆ allowed`는 runtime invariant 아님
- **서사 철회**: "legacy bug 자동 감지" 프레임 폐기
- CI 영향 분석: `.github/workflows/ci.yml` 확인 결과 `validate_cpg_schema.py`가 CI에 wire-up 안 됨 → "101 errors"는 dormant check
- Commit `89d19aef`: docs(cpg-expansion) — retraction + dissonance 기록

### 11:30 — Phase 1.5 runtime-consistent invariants

- `cpg_model/schemas/conditional_placeholders.py` (신규): RUNTIME_HANDLED_PLACEHOLDERS={'start_vasopressor_if_hypotensive'}, OBSERVED_SUFFIXES=11
- `semantic_layer/parsed_json_loader.py` (신규): deterministic JSON→YAML, 3 legacy invariant 제거:
  1. `mandatory ⊆ allowed` → 제거
  2. `allowed_actions` REQUIRED → RECOMMENDED
  3. `forbidden ∩ allowed = ∅` → conditional_rules로 flip 허용
- `scripts/ci/validate_cpg_schema.py` — 동일 3 완화 적용
- `scripts/auto_generate_cpg.py` — `--from-parsed-json` flag, validator subprocess path fix
- 검증 결과: **validator 25 CPG 0 errors** (101 → 0), **pytest 484 pass** (engine+schemas+assessor), **SSC round-trip 통과** (이전 reject)
- Commit `6f918992`: feat(cpg-pipeline) — Phase 1.5 runtime-consistent invariants

### 12:00 — Round-trip fidelity 100%

- `scripts/verify/round_trip_fidelity.py` — 25 CPG × 16 semantic fields × 167 nodes 일치율
- **결과**: `PASS: 100.0% (2672/2672 fields) across 25 graphs` — target 95%
- Per-field 전부 100%: mandatory_actions, allowed_actions, forbidden_actions, deadlines, required_prior_actions, next_nodes, conditional_next, recommendation_class, evidence_level, source_guideline, source_section, source_quote, source_page, precondition, node_type, name
- Per-graph 25/25 at 100%
- Commit `75189a31`: test(cpg-pipeline) — round-trip fidelity 100%

### 12:30 — Scenario derivation parity 100%

- `scripts/verify/scenario_derivation_parity.py` — patient_generator(orig) vs patient_generator(regen)
- **결과**: `PASS: orig=584 regen=584 common=584 only_orig=0 only_regen=0 field_mismatches=0`
- 7 field 전부 일치: guideline_graph, trap_scenario, generation_method, triggered_rules, expected_actions, forbidden_actions, working_diagnosis
- API 주의: `PatientGenerator.generate_from_graph(graph)` (아니라 `generate_all_scenarios`가 아님)
- Commit `eb6be89d`: test(cpg-pipeline) — scenario-derivation parity 100%

---

## 13:00 — 🚧 P1 Scale robustness (진행 중)

**목표**: 99 후보 전부에 대해 minimal synthetic extended JSON → rule-based loader → YAML → validator + patient_generator 통과 여부

### 13:00 — 첫 시도 (경로 버그 발견)

- `scripts/verify/p1_stub_99_generation.py` 작성 — 99 stub CPG 생성기
- 각 stub: 2 노드 (initial_assessment → treatment_plan), 필수 필드 전부 채움
- 실행 결과:
  ```
  [1/3] 99/99 YAMLs written; loader fails: 0
  [2/3] validator rc=2 (validator_pass=False, errors=0)   ← 🐛
  [3/3] 99/99 stubs generated scenarios; total_scenarios=99; scen_fails=0

  FAIL: loader=99/99 validator_rc=2 scen_ok=99/99 total_scenarios=99
  ```
- **진단**: `Path(__file__).resolve().parent.parents[2]`가 `AnonProject/` (cga_bench의 parent)로 잘못 resolve됨
  - `here.parents[0]` = `scripts/`
  - `here.parents[1]` = `cga_bench/` ← 원하는 repo_root
  - `here.parents[2]` = `AnonProject/` ← 잘못 잡힘
- 결과적으로 output dir이 `AnonProject/cpg_model/graphs_stub_99/`로 생성됨 (잘못된 위치) → validator가 빈 디렉토리 탐색
- 실제 loader/scenario 결과는 OK — loader 99/99 ✅, scenario 99/99 ✅ (stub 특성상 trap 없이 baseline 1개씩)

### 13:10 — 경로 fix + 재실행 → **PASS**

- Fix: `repo_root = here.parents[1]` (cga_bench/), sys.path 그대로 유지 (이미 맞음)
- Note: `rm -rf` wrong-location 디렉토리 시도 → OMC dangerous-cmd hook 차단 (expected)
- 재실행 결과:
  ```
  [1/3] 99/99 YAMLs written; loader fails: 0
  [2/3] validator rc=0 (validator_pass=True, errors=0)
  [3/3] 99/99 stubs generated scenarios; total_scenarios=99; scen_fails=0

  PASS: loader=99/99 validator_rc=0 scen_ok=99/99 total_scenarios=99
  ```
- **증명된 것**: 99 스케일에서 파이프라인이 mechanically robust — loader 모두 accept, validator 모두 pass, patient_generator 모두 execute
- **증명 못한 것**: stub은 clinical content이 없음 (trap 0, baseline 1개/CPG만). 따라서 "실제 guideline 내용을 파이프라인에 넣으면 유의미한 시나리오가 생성된다"는 주장은 P2에서 검증 필요
- Total scenarios = 99 (baseline only) vs 기존 25 CPG 584 scenarios 비교 시 stub이 conditional_rules/rich node structure 결여임을 확인

### Phase 1 + P1 정리

| Layer | 검증 | 결과 |
|---|---|---|
| Field fidelity (25 real CPG) | round_trip_fidelity.py | 2672/2672 = 100% |
| Scenario derivation (25 real CPG) | scenario_derivation_parity.py | 584/584 = 100% |
| Scale robustness (99 stub CPG) | p1_stub_99_generation.py | 99/99 loader + validator + scenario |
| Runtime regression | pytest engine+schemas+assessor | 484 pass |
| Validator 25 CPG | validate_cpg_schema.py | 0 errors, 125 info warnings |

→ **Mechanical 증명 완결**. Clinical content 증명은 P2 LLM smoke로 이동.

---

## 13:30 — 🚧 P2: LLM clinical smoke (시작)

**목표**: 기존 25 CPG의 rag_corpus parsed.json → LLM path (auto_generate_cpg.py) → 생성 YAML을 원본 수작업 YAML과 field-level diff. "LLM 경로가 실제 clinical 의미에 근접하는가" 측정.

**제약**:
- 기존 rag_corpus parsed.json 스키마는 `{recommendations[], tables[], key_sections{}}`로 빈약 (text/strength/page만)
- 따라서 LLM은 original guideline text를 parse하는 게 아니라 pre-digested summary를 재파싱
- 전제: SSC 1개로 smoke → 성공 시 나머지 확대 여부 사용자 결정

### 13:30 — `_load_input_text`에 rag_corpus 구조 지원 필요

현재 `auto_generate_cpg.py::_load_input_text`는 `text` 필드 또는 `chunks[].text`만 인식. rag_corpus의 `recommendations[].text` 패턴은 "Unsupported parsed.json shape"로 reject. 추가 지원 필요.

### 13:40 — `_load_input_text` 확장

- rag_corpus canonical shape `{recommendations[], tables[], key_sections{}}` 지원 추가
- 동작: 각 rec의 `[id p.page] text` 형식으로 concat + `key_sections` dict 추가 context
- 목적: SSC 같은 기존 rag_corpus 파일을 LLM path에 바로 입력 가능

### 13:45 — 🚨 vLLM endpoint 전수 확인 → 모두 offline

확인한 URL (curl --max-time 2):

| Endpoint | Status |
|---|---|
| localhost:8013/v1/models | no response |
| localhost:30003/v1/models | no response |
| 127.0.0.1 | no response |
| 127.0.0.1 | no response |
| 127.0.0.1 | no response |

이전 세션 기록 (`reference_ssh_and_gpu_hosts.md`, 메모리 1106-1111) 상 145 fleet은 live였으나 현재 시점 unreachable.

**P2 block**: 실제 LLM clinical smoke는 vLLM 서비스 필요. Endpoint 전무 상태에서 실행 불가.

선택지:
1. **(A) vLLM 서비스 기동** — 145 또는 144에 SSH (`sudo -n -u anonymous-org ssh`) → launch_vllm_*.sh 실행. 시간 ~5-15분, SSH 권한 필요
2. **(B) Mock backend로 flow smoke** — 실제 LLM 응답 없이 `--backend mock`으로 스크립트 경로만 검증. "clinical quality 증거" 미확보 상태로 marking
3. **(C) P2 defer** — 현재까지의 P1 mechanical + 2672/2672 field + 584/584 scenario 성과로 충분하다 판단, 논문 appendix에 반영. P2는 endpoint 확보 시점에 재개

→ 사용자 결정 대기 (세 번째 선택 기본 추천 이유: 현재 실증 규모가 이미 방어력 충분 + vLLM 재기동이 불필요한 GPU 시간 소비)

### 14:00 — vLLM endpoint 재탐지 (사용자 지시 "경합 확인")

- 외부 `curl --max-time 2`는 false-negative였음. SSH 내부 `ps` 확인으로 145에 vLLM 7개 live 확인:
  - 30004 google/gemma-3-27b-it
  - 30005 openai/gpt-oss-120b (TP=2)
  - 30007 Qwen/Qwen3.5-35B-A3B-FP8
  - 30009 deepseek-ai/DeepSeek-R1-Distill-Qwen-7B
  - 30013 Qwen/Qwen3.5-27B-FP8
  - 30014 gemma-3-27b-it (2nd)
  - 30023 Qwen3.5-27B-FP8 (2nd)
- **미스**: 외부 curl `--max-time 2`가 모델 부하 시 실패. **30초 이상 권장**.
- 외부 `/v1/models` 요청 Auth 없으면 `{"error":"Unauthorized"}`. API key `sk-no-key-required` (vLLM `--api-key` arg) 필요.
- 2026-04-22 이후 `reference_ssh_and_gpu_hosts.md`에 이 내용 보강.

### 14:30 — P2 SSC LLM smoke (실행 & 성공)

**Command**:
```bash
cd /home/anonymous-org/anonymous-project/AnonProject && PYTHONPATH=. OPENAI_API_KEY=sk-no-key-required \
  python3 cga_bench/scripts/auto_generate_cpg.py \
    --input cga_bench/data_release/v5.0/rag_corpus/SSC-2021-Sepsis-Hour1-Bundle.parsed.json \
    --domain sepsis --source "SSC 2021" --guideline-id ssc_llm_smoke \
    --backend vllm --model "Qwen/Qwen3.5-27B-FP8" \
    --endpoint http://localhost:8013/v1 \
    --output cga_bench/cpg_model/graphs_llm_smoke/ssc_llm_smoke.yaml \
    --validate --verbose
```

**결과 (exit 0)**:
- Loaded 3,196 chars (rag_corpus recommendations[] 구조 지원 덕)
- LLM request 15:49:35 → response 15:53:37 (**~4분**, 27B-FP8 single call)
- **Extracted 9 recommendations; parse_confidence=0.92**
- Wrote `cga_bench/cpg_model/graphs_llm_smoke/ssc_llm_smoke.yaml` (3,052 bytes)
- `validate_cpg_schema.py` → **PASSED, 0 errors**

**생성 YAML 분석**:
- 2 nodes (diagnostic_workup → treatment_plan) — CPGYAMLGenerator MVP category-based
- mandatory: `measure_serum_lactate`, `obtain_blood_cultures`, `administer_antimicrobials`, `administer_norepinephrine`, `administer_iv_corticosteroids` (LLM output 그대로)
- `source_section: SSC_R1 / SSC_R2 / ...` — 원본 ID 보존 ✅
- `source_quote`: 원문 verbatim span 정확히 포함 ✅
- `parse_confidence: 0.9222` 기록됨
- `recommendation_class: I`, `evidence_level: B` — LLM이 strength "strong"을 매핑

**vs 원본 수작업 `ssc_sepsis_hour1_bundle.yaml`**:
| 항목 | 수작업 원본 | LLM 생성 |
|---|---|---|
| Nodes | 7 (initial_recognition, sepsis_bundle, septic_shock_bundle, reassessment, disposition_decision, admit_to_icu, admit_to_ward) | 2 (diagnostic_workup, treatment_plan) |
| Conditional rules | 11 (penicillin 교차반응, HF fluid 신중, ESRD no fluid, neutropenia broad-spectrum, 등) | 0 |
| Deadlines | 다수 (lactate/cultures/antibiotics 각 60min, crystalloid 180min) | 대부분 비어있음 |
| Source quotes | 구체적 (Table 1, Recommendation 12 등) | SSC_R1~R8 |

**P2 smoke 해석**:
- ✅ **Mechanical**: LLM path는 end-to-end 정상 동작. Rec 추출 → YAML → validator PASS 전 flow.
- ✅ **Source traceability**: Phase 1.1에서 추가한 source_guideline/section/quote/page 필드가 실제 LLM output에 채워짐. Reviewer audit 가능.
- ⚠️ **Clinical richness 부족**: 2 nodes vs 원본 7 nodes, conditional_rules 0 vs 11, deadlines 대부분 빈 상태. 이는 **LLM quality 문제 아님 — CPGYAMLGenerator MVP의 설계 한계**:
  - Category당 1 node (ASSESSMENT/DIAGNOSTIC/TREATMENT/MONITORING/CONSULTATION/DISPOSITION)로 고정. 임상 현실에는 "septic shock sub-pathway" 같은 세분화 필요.
  - `conditional_rules` 처리 로직 없음 (패치 대상).
  - LLM prompt에 deadline 강제 request 약함 (prompt 개선 여지).

**결론**: "LLM path가 실제로 작동한다"는 **mechanical 증거 확보**. Clinical equivalence는 **Phase 2**의 generator 다양화 + conditional_rules 추출 + clinician review 작업 필요.

### Phase 1 + 1.5 + P1 + P2 최종 종합

| Layer | Evidence | Result |
|---|---|---|
| Field fidelity (25 real CPG) | round_trip_fidelity.py | **2672/2672 (100%)** |
| Scenario derivation parity | scenario_derivation_parity.py | **584/584 (100%)** |
| Scale robustness (99 stub) | p1_stub_99_generation.py | **99/99** |
| LLM path mechanical (SSC smoke) | auto_generate_cpg.py via vLLM | **exit 0, validator PASS** |
| Runtime regression (pytest) | engine+schemas+assessor | **484 pass** |

LLM path clinical richness는 CPGYAMLGenerator 다양화 Phase 2로 넘김.

---

## 2026-04-23 — Session 2: Coverage Audit + Rubric Freeze + YAML Batch

### Step 0: Annotation Corrections + Rubric Freeze

- **0a (6 corrections)**: Previously applied in Session 1 — all 6 verified:
  - #1 ata→jta_jes_thyroid_storm_2016 ✅ (rename in bulk_A)
  - #2 aasld→acg_acute_liver_failure_2023 ✅ (rename in bulk_A)
  - #3 ukka C5=0 ✅, #4 ada_hhs C2=0 ✅, #5 acog C9=0 ✅, #6 wms C2=1 ✅
- **0a (JTA/JES whitelist)**: Added JTA, JES to `TIER_1_SOCIETIES` in `scripts/score_cpg_v2.py`
- **0b (Rubric freeze)**: Added "Rubric Version Lock" section to `docs/cpg_expansion_v7/06_selection_criteria_v2.md`
- **0c (No drift verification)**: Re-ran scorer on 25 core CPGs — 17S/7A/0B/1Excl unchanged, mean 15.6/19
- **Test suite**: 80/80 pass in 0.41s

### Step 1: Coverage Audit

- Built ACEP EM Model (2022, 20 categories) × CGA-Bench coverage matrix
- **Output**: `docs/cpg_expansion_v7/09_coverage_matrix.md`
- Results: 17/18 clinical ACEP categories covered, 14/14 Lancet Commission emergencies, 11/15 GBD Top-15
- Single out-of-scope category: non-traumatic musculoskeletal (no hour-1 protocols)
- 4 GBD exclusions: COVID-19, cancers, HIV/AIDS, TB (all chronic/pandemic)

### Step 2b-2c: Spot-Check + Annotation Reliability

- **Spot-check protocol**: `docs/cpg_expansion_v7/10_spot_check_protocol.md`
  - Stratified sampling: borderline 100%, Tier S 30%, Tier A 20%, B/Excl 10%
  - ~35 candidates, ~7 hours, pre-registered sample
- **Annotation reliability**: `docs/cpg_expansion_v7/11_annotation_reliability.md`
  - Paper-ready appendix with +1.75 conservative bias finding
  - Spearman rho=0.82, 95% CI [+0.8, +2.7], zero inflation cases

### Step 3: YAML Batch Generation (score-19 + score-18)

- **Score-19 batch (5 graphs)**: COMPLETE
  - aha_acc_aortic_dissection_2022, aha_asa_ich_2022, esvs_aaa_2024, nrp_neonatal_resuscitation_2020, pals_pediatric_traumatic_arrest_2020
  - All pass schema validation + scenario generation
- **Score-18 batch (8 graphs)**: COMPLETE
  - aha_cardiogenic_shock_2017, aha_ttm_post_arrest_2023, bts_pleural_disease_2023, erc_hypothermia_2021
  - esvs_acute_limb_ischemia_2020, ispad_pediatric_dka_2022, ukka_hyperkalemia_2023, who_severe_malaria_2023
  - All pass schema validation + scenario generation
- **Running totals**: 16 auto graphs (3 pilot + 5 score-19 + 8 score-18), 94 nodes, 64 scenarios
- Remaining: ~40 more Tier S candidates (score 17-15)

### Step 4: Risk Checklist

- Held-out v2 scores verified: pals=17/S, apa=15/S, aba=14/A, acog=14/A, universal=2/Excl — no drift
- c6_score bug check: no bug, 3-tier priority correct
- 79-entry cross-check between full_124 and draft_batchA: 0 differences
- Universal safety exclusion statement: deferred to paper-edit session

---

## 2026-04-23 — Session 3: Score-18 Batch + Scenario Generation

### Step 3 (continued): Score-18 YAML Batch

- Added 8 builder functions to `generate_expansion_graphs.py` (16 total builders now)
- Schema validation: 16/16 PASS (94 warnings for optional source_page only)
- Scenario generation: 64 scenarios from 16 graphs (4 per graph)
- Clinical protocols include conditional_next branching, conditional_rules, required_prior, forbidden_actions

### Scenario Generation Pipeline

- `scripts/generate_scenarios_from_cpg.py --graphs-dir cpg_model/graphs/auto/` — 64 scenarios total
- Output: `configs/scenarios/auto/*.yaml` (16 scenario files)

### Test Suite Verification

- `tests/test_ci/test_score_cpg_v2.py` — 80/80 pass (0.46s)
- `tests/test_ci/` total — 125/125 pass (0.62s)

---

(이 log는 진행 중인 세션의 실시간 기록. 각 step마다 update.)
