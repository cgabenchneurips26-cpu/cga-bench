# CGA-Bench 정상동작 검증과 벤치마크·실험 확장 제안서

## 목표 정의와 “정상 동작”의 검증 기준
이 프로젝트의 “정상 동작”은 단순히 코드가 실행되는 수준이 아니라, **(1) 임상 가이드라인 기반 제약(필수/금기/허용·시간·순서)이 일관되게 계산되고**, **(2) 로그로부터 위반이 재현 가능하게 추출되며**, **(3) 위험(Severity)과 권고 강도 등을 반영하는 점수(Track B)가 의도대로 단조(monotonic)·안전 중심(safety-sensitive)으로 작동하고**, **(4) 외부 벤치마크/새 데이터셋으로 확장했을 때도 데이터 정규화·도메인 정합성·공정성(예산 매칭)이 깨지지 않는 상태**로 정의하는 것이 가장 실용적입니다. (특히 “정적 QA 중심 평가가 실제 임상 의사결정(정보 수집→검사/치료 선택→순차 진행)을 충분히 반영하지 못한다”는 문제의식은 최근 의료 에이전트 벤치마크들이 공통적으로 강조하는 지점입니다.) citeturn7view3turn7view2turn0search4

또한 NeurIPS(특히 Datasets & Benchmarks 트랙)를 목표로 한다면, “정상 동작”은 연구 커뮤니티 관점에서는 **재현 가능한 실행 경로(설치/커맨드/환경/데이터 접근)와 검증 가능한 산출물(점수·로그·분석 스크립트)**까지 포함합니다. NeurIPS는 “코드 공개를 강제하지는 않지만, 합리적인 재현 경로를 요구”하며, Datasets & Benchmarks 트랙은 데이터/벤치마크 특성에 맞는 제출·호스팅·메타데이터 요구를 별도로 둡니다. citeturn6search0turn6search1turn6search7

정리하면, 이번 확장의 1차 목적은 **스코어링/위반감지/분리(Scoring-Agent separation)·공정성 가드가 깨지지 않는지**를 “증거(테스트·스트레스 실험·대조군)”로 확인하는 것이고, 2차 목적은 **(A) 기존 6개 도메인 내 시나리오 커버리지 확장**, **(B) 별개 신규 벤치마크 제안/구축**, **(C) 학술 제출용(NeurIPS급) 실험 패키지 확장**을 한 번에 달성하는 것입니다. citeturn6search0turn6search1

## 정상 동작 확인을 위한 검증 프레임워크
정상 동작을 “확장성 있게” 보장하려면, 테스트를 **정적 정확성(정답 검증)**과 **동적 강건성(변형·잡음·스케일 변화에도 불변식 유지)**로 나눠 설계하는 것이 효과적입니다. 특히 이 프로젝트는 “행동 시퀀스 + 시간 제약 + 금기/필수 규칙 + 위험 점수”가 결합되므로, 단순 단위테스트만으로는 놓치는 실패 모드가 생기기 쉽습니다. citeturn7view0turn4search4turn4search5

핵심은 아래 6개 축을 명시적으로 검증하는 것입니다(각 항목은 “통과/실패”가 분명한 형태로 설계).

첫째, **규칙/그래프 정합성(가이드라인→그래프→제약의 보존)**. 예를 들어 entity["organization","Surviving Sepsis Campaign","sepsis guideline initiative"]의 Hour-1 bundle은 혈중 젖산(lactate) 측정, 항생제 투여 전 혈액배양, 광범위 항생제, 수액, 필요 시 승압제 등의 *시간 민감한* 요소를 포함하며, 이는 “필수 행동 + 마감 시간 + 순서 제약”으로 표현 가능해야 합니다. citeturn3search23turn3search7turn1search0  
이 검증은 “그래프가 해당 원문 요구를 표현하고 있는가?”를 체크하는 단계라서, 최소한 대표 도메인(Sepsis/Chest pain/Stroke)에서 **원문 문구→그래프 노드/엣지→평가 결과**가 추적 가능해야 합니다. citeturn1search0turn1search5turn2search1

