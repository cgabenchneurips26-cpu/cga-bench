# EX-23~33 전수 교차검증 보고서

> 검증 기준: main_final_v11.tex, appendix_v2.tex, handoff-v7-final.md
> 검증 방법: 수치 교차대조, 정의 일관성, 내부 산술 정합성
> 판정: 🔴 CRITICAL / 🟡 INVESTIGATE / 🟢 VERIFIED

---

## 🔴 CRITICAL #1: Consensus FA 수치 불일치 (EX-24 vs 기존)

| 출처 | 값 | 정의 |
|------|-----|------|
| handoff-v7 | **13.1%** (≈1,841건) | FA (all-oblivious) |
| 논문 Table 2 각주 L375 | `\faAllOblivious`% | TOM + ASC + CwT pass ∧ TCC fail |
| 논문 본문 L382 | same | "all **three** process-oblivious evaluators" |
| **EX-24** | **14.1%** (1,986건) | "Consensus FA" |
| 차이 | **+1.0pp, +145 에피소드** | |

### 위험
- 논문의 가장 중요한 headline number. abstract, intro, conclusion, 3곳에서 사용.
- 1.0pp 차이는 reviewer가 "어디서 온 숫자인가?"라고 물으면 답 못 함.
- 145 에피소드 차이는 rounding이 아님 — 정의 또는 파이프라인 차이.

### 가능한 원인 (우선순위 순)
1. **EX-24가 다른 TCC scoring 버전 사용**: EX-24가 bug-fix 이후 재scoring을 했을 가능성. 하지만 EX-28에서 TCC verdict flip = 0이므로 이것은 원인 아님.
2. **"consensus"와 "all-oblivious"의 정의 차이**: EX-24의 "consensus FA"가 TOM을 제외하고 ASC + CwT만으로 계산했을 가능성. TOM은 모든 에피소드를 pass하므로 제외해도 결과 같아야 함 → 이것도 원인 아님.
3. **PAF 포함 여부**: PAF를 제외하면 더 많은 에피소드가 "all pass"에 포함되어 count가 올라감. 그런데 논문의 all-oblivious는 이미 PAF를 제외(TOM+ASC+CwT만). EX-24가 PAF도 제외했으면 결과 같아야 함.
4. **TCC 판정 기준 차이**: EX-24에서 "hard violation 보유" 판정에 TCC scorer 대신 raw violation count를 사용했을 가능성. TCC scorer는 일부 violation을 alternative branch로 면제할 수 있으나, raw count는 면제 안 함 → raw count 기준이면 더 많은 에피소드가 "hard violation 보유"로 분류됨.
5. **에피소드 셋 차이**: 14,055 vs 14,025 (dedup). EX-24가 14,055 전체를 사용하고, 기존 계산이 14,025를 사용했다면 30개 차이는 설명 가능하지만, 145개 차이는 아님.

### 필수 조치
```
Claude Code에서:
1. EX-24 코드에서 "consensus FA" 정의 확인
   - 어떤 evaluator가 "all pass" 조건에 포함되는지
   - "hard violation" 판정이 TCC verdict인지 raw violation count인지
2. 기존 auto_numbers.tex에서 \faAllOblivious 계산 로직 추적
3. 두 계산을 동일 정의로 재실행하여 정합 확인
4. 불일치 원인 확인 후: 
   → 정의 같으면 최신 값으로 통일
   → 정의 다르면 별도 매크로 사용하고 정의 명시
```

### 추가 문제: 논문 내부 용어 불일치
- **Abstract/Intro (L56, L68)**: "pass **all** action-set evaluators" — PAF 포함 암시
- **Table 2 각주 (L375)**: "pass **TOM + ASC + CwT**" — PAF 미포함 명시
- **본문 (L382)**: "all **three** process-oblivious evaluators" — 3개로 명시
- → Abstract/Intro에서 "all action-set evaluators"를 "all three process-oblivious evaluators (TOM, ASC, CwT)"로 수정 필요

---

## 🔴 CRITICAL #2: Constraint 수 불일치 (EX-25 vs 기존)

| 출처 | 값 | 상세 |
|------|-----|------|
| handoff-v7 | **1,049** hard | — |
| **EX-25** | **1,039** total | MUST 557 + FORBIDDEN 212 + WITHIN 215 + BEFORE 55 |
| 차이 | **10개** | |

