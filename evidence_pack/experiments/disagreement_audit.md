# Experiment C: Disagreement Audit (4-Quadrant)

## 4-Quadrant Matrix

CGA Threshold: 70%

|                  | CGA PASS | CGA FAIL |
|------------------|----------|----------|
| **Task PASS**    | Q1: 21 | Q2: 28 |
| **Task FAIL**    | Q3: 7 | Q4: 17 |

Total episodes: 73

## Q2 Analysis (Task PASS / CGA FAIL)

- Total Q2: 28
- Naturally occurring: 11
- From perturbation: 17

### Failure Mode Breakdown

| Mode | Count |
|------|-------|
| mixed | 10 |
| overaction | 2 |
| safety | 8 |
| sequence | 2 |
| timing | 6 |

## Q3 Analysis (Task FAIL / CGA PASS)

- Total Q3: 7
- Interpretation: CGA recognizes process quality independent of outcome

## Threshold Sensitivity

| Threshold | Q1 | Q2 | Q3 | Q4 |
|-----------|----|----|----|----|
| 50% | 33 | 16 | 15 | 9 |
| 60% | 25 | 24 | 11 | 13 |
| 70% | 21 | 28 | 7 | 17 |
| 80% | 20 | 29 | 4 | 20 |

## By Scenario

| Scenario | Q1 | Q2 | Q3 | Q4 |
|----------|----|----|----|----|
| aki_stage1_basic | 2 | 4 | 0 | 3 |
| contrast_aki_prevention_basic | 4 | 1 | 0 | 4 |
| dka_hypokalemia_trap | 2 | 2 | 2 | 3 |
| dka_moderate_basic | 2 | 2 | 2 | 4 |
| septic_shock_basic | 3 | 5 | 1 | 0 |
| septic_shock_penicillin_allergy | 3 | 5 | 0 | 1 |
| stemi_inferior_rv_trap | 3 | 6 | 0 | 0 |
| stroke_tpa_eligible | 2 | 3 | 2 | 2 |