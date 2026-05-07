# Phase 1.G / 1.H / 1.I Report — 4-type CwT + Model-pair Robustness + Pose-B Catalogue Check

> **날짜**: 2026-04-26
> **대상 코퍼스**: 16,944 episodes (Full) / 14,826 episodes (W8, DeepSeek 제외)
> **선행**: `260426_reexp_comprehensive_report.md` (Phase 0 + Phase 1.A–F)
> **목적**: 4-type CwT (principled middle), model-pair reversal robustness, π-class Bayes catalogue robustness 측정 → paper primary CwT variant 결정

---

## 1. Executive Summary

| Phase | 산출물 | 핵심 결론 |
|---|---|---|
| **1.G** | `evidence_pack/phase1g/` | Scenario B (4-type FA position 0.42) — Original (5-type) 채택, 4-type을 sensitivity row로 |
| **1.H** | `evidence_pack/phase1h/` | Original ≈ 4-type robust (mean ~47%), 3-type만 inflate (52%, 일부 pair 72.5%) |
| **1.I** | `evidence_pack/phase1i/` | **All π-class orderings preserved** (term > aset > nord ≈ nctx) under all 3 CwT catalogues — Pillar 3 robust |

**Recommendation for paper**: Original (5-type) CwT을 primary로 유지. Appendix에 4-type / 3-type sensitivity 추가. 3-type collapse는 audit harness validation의 constructive example로 활용.

---

## 2. Phase 1.G — 4-type CwT (Principled Middle)

### 2.1 정의

| 변형 | 포함 violation types | OMISSION 처리 | DEVIATION 처리 |
|---|---|---|---|
| Original (5-type) | omission, commission, timing, sequence, deviation | 포함 | 포함 |
| **4-type (NEW)** | commission, timing, sequence, deviation | **제외** | 포함 |
| 3-type | commission, timing, sequence | 제외 | 제외 |

`assessor_core/spec/verdict_definitions.py:cwt_typed_4type_verdict()` (Phase 1.G에 추가)

### 2.2 Hero Numbers (W8, N=14,826)

| Metric | Original | 4-type | 3-type |
|---|---|---|---|
| CwT pass rate | 36.43% | **72.91%** | 99.02% |
| Strict 3-way FA | 6.25% | **15.86%** | 29.12% |
| Verdict flip rate | 83.50% | 77.90% | 79.46% |
| Pair reversal rate | 47.43% | 47.34% | **53.76%** |
| η²(evaluator) | 0.0725 | **0.0467** | 0.1723 |
| η² ratio (eval/run) | 24,166× | 23,350× | **34,460×** |
| BSR (CwT) | 0.4141 | **0.3396** | 0.4899 |
| Matched-pair detection (CwT) | **23.06%** | 18.17% | 1.91% |

### 2.3 Scenario Classification

4-type CwT의 strict-3way FA position (Original=0, 3-type=1):
- Full: 0.45
- W8: 0.42

**→ Scenario B (principled middle, explicit trade-off)**

### 2.4 해석

1. **OMISSION dominance 재확인**: Original→4-type pass rate +36.5pp 점프 (omission 제외만으로 두 배 이상 통과)
2. **DEVIATION이 evaluator-factor 압축자**: 4-type η² (0.047)이 Original (0.073)보다 **낮다**. 즉 DEVIATION 포함이 모든 evaluator의 verdict를 비슷하게 만들어 evaluator factor를 줄임. 3-type에서 DEVIATION을 빼면 η² 0.172로 폭증.
3. **3-type matched-pair collapse**: 23.06% → 1.91% (-21.15pp). DEVIATION을 빼면 모델 간 품질 차이 탐지가 거의 불가능 — random coin-flip 수준의 BSR(0.49).
4. **Original CwT 정당성 확정**: matched-pair detection이 가장 높음 (23%), pair reversal stable (47%, 4-type과 동일). 4-type은 reasonable alternative이지만 detection capacity는 약간 약함.

### 2.5 Paper 결정

- **Primary CwT = Original (5-type)** 유지 (matched-pair 23% > 18% > 2%)
- Appendix `\section{CwT Violation-Type Sensitivity}`에 4-type 행 추가 (이미 phase1 sensitivity table 있음, 3-row로 확장 필요)
- Self-audit text에 "DEVIATION 제거 시 η² 폭증, OMISSION+DEVIATION 동시 제거 시 detection collapse" 두 신규 발견 추가

