# CGA-Bench 실험 확장을 위한 벤치마크 데이터셋 조사 보고서

**CGA-Bench는 3개 통합 티어에 걸쳐 25개 이상의 신규 데이터셋을 활용할 수 있다.** NeurIPS 수준의 확장성 검증에 가장 적합한 후보는 CliBench, MedR-Bench, AMEGA, MedGUIDE, MIMIC-CDM으로, 각각 구조화된 임상 행동 출력, ground-truth 어노테이션, CPG 그래프 형식화와의 직접적 호환성을 제공한다. 아래는 통합 유형별로 정리한 종합 현황과 CGA-Bench의 DualTrack 채점 및 5종 위반 분류 체계와의 적합성 평가이다.

---

## Tier 1: 어댑터 통합이 즉시 가능한 신규 에이전트 벤치마크

기존의 AgentClinic, MedAgentBench, MedChain과 별개이며, CGA-Bench 아키텍처와의 호환성이 가장 높은 벤치마크들이다. 모두 CPG 위반 추출에 적합한 구조화된 임상 행동을 출력한다.

### CliBench (Ma et al., ICLR 2025; arXiv:2406.09923)

진단, 치료 시술, 검사 처방, 약물 처방의 4가지 태스크에 걸쳐 LLM의 임상 의사결정을 평가한다. **수천 건의 실제 MIMIC-IV 케이스**를 ICD-10, LOINC, RxNorm 온톨로지로 코딩하여 사용한다. 구조화된 출력 형식이 CGA-Bench의 semantic layer에 직접 매핑된다. **OMISSION**(누락된 권고 시술/약물), **COMMISSION**(불필요한 처방), **DEVIATION**(잘못된 약물/용량) 위반 감지에 강하나, single-turn 평가 방식으로 인해 TIMING과 SEQUENCE 분석에는 한계가 있다. PhysioNet 크레덴셜 필요; 코드는 GitHub에서 오픈소스로 제공된다.

### MedR-Bench (Nature Communications, 2025)

13개 신체 시스템에 걸쳐 **1,453개의 구조화된 환자 케이스**를 제공하며, 검사 권고 → 진단 의사결정 → 치료 계획의 3단계 평가 파이프라인을 갖추고 있다. LLM 기반 환자 에이전트를 통한 대화형 평가를 지원한다. 반복적 검사 처방 단계가 SEQUENCE 분석을 직접 지원하며, 치료 계획 출력으로 OMISSION과 COMMISSION 감지가 가능하다. Ground truth는 출판된 임상 케이스 리포트의 참조 추론 체인에서 도출된다. 공개 접근 가능.

### CSEDB (Wang et al., npj Digital Medicine, 2025)

**26개 임상 과에 걸쳐 2,069개 개방형 문항**을 포함하며, 안전성(17개 지표)과 효과성(13개 지표)으로 나뉜 30개 평가 메트릭을 제공한다. 안전성 지표는 **가이드라인 준수, 약물 금기, 약물 상호작용, 용량 오류**를 명시적으로 평가하며, CGA-Bench의 위반 유형과 거의 완벽하게 매핑된다. **32명의 전문의**가 위험 가중 결과 측정치로 검증했다. 응급 및 ICU 관련 분야를 포함한다. 이메일 신청으로 접근 가능; GitHub 저장소 존재. 참고: 주로 중국 의료 맥락에 맞게 설계되었으나 영문 모델도 평가함.

### MedConsultBench (Qiao et al., Meituan, arXiv:2601.12661, 2026년 1월)

Atomic Information Unit(AIU) 단위의 서브턴 수준 추적을 통해 전체 진료 주기를 평가한다. 병력 청취 → 진단 → 치료 계획 → 후속 관리를 **22개 세분화 지표**로 측정하며, 약물 처방 호환성 평가를 포함한다. AIU 분해 방식은 후보 중 **가장 정밀한 TIMING 위반 감지**를 가능하게 한다. 약물 안전성 비평 컴포넌트가 COMMISSION과 DEVIATION에 직접 매핑된다. CGA-Bench의 프로세스 인식 평가와 **아키텍처적으로 가장 잘 맞는** 후보이다.

### AMEGA (Fast et al., npj Digital Medicine, 2024)

**LLM의 가이드라인 준수도 평가를 명시적 목적으로 설계**되었다. 13개 전문과에 걸쳐 20개 진단 시나리오, **135개 질문, 1,337개 가중 채점 요소**를 임상 가이드라인 권고에 대해 평가한다. 개방형 평가(MCQ 아님)에 LLM-as-judge 채점 방식을 사용한다. 치료 전략, 진단 절차, 감별 진단을 포함한다. GitHub에서 완전 오픈소스(DATEXIS/AMEGA-benchmark). 5가지 위반 유형 모두에 직접 적용 가능하나 **24케이스로 제한**되어, 대규모 테스트보다는 방법론 검증에 적합하다.

