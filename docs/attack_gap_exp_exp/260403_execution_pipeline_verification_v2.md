> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# CGA-Bench 병렬 워크스트림 — 개발자 배분용

> EXP-A~F (시나리오 동등성, ablation, disagreement 정량화 등)은 별도 진행 중.
> 이 문서는 **그 외에 병렬 착수 가능한 작업**을 개발자별로 배분하기 위한 것.

---

## 워크스트림 배분 맵

```
개발자 1: EXP-A~F (기존 프롬프트)
개발자 2: WS-1 (Reproducibility infra) + WS-2 (Benchmark comparison)
개발자 3: WS-3 (LLM Judge pipeline) + WS-4 (Run variance)
개발자 4: WS-5 (Contamination probe) + WS-6 (Error taxonomy + case study)
개발자 5: WS-7 (Anonymous repo) + WS-8 (Appendix skeleton)
```

---

## WS-1: Reproducibility Infrastructure (즉시 착수)

**왜 필수인가:** NeurIPS 2026 E&D Track은 "primary contribution이 reusable executable artifact인 경우 코드 공개가 제출 시 필수"라고 명시. 리뷰어 체크리스트에 reproducibility 항목이 존재하며, BetterBench 분석에서 17/24 벤치마크에 재현 스크립트가 없음이 비판 대상이었음. 우리가 "evaluation audit" 논문을 쓰면서 스스로 재현 불가능하면 즉시 reject 사유.

```
목표: `make reproduce` 한 줄로 전체 파이프라인 재현.

=== 작업 ===

1. Makefile 생성 (프로젝트 루트)

   타겟 구조:
   
   make setup          — conda env 생성 + pip install
   make validate-graphs — 25개 CPG graph YAML 스키마 검증
   make derive         — ConstraintDerivationEngine 실행 → 451 constraints 재도출
   make generate       — PatientGenerator 실행 → 254 auto scenarios 재생성
   make test           — pytest 194 tests
   make episodes-dry   — 1 model × 5 scenarios × 1 run (smoke test)
   make episodes-full  — 전체 실행 (GPU 필요, CI에서는 skip)
   make rescore        — 전체 재채점
   make experiments    — EXP-A~F 순차 실행
   make paper-numbers  — auto_numbers.tex 생성
   make all            — setup → test → derive → generate → experiments → paper-numbers
   
   각 타겟은 idempotent (재실행 시 동일 결과).
   GPU 필요 타겟은 환경변수 체크 후 graceful skip.

2. environment.yml 생성
   
   Python 3.10+, 모든 의존성 pinned version.
   pytorch, vllm 등 GPU 의존성은 optional group으로 분리.

3. Docker 설정 (선택적이나 권장)
   
   Dockerfile + docker-compose.yml
   CPU-only 이미지 (테스트 + 분석용)와 GPU 이미지 분리.

4. CI 설정
   
   .github/workflows/ci.yml:
   - push/PR 시: make setup → make test → make validate-graphs → make derive
   - derive 결과가 기존 결과와 deterministic 일치하는지 diff 확인
   - 실행 시간 상한: 30분

5. scripts/verify_determinism.py 생성
   
   ConstraintDerivationEngine + PatientGenerator를 3회 실행하여
   출력이 byte-identical인지 검증. seed 고정 확인.

출력:
- Makefile
- environment.yml  
- Dockerfile, docker-compose.yml
- .github/workflows/ci.yml
- scripts/verify_determinism.py
- REPRODUCE.md (재현 가이드, 예상 실행 시간, 하드웨어 요구사항)
```

---

## WS-2: Benchmark Comparison Table (즉시 착수)

**왜 필수인가:** Related work 비교 없음이 리뷰어 공격 목록에 있음. "이 벤치마크가 기존 벤치마크(MedAgentBench, AgentClinic, AMEGA, ClinicalBench 등)와 어떻게 다른가?"는 반드시 나올 질문. 비교표 없이 제출하면 "novelty unclear"로 score 하락.

