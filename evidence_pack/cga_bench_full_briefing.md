> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# CGA-Bench Full Briefing

*Last updated: 2026-04-02 | Branch: eval_science*

다른 세션에서 이 문서 하나만 읽고 프로젝트 전체를 파악할 수 있도록 작성됨.

---

## 1. 한 줄 요약

CGA-Bench는 LLM 의료 에이전트가 임상 가이드라인(CPG)의 시간·순서·안전 제약을 준수하는지 평가하는 trajectory-level conformance benchmark로, 기존 task-completion 메트릭이 놓치는 process-level 결함을 정량화한다.

---

## 2. 세 가지 진짜 Novelty

### 2.1 Trajectory-Level Conformance
기존 벤치마크(MedQA, HealthBench, AgentClinic)는 "정답을 맞혔는가"를 평가. CGA-Bench는 "정답에 도달하는 과정이 임상적으로 안전한가"를 평가.

- 5가지 violation: OMISSION (필수 행위 누락), COMMISSION (금기 행위), TIMING (시간 초과), SEQUENCE (순서 위반), DEVIATION (프로토콜 이탈)
- 7개 Q2 에피소드 (C2>=0.7 threshold): task completion = PASS이지만 CGA = FAIL → 기존 메트릭으로는 발견 불가능한 결함

### 2.2 Executable Guideline Grading
YAML 기반 CPG 그래프가 실행 가능한 형태로 가이드라인을 인코딩:
```
G(s_t) → (A_G: allowed, M_G: mandatory, F_G: forbidden, D_G: deadlines)
```
- 13개 도메인, 14개 CPG YAML 파일 (7 core + 7 expansion)
- 16개 시나리오 파일 (anticoagulant interaction 포함)
- 92개 timing constraint with evidence strength (38% RCT-backed)
- Scoring-Agent 분리: 에이전트는 채점 엔진에 접근 불가 (evaluation leakage 방지)
- 12개 독립 agent rules (sepsis, chest_pain, stroke, heart_failure, aki, dka, pe, af, copd, gi_bleeding, htn_emergency + decision_table)

### 2.3 Metric-Mismatch Audit
CGA Score만으로는 conservative strategy를 과대평가. Composite metric으로 해결:
- CGA alone: p=0.2046 (ns) — 모델 간 순위 구별 불가
- **Composite A: p=8.125e-05 (highly significant)** — Holm-corrected p=1.625e-04
- Per-run replication: 모든 3개 run 개별적으로 significant (p < 0.002)
- LOSO stability: 15/15 시나리오 제거 시 모두 significant (p range: [2.78e-05, 2.86e-04])
- **주의**: 공식은 하나 `CGA × min(1, acts/(exp×2))`. `composite_formula_comparison.md` 참조

---

## 3. 실험 결과

### 3.1 Internal: 16 Scenarios x 4 Models x 3-Run (Post-R1-R5, 180 Episodes)

**Data Provenance**: `results/clean_slate_rescored/` (4 models x 15 scenarios x 3 runs = 180 episodes)

| Model | Identity | Params | CGA Mean | CGA Std | Comp A Mean | Comp A Std |
|-------|----------|--------|----------|---------|-------------|-----------|
| oss120b | DeepSeek-V3-0324 | 120B | **0.5072** | 0.2142 | **0.5054** | 0.2147 |
| qwen27b | DeepSeek-R1-Distill-Qwen-32B | 27B | 0.4447 | 0.2368 | 0.3909 | 0.2452 |
| qwen35b | Qwen3.5-35B-A3B | 35B | 0.4389 | 0.2269 | 0.4150 | 0.2269 |
| qwen4b | Qwen3-4B | 4B | 0.4316 | 0.2243 | 0.3175 | 0.2028 |

- Perfect CGA episodes: **0** (no model achieves CGA=1.0 under strict scoring)
- Composite A ranking: oss120b > qwen35b > qwen27b > qwen4b

