================================================================================
NORMALIZER GAP v2: POST-NORMALIZATION RESIDUAL
================================================================================

## Normalization Impact
  Total expected actions: 140293
  Raw omissions (before normalizer): 59820
  Norm omissions (after normalizer): 54050
  Resolved by normalizer: 5770
  Raw omission rate: 42.6%
  Norm omission rate: 38.5%
  Reduction: 4.1% (5770 actions)

## Residual Near-Misses (post-normalization, sim>=0.5)
  Unique pairs: 260
  Total episode-actions: 6883
  Residual NM rate: 12.7%

  Similarity tier distribution:
    0.90+: 0 episode-actions
    0.80-0.90: 251 episode-actions
    0.70-0.80: 359 episode-actions
    0.60-0.70: 1929 episode-actions
    0.50-0.60: 4344 episode-actions

## Per-Model Comparison (Raw vs Normalized Omissions)
  Model           Episodes   Raw Om  Norm Om  Resolved  Raw Rate  Norm Rate
  --------------- -------- -------- -------- --------- --------- ----------
  gemma31b            1413     9573     8436      1137                     
  nemotron30b         1722    14887    13683      1204                     
  oss120b              919     5193     4664       529                     
  qwen27b             2003     9968     9228       740                     
  qwen35b             1988     9129     8077      1052                     
  qwen397b             631     2847     2687       160                     
  qwen4b              1165     8223     7275       948                     

## Top 50 Residual Near-Miss Pairs (THESE are the real normalizer gaps)
    # Performed (normalized)                        Expected (normalized)                           Sim  Count
  --- --------------------------------------------- --------------------------------------------- ----- ------
    1 consider_rrt_planning                         monitor_creatinine                             0.51    833
    2 assess_inhaler_technique                      reassess_after_treatment                       0.58    566
    3 check_current_medications                     hold_nephrotoxic_medications                   0.60    416
    4 order_lab_coagulation                         give_anticoagulation                           0.68    248
    5 assess_urine_output                           assess_serum_creatinine_at_48h                 0.53    218
    6 echocardiogram_post_mi                        serial_electrocardiogram                       0.56    209
    7 give_crystalloid_fluid                        give_calcium_gluconate                         0.55    174
    8 apply_continuous_monitoring                   give_continuous_salbutamol_nebulized           0.51    156
    9 monitor_serum_creatinine_48_72h               monitor_creatinine                             0.73    139
   10 give_ketamine_for_induction                   determine_disposition                          0.50    125
   11 initiate_mra                                  initiate_sglt2i                                0.67    123
   12 give_epinephrine_nebulized                    give_epinephrine_im                            0.80    123
   13 assess_vital_signs                            reassess_airway                                0.55     95
   14 give_epinephrine_1mg_iv_immediately           resume_cpr_immediately                         0.56     91
   15 order_lab_urine_culture                       assess_urine_output                            0.52     88
   16 continue_iv_hydration_if_needed               iv_hydration_pre_contrast                      0.50     87
   17 admit_to_ward                                 admit_to_icu                                   0.72     86
   18 check_current_medications                     evaluate_rrt_indications                       0.61     69
   19 admit_to_observation                          admit_to_cardiology_service                    0.64     67
   20 give_respiratory_fluoroquinolone              give_beta_lactam_plus_fluoroquinolone          0.67     67
   21 assess_hemodynamic_profile                    hemodynamic_monitoring                         0.58     60
   22 consider_combination_diuretics                manage_comorbidities                           0.52     58
   23 give_medication_furosemide                    give_insulin_dextrose                          0.55     57
   24 order_lab_csf_culture                         order_lab_csf_analysis                         0.70     56
   25 give_amiodarone_150mg_repeat                  give_epinephrine_1mg_iv_immediately            0.54     54
   26 order_lab_bmp                                 order_lab_free_t3                              0.67     54
   27 order_lab_bmp                                 order_lab_free_t4                              0.67     54
   28 give_nebulized_epinephrine                    prescribe_epinephrine_autoinjector             0.50     53
   29 request_consultation                          give_anticoagulation                           0.55     51
   30 give_octreotide                               give_crystalloid_bolus                         0.54     48
   31 assess_vital_signs                            reassess_neurological_status                   0.56     48
   32 assess_hydration_status                       assess_anion_gap_closure                       0.60     47
   33 initiate_beta_blocker                         initiate_sglt2i                                0.56     46
   34 admit_to_hospital                             admit_to_icu                                   0.69     42
   35 admit_to_icu_or_stroke_unit                   admit_to_icu                                   0.61     42
   36 consult_electrophysiology                     consult_endocrinology                          0.70     39
   37 assess_vital_signs                            reassess_perfusion                             0.56     39
   38 admit_to_observation                          admit_to_icu                                   0.62     36
   39 apply_continuous_monitoring                   initiate_continuous_iv_anesthetic              0.50     36
   40 give_normal_saline_bolus                      give_insulin_dextrose                          0.58     35
   41 assess_vital_signs                            assess_rrt_need                                0.61     34
   42 discontinue_nephrotoxic_agents                consult_nephrology                             0.54     33
   43 order_lab_bmp                                 order_lab_cyanide_level                        0.56     31
   44 iv_hydration_pre_contrast                     avoid_contrast                                 0.56     31
   45 arterial_line_monitoring                      determine_disposition                          0.53     31
   46 give_crystalloid_fluid                        give_crystalloid_30ml_kg                       0.78     31
   47 give_crystalloid_fluid                        give_aggressive_iv_fluid                       0.56     30
   48 order_lab_procalcitonin                       order_lab_abg                                  0.61     30
   49 give_acetaminophen                            give_epinephrine_im                            0.59     27
   50 optimize_volume_status                        optimize_hemodynamics                          0.56     27

