================================================================================
EX-2: ARTIFACT OBSERVABILITY LADDER
Episodes: 12379
================================================================================

Mode   Artifact                FORBID    OMIT     SEQ    TIME  Hard-ep  FA rate
------ ---------------------- ------- ------- ------- ------- -------- --------
A      Terminal only                0       0       0       0        0    78.4%
B      Action multiset           1430   54686       0       0     8141    12.6%
C      Ordered actions           1430   54686     244       0     8242    11.8%
D      Timed actions             1430   54686     244    8396     9703     0.0%
E      Full (CGA-Bench)          1430   54686     244    8396     9703     0.0%

## Monotonicity Check
  FA rates: 78.4% → 12.6% → 11.8% → 0.0% → 0.0%
  Monotonically decreasing: ✅ YES

## Detection Gain per Transition
  A→B: FA 78.4%→12.6% (Δ=+65.8pp) new types: {'COMMISSION', 'OMISSION'}
  B→C: FA 12.6%→11.8% (Δ=+0.8pp) new types: {'SEQUENCE'}
  C→D: FA 11.8%→0.0% (Δ=+11.8pp) new types: {'TIMING'}
  D→E: FA 0.0%→0.0% (Δ=+0.0pp) new types: none

## Key Claims for Paper
  1. Terminal-only (A): FA=78.4% — cannot detect ANY structured violations
  2. Action multiset (B): FA=12.6% — catches FORBIDDEN+OMISSION but blind to timing/ordering
  3. Adding order (C): FA drops to 11.8% — SEQUENCE violations now visible
  4. Adding timestamps (D): FA drops to 0.0% — TIMING violations now visible
  5. Full artifact (E): FA=0.0% — all violations detectable
  ★ Gap B→E: 12.6pp — this is what enriched artifacts buy you