# Per-model Conformance & Blind-Spot Metrics including ALLM.H — V6 706 vs SGSC V7.3 Substrate Comparison

**작성일:** 2026-05-06
**대상 corpus:** V6 706 manual (paper main) · SGSC V7.3 (paper appendix)
**모델:** 9 open-weight + ALLM.H (n=10)
**데이터 출처:**
- `evidence_pack/analysis/verdict_matrix_v6_706_with_allmh.json` (11.4 MB, n=21,180 episodes)
- `evidence_pack/analysis/verdict_matrix_v7_3_with_allmh.json` (6.8 MB, n=12,540 episodes)

**관련 매크로 파일:**
- `paper/auto_numbers_v6_706_with_allmh.tex` (Phase 1 + Phase 2 verdict-derived)
- `paper/auto_numbers_v73_full_with_allmh.tex`
- `paper/auto_numbers_v73_expanded_with_allmh.tex`
- `paper/auto_numbers_v6_phase_b_with_allmh.tex`
- `paper/auto_numbers_allmh.tex` (cross-substrate summary)

**관련 메모:**
- `memory/project_allm_h_v73_deployment.md` (ALLM.H 5/5 substrate readiness)
- `memory/project_v73_typed_cwt_sanity_3check.md` (typed CwT ladder)
- `docs/critical_review/deviation_metric_reconsideration_20260504.md` (DEVIATION rubric flaw)

---

## 1. Definitions

| Symbol | Meaning |
|---|---|
| TCC | Trace-conformance check pass rate ≡ `NOT v4_hard` (no hard violation: OMISSION/COMMISSION/TIMING/SEQUENCE 임계 초과 부재) |
| ASC | Action-set consensus pass (`ac_proxy = action_coverage ≥ 0.5`) |
| MAB | MedAgentBench-style F1 pass (`mab_proxy = mab_f1 ≥ 0.5`) |
| CwT | Coverage-with-timing (C2 mandatory completion `c2_pass = c2_score ≥ 0.7`) |
| BSR$_{\text{cond}}$ | Conditional blind-spot rate $P(\text{hard} \mid \text{ASC pass})$ |
| Δ | MAB pass% − TCC pass% (positive = MAB over-credits the model) |
| strict3 | $P(\text{ASC} \cap \text{MAB} \cap \text{CwT pass} \cap \text{hard})$ — 3-way consensus FA |
| loose2 | $P(\text{ASC} \cap \text{CwT pass} \cap \text{hard})$ — 2-way consensus FA |
| Hard | $P(v4\_\text{hard})$ — episode가 hard violation 보유 |

**임계값:** AC ≥ 0.5, MAB-F1 ≥ 0.5, C2 ≥ 0.7, ACov ≥ 0.5 (file: `verdict_matrix_v*.json metadata.evaluator_thresholds`).

---

## 2. Main paper corpus — V6 706 (n=21,180)

V6 706 = 706 manual scenarios × 10 models × 3 runs. 본문 §5.2 / Table~\ref{tab:evaluator_performance}, Table~\ref{tab:headline_replay} 캐논 corpus.

### Table A. Per-model conformance and blind-spot metrics (with rank)

| Model | TCC (%) | ASC (%) | MAB (%) | BSR$_{\text{cond}}$ (%) | Δ (pp) | ASC rank |
|---|---:|---:|---:|---:|---:|---:|
| Gemma-4-31B | **52.9** (1) | 74.7 | 55.6 | 47.8 | +2.7 | 7 |
| Qwen3.5-397B-A17B | **50.5** (2) | 84.0 | 54.2 | 53.8 | +3.7 | 3 |
| Qwen3.5-27B | **47.7** (3) | 78.7 | 57.3 | 55.3 | +9.6 | 5 |
| Qwen3.5-35B-A3B | **44.9** (4) | 86.3 | 52.1 | 58.7 | +7.3 | 1 |
| Nemotron-3-30B-A3B | **44.6** (5) | 62.6 | 52.2 | 64.2 | +7.6 | 9 |
| GPT-oss-120B | **43.3** (6) | 85.0 | 49.4 | 61.2 | +6.1 | 2 |
| Llama-4-Scout-17B-16E | **42.4** (7) | 76.8 | 62.5 | 65.1 | +20.1 | 6 |
| Qwen3-4B | **41.2** (8) | 79.3 | 66.2 | 65.5 | +25.0 | 4 |
| **ALLM.H** | **39.7** (9) | 53.9 | 33.6 | 73.1 | −6.0 | 10 |
| DeepSeek-R1-7B | **33.6** (10) | 64.6 | 24.6 | 80.4 | −9.1 | 8 |
| **Aggregate** | **44.1** | 74.6 | 50.8 | 61.8 | +6.7 | — |

