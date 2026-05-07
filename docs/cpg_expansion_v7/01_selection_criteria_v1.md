# CPG Selection Criteria v1 — M1~M6 Rubric

**작성일**: 2026-04-22
**적용 대상**: CGA-Bench v7 CPG 확장 (기존 25 → +99 후보 평가)
**목적**: 기존의 주관적 Tier S/A/B 분류를 폐기하고, NeurIPS 리뷰어가 재현할 수 있는 **정량적 6-지표 선정 기준**을 수립한다.

---

## 1. 배경 — 왜 이 기준이 필요한가

논문 초안에서 "Tier S / Tier A / Tier B"는 subjective grading이었고, 각 Tier의 정의가 "clear deadline", "sequential nature" 같은 **정성적 문구**에 의존했다. 리뷰어는 "왜 이 가이드라인은 Tier S이고 저건 Tier A인가"를 쉽게 반박할 수 있다.

대신, **기존 25 CPG의 공통 속성을 역추적하여 얻은 6개 정량 지표**로 후보를 점수화하면, 동일 guideline 입력에 대해 항상 동일한 점수가 나오도록 보장할 수 있다.

**핵심 주장**: 25 CPG는 임의로 선정된 것이 아니라 "M1~M6 중 최소 4개를 충족하는 가이드라인"이라는 measurable rule로 설명 가능하다.

---

## 2. 6개 정량 지표 (M1~M6)

| ID | 지표명 | 정의 (measurable) | 25 CPG 충족률 |
|---|---|---|---|
| **M1** | Time-sensitivity | 가이드라인 내 **deadline ≤ 60 min** 인 mandatory action이 **≥ 3개** 존재 | 60% (15/25) |
| **M2** | Sequential dependency | 가이드라인 내 **before-constraint** (액션 A → 액션 B 순서 요구) 수가 **≥ 1개** | 84% (21/25) |
| **M3** | Tier-1 society issuance | 발행기관이 아래 Tier-1 학회 목록에 포함 | 96% (24/25) |
| **M4** | Evidence/scale | **Class I recommendation** 명시 **OR** required_action 수 **≥ 10개** | 96% (24/25) |
| **M5** | Documented source | 공식 학회/학술지 발행문에 **DOI/URL/ISBN** 확보 가능 | 100% (25/25) |
| **M6** | Conditional richness | (before + within-constraint) 총수 **≥ 8개** **OR** 예상 노드 수 **≥ 7** | 변동 (분포 추적 중) |

### 2.1 M1 세부 — Time-sensitivity

- **측정 방법**: CPG YAML의 `nodes.*.deadline_minutes` 필드를 순회. `deadline_minutes ≤ 60` 인 mandatory action 수 집계.
- **임계값 근거**: SSC Hour-1 Bundle, Door-to-Balloon 90min, AHA tPA 60min door-to-needle 등 응급의학 핵심 deadline이 1시간 단위로 수렴.
- **부정 예**: 만성질환 장기관리 (고혈압 외래), Kawasaki (IVIG <10일), Myasthenic crisis (hours-days).

### 2.2 M2 세부 — Sequential dependency

- **측정 방법**: 가이드라인 프로토콜에 "Action A MUST precede Action B" 형태의 순서 제약 존재 여부.
- **구현**: CPG YAML의 `before_constraints` 리스트 length.
- **부정 예**: ADA Severe Hypoglycemia (단일 action — D50 IV only), 단순 antidote-only toxicology.

### 2.3 M3 세부 — Tier-1 society 정량 기준

**주의**: 단순 학회명 목록으로는 "왜 이 학회는 포함하고 저건 뺐냐" 공격에 취약. 따라서 **3-part composite criterion**을 사용한다.

다음 3가지 하위 기준 중 **최소 2개**를 만족하면 M3=1:

- **M3a (Specialty representation)**: 발행기관이 해당 의학 전문 분야에서 다음 중 하나의 지위를 가진 professional society:
  - ABMS/AOA (미국) / RCP/RCS (영국) / UEMS (유럽) 같은 **specialty certification board**와 affiliate
  - 또는 해당 전문 분야의 **국가 대표 학회** (예: ACOG = 미국 산부인과 대표)
  - 또는 해당 전문 분야의 **국제 전문 학회** (예: KDIGO = 국제 신장학회, WHO = 국제 보건기구)
  - → 정부기관(지역/주 단위 health department), 단일 저자 review, 비학회 네트워크는 미달