**Sub-Construct Profiles (C1-C5)**:
| Model | C1 Path | C2 Mandatory | C3 Forbidden | C4 Timing | C5 Sequence |
|-------|---------|-------------|-------------|----------|------------|
| oss120b | 0.667 | **0.616** | 0.867 | 0.852 | 1.000 |
| qwen27b | 0.754 | 0.563 | 0.867 | 0.902 | 1.000 |
| qwen35b | 0.703 | 0.558 | 0.867 | 0.903 | 1.000 |
| qwen4b | **0.789** | 0.524 | 0.867 | **0.927** | 1.000 |

- C3 (Forbidden Avoidance): 모든 모델 동일 (0.867)
- C5 (Sequence Integrity): 모든 모델 동일 (1.000)
- C2 (Mandatory Completion): 유일하게 개별적으로 significant (chi2=9.55, p=0.023)

### 3.2 Statistical Tests (Post-R1-R5)

| Test | chi2 | p-value | Significant? | Notes |
|------|------|---------|-------------|-------|
| **Composite A (Friedman)** | **21.54** | **8.125e-05** | **Yes** | epsilon2=0.479 |
| CGA alone (Friedman) | 4.59 | 0.205 | No | -- |
| Holm-corrected Comp A | -- | **1.625e-04** | **Yes** | Family size=2 |

**Bootstrap 95% CI (Composite A, 10K resamples)**:
| Model | Point | 95% CI |
|-------|-------|--------|
| oss120b | 0.505 | [0.397, 0.607] |
| qwen35b | 0.415 | [0.300, 0.527] |
| qwen27b | 0.391 | [0.269, 0.513] |
| qwen4b | 0.318 | [0.217, 0.418] |

**Kendall's W** = 1.0000 (perfect rank agreement across 5 weight profiles)

### 3.3 Cross-Benchmark Comparison (17,784 episodes, corrected)

| Benchmark | Episodes | Original Discordant | Corrected |
|---|---|---|---|
| AgentClinic | 321 | 51.5% | **12.5%** |
| HealthBench | 5,000 | 89.7% | **30.1%** |
| MedChain | 12,163 | 31.8% | 31.8% |
| MedAgentBench | 300 | N/A | N/A (scope외) |
| **Aggregate** | **17,784** | **68.6%** | **28.9%** |

### 3.4 Evaluation Science Experiments

| Experiment | Result | Status |
|---|---|---|
| Exp A: Perturbation sensitivity | 9/9 detected (100%), 4-9%p drop | Done |
| Exp B: Clinician validation | 25 pairs ready, React UI deployed, IRB protocol drafted | Awaiting responses |
| Exp C: 4-Quadrant | Q2=7 episodes (C2>=0.7 threshold) | Done |
| Exp D: Actionability | targeted 0%, cross-dim coupling in DKA | Done |
| Exp E: Scoring sensitivity | Kendall's W=1.000 | Done |

### 3.5 BSR (Blind-Spot Rate) — B2 Jaccard Baseline

| Perturbation | BSR (all) | BSR (high) | N Valid | 95% CI (all) |
|-------------|-----------|-----------|---------|-------------|
| P1 DELAY | 10.6% | 12.9% | 180 | [3.3%, 18.3%] |
| P2 SWAP | 16.7% | 16.7% | 36 | [0.0%, 25.0%] |
| P3 DEVIATION | 18.2% | 9.7% | 159 | [7.6%, 30.6%] |
| P4 COMMISSION | 0.0% | 0.0% | 96 | [0.0%, 0.0%] |
| P5 OMISSION | 0.0% | 0.0% | 180 | [0.0%, 0.0%] |

### 3.6 Discriminant Validity

| Definition | r | p-value | N |
|-----------|---|---------|---|
| **C2 >= 0.7** | **0.700** | **8.43e-28** | 180 |
| C2 >= 1.0 | 0.230 | 1.89e-03 | 180 |
| Spearman CGA vs C2 | 0.820 | 6.37e-45 | 180 |
| Spearman CGA vs Coverage | 0.260 | 4.31e-04 | 180 |

- **WARNING**: r=0.70 indicates moderate-to-high correlation, NOT orthogonality
- Coverage (r=0.26)는 가장 독립적인 construct

---

