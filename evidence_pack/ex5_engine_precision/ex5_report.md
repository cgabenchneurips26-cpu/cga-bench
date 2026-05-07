======================================================================
EX-5: ENGINE PRECISION TAXONOMY
======================================================================

## 3-Level Precision
  Level 1 (Raw Structural):    21.7%  — engine constraints matching manual
  Level 2 (Corrected):         62.3%  — ≥1 model performs the action
  Level 3 (Verdict-Relevant):   3.6pp  — additional hard-viol rate from engine constraints

## Hard Violation Rate
  Manual scenarios: 75.2% (1766/2348)
  Auto scenarios:   78.8% (8735/11089)
  Newly exposed:    +3.6pp

## Violation Type Breakdown
  Type              Manual     Auto    Delta
  OMISSION           2.33/ep    4.82/ep   +2.49
  COMMISSION         0.17/ep    0.10/ep   -0.07
  TIMING             0.90/ep    0.67/ep   -0.23
  SEQUENCE           0.01/ep    0.02/ep   +0.01

## Paper Claims
  1. Raw precision (21.7%) is low because manual is under-specified
  2. Corrected precision (62.3%) shows most engine constraints are actionable
  3. Engine constraints expose 3.6pp additional hard violations