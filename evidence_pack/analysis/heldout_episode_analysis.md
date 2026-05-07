# Held-out Domain Episode Analysis

## Summary
- In-domain: 15360 episodes (61879 unmatched)
- Held-out: 1584 episodes
- Held-out graphs: aabb_transfusion, aba_burn_resuscitation, acog_obstetric_hemorrhage, apa_agitation_management, pals_pediatric_emergency

## Claim Metrics Comparison
| Metric | In-Domain | Held-Out | Fisher p |
|--------|-----------|----------|----------|
| FA rate | 0.4539 [0.446, 0.462] | 0.8731 [0.857, 0.889] | 0.0 |
| All-oblivious FA | 0.2105 | 0.6301 | — |
| Verdict-flip rate | 0.6028 | 0.8737 | — |
| BSR (AC) | 0.4539 | 0.8731 | — |
| BSR (C2) | 0.2150 | 0.6301 | — |
| Hard-viol rate | 0.5191 | 0.8737 | — |
| Mean compliance | 0.5463 | 0.5860 | — |

## Per Held-Out Graph
| Graph | N | FA Rate | AO Rate | Flip Rate | Compliance |
|-------|---|---------|---------|-----------|------------|
| aabb_transfusion | 288 | 0.410 | 0.368 | 0.413 | 0.701 |
| aba_burn_resuscitation | 480 | 0.971 | 0.217 | 0.971 | 0.404 |
| acog_obstetric_hemorrhage | 216 | 1.000 | 1.000 | 1.000 | 0.665 |
| apa_agitation_management | 360 | 0.994 | 0.986 | 0.994 | 0.647 |
| pals_pediatric_emergency | 240 | 0.938 | 0.904 | 0.938 | 0.649 |

## Per-Model (In-Domain vs Held-Out)
| Model | In FA | HO FA | In Compliance | HO Compliance |
|-------|-------|-------|---------------|---------------|
| _duplicates_archive_20260427 | 0.000 (0) | — (0) | 0.000 | — |
| _gemma31b_auto_v2_unscored_extras_20260427 | 0.000 (0) | — (0) | 0.000 | — |
| _oss120b_dup_archive_20260427 | 0.000 (0) | — (0) | 0.000 | — |
| deepseek_r1_7b | 0.522 (1920) | 0.944 (198) | 0.366 | 0.436 |
| gemma31b | 0.337 (1920) | 0.748 (198) | 0.566 | 0.631 |
| nemotron30b | 0.423 (1920) | 0.950 (198) | 0.421 | 0.508 |
| oss120b | 0.512 (1920) | 0.894 (198) | 0.623 | 0.650 |
| qwen27b | 0.410 (1920) | 0.818 (198) | 0.577 | 0.654 |
| qwen35b | 0.481 (1920) | 0.899 (198) | 0.633 | 0.649 |
| qwen397b | 0.437 (1920) | 0.854 (198) | 0.618 | 0.632 |
| qwen4b | 0.509 (1920) | 0.879 (198) | 0.566 | 0.527 |
