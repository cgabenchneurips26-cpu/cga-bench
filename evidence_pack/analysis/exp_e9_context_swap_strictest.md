# E9 Follow-up G2 -- Context-Swap x Strictest Authority

Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (section B)

## Summary

Among 238 conditional FORBIDDEN matched pairs, 154 (64.7%) retain a Class-I + LOE-A or strong-society source-node under the strictest authority cut, spanning 17 graphs. Action-set evaluators still detect 0% of these pairs (constructive proof). TCC detects 100% (by definition of the trigger_range witness).

## S1 vs S2 Retention -- per-graph table

| Graph | S1 retained | S2 retained | Held-out |
|---|---|---|---|
| aabb_transfusion | 5 | 5 | yes |
| aba_burn_resuscitation | 3 | 0 | yes |
| acls_cardiac_arrest | 17 | 10 | no |
| acog_obstetric_hemorrhage | 3 | 3 | yes |
| ada_dka_management | 13 | 10 | no |
| aha_chest_pain_evaluation | 10 | 10 | no |
| aha_heart_failure_2022 | 8 | 5 | no |
| aha_stroke_2019 | 7 | 2 | no |
| anaphylaxis_management | 8 | 5 | no |
| apa_agitation_management | 6 | 4 | yes |
| atrial_fibrillation | 6 | 0 | no |
| cap_pneumonia | 8 | 8 | no |
| copd_exacerbation | 8 | 0 | no |
| gi_bleeding | 6 | 0 | no |
| gina_asthma_exacerbation | 19 | 16 | no |
| hypertensive_emergency | 8 | 0 | no |
| idsa_meningitis | 15 | 15 | no |
| kdigo_aki_full | 18 | 18 | no |
| kdigo_contrast_aki | 15 | 15 | no |
| pals_pediatric_emergency | 4 | 0 | yes |
| pulmonary_embolism | 9 | 9 | no |
| ssc_sepsis_hour1_bundle | 10 | 0 | no |
| status_epilepticus | 8 | 8 | no |
| toxicology_management | 17 | 11 | no |

## Headline comparison

| Metric | S1 (default) | S2 (strictest) |
|---|---|---|
| Retained pairs | 231 / 238 (97.1%) | 154 / 238 (64.7%) |
| Distinct graphs | 24 | 17 |
| Distinct forbidden actions | 406 | 272 |
| Held-out pairs | 21 | 12 |
| In-domain pairs | 210 | 142 |

## S2 severity breakdown

| Severity | Count |
|---|---|
| HIGH | 85 |
| CRITICAL | 67 |
| MODERATE | 2 |

## S2 condition_type breakdown

| Condition type | Count |
|---|---|
| comorbidity | 60 |
| lab_value | 34 |
| other | 31 |
| medication | 19 |
| timing | 6 |
| allergy | 3 |
| history | 1 |

## Pre-reg gate verdict

| Gate | Threshold | Value | PASS |
|---|---|---|---|
| retained_ge_30 | >= 30 | 154 | YES |
| domains_ge_8 | >= 8 | 17 | YES |
| ASC detection | = 0% | 0.0% | YES |
| PAF detection | = 0% | 0.0% | YES |
| CwT detection | = 0% | 0.0% | YES |
| TCC detection | = 100% | 100.0% | YES |

**All gates PASS: YES**

## Paper-ready one-liner

Among 238 conditional FORBIDDEN matched pairs, 154 (64.7%) retain a Class-I + LOE-A or strong-society source-node under the strictest authority cut, spanning 17 graphs (152 / 154 = 98.7% are HIGH or CRITICAL severity). Action-set evaluators detect 0% of these pairs (constructive); TCC detects 100%.
