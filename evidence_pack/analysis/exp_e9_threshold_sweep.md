# E9 Follow-up F1 — Authority Threshold Sweep

Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md

## Headline comparison

| Sweep | Taxonomy | Strict FA | MAB replay loss | AC replay loss | Ranking reversal | High nodes |
|---|---|---|---|---|---|---|
| **S1** | default high-authority | 5.90% (1124) | 62.06% | 84.39% | 1/36 (2.78%) | 581/636 |
| **S2** | strictest (Class I+A only, no allergy) | 2.87% (548) | 76.81% | 89.15% | 12/36 (33.33%) | 192/636 |
| **S3** | default minus drug-allergy | 5.90% (1124) | 62.06% | 84.39% | 1/36 (2.78%) | 581/636 |

## Pre-registered success-criterion check

| Sweep | strict-FA > 0 | MAB replay loss > 50% (qualitative) | ≥0 ranking reversals |
|---|---|---|---|
| **S1** | YES | YES | YES |
| **S2** | YES | YES | YES |
| **S3** | YES | YES | YES |

## Constraint-event drop rate per sweep

| Sweep | Total events | Retained | Drop rate |
|---|---|---|---|
| **S1** | 179225 | 177573 | 0.92% |
| **S2** | 179225 | 109199 | 39.07% |
| **S3** | 179225 | 177573 | 0.92% |

## Interpretation

* S1 is the published E9 headline. * S2 (Class I + LOE A only, no IIa, no allergy) is the strictest filter we believe a reviewer could reasonably demand. * S3 isolates the contribution of the drug-allergy auto-promotion.