```
목표: 기존 의료 AI agent 벤치마크 10개+ 와의 체계적 비교표 생성.

=== 작업 ===

1. scripts/generate_benchmark_comparison.py 생성

   비교 대상 (웹 검색으로 최신 정보 확인 필요):
   - MedAgentBench (Stanford, 2025) — FHIR 기반 300 tasks
   - AgentClinic (2024) — multi-agent simulated clinic
   - AMEGA (NEJM AI, 2025) — 가이드라인 준수 평가
   - ClinicalBench (2024) — clinical reasoning
   - MedQA/MedMCQA — QA 기반 (non-agent, baseline)
   - GMAI-MMBench (NeurIPS 2024) — multimodal medical
   - MultiMedQA / Med-PaLM — QA + clinician eval
   - AgentBench (2023) — general agent
   - WebArena/SWE-bench — non-medical agent (참고용)
   - CPGPrompt (2025) — CPG→decision tree (가장 직접적 경쟁자)

   비교 축:
   - Evaluation 방법 (rule-based / LLM-judge / human / hybrid)
   - Scenario 생성 방법 (manual / template / LLM / knowledge graph)
   - Constraint 유형 (temporal / safety / completeness / ordering)
   - Domain 수, Scenario 수, Model 수
   - Clinician 참여 유형 (scenario 작성 / 검증 / 수행)
   - 코드 공개 여부
   - Multi-evaluator 비교 여부 (우리의 차별점)
   - Agent interactivity (static QA vs interactive environment)

   이 데이터를 수동으로 JSON에 정리한 후 (각 벤치마크 논문 확인 필요),
   자동으로 LaTeX 테이블 생성.

2. evidence_pack/tables/benchmark_comparison.tex 생성

   booktabs 스타일, landscape 페이지.
   우리 벤치마크의 고유 특성(multi-evaluator disagree 분석, 
   constraint derivation engine, temporal constraint)이 
   시각적으로 구분되도록 bold/highlight.

3. paper 삽입용 prose 초안 (500단어)

   evidence_pack/benchmark_comparison_prose.md:
   "기존 벤치마크들은 single evaluator를 gold standard로 가정한다.
   CGA-Bench는 이 가정 자체를 검증하는 최초의 벤치마크이다"
   라는 positioning을 뒷받침하는 논거.

출력:
- evidence_pack/benchmark_comparison_data.json
- evidence_pack/tables/benchmark_comparison.tex
- evidence_pack/benchmark_comparison_prose.md
```

---

## WS-3: EXP-2 LLM Judge Pipeline 구축 (즉시 착수, 실행은 episode 후)

**왜 필수인가:** DxEM = strawman이라는 리뷰어 공격에 대한 방어. 현재 DxEM은 100% pass (structural)로 의미가 없으므로, non-degenerate LLM judge baseline이 필요. 또한 "LLM judge가 constraint-based evaluator와 얼마나 다른가?"는 Gap 3 (disagreement 정량화)의 핵심 비교축.