둘째, **A/B 대조(contrasting) 시나리오의 스코어 단조성**. 이미 문서에 “혈액배양 후 항생제(준수) vs 항생제 후 혈액배양(Sequence 위반)” 같은 패턴이 제시되어 있으므로, 이를 시스템 레벨의 “골든 테스트”로 격상시키는 것이 좋습니다. A/B의 차이는 *오직 하나의 제약(순서·시간·금기)*만 바뀌고 나머지는 동일해야 하며, 결과는 “위반 유형 1개만 추가”되고 그에 따라 점수가 감소해야 합니다. 이 스타일은 임상 프로토콜의 핵심 특성(순서/시간)에 잘 대응합니다. citeturn1search5turn3search23

셋째, **Safety Gate의 민감도/경계조건 검증**. 예컨대 entity["organization","American Heart Association","medical association us"]/entity["organization","American College of Cardiology","cardiology society us"] 흉통 가이드의 “도착 후 10분 내 ECG 확인” 같은 시간 제약은 임상적으로 중요하며, 지연이 TIMING 위반으로 확실히 잡혀야 합니다. citeturn1search5turn1search1  
여기서 특히 중요한 것은 **경계값(예: 10분, 60분) 바로 전/후**에 대해 위반이 뒤집히는지를 자동화된 테스트로 고정하는 것입니다. (이 검증이 없으면 외부 데이터셋 통합 시 timestamp 단위(초/분) 불일치로 위반 판정이 흔들리는 문제가 실제로 자주 발생합니다.) citeturn7view0

넷째, **정규화/매핑 계층의 안정성**. 외부 벤치마크를 붙일 때 가장 흔한 실패는 “행동 ID/이름/도구 호출이 조금만 달라져도 expected_actions 매칭이 깨지는 문제”입니다. 이를 막으려면, (a) 동의어·형태 변형·철자 변형에 대한 정규화 회복력(robustness)과 (b) 정규화가 과잉 일반화되어 금기 행동을 “허용 행동”으로 오분류하지 않는 안전성(precision)을 동시에 고정해야 합니다. 특히 의료에서는 *잘못된 매핑이 곧 위험 점수의 왜곡*으로 이어집니다. citeturn2search3turn2search23

다섯째, **Scoring-Agent separation의 “공격적” 검증(Leakage test)**. 단순히 “에이전트가 cpg_engine을 import하지 않는다” 수준이 아니라, (a) 런타임에서 scoring-side 모듈 경로를 격리(컨테이너/별 패키지/옵션 의존성 분리), (b) 에이전트 출력에 “스코어러 내부 용어/노드명/숨겨진 액션 키”가 과도하게 등장하는지 탐지(카나리아 토큰 방식), (c) 오라클/규칙 기반 에이전트가 평가 그래프 없이도 일관된 성능을 유지하는지 등을 통해 “정보 누출 가능성”을 실험적으로 낮추는 것이 논문화에도 유리합니다. 의료 에이전트 벤치마크들도 (대화·도구 사용·환경 상호작용에서) 모델이 허점을 학습할 수 있음을 반복적으로 지적합니다. citeturn7view3turn7view2turn0search4

여섯째, **대규모 스트레스 테스트(성능·메모리·로그 크기)**. 로그 기반 스코어링은 이벤트 수가 커지면 병목이 “규칙 판정 자체”보다 “로그 처리/정규화/내보내기(XES/OCEL)”에서 발생하는 경우가 많습니다. XES는 대규모 이벤트 데이터 교환을 표준화하기 위해 만들어졌고(IEEE 표준), OCEL 2.0은 객체 중심 이벤트 로그로 더 풍부한 관계/상태 변화를 표현하도록 확장된 표준입니다. 따라서 “내보내기 + 재로딩 + 재채점”까지 포함한 부하 테스트가 확장성 검증의 핵심이 됩니다. citeturn4search4turn4search20turn4search5turn4search13

## 기존 도메인 내 시나리오·데이터셋 확장 전략
“같은 도메인(Sepsis/Chest pain/Stroke/HF/AKI/DKA) 안에서 더 다양한 시나리오로 커버리지를 넓히는 것”은, 벤치마크 논문에서 가장 설득력 있는 확장 축입니다. 이유는 (1) 도메인 정합성 문제가 상대적으로 작고, (2) 점수/위반 유형 분포를 의도적으로 설계할 수 있으며, (3) “가이드라인 준수”라는 핵심 주장(construct validity)을 강화하기 쉬워서입니다. citeturn1search0turn1search1turn2search1turn2search0turn1search2turn2search3

