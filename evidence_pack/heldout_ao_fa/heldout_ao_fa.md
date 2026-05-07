# Held-out All-Oblivious False-Accept Rate

**Total episodes**: 16944
**Held-out**: 1584 episodes (5 graphs)
**In-domain**: 15360 episodes (20 graphs)

## All-Oblivious FA Rate

All-oblivious FA = DxEM + AC-Proxy + C2 all pass, but episode has hard violations.

| Group | N | AO Pass | AO FA | AO FA Rate | 95% CI | Hard Viol Rate |
|-------|---|---------|-------|------------|--------|----------------|
| Held-out | 1584 | 148 | 92 | 5.8% | [4.7, 7.0]% | 75.8% |
| In-domain | 15360 | 5034 | 1867 | 12.2% | [11.7, 12.7]% | 47.9% |

## Fisher Exact Test

- Odds ratio: 0.4456
- p-value: 5.2573e-16
- Contingency: [[92, 1492], [1867, 13493]]

## Per Held-out Domain

| Domain | N | AO FA Count | AO FA Rate | Hard Viol Rate |
|--------|---|-------------|------------|----------------|
| aabb_transfusion | 288 | 16 | 5.6% | 8.0% |
| aba_burn_resuscitation | 480 | 0 | 0.0% | 98.8% |
| acog_obstetric_hemorrhage | 216 | 7 | 3.2% | 75.9% |
| apa_agitation_management | 360 | 24 | 6.7% | 99.7% |
| pals_pediatric_emergency | 240 | 45 | 18.8% | 75.0% |

## auto_numbers

- `\heldoutAllObliviousFA` = 5.8
- `\heldoutAllObliviousCount` = 92
- `\heldoutAOPassRate` = 9.3
- `\heldoutCondFA` = 62.2
- `\indomainAllObliviousFA` = 12.2
- `\indomainCondFA` = 37.1
- `\fisherPHeldoutAOFA` = 5.2573e-16
