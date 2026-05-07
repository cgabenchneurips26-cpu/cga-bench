# EX-4A: Clock Sweep — Timing Constraint Robustness

**Episodes**: 16944
**Baseline step**: 5 min
**Step sizes tested**: [2, 5, 10, 15, 20]
**Max verdict flip**: 24.0%

## Sweep Results

| Step (min) | WITHIN Viol (%) | Flip vs Baseline (%) | N Violations | N Flips |
|------------|-----------------|---------------------|--------------|---------|
| 2 | 46.44 | 19.61 | 7868 | 3322 |
| 5 * | 66.04 | 0.0 | 11190 | 0 |
| 10 | 77.01 | 10.97 | 13049 | 1859 |
| 15 | 87.65 | 21.61 | 14852 | 3662 |
| 20 | 90.0 | 23.96 | 15249 | 4059 |

## Interpretation

If the max flip rate is low (<15%), the WITHIN-constraint verdicts are robust
to clock granularity and the timing signal is NOT a clock artifact.

## auto_numbers

- `\clockSweepMaxFlip` = 24.0
- `\clockSweepSteps` = 5
- `\clockSweepBaseline` = 5
- `\clockSweepN` = 16944
