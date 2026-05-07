# EX-20: No-Context Matched Pair — Theorem Case 4 Witness

**Total conditional FORBIDDEN rules**: 240
**Well-formed pairs**: 238 (across 25 graphs)
**Held-out / In-domain**: 22 / 216
**Distinct forbidden actions**: 421

## Detection Rates

| Evaluator Type | Detection Rate | Reason |
|----------------|---------------|--------|
| TCC (CGA-Bench) | 100.0% | Evaluates conditional constraints with patient state |
| Action-set (AC/PAF/CwT) | 0.0% | Context-free; identical action set → identical verdict |

## Condition Type Breakdown

| Type | Count |
|------|-------|
| comorbidity | 101 |
| other | 54 |
| lab_value | 40 |
| medication | 23 |
| timing | 9 |
| allergy | 7 |
| history | 4 |

## Severity Breakdown

| Severity | Count |
|----------|-------|
| HIGH | 131 |
| CRITICAL | 102 |
| MODERATE | 5 |

## Per-Graph Coverage

| Graph | Rules | Distinct Actions | Severity | Held-out |
|-------|-------|-----------------|----------|----------|
| aabb_transfusion | 5 | 11 | HIGH:2, CRITICAL:3 | yes |
| aba_burn_resuscitation | 4 | 7 | HIGH:2, CRITICAL:2 | yes |
| acls_cardiac_arrest | 17 | 26 | HIGH:11, CRITICAL:6 |  |
| acog_obstetric_hemorrhage | 3 | 5 | CRITICAL:2, HIGH:1 | yes |
| ada_dka_management | 13 | 25 | HIGH:6, CRITICAL:7 |  |
| aha_chest_pain_evaluation | 10 | 27 | CRITICAL:6, HIGH:4 |  |
| aha_heart_failure_2022 | 8 | 21 | CRITICAL:3, HIGH:5 |  |
| aha_stroke_2019 | 7 | 13 | CRITICAL:4, HIGH:3 |  |
| anaphylaxis_management | 8 | 16 | HIGH:5, CRITICAL:3 |  |
| apa_agitation_management | 6 | 12 | CRITICAL:6 | yes |
| atrial_fibrillation | 6 | 15 | CRITICAL:3, HIGH:3 |  |
| cap_pneumonia | 8 | 18 | CRITICAL:1, HIGH:7 |  |
| copd_exacerbation | 8 | 15 | CRITICAL:1, HIGH:6, MODERATE:1 |  |
| gi_bleeding | 6 | 13 | CRITICAL:3, HIGH:3 |  |
| gina_asthma_exacerbation | 19 | 31 | HIGH:15, MODERATE:2, CRITICAL:2 |  |
| hypertensive_emergency | 8 | 24 | CRITICAL:6, HIGH:2 |  |
| idsa_meningitis | 15 | 22 | CRITICAL:10, HIGH:5 |  |
| kdigo_aki_full | 18 | 32 | HIGH:10, CRITICAL:8 |  |
| kdigo_contrast_aki | 15 | 22 | HIGH:13, CRITICAL:2 |  |
| pals_pediatric_emergency | 4 | 8 | CRITICAL:2, HIGH:2 | yes |
| pulmonary_embolism | 9 | 15 | CRITICAL:4, HIGH:5 |  |
| ssc_sepsis_hour1_bundle | 10 | 25 | CRITICAL:2, HIGH:7, MODERATE:1 |  |
| status_epilepticus | 8 | 13 | CRITICAL:5, HIGH:3 |  |
| toxicology_management | 17 | 26 | HIGH:9, CRITICAL:8 |  |
| universal_clinical_safety | 6 | 18 | CRITICAL:3, HIGH:2, MODERATE:1 |  |

## Sample Rules (first 20)

