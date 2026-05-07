# 실험 결과 교차 검증 Prompts

> main.tex 수정 전에 반드시 수행. 순서대로.

---

## 🔴 V0. Constraint Count 진실 확인 (최우선, 2시간)

```
P0 결과에서 논문과 실제 YAML 사이에 큰 차이가 발견됐다.
이것이 downstream 수치에 어떤 영향을 주는지 완전히 추적해줘.

1. YAML에서 constraint를 직접 세줘:
   - 각 scenario별, constraint type별 (FORBIDDEN, WITHIN, BEFORE, MUST, SHOULD_WITHIN)
   - scenario 간 중복이 있는지 (같은 constraint가 여러 scenario에 등장?)
   - unique constraint vs scenario-instance constraint 구분

2. evaluation pipeline 코드를 열어서 실제로 어떤 constraint를 사용하는지 확인:
   - C3 계산 시 FORBIDDEN 몇 개를 denominator로 쓰는가?
   - C4 계산 시 WITHIN 몇 개를 denominator로 쓰는가?
   - C5 계산 시 BEFORE 몇 개를 denominator로 쓰는가?
   - HardViol 판정 시 FORBIDDEN + WITHIN + BEFORE 전부를 보는가,
     아니면 WITHIN만 보는가?

3. 논문의 "92"가 정확히 어디서 나온 숫자인지 추적:
   - WITHIN만 센 것인가?
   - unique constraint만 센 것인가?
   - 특정 evidence level만 센 것인가?

4. "112 total = 92 hard + 20 soft"라는 논문 서술과
   실제 230 hard + 1128 soft의 관계를 설명해줘.
   가능한 해석:
   (a) 92 = WITHIN만, 논문이 FORBIDDEN/BEFORE를 hard에서 누락
   (b) 92 = unique constraint types, 230 = scenario-instance 전개
   (c) 논문이 쓴 숫자가 오래된 버전의 YAML 기준

5. 이 차이가 기존 실험 결과에 영향을 주는지 확인:
   - C3, C4, C5 값이 바뀌는가?
   - HardViol 판정이 바뀌는 episode가 있는가?
   - UP_strong이 바뀌는가?

6. 정확한 숫자를 확정해서 출력:
   - "논문에서 써야 하는 정확한 constraint count" 확정
   - 필요시 evaluation pipeline 수정

YAML 파일 경로: [경로]
evaluation pipeline 코드: [경로]
기존 episode 결과: [경로]
```

---

## 🔴 V1. DxEM 100% Pass 검증 (1시간)

```
P1C에서 DxEM이 180/180 pass (0 fail)로 나왔다.
이건 4B 모델까지 포함해서 진단 정확도 100%라는 뜻인데,
현실적이지 않다. 원인을 찾아줘.

1. DxEM 구현 코드를 열어서 확인:
   - gold diagnosis는 어디서 가져오는가?
   - agent의 "최종 진단"은 어떻게 추출하는가?
   - matching 로직: exact string match? fuzzy? contains?
   - threshold가 있는가?

2. 실제 episode 5개를 수동 검증:
   - 4B 모델의 episode 2개 + 120B 모델의 episode 2개 + 35B 1개
   - 각 episode에서:
     * agent의 실제 마지막 발화 전문
     * 거기서 추출된 "최종 진단"
     * gold diagnosis
     * DxEM이 이 둘을 match라고 판단한 이유

3. 가능한 문제 원인 확인:
   (a) agent가 scenario의 presenting complaint를 그대로 반복
       (예: "DKA"라고 scenario에 써있고 agent도 "DKA"라고 말함
       → scenario 자체가 진단을 줬기 때문에 당연히 match)
   (b) matching이 너무 관대 (substring match 등)
   (c) gold diagnosis가 너무 넓음 (예: "diabetic ketoacidosis"만 있으면
       "the patient has DKA"도 pass)
   (d) 진단 추출 로직이 scenario description에서 진단을 가져옴
       (agent output이 아니라)

4. 만약 DxEM이 구조적으로 100% pass할 수밖에 없다면:
   - 이유를 문서화 (예: "scenario가 이미 진단을 제공하므로
     모든 agent가 진단을 올바르게 반복한다")
   - 이 경우 DxEM의 의미를 논문에서 어떻게 써야 하는지 제안
   - "DxEM 100% pass는 terminal-output evaluator의 한계가 아니라
     scenario design의 특성이다"라는 해석이 맞는지 판단

5. 만약 DxEM 구현에 버그가 있다면:
   - 수정 후 재실행
   - 수정된 verdict matrix 출력

출력: v1_dxem_verification.md
DxEM 코드: [경로]
episode 데이터: [경로]
```

