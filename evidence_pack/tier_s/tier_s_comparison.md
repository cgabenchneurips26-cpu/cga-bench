# Tier S Robustness: Full vs Tier S Comparison

Tier S: 17 CPGs (score >= 15/19), 535 scenarios, 11235 episodes

| Metric | Full (14826) | Tier S (11235) | Delta |
| --- | :---: | :---: | :---: |
| Episodes | 14826 | 11235 | -3591 |
| Hard violations (%) | 48.4% | 47.9% | -0.5 |
| Strict FA rate | 10.7% | 10.1% | -0.6 |
| Verdict flip rate | 83.5% | 83.2% | -0.3 |
| eta2(evaluator) | 0.0725 | 0.0809 | +0.0 |
| eta2(run) | 0.0515 | 0.0613 | +0.0 |
| eta2 ratio | 1.4x | 1.3x | -0.1 |

## Per-Evaluator Pass Rates

| Evaluator | Full | Tier S | Delta |
| --- | :---: | :---: | :---: |
| AC-Proxy | 74.1% | 73.5% | -0.6% |
| MAB-Proxy | 53.9% | 56.0% | +2.1% |
| C2 | 36.4% | 33.6% | -2.8% |
| CGA-Bench | 51.6% | 52.1% | +0.5% |

## Per-Evaluator False-Accept Rates (against v4_hard)

| Evaluator | Full | Tier S | Delta |
| --- | :---: | :---: | :---: |
| AC-Proxy | 40.5% | 39.8% | -0.7% |
| MAB-Proxy | 31.3% | 32.9% | +1.6% |
| C2 | 13.3% | 13.1% | -0.2% |
| CGA-Bench | 0.0% | 0.0% | +0.0% |

## Per-Evaluator BSR

| Evaluator | Full | Tier S | Delta |
| --- | :---: | :---: | :---: |
| AC-Proxy | 0.5839 | 0.5811 | -0.0028 |
| MAB-Proxy | 0.6025 | 0.6186 | +0.0161 |
| C2 | 0.4186 | 0.4457 | +0.0271 |
| CGA-Bench | 0.0000 | 0.0000 | +0.0000 |
