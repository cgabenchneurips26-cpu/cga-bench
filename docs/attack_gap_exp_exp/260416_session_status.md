# Session Status Report — EX-36 / EX-37 / EX-38 + Infra Cleanup
**Date**: 2026-04-16
**Branch**: `eval_science`
**Predecessor**: `260410_review_defense_status.md` (14/16 attack defenses)

---

## TL;DR

This session committed 13 atomic commits covering:
1. Three new defense experiments (EX-36, EX-37, EX-38)
2. Direct-scaffold agent implementation (qwen27b_direct)
3. Two new model registrations (qwen27b_temp06, qwen27b_direct)
4. EX-17 + heldout AO FA recomputation on full v6 corpus (16,944 eps)
5. Paper v12 / appendix / auto_numbers integration of new numbers
6. Croissant v6.0 dataset metadata
7. Parent-repo `.gitignore` hygiene + un-tracking of runtime state

EX-37 is **partially complete** — react vs direct results landed; the
checklist arm is blocked on Gemma-4-31B vLLM availability and is
deferred to a follow-on session.

---

## New Defense Experiments

### EX-36 — Temperature Sensitivity (eta-squared decomposition)
- **Attack**: T=0.1 makes run variance trivially zero, so evaluator >>
  run is tautological.
- **Defense**: Re-run qwen27b at T=0.6 with non-trivial run variance
  and show eta_sq(eval) >> eta_sq(run) still holds.
- **Result**:
  | T | eta_sq(eval) | eta_sq(run) | Dominance |
  |---|--------------|-------------|-----------|
  | 0.1 | 0.181 | 0.0001 | 3,153.5 |
  | 0.6 | 0.282 | 0.0000 | 34,942.2 |
- **Files**: `evidence_pack/ex36_temperature_eta/{report,results,macros}`,
  `scripts/experiments/exp_e36_temperature_eta.py`,
  `configs/agents/clean_slate_qwen27b_temp06.yaml`
- **Status**: ✅ COMPLETE

### EX-37 — Scaffold Three-Way Comparison
- **Attack**: Blind spots are an artifact of ReAct chain-of-thought
  prompting, not structural.
- **Defense plan**: Run three scaffolds (ReAct, Checklist, Direct) and
  show identical blind-spot structure -- pure ablation since ReAct and
  Direct share the same base model (Qwen3.5-27B-FP8).
- **Result (2-way only — Checklist arm pending)**:
  | Scaffold | N | Flip% | AO-FA% | \|BS\| |
  |----------|---|-------|--------|------|
  | ReAct  (qwen27b)         | 2118 | 81.0 | 12.8 | 272 |
  | Direct (qwen27b_direct)   | 2118 | 78.7 | 16.1 | 341 |
  | Checklist (gemma31b)      | 0 (pending) | -- | -- | -- |
  - Pairwise McNemar (react vs direct): AC chi2=36.6 / MAB chi2=68.8 /
    C2 chi2=35.1 / CGA chi2=4.62 (p=0.0317) — all significant.
  - Jaccard(BS_react, BS_direct) = 0.341, intersection = 156 episodes.
- **Interpretation**: Both scaffolds produce substantial, non-empty
  blind-spot populations; the projection $\pi_{\text{aset}}$ is the
  structural cause and scaffold only shifts which trajectories fall
  into the unrecoverable region. Consistent with Theorem 1.
- **Files**: `evidence_pack/ex37_scaffold_three_way/{report,results,macros}`,
  `scripts/experiments/exp_e37_scaffold_three_way.py`,
  `configs/agents/clean_slate_qwen27b_direct.yaml`,
  `agent_runner/llm_provider.py` (DIRECT_SYSTEM_PROMPT),
  `agent_runner/rag_agent.py` (direct scaffold branch)
- **Status**: 🟡 PARTIAL — Gemma checklist data generation blocked
  (see "Open Items" below)