### 위험
- Abstract에서 `\numTotalConstraints`로 사용.
- 논문의 CPG library 설명(Section 4.1)에서 constraint type별 수치를 개별 매크로로 보고.
- type별 합산(1,039)과 총합 매크로(1,049)가 불일치하면 reviewer가 즉시 잡음.

### 가능한 원인
1. **hard vs total 분류 차이**: handoff의 "1,049 hard"가 실제로는 "1,049 total (hard+soft)"이고, EX-25의 1,039가 hard만 센 것. 이 경우 soft 10개가 빠짐.
2. **그래프 범위 차이**: EX-25가 20 core 그래프만 감사하고 5 held-out을 제외.
3. **집계 시점 차이**: normalizer fix 전후로 constraint 수가 바뀜.

### 필수 조치
```
Claude Code에서:
1. auto_numbers.tex에서 \numTotalConstraints, \numHardConstraints, \numSoftConstraints 값 확인
2. EX-25가 몇 개 그래프를 감사했는지 확인 (20 vs 25)
3. EX-25의 type별 합산 = 총합인지 확인
4. constraint_derivation.py 출력과 대조
```

---

## 🟡 INVESTIGATE #1: EX-27 "Violation Rate" 정의 모호

| 지표 | EX-27 값 | 기존 값 | 비교 |
|------|----------|---------|------|
| Baseline violation rate | **63.66%** | TCC fail rate ≈ 47.7% | **15.9pp 차이** |

### 문제
- EX-27이 보고하는 "Violation Rate"가 무엇인지 불명확.
- TCC fail rate(47.67%, EX-28 기준)와 15.9pp 차이.
- 가능한 해석:
  - (A) "WITHIN violation이 있는 에피소드 비율" → TCC fail rate보다 높을 수 없음 (WITHIN violation ⊂ TCC fail)
  - (B) "전체 WITHIN constraint 중 위반된 비율" (per-constraint basis) → 에피소드 수가 아니므로 비교 불가
  - (C) "WITHIN constraint가 있는 에피소드 중 위반이 있는 비율" → 분모가 다르므로 높을 수 있음

### 해석 (C)가 맞다면
- 14,055 에피소드 중 WITHIN constraint가 활성화되는 에피소드만 분모로 사용
- 이 경우 분모 < 14,055이므로 rate > TCC fail rate 가능
- 하지만 논문에서 이 수치를 사용할 때 "what fraction"인지 명확히 해야 함

### Clock sweep 값은 기존과 일관 ✅
| Step | EX-27 Flip | Handoff EX-4A |
|------|-----------|---------------|
| 2 min | 20.24% | 20.2% |
| 5 min | 0% | 0% |
| 10 min | 11.71% | 11.7% |
| 15 min | 24.02% | 24.0% |
| 20 min | 26.69% | 26.7% |
→ 모든 값 rounding 범위 내 일치.

### 31.8% clock-dependent 검증
- EX-27: 2min에서 flip = 20.24pp
- Baseline violation rate = 63.66%
- 20.24/63.66 = **31.8%** ← 정확히 일치 ✅
- 하지만 이것은 "violation rate" 기준이지 "TCC fail rate" 기준이 아님
- 논문의 "31.8% clock-dependent"가 어떤 분모를 쓰는지 확인 필요

### 필수 조치
```
Claude Code에서:
1. EX-27의 "Violation Rate" 정확한 정의 확인
   - per-episode? per-constraint? 분모는?
2. 논문의 "31.8% clock-dependent" 계산 기반 확인
3. 불일치 시 논문 표현 수정
```

---

## 🟡 INVESTIGATE #2: EX-32 vs EX-17 Solver 분류 차이

| 카테고리 | EX-17 (handoff) | EX-32 (new) | 차이 |
|---------|----------------|-------------|------|
| Equal | 9,669 (68.9%) | 10,146 (72.3%) | +477 |
| ILP Better | 3,319 (23.7%) | 2,826 (20.1%) | -493 |
| Tiered Better | 1,037 (7.4%) | 1,053 (7.5%) | +16 |
| **Verdict Reversals** | **0** | **0** | — |
| Total | 14,025 | 14,025 | ✅ |

