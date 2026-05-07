# Self-Review: B-tier 구현 코드 감사

**Date:** 2026-04-23
**Scope:** commits `e8c25000` (B-tier code), `91d88c60` (paper), `890a3839` (doc integrity), `aba65f88` (progress report)
**Reviewer:** self (opus 4.7, 1M context)

---

## 요약

| 항목 | 상태 |
|---|---|
| 테스트 | 17/17 PASS (pytest 실측, PYTHONPATH=.) |
| 기능 | 의도대로 동작, 결과 JSON/TeX 모두 생성됨 |
| **발견된 이슈** | **Critical 1건, Important 2건, Minor 3건** |

---

## Critical (반드시 수정)

### C1. v4_hard(TCC 레퍼런스)를 evaluator 풀에 포함시킨 순환 설계

- **파일:** `scripts/experiments/exp_ensemble_bsr.py:28`
  ```python
  CORE_SHIMS = ["dxem", "ac_proxy", "mab_proxy", "c2_shim", "acov_shim", "v4_hard"]
  ```
- **문제:** `audit/metrics/ensemble.py:73`에서 `ref = [get_verdict(eid, "v4_hard") ...]` — 즉 **v4_hard가 곧 레퍼런스**. 그런데 CORE_SHIMS에 v4_hard가 포함되어 있어 "evaluator vs 자기 자신"으로 `individual_bsr["v4_hard"] = 0.0`이 되고, AND(e, v4_hard)는 정의상 `e AND ref`라서 BSR이 tautologically 낮아짐.
- **결과 오염 정량:**
  - `best_and_pair = (dxem, v4_hard), BSR=0.0` — 완전 트리비얼 결과
  - same-class 4쌍 중 **2쌍이 v4_hard 포함** (ac_proxy×v4_hard=0.0793, acov_shim×v4_hard=0.0793). 이 두 값이 same-class 평균을 0.2431로 끌어내림.
  - v4_hard를 제외하면: same = (0.4161+0.3975)/2 = **0.407**, cross (v4_hard 포함 쌍 4개 제외) = **0.468** → 가설은 여전히 falsify되지만 격차가 훨씬 작음. 논문 내러티브 숫자 (24.3% vs 40.2%)는 오염된 값.
- **왜 중요:** 레퍼런스를 앙상블 멤버로 사용하는 건 방법론적으로 부적절. 리뷰어가 즉시 걸고 넘어질 지점.
- **수정:** `CORE_SHIMS`에서 `"v4_hard"` 제거, 또는 `ensemble_bsr_experiment`에서 `evaluators` 중 `name == "v4_hard"` 자동 배제. 후자가 안전.

---

## Important (릴리즈 전 수정)

### I1. dead assertion — 실질적으로 `assert True`인 테스트

- **파일:** `tests/test_audit/test_ensemble_bsr.py:181`
  ```python
  assert p["and_fa"] <= p["false_accept"] if "false_accept" in p else True
  ```
- **문제:** pair dict의 실제 key는 `and_fa`/`or_fa`뿐이고 `false_accept`는 없음. `"false_accept" in p`는 항상 `False` → 조건식이 `True`로 단락되어 **항상 통과**. 테스트 이름 `test_and_bsr_leq_min_individual`은 속성 검증을 약속하지만 커버리지 0.
- **수정:** `p["and_fa"] <= min(p["individual_bsr_a"]*n, p["individual_bsr_b"]*n)` 형태로 실제 속성을 테스트하거나, 테스트 제거.

### I2. false-positive 경고를 뿜는 validator

- **파일:** `scripts/experiments/exp_bayes_matrix.py:107-127` (`validate_consistency`)
- **문제:** `row_max > pooled` 를 경고로 올리는데, **같은 파일 주석(L122-124)에서 본인이 이 체크가 틀렸다고 명시**: "joint >= max(marginals) for independent coordinates is NOT guaranteed". 실제로 aset/nord/nctx 세 행 모두 경고 발생(`bayes_matrix_results.json:validation_issues`에 3건). 상관된 좌표에서는 joint가 marginal보다 작을 수 있는 게 정상이므로, 이 체크 자체가 넌센스.
- **결과 오염:** JSON 아티팩트에 항상 "실패한 validation" 3건이 기록됨. 후속 스크립트가 이 필드를 신뢰한다면 오탐 발생.
- **수정:** `validate_consistency` 함수를 삭제하거나, 체크 방향을 뒤집어 "joint ≤ min(marginals) + tolerance"로 재정의(이 역시 정보 공유 시 성립하지 않을 수 있음). 가장 안전한 건 **완전 제거**하고 "matrix shape/coverage" 체크만 남기는 것.

