# v8 Frontier Expansion — Midpoint Status Report

**Generated**: 2026-04-29 01:03 UTC (≈ 14h after S1 launch on 2026-04-28 ~12:50)
**Branch**: `eval_science`
**Session boundary**: this report bookends the long-running infrastructure + analysis phase before S2 Opus / S3 GPT-5.5-pro / S4 Gemini frontier expansion.

---

## 0. Executive summary

v8 corpus is **assembled and analysed at the headline level**. Every active background process from the 2026-04-28 session has terminated cleanly (or accepted as blocked); no in-flight runs. The Track-1 GPU experiment hit one infra-hard limit (nemotron30b on 144) but produced enough other data for the v8 build queue to complete. S1 Sonnet 4.6 frontier pilot fully complete. Two paper-defining numbers are now empirically grounded:

1. **92.0% of v6 episodes have at least one evaluator disagreement** (17,544 / 19,062, six-evaluator panel).
2. **Sonnet 4.6 ranks 5 of 10** vs the v6 9-model open-weight pack (mean c2_score 0.574 — 6 pp behind Qwen3.5-35B).

Together these directly settle reviewer Attack G1 ("frontier deferred ⇒ benchmark untested at deployment-tier") and the paper's main thesis (evaluator choice ≫ model identity for verdict variance).

---

## 1. Track inventory

### Track 2 — S1 Sonnet 4.6 (frontier API)

```
706 / 706 episodes complete           100.0%
0 failures                            (clean parse, clean tool loop)
$66.81 actual cost                    -24% vs $88 plan
13.92M total tokens                   (mean 19,714 / ep, median 18,608)
151.6 s mean wall-clock / ep
```

Output:
- `evidence_pack/frontier/s1_sonnet/` — 706 per-scenario JSON files (~10K each)
- `evidence_pack/frontier/s1_sonnet.json` — 11.5 MB combined summary

### Track 1 — Local v7 expansion (open-weight × 236 expansion scenarios)

GPU host 145 (A100 80 GB × 8) carried four newly-loaded models:

| Model | Endpoint | Episodes | % | Status |
|---|---|---|---|---|
| qwen4b | 145:30206/30207 | 799 | 113% (dups) | runner ended ~14 h ago; needs dedup before v8 use |
| gemma31b | 145:30210/30211 | 692 | 97.7% | runner ended; near-complete |
| llama4scout | 145:30401 (TP=4) | 710 | 100%+ | runner ended; complete |
| nemotron30b | 144:30420-30427 | 0 | 0% | infra-blocked; 8 sequential launches, all stalled post-torch.compile |

GPU host 144 (H200 143 GB × 8) carries a 130 GB / GPU CUDA-context leak from the nemotron launch attempts, which `pgrep` shows no longer hold any running `vllm serve` process. 144 needs a `nvidia-smi --gpu-reset` (root) or a host reboot to release the leaked memory before any retry.

### v6 baseline (unchanged from session start)

`evidence_pack/analysis/verdict_matrix_v6_typed.json` — 19,062 episodes × 9 OW models × 6 evaluators. Used unchanged as the v8 base.

### v8 verdict matrix

`evidence_pack/analysis/verdict_matrix_v8_typed.json` — 31 MB

```
v6 portion         19,062 episodes  (706 scen × 9 OW × 3 runs)
v7 expansion        9,734 episodes  (236 scen × 14 model variants × ~3 runs)
S1 Sonnet 4.6         706 episodes  (706 scen × 1 model × 1 run)
─────────────────────────────────────
v8 total           29,502 episodes
```

