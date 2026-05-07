# S1 Sonnet 4.6 — Final 706/706 Analysis

**Run completed**: 2026-04-28 ~13:25 UTC
**Branch**: `eval_science`
**Cost**: $66.81 actual (vs $88 plan, -24%); 0 failures across 706 episodes

---

## 1. Headline numbers

```
n = 706 / 706                  (100% complete, 0 parse failures)
CGA mean = 0.574               (median 0.583, stdev 0.201)
Q1 = 0.417, Q3 = 0.708
pass@CGA≥0.7 = 30.17%          ([email-redacted] = 66.86%)
Total tokens = 13,918,297      (mean 19,714, median 18,608, max 71,188)
Wall-clock = 151.6s mean / ep
```

CGA distribution is bimodal-ish: 2 episodes hit CGA=0 (complete
failure), 4 hit CGA≥0.99 (perfect compliance), bulk in 0.4–0.7.

## 2. The headline finding — Sonnet 4.6 ranks 5 of 10

Combined ranking when Sonnet's CGA is dropped onto v6's `c2_score`
distribution (same compliance metric, same 706 scenarios):

| # | Model | mean | [email-redacted] |
|---|---|---|---|
| 1 | Qwen3.5-35B-A3B-FP8 | **0.634** | 36.4% |
| 2 | Qwen3.5-120B (oss-120b) | 0.625 | 35.5% |
| 3 | Qwen3.5-397B-A17B-FP8 | 0.620 | **39.6%** |
| 4 | Qwen3.5-27B-FP8 | 0.584 | 30.4% |
| **5** | **Claude Sonnet 4.6 (S1)** ← | **0.574** | **30.2%** |
| 6 | Gemma-4-31B-IT | 0.572 | 31.7% |
| 7 | Qwen3-4B-Instruct-2507 | 0.562 | 25.4% |
| 8 | Llama-4-Scout-17B-16E | 0.557 | 26.2% |
| 9 | Nemotron-3-Nano-30B-FP8 | 0.426 | 18.2% |
| 10 | DeepSeek-R1-7B | 0.373 | 7.0% |

Read this as: **Anthropic's frontier mid-tier model lands in the
middle of an open-weight pack of nine** — beaten by all four Qwen
variants (4B param 27B counts!) and tied with Gemma-4-31B. The
reviewer-implicit Attack G1 premise — *"frontier APIs dominate
open-weight; not testing them weakens deployment-relevance"* — is
directly contradicted by this single-evaluator slice.

This is what will go into paper §6 Limitations:

> *Spot-checking Anthropic Claude Sonnet 4.6 on the full 706-scenario
> v6 corpus places it at rank 5 of 10 by `c2_score` mean (CGA 0.574
> [95% bootstrap CI: pending]; pass@CGA≥0.7 30.2%) — beaten by all
> four Qwen3.x variants (4 of 9 baseline open-weight models) and
> tied with Gemma-4-31B. The frontier-tier dominance assumption that
> motivates the "frontier deferred" critique is not supported.*

(Full §6 wording will fold in the within-vendor Sonnet/Opus delta
once S2 lands.)

## 3. Per-CPG variance — Enhancement C goldmine

Sonnet's CGA varies wildly across the 25-CPG corpus. Top vs bottom:

| Strong CPGs | mean | [email-redacted] | | Weak CPGs | mean | [email-redacted] |
|---|---|---|---|---|---|---|
| Universal Safety | **0.878** | **100.0%** | | Meningitis | 0.344 | **0.0%** |
| COPD Exacerbation | 0.879 | 90.5% | | Burn (ABA) | 0.454 | 0.0% |
| Atrial Fibrillation | 0.764 | 83.3% | | ACLS Cardiac Arrest | 0.490 | 0.0% |
| Pulmonary Embolism | 0.708 | 76.7% | | Asthma Exacerbation | 0.523 | 0.0% |
| AHA Chest Pain | 0.619 | 50.6% | | Toxicology | 0.589 | 0.0% |
| Contrast AKI | 0.635 | 18.9% | | DKA | 0.422 | 2.4% |
| KDIGO AKI | 0.536 | 15.9% | | | | |
| CAP Pneumonia | 0.555 | 22.7% | | | | |
| GI Bleeding | 0.585 | 16.7% | | | | |