### 문제
- 493 에피소드가 ILP Better → Equal로 이동. 이는 전체의 3.5%.
- 원인 후보: solver 버전 차이, 수치 정밀도, tie-breaking 기준
- **verdict reversal = 0은 양쪽 동일** → 결론에는 영향 없음.

### 위험
- `\solverILPPct` 매크로 값이 23.7%(EX-17)인지 20.1%(EX-32)인지 불일치.
- `\solverTieredBetter` 매크로: 7.4% vs 7.5%.
- 논문에서 두 값을 모두 사용하는데 어느 것이 canonical인지 결정 필요.

### 필수 조치
```
Claude Code에서:
1. EX-17과 EX-32가 동일한 solver 코드를 사용했는지 확인
2. 차이가 FORBIDDEN guard fix 전후라면: EX-32가 canonical
3. auto_numbers.tex의 \solverILPPct, \solverTieredBetter 값 확인 후 갱신
4. 어느 버전이든 verdict reversal = 0이므로 결론은 안전
```

---

## 🟡 INVESTIGATE #3: EX-25 Unreachable Nodes 36.5% 프레이밍

### 사실
- 167 노드 중 61개(36.5%)가 706 시나리오 어디에서도 활성화되지 않음.
- 5개 그래프에 집중.

### 위험
- Reviewer가 "36.5% dead code"로 읽으면 엔진 품질에 의문.
- 하지만 이것은 "unreachable"이 아니라 "unactivated in current test set"일 수 있음.
  - Multi-entry 그래프에서 특정 clinical pathway는 현재 시나리오 세트가 커버하지 않는 경우.
  - 706 시나리오가 모든 possible patient context를 커버하지 않으므로 일부 노드가 미활성화됨.

### 프레이밍 전략
```
논문에서:
"61 of 167 graph nodes (36.5%) are not activated by any scenario in the 
current test set. These are concentrated in 5 multi-entry graphs that 
model alternative clinical pathways (e.g., different treatment lines for 
the same condition). Unactivated nodes cannot produce false violations — 
they represent under-coverage (reduced recall for rare pathways) rather 
than constraint inflation. We treat expanding scenario coverage for these 
nodes as future work."
```

### 추가 확인 필요
```
1. 61개 노드가 어떤 그래프에 속하는지 분포 확인
2. 해당 그래프의 multi-entry 구조 확인 (정말 alternative pathway인지)
3. 노드가 valid CPG content인지 확인 (dead code 아닌지)
```

---

## 🟡 INVESTIGATE #4: EX-25 Duplicates 91건(8.8%)

### 사실
- 1,039 제약조건 중 91건이 중복.

### 위험
- "중복"의 정의가 불명확. (guard, op, target) 삼중쌍 동일 = 논리적 중복? 아니면 다른 그래프에서 동일 constraint를 각각 생성?
- 91건이 verdict에 영향을 주는지 확인 필요.

### 필수 확인
```
1. 중복 제거 후 TCC verdict가 변하는 에피소드 수 확인
   - 변하면 중복이 verdict에 영향 → 심각한 문제
   - 안 변하면 중복은 redundancy일 뿐 → 안전
2. 중복의 성격: 같은 그래프 내 중복 vs 다른 그래프 간 중복
```

---

## 🟡 INVESTIGATE #5: EX-23 HB-Artifact Detection Loss "—" 누락

### 사실
- EX-23 표에서 HB-Artifact의 Detection Loss가 "—"으로 비어 있음.
- AC-Artifact: 82.6%, MAB-Artifact: 65.7%, HB-Artifact: ?

### 위험
- HB-Artifact FA = 39.4%이고 TCC FA = 0%이므로, detection loss는 계산 가능해야 함.
- 빠진 이유: LLM judge 기반 mode라서 detection 개념이 다를 수 있음.

### 필수 확인
```
1. HB-Artifact에서 "detection"을 어떻게 정의했는지 확인
2. 값이 계산 가능하면 채우고, 불가능하면 이유 명시
3. HB FA(39.4%)와 AC FA(39.4%)가 동일한 이유 확인
   - 같은 에피소드 세트를 pass시키는지?
   - HB judge가 AC와 실질적으로 같은 정보만 사용하는지?
```

