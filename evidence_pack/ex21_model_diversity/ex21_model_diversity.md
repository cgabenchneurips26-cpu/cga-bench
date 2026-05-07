# EX-21: Model Diversity — Cross-Family Blind-Spot Persistence

## Summary

- **Diversity models tested**: 1
- **Baseline models**: 7
- **Diversity mean flip rate**: 87.9%
- **Baseline mean flip rate**: 83.5%
- **Diversity mean AO-FA**: 17.5%
- **Baseline mean AO-FA**: 10.7%
- **Conclusion**: Blind spots persist across model families

## Per-Model Results

| Model | Family | N | Flip% | AO-FA% | AC Pass% | MAB Pass% | C2 Pass% | CGA Pass% |
|-------|--------|---|-------|--------|----------|-----------|----------|-----------|
| DeepSeek-R1-7B | diversity | 2118 | 87.9 | 17.5 | 76.3 | 46.2 | 30.1 | 34.9 |
| OpenBioLLM-8B | diversity | 0 | — | — | — | — | — | — |
| Llama4-Scout-17B | diversity | 0 | — | — | — | — | — | — |
| OSS-120B | baseline | 2118 | 82.4 | 14.3 | 85.4 | 50.2 | 40.4 | 46.3 |
| Qwen3.5-35B | baseline | 2118 | 84.1 | 13.0 | 83.5 | 53.6 | 39.4 | 52.7 |
| Qwen3.5-27B | baseline | 2118 | 81.0 | 12.8 | 79.1 | 56.8 | 39.9 | 44.7 |
| Qwen3-4B | baseline | 2118 | 85.3 | 8.6 | 56.9 | 50.9 | 32.1 | 56.3 |
| Qwen3.5-397B | baseline | 2118 | 86.0 | 13.0 | 82.9 | 59.3 | 37.4 | 45.4 |
| Gemma4-31B | baseline | 2118 | 80.0 | 8.7 | 74.2 | 57.5 | 43.3 | 59.8 |
| Nemotron-30B | baseline | 2118 | 85.6 | 4.6 | 56.9 | 49.0 | 22.4 | 56.0 |

## Per-Evaluator False-Accept Rates (among hard-violation episodes)

| Model | N_hard | AC-FA% | MAB-FA% | C2-FA% | CGA-FA% |
|-------|--------|--------|---------|--------|---------|
| DeepSeek-R1-7B | 1378 | 87.3 | 55.8 | 28.6 | 0.0 |
| OSS-120B | 1137 | 90.7 | 52.4 | 30.3 | 0.0 |
| Qwen3.5-35B | 1001 | 90.3 | 58.0 | 32.1 | 0.0 |
| Qwen3.5-27B | 1172 | 79.1 | 67.3 | 28.5 | 0.0 |
| Qwen3-4B | 925 | 70.8 | 71.5 | 28.6 | 0.0 |
| Qwen3.5-397B | 1157 | 90.7 | 71.0 | 27.9 | 0.0 |
| Gemma4-31B | 852 | 84.7 | 63.3 | 31.5 | 0.0 |
| Nemotron-30B | 931 | 76.4 | 69.7 | 13.2 | 0.0 |
