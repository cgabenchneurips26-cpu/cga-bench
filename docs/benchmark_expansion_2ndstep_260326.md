# CGA-Bench Validation + 확장 — Claude Code 프롬프트

**실행 순서**: Step 1(cross-reference) → Step 2(ART 통합) → Step 3(AgentEHR 통합)

---

## Step 1: Published Results Cross-Reference 테이블

```
cga_bench의 외부 벤치마크 결과를 기존 논문의 published results와 cross-reference하는
비교 테이블을 만들어라.

목적: "CGA-Bench의 점수가 기존 평가와 일관된다"는 external validity 근거 확보.

1. 다음 published results를 수집해라 (웹 검색으로 정확한 수치 확인):

   MedAgentBench (Stanford, NEJM AI 2025):
   - Claude 3.5 Sonnet v2: overall SR 69.67%
   - GPT-4o: 확인 필요
   - 다른 모델들의 SR도 Table 3에서 확인
   - query SR vs action SR 구분도 있으면 수집

   AgentClinic:
   - 원논문의 모델별 diagnostic accuracy / task completion rate
   - OpenManus/Manus 논문 (npj Digital Medicine 2026)에서:
     AgentClinic MedQA 60.3%, AgentClinic MIMIC 28.0%

   HealthBench (OpenAI):
   - 원논문의 모델별 결과 (compliance, rubric score 등)
   - HealthBench 60% success rate (from systematic review)

   MedChain:
   - 원논문의 모델별 결과

2. CGA-Bench 결과와 나란히 놓은 비교 테이블:

   ┌───────────────┬─────────────────────┬──────────────────────┬───────────────────┐
   │   Benchmark   │ Published (Original)│ Published (3rd-party)│ CGA-Bench (Ours)  │
   ├───────────────┼─────────────────────┼──────────────────────┼───────────────────┤
   │ MedAgentBench │ SR 69.67% (Sonnet)  │ 30.3% (OpenManus)    │ 96.7% (live)      │
   │               │                     │                      │ 0.0% (static)     │
   ├───────────────┼─────────────────────┼──────────────────────┼───────────────────┤
   │ AgentClinic   │ ?% (original)       │ 60.3% (Manus)        │ 62.0% (live)      │
   │               │                     │                      │ 14.6% (static)    │
   ├───────────────┼─────────────────────┼──────────────────────┼───────────────────┤
   │ HealthBench   │ ?% (OpenAI)         │ 60% (review)         │ 45.0% (live)      │
   ├───────────────┼─────────────────────┼──────────────────────┼───────────────────┤
   │ MedChain      │ ?% (original)       │ —                    │ 10.0% (live)      │
   └───────────────┴─────────────────────┴──────────────────────┴───────────────────┘

3. 중요: 메트릭이 다르면 명시적으로 구분해라:
   - Published의 "success rate"은 task completion 여부 (binary)
   - CGA-Bench의 "compliance"는 CPG 준수율 (continuous 0-100%)
   - "Live"는 CGA 파이프라인이 LLM agent를 직접 실행한 것
   - "Static"은 기존 데이터를 정적으로 평가한 것
   - 이 메트릭 차이를 테이블 각주로 설명

4. 논문 논거 작성:
   - CGA-Bench가 기존 SR과 다른 차원(CPG adherence)을 측정한다는 점
   - MedAgentBench live 96.7%는 "CPG에 맞는 행동을 하는 비율"이고,
     published 69.67%는 "task를 완료하는 비율" — 둘 다 높지만 측정 대상이 다름
   - 이 차이가 왜 중요한지: task 완료해도 CPG 위반할 수 있고, 반대도 가능

5. 저장:
   - evidence_pack/tables/table_cross_reference.tex
   - evidence_pack/external_benchmarks/cross_reference_analysis.md

6. 추가로 MedHELM taxonomy와 CGA-Bench C1-C5의 매핑 테이블도 만들어라:

   ┌──────────────────────────┬─────────────────────────┐
   │ MedHELM Category         │ CGA-Bench Mapping       │
   ├──────────────────────────┼─────────────────────────┤
   │ Clinical Decision Support │ C1 (Path), C2 (Action)  │
   │ - Diagnostic Decisions    │ C1 Path Selection       │
   │ - Treatment Planning      │ C2 Mandatory Completion │
   │ - Safety Assessment       │ C3 Forbidden Avoidance  │
   │ Administration & Workflow │ C4 Timing Compliance    │
   │ - Workflow Coordination   │ C5 Sequence Integrity   │
   └──────────────────────────┴─────────────────────────┘

   이 매핑을 evidence_pack/tables/table_medhelm_alignment.tex로 저장.
```

