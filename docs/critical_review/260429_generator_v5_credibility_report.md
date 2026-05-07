# Auto-Scenario Generator v5 신빙성 개선 보고서

> 작성일: 2026-04-29 | 브랜치: eval_science
> 목적: v4 자체 평가에서 발견된 3가지 신빙성 문제 해결

## 1. v4 → v5 개선 요약

| 지표 | v4 (이전) | v5 (현재) | Manual 기준 | 상태 |
|------|----------|----------|------------|------|
| FA % | 100.0% | **83.7%** | 80.4% | OK (3.3pp 차이) |
| Avg FA/scenario | 4.9 | **3.6** | 2.2 | 개선 (-27%) |
| Comorbidity % | 61.0% | **82.4%** | 83.2% | OK (0.8pp 차이) |
| Metadata % | 0% | **100.0%** | N/A | 신규 기능 |
| FA provenance | 없음 | **100.0%** | N/A | 신규 기능 |
| Validator rules | 4 (A-D) | **6 (A-F)** | N/A | +2 규칙 추가 |
| Tests | 51 | **72** | N/A | +21 테스트 |

## 2. 변경 내용

### 2.1 Provenance Metadata (Task 1)

모든 자동 생성 시나리오에 `_generation_metadata` dict 추가:

```yaml
_generation_metadata:
  generator_version: "v5"
  generation_phase: "branch"       # branch | conditional_rule | universal_trap | baseline
  graph_id: "ssc_sepsis_hour1_bundle"
  source_node_ids: ["n1", "n2"]    # 경로 탐색 중 방문한 노드
  forbidden_action_provenance:     # 각 FA의 출처
    give_nsaid: "node:n1"
    give_penicillin: "rule:ALLERGY-PEN"
    give_acetaminophen: "trap:liver_acetaminophen"
```

**변경된 함수**:
- `walk_reachable_path()`: `return_node_ids=True` 옵션으로 방문 노드 ID 반환
- `_extract_node_forbidden_actions()`: `(list, dict)` 반환으로 FA 출처 추적
- `_build_generation_metadata()`: 신규 헬퍼 함수

**문헌 근거**: HL7 FHIR CPG IG 2.0의 `relatedArtifact` 패턴, AABB transfusion의 `_derived_constraints` 패턴

### 2.2 FA 과잉 주입 수정 (Task 2)

| Phase | 이전 | 이후 | 근거 |
|-------|------|------|------|
| Branch (Phase 1) | 100% FA, 전체 주입 | **80% 확률, 최대 3개** | Manual 80.4% 기준 |
| Conditional rule (Phase 2) | 100% | 100% (유지) | Trap은 정의상 FA 필수 |
| Universal trap (Phase 2b) | 100% | 100% (유지) | Trap은 정의상 FA 필수 |
| Baseline (Phase 3) | FA 주입 | **FA 제거** | Clean happy-path 테스트 |

### 2.3 Comorbidity 보정 (Task 3)

**이전**: `rng.randint(0, 2)` → P(0)=33.3%, P(1)=33.3%, P(2)=33.3%
**이후**: `rng.choices([0,1,2], weights=[0.20, 0.45, 0.35])` → P(0)=20%, P(≥1)=80%

추가: `"general"` 도메인에 fallback comorbidity pool 추가 (hypertension, DM, CKD 등 7개).
이전에 21개 그래프가 domain="general"로 빈 pool → comorbidity 0%였음.

**Phase별 결과**:
- Branch: 46.8% → **80.8%** (Manual 83.2%에 근접)
- Conditional rule: 96.7% (유지)
- Universal trap: 97.4% (유지)
- Baseline: 0% (의도적 — clean test)

### 2.4 Validator Rules E+F (Task 4)

`scripts/ci/validate_scenario_plausibility.py`에 2개 규칙 추가:

- **Rule E (Provenance completeness)**: `_generation_metadata` 필수 필드 검증
  - E1: graph_id 필수
  - E2: generation_phase 유효성 (branch/conditional_rule/universal_trap/baseline)
  - E3: source_node_ids 비어있으면 WARNING
  - E4: 모든 FA에 provenance 있는지 ERROR

- **Rule F (FA-to-graph traceability)**: FA 출처 노드가 실제 그래프에 존재하는지 검증
  - `node:n1` → 그래프에 n1 노드 존재하고 FA가 해당 노드의 forbidden_actions에 있는지
  - `rule:XXX`, `trap:XXX` 출처는 Rule F에서 미검증 (별도 검증 불필요)

**검증 결과**: 1067 시나리오 × 6 규칙 → **0 ERROR, 467 WARNING** (WARNING은 D_chief_complaint 등 기존 항목)

### 2.5 테스트 (Task 5)

+21 테스트, 총 72개:

| 테스트 클래스 | 테스트 수 | 검증 항목 |
|-------------|----------|----------|
| TestGenerationMetadata | 6 | 메타데이터 존재, 필수 필드, phase 매칭, provenance 커버리지 |
| TestFACalibration | 4 | baseline FA 없음, 80% 확률, 3개 상한, trap은 항상 FA |
| TestComorbidityCalibration | 1 | ~80% 비율 통계 검증 |
| TestRuleEProvenance | 5 | 수동 시나리오 skip, missing graph_id, invalid phase, FA 누락 |
| TestRuleFTraceability | 5 | dangling node ref, FA not in node list, trap source pass |

## 3. 과잉 설계 여부 자체 평가

### 과잉 아닌 것 (OK)
- Metadata 100%: paper defensibility를 위한 최소 요건 (FHIR CPG 표준)
- FA provenance 100%: 모든 FA가 graph node/rule/trap에 traceable
- Comorbidity 82.4%: Manual 83.2%와 0.8pp 차이

### 주의 필요 (INFO)
- Avg FA/scenario 3.6: Manual 2.2의 1.6배. 구조적 원인 (auto graph가 노드별 세분화된 FA 보유)
- FA 83.7%: Manual 80.4%보다 약간 높지만 통계적 변동 범위 내

### 잔여 과제 (P2)
- Avg FA 3.6 → 2.5 수준: graph FA에서 가중치 기반 샘플링으로 추가 조정 가능
- Allergy 1.0% vs Manual 5.6%: Phase 1 branch에 allergy 부여 로직 필요

## 4. 변경된 파일

| 파일 | 변경 |
|------|------|
| `scripts/generate_scenarios_from_cpg.py` | +general comorbidity pool, metadata, FA calibration, comorbidity weights |
| `scripts/ci/validate_scenario_plausibility.py` | +Rules E (provenance) + F (FA traceability) |
| `tests/test_ci/test_generate_scenarios.py` | +21 tests (51→72), _extract_node_forbidden_actions tests updated for tuple return |
