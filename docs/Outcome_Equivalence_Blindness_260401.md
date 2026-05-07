C1-C5의 형식적 재정의와 Outcome-Equivalence Blindness proposition을
LaTeX 문서로 작성해줘. 코드 변경 없음, 수학적 문서 작업만.

강건성 분석 확인 수치를 활용:
- Composite A p=0.000081, ε²=0.479
- Leave-one-out 15/15 sig (p=0.0001~0.001)
- Run r0/r1/r2: p=0.0007/0.0001/0.0020
- C2 Friedman p=0.023

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Part A: Trace와 Guideline의 형식적 정의
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## Definition 1: Clinical Agent Trace

τ = ⟨(a₁, t₁, z₁), ..., (aₙ, tₙ, zₙ)⟩

- aᵢ ∈ Σ: canonical action alphabet
- tᵢ ∈ ℝ⁺: 타임스탬프 (t₁ ≤ ... ≤ tₙ)
- zᵢ: 관측 가능한 환자 상태 요약
- y(τ): terminal output (최종 진단/치료 계획)

## Definition 2: Computable Clinical Guideline

G = (Σ, Γ, C_hard, C_soft)

C_hard (위반 시 환자 안전 위협):
  - FORBIDDEN(a, γ): 조건 γ 하에서 행동 a 금지
  - WITHIN(a, Δ, γ): 조건 γ 하에서 Δ분 이내 수행
  - BEFORE(a, b, γ): 조건 γ 하에서 a → b 순서

C_soft (권고 수준):
  - MUST(a, γ): 수행 권고
  - SHOULD_WITHIN(a, Δ, γ): 권고 시간 내 수행

## Definition 3: Conformant Language

L(G) = {τ ∈ T : ∀c ∈ C_hard ∪ C_soft, τ ⊨ c}

여기서 τ ⊨ c의 의미는 constraint type별로:
- τ ⊨ MUST(a,γ): γ(z₁)=true ⟹ ∃i, aᵢ=a
- τ ⊨ FORBIDDEN(a,γ): γ(z₁)=true ⟹ ∀i, aᵢ≠a
- τ ⊨ WITHIN(a,Δ,γ): γ(z₁)=true ⟹ ∃i, aᵢ=a ∧ tᵢ≤Δ
- τ ⊨ BEFORE(a,b,γ): γ(z₁)=true ∧ ∃j(aⱼ=b) ⟹ ∃i<j, aᵢ=a

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Part B: C1-C5를 Constraint Satisfaction의 Projection으로 재정의
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 표기
- M(G,z) = {a : MUST(a,γ) ∈ C_soft, γ(z)=true} (활성 mandatory)
- F(G,z) = {a : FORBIDDEN(a,γ) ∈ C_hard, γ(z)=true} (활성 forbidden)
- D(G,z) = {(a,Δ) : WITHIN(a,Δ,γ) ∈ C_hard∪C_soft, γ(z)=true}
- S(G,z) = {(a,b) : BEFORE(a,b,γ) ∈ C_hard∪C_soft, γ(z)=true}
- A(G) = Σ \ F(G,z): 허용 행동

## 5개 Projection

C1(τ,G) = |{i : aᵢ ∈ A(G)}| / |τ|
  Path Selection: 허용 범위 내 행동 비율

C2(τ,G) = |{m ∈ M(G,z₁) : ∃i, match(aᵢ,m)}| / |M(G,z₁)|
  Mandatory Completion: 필수 행동 완료 비율

C3(τ,G) = 𝟙[∀f ∈ F(G,z₁) : ¬∃i, match(aᵢ,f)]
  Forbidden Avoidance: 금기 행동 회피 (binary)
  ※ Binary인 이유: 단일 금기 위반도 환자 위해를 초래할 수 있으므로,
  severity-weighted 평균보다 zero-tolerance가 임상적으로 적절.
  이는 CSEDB(Wang et al., 2025)의 absolute contraindication에
  대한 binary safety gate 설계와 일치.

C4(τ,G) = |{(a,Δ)∈D(G,z₁) : ∃i, match(aᵢ,a) ∧ tᵢ≤Δ}| / |D(G,z₁)|
  Timing Compliance: 시간 제약 준수 비율

C5(τ,G) = |{(a,b)∈S(G,z₁) : ∃i<j, match(aᵢ,a) ∧ match(aⱼ,b)}| / |S(G,z₁)|
  Sequence Integrity: 순서 제약 준수 비율

## CGA Score
CGA(τ,G) = Σₖ wₖ · Cₖ(τ,G), Σwₖ=1

