# CGA-Bench 정상 동작 검증 프레임워크 구현 전략

## 실행 요약
본 문서는 CGA-Bench가 “정상 동작”하는지(규칙 기반 제약 산출 → 위반 감지 → 위해 기반 점수화 → 공정성/예산/격리 보장) **증거 중심으로 검증**하기 위한 실행 가능한(코드·테스트·데이터·스크립트 단위의) 프레임워크를 제안합니다. 핵심 산출물은 (1) **테스트 피라미드(단위/통합/E2E)**, (2) 임상 가이드라인 근거에 기반한 **A/B 골든 테스트 세트**, (3) 외부/대규모 데이터로 “확장성”을 확인하는 **스트레스·성능·내보내기(XES/OCEL) 회귀 테스트**, (4) 스코어링과 에이전트의 정보 누출을 실험적으로 낮추는 **격리·안티-리키지 기법(컨테이너/의존성 분리/카나리 토큰)**, (5) **정량 합격 기준(기능·안전·강건성·공정성·확장성)**입니다.  
특히 외부 데이터셋(Synthea, MIMICEL, AgentClinic, MedAgentBench, MedChain)을 “성능 비교용”이 아니라 **파이프라인의 강건성·스케일·도메인 불일치 처리**를 검증하는 입력으로 구조화합니다. Synthea는 공개·합성 EHR(FHIR 포함) 생성기로 대량 픽스처 생산에 적합하고, MIMICEL은 XES 포함 대규모 이벤트 로그로 내보내기/처리량 스트레스에 적합합니다. citeturn1search0turn1search3turn5view0turn1search5turn1search14  
재현성 측면에서는 entity["organization","NeurIPS","ml conference"] 체크리스트·코드 제출 정책·D&B 트랙 데이터 호스팅 가이드(기계 판독 메타데이터 포함)를 준수하는 실행 스크립트/고정 버전/시드 관리까지 포함합니다. citeturn4search0turn4search13turn4search1turn4search2

## 목표와 명세
### 검증 목표 정의
“정상 동작”을 다음 5개 목표로 분해하고, 각 목표마다 **입력/출력/합격 기준**을 고정합니다.

1) **기능 정확성(Functional Correctness)**  
CPG 그래프/환자 상태/행동 로그가 주어질 때, 필수·금기·허용·마감·순서 제약이 일관되게 산출되고(엔진), 위반이 정확히 분류되며(추출기), 위해 기반 점수(및 Safety Gate)가 의도대로 계산되는지(스코어러)를 검증합니다.

2) **안전 민감도(Safety Sensitivity)**  
임상적으로 위험한 금기/지연/순서 위반이 점수에 더 크게 반영되며, 심각 위반 시 Safety Gate가 확실히 작동하는지 확인합니다. 예: 흉통에서 도착 후 10분 내 ECG 확보/판독 권고(시간 민감) citeturn2search1turn2search9, 패혈증에서 항균제 “이상적으로 1시간 이내”(시간 민감) citeturn2search0turn2search8

3) **강건성(Robustness)**  
외부 벤치마크의 표기·단위·타임스탬프·행동 동의어 차이에도 정규화/파싱이 망가지지 않되, 과잉 정규화로 위험 행동이 누락되지 않도록(정밀도 유지) 확인합니다.

4) **공정성(Fairness)과 예산 일치(Budget Matching)**  
에이전트별 토큰/도구 호출 예산을 맞춘 상태에서 평가 루프가 동일 조건을 강제하는지, 초과/누락 시 실패로 처리하는지 검증합니다(실험 하네스 레벨).

5) **확장성(Scalability)·성능 회귀(Performance Regression)**  
대규모 이벤트 로그에서 처리량/메모리/내보내기 포맷(XES/OCEL) 변환이 안정적으로 수행되는지 검사합니다. XES는 “대용량 이벤트 데이터의 운송/저장/교환”을 위한 표준으로 명시되어 있고 citeturn1search5turn1search20, OCEL 2.0은 객체 중심 로그의 더 표현력 있는 교환 표준을 제공한다고 설명합니다. citeturn1search14turn1search6