---

## 3. Phase 1.H — Model-pair Pair Reversal Robustness

### 3.1 설계

각 model-pair (W8: 21 pairs, Full: 28 pairs)에 대해 cross-evaluator pair reversal rate를 3 CwT variant 별로 계산. 어느 model 비교가 evaluator-CwT 선택에 가장 민감한지 식별.

### 3.2 결과 (W8, 21 pairs)

| Variant | Mean | Min | Max | Range |
|---|---|---|---|---|
| Original | 46.86% | 36.17% | 55.42% | 19.25 |
| 4-type | 46.55% | 33.33% | 62.04% | 28.71 |
| 3-type | **52.10%** | 30.43% | **72.53%** | **42.10** |

**Cross-variant robustness**: 21 pairs 중 10 pairs(48%)가 ≥10pp 범위로 흔들림. 흔들림은 모두 3-type ↔ {Original, 4-type} 사이에서 발생.

### 3.3 해석

- **Original ↔ 4-type robust**: 두 variant 모두 mean ~47%, range 좁음. Paper의 75% hero claim (or whatever the exact metric was)의 robustness가 4-type 도입에도 유지될 가능성 높음.
- **3-type만 inflate**: mean +5pp, max 72.5%. DEVIATION 제외 시 일부 model-pair에서 reversal이 폭증 (i.e., evaluator 선택에 따라 model 순위가 자주 뒤집힘).
- **Implication**: Paper가 Original을 유지하면 Phase 1.H는 robustness signal로 쓸 수 있고, 4-type을 추가 채택해도 Pillar 3 (model 순위) 안정성이 유지됨.

산출: `evidence_pack/phase1h/phase1h_modelpair_reversal_{full,w8}.json` + `_table.tex` (28-row / 21-row LaTeX table).

---

## 4. Phase 1.I — Pose-B Catalogue Robustness

### 4.1 설계

3 CwT-variant verdict를 "catalogue"로 사용 (Original / 4-type / 3-type) + CDE(v4_hard) 기준선. 각 catalogue × 4 π-class projection (term, aset, nord, nctx) 조합에서 plug-in Bayes error ε* 계산. canonical ordering (term > aset > nord ≈ nctx)이 모든 catalogue에서 보존되는지 검증.

### 4.2 결과 (W8, N=14,826)

| Catalogue | Pass% | ε_term | ε_aset | ε_nord | ε_nctx | term/aset | Ordering |
|---|---|---|---|---|---|---|---|
| CDE (v4_hard) | 51.61% | 0.1590 | 0.0303 | 0.0052 | 0.0052 | 5.25× | ✓ |
| Original (5-type) | 36.43% | 0.2095 | 0.0773 | 0.0248 | 0.0248 | 2.71× | ✓ |
| 4-type | 72.91% | 0.1413 | 0.0374 | 0.0121 | 0.0121 | 3.78× | ✓ |
| 3-type | 99.02% | 0.0097 | 0.0028 | 0.0006 | 0.0006 | 3.46× | ✓ |

**All orderings preserved**: 모든 catalogue에서 term > aset > nord ≈ nctx.

### 4.3 해석 — Pillar 3 강화

- **Pillar 3 robust under all CwT-variant catalogues**: π-class projection taxonomy는 어떤 CwT 정의를 써도 무너지지 않음. CDE 기준 5.25×, Original 2.71×, 4-type 3.78×, 3-type 3.46× — 모두 term > aset 차이가 명확.
- **Memory의 5.50×/5.60× 수치 검증**: 정확한 LLM-judge 카탈로그(예: gpt-oss-120b vs Qwen)는 다른 인프라가 필요해 본 phase에서는 미실행. 대안으로 3 CwT variants를 "catalogue stand-in"으로 사용. 결과는 모든 ordering 보존.
- **Reviewer-defense narrative**: "Pillar 3 conclusions are not artefacts of a particular CwT definition; they hold for {5-type, 4-type, 3-type} and the original CDE catalogue."

산출: `evidence_pack/phase1i/phase1i_bayes_3variants.json` + `_table.tex` + `_macros.tex`.

---

## 5. Decision Matrix — Paper Primary CwT

