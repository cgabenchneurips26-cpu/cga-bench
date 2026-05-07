데이터셋별 구현 가이드
2-1. AMEGA

AMEGA의 공개 HF dataset card는 evaluation-only를 명시하고, cases, questions, sections, criteria 네 구성으로 데이터를 노출합니다. 같은 공개 소스 안에서도 수치가 일치하지 않는데, HF card는 20개 case / 1,337 criteria, GitHub README는 24개 scenario / 163 questions / 1,497 criteria라고 설명합니다. 따라서 어댑터는 반드시 특정 artifact/commit/hash를 manifest로 고정해야 합니다.

구현은 질문 단위(question-level) 로 끊는 게 맞습니다.
한 case에 여러 question과 weighted criterion이 매달릴 수 있으니, case를 하나의 episode로 뭉개지 말고:

case narrative → input_text

question → task prompt

criteria/sections → checklist와 weighted rubric

guideline metadata가 있으면 provenance에 저장

이렇게 나누세요.

어댑터에서 특히 주의할 점은, criteria를 바로 CGA action으로 간주하면 안 된다는 것입니다. AMEGA rubric에는 “언급했는가 / 설명했는가 / 판단했는가” 유형도 섞일 수 있으므로, 먼저 criteria를 아래 셋으로 분류해야 합니다.

행동(action): 검사 시행, 약물 투여, 처치, referral

판단(state/assessment): differential, 위험 판단, contraindication 인식

설명(explanation): rationale, patient counseling

CGA-Bench의 Track A/Track B에 직접 들어가는 것은 주로 첫 번째이고, 두 번째는 working_diagnosis 또는 clinical_state_extractor에, 세 번째는 native rubric 보조지표로 남기는 편이 좋습니다.

CPG 평가 가능성은 중간입니다.
AMEGA는 guideline adherence benchmark지만, 공개 형태는 open-ended QA + rubric에 가깝기 때문에 C1/C2/C3는 derived 방식으로 가능하고, C4/C5는 case 안에 명시적 시간·순서가 있을 때만 켜는 것이 안전합니다. 즉, AMEGA는 derived_track_b 또는 보수적으로 track_a_only + selective Track B가 맞습니다.

2-2. CliBench

CliBench는 MIMIC-IV와 MIMIC-IV-Note 원천 파일, 그리고 별도 ndc_metadata.json을 사용하며, README에 patients, admissions, procedures_icd, prescriptions, diagnoses_icd, labevents, note 파일들을 내려받아 전처리하는 절차가 공개돼 있습니다. 추론 스크립트는 실제 target을 target_diagnoses, target_procedures, target_laborders, target_prescriptions로 다루고, 입력은 환자 정보 + discharge note + radiology note + lab events를 합쳐 구성합니다. 또한 논문/오픈리뷰 설명상 procedure는 ICD-10-PCS, lab order는 LOINC, prescription은 ATC에 맞춘 구조를 전제로 합니다.

이 데이터셋은 CGA-Bench와 가장 잘 맞는 action-centric benchmark입니다. 다만 구현에서 가장 중요한 건 진단과 오더를 같은 액션 타입으로 취급하지 않는 것입니다.

권장 namespace는 아래처럼 분리하세요.

dx/icd10cm:*

proc/icd10pcs:*

lab/loinc:* 또는 lab/name:*

med/atc:* 또는 med/name:*

그리고 target_diagnoses는 strict하게 “행동”이라기보다 path selection / working diagnosis state에 가깝기 때문에, harm weight를 약물·검사 오더와 동일하게 주는 것은 피하는 게 좋습니다.

어댑터는 보통 이렇게 갑니다.

원 전처리 결과를 읽어 CanonicalCase 생성

task별로 domain route 결정

diagnosis: chest pain / sepsis / aki / dka 등 routing

procedure/lab/med: 더 직접적인 action task

gold code/name을 action_normalizer로 canonical action ID에 매핑

agent 출력도 동일 normalizer로 변환

Track A 계산

해당 도메인에 내부 CPG graph가 있을 때만 Track B 계산