---

## Step 2: ART (Action-based Reasoning clinical Task) 벤치마크 통합

```
ART 벤치마크를 cga_bench에 통합해라.
ART는 EHR 데이터에서 action-based reasoning task를 생성하는 벤치마크로,
retrieval failures, aggregation errors, conditional logic misjudgments를 테스트한다.

Phase 1: 데이터 확보

1. ART 벤치마크 데이터를 확보해라:
   - 논문: arxiv 2601.08988 "ART: Action-based Reasoning clinical Task benchmark"
   - GitHub 검색: "ART action reasoning clinical task benchmark"
   - HuggingFace 검색: "ART medical benchmark"
   - 데이터가 공개되어 있으면 다운로드
   - 없으면 논문에서 task 구조와 예시를 분석하고,
     CGA-Bench의 기존 시나리오에서 ART-style task를 생성하는 방법을 제안

2. ART의 task 구조 분석:
   - 논문에서 task format 확인 (instruction, EHR context, ground truth)
   - 3가지 error category: retrieval, aggregation, conditional logic
   - 각 category의 task 예시를 3개씩 보여줘

Phase 2: Adapter 구현

3. ART 데이터를 CGA-Bench 파이프라인에 연결:
   - DatasetManifest 생성 (task_type, eval_mode, sub_score_mask)
   - ART의 action-based 특성상 C1/C2가 주요 평가 축
   - conditional logic task는 C3(forbidden avoidance)와 매핑 가능
   - threshold task는 C4(timing)와 부분적으로 매핑 가능

4. Registry에 등록:
   - configs/external_datasets.yaml 또는 registry.py에 추가

Phase 3: 실행

5. Smoke test 10건 → 성공하면 30-50건 확대

6. 결과 저장:
   - evidence_pack/external_benchmarks/art_results.json
   - evidence_pack/external_benchmarks/art_summary.md

7. ART 결과가 특별히 의미있는 이유를 정리:
   - ART가 "action-based"를 명시적으로 표방하는 벤치마크
   - CGA-Bench의 action-level evaluation과 직접적으로 정렬
   - "action-based evaluation에 특화된 벤치마크에서도 CGA 파이프라인이 작동한다"
```

---

## Step 3: AgentEHR 벤치마크 통합

