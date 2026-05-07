# v8 Frontier Expansion — S1 + Track 1 Mid-Run Analysis

**Date**: 2026-04-28 ~07:50 UTC
**Branch**: `eval_science`
**Coverage**: S1 Sonnet 4.6 frontier pilot 97.5% complete; Track 1 local-model expansion 30–113% across 4 models on the v7 corpus.

---

## 1. S1 — Claude Sonnet 4.6 on v6 706 scenarios

### Run health

- **Episodes**: 688 / 706 (97.5% complete, ETA <30 min)
- **Success rate**: 100% (0 parse / call failures)
- **Cost actual**: $0.0951 / episode → projected $67 for full 706 (vs $88 plan, -24%)
- **Tokens / episode**: mean 19,808; median 18,684; max 71,188
- **Wall-clock / episode**: mean 152s; median 154s

### CGA distribution (compliance score)

- mean **0.573**, median 0.583, std 0.203
- min 0.000, max 1.000
- **pass@CGA≥0.7**: **30.8%**
- pass@CGA≥0.5: 66.1%
- mean violations/ep: 8.56; mean actions/ep: 19.8

### Where Sonnet 4.6 lands among the v6 9-model open-weight pack

Using the same `c2_score` metric on the v6 typed verdict matrix
(`evidence_pack/analysis/verdict_matrix_v6_typed.json`):

| Rank | Model | c2_score mean | [email-redacted] |
|---|---|---|---|
| 1 | Qwen3.5-35B | **0.634** | 36.4% |
| 2 | Qwen3.5-120B (oss-120b) | 0.625 | 35.5% |
| 3 | Qwen3.5-397B | 0.620 | **39.6%** |
| 4 | Qwen3.5-27B | 0.584 | 30.4% |
| **5** | **Claude Sonnet 4.6 (S1)** | **0.573** | **30.8%** |
| 6 | Gemma-4-31B | 0.572 | 31.7% |
| 7 | Qwen3-4B | 0.562 | 25.4% |
| 8 | Llama-4-Scout-17B | 0.557 | 26.2% |
| 9 | Nemotron-30B-FP8 | 0.426 | 18.2% |
| 10 | DeepSeek-R1-7B | 0.373 | 7.0% |

### Implication for paper Attack-G1 defense

Sonnet 4.6 (Anthropic frontier mid-tier) lands at **rank 5 of 10** —
beaten by four open-weight Qwen variants (35B, 120B, 397B, 27B), and
roughly tied with Gemma-4-31B. The reviewer-implicit assumption that
*"deployed frontier models will outclass open-weight"* is **not
supported** by this single-run, single-evaluator slice.

Caveat: this is one evaluator (`c2_score`) and one run. The full v8
plan runs 6 evaluators (TOM/ASC/PAF/CwT/ACov/TCC) — only after that
analysis can we say whether **σ²_eval / σ²_model ≥ 2** (the registered
H1). But early signal is consistent with the user's thesis:
*"evaluator choice dominates model identity."*

---

## 2. Track 1 — Local v7 expansion (4 models × 236 scen × 3 runs)

### Run progress (mid-run snapshot)

| Model | Episodes | Pct | CGA mean | [email-redacted] | tokens/ep |
|---|---|---|---|---|---|
| qwen4b | 799 / 708 | **113%** ⚠ | 0.465 | 21.7% | 24,729 |
| gemma31b | 692 / 708 | 97.7% | 0.520 | 14.2% | 32,339 |
| llama4scout | 518 / 708 | 73.2% | 0.432 | 18.6% | 30,069 |
| nemotron30b | 0 / 708 | 0% | — | — | (144 endpoints loading) |

### qwen4b > 100% — the dedup problem

`results/expansion_v7/qwen4b/` has **91 duplicate JSON files** above
the 708 expected. Cause: this session launched qwen4b expansion
runners in three waves (v1 16-worker, v2 8-worker after v1 was
mistakenly thought dead, v3 after a graph-restore restart). All three
waves wrote to the same output directory before the claim-file lock
caught up. Multiple timestamps for the same `(scenario_id, run_idx)`
pair coexist.

**Action required before v8 build**: dedup per-scenario per-run by
keeping the **latest timestamp**. Add a step to
`build_v8_corpus_and_run_all.sh` Step 2 that does:

```python
# group by (scenario_id, run_index), keep newest timestamp's JSON
seen = {}
for fp in model_dir.glob("*.json"):
    parts = fp.stem.split("_r")
    sid, ridx_ts = parts[0], parts[1]
    ridx, ts = ridx_ts.split("_", 1)
    key = (sid, ridx)
    if key not in seen or ts > seen[key][1]:
        seen[key] = (fp, ts)
files = [v[0] for v in seen.values()]
```

Without this, v8 metrics will double-count qwen4b on the duplicated
scenarios.

### Same models, v6 core vs v7 expansion — the corpus difficulty signal

Comparing each Track 1 model's CGA on v7 expansion to its own v6 core
baseline:

| Model | v6 core CGA | v7 expansion CGA | Δ |
|---|---|---|---|
| qwen4b | 0.562 | 0.465 | **−0.097** |
| gemma31b | 0.572 | 0.520 | **−0.052** |
| llama4scout | 0.557 | 0.432 | **−0.125** |

All three models score 5–13 pp lower on v7 expansion than on v6 core.
This confirms v7 is a **harder corpus** — the 28 newly-active CPGs
restored from `_archive_unscored_20260425/` carry trickier
trap/mild/moderate/severe scenarios than the v6 core 25 CPGs.

This is exactly what the user wanted when they said *"임상
가이드라인 늘렸다"* — the expanded corpus is more discriminating.
v8 will benefit from the broader CPG diversity.

### Token efficiency

Frontier (Sonnet) uses fewer tokens per episode than Track 1 models:

- Sonnet 4.6: 19,808 tokens/ep
- qwen4b: 24,729
- gemma31b: 32,339
- llama4scout: 30,069

Suggests Sonnet's reasoning is more concise per-step. Plays into
budget-matched comparison: under a 100K-token cap, Sonnet has more
headroom for additional ReAct steps, while gemma31b is closer to the
cap on complex scenarios.

---

## 3. Decisions surfaced by mid-run data

### S2 Opus 4.7 GO/NO-GO (planned post-S1 gate)

S1 result strongly supports proceeding to S2:

- Sonnet at rank 5 means the within-vendor pair (Sonnet vs Opus) is
  the experiment's **load-bearing** evidence: if Opus rises to the
  top while Sonnet sits mid-pack, that's huge within-vendor variance
  — and we test whether eval choice still dominates that.
- $353 cost is justified by the headline-level ROI: this gives the
  paper a quantitative within-vendor delta that is the **only** way
  to defend the claim against "frontier just dominates" attack.

**Recommendation: GO on S2 once S1 fully completes (~30 min).**

### Track 1 nemotron30b status

144 nemotron30b ×8 instances in v6 launch (PIDs 189168–189175). Model
load takes 5–10 min after the env-fix chain (vLLM 0.19 + ninja +
torchao removed). Should reach health by ~07:55 UTC.

If nemotron loads, v7 baseline 9/9 model coverage achieved. If it
fails again, v7 baseline goes 8/9 (existing 5 + qwen4b + gemma31b +
llama4scout) and v8 metadata flags nemotron as a v7-portion gap.

### qwen4b dedup mandatory

Add to v8 build Step 2 before the rest of the pipeline runs.

---

## 4. Files used and produced this analysis pass

- Source episode JSONs:
  - `evidence_pack/frontier/s1_sonnet/{scenario}_r0.json` (688 files)
  - `results/expansion_v7/{qwen4b,gemma31b,llama4scout,nemotron30b}/*.json`
- v6 reference: `evidence_pack/analysis/verdict_matrix_v6_typed.json`
- This report: `docs/260428_v8_s1_track1_analysis.md`

---

## 5. Next 1–2h timeline

- **+15 min**: S1 finishes (706/706); per-scenario dir frozen
- **+5 min**: 144 nemotron endpoints up (or final fail confirmation)
- **+30 min**: nemotron expansion_runner produces enough episodes
- **+30 min**: qwen4b + gemma31b cross 566 threshold; v8 build queue
  triggers
- **+45 min**: dedup + v6 ∪ v7 verdict matrix built
- **+90 min**: 4-script analysis pipeline (exp_d, exp_e1,
  evaluator_agreement, core_vs_expansion) on v8
- **+120 min**: paper/auto_numbers_v8.tex regenerated; ready for §6
  rewrite
