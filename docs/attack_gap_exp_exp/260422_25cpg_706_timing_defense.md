# 25 CPG · 706 시나리오 · Timing 축 — NeurIPS 공격 3종 재검증 방어 문서

**작성일**: 2026-04-22
**대상 공격 3종**:
1. 왜 CPG 가이드라인이 25개뿐인가? 선정 기준 불명확 / 더 쓸 수 있지 않나
2. 706 시나리오가 정말 "의미 있는 최대"인가 (방어 논리 재검증)
3. 경쟁 의료/임상 AI 벤치 중 timing을 평가하는 것이 "하나도 없다"는 주장은 정말 사실인가

**사용자 직관 요약**: 타이밍 평가가 11/11 벤치에서 정말 없다는 주장은 "말이 안 된다". → **정직한 재검증 결과 사용자 직관이 맞았다.** 현재 문구는 엄밀히 틀렸고, 좁은 scope로 리프레이즈 필요.

---

## Q1. 25개 CPG 선정 기준과 "안 쓴" 후보 가이드라인

### 1-1. 암묵적 선정 기준 (논문에 명시적이지 않지만 일관됨)

1. **time-sensitive emergency medicine** — abstract가 "time-sensitive clinical treatment protocols"로 범위를 선언 (`paper/main_final_v17.tex:178`). 만성질환 장기관리·단일결정 진단기준은 구조적으로 제외 (deadline 부재 → TIMING violation 측정 불가).
2. **주요 학회 발행 + sequential decision protocol** — AHA/ACC/ESC/KDIGO/IDSA/SSC/GOLD/GINA/ACG/AES/ADA/WAO/ABA/ACOG/APA. "A → B → C within T" 형태의 순차 프로토콜 필수.
3. **Held-out 5 = domain generalization 보호** — 수혈/화상/산후출혈/초조/소아응급. E4–E7에서 blind-spot 패턴(conditional FA 62.2% vs in-domain 37.1%) 재현 + Spearman 순위 보존 → "memorization/contamination" 공격(A4)에 직접 방어.

### 1-2. "같은 기준을 만족하는데 빠진" 주요 후보 (솔직 목록)

영역별 웹 검증 결과, **Tier S(매우 강한 후보) 10개**가 현재 25개 외에도 존재한다:

| # | 가이드라인 | 기관/연도 | 핵심 deadline / sequence | 등급 |
|---|---|---|---|---|
| 1 | ATLS Primary Survey (ABCDE) | ACS 2018 (10th ed) | golden hour, airway→breathing→circulation 순차 강제 | S |
| 2 | Aortic Dissection | AHA/ACC 2022 | β-blocker 1차 → vasodilator 2차, HR<60 / SBP<120 rapid | S |
| 3 | Post-Cardiac Arrest / TTM | AHA 2023 focused update | TTM initiation <122 min, 32–37.5°C × ≥24h | S |
| 4 | Thyroid Storm | ATA 2016 + JTA 2016 | β-blocker → PTU → iodine (1h gap) → steroid 엄격 순서 | S |
| 5 | HHS (Hyperosmolar) | ADA/EASD 2024 Consensus + JBDS 2023 | 5-phase pathway (0–60 min, 1–6h, …); glucose 감소율 제한 | S |
| 6 | Severe Hyperkalemia | KDIGO 2018 + UKKA 2023 | K>6.5 + ECG → Ca immediate → insulin/dextrose → 제거 | S |
| 7 | Severe Hyponatremia | ESE/ESICM/ERA 2014 + SfE 2022 | 3% NaCl first-hour bolus, ΔNa 4–6 mmol/L, ceiling ≤10/24h | S |
| 8 | Preeclampsia / Severe HTN in pregnancy | ACOG PB 222 (2020) + CMQCC | 중증 BP → IV antihypertensive **30–60 min**, MgSO4 load+maint | S |
| 9 | Aneurysmal SAH | NCS 2023 + AHA/ASA 2023 | aneurysm securing <24h + nimodipine × 21일 | S |
| 10 | Spontaneous ICH | AHA/ASA 2022 | BP treat **<2h** onset, target **<1h**, ΔSBP 상한 | S |

**Tier A(추가 가능, 있으면 좋음) 5개**: BTF 2016 Severe TBI, AHA 2022 Cardiogenic Shock, ATS/ESICM 2023 ARDS, Endocrine Society 2016 Adrenal Crisis, IDSA 2014 + EAST 2018 Necrotizing Fasciitis (debridement <12h).

### 1-3. 25개에서 멈춘 합리적 이유

