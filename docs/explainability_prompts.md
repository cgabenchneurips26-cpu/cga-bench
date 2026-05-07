# CGA-Bench Explainability 구현 — Claude Code 프롬프트

**목표**: 벤치마크가 숫자뿐 아니라 "왜 이 점수인지"를 임상적으로 설명하는 기능 추가
**실행 순서**: Step A→B는 순차, C/D는 B 이후 병렬 가능

---

## Step A: Violation-Level Explanation 생성기

```
cga_bench에 각 위반(violation)에 대한 임상적 설명을 자동 생성하는 기능을 구현해라.

목표:
각 violation이 "무엇이 잘못됐고, 왜 중요하고, 가이드라인 근거가 뭔지"를 구조화된 JSON으로 출력.

1. 먼저 현재 violation 데이터 구조를 확인해라:
   - ViolationExtractor 또는 violation 관련 클래스가 어디에 있는지
   - 각 violation이 어떤 필드를 갖고 있는지 (type, action, timestamp 등)
   - CPG YAML에 source_quote, evidence_level, recommendation 같은 필드가 있는지 확인

2. ViolationExplainer 클래스를 구현해라 (eval_harness/explainability/violation_explainer.py):

   입력: Violation 객체 + CPG context
   출력: 다음 구조의 JSON

   {
     "violation_id": "v001",
     "type": "TIMING",
     "action": "start_vasopressor_vasopressin",
     "clinical_explanation": {
       "what_happened": "승압제(vasopressin) 투여가 권장 시간(60분) 대비 15분 지연되었습니다.",
       "clinical_significance": "패혈성 쇼크에서 승압제 지연은 시간당 사망률 증가와 연관됩니다.",
       "guideline_reference": "SSC 2021 Hour-1 Bundle",
       "source_quote": "CPG YAML에서 가져온 원문 근거",
       "severity": "MODERATE",
       "recommendation": "MAP < 65mmHg 지속 시 수액과 동시에 승압제를 시작하십시오."
     }
   }

3. 설명 생성 방식 — LLM이 아닌 템플릿 + CPG 매핑 기반:
   - 위반 유형별 설명 템플릿 (TIMING, DEVIATION, OMISSION, SEQUENCE, SAFETY)
   - CPG YAML의 source_quote/evidence 필드를 explanation에 자동 연결
   - severity 판정: CPG의 evidence_level + 행동의 mandatory/optional 여부로 결정
   - 템플릿에 변수만 채우는 방식 (재현성 보장, LLM 의존 없음)

4. severity 등급 체계:
   - CRITICAL: mandatory action의 omission 또는 safety violation
   - HIGH: mandatory action의 timing violation (>50% 초과)
   - MODERATE: mandatory action의 timing violation (<50% 초과) 또는 sequence violation
   - LOW: optional action 관련 또는 임상적으로 관련 있는 deviation
   - INFORMATIONAL: 임상적으로 정당하지만 CPG에 명시되지 않은 행동

5. 8개 시나리오의 기존 3회 반복 결과에 대해 explanation을 생성하고,
   evidence_pack/explanations/ 에 시나리오별 JSON 저장.
   잘 생성되는지 septic_shock_basic 1건을 예시로 전체 출력 보여줘.
```

---

## Step B: Episode-Level Narrative + Timeline 생성기

```
cga_bench에 에피소드 전체를 임상 서사(narrative)로 변환하는 기능을 구현해라.

목표:
의료진이 "이 AI가 환자를 어떻게 진료했는지"를 한눈에 볼 수 있는 타임라인 + 서사 생성.

1. EpisodeNarrativeGenerator 클래스를 구현해라 (eval_harness/explainability/narrative_generator.py):

   입력: EpisodeLog + ViolationReport + CPG context
   출력:

   {
     "scenario": "septic_shock_basic",
     "patient_summary": "65세 남성, 발열·저혈압으로 응급실 내원. MAP 58mmHg, HR 112.",
     "timeline": [
       {
         "time_offset_min": 0,
         "actions": ["assess_infection_source", "assess_organ_dysfunction"],
         "status": "COMPLIANT",
         "note": "감염원 및 장기부전 평가 — 가이드라인 준수"
       },
       {
         "time_offset_min": 5,
         "actions": ["order_lab_lactate", "order_lab_blood_culture"],
         "status": "COMPLIANT",
         "note": "Hour-1 Bundle: 젖산 및 혈액배양 오더"
       },
       {
         "time_offset_min": 75,
         "actions": ["start_vasopressor_vasopressin"],
         "status": "TIMING_VIOLATION",
         "note": "⚠️ 승압제 추가 — 권장 시간(60분) 15분 초과",
         "violation_ref": "v001"
       }
     ],
     "summary": {
       "total_actions": 15,
       "compliant": 13,
       "violations": 2,
       "compliance": "92.4%",
       "primary_issue": "승압제 투여 타이밍 지연"
     },
     "clinical_assessment": "필수 행동 전부 수행, 순서 정확. 승압제 타이밍만 지연. Hour-1 Bundle 대부분 준수."
   }

2. 구현 세부사항:
   - EpisodeLog의 action sequence를 시간순으로 정렬
   - 각 action을 CPG의 mandatory/optional/deviation으로 분류
   - Step A의 ViolationExplainer를 호출해서 violation 설명을 timeline에 포함
   - patient_summary는 시나리오 config의 환자 정보에서 자동 생성
   - clinical_assessment는 위반 패턴에 따른 템플릿 기반 요약 (LLM 불필요)

3. 8개 시나리오에 대해 narrative를 생성하고 evidence_pack/narratives/ 에 저장.

4. 추가로 마크다운 형식의 사람이 읽을 수 있는 버전도 생성:
   evidence_pack/narratives/septic_shock_basic_narrative.md 같은 형태로.
   타임라인에 ✅/⚠️/❌ 이모지를 사용해서 가독성을 높여줘.
```

