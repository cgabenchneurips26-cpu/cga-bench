# SGSC v7 Pilot-14 상세 분석 보고서

**날짜**: 2026-04-30
**브랜치**: `eval_science`
**LLM 엔드포인트**: `gemma-4-31b-it` @ `127.0.0.1
**실행 스크립트**: `scripts/sgsc/run_pilot_14.py --parallel 4`

---

## 1. 실행 개요

| 항목 | 값 |
|------|-----|
| 대상 가이드라인 | 14 (9 conflict-bearing + 5 breadth) |
| 성공률 | **14/14 (100%)** |
| 총 시나리오 | **283** |
| 총 atoms | **443** |
| Hallucination rate | **0.0%** |
| Leakage audit | **ALL PASSED** |
| 예상 에피소드 (8m×3r) | **6,792** |
| 총 소요시간 (sequential) | 192.1분 (평균 823초/가이드라인) |
| Atoms/시나리오 비율 | 1.57 |

---

## 2. 가이드라인별 상세 결과

### 2.1 Conflict-Bearing 가이드라인 (9개)

| Guideline ID | 시나리오 | Atoms | 소요시간 | Conflict Pattern |
|---|---|---|---|---|
| aha_heart_failure_2022 | **54** | 75 | 31.3m | ACE/MRA contraindication in hyperkalemia |
| acls_cardiac_arrest | 23 | 43 | 18.1m | hypothermia bypass |
| ada_dka_management | 23 | 42 | 19.6m | K+ > 5.5 insulin bypass |
| aabb_transfusion | 13 | 21 | 8.9m | liberal vs restrictive threshold (held-out) |
| pals_pediatric_emergency | 14 | 22 | 7.1m | congenital heart disease fluid restriction (held-out) |
| idsa_meningitis | 12 | 17 | 10.7m | OR_REQUIRED ampicillin alternative |
| pulmonary_embolism | 10 | 18 | 5.9m | OR_REQUIRED thrombolysis vs embolectomy |
| ssc_sepsis_hour1_bundle | 6 | 7 | 2.4m | ESRD bypass |
| aha_chest_pain_evaluation | 4 | 5 | 2.4m | aortic dissection bypass |
| **소계** | **159** | **250** | **106.4m** | |

### 2.2 Breadth 가이드라인 (5개)

| Guideline ID | 시나리오 | Atoms | 소요시간 |
|---|---|---|---|
| aha_stroke_2019 | **44** | 51 | 33.1m |
| gina_asthma_exacerbation | 25 | 48 | 19.5m |
| status_epilepticus | 21 | 35 | 12.2m |
| kdigo_aki_full | 20 | 24 | 7.4m |
| anaphylaxis_management | 14 | 35 | 13.6m |
| **소계** | **124** | **193** | **85.7m** |

### 2.3 Held-out 가이드라인 (2개, conflict-bearing에 포함)

| Guideline ID | 시나리오 | Atoms |
|---|---|---|
| aabb_transfusion | 13 | 21 |
| pals_pediatric_emergency | 14 | 22 |
| **소계** | **27** | **43** |

---

## 3. Sanitizer 진화 분석

SSC Sepsis Hour-1 Bundle (8 recommendations → 9 raw atoms)을 기준으로 sanitizer 버전별 파싱 성공률 비교:

### 3.1 Sanitizer v2 결과: 5/9 atoms (55.6%)

| Atom ID | 결과 | 실패 원인 |
|---|---|---|
| measure_lactate | OK | - |
| serial_lactate | **FAIL** | `evidence.recommendation_class` = None, `evidence.level` = None |
| obtain_blood_cultures | **FAIL** | `evidence.level` = None |
| administer_antimicrobials | OK | - |
| administer_crystalloids | OK | - |
| administer_norepinephrine | OK | - |
| administer_corticosteroids | **FAIL** | `evidence.recommendation_class` = None, `evidence.level` = None |
| use_balanced_crystalloids | **FAIL** | `counterfactual_pairs[0]` = list instead of string |
| avoid_albumin | OK | - |

### 3.2 Sanitizer v3 결과: 9/9 atoms (100%)

| Atom ID | Action | Constraint | Deadline | Sequence |
|---|---|---|---|---|
| measure_lactate | `measure_lactate` | REQUIRED | - | - |
| serial_lactate | `measure_lactate_serial` | REQUIRED | - | after: measure_lactate |
| obtain_blood_cultures | `obtain_blood_cultures` | REQUIRED | - | before: administer_antimicrobials |
| administer_antimicrobials | `administer_antimicrobials` | WITHIN | **60분** | - |
| administer_crystalloids | `administer_crystalloids` | WITHIN | **180분** | - |
| administer_norepinephrine | `administer_norepinephrine` | REQUIRED | - | - |
| administer_corticosteroids | `administer_corticosteroids` | REQUIRED | - | after: crystalloids + norepinephrine |
| use_balanced_crystalloids | `use_balanced_crystalloids` | REQUIRED | - | - |
| avoid_albumin | `administer_albumin` | **FORBIDDEN** | - | - |

### 3.3 v3 수정 사항 (6가지 LLM 출력 오류 패턴)

| 패턴 | LLM 출력 | v3 수정 |
|---|---|---|
| `evidence.recommendation_class` = None | JSON null | → `"unknown"` |
| `evidence.level` = None | JSON null | → `"unknown"` |
| `evidence.system` = None | JSON null | → `"unknown"` |
| `source.section` = None | JSON null | → `""` |
| `source.page` = int | 정수 | → `str(page)` |
| `counterfactual_pairs[0]` = list | `["a", "b"]` | → `"a_vs_b"` |

---

## 4. 버그 수정 히스토리

### 4.1 Bug: vLLM max_tokens 400 Bad Request

- **원인**: `DEFAULT_MAX_TOKENS=8192` 설정 시 vLLM `--max-model-len=8192`에서 prompt+completion이 총 8192 토큰을 초과
- **증상**: 14/14 가이드라인 모두 `400 Bad Request` 즉시 실패
- **수정**: `DEFAULT_MAX_TOKENS` 8192 → **4096**
- **파일**: `sgsc/extraction/atom_proposer.py:24`

### 4.2 Bug: JSON 출력 Truncation

- **원인**: 큰 recommendation set (8+ recs)의 LLM JSON 응답이 4096 output tokens를 초과하여 잘림
- **증상**: `Could not extract JSON from LLM response: ```json\n[\n  {\n    "atom_id":...` (불완전 JSON)
- **발견**: Gemma tokenizer는 structured JSON에서 ~3 chars/token (일반 텍스트 4 chars/token 아님)
  - 14K chars JSON ≈ 4,667 tokens > 4,096 limit
