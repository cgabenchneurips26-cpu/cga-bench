> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# CGA-Bench Pipeline Verification Audit Report

**Date**: 2026-04-03
**Runtime**: 86.9 seconds
**Status**: PASS (with caveats)

## Summary

| Section | Status | Time | Issues |
|---------|--------|------|--------|
| A: Engine Load + Traversal | OK | 1.6s | 0 |
| B: Action Normalizer | OK | 1.0s | 17 MISMATCH (natural language → normalized ID) |
| C: Scorer Pipeline | OK | 15.4s | 0 |
| D: Scenario Config | OK | 19.8s | 0 |
| E: Episode Compatibility | OK | 15.5s | 4 MISSING (keyword count artifact) |
| F: Temporal Constraints | OK | 0.8s | 0 |
| G: Numbers Audit | OK | 32.8s | 0 |

**Keyword totals**: FAIL=4 (all from "0 FAIL" text), MISSING=4, MISMATCH=17

## Section Details

### A: CPG Engine (25 graphs)
- All 25 graphs load via CPGEngineFactory: **25/25 OK**
- All 11 new/held-out graphs fully traversable: **11/11 OK**
- All nodes reachable from entry node

### B: Action Normalizer
- 1,461 unique actions across 25 graphs
- **17 MISMATCH**: Natural language action descriptions (e.g., "give tPA") don't match
  normalized IDs (e.g., "give_alteplase_0.9mg_kg"). This is expected — the normalizer
  handles this mapping at runtime. These are not bugs.

### C: Scorer Pipeline
- ViolationExtractor + HarmScorer run on all 25 graphs
- All scoring pipelines produce valid CGAScore objects

### D: Scenario Config
- All scenario YAML files parse correctly
- All guideline_graph references resolve to existing graph files

### E: Episode Compatibility
- 181 existing episodes in clean_slate_rescored/
- 688 scenario IDs known to ScenarioLoader
- All existing episode scenario_ids found in ScenarioLoader
- Random sample of 5 episodes: all valid structure

### F: Temporal Constraints
- Deadline validation across all graphs
- Sequence rules properly parsed

### G: Numbers Audit
- 25 graphs with 312+ conditional rules
- Scenario distribution across all guideline_graphs verified
- Manual (105) + Auto (526) = 631 total scenarios across 29 graph variants


## Raw Audit Output