---

## Step C: Deviation Severity 차등 반영 (Step B 이후)

```
cga_bench의 deviation scoring을 severity 기반으로 차등화해라.

현재 문제:
- 모든 deviation이 동일한 weight(0.3)로 처벌됨
- "AKI에서 troponin 오더" (관련은 있지만 비표준)와 "AKI에서 thrombolytic 투여" (완전 무관, 위험)가 같은 점수

목표:
deviation의 임상적 심각도에 따라 가중치를 차등 적용.

1. Step A에서 만든 severity 등급을 scoring에 연결해라:

   deviation_weight_map = {
     "CRITICAL": 1.0,      # 위험한 deviation (완전 무관한 치료)
     "HIGH": 0.7,
     "MODERATE": 0.4,
     "LOW": 0.15,           # 임상적으로 관련 있는 추가 검사
     "INFORMATIONAL": 0.05  # 거의 무시
   }

2. severity 판정 기준:
   - CPG의 contraindicated actions에 해당하면 → CRITICAL
   - CPG 도메인과 완전히 무관한 행동 → HIGH
   - CPG 도메인 관련이지만 허용 목록에 없는 행동 → MODERATE
   - CPG 도메인 관련이고 임상적으로 정당한 추가 검사 → LOW
   - 반복 행동 (이미 수행된 행동의 재주문) → INFORMATIONAL

3. "도메인 관련성" 판정 방법:
   - ActionNormalizer의 fuzzy match score를 활용
   - best_match_score > 0.7이면 "관련 있는 deviation" → LOW
   - best_match_score > 0.4이면 "부분적 관련" → MODERATE
   - best_match_score < 0.4이면 "무관" → HIGH
   - CPG contraindicated list에 있으면 score 무관하게 → CRITICAL

4. 구현 위치: C1 계산 로직에서 deviation_count 대신 weighted_deviation_score 사용
   - C1 = 1 - weighted_deviation_score / total_actions
   - weighted_deviation_score = sum(weight_i for each deviation_i)

5. 전/후 비교:
   - 8개 시나리오에 대해 uniform weight vs severity-weighted 점수 비교 테이블 생성
   - 가장 큰 차이가 나는 시나리오와 그 이유를 설명
   - aki_stage1과 contrast_aki에서 가장 큰 변화가 예상됨 (임상적으로 관련 있는 deviation이 많으므로)

6. 이것을 ablation의 하나로도 사용:
   - evidence_pack/ablation/에 severity_weighted_results.json 추가
   - "uniform vs severity-weighted" 비교 LaTeX 테이블 생성
```

---

## Step D: Comparative Radar Chart 생성기 (Step B 이후, C와 병렬)

```
cga_bench의 시나리오별/에이전트별 sub-score를 radar chart로 시각화하는 기능을 구현해라.

1. eval_harness/explainability/radar_chart.py 에 구현:

   입력: 시나리오별 C1~C5 점수 딕셔너리
   출력: matplotlib 기반 radar chart PNG + PDF

2. 차트 유형 3가지:

   A) 단일 시나리오 radar:
      - 5축: C1(Path Selection), C2(Completeness), C3(Sequence), C4(Timing), C5(Safety)
      - 예: septic_shock_basic의 C1=98.6, C2=100, C3=100, C4=73.3, C5=100

   B) 시나리오 비교 radar (오버레이):
      - 같은 차트에 2-3개 시나리오를 겹쳐서 표시
      - 예: sepsis vs DKA vs AKI → 어떤 도메인에서 어떤 sub-score가 약한지 한눈에

   C) 에이전트 비교 radar (future-proof):
      - 같은 시나리오에 대해 RAG vs Oracle vs (future) Planner 비교
      - 현재는 RAG만 있으니 B 유형에 집중하되, 인터페이스는 에이전트 비교도 지원하게

3. 스타일:
   - 학술 논문용: 흑백으로도 구분 가능하게 (선 스타일 + 마커로 구분)
   - 색상은 colorblind-friendly palette
   - 폰트: 논문 본문과 동일 (Times New Roman 또는 Computer Modern)
   - 범례, 축 라벨 포함

4. 생성할 차트 목록:
   - 8개 시나리오 각각의 individual radar (8개)
   - 도메인 그룹 비교: sepsis류 vs cardiac vs metabolic vs renal (1개)
   - 전체 8개 시나리오 오버레이 (1개, 복잡하지만 overview용)

5. 저장: evidence_pack/figures/radar_*.png + .pdf
   LaTeX에서 바로 include할 수 있게 PDF도 생성.

6. 추가: 위 radar chart를 생성하는 CLI 명령어도 만들어줘.
   python -m cga_bench.report --radar --scenarios all --output evidence_pack/figures/
```

---

## 실행 순서 요약

```
Step A (Violation Explanation)
  ↓
Step B (Episode Narrative + Timeline)
  ↓
  ├── Step C (Deviation Severity — scoring 개선)
  └── Step D (Radar Chart — 시각화)
```

## 완료 체크리스트

```
□ Step A: ViolationExplainer 구현, 8시나리오 explanation JSON 생성
□ Step B: EpisodeNarrativeGenerator 구현, 8시나리오 narrative JSON + MD 생성
□ Step C: Severity-weighted deviation scoring, uniform vs weighted 비교 테이블
□ Step D: Radar chart 10장 (individual 8 + group 1 + overview 1), PNG + PDF
```