확장 설계는 “케이스 수를 늘리는 것”만으로는 부족하고, **위반 유형 5종(OMISSION/COMMISSION/TIMING/SEQUENCE/DEVIATION)이 모두 충분히 발생하도록** 시나리오 변형 축을 체계적으로 구성해야 합니다. 아래는 도메인별로 “실제로 위반을 유발하는 축”을 기준으로 한 확장 제안입니다.

Sepsis(SSC 계열)는 시간 압박·순서 의존성이 가장 뚜렷합니다. Hour-1 bundle은 “가능한 빨리” 치료를 시작하되, 혈액배양을 항생제 전에 시행하는 등 순서 제약이 결합됩니다. citeturn3search23turn3search7turn1search0  
따라서 (a) lactate 초기값/재측정 조건, (b) 저혈압 vs lactate 상승(≥4) 조건에 따른 수액/승압제 분기, (c) 배양 채취 지연/누락, (d) 항생제 스펙트럼 부적절(커미션/디비에이션) 같은 축을 조합하면, **TIMING+SEQUENCE+OMISSION**을 높은 신호로 만들 수 있습니다. citeturn3search23turn3search7turn1search32

Chest pain(AHA/ACC 2021)은 초기에 ECG를 10분 내 획득/판독해야 한다는 시간 제약이 명확하고, ACS 위험도에 따라 검사·처치 경로가 갈립니다. citeturn1search5turn1search1  
확장 축은 (a) STEMI/NSTEMI/비심장성 통증의 감별 난이도, (b) 초기 troponin 음성 후 반복 검사 타이밍, (c) 저혈압/우심실 경색 등 약물 금기 시나리오(커미션), (d) 과잉 검사(디비에이션)로 설계하는 편이 효과적입니다. citeturn1search1turn1search5

Stroke(AHA/ASA 2019 update)는 IV alteplase/tPA 적응증, 혈관 내 치료(Thrombectomy) 적합성 등 “적격성 판단 + 제한된 치료 창”이 핵심입니다. citeturn2search1turn2search17  
확장 축은 (a) last-known-well 시간 불명/모호, (b) 출혈성 뇌졸중/저혈당 등 mimic 배제, (c) 항응고제 복용/혈압 등 금기 조건, (d) 영상 검사 순서(CT→CTA 등)로 설계해 **금기 회피(C3)·타이밍(C4)**를 촘촘히 볼 수 있습니다. citeturn2search1turn2search17

Heart failure(entity["organization","American Heart Association","medical association us"]/entity["organization","American College of Cardiology","cardiology society us"]/HFSA 2022)는 만성/급성 악화, 박출률 분류(HFrEF/HFpEF) 및 약물군(GDMT) 등 “상태 분류→치료 조합” 성격이 강합니다. citeturn2search0turn2search16  
따라서 (a) 저혈압/신기능 저하/고칼륨혈증 등으로 일부 약물이 제한되는 상황(금기/허용 경계), (b) 급성 폐부종에서 이뇨제/산소/환기 지원 우선순위(순서·타이밍), (c) 과잉 수액·부적절 약물(커미션)을 설계하면 **DEVIATION/COMMISSION** 신호를 높일 수 있습니다. citeturn2search0turn2search16

AKI(KDIGO 2012)는 정의/분류(진단 기준)과 예방/약물 독성 회피가 핵심이며, 특히 조영제 유발 AKI 같은 시나리오는 “선제적 예방 행동의 누락(OMISSION)”을 강하게 평가할 수 있습니다. citeturn1search2turn1search10  
확장 축은 (a) 기저 CKD/탈수/패혈증 동반, (b) 조영제 노출 전후 수액/모니터링, (c) NSAID/ACEi/ARB 등 신독성 위험 약물 동시 사용(상호작용), (d) 소변량 모니터링 누락 등으로 구성하는 것이 자연스럽습니다. citeturn1search2turn1search10

