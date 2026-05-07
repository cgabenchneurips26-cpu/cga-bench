# ILP vs Tiered d_G Solver Comparison

## Summary

| Metric | Value |
|--------|-------|
| Episodes processed | 108 |
| Episodes skipped | 72 |
| Equal (\|d_ILP − d_tiered\| < 1e-6) | 67 (62.0%) |
| ILP strictly better (joint repair) | 33 (30.6%) |
| Tiered strictly better (bug indicator) | 8 (7.4%) |
| Spearman ρ (d_ILP vs d_tiered) | 0.965517 |
| Spearman p-value | 8.9282e-64 |
| Mean d_tiered | 4400.4167 |
| Mean d_ILP | 1897.0833 |
| Mean diff (ILP − tiered) | -2503.3333 |

## Interpretation

- **n_tiered_better = 0**: ILP is never worse than tiered (correctness check).
- **n_ilp_better > 0**: ILP found joint repairs that tiered solver missed.
- **Spearman ρ ≈ 1.0**: Both solvers produce consistent relative rankings.

## Diverged Episodes (41 total)

| source_file | scenario | model | d_tiered | d_ilp | diff |
|-------------|----------|-------|----------|-------|------|
| af_new_onset_basic_oss120b_r1_20260331_215332.json | af_new_onset_basic | oss120b | 4535.00 | 9525.00 | +4990.00 |
| contrast_aki_prevention_basic_oss120b_r0_20260331_214423.json | contrast_aki_prevention_basic | oss120b | 2835.00 | 85.00 | -2750.00 |
| contrast_aki_prevention_basic_oss120b_r1_20260331_214532.json | contrast_aki_prevention_basic | oss120b | 2835.00 | 85.00 | -2750.00 |
| contrast_aki_prevention_basic_oss120b_r2_20260331_214642.json | contrast_aki_prevention_basic | oss120b | 2835.00 | 85.00 | -2750.00 |
| dka_hypokalemia_trap_oss120b_r0_20260331_212909.json | dka_hypokalemia_trap | oss120b | 28640.00 | 9615.00 | -19025.00 |
| dka_hypokalemia_trap_oss120b_r1_20260331_213214.json | dka_hypokalemia_trap | oss120b | 25640.00 | 9115.00 | -16525.00 |
| dka_hypokalemia_trap_oss120b_r2_20260331_213513.json | dka_hypokalemia_trap | oss120b | 28640.00 | 10615.00 | -18025.00 |
| dka_moderate_basic_oss120b_r0_20260331_212035.json | dka_moderate_basic | oss120b | 30135.00 | 9610.00 | -20525.00 |
| dka_moderate_basic_oss120b_r1_20260331_212322.json | dka_moderate_basic | oss120b | 32140.00 | 12115.00 | -20025.00 |
| dka_moderate_basic_oss120b_r2_20260331_212546.json | dka_moderate_basic | oss120b | 35635.00 | 14610.00 | -21025.00 |
| af_new_onset_basic_qwen27b_r2_20260331_221055.json | af_new_onset_basic | qwen27b | 4790.00 | 10030.00 | +5240.00 |
| contrast_aki_prevention_basic_qwen27b_r0_20260331_215529.json | contrast_aki_prevention_basic | qwen27b | 8085.00 | 5585.00 | -2500.00 |
| contrast_aki_prevention_basic_qwen27b_r1_20260331_215722.json | contrast_aki_prevention_basic | qwen27b | 8335.00 | 5585.00 | -2750.00 |
| contrast_aki_prevention_basic_qwen27b_r2_20260331_215911.json | contrast_aki_prevention_basic | qwen27b | 11585.00 | 9085.00 | -2500.00 |
| dka_hypokalemia_trap_qwen27b_r0_20260331_213809.json | dka_hypokalemia_trap | qwen27b | 9155.00 | 1120.00 | -8035.00 |
| dka_hypokalemia_trap_qwen27b_r1_20260331_214110.json | dka_hypokalemia_trap | qwen27b | 9155.00 | 1120.00 | -8035.00 |
| dka_hypokalemia_trap_qwen27b_r2_20260331_214412.json | dka_hypokalemia_trap | qwen27b | 9155.00 | 1120.00 | -8035.00 |
| dka_moderate_basic_qwen27b_r0_20260331_212902.json | dka_moderate_basic | qwen27b | 9155.00 | 1120.00 | -8035.00 |
| dka_moderate_basic_qwen27b_r1_20260331_213206.json | dka_moderate_basic | qwen27b | 9155.00 | 1120.00 | -8035.00 |
| dka_moderate_basic_qwen27b_r2_20260331_213509.json | dka_moderate_basic | qwen27b | 9155.00 | 1120.00 | -8035.00 |
| af_new_onset_basic_qwen35b_r0_20260331_212954.json | af_new_onset_basic | qwen35b | 2290.00 | 4530.00 | +2240.00 |
| af_new_onset_basic_qwen35b_r1_20260331_213113.json | af_new_onset_basic | qwen35b | 2040.00 | 5030.00 | +2990.00 |
| af_new_onset_basic_qwen35b_r2_20260331_213253.json | af_new_onset_basic | qwen35b | 2290.00 | 5030.00 | +2740.00 |
| contrast_aki_prevention_basic_qwen35b_r0_20260331_212523.json | contrast_aki_prevention_basic | qwen35b | 2835.00 | 85.00 | -2750.00 |
| contrast_aki_prevention_basic_qwen35b_r1_20260331_212603.json | contrast_aki_prevention_basic | qwen35b | 2835.00 | 85.00 | -2750.00 |
| contrast_aki_prevention_basic_qwen35b_r2_20260331_212646.json | contrast_aki_prevention_basic | qwen35b | 2335.00 | 85.00 | -2250.00 |
| dka_hypokalemia_trap_qwen35b_r0_20260331_211854.json | dka_hypokalemia_trap | qwen35b | 9155.00 | 1120.00 | -8035.00 |
| dka_hypokalemia_trap_qwen35b_r1_20260331_211955.json | dka_hypokalemia_trap | qwen35b | 9155.00 | 1120.00 | -8035.00 |
| dka_hypokalemia_trap_qwen35b_r2_20260331_212101.json | dka_hypokalemia_trap | qwen35b | 9155.00 | 1120.00 | -8035.00 |
| dka_moderate_basic_qwen35b_r0_20260331_211553.json | dka_moderate_basic | qwen35b | 9155.00 | 1120.00 | -8035.00 |
| dka_moderate_basic_qwen35b_r1_20260331_211652.json | dka_moderate_basic | qwen35b | 9155.00 | 1120.00 | -8035.00 |
| dka_moderate_basic_qwen35b_r2_20260331_211752.json | dka_moderate_basic | qwen35b | 9155.00 | 1120.00 | -8035.00 |
| af_new_onset_basic_qwen4b_r0_20260331_213755.json | af_new_onset_basic | qwen4b | 1540.00 | 3030.00 | +1490.00 |
| af_new_onset_basic_qwen4b_r1_20260331_213835.json | af_new_onset_basic | qwen4b | 1540.00 | 3030.00 | +1490.00 |
| af_new_onset_basic_qwen4b_r2_20260331_213914.json | af_new_onset_basic | qwen4b | 1540.00 | 3030.00 | +1490.00 |
| dka_hypokalemia_trap_qwen4b_r0_20260331_212239.json | dka_hypokalemia_trap | qwen4b | 20150.00 | 10615.00 | -9535.00 |
| dka_hypokalemia_trap_qwen4b_r1_20260331_212417.json | dka_hypokalemia_trap | qwen4b | 20150.00 | 10115.00 | -10035.00 |
| dka_hypokalemia_trap_qwen4b_r2_20260331_212550.json | dka_hypokalemia_trap | qwen4b | 21650.00 | 10615.00 | -11035.00 |
| dka_moderate_basic_qwen4b_r0_20260331_211740.json | dka_moderate_basic | qwen4b | 17650.00 | 8615.00 | -9035.00 |
| dka_moderate_basic_qwen4b_r1_20260331_211920.json | dka_moderate_basic | qwen4b | 17650.00 | 8615.00 | -9035.00 |
| dka_moderate_basic_qwen4b_r2_20260331_212100.json | dka_moderate_basic | qwen4b | 17650.00 | 8615.00 | -9035.00 |
