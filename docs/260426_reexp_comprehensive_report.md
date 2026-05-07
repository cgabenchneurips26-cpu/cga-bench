# CGA-Bench Re-Experiment Protocol 종합 보고서

> **프로젝트**: CGA-Bench (Clinical Guideline Adherence Benchmark)
> **범위**: Phase 0 (Audit + Spec Freeze) + Data Cleanup + Phase 1 (Re-Scoring + Re-Aggregation + Paper Integration)
> **날짜**: 2026-04-26
> **기준 코퍼스**: 16,944 episodes (8 models × 706 scenarios × 3 runs)
> **W8 코퍼스**: 14,826 episodes (DeepSeek-R1-7B 제외, 7 models)

---

## 1. 배경 및 목적

CGA-Bench re-experiment protocol은 평가자 audit harness(§4.4, Contribution 4) 구축 과정에서 발견된 **evaluator definition ambiguity**를 해소하기 위한 체계적 재실험이다.

### 1.1 발견된 문제

| # | 문제 | 영향 |
|---|------|------|
| 1 | CwT verdict에 포함되는 violation type이 명시적으로 정의되지 않음 | 재현성 저해 |
| 2 | DxEM(TOM)이 100% constant → ANOVA에서 정보 없는 요인으로 작동 | η² 해석 오류 가능 |
| 3 | ACov ≡ AC-Proxy (tau=1.000) — 실질적 중복 | "6 evaluators" 표기의 정확성 |
| 4 | 논문 매크로 1,294개 중 Category B(verdict-dependent)의 정확한 범위 미파악 | 재계산 누락 위험 |

### 1.2 Protocol 구조

```
Phase 0: Audit + Specification Freeze
  ├─ D1: re_experiment_protocol_v1.md (공식 spec)
  ├─ D2: verdict_definitions.py (pure function)
  ├─ D3: 106 unit tests
  ├─ D4: auto_numbers_audit.csv (1,294 macro 분류)
  └─ D5: Git tag re-experiment-v1-spec-frozen

Data Cleanup: Archive + Organization
  ├─ 40+ legacy dirs → _archive/
  ├─ results/README.md (active data map)
  └─ Stale code reference fix

Phase 1: Re-Scoring + Re-Aggregation + Paper
  ├─ 1.A: Code changes (A1-A8)
  ├─ 1.B: Re-scoring (16,944 episodes)
  ├─ 1.C: Re-aggregation (hero numbers + sensitivity)
  ├─ 1.E: Verification (projection ordering + matched-pair)
  └─ 1.F: Paper integration (macros + appendix + main text)
```

---

## 2. Phase 0 — Audit + Specification Freeze

### 2.1 Evaluator 공식 정의 (6개)

| Evaluator | Family | Verdict Rule | Pi-class |
|-----------|--------|-------------|----------|
| DxEM (TOM) | Term-only | Always True (모든 에피소드 통과) | term |
| AC-Proxy (ASC) | Action Coverage | `action_coverage >= 0.5` | nctx |
| MAB-Proxy (PAF) | MAB F1 | `mab_f1 >= 0.5` | term |
| C2 (CwT) | Compliance Score | `c2_score >= 0.7` (모든 violation type 포함) | aset |
| ACov | Action Coverage | `action_coverage >= 0.5` (≡ ASC) | nctx |
| CGA-Bench (TCC) | Hard Violation | `v4_hard == False` (commission + timing + sequence 없음) | nctx |

### 2.2 Macro 감사 결과

| Category | 수량 | 설명 |
|----------|------|------|
| A (verdict-independent) | 78 | 아키텍처 수치 (graph 수, scenario 수 등) |
| B (verdict-dependent) | 1,166 | pass rate, FA, η², BSR 등 — Phase 1에서 sensitivity check |
| C (paper-text-only) | 50 | 서술 문구, reference 등 |

### 2.3 Phase 0 Residual Items (4건 모두 해결)

| # | 항목 | 해결 |
|---|------|------|
| 1 | η² computation path lock | `\cresFiveEtaSq{0.072}` — Path 4 확정 |
| 2 | OracleAgent generator script | `compute_oracle_per_domain.py` 재구성, 값 검증 |
| 3 | LLM-judge macro author-dependency | 16개 매크로 모두 author-independent 확인 |
| 4 | ASC pi-class paper framing | pi_nctx 정확 분류, disclosure 문단 작성 |