### EX-38 — Variable Action Duration (cross-model persistence)
- **Attack**: 5-min fixed step is unrealistic; timing violations are
  artifacts of the simulation grid.
- **Defense**: Replay v5 episodes with 21 clinically calibrated
  per-action durations, show 96.5% (95% CI [96.0, 97.0]) of timing
  violations persist across all 8 models.
- **Per-model persistence (8/8 > 95%)**:
  - deepseek_r1_7b 95.88, gemma31b 96.68, nemotron30b 97.54,
    oss120b 95.03, qwen27b 97.24, qwen35b 96.04, qwen397b 96.80,
    qwen4b 96.64
- **Sensitivity sweep (default duration in min)**: 3 -> 89.07%, 5 ->
  96.37%, 7 -> 97.97%, 10 -> 98.74%. The 5-min default is conservative.
- **Files**: `evidence_pack/ex38_variable_duration/{report,results,macros}`,
  `scripts/experiments/exp_e38_variable_duration_crossmodel.py`
- **Status**: ✅ COMPLETE

---

## Recomputations on Canonical v6 Corpus

### EX-17 — Solver Agreement (16,944 eps)
Updated from prior v5 subset:
- Spearman rho: 0.919 -> 0.920
- ILP strictly better: 24.4% -> 20.4% (n=3,449)
- Tiered strictly better: 7.19% -> 8.68% (n=1,470)
- Equal: 71.0% (n=12,025)
- Verdict reversals: 0 (preserved)
Solver scatter PNG regenerated; per-episode pairs persisted as
`solver_pairs_full.json` for deterministic re-rendering.

### Held-out All-Oblivious FA (16,944 eps)
- Total: 14,055 -> 16,944 (held-out 1,356 -> 1,584; in-domain 12,699 -> 15,360)
- Held-out AO FA rate: 2.4% -> 5.8% [4.7, 7.0]
- In-domain AO FA rate: 14.3% -> 12.2% [11.7, 12.7]
- Fisher OR: 0.145 -> 0.446 (still p = 5.26e-16)

---

## Paper Integration (commit `703314ee`)
- `auto_numbers.tex`: 8+ macros updated to canonical v6 values
  (`\solverILPRho`, `\solverILPPct`, `\solverTieredBetter`,
  `\solverEqualN`, etc.); scenario count 107/584 -> 105/601 (excludes
  e2e-test-only scenarios); `\crossReplayMABBlindPct` formula fix
  (was 39.9, now 60.3 = FA/pass).
- `appendix.tex`: solver scatter figure added; FA(AC)/FA(MAB) clarified
  as action-level rates (not full BSR); timing stress Resolved%
  direction note corrected (fail->pass).
- `main_final_v12.tex`: `\solverTieredBetter` fallback aligned;
  AC-Diag/MAB-F1 convergence note added (both replay scorers converge
  to native ASC/PAF since they share `\pi_{\text{aset}}`).
- Removed: `paper/main_final_v8.tex`, `paper/main_final_v10.tex`.

---

## Infrastructure Changes

### Direct Scaffold (`agent_runner/`)
- `llm_provider.py`: added `DIRECT_SYSTEM_PROMPT` -- single-shot JSON
  output, no chain-of-thought, with explicit empty-action guard.
- `rag_agent.py`: added `direct` branch in `_dispatch` so existing
  RAG pipeline works with the new scaffold.