## 4. 기술 스택

### Architecture
```
┌─────────────────────────────┐   ┌──────────────────────────────┐
│   SCORING (Agent 접근 금지)   │   │   AGENT (Agent 접근 가능)     │
│                             │   │                              │
│  cpg_engine/    CPG 그래프    │   │  agent_runner/  RAG/Planner  │
│  assessor_core/ 위반 추출     │   │  agent_rules/   독립 규칙     │
│  cpg_model/graphs/ YAML     │   │  tool_api/      시나리오 API  │
└─────────────────────────────┘   └──────────────────────────────┘
              ↓                              ↓
        ┌─────────────────────────────────────────┐
        │  eval_harness/  실험 오케스트레이션      │
        │  semantic_layer/ 외부 벤치마크 어댑터     │
        │  clinician_validation/ 임상 검증 플랫폼  │
        │  clinician_survey/ 임상 설문 (25 cases)  │
        └─────────────────────────────────────────┘
```

### Key Components
- **CPG Engine**: YAML → `G(s_t) → (A, M, F, D)` 평가
- **ViolationExtractor**: episode log → 5종 violation 추출
- **HarmScorer**: violation → CGA Score (C1-C5 sub-constructs)
- **DualTrack Evaluator**: Track A (action coverage) x Track B (CPG compliance) x Safety Gate
- **ActionNormalizer**: 500+ 매핑 + Jaccard similarity fuzzy matching
- **RAGAgent**: BM25/Dense/Hybrid retrieval + vLLM (budget-matched)
- **OracleAgent**: cpg_engine 독립 규칙 기반 upper bound
- **Clinical Interaction Detector**: 약물 상호작용 감지
- **DKA Violation Detector**: DKA 특화 위반 감지
- **Event Sourcing**: 불변 이벤트 로그 + XES/OCEL 내보내기

### LLM Backends
- vLLM (DeepSeek-V3-0324 120B, DeepSeek-R1-Distill-Qwen-32B, Qwen3.5-35B-A3B, Qwen3-4B)
- OpenAI GPT-4o (reference, config ready)
- Anthropic Claude 3.5 (reference, config ready)
- Mock (testing)

### Code Scale
- **Source code**: ~67,600 lines (cpg_engine + cpg_model + assessor_core + agent_runner + agent_rules + scenario_engine + eval_harness + semantic_layer + tool_api)
- **Test code**: ~51,000 lines (138 test files, 28 test directories)
- **Scripts**: 63 Python scripts + CI/CD

---

## 5. 정직한 약점

### 해결됨 (2026-04-01, R1-R5 Fixes)
| Issue | Fix | Impact |
|---|---|---|
| R1: Oracle upper-bound range 71-100% | Corrected to 20-100% | 범위 정확도 |
| R2: DeepSeek-R1-7B episode count 10 | Corrected to 54 episodes | 데이터 정확도 |
| R3: Composite formula saturation 67% | Corrected to 90% (k=2 formula) | 공식 정확도 |
| R4: "Two formulas" claim | Single formula 확인, 문서 정리 | 일관성 |
| R5: Friedman p-value scope confusion | Single-run vs multi-run 명확화 | 통계 정확도 |
| AgentClinic AKI 오탐지 | `\baki\b` word boundary | 51.5% → 12.5% |
| HealthBench 89.7% 과장 | 50-sample 수동 분류 | 89.7% → 30.1% |

### 미해결 (논문에서 limitation으로 기술)
| Issue | Status | Paper Language |
|---|---|---|
| Cross-comparison은 metric proxy | 인정 | "Task Completion proxy, not exact reproduction" |
| MedChain 99.8% general fallback | 인정 | "Limited domain-specific signal" |
| Perturbation = synthetic baseline | 인정 | "Sensitivity analysis, not empirical LLM finding" |
| Sequence FM = Q2에서 0 | 구조적 | "Pure sequence violations co-occur with omission" |
| MedAgentBench = FHIR ops | 범위 밖 | "Outside CGA evaluation scope" |
| HealthBench keyword FP rate ~73% | 보고 | "Action keyword matching has inherent limitations" |
| Clinician validation 미완료 | 대기중 | IRB protocol 준비 완료, 응답 대기 |
| Proprietary model 결과 없음 | 예산 제약 | GPT-4o/Claude API 비용 ~$17 필요 |