- **데이터 희소성**: MIMIC-IV demo에 thyroid storm/adrenal crisis/SAH 환자 수가 적음 → 실제 환자 상태 주입 불가.
- **기존 그래프와 의미적 overlap**: 예) ICH는 `aha_stroke.yaml`에, cardiogenic shock은 `aha_heart_failure.yaml`에 부분 포함 가능.
- **Held-out 5개로 이미 generalization 주장 입증** — Tier S 10개 중 절반은 future-work로 명시해도 충분.
- **ATLS처럼 "teamwork concurrent" 프로토콜**은 strict sequential보다 동시실행에 가까워 DAG 모델링 복잡.

### 1-4. 방어 문구 권고

> "The 25 CPGs are not arbitrary — they satisfy three conjunctive criteria (time-sensitivity, major-society issuance, sequential-decision structure). An additional ~10 Tier-S candidates (e.g., ATLS ABCDE, aortic dissection, TTM, thyroid storm, HHS, severe hyperkalemia/hyponatremia, preeclampsia, SAH, ICH) satisfy the same criteria and are explicitly noted as v18 extension targets in Appendix. These were deferred due to (a) MIMIC-IV demo cohort sparsity for rare endocrine emergencies, (b) semantic overlap with existing graphs (ICH ⊂ stroke), and (c) the fact that held-out 5 already provides sufficient generalization evidence."

---

## Q2. 706 시나리오가 "의미 있는 최대"인 이유 + 전체 확장 시 장단점

### 2-1. 706의 유도 (4-axis derivation, `cpg_model/patient_generator.py`)

- Axis 1: 312개 조건부 규칙 × 1 trap
- Axis 2: 경로별 non-trap baseline
- Axis 3: 값 경계 변이 (±2)
- Axis 4: 2–3 규칙 동시 발화 (후보 1,237개)
- Stage 1 환자 컨텍스트 필터 → 81.6% 과생성 제거
- 최종 = 601 자동 + 105 수작업 = **706 = 실무 최대 1,237의 57%**

### 2-2. "더 늘려도 의미 없다"의 4가지 근거

| 축 | 지표 | 해석 |
|---|---|---|
| 제약 포화 | expansion ratio **8.0×** (수작업 6.6제약 → 엔진 53.1제약, `paper/auto_numbers.tex:40-42`) | temporal/completeness 제약이 이미 포화. 추가 시나리오 = 중복 패턴 |
| 통계 검정력 | n = 8 × 706 × 3 = **16,944**, power ≥ 0.80 @ α=0.05 (`exp_cres_5_expansion.py:178-206`) | post-hoc power 포화. 2배 N → effect size 추정오차 <5% 추가 감소뿐 |
| 임상 타당성 | Axis 5 (3-rule 이상 동시) = rare event | 수학적 상한은 의미 있는 임상 ≠ |
| 분포 외삽 | Held-out 1,584 episodes에서 evaluator 상대순위 보존 (Spearman ρ, `heldout_macros.tex`) | 분포 shift 후에도 순위 일관성 → 706이 in-dist 충분성의 경계 |

### 2-3. 25 → 50~100 CPG 확장의 Pros / Cons

**Pros**
- External validity 확대, 도메인 편향(sepsis/chest pain 집중) 완화
- "comprehensive" 주장 강화 (수치 상승이 sales point)
- Held-out N 확대 → ordering preservation 신뢰도 ↑
- Theorem tightness witness 다양성 ↑

**Cons (결정적)**
- **Power 수확 체감**: η²_eval가 이미 MDE를 크게 상회, 추가 N의 detection power 기여 ≈ 0 (`exp_cres_5_expansion.py:316-321`)
- **η²_eval/η²_run > 230× 주장은 25 CPG로 이미 결판남** (`main_final_v17.tex:188,198`)
- **품질관리 비용 선형 폭증**: source traceability + constraint ablation + evidence grading을 CPG마다 재실행 (`main_final_v17.tex:310`)
- **Compute 2배+**: 50 CPG면 에피소드 33k+, GPU-hour 2배인데 effect size 변동 없음
- **Selection bias 공격 증가**: "왜 이 50개인가"라는 새로운 공격벡터 등장
- **유지보수 부담**: SSC/ACLS 개정 시 전체 graph 재검증
- **이론 증명은 CPG 수에 independent**: E1 tightness는 "by construction" (`main_final_v17.tex:331`)

### 2-4. 권장 포지셔닝

> "Current 25 CPGs × 706 scenarios × 16,944 episodes already saturates (i) constraint-derivation headroom (8.0× expansion), (ii) statistical power (post-hoc η² ≫ MDE), and (iii) ordering-preservation under held-out distribution shift. Additional compute is better spent on **MIMIC-IV re-scoring** (`mimicProtocolHash` pre-registered) and **clinician-validated construct evidence (60-episode packet)** — both of which address pre-registered limitations more directly than coverage breadth."

