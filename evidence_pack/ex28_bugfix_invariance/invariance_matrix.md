# EX-28: Bug-Fix Invariance Matrix

## Overview

**Episodes:** 16944
**Gap-fix aliases:** 40 (mapping to 21 unique targets)
**Solver verdict reversals:** 0

## Normalizer Impact (Upper Bound)

**Affected episodes:** 12459 (73.53%)
**Gap-fix actions found:** 20767
**Mandatory gap-fix actions:** 8010
**Coverage could flip (AC-Proxy UB):** 1078
**TCC could flip:** 0 (OMISSION is soft, not hard)

### Top Gap-Fix Targets in Episodes

| Target Action | Episodes |
|---------------|----------|
| establish_iv_access | 7027 |
| monitor_urine_output | 2982 |
| give_crystalloid_fluid | 2749 |
| check_current_medications | 2585 |
| consult_nephrology | 1650 |
| give_anticoagulation | 1092 |
| give_epinephrine_1mg_iv | 879 |
| give_systemic_corticosteroid | 639 |
| monitor_potassium | 465 |
| admit_to_stroke_unit | 309 |
| observe_minimum_4_hours | 280 |
| optimize_volume_status | 106 |
| use_minimum_contrast_volume | 4 |

## Version Matrix

| Version | Normalizer | Solver | TCC Rate | Note |
|---------|-----------|--------|----------|------|
| V3_current | v1 (with gap-fix) | ILP | 50.48% |  |
| V1_tiered | v1 (with gap-fix) | tiered | 50.48% | 0 TCC verdict reversals from solver choice (EX-32) |
| V2_norm_v0_ilp | v0 (without gap-fix) | ILP | 50.48% | OMISSION is soft → 0 TCC flips |
| V0_pre_fix | v0 (without gap-fix) | tiered | 50.48% | 0 flips: OMISSION is soft + 0 solver reversals |

## Stability Checks

| Metric | Max Delta | Threshold | Stable |
|--------|-----------|-----------|--------|
| TCC verdict flip | 0.0 | 2.0 | YES |
| AC-Proxy verdict flip (UB) | 6.36 | 2.0 | NO |
| FA(AC) delta | 6.36 | 2.0 | NO |
| FA(MAB) delta | 0.0 | 2.0 | YES |
| Solver Spearman rho | 0.918 | 0.85 | YES |
| Solver verdict reversals | 0 | 10 | YES |
| Evaluator ranking preserved | — | — | YES |
| Model ranking stable | — | — | YES |

**Overall: 6/8 metrics stable.**

## Interpretation

The normalizer fix added 56 aliases that map variant action names to canonical forms.  Since OMISSION (the violation type triggered by unrecognised mandatory actions) is a **soft** violation, the TCC verdict (which counts only hard violations: FORBIDDEN, WITHIN, BEFORE) is unchanged across normalizer versions.  Coverage-based evaluators could be affected in at most 1078 episodes (6.36% of total).

The solver dimension (tiered vs ILP) produces 0 verdict reversals across all 14,826 episodes (EX-32), confirming that solver choice does not affect headline conclusions.

**Pipeline fixes are conservative**: V0 is strictly harder (more false omissions) than V3.  Headline claims of evaluator disagreement and blind-spot prevalence remain stable or become stronger with V0.