---

## 6. 학회별 부족한 점

### NeurIPS (Datasets & Benchmarks Track)
- ✅ Novelty: trajectory-level conformance, process evaluation
- ✅ Scale: 17,784 cross-benchmark episodes + 180 internal episodes
- ✅ Statistical rigor: Friedman p=8.125e-05, Holm-corrected, LOSO 15/15, per-run 3/3
- ✅ Release package: cga-bench-release/ (MIT license, README, pyproject.toml, checksums)
- ✅ Data release v1.0: Croissant metadata, annotation protocol, data governance
- ⚠️ Clinician validation 미완료 (25 pairs + IRB protocol ready, responses pending)
- ⚠️ Inter-rater reliability 아직 없음 (Krippendorff alpha pipeline만 준비)
- ⚠️ Proprietary model baselines 없음 (GPT-4o, Claude)

### AAAI / ICML
- ⚠️ Formal verification 부재 (CPG 그래프가 가이드라인과 일치하는지 clinician 검증 필요)
- ⚠️ Larger model evaluation 부재 (GPT-4, Claude 3.5 결과 없음 — API 비용)

### Domain-Specific (JAMIA, npj Digital Medicine)
- ⚠️ Real patient data 없음 (MIMIC-IV demo만 사용)
- ⚠️ Clinician co-author 필요
- ⚠️ IRB 미진행

---

## 7. 확장 방향

1. **Clinician validation 완료** (Exp B) → inter-rater reliability 확보
2. **GPT-4o / Claude baseline** 추가 → 상위 모델과의 비교 (~$17 예산 필요)
3. **Adversarial trap scenarios** 추가 완료 (3개: anticoagulant interaction, euglycemic DKA, contrast AKI nephrotoxin)
4. **HealthBench scoring 개선** → keyword-mandatory 기반으로 개선
5. **MedChain domain detection** 강화 → 중국어 의료 텍스트 도메인 매칭
6. **Real patient simulation** → MIMIC-IV full dataset 연동
7. **Multi-agent evaluation** → 2+ agent collaboration 시나리오

---

## 8. 파일 구조