### Table B. Headline replay (MAB-style F1 vs AC-style coverage vs TCC) — Pub-size order

| Model | N | MAB (%) | AC (%) | TCC (%) | Δ(MAB−TCC) | Δ(AC−TCC) |
|---|---:|---:|---:|---:|---:|---:|
| Qwen3.5-397B-A17B | 2,118 | 54.2 | 84.0 | 50.5 | +3.7 | +33.5 |
| GPT-oss-120B | 2,118 | 49.4 | 85.0 | 43.3 | +6.1 | +41.6 |
| Llama-4-Scout-17B-16E | 2,118 | 62.5 | 76.8 | 42.4 | +20.1 | +34.4 |
| Gemma-4-31B | 2,118 | 55.6 | 74.7 | 52.9 | +2.7 | +21.8 |
| **ALLM.H** | 2,118 | 33.6 | 53.9 | 39.7 | **−6.0** | +14.2 |
| Nemotron-3-30B-A3B | 2,118 | 52.2 | 62.6 | 44.6 | +7.6 | +18.0 |
| Qwen3.5-35B-A3B | 2,118 | 52.1 | 86.3 | 44.9 | +7.3 | +41.4 |
| Qwen3.5-27B | 2,118 | 57.3 | 78.7 | 47.7 | +9.6 | +31.0 |
| DeepSeek-R1-7B | 2,118 | 24.6 | 64.6 | 33.6 | −9.1 | +31.0 |
| Qwen3-4B | 2,118 | 66.2 | 79.3 | 41.2 | +25.0 | +38.1 |
| **Aggregate** | 21,180 | 50.8 | 74.6 | 44.1 | +6.7 | +30.5 |

- **8/10** models satisfy MAB > TCC (paper headline `\hlNumModelsMABgtTCC`).
- **10/10** models satisfy AC > TCC (≥ 0; AC is uniformly looser than TCC on V6).
- 두 예외 ALLM.H, DeepSeek-R1-7B는 액션-셋 coverage 자체가 낮아 MAB가 보수적인 것 — "blind-spot" 부재 신호가 아니라 모델 출력 빈도 특성.

### Table C. Strict false-accept (ASC ∩ MAB ∩ CwT pass + hard)

| Model | N | strict3 N | strict3 (%) | loose2 N | loose2 (%) | Hard (%) |
|---|---:|---:|---:|---:|---:|---:|
| Llama-4-Scout-17B-16E | 2,118 | 212 | 10.01 | 248 | 11.71 | 57.6 |
| Qwen3.5-397B-A17B | 2,118 | 187 | 8.83 | 323 | 15.25 | 49.5 |
| Qwen3-4B | 2,118 | 166 | 7.84 | 218 | 10.29 | 58.8 |
| GPT-oss-120B | 2,118 | 164 | 7.74 | 365 | 17.23 | 56.7 |
| Qwen3.5-35B-A3B | 2,118 | 131 | 6.19 | 294 | 13.88 | 55.1 |
| Qwen3.5-27B | 2,118 | 124 | 5.85 | 246 | 11.61 | 52.3 |
| **ALLM.H** | 2,118 | 123 | 5.81 | 330 | 15.58 | 60.3 |
| Nemotron-3-30B-A3B | 2,118 | 62 | 2.93 | 155 | 7.32 | 55.4 |
| DeepSeek-R1-7B | 2,118 | 41 | 1.94 | 98 | 4.63 | 66.4 |
| Gemma-4-31B | 2,118 | 37 | 1.75 | 159 | 7.51 | 47.1 |
| **Aggregate** | 21,180 | 1,247 | **5.89** | 2,436 | **11.50** | 55.9 |

