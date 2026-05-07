# P2 — Paper Macro Regeneration & v6 Unification Plan

_2026-04-22 · branch: eval_science_

## Context

The full_706_v6 re-sweep (16,944 episodes, 8 models × react) completed
at 2026-04-22 08:58. Summary stored in
``evidence_pack/analysis/full_706_v6_summary.json``. The paper's
quantitative claims must be regenerated from this fresher data —
but the current macro aggregation pipeline was written for a
different axis layout. This doc tracks the regeneration plan.

## 1. Where paper macros come from (audit)

### `paper/auto_numbers.tex` (903 lines) and `auto_numbers_v2.tex` (906 lines)

Primary aggregator: ``scripts/experiments/extract_auto_numbers.py``.
Reads from the experiment-specific JSONs:

- ``evidence_pack/exp_e1_verdict_flip.json``
- ``evidence_pack/exp_e2_bsr.json``
- ``evidence_pack/exp_e3_instrumentation_ablation.json``
- ``evidence_pack/exp_e4_operating_point.json``
- ``evidence_pack/exp_e5_evaluator_expansion.json``

These JSONs are upstream of the macros; they in turn derive from
``full_706`` episodes but via experiment-specific analyzers. If we
swap the underlying sweep from v5 → v6, the E1-E5 analyzers need
to be re-run on the new episodes. Their *macros* are not directly
tied to "mean CS per model".

### Per-model leaderboard macros

Macros like ``\wEightComplianceMax = 0.796`` sit in a separate W8
section (`% W8 cross-model block` starting around line 679 of
`auto_numbers.tex`). They come from
``scripts/experiments/aggregate_ex_w8_crossmodel.py`` which reads
the old 3 models × 3 scaffolds W8 result directory and writes
``evidence_pack/ex_w8_crossmodel/{matrix.json, macros.tex, w8_table.tex}``.

### Ad-hoc model citations in prose

