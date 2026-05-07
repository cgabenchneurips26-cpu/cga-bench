# 16. Frontier API Spot-Check 전략 — 통합 실행 보고서

> **Document scope.** 이 세션 (2026-04-24 ~ 2026-04-28) 전반에서 분산되어 논의된 frontier API 사용 전략을 단일 보고서로 통합. NeurIPS 2026 D&B 5/6 deadline 안에 실행 가능한 형태로 정리.
>
> **Source materials integrated.**
> - `docs/session_continuity_260424_260426/13_competitive_landscape_patch_for_system_ai.md` §12.3 (Attack G1) + §13.1 (E_CRIT-3 plan)
> - `docs/session_continuity_260424_260426/14_experiments_handoff_for_system_ai.md` §2.3 (E_CRIT-3 detailed)
> - `docs/session_continuity_260424_260426/15_attack_defense_and_rubric_mapping.md` Part III.3 + Part VI (pending)
> - `paper/main_final_v18.tex` §4.1 Setup, §6 Limitations (현재 frontier API "deferred" 표현 잔존)
> - `scripts/experiments/run_frontier_models.py` + `integrate_frontier_results.py` (existing P2-1 infrastructure)
>
> **Audience.** (a) 5/6 NeurIPS 2026 D&B Track 제출 직전 frontier spot-check 실행 결정 자료, (b) anonymous-user 환경에서 위임 실행 시 self-contained 가이드.

---

## Part I. Why we need this — Attack G1 분석

### I.1 Reviewer 공격 시나리오

Doc 13 §12.3에서 식별된 **Attack G1** ("Open-weight only models, no frontier API"):

> **Reviewer 입장**: *"Your 8 models all open-weight 4B-397B. Cannot generalize to deployed clinical AI agents (Claude Sonnet, GPT-4o)."*
>
> **확률**: 40-50% (높음) — NeurIPS reviewer가 흔히 던지는 외부 타당성 공격.
> **위험도**: 높음 — paper의 deployment relevance 청구를 직접 약화시킴.

핵심 논리는 다음과 같다. CGA-Bench 헤드라인 청구는 *"evaluator choice가 모델 ID보다 중요한 variance를 갖는다"* + *"75% pairwise model rankings reverse"* + *"6.6% strict consensus FA"*. reviewer 입장에서는 이 모든 청구가 9개 open-weight model (4B--397B 파라미터, Qwen/DeepSeek/Nemotron/Gemma/GPT-oss/Llama-4) 만으로 성립한다. 의료 AI 실제 배포 환경은 Claude Sonnet 4.5 / GPT-4o / Gemini 2.5 Pro 같은 frontier API에 더 가깝다. 따라서 *"open-weight pattern이 frontier에도 generalize되는가"* 가 확인되지 않으면 paper의 deployment-relevance 강도가 떨어진다.

### I.2 현재 paper에서 G1 attack 표면 (vulnerability)

`main_final_v18.tex` §6 Limitations 첫 문장:

```latex
Runs use one ReAct scaffold on \numModels{} open-weight models (4B--397B) at $T{=}0.1$;
frontier APIs and broader $T$ sweeps are deferred (App.~\ref{app:temperature_sensitivity}).
```

이 문장은 reviewer에게 직접 공격 명분을 제공한다. *"deferred"* 가 곧 *"이 paper는 frontier에 대해 모른다"* 로 읽힌다. spot-check 결과 한 줄로 *"Frontier spot check confirms the open-weight ranking instability transfers"* 를 추가할 수 있으면 G1을 차단한다.

### I.3 전략 결정 — frontier full-evaluation은 **불필요**, spot-check만 필요

**채택하지 않는 옵션 (이유):**
- Full ranking on N=706 manual scenarios × frontier 2 model × 3 runs = 4,236 frontier API calls × tool-loop. 비용 ~$2,000-5,000. 시간 1주+. ROI 낮음.
- Phase B 76,464 episodes scale의 frontier 재실행. 비현실적.

