# Beta-Blocker Commission in HF Scenarios — Corrected Analysis

**작성일:** 2026-05-06
**Corpus:** V73 SGSC (418 scenarios, 23 HF scenarios × 10 models × 3 runs = 690 HF episodes)
**데이터 출처:** `results/v73_full_with_allmh/`
**재현 스크립트:** inline Python (see `/tmp/v73_sgsc_repro_verify_v2.json`)

---

## 1. Errata — 이전 세션 테이블 수정

이전 세션에서 보고한 값 3개가 부정확했음:

| Model | 이전 보고 BB | 실제 BB | 이전 Det | 실제 Det | 수정 내용 |
|---|---|---|---|---|---|
| oss120b | 66-68 | **62** | 100% | **95.7%** | 1개 시나리오 비결정적 (`section_95_c013`) |
| qwen35b | 66-68 | **61** | 100% | **91.3%** | 2개 비결정적 (`section_101_c017`, `section_93_c011`) |
| qwen397b | 63 | **61** | 100% | **91.3%** | 2개 비결정적 (`section_82_c008`, `section_93_c011`) |

추가로 이전 테이블에 누락된 2개 모델:
- **qwen27b**: 25/69 BB commission, 39.1% deterministic
- **llama4scout**: 17/69 BB commission, 39.1% deterministic

---

## 2. 수정된 전체 테이블

| Model | BB commission (69 HF eps) | Det scenarios (23) | Det% | Group |
|---|---:|---:|---:|---|
| allm_h | 63 | 23/23 | 100% | Aggressive-deterministic |
| gemma31b | 63 | 23/23 | 100% | Aggressive-deterministic |
| oss120b | 62 | 22/23 | 95.7% | Aggressive-deterministic |
| qwen35b | 61 | 21/23 | 91.3% | Aggressive-deterministic |
| qwen397b | 61 | 21/23 | 91.3% | Aggressive-deterministic |
| qwen4b | 43 | 9/23 | 39.1% | Stochastic |
| qwen27b | 25 | 9/23 | 39.1% | Stochastic |
| llama4scout | 17 | 9/23 | 39.1% | Stochastic |
| nemotron30b | 0 | 23/23 | 100% | Conservative |
| deepseek_r1_7b | 0 | 23/23 | 100% | Conservative |

---

## 3. 3-Group Taxonomy

### Group A: Conservative (BB comm = 0%, Det = 100%)
**모델:** Nemotron-3-30B-A3B, DeepSeek-R1-7B
**행동:** 23개 HF 시나리오 전부에서 beta-blocker를 처방하지 않음. 3/3 run 완전 일치.
**임상 해석:** 2024 ACC Expert Consensus와 정렬 — decompensated HF에서 BB 신규 개시 금지 원칙을 준수. 다만 이것이 "올바른 임상적 보수성"인지 "일반적 약물 처방 회피"인지는 구분 필요. 이 모델들은 다른 domain (sepsis, stroke)에서도 전반적으로 낮은 commission rate를 보임.

### Group B: Aggressive-Deterministic (BB comm = 89-91%, Det ≥ 91%)
**모델:** ALLM.H, Gemma-4-31B, GPT-oss-120B, Qwen3.5-35B-A3B, Qwen3.5-397B-A17B
**행동:** 21-23개 HF 시나리오에서 일관되게 BB 처방. 소수(0-2개) 시나리오만 비결정적.
**임상 해석:** BB가 HFrEF GDMT 4-pillar의 핵심 구성요소라는 지식은 보유하나, decompensated 상태에서의 initiation 금지 조건을 인식하지 못함. "BB는 항상 좋다"는 과도한 일반화(overgeneralization). 이 trap은 2024 ACC ECDP의 핵심 권고 위반: *"Beta-blockers should not be newly initiated in patients with decompensated signs or symptoms"*.