- ``paper/appendix.tex`` references `nemotron30b`, `gemma31b`,
  `deepseek_r1_7b`, `qwen397b` directly in prose (e.g., "$\geq 95\%$
  on three evaluators (nemotron30b for C2, deepseek_r1_7b for …)").
- ``paper/prompt_sensitivity_agent_table.tex`` lists a per-model ×
  per-scaffold table (oss120b/ReAct 85.4, oss120b/Direct 84.4, …) —
  this is data from the v5 W8 3×3 experiment, not auto-numbers.
- ``paper/main_final_v17.tex`` uses `\normalizerMM*` macros for a
  multi-model normalizer-ablation replay. These feed from a
  ``normalizer_ablation_replay`` JSON, not full_706 directly.

## 2. Figure file → data source dependencies

| Figure | Script | Data source | Status |
|---|---|---|---|
| 3 (cde) | ``paper/figures/make_figure3_cde.py`` | (to audit) | untracked in git; may be new |
| 4 (ranking) | ``paper/figures/make_figure4_ranking.py`` | ``evidence_pack/analysis/rank_bootstrap.json`` | **file missing** — needs regeneration |
| 5 (e1 only) | ``paper/figures/make_figure5_e1_only.py`` | ``exp_orthogonal_perturbation.json``, ``exp_before_only_perturbation.json`` | exists (unchanged) |
| 6 (w8 heatmap) | ``paper/figures/make_figure6_w8_aofa_heatmap.py`` | ``evidence_pack/w8_full/w8_results.json`` | exists (old W8 3×3) |

## 3. Scenario → domain mapping

Canonical helper at
``scripts/experiments/v3_p6_violation_spread.py::load_scenario_domain_map()``.
It parses all 25 scenario YAML files under ``configs/scenarios/``
and returns ``{scenario_id: domain_label}`` where
``domain_label`` derives from the ``guideline_graph`` field of each
scenario config. This is the right helper to import into a v6 per-
domain aggregator.

## 4. Axis mismatch: v5 W8 (3×3) vs v6 react (8×1)

The v5 W8 crossmodel experiment:
- Models: {oss120b, qwen35b, gemma31b}
- Scaffolds: {react, direct, checklist}
- Total cells: 9

The just-completed v6 sweep:
- Models: {qwen4b, qwen27b, qwen35b, gemma31b, oss120b, deepseek_r1_7b, nemotron30b, qwen397b}
- Scaffolds: {react}
- Total cells: 8

These don't compose into a single table. Two axis-unification
options exist:

### Option A — Keep both, new "CrossModel-v6" section

Treat v6 as a new experiment block. Add new `\crossModelV6*` macros
alongside the existing `\wEight*`. Paper gets two tables/figures:
"3 models × 3 scaffolds (V5 W8)" + "8 models × 1 scaffold (V6)".
Pros: zero additional compute. Cons: readers have to remember
which slice is which.

### Option B — Re-run v6 over all scaffolds (8 × 4 = 32 cells)

Adds {direct, checklist, tool_use} for all 8 models on top of the
existing v6 react data. Unified axis: 8 models × 4 scaffolds. W8
becomes a subset.
Pros: clean single matrix. Cons: ~12-15h additional wall-clock.

### Wall-clock estimate for Option B

The react-only v6 sweep: 16,944 episodes in 5.5 h (~51 eps/min
overall with the post-reshuffle parallel 145 layout + existing 144
endpoints). Scaling to 3 additional scaffolds:

- Additional scenarios per scaffold: 8 models × 706 × 3 = 16,944
- Total additional episodes: 50,832
- Total additional wall-clock at same throughput: ~16.5 h
- Real expectation (scaffold-specific latency differences and
  occasional tail-scenario drags): **12-15 h**, overnight-safe.

Per-scaffold notes:
- ``direct``: no chain-of-thought prefix → ~20 % faster per call;
  fewer LLM calls per episode.
- ``checklist``: similar to react in call count; prompt structure
  similar.
- ``tool_use``: structured-output parser is slower; ~20 % slower
  per call; fewer retries thanks to forced JSON.

Net: roughly the same total as running react 3 more times with
minor scaffold-dependent variance. **Budget 15 h**.

## 5. Recommendation

Go with **Option B (unify on v6 with all 4 scaffolds)**. Rationale:

1. Paper narrative simplifies — one sweep, one matrix, no
   scaffold-scope caveats sprinkled across sections.
2. 15 h overnight is small vs the review-cycle cost of explaining
   the axis mismatch.
3. V5 W8 stays on disk (archive to
   ``results/ex_w8_crossmodel_v5/``) — can still be cited if
   reviewers want a before/after comparison.

## 6. Execution plan (P2 work items)

### P2-a — Start v6 × {direct, checklist, tool_use} sweep (~15 h)
  - Reuse 145 vLLM layout (unchanged).
  - Launcher: same ``scripts/experiments/full_690_runner.py`` on
    each scaffold's config (``clean_slate_<model>_direct.yaml``
    etc.). Claim-file coordination keeps duplicates at zero.
  - Output dir: ``results/full_706_v6_scaffolds_{direct,checklist,tooluse}_<timestamp>/``.

### P2-b — Per-domain-aware aggregator (parallel with sweep)
  - Extend ``scripts/experiments/analyze_full_706_v6.py`` to
    import ``load_scenario_domain_map`` and emit
    ``per_domain[domain][model][scaffold]`` slices.
  - Unit test against the existing react-only data before the
    new scaffolds finish.

### P2-c — CrossModel-v6 macro emitter (parallel)
  - New script ``scripts/experiments/aggregate_full_706_v6.py``.
    Reads the four scaffold result dirs + scenario→domain map and
    writes:
    - ``evidence_pack/full_706_v6/matrix.json`` — 8 × 4 × 20
      domain cube.
    - ``evidence_pack/full_706_v6/macros.tex`` — ``\vSixCS<Model><Scaffold>``,
      ``\vSixDomain<Domain>Mean``, etc.
    - ``evidence_pack/full_706_v6/leaderboard_table.tex`` — paper-
      ready booktabs table.

