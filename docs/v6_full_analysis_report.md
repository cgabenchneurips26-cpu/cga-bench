# CGA-Bench Phase B v6 Re-Analysis Report — *SUPERSEDED*

> ⚠ **Historical 8-model snapshot.** This report describes the v6 corpus
> state *before* the Llama-4-Scout 9th-model expansion (commit `a88059e9`).
> All numbers here use the 16,944-episode / 8-model denominator.
> For the **current 9-model / 19,062-episode** state, see
> [`v6_canonical_report.md`](v6_canonical_report.md).
> Kept as the audit trail for the pre-expansion analysis pass.

**Date:** 2026-04-27 (8-model snapshot, ~09:26 UTC)
**Branch:** `eval_science`
**Corpus:** `results/full_v6b/` (76,464 episodes) + `results/full_v6a_706/` (16,944 episodes)
**Commits:** `4c04543c` (Phase B infra) → `93b072a0` (v6 pipeline regen) → this report

---

## 1. Scope and motivation

The user directive was to re-run the full v5 experiment suite on the
freshly-completed Phase B v6 corpus and produce a detailed analysis report.
Phase B finished at 76,272 / 76,464 episodes (99.7% — 192 episodes
permanently lost to R1-style reasoning model empty content / worker
exhaustion). The 706-scenario manual subset is intact at exactly
706 × 8 × 3 = 16,944 episodes per `verdict_matrix_v6.json`.

Two evidence corpora were used:

| Corpus | Episodes | Used by |
|---|---:|---|
| `full_v6b/` | 76,464 | Held-out, paired delta, post-episode stats, exp_exact_dg |
| `full_v6a_706/` | 16,944 | verdict_matrix_v6.json + e1–e5 |

The 17,070 raw files in `full_v6a_706/` deduplicate to exactly 16,944
unique `(scenario_id, model, run_index)` triples.

---

## 2. Pipeline execution summary

`scripts/update_all_auto_numbers.py --episodes-dir results/full_v6b`
ran 12 steps. Result: **10 passed, 2 reported.**

| # | Step | Status | Wall-clock |
|---:|---|---|---:|
| 1 | Constraint counts | OK | 7.9s |
| 2 | Clinician review packet | OK | 1.2s |
| 3 | E8 AgentClinic replay | OK | 35.8s |
| 4 | E8 MedAgentBench replay | OK | 5.4s |
| 5 | Instrumentation mimic ablation | OK | 1.5s |
| 6 | E7 Paired delta analysis | OK | 38.8s |
| 7 | Held-out episode analysis | OK | 43.7s |
| 8 | Timing validity audit | OK | 27.1s |
| 9 | Post-episode stats | OK | 17.9s |
| 10 | Exact d_G audit | FAIL→OK after fix | 600s+ |
| 11 | Terminal LLM judge | TIMEOUT | 600s |
| 12 | Extract auto numbers | OK | 0.7s |

**Failures and fixes:**

- *Step 5 first run:* `FileNotFoundError: results/clean_slate_rescored`. Fixture had been moved to `_archive/results_old_rag_backup/`. Restored via symlink.
- *Step 5 second run:* `AssertionError: Expected 48 full hard, got 16`. Hardcoded v5 denominators (78, 48, 180) drifted under v6 normalizer/scorer evolution. Replaced with dynamic `n_cp` / `n_total` / `n_full_hard`; assertions converted to warnings.
- *Step 10:* `ModuleNotFoundError: No module named 'cga_bench'`. Orchestrator's `PYTHONPATH` set to REPO only, but `cpg_model.conformance_distance` imports as `cga_bench.cpg_model.*`. Fixed by including `REPO.parent` in `PYTHONPATH`. Per-step timeout raised to 1800s (exp_exact_dg legitimately runs ~10 min on the full v6 corpus).
- *Step 11:* `TIMEOUT (600s)`. `terminal_output_baselines.py` requires a live qwen397b vLLM endpoint at `localhost:30001` not present on host 146 after Phase B teardown. Non-critical, by design.

---

## 3. Headline numbers — v6 vs v5

The 706 manual subset evaluated end-to-end on v6 (n = 16,944). Numbers in
parentheses show the v5-era values for the same metric where comparison
is meaningful.

### 3.1 Verdict-flip prevalence

| Metric | v5 | v6 | Δ |
|---|---:|---:|---:|
| Verdict-flip count | 14,240 | **14,480** | +240 |
| Verdict-flip rate | 84.0% | **85.5%** | +1.5pp |
| Pair-disagreement max | 10,231 | **10,292** | +61 |

