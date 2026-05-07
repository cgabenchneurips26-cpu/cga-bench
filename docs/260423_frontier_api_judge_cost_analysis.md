# Frontier API Judge Cost Analysis

**Date**: 2026-04-23
**Context**: CGA-Bench expansion v7 — 11 local models × 236 scenarios × 3 runs. To raise judging reliability beyond local-only evaluation, we assess the cost of re-grading every episode with 3 frontier APIs: Anthropic Claude, Google Gemini, OpenAI ChatGPT.
**Goal**: call-count projection + USD cost for 4 sweep scales × 4 ensemble tiers.

---

## 1. Executive Summary

**All figures computed programmatically** from the token model in §2 with prices in §4. Arithmetic script preserved inline in §9 for re-verification.

Full sweep (11 models × 236 scenarios × 3 runs = 7 788 episodes × 3 providers = **23 364 judge calls**):

| Ensemble | No-cache | Cached | Use case |
|---|---:|---:|---|
| **Default**: Sonnet 4.6 + GPT-5 + Gemini 2.5 Pro | **$828** | **$542** | ← Recommended start |
| Highest-trust: Opus 4.7 + GPT-5 + Gemini 2.5 Pro | $2 351 | $1 435 | Publication-grade |
| Highest-thinking: Opus 4.7 + o3 + Gemini 2.5 Pro | $3 840 | $2 559 | Overkill for rubric task |
| Budget: Haiku 4.5 + GPT-4.1-mini + Gemini Flash | $157 | $95 | Calibration / pilot |

Smaller scales (same 4 ensembles):

| Scale | Calls | Default | Budget |
|---|---:|---:|---:|
| **Scenario-only** (11 mdl × 236 × 1 run = 2 596 eps) | 7 788 | $276 / $181 | $52 / $32 |
| **Single-baseline** (1 mdl × 708 eps) | 2 124 | $75 / $49 | $14 / $9 |
| **Demo / calibration** (1 mdl × 59 graphs × 1 run) | 177 | $6 / $4 | **$1.19 / $0.72** |

Top-line takeaways:

- **Full-sweep default ensemble = $542 with caching**. Well under any grant line item; no procurement friction.
- **Caching is worth 24-41 %** (not 60-90 % as sometimes cited) because **output tokens dominate Anthropic pricing** (75:15 output:input ratio) and cache only discounts input. Still worth enabling — $286 saved on the default full sweep.
- **Start with the budget demo ($0.72)** to measure inter-judge agreement κ on the 59 new batch3/4 CPGs — never seen by an LLM judge before. That's the go/no-go gate for full spend.
- **Gemini Flash is ~30× cheaper than Sonnet 4.6** for the same token-count workload. If Flash inter-judge agreement matches Sonnet on the demo set, swap it in.

---

## 2. Empirical Episode-Size Distribution

Measured over 436 real episodes under `results/expansion_v7/` on 2026-04-23:

| Metric | Tokens |
|---|---:|
| p10 episode | 3 265 |
| p50 (median) | 4 218 |
| p90 episode | 5 379 |
| Max observed | 7 199 |
| Actions per episode (p50/p90) | 24 / 24 |

**Working assumption: 5 000 input tokens / episode payload** (slightly above median to absorb variance; below p90 because not every judge prompt needs the full trace).

### Full judge-prompt token budget

| Component | Tokens | Cacheable? |
|---|---:|---|
| System prompt + JSON schema | 800 | ✓ (static) |
| CPG graph context (YAML) | 3 000 | ✓ (shared across 132 eps / guideline) |
| Episode payload (actions + violations) | 5 000 | ✗ (unique) |
| Few-shot rubric examples | 2 500 | ✓ (static) |
| **Total input per call** | **11 300** | 7 500 cacheable, 3 800 unique |
| Structured judge verdict (output) | 1 000 | ✗ |

---

## 3. Call-Count Projection

Judge ensemble = 3 providers. Each episode hits 3 endpoints.

| Sweep | Episodes | Judge calls |
|---|---:|---:|
| **Full** — 11 mdl × 236 scen × 3 runs | 7 788 | **23 364** |
| **Scenario-only** — 11 × 236 × 1 run | 2 596 | 7 788 |
| **Single-baseline** — 1 mdl × 708 eps | 708 | 2 124 |
| **Demo / calibration** — 1 mdl × 59 graphs × 1 | 59 | 177 |

