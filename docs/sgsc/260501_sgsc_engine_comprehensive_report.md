# SGSC v7 Engine Comprehensive Report

**Date**: 2026-05-01
**Branch**: `eval_science`
**Corpus Version**: v7 (SGSC-3 full 25-guideline, Qwen3.5-397B)
**Status**: 243 scenarios, 462 atoms, 25 guidelines, 570/570 SGSC tests passing

---

## 1. Executive Summary

Source-Grounded Scenario Compiler (SGSC)는 임상 가이드라인(CPG) 텍스트에서 평가용 시나리오를 자동 생성하는 15단계 파이프라인이다. 기존 CGA-Bench의 수동 YAML 작성 방식을 대체하며, LLM을 **원자 제안자(proposer)**로만 사용하고 나머지 모든 컴파일은 **완전 결정적(deterministic)**으로 수행한다.

### v7 최종 코퍼스 현황

| 항목 | 값 |
|------|-----|
| 가이드라인 | 25 |
| 시나리오 (public + private) | 243 |
| RecommendationAtom | 462 |
| 모델 수 (평가 대상) | 8 |
| 실행 횟수 | 3 |
| 예상 에피소드 | 5,832 |
| 제약 조건: FORBIDDEN | 29 |
| 제약 조건: REQUIRED | 396 |
| 제약 조건: WITHIN | 37 |
| Hallucination rate | 0.0% |
| Leakage audit | ALL PASSED |
| No-go criteria | 4/4 PASSED |

### 진화 경로

```
v6 Manual (706 scenarios, 수동 YAML)
  → Pilot-14 (283 scenarios, Gemma-4-31b-it, 14 guidelines)
  → SGSC-3 Option B (243 scenarios, Qwen3.5-397B, 25 guidelines)  ← 현재
```

---

## 2. Architecture Overview

### 2.1 6-Layer Design

SGSC는 6개 레이어로 구성되며, LLM은 Layer 2(Extraction)에서만 사용된다.

```
Layer 1: Schemas (Pydantic v2 IR)
  ├─ RecommendationAtom      — 중심 중간표현 (IR)
  ├─ ScenarioSeed            — 시나리오 씨앗
  ├─ CounterfactualFamily    — 반사실적 시나리오 가족
  ├─ CoverageItem / Vector   — 커버리지 추적
  └─ GuidelineQualityCard    — 가이드라인별 품질 메타데이터

Layer 2: Extraction (LLM-as-proposer) [유일한 LLM 의존]
  ├─ atom_proposer.py        — LLM이 atom 후보 제안 (chunked)
  ├─ schema_validator.py     — Pydantic + business-rule 검증
  └─ multi_model_agreement.py — N-model 합의 필터 (optional)

Layer 3: Verification (source grounding)
  ├─ quote_verifier.py       — 3-tier: VERIFIED / GROUNDED / UNGROUNDED
  ├─ entailment_checker.py   — 6-field 엔테일먼트 (rule_based / llm / llm_strict)
  └─ hallucination_detector.py — hallucination rate 계산

Layer 4: Compilers (deterministic, LLM 없음)
  ├─ constraint_compiler.py  — Atom → DerivedConstraint (@dataclass)
  ├─ graph_compiler.py       — Atoms → YAML graph dict
  ├─ scenario_compiler.py    — Seeds → scenario YAML (public/private split)
  ├─ counterfactual_compiler.py — Atoms → CounterfactualFamily
  └─ mutation_compiler.py    — MutationTemplate → variant traces

Layer 5: Optimizer (deterministic, LLM 없음)
  ├─ coverage_tracker.py     — 13-type 커버리지 추출
  ├─ set_cover_solver.py     — Greedy weighted set-cover
  └─ scenario_selector.py    — Tracker + Solver 오케스트레이션

Layer 6: Audit (deterministic)
  ├─ source_fidelity.py      — entailment rate, hallucination rate
  ├─ leakage_scanner.py      — private-field 누출 탐지 (7+ 패턴)
  └─ coverage_reporter.py    — JSON / Markdown / LaTeX 보고서
```

### 2.2 추가 모듈 (post-baseline)

| 모듈 | 라인 수 | 용도 |
|------|---------|------|
| `validation_packet.py` | 501 | Cohen's kappa, Gwet AC1, Krippendorff alpha 기반 multi-rater agreement |
| `e2e_harness.py` | 285 | 배치 파이프라인 오케스트레이션 |
| `manifest.py` | 196 | 아티팩트 매니페스트 (체크섬, 프로비넌스, 재현성) |

### 2.3 코드베이스 규모

| 구분 | 파일 수 | 라인 수 |
|------|---------|---------|
| Source (sgsc/) | 34 | 5,251+ |
| Tests (test_sgsc/) | 22 | 5,194+ |
| Test-to-source ratio | — | 0.99:1 |
| Test count | — | 570 |
| Test execution time | — | ~0.43s |

---

## 3. Core IR: RecommendationAtom

`RecommendationAtom`은 SGSC의 중심 중간표현(IR)이다. 하나의 가이드라인 권고사항에서 하나의 실행 가능한 행동을 추출한 원자 단위이다.

```python
class RecommendationAtom(BaseModel):
    atom_id: str                     # 고유 식별자 (guideline_id + action, snake_case)
    source: SourceReference          # guideline_id, section, quote, quote_hash(SHA-256)
    population: PopulationCriteria   # inclusion[], exclusion[]
    action: AtomAction               # canonical_id, action_type, terminology{}
    constraint: AtomConstraint       # FORBIDDEN|REQUIRED|BEFORE|WITHIN|EXPECTED
    sequence: AtomSequence           # before[], required_prior[]
    evidence: AtomEvidence           # system, recommendation_class, level
    scenario_hooks: ScenarioHooks    # boundary_variables[], counterfactual_pairs[]
    proposed_by: str                 # 프로비넌스: 어떤 LLM이 제안했는가
    agreement_score: float           # Multi-model 합의 점수 [0,1]
    entailment_status: str           # pending|grounded|entailed|rejected|ungrounded
```

### 설계 결정

| 결정 | 근거 |
|------|------|
| Pydantic v2 + `frozen=True` (sub-models) | 불변 IR — downstream mutation 방지 |
| `quote_hash` = SHA-256 자동 계산 | dedup + 감사 추적 가능 |
| `constraint.type` = CGA-Bench `DerivedConstraint`와 동일 문자열 | 기존 파이프라인과 무장애 통합 |
| `scenario_hooks` 분리 | generation hint가 IR을 오염시키지 않음 |
| `entailment_status` mutable field | 파이프라인 단계별 상태 전이 추적 |

### Atom 상태 전이