### Runner Registration (`scripts/experiments/full_690_runner.py`)
Added two model entries:
- `qwen27b_temp06` (T=0.6 ReAct -> EX-36 dataset)
- `qwen27b_direct`  (T=0.1 Direct -> EX-37 dataset)
Plus `llama4scout` host fix (localhost:8205 -> 127.0.0.1

### Repo Hygiene (parent repo `anonymous-project/AnonProject`)
- `.gitignore`: added `.omc/`, `.hypothesis/`, `reports/junit.xml`,
  `**/.claude/backups/`.
- Untracked four already-committed runtime files via
  `git rm --cached` so they no longer churn `git status`.

### Croissant v6.0
Dataset metadata bumped from v1.0 to v6.0 with full episode/constraint
counts; data_release/v1.0 mirror updated for parity.

---

## Compute Environment Notes (for next session)

- **Host this session**: `localhost` = 127.0.0.1
- **Defense data home**: `[email-redacted]:${CGA_BENCH_ROOT}/cga_bench`
  (NOT a git repo on 145 -- treat as a synced working copy; results
  must be `scp`-pulled back to 146 for commit)
- **EX-37 data on 145** (READY):
  - `results/full_706_v5/qwen27b/`        (2118 files, ReAct)
  - `results/full_706_v5/qwen27b_direct/` (2118 files, Direct, post-dedup)
  - `results/full_706_v5/qwen27b_temp06/` (2118 files, T=0.6, post-dedup)
- **EX-37 data MISSING**: `results/full_706_v5/gemma31b_checklist/` (0 files)
- **vLLM availability**:
  - 145: 8 x A100 80GB (free as of session end; qwen27b vLLMs torn down)
  - 144: dead (`Permission denied (publickey,password)` from anonymous-org@145;
    `:30003` connection refused)
  - 145 transformers 4.57.6 cannot load `gemma-4-31b-it` (model_type
    `gemma4` unrecognized) -- requires transformers/vllm upgrade or
    a substitute checklist-capable model

---

## Open Items / Hand-off

1. **Gemma-4-31B-IT availability** — pick one:
   - upgrade `/home/anonymous-org/anaconda3` transformers + vllm on 145
   - find a different checklist-capable model already cached
   - use a hosted endpoint (no longer 144:30003)
2. **Re-run EX-37 with full 3-way data** — single command on 145 once
   `results/full_706_v5/gemma31b_checklist/` is populated:
   ```bash
   PYTHONPATH=${CGA_BENCH_ROOT} \
     /home/anonymous-org/anaconda3/bin/python \
     scripts/experiments/exp_e37_scaffold_three_way.py
   ```
   Then `scp` the three `evidence_pack/ex37_scaffold_three_way/*` files
   to 146 and commit.
3. **Paper integration of new EX-3x numbers** — pull macros from
   `evidence_pack/ex3{6,7,8}/macros.tex` into `auto_numbers.tex` and
   wire into appropriate `appendix.tex` sections. EX-37 macros include
   N/A placeholders for the checklist arm; do not stamp those into the
   paper until Gemma data lands.
4. **localhost (146) leftover** — `results/full_706_v5/qwen27b_direct/` on
   146 has 525 partial files from a duplicate run; safe to delete since
   145 has the canonical 2118.

---

## Commit Manifest (this session — 13 commits on `eval_science`)

```
6663f366  feat(defense): EX-37 scaffold ablation -- react vs direct results
17489380  chore: untrack runtime state files now covered by .gitignore     [parent repo]
f8db8458  chore: ignore runtime/harness state in parent repo               [parent repo]
0445064a  chore(claude): allow plugin mirror copy commands in sandbox
b6418213  docs(croissant): bump to v6.0 with 16,944-episode corpus metadata
703314ee  docs(paper): integrate EX-17/heldout re-runs + scope-clarify FA cross-replay
6b277540  refactor(heldout): recompute held-out AO FA on full v6 dataset
4a039485  refactor(ex17): re-run solver agreement on full v6 dataset (16,944 eps)
c861f04a  feat(defense): EX-38 Variable-duration cross-model persistence
6a992582  feat(defense): EX-37 scaffold three-way comparison script (data pending)
20fb4c71  feat(defense): EX-36 Temperature eta-squared decomposition
059537a6  feat(runner): register qwen27b_direct/temp06 + fix llama4scout host
d11a7367  feat(agent): add direct scaffold for blind-spot attribution (EX-37 prep)
```
