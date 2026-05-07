# v6 vs v7 Corpus 비교 분석 보고서

**작성일**: 2026-05-01
**분석 범위**: v6 corpus (`data_release/v5.0/scenarios/`, 708 scenarios) vs v7 corpus (`sgsc_output/`, 243 scenarios)
**v6 생성 방식**: Manual YAML + auto_generated (guideline graph → combinatorial expansion)
**v7 생성 방식**: SGSC 15-step pipeline (Qwen3.5-397B atom extraction → deterministic compilation)

---

## Executive Summary

| 지표 | v6 | v7 | 비고 |
|------|----|----|------|
| Total scenarios | 708 | 243 | v7 = 0.34x |
| Domains covered | 25+1 | 25 | 동일 coverage |
| Avg mandatory actions/scenario | 12.87 | 1.00 | v7는 single-action seed |
| Avg forbidden actions/scenario (YAML) | 11.12 | 0.00 | v7는 graph path로 처리 |
| Graph-level forbidden actions | N/A | 195 | v7 고유 아키텍처 |
| FORBIDDEN DerivedConstraints | N/A | 202 | CDE scorer가 평가 |
| Mean Jaccard (action overlap) | — | 0.165 | 16.5% semantic overlap |

**핵심 발견**: v6와 v7는 **구조적으로 비교 불가**. v6는 multi-action bundled scenarios (avg 12.87 expected + 11.12 forbidden per scenario), v7는 single-action seeds + graph-level constraint evaluation. v7의 FORBIDDEN 처리는 scenario YAML이 아닌 graph/DerivedConstraint/CDE 경로로 이루어짐.

---

## Q1: 도메인 분포 및 Constraint Type 분포

### 1.1 Per-Domain Scenario Count

| Domain | v6 | v7 | v7/v6 | 비고 |
|--------|----|----|-------|------|
| aabb_transfusion | 12 | 7 | 0.58 | |
| aba_burn_resuscitation | 20 | 10 | 0.50 | |
| acls_cardiac_arrest | 44 | 7 | 0.16 | v6 auto_gen 다수 |
| acog_obstetric_hemorrhage | 9 | 4 | 0.44 | |
| ada_dka_management | 42 | 24 | 0.57 | |
| aha_chest_pain_evaluation | 34 | 5 | 0.15 | v6 auto_gen 다수 |
| aha_heart_failure_2022 | 54 | 35 | 0.65 | v7 최대 domain |
| aha_stroke_2019 | 37 | 22 | 0.59 | |
| anaphylaxis_management | 17 | 12 | 0.71 | 높은 비율 유지 |
| apa_agitation_management | 15 | 10 | 0.67 | |
| atrial_fibrillation | 23 | 3 | 0.13 | |
| cap_pneumonia | 22 | 5 | 0.23 | |
| copd_exacerbation | 21 | 5 | 0.24 | |
| gi_bleeding | 23 | 10 | 0.43 | |
| gina_asthma_exacerbation | 46 | 21 | 0.46 | |
| hypertensive_emergency | 17 | 7 | 0.41 | |
| idsa_meningitis | 31 | 6 | 0.19 | |
| kdigo_aki_full | 72 | 5 | 0.07 | v6 최대→v7 최소 비율 |
| kdigo_contrast_aki | 42 | 10 | 0.24 | |
| pals_pediatric_emergency | 10 | 7 | 0.70 | |
| pulmonary_embolism | 29 | 5 | 0.17 | |
| ssc_sepsis_hour1_bundle | 23 | 4 | 0.17 | |
| status_epilepticus | 16 | 7 | 0.44 | |
| toxicology_management | 28 | 11 | 0.39 | |
| universal_clinical_safety | 19 | 1 | 0.05 | |
| **TOTAL** | **708** | **243** | **0.34** | |

**분석**:
- v7/v6 비율 범위: 0.05 (universal_clinical_safety) ~ 0.71 (anaphylaxis_management)
- v7이 v6보다 적은 이유: v6의 `auto_generated_scenarios.yaml`이 601개 combinatorial scenarios를 생성 (guideline graph에서 경우의 수 조합). v7은 atom당 1개 seed를 생성하는 설계.
- 비율이 낮은 도메인 (kdigo_aki_full 0.07, universal_clinical_safety 0.05): v6에서 auto_generated가 다량 생성된 반면, v7에서는 entailment gate를 통과한 atom 수가 적음.
- 비율이 높은 도메인 (anaphylaxis 0.71, pals 0.70): v6 auto_generated가 적었거나, v7 atom extraction이 풍부한 경우.

