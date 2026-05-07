> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# FINAL NUMBERS — Clean Slate V2 (Rescored)

**Generated**: 2026-04-01 06:24:13 UTC
**Pipeline**: R1-R5 fixes applied, R6 re-scored 180 episodes
**Data**: `results/clean_slate_rescored/` (4 models x 15 scenarios x 3 runs)
**JSON source**: `evidence_pack/analysis/robustness_clean_v2.json`

---

## 1. Leave-One-Scenario-Out Friedman (Composite A, k=2)

| Dropped Scenario | Friedman p | Chi-sq |
|:---|---:|---:|
| adhf_warm_wet | 0.0000 *** | 23.49 |
| af_new_onset_basic | 0.0001 *** | 20.76 |
| aki_stage1_basic | 0.0000 *** | 23.78 |
| contrast_aki_prevention_basic | 0.0003 *** | 18.90 |
| copd_moderate_exacerbation | 0.0002 *** | 19.68 |
| dka_hypokalemia_trap | 0.0001 *** | 20.95 |
| dka_moderate_basic | 0.0002 *** | 19.49 |
| gi_bleeding_upper_basic | 0.0003 *** | 18.99 |
| hemorrhagic_stroke | 0.0003 *** | 18.99 |
| htn_emergency_basic | 0.0002 *** | 19.44 |
| pe_submassive_basic | 0.0003 *** | 18.90 |
| septic_shock_basic | 0.0002 *** | 19.68 |
| septic_shock_penicillin_allergy | 0.0002 *** | 19.68 |
| stemi_inferior_rv_trap | 0.0003 *** | 18.90 |
| stroke_tpa_eligible | 0.0001 *** | 21.54 |

- **p range**: [0.0000, 0.0003], median=0.0002
- **Significant at 0.05**: 15/15 (True)

## 2. Run-Level Consistency

### Composite A (per-run Friedman)

| Run | Chi-sq | p-value | Rank 1 |
|:---|---:|---:|:---|
| run_0 | 17.08 | 0.0007 * | oss120b |
| run_1 | 21.14 | 0.0001 * | oss120b |
| run_2 | 14.82 | 0.0020 * | oss120b |

### CGA Alone (per-run Friedman)

| Run | Chi-sq | p-value | Rank 1 |
|:---|---:|---:|:---|
| run_0 | 2.19 | 0.5343 ns | oss120b |
| run_1 | 5.03 | 0.1696 ns | oss120b |
| run_2 | 2.42 | 0.4903 ns | oss120b |

## 3. Holm-Bonferroni Correction (2-test family)

| Test | Raw p | Holm alpha | Significant |
|:---|---:|---:|:---:|
| Composite_A | 0.000081 | 0.0250 | Yes |
| CGA_alone | 0.204554 | 0.0500 | No |

- CGA alone Friedman: chi-sq=4.5882, p=0.204554
- Composite A Friedman: chi-sq=21.5414, p=8.1e-05

## 4. k-Space Sensitivity (Composite A = CGA * min(1, acts/(exp*k)))