```
목표: vLLM endpoint로 LLM judge를 실행하고, CGA-Bench evaluator와의 
agreement를 측정하는 전체 파이프라인 구축.

=== 작업 ===

1. scripts/experiments/exp_2_llm_judge.py 생성

   **Phase A: 프롬프트 설계 (즉시)**
   
   LLM judge 프롬프트 3가지 변형:
   
   (a) Rubric-free: 시나리오 설명 + agent trace만 주고
       "이 에이전트의 수행을 pass/fail로 평가하라" (가장 약한 baseline)
   
   (b) Rubric-aware: 시나리오 설명 + agent trace + 
       "다음 constraint를 모두 충족해야 pass: [FORBIDDEN/REQUIRED/BEFORE/WITHIN 목록]"
       (constraint를 힌트로 제공)
   
   (c) CoT-judge: (b) + "먼저 각 constraint별로 충족 여부를 판단하고,
       종합하여 pass/fail을 결정하라" (chain-of-thought)
   
   각 프롬프트를 Jinja2 템플릿으로 작성.
   
   **Phase B: Dry-run (즉시 — 기존 episode로)**
   
   results/clean_slate_rescored/ 의 기존 180 episode 중
   10개 대표 episode를 선정하여:
   - 3가지 프롬프트 변형 × 10 episodes = 30 LLM judge 호출
   - vLLM 또는 OpenAI API로 실행
   - CGA-Bench evaluator 결과와 비교하여 프롬프트 품질 확인
   
   **Phase C: 본 실행 (episode 후)**
   
   전체 episode에 대해 3가지 프롬프트 변형 실행.
   
   **Phase D: 분석**
   
   LLM judge (a)(b)(c) 각각 vs CGA-Bench 6 evaluators:
   - Cohen's κ
   - "LLM judge가 constraint-based evaluator와 불일치하는 비율"
   - "constraint 힌트가 LLM judge의 정확도를 얼마나 올리는가"
     → constraint derivation의 가치를 간접 증명
   - 불일치 사례의 qualitative 분석 (10개 샘플)

2. configs/llm_judge_prompts/ 디렉토리 생성
   
   - rubric_free.jinja2
   - rubric_aware.jinja2
   - cot_judge.jinja2
   - judge_config.yaml (model, temperature, max_tokens 등)

출력:
- configs/llm_judge_prompts/*.jinja2
- scripts/experiments/exp_2_llm_judge.py
- evidence_pack/exp_2_llm_judge.json (dry-run 결과)
- evidence_pack/exp_2_llm_judge.md
- evidence_pack/tables/llm_judge_agreement.tex
```

---

## WS-4: Run Variance 분석 파이프라인 (Episode 후)

**왜 필수인가:** 3 runs per scenario의 variance가 "모든 결론의 신뢰구간"을 결정. Run variance가 evaluator disagreement보다 크면 논문의 핵심 주장이 무효화됨 ("그건 disagreement가 아니라 noise다"). 리뷰어 공격 목록에 "Run variance 🔴 미구현"으로 명시되어 있음.

```
목표: 3-run variance가 evaluator disagreement보다 체계적으로 작음을 증명.

=== 작업 ===

1. scripts/experiments/ws4_run_variance.py 생성

   **분석 1: Intra-scenario variance**
   
   각 (시나리오, 모델) 조합의 3 runs에 대해:
   - Pass/fail 일치도 (3/3 일치, 2/1 split)
   - 3/3 일치 비율 = run stability
   - 2/1 split인 경우의 특성 분석
     (어떤 시나리오/모델/도메인에서 unstable한가?)

   **분석 2: Run variance vs Evaluator variance 비교**
   
   핵심 비교: 
   "같은 evaluator의 3 runs 간 variance" vs 
   "같은 run의 6 evaluators 간 variance"
   
   - 각 (시나리오, 모델)에서:
     within-run evaluator disagreement = 6 evaluators의 pass/fail entropy
     across-run instability = 3 runs의 majority vote 불일치
   - paired comparison: evaluator variance가 run variance보다 체계적으로 큰지
     (Wilcoxon signed-rank test)
   
   → 이것이 논문의 핵심 방어: "관측된 disagreement는 run noise가 아니라 
     evaluator 설계의 체계적 차이에서 비롯된다"

   **분석 3: Variance 분해 (ANOVA)**
   
   Pass/fail을 종속변수로, 3-way ANOVA:
   - Factor A: Model (5 levels)
   - Factor B: Evaluator (6 levels)  
   - Factor C: Run (3 levels)
   - 각 factor의 explained variance (η²)
   
   기대: Evaluator η² >> Run η² 이면 주장 성립.

   **분석 4: 3-run이 충분한지**
   
   Bootstrap으로 시뮬레이션:
   - 3 runs의 majority vote 결과 vs 
     hypothetical 10 runs의 majority vote 결과
   - 수렴 분석: 몇 run부터 결과가 안정되는가
   - 3 runs이 불충분한 시나리오 비율

출력:
- evidence_pack/ws4_run_variance.json
- evidence_pack/ws4_run_variance.md
- evidence_pack/figures/ws4_variance_decomposition.png (η² bar chart)
- evidence_pack/figures/ws4_run_vs_evaluator.png (paired comparison)
- evidence_pack/figures/ws4_stability_by_domain.png (heatmap)
- evidence_pack/tables/run_variance.tex
```

---

