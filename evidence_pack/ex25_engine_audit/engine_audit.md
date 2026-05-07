# EX-25: Engine Structural Audit

**Graphs:** 25
**Nodes:** 167
**Constraints:** 1049
**Unique actions:** 611
**Constraints/node:** 6.3

## Constraint Type Distribution

| Type | Count | % |
|------|-------|---|
| MUST | 557 | 53.1% |
| FORBIDDEN | 212 | 20.2% |
| WITHIN | 215 | 20.5% |
| BEFORE | 65 | 6.2% |

## Audit Results

| Dimension | Count | Rate | Status |
|-----------|-------|------|--------|
| Unreachable nodes | 61 | 36.5% | WARN |
| Dead-end nodes | 96 | 57.5% | INFO (legitimate terminals) |
| Contradictions | 0 | 0.0% | CLEAN |
| Duplicates | 98 | 9.3% | WARN |
| Provenance complete | 167/167 | 100.0% | CLEAN |

## Per-Graph Summary (sorted by constraint count)

| Graph | Nodes | Constraints | Unreach | Dead | Contra | Prov% |
|-------|-------|-------------|---------|------|--------|-------|
| aha_stroke_2019 | 25 | 120 | 24 | 25 | 0 | 100.0% |
| aha_heart_failure_2022 | 24 | 92 | 23 | 24 | 0 | 100.0% |
| ada_dka_management | 8 | 82 | 0 | 1 | 0 | 100.0% |
| aha_chest_pain_evaluation | 11 | 66 | 0 | 4 | 0 | 100.0% |
| kdigo_aki_full | 13 | 63 | 12 | 13 | 0 | 100.0% |
| gina_asthma_exacerbation | 5 | 58 | 0 | 1 | 0 | 100.0% |
| aba_burn_resuscitation | 6 | 53 | 0 | 1 | 0 | 100.0% |
| kdigo_contrast_aki | 7 | 51 | 0 | 3 | 0 | 100.0% |
| status_epilepticus | 5 | 51 | 0 | 1 | 0 | 100.0% |
| acls_cardiac_arrest | 6 | 49 | 0 | 1 | 0 | 100.0% |
| anaphylaxis_management | 5 | 45 | 0 | 1 | 0 | 100.0% |
| ssc_sepsis_hour1_bundle | 7 | 40 | 0 | 2 | 0 | 100.0% |
| idsa_meningitis | 5 | 34 | 0 | 1 | 0 | 100.0% |
| pals_pediatric_emergency | 4 | 33 | 0 | 3 | 0 | 100.0% |
| toxicology_management | 6 | 33 | 0 | 1 | 0 | 100.0% |
| aabb_transfusion | 4 | 32 | 0 | 1 | 0 | 100.0% |
| apa_agitation_management | 4 | 31 | 0 | 2 | 0 | 100.0% |
| acog_obstetric_hemorrhage | 4 | 27 | 0 | 1 | 0 | 100.0% |
| cap_pneumonia | 3 | 16 | 0 | 2 | 0 | 100.0% |
| pulmonary_embolism | 3 | 15 | 1 | 2 | 0 | 100.0% |
| atrial_fibrillation | 3 | 13 | 1 | 2 | 0 | 100.0% |
| copd_exacerbation | 2 | 13 | 0 | 1 | 0 | 100.0% |
| gi_bleeding | 2 | 13 | 0 | 1 | 0 | 100.0% |
| hypertensive_emergency | 2 | 12 | 0 | 1 | 0 | 100.0% |
| universal_clinical_safety | 3 | 7 | 0 | 1 | 0 | 100.0% |

## Duplicate Details (first 20)

- aba_burn_resuscitation: BEFORE(calculate_parkland_formula) in fluid_resuscitation and fluid_resuscitation
- aba_burn_resuscitation: BEFORE(calculate_parkland_formula) in fluid_resuscitation and fluid_resuscitation
- aba_burn_resuscitation: BEFORE(start_lactated_ringers) in fluid_resuscitation and fluid_resuscitation
- acls_cardiac_arrest: FORBIDDEN(delay_cpr) in initial_assessment and rhythm_assessment
- acls_cardiac_arrest: FORBIDDEN(delay_cpr) in initial_assessment and shockable_pathway
- acls_cardiac_arrest: FORBIDDEN(delay_defibrillation) in initial_assessment and shockable_pathway
- acls_cardiac_arrest: BEFORE(give_epinephrine_1mg_iv) in shockable_pathway and shockable_pathway
- acls_cardiac_arrest: BEFORE(give_amiodarone_300mg) in shockable_pathway and shockable_pathway
- acls_cardiac_arrest: FORBIDDEN(delay_cpr) in initial_assessment and non_shockable_pathway
- acls_cardiac_arrest: MUST(evaluate_reversible_causes) in non_shockable_pathway and reversible_causes
- acls_cardiac_arrest: FORBIDDEN(delay_cpr) in initial_assessment and reversible_causes
- acls_cardiac_arrest: WITHIN(evaluate_reversible_causes) in non_shockable_pathway and reversible_causes
- ada_dka_management: MUST(start_iv_fluid_ns) in initial_assessment and severe_dka_pathway
- ada_dka_management: FORBIDDEN(discharge_home) in initial_assessment and severe_dka_pathway
- ada_dka_management: MUST(monitor_glucose_hourly) in insulin_therapy and ongoing_monitoring
- ada_dka_management: WITHIN(monitor_glucose_hourly) in insulin_therapy and ongoing_monitoring
- aha_chest_pain_evaluation: MUST(give_aspirin_loading) in stemi_pathway and nste_acs_pathway
- aha_chest_pain_evaluation: MUST(give_anticoagulation) in stemi_pathway and nste_acs_pathway
- aha_chest_pain_evaluation: FORBIDDEN(discharge_home) in stemi_pathway and nste_acs_pathway
- aha_chest_pain_evaluation: BEFORE(give_nitrates_if_indicated) in stemi_pathway and nste_acs_pathway