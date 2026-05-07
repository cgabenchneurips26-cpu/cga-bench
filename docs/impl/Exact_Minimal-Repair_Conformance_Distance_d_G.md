> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# Exact Minimal-Repair Conformance Distance d_G — 구현 프롬프트

## 배경

논문의 central formal object는 다음과 같다:

```
d_G(τ, p) = min_{τ' ∈ L(G, p)} cost(τ → τ')
```

여기서:
- τ = agent trace ⟨(z_t, a_t, t_t)⟩, action sequence + timestamps
- L(G, p) = guideline G와 patient context p에 대한 conformant trace language
- cost(τ → τ') = trace를 τ에서 τ'로 변환하는 최소 편집 비용
- conformant = 모든 hard constraint 만족

현재 구현은 violation counting (upper bound)만 한다.
이것을 exact minimal-repair distance로 교체해야 한다.

## Constraint 구조 분석

4가지 constraint operator:

1. **FORBID(a, γ)**: patient context γ가 활성이면 action a를 수행하면 안 됨
   - Violation: a가 trace에 존재
   - Repair: a를 삭제 (cost = cost_forbid)

2. **MUST(a, γ)**: action a를 반드시 수행해야 함
   - Violation: a가 trace에 없음
   - Repair: a를 적절한 위치에 삽입 (cost = cost_omit)

3. **BEFORE(a, b)**: action a가 action b보다 먼저 수행되어야 함
   - Violation: b가 a보다 먼저 수행됨 (또는 a 없이 b만 수행)
   - Repair: a와 b의 순서를 교체 (cost = cost_swap)
   - 또는: a를 b 이전에 삽입 (cost = cost_insert)

4. **WITHIN(a, Δ, t_ref)**: action a가 reference 시점 t_ref로부터 Δ 이내에 수행되어야 함
   - Violation: a의 timestamp t_a > t_ref + Δ (또는 a 미수행)
   - Repair: a의 timestamp를 t_ref + Δ 이내로 이동 (cost = cost_delay × (t_a - t_ref - Δ))

## 핵심 관찰: repair는 독립적이지 않다

단순히 각 violation을 독립적으로 repair하면 overcounting이 발생한다:
- FORBID action을 삭제하면 BEFORE constraint의 순서 관계가 바뀔 수 있음
- MUST action을 삽입하면 WITHIN deadline에 영향을 줄 수 있음
- Action 순서를 변경하면 다른 BEFORE constraint에 cascading 영향

따라서 **joint optimization**이 필요하다.

## 구현 방법: Tiered Constraint Satisfaction + Minimum-Cost Repair

### 접근법 1: ILP (Integer Linear Programming) — 권장

```python
# 각 repair operation을 binary decision variable로 모델링

# Variables:
# x_delete[i] ∈ {0,1}: trace의 i번째 action을 삭제할지
# x_insert[j] ∈ {0,1}: missing action j를 삽입할지
# x_swap[i,j] ∈ {0,1}: action i와 j의 순서를 교체할지
# x_shift[i] ≥ 0: action i의 timestamp를 얼마나 이동할지

# Objective: minimize total cost
# min Σ cost_forbid × x_delete[i] 
#   + Σ cost_omit × x_insert[j]
#   + Σ cost_swap × x_swap[i,j]
#   + Σ cost_delay × x_shift[i]

# Subject to:
# 1. 모든 FORBID constraint 만족 (forbidden action이 삭제되거나 없어야 함)
# 2. 모든 MUST constraint 만족 (required action이 존재하거나 삽입되어야 함)
# 3. 모든 BEFORE constraint 만족 (순서가 맞거나 교체되어야 함)
# 4. 모든 WITHIN constraint 만족 (deadline 내이거나 shift되어야 함)
# 5. Repair 후 trace가 self-consistent (삭제 + 삽입 + 교체 + shift 결과가 유효)
```

### 접근법 2: DP (Dynamic Programming) — 대안

Action sequence를 state로, constraint satisfaction을 transition으로 모델링.
State: (현재 action 위치, 만족된 constraint set)
Transition: skip(delete), include, insert, reorder
이것은 constraint 수가 작을 때 (< 50 per scenario) tractable.

### 접근법 3: A* Search — 대안

Initial state: 원본 trace
Goal: 모든 hard constraint 만족
Operations: delete, insert, swap, shift
Heuristic: 남은 미만족 constraint 수 × min cost
이것은 trace가 짧고 constraint가 적을 때 효율적.

## 구현 요구사항

=== cpg_model/conformance_distance.py 생성 ===

```python
class ConformanceDistanceSolver:
    """
    Exact minimal-repair conformance distance d_G(τ, p).
    
    Given:
        trace: List[Action] with timestamps
        constraints: List[TypedConstraint] (active for this patient)
    
    Returns:
        distance: float (0 = conformant, > 0 = nonconformant)
        repair_plan: List[RepairOperation]
        witness: List[ViolatedConstraint]
    """
```

### Cost function (tiered — 임상적 우선순위 반영)

```python
COST_TIERS = {
    'FORBID': 1000.0,    # 환자 안전 — 최고 우선순위
    'WITHIN_CRITICAL': 100.0,  # 시간 긴급 (e.g., antibiotics within 60min)
    'BEFORE': 10.0,      # 순서 위반
    'MUST': 5.0,         # 누락 (required action)
    'WITHIN_SOFT': 1.0,  # 시간 초과 (비긴급)
}
```

### ILP 구현 상세

scipy.optimize.linprog 또는 PuLP 라이브러리 사용.

Decision variables per episode:
- 각 trace action에 대해: delete (binary)
- 각 missing MUST action에 대해: insert (binary)  
- 각 BEFORE pair에 대해: swap (binary)
- 각 WITHIN violation에 대해: time_shift (continuous, ≥ 0)

Constraints:
- FORBID: 만약 action a_i가 FORBID이면, x_delete[i] = 1이거나 원래 없어야 함
- MUST: 만약 action a_j가 MUST이면, trace에 존재하거나 x_insert[j] = 1
- BEFORE(a, b): 만약 trace에서 b가 a 앞이면, x_swap[a,b] = 1이거나 
  x_delete[b] = 1이거나 x_insert[a_before_b] = 1
- WITHIN(a, Δ): 만약 t_a > t_ref + Δ이면, x_shift[a] ≥ t_a - (t_ref + Δ)

Objective: minimize weighted sum of all repair operations.

### 중요: BEFORE constraint의 cascading 처리

BEFORE(a, b)와 BEFORE(b, c)가 동시에 있을 때:
- a, b, c의 순서가 모두 맞아야 함
- swap(b, a)을 하면 BEFORE(b, c)에 영향 줄 수 있음
- 이것은 topological sort constraint로 모델링:
  repair 후의 action sequence가 모든 BEFORE pair에 대해 valid partial order

이것을 ILP로:
- position[i] ∈ Z: repair 후 action i의 위치
- BEFORE(a, b) → position[a] < position[b]
- 원래 위치와 다르면 cost 발생

### 출력

```python
@dataclass
class ConformanceResult:
    distance: float                    # d_G(τ, p)
    is_conformant: bool               # d_G == 0
    violations: List[Violation]        # 각 위반의 (type, constraint, trace_segment)
    repair_plan: List[RepairOp]       # 최소 비용 repair 경로
    repair_trace: List[Action]        # repair 적용 후의 conformant trace
    cost_breakdown: Dict[str, float]  # tier별 비용 분해
```

### 테스트

=== tests/test_conformance_distance.py 생성 ===

1. **Conformant trace → d_G = 0**: 모든 constraint 만족하는 trace
2. **Single FORBID → d_G = cost_forbid**: forbidden action 1개만 있는 trace
3. **Single MUST missing → d_G = cost_must**: required action 1개만 누락
4. **Single BEFORE violation → d_G = cost_swap**: 순서 1쌍만 역전
5. **Single WITHIN violation → d_G = cost_delay × overtime**: deadline 초과
6. **Co-occurring violations → d_G < sum(individual)**: joint repair가 독립 repair보다 저렴
7. **Cascading BEFORE → correct cascade**: BEFORE(a,b) + BEFORE(b,c) + trace순서 c,a,b
8. **FORBID + MUST interaction**: forbidden action을 삭제하면 MUST도 해소되는 경우
9. **Monotonicity**: violation 추가 시 d_G가 감소하지 않음 (Proposition 2 검증)
10. **Determinism**: 같은 입력 3회 → 같은 d_G

### 전체 episode 실행

=== scripts/experiments/exp_exact_dg.py 생성 ===

기존 180 episode 전체에 대해 exact d_G를 계산:

1. 각 episode에 대해:
   - active constraints 도출 (ConstraintDerivationEngine)
   - exact d_G 계산 (ConformanceDistanceSolver)
   - violation counting surrogate도 함께 계산

2. exact vs surrogate 비교:
   - Spearman ρ (ranking agreement)
   - Pearson r (linear agreement)  
   - pass/fail verdict가 달라지는 episode 수
   - rank reversal count

3. exact d_G 기반 새 분석:
   - cost tier별 분해 (안전 vs 시간 vs 순서 vs 누락)
   - 모델별 평균 d_G
   - evaluator별 BSR을 exact d_G > 0으로 재계산
   - repair plan의 가장 빈번한 operation type

출력:
- evidence_pack/exp_exact_dg.json
- evidence_pack/exp_exact_dg.md
- evidence_pack/figures/exp_exact_dg_scatter.png (exact vs surrogate)
- evidence_pack/figures/exp_exact_dg_tier_breakdown.png
- evidence_pack/tables/exact_dg.tex

### 성능 요구

- 180 episodes × ~25 constraints/episode 
- ILP: PuLP + CBC solver, 각 episode < 1초 목표
- 전체: < 5분
- 만약 느리면: scipy.optimize.milp 또는 constraint 수 기반 DP fallback

### 의존성

- PuLP (pip install pulp) — CBC solver 내장
- 또는 scipy.optimize.milp (scipy ≥ 1.9)
- numpy, dataclasses

### 주의사항

- soft constraint는 d_G 계산에서 제외 (hard-conformance만)
- soft violation은 별도 V_soft(τ) multiset으로 보고
- cost tier 값은 config로 분리 (sensitivity analysis 가능하도록)
- repair_trace는 실제로 모든 constraint를 만족하는지 post-verification 필수