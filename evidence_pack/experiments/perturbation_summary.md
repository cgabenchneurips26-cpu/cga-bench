# Experiment A: Outcome-Preserving Perturbation Results

## Key Finding

Task-completion metrics remain PASS for all perturbations (except P3 omission),
while CGA detects process defects across all 5 perturbation types.

## Sensitivity Metrics

- **Continuous detection** (CGA Δ < 0 among TC PASS): **81.8%** (27/33)
- **Dimension-level detection** (target sub-score drops): **80.0%** (32/40)
- Binary detection (CGA < 70% threshold): 51.5% (17/33)

## Per-Perturbation Type Detection

| Perturbation | Target Dim | TC PASS | CGA Δ (mean) | Target Δ (mean) | Continuous Det. | Dim Det. |
|-------------|-----------|---------|-------------|----------------|----------------|---------|
| P1_delay | timing_compliance | 100% | -0.322 | -0.322 | 88% | 88% |
| P2_swap_order | sequence_integrity | 100% | -0.500 | -0.375 | 75% | 50% |
| P3_omission | mandatory_completion | 12% | -0.211 | -0.166 | 0% | 88% |
| P4_extra_action | path_selection | 100% | -0.104 | -0.104 | 75% | 75% |
| P5_contraindicated | forbidden_avoidance | 100% | -1.000 | -1.000 | 100% | 100% |

## Full Results Table

| Scenario | Perturbation | TC | CGA | Δ CGA | Target Dim | Δ Target |
|----------|-------------|----|----|-------|-----------|---------|
| septic_shock_basic | Baseline | PASS | 100.0% | — | — | — |
| septic_shock_basic | P1_delay | PASS | 85.7% | -14.3% | timing_compliance | -0.143 |
| septic_shock_basic | P2_swap_order | PASS | 50.0% | -50.0% | sequence_integrity | -0.500 |
| septic_shock_basic | P3_omission | FAIL | 85.7% | -14.3% | mandatory_completion | -0.143 |
| septic_shock_basic | P4_extra_action | PASS | 87.5% | -12.5% | path_selection | -0.125 |
| septic_shock_basic | P5_contraindicated | PASS | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| septic_shock_penicillin_allergy | Baseline | PASS | 100.0% | — | — | — |
| septic_shock_penicillin_allergy | P1_delay | PASS | 85.7% | -14.3% | timing_compliance | -0.143 |
| septic_shock_penicillin_allergy | P2_swap_order | PASS | 50.0% | -50.0% | sequence_integrity | -0.500 |
| septic_shock_penicillin_allergy | P3_omission | FAIL | 50.0% | -50.0% | mandatory_completion | -0.143 |
| septic_shock_penicillin_allergy | P4_extra_action | PASS | 87.5% | -12.5% | path_selection | -0.125 |
| septic_shock_penicillin_allergy | P5_contraindicated | PASS | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| stemi_inferior_rv_trap | Baseline | PASS | 100.0% | — | — | — |
| stemi_inferior_rv_trap | P1_delay | PASS | 50.0% | -50.0% | timing_compliance | -0.500 |
| stemi_inferior_rv_trap | P2_swap_order | PASS | 50.0% | -50.0% | sequence_integrity | +0.000 |
| stemi_inferior_rv_trap | P3_omission | PASS | 100.0% | +0.0% | mandatory_completion | +0.000 |
| stemi_inferior_rv_trap | P4_extra_action | PASS | 75.0% | -25.0% | path_selection | -0.250 |
| stemi_inferior_rv_trap | P5_contraindicated | PASS | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| dka_moderate_basic | Baseline | PASS | 100.0% | — | — | — |
| dka_moderate_basic | P1_delay | PASS | 85.7% | -14.3% | timing_compliance | -0.143 |
| dka_moderate_basic | P2_swap_order | PASS | 0.0% | -100.0% | sequence_integrity | -1.000 |
| dka_moderate_basic | P3_omission | FAIL | 87.5% | -12.5% | mandatory_completion | -0.125 |
| dka_moderate_basic | P4_extra_action | PASS | 88.9% | -11.1% | path_selection | -0.111 |
| dka_moderate_basic | P5_contraindicated | PASS | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| dka_hypokalemia_trap | Baseline | PASS | 100.0% | — | — | — |
| dka_hypokalemia_trap | P1_delay | PASS | 85.7% | -14.3% | timing_compliance | -0.143 |
| dka_hypokalemia_trap | P2_swap_order | PASS | 0.0% | -100.0% | sequence_integrity | -1.000 |
| dka_hypokalemia_trap | P3_omission | FAIL | 87.5% | -12.5% | mandatory_completion | -0.125 |
| dka_hypokalemia_trap | P4_extra_action | PASS | 88.9% | -11.1% | path_selection | -0.111 |
| dka_hypokalemia_trap | P5_contraindicated | PASS | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| stroke_tpa_eligible | Baseline | PASS | 100.0% | — | — | — |
| stroke_tpa_eligible | P1_delay | PASS | 50.0% | -50.0% | timing_compliance | -0.500 |
| stroke_tpa_eligible | P2_swap_order | PASS | 50.0% | -50.0% | sequence_integrity | +0.000 |
| stroke_tpa_eligible | P3_omission | FAIL | 87.5% | -12.5% | mandatory_completion | -0.125 |
| stroke_tpa_eligible | P4_extra_action | PASS | 88.9% | -11.1% | path_selection | -0.111 |
| stroke_tpa_eligible | P5_contraindicated | PASS | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| contrast_aki_prevention_basic | Baseline | PASS | 100.0% | — | — | — |
| contrast_aki_prevention_basic | P1_delay | PASS | 100.0% | +0.0% | timing_compliance | +0.000 |
| contrast_aki_prevention_basic | P2_swap_order | PASS | 100.0% | +0.0% | sequence_integrity | +0.000 |
| contrast_aki_prevention_basic | P3_omission | FAIL | 66.7% | -33.3% | mandatory_completion | -0.333 |
| contrast_aki_prevention_basic | P4_extra_action | PASS | 100.0% | +0.0% | path_selection | +0.000 |
| contrast_aki_prevention_basic | P5_contraindicated | PASS | 0.0% | -100.0% | forbidden_avoidance | -1.000 |
| aki_stage1_basic | Baseline | PASS | 100.0% | — | — | — |
| aki_stage1_basic | P1_delay | PASS | 0.0% | -100.0% | timing_compliance | -1.000 |
| aki_stage1_basic | P2_swap_order | PASS | 100.0% | +0.0% | sequence_integrity | +0.000 |
| aki_stage1_basic | P3_omission | FAIL | 66.7% | -33.3% | mandatory_completion | -0.333 |
| aki_stage1_basic | P4_extra_action | PASS | 100.0% | +0.0% | path_selection | +0.000 |
| aki_stage1_basic | P5_contraindicated | PASS | 0.0% | -100.0% | forbidden_avoidance | -1.000 |