# WS-4: Run Variance Analysis

## 1. Intra-Scenario Variance (Pass/Fail Agreement)

- Total (scenario, model) pairs with 3 runs: **60**
- 3/3 unanimous agreement: **54** (90.0%)
- 2/1 split: **6** (10.0%)

## 2. Run Variance vs Evaluator Variance

- Mean within-run evaluator entropy: **0.7729**
- Mean across-run instability: **0.0111**
- Wilcoxon signed-rank test: W=0.0, p=8.00e-12 (significant)

## 3. Variance Decomposition

- N observations: 180
- Grand mean compliance: 0.4556
- Model effect (eta-sq): **0.0176** (1.8%)
- Scenario effect (eta-sq): **0.8412** (84.1%)
- Residual (Run + Interaction): **0.1412** (14.1%)

Interpretation: Low residual eta-squared indicates that run-to-run variance is small relative to model and scenario effects.

## 4. Bootstrap Sufficiency

- Total (scenario, model) pairs: **60**
- Pairs with stable majority vote (>95%): **54** (90.0%)
- Bootstrap samples: 5000

### Unstable Pairs (majority vote may flip)

| Model | Scenario | Verdicts | Stability |
|-------|----------|----------|-----------|
| DeepSeek-V3 (120B) | adhf_warm_wet | [0, 1, 0] | 73.2% |
| Qwen3.5 (35B) | htn_emergency_basic | [0, 0, 1] | 73.3% |
| Qwen3.5 (35B) | copd_moderate_exacerbation | [1, 0, 0] | 74.1% |
| Qwen3 (4B) | contrast_aki_prevention_basic | [1, 0, 1] | 74.1% |
| R1-Distill (27B) | copd_moderate_exacerbation | [0, 1, 1] | 74.3% |
| DeepSeek-V3 (120B) | htn_emergency_basic | [1, 1, 0] | 75.2% |
## Analysis 3b: Evaluator vs Run Variance Decomposition

| Factor | eta-squared | Interpretation |
|--------|------------|----------------|
| Evaluator | 0.2963 (29.6%) | Variance from evaluator choice |
| Run | 0.0004 (0.0%) | Run-to-run noise |
| Residual | 0.7033 (70.3%) | Scenario/model interaction |

**Evaluator/Run dominance ratio: 830.6x**

This confirms the paper's key claim: observed disagreement is driven by evaluator design, not run-to-run noise.
