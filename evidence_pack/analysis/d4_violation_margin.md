# D4: Timing Violation Margin Histogram

## Summary

- **Total timing violations**: 115
- **Median margin**: 20.0 min
- **Mean margin**: 40.4 min
- **Max margin**: 145.0 min

## Zone Distribution

| Zone | Threshold | Count | % |
|------|-----------|-------|---|
| Borderline | 0–5 min | 1 | 0.9% |
| Moderate   | 5–15 min | 33 | 28.7% |
| Clear      | >15 min | 81 | 70.4% |

## Per-Model Breakdown

| Model | N violations | Median margin | Borderline | Moderate | Clear |
|-------|-------------|--------------|------------|----------|-------|
| oss120b | 46 | 47.5 min | 0 | 11 | 35 |
| qwen27b | 23 | 20.0 min | 0 | 6 | 17 |
| qwen35b | 23 | 20.0 min | 0 | 11 | 12 |
| qwen4b | 23 | 30.0 min | 1 | 5 | 17 |

## UP Subset (c2 >= 0.7)

- N violations: 86
- Median margin: 20.0 min
- Borderline: 0, Moderate: 28, Clear: 58

## Interpretation

The vast majority of timing violations are in the 'Clear' zone (>15 min late),
indicating these are not borderline cases. The 70% clear rate confirms that timing violations reflect genuine protocol deviations rather than
measurement noise from the 5-min action duration assumption.

## Output Files

- `evidence_pack/figures/timing_margin_histogram.pdf`
- `evidence_pack/figures/timing_margin_histogram.png`
- `evidence_pack/analysis/d4_violation_margin.json`