### Group C: Stochastic (BB comm = 25-62%, Det = 39%)
**모델:** Qwen3-4B, Qwen3.5-27B, Llama-4-Scout-17B-16E
**행동:** 같은 시나리오에서도 run마다 BB 처방 여부가 달라짐 (14/23 시나리오 비결정적).
**임상 해석:** 임상 지식의 불확실성(epistemic uncertainty)이 stochastic 행동으로 표현됨. Temperature=0 greedy decoding에서도 logit 수준에서 BB 처방/비처방 간 확률이 근접해 token-level nondeterminism 발생.

---

## 4. 임상 근거 (Literature Support)

### Beta-blocker initiation in decompensated HF

| Source | 핵심 권고 |
|---|---|
| **2024 ACC ECDP** (JACC 2024) | "BB should not be newly initiated in patients with decompensated signs or symptoms but can be continued" |
| **2022 AHA/ACC/HFSA** | BB is Class I for stable HFrEF; initiate after hemodynamic stabilization |
| **STRONG-HF** (2023) | Rapid GDMT initiation is safe, but only *after* stabilization (Class I, Level B) |
| **ESC 2021** | "BB should be cautiously initiated in hospital, once the patient is haemodynamically stabilized" |
| **Circulation 2024** | "Barring absolute contraindications, patients with HFrEF should receive rapid initiation of all 4 foundational therapies" — but *after* stabilization |

### 이 trap이 CGA-Bench에서 작동하는 메커니즘

1. **CPG graph 설계:** `hf_initial_assessment` node에서 `initiate_beta_blocker`는 **allowed** (stable HFrEF 기준)
2. **SGSC 시나리오의 patient state:** decompensated HF (volume overload, congestion markers) → CPG engine이 dynamic constraint로 BB를 **forbidden**으로 전환
3. **모델의 실패 패턴:** "BB는 HF GDMT의 핵심" → context-blind 처방 → COMMISSION violation
4. **임상적 유사성:** 실제 병원에서도 "[clinical inertia의 반대] — 안정화 전 과도한 GDMT initiation"이 보고됨 (Ochsner Journal 2024)

---

## 5. Paper-Ready Text

### 5.1 Reproducibility claim (appendix 또는 §Experiments)

> **Run-level reproducibility.** Across all 10 models on the V7.3 SGSC corpus (418 scenarios, 3 runs each), the standard deviation of per-run mean CGA-S is below 0.007 for every model (max $\sigma = 0.0062$, DeepSeek-R1-7B; Table~\ref{tab:run_reproducibility}), confirming that greedy decoding ($T{=}0$) yields stable aggregate scores.
> Individual scenario-level variance is higher (mean per-scenario $\sigma$ ranges from 0.006 to 0.040), indicating that run-level stability arises from averaging over 418 scenarios rather than from per-scenario determinism.

### 5.2 BB commission finding (§Results 또는 §Case Study)

> **Case study: beta-blocker initiation in decompensated HF.**
> The AHA Heart Failure 2022 graph includes 23 scenarios in the V7.3 SGSC corpus where the patient presents with decompensated heart failure. Per 2024 ACC Expert Consensus, beta-blockers should not be newly initiated in decompensated patients despite being a cornerstone of stable HFrEF GDMT.
>
> Three behavioral groups emerge (Table~\ref{tab:bb_commission}):
> \textbf{(i)~Conservative} models (Nemotron-3-30B, DeepSeek-R1-7B) correctly withhold beta-blockers in all 23 scenarios across all 3 runs.
> \textbf{(ii)~Aggressive-deterministic} models (ALLM.H, Gemma-4-31B, GPT-oss-120B, Qwen3.5-35B, Qwen3.5-397B) commit the \textsc{commission} violation in 21--23 of 23 scenarios with $\geq$91\% cross-run determinism, indicating a systematic knowledge gap rather than stochastic error.
> \textbf{(iii)~Stochastic} models (Qwen3-4B, Qwen3.5-27B, Llama-4-Scout) exhibit run-dependent behavior (39\% determinism), prescribing beta-blockers in some runs but not others for the same scenario.
>
> This three-way split illustrates that \textsc{commission} violations in CGA-Bench are not uniformly random: they reflect stable, model-specific clinical reasoning patterns that are reproducible across evaluation runs.

