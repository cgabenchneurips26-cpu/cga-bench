# EXP-E3: Instrumentation Ablation

**Total episodes:** 16944

## Condition Summaries

| Condition | N Hard | Hard Rate | BSR(DxEM) | BSR(AC) | BSR(MAB) | BSR(C2) | BSR(ACov) |
|-----------|--------|-----------|-----------|---------|----------|---------|-----------|
| Full | 8553 | 0.505 | 0.505 | 0.424 | 0.294 | 0.114 | 0.424 |
| -Timestamps | 1632 | 0.096 | 0.096 | 0.073 | 0.039 | 0.018 | 0.073 |
| -Ordering | 8514 | 0.502 | 0.502 | 0.422 | 0.292 | 0.114 | 0.422 |
| -State | 8238 | 0.486 | 0.486 | 0.411 | 0.285 | 0.104 | 0.411 |
| -All (Terminal) | 0 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 | 0.000 |

## Violation Loss vs. Full Condition

| Condition | FORBIDDEN Lost | WITHIN Lost | BEFORE Lost |
|-----------|----------------|-------------|-------------|
| -Timestamps | 0 | 14989 | 283 |
| -Ordering | 0 | 0 | 283 |
| -State | 2141 | 0 | 0 |
| -All (Terminal) | 2141 | 14989 | 283 |

## McNemar Tests (v4-hard detection)

| Condition A | Condition B | b | c | chi2 | p |
|-------------|-------------|---|---|------|---|
| Full | -Timestamps | 6921 | 0 | 6921.000 | 0.00e+00 * |
| Full | -Ordering | 39 | 0 | 39.000 | 4.24e-10 * |
| Full | -State | 315 | 0 | 315.000 | 1.78e-70 * |
| Full | -All (Terminal) | 8553 | 0 | 8553.000 | 0.00e+00 * |
| -Timestamps | -Ordering | 0 | 6882 | 6882.000 | 0.00e+00 * |
| -Timestamps | -State | 315 | 6921 | 6030.851 | 0.00e+00 * |
| -Timestamps | -All (Terminal) | 1632 | 0 | 1632.000 | 0.00e+00 * |
| -Ordering | -State | 315 | 39 | 215.186 | 1.01e-48 * |
| -Ordering | -All (Terminal) | 8514 | 0 | 8514.000 | 0.00e+00 * |
| -State | -All (Terminal) | 8238 | 0 | 8238.000 | 0.00e+00 * |

---

**Finding:** Richer scorers cannot compensate for artifacts that lack observable events. Removing timestamps eliminates WITHIN and BEFORE violations; removing state removes FORBIDDEN detection. Only the Full condition preserves complete constraint observability.
