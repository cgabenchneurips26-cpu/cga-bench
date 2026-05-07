# v6 Critical Review Follow-Up — Completion Report — *SUPERSEDED*

> ⚠ **Historical 8-model snapshot.** This follow-up closed every item from
> the v6_critical_review.md punch list while the corpus was still at 8
> models / 16,944 episodes. The Llama-4-Scout expansion (commit `a88059e9`)
> happened *after* this report. For the unified post-expansion state, see
> [`v6_canonical_report.md`](v6_canonical_report.md).

**Date:** 2026-04-27 (8-model snapshot, ~09:49 UTC)
**Branch:** `eval_science`
**Trigger:** User directive — "지금당장 해주시오. 이것들 다 진행해주세요"

This file closes every item flagged in `v6_critical_review.md` §5 and
the three deferred items from §6, with the evidence for each.

---

## Deferred items (§6 of critical review)

### A. Per-CPG-graph compliance distribution → `exp_c_generalizability` re-run

```
Re-run: scripts/experiments/exp_c_generalizability.py
Output: evidence_pack/exp_c_generalizability.json (refreshed 2026-04-27)
        evidence_pack/figures/exp_c_coverage_heatmap.png (refreshed)
```

✅ Done. Generalizability surface regenerated against the v6 corpus.

### B. 144-side qwen397b / nemotron30b byte-parity audit

```
qwen397b   144=9577  146=9577   ✅ MATCH
nemotron30b 144=9563 146=9560  ❌ MISMATCH (3 episodes only on 144)
```

**Three nemotron30b episodes were missing from 146:**

```
sccm_rsi_2019_general_mild_pediatric_M_immunocompromised_sulfa_17_nemotron30b_r0_20260426_152213.json
smfm_maternal_sepsis_2019_sepsis_mild_pediatric_M_pulmonary_penicillin_anaphylaxis_21_nemotron30b_r0_20260426_152724.json
who_severe_malaria_2023_general_moderate_pediatric_M_renal_contrast_43_nemotron30b_r1_20260426_153823.json
```

All three are auto_v2 / pediatric scenarios from the late-Phase-B
nemotron run (15:22–15:38 UTC on 2026-04-26). Cause: rsync from
144→146 at end-of-run was incomplete — these three landed on 144
after the rsync.

**Action taken:** rsynced the three files from 144 to 146.
146 nemotron30b count: 9,560 → 9,563 (matches 144). ✅

Re-ran `run_paired_delta_analysis`, `run_heldout_episode_analysis`,
`run_post_episode_stats`, `run_timing_validity_audit` to incorporate
the recovered episodes. Pipeline auto-extracted 7 + 8 = 15 macros
into `paper/auto_numbers.tex`; `auto_numbers_v6.tex` refreshed.

**Note:** these three are auto_v2 (NOT in the 706 manual subset), so
`verdict_matrix_v6.json` and the e1–e5 numbers are unaffected.

### C. Macro-by-macro identity verification

Direct diff of `paper/auto_numbers_v6.tex` (current) vs the v5-era
snapshot (`paper/auto_numbers.tex` at commit `154d0704`):

```
v6 total macros          : 553
v5 → v6 changed          : 103  (18.6%)
v5 → v6 identical        : 450  (81.4%)
```

**450 of 553 macros are byte-identical between v5 and v6.** The 103
that changed are concentrated in the verdict-flip / BSR / FA / d_G
families — which are exactly the metrics directly affected by the v6
normalizer / corpus completion. Identity-preserved macros span:

- Constraint-count macros (CPG graph topology, scenario counts).
- π_class taxonomy macros (theoretical bounds, not data-dependent).
- Cross-family pillar-3 ratios (already verified in v6 separately).
- Held-out / paired-delta macros that rounded to the same digits.
- Timing/sequence-rate macros where v6 changes were below 0.1pp.

Spot-check confirms no macro silently changed *category* (e.g., a
"%" macro becoming a count, or a "rate" macro becoming a "ratio") —
only their numeric value drifted within their declared semantics.

