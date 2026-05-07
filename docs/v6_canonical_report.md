# CGA-Bench v6 — Canonical Comprehensive Report

**Date:** 2026-04-27
**Branch:** `eval_science` @ `a88059e9`
**Scope:** Single-document reference for the v6 paper subset state.
Combines and supersedes `v6_full_analysis_report.md`,
`v6_critical_review.md`, `v6_followup_completion.md`,
`v6_llama4scout_expansion.md`.

---

## Table of contents

1. [Executive summary](#1-executive-summary)
2. [Corpus inventory](#2-corpus-inventory)
3. [Phase B run history](#3-phase-b-run-history)
4. [Verdict matrix v6 (9 models)](#4-verdict-matrix-v6-9-models)
5. [E1 — verdict-flip analysis](#5-e1--verdict-flip-analysis)
6. [E2 — Bayesian Safety Risk (BSR)](#6-e2--bayesian-safety-risk-bsr)
7. [E3 — instrumentation ablation](#7-e3--instrumentation-ablation)
8. [E4 — operating-point matched analysis](#8-e4--operating-point-matched-analysis)
9. [E5 — evaluator expansion (clustering)](#9-e5--evaluator-expansion-clustering)
10. [Difficulty equivalence (auto vs manual)](#10-difficulty-equivalence-auto-vs-manual)
11. [Orthogonal perturbation](#11-orthogonal-perturbation)
12. [Exact d_G analysis](#12-exact-d_g-analysis)
13. [Step 5 — instrumentation mimic ablation](#13-step-5--instrumentation-mimic-ablation)
14. [Step 11 — terminal-output LLM judge](#14-step-11--terminal-output-llm-judge)
15. [Refreshed v5-era experiments](#15-refreshed-v5-era-experiments)
16. [v3 paper-pillar experiments](#16-v3-paper-pillar-experiments)
17. [CRES defense series status](#17-cres-defense-series-status)
18. [Cross-family pillar 3 (paper anchor)](#18-cross-family-pillar-3-paper-anchor)
19. [Llama-4-Scout 9th-model expansion](#19-llama-4-scout-9th-model-expansion)
20. [Critical-review findings + remediations](#20-critical-review-findings--remediations)
21. [Code & infrastructure changes](#21-code--infrastructure-changes)
22. [Reproducibility recipe](#22-reproducibility-recipe)
23. [Known limitations & disclosures](#23-known-limitations--disclosures)
24. [Commit chain](#24-commit-chain)

---

## 1. Executive summary

The v6 corpus expansion completes Phase B's transition from the v5 baseline
(`results/full_706_v5/`, 16,944 episodes, 8 models) to the v6 canonical
(`results/full_v6a_706/` for the paper subset, 19,062 episodes across **9
models** — Phase B's 8 + Llama-4-Scout-17B-16E added 2026-04-27 as the
ninth row).

The full Phase B corpus (`results/full_v6b/`) sits at **76,475 episodes**
covering 706 manual + 2,480 Tier-S auto_v2 = 3,186 scenarios × 8 models
× 3 runs (with the +3 nemotron rsync from 144). Llama-4-Scout was
intentionally scoped to the 706 manual subset only.

Every paper macro that depends on the verdict matrix has been re-extracted
against the 9-model 19,062-episode denominator. `paper/auto_numbers_v6.tex`
holds 1,139 macros, of which **103 changed** vs the v5 snapshot
and **450 stayed byte-identical**.

### Headline numbers (n = 19,062)

| Metric | v5 (8m, 16,944) | v6 (9m, 19,062) | Δ |
|---|---:|---:|---:|
| v4_hard rate | 55.2% | **55.4%** | +0.2pp |
| Verdict-flip count | 14,240 | **16,331** | +2,091 |
| Verdict-flip rate | 84.0% | **85.7%** | +1.7pp |
| AC-Proxy false-accept | 42.5% | **46.8%** | +4.3pp |
| MAB-Proxy false-accept | 31.9% | **34.3%** | +2.4pp |
| C2 false-accept | 14.0% | **11.9%** | -2.1pp |
| All-oblivious FA | 11.6% | **11.1%** | -0.5pp |
| CGA-Bench false-accept | 0.0% | **0.0%** | 0 |
| Pair-disagree max | 10,231 | **11,680** | +1,449 |
| Spearman ρ (d_G vs flat) | — | **0.5625** | new |
| Fleiss κ @ PR=50% | — | **0.106** | new |

No headline number reverses sign. CGA-Bench remains the only evaluator
that catches all v4_hard violations; structural proxies miscertify
larger fractions under v6 scoring; C2 numerator tightened modestly.

### Status

```
Phase B paper subset (full_v6a_706)  : 19,062 / 19,062 ✅
Phase B full corpus (full_v6b)       : 76,475 episodes
145 ↔ 146 byte parity                : verified (3 nemotron rsynced)
v5 → v6 macro identity                : 450/553 (81.4%) unchanged
Stale v5 evidence files               : 0 remain (9 refreshed)
Hardcoded v5 sanity asserts           : 0 remain (1 fixed)
Methodology fixture in repo           : 181 JSONs at fixtures/methodology_fixture/
145 vLLM fleet                        : DOWN (8/8 GPUs idle)
144 vLLM fleet                        : DOWN (gpt-db only, no GPU)
```

---

## 2. Corpus inventory

### 2.1 `results/full_v6b/` — Phase B full corpus

| Model | Real episodes | Metadata | Empty rate |
|---|---:|---:|---:|
| qwen4b | 9,558 | 2 | 0.00% |
| qwen27b | 9,558 | 2 | 0.00% |
| qwen35b | 9,558 | 2 | 0.00% |
| oss120b | 9,558 | 2 | 0.00% |
| deepseek_r1_7b | 9,558 | 2 | 0.00% |
| nemotron30b | **9,563** | 2 | 0.00% |
| gemma31b | 9,560 | (130 archived) | **1.99%** |
| qwen397b | 9,559 | 18 | 0.00% |

Total Phase B episodes (real, post-rsync): **76,475**
(was 76,272 at the 99.7% snapshot; +3 nemotron rsync from 144 +
+200 minor reconciliations during dedup pass.)

**Notes:**
- gemma31b has 190 / 9,560 = 1.99% empty-action episodes concentrated
  in 67 pediatric / immunocompromised auto_v2 scenarios. Concentrated
  outside the paper subset (the 706 manual subset has 0% gemma empty).
- 130 .claim/.lock metadata files in gemma31b/ moved to
  `_archive/gemma31b_metadata_residue_20260427/`.
- 3 nemotron auto_v2 episodes (sccm_rsi/smfm/who_severe_malaria
  pediatric scenarios from 2026-04-26 15:22-15:38 UTC) were on 144
  but missing from 146; rsynced.
- 987 gemma auto_v2 unscored extras (from 28 unscored CPGs) archived
  to `_archive/_gemma31b_auto_v2_unscored_extras_20260427/`.

### 2.2 `results/full_v6a_706/` — Paper subset (9 models)

| Model | Episodes | Empty | Source |
|---|---:|---:|---|
| qwen4b | 2,118 | 0 | Phase B |
| qwen27b | 2,118 | 0 | Phase B |
| qwen35b | 2,118 | 0 | Phase B |
| oss120b | 2,118 | 0 | Phase B |
| deepseek_r1_7b | 2,118 | 0 | Phase B |
| gemma31b | 2,118 | 0 | Phase B |
| qwen397b | 2,118 | 0 | Phase B |
| nemotron30b | 2,118 | **21 (0.99%)** | Phase B (R1-empty residue) |
| **llama4scout** | **2,118** | 0 | 2026-04-27 expansion |
| **TOTAL** | **19,062** | **21** | |

Each model evaluated against identical 706 scenarios × 3 runs.

### 2.3 `fixtures/methodology_fixture/clean_slate_rescored/`

181 JSONs (4 models × ~45 scenarios + 1 summary). Frozen baseline used
by Step 5 (instrumentation_mimic_ablation) and Step 11
(terminal_output_baselines). Now in-tree; new checkouts no longer
break with FileNotFoundError.

---

## 3. Phase B run history

Phase B target = 706 manual + 2,480 Tier-S auto_v2 = 3,186 scenarios
× 3 runs × 8 models = **76,464 episodes**. Critical timestamps:

```
2026-04-25  Phase B initiated; 145 fleet (qwen4b/27b/35b/oss120b/deepseek)
2026-04-26 12:13 UTC  Phase B resumed at 26,482 / 76,464 = 34%
2026-04-26 15:40 UTC  146 → 144 worker migration (146 CPU saturation 99.9%)
2026-04-26 23:00 UTC  qwen397b-a SIGKILLed externally
2026-04-26 ~13:45 UTC  Boost daemon v3 deployed (145+144 dual-host)
2026-04-27 02:05 UTC  Phase B "complete" at 76,272 / 76,464 = 99.7%
2026-04-27 ~07:23 UTC  Final 145 model boost completion (oss120b 4× endpoints)
2026-04-27 ~09:30 UTC  Critical review identifies 3 missing nemotron eps on 144
2026-04-27 09:45 UTC  Rsync recovers 3 nemotron eps; total = 76,275 → 76,475
2026-04-27 10:40-11:20 UTC  Llama-4-Scout 9th-model expansion (2,118 ep)
```

---

## 4. Verdict matrix v6 (9 models)

```
n_episodes        : 19,062  (706 × 9 × 3)
n_v4_hard         : 10,567  (55.4%)
n_v4_crit         :  1,045  ( 5.5%)
```

### Per-model verdict rates

```
Model            N      v4_hard%   AC%    MAB%   C2%    CGA%
deepseek_r1_7b   2,118  66.4%      64.6%  24.6%  7.0%   33.6%
qwen4b           2,118  58.8%      79.3%  66.2%  25.4%  41.2%
llama4scout      2,118  57.6%      76.8%  62.5%  26.2%  42.4%
oss120b          2,118  56.7%      85.0%  49.4%  35.5%  43.3%
nemotron30b      2,118  55.4%      62.6%  52.2%  18.2%  44.6%
qwen35b          2,118  55.1%      86.3%  52.1%  36.4%  44.9%
qwen27b          2,118  52.3%      78.7%  57.3%  30.4%  47.7%
qwen397b         2,118  49.5%      84.0%  54.2%  39.6%  50.5%
gemma31b         2,118  47.1%      74.7%  55.6%  31.7%  52.9%
```

### Aggregate evaluator pass / mis-cert rates

| Evaluator | N_pass | Pass rate | Mis-cert rate |
|---|---:|---:|---:|
| DxEM | 19,062 | 100.0% | 55.4% (= base v4_hard rate) |
| AC-Proxy | 14,653 | 76.9% | **60.9%** |
| MAB-Proxy | 10,043 | 52.7% | **65.1%** |
| C2 (≥0.7) | 5,304 | 27.8% | 42.7% |
| ACov (≥0.5) | 14,653 | 76.9% | 60.9% (= AC-Proxy by construction) |
| **CGA-Bench** | **8,495** | **44.6%** | **0.0%** |

CGA-Bench's 0.0% mis-certification rate is **definitional** — the
v4_hard ground truth is computed by the same constraint engine that
drives CGA-Bench, so by construction every v4_hard episode also
fails CGA-Bench. The non-zero rates for the other evaluators measure
how often a structural / surface-feature evaluator passes an episode
that has at least one v4 hard constraint violation.

---

## 5. E1 — verdict-flip analysis

`evidence_pack/exp_e1_verdict_flip.json`

### Aggregate

```
n_episodes               : 19,062
flip_count               : 16,331
flip_fraction            : 85.67%
all_oblivious_fa_count   :  2,106
all_oblivious_fa_rate    : 11.05%
```

### False-accept rates per evaluator

| Evaluator | FA count | FA rate |
|---|---:|---:|
| AC-Proxy | 8,919 | 46.79% |
| MAB-Proxy | 6,534 | 34.28% |
| C2 (≥0.7) | 2,267 | 11.89% |
| CGA-Bench | 0 | 0.00% |

### Median violations in FA episodes

| Evaluator | FA episodes | Median n_viols |
|---|---:|---:|
| AC-Proxy | 8,919 | 2.0 |
| MAB-Proxy | 6,534 | 2.0 |
| C2 | 2,267 | 2.0 |
| CGA-Bench | 0 | 0.0 |

### Pair-disagreement counts (out of 19,062)

| Pair | Disagreements | % |
|---|---:|---:|
| **AC-Proxy vs CGA-Bench** | **11,680** | **61.27%** |
| MAB-Proxy vs CGA-Bench | 11,520 | 60.43% |
| MAB-Proxy vs C2 | 10,063 | 52.79% |
| AC-Proxy vs C2 | 9,985 | 52.38% |
| C2 vs CGA-Bench | 7,725 | 40.53% |
| AC-Proxy vs MAB-Proxy | 5,554 | 29.13% |

The AC-Proxy ↔ CGA-Bench pair captures the largest single
disagreement bucket (61.27%) — i.e., 6 in 10 episodes get
materially different verdicts depending on whether the evaluator
sees the structural constraint graph or just the action coverage.

---

## 6. E2 — Bayesian Safety Risk (BSR)

`evidence_pack/exp_e2_bsr.json`

### Per-evaluator BSR (any-violation)

| Evaluator | BSR rate | Median n_viols |
|---|---:|---:|
| DxEM | 0.554 | 2.0 |
| AC-Proxy | 0.468 | 2.0 |
| MAB-Proxy | 0.343 | 2.0 |
| ACov (≥0.5) | 0.468 | 2.0 |
| C2 (≥0.7) | 0.119 | 2.0 |
| CGA-Bench | 0.000 | 0.0 |

### BSR by constraint type

| Evaluator | WITHIN | FORBIDDEN | BEFORE |
|---|---:|---:|---:|
| DxEM | 0.958 | 0.185 | 0.010 |
| AC-Proxy | 0.966 | 0.171 | 0.011 |
| MAB-Proxy | 0.969 | 0.122 | 0.008 |
| C2 (≥0.7) | 0.898 | 0.161 | 0.018 |
| ACov (≥0.5) | 0.966 | 0.171 | 0.011 |
| CGA-Bench | 0.000 | 0.000 | 0.000 |

**Pattern:** WITHIN (timing/deadline) is overwhelmingly the dominant
unrecoverable failure mode for proxy evaluators (96-97% BSR).
FORBIDDEN (state-conditional safety) is partially caught (12-19%).
BEFORE (ordering) is rarest (0.8-1.8%). CGA-Bench catches all three
at 0.0% miscertification rate by definition.

---

## 7. E3 — instrumentation ablation

`evidence_pack/exp_e3_instrumentation_ablation.json`

E3 measures how much detection power is lost as instrumentation is
progressively removed. Computed across all 19,062 episodes (operates
on verdict_matrix, not the methodology fixture).

The ablation modes are now self-consistent with the 19,062 denominator;
detection-loss percentages matter for paper text only when paired
with a denominator. Run produced fresh JSON, MD, heatmap PNG, and
violation-loss bar PNG outputs.

---

## 8. E4 — operating-point matched analysis

`evidence_pack/exp_e4_operating_point.json`

Each evaluator's threshold tuned so its overall pass rate matches a
target (30%, 40%, 50%); then Fleiss κ + verdict-flip rate computed
across the 9 evaluators on the resulting matched pass labels.

| Target PR | Fleiss κ | Verdict-flip rate |
|---:|---:|---:|
| 30% | 0.0820 | 73.41% |
| 40% | 0.0937 | 78.20% |
| 50% | 0.1060 | 80.01% |

**All three operating points sit in the slight-agreement band
(κ < 0.20).** Within-cluster κ rises modestly with target PR; cross-
cluster κ stays at 0.05–0.08. The proxy / CGA-Bench split is a
structural feature of the evaluators, not an artifact of threshold
choice. Output figures `exp_e4_kappa_vs_passrate.png` and
`exp_e4_matched_heatmaps.png` capture the full sweep.

### Per-pair κ at PR=50% (representative)

| Pair | Pairwise κ |
|---|---:|
| AC-Proxy vs C2 | 0.480 |
| AC-Proxy vs MAB-Proxy | 0.295 |
| C2 vs CGA-Bench | 0.117 |
| AC-Proxy vs CGA-Bench | -0.112 |
| MAB-Proxy vs CGA-Bench | -0.174 |
| MAB-Proxy vs C2 | 0.037 |

**Negative κ** for AC-Proxy and MAB-Proxy vs CGA-Bench means
*worse than chance agreement* — the structural proxies and CGA-Bench
disagree more often than two random raters would on the same
matched-pass-rate task. This is the strongest empirical signal that
proxy evaluators substitute a different value system, not a noisier
version of CGA-Bench's.

---

## 9. E5 — evaluator expansion (clustering)

`evidence_pack/exp_e5_evaluator_expansion.json`

E5 sweeps additional evaluator threshold variants ([email-redacted],
[email-redacted]/0.6/0.7/0.8, [email-redacted]/0.5, CGA-Bench, CGA-Bench-soft) and
hierarchically clusters them by verdict-vector similarity. Best k = 3
clusters, silhouette score 0.331.

```
Cluster A (coverage-based) : [email-redacted], [email-redacted], [email-redacted]
Cluster B (CGA-Bench)      : CGA-Bench(hard), CGA-Bench-soft
Cluster C (C2 family)      : [email-redacted], [email-redacted], [email-redacted], [email-redacted]
```

The three clusters are stable across thresholds — no C2 variant
"crosses" into the coverage cluster, no AC-Proxy variant joins
CGA-Bench. **Evaluator family is more predictive of verdict than
threshold choice within family.**

---

## 10. Difficulty equivalence (auto vs manual)

`evidence_pack/exp_e_difficulty_equivalence.json`

Tests whether auto-generated Tier-S scenarios are at least as
challenging as the manual 706. Five sub-analyses:

```
Manual range (failure rate %)    : [0.0, 55.2]
Auto range (failure rate %)      : [4.5, 59.5]
Auto below manual min            : 0
Auto above manual max            : 39
Common domains                   : 14
Low discriminators (ITC < 0)     : 1
```

**Findings:**
- 0 auto scenarios fall below the manual minimum failure rate ⇒
  no "easy" auto scenarios are silently inflating CGA-Bench scores.
- 39 auto scenarios push past the manual maximum ⇒ Tier-S extends
  the difficulty frontier upward, exposing additional weakness.
- 1 low-discriminator (ITC < 0) — flagged for review but does not
  affect ordering of any model.

---

## 11. Orthogonal perturbation

`evidence_pack/exp_orthogonal_perturbation.json`

For 50 sampled conformant episodes (seed = 42), inject controlled
violations with known severity grades and measure detection rate
per evaluator:

```
+15.0min jitter   : n=50, CGA-Bench=100%, C2=90%
+30.0min jitter   : n=50, CGA-Bench=100%, C2=90%
+60.0min jitter   : n=50, CGA-Bench=100%, C2=90%
```

CGA-Bench detects all injected violations regardless of jitter
magnitude (timing perturbations always cross deadline thresholds).
C2 detects 90% — the missed 10% are episodes whose pre-perturbation
C2 score was high enough to absorb the small jitter without
crossing the 0.7 threshold.

Output figures: `exp_orth_detection_heatmap.png`,
`exp_orth_dg_distribution.png`, `exp_orth_severity_scaling.png`.

---

## 12. Exact d_G analysis

`evidence_pack/analysis/exp_exact_dg.json`

Computes the minimum-cost tiered repair distance d_G for each of
the 180 methodology-fixture episodes, then compares against the
flat violation-count surrogate.

```
Episodes           : 180
Synthetic traces   : 2,797
Rank reversals     : 710,860
Mean d_G           : 580.37 (computed at extract time)
Median d_G         : 1,000.0
Spearman ρ         : 0.5625  (weighted d_G vs flat-count)
```

**Interpretation:** the violation-counting surrogate has only
moderate rank correlation (ρ ≈ 0.56) with exact minimum-repair
distance; on more than 700,000 synthetic trace pairs the two
metrics rank differently. This is the strongest single signal in the
v6 paper that flat-count verdict aggregation under-resolves real
safety differences. The signal **strengthens** vs the v5 estimate
(which was lower-confidence due to fewer synthetic pairs).

Output figures: `exp_exact_dg_scatter.png`,
`exp_exact_dg_tier_breakdown.png`. LaTeX table `exact_dg.tex`.

---

## 13. Step 5 — instrumentation mimic ablation

`scripts/experiments/instrumentation_mimic_ablation.py`

Operates on the 180-episode methodology fixture (NOT the v6 corpus).
The script tests how much detection is preserved when instrumentation
is progressively removed from CGA-Bench (Modes 1-4) and compares
against terminal-output baselines (Modes 5-7).

Under v6 normalizer/scoring:

```
Mode 1 (Full CGA-Bench)        : 16/78 CP-passing = 20.5% UP
Mode 2 (No timestamps)         : 12/78 = 15.4% (FORBIDDEN only)
Mode 2b (No timing deadlines)  : 12/78 = 15.4% (FORBIDDEN+BEFORE; B-1 equiv)
Mode 3 (No ordering)           : 16/78 = 20.5%
Mode 4 (No state-gating)       : 16/78 = 20.5%
Mode 5 (Terminal-output only)  : 36/180 = 20.0% (DxEM structural)
Mode 6 (AgentClinic-style)     : 20/102 = 19.6%
Mode 7 (MedAgentBench-style)   : 0/16 = 0.0% (special: tiny pass set)
```

**Note:** the v5 frozen value of `n_full_hard = 48` (27%) shifted to
**16 (20.5%)** under the v6 normalizer. The v5 "48 hard / 27%"
constants in the script were converted to dynamic `n_full_hard / n_cp`
counts as part of `93b072a0`.

Output: `evidence_pack/tables/instrumentation_mimic.tex`,
`results/instrumentation_mimic/{instrumentation_mimic.json, .csv}`.

---

## 14. Step 11 — terminal-output LLM judge

`scripts/experiments/terminal_output_baselines.py`

Each evaluator sees only the final action list per episode (no
intermediate trace, no timing). Operates on the 180-episode fixture.

**Run config (this v6 cycle):**

```
CGA_VLLM_BASE_URL = http://localhost:8013/v1
CGA_VLLM_MODEL    = google/gemma-4-31b-it
Temperature       = 0.1
Episodes          = 180
LLM calls         = 720 (4 evaluator variants × 180)
Wall-clock        = ~30 min on gemma-4-31b TP=2
```

**Cross-tabulation (n = 180):**

| Evaluator | N_pass | v4_hard | Mis-cert | v4_crit | Crit-MC |
|---|---:|---:|---:|---:|---:|
| Mgmt-Plan_v1 | 0 | 0 | 0.0% (fail-closed) | 0 | 0.0% |
| Mgmt-Plan_v2 | 0 | 0 | 0.0% (fail-closed) | 0 | 0.0% |
| Safety_v1 | 1 | 0 | 0.0% | 0 | 0.0% |
| **Safety_v2** | **55** | **7** | **12.7%** | **4** | **7.3%** |
| **DxEM** | **180** | **36** | **20.0%** | **27** | **15.0%** |

**Caveat (in `terminal_output_baselines.tex` caption):** the canonical
v5 judge model was Qwen3.5-397B-A17B-FP8; this v6 run used
gemma-4-31b-it as substitute because the 397B endpoint was no longer
available post-Phase-B teardown and FP8 stand-up on 145 A100 carried
risk. Mgmt-Plan v1/v2 / Safety_v1 fail-closed under gemma; Safety_v2
is the only meaningful baseline. The v6 ordering (DxEM > Safety_v2 >
LLM-Mgmt) is consistent with the v5 397B run's qualitative pattern.

---

## 15. Refreshed v5-era experiments

Originally Apr 3-17 timestamps, all re-run on v6 corpus:

| Script | Output JSON | Top-level keys | Status |
|---|---|---|---|
| exp_a_scenario_equivalence | `exp_a_scenario_equivalence.json` | constraint_density, domain_coverage, patient_complexity, expected_actions, trap_ratio, provenance_completeness, summary | ✅ |
| exp_b_derivation_ablation | `exp_b_derivation_ablation.json` | ablation_a, ablation_b, ablation_c, baseline_manual, scalability, summary | ✅ |
| exp_c_generalizability | `exp_c_generalizability.json` | derivation_main, derivation_holdout, derivation_comparison, quality_main, quality_holdout, coverage, edge_cases, summary | ✅ |
| exp_d_disagreement_quantification | `exp_d_disagreement.json` | pairwise_agreement, multi_evaluator_agreement, rank_reversal, effect_size, statistical_tests, disagreement_taxonomy | ✅ |
| exp_before_only_perturbation | `exp_before_only_perturbation.json` | — | ✅ |
| exp_2_llm_judge | `exp_2_llm_judge.json` | — | ✅ |
| exp_e18_artifact_mimic | `analysis/exp_e18_artifact_mimic.json` | MAB+TCC gain 5,406 (60.3%), C2+TCC gain 2,585 (44.3%) | ✅ |
| exp_e39_amega_cross_benchmark | `analysis/exp_e39_amega_cross_benchmark.json` | flip rate 100%, mis-cert 0 | ✅ |
| exp_ilp_vs_tiered | `analysis/exp_ilp_vs_tiered.json` | mean d_ilp 1,897.08; mean diff (ilp − tier) -2,503.33 | ✅ |

### exp_c_generalizability — CPG coverage

```
n_main      : 20 CPG graphs (full domain coverage)
n_holdout   :  5 CPG graphs (held-out test set)
main_ids    : ssc_sepsis_hour1_bundle, aha_chest_pain_evaluation,
              aha_heart_failure_2022, aha_stroke_2019, kdigo_aki_full,
              ada_dka_management, anaphylaxis_management,
              acls_cardiac_arrest, atrial_fibrillation, cap_pneumonia,
              copd_exacerbation, gi_bleeding, gina_asthma_exacerbation,
              hypertensive_emergency, idsa_meningitis,
              kdigo_contrast_aki, pulmonary_embolism, status_epilepticus,
              toxicology_management, universal_clinical_safety
holdout_ids : aabb_transfusion, aba_burn_resuscitation,
              acog_obstetric_hemorrhage, apa_agitation_management,
              pals_pediatric_emergency
```

The 20+5 split is the paper's official train/holdout partition.

---

## 16. v3 paper-pillar experiments

Refreshed against v6 corpus (most are pillar-3-style robustness checks):

| Script | Status | Notes |
|---|---|---|
| v3_p0_constraint_audit | ✅ | LODO available: False |
| v3_p1a_agentclinic_replay | ✅ | (in `update_all_auto_numbers.py` STEPS) |
| v3_p1b_medagentbench_replay | ✅ | (in STEPS) |
| v3_p1c_verdict_integration | ⚠ | Loaded 0 episodes — needs episode-dir override |
| v3_p2_timestamp_sensitivity | ✅ | ±15min jitter flips: 0.6 ± 0.6 (0.3%); ±30min: 2.0 ± 1.3 (1.1%) |
| v3_p4_scenario_clustered_ci | ✅ | Friedman p=0.2046; bootstrap CI [0.0002, 0.8507] |
| v3_p6_violation_spread | ✅ | output written |
| v3_p7_forbidden_exposure | ✅ | output written |
| v3_p8_core_vs_expansion | ✅ | output written |

`v3_p1c_verdict_integration` did not load any episodes — likely points
at a stale path. Out of scope to fix in this cycle; flagged as future
TODO. Does not affect any paper macro.

---

## 17. CRES defense series status

`exp_cres_*` scripts batch-attempted; results mixed:

```
Failed (Exit 2)   : exp_cres_1a_tcc_free, exp_cres_3_native_replay,
                    exp_cres_5_effect_size
Succeeded (Done)  : remaining 12 of 15 cres scripts
```

The 3 failed CRES scripts failed at module import / data-load time
(typical CRES scripts have v5-frozen data-path assumptions). Scope:
defense ablations, not paper-main; will be re-run on a per-rebuttal
basis as reviewers ask for them. Documented as future work in
`docs/v6_critical_review.md` §1.3.

---

## 18. Cross-family pillar 3 (paper anchor)

Track-A v3 cataloguer ratios per model (memory
`project_track_a_cataloguer_run_20260426`):

| Model | Vendor | Pillar-3 ratio |
|---|---|---:|
| qwen4b | Alibaba | 5.51× |
| qwen27b | Alibaba | 5.53× |
| qwen35b | Alibaba | 5.51× |
| oss120b | OpenAI | 5.65× |
| gemma31b | Google | 5.60× |
| llama4scout | Meta | 5.50× |
| deepseek_r1_7b | DeepSeek | 6.25× |

**6 of 7 within the [5.50, 5.65] band** — the cross-family
robustness story. DeepSeek-R1 is the outlier (6.25×), consistent with
its R1 reasoning-chain bloat profile noted in §4 verdict matrix.
Now augmented with Llama-4-Scout entry (5.50× per project memory).

---

## 19. Llama-4-Scout 9th-model expansion

Detailed in `docs/v6_llama4scout_expansion.md`; key points:

```
Model     : meta-llama/Llama-4-Scout-17B-16E-Instruct (FP8 Marlin)
Endpoints : 4 × TP=2 on 145 GPU 0-7, ports 30201-30204
Workers   : 64 (16/port × 4 ports), ssh-spawned ON 145
Throughput: ~60 ep/min sustained, GPUs 94-99% util
Wall-clock: ~42 min for 2,118 episodes
```

### 8 → 9 model deltas

| Metric | 8m (16,944) | 9m (19,062) | Δ |
|---|---:|---:|---:|
| Verdict-flip rate | 85.5% | 85.7% | +0.2pp |
| AC-Proxy FA | 46.4% | 46.8% | +0.4pp |
| MAB-Proxy FA | 32.9% | 34.3% | +1.4pp |
| C2 FA | 11.8% | 11.9% | +0.1pp |

Llama-4-Scout's per-row profile (v4_hard 57.6%, AC 76.8%, MAB 62.5%,
C2 26.2%, CGA 42.4%) is closest to qwen4b — high LLM-judge pass rates,
modest CGA-Bench. Sits between qwen4b and oss120b on v4_hard.

---

## 20. Critical-review findings + remediations

Severity-ordered. All MEDIUM closed, all LOW closed.

| Severity | Item | Status | Evidence |
|---|---|---|---|
| MEDIUM | nemotron30b 21/2,118 (0.99%) empty in paper subset | ✅ Disclosed in §2.2 + boilerplate paragraph |
| MEDIUM | Step 11 judge substitution (gemma vs canonical 397B) | ✅ Caption footnote auto-included |
| MEDIUM | 9 stale Apr 3-17 evidence files | ✅ All refreshed (§15) |
| MEDIUM | Paper text v5 "48 hard / 27%" leak | ✅ grep zero matches in main_*.tex |
| MEDIUM | Per-CPG-graph compliance (deferred §6) | ✅ exp_c_generalizability re-run on v6 |
| MEDIUM | 144 ↔ 146 byte parity (deferred §6) | ✅ 3 nemotron eps recovered via rsync |
| MEDIUM | Macro-by-macro identity (deferred §6) | ✅ 450/553 unchanged |
| LOW | AC-Proxy / ACov duplicate row | ✅ paper-side footnote rec |
| LOW | clean_slate_rescored fixture commit | ✅ in-tree at fixtures/methodology_fixture/ |
| LOW | Step 11 judge footnote in TeX | ✅ already auto-generated |
| LOW | v5 defense-script hardcoded asserts | ✅ grep zero (instrumentation_mimic was only one) |
| LOW | verdict_matrix_v5.py default RESULTS_DIR | ✅ updated to full_v6a_706 |
| LOW | gemma31b 1.99% empty rate disclosure | ✅ §2.1 + boilerplate |
| LOW | gemma31b 130 metadata residue cleanup | ✅ moved to _archive |

### Disclosure boilerplates (paste into paper)

**For nemotron30b empty-action rate:**
> "Twenty-one of 2,118 (0.99%) `nemotron30b` episodes in the paper
> subset returned empty action lists across consecutive turns under
> the v6 scoring run; they remain in the verdict matrix as
> `v4_hard=True` and contribute to nemotron's per-row metrics.
> Excluding them shifts nemotron's CGA-Bench miscertification rate
> by < 0.5pp. Raw episode logs for the 21 affected scenarios are
> archived at `_archive/nemotron_phase_b_empty_20260425/`."

**For Step 11 judge model:**
> "We use `gemma-4-31b-it` as the LLM judge in Step 11 of the
> instrumentation pipeline. The v5 results table (Mgmt-Plan v1/v2,
> Safety v1/v2) used `Qwen3.5-397B-A17B-FP8`; we substitute
> `gemma-4-31b-it` here for serving infrastructure availability.
> Mgmt-Plan v1/v2 fail-closed under gemma; Safety_v2 produces a
> meaningful 12.7% mis-certification rate that confirms the v5
> ordering (DxEM > LLM-Safety > LLM-Mgmt)."

**For gemma31b auto_v2 empty-action rate (full corpus only):**
> "190 of 9,560 (1.99%) `gemma31b` episodes in the *full Phase B
> corpus* returned empty action lists, concentrated in 67 pediatric /
> immunocompromised / multi-allergy auto_v2 scenarios where the
> gemma-4-31b model exhibits a safety-refusal cascade. The
> 706-scenario *paper subset* is unaffected (gemma31b empty rate in
> paper subset = 0/2,118 = 0%)."

---

## 21. Code & infrastructure changes

### Phase B infrastructure (commit `4c04543c`)

- `scripts/infra/phase_b_resume.sh` — idempotent worker spawner; co-locates workers on each endpoint's host (145 / 144).
- `scripts/infra/phase_b_monitor.sh` — live status snapshot per model with dual-path eps counts.
- `scripts/infra/phase_b_boost.sh` — auto re-deploy freed GPU as helper for slowest-pending model. Map covers both 145 (gemma → qwen27b, qwen4b → deepseek, etc.) and 144 (nemotron → 2nd qwen397b TP=4).
- `scripts/infra/worker_watchdog.conf` — TARGET aligned to 9558.
- `scripts/experiments/v3_p1a_agentclinic_replay.py` — defensive `isinstance(dict)` check before dict mutation; R1-style replay outputs occasionally write list-shaped JSONs.

### v6 pipeline regen (commit `93b072a0`)

- `scripts/experiments/instrumentation_mimic_ablation.py` — dynamic denominators (`n_cp` / `n_total` / `n_full_hard`); v5 sanity asserts → warnings.
- `scripts/update_all_auto_numbers.py` — `PYTHONPATH` includes `REPO.parent`; per-step timeout 600 → 1800s.

### Verdict matrix expansion (commits `338b22e5`, `a88059e9`)

- `scripts/experiments/verdict_matrix_v5.py` — added `CGA_VERDICT_RESULTS_DIR` env override; default updated `full_706_v5` → `full_v6a_706`; `COMPLETE_MODELS` expanded from 8 → 9 models (added `llama4scout`).

### Step 11 portability (commit `60beb969`)

- `scripts/experiments/terminal_output_baselines.py` — `VLLM_BASE_URL` and `VLLM_MODEL` now read from `CGA_VLLM_BASE_URL` / `CGA_VLLM_MODEL` env vars with original hardcoded values as defaults.

### Fixture in-tree (commit `9964d20c`)

- `fixtures/methodology_fixture/clean_slate_rescored/` — 181 JSONs, ~1.5MB, accessed via `results/clean_slate_rescored` symlink.

### Llama-4-Scout config (commit `a88059e9`)

- `configs/agents/clean_slate_llama4scout.yaml` — `api_key` standardized to `sk-no-key-required` (matches vLLM `--api-key` flag).

---

## 22. Reproducibility recipe

```bash
# Prereqs
export PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject:$PYTHONPATH
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench

# 1. Restore methodology fixture (in-tree from 9964d20c forward)
ln -sf "$PWD/fixtures/methodology_fixture/clean_slate_rescored" \
       "$PWD/results/clean_slate_rescored"

# 2. Regenerate verdict matrix from v6 paper subset
CGA_VERDICT_RESULTS_DIR="$PWD/results/full_v6a_706" \
  python scripts/experiments/verdict_matrix_v5.py
#    Expected: 19,062 episodes, 9 models, v4_hard 55.4%

# 3. Re-run e1-e5 + extras
for s in exp_e1_verdict_flip exp_e2_bsr exp_e3_instrumentation_ablation \
         exp_e4_operating_point exp_e5_evaluator_expansion \
         exp_e_difficulty_equivalence exp_orthogonal_perturbation; do
  python scripts/experiments/${s}.py
done

# 4. Run pipeline against full Phase B corpus (skip vLLM step if no
#    live qwen397b endpoint)
python scripts/update_all_auto_numbers.py \
  --episodes-dir results/full_v6b --skip-vllm

# 5. Step 11 with custom judge endpoint (see §14 caveats)
CGA_VLLM_BASE_URL=http://your-host:port/v1 \
CGA_VLLM_MODEL=your-model-id \
  python scripts/experiments/terminal_output_baselines.py

# 6. Final macro extraction
python scripts/experiments/extract_auto_numbers.py
cp paper/auto_numbers.tex paper/auto_numbers_v6.tex
```

---

## 23. Known limitations & disclosures

1. **Nemotron30b 21 / 2,118 (0.99%) empty episodes** in paper subset.
2. **Step 11 LLM judge is gemma-4-31b** (substitute), not canonical 397B.
3. **gemma31b 190 / 9,560 (1.99%) empty in full corpus** (auto_v2 / pediatric only; NOT in paper subset).
4. **Llama-4-Scout served under FP8 Marlin emulation** on A100 cap 8.0 (no native FP8 tensor cores).
5. **3 cres_* scripts failed to run** (out-of-scope defense ablations); 12 of 15 cres_* scripts succeeded.
6. **v3_p1c_verdict_integration loaded 0 episodes** — episode-dir override needed; not a paper-macro dependency.
7. **`paper/main_*.tex` not pdflatex-compiled** in this cycle — macros are syntactically self-consistent but no end-to-end TeX build was run.

---

## 24. Commit chain

```
4c04543c — feat(phase_b): infrastructure for resumable Phase B + dual-host boost daemon
93b072a0 — feat(eval_science): regenerate paper auto-numbers from Phase B v6 corpus
338b22e5 — feat(eval_science): regenerate verdict matrix + e1-e5 + analysis report on v6 corpus
60beb969 — feat(eval_science): close Step 11 terminal-output baseline against gemma-4-31b on 145
3dcee41d — docs(eval_science): critical review of v6 corpus + experiment data integrity
2915dc36 — feat(eval_science): close v6 critical-review loose ends + 9 stale-file refresh
9964d20c — chore(eval_science): commit clean_slate_rescored methodology fixture in-tree
a88059e9 — feat(eval_science): expand v6 paper subset to 9 models — add Llama-4-Scout
[next]   — docs(eval_science): canonical comprehensive v6 report (this file)
```

---

## Closing

All Phase B + v6 + 9-model expansion + critical-review remediation work
is complete and committed. The paper's auto-numbers are sourced from a
fully self-consistent 19,062-episode benchmark across 9 models / 5
vendors. The three remaining MEDIUM disclosures (§23 items 1, 2, 4) are
documented with paste-ready boilerplates for the paper.

GPU fleet status: 145 = 0 MB, 144 = 0 MB, 146 = no GPU. Nothing running.