### MedGUIDE (Li et al., 2025, NeurIPS 워크숍)

17개 암 종에 걸쳐 **55개 NCCN 의사결정 트리에서 7,747개 MCQ**를 구축하여 단계별 가이드라인 따르기를 테스트한다. 각 질문은 구조화된 임상 경로에 따른 올바른 다음 단계를 묻는다. 종양학 중심으로 급성 치료와는 다르지만, 현존하는 **최대 규모의 구조화된 가이드라인 준수 테스트 데이터셋**이다. SEQUENCE(올바른 다음 단계), DEVIATION(잘못된 경로), OMISSION(누락된 단계) 테스트가 가능하다. 심사 중; 코드 공개 예정.

### 종합 비교표

| 벤치마크 | 규모 | 구조화된 행동 | 에이전트 기반 | 위반 커버리지 | 공개 접근 | CPG 적합도 |
|-----------|------|---------------|---------------|---------------|-----------|------------|
| **CliBench** | ~수천건 | ✅ ICD/LOINC/RxNorm | ❌ single-turn | OMI, COM, DEV | PhysioNet | ★★★★ |
| **MedR-Bench** | 1,453 | ✅ 3단계 파이프라인 | ✅ 환자 에이전트 | OMI, COM, SEQ | 공개 | ★★★★ |
| **CSEDB** | 2,069 | ✅ 안전성 지표 | 부분적 | OMI, COM, DEV | 신청제 | ★★★★ |
| **MedConsultBench** | 다수 케이스 | ✅ AIU + 처방 | ✅ 전주기 | 5가지 모두 | 공개 | ★★★★★ |
| **AMEGA** | 135문항(24케이스) | ✅ 개방형 | ❌ | OMI, COM, DEV | 오픈소스 | ★★★★ |
| **MedGUIDE** | 7,747 | ✅ 경로 단계 | ❌ MCQ | SEQ, DEV, OMI | 공개 예정 | ★★★★ |

---

## Tier 1b: 보완 가치가 높은 벤치마크

**CRAFT-MD** (Johri et al., Nature Medicine, 2025; AAAI Best Paper) — 의사AI + 환자AI 멀티에이전트 대화 프레임워크로 140개 피부과 케이스를 평가한다. 병력 청취 완전성 평가가 정보 수집 단계의 OMISSION에 매핑된다. GitHub 오픈소스(rajpurkarlab/craft-md). CPG 적합도는 보통 — 주로 진단 중심이며 치료 중심이 아님.

**HealthBench** (OpenAI, 2025) — 262명의 의사가 26개 전문과에 걸쳐 검증한 **~5,000개 멀티턴 대화**를 제공한다. 루브릭 기반 평가가 치료 계획을 포함한 12개 임상 역량을 커버한다. 공개 접근 가능. 자유 텍스트 출력으로 구조화된 행동 추출 충실도는 낮으나, 규모와 의사 검증은 매력적이다.

**FHIR-AgentBench** (Lee et al., 2025; arXiv:2509.19319) — MIMIC-IV 데이터 기반 **FHIR API를 통한 2,931개 임상 질문**에서 LLM 에이전트를 테스트한다. 주로 정보 검색 벤치마크이나, FHIR 호환 아키텍처가 CGA-Bench 에이전트의 환자 기록 접근 상호운용성 레이어를 제공한다. 공개 배포.

**PsychiatryBench** (arXiv:2509.09711, 2025) — 치료 계획, 관리 계획, 순차적 케이스 분석을 포함한 11개 태스크 유형에 걸쳐 **5,188개 전문가 어노테이션 항목**을 제공한다. 정신과 가이드라인 내 CPG 준수 검사에 매핑 가능하다.

---

## Tier 2: 기존 도메인 시나리오 확장을 위한 도메인 특화 데이터셋

CGA-Bench의 기존 6개 임상 도메인에서 환자 다양성과 엣지 케이스 커버리지를 확장하는 데이터셋이다.

### 패혈증(Sepsis) 도메인 확장

**PhysioNet/CinC Challenge 2019** 데이터셋은 **40,336명의 ICU 환자**에 대해 40개 임상 변수의 시간별 시계열, Sepsis-3 라벨(발병 시점 포함), 3개 병원 시스템 데이터를 제공한다. 완전 공개. 치료 데이터가 없어 직접적 CPG 준수 테스트에는 한계가 있으나, 시간적 활력징후 궤적으로 인식 타이밍 평가를 지원한다.