**Commit**: `52a789dc` (Phase 0.C final)

---

## 3. Data Cleanup — Archive + Organization

### 3.1 정리 결과

| 구분 | 항목 수 | 용량 | 설명 |
|------|---------|------|------|
| 삭제/이동 대상 | 40+ dirs/files | ~220 MB | Legacy code, old results, discarded runs |
| 유지 (active) | 10 dirs | ~2.9 GB | Canonical corpus + active experiments |

### 3.2 Archive 대상 (주요)

| 디렉토리 | 이유 |
|-----------|------|
| `clinician_study/`, `clinician_survey/` | v3 `clinician_validation/`으로 대체됨 |
| `code_verification/` | One-off verification (evidence_pack에 결과 보존) |
| `analysis/cres9/` | CRES 결과 evidence_pack에 이미 보존 |
| `encoding_audit/human/` | Human annotation 자료 (별도 보관) |
| `constraints/`, `guidelines/`, `index/` | Legacy scoring infra (v5+ 미사용) |
| `paper_sections/` | Old paper structure (현재 main_final_v17.tex 단일 파일) |
| `results/` 30+ dirs | DISCARDED, dryrun, smoke, debug, pre-v5 runs |
| `cpg_model/graphs/auto/` 30 files | Auto-v2 expansion (expansion_v7로 대체) |
| `configs/scenarios/auto_v2/` 30 files | Auto-v2 scenarios (expansion_v7로 대체) |
| `evidence_pack/analysis/verdict_matrix_v4.json` | v6으로 대체 (297K lines, 미참조) |

### 3.3 Active Data (유지)

| 디렉토리 | 용량 | 용도 |
|-----------|------|------|
| `results/full_706_v5/` | 456M | **Canonical** 16,944 episode corpus |
| `results/full_706_v6_aliasfix_*/` | 288M | v6 ReAct scaffold re-sweep |
| `results/full_706_v6_scaffolds_*/` | 805M | v6 multi-scaffold (checklist + direct) |
| `results/ex_w8_crossmodel_v5/` | 275M | W8 scaffold independence study |
| `results/expansion_v7/` | 141M+ | CPG expansion (942 scenarios) |
| `results/heldout_v1/` | 20M | Held-out domain analysis |

---

## 4. Phase 1 — Re-Experiment 결과

### 4.1 Code Changes (A1-A8) 요약

| Task | 파일 | 내용 |
|------|------|------|
| A1 | `verdict_definitions.py` | `cwt_typed_verdict()`: OMISSION/DEVIATION 제외, threshold 0.7 |
| A4 | `verdict_definitions.py` | `dg_typed_cost()`: weights {commission:1.0, timing:0.5, sequence:0.6} |
| A5 | `auto_numbers.tex` | `\dxemPassRate{100.0}` 수정, `\normalizerMMEpisodes` fix |
| A6 | `main_final_v17.tex` | Self-audit Contribution 5 (§4.4 확장) |
| A7 | `main_final_v17.tex` | ASC pi-class footnote (§3 Theorem 1 영역) |
| A2 | Paper text only | ACov "5 effective evaluators" 명시 (β 결정) |
| A3 | 검증만 | DxEM ANOVA 제외 — 이미 Path 4에서 적용 확인 |
| A8 | 검증만 | 25.1% guard comment — Phase 0.C에서 이미 완료 |

### 4.2 Re-Scoring (B1-B3) — 16,944 Episodes

```
Input:  evidence_pack/analysis/verdict_matrix_v6.json
        results/full_706_v5/ (raw episodes)
Output: evidence_pack/verdicts/verdict_matrix_v6_typed_phase1.json (10.8 MB)
        evidence_pack/dg/dg_typed_v1.parquet (225 KB)
```

| 항목 | 값 |
|------|-----|
| 매칭된 에피소드 | 16,944 / 16,944 (0 unmatched) |
| Verdict 변경 수 | 10,751 (63.5%) |
| CwT-typed pass 분포 | min=0.500, median=0.968, max=1.000 |
| dg_typed > 0 에피소드 | 8,553 (50.5%) |

### 4.3 Evaluator Verdict Matrix

