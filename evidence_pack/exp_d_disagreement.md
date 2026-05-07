# EXP-D: Evaluation Disagreement Quantification

## 1. Pairwise Cohen's Kappa

| Pair | kappa | Agreement % | Asymmetry |
|------|-------|-------------|-----------|
| DxEM vs AC-Proxy | 0.0000 | 76.9% | 4409 |
| DxEM vs MAB-Proxy | 0.0000 | 52.7% | 9019 |
| DxEM vs C2 | 0.0000 | 27.8% | 13758 |
| DxEM vs ACov | 0.0000 | 76.9% | 4409 |
| DxEM vs CGA-Bench | 0.0000 | 44.6% | 10567 |
| AC-Proxy vs MAB-Proxy | 0.3999 | 70.9% | 4610 |
| AC-Proxy vs C2 | 0.1540 | 47.6% | 9349 |
| AC-Proxy vs ACov | 1.0000 | 100.0% | 0 |
| AC-Proxy vs CGA-Bench | -0.1578 | 38.7% | 6158 |
| MAB-Proxy vs C2 | -0.0312 | 47.2% | 4739 |
| MAB-Proxy vs ACov | 0.3999 | 70.9% | 4610 |
| MAB-Proxy vs CGA-Bench | -0.2017 | 39.6% | 1548 |
| C2 vs ACov | 0.1540 | 47.6% | 9349 |
| C2 vs CGA-Bench | 0.1484 | 59.5% | 3191 |
| ACov vs CGA-Bench | -0.1578 | 38.7% | 6158 |

## 2. Multi-Evaluator Agreement (Fleiss' Kappa)

**Overall**: 0.0540

### Per-Domain
| Domain | Fleiss' kappa |
|--------|---------------|
| aki | -0.0539 |
| atrial_fibrillation | -0.0407 |
| chest_pain | 0.0355 |
| copd | 0.2798 |
| dka | -0.0788 |
| gi_bleeding | -0.0483 |
| heart_failure | -0.1724 |
| hypertensive_emergency | 0.1656 |
| other | 0.0119 |
| pneumonia | 0.0386 |
| pulmonary_embolism | -0.0504 |
| sepsis | -0.1722 |
| stroke | -0.0982 |

### Per-Model
| Model | Fleiss' kappa |
|-------|---------------|
| 120B | 0.0144 |
| 27B | 0.0366 |
| 35B | 0.0101 |
| 397B | 0.0384 |
| 4B | 0.0413 |
| DeepSeek-R1-7B | -0.0172 |
| Gemma31B | 0.0838 |
| Llama4-Scout-17B | 0.0498 |
| Nemotron30B | 0.0979 |

## 3. Rank Reversal Analysis

**Total rank reversals**: 191

### Rank Correlations
| Pair | Spearman rho | Kendall tau | Reversals |
|------|-------------|-------------|-----------|
| DxEM vs AC-Proxy | 0.8000 | 0.6111 | 7 |
| DxEM vs MAB-Proxy | -0.2167 | -0.1667 | 21 |
| DxEM vs C2 | 0.5833 | 0.3889 | 11 |
| DxEM vs ACov | 0.8000 | 0.6111 | 7 |
| DxEM vs CGA-Bench | 0.1500 | 0.0556 | 17 |
| AC-Proxy vs MAB-Proxy | -0.0333 | 0.0000 | 18 |
| AC-Proxy vs C2 | 0.7833 | 0.5556 | 8 |
| AC-Proxy vs ACov | 1.0000 | 1.0000 | 0 |
| AC-Proxy vs CGA-Bench | 0.1667 | 0.1111 | 16 |
| MAB-Proxy vs C2 | -0.0500 | -0.1111 | 20 |
| MAB-Proxy vs ACov | -0.0333 | 0.0000 | 18 |
| MAB-Proxy vs CGA-Bench | 0.1167 | 0.1111 | 16 |
| C2 vs ACov | 0.7833 | 0.5556 | 8 |
| C2 vs CGA-Bench | 0.6833 | 0.5556 | 8 |
| ACov vs CGA-Bench | 0.1667 | 0.1111 | 16 |

