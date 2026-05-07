# EXP-C: Held-out Domain Generalizability Analysis

**Main graphs**: 20
**Held-out graphs**: 5

## Analysis 1: Derivation Success

| Graph | Label | Rules | Scenarios | Avg Constraints | Failures |
|-------|-------|-------|-----------|-----------------|----------|
| acls_cardiac_arrest | main | 18 | 42 | 39.64 | 0 |
| ada_dka_management | main | 14 | 28 | 51.21 | 0 |
| aha_chest_pain_evaluat | main | 10 | 21 | 47.24 | 0 |
| aha_heart_failure_2022 | main | 8 | 40 | 25.32 | 0 |
| aha_stroke_2019 | main | 7 | 21 | 25.86 | 0 |
| anaphylaxis_management | main | 8 | 17 | 39.06 | 0 |
| atrial_fibrillation | main | 7 | 18 | 13.22 | 0 |
| cap_pneumonia | main | 9 | 18 | 16.06 | 0 |
| copd_exacerbation | main | 8 | 16 | 11.12 | 0 |
| gi_bleeding | main | 8 | 14 | 14.79 | 0 |
| gina_asthma_exacerbati | main | 21 | 43 | 51.88 | 0 |
| hypertensive_emergency | main | 9 | 11 | 11.64 | 0 |
| idsa_meningitis | main | 16 | 33 | 27.88 | 0 |
| kdigo_aki_full | main | 19 | 61 | 31.15 | 0 |
| kdigo_contrast_aki | main | 16 | 38 | 48.26 | 0 |
| pulmonary_embolism | main | 9 | 24 | 12.04 | 0 |
| ssc_sepsis_hour1_bundl | main | 10 | 14 | 27.79 | 0 |
| status_epilepticus | main | 8 | 17 | 39.65 | 0 |
| toxicology_management | main | 18 | 24 | 27.75 | 0 |
| universal_clinical_saf | main | 6 | 18 | 8.72 | 0 |
| aabb_transfusion | holdout | 5 | 13 | 17.54 | 0 |
| aba_burn_resuscitation | holdout | 4 | 18 | 31.72 | 0 |
| acog_obstetric_hemorrh | holdout | 4 | 10 | 9.0 | 0 |
| apa_agitation_manageme | holdout | 6 | 15 | 13.27 | 0 |
| pals_pediatric_emergen | holdout | 4 | 11 | 15.82 | 0 |

### Statistical Comparison (Main vs Held-out)

- Rules: U=99.5, p=0.0008
- Scenarios: U=88.0, p=0.0106
- Constraints: U=68.0, p=0.2431

## Analysis 2: Auto Scenario Quality

| Metric | Main | Held-out |
|--------|------|----------|
| n_scenarios | 535 | 66 |
| complexity_mean | 1.01 | 0.24 |
| constraint_density_mean | 27.89 | 17.17 |
| expected_count_mean | 14.63 | 8.89 |
| trap_ratio | 0.847 | 0.788 |

## Analysis 3: Structural Coverage

| Graph | Rule Coverage | Action Coverage |
|-------|-------------|-----------------|
| aabb_transfusion | 0.800 | 0.600 |
| aba_burn_resuscitation | 1.000 | 0.875 |
| acls_cardiac_arrest | 1.000 | 1.000 |
| acog_obstetric_hemorrh | 0.750 | 0.400 |
| ada_dka_management | 0.857 | 0.567 |
| aha_chest_pain_evaluat | 1.000 | 1.000 |
| aha_heart_failure_2022 | 0.875 | 0.603 |
| aha_stroke_2019 | 0.857 | 0.451 |
| apa_agitation_manageme | 1.000 | 0.312 |
| pals_pediatric_emergen | 1.000 | 0.533 |

## Analysis 4: Edge Cases

- Main condition patterns: 38
- Held-out condition patterns: 11
- Unique held-out patterns: 17
- Parsing failures: 0

### Unique Held-out Patterns

- `aabb_transfusion:TRANS-STABLE-NO-TRANSFUSE-ABOVE-7` — `patient.VAR(STR, NUM) >= NUM and STR in patient.VAR(STR, {})`
- `aabb_transfusion:TRANS-JEHOVAH-NO-BLOOD` — `STR in patient.VAR(STR, []) or STR in patient.VAR(STR, [])`
- `aabb_transfusion:TRANS-ANAPHYLAXIS-EPI` — `STR in patient.VAR(STR, {})`
- `aabb_transfusion:TRANS-ANAPHYLAXIS-EPI-FORBIDDEN` — `STR in patient.VAR(STR, {})`
- `aba_burn_resuscitation:BURN-CYANIDE-HYDROXOCOBALAMIN` — `STR in patient.VAR(STR, [])`
- `aba_burn_resuscitation:BURN-CYANIDE-HYDROXOCOBALAMIN-FORBIDDEN` — `STR in patient.VAR(STR, [])`
- `aba_burn_resuscitation:BURN-CHEST-ESCHAR-VENTILATION` — `STR in patient.VAR(STR, [])`
- `aba_burn_resuscitation:BURN-CHEST-ESCHAR-VENTILATION-FORBIDDEN` — `STR in patient.VAR(STR, [])`
- `apa_agitation_management:PSYCH-ETOH-NO-BENZO-MONOTHERAPY` — `STR in patient.VAR(STR, {})`
- `apa_agitation_management:PSYCH-QTC-NO-HALOPERIDOL` — `patient.VAR(STR, NUM) > NUM or STR in patient.VAR`