### 5.3 LaTeX table

```latex
\begin{table}[t]
\centering
\caption{Beta-blocker \textsc{commission} in 23 decompensated HF scenarios
  (V7.3 SGSC, 69 episodes per model).
  \emph{BB eps}: episodes with \texttt{initiate\_beta\_blocker} commission;
  \emph{Det}: fraction of scenarios where the violation outcome
  is identical across all 3 runs.}
\label{tab:bb_commission}
\small
\begin{tabular}{@{}llrrr@{}}
\toprule
\textbf{Group} & \textbf{Model} & \textbf{BB eps} & \textbf{Det (\%)} & \textbf{BB rate} \\
\midrule
\multirow{2}{*}{Conservative}
  & Nemotron-3-30B-A3B        & 0/69  & 100 & 0\% \\
  & DeepSeek-R1-7B            & 0/69  & 100 & 0\% \\
\midrule
\multirow{5}{*}{\shortstack[l]{Aggressive-\\deterministic}}
  & ALLM.H                    & 63/69 & 100 & 91\% \\
  & Gemma-4-31B               & 63/69 & 100 & 91\% \\
  & GPT-oss-120B              & 62/69 & 95.7 & 90\% \\
  & Qwen3.5-35B-A3B           & 61/69 & 91.3 & 88\% \\
  & Qwen3.5-397B-A17B         & 61/69 & 91.3 & 88\% \\
\midrule
\multirow{3}{*}{Stochastic}
  & Qwen3-4B                  & 43/69 & 39.1 & 62\% \\
  & Qwen3.5-27B               & 25/69 & 39.1 & 36\% \\
  & Llama-4-Scout-17B-16E     & 17/69 & 39.1 & 25\% \\
\bottomrule
\end{tabular}
\end{table}
```

---

## 6. 3-Group 분류 근거

### 통계적 근거
- **Group A/B boundary** (0% vs ≥88% BB rate): 자연적 gap. 0과 17 사이에 연속 분포 없음.
- **Group B/C boundary** (≥88%, Det≥91% vs ≤62%, Det=39%): BB rate에서 61 → 43의 gap (18 eps), Det에서 91% → 39%의 gap (52pp). 명확한 bimodal 분포.
- 3개 Stochastic 모델은 모두 정확히 14/23 non-deterministic scenarios (우연의 일치가 아닌 동일한 14개 시나리오에서 비결정적일 가능성 높음).

### 임상적 근거 (수정됨 — §8 교차 검증 반영)
- **Conservative = Global BB avoidance:** ~~decompensation-aware~~. §8 교차 검증 결과, stable HFrEF에서도 BB를 처방하지 않아 "decompensation 인지"가 아닌 "전반적 BB 회피"로 재해석됨.
- **Aggressive = GDMT-first bias:** BB가 Class I인 것은 맞지만 stabilization 전제조건을 무시. 단, stable HFrEF에서는 올바르게 처방하므로 "BB가 항상 좋다"는 단방향 bias.
- **Stochastic = uncertain knowledge:** BB가 해당 상황에서 적절한지에 대한 모델 내부 확률이 50:50에 가까움. 흥미롭게도 qwen27b가 가장 높은 balanced accuracy를 보임 (§8 참조).

### 추가 실험 제안
1. **Prompt ablation:** "The patient is hemodynamically unstable" 문구를 명시적으로 넣었을 때 Group B 모델의 BB commission이 줄어드는지 확인 → knowledge gap vs. prompt sensitivity 구분
2. ~~**Stable HFrEF 시나리오 비교**~~ → **완료** (§8). V6b 9개 stable HFrEF 시나리오로 교차 검증 수행. 결과: Conservative 모델은 stable에서도 BB omission 89%.
3. **Cross-domain commission profile:** BB commission 패턴과 다른 domain의 commission 패턴(e.g., nitrate in RV infarct, NSAID in AKI)의 상관관계 → model-level "aggressiveness" trait의 일관성

