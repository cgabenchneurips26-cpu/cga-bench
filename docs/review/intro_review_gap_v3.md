# C3 Fix 후 상황 평가

---

## 1. 무엇이 바뀌었고, 무엇이 유지되었는가

### 좋아진 것
- **CGA alone p=0.249→0.074**: 여전히 ns이지만, C3 수정으로 모델 간 CGA 분산이 증가. 벤치마크가 더 정밀해짐
- **C3 Friedman p=1.000→0.112**: "all tied"에서 실질 변이 감지로 전환. C3가 살아남
- **모델 순위 변화 없음**: 서사 전면 재작성 불필요
- **Q2 에피소드 22건 유지**: necessity 주장 유지
- **r=0.486→0.492**: 판별 타당도 안정

### 나빠진 것
- **Composite A single-run p=0.043→0.073 (ns)**: 기존 논문의 primary 수치가 유의하지 않게 됨
- **Composite B single-run p=0.040→0.275 (ns)**: harmonic mean도 상실
- **N=50에서도 80% power 미달**: 효과 크기가 시나리오 간 분산 대비 작음

### 논문에 미치는 영향

| 기존 주장 | 수정 후 상태 | 영향 |
|-----------|:---:|------|
| "Composite A single-run p=0.043" | ❌ ns | 이 수치를 primary로 보고 불가 |
| "Composite A multi-run p=0.013" | ✅ sig (p=0.020) | 이것이 유일한 유의 결과 |
| "Composite B p=0.040" | ❌ ns | 사용 불가 |
| "CGA alone ns" | ✅ 유지 | 서사 변화 없음 |
| "모델 순위: 120b > 20b > 35B > 4B (Composite)" | ✅ 유지 | 서사 변화 없음 |
| "Q2 = 22 에피소드" | ✅ 유지 | necessity 주장 유지 |

---

## 2. 3차 검증: Fix 결과의 신뢰성 확인

Fix 결과도 Claude Code가 생성했으므로 검증이 필요합니다. 특히 C3 수정이 "미미한 영향"이라는 주장과, single-run이 ns로 전환된 것 사이의 긴장을 확인해야 합니다.

```
Fix-1~3 후 재계산 결과를 검증해줘.
코드를 실행하지 말고, 생성된 파일의 원문을 확인하는 방식으로.

## V-A: C3 수정의 영향이 정말 "미미"한가?

### Step 1: pre_post_fix_comparison.json 원문 확인
- `evidence_pack/analysis/pre_post_fix_comparison.json`을 열어서
  29건 영향 에피소드의 수정 전/후 CGA Score를 전부 출력
- CGA Score 변화의 min, max, mean 확인
- "미미(<0.01)"라고 했는데, 개별 에피소드에서 큰 변화가 있지 않은지

### Step 2: 왜 CGA는 거의 안 변했는데 Friedman p가 크게 변했는가?
- Composite A single-run이 0.043→0.073으로 변한 구체적 메커니즘:
  - 어떤 모델의 어떤 시나리오에서 composite score가 변했는지
  - Friedman은 rank-based이므로, 점수 자체보다 순위 변화가 중요
  - 2개 시나리오(DKA, STEMI)에서 특정 모델의 순위가 바뀌었는지 확인
- CGA Score가 -0.007~-0.009 변화인데 Friedman p가 0.043→0.073으로
  변할 정도이면, 기존 유의성이 얼마나 취약했는지를 보여줌

### Step 3: multi-run p=0.020은 안전한가?
- multi-run means 기반 Friedman에서 p=0.020
- 이것이 단일 시나리오(DKA 또는 STEMI) 제거 시에도 유의한지 확인
  → leave-one-scenario-out 분석이 이미 되어 있는지 확인
  → 안 되어 있으면 이 분석이 필요하다고 보고

## V-B: C3 수정 코드 자체가 올바른가?

### Step 1: C3 binary 공식 확인
- harm_scorer.py:225의 수정된 코드를 원문 출력
- "Binary: 0.0 if commission > 0 else 1.0"이 맞는지
- 이 공식이 맞다면: commission 1건이라도 있으면 C3=0.0
  → 이것이 너무 가혹하지 않은지 (minor commission도 C3=0?)
  → 기존 논문 설계에서 severity weighting이 C3에 반영되어야 하는지

### Step 2: commission 감지가 실제로 작동하는지
- 수정 후, DKA hypokalemia_trap에서 start_insulin_infusion이
  실제로 COMMISSION violation으로 감지되는지
- 영향받은 29건 에피소드 중 commission violation 수 확인
- 15/19 에피소드에서 금기 위반이 있다고 했는데, 수정 후 실제 14건만 영향?
  → 29건(14 DKA + 15 STEMI)의 세부 구성 확인

## V-C: Fix-2 (N=201) 실제로 수정되었는가?

### Step 1: 재계산 시 사용된 N 확인
- subconstruct_profiles.json에서 실제 에피소드 수 확인
- "이미 truncation 존재"라고 했는데, 그러면 원래 N=201이 아니라
  M3의 "66개 과대 로드" 진단 자체가 틀렸던 건지?
- N=173 (oss-120b 38개)이면, 모든 모델이 45개가 아닌 것
  → 일부 시나리오에서 3 runs 미만이 존재한다는 뜻
  → 이것이 균형 데이터인지 확인

### Step 2: r=0.486→0.492 변화의 원인
- C3 수정 때문인지, N 변경 때문인지, 둘 다인지
- 두 수정을 분리하여 각각의 기여 확인 가능한지

## 출력
- V-A: 29건 에피소드의 수정 전/후 CGA Score 테이블
- V-A: single-run p 변화의 구체적 메커니즘
- V-A: multi-run p=0.020의 leave-one-out 강건성
- V-B: 수정된 C3 코드 원문 + commission 감지 확인
- V-C: 재계산 N과 r 변화 원인
```

