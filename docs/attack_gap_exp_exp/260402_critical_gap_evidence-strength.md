# EVIDENCE_STRENGTH 매핑 수정

## 문제

IIa → STRONG 매핑 때문에 UP_strong = UP_any (61.5%).
Tier 구분이 무의미해짐. IIa는 MODERATE여야 함.

## Step 1: 현재 매핑 확인 + 수정 (30min)

```
gap_experiments.py에서 EVIDENCE_STRENGTH 매핑을 찾아서 수정해줘.

올바른 매핑:

EVIDENCE_STRENGTH = {
    # AHA/ACC Classification
    "I": "STRONG",        # Class I: strong recommendation
    "IIa": "MODERATE",    # Class IIa: reasonable (moderate)
    "IIb": "MODERATE",    # Class IIb: may be considered (weak)
    "III": "STRONG",      # Class III: harmful — STRONG (negative)
    
    # SSC / KDIGO / GRADE
    "strong": "STRONG",
    "weak": "MODERATE",
    "conditional": "MODERATE",
    
    # Evidence levels (fallback)
    "A": "STRONG",        # High quality evidence
    "B": "MODERATE",      # Moderate quality
    "B-R": "MODERATE",    # Moderate, randomized
    "B-NR": "MODERATE",   # Moderate, non-randomized
    "C": "MODERATE",      # Low quality / consensus
    "C-LD": "MODERATE",   # Limited data
    "C-EO": "MODERATE",   # Expert opinion
    "D": "MODERATE",      # Very low quality
}

주의: Class III (harmful)은 STRONG으로 유지.
이건 "strongly recommended NOT to do"이므로 
forbidden constraint에 해당하면 STRONG이 맞음.

수정 후 저장.
```

## Step 2: 14 YAML의 node별 분류 확인 (30min)

```
수정된 매핑으로, 14 YAML × 113 nodes의 
STRONG vs MODERATE 분포를 재확인:

| Graph | Total nodes | STRONG (Class I, III, Level 1, Grade A) |
|       |             | MODERATE (Class IIa/IIb, Level 2, Grade B/C) |

특히:
- ssc_sepsis_hour1: antibiotics WITHIN이 STRONG인지 확인
  (SSC 2021에서 이건 Strong recommendation, High quality = STRONG)
- ada_dka_management: insulin timing이 어떤 class인지
- aha_chest_pain: PCI timing이 Class I인지 확인

이전에 누락 → MODERATE fallback이었던 node들이
이제 올바르게 분류되는지 확인.
```

## Step 3: Exp11 재실행 + 새 수치 (1h)

```
수정된 매핑으로 Exp11 재실행:

1. event_level_hardviol_v4.json 생성
2. 새 UP_strong, UP_crit, UP_any:
   - UP_any는 변하면 안 됨 (48/78)
   - UP_strong < UP_any 여야 함 (tier 구분이 살아남)
   - UP_crit <= UP_strong

3. 예상:
   - 기존 27/78은 "Class I only"가 strong인 경우
   - 새 수치는 그보다 같거나 약간 높을 것 
     (Step 1의 evidence fix가 일부 None→Class I를 추가했으므로)
   - 하지만 IIa가 MODERATE로 내려가므로 일부 상쇄

4. 모델별, domain별, scenario별 breakdown
```

## Step 4: Downstream 전체 재계산 (1h)

```
새 UP_strong으로:
1. Scenario-clustered bootstrap CI
2. Verdict matrix (all evaluators × strong tier)
3. Stratification (Core/Expansion)
4. Instrumentation ablation
5. Domain spread

+ 이전 결과와 비교 delta table
```

## Step 5: Sanity Check (15min)

```
새 결과에서 확인:

1. UP_strong < UP_any (tier 구분 존재)
2. UP_crit < UP_strong (severity gradient 존재)
3. Sepsis UP_strong > 0 (evidence fix 효과)
4. DKA/ACS는 여전히 높은 UP_strong
5. 전체 수치가 합리적인 범위 (20-50% 정도)

만약 UP_strong이 여전히 UP_any와 같으면:
→ 매핑에 여전히 문제가 있음
→ 14 YAML의 recommendation_class 분포를 다시 확인
```