---

## 🔴 V2. CGA-Bench Sensitivity/Specificity = 1.0 검증 (30분)

```
P1C에서 CGA-Bench의 sensitivity=1.0, specificity=1.0이 나왔다.
이게 tautological인지 확인해줘.

1. P1C에서 "ground truth"로 사용한 것이 무엇인지 확인:
   - HardViol 자체를 ground truth로 쓴 건 아닌지?
   - 만약 HardViol = ground truth이고 CGA-Bench = HardViol이면
     당연히 sensitivity=specificity=1.0이다
   - 이건 "CGA-Bench가 완벽하다"가 아니라 "자기 자신과 비교했다"

2. 맞다면:
   - 이 숫자를 논문에 쓰면 안 된다
   - verdict matrix에서 CGA-Bench 행의 sensitivity/specificity를
     제거하거나, "reference (by definition)"으로 표기

3. 진짜 sensitivity/specificity를 구하려면:
   - 외부 ground truth (clinician judgment)가 필요
   - 이건 P3 (clinician study)의 결과
   - P3 전까지는 CGA-Bench를 "reference evaluator"로만 쓰고
     sensitivity/specificity는 claim하지 않는다

출력: v2_tautology_check.md
P1C 코드: [경로]
```

---

## 🔴 V3. UP_STRONG 숫자 일관성 확인 (1시간)

```
여러 실험에서 UP_STRONG 관련 숫자가 다르게 보인다. 추적해줘.

1. 논문의 UP_STRONG = 34.6% (27/78)
   - 78 = completion-passing (C2 >= 0.7)
   - 27 = 그 중 guideline-strong hard violation
   - 이 27이 정확한지 episode ID로 확인

2. P8의 Core UP_STRONG = 73.3% (44/60)
   - 60 = core completion-passing
   - 44 = 그 중 guideline-strong hard violation
   - 그런데 78개 중 core completion-passing이 60이면
     expansion completion-passing은 18개
   - expansion UP_STRONG = 52.4%면 expansion에서도 ~9개
   - 44 + 9 = 53인데, 전체는 27?
   → 숫자가 안 맞음. 확인 필요.

3. 가능한 원인:
   (a) P8의 "UP_STRONG" 정의가 논문과 다름
       (예: P8은 any hard violation, 논문은 guideline-strong만)
   (b) P8의 completion-passing threshold가 다름
   (c) P8의 "core"가 9개 scenario인데 논문은 8개 core로 알고 있었음

4. "guideline-strong"의 정의를 코드에서 확인:
   - 어떤 constraint가 "strong"으로 분류되는가?
   - evidence level field가 YAML에 있는가?
   - 코드가 이 field를 실제로 사용하는가?

5. V0의 constraint count 결과와 교차:
   - 230 hard constraints 중 "guideline-strong"은 몇 개?
   - 이 숫자가 UP_STRONG 계산에 맞는지

출력: v3_upstrong_reconciliation.md
```

---

## 🔴 V4. P7 Forbidden Count 불일치 (30분)

```
P0: FORBIDDEN = 109
P7: 총 135 forbidden constraints (130 zero + 2 triggered + 4 mand-cond = 136?)

1. 109 vs 135의 차이 원인 추적:
   - P0과 P7이 같은 YAML을 읽는가?
   - P0은 unique constraint, P7은 scenario-instance인가?
   - P7의 135가 어디서 나온 숫자인지 코드에서 확인

2. P7의 합계 확인:
   130 + 2 + 4 + 1 = 137인데 135라고 한 이유

3. 정확한 forbidden constraint count 확정

출력: v4_forbidden_reconciliation.md
```

---

## 🟠 V5. AgentClinic Scorer 충실도 확인 (1시간)

```
P1A에서 AgentClinic 방식으로 52% mis-cert가 나왔다.
이 scorer가 실제 AgentClinic의 evaluation을 충실히 재현하는지 확인해줘.

1. P1A 코드의 scorer 로직을 AgentClinic 원논문/코드와 비교:
   - AgentClinic이 실제로 어떤 필드를 보는가?
   - 우리 reconstruction이 빠뜨린 것은 없는가?
   - pass/fail threshold는 같은가?

2. AgentClinic의 실제 코드가 공개되어 있다면:
   - 우리 reconstruction과 line-by-line 비교
   - 차이점 문서화

3. AgentClinic 코드가 비공개라면:
   - 논문에서 서술된 evaluation protocol 기반으로 reconstruction
   - 논문에 "reconstructed following the published protocol"이라고
     명시해야 함
   - "faithful reconstruction"이라고 쓸 수 있는지 판단

4. 동일하게 MedAgentBench F1 scorer도 확인

출력: v5_scorer_fidelity.md
```

