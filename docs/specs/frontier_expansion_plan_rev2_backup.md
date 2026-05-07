# Frontier API v6 Expansion — Implementation Plan (rev2)

## Context

CGA-Bench v6 (branch `eval_science`, 19,062 episodes × 9 open-weight models 4B–397B) faces NeurIPS reviewer Attack G1: *"open-weight only, can't generalize to deployed clinical AI (Claude/GPT/Gemini)."* The first-pass strategy doc (`docs/specs/docs_frontier_api_strategy.md`) covered only 2 mid-tier frontier models on a 60-episode subset, which user judged too narrow.

**User's two-axis thesis (sharper than strategy doc):**

1. **Cross-vendor frontier ceiling** — run the strongest available frontier APIs from 3 vendors (Claude Opus 4.7, GPT-5.5-pro, Gemini 3 Pro) to test whether v6's ranking-instability finding (75% pairwise reversal across evaluators) transfers to the actual deployment-tier ceiling.
2. **Within-vendor tier robustness** — add Claude Sonnet 4.6 alongside Opus 4.7. Sonnet vs Opus is a known meaningful capability gap. Paper's main claim — *evaluator choice dominates model identity in determining safety verdicts* — should hold even across this within-vendor performance delta. If yes, the claim is robust to (a) vendor switch, (b) tier switch within a vendor.

**Strategy:** every enhancement gate is run on the **full 706-scenario W8 corpus**, not a 60-ep subset. User instinct correct — full corpus gives ±3.7pp Wilson CI vs. ±13pp at N=60, and unlocks proper per-domain robustness (claim must hold per-CPG, not just aggregate). Cost is amortized across stages with explicit user gates.

**API connectivity verified 2026-04-28** (curl HTTP 200 all three vendors, target models accessible).

## Scope (Approved)

| Axis | Model | API ID | Role | Stage cost |
|---|---|---|---|---|
| Anthropic mid (within-vendor pair partner) | Claude Sonnet 4.6 | `claude-sonnet-4-6` | **S1 pilot** + within-vendor delta | ~$88 |
| Anthropic ceiling | Claude Opus 4.7 | `claude-opus-4-7` | **S2** within-vendor pair completion | ~$353 |
| OpenAI ceiling | GPT-5.5-pro | `gpt-5.5-pro-2026-04-23` | **S3** 2nd-vendor ceiling | ~$159 |
| Google ceiling | Gemini 3 Pro | `gemini-3-pro-preview` | **S4** 3rd-vendor ceiling | ~$53 |

- **Episodes**: 706 manual scenarios (full W8 corpus excluding DeepSeek-R1-7B per `audit/shims/_verdict_cache.py:21`).
- **Runs**: 1 per (model, episode). Disclosure: temp=0.1 frontier models are near-deterministic (OpenAI/Gemini support `seed`); Anthropic ignores seed → noted as known limitation.
- **Total**: 706 × 4 × 1 = **2,824 frontier API calls, ~$653 total**.
- **Budget cap raise**: env-file `FRONTIER_RUN_BUDGET_USD` raised per-stage (S1 $100 → S2 $500 → S3 $700 → S4 $750), each requiring user gate.

## Six Enhancements (all in, all post-hoc, all $0)

These run on whatever data is available — partial enhancement after S1, full after S4. They quantify the headline claim *"evaluator choice > model identity for verdict variance"* beyond simple ranking comparison.

| # | Enhancement | Strengthens |
|---|---|---|
| **A** | **2-way ANOVA variance decomposition** — total verdict variance = σ²_eval + σ²_model + σ²_interact + σ²_resid. Headline: σ²_eval / σ²_model ratio. | Aggregate quantification |
| **B** | **Bootstrap 95% CI on σ²_eval / σ²_model** (1000 iter) | Uncertainty quantification |
| **C** | **Per-CPG-domain replication** — A+B run on each of the 25 CPG domains independently. Report % of domains where σ²_eval > σ²_model. | Domain-level robustness |
| **D** | **Adversarial worst-case selection** — pick the model pair with maximal score gap (e.g., qwen4b vs qwen397b among open-weight, or Sonnet vs Opus within frontier) — does evaluator variance still dominate even there? | Stress test against "easy case" attack |
| **E** | **Pre-registered hypothesis** (declared in this plan, before any S1 data) — success criterion: σ²_eval / σ²_model ≥ 2.0 with 95% CI excluding 1.0; per-domain (C) ≥ 80% of 25 domains; Spearman ρ ≥ 0.5 between augmented and baseline 9-model ranking. | Anti-p-hacking |
| **F** | **Falsification clause** (declared in plan, written into paper §6) — claim is retracted if any single evaluator pair shows Spearman ρ ≥ 0.95 across all 13 models, OR if σ²_eval / σ²_model 95% CI includes 1.0 in aggregate. | Falsifiable benchmark trademark |