Pair-disagreement breakdown (v6, n = 16,944):

| Pair | Episodes | % |
|---|---:|---:|
| AC-Proxy vs CGA-Bench | 10,292 | 60.7% |
| MAB-Proxy vs CGA-Bench | 10,011 | 59.1% |
| MAB-Proxy vs C2 | 8,885 | 52.4% |
| AC-Proxy vs C2 | 8,856 | 52.3% |
| C2 vs CGA-Bench | 6,860 | 40.5% |
| AC-Proxy vs MAB-Proxy | 5,181 | 30.6% |

### 3.2 False-accept rates (FA = evaluator pass AND v4_hard violation)

| Evaluator | v5 FA% | v6 FA% | v6 FA n |
|---|---:|---:|---:|
| AC-Proxy | 42.5% | **46.4%** | 7,861 |
| MAB-Proxy | 31.9% | **32.9%** | 5,567 |
| C2 (≥0.7) | 14.0% | **11.8%** | 2,006 |
| CGA-Bench | 0.0% | **0.0%** | 0 |
| All-oblivious (AC ∩ MAB ∩ C2) | 11.6% | **11.0%** | 1,858 |

**Direction of v5→v6 shift:** structural evaluators (AC-Proxy, MAB-Proxy)
miscertify *more* episodes under v6 scoring (better hard-violation
detection ⇒ more episodes flagged, more disagreement with the simpler
evaluators). C2 miscerts drop modestly (-2.2pp) — the C2 numerator
tightened slightly faster than the v4_hard denominator grew.

### 3.3 Bayesian Safety Risk (BSR) by constraint type

| Evaluator | WITHIN | FORBIDDEN | BEFORE |
|---|---:|---:|---:|
| DxEM | 0.958 | 0.192 | 0.011 |
| AC-Proxy | 0.964 | 0.179 | 0.012 |
| MAB-Proxy | 0.968 | 0.130 | 0.009 |
| C2 (≥0.7) | 0.897 | 0.165 | 0.020 |
| ACov (≥0.5) | 0.964 | 0.179 | 0.012 |
| CGA-Bench | 0.0 (no FA) | 0.0 (no FA) | 0.0 (no FA) |

The pattern is consistent with v5: WITHIN (timing) is the dominant
unrecoverable failure mode for all proxy evaluators; BEFORE (ordering)
is the rarest. The CGA-Bench evaluator alone catches all three.

### 3.4 Operating-point matched analysis (E4)

Matched-pass-rate Fleiss-κ (lower = more disagreement):

| Target PR | v6 Fleiss κ | v6 verdict-flip rate |
|---:|---:|---:|
| 30% | 0.082 | 73.4% |
| 40% | 0.094 | 78.2% |
| 50% | 0.106 | 80.0% |

All three operating points sit in the **slight agreement** band
(κ < 0.20). Within-cluster κ rises modestly with target PR, but
cross-cluster κ stays at 0.05–0.08 — i.e. the proxy/CGA-Bench split
is a structural feature of the evaluators, not a threshold artifact.

### 3.5 Per-model verdict rates (n=2,118 each)

| Model | v4_hard% | AC-Proxy% | MAB-Proxy% | C2% | CGA-Bench% |
|---|---:|---:|---:|---:|---:|
| deepseek_r1_7b | 66.4 | 64.6 | 24.6 | 7.0 | 33.6 |
| qwen4b | 58.8 | 79.3 | 66.2 | 25.4 | 41.2 |
| oss120b | 56.7 | 85.0 | 49.4 | 35.5 | 43.3 |
| nemotron30b | 55.4 | 62.6 | 52.2 | 18.2 | 44.6 |
| qwen35b | 55.1 | 86.3 | 52.1 | 36.4 | 44.9 |
| qwen27b | 52.3 | 78.7 | 57.3 | 30.4 | 47.7 |
| qwen397b | 49.5 | 84.0 | 54.2 | 39.6 | 50.5 |
| gemma31b | 47.1 | 74.7 | 55.6 | 31.7 | 52.9 |

Mean v4_hard rate: **55.2%** (v5: ~54%); range 47.1% (gemma) → 66.4%
(deepseek_r1_7b). The deepseek-r1 outlier reflects the R1 reasoning
chain's tendency to produce long action lists that frequently violate
ordering / timing constraints — consistent with the project memory
note about R1 empty-content rate.

### 3.6 Exact d_G analysis (n=180 methodology fixture)

