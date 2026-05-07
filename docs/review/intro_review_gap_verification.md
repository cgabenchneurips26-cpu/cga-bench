# CGA-Bench 실험 결과 검증 프롬프트

> **원칙**: Claude Code가 생성한 코드와 결과를 "독립적으로 재현"하거나
> "입력 데이터 → 출력 수치 경로를 수동 추적"하여 검증한다.
> 아래 검증은 의심 수준별로 정렬: 🔴 매우 의심 → 🟡 확인 필요 → 🟢 경미

---

## 🔴 검증 1: P0-1 "k=1.8~4.0 전체에서 유의" — 정말인가?

**의심 근거:**
- 기존 문서에서 k=1.9일 때 p=0.073(ns)이라고 명시되어 있었음
- 그런데 실험 결과는 "k=1.8~4.0 전체에서 유의"라고 함
- 이 두 사실이 모순됨. k=1.9가 ns인데 k=1.8이 유의할 수 있는가?
- "23/36 포인트에서 유의"면 13개는 비유의 → "전체에서 유의"라는 표현이 과장일 수 있음

```
다음 검증 작업을 수행해줘. 기존 P0-1 실험 코드를 읽되, 직접 재실행하지 말고
코드 로직과 데이터를 추적하여 결과를 검증해.

## 검증 항목

### 1-A: k=1.8~4.0 "유의" 주장의 정확한 의미
- `scripts/experiments/k_space_sensitivity.py`를 열어서:
  - k별 p-value가 저장된 정확한 변수/파일 위치 확인
  - `evidence_pack/analysis/k_space_sensitivity.json` 을 열어서
    k=1.8, 1.9, 2.0, 2.1 각각의 정확한 p-value 확인
  - 특히 **k=1.9의 p-value**가 기존 문서의 0.073과 일치하는지 확인
  - 불일치하면: 어떤 데이터를 사용했는지 (single-run vs multi-run means) 확인

### 1-B: Friedman 입력 데이터 검증
- Friedman 검정에 들어간 실제 행렬(4 models × 15 scenarios)을 출력해줘
  - k=2.0일 때의 composite score 행렬
  - scipy.stats.friedmanchisquare()에 전달된 정확한 4개 배열
- 이 행렬에서 수동으로 Friedman statistic을 계산하면 같은 결과가 나오는지 확인

### 1-C: "23/36 유의" vs "전체에서 유의" 표현 검증
- 36개 k값 중 p<0.05인 것과 p≥0.05인 것을 나열
- p≥0.05인 13개 k값이 어디에 분포하는지 확인 (낮은 k? 높은 k?)
- "k=1.8~4.0 전체에서 유의"라는 요약이 정확한지 판단

### 1-D: multi-run means vs single-run 혼동 확인
- 기존 문서: "p=0.043 (single-run) / p=0.013 (multi-run means)"
- P0-1이 어떤 것을 primary로 사용했는지 확인
- k=2.0에서의 p-value가 0.043인지 0.013인지 0.007인지 확인
  (결과에 "p_raw=0.007"이라고 되어 있는데, 기존 문서의 어떤 수치와도 불일치)

## 출력
- k=1.8, 1.9, 2.0, 2.1 각각의 정확한 p-value (소수점 4자리)
- 사용된 데이터가 single-run인지 multi-run means인지
- 기존 문서(`composite_formula_comparison.md`)의 수치와의 일치/불일치 여부
- 불일치가 있으면 원인 분석
```

---

## 🔴 검증 2: P0-2 "16/18 쌍에서 구별 불가" — 부트스트랩이 올바르게 구현되었는가?

**의심 근거:**
- "16/18 쌍에서 CI가 0 포함" = 거의 모든 모델 쌍이 구별 불가
- 이것이 사실이면, 벤치마크가 모델을 구별하는 능력이 거의 없다는 뜻
- 논문에 이대로 쓰면 오히려 자해(self-harm) — Claude Code가 이 함의를 이해하고 있었는가?
- 부트스트랩 단위가 scenario인지, run인지, episode인지에 따라 CI 너비가 크게 달라짐