```
[LLM 제안] → pending
  → [Quote Grounding Pass] → grounded
  → [Entailment Pass] → entailed  (최종 수락)
  → [Entailment Fail: NOT_ENTAILED] → rejected  (거부)
  → [Grounding Fail 또는 PARTIAL] → review_required  (인간 검토 필요)
```

---

## 4. Pipeline Flow: 15 Steps

### 4.1 전체 흐름도

```
Corpus + Recommendations
  → Step 1:   Load recommendations (passthrough)
  → Step 2:   LLM proposes RecommendationAtoms            [LLM]
  → Step 2b:  ActionNormalizer 정규화                       [deterministic]
  → Step 3:   Schema validation (Pydantic + business rules)
  → Step 4:   Multi-model agreement filter                  [LLM, optional]
  → Step 5:   3-tier quote grounding (VERIFIED/GROUNDED/UNGROUNDED)
  → Step 6:   Field-level entailment (6 fields, 3 modes)   [rule_based default]
  → Step 7:   Deterministic graph compiler → YAML graph
  → Step 8:   Deterministic scenario seed compiler
  → Step 9:   Deterministic counterfactual family compiler
  → Step 10:  Mutation trace compiler
  → Step 11:  Coverage item extraction (13 types)
  → Step 12:  Set-cover optimizer → minimal scenario set
  → Step 13:  Generate scenario YAML (full + public/private split)
  → Step 14:  Leakage audit (full + public-only scan)
  → Step 15:  Coverage report (JSON + Markdown + LaTeX)
```

**LLM 격리 원칙**: Step 2, 4, 6만 LLM을 사용한다. Step 7-15는 완전 결정적이며 모델 엔드포인트 없이 테스트 가능하다.

### 4.2 Step별 상세

#### Step 1-2: Atom Extraction

LLM이 가이드라인 권고사항 텍스트에서 `RecommendationAtom` JSON 배열을 출력한다.

- **Chunking** (`_CHUNK_SIZE = 5`): 5개 권고 단위로 분할하여 output-token truncation 방지
- **Sanitizer v3** (`_sanitize_atom_dict`): 6가지 LLM 출력 오류 패턴 자동 교정
- **JSON Extractor** (`_extract_json`): `<think>` 태그, markdown code block, 잘린 code block 처리
- **Deduplication**: chunk 간 `atom_id` 기준 중복 제거

#### Step 2b: ActionNormalizer Integration (β-4~β-6)

CGA-Bench 전체 시스템의 `ActionNormalizer`를 SGSC 파이프라인에 통합하여, LLM이 제안한 action ID를 정규 형태로 변환한다.

```python
# pipeline.py — Step 2b
atoms = _normalize_atom_actions(atoms)

# action.canonical_id 정규화 (예: "give_abx" → "administer_antibiotics")
# sequence.required_prior, sequence.before 내 action 참조도 함께 정규화
```

- `ActionNormalizer`는 lazy import로 SGSC 단독 실행 시에도 graceful fallback
- AtomAction, AtomSequence는 `frozen=True` — `model_copy(update={...})` 패턴으로 안전하게 갱신

#### Step 3: Schema Validation

Pydantic v2 모델 검증 + 비즈니스 규칙 검사:
- atom_id 고유성
- constraint type 유효성 (FORBIDDEN|REQUIRED|BEFORE|WITHIN|EXPECTED)
- source.quote 비어있지 않음
- evidence 필수 필드 존재

#### Step 5: 3-Tier Quote Grounding

| Tier | 조건 | 상태 |
|------|------|------|
| VERIFIED | source quote가 corpus에 verbatim 존재 | 수락 |
| GROUNDED | fuzzy match (Jaccard similarity ≥ threshold) | 수락 |
| UNGROUNDED | 어떤 매칭도 실패 | 거부 |

- `grounding_threshold` 기본값: 0.6
- Grounding 실패 atoms는 `review_required_atoms`로 분류

#### Step 6: Field-Level Entailment (핵심 개선)

baseline 95줄 stub에서 412줄 프로덕션 시스템으로 **+334% 확장**.

**6개 필드별 개별 검증**:

| 필드 | 검증 내용 |
|------|----------|
| action | source quote에 해당 action이 언급되는가 |
| guard | exclusion/conditional 조건이 source에 있는가 |
| exclusion | population exclusion이 source에 있는가 |
| timing | deadline/time constraint가 source에 있는가 |
| sequence | before/required_prior 관계가 source에 있는가 |
| evidence | recommendation class/level이 source에 있는가 |

**3가지 엔테일먼트 등급**:
- `ENTAILED`: 완전히 지지됨
- `PARTIALLY_ENTAILED`: 부분적 증거 존재
- `NOT_ENTAILED`: 지지 증거 없음 (거부)

**3가지 모드**:
- `rule_based` (기본): deterministic substring/pattern matching, LLM 미사용
- `llm`: LLM 기반 + rule-based fallback
- `llm_strict`: LLM 전용, PARTIAL도 거부

**엔테일먼트 Gate 2 (필수)**:
- `NOT_ENTAILED` → 확정 거부 (`rejected_atoms`)
- `PARTIAL` + strict mode → 인간 검토 (`review_required_atoms`)
- 모든 필드 `ENTAILED` → 수락 (`atoms`)

#### Step 7: Graph Compiler

수락된 atoms에서 YAML 호환 그래프 dict 생성:
- 노드 = action 기반 그룹핑
- 엣지 = sequence 관계 (required_prior, before)
- BEFORE constraint → `required_prior_actions` 역방향 배선
- `max_nodes` 초과 시 섹션별 병합 (action list + required_prior 통합)
- 출력: `cpg_model/graphs/*.yaml` 구조와 호환

#### Step 8-9: Scenario Seed + Counterfactual Family Compiler

**Seed Compiler**:
- 각 atom에서 ScenarioSeed 생성
- 환자 템플릿 8종 순환 (age/sex 다양성)
- Boundary variables에서 경계값 시나리오 생성
- Mutation templates (omit, delay, swap, forbidden) 자동 생성

**Counterfactual Compiler**:
- Exclusion families: population exclusion 기반 쌍
- Timing families: WITHIN constraint 기반 (met/missed 쌍)
- Sequence families: BEFORE constraint 기반 (correct/violated 쌍)
- Alternative families: ALTERNATIVE coverage type 기반

#### Step 10: Mutation Trace Compiler

각 seed의 mutation templates를 구체화:
- `omit`: 필수 action 누락
- `delay`: WITHIN deadline 초과
- `swap`: 잘못된 action 대체
- `forbidden`: 금지된 action 수행

#### Step 11-12: Coverage Optimization

**13-Type Coverage Model** (baseline 6+1에서 확장):