```
cga_bench/
├── cpg_engine/              # CPG 그래프 평가 엔진
├── cpg_model/
│   ├── graphs/              # 14개 YAML CPG 그래프
│   └── schemas/             # Action, PatientState 등 데이터 타입
├── assessor_core/           # ViolationExtractor, HarmScorer, DualTrack, ActionNormalizer
│   ├── violations.py        # 5가지 위반 유형 추출
│   ├── harm_scorer.py       # CGA Score 산출
│   ├── dual_track_evaluator.py  # Track A x Track B x Safety Gate
│   ├── action_normalizer.py # 500+ 매핑 + fuzzy matching
│   ├── evaluation_loop.py   # 평가 루프 오케스트레이션
│   ├── event_log.py         # 불변 이벤트 소싱
│   ├── clinical_interaction_detector.py  # 약물 상호작용 감지
│   ├── episode_risk_scorer.py  # 에피소드 위험 점수
│   └── dka_violation_detector.py  # DKA 특화 위반 감지
├── agent_runner/            # RAGAgent, PlannerAgent, ReflectionAgent, OracleAgent
│   └── llm_provider.py     # 멀티 LLM 백엔드 (OpenAI/Anthropic/vLLM/Mock)
├── agent_rules/             # 독립 decision table (12개 도메인 규칙)
│   ├── decision_table.py    # 추상 클래스
│   ├── sepsis_rules.py      # SSC 2021
│   ├── chest_pain_rules.py  # AHA 2021
│   ├── stroke_rules.py      # AHA 2019
│   ├── heart_failure_rules.py  # AHA 2022
│   ├── aki_rules.py         # KDIGO AKI
│   ├── dka_rules.py         # ADA DKA
│   ├── pe_rules.py          # ESC PE 2019
│   ├── af_rules.py          # ESC AF 2020
│   ├── copd_rules.py        # GOLD COPD 2024
│   ├── gi_bleeding_rules.py # ACG GI Bleeding 2023
│   └── htn_emergency_rules.py  # AHA HTN Crisis 2017
├── scenario_engine/         # 임상 시뮬레이션 환경 (Gym-like interface)
├── eval_harness/            # 실험 러너, 예산 관리, 공정성 검증
├── semantic_layer/
│   ├── external/            # 외부 벤치마크 어댑터 (22개 파일)
│   │   ├── healthbench*.py  # HealthBench 4-module 확장 (DAR, Quality, Integration)
│   │   ├── agentclinic.py, medchain.py, medagentbench.py
│   │   ├── closed_loop_evaluator.py, domain_detector.py
│   │   └── art.py, agentehr.py  # ART, AgentEHR 어댑터
│   ├── conformance/         # Declare 적합성 검사 (13 files)
│   ├── export/              # XES/OCEL/MTL 내보내기 (7 files)
│   ├── ontology/            # 의학 온톨로지 매핑 (19 files)
│   └── terminology/         # 의학 용어 체계 (5 files)
├── env/                     # 환경 어댑터 (AgentClinic, MedAgentBench, MedChain, ArchEHR-QA)
├── testing/                 # E2E 테스트 인프라, Mock provider
├── data_release/v1.0/       # Croissant 메타데이터, 주석 프로토콜, 데이터 거버넌스
├── clinician_validation/    # React 기반 임상 검증 플랫폼 (Exp B)
├── clinician_survey/        # 임상 설문 (25 cases, IRB protocol)
├── configs/
│   ├── scenarios/           # 16개 시나리오 YAML (anticoagulant interaction 포함)
│   ├── agents/              # 24개 에이전트 설정 YAML
│   └── experiments/         # 14개 실험 설정 YAML
├── scripts/                 # 63개 Python 스크립트 + CI/CD
│   ├── ci/                  # audit_sources, audit_citations, leakage_scan, validate_cpg_schema
│   ├── repro/               # 환경 기록, 시드 관리
│   └── *.py                 # 분석, 결과 생성, 통계 검증
├── tests/                   # 138 test files, 28 directories
├── evidence_pack/           # 모든 분석 결과
│   ├── FINAL_NUMBERS_CONFIRMED.md  # Post-R1-R5 확정 수치
│   ├── VERDICT_TABLE.md     # Claim별 verdict
│   ├── analysis/            # 75개 분석 파일 (JSON + MD)
│   ├── experiments/         # clinician materials, perturbation, actionability
│   ├── tables/              # 16개 LaTeX 테이블
│   ├── figures/             # 15개 PDF 그림
│   └── external_benchmarks/ # AgentClinic 321 episodes
├── cga-bench-release/       # 공개 릴리스 패키지 (MIT license, 339 files)
├── results/                 # 실험 결과 JSON
├── run_benchmark.py         # 내부 벤치마크 실행
├── run_external_benchmark.py # 외부 벤치마크 실행
├── run_neurips_experiment.py # NeurIPS 실험 실행
├── KNOWN_ISSUES.md          # 반복 문제 패턴 + 체크리스트
└── CHANGELOG.md             # 버전별 변경 이력
```

---

## 9. 핵심 숫자

> 모든 숫자는 `results/clean_slate_rescored/` 180 에피소드에서 직접 계산됨.
> 참조: `evidence_pack/FINAL_NUMBERS_CONFIRMED.md`

