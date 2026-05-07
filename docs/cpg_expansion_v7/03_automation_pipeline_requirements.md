# CPG Automation Pipeline — Requirements & Roadmap

**작성일**: 2026-04-22
**목적**: "guideline document → CPG YAML graph" 자동 생성 파이프라인을 production-ready로 만들어 v7 확장을 **공정·재현 가능**하게 수행. 리뷰어 질문 "54개를 수동 작성하면 confirmation bias 아닌가?"에 대한 defence.

---

## 1. 현재 상태 (정확한 스냅샷)

### 1.1 존재하는 컴포넌트

- **`semantic_layer/cpg_parser.py`** — LLM 기반 구조화 추출 (부분 완성)
  - ✅ PDF/텍스트 chunk 처리 (`_extract_from_chunk`, L182-283)
  - ✅ LLM JSON schema structured output (L227-251)
  - ✅ 권고 강도 / 카테고리 / 타이밍 파싱 (L313-351)
  - ❌ **Source traceability 미구현**: `ExtractedRecommendation` dataclass에 `source_guideline/section/quote` 필드 **부재** (L46-62)
  - ❌ Evidence level 자동 매핑 미흡 (Class I/IIa/IIb → "1A/1B/2A" 변환 규칙 없음)
  - ⚠️ 프롬프트가 일반적 (domain별 few-shot 없음)

- **`semantic_layer/constraint_derivation.py`** — graph → constraints 방향 (역방향 X)

- **`assessor_core/action_normalizer.py`** — 710줄, direct mapping + pattern rules + fuzzy matching (있음)

- **`cpg_model/patient_generator.py`** — CPG YAML → 시나리오 4-axis derivation (✅ 완성)

- **`scripts/ci/validate_cpg_schema.py`** — 스키마 검증 (존재, integration 안 됨)

- **`data_release/v5.0/rag_corpus/*.parsed.json`** — 이미 텍스트 추출된 guideline 25개 (입력 준비됨)

### 1.2 **결정적 사실**: upstream 자동화는 없다

- Git 히스토리 역추적: held-out 5개(`aba_burn`, `acog_obstetric`, `apa_agitation`, `pals_pediatric`, `toxicology_management`) 모두 **수작업 YAML 작성**으로 커밋됨 (커밋 `aba39e4a` 등)
- `cpg_parser.py`는 import되는 곳이 3개뿐 — tests, llm_assist_agent, action_normalizer. **Production에서 CPG YAML 생성에 사용된 흔적 0.**
- `docs/EXTENDING_CGA_BENCH.md`는 YAML을 **직접 작성하는 방법**만 안내.

→ 99개 전부 수작업 YAML은 34×(300-400 lines) = **~26시간 전문가 시간**. 그리고 이것은 리뷰어에게 "confirmation bias-free하다"를 증명할 수 없다.

---

## 2. Component Gap Matrix

| ID | Component | 현재 상태 | Gap | 복잡도 |
|---|---|---|---|---|
| A | Guideline ingestion (PDF/HTML → text) | `rag_corpus/*.parsed.json` 있음 | 메타데이터 추출 (title/year/society/DOI) 자동화 | Low |
| B | Rule extraction LLM prompt | 일반 프롬프트 (`cpg_parser.py:182`) | Domain-specific few-shot (SSC sepsis, STEMI, stroke 예시) | Med |
| C | Structured schema | `ExtractedRecommendation` 있음 | `source_guideline/section/quote/page` 필드 추가 (Phase 1 필수) | Low |
| D | Deadline/constraint normalization | "within 60 minutes" → `deadline_minutes: 60` 기본 구현 | 다양한 표현 ("immediately", "within 1h", "3-hour bundle") 정규화 | Low |
| E | Action ID canonicalization | `action_normalizer.py` 710 lines | LLM fallback confidence 0.75 → 0.85+ 필요 | Med |
| F | **Source traceability** | **없음** | 각 rule → guideline page/section/exact quote 매핑. Provenance index 구축 | **High** |
| G | **Cross-reference validation** | **없음** | 기존 CPG와 신규 rule 간 action/deadline 충돌 detection | **High** |
| H | Schema CI validation | validate 스크립트 존재 | auto-pipeline에 gate로 integration | Med |
| I | **Human review workflow** | **없음** | Clinician review packet (HTML/PDF) + approve/edit/reject UI + audit log | **High** |
| J | Evidence level tagging | 필드만 정의 | Class I/IIa/IIb → strength 매핑 규칙 | Med |

**결정적 Gap 3개**: F (source traceability), G (cross-ref), I (human review) — 모두 현재 **0% 구현**. 리뷰어 방어의 핵심.

---

## 3. 3-Phase Roadmap

### Phase 1 — MVP (wall-clock 1-2일)

**목표**: "guideline text → YAML draft" end-to-end 동작

**구현**:

1. `cpg_parser.py` 개선 (40 LOC):
   - `ExtractedRecommendation` dataclass에 `source_section: str, source_quote: str, source_page: int` 추가
   - `_extract_from_chunk` prompt에 "Include the exact original quote and section number" 지시

2. YAML generator 신규 (200 LOC):
   ```python
   # semantic_layer/cpg_yaml_generator.py
   class CPGYAMLGenerator:
       def generate_yaml(parsed: ParsedGuideline) -> dict:
           """ParsedGuideline → CPG graph YAML (nodes/edges/mandatory/forbidden)"""
   ```

3. 통합 엔트리 (150 LOC):
   ```python
   # scripts/auto_generate_cpg.py
   def generate_cpg_from_guideline(pdf_path, domain):
       parsed = CPGParser(llm).parse_file(pdf_path, domain)
       yaml_graph = CPGYAMLGenerator().generate_yaml(parsed)
       write_yaml(f"cpg_model/graphs/auto/{domain}.yaml", yaml_graph)
       return yaml_graph, parsed
   ```

4. Test (100 LOC):
   - `tests/test_semantic_layer/test_cpg_auto_generation.py`
   - SSC sepsis.parsed.json을 입력으로 넣어 기존 `ssc_sepsis_hour1.yaml`과 diff

**산출물**: `cpg_model/graphs/auto/*_auto.yaml` 5개 샘플 (검증용, 수작업 vs 자동 비교)

### Phase 2 — Review + CI (wall-clock 1-2일)

**목표**: 전문가 검수 + 자동 schema 검증 + git integration

**구현**:

1. Review packet generator (250 LOC):
   ```python
   # semantic_layer/review_packet_generator.py
   def generate_review_packet(parsed):
       return {
           "recommendations": [
               {
                   "rec_id": rec.id,
                   "original_text": rec.text,
                   "source_page": rec.source_page,
                   "source_quote": rec.source_quote,
                   "parsed_action_id": rec.action_id,
                   "parsed_deadline": rec.deadline_minutes,
                   "clinician_review": {"status": "pending", ...}
               }
           ]
       }
   ```

2. Review web UI (FastAPI + React, 500 LOC):
   - GET `/review/{cpg_id}` — packet 렌더
   - POST `/review/submit/{cpg_id}` — 승인/수정 저장
   - 기존 `clinician_validation/` 패턴 재사용 가능

3. CI validator integration (150 LOC):
   ```python
   # scripts/ci/auto_cpg_validator.py
   def validate_generated_yaml(yaml_path):
       errors = []
       errors.extend(schema_validate(yaml_path))       # 기존 validate_cpg_schema.py 활용
       errors.extend(check_action_ids(yaml_path))      # action_normalizer.py 활용
       errors.extend(check_source_complete(yaml_path)) # 신규 F-component gate
       errors.extend(check_conflicts_25cpg(yaml_path)) # 신규 G-component gate
       return errors
   ```

4. Git commit 자동화 (100 LOC):
   ```python
   # scripts/auto_commit_cpg.py
   # Approved YAML → git commit
   # Commit msg: feat(cpg): Add {domain} from {guideline_source}
   #             Clinician review: {clinician_email}
   #             Source: {DOI/URL}
   #             Confidence: medium (auto-generated + human-reviewed)
   ```

**산출물**: web UI, review audit log, CI gate

### Phase 3 — Scale-out (wall-clock 1일)

**목표**: 54개 6점 후보 배치 실행

**구현**:

1. 배치 러너 (200 LOC):
   ```python
   # scripts/batch_generate_cpgs.py
   # 54개 병렬 처리 (max_parallel=4, LLM rate limit 고려)
   # ProcessPoolExecutor + as_completed
   ```

2. Quality report (150 LOC):
   - Success rate, source traceability completeness, conflict count, schema pass rate
   - `batch_report_20260424.json`

3. Tracking dashboard (200 LOC):
   - 실시간 생성 상태
   - Auto-approve ready vs review needed 분류

**산출물**:
- `cpg_model/graphs/auto/*.yaml` 54개
- `batch_report_*.json`
- Review packet 54개 → clinician batch review (병렬 12 reviewers × 5개씩 1시간 = 1일)

---

## 4. 총 일정 (wall-clock)

| Phase | 작업 | 기간 |
|---|---|---|
| 1 | MVP | 1-2일 |
| 2 | Review+CI | 1-2일 |
| 3 | Scale-out (54 CPG 생성 + 검수) | 1일 (+ clinician 검수 1일 병렬) |
| — | v7 sweep 전체 | 0.5일 (12시간 compute) |
| **Total** | — | **5-7일** |

**비교**: 수작업 시 54개 × 45분 = 40시간 (5일) + 검증/디버깅 불확실 + 리뷰어 방어 불가.

---

## 5. 리뷰어 방어 프레임

### 5.1 논문 Appendix 서술 (draft)

