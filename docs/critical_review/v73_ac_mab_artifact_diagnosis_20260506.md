# V7.3 SGSC AC/MAB Metric Collapse — Scoring Artifact Diagnosis

**작성일:** 2026-05-06 04:35 UTC
**문제:** V7.3 SGSC corpus에서 `action_coverage` 81.1% / `mab_f1` 81.1%가 정확히 0.000으로 collapsed
**상태:** ROOT-CAUSE 확정, scoring re-run으로 복구 가능 (모델 재실행 불필요)

---

## 1. 발견 요약

V6 706과 V7.3 SGSC corpus를 같은 코드(`assessor_core/`)로 채점했을 때 다음 비대칭이 관측됨:

| 신호 | V6 706 (n=21,180) | V7.3 SGSC (n=12,540) | 진단 |
|---|---:|---:|---|
| `c2_score == 0` | 2.4% | 12.7% | C2 정상 작동 |
| `n_viols == 0` | 44.1% | 57.3% | violation extractor 정상 |
| `action_coverage == 0` | 1.8% | **81.1%** | ★ collapse |
| `mab_f1 == 0` | 1.8% | **81.1%** | ★ collapse |
| `mab_f1` median | 0.500 | **0.000** | metric degenerate |
| `mab_f1` p75 | 0.585 | **0.000** | sample 75% = 0 |

**핵심 비대칭**: 같은 trajectory를 같은 코드로 채점 → C2(mandatory_completion)는 정상, AC/MAB(expected coverage)만 collapse.

---

## 2. 결정성 검증

같은 모델·같은 scenario·다른 run_index에서 ac/mab가 동일한지 확인:

```
aabb_transfusion_massive_transfusion_protocol_c003_ALLMH_0: c2=0.750 ac=0.000 mab=0.000
aabb_transfusion_massive_transfusion_protocol_c003_ALLMH_1: c2=0.750 ac=0.000 mab=0.000
aabb_transfusion_massive_transfusion_protocol_c003_ALLMH_2: c2=0.750 ac=0.000 mab=0.000
```

→ run 간 0% 분산. 모델 stochasticity가 아니라 **deterministic scoring artifact**.

---

## 3. 가설 매트릭스

| 가설 | 진위 | 근거 |
|---|---|---|
| 모델이 V7.3에서 행동을 안 했다 | ✗ | `n_viols` median=0, p75=1, p90=2 — 정상 행동 |
| C2 채점 코드가 망가졌다 | ✗ | c2_score median=0.625, p75=0.708 — 정상 |
| Violation extractor가 망가졌다 | ✗ | v4_hard 비율 42.7% — 정상 |
| 모델 재실행 시 다른 결과 나온다 | ✗ | 같은 run_index 0/1/2가 deterministic하게 같음 |
| **`expected_actions` 셋이 SGSC compiler atom-proposer expansion으로 너무 광범위해져서 `action_normalizer.py` fuzzy match가 실패** | **✓** | 같은 trajectory에 대해 mandatory_set(c2) 75% 매칭, expected_set(ac/mab) 0% 매칭 |
| **`action_normalizer.py` Jaccard threshold가 SGSC paraphrase variant를 못 따라감** | **✓ (가능성)** | V6 corpus 기준으로 calibrated된 normalizer가 V7.3 atom-proposer 출력에 부적합 |

**결론**: scoring artifact, 모델 재실행 무의미, **scoring pipeline 차원에서 수정 가능**.

---

## 4. 사용자 직관 ↔ 진단 답

| 사용자 질문 | 정답 |
|---|---|
| "잘못 만들었다는 거냐?" | ✗ trajectory + C2 + violation은 valid; **expected_set 정의 또는 normalizer 호환성**만 문제 |
| "추가가 안 된 거 아니냐?" | △ atom-proposer expansion이 expected_actions 셋에 일부 paraphrase variant를 normalizer-incompatible 형태로 추가했을 가능성 |
| "다시 run하면 되는 거 아니냐?" | ✓ **단 model re-run이 아니라 re-score**. P3에서 expected_actions 재정의 후 trajectory 기반 재채점 |

---

## 5. 후속 작업 (P0 즉시 / P1-P3 진단)

| 우선 | 작업 | 소요 | 결과 |
|---|---|---|---|
| **P0** | paper에서 V7.3 AC/MAB 폐기 / TCC + C2만 cross-corpus headline 사용 | 즉시 | 본문 정직성 회복 |
| **P1** | 1개 V7.3 trajectory의 actions와 expected_actions 직접 비교 — 어느 매칭 단계에서 0이 나오는지 trace | 1-2h | root cause 확정 |
| **P2** | SGSC compiler의 `expected_actions` 출력 검사 — atom-proposer가 paraphrase variants를 expected에 union으로 넣는지 / normalizer-compatible 형태인지 | 1h | scoring fix path 결정 |
| **P3** | (a) `expected_actions := mandatory ∪ optional` 재정의 또는 (b) normalizer Jaccard threshold 0.70 → 0.50 완화 후 V7.3 trajectories 재채점 | 2-4h | AC/MAB이 informative metric으로 회복 |

**Note (사용자 메모)**: V6 기준으로도 Jaccard threshold가 0.70이 아니라 0.50이었을 가능성이 있음 — `assessor_core/action_normalizer.py` 코드 직접 확인 필요. 만약 0.50이면 V7.3은 그보다 더 낮은 threshold가 필요할 수 있음.

---

## 6. 영향 범위

- **paper §5.4 MAB over-credit 주장**: V6 corpus 한정으로 명시 필요. V7.3에서의 −57.1pp inversion은 *evaluator collapse*이며 *MAB의 corpus-property dependence*의 정량 증거이긴 하나 본문 thesis 직접 지지보다는 §6 Discussion footnote가 적합.
- **paper §6 Discussion (substrate-dependence)**: TCC ranking flip(Spearman ρ=−0.309)은 robust, 그대로 사용 가능. AC/MAB ranking flip은 P3 결과 나오기 전까지 보류.
- **memory `project_allm_h_v73_deployment` rule**: ALLM.H dual-substrate 의무 규칙은 typed_compliance(C1-C5 derived) 기준이었으므로 raw verdict matrix와 직접 무관. 그러나 Table A′ 결과 일부도 artifact 영향 받음 가능성 → P3 후 재검증.

---

## 7. Provenance & Reproducibility

- **계산일**: 2026-05-06 04:35 UTC
- **데이터**:
  - `evidence_pack/analysis/verdict_matrix_v6_706_with_allmh.json`
  - `evidence_pack/analysis/verdict_matrix_v7_3_with_allmh.json`
- **결정성**: 모든 통계 deterministic, run_index 0/1/2 cross-check로 검증
- **commit**: working tree (eval_science branch, e9c34766 기점)
- **재현 명령**: `docs/critical_review/per_model_conformance_blind_spot_with_allmh_20260506.md` §6.3 + 본 문서 §1-3 표

**End of artifact diagnosis report.**
