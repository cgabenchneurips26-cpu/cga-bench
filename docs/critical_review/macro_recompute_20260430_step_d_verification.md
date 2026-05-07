# Step D Verification — Macro Recompute Cycle Final Audit (2026-04-30)

This document records verification results after Step B (macro recompute) and Step C (prose reconciliation). Step D consists of six checks (D-1..D-6) closing the recompute cycle.

## D-1 — pdflatex compile

**Tool availability**: `/usr/bin/pdflatex` available; latexmk not present.
**Compile target**: `paper/main_final_v18.tex` (draftmode, 90s timeout, nonstopmode).
**Result**: pdflatex returned **exit 0** (success). All Step B/C macros (`\safetyCoreFAEpisodes{144}`, `\nonTimingForbiddenOnly{423}`, `\faMustOnlyEpisodes{980}`, `\strictFACriticalPct{1.96}`, `\consensusFARate{11.05}`, etc.) resolved without `! Undefined control sequence`. Cosmetic warnings only:

| Warning | Lines | Severity |
|---|---|---|
| Overfull hbox (139pt) | L2176–2187 (App.~Z Tier table) | typesetting; pre-existing, not Step B/C/D-induced |
| Overfull hbox (63pt) | L2252–2259 (App.~Z auto-transition list) | typesetting; pre-existing |
| Duplicate destination `table.45`/`table.46` | (PDF anchor collision) | cosmetic; pre-existing |
| `Label(s) may have changed. Rerun to get cross-references right.` | n/a | normal first-pass behavior |

The compile is a smoke check confirming the macro substitution chain produces a buildable document. The cosmetic warnings predate Step B/C/D and are not blockers for camera-ready submission.

## D-2 — Numerical consistency (14/14 ✓)

| Identity | Expected | Computed | Verdict |
|---|---|---|---|
| `\safetyCoreFAEpisodes` = `\strictFAThreeCount` − `\faMustOnlyEpisodes` | 144 | 1124 − 980 = 144 | ✓ |
| `\safetyCoreFAPct` = 144 / 19062 × 100 | 0.76 | 0.76 | ✓ |
| `\faMustOnlyPct` = 980 / 1124 × 100 | 87.2 | 87.2 | ✓ |
| `\nonTimingNaturalPct` = 443 / 19062 × 100 | 2.32 | 2.32 | ✓ |
| `\nonTimingACBlindPct` = 306 / 443 × 100 | 69.1 | 69.1 | ✓ |
| `\nonTimingMABBlindPct` = 201 / 443 × 100 | 45.4 | 45.4 | ✓ |
| `\nonTimingForbiddenOnly` + `\nonTimingBeforeOnly` = `\nonTimingNaturalCount` | 443 | 423 + 20 = 443 | ✓ |
| `\strictFAThree` = 1124 / 19062 × 100 | 5.90 | 5.90 | ✓ |
| `\strictFACriticalPct` = 22 / 1124 × 100 | 1.96 | 1.96 | ✓ |
| `\consensusFARate` = 2106 / 19062 × 100 | 11.05 | 11.05 | ✓ |
| `\consensusFACriticalPct` = 139 / 2106 × 100 | 6.60 | 6.60 | ✓ |
| Safety-core sum 0 + 0 + 139 + 5 = 144 | 144 | 144 | ✓ |
| Strict-FA total 980 + 144 = 1124 | 1124 | 1124 | ✓ |
| Strict-FA total 980 + 0 + 0 + 139 + 5 = 1124 | 1124 | 1124 | ✓ |

All sum-additive invariants hold, including the X1-fix invariant (safety-core decomposition rows sum to strict-3way-FA total).

## D-3 — App.~Z (Conflict-Resolution v1.1) macro spot-check

Verified macros in `appendix_v18.tex` §Z subsections L2094–2300:

| Macro | Value | Used in | Internal consistency |
|---|---|---|---|
| `\cdeAuditCpgsTotal` | 25 | L2167, L2173 | ✓ matches `\numGraphsTotal` |
| `\conflictPatternsN` | 11 | L2173, L2184, L2213, L2218, L2267 | ✓ = Tier B (9) + Tier C (2) |
| `\conflictGraphsN` | 9 | L2173, L2184 | ✓ = Tier B graphs (7) + Tier C graphs (2) |
| `\tierAN` | 0 | L2180 | ✓ "vacuous in current corpus" footnote |
| `\tierBN` | 9 | L2181 | ✓ "Static mandatory + conditional FORBIDDEN" |
| `\tierCN` | 2 | L2182 | ✓ "Genuine OR_REQUIRED semantics" |
| `\strictFAThreePre` | 6.6 | L2225 | Phase A 8m demo corpus value (intentional separation per L2208 "v1.1 demonstration pipeline") |
| `\strictFAThreeFixed` | 6.6 | L2225 | "qualitatively unchanged; CONFLICT now surfaced" — explicitly flat |