| Evaluator | Pass Rate | v4_hard in Pass | Mis-cert | False Accept |
|-----------|-----------|-----------------|----------|--------------|
| DxEM (TOM) | 100.0% | 8,553 | 50.5% | 8,553 |
| AC-Proxy (ASC) | 74.4% | 7,202 | 57.1% | 7,202 |
| MAB-Proxy (PAF) | 53.0% | 5,406 | 60.3% | 5,406 |
| C2 (CwT) | 35.6% | 2,372 | 39.3% | 2,372 |
| ACov | 74.4% | 7,202 | 57.1% | 7,202 |
| **CGA-Bench (TCC)** | **49.5%** | **0** | **0.0%** | **0** |

### 4.4 Model별 성능

| Model | v4_hard | AC Pass | MAB Pass | C2 Pass | CGA Pass |
|-------|---------|---------|----------|---------|----------|
| oss120b | 53.7% | 85.4% | 50.2% | 40.4% | 46.3% |
| qwen397b | 54.6% | 82.9% | 59.4% | 37.4% | 45.4% |
| qwen35b | 47.3% | 83.5% | 53.6% | 39.4% | 52.7% |
| qwen27b | 55.3% | 79.1% | 56.8% | 39.9% | 44.7% |
| gemma31b | 40.2% | 74.2% | 57.5% | 43.3% | 59.8% |
| nemotron30b | 44.0% | 56.9% | 49.0% | 22.4% | 56.0% |
| qwen4b | 43.7% | 56.9% | 50.9% | 32.1% | 56.3% |
| deepseek_r1_7b | 65.1% | 76.4% | 46.2% | 30.1% | 34.9% |

**관찰**: CGA-Bench(TCC) pass rate는 모델 크기와 단순 비례하지 않음 — gemma31b(59.8%)이 oss120b(46.3%)보다 높음. 이는 모델별 violation pattern 차이를 반영.

---

## 5. CwT Violation-Type Sensitivity Analysis (핵심 실험)

### 5.1 실험 설계

- **Original CwT**: 5종 violation 모두 포함 (omission, commission, timing, sequence, deviation)
- **Typed CwT**: 3종만 포함 (commission, timing, sequence) — omission + deviation 제외
- **Threshold**: 둘 다 0.7

### 5.2 전체 코퍼스 결과 (N=16,944)

| Metric | Original | Typed | Delta | Rel.% |
|--------|----------|-------|-------|-------|
| CwT pass rate | 35.64% | 99.03% | **+63.39 pp** | +177.9% |
| Strict 3-way FA | 6.60% | 29.82% | **+23.22 pp** | +351.8% |
| Verdict flip rate | 84.04% | 80.78% | -3.26 pp | -3.9% |
| Pair reversal | 46.31% | 53.43% | +7.12 pp | +15.4% |
| η²(evaluator) | 0.0775 | 0.1832 | **+0.1057** | +136.4% |
| CwT BSR | 0.4202 | 0.4904 | +0.07 | +16.7% |
| CwT matched-pair | 23.87% | 1.90% | **-21.97 pp** | -92.0% |

### 5.3 W8 필터링 결과 (N=14,826)

| Metric | Original | Typed | Delta | Rel.% |
|--------|----------|-------|-------|-------|
| CwT pass rate | 36.43% | 99.02% | **+62.59 pp** | +171.8% |
| Strict 3-way FA | 6.25% | 29.12% | **+22.87 pp** | +365.9% |
| Verdict flip rate | 83.50% | 79.46% | -4.04 pp | -4.8% |
| Pair reversal | 47.43% | 53.76% | +6.33 pp | +13.3% |
| η²(evaluator) | 0.0725 | 0.1723 | **+0.0998** | +137.7% |
| CwT BSR | 0.4141 | 0.4899 | +0.08 | +18.3% |
| CwT matched-pair | 23.06% | 1.91% | **-21.15 pp** | -91.7% |

### 5.4 BSR per Evaluator (W8)

| Evaluator | Original | Typed | 해석 |
|-----------|----------|-------|------|
| ASC (pi_nctx) | 0.5918 | 0.5918 | 변화 없음 |
| PAF (pi_term) | 0.6038 | 0.6038 | 변화 없음 |
| **CwT (pi_aset)** | **0.4141** | **0.4899** | **→ random** |
| TOM (pi_term) | 0.5000 | 0.5000 | 변화 없음 (constant) |