### 요구 입력과 산출물
입력(Required Inputs)은 다음을 최소 단위로 고정합니다.

- **CPG 그래프/YAML**: 도메인별 규칙(필수/금기/마감/순서 포함)  
- **Scenario fixture**: (환자 상태, expected_actions, deadlines)  
- **Episode log**: 행동 이벤트(시간 포함), 관찰/상태 스냅샷(가능하면), 도구 호출 기록  
- **외부 데이터 어댑터 입력**: AgentClinic/MedAgentBench/MedChain의 원시 샘플(대화/도구/API/이미지 메타데이터 등) citeturn0search0turn7search4turn0search10  
- **대규모 이벤트 로그**: MIMICEL의 CSV/XES citeturn5view0turn8view0, 또는 Synthea 기반 합성 이벤트 로그(후술) citeturn1search0turn1search3

산출물(Outputs)은 “합격/실패가 명확한” 형태로 생성합니다.

- 테스트 리포트: junit XML + HTML(선택)  
- 정량 메트릭 JSON: 기능/강건성/공정성/확장성 지표  
- **골든 테스트 아티팩트**: 입력 fixture + 기대 출력(위반 리스트, 점수, Safety Gate 값)  
- 스트레스 테스트 리포트: 처리량(events/sec), peak RSS, 내보내기/재로딩 성공률  
- 리프로덕션 번들: 실행 커맨드, 환경 고정 파일, 시드/버전 로그(아래 체크리스트)

## 검증 아키텍처와 격리·안티-리키지 설계
### 검증 하네스 구조
검증 프레임워크는 “테스트 정의(What) ↔ 실행기(How)”를 분리합니다.

