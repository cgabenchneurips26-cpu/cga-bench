# Result Lineage Audit

**Date**: 2026-04-25
**Purpose**: Map every result era, identify stale references in active code/docs, prevent number confusion.

---

## 1. Result Eras (Chronological)

| Era | Directory | Episodes | Models | Scenarios | Status | Notes |
|-----|-----------|----------|--------|-----------|--------|-------|
| **v1** (Mar 31 raw) | `clean_slate_20260331_*` | 180 | 4 (oss120b, qwen27b, qwen35b, qwen4b) | 15 | **ARCHIVED** (`_archive/results/`) | Raw pre-R1-R5 runs |
| **v2** (Mar 31 rescored) | `clean_slate_rescored/` | 180 | 4 | 15 | **ARCHIVED** (`_archive/results_old_rag_backup/`) | Post-R1-R5 rescoring |
| **v3** (expansion) | `expansion_3run/` | ~66 | 1 (oss120b) | 22 | **ARCHIVED** (`_archive/results_old_rag_backup/`) | Expansion domain tests |
| **v4** (oracle) | `oracle_expansion/`, `oracle_expansion_v2/`, `oss120b_exp/` | various | 1 | various | **ARCHIVED** (`_archive/results/`) | Oracle-specific runs |
| **v5** (full 706) | `results/full_706_v5/` | **14,826** | 7 | 706 | **EXISTS** | First complete 706-scenario run |
| **v6** (8-model) | `results/full_706_v6_*` | **16,944** | 8 (+deepseek_r1_7b) | 706 | **EXISTS** | Current paper baseline |
| **v6a** | `results/full_v6a_706/` | partial | varies | 706 | **EXISTS** | Intermediate v6 |
| **v6b** | `results/full_v6b/` | partial | varies | varies | **EXISTS** | Intermediate v6 |
| **W8** | `results/ex_w8_crossmodel_v5/` | 8,472+ | 4 | 706 | **EXISTS** | Scaffold independence experiment |
| **v7** (expansion) | `results/expansion_v7/` | ongoing | 5+ | 706 | **EXISTS** | Latest expansion run |
| **beta** | `results/full_942_beta_run_*` | partial | varies | 942 | **EXISTS** | Beta CPG expansion test |
| **heldout** | `results/heldout_v1/` | varies | varies | 82 | **EXISTS** | Held-out domain validation |

### Canonical Numbers for Paper

| Metric | v5 Value | v6 Value | Paper Uses |
|--------|----------|----------|------------|
| Models | 7 | 8 | v6: 8 |
| Scenarios | 706 | 706 | 706 |
| Episodes | 14,826 | 16,944 | v6: 16,944 (all consistent) |
| `\solverSubsetN` | - | 16944 | v6 |
| `\normalizerMMEpisodes` | ~~14826~~ | 16944 | **FIXED 2026-04-26** |
| `\normalizerAblationEpisodes` | - | 16944 | v6 |

**~~Paper number conflict~~** (RESOLVED 2026-04-26): Re-ran `normalizer_ablation_multimodel.py` with 8 models (added `deepseek_r1_7b`). Updated `auto_numbers.tex:1020` from 14826→16944, 7→8 models. Mean delta changed from +3.9pp→+3.6pp. Spearman rho unchanged at 1.000, H1 still holds.

---

## 2. Stale Script References (Active Python Code)

### Scripts referencing `clean_slate_rescored/` (ARCHIVED — does not exist at `results/`)

These scripts will **fail** if run because the path doesn't exist:

| Script | Line | Variable |
|--------|------|----------|
| `scripts/experiments/_common.py` | 35 | `RESULTS_DIR` (marked DEPRECATED) |
| `scripts/experiments/p0_episode_audit.py` | 20 | `RESULTS_DIR` |
| `scripts/experiments/p2_bootstrap_ci.py` | 21 | `RESULTS_DIR` |
| `scripts/experiments/p3_c3_forbidden_analysis.py` | 16 | `RESCORED_DIR` |
| `scripts/experiments/p4_verdict_flip_table.py` | 15 | `RESULTS_DIR` |
| `scripts/experiments/p5_intro_rewrite_materials.py` | 13 | `RESULTS_DIR` |
| `scripts/experiments/p6_normalizer_safety_impact.py` | 14 | `RESCORED_DIR` |
| `scripts/experiments/p8_clinician_survey.py` | 29 | `RESULTS_DIR` |
| `scripts/experiments/bsr_perturbation.py` | 37 | `RESC_ROOT` |
| `scripts/experiments/bsr_baseline_comparison.py` | 45 | `RESC_ROOT` |
| `scripts/experiments/clinician_study_materials.py` | 31 | `RESULTS_DIR` |
| `scripts/experiments/cross_validation.py` | 34 | `RESCORE_DIR` |
| `scripts/experiments/d1_clock_scale_sweep.py` | 45 | `RESCORED_DIR` |
| `scripts/experiments/d2_parallel_order_analysis.py` | 32 | `RESCORED_DIR` |
| `scripts/experiments/d3_action_duration_model.py` | 30 | `RESCORE_DIR` |
| `scripts/experiments/d4_violation_margin_histogram.py` | 35 | `RESCORE_DIR` |
| `scripts/experiments/exp_reconcile.py` | 21 | `RESULTS_DIR` |
| `scripts/experiments/extract_normalization_pairs.py` | 32 | `RESCORED_DIR` |
| `scripts/experiments/gap_experiments.py` | 44 | `RESULTS_DIR` |
| `scripts/experiments/generate_appendix_tables.py` | 37 | `RESCORED_DIR` |
| `scripts/experiments/necessity_gap_part1.py` | 24 | `RESCORED_DIR` |
| `scripts/experiments/rescore_clean_slate.py` | 42-43 | `INPUT_DIR`/`OUTPUT_DIR` |
| `scripts/experiments/robustness_analysis.py` | 39 | `RESCORED_DIR` |
| `scripts/experiments/system_verification.py` | 31 | `RESCORED_DIR` |
| `scripts/experiments/terminal_output_baselines.py` | 50 | `RESULTS_DIR` |
| `scripts/experiments/trap_augmentation.py` | 27 | `RESCORED_DIR` |
| `scripts/experiments/v3_p0_constraint_audit.py` | 37 | `RESCORE_DIR` |
| `scripts/experiments/v3_p1a_agentclinic_replay.py` | 560 | string |
| `scripts/experiments/v3_p1c_verdict_integration.py` | 32 | `RESC_DIR` |
| `scripts/experiments/v3_p2_timestamp_sensitivity.py` | 28 | `RESULTS_DIR` |
| `scripts/experiments/v3_p4_scenario_clustered_ci.py` | 28 | `RESULTS_DIR` |
| `scripts/experiments/v3_p6_violation_spread.py` | 35 | `RESCORED_DIR` |
| `scripts/experiments/v3_p7_forbidden_exposure.py` | 35 | `RESCORED_DIR` |
| `scripts/experiments/v3_p8_core_vs_expansion.py` | 36 | `RESCORED_DIR` |
| `scripts/experiments/vf_and_spread.py` | 21 | `RESCORED_DIR` |
| `scripts/experiments/vv_verification.py` | 30 | `RESCORED_DIR` |
| `scripts/experiments/ws5_contamination_probe.py` | 42 | `RESULTS_DIR` |
| `scripts/experiments/z1_restricted_analysis.py` | 26 | `RESULTS_DIR` |
| `scripts/experiments/c3_poster_child_detail.py` | 32 | `RESCORE_BASE` |
| `scripts/experiments/exp_e_difficulty_equivalence.py` | 81 | docstring |
| `scripts/generate_action_annotation_sheet.py` | 19 | `RESULTS_DIR` |
| `scripts/select_case_studies.py` | 17 | `RESULTS_DIR` |

### Scripts referencing `clean_slate_20260331_210910` (ARCHIVED)

| Script | Line |
|--------|------|
| `scripts/cp3_validate.py` | 9 |
| `scripts/cp4_friedman.py` | 12 |
| `scripts/cp4_verify_friedman.py` | 12 |
| `scripts/q1_run_variance.py` | 9 |
| `scripts/q2_cga_perfect.py` | 8 |
| `scripts/q3_composite_sensitivity.py` | 11 |
| `scripts/experiments/p6_normalizer_safety_impact.py` | 13 |
| `scripts/experiments/v3_p1c_verdict_integration.py` | 31 |
| `scripts/experiments/v3_p7_forbidden_exposure.py` | 36 |
| `scripts/experiments/extract_normalization_pairs.py` | 33 |
| `scripts/experiments/bsr_perturbation.py` | 36 |
| `scripts/experiments/bsr_baseline_comparison.py` | 44 |
| `scripts/experiments/robustness_analysis.py` | 558 |

### Scripts referencing `expansion_3run/` or `oracle_expansion*/oss120b_exp` (ARCHIVED)

| Script | Lines |
|--------|-------|
| `scripts/compute_final_stats.py` | 38-40, 231-233 |
| `scripts/experiments/integrate_frontier_results.py` | 54-56 |
| `scripts/experiments/k_space_sensitivity.py` | 76-78 |
| `scripts/experiments/oracle_error_diagnosis.py` | 249, 265 |