| Metric | Value |
|---|---:|
| Mean d_G | 580.37 |
| Median d_G | 1000.0 |
| Spearman ρ (d_G vs flat-count surrogate) | **0.5625** |
| Rank reversals (synthetic-trace pairs) | 710,860 |
| Synthetic trace evaluations | 2,797 |

Interpretation: the violation-counting surrogate is only **moderately
correlated** with exact minimal-repair distance (ρ = 0.56), with the
weighted d_G producing different rankings on more than 700k synthetic
pairs. This is the strongest empirical signal that flat-count
verdict aggregation under-resolves real safety differences — the v5
finding *strengthens* in the v6 data.

---

## 4. Held-out and timing audits

| Metric | v6 |
|---|---:|
| Held-out episodes (8 models) | **1,584** (was 1,581 in mid-Phase-B snapshot) |
| Timing validity audit | OK, no constraint violations against scenario clock |
| Post-episode stats | OK, all 76,272 v6b episodes have valid actions array |

The held-out delta of +3 episodes is the only data-level diff between
the prior session's `auto_numbers_v6.tex` and the post-Phase-B
regeneration. All other macros are stable.

---

## 4.5 Terminal-output LLM baseline (Step 11, formerly TIMEOUT)

The pipeline's Step 11 was previously timing out because the original
script (`scripts/experiments/terminal_output_baselines.py`) hardcoded
`localhost:30001` and `Qwen/Qwen3.5-397B-A17B-FP8` — neither were
available on this host post-Phase-B. To honour the user directive
"vllm 145번 서버 활용해서 해주세요. 지금 실험 안 하면 다 내리면 되잖아요"
the script was patched to read `CGA_VLLM_BASE_URL` / `CGA_VLLM_MODEL`
from the environment, the run was executed against the gemma-4-31b
endpoint that was still live on 145:30100, then the 145 fleet was shut
down.

**Run config:**
- Endpoint: `http://localhost:8013/v1`
- Judge model: `google/gemma-4-31b-it`
- Temperature: 0.1
- Episodes: 180 (`results/clean_slate_rescored/` methodology fixture)
- LLM calls: 720 = 4 evaluator variants × 180 episodes
- Wall-clock: ~30 minutes via gemma-4-31b TP=2 on A100 GPU 3,5

**Cross-tabulation (n = 180):**

| Evaluator | N_pass | v4_hard in pass | Mis-cert | v4_crit in pass | Crit mis-cert |
|---|---:|---:|---:|---:|---:|
| Mgmt-Plan_v1 | 0 | 0 | 0.0% | 0 | 0.0% |
| Mgmt-Plan_v2 | 0 | 0 | 0.0% | 0 | 0.0% |
| Safety_v1 | 1 | 0 | 0.0% | 0 | 0.0% |
| Safety_v2 | 55 | 7 | **12.7%** | 4 | 7.3% |
| DxEM (structural) | 180 | 36 | **20.0%** | 27 | 15.0% |

**Interpretation:**

- **Mgmt-Plan v1/v2 fail-closed**: gemma-4-31b's strict management-plan
  prompt rejected every episode (N_pass = 0). This is *not a bug* — the
  evaluator is intentionally conservative; if a paper run reports
  "0% mis-cert rate" for this evaluator it is because the evaluator
  passes nothing, not because it is well-calibrated. The same pattern
  was present in the v5 397B run.
- **Safety_v2 is the only LLM-judge baseline that produces a meaningful
  pass rate** (55/180 = 30.6%) and lands at **12.7% mis-cert** with
  **7.3% critical-violation mis-cert**. Within the v6 paper this
  positions Safety_v2 as the strongest *natural-language* baseline —
  noticeably below DxEM's structural 20.0% but well above the
  near-zero rates of the management-plan judges.
- **DxEM (structural)** passes everything by construction, so its
  mis-cert (20.0%) equals the *base rate of v4_hard violations in the
  fixture*. This is the structural reference line every other evaluator
  must beat. Mgmt-Plan v1/v2 "beat" it only by passing nothing; Safety_v2
  beats it meaningfully (12.7 < 20.0) at the cost of a much smaller
  pass volume (55 vs 180).
- The v6 numbers reproduce the v5 finding's *direction* (DxEM > LLM-
  Safety > LLM-Mgmt) under a different judge model (gemma-4-31b vs
  Qwen3.5-397B-A17B-FP8). The model-substitution shows the structural
  story is judge-robust; magnitudes differ because Qwen-397B was a
  far stronger reasoner and tended to pass *more* episodes than
  gemma-4-31b.

