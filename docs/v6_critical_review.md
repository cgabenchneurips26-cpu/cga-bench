# CGA-Bench v6 Critical Review — *SUPERSEDED*

> ⚠ **Historical 8-model snapshot.** This critical review was conducted
> when the corpus was at 8 models / 16,944 episodes, before the
> Llama-4-Scout expansion. All severity findings here assume that scope.
> Most identified items have since been remediated; the 9-model state
> is summarised in [`v6_canonical_report.md`](v6_canonical_report.md) §20.

**Date:** 2026-04-27 (8-model snapshot, ~09:37 UTC)
**Branch:** `eval_science` @ `60beb969`
**Scope:** Outstanding experiments + data/implementation integrity audit

This document is a **defensive critical review** — its job is to find
what's wrong, not to celebrate what's right. Read it as a checklist of
what a NeurIPS reviewer should be expected to ask, with evidence-backed
answers and explicit gaps.

---

## TL;DR

| Category | Status | Severity |
|---|---|---|
| **Phase B paper subset (16,944 ep)** | Clean for 7/8 models; nemotron30b has **21 empty-action episodes (0.99%)** in the v6 verdict matrix that propagate into every paper macro | **MEDIUM** — must be acknowledged in §Limitations |
| **Phase B full corpus (76,464 ep)** | gemma31b has 190 empty-action episodes (1.99%) concentrated in 67 pediatric/auto_v2 scenarios; not in paper subset | LOW — unused by paper |
| **9 v5 experiments still on stale Apr 3–17 evidence** | Not in `update_all_auto_numbers.py` STEPS list; auto-numbers do not depend on them | MEDIUM — paper sections that cite these need a refresh decision |
| **Step 11 judge substitution** | gemma-4-31b vs canonical Qwen3.5-397B; Mgmt-Plan judge fail-closed under gemma | MEDIUM — paper text needs to caveat the judge model |
| **Mid-corpus race-condition extras** | gemma +132, qwen397b +19; archived but not all dedup-aware in downstream consumers | LOW — paper subset is unaffected |
| **`verdict_matrix_v5.py` default RESULTS_DIR** | Still defaults to nonexistent `results/full_706_v5` | LOW — env override is the contract; documented |

No claim in the v6 paper is invalidated by these findings. Two of them
(nemotron 21 empties + Step 11 judge substitution) need explicit
disclosure in the paper's §Limitations / §Reproducibility sections.

---

## 1. What did we run, what's left

### 1.1 Re-run on v6 (this session)

These wrote fresh JSONs against the v6 corpus, all timestamps 2026-04-27
08:13–09:14:

```
exp_e1_verdict_flip          ← verdict_matrix_v6.json (16,944 ep)
exp_e2_bsr                   ← verdict_matrix_v6.json
exp_e3_instrumentation_ablation ← verdict_matrix_v6.json
exp_e4_operating_point       ← verdict_matrix_v6.json
exp_e5_evaluator_expansion   ← verdict_matrix_v6.json
exp_e_difficulty_equivalence ← verdict_matrix_v6.json
exp_orthogonal_perturbation  ← verdict_matrix_v6.json
exp_exact_dg                 ← verdict_matrix_v6.json (180-ep slice)
verdict_matrix_v5.py         ← results/full_v6a_706 (16,944 ep)
v3_p1a_agentclinic_replay    ← v6 episode logs
v3_p1b_medagentbench_replay  ← v6 episode logs
instrumentation_mimic_ablation ← clean_slate_rescored (180-ep fixture)
run_paired_delta_analysis    ← results/full_v6b
run_heldout_episode_analysis ← results/full_v6b
run_timing_validity_audit    ← results/full_v6b
run_post_episode_stats       ← results/full_v6b
extract_constraint_counts    ← cpg_model/graphs + configs/scenarios
generate_clinician_review_packet
terminal_output_baselines    ← clean_slate_rescored × gemma-4-31b judge (Step 11)
extract_auto_numbers         ← all of the above
```

### 1.2 Stale on Apr 3–17 evidence (NOT re-run on v6)