| k | Friedman p | Rank 1 | Rank 2 | Rank 3 | Rank 4 |
|---:|---:|:---|:---|:---|:---|
| 0.5 | 0.2046 ns | oss120b(2.0) | qwen35b(2.5) | qwen27b(2.6) | qwen4b(2.9) |
| 0.6 | 0.2046 ns | oss120b(2.0) | qwen35b(2.5) | qwen27b(2.6) | qwen4b(2.9) |
| 0.7 | 0.0728 ns | oss120b(1.8) | qwen35b(2.5) | qwen27b(2.7) | qwen4b(3.0) |
| 0.8 | 0.0728 ns | oss120b(1.8) | qwen35b(2.5) | qwen27b(2.7) | qwen4b(3.0) |
| 0.9 | 0.0728 ns | oss120b(1.8) | qwen35b(2.5) | qwen27b(2.7) | qwen4b(3.0) |
| 1.0 | 0.0728 ns | oss120b(1.8) | qwen35b(2.5) | qwen27b(2.7) | qwen4b(3.0) |
| 1.1 | 0.0188 * | oss120b(1.8) | qwen35b(2.4) | qwen27b(2.6) | qwen4b(3.2) |
| 1.2 | 0.0188 * | oss120b(1.8) | qwen35b(2.4) | qwen27b(2.6) | qwen4b(3.2) |
| 1.3 | 0.0188 * | oss120b(1.8) | qwen35b(2.4) | qwen27b(2.6) | qwen4b(3.2) |
| 1.4 | 0.0094 * | oss120b(1.8) | qwen35b(2.3) | qwen27b(2.7) | qwen4b(3.2) |
| 1.5 | 0.0020 * | oss120b(1.6) | qwen35b(2.4) | qwen27b(2.9) | qwen4b(3.2) |
| 1.6 | 0.0007 * | oss120b(1.5) | qwen35b(2.4) | qwen27b(2.9) | qwen4b(3.2) |
| 1.7 | 0.0007 * | oss120b(1.5) | qwen35b(2.4) | qwen27b(2.9) | qwen4b(3.2) |
| 1.8 | 0.0012 * | oss120b(1.6) | qwen35b(2.3) | qwen27b(2.9) | qwen4b(3.2) |
| 1.9 | 0.0001 * | oss120b(1.4) | qwen35b(2.4) | qwen27b(2.9) | qwen4b(3.4) |
| 2.0 | 0.0001 * | oss120b(1.4) | qwen35b(2.4) | qwen27b(2.9) | qwen4b(3.3) |
| 2.1 | 0.0001 * | oss120b(1.4) | qwen35b(2.4) | qwen27b(2.9) | qwen4b(3.4) |
| 2.2 | 0.0001 * | oss120b(1.4) | qwen35b(2.4) | qwen27b(2.9) | qwen4b(3.4) |
| 2.3 | 0.0001 * | oss120b(1.4) | qwen35b(2.4) | qwen27b(2.9) | qwen4b(3.3) |
| 2.4 | 0.0001 * | oss120b(1.4) | qwen35b(2.4) | qwen27b(2.9) | qwen4b(3.3) |
| 2.5 | 0.0000 * | oss120b(1.4) | qwen35b(2.3) | qwen27b(3.0) | qwen4b(3.4) |
| 2.6 | 0.0000 * | oss120b(1.4) | qwen35b(2.2) | qwen27b(2.9) | qwen4b(3.5) |
| 2.7 | 0.0000 * | oss120b(1.4) | qwen35b(2.3) | qwen27b(2.9) | qwen4b(3.4) |
| 2.8 | 0.0000 * | oss120b(1.4) | qwen35b(2.2) | qwen27b(2.9) | qwen4b(3.5) |
| 2.9 | 0.0000 * | oss120b(1.4) | qwen35b(2.3) | qwen27b(2.9) | qwen4b(3.4) |
| 3.0 | 0.0000 * | oss120b(1.4) | qwen35b(2.3) | qwen27b(2.9) | qwen4b(3.4) |
| 3.1 | 0.0000 * | oss120b(1.4) | qwen35b(2.2) | qwen27b(2.9) | qwen4b(3.5) |
| 3.2 | 0.0000 * | oss120b(1.3) | qwen35b(2.3) | qwen27b(3.0) | qwen4b(3.4) |
| 3.3 | 0.0000 * | oss120b(1.3) | qwen35b(2.2) | qwen27b(3.0) | qwen4b(3.5) |
| 3.4 | 0.0000 * | oss120b(1.3) | qwen35b(2.3) | qwen27b(3.0) | qwen4b(3.4) |
| 3.5 | 0.0000 * | oss120b(1.3) | qwen35b(2.2) | qwen27b(3.0) | qwen4b(3.5) |
| 3.6 | 0.0000 * | oss120b(1.3) | qwen35b(2.3) | qwen27b(3.0) | qwen4b(3.4) |
| 3.7 | 0.0000 * | oss120b(1.3) | qwen35b(2.3) | qwen27b(3.0) | qwen4b(3.4) |
| 3.8 | 0.0000 * | oss120b(1.3) | qwen35b(2.2) | qwen27b(3.0) | qwen4b(3.5) |
| 3.9 | 0.0000 * | oss120b(1.3) | qwen35b(2.3) | qwen27b(3.0) | qwen4b(3.4) |
| 4.0 | 0.0000 * | oss120b(1.3) | qwen35b(2.3) | qwen27b(3.0) | qwen4b(3.4) |

- **Significant range**: k=1.1..4.0
- **Significant count**: 30/36

## 5. Bootstrap 95% Confidence Intervals (10,000 iterations)

| Model | CGA Mean | CGA 95% CI | Comp A Mean | Comp A 95% CI |
|:---|---:|:---|---:|:---|
| DeepSeek-R1-671B (oss-120b) | 0.5072 | [0.4439, 0.5685] | 0.5054 | [0.4405, 0.5682] |
| Qwen3.5-35B | 0.4389 | [0.3702, 0.5047] | 0.4150 | [0.3486, 0.4799] |
| Qwen3.5-27B | 0.4447 | [0.3735, 0.5122] | 0.3909 | [0.3200, 0.4622] |
| Qwen3-4B | 0.4316 | [0.3642, 0.4949] | 0.3175 | [0.2580, 0.3770] |

