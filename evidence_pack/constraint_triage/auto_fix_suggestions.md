# 자동 수정 제안

## BUG: action_effects.yaml에 없는 REQUIRED actions
이 actions는 REQUIRED로 지정되어 있지만 시뮬레이션에서 수행 불가능합니다.
두 가지 수정 방법:
  A) action_effects.yaml에 해당 action 추가
  B) graph YAML에서 해당 action을 soft constraint로 변경


### aba_burn_resuscitation
  - pain_management [BUG_NOT_IN_EFFECTS]
  - update_tetanus_if_needed [BUG_NOT_IN_EFFECTS]
  - perform_early_intubation [BUG_NOT_IN_EFFECTS]
  - perform_escharotomy [BUG_NOT_IN_EFFECTS]
  - remove_clothing_jewelry [BUG_NOT_IN_EFFECTS]

### acls_cardiac_arrest
  - optimize_hemodynamics [BUG_NOT_IN_EFFECTS]

### ada_dka_management
  - verify_resolution_criteria [BUG_NOT_IN_EFFECTS]
  - start_subcutaneous_insulin [BUG_NOT_IN_EFFECTS]
  - resume_oral_intake [BUG_NOT_IN_EFFECTS]
  - recheck_potassium_in_1h [BUG_NOT_IN_EFFECTS]

### aha_chest_pain_evaluation
  - stress_testing_or_cta [BUG_NOT_IN_EFFECTS]

### aha_heart_failure_2022
  - identify_precipitating_factors [BUG_NOT_IN_EFFECTS]
  - monitor_electrolytes [BUG_NOT_IN_EFFECTS]
  - optimize_gdmt_titration [BUG_NOT_IN_EFFECTS]
  - iv_diuretics [BUG_NOT_IN_EFFECTS]
  - palliative_care_discussion [BUG_NOT_IN_EFFECTS]
  - monitor_for_deterioration [BUG_NOT_IN_EFFECTS]
  - initiate_ace_or_arb_or_arni [BUG_NOT_IN_EFFECTS]
  - hemodynamic_monitoring [BUG_NOT_IN_EFFECTS]
  - list_if_appropriate [BUG_NOT_IN_EFFECTS]
  - psychosocial_evaluation [BUG_NOT_IN_EFFECTS]
  - lvad_workup [BUG_NOT_IN_EFFECTS]
  - initiate_sglt2i [BUG_NOT_IN_EFFECTS]
  - patient_education [BUG_NOT_IN_EFFECTS]
  - select_mcs_device [BUG_NOT_IN_EFFECTS]
  - evaluate_diastolic_function [BUG_NOT_IN_EFFECTS]
  - mechanical_circulatory_support_evaluation [BUG_NOT_IN_EFFECTS]
  - initiate_mra [BUG_NOT_IN_EFFECTS]
  - implant_crt [BUG_NOT_IN_EFFECTS]
  - invasive_hemodynamic_monitoring [BUG_NOT_IN_EFFECTS]
  - multidisciplinary_team_evaluation [BUG_NOT_IN_EFFECTS]
  - obtain_informed_consent [BUG_NOT_IN_EFFECTS]
  - manage_volume_status [BUG_NOT_IN_EFFECTS]
  - implant_icd [BUG_NOT_IN_EFFECTS]
  - hospice_referral_if_appropriate [BUG_NOT_IN_EFFECTS]
  - initiate_beta_blocker [BUG_NOT_IN_EFFECTS]
  - increase_diuretic_dose [BUG_NOT_IN_EFFECTS]
  - manage_comorbidities [BUG_NOT_IN_EFFECTS]
  - regular_follow_up [BUG_NOT_IN_EFFECTS]
  - monitor_kidney_function [BUG_NOT_IN_EFFECTS]
  - symptom_management [BUG_NOT_IN_EFFECTS]
  - identify_etiology [BUG_NOT_IN_EFFECTS]