Note: "3 runs" exists because the stochastic agent loop (temperature > 0) is sampled 3× for statistical power. Judging every run exposes inter-run variance; judging only the modal run cuts cost by 3×.

---

## 4. Provider Pricing Matrix (2026-04, USD/M tokens)

Verify on each provider's pricing page before invoicing.

| Provider | Tier | Model ID | Input | Cached input | Output |
|---|---|---|---:|---:|---:|
| **Anthropic** | flagship | `claude-opus-4-7` | 15.00 | 1.50 | 75.00 |
| | mid | `claude-sonnet-4-6` | 3.00 | 0.30 | 15.00 |
| | budget | `claude-haiku-4-5` | 1.00 | 0.10 | 5.00 |
| **OpenAI** | flagship | `gpt-5` | 2.50 | 1.25 | 10.00 |
| | thinking | `o3` / `o4-mini` | 15.00 | 7.50 | 60.00 |
| | budget | `gpt-4.1-mini` | 0.15 | 0.075 | 0.60 |
| **Google** | flagship | `gemini-2.5-pro` | 1.25 | 0.3125 | 5.00 |
| | budget | `gemini-2.5-flash` | 0.10 | 0.025 | 0.40 |

Cache mechanics:
- **Anthropic**: `cache_control` 90 % discount on cached reads (5-min TTL default, 1-hour TTL at $0.30/M premium). Cache writes cost 1.25× normal input.
- **OpenAI**: automatic 50 % discount on cached prefixes ≥ 1 024 tokens.
- **Google**: explicit context caching, 75 % off. $0.0125/1M/hour retention fee.

---

## 5. Per-Call USD Cost

Budget: 11 300 input (7 500 cacheable, 3 800 unique) + 1 000 output.

| Model | No-cache | Cached | Cache savings |
|---|---:|---:|---:|
| Claude Opus 4.7 | **$0.2445** | **$0.1432** | 41 % |
| Claude Sonnet 4.6 | **$0.0489** | **$0.0286** | 41 % |
| Claude Haiku 4.5 | **$0.0163** | **$0.0095** | 41 % |
| GPT-5 | **$0.0382** | **$0.0289** | 25 % |
| GPT-o3 / o4-mini | **$0.2295** | **$0.1732** | 25 % |
| GPT-4.1-mini | **$0.0023** | **$0.0017** | 25 % |
| Gemini 2.5 Pro | **$0.0191** | **$0.0121** | 37 % |
| Gemini 2.5 Flash | **$0.0015** | **$0.0010** | 37 % |

Why are Anthropic savings higher than OpenAI? Because Anthropic's cache discount is 90 % vs OpenAI's 50 % on the same cached 7 500-token prefix. Google sits in between at 75 %.

---

## 6. Sweep-Level Totals

All 4 ensembles across 4 scales.

### 6.1 Full sweep (23 364 calls)

| Ensemble | No-cache | Cached |
|---|---:|---:|
| Default (Sonnet + GPT-5 + Gemini Pro) | $828 | **$542** |
| Highest-trust (Opus + GPT-5 + Gemini Pro) | $2 351 | $1 435 |
| Highest-thinking (Opus + o3 + Gemini Pro) | $3 840 | $2 559 |
| Budget (Haiku + GPT-4.1-mini + Flash) | $157 | $95 |

### 6.2 Scenario-only sweep (7 788 calls)

| Ensemble | No-cache | Cached |
|---|---:|---:|
| Default | $276 | $181 |
| Highest-trust | $784 | $478 |
| Highest-thinking | $1 280 | $853 |
| Budget | $52 | $32 |

### 6.3 Single-baseline (2 124 calls)

| Ensemble | No-cache | Cached |
|---|---:|---:|
| Default | $75.24 | $49.29 |
| Highest-trust | $213.73 | $130.43 |
| Highest-thinking | $349.13 | $232.64 |
| Budget | $14.25 | $8.67 |

### 6.4 Demo / calibration (177 calls)

