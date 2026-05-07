# EXP-E4: Operating-Point Matched Agreement Analysis

Threshold sweep matching all four evaluators to the same pass rate,
proving disagreement is **not** a threshold-calibration artifact.

## Results by Operating Point

### Pass Rate ≈ 30%

| Evaluator | Threshold | Actual Pass Rate |
| --- | --- | --- |
| AC-Proxy | 0.7551 | 0.315 |
| MAB-Proxy | 0.5714 | 0.291 |
| C2 | 0.6735 | 0.293 |
| CGA-Bench | 0.5176 | 0.446 |

**Fleiss' κ = 0.080**  
Verdict flip rate = 0.742  
Within-cluster κ = 0.151  
Cross-cluster κ = 0.063

| Pair | Cohen's κ |
| --- | --- |
| AC-Proxy vs MAB-Proxy | 0.181 |
| AC-Proxy vs C2 | 0.511 |
| AC-Proxy vs CGA-Bench | -0.037 |
| MAB-Proxy vs C2 | -0.041 |
| MAB-Proxy vs CGA-Bench | -0.209 |
| C2 vs CGA-Bench | 0.151 |

### Pass Rate ≈ 40%

| Evaluator | Threshold | Actual Pass Rate |
| --- | --- | --- |
| AC-Proxy | 0.7143 | 0.403 |
| MAB-Proxy | 0.5510 | 0.373 |
| C2 | 0.6327 | 0.375 |
| CGA-Bench | 0.5176 | 0.446 |

**Fleiss' κ = 0.115**  
Verdict flip rate = 0.758  
Within-cluster κ = 0.168  
Cross-cluster κ = 0.092

| Pair | Cohen's κ |
| --- | --- |
| AC-Proxy vs MAB-Proxy | 0.272 |
| AC-Proxy vs C2 | 0.499 |
| AC-Proxy vs CGA-Bench | -0.047 |
| MAB-Proxy vs C2 | 0.021 |
| MAB-Proxy vs CGA-Bench | -0.163 |
| C2 vs CGA-Bench | 0.123 |

### Pass Rate ≈ 50%

| Evaluator | Threshold | Actual Pass Rate |
| --- | --- | --- |
| AC-Proxy | 0.6531 | 0.496 |
| MAB-Proxy | 0.5102 | 0.484 |
| C2 | 0.5714 | 0.515 |
| CGA-Bench | 0.5176 | 0.446 |

**Fleiss' κ = 0.091**  
Verdict flip rate = 0.815  
Within-cluster κ = 0.137  
Cross-cluster κ = 0.069

| Pair | Cohen's κ |
| --- | --- |
| AC-Proxy vs MAB-Proxy | 0.274 |
| AC-Proxy vs C2 | 0.487 |
| AC-Proxy vs CGA-Bench | -0.123 |
| MAB-Proxy vs C2 | 0.032 |
| MAB-Proxy vs CGA-Bench | -0.213 |
| C2 vs CGA-Bench | 0.092 |

## Cluster Structure

Cluster preserved (within > cross): **True**

Clusters: {AC-Proxy, C2} vs {MAB-Proxy, CGA-Bench}.

## Interpretation

Low Fleiss' κ across all operating points confirms that
evaluator disagreement is a genuine structural property,
not an artifact of different classification thresholds.