```
다음 검증 작업을 수행해줘.

## 검증 항목

### 2-A: 부트스트랩 리샘플링 단위 확인
- `scripts/experiments/bootstrap_ci.py`를 열어서:
  - 실제 리샘플링이 scenario 단위인지 확인
  - 구체적으로: 15개 시나리오 중 15개를 복원추출하는 것이 맞는지
  - 혹시 에피소드 단위(180개 중 180개 복원추출)로 하고 있지는 않은지
  - 3 runs을 어떻게 처리했는지: run 평균을 먼저 구했는지, 아니면 개별 run을 독립 관측으로 취급했는지

### 2-B: pairwise 차이 CI 계산 로직
- 모델 A와 모델 B의 차이에 대한 CI를 어떻게 계산했는지 확인
  - 올바른 방법: 각 부트스트랩 샘플에서 (mean_A - mean_B)를 계산, 이 차이의 분포에서 CI
  - 잘못된 방법: 각 모델의 CI를 독립적으로 구한 뒤 겹침 여부만 확인
    (이 방법은 CI 겹침 ≠ 차이 비유의 이므로 보수적)
  - 어떤 방법을 사용했는지 코드에서 확인

### 2-C: "16/18" 수치의 정확한 출처
- `evidence_pack/analysis/bootstrap_confidence_intervals.json`을 열어서:
  - 18개 pairwise 비교 각각의 차이 점추정 + 95% CI 확인
  - CI가 0을 포함하지 않는 2개 쌍이 어떤 모델 조합인지 확인
  - 어떤 메트릭에서 2개 쌍이 유의한지 (CGA? Composite? Coverage?)

### 2-D: 논문 활용 시 자해 위험 평가
- 이 결과가 논문에 그대로 실리면:
  "CGA-Bench는 4개 모델 중 거의 아무 쌍도 통계적으로 구별하지 못한다"가 됨
- 이것이 정말로 보고해야 할 결과인지, 아니면 부트스트랩 구현 오류인지 판단
- 구별 불가가 사실이라면: 어떤 프레이밍이 가능한지 제안
  (예: "개별 모델 구별보다 행동 패턴의 질적 차이가 벤치마크의 주된 기여")

## 출력
- 리샘플링 단위 확인 결과
- pairwise CI 계산 방법 확인 결과
- 18개 pairwise 비교 전체 테이블 (차이 [95% CI])
- 논문 프레이밍 권고
```

---

## 🔴 검증 3: P0-3 "r=0.463 판별 타당도" — 계산 과정이 올바른가?

**의심 근거:**
- point-biserial r=0.463은 "CGA는 Task Completion과 다른 구성개념 측정"의 근거
- 그런데 Task Completion을 "C2 ≥ 1.0"으로 정의했다면, 이 binary 변수의 분포가 중요
- 만약 대부분 에피소드가 Task PASS(C2 ≥ 1.0)이면, binary 변수의 분산이 극히 작아
  point-biserial r이 인위적으로 낮아질 수 있음 → 판별 타당도가 아니라 분산 부족

```
다음 검증 작업을 수행해줘.

## 검증 항목

### 3-A: Task Completion 분포 확인
- 전체 에피소드에서 C2 ≥ 1.0 (Task PASS)인 비율 확인
  - 만약 90%+ 가 PASS이면, binary 변수의 분산이 극히 작아
    point-biserial r의 해석이 제한됨
  - 정확한 PASS / FAIL 비율 보고

### 3-B: r=0.463 재현
- `scripts/experiments/subconstruct_analysis.py`에서:
  - CGA Score (continuous)와 Task Completion (binary) 데이터 추출
  - scipy.stats.pointbiserialr()에 전달된 정확한 두 배열 확인
  - 수동 재계산으로 r=0.463 재현

### 3-C: Q2 에피소드 분석 교차 검증
- "22개 Q2 에피소드 중 21개가 C1 failure"라는 결과 확인
  - 기존 `evidence_pack/analysis/necessity_audit_final.json`의 Q2 에피소드와 대조
  - C1 (Path Selection)이 Q2 failure의 주원인이라는 것이 직관적으로 맞는지:
    → Q2 = Task PASS / CGA FAIL
    → C1이 낮다 = 허용 범위 밖 행동 수행
    → 이것이 "과잉 행동에 의한 CGA 감점"을 의미하는지 확인
  - 기존 문서에서 Q2의 failure mode는 "timing FM 4건, overaction FM 11건"이었는데,
    "C1 failure 21건"과의 관계가 명확한지 확인

### 3-D: C4 Timing p=0.0075의 의미
- C4(Timing Compliance)에서만 Friedman 유의 (p=0.0075)
- 다른 sub-construct (C1, C2, C3, C5)에서는 비유의인지 확인
- C4에서 어떤 모델이 가장 좋고 나쁜지 확인
- 이 결과가 논문 서사에 어떻게 통합되는지 확인

## 출력
- Task PASS / FAIL 비율
- r=0.463 재현 확인 (일치/불일치)
- Q2 에피소드의 C1 failure와 기존 failure mode 분류의 관계
- C1-C5 각각의 Friedman p-value
```