- Aggregate strict3 5.89% = paper headline `\strictFAThree{}` (1,247 episodes ASC ∩ MAB ∩ CwT all-pass yet hard violation present).
- Aggregate loose2 11.50% = `\faAllOblivious{}` (2,436 episodes 2-way consensus FA).
- ALLM.H strict3 5.81% (mid-pack, 7th of 10) — hard rate 60.3%로 corpus 평균(55.9%)보다 높지만 ASC/MAB 임계 둘 다 통과하는 episode는 적어 strict3 절댓값은 중간.

---

## 3. Appendix corpus — SGSC V7.3 (n=12,540)

SGSC V7.3 = 418 SGSC scenarios × 10 models × 3 runs. Appendix \ref{app:bsr_table} 보고용 substrate-dependence 증거 corpus.

### Table A′. Per-model conformance and blind-spot metrics (with rank) — V7.3 SGSC

| Model | TCC (%) | ASC (%) | MAB (%) | BSR$_{\text{cond}}$ (%) | Δ (pp) | ASC rank |
|---|---:|---:|---:|---:|---:|---:|
| Nemotron-3-30B-A3B | **82.5** (1) | 5.5 | 0.6 | 66.7 | −81.9 | 10 |
| Qwen3.5-27B | **73.8** (2) | 6.8 | 0.4 | 78.8 | −73.4 | 9 |
| Qwen3-4B | **64.9** (3) | 7.8 | 0.5 | 73.5 | −64.4 | 8 |
| DeepSeek-R1-7B | **58.1** (4) | 8.5 | 0.1 | 76.6 | −58.0 | 7 |
| **ALLM.H** | **56.1** (5) | 10.1 | 0.0 | 82.7 | −56.1 | 5 |
| Qwen3.5-397B-A17B | **51.9** (6) | 12.5 | 0.0 | 76.4 | −51.9 | 3 |
| Llama-4-Scout-17B-16E | **51.3** (7) | 9.5 | 0.3 | 78.2 | −51.0 | 6 |
| Qwen3.5-35B-A3B | **45.5** (8) | 13.2 | 0.0 | 72.9 | −45.5 | 2 |
| GPT-oss-120B | **44.7** (9) | 13.3 | 0.0 | 83.8 | −44.7 | 1 |
| Gemma-4-31B | **44.6** (10) | 10.4 | 0.0 | 84.6 | −44.6 | 4 |
| **Aggregate** | **57.3** | 9.8 | 0.2 | 78.0 | −57.1 | — |

### Table B′. Headline replay — V7.3 SGSC

| Model | N | MAB (%) | AC (%) | TCC (%) | Δ(MAB−TCC) | Δ(AC−TCC) |
|---|---:|---:|---:|---:|---:|---:|
| Nemotron-3-30B-A3B | 1,254 | 0.6 | 5.5 | 82.5 | −81.9 | −77.0 |
| Qwen3.5-27B | 1,254 | 0.4 | 6.8 | 73.8 | −73.4 | −67.1 |
| Qwen3-4B | 1,254 | 0.5 | 7.8 | 64.9 | −64.4 | −57.1 |
| DeepSeek-R1-7B | 1,254 | 0.1 | 8.5 | 58.1 | −58.0 | −49.5 |
| **ALLM.H** | 1,254 | 0.0 | 10.1 | 56.1 | −56.1 | −45.9 |
| Qwen3.5-397B-A17B | 1,254 | 0.0 | 12.5 | 51.9 | −51.9 | −39.4 |
| Llama-4-Scout-17B-16E | 1,254 | 0.3 | 9.5 | 51.3 | −51.0 | −41.8 |
| Qwen3.5-35B-A3B | 1,254 | 0.0 | 13.2 | 45.5 | −45.5 | −32.3 |
| GPT-oss-120B | 1,254 | 0.0 | 13.3 | 44.7 | −44.7 | −31.3 |
| Gemma-4-31B | 1,254 | 0.0 | 10.4 | 44.6 | −44.6 | −34.2 |
| **Aggregate** | 12,540 | 0.2 | 9.8 | 57.3 | −57.1 | −47.6 |