---

## Minor (개선 권장)

### M1. 생성했으나 논문에서 사용하지 않는 derived 매크로들

- `ensemble_bsr_macros.tex` 중 `\ensembleBestPairA/B`, `\ensembleBestAndBSR`, `\ensembleReduction`, `\ensembleBestIndividualBSR` — 모두 0.0/v4_hard 오염 산출물이라 논문이 참조하지 않음 (확인: `main_final_v17.tex`에 0건).
- `bayes_matrix_derived_macros.tex` 전체 13개 매크로(`\bayesErrRowMean*`, `\bayesErrColMean*`, `\bayesErrSharpest*`) 모두 **0건 참조**. 특히 "TIMING이 sharpest separator (Δ=0.411)"는 논문 헤드라인 finding인데 해당 매크로(`\bayesErrSharpestDrop`)가 paper에 하드코딩된 것으로 보임 → **traceability 깨짐**.
- **수정:** paper prose에서 해당 매크로를 실제로 `\input`하거나, 미사용 매크로 생성을 중단.

### M2. 테스트의 수동 monkeypatch 패턴

- **파일:** `tests/test_audit/test_ensemble_bsr.py:133-146, 164-176, 193-205, 219-232` — 4개 테스트에서 동일한 수동 save/restore 패턴:
  ```python
  original = mod.get_verdict
  mod.get_verdict = fake_get_verdict
  try: ... finally: mod.get_verdict = original
  ```
- **문제:** `test_active_agent_shim.py`는 `pytest.MonkeyPatch`를 올바르게 사용하는데, B1 테스트만 수동 처리. 테스트 중간 assert 실패 시 finally가 실행되지만, 여전히 장황하고 다른 파일과 스타일 불일치.
- **수정:** `monkeypatch: pytest.MonkeyPatch` fixture로 통일.

### M3. `ActiveAgentShim.verdict()`가 호출마다 `load_w8_episodes()` 재호출

- **파일:** `audit/shims/active_agent_shim.py:35`
- 싱글톤 캐시 덕분에 O(1)이지만, 논리적으로 깔끔하지 않음. `__init__`에서 한 번 로드하거나 class-level 캐시로 이동하면 `verdict`의 데이터 의존성이 명시적.
- **수정:** 기능 문제 아님. 스타일 개선 여지만 있음.

---

## 강점 (잘된 부분)

- **Evaluator 인터페이스 분리:** `audit/evaluator_base.py`의 ABC가 scorer-side 모듈(`assessor_core`, `cpg_engine`)과 isolated. isolation rule 준수.
- **결과 재현성:** 모든 실험이 JSON+TeX 쌍으로 저장되고 timestamp 포함 → paper traceability (`PAPER_TRACEABILITY.md` 철학과 일치).
- **ActiveAgent 설계:** TCC-derived임을 파일 docstring(L11-14)과 커밋 메시지 모두에 명시 → pi-class witness로 오용 방지.
- **가설 falsification을 숨기지 않고 기록:** `hypothesis_confirmed: false`를 JSON과 매크로에 그대로 노출 → 과학적 정직성. 이게 reframing의 근거.
- **테스트 커버리지:** `_bsr_from_verdicts` 단위 테스트 4종, consensus property 2종, integration 4종 — 대체로 견고.

---

## 결론

**Merge 가능 여부: 수정 후 가능 (With fixes)**

- **C1(v4_hard 오염)은 릴리즈 블로커**. 논문 숫자 24.3% vs 40.2%가 방법론적 비판에 그대로 노출됨. v4_hard 제거 후 재실행 필요 (결론 방향은 안 바뀜: falsification은 유지).
- I1, I2는 release 전 수정 권장.
- M1-M3는 camera-ready 전 정리.
- **기능 코드 자체의 버그는 없음** — 모두 "방법론/test-quality/dead-code" 이슈.

### 권장 수정 순서

1. `CORE_SHIMS`에서 `v4_hard` 제거 → 재실행 → 논문 매크로/문장 업데이트
2. `test_and_bsr_leq_min_individual` 재작성
3. `validate_consistency` 제거 (또는 shape 체크만 남기고 이름 변경)
4. (선택) derived 매크로 실제 paper 참조로 전환 또는 생성 중단
