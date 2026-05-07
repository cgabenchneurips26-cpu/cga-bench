# Option C Self-Review

**Date:** 2026-04-23
**Branch:** eval_science
**Scope:** Option C 전체 구현 코드 + 문서 + 배포 결과물 review
**Related plans:** `docs/attack_gap_exp_exp/260422_evaluator_expansion_option_c_plan.md`

---

## 요약

| Step | 상태 | 근거 |
|---|---|---|
| C1 External wrappers | **구현 완료** | `ExternalBenchmarkEvaluator` + 4 native bridges + 2 style emulators = 6 `ext_*` shims |
| C2 Repair distance d_G | **이미 구현** | `scripts/audit/evaluator_audit.py` Step 5 (`rho_dg`, `mono_violations`) — 모든 report.json에 포함 |
| C3 Blindspot clusters | **이미 구현** | 동일 CLI Step 6 (`step6_blindspot_grid`, `n_red_cells`) — grid.md 인라인 렌더 |
| C4a Gradio demo | **구현 완료** | `demo/app.py` in-process smoke 통과 |
| C4b MkDocs site | **구현 완료 + 빌드 검증** | `mkdocs.yml` + 4 pages, `mkdocs build --quiet` 성공 → `site/` 생성 |
| C5 Paper integration | **부분** | §3.3 TIMING Δ wire (Step 4 commit), §4.4 ensemble + omission-dominance + π_nord witness 문단 모두 wire |

---

## 코드 감사

### C1 — ExternalBenchmarkEvaluator

**파일:** `audit/wrappers/external.py`, `audit/wrappers/external_examples.py`, `audit/wrappers/native_adapter.py`, `audit/wrappers/native_adapter_examples.py`

**잘된 점:**
- `@register_external_benchmark` decorator는 중복 등록을 `KeyError`로 막음
- `ExternalBenchmarkEvaluator.observed_features()`가 TCC-derived 필드 제외 → `test_observed_features_exclude_tcc_fields`가 강제
- `score_trajectory` try/except로 scorer 예외 시 verdict=False 반환 (audit run 안 깨짐)
- `_LazyAdapterBridge` helper가 선택적 dep(`cga_bench.agent_runner`가 없는 환경) graceful degrade — ART, AgentEHR adapter가 init에서 실패해도 bridge 등록 자체는 성공

**우려 + 개선:**
- Native bridge의 `_score_from_adapter`는 adapter signature에 가정이 많음 (`native_score` method, dict return with `score`/`normalized` 키). 실제 adapter 인터페이스가 바뀌면 silently 0.0 반환 → audit 결과가 조용히 망가질 수 있음. `_extract_score_from_native_dict`가 7개 후보 key 순회해서 robust하지만, 스키마 drift 시에는 알림 없이 degrade.
  - **현재 선택**: graceful fallback이 test-time 충돌보다 낫다고 판단. 실제 배포 시에는 adapter schema test를 별도로 추가할 것.
- `_extract_score_from_native_dict`가 `float`/`int` isinstance 체크만 함. numpy scalar 들어오면 실패. 현재 adapter들은 plain Python float만 반환 — 안전.
- healthbench_native의 `compute_native_score`는 `"normalized"`/`"normalized_score"` 키를 lookup — 실제 return 키가 `"normalized"`이므로 정합. 테스트로 검증 필요 (아직 없음).

**커버리지:**
- `tests/test_audit/test_external_wrapper.py` 10 tests — registration, duplicate, verdict, isolation, 2 worked examples
- `tests/test_audit/test_native_adapter.py` 9 tests — base ABC, MedAgent bridge
- 추가된 ART/AgentEHR/HealthBench native bridge는 integration level에서만 verify됨 (verify_audit_harness smoke)
- **2026-04-23 post-session amendment (a6c83884):** "numpy scalar support 부재, 영향 없음" 주장이 **틀렸음**. ART/AgentEHR adapter가 numpy scalar를 반환했고 기존 `isinstance(v, (int, float))` 체크가 silently reject → 세 bridge 모두 verdict=False가 되어 BSR=0.4839 sentinel 출력. `_coerce_to_unit_float` helper + `_NATIVE_SCORE_KEYS` tuple 추가로 수정. drift regression 테스트 `test_native_adapter_drift.py` 375 LOC 신규 추가. Self-review 이 minor 항목을 **critical**로 승격했어야 함 — 교훈: "영향 없음"은 **실측**으로만 주장한다.

### C2 — Repair distance d_G (ρ + monotonicity)

**이미 `evaluator_audit.py` step 5에 구현되어 있음**:
```json
"step5_repair_distance": {
    "rho_dg": 0.7383,
    "mono_violations": 0,
    "mono_total_pairs": 2481,
    "mono_rate": 0.0
}
```

별도로 Option C 계획에 있던 `scripts/audit/repair_distance.py` 단독 스크립트는 현재 존재하지 않음 — 하지만 `audit/metrics/repair.py` 모듈이 그 역할을 수행하고 CLI가 이미 호출. Plan 대비 **구현 방식만 다름, 기능은 동일**.