### Table C′. Strict false-accept — V7.3 SGSC

| Model | N | strict3 N | strict3 (%) | loose2 N | loose2 (%) | Hard (%) |
|---|---:|---:|---:|---:|---:|---:|
| GPT-oss-120B | 1,254 | 0 | 0.00 | 109 | 8.69 | 55.3 |
| Qwen3.5-35B-A3B | 1,254 | 0 | 0.00 | 102 | 8.13 | 54.5 |
| Qwen3.5-397B-A17B | 1,254 | 0 | 0.00 | 99 | 7.89 | 48.1 |
| Llama-4-Scout-17B-16E | 1,254 | 0 | 0.00 | 82 | 6.54 | 48.7 |
| Gemma-4-31B | 1,254 | 0 | 0.00 | 77 | 6.14 | 55.4 |
| **ALLM.H** | 1,254 | 0 | 0.00 | 72 | 5.74 | 43.9 |
| Qwen3.5-27B | 1,254 | 0 | 0.00 | 58 | 4.63 | 26.2 |
| Qwen3-4B | 1,254 | 0 | 0.00 | 43 | 3.43 | 35.1 |
| Nemotron-3-30B-A3B | 1,254 | 0 | 0.00 | 31 | 2.47 | 17.5 |
| DeepSeek-R1-7B | 1,254 | 0 | 0.00 | 27 | 2.15 | 41.9 |
| **Aggregate** | 12,540 | 0 | 0.00 | 700 | 5.58 | 42.7 |

- V7.3에서는 MAB-F1 ≥ 0.5 임계를 거의 누구도 통과하지 못해 (aggregate MAB pass = 0.2%) **3-way strict3는 일관되게 0**. SGSC corpus의 expanded expected-action 집합이 MAB 분모를 키워 F1을 구조적으로 낮춤.
- loose2(ASC ∩ CwT) 5.58%이 V7.3의 paper-replicable headline metric. V6의 11.50%과 비교하면 SGSC가 절반 수준.

---

## 4. Cross-substrate inversion

### Table D. V6 706 ↔ V7.3 SGSC 핵심 지표 비교

| 지표 | V6 706 (main) | V7.3 SGSC (appendix) | Δ (V7.3 − V6) |
|---|---:|---:|---:|
| Episodes | 21,180 | 12,540 | — |
| Scenarios × Models × Runs | 706×10×3 | 418×10×3 | — |
| Aggregate TCC | 44.1% | 57.3% | +13.2pp |
| Aggregate ASC | 74.6% | 9.8% | −64.8pp |
| Aggregate MAB | 50.8% | 0.2% | −50.6pp |
| Aggregate CwT | 27.9% | 30.7% | +2.8pp |
| Aggregate Δ(MAB−TCC) | **+6.7** | **−57.1** | **−63.8pp (부호 역전)** |
| Aggregate Δ(AC−TCC) | **+30.5** | **−47.6** | **−78.1pp (부호 역전)** |
| Aggregate Hard rate | 55.9% | 42.7% | −13.2pp |
| Aggregate strict3 | 5.89% | 0.00% | −5.89pp |
| Aggregate loose2 | 11.50% | 5.58% | −5.92pp |
| Aggregate BSR$_{\text{cond,ASC}}$ | 61.8% | 78.0% | +16.2pp |
| TCC top-1 model | Gemma-4-31B (52.9) | Nemotron-3-30B-A3B (82.5) | model swap |
| TCC bottom-1 model | DeepSeek-R1-7B (33.6) | Gemma-4-31B (44.6) | model swap |
| **ALLM.H TCC rank** | **9 / 10** | **5 / 10** | **+4 ranks** |
| ALLM.H Δ(MAB−TCC) | −6.0 | −56.1 | −50.1pp |

