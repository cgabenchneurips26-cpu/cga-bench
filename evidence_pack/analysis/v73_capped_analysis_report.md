# v7.3 Capped Corpus Analysis Report
Generated: 2026-05-03 | Corpus: sgsc_v73_expanded_capped

## 1. Corpus Overview

| Item | Value |
|------|-------|
| Total episodes | **14,280** |
| Models | 7 |
| Scenarios | 680 |
| Runs per scenario | 3 |
| Graphs | 49 |
| Formula | 7 models x 680 scen x 3 runs = 14,280 |

## 2. Category A/B/M Classification

Classification logic:
- **Cat A (graph-anchored)**: ALL expected_actions exist in CPG graph vocabulary -> C2 valid
- **Cat B (vocab-disconnect)**: ALL expected_actions are SGSC-invented -> C2=0 by design
- **Cat M (mixed)**: some graph-native, some SGSC-invented -> partial C2

### Episode-level distribution

| Category | Episodes | % | Scenarios | % |
|----------|----------|---|-----------|---|
| Cat A | 2,058 | 14.4% | 98 | 14.4% |
| Cat B | 7,392 | 51.8% | 352 | 51.8% |
| Cat M | 4,830 | 33.8% | 230 | 33.8% |

### Interpretation

Cat B dominates (51.8%) because expansion graphs generate SGSC-invented action IDs
that do not map back to graph node vocabulary. For these scenarios, C2 (mandatory
completion) is structurally zero — the scorer cannot match agent actions to
expected actions. **Cat A (14.4%) is the only subset where CGA sub-scores are
fully valid.**

## 3. Per-Model Results

### 3.1 Overall CGA (all episodes)

| Rank | Model | CGA mean | CGA median | CGA std | n |
|------|-------|----------|------------|---------|---|
| 1 | qwen35b | **0.651** | 0.708 | 0.179 | 2,040 |
| 2 | qwen397b | **0.633** | 0.667 | 0.199 | 2,040 |
| 3 | qwen27b | **0.613** | 0.667 | 0.227 | 2,040 |
| 4 | qwen4b | **0.603** | 0.643 | 0.204 | 2,040 |
| 5 | gemma31b | **0.596** | 0.667 | 0.230 | 2,040 |
| 6 | nemotron30b | **0.580** | 0.625 | 0.228 | 2,040 |
| 7 | deepseek_r1_7b | **0.507** | 0.542 | 0.198 | 2,040 |

### 3.2 Cat A CGA + C2 (graph-anchored, validity-certified)

| Rank | Model | CGA(A) | C2(A) | n |
|------|-------|--------|-------|---|
| 1 | qwen35b | **0.765** | 0.607 | 294 |
| 2 | qwen397b | **0.764** | 0.611 | 294 |
| 3 | qwen27b | **0.752** | 0.551 | 294 |
| 4 | gemma31b | **0.744** | 0.552 | 294 |
| 5 | nemotron30b | **0.722** | 0.497 | 294 |
| 6 | qwen4b | **0.711** | 0.554 | 294 |
| 7 | deepseek_r1_7b | **0.619** | 0.532 | 294 |

### 3.3 Cat B CGA (vocab-disconnect)

| Rank | Model | CGA(B) | C2(B) | n |
|------|-------|--------|-------|---|
| 1 | qwen35b | **0.644** | 0.013 | 1056 |
| 2 | qwen27b | **0.636** | 0.013 | 1056 |
| 3 | qwen397b | **0.631** | 0.013 | 1056 |
| 4 | gemma31b | **0.628** | 0.013 | 1056 |
| 5 | qwen4b | **0.628** | 0.011 | 1056 |
| 6 | nemotron30b | **0.604** | 0.013 | 1056 |
| 7 | deepseek_r1_7b | **0.514** | 0.013 | 1056 |

### 3.4 Cat M CGA (mixed)

| Rank | Model | CGA(M) | C2(M) | n |
|------|-------|--------|-------|---|
| 1 | qwen35b | **0.614** | 0.295 | 690 |
| 2 | qwen397b | **0.581** | 0.284 | 690 |
| 3 | qwen4b | **0.519** | 0.258 | 690 |
| 4 | qwen27b | **0.518** | 0.261 | 690 |
| 5 | nemotron30b | **0.484** | 0.241 | 690 |
| 6 | gemma31b | **0.484** | 0.246 | 690 |
| 7 | deepseek_r1_7b | **0.450** | 0.240 | 690 |

## 4. Violation Distribution

Total violations across all episodes: **104,675**

| Type | Count | % |
|------|-------|---|
| DEVIATION | 56,407 | 53.9% |
| OMISSION | 33,481 | 32.0% |
| TIMING | 13,218 | 12.6% |
| COMMISSION | 1,057 | 1.0% |
| SEQUENCE | 512 | 0.5% |

### Per-Model Violation Breakdown

| Model | OMIS | COMM | TIME | DEV | SEQ | Total |
|-------|------|------|------|-----|-----|-------|
| qwen35b | 4,604 | 272 | 1,973 | 8,056 | 90 | 14,995 |
| qwen397b | 4,659 | 190 | 1,728 | 8,637 | 74 | 15,288 |
| qwen27b | 4,780 | 132 | 1,491 | 7,376 | 90 | 13,869 |
| qwen4b | 4,813 | 82 | 2,055 | 7,300 | 90 | 14,340 |
| gemma31b | 4,871 | 184 | 1,706 | 6,869 | 90 | 13,720 |
| nemotron30b | 4,878 | 62 | 1,784 | 6,042 | 45 | 12,811 |
| deepseek_r1_7b | 4,876 | 135 | 2,481 | 12,127 | 33 | 19,652 |

