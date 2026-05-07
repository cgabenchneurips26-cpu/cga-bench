# E7: Paired Delta Analysis — Manual vs Engine Scenarios

## Summary
- Total episodes: 78823 (manual=2520, auto=14424)
- Paired (graph, model) keys: 112
- Graphs with pairs: 14

## Aggregate Metrics
| Metric | Manual | Auto | Delta |
|--------|--------|------|-------|
| FA rate | 0.2464 | 0.5362 | +0.2898 |
| All-oblivious FA | 0.1698 | 0.2637 | +0.0939 |
| Hard-viol rate | 0.5468 | 0.5532 | — |

Manual FA 95% CI: [0.2298, 0.2631]
Auto FA 95% CI: [0.5280, 0.5442]

## Newly Exposed by Engine
- Count: 2436 / 8472 = 28.7%

## McNemar Test (Graph-Level)
- Manual-pass / Auto-fail: 31
- Manual-fail / Auto-pass: 49
- Chi2: 3.6125

## Per-Graph Deltas
| Graph | Manual FA | Auto FA | Delta | Newly Exposed | Held-out |
|-------|-----------|---------|-------|---------------|----------|
| ada_dka_management | 0.726 (288) | 0.975 (720) | +0.249 | 0 |  |
| aha_chest_pain_evaluation | 0.288 (312) | 0.448 (504) | +0.160 | 126 |  |
| aha_heart_failure_2022 | 0.013 (240) | 0.232 (1056) | +0.220 | 0 |  |
| aha_stroke_2019 | 0.106 (312) | 0.486 (576) | +0.380 | 72 |  |
| atrial_fibrillation | 0.444 (144) | 0.968 (408) | +0.524 | 204 |  |
| cap_pneumonia | 0.025 (120) | 0.083 (408) | +0.058 | 0 |  |
| copd_exacerbation | 0.000 (144) | 0.078 (360) | +0.078 | 45 |  |
| gi_bleeding | 0.208 (120) | 0.308 (432) | +0.100 | 162 |  |
| hypertensive_emergency | 0.035 (144) | 0.451 (264) | +0.416 | 132 |  |
| kdigo_aki_full | 0.010 (192) | 0.018 (1536) | +0.007 | 960 |  |
| kdigo_contrast_aki | 0.142 (120) | 0.160 (888) | +0.018 | 222 |  |
| pulmonary_embolism | 0.050 (120) | 0.238 (576) | +0.188 | 288 |  |
| ssc_sepsis_hour1_bundle | 0.683 (240) | 0.211 (312) | -0.472 | 117 |  |
| universal_clinical_safety | 0.000 (24) | 0.079 (432) | +0.079 | 108 |  |

## Model x Source Interaction
| Model | Manual FA | Auto FA | Delta |
|-------|-----------|---------|-------|
| _duplicates_archive_20260427 | 0.0000 (0) | 0.0000 (0) | +0.0000 |
| _gemma31b_auto_v2_unscored_extras_20260427 | 0.0000 (0) | 0.0000 (0) | +0.0000 |
| _oss120b_dup_archive_20260427 | 0.0000 (0) | 0.0000 (0) | +0.0000 |
| deepseek_r1_7b | 0.2667 (315) | 0.6129 (1803) | +0.3462 |
| gemma31b | 0.2635 (315) | 0.3943 (1803) | +0.1309 |
| nemotron30b | 0.2508 (315) | 0.5114 (1803) | +0.2606 |
| oss120b | 0.2635 (315) | 0.5979 (1803) | +0.3344 |
| qwen27b | 0.2444 (315) | 0.4836 (1803) | +0.2392 |
| qwen35b | 0.2413 (315) | 0.5691 (1803) | +0.3278 |
| qwen397b | 0.2444 (315) | 0.5164 (1803) | +0.2719 |
| qwen4b | 0.1968 (315) | 0.6040 (1803) | +0.4072 |