### P2-d — Figure regeneration
  - Figure 4 — rebuild ``evidence_pack/analysis/rank_bootstrap.json``
    from the v6 matrix (bootstrap rank CIs per model × scaffold
    cell); regenerate ``paper/figures/figure4.png``.
  - Figure 6 — new v6 8×4 heatmap overlaying the v5 W8 3×3 as a
    zoomed inset, OR replace outright (decision deferred to
    after P2-c).
  - Figure 3 (cde) — audit
    ``paper/figures/make_figure3_cde.py`` for sensitivity to v5
    results; patch if needed.

### P2-e — Narrative / taint doc updates
  - ``docs/attack_gap_exp_exp/260421_empty_actions_root_cause.md``
    → rewrite "58-94 % empty" narrative as
    "agent_exhausted 63-83 % / agent_completed 5-17 %, true
    genuine empty ≤ 0.5 %". Cite the v6 summary JSON.
  - ``docs/attack_gap_exp_exp/260421_macro_taint_reverify.md``
    → re-run the taint scan using the v6 three-way
    termination_reason split. Expected: contamination
    threshold is no longer exceeded for any cell once
    ``agent_exhausted`` is counted separately.

### P2-f — Paper tex updates
  - ``paper/auto_numbers_v2.tex`` — append
    ``\input{evidence_pack/full_706_v6/macros.tex}`` or copy-paste
    macros inline (maintainer preference).
  - Add aliases for any old macro names that the paper references
    but the new generator doesn't emit (to avoid a cascade of
    edits in `main_final_v17.tex`).
  - Replace prose references to "58 % empty on qwen4b" with the
    v6 three-way breakdown.

## 7. Timeline

| Step | Wall-clock | Blocker? |
|---|---|---|
| P2-a (sweep 3 scaffolds × 8 models) | **~15 h overnight** | GPU fleet availability |
| P2-b (per-domain aggregator) | ~1 h | none; can start now |
| P2-c (macro emitter) | ~2 h | depends on sweep done for 4 scaffolds |
| P2-d (figures) | ~2-3 h | depends on P2-c |
| P2-e (narrative docs) | ~1 h | none; can start now |
| P2-f (paper tex) | ~1-2 h | depends on P2-c/d |

Total active human/agent work: ~8-10 h spread across sweep duration.

## 8. Dependencies on external state

- 145 vLLM fleet must stay up (7 instances + boosts). Reshuffle
  script at ``scripts/infra/launch_vllm_145.sh``.
- 144 read-only: qwen397b @ 30002 and nemotron30b @ 30003 must stay
  live through the sweep.
- Disk: 50 k episodes × ~6 KB = ~300 MB new results. No concern.

## 9. Risk list

- **Tool-use scaffold failure mode.** Several models (deepseek,
  gemma3-27b) may not support the vLLM tool-use parser with the
  currently wired config. Mitigation: smoke-test one episode per
  model before kicking off the 2,118-episode sweep for that
  (model × tool_use) cell. If a model fails, mark the cell
  "scaffold not supported" and proceed with the other 3 scaffolds
  for that model.
- **Gemma-3-27b re-use.** We swapped the model ID from
  gemma-4-31b-it to gemma-3-27b-it in v6. The paper's narrative
  still refers to "Gemma4-31B". The v6 aggregator must emit
  labels that make this distinction explicit (``Gemma-3-27B
  (swapped for Gemma-4-31B)``) to avoid paper-level confusion.
- **Checkpoint consistency.** The earlier oss120b tail issue
  (checkpoint.json wrote "2118 done" while 12 orphan claims
  remained) demonstrated that ``checkpoint.json`` can desync from
  file-existence. Mitigation: for each scaffold sweep, delete
  ``checkpoint.json`` before the last-mile catch-up workers.

## 10. Decision required before starting

**Confirm Option B (unify v6 with all 4 scaffolds, 15 h sweep).**

If approved:
1. Archive v5 W8 → ``results/ex_w8_crossmodel_v5/`` to free the
   name.
2. Launch the 3-scaffold sweep tonight (~15 h).
3. Run P2-b / P2-e in parallel as sweep progresses.
4. Reassemble macros / figures in the morning.

If rejected (stay with Option A):
1. Implement two separate aggregators — one for W8-as-is, one for
   v6-react-only.
2. Paper gets two tables / figures.
3. No additional compute.
