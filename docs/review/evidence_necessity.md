cga_bench의 존재 이유(necessity)를 실증하는 before/after 증거를 만들어라.

핵심 질문: "기존 벤치마크 점수만으로는 놓치는 임상적 오류를 CGA-Bench가 포착하는가?"

Part A: 내부 시나리오에서 증거 수집

1. 72 에피소드 (3모델 × 8시나리오 × 3회)에서 다음 케이스를 찾아라:
   - "C2(mandatory completion)=100%이지만 C4(timing)가 낮은 케이스"
     → "뭘 해야 하는지는 알지만 언제 해야 하는지는 모른다"
   - "C1(path selection)이 높지만 C5(sequence)가 낮은 케이스"
     → "올바른 행동을 선택했지만 순서가 틀렸다"
   - "overall compliance가 높지만 safety gate에 걸린 케이스" (있다면)
     → "대부분 맞았지만 단 하나의 위험한 행동"

   각 패턴에 해당하는 구체적 에피소드를 보여줘.
   해당 에피소드에서 어떤 action이 문제였는지 상세히.

2. 이 케이스들을 기존 벤치마크 관점에서 재평가:
   - 만약 MedAgentBench처럼 "task completion 여부"만 평가했다면?
     → 위 케이스들은 "성공"으로 판정됐을 것
   - 만약 MedQA처럼 "정답 선택 여부"만 평가했다면?
     → timing/sequence 오류는 감지 불가
   - 이 차이를 테이블로 정리

Part B: 외부 벤치마크에서 증거 수집

3. AgentClinic live 20건에서:
   - CGA compliance가 높은 케이스(>80%)와 낮은 케이스(<40%) 비교
   - 낮은 케이스에서 어떤 violation type이 주로 발생하는지
   - AgentClinic의 원래 평가(diagnostic accuracy)와
     CGA compliance가 불일치하는 케이스가 있는지
     → "진단은 맞았지만 과정이 틀린" 케이스 = CGA의 존재 이유

4. HealthBench 50건에서:
   - rubric score가 높지만 CGA에서 deviation이 많은 케이스
   - "좋은 조언이지만 가이드라인 비표준" = CGA가 잡는 차원

Part C: Necessity argument 구성

5. 위 증거를 다음 구조로 정리:

   "기존 평가가 놓치는 3가지 failure mode":

   Failure Mode 1: Timing Blindness
   - 기존 평가: "항생제를 투여했는가?" → Yes → 성공
   - CGA-Bench: "항생제를 1시간 내에 투여했는가?" → No → timing violation
   - 실제 에피소드 예시 + 임상적 의미

   Failure Mode 2: Sequence Ignorance
   - 기존 평가: "혈액배양과 항생제를 모두 했는가?" → Yes → 성공
   - CGA-Bench: "혈액배양을 항생제 전에 했는가?" → No → sequence violation
   - 실제 에피소드 예시 + 임상적 의미

   Failure Mode 3: Overaction Tolerance
   - 기존 평가: "필수 행동을 했는가?" → Yes → 성공
   - CGA-Bench: "불필요한 검사를 과도하게 했는가?" → Yes → deviation
   - 실제 에피소드 예시 + 임상적 의미

6. 저장:
   - evidence_pack/analysis/necessity_evidence.json
   - evidence_pack/analysis/necessity_evidence.md
   - 논문의 Introduction 또는 Section 1에 넣을 수 있는
     concrete example 3개 (각 failure mode당 1개)