---

## 🟡 검증 4: P1-2 "100% omission-caused, 모두 establish_iv_access" — 단일 시나리오 편향?

**의심 근거:**
- "77개 위반 dependency 전부 establish_iv_access 누락에서 기인 (DKA 시나리오)"
- 이것은 sequence violation이 **DKA라는 단일 시나리오에서만** 발생한다는 뜻
- 만약 사실이면, "LLM이 순서를 재배열하지 않는다"는 일반화가 아니라
  "DKA 시나리오의 IV access 설정이 자주 누락된다"라는 시나리오 특화 발견

```
다음 검증 작업을 수행해줘.

## 검증 항목

### 4-A: Sequence violation의 시나리오 분포
- `evidence_pack/analysis/sequence_counterfactual.json`을 열어서:
  - 48개 sequence violation 에피소드가 어떤 시나리오에서 발생했는지 분포 확인
  - DKA 시나리오에서만 발생했는지, 다른 시나리오에서도 발생했는지
  - 만약 DKA에만 집중되어 있으면, 이것은 "LLM 일반 패턴"이 아니라
    "DKA 시나리오 특화 패턴"임을 명시해야 함

### 4-B: establish_iv_access의 CPG 그래프 내 위치
- `cpg_model/graphs/ada_dka_management.yaml`에서:
  - establish_iv_access가 어떤 action의 required_prior_action인지 확인
  - 이것이 누락되면 자동으로 몇 개의 sequence violation이 발생하는지
  - 하나의 omission이 다수의 sequence violation을 연쇄적으로 유발하는 구조인지

### 4-C: "77개 위반"의 세분화
- 48개 에피소드에서 77개 violation이면, 에피소드당 평균 1.6개
- 하나의 establish_iv_access 누락이 에피소드 내에서 2+ sequence violation을
  유발하는 "팬아웃(fan-out)" 구조인지 확인
- 이것이 "이중 처벌 문제"의 구체적 메커니즘인지 확인

### 4-D: 논문 서사 수정 필요성 판단
- "LLM이 순서를 재배열하지 않는다"는 일반화가 정당화되는지
- DKA 단일 시나리오 한정이면, 서사를 다음과 같이 수정해야 하는지:
  "적어도 DKA 시나리오에서, sequence violation은 독립적 순서 오류가 아니라
  선행 단계(IV access) 누락의 연쇄적 결과로 나타난다. 다른 도메인에서의
  일반화는 추가 검증이 필요하다."

## 출력
- 48개 에피소드의 시나리오 분포
- establish_iv_access의 CPG 그래프 구조
- fan-out 구조 확인 여부
- 논문 서사 수정 권고
```

---

## 🟡 검증 5: P0-4 시나리오 복잡도 — 수치 교차 검증

**의심 근거:**
- "341 mandatory actions"이 14개 YAML 그래프 전체 합산이라면,
  시나리오 15개에서 실제 활성화되는 mandatory는 훨씬 적을 수 있음
- 논문에 "341 mandatory"를 쓰면서 15개 시나리오만 테스트하면
  "왜 341개 중 일부만 평가하나?"라는 비판을 받을 수 있음

```
다음 검증 작업을 수행해줘.

## 검증 항목

### 5-A: 그래프 전체 vs 시나리오 실효 수치 구분
- `evidence_pack/analysis/scenario_complexity.json`에서:
  - 14개 그래프의 총 mandatory (341) vs 15개 시나리오에서 실제 활성화된 mandatory
  - 각 시나리오의 expected_actions 수를 합산한 값과
    341이라는 수치의 관계 설명
  - 논문에 쓸 수 있는 수치는 "그래프 전체"인지 "시나리오 활성화"인지 판단

### 5-B: 비교 벤치마크 테이블의 "없음" 셀 검증
- 비교 테이블에서 MedQA, AgentClinic, HealthBench, MedAgentBench의
  temporal/sequential/forbidden 평가 여부를 "없음"으로 표기했는데:
  - 각 벤치마크의 원 논문에서 이를 확인할 수 있는지
  - 특히 HealthBench는 "safety" 관련 rubric이 있으므로
    "forbidden 없음"이 정확한지 재확인

## 출력
- 그래프 전체 수치 vs 시나리오 활성화 수치 대조표
- 비교 벤치마크 "없음" 셀의 근거 확인 결과
```