### aha_stroke_2019
  - statin_therapy [BUG_NOT_IN_EFFECTS]
  - repeat_ct_6h_or_if_deterioration [BUG_NOT_IN_EFFECTS]
  - discharge_planning [BUG_NOT_IN_EFFECTS]
  - stop_tpa_infusion [BUG_NOT_IN_EFFECTS]
  - document_shared_decision [BUG_NOT_IN_EFFECTS]
  - dual_antiplatelet_before_procedure [BUG_NOT_IN_EFFECTS]
  - speech_therapy_if_needed [BUG_NOT_IN_EFFECTS]
  - neurosurgery_evaluation [BUG_NOT_IN_EFFECTS]
  - elevate_head_of_bed [BUG_NOT_IN_EFFECTS]
  - perform_thrombectomy_procedure [BUG_NOT_IN_EFFECTS]
  - reverse_anticoagulation_if_applicable [BUG_NOT_IN_EFFECTS]
  - use_iv_labetalol_or_nicardipine [BUG_NOT_IN_EFFECTS]
  - confirm_stenosis_degree [BUG_NOT_IN_EFFECTS]
  - stat_coagulation_panel [BUG_NOT_IN_EFFECTS]
  - review_exclusion_criteria [BUG_NOT_IN_EFFECTS]
  - evaluate_for_recurrent_stroke [BUG_NOT_IN_EFFECTS]
  - obtain_informed_consent [BUG_NOT_IN_EFFECTS]
  - perform_cas [BUG_NOT_IN_EFFECTS]
  - give_cryoprecipitate [BUG_NOT_IN_EFFECTS]
  - physical_therapy [BUG_NOT_IN_EFFECTS]
  - repeat_ct_24h [BUG_NOT_IN_EFFECTS]
  - maintain_bp_below_180_105_post_tpa [BUG_NOT_IN_EFFECTS]
  - early_mobilization [BUG_NOT_IN_EFFECTS]
  - groin_site_monitoring [BUG_NOT_IN_EFFECTS]
  - reduce_bp_to_below_185_110_before_tpa [BUG_NOT_IN_EFFECTS]
  - evaluate_for_hemorrhage [BUG_NOT_IN_EFFECTS]
  - give_alteplase_0.9mg_kg [BUG_NOT_IN_EFFECTS]
  - occupational_therapy [BUG_NOT_IN_EFFECTS]
  - hold_antiplatelet_anticoagulation_24h [BUG_NOT_IN_EFFECTS]
  - start_antiplatelet_after_24h_if_no_hemorrhage [BUG_NOT_IN_EFFECTS]
  - swallow_screen [BUG_NOT_IN_EFFECTS]
  - treat_if_bp_above_220_120 [BUG_NOT_IN_EFFECTS]
  - neurological_checks_q15min [BUG_NOT_IN_EFFECTS]
  - start_doac_preferred [BUG_NOT_IN_EFFECTS]
  - neurosurgery_consult_for_decompressive_craniectomy [BUG_NOT_IN_EFFECTS]
  - seizure_prophylaxis_consideration [BUG_NOT_IN_EFFECTS]
  - diabetes_management [BUG_NOT_IN_EFFECTS]
  - reverse_coagulopathy [BUG_NOT_IN_EFFECTS]
  - icu_management [BUG_NOT_IN_EFFECTS]
  - neurological_monitoring [BUG_NOT_IN_EFFECTS]
  - review_anticoagulation_status [BUG_NOT_IN_EFFECTS]
  - evaluate_for_edema [BUG_NOT_IN_EFFECTS]
  - early_rehabilitation_assessment [BUG_NOT_IN_EFFECTS]
  - dvt_prophylaxis [BUG_NOT_IN_EFFECTS]
  - neurosurgery_consult [BUG_NOT_IN_EFFECTS]
  - monitor_bp_q15min_x2h_then_q30min_x6h [BUG_NOT_IN_EFFECTS]
  - surgical_planning [BUG_NOT_IN_EFFECTS]
  - perform_cea_within_2_weeks [BUG_NOT_IN_EFFECTS]
  - review_inclusion_criteria [BUG_NOT_IN_EFFECTS]
  - dvt_prophylaxis_mechanical [BUG_NOT_IN_EFFECTS]
  - evd_for_hydrocephalus [BUG_NOT_IN_EFFECTS]
  - smoking_cessation [BUG_NOT_IN_EFFECTS]
  - icp_monitoring_if_indicated [BUG_NOT_IN_EFFECTS]
  - type_and_screen [BUG_NOT_IN_EFFECTS]

### anaphylaxis_management
  - refer_to_allergist [BUG_NOT_IN_EFFECTS]

### apa_agitation_management
  - reassess_need_q1h [BUG_NOT_IN_EFFECTS]
  - stop_offending_agent [BUG_NOT_IN_EFFECTS]

### gina_asthma_exacerbation
  - reassess_after_treatment [BUG_NOT_IN_EFFECTS]

### idsa_meningitis
  - perform_lumbar_puncture [BUG_NOT_IN_EFFECTS]

### kdigo_aki_full
  - initiate_rrt_immediately [BUG_NOT_IN_EFFECTS]
  - plan_rrt_modality [BUG_NOT_IN_EFFECTS]
  - use_iso_osmolar_contrast [BUG_NOT_IN_EFFECTS]
  - use_low_or_iso_osmolar_contrast [BUG_NOT_IN_EFFECTS]
  - urgent_nephrology_consult [BUG_NOT_IN_EFFECTS]
  - plan_follow_up_creatinine [BUG_NOT_IN_EFFECTS]
  - standard_contrast_protocol [BUG_NOT_IN_EFFECTS]
  - treat_hyperkalemia_temporizing [BUG_NOT_IN_EFFECTS]
  - vascular_access_placement [BUG_NOT_IN_EFFECTS]
  - post_procedure_creatinine_48h [BUG_NOT_IN_EFFECTS]

### kdigo_contrast_aki
  - schedule_followup [BUG_NOT_IN_EFFECTS]
  - serial_scr_monitoring [BUG_NOT_IN_EFFECTS]
  - standard_contrast_administration [BUG_NOT_IN_EFFECTS]
  - use_minimum_contrast_volume [BUG_NOT_IN_EFFECTS]

### status_epilepticus
  - reassess_neurological_status [BUG_NOT_IN_EFFECTS]

### toxicology_management
  - identify_toxin_class [BUG_NOT_IN_EFFECTS]
  - review_ecg_for_toxicity [BUG_NOT_IN_EFFECTS]