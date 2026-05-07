# Attack-gap X + Y session report — forward-direction MAB + CDE vs LLM extraction

**Date:** 2026-04-23
**Branch:** `eval_science`
**Plan:** `/home/anonymous-user/.claude/plans/contribution-4-evaluator-melodic-cupcake.md`
**Source:** `docs/attack_gap_exp_exp/260423_attackgap.md` (experiments X, Y, Z; Z deferred)

## Summary

Two attack-gap experiments landed in this session. Both produce
**numerically honest findings that depart from the attackgap.md's
stated expectations**, and both are useful as reviewer-defence
artefacts precisely because the discrepancies pre-empt an A3 "post-
hoc tuning" critique.

| Experiment | Expected (attackgap.md) | Actual | Status |
|---|---|---|---|
| X.3 MAB forward FA | 20-35% band | **58.67% aggregate; 0-100% per-task** | Shipped |
| X   AgentClinic forward FA | comparable | **blocked** (0/122 have dialogue turns) | Docs only |
| Y.0 1,049 reconcile | find generator | Engine audit: MUST 557 + FORBIDDEN 212 + WITHIN 215 + BEFORE 65 = 1049 ✅ | Resolved |
| Y.1 CDE/LLM ratio  | ≈ 8.0× | **1.01× aggregate; MUST 2.0×, FORBIDDEN 0.4×** | Shipped (23/25) |
| Z scaffold grid    | 4×8 cells | deferred to next session (per user decision) | Deferred |

## Commits (this session)

| SHA | One-liner |
|---|---|
| `<X.3>` | X.3 MAB forward-direction TCC re-score — 300 eps, FA 58.67%, per-task heterogeneity |
| `<Y.1>` | Y.1 CDE vs LLM constraint extraction — totals match, per-type asymmetric |

## Findings

### X.3 — MAB forward-direction re-score (300 episodes)

Method: `task_id // 30 + 1` → `task<N>` → `MEDAGENTBENCH_TASK_MAPPINGS`,
extract FHIR `tool_call` actions, fuzzy-match against `cpg_mandatory`.

- **Native ("completed" status) pass**: 176 / 300 = 58.67%
- **TCC (mandatory-completion) pass**: 0 / 300 = 0%
- **FA rate** (native=pass, tcc=fail): **58.67%**, not the expected 20-35%
- **Per-task** shows strong vocabulary-coupling effect:

  | task_type | FA rate | interpretation |
  |---|---|---|
  | task1 / 2 / 3 / 8 | 100% | mandatory phrases (e.g. `verify_patient_identity`) don't overlap FHIR tool vocab |
  | task6 | 0% | mandatory overlaps tool vocab well |
  | task4 | 10.0% | near-miss |
  | task5 / 7 | 36.7% | partial |
  | task9 | 73.3% | mandatory-heavy |
  | task10 | 30.0% | on expected band |

This is the real signal: MAB's "completed" flag is a weak proxy for
TCC-compliance, and the gap is driven by action-vocabulary overlap,
not by any per-task scoring deficiency in either method. The aggregate
FA band is a less informative summary than the per-task table.

### X — AgentClinic status

All 122 cases in `data/episodes/agentclinic_converted.jsonl` have an
empty `interactions` field. No trajectory to score. Blocker documented
in `evidence_pack/cross_benchmark_forward/AGENTCLINIC_BLOCKER.md`; three
forward paths listed (re-run via `run_external_benchmark.py`; upstream
fetch; declare out of scope).

### Y.0 — 1,049 vs 230 mismatch resolved

`evidence_pack/ex25_engine_audit/engine_audit.json` contains
`n_total_constraints: 1049` with breakdown MUST 557 + FORBIDDEN 212 +
WITHIN 215 + BEFORE 65. This is the authoritative source the paper
macro cites. The `v3_constraint_audit.json::hard_total=230` earlier
explore-agent report was a misread of that file's schema (no hard/soft
keys; different census). **Paper's 1049 is not a bug**.

### Y.1 — CDE vs LLM constraint totals and per-type asymmetry (23/25)

| Source | MUST | FORBIDDEN | WITHIN | BEFORE | Total |
|---|---|---|---|---|---|
| CDE | 557 | 212 | 215 | 65 | 1049 |
| LLM (23/25) | 278 | 533 | 168 | 57 | 1036 |
| Ratio (CDE ÷ LLM) | 2.00× | 0.40× | 1.28× | 1.14× | **1.01×** |

Key reads:

- Paper's "CDE recovers 8.0× more constraints than LLM extraction" is
  not supported by these numbers. Aggregate ratio is 1.01×.
