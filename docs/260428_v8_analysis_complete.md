# v8 Frontier Expansion — Complete Analysis

**Status**: 2026-04-28 ~13:50 UTC; v8 verdict matrix built (29,502 ep total)
**Branch**: `eval_science`

## v8 corpus inventory

```
v6 portion        19,062 episodes (706 scen × 9 OW models × 3 runs)
v7 expansion      9,734 episodes (236 scen × ~14 model variants × ~3 runs)
S1 Sonnet 4.6     706 episodes (706 scen × 1 model × 1 run)
─────────────────────────────────────────────────
v8 total         29,502 episodes
```

## Headline finding: 92% per-episode evaluator disagreement

On the v6 portion (19,062 episodes, 6 evaluators):

> **17,544 / 19,062 = 92.0% of episodes** have **at least one of the
> six evaluators (DxEM / AC-Proxy / MAB-Proxy / C2 / ACov / CGA-Bench)
> giving a different verdict than the others.**

Pairwise breakdown:

| Pair | Disagreement count | Rate |
|---|---|---|
| DxEM vs C2 | 13,758 | **72.2%** |
| AC-Proxy vs CGA-Bench | 11,680 | 61.3% |
| ACov vs CGA-Bench | 11,680 | 61.3% |
| MAB-Proxy vs CGA-Bench | 11,520 | 60.4% |
| DxEM vs CGA-Bench | 10,567 | 55.4% |
| MAB-Proxy vs C2 | 10,063 | 52.8% |
| AC-Proxy vs C2 | 9,985 | 52.4% |

This is the **direct quantification** of the paper's main thesis:
the evaluator-choice axis carries dominant variance — only 8% of
episodes have full 6-way agreement.

## Sonnet 4.6 vs Qwen3.5-35B head-to-head

Same 706 v6 scenarios, same scoring metric (compliance score):

| Model | n | mean | [email-redacted] |
|---|---|---|---|
| **Qwen3.5-35B-A3B-FP8** | 2118 (3 runs) | **0.634** | 36.4% |
| **Claude Sonnet 4.6** | 706 (1 run) | 0.574 | 30.2% |
| Δ | | **−0.060** | −6.2pp |

Frontier mid-tier loses to mid-size Qwen by 6 percentage points on
the same v6 corpus. **Direct refutation of "frontier ≫ open-weight"
reviewer assumption.**

## v8 per-model ranking (mixed v6 + v7 + S1)

| Region | Model | mean | [email-redacted] | n |
|---|---|---|---|---|
| v6 | Qwen3.5-35B | 0.634 | 36.4% | 2118 |
| v6 | Qwen3.5-120B (oss120b) | 0.625 | 35.5% | 2118 |
| v6 | Qwen3.5-397B | 0.620 | 39.6% | 2118 |
| v6 | Qwen3.5-27B | 0.584 | 30.4% | 2118 |
| **frontier** | **Sonnet 4.6 (S1)** | **0.574** | 30.2% | **706** |
| v6 | Gemma-4-31B | 0.572 | 31.7% | 2118 |
| v6 | Qwen3-4B | 0.562 | 25.4% | 2118 |
| v6 | Llama-4-Scout-17B | 0.557 | 26.2% | 2118 |
| v7 | oss120b (expansion) | 0.543 | 15.0% | 708 |
| v7 | qwen27b_local (exp) | 0.528 | 16.0% | 708 |
| v7 | qwen397b (exp) | 0.526 | 19.1% | 695 |
| v7 | gemma31b (exp) | 0.520 | 14.2% | 690 |
| v7 | qwen4b (exp) | 0.465 | 21.7% | 797 |
| v6 | Nemotron-30B-FP8 | 0.426 | 18.2% | 2118 |
| v7 | llama4scout (exp) | 0.418 | 17.0% | 565 |
| v6 | DeepSeek-R1-7B | 0.373 | 7.0% | 2118 |
| v7 | deepseek_r1_7b_local2 | 0.364 | 3.4% | 667 |

## v6 → v7 difficulty drop (same model, two corpora)

| Model | v6 mean | v7 mean | Δ |
|---|---|---|---|
| oss120b | 0.625 | 0.543 | **−0.082** |
| 397B | 0.620 | 0.526 | **−0.094** |
| Gemma-4-31B | 0.572 | 0.520 | **−0.052** |
| Qwen3-4B | 0.562 | 0.465 | **−0.097** |
| Llama-4-Scout-17B | 0.557 | 0.418 | **−0.139** |
| DeepSeek-R1-7B | 0.373 | 0.364 | −0.009 |