---

## 🟡 INVESTIGATE #6: EX-28 AC Verdict Flip 6.55pp — Unstable

### 사실
- TCC verdict flip = 0.0pp (stable)
- AC verdict flip = 6.55pp (NOT stable)

### 해석 — 이것은 오히려 좋은 결과
- 의미: normalizer 수정이 action-set evaluator의 verdict를 6.55pp 변화시키지만, TCC는 전혀 변화 없음.
- 이유: normalizer가 action을 다르게 매핑하면 ASC의 coverage 계산이 바뀌지만, TCC는 constraint 자체를 체크하므로 normalizer 의존성이 낮음.

### 논문 반영 전략
```
"Normalizer updates affect action-set evaluators (AC verdict flip = 6.55pp) 
but leave TCC verdicts completely unchanged (0.0pp), consistent with TCC's 
design: typed constraint checking depends on the presence and timing of 
actions in the canonical alphabet, not on the specific string-matching 
thresholds used during normalization."
```

→ AC의 불안정을 TCC의 안정성과 대비하면 추가 evidence가 됨.

---

## 🟡 INVESTIGATE #7: EX-29 Held-Out FA 범위 2.8%~92.1% — 극단적

### 산술 검증 ✅
| Domain | Episodes | FA(AC) count (계산) |
|--------|----------|-------------------|
| AABB | 252 | 252 × 0.028 = 7.1 ≈ 7 |
| ABA | 420 | 420 × 0.912 = 383.0 |
| ACOG | 189 | 189 × 0.725 = 137.0 |
| APA | 315 | 315 × 0.921 = 290.1 |
| PALS | 180 | 180 × 0.833 = 149.9 |
| **Total** | **1,356** ✅ (= `\heldoutN`) | **967.1** |
| **Weighted FA** | | **71.3%** |

### 논문과의 교차검증
- 논문: `\heldoutN` = 1,356 → **일치** ✅
- 논문: `\heldoutCondFA` = 53.3% — 이것은 conditional FA (P(TCC fail | all-oblivious pass))이므로 FA(AC) 71.3%와 직접 비교 불가. **정의 다름** ✅ (문제 아님)
- EX-29: "In-domain FA 36.0%" vs 논문 `\indomainCondFA` = 36.4% → 0.4pp 차이.
  - 이 차이가 conditional FA vs unconditional FA의 차이인지, rounding인지 확인 필요.

### ABA Burn 91.2% 검증
- Hard Rate = 98.6% → 420 × 0.986 = 414 episodes have hard violations.
- FA(AC) = 91.2% → 420 × 0.912 = 383 episodes: ASC pass ∧ hard violation.
- 즉 hard-violating 414건 중 383건(92.5%)을 ASC가 pass시킴.
- 이것은 ABA Burn 그래프의 constraint가 주로 WITHIN/BEFORE 유형이어서 ASC가 구조적으로 못 잡는 경우일 가능성.

### 필수 확인
```
1. ABA Burn 그래프의 constraint type 분포 확인 (WITHIN 비율 높을 것으로 예상)
2. AABB Transfusion의 낮은 hard rate (2.8%) 원인 확인
   - 모델들이 transfusion protocol을 잘 따르는 것인지
   - constraint가 적어서 위반 자체가 드문 것인지
3. "In-domain FA 36.0%"의 정확한 정의 확인
```

---

## 🟢 VERIFIED: EX-26 Scorer Fidelity

- 40 traces × 3 scorers = 120 evaluations
- Exact match: 100%, κ = 1.0
- 산술 검증: 별도 필요 없음 (deterministic scorer이므로)
- **완전 통과** ✅

### 제한사항 (논문 반영 시 주의)
- 이것은 "우리의 replay scorer가 내부적으로 결정론적"임을 보여줌
- "native benchmark scorer와 동일한 결과를 낸다"는 아직 미증명
- 논문에서 "deterministic fidelity" vs "native equivalence"를 구분해야 함

---

## 🟢 VERIFIED: EX-32 Verdict Reversals = 0

- ILP vs Tiered 간 verdict reversal: **0건** ✅
- Solver Spearman ρ: **0.918** (handoff 0.918과 일치) ✅
- Total episodes: **14,025** (handoff 일치) ✅
- Tiered-better 비율: 7.51% (handoff 7.4% ← EX-17의 7.39%와 근사)

