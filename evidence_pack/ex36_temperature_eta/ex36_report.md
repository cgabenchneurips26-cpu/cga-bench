# EX-36: Temperature Sensitivity -- eta-squared Decomposition

**Status**: complete

## Attack

> T=0.1 makes run variance trivially zero. Evaluator >> run is a tautology.

## Defense

> eta-squared(evaluator) >> eta-squared(run) even at T=0.6 with real run variance.

## eta-squared Decomposition

| Temperature | eta-sq(eval) | eta-sq(run) | eta-sq(resid) | Dominance Ratio |
|------------|--------------|-------------|---------------|-----------------|
| T=0.1 | 0.1806 | 0.0001 | 0.8194 | 3153.5 |
| T=0.6 | 0.2823 | 0.0000 | 0.7177 | 34942.2 |

## Agreement Metrics

| Temperature | N | Flip% | 3/3 Agree% | FA% |
|------------|---|-------|-----------|-----|
| T=0.1 | 2118 | 80.1 | 84.3 | 28.7 |
| T=0.6 | 1870 | 86.5 | 88.1 | 39.4 |