- **M3b (Peer-reviewed publication)**: 가이드라인이 다음 중 하나로 발행:
  - **PubMed-indexed journal**에 published (DOI 확보 가능)
  - 또는 학회 **공식 간행물**(e.g., *Circulation*, *Diabetes Care*) series에 published
  - → 학회 웹사이트 PDF만 있고 peer review 없으면 미달

- **M3c (Evidence-based methodology)**: 가이드라인 본문에 다음 중 하나를 명시:
  - **GRADE** (Grading of Recommendations Assessment)
  - **ILCOR** CoSTR (resuscitation)
  - **OCEBM** levels of evidence
  - **Cochrane** systematic review 기반
  - 또는 **systematic literature review + external expert panel** 프로세스 명시
  - → 단순 narrative review 또는 개인 견해 기반이면 미달

**최종 판정**: (M3a + M3b + M3c) ≥ 2 → M3 = 1

### 2.3.1 대표 Tier-1 society (기존 25 CPG 기반, 전수 아님)

아래 학회/기관은 위 criterion을 **전부 또는 2/3 이상 만족**하는 것으로 pre-validated. 새 가이드라인이 이 목록의 기관 발행이면 M3=1로 자동 qualifying.

**Cardiology**: AHA, ACC, HRS, AHA/ASA, ESC, ESVS, ERC
**Nephrology**: KDIGO, UKKA, ERA
**Infectious / Global**: IDSA, WHO, CDC, SSC
**Pulmonary**: ATS, ERS, GOLD, GINA, BTS, DAS
**GI / Hepatology**: ACG, AGA, AASLD
**Surgery / Trauma**: ACS COT, EAST, WSES, ABA, ISBI, AOSpine
**Endocrinology**: ADA, ATA, Endocrine Society, AACE, ISPAD, EASD
**Obstetrics**: ACOG, SMFM, RCOG
**Pediatrics**: AAP, NRP, ISPAD
**Neurology**: AAN, NCS, AES, EAN
**Toxicology**: AACT, UHMS, EXTRIP consortium
**Hematology / Oncology**: ASH, ASCO, ISTH, NCCN, AABB
**GU**: AUA, EAU
**Psychiatry**: APA
**Anesthesia**: ASA, SCCM
**Ophthal / ENT**: AAO, ENT-UK
**Environmental**: WMS
**Neuro-trauma**: BTF

### 2.3.2 배제 사례 (M3=0 예시)

| 사례 | 배제 이유 | 적용되는 M3 하위 기준 실패 |
|---|---|---|
| NSW Health Rhabdomyolysis protocol | 호주 뉴사우스웨일스 주정부 보건당국. 전문의 학회 아님 | M3a 미달 (정부기관) |
| BIMDG (British Inherited Metabolic Disease Group) | UK 내 전문가 네트워크이나 ABMS/RCP 인증 학회 아님, peer-reviewed journal publication 약함 | M3a 부분·M3b 미달 |
| Boyer & Shannon Serotonin Syndrome (NEJM 2005) | 개인 저자 review article. 학회 endorsement 없음 | M3a 미달 |
| "Ludwig Angina / PTA" general surgery literature | 공식 학회 가이드라인 부재, 교과서 수준만 존재 | M3a, M3b, M3c 모두 미달 |
| Hospital-specific internal protocol | 단일 병원 정책. 학회 발행 아님 | M3a 미달 |

### 2.3.3 Edge case 처리 원칙

- **Multi-society joint publication** (예: AHA/ESC Endocarditis 2023): 2개 학회가 공동 발행하면 M3=1 자동.
- **Society-endorsed but author-led** (예: EXTRIP 2015 Li toxicity): EXTRIP Workgroup이 학회는 아니지만 AACT·EAPCCT 등 Tier-1 society가 endorse → M3b, M3c 만족 시 M3=1.
- **Consensus statement vs full guideline**: consensus statement도 peer-reviewed journal published + GRADE/systematic review 기반이면 M3=1 (예: AHA Cardiogenic Shock Scientific Statement 2022).

