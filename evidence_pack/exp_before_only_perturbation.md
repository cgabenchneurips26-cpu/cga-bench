# BEFORE-Only Perturbation Experiment

## Summary

- Graphs with BEFORE constraints: **14**
- Eligible pairs (both actions mandatory): **46**
- Pairs generated: **17**
- Orthogonal pairs (BEFORE-only violation): **17**

## Detection Rates (orthogonal pairs only)

| Evaluator | Detection Rate |
|-----------|---------------|
| DxEM | 0.0000 |
| AC-Proxy | 0.0000 |
| MAB-Proxy | 0.0000 |
| C2>=0.7 | 0.0000 |
| CGA-Bench | 1.0000 |

## Interpretation

Expected result: AC-Proxy, MAB-Proxy, and C2 should show **0.0** detection
(action multiset unchanged by timestamp swap).  CGA-Bench should show **1.0**
(BEFORE violation detected via conformance distance).

## Sample Pairs

| Graph | Prior | Dependent | d_G base | d_G perturbed | Orthogonal |
|-------|-------|-----------|----------|---------------|------------|
| aabb_transfusion | order_cbc | apply_restrictive_threshold | 0.0 | 10.0 | Yes |
| aba_burn_resuscitation | estimate_tbsa | calculate_parkland_formula | 0.0 | 20.0 | Yes |
| aba_burn_resuscitation | obtain_patient_weight | calculate_parkland_formula | 0.0 | 10.0 | Yes |
| aba_burn_resuscitation | establish_iv_access | start_lactated_ringers | 0.0 | 10.0 | Yes |
| anaphylaxis_management | establish_iv_access | give_normal_saline_bolus | 0.0 | 10.0 | Yes |
| anaphylaxis_management | observe_minimum_4_hours | prescribe_epinephrine_autoinjector | 0.0 | 10.0 | Yes |
| apa_agitation_management | attempt_verbal_deescalation | apply_least_restrictive_restraint | 0.0 | 10.0 | Yes |
| atrial_fibrillation | obtain_12_lead_ecg | give_rate_control | 0.0 | 10.0 | Yes |
| cap_pneumonia | order_lab_blood_culture | give_beta_lactam_plus_macrolide | 0.0 | 20.0 | Yes |
| idsa_meningitis | order_lab_blood_culture | give_empiric_antibiotics | 0.0 | 10.0 | Yes |
| kdigo_contrast_aki | check_baseline_egfr | use_minimum_contrast_volume | 0.0 | 30.0 | Yes |
| kdigo_contrast_aki | iv_hydration_pre_contrast | use_minimum_contrast_volume | 0.0 | 30.0 | Yes |
| kdigo_contrast_aki | iv_hydration_pre_contrast | iv_hydration_post_contrast | 0.0 | 20.0 | Yes |
| kdigo_contrast_aki | document_stable_egfr | provide_discharge_instructions | 0.0 | 10.0 | Yes |
| status_epilepticus | give_benzodiazepine_first_line | give_second_line_antiepileptic | 0.0 | 10.0 | Yes |
| status_epilepticus | give_benzodiazepine_first_line | initiate_continuous_iv_anesthetic | 0.0 | 30.0 | Yes |
| status_epilepticus | give_second_line_antiepileptic | initiate_continuous_iv_anesthetic | 0.0 | 10.0 | Yes |
