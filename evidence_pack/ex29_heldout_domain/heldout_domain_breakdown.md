# EX-29: Held-Out Per-Domain Breakdown

**Held-out domains:** 5
**In-domain episodes:** 15360

## Per-Domain Metrics

| Domain | N | Flip% | FA(AC)% | FA(MAB)% | FA(C2)% | AO-FA% | d |
|--------|---|-------|---------|----------|---------|--------|---|
| aabb_transfusion | 288 | 68.1 | 8.0 | 0.3 | 8.0 | 8.0 | -0.646 |
| aba_burn_resuscitation | 480 | 93.5 | 91.0 | 70.0 | 21.0 | 21.0 | 1.07 |
| acog_obstetric_hemorrhage | 216 | 87.5 | 75.9 | 26.9 | 75.5 | 75.5 | 0.751 |
| apa_agitation_management | 360 | 100.0 | 99.7 | 51.4 | 74.7 | 74.7 | 1.251 |
| pals_pediatric_emergency | 240 | 99.2 | 75.0 | 25.0 | 70.4 | 70.4 | 0.732 |
| **In-domain** | 15360 | 79.4 | 39.3 | 31.0 | 12.1 | 12.1 | ref |

## Violation Type Distribution

| Domain | COMMISSION | TIMING | SEQUENCE | OMISSION | DEVIATION |
|--------|-----------|--------|----------|----------|-----------|
| aabb_transfusion | 0.4% | 0.6% | 0.0% | 11.9% | 87.1% |
| aba_burn_resuscitation | 0.0% | 8.6% | 1.6% | 54.0% | 35.8% |
| acog_obstetric_hemorrhage | 3.4% | 12.1% | 0.0% | 12.0% | 72.5% |
| apa_agitation_management | 3.5% | 21.7% | 0.0% | 19.4% | 55.4% |
| pals_pediatric_emergency | 0.0% | 18.9% | 0.0% | 6.1% | 75.0% |

## Cross-Domain Consistency

- FA range: 8.0--99.7%
- Flip range: 68.1--100.0%
- Spearman rho (AO-FA vs flip): 0.4
- Domains with blind spots: 5/5