v18에서는 Tier S 10개 중 5개씩 단계적 추가 + held-out 비율 5/25 → 10/35 상향을 제안.

---

## Q3. "경쟁 의료 벤치마크 중 timing 평가가 하나도 없다"는 주장의 정직한 재검증

### 3-1. 결론 (중요: 현재 주장은 **엄밀히 틀렸다**)

CGA-Bench `appendix_tier1-1.tex`의 **"11/11 external benchmarks do not capture timing deadlines"** 주장은 **좁게 보면 대체로 맞지만, 현재 문구대로라면 기술적으로 틀렸고 오해를 부른다.** 사용자의 직관이 정확했다.

**구체적 반례**:
- **MedAgentBench**: "two elevated TSH values ≥7 days apart" 등 **temporal-logic 조건**을 task 정답에 포함. 8-round budget ceiling도 있음. 단, guideline deadline(within 60 min)이 아닌 **conditional timestamp-gating**.
- **PhysioNet Sepsis Challenge 2019**: utility score = early-detection - late-detection - FP. 본질적으로 timing-centric. 단, LLM agent benchmark가 아닌 time-series classification.
- **Harutyunyan 2019 MIMIC-III, ICU-Sepsis, MIMIC-Sepsis**: 시간축 직접 채점하지만 supervised/RL 벤치 (LLM agent 아님).
- **MTBBench**: "longitudinal patient timeline + multi-turn agent" — agent 벤치이면서 시간 다룸. 단 trajectory-level deadline 채점은 아니고 decision correctness 채점. **회색 영역.**

### 3-2. 재검증 표 (핵심)

| # | Benchmark | Timing 평가? | 비고 |
|---|---|---|---|
| 1 | AgentClinic | N | diagnostic accuracy + turn count |
| 2 | MedAgentBench | **부분 (반례성)** | 8-round ceiling + "≥7d apart" temporal-logic 조건 |
| 3 | HealthBench | N | "static offline conversations, no temporal" 명시 |
| 4 | AMEGA | N | 1337 rubric elements |
| 5 | CliBench | N (부분) | "first batch within 24h admission"; deadline 미채점 |
| 6 | MedGUIDE | N | NCCN MCQ, timestamp 없음 |
| 7 | CancerGUIDE | N | pathway concordance |
| 8 | MTBBench | **부분 (회색)** | longitudinal agent, decision correctness로 채점 |
| 9 | EHRStruct | N | 11 structured tasks |
| 10 | LLMEval-Med | N | LLM-as-Judge checklist |
| 11 | NICE RAG eval | N | faithfulness/grounding |
| 12 | MedCalc-Bench | N | 55 calculator tasks |
| 13 | PhysioNet Sepsis 2019 | **Y (강함)** | utility-score timing-centric. LLM agent 아님 |
| 14 | Harutyunyan 2019 MIMIC-III | **Y** | hourly 예측. 전통 ML |
| 15 | MedAlign | 부분 | timeline position bias, deadline 아님 |
| 16 | TIMER-Bench | Y (reasoning) | temporal reasoning, not deadline |
| 17 | ICU-Sepsis / MIMIC-Sepsis | **Y** | RL MDP, 4h timesteps, LLM agent 아님 |
| 18 | MedAgents-Benchmark | N | reasoning |

### 3-3. 진짜 반례 Top 3 (CGA-Bench 주장을 위협하는 것)

1. **MedAgentBench temporal-logic tasks** (NEJM AI, arxiv 2501.14654)
   - "two elevated TSH values ≥7 days apart" 같은 task는 정답 판정에 timestamp 간격 요구
   - 그러나 (a) guideline deadline이 아닌 **conditional-gating**, (b) terminal POST payload 기준 (trace 아님)
   - **→ 논문에 명시 예외로 언급 + "왜 여전히 blind spot인지" 설명 필수**

2. **PhysioNet Sepsis 2019 Challenge** (Reyna 2019)
   - utility-score가 early/late/FP 선형 결합 — 본질적으로 timing-centric
   - 반례로 보이지만 **LLM agent benchmark가 아닌 binary classification stream** → scope 밖

3. **MTBBench** (arxiv 2511.20490)
   - "longitudinal patient timeline + multi-turn agent" — agent 벤치 + 시간
   - trajectory-level deadline 채점 ≠ decision correctness 채점 → 회색

### 3-4. 권장 리프레이징 (방어 가능한 정확한 문구)

**현재 (위험)**:
> "no external benchmark captures timing deadlines"

