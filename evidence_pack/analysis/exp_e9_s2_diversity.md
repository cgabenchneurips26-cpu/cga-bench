# G3 — S2 Strict-FA Diversity Analysis

**548 S2 strict-FA span 9 CPG source systems and 9 clinical domains; top-3 (anaph 35.6%, asthma 32.8%, acls 23.0%) account for 91.4%, ruling out a single-guideline artefact.**

## Summary

- **S2 strict-FA total**: 548
- **Distinct models**: 9
- **Distinct scenarios**: 122
- **Distinct domain prefixes**: 9
- **Distinct CPG source systems**: 9

---

## Table 1: By Model

| Model | Count | % |
|---|---:|---:|
| qwen397b | 156 | 28.5 |
| oss120b | 108 | 19.7 |
| llama4scout | 94 | 17.2 |
| qwen35b | 84 | 15.3 |
| qwen4b | 51 | 9.3 |
| qwen27b | 30 | 5.5 |
| gemma31b | 12 | 2.2 |
| nemotron30b | 8 | 1.5 |
| deepseek_r1_7b | 5 | 0.9 |

*Top model (qwen397b): 28.5% — no single-model dominance.*

---

## Table 2: By Domain Prefix

| Domain | Count | % |
|---|---:|---:|
| anaph | 195 | 35.6 |
| asthma | 180 | 32.8 |
| acls | 126 | 23.0 |
| mening | 26 | 4.7 |
| se | 14 | 2.6 |
| aabb | 3 | 0.5 |
| dka | 2 | 0.4 |
| pe | 1 | 0.2 |
| caki | 1 | 0.2 |

Top-3 (anaph 35.6%, asthma 32.8%, acls 23.0%) = 91.4% of S2 strict-FA.
Tail domains (<= 2% each): aabb 3 (0.5%), dka 2 (0.4%), pe 1 (0.2%), caki 1 (0.2%)

---

## Table 3: By CPG Source System

| CPG Source | Count | % |
|---|---:|---:|
| WAO | 195 | 35.6 |
| GINA | 180 | 32.8 |
| AHA-ACLS | 126 | 23.0 |
| IDSA | 26 | 4.7 |
| AAN-ACEP | 14 | 2.6 |
| AABB | 3 | 0.5 |
| ADA | 2 | 0.4 |
| ESC | 1 | 0.2 |
| KDIGO | 1 | 0.2 |

*Top CPG source (WAO): 35.6%.*

---

## Table 4: By Violation Type

| Violation Type | Count | % |
|---|---:|---:|
| WITHIN | 548 | 100.0 |
| FORBIDDEN | 4 | 0.7 |

---

## Gate Verdict

GATE VERDICT: **no single-guideline / no single-model artefact** -- top model (qwen397b) accounts for 28.5% (156/548); top CPG source (WAO) covers 35.6% of episodes; top domain (anaph) covers 35.6%.  The tail spans 9 models, 122 scenarios, 9 domain prefixes, 9 CPG systems.