CwT만 영향 받음. BSR 0.49 ≈ 동전 던지기 — typed CwT는 TCC와의 분별력을 상실.

### 5.5 Matched-Pair Detection (W8)

| Evaluator | Original | Typed | 해석 |
|-----------|----------|-------|------|
| ASC | 17.02% | 17.02% | 변화 없음 |
| PAF | 19.72% | 19.72% | 변화 없음 |
| **CwT** | **23.06%** | **1.91%** | **탐지 능력 소멸** |
| TCC | 16.64% | 16.64% | 변화 없음 |

---

## 6. 해석 및 시사점

### 6.1 Omission Dominance 확정

Phase 1의 핵심 발견은 **omission이 CwT 판별력의 거의 전부**를 구성한다는 것이다:

1. Omission 제외 시 pass rate 36% → 99% (사실상 모든 에피소드 통과)
2. Matched-pair detection 23% → 2% (모델 간 품질 차이 탐지 불가)
3. BSR 0.41 → 0.49 (TCC 기준 대비 random 수준)

**메커니즘**: 현재 LLM 에이전트의 주된 실패 모드는 "위험한 행동(commission)"이 아니라 **"필수 행동 누락(omission)"**이다. 에이전트가 아무것도 하지 않거나 일부만 수행 → omission 위반 대량 발생 → CwT FAIL. Commission/timing/sequence만으로는 에이전트를 구별할 수 없다.

### 6.2 원래 CwT의 정당성

| 관점 | 근거 |
|------|------|
| **임상적** | 패혈증에서 1시간 내 항생제 미투여 = 환자 사망률 증가 — omission은 실제 해악 |
| **통계적** | Omission 포함 CwT만이 의미 있는 BSR(0.41)과 matched-pair detection(23%) 제공 |
| **벤치마크적** | 평가자 간 불일치(flip rate 83.5%)가 "evaluator choice matters" 주장의 근거 |

### 6.3 Audit Harness Validation

단일 설계 선택(violation-type inclusion)이 η²(evaluator)를 **2.4배 팽창**(0.0725→0.1723)시킬 수 있음을 constructively 입증. 이것이 정확히 audit harness(§4.4)가 탐지하도록 설계된 병리(pathology)이며, **"evaluator definition이 결과를 지배한다"**는 CGA-Bench의 핵심 주장을 강화.

### 6.4 선행 연구와의 연결

| 선행 발견 | Phase 1 확인 |
|-----------|-------------|
| B3 omission dominance (n_viols=0 → 7,651 fails) | 10,751/16,944 verdict 변경 = 63.5% |
| Pi-class separation (same-class tau=0.47 vs cross=0.19) | CwT typed → pi_aset 구조 파괴 (BSR → random) |
| DxEM constant (100% True) | 여전히 100% — 영향 없음 확인 |
| Blindspot grid (domain × constraint heatmap) | Omission이 모든 domain에서 지배적 |

---

## 7. Paper 변경 사항

### 7.1 신규 LaTeX 매크로 (17개, `auto_numbers.tex`)

Phase 1 W8-filtered hero numbers — `\cwtOrigPass`, `\cwtTypedPass`, `\cwtTypedDeltaPP`, `\cwtOrigFA`, `\cwtTypedFA`, `\cwtTypedFADelta`, `\cwtOrigFlip`, `\cwtTypedFlip`, `\cwtOrigEtaEval`, `\cwtTypedEtaEval`, `\cwtOrigBSR`, `\cwtTypedBSR`, `\cwtOrigDetection`, `\cwtTypedDetection`, `\cwtTypedNChanged`, `\cwtTypedChangedPct`

### 7.2 Appendix 추가

`\section{CwT Violation-Type Sensitivity Analysis}` (`\label{app:cwt_correction}`)
- Protocol, Results, Interpretation, Implication 4개 문단

### 7.3 Main Text 수정

Self-audit 문단(~line 393)에 typed CwT → η² inflation constructive example 참조 추가.

---

## 8. 결정 사항 기록 (IV.1–IV.4)