**채택하는 옵션 (이유):**
- **W8-stratified 60-episode subset** × 2 frontier models × 3 runs = 360 frontier API calls. 비용 $50-100. 시간 1 day.
- 결과: 75% pairwise reversal pattern과 Pillar 3 ratio가 frontier-tier에서도 *qualitatively* 보존되는지 확인.
- *"deferred"* 문구를 *"spot-checked, transfers"* 로 교체.

이는 **Important** priority 실험 (E_CRIT-3) 으로 분류된다 (Doc 14 §1.3). 중요하지만 paper의 *necessity*가 아닌 *sufficient* 확장. Paper의 핵심 청구 (Theorem 1 + 6.6% consensus FA + matched-pair witness) 는 frontier 결과 없이도 성립한다. Frontier spot-check은 reviewer 답변을 매끄럽게 만드는 supplementary evidence.

---

## Part II. 실행 전략 — E_CRIT-3 spec

### II.1 Scope and targets

| 항목 | 값 |
|---|---|
| Experiment ID | E_CRIT-3 |
| Targets | Attack G1 (no frontier API) |
| Priority | 🔴🔴 Critical (Doc 14 분류) |
| Time | 1 day |
| Resource | API quota $50-100 |
| Pre-condition | Anthropic + OpenAI API keys |
| Status | **NOT STARTED** (existing scripts present, no results) |

### II.2 Frontier model 선택 — 2 vendors, 2 tiers

| 모델 | Vendor | API endpoint | 선택 사유 |
|---|---|---|---|
| Claude Sonnet 4.5 (claude-sonnet-4-5) | Anthropic | `https://api.anthropic.com/v1/messages` | Anthropic frontier 대표; tool-use + extended reasoning 강함; 의료 AI deployments에서 가장 흔히 인용 |
| GPT-4o (gpt-4o-2024-08-06 또는 latest) | OpenAI | `https://api.openai.com/v1/chat/completions` | OpenAI frontier 대표; HealthBench paper의 base benchmark; 일반 비교 baseline |

**왜 정확히 2개?**
- **1개만 (예: Claude만)**: vendor-specific signal vs. frontier-tier signal 구분 불가. reviewer가 *"Claude만 vs. open-weight 차이는 vendor effect"* 라고 공격 가능.
- **3개 이상 (Claude + GPT-4o + Gemini 2.5 Pro)**: cost 1.5×, 시간 1.5일, ROI 미미. vendor diversity는 이미 open-weight 5개 vendor (Alibaba/DeepSeek/Nvidia/Google/OpenAI/Meta — 6개 with Llama-4-Scout) 로 확보됨.
- **2개 (Claude + GPT-4o)**: 두 frontier vendors 간 *consistency*가 곧 *frontier-tier signal*. open-weight signal과 비교 가능.

**Fallback (Doc 14 §2.3):** API quota 부족 시 → Claude Sonnet 1개 only + 30 episodes.

**대체 모델 (만약 위 2개 unavailable):**
- Claude 4 Opus (claude-opus-4-1) — 더 강력하지만 cost ~3×
- GPT-5 (gpt-5-2025-08, 출시 시) — 가장 최신
- Gemini 2.5 Pro — Google API tier

권고: **default Claude Sonnet 4.5 + GPT-4o**. 다른 모델은 deviation으로 별도 disclosure.

### II.3 Episode subset — W8-stratified 60

W8-stratification은 Doc 14 §2.3의 권고 + paper §4.1 corpus subset 표의 *"W8-filtered ranking subset (8-mdl, 706 scen, 3 runs = 16,944 ep)"* 와 일치한다.

**60-episode 샘플링 절차:**
1. W8-filtered 16,944 episodes 중 stratified random sample (size 60).
2. Stratification 변수: (a) CPG domain (25개; minimum 1 episode per domain → 25 episodes baseline), (b) violation type (per primary `d_G > 0` violation: WITHIN/BEFORE/FORBID/MUST balance), (c) difficulty (Phase A FA rate quartile).
3. 잔여 35 episodes는 expected-difficult 영역 (manual trap scenarios) 우선.
4. seed 고정 (`--seed 42`) → reproducibility.