**MIMIC-Sepsis** (arXiv:2510.24500, 2025)는 MIMIC-IV에서 치료 중재(혈관수축제, 수액, 항생제, 인공호흡)를 패혈증 발병 기준으로 정렬한 **35,239명의 패혈증 환자** 큐레이트 벤치마크를 제공한다. **SSC 2021 가이드라인 준수 테스트에 최적의 단일 데이터셋**으로, 항생제가 1시간 이내에 투여되었는지, 혈액배양이 항생제 투여에 선행했는지 직접 평가할 수 있다. PhysioNet 접근 필요.

**ICU-Sepsis** (Choudhary et al., RL Conference 2024)는 패혈증 치료를 716개 상태와 25개 행동(5×5 혈관수축제/수액 용량 그리드)의 **OpenAI Gym 호환 MDP**로 패키징했다. ~17,000건의 MIMIC-III 패혈증 입원에서 구축. Gym-like 인터페이스가 CGA-Bench의 scenario_engine 아키텍처와 직접 유사하여 어댑터 개발이 간단하다.

**Health Gym 합성 패혈증 데이터셋** (PhysioNet)은 혈관수축제 용량, IV 수액 용량, 결과를 포함한 48시간 시계열의 **2,164명 합성 환자**를 제공한다. **크레덴셜 없이 완전 공개**. 빠른 프로토타이핑에 유용하다.

### 흉통·뇌졸중: GWTG 레지스트리

AHA Precision Medicine Platform의 **GWTG-Stroke**는 미국 2,800개 이상 병원의 **780만건 이상 기록**을 1,233개 변수로 보유하며, door-to-needle 시간, tPA 투여, 혈전제거술 타이밍, 명시적 가이드라인 준수 지표를 포함한다. 허혈성(69.2%), ICH(11.5%), SAH(3.9%), TIA(15.3%)를 커버한다. 초기 탐색을 위한 **1,000건 샘플 합성 버전이 공개**되어 있으며, 전체 접근은 AHA 승인 논문 제안서가 필요하다.

**GWTG-Heart Failure** (~240만건)과 **GWTG-CAD** (~50만건)도 동일 모델을 따르며, 가이드라인 기반 약물치료 준수, EF 표현형(HFrEF, HFmrEF, HFpEF), 퇴원 약물 준수를 명시적으로 추적한다. 해당 도메인의 **CPG 준수 평가에 대한 골드 스탠다드 레지스트리**이다.

### MIMIC-IV 기반 엣지 케이스 추출

MIMIC-IV v3.1(2024년 10월; ~300,000 입원, ~75,000 ICU 입원)은 ICD 하위 코드 + 검사값 + 임상 노트 조합으로 6개 도메인 전반의 엣지 케이스 식별을 지원한다:

- **정상혈당 DKA(Euglycemic DKA)**: DKA 진단 + 혈당 <250 mg/dL, 특히 SGLT2 억제제 사용 시
- **트로포닌 음성 ACS**: ACS 진단 + 정상 연속 트로포닌 궤적
- **간신증후군(Hepatorenal syndrome)**: 간경변 ICD 코드 + AKI 병기(KDIGO 기준은 MIMIC-IV에서 검증된 오픈소스 파이프라인 **pyAKI**로 구현 가능)
- **횡문근융해 유발 AKI**: CK 수치 상승 + AKI 코드
- **후순환 뇌졸중**: 특정 ICD-10 코드(I63.5x 시리즈)
- **HFpEF**: ICD 코드 I50.31-33 + 심초음파 노트
- **DKA-AKI 중첩**: Frontiers in Public Health(2023) 코호트에서 이미 **1,322명** 특성 분석 완료

기 출판된 MIMIC-IV 코호트 연구들이 즉시 사용 가능한 추출 파이프라인을 제공한다: 패혈증 연관 AKI 환자 **12,842명**, 급성 허혈성 뇌졸중 ICU 입원 **3,489건**, DKA 환자 **2,382명**, 다수의 심부전 코호트.

### 외부 검증을 위한 추가 공개 ICU 데이터베이스

**eICU Collaborative Research Database** (PhysioNet)는 미국 208개 병원의 **200,000건 이상 ICU 입원**을 치료 계획, 약물, APACHE 점수와 함께 제공하며, 다기관 일반화 테스트에 이상적이다. **AmsterdamUMCdb** (~23,000건), **HiRID** (~33,000건), **SICdb**는 교차 인구 검증을 위한 유럽 ICU 데이터를 제공한다. 모두 PhysioNet 크레덴셜 필요.