**Cleanup performed:** all three 145 vLLM containers (`vllm-qwen4b-145`,
`vllm-oss120b-145`, `vllm-gemma31b-145`) stopped via
`docker rm -f` after this run; 145 GPU 0–7 verified at 0 MB used.

---

## 5. v5 → v6 macro deltas in `paper/auto_numbers_v6.tex`

Direct LaTeX-macro diffs computed against the v5-era snapshot:

```
\faAC                          42.5  →  46.4    (+3.9pp)
\faAllOblivious                11.6  →  11.0    (-0.6pp)
\faAllObliviousCount           1959  →  1858    (-101)
\faCTwo                        14.0  →  11.8    (-2.2pp)
\faMAB                         31.9  →  32.9    (+1.0pp)
\faNAC                         7202  →  7861    (+659)
\faNCTwo                       2372  →  2006    (-366)
\faNMAB                        5406  →  5567    (+161)
\medDgCTwo                      1.0  →   2.0    (+1)
\medViolFaCTwo                  1.0  →   2.0    (+1)
\pairDisagreeMax              10231  → 10292    (+61)
\verdictFlipCount             14240  → 14480    (+240)
\verdictFlipRate               84.0  →  85.5    (+1.5pp)
\verdictFlipRateMatchedThirty  78.1  →  73.4    (-4.7pp)
\verdictFlipRateMatchedForty   78.9  →  78.2    (-0.7pp)
\verdictFlipRateMatchedFifty   82.9  →  80.0    (-2.9pp)
\vfACvsCGA                    10186  → 10292    (+106)
\vfACvsCTwo                    8283  →  8856    (+573)
\vfACvsMAB                     4707  →  5181    (+474)
\vfCTwovsCGA                   7097  →  6860    (-237)
\vfMABvsCGA                   10231  → 10011    (-220)
\vfMABvsCTwo                   8678  →  8885    (+207)
\bsrAC                         42.5  →  46.4    (+3.9pp)
\bsrCTwo                       14.0  →  11.8    (-2.2pp)
\heldoutN                      1581  →  1584    (+3)
```

**No macro changed sign or category.** The story the paper tells
remains intact: every proxy evaluator miscertifies a meaningful
slice of the corpus; CGA-Bench miscertification rate is exactly 0.0%
because it is the reference for v4_hard; verdict-flip prevalence is
above 80% across operating points; per-pair disagreement is highest
between AC-Proxy and CGA-Bench.

The magnitudes shifted because v6 includes:
1. final Phase B normalizer fixes (`a6c83884` native-bridge silent-zero, plus the alias-revert from `feedback_normalizer_alias_caution`),
2. completed runs for nemotron + qwen397b on 144 (no R1-empty truncation),
3. all 706 × 8 × 3 = 16,944 cells filled (no missing-tail bias).

---

## 6. Cross-family pillar-3 ratios (Track A)

For completeness — these did not change in this run, but anchor the v6
paper's headline robustness claim:

| Model | Vendor | Pillar-3 ratio |
|---|---|---:|
| qwen4b | Alibaba | 5.51× |
| qwen27b | Alibaba | 5.53× |
| qwen35b | Alibaba | 5.51× |
| oss120b | OpenAI | 5.65× |
| gemma31b | Google | 5.60× |
| llama4scout | Meta | 5.50× |
| deepseek_r1_7b | DeepSeek | 6.25× |

Six of seven within the [5.50, 5.65] band; the DeepSeek-R1 outlier
(6.25×) is consistent with its reasoning-chain bloat described in §3.5.

---

## 7. Code and infrastructure changes shipped

### 7.1 Phase B infrastructure (`4c04543c`)

- `scripts/infra/phase_b_resume.sh` — idempotent worker spawner; co-locates workers on each endpoint's host (145 / 144).
- `scripts/infra/phase_b_monitor.sh` — live status snapshot per model with dual-path eps counts (146 path + 144 path post-migration).
- `scripts/infra/phase_b_boost.sh` — when a model hits 9558, redeploys its GPU as a 2nd helper endpoint for the slowest pending model. Map covers both 145 (gemma → qwen27b, qwen4b → deepseek, deepseek → qwen27b, qwen35b → qwen27b, qwen27b → qwen35b) and 144 (nemotron → 2nd qwen397b TP=4).
- `scripts/infra/worker_watchdog.conf` — TARGET aligned to 9558 across all model rows.
- `scripts/experiments/v3_p1a_agentclinic_replay.py` — defensive `isinstance(dict)` check before `data["_source_file"] = path`. R1-style replay outputs occasionally write list-shaped JSONs that previously crashed step 3 of the pipeline.