CPG 평가 가능성은 부분적으로 강함입니다.
procedure/lab/prescription은 Action으로 직접 들어오기 때문에 Track A가 강하고, 특정 도메인에 대해 내부 CPG graph를 붙이면 Track B도 의미가 있습니다. 반면 diagnosis task는 “정답 코드 매칭” 성격이 강해서, 그대로 CGA 위반으로 재해석하면 과벌점이 생길 수 있습니다. 따라서 CliBench는 task별 분리 평가가 맞습니다.

procedure/lab/med: derived_track_b

diagnosis: track_a_only 또는 state-aware derived scoring

그리고 법적/운영 제약이 가장 큽니다. MIMIC 계열은 credentialed data이고, PhysioNet은 현재 제3자 API나 온라인 플랫폼으로 데이터를 보내는 것을 금지한다고 명시합니다. 또 MIMIC 파생 데이터/모델도 민감 정보로 취급하고 원 데이터와 같은 agreement 하에서 공유하라고 안내합니다. 따라서 CliBench adapter 실험은 로컬 또는 온프렘 inference 전용으로 설계하는 게 안전합니다.

2-3. MedGUIDE

MedGUIDE는 논문 기준 55개 NCCN decision tree, 17개 cancer type, 7,747개 high-quality sample로 만들어진 oncology guideline benchmark입니다. 공개 HF dataset 예시 필드는 profile, prompt, options, answer, answer_text, path, disease, 그리고 여러 quality criterion 점수입니다. 즉, 한 row가 “환자 케이스 + 선택지 + 정답 leaf + gold decision path” 구조를 갖습니다.

이건 CGA-Bench에 붙이기 아주 좋습니다. 이유는 path가 있기 때문입니다.
구현은 아래 방식이 가장 자연스럽습니다.

profile → input_text

prompt → 모델 질의

options → candidate leaf nodes

answer_text → gold composite action 또는 recommended plan

path → intermediate mandatory decision steps

disease → domain router / graph selector

그리고 path를 그냥 문자열로 두지 말고, 내부에서 다음처럼 분해하세요.

def medguide_path_to_expectations(path_nodes):
    expected = []
    for node in path_nodes[:-1]:
        expected.append(ExpectedAction(
            action_id=f"onc_decision/{slug(node)}",
            kind="mandatory",
            provenance="medguide:path"
        ))
    expected.append(ExpectedAction(
        action_id=f"onc_plan/{slug(path_nodes[-1])}",
        kind="mandatory",
        provenance="medguide:leaf"
    ))
    return expected

다만 중요한 제약이 있습니다. MedGUIDE는 single-turn MCQ에 가깝기 때문에, 보통은 C1/C2는 강하게, C3는 contraindication option이 있을 때만, C4/C5는 대체로 끄는 쪽이 맞습니다. 즉 “decision-tree adherence”는 잘 보지만, “real workflow timing/sequence”는 약합니다.

CPG 평가 가능성은 중상입니다.
oncology domain graph만 추가하면 derived_track_b로 매우 잘 들어갑니다. 다만 NCCN 기반이므로, NCCN 알고리즘/도식/문구의 재현과 배포는 permission 이슈를 먼저 확인해야 합니다. NCCN은 현재 content를 사용·재현·배포하려면 permission request를 안내하고 있고, 가이드라인 관련 material 재사용도 NCCN 직접 승인을 요구합니다. 따라서 내부 graph에는 verbatim guideline text 대신 node ID, provenance, citation pointer만 저장하는 방식이 안전합니다.

2-4. CancerGUIDE

CancerGUIDE 논문은 NSCLC longitudinal case 121개를 board-certified oncologist가 NCCN trajectory로 주석한 dataset을 제시합니다. 그런데 공개 HF 릴리스는 synthetic_structured / synthetic_unstructured 두 JSON이며, 필드는 patient_id, patient_note, label이고 각각 165개 / 151개 row로 설명됩니다. HF card는 이 릴리스가 GPT-4.1로 생성한 synthetic case라고 명시합니다. 즉, 공개 릴리스는 논문이 말하는 expert-annotated 121-case longitudinal artifact와 동일한 형태가 아닌 것으로 보입니다.

그래서 구현 전략을 둘로 나눠야 합니다.