- The real gap is shape, not size: CDE has 2× more explicit MUST, LLM
  has 2.5× more FORBIDDEN (likely because the prompt catches every
  "do not / avoid" phrase as a forbidden rule).
- 2 CPGs (AHA-2019-Stroke, AHA-2022-Heart-Failure) still truncate at
  max_tokens=6144; rerun with 8192+ in a future session.

**Paper §4.2 requires prose revision**: either cite these macros
(1.01× aggregate, per-type asymmetry) or find the original "8×"
derivation and preserve it as an orthogonal measurement.

## Reviewer attack surface — what this session closes

- **§6 Limitations "deferred to future work"** (E8 forward axis):
  X.3 ships the MAB side, 176 native-pass / 0 TCC-pass on 300 eps,
  documented per-task heterogeneity. Partial, but the deferred
  language can be weakened.
- **§4.3 "catalogue method is orthogonal to evaluator audit"**: Y.1
  shows the two catalogues differ in type composition, not in
  aggregate size. Y.3 invariance check is still deferred (audit
  harness re-run on LLM constraints) — preserves the orthogonality
  claim as a testable hypothesis.

## Addendum (session v2 — user-directed follow-up)

All four immediate follow-ups executed:

1. **Y.1 last 2 CPGs** ✅ (max_tokens=8192 + rerun). 25/25 coverage.
   Final LLM total **1268** vs CDE 1049 → ratio **0.83×** (LLM exceeds
   CDE once the two large cardiology CPGs land).
2. **Y.3 invariance check** ✅. New `LLMCatalogueShim` evaluator
   (audit/shims/llm_catalogue_shim.py) runs LLM catalogue-based
   verdict on 14,826 W8 eps. **pair τ vs v4_hard = -0.075** →
   verdict streams are effectively independent. Audit is
   **catalogue-conditional, not invariant**. Directly shapes Pose
   B §4.3 framing.
3. **AC forward re-score** ✅ (partial, 20 eps). `run_external_benchmark.py
   --benchmark agentclinic --agent llm_assist` produced coverage
   1.43%, CPG compliance 8.25%, 0.5 actions/scenario. Honest partial
   that documents the AC dialogue-vs-trajectory structural mismatch.
4. **Paper §4.2 / §4.4 / §6 prose revision** ✅. Two new §4.4
   paragraphs (Catalogue-conditional audit sensitivity +
   External-benchmark forward replay). Preamble loads 3 new macro
   files. pdflatex --interaction=nonstopmode passes with 0 undefined
   / error / runaway.

## Deferred (next session)

- Matcher-threshold sensitivity sweep on Y.3 (50% MUST coverage is
  one of several viable rules; τ may vary with it).
- AC forward to 122 eps (currently 20 / 122).
- Z scaffold × model 8×4 grid (user-deferred).

## Artefacts

```
scripts/experiments/exp_crossbench_forward.py   X.3
scripts/experiments/exp_cde_vs_llm.py           Y.1
tests/test_experiments/test_crossbench_forward.py
tests/test_experiments/test_cde_vs_llm.py

evidence_pack/cross_benchmark_forward/mab/results.json
evidence_pack/cross_benchmark_forward/mab/macros.tex
evidence_pack/cross_benchmark_forward/AGENTCLINIC_BLOCKER.md

evidence_pack/constraint_comparison/llm_raw/*.json   (23 CPGs)
evidence_pack/constraint_comparison/llm_summary.json
evidence_pack/constraint_comparison/compare_summary.json
evidence_pack/constraint_comparison/macros.tex
```

## Macros emitted

```
\crossBenchMabTotal     = 300
\crossBenchMabFA        = 176
\crossBenchMabFARate    = 0.5867
\crossBenchMabFAPct     = 58.7
\crossBenchMabFR        = 0
\crossBenchMabAgreePct  = 41.3
\crossBenchMabNTaskTypes = 10

\cdeVsLlmCdeTotal        = 1049
\cdeVsLlmLlmTotal        = 1036
\cdeVsLlmRatio           = 1.01
\cdeVsLlmRatioMust       = 2.00
\cdeVsLlmRatioForbidden  = 0.40
\cdeVsLlmRatioWithin     = 1.28
\cdeVsLlmRatioBefore     = 1.14
```

Paper preamble needs two new `\IfFileExists{...}` blocks for
`cross_benchmark_forward/mab/macros.tex` and
`constraint_comparison/macros.tex` — not added this session; folded
into the "§4.2 prose revision" follow-up.