## High-Confidence Residual Aliases (sim >= 0.7, 34 pairs)
  "monitor_serum_creatinine_48_72h" → "monitor_creatinine"  (sim=0.73, 139 episodes)
  "give_epinephrine_nebulized" → "give_epinephrine_im"  (sim=0.80, 123 episodes)
  "admit_to_ward" → "admit_to_icu"  (sim=0.72, 86 episodes)
  "give_crystalloid_fluid" → "give_crystalloid_30ml_kg"  (sim=0.78, 31 episodes)
  "order_lab_glucose" → "order_lab_lactate"  (sim=0.77, 17 episodes)
  "continuous_cardiac_monitoring" → "continuous_fetal_monitoring"  (sim=0.82, 16 episodes)
  "admit_to_icu_or_stroke_unit" → "admit_to_stroke_unit"  (sim=0.85, 13 episodes)
  "order_lab_bmp" → "order_lab_crp"  (sim=0.85, 12 episodes)
  "monitor_potassium" → "monitor_potassium_q2h"  (sim=0.90, 12 episodes)
  "order_imaging_chest_xray" → "order_imaging_cta"  (sim=0.83, 12 episodes)
  "give_iv_antihypertensive" → "give_iv_antihypertensive_to_target_185_110"  (sim=0.73, 12 episodes)
  "continuous_bp_monitoring" → "continuous_fetal_monitoring"  (sim=0.86, 10 episodes)
  "start_vasopressor_vasopressin" → "start_vasopressor_if_hypotensive"  (sim=0.72, 10 episodes)
  "order_lab_ketones" → "order_lab_ethanol_level"  (sim=0.70, 9 episodes)
  "order_lab_ketones" → "order_lab_troponin"  (sim=0.74, 9 episodes)
  "order_basic_metabolic_panel" → "assess_basic_metabolic_panel"  (sim=0.84, 9 episodes)
  "give_iv_antihypertensive" → "start_iv_antihypertensive"  (sim=0.82, 9 episodes)
  "hold_metformin_if_g3b" → "hold_metformin_48h_post"  (sim=0.73, 7 episodes)
  "order_lab_cbc" → "order_lab_bmp"  (sim=0.85, 7 episodes)
  "narrow_antibiotics_based_on_culture" → "narrow_antibiotics_when_culture_available"  (sim=0.76, 7 episodes)
  "assess_anticoagulation_need" → "give_anticoagulation"  (sim=0.72, 6 episodes)
  "order_lab_cbc" → "order_lab_abg"  (sim=0.85, 6 episodes)
  "order_lab_glucose" → "order_lab_cbc"  (sim=0.73, 6 episodes)
  "give_diuretic" → "give_cautious_diuretic"  (sim=0.74, 6 episodes)
  "give_diuretic" → "iv_diuretics"  (sim=0.88, 6 episodes)
  "assess_crt_indication" → "assess_current_medications"  (sim=0.81, 6 episodes)
  "admit_to_stroke_unit" → "admit_to_icu_or_stroke_unit"  (sim=0.85, 5 episodes)
  "order_imaging_lower_extremity_doppler" → "order_lab_lower_extremity_doppler"  (sim=0.89, 4 episodes)
  "order_lab_urine_culture" → "order_lab_blood_culture"  (sim=0.78, 3 episodes)
  "calculate_nihss_score" → "calculate_chadsvasc"  (sim=0.70, 3 episodes)