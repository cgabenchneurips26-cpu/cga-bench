# WS-6: Error Taxonomy

- Total episodes: 180
- Episodes with violations: 180
- Compound episodes (multi-category): 73
- Total classified violations: 1767

## Overall Distribution

| Category | Name | Count | Rate |
|----------|------|------:|-----:|
| 1a | Safety: Medication Contraindication | 24 | 1.4% |
| 1b | Safety: Procedure Contraindication | 0 | 0.0% |
| 2a | Temporal: Sequence Reversal | 0 | 0.0% |
| 2b | Temporal: Deadline Exceeded | 115 | 6.5% |
| 3a | Omission: Critical Treatment | 1325 | 75.0% |
| 3b | Omission: Monitoring | 230 | 13.0% |
| 4 | Compound (Multi-Category) | 73 | 4.1% |

## Per-Model Distribution

| Model | Medication Contraindication | Procedure Contraindication | Sequence Reversal | Deadline Exceeded | Critical Treatment | Monitoring | Compound (Multi-Category) | Total |
|-------|------:|------:|------:|------:|------:|------:|------:|------:|
| DeepSeek-V3 (120B) | 6 | 0 | 0 | 46 | 442 | 83 | 19 | 596 |
| R1-Distill (27B) | 6 | 0 | 0 | 23 | 330 | 57 | 19 | 435 |
| Qwen3.5 (35B) | 6 | 0 | 0 | 23 | 315 | 56 | 20 | 420 |
| Qwen3 (4B) | 6 | 0 | 0 | 23 | 238 | 34 | 15 | 316 |

## Per-Domain Distribution

| Domain | Medication Contraindication | Procedure Contraindication | Sequence Reversal | Deadline Exceeded | Critical Treatment | Monitoring | Compound (Multi-Category) | Total |
|-------|------:|------:|------:|------:|------:|------:|------:|------:|
| aki | 0 | 0 | 0 | 6 | 296 | 50 | 5 | 357 |
| atrial_fibrillation | 0 | 0 | 0 | 11 | 112 | 7 | 10 | 140 |
| chest_pain | 0 | 0 | 0 | 21 | 16 | 12 | 12 | 61 |
| copd | 0 | 0 | 0 | 0 | 79 | 11 | 0 | 90 |
| dka | 24 | 0 | 0 | 35 | 117 | 71 | 24 | 271 |
| gi_bleeding | 0 | 0 | 0 | 0 | 90 | 8 | 0 | 98 |
| heart_failure | 0 | 0 | 0 | 2 | 84 | 35 | 2 | 123 |
| other | 0 | 0 | 0 | 0 | 237 | 26 | 0 | 263 |
| pulmonary_embolism | 0 | 0 | 0 | 0 | 106 | 10 | 0 | 116 |
| sepsis | 0 | 0 | 0 | 40 | 46 | 0 | 20 | 106 |
| stroke | 0 | 0 | 0 | 0 | 142 | 0 | 0 | 142 |