### 2.4 M4 세부 — Evidence/scale

다음 중 하나를 만족:
- 가이드라인에 **Class I recommendation** (또는 LOE A/1A) 명시 존재
- 프로토콜 내 **required_action ≥ 10개** (규모 proxy)

### 2.5 M5 세부 — Documented source

다음 중 하나 확보:
- DOI (peer-reviewed journal)
- 학회 공식 URL (`*.aha.org`, `*.nice.org.uk` 등)
- ISBN (학회 manual book)

### 2.6 M6 세부 — Conditional richness

시나리오 derivation 엔진(patient_generator.py의 4-axis)이 **≥ 10개 유의미한 시나리오**를 생성할 수 있는 최소 조건.

선형 회귀 (25 CPG 기준, Pearson r=0.595, p=0.0017):
```
scenarios_per_CPG ≈ 1.51 × nodes + 18.17
```
→ 시나리오 10개 이상 생성 위해 노드 ≥ 7개 권장.

---

## 3. 총점 및 Cutoff

- **총점**: M1 + M2 + M3 + M4 + M5 + M6 ∈ {0, 1, ..., 6}
- **Tier-valid cutoff**: **총점 ≥ 4** → 벤치마크 포함 후보
- **Priority tier (6점)**: 모든 지표 만족, v7 1차 확장 우선순위
- **Exclusion (≤3점)**: 학회 발행/evidence/richness 중 2개 이상 미달 → 제외

### 3.1 최소 공통 기준

**M3 ∧ M4 ∧ M5** (기존 25 CPG의 96% 만족) — Tier-1 학회 발행 + 증거/규모 + 출처 문서화.

**권장 사용 기준**:
- 논문 abstract: "M3 ∧ M4 ∧ M5"로 최소 선정 기준 명시
- Selection score ≥ 4 로 최종 후보 선별
- 점수 6점 후보를 Phase 1 확장 우선순위로

---

## 4. 채점 가능성 — Pre-screening vs Post-YAML

**중요**: 6개 지표는 **측정 시점**에 따라 2가지 모드로 나뉜다.

### 4.1 측정 모드 A: Pre-screening (guideline text만 있음)

CPG YAML이 아직 없는 **후보 스크리닝** 단계. 이 시점에는 M1/M2/M6을 원본 문서에서 직접 측정하기 어려우므로 **LLM-assisted 추정**을 쓴다.

| 지표 | Pre-screening 측정 | 자동화 가능도 |
|---|---|---|
| M1 | LLM에게 "deadline ≤ 60min mandatory action 수" 질문 (temperature=0, versioned prompt) | **LLM 추정** |
| M2 | LLM에게 "ordered action pair 수" 질문 | **LLM 추정** |
| M3 | 발행기관명을 **Tier-1 대표 학회 리스트 + M3a/b/c composite check** 룰로 판정 | **코드 100% 자동** |
| M4 | LLM에게 "Class I recommendation 수 + required action 수" 질문 | **LLM 추정** (Class I 문자열 grep은 가능) |
| M5 | URL/DOI/ISBN 존재 여부 (regex + 학회 공식 URL pattern check) | **코드 100% 자동** |
| M6 | LLM에게 "예상 노드 수" 질문 (복잡도 추정) | **LLM 추정** |

→ Pre-screening score는 **추정치**. 확정은 Mode B에서 수행.

### 4.2 측정 모드 B: Post-YAML (CPG graph 생성 후)

Automation pipeline이 YAML을 생성하고 clinician 검수까지 마친 시점. 이때는 **CPG YAML의 필드를 순회하여 코드로 100% 자동 채점**.

| 지표 | Post-YAML 자동 측정 코드 |
|---|---|
| M1 | `sum(1 for node in yaml['nodes'] for a in node.mandatory_actions if a.deadline_minutes <= 60) >= 3` |
| M2 | `len(yaml.get('before_constraints', [])) >= 1` |
| M3 | `yaml.metadata.source_society in TIER1_SOCIETY_SET` OR composite M3a/b/c pass |
| M4 | `any(n.recommendation_class == 'I' for n in yaml.nodes) or total_required_actions >= 10` |
| M5 | `re.match(DOI_REGEX, yaml.metadata.source_url) or re.match(ISBN_REGEX, yaml.metadata.source_isbn)` |
| M6 | `len(yaml.before_constraints) + len(yaml.within_constraints) >= 8 or len(yaml.nodes) >= 7` |

