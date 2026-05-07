================================================================================
FULL NORMALIZER GAP QUANTIFICATION
================================================================================

## Overview
  Episodes analyzed: 9674
  Total expected actions: 137924
  Total omitted actions: 58667
  Near-miss omissions (sim>=0.5): 10653
  Near-miss rate: 18.2%
  Episodes with near-miss: 4681/9674 (48.4%)
  Unique (performed, expected) pairs: 356

## Similarity Tier Distribution
  Tier          Pairs   Episodes  % of near-miss
  ------------ ------ ---------- ---------------
  0.90+             6        243            2.3%
  0.80-0.90        29        847            8.0%
  0.70-0.80        51       1274           12.0%
  0.60-0.70        94       2855           26.8%
  0.50-0.60       176       5434           51.0%

## Projected Impact by Fix Threshold
   Threshold  Pairs   Remove   Remain  Rate Before  Rate After  Reduction
  ---------- ------ -------- -------- ------------ ----------- ----------
         0.9      6      243    58424       42.5%      42.4%       0.4%
         0.8     35     1090    57577       42.5%      41.8%       1.9%
         0.7     86     2364    56303       42.5%      40.8%       4.0%
         0.6    180     5219    53448       42.5%      38.8%       8.9%
         0.5    356    10653    48014       42.5%      34.8%      18.2%

## Per-Model Breakdown
  Model           Episodes  Omissions  Near-miss  NM rate
  --------------- -------- ---------- ---------- --------
  gemma31b            1387       9425       1677    17.8%
  nemotron30b         1661      14565       2782    19.1%
  oss120b              891       4838        695    14.4%
  qwen27b             1983       9908       1461    14.7%
  qwen35b             1974       9064       2436    26.9%
  qwen397b             623       2752        258     9.4%
  qwen4b              1155       8115       1344    16.6%

## Top 50 Near-Miss Pairs (by episode count)
    # Performed                                     Expected                                        Sim  Count Models
  --- --------------------------------------------- --------------------------------------------- ----- ------ ---
    1 assess_inhaler_technique                      reassess_after_treatment                       0.58    552   3
    2 calculate_contrast_volume_limit               use_minimum_contrast_volume                    0.62    539   5
    3 calculate_contrast_volume_limit               use_lowest_contrast_volume                     0.63    359   5
    4 check_current_medications                     hold_nephrotoxic_medications                   0.60    279   2
    5 check_current_medications                     check_scr_at_48h                               0.54    269   4
    6 order_lab_coagulation                         give_anticoagulation                           0.68    258   6
    7 give_hydrocortisone_iv                        give_systemic_corticosteroid                   0.56    251   3
    8 give_hydrocortisone_iv                        give_systemic_corticosteroid_iv                0.60    244   3
    9 consult_nephrology_if_needed                  consult_nephrology                             0.78    231   4
   10 monitor_creatinine_q6h                        monitor_creatinine_daily                       0.83    216   3
   11 monitor_creatinine_q6h                        monitor_acid_base                              0.56    207   3
   12 monitor_creatinine_q6h                        monitor_potassium                              0.51    207   3
   13 monitor_creatinine_q6h                        monitor_creatinine_q12h                        0.93    207   3
   14 order_lab_creatinine                          consider_alternative_imaging                   0.50    202   1
   15 check_scr_at_72h                              monitor_scr_48_72h                             0.53    196   2
   16 consult_nephrology_if_needed                  urgent_nephrology_consult                      0.57    178   5
   17 give_crystalloid_fluid                        give_calcium_gluconate                         0.55    174   5
   18 apply_continuous_monitoring                   give_continuous_salbutamol_nebulized           0.51    156   1
   19 prescribe_oral_corticosteroid_5_day           give_systemic_corticosteroid                   0.57    141   1
   20 prescribe_oral_corticosteroid_5_day           give_systemic_corticosteroid_iv                0.58    139   1
   21 give_ketamine_for_induction                   determine_disposition                          0.50    125   1
   22 discontinue_nephrotoxic_agents                discontinue_nephrotoxins                       0.89    125   4
   23 add_diuretic_for_congestion                   evaluate_diastolic_function                    0.52    119   6
   24 give_epinephrine_nebulized                    give_epinephrine_im                            0.80    111   2
   25 consult_nephrology                            nephrology_consult                             0.56     99   4
   26 consider_ace_or_arb_or_arni                   initiate_ace_or_arb_or_arni                    0.78     97   6
   27 assess_vital_signs                            reassess_airway                                0.55     95   3
   28 post_procedure_creatinine_48_72h              monitor_creatinine_daily                       0.57     95   1
   29 consider_beta_blocker                         initiate_beta_blocker                          0.71     94   5
   30 post_procedure_creatinine_48_72h              monitor_creatinine_q12h                        0.66     92   1
   31 give_epinephrine_1mg_iv_immediately           resume_cpr_immediately                         0.56     91   7
   32 check_scr_at_72h                              check_scr_at_48h                               0.88     91   1
   33 calculate_egfr                                give_calcium_gluconate                         0.50     90   4
   34 order_lab_urine_culture                       monitor_urine_output                           0.56     88   1
   35 continue_iv_hydration_if_needed               iv_hydration_pre_contrast                      0.50     87   1
   36 admit_to_ward                                 admit_to_icu                                   0.72     83   2
   37 order_lab_blood_culture                       order_lab_blood_gas                            0.76     74   5
   38 check_current_medications                     evaluate_rrt_indications                       0.61     69   4
   39 admit_to_observation                          admit_to_cardiology_service                    0.64     67   2
   40 assess_hemodynamic_profile                    invasive_hemodynamic_monitoring                0.63     59   7
   41 monitor_urine_output                          monitor_scr_48_72h                             0.53     59   1
   42 consider_combination_diuretics                manage_comorbidities                           0.52     58   5
   43 give_respiratory_fluoroquinolone              give_beta_lactam_plus_fluoroquinolone          0.67     58   4
   44 give_epinephrine_repeat_3_5min                give_epinephrine_1mg_iv_immediately            0.61     57   4
   45 give_medication_furosemide                    give_insulin_dextrose                          0.55     57   3
   46 order_csf_culture                             order_csf_analysis                             0.63     56   1
   47 order_type_and_crossmatch                     type_and_crossmatch                            0.86     54   2
   48 give_nebulized_epinephrine                    prescribe_epinephrine_autoinjector             0.50     53   2
   49 order_imaging_ct_head                         order_stat_ct_head                             0.77     50   6
   50 give_iv_diuretic                              iv_diuretics                                   0.79     49   7