### Concrete Reversals (first 10)
- **120B** vs **35B**: DxEM ranks 1/3, AC-Proxy ranks 2/1
- **27B** vs **35B**: DxEM ranks 2/3, AC-Proxy ranks 5/1
- **27B** vs **397B**: DxEM ranks 2/4, AC-Proxy ranks 5/3
- **27B** vs **4B**: DxEM ranks 2/5, AC-Proxy ranks 5/4
- **DeepSeek-R1-7B** vs **Gemma31B**: DxEM ranks 6/7, AC-Proxy ranks 8/7
- **DeepSeek-R1-7B** vs **Llama4-Scout-17B**: DxEM ranks 6/8, AC-Proxy ranks 8/6
- **Gemma31B** vs **Llama4-Scout-17B**: DxEM ranks 7/8, AC-Proxy ranks 7/6
- **120B** vs **27B**: DxEM ranks 1/2, MAB-Proxy ranks 8/3
- **120B** vs **35B**: DxEM ranks 1/3, MAB-Proxy ranks 8/7
- **120B** vs **397B**: DxEM ranks 1/4, MAB-Proxy ranks 8/5

## 4. Effect Size Analysis

**Most lenient**: DxEM
**Most strict**: C2
**Max gap**: 0.7218 (95% CI: [0.7156, 0.7280])

### Per-Model Gap
| Model | Gap | Most Lenient | Most Strict |
|-------|-----|-------------|-------------|
| 120B | 0.6449 | DxEM | C2 |
| 27B | 0.6964 | DxEM | C2 |
| 35B | 0.6355 | DxEM | C2 |
| 397B | 0.6039 | DxEM | C2 |
| 4B | 0.7465 | DxEM | C2 |
| DeepSeek-R1-7B | 0.9297 | DxEM | C2 |
| Gemma31B | 0.6832 | DxEM | C2 |
| Llama4-Scout-17B | 0.7380 | DxEM | C2 |
| Nemotron30B | 0.8178 | DxEM | C2 |

## 5. Statistical Tests

**Cochran's Q**: Q=29758.0619, df=5, p=0.00e+00

**McNemar tests**: 14/15 significant after Bonferroni correction (alpha=0.0033)

| Pair | chi2 | p | Significant |
|------|------|---|-------------|
| DxEM vs AC-Proxy | 4409.00 | 0.00e+00 | Yes |
| DxEM vs MAB-Proxy | 9019.00 | 0.00e+00 | Yes |
| DxEM vs C2 | 13758.00 | 0.00e+00 | Yes |
| DxEM vs ACov | 4409.00 | 0.00e+00 | Yes |
| DxEM vs CGA-Bench | 10567.00 | 0.00e+00 | Yes |
| AC-Proxy vs MAB-Proxy | 3826.45 | 0.00e+00 | Yes |
| AC-Proxy vs C2 | 8753.51 | 0.00e+00 | Yes |
| AC-Proxy vs ACov | 0.00 | 1.0000 | No |
| AC-Proxy vs CGA-Bench | 3246.66 | 0.00e+00 | Yes |
| MAB-Proxy vs C2 | 2231.75 | 0.00e+00 | Yes |
| MAB-Proxy vs ACov | 3826.45 | 0.00e+00 | Yes |
| MAB-Proxy vs CGA-Bench | 208.01 | 0.00e+00 | Yes |
| C2 vs ACov | 8753.51 | 0.00e+00 | Yes |
| C2 vs CGA-Bench | 1318.12 | 0.00e+00 | Yes |
| ACov vs CGA-Bench | 3246.66 | 0.00e+00 | Yes |

## 6. Disagreement Taxonomy

**Disagreement episodes**: 17544 / 19062 (92.0%)

| Type | Count | % | Examples |
|------|-------|---|---------|
| Type A: Timing | 10099 | 57.6% | aabb_t_basic_cardiac_liberal_threshold_DeepSeek-R1-7B_0, aabb_t_basic_cardiac_liberal_threshold_DeepSeek-R1-7B_1 |
| Type B: Forbidden | 1962 | 11.2% | acls_combo_hypothermia_no_drugs_nonshockable_epi_immediate_tamponade_pericardiocentesis_DeepSeek-R1-7B_0, acls_combo_hypothermia_no_drugs_nonshockable_epi_immediate_tamponade_pericardiocentesis_DeepSeek-R1-7B_1 |
| Type C: Completeness | 176 | 1.0% | adhf_warm_wet_120B_0, adhf_warm_wet_120B_1 |
| Type D: Partial credit | 7064 | 40.3% | aabb_t_combo_cardiac_liberal_threshold_jehovah_no_blood_anaphylaxis_epi_DeepSeek-R1-7B_0, aabb_t_trap_txa_within_3h_time_sin_boundary_DeepSeek-R1-7B_0 |
