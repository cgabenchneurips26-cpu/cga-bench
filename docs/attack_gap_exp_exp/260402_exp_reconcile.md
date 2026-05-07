# EXP-RECONCILE: UP Rate Numerator 불일치 최종 해결

## 배경

논문의 핵심 수치에 불일치가 발견됨:

| Metric | 논문(Exp11) | P2 Bootstrap | 차이 |
|--------|------------|--------------|------|
| UP_strong | 27/78 (34.6%) | 28/78 (35.9%) | +1 |
| UP_crit | 13/78 (16.7%) | 10/78 (12.8%) | -3 |
| UP_any | 48/78 (61.5%) | 50/78 (64.1%) | +2 |

이전 V3 검증에서 5가지 method가 모두 다른 값을 산출했음:
- (A) Event field guideline_class → 22/78
- (B) Graph YAML node lookup → 50/78 (95% node가 STRONG이라 overcounts)
- (C) Exp11 re-evaluation → 27/78
- (D) severity >= 0.7 → 22/78
- (E) any hard vtype → 50/78

## 목표

1. 불일치의 정확한 원인을 episode-level로 추적
2. 정의를 하나로 확정
3. 확정된 정의로 모든 수치를 재계산
4. tracking_sheet.md의 11개 location을 업데이트

## 작업

### Step 1: 불일치 episode 특정 (30분)

```
아래 두 소스를 episode-by-episode로 비교해줘:

Source A: Exp11 (gap_experiments.py exp11)의 UP_strong 판정
Source B: P2 bootstrap (v3_p2_timestamp_sensitivity.py 또는 
          v3_p4_scenario_clustered_ci.py)의 UP_strong 판정

1. 78개 completion-passing episode 전부에 대해:
   | episode_id | model | scenario | run | 
   | Exp11_strong | P2_strong | MATCH? |

2. 불일치하는 episode를 전부 나열
   (예상: 1~3개)

3. 각 불일치 episode에 대해:
   - Exp11이 STRONG이라고 판단한/안 한 이유
   - P2가 STRONG이라고 판단한/안 한 이유
   - 어떤 constraint가 판정을 가르는지
   - 해당 constraint의 evidence level은?

4. UP_crit에 대해서도 동일하게:
   Exp11 = 13, P2 = 10 → 3개 episode 차이 추적

5. UP_any에 대해서도:
   Exp11 = 48, P2 = 50 → 2개 episode 차이 추적
   (이건 V3에서 이미 "2개 episode에서 V3은 violation_events에 
   timing/sequence 위반을 감지하지만 Exp11에서는 미확인"이라고 
   밝혀진 바 있음 — 이것과 같은 2개인지 확인)
```

### Step 2: 정의 확정 (15분)

```
불일치 원인을 바탕으로, 아래 중 하나를 논문의 공식 정의로 선택해줘:

Option A: Exp11 method (YAML graph 기반 재평가)
  - 장점: graph-grounded, 가장 보수적
  - 단점: evidence lookup 과정에서 일부 constraint를 놓칠 수 있음

Option B: P2/P4 method (기존 violation_events 기반)
  - 장점: 기존 파이프라인 결과와 일치
  - 단점: violation_events의 guideline_class field가 불완전할 수 있음

선택 기준:
1. 어떤 method가 "guideline-strong hard constraint violation"의 
   정의에 더 충실한가?
2. 어떤 method가 더 reproducible한가? (코드만 보면 재현 가능한가)
3. 어떤 method가 reviewer에게 더 방어 가능한가?

추천과 그 이유를 1문단으로 적어줘.
```

### Step 3: 확정 정의로 전수 재계산 (30분)

```
확정된 method로 아래를 전부 재계산해줘:

1. 전체 (All models):
   - UP_strong: ?/78 = ?%
   - UP_crit: ?/78 = ?%
   - UP_any: ?/78 = ?%

2. 모델별:
   | Model | N_pass | UP_crit | UP_strong | UP_any |
   120B, 27B, 35B, 4B 각각

3. 전체 episode 기준 absolute prevalence:
   - hard violation이 있는 episode: ?/180 = ?%
   - completion-passing AND strong violation: ?/180 = ?%

4. Core vs Expansion:
   | Subset | CP | UP_strong | UP_crit |

5. 9 poster-child episodes (모든 process-oblivious evaluator가 
   pass하면서 hard violation이 있는 episode) 수 재확인
```

### Step 4: Scenario-Clustered Bootstrap CI (30분)

```
Step 3에서 확정된 UP rate에 대해 scenario-clustered bootstrap CI를 계산해줘.

주의: 기존 P4는 CGA mean에 대한 CI만 계산했음.
여기서 필요한 건 UP_strong RATE에 대한 CI.

방법:
1. resampling unit = scenario (15개)
2. 각 bootstrap iteration에서 15개 scenario를 복원추출
3. 선택된 scenario의 모든 completion-passing episode에서 
   UP_strong rate 계산
4. B = 10,000회
5. BCa 95% CI

계산 대상:
- UP_strong: 전체 + 모델별
- UP_crit: 전체
- UP_any: 전체

출력 형식:
"34.6% [XX.X%--YY.Y%, 95% scenario-clustered CI]"
```

### Step 5: tracking_sheet.md 업데이트

```
확정된 숫자로 tracking_sheet.md의 아래 11개 location을 업데이트:

(tracking_sheet에서 DISC-1으로 태그된 모든 항목)

각 항목의 상태를 ⬜ EMPTY 또는 🔧 NEEDS_FIX에서 ✅ CONFIRMED로 변경.
{CI} placeholder도 실제 CI 값으로 교체.
```

## 출력

1. reconciliation_report.md:
   - 불일치 episode 목록과 원인
   - 확정 정의와 선택 이유
   - 확정 수치 전체
   - CI 전체

2. tracking_sheet.md 업데이트 (diff 형식)

3. main.tex 수정이 필요한 11개 위치의 정확한 old→new 매핑

## 파일 경로

Exp11 결과: [경로]
P2/P4 결과: [경로]
Episode 데이터: [경로]
tracking_sheet.md: tracking/tracking_sheet.md
```