The `\strictFAThreePre/Fixed{6.6/6.6}` flat-pre/post pair is documented in `auto_numbers.tex` L1499-1500 as Phase A 8m demo numbers, distinct from the headline §5.5 Phase A 9m `\strictFAThree{5.90}`. The two values reference different corpora deliberately. No Step E action required — but a one-sentence footnote in App.~Z.4 caption clarifying the demo-corpus boundary would reduce reviewer confusion.

## D-4 — SCN-012 doc visibility (X6 from initial audit)

| File | Tracked? | Path public? |
|---|---|---|
| `docs/critical_review/17_scn012_pe_scoring_gap_analysis.md` | Yes (`git ls-files`) | Repo-public |
| `docs/critical_review/critic_scn012_cde_rescoring_implementation_plan.md` | Yes | Repo-public |

`docs/critical_review/` is not gitignored. If the NeurIPS submission package excludes the `docs/` tree (typical for code-supplementary submissions), there is no exposure path. If it includes them (e.g., reproducibility audit), reverse-identification of the SCN-012 case from the v1.1 paragraph keywords (`massive-PE + simultaneously required and contraindicated + co-satisfiable`) is feasible.

**Recommendation (deferred)**: confirm submission packaging intent before camera-ready; if `docs/critical_review/` is included, either anonymise filenames or add a `submission/.gitattributes export-ignore` rule. This is a packaging-level decision, not a content fix.

## D-5 — `\faWithinOnlyN{8,514}` orphan check

| Macro | Defined in | Used in | Verdict |
|---|---|---|---|
| `\faWithinOnlyN` | `auto_numbers.tex:452` (= 8,514, Phase A 9m all hard-violating) | `main_final_v17.tex`, `main_final_v12.tex`, `main_final_v16.tex`, `main_test_compile.tex` | **Orphan in v18** — not used by `main_final_v18.tex` |
| `\faWithinOnlyEpisodes` | `main_final_v18.tex:225` (= 0 after Step B; WITHIN-only **within strict-3way-FA**, distinct concept) | App table only | Active |

Despite similar names, the two macros measure different cohorts (all hard-violating vs. strict-FA subset) and on different bases. The `\faWithinOnlyN` value 8,514 was confirmed by re-running `refresh_paper_macros.py` against Phase A 9m corpus — it is the correct count of hard-violating episodes whose `viol_types == {WITHIN}`, not Phase B as initially suspected.

`\faWithinOnlyN` is left in `auto_numbers.tex` for backward compatibility with v17/v16 builds; no v18 paper text references it.

## D-6 — refresh_paper_macros.py overwrite-risk audit

### Bug found and fixed: `COMMISSION` literal vs. matrix `FORBIDDEN`

`scripts/experiments/refresh_paper_macros.py` line 212 (and corresponding description at line 584) compared `viol_types == {"COMMISSION"}`, but the released `verdict_matrix_v6.json` carries the literal `"FORBIDDEN"` (verified by direct sample of 200 episodes: `{'WITHIN', 'FORBIDDEN'}`). This caused `\nonTimingForbiddenOnly` to always compute as 0, which is exactly the manual-edit-error value found in `auto_numbers.tex` before Step B.

**Root cause of the original `\nonTimingForbiddenOnly{0}` macro stale**: the macro was last refreshed by this buggy script. When Step B set the value to 423 by hand, the next script run would have silently reverted it back to 0. Step D's Edit at `refresh_paper_macros.py:212` and `:584` is the durable fix.

### Decimal-precision alignment

The Step B audit set 4 macros to 2-decimal precision (`5.90`, `1.96`, `11.05`, `6.60`). The script default was 1 decimal. Step D updated:
- `strictFAThree` → `decimals=2`
- `strictFACriticalPct` → `decimals=2`
- `consensusFARate` → `decimals=2`
- `consensusFACriticalPct` → `decimals=2`

Without this fix, future runs would silently downgrade Step B values to 1-decimal (`5.9`, `2.0`, `11.0`, `6.6`). The 1.96 → 2.0 round-down is the most consequential — `\strictFACriticalPct` appears in §5.5 and the §5.5 verdict-flip narrative.

### Final verify-only

After all D-6 fixes:
```
paper/auto_numbers.tex     : 113 match, 0 differ
paper/auto_numbers_v6.tex  : 113 match, 0 differ  (after script-driven sync)
paper/auto_numbers_v18.tex : 113 match, 0 differ  (after script-driven sync)
```