---

## 3. Stale Evidence Pack References

These evidence_pack files cite 180-episode era data:

| File | Issue |
|------|-------|
| `evidence_pack/FINAL_NUMBERS_CLEAN_V2.md` | "180 episodes", `clean_slate_rescored/` |
| `evidence_pack/PAPER_NUMBER_SOURCE.md` | "180 episodes", `clean_slate_rescored` |
| `evidence_pack/cga_bench_full_briefing.md` | "180 episodes", `clean_slate_rescored/` |
| `evidence_pack/episode_run_env_report.md` | "180 episodes" |
| `evidence_pack/pipeline_audit_report_20260403.md` | `clean_slate_rescored` paths |
| `evidence_pack/analysis/p0_audit_report.md` | "180 episodes" |
| `evidence_pack/analysis/v3_verdict_integration.md` | "180/180 episodes" |
| `evidence_pack/case_studies/*.json` | `clean_slate_rescored/` episode paths |

---

## 4. Stale Docs References

These docs reference 180-episode era or archived paths:

| Directory | Count | Notes |
|-----------|-------|-------|
| `docs/attack_gap_exp_exp/` | 15+ files | All reference "180 episodes" and `clean_slate_rescored/` |
| `docs/impl/` | 2 files | "180 episodes" references |
| `docs/scenario_expansion/` | 3 files | `clean_slate_rescored/` and `full_690` references |
| `docs/Blind_Spot_Rate_Pipeline_260401.md` | 1 file | "180 episodes" |
| `docs/neurips2026_submission_requirements.md` | 1 file | "180 episodes, 15 scenarios" |
| `docs/ANNOTATION_GUIDE_ACTION_NORMALIZATION.md` | 1 file | `clean_slate_rescored/` |
| `docs/review/Entire_system_review.md` | 1 file | `clean_slate_rescored/` |

---

## 5. Recommended Actions

### P0 (Paper-breaking) — RESOLVED 2026-04-26
1. ~~**Fix `\normalizerMMEpisodes`**~~: Re-ran `normalizer_ablation_multimodel.py` with 8 models. Updated `auto_numbers.tex` (14826→16944, 7→8 models, +3.9→+3.6pp). Script default updated to include `deepseek_r1_7b`.

### P1 (Would break if run) — RESOLVED 2026-04-26
2. ~~**45+ scripts** referencing `clean_slate_rescored/`~~ — Option (c) applied: deprecation banner added at top of every affected `.py` file via one-shot `scripts/batch_add_deprecation_headers.py`. Files left in place (intra-script imports preserved); banner directs readers to `docs/RESULT_LINEAGE_AUDIT.md` and current v6 baseline.

3. ~~**6 scripts** referencing `clean_slate_20260331_210910`~~ — Same banner applied.

4. ~~**4 scripts** referencing `expansion_3run/`, `oracle_expansion/`, `oss120b_exp/`~~ — Same banner applied. `scripts/experiments/full_690_runner.py` was **deliberately excluded** because it is the active v6 runner; its `oss120b_exp2/exp3` references are config keys, not result paths.

### P2 (Misleading but not breaking) — RESOLVED 2026-04-26
5. ~~**8 evidence_pack JSON files**~~ — Top-level `_historical` key inserted (era + note + see-link).
6. ~~**13 evidence_pack markdown files** + **22 docs**~~ — `> **HISTORICAL DOCUMENT**` banner inserted at the top of each file.
7. ~~`docs/neurips2026_submission_requirements.md`~~ — Banner inserted.

### P3 (Cleanup) — RESOLVED 2026-04-26
8. ~~`AUDIT_CHECKLIST.md`~~ — Updated: 7 → 8 models, 14,826 → 16,944 episodes, `full_706_v5` → `full_706_v6_*`, added `deepseek_r1_7b` row, moved v5 row to "Historical predecessor" note.
9. `CHANGELOG.md` correctly says 16,944 — no change needed.

### Totals
- 52 Python scripts: deprecation banner
- 35 Markdown docs: HISTORICAL banner
- 8 JSON files: `_historical` key
- 1 audit checklist: hard rebaseline to v6
- 1 one-shot batch script (`scripts/batch_add_deprecation_headers.py`): deleted after run

Verification: `grep -L "DEPRECATED" scripts/experiments/_common.py` returns nothing
(the banner is present); `grep -L "DEPRECATED" scripts/experiments/full_690_runner.py`
returns the file path (banner correctly absent on the active runner).