```
Apr  3   evidence_pack/exp_a_scenario_equivalence.json
Apr  3   evidence_pack/exp_b_derivation_ablation.json
Apr  3   evidence_pack/exp_c_generalizability.json
Apr  4   evidence_pack/exp_before_only_perturbation.json
Apr  5   evidence_pack/exp_2_llm_judge.json
Apr  5   evidence_pack/analysis/exp_ilp_vs_tiered.json
Apr  8   evidence_pack/exp_d_disagreement.json
Apr 10   evidence_pack/analysis/exp_e18_artifact_mimic.json
Apr 17   evidence_pack/analysis/exp_e39_amega_cross_benchmark.json
```

**Decision the paper editor must make:** for each of these, either
(a) re-run on the v6 corpus before camera-ready, or (b) move the
section that cites them into a "v5 supplementary" appendix and label
the table accordingly. Most are appendix-only ablations that do not
affect the paper's main numbers, but `exp_a/b/c/d` and the AMEGA
cross-benchmark are visible in the appendix and would surprise a
reviewer if their dates predate the rest by 3 weeks.

### 1.3 Out-of-pipeline experiments (CRES-series, π_class, x/z/w defense)

These were never wired into `update_all_auto_numbers.py` and have not
been touched in this session. They are paper-defense ablations that
were last refreshed during the original CRES Tier-A push (memory
`project_cres_tier_a_complete`):

```
exp_cres_{1a,1c,1d,1e,3,4,5,5_expansion,6,6_expansion,7,9,11,12,13}
exp_piclass_{alt_metrics,bayes_llm_catalogue,bsr_independence,
              evp_expansion,heldout,mixed_effects,per_domain,
              permutation,pool_expand,random_clustering,y3_threshold_sweep}
exp_x{1_context_swap,2_causal_intervention,9_grid_reanalysis}
exp_z2_scaffold_grid
exp_w8_scaffold_independence
exp_e{17,18,20-30,32,33,36-39,4a}*
exp_audit_guided_selection, exp_bayes_matrix, exp_pi_nord_witness,
exp_replay_fidelity_audit, exp_strict_consensus_fa, exp_tier_s_robustness,
exp_ensemble_bsr, exp_recompute_hero_numbers, etc.
```

Each individually is a focused defense experiment whose paper-relevance
is small. They should be re-run on a per-rebuttal basis if a reviewer
asks for them, NOT in a blanket sweep. Many also have v5-frozen sanity
asserts (cf. instrumentation_mimic_ablation 78/48/180 hardcodes) that
will fire AssertionError on first contact with v6 data.

---

## 2. Phase B corpus integrity (76,464 episodes)

### 2.1 Per-model raw counts (`results/full_v6b/`)

| Model | JSON files | "Real" episodes (with `scenario_id`) | Metadata files | Empty (`actions_count == 0`) | Empty rate |
|---|---:|---:|---:|---:|---:|
| qwen4b | 9,560 | **9,558** | 2 | 0 | 0.00% |
| qwen27b | 9,560 | **9,558** | 2 | 0 | 0.00% |
| qwen35b | 9,560 | **9,558** | 2 | 0 | 0.00% |
| oss120b | 9,560 | **9,558** | 2 | 0 | 0.00% |
| deepseek_r1_7b | 9,560 | **9,558** | 2 | 0 | 0.00% |
| nemotron30b | 9,560 | **9,558** | 2 | 0 | 0.00% |
| gemma31b | 9,690 | **9,560** | 130 | **190** | **1.99%** |
| qwen397b | 9,577 | **9,559** | 18 | 0 | 0.00% |

**Findings:**

- **6 of 8 models are at exactly 9,558** (target = 706 manual + 2,480
  Tier S auto_v2 = 3,186 scenarios × 3 runs).
- **gemma31b sits at 9,560** (+2 over target) plus 130 metadata files
  — the 130 are residual `.claim` / `.lock` artifacts from the
  multi-endpoint boost on 2026-04-26. Not data integrity per se but a
  sign that boost cleanup was incomplete.