---

## 🟡 검증 6: P1-1 HealthBench 감사 — "616 rubrics"의 실체

**의심 근거:**
- "50 에피소드, 616 rubrics"이라면 에피소드당 평균 12.3 rubrics
- 이것이 HealthBench의 원본 rubric 구조와 일치하는지 확인 필요
- "Old classifier: 17.9% ACTION → New: 3.7% ACTION"이라는 개선 수치가
  실제 discordant rate 변화(89.7% → 30.1%)와 어떻게 연결되는지 불명확

```
다음 검증 작업을 수행해줘.

## 검증 항목

### 6-A: 616 rubrics의 출처
- `evidence_pack/sampling/healthbench_50sample_audit.json`에서:
  - 50개 에피소드의 구체적 HealthBench episode ID 목록
  - 각 에피소드가 몇 개의 rubric을 가지는지 분포
  - 616이라는 총 rubric 수가 어떻게 도출되었는지

### 6-B: "17.9% → 3.7%" 와 "89.7% → 30.1%"의 관계
- "17.9% ACTION"은 rubric 단위인지 에피소드 단위인지 확인
- 기존 문서의 "89.7% discordant → 30.1%"는 에피소드 단위
- 이 두 수치가 어떻게 연결되는지 구체적 경로 추적

### 6-C: "인간 리뷰어용 빈 필드"의 의미
- CSV에 manual_review_label, manual_review_reasoning 필드가 비어 있다면
  → 실제로 수동 검증이 아직 수행되지 않았다는 뜻?
  → 그러면 "감사 완료"가 아니라 "감사 프레임워크 구축 완료"가 정확한 표현

## 출력
- 616 rubrics 구조 설명
- 수치 연결 관계 설명
- 실제 수동 검증 수행 여부 (완료 vs 프레임워크만)
```

---

## 🟢 검증 7: P2-1 예산 추정 — API 가격 정확성

```
다음을 간단히 확인해줘.

- `evidence_pack/analysis/budget_estimate_frontier.json`에서 사용된
  GPT-4o와 Claude 3.5 Sonnet의 토큰당 가격이 2026년 3월 현재 정확한지
- 에피소드당 평균 토큰 수 추정의 근거 (기존 4개 모델의 실제 사용량 기반인지)
- $18.70이라는 총 비용에 buffer가 포함되어 있다면 buffer 비율은 몇 %인지
```

---

## 실행 순서 권장

```bash
# 🔴 최우선 — 핵심 수치의 신뢰성
# 1. k-space 결과의 기존 문서와의 불일치 해소 (가장 의심스러움)
# 2. 부트스트랩 구현 정확성 + "16/18 구별 불가"의 함의
# 3. 판별 타당도 r=0.463의 계산 과정 + Task PASS 비율

# 🟡 다음 — 해석의 정확성
# 4. Sequence violation이 DKA 단일 시나리오 편향인지
# 5. 시나리오 복잡도 수치의 논문 사용 적절성
# 6. HealthBench 감사의 "완료" 정의

# 🟢 경미
# 7. API 가격 정확성
```

---

## 검증 후 예상 시나리오별 대응

| 검증 결과 | 대응 |
|-----------|------|
| P0-1의 p=0.007이 multi-run이고 기존 0.013과 불일치 | 데이터 입력 오류 가능성. 원본 데이터에서 재계산 필요 |
| P0-2의 16/18 구별 불가가 구현 오류 | 리샘플링 단위 수정 후 재실행 |
| P0-2의 16/18 구별 불가가 사실 | 논문 서사를 "모델 순위"에서 "행동 패턴 질적 차이"로 전환 |
| P0-3의 r=0.463이 PASS 비율 90%+ 때문 | "판별 타당도" 주장 약화, Q2 에피소드에 집중 |
| P1-2가 DKA 단일 시나리오 | "일반화" 주장 제거, "DKA에서의 사례 연구"로 한정 |
| P1-1의 수동 검증이 미완료 | "감사 완료" → "감사 프레임워크 구축" 으로 문구 수정 |