DKA/HHS는 인슐린 주입, 전해질(특히 K+) 관리, 수액, 원인 치료의 조합이며, 최근 ADA/국제 컨센서스가 진단·해소 기준 업데이트를 논의하고 있습니다. citeturn2search3turn2search23turn2search15  
확장 축은 (a) euglycemic DKA, (b) HHS 혼합형, (c) 초기 K+에 따른 인슐린 시작 타이밍(금기/순서), (d) 과도한 인슐린/수액으로 인한 위험(커미션) 등이며, “고정된 프로토콜을 제대로 따라가는지”를 보기 좋습니다. citeturn2search3turn2search23

추가로, 문서에 포함된 소아 발열/두통(수막염/SAH) 확장은 “외부 타당도”를 강화하는 좋은 방향입니다. 예를 들어 entity["organization","National Institute for Health and Care Excellence","uk guideline body"]의 “5세 미만 발열 평가” 가이드는 serious illness 위험도 분류를 목표로 하며, “suspected sepsis” 가이드와 연결해 위험 징후(레드/앰버/그린)에 따른 의사결정을 체계화합니다. citeturn3search1turn3search25turn3search5  
SAH는 entity["organization","American Heart Association","medical association us"]/ASA의 aSAH 가이드가 존재하므로 “CT/LP 타이밍, 재출혈 예방” 같은 시간·순서 제약을 시나리오화하기 좋습니다. citeturn3search0turn3search4

## 외부 벤치마크·대규모 데이터로 확장성 점검
외부 벤치마크 통합은 “성능이 좋다/나쁘다”만을 위한 것이 아니라, **(1) 파서/정규화가 새로운 데이터 형태에서도 깨지지 않는지**, **(2) 도메인 자동 감지와 모듈형 fallback이 제대로 작동하는지**, **(3) 예산 매칭·공정성 가드가 확장 환경에서도 유지되는지**를 검증하는 목적이 큽니다. citeturn7view3turn7view2turn9view1

현재 의료 에이전트 벤치마크 중, CGA-Bench류(가이드라인 준수·시간/순서·행동 평가)에 특히 유용한 1순위 후보는 다음 세 가지입니다.

AgentClinic은 “정적 의학 QA”를 “임상 환경에서의 에이전트 과제”로 바꿔, 환자와의 대화 및 적극적 정보 수집을 요구하는 오픈소스 벤치마크를 표방합니다. 또한 멀티모달(이미지+대화)과 대화-only 변형(USMLE 기반)으로 구성됩니다. citeturn7view3turn0search4  
이 데이터는 **정보 수집→검사 선택→진단** 형태라서, CGA-Bench의 “상태 추출/행동 정규화/위험 점수” 파이프라인 강건성 테스트에 매우 적합합니다. citeturn7view3turn0search4

MedAgentBench는 의료 기록(EHR) 맥락에서 LLM “에이전트 능력”을 평가하기 위해, **FHIR 호환 인터랙티브 환경에서 300개 임상 과제를 수행**하도록 설계된 벤치마크입니다. citeturn7view2turn0search5turn0search1  
CGA-Bench의 설계 목표 중 “도구 사용/환경 상호작용 + 공정한 예산 매칭”과 결이 맞고, 특히 **FHIR 기반 환경**은 액션을 구조화하는 데 유리합니다. citeturn7view2turn5search6turn5search19

MedChain은 12,163 케이스(19개 specialty, 다단계 workflow)를 포함하고, 개인화·상호작용·순차성을 핵심 특징으로 강조합니다. NeurIPS 2025 Datasets & Benchmarks 트랙 스포트라이트로 공개된 점도 “최신 비교 기준”으로서 가치가 큽니다. citeturn9view0turn9view1turn0search6  
MedChain은 “단계 간 error propagation”을 명시적으로 논의하므로, CGA-Bench의 위반 유형(특히 SEQUENCE/DEVIATION)과 결합했을 때 “순차 의사결정의 안전성 손상”을 더 정교하게 분석할 수 있습니다. citeturn9view0turn9view1

여기에 “규모”를 넣기 위해서는, **Synthea+FHIR** 및 **PhysioNet 계열 EHR/이벤트 로그**를 별도 축으로 쓰는 것이 확장성 검증에 탁월합니다.

