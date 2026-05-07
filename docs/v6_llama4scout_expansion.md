# v6 Paper Subset Expansion to 9 Models — Llama-4-Scout Addition

**Date:** 2026-04-27
**Branch:** `eval_science`
**Trigger:** User directive — "병렬로 llama4-scout 실험 돌려줘 v6 에피소드에 대해서 확장으로 / GPU idle한 상황에서 활용을 해야겠다"

This is the v6 paper subset expansion run that adds Llama-4-Scout-17B-16E
as the 9th model. All headline tables go from 8 → 9 models, denominator
goes from 16,944 → 19,062 episodes.

---

## 1. Run summary

| Item | Value |
|---|---|
| Model | `meta-llama/Llama-4-Scout-17B-16E-Instruct` |
| Quantization | FP8 (Marlin emulation on A100, native FP8 unsupported on cap 8.0) |
| Endpoints | 4 × TP=2 on 145 (ports 30201-30204, GPU 0-7) |
| Workers | 64 (16 per endpoint, ssh-spawned ON 145, --host localhost) |
| Throughput | ~60 episodes/min sustained, 8/8 GPUs at 94-99% util |
| Wall-clock | ~42 min from worker spawn to 2,118 episodes |
| Output | `results/full_v6b_llama4scout/llama4scout/` (rsynced 145 → 146) |
| 145 fleet state | DOWN — all 4 containers `docker rm -f`'d, 8/8 GPUs at 0 MB |

**Initial deployment hiccups (all resolved):**

- First TP=8 attempt rejected — model needed TP=2 minimum (per user
  directive "TP를 왜 8로 해 1이나 2 최소로 하고 엔드포인트 여러개").
- TP=2 launch failed with HF gated-repo 401 — fixed by mounting
  `/home/anonymous-org/.cache/huggingface` and passing `HF_TOKEN` env var.
- 3-of-4 endpoints failed with engine-init OOM under
  `--gpus all + NVIDIA_VISIBLE_DEVICES`. Fixed by switching to
  `--runtime=nvidia + NVIDIA_VISIBLE_DEVICES` (no `--gpus all`).
- Workers initially 401-rejected — agent config had
  `api_key: "not_needed"` while vLLM expected `sk-no-key-required`.
  Fixed in `configs/agents/clean_slate_llama4scout.yaml`.

---

## 2. 9-model verdict matrix

```
Total episodes: 19,062  (706 × 9 × 3)
v4_hard rate  : 55.4%   (10,567 / 19,062)
v4_crit rate  :  5.5%   (1,045 / 19,062)
```

### Per-model rates

| Model | n | v4_hard | AC-Proxy | MAB-Proxy | C2 | CGA-Bench |
|---|---:|---:|---:|---:|---:|---:|
| deepseek_r1_7b | 2,118 | 66.4% | 64.6% | 24.6% | 7.0% | 33.6% |
| qwen4b | 2,118 | 58.8% | 79.3% | 66.2% | 25.4% | 41.2% |
| **llama4scout** | **2,118** | **57.6%** | **76.8%** | **62.5%** | **26.2%** | **42.4%** |
| oss120b | 2,118 | 56.7% | 85.0% | 49.4% | 35.5% | 43.3% |
| nemotron30b | 2,118 | 55.4% | 62.6% | 52.2% | 18.2% | 44.6% |
| qwen35b | 2,118 | 55.1% | 86.3% | 52.1% | 36.4% | 44.9% |
| qwen27b | 2,118 | 52.3% | 78.7% | 57.3% | 30.4% | 47.7% |
| qwen397b | 2,118 | 49.5% | 84.0% | 54.2% | 39.6% | 50.5% |
| gemma31b | 2,118 | 47.1% | 74.7% | 55.6% | 31.7% | 52.9% |

**Llama-4-Scout positioning:** v4_hard rate 57.6% sits between qwen4b
(58.8%) and oss120b (56.7%). On CGA-Bench it scores 42.4% — below
gemma31b's 52.9% but above oss120b's 43.3%. Profile is most similar to
qwen4b: high AC-Proxy pass rate, high MAB-Proxy, moderate C2, modest
CGA-Bench.

### Evaluator-level totals