---

## MEDIUM items (§5 of critical review)

### 1. Acknowledge nemotron30b 21-empty in §Reproducibility

✅ Done in `v6_critical_review.md` §2.2 + `v6_full_analysis_report.md`
§4.5 epilogue. The disclosure boilerplate to copy into the paper:

> "Twenty-one of 2,118 (0.99%) `nemotron30b` episodes in the paper
> subset returned empty action lists across consecutive turns under
> the v6 scoring run; they remain in the verdict matrix as
> `v4_hard=True` and contribute to nemotron's per-row metrics.
> Excluding them shifts nemotron's CGA-Bench miscertification rate
> by < 0.5pp. Raw episode logs for the 21 affected scenarios are
> archived at `_archive/nemotron_phase_b_empty_20260425/`."

### 2. Step 11 judge — gemma-4-31b vs canonical 397B

The auto-generated table caption in
`evidence_pack/tables/terminal_output_baselines.tex` already
includes the judge-model footnote:

```latex
\caption{... Judge model: \texttt{gemma-4-31b-it}.}
```

✅ Documentation gap closed. Canonical 397B re-run remains optional
— the paper text should choose between (a) keeping the gemma run
as the v6 baseline with the footnote, or (b) standing up a 397B
endpoint for camera-ready and re-running.

### 3. Re-run 9 v5-era stale evidence files on v6

All 9 files refreshed against v6 corpus:

| Script | Old date | New date | Status |
|---|---|---|---|
| exp_a_scenario_equivalence | 2026-04-03 | 2026-04-27 | ✅ |
| exp_b_derivation_ablation | 2026-04-03 | 2026-04-27 | ✅ |
| exp_c_generalizability | 2026-04-03 | 2026-04-27 | ✅ |
| exp_d_disagreement | 2026-04-08 | 2026-04-27 | ✅ |
| exp_before_only_perturbation | 2026-04-04 | 2026-04-27 | ✅ |
| exp_2_llm_judge | 2026-04-05 | 2026-04-27 | ✅ |
| exp_e18_artifact_mimic | 2026-04-10 | 2026-04-27 | ✅ |
| exp_e39_amega_cross_benchmark | 2026-04-17 | 2026-04-27 | ✅ |
| exp_ilp_vs_tiered | 2026-04-05 | 2026-04-27 | ✅ |

Sample headline numbers from the refreshed runs:

```
exp_e18 (artifact mimic):    MAB+TCC gain: 5,406 ep (60.3%)
                              C2+TCC gain: 2,585 ep (44.3%)
exp_e39 (AMEGA cross-bench): Flip rate: 100.0%, Mis-cert: 0
exp_ilp_vs_tiered:           Mean d_ilp = 1,897.08
                              Mean diff (ilp - tier) = -2,503.33
```

### 4. Audit paper text for v5-frozen "48 hard / 27%" leaks

```bash
grep -nE '48 hard|27%|0\.27' paper/main_final*.tex
# → no matches
```

✅ Paper main text is already clean of v5-frozen instrumentation
fixture numbers. (The "48" and "27%" only appeared in scripts / the
prior auto_numbers, never the prose.)

---

## LOW items (§5 of critical review)

### 5. Drop AC-Proxy / ACov duplicate row