Synthea는 현실적이지만 실제가 아닌(synthetic) EHR을 생성하며, 공개 정보 기반·오픈소스라서 “비용/프라이버시 제약이 적다”는 점이 장점으로 명시됩니다. 또한 FHIR 등의 산업 표준 포맷으로 내보내기가 가능합니다. citeturn8view0turn8view2  
즉, Synthea를 사용하면 “대규모 환자군 + 다양한 경로 + 반복 가능한 시드”로 시나리오를 대량 생성하고, CGA-Bench의 시간/순서/금기 규칙이 **스케일업 환경에서 얼마나 안정적으로 도는지**를 체계적으로 측정할 수 있습니다. citeturn8view0turn5search6

PhysioNet의 MIMIC-IV는 응급실/ICU 환자에 대한 대규모 비식별 EHR 데이터셋으로 소개되며, 응급실 모듈(MIMIC-IV-ED)도 별도로 존재합니다. citeturn5search7turn7view1turn5search4  
특히 “이벤트 로그” 관점에서 중요한 것은 MIMIC-IV-ED로부터 추출한 이벤트 로그인 MIMICEL인데, 이 데이터는 7,568,824 events와 425,028 cases 규모로 CSV와 XES 포맷을 제공한다고 명시합니다. citeturn7view0  
CGA-Bench가 XES/OCEL 내보내기를 강조한다면, MIMICEL은 곧바로 **대규모 이벤트 로그 처리·내보내기·재로딩**의 스트레스 테스트로 사용할 수 있습니다. (XES 표준 자체가 “대규모 이벤트 데이터 교환”을 목표로 한다는 점도 정합합니다.) citeturn7view0turn4search4turn4search20

image_group{"layout":"carousel","aspect_ratio":"16:9","query":["AgentClinic benchmark screenshot","MedAgentBench virtual EHR FHIR environment screenshot","Synthea synthetic EHR architecture diagram"],"num_per_query":1}

이 외에 eICU Collaborative Research Database는 20만+ ICU admission 규모의 멀티센터 비식별 중환자 데이터로 소개되며, treatment 정보 등을 포함한다고 설명됩니다. 다만 데이터 사용 계약/접근 절차가 따르는 점이 일반적이므로(즉 공개 재현성에 비용이 생김), “논문 공개 실험”과 “내부 확장성 검증”을 분리해 운영하는 것이 현실적입니다. citeturn5search1turn5search5turn5search15

## 별개의 새로운 벤치마크 제안
기존 도메인 확장과 별개로, “새로운 벤치마크”를 만들 때 NeurIPS Datasets & Benchmarks 관점에서 설득력이 커지는 방향은 **(A) 데이터/평가의 표준성**, **(B) 재현 가능한 파이프라인**, **(C) 기존 벤치마크가 덜 다루는 “가이드라인 준수”의 측정 가능성**을 동시에 만족시키는 것입니다. citeturn6search1turn6search7turn6search0

여기서 CGA-Bench의 강점(시간 제약, 순서 의존, 금기/필수, 위해 기반 점수)을 더 날카롭게 드러낼 수 있는 신규 벤치마크 형태를 두 가지로 제안합니다.

첫 번째 제안은 “CPG-FlowBench(가칭): 이벤트 로그 기반 가이드라인 준수 벤치마크”입니다. 핵심 아이디어는, 환자 케이스를 “QA/대화” 중심이 아니라 **사건(event) 스트림**으로 보고, 에이전트가 “다음 행동”을 선택한 결과가 이벤트 로그로 누적되며, 이를 XES/OCEL로 내보내 분석 가능하게 만드는 것입니다. XES는 IEEE 표준으로 이벤트 스트림 교환을 표준화하고, OCEL 2.0은 객체 중심 이벤트 로그로 관계/상태 변화를 더 풍부하게 담도록 확장된 표준이라는 점에서, “로그-기반 준수 평가” 벤치마크의 포맷 정당성이 높습니다. citeturn4search4turn4search20turn4search5turn4search13  
데이터 소스로는 (1) 공개 재현성 우선이면 Synthea(FHIR 기반 synthetic EHR), (2) 현실성/스케일 우선이면 MIMICEL(XES 포함 대규모 ED 이벤트 로그)을 고려할 수 있습니다. citeturn8view0turn7view0

