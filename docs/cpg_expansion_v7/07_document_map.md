# CPG Selection Criteria v2 — Document & Code Map

**작성일**: 2026-04-23
**목적**: v1(M1-M6) → v2(C1-C12) CPG 분류 기준의 설계 / 구현 / 데이터 / 리포트 전 자산을 한 곳에 집약한다. 세션이 바뀌거나 리뷰어가 내부 구조를 파악할 때 이 문서에서 출발하면 된다.

---

## 1. Design / Rubric (기준 정의)

| # | 경로 | 버전 | 내용 |
|---|---|---|---|
| 1 | `docs/cpg_expansion_v7/01_selection_criteria_v1.md` | **v1 (M1-M6)** | 6개 정량지표 원 rubric — 25 CPG 역추적 근거, Tier-1 society composite M3 정의 (M3a/b/c), 배제 사례 표 |
| 2 | `docs/cpg_expansion_v7/06_selection_criteria_v2.md` | **v2 (C1-C12)** | 3-axis source-document rubric — 19점 만점, anti-circular-reasoning guarantee, per-criterion 정의 + tier threshold (S≥15 / A≥11 / B≥7) |
| 3 | `docs/attack_gap_exp_exp/260423_CPG Selection Criteria v2.md` | v2 strategic | v2 도입 배경 + attack-gap 맥락 해석 (2026-04-23, 21KB) |

## 2. Candidate Pool / Scoring Data

| # | 경로 | 내용 |
|---|---|---|
| 4 | `docs/cpg_expansion_v7/02_candidate_rescoring_99.md` | 99개 후보 M1-M6 전수 점수표 (15 areas, 54개 6점 만점) |
| 5 | `data/cpg_source_properties.json` | **25 CPG** expert annotation (C1-C12 ground truth) |
| 6 | `data/cpg_source_properties_candidates_draft.json` | **8 Tier-A 후보** authoritative annotation (2026-04-23) |
| 7 | `data/gbd_top30_causes.json` | C6 GBD burden lookup (25 graph_id → m10_score). Gap: 새 후보는 entry 없이 props.c6_score fallback 경유 |

## 3. Plan / Automation / Progress

| # | 경로 | 내용 |
|---|---|---|
| 8 | `docs/cpg_expansion_v7/03_automation_pipeline_requirements.md` | 자동화 파이프라인 요구사항 (field extraction, validation) |
| 9 | `docs/cpg_expansion_v7/04_validator_runtime_dissonance.md` | Static validator vs runtime scorer 불일치 분석 |
| 10 | `docs/cpg_expansion_v7/05_progress_log.md` | Phase 1-2 진행 로그 |
| 11 | `docs/cpg_expansion_v7/07_document_map.md` | **이 문서** |

## 4. Implementation (code)

| # | 경로 | 역할 |
|---|---|---|
| 12 | `scripts/score_cpg_v2.py` | **C1-C12 scoring engine** (~820 lines) — `compute_all_scores`, `score_c1..c12`, 3-axis aggregation, tier classification, `--candidate-props-path` / `--output-prefix` 플래그 |
| 13 | `scripts/cpg_v2_phase2b/estimate_c1_c12_for_99.py` | **Heuristic estimator** — M1-M6 + area/publisher 기반 C1-C12 보수 추정 (99 candidates) |
| 14 | `scripts/cpg_v2_phase2b/auto_extract_c1_c12.py` | **Phase C auto-extract** — 8/12 필드 regex + GBD lookup 자동 추출, 4 필드 (C7/C9/C11/C12) reviewer TODO |
| 15 | `tests/test_ci/test_score_cpg_v2.py` | 80 tests (including `TestNoCircularReasoning` 5-test 클래스) |

## 5. Reports

| # | 경로 | 내용 |
|---|---|---|
| 16 | `reports/cpg_scores_v2.{json,md}` | 25 CPG 정식 점수 (17S/7A/0B/1Excl, mean 15.6) |
| 17 | `reports/cpg_scores_v2_99_candidates_estimated.{json,md}` | 99 후보 heuristic 추정 (34S/56A/8B/1Excl) |
| 18 | `reports/cpg_scores_v2_with_candidates.{json,md}` | **33-entry 통합 scoring** (25 YAML + 8 source-only, 24S/8A/0B/1Excl, mean 15.6) |
| 19 | `reports/candidate_annotation_notes.md` | 8 후보 annotation 검토 노트 + access tier + reviewer concerns |

## 6. 전체 흐름

```
v1 (M1-M6) rubric               v2 (C1-C12) rubric
  01_selection_criteria_v1.md → 06_selection_criteria_v2.md
            │                            │
            ▼                            ▼
  02_candidate_rescoring_99.md     data/cpg_source_properties.json (25)
      (99 candidates, M1-M6)              │
            │                             ▼
            │                     scripts/score_cpg_v2.py
            │                             │
            ▼                             ▼
  estimate_c1_c12_for_99.py ─────► cpg_scores_v2_99_candidates_estimated.md
      (heuristic M→C)
            │
            ▼
  auto_extract_c1_c12.py        cpg_source_properties_candidates_draft.json (8)
      (Phase C)                            │
            │                              ▼
            └────────────►  cpg_scores_v2_with_candidates.md (authoritative 33)
```

## 7. 읽는 순서 추천

1. **전체 파악**: `06_selection_criteria_v2.md` → 본 문서(`07_document_map.md`) → `reports/cpg_scores_v2_with_candidates.md`
2. **구현 확인**: `scripts/score_cpg_v2.py` docstring → `compute_all_scores` / `score_c6`-with-props override → `tests/test_ci/test_score_cpg_v2.py::TestNoCircularReasoning`
3. **데이터 확인**: `data/cpg_source_properties.json` (sample entry `aha_chest_pain_evaluation`) → `data/cpg_source_properties_candidates_draft.json` (sample `ada_hhs_2024`)

## 8. Known gaps / follow-ups

- `data/gbd_top30_causes.json` 는 25 core graph 만 커버. 새 후보는 `props.c6_score` 로 우회 (2026-04-23 score_c6 fix).
- `cpg_source_properties_candidates_draft.json` 의 8개 중 2개(`ata_thyroid_storm_2016` → JTA/JES, `aasld_acute_liver_failure_2023` → ACG)는 publisher 오기재로 rename 필요.
- 91 remaining candidates (99 − 8) 는 bulk auto_extract 대기 (Phase 2b 후속).
- v2 rubric 도입에 따른 논문 macro 재확인: `\numGraphsTotal{25}` 유지하되 `universal_clinical_safety` 는 meta-graph 각주 추가.
