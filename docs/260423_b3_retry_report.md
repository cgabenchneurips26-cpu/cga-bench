# B3 재도전: Constructive π_nord Witness — Honest Negative Result

**Date:** 2026-04-23
**Branch:** eval_science
**Commit:** `1f738a9e feat(audit): B3-retry — constructive pi_nord witness with honest floor gap`
**Related self-review:** `docs/260423_btier_self_review.md`

---

## 배경

Self-review에서 B-tier의 B3(Constructive π_nord witness)가 원래 목표("Bayes floor 0.003에 근접하는 evaluator를 만들어 Theorem 3.4 tightness를 constructive하게 증명")에 도달하지 못하고 `ActiveAgent`(TCC-derived diagnostic probe)로 피봇되었음을 발견. 사용자 지시로 재도전 수행.

---

## 원래 목표 vs 실제 결과

| 항목 | 원래 요청 | 실제 |
|---|---|---|
| Evaluator 구성 | ordered action sequence + precondition satisfaction check | ordered actions + scenario expected/forbidden sets |
| 목표 BSR | ≈ π_nord floor (0.003) | V3_half_expected = **0.4914** |
| Floor 대비 | tight witness | **164× gap** |
| Theorem 3.4 | "is tight via constructive witness" | "is an existence theorem, not a constructive recipe" |

---

## 구현 요약

### `audit/shims/pi_nord_shim.py` — `PiNordShim`

Pi_nord-admissible features만 관찰:
- `actions[*].action_id` (순서 유지, timestamp 제거)
- `expected_actions` (scenario-derived, TCC 미사용)
- `forbidden_actions` (scenario-derived, TCC 미사용)

**TCC-derived 필드 zero 접근**. `test_observed_features_are_pi_nord_admissible`가 강제 검증.

### `audit/shims/_trajectory_cache.py`

`episode_id → trajectory JSON path` singleton 인덱스. `verdict_matrix_v6.json`의 `(scenario_id, model_dir, run_index)` key로 `results/full_706_v6_aliasfix_*/<model_dir>_react/*.json` 파일과 매칭. 14,826 W8 episodes 전부 커버.

### `scripts/experiments/exp_pi_nord_witness.py`

4 variant를 14,826 episodes에 평가:

| Variant | BSR | FA | FR | Floor ratio |
|---|---|---|---|---|
| V1_strict (expected ⊆ taken ∧ no forbidden) | 0.5076 | 1042 | 6483 | 169× |
| V2_no_forbidden (commission only) | 0.5735 | 7460 | 1042 | 191× |
| **V3_half_expected (best)** | **0.4914** | 5338 | 1948 | **164×** |
| V4_any_action | 0.5735 | 7460 | 1042 | 191× |

### 매크로 (paper wire)

`evidence_pack/audit/pi_nord_witness_macros.tex`:
- `\piNordFloor` = 0.003
- `\piNordWitnessBestBSRPct` = 49.1
- `\piNordWitnessRatioToFloor` = 164
- `\piNordWitnessStrictBSR` = 0.5076
- `\piNordWitnessNoForbiddenBSR` = 0.5735
- `\piNordWitnessNEpisodes` = 14,826

### Paper §4.4 새 paragraph

"Constructive π_nord witness gap" — 164× gap을 honest하게 기록. Theorem 3.4를 **existence theorem**으로 reframe.

---

## 해석: 왜 164× gap인가

- **관찰 한계 아님**: ordered actions는 fibre를 구분하기 충분 (Theorem 3.4 관점)
- **Specification cost**: π_nord floor 도달에는 patient-conditional mandatory actions를 CPG에서 re-derive해야 함
- CPG derivation engine은 scorer-side 구성 요소 → agent-side evaluator에 구현 불가능 (scorer-agent separation rule)
- 따라서 Theorem 3.4의 floor는 **Bayes-optimal lower bound일 뿐**, 독립 재구현 없이는 도달 불가

### Reviewer 방어 효과

| 예상 공격 | 기존 답변 | 현재 답변 |
|---|---|---|
| "Theorem이 promise한 evaluator 만들 수 있나?" | 없음 (diagnostic probe만) | 164× gap 정량화, existence로 재프레이밍 |
| "Bayes floor는 design recipe인가?" | 불명확 | 명시적으로 아니라고 답변 + ceiling vs floor 포지셔닝 |

---

## 남은 작업 (camera-ready 후보)

1. **V5 variant**: CPG YAML 파싱으로 per-scenario mandatory action 추출 → gap 좁히기
2. **Patient-conditional mandatory**: `decision_table.py` 기반 evaluator (단, 이건 scorer 재구현에 해당)
3. **Sensitivity**: 각 CPG 도메인별로 gap 분석 (sepsis vs stemi vs aki 등)

---

## 검증

- **All audit tests**: 225/225 pass
- **New tests**: `tests/test_audit/test_pi_nord_shim.py` 8 tests
  - `test_observed_features_are_pi_nord_admissible`: TCC-derived 필드 접근 방지 강제
  - 다른 7개: 정상 verdict 경로 검증

---

## Commit Hash

`1f738a9e` — feat(audit): B3-retry — constructive pi_nord witness with honest floor gap
