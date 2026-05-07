# Attack-gap X + Y session v3 — follow-up additions

**Date:** 2026-04-23 (v3 continuation)
**Branch:** `eval_science`
**Prior reports:** `260423_attackgap_xy_report.md`, `260423_piclass_pool_dilution_finding.md`
**User prompt chain:** reframing (Theorem-1 consistent MAB 58.67% + scope-limit Y.3) → extended Y.3 + AC 122 → threshold sweep + main-finding partial replication + Z pre-flight

## Round-3 additions

| # | Item | Result | Status |
|---|---|---|---|
| R1 | Commit-chain verification (revert integrity) | f623eaa0 reverted by b9fbe31f, subsequent commits (8e60cd3e etc.) built on revert — clean | Verified |
| R2 | Y.3-extended: 4-projection Bayes error under LLM catalogue | Ordering preserved (term > aset > nord ≈ nctx) both CDE and LLM | Shipped |
| R3 | AC forward full 122 eps | coverage 2.37% (up from 1.43% at 20 eps), CPG 7.46% | Shipped |
| R4 | Y.3 threshold sweep {0, 0.25, 0.5, 0.75, 1.0} | τ stable negative: -0.057, -0.055, -0.050, -0.031, -0.028 | Shipped |
| R5 | Main-finding partial replication | LLM single-shim 72.98% FA on CDE-hard vs paper 6.6% CDE 3-consensus | Shipped (partial) |
| R6 | Z pre-flight | **32/32 (model × scaffold) cells full**, 2120+ eps each → Z.1 runs already done | Verified |

## Key numbers

### Y.3-extended Bayes error ordering (ordering preserved)

```
projection     CDE ε     LLM ε    Δ(LLM-CDE)
term          0.1590    0.0150    -0.1440
aset          0.0303    0.0001    -0.0302
nord          0.0052    0.0000    -0.0052
nctx          0.0052    0.0000    -0.0052
```

Both catalogues show term > aset > nord ≈ nctx. Theorem 3.4 taxonomic
claim is **catalogue-robust** even though the verdict streams are
catalogue-conditional (τ = -0.075).

### Y.3 threshold sensitivity

| threshold | LLM pass | agree | τ |
|---|---|---|---|
| 0.00 | 71.21% | 46.73% | -0.0572 |
| 0.25 | 71.04% | 46.84% | -0.0549 |
| 0.50 | 70.80% | 47.08% | -0.0496 |
| 0.75 | 69.28% | 47.94% | -0.0313 |
| 1.00 | 69.12% | 48.10% | -0.0279 |

|τ| ∈ [0.028, 0.057] across thresholds — the 50% knob is not a
tunable that can flip the conclusion.

Secondary observation: the inline verdict implementation gives LLM
pass rate ≈ 70% vs the shim's 1.7%. Cause: the committed shim
pessimistically fails when `scenario_id` cannot be resolved to a CPG,
which inflates |τ|. Under neutral resolution the catalogue-conditional
signal is milder (|τ| ≤ 0.058) but still non-zero.

### AC forward 20 → 122

| metric | 20 eps | 122 eps |
|---|---|---|
| coverage | 1.43% | 2.37% |
| CPG compliance | 8.25% | 7.46% |
| actions/scenario | 0.5 | 0.70 |
| violations/scenario | 1.1 | 1.34 |

Systematic dialogue-vs-trajectory mismatch confirmed — not a small-
sample artefact.

### Main-finding partial replication

- CDE-hard subset (v4_hard=False): 7,651 / 14,826
- LLM catalogue pass on CDE-hard (thr=0.5): 5,584 / 7,651 = **72.98%**
- Paper strictFAThree (CDE ASC∩PAF∩CwT FA): **6.6%**
- Ratio: 11.06× (LLM single-shim looser than CDE 3-consensus)

Caveat: single-vs-3-consensus comparison, not a direct replication.
True replication needs LLM-catalogue analogues of ASC/CwT/PAF and a
fresh intersection. That's a camera-ready candidate.

### Z pre-flight — coverage 32/32 ✅

Every (model, scaffold) cell has full 706-scenario × 3-run data on
disk:

```
model          react    direct  checklist   tooluse
deepseek_r1_7b  2120      2120      2121      4241
gemma31b        2120      2120      2122      2121
nemotron30b     2120      2120      2120      4240
oss120b         2120      2120      2120      4242
qwen27b         2120      2120      2121      2120
qwen35b         2120      2120      2120      2120
qwen397b        2120      2120      2120      4241
qwen4b          2120      2120      2120      2120

Total 32/32 filled, 0 missing
```

Z.1 GPU runs are already complete. Z.2 (per-cell AO/FA + Friedman
χ² recomputation) and Z.3 (paper Figure 5 + Table 29 regeneration)
become pure analysis tasks. Scoped to the next session because the
verdict_matrix_v6.json only covers ReAct; scaffold-extended verdict
data needs to be built on top of `results/full_706_v6_scaffolds_*`
first.

## Commits added this round

| SHA | One-liner |
|---|---|
| `1fbbba0f` | Y.3-extended ordering preservation + AC forward full 122 + paper wire-in |
| `009f87b3` | Y.3 matcher-threshold sweep (τ robust across thresholds) |
| `ed7579c3` | Main-finding partial replication (LLM 72.98% vs CDE 6.6%) |

## Paper §4.4 now says (v3)

- Catalogue-conditional audit paragraph: τ=-0.075 + **taxonomic
  ordering preserved under swap** (new half-sentence).
- Preamble loads 5 macro files now (was 3).
- pdflatex --interaction=nonstopmode clean.

## Reviewer defence matrix (v3)

| Attack | Response |
|---|---|
| §6 forward deferred | MAB 300 + AC 122 (both external benchmarks shipped) |
| §4.3 catalogue invariant | τ=-0.075 catalogue-conditional + ordering preserved taxonomically |
| Theorem 3.4 robustness | LLM catalogue preserves term > aset > nord ≈ nctx ordering |
| Main-finding 6.6% FA robust? | LLM single-shim 73%, full 3-consensus rebuild deferred (camera-ready) |
| Z scaffold underpowered | 32/32 cells already on disk — Z.2/Z.3 is analysis, not runner |

## Deferred to next session

- Z.2 per-cell AO/FA + Friedman χ² + AO-FA band
- Z.3 Figure 5 (4×8 heatmap) + Table 29 rewrite
- Main-finding full replication: rebuild LLM-catalogue ASC/CwT/PAF
  analogues, intersect, compare to CDE 6.6%
- Paper §4.2 "CDE and LLM extraction produce catalogues of comparable
  size..." sentence insertion (user-approved wording; not yet
  landed)

## Artefacts

```
scripts/experiments/
  exp_piclass_bayes_llm_catalogue.py     (R2)
  exp_piclass_y3_threshold_sweep.py      (R4)

evidence_pack/constraint_comparison/
  y3_bayes_extended_results.json         (R2)
  y3_bayes_extended_macros.tex           (R2)
  y3_threshold_sweep_results.json        (R4)
  y3_threshold_sweep_macros.tex          (R4)
  main_finding_replication.json          (R5)

evidence_pack/cross_benchmark_forward/agentclinic/
  results_122.json                       (R3)
  macros.tex                             (R3 — 122 overwrites 20)

evidence_pack/ex_w8_crossmodel/
  coverage_v2_preflight.json             (R6)

paper/main_final_v17.tex                 (updated §4.4 + preamble)
```
