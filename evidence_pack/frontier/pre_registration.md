# Frontier API v8 Expansion — Pre-Registration

**Filed**: 2026-04-28 (UTC)
**Branch**: `eval_science`
**Scope**: NeurIPS 2026 D&B Track frontier API expansion experiment, attached to camera-ready submission for `paper/main_final_v18.tex`.

This document is filed **before** any frontier API call is made for Stage S1 onward. It declares the success/failure criteria for the headline claim, the falsification clause, and the analysis decisions, so that the result analysis cannot be retroactively shaped to match the data ("p-hacking by exploration").

---

## 1. Hypothesis under test

> **H1.** Across our v8 corpus (706 v6 scenarios + 236 v7 expansion scenarios = 942 total), the variance in safety verdicts attributable to **evaluator choice** dominates the variance attributable to **model identity**, regardless of whether the model is open-weight or frontier-API-tier, and regardless of within-vendor tier shifts (Claude Sonnet 4.6 vs Opus 4.7).

Operationalized:

- Let `V(eval, model, episode) ∈ {0,1}` be the binary verdict produced by evaluator *eval* on *model*'s output on *episode*.
- Let σ²_eval = Var across the 6 evaluators {DxEM, AC-Proxy, MAB-Proxy, C2≥0.7, ACov≥0.5, CGA-Bench} holding (model, episode) fixed, then averaged.
- Let σ²_model = Var across the 13 models (9 open-weight v6 baseline + 4 frontier API: Claude Sonnet 4.6, Claude Opus 4.7, GPT-5.5-pro, Gemini 3 Pro) holding (evaluator, episode) fixed, then averaged.
- Let R = σ²_eval / σ²_model.

**H1 holds iff R ≥ 2.0 with 1000-iteration bootstrap 95% confidence interval excluding 1.0.**

## 2. Success / partial / failure thresholds

Pre-declared (binding):

| Tier | Conditions on R + per-domain (C) + falsification F | Paper claim wording |
|---|---|---|
| **A — Strong** | R ≥ 2.0 AND CI excludes 1.0 AND ≥ 80% of CPG domains satisfy domain-level R ≥ 2.0 AND F not triggered | "Across 942 scenarios and 13 models spanning 3 frontier vendors plus a within-vendor Sonnet/Opus pair, evaluator-choice variance dominates model-identity variance by Xx [95% CI a–b]; the dominance holds in Y% of CPG domains" |
| **B — Partial** | R ≥ 1.0 with CI excluding 1.0, but either R < 2.0 or domain-level pass rate ∈ [0.5, 0.8) | "Partial transfer: ranking instability dominates in aggregate, but model identity becomes more important in specific CPG domains [list]" |
| **C — Falsification** | CI includes 1.0 OR F-clause triggered (any evaluator pair Spearman ρ ≥ 0.95 across all 13 models) | "Frontier-tier disagrees: evaluator choice does NOT dominate model identity at the deployment-tier ceiling; ranking-instability claim is most relevant to mid-tier open-weight models" — claim scope narrowed |

**No mid-experiment threshold adjustment.** If the data lands in tier B, the paper says tier B. No "we re-thought it as A" allowed.

## 3. Falsification clause F (registered before data)

The paper is required to retract the central claim if **either**:

- **F.1**: For any of the C(6, 2) = 15 evaluator pairs, Spearman ρ on the 13-model ranking is ≥ 0.95. This would mean the 6 evaluators are functionally redundant and "evaluator choice" is not a real axis of variance.
- **F.2**: The 1000-iter bootstrap 95% CI on R = σ²_eval / σ²_model includes 1.0 in aggregate.

Either condition forces a tier-C "scope narrow" rewrite of paper §6.

## 4. Within-vendor robustness sub-test (S2 gate)

A separate, more targeted version of H1 is checked between Claude Sonnet 4.6 and Claude Opus 4.7 only:

- σ²_eval_within_vendor = Var across 6 evaluators holding (the Anthropic model, episode) fixed, averaged.
- σ²_within_vendor = Var across {Sonnet, Opus} holding (evaluator, episode) fixed, averaged.
- R_within = σ²_eval_within_vendor / σ²_within_vendor.

**Within-vendor success: R_within ≥ 2.0 with bootstrap 95% CI excluding 1.0.**

Failure mode: if Sonnet vs Opus performance differs more than evaluator choice, the within-vendor robustness claim fails. The paper must report this honestly.

## 5. Pre-declared analysis pipeline (locked)

1. **Subset** v6 baseline matrix (`evidence_pack/analysis/verdict_matrix_v6_typed.json`) to the 706 scenarios in `evidence_pack/frontier/w8_706_manifest.json` (fingerprint `171e59b80716a538…`).
2. **Take** v7 baseline matrix (built post-Track-1 GPU completion) for the 236 expansion scenarios.
3. **Frontier**: each of {Sonnet 4.6, Opus 4.7, GPT-5.5-pro, Gemini 3 Pro} runs all 942 scenarios with run_index=0, ReAct scaffold, BM25 retrieval (top-k=5), 100K-token / 50-tool-call budget — identical to the open-weight 9-model regime.
4. **Score** all frontier outputs via `scripts/experiments/run_six_evaluator_scoring.py` (existing post-hoc CPG engine; no per-frontier customization).
5. **Compute** R and R_within with 1000-iteration cluster bootstrap (cluster = scenario_id, so per-scenario stochasticity does not violate IID assumption).
6. **Per-domain** R repeated for each CPG domain in the manifest (≥ 5 episodes/domain minimum; smaller domains aggregated into "other").
7. **Adversarial** worst-case: identify the model pair {a, b} maximizing |mean(score_a) − mean(score_b)| across the joint matrix; recompute R_within for {a,b}.
8. **Macros emitted** to `paper/frontier_macros.tex`, copied verbatim from analysis JSON.

No step in the pipeline may be added, removed, or reordered after S1 begins.

## 6. Stop conditions

The experiment is allowed to stop early under exactly these conditions:

- **API budget breach**: cumulative cost exceeds the per-stage cap (S1 $100, S2 $500, S3 $700, S4 $750). Mid-stage cost guardrails abort before the next call if projected overrun.
- **Infrastructure failure**: ≥ 5% parse-failure rate on any single model run (e.g., LLM JSON corruption). Stage paused, infra fixed, stage restarted from clean checkpoint.
- **User abort**: user reviews stage gate output and explicitly says stop.

Otherwise, all 4 stages run on all 942 scenarios.

## 7. Disclosure & version control

- Filename: `evidence_pack/frontier/pre_registration.md`
- Committed to git as part of the v8 frontier-expansion infrastructure commit.
- The git commit hash containing this file is referenced in `paper/main_final_v18.tex` §6 alongside the falsification clause (so reviewers can verify the pre-reg pre-dates the data).
- This document is not edited after the first commit. Errata go to a separate `pre_registration_errata.md`.

## 8. Author & approval

- **Author**: CGA-Bench Developer (Claude Opus 4.7 1M context, supervised by user `anonymous-org@146`).
- **Approval gate**: User confirmed γ scope (v6 + v7 = v8 = 942 scenarios, 4 frontier models, 1 run match against v6 baseline run-0) on 2026-04-28 in the planning conversation; quoted thesis verbatim:
  > "Claim: vendor가 바뀌든, 같은 vendor 안에서 tier가 바뀌든, paper의 핵심 청구 (evaluator choice가 model identity보다 verdict variance를 더 결정함)는 유지된다."

---

*This pre-registration is registered. No changes to thresholds, definitions, or pipeline are allowed after the first frontier API call (Stage S1).*