---

## 7. Provenance

- **재현 방법:** V73 SGSC raw JSON 직접 파싱 (`results/v73_full_with_allmh/`)
- **HF 시나리오 식별:** filename containing `heart_fail` or `cardiogenic` (23 unique scenario_ids)
- **BB commission 정의:** `violation_events` 중 `violation_type == "commission"` AND `action_involved` containing `"beta_blocker"` (case-insensitive)
- **Determinism 정의:** 시나리오 내 3 runs 모두 동일한 BB commission 여부 (3/3 또는 0/3)
- **결과 파일:** `/tmp/v73_sgsc_repro_verify_v2.json`

---

## 8. Cross-Validation: Stable HFrEF에서의 BB 처방 행동 (추가 실험 #2)

**목적:** §3의 3-Group 분류가 진정한 임상적 판단력 차이인지, 아니면 단순한 "전반적 처방 경향"인지 구분.

**방법:**
- **Corpus:** V6b PhaseB (`results/full_v6b/`), 9 models (allm_h 제외), 3186 scenarios, 3 runs
- **Stable HFrEF 시나리오:** CPG graph `aha_heart_failure_2022.yaml`의 `hfref_gdmt` node에서 `initiate_beta_blocker`가 **mandatory**인 시나리오 9개 식별
- **BB omission 정의:** `violation_events` 중 `violation_type == "omission"` AND `description` containing `"initiate_beta_blocker"`
- **핵심 질문:** Conservative 모델(nemotron30b, deepseek_r1_7b)이 stable HFrEF에서 BB를 올바르게 처방하는가?

### 8.1 V73 SGSC 한계

V73 SGSC의 23개 HF 시나리오는 **전부 decompensated HF** (BB-forbidden). Stable HFrEF (BB-mandatory) 시나리오가 0개이므로, V6b corpus를 사용해야 교차 검증 가능.

### 8.2 Cross-Validation 결과

| Model | V73: BB comm/69 (forbidden) | V6b: BB Rx/27 (mandatory) | V6b: BB Omit/27 | Correct Withhold (V73) | Correct Prescribe (V6b) | **BA** | Interpretation |
|---|---:|---:|---:|---:|---:|---:|---|
| nemotron30b | 0/69 | 0/27 | 24/27 | 100% | 11.1% | **0.556** | Global BB avoidance |
| deepseek_r1_7b | 0/69 | 3/27 | 24/27 | 100% | 11.1% | **0.556** | Global BB avoidance |
| gemma31b | 63/69 | 21/27 | 3/27 | 8.7% | 77.8% | **0.432** | Global BB bias |
| oss120b | 62/69 | 23/27 | 1/27 | 10.1% | 85.2% | **0.477** | Global BB bias |
| qwen35b | 61/69 | 23/27 | 1/27 | 11.6% | 85.2% | **0.484** | Global BB bias |
| qwen397b | 61/69 | 21/27 | 3/27 | 11.6% | 77.8% | **0.447** | Global BB bias |
| qwen4b | 43/69 | 17/27 | 7/27 | 37.7% | 63.0% | **0.503** | Near-random |
| qwen27b | 25/69 | 17/27 | 7/27 | 63.8% | 63.0% | **0.634** | Best discriminator |
| llama4scout | 17/69 | — | — | 75.4% | — | — | V6b 미포함 |

**BA** = Balanced Accuracy = (Correct Withhold Rate + Correct Prescribe Rate) / 2

### 8.3 핵심 발견

1. **Conservative ≠ Decompensation-aware.**
   Nemotron30b와 DeepSeek-R1-7B는 stable HFrEF에서 BB를 27 episodes 중 0-3회만 처방 (89% omission). 이는 "decompensated 상태를 인식해서 BB를 withhold한 것"이 아니라, **BB를 전혀 처방하지 않는 전반적 경향**. 다른 domain (sepsis, stroke)에서도 낮은 commission rate를 보이는 것과 일치.

