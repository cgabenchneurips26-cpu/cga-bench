# EX-1 Three-Judge Inter-Reliability Analysis

## Setup
- **500 episodes** (stratified: 250 TCC-fail, 150 TCC-pass, 100 borderline)
- **4 artifact levels**: T0 (diagnosis only) → T3 (full trace + timestamps)
- **3 prompt variants**: P1 (strict PASS/FAIL), P2 (attending YES/NO), P3 (1-5 scale)
- **3 judge models** from different families:
  - qwen35b: Qwen/Qwen3.5-35B-A3B-FP8
  - gemma31b: google/gemma-4-31b-it
  - nemotron30b: nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8

## P1 (Strict PASS/FAIL) — Most Clinically Relevant

| Level | qwen35b FA% | gemma31b FA% | nemotron30b FA% | Range |
|-------|-------------|-------------|-----------------|-------|
| T0    | 0.4         | 2.6         | 0.6             | 2.2pp |
| T1    | 16.8        | 18.8        | 30.8            | 14.0pp |
| T2    | 21.8        | 39.4        | 31.4            | 17.6pp |
| T3    | 4.4         | 29.0        | 4.4             | 24.6pp |
| **T2→T3 Δ** | **17.4pp** | **10.4pp** | **27.0pp** | — |

## P2 (Attending YES/NO)

| Level | qwen35b FA% | gemma31b FA% | nemotron30b FA% | Range |
|-------|-------------|-------------|-----------------|-------|
| T0    | 4.2         | 45.4        | 8.2             | 41.2pp |
| T1    | 11.2        | 52.8        | 38.0            | 41.6pp |
| T2    | 13.6        | 43.4        | 54.0            | 40.4pp |
| T3    | 2.6         | 26.4        | 21.6            | 23.8pp |
| **T2→T3 Δ** | **11.0pp** | **17.0pp** | **32.4pp** | — |

## P3 (1-5 Scale) — Note: highly susceptible to anchoring

| Level | qwen35b FA% | gemma31b FA% | nemotron30b FA% | Range |
|-------|-------------|-------------|-----------------|-------|
| T0    | 1.0         | 49.7        | 67.7            | 66.7pp |
| T1    | 48.6        | 32.6        | 68.2            | 35.6pp |
| T2    | 56.6        | 44.2        | 68.2            | 24.0pp |
| T3    | 48.6        | 22.4        | 67.0            | 44.6pp |
| **T2→T3 Δ** | **8.0pp** | **21.8pp** | **1.2pp** | — |

Note: nemotron30b P3 is near-degenerate (67-68% FA across all levels).

## Aggregate FA (across all prompts)

| Level | qwen35b | gemma31b | nemotron30b | Range |
|-------|---------|----------|-------------|-------|
| T0    | 1.9%    | 32.1%    | 25.4%       | 30.2pp |
| T1    | 25.5%   | 34.7%    | 45.7%       | 20.2pp |
| T2    | 30.7%   | 42.3%    | 51.2%       | 20.5pp |
| T3    | 18.5%   | 25.9%    | 31.0%       | 12.5pp |
| **T2→T3 Δ** | **12.2pp** | **16.4pp** | **20.2pp** | — |

## Key Findings

### Finding 1: T2→T3 Gap Is Universal
All 3 judges show FA reduction from T2 to T3 across ALL prompt variants (9/9 combinations).
- P1: 17.4pp, 10.4pp, 27.0pp (all positive)
- P2: 11.0pp, 17.0pp, 32.4pp (all positive)
- Aggregate: 12.2pp, 16.4pp, 20.2pp

**Conclusion**: Temporal observability improves LLM judge accuracy regardless of model family. This is a model-independent structural finding.

### Finding 2: Inter-Judge Variance Is Enormous
At T3/P1 (best conditions): qwen35b=4.4%, nemotron30b=4.4%, gemma31b=29.0%
- Two judges agree perfectly (4.4%) while the third is 6.6× higher
- At T2/P2: range is 40.4pp (13.6% vs 54.0%)

**Conclusion**: Even with identical input (same 500 episodes, same prompt, same artifact level), LLM judges produce wildly inconsistent FA rates. This inter-judge variance independently motivates deterministic constraint checking.

### Finding 3: Dual Conclusion (Paper Narrative)
> "Despite an 18–25pp gap in absolute FA between judges, the T2→T3 reduction is
> consistent (10.4–27.0pp for P1, 11.0–32.4pp for P2), confirming that the
> temporal-observability effect is robust across judge models.
> The large inter-judge variance (24.6pp at T3/P1) independently motivates
> deterministic constraint checking over probabilistic LLM judgment."

### Finding 4: Prompt Sensitivity Compounds Judge Variance
P3 (1-5 scale) is nearly degenerate for nemotron30b (67% FA regardless of artifact level).
This demonstrates that LLM-based evaluation suffers from BOTH model variance AND prompt variance,
creating a combinatorial reliability problem that deterministic TCC avoids entirely.