### Table E. Per-model TCC rank flip (V6 → V7.3)

| Model | V6 TCC (%) | V6 rank | V7.3 TCC (%) | V7.3 rank | Δ rank |
|---|---:|---:|---:|---:|---:|
| Gemma-4-31B | 52.9 | 1 | 44.6 | 10 | **−9** |
| Qwen3.5-397B-A17B | 50.5 | 2 | 51.9 | 6 | −4 |
| Qwen3.5-27B | 47.7 | 3 | 73.8 | 2 | +1 |
| Qwen3.5-35B-A3B | 44.9 | 4 | 45.5 | 8 | −4 |
| Nemotron-3-30B-A3B | 44.6 | 5 | 82.5 | 1 | **+4** |
| GPT-oss-120B | 43.3 | 6 | 44.7 | 9 | −3 |
| Llama-4-Scout-17B-16E | 42.4 | 7 | 51.3 | 7 | 0 |
| Qwen3-4B | 41.2 | 8 | 64.9 | 3 | **+5** |
| **ALLM.H** | **39.7** | **9** | **56.1** | **5** | **+4** |
| DeepSeek-R1-7B | 33.6 | 10 | 58.1 | 4 | **+6** |

**Spearman rank correlation (V6 ↔ V7.3 TCC):** 음의 상관 — `corr(rank_V6, rank_V73) ≈ −0.32` (10개 모델 단순 계산), 즉 corpus 변경시 ranking이 거의 무의미하게 무너짐.

---

## 5. Interpretation

### 5.1 ALLM.H substrate-dependence (paper §Discussion 핵심)

| Substrate | n | ALLM.H TCC rank | BSR$_{\text{cond}}$ | 해석 |
|---|---:|---:|---:|---|
| V6 706 manual | 21,180 | 9 / 10 | 73.1% | Expert-curated guideline 어휘 (예: `give_crystalloid_30ml_kg`)와 ALLM.H 의학 SFT 출력(`administer_normal_saline_bolus_30ml_per_kg`) 미정렬 → action_id normalize 실패 → C2/C3 점수 저하 |
| V7.3 SGSC | 12,540 | **5 / 10** | 82.7% | SGSC가 자동 atom-proposer로 paraphrase variant 다수 포함 → ALLM.H의 자연 phrasing이 더 잘 매칭 |

**Paper 규칙:** ALLM.H 단일-substrate 보고 금지. 본문은 V6 706, Appendix는 V7.3 SGSC, 두 substrate의 dual metric (compliance + typed_compliance) 동시 게재.

### 5.2 Δ(MAB−TCC) 부호 역전이 의미하는 바

본문 §5.4의 핵심 주장은 *"trace-level scorer가 제공하는 conclusion을 action-set scorer가 over-credit한다 (Δ > 0)"*. V6에서 +6.7pp로 성립. 그러나 **SGSC V7.3에서는 Δ = −57.1pp**, 즉 MAB가 TCC보다 더 엄격.

이 역전은 이론적으로 **모순이 아니다**:

- V6 706: `expected_actions` per scenario 평균 7.0개, 짧은 list → MAB-F1 ≥ 0.5 임계가 쉽게 충족됨 → MAB pass% 높음 → MAB가 TCC를 over-credit.
- V7.3 SGSC: `expected_actions` per scenario 평균 22.4개 (3.2× 확장), 길고 풍부한 expected list → MAB-F1 분모가 커지고 ≥ 0.5 임계 사실상 미달 → MAB pass% 0.2% → MAB가 TCC보다 훨씬 엄격.

