# Composite Metric Analysis

## Problem: CGA rewards conservative behavior

4B (9 actions, 85% efficiency) → CGA 74.8%
120B (23 actions, 31% efficiency) → CGA 66.4%

## Solution: CGA × Coverage

| Model | Params | CGA | Coverage | Comp_A | Behavior |
|-------|--------|-----|----------|--------|----------|
| oss-120b | 120B | 66.4% | 0.94 | 62.0% | Ambitious |
| Qwen3.5-35B | 35B | 65.7% | 0.91 | 58.3% | Balanced |
| oss-20b | 20B | 66.7% | 0.91 | 59.7% | Balanced |
| Qwen3-4B | 4B | 74.8% | 0.66 | 47.4% | Conservative |


## Friedman Tests
- CGA: p=... (check above)
- Composite A: p=... (check above)

## Ranking
- CGA: Qwen3-4B > oss-20b > oss-120b > Qwen3.5-35B
- Composite: oss-120b > oss-20b > Qwen3.5-35B > Qwen3-4B
- **Flip: YES**