---

## 3. 논문 전략 재수립

### 핵심 변화: "유의한 유일한 결과"가 multi-run means뿐

기존에는 single-run(p=0.043)과 Composite B(p=0.040) 두 개가 유의했지만,
수정 후에는 **multi-run means p=0.020만 유의**합니다.

이것은 리뷰어에게 두 가지로 읽힐 수 있습니다:

**(A) 부정적 독해**: "run 평균으로 분산을 인위적으로 줄여야만 유의해지는 취약한 결과"

**(B) 긍정적 독해**: "multiple runs averaging은 noise reduction의 표준 기법이며,
single-run의 비유의는 measurement noise 때문이지 효과 부재 때문이 아니다"

### 권장 전략: Effect Size 중심 보고로 전환

p-value 의존도를 줄이고, 다음 구조로 논문을 재구성:

```
1. Primary result: Effect size (ε²=0.35~0.45, large)
   → "CGA-Bench는 모델 간 large effect를 감지한다"

2. Statistical significance: Multi-run means p=0.020
   → "noise-reduced 조건에서 통계적으로 유의하다"

3. Honest limitation: Single-run p=0.073 (ns)
   → "단일 실행에서는 n=15의 검정력 한계로 유의하지 않다"

4. Power analysis: 80% power에 n=30+ 필요
   → "향후 시나리오 확장의 구체적 목표"

5. Qualitative contribution (p-value 무관):
   - Q2 에피소드 22건 (기존 메트릭이 놓치는 결함)
   - C4 Timing에서 유의한 모델 차이 (p=0.0075)
   - 4B 보수적 전략 발견 (C1=0.862, actions=9.2)
   - Temporal/Sequential/Forbidden 차원의 최초 측정
```

### 구체적 논문 문구 수정

**Abstract:**

> Before: "Composite A achieves Friedman p=0.043"
>
> After: "Composite A reveals a large effect (ε²≈0.4) across models,
> reaching significance under multi-run aggregation (p=0.020, Holm-corrected p=0.029).
> CGA-Bench identifies 22 episodes where agents pass task-completion
> benchmarks yet violate clinical guidelines — failures invisible to
> existing metrics."

**Results 핵심 문단:**

> "With 15 scenarios and 4 models, CGA-Bench operates at the lower
> bound of statistical power for the Friedman test. Composite A yields
> p=0.073 on single runs and p=0.020 on multi-run means, consistent
> with a true large effect (ε²=0.40–0.45) that is intermittently
> detected due to sample-size constraints. Bootstrap analysis confirms
> that 16/18 model pairs are not statistically distinguishable at n=15,
> with n≈30 scenarios required for 80% power.
>
> The benchmark's primary contribution is therefore qualitative rather
> than ranking-based: it surfaces failure modes — timing violations,
> conservative strategy traps, omission-caused sequence cascades —
> that are invisible to task-completion metrics."

**Limitation Section:**

> "Three limitations merit emphasis. First, n=15 scenarios provide
> insufficient power for definitive model ranking; we recommend n≥30
> for future deployments. Second, Composite A significance depends on
> multi-run averaging; single-run results are non-significant (p=0.073).
> Third, C3 (Forbidden Avoidance) scoring was corrected during
> development to address commission detection gaps in DKA and STEMI
> scenarios, affecting 29/268 episodes (10.8%). We report all results
> with the corrected scoring."

---

## 4. C3 Binary 공식의 적절성 문제

C3을 "commission > 0 → 0.0, else 1.0"으로 수정한 것은 **너무 가혹할 수 있습니다**.
minor severity commission이라도 C3=0이 되면, 기존의 severity weighting 철학과 모순됩니다.

검토 포인트:

| C3 공식 옵션 | 장점 | 단점 |
|---|---|---|
| Binary (현재 수정) | 단순, 금기 위반에 zero tolerance | minor commission도 C3=0, severity 무시 |
| 1 - weighted_sum | severity 반영, 기존 C1/C2/C4/C5와 일관 | 기존 버그 공식의 변형이 될 위험 |
| 1 - max_severity | 가장 심각한 위반만 반영 | 복수 위반 무시 |

**권장**: 3차 검증에서 C3 binary 공식이 실제 결과에 어떤 영향을 주는지 확인한 뒤,
severity-weighted 버전과 비교하여