**Theorem 1 (Observation Coarsening) 적용:** MAB는 *projection $\pi_{\text{aset}}$* 하에서 정의되는 evaluator이므로 corpus-level expected_actions 분포에 종속. SGSC는 더 까다로운 expected_set으로 MAB를 "tightening"하지만, **이는 MAB가 hard-violation detection 능력을 얻은 것이 아니다** — strict3 0%, loose2 5.58%로 여전히 blind-spot이 잔존.

### 5.3 Paper-rep 가능 metric 매핑

| Paper Section | Primary corpus | Secondary (Appendix) | 핵심 metric |
|---|---|---|---|
| §5.2 Verdict flip prevalence | V6 706 | V7.3 SGSC | strict3 5.89% / loose2 11.50% (V6) → strict3 0% / loose2 5.58% (V7.3) |
| §5.3 Per-model headline | V6 706 (Pub-size order) | V7.3 SGSC (TCC desc) | Δ(MAB−TCC) +6.7 / Δ(AC−TCC) +30.5 (V6) → −57.1 / −47.6 (V7.3) |
| §5.4 Ranking flip | V6 706 | V7.3 SGSC | Spearman ≈ −0.32 cross-substrate |
| §6 Discussion (substrate dep) | both | — | ALLM.H rank 9 → 5 |
| Appendix BSR table | both | — | Per-model BSR$_{\text{cond}}$ (Tables A, A′) |

---

## 6. 검증 (recompute & integrity)

### 6.1 V6 706 cross-check vs `auto_numbers_v6_706_with_allmh.tex`

| Macro | 값 (paper) | 본 보고서 (recomputed) | 일치 |
|---|---:|---:|---|
| `\vSevenThreeNHard` | 11,845 | 21,180 × 55.9% = 11,840 | ✓ (rounding) |
| `\vSevenThreePassMAB` | 50.8 | 50.78 | ✓ |
| `\vSevenThreePassAC` | 74.6 | 74.57 | ✓ |
| `\vSevenThreeBsrAC` | 61.8 | 61.75 | ✓ |
| `\vSevenThreeConsensusFAThreeWayRate` | 5.89 | 5.89 | ✓ |
| `\vSevenThreeFlipRate` | 55.9 | 55.92 | ✓ |
| `\vSevenThreeMABALLMH` | 33.6 | 33.62 | ✓ |
| `\vSevenThreeACALLMH` | 53.9 | 53.87 | ✓ |
| `\vSevenThreeCGAEvalALLMH` | 39.7 | 39.66 | ✓ |
| `\vSevenThreeHardALLMH` | 60.3 | 60.34 | ✓ |

모든 paper 매크로와 일치 — 본 표는 verdict_matrix에서 직접 재계산되었으며 오차는 표시 자릿수 round 내.

### 6.2 V7.3 SGSC 메타데이터 sanity

```
verdict_matrix_v7_3_with_allmh.json:
  metadata.n_episodes: 12540
  metadata.n_models:   10
  metadata.models:     {allm_h, deepseek_r1_7b, gemma31b, llama4scout, nemotron30b,
                        oss120b, qwen27b, qwen35b, qwen397b, qwen4b}
  hard_viol_definition: "v4_hard = OMISSION ∨ COMMISSION ∨ TIMING ∨ SEQUENCE 임계"
```

12,540 = 418 scenarios × 10 models × 3 runs. ALLM.H 1,254 episodes 100% mirrored.

### 6.3 Reproduce 명령

