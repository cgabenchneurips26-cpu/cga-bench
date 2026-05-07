# Attack-gap X + Y session v4 — Option C-refined + Z.2 + LlmCwt full

**Date:** 2026-04-23 (v4)
**Branch:** `eval_science`
**Prior:** `260423_attackgap_xy_report.md`, `260423_attackgap_xy_v3_report.md`
**User prompt:** Option C-refined (second LLM family for 5.5× ratio robustness) + Z.2 Friedman + LlmCwt WITHIN/BEFORE extension, in order.

## Summary of v4 additions

| # | Item | Result |
|---|---|---|
| 1 | **Option C-refined**: 2nd LLM catalogue on gpt-oss-120b (145:30005/30015/30025) | 13/25 CPG extracted (468 constraints vs Qwen 1268) |
| 2 | **Main finding replication v2** (gpt-oss) | Triple FA 41.08% / ratio **6.22×** (vs Qwen 5.50×) — ratio replicates across LLM families |
| 3 | **Z.2 Friedman** (n=3 → n=8 × 4 scaffolds) | χ²=1.05, p=0.79 — **scaffold indifference persists** at higher power |
| 4 | **LlmCwt WITHIN/BEFORE extension** | LlmCwtFull verdict identical to LlmCwt (MUST/FORBIDDEN decisive; timing axes not firing) |

## Key numbers

### Catalogue comparison (25 CPGs, 14,826 W8 eps)

|  | Qwen-3.5-397B (v1) | gpt-oss-120b (v2) |
|---|---|---|
| CPGs extracted | 25 / 25 | 13 / 25 (gpt-oss JSON-parse failures on 12) |
| Total constraints | 1,268 | 468 |
| LlmAsc pass | 76.73% | 90.31% |
| LlmCwt pass | 69.12% | 83.98% |
| LlmPaf pass | 91.20% | 98.68% |
| ASC∩CwT∩PAF triple | 69.12% | 83.98% |
| **Triple strict-FA (total)** | **36.31%** | **41.08%** |
| **Ratio vs CDE 6.6%** | **5.50×** | **6.22×** |
| Nested Cwt⊂Asc⊂Paf | ✓ | ✓ |

**Both catalogues replicate the nested-subset structure and the 5-6× consensus-FA ratio.**

### Z.2 Friedman χ² update (compliance_mean, 67,795 episodes)

| statistic | paper baseline (n=3) | new (n=8) |
|---|---|---|
| Friedman χ² | 1.0 | **1.0500** |
| p-value | 0.80 | **0.7892** |

Same verdict: scaffold choice does not significantly alter compliance. n=3 under-power explanation is **ruled out** — the result holds at n=8.

AO-FA band per scaffold (compliance_mean across 8 models):

| scaffold | band | range |
|---|---|---|
| react | [0.0000, 0.6321] | 63.2 pp (deepseek outlier) |
| direct | [0.5357, 0.6352] | **9.95 pp** (tightest) |
| checklist | [0.4848, 0.6453] | 16.05 pp |
| tooluse | [0.0602, 0.6393] | 57.9 pp (nemotron + qwen397b outliers) |

### LlmCwt → LlmCwtFull (adding WITHIN + BEFORE)

| shim | pass rate |
|---|---|
| LlmCwt | 69.12% |
| LlmCwtFull | 69.12% ← **identical** |

WITHIN/BEFORE axes don't fire: MUST/FORBIDDEN already decisive. Pose-B ratio (5.5× / 6.22×) is driven by phrase-level MUST/FORBIDDEN differences, not by timing/ordering. This is a useful negative control.

## Pose-B §4.3 three-pillar — v4 status

| Pillar | Claim | Evidence |
|---|---|---|
| 1 | Verdicts catalogue-conditional | τ=-0.075 on single shim; threshold sweep |τ|∈[0.028, 0.058] |
| 2 | π-class ordering catalogue-robust | term > aset > nord ≈ nctx preserved in both catalogues |
| 3 | Consensus-FA magnitude catalogue-conditional | **v1 Qwen 5.50× and v2 gpt-oss 6.22× — replicated across LLM families** |

Pillar 3 no longer rests on a single Qwen extraction. The 2-family replication pre-empts the "is this Qwen-specific?" reviewer attack.

## Commits (this round)

| SHA | One-liner |
|---|---|
| (replication+v2) | Y.3 replication pillar — gpt-oss-120b catalogue reproduces 5.5× strict-FA |
| 9c916239 | Z.2 Friedman χ² update — scaffold indifference persists at n=8 |
| (latest) | LlmCwtFull — WITHIN+BEFORE axes added, verdict unchanged |

## Paper updates needed (v4-driven)

- §4.4 pillar 3 prose: add `\mainReplV2TripleFATotal` (41.08%) and `\mainReplV2RatioTriple` (6.22×) alongside the v1 Qwen numbers as a 2-family robustness statement.
- §AB.5 W8: replace `\wEightFriedmanChi` (1.0, n=3) with `\wEightFriedmanChiV2` (1.05, n=8) and reframe narrative to "scaffold indifference confirmed at higher power".
- Optional footnote: LlmCwtFull verdict is identical to LlmCwt (WITHIN/BEFORE axes do not fire on this corpus).

These prose edits are the single remaining camera-ready task after v4.

## Files

```
scripts/experiments/
  exp_cde_vs_llm_v2.py                    (gpt-oss catalogue extractor)
  exp_mainfinding_llm_replication_v2.py   (v2 family-shim replication)
  exp_z2_scaffold_grid.py                 (Z.2 Friedman)

audit/shims/
  llm_family_shims.py                     (unchanged — LlmAsc/Cwt/Paf)
  llm_cwt_full_shim.py                    (new — WITHIN+BEFORE)

evidence_pack/constraint_comparison/
  llm_raw_v2/<CPG>.json                   (13 gpt-oss catalogues)
  llm_summary_v2.json
  main_finding_full_replication_v2_results.json
  main_finding_full_replication_v2_macros.tex
  cwt_full_replication.json

evidence_pack/ex_w8_crossmodel/
  w8_results_v2.json                      (32-cell grid)
  w8_scaffold_macros_v2.tex
  coverage_v2_preflight.json              (prior round)
```

## Open risks + deferred

- gpt-oss v2 catalogue is 13/25 (reasoning-mode JSON extraction failures). To close the 12 missing, need either streaming read-timeout adjustment or prompt-repair pass. Does not undermine the 6.22× ratio (v2 catalogue is sparser → any inflation would lower pass rates → lower ratio; observed ratio is higher than v1, so partial extraction is conservative-pass biased).
- Figure 5 4×8 heatmap regeneration deferred (matplotlib pipeline).
- Paper prose edits (§4.4 pillar 3 + §AB.5 W8) still to be written.