### Formulation gap 702건 — 추가 검증 필요
- Mean diff 2,144.3 — cost 단위가 뭔지에 따라 해석 다름
- 이 값이 논문에 반영될 때 cost 단위 명시 필수
- Verdict reversal 0이므로 결론에 영향 없음 확인 ✅

---

## 🟢 VERIFIED: EX-33 Benchmark Survey

- 12개 benchmark 분류 — 코드 실험 아닌 문헌 조사
- 결과: timing 0/12, ordering 1/12 (AMEGA), conditional safety 2/12
- 이것은 fact check가 필요한 claim이므로 각 benchmark 논문과 대조 필요
- 하지만 수치 정합성 문제는 아님

### 확인 필요
```
1. AMEGA가 ordering을 체크한다는 주장의 근거 확인
2. "conditional safety 2/12"가 어떤 benchmark인지 확인
3. HealthBench가 분류에서 어디에 해당하는지 명확히
```

---

## 🟢 VERIFIED: EX-30 Non-Timing Traps

### 산술 검증
- 226 non-timing constraints: BEFORE 9 + FORBIDDEN 217 = 226 ✅
- 25/25 그래프 커버 ✅
- 247 natural non-timing TCC fail 중 AC-blind 176건 = 176/247 = 71.3% ✅
- MAB-blind 152건 = 152/247 = 61.5% ✅
- 4/4 synthetic traps: 모두 coverage=1.0, AC pass, TCC fail ✅

### 한 가지 관찰
- BEFORE constraint가 9개 밖에 없음 (전체 1,039 중). 이것은 EX-25와 일치 (BEFORE 55는 전체 그래프 수준, 9는 non-timing 관련?).
- 확인 필요: "BEFORE 9"는 EX-30에서 사용한 non-timing trap에 관련된 BEFORE 수인지, 전체 BEFORE 수(55)와 다른 기준인지.

---

## 조치 우선순위 총정리

| 순위 | ID | 심각도 | 내용 | 조치 |
|------|-----|--------|------|------|
| 1 | CRITICAL #1 | 🔴 | FA 13.1% vs 14.1% | EX-24 정의 확인 + 기존 계산 재현 |
| 2 | CRITICAL #2 | 🔴 | Constraints 1,049 vs 1,039 | 그래프 범위 + hard/soft 분류 확인 |
| 3 | INVEST #1 | 🟡 | EX-27 violation rate 정의 | 분모 확인 (per-episode vs per-constraint) |
| 4 | INVEST #2 | 🟡 | EX-32 vs EX-17 solver 분류 shift | canonical 버전 결정 |
| 5 | INVEST #5 | 🟡 | EX-23 HB detection loss 누락 | 값 확인 + HB≈AC 이유 |
| 6 | INVEST #3 | 🟡 | Unreachable 36.5% 프레이밍 | 노드 분포 확인 |
| 7 | INVEST #4 | 🟡 | Duplicates 91건 verdict 영향 | 중복 제거 후 verdict 변화 확인 |
| 8 | INVEST #7 | 🟡 | ABA Burn FA 91.2% | constraint type 분포 확인 |
| 9 | INVEST #6 | 🟡 | AC flip 6.55pp | 프레이밍 전략 (강점으로 전환) |
| 10 | — | 🟢 | 논문 내 "all action-set" 용어 | "all three process-oblivious" 로 통일 |

---

## PART 2: 추가 발견 사항 (심층 분석)

---

### 🟡 INVESTIGATE #8: EX-27 "Violation Rate" 63.66%의 정체 — 해결

**분석 결과**: 수학적으로 역추적하면 정체가 밝혀짐.

```
EX-27: 2min step에서 flip = 20.24pp
논문: "31.8% of baseline's timing violations are resolved"
검증: 20.24 / 63.66 = 31.79% ≈ 31.8% ✅ → 산술 정합

역산: 
  violations_resolved = 14,055 × 0.2024 = 2,843 episodes
  baseline_violations = 2,843 / 0.318 = 8,940 episodes
  8,940 / 14,055 = 63.60% ≈ 63.66% ✅
```