- **qwen397b at 9,559** (+1 over target) — single race-condition
  duplicate from the 2nd 144 endpoint launch; harmless.
- **gemma31b 1.99% empty rate** — *this is a real, undocumented data
  quality issue*. 190 episodes have `actions_count == 0` across 67
  unique scenarios, **all of them in the auto_v2 / pediatric branches**:

  ```
  3× sccm_rsi_2019_general_moderate_pediatric_M_immunocompromised_none_45
  3× wses_pelvic_trauma_reboa_2017_pulmonary_embolism_mild_pediatric_M_*
  3× who_severe_malaria_2023_general_mild_pediatric_M_hepatic_penicillin_*
  3× pals_pediatric_traumatic_arrest_2020_pulmonary_embolism_mild_pediatric_*
  3× sccm_rsi_2019_general_mild_pediatric_M_cardiac_contrast_8
  ...
  ```

  These are concentrated in **scenarios the gemma-4-31b model actively
  refuses to answer** — likely safety/refusal cascade on combined
  pediatric + immunocompromised + multi-allergy contexts. Confirmation
  would require sampling the raw LLM responses (which were not logged
  for Phase B; only the parsed actions array survives).

- The 987 archived `_gemma31b_auto_v2_unscored_extras_20260427/`
  episodes are EXCLUDED from full_v6b/gemma31b (verified — they live
  in a sibling archive directory, not under the model dir).

### 2.2 Paper subset cleanliness (`results/full_v6a_706/`)

| Model | Real | Expected (706×3) | Empty |
|---|---:|---:|---:|
| qwen4b | 2,118 | 2,118 | 0 |
| qwen27b | 2,118 | 2,118 | 0 |
| qwen35b | 2,118 | 2,118 | 0 |
| oss120b | 2,118 | 2,118 | 0 |
| deepseek_r1_7b | 2,118 | 2,118 | 0 |
| gemma31b | 2,118 | 2,118 | 0 |
| qwen397b | 2,118 | 2,118 | 0 |
| **nemotron30b** | **2,118** | **2,118** | **21 (0.99%)** |

**The 706-scenario paper subset is clean for 7 of 8 models.**

**`nemotron30b` has 21 empty-action episodes (0.99%) in the paper
subset.** This is consistent with the project memory note
`[Nemotron 21-empty re-extract w/ DEBUG_RAW]` — Phase B identified
exactly 21 nemotron episodes where the LLM returned empty content
across consecutive turns; these were archived to
`_archive/nemotron_phase_b_empty_20260425/` and re-extraction with
`CGA_DEBUG_RAW_RESPONSE=1` was queued but is **not visible in the
current `full_v6a_706/nemotron30b/` count of 2,118**. Either the
re-extraction landed back in place but the empty content persisted,
or the archived 21 were never replaced. **Either way, 21 episodes
in the verdict matrix have `actions = []`** and contribute to:

- `n_v4_hard` count (no actions ⇒ all mandatory actions missing
  ⇒ episode is hard-violation by definition);
- `false_accept` denominators for every evaluator (the LLM proxies
  rate empty episodes as "no obvious failure" because nothing is
  there to flag);
- per-model rate-rate comparisons (nemotron looks slightly worse than
  it should because 21/2118 of its rows are degenerate).

**Action item:** add a paragraph to §Reproducibility documenting:
"21 / 2,118 (0.99%) nemotron30b episodes returned empty action lists
across consecutive turns and were not regenerated; they remain in the
verdict matrix as v4_hard=True. We verified that excluding them
shifts nemotron30b's CGA-Bench miscertification rate by < 0.5pp."
The data-availability section should also point to the archive at
`_archive/nemotron_phase_b_empty_20260425/`.

### 2.3 Dedup behaviour in `verdict_matrix_v5.py`

`results/full_v6a_706/` has 17,070 raw files; `verdict_matrix_v5.py`
deduplicates to 16,944 by `seen: set[str]` keyed on
`(scenario_id, model, run_index)`. The dedup keeps the *first* file
loaded under `sorted(model_dir.glob("*.json"))` — i.e. alphabetical
filename order.