**왜 60?**
- 너무 적으면 (예: 30) ranking pattern statistical power 부족 (CI width too wide for 95%).
- 너무 많으면 (예: 100+) cost 1.5×, 1 day 안에 안 끝남.
- 60은 hybrid sweet spot: 25 domains + 35 difficult/balance = 60. Wilson 95% CI on a 50% rate ≈ ±13pp (acceptable).

### II.4 Evaluation pipeline

3 단계로 구성. 모든 단계는 existing scripts 활용.

**Step 1: Frontier model run** (Doc 14 §2.3 명령):

```bash
export ANTHROPIC_API_KEY="..."
export OPENAI_API_KEY="..."

PYTHONPATH=. python scripts/experiments/frontier_spot_check.py \
    --models claude-sonnet-4-5,gpt-4o \
    --n-episodes 60 \
    --stratify w8 \
    --runs 3 \
    --seed 42 \
    --temperature 0.1 \
    --scaffold react \
    --rag bm25 \
    --output evidence_pack/frontier/spot_check_v1.json
```

**전제**: `frontier_spot_check.py`는 현재 부재. `run_frontier_models.py` (existing) 를 base로 wrapper 작성 필요. 핵심 차이점:
- existing은 15 scenarios × 3 runs (P2-1 legacy).
- 신규는 60 W8-stratified episodes × 2 frontier × 3 runs.
- Same ReAct scaffold + BM25 retrieval as 8 open-weight models (budget-matched 청구를 위해).

**Step 2: 6-evaluator scoring on frontier outputs:**

```bash
PYTHONPATH=. python scripts/experiments/run_six_evaluator_scoring.py \
    --episodes evidence_pack/frontier/spot_check_v1.json \
    --output evidence_pack/frontier/verdict_matrix_frontier.json
```

6 evaluators (TOM, ASC, PAF, CwT, ACov, TCC) 동일 적용. Same `cpg_engine/` post-hoc instances. Same `assessor_core/violations.py` + `harm_scorer.py`.

**Step 3: Comparison vs. open-weight 8 models (or 9):**

```bash
PYTHONPATH=. python scripts/experiments/frontier_ranking_comparison.py \
    --frontier evidence_pack/frontier/verdict_matrix_frontier.json \
    --baseline evidence_pack/analysis/verdict_matrix_v6.json \
    --episodes-baseline-subset 60 \
    --output evidence_pack/frontier/ranking_comparison.json \
    --macros paper/frontier_macros.tex
```

비교 metrics:
- **Frontier rank insertion**: Claude/GPT-4o가 9 open-weight 모델 ranking에서 어디 위치하는가? (TCC ranking에서 top-1? mid? bottom?)
- **Per-evaluator rank shift**: 9 baseline 중 frontier보다 위/아래에 있는 모델 수 — evaluator별로 다른가?
- **Pillar 3 ratio**: open-weight pattern과 frontier pattern 일치?
- **Pairwise reversal rate**: frontier 추가 후 pairwise model rankings reverse rate가 75%에서 어느 정도로 변하는가?
- **Verdict flip rate**: 60 episodes 중 6 evaluators가 verdict 일치하지 않는 episode 비율 (baseline 85.7%와 비교).

### II.5 Macros to populate

Doc 14 §2.3 + Doc 15 Part V.2 표 정의에 따라 다음 5개 macro 생성:

| Macro | 정의 | Expected value |
|---|---|---|
| `\frontierNEpisodes` | spot-check 사용된 episode 수 | 60 |
| `\frontierRankBetween` | frontier-tier가 9 baseline ranking 중 위치 (예: "rank 3-5") | TBD |
| `\frontierRankingPreservation` | open-weight ordering 보존율 (Spearman ρ) | TBD |
| `\frontierPillarThree` | frontier-only Pillar 3 ratio | TBD |
| `\frontierFlipRate` | frontier 결합 6-eval pairwise reversal rate (%) | TBD |

