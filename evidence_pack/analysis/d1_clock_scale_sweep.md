# D1: Clock Scale Sweep — Results

**Generated**: 2026-04-02T08:37:14.936544+00:00  
**Total episodes**: 180  
**Models**: oss120b, qwen27b, qwen35b, qwen4b  
**Scales tested**: 2, 3, 5, 7, 10, 15, 20 min/turn  
**Default scale**: 5 min/turn  
**Completion-passing threshold**: C2 >= 0.7  

## Motivation

Reviewers may argue that the 5 min/turn clock is arbitrary, and that
choosing a different scale would change which actions appear as timing
violations. This sweep re-scales all action timestamps while keeping
CPG deadlines fixed (they are guideline-specified, not clock-dependent),
and recomputes UP safety rates across the full range 3-15 min/turn.

## Summary Table

| Scale (min/turn) | N_CP | UP_any | UP_strong | UP_crit | Delta_strong vs 5min | Timing viols |
|-----------------|------|--------|-----------|---------|---------------------|-------------|
| 2 | 78 | 59.0% | 25.6% | 11.5% | -2.6pp | 53 |
| 3 | 78 | 62.8% | 28.2% | 12.8% | +0.0pp | 80 |
| 5 (default) | 78 | 64.1% | 28.2% | 12.8% | — | 87 |
| 7 | 78 | 70.5% | 35.9% | 20.5% | +7.7pp | 105 |
| 10 | 78 | 70.5% | 35.9% | 20.5% | +7.7pp | 113 |
| 15 | 78 | 70.5% | 35.9% | 20.5% | +7.7pp | 113 |
| 20 | 78 | 70.5% | 43.6% | 28.2% | +15.4pp | 119 |

## Per-Model Breakdown at Each Scale

### Scale = 2 min/turn

N_CP = 78 / 180 total episodes, timing violations = 53

| Model | N_CP | UP_any | UP_strong | UP_crit |
|-------|------|--------|-----------|---------|
| DeepSeek-V3 (120B) | 22 | 59.1% | 31.8% | 22.7% |
| R1-Distill (27B) | 21 | 61.9% | 19.0% | 4.8% |
| Qwen3.5 (35B) | 20 | 60.0% | 15.0% | 0.0% |
| Qwen3 (4B) | 15 | 53.3% | 40.0% | 20.0% |

### Scale = 3 min/turn

N_CP = 78 / 180 total episodes, timing violations = 80

| Model | N_CP | UP_any | UP_strong | UP_crit |
|-------|------|--------|-----------|---------|
| DeepSeek-V3 (120B) | 22 | 63.6% | 31.8% | 22.7% |
| R1-Distill (27B) | 21 | 71.4% | 28.6% | 9.5% |
| Qwen3.5 (35B) | 20 | 60.0% | 15.0% | 0.0% |
| Qwen3 (4B) | 15 | 53.3% | 40.0% | 20.0% |

### Scale = 5 min/turn (default)

N_CP = 78 / 180 total episodes, timing violations = 87

| Model | N_CP | UP_any | UP_strong | UP_crit |
|-------|------|--------|-----------|---------|
| DeepSeek-V3 (120B) | 22 | 63.6% | 31.8% | 22.7% |
| R1-Distill (27B) | 21 | 71.4% | 28.6% | 9.5% |
| Qwen3.5 (35B) | 20 | 65.0% | 15.0% | 0.0% |
| Qwen3 (4B) | 15 | 53.3% | 40.0% | 20.0% |

### Scale = 7 min/turn

N_CP = 78 / 180 total episodes, timing violations = 105

| Model | N_CP | UP_any | UP_strong | UP_crit |
|-------|------|--------|-----------|---------|
| DeepSeek-V3 (120B) | 22 | 77.3% | 45.5% | 36.4% |
| R1-Distill (27B) | 21 | 71.4% | 28.6% | 9.5% |
| Qwen3.5 (35B) | 20 | 75.0% | 30.0% | 15.0% |
| Qwen3 (4B) | 15 | 53.3% | 40.0% | 20.0% |

### Scale = 10 min/turn

N_CP = 78 / 180 total episodes, timing violations = 113

| Model | N_CP | UP_any | UP_strong | UP_crit |
|-------|------|--------|-----------|---------|
| DeepSeek-V3 (120B) | 22 | 77.3% | 45.5% | 36.4% |
| R1-Distill (27B) | 21 | 71.4% | 28.6% | 9.5% |
| Qwen3.5 (35B) | 20 | 75.0% | 30.0% | 15.0% |
| Qwen3 (4B) | 15 | 53.3% | 40.0% | 20.0% |

### Scale = 15 min/turn

N_CP = 78 / 180 total episodes, timing violations = 113

| Model | N_CP | UP_any | UP_strong | UP_crit |
|-------|------|--------|-----------|---------|
| DeepSeek-V3 (120B) | 22 | 77.3% | 45.5% | 36.4% |
| R1-Distill (27B) | 21 | 71.4% | 28.6% | 9.5% |
| Qwen3.5 (35B) | 20 | 75.0% | 30.0% | 15.0% |
| Qwen3 (4B) | 15 | 53.3% | 40.0% | 20.0% |

### Scale = 20 min/turn

N_CP = 78 / 180 total episodes, timing violations = 119

| Model | N_CP | UP_any | UP_strong | UP_crit |
|-------|------|--------|-----------|---------|
| DeepSeek-V3 (120B) | 22 | 77.3% | 45.5% | 36.4% |
| R1-Distill (27B) | 21 | 71.4% | 42.9% | 23.8% |
| Qwen3.5 (35B) | 20 | 75.0% | 45.0% | 30.0% |
| Qwen3 (4B) | 15 | 53.3% | 40.0% | 20.0% |

## Key Claims

1. **UP_strong range**: 25.6% - 43.6% across scales 3-15 min/turn (range = 18.0 pp).

2. **Direction**: At faster scales (3 min/turn), actions happen earlier and fewer timing violations occur (conservative direction). At slower scales (15 min/turn), more timing violations accumulate.

3. **Robustness**: Commission and sequence violations are entirely unaffected by the clock scale; only timing violations vary.

4. **Guideline-anchored deadlines**: All deadlines are sourced from ACC/AHA/SSC/ADA/KDIGO/ESC guidelines and remain fixed across all scales.