**권장 (정확 + 방어 가능)**:
> "Among the 11 surveyed **LLM-agent** benchmarks, none score **action-level deadline compliance against published clinical-practice-guideline time windows** (e.g., SSC Hour-1 antibiotic, door-to-balloon ≤90 min). The closest partial exception is MedAgentBench's conditional-interval gating (e.g., `≥7 days apart`), which checks timestamp *relations* within a final POST payload but not guideline-specified deadlines evaluated against an action trace. Time-series ICU benchmarks (PhysioNet Sepsis 2019, Harutyunyan 2019, ICU-Sepsis) do score timing but evaluate supervised/RL policies rather than LLM agents, and therefore fall outside the LLM-agent evaluation-science scope of this work."

### 3-5. 필요한 논문 수정

1. `paper/appendix_tier1-1.tex` — dimension coverage 표에 **"conditional-interval ≠ CPG-deadline"** 각주 추가
2. 본문의 timing 차별화 서술에 **scope qualifier "among LLM-agent benchmarks scoring CPG adherence"** 삽입 (3군데 정도)
3. `appendix` 벤치 survey 표에 MedAgentBench의 temporal-logic 항목을 **"partial: conditional-interval"**로 표기 (현재 ✗ 표기는 정확하지 않음)
4. Related Work에 PhysioNet/Harutyunyan을 "time-series ICU benchmarks (different scope)" 박스로 명시 — 리뷰어가 "이런 거 있잖아" 공격 시 선제 방어

---

## 종합 방어 포지셔닝 (한 장 요약)

| 공격 | 현재 주장 상태 | 수정 필요 여부 |
|---|---|---|
| Q1. 25개 기준 | 암묵적 3-criteria 일관됨 | **경미**: Tier S 10개를 future-work로 appendix에 명시 |
| Q2. 706 최대 | 4-지표(제약포화/power/임상타당성/순위보존) 방어 가능 | **없음**: 현재 논리 유지, 확장 compute는 MIMIC-IV re-scoring에 투입 |
| Q3. Timing 0/11 | **엄밀히 틀림** | **필수**: scope qualifier 삽입 + MedAgentBench 반례 명시 |

**가장 급한 작업**: Q3의 리프레이징. 현재 본문·appendix 문구 그대로 제출하면 NeurIPS 리뷰어 중 MedAgentBench/PhysioNet Sepsis 친숙한 사람이 반례를 꺼낼 가능성이 높음. 1일 작업으로 해결 가능.

---

## 관련 파일

- `/home/anonymous-org/anonymous-project/AnonProject/cga_bench/paper/main_final_v17.tex`
- `/home/anonymous-org/anonymous-project/AnonProject/cga_bench/paper/appendix_tier1-1.tex`
- `/home/anonymous-org/anonymous-project/AnonProject/cga_bench/paper/auto_numbers.tex`
- `/home/anonymous-org/anonymous-project/AnonProject/cga_bench/evidence_pack/heldout_v1/heldout_macros.tex`
- `/home/anonymous-org/anonymous-project/AnonProject/cga_bench/cpg_model/patient_generator.py`
- `/home/anonymous-org/anonymous-project/AnonProject/cga_bench/scripts/experiments/exp_cres_5_expansion.py`
- `/home/anonymous-org/anonymous-project/AnonProject/cga_bench/assessor_core/violations.py` (TIMING 구현)

## 주요 외부 출처

- [NEJM AI MedAgentBench](https://ai.nejm.org/doi/full/10.1056/AIdbp2500144), [arxiv 2501.14654](https://arxiv.org/abs/2501.14654)
- [PhysioNet Sepsis Challenge 2019](https://physionet.org/content/challenge-2019/1.0.0/)
- [Harutyunyan MIMIC-III Benchmark](https://www.nature.com/articles/s41597-019-0103-9)
- [MTBBench](https://arxiv.org/abs/2511.20490)
- [SSC 2021 Guidelines (Intensive Care Medicine)](https://doi.org/10.1007/s00134-021-06506-y)
- [ATA 2016 Hyperthyroidism/Thyroid Storm](https://www.liebertpub.com/doi/full/10.1089/thy.2016.0229)
- [ADA 2024 Hyperglycemic Crises Consensus (HHS)](https://diabetesjournals.org/care/article/47/8/1257/156808)
- [AHA/ASA 2022 Spontaneous ICH](https://www.ahajournals.org/doi/10.1161/STR.0000000000000407)
- [ACOG PB 222 Preeclampsia](https://www.acog.org/clinical/clinical-guidance/practice-bulletin/articles/2020/06/gestational-hypertension-and-preeclampsia)