Macros file: `paper/frontier_macros.tex` (auto-generated). `auto_numbers.tex`에 `\input{frontier_macros}` 추가 또는 auto_numbers.tex에 직접 통합.

### II.6 Cost estimate

per episode 추정:
- Average tool-loop: 5-15 ReAct steps per episode (clinical scenario complexity).
- per-step token: ~2K input + ~500 output (Claude/GPT-4o pricing).
- 60 episodes × 3 runs × 2 models = 360 episodes total.
- 평균 10 steps × ~25K total tokens per episode = 360 × 25K = 9M tokens total.

**Pricing (2026-04 rates):**
- Claude Sonnet 4.5: $3/MTok input, $15/MTok output → ~$10-30 per 60 ep × 3 runs.
- GPT-4o: $2.5/MTok input, $10/MTok output → ~$8-25 per 60 ep × 3 runs.

**Total**: $20-60 (typical). Doc 14 권고 budget $50-100은 안전 margin 포함.

### II.7 Risks and mitigations

| Risk | 가능성 | Mitigation |
|---|---|---|
| Frontier model의 system prompt sensitivity 다름 | 높음 | Doc 14 §2.3: "Qwen-tuned prompt 사용 시 frontier 성능 저하 위험". 해결: ReAct scaffold prompt 그대로 사용 + system prompt에 *"tool-use guideline-following clinical agent"* 한 줄로 minimal. Frontier가 더 verbose 행동 시 disclosure |
| Budget-matched 비교 어려움 (token budget 정의 다름) | 중 | Per-episode token cap 동일 적용 (예: 32K input + 4K output). Frontier가 token 더 효율 사용 시 fairness 청구 강화 가능 |
| Tool-call format 차이 (function-call vs. ReAct text) | 중 | `agent_runner/llm_provider.py`의 `LLMBackend` enum에 ANTHROPIC + OPENAI 이미 존재. JSON parsing은 `repair_json` 적용. 양쪽 모두 ReAct text format으로 fallback |
| API rate limit / timeout | 중 | `LLMConfig.timeout_seconds=120`, `max_retries=3` 적용 (existing). Per-vendor concurrent request limit 준수 (Anthropic 5 RPS, OpenAI 500 RPM) |
| 결과가 baseline과 큰 ranking shift 보임 | 낮음-중 | **Honest disclosure 우선**. paper §6 Limitations에 *"frontier rank inserted at position X; open-weight ranking otherwise preserved"* 또는 *"frontier diverges; open-weight ordering does not transfer"* 명시. 후자도 reviewer-acceptable (audit paper의 falsifiable disclosure) |
| API key access 차단 | 낮음 | Fallback: 1 model + 30 episodes (Claude only) |

### II.8 Falsifiability and honest-failure framing

Doc 13 §13.1 (E_CRIT-3 outcome) + Doc 14 §2.3 (Fallback) 일관 권고: **결과가 unfavorable 하더라도 disclosure 우선**.

Possible outcomes 3 case:
- **Case A (favorable)**: frontier ordering이 open-weight ordering과 ρ ≥ 0.7. paper §4 paragraph + §6 약화: "open-weight ranking instability transfers."
- **Case B (mixed)**: frontier rank가 mid-pack 위치 + Pillar 3 ratio shift. paper에 *"frontier insertion at TCC-rank X; cross-tier ordering shifts under coverage evaluators"* 솔직 보고.
- **Case C (unfavorable)**: frontier가 모든 evaluator에서 top, ranking pattern 다름. paper §6에 *"frontier-tier improves both coverage and TCC compliance, suggesting our ranking-instability finding is most relevant to mid-tier open-weight models"* — 청구 scope 좁힘.

세 case 모두 acceptable to reviewer (audit paper의 valid finding). **Case C가 reviewer 입장에서 가장 valuable scientifically** (frontier capability gap을 정량화). Reject 위험은 spot-check 결과 자체가 아니라 *결과 부재*에 있음.

