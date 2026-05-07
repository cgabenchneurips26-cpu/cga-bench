# 외부 벤치마크 확장 — 방향 1 + 2 병렬 진행

**방향 1**: AMEGA, LLMEval-Med 등 LLM completion 기반 벤치마크 추가
**방향 2**: MedAgentBench/MedChain/AgentClinic을 live agent 모드로 재실행
**실행**: Step 1(방향2 현황 파악) → Step 2(방향2 실행) + Step 3(방향1 데이터 확보) 병렬 → Step 4(방향1 실행) → Step 5(통합)

---

## Step 1: Live Agent 모드 가능 여부 확인

```
cga_bench에서 기존 외부 벤치마크(MedAgentBench, MedChain, AgentClinic)를
static evaluation이 아닌 live LLM agent 모드로 실행할 수 있는지 확인해라.

1. run_external_benchmark.py의 전체 옵션을 보여줘:
   - --agent 또는 --mode 같은 옵션이 있는지
   - static vs live 모드 구분이 있는지
   - 없으면 내부 시나리오(run_benchmark.py 등)에서 에이전트를 실행하는 방식을 확인

2. 각 외부 벤치마크 adapter에서:
   - build_observation()이 구현되어 있는지 (에이전트에게 입력을 줄 수 있는지)
   - parse_agent_output()이 구현되어 있는지 (에이전트 출력을 파싱할 수 있는지)
   - 이 두 함수가 실제로 작동하는지 (mock이 아닌 실제 구현인지)

3. HealthBench에서 live agent가 작동한 방식을 역추적:
   - HealthBench 50건 실행 시 에이전트가 어떻게 action을 생성했는지
   - 이 동일한 패턴을 MedAgentBench/MedChain/AgentClinic에 적용할 수 있는지

4. 현실적 판단:
   - live agent 실행이 바로 가능한 벤치마크: ?
   - 추가 구현 필요한 벤치마크: 뭐가 필요한지
   - 구조적으로 불가능한 벤치마크: 이유

5. AgentClinic은 원래 대화형이니 live agent 모드가 자연스러움.
   AgentClinic의 대화 시뮬레이터가 있는지 확인:
   - 환자 역할 LLM + 의사 역할 LLM 구조인지
   - 기존 코드에 이 구조가 구현되어 있는지
```

---

## Step 2: Live Agent 모드 실행 (Step 1 결과에 따라)

```
Step 1에서 live agent 실행이 가능한 외부 벤치마크에 대해 실행해라.

실행 방법 (Step 1 결과에 따라 조정):

1. 각 벤치마크별 10건 smoke test 먼저:
   - live agent가 action을 생성하는지 확인
   - actions_performed가 비어있지 않은지 확인
   - 성공률 80%+이면 확대

2. Smoke test 통과한 벤치마크는 20~50건으로 확대:
   - MedAgentBench: FHIR 케이스에 대해 LLM이 의료 행동을 생성
   - MedChain: workflow 케이스에 대해 LLM이 치료 계획 생성
   - AgentClinic: 환자-의사 대화를 LLM으로 시뮬레이션

3. 결과를 static 결과와 나란히 비교:

   ┌───────────────┬─────────────────┬────────────────┐
   │   Benchmark   │ Static Eval     │ Live Agent     │
   ├───────────────┼─────────────────┼────────────────┤
   │ MedAgentBench │ 0.0%            │ ?%             │
   ├───────────────┼─────────────────┼────────────────┤
   │ MedChain      │ 5.8%            │ ?%             │
   ├───────────────┼─────────────────┼────────────────┤
   │ AgentClinic   │ 14.6%           │ ?%             │
   └───────────────┴─────────────────┴────────────────┘

4. 결과 저장:
   - evidence_pack/external_benchmarks/{benchmark}_live_results.json
   - evidence_pack/external_benchmarks/static_vs_live_comparison.md
```

---

## Step 3: 새 벤치마크 데이터 확보 + Adapter (Step 2와 병렬)

