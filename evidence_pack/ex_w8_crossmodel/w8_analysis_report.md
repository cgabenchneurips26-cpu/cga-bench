# W8 Cross-Model × Scaffold Experiment — Final Analysis Report

**Date**: 2026-04-20
**Analyst**: CGA-Bench Automated Analysis Pipeline
**Data**: 8,472 episodes (3 models × 4 scaffolds × 706 scenarios)

---

## 1. Executive Summary

We evaluated three LLM models (oss120b/120B, qwen35b/35B, gemma31b/31B) across four agent scaffolds (react, direct, checklist, tooluse) on 706 clinical guideline adherence scenarios. The experiment addresses NeurIPS reviewer concerns about scaffold sensitivity and model-scaffold interaction effects.

**Core finding**: Model choice explains 4.7× more variance than scaffold choice (η²=8.5% vs 1.8%), but a critical scaffold reversal exists — tooluse is simultaneously the best scaffold for oss120b/gemma31b and the worst for qwen35b. This interaction invalidates scaffold-independent claims and requires reporting scaffold-specific results.

---

## 2. Compliance Matrix

### 2.1 Mean Compliance Score (±std)

|  | react | direct | checklist | tooluse |
|--|-------|--------|-----------|---------|
| **oss120b** | 0.761±0.146 | 0.668±0.177 | 0.705±0.173 | **0.796±0.118** |
| **qwen35b** | **0.688±0.193** | 0.634±0.183 | 0.651±0.172 | 0.594±0.250 |
| **gemma31b** | 0.587±0.237 | 0.539±0.231 | 0.569±0.214 | **0.652±0.170** |

### 2.2 Pass Rate (≥0.5 threshold / ≥0.75 threshold)

|  | react | direct | checklist | tooluse |
|--|-------|--------|-----------|---------|
| **oss120b** | 94.6/63.2 | 86.8/36.7 | 89.8/48.0 | **98.3/72.0** |
| **qwen35b** | **89.1/44.6** | 82.0/30.5 | 87.1/31.4 | 76.2/33.9 |
| **gemma31b** | 72.5/27.5 | 57.2/23.2 | 63.5/24.5 | **86.1/32.4** |

---

## 3. Variance Decomposition

| Source | η² | % Variance | Interpretation |
|--------|-----|-----------|----------------|
| Model | 0.0855 | 8.5% | Model size is the dominant factor |
| Scaffold | 0.0181 | 1.8% | Scaffold matters, but less so |
| Residual | — | 89.6% | Scenario-level variance dominates |
| **Ratio** | | **4.7×** | Model matters 4.7× more than scaffold |

The residual (89.6%) reflects high scenario-level variance — different clinical scenarios have fundamentally different difficulty levels, independent of model or scaffold.

---

## 4. Scaffold Ranking and Reversal Analysis

### 4.1 Per-Model Rankings

| Model | 1st | 2nd | 3rd | 4th |
|-------|-----|-----|-----|-----|
| oss120b | tooluse (0.796) | react (0.761) | checklist (0.705) | direct (0.668) |
| qwen35b | react (0.688) | checklist (0.651) | direct (0.634) | tooluse (0.594) |
| gemma31b | tooluse (0.652) | react (0.587) | checklist (0.569) | direct (0.539) |

### 4.2 Pairwise Scaffold Concordance (Kendall τ)

| Pair | τ | Interpretation |
|------|---|----------------|
| oss120b ↔ gemma31b | **1.00** | Perfectly concordant — same scaffold ordering |
| oss120b ↔ qwen35b | **0.00** | **Reversal** — tooluse flips from #1 to #4 |
| qwen35b ↔ gemma31b | **0.00** | **Reversal** — same tooluse flip |

### 4.3 Interpretation

The reversal is driven entirely by qwen35b's anomalous behavior in the tooluse scaffold. Two of three model pairs show reversal (τ=0), meaning scaffold rankings are **not model-independent**. This has paper implications: we cannot claim a single "best scaffold" without qualifying by model family.

