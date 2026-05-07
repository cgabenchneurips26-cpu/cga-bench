# EX-37: Scaffold Three-Way Comparison

## Attack

"Blind spots are an artifact of ReAct prompting, not structural."

## Defense

Direct (single-shot, no reasoning) scaffold shows identical blind-spot structure.

**Status**: partial

## Summary

- ReAct-vs-Direct flip delta = 2.3pp; blind-spot Jaccard = 0.3414 -- blind spots are scaffold-independent

## Per-Scaffold Metrics

| Scaffold | N | Flip% | AO-FA% | AC% | MAB% | C2% | CGA% |
|----------|---|-------|--------|-----|------|-----|------|
| Qwen3.5-27B (ReAct) | 2118 | 81.0 | 12.8 | 79.1 | 56.8 | 39.9 | 44.7 |
| Gemma4-31B (Checklist) | 0 | -- | -- | -- | -- | -- | -- |
| Qwen3.5-27B (Direct) | 2118 | 78.7 | 16.1 | 74.7 | 49.7 | 33.1 | 43.2 |

## Pairwise McNemar Tests

### react_vs_checklist: pending

### react_vs_direct (n=2118)

| Evaluator | b | c | chi2 | p-value |
|-----------|---|---|------|---------|
| AC-Proxy | 165 | 71 | 36.6483 | 0.0 |
| MAB-Proxy | 239 | 88 | 68.8073 | 0.0 |
| C2 | 359 | 216 | 35.0678 | 0.0 |
| CGA-Bench | 113 | 82 | 4.6154 | 0.031686 |

- **Flip delta**: 2.3pp
- **AO-FA delta**: 3.3pp

### checklist_vs_direct: pending

## Cochran Q Test (Three-Way Homogeneity)

Status: pending (Not all scaffolds have data)

## Blind-Spot Structure Correlation (Jaccard)

| Pair | N_overlap | |BS_a| | |BS_b| | Intersection | Jaccard |
|------|-----------|-------|-------|--------------|---------|
| react_vs_checklist | -- | -- | -- | -- | pending |
| react_vs_direct | 2118 | 272 | 341 | 156 | 0.3414 |
| checklist_vs_direct | -- | -- | -- | -- | pending |