| Category | Key Number | Source |
|---|---|---|
| 내부 시나리오 | 16 scenarios (15 evaluated + 1 anticoagulant), 13 domains | configs/scenarios/ |
| 내부 에피소드 | 180 (4 models x 15 scenarios x 3 runs) | clean_slate_rescored/ |
| CPG 그래프 | 14 YAML files (7 core + 7 expansion) | cpg_model/graphs/ |
| Agent 규칙 | 12 domain rule files | agent_rules/ |
| Agent 설정 | 24 YAML configs | configs/agents/ |
| Friedman Composite A | p=8.125e-05 (multi-run), Holm p=1.625e-04 | FINAL_NUMBERS_CONFIRMED.md |
| CGA alone (Friedman) | p=0.205 (ns) | FINAL_NUMBERS_CONFIRMED.md |
| LOSO stability | 15/15 significant (p < 0.0003) | FINAL_NUMBERS_CONFIRMED.md |
| Per-run replication | 3/3 significant (p < 0.002) | FINAL_NUMBERS_CONFIRMED.md |
| Kendall's W | 1.000 (5 weight profiles) | FINAL_NUMBERS_CONFIRMED.md |
| Q2 에피소드 | 7 (C2>=0.7 AND CGA<0.5) | FINAL_NUMBERS_CONFIRMED.md |
| Bootstrap CI (oss120b Comp A) | [0.397, 0.607] | FINAL_NUMBERS_CONFIRMED.md |
| Timing constraints | 92 (38% RCT-backed) | timing_evidence.json |
| Cross-benchmark | 17,784 episodes, 28.9% corrected discordant | cross_comparison_17k.json |
| Tests | 138 files, 28 directories | tests/ |
| Source code | ~67,600 lines | cpg_engine ~ tool_api |
| Test code | ~51,000 lines | tests/ |
| Evidence pack | 75 analysis + 16 tables + 15 figures | evidence_pack/ |
| Release package | 339 files, MIT license | cga-bench-release/ |
| Clinician survey | 25 cases (20 unsafe + 5 safe controls) | clinician_survey/ |
| Scripts | 63 Python scripts | scripts/ |

---

## 10. 다른 LLM에게 요청 가능한 조언 목록

이 프로젝트의 코드와 데이터를 보지 않은 LLM에게 아래 질문을 할 수 있다:

1. **"CGA Score만으로 Friedman non-significant인데 Composite는 highly significant (p=8e-05). 이걸 논문에서 어떻게 framing해야 하는가?"** — 핵심 metric design 논의
2. **"Task completion = C2 >= 0.7 proxy의 한계를 인정하면서도 necessity argument를 유지하는 논문 구조는?"** — limitation section 작성
3. **"7개 Q2 에피소드 중 path selection failure가 dominant failure mode. 통계적 충분성은?"** — 통계적 검정력
4. **"Cross-benchmark 28.9% discordant에서 MedChain 99.8% general fallback을 제외하면 의미 있는 숫자인가?"** — external validity
5. **"Clinician validation에서 Krippendorff alpha가 0.6 미만이면 어떤 fallback 전략이 있는가?"** — Exp B contingency
6. **"Scoring sensitivity Kendall's W=1.0이 '모든 가중치에서 동일 순위'인데, 이게 장점인가 아니면 metric이 둔감하다는 신호인가?"** — metric sensitivity 해석
7. **"Perturbation 9/9 detection을 sensitivity analysis로 frame할 때, reviewer가 '이건 tautology 아닌가'라고 물으면 어떻게 답하는가?"** — reviewer Q&A 준비
8. **"C3 (0.867) / C5 (1.000)이 모든 모델에서 동일 — 이게 benchmark의 한계인가 아니면 모델 특성인가?"** — sub-construct 해석
9. **"NeurIPS Datasets track에서 'reproducibility'를 강조하려면 어떤 artifact를 제출해야 하는가?"** — submission checklist (cga-bench-release 존재)
10. **"LOSO 15/15 significant + per-run 3/3 significant를 어떻게 논문에서 보고하는 것이 가장 효과적인가?"** — robustness reporting

---

## 11. 버전 이력 요약

| Version | Date | Key Changes |
|---------|------|-------------|
| 0.2.0 | 2026-03-25 | DualTrack scoring, 6 clinical domains, golden tests, event sourcing |
| 0.3.0 | 2026-04-01 | 15 scenarios, 7 expansion CPG graphs, clean slate experiments, bootstrap CIs, HealthBench extension |
| Unreleased | 2026-04-02 | 3 adversarial traps, BSR pipeline, R1-R5 fixes, release package, clinician survey |