공개 synthetic release만 쓸 때

patient_note → input_text

label → gold recommended treatment

task_type = longitudinal_text가 아니라 사실상 open_qa 또는 label_prediction

eval_mode = track_a_only 또는 약한 derived_track_b

이 경우는 trajectory benchmark가 아니라 note→treatment label benchmark에 더 가깝습니다.

논문 수준의 expert longitudinal dataset에 접근 가능할 때

encounter, diagnostic result, prior therapy, progression event를 timeline_events로 복원

NSCLC-specific CPG graph를 구축

line of therapy, resection/adjuvant/systemic therapy 분기를 node로 설계

TIMING/SEQUENCE까지 평가 가능

즉 진짜 강한 CPG 평가는 private/full expert resource가 있을 때 가능합니다.
공개 synthetic release는 oncology graph와 action normalizer를 빠르게 smoke-test하는 용도로는 좋지만, trajectory fidelity 검증용으로는 부족합니다.

CPG 평가 가능성은

공개 HF synthetic: 중간 이하

논문형 full longitudinal set: 강함

입니다. 이 차이를 README와 experiment config에 명확히 써두는 게 좋습니다.

2-5. MTBBench

MTBBench는 제목 그대로 multimodal sequential clinical decision-making benchmark in oncology이며, 논문은 MTB 환경에서의 multimodal + longitudinal oncology reasoning을 핵심으로 둡니다. 공개 자료에 따르면 benchmark 데이터는 두 개의 JSON 파일과 환자별 folder로 구성되고, HANCOCK cohort는 pathology/TMA 계열, MSK-CHORD는 longitudinal genomic profile 계열이며, 추가로 DrugBank API 구성도 필요합니다. HF dataset card는 1,012 rows와 약 1.4GB 규모를 보여줍니다.

이 데이터셋은 현재 CGA-Bench에 바로 붙이기엔 가장 공수가 큽니다.
기존 구조 기준으로는 다음 확장이 먼저 필요합니다.

tool_api에 pathology/genomics/drug lookup wrapper 추가

env/adapters/mtbbench_adapter.py에서 multimodal asset loader 구현

Observation에 이미지/보고서/시계열 분자정보 포인터 추가

oncology MTB용 graph 구축

long-horizon step loop 정의