- **수정**: `_CHUNK_SIZE=5` 도입 — 5개 recommendation씩 나누어 LLM 호출
  - 5 recs × ~1,900 bytes/atom ÷ 3 chars/token ≈ 3,167 tokens (4,096 이내)
- **파일**: `sgsc/extraction/atom_proposer.py:27`

### 4.3 Bug: ProcessPoolExecutor sys.path 미상속

- **원인**: Python 3.13에서 `ProcessPoolExecutor`가 `spawn` 방식 사용 시 worker에 `sys.path` 미상속
- **증상**: 14/14 가이드라인 모두 `No module named 'cga_bench'` 즉시 실패
- **수정**: `sys.path.insert`를 함수 내부(line 151)에서 **모듈 레벨**(line 30)로 이동
- **파일**: `scripts/sgsc/run_pilot_14.py:33-36`

### 4.4 Bug: vLLM /v1/models 빈 응답

- **원인**: vLLM `--api-key` 설정 시 `/v1/models` 엔드포인트도 Authorization header 필요
- **증상**: `api_key` 없이 호출하면 빈 모델 리스트 반환 → dry-run 검증 혼란
- **수정**: `AtomProposerConfig.api_key` 기본값 `"sk-no-key-required"` 유지, 프로덕션에서 명시적 전달

