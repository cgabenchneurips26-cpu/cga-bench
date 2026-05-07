# CGA-Bench CPG Selection Criteria v2: M7–M12 Refined Definitions + Claude Code Prompt

## Part 1: M7–M12 Refined Definitions

---

### M7. Recency & Currency (가이드라인 최신성)

**근거**: AGREE II는 가이드라인이 정기적으로 업데이트될 것을 권고하며, 일반적 간격은 5년. WHO GBD 2024에서도 최신 역학 데이터에 기반한 가이드라인의 중요성을 강조. CPG가 AI agent 평가에 사용되려면, 현재 임상 표준을 반영해야 reviewer를 설득할 수 있음.

**채점 기준**:

| 점수 | 조건 | 판정 소스 |
|---|---|---|
| 2 | 발행 또는 최종 업데이트가 **2020-01-01 이후** | YAML `meta.source_url` → 원문 발행연도 |
| 1 | 발행 또는 최종 업데이트가 **2015-01-01 ~ 2019-12-31** | 동일 |
| 0 | **2015년 이전** 발행이며, 이후 공식 업데이트/reaffirmation 없음 | 동일 |

**예외 규칙**: "Living guideline"(지속적 업데이트 체계, 예: WHO COVID-19)은 마지막 업데이트일 기준. "Reaffirmed without change"는 reaffirmation 연도 적용.

**자동화 가능성**: YAML `meta.publication_year` 필드 필요. 없으면 DOI에서 CrossRef API로 발행연도 추출.

---

### M8. Development Rigor — AGREE-Lite (개발 엄밀성)

**근거**: AGREE II 23개 항목 중 Domain 3 (Rigor of Development)이 전반적 품질 평가에 가장 큰 영향. 그러나 25개 CPG에 전체 AGREE II를 적용하는 것은 비현실적. 따라서 Domain 3의 **핵심 3개 항목**만 축약 평가.

**3개 체크 항목** (각각 Yes/No):

| 항목 | AGREE II 원본 | 판정 방법 |
|---|---|---|
| R1: Systematic evidence review | Item 7: "Systematic methods were used to search for evidence" | 가이드라인 Methods 섹션에 "systematic review", "literature search", "evidence synthesis" 등 명시 |
| R2: Evidence-recommendation linkage | Item 12: "There is an explicit link between the recommendations and the supporting evidence" | 각 권고사항에 개별 근거 등급(GRADE level, Class/LOE 등) 부여 여부 |
| R3: External review or public comment | Item 13: "The guideline has been externally reviewed by experts prior to its publication" | "external review", "public comment period", "peer review" 등 명시 |

**채점**:

| 점수 | 조건 |
|---|---|
| 2 | 3/3 충족 |
| 1 | 2/3 충족 |
| 0 | ≤ 1/3 충족 |

**자동화 가능성**: 반자동. YAML에 `meta.has_systematic_review`, `meta.has_evidence_linkage`, `meta.has_external_review` boolean 필드 추가. 초기값은 CPG 원문에서 수동 확인 후 1회 기입, 이후 자동 집계.

---

### M9. Time-to-Harm Severity (시간-위해 심각도)

**근거**: CGA-Bench의 핵심 thesis는 "timing violation이 임상적으로 중요하다"는 것. 이 기준은 **해당 CPG에서 시간 위반이 실제로 얼마나 심각한 결과를 초래하는지**를 평가. 논문의 consensus FA severity 분석(22.1% critical)과 직접 연결.

**정의**: 해당 CPG의 WITHIN 또는 BEFORE constraint 위반이 환자에게 초래할 수 있는 최악의 결과(worst-case outcome)를 기준으로 분류.

**채점 기준**:

| 점수 | 최악 결과 | 예시 | 판정 근거 |
|---|---|---|---|
| 2 | **사망 또는 비가역적 장애** — 분·시간 단위 delay가 mortality/morbidity에 직접 영향하는 근거 있음 | Stroke tPA window (NNT 변화/시간), Sepsis Hour-1 bundle (mortality per hour delay), STEMI door-to-balloon, Cardiac arrest ACLS | 원문 CPG에 "mortality", "death", "irreversible" 등의 언급 + 시간-결과 관계 데이터(예: "every 15-min delay increases mortality by X%") |
| 1 | **합병증 증가 또는 입원 연장** — delay가 morbidity를 증가시키지만 직접적 사망 위험은 낮음 | DKA insulin timing, Pneumonia antibiotics, DVT prophylaxis, AKI fluid resuscitation | 원문 CPG에 "complication", "prolonged stay", "adverse outcome" 등 |
| 0 | **경미하거나 불확실** — timing이 결과에 미치는 영향이 약하거나, CPG 자체에 timing constraint가 없음 | Chronic disease management, Screening guidelines, Rehab protocols | Timing constraint 부재 또는 deadline이 일/주 단위 |

**자동화 가능성**: 반자동. YAML에 `meta.time_to_harm_severity: critical|moderate|mild` 필드 추가. 근거 문장도 함께 기록: `meta.time_to_harm_evidence: "SSC 2021: each hour delay in Abx associated with 4% mortality increase"`.

---

### M10. Disease Burden / Prevalence (질병부담)

**근거**: benchmark의 **generalizability**와 **real-world relevance**를 정당화. WHO GBD 2021 데이터에서 글로벌 사망/DALY 상위 원인과의 매핑. Emergency condition 분류(Lancet Commission)도 참조.

**정의**: 해당 CPG가 커버하는 질환/상태가 WHO GBD Top-20 사망/DALY 원인 또는 응급의학 핵심 영역에 해당하는지.

**채점 기준**:

| 점수 | 조건 | 매핑 리스트 (WHO GBD 2021 기준) |
|---|---|---|
| 2 | **WHO GBD Top-15 사망 원인** 또는 **응급실 방문 Top-10 원인**에 직접 매핑 | IHD, Stroke, COPD, Lower respiratory infection, Neonatal conditions, Trachea/bronchus/lung cancers, Diabetes mellitus, Kidney diseases, Diarrhoeal diseases, Road injury, Hypertensive heart disease, HIV/AIDS, TB, Cirrhosis, Self-harm / Sepsis, Cardiac arrest, Acute MI, Trauma, Anaphylaxis, Status epilepticus |
| 1 | **GBD Top-30** 또는 **전문과별 주요 질환**이나 Top-15에는 해당 안 됨 | Heart failure, Atrial fibrillation, Asthma, Breast cancer, Colorectal cancer, Falls, Burns, Meningitis (Top-15 아닌 경우), DVT/PE |
| 0 | **GBD Top-30에 해당 안 됨** — 희귀질환, 단일 시술, 또는 매우 제한적 인구 | 특정 희귀 유전질환, 미용 시술, 극히 제한적 상황 |

**자동화 가능성**: 자동. YAML `meta.icd10_codes` 또는 `meta.disease_category` 필드를 GBD cause list와 매핑하는 lookup table 구현. `scripts/gbd_mapper.py`에서 ICD-10 → GBD cause → tier 자동 분류.

**GBD 매핑 테이블 구축**: WHO GBD 2021 Results 다운로드 → Top-30 causes by DALY (global, both sexes, all ages) → ICD-10 코드 매핑 → JSON lookup.

---

### M11. Contraindication Density (금기/상호작용 풍부도)

**근거**: Theorem 1 Case 1 (π_term blind to FORBID), Case 4 (π_nctx blind to conditional FORBID)의 경험적 테스트를 위해 FORBID constraint가 풍부한 CPG가 필요. 논문의 non-timing blind spot 분석에서 354 episodes 중 315건이 FORBIDDEN-only. 현재 M6은 `before + within`만 집계하므로 FORBID를 별도 지표로 분리.

**정의**: 해당 CPG YAML에서 추출 가능한 FORBID 유형 constraint의 수. 여기서 FORBID는 다음을 포함:
- **Node-level forbidden**: 특정 환자 상태에서 특정 action이 금기 (예: tPA + warfarin INR>1.7)
- **Combination forbidden**: 두 action의 동시/순차 사용이 금기 (예: anticoagulant + tPA)
- **Drug-drug interaction**: 약물 상호작용 기반 금기
- **Allergy-gated**: 알러지 조건 기반 금기

**채점 기준**:

| 점수 | 조건 | YAML 필드 |
|---|---|---|
| 2 | **FORBID constraint ≥ 5개** (node-level + combination + drug interaction 합산) | `rules[].type == "forbidden"` 카운트 |
| 1 | **FORBID constraint 2–4개** | 동일 |
| 0 | **FORBID constraint ≤ 1개** | 동일 |

**자동화 가능성**: 완전 자동. 기존 YAML 파서에서 `forbidden` 타입 규칙 카운트. 추가로 `conditional_rules` 중 action이 `forbid`인 것도 합산.

```python
# Pseudocode
def score_m11(cpg_yaml):
    forbid_count = sum(1 for r in cpg_yaml['rules'] 
                       if r.get('type') == 'forbidden' 
                       or r.get('constraint_type') == 'FORBID')
    if forbid_count >= 5: return 2
    elif forbid_count >= 2: return 1
    else: return 0
```

---

### M12. Multi-Pathway Branching (분기 경로 다양성)

**근거**: Proposition 1 (Monotone Violation)은 B=∅ (acceptable alternative branches 없음) 전제에서만 성립. B≠∅인 가이드라인은 formalism의 경계 사례를 테스트하며, 실제 임상에서 "clinically equivalent alternatives"는 흔함 (예: stroke에서 tPA vs mechanical thrombectomy, 항생제 선택에서 1st-line vs allergy-alternative). 또한 CPG-on-FHIR의 CPGStrategy/CPGPathway 구조와 직접 매핑.

**정의**: 해당 CPG YAML에서 decision node (환자 상태에 따라 다른 경로를 타는 분기점)의 수.

**분기점의 조작적 정의**:
- **Type A — Guard-gated branch**: `conditional_rules`에서 동일 graph position에 대해 서로 다른 `guard` 조건이 다른 action pathway를 활성화하는 경우 (예: tPA eligible vs not eligible)
- **Type B — Alternative-action branch**: `acceptable_alternatives` 필드에서 동일 clinical goal에 대해 2개 이상의 action sequence가 정의된 경우 (예: IV alteplase vs mechanical thrombectomy)
- **Type C — Dose/route branch**: 동일 약물의 투여 경로/용량이 환자 체중/신기능 등에 따라 분기하는 경우 (formalism 관점에서는 같은 action이므로 카운트하지 않음 — M12에서 제외)

**채점 기준**:

| 점수 | 조건 | 판정 |
|---|---|---|
| 2 | **Type A + Type B 합산 ≥ 3개** | 복잡한 multi-pathway guideline |
| 1 | **합산 1–2개** | 단순 분기 |
| 0 | **분기 없음** — 단일 linear pathway | 모든 환자에게 동일 경로 |

**자동화 가능성**: 반자동.
- Type A: YAML `conditional_rules`에서 동일 `target_node`에 대해 서로 다른 `guard`가 있는 경우 → 자동 감지 가능
- Type B: YAML에 `acceptable_alternatives` 또는 `branch_set` 필드가 있으면 자동; 없으면 수동 확인 후 `meta.branch_count` 기입

```python
# Pseudocode
def score_m12(cpg_yaml):
    # Type A: guard-gated branches
    from collections import Counter
    target_guards = Counter()
    for rule in cpg_yaml.get('conditional_rules', []):
        target_guards[rule['target_node']] += 1
    type_a = sum(1 for count in target_guards.values() if count >= 2)
    
    # Type B: explicit alternatives
    type_b = len(cpg_yaml.get('acceptable_alternatives', []))
    
    total = type_a + type_b
    if total >= 3: return 2
    elif total >= 1: return 1
    else: return 0
```

---

## Part 2: Claude Code 통합 프롬프트

아래 프롬프트를 Claude Code 세션에서 실행하면:
1. 기존 M1–M6 + 신규 M7–M12 정의를 통합한 `02_selection_criteria_v2.md` 생성
2. `scripts/score_cpg_v2.py` 채점 스크립트 생성
3. 기존 25개 CPG YAML에 `meta` 필드 확장 템플릿 생성
4. 소급 채점 실행 + Tier 분류 리포트 생성

---