## WS-5: Data Contamination Probe (즉시 착수)

**왜 필수인가:** 모델 학습 데이터에 CPG 가이드라인 원문이 포함되어 있으면, 벤치마크 결과가 "진짜 임상 추론"이 아니라 "암기"를 측정하는 것일 수 있음. SWE-bench에서 이미 비판받은 문제.

```
목표: 평가 대상 모델들이 CPG 원문을 "암기"했는지 간접 측정.

=== 작업 ===

1. scripts/experiments/ws5_contamination_probe.py 생성

   **Probe 1: Verbatim recall test**
   
   각 CPG graph의 원본 가이드라인에서 핵심 문장 5개 추출 (수동 — JSON으로 미리 준비).
   각 문장의 앞 절반을 모델에 주고 뒷 절반을 생성하게 함.
   BLEU/ROUGE로 원문 재현율 측정.
   
   높은 재현율 = 잠재적 contamination.
   
   **Probe 2: Constraint recall without context**
   
   각 시나리오의 patient context만 주고 (CPG 이름 불포함):
   "이 환자에게 금기인 약물/시술을 나열하라"
   모델 응답 vs derived FORBIDDEN constraints의 recall/precision.
   
   높은 recall = 모델이 가이드라인 내용을 이미 알고 있음.
   → 이 자체가 나쁜 것은 아님. 하지만 논문에서 
     "이 성능이 reasoning인지 recall인지"를 구분해야 함.

   **Probe 3: Novel constraint test**
   
   실제 CPG에 없는 가상의 constraint를 포함한 시나리오 5개 생성
   (예: 가상의 약물 상호작용).
   모델이 이 가상 constraint를 따르는지 무시하는지 측정.
   
   가상 constraint 무시 = 가이드라인 암기에 의존
   가상 constraint 준수 = 시나리오 context를 실제로 읽고 추론

   **Probe 4: Held-out domain advantage**
   
   Held-out 5개 domain (Burns, Transfusion 등)은 
   main 20개 domain보다 학습 데이터에 덜 포함되었을 가능성.
   → held-out domain에서 모델 성능이 유의하게 낮으면 contamination 시사.
   (이 분석은 EXP-C의 결과와 연동)

2. configs/contamination_probes.json 생성
   
   각 CPG의 핵심 문장 5개 × 25 graphs = 125 probes.
   (수동 작성 필요 — 이 스크립트는 JSON이 준비되면 실행)
   
   일단은 main 20개 graph 중 5개 (가장 잘 알려진 CPG)에 대해 
   25 probes로 pilot 실행.

출력:
- configs/contamination_probes.json (probe 데이터)
- scripts/experiments/ws5_contamination_probe.py
- evidence_pack/ws5_contamination.json
- evidence_pack/ws5_contamination.md
- evidence_pack/tables/contamination_probe.tex
```

---

## WS-6: Error Taxonomy + Case Study 자동 선정 (Episode 후)

**왜 필수인가:** 평가과학 논문의 설득력 공식 3단계 "분류 체계(taxonomy) 제공"과 2단계 "구체적 사례 제시"에 해당. EXP-D가 정량적 disagreement를 측정한다면, WS-6는 정성적 이해를 제공.