## Implementation Phases

### Phase A — Infrastructure (Day 0, 4–6h)

**A.1 LLMBackend Gemini extension** — `agent_runner/llm_provider.py`
- Existing enum (line 231–237): OPENAI/ANTHROPIC/VLLM/MOCK. Add `GEMINI = "gemini"` + `GeminiProvider(BaseLLMProvider)` class (~80 lines, mirror `AnthropicProvider:453–521`).
- Reuse: `repair_json:27`, `safe_json_parse`, `BaseLLMProvider` token-tracking dict, retry/timeout pattern.
- Env: `GEMINI_API_KEY` (already in `secrets/frontier_api_keys.env` line 27).
- Endpoint: `https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent` (verified 4-28 ping).
- No regression on existing OPENAI/ANTHROPIC/VLLM paths.

**A.2 Secret loader helper** — `agent_runner/frontier_env_loader.py` (NEW, ~30 lines)
- Reads `secrets/frontier_api_keys.env`, validates `(stat.st_mode & 0o077) == 0`, exports vars to `os.environ` if not already present.
- Reusable from all wrapper scripts.

**A.3 Four frontier model configs** in `configs/agents/`:
- `rag_claude_sonnet46.yaml` (anthropic, claude-sonnet-4-6) — **S1 pilot**
- `rag_claude_opus47.yaml` (anthropic, claude-opus-4-7) — S2
- `rag_gpt55pro.yaml` (openai, gpt-5.5-pro-2026-04-23, OpenAI-Organization header) — S3
- `rag_gemini3pro.yaml` (gemini, gemini-3-pro-preview) — S4
- All inherit from `configs/agents/rag_gpt4o.yaml` template: ReAct + BM25 (top-k=5) + 100K token / 50 tool-call budget — matches open-weight 9-model regime exactly for budget-matched comparison.

### Phase B — 706-Scenario Manifest (Day 0, 30min)

**B.1 Frozen 706-scenario manifest** — `scripts/experiments/extract_w8_706_manifest.py` (NEW, ~80 lines, one-shot)
- Input: `configs/scenarios/*_scenarios.yaml` (706 manual scenarios) + `audit/shims/_verdict_cache.py` W8 filter.
- Output: `evidence_pack/frontier/w8_706_manifest.json` — list of 706 (scenario_id, cpg_domain, primary_violation_type, fa_quartile) records, deterministic.
- Acceptance: 25 distinct CPG domains, sum of per-domain counts = 706, hash-frozen.

### Phase C — Staged Frontier Run (gated)

#### Stage S1 — Sonnet 4.6 pilot ($88, ~2h wall-clock)

```bash
export FRONTIER_RUN_BUDGET_USD=100
PYTHONPATH=. python scripts/experiments/frontier_spot_check.py \
    --models claude-sonnet-4-6 \
    --manifest evidence_pack/frontier/w8_706_manifest.json \
    --runs 1 --seed 42 \
    --output evidence_pack/frontier/s1_sonnet.json
```

**Gate S1 verification (user reviews before approving S2):**
1. Schema compatibility: `verdict_matrix` re-scoring of `s1_sonnet.json` produces same column set as `verdict_matrix_v6_typed.json`.
2. Token usage: average tokens/episode within 50%–200% of $0.125 projection ($88 ± $44).
3. Output quality: ≥95% episodes have valid action sequences (no JSON parse failures, no truncated tool-call loops).
4. Sanity-check verdict pattern: Sonnet TCC pass rate falls within open-weight model envelope (i.e., not catastrophically out of distribution suggesting infrastructure bug).
5. **Partial enhancements**: run A+B+E on 10-model dataset (9 baseline + Sonnet) — does σ²_eval / σ²_model ≥ 2.0 hold even with single frontier model? Early signal of claim direction.

→ User decision: proceed to S2, or pause/abort.

#### Stage S2 — Opus 4.7 (within-vendor pair, $353, ~6h wall-clock)

