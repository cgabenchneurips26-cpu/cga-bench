# EX-15: Constraint-Type Ablation (Corrected)

## Key Result: Pass Rate Gap

| Mode | Constraints | Pass Rate |
|------|------------|-----------|
| TCC-full | MUST+FORBIDDEN+BEFORE+WITHIN | 21.4% |
| TCC-noTiming | MUST+FORBIDDEN+BEFORE | 32.5% |
| TCC-noOrder | MUST+FORBIDDEN+WITHIN | 21.4% |
| TCC-actionOnly | MUST+FORBIDDEN | 33.1% |

Gap: TCC-actionOnly (33.1%) → TCC-full (21.4%) = **11.7pp**
1,863 episodes (11.8%) fail ONLY due to TIMING/SEQUENCE constraints.
  - TIMING violations: 3,433
  - SEQUENCE violations: 101

## Interpretation

TIMING is the dominant contributor (noTiming 32.5% → full 21.4% = 11.1pp).
SEQUENCE contributes marginally (noOrder 21.4% = full 21.4%).

"Removing temporal constraints from TCC increases its pass rate by 11.7pp,
closing 1,863 episodes. This dimensional contribution — not a scoring
idiosyncrasy — explains the evaluator disagreement."

## Note on κ comparison

κ(TCC-actionOnly, ASC) = 0.042 is misleadingly low because ASC uses
coverage ≥ 0.5 (tolerates 50% omission) while TCC uses any-omission = fail.
This is a threshold difference, not an observability difference.
The valid comparison is within-TCC ablation (pass rate gap).