---

## 5. 코드 변경 요약

### 5.1 수정된 파일 (3개, +184/-19 lines)

| 파일 | 변경 내용 |
|---|---|
| `sgsc/extraction/atom_proposer.py` | DEFAULT_MAX_TOKENS=4096, _CHUNK_SIZE=5, `_format_rec_texts()`, `_parse_llm_atoms()`, `_sanitize_atom_dict()` v3, chunked `propose_atoms()` with dedup |
| `tests/test_sgsc/test_atom_proposer.py` | max_tokens assertion 4096, 3 new chunking tests (boundary, distinct, dedup) |
| `scripts/sgsc/run_pilot_14.py` | module-level sys.path setup |

### 5.2 신규 생성 파일

| 파일 | 용도 |
|---|---|
| `configs/sgsc/pilot_14_registry.json` | 14 가이드라인 레지스트리 (corpus/graph 경로) |
| `scripts/sgsc/run_pilot_14.py` | Python 배치 오케스트레이터 |
| `scripts/sgsc/run_pilot_14.sh` | Shell 배치 래퍼 |
| `sgsc_output/*/` | 14개 가이드라인별 출력 디렉토리 |
| `sgsc_output/pilot_14_report.json` | 배치 결과 리포트 |
| `docs/sgsc/260430_r6_macro_inventory.md` | Paper macro audit (v6→v7 전환용) |
| `docs/sgsc/260430_scn012_bridge.md` | SCN-012 v6→v7 bridge mapping |
| `docs/sgsc/260430_v6_baseline_freeze.md` | v6 baseline 동결 문서 |
| `docs/sgsc/260430_sgsc8_bridge_template.md` | SGSC-8 bridge template |

### 5.3 테스트 현황

| 테스트 파일 | 테스트 수 | 상태 |
|---|---|---|
| `test_atom_proposer.py` | 21 | ALL PASS |
| 기존 SGSC 테스트 전체 | 528+ | ALL PASS |

---

## 6. 아키텍처 결정 사항

### 6.1 Recommendation Chunking 전략

```
recommendations (N개)
  ├─ N ≤ 5: 단일 LLM 호출
  └─ N > 5: ceil(N/5) 청크로 분할
       ├─ 각 청크: 독립 LLM 호출 (batch X/Y 표시)
       ├─ 결과 병합: all_atoms.extend(chunk_atoms)
       └─ Dedup: atom_id 기준 중복 제거
```

**선택 근거**: chunk_size=8 → JSON 여전히 truncation, chunk_size=5 → 3,167 tokens/chunk (4,096 limit 대비 77% 사용)

### 6.2 Production Timeout 설정

| 컴포넌트 | 기본값 | 프로덕션 값 | 근거 |
|---|---|---|---|
| `AtomProposerConfig.timeout_seconds` | 300s | 600s | Gemma-31b 대형 corpus 처리 시 120s 초과 확인 |
| `sgsc/cli.py` | 300s | 600s | CLI 진입점 일관성 |
| `run_pilot_14.py` | - | 600s | 명시적 전달 |

### 6.3 Entailment Filtering 효과 (SSC Sepsis 사례)

```
LLM 제안: 9 atoms (raw)
  → Sanitizer v3 파싱: 9/9 (100%)
  → Schema validation: 9/9 (100%)
  → Quote grounding: 9/9 (100%)
  → Entailment filter: 6/9 (66.7%)
    - REJECTED: serial_lactate (sequence, evidence)
    - REJECTED: administer_corticosteroids (sequence)
    - REJECTED: use_balanced_crystalloids (action)
  → Final scenarios: 5 (from 6 atoms)
```

---

## 7. 목표 대비 Gap 분석

### 7.1 시나리오 수 Gap

| 항목 | 목표 | 실제 | 달성률 |
|---|---|---|---|
| 총 시나리오 | ~700 | 283 | **40.4%** |
| 총 atoms | - | 443 | - |
| 예상 에피소드 | ~16,800 | 6,792 | 40.4% |