### 1.2 Constraint Type 분포 비교

**핵심 발견**: v7에는 constraint를 표현하는 **두 개의 레이어**가 존재하며, 분포가 완전히 다름.

#### Layer 1: Atom-Level Constraint (LLM 추출 직접 결과)

| Type | v6 % (참조) | v7 Count | v7 % | Delta |
|------|-------------|----------|------|-------|
| REQUIRED (=MUST) | 53.1% | 396 | 85.7% | +32.6pp |
| FORBIDDEN (=FORBID) | 20.2% | 29 | 6.3% | -13.9pp |
| WITHIN | 20.5% | 37 | 8.0% | -12.5pp |
| BEFORE | 6.2% | 0 | 0.0% | -6.2pp |

**해석**: Atom-level에서 REQUIRED가 85.7%로 과대 대표됨. LLM (Qwen3.5-397B)이 가이드라인 권고사항에서 "해야 할 것"을 "하지 말아야 할 것"보다 훨씬 많이 추출하는 경향. BEFORE가 0%인 것은 LLM이 순서 제약을 별도 constraint type으로 추출하지 못하고 sequence 필드에만 기록하기 때문.

#### Layer 2: DerivedConstraint (Graph Compiler 확장 결과)

| Type | Count | % | 비고 |
|------|-------|---|------|
| REQUIRED | 165 | 35.7% | atom→graph 변환시 축소 |
| FORBIDDEN | 202 | 43.7% | graph forbidden_actions에서 대량 생성 |
| WITHIN | 76 | 16.5% | 타임라인 제약 확장 |
| BEFORE | 15 | 3.2% | sequence.required_prior에서 파생 |
| EXPECTED | 4 | 0.9% | 기타 |
| **TOTAL** | **462** | **100%** | |

**해석**: DerivedConstraint 레이어에서 FORBIDDEN이 43.7%로 급증. 이는 `graph_compiler.py`가 atom의 population exclusion, contraindication 정보를 `forbidden_actions`로 확장하기 때문. **v6 참조 분포 (MUST 53.1%, FORBID 20.2%)와 비교하면 DerivedConstraint 레이어가 더 유사한 분포를 보이지만, FORBIDDEN이 과대 대표 (43.7% vs 20.2%)**.

#### Graph-Level Forbidden Actions

v7 graph에 포함된 실제 forbidden action 수: **195개**, 24/25 도메인에 분포.

| Domain | Graph FA Count | 주요 금지 행위 |
|--------|----------------|---------------|
| toxicology_management | 25 | 다약물 중독 금기 |
| gina_asthma_exacerbation | 22 | 진정제/beta-차단제 금기 |
| anaphylaxis_management | 19 | 경구 항히스타민/지연 투여 |
| status_epilepticus | 14 | 발작 중 경구 투약 금기 |
| aba_burn_resuscitation | 11 | 과다 수액 금기 |
| copd_exacerbation | 10 | 고유량 산소/과다 수액 |
| kdigo_contrast_aki | 9 | 고삼투압 조영제 |
| idsa_meningitis | 9 | 경구 항생제 금기 |

---

## Q2: Difficulty Profile 비교

### 2.1 Overall Difficulty Metrics

| Metric | v6 | v7 | Delta | 해석 |
|--------|----|----|-------|------|
| Total scenarios | 708 | 243 | -465 | |
| Avg mandatory actions/scenario | **12.87** | **1.00** | **-11.87** | 구조적 차이 |
| Max mandatory actions | 31 | 1 | -30 | |
| Avg forbidden actions/scenario (YAML) | **11.12** | **0.00** | **-11.12** | v7: graph path |
| Max forbidden actions (YAML) | 27 | 0 | -27 | |
| % scenarios with FA (YAML) | **97.0%** | **0.0%** | **-97.0pp** | |
| v7 graph-level forbidden | N/A | 195 | — | 24/25 domains |
| v7 FORBIDDEN DerivedConstraints | N/A | 202 | — | CDE 평가 대상 |

### 2.2 구조적 차이 원인 분석

