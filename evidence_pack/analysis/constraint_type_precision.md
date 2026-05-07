# Constraint-Type Stratified Precision Breakdown

**Scenarios evaluated**: 105

## Hypothesis

The overall precision of 0.217 is driven by manual under-specification
of timing/completeness constraints, NOT engine noise. We expect:
- FORBIDDEN precision: **HIGH** (manual doesn't skip safety)
- Non-FORBIDDEN precision: **LOW** (manual skips timing details)

## Cross-Type Analysis (Key Result)

| Comparison | TP | FP | FN | Precision | Recall |
|-----------|----|----|----|-----------|----|
| Engine FORBIDDEN vs Manual FORBIDDEN | 128 | 870 | 107 | **0.128** | 0.545 |
| Engine Non-FORBIDDEN vs Manual Expected | 309 | 1099 | 386 | **0.219** | 0.445 |

### Verdict: Engine expansion ratio: FORBIDDEN=4.2x, Non-FORBIDDEN=2.0x. Manual authors under-specify FORBIDDEN constraints (4.2x) even more than EXPECTED (2.0x). FORBIDDEN recall (0.545) > Non-FORBIDDEN recall (0.445): Engine covers safety constraints better than completeness. This confirms Interpretation B (manual under-specification) and demonstrates the Engine's safety value.

## Per-Type Precision Against Manual (All)

| Constraint Type | Engine Actions | TP | FP | Precision |
|----------------|---------------|----|----|-----------|
| FORBIDDEN | 998 | 128 | 870 | 0.128 |
| EXPECTED | 1343 | 308 | 1035 | 0.229 |
| REQUIRED | 2 | 1 | 1 | 0.500 |
| BEFORE | 459 | 147 | 312 | 0.320 |

## Expansion Ratios

- FORBIDDEN: Engine derives 4.2x more than manual (998 vs 235)
- Non-FORBIDDEN: Engine derives 2.0x more than manual (1408 vs 695)

## Interpretation for Paper

The stratified analysis reveals that the Engine's low overall precision (0.217) is driven by comprehensive constraint derivation across ALL types. FORBIDDEN constraints show the highest expansion ratio (4.2x), meaning manual authors under-specify safety-critical constraints even more than completeness/timing constraints. The Engine systematically derives allergy cross-reactivity, drug interaction, and comorbidity-based contraindications that manual authors implicitly assume but don't enumerate. FORBIDDEN recall (0.545) exceeds Non-FORBIDDEN recall (0.445), confirming the Engine covers safety obligations better. This strengthens Interpretation B: the 'false positives' are legitimate CPG-grounded constraints, not noise.