> **CPG Graph Construction via Automated Extraction Pipeline**
>
> To ensure fairness and reproducibility of our v7 expansion from 25 to 79 CPGs, we developed an automated extraction pipeline rather than hand-authoring YAML graphs. The pipeline consists of three stages:
>
> **(1) Reproducible Extraction**: For each candidate guideline, we apply LLM-based structured extraction (Qwen-30B, temperature=0, versioned prompt v1.0) to produce Pydantic-typed recommendations. Every extracted rule carries source provenance: `source_guideline`, `source_section`, and `source_quote` (verbatim text span from the original document). Extraction prompts are committed to git; repeat runs yield identical outputs.
>
> **(2) Systematic Normalization**: Extracted action identifiers are mapped to CGA-Bench's canonical action vocabulary through a five-layer normalizer (exact match → abbreviation expansion → domain-specific mapping → fuzzy match → LLM semantic match with confidence ≥ 0.85). Ambiguous mappings are flagged for clinician review.
>
> **(3) Clinician-in-the-Loop Review**: Each auto-generated YAML is paired with a review packet presenting the original quote, parsed interpretation, and proposed action mapping. Board-certified emergency physicians (N ≥ 3 per guideline) approve, edit, or reject each recommendation via a web interface. Inter-rater disagreement triggers adjudication. Only unanimously approved (or adjudicated) YAMLs are committed.
>
> This approach yields a fully-provenance-traced v7 benchmark while distributing cognitive load across automated extraction (reproducibility) and expert review (clinical validity).

### 5.2 기대 리뷰어 반응

- "왜 이 가이드라인은 포함되고 저건 제외되었나?" → **M1-M6 rubric score ≥ 4 cutoff** (measurable)
- "Hand-authoring bias 아닌가?" → **automated extraction + human review 이중 프로세스** (rebuttal)
- "Provenance 보장?" → **source_quote 필드로 원문 trace 가능** (open audit)
- "Reproducibility?" → **temperature=0, versioned prompts, full pipeline code committed** (re-runnable)

---

## 6. 즉시 실행 항목 (Priority 1)

| # | 파일 | 변경 | 담당 | ETA |
|---|---|---|---|---|
| 1 | `semantic_layer/cpg_parser.py` | `ExtractedRecommendation`에 source fields 추가 (L46-62) | (미정) | 30min |
| 2 | `semantic_layer/cpg_parser.py` | `_extract_from_chunk` prompt v1.0 확정 (L182-220) | (미정) | 2h |
| 3 | `semantic_layer/cpg_yaml_generator.py` | 신규 파일 | (미정) | 4h |
| 4 | `tests/test_semantic_layer/test_cpg_auto_generation.py` | 신규 테스트 | (미정) | 2h |
| 5 | `scripts/auto_generate_cpg.py` | 신규 entry point | (미정) | 2h |
| 6 | `scripts/ci/auto_cpg_validator.py` | 신규 CI gate | (미정) | 3h |

**Phase 1 예상 총 소요**: 13-15시간 (1-2일)

---

## 7. 리스크 및 블로커

### 7.1 LLM 추출 정확도

- **리스크**: SSC sepsis에서 "60분 내 항생제"를 "60분 이내 *항생제 투여 시작*"으로 정확히 파싱할 확률 ~80%
- **완화**: Phase 1의 5개 샘플에서 기존 수작업 YAML과 diff 측정. 80% < accuracy < 95% 구간이면 프롬프트 iteration. ≥ 95%면 Phase 2 진행.

### 7.2 Clinician 검수 capacity

- **리스크**: 54개 × 30분/CPG = 27시간 검수. 병렬 3명 필요
- **완화**: 6점 만점만 Phase 3 → 나머지 A/B tier는 v8로 defer

### 7.3 기존 25 CPG와의 충돌

- **리스크**: 같은 action이 다른 deadline 제약을 가지면 evaluation 붕괴
- **완화**: G-component (cross-ref validator)가 CI gate로 차단

---

## 8. 관련 문서

- `docs/cpg_expansion_v7/01_selection_criteria_v1.md` — 선정 기준 rubric (input)
- `docs/cpg_expansion_v7/02_candidate_rescoring_99.md` — 점수화 결과 (54개 6점 타겟)
- `docs/EXTENDING_CGA_BENCH.md` — 기존 수작업 workflow (이 문서가 대체)

## 9. 관련 코드

- `semantic_layer/cpg_parser.py` — Phase 1 수정 대상
- `semantic_layer/constraint_derivation.py` — graph→constraints (참조만)
- `assessor_core/action_normalizer.py` — E-component 재사용
- `scripts/ci/validate_cpg_schema.py` — H-component 재사용
- `cpg_model/patient_generator.py` — downstream (수정 불필요, 이미 자동)
- `clinician_validation/` — I-component UI 재사용

---

## 10. 변경 이력

- **v1 (2026-04-22)**: 99 CPG 전수 점수화 직후 작성. cpg_parser.py 현황 + 3-phase roadmap 확정.