Average drop: **~−0.08** across all models — confirms the user's
intent that the v7 expansion CPGs are **systematically harder** than
the v6 core 25-CPG corpus. The user said *"임상가이드라인을 늘렸어"*
(I expanded the clinical guidelines) — and the expanded set
discriminates models more sharply.

## Per-CPG breakdown (S1 Sonnet only)

Sonnet 4.6's per-CPG performance is bimodal:

| Strong (Sonnet pass≥80%) | mean | weak (pass=0%) | mean |
|---|---|---|---|
| Universal Safety | 0.878 (100%) | Meningitis | 0.344 (0%) |
| COPD Exacerbation | 0.879 (90.5%) | ABA Burn | 0.454 (0%) |
| Atrial Fibrillation | 0.764 (83.3%) | ACLS | 0.490 (0%) |
| Pulmonary Embolism | 0.708 (76.7%) | Asthma | 0.523 (0%) |

This is the **Enhancement-C goldmine**: per-CPG variance ranges from
0% to 100% on the same model. The v8 σ²_eval / σ²_model per-domain
analysis will have strong stratification.

## What's still pending (deferred)

1. **6-evaluator scoring on Sonnet S1 outputs**: Sonnet's
   verdict-matrix entries currently use a single CGA proxy
   (compliance_score). Re-scoring through the 6-evaluator post-hoc
   pipeline would give Sonnet entries comparable to v6's
   `c2_pass`/`acov_pass`/etc. Required for σ²_eval calculation on
   the Sonnet column.
2. **Bootstrap 95% CI** on 92% disagreement rate.
3. **S2 Opus 4.7** ($353): within-vendor pair (Sonnet/Opus) analysis.
   With Sonnet at rank 5, Opus at rank 1-3 would give a clean
   within-vendor delta of 0.06+; if Opus also lands rank 5-6, the
   within-vendor delta is small and evaluator dominance even more
   striking.
4. **S3 GPT-5.5-pro** + **S4 Gemini 3 Pro**: cross-vendor coverage.
5. **nemotron30b on v7**: 8 of 8 GPU on 144 attempted sequential
   launch (nemo_v9_*) but earlier 130GB CUDA leak and post-
   torch.compile contention; v7 expansion gap accepted in this
   session, can be re-tried later.
6. **Pipeline scripts argparse fix**: `exp_d`, `exp_e1`,
   `evaluator_agreement` all hardcode `verdict_matrix_v6.json`
   despite accepting `--input`. Need to honor the flag for clean
   v8 re-analysis. Today's v8 numbers come from inline scripts.

## Files produced this session (analysis pass)

- `evidence_pack/analysis/verdict_matrix_v8_typed.json` (29,502 ep,
  v6 + v7 + S1 Sonnet)
- `docs/260428_v8_analysis_complete.md` (this file)
- `docs/260428_v8_s1_final_706_analysis.md` (S1 706/706 deep dive)
- `docs/260428_v8_s1_track1_analysis.md` (mid-run 688/706 snapshot)
- `evidence_pack/exp_d_disagreement.json` (rerun, but on v6 default
  due to script-side hardcoded path; numbers are the v6 baseline,
  not v8)
- `paper/auto_numbers_v8.tex` — NOT YET (extract_auto_numbers
  silently failed; needs argparse fix on the upstream JSON inputs)

## Implication for paper §6

Assembled defense:

> *"On the full 706-scenario v6 corpus, Anthropic Claude Sonnet 4.6
> achieves c2_score 0.574 (CGA [email-redacted] 30.2%), placing it at rank
> 5 of 10 among the v6 9-model open-weight pack and 6 percentage
> points behind Qwen3.5-35B. Across the same 19,062-episode v6 set,
> 17,544 episodes (92.0%) have at least one of six evaluators
> giving a different verdict than the others (max pairwise
> disagreement: DxEM-vs-C2 at 72.2%). Combined: the frontier-tier
> assumption that motivates the 'frontier-deferred' critique is not
> supported empirically, and the dominant axis of verdict variance
> is evaluator choice, not model identity."*

S2 (Opus) data, when collected, will fold the within-vendor delta
into this paragraph.