### CI Overlap Check

- oss120b vs qwen35b: OVERLAP (gap=-0.0394)
- qwen35b vs qwen27b: OVERLAP (gap=-0.1136)
- qwen27b vs qwen4b: OVERLAP (gap=-0.0570)

## 6. Sub-Construct C1-C5 Profiles

| Model | C1 Path | C2 Mandatory | C3 Forbidden | C4 Timing | C5 Sequence |
|:---|---:|---:|---:|---:|---:|
| DeepSeek-R1-671B (oss-120b) | 0.667 | 0.616 | 0.867 | 0.852 | 1.000 |
| Qwen3.5-27B | 0.754 | 0.563 | 0.867 | 0.902 | 1.000 |
| Qwen3.5-35B | 0.703 | 0.558 | 0.867 | 0.903 | 1.000 |
| Qwen3-4B | 0.789 | 0.524 | 0.867 | 0.927 | 1.000 |

### Per-Construct Friedman

| Construct | Chi-sq | p-value |
|:---|---:|---:|
| C1_path_selection | 5.16 | 0.1602 ns |
| C2_mandatory_completion | 9.55 | 0.0228 * |
| C3_forbidden_avoidance | 0.00 | 1.0000 ns |
| C4_timing_compliance | 5.13 | 0.1626 ns |
| C5_sequence_integrity | 0.00 | 1.0000 ns |

## 7. Point-Biserial Correlations

- **CGA vs Task Completion (C2≥0.7)**: r=0.70, p<10^-26 (N=180, 78 PASS / 102 FAIL)
- ~~CGA vs actions_count>0: r=0.0, p=1.0~~ — **DEGENERATE** (all 180 episodes have actions; constant binary)
- **Model Size vs CGA (Spearman)**: rho=0.8, p=0.2

### C2 Threshold Correlations (C2 >= t vs CGA)

| Threshold | r | p | N above | % above |
|---:|---:|---:|---:|---:|
| 0.5 | 0.6704 | 0.000000 * | 128 | 71.1% |
| 0.6 | 0.6725 | 0.000000 * | 106 | 58.9% |
| 0.7 | 0.6998 | 0.000000 * | 78 | 43.3% |
| 0.8 | 0.6822 | 0.000000 * | 69 | 38.3% |
| 0.9 | 0.2301 | 0.001890 * | 4 | 2.2% |

## 8. Q2 Re-Derivation: Optimal C2 Threshold

**Recommended threshold**: C2 >= 0.65
**Spread (max differentiation)**: 0.2222

| Threshold | oss120b | qwen27b | qwen35b | qwen4b | Spread | Overall |
|---:|---:|---:|---:|---:|---:|---:|
| 0.1 | 0.91 | 0.87 | 0.87 | 0.89 | 0.044 | 0.88 |
| 0.15 | 0.91 | 0.87 | 0.87 | 0.87 | 0.044 | 0.88 |
| 0.2 | 0.87 | 0.87 | 0.87 | 0.87 | 0.000 | 0.87 |
| 0.25 | 0.87 | 0.87 | 0.87 | 0.87 | 0.000 | 0.87 |
| 0.3 | 0.87 | 0.87 | 0.87 | 0.80 | 0.067 | 0.85 |
| 0.35 | 0.80 | 0.80 | 0.80 | 0.73 | 0.067 | 0.78 |
| 0.4 | 0.80 | 0.80 | 0.80 | 0.73 | 0.067 | 0.78 |
| 0.45 | 0.80 | 0.69 | 0.69 | 0.67 | 0.133 | 0.71 |
| 0.5 | 0.80 | 0.69 | 0.69 | 0.67 | 0.133 | 0.71 |
| 0.55 | 0.67 | 0.62 | 0.56 | 0.51 | 0.156 | 0.59 |
| 0.6 | 0.67 | 0.62 | 0.56 | 0.51 | 0.156 | 0.59 |
| 0.65 | 0.60 | 0.53 | 0.47 | 0.38 | 0.222 | 0.49 |
| 0.7 | 0.49 | 0.47 | 0.44 | 0.33 | 0.156 | 0.43 |
| 0.75 | 0.49 | 0.40 | 0.38 | 0.33 | 0.156 | 0.40 |
| 0.8 | 0.49 | 0.33 | 0.38 | 0.33 | 0.156 | 0.38 |
| 0.85 | 0.07 | 0.00 | 0.02 | 0.00 | 0.067 | 0.02 |
| 0.9 | 0.07 | 0.00 | 0.02 | 0.00 | 0.067 | 0.02 |
| 0.95 | 0.07 | 0.00 | 0.02 | 0.00 | 0.067 | 0.02 |
| 1.0 | 0.07 | 0.00 | 0.02 | 0.00 | 0.067 | 0.02 |