```bash
python3 - <<'PY'
import json
from pathlib import Path
from collections import defaultdict
for tag, path in [
    ("V6_706", "evidence_pack/analysis/verdict_matrix_v6_706_with_allmh.json"),
    ("V73_SGSC", "evidence_pack/analysis/verdict_matrix_v7_3_with_allmh.json"),
]:
    pe = json.loads(Path(path).read_text())["per_episode"]
    M = defaultdict(lambda: {"n":0,"ac":0,"mab":0,"c2":0,"tcc":0,"hard":0,
                              "ac_hard":0,"strict3":0,"loose2":0})
    for ep in pe:
        s = M[ep["model_dir"]]; s["n"] += 1
        h = bool(ep.get("v4_hard"))
        a = bool(ep.get("ac_proxy")); m = bool(ep.get("mab_proxy")); c = bool(ep.get("c2_pass"))
        s["hard"] += h; s["tcc"] += not h
        s["ac"] += a; s["mab"] += m; s["c2"] += c
        if a and h: s["ac_hard"] += 1
        if a and m and c and h: s["strict3"] += 1
        if a and c and h: s["loose2"] += 1
    print(tag, "models:", len(M))
    for model, s in sorted(M.items(), key=lambda kv: -kv[1]["tcc"]/kv[1]["n"]):
        n = s["n"]
        print(f"  {model:<18} TCC={100*s['tcc']/n:5.1f}  ASC={100*s['ac']/n:5.1f}  "
              f"MAB={100*s['mab']/n:5.1f}  BSR={100*s['ac_hard']/s['ac']:5.1f}  "
              f"strict3={100*s['strict3']/n:5.2f}  loose2={100*s['loose2']/n:5.2f}")
PY
```

---

## 7. Recommendation (paper authoring rules)

### 7.1 본문(main) — V6 706 사용 (현행 유지)

- Table~\ref{tab:evaluator_performance} → §2 Table A 구조 유지, ALLM.H 행 추가.
- Table~\ref{tab:headline_replay} → §2 Table B 구조 유지, ALLM.H 행 추가, Pub-size order로 정렬.
- 본문 구절: "9/10 models satisfy MAB > TCC" → **"8/10 models satisfy MAB > TCC after ALLM.H inclusion"**으로 갱신 (이전 9/9에서 ALLM.H 추가시 분모 변경 + ALLM.H Δ=−6.0pp가 새 예외).

### 7.2 Appendix \ref{app:bsr_table} — V7.3 SGSC 추가

- **신규 추가:** §3 Table A′/B′/C′ 그대로 appendix에 삽입.
- 캡션: *"Substrate-dependence stress test: identical evaluator definitions on SGSC V7.3 corpus reveal Δ sign reversal and rank shuffling."*
- 본문 §6 Discussion에서 cross-link: *"While the V6 corpus exhibits +6.7pp MAB over-credit (Table~\ref{tab:headline_replay}), the SGSC V7.3 corpus inverts this to −57.1pp (App.~\ref{app:bsr_table_v73}), confirming that the over-credit/under-credit direction is corpus-property-driven rather than scorer-fixed."*

### 7.3 ALLM.H disclosure 의무

- 본문/appendix 모두에서 ALLM.H 표기 시 **dual-substrate ranking 동시 게재** (V6 rank 9 / V7.3 rank 5).
- 단일-substrate "ALLM.H beats X" 주장 **전면 금지** (memo `project_allm_h_v73_deployment` 적용).

### 7.4 미해결 이슈

- **V7.3 strict3 = 0%**: 3-way consensus FA가 SGSC에서 무의미하므로 3-way headline은 V6 전용으로 확정. V7.3에서는 loose2 (ASC ∩ CwT) 만 paper-rep 가능.
- **MAB calibration 차이**: V7.3 expected_actions 평균 22.4개 vs V6 7.0개. Paper §App.D의 *"MAB-F1 ≥ 0.5 임계는 corpus-property에 의존"* 면책 문구 필요.
- **Spearman −0.32**: Bonferroni-adjusted significance test 미수행. cross-substrate ranking flip이 통계적으로 유의한지 부트스트랩 95% CI 첨부 필요 (`scripts/experiments/bootstrap_rank_correlation.py` 작성 예정).

---

## 8. Provenance

- **계산일:** 2026-05-06 04:15 UTC
- **계산 환경:** Python 3.13 / standard library only (no pandas)
- **결정성 (determinism):** verdict_matrix_v*.json은 pre-registered hash → 재계산시 bit-identical
- **commit:** working tree (eval_science branch, e9c34766 기점)
- **검증 필요시:** §6.3 reproduce 스니펫 실행

**End of report.**