즉, MTBBench는 semantic_layer/external/*만으로는 부족하고 env/adapters/* + tool_api/* + oncology CPG graph가 모두 필요합니다.

CPG 평가 가능성은 잠재적으로 매우 높습니다.
multimodal과 longitudinal을 모두 포함하므로, 제대로 붙이면 C1~C5를 가장 풍부하게 볼 수 있습니다. 대신 첫 구현에서는 다음 원칙이 중요합니다.

이미지/유전체 자체를 scorer에 직접 넣지 말고, agent가 사용한 tool result를 event log로 남겨서 평가

timing은 “real-world clock”가 아니라 encounter sequence / tumor board step order로 모델링

DrugBank 같은 외부 도구 호출은 reproducibility를 위해 snapshot 필요

실무 순서상으로는 마지막 단계가 맞습니다.

2-6. EHRStruct

EHRStruct는 논문 기준 11개 representative task, 2,200개 sample을 두 개의 widely used EHR dataset에서 만들었고, 공개 repo는 aggregation, arithmetic, death, disorder, filter, medications, snomed 폴더 아래 sample_001.csv–sample_100.csv와 query_answer_*.csv들을 둡니다. README는 source로 Synthea와 eICU를 사용한다고 설명하고, 라이선스는 CC BY-NC 4.0입니다.

이 벤치마크는 “CPG adherence” 그 자체보다는 structured EHR reasoning benchmark입니다.
그래서 CGA-Bench에서는 main benchmark가 아니라 입력 파서·상태 추출기·front-end robustness suite로 두는 것이 맞습니다.

권장 역할은 이렇습니다.

clinical_state_extractor가 structured table을 잘 읽는지

state_reducer가 structured field를 canonical state로 바꾸는지

action_normalizer 이전 단계의 observation builder가 튼튼한지

즉, EHRStruct는 track_a_only조차 억지일 수 있고, 대부분은 CPG 평가용이 아니라 input-generalization test로 보는 편이 공정합니다.

또 source가 Synthea(합성, 자유 사용)와 eICU(credentialed access)가 섞여 있으므로, adapter manifest에 source provenance를 반드시 남기세요. Synthea는 synthetic data로 legal/privacy restriction 없이 쓸 수 있다고 안내하지만, eICU는 credentialed access가 필요합니다. 따라서 open split와 restricted split를 물리적으로 분리하는 편이 안전합니다.

2-7. LLMEval-Med

LLMEval-Med 논문은 2,996 questions와 expert-developed checklist 기반 자동 평가를 설명합니다. 그런데 공개 GitHub repo의 dataset/dataset.json은 667 medical questions로 설명되고, 각 row는 category1, category2, scene, round, problem, groupCode, sanswer, difficulty, checklist를 가집니다. 즉, 논문 버전과 공개 릴리스 사이에 규모 차이가 있으므로, 이것도 manifest pinning이 필수입니다.

이 데이터셋은 checklist가 있다는 점이 CGA-Bench와 잘 맞습니다.
다만 checklist의 내용이 모두 “행동”은 아닙니다. 따라서 아래처럼 먼저 필터링하세요.

Medical Reasoning, Medical Ethics and Safety, 일부 clinical scene
→ expected_actions, forbidden_actions, safety_checks로 변환 가능

Medical Knowledge, Text Generation
→ native checklist score 위주, CGA action score로는 부적합한 경우 많음

구현 포인트는 다음입니다.

scene, category2로 clinical scenario만 필터

checklist를 clause 단위로 쪼개기

clause를 action / state recognition / explanation으로 분류

action만 Track A 후보에 넣고, safety clause는 forbidden avoidance로 별도 저장

category별 native judge score와 CGA score를 함께 보고

CPG 평가 가능성은 부분적입니다.
LLMEval-Med 전체를 CGA로 재채점하는 건 무리이고, **clinical scene subset만 골라 derived_track_b 또는 track_a_only**로 쓰는 것이 맞습니다. 특히 round가 있어도 multi-turn clinical workflow를 의미하지 않는 경우가 많으니, sequence를 자동으로 켜면 안 됩니다.

2-8. NICE silver-standard dataset

이 데이터셋의 논문 초록은 publicly available NICE guidelines across multiple diagnoses에서 만든 validated silver-standard dataset이라고 설명하고, realistic patient scenario와 clinical question을 포함한다고 말합니다. 공개 GitHub repo는 현재 triplets.csv와 appendix PDF를 포함합니다. NICE는 현재 재사용 정책에서 UK 내 reuse는 Open Content Licence, international reuse는 개인 연구·학습 목적 외에는 fee와 licensing agreement 대상이라고 안내합니다.

이 후보는 새 public-domain CPG graph를 싸게 늘리는 데 가장 실용적입니다.
다만 제가 지금 확인한 공개 repo 레벨에서는 triplets.csv의 구체적인 column schema를 확정하지 않았으므로, 어댑터를 하드코딩하지 말고 초기 import 단계에서 schema introspection을 넣는 게 좋습니다.

예를 들면:

def inspect_triplets_schema(df):
    cols = set(df.columns)
    # 예: scenario / question / answer / guideline_ref / diagnosis ...
    # 실제 컬럼명을 보고 매핑
    return cols

구현은 보통 아래 순서가 좋습니다.

triplets.csv에서 scenario/question/answer/guideline reference 분리

NICE guideline identifier를 source_guideline으로 저장

질환별로 소형 CPG graph 생성

silver label은 confidence < 1.0으로 기록

Track B는 derived로 계산하되, gold와 rule이 충돌하면 native score도 같이 보고

CPG 평가 가능성은 중상입니다.
NICE가 공개 guideline 기반이라 graph bootstrap이 쉽고 multi-diagnosis 확장성이 좋습니다. 다만 silver-standard라서 hard failure benchmark가 아니라 graph expansion benchmark로 보는 편이 더 정확합니다. 그리고 한국에서 제품/서비스에 넣는 형태라면 NICE의 international reuse 조건을 꼭 검토해야 합니다.