→ **Post-YAML score가 공식 score**. 논문에 이 값만 등재.

### 4.3 재현 절차 (Mode B, 공식 채점)

```python
# scripts/score_cpg.py
def score_cpg(yaml_path: str) -> dict:
    """Post-YAML automatic scoring using M1~M6 rubric."""
    g = yaml.safe_load(open(yaml_path))
    scores = {
        'M1': int(count_short_deadline_actions(g) >= 3),
        'M2': int(len(g.get('before_constraints', [])) >= 1),
        'M3': int(is_tier1_society(g['metadata']['source_society'])),
        'M4': int(has_class_i(g) or count_required_actions(g) >= 10),
        'M5': int(has_doi_or_url_or_isbn(g['metadata'])),
        'M6': int(
            (len(g.get('before_constraints', [])) + len(g.get('within_constraints', []))) >= 8
            or len(g['nodes']) >= 7
        ),
    }
    scores['TOTAL'] = sum(scores.values())
    scores['TIER_VALID'] = scores['TOTAL'] >= 4
    return scores
```

이 함수를 기존 25 CPG와 v7 확장 CPG 전부에 적용해 `docs/cpg_expansion_v7/scores.json`으로 dump → 논문 Appendix에 그대로 포함.

---

## 5. 기존 25 CPG의 rubric 적용 결과

### Score distribution

| Score | Count | Percent |
|---|---|---|
| 6 | ~18 | ~72% |
| 5 | ~5 | ~20% |
| 4 | ~1 | ~4% |
| 3 | ~1 (universal_clinical_safety: M3=0) | ~4% |
| ≤2 | 0 | 0% |

기존 25 CPG는 전부 ≥3점, 24개는 ≥4점. `universal_clinical_safety`만 "universal/추상적 safety principles"이라 M3 학회 발행 요건을 엄밀히 만족하지 않음 (이것은 논문에 "reference category"로 별도 명시 가능).

---

## 6. 논문 서술 (Appendix 제안 문구)

> "**Guideline Selection Criteria**: We define a 6-dimensional measurable rubric (M1-M6) over clinical practice guidelines: time-sensitivity (M1, ≥3 mandatory actions with deadline ≤60 min), sequential dependency (M2, ≥1 before-constraint), Tier-1 society issuance (M3, list in Appendix Table X), evidence/scale (M4, Class I recommendation or ≥10 required actions), documented source (M5, DOI/URL/ISBN verifiable), and conditional richness (M6, ≥8 (before+within) constraints or ≥7 nodes). A guideline is included if score ≥ 4. The core 25 CPGs in CGA-Bench v6 satisfy score ≥ 3 (24/25 satisfy ≥ 4), with the Universal Clinical Safety pseudo-graph explicitly marked as a reference category. Expansion candidates for v7 are scored identically; see Appendix Table Y for the full 99-candidate rubric matrix."

---

## 7. 변경 이력

- **v1 (2026-04-22)**: 최초 명문화. 기존 25 CPG 역추적 + 99 후보 재점수화와 함께 수립.

## 8. 관련 문서

- `docs/cpg_expansion_v7/02_candidate_rescoring_99.md` — 99개 후보 M1~M6 전수 점수화
- `docs/cpg_expansion_v7/03_automation_pipeline_requirements.md` — 자동화 파이프라인 요구사항
- `docs/attack_gap_exp_exp/260422_25cpg_706_timing_defense.md` — 공격 3종 방어 배경

## 9. 관련 코드

- `cpg_model/graphs/*.yaml` — 기존 25 CPG graph (M1, M2, M6 직접 측정 가능)
- `evidence_pack/guideline_cards.yaml` — guideline 메타데이터 (M3, M4, M5 추출)
- `semantic_layer/cpg_parser.py` — guideline document → structured extraction (M1-M6 자동 추출에 사용)
- `scripts/ci/validate_cpg_schema.py` — schema validation
