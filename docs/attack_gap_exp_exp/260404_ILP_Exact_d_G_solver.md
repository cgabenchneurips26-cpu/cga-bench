> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# H1/H3/Theory 구현 — 3개 작업을 순서대로 실행

---

## 작업 1: ILP Exact d_G Solver

### 배경

현재 cpg_model/conformance_distance.py에 "4-phase tiered repair" solver가 있다.
이것은 FORBID → MUST → BEFORE → WITHIN 순서로 greedy하게 repair하므로,
각 phase가 이전 phase의 repair 결과에 의존한다.
따라서 global optimum이 아닐 수 있다.

논문에서 "exact solver"라고 쓰려면, 모든 constraint를 동시에 고려하는 
joint optimization이 필요하다.

### 구현

cpg_model/conformance_distance_ilp.py 생성:

```python
"""
ILP-based exact minimal-repair conformance distance solver.

Uses PuLP (CBC backend) to jointly optimize all repair operations
across all constraint types simultaneously.

This is the true d_G = min_{τ' ∈ L(G,p)} cost(τ → τ').
"""

from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional
import pulp

@dataclass 
class TraceAction:
    action_id: str      # canonical action name
    timestamp: float    # simulated time
    position: int       # index in trace

@dataclass
class Constraint:
    ctype: str          # 'FORBID', 'MUST', 'BEFORE', 'WITHIN'
    target: str         # action_id (or tuple for BEFORE)
    target2: str = None # second action for BEFORE(target, target2)
    deadline: float = None  # for WITHIN
    ref_time: float = None  # reference time for WITHIN
    evidence: str = None
    source_node: str = None

@dataclass
class RepairOp:
    op_type: str        # 'delete', 'insert', 'reorder', 'shift'
    target: str         # action affected
    cost: float
    detail: str         # human-readable description

@dataclass
class ExactConformanceResult:
    distance: float
    is_conformant: bool
    violations: List[dict]
    repair_plan: List[RepairOp]
    cost_breakdown: Dict[str, float]  # by constraint type
    solver_status: str
    solver_time: float

# Cost tiers (same as tiered solver for comparability)
COST = {
    'FORBID': 1000.0,
    'MUST': 5.0,
    'BEFORE': 10.0,
    'WITHIN_PER_MINUTE': 1.0,  # per minute of delay
    'WITHIN_CRITICAL': 100.0,  # if > 2x deadline
}
```

### ILP 모델링

Decision variables:

```
For each trace action i that violates FORBID:
  x_del[i] ∈ {0,1}  — delete action i

For each MUST action j not in trace:
  x_ins[j] ∈ {0,1}  — insert action j

For each BEFORE(a,b) pair where b appears before a:
  x_swap[a,b] ∈ {0,1}  — reorder a before b
  
  Alternative: use position variables
  pos[i] ∈ Z for each action → BEFORE(a,b) means pos[a] < pos[b]
  cost = sum of |pos[i] - original_pos[i]| (or simplified)

For each WITHIN(a, Δ) where t_a > ref + Δ:
  x_shift[a] ≥ 0  — shift a's timestamp earlier by this amount
  Constraint: x_shift[a] ≥ t_a - (ref + Δ) if not deleted
```

Objective: minimize total cost

```
min  Σ COST['FORBID'] * x_del[i]
   + Σ COST['MUST'] * x_ins[j]
   + Σ COST['BEFORE'] * x_swap[a,b]
   + Σ COST['WITHIN_PER_MINUTE'] * x_shift[a]
```

Constraints:

```
# FORBID satisfaction: for each forbidden action present in trace
# Either delete it or it wasn't there (already handled by only creating vars for present ones)
For each forbidden action a_i in trace:
    x_del[i] = 1  (must delete — FORBID is absolute)
    Actually: this is not a variable, it's forced. Cost is fixed.
    
Wait — FORBID is unconditional: if the action is in the trace AND forbidden,
it MUST be deleted. There's no choice. So FORBID cost is deterministic.

# MUST satisfaction: for each required action not in trace
# Must insert it (no choice if it's hard constraint)
For each required action a_j not in trace:
    x_ins[j] = 1  (must insert)
    Again, this is forced for hard constraints.

# BEFORE satisfaction: for BEFORE(a,b) where b is at position p_b and a at p_a > p_b
# Options: swap them, or delete one, or insert a before b
# ILP: binary choice among repair options
For each violated BEFORE(a,b):
    x_swap[a,b] + x_del_for_before[b] >= 1
    Cost: min(swap_cost, delete_cost)

# WITHIN satisfaction: for WITHIN(a, Δ) where t_a > ref + Δ
# Must shift a earlier (or delete a + reinsert within window)
For each violated WITHIN(a):
    overtime = t_a - (ref + Δ)
    cost = WITHIN_PER_MINUTE * overtime  (or WITHIN_CRITICAL if overtime > Δ)
```

핵심 관찰: 대부분의 hard constraint violation에서 repair가 **forced** (선택의 여지가 없음).
- FORBID action이 있으면 반드시 삭제
- MUST action이 없으면 반드시 삽입
- BEFORE가 역전되면 반드시 순서 복원
- WITHIN이 초과되면 cost는 초과 시간에 비례

따라서 ILP의 진짜 가치는 **interaction이 있는 경우**:
- FORBID action을 삭제하면 BEFORE pair가 해소될 수 있음
- MUST action을 삽입하면 BEFORE pair가 생성될 수 있음
- 순서 변경이 WITHIN deadline에 영향

이런 interaction이 없는 episode에서는 tiered solver와 ILP가 동일한 결과를 냄.
interaction이 있는 episode에서만 차이가 남.

### 구현 순서

1. `ExactConformanceDistanceSolver` 클래스 구현
2. 위의 ILP 모델 구현 (PuLP)
3. `solve(trace, constraints) -> ExactConformanceResult` 메서드
4. Post-verification: repair 적용 후 모든 hard constraint 만족 확인

### 테스트

tests/test_conformance_distance_ilp.py 생성:

1. Conformant trace → d_G = 0
2. Single FORBID → d_G = COST['FORBID']
3. Single MUST missing → d_G = COST['MUST']
4. Single BEFORE violation → d_G = COST['BEFORE']
5. Single WITHIN violation → d_G = overtime * COST['WITHIN_PER_MINUTE']
6. **FORBID + BEFORE interaction**: forbidden action 삭제가 BEFORE pair도 해소
   → ILP cost < FORBID_cost + BEFORE_cost (joint < independent)
7. **Comparison with tiered solver**: 180 episodes에서 ILP vs tiered
   → ILP ≤ tiered (항상, upper bound이므로)
   → 차이가 나는 episode 목록

### 180 episodes 비교 실행

scripts/experiments/exp_ilp_vs_tiered.py 생성:

```
180 episodes 전부에 대해:
  1. Tiered solver 실행 → d_tiered
  2. ILP solver 실행 → d_ilp
  3. 비교:
     - d_ilp == d_tiered인 episode 수
     - d_ilp < d_tiered인 episode 수 (ILP가 더 좋은 repair를 찾음)
     - d_ilp > d_tiered인 episode 수 (버그 — 있으면 안 됨)
     - Spearman ρ(d_ilp, d_tiered)
     - verdict 차이: d_ilp = 0 but d_tiered > 0 (또는 반대)
```

출력:
- evidence_pack/analysis/exp_ilp_vs_tiered.json
- evidence_pack/analysis/exp_ilp_vs_tiered.md
- 논문용 한 줄: "ILP exact solver와 tiered solver는 N/180 episodes에서 동일 결과, 
  M episodes에서 ILP가 더 낮은 cost를 찾음 (joint repair interaction)"

---

## 작업 2: BEFORE-only Perturbation Pair 구축

### 문제

E1에서 BEFORE-only n=0. Conformant trace에서 BEFORE(a,b) pair의 두 action이 
모두 존재하는 경우가 없었음.

### 탐색 전략

```python
# Step 1: 25개 CPG graph에서 모든 BEFORE constraint 추출
# 각 BEFORE(a, b)에 대해:
#   - a와 b가 모두 MUST인 시나리오가 있는지
#   - 해당 시나리오의 episode 중 conformant(CGA-Bench pass)인 것이 있는지
#   - 그 episode에서 a와 b가 모두 trace에 존재하는지

# Step 2: 존재하면 → perturbation 적용 (a와 b의 순서만 swap)
# Step 3: 존재하지 않으면 → 합성 trace 구성
```

### 합성 trace 구성 (Step 3 fallback)

```python
# BEFORE(a, b) constraint가 있는 시나리오에서:
# 1. 해당 시나리오의 모든 MUST action을 올바른 순서로 배열
# 2. a가 b보다 먼저 오도록 배치
# 3. 각 action에 적절한 timestamp 부여 (WITHIN deadline 내)
# 4. 이 trace가 d_G = 0인지 ILP solver로 확인
# 5. 확인되면: a와 b의 순서만 swap → BEFORE-only violation
# 6. terminal output (진단)은 원본 시나리오의 정답으로 설정

# 핵심: 합성 trace이지만, 실제 CPG graph의 constraint에 기반하므로
# "인위적"이 아니라 "통제된 반례"
```

### 구현

scripts/experiments/exp_before_only_perturbation.py 생성:

1. 25개 graph × BEFORE constraints 순회
2. 각 BEFORE pair에 대해 conformant trace 탐색
3. 없으면 합성 trace 구성
4. 순서 swap → BEFORE-only violation 생성
5. 모든 evaluator로 채점 + d_G 계산
6. 결과를 E1 table에 병합

목표: **최소 15-20개 BEFORE-only pairs**

출력:
- evidence_pack/exp_before_only_perturbation.json
- E1 table 업데이트 (BEFORE-only 행 추가)

---

## 작업 3: Observation-Coarsening Theorem

### 이것은 코드가 아닌 수학입니다. 하지만 논문에 들어가야 하므로 LaTeX로 작성합니다.

paper/observation_coarsening.tex 생성:

```latex
\begin{definition}[Trace projection]
\label{def:projection}
A \emph{trace projection} is a surjective map $\pi: \mathcal{T} \to \mathcal{T}'$ 
that discards some observables from the trace. We define five canonical projections:
\begin{itemize}[nosep]
\item $\pi_{\text{term}}(\tau) = y(\tau)$: terminal output only.
\item $\pi_{\text{aset}}(\tau) = \text{multiset}(\{a_t\}_{t=1}^T)$: 
  action multiset (no ordering, no timing).
\item $\pi_{\text{nord}}(\tau) = \langle a_t \rangle_{t=1}^T$ 
  with $t_t$ replaced by index: ordered actions, no wall-clock time.
\item $\pi_{\text{ntim}}(\tau) = \langle (a_t) \rangle$ 
  unordered with timestamps stripped: actions with no temporal information.
\item $\pi_{\text{nctx}}(\tau) = \langle (a_t, t_t) \rangle$ 
  with patient state $z_t$ stripped: actions+time but no conditional context.
\end{itemize}
\end{definition}

\begin{theorem}[Observation-Coarsening Blindness]
\label{thm:coarsening}
Let $m_\pi(\tau) = f(\pi(\tau))$ be any evaluator that depends only on 
the projected trace $\pi(\tau)$. Then:
\begin{enumerate}[nosep]
\item Under $\pi_{\text{term}}$: $m_\pi$ cannot distinguish violations of 
  {\sc forbid}, {\sc before}, {\sc within}, or ordering-dependent {\sc must}.
\item Under $\pi_{\text{aset}}$: $m_\pi$ cannot distinguish violations of 
  {\sc before} or {\sc within} (action set is preserved).
\item Under $\pi_{\text{ntim}}$: $m_\pi$ cannot distinguish violations of 
  {\sc within} (ordering preserved but deadlines invisible).
\item Under $\pi_{\text{nctx}}$: $m_\pi$ cannot distinguish violations of 
  conditionally-activated {\sc forbid} 
  (context guards $\gamma$ cannot be evaluated).
\end{enumerate}
Formally, for each case $k$, if $G$ contains a constraint $c$ of the 
corresponding type, there exist $\tau_1 \in L(G,\mathbf{p})$ and 
$\tau_2 \notin L(G,\mathbf{p})$ such that 
$\pi(\tau_1) = \pi(\tau_2)$ and hence $m_\pi(\tau_1) = m_\pi(\tau_2)$.
\end{theorem}

\begin{proof}
Each case follows by explicit construction (witnesses provided by 
Experiment E1, Table~\ref{tab:perturbation}):
\begin{enumerate}[nosep]
\item $\pi_{\text{term}}$: Take conformant $\tau_1$, 
  insert a {\sc forbid} action or delay a {\sc within} action past deadline. 
  Terminal output is unchanged, so $\pi_{\text{term}}(\tau_1) = \pi_{\text{term}}(\tau_2)$.
  Witnessed by 72 {\sc forbid}-only and 56 {\sc within}-only pairs in E1.
\item $\pi_{\text{aset}}$: Take conformant $\tau_1$, 
  delay a {\sc within} action (multiset unchanged) or 
  swap a {\sc before} pair (multiset unchanged). 
  Witnessed by 56 {\sc within}-only and $N$ {\sc before}-only pairs in E1.
\item $\pi_{\text{ntim}}$: Take conformant $\tau_1$, 
  delay a {\sc within} action (ordering preserved, deadline invisible). 
  Witnessed by 56 {\sc within}-only pairs.
\item $\pi_{\text{nctx}}$: Take conformant $\tau_1$ for patient without allergy, 
  change context to allergy patient (activating {\sc forbid}). 
  Actions and timestamps identical, but context changes violation status. \qedhere
\end{enumerate}
\end{proof}
```

### 논문 내 위치

Section 3 (Formalism)에서 Proposition 1을 이 Theorem으로 교체.
Proposition 2 (Monotonicity)는 B=∅ 조건을 추가하여 유지.

### E1/E3과의 연결

```
Theorem의 각 case가 E1의 각 perturbation type에 대응:
  Case 1 (π_term) → E1 전체 + E3 terminal-only
  Case 2 (π_aset) → E1 WITHIN-only + BEFORE-only
  Case 3 (π_ntim) → E1 WITHIN-only + E3 no-timestamps
  Case 4 (π_nctx) → E3 no-state (간접) 또는 별도 perturbation 추가 가능

E5 cluster structure도 이 theorem으로 설명:
  Action-set cluster = evaluators operating under π_aset
  Conformance cluster = evaluator with full trace access (no projection)
```

---

## 실행 순서

```
1. ILP solver 구현 + 테스트 (작업 1)
   → PuLP 설치 확인 (pip install pulp)
   → 테스트 통과 확인
   → 180 episodes에서 ILP vs tiered 비교

2. BEFORE-only pair 구축 (작업 2)
   → 25개 graph에서 BEFORE pair 탐색
   → conformant trace 찾기 또는 합성
   → perturbation 적용 + 전 evaluator 채점

3. Observation-Coarsening theorem (작업 3)
   → paper/observation_coarsening.tex 작성
   → main.tex Section 3에 통합

순서가 중요한 이유:
  - ILP solver가 먼저 있어야 BEFORE-only pair의 d_G를 계산할 수 있음
  - BEFORE-only 결과가 있어야 Theorem의 Case 2 witness가 완전해짐
```