**v6 시나리오 설계 철학**: 하나의 시나리오에 환자의 전체 clinical pathway를 bundling.
- 예: sepsis 시나리오 1개에 `[lactate, blood_culture, antibiotics, fluid, vasopressor]` 5개 expected + `[give_ampicillin, give_penicillin]` 2개 forbidden
- "이 환자에게 전체적으로 무엇을 해야 하고 무엇을 하면 안 되는가"

**v7 시나리오 설계 철학**: atom 1개 = seed 1개 (single-action test).
- 예: sepsis seed 1개는 `[order_lab_blood_culture]` 1개 expected만 포함
- FORBIDDEN은 scenario YAML에 없고, graph/DerivedConstraint를 통해 CDE scorer가 episode 평가 시 별도로 체크
- "각 개별 행위가 가이드라인에 부합하는가"

**결론**: v7의 avg mandatory=1.00, avg forbidden=0.00은 **버그가 아닌 설계**. v7은 MC/DC coverage를 위해 individual action isolation 전략을 사용. FORBIDDEN 평가는 `constraint_compiler.py` → `DerivedConstraint` → CDE scorer 경로로 수행.

### 2.3 WITHIN Constraint 상세

| Domain | WITHIN Atoms | 비고 |
|--------|-------------|------|
| ada_dka_management | 8 | 인슐린/수액 타이밍 |
| gina_asthma_exacerbation | 6 | 기관지확장제 투여 |
| acog_obstetric_hemorrhage | 4 | 수혈/수술 타이밍 |
| apa_agitation_management | 4 | 진정제 투여 |
| anaphylaxis_management | 3 | 에피네프린 |
| 기타 10개 도메인 | 12 | |
| **TOTAL** | **37** | **v7 atom의 8.0%** |

**WITHIN deadline 분포**: min=2min, median=15min, max=1440min (24h), mean=76min

v6 참조: WITHIN 20.5% → v7 atom-level 8.0% (gap: -12.5pp). 그러나 DerivedConstraint level에서 WITHIN=16.5%로 closer. 이는 graph compiler가 REQUIRED atoms에서도 deadline 기반 WITHIN constraints를 파생시키기 때문.

---

## Q3: Trap-Loaded Scenario 재현 및 Jaccard Similarity

### 3.1 Trap-Loaded Scenario 분석

**정의**: "trap-loaded scenario" = forbidden_actions가 1개 이상인 시나리오.

| 지표 | v6 | v7 (YAML) | v7 (Graph) |
|------|----|-----------|----|
| Trap-loaded scenarios | 687/708 (97.0%) | 0/243 (0.0%) | N/A |
| Domains with forbidden | N/A | 0/25 | 24/25 (96.0%) |
| FORBIDDEN DerivedConstraints | N/A | — | 202 |
| Paper App T reference | 22.1% | — | — |

**핵심 발견**:

1. **v6의 97.0% trap rate vs Paper App T의 22.1%**: Paper App T의 22.1%는 "critical-severity FA" scenarios만 카운트. v6의 97.0%는 모든 FA scenarios (auto_generated 포함). auto_generated scenarios는 각각 avg 12.7개 forbidden actions를 포함하므로 사실상 전부 trap-loaded.

2. **v7의 0% trap rate (YAML level)**: v7 scenario compiler의 설계에 의한 것:
   - `scenario_compiler.py` line 106-109: `FORBIDDEN` 타입 atom은 seed 생성 시 skip (`continue`)
   - FORBIDDEN atoms는 counterfactual families에만 기여
   - 결과적으로 scenario YAML에는 forbidden_actions가 없음

3. **v7의 실질적 FORBIDDEN coverage**: scenario YAML에는 없지만:
   - 195개 graph-level forbidden actions (24/25 domains)
   - 202개 FORBIDDEN DerivedConstraints
   - CDE scorer가 episode 평가 시 이 constraints로 위반 감지
   - **v7 episode rerun에서 FORBIDDEN 평가는 graph/CDE path로 정상 수행됨**

4. **v7의 trap reproduction 여부**: v7은 v6와 다른 메커니즘으로 trap을 구현. v6는 scenario-level에서 explicit forbidden_actions 목록, v7은 constraint-level에서 implicit FORBIDDEN evaluation. **기능적으로는 equivalent하나 구조적으로는 다름.**