## High-Confidence Aliases to Add (sim >= 0.7, 86 pairs)
  "consult_nephrology_if_needed" → "consult_nephrology"  (sim=0.78, impact=231 episodes)
  "monitor_creatinine_q6h" → "monitor_creatinine_daily"  (sim=0.83, impact=216 episodes)
  "monitor_creatinine_q6h" → "monitor_creatinine_q12h"  (sim=0.93, impact=207 episodes)
  "discontinue_nephrotoxic_agents" → "discontinue_nephrotoxins"  (sim=0.89, impact=125 episodes)
  "give_epinephrine_nebulized" → "give_epinephrine_im"  (sim=0.80, impact=111 episodes)
  "consider_ace_or_arb_or_arni" → "initiate_ace_or_arb_or_arni"  (sim=0.78, impact=97 episodes)
  "consider_beta_blocker" → "initiate_beta_blocker"  (sim=0.71, impact=94 episodes)
  "check_scr_at_72h" → "check_scr_at_48h"  (sim=0.88, impact=91 episodes)
  "admit_to_ward" → "admit_to_icu"  (sim=0.72, impact=83 episodes)
  "order_lab_blood_culture" → "order_lab_blood_gas"  (sim=0.76, impact=74 episodes)
  "order_type_and_crossmatch" → "type_and_crossmatch"  (sim=0.86, impact=54 episodes)
  "order_imaging_ct_head" → "order_stat_ct_head"  (sim=0.77, impact=50 episodes)
  "give_iv_diuretic" → "iv_diuretics"  (sim=0.79, impact=49 episodes)
  "consult_cardiology" → "consult_endocrinology"  (sim=0.77, impact=48 episodes)
  "order_lab_inr" → "order_lab_free_t4"  (sim=0.73, impact=44 episodes)
  "order_lab_inr" → "order_lab_free_t3"  (sim=0.73, impact=44 episodes)
  "give_bronchodilator" → "give_short_acting_bronchodilator"  (sim=0.74, impact=43 episodes)
  "give_aspirin_loading" → "give_aspirin"  (sim=0.75, impact=31 episodes)
  "give_crystalloid_fluid" → "give_crystalloid_30ml_kg"  (sim=0.78, impact=28 episodes)
  "monitor_potassium" → "monitor_potassium_q4h"  (sim=0.90, impact=26 episodes)
  "monitor_urine_output" → "monitor_urine_output_target_200ml_h"  (sim=0.73, impact=26 episodes)
  "review_nephrotoxic_medications" → "review_medications"  (sim=0.75, impact=26 episodes)
  "give_iv_diuretic" → "give_iv_furosemide"  (sim=0.71, impact=25 episodes)
  "optimize_fluid_status" → "optimize_volume_status"  (sim=0.84, impact=24 episodes)
  "establish_iv_access" → "establish_large_bore_iv_access"  (sim=0.78, impact=24 episodes)
  "give_iv_crystalloid_bolus" → "give_crystalloid_fluid"  (sim=0.81, impact=23 episodes)
  "give_epinephrine_repeat_3_5min" → "give_epinephrine_1mg_iv"  (sim=0.72, impact=23 episodes)
  "avoid_additional_nephrotoxins" → "avoid_nephrotoxins"  (sim=0.77, impact=22 episodes)
  "give_anticoagulation" → "initiate_anticoagulation"  (sim=0.82, impact=21 episodes)
  "monitor_potassium" → "monitor_potassium_q6h"  (sim=0.90, impact=18 episodes)
  "order_serial_ecg" → "serial_ecg"  (sim=0.77, impact=17 episodes)
  "order_lab_glucose" → "order_lab_lactate"  (sim=0.77, impact=17 episodes)
  "continuous_cardiac_monitoring" → "continuous_fetal_monitoring"  (sim=0.82, impact=16 episodes)
  "observe_minimum_24_hours" → "observe_minimum_4_hours"  (sim=0.98, impact=15 episodes)
  "order_lab_anion_gap" → "order_lab_abg"  (sim=0.75, impact=14 episodes)
  "admit_to_icu_or_stroke_unit" → "admit_to_stroke_unit"  (sim=0.85, impact=13 episodes)
  "order_lab_bmp" → "order_lab_crp"  (sim=0.85, impact=12 episodes)
  "use_low_osmolar_contrast" → "use_lowest_contrast_dose"  (sim=0.71, impact=12 episodes)
  "review_nephrotoxic_medications" → "hold_nephrotoxic_medications"  (sim=0.83, impact=12 episodes)
  "assess_aki_risk_factors" → "assess_aki_risk"  (sim=0.79, impact=12 episodes)