---

## Part III. Paper integration plan

### III.1 §6 Limitations 약화 (Tier 0 — 즉시 적용)

**현재 (vulnerable)**:
```latex
Runs use one ReAct scaffold on \numModels{} open-weight models (4B--397B) at $T{=}0.1$;
frontier APIs and broader $T$ sweeps are deferred (App.~\ref{app:temperature_sensitivity}).
```

**Spot-check 완료 후 (defense)**:
```latex
Runs use one ReAct scaffold on \numModels{} open-weight models (4B--397B) at $T{=}0.1$.
A frontier-API spot check (\frontierNEpisodes{} W8-stratified episodes $\times$ Claude
Sonnet 4.5 and GPT-4o $\times$ 3 runs; App.~\ref{app:frontier_spotcheck}) places the
frontier tier at TCC-\frontierRankBetween{} among the open-weight \numModels{} models, with
ranking-preservation Spearman $\rho{=}\frontierRankingPreservation{}$ and
pairwise-reversal rate \frontierFlipRate{}\% — the open-weight ranking instability
transfers. Broader $T$ sweeps remain deferred (App.~\ref{app:temperature_sensitivity}).
```

### III.2 New paragraph in §4 robustness summary 또는 별도 §4.7

옵션 A — §4.5 Robustness Summary 마지막에 추가 (1-2 sentence):

```latex
\emph{Frontier spot check.} A 60-episode W8-stratified subset re-scored under
Claude Sonnet 4.5 and GPT-4o (3 runs each, same ReAct scaffold) places the
frontier tier at TCC-\frontierRankBetween{} among the open-weight \numModels{} models,
with Pillar 3 ratio \frontierPillarThree{}$\times$ and pairwise reversal rate
\frontierFlipRate{}\% (App.~\ref{app:frontier_spotcheck}). The structural
75\%-reversal pattern transfers to the frontier tier.
```

옵션 B — 별도 §4.7 subsection (~5 sentences). 더 visible 하지만 length +0.2p.

권고: 옵션 A — Robustness Summary에 통합.

### III.3 New appendix § `app:frontier_spotcheck`

내용:
- Methodology (60-episode stratification, 3 runs, ReAct scaffold same as open-weight).
- Per-evaluator rank table: 9 open-weight + 2 frontier = 11 rows × 6 evaluator columns.
- Pillar 3 ratio per evaluator + frontier vs. open-weight Δ.
- Cost disclosure (~$50-100 API quota, fully replicable given API access).
- Honest disclosure (Case A/B/C 결과별).

### III.4 Bibliography additions (if needed)

- `claude2025` — Anthropic Claude Sonnet 4.5 (system card 또는 release note).
- `gpt4o2024` — OpenAI GPT-4o release note (이미 ML literature에 cite).

이 두 reference는 §4.1 Setup paragraph에서 *"frontier API: Claude Sonnet 4.5~\cite{claude2025} and GPT-4o~\cite{gpt4o2024}"* 인용용.

---

## Part IV. Execution decision matrix (지금 시점)

### IV.1 현재 상태 (2026-04-28)

| 항목 | 상태 |
|---|---|
| `frontier_spot_check.py` script | ❌ 없음 (similar `run_frontier_models.py` 존재 — base wrapper) |
| `run_six_evaluator_scoring.py` | ✅ existing (post-hoc CPG engine) |
| `frontier_ranking_comparison.py` | ❌ 없음 (분석 wrapper 신규 작성 필요) |
| API keys | ❌ 사용자 확보 필요 (Anthropic + OpenAI) |
| Budget | $20-60 typical, $100 cap |
| W8-stratified subset 정의 | ⚠ 필요 (60 episode 선정 + frozen JSON) |
| Existing infrastructure | `agent_runner/llm_provider.py` (LLMBackend.OPENAI + ANTHROPIC), eval_harness/runner.py (budget matching) |

