# 자가검토: 신규 자동 가이드라인 5종 시나리오 평가 (v5 Generator)

**날짜**: 2026-04-29
**대상**: v5 generator로 생성된 5개 신규 auto 가이드라인 × 11 시나리오 = 55개

## 1. 대상 가이드라인

| # | Graph ID | 도메인 | 원본 가이드라인 |
|---|----------|--------|----------------|
| 1 | `btf_severe_tbi_2020` | 신경외과/외상 | Brain Trauma Foundation 4th Ed. |
| 2 | `asco_tls_2023` | 종양학 | ASCO Tumor Lysis Syndrome |
| 3 | `erc_hypothermia_2021` | 응급의학 | ERC Accidental Hypothermia |
| 4 | `baveno_vii_varices_2022` | 소화기 | Baveno VII Portal Hypertension |
| 5 | `asam_alcohol_withdrawal_2020` | 중독의학 | ASAM Alcohol Withdrawal |

## 2. 검증 파이프라인 결과

### 2.1 Plausibility Validator (Rules A-F)

| 항목 | 결과 |
|------|------|
| 시나리오 수 | 55 |
| ERROR | **0** |
| WARNING | 55 (모두 Rule D — generic chief complaint "presenting symptoms") |
| Rule E (provenance) | PASS — 55/55 |
| Rule F (FA traceability) | PASS — 55/55 |

### 2.2 CPG Engine 평가

| 항목 | 결과 |
|------|------|
| 정상 평가 (OK) | **55/55** (100%) |
| 실패 (FAIL) | 0 |
| 평균 A_G (allowed) | 9.8 |
| 평균 M_G (mandatory) | 3.0 |
| 평균 F_G (forbidden) | 0.8 |

#### Per-graph CPG engine output

| Graph | A_G | M_G | F_G | D_G |
|-------|-----|-----|-----|-----|
| asam_alcohol_withdrawal_2020 | 12 | 3 | 0 | 3 |
| asco_tls_2023 | 11 | 3 | 0 | 3 |
| baveno_vii_varices_2022 | 6 | 2 | 2 | 2 |
| btf_severe_tbi_2020 | 10 | 4 | 2 | 3 |
| erc_hypothermia_2021 | 10 | 3 | 0 | 2 |

### 2.3 Provenance 검증

| 항목 | 결과 |
|------|------|
| `_generation_metadata` 존재 | 55/55 (100%) |
| `generator_version` = "v5" | 55/55 |
| `generation_phase` 유효 | 55/55 (branch=30, universal_trap=20, baseline=5) |
| `source_node_ids` 비어있지 않음 | 55/55 |
| source node가 그래프에 존재 | 55/55 |
| FA provenance 완전 커버 | 55/55 |

### 2.4 Phase 분포 (Per-graph)

| Graph | branch | universal_trap | baseline | 합계 |
|-------|--------|---------------|----------|------|
| 각 그래프 | 6 | 4 | 1 | 11 |
| 전체 | 30 | 20 | 5 | 55 |

## 3. 상세 Spot-Check (3개 시나리오)

### 3.1 btf_severe_tbi_2020_acute_deterioration_severe (branch)

- **환자**: 45세 F, 65kg, comorbidity=[obesity]
- **활력징후**: HR=105, BP=117/69, MAP=85, SpO2=92, Temp=38.0, RR=16
- **기대 행위**: 10개 (assess_glasgow_coma_scale, secure_airway, ct_head, monitor_icp 등)
- **금지 행위**: 2개 — `give_corticosteroids_for_tbi` ← node:primary_treatment, `give_prophylactic_hyperventilation` ← node:initial_assessment
- **GT**: 5개 키 (ECG, CXR, CBC, BMP, lactate=6.04)
- **임상 타당성**: Severe TBI에 맞는 프레젠테이션. 코르티코스테로이드/과호흡 금지는 BTF 가이드라인 Level I 근거
- **Provenance**: PASS — 모든 FA에 node-level 출처, 3개 source node 모두 그래프에 존재

### 3.2 asco_tls_2023_renal_nsaid (universal_trap)