```bash
export FRONTIER_RUN_BUDGET_USD=500
PYTHONPATH=. python scripts/experiments/frontier_spot_check.py \
    --models claude-opus-4-7 \
    --manifest evidence_pack/frontier/w8_706_manifest.json \
    --runs 1 --seed 42 \
    --output evidence_pack/frontier/s2_opus.json
```

**Gate S2 verification (user reviews before approving S3):**
1. Within-vendor delta computation:
   - Sonnet vs Opus per-evaluator score gap (6 evaluators × 706 ep)
   - Verdict disagreement rate (% episodes where Opus and Sonnet disagree on TCC pass/fail)
2. **Headline within-vendor test (claim's main load-bearing number)**:
   - σ²_eval (across 6 evaluators, holding model fixed) vs σ²_within_vendor (Opus vs Sonnet, holding evaluator fixed)
   - **Pre-registered (E) success**: σ²_eval / σ²_within_vendor ≥ 2.0 with bootstrap 95% CI excluding 1.0
   - If yes, paper claim "evaluator choice dominates within-vendor tier shift" empirically grounded.
3. Cost actual vs projection.

→ User decision: proceed to S3, or pause/abort.

#### Stage S3 — GPT-5.5-pro (2nd vendor, $159, ~3h wall-clock)

```bash
export FRONTIER_RUN_BUDGET_USD=700
PYTHONPATH=. python scripts/experiments/frontier_spot_check.py \
    --models gpt-5.5-pro-2026-04-23 \
    --manifest evidence_pack/frontier/w8_706_manifest.json \
    --runs 1 --seed 42 \
    --output evidence_pack/frontier/s3_gpt55pro.json
```

**Gate S3 verification:**
1. Cross-vendor consistency: GPT-5.5-pro frontier rank position vs Opus 4.7 frontier rank position. If both land in similar TCC-rank band among 9 baseline, "frontier-tier" signal coherent.
2. 11-model (9 baseline + Sonnet + Opus + GPT-5.5-pro) augmented analysis:
   - Spearman ρ vs 9-model baseline ordering
   - Pairwise reversal rate vs 75% baseline (now C(11,2)=55 pairs)
   - σ²_eval / σ²_model with 11 models — narrowing CI

→ User decision: proceed to S4, or call it done with 11 models.

#### Stage S4 — Gemini 3 Pro (3rd vendor, $53, ~2h wall-clock)

```bash
export FRONTIER_RUN_BUDGET_USD=750
PYTHONPATH=. python scripts/experiments/frontier_spot_check.py \
    --models gemini-3-pro-preview \
    --manifest evidence_pack/frontier/w8_706_manifest.json \
    --runs 1 --seed 42 \
    --output evidence_pack/frontier/s4_gemini3pro.json
```

→ Final 13-model (9 baseline + 4 frontier) dataset. Proceed to Phase D.

### Phase D — Final Analysis (Day 3, 4h)

**D.1 6-evaluator post-hoc scoring** — concatenate `s1_sonnet.json`...`s4_gemini3pro.json` → run existing `scripts/experiments/run_six_evaluator_scoring.py` → `evidence_pack/frontier/verdict_matrix_frontier.json` (706 ep × 4 frontier × 6 evaluators).

**D.2 Cross-vendor + within-vendor + 6-enhancement analysis** — `scripts/experiments/frontier_full_analysis.py` (NEW, ~400 lines)

Inputs:
- `evidence_pack/frontier/verdict_matrix_frontier.json` (4 frontier × 706 × 6 eval)
- `evidence_pack/analysis/verdict_matrix_v6_typed.json` (9 open-weight, subset to same 706 W8 IDs via `w8_706_manifest.json`)

Computes (all 6 enhancements, mapped to existing utilities):
- **Ranking metrics** (reuse `scripts/experiments/exp_d_disagreement_quantification.py:263–352` `rank_reversal_analysis()`):
  - 13-model frontier-augmented Spearman ρ vs 9-model baseline ordering
  - Pairwise reversal rate (78 pairs)
  - Per-evaluator rank insertion of 4 frontier models
- **Enhancement A (ANOVA)**: scipy.stats.f_oneway on (verdict ~ evaluator + model + evaluator:model). Report σ² components.
- **Enhancement B (Bootstrap CI)**: 1000-iter bootstrap on (model, episode) pairs, recompute σ²_eval / σ²_model each iter, report 2.5/50/97.5 percentile.
- **Enhancement C (per-domain)**: A+B repeated on each of 25 CPG domains (reuse domain map from `exp_d_disagreement_quantification.py:81–111`). Report % domains where σ²_eval > σ²_model + bootstrap CI excludes 1.0.
- **Enhancement D (worst-case)**: identify max-score-gap model pair globally; recompute σ²_eval / σ²_within_pair on this adversarial subset.
- **Enhancement E (pre-reg)**: emit pass/fail vs declared thresholds.
- **Enhancement F (falsification)**: check Spearman ρ < 0.95 for all 15 evaluator pairs across 13 models.
- **Within-vendor headline**: Opus vs Sonnet per-evaluator delta + σ²_eval / σ²_within_vendor + bootstrap CI.
- **Pillar 3 ratio** (reuse pattern from `phase1j_pillar3_3variants.py`): per-evaluator FA gap, frontier vs open-weight Δ.

Outputs:
- `evidence_pack/frontier/full_analysis.json`
- `paper/frontier_macros.tex` (auto-generated, 12 macros)

### Phase E — Paper Integration (Day 4, 3h)

**E.1 Macros** (`paper/frontier_macros.tex`, auto-emitted by D.2):

| Macro | Source | Purpose |
|---|---|---|
| `\frontierNEpisodes` | constant 706 | corpus size |
| `\frontierVendors` | 3 | vendor diversity |
| `\frontierRankBetween` | rank tuple | where 4 frontier slot into 9-model TCC ranking |
| `\frontierRankingPreservation` | Spearman ρ | open-weight ordering preservation |
| `\frontierFlipRate` | 13-model pairwise reversal % | 75% baseline replication |
| `\frontierEvalVarRatio` | σ²_eval / σ²_model | **A — headline** |
| `\frontierEvalVarRatioCI` | bootstrap 95% CI | **B** |
| `\frontierPerDomainRobustness` | % of 25 domains where eval > model variance | **C** |
| `\frontierAdversarialEvalDominates` | yes/no on worst-case pair | **D** |
| `\frontierPreRegPass` | E success criteria pass/fail | **E** |
| `\frontierFalsificationClear` | F clause not triggered yes/no | **F** |
| `\frontierWithinVendorEvalRatio` | σ²_eval / σ²_within_vendor (Opus-Sonnet) | within-vendor headline |
| `\frontierWithinVendorClaimHolds` | yes/no | within-vendor verdict |

**E.2 Paper rewrite** — `paper/main_final_v18.tex`
- §6 Limitations (current "frontier APIs ... deferred" line ~422): replace with frontier-spot-check sentence citing all 13 macros.
- §4.5 Robustness Summary: add 3 sentences (cross-vendor, within-vendor, per-domain).
- New appendix `app:frontier_spotcheck`: methodology + per-evaluator rank table (13 rows × 6 cols) + Sonnet-vs-Opus within-vendor sub-table + ANOVA decomposition table + per-domain heatmap + cost disclosure + Case A/B/C honest-failure framing + falsification clause F as italicized standalone box.
- `paper/auto_numbers.tex`: add `\input{frontier_macros}` near top.
- Pre-registration document: write `evidence_pack/frontier/pre_registration.md` *before* S1 runs, declaring E thresholds. Cite from §6.

**E.3 Bibliography** — `paper/refs.bib`
- Add `claude2026opus47`, `claude2026sonnet46`, `gpt55pro2026`, `gemini3pro2026`.

## Critical Files

| File | Action | Stage |
|---|---|---|
| `agent_runner/llm_provider.py` | EDIT | Phase A.1 — add Gemini |
| `agent_runner/frontier_env_loader.py` | NEW | Phase A.2 |
| `configs/agents/rag_claude_sonnet46.yaml` | NEW | Phase A.3 / S1 |
| `configs/agents/rag_claude_opus47.yaml` | NEW | Phase A.3 / S2 |
| `configs/agents/rag_gpt55pro.yaml` | NEW | Phase A.3 / S3 |
| `configs/agents/rag_gemini3pro.yaml` | NEW | Phase A.3 / S4 |
| `scripts/experiments/extract_w8_706_manifest.py` | NEW | Phase B |
| `evidence_pack/frontier/w8_706_manifest.json` | NEW (output) | Phase B |
| `scripts/experiments/frontier_spot_check.py` | NEW | Phase C |
| `evidence_pack/frontier/pre_registration.md` | NEW | Pre-S1 |
| `evidence_pack/frontier/s1_sonnet.json` | NEW (output) | S1 |
| `evidence_pack/frontier/s2_opus.json` | NEW (output) | S2 |
| `evidence_pack/frontier/s3_gpt55pro.json` | NEW (output) | S3 |
| `evidence_pack/frontier/s4_gemini3pro.json` | NEW (output) | S4 |
| `scripts/experiments/frontier_full_analysis.py` | NEW | Phase D |
| `evidence_pack/frontier/verdict_matrix_frontier.json` | NEW (output) | Phase D |
| `evidence_pack/frontier/full_analysis.json` | NEW (output) | Phase D |
| `paper/frontier_macros.tex` | NEW (output) | Phase D |
| `paper/main_final_v18.tex` | EDIT | Phase E |
| `paper/auto_numbers.tex` | EDIT | Phase E |
| `paper/refs.bib` | EDIT | Phase E |

## Reused Existing Assets (no changes)

- `agent_runner/llm_provider.py:311–521` — OPENAI + ANTHROPIC providers
- `eval_harness/runner.py:71–269` — budget enforcement
- `audit/shims/_verdict_cache.py` — W8 filter (DeepSeek-R1-7B exclusion at line 21)
- `scripts/experiments/run_frontier_models.py` — base for `frontier_spot_check.py`
- `scripts/experiments/integrate_frontier_results.py` — base for full analysis
- `scripts/experiments/run_six_evaluator_scoring.py` — post-hoc 6-eval pipeline
- `scripts/experiments/exp_d_disagreement_quantification.py:263–352` — `rank_reversal_analysis()`
- `scripts/experiments/extract_auto_numbers.py` — JSON→TeX macro emitter
- `configs/agents/rag_gpt4o.yaml` + `rag_claude35.yaml` — config templates
- `assessor_core/violations.py` + `harm_scorer.py` + `cpg_engine/` — same scoring infra
- `evidence_pack/analysis/verdict_matrix_v6_typed.json` (9-model baseline)
- `cpg_model/graphs/` (25 CPG YAML files for per-domain analysis)
- `secrets/frontier_api_keys.env` (3 keys filled, gitignored, chmod 600)

## Verification (End-to-End)

```bash
# Phase A — infrastructure smoke
python3 -c "
from agent_runner.frontier_env_loader import load_frontier_env
from agent_runner.llm_provider import LLMBackend, GeminiProvider
e = load_frontier_env()
assert all(e.get(k,'') for k in ['OPENAI_API_KEY','ANTHROPIC_API_KEY','GEMINI_API_KEY'])
assert LLMBackend.GEMINI.value == 'gemini'
print('Phase A OK')
"

# Phase B — manifest
PYTHONPATH=. python scripts/experiments/extract_w8_706_manifest.py
python3 -c "
import json
m = json.load(open('evidence_pack/frontier/w8_706_manifest.json'))
assert len(m['scenarios']) == 706
assert len({s['cpg_domain'] for s in m['scenarios']}) == 25
print('Phase B OK')
"

# Pre-S1 — pre-registration written
test -f evidence_pack/frontier/pre_registration.md
grep -q 'σ²_eval / σ²_model ≥ 2.0' evidence_pack/frontier/pre_registration.md

# S1 — Sonnet pilot (USER GATE — verify before S2)
export FRONTIER_RUN_BUDGET_USD=100
PYTHONPATH=. python scripts/experiments/frontier_spot_check.py \
    --models claude-sonnet-4-6 \
    --manifest evidence_pack/frontier/w8_706_manifest.json \
    --runs 1 --output evidence_pack/frontier/s1_sonnet.json

# S1 gate checks
PYTHONPATH=. python scripts/experiments/run_six_evaluator_scoring.py \
    --episodes evidence_pack/frontier/s1_sonnet.json \
    --output /tmp/s1_verdicts.json
python3 -c "
import json
v = json.load(open('/tmp/s1_verdicts.json'))
b = json.load(open('evidence_pack/analysis/verdict_matrix_v6_typed.json'))
assert set(v['metadata']['evaluator_thresholds']) == set(b['metadata']['evaluator_thresholds']), 'evaluator set mismatch'
assert v['metadata']['n_episodes'] >= 670, 'too many parse failures'  # ≥95%
print('S1 schema + parse-rate OK')
"
# → user reviews S1 results manually, decides to proceed

# S2/S3/S4 each repeat with raised budget cap, output to s{N}_{model}.json

# Phase D — final analysis
PYTHONPATH=. python scripts/experiments/frontier_full_analysis.py \
    --inputs evidence_pack/frontier/s{1,2,3,4}_*.json \
    --baseline evidence_pack/analysis/verdict_matrix_v6_typed.json \
    --manifest evidence_pack/frontier/w8_706_manifest.json \
    --output evidence_pack/frontier/full_analysis.json \
    --macros paper/frontier_macros.tex \
    --enhancements all

# Pre-reg verdict
python3 -c "
import json
a = json.load(open('evidence_pack/frontier/full_analysis.json'))
print('Enhancement E (pre-reg) verdict:', a['enhancement_E']['claim_supported'])
print('  σ²_eval / σ²_model:', a['enhancement_A']['ratio'])
print('  bootstrap 95% CI:', a['enhancement_B']['ci'])
print('  per-domain (% pass):', a['enhancement_C']['domains_passing_pct'])
print('  adversarial:', a['enhancement_D']['claim_holds'])
print('  falsification F triggered:', a['enhancement_F']['triggered'])
print('  within-vendor (Opus-Sonnet) eval/within ratio:', a['within_vendor']['eval_within_ratio'])
"

# Tests
PYTHONPATH=. pytest tests/ -k 'frontier or llm_provider or gemini' -v

# Paper compile
cd paper && pdflatex main_final_v18.tex 2>&1 | tail -5
grep -c 'frontierEvalVarRatio\|frontierWithinVendor' main_final_v18.aux
```

## Honest-Failure Decision Tree

| Outcome at end of Phase D | §6 Limitations wording | Paper claim |
|---|---|---|
| **A**: E pre-reg passes (ratio ≥ 2.0, CI excludes 1.0), C ≥ 80% domains, F clear | "spot-checked across 3 vendors + 1 within-vendor pair on full 706-scenario corpus; evaluator-choice variance dominates model-identity variance by Xx [95% CI a–b], holds in Y% of 25 CPG domains and across the within-vendor Opus/Sonnet pair" | strong |
| **B**: E partial (ratio < 2 but CI excludes 1.0; OR C 50–80% domains) | "partial transfer; ranking instability dominates in aggregate but model identity becomes more important in specific CPG domains [list]" — nuanced disclosure | nuanced |
| **C**: E fails (CI includes 1.0) OR F triggered | "frontier-tier disagrees: evaluator choice does NOT dominate model identity at the deployment-tier ceiling; ranking-instability claim is most relevant to mid-tier open-weight models" — scope-narrowed | scope-narrowed but still publishable; honest disclosure of falsifiable failure |

All three cases reviewer-acceptable per audit-paper falsifiability norms. Skip is the only outcome that *can't* be defended.

## Out of Scope

- xAI Grok / DeepSeek paid / Mistral / aggregator backends (keys empty, not on critical path)
- Phase B 76,464-episode rerun (infeasible)
- Broader temperature sweeps (separate experiment)
- 3-run replication (1 run sufficient at 706 ep; Anthropic seed limitation disclosed)

## Timeline

- **Day 0 (4/28)** — Phase A + B (infra + manifest) + pre-registration write. 5–7h.
- **Day 1 (4/29)** — S1 Sonnet pilot ($88, ~2h wall-clock). User gate.
- **Day 1–2** — S2 Opus ($353, ~6h). User gate.
- **Day 2** — S3 GPT-5.5-pro ($159, ~3h). User gate.
- **Day 3 (4/30)** — S4 Gemini 3 Pro ($53, ~2h). Phase D analysis. 4h.
- **Day 4 (5/1)** — Phase E paper integration. 3h.
- **Day 5 (5/2)** — buffer.
- **Day 6–7 (5/3–5/5)** — camera-ready polish.
- **Day 8 (5/6)** — submission.

Total Phase A–E wall-clock: ~30h spread across 4 calendar days. Buffer 2 days. Submission deadline 5/6 ✅.

## Cumulative Cost Tracker

| Stage cumulative | Episodes | Models active | Cost added | Cost cumulative |
|---|---|---|---|---|
| S1 done | 706 | 1 (Sonnet) | $88 | **$88** |
| S2 done | 1,412 | 2 (Sonnet+Opus) | $353 | **$441** |
| S3 done | 2,118 | 3 (+GPT-5.5-pro) | $159 | **$600** |
| S4 done | 2,824 | 4 (+Gemini 3 Pro) | $53 | **$653** |

Each stage independently abortable. If S1 reveals infrastructure problem, abort with $88 spent. If S2 within-vendor result already settles claim, can stop at $441. Etc.