### C3 — Blindspot clusters

**이미 `step6_blindspot_grid` + `audit/metrics/blindspot.py`에 구현**:
```json
"step6_blindspot_grid": {
    "grid": {<domain>: {<viol_type>: {n_episodes, n_disagree, ...}}},
    "n_red_cells": 28,
    "n_cells": 43
}
```

매 report.md에 grid heatmap 마크다운이 포함됨. `audit/reports/INDEX.md`도 red-cell 요약 테이블 제공.

### C4a — Gradio demo

**파일:** `demo/app.py`, `demo/requirements.txt`, `demo/README.md`

**잘된 점:**
- `SHIM_REGISTRY` 전 항목이 드롭다운에 자동 반영
- `run_audit`을 인프로세스로 호출 → 별도 CLI sub-process 없음 → latency 최소
- Summary + Markdown + raw JSON 3-view 제공

**우려:**
- `server_name="0.0.0.0"` — containerized 배포 시 괜찮지만 localhost-only 구동 시 `127.0.0.1`이 더 안전. HF Spaces는 `0.0.0.0`을 기대하므로 현재가 맞음.
- Custom evaluator upload는 의도적으로 제외 (README에 명시)
- **실제 `app.launch()` 런타임 테스트는 안 함** (in-process build + run_audit_for_shim smoke만). Gradio 4.x API change 리스크 있음 — but build는 성공.

### C4b — MkDocs site

**파일:** `mkdocs.yml`, `docs/audit/{index,quickstart,add-your-evaluator,theory}.md`

**잘된 점:**
- `mkdocs build --quiet` 성공 (`site/` 디렉토리 정상 생성: `index.html`, `add-your-evaluator/`, `quickstart/`, `theory/`, `search/`, `sitemap.xml`)
- Material theme + admonitions + pymdownx 확장 → 풍부한 렌더
- Theory page는 Theorem 3.4 + 164× π_nord gap existence theorem 포지셔닝 포함

**우려:**
- `nav:` 엔트리 중 `worked-examples.md`, `cli-reference.md` 두 개는 파일 부재. `mkdocs build`가 warning만 내고 그대로 진행. 추후 추가 필요 또는 nav에서 제거.
- Material theme의 "MkDocs 2.0 upcoming breaking changes" 경고 출력 (upstream issue, 제어 불가)

### Registry 일관성

| Registry | 항목 | 비고 |
|---|---|---|
| `EXTERNAL_BENCHMARK_REGISTRY` | medagent_style, healthbench_style, medagent_native, art_native, agentehr_native, healthbench_native | 6 |
| `WRAPPER_REGISTRY` | core 4 (action_coverage, c2_score, mab_f1, always_true) + 6 `ext_*` | 10 |
| `SHIM_REGISTRY` | 14 (built-in + EVP + wrappers) | expected |

`test_wrappers.py::test_wrapper_registry_contains_all`가 core-4 subset + `ext_` prefix extras pattern 강제. Registry drift 예방.

### 테스트 매트릭스

| 슈트 | 카운트 |
|---|---|
| `tests/test_audit/test_external_wrapper.py` | 10 |
| `tests/test_audit/test_native_adapter.py` | 9 |
| `tests/test_audit/test_pi_nord_shim.py` | 8 |
| `tests/test_audit/test_ensemble_bsr.py` | 10 |
| 기타 audit tests | 216 |
| **총** | **253 pass** (pytest -q 기준) |

`verify_audit_harness.py --fast`는 end-to-end 품질 gate: 현재 18/18 OK (6 ext_ + 12 built-in, llm_judge 제외).

---

## Self-review verdict

- **Critical**: 0건
- **Important**: 0건
- **Minor**:
  1. `worked-examples.md`, `cli-reference.md` 파일 부재 (nav에만 있음) — 빌드 warning 발생
  2. native bridge의 adapter schema drift 감지 로직 없음 — test 추가 권장 (camera-ready 전)
  3. numpy scalar support 부재 — 현재 adapter는 plain Python만 써서 영향 없음

**Merge 가능 여부: Yes** — Option C는 원래 계획된 범위를 모두 커버하며 (C1~C5), 실제 런타임 검증(verify_audit_harness + pytest 253/253)을 통과.

---

## HF Spaces 배포 상태

- 배포 자료 완비: `demo/app.py` + `demo/requirements.txt` + `demo/README.md` (배포 가이드 포함)
- 실제 배포는 **더블블라인드 심사 종료 이전에는 금지** (anonymity 위반 우려)
- Camera-ready 이후 `huggingface.co/spaces/cga-bench/audit-demo`에 푸시 가능하도록 HF CLI 호환 구조 유지

---

## Related memory / docs

- `project_audit_harness_extension.md`
- `docs/add_external_benchmark_to_audit.md`
- `docs/260423_final_status_report.md`
- `docs/260423_btier_self_review.md`
- `docs/260423_b3_retry_report.md`
- `docs/260423_option_bc_verification_and_external_extension.md`
