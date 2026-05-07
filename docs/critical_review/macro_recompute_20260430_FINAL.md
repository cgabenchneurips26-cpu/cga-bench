# Paper Macro Recompute Cycle — Final Report (2026-04-30)

## Cycle scope

A reviewer audit of three paper TeX files (`paper/auto_numbers.tex`, `paper/main_final_v18.tex`, `paper/appendix_v18.tex`) at commit `6aac31a7` surfaced 8 categories of macro-level defects (X1–X8, W3 follow-ons, plus 10 follow-up items N1–N10). This report is the consolidated record of the recompute cycle that closed those defects, ending in tag `paper-macro-recompute-20260430` and Step F (CI + N5 systemic audit).

The cycle eliminated three classes of failure mode:
1. **Stale-value macros** — values from a pre-Llama4Scout (Phase A 8-model) corpus left behind after the corpus expanded to 9 models, with percent macros that re-rounded against the wrong denominator
2. **Mislabelled corpus comments** — values numerically correct for Phase A 9m but commented as "v6 Phase B", inviting reviewer cross-corpus comparison errors
3. **Generator-source schema mismatch** — `refresh_paper_macros.py` and `compute_table26_bsr_per_model.py` compared `viol_types ∈ {WITHIN, FORBIDDEN, BEFORE}` against the assessor-layer literal `"COMMISSION"`, silently producing `0` for `\nonTimingForbiddenOnly` on every generator run

## Commit chronology

| Step | Commit | Files | Substantive changes |
|---|---|---|---|
| A (analysis) | n/a (read-only) | — | Scientist agent recomputed disputed values from `evidence_pack/analysis/verdict_matrix_v6.json` + `exp_e9_safety_core.json`; produced reconciliation table at `docs/critical_review/macro_recompute_20260430.md` |
| B (macro values) | `a45a1ba1` | 4 | 13 macro corrections (7 hard values + 6 corpus-comment relabels) + first-track of `paper/main_final_v18.tex` |
| C (prose) | `741d4a76` | 3 | §6 Limitations narrative reconciliation + appendix safety_core table reorder + matrix-conflation caveat |
| D (script bug) | `d5ada272` | 6 | `refresh_paper_macros.py` `COMMISSION→FORBIDDEN` fix + 4-macro `decimals=2` + auto_numbers v6/v18 mirror sync + first-track of script + per_model_bsr_v6.json regeneration |
| E (Tier-1 follow-ups) | `c051367d` | 4 | N1 cross-cohort caption + N2 demo-corpus footnote + N4 retire `\strictFACriticalCount` + N7 Phase B critical macros |
| F (Tier-2 follow-ups) | (this commit) | 5 | N5 systemic audit + 2-script bug fix (`compute_table26_bsr_per_model.py`, `ws6_select_poster_children.py`) + N9 CI verify-only step |

## What was at risk before the cycle

- `\safetyCoreFAEpisodes{354}` was a **definition-vs-value mismatch**: comment claimed `strictFAThreeCount − MUST_only_omission_count` but value was the unrelated EX-30 non-timing TCC-fail count (315 + 39 = 354) from a different corpus. Used in 3 paper places (§5.5, App L803, App L818) to anchor a process-completeness claim.
- `\nonTimingForbiddenOnly{0}` was a **silent generator bug** — the value was always 0 because the generator script compared against the wrong vocabulary literal. Two parallel scripts had the same bug. Fix in only one would still leave the other to silently revert on the next run.
- `\strictFAThree{5.9}`, `\strictFAThreeCount{1124}`, `\consensusFATotal{2106}`, `\consensusFACritical{139}`, `\consensusFACriticalPct{6.6}`, `\consensusFARate{11.0}` were **mislabelled as v6 Phase B** but were numerically Phase A 9m. The mislabel meant any reviewer looking up "Phase B headline" would see the wrong corpus's number, and any reviewer comparing "Phase A vs Phase B" would compare 9m to 9m thinking it was 9m vs 8m.
- `\strictFACriticalCount{123}` was an **orphan name collision** with `\strictFACritical{22}`: same prefix, different concepts (Phase A 8m safety-core vs Phase A 9m v4_crit), different corpora, different magnitudes (5.6× ratio). A typo in any future verdict-flip prose addition would silently inflate the cited claim 5.6×.
- §5.5 paragraph cited macros from **3 different phase corpora in one sentence** without explicit corpus annotation, invisible to anyone not reading the macro definitions.
- §6 Limitations contained two adjacent paragraphs that **contradicted each other** on whether clinician validation was used as evidence for the present submission.
- The release matrix (`verdict_matrix_v6.json`) **conflates MUST-only-omission with WITHIN-only timing** under the single literal `"WITHIN"` because OMISSION is not a tracked viol_type — but the paper's safety-core decomposition assumed a 5-cell breakdown distinguishing them, with row totals that did not sum to `\strictFAThreeCount` (904 + 56 + 17 + 72 + 209 = 1258 ≠ 1124).

## What is solid after the cycle

