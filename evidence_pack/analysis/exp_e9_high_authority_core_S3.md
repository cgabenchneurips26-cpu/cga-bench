# E9: High-Authority Core Robustness Audit

Spec: docs/attack_gap_exp_exp/260430_e9_High-Authority_Core_Robustness.md

**Episodes evaluated**: 19062

## Headline metrics

| Metric | Full catalogue | High-authority subset |
|---|---|---|
| Strict FA (ASC ∩ CwT ∩ PAF pass, TCC fail) | 5.90% (1124) | 5.90% (1124) |
| Replay loss (MAB-proxy under TCC) | 61.83% | 62.06% |
| Replay loss (AC-proxy under TCC) | 84.40% | 84.39% |
| Replay loss (C2 under TCC) | 21.45% | 21.35% |
| Ranking reversal (high-authority TCC vs cached TCC) | -- | 2.78% (1/36) |

## Pre-registered success criterion

* strict-FA stays non-zero: **YES** (5.90%)
* replay loss > 50%: **YES** (MAB=62.06%)
* >= 1 ranking reversal persists: **YES** (1 of 36 model pairs)

## Per-violation-type breakdown (count per episode-type)

| Type | Full | High-authority |
|---|---|---|
| BEFORE | 101 | 101 |
| FORBIDDEN | 1958 | 1958 |
| WITHIN | 10124 | 10086 |

## Constraint-count drop

Total violation events: 179225, high-authority retained: 177573 (drop rate 0.92%)

## Per-model fail rate (TCC pass = no hard violations)

| Model | Full TCC fail rate | High-authority TCC fail rate |
|---|---|---|
| deepseek_r1_7b | 66.38% | 64.97% |
| gemma31b | 47.12% | 47.12% |
| llama4scout | 57.60% | 57.60% |
| nemotron30b | 55.43% | 55.05% |
| oss120b | 56.66% | 56.66% |
| qwen27b | 52.31% | 52.31% |
| qwen35b | 55.15% | 55.15% |
| qwen397b | 49.48% | 49.48% |
| qwen4b | 58.78% | 58.78% |