```
목표: (1) 에이전트 실패 유형의 체계적 분류, 
      (2) 논문에 삽입할 case study 3-5개 자동 선정.

=== 작업 ===

1. scripts/experiments/ws6_error_taxonomy.py 생성

   **Part A: Failure mode 분류**
   
   모든 episode에서 fail 판정을 받은 것들을 분석:
   
   Category 1 — Safety violation: FORBIDDEN 행동 수행
     Sub-1a: 약물 금기 위반
     Sub-1b: 시술 금기 위반
     Sub-1c: 검사 금기 위반
   
   Category 2 — Temporal violation: BEFORE/WITHIN 위반
     Sub-2a: 순서 역전 (A before B인데 B 먼저 수행)
     Sub-2b: 시간 초과 (WITHIN 30min인데 45min 후 수행)
     Sub-2c: 시간 정보 자체 무시
   
   Category 3 — Omission: REQUIRED 행동 미수행
     Sub-3a: 핵심 치료 누락
     Sub-3b: 모니터링 누락
     Sub-3c: 후속 조치 누락
   
   Category 4 — Compound: 복수 유형 동시 발생
   
   각 category별 빈도, 모델별 분포, 도메인별 분포.
   → 이것이 논문의 Section 5 (Analysis)의 뼈대.

   **Part B: Case study 자동 선정**
   
   "논문에서 가장 설득력 있는 case study"를 자동 선정하는 알고리즘:
   
   Score = w1 × evaluator_disagreement_count  (이 episode에서 불일치 evaluator 수)
         + w2 × clinical_severity           (FORBIDDEN 위반 포함 여부)
         + w3 × model_diversity             (몇 개 모델이 같은 실패를 하는가)
         + w4 × interpretability            (실패 원인이 명확한가)
   
   Top-5 episode를 선정하여 각각:
   - 시나리오 요약 (2-3문장)
   - Agent trace 핵심 부분 (anonymized)
   - 각 evaluator의 판정 + 판정 근거
   - "이 사례가 보여주는 evaluation disagreement의 유형"
   
   → evidence_pack/case_studies/ 에 개별 markdown 생성

2. scripts/experiments/ws6_select_poster_children.py 생성
   
   기존 select_case_studies.py가 있으면 확장, 없으면 신규.
   위 scoring 알고리즘 구현.

출력:
- evidence_pack/ws6_error_taxonomy.json
- evidence_pack/ws6_error_taxonomy.md
- evidence_pack/case_studies/case_1.md ~ case_5.md
- evidence_pack/figures/ws6_failure_distribution.png (sunburst chart)
- evidence_pack/figures/ws6_failure_by_model.png (stacked bar)
- evidence_pack/tables/error_taxonomy.tex
- evidence_pack/tables/case_study_summary.tex
```

---

## WS-7: Anonymous Repo 준비 (Phase 1부터 점진적)

```
목표: 제출 시점에 실행 가능한 anonymous GitHub repo.

=== 작업 ===

1. scripts/prepare_anonymous_repo.py 생성

   - 모든 .py, .yaml, .md, .tex 파일에서 저자 식별 정보 제거
     (이름, 이메일, 기관, GitHub handle, 특정 서버 주소)
   - regex 기반 스캔 + 수동 확인 목록 생성
   - git history에서 저자 정보 제거 (git filter-branch)
   - _archive/ 디렉토리 제외
   - 결과: anonymous_repo/ 디렉토리에 클린 복사본

2. anonymous_repo/README.md 생성

   - 프로젝트 설명 (논문 제목 anonymized)
   - 설치 + 실행 가이드
   - 디렉토리 구조 설명
   - 라이선스 (MIT 또는 Apache 2.0)

3. 검증
   
   - anonymous_repo/ 에서 `make test` 통과 확인
   - `grep -r "author_name"` 등으로 식별정보 잔존 확인
```

---

## WS-8: Appendix Skeleton (Phase 1부터 점진적)

```
목표: 논문 appendix의 구조와 placeholder 생성. 
본문 10페이지 제한이므로 appendix에 상세 내용 배치가 필수.

=== 작업 ===

1. paper/appendix.tex 생성

   구조:
   
   A. CPG Graph 상세
      A.1 전체 25개 graph 목록 + 출처 가이드라인 + node/edge 수
      A.2 Conditional rule 전체 목록 (표)
      A.3 Constraint type별 분포 (그래프)
   
   B. Scenario 상세  
      B.1 Manual vs Auto 시나리오 통계 (EXP-A 결과 삽입 위치)
      B.2 시나리오 예시 3개 (full YAML)
      B.3 Patient complexity 분포
   
   C. Derivation Engine 상세
      C.1 알고리즘 pseudocode
      C.2 Ablation 결과 (EXP-B 결과 삽입 위치)
      C.3 Scalability 분석
   
   D. Evaluation Disagreement 상세
      D.1 전체 κ 행렬 (EXP-D 결과)
      D.2 Rank reversal 전체 목록
      D.3 Disagreement taxonomy 상세 (WS-6 결과)
      D.4 Case studies 전체 (WS-6 결과)
   
   E. Experimental Details
      E.1 모델 설정 (temperature, max_tokens 등)
      E.2 Run variance 분석 (WS-4 결과)
      E.3 LLM Judge 프롬프트 전문 (WS-3 결과)
      E.4 Data contamination probe (WS-5 결과)
   
   F. Generalizability
      F.1 Held-out domain 상세 결과 (EXP-C)
      F.2 Difficulty equivalence 상세 (EXP-E)
   
   G. Benchmark Comparison
      G.1 전체 비교표 (WS-2 결과)
      G.2 차별화 논거
   
   H. Reproducibility
      H.1 하드웨어 사양
      H.2 실행 시간
      H.3 Anonymous repo 구조

   각 섹션에 \placeholder{EXP-X 결과 삽입} 마커.
   
2. paper/appendix_figures.tex
   
   evidence_pack/figures/ 의 모든 figure를 
   appendix에 배치하는 \includegraphics 코드 자동 생성.
```