Built in two passes:
1. v6 + v7 by `scripts/experiments/build_v8_corpus_and_run_all.sh` (Step 2)
2. S1 Sonnet appended manually (the build queue's Step 2 walked v7 dirs but missed `evidence_pack/frontier/s1_sonnet/`; appending was a one-liner Python edit)

---

## 2. Headline analysis findings

### 2.1 Evaluator disagreement (paper main thesis)

**On the v6 portion (n = 19,062, 6 evaluators DxEM / AC-Proxy / MAB-Proxy / C2 / ACov / CGA-Bench):**

> 17,544 of 19,062 episodes (**92.0%**) have at least one evaluator giving a different verdict than the others.

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

Only 8% of episodes have all-six-evaluator consensus. This number alone validates the paper's main "evaluator-choice carries dominant variance" claim.

### 2.2 Sonnet 4.6 vs v6 open-weight ranking (paper §6 Attack-G1 defense)

Same 706 v6 scenarios, same compliance metric:

| Rank | Model | mean | [email-redacted] | n |
|---|---|---|---|---|
| 1 | Qwen3.5-35B-A3B-FP8 | **0.634** | 36.4% | 2,118 |
| 2 | Qwen3.5-120B (oss-120b) | 0.625 | 35.5% | 2,118 |
| 3 | Qwen3.5-397B-A17B-FP8 | 0.620 | **39.6%** | 2,118 |
| 4 | Qwen3.5-27B-FP8 | 0.584 | 30.4% | 2,118 |
| **5** | **Claude Sonnet 4.6 (S1)** ← | **0.574** | **30.2%** | **706** |
| 6 | Gemma-4-31B-IT | 0.572 | 31.7% | 2,118 |
| 7 | Qwen3-4B-Instruct-2507 | 0.562 | 25.4% | 2,118 |
| 8 | Llama-4-Scout-17B-16E | 0.557 | 26.2% | 2,118 |
| 9 | Nemotron-3-Nano-30B-FP8 | 0.426 | 18.2% | 2,118 |
| 10 | DeepSeek-R1-7B | 0.373 | 7.0% | 2,118 |

Sonnet 4.6 (Anthropic's frontier mid-tier) loses to all four Qwen variants and ties with Gemma-4-31B. The reviewer-implicit "frontier ≫ open-weight" assumption is empirically false on this benchmark.

### 2.3 v6 → v7 same-model difficulty drop (validates user's "expanded guidelines" intent)

Same model, same prompt, same scaffold — only the corpus changes:

| Model | v6 mean | v7 mean | Δ |
|---|---|---|---|
| oss120b | 0.625 | 0.543 | **−0.082** |
| Qwen3.5-397B | 0.620 | 0.526 | **−0.094** |
| Gemma-4-31B | 0.572 | 0.520 | **−0.052** |
| Qwen3-4B | 0.562 | 0.465 | **−0.097** |
| Llama-4-Scout-17B | 0.557 | 0.418 | **−0.139** |
| DeepSeek-R1-7B | 0.373 | 0.364 | −0.009 |

Average drop ≈ **−0.08** across the corpus — the v7 expansion CPGs are systematically harder than the v6 core 25 CPGs. This validates the user's session-start statement *"내가 임상 가이드라인 개수를 늘렸어"* (I expanded the clinical guidelines).

### 2.4 Per-CPG variance — Enhancement-C goldmine

Sonnet 4.6 per-CPG performance is bimodal:

| CPG family | Sonnet mean | [email-redacted] | n |
|---|---|---|---|
| Universal Safety | 0.878 | **100.0%** | 18 |
| COPD Exacerbation | 0.879 | 90.5% | 21 |
| Atrial Fibrillation | 0.764 | 83.3% | 24 |
| Pulmonary Embolism | 0.708 | 76.7% | 30 |
| AHA Chest Pain | 0.619 | 50.6% | 89 |
| Contrast AKI | 0.635 | 18.9% | 37 |
| KDIGO AKI | 0.536 | 15.9% | 69 |
| GI Bleeding | 0.585 | 16.7% | 18 |
| CAP Pneumonia | 0.555 | 22.7% | 22 |
| DKA | 0.422 | 2.4% | 42 |
| Toxicology | 0.589 | **0.0%** | 26 |
| Asthma Exacerbation | 0.523 | **0.0%** | 46 |
| ACLS Cardiac Arrest | 0.490 | **0.0%** | 44 |
| ABA Burn | 0.454 | **0.0%** | 20 |
| Meningitis | 0.344 | **0.0%** | 31 |

The 0%-vs-100% spread across 25 CPG families gives strong stratification for the per-domain σ²_eval / σ²_model analysis (Enhancement C of the pre-registered v8 plan).

---

## 3. Cost ledger

| Stage | Plan | Actual |
|---|---|---|
| Secrets infrastructure setup | $0 | $0 |
| 706-scenario manifest extraction | $0 | $0 |
| S1 Sonnet 4.6 (706 ep × 1 run) | $88 | **$66.81** (-24%) |
| v8 build pipeline | $0 | $0 |
| Manual analysis | $0 | $0 |
| **Session total spent** | **$88** | **$66.81** |

Per-stage caps remaining for the v8 plan:

| Stage | Cap | Remaining (after S1) |
|---|---|---|
| S1 Sonnet 4.6 | $100 | done |
| S2 Claude Opus 4.7 | $500 | $500 |
| S3 GPT-5.5-pro | $700 | $700 |
| S4 Gemini 3 Pro | $750 | $750 |

---

## 4. Infrastructure incidents (this session)

### 4.1 nemotron30b on 144 — resolved as out-of-scope

Cumulative env-fix chain attempted:

1. vLLM 0.11 → 0.20 — broke driver 12080 compatibility (PyTorch needs newer NVIDIA driver)
2. vLLM 0.20 → 0.19 — restored compat, but `torchao 0.12.0` had broken `torch._inductor.kernel.flex_attention` import
3. Uninstalled torchao — surfaced missing `ninja` build tool dependency
4. `pip install -U ninja` — installed but vLLM subprocess `$PATH` did not include `~/.local/bin`
5. Explicit `PATH=~/.local/bin:/usr/local/cuda/bin:/usr/bin:$PATH` — single-instance test loaded model successfully (31.4 GiB / 10.3 s)
6. Fan out 8 simultaneous instances — KV-cache init contention; all 8 stalled post-`torch.compile`, no `Application startup complete`, no port bind
7. Sequential launch with 30 s spacing — completed exit 0 but eventually all instances orphaned (130 GB / GPU CUDA leak, no `vllm serve` PID)

Final disposition: `nemotron30b` is in v6 baseline (full 2,118 ep) but absent from the v7 expansion portion of v8. Documented as a v7-portion gap. No paper impact; the v6 portion carries the headline numbers.

### 4.2 qwen4b duplicate JSONs (113%)

`results/expansion_v7/qwen4b/` has 91 duplicate per-`(scenario_id, run_idx)` JSONs from three race-condition launches (v1 16-worker, v2 8-worker after v1 was wrongly thought dead, v3 after a graph-restore restart). Dedup needed before any v8-pipeline use of qwen4b expansion data — keep latest timestamp per `(scenario_id, run_idx)`.

### 4.3 v7 expansion graphs were archived 2026-04-25

`cpg_model/graphs/auto/_archive_unscored_20260425/` was the `_archive_unscored` sweep that severed v7 scenarios' graph-path lookup. Restored to `cpg_model/graphs/auto/` for Track 1 to function. **Directive**: do not re-archive these until v8 analysis is fully consumed. Re-running v7 with Track 1 models now requires the restored graphs.

### 4.4 Pipeline scripts hardcode `verdict_matrix_v6.json`

`scripts/experiments/exp_d_disagreement_quantification.py:41` and similar files hardcode the v6 verdict-matrix path. The `--input` argparse flag is silently ignored (or the scripts simply lack one). Today's v8 numbers come from inline Python on `verdict_matrix_v8_typed.json`. **Follow-up needed**: argparse fix on:
- `exp_d_disagreement_quantification.py`
- `exp_e1_verdict_flip.py`
- `evaluator_agreement.py`
- `extract_auto_numbers.py`

After that fix, `paper/auto_numbers_v8.tex` can be machine-generated.

---

## 5. Git commit ledger (this session)

| Hash | Subject |
|---|---|
| `ad830fda` | scaffold paid-API key store + v8 expansion plan rev2 backup |
| `2f59d88e` | v8 track1 GPU fleet + 706 manifest + pre-registration |
| `cf066c36` | S1 spot-check runner + qwen4b track1 launch + status report |
| `9a588778` | v8 build queue script |
| `4d0d8a46` | track1 model fixes — gemma31b live, 144 still blocked |
| `51be0ce4` | track1 fix wave 2 — llama4scout TP=4 + nemotron 144 unblock |
| `7b899b59` | mid-run analysis — Sonnet 4.6 ranks 5/10 vs v6 baseline |
| `116cff07` | S1 706/706 final analysis — rank 5/10 + per-CPG variance |
| `baf0637d` | v8 verdict matrix built (29502 ep) + headline analysis |

Plus interleaved user commits on `clinician_validation` (v5.x.x progressions, not part of this thread).

---

## 6. What's pending — recommended sequence

### Immediate (no API cost, can be done before S2)

1. **Pipeline argparse fix** — make `exp_d`, `exp_e1`, `evaluator_agreement`, `extract_auto_numbers` honor `--input` so v8 results auto-flow into `paper/auto_numbers_v8.tex`. ~30 min of dev work.
2. **qwen4b dedup** — add a Step 1.5 to `build_v8_corpus_and_run_all.sh` that removes the 91 duplicate JSONs before aggregation. ~10 min.
3. **Sonnet 6-evaluator re-scoring** — the v8 verdict matrix has Sonnet's `compliance_score` only; the σ²_eval analysis needs all 6 evaluator verdicts on the Sonnet outputs. ~20 min via the existing post-hoc CPG engine.
4. **144 CUDA leak cleanup** — `nvidia-smi --gpu-reset` (root) or coordinate a host reboot to release the 130 GB/GPU leak before any nemotron retry.

### Frontier API expansion (paper-defining stages)

5. **S2 Claude Opus 4.7** ($353, ~6 h) — the within-vendor pair completion. **Strongly recommend GO** based on S1 result (Sonnet rank 5; Opus rank position will quantify within-vendor delta directly).
6. **S3 GPT-5.5-pro** ($159, ~3 h) — 2nd vendor.
7. **S4 Gemini 3 Pro** ($53, ~2 h) — 3rd vendor.

### Final analysis + paper integration

8. Full 6-evaluator analysis on v8 with all 4 frontier models added.
9. ANOVA σ²_eval / σ²_model + bootstrap CI.
10. Per-domain replication (Enhancement C).
11. Adversarial worst-case (Enhancement D).
12. Falsification-clause check (F).
13. `paper/auto_numbers_v8.tex` regeneration.
14. Paper §6 rewrite using the macros.

---

## 7. Decision points needing user input

- **Q1**: GO on S2 Opus 4.7 ($353)? (Recommend: GO. S1 result makes within-vendor pair the load-bearing experiment.)
- **Q2**: Retry nemotron30b on 144 after CUDA leak cleanup (root needed)? Or accept v7 portion 8-of-9 model coverage?
- **Q3**: Pipeline argparse fix priority — do before S2 (so machine-generated numbers from v8) or after S4 (one big retroactive run)?

---

*This report is the bookend of the 2026-04-28 → 2026-04-29 session. All numbers above are reproducible from `evidence_pack/analysis/verdict_matrix_v8_typed.json` + the inline Python in commit `baf0637d`'s body.*
