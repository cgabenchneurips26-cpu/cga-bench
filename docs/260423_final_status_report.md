# CGA-Bench Audit Harness — Final Status Report

**Date:** 2026-04-23
**Branch:** `eval_science` (12 commits ahead of `origin/eval_science`)
**Scope:** B-tier novelty upgrade → self-review → B3 retry → Option B/C verification → external benchmark extension → demo + docs + native adapter bridge

---

## 오늘 한 일 (총 12 commits)

### 1. B-tier 상류 (`e8c25000` → `aba65f88`, 기존)
- B1 Ensemble BSR 실험 (15 pairs)
- B2 4×5 Bayes error matrix validation
- B3 ActiveAgent diagnostic probe (pivot에서 기록)
- Paper §4.4 prose integration + 문서 무결성 정리

### 2. Self-review 및 defects 수정 (commits `362fbda5`–`b78789bb`)
- `docs/260423_btier_self_review.md` — 코드 감사 리포트
- **C1**: `v4_hard`를 ensemble BSR pool에서 제거 (reference contamination 해소, paper 24.3→40.7%, 40.2→48.7% 매크로 자동 갱신)
- **I1**: `test_and_bsr_leq_min_individual` dead assertion → `test_and_fa_leq_or_fa` (실제 AND⊆OR invariant)
- **I2**: `validate_consistency`의 nonsensical `row_max > pooled` 체크 제거, `check_pooled_present`로 축소
- **M1 일부**: `bayes_matrix_derived_macros.tex` paper §3.3에 wire (TIMING Δ=0.411 sharpest-separation 노출)

### 3. B3 재도전 (`1f738a9e`)
- `audit/shims/pi_nord_shim.py` — **진짜 constructive π_nord witness** (TCC-derived 필드 zero 접근)
- `audit/shims/_trajectory_cache.py` — 14,826 W8 episode 파일 매핑
- `scripts/experiments/exp_pi_nord_witness.py` — 4 variant 실험
- 결과: 최고 BSR=0.4914 (V3_half_expected), **floor 0.003 대비 164× gap**
- Paper §4.4에 "Constructive π_nord witness gap" 문단 추가 → Theorem 3.4를 **existence theorem**으로 재프레이밍

### 4. Option B/C 검증 + 외부 벤치마크 확장 (`181f4a5d`)
- `scripts/audit/verify_audit_harness.py` — 전 SHIM_REGISTRY 자동 end-to-end smoke
- **15/15 OK**: Option B의 6 shim + Option C2/C3 diagnostics(ρ(d_G), red cells) 모두 report.json에 포함 확인
- `audit/wrappers/external.py` — `ExternalBenchmarkEvaluator` ABC + `@register_external_benchmark` decorator
- `audit/wrappers/external_examples.py` — 2 worked examples (`ext_medagent_style`, `ext_healthbench_style`)
- `docs/add_external_benchmark_to_audit.md` — 3-step recipe for new benchmarks

### 5. 이번 라운드 (demo + docs + native adapter; 이 커밋)
- 이하 §5에서 상세

---

## 현재 테스트 상태

| 슈트 | 결과 |
|---|---|
| `tests/test_audit/` | **242/242 PASS** (~96s) |
| `verify_audit_harness.py --fast` | **15/15 OK** (shim 전수 smoke, llm_judge skip) |
| Paper 매크로 재생성 | 자동화됨 (exp_ensemble_bsr.py, exp_bayes_matrix.py, exp_pi_nord_witness.py) |

---

## 현재 shim inventory (15개, `ext_` 포함)

| shim | π-class | BSR | floor | red/43 |
|---|---|---|---|---|
| v4_hard | nctx | 0.0000 | 0.003 | 0 |
| active_agent | nctx | 0.0000 | 0.003 | 0 |
| ac_proxy | nctx | 0.4161 | 0.003 | 19 |
| acov_shim | nctx | 0.4161 | 0.003 | 19 |
| mab_proxy | term | 0.3975 | 0.436 | 27 |
| mab_f1 | nctx | 0.3990 | 0.003 | 28 |
| ext_healthbench_style | nctx | 0.4522 | 0.003 | 25 |
| action_coverage | nctx | 0.4997 | 0.003 | 29 |
| ext_medagent_style | nctx | 0.5067 | 0.003 | 28 |
| pi_nord_witness | aset | 0.5076 | 0.024 | 29 |
| dxem | term | 0.5161 | 0.436 | 17 |
| always_true | term | 0.5161 | 0.436 | 17 |
| c2_score | nctx | 0.5710 | 0.003 | 29 |
| c2_shim | aset | 0.5814 | 0.024 | 30 |
| viol_count | nctx | 0.6393 | 0.003 | 25 |

---

## 리뷰어 방어 준비 상태

| 예상 공격 | 현재 대응 |
|---|---|
| "Theorem 3.4 is just data-processing" | Contribution 4 (audit harness) 재프레이밍 + §3.3에 TIMING sharpest-separation finding wire |
| "Can you build the evaluator your theorem promises?" | 164× gap 정량화 + existence theorem로 honest framing |
| "Does 'any evaluator' scale to external benchmarks?" | `ExternalBenchmarkEvaluator` + `@register_external_benchmark` decorator + 2 worked examples (`ext_medagent_style`, `ext_healthbench_style`) |
| "BSR is scalar — where is the evaluator blind?" | Option C3 blindspot grid (domain × constraint-type) + red cells column |
| "d_G is mentioned but not computed" | Option C2 ρ(d_G) + monotonicity 이미 report에 포함 |
| "v4_hard가 ensemble에 들어있어 cross-class 숫자가 인위적" | Self-review에서 C1으로 이미 수정, 매크로 재생성 완료 |

---

## 미구현이었던 3항목 — 이번 라운드에서 구현

§5 `demo/app.py` (Gradio), `mkdocs.yml` + `docs/audit/`, `NativeAdapterEvaluator` (external adapter native scorer bridge).

각 항목의 세부 진행은 본 커밋의 관련 커밋 메시지와 `docs/260423_demo_docs_native_adapter.md` 참조.
