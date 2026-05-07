# D3: Action Duration Sensitivity Analysis

## Summary

- **Total episodes analyzed**: 180 (rescored)
- **Reference timing violations** (Uniform 5min): 90

## Results by Duration Model

| Model | Description | Total Timing | % of Ref | UP Timing | UP Strong | UP Crit |
|-------|-------------|-------------|----------|-----------|-----------|---------|
| uniform_5min | Uniform 5min (current default) | 90 | 100.0% | 64 | 15 | 0 |
| class_based | Class-based (action type) | 81 | 90.0% | 60 | 15 | 0 |
| fast_2min | Fast 2min (lower bound) | 75 | 83.3% | 56 | 13 | 0 |
| slow_10min | Slow 10min (upper bound) | 96 | 106.7% | 67 | 18 | 0 |

## Robustness Assessment

- Timing violation count ranges from **75** (fast) to **96** (slow) across all duration models.
- Reference (Uniform 5min): **90** violations.
- Range: 83.3%–106.7% of reference count, indicating timing results are robust to duration assumptions.

## Action Class Duration Table

| Prefix | Duration (min) | Rationale |
|--------|---------------|-----------|
| order_lab | 1 | Electronic order |
| order_imaging | 2 | Electronic order + confirmation |
| give_iv | 3 | IV setup |
| give | 5 | Preparation + administration |
| start_vasopressor | 5 | Setup + titration |
| consult | 2 | Request |
| assess | 5 | Physical exam/assessment |
| monitor | 3 | Setup monitoring |
| activate | 2 | Activate lab/team |
| default | 5 | Fallback |

## Interpretation

Timing violations persist robustly across all four duration models,
confirming that findings are not an artifact of the uniform 5-minute
assumption used as the default in the CGA-Bench evaluation pipeline.