| Rule ID | Graph | Type | Severity | Forbidden Actions | Trigger |
|---------|-------|------|----------|-------------------|---------|
| TRANS-CARDIAC-LIBERAL-THRESHOLD-FORBIDDEN | aabb_transfusion | comorbidity | HIGH | use_liberal_transfusion_threshold_cardiac, transfuse_for_hb_above_8_in_cardiac | patient.comorbidities contains 'acute_coronary_syndrome' |
| TRANS-STABLE-NO-TRANSFUSE-ABOVE-7 | aabb_transfusion | lab_value | HIGH | transfuse_prbc, order_transfusion | patient.labs.hemoglobin in [7.0, 9.9] |
| TRANS-TXA-WITHIN-3H | aabb_transfusion | timing | CRITICAL | give_tranexamic_acid | patient.presentation.time_since_injury_hours in [3.1, 24.0] |
| TRANS-JEHOVAH-NO-BLOOD | aabb_transfusion | other | CRITICAL | give_prbc, give_ffp, give_platelets (+1) | patient.preferences contains 'jehovah_witness' |
| TRANS-ANAPHYLAXIS-EPI-FORBIDDEN | aabb_transfusion | other | CRITICAL | continue_transfusion_during_anaphylaxis, give_only_antihistamine_for_transfusion_anaphylaxis | patient.presentation contains 'anaphylactic_transfusion_reac |
| BURN-PEDIATRIC-DEXTROSE-FORBIDDEN | aba_burn_resuscitation | other | HIGH | withhold_glucose_monitoring_pediatric_burn, give_dextrose_free_fluid_only_pediatric_burn | patient.age in [1, 4] |
| BURN-OVERRESUS-LIMIT | aba_burn_resuscitation | timing | HIGH | exceed_6ml_kg_tbsa_in_24h | patient.presentation.tbsa_percent in [41, 90] |
| BURN-CYANIDE-HYDROXOCOBALAMIN-FORBIDDEN | aba_burn_resuscitation | history | CRITICAL | give_sodium_nitrite_in_cyanide_burn, delay_cyanide_antidote_for_level | patient.history contains 'enclosed_space_fire' |
| BURN-CHEST-ESCHAR-VENTILATION-FORBIDDEN | aba_burn_resuscitation | other | CRITICAL | delay_escharotomy_for_imaging, increase_ventilator_pressure_without_escharotomy | patient.exam_findings contains 'circumferential_chest_burn' |
| ACLS-SHOCKABLE-NO-ATROPINE | acls_cardiac_arrest | other | HIGH | give_atropine_for_cardiac_arrest | patient.cardiac_rhythm contains 'vf' |
| ACLS-SHOCKABLE-NO-CALCIUM-WITHOUT-INDICATION | acls_cardiac_arrest | lab_value | HIGH | give_calcium_without_indication | patient.labs.potassium in [0.0, 6.5] |
| ACLS-SHOCKABLE-NO-BICARB-ROUTINE | acls_cardiac_arrest | lab_value | HIGH | give_sodium_bicarbonate_routine | patient.labs.ph in [7.11, 7.6] |
| ACLS-SHOCKABLE-DEFIB-FIRST-FORBIDDEN | acls_cardiac_arrest | other | CRITICAL | give_amiodarone_before_first_shock, delay_defibrillation_for_intubation | patient.cardiac_rhythm contains 'vf' |
| ACLS-HYPERKALEMIA-CALCIUM-FORBIDDEN | acls_cardiac_arrest | lab_value | CRITICAL | give_succinylcholine_in_hyperkalemic_arrest, delay_calcium_in_hyperkalemic_arrest | patient.labs.potassium in [6.6, 12.0] |
| ACLS-HYPOTHERMIA-NO-DRUGS | acls_cardiac_arrest | other | HIGH | give_epinephrine_1mg_iv, give_amiodarone_300mg, give_lidocaine_alternative | patient.vitals.temperature in [15.0, 29.9] |
| ACLS-TENSION-PNEUMO-DECOMPRESS-FORBIDDEN | acls_cardiac_arrest | comorbidity | CRITICAL | delay_needle_decompression_for_xray_in_arrest, give_only_epinephrine_in_tension_pneumo_arrest | patient.comorbidities contains 'tension_pneumothorax' |
| ACLS-SHOCKABLE-NO-BICARB-ADDITIONAL | acls_cardiac_arrest | comorbidity | HIGH | give_routine_bicarbonate_in_shockable_arrest, delay_defibrillation_for_bicarbonate_push | patient.comorbidities contains 'shockable_rhythm' |
| ACLS-NONSHOCKABLE-NO-BICARB-ADDITIONAL | acls_cardiac_arrest | comorbidity | HIGH | give_routine_bicarbonate_in_nonshockable_arrest, substitute_bicarbonate_for_epinephrine_in_pea | patient.comorbidities contains 'nonshockable_rhythm' |
| ACLS-NONSHOCKABLE-NO-ATROPINE | acls_cardiac_arrest | other | HIGH | give_atropine_for_asystole | patient.cardiac_rhythm contains 'asystole' |
| ACLS-NONSHOCKABLE-NO-DEFIB-ASYSTOLE | acls_cardiac_arrest | other | HIGH | deliver_defibrillation_asystole | patient.cardiac_rhythm contains 'asystole' |

## Constructive Proof

**Premise**: Each conditional FORBIDDEN rule with trigger_range and normal_range defines a matched patient pair where an identical action trace containing the forbidden action produces divergent verdicts.

**TCC detection**: Under trigger_range, the CPG engine activates the FORBIDDEN constraint. TCC evaluates the action trace against patient-specific constraints and flags the violation. Detection rate = 100%.

**ASC detection**: Action-set evaluators (AC-Proxy, PAF, CwT) compare the action trace against a fixed expected-action set. They receive no patient context and produce identical verdicts for both patients. Detection rate = 0%.

## auto_numbers

- `\noContextPairs` = 238
- `\noContextASCDetect` = 0.0
- `\noContextTCCDetect` = 100.0
- `\noContextGraphs` = 25
- `\noContextDistinctActions` = 421
- `\noContextCritical` = 102
- `\noContextHigh` = 131
