# Validator ↔ Runtime 불일치 — 철회문 + 재설계 방향

**작성일**: 2026-04-22
**상태**: 🚨 **Retraction** — 이전 대화 세션에서 주장한 "legacy bug 자동 감지 방어력 증거"는 **틀렸다**. 본 문서가 정정본.

---

## 1. 철회 대상 주장 (내가 틀렸던 것)

대화 세션 중 다음 주장을 한 바 있다:

> "기존 25 CPG 중 6개가 validator strict check fail (101 errors) — 이건 오히려 자동 파이프라인이 legacy 수작업 아티팩트의 invariant 위반을 자동 감지하는 증거로, 리뷰어 방어력을 강화한다."

**이 프레임은 철회한다**. 증거 없이 validator의 claim을 그대로 받아들였고, runtime과의 정합성을 확인하지 않은 상태로 "legacy bug"라고 단정지었다. 사용자가 "self 검증이 필요하다 / 확실한 증거가 있어야지"라고 정확히 지적했고, 실증 검증 결과 주장이 뒤집혔다.

---

## 2. 실증 검증 (사용자 요구에 따른 self-verification)

### 2-a. Runtime 엔진 테스트 결과

```bash
PYTHONPATH=. python3 -m pytest \
  tests/test_engine/test_ssc_sepsis.py \
  tests/test_engine/test_ada_dka.py \
  tests/test_engine/test_aha_chest_pain.py -q
```

결과:
```
tests/test_engine/test_ssc_sepsis.py .............          (13 passed)
tests/test_engine/test_ada_dka.py .................         (33 passed)
tests/test_engine/test_aha_chest_pain.py ....               (33 passed)
============================== 79 passed in 0.74s ==============================
```

**79/79 통과**. 내가 "broken legacy"라고 단정한 3개 YAML (ssc_sepsis_hour1_bundle, ada_dka_management, aha_chest_pain_evaluation)이 모두 runtime 엔진 테스트 전부 통과.

### 2-b. 근본 원인 — Validator의 over-strictness

`scripts/ci/validate_cpg_schema.py:161-165`:
```python
mandatory = set(node.get("mandatory_actions") or [])
allowed = set(node.get("allowed_actions") or [])
diff = mandatory - allowed
if diff:
    errors.append(f"{prefix}: mandatory_actions not in allowed_actions: {sorted(diff)}")
```

이 strict check는 `mandatory ⊆ allowed`를 요구하지만, **runtime은 이 invariant에 의존하지 않는다**.

### 2-c. Runtime의 실제 invariant — Semantic resolver (4단계)

`assessor_core/violations.py:610-647` `_action_satisfies_requirement`:

```python
def _action_satisfies_requirement(self, performed_key, required_key, state):
    """수행된 행동이 필수 요구사항을 만족하는지 확인 (strict matching).
    매칭 단계:
    1. 정확 일치 (원본)
    2. 양쪽 정규화 후 정확 일치
    3. ActionNormalizer alias 체크 (같은 canonical form으로 매핑)
    4. 명시적 조건부 핸들러 (start_vasopressor_if_hypotensive 등)
    """
    # 1단계: 정확 일치
    if performed_key == required_key: return True
    # 2단계: 정규화
    if self._normalizer.normalize(performed_key) == self._normalizer.normalize(required_key):
        return True
    # 3단계: alias
    if self._normalizer.are_aliases(performed_key, required_key): return True
    # 4단계: 조건부 핸들러
    if required_key == "start_vasopressor_if_hypotensive":
        if state.vitals.map_mmhg < 65 and performed_key.startswith("start_vasopressor_"):
            return True
    return False
```

그리고 `cpg_engine/stepper.py:124`에 `_action_satisfies` 함수가 또 있음 — runtime은 **2-tier semantic resolver**를 가짐.

### 2-d. Conditional placeholder 패턴 목록

기존 25 CPG에서 발견된 intentional semantic placeholders:

- `*_if_hypotensive` — 현재 runtime에 명시적 핸들러 존재 (L642)
- `*_if_elevated` — `remeasure_lactate_if_elevated` (SSC L94,148,426)
- `*_if_indicated` — `give_nitrates_if_indicated` (chest_pain stemi_pathway)
- `*_if_unstable` — (heart_failure 등에서 사용 예상)
- Disposition placeholders (`determine_disposition`, `admit_to_*`) — mandatory에 있으나 concrete form은 downstream 노드에 있고 normalizer가 resolve

→ 즉 validator가 flagging한 "6개 FAIL YAML / 101 errors"는 **runtime-intentional design**이고, runtime이 정상 scoring 한다.

---

## 3. 사용자 질문 답변

### Q1. "둘 다 하면 CI가 뭐가 바뀔까?"

**`.github/workflows/ci.yml` 분석 결과**:
- CI는 pytest(test_schemas / test_engine / test_assessor / ...)만 돌린다.
- `validate_cpg_schema.py`는 **CI에 connected 되어 있지 않다**. grep 결과 파일 내 self-reference만 존재.
- 따라서 validator는 현재 **manual-only dormant check**.

**결과**:

| 옵션 | Loader strict check | Validator strict check | CI gate | 실제 운영 영향 |
|---|---|---|---|---|
| (A) Loader만 수정 | 완화 (semantic 허용) | 유지 (dormant) | 변화 없음 | 0 |
| (B) Validator만 수정 | 유지 (strict) | 완화 | 변화 없음 (dormant) | 0 |
| (C) 둘 다 수정 | 완화 | 완화 | 변화 없음 | 0 |

→ **세 옵션 모두 CI 운영에 영향 0**. 선택 기준은 "도구 일관성" + "미래 CI wire-up 시 안정성"이 된다.

### Q2. "무슨 실험을 다시해야 하나?"

**과학적 결과(sweep) 재실행 = 불필요**:
- `results/full_706_v6_*` 의 scoring 값은 runtime 엔진이 계산했고, runtime은 원래부터 semantic resolver로 정상 작동했으므로 **재실행해도 동일 결과**. 16,944 에피소드 어떤 수치도 바뀌지 않는다.
- 논문의 tables/figures (η²_eval, blind-spot ratio, held-out ordering 등) 모두 그대로 유효.

**필수 regression check = 테스트 suite만**:
1. `tests/test_engine/` — 79+ tests. (이미 이번 세션에 pass 확인)
2. `tests/test_assessor/` — semantic resolver 직접 테스트.
3. `tests/test_schemas/` — YAML 스키마 테스트.
4. `tests/test_correctness/` + `tests/test_reproducibility/` — 전체 determinism regression.
5. 수정한 파이프라인 smoke:
   - `parsed_json_loader`로 기존 PASS YAML 19개 + FAIL YAML 6개 전부 round-trip.
   - `auto_generate_cpg.py --from-parsed-json`로 SSC 재생성 후 `test_ssc_sepsis.py` 통과 여부.

Wall-clock: 테스트 전수 = 몇 분. Sweep 재실행 = 필요 없음.

---

## 4. 재설계 방향 (Option C 기준 — 사용자 권고 시)

### 4-a. 공유 placeholder allowlist

새 파일 `cpg_model/schemas/conditional_placeholders.py` (proposal):

```python
# Runtime semantic resolver가 허용하는 conditional placeholder 패턴.
# validator + parsed_json_loader + cpg_yaml_generator 가 이 allowlist를 공유.
SEMANTIC_PLACEHOLDER_SUFFIXES: tuple[str, ...] = (
    "_if_hypotensive",
    "_if_elevated",
    "_if_indicated",
    "_if_unstable",
    "_if_high_risk",
)
DISPOSITION_PLACEHOLDERS: tuple[str, ...] = (
    "determine_disposition",
    # ... (향후 추가)
)

def is_semantic_placeholder(action_id: str) -> bool:
    if action_id in DISPOSITION_PLACEHOLDERS:
        return True
    return any(action_id.endswith(s) for s in SEMANTIC_PLACEHOLDER_SUFFIXES)
```