---

## 5. The qwen35b Tooluse Paradox

qwen35b in tooluse mode exhibits extreme conservatism:

| Metric | qwen35b tooluse | qwen35b react | Δ |
|--------|----------------|---------------|---|
| Actions/episode | **3.1** | 17.4 | -82% |
| Tokens/episode | **621** | 20,710 | -97% |
| LLM calls | 6.0 | 10.4 | -42% |
| Omissions | 2,965 | 1,949 | +52% |
| Commissions | **0** | 80 | -100% |
| C1 (path selection) | 0.974 | 0.901 | +8% |
| C3 (forbidden avoidance) | 0.997 | 0.922 | +8% |
| C2 (mandatory completion) | **0.616** | 0.770 | -20% |

**Diagnosis**: The tooluse scaffold's structured function-call format causes qwen35b to adopt an ultra-conservative strategy — it avoids all commissions (0 total) and deviations (136 total, lowest in experiment) by simply not taking actions. This maximizes safety sub-scores (C1, C3) but catastrophically fails on completeness (C2).

**Mechanism**: qwen35b interprets tool-use function signatures more literally and rigidly than free-text scaffolds. When uncertain, it defaults to inaction rather than risking a wrong function call. This is the opposite of oss120b, which uses tooluse's structure to systematically work through the required action list.

---

## 6. Sub-Score Decomposition (C1–C5)

### 6.1 C2 Mandatory Completion — The Key Differentiator

C2 has the widest range across all cells and is most strongly correlated with overall compliance:

| Cell | C2 | Overall Comply | Omissions |
|------|-----|---------------|-----------|
| oss120b tooluse | **0.991** | 0.796 | 40 |
| oss120b react | 0.906 | 0.761 | 541 |
| qwen35b react | 0.770 | 0.688 | 1,949 |
| gemma31b tooluse | 0.748 | 0.652 | 2,531 |
| qwen35b tooluse | **0.616** | 0.594 | 2,965 |
| gemma31b direct | 0.649 | 0.539 | 3,540 |

C2 range: **0.616 – 0.991** (Δ = 0.375). All other sub-scores have ranges < 0.15.

### 6.2 C5 Sequence Integrity — Ceiling Effect

C5 ≥ 0.993 for all cells except oss120b direct (0.994) — effectively solved. Sequence violations are rare (0–40 per cell).

### 6.3 C1 Path Selection — Stable Across Conditions

C1 ranges 0.853–0.974, with qwen35b tooluse being the outlier (0.974 due to taking few actions). Excluding that cell, C1 varies only 0.853–0.901.

---

## 7. Violation Profile Analysis

### 7.1 Violation Counts by Type

| Type | oss120b (sum) | qwen35b (sum) | gemma31b (sum) |
|------|--------------|---------------|----------------|
| **Omission** | 4,402 | 10,577 | 12,550 |
| Deviation | 9,979 | 5,730 | 6,851 |
| Timing | 3,251 | 2,276 | 2,716 |
| Commission | 600 | 463 | 372 |
| Sequence | 97 | 64 | 6 |

**Key pattern**: oss120b has the fewest omissions (acts on everything) but most deviations (takes many off-protocol actions). Smaller models have far more omissions but fewer deviations — they fail by inaction, not by wrong action.

### 7.2 Commission Rate (Safety)

Total commissions across 706 scenarios:

| Cell | Commissions | Rate/episode |
|------|------------|-------------|
| qwen35b tooluse | **0** | 0.000 |
| gemma31b react | 44 | 0.062 |
| qwen35b react | 80 | 0.113 |
| gemma31b direct | 88 | 0.125 |
| oss120b tooluse | 143 | 0.203 |
| qwen35b checklist | 208 | 0.295 |

Smaller models are generally safer (fewer commissions) but less complete.

---

## 8. Cost-Quality Analysis