```
LLM completion 기반 외부 벤치마크를 추가로 확보해라.
우선순위: AMEGA > LLMEval-Med > MedGUIDE

AMEGA:

1. AMEGA 데이터셋 접근 방법 확인:
   - HuggingFace, GitHub, 또는 공식 사이트에서 다운로드 가능한지
   - 검색: "AMEGA medical benchmark dataset download"
   - 데이터 형식 확인 (JSON? JSONL? CSV?)

2. 데이터를 data/external_benchmarks/amega/ 에 배치

3. pipeline.py에 split_amega_questions 로직이 이미 있으니,
   이걸 활용해서 독립 adapter를 작성할 필요 없이 실행:
   - UniversalExternalAdapter + AMEGA manifest로 바로 실행 가능한지 확인
   - 10건 smoke test

LLMEval-Med:

4. LLMEval-Med 데이터셋 접근:
   - 검색: "LLMEval-Med dataset download"
   - 667 questions, clinical scene subset
   - 데이터 형식 확인

5. data/external_benchmarks/llmeval_med/ 에 배치

6. Registry에 이미 manifest가 있으니 (LLMEVAL_MED),
   UniversalExternalAdapter로 실행 시도:
   - 10건 smoke test
   - 성공률 확인

MedGUIDE (시간 여유 있으면):

7. MedGUIDE 데이터셋:
   - 55 NCCN decision trees, 17 cancer types, 7747 samples
   - MCQ path 형태라 C1(path selection) 평가에 적합
   - 라이선스: NCCN verbatim text 제한 확인 필요

8. 각 데이터셋에서 데이터를 못 구하면:
   - 접근 방법과 필요한 절차를 보고해라
   - 무리하게 진행하지 말고 가능한 것만 진행

각 데이터셋의 상태를 보고해라:
- 다운로드 성공/실패
- 데이터 건수와 형태
- Smoke test 결과 (가능한 경우)
```

---

## Step 4: 새 벤치마크 확대 실행

```
Step 3에서 데이터 확보 + smoke test 성공한 벤치마크에 대해 확대 실행해라.

1. 성공한 각 벤치마크에 대해 30~50건 실행:
   - HealthBench와 동일한 방식: LLM completion → action 추출 → CGA 평가
   - 도메인 다양성 있게 샘플링

2. 결과 정리 (벤치마크별):
   - 성공률
   - Compliance mean±SD
   - Sub-score 분포
   - 주요 위반 유형

3. 결과 저장:
   - evidence_pack/external_benchmarks/{benchmark}_results.json
   - evidence_pack/external_benchmarks/{benchmark}_summary.md
```

---

## Step 5: 최종 통합 테이블

```
모든 외부 벤치마크 결과를 최종 통합 테이블로 만들어라.

1. 통합 대상:
   - Internal (8 CPG scenarios): 75.1%
   - HealthBench (live): 45.0%
   - AgentClinic (static / live): 14.6% / ?%
   - MedChain (static / live): 5.8% / ?%
   - MedAgentBench (static / live): 0.0% / ?%
   - AMEGA (live, 가능하면): ?%
   - LLMEval-Med (live, 가능하면): ?%
   - MedGUIDE (live, 가능하면): ?%

2. 테이블 구조:

   ┌──────────────────┬───────────┬─────┬─────────────────┬────────────────┬────────┐
   │    Benchmark     │   Type    │  N  │ Static Eval     │ Live Agent     │ Safety │
   ├──────────────────┼───────────┼─────┼─────────────────┼────────────────┼────────┤
   │ Internal (8 CPG) │ Sim-agent │ 24  │ —               │ 75.1%          │ 100%   │
   │ HealthBench      │ Rubric QA │ 50  │ —               │ 45.0%          │ 100%   │
   │ AMEGA            │ Open QA   │ ?   │ —               │ ?%             │ ?%     │
   │ LLMEval-Med      │ Open QA   │ ?   │ —               │ ?%             │ ?%     │
   │ AgentClinic      │ Dialogue  │ 20  │ 14.6%           │ ?%             │ 100%   │
   │ MedChain         │ Workflow  │ 49  │ 5.8%            │ ?%             │ 99.4%  │
   │ MedAgentBench    │ FHIR API  │ 50  │ 0.0%            │ ?%             │ 100%   │
   └──────────────────┴───────────┴─────┴─────────────────┴────────────────┴────────┘

3. 이 테이블이 보여주는 논문 contribution:
   - "CGA-Bench는 7개+ 벤치마크를 통일된 프레임워크로 평가한다"
   - "Static evaluation의 한계와 live agent evaluation의 필요성을 정량적으로 보여준다"
   - "Action representation의 구조적 차이가 compliance에 직접 반영된다"

4. 저장:
   - evidence_pack/tables/table_external_final.tex — 최종 LaTeX
   - evidence_pack/external_benchmarks/final_summary.md — 전체 요약
   - 기존 테이블들(table_external_multi.tex 등)도 유지

5. 논문용 Figure 제안:
   - Static vs Live 비교 bar chart (벤치마크별 두 막대)
   - 가능하면 evidence_pack/figures/에 생성
```

---

## 실행 체크리스트

```
방향 2 (Live Agent):
□ Step 1: live agent 가능 여부 확인
□ Step 2: 가능한 벤치마크 live 실행, static vs live 비교

방향 1 (새 벤치마크):
□ Step 3: AMEGA/LLMEval-Med/MedGUIDE 데이터 확보 + smoke test
□ Step 4: 성공한 벤치마크 확대 실행

통합:
□ Step 5: 최종 통합 테이블 + LaTeX + Figure
```