| Evaluator | N_pass | Pass rate | Mis-cert |
|---|---:|---:|---:|
| DxEM | 19,062 | 100.0% | 55.4% (= base v4_hard rate) |
| AC-Proxy | 14,653 | 76.9% | **60.9%** |
| MAB-Proxy | 10,043 | 52.7% | **65.1%** |
| C2 (≥0.7) | 5,304 | 27.8% | 42.7% |
| ACov (≥0.5) | 14,653 | 76.9% | 60.9% (= AC-Proxy by construction) |
| CGA-Bench | 8,495 | 44.6% | **0.0%** (definitional) |

### Verdict-flip prevalence

| Metric | 8-model v6 | 9-model v6 | Δ |
|---|---:|---:|---:|
| n_episodes | 16,944 | 19,062 | +2,118 |
| Verdict-flip count | 14,480 | **16,331** | +1,851 |
| Verdict-flip rate | 85.5% | **85.7%** | +0.2pp |
| AC-Proxy FA | 46.4% | **46.8%** | +0.4pp |
| MAB-Proxy FA | 32.9% | **34.3%** | +1.4pp |
| C2 FA | 11.8% | **11.9%** | +0.1pp |
| All-oblivious FA | 11.0% | **11.1%** | +0.1pp |
| CGA-Bench FA | 0.0% | **0.0%** | 0 |

**The headline story is identical and slightly strengthened:**

- Verdict-flip rate ticks up to 85.7% — Llama-4-Scout's verdicts
  contribute to inter-evaluator disagreement at roughly the
  population mean.
- AC-Proxy / MAB-Proxy / C2 false-accept rates all stable to
  within 1.4pp of their 8-model values.
- CGA-Bench FA rate stays exactly 0.0% — adding a new model does
  not introduce any new mis-certifications under the structural
  evaluator.

---

## 3. Re-run experiments (refreshed against 9-model matrix)

```
exp_e1_verdict_flip          ✅ 19,062 ep, FA + flip rates updated
exp_e2_bsr                   ✅ BSR by constraint type recomputed
exp_e3_instrumentation_ablation ✅ ablation modes re-tabulated
exp_e4_operating_point       ✅ matched-PR Fleiss κ at 30/40/50%
exp_e5_evaluator_expansion   ✅ 9-evaluator clustering refreshed
exp_e_difficulty_equivalence ✅ structural difficulty re-fit
exp_orthogonal_perturbation  ✅ severity scaling re-checked
extract_auto_numbers         ✅ all macros re-extracted to denominator 19,062
auto_numbers_v6.tex          ✅ refreshed (1,139 macros total)
```

All seven downstream experiments completed cleanly without modification.
The matrix's larger denominator only changes the percentage formatting
in the macros; the structural conclusions — verdict-flip prevalence,
inter-evaluator disagreement, BSR ordering — are unchanged.

---

## 4. Updated full commit chain

```
4c04543c — Phase B infrastructure
93b072a0 — v6 pipeline regen (10/12 steps)
338b22e5 — verdict matrix v6 (8 models) + e1-e5 + analysis report
60beb969 — Step 11 (gemma-4-31b judge) + 145 fleet shutdown
3dcee41d — critical review
2915dc36 — close all critical-review loose ends + 9 stale-file refresh
9964d20c — methodology fixture in-tree
[next]   — 9-model expansion (Llama-4-Scout addition)
```

---

## 5. Known deviations (must disclose with the 9-model row)

- **FP8 Marlin emulation on A100** — Llama-4-Scout-17B-16E was served
  with FP8 weights but A100 cap 8.0 lacks native FP8 tensor cores,
  so vLLM falls back to the Marlin "weight-only FP8" kernel. This
  may slightly degrade output quality vs. native FP8 on Hopper; the
  v5 run history (memory `reference_llama4scout_known_good_config`)
  documented the same emulation path on the same hardware.
- **No DEBUG_RAW capture** — the run did not record raw LLM responses,
  so any future re-extraction needs to re-run the full benchmark.

---

## 6. Final state

- 145 fleet: DOWN (8/8 GPUs idle)
- 144 fleet: DOWN (gpt-db only, no GPU)
- Paper subset corpus: 19,062 episodes (706 × 9 × 3) ✅
- Verdict matrix v6: 9 models, all evaluator + per-model rates fresh
- Auto-numbers macros: refreshed to 19,062 denominator
- All e1-e5 + exp_e_difficulty + orthogonal_perturbation: re-run on 9-model matrix

This expansion strictly improves the paper's claim of cross-family
robustness: 9 models across 5 vendors (Alibaba 4× Qwen + Meta + Google
+ OpenAI + DeepSeek + NVIDIA) all evaluated on identical 706-scenario
infrastructure.