- **tests/**: 단위/통합/E2E/골든/스트레스 테스트 정의  
- **eval_harness/**: 실험 실행(예산 매칭, 로그 수집)  
- **reports/**: 표준화된 결과(JSON + 요약표)  
- **scripts/**: 재현 커맨드·프로파일링·스트레스 러너

외부 벤치마크 통합(AgentClinic/MedAgentBench/MedChain)은 “성능 비교”보다 “파싱·정규화·도메인 감지·fallback 안정성”의 테스트 입력으로 취급합니다. AgentClinic은 “대화+능동적 데이터 수집”을 포함하는 시뮬레이션 기반 의료 에이전트 벤치마크로 소개됩니다. citeturn0search0turn0search12 MedAgentBench는 300개 임상 과제를 FHIR 호환 환경과 상호작용하며 수행하도록 설계되었다고 명시합니다. citeturn0search1turn7search4 MedChain은 12,163 케이스의 순차적 임상 워크플로우 데이터로 설명됩니다. citeturn0search2turn0search10

### 컨테이너/의존성 분리로 스코어-에이전트 격리
스코어링 누출을 “구조적으로” 줄이기 위해, 최소 아래 2-컨테이너(또는 2-venv) 모델을 권장합니다.

- **scorer container**: cpg_engine + assessor_core + semantic_layer(스코어러 부분) + export(XES/OCEL)  
- **agent container**: agent_runner + tool_api + 외부 벤치마크 어댑터(필요 시)  

실행기는 두 컨테이너 사이를 (a) 파일 기반 이벤트 로그, 또는 (b) gRPC/stdio 파이프 같은 좁은 인터페이스로만 연결합니다. scorer 측은 네트워크 egress를 차단하고(offline), agent 측은 scorer 코드가 설치되지 않도록 “extras 분리”를 적용합니다.

- PhysioNet의 credentialed 데이터 라이선스/DUA는 민감 데이터 취급 책임(재식별 금지 등)과 자격/교육 요구를 명시합니다. citeturn7search2turn7search5  
- MIMIC-IV/MIMICEL 자체도 credentialed access 정책(자격 사용자 + DUA + CITI 교육)을 요구합니다. citeturn6view1turn8view0  
따라서 격리 설계는 “재현성”뿐 아니라 “데이터 거버넌스” 관점에서도 필수입니다.

### 카나리 토큰 기반 누출 탐지(실험적)
“스코어러 내부 정보(노드명, 숨은 액션 키, 룰 텍스트)가 에이전트 프롬프트/응답으로 유출되는지”를 탐지하기 위해, 테스트 환경에서만 다음을 삽입합니다.

- scoring-side 코드/데이터에 **고유한 무의미 문자열(canary)** 삽입  
  - 예: `CGA_CANARY__<uuid>`를 CPG 그래프 메타데이터/주석/스코어러 로그 포맷 문자열 등에 주입  
- agent-side 입력/출력 전체(프롬프트, tool call payload, action JSON, reasoning trace가 있다면 그 텍스트까지)를 수집  
- 정규식/해시 기반으로 canary 출현 여부를 검사  
- **출현 = 즉시 실패(fail)**로 처리(0 허용)

의사코드(개념):

```python
def leakage_scan(transcripts: list[str], canaries: list[str]) -> dict:
    hits = {c: 0 for c in canaries}
    for t in transcripts:
        for c in canaries:
            if c in t:
                hits[c] += 1
    return {"total_hits": sum(hits.values()), "hits": hits}
```

이 방식은 “완전 보장”이 아니라 **회귀 검출(regression detector)**로 쓰는 것이 핵심입니다.

## 테스트 설계와 구체적 케이스
### 테스트 유형·범위 표
아래 표는 “무엇을 어떤 테스트로 잡을지”를 고정합니다(테스트 추가 시 표를 먼저 갱신하도록 개발 규칙화).

| 테스트 유형 | 주요 대상 모듈 | 핵심 검증 질문 | 최소 픽스처 | 합격 기준(요약) |
|---|---|---|---|---|
| 단위(Unit) | CPG 엔진(평가/스테퍼/도달성/시간 제약) | 입력 상태→제약 산출이 결정적·일관적인가 | 소형 그래프 1–3개, 상태 10개 | 제약 세트 exact match(스냅샷) |
| 단위(Unit) | 위반 추출기 | 5개 위반 유형이 정확히 분리되는가 | 행동 로그(시간/순서 포함) 20개 | 위반 타입·개수·시점 exact match |
| 단위(Unit) | HarmScorer/ Safety Gate | 가중치·심각도·게이트가 단조성 유지? | 위반 리스트 + 로그 | A보다 B가 위험↑이면 점수↓(단조성) |
| 통합(Integration) | 엔진+추출기+스코어러 | E2E가 아닌 “스코어링 파이프” 정합성 | 시나리오 10개 | 위반·점수·서브스코어 일관 |
| E2E | eval_harness+agent_runner+scenario_engine | 실행기/예산/로그/재현성 잘 묶였는가 | Mock LLM + 시나리오 5개 | 예산 강제, 재실행 동일 결과 |
| A/B 골든 | 전 도메인 대표 규칙 | 규칙 1개 차이만 점수/위반에 반영? | A/B 쌍 12개 | “딱 1개 위반만” 차이 + 기대 폭 |
| 스트레스 | export/import + 대규모 로그 | XES/OCEL 내보내기/재로딩/성능 | MIMICEL(XES/CSV) citeturn5view0turn8view0 | 성공률 100%, 처리량·메모리 회귀 없음 |

### A/B 골든 테스트(가이드라인 근거 포함)
골든 테스트는 “임상적으로 명확하고, 단 하나의 조건만 바뀌는” 쌍으로 구성합니다. **실패 시 디버깅 비용이 낮고, 회귀에 가장 강한 방어선**이 됩니다.

#### 흉통: ECG 10분 규칙(시간 위반)
AHA/ACC 흉통 가이드라인은 급성 흉통 환자에서 12유도 ECG를 도착 후 10분 내 확보·검토(특히 STEMI 평가)를 포함하는 권고를 명시합니다. citeturn2search1turn2search9

- A(준수): `ecg_time = 8min`  
- B(위반): `ecg_time = 15min`  
- 기대:
  - B에서 **TIMING 1건** 추가
  - C4(Timing) 하락, peak_risk가 정책에 따라 상승
  - Score: `score_B < score_A`(최소 하락폭 threshold 설정)

구현 포인트: 타임스탬프 단위(초/분) 혼동을 막기 위해, 테스트 픽스처는 “초 단위 epoch”로도 한 번, “분 단위 상대시간”으로도 한 번 실행해 일관성을 확인합니다(강건성 축).

#### 패혈증: 항균제 1시간·Hour-1 bundle(시간/순서)
entity["organization","Society of Critical Care Medicine","critical care society"] 및 entity["organization","Surviving Sepsis Campaign","sepsis guidelines program"] 자료는 패혈증/쇼크에서 항균제를 즉시(이상적으로 1시간 내) 투여하는 권고와 Hour-1 bundle의 속도·우선순위를 강조합니다. citeturn2search0turn2search8

- A(준수): blood culture → antibiotics(순서 준수), antibiotics_time=45min  
- B(위반1): antibiotics → blood culture(순서 위반), antibiotics_time=45min  
- B(위반2): blood culture → antibiotics(순서 준수), antibiotics_time=75min(시간 위반)  
- 기대:
  - B(위반1)에서 SEQUENCE 1건
  - B(위반2)에서 TIMING 1건
  - 둘 다 A보다 점수 하락, 단 “순서 위반 vs 시간 지연”의 상대 가중치는 정책대로 재현

#### 뇌졸중: thrombolysis/치료 창(적격성·시간)
AHA/ASA 2019 업데이트는 IV alteplase의 시간 창(예: 3–4.5시간 범위의 적응증 조건) 등을 포함합니다. citeturn2search2turn2search30  
참고로 2026년에 새로운 가이드라인이 게시되어(성인 확장 및 소아 가이드 포함) 최신 권고가 바뀔 수 있으므로, 골든 테스트는 “벤치마크가 기준으로 삼는 버전”을 고정하고, 버전 업데이트는 별도 마이그레이션 작업으로 분리하는 것이 안전합니다. citeturn2search14

- A: last-known-well = 2h, 주요 금기 없음 → tPA 고려(허용/필수는 모델 정책에 맞춰 명시)  
- B: last-known-well = 6h → tPA 금기/비적격(또는 DEVIATION)  
- 기대: 금기/허용 판정과 위반 유형이 명확히 갈림

### 단위 테스트 예시(위반 유형 5종을 “정확히” 잡는 케이스)
각 위반 유형별로 “최소 로그”를 마련해, 추출기의 오탐/미탐을 즉시 탐지합니다.

- OMISSION: 필수 행동 1개 누락(다른 행동은 모두 정상)  
- COMMISSION: 금기 행동 1개만 수행(나머지 정상)  
- TIMING: 마감 1개만 초과(경계값 바로 전/후)  
- SEQUENCE: 선행 조건 위반 1개(순서만 뒤집기)  
- DEVIATION: 허용 범위 밖 행동 1개(정규화가 과잉 매핑되지 않게)

스코어러 단위 테스트는 “가중치 변경/심각도 변경” 시 회귀를 막아야 하므로, 아래의 **단조성(property-based)** 규칙을 추가합니다.

- 동일한 로그에서 severity를 1단계 올리면 점수는 감소(또는 동일)해야 한다.  
- 동일한 severity에서 violation_type_weight가 큰 위반을 작은 위반으로 바꾸면 점수는 증가(또는 동일)해야 한다.

## 데이터 픽스처와 외부/대규모 데이터셋 활용 계획
### 데이터셋 비교 표
요구된 5개 데이터셋을 “검증 목적” 관점에서 비교합니다.

| 데이터셋 | 성격/모달리티 | 접근/제약 | 스케일 힌트 | 검증 프레임워크에서의 역할 |
|---|---|---|---|---|
| Synthea | 합성(synthetic) EHR 생성기, FHIR 출력 가능 citeturn1search0turn1search3 | 공개/프라이버시 제약 낮음(합성) citeturn1search0 | 대량 생성 가능(설정/시드 기반) | 대규모 픽스처 생성(회귀·로드·정규화·예산 스트레스) |
| MIMICEL | 응급실 이벤트 로그(CSV + XES), 7,568,824 events/425,028 cases, XES 변환 포함 citeturn5view0 | credentialed access + DUA + CITI 교육 요구 citeturn8view0turn6view1 | 매우 큼(대용량 로그) | XES 내보내기/재로딩·처리량·메모리 스트레스, 포맷 회귀 |
| AgentClinic | 대화+능동적 데이터 수집 포함 의료 에이전트 벤치마크 citeturn0search0turn0search12 | 오픈소스/구현 제공(리포지토리) citeturn0search4 | 다전문과/다언어 등(설명 기반) citeturn0search8 | 파서/정규화 강건성(대화→행동 구조화), 도메인 감지·fallback 테스트 |
| MedAgentBench | 300개 임상 과제, FHIR 호환 상호작용 환경 citeturn0search1turn7search4 | 코드 공개(논문/리포지토리) citeturn0search25turn7search1 | 환자 100명, 700k+ data elements 언급 citeturn7search4 | 도구/API 기반 행동 출력 검증, budget matching·tool-call 회귀 |
| MedChain | 12,163 임상 케이스, 순차적 임상 워크플로우 강조 citeturn0search2turn0search10 | NeurIPS D&B 트랙 공개 포스터/논문 citeturn0search2 | 12k 규모, 순차성·상호작용 강조 | 외부 타당도 입력, SEQUENCE/DEVIATION 유형의 파서·평가 안정성 테스트 |

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["Synthea synthetic patient generator logo","PhysioNet MIMIC IV dataset","AgentClinic benchmark screenshot","OCEL 2.0 metamodel diagram"],"num_per_query":1}

### 픽스처(고정 입력) 설계
검증에서 “중요한 것은 다양성”이 아니라 **불변식이 깨졌을 때 즉시 알 수 있는 최소 예제(minimal counterexample)**입니다. 따라서 픽스처는 3계층으로 설계합니다.

- Micro fixture(단위): 5–20 이벤트로 위반 1개만 재현  
- Meso fixture(통합): 도메인별 대표 시나리오 10개(각각 위반 유형 1–2개 포함)  
- Macro fixture(스트레스): MIMICEL 등 대규모 로그 + 합성 로그(수십만~수백만 이벤트)

Synthea 기반 합성 픽스처는 “가이드라인 준수” 자체를 라벨링하기보다, **파서/정규화/성능 회귀**에 최적화합니다. Synthea가 합성 환자 EHR을 생성하며 공개 정보 기반·오픈소스이고, 프라이버시 제약이 낮다고 명시된 점이 테스트 데이터 제조에 유리합니다. citeturn1search0turn1search3  
또한 MedAgentBench가 FHIR 호환 환경과의 상호작용을 요구하므로, Synthea의 FHIR 출력은 “FHIR 리소스 → 행동으로의 매핑” 테스트를 구성하기 좋습니다. citeturn7search4turn1search3

### MIMICEL을 활용한 XES/CSV 호환·대규모 스트레스
MIMICEL은 XES 형식으로도 제공되며, 이벤트 로그 표준 스키마(트레이스/이벤트 구조)를 설명하고, CSV→XES 변환에 Python 라이브러리(PM4Py)를 사용했다고 명시합니다. citeturn5view0turn8view0  
XES 표준은 “대용량 이벤트 데이터의 운송/저장/교환 표준화”를 목표로 한다고 설명됩니다. citeturn1search5turn1search20  
따라서 검증 프레임워크의 스트레스 테스트는 다음을 포함해야 합니다.

- XES → 내부 이벤트 로그 로딩 성공률(100%)  
- 내부 로그 → XES export → 재로딩 후 “동치성 체크”(이벤트 수/시간 정렬/필수 필드)  
- 내부 로그 → OCEL 2.0 export(JSON/SQLite 중 1개 선택) → 재로딩 후 동치성 체크  
  - OCEL 2.0은 객체 변화/관계 표현 및 교환 포맷(JSON/XML/SQLite)을 제공한다고 설명됩니다. citeturn1search14turn1search6

## 메트릭·합격 기준·스트레스 테스트·재현성 운영
### 메트릭과 합격 기준 표
아래는 “단 1번의 CI 실행”으로도 합격/실패를 판정할 수 있게 설계한 기준입니다(수치는 기본값이며, 프로젝트 정책으로 고정).

| 범주 | 메트릭 | 측정 방법 | 기본 합격 기준 |
|---|---|---|---|
| 기능 | 제약 산출 스냅샷 일치율 | 엔진 출력 구조체를 JSON 스냅샷 비교 | 100% |
| 기능 | 위반 추출 정확도 | 골든 로그에서 위반 타입/개수/시점 비교 | 100% |
| 안전 | Safety Gate 트리거 정확도 | 심각 위반 삽입 시 gate가 작동하는지 | 100% |
| 단조성 | 위험↑ → 점수↓ | property-based(무작위 변형)로 검증 | 위반 0 |
| 강건성 | JSON/행동 정규화 복구율 | 외부 벤치마크 변형 입력(형식 오류 포함) | ≥ 99.5% (심각 위반 누락 0) |
| 공정성 | 예산(토큰/툴콜) 편차 | agent별 budget_tracker 로그 비교 | 편차 ≤ 1% 또는 정책값 |
| 확장성 | 처리량(events/sec) | 스트레스 러너에서 측정 | 기준 대비 10% 이상 하락 시 실패 |
| 확장성 | peak RSS | 메모리 프로파일러로 peak 측정 | 기준 대비 15% 이상 증가 시 실패 |
| 포맷 | XES/OCEL export-import 성공률 | round-trip 테스트 | 100% |
| 누출 | 카나리 히트 수 | leakage_scan | 0 |

### 스트레스 테스트 설계
스트레스는 “시간이 오래 걸리는 테스트”이므로, CI와 분리해 2단계로 운영합니다.

- CI(짧은 스트레스): 1–5만 이벤트로 XES/OCEL round-trip + 처리량/메모리 스모크  
- Nightly/Weekly(긴 스트레스): MIMICEL 샘플/전체 구간으로 확장  
  - MIMICEL은 수백만 이벤트 규모(7,568,824 events)가 명시되어 있어 스트레스에 충분합니다. citeturn5view0

### 재현성 체크리스트
entity["organization","NeurIPS","ml conference"] 제출을 염두에 둔다면, 최소 “다른 연구자가 같은 커맨드를 실행해 같은 결과를 얻는 경로”를 제공해야 합니다. NeurIPS는 제출 PDF에 paper checklist를 포함하도록 안내하고 citeturn4search0, 코드 제출 정책에서 의존성 명시·자체 실행 가능성을 권장합니다. citeturn4search13 D&B 트랙은 데이터 호스팅과 Croissant 메타데이터를 요구합니다. citeturn4search1turn4search2

체크리스트(실행 산출물로 남기기):

- `requirements.txt`/`uv.lock`/`poetry.lock` 중 하나를 고정(1개만 선택)  
- Python 버전(3.11+) 고정, OS/커널 정보 기록  
- 모든 실험 run에 **seed**(python/random/numpy/torch) 기록  
- 데이터 버전(예: MIMICEL v2.1.0, MIMIC-IV v3.1)과 DOI를 로그에 남김 citeturn8view0turn6view3  
- 외부 벤치마크는 commit hash(리포지토리 SHA) 기록(예: AgentClinic/MedAgentBench Git SHA) citeturn0search4turn0search25  
- 스트레스 벤치마크는 입력 이벤트 수/필터 조건/머신 스펙/측정 횟수 기록  
- 결과는 `reports/<date>/<gitsha>/`에 JSON+요약표로 저장

## 도구·스크립트·일정·리스크
### 권장 스크립트/커맨드 세트
테스트 프레임워크는 “정해진 커맨드 5개로 모든 것을 돌릴 수 있게” 만드는 것이 유지보수에 유리합니다.

- 린트/포맷/타입체크(예: ruff/mypy)  
- 단위/통합 테스트: `PYTHONPATH=. pytest tests/test_engine tests/test_assessor -q`  
- E2E 테스트: `PYTHONPATH=. pytest tests/test_e2e -q`  
- 골든 테스트: `PYTHONPATH=. pytest tests/test_golden -q` (신설)  
- 스트레스/성능: `python scripts/bench/stress_eventlog_roundtrip.py --dataset mimicel --format xes --limit 50000`

프로파일링은 “정확도 테스트”와 분리해, 성능 회귀를 구조화합니다.

- 처리량: 이벤트/초, 에피소드/분(metric JSON 저장)  
- 메모리: peak RSS  
- export/import: round-trip 성공률 및 소요시간

XES/OCEL의 목적(대용량 이벤트 데이터의 교환/표현력 확대)은 표준 문서에서 강조됩니다. citeturn1search5turn1search14

### 일정·리소스 추정(제약 미정 → 열린 선택지 포함)
컴퓨트/스토리지 제약이 명시되지 않았으므로 “열린 선택지”로 두되, 팀·인프라 규모별로 계획을 쪼갭니다.

- 열린 선택지:
  - 컴퓨트: CPU-only, 단일 GPU(에이전트 모델 구동), 다중 GPU(대규모 모델/병렬)  
  - 스토리지: 로컬 SSD, NAS, 오브젝트 스토리지  
  - 데이터 접근: credentialed(MIMIC 계열) vs 공개(Synthea/공개 벤치마크)

권장 일정(인력 2–3명 기준, 총 3–5주):

- 주차 A: 골든 테스트 12쌍 + 단위 테스트 스냅샷 체계 구축  
- 주차 B: 통합/E2E 테스트와 budget matching 강제 검증(Mock LLM 포함)  
- 주차 C: 외부 어댑터 입력 검증(AgentClinic/MedAgentBench/MedChain 샘플), 정규화 강건성 테스트  
- 주차 D: 스트레스(소형→대형), XES/OCEL round-trip, 성능 기준선(baseline) 확정  
- 주차 E: 컨테이너 격리/카나리 누출 탐지 CI 통합 + 재현성 번들 문서화(NeurIPS 체크리스트 대응) citeturn4search0turn4search13turn4search1

### 주요 리스크와 완화
- **리스크: MIMIC/MIMICEL 접근 지연(credentialed + DUA + CITI)**  
  - 완화: 초기 스트레스는 Synthea 합성 로그로 시작, MIMIC 계열은 승인 후 확장. MIMIC-IV/MIMICEL이 credentialed 정책을 요구하는 것이 명시되어 있습니다. citeturn6view1turn8view0
- **리스크: 외부 벤치마크 입력 다양성으로 파서/정규화가 깨짐**  
  - 완화: “복구율(≥99.5%) + 심각 위반 누락 0”의 이중 기준을 두고, 실패 입력은 최소 반례로 축소하여 골든 회귀로 편입.
- **리스크: LLM 비결정성으로 E2E가 플래키(flaky)해짐**  
  - 완화: 정상동작 검증의 1차 목표는 스코어러/하네스이므로 Mock LLM 기반 결정적 E2E를 기본으로 두고, 실제 LLM 실험은 별도 실험 트랙으로 분리.
- **리스크: 스코어러 내부 정보 누출**  
  - 완화: 컨테이너/의존성 분리 + 카나리 탐지(히트 0) + 네트워크 차단.

## 우선순위 실행 단계와 예시 코드
아래 단계는 “최소 노력으로 최대 리스크를 줄이는” 순서로 정렬했습니다.

### 즉시 착수
첫 단계는 골든 테스트와 단위 테스트 스냅샷을 고정해, 이후 리팩터링/확장 시 회귀를 즉시 잡는 것입니다.

- `tests/test_golden/` 신설  
- 도메인별 A/B 2쌍씩(최소 12쌍)부터 시작  
- 각 골든 케이스에 대해:
  - 입력 fixture(YAML/JSON)  
  - 기대 위반 리스트(JSON)  
  - 기대 점수/서브스코어(JSON)  
  - “딱 한 가지 변화만” 들어가도록 리뷰 규칙화

예시(개념) – A/B 실행기를 고정:

```python
def run_case(case_fixture) -> dict:
    engine = load_engine(case_fixture["graph"])
    episode_log = simulate_or_load(case_fixture["episode_log"])
    violations = extract_violations(engine, episode_log)
    score = score_episode(violations, episode_log, case_fixture["scoring_config"])
    return {"violations": violations, "score": score}

def assert_ab_monotonic(a_res, b_res, expected_new_violation_type):
    assert b_res["score"]["final_score"] < a_res["score"]["final_score"]
    assert count_new_type(b_res["violations"], expected_new_violation_type) == 1
```

### 격리·누출 탐지 CI 통합
두 번째는 “깨지면 큰 사고”인 스코어-에이전트 분리를 자동 검증하는 것입니다.

- scorer/agent 컨테이너 분리(또는 2-venv)  
- scorer 네트워크 차단(가능하면)  
- 카나리 토큰 삽입 + `leakage_scan` 실행  
- 누출 히트 0을 CI fail 조건으로 고정

### 외부 데이터 어댑터의 “파싱 계약(contract) 테스트”
세 번째는 외부 벤치마크 입력을 “우리 내부 표준 EpisodeLog”로 변환하는 어댑터에 대해, 계약 테스트를 걸어 확장성을 보장하는 것입니다.

- AgentClinic: 대화/도구 호출을 “관찰→행동 후보→결정 행동”의 이벤트로 직렬화 citeturn0search12  
- MedAgentBench: FHIR API 상호작용을 tool-call 이벤트로 캡처(표준 API 기반 언급) citeturn7search4turn7search0  
- MedChain: 순차 워크플로우 단계(진료 단계)별 행동/결정 이벤트로 변환 citeturn0search10

### XES/OCEL round-trip 스트레스와 성능 기준선 확정
마지막으로 스케일 테스트를 “측정 가능하고, 회귀 감지 가능하게” 고정합니다.

- XES: 표준의 목적이 대용량 이벤트 데이터 교환임을 근거로 round-trip을 필수 회귀로 둡니다. citeturn1search5turn1search20  
- OCEL 2.0: 객체 관계/상태 변화를 더 잘 표현하는 표준 문서를 근거로 최소 1개 포맷(JSON 또는 SQLite)을 고정해 round-trip을 수행합니다. citeturn1search14turn1search6  
- MIMICEL: XES/CSV 규모가 명시되어 있어 스트레스 입력으로 적합합니다. citeturn5view0

이때 PhysioNet/MIMIC 계열의 접근 정책(자격/DUA/교육)은 리포지토리 문서에 명확히 분리 표기하고, 공개 가능 실험(Synthea 기반)과 승인 필요 실험(MIMIC 기반)을 “두 트랙”으로 운영하는 것이 안전합니다. citeturn6view1turn1search0turn1search3