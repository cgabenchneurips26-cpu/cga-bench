# W8 Cross-Model Experiment: oss120b Scaffold Comparison

**Date**: 2026-04-19
**Model**: oss120b (Llama-3.1-OSS-120B, TP=2)
**Infrastructure**: 2 servers x 8 GPUs = 16 GPUs, 8 vLLM endpoints
**Scenarios**: 706 (20 core + 5 held-out CPG domains)
**Runs per scenario**: 1 (W8_RUNS=1)

## Completion Status

| Scaffold | Unique Scenarios | Status |
|----------|-----------------|--------|
| react | 706/706 | COMPLETE |
| tooluse | 706/706 | COMPLETE |
| direct | 595/706 (111 remaining) | GAP-FILL IN PROGRESS |
| checklist | 494/706 (212 remaining) | GAP-FILL IN PROGRESS |

## Results Summary (r0 episodes only)

| Scaffold | Episodes | Compliance | Pass% (>=0.5) | Perfect% | C1 Path | C2 Mandatory | C3 Forbidden | C4 Timing | C5 Sequence |
|----------|----------|-----------|---------------|----------|---------|-------------|-------------|-----------|-------------|
| react | 723 | 0.7355 | 90.9% | 1.9% | 0.8519 | 0.9061 | 0.8534 | 0.8997 | 0.9989 |
| **tooluse** | **706** | **0.7959** | **98.2%** | **3.3%** | **0.8522** | **0.9914** | **0.8598** | **0.8989** | **0.9987** |
| direct | 595 | 0.6285 | 82.5% | 0.2% | 0.8618 | 0.7236 | 0.8403 | 0.8748 | 0.9938 |
| checklist | 494 | 0.6504 | 86.4% | 0.2% | 0.8629 | 0.7464 | 0.8866 | 0.8892 | 0.9925 |

## Key Findings

### 1. Tooluse scaffold dominates
- **98.2% pass rate** vs 90.9% (react), 86.4% (checklist), 82.5% (direct)
- **0.7959 compliance** — highest by a significant margin (+0.06 over react)
- Near-perfect C2 mandatory completion: **0.9914** (vs 0.72-0.91 for others)

### 2. Mandatory completion (C2) is the discriminating factor
- tooluse: 0.9914 — virtually all mandatory actions completed
- react: 0.9061 — misses some mandatory actions
- checklist: 0.7464 — significant omission problem
- direct: 0.7236 — worst mandatory completion

### 3. Omission count tells the story
| Scaffold | Omissions | Commissions | Deviations | Timing |
|----------|-----------|-------------|------------|--------|
| tooluse | **40** | 135 | 2,546 | 795 |
| react | 1,007 | 152 | 2,583 | 813 |
| checklist | 1,818 | 83 | 1,683 | 617 |
| direct | 2,347 | 131 | 2,028 | 842 |

Tooluse reduces omissions by **25x** vs react and **59x** vs direct.

### 4. Token efficiency
| Scaffold | Mean Tokens | Mean LLM Calls |
|----------|------------|----------------|
| direct | 13,465 | 8.4 |
| checklist | 23,108 | 12.5 |
| react | 30,663 | 12.4 |
| tooluse | 31,705 | 12.0 |

Direct uses fewest tokens but performs worst — raw efficiency doesn't correlate with quality.

## Infrastructure Optimizations Applied

1. **LLM timeout 60s -> 300s**: Eliminated 20-26 timeouts/runner/30min
2. **W8_RUNS env var fix**: Was hardcoded to 3, now reads env (3x throughput gain)
3. **Auto-transition scripts**: GPU redistribution as scaffolds complete (5-6x aggregate speedup)
4. **Claim file cleanup**: Orphaned claims from crashed runners blocked completion

## Commit
- `01061db4` fix(w8): LLM timeout 60->300s + W8_RUNS env var fix + auto-transition scripts
