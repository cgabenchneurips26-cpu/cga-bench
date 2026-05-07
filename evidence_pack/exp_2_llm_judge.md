# EXP-2: LLM Judge Pipeline Agreement Analysis

**Mode**: dry-run
**Model**: Qwen/Qwen3-30B-A3B-Instruct-2507
**Episodes evaluated**: 10

## Judge Variant Pass Rates

| Variant | Pass Rate |
|---------|-----------|
| rubric_free | 0.0% |
| rubric_aware | 0.0% |
| cot_judge | 0.0% |

## Inter-Judge Agreement (between prompt variants)

| Pair | Cohen's Kappa | Interpretation |
|------|---------------|----------------|
| rubric_free_vs_rubric_aware | 1.0000 | almost perfect agreement |
| rubric_free_vs_cot_judge | 1.0000 | almost perfect agreement |
| rubric_aware_vs_cot_judge | 1.0000 | almost perfect agreement |

## Judge vs CGA-Bench Evaluator Agreement

### rubric_free

| Evaluator | Kappa | Agreement % | Interpretation |
|-----------|-------|-------------|----------------|
| DxEM | 0.0000 | 0.0% | slight agreement |
| AC-Proxy | 0.0000 | 0.0% | slight agreement |
| MAB-Proxy | 0.0000 | 80.0% | slight agreement |
| C2 | 1.0000 | 100.0% | almost perfect agreement |
| ACov | 0.0000 | 0.0% | slight agreement |
| CGA-Bench | 0.0000 | 10.0% | slight agreement |

### rubric_aware

| Evaluator | Kappa | Agreement % | Interpretation |
|-----------|-------|-------------|----------------|
| DxEM | 0.0000 | 0.0% | slight agreement |
| AC-Proxy | 0.0000 | 0.0% | slight agreement |
| MAB-Proxy | 0.0000 | 80.0% | slight agreement |
| C2 | 1.0000 | 100.0% | almost perfect agreement |
| ACov | 0.0000 | 0.0% | slight agreement |
| CGA-Bench | 0.0000 | 10.0% | slight agreement |

### cot_judge

| Evaluator | Kappa | Agreement % | Interpretation |
|-----------|-------|-------------|----------------|
| DxEM | 0.0000 | 0.0% | slight agreement |
| AC-Proxy | 0.0000 | 0.0% | slight agreement |
| MAB-Proxy | 0.0000 | 80.0% | slight agreement |
| C2 | 1.0000 | 100.0% | almost perfect agreement |
| ACov | 0.0000 | 0.0% | slight agreement |
| CGA-Bench | 0.0000 | 10.0% | slight agreement |