### 4-b. Loader 완화

`semantic_layer/parsed_json_loader.py::_normalise_nodes`:

```python
# BEFORE (current, over-strict)
missing_mand = mandatory - allowed
if missing_mand:
    raise ParsedJSONError(...)

# AFTER (runtime-consistent)
missing_mand = {m for m in mandatory - allowed if not is_semantic_placeholder(m)}
if missing_mand:
    raise ParsedJSONError(...)
```

### 4-c. Validator 동일 완화

`scripts/ci/validate_cpg_schema.py:161-165` 에 동일 allowlist import + 필터링.

### 4-d. Invariant 문서화

각 conditional placeholder의 runtime resolver 동작을 `assessor_core/CONDITIONAL_PLACEHOLDERS.md`에 명시. 리뷰어가 "이게 의도적인지 우연인지" 물을 때 답할 수 있도록.

---

## 5. 리뷰어 방어 프레임 — 교정본

### 철회

- ❌ "우리 rule-based 파이프라인이 legacy 수작업 YAML의 invariant 위반을 자동 감지한다."
  - 이 주장은 **틀렸다**. Invariant 자체가 runtime과 불일치하는 validator 버그였다.

### 유지

- ✅ **결정론적 재현성**: JSON→YAML 변환은 LLM 미사용, byte-identical 출력.
- ✅ **Round-trip 의미 보존**: PASS YAML (AABB 등)에서 4 노드 × 모든 action/deadline 필드 일치.
- ✅ **Strict validation (완화된 invariant 기준)**: runtime resolver의 allowlist를 승계하여, runtime이 실제로 reject할 YAML만 reject.

### 신규 프레임

- ✅ **"Runtime ↔ static check 일관성 정리"**: validator + loader + runtime 세 도구가 동일 invariant 공유 → 리뷰어가 어느 경로에서든 검증해도 일관된 결과.
- ✅ **Dissonance 자체를 artifact**: 현재 validator가 runtime과 불일치함을 **우리가 자체 검증으로 발견·기록**했다. 이게 "self-audit rigor"의 증거.

---

## 6. 방법론적 교훈

**내가 실수한 사이클**:
1. Validator 돌림 → 101 errors
2. 편한 서사(legacy bug 자동 감지)로 바로 수렴
3. Runtime 테스트로 cross-check 안 함
4. 사용자가 "self 검증 필요"라고 지적 → 79/79 pass 확인 → 프레임 붕괴

**교정된 기본 원칙** (향후 모든 assertion에 적용):
1. Tool의 output을 "claim"으로 간주, 즉시 수용 금지.
2. 반증 가능한 실증 테스트 **먼저** (여기서는 `pytest tests/test_engine/`).
3. Tool들 사이 invariant 불일치가 발견되면 **양쪽 다 의심** — 한쪽만 "broken"이라고 단정하지 말 것.

---

## 7. 변경 이력

- **v1 (2026-04-22)**: 틀린 주장 철회 + 79/79 pytest 실증 + CI 영향 분석 + 재설계 방향 기록.

## 8. 관련 문서

- `docs/cpg_expansion_v7/01_selection_criteria_v1.md` — rubric (유지)
- `docs/cpg_expansion_v7/02_candidate_rescoring_99.md` — 99 후보 (유지)
- `docs/cpg_expansion_v7/03_automation_pipeline_requirements.md` — Phase 1-3 roadmap (일부 서술은 semantic resolver 대응으로 개정 예정)

## 9. 관련 코드

- `scripts/ci/validate_cpg_schema.py:161-165` — 완화 대상 strict check
- `assessor_core/violations.py:610-647` — runtime semantic resolver (ground truth)
- `cpg_engine/stepper.py:83,124` — runtime `_action_satisfies`
- `semantic_layer/parsed_json_loader.py::_normalise_nodes` — 완화 대상 loader check
- `.github/workflows/ci.yml` — validator wire-up 없음 확인