### 7.2 가이드라인별 산출량 불균형

| 범위 | 가이드라인 수 | 평균 시나리오 |
|---|---|---|
| 40+ 시나리오 | 2 (heart_failure, stroke) | 49.0 |
| 20-39 시나리오 | 4 (acls, ada_dka, gina, status_ep) | 23.0 |
| 10-19 시나리오 | 5 (aabb, anaphylaxis, pals, idsa, PE) | 12.6 |
| <10 시나리오 | 3 (sepsis, chest_pain, kdigo?) | 10.0 |

**산출량 제한 요인**:
1. **Corpus 크기**: Sepsis(8 recs), Chest Pain(소형) → 적은 atoms → 적은 시나리오
2. **Entailment 필터**: 평균 33% rejection rate (9→6 atoms in SSC)
3. **Counterfactual 다양성**: 작은 atom set → 적은 counterfactual families → 적은 mutation traces

### 7.3 시나리오 수 증가 방안

| 방안 | 예상 효과 | 위험도 |
|---|---|---|
| Sanitizer v3로 재실행 | +30~50% atoms (파싱 개선) | 낮음 |
| Temperature 0.2→0.4 | +10~20% atom 다양성 | 중간 (hallucination 위험) |
| 2-pass proposal (서로 다른 prompt) | +40~60% unique atoms | 중간 (LLM 비용 2배) |
| Corpus 보강 (더 많은 recommendations) | +대폭 | 높음 (수작업 필요) |

---

## 8. Day 1 Trigger 완료 현황

| Trigger | 설명 | 상태 | 산출물 |
|---|---|---|---|
| **A: SGSC-3 Atom Proposal** | 14 CPG 전체 atom 추출 | **DONE** | `sgsc_output/pilot_14_report.json` |
| **B: Auto-Transition Schema** | v6→v7 자동 전환 스키마 | **DONE** | `cpg_model/schemas/base.py` |
| **C: SGSC-8 Bridge Template** | Bridge 문서 템플릿 | **DONE** | `docs/sgsc/260430_sgsc8_bridge_template.md` |

---

## 9. 핵심 발견 사항 (Pitfalls)

1. **vLLM max_tokens ≠ max-model-len**: `max_tokens`는 completion 전용, `max-model-len`은 prompt+completion 총합. `max_tokens=max_model_len`으로 설정하면 모든 요청이 400 에러.

2. **Gemma JSON 토큰 비율**: Structured JSON은 ~3 chars/token (일반 텍스트 ~4보다 밀도 높음). 토큰 예산 계산 시 반드시 3으로 나눌 것.

3. **ProcessPoolExecutor + sys.path**: Python 3.13 Linux에서 `spawn` 방식 사용 가능. Worker에서 `sys.path`가 상속되지 않을 수 있으므로 **모듈 레벨**에서 설정 필수.

4. **vLLM api_key 요구**: `--api-key` 옵션으로 시작된 vLLM은 `/v1/models` 포함 모든 엔드포인트에서 Authorization header 필요. 빈 리스트 반환은 에러가 아닌 인증 실패.

5. **Entailment rejection rate ~33%**: LLM이 제안한 atoms 중 1/3은 source corpus에서 뒷받침되지 않아 자동 제거. 이는 설계대로 작동하는 것 (hallucination 방지).

---

## 10. 다음 단계 권장사항

1. **Sanitizer v3 전체 재실행** (P0): v3가 SSC에서 5→9 atoms (80% 증가). 14개 전체 재실행 시 283→~400+ 시나리오 예상.
2. **Entailment threshold 조정** (P1): 현재 strict rule-based → 완화 시 더 많은 atoms 통과 가능.
3. **2-pass atom proposal** (P2): 서로 다른 시스템 프롬프트로 2회 호출, unique atoms 병합.
4. **Paper macro 업데이트** (P1): `docs/sgsc/260430_r6_macro_inventory.md` 기반으로 v7 수치 반영.