| # | 결정 | 선택 | 근거 |
|---|------|------|------|
| IV.1 | ACov 처리 | **β — backward-compat 유지** | 변경 비용 최소, "5 effective" 명시 |
| IV.2 | EXP-2 depth | **α — rubric_aware만** | 결과 strong이면 cot_judge 추가 |
| IV.3 | Sensitivity depth | **Hero + secondary (~25-30)** | Full table은 appendix에 배치 |
| IV.4 | Pre-registration | **Internal git tag** | Reviewer 요청 시 camera-ready에서 arXiv/OSF 추가 |

---

## 9. 산출물 총 목록

### 9.1 Phase 0 산출물

| 파일 | 설명 |
|------|------|
| `docs/re_experiment_protocol_v1.md` | 공식 specification |
| `assessor_core/spec/verdict_definitions.py` | Pure function 정의 (기존 + cwt_typed + dg_typed) |
| `tests/test_verdict_definitions.py` | 106 단위 테스트 |
| `auto_numbers_audit.csv` | 1,294 macro 분류 |
| `docs/260426_phase0_spec_freeze_report.md` | Phase 0 보고서 |
| `docs/260426_phase0c_final_report.md` | Phase 0.C 잔여 항목 보고서 |

### 9.2 Phase 1 산출물

| 파일 | 크기 | 설명 |
|------|------|------|
| `evidence_pack/verdicts/verdict_matrix_v6_typed_phase1.json` | 10.8 MB | 16,944 ep, typed verdict 포함 |
| `evidence_pack/dg/dg_typed_v1.parquet` | 225 KB | dg_typed cost per episode |
| `evidence_pack/phase1/phase1_sensitivity.json` | 4.6 KB | 전체 코퍼스 hero numbers |
| `evidence_pack/phase1/phase1_sensitivity_w8.json` | 4.6 KB | W8 hero numbers |
| `evidence_pack/phase1/phase1_sensitivity_macros.tex` | 1.6 KB | 전체 코퍼스 LaTeX 매크로 |
| `evidence_pack/phase1/phase1_sensitivity_w8_macros.tex` | 1.6 KB | W8 LaTeX 매크로 |
| `evidence_pack/phase1/phase1_sensitivity_table.tex` | 1.1 KB | Sensitivity booktabs table |
| `scripts/experiments/phase1_rescore.py` | — | B1+B2 재채점 스크립트 |
| `scripts/experiments/phase1_reaggregate.py` | — | C1+C3+E1+E2 재집계 스크립트 |
| `paper/auto_numbers.tex` | +17 macros | Phase 1 W8 hero numbers |
| `paper/appendix.tex` | +1 section | CwT correction appendix |
| `paper/main_final_v17.tex` | +1 paragraph | Self-audit typed CwT 참조 |
| `docs/260426_phase1_analysis_report.md` | — | Phase 1 상세 분석 보고서 |
| `docs/260426_reexp_comprehensive_report.md` | — | **본 종합 보고서** |

---

## 10. 미완료 항목 및 다음 단계

| 항목 | 우선도 | 상태 | 비고 |
|------|--------|------|------|
| Phase 1.D (EXP-2 LLM Judge) | P1 | NOT STARTED | rubric_aware prompt, 1000-2000 ep 샘플 |
| Pose B re-execution (C2) | P2 | SKIPPED | 3 catalogues × typed CwT — 핵심 결과에 영향 없음 |
| Bayes matrix with typed CwT | P2 | DEFERRED | B2 matrix 재계산 — camera-ready |
| Git tag `re-experiment-v1-phase1-complete` | P0 | PENDING | 커밋 후 태깅 |

---

## 11. Reproducibility

```bash
# 전제: PYTHONPATH 설정 (assessor_core의 cga_bench.* import 해결)
export PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject:/home/anonymous-org/anonymous-project/AnonProject/cga_bench

# Phase 1.B: Re-scoring (16,944 episodes)
python scripts/experiments/phase1_rescore.py

# Phase 1.C: Re-aggregation (전체 코퍼스)
python scripts/experiments/phase1_reaggregate.py

# Phase 1.C: Re-aggregation (W8 필터링)
python scripts/experiments/phase1_reaggregate.py --w8

# Tests (106개 verdict definition tests)
PYTHONPATH=. pytest tests/test_verdict_definitions.py -v

# Full test suite
PYTHONPATH=. pytest tests/ -v
```

---

*Generated: 2026-04-26 06:00 UTC*
*Git branch: eval_science*
*Predecessor: Phase 0 commit `52a789dc`*