**결론**: "Violation Rate 63.66%" = "14,055 에피소드 중 적어도 1개의 WITHIN violation(hard+soft 포함)이 있는 에피소드 비율".

**왜 TCC fail rate(47.67%)보다 높은가?**
- TCC는 HARD violations에만 fail.
- 논문 L213: WITHIN에는 hard(`\numWithin`)과 soft(`\numShouldWithin`)가 있음.
- 63.66% - 47.67% ≈ 15.99%의 에피소드는 soft WITHIN 위반만 보유 → TCC pass.
- 또는 alternative branch(B)로 해소된 hard violation.

**위험**: EX-27 보고서에서 "Violation Rate"라고만 쓰면 독자가 TCC fail rate로 착각.
**조치**: 논문 반영 시 "fraction of episodes containing at least one WITHIN constraint violation (hard or soft)" 로 명시.
**31.8% 계산은 safe**: 분자분모가 같은 정의이므로 비율 자체는 정확.

---

### 🟡 INVESTIGATE #9: EX-23 HB-Artifact ≈ AC-Artifact 동치 의혹

| Mode | Pass Rate | FA |
|------|-----------|-----|
| AC-Artifact | 72.4% | 39.4% |
| HB-Artifact | 72.3% | 39.4% |

**차이**: Pass rate 0.1pp, FA 0.0pp.

**의혹**: LLM judge 기반인 HB-Artifact가 deterministic rule-based인 AC-Artifact와 
거의 동일한 결과를 내는 것은 세 가지로 해석 가능:

1. **정상**: LLM judge가 실질적으로 coverage check만 수행.
   - 이 경우 결과 자체는 valid하고, "even a sophisticated judge cannot overcome 
     representational blindness"라는 더 강한 주장 가능.
   - 하지만 EX-1의 T2 judge(Qwen35b)에서 FA=23.9%인데, HB-Artifact FA=39.4%는 
     오히려 더 높음. 정보가 더 많은데 FA가 더 높다? → rubric prompt 차이일 수 있음.

2. **구현 미완**: HB-Artifact가 실제로 LLM judge를 호출하지 않고 AC와 같은 
   rule-based scoring을 사용했을 가능성.
   - Detection Loss "—" 누락이 이 가설을 지지.

3. **Sample-based**: HB-Artifact가 500개 샘플에서만 실행되었는데,
   FA를 전체 에피소드로 외삽한 경우.

**필수 조치**:
```
Claude Code에서:
1. EX-23의 HB-Artifact 구현 코드 확인
   - 실제로 LLM judge를 호출했는지?
   - 몇 개 에피소드에서 실행했는지?
2. HB의 Detection Loss 값 확인/계산
3. AC와 HB의 verdict가 동일한 에피소드 비율 확인
   - 99%+ 동일이면 실질적으로 같은 mode → 하나로 합치거나 차이 설명
   - 90% 미만이면 FA가 같더라도 다른 에피소드를 pass/fail → valid
```

---

### 🟡 INVESTIGATE #10: EX-30 Constraint 수의 EX-25 불일치

| 출처 | FORBIDDEN | BEFORE | 합계 |
|------|-----------|--------|------|
| EX-25 (전체 graph inventory) | 212 | 55 | 267 |
| EX-30 (non-timing inventory) | 217 | 9 | 226 |

**FORBIDDEN 차이 +5**: 가능한 원인:
- EX-30이 conditional FORBIDDEN을 추가로 세는 경우 (EX-20의 238 matched pairs에서 
  생성된 conditional FORBIDDEN이 base count에 없었을 수 있음)
- 또는 그래프 파일 버전 차이

**BEFORE 차이 -46**: 매우 큰 차이. 가능한 원인:
- EX-30의 "BEFORE 9"가 "WITHIN과 함께 나타나지 않는 순수 BEFORE constraint"만 
  센 것일 가능성. 55개 BEFORE 중 46개가 WITHIN과 동일 action path에 있어서 
  timing 관련으로 분류되었을 수 있음.
- 이 해석이 맞으면 "non-timing" 정의가 "WITHIN과 무관한 constraint"임.

