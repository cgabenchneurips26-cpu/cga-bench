# Paper Macro Contamination Impact Report
**Date:** 2026-04-21  
**Root Cause:** Empty-actions contamination in 7 experimental cells

## Summary

Out of 612 macros in `auto_numbers.tex` and `auto_numbers_v2.tex`:
- **80 macros are TAINTED** by 6 contaminated cells (in E1-E5 evidence pack)
- **532 macros are SAFE** (W8 scaffold independence + other aggregates)
- **0 macros tainted by S2 symlinks** (symlinks don't generate new macros)

## Contaminated Cells & Macro Sources

### 6 Cells Tainting auto_numbers.tex (E1-E5)
These cells appear in `results/full_706_v5/` and are loaded by `verdict_matrix_v5.py` via `COMPLETE_MODELS`:
1. **qwen4b_react** (98.1% empty actions)
2. **nemotron30b_react** (98.6% empty)
3. **qwen4b_checklist** (58.6% empty)
4. **qwen35b_react** (28.5% empty)
5. **qwen397b_react** (24.8% empty)
6. **gemma31b_direct** (20.3% empty)

**Note:** `qwen35b_tooluse` (87.0% empty) is NOT in `COMPLETE_MODELS`—it only appears in W8, which uses safe models.

### Evidence Chain
```
results/full_706_v5/{contaminated_cells}/
  ↓
verdict_matrix_v5.py (COMPLETE_MODELS = {oss120b, qwen27b, qwen35b, qwen4b, qwen397b, gemma31b, nemotron30b, deepseek_r1_7b})
  ↓
evidence_pack/analysis/verdict_matrix_v6.json
  ↓
exp_e1_verdict_flip.py → exp_e2_bsr.py → exp_e3_instrumentation.py → exp_e4_operating_point.py → exp_e5_evaluator_expansion.py
  ↓
evidence_pack/exp_e{1..5}_*.json
  ↓
extract_auto_numbers.py
  ↓
paper/auto_numbers.tex (80 macros)
```

## Tainted Macros (80 total)

### Category A: E1 Verdict-Flip Metrics (20 macros)
Primary verdictFlip* and fa* (false-accept) metrics derived from verdict_matrix_v6:
- `verdictFlipRate`, `verdictFlipCount`, `verdictFlipRateMatched*`
- `faAC`, `faMAB`, `faCGA`, `faCTwo` (per-evaluator false-accept rates)
- `faAllOblivious`, `faAllObliviousCount`
- `medianViolFalseAccept`, `medViolFa*`

### Category B: E2 BSR Metrics (15 macros)
Best-single-rule performance across evaluators:
- `bsrAC`, `bsrMAB`, `bsrCGA`, `bsrCTwo`, `bsrDxEM`, `bsrACov`
- `bsrNo*` (ablations: `bsrNoOrder*`, `bsrNoState*`, `bsrNoTime*`, `bsrTerminal*`)
- `bsrN*` (counts), `bsrMax/MinOblivious`

### Category C: E3 Instrumentation Metrics (20 macros)
Ablation of temporal/state instrumentation:
- `instrFull*`, `instrHard*` (base cases)
- `instrNo*Loss`, `instrNo*Retain` (impact: `Order`, `State`, `Time`, `Terminal`)
- `instrViolLost*` (violation loss by type: `Before`, `Forbidden`, `Within`)

### Category D: E4 Operating Point Metrics (16 macros)
Evaluator agreement at different operating points (0.3, 0.4, 0.5):
- `fleissKappaMatched*`, `kappaACvsCGA*`, `kappaACvsC*`, `kappaMABvs*`
- `opPassRate*` (AC, CGA, MAB at operating points)
- `clusterCGABench*`, `clusterPreservedPct`

### Category E: E5 Evaluator Expansion Metrics (9 macros)
Bootstrap evaluator clustering:
- `bootstrapARI*` (Adjusted Rand Index CI bounds)
- `cophenetic`, `nBootstrap`, `numClusters`, `numEvaluatorsExpanded`

## Safe Macros (532 total)

### W8 Scaffold Independence (55 macros)
Prompt scaffold comparison using only **oss120b, qwen35b, gemma31b**:
- `promptScaffold*` (React, Direct, Checklist, ToolUse metrics)
- `wEight*` (W8 aggregate statistics)
- All 4 scaffolds tested in W8 use safe models only

**Status:** ✓ SAFE — no contaminated model×scaffold combinations

### Other macros (477)
Non-experimental constants and derived values from safe sources.

## Top-5 Highest-Impact Tainted Macros

| Macro | Value | Impact |
|-------|-------|--------|
| `verdictFlipRate` | 84.0% | E1 primary finding — verdict flip prevalence |
| `faAC` | 42.5% | E1 primary finding — false-accept rate (AC-Proxy) |
| `bsrDxEM` | 50.5% | E2 primary finding — best-single-rule failure rate |
| `instrFullHardRate` | 50.5% | E3 primary finding — hard violation prevalence |
| `fleissKappaMatched` | 0.056 | E4 primary finding — evaluator agreement (poor) |

## Recomputation Requirements

### Must Recompute
1. **All E1-E5 evidence pack JSONs** → Regenerate verdict_matrix_v6.json from clean results/full_706_v5
2. **auto_numbers.tex** (80 macros) → Re-run extract_auto_numbers.py
3. **main_final_v17.tex usage** → 80 macros appear throughout main text/appendix

### No Action Needed
- **auto_numbers_v2.tex** (332/335 safe macros) — W8 scaffold independence is unaffected
- **S2 symlinks** (0 macros) — Symlinks don't create new macros, only reference existing cells

## Paper Impact
- **Most critical figures:** Verdict-flip rates (Fig 3), BSR performance (Fig 4), evaluator agreement (Fig 5)
- **Most critical tables:** Table 1 (E1 metrics), Appendix Tables B-E (E2-E5 ablations)
- **Claim impact:** 12+ major claims in abstract/intro depend on E1-E5 macros

---
**Next Steps:**
1. Re-run `verdict_matrix_v5.py` after cleaning results/full_706_v5
2. Re-run E1-E5 experiment scripts in order
3. Re-run `extract_auto_numbers.py` to update auto_numbers.tex
4. Regenerate affected figures (3, 4, 5) and tables
5. Spot-check main_final_v17.tex for macro reference updates