두 번째 제안은 “Guideline-to-Actions Bench(가칭): 가이드라인 기반 행동 집합/제약 합성(semantic layer) 벤치마크”입니다. AgentClinic/MedAgentBench/MedChain이 “에이전트 과제 수행”을 강조한다면, 이 벤치는 그 이전 단계인 **(i) 가이드라인 텍스트→(ii) 행동 온톨로지/제약(필수/금기/시간/순서)→(iii) 평가 가능한 스펙**으로의 변환 품질을 측정합니다. AgentClinic가 정적 QA의 한계를 지적하고, MedAgentBench가 FHIR 환경에서의 도구 상호작용을 요구하며, MedChain이 순차·상호작용·개인화를 강조하는 흐름을 고려하면, “가이드라인 스펙 합성 자체”를 독립 평가하는 벤치는 상보적인 기여가 됩니다. citeturn7view3turn7view2turn9view0  
이때 Declare 계열(선언형 제약)과 같은 “제약 템플릿 기반 모델링”을 사용하면, CPG의 시간/순서/선행조건을 규칙 템플릿으로 표현하고 적합성(conformance)을 검사할 수 있습니다. Declare는 제약 템플릿을 기반으로 선언형 프로세스를 모델링하는 접근으로 소개되어 왔습니다. citeturn4search34turn4search2turn4search26

두 제안 모두 NeurIPS Datasets & Benchmarks 트랙 요구에 맞추려면, **데이터 접근/호스팅/버전/메타데이터**가 중요합니다. NeurIPS D&B 트랙은 데이터 호스팅 가이드에서 “Croissant 형태의 기계 판독 메타데이터” 등을 요구하는 방향을 명시하고 있습니다. citeturn6search7turn6search1  
따라서 벤치마크의 최소 공개 버전(MVP)은 (a) 누구나 접근 가능한 소스(Synthea 기반)로 구성하고, (b) 현실성 확장 버전은 MIMIC/eICU 등 “승인 기반 데이터”로 별도 트랙을 두는 “2단 공개 전략”이 논문화에 유리합니다. citeturn8view0turn5search7turn5search5

마지막으로, 문서 상의 참고문헌 정확성은 벤치마크 신뢰도에 직접 연결됩니다. 예컨대 “dc24-S015”는 ADA Standards of Care 2024에서 **임신 중 당뇨 관리(Management of Diabetes in Pregnancy)** 섹션의 PDF로 연결되는 경우가 대표적입니다. DKA/HHS는 같은 연도 스탠더드 내 “Diabetes Care in the Hospital” 섹션이나 별도 컨센서스 보고서에서 직접적으로 다룹니다. 따라서 DKA 그래프의 출처 표기는 “관련 섹션/컨센서스 문서”로 정정하는 것이 안전합니다. citeturn1search3turn2search3turn2search23

## NeurIPS 제출용 실험 확장 패키지
학술 제출(특히 NeurIPS)을 목표로 할 때, 실험 확장은 “모델을 많이 돌렸다”보다 **실험 설계가 기여점을 분리해 보여주는가**가 더 중요합니다. 또한 NeurIPS는 제출 체크리스트/코드·데이터 정책을 통해 재현 경로를 요구합니다. citeturn6search0turn6search4  
그리고 Datasets & Benchmarks 트랙은 데이터/벤치마크 논문 특성상 (1) 단일/이중 블라인드 옵션, (2) 데이터 호스팅·메타데이터, (3) 리뷰 기준의 차이를 별도로 안내합니다. citeturn6search1turn6search7

실험 패키지는 다음 4개 블록으로 구성하면 “논문 구조” 자체가 자연스럽게 나옵니다.

첫째, **베이스라인과 상한/하한 설정**. 최소한 (a) 규칙 기반(Oracle류), (b) 텍스트 기반 strong baseline(예: RAG), (c) 계획/반성/멀티에이전트 변형, (d) 외부 벤치마크 표준 설정(AgentClinic/MedAgentBench/MedChain에서 제공하는 대표 설정)을 포함시키는 것이 좋습니다. 이 구성은 의료 에이전트 벤치마크들이 “정적 QA 대비 에이전트 과제에서의 성능 저하/변동성”을 반복적으로 관찰한다는 점을 정면으로 다룹니다. citeturn7view3turn7view2turn9view0