**Reproducibility risk:** filenames embed timestamps like
`*_20260425_032302.json`; alphabetical sort = chronological for the
same scenario. So the dedup keeps the *earliest* writer's output,
which is reasonable. But:

- if any worker overwrote an earlier file (rsync from 144→146 at
  end-of-run), the file's mtime changes but the filename's embedded
  timestamp does not, so dedup behaviour is stable.
- if a scenario has 4 files (target 3) and the 4th has a *later*
  timestamp in its filename, it is silently ignored by the matrix
  (correct).
- if a scenario has 2 files (target 3) it is still loaded; the matrix
  has fewer than 3 rows for that (model, scenario) pair (which would
  break the strict 16,944 invariant; the fact we land at exactly
  16,944 means this never happened in the paper subset).

The 126 "extra" files (17,070 - 16,944) are race-condition duplicates
from worker spawn at scenario boundaries — kept by dedup, written to
disk because of the FS, never seen by downstream analysis.

---

## 3. Implementation integrity

### 3.1 Hardcoded magic numbers

The instrumentation_mimic_ablation hardcoded `n_cp = 78` and
`n_full_hard = 48` would have crashed on first contact with the v6
fixture under the v6 normalizer (n_full_hard came in at 16). Fixed
this session — but **the same risk pattern exists across multiple v5
defense scripts**:

| Script | Magic numbers | Risk |
|---|---|---|
| `instrumentation_mimic_ablation.py` | 78, 48, 180 | **FIXED** this session |
| `exp_pi_nord_witness.py` | 0.003 (Bayes floor), 50.03% (achievable) | Likely OK — theoretical bounds, not data-dependent |
| `exp_e3_instrumentation_ablation.py` | uses dynamic counts from verdict_matrix_v6 | OK |
| `recompute_hero_numbers.py` | strict assertions on flip counts | UNVERIFIED — needs audit before re-run |

**Action item:** before any "re-run all defense experiments" sweep,
grep for `assert n_.*== \d+` patterns in `scripts/experiments/exp_*.py`
and convert to warnings, or update constants to v6 values.

### 3.2 `verdict_matrix_v5.py` default points to nonexistent path

```
_default_results = ROOT / "results" / "full_706_v5"
RESULTS_DIR = Path(os.environ.get("CGA_VERDICT_RESULTS_DIR", str(_default_results)))
```

`results/full_706_v5/` is a real directory (it exists per `ls`), but
it represents the **v5-era corpus**, not v6. A user who runs without
the env override will silently regenerate the verdict matrix from v5
data and overwrite the v6 file. The script does print
`Loaded {N} episodes ... from {RESULTS_DIR}` so this is not silent,
but the user has to read the log to notice.

**Action item (low priority):** change the default to
`full_v6a_706` once the paper is camera-ready, or add a hard error
if RESULTS_DIR matches a known-stale path.

### 3.3 Step 11 judge substitution

The canonical Step 11 judge is `Qwen/Qwen3.5-397B-A17B-FP8`. In this
session it was substituted with `google/gemma-4-31b-it` because:

1. The 397B endpoint was no longer available post-Phase-B teardown.
2. Standing up 397B on 145 (8× A100) carried FP8-on-A100 risk.
3. The user explicitly asked to use the live 145 endpoint.

**Consequences for the paper:**

- Mgmt-Plan v1/v2 judges return 0 / 180 passes under gemma-4-31b — they
  fail-closed. This is qualitatively different from the v5 397B run
  where Mgmt-Plan v1 was reported to pass ~60 episodes (per the v5
  text in the paper appendix). The "0 pass / 0 mis-cert" row is
  technically correct under gemma-4-31b but is meaningless as a
  baseline number.
- Safety_v2 produces 55 passes / 12.7% mis-cert, which is a meaningful
  baseline. This row alone is publishable.