```markdown
# Claude Code Prompt: CGA-Bench CPG Selection Criteria v2 구현

## 컨텍스트

CGA-Bench는 clinical AI agent의 trace-level conformance를 평가하는 벤치마크이다.
현재 25개 CPG(Clinical Practice Guideline)를 YAML 그래프로 인코딩해서 사용 중이다.
CPG 선정 기준은 현재 M1–M6까지 6개 지표로, `docs/cpg_expansion_v7/01_selection_criteria_v1.md`에 정의되어 있다.

이번 작업은 M7–M12 6개 지표를 추가하여 3-Axis 프레임워크로 확장하는 것이다.

## 3-Axis 프레임워크 개요

### Axis 1: Guideline Quality & Trustworthiness (M3, M5, M7, M8)
- M3: Tier-1 society issuance (기존, M3c GRADE 강화: 0–2)
- M5: Documented source (기존, 0–1)
- M7: Recency & Currency (신규, 0–2)
- M8: Development Rigor — AGREE-Lite (신규, 0–2)

### Axis 2: Clinical Significance & Safety Impact (M4, M9, M10, M11)
- M4: Evidence/scale (기존, 0–1)
- M9: Time-to-Harm Severity (신규, 0–2)
- M10: Disease Burden / Prevalence (신규, 0–2)
- M11: Contraindication Density (신규, 0–2)

### Axis 3: Formalizability & Benchmark Utility (M1, M2, M6, M12)
- M1: Time-sensitivity (기존, 0–1)
- M2: Sequential dependency (기존, 0–1)
- M6: Conditional richness (기존, 0–1)
- M12: Multi-Pathway Branching (신규, 0–2)

**총점 범위**: 0–19
**Tier 분류**:
- Tier S (≥ 15): 핵심 벤치마크
- Tier A (11–14): 주요 벤치마크
- Tier B (7–10): 보조 벤치마크
- Excluded (< 7): 포함 부적절

## 작업 순서

### Step 1: 문서 생성
파일: `docs/cpg_expansion_v7/02_selection_criteria_v2.md`

내용:
- M1–M6 기존 정의 (v1에서 가져오기)
- M3c 강화: GRADE/SIGN/Oxford CEBM = 2점, 자체 등급 = 1점, 없음 = 0점
- M7–M12 신규 정의 (아래 상세 정의 참조)
- 3-Axis 프레임워크 다이어그램 (Mermaid)
- Tier 분류 기준
- 학술적 근거 (AGREE II, GRADE, WHO GBD 참조)

### Step 2: YAML meta 필드 확장 템플릿

기존 25개 CPG YAML 파일의 `meta` 섹션에 추가해야 할 필드:

```yaml
meta:
  # 기존 필드 유지
  source_url: "https://..."
  doi: "10.xxxx/yyyy"
  
  # M7 Recency
  publication_year: 2021          # 발행연도
  last_update_year: 2023          # 최종 업데이트/reaffirmation 연도 (없으면 publication_year와 동일)
  
  # M8 AGREE-Lite
  has_systematic_review: true     # Methods에 체계적 문헌검색 명시
  has_evidence_linkage: true      # 각 권고에 개별 근거등급 부여
  has_external_review: false      # 외부 검토/공개 의견수렴 수행
  
  # M9 Time-to-Harm
  time_to_harm_severity: "critical"  # critical | moderate | mild
  time_to_harm_evidence: "SSC 2021: each hour delay in antibiotics associated with 4% increase in mortality"
  
  # M10 Disease Burden
  icd10_codes: ["A41", "R65.2"]   # 해당 질환 ICD-10 코드
  gbd_cause_category: "Sepsis"     # WHO GBD cause name
  gbd_rank_death: 12               # GBD 사망원인 순위 (없으면 null)
  gbd_rank_daly: 15                # GBD DALY 순위 (없으면 null)
  is_emergency_condition: true     # Lancet Commission emergency condition 해당 여부
  
  # M11 (자동 계산 가능 — 아래는 override용)
  # forbid_count는 rules에서 자동 집계하되, 수동 보정이 필요한 경우 여기에 override
  forbid_count_override: null
  
  # M12 Multi-Pathway
  branch_count_type_a: 2           # Guard-gated branches
  branch_count_type_b: 1           # Alternative-action branches
