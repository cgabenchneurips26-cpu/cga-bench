# Tier S Regression Diff — expansion_v7 vs Apr 23 baseline

_Generated: 2026-04-26T07:40:07_

## Episode counts
- expansion_v7 aggregate: **7,655** episodes across 5 base models
- Apr 23 baseline (`tier_s_robustness.json` full): 14826 episodes

## Per-endpoint episode counts (consolidated by base model)

| Base model | Endpoints | n_episodes | mean_compliance |
|---|---|---|---|
| deepseek_r1_7b | 4 (deepseek_r1_7b_exp1, deepseek_r1_7b_exp2, deepseek_r1_7b_local1, deepseek_r1_7b_local2) | 2,750 | 0.3563 |
| oss120b | 3 (oss120b, oss120b_exp2, oss120b_exp3) | 2,124 | 0.5435 |
| qwen27b | 1 (qwen27b_local) | 708 | 0.5279 |
| qwen35b_a3b | 1 (qwen35b_a3b_local) | 683 | 0.4981 |
| qwen397b | 2 (qwen397b, qwen397b_react_s2) | 1,390 | 0.5235 |

## Evaluator pass-rate / FA diff vs Apr 23 baseline (W8 full)

| Evaluator | Baseline pass% | v7 pass% | Δpass | Baseline FA% | v7 FA% | ΔFA | Flag |
|---|---|---|---|---|---|---|---|
| ASC | 74.1 | 91.47 | +17.37 | 40.5 | 20.33 | -20.17 | [PASS-REGRESSION] [FA-REGRESSION] |
| PAF | 53.9 | 42.6 | -11.30 | 31.3 | 9.64 | -21.66 | [PASS-REGRESSION] [FA-REGRESSION] |
| CwT | 36.4 | 11.95 | -24.45 | 13.3 | 2.28 | -11.02 | [PASS-REGRESSION] [FA-REGRESSION] |
| TCC | 51.6 | 76.25 | +24.65 | 0.0 | n/a | n/a | [PASS-REGRESSION] |

**Threshold for regression flag**: |Δ| ≥ 5.0pp.

## Notes

- Comparison is across different scenario sets: baseline=14,826 W8 episodes, expansion_v7=mixed Tier S coverage. Exact numerical equivalence is NOT expected — regression flags catch large directional shifts only.
- Tier S scenarios have grown from 535 (Apr 23, 17 CPGs subset) to 2,480 (current, 31 CPGs). Verdict definitions are frozen via `verdict_definitions.py`.
