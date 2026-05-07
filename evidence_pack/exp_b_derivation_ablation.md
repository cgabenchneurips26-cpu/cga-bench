# EXP-B: Constraint Derivation Engine Ablation Study

**Graphs analyzed**: 25
**Auto scenarios used**: 601
**Manual scenarios used**: 107

## Ablation Results

### Ablation A: Unconditional Activation

All conditional rules activated regardless of patient context.
- Baseline constraints: 662
- Ablated constraints: 1202
- **Overgeneration rate: 81.6%**

### Ablation B: No Type Distinction

All constraints mapped to REQUIRED (losing FORBIDDEN/BEFORE/WITHIN).
- Avg constraint types (normal): 2.86
- Avg constraint types (ablated): 3.41
- **Differentiation loss: -19.1%**
- Scenarios losing FORBIDDEN: 601

### Ablation C: Random Patient Context

Random patient instead of PatientGenerator-derived patient.
- Evaluated: 200 scenarios
- **FP rate: 33.9%**
- **FN rate: 35.2%**

## Baseline-Manual Comparison

Engine-derived constraints vs manual expected/forbidden actions.
- Evaluated: 105 scenarios
- **Precision: 0.217 ± 0.126**
- **Recall: 0.481 ± 0.272**

## Scalability

| Graph | Nodes | Rules | Constraints | Time (ms) |
|-------|-------|-------|-------------|-----------|
| toxicology_management | 6 | 25 | 26 | 0.9 |
| acls_cardiac_arrest | 6 | 24 | 38 | 0.9 |
| gina_asthma_exacerbation | 5 | 24 | 47 | 0.9 |
| kdigo_aki_full | 13 | 24 | 16 | 1.2 |
| idsa_meningitis | 5 | 20 | 27 | 0.8 |
| kdigo_contrast_aki | 7 | 19 | 38 | 0.7 |
| ada_dka_management | 8 | 17 | 49 | 0.6 |
| anaphylaxis_management | 5 | 13 | 36 | 0.4 |
| cap_pneumonia | 3 | 13 | 11 | 0.6 |
| ssc_sepsis_hour1_bundle | 7 | 11 | 25 | 0.6 |
| status_epilepticus | 5 | 11 | 38 | 0.4 |
| aha_chest_pain_evaluation | 11 | 10 | 46 | 0.5 |
| gi_bleeding | 2 | 10 | 11 | 0.3 |
| hypertensive_emergency | 2 | 10 | 10 | 0.3 |
| pulmonary_embolism | 3 | 10 | 10 | 0.3 |
| aha_heart_failure_2022 | 24 | 9 | 21 | 1.1 |
| universal_clinical_safety | 3 | 9 | 6 | 0.3 |
| apa_agitation_management | 4 | 8 | 11 | 0.5 |
| copd_exacerbation | 2 | 8 | 10 | 0.3 |
| aabb_transfusion | 4 | 7 | 14 | 0.9 |
| aba_burn_resuscitation | 6 | 7 | 26 | 0.5 |
| aha_stroke_2019 | 25 | 7 | 23 | 1.1 |
| atrial_fibrillation | 3 | 7 | 12 | 0.2 |
| pals_pediatric_emergency | 4 | 5 | 13 | 0.3 |
| acog_obstetric_hemorrhage | 4 | 4 | 8 | 0.3 |