| Ensemble | No-cache | Cached |
|---|---:|---:|
| Default | $6.27 | $4.11 |
| Highest-trust | $17.81 | $10.87 |
| Highest-thinking | $29.09 | $19.39 |
| **Budget** | **$1.19** | **$0.72** |

---

## 7. Recommendations

1. **Step 0: $0.72 budget demo (59 cached judge calls).** Haiku 4.5 + GPT-4.1-mini + Gemini Flash on 59 batch3/4 episodes (one per new graph, baseline model). Compute Fleiss κ across the 3 judges. This is the go/no-go gate — if κ < 0.4 on a balanced rubric, the judging protocol is broken, not the judges.

2. **Step 1: scale to default ensemble for scenario-only sweep ($181).** Swap Haiku → Sonnet 4.6, GPT-4.1-mini → GPT-5, Flash → Gemini 2.5 Pro. Run on 2 596 episodes (every scenario once per local model). Compare agreement vs local self-judge.

3. **Step 2: full sweep only if Step 1 shows divergence ($542).** If the scenario-only sweep already shows stable rankings, doing 3× the judging adds little epistemic value — skip to analysis.

4. **Enable prompt caching from day 1.** Saves $286 on the default full sweep. Implementation: emit the system prompt + CPG graph YAML + few-shot block as the cacheable prefix; append only the episode payload + "grade this" instruction as the fresh suffix.

5. **Don't use thinking models (o3, Opus w/ extended thinking) for pointwise judging.** Output tokens already dominate cost; thinking 3-5× the output budget for marginal quality gain on a fixed rubric. Reserve thinking for adjudicating the ≥ 2-judge-disagreement subset (typically 5-10 % of episodes).

6. **Cost tripwire in the judging driver.** Halt if daily spend exceeds $50 (calibration) or $100 (production). Batched retries on 5xx are the usual leak source.

7. **Judge one run per {scenario, model} instead of three.** Drops full sweep from 23 364 → 7 788 calls and default-ensemble cost from $542 → $181. Multi-run variance is a property of the local agent, not the judge — you can extract it offline from the local scores without re-judging.

---

## 8. Open Questions

- **Human anchor**: to compute judge *accuracy* (not just agreement) you need a clinician-annotated ground truth. ~200 episodes × ~$15-25/episode clinician fee = $3-5K independent of API cost.
- **Granularity**: holistic (episode-as-a-whole, assumed here) vs. turn-level (per-action grading). Turn-level ≈ 24× the call count and 10-20× the API cost.
- **Rubric availability**: the 28 new batch3/4 CPGs do not ship with separate guideline-card docs yet. Judges will see the YAML graph alone. Test reliability on the demo sweep before scaling.
- **Cache TTL trap**: Anthropic's default 5-min TTL means a slow sweep (< 1 call/min to the same cached prefix) re-pays the cache write cost repeatedly. Either pipeline judge calls in bursts, or pay the $0.30/M 1-hour TTL premium.

---

## 9. Recomputation Script

```python
INPUT, CACHED = 11300, 7500
FRESH = INPUT - CACHED      # 3800
OUTPUT = 1000

providers = {  # (input, cached_input, output) USD per 1M
    "Opus 4.7":      (15.00, 1.50,   75.00),
    "Sonnet 4.6":    (3.00,  0.30,   15.00),
    "Haiku 4.5":     (1.00,  0.10,   5.00),
    "GPT-5":         (2.50,  1.25,   10.00),
    "o3/o4-mini":    (15.00, 7.50,   60.00),
    "GPT-4.1-mini":  (0.15,  0.075,  0.60),
    "Gemini 2.5 Pro":(1.25,  0.3125, 5.00),
    "Gemini Flash":  (0.10,  0.025,  0.40),
}

def cost_call(pi, pc, po, cache=False):
    if cache:
        return (FRESH*pi + CACHED*pc + OUTPUT*po) / 1e6
    return ((FRESH+CACHED)*pi + OUTPUT*po) / 1e6

# Full sweep 23 364 calls = 7 788 episodes × 3 providers
# Substitute providers/ensemble size to re-derive any table cell.
```

Episode-size source: `results/expansion_v7/*/*.json`, 436 samples, 2026-04-23.