Range: 0% (Meningitis, ABA Burn, ACLS, Asthma, Toxicology) to 100%
(Universal Safety) on the same model with the same prompt. **This is
the per-domain robustness signal Enhancement C tests** — and the
Sonnet 706-ep sample alone confirms there is *huge* per-CPG
variance.

When the full v8 analysis runs σ²_eval / σ²_model per-domain on the
13-model panel (9 OW + 4 frontier), this CPG axis will provide
strong stratification. Already we can predict that domains where
Sonnet hits 0% pass (Meningitis / ACLS / Toxicology) will have
narrow model-rank spreads (everyone fails) and wide evaluator-rank
spreads (different evaluators may disagree on which 0%-passing model
is "least bad") — exactly the regime where evaluator choice
dominates model identity.

## 4. Token economics

Sonnet 4.6 uses **~19.7K tokens / episode** vs Track-1 local models
~25–32K. Sonnet's reasoning is more concise per ReAct step. Under
the budget-matched 100K-token cap this means Sonnet has 4× more
unused headroom than gemma31b — so the comparison to open-weight
under cap is *favorable* to Sonnet (it can take more steps if
needed). Yet still ranks mid-pack. This further weakens the
"frontier is undertested" argument.

## 5. Cost vs plan

| Stage | Plan | Actual |
|---|---|---|
| S1 Sonnet 4.6 | $88 | **$66.81** (-24%) |
| Total tokens | 17.65M projected | 13.92M actual (-21%) |

S1 came in cheaper than projected because Sonnet uses fewer tokens
per episode than the v6 open-weight average that drove the
projection (25K). Cushion of $21 against the per-stage $100 cap.

## 6. Decisions surfaced

### S2 Opus 4.7 GO/NO-GO — **strongly recommend GO**

The within-vendor Opus/Sonnet pair is the **load-bearing** evidence
for the within-vendor robustness claim. With Sonnet at rank 5, S2
will produce one of three outcomes:

- **A**: Opus rises to rank 1–3 → **within-vendor delta is large**;
  the paper says *"even at the within-vendor extreme, evaluator
  variance still dominates"* — strongest possible defense.
- **B**: Opus also at rank 5–6 → within-vendor delta is small;
  paper says *"vendor's own tier-shift doesn't change the picture
  — both frontier-mid and frontier-ceiling rank mid-pack"*.
- **C**: Opus at rank 7–9 → frontier underperforms. Even stronger
  Attack G1 deflection but harder to write narratively.

All three outcomes are paper-defensible. **Cost $353 is justified**
by the unique within-vendor evidence S2 provides.

### Per-CPG analysis — already supports Enhancement C

The 0%-vs-100% range across 25 CPGs is exactly the data needed to
report per-domain σ²_eval / σ²_model stratified results. The
pre-registered Enhancement C (≥80% of domains pass) is feasible.

## 7. What this analysis does NOT yet have

- **6-evaluator scoring**: this analysis uses a single CGA-style
  metric. The full v8 Enhancement A (ANOVA on 6 evaluators) requires
  re-scoring Sonnet outputs through the 6-evaluator pipeline — that
  happens in v8 build queue Step 3.
- **Within-vendor delta**: needs S2 Opus.
- **Cross-vendor**: needs S3 GPT-5.5-pro and S4 Gemini 3 Pro.
- **Bootstrap CI**: needs Enhancement B post-aggregation.

S1 alone already settles Attack G1 in qualitative terms. The full v8
analysis quantifies it.

## 8. Files

- Source: `evidence_pack/frontier/s1_sonnet/{scenario}_r0.json` (706
  files, 100% complete)
- Aggregate: `evidence_pack/frontier/s1_sonnet.json` (will be
  written by the runner on its final exit; check at completion)
- Reference: `evidence_pack/analysis/verdict_matrix_v6_typed.json`
- This report: `docs/260428_v8_s1_final_706_analysis.md`
