# W8 Cross-Model Experiment: 3-Model × 4-Scaffold Analysis

**Date**: 2026-04-20 (completed)
**Models**: oss120b, qwen35b, gemma31b
**Scaffolds**: react, direct, checklist, tooluse
**Scenarios**: 706 per cell
**Total episodes**: 8,472 (12 cells × 706)

## Completion Status — ALL COMPLETE

| Model | react | direct | checklist | tooluse |
|-------|-------|--------|-----------|---------|
| oss120b | 706/706 ✅ | 706/706 ✅ | 706/706 ✅ | 706/706 ✅ |
| qwen35b | 706/706 ✅ | 706/706 ✅ | 706/706 ✅ | 706/706 ✅ |
| gemma31b | 706/706 ✅ | 706/706 ✅ | 706/706 ✅ | 706/706 ✅ |

---

## Final Verdict Matrix

| Model | Scaffold | Comply | Pass% |
|-------|----------|--------|-------|
| **oss120b** | **tooluse** | **0.796** | **98.3** |
| oss120b | react | 0.761 | 94.6 |
| oss120b | checklist | 0.705 | 89.8 |
| oss120b | direct | 0.668 | 86.8 |
| **qwen35b** | **react** | **0.688** | **89.1** |
| qwen35b | checklist | 0.651 | 87.1 |
| qwen35b | direct | 0.634 | 82.0 |
| qwen35b | tooluse | 0.594 | 76.2 |
| **gemma31b** | **tooluse** | **0.652** | **86.1** |
| gemma31b | react | 0.587 | 72.5 |
| gemma31b | checklist | 0.569 | 63.5 |
| gemma31b | direct | 0.539 | 57.2 |

### By Model (averaged across scaffolds)
| Model | Avg Comply | Avg Pass% | Best Scaffold |
|-------|-----------|----------|---------------|
| oss120b (120B) | 0.733 | 92.4% | tooluse |
| qwen35b (35B) | 0.642 | 83.6% | react |
| gemma31b (31B) | 0.587 | 69.8% | tooluse |

### By Scaffold (averaged across models)
| Scaffold | Avg Comply | Avg Pass% |
|----------|-----------|----------|
| tooluse | 0.681 | 86.9% |
| react | 0.679 | 85.4% |
| checklist | 0.642 | 80.1% |
| direct | 0.614 | 75.3% |

---

## Results: oss120b (120B params)

| Scaffold | Comply | Pass% | C1 | C2 | C3 | C4 | C5 | Omissions | Actions |
|----------|--------|-------|----|----|----|----|----|-----------| --------|
| **tooluse** | **0.796** | **98.3** | 0.852 | **0.991** | 0.860 | 0.899 | 0.999 | **40** | 24.0 |
| react | 0.761 | 94.6 | 0.852 | 0.906 | 0.853 | 0.900 | 0.999 | 1,007 | 23.7 |
| checklist | 0.705 | 89.8 | 0.863 | 0.746 | 0.887 | 0.889 | 0.993 | 1,818 | 24.1 |
| direct | 0.668 | 86.8 | 0.862 | 0.724 | 0.840 | 0.875 | 0.994 | 2,347 | 24.0 |

## Results: qwen35b (35B params)

| Scaffold | Comply | Pass% | C1 | C2 | C3 | C4 | C5 | Omissions | Actions |
|----------|--------|-------|----|----|----|----|----|-----------| --------|
| **react** | **0.688** | **89.1** | 0.877 | 0.705 | 0.874 | 0.903 | 1.000 | 2,857 | 22.6 |
| checklist | 0.651 | 87.1 | 0.879 | 0.722 | 0.824 | 0.908 | 0.998 | 2,821 | 23.5 |
| direct | 0.634 | 82.0 | 0.882 | 0.713 | 0.837 | 0.896 | 0.994 | 2,866 | 22.4 |
| tooluse | 0.594 | 76.2 | **0.974** | 0.616 | **0.997** | 0.984 | 0.998 | 3,011 | **5.3** |

## Results: gemma31b (31B params)

| Scaffold | Comply | Pass% | C1 | C2 | C3 | C4 | C5 | Omissions | Actions |
|----------|--------|-------|----|----|----|----|----|-----------| --------|
| **tooluse** | **0.652** | **86.1** | 0.854 | **0.733** | 0.863 | 0.907 | 1.000 | 2,705 | 23.8 |
| react | 0.587 | 72.5 | 0.886 | 0.657 | 0.888 | 0.919 | 1.000 | 3,490 | 19.2 |
| checklist | 0.569 | 63.5 | 0.883 | 0.666 | 0.873 | 0.912 | 1.000 | 3,368 | 19.7 |
| direct | 0.539 | 57.2 | 0.888 | 0.649 | 0.887 | 0.900 | 1.000 | 3,540 | 18.0 |

---

## Key Findings

### 1. Model size dominates scaffold choice
| Model | Best Scaffold | Compliance | Pass% |
|-------|--------------|-----------|-------|
| oss120b (120B) | tooluse | 0.796 | 98.3% |
| qwen35b (35B) | react | 0.688 | 89.1% |
| gemma31b (31B) | tooluse | 0.652 | 86.1% |

oss120b >> qwen35b > gemma31b. The 120B model's advantage is massive (+0.09 over qwen35b, +0.15 over gemma31b).

### 2. Tooluse is best for large/small models, but react wins for mid-size
- **oss120b tooluse**: 98.3% pass, only 40 omissions — near-perfect mandatory completion
- **gemma31b tooluse**: 86.1% pass, best across its scaffolds
- **qwen35b react**: 89.1% pass — react provides the right balance for mid-size models
- **qwen35b tooluse**: 76.2% pass, WORST scaffold for qwen35b

### 3. qwen35b tooluse paradox: ultra-conservative behavior
qwen35b in tooluse scaffold takes only **5.3 actions** (vs 22+ in other scaffolds):
- C1 path selection = 0.974 (highest) — almost no deviations
- C3 forbidden avoidance = 0.997 (highest) — almost no commissions
- C2 mandatory completion = 0.616 (lowest) — massive omissions (3,011)
- **Diagnosis**: tooluse scaffold makes qwen35b too cautious — it avoids mistakes by avoiding actions entirely

### 4. C2 mandatory completion is the key differentiator
Across all models and scaffolds, C2 has the highest variance and strongest correlation with overall compliance.
- Range: 0.616 (qwen35b tooluse) to 0.991 (oss120b tooluse)
- Omission counts: 40 (best) to 3,540 (worst)

### 5. Scaffold ranking overall: tooluse > react > checklist > direct
- tooluse (0.681) and react (0.679) are near-tied at the top
- direct (0.614) consistently worst — minimal guidance hurts all models

### 6. Token efficiency vs quality
| Model-Scaffold | Tokens | Compliance | Efficiency |
|---------------|--------|-----------|------------|
| oss120b tooluse | 31,705 | 0.796 | baseline |
| qwen35b react | 28,313 | 0.688 | ~same cost, 14% worse |
| gemma31b tooluse | 15,153 | 0.652 | 2x cheaper, 18% worse |
| qwen35b tooluse | 11,530 | 0.594 | 3x cheaper, 25% worse |

---

## Next Steps
1. Post-W8 defense experiments (see `docs/plan_post_w8_defense.md`)
2. Scaffold-independence statistical tests (Friedman + Kendall W)
3. Paper integration: Table 5 (cross-model scaffold comparison)