- **Sum-additivity invariant holds**: 980 + 0 + 0 + 139 + 5 = 1124 = `\strictFAThreeCount` (Phase A 9m, recompute-verified)
- **All 113 registry-managed macros byte-equal across 3 mirror files** (`auto_numbers.tex`, `auto_numbers_v6.tex`, `auto_numbers_v18.tex`); CI step `Paper macro consistency (verify-only)` enforces this on every push
- **All 14 sum-additive arithmetic identities verified** programmatically (Step D-2 verification)
- **End-to-end pdflatex compile passes** (`exit 0`, no `Undefined control sequence`); the only warnings are pre-existing typesetting overflow in App.~Z
- **§6 Limitations narrative is self-consistent**: clinician validation status now reads as one paragraph linking systematic-pairwise (deferred) with one validator-surfaced finding (integrated as catalogue refinement, App.~Z)
- **App safety_core table caption discloses the matrix conflation** explicitly: WITHIN-only=0 is a placeholder preserving additivity, with the cross-cohort note that strict-FA-cohort values are not directly comparable to corpus-wide §formalism counts
- **App.~Z.4 v1.1 patch table caption discloses the demo-corpus boundary**: the 6.6/6.6 flat pre/post is qualitatively-by-design over Phase A 8m demo, distinct from §verdict_flip headline 5.90 over Phase A 9m
- **`\strictFACriticalCount` is retired**: future typo `\strictFACritical → \strictFACriticalCount` will fail compile (not silently inflate the claim 5.6×)
- **Two CRITICAL generator-side bugs are fixed**: `refresh_paper_macros.py:212` (Step D) and `compute_table26_bsr_per_model.py:209` (Step F). `ws6_select_poster_children.py:182` LOW-severity dead-alias also cleaned up.
- **Phase B critical macros now first-class**: `\consensusFACriticalPctPhaseB`, `\consensusFACriticalPhaseB`, `\strictFACriticalPctPhaseB`, `\strictFACriticalPhaseB` available; main §robustness paragraph uses macro substitution instead of hardcoded `6.6\% → 3.9\%`

## N-series follow-up status

| ID | Tier | Status | Resolution |
|---|---|---|---|
| N1 | 1 | ✅ Step E | App safety_core caption gained explicit cross-cohort note |
| N2 | 1 | ✅ Step E | App.~Z.4 v1.1 patch caption gained Phase A 8m demo-corpus footnote |
| N3 | 1 | ✅ closed | `consensusFAHigh/Medium/Low` confirmed unused in v18 active paper (only legacy v3/v17/reconstructed/tier1-1) |
| N4 | 2 | ✅ Step E | `\strictFACriticalCount{123}` retired (commented out) |
| N5 | 2 | ✅ Step F | Systemic audit: 2 scripts had same bug class; both fixed |
| N6 | 2 | ✅ Step C | §6 Limitations narrative reconciled |
| N7 | 3 | ✅ Step E | Phase B critical macros added; main L438 hardcode replaced |
| N8 | 3 | ⏳ deferred | `docs/critical_review/` packaging decision = camera-ready scope |
| N9 | 3 | ✅ Step F | CI step `Paper macro consistency (verify-only)` added to `.github/workflows/ci.yml` |
| N10 | 3 | ⏳ deferred | v17/v16 ancillary build = packaging-dependent |

## Verification matrix

| Check | Tool | Result |
|---|---|---|
| Macro byte-equality (3 mirrors) | `python scripts/experiments/refresh_paper_macros.py --verify-only` | 113/113 × 3 = 339/339 match, 0 differ |
| Arithmetic sum identities | Python computation against macro values | 14/14 ✓ |
| Compile correctness | `pdflatex -draftmode main_final_v18.tex` | exit 0; no `Undefined control sequence` |
| Schema vocabulary cross-check | Sample 200 episodes from `verdict_matrix_v6.json` | viol_types ∈ {WITHIN, FORBIDDEN}, no `COMMISSION` |
| Generator script class A audit | Read-only scan of 32 scripts touching `viol_types` or `violations_by_type` | 2 critical bugs found and fixed; ~60 scripts safe by construction |
| CI integration | `.github/workflows/ci.yml` step | Added between "Source audit" and "leakage-scan" job |

## Outstanding (deferred — non-blocking for v1 submission)

1. **N8 / N10 — packaging decisions for camera-ready**:
   - If `docs/critical_review/` is included in submission, evaluate whether `17_scn012_pe_scoring_gap_analysis.md` enables reverse-identification of the SCN-012 case from §6 v1.1 keywords (`massive-PE + simultaneously required and contraindicated + co-satisfiable`); add `submission/.gitattributes export-ignore` if so.
   - v17/v16 ancillary `.tex` files compile against potentially-stale mirror values; if any of these are shipped as supplementary material, run a separate compile pass.