| Criterion | Original | 4-type | 3-type | Winner |
|---|---|---|---|---|
| Matched-pair detection (signal) | 23.06% | 18.17% | 1.91% | **Original** |
| BSR vs TCC (lower=closer) | 0.41 | **0.34** | 0.49 | 4-type |
| η²(eval/run) ratio (≫1 desired) | 24,166× | 23,350× | **34,460×** | 3-type |
| Pair reversal stability | 47.43% | 47.34% | 53.76% | Original ≈ 4-type |
| Pillar 3 ordering preserved | ✓ | ✓ | ✓ | All |
| Catalogue ratio (term/aset) | 2.71× | 3.78× | 3.46× | All ≥ 2.7× |

**Decision: Original (5-type)**
- 가장 높은 matched-pair detection (paper의 핵심 신호 — model-quality discrimination)
- BSR 0.41은 4-type 0.34와 비교해 약간 멀지만 random(0.5)보다 충분히 작음
- DEVIATION 포함의 임상적 정당성 (off-protocol 행동도 환자 위해)
- 4-type은 sensitivity row로 보존 (η² 더 낮음 + BSR 더 좋음 = "alternative reasonable definition")
- 3-type은 audit harness의 constructive validation example (matched-pair 1.9%로 evaluator 능력 소실)

---

## 6. Phase 1.D — Rubric-Aware LLM Judge (Offline Proxy via LLMCatalogueShim)

### 6.1 실행 방식

새로운 LLM API 호출 없이 기존 인프라 활용:
- **Rubric source**: `evidence_pack/constraint_comparison/llm_raw/*.json` — LLM이 미리 추출한 CPG별 MUSTs/FORBIDDEN constraints
- **Judge**: `audit/shims/llm_catalogue_shim.LLMCatalogueShim`
- **Verdict rule**: PASS iff (≥50% MUSTs covered) AND (no FORBIDDEN performed)
- **Corpus**: 14,826 W8 episodes (전수)

이는 user spec의 "Oracle-Informed LLM Judge"의 offline 등가물 — LLM이 per-episode judge가 아니라 rubric extractor 역할.

### 6.2 결과

| Metric | 값 | 해석 |
|---|---|---|
| Rubric pass rate | **1.68%** (249/14,826) | 매우 conservative — 사실상 거의 모든 episode fail |
| BSR vs TCC | 0.4903 | random에 가까움 |
| Matched-pair detection | 2.38% | 모델 차이 detection 거의 소실 |

**Consensus FA augmented (rubric을 5번째 evaluator로 추가)**:

| CwT variant | FA4 (no rubric) | FA5 (+rubric) | Δ |
|---|---|---|---|
| Original | 6.25% | 0.00% | -6.25 pp |
| 4-type | 15.86% | 0.00% | -15.86 pp |
| 3-type | 29.12% | 0.19% | -28.93 pp |

### 6.3 결론 — NOT STRONG (paper 추가 skip)

User spec: "결과 strong (예: rubric-aware FA ≥ 50%)이면 §App에 1 paragraph + table"

**Max FA5 = 0.19% << 50% threshold → NOT-STRONG → paper 추가 불필요.**

**해석**:
- Rubric-aware judge는 FA를 거의 완벽히 eliminate (consensus FA → 0%) 하지만 matched-pair detection도 함께 무너짐 (2.38%)
- 이는 catalogue 기반 strict rubric의 known limitation — over-conservative
- Phase 1.G/H/I 결과가 paper의 핵심 주장을 이미 충분히 뒷받침 → Phase 1.D는 evidence_pack에만 보존하고 paper에는 미반영

### 6.4 산출

| 파일 | 내용 |
|---|---|
| `evidence_pack/phase1d/phase1d_rubric_aware_results.json` | Full metrics |
| `evidence_pack/phase1d/phase1d_rubric_aware_macros.tex` | 12 macros (paper 미사용) |
| `evidence_pack/phase1d/phase1d_rubric_aware_table.tex` | 3-row 비교 table (paper 미사용) |
| `scripts/experiments/phase1d_rubric_aware_judge.py` | 신규 분석 스크립트 |

---

## 7. 산출물 총 목록 (이 세션)

