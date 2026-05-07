# Submission Checklist — Macro Recompute Cycle Close-Out (2026-04-30)

This document captures the deadline-time mechanical actions that the macro recompute cycle does not address by code change alone. Read this 24h before camera-ready submission.

## Pre-push verification (run from repo root)

```bash
# 1. Local macro consistency (must pass)
cd cga_bench && python scripts/experiments/refresh_paper_macros.py --verify-only
# Expected: "113 match, 0 differ" × 3 mirrors, exit 0
cd ..

# 2. Local pdflatex compile (must pass)
cd cga_bench/paper && pdflatex -interaction=nonstopmode -draftmode main_final_v18.tex
# Expected: exit 0; cosmetic warnings (overfull hbox, rerun-for-refs) acceptable
cd ../..

# 3. Tag check (must point to Step F or later)
git rev-parse paper-macro-recompute-20260430
# Expected: HEAD ancestry includes Steps B, C, D, E, F (commits a45a1ba1 → 1f6e848e)

# 4. Optional: full pytest pass (CI runs this on push anyway)
PYTHONPATH=cga_bench pytest cga_bench/tests/test_assessor/ cga_bench/tests/test_engine/ -q
```

## CI verification (after push, before merge)

```bash
# Confirm the new "Paper macro consistency (verify-only)" step ran green on first push
gh run list --workflow=ci.yml --limit 3
gh run view <run-id> --log | grep -A 5 "Paper macro consistency"
# Expected: "113 match, 0 differ" × 3 mirrors in the step output, step ✓
```

If the step does not appear in the log, the YAML may have been rejected by GitHub Actions or the step name may have been edited inadvertently. Re-check `.github/workflows/ci.yml` line 104 onward.

## Overleaf re-bundle (24h before camera-ready)

The mounted `paper/cgabench_overleaf_v18.zip` (if present from Plan 18 era) predates Steps B/C/D/E/F. To avoid shipping a stale bundle:

```bash
# Compare bundle and source mtime
ls -la paper/cgabench_overleaf_v18.zip 2>/dev/null
ls -la paper/auto_numbers.tex paper/main_final_v18.tex paper/appendix_v18.tex

# If zip predates any of the source files, re-export from the latest commit:
git archive --format=zip --prefix=cgabench_overleaf_v18/ \
  HEAD -- paper/main_final_v18.tex paper/auto_numbers.tex \
  paper/appendix_v18.tex paper/figures/ paper/observation_coarsening_v2.tex \
  paper/references.bib \
  > paper/cgabench_overleaf_v18.zip
```

File checklist for the bundle (must include all of these):

- [ ] `paper/main_final_v18.tex` (active main; carries safety-core macros inline)
- [ ] `paper/auto_numbers.tex` (113 registry-managed macros + Phase B critical macros)
- [ ] `paper/appendix_v18.tex` (App.~Z.4 corpus boundary footnote, App.~Z.5 Tier-B graph YAML patch item)
- [ ] `paper/figures/figure{1..6}.tex` (referenced by main + appendix)
- [ ] `paper/observation_coarsening_v2.tex` (input from §formalism)
- [ ] `paper/references.bib`
- [ ] Any auxiliary `.tex` inputs the main file `\input{}`s — grep first to enumerate

## Packaging-level decisions (camera-ready scope)

- [ ] **N8 — Internal audit doc visibility**: decide whether to ship `docs/critical_review/` in the supplementary tarball
  - If YES: add `submission/.gitattributes export-ignore` rules for SCN-012-related files (`17_scn012_pe_scoring_gap_analysis.md`, `n5_systemic_commission_audit_20260430.md`) to prevent reverse-identification from reviewer reads
  - If NO: confirm no other path exposes the SCN-012 case identity beyond the App.~Z anonymous v1.1 paragraph

- [ ] **N10 — Ancillary build paths**: decide whether to ship v17/v16 or main_final_v18 only
  - If only v18: no action; v17/v16 ancillary files compile against possibly-stale mirror macros and should NOT be shipped
  - If v17 also: run `pdflatex main_final_v17.tex` to confirm it compiles cleanly against current `auto_numbers.tex`; resolve any issues before bundling

- [ ] **D-3 outstanding #1**: confirm App.~Z.5 v2 roadmap now lists Tier-B graph YAML patches (added 2026-04-30, Step F+1 commit). If a reviewer asks "where is the patch for the 9 Tier-B patterns?", answer is "v1.2 — see App.~Z.5 item Tier-B graph YAML patches".

## Process artifacts to preserve

These documents form the audit trail and should remain in version control even if not shipped externally:

- `docs/critical_review/macro_recompute_20260430.md` (Step A reconciliation)
- `docs/critical_review/macro_recompute_20260430_step_b.diff`
- `docs/critical_review/macro_recompute_20260430_step_c.diff`
- `docs/critical_review/macro_recompute_20260430_step_d_verification.md`
- `docs/critical_review/macro_recompute_20260430_step_e_n1_n2_n4_n7.diff`
- `docs/critical_review/n5_systemic_commission_audit_20260430.md`
- `docs/critical_review/macro_recompute_20260430_FINAL.md` (cycle consolidated record)
- `docs/critical_review/submission_checklist_20260430.md` (this document)

## v1.2 starter list (post-deadline)

Captured here so the v1.2 cycle starts with a clear backlog:

1. **Registry expansion**: Move hand-managed macros (`safetyCoreFA*`, `faMustOnly*`, `nonTimingNaturalPct`/`ACBlind`/`MABBlind`, `strictFAFour*`) into `MACRO_REGISTRY` so the CI verify-only step covers them. May require alternate-corpus invocations (`--label phase_b_full`, `--source exp_e9_safety_core.json`).

2. **Generator consolidation**: Retire `compute_table26_bsr_per_model.py` (duplicates `refresh_paper_macros.py` for `\nonTimingForbiddenOnly` and others). Both scripts now carry the duplicate-writer warning; consolidation removes the warning surface.

3. **Sum-additivity pytest**: Add `tests/test_paper/test_macro_arithmetic.py` asserting decomposition row sums match parent macros (e.g., 980+0+0+139+5 == strictFAThreeCount). Process Lesson #5 from FINAL report.

4. **Phase B safety-core decomposition**: Compute the safety-core breakdown for the Phase B 8m corpus (n=76,464) and surface as `\safetyCoreFAEpisodesPhaseB` etc. Currently only Phase A 9m is decomposed.

5. **App.~Z.5 v1.2 deliverable execution**: Tier-B graph YAML patches (9 graphs), Phase A re-score under v1.1 flag, Phase B 706-episode re-scoring with conflict detection.

6. **`\strictFACriticalCount` deletion**: After v1 ships, remove the commented-out RETIRED stub from auto_numbers.tex entirely.

7. **Schema-drift CI check**: The schema assertion added in Step F+1 (`_VALID_VIOL_TYPES` guard in `aggregate()`) only runs when the script is invoked. A separate CI job that probes `verdict_matrix_v6.json` for token-vocabulary changes could surface drift even before any consumer runs.

## Sign-off

Cycle status as of 2026-04-30 Step F+1 (this commit):

| Layer | Status |
|---|---|
| Macro values (113 registry-managed) | ✅ verified against verdict_matrix_v6.json |
| Macro values (hand-managed ~50) | ✅ Step B/C/E recomputed and documented |
| Generator scripts (2 paper-feeding) | ✅ both fixed + schema-drift assertions |
| §6 narrative consistency | ✅ Step C reconciliation |
| Appendix table integrity | ✅ Step C reorder + caption caveats |
| App.~Z.5 v1.2 deferred items | ✅ Tier-B graph YAML patches now explicitly listed |
| pdflatex compile | ✅ exit 0 |
| CI guard | ✅ verify-only step + schema assertion at runtime |
| Submission packaging | ⏳ N8/N10 deferred to camera-ready |
| Overleaf bundle | ⏳ rebundle 24h before submission per checklist above |
| Tag pointer | ✅ `paper-macro-recompute-20260430` → Step F (commit 1f6e848e); will advance again with Step F+1 |