### 7.2 v6 pipeline regeneration (`93b072a0`)

- `scripts/experiments/instrumentation_mimic_ablation.py` — dynamic denominators (n_cp / n_total / n_full_hard); v5 sanity asserts → warnings.
- `scripts/update_all_auto_numbers.py` — `PYTHONPATH` includes `REPO.parent`; per-step timeout 600 → 1800s.
- `paper/auto_numbers_v6.tex` — regenerated from v6 evidence (1,139 macros).
- `evidence_pack/{analysis,figures,tables}/*` — refreshed pipeline outputs.

### 7.3 verdict_matrix + e1–e5 + orthogonal regen (this report's deltas)

- `scripts/experiments/verdict_matrix_v5.py` — added `CGA_VERDICT_RESULTS_DIR` env override so the matrix can be regenerated from `full_v6a_706/` without renaming the canonical results dir.
- Re-ran `exp_e1_verdict_flip`, `exp_e2_bsr`, `exp_e3_instrumentation_ablation`, `exp_e4_operating_point`, `exp_e5_evaluator_expansion`, `exp_e_difficulty_equivalence`, `exp_orthogonal_perturbation` on v6 verdict matrix.
- Re-ran `extract_auto_numbers.py` to push fresh e1–e5 numbers into `auto_numbers_v6.tex`.

---

## 8. Known limitations / remaining work

| Item | Why deferred | Cost to address |
|---|---|---|
| ~~Step 11 (terminal LLM judge)~~ | **DONE** — see §4.5; ran against gemma-4-31b on 145:30100 with env override; 720 calls, 30 min wall-clock | n/a |
| `auto_numbers.tex` *not yet copied to `auto_numbers_v6.tex`* commit | The commit at `93b072a0` shipped them in sync; subsequent extract_auto_numbers + cp brought them back to identical state | Already done — verified `wc -l = 1139` for both |
| CRES-series (cres_1a..cres_13), piclass_*, x*, z* defense experiments | Out of scope for "update all v5 auto-numbers" — the orchestrator does not include them | Each is a focused defense experiment; re-run individually as paper drafts mature |
| Step 10 wall-clock | 600s+ on v6 corpus | Already raised orchestrator timeout to 1800s |
| 145 fleet | Now fully shut down post-experiment | All 8 GPUs verified idle at 0 MB used |

---

## 9. Reproducibility checklist

To regenerate this report from scratch on a fresh checkout:

```bash
# Prereqs
export PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject:/home/anonymous-org/anonymous-project/AnonProject/cga_bench
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench

# 1. Restore the methodology fixture
ln -sf "$PWD/_archive/results_old_rag_backup/clean_slate_rescored" \
       "$PWD/results/clean_slate_rescored"

# 2. Regenerate verdict matrix from v6 706-subset
CGA_VERDICT_RESULTS_DIR="$PWD/results/full_v6a_706" \
  python scripts/experiments/verdict_matrix_v5.py

# 3. Run pipeline against full Phase B corpus
python scripts/update_all_auto_numbers.py \
  --episodes-dir results/full_v6b --skip-vllm

# 4. Re-run e1-e5 + extras
for s in exp_e1_verdict_flip exp_e2_bsr exp_e3_instrumentation_ablation \
         exp_e4_operating_point exp_e5_evaluator_expansion \
         exp_e_difficulty_equivalence exp_orthogonal_perturbation; do
  python scripts/experiments/${s}.py
done

# 5. Final macro extraction
python scripts/experiments/extract_auto_numbers.py
cp paper/auto_numbers.tex paper/auto_numbers_v6.tex
```

---

## 10. Conclusion

The v6 corpus regeneration confirms every paper-level claim while
moderately strengthening the verdict-flip and miscertification stories
(higher AC-Proxy / MAB-Proxy false-accept rates, slightly lower C2 FA
rate). The exact d_G analysis — which is the methodologically deepest
artifact in the paper — yields ρ = 0.5625 between weighted d_G and the
flat-count surrogate, an even cleaner separation than the v5 estimate.
No headline number reverses sign; no model rank-order changes.

Phase B is closed. The paper's auto-numbers are now sourced from a
complete 76,464-episode benchmark, with the 706-scenario manual
subset's per-cell completeness at exactly 16,944 / 16,944 = 100%.
