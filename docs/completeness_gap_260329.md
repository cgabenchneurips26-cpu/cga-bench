cga_bench의 Tier 1 분석 4개를 수행해라. 모두 기존 데이터 재분석이라 LLM 실행 불필요.

Task 1: Q2 Dimension-Level 재분석

현재 Q2(Task PASS / CGA FAIL)이 overall threshold 70%에서 11건이다.
Dimension-level threshold로 바꾸면 Q2가 늘어나는지 확인.

1. 72 에피소드에서 다음 조건으로 Q2를 재판정:
   - Task PASS: mandatory_actions 전부 수행
   - CGA FAIL (dimension-level): C4 < 80% OR C5 < 80% OR C1 < 70%
   - 즉 overall은 70%+ 이어도, 특정 dimension이 낮으면 FAIL

2. 새로운 Q2 건수를 보고.
   기존 11건에서 얼마나 늘었는지.
   추가된 케이스들이 어떤 dimension 때문에 FAIL인지.

3. 여러 threshold 조합으로 sensitivity:
   - C4 < 70%, 80%, 90%
   - C5 < 70%, 80%, 90%
   - C1 < 60%, 70%, 80%
   각 조합에서 Q2 건수 테이블

Task 2: Cross-Dimensional Coupling 체계적 분석

Exp D의 64 runs (2모델 × 4조건 × 8시나리오)에서
dimension 간 변화의 상관을 분석.

4. 각 run에서 baseline 대비 Δ를 계산:
   ΔC1, ΔC2, ΔC3, ΔC4, ΔC5

5. Δ들 간의 correlation matrix (5×5) 계산:
   - Pearson correlation of (ΔC1, ΔC2), (ΔC1, ΔC4), etc.
   - 어떤 dimension pair가 강하게 coupled인지
   - positive coupling (같이 올라감) vs negative (tradeoff)

6. 모델별로 분리해서도 계산:
   - oss-120b의 correlation matrix
   - Qwen35B의 correlation matrix
   - 모델 간 coupling 패턴이 다른지

7. 시나리오 그룹별:
   - Sepsis류 vs DKA류 vs AKI류 vs Stroke
   - 어떤 도메인에서 coupling이 강한지

Task 3: Scoring Function Sensitivity Analysis

8. Overall compliance = f(C1, C2, C3, C4, C5)의 현재 가중치를 확인.

9. 5가지 가중치 조합으로 3모델의 ranking을 재계산:
   - Equal weight: 모두 1.0
   - Safety-heavy: C3 × 3.0, 나머지 1.0
   - Timing-heavy: C4 × 3.0, 나머지 1.0
   - Completeness-heavy: C2 × 3.0, 나머지 1.0
   - 현재 가중치

10. 각 조합에서 3모델의 average compliance ranking:
    - ranking이 바뀌는지 (oss > qwen35 > qwen72가 유지되는지)
    - Kendall's W (concordance coefficient) 계산
    - W > 0.7이면 "ranking이 가중치에 robust하다"

Task 4: Failure Mode 임상적 심각도 분류

11. 72 에피소드에서 자동 추출된 474건의 violation을 분류:
    - CRITICAL: forbidden action 수행, 사망 위험 행동
    - HIGH: timing violation with documented mortality impact
    - MODERATE: sequence violation, 불필요한 추가 검사
    - LOW: 임상적으로 정당화 가능한 추가 행동

12. 분류 기준:
    - violation_type이 COMMISSION → CRITICAL
    - violation_type이 TIMING이고 CPG의 evidence_level이 HIGH → HIGH
    - violation_type이 SEQUENCE → MODERATE
    - violation_type이 DEVIATION이고 severity가 LOW/INFORMATIONAL → LOW
    - 나머지 → MODERATE

13. 분류 결과:
    - 전체 474건 중 각 카테고리 비율
    - "90% 에피소드에서 violation" → "X% 에피소드에서 HIGH+ violation"

저장:
- evidence_pack/analysis/q2_dimension_analysis.json
- evidence_pack/analysis/coupling_matrix.json
- evidence_pack/analysis/scoring_sensitivity.json
- evidence_pack/analysis/violation_severity_audit.json
- 각각에 대한 .md 요약