- **환자**: 65세 F, comorbidity=[copd], contraindication=[renal_impairment]
- **금지 행위**: 6개 — `alkalinize_urine` ← node, `give_allopurinol_with_rasburicase` ← node, `give_rasburicase_with_g6pd_deficiency` ← node, `give_nsaid/ibuprofen/ketorolac` ← trap:renal_nsaid
- **Provenance**: PASS — node-source와 trap-source 모두 정확히 기록됨
- **임상 타당성**: TLS에서 소변 알칼리화 금지 (인산칼슘 침전), G6PD 결핍시 라스부리카제 금지는 ASCO 가이드라인 근거. Renal NSAID trap도 임상적으로 적절

### 3.3 asam_alcohol_withdrawal_2020_baseline_clean (baseline)

- **금지 행위**: 0개 (baseline이므로 정상)
- **기대 행위**: 10개 (CIWA-Ar 평가, diazepam loading, thiamine IV 등)
- **Provenance**: `forbidden_action_provenance: {}` (빈 dict — baseline이므로 정상)
- **임상 타당성**: 알코올 금단 프로토콜의 clean happy-path 테스트

## 4. Sanity Check 결과

| 검사 항목 | 결과 | 판정 |
|----------|------|------|
| Branch에 M_G > 0 | 30/30 (100%) | PASS |
| Trap에 scenario-level FA 존재 | 20/20 (100%) | PASS |
| Baseline에 scenario-level FA = 0 | 5/5 (100%) | PASS |
| Engine F_G와 scenario FA 불일치 | 12/20 trap에서 engine F_G=0 | **참고** (아래 설명) |

### Engine F_G vs Scenario FA 불일치 설명

Universal trap 시나리오는 두 종류의 FA를 가짐:
1. **Graph node-level FA**: 그래프 노드에 정의된 금지 행위 (engine이 직접 반환)
2. **Trap-level FA**: `_UNIVERSAL_TRAPS`에서 주입된 금지 행위 (시나리오에만 기록)

asam/asco/erc 그래프는 node-level FA가 entry node에 없어서 engine이 F_G=0을 반환하지만, 시나리오에는 trap FA가 정상 포함됨. 이는 **설계 의도대로** — trap FA는 시나리오 평가 시 별도 검증됨.

btf/baveno는 node-level FA가 있어서 engine도 F_G>0을 반환.

## 5. 발견된 문제점

### P1: Chief Complaint 일률적 "presenting symptoms" (WARNING 수준)

모든 55개 시나리오의 chief complaint가 `presenting symptoms`로 동일. 도메인별로 다르게 생성되어야 함:
- btf → "head trauma", "altered mental status"
- asco_tls → "tumor lysis syndrome concern", "chemotherapy monitoring"
- erc_hypothermia → "hypothermia", "environmental exposure"
- baveno → "GI bleeding", "hematemesis"
- asam → "alcohol withdrawal", "tremor and agitation"

**영향**: 임상 현실성 저하, LLM agent가 chief complaint에서 도메인 힌트를 못 받음
**심각도**: Medium — 기능적으로는 정상 작동하나 리뷰어 질문 가능

### P2: Working Diagnosis 다양성 부족

Branch 시나리오의 working_diagnosis가 `acute_deterioration`, `undifferentiated_emergency` 등 generic 값만 사용. Graph 도메인에 특화된 진단명이 필요:
- btf → "severe_traumatic_brain_injury"
- asco_tls → "tumor_lysis_syndrome_high_risk"

### P3: 동일 seed → 동일 vitals (cross-graph)

4/5 그래프의 `acute_deterioration_mild` 시나리오가 동일한 vitals (HR=105, SBP=117, MAP=85 등). seed가 같으면 vitals pool이 같은 값을 반환하기 때문. 기능적 문제는 아니나 다양성 관점에서 개선 여지.

## 6. 종합 판정

| 항목 | 판정 |
|------|------|
| Plausibility Validator | **PASS** (0 ERROR) |
| CPG Engine 정상 평가 | **PASS** (55/55) |
| Provenance 완전성 | **PASS** (100%) |
| FA Traceability | **PASS** (100%) |
| Phase 분포 정합성 | **PASS** |
| 임상 타당성 (spot-check) | **PASS** (minor issues) |

**결론**: v5 generator는 신규 auto 가이드라인에서도 정상 작동. 모든 시나리오가 CPG engine으로 평가 가능하며, provenance metadata가 완전하게 기록됨. chief complaint 다양화(P1)와 working diagnosis 특화(P2)는 v6에서 개선 권장.