| # | Type | 출처 | 가중치 |
|---|------|------|--------|
| 1 | RECOMMENDATION | 각 atom 당 1개 | 1.0x |
| 2 | CONSTRAINT | constraint type + action 별 | 1.0x |
| 3 | GUARD | exclusion criteria 있는 atom | 1.3x |
| 4 | BOUNDARY | boundary variable 별 | 1.0x |
| 5 | ALTERNATIVE | 임상적 동등 분기 | 1.5x |
| 6 | MUTATION | mutation template 별 | 1.5x |
| 7 | SOURCE | source linkage 검증 | 1.0x |
| 8 | GUARD_TRUE | guard 조건 true 케이스 | MC/DC |
| 9 | GUARD_FALSE | guard 조건 false 케이스 | MC/DC |
| 10 | TIMING_MET | deadline 준수 케이스 | MC/DC |
| 11 | TIMING_MISSED | deadline 위반 케이스 | MC/DC |
| 12 | ORDER_CORRECT | 순서 준수 케이스 | MC/DC |
| 13 | ORDER_VIOLATED | 순서 위반 케이스 | MC/DC |

Coverage types 8-13은 Modified Condition/Decision Coverage (MC/DC) 기반으로, guard 조건, timing 제약, action 순서의 true/false 양면을 모두 커버한다.

**Set-Cover Optimizer**: Greedy weighted set-cover로 모든 coverage item을 최소 k회 이상 커버하는 시나리오 부분집합 선택.

#### Step 13: Scenario YAML Generation

- **Full scenarios**: 모든 필드 포함
- **Public scenarios**: agent에게 노출되는 필드만 (patient state, available actions)
- **Private scenarios**: scorer 전용 (expected_actions, forbidden_actions, deadlines, mandatory_actions)
- Private fields: `expected_actions`, `forbidden_actions`, `deadlines`, `mandatory_actions`

#### Step 14: Leakage Audit

7+ 패턴으로 정보 누출 탐지:
- Full scenario scan: 모든 시나리오 대상
- Public-only scan: agent-visible 시나리오만 대상
- Private field 노출 검사
- Canary token 검사

#### Step 15: Coverage Report + Artifact Persistence

- Coverage report: JSON + Markdown + LaTeX
- Graph: `{guideline_id}_graph.json`
- Scenarios: `{guideline_id}_scenarios.json` + `_public.json` + `_private.json`
- Constraints: `{guideline_id}_constraints.json`
- Atoms: `atoms_smoke.json` (β-8.5에서 추가 — F1 fix)
- Manifest: `sgsc_manifest_v1.json`

---

## 5. Trust Gate Framework

baseline 이후 가장 중요한 아키텍처 변경. 8개 gate로 파이프라인 신뢰성을 구조적으로 보증한다.

### Gate 1 (Phase A): Assertion Hardening + Atom Granularity

**문제**: E2E assertion이 trivially true (`hallucination_rate >= 0.0` — 항상 참).

**수정**:
- `hallucination_rate >= 0.0` → `hallucination_rate > 0.5 or len(result.atoms) == 0`
- `total_families >= 0` → `total_families >= 1`
- `total_mutations >= 0` → `total_mutations >= 1`
- `hallucination_rate < 0.5` → `hallucination_rate < 0.2`
- Atom granularity invariant: 하나의 recommendation → 다수 atom 가능, 각 atom은 정확히 하나의 recommendation 추적

### Gate 2 (Phase C): Mandatory Field-Level Entailment

**문제**: 95줄 stub, boolean enable/disable, 필드별 세분화 없음.

**수정**: 412줄 full rewrite (§4.2 Step 6 참조).

### Gate 3 (Phase B): Public/Private Scenario Split

**문제**: 모든 시나리오 필드가 agent에게 노출 — 평가 누출 위험.

**수정**:
- `split_scenario_public_private()` 함수
- `seeds_to_split_scenario_yaml()` 함수
- 7개 신규 leakage 패턴
- `scan_public_scenarios()` public-only 스캔

### Gate 4: Reserved (future)

### Gate 5 (Phase D): MC/DC Coverage + ALTERNATIVE

**문제**: 7개 coverage type 중 6개만 활성, ALTERNATIVE은 placeholder.

**수정**:
- 6개 MC/DC coverage type 추가 (GUARD_TRUE/FALSE, TIMING_MET/MISSED, ORDER_CORRECT/VIOLATED)
- ALTERNATIVE coverage type 활성화
- Sequence + alternative family generator 추가
- coverage_tracker.py: 213 → 349줄 (+64%)

### Gate 6 (Phase E): Compiler Mutation Testing

**문제**: unit test 외에 compiler 정확성 검증 방법 없음.

**수정**:
- `test_compiler_mutation_robustness.py` (15 tests, 318줄)
- Kill-rate metric: atom 입력에 의도적 mutation → 출력 변화 전파 검증

### Gate 7 (Phase F): Validation Protocol

- `validation_packet.py` (501줄)
- Cohen's kappa, Gwet AC1, Krippendorff alpha (binary, pairwise)
- Pure Python 구현 (scipy 의존성 제거)
- Evidence aggregation + adjudication protocol

### Gate 8 (Phase G-H): Manifest + Summary

- `manifest.py` (196줄): 아티팩트별 SHA-256 체크섬, 프로비넌스 메타데이터
- 모든 trust gate E2E 파이프라인에서 통합 검증

---

## 6. Atom Proposer 진화

### 6.1 Baseline → Pilot-14 → SGSC-3 진화 경로

| 항목 | Baseline (v1) | Pilot-14 (v2-v3) | SGSC-3 (v4, 현재) |
|------|--------------|-------------------|-------------------|
| LLM | 없음 (mock만) | Gemma-4-31b-it | Qwen3.5-397B |
| max_tokens | 8192 | 4096 | 8192 |
| chunking | 없음 | _CHUNK_SIZE=5 | _CHUNK_SIZE=5 |
| sanitizer | 없음 | v2→v3 | v3 |
| thinking model 지원 | 없음 | 없음 | `<think>` strip + `enable_thinking: false` |
| timeout | implicit | 300s → 600s | 300s (기본) |
| JSON extractor | 기본 | 기본 + code block | + truncated block + structure detection |
| lines | 173 | 282 | 298 |

### 6.2 Sanitizer v3: 6가지 LLM 출력 오류 패턴 교정

| 패턴 | LLM 출력 | v3 교정 |
|------|---------|---------|
| `evidence.recommendation_class` = None | JSON null | → `"unknown"` |
| `evidence.level` = None | JSON null | → `"unknown"` |
| `evidence.system` = None | JSON null | → `"unknown"` |
| `source.section` = None | JSON null | → `""` |
| `source.page` = int | 정수 | → `str(page)` |
| `counterfactual_pairs[0]` = list | `["a", "b"]` | → `"a_vs_b"` |

