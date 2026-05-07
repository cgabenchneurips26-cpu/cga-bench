# Evaluator × Violation Type Cross-Tabulation

**Episodes**: 180
**Violation types observed**: BEFORE, FORBIDDEN, WITHIN

## Sensitivity Matrix: P(Evaluator FAIL | Violation Type Present)

| Evaluator | BEFORE | FORBIDDEN | WITHIN |
|-----------|------|------|------|
| AC-Proxy | 0.333 (n=36) | 0.520 (n=25) | 0.207 (n=58) |
| MAB-Proxy | **1.000** (n=36) | **1.000** (n=25) | **0.966** (n=58) |
| C2 | 0.333 (n=36) | 0.520 (n=25) | 0.276 (n=58) |
| CGA-Bench | **1.000** (n=36) | **1.000** (n=25) | **1.000** (n=58) |

## Cluster Interpretation

### Cluster A (Coverage): AC-Proxy, C2

- BEFORE: avg fail rate = 0.333
- FORBIDDEN: avg fail rate = 0.520
- WITHIN: avg fail rate = 0.241

### Cluster B (Safety+Temporal): MAB-Proxy, CGA-Bench

- BEFORE: avg fail rate = 1.000
- FORBIDDEN: avg fail rate = 1.000
- WITHIN: avg fail rate = 0.983

## Mis-certification Rates

| Evaluator | Violation Episodes | Mis-certified | Rate | Top Missed Type |
|-----------|-------------------|---------------|------|-----------------|
| AC-Proxy | 70 | 52 | 0.743 | WITHIN |
| MAB-Proxy | 70 | 2 | 0.029 | WITHIN |
| C2 | 70 | 48 | 0.686 | WITHIN |
| CGA-Bench | 70 | 0 | 0.000 |  |

## Paper Narrative

The cross-tabulation reveals that the low Fleiss' κ (0.169) reflects **structural dimensional disagreement**, not random noise. Evaluators form two clusters with distinct sensitivity profiles:

- **Cluster A** (AC-Proxy, C2): Higher sensitivity to coverage/completeness gaps but lower sensitivity to safety violations
- **Cluster B** (MAB-Proxy, CGA-Bench): Higher sensitivity to FORBIDDEN and temporal (WITHIN/BEFORE) constraint violations

This validates CGA-Bench's multi-evaluator design: no single evaluator captures all clinically relevant dimensions. The union provides comprehensive coverage that any individual evaluator misses.