### IV.2 실행 가능성 (5/6 deadline 기준)

오늘 (4/28) ~ 5/6 = 8 days. E_CRIT-3 cost 1 day + integration 1 day = 2 days. **충분히 가능.**

### IV.3 Decision points (사용자/anonymous-user 결정 필요)

**D1. 실행 여부**:
- (A) **실행** — paper에 frontier paragraph 추가, G1 attack 차단. (권고)
- (B) Skip — paper의 §6 *"frontier deferred"* 유지, future work.

**D2. 모델 선택**:
- (A) **Claude Sonnet 4.5 + GPT-4o** (default). (권고)
- (B) Claude Sonnet 4.5만 (fallback, $30 cost).
- (C) GPT-4o + Gemini 2.5 Pro (대체).
- (D) 3개 frontier (Claude + GPT-4o + Gemini), $100+ cost.

**D3. Episode count**:
- (A) **60 W8-stratified** (default).
- (B) 30 (fallback, 빠름).
- (C) 100 (extra power, +0.5d).

**D4. Paper integration scope**:
- (A) **§6 Limitations 약화 + §4.5 1-2 sentences + App.** (권고)
- (B) §6 약화만 (minimal).
- (C) 별도 §4.7 full subsection (visible, length +0.2p).

**D5. 환경**:
- (A) **anonymous-user env**에 위임 (E_CRIT-3 handoff 14번 doc 따라). (권고)
- (B) 본 cowork session에서 직접 실행 (API keys + scripts 사용자 제공 필요).

권고: D1=(A), D2=(A), D3=(A), D4=(A), D5=(A).

---

## Part V. Pre-flight checklist

D1=(A) 결정 시 anonymous-user 환경에서 실행 전 확인:

```
[ ] API keys available
    [ ] ANTHROPIC_API_KEY (claude-sonnet-4-5 access)
    [ ] OPENAI_API_KEY (gpt-4o access)
[ ] Scripts ready
    [ ] scripts/experiments/frontier_spot_check.py 작성 (run_frontier_models.py base)
    [ ] scripts/experiments/frontier_ranking_comparison.py 작성
    [ ] scripts/experiments/run_six_evaluator_scoring.py 작동 확인
[ ] Subset frozen
    [ ] evidence_pack/frontier/w8_60_subset.json (60 episode IDs, hash-frozen)
    [ ] Stratification verified (25 domains × 1+ episode each)
[ ] Budget pre-flight
    [ ] Sample 1 model × 3 episodes dry-run
    [ ] Token usage estimate × 360 → cost projection
    [ ] $100 cap budget approval
[ ] Output paths
    [ ] evidence_pack/frontier/spot_check_v1.json
    [ ] evidence_pack/frontier/verdict_matrix_frontier.json
    [ ] evidence_pack/frontier/ranking_comparison.json
    [ ] paper/frontier_macros.tex
[ ] Integration ready
    [ ] auto_numbers.tex에 frontier_macros 통합 또는 별도 \input
    [ ] §6 Limitations 약화 wording draft
    [ ] §4.5 또는 §4.7 paragraph draft
    [ ] App.~ref{app:frontier_spotcheck} 신규 section
[ ] Falsifiability disclosure
    [ ] Case A/B/C wording 미리 준비
    [ ] honest-failure framing OK with user
```

---

## Part VI. Timeline (5/6 deadline 기준)

```
Day 0 (지금, 4/28)  — Decision D1-D5 + API key setup + script wrapper 작성 (4-6h)
Day 1 (4/29)         — frontier_spot_check.py dry-run (3 episodes) → debug + budget verify
Day 2 (4/30)         — Full 60 × 2 × 3 = 360 episode run (Claude + GPT-4o)
                       Approx wall-clock: 4-8h per model with rate limits
Day 3 (5/1)          — 6-evaluator scoring + ranking comparison
                       paper/frontier_macros.tex 생성
                       ranking_comparison.json analysis
Day 4 (5/2)          — Paper integration:
                       - §6 Limitations 문장 교체
                       - §4.5 또는 §4.7 paragraph 추가
                       - App.~ref{app:frontier_spotcheck} section 작성
                       - Compile + length check
Day 5 (5/3)          — Buffer for re-runs, additional analysis
Day 6-7 (5/4-5/5)    — Camera-ready polish + cross-references + final compile
Day 8 (5/6)          — SUBMISSION
```