```
AgentEHR 벤치마크를 cga_bench에 통합해라.
AgentEHR는 MIMIC-IV 기반 6개 task로 multi-step EHR reasoning을 평가하며,
MCP 서버를 통해 19개 tool을 제공하는 최신 벤치마크다.

Phase 1: 데이터/코드 확보

1. AgentEHR 접근:
   - 논문: arxiv 2601.13918 "AgentEHR: Advancing Autonomous Clinical Decision-Making"
   - GitHub 검색: "AgentEHR benchmark"
   - HuggingFace 검색
   - MIMIC-IV 데이터 의존이면 PhysioNet 접근이 필요할 수 있음 — 확인

2. AgentEHR의 task 구조 분석:
   - 6개 task가 뭔지 (diagnosis, treatment planning 등)
   - multi-step interaction이 어떤 형태인지
   - tool (MCP 서버 19개) 목록과 역할
   - Common / Long-tail / Cross-DB subset 구조

Phase 2: Adapter 구현

3. AgentEHR의 구조가 CGA-Bench와 어떻게 매핑되는지 분석:
   - AgentEHR의 "tool call sequence"가 CGA의 "action sequence"와 대응
   - diagnosis task → C1 (path selection)
   - treatment planning → C2 (mandatory completion) + C3 (forbidden)
   - temporal reasoning → C4 (timing)
   - multi-step → C5 (sequence)

4. Adapter 구현:
   - semantic_layer/external/agentehr.py (또는 UniversalExternalAdapter 활용)
   - DatasetManifest 생성
   - Registry 등록

Phase 3: 실행

5. MIMIC-IV 데이터 접근이 가능하면:
   - Smoke test 10건
   - 확대 실행 30-50건

6. MIMIC-IV 접근이 불가능하면:
   - AgentEHR가 제공하는 sample/demo 데이터로 제한적 실행
   - 또는 "pipeline 호환성 확인"만 수행하고 결과는 데이터 확보 후 추가

7. 결과 저장:
   - evidence_pack/external_benchmarks/agentehr_results.json
   - evidence_pack/external_benchmarks/agentehr_summary.md

Phase 4: 최종 통합

8. 모든 외부 벤치마크를 최종 통합 테이블로:

   ┌──────────────────┬───────────┬─────┬──────────────┬────────────────┬────────┐
   │    Benchmark     │   Type    │  N  │ Static Eval  │ Live Agent     │ Safety │
   ├──────────────────┼───────────┼─────┼──────────────┼────────────────┼────────┤
   │ Internal (8 CPG) │ Sim-agent │ 24  │ —            │ 75.1%          │ 100%   │
   │ HealthBench      │ Rubric QA │ 50  │ —            │ 45.0%          │ 100%   │
   │ MedAgentBench    │ FHIR API  │ 20  │ 0.0%         │ 96.7%          │ 100%   │
   │ AgentClinic      │ Dialogue  │ 20  │ 14.6%        │ 62.0%          │ 100%   │
   │ MedChain         │ Workflow  │ 49  │ 5.8%         │ 10.0%          │ 99.4%  │
   │ AMEGA            │ Guide QA  │ 24  │ —            │ pipeline ✅    │ —      │
   │ LLMEval-Med      │ Med QA    │ 50  │ —            │ pipeline ✅    │ —      │
   │ ART              │ Action    │ ?   │ —            │ ?%             │ ?%     │
   │ AgentEHR         │ EHR Agent │ ?   │ —            │ ?%             │ ?%     │
   └──────────────────┴───────────┴─────┴──────────────┴────────────────┴────────┘

9. 최종 LaTeX 테이블:
   - evidence_pack/tables/table_external_final_v2.tex (전체 통합)
   - evidence_pack/tables/table_cross_reference.tex (published 비교)
   - evidence_pack/tables/table_medhelm_alignment.tex (taxonomy 매핑)

10. 최종 논문 논거 정리:
    evidence_pack/external_benchmarks/final_validation_summary.md에:
    - "CGA-Bench는 9개 외부 벤치마크를 통일된 프레임워크로 평가한다"
    - "Published results와의 cross-reference로 external validity를 확인했다"
    - "MedHELM taxonomy와의 정렬로 평가 축의 임상적 근거를 확보했다"
    - "Action-based 벤치마크(ART)에서의 성공은 CGA의 action-level 평가 접근을 지지한다"
```

---

## 실행 체크리스트

```
□ Step 1: Cross-reference 테이블 (published vs CGA) 완성
□ Step 1: MedHELM taxonomy alignment 테이블 완성
□ Step 2: ART 데이터 확보 + adapter + 실행
□ Step 3: AgentEHR 데이터 확보 + adapter + 실행 (가능한 범위)
□ Step 3: 최종 통합 테이블 업데이트 (9개 벤치마크)
□ Step 3: final_validation_summary.md 작성
```