The script's own `--verify-only` mode now confirms all three macro files are byte-consistent with `verdict_matrix_v6.json` for the 113 registry-managed macros. Hand-managed macros (`safetyCoreFA*`, `faMustOnly*`, `faForbidOnlyEpisodes`, etc.) live in `main_final_v18.tex` inline and are not registry-managed; they are not at risk of script overwrite because the script does not edit `main_final_v18.tex`.

## Macros not covered by the registry (intentional)

| Macro | Defined in | Reason for hand-management |
|---|---|---|
| `\safetyCoreFAEpisodes` | `main_final_v18.tex:221` | Computed from cross-cell decomposition; `exp_e9_safety_core.json` is the source, not `verdict_matrix.json` directly |
| `\safetyCoreFAPct` | `main_final_v18.tex:222` | Same cell-derived computation |
| `\faMustOnlyEpisodes` | `main_final_v18.tex:223` | Released matrix conflates MUST-only with WITHIN-only — see appendix caveat |
| `\faMustOnlyPct` | `main_final_v18.tex:224` | Same |
| `\faWithinOnlyEpisodes` | `main_final_v18.tex:225` | Set to 0 to preserve table additivity given matrix conflation |
| `\faBeforeOnlyEpisodes` | `main_final_v18.tex:226` | Cell-derived, not registry-computable |
| `\faForbidOnlyEpisodes` | `main_final_v18.tex:227` | Cell-derived (intersection with strict-FA) |
| `\faMixedSafetyEpisodes` | `main_final_v18.tex:228` | Cell-derived |
| `\nonTimingNaturalPct` | `auto_numbers.tex:421` | Composite percentage; could be added to registry if needed (TODO) |
| `\nonTimingACBlindPct` | `auto_numbers.tex:422` | Composite ratio (subset-of-non-timing passing ASC); needs ASC field on per-episode basis — could be added to registry |
| `\nonTimingMABBlindPct` | `auto_numbers.tex:537` | Same; could be added to registry |
| `\strictFACriticalCount` | `auto_numbers.tex:585` | Phase A 8m artifact, kept for backward-compat; should be retired |
| `\strictFAFour` | `auto_numbers.tex:582` | Phase B 8m headline value; would need separate `--verdict-matrix verdict_matrix_v6_full.json` invocation |
| `\strictFAFourCount` | `auto_numbers.tex:583` | Same as above |

The hand-managed list documents Step B's residual surface area. A future improvement would extend the script's `MACRO_REGISTRY` with these specs (especially the `nonTiming*Pct` triplet and the strict-FA-Four pair via `--label phase_b`), eliminating hand-management entirely. For the present submission cycle, hand-management is sufficient and traceable through this document.

## Step B/C/D summary

| Step | Commit | Files | Substantive changes |
|---|---|---|---|
| B | a45a1ba1 | 4 | 13 macro values (7 hard, 6 comment) + first-track of `main_final_v18.tex` + recompute report |
| C | 741d4a76 | 3 | §6 narrative reconciliation + App safety-core table reorder + caveat caption |
| D | (this commit) | 5 | refresh script bug fix (COMMISSION→FORBIDDEN) + 4 macros decimals=2 + 2 mirror sync + script first-track + per_model_bsr_v6.json regeneration |

After D, every disputed macro is now sourced from a re-runnable computation, traceable through `evidence_pack/analysis/` artefacts, and protected against silent script-overwrite reversion. The chain `verdict_matrix_v6.json + exp_e9_safety_core.json → refresh_paper_macros.py + hand-managed list → auto_numbers*.tex + main_final_v18.tex inline → §5.5 / App safety_core_decomposition` is end-to-end consistent and reproducible by `PYTHONPATH=. python scripts/experiments/refresh_paper_macros.py --verify-only` (exit 0 = clean).

## Outstanding (non-blockers)

1. App.~Z.4 caption (table at L2218): one-sentence note that `\strictFAThreePre/Fixed` reference Phase A 8m demo corpus, distinct from §5.5 Phase A 9m `\strictFAThree{5.90}`. Cosmetic, not a content fix.
2. `\strictFACriticalCount` (auto_numbers.tex L585): orphan macro, no paper text uses it. Recommend retiring in v1.2 cleanup.
3. `submission/.gitattributes export-ignore` for `docs/critical_review/` if camera-ready package risks SCN-012 reverse-identification.
4. Extend `MACRO_REGISTRY` with `nonTimingNaturalPct`, `nonTimingACBlindPct`, `nonTimingMABBlindPct`, and Phase B `strictFAFour*` specs to fully eliminate hand-management.