```

### Step 3: 채점 스크립트

파일: `scripts/score_cpg_v2.py`

입력: `cpg_graphs/` 디렉토리의 모든 YAML 파일
출력:
1. `reports/cpg_scores_v2.json` — 25개 CPG × 12개 지표 점수 + 총점 + Tier
2. `reports/cpg_scores_v2.md` — 사람이 읽을 수 있는 마크다운 테이블
3. stdout에 요약 통계 출력

각 지표 채점 로직:

```python
# M1: Time-sensitivity (기존)
# deadline ≤ 60min인 mandatory action 수 ≥ 3 → 1, else 0

# M2: Sequential dependency (기존)
# before-constraint 수 ≥ 1 → 1, else 0

# M3: Tier-1 society (기존 + M3c 강화)
# M3a(전문학회) + M3b(peer-reviewed) + M3c(GRADE등급: 0/1/2)
# composite = M3a(0/1) + M3b(0/1) + min(M3c, 1)  -- M3c가 2여도 composite은 max 3
# composite ≥ 2 → 1, else 0 (기존 호환)
# 별도로 M3c_grade_score도 기록 (0/1/2)

# M4: Evidence/scale (기존)
# Class I 있거나 required_action ≥ 10 → 1, else 0

# M5: Documented source (기존)
# DOI/URL 1개 이상 → 1, else 0

# M6: Conditional richness (기존)
# (before+within) ≥ 8 또는 nodes ≥ 7 → 1, else 0

# M7: Recency
def score_m7(meta):
    year = meta.get('last_update_year') or meta.get('publication_year')
    if year is None: return 0
    if year >= 2020: return 2
    if year >= 2015: return 1
    return 0

# M8: AGREE-Lite
def score_m8(meta):
    checks = [
        meta.get('has_systematic_review', False),
        meta.get('has_evidence_linkage', False),
        meta.get('has_external_review', False),
    ]
    passed = sum(1 for c in checks if c)
    if passed >= 3: return 2
    if passed >= 2: return 1
    return 0

# M9: Time-to-Harm
def score_m9(meta):
    severity = meta.get('time_to_harm_severity', 'mild')
    return {'critical': 2, 'moderate': 1, 'mild': 0}.get(severity, 0)

# M10: Disease Burden
def score_m10(meta):
    # WHO GBD Top-15 death or emergency condition → 2
    # GBD Top-30 or specialty major → 1
    # else → 0
    death_rank = meta.get('gbd_rank_death')
    daly_rank = meta.get('gbd_rank_daly')
    is_emergency = meta.get('is_emergency_condition', False)
    
    if is_emergency:
        return 2
    if death_rank and death_rank <= 15:
        return 2
    if daly_rank and daly_rank <= 15:
        return 2
    if (death_rank and death_rank <= 30) or (daly_rank and daly_rank <= 30):
        return 1
    return 0

# M11: Contraindication Density
def score_m11(cpg_data, meta):
    override = meta.get('forbid_count_override')
    if override is not None:
        count = override
    else:
        count = sum(1 for r in cpg_data.get('rules', [])
                    if r.get('type') == 'forbidden'
                    or r.get('constraint_type') == 'FORBID')
    if count >= 5: return 2
    if count >= 2: return 1
    return 0

# M12: Multi-Pathway Branching
def score_m12(cpg_data, meta):
    type_a = meta.get('branch_count_type_a', 0)
    type_b = meta.get('branch_count_type_b', 0)
    
    # 자동 감지 시도 (Type A)
    if type_a == 0:
        from collections import Counter
        target_guards = Counter()
        for rule in cpg_data.get('conditional_rules', []):
            target = rule.get('target_node') or rule.get('target')
            if target:
                target_guards[target] += 1
        type_a = sum(1 for c in target_guards.values() if c >= 2)
    
    # Type B: acceptable_alternatives
    if type_b == 0:
        type_b = len(cpg_data.get('acceptable_alternatives', []))
    
    total = type_a + type_b
    if total >= 3: return 2
    if total >= 1: return 1
    return 0