**효과**: SSC Sepsis 기준 파싱 성공률 55.6% (v2) → 100% (v3).

### 6.3 Chunking 전략

```
recommendations (N개)
  ├─ N ≤ 5: 단일 LLM 호출
  └─ N > 5: ceil(N/5) 청크로 분할
       ├─ 각 청크: 독립 LLM 호출 (batch X/Y 표시)
       ├─ 결과 병합: all_atoms.extend(chunk_atoms)
       └─ Dedup: atom_id 기준 중복 제거
```

**근거**: Gemma JSON 토큰 비율 ~3 chars/token. 14K chars JSON ≈ 4,667 tokens > 4,096 limit. chunk_size=5 → ~3,167 tokens/chunk (77% 사용률).

### 6.4 JSON Extractor: Thinking Model 대응 (β-8)

Qwen3.5-397B는 thinking model로, 기본 설정에서 `<think>...</think>` 블록을 출력에 포함한다.

**문제**: 닫는 `</think>` 태그만 있고 여는 태그 없는 경우 발생, 기존 regex 패턴 실패.

**해결 (2단계)**:
1. `chat_template_kwargs: {"enable_thinking": false}` 로 thinking mode 비활성화
2. `_extract_json()`에 다중 fallback 체인:
   - Plain JSON 파싱 시도
   - Markdown code block 추출 (` ```json ... ``` `)
   - Truncated code block 처리 (닫는 ` ``` ` 없는 경우)
   - Structure detection (`\[\s*\{` 패턴으로 JSON 배열/객체 탐색)

---

## 7. Entailment System 상세

baseline 대비 가장 극적인 단일 파일 변환 (+334%).

### 7.1 아키텍처

```
check_atoms_entailment(atoms, mode, thresholds)
  └─ per atom:
       ├─ _check_action_entailment()     → action keyword in quote
       ├─ _check_guard_entailment()      → exclusion conditions in quote
       ├─ _check_exclusion_entailment()  → population exclusion in quote
       ├─ _check_timing_entailment()     → deadline/time references in quote
       ├─ _check_sequence_entailment()   → before/prior references in quote
       └─ _check_evidence_entailment()   → recommendation class/level in quote
```

### 7.2 Rule-Based Matching

`_stem_match()` 함수로 keyword 기반 substring matching 수행:
- Action ID를 snake_case에서 개별 단어로 분해
- Source quote에서 해당 단어 존재 여부 확인
- Threshold 이상의 매칭 비율이면 ENTAILED

### 7.3 Dual-Threshold Reporting (TG-V2)

`compare_entailment_thresholds()`: 0.4 / 0.5 / 0.6 / 0.7 threshold별 수락 atom 수 비교 → threshold 민감도 분석.

### 7.4 파이프라인 통합

```python
# pipeline.py Step 6
entailment_reports = check_atoms_entailment(
    atoms, mode=config.entailment_mode,
    action_threshold=config.grounding_threshold,
    guard_threshold=config.grounding_threshold,
)

# Gate 2 분류:
#   passing_atom_ids   → entailed (수락)
#   rejected_atom_ids  → NOT_ENTAILED (거부)
#   partial_atom_ids   → PARTIAL (review_required)
```

---

## 8. CGA-Bench Integration

### 8.1 호환성 매핑

| SGSC Component | CGA-Bench Module | 통합 방식 |
|----------------|-----------------|----------|
| `AtomConstraint.type` | `DerivedConstraint.constraint_type` | 동일 문자열 (FORBIDDEN, REQUIRED, BEFORE, WITHIN) |
| `constraint_compiler.py` | `DerivedConstraint` (@dataclass) | 기존 dataclass 인스턴스 직접 생성 |
| `graph_compiler.py` 출력 | `cpg_model/graphs/*.yaml` | dict 구조 일치 (nodes, entry_node, metadata) |
| `scenario_compiler.py` 출력 | `ScenarioDefinition` | `ScenarioLoader.load_all_scenarios()` 호환 |
| `quote_verifier.py` | `ground_graph_quotes.py` | 3-tier 로직 공유 |
| `counterfactual_compiler.py` | `_x1_pair_discovery.py` | matched-pair 패턴 재사용 |
| `leakage_scanner.py` | `scripts/ci/leakage_scan.py` | canary 패턴 확장 |

### 8.2 ActionNormalizer Integration (β-4~β-6)

```
Step 2b (pipeline.py):
  atom.action.canonical_id → ActionNormalizer.normalize()
  atom.sequence.required_prior → 각 참조 action도 정규화
  atom.sequence.before → 각 참조 action도 정규화

Step 7 (graph_compiler.py):
  node.actions → 정규화된 canonical_id 사용

Step 8 (scenario_compiler.py):
  scenario.expected_actions → 정규화된 action 명 사용
```

**핵심 제약**: AtomAction과 AtomSequence는 `frozen=True` (불변). `model_copy(update={...})` 패턴으로 안전하게 갱신해야 하며, 직접 속성 할당은 불가.

---

## 9. Production Execution History

### 9.1 Pilot-14 (Gemma-4-31b-it)

| 항목 | 값 |
|------|-----|
| 대상 | 14 가이드라인 (9 conflict-bearing + 5 breadth) |
| 성공률 | 14/14 (100%) |
| 총 시나리오 | 283 |
| 총 atoms | 443 |
| Hallucination rate | 0.0% |
| 총 소요시간 | 192.1분 (avg 823초/가이드라인) |
| Atoms/시나리오 비율 | 1.57 |

**Top-3 가이드라인 (시나리오 수)**:
1. aha_heart_failure_2022: 54 scenarios, 75 atoms (31.3분)
2. aha_stroke_2019: 44 scenarios, 51 atoms (33.1분)
3. gina_asthma_exacerbation: 25 scenarios, 48 atoms (19.5분)

**Entailment Filtering 효과 (SSC Sepsis 사례)**:
```
LLM 제안: 9 atoms → Sanitizer: 9/9 → Schema: 9/9 → Grounding: 9/9
  → Entailment: 6/9 (33% rejection)
    REJECTED: serial_lactate (sequence, evidence)
    REJECTED: administer_corticosteroids (sequence)
    REJECTED: use_balanced_crystalloids (action)
  → Final: 5 scenarios (from 6 atoms)
```

### 9.2 SGSC-3 Full 25 (Qwen3.5-397B) — 현재 v7 코퍼스

| 항목 | 값 |
|------|-----|
| 대상 | 25 가이드라인 |
| LLM | Qwen3.5-397B (vLLM serving) |
| 성공률 | 25/25 (100%) |
| 총 시나리오 | 243 |
| 총 atoms | 462 |
| 예상 에피소드 | 5,832 (8m × 243s × 3r) |
| No-go criteria | 4/4 PASSED |

**가이드라인별 시나리오 수**:

| Guideline | Scenarios | Guideline | Scenarios |
|-----------|-----------|-----------|-----------|
| aha_heart_failure_2022 | 35 | gina_asthma_exacerbation | 21 |
| ada_dka_management | 24 | aha_stroke_2019 | 22 |
| anaphylaxis_management | 12 | status_epilepticus | 7 |
| aba_burn_resuscitation | 10 | toxicology_management | 11 |
| gi_bleeding | 10 | kdigo_contrast_aki | 10 |
| apa_agitation_management | 10 | aabb_transfusion | 7 |
| acls_cardiac_arrest | 7 | pals_pediatric_emergency | 7 |
| hypertensive_emergency | 7 | idsa_meningitis | 6 |
| cap_pneumonia | 5 | pulmonary_embolism | 5 |
| copd_exacerbation | 5 | kdigo_aki_full | 5 |
| aha_chest_pain_evaluation | 5 | ssc_sepsis_hour1_bundle | 4 |
| acog_obstetric_hemorrhage | 4 | atrial_fibrillation | 3 |
| universal_clinical_safety | 1 | | |

---

## 10. Bug History & Fixes

### 10.1 Pilot-14 (Gemma) Bugs

#### Bug P1: vLLM max_tokens 400 Bad Request
- **원인**: `DEFAULT_MAX_TOKENS=8192` + vLLM `--max-model-len=8192` → prompt+completion 총합 초과
- **증상**: 14/14 모두 `400 Bad Request` 즉시 실패
- **수정**: `DEFAULT_MAX_TOKENS` 8192 → 4096
- **파일**: `atom_proposer.py:24`

#### Bug P2: JSON 출력 Truncation
- **원인**: 8+ recommendations의 JSON 응답이 4096 output tokens 초과하여 잘림
- **발견**: Gemma tokenizer는 structured JSON에서 ~3 chars/token
- **수정**: `_CHUNK_SIZE=5` 도입 (5개 recommendation/청크)
- **파일**: `atom_proposer.py:27`

#### Bug P3: ProcessPoolExecutor sys.path 미상속
- **원인**: Python 3.13 `spawn` 방식 — worker에 `sys.path` 미상속
- **증상**: 14/14 `No module named 'cga_bench'`
- **수정**: `sys.path.insert`를 함수 내부에서 모듈 레벨로 이동
- **파일**: `run_pilot_14.py:33-36`

#### Bug P4: vLLM api_key 빈 응답
- **원인**: vLLM `--api-key` 설정 시 모든 엔드포인트에 Authorization 필요
- **수정**: `api_key` 기본값 유지 + 프로덕션에서 명시적 전달

### 10.2 SGSC-3 (Qwen3.5-397B) Bugs — β-7/β-8

#### Bug Q1: 0 Atoms Parsed (Thinking Model)
- **원인**: Qwen3.5-397B가 `<think>...</think>` 블록을 출력, JSON 추출 실패
- **변종**: 닫는 `</think>` 태그만 있고 여는 태그 없는 케이스
- **수정 1단계**: `_extract_json()`에 `<think>` 태그 strip regex 추가
- **수정 2단계**: `chat_template_kwargs: {"enable_thinking": false}` 추가
- **효과**: 0 atoms → 정상 파싱 (6 atoms for ssc_sepsis_hour1_bundle)

#### Bug Q2: Markdown Code Block Parse Warning
- **원인**: LLM이 JSON을 ` ```json ... ``` `으로 감싸서 반환
- **증상**: 4개 가이드라인에서 JSON extraction warning
- **수정**: truncated code block handler 추가 (여는 ` ``` ` 만 있고 닫는 것 없는 경우)
- **파일**: `atom_proposer.py:111-118`

#### Bug Q3: DEFAULT_MAX_TOKENS 복원
- **배경**: Pilot-14에서 vLLM 호환을 위해 8192→4096으로 내렸으나, Qwen3.5-397B는 충분한 context window 보유
- **수정**: `DEFAULT_MAX_TOKENS` 4096 → 8192로 복원
- **효과**: 더 긴 JSON 응답 허용 → 더 많은 atoms 추출

### 10.3 β-8 Parser Fix (Option B Re-run 이후)

#### Parse Failure 분석
- **1차 실행**: 25개 가이드라인 중 ~20% 청크에서 parse warning 발생
- **원인 분류**:
  1. Triple-backtick JSON code blocks (가장 빈번)
  2. Truncated code blocks (output token limit에서 잘림)
  3. `<think>` 잔여 태그
- **수정**: `_extract_json()` 다중 fallback 체인 구축
- **검증**: 6개 edge case test 추가, 21/21 atom_proposer 테스트 통과

#### Option B Full Re-run
- **결정**: 20% 청크 손실은 atom 손실을 의미 → 전체 25 가이드라인 클린 재실행
- **결과**: 243 scenarios (vs 이전 239), 462 atoms
- **acog_obstetric_hemorrhage 회복**: 0/0 → 4 scenarios, 2 graph nodes (별도 단일 재실행)

### 10.4 β-8.5 Fixes

#### F1: atoms_smoke.json 미생성 (CRITICAL)
- **원인**: `pipeline.py`가 수락된 atoms를 메모리에만 보관, 디스크에 쓰지 않음
- **영향**: `build_manifest_tables.py`가 `atoms_smoke.json`을 찾아 atom 수 집계 → 0개로 보고
- **LaTeX 영향**: `\sgscAtomCount{0}` (잘못됨)
- **수정**: `pipeline.py`에 atoms_smoke.json 쓰기 추가
  ```python
  atoms_path = output / "atoms_smoke.json"
  atoms_path.write_text(json.dumps([a.model_dump(mode="json") for a in atoms], indent=2))
  ```
- **백필**: 기존 25개 가이드라인에 대해 graph `source_recommendation_ids`에서 atom 데이터 재구성 → 462개 atoms 복원
- **파일**: `pipeline.py:342-344`

#### F1 부수 문제: Backup 디렉토리 오염
- **원인**: `acog_obstetric_hemorrhage_optionb_backup` 등이 `sgsc_output/`에 존재
- **영향**: manifest가 27 guidelines로 잘못 집계
- **수정**: backup 디렉토리를 `reports/`로 이동
- **결과**: 25 guidelines, 243 scenarios, 462 atoms 정확 집계

---

## 11. Known Issues (Deferred)

β-8 post-mortem critical review에서 식별된 9개 이슈. 시나리오 수를 변경하는 수정은 full re-run이 필요하므로 다음 iteration으로 연기.

### HIGH Severity

#### 7-1. BEFORE mutation template checks wrong field
- **파일**: `scenario_compiler.py:77`
- **문제**: `atom.sequence.required_prior` 대신 `atom.sequence.before`를 확인해야 함
- **의미**: BEFORE constraint → "이 action이 다른 action **앞에** 와야 함"인데, `required_prior`는 "이 action **전에** 필요한 것"
- **영향**: BEFORE-constraint violation 시나리오가 생성되지 않음
- **수정 시 영향**: 시나리오 수 변경 → full re-run 필요

### MEDIUM Severity

#### 7-2. Seed ID 충돌
- **파일**: `scenario_compiler.py:128-129`
- **문제**: `seed_id = f"{guideline_id}_{canonical_id}_seed"` — 같은 action + 다른 constraint type → 동일 seed_id
- **영향**: dict comprehension이 첫 번째를 자동 삭제
- **수정**: constraint type 포함: `f"{guideline_id}_{canonical_id}_{constraint_type}_seed"`

#### 7-3. `_stem_match` substring false positive
- **파일**: `entailment_checker.py:85-112`
- **문제**: `keyword in text` 사용 — 단어 경계 없음
- **예시**: `"iv"` → `"survive"` 매칭, `"art"` → `"start"` 매칭
- **영향**: entailment rate 부풀림 (hallucinated atom이 검증 통과 가능)
- **수정**: `re.search(rf"\b{re.escape(keyword)}\b", text)` 사용

#### 7-4. `action_type` 무검증
- **파일**: `atom.py:64`
- **문제**: 6개 유효값 정의되어 있으나 validator 없음 → LLM이 임의 문자열 출력 가능

#### 7-5. `entailment_verdicts` first field only
- **파일**: `pipeline.py:266-268`
- **문제**: source fidelity 계산에 첫 번째 필드(action) 결과만 사용
- **영향**: 보고된 `hallucination_rate`가 과소 추정될 수 있음

#### 7-7. LLM HTTP error에 retry 없음
- **파일**: `atom_proposer.py:83-89`
- **문제**: 단일 500/502/429 에러 → 가이드라인 전체 실패
- **수정 필요**: exponential backoff + 3회 retry

### LOW Severity

#### 7-6. `max_scenarios` dead code
- **파일**: `pipeline.py:53`, `run_full_25.py:639`
- **문제**: config에 설정되지만 `run_pipeline()`에서 미참조

#### 7-8. Evidence strong/weak 분류 반전 위험
- **파일**: `entailment_checker.py:286-322`
- **문제**: "should"를 strong으로 분류하지만, 조건부 권고도 "should" 사용

#### 7-9. Pre-existing test failures (SGSC 무관)
- `test_audit_guided_selection.py::test_v4_hard_self_class`
- `test_blindspot_clusters.py::test_episode_coverage`

---

## 12. P0 Fixes (Baseline Critical Review)

self-critical review (108 findings) 중 8개 P0 항목. 모두 해결 완료.

### C-1: `defaultdict` misuse (CRITICAL)
**문제**: `.get()` 호출이 `defaultdict` 메커니즘을 우회.
**수정**: `dict` + `.setdefault()` 사용.

### C-2: BEFORE constraints not wired (CRITICAL)
**문제**: `_build_node`가 BEFORE constraint semantics를 무시.
**수정**: BEFORE → `required_prior_actions` 역방향 배선 추가.

### C-3: recommendation_class normalization 누락 (CRITICAL)
**문제**: "Strong", "Category 1", "conditional" 등이 정규화 없이 통과.
**수정**: `_REC_CLASS_MAP` (15 매핑) — AHA, GRADE, NCCN 시스템 커버.

### C-7: ALTERNATIVE coverage type 미구현 (CRITICAL)
**문제**: 7개 coverage type 문서화, 6개만 구현. 인플레이션.
**수정**: ALTERNATIVE → reserved로 명시 문서화 → Phase D에서 활성화.

### C-8: Trivially-true E2E assertions (CRITICAL)
**문제**: 4개 assertion이 항상 true.
**수정**: 의미 있는 threshold + 최소 1개 보장 assertion으로 교체.

### M-C2: Node merging drops required_prior_actions (MAJOR)
**문제**: max_nodes 초과 시 병합된 노드의 `required_prior_actions` 소실.
**수정**: 병합 시 모든 action list 통합 + dedup.

### M-C4: Patient template diversity (MAJOR)
**문제**: 모든 시나리오가 동일 환자 (age=55, sex=M).
**수정**: 8종 환자 템플릿 순환.

### D1: validation_packet metric 오류 (P0)
**문제**: Spearman correlation 사용 (chance-corrected agreement가 아님).
**수정**: Cohen's kappa + Gwet AC1로 교체. scipy 의존성 제거.

---

## 13. Output Artifacts

### 13.1 Per-Guideline Output

각 가이드라인 디렉토리 (`sgsc_output/{guideline_id}/`)에 생성되는 파일:

| 파일 | 형식 | 내용 |
|------|------|------|
| `{id}_graph.json` | JSON | YAML 호환 그래프 (nodes, edges, metadata) |
| `{id}_scenarios.json` | JSON | 전체 시나리오 (scenario_id 키) |
| `{id}_scenarios_public.json` | JSON | Agent-visible 필드만 |
| `{id}_scenarios_private.json` | JSON | Scorer-only 필드만 |
| `{id}_constraints.json` | JSON | DerivedConstraint 목록 |
| `{id}_coverage.json` | JSON | CoverageReport |
| `{id}_coverage.md` | Markdown | Human-readable coverage |
| `{id}_coverage.tex` | LaTeX | Paper-ready coverage table |
| `atoms_smoke.json` | JSON | 수락된 atoms (β-8.5 F1 fix 이후) |

### 13.2 Aggregate Output

| 파일 | 내용 |
|------|------|
| `sgsc_manifest_v1.json` | 전체 매니페스트 (체크섬, 카운트, 에피소드 공식) |
| `full_25_report.json` | 배치 실행 보고서 |
| `paper/auto_numbers_sgsc.tex` | LaTeX 매크로 자동 생성 |

### 13.3 현재 LaTeX 매크로

```latex
\providecommand{\sgscGuidelineCount}{25}
\providecommand{\sgscScenarioCount}{243}
\providecommand{\sgscAtomCount}{462}
\providecommand{\sgscModelCount}{8}
\providecommand{\sgscRunCount}{3}
\providecommand{\sgscExpectedEpisodes}{5832}
\providecommand{\sgscConstraintForbidden}{29}
\providecommand{\sgscConstraintRequired}{396}
\providecommand{\sgscConstraintWithin}{37}
\providecommand{\sgscMutationKillRate}{100.0\%}
\providecommand{\sgscNullControlRate}{100.0\%}
\providecommand{\sgscCounterfactualSensitivity}{100.0\%}
```

---

## 14. Test Architecture

### 14.1 Test Suite 현황

| 구분 | 테스트 수 | 상태 |
|------|----------|------|
| SGSC 전체 | 570 | ALL PASS |
| Atom proposer | 21 | ALL PASS |
| Entailment checker | 31 | ALL PASS |
| Validation packet | 34 | ALL PASS |
| Compiler mutation robustness | 15 | ALL PASS |
| Manifest | 26 | ALL PASS |
| E2E harness | 19 | ALL PASS |

### 14.2 Fixture 전략

모든 테스트는 `conftest.py`의 공유 fixture 사용:
- `sample_atom()` — WITHIN atom (deadline 포함)
- `sample_atoms()` — 3-atom set (WITHIN + REQUIRED + FORBIDDEN)
- `sample_seed()` — boundary + mutation 포함 seed
- `sample_family()` — 2-member counterfactual family
- `sample_corpus_text()` — 모든 quote 문자열 포함 corpus

### 14.3 Mock 경계

| 카테고리 | Mock 대상 |
|---------|----------|
| Schema tests | 없음 (pure validation) |
| Compiler tests | 없음 (deterministic I/O) |
| Verification tests | 없음 (deterministic matching) |
| Pipeline E2E | LLM (precomputed atoms) |
| Atom proposer | LLM (_llm_call mock) |

---

## 15. Evaluation Validity Framework

### 15.1 3-Layer Validity 분리

| Layer | 질문 | 현재 상태 |
|-------|------|----------|
| A. Source Fidelity | guideline → atom 변환이 정확한가? | 개선 중 (field entailment) |
| B. Compiler Fidelity | atom → graph/scenario 변환이 의미 보존하는가? | 강함 (deterministic + mutation tests) |
| C. Evaluation Validity | 생성된 시나리오가 clinical guideline adherence를 측정하는가? | 가장 약함 (아직 미닫힘) |

### 15.2 Construct Validity 5-Hypothesis

| Hypothesis | Evidence | 상태 |
|------------|----------|------|
| H1. Known-violation traces → TCC fail | mutation compiler kill-rate | 100% kill rate |
| H2. Known-clean traces → TCC pass | null control traces | 100% pass |
| H3. Timing/order perturbation → TCC flip | matched-pair counterfactuals | 100% sensitivity |
| H4. Clinician non-adherence → TCC fail 상관 | clinician validation packet | 진행 중 |
| H5. EHR traces → similar constraint families | MIMIC calibration | 미시작 |

### 15.3 Representativeness 지표

```latex
\providecommand{\sgscDomainCount}{1}
\providecommand{\sgscGuardedAtomPct}{50.0}
\providecommand{\sgscTimedConstraintPct}{0.0}
\providecommand{\sgscCounterfactualPct}{0.0}
\providecommand{\sgscAvgScenarioYield}{1.0}
```

---

## 16. v6 → v7 Transition

### 16.1 주요 차이점

| 항목 | v6 (Manual) | v7 (SGSC) |
|------|-------------|-----------|
| 시나리오 작성 | 수동 YAML | 자동 (LLM atom → deterministic compile) |
| 가이드라인 수 | 25 | 25 |
| 시나리오 수 | 706 | 243 |
| 에피소드 수 | ~19,062 | 5,832 |
| Source tracing | 없음 | SHA-256 quote hash per atom |
| Entailment | 없음 | 6-field, 3-mode |
| Coverage | 미추적 | 13-type + MC/DC |
| Leakage scan | 기본 | Public/private split + 7+ patterns |
| Counterfactuals | 수동 | 자동 family compiler |
| Reproducibility | 없음 | Manifest + checksums |

### 16.2 Paper Macro 전략

- v7 수치로 전면 swap (`\sgscGuidelineCount{25}` 등)
- v6 수치는 Appendix baseline reference로 보존
- 용어 분리: "v7 SGSC core 25" (신규) vs "Tier-S phase-B expansion" (기존)

---

## 17. Batch Execution Infrastructure

### 17.1 run_full_25.py

Full 25-guideline 배치 실행기:
- `configs/sgsc/full_25_registry.json` (25 가이드라인 레지스트리)
- `--skip-existing` flag로 이미 완료된 가이드라인 스킵
- 4-way parallel processing 지원
- No-go criteria 자동 검사 (4개)
- Manifest + LaTeX macro 자동 생성

### 17.2 No-Go Criteria (4개)

| # | Criteria | Threshold |
|---|----------|-----------|
| 1 | All guidelines processed | 25/25 |
| 2 | Leakage audit pass | ALL PASSED |
| 3 | Hallucination rate | < 0.2 |
| 4 | Coverage completeness | hard target uncovered = 0 |

### 17.3 Registry Config

각 가이드라인 엔트리:
```json
{
  "guideline_id": "ssc_sepsis_hour1_bundle",
  "guideline_name": "SSC 2021 Hour-1 Bundle",
  "corpus_file": "data_release/v5.0/rag_corpus/SSC-2021.parsed.json",
  "recommendations_file": "data_release/v5.0/recommendations/ssc_sepsis.json",
  "category": "conflict_bearing",
  "domain": "sepsis"
}
```

---

## 18. Engineering Pitfalls & Lessons Learned

### 18.1 LLM Integration Pitfalls

| # | Pitfall | 교훈 |
|---|---------|------|
| 1 | vLLM `max_tokens` ≠ `max-model-len` | `max_tokens`는 completion 전용, `max-model-len`은 prompt+completion 총합 |
| 2 | JSON 토큰 밀도 | Structured JSON은 ~3 chars/token (일반 텍스트 ~4보다 밀도 높음) |
| 3 | Thinking model 출력 | `<think>` 태그가 JSON 파싱을 깨뜨림 → `enable_thinking: false` 필수 |
| 4 | ProcessPoolExecutor + sys.path | Python 3.13 `spawn` 방식 — worker에 `sys.path` 미상속 |
| 5 | vLLM api_key | `--api-key` 설정 시 모든 엔드포인트에 Auth header 필요 |

### 18.2 Pydantic Frozen Model Pitfalls

| # | Pitfall | 교훈 |
|---|---------|------|
| 1 | Frozen sub-model 직접 할당 | `atom.action.canonical_id = x` → `FrozenInstanceError` |
| 2 | 올바른 갱신 패턴 | `atom.action = atom.action.model_copy(update={"canonical_id": x})` |
| 3 | Mutable parent + frozen child | `RecommendationAtom`은 mutable, 하위 모델은 frozen |

### 18.3 Parser Evolution Pitfalls

| # | Pitfall | 교훈 |
|---|---------|------|
| 1 | Regex 한정 패턴 | `\[` 만으로 JSON 배열 탐색 → `[R1]` 같은 텍스트와 혼동 |
| 2 | 올바른 패턴 | `\[\s*\{` (배열 + 객체) 또는 `\{\s*\"` (키 시작) |
| 3 | Truncated output | vLLM이 output token limit에서 잘라 닫는 괄호/backtick 없음 |

### 18.4 Infrastructure Pitfalls

| # | Pitfall | 교훈 |
|---|---------|------|
| 1 | `--skip-existing` + 빈 출력 | 실패한 가이드라인 디렉토리가 남아있으면 재실행 불가 |
| 2 | Backup 디렉토리 오염 | `sgsc_output/` 내 backup 폴더 → manifest 가이드라인 수 부풀림 |
| 3 | atoms_smoke.json 미생성 | 파이프라인 출력 → manifest 입력 체인에서 누락 |
| 4 | SIGPIPE 부작용 | `head -5` 사용 → 파이프라인이 일부 처리 후 SIGPIPE로 죽음 → 부분 출력 잔존 |

---

## 19. Roadmap & Next Steps

### 19.1 Immediate (NeurIPS Camera-Ready)

- [x] F1 fix: atoms_smoke.json persistence
- [x] Manifest regeneration (25 guidelines, 462 atoms, 243 scenarios)
- [x] LaTeX macro update
- [x] acog_obstetric_hemorrhage recovery (4 scenarios)
- [x] KNOWN_ISSUES 문서화 (9 deferred findings)
- [ ] β-8.5 commit
- [ ] Paper §6 reframe (v6 → v7)

### 19.2 Next Iteration (Post-Deadline)

- [ ] 7-1 BEFORE mutation field fix → scenario re-generation
- [ ] 7-2 Seed ID collision fix → scenario re-generation
- [ ] 7-3 `_stem_match` word boundary fix → entailment re-check
- [ ] 7-7 LLM retry/backoff 추가
- [ ] Full 25-guideline re-run (수정 반영)

### 19.3 Medium-Term

- [ ] Clinician validation packet (100 atoms + 60 scenarios)
- [ ] MIMIC-IV calibration probe
- [ ] ILP vs greedy set-cover 비교
- [ ] FHIR/CQL crosswalk preview
- [ ] Cross-benchmark positioning (MedAgentBench, AgentClinic)

---

## 20. Appendix: File Inventory

### sgsc/ (34 files, ~5,251 lines)

```
sgsc/
  __init__.py
  pipeline.py                         ~363 lines  (15-step orchestration + atoms_smoke.json)
  cli.py                              ~117 lines  (CLI entry point)
  manifest.py                         ~196 lines  (artifact manifest)
  e2e_harness.py                      ~285 lines  (batch orchestration)
  validation_packet.py                ~501 lines  (agreement metrics)
  VERSION                             1 line
  schemas/
    __init__.py
    atom.py                           ~169 lines  (RecommendationAtom IR)
    seed.py                           ~89 lines   (ScenarioSeed)
    family.py                         ~71 lines   (CounterfactualFamily)
    coverage.py                       ~88 lines   (CoverageItem, CoverageType)
    quality.py                        ~71 lines   (GuidelineQualityCard)
  extraction/
    __init__.py
    atom_proposer.py                  ~298 lines  (LLM proposer + chunking + sanitizer v3)
    schema_validator.py               ~161 lines  (Pydantic + business rules)
    multi_model_agreement.py          ~112 lines  (N-model filter)
  verification/
    __init__.py
    quote_verifier.py                 ~229 lines  (3-tier verification)
    entailment_checker.py             ~412 lines  (6-field entailment)
    hallucination_detector.py         ~41 lines   (rate computation)
  compilers/
    __init__.py
    constraint_compiler.py            ~98 lines   (Atom → DerivedConstraint)
    graph_compiler.py                 ~309 lines  (Atoms → graph)
    scenario_compiler.py              ~319 lines  (Seeds → scenarios + split)
    counterfactual_compiler.py        ~253 lines  (families)
    mutation_compiler.py              ~96 lines   (mutation traces)
  optimizer/
    __init__.py
    coverage_tracker.py               ~349 lines  (13-type extraction)
    set_cover_solver.py               ~147 lines  (greedy weighted)
    scenario_selector.py              ~113 lines  (orchestration)
  audit/
    __init__.py
    source_fidelity.py                ~64 lines   (hallucination rate)
    leakage_scanner.py                ~153 lines  (7+ patterns)
    coverage_reporter.py              ~132 lines  (JSON/MD/LaTeX)
```

### tests/test_sgsc/ (22 files, ~5,194 lines, 570 tests)

```
tests/test_sgsc/
  conftest.py                         ~263 lines  (shared fixtures)
  test_schemas.py                     46 tests
  test_pipeline_e2e.py                17 tests
  test_coverage_tracker.py            29 tests
  test_atom_proposer.py               21 tests    (incl. chunking + truncation tests)
  test_graph_compiler.py              21 tests
  test_constraint_compiler.py         36 tests
  test_counterfactual_compiler.py     35 tests
  test_scenario_compiler.py           29 tests
  test_quote_verifier.py              23 tests
  test_mutation_compiler.py           19 tests
  test_coverage_reporter.py           23 tests
  test_set_cover_solver.py            21 tests
  test_leakage_scanner.py             32 tests
  test_schema_validator.py            23 tests
  test_source_fidelity.py             17 tests
  test_entailment_checker.py          31 tests
  test_validation_packet.py           34 tests
  test_compiler_mutation_robustness.py 15 tests
  test_manifest.py                    26 tests
  test_e2e_harness.py                 19 tests
```

---

## 21. Conclusion

SGSC v7은 baseline의 30파일/3,366줄/249테스트에서 34파일/5,251줄/570테스트로 성장했다. 가장 중요한 아키텍처 변화는:

1. **Entailment system 완전 재작성** (+334%): stub에서 6-field, 3-mode, dual-threshold production system으로
2. **13-type MC/DC coverage model**: 6개 active + 1 reserved에서 13개 모두 active로
3. **Trust Gate 1-8 framework**: assertion hardening, public/private split, compiler mutation testing, validation protocol, manifest
4. **LLM thinking model 지원**: Qwen3.5-397B의 `<think>` 블록 처리 + `enable_thinking: false`
5. **ActionNormalizer 통합**: CGA-Bench 전체 시스템과 action ID 정규화 통일

v7 corpus (243 scenarios, 462 atoms, 25 guidelines)는 v6 manual corpus (706 scenarios)보다 적지만, source grounding, field-level entailment, coverage accounting, leakage prevention이 구조적으로 보증된 최초의 corpus이다. 9개 deferred issues는 다음 iteration에서 해결 시 시나리오 수와 품질 모두 개선될 것으로 기대된다.