---

## 전체 타임라인 (마감 5월 4일 기준)

```
Week 1 (4/3 ~ 4/9):
  ├─ 개발자1: EXP-A, B, C (pre-episode 실험)
  ├─ 개발자2: WS-1 (Makefile/Docker), WS-2 시작 (comparison data 수집)
  ├─ 개발자3: WS-3 Phase A (LLM judge 프롬프트 설계 + dry-run)
  ├─ 개발자4: WS-5 pilot (contamination probe 데이터 5 graphs 준비)
  └─ 개발자5: WS-7 (anonymous repo 초안), WS-8 (appendix skeleton)

Week 2 (4/10 ~ 4/16):
  ├─ Episode 전체 실행 시작 (3-4일)
  ├─ 개발자1: EXP-D, E 코드 작성 (episode 완료 대기)
  ├─ 개발자2: WS-2 완료 (comparison table)
  ├─ 개발자3: WS-3 Phase B 실행
  ├─ 개발자4: WS-5 나머지 20 graphs probe 준비
  └─ 개발자5: WS-8 appendix 본문 작성 시작

Week 3 (4/17 ~ 4/23):
  ├─ Episode 완료 → 재채점
  ├─ 개발자1: EXP-D, E, F 실행
  ├─ 개발자2: WS-1 CI 테스트 + 검증
  ├─ 개발자3: WS-3 Phase C 실행 + WS-4 run variance
  ├─ 개발자4: WS-5 실행 + WS-6 error taxonomy
  └─ 개발자5: main.tex 수치 업데이트 시작

Week 4 (4/24 ~ 4/30):
  ├─ 전원: 논문 최종 수정
  ├─ 개발자1: EXP-F (evidence pack 통합)
  ├─ 개발자2: WS-1 최종 검증
  ├─ 개발자3: LLM judge 결과 논문 반영
  ├─ 개발자4: case study + taxonomy 논문 반영
  └─ 개발자5: appendix 완성 + anonymous repo 최종 검증

5/1 ~ 5/3: 최종 리뷰, abstract 제출 (5/4), 논문 제출 (5/6)
```

---

## 의존 관계 그래프

```
즉시 착수 가능 (episode 불필요):
  EXP-A ─┐
  EXP-B ─┼─ (독립)
  EXP-C ─┘
  WS-1  ── (독립)
  WS-2  ── (독립, 웹 조사 필요)
  WS-3 Phase A ── (독립)
  WS-5 pilot ── (독립)
  WS-7  ── (독립)
  WS-8  ── (독립)

Episode 완료 후:
  EXP-D ── (episode 결과 필요)
  EXP-E ── (episode 결과 필요, EXP-A 참조)
  WS-3 Phase C ── (episode 결과 필요)
  WS-4  ── (episode 결과 필요)
  WS-5 full ── (모델 API 접근 필요)
  WS-6  ── (episode 결과 필요, EXP-D 결과 참조)

모든 실험 후:
  EXP-F ── (EXP-A~E + WS-1~6 결과 필요)
  논문 최종 수정 ── (EXP-F 결과 필요)
```