```

### Step 4: GBD Lookup Table

파일: `data/gbd_top30_causes.json`

WHO GBD 2021 기준 Top-30 사망/DALY 원인과 ICD-10 매핑.
이 테이블은 M10 자동 채점에 사용됨.

주요 엔트리 (사망 기준 Top-15):
1. Ischaemic heart disease (I20-I25)
2. Stroke (I60-I69)
3. COVID-19 (U07)
4. COPD (J40-J44)
5. Lower respiratory infections (J09-J22)
6. Neonatal conditions (P00-P96)
7. Trachea/bronchus/lung cancers (C33-C34)
8. Diabetes mellitus (E10-E14)
9. Kidney diseases (N17-N19)
10. Diarrhoeal diseases (A00-A09)
11. Road injury (V01-V99)
12. Hypertensive heart disease (I11)
13. HIV/AIDS (B20-B24)
14. Tuberculosis (A15-A19)
15. Cirrhosis (K70-K76)

Emergency conditions (Lancet Commission 추가):
- Sepsis/septic shock (A41, R65.2)
- Cardiac arrest (I46)
- Acute MI / STEMI (I21)
- Status epilepticus (G41)
- Anaphylaxis (T78.2)
- Major trauma (S00-T14)
- Acute abdomen (K35, K80-K81)
- Meningitis (G00-G03)
- DKA (E10.1, E13.1)
- Pulmonary embolism (I26)
- Burns (T20-T32)

### Step 5: 소급 채점 실행

1. 먼저 기존 25개 YAML에 `meta` 필드가 있는지 확인
2. 없으면 → meta 템플릿을 append하는 스크립트 실행
3. M1–M6 + M7–M12 전체 채점
4. 자동 채점 가능한 것 (M1, M2, M5, M6, M7, M10, M11): 바로 실행
5. 반자동 (M3, M4, M8, M9, M12): 초기값 생성 후 사람 검증 TODO 마크
6. Tier 분류 + 리포트 생성

### Step 6: 검증 및 리포트

출력 예시:
```
=== CGA-Bench CPG Selection Criteria v2 — Scoring Report ===

Total CPGs scored: 25
Score distribution: min=X, max=Y, mean=Z, median=W

Tier S (≥15): N개 — [cpg_name_1, cpg_name_2, ...]
Tier A (11-14): N개 — [...]
Tier B (7-10): N개 — [...]
Excluded (<7): N개 — [...]

Per-Axis Summary:
  Quality (M3+M5+M7+M8, max 7): mean=X
  Clinical (M4+M9+M10+M11, max 7): mean=X
  Formalizability (M1+M2+M6+M12, max 5): mean=X

TODO items requiring human review:
  - cpg_name_1: M8 (AGREE-Lite) — needs manual check of Methods section
  - cpg_name_2: M9 (Time-to-Harm) — severity classification pending
  ...
```

## 핵심 원칙

1. **기존 M1–M6 채점 결과와 역호환**: v1에서 Tier-valid (≥4점)이었던 CPG가 v2에서도 최소 Tier B 이상이어야 함. 역전이 발생하면 경고 출력.

2. **자동화 우선**: M1, M2, M5, M6, M7, M10, M11은 YAML만으로 완전 자동 채점. M3, M4, M8, M9, M12는 meta 필드가 채워져 있으면 자동, 아니면 TODO.

3. **논문 연동**: 최종 리포트에서 Appendix A.11(또는 새 appendix)에 들어갈 테이블 LaTeX 자동 생성:
```latex
\begin{table}[h]
\caption{CPG selection criteria scores (M1--M12) for all \numGraphsTotal{} guidelines.}
...
\end{table}
```

4. **학술적 근거 참조**: 문서 상단에 AGREE II (Brouwers et al., CMAJ 2010), GRADE (Guyatt et al., BMJ 2008), WHO GBD 2021, Lancet Commission on Emergency Care 인용.

5. **경로**: 모든 파일은 프로젝트 루트 기준:
   - `docs/cpg_expansion_v7/02_selection_criteria_v2.md`
   - `scripts/score_cpg_v2.py`
   - `data/gbd_top30_causes.json`
   - `reports/cpg_scores_v2.json`
   - `reports/cpg_scores_v2.md`
```

---

위 프롬프트를 Claude Code에 제공하면 됩니다. YAML 파일 구조만 확인되면 바로 실행 가능합니다.