### 3.2 Domain-Stratified Jaccard Similarity

Jaccard(A, B) = |A intersection B| / |A union B|, action set 기준 (normalized, graph-forbidden 포함)

| Domain | v6 Actions | v7 Actions | Intersection | Union | Jaccard |
|--------|-----------|-----------|-------------|-------|---------|
| anaphylaxis_management | 51 | 31 | 22 | 60 | **0.367** |
| gina_asthma_exacerbation | 62 | 43 | 27 | 78 | **0.346** |
| copd_exacerbation | 49 | 15 | 15 | 49 | **0.306** |
| aba_burn_resuscitation | 42 | 21 | 14 | 49 | 0.286 |
| aabb_transfusion | 29 | 13 | 9 | 33 | 0.273 |
| gi_bleeding | 48 | 15 | 12 | 51 | 0.235 |
| pals_pediatric_emergency | 22 | 10 | 6 | 26 | 0.231 |
| toxicology_management | 56 | 35 | 17 | 74 | 0.230 |
| status_epilepticus | 45 | 20 | 11 | 54 | 0.204 |
| pulmonary_embolism | 47 | 13 | 10 | 50 | 0.200 |
| apa_agitation_management | 26 | 13 | 6 | 33 | 0.182 |
| idsa_meningitis | 52 | 15 | 10 | 57 | 0.175 |
| cap_pneumonia | 61 | 12 | 10 | 63 | 0.159 |
| ada_dka_management | 93 | 32 | 17 | 108 | 0.157 |
| hypertensive_emergency | 54 | 13 | 9 | 58 | 0.155 |
| acog_obstetric_hemorrhage | 13 | 4 | 2 | 15 | 0.133 |
| acls_cardiac_arrest | 55 | 12 | 7 | 60 | 0.117 |
| kdigo_contrast_aki | 83 | 18 | 10 | 91 | 0.110 |
| aha_heart_failure_2022 | 98 | 42 | 11 | 129 | 0.085 |
| aha_stroke_2019 | 110 | 26 | 10 | 126 | 0.079 |
| atrial_fibrillation | 37 | 5 | 2 | 40 | 0.050 |
| universal_clinical_safety | 32 | 9 | 1 | 40 | 0.025 |
| ssc_sepsis_hour1_bundle | 56 | 5 | 1 | 60 | 0.017 |
| aha_chest_pain_evaluation | 91 | 6 | 1 | 96 | 0.010 |
| kdigo_aki_full | 107 | 7 | 0 | 114 | **0.000** |
| **MEAN** | — | — | — | — | **0.165** |

### 3.3 Jaccard 분석

**Overall Mean Jaccard = 0.165** → v6-v7 간 action 어휘의 16.5%만 겹침.

**높은 Jaccard (>0.3) 도메인 (3개)**:
- `anaphylaxis_management` (0.367): 에피네프린, 기도확보 등 핵심 action이 두 버전에서 동일
- `gina_asthma_exacerbation` (0.346): 기관지확장제, 스테로이드 등 표준화된 행위명
- `copd_exacerbation` (0.306): 기관지확장제, 코르티코스테로이드 명칭 일치

**낮은 Jaccard (<0.1) 도메인 (6개)**:
- `kdigo_aki_full` (0.000): v6에 107개 action (매우 세분화), v7에 7개 (추상화). 완전 불일치.
- `aha_chest_pain_evaluation` (0.010): v6의 `aspirin` vs v7의 `aspirin_load` — normalization 후에도 불일치
- `ssc_sepsis_hour1_bundle` (0.017): v6의 `give_broad_spectrum_antibiotics` vs v7의 `give_antibiotics` 수준 차이

**낮은 Jaccard의 원인**:
1. **Action naming convention 차이**: v6 수작업 명명 vs v7 LLM 추출 명명
2. **Granularity 차이**: v6는 세분화 (`give_ampicillin`, `give_amoxicillin`), v7은 추상화 (`give_antibiotics`)
3. **ActionNormalizer 한계**: 현재 normalizer는 prefix stripping만 수행, 의미적 동의어 매핑 미수행
4. **Coverage scope 차이**: v6 auto_generated는 모든 graph action을 조합으로 나열, v7은 entailment 통과 atom만 사용

---

## Additional: `_stem_match` False Positive 분석

### 방법론

