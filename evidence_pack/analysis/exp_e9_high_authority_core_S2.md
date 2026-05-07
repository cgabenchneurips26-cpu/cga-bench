# E9: High-Authority Core Robustness Audit

Spec: docs/attack_gap_exp_exp/260430_e9_High-Authority_Core_Robustness.md

**Episodes evaluated**: 19062

## Headline metrics

| Metric | Full catalogue | High-authority subset |
|---|---|---|
| Strict FA (ASC ∩ CwT ∩ PAF pass, TCC fail) | 5.90% (1124) | 2.87% (548) |
| Replay loss (MAB-proxy under TCC) | 61.83% | 76.81% |
| Replay loss (AC-proxy under TCC) | 84.40% | 89.15% |
| Replay loss (C2 under TCC) | 21.45% | 11.05% |
| Ranking reversal (high-authority TCC vs cached TCC) | -- | 33.33% (12/36) |

## Pre-registered success criterion

* strict-FA stays non-zero: **YES** (2.87%)
* replay loss > 50%: **YES** (MAB=76.81%)
* >= 1 ranking reversal persists: **YES** (12 of 36 model pairs)

## Per-violation-type breakdown (count per episode-type)

| Type | Full | High-authority |
|---|---|---|
| BEFORE | 101 | 58 |
| FORBIDDEN | 1958 | 995 |
| WITHIN | 10124 | 5679 |

## Constraint-count drop

Total violation events: 179225, high-authority retained: 109199 (drop rate 39.07%)

## Per-model fail rate (TCC pass = no hard violations)

| Model | Full TCC fail rate | High-authority TCC fail rate |
|---|---|---|
| deepseek_r1_7b | 66.38% | 30.93% |
| gemma31b | 47.12% | 29.32% |
| llama4scout | 57.60% | 33.19% |
| nemotron30b | 55.43% | 28.85% |
| oss120b | 56.66% | 29.79% |
| qwen27b | 52.31% | 28.38% |
| qwen35b | 55.15% | 30.45% |
| qwen397b | 49.48% | 29.89% |
| qwen4b | 58.78% | 29.37% |
