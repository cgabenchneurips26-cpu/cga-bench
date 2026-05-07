# E9 Follow-up F3 — Severity Overlay on Strict-FA Episodes

Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (§5.3)

**Strict-FA episodes**: 1124

## Severity distribution (max harm per episode)

| Severity | Count | Share |
|---|---|---|
| catastrophic | 0 | 0.00% |
| severe | 22 | 1.96% |
| major | 85 | 7.56% |
| moderate | 189 | 16.81% |
| minor | 828 | 73.67% |
| none | 0 | 0.00% |

## Aggregate shares

- Critical / Severe / Major (combined): **9.52%**
- Moderate: 16.81%
- Minor: 73.67%
- None / soft only: 0.00%

## Promotion decision

- Threshold for promotion to main §5.5: **critical_major share >= 20%**
- Result: **APPENDIX-ONLY**
- Reason: critical_major share = 0.0952; threshold = 0.20

## Per-model severity distribution

| Model | catastrophic | severe | major | moderate | minor | none |
|---|---|---|---|---|---|---|
| deepseek_r1_7b | 0 | 3 | 8 | 14 | 16 | 0 |
| gemma31b | 0 | 2 | 0 | 19 | 16 | 0 |
| llama4scout | 0 | 8 | 23 | 40 | 141 | 0 |
| nemotron30b | 0 | 5 | 45 | 4 | 8 | 0 |
| oss120b | 0 | 1 | 2 | 22 | 139 | 0 |
| qwen27b | 0 | 0 | 0 | 19 | 105 | 0 |
| qwen35b | 0 | 0 | 6 | 21 | 104 | 0 |
| qwen397b | 0 | 0 | 0 | 20 | 167 | 0 |
| qwen4b | 0 | 3 | 1 | 30 | 132 | 0 |

## Drop-in paper sentences

> Severity overlay (Appendix Z.5) reports a 9.5\% critical+major share across the 1124 strict-FA episodes; the share falls below the pre-registered 20\% threshold for main-text promotion.