2. **Registry expansion** — extend `MACRO_REGISTRY` in `refresh_paper_macros.py` to cover the remaining hand-managed macros so they are also under CI verify-only protection:
   - `nonTimingNaturalPct`, `nonTimingACBlindPct`, `nonTimingMABBlindPct` (composite ratios — need ASC/PAF fields per episode)
   - `\strictFAFour`, `\strictFAFourCount` (Phase B 8m headline values — needs alternate `--verdict-matrix verdict_matrix_v6_full.json --label phase_b_full` invocation)
   - `safetyCoreFAEpisodes`, `faMustOnlyEpisodes`, etc. — these come from `exp_e9_safety_core.json` not `verdict_matrix_v6.json`, so a second `--source` flag would be needed
   This is a v1.2 cleanup task; current state is documented and traceable.

3. **App.~Z table 26 typesetting overflow** at `appendix_v18.tex:2176-2187` and `:2252-2259` — pre-existing overfull hbox warnings; cosmetic only.

4. **`compute_table26_bsr_per_model.py` retirement candidate** — Step F's audit revealed this script duplicates `refresh_paper_macros.py`'s macro-injection responsibility for at least `\nonTimingForbiddenOnly`. Two parallel implementations of the same paper macro is itself a fragility. Recommend consolidating into a single registry-managed generator in v1.2.

## Process lessons (recorded for future audit cycles)

1. **Comment-vs-value mismatches are silent**: a macro labelled "v6 Phase B" with a Phase A 9m value compiles cleanly, renders correctly in numbers, and only surfaces if a reviewer cross-checks the comment with the corpus. Mitigation: corpus tag in macro NAME (`\strictFAThreePhaseA9m`) not just COMMENT — but this requires whole-paper rename.

2. **Generator-script vocabulary drift**: producer (`verdict_matrix_v4.py`) writes one vocabulary, consumer (paper-macro generator) reads with a different vocabulary, no fail-loud assertion in between. Mitigation: `assert types <= {"WITHIN", "FORBIDDEN", "BEFORE"}` at consumer entry, fail loudly on schema drift.

3. **Hand-managed macros need a registry too**: anything not in `MACRO_REGISTRY` is effectively unprotected from script-overwrite reversion AND from corpus-evolution drift. Expanding the registry to all data-derived macros eliminates the hand-management surface area.

4. **CI guard pays for itself once**: the new `Paper macro consistency (verify-only)` step would have caught the original `\nonTimingForbiddenOnly{0}` bug the first time someone ran the script after the COMMISSION→FORBIDDEN matrix schema was introduced. ROI = one cycle's worth of paper claims that almost shipped wrong.

5. **Sum-additivity is a free invariant**: any decomposition table where row totals should sum to a parent macro should have an explicit pytest or doctest. The 904+56+17+72+209=1258 vs strictFAThreeCount=1124 mismatch was visible by eye but not asserted anywhere.

## Tag history

- `paper-macro-recompute-20260430` — Step D commit (`d5ada272`); marks the boundary between "stale-macro state" and "audited+verified state". Steps E and F extend the cycle but do not reset the tag.

## Files of record

| Path | Purpose |
|---|---|
| `docs/critical_review/macro_recompute_20260430.md` | Step A reconciliation report (237 lines) |
| `docs/critical_review/macro_recompute_20260430_step_b.diff` | Step B `auto_numbers.tex` delta snapshot |
| `docs/critical_review/macro_recompute_20260430_step_c.diff` | Step C prose delta snapshot |
| `docs/critical_review/macro_recompute_20260430_step_d_verification.md` | Step D verification narrative |
| `docs/critical_review/macro_recompute_20260430_step_e_n1_n2_n4_n7.diff` | Step E delta snapshot (Tier-1 follow-ups) |
| `docs/critical_review/n5_systemic_commission_audit_20260430.md` | Step F N5 systemic audit (this cycle's most strategic finding) |
| `docs/critical_review/macro_recompute_20260430_FINAL.md` | THIS document — consolidated cycle record |
| `paper/auto_numbers.tex` | Single source of truth for 113 registry-managed macros + ~50 hand-managed |
| `paper/main_final_v18.tex` | First-tracked at Step B; safety-core macros inline at L221-228 |
| `paper/appendix_v18.tex` | Safety-core table caption + Z.4 v1.1 patch caption now corpus-tagged |
| `scripts/experiments/refresh_paper_macros.py` | First-tracked at Step D; `--verify-only` is the canonical CI gate |
| `scripts/experiments/compute_table26_bsr_per_model.py` | Parallel macro generator; retirement candidate |
| `.github/workflows/ci.yml` | Added `Paper macro consistency (verify-only)` step at L104-110 |

## End-state guarantee

After this cycle, any hand-edit to `auto_numbers{,_v6,_v18}.tex` for a registry-managed macro will fail CI within the next push — the `--verify-only` step compares against `verdict_matrix_v6.json` re-derivation. Any future viol_types schema change in the verdict matrix that is not propagated to consumers will surface either as a CI failure (if the consumer is in `MACRO_REGISTRY`) or as zero-counts in observable paper tables (if a hand-managed macro). The cycle did not eliminate the second category; that is the v1.2 registry-expansion deliverable.
