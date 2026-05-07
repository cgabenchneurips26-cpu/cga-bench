# E9 Follow-up G1 -- Safety-Core Overlay

Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (SS A)

## Headline

Of the **1124** S1 strict-FA episodes, **144** (12.8%) contain at least one FORBIDDEN or BEFORE violation (safety-core; Wilson 95% CI [11.0%, 14.9%]). Under the strictest taxonomy (S2) this collapses to **4** episodes (-140, -97.2%).

## S1 / S2 side-by-side

| Metric | S1 (default high-authority) | S2 (strictest, Class I+A) |
|---|---|---|
| Strict-FA total | 1124 | 548 |
| Safety-core (FORBIDDEN or BEFORE) | **144** | **4** |
| MUST-only (WITHIN / empty) | 980 | 544 |
| Safety-core % | 12.8% | 0.7% |
| Wilson 95% CI | [11.0%, 14.9%] | [0.3%, 1.9%] |
| MAB replay-loss (safety-core) | 41.2% | 41.2% |
| AC replay-loss (safety-core) | 78.5% | 78.5% |

## S1 Family breakdown (safety-core only)

| Family | Count | Description |
|---|---|---|
| forbid_only | 139 | FORBIDDEN only, no BEFORE, no WITHIN |
| before_only | 0 | BEFORE only, no FORBIDDEN, no WITHIN |
| forbid_within | 5 | FORBIDDEN + WITHIN (mixed) |
| before_within | 0 | BEFORE + WITHIN (mixed) |
| forbid_before | 0 | FORBIDDEN + BEFORE, no WITHIN |
| forbid_before_within | 0 | FORBIDDEN + BEFORE + WITHIN |

## S2 Family breakdown (safety-core only)

| Family | Count |
|---|---|
| forbid_only | 0 |
| before_only | 0 |
| forbid_within | 4 |
| before_within | 0 |
| forbid_before | 0 |
| forbid_before_within | 0 |

## Replay-loss detail (S1)

Among all TCC-fail safety-core episodes under S1 (n=2053), the MAB proxy still called PASS in **41.2%** of cases and the AC proxy in **78.5%** of cases.

## S1->S2 Collapse (strictness gradient)

S1 safety-core: 144 -> S2: 4 (-140, **-97.2%**). Reported as strictness-gradient meta-finding; S2 n=4 is below the n>=30 per-stratum threshold and is cited as a boundary note only.

## Gate verdict

S1 safety-core n=144 >= 30 threshold: **PASS**
S2 safety-core n=4 < 30: boundary note only (not primary claim).