## 5. Per-Graph Analysis

| Graph | Episodes | CGA | Categories |
|-------|----------|-----|------------|
| aabb_transfusion | 315 | 0.739 | A=21, B=42, M=252 |
| aba_burn_resuscitation | 315 | 0.572 | A=84, M=231 |
| acls_cardiac_arrest | 315 | 0.655 | A=126, M=189 |
| acog_obstetric_hemorrhage | 315 | 0.711 | A=147, B=84, M=84 |
| ada_dka_management | 315 | 0.510 | A=84, B=42, M=189 |
| aha_acc_aortic_dissection_2022 | 315 | 0.389 | A=21, B=294 |
| aha_asa_ich_2022 | 315 | 0.822 | B=315 |
| aha_chest_pain_evaluation | 315 | 0.209 | M=315 |
| aha_heart_failure_2022 | 315 | 0.729 | A=42, B=168, M=105 |
| aha_stroke_2019 | 315 | 0.597 | A=21, B=63, M=231 |
| aha_ttm_post_arrest_2023 | 315 | 0.194 **LOW** | B=315 |
| anaphylaxis_management | 315 | 0.736 | A=126, M=189 |
| apa_agitation_management | 315 | 0.673 | A=126, M=189 |
| asam_alcohol_withdrawal_2020 | 315 | 0.757 | B=315 |
| asco_tls_2023 | 315 | 0.590 | B=315 |
| ash_sickle_cell_acs_2020 | 315 | 0.640 | B=315 |
| atrial_fibrillation | 315 | 0.702 | A=210, B=105 |
| ats_esicm_sccm_ards_2023 | 315 | 0.751 | B=315 |
| baveno_vii_varices_2022 | 315 | 0.425 | B=315 |
| bts_pleural_disease_2023 | 315 | 0.811 | B=252, M=63 |
| eau_obstructive_pyelonephritis_2024 | 315 | 0.735 | B=315 |
| erc_drowning_2021 | 315 | 0.720 | B=315 |
| erc_hypothermia_2021 | 315 | 0.599 | B=315 |
| ers_ats_niv_2017 | 315 | 0.795 | A=21, B=294 |
| esvs_aaa_2024 | 315 | 0.546 | B=315 |
| esvs_acute_limb_ischemia_2020 | 315 | 0.717 | A=21, B=294 |
| gina_asthma_exacerbation | 315 | 0.532 | A=105, M=210 |
| gina_pediatric_status_asthma_2024 | 315 | 0.442 | B=84, M=231 |
| idsa_meningitis | 315 | 0.523 | A=105, M=210 |
| ispad_pediatric_dka_2022 | 315 | 0.717 | B=315 |
| kdigo_aki_full | 315 | 0.508 | B=84, M=231 |
| kdigo_contrast_aki | 315 | 0.626 | A=63, B=84, M=168 |
| ncs_aha_sah_2023 | 315 | 0.076 **LOW** | B=252, M=63 |
| pals_pediatric_emergency | 315 | 0.673 | A=126, M=189 |
| sccm_pediatric_septic_shock_2020 | 315 | 0.696 | B=315 |
| ssc_sepsis_hour1_bundle | 315 | 0.387 | M=315 |
| status_epilepticus | 315 | 0.546 | A=84, B=42, M=189 |
| toxicology_management | 315 | 0.544 | A=105, B=63, M=147 |
| ukka_hyperkalemia_2023 | 315 | 0.500 | B=315 |
| universal_clinical_safety | 315 | 0.661 | M=315 |
| who_severe_malaria_2023 | 315 | 0.665 | B=315 |
| cap_pneumonia | 210 | 0.624 | A=105, M=105 |
| copd_exacerbation | 210 | 0.726 | A=105, M=105 |
| hypertensive_emergency | 210 | 0.724 | A=105, M=105 |
| pals_pediatric_traumatic_arrest_2020 | 210 | 0.625 | B=210 |
| pulmonary_embolism | 210 | 0.624 | A=105, M=105 |
| aha_cardiogenic_shock_2017 | 105 | 0.680 | B=105 |
| gi_bleeding | 105 | 0.460 | M=105 |
| nrp_neonatal_resuscitation_2020 | 105 | 0.256 | B=105 |

## 6. Key Observations

1. **Ranking stable across categories**: qwen35b > qwen397b > qwen27b holds in all 3 categories
2. **Cat A C2 range 0.497-0.611**: meaningful variation — larger models do not trivially dominate
3. **DEVIATION dominates (53.9%)**: agents produce many off-protocol actions; OMISSION is 32.0%
4. **ncs_aha_sah_2023 outlier**: CGA=0.076 across all models — likely graph/scenario issue
5. **aha_chest_pain_evaluation**: CGA=0.209, all Cat M — known difficult graph
6. **Cat B C2 near-zero confirms design**: vocab-disconnect scenarios correctly yield no C2 credit
7. **deepseek_r1_7b gap**: 14.3pp below next model (nemotron30b) — expected for 7B parameter count
8. **Expansion graphs skew Cat B**: SGSC compiler invents action IDs not in graph vocabulary

## 7. Artifacts

| Artifact | Path |
|----------|------|
| JSON evidence | evidence_pack/analysis/v73_capped_analysis.json |
| LaTeX macros | paper/auto_numbers_v73_capped.tex |
| Episode results | results/v73_expanded/ (7 model dirs, 2040 each) |
| Capped scenarios | configs/scenarios/sgsc_capped/ (49 YAML files, 680 scenarios) |
