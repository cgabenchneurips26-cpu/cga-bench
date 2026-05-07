# Paper Macro Taint — Re-verification Report

**Date**: 2026-04-21  
**Supersedes (partial)**: `260421_paper_macro_impact.md`  
**Scope**: full-sample empty-termination audit of every cell in
`full_706_v5/` that feeds `verdict_matrix_v5.py`.

---

## 1. Method

`verdict_matrix_v5.py` reads the 8 `COMPLETE_MODELS`:

```
oss120b, qwen27b, qwen35b, qwen4b, qwen397b,
gemma31b, nemotron30b, deepseek_r1_7b
```

from `results/full_706_v5/{model}/`. For each cell we scanned **all**
episode JSONs (not a 100-sample slice) and counted
`termination_reason == "consecutive_empty_actions"` as the taint signal.
Threshold for "really tainted": ≥ 20 % consecutive-empty termination
rate.

## 2. Results (full-N)

| Cell | total | empty_term | empty % | top reasons | verdict |
|---|---:|---:|---:|---|---|
| oss120b | 2121 | 27 | 1.3 % | timeout 98.3 %, empty 1.3 %, completed 0.3 % | CLEAN |
| qwen27b | 2123 | 1 | 0.05 % | timeout 65.4 %, disposition 33.9 %, completed 0.4 % | CLEAN |
| qwen35b | 2121 | 43 | 2.0 % | timeout 88.8 %, disposition 8.5 %, empty 2.0 % | CLEAN |
| qwen4b | 2121 | 555 | **26.2 %** | timeout 72.1 %, empty 26.2 %, completed 1.6 % | **TAINTED** |
| qwen397b | 2121 | 155 | 7.3 % | timeout 59.1 %, disposition 33.1 %, empty 7.3 % | CLEAN |
| gemma31b | 2121 | 79 | 3.7 % | disposition 48.1 %, timeout 47.7 %, empty 3.7 % | CLEAN |
| nemotron30b | 2121 | 331 | **15.6 %** | timeout 81.8 %, empty 15.6 %, completed 1.9 % | BORDERLINE |
| deepseek_r1_7b | 2137 | 480 | **22.5 %** | timeout 67.3 %, empty 22.5 %, completed 8.4 % | **TAINTED** |

Only **2** cells clearly above threshold (qwen4b, deepseek_r1_7b) and
**1** borderline (nemotron30b). Five cells are clean (≤ 10 %).

## 3. Comparison with prior claim

`260421_paper_macro_impact.md` listed 6 cells as "contaminated":

| prior claim | empty % | actual corpus | reality |
|---|---:|---|---|
| qwen4b_react 98.1 % | ex_w8_crossmodel | full_706_v5 qwen4b | **26.2 %** — tainted but not 98 % |
| nemotron30b_react 98.6 % | ex_w8_crossmodel | full_706_v5 nemotron30b | 15.6 % — borderline, not 98 % |
| qwen4b_checklist 58.6 % | ex_w8_crossmodel | full_706_v5 qwen4b | 26.2 % — see above |
| qwen35b_react 28.5 % | ex_w8_crossmodel | full_706_v5 qwen35b | **2.0 %** — clean in v5 |
| qwen397b_react 24.8 % | ex_w8_crossmodel | full_706_v5 qwen397b | **7.3 %** — clean in v5 |
| gemma31b_direct 20.3 % | ex_w8_crossmodel | full_706_v5 gemma31b | **3.7 %** — clean in v5 |

The prior report conflated **ex_w8_crossmodel** rates (W8 appendix
corpus, scaffold-tagged, 2026-04-18+) with **full_706_v5** rates
(E1–E5 corpus, scaffold-neutral, 2026-04-04). They are different runs.

`full_706_v5/qwen4b`, `full_706_v5/deepseek_r1_7b` are the only cells
in the E1–E5 input pool that exhibit material contamination.
`full_706_v5/nemotron30b` is close to threshold and should be re-run
alongside them as a precaution.

## 4. Implication for the 80 tainted-macro list

Any macro that aggregates across all 8 `COMPLETE_MODELS` receives
two contaminated inputs (out of eight). The practical taint magnitude
depends on whether the aggregator is a mean, a max, or a per-model
metric.

- **Per-model macros** that reference qwen4b / deepseek_r1_7b
  directly (e.g. `\qwenFourBVerdictFlip`, `\deepseekVerdictFlip`)
  are fully tainted.
- **Cross-model means** (e.g. `\verdictFlipRate` = 84.0 %) are
  ~25 % contaminated because 2 of 8 cells are tainted.
- **Max/min/rank statistics** (e.g. `\bsrMaxOblivious`) depend on
  whether qwen4b / deepseek_r1_7b happened to hold the extremum.
- **Kappa / agreement** metrics are contaminated in proportion to
  how much of the agreement pool is driven by the two bad cells.

Concretely: of the 80 macros, we estimate
- ~15-20 fully tainted (per-cell)
- ~45-55 partially tainted (cross-model aggregates)
- ~10-15 robust (not influenced by the 2 cells)

This matches a re-run scope much smaller than "recompute all 80".

## 5. Revised re-run scope

| Corpus | Cells to re-run | Rationale |
|---|---|---|
| `full_706_v5/` | `qwen4b`, `deepseek_r1_7b`, `nemotron30b` | > 15 % empty, feeds E1–E5 |
| `ex_w8_crossmodel/` | 7 cells from root-cause doc (§8) | 20 – 98 % empty, feeds W8 |
| `ex_w8_crossmodel/` | 3 empty `*_tooluse` cells | decision #2: completeness run |

full_706_v5 re-run is **added back to the plan** (Step 4) under a new
"precautionary" bucket; the original plan had marked full_706_v5 as
out of scope, which is now retracted for the 3 specific cells above.

## 6. Recompute list (after re-run)

Only the macros that change by more than ±0.5 (absolute) or ±5 %
(relative), whichever is tighter, will be updated in
`paper/auto_numbers.tex`. Diff log goes to
`docs/attack_gap_exp_exp/260421_macro_diff.md` as planned.