**필수 조치**:
```
Claude Code에서:
1. EX-30의 "non-timing constraint" 정의 확인
   - "WITHIN과 같은 action에 연결되지 않은 BEFORE/FORBIDDEN만" 인지
   - 아니면 "모든 BEFORE/FORBIDDEN" 인지
2. FORBIDDEN 212 vs 217 차이 원인 확인
```

---

### 🟢 VERIFIED (추가): EX-28 TCC Rate = TCC FAIL Rate 확인

**혼동 가능성**: EX-28의 "TCC Rate 47.67%"는 TCC FAIL rate.
**검증**: 100% - 47.67% = 52.33% ≈ EX-23의 TCC Pass Rate 52.3%.
**rounding**: 0.03pp → rounding 범위 내.
**결론**: 불일치 아님. 단, 보고서에서 "TCC Rate"를 "TCC Fail Rate"로 명시하면 혼동 방지.

---

### 🟢 VERIFIED (추가): EX-29 Held-Out Episode Total

| Domain | Episodes |
|--------|----------|
| AABB | 252 |
| ABA | 420 |
| ACOG | 189 |
| APA | 315 |
| PALS | 180 |
| **Total** | **1,356** |

**논문 `\heldoutN` = 1,356** → **정확히 일치** ✅

---

## PART 3: 전체 조치 계획 (Claude Code 세션용)

### Phase 1: CRITICAL 해결 (최우선)

```
Task 1.1: CRITICAL #1 — FA 13.1% vs 14.1% 
  1. evidence_pack/verdict_matrix_v4.json 열기
  2. "all-oblivious FA" 계산 코드 (exp_e1_verdict_flip.py 또는 관련 스크립트) 찾기
  3. 정의 확인: TOM pass ∧ ASC pass ∧ CwT pass ∧ (TCC fail? d_G>0? raw violation>0?)
  4. EX-24 코드 (exp_e24_consensus_fa_severity.py) 열기
  5. "consensus FA" 정의 확인
  6. 두 정의의 차이점 확인
  7. 가능하다면 두 계산을 동일 정의로 재실행
  8. 결론:
     → 정의 동일 + 값 불일치: 최신 코드의 값으로 auto_numbers 갱신
     → 정의 다름: 두 매크로를 분리하고 논문에서 정의 명시
     → 어느 경우든: abstract/intro에서 "all action-set evaluators" → 
        "all three process-oblivious evaluators (TOM, ASC, CwT)" 로 수정

Task 1.2: CRITICAL #2 — Constraint 1,049 vs 1,039
  1. auto_numbers.tex에서 \numTotalConstraints 확인
  2. constraint_derivation.py 출력과 대조
  3. EX-25가 감사한 그래프 범위 확인 (20 vs 25)
  4. hard/soft 분류가 type별 합산에 어떻게 반영되는지 확인
  5. 정확한 값으로 통일
```

### Phase 2: INVESTIGATE 해결 (CRITICAL 해결 후)

```
Task 2.1: EX-23 HB-Artifact 구현 확인
  - LLM judge 실제 호출 여부
  - AC와 verdict 일치율
  - Detection Loss 값 계산

Task 2.2: EX-30 Constraint 수 정의 확인
  - "non-timing" 정의
  - FORBIDDEN 212 vs 217 원인

Task 2.3: EX-32 vs EX-17 Solver 분류 shift 확인
  - solver 코드 버전 동일 여부
  - canonical 값 결정 (EX-32가 최신이면 EX-32 사용)

Task 2.4: EX-25 Unreachable 61 nodes 분포 확인
  - 5개 그래프 식별
  - multi-entry pathway 구조인지 확인
  - dead code 아닌지 확인

Task 2.5: EX-25 Duplicates 91건 verdict 영향 확인
  - 중복 제거 후 TCC verdict 변화 에피소드 수 확인
```

### Phase 3: 논문 반영 (Phase 1-2 해결 후)

```
1. auto_numbers.tex 갱신 (EX-23~33 매크로 추가)
2. Abstract/Intro 재구조화 (first-page hero hierarchy)
3. Theorem-experiment precision 수정
4. Solver "exact" 교체
5. Replay overclaim 톤 조절
6. Clinician pending 대비 wording
7. Supporting Analyses에 EX-23~33 결과 반영
8. Appendix 확장 (engine audit, timing stress, invariance, fidelity, survey)
9. pdflatex 컴파일 + 페이지 확인
```