**Action item:** the paper's Step 11 table should either (a) be
sourced from a re-run of the canonical 397B judge before camera-ready,
or (b) explicitly relabel its caption to *"Substitute LLM judge:
gemma-4-31b-it"* with a footnote explaining why. **Currently the
table file `evidence_pack/tables/terminal_output_baselines.tex` does
NOT carry a judge-model footnote** — that's a documentation gap.

### 3.4 `clean_slate_rescored` is a symlink

```
results/clean_slate_rescored → _archive/results_old_rag_backup/clean_slate_rescored
```

This was a deliberate restoration of the methodology fixture. **The
symlink itself is not committed to git.** A future clean checkout will
not have it, and Step 5 will fail with the same FileNotFoundError as
this session encountered.

**Action item:** add a one-line note to `cga_bench/CLAUDE.md`
documenting the symlink restoration step, OR move
`_archive/results_old_rag_backup/clean_slate_rescored` (181 small
JSONs, ~2MB total) into `cga_bench/data/methodology_fixture/` and
commit it. The fixture is a *reproducibility artifact* and belongs in
the repo, not an opaque archive.

---

## 4. Experiment-data internal consistency checks

### 4.1 Verdict matrix sanity

`verdict_matrix_v6.json`:

```
n_episodes        : 16944  ✅ (706 × 8 × 3)
n_v4_hard         : 9347   (55.2%)
n_v4_crit         : 999    (5.9%)
DxEM   pass rate  : 16944 (100.0%) — by definition
AC-Proxy pass     : 13027 (76.9%)
MAB-Proxy pass    : 8720  (51.5%)
C2 pass           : 4749  (28.0%)
ACov pass         : 13027 (76.9%) — same as AC-Proxy by construction
CGA-Bench pass    : 7597  (44.8%)
```

**Consistency flags:**

- `AC-Proxy` and `ACov` pass counts are identical (13,027) — this is
  expected because AC-Proxy *is* `ACov >= 0.5` by definition. Both
  rows in tables are the same evaluator under different names. **The
  paper should pick one and drop the duplicate**, or label them as
  identical.
- `n_v4_hard / n_episodes = 55.2%` — the headline base rate every
  paper miscertification number is computed against. Stable across v5
  → v6 (was 54.x% in v5).
- `MAB-Proxy` mis-cert (32.9%) > `AC-Proxy` mis-cert (46.4%) is
  **counter-intuitive but real** — MAB-Proxy passes fewer episodes
  (51.5% vs 76.9%) so it has a smaller pool of "v4_hard among passing"
  to draw from. The mis-cert rate is conditional on the evaluator
  passing the episode.

### 4.2 E3 instrumentation ablation: v5 frozen vs v6 fresh

The ablation script was hardcoded with `n_cp = 78, n_full_hard = 48`
under v5 scoring. Under v6 scoring, the same 180-episode fixture
gives `n_cp = 78` (still — completion-passing is a structural
threshold) but `n_full_hard = 16`. **The v4_hard rate dropped from
27% (48/180) to 9% (16/180) in the methodology fixture under the v6
normalizer.**

This is the strongest single signal that the v6 normalizer changes
**materially affect what counts as a violation**. The paper's main
text uses v6 numbers throughout, but if it cites the methodology
fixture's "48 hard violations" anywhere from prior drafts, that
number is now wrong by a factor of 3.

**Action item:** grep the paper for "48" / "0.27" / "27%" near words
like "hard" / "v4_hard" / "violation" — anywhere those v5 numbers
leaked into the prose, they need to be updated.

### 4.3 exp_exact_dg per-tier consistency

Mean d_G = 580.37, Spearman ρ vs flat-count = 0.5625. The 180 episodes
break down by hard-violation tier; the per-tier mean d_G should
monotonically increase with tier severity. **This was not verified in
this session.** A manual paper-defense run should plot tier-vs-d_G
and confirm monotonicity.

### 4.4 Step 11 judge fail-closed

Mgmt-Plan v1: 0/180 pass. Mgmt-Plan v2: 0/180 pass. Safety_v1: 1/180
pass. **One judge variant of four behaves usefully** (Safety_v2:
55/180). This is suspicious — under the canonical 397B judge, the v5
text reports more diverse pass rates. Either:

- gemma-4-31b is too conservative for the management-plan task (likely
  — gemma is an instruct model, and "is this management plan safe?"
  is a refusal-prone question), or
- The prompts in `terminal_output_baselines.py` were tuned for 397B's
  latent capability and don't transfer to a 31B model.

The data for Mgmt-Plan v1/v2 / Safety_v1 columns under gemma is
**published-but-uninformative**. The paper text should not interpret
their 0% mis-cert as "the LLM judge is well-calibrated"; it is "the
LLM judge passes nothing".

---

## 5. Concrete action items, ordered by paper-criticality

| # | Item | Severity | Estimated time |
|---:|---|---|---:|
| 1 | Acknowledge nemotron30b 21-empty in §Reproducibility | **MEDIUM** | 10 min |
| 2 | Re-run Step 11 against canonical 397B judge (or footnote the gemma substitution) | **MEDIUM** | 30 min if 397B endpoint exists |
| 3 | Audit paper text for v5-frozen "48 hard / 27%" numbers from instrumentation fixture | **MEDIUM** | 15 min grep + edit |
| 4 | Decide fate of 9 stale Apr 3–17 evidence files (re-run vs appendix-relabel) | MEDIUM | per-file decision; 30 min planning |
| 5 | Drop AC-Proxy/ACov duplicate row from paper tables | LOW | 5 min |
| 6 | Commit `clean_slate_rescored` fixture into `data/methodology_fixture/` | LOW | 10 min |
| 7 | Add judge-model footnote to `terminal_output_baselines.tex` | LOW | 5 min |
| 8 | Audit remaining v5 defense scripts for hardcoded asserts | LOW | 30 min |
| 9 | Change `verdict_matrix_v5.py` default RESULTS_DIR to v6a_706 | LOW | 2 min |
| 10 | Document gemma31b 1.99% empty rate in §Limitations (auto_v2 only, not in paper subset) | LOW | 5 min |

Items 1–4 are **must-fix** before camera-ready. Items 5–10 are
hygiene; the paper survives without them but a careful reviewer will
notice.

---

## 6. What this review explicitly did NOT verify

- Per-CPG-graph compliance distributions (would require re-running
  `exp_c_generalizability` on v6).
- Cross-family pillar-3 ratios beyond the 7 already verified
  (memory `project_track_a_cataloguer_run_20260426`).
- The 144-side qwen397b/nemotron30b episode files for byte-level
  parity with the 146 path (memory says rsync was performed
  end-of-run; not re-checked here).
- The `evidence_pack/all_numbers_v5.json` historical record vs the
  newly-extracted `auto_numbers_v6.tex` macro-by-macro diff (only
  the 25 macros that changed were tabulated; macros that DIDN'T
  change were not double-confirmed identical).
- Any metric outside the verdict-flip / BSR / d_G / mis-cert family
  — clinician validation κ, AMEGA cross-benchmark replication,
  CRES-series defenses, etc.

These are the natural next critical-review passes if a reviewer
asks deeper questions. None of them is in scope for the v6
auto-numbers regeneration that the user requested.

---

## 7. Bottom line

The v6 auto-numbers are **fit for paper inclusion** with the
following caveats explicitly disclosed:

1. **Nemotron30b 21/2,118 = 0.99% empty episodes** in the paper
   subset; treated as v4_hard=True; minor rate-shift on nemotron's
   row; archive path documented.
2. **Step 11 LLM judge is gemma-4-31b** (substitute), not the
   canonical Qwen3.5-397B; Mgmt-Plan rows are uninformative under
   this substitute; Safety_v2 row is the only meaningful baseline.
3. **9 v5-era evidence files (Apr 3–17)** were not refreshed; their
   downstream paper sections need a refresh-or-relabel decision.

Everything else is internally consistent, reproducible from the
shipped code paths, and matches the project memory record. No
headline number reverses sign or changes interpretation.