### 8.1 Pareto Frontier

| Cell | Tokens | Comply | Tokens/Comply | Pareto? |
|------|--------|--------|--------------|---------|
| qwen35b tooluse | 621 | 0.594 | 1,046 | ✅ Cheapest |
| gemma31b react | 10,252 | 0.587 | 17,477 | ❌ Dominated |
| gemma31b direct | 10,817 | 0.539 | 20,052 | ❌ Dominated |
| qwen35b direct | 11,872 | 0.634 | 18,723 | ✅ |
| gemma31b tooluse | 16,213 | 0.652 | 24,858 | ✅ |
| qwen35b react | 20,710 | 0.688 | 30,087 | ✅ |
| oss120b direct | 16,759 | 0.668 | 25,074 | ❌ Dominated |
| oss120b tooluse | 31,614 | 0.796 | 39,710 | ✅ Best quality |

### 8.2 Efficiency Tiers

| Tier | Best Cell | Comply | Cost | Use Case |
|------|----------|--------|------|----------|
| **Maximum quality** | oss120b tooluse | 0.796 | 31.6K tok | Critical care decisions |
| **Best balance** | qwen35b react | 0.688 | 20.7K tok | Standard clinical support |
| **Budget** | gemma31b tooluse | 0.652 | 16.2K tok | Cost-constrained deployment |
| **Ultra-cheap** | qwen35b tooluse | 0.594 | 621 tok | Screening/triage only |

---

## 9. Paper Implications

### 9.1 Claims Supported
1. **Model size matters most**: η²(model) = 8.5% vs η²(scaffold) = 1.8% (4.7× ratio)
2. **Tooluse and react scaffolds are generally best**: avg comply 0.681 and 0.679 respectively
3. **C2 mandatory completion is the discriminating axis**: range 0.375 vs <0.15 for other sub-scores
4. **Omission is the dominant failure mode**: 27,529 omissions vs 1,435 commissions across all cells

### 9.2 Claims Requiring Qualification
1. **"Tooluse is the best scaffold"** — only for oss120b and gemma31b; **worst** for qwen35b (τ=0 reversal)
2. **Scaffold rankings are model-dependent** — 2 of 3 pairwise comparisons show reversal
3. **Ultra-cheap inference is possible** — qwen35b tooluse at 621 tokens achieves 0.594 comply, but at the cost of near-zero action output

### 9.3 Recommended Table for Paper (Table 5)

```latex
\begin{table}[t]
\caption{W8: Cross-model scaffold comparison (706 scenarios, 8,472 episodes).
$\eta^2_\text{model}=0.085$, $\eta^2_\text{scaffold}=0.018$, ratio $4.7\times$.}
\begin{tabular}{llccc}
\toprule
Model & Best Scaffold & Comply & Pass\% & $\tau$ vs oss120b \\
\midrule
oss120b (120B) & tooluse & 0.796 & 98.3 & --- \\
qwen35b (35B) & react & 0.688 & 89.1 & 0.00 \\
gemma31b (31B) & tooluse & 0.652 & 86.1 & 1.00 \\
\bottomrule
\end{tabular}
\end{table}
```

---

## 10. Appendix: Experimental Setup

- **Models**: oss120b (openai/gpt-oss-120b, TP=2), qwen35b (Qwen/Qwen3.5-35B-A3B-FP8, TP=1), gemma31b (google/gemma-4-31b-it, TP=1)
- **Scaffolds**: react (ReAct reasoning), direct (no scaffold), checklist (structured checklist), tooluse (function calling)
- **Scenarios**: 706 clinical scenarios across 25 CPG domains
- **Infrastructure**: 2× 8×H200 GPU servers (<external-gpu-host>, <internal-gpu-host>)
- **vLLM**: v0.19.0 (144), gemma4 tag (145)
- **Run duration**: ~8 hours total (gap-fill + container swaps)
- **Deduplication**: unique scenario_id per cell, first-seen policy