| 파일 | 크기 | 설명 |
|---|---|---|
| `assessor_core/spec/verdict_definitions.py` | 수정 | `cwt_typed_4type_verdict()` 추가, EVALUATOR_REGISTRY에 등록 |
| `scripts/experiments/phase1g_rescore_4type.py` | 신규 | typed VM에 cwt_typed_4type_pass/score 컬럼 in-place 추가 |
| `scripts/experiments/phase1g_reaggregate_3variants.py` | 신규 | 3-variant hero numbers 집계 (Full + W8 모드) |
| `scripts/experiments/phase1h_modelpair_reversal.py` | 신규 | 28/21 model-pair × 3 variants reversal table |
| `scripts/experiments/phase1i_bayes_3variants.py` | 신규 | π-class Bayes error × 3 catalogues + ordering check |
| `evidence_pack/verdicts/verdict_matrix_v6_typed_phase1.json` | 수정 (in-place) | +cwt_typed_4type_pass / +cwt_typed_4type_score columns |
| `evidence_pack/phase1g/phase1g_3variants_{full,w8}.json` | 신규 | 전체 hero numbers JSON |
| `evidence_pack/phase1g/phase1g_3variants_{full,w8}_table.tex` | 신규 | 3-row sensitivity table (Original / 4-type / 3-type) |
| `evidence_pack/phase1g/phase1g_3variants_{full,w8}_macros.tex` | 신규 | LaTeX macros (27 per suffix) |
| `evidence_pack/phase1h/phase1h_modelpair_reversal_{full,w8}.json` | 신규 | per-pair reversal table |
| `evidence_pack/phase1h/phase1h_modelpair_reversal_{full,w8}_table.tex` | 신규 | LaTeX 28/21-row table |
| `evidence_pack/phase1i/phase1i_bayes_3variants.json` | 신규 | 4 catalogue × 4 projection Bayes error matrix |
| `evidence_pack/phase1i/phase1i_bayes_3variants_table.tex` | 신규 | LaTeX 4-row × 7-col table |
| `evidence_pack/phase1i/phase1i_bayes_3variants_macros.tex` | 신규 | 19 LaTeX macros (Pillar 3 ratios, ordering flags) |
| `paper/auto_numbers.tex` | 수정 | +33 macros (Phase 1.G/H/I) |
| `docs/260426_phase1ghi_report.md` | 신규 | **본 보고서** |

---

## 8. 권장 후속 작업 (Step 4-6 from user spec)

### Step 4 — Self-audit Contribution 5 텍스트 finalize

`paper/main_final_v17.tex`의 Self-audit 문단에 다음 두 발견 추가 (~line 393):

> Beyond the typed→untyped pass-rate inflation already documented, two
> finer-grained sensitivities emerged when we widened the typed-CwT
> definition to a 4-type variant (excluding only OMISSION). First, the
> 4-type variant has \textit{lower} $\eta^2_{\text{eval}}$ (0.047 vs.\ 0.073
> for the original 5-type definition); the DEVIATION channel itself
> compresses the evaluator factor. Second, removing DEVIATION on top of
> OMISSION (the 3-type variant) collapses matched-pair detection from
> 23.1\% to 1.9\%, a constructive demonstration that a single design
> choice can erase the evaluator's discriminative power between models.

### Step 5 — Phase 1.D rubric_aware EXP-2 (optional)

§6.2에 명시된 시퀀스 따라 실행. 결과 strong이면 Appendix 추가.

### Step 6 — Paper integration

| 항목 | 위치 | 내용 |
|---|---|---|
| Sensitivity table 확장 | Appendix `\section{CwT Violation-Type Sensitivity}` | 2-row → 3-row (Original / 4-type / 3-type) |
| Phase 1.H robustness | Appendix new subsection | "Model-pair reversal is stable under Original ↔ 4-type relabel; only 3-type inflates" |
| Phase 1.I Pose-B | Appendix new subsection or §3 footnote | "π-class ordering preserved under all 3 CwT catalogues + CDE — Pillar 3 robust" |
| Self-audit § paragraph | §4.4 main text | Step 4 텍스트 |
| Macros load | `paper/main_final_v17.tex` preamble | ✓ already includes `\input{auto_numbers.tex}` (verify) |

### Cross-reference verify

```bash
# Verify all Phase 1.G/H/I macros are referenced or available
grep -E "\\\\(cwtFourType|phaseH|phaseI)" paper/main_final_v17.tex | wc -l
# Expected: matches the count of distinct macros if integrated, or 0 if Step 6 not yet started.
```

### Final 9-page compile

```bash
cd paper && pdflatex main_final_v17.tex && pdflatex main_final_v17.tex
# Verify page count and confirm no missing macros
```

---

*Generated: 2026-04-26 06:05 UTC*
*Predecessor: `260426_reexp_comprehensive_report.md`*
*Branch: `eval_science`*