---

## Tier 3: 인프라 확장을 위한 EHR 벤치마크 및 NLP 데이터셋

### MIMIC-CDM: 특별 주목

**MIMIC-CDM** (Hager et al., Nature Medicine, 2024)은 4가지 복부 병리에 대한 **2,400건의 실제 환자 케이스**를 반복적 정보 수집(HPI → 신체검사 → 검사 → 영상 → 진단 → 치료)과 함께 제공한다. **진단 및 치료 가이드라인 준수를 명시적으로 평가**하며 HuggingFace 리더보드를 포함한다. 4개 도메인(충수염, 췌장염, 담낭염, 게실염)은 CGA-Bench의 6개 도메인과 겹치지 않으나, 순차적 의사결정 + 가이드라인 준수 확인 평가 프레임워크 아키텍처는 도메인 특화 어댑터 구축 템플릿으로 **직접 전용 가능**하다.

### ArchEHR-QA (기존 어댑터 스텁 상세)

ArchEHR-QA(Soni & Demner-Fushman, BioNLP at ACL 2025)는 MIMIC-III/IV ICU 및 응급실 임상 노트에서 **134건의 전문가 어노테이션 케이스**를 제공한다. 2026년 버전은 질문 해석, 근거 식별, 답변 생성, 근거 정렬의 4가지 서브태스크로 확장된다. 소규모 데이터셋이며 환자 QA 중심으로 치료 결정 중심이 아니다. 근거 식별 서브태스크가 CGA-Bench 에이전트의 올바른 임상 근거 검색 검증에 활용 가능하나, **직접적 CPG 준수 적용성은 낮다**. PhysioNet 접근 필요.

### 치료 결정 관련 n2c2 공유 태스크

**2022 n2c2 Track 1 (CMED)**이 가장 관련성이 높다: 500개 임상 노트에 걸쳐 **9,013개 어노테이션 약물 언급**을 5차원 분류 — Action(시작/중단/증량/감량), Negation, Temporality(과거/현재/미래), Certainty, Actor — 로 제공한다. Action과 Temporality 차원이 CGA-Bench의 TIMING 및 SEQUENCE 위반 감지에 직접 매핑된다. DBMI Data Portal에서 DUA로 이용 가능.

**2018 n2c2 Track 2** (ADE 및 약물 추출)는 약물-ADE 관계가 있는 **505개 퇴원 요약**을 제공 — COMMISSION 감지에 직접 관련. **2010 i2b2 Relations challenge**는 871개 노트에서 치료-문제 관계("치료가 문제를 개선/악화/유발")를 어노테이션. **2012 i2b2 Temporal Relations** 태스크(310개 노트)는 SEQUENCE 위반을 위한 이벤트 순서 평가를 지원한다.

### CPGPrompt: 방법론적 보완

**CPGPrompt** (arXiv:2601.03475, 2025)는 대규모 데이터셋을 제공하지 않으나, **서술형 임상 가이드라인을 구조화된 가이던스 트리로 변환하여 LLM 챗봇으로 실행하는 프레임워크**를 제안한다. 두통(128 비네트), 요통(99), 전립선암(96)으로 평가. 가이던스 트리 형식화 접근법이 CGA-Bench의 CPG 엔진에서 신규 가이드라인을 계산 가능한 그래프로 변환하는 데 직접 활용 가능하다.

---

## CGA-Bench 평가 아키텍처와의 매핑

CGA-Bench의 각 컴포넌트는 데이터셋에 특정 특성을 요구한다:

**CPG 엔진 호환성**(가이드라인 그래프 형식화)은 명시적 가이드라인 참조가 있는 데이터셋에서 가장 강하다: GWTG 레지스트리는 특정 AHA/ACC 품질 지표를 추적하고, MIMIC-Sepsis는 SSC 번들 타이밍 확인을 가능하게 하며, MedGUIDE는 사전 형식화된 NCCN 의사결정 트리를 제공하고, AMEGA는 출판된 가이드라인 루브릭에 대해 채점한다. CPGPrompt 방법론은 모든 데이터셋에 대해 신규 가이드라인을 변환하는 확장 가능한 접근법을 제공한다.

**위반 추출기 커버리지**는 데이터셋별로 상이하다:

- **TIMING 위반**: 시간 데이터 필요 — MIMIC-Sepsis(패혈증 발병 대비 중재 시점), ICU-Sepsis(순차적 MDP 행동), n2c2 CMED(시간적 약물 분류)가 최적
- **SEQUENCE 위반**: 다단계 의사결정 궤적 필요 — MedConsultBench(AIU 추적), MedR-Bench(3단계 파이프라인), MIMIC-CDM(반복적 정보 수집)이 제공
- **OMISSION/COMMISSION 감지**: ground truth 대비 구조화된 행동 출력 필요 — CliBench(온톨로지 코딩 출력), CSEDB(안전성 지표), GWTG 레지스트리(품질 지표 준수)가 최적

**시나리오 엔진 호환성**(Gym-like 인터페이스)은 ICU-Sepsis(이미 Gym 호환), MedConsultBench(상태 추적 순차 상호작용), MedR-Bench(대화형 환자 에이전트)에 자연스럽게 맞는다. 대부분의 정적 벤치마크는 래퍼 개발이 필요하다.

**Safety Gate 통합**은 CSEDB(치명적 약물 상호작용 및 금기 약물을 포함한 17개 명시적 안전성 지표), MedConsultBench(약물 안전성 비평), n2c2 2018 Track 2(약물 부작용 관계)에 가장 직접적으로 매핑된다.

---

## NeurIPS 제출을 위한 전략적 권고

가장 강력한 확장성 입증은 3가지 통합 유형을 결합하는 것이다.

**1단계: 신규 외부 벤치마크 어댑터 2개 구축** — CliBench와 MedR-Bench가 구조화된 출력, 공개 접근성, 톱 베뉴 게재를 고려할 때 최적의 후보이다.

**2단계: 도메인 내 시나리오 커버리지 확장** — MIMIC-Sepsis를 활용하여 패혈증 도메인 확장(35,239명 환자로 SSC 2021 타이밍 번들 준수 테스트 가능), GWTG-Stroke 합성 데이터로 뇌졸중 도메인 초기 검증 수행.

**3단계: CPG 그래프 일반화 입증** — CPGPrompt 가이던스 트리 방법론을 적용하여 현재 6개 도메인 외 최소 1개 신규 임상 가이드라인을 형식화.

### 통계적 엄밀성

MIMIC-IV 생태계가 6개 도메인 전반에서 가장 큰 접근 가능한 환자 인구를 제공한다. MIMIC-IV(300K+ 입원), eICU(200K+ 입원, 외부 검증용), GWTG 레지스트리(수백만 건 기록)의 조합은 유의성 임계값을 충분히 초과하는 표본 크기를 보장한다. **pyAKI 오픈소스 파이프라인**은 이 모든 데이터베이스에서 표준화된 KDIGO 분류를 가능하게 한다.

### 핵심 차별화 포인트

강조할 가장 임팩트 있는 갭: **5가지 위반 유형을 통합적으로 평가하는 기존 벤치마크는 없다.** AMEGA와 MedGUIDE가 가이드라인 준수에 가장 근접하나 CGA-Bench의 통합 위반 분류 체계는 갖추고 있지 않다. CGA-Bench의 DualTrack 채점이 CliBench, MedR-Bench, MIMIC-Sepsis, 그리고 최소 1개 GWTG 레지스트리에 걸쳐 동작함을 입증하면, 고유하게 포괄적인 평가 프레임워크를 확립하게 되며 — 이것이 NeurIPS 논문에 필요한 확장성 스토리이다.

---

## 참고 문헌 (주요 출처)

- CliBench: https://clibench.github.io/ (arXiv:2406.09923)
- MedR-Bench: Nature Communications, 2025
- CSEDB: npj Digital Medicine, 2025 (arXiv:2507.23486)
- MedConsultBench: arXiv:2601.12661
- AMEGA: npj Digital Medicine, 2024 (GitHub: DATEXIS/AMEGA-benchmark)
- MedGUIDE: arXiv:2505.11613 (NeurIPS 2025 워크숍)
- CRAFT-MD: Nature Medicine, 2025; AAAI Best Paper
- MIMIC-CDM: Nature Medicine, 2024 (PhysioNet: mimic-iv-ext-cdm)
- MIMIC-Sepsis: arXiv:2510.24500
- ICU-Sepsis: GitHub: icu-sepsis/icu-sepsis
- PhysioNet/CinC 2019: physionet.org/content/challenge-2019
- GWTG-Stroke: AHA Journals (doi:10.1161/STROKEAHA.124.048174)
- eICU-CRD: physionet.org/content/eicu-crd/2.0
- CPGPrompt: arXiv:2601.03475
- pyAKI: PLOS One (doi:10.1371/journal.pone.0315325)
- n2c2 CMED 2022: PMC10529825
- ArchEHR-QA: physionet.org/content/archehr-qa-bionlp-task-2025