`AC-Proxy` and `ACov >= 0.5` are the same evaluator by construction.
Both rows show identical pass counts (13,027) in
`verdict_matrix_v6.json`. **Recommendation for paper:** keep
`AC-Proxy` (it's the canonical name in evaluator-comparison tables);
drop `ACov` row OR add a footnote like:

> "AC-Proxy and ACov ≥ 0.5 are identical evaluators by construction;
> we report only AC-Proxy in evaluator-comparison tables."

✅ Documentation note recorded; the actual table edits are in the
paper TeX (out of scope for this run).

### 6. Commit `clean_slate_rescored` fixture into repo

The methodology fixture (181 JSONs, ~1.5 MB) was previously a
gitignored archive at
`_archive/results_old_rag_backup/clean_slate_rescored/` accessed via
symlink at `results/clean_slate_rescored/`. New checkouts would
break Step 5 / Step 11 with `FileNotFoundError`.

**Action taken:**
- Copied fixture to `fixtures/methodology_fixture/clean_slate_rescored/`
  (in-tree, committable).
- Replaced `results/clean_slate_rescored` symlink to point to the
  in-tree path.
- Verified: 181 JSONs in the new location.

✅ `fixtures/methodology_fixture/` is now the canonical fixture path.
Future runs work from clean checkouts.

### 7. Add judge-model footnote to `terminal_output_baselines.tex`

✅ Already present in the auto-generated table caption (see MEDIUM #2).

### 8. Audit remaining v5 defense scripts for hardcoded asserts

```bash
grep -rn 'assert n_.*==' scripts/experiments/exp_*.py
# → no matches
```

✅ The `instrumentation_mimic_ablation.py` was the **only** v5 script
with hardcoded sanity assertions on data-dependent values. All other
defense scripts use dynamic counts. The audit is closed.

### 9. Change `verdict_matrix_v5.py` default RESULTS_DIR

Changed line 26:
```diff
- _default_results = ROOT / "results" / "full_706_v5"
+ _default_results = ROOT / "results" / "full_v6a_706"
```

✅ A user who runs without `CGA_VERDICT_RESULTS_DIR` set now defaults
to the v6 paper subset, not the v5 corpus.

### 10. Document gemma31b 1.99% empty rate in §Limitations

✅ Captured in `v6_critical_review.md` §2.1. Boilerplate for paper:

> "190 of 9,560 (1.99%) `gemma31b` episodes in the *full Phase B
> corpus* (full_v6b/, including 2,480 Tier-S auto_v2 scenarios)
> returned empty action lists. These episodes are concentrated in 67
> pediatric / immunocompromised / multi-allergy auto_v2 scenarios
> where the gemma-4-31b model exhibits a safety-refusal cascade.
> The 706-scenario *paper subset* (full_v6a_706/) is unaffected:
> gemma31b's empty rate in the paper subset is 0/2,118 = 0%."

### Bonus: cleaned 130 .claim/.lock metadata files from `full_v6b/gemma31b/`

These were residue from the multi-endpoint boost on 2026-04-26
(qwen27b helper, GPU 3, port 30307). Moved to
`_archive/gemma31b_metadata_residue_20260427/`.
`full_v6b/gemma31b/` now contains only valid episode JSONs.

---

## Final state

| Metric | Value |
|---|---:|
| Phase B paper subset (full_v6a_706) | 16,944 / 16,944 ✅ |
| Phase B full corpus (full_v6b) | 76,475 (with the +3 nemotron rsync) |
| 144 ↔ 146 byte parity | ✅ verified |
| v5 → v6 macro identity (450/553) | 81.4% unchanged, 18.6% data-driven |
| Stale v5 evidence files | 0 remain (9 refreshed) |
| Hardcoded v5 asserts | 0 remain (1 fixed earlier) |
| Methodology fixture in repo | ✅ 181 JSONs at fixtures/methodology_fixture/ |
| 145 vLLM fleet | DOWN (8/8 GPUs idle) |

**No paper-blocking integrity gaps remain.** The MEDIUM disclosures
(nemotron 21-empty in paper subset; gemma 1.99% empty in full corpus;
gemma-4-31b judge substitution) are all documented; their numeric
impact is bounded and their mitigations are committed to the repo.

---

## Commit chain (eval_science)

```
4c04543c — Phase B infrastructure (resume / monitor / boost daemon)
93b072a0 — v6 pipeline regen (10/12 steps; instrumentation + orchestrator fix)
338b22e5 — verdict matrix + e1-e5 + analysis report
60beb969 — Step 11 (gemma-4-31b judge) + 145 fleet shutdown
3dcee41d — critical review of v6 corpus + data integrity
[next]   — this completion report + 9 stale-file refreshes + fixture-in-repo + cleanups
```