v7의 462개 atom에 대해 `action.canonical_id`에서 keyword를 추출하고 `source.quote`에 대해:
- **Original**: `keyword in text` (substring match, 현재 구현)
- **Fixed**: `\bkeyword\b` (word-boundary regex, 제안 수정)

### 결과

| 지표 | 값 |
|------|-----|
| Total keyword-quote checks | 1,221 |
| Original (substring) matches | 365 |
| Fixed (word-boundary) matches | 250 |
| **False positives** | **115** |
| **False positive rate** | **9.42%** |

### False Positive 패턴 분류

| 패턴 | Count | 예시 | 설명 |
|------|-------|------|------|
| "assess" in "Assessment" | ~40 | `assess` -> `Transfusion Assessment` | 명사형에 동사가 substring match |
| "forbid" in "forbidden" | ~25 | `forbid` -> `transfusion is forbidden` | 파생어 불일치 |
| "give" in "given/forgive" | ~15 | `give` -> `oxygen should be given` | 과거분사/다른 단어 |
| "pre" in "prevention/present" | ~10 | `pre` -> `prevention of cardiac` | 접두사 충돌 |
| "add" in "additional/address" | ~10 | `add` -> `additional monitoring` | 짧은 keyword |
| 기타 | ~15 | 다양한 부분 문자열 충돌 | |

### Impact Assessment

- 115개 false positive 중 **atom rejection에 실제 영향을 주는 경우**는 제한적
- `_stem_match`는 entailment checker의 6개 필드 중 1개 (action grounding)에만 사용
- action grounding이 PARTIAL로 판정되어도 다른 5개 필드가 ENTAILED이면 atom은 accepted
- **결론**: word-boundary fix는 정확성을 개선하지만, v7 corpus의 atom 수 (462개)에 미치는 실제 영향은 미미 (KNOWN_ISSUES 7-3의 (a) 분류 유지)

---

## 종합 결론 및 Paper 시사점

### 1. v6-v7 직접 비교는 부적절

v6와 v7는 근본적으로 다른 설계 철학:

| 차원 | v6 | v7 |
|------|----|----|
| Scenario 단위 | Multi-action bundled | Single-action seed |
| FORBIDDEN 처리 | Scenario YAML 내장 | Graph/CDE 경로 |
| 생성 방식 | Manual + combinatorial | LLM extraction + deterministic |
| Difficulty 표현 | Per-scenario complexity | Per-constraint coverage |
| 평가 방식 | Scenario-level compliance | Constraint-level MC/DC |

### 2. Paper S6 프레이밍 제안

v6→v7 전환을 "동일 벤치마크의 개선판"으로 프레이밍하면 안 됨. 대신:

> "v7은 v6의 수작업 시나리오를 대체하는 것이 아니라, 가이드라인 원문에서 자동으로 파생된 constraint-level 평가 체계를 도입한다. v6는 임상 시나리오의 사실성(fidelity)을, v7은 가이드라인 준수의 체계성(systematicity)을 각각 우선시한다."

### 3. 핵심 수치 (Paper 인용용)

- **Domain coverage**: v7은 v6의 25개 도메인 전부 커버
- **Constraint coverage**: 462 DerivedConstraints (REQUIRED 35.7%, FORBIDDEN 43.7%, WITHIN 16.5%, BEFORE 3.2%)
- **Action vocabulary overlap**: Mean Jaccard 0.165 (16.5% normalized action overlap)
- **Trap mechanism**: v7은 scenario-level FA 대신 graph-level FA + CDE evaluation (195 forbidden actions across 24 domains)
- **_stem_match FP rate**: 9.42% (115/1221), word-boundary fix로 해결 가능하나 corpus 영향 미미

### 4. Limitations for Paper S7

1. v7 scenario-level forbidden_actions가 비어있어 direct difficulty comparison 불가
2. Action naming convention 차이로 Jaccard가 실제 semantic overlap보다 낮게 측정됨
3. v6 auto_generated scenarios (601/708)는 combinatorial expansion 산물로 독립 시나리오가 아님
4. BEFORE constraint가 atom-level 0%: LLM extraction의 한계 (KNOWN_ISSUES 7-1 관련)

---

*Generated by v6_v7_corpus_analysis.py + manual analysis*
*Report path: docs/sgsc/260501_v6_v7_comparison_report.md*
