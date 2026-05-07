# EX-27: Timing Stress Suite

## Overview

Tests whether WITHIN-constraint verdicts are robust to clinically realistic timing models beyond the 5-min fixed step baseline.

## Sub-A: Action-Class Duration Model

- **Baseline violation rate:** 66.04%
- **Duration model violation rate:** 65.66%
- **Verdict flips:** 368 (2.17%)
  - Flip to pass: 216
  - Flip to fail: 152
- **WITHIN violations persisting:** 98.07%
- **WITHIN violations resolved:** 1.93%

## Sub-B: Parallel Batching

- **Baseline violation rate:** 66.04%
- **Parallel model violation rate:** 65.1%
- **Verdict flips:** 463 (2.73%)
  - Flip to pass: 311
  - Flip to fail: 152
- **WITHIN violations resolved:** 2.78%

## Sub-C: Zero Reasoning Cost

- **Baseline violation rate:** 66.04%
- **Zero-reasoning violation rate:** 66.03%
- **Verdict flips:** 2 (0.01%)
  - Flip to pass: 2
  - Flip to fail: 0

## Sub-D: Clock Sweep Cross

| Step (min) | Violation Rate | Flip from Baseline |
|------------|---------------|-------------------|
| 2 | 46.44% | 19.61% |
| 5 (baseline) | 66.04% | 0.0% |
| 10 | 77.01% | 10.97% |
| 15 | 87.65% | 21.61% |
| 20 | 90.0% | 23.96% |

## Interpretation

Under all four clinically motivated timing models, the majority of WITHIN violations persist.  Duration-model (Sub-A) resolves some violations because electronic orders take 2 min instead of 5 min, compressing early-trace timestamps.  Parallel batching (Sub-B) has a similar but smaller effect.  Zero-reasoning (Sub-C) shows the impact of reasoning overhead on timing.  Clock sweep (Sub-D) confirms that violation rates vary monotonically with step size, ruling out non-monotonic artifacts.