2. **Aggressive-deterministic = Unidirectional GDMT bias.**
   Gemma31b, oss120b, qwen35b, qwen397b는 stable HFrEF에서 BB를 77-85%로 올바르게 처방하나, decompensated에서도 88-91% commission. "BB는 항상 HF에 좋다"는 단방향 bias이며, patient state에 따른 조건부 추론이 부재.

3. **Stochastic 중 qwen27b가 최고 판별력.**
   qwen27b의 BA=0.634는 전체 모델 중 가장 높음. V73에서 63.8% correct withhold, V6b에서 63.0% correct prescribe — 완벽하지는 않으나, decompensated와 stable을 어느 정도 구분. "불확실성"이 오히려 conditional reasoning의 신호일 수 있음.

4. **어떤 모델도 BA > 0.70을 달성하지 못함.**
   이상적인 모델은 BA=1.0 (decompensated에서 0% commission + stable에서 100% prescribe). 최고 BA=0.634(qwen27b)는 random baseline(0.50)보다 불과 13.4pp 높으며, **BB initiation의 조건부 판단은 현재 LLM의 근본적 한계**.

### 8.4 3-Group Taxonomy 수정

| Group | 이전 해석 (§3) | 수정된 해석 (§8 교차 검증 후) |
|---|---|---|
| **Conservative** | Decompensation-aware (2024 ACC ECDP 준수) | **Global BB avoidance** — 상태와 무관하게 BB 비처방. 단방향 "안전 편향". |
| **Aggressive-det** | Context-blind GDMT overgeneralization | **Unidirectional GDMT bias** — BB 자체는 올바르게 인지하나, forbidden 조건 무시. 단방향 "적극 편향". |
| **Stochastic** | Epistemic uncertainty → stochastic behavior | **Partial conditional reasoning** — 특히 qwen27b는 가장 높은 BA를 보이며, 불확실성이 "실패"가 아닌 "조건부 추론의 partial 성공"일 수 있음. |

### 8.5 Corpus 제약 사항

- V73 SGSC와 V6b는 **시나리오 생성 방법이 다름** (SGSC vs PhaseB). 동일 시나리오가 아니므로 직접 대조는 제한적.
- V6b에 allm_h와 llama4scout 데이터가 없어 9개 모델만 교차 검증 가능.
- V6b의 9개 BB-mandatory 시나리오(27 episodes)는 표본이 작아 통계적 신뢰구간이 넓음.

---

## 9. Updated Paper-Ready Text

### 9.1 BB commission finding (§Results 또는 §Case Study) — 교차 검증 포함 버전

> **Case study: beta-blocker initiation in decompensated HF.**
> The AHA Heart Failure 2022 graph includes 23 scenarios in the V7.3 SGSC corpus where the patient presents with decompensated heart failure. Per 2024 ACC Expert Consensus, beta-blockers should not be newly initiated in decompensated patients despite being a cornerstone of stable HFrEF GDMT.
>
> Three behavioral groups emerge (Table~\ref{tab:bb_commission}):
> \textbf{(i)~Conservative} models (Nemotron-3-30B, DeepSeek-R1-7B) withhold beta-blockers in all 23 decompensated scenarios across all 3 runs.
> \textbf{(ii)~Aggressive-deterministic} models (ALLM.H, Gemma-4-31B, GPT-oss-120B, Qwen3.5-35B, Qwen3.5-397B) commit the \textsc{commission} violation in 21--23 of 23 scenarios with $\geq$91\% cross-run determinism.
> \textbf{(iii)~Stochastic} models (Qwen3-4B, Qwen3.5-27B, Llama-4-Scout) exhibit run-dependent behavior (39\% determinism).
>
> **Cross-validation on stable HFrEF.** To distinguish genuine clinical discrimination from blanket prescribing patterns, we evaluated the same models on 9 stable HFrEF scenarios from the V6b corpus where beta-blocker initiation is \emph{mandatory}. Conservative models prescribed beta-blockers in only 11\% of mandatory episodes, revealing \emph{global beta-blocker avoidance} rather than decompensation-aware reasoning. Aggressive models correctly prescribed in 78--85\% of mandatory episodes but committed violations in 88--91\% of forbidden episodes. No model exceeded a balanced accuracy of 0.64 (Table~\ref{tab:bb_cross_validation}), indicating that \emph{conditional} reasoning about beta-blocker initiation---prescribe when stable, withhold when decompensated---remains a fundamental gap across all evaluated models.

