# Orthogonal Perturbation Suite — 구현 프롬프트

## 목표

Proposition 1 (Outcome-Equivalence Blindness)의 constructive empirical proof.

핵심: conformant trace에서 **terminal output을 유지하면서** 정확히 **하나의 violation type만** 주입하고, 
각 evaluator가 잡는지 못 잡는지를 측정.

이것은 E3의 co-occurrence 문제 (BEFORE와 FORBIDDEN이 같은 24개 episode에서 공출현)를 
근본적으로 해결한다. 자연발생 데이터에서 차원 분리가 안 되면, **직접 만든다.**

## 설계

### 입력: Conformant traces

기존 180 episode 중 CGA-Bench = pass인 episode (d_G = 0, 즉 hard violation 없음).
이것들이 perturbation의 base trace가 된다.

### Perturbation types (각각 정확히 1개 violation만 주입)

**P1: WITHIN-only perturbation**
- Base trace에서 WITHIN constraint가 있는 action 1개를 선택
- 해당 action의 timestamp를 deadline + margin (e.g., +30min)으로 이동
- 나머지 action sequence, 최종 진단, 최종 관리 계획 유지
- 결과: terminal output 동일, action multiset 동일, 오직 timing만 위반

**P2: BEFORE-only perturbation**
- Base trace에서 BEFORE(a, b) constraint가 있는 pair 선택
- a와 b의 timestamp/순서만 교체 (b가 a보다 먼저 오도록)
- action multiset 유지, terminal output 유지
- 결과: 오직 순서만 위반

**P3: FORBID-only perturbation**
- Base trace에 FORBIDDEN action 1개를 삽입
- 삽입 위치: trace 중간 (다른 constraint에 영향 최소화)
- terminal output (진단, 관리 계획) 유지
- 결과: 오직 contraindicated action만 추가

**P4: MUST-omission perturbation**
- Base trace에서 MUST action 1개를 삭제
- 다른 action과 timestamp 유지, terminal output 유지
- 결과: 오직 필수 행동 1개만 누락

**P5: Null perturbation (control)**
- Base trace를 그대로 복사 (변경 없음)
- 모든 evaluator가 pass해야 함 — sanity check

### 각 perturbation에서 측정

1. 모든 evaluator의 verdict (pass/fail):
   - Terminal-output (DxEM)
   - Action-set overlap (AC-Proxy)
   - Penalized action-set (MAB-Proxy)
   - Coverage + timing (C2)
   - Typed conformance (CGA-Bench)

2. d_G (exact solver):
   - Base trace: d_G = 0
   - Perturbed trace: d_G > 0
   - d_G의 cost tier breakdown

3. BSR per perturbation type:
   - 각 evaluator가 해당 perturbation type을 얼마나 자주 놓치는가

### 구현

=== scripts/experiments/exp_orthogonal_perturbation.py 생성 ===

```python
"""
Orthogonal Perturbation Suite for Proposition 1.

For each conformant trace in the 180-episode set:
  1. Apply each perturbation type independently
  2. Score with all evaluators
  3. Compute exact d_G on perturbed trace
  4. Record which evaluators detect vs miss the injected violation
"""

# Step 1: Conformant traces 선별
# CGA-Bench = pass인 episode 필터
# 이 중 각 perturbation type을 적용할 수 있는 것만 선별:
#   P1: WITHIN constraint가 있는 action이 존재하는 trace
#   P2: BEFORE(a,b) pair가 둘 다 trace에 존재하는 trace
#   P3: FORBIDDEN action이 정의된 scenario (해당 action이 trace에 없어야 함)
#   P4: MUST action이 trace에 존재하는 trace

# Step 2: Perturbation 적용
# deep copy → single modification → terminal output 보존 확인

# Step 3: 재채점
# 각 evaluator로 perturbed trace 채점

# Step 4: 결과 집계
```

### 핵심 출력 테이블 (논문 Table)

```
| Perturbation | n_pairs | DxEM | AC-Proxy | MAB | C2 | CGA | d_G > 0 |
|-------------|---------|------|----------|-----|----|----|---------|
| Null (ctrl) |   N     | 100% pass | 100% | 100% | 100% | 100% | 0% |
| WITHIN-only |   N     | 100% pass | ?% | ?% | ?% | 100% fail | 100% |
| BEFORE-only |   N     | 100% pass | ?% | ?% | ?% | 100% fail | 100% |
| FORBID-only |   N     | 100% pass | ?% | ?% | ?% | 100% fail | 100% |
| MUST-omit   |   N     | 100% pass | ?% | ?% | ?% | 100% fail | 100% |
```

기대 결과:
- DxEM: 모든 perturbation에서 100% pass (terminal output 미변경)
- AC-Proxy: FORBID-only에서 일부 fail (action set 변경), 나머지 pass
- MAB-Proxy: FORBID-only에서 fail, 나머지 대부분 pass
- C2: WITHIN-only에서 일부 fail (timing penalty), 나머지 pass
- CGA-Bench: 모든 perturbation에서 100% fail

이 테이블이 Proposition 1의 **constructive proof**:
- 같은 terminal output
- 같은 action multiset (P1, P2에서)
- 다른 d_G
- action-set evaluators는 구별 못 함

### 추가 분석

1. **Evaluator detection rate by perturbation type**: 
   각 evaluator × perturbation type의 detection matrix → heatmap

2. **d_G distribution by perturbation type**:
   각 perturbation의 d_G 분포 (violin plot)

3. **Severity scaling**:
   WITHIN perturbation에서 delay를 5min, 15min, 30min, 60min으로 변화시키며
   d_G와 evaluator detection rate 변화 측정

### 출력

- evidence_pack/exp_orthogonal_perturbation.json
- evidence_pack/exp_orthogonal_perturbation.md
- evidence_pack/figures/exp_orth_detection_heatmap.png
- evidence_pack/figures/exp_orth_dg_distribution.png
- evidence_pack/figures/exp_orth_severity_scaling.png
- evidence_pack/tables/orthogonal_perturbation.tex (논문 핵심 테이블)

### 의존성

- ConformanceDistanceSolver (cpg_model/conformance_distance.py) — exact d_G
- 기존 evaluator scoring 함수들
- 기존 180 episode JSON

### 실행 순서

1. exact d_G solver 먼저 구현 + 테스트 통과
2. 그 다음 이 perturbation suite 실행
3. 결과를 논문에 반영

### 주의사항

- perturbation 후 trace의 internal consistency 확인:
  예: timestamp 이동 시 다른 action과의 순서가 바뀌지 않도록
  (바뀌면 BEFORE violation이 추가 발생 → orthogonality 깨짐)
- FORBID action 삽입 시, 해당 action이 다른 MUST/BEFORE에 연결되지 않는지 확인
- seed=42로 모든 random choice 고정
- 각 perturbation type별 최소 20개 pair 목표
```