Buffer 1 day 포함 → 안전.

---

## Part VII. ROI assessment

### VII.1 시나리오별 ROI

| Outcome scenario | Reviewer 반응 | Paper 가치 변화 |
|---|---|---|
| Case A (favorable, ρ ≥ 0.7) | "open-weight finding transfers to frontier — solid generalization" | ↑↑ Acceptance probability +5-10pp |
| Case B (mixed) | "interesting nuance — paper acknowledges where finding holds vs. doesn't" | ↑ Acceptance probability +2-5pp |
| Case C (unfavorable) | "honest finding — paper now has 'open-weight specific' claim that's still scientifically valuable" | → Acceptance probability ±0pp (scope narrowing은 reject 사유 아님) |
| Skip (no spot-check) | "deferred — possible serious limitation" | ↓ Acceptance probability -3-5pp (G1 attack 그대로 유지) |

### VII.2 Cost-benefit

- **Cost**: $20-100, 2 days (1 day API run + 1 day integration), 1-2 wrapper scripts.
- **Benefit**: G1 attack 차단 (40-50% probability × 높은 위험도 = 20-25 expected reject probability mitigated).

ROI 명백히 positive. **권고: 즉시 실행 (D1=A)**.

---

## Part VIII. 결론 한 줄

**Frontier API spot-check 60 episodes × Claude Sonnet 4.5 + GPT-4o = $20-60, 2 days, +5-10pp acceptance probability**. paper §6 *"deferred"* 단서를 *"spot-checked, transfers"* 로 교체하는 것이 5/6 deadline 안에 가장 높은 ROI를 갖는 단일 작업. 결과가 unfavorable해도 honest disclosure로 reviewer-acceptable. Skip은 G1 attack 명분을 그대로 두므로 권장하지 않음.

다음 결정 부탁드립니다 (D1-D5).

---

## Appendix A — Doc 13 §13.1 + Doc 14 §2.3 + Doc 15 부분 cross-reference

본 보고서가 통합한 외부 source는 다음 위치:

- `docs/session_continuity_260424_260426/13_competitive_landscape_patch_for_system_ai.md`
  - §12.3 Attack G1 (line ~705): "Open-weight only models, no frontier API" 공격 분석
  - §13.1 Experiment E_CRIT-3 (line ~850): plan/outcome/cost 요약
  - §13.4 Hand-off summary (line ~990): 5/6 deadline 권고

- `docs/session_continuity_260424_260426/14_experiments_handoff_for_system_ai.md`
  - §1.3 Tier table (line ~45): E_CRIT-3 priority/resource/time
  - §2.3 E_CRIT-3 detailed plan (line ~233-313): goal, plan, command, integration, fallback, risk

- `docs/session_continuity_260424_260426/15_attack_defense_and_rubric_mapping.md`
  - Part III.3 (line ~290): 12 experiments handoff table — E_CRIT-3 행
  - Part V.2 (line ~519): E1-E7 ↔ NeurIPS rubric mapping (E_CRIT-3은 별도)
  - Part VI.4 (line ~557): 결론 — "frontier API ceiling unknown" 명시

- `paper/main_final_v18.tex` line 422: 현재 §6 Limitations *"frontier APIs and broader T sweeps are deferred"* 표현

- `scripts/experiments/run_frontier_models.py` (existing, line 1-50): P2-1 base wrapper. 신규 frontier_spot_check.py의 base.

- `scripts/experiments/integrate_frontier_results.py` (existing): 4-OSS + 2-frontier 통합 분석 base. 신규 frontier_ranking_comparison.py와 별개 (그러나 reuse 가능).