### 9.2 Cross-Validation LaTeX Table

```latex
\begin{table}[t]
\centering
\caption{Cross-validation of beta-blocker clinical discrimination.
  \emph{Correct withhold}: fraction of decompensated HF episodes (V7.3 SGSC)
  where the model correctly avoided \texttt{initiate\_beta\_blocker}.
  \emph{Correct prescribe}: fraction of stable HFrEF episodes (V6b)
  where the model correctly initiated beta-blockers.
  BA = balanced accuracy.}
\label{tab:bb_cross_validation}
\small
\begin{tabular}{@{}lrrrr@{}}
\toprule
\textbf{Model} & \textbf{Withhold (\%)} & \textbf{Prescribe (\%)} & \textbf{BA} & \textbf{Pattern} \\
\midrule
Nemotron-3-30B     & 100   & 11.1  & 0.556 & Avoidance \\
DeepSeek-R1-7B     & 100   & 11.1  & 0.556 & Avoidance \\
\midrule
Gemma-4-31B        & 8.7   & 77.8  & 0.432 & BB bias \\
GPT-oss-120B       & 10.1  & 85.2  & 0.477 & BB bias \\
Qwen3.5-35B        & 11.6  & 85.2  & 0.484 & BB bias \\
Qwen3.5-397B       & 11.6  & 77.8  & 0.447 & BB bias \\
\midrule
Qwen3-4B           & 37.7  & 63.0  & 0.503 & Near-random \\
Qwen3.5-27B        & 63.8  & 63.0  & 0.634 & Best \\
\bottomrule
\end{tabular}
\end{table}
```

---

## 10. Provenance (Updated)

### V73 SGSC Analysis (§1-§7)
- **데이터:** `results/v73_full_with_allmh/` (10 models × 418 scenarios × 3 runs)
- **HF 시나리오:** filename containing `heart_fail` or `cardiogenic` → 23 unique scenario_ids
- **BB commission:** `violation_events` 중 `violation_type == "commission"` AND `action_involved` containing `"beta_blocker"`
- **결과:** `/tmp/v73_sgsc_repro_verify_v2.json`

### V6b Cross-Validation (§8)
- **데이터:** `results/full_v6b/` (9 models × 3186 scenarios × 3 runs)
- **BB-mandatory 시나리오:** filename containing `heart_fail` → `hfref_gdmt` node에서 `initiate_beta_blocker`가 mandatory인 9개 시나리오
- **BB omission:** `violation_events` 중 `violation_type == "omission"` AND `description` containing `"initiate_beta_blocker"`
- **BB prescription:** `actions` 배열에서 `action_id` containing `"beta_blocker"` OR `"carvedilol"` OR `"metoprolol"`
- **BA 계산:** `(correct_withhold_rate + correct_prescribe_rate) / 2`

### CPG Graph Reference
- `cpg_model/graphs/aha_heart_failure_2022.yaml`:
  - `hf_initial_assessment` → allowed: `initiate_beta_blocker`
  - `hfref_gdmt` → mandatory: `initiate_beta_blocker`
  - `adhf_cold_wet` → forbidden: `give_high_dose_beta_blocker`
  - `cardiogenic_shock_management` → forbidden: `give_beta_blocker`

**End of report.**