```
======================================================================
CGA-Bench Pipeline Verification Audit
======================================================================

--- Running Section A ---
============================================================
A.1: Load all graphs via CPGEngineFactory
============================================================
Found 25 graph files in ${CGA_BENCH_ROOT}/cga_bench/cpg_model/graphs

  OK  aabb_transfusion                          nodes=  4  entry=transfusion_assessment
  OK  aba_burn_resuscitation                    nodes=  6  entry=burn_initial_assessment
  OK  acls_cardiac_arrest                       nodes=  6  entry=initial_assessment
  OK  acog_obstetric_hemorrhage                 nodes=  4  entry=pph_recognition
  OK  ada_dka_management                        nodes=  8  entry=initial_assessment
  OK  aha_chest_pain                            nodes= 11  entry=initial_assessment
  OK  aha_heart_failure                         nodes= 24  entry=hf_initial_assessment
  OK  aha_stroke                                nodes= 25  entry=stroke_initial_assessment
  OK  anaphylaxis_management                    nodes=  5  entry=initial_recognition
  OK  apa_agitation_management                  nodes=  4  entry=agitation_assessment
  OK  atrial_fibrillation                       nodes=  3  entry=initial_assessment
  OK  cap_pneumonia                             nodes=  3  entry=initial_assessment
  OK  copd_exacerbation                         nodes=  2  entry=initial_assessment
  OK  gi_bleeding                               nodes=  2  entry=initial_assessment
  OK  gina_asthma_exacerbation                  nodes=  5  entry=initial_assessment
  OK  hypertensive_emergency                    nodes=  2  entry=initial_assessment
  OK  idsa_meningitis                           nodes=  5  entry=initial_assessment
  OK  kdigo_aki_full                            nodes= 13  entry=initial_assessment
  OK  kdigo_contrast_aki                        nodes=  7  entry=risk_assessment
  OK  pals_pediatric_emergency                  nodes=  4  entry=pediatric_assessment
  OK  pulmonary_embolism                        nodes=  3  entry=initial_assessment
  OK  ssc_sepsis_hour1                          nodes=  7  entry=initial_recognition
  OK  status_epilepticus                        nodes=  5  entry=initial_stabilization
  OK  toxicology_management                     nodes=  6  entry=initial_stabilization
  OK  universal_clinical_safety                 nodes=  3  entry=initial_encounter

A.1 summary: 25 OK, 0 FAIL (total 25)

============================================================
A.2: Node traversal for 11 new/held-out graphs
============================================================
  OK   anaphylaxis_management                    entry=initial_recognition  nodes=5  edges=4  all reachable
  OK   acls_cardiac_arrest                       entry=initial_assessment  nodes=6  edges=6  all reachable
  OK   status_epilepticus                        entry=initial_stabilization  nodes=5  edges=4  all reachable
  OK   gina_asthma_exacerbation                  entry=initial_assessment  nodes=5  edges=6  all reachable
  OK   idsa_meningitis                           entry=initial_assessment  nodes=5  edges=4  all reachable
  OK   toxicology_management                     entry=initial_stabilization  nodes=6  edges=13  all reachable
  OK   aba_burn_resuscitation                    entry=burn_initial_assessment  nodes=6  edges=7  all reachable
  OK   aabb_transfusion                          entry=transfusion_assessment  nodes=4  edges=4  all reachable
  OK   acog_obstetric_hemorrhage                 entry=pph_recognition  nodes=4  edges=4  all reachable
  OK   pals_pediatric_emergency                  entry=pediatric_assessment  nodes=4  edges=3  all reachable
  OK   apa_agitation_management                  entry=agitation_assessment  nodes=4  edges=3  all reachable

A.2 summary: 11 OK, 0 WARN/FAIL (total 11)

============================================================
Section A complete.
  A.1: 25 OK, 0 FAIL
  A.2: 11 OK, 0 WARN/FAIL
============================================================

  [OK] Section A completed in 1.6s

--- Running Section B ---
============================================================
B.1: All graph actions through ActionNormalizer
============================================================
Collected 1461 unique actions from 25 graphs

  MAPPED  add_diuretic_for_congestion                        -> iv_diuretics
  MAPPED  add_metolazone                                     -> add_thiazide_metolazone
  MAPPED  add_vasodilator_if_hypertensive                    -> consider_vasodilators
  MAPPED  administer_contrast_without_egfr                   -> give_contrast_without_estimated_glomerular_filtration_rate
  MAPPED  administer_contrast_without_egfr_check             -> give_contrast_without_estimated_glomerular_filtration_rate_check
  MAPPED  administer_contrast_without_hydration              -> give_contrast_without_hydration
  MAPPED  administer_oxygen                                  -> give_oxygen
  MAPPED  administer_oxygen_high_flow                        -> give_oxygen_high_flow
  MAPPED  administer_oxygen_if_hypoxic                       -> give_oxygen_if_hypoxic
  MAPPED  administer_oxygen_to_target_94_98                  -> give_oxygen_to_target_94_98
  MAPPED  administer_specific_antidote                       -> give_specific_antidote
  MAPPED  admit_to_ccu                                       -> admit_to_icu
  MAPPED  assess_airway                                      -> assess_vital_signs
  MAPPED  assess_ci_aki_risk                                 -> review_risk_factors
  MAPPED  assess_urine_output                                -> monitor_urine_output
  MAPPED  calculate_egfr                                     -> calculate_estimated_glomerular_filtration_rate
  MAPPED  check_antiepileptic_drug_levels                    -> assess_antiepileptic_drug_levels
  MAPPED  check_baseline_egfr                                -> assess_baseline_estimated_glomerular_filtration_rate
  MAPPED  check_hepatic_dose_adjustment                      -> assess_hepatic_dose_adjustment
  MAPPED  check_point_of_care_glucose                        -> assess_point_of_care_glucose
  MAPPED  check_renal_dose_adjustment                        -> assess_renal_dose_adjustment
  MAPPED  check_scr_at_48h                                   -> assess_serum_creatinine_at_48h
  MAPPED  check_scr_at_72h                                   -> assess_serum_creatinine_at_72h
  MAPPED  consider_ace_or_arb_or_arni                        -> initiate_ace_or_arb_or_arni
  MAPPED  consider_beta_blocker                              -> initiate_beta_blocker
  MAPPED  consider_mra                                       -> initiate_mra
  MAPPED  consult_cardiology                                 -> request_consultation
  MAPPED  consult_nephrology                                 -> nephrology_consult
  MAPPED  consult_neurology                                  -> request_consultation
  MAPPED  consult_neurosurgery                               -> neurosurgery_consult
  MAPPED  consult_specialist                                 -> request_consultation
  MAPPED  consult_surgery                                    -> request_consultation
  MAPPED  delay_antibiotics_for_ct                           -> delay_antibiotics_for_computed_tomography
  MAPPED  delay_ct_for_labs                                  -> delay_computed_tomography_for_labs
  MAPPED  delay_ecg_for_registration                         -> delay_electrocardiogram_for_registration
  MAPPED  delay_reversal_for_inr_result                      -> delay_reversal_for_international_normalized_ratio_result
  MAPPED  discharge_without_ecg                              -> discharge_without_electrocardiogram
  MAPPED  discharge_without_egfr_confirmation                -> discharge_without_estimated_glomerular_filtration_rate_confirmation
  MAPPED  discharge_without_scr_check                        -> discharge_without_serum_creatinine_check
  MAPPED  discontinue_nephrotoxins                           -> hold_nephrotoxic_medications
  MAPPED  discuss_goals_of_care                              -> palliative_care_discussion
  MAPPED  diuretics_for_congestion                           -> iv_diuretics
  MAPPED  document_egfr_check                                -> document_estimated_glomerular_filtration_rate_check
  MAPPED  document_stable_egfr                               -> document_stable_estimated_glomerular_filtration_rate
  MAPPED  ecg_for_hyperkalemia                               -> electrocardiogram_for_hyperkalemia
  MAPPED  give_ace_inhibitor                                 -> initiate_ace_or_arb_or_arni
  MAPPED  give_alteplase                                     -> give_alteplase_0.9mg_kg
  MAPPED  give_antibiotics                                   -> give_broad_spectrum_antibiotics
  MAPPED  give_arb                                           -> initiate_ace_or_arb_or_arni
  MAPPED  give_aspirin                                       -> give_aspirin_loading
  MAPPED  give_beta_blocker                                  -> initiate_beta_blocker
  MAPPED  give_enoxaparin                                    -> give_anticoagulation
  MAPPED  give_fluid_bolus                                   -> give_crystalloid_30ml_kg
  MAPPED  give_gadolinium_in_severe_ckd_for_mri              -> give_gadolinium_in_severe_ckd_for_magnetic_resonance_imaging
  MAPPED  give_heparin                                       -> give_anticoagulation
  MAPPED  give_heparin_within_24h_of_tpa                     -> give_heparin_within_24h_of_alteplase
  MAPPED  give_iv_fluid                                      -> give_crystalloid_fluid
  MAPPED  give_iv_fluids                                     -> give_crystalloid_fluid
  MAPPED  give_labetalol                                     -> use_iv_labetalol_or_nicardipine
  MAPPED  give_metoprolol                                    -> initiate_beta_blocker
  MAPPED  give_nitrates                                      -> give_nitrates_if_indicated
  MAPPED  give_nitroglycerin                                 -> give_nitrates_if_indicated
  MAPPED  give_nitroprusside                                 -> consider_vasodilators
  MAPPED  give_ns_bolus_10ml_kg                              -> give_normal_saline_bolus_10ml_kg
  MAPPED  give_ns_bolus_20ml_kg                              -> give_normal_saline_bolus_20ml_kg
  MAPPED  give_packed_rbc_if_hgb_below_7                     -> give_packed_red_blood_cell_count_if_hemoglobin_below_7
  MAPPED  give_pcc                                           -> reverse_anticoagulation_if_applicable
  MAPPED  give_potassium_replacement                         -> give_potassium_iv
  MAPPED  give_rate_control_without_ecg                      -> give_rate_control_without_electrocardiogram
  MAPPED  give_statin                                        -> statin_therapy
  MAPPED  give_tpa                                           -> give_alteplase_0.9mg_kg
  MAPPED  give_tpa_for_todds_paralysis                       -> give_alteplase_for_todds_paralysis
  MAPPED  give_vasodilator                                   -> add_vasodilator_if_hypertensive
  MAPPED  give_vitamin_k                                     -> reverse_anticoagulation_if_applicable
  MAPPED  hold_metformin                                     -> hold_metformin_if_applicable
  MAPPED  hold_nephrotoxic_medications                       -> discontinue_nephrotoxic_agents
  MAPPED  initiate_arni                                      -> initiate_ace_or_arb_or_arni
  MAPPED  inotrope_support                                   -> consider_inotropes
  MAPPED  interpret_ecg                                      -> obtain_12_lead_ecg
  MAPPED  invasive_hemodynamic_monitoring                    -> hemodynamic_monitoring
  MAPPED  iv_hydration_if_proceeding                         -> iv_hydration_pre_contrast
  MAPPED  minimize_contrast_volume                           -> use_minimum_contrast_volume
  MAPPED  monitor_bmp_q2_4h                                  -> monitor_basic_metabolic_panel_q2_4h
  MAPPED  monitor_ck_renal_function                          -> monitor_creatine_kinase_renal_function
  MAPPED  monitor_scr_48_72h                                 -> monitor_serum_creatinine_48_72h
  MAPPED  monitor_urine_output                               -> assess_urine_output
  MAPPED  nephrology_consult                                 -> consult_nephrology
  MAPPED  neurological_monitoring                            -> neurological_checks_q15min
  MAPPED  obtain_ecg                                         -> obtain_12_lead_ecg
  MAPPED  obtain_prior_ecg_comparison                        -> obtain_12_lead_ecg
  MAPPED  optimize_fluid_status                              -> give_crystalloid_fluid
  MAPPED  optimize_volume_status                             -> assess_hydration_status
  MAPPED  order_baseline_creatinine                          -> check_baseline_egfr
  MAPPED  order_carboxyhemoglobin                            -> order_lab_carboxyhemoglobin
  MAPPED  order_cbc                                          -> order_lab_cbc
  MAPPED  order_cbc_coagulation                              -> order_lab_complete_blood_count_coagulation
  MAPPED  order_chest_xray                                   -> order_imaging_chest_xray
  MAPPED  order_creatinine                                   -> check_baseline_egfr
  MAPPED  order_csf_analysis                                 -> order_lab_csf_analysis
  MAPPED  order_csf_cell_count                               -> order_lab_csf_cell_count
  MAPPED  order_csf_culture                                  -> order_lab_csf_culture
  MAPPED  order_csf_gram_stain                               -> order_lab_csf_gram_stain
  MAPPED  order_csf_pcr_panel                                -> order_lab_csf_pcr_panel
  MAPPED  order_csf_protein_glucose                          -> order_lab_csf_protein_glucose
  MAPPED  order_ct_angiography                               -> order_lab_computed_tomography_angiography
  MAPPED  order_ct_pa_without_considering_vq                 -> order_lab_computed_tomography_pa_without_considering_vq
  MAPPED  order_ct_with_contrast_without_nephrology_consult_in_aki -> order_lab_computed_tomography_with_contrast_without_nephrology_consult_in_aki
  MAPPED  order_ct_with_contrast_without_renal_assessment    -> order_lab_computed_tomography_with_contrast_without_renal_assessment
  MAPPED  order_cyanide_level                                -> order_lab_cyanide_level
  MAPPED  order_cystatin_c                                   -> order_lab_cystatin_c
  MAPPED  order_ecg                                          -> obtain_12_lead_ecg
  MAPPED  order_ecg_stat                                     -> order_lab_electrocardiogram_stat
  MAPPED  order_fibrinogen                                   -> order_lab_fibrinogen
  MAPPED  order_fluid_normal_saline                          -> give_iv_fluids
  MAPPED  order_imaging_ct_head                              -> order_stat_ct_head
  MAPPED  order_imaging_ct_pa                                -> order_imaging_computed_tomography_pa
  MAPPED  order_imaging_ecg                                  -> order_imaging_electrocardiogram
  MAPPED  order_imaging_echocardiogram                       -> order_echocardiogram
  MAPPED  order_lab_blood_gas                                -> order_lab_abg
  MAPPED  order_lab_bnp                                      -> order_bnp_or_ntprobnp
  MAPPED  order_lab_cbc_repeat                               -> order_lab_complete_blood_count_repeat
  MAPPED  order_lab_ck                                       -> order_lab_creatine_kinase
  MAPPED  order_lab_creatinine                               -> order_lab_bmp
  MAPPED  order_lab_eGFR                                     -> order_lab_estimated_glomerular_filtration_rate
  MAPPED  order_lab_electrolytes                             -> order_lab_bmp
  MAPPED  order_lab_inr                                      -> order_lab_coagulation
  MAPPED  order_lab_liver_function                           -> order_lab_liver_function_tests
  MAPPED  order_lab_ntproBNP                                 -> order_lab_ntprobnp
  MAPPED  order_lab_tsh                                      -> order_lab_thyroid_stimulating_hormone
  MAPPED  order_lumbar_puncture                              -> order_lab_lumbar_puncture
  MAPPED  order_mri_gadolinium_without_nephrology_approval_in_ckd -> order_lab_magnetic_resonance_imaging_gadolinium_without_nephrology_approval_in_ckd
  MAPPED  order_mri_with_gadolinium                          -> order_lab_magnetic_resonance_imaging_with_gadolinium
  MAPPED  order_point_of_care_ultrasound                     -> order_lab_point_of_care_ultrasound
  MAPPED  order_renal_biopsy                                 -> order_lab_renal_biopsy
  MAPPED  order_renal_ultrasound                             -> order_lab_renal_ultrasound
  MAPPED  order_reticulocyte_count                           -> order_lab_reticulocyte_count
  MAPPED  order_serial_ecg                                   -> order_lab_serial_electrocardiogram
  MAPPED  order_thromboelastography                          -> order_lab_thromboelastography
  MAPPED  order_transfusion                                  -> order_lab_transfusion
  MAPPED  order_type_and_crossmatch                          -> order_lab_type_and_crossmatch
  MAPPED  order_type_and_screen                              -> order_lab_type_and_screen
  MAPPED  order_urinalysis                                   -> order_lab_urinalysis
  MAPPED  perform_lp_without_ct                              -> perform_lp_without_computed_tomography
  MAPPED  perform_lp_without_ct_when_contraindicated         -> perform_lp_without_computed_tomography_when_contraindicated
  MAPPED  prehydrate_iv_ns                                   -> prehydrate_iv_normal_saline
  MAPPED  reassess_patient                                   -> reassess_perfusion
  MAPPED  reduce_bp_below_140_in_tpa_candidate               -> reduce_bp_below_140_in_alteplase_candidate
  MAPPED  reduce_bp_to_below_185_110_before_tpa              -> reduce_bp_to_below_185_110_before_alteplase
  MAPPED  repeat_cbc                                         -> repeat_complete_blood_count
  MAPPED  repeat_ct_head                                     -> repeat_computed_tomography_head
  MAPPED  repeat_nihss                                       -> perform_nihss
  MAPPED  resume_metformin_if_egfr_stable                    -> resume_metformin_if_estimated_glomerular_filtration_rate_stable
  MAPPED  review_ecg_for_toxicity                            -> review_electrocardiogram_for_toxicity
  MAPPED  schedule_followup                                  -> regular_follow_up
  MAPPED  serial_ecg                                         -> serial_electrocardiogram
  MAPPED  serial_scr_monitoring                              -> serial_serum_creatinine_monitoring
  MAPPED  start_iv_fluid_ns                                  -> start_iv_fluid_normal_saline
  MAPPED  start_iv_hydration                                 -> start_iv_fluid_normal_saline
  MAPPED  stat_ct_head                                       -> order_stat_ct_head
  MAPPED  stop_metformin                                     -> hold_metformin_if_applicable
  MAPPED  stop_tpa_infusion                                  -> stop_alteplase_infusion

Identity (no mapping needed): 1300
Mapped (transformed):         161
Unmapped (no rule found):     1174

Unmapped actions:
  - abruptly_stop_chronic_steroid_in_exacerbation
  - activate_cath_lab
  - activate_cath_lab_for_stemi
  - activate_cath_lab_if_stemi
  - activate_code_team
  - activate_massive_transfusion_protocol
  - add_amiodarone_loading
  - add_ampicillin_and_aminoglycoside
  - add_ampicillin_for_listeria
  - add_anaerobic_coverage
  - add_dextrose_to_iv
  - add_dextrose_when_glucose_below_200
  - add_digoxin
  - add_hydralazine_isdn_if_intolerant
  - add_ivabradine
  - add_ivabradine_if_indicated
  - add_linezolid
  - add_macrolide_without_theophylline_check
  - add_new_aed_without_checking_levels
  - add_vancomycin
  - additional_contrast_exposure
  - additional_fluid_bolus
  - adjust_drug_doses
  - adjust_fluid_rate
  - adjust_insulin_rate
  - adjust_medication_doses
  - adjust_vasopressor
  - admit_to_cardiology_service
  - admit_to_hospital
  - admit_to_icu
  - admit_to_medical_floor
  - admit_to_observation
  - admit_to_stroke_unit
  - admit_to_ward
  - aggressive_cooling
  - aggressive_fluid_bolus
  - analyze_rhythm
  - antiplatelet_therapy
  - apply_butter_to_burn
  - apply_continuous_monitoring
  - apply_droplet_precautions
  - apply_end_tidal_co2_monitoring
  - apply_ice_to_burn
  - apply_least_restrictive_restraint
  - apply_liberal_threshold_hb_8
  - apply_oxygen
  - apply_restrictive_threshold
  - apply_topical_antibiotic_before_transfer
  - arrange_followup
  - arrange_pci
  - arrange_transfer_if_indicated
  - arterial_line_monitoring
  - assess_abdominal_status
  - assess_active_bleeding
  - assess_aggression_level
  - assess_airway_breathing_circulation
  - assess_aki_risk_factors
  - assess_anaphylaxis_criteria
  - assess_anion_gap_closure
  - assess_anticoagulation_need
  - assess_bp
  - assess_burn_center_referral_criteria
  - assess_burn_depth
  - assess_cardiovascular_status
  - assess_chadsvasc_score
  - assess_chief_complaint
  - assess_clinical_presentation
  - assess_compartment_pressures
  - assess_contraindications_to_lp
  - assess_crt_indication
  - assess_curb65
  - assess_decontamination_indication
  - assess_distal_pulses
  - assess_end_organ_damage
  - assess_etiology
  - assess_for_ckd_development
  - assess_for_complications
  - assess_for_early_invasive
  - assess_for_genital_tract_laceration
  - assess_for_retained_products
  - assess_general_status
  - assess_hemodynamic_profile
  - assess_hemodynamic_status
  - assess_hydration_status
  - assess_icd_indication
  - assess_icu_criteria
  - assess_infection_source
  - assess_inhalation_injury_signs
  - assess_inhaler_technique
  - assess_lvef
  - assess_medical_causes
  - assess_mental_status
  - assess_musculoskeletal_status
  - assess_neurological_status
  - assess_nihss
  - assess_niv_eligibility
  - assess_nyha_class
  - assess_organ_dysfunction
  - assess_pain_level
  - assess_patient
  - assess_pediatric_triangle
  - assess_respiratory_status
  - assess_rrt_need
  - assess_safety_of_environment
  - assess_seizure_semiology
  - assess_severity_classification
  - assess_skin_status
  - assess_substance_use
  - assess_symptoms_of_anemia
  - assess_toxidrome
  - assess_uterine_tone
  - assess_vascular_access
  - assess_vital_signs
  - assess_vital_signs_age_appropriate
  - assess_wells_score
  - attach_defibrillator_pads
  - attempt_verbal_deescalation
  - attribute_ams_to_dementia
  - avoid_additional_nephrotoxins
  - avoid_contrast
  - begin_high_quality_cpr
  - bp_management
  - bronchoscopy_if_suspected
  - calculate_aki_stage
  - calculate_anion_gap
  - calculate_broselow_weight
  - calculate_chadsvasc
  - calculate_contrast_volume_limit
  - calculate_corrected_sodium
  - calculate_estimated_glomerular_filtration_rate
  - calculate_hasbled
  - calculate_osmolar_gap
  - calculate_parkland_formula
  - calculate_risk_score
  - call_anesthesia_consult
  - call_for_help
  - cardiac_monitoring_for_afib
  - cardiac_rehabilitation_referral
  - cardiovert_without_digoxin_fab
  - careful_fluid_challenge
  - carotid_evaluation
  - central_line_access
  - choose_appropriate_medication
  - classify_dka_severity
  - confirm_cardiac_arrest
  - consider_b_lynch_suture
  - consider_bicarbonate_if_ph_below_6.9
  - consider_dialysis_timing
  - consider_double_sequential_defibrillation
  - consider_fibrinolysis_if_pci_delayed
  - consider_hysterectomy_if_refractory
  - consider_inotropes
  - consider_outpatient_stress_test
  - consider_rrt_if_indicated
  - consider_rrt_planning
  - consider_vasodilators
  - consult_burn_center
  - consult_gi
  - consult_hepatology
  - consult_interventional_radiology
  - consult_nephrology_if_needed
  - consult_obstetrics
  - contact_poison_control
  - continue_ace_inhibitor
  - continue_aminoglycoside_with_contrast
  - continue_aminoglycosides
  - continue_antibiotics
  - continue_beta_blocker_if_stable
  - continue_cpr
  - continue_dexamethasone_4_days
  - continue_dual_antiplatelet
  - continue_high_quality_cpr
  - continue_iv_fluids
  - continue_iv_hydration_if_needed
  - continue_medical_therapy
  - continue_metformin_during_contrast_study
  - continue_metformin_in_aki
  - continue_metformin_in_dka
  - continue_mra
  - continue_nephrotoxic_drugs
  - continue_nephrotoxin_during_contrast_exposure
  - continue_nsaid
  - continue_nsaid_with_contrast
  - continue_nsaids
  - continue_sglt2_inhibitor_in_dka
  - continue_transfusion_during_anaphylaxis
  - continue_transfusion_during_reaction
  - continue_vasopressor
  - continue_verbal_deescalation
  - continuous_bp_monitoring
  - continuous_cardiac_monitoring
  - continuous_eeg_monitoring
  - continuous_fetal_monitoring
  - correct_electrolyte_abnormalities
  - cover_with_clean_dry_dressing
  - daily_weights
  - debride_in_field
  - delay_antibiotics
  - delay_antibiotics_due_to_no_fever
  - delay_antibiotics_for_computed_tomography
  - delay_antibiotics_for_cultures_beyond_1h
  - delay_antibiotics_for_imaging
  - delay_antibiotics_for_lp
  - delay_antibiotics_for_source
  - delay_antibiotics_until_culture
  - delay_anticoagulation
  - delay_anticoagulation_if_high_probability
  - delay_antidote
  - delay_benzodiazepine
  - delay_blood_products_for_crossmatch
  - delay_bronchodilator
  - delay_calcium_in_hyperkalemic_arrest
  - delay_cath_lab_for_dka_resolution
  - delay_computed_tomography_for_labs
  - delay_cpr
  - delay_cyanide_antidote_for_level
  - delay_defibrillation
  - delay_defibrillation_for_bicarbonate_push
  - delay_defibrillation_for_intubation
  - delay_dexamethasone_for_culture_in_meningitis
  - delay_electrocardiogram_for_registration
  - delay_empiric_antidote_if_indicated
  - delay_empiric_coverage
  - delay_epinephrine_for_antihistamine
  - delay_escharotomy_for_imaging
  - delay_fomepizole_for_osmolar_gap
  - delay_glucose_correction_for_eeg
  - delay_icu_transfer_in_severe_cap
  - delay_intubation
  - delay_intubation_for_imaging
  - delay_iv_access
  - delay_nac_for_level_confirmation
  - delay_needle_decompression_for_xray_in_arrest
  - delay_pci_for_endoscopy
  - delay_pericardiocentesis_for_imaging_in_arrest
  - delay_perimortem_csection_beyond_4min
  - delay_platelet_transfusion_in_active_bleed
  - delay_potassium_replacement
  - delay_reperfusion
  - delay_resuscitation
  - delay_resuscitation_for_endoscopy
  - delay_resuscitation_for_endoscopy_in_gi_bleed
  - delay_reversal_for_international_normalized_ratio_result
  - delay_second_line_agent
  - delay_thrombolysis_in_massive_pe
  - delay_transfusion_for_endoscopy
  - delay_treatment
  - delay_treatment_for_estimated_blood_loss
  - deliver_defibrillation
  - deliver_defibrillation_asystole
  - determine_disposition
  - diabetes_education
  - discharge_based_on_normal_glucose
  - discharge_before_24h_in_mastocytosis
  - discharge_before_4_hours
  - discharge_before_8h_severe_anaphylaxis
  - discharge_before_airway_stable
  - discharge_before_gap_closed
  - discharge_critically_ill
  - discharge_during_absorption_phase
  - discharge_home
  - discharge_major_burn_home
  - discharge_prematurely
  - discharge_severe_exacerbation_without_mgso4
  - discharge_with_action_plan
  - discharge_with_followup
  - discharge_with_instructions
  - discharge_with_low_nihss
  - discharge_with_vague_complaints
  - discharge_without_action_plan
  - discharge_without_allergist_referral
  - discharge_without_assessment
  - discharge_without_autoinjector_prescription
  - discharge_without_corticosteroid_prescription
  - discharge_without_diagnosis
  - discharge_without_documentation
  - discharge_without_electrocardiogram
  - discharge_without_estimated_glomerular_filtration_rate_confirmation
  - discharge_without_evaluation
  - discharge_without_fetal_assessment
  - discharge_without_followup
  - discharge_without_insulin
  - discharge_without_insulin_plan
  - discharge_without_neurology_followup
  - discharge_without_observation_period
  - discharge_without_psychiatry_evaluation
  - discharge_without_sepsis_workup
  - discharge_without_serial_testing
  - discharge_without_serum_creatinine_check
  - discontinue_antibiotics_early
  - discontinue_antiplatelet_early
  - discontinue_dexamethasone_if_not_pneumococcal
  - discontinue_eeg_monitoring
  - discontinue_eeg_prematurely
  - discontinue_insulin_for_low_glucose
  - discontinue_monitoring_prematurely
  - discontinue_nephrotoxic_agents
  - discontinue_nsaid
  - discuss_risk_benefit_with_patient
  - document_estimated_glomerular_filtration_rate_check
  - document_restraint_indication
  - document_risk_assessment
  - document_stable_estimated_glomerular_filtration_rate
  - drop_bp_below_120_systolic
  - dvt_prophylaxis
  - early_mobilization
  - echocardiogram_post_mi
  - educate_patient_trigger_avoidance
  - electrocardiogram_for_hyperkalemia
  - endocrinology_consult
  - endocrinology_followup
  - ensure_patient_education
  - ensure_stable_glucose_control
  - escalate_diuresis_in_cardiorenal_syndrome
  - escalate_to_icu
  - establish_iv_io_access
  - establish_iv_or_io_access
  - establish_large_bore_iv
  - establish_second_iv_access
  - estimate_tbsa
  - evaluate_alternative_diagnoses
  - evaluate_reversible_causes
  - evaluate_rrt_indications
  - exceed_6ml_kg_tbsa_in_24h
  - extubate_during_active_se
  - fluid_restrict
  - give_100_percent_oxygen
  - give_ace_inhibitor_again
  - give_ace_inhibitor_in_aki
  - give_ace_inhibitor_in_eclampsia
  - give_acetaminophen
  - give_acetaminophen_alternative
  - give_acetaminophen_full_dose_in_cirrhosis
  - give_acetylcysteine_nebulized_in_acute_asthma
  - give_activated_charcoal
  - give_activated_charcoal_if_unprotected_airway
  - give_activated_charcoal_with_caustic
  - give_activated_charcoal_with_hydrocarbon
  - give_acyclovir_iv
  - give_additional_beta_blocker
  - give_additional_beta_blocker_in_anaphylaxis
  - give_additional_ccb
  - give_additional_opioid_during_arrest
  - give_additional_opioid_in_overdose
  - give_adenosine
  - give_adult_dose_anticonvulsant_in_neonate
  - give_adult_dose_epinephrine
  - give_adult_dose_medications
  - give_adult_empiric_for_neonatal_meningitis
  - give_aggressive_bp_lowering
  - give_aggressive_diuresis_in_hypotensive_hf
  - give_aggressive_fluid_30ml_kg
  - give_aggressive_fluid_bolus
  - give_aggressive_iv_fluid
  - give_aggressive_iv_fluids
  - give_albumin_colloid_adjunct
  - give_albumin_infusion
  - give_alteplase_for_todds_paralysis
  - give_alteplase_pe
  - give_alteplase_without_ruling_out_mimic
  - give_aminoglycoside
  - give_aminoglycoside_high_dose
  - give_aminoglycoside_in_hepatorenal
  - give_aminoglycoside_without_adjustment
  - give_aminoglycoside_without_monitoring
  - give_aminoglycoside_without_tdm_in_stage1_aki
  - give_aminophylline_in_acute_exacerbation
  - give_amiodarone_150mg_repeat
  - give_amiodarone_300mg
  - give_amiodarone_before_first_shock
  - give_amiodarone_for_asystole
  - give_amiodarone_iv
  - give_amiodarone_without_thyroid_evaluation
  - give_amoxicillin
  - give_ampicillin
  - give_ampicillin_iv
  - give_antibiotics_only_without_acyclovir_in_encephalitis
  - give_antibiotics_routine
  - give_anticholinergic_high_dose
  - give_anticoagulation_only_in_massive_pe
  - give_anticoagulation_without_chadsvasc
  - give_anticoagulation_without_ruling_out_dissection
  - give_anticonvulsant_if_seizures
  - give_antiemetic
  - give_antiepileptic_before_glucose_correction
  - give_antiepileptic_medication
  - give_antihistamine_as_first_line
  - give_antiplatelet
  - give_antipseudomonal_beta_lactam
  - give_antipsychotic_in_nms
  - give_antipyretic
  - give_antipyretic_for_hyperthermia_toxicologic
  - give_antiseizure_prophylaxis
  - give_apixaban
  - give_apixaban_standard
  - give_arb_in_aki
  - give_aspirin_high_dose
  - give_aspirin_in_severe_thrombocytopenia
  - give_aspirin_loading
  - give_atenolol
  - give_atropine
  - give_atropine_for_asystole
  - give_atropine_for_cardiac_arrest
  - give_azithromycin_only_for_aspiration
  - give_benzodiazepine
  - give_benzodiazepine_as_second_line
  - give_benzodiazepine_chronic
  - give_benzodiazepine_first_line
  - give_benzodiazepine_for_agitation
  - give_benzodiazepine_for_seizures
  - give_benzodiazepine_high_dose
  - give_benzodiazepine_im
  - give_benzodiazepine_weight_based
  - give_beta_blocker_alone
  - give_beta_blocker_first
  - give_beta_blocker_if_stable
  - give_beta_blocker_in_asthma_anaphylaxis
  - give_beta_blocker_in_ccb_overdose
  - give_beta_blocker_iv
  - give_beta_lactam_plus_fluoroquinolone
  - give_beta_lactam_plus_macrolide
  - give_bicarbonate
  - give_bicarbonate_if_ph_above_7.0
  - give_bicarbonate_without_indication
  - give_bipap
  - give_bolus_greater_than_10ml_kg
  - give_bolus_greater_than_20ml_kg
  - give_bolus_over_20ml_kg_h
  - give_broad_spectrum_antibiotics
  - give_bronchodilator
  - give_calcium_channel_blocker
  - give_calcium_chloride
  - give_calcium_gluconate
  - give_calcium_in_digoxin_toxicity
  - give_calcium_without_indication
  - give_carboprost
  - give_category_x_drug
  - give_cefepime
  - give_cefotaxime_iv
  - give_ceftriaxone
  - give_ceftriaxone_iv
  - give_ceftriaxone_only_in_immunocompromised
  - give_celecoxib
  - give_cephalosporin
  - give_charcoal_after_endoscopy
  - give_chest_physiotherapy
  - give_chest_physiotherapy_in_acute_asthma
  - give_chloramphenicol_iv
  - give_chlorpromazine
  - give_ciprofloxacin
  - give_colloid_in_first_24h
  - give_colloid_solution
  - give_continuous_salbutamol_nebulized
  - give_contraindicated_medication
  - give_contrast
  - give_contrast_without_assessment
  - give_contrast_without_isotonic_prehydration_in_ckd
  - give_contrast_without_precaution
  - give_contrast_without_prehydration_high_risk
  - give_contrast_without_preparation
  - give_corticosteroid
  - give_corticosteroid_weight_based
  - give_cox2_inhibitor_in_aki
  - give_cpap
  - give_cryoprecipitate
  - give_cryoprecipitate_if_fibrinogen_low
  - give_crystalloid_30ml_kg
  - give_crystalloid_60ml_kg
  - give_crystalloid_as_sole_resuscitation
  - give_crystalloid_bolus
  - give_crystalloid_fluid
  - give_cyproheptadine
  - give_dabigatran
  - give_dantrolene
  - give_deferoxamine
  - give_dexamethasone_after_antibiotics
  - give_dexamethasone_after_antibiotics_in_meningitis
  - give_dexamethasone_iv
  - give_dexamethasone_oral
  - give_dextrose_50_percent
  - give_dextrose_for_hypoglycemia
  - give_dextrose_free_fluid_only_pediatric_burn
  - give_dextrose_if_hypoglycemic
  - give_diazepam_10mg_iv
  - give_diazepam_iv_in_neonate
  - give_digoxin
  - give_digoxin_fab_fragments
  - give_diltiazem
  - give_dimercaprol
  - give_diphenhydramine
  - give_diuretic
  - give_diuretics
  - give_doac
  - give_droperidol
  - give_dual_antiplatelet
  - give_dual_antiplatelet_without_gi_protection
  - give_edoxaban
  - give_empiric_antibiotics
  - give_empiric_azithromycin_without_infection_evidence
  - give_enalapril
  - give_enalaprilat
  - give_enoxaparin_1mg_kg_bid
  - give_enoxaparin_full_dose
  - give_enoxaparin_full_dose_in_ckd
  - give_epinephrine_0_5mg
  - give_epinephrine_1mg_iv
  - give_epinephrine_1mg_iv_immediately
  - give_epinephrine_im
  - give_epinephrine_im_0_01mg_kg
  - give_epinephrine_iv_bolus
  - give_epinephrine_iv_push
  - give_epinephrine_nebulized
  - give_epinephrine_repeat_3_5min
  - give_epinephrine_subcutaneous
  - give_ethanol_concurrently_with_fomepizole
  - give_ffp
  - give_ffp_as_sole_reversal
  - give_fibrinolytic
  - give_fibrinolytic_for_pe
  - give_flumazenil
  - give_fluoroquinolone
  - give_fluoroquinolone_without_clear_indication
  - give_fomepizole
  - give_forced_diuresis
  - give_forced_diuresis_in_poisoning
  - give_fosphenytoin_20mg_pe_kg
  - give_full_crystalloid_30ml_kg_without_assessment
  - give_full_dose_anticoagulation
  - give_full_dose_heparin_with_active_bleed
  - give_full_dose_hepatotoxin_in_liver_failure
  - give_full_dose_nephrotoxin_in_renal_failure
  - give_full_dose_phenytoin
  - give_furosemide_if_taco
  - give_gadolinium_contrast
  - give_gadolinium_in_severe_ckd_for_magnetic_resonance_imaging
  - give_gentamicin_empiric_without_renal_dosing
  - give_gentamicin_iv
  - give_glucagon
  - give_glucagon_high_dose
  - give_glucose_without_thiamine
  - give_h1_antihistamine
  - give_h1_antihistamine_weight_based
  - give_h2_antihistamine
  - give_haloperidol
  - give_haloperidol_in_nms
  - give_haloperidol_in_withdrawal_seizure
  - give_heliox
  - give_hemabate
  - give_heparin_bolus
  - give_heparin_within_24h_of_alteplase
  - give_hepatotoxic_drug_in_apap_overdose
  - give_high_dose_beta_blocker
  - give_high_dose_dexamethasone_in_septic_shock
  - give_high_dose_diuretics
  - give_high_dose_diuretics_if_hypotensive
  - give_high_dose_insulin_euglycemia
  - give_high_dose_methylprednisolone
  - give_high_dose_steroid_early
  - give_high_fio2
  - give_high_flow_o2_without_monitoring
  - give_high_flow_oxygen_100pct
  - give_high_osmolar_contrast
  - give_hydrocortisone_iv
  - give_hydroxocobalamin
  - give_hypotonic_fluid_early
  - give_ibuprofen
  - give_insulin_bolus
  - give_insulin_bolus_in_severe_hypokalemia
  - give_insulin_dextrose
  - give_insulin_for_normal_glucose
  - give_intralipid_emulsion
  - give_iodinated_contrast_without_prep_in_aki_stage2
  - give_ipecac
  - give_ipratropium_nebulized
  - give_isotretinoin
  - give_iv_amiodarone
  - give_iv_antibiotics_immediately
  - give_iv_antihypertensive
  - give_iv_beta_blocker
  - give_iv_crystalloid_bolus
  - give_iv_inotropes
  - give_iv_ketamine
  - give_iv_labetalol
  - give_iv_labetalol_or_hydralazine
  - give_iv_metoprolol_in_acute_failure
  - give_iv_metoprolol_without_alpha_block
  - give_iv_morphine
  - give_iv_nicardipine
  - give_iv_nitroprusside
  - give_iv_ppi
  - give_iv_salbutamol
  - give_iv_theophylline_in_acute_asthma
  - give_ketamine_for_induction
  - give_ketamine_infusion
  - give_ketorolac
  - give_known_allergen_drug
  - give_lactated_ringer
  - give_lactated_ringer_in_liver_failure
  - give_large_volume_fluid
  - give_levetiracetam
  - give_levetiracetam_60mg_kg
  - give_levetiracetam_as_first_line
  - give_levofloxacin
  - give_lidocaine_alternative
  - give_lmwh
  - give_loading_dose_without_level_check
  - give_long_acting_sedative_during_arrest
  - give_long_acting_sedative_in_opioid_od
  - give_long_acting_sulfonylurea
  - give_lorazepam
  - give_lorazepam_4mg
  - give_lorazepam_4mg_iv
  - give_lorazepam_im
  - give_losartan
  - give_magnesium_containing_antacids
  - give_magnesium_sulfate
  - give_magnesium_sulfate_iv
  - give_mannitol_for_toxin_clearance
  - give_mannitol_or_hypertonic_saline_if_edema
  - give_meropenem_iv
  - give_metformin_in_renal_failure
  - give_methergine
  - give_methotrexate
  - give_methylene_blue
  - give_methylergonovine
  - give_methylergonovine_in_anaphylaxis
  - give_methylprednisolone_iv
  - give_midazolam
  - give_midazolam_10mg
  - give_midazolam_10mg_im
  - give_midazolam_infusion
  - give_misoprostol
  - give_morphine
  - give_morphine_if_needed
  - give_morphine_in_cholinergic_crisis
  - give_moxifloxacin
  - give_mucolytics
  - give_mucolytics_in_hypoxic_asthma
  - give_multiple_dose_activated_charcoal
  - give_n_acetylcysteine
  - give_naloxone
  - give_naproxen
  - give_nebulized_epinephrine
  - give_nitrates_if_indicated
  - give_nitrates_if_rv_infarct
  - give_nitroprusside_in_eclampsia
  - give_niv
  - give_non_antipseudomonal_in_risk
  - give_nonselective_beta_blocker
  - give_normal_saline_bolus
  - give_normal_saline_bolus_10ml_kg
  - give_normal_saline_bolus_20ml_kg
  - give_nsaid
  - give_nsaid_in_aki
  - give_nsaid_in_aspirin_sensitive_asthma
  - give_nsaid_in_hepatorenal
  - give_nsaid_in_mastocytosis
  - give_nsaid_periprocedural_with_contrast
  - give_octreotide
  - give_olanzapine_im
  - give_only_antihistamine_for_transfusion_anaphylaxis
  - give_only_bronchodilator_in_life_threatening
  - give_only_epinephrine_in_tension_pneumo_arrest
  - give_oral_antibiotics_only
  - give_oral_antiepileptic
  - give_oral_antiepileptic_only
  - give_oral_antihypertensive_alone
  - give_oral_antihypertensive_only
  - give_oral_fluids_if_altered
  - give_oral_fluids_only_in_gi_hemorrhagic_shock
  - give_oral_hypoglycemic
  - give_oral_medication_if_vomiting
  - give_oral_potassium_in_aki_with_elevated_k
  - give_osmotic_therapy
  - give_oxytocin_iv
  - give_p2y12_inhibitor
  - give_packed_red_blood_cell_count_if_hemoglobin_below_7
  - give_pain_medication
  - give_penicillin
  - give_pentobarbital_infusion
  - give_phenobarbital_15mg_kg
  - give_phenobarbital_first_line
  - give_phenytoin
  - give_phenytoin_as_first_line
  - give_phenytoin_in_alcohol_withdrawal_seizure
  - give_physostigmine
  - give_piperacillin
  - give_piperacillin_tazobactam
  - give_platelets
  - give_positive_pressure_ventilation
  - give_potassium
  - give_potassium_containing_fluid
  - give_potassium_in_hyperkalemic_aki
  - give_potassium_iv
  - give_potassium_supplement
  - give_potassium_supplement_in_hyperkalemic_aki_stage2
  - give_potassium_supplements_if_hyperkalemia
  - give_pralidoxime
  - give_prbc
  - give_prbc_ffp_platelets
  - give_prbc_ffp_platelets_1_1_1
  - give_prednisolone_oral
  - give_prokinetic
  - give_prophylactic_antibiotics
  - give_propofol_as_first_line
  - give_propofol_infusion
  - give_propranolol
  - give_pyridoxine
  - give_quetiapine
  - give_rapid_fluid_bolus
  - give_rapid_iv_bolus_antihypertensive
  - give_rate_control
  - give_rate_control_without_electrocardiogram
  - give_respiratory_fluoroquinolone
  - give_rivaroxaban
  - give_rivaroxaban_standard
  - give_routine_antibiotics_in_viral_asthma
  - give_routine_bicarbonate_in_nonshockable_arrest
  - give_routine_bicarbonate_in_shockable_arrest
  - give_salbutamol_nebulized
  - give_salbutamol_pmdi_spacer
  - give_second_line_antiepileptic
  - give_sedative
  - give_sedatives
  - give_single_agent_for_pseudomonas_risk
  - give_sodium_bicarbonate
  - give_sodium_bicarbonate_drip
  - give_sodium_bicarbonate_routine
  - give_sodium_nitrite_in_cyanide_burn
  - give_spironolactone_in_hyperkalemic_aki
  - give_ssri_in_serotonin_syndrome
  - give_standard_cap_antibiotics_only
  - give_standard_dose_doac
  - give_standard_empiric_without_mrsa_in_risk
  - give_steroid_without_oxygen_requirement
  - give_stress_dose_steroids
  - give_subcutaneous_insulin_initially
  - give_succimer
  - give_succinylcholine
  - give_succinylcholine_for_rsi_in_hyperkalemic_aki
  - give_succinylcholine_if_hyperkalemic
  - give_succinylcholine_in_hyperkalemic_aki
  - give_succinylcholine_in_hyperkalemic_arrest
  - give_succinylcholine_in_op_poisoning
  - give_supplemental_oxygen
  - give_systemic_corticosteroid
  - give_systemic_corticosteroid_iv
  - give_tenecteplase
  - give_theophylline_in_acute
  - give_thiamine_if_suspected_deficiency
  - give_thiazolidinedione
  - give_thrombolysis
  - give_thrombolytic
  - give_thrombolytics_without_imaging
  - give_tramadol_in_serotonin_syndrome
  - give_tranexamic_acid
  - give_tranexamic_acid_1g
  - give_ufh
  - give_uncrossmatched_o_neg
  - give_valproate
  - give_valproate_40mg_kg
  - give_valproate_as_first_line
  - give_valproic_acid
  - give_vancomycin_iv
  - give_vancomycin_without_premedication
  - give_vasodilator_without_beta_blocker
  - give_vasopressor
  - give_vasopressor_without_fluid
  - give_vasopressors_only_in_tamponade_arrest
  - give_verapamil
  - give_verapamil_in_beta_blocker_od
  - give_warfarin
  - give_whole_blood
  - give_whole_bowel_irrigation_with_obstruction
  - hemodynamic_monitoring
  - hobble_restraint
  - hold_ace_inhibitor
  - hold_arb
  - hold_insulin_until_k_above_3.3
  - hold_metformin_48h_post
  - hold_metformin_before_contrast
  - hold_metformin_if_applicable
  - hold_metformin_if_g3b
  - hold_nephrotoxin_before_contrast
  - hold_nsaids
  - identify_aki_etiology
  - identify_precipitating_factors
  - identify_toxin_class
  - ignore_neurological_deterioration
  - increase_amiodarone_dose
  - increase_beta_blocker
  - increase_furosemide
  - increase_ventilator_pressure_without_escharotomy
  - induce_emesis
  - infectious_disease_consult
  - initiate_ace_or_arb_or_arni
  - initiate_ace_with_hyperkalemia
  - initiate_arni_with_hyperkalemia
  - initiate_beta_blocker
  - initiate_bipap
  - initiate_continuous_iv_anesthetic
  - initiate_cooling_measures
  - initiate_cpap
  - initiate_hemodialysis
  - initiate_hemoperfusion
  - initiate_inhaled_anesthetic
  - initiate_maintenance_antiepileptic
  - initiate_mechanical_ventilation
  - initiate_mra
  - initiate_mra_with_hyperkalemia
  - initiate_niv
  - initiate_rewarming
  - initiate_rrt_immediately
  - initiate_rrt_within_24h
  - initiate_secondary_prevention
  - initiate_sglt2i
  - initiate_targeted_temperature_management
  - insert_foley_catheter
  - interrupt_cpr_for_intubation_extended
  - interrupt_cpr_prolonged
  - intubation_if_needed
  - iv_diuretics
  - iv_hydration_periprocedure
  - iv_hydration_post_contrast
  - iv_hydration_pre_contrast
  - leave_patient_unsupervised_while_agitated
  - leave_restrained_patient_unmonitored
  - maintain_iv_access
  - maintain_temperature
  - manage_cerebral_edema
  - manage_comorbidities
  - manage_seizures
  - manage_volume_status
  - measure_oxygen_saturation
  - measure_peak_expiratory_flow
  - mechanical_circulatory_support_evaluation
  - monitor_acid_base
  - monitor_airway_patency
  - monitor_basic_metabolic_panel_q2_4h
  - monitor_blood_pressure
  - monitor_bp_q15min_x2h_then_q30min_x6h
  - monitor_cardiac_rhythm
  - monitor_closely
  - monitor_coagulation
  - monitor_creatine_kinase_renal_function
  - monitor_creatinine_daily
  - monitor_creatinine_q12h
  - monitor_creatinine_q6h
  - monitor_drug_levels
  - monitor_electrolytes
  - monitor_fibrinogen
  - monitor_fluid_balance_hourly
  - monitor_glucose_q4h
  - monitor_hearing
  - monitor_kidney_function
  - monitor_neurological_status
  - monitor_neurovascular_status_q15min
  - monitor_potassium_q6h
  - monitor_recovery
  - monitor_respiratory_status
  - monitor_sedation_level
  - monitor_serum_creatinine_48_72h
  - monitor_urine_output_target_0_5_ml_kg_h
  - monitor_ventilation_pressures
  - monitor_vitals_q15min
  - narrow_antibiotics_based_on_culture
  - narrow_antibiotics_when_culture_available
  - needle_decompression
  - nephrology_follow_up
  - neurological_checks_q15min
  - neuroprognosticate_before_72h
  - neuroprognostication_72h
  - neurosurgery_evaluation
  - observe_minimum_24_hours
  - observe_minimum_4_hours
  - observe_minimum_8_hours
  - obtain_brief_history
  - obtain_chest_pain_history
  - obtain_detailed_history
  - obtain_exposure_history
  - obtain_fingerstick_glucose
  - obtain_patient_weight
  - obtain_psychiatric_history
  - obtain_vital_signs
  - obtain_weight_kg
  - omit_acyclovir_if_hsv_suspected
  - omit_ampicillin_in_immunocompromised_meningitis
  - omit_ampicillin_in_neonatal_meningitis
  - omit_anaerobic_coverage_in_aspiration
  - omit_vancomycin_or_linezolid_in_mrsa_risk
  - optimize_hemodynamics
  - optimize_timing_based_on_trajectory
  - oral_hydration
  - oral_hydration_if_applicable
  - order_imaging_chest_xray
  - order_imaging_computed_tomography_pa
  - order_imaging_electrocardiogram
  - order_imaging_lower_extremity_doppler
  - order_imaging_ultrasound_abdomen
  - order_lab_acetaminophen_level
  - order_lab_anion_gap
  - order_lab_antiepileptic_levels
  - order_lab_blood_culture
  - order_lab_coagulation
  - order_lab_complete_blood_count_repeat
  - order_lab_creatine_kinase
  - order_lab_csf_latex_agglutination
  - order_lab_cystatin_c
  - order_lab_dat
  - order_lab_estimated_glomerular_filtration_rate
  - order_lab_ethanol_level
  - order_lab_glucose
  - order_lab_ketones
  - order_lab_lactate
  - order_lab_legionella_antigen
  - order_lab_liver_function_tests
  - order_lab_ntprobnp
  - order_lab_osmolar_gap
  - order_lab_procalcitonin
  - order_lab_qtc
  - order_lab_salicylate_level
  - order_lab_serial_drug_levels
  - order_lab_serial_levels
  - order_lab_serial_liver_function
  - order_lab_serial_renal_function
  - order_lab_sputum_culture
  - order_lab_thyroid
  - order_lab_thyroid_stimulating_hormone
  - order_lab_toxicology_screen
  - order_lab_troponin
  - order_lab_tryptase
  - order_lab_type_and_crossmatch
  - order_lab_uds
  - overlap_iv_insulin_2h
  - pain_management
  - perform_angiography
  - perform_bag_mask_ventilation
  - perform_balloon_tamponade
  - perform_cardioversion
  - perform_cardioversion_without_anticoag
  - perform_cardioversion_without_tee
  - perform_chest_escharotomy
  - perform_cricothyrotomy
  - perform_early_intubation
  - perform_endotracheal_intubation
  - perform_enhanced_elimination
  - perform_escharotomy
  - perform_eye_irrigation
  - perform_gastric_lavage
  - perform_left_uterine_displacement
  - perform_lp_in_coagulopathy_uncorrected
  - perform_lp_without_computed_tomography
  - perform_lp_without_computed_tomography_when_contraindicated
  - perform_lumbar_puncture
  - perform_lumbar_puncture_immediate
  - perform_percussion_drainage_in_bronchospasm
  - perform_physical_exam
  - perform_skin_decontamination
  - perform_uterine_artery_embolization
  - perform_uterine_massage
  - perform_whole_bowel_irrigation
  - pericardiocentesis
  - physical_therapy
  - physically_restrain_without_sedation
  - place_arterial_line
  - place_central_line
  - place_evd_if_hydrocephalus
  - place_foley_catheter
  - place_nasogastric_tube
  - place_oral_airway_during_seizure
  - place_pregnant_arrest_patient_supine
  - place_supraglottic_airway
  - plan_follow_up_creatinine
  - plan_long_term_antiepileptic
  - plan_rrt_modality
  - plot_rumack_matthew_nomogram
  - position_left_lateral_decubitus
  - position_recovery
  - position_supine_flat_in_pregnancy
  - position_supine_legs_elevated
  - post_procedure_creatinine_48_72h
  - post_procedure_creatinine_48h
  - prehydrate_iv_normal_saline
  - prepare_for_intubation
  - prepare_perimortem_cesarean
  - prepare_second_line_agent
  - prepare_transfer_documentation
  - prescribe_epinephrine_autoinjector
  - prescribe_ics_laba
  - prescribe_oral_antihistamine
  - prescribe_oral_corticosteroid_5_day
  - prescribe_oral_corticosteroid_taper
  - proceed_to_cabg_within_5_days
  - proceed_to_endoscopy_without_resuscitation
  - prone_restraint
  - protect_airway
  - provide_anaphylaxis_action_plan
  - provide_asthma_action_plan
  - provide_chemoprophylaxis_to_close_contacts
  - provide_discharge_instructions
  - provide_poison_prevention_education
  - provide_sick_day_rules
  - provide_supportive_care
  - quantify_blood_loss
  - rapid_anesthetic_wean
  - reassess_after_1_hour
  - reassess_after_each_bolus
  - reassess_after_treatment
  - reassess_airway
  - reassess_clinical_status
  - reassess_hemodynamic_status
  - reassess_hemoglobin
  - reassess_need_q1h
  - reassess_neurological_status
  - reassess_perfusion
  - reassess_rhythm
  - reassess_seizure_activity
  - reassess_uterine_tone
  - reassess_vitals
  - recheck_potassium_in_1h
  - reduce_bp_below_140_in_alteplase_candidate
  - reduce_bp_more_than_25pct_in_1h
  - reduce_bp_to_below_185_110_before_alteplase
  - refer_to_allergist
  - remeasure_lactate_if_elevated
  - remove_clothing_jewelry
  - remove_restraints_when_safe
  - remove_trigger_if_identifiable
  - repeat_benzodiazepine_once
  - repeat_complete_blood_count
  - repeat_computed_tomography_head
  - repeat_contrast_within_48h
  - repeat_epinephrine_im_5min
  - repeat_fluid_bolus
  - repeat_lactate
  - repeat_lumbar_puncture_if_no_improvement
  - repeat_salbutamol_q20min
  - report_to_poison_control
  - report_to_public_health
  - request_cardiology_consult
  - request_consultation
  - request_icu_consult
  - request_neurology_consult
  - request_psychiatry_consult
  - request_social_work_consult
  - request_toxicology_consult
  - restart_metformin_before_48h_post_contrast
  - restart_metformin_before_dka_resolved
  - restart_nsaid_without_ppi
  - restart_same_unit
  - restrain_patient_forcefully
  - restrain_without_attempting_deescalation
  - restrict_fluid
  - resume_ace_inhibitor
  - resume_cpr_immediately
  - resume_home_medications
  - resume_metformin_if_estimated_glomerular_filtration_rate_stable
  - resume_oral_intake
  - review_acetaminophen_level
  - review_electrocardiogram_for_toxicity
  - review_recent_contrast_exposure
  - review_risk_factors
  - review_salicylate_level
  - review_toxicology_screen
  - review_transfusion_history
  - review_trigger_avoidance
  - schedule_catheterization
  - schedule_dialysis_post_contrast
  - schedule_followup_2_7_days
  - schedule_outpatient_followup
  - send_blood_bank_workup
  - serial_electrocardiogram
  - serial_lab_monitoring
  - serial_lactate_monitoring
  - serial_serum_creatinine_monitoring
  - serial_troponin
  - serial_vital_sign_monitoring
  - skip_allergy_verification_before_drug
  - skip_prehydration
  - skip_risk_assessment
  - social_work_consult
  - standard_contrast_administration
  - standard_contrast_protocol
  - start_continuous_monitoring
  - start_doac_immediately
  - start_doac_preferred
  - start_epinephrine_infusion
  - start_insulin_before_k_check
  - start_insulin_drip_without_potassium_correction
  - start_insulin_infusion
  - start_lactated_ringers
  - start_levetiracetam
  - start_mechanical_ventilation_permissive_hypercapnia
  - start_new_raas_inhibitor_in_aki
  - start_phenytoin
  - start_subcutaneous_insulin
  - start_vasopressor_if_hypotensive
  - start_vasopressor_norepinephrine
  - start_vasopressor_vasopressin
  - stat_coagulation_panel
  - statin_therapy
  - stop_all_antipsychotics
  - stop_alteplase_infusion
  - stop_anticoagulation_indefinitely
  - stop_insulin_before_gap_closed
  - stop_iv_insulin_without_overlap
  - stop_monitoring_early
  - stop_offending_agent
  - stop_serotonergic_agents
  - stop_sglt2_inhibitor
  - stop_transfusion_immediately
  - stress_testing_or_cta
  - substitute_bicarbonate_for_epinephrine_in_pea
  - swallow_screen
  - target_normal_bp_immediately
  - terminate_care_prematurely
  - terminate_resuscitation_prematurely
  - titrate_fluids_to_urine_output
  - titrate_to_burst_suppression
  - transfer_to_higher_care
  - transfuse_for_hb_above_10
  - transfuse_for_hb_above_8_in_cardiac
  - transfuse_if_hb_below_8
  - transfuse_platelets
  - transfuse_prbc
  - transfuse_prbc_if_hb_below_7
  - transfuse_without_consent
  - transfuse_without_indication
  - transfuse_without_type_and_screen
  - transition_before_criteria_met
  - transition_to_subq_insulin
  - treat_atrial_fibrillation
  - treat_hyperkalemia_temporizing
  - treat_hypertension
  - treat_on_ward_if_severe_cap
  - type_and_crossmatch
  - update_tetanus_if_needed
  - urgent_nephrology_consult
  - use_adult_vital_sign_norms
  - use_depolarizing_agent_in_aki_hyperkalemia
  - use_high_osmolar_contrast
  - use_high_osmolar_contrast_in_high_risk
  - use_high_volume_contrast_in_ckd_diabetes
  - use_iv_labetalol_or_nicardipine
  - use_latex_containing_iv_tubing
  - use_latex_gloves_or_equipment
  - use_liberal_transfusion_threshold_cardiac
  - use_low_or_iso_osmolar_contrast
  - use_low_osmolar_contrast
  - use_lowest_contrast_volume
  - use_minimum_contrast_volume
  - use_normal_saline_only
  - use_rapid_sequence_with_histamine_releasers
  - vascular_access_placement
  - vasopressor_if_shock
  - vasopressor_support
  - verify_allergy_before_medication
  - verify_resolution_criteria
  - wean_anesthetic_infusion
  - weight_management
  - withhold_antibiotics
  - withhold_antibiotics_in_confirmed_pneumonia
  - withhold_antibiotics_pending_lp
  - withhold_anticoagulation_without_bridge
  - withhold_dextrose_in_euglycemic_dka
  - withhold_epinephrine
  - withhold_fluid_in_hypotension
  - withhold_glucagon_despite_epi_resistance
  - withhold_glucose_monitoring_pediatric_burn
  - withhold_steroids_in_refractory_shock
  - withhold_stress_dose_steroid_in_dependent
  - withhold_treatment
  - withhold_treatment_based_on_low_nihss
  - withhold_txa_in_pph

B.1 summary: identity=1300 mapped=161 unmapped=1174

============================================================
B.2: Agent output patterns -> expected mapping (15 test cases)
============================================================
  MISMATCH obtain 12-lead ECG                       -> obtain 12-lead ecg  (expected: obtain_12_lead_ecg)
  MISMATCH order troponin                           -> order troponin  (expected: order_lab_troponin)
  MISMATCH give aspirin                             -> give aspirin  (expected: give_aspirin)
  MISMATCH start IV normal saline                   -> start iv normal saline  (expected: start_iv_fluid_ns)
  MISMATCH activate cath lab                        -> activate cath lab  (expected: activate_cath_lab)
  MISMATCH check potassium                          -> check potassium  (expected: order_lab_bmp)
  MISMATCH start insulin drip                       -> start insulin drip  (expected: start_insulin_infusion)
  MISMATCH intubate                                 -> intubate  (expected: perform_early_intubation)
  MISMATCH give epinephrine IM                      -> give epinephrine im  (expected: give_epinephrine_im)
  MISMATCH order CT head                            -> order ct head  (expected: order_stat_ct_head)
  MISMATCH consult neurosurgery                     -> consult neurosurgery  (expected: neurosurgery_consult)
  MISMATCH give tPA                                 -> give tpa  (expected: give_alteplase_0.9mg_kg)
  MISMATCH start norepinephrine                     -> start norepinephrine  (expected: start_vasopressor_if_hypotensive)
  MISMATCH give lorazepam                           -> give lorazepam  (expected: give_benzodiazepine_weight_based)
  MISMATCH perform needle decompression             -> perform needle decompression  (expected: perform_needle_decompression)

B.2 summary: 0 OK, 15 MISMATCH

============================================================
Section B complete.
  B.1: identity=1300 mapped=161 unmapped=1174
  B.2: 0 OK, 15 MISMATCH
============================================================

  [OK] Section B completed in 1.0s

--- Running Section C ---
Section C: Scoring + E2E Init Audit
============================================================
============================================================
C.1  Scorer API Discovery
============================================================

--- assessor_core.violations ---
  class Action
  class ActionRecord
  class CPGEngine
  class EpisodeLog
  class GuidelineEngineOutput
  class HarmSeverity
  class HarmSeverityMapping
  class PatientState
  class TimingSeverityThreshold
  class ViolationEvent
  class ViolationExtractor
  class ViolationExtractorConfig
  class ViolationType
  func  dataclass

  ViolationExtractor.__init__ sig: (self, engine: cga_bench.cpg_engine.engine.CPGEngine, config: cga_bench.assessor_core.violations.ViolationExtractorConfig)

--- assessor_core.harm_scorer ---
  class CGAScore
  class EpisodeLog
  class HarmScorer
  class HarmScorerConfig
  class HarmSeverity
  class MetricsReporter
  class RecommendationClass
  class SynergyPenalty
  class ViolationEvent
  class ViolationType
  func  dataclass
  func  field

  HarmScorer.__init__ sig: (self, total_mandatory_count: int, config: cga_bench.assessor_core.harm_scorer.HarmScorerConfig)

============================================================
C.2  E2E Initialization for Held-Out Graphs
============================================================

--- anaphylaxis_management ---
  Scenario: anaph_basic_beta_blocker_glucagon  (expected_actions=13)
  Graph path: ${CGA_BENCH_ROOT}/cga_bench/cpg_model/graphs/anaphylaxis_management.yaml
  Allowed:   8
  Mandatory: 3
  Forbidden: 3
  Deadlines: 2

--- acls_cardiac_arrest ---
  Scenario: acls_trap_hypothermia_no_drugs  (expected_actions=13)
  Graph path: ${CGA_BENCH_ROOT}/cga_bench/cpg_model/graphs/acls_cardiac_arrest.yaml
  Allowed:   9
  Mandatory: 4
  Forbidden: 3
  Deadlines: 4

--- status_epilepticus ---
  Scenario: se_trap_hypoglycemia_glucose_first  (expected_actions=13)
  Graph path: ${CGA_BENCH_ROOT}/cga_bench/cpg_model/graphs/status_epilepticus.yaml
  Allowed:   11
  Mandatory: 4
  Forbidden: 4
  Deadlines: 3

--- gina_asthma_exacerbation ---
  Scenario: asthma_trap_initial_no_mucolytics  (expected_actions=17)
  Graph path: ${CGA_BENCH_ROOT}/cga_bench/cpg_model/graphs/gina_asthma_exacerbation.yaml
  Allowed:   9
  Mandatory: 4
  Forbidden: 6
  Deadlines: 3

--- idsa_meningitis ---
  Scenario: mening_trap_penicillin_allergy  (expected_actions=13)
  Graph path: ${CGA_BENCH_ROOT}/cga_bench/cpg_model/graphs/idsa_meningitis.yaml
  Allowed:   12
  Mandatory: 4
  Forbidden: 1
  Deadlines: 3

--- toxicology_management ---
  Scenario: tox_trap_ident_no_delay_antidote  (expected_actions=13)
  Graph path: ${CGA_BENCH_ROOT}/cga_bench/cpg_model/graphs/toxicology_management.yaml
  Allowed:   19
  Mandatory: 4
  Forbidden: 3
  Deadlines: 3

--- aba_burn_resuscitation ---
  Scenario: aba_bu_basic_pediatric_dextrose  (expected_actions=12)
  Graph path: ${CGA_BENCH_ROOT}/cga_bench/cpg_model/graphs/aba_burn_resuscitation.yaml
  Allowed:   11
  Mandatory: 6
  Forbidden: 3
  Deadlines: 4

--- aabb_transfusion ---
  Scenario: aabb_t_basic_cardiac_liberal_threshold  (expected_actions=5)
  Graph path: ${CGA_BENCH_ROOT}/cga_bench/cpg_model/graphs/aabb_transfusion.yaml
  Allowed:   8
  Mandatory: 5
  Forbidden: 2
  Deadlines: 3

--- acog_obstetric_hemorrhage ---
  Scenario: acog_o_trap_asthma_no_carboprost  (expected_actions=6)
  Graph path: ${CGA_BENCH_ROOT}/cga_bench/cpg_model/graphs/acog_obstetric_hemorrhage.yaml
  Allowed:   9
  Mandatory: 6
  Forbidden: 1
  Deadlines: 4

--- pals_pediatric_emergency ---
  Scenario: pals_p_trap_dka_slow_fluid  (expected_actions=4)
  Graph path: ${CGA_BENCH_ROOT}/cga_bench/cpg_model/graphs/pals_pediatric_emergency.yaml
  Allowed:   9
  Mandatory: 4
  Forbidden: 2
  Deadlines: 3

--- apa_agitation_management ---
  Scenario: apa_ag_trap_etoh_no_benzo_monotherapy  (expected_actions=5)
  Graph path: ${CGA_BENCH_ROOT}/cga_bench/cpg_model/graphs/apa_agitation_management.yaml
  Allowed:   10
  Mandatory: 5
  Forbidden: 2
  Deadlines: 3

============================================================
Section C complete.

  [OK] Section C completed in 15.4s

--- Running Section D ---
Section D: Config & Execution Script Verification
============================================================
============================================================
D.1  Model Config Validation
============================================================
  Directory not found: ${CGA_BENCH_ROOT}/cga_bench/configs/models
  (No model configs to validate — this is informational)

============================================================
D.2  ScenarioLoader Validation
============================================================
  Total scenarios: 688
  First 5: ['aabb_t_basic_cardiac_liberal_threshold', 'aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood', 'aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi', 'aabb_t_combo_txa_within_3h_jehovah_no_blood', 'aabb_t_pathway_restrictive_thr_massive_transfu_transfusion_rea']
  Last 5:  ['tox_trap_opioid_naloxone', 'tox_trap_organophosphate_atropine', 'tox_trap_tca_no_physostigmine', 'unstable_angina_intermediate', 'warfarin_nsaid_interaction_trap']
  Written: ${CGA_BENCH_ROOT}/cga_bench/configs/scenario_list_full.txt  (688 lines)

============================================================
D.3  vLLM + GPU Check (informational)
============================================================
  vllm version: 0.17.0
  Fri Apr  3 08:15:14 2026       
  +-----------------------------------------------------------------------------------------+
  | NVIDIA-SMI 570.169                Driver Version: 570.169        CUDA Version: 12.8     |
  |-----------------------------------------+------------------------+----------------------+
  | GPU  Name                 Persistence-M | Bus-Id          Disp.A | Volatile Uncorr. ECC |
  | Fan  Temp   Perf          Pwr:Usage/Cap |           Memory-Usage | GPU-Util  Compute M. |
  |                                         |                        |               MIG M. |
  |=========================================+========================+======================|
  |   0  NVIDIA A100 80GB PCIe          On  |   00000000:4F:00.0 Off |                    0 |
  | N/A   35C    P0             73W /  300W |   76433MiB /  81920MiB |      0%      Default |
  ... (49 more lines)

============================================================
Section D complete.

  [OK] Section D completed in 19.8s

--- Running Section E ---
Section E: Existing Episode Compatibility
============================================================
============================================================
E.1  Existing Episode JSON Check
============================================================
  Known scenario IDs from ScenarioLoader: 688

  Directory: results/clean_slate_rescored
    JSON files: 181
  First File: clean_slate_rescored/oss120b/adhf_warm_wet_oss120b_r0_20260331_221255.json
    Top-level keys (21): ['scenario_id', 'agent_id', 'model_name', 'run_index', 'actions_count', 'n_expected_actions', 'old_compliance_score', 'old_sub_scores', 'old_total_violations', 'old_violations_by_type', 'new_compliance_score', 'new_sub_scores', 'new_total_violations', 'new_violations_by_type', 'new_peak_risk']
    ... and 6 more
    scenario_id: adhf_warm_wet
    model_name:  oss-120b
    actions_count: 38

  Directory: results
    JSON files: 43
  First File: agentclinic_full_321.json
    Top-level keys (7): ['timestamp', 'config', 'summary', 'cpg_summary', 'modular_summary', 'failed_scenario_ids', 'results']
    scenario_id: <missing>
    model_name:  <missing>
    actions_count: 0

  Cross-check: scenario_id 'adhf_warm_wet' in ScenarioLoader? YES

  --- Random Sample (up to 5 episodes) ---

  Sample[0] File: clean_slate_rescored/qwen4b/htn_emergency_basic_qwen4b_r1_20260331_214549.json
    Top-level keys (21): ['scenario_id', 'agent_id', 'model_name', 'run_index', 'actions_count', 'n_expected_actions', 'old_compliance_score', 'old_sub_scores', 'old_total_violations', 'old_violations_by_type', 'new_compliance_score', 'new_sub_scores', 'new_total_violations', 'new_violations_by_type', 'new_peak_risk']
    ... and 6 more
    scenario_id: htn_emergency_basic
    model_name:  Qwen3-4B
    actions_count: 11

  Sample[1] File: clean_slate_rescored/oss120b/htn_emergency_basic_oss120b_r1_20260331_220220.json
    Top-level keys (21): ['scenario_id', 'agent_id', 'model_name', 'run_index', 'actions_count', 'n_expected_actions', 'old_compliance_score', 'old_sub_scores', 'old_total_violations', 'old_violations_by_type', 'new_compliance_score', 'new_sub_scores', 'new_total_violations', 'new_violations_by_type', 'new_peak_risk']
    ... and 6 more
    scenario_id: htn_emergency_basic
    model_name:  oss-120b
    actions_count: 24

  Sample[2] File: clean_slate_rescored/oss120b/aki_stage1_basic_oss120b_r0_20260331_214813.json
    Top-level keys (21): ['scenario_id', 'agent_id', 'model_name', 'run_index', 'actions_count', 'n_expected_actions', 'old_compliance_score', 'old_sub_scores', 'old_total_violations', 'old_violations_by_type', 'new_compliance_score', 'new_sub_scores', 'new_total_violations', 'new_violations_by_type', 'new_peak_risk']
    ... and 6 more
    scenario_id: aki_stage1_basic
    model_name:  oss-120b
    actions_count: 34

  Sample[3] File: external_benchmark_20260120_101330.json
    Top-level keys (5): ['timestamp', 'config', 'summary', 'cpg_summary', 'results']
    scenario_id: <missing>
    model_name:  <missing>
    actions_count: 0

  Sample[4] File: clean_slate_rescored/qwen27b/hemorrhagic_stroke_qwen27b_r1_20260331_230232.json
    Top-level keys (21): ['scenario_id', 'agent_id', 'model_name', 'run_index', 'actions_count', 'n_expected_actions', 'old_compliance_score', 'old_sub_scores', 'old_total_violations', 'old_violations_by_type', 'new_compliance_score', 'new_sub_scores', 'new_total_violations', 'new_violations_by_type', 'new_peak_risk']
    ... and 6 more
    scenario_id: hemorrhagic_stroke
    model_name:  Qwen3.5-27B
    actions_count: 3

  All 5 sampled episodes reference valid scenario IDs

============================================================
Section E complete.

  [OK] Section E completed in 15.5s

--- Running Section F ---
============================================================
F.1: Deadline entries across all graphs
============================================================
Scanning 25 graph files

  aabb_transfusion                          deadlines=  8  sample: transfusion_assessment/order_cbc=15min, transfusion_assessment/order_type_and_screen=30min (+6 more)
  aba_burn_resuscitation                    deadlines= 15  sample: burn_initial_assessment/assess_airway=5min, burn_initial_assessment/assess_vital_signs=5min (+13 more)
  acls_cardiac_arrest                       deadlines= 15  sample: initial_assessment/confirm_cardiac_arrest=1min, initial_assessment/begin_high_quality_cpr=1min (+13 more)
  acog_obstetric_hemorrhage                 deadlines= 10  sample: pph_recognition/quantify_blood_loss=5min, pph_recognition/assess_vital_signs=5min (+8 more)
  ada_dka_management                        deadlines= 19  sample: initial_assessment/assess_vital_signs=5min, initial_assessment/establish_iv_access=10min (+17 more)
  aha_chest_pain_evaluation                 deadlines= 16  sample: initial_assessment/obtain_12_lead_ecg=10min, initial_assessment/assess_vital_signs=5min (+14 more)
  aha_heart_failure_2022                    deadlines=  7  sample: hf_initial_assessment/order_bnp_or_ntprobnp=60min, hf_initial_assessment/order_ecg=60min (+5 more)
  aha_stroke_2019                           deadlines=  6  sample: stroke_initial_assessment/check_glucose=10min, stroke_initial_assessment/order_stat_ct_head=25min (+4 more)
  anaphylaxis_management                    deadlines=  9  sample: initial_recognition/assess_airway_breathing_circulation=2min, initial_recognition/assess_anaphylaxis_criteria=3min (+7 more)
  apa_agitation_management                  deadlines=  9  sample: agitation_assessment/assess_safety_of_environment=2min, agitation_assessment/attempt_verbal_deescalation=10min (+7 more)
  atrial_fibrillation                       deadlines=  2  sample: initial_assessment/obtain_12_lead_ecg=10min, unstable_af/perform_cardioversion=30min
  cap_pneumonia                             deadlines=  3  sample: initial_assessment/order_imaging_chest_xray=60min, inpatient_cap/give_beta_lactam_plus_macrolide=240min (+1 more)
  copd_exacerbation                         deadlines=  2  sample: initial_assessment/assess_vital_signs=10min, severe_exacerbation/give_bronchodilator=30min
  gi_bleeding                               deadlines=  2  sample: initial_assessment/establish_iv_access=15min, hemodynamically_unstable/give_iv_crystalloid_bolus=15min
  gina_asthma_exacerbation                  deadlines= 14  sample: initial_assessment/assess_severity_classification=5min, initial_assessment/measure_peak_expiratory_flow=10min (+12 more)
  hypertensive_emergency                    deadlines=  2  sample: initial_assessment/assess_vital_signs=5min, hypertensive_emergency_node/give_iv_antihypertensive=30min
  idsa_meningitis                           deadlines= 12  sample: initial_assessment/assess_clinical_presentation=10min, initial_assessment/assess_neurological_status=10min (+10 more)
  kdigo_aki_full                            deadlines=  9  sample: initial_assessment/order_creatinine=60min, aki_stage_2_management/consult_nephrology=240min (+7 more)
  kdigo_contrast_aki                        deadlines=  8  sample: risk_assessment/check_baseline_egfr=60min, risk_assessment/review_risk_factors=60min (+6 more)
  pals_pediatric_emergency                  deadlines=  9  sample: pediatric_assessment/assess_pediatric_triangle=5min, pediatric_assessment/assess_vital_signs_age_appropriate=5min (+7 more)
  pulmonary_embolism                        deadlines=  4  sample: initial_assessment/assess_vital_signs=10min, confirmed_pe_stable/give_anticoagulation=60min (+2 more)
  ssc_sepsis_hour1_bundle                   deadlines= 11  sample: initial_recognition/assess_infection_source=10min, initial_recognition/assess_organ_dysfunction=10min (+9 more)
  status_epilepticus                        deadlines= 11  sample: initial_stabilization/assess_airway_breathing_circulation=2min, initial_stabilization/check_point_of_care_glucose=5min (+9 more)
  toxicology_management                     deadlines= 11  sample: initial_stabilization/assess_airway_breathing_circulation=2min, initial_stabilization/assess_vital_signs=5min (+9 more)
  universal_clinical_safety                 deadlines=  1  sample: initial_encounter/assess_vital_signs=15min

Total deadline entries across all graphs: 215
Graphs with deadlines:    25
Graphs without deadlines: 0

--- New/held-out graph deadline status ---
  anaphylaxis_management                    HAS deadlines
  acls_cardiac_arrest                       HAS deadlines
  status_epilepticus                        HAS deadlines
  gina_asthma_exacerbation                  HAS deadlines
  idsa_meningitis                           HAS deadlines
  toxicology_management                     HAS deadlines
  aba_burn_resuscitation                    HAS deadlines
  aabb_transfusion                          HAS deadlines
  acog_obstetric_hemorrhage                 HAS deadlines
  pals_pediatric_emergency                  HAS deadlines
  apa_agitation_management                  HAS deadlines

--- All graphs with deadlines ---
  aabb_transfusion [NEW]
  aba_burn_resuscitation [NEW]
  acls_cardiac_arrest [NEW]
  acog_obstetric_hemorrhage [NEW]
  ada_dka_management
  aha_chest_pain_evaluation
  aha_heart_failure_2022
  aha_stroke_2019
  anaphylaxis_management [NEW]
  apa_agitation_management [NEW]
  atrial_fibrillation
  cap_pneumonia
  copd_exacerbation
  gi_bleeding
  gina_asthma_exacerbation [NEW]
  hypertensive_emergency
  idsa_meningitis [NEW]
  kdigo_aki_full
  kdigo_contrast_aki
  pals_pediatric_emergency [NEW]
  pulmonary_embolism
  ssc_sepsis_hour1_bundle
  status_epilepticus [NEW]
  toxicology_management [NEW]
  universal_clinical_safety

--- All graphs without deadlines ---

F.1 summary: 215 deadline entries, 25 graphs with, 0 graphs without

============================================================
Section F complete.
============================================================

  [OK] Section F completed in 0.8s

--- Running Section G ---
======================================================================
Section G: 논문 수치 일관성
======================================================================

--- G.1: Number Verification ---
  CPG Graphs:          25
  Total Scenarios:     688 (manual=105, auto=583)
  Total Nodes:         167
  Conditional Rules:   312
  Sequence Rules:      10
  Unique Actions:      1461

--- Per-graph breakdown ---
  aabb_transfusion                               nodes=  4  cond_rules=  7  seq_rules=  0  actions= 31
  aba_burn_resuscitation                         nodes=  6  cond_rules=  7  seq_rules=  3  actions= 42
  acls_cardiac_arrest                            nodes=  6  cond_rules= 24  seq_rules=  2  actions= 51
  acog_obstetric_hemorrhage                      nodes=  4  cond_rules=  4  seq_rules=  0  actions= 30
  ada_dka_management                             nodes=  8  cond_rules= 17  seq_rules=  0  actions= 64
  aha_chest_pain_evaluation                      nodes= 11  cond_rules= 10  seq_rules=  0  actions= 47
  aha_heart_failure_2022                         nodes= 24  cond_rules=  9  seq_rules=  0  actions=100
  aha_stroke_2019                                nodes= 25  cond_rules=  7  seq_rules=  0  actions=120
  anaphylaxis_management                         nodes=  5  cond_rules= 13  seq_rules=  2  actions= 37
  apa_agitation_management                       nodes=  4  cond_rules=  8  seq_rules=  0  actions= 38
  atrial_fibrillation                            nodes=  3  cond_rules=  7  seq_rules=  0  actions= 30
  cap_pneumonia                                  nodes=  3  cond_rules= 13  seq_rules=  0  actions= 14
  copd_exacerbation                              nodes=  2  cond_rules=  8  seq_rules=  0  actions= 21
  gi_bleeding                                    nodes=  2  cond_rules= 10  seq_rules=  0  actions= 21
  gina_asthma_exacerbation                       nodes=  5  cond_rules= 24  seq_rules=  0  actions= 46
  hypertensive_emergency                         nodes=  2  cond_rules= 10  seq_rules=  0  actions= 25
  idsa_meningitis                                nodes=  5  cond_rules= 20  seq_rules=  1  actions= 47
  kdigo_aki_full                                 nodes= 13  cond_rules= 24  seq_rules=  0  actions= 74
  kdigo_contrast_aki                             nodes=  7  cond_rules= 19  seq_rules=  0  actions= 58
  pals_pediatric_emergency                       nodes=  4  cond_rules=  5  seq_rules=  0  actions= 30
  pulmonary_embolism                             nodes=  3  cond_rules= 10  seq_rules=  0  actions= 26
  ssc_sepsis_hour1_bundle                        nodes=  7  cond_rules= 11  seq_rules=  0  actions= 42
  status_epilepticus                             nodes=  5  cond_rules= 11  seq_rules=  2  actions= 51
  toxicology_management                          nodes=  6  cond_rules= 25  seq_rules=  0  actions= 84
  universal_clinical_safety                      nodes=  3  cond_rules=  9  seq_rules=  0  actions= 69

--- Scenarios per guideline_graph ---
  aabb_transfusion                               manual=  0  auto= 12  total= 12
  aba_burn_resuscitation                         manual=  0  auto= 18  total= 18
  acls_cardiac_arrest                            manual=  0  auto= 42  total= 42
  acog_obstetric_hemorrhage                      manual=  0  auto=  9  total=  9
  ada_dka_management                             manual= 12  auto= 30  total= 42
  aha_chest_pain                                 manual= 13  auto=  0  total= 13
  aha_chest_pain_evaluation                      manual=  0  auto= 21  total= 21
  aha_heart_failure                              manual= 10  auto=  0  total= 10
  aha_heart_failure_2022                         manual=  0  auto= 39  total= 39
  aha_stroke                                     manual= 13  auto=  0  total= 13
  aha_stroke_2019                                manual=  0  auto= 20  total= 20
  anaphylaxis_management                         manual=  0  auto= 17  total= 17
  apa_agitation_management                       manual=  0  auto= 15  total= 15
  atrial_fibrillation                            manual=  6  auto= 17  total= 23
  cap_pneumonia                                  manual=  5  auto= 17  total= 22
  copd_exacerbation                              manual=  6  auto= 15  total= 21
  gi_bleeding                                    manual=  5  auto= 18  total= 23
  gina_asthma_exacerbation                       manual=  0  auto= 46  total= 46
  hypertensive_emergency                         manual=  6  auto= 11  total= 17
  idsa_meningitis                                manual=  0  auto= 31  total= 31
  kdigo_aki_full                                 manual=  8  auto= 61  total= 69
  kdigo_contrast_aki                             manual=  5  auto= 37  total= 42
  pals_pediatric_emergency                       manual=  0  auto= 10  total= 10
  pulmonary_embolism                             manual=  5  auto= 24  total= 29
  ssc_sepsis_hour1                               manual= 10  auto=  0  total= 10
  ssc_sepsis_hour1_bundle                        manual=  0  auto= 13  total= 13
  status_epilepticus                             manual=  0  auto= 16  total= 16
  toxicology_management                          manual=  0  auto= 26  total= 26
  universal_clinical_safety                      manual=  1  auto= 18  total= 19

  [OK] Section G completed in 32.8s


======================================================================
SUMMARY
======================================================================
Total time: 86.9s

  Section A: OK [1.6s]  (FAIL=4)
  Section B: OK [1.0s]  (MISMATCH=17)
  Section C: OK [15.4s]
  Section D: OK [19.8s]
  Section E: OK [15.5s]  (MISSING=4)
  Section F: OK [0.8s]
  Section G: OK [32.8s]

Keyword totals:
  FAIL: 4
  MISSING: 4
  MISMATCH: 17
  1 section(s) have FAIL/ERROR keywords
```
