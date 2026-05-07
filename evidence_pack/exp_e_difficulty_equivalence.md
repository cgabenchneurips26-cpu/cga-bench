# EXP-E: Manual vs Auto Difficulty Equivalence

**Manual scenarios**: 107
**Auto scenarios**: 601
**Episodes**: 180

## 1. Structural Difficulty Comparison

- Manual: 22.193 ± 15.343 (95% CI: [19.290, 25.146])
- Auto: 27.937 ± 15.339 (95% CI: [26.709, 29.159])
- Mann-Whitney U: p=1.08e-04
- KS test: p=1.86e-04
- Cohen's d: -0.3744

## 2. Model Ordering Stability

- Overall ranking: {'oss120b': 1, 'qwen27b': 2, 'qwen35b': 3, 'qwen4b': 4}
- LOO exact stability: 0.800
- LOO avg Spearman rho: 0.9600

## 3. Item-Total Correlation (Manual Baseline)

- Avg ITC: 0.1480
- High discriminators (ITC>0.3): 4
- Low discriminators (ITC<0): 1

## 4. Domain-Stratified Comparison

- Common domains: 14

| Domain | Manual Mean | Auto Mean | p-value |
|--------|------------|-----------|---------|
| ada_dka_management | 50.82 | 52.83 | 0.0062 |
| aha_chest_pain_evaluation | 39.78 | 40.46 | 0.0070 |
| aha_heart_failure_2022 | 18.99 | 19.47 | 0.8033 |
| aha_stroke_2019 | 24.90 | 27.79 | 0.00e+00 |
| atrial_fibrillation | 7.40 | 8.66 | 0.0126 |
| cap_pneumonia | 6.30 | 11.16 | 0.0029 |
| copd_exacerbation | 5.90 | 7.20 | 0.0204 |
| gi_bleeding | 4.50 | 7.97 | 0.0027 |
| hypertensive_emergency | 6.88 | 7.52 | 0.2789 |
| kdigo_aki_full | 13.20 | 25.90 | 0.00e+00 |
| kdigo_contrast_aki | 30.30 | 42.84 | 2.00e-04 |
| pulmonary_embolism | 6.00 | 8.01 | 0.0187 |
| ssc_sepsis_hour1_bundle | 26.25 | 26.97 | 1.0000 |
| universal_clinical_safety | 9.30 | 10.39 | N/A |

## 5. Edge Case Coverage

- Manual range: [0.0, 55.2]
- Auto range: [4.5, 59.5]
- Auto below manual min: 0
- Auto above manual max: 39