둘째, **기여점 분리(ablation) 설계**. CGA-Bench류에서 논문 기여로 설득력 있는 축은 대체로 (1) 시간 제약/순서 의존 위반 감지의 유효성, (2) 위해 기반 위험 점수의 유용성, (3) DualTrack(행동 커버리지 vs 가이드라인 준수)의 분리 효과, (4) 공정성 가드(overspecific/fallback)의 필요성입니다. 특히 MedChain이 sequentiality·interactivity 제거/유지 ablation으로 난이도·현실성을 논증한 것처럼, “시간/순서/금기/위험 점수” 각각을 제거/완화했을 때 평가가 어떻게 무뎌지는지 보여주면 설득력이 커집니다. citeturn9view0turn9view1

셋째, **확장성 실험(스케일 축)과 병목 분석**. 여기서는 “새 데이터셋에서 점수 분포가 나온다”가 아니라, 다음을 계량화하는 것이 중요합니다.
- 데이터 스케일: 시나리오 수, 에피소드 길이, 이벤트 수가 커질 때 처리량/지연이 어떻게 변하는지(예: MIMICEL의 수백만 이벤트 규모는 스트레스 테스트에 충분히 크다고 명시). citeturn7view0  
- 포맷 스케일: XES/OCEL 내보내기 및 재로딩이 표준에 맞게 동작하고(교환/저장/분석 목적), 큰 로그에서 실패하지 않는지. citeturn4search4turn4search20turn4search5  
- 환경 스케일: FHIR 기반 환경(예: MedAgentBench)처럼 도구/리소스 호출이 늘어날 때 예산 매칭이 유지되는지. citeturn7view2turn5search6turn5search19

넷째, **임상의 정렬(clinician alignment)·위험 점수의 해석 가능성**. 문서에 3-way safety 분류와 κ(코헨 카파) 등이 언급되어 있다면, 최소한 “두 명 평가자” 상황에서 κ를 보고하거나, “다수 평가자” 상황에서는 Fleiss κ 등으로 확장할 수 있습니다. κ는 범주형 라벨의 평가자 일치도를 측정하는 통계로 널리 쓰이며, 바이오메디컬 문헌에서는 해석 가이드(예: 0.61–0.80 substantial 등)를 소개한 리뷰도 존재합니다. citeturn4search7turn4search3  
이 블록은 “점수가 임상적 위해(unsafe)와 실제로 정렬되는가?”를 보여주므로, 위해 기반 스코어링의 핵심 기여점을 강화합니다. citeturn4search7

NeurIPS 제출 실무 관점에서는, (a) 설치/실행 커맨드와 환경(의존성·버전), (b) 데이터 접근/준비 절차, (c) 익명 코드/데이터 제출 규칙(제출 시 zip/익명 URL 등), (d) D&B 트랙이라면 Croissant 메타데이터 및 호스팅 가이드 준수까지를 “부록/레포지토리”로 고정해두는 것이 좋습니다. citeturn6search0turn6search4turn6search7

**Q1**  **기존 6개 도메인(Sepsis/Chest pain/Stroke/HF/AKI/DKA) 중에서 “위반 유형 분포가 가장 불균형한 도메인”을 어떻게 계량화하고, 그 불균형을 줄이기 위한 시나리오 생성 규칙을 어떻게 설계하면 좋을까?**  

**Q2**  **Synthea(FHIR 기반 synthetic EHR)로 대규모 시나리오를 만들 때, “가이드라인 준수 평가에 필요한 시간·순서·금기 근거”를 데이터 생성 단계에서 어떻게 주입해야 추후 라벨 정합성(ground truth)이 흔들리지 않을까?**  

**Q3**  **NeurIPS Datasets & Benchmarks 트랙 기준에서, ‘새 벤치마크’의 핵심 기여를 DualTrack(커버리지×준수)+위해 점수로 잡을지, 아니면 XES/OCEL·Declare 기반의 “프로세스 마이닝 친화적 평가 표준화”로 잡을지—두 방향의 비교 실험을 어떻게 구성하면 가장 설득력 있을까?**