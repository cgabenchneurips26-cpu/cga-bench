# EX-39: AMEGA Cross-Benchmark Evaluation

**Episodes**: 216 (24 AMEGA cases, 7 domain-matched)

## Pass Rates

| Evaluator | Pass Rate |
|-----------|-----------|
| AMEGA-CL | 0.0% |
| AC-Proxy | 8.3% |
| MAB-F1 | 0.0% |
| CwT | 4.6% |
| TCC | 100.0% |

## Pairwise Cohen's Kappa

| Pair | Kappa |
|------|-------|
| AMEGA-CL vs AC-Proxy | 0.000 |
| AMEGA-CL vs MAB-F1 | 1.000 |
| AMEGA-CL vs CwT | 0.000 |
| AMEGA-CL vs TCC | 0.000 |
| AC-Proxy vs MAB-F1 | 0.000 |
| AC-Proxy vs CwT | 0.013 |
| AC-Proxy vs TCC | 0.000 |
| MAB-F1 vs CwT | 0.000 |
| MAB-F1 vs TCC | 0.000 |
| CwT vs TCC | 0.000 |
| **Average** | **0.101** |

## Mis-certification (Evaluator=PASS but TCC=FAIL)

| Evaluator | Count | Rate |
|-----------|-------|------|
| AMEGA-CL | 0 | 0.0% |
| AC-Proxy | 0 | 0.0% |
| MAB-F1 | 0 | 0.0% |
| CwT | 0 | 0.0% |
| **Total** | **0** | **0.0%** |

## Verdict Flip Rate: 100.0%
- Unanimous: 0/216
- Flipped: 216/216

## Domain-Matched Subset (n=63)

| Evaluator | Pass Rate |
|-----------|-----------|
| AMEGA-CL | 0.0% |
| AC-Proxy | 7.9% |
| MAB-F1 | 0.0% |
| CwT | 14.3% |
| TCC | 100.0% |