---

## 🟠 V6. LLM Second Encoder (encoding validity 대안) (3시간)

```
Second encoder가 없으므로, LLM을 second encoder로 사용해서
encoding validity를 최소한이라도 확보해줘.

1. 대상: 6개 domain에서 각 1개 scenario = 6개 scenario
   해당 scenario의 hard constraint 전체

2. GPT-4o에게 아래를 제공:
   - CPG 원문 해당 섹션 (우리가 constraint 추출에 사용한 것과 동일)
   - Patient presenting state
   - 빈 template:
     "이 가이드라인에서 이 환자에게 적용되는 clinical constraints를
      아래 형식으로 추출하세요:
      - Action: [action name]
      - Type: FORBIDDEN / WITHIN / BEFORE / MUST
      - Condition: [when this applies]
      - Deadline: [if timing, in minutes]
      - Hard/Soft: [hard = violation is clinically dangerous,
                     soft = suboptimal but not dangerous]
      - Evidence: [guideline evidence level if stated]"

3. GPT-4o의 output과 우리 constraint를 비교:
   - action identity match (fuzzy, threshold 0.7)
   - constraint type agreement
   - hard/soft agreement
   - deadline agreement (±15분)

4. Cohen's kappa 또는 percent agreement 계산

5. 결과 해석:
   - agreement > 0.7이면: "LLM-based second encoding shows
     substantial agreement, supporting encoding reproducibility"
   - agreement < 0.5이면: 우리 encoding이 idiosyncratic할 수 있음
     → limitation으로 더 강하게 써야 함

6. 논문에 쓸 문장:
   "As a proxy for independent human encoding, we used GPT-4o as
    a second encoder on {} scenarios ({} constraints).
    Agreement: action identity {}\%, constraint type κ={},
    hard/soft κ={}, deadline (±15min) {}\%.
    This provides preliminary evidence for encoding reproducibility;
    independent human validation is planned."

출력:
  - encoding_audit/llm_encoder_output/ (scenario별)
  - encoding_audit/agreement_analysis.md
  - encoding_audit/paper_text.md

CPG 문서: [경로]
scenario 정의: [경로]
constraint 정의: [경로]
```

---

## 🟠 V7. Normalizer Hard-Constraint Impact (1시간)

```
normalizer의 8개 miss가 hard constraint에 영향을 주는지
직접 확인해줘. 이건 논문의 scoring reliability 핵심.

1. 8개 miss를 전부 나열 (appendix에서 추출)

2. 각 miss에 대해:
   - 이 action이 어떤 constraint에 참조되는가?
   - FORBIDDEN? WITHIN? BEFORE? MUST?
   - hard constraint에 참조되면: 어느 scenario, 어느 episode에서?

3. miss를 수정한 normalizer로 전체 180 episode 재평가:
   - C3, C4, C5 값 변화
   - HardViol 판정 변화 episode 수
   - UP_strong 변화

4. hard-constraint-linked action 전체에 대한 normalizer accuracy:
   - hard constraint에 참조되는 unique action 목록
   - 이 action들의 normalization 정확도 (별도 P/R/F1)

출력: normalizer_audit/hard_constraint_impact.md
```

---

## 실행 순서

```
즉시 (병렬):
  V0: Constraint count 진실 확인 ← 모든 것의 기반
  V1: DxEM 100% pass 검증

V0 완료 후:
  V3: UP_STRONG 숫자 일관성
  V4: Forbidden count 불일치

V1 완료 후:
  V2: CGA-Bench sensitivity/specificity tautology

이후:
  V5: AgentClinic scorer 충실도
  V6: LLM second encoder
  V7: Normalizer hard-constraint impact

모든 검증 완료 후:
  → 확정된 숫자로 main.tex 최종 수정
```

---

## Second Encoder 전략 요약

| 방법 | 노력 | 신뢰도 | 추천 |
|------|------|--------|------|
| LLM second encoder (V6) | 3시간 | 중 | ✅ 지금 하기 |
| 본인 시간차 재인코딩 | 2일 | 중-하 | ⚠️ 시간 있으면 |
| 독립 clinician | 1-2주 | 상 | ✅ P3와 병행 |
| 안 함 + limitation 명시 | 0 | 하 | 🔻 최후 수단 |

추천 조합: **V6(LLM) 지금 + limitation에 "human validation planned" 명시**
→ camera-ready에서 clinician encoding audit 추가 가능