## 9. Violation Co-Occurrence Matrix

### Type Prevalence

- **omission**: 97.8% of episodes
- **commission**: 13.3% of episodes
- **timing**: 33.9% of episodes
- **sequence**: 0.0% of episodes
- **deviation**: 89.4% of episodes

### Conditional Probability P(col | row) %

| | omission | commission | timing | sequence | deviation |
|:---|---:|---:|---:|---:|---:|
| omission | 100 | 14 | 32 | 0 | 89 |
| commission | 100 | 100 | 50 | 0 | 100 |
| timing | 93 | 20 | 100 | 0 | 97 |
| sequence | 0 | 0 | 0 | 100 | 0 |
| deviation | 98 | 15 | 37 | 0 | 100 |

## 10. Sample Size Simulation (Power Analysis)

| N Scenarios | Power | Significant/2000 |
|---:|---:|---:|
| 5 | 0.540 | 1080 | 
| 7 | 0.836 | 1671 | <--
| 8 | 0.919 | 1838 | 
| 9 | 0.993 | 1985 | 
| 10 | 1.000 | 2000 | 
| 11 | 1.000 | 2000 | 
| 12 | 1.000 | 2000 | 
| 13 | 1.000 | 2000 | 
| 14 | 1.000 | 2000 | 
| 15 | 1.000 | 2000 | 

- **Minimum for 80% power**: 7 scenarios
- **Current**: 15 scenarios

## 11. Q4 Manual Verification: ADHF warm_wet / qwen4b / r0

- **Old CGA**: 1.0, **New CGA**: 0.4286
- **Performed actions**: 7
- **Expected actions**: 6

| Expected Action | Normalized | Matched |
|:---|:---|:---:|
| iv_diuretics | iv_diuretics | Y |
| fluid_restrict | fluid_restrict | N |
| daily_weights | daily_weights | N |
| monitor_urine_output | monitor_urine_output | N |
| monitor_electrolytes | monitor_electrolytes | N |
| continuous_monitoring | continuous_monitoring | N |

- **Manual C2**: 0.1667 (1/6)
- **Code C2**: 0.3333
- **Agreement**: NO (delta=0.1666)

## 12. Q2 Episodes (C2>=0.7 AND CGA<0.5)

- **Q2 count**: 7/180 (3.9%)
- **Inverse (CGA>=0.5 but C2<0.7)**: 22

### By Model

- **DeepSeek-R1-671B (oss-120b)**: 3
- **Qwen3.5-27B**: 3
- **Qwen3.5-35B**: 1

### By Scenario

- **dka_moderate_basic**: 3
- **pe_submassive_basic**: 3
- **htn_emergency_basic**: 1

### Episode List

| Scenario | Model | Run | C2 | CGA | Actions | Violations |
|:---|:---|---:|---:|---:|---:|---:|
| htn_emergency_basic | qwen35b | 1 | 0.833 | 0.467 | 15 | 8 |
| dka_moderate_basic | oss120b | 0 | 0.800 | 0.389 | 36 | 22 |
| dka_moderate_basic | oss120b | 1 | 0.800 | 0.438 | 32 | 18 |
| dka_moderate_basic | oss120b | 2 | 0.800 | 0.448 | 29 | 16 |
| pe_submassive_basic | qwen27b | 0 | 0.750 | 0.304 | 23 | 16 |
| pe_submassive_basic | qwen27b | 1 | 0.750 | 0.389 | 18 | 11 |
| pe_submassive_basic | qwen27b | 2 | 0.750 | 0.333 | 15 | 10 |

## Summary

| Check | Result | Verdict |
|:---|:---|:---:|
| LOSO 15/15 sig? | 15/15 | PASS |
| Run r0/r1/r2 consistency | p=0.0007/0.0001/0.0020 | PASS |
| Holm Composite A | p=8.1e-05 | PASS |
| k-space sig range | k=1.1..4.0 | PASS |
| Bootstrap CI separated | 0/3 pairs | PARTIAL |
| ADHF manual match | 1/6 (C2 agree: False) | CHECK |
| Q2 episodes | 7 | INFO |

---

*Generated by `scripts/experiments/robustness_analysis.py`*
*Source data: `results/clean_slate_rescored/` (180 episodes)*