## 참고 (future work로 언급)
이상적 메트릭은 d_G(τ) = min_{τ'∈L(G)} cost(τ→τ')이나,
이는 일반적으로 NP-hard. C1-C5 분해는 이에 대한 tractable
diagnostic decomposition으로, exact distance가 아닌
차원별 위반 진단을 제공한다.
(upper bound 관계의 formal proof는 open question으로 남김)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Part C: Propositions
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## Proposition 1 (Outcome-Equivalence Blindness)

※ 이 proposition의 역할: 이론적 가능성을 확립한 후,
BSR 실험으로 실제 빈도를 정량화하는 이론→실증 구조의 첫 단계.
Proposition 단독으로 novelty를 주장하지 않음.

Statement:
m_out: T → ℝ를 terminal-output-only metric이라 하자:
  y(τ₁)=y(τ₂) ⟹ m_out(τ₁)=m_out(τ₂)

G가 하나 이상의 nonterminal constraint를 포함하면
(WITHIN, BEFORE, 또는 FORBIDDEN 중 하나 이상),
∃τ₁,τ₂: y(τ₁)=y(τ₂) ∧ CGA(τ₁)≠CGA(τ₂)

Proof (constructive, WITHIN 케이스):
  G가 WITHIN(a,Δ,γ)를 포함, γ(z)=true라 하자.
  τ₁: a를 시점 Δ-1에 수행하는 conformant trace 구성.
  τ₂: τ₁과 동일하되, a의 timestamp만 Δ+1로 변경.
  y(τ₁)=y(τ₂) (동일 행동 집합, 동일 최종 상태).
  그러나 τ₁⊨WITHIN(a,Δ,γ), τ₂⊭WITHIN(a,Δ,γ).
  따라서 C4(τ₁)>C4(τ₂), 즉 CGA(τ₁)≠CGA(τ₂). □

  BEFORE 케이스: 동일 행동 집합에서 순서만 교환.
  FORBIDDEN 케이스: forbidden action 삽입 (terminal output 불변).

Empirical instantiation:
  "BSR 실험에서 BSR=[X]%가 관측됨 — controlled perturbation에서
  baseline metric이 동일하지만 CGA가 다른 에피소드 비율."

## Proposition 2 (Monotonic Violation Growth)

w: ViolationType → ℝ⁺가 비음수이고,
C3의 binary 구조에서 hard forbidden 위반이 CGA를 0으로 만들면,
τ에 constraint 위반을 하나 추가한 τ̃에 대해:
  CGA(τ̃) ≤ CGA(τ)

Proof sketch:
  각 Cₖ는 위반 추가 시 비증가 (C1,C2,C4,C5는 분자 비증가/분모 비감소,
  C3는 binary에서 1→0 전환만 가능). CGA = Σwₖ·Cₖ이므로 비증가. □

실증: 강건성 분석에서 monotonicity violation = 0건 확인됨.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Part D: Process Mining 용어 매핑
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

| CGA-Bench | Process Mining | Declare | 비고 |
|-----------|---------------|---------|------|
| C1 Path Selection | Fitness | — | 허용 행동 비율 |
| C2 Mandatory Completion | — | Existence(n,a) | 필수 행동 충족 |
| C3 Forbidden Avoidance | — | Absence(a) | 금기 회피 (binary) |
| C4 Timing Compliance | Temporal perspective | Timed Existence | 시간 제약 |
| C5 Sequence Integrity | — | ChainResponse(a,b) | 순서 제약 |

차별화 (6가지):
1. 구조화된 이벤트 로그 불필요 — LLM 자유 텍스트에서 정규화
2. 고정 활동 어휘 불필요 — 500+ 매핑의 ActionNormalizer
3. 텍스트 가이드라인에서 직접 형식화
4. 등급화된 맥락 의존적 채점 (binary fitness가 아님)
5. 환자 상태 조건부(context-guarded) 제약
6. 개방형 비결정적 행동 공간

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Part E: 논문에서의 배치
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

§3.1 — Definition 1-3 (Trace, Guideline, Conformance)
§3.2 — C1-C5 formal definitions + CGA Score
§3.3 — Proposition 1 (1/3 page) + "BSR로 실증" 예고
§4.1 — BSR 실험 결과 → Proposition 1의 empirical instantiation
§4.2 — 강건성: p=0.000081, leave-one-out 15/15, run 3/3
Appendix — Proposition 2 증명, PM 용어 매핑, C3 binary 근거

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
산출물
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. paper_sections/formal_definitions.tex — Definition 1-3, C1-C5
2. paper_sections/propositions.tex — Proposition 1-2 + proofs
3. paper_sections/pm_mapping.tex — 용어 매핑 + 차별화 6가지
4. paper_sections/paper_structure_guide.tex — 배치 가이드