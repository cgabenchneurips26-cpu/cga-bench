# CGA-Bench 필수 실험 — Claude Code 프롬프트 (검토 수정판)

> 우선순위: P0 (제출 전 반드시) → P1 (강력 권장) → P2 (카메라레디)
> 각 프롬프트는 독립 실행 가능하며, 순서대로 실행을 권장
>
> **수정 이력**: 초판 대비 주요 수정사항
> - P0-1: 데이터 소스 경로를 원본 에피소드 기반으로 수정, `exp` 값 출처 명시
> - P0-2: post-hoc power analysis의 학술적 논쟁 반영하여 시뮬레이션 기반으로 전환, BCa → percentile CI로 변경 (n=3 불안정 해소)
> - P0-3: 부분-전체 상관(part-whole correlation) 문제 수정, 레이더 차트 정규화 명시
> - P0-4: 자의적 "평가 축 공식" 삭제, 차원별 개별 보고로 변경
> - P1-1: 데이터 존재 확인을 Step 0으로 추가, 단일 리뷰어 한계 인정
> - P1-2: 반사실 분석을 구체적 알고리즘으로 재정의

---

## P0-1. 다중 비교 보정 + 전체 k-space 민감도 분석

**왜 필수인가:** 리뷰어가 "p=0.043은 k=2.0에서만 유의한 거 아닌가?"라고 물으면, 전체 k-space 그래프 하나로 답할 수 있어야 한다.

```
프로젝트 코드베이스를 분석하여 다음 실험을 구현하고 실행해줘.

## 목표
Composite metric의 k 파라미터에 대한 전체 민감도 분석 + 다중 비교 보정

## 배경
- 현재 composite formula: `CGA × min(1, acts/(exp×k))` 에서 k=2.0일 때 Friedman p=0.043
- k=1.9에서 p=0.073 (ns), ÷exp (k=1.0) 에서 p=0.66 (ns)
- 리뷰어 비판: "k=2.0은 사후 최적화(post-hoc optimization) 아닌가?"

## 데이터 소스 (중요 — 정확한 경로 확인 필요)
- **원본 에피소드 결과**: `results/` 디렉토리 하위의 모델별 폴더에서
  에피소드별 CGA Score, action 수, violation 상세를 직접 로드
- **expected_actions 수(exp)**: 각 시나리오의 `configs/scenarios/*.yaml`에서
  `expected_actions` 리스트의 길이로 계산. 시나리오별로 다름에 주의
- **집계 참조용**: `evidence_pack/analysis/composite_metric.json`,
  `composite_formula_comparison.md` — 교차 검증용으로만 사용
- 만약 원본 에피소드 파일 구조를 파악하기 어려우면, 먼저 `results/` 디렉토리의
  파일 구조를 탐색하고 어떤 JSON 필드에 CGA Score와 action count가 있는지 확인해줘

## 구현 사항

### Step 1: 데이터 로드 및 검증
- `results/` 에서 4개 모델(oss-120b, Qwen3.5-35B, oss-20b, Qwen3-4B)의
  15 scenarios × 3 runs 에피소드 데이터 로드
- 각 에피소드에서 추출: cga_score, total_actions, scenario_id
- `configs/scenarios/*.yaml`에서 scenario_id별 expected_actions 수 추출
- **검증**: 집계 결과가 `composite_metric.json`의 수치와 일치하는지 확인

### Step 2: k-space 스윕
- k = 0.5 ~ 4.0 범위를 0.1 단위로 스윕 (36개 포인트)
- 각 k에서:
  - Composite = CGA × min(1, acts / (exp × k)) 계산 (에피소드별)
  - **Primary 분석**: 3 runs의 scenario별 평균을 먼저 구한 뒤 (multi-run means),
    4 models × 15 scenarios 행렬에 대해 Friedman 검정
  - **Secondary 분석**: single-run (run 1만) Friedman 검정
  - Effect size: epsilon-squared = χ² / (n(k-1)) 계산
  - 각 모델의 평균 composite score 기록

### Step 3: 다중 비교 보정
- **사전 정의된(pre-specified) 4개 테스트**로 한정:
  (a) CGA alone — Friedman
  (b) Composite A with k=1.0 (÷exp) — Friedman
  (c) Composite A with k=2.0 (÷(exp×2)) — Friedman
  (d) Composite B (harmonic mean of CGA and Coverage) — Friedman
- Bonferroni-Holm 보정 (familywise error α=0.05)
- Benjamini-Hochberg FDR 보정 (병행 보고)
- **주의**: k-space 스윕의 36개 테스트에는 보정을 적용하지 않음
  (이는 탐색적 시각화이며, 4개 사전정의 테스트만이 확인적 분석)

### Step 4: 시각화 + 출력
- Figure 1: k vs p-value 곡선 (horizontal lines at α=0.05, Holm-corrected α)
  - multi-run과 single-run을 두 라인으로 표시
- Figure 2: k vs effect size (epsilon-squared) 곡선
  - 핵심: "p-value는 k에 민감하지만 effect size는 안정적인가?"
- Figure 3: k vs 각 모델 평균 composite score (4개 라인)
- 보정 전/후 p-value 비교 테이블 (LaTeX format)

### Step 5: 핵심 서사 도출
다음 질문에 구체적으로 답하는 summary 생성:
- "k=2.0이 유의한 유일한 점인가?" → k-space 곡선에서 답
- "effect size는 k에 걸쳐 안정적인가?" → p가 불안정해도 effect size가 안정적이면
  "표본 크기 부족으로 p가 불안정한 것이지, 효과 자체가 없는 것이 아니다"라고 주장 가능
- "보정 후에도 유의한 결과가 있는가?" → 없으면, effect size 중심 보고로 전환

## 기술 제약
- scipy.stats.friedmanchisquare 사용
- statsmodels.stats.multitest.multipletests 사용 (method='holm', method='fdr_bh')
- matplotlib로 publication-quality 그래프 (300 dpi, serif font)
- 기존 코드의 composite 계산 로직을 최대한 재사용 (중복 구현 금지)

## 산출물
1. `scripts/experiments/k_space_sensitivity.py` — 재현 가능한 스크립트
2. `evidence_pack/analysis/k_space_sensitivity.json` — 전체 결과
3. `evidence_pack/tables/multiple_comparison_correction.tex` — LaTeX 테이블
4. `evidence_pack/figures/k_space_pvalue.pdf` — p-value 곡선
5. `evidence_pack/figures/k_space_effect_size.pdf` — effect size 곡선
```

---

## P0-2. 부트스트랩 신뢰구간 + 필요 표본 크기 시뮬레이션

**왜 필수인가:** "단일 실행 결과에 에러바 없음"은 NeurIPS에서 가장 흔한 거절 사유 중 하나.

```
프로젝트 코드베이스를 분석하여 다음 실험을 구현하고 실행해줘.

## 목표
모든 주요 메트릭에 대한 부트스트랩 95% CI + 필요 시나리오 수 시뮬레이션

## 배경
- 4 models × 15 scenarios × 3 runs = 180 에피소드 (일부 추가 존재, 239+)
- 현재 point estimate만 보고, CI 없음

## 주의사항 — Post-hoc Power Analysis에 대한 학술적 논쟁
- 관측된 effect size로 사후 검정력을 계산하면 p-value의 단조 변환에 불과하다는
  비판이 존재 (Hoenig & Heisey 2001, "The Abuse of Power")
- 따라서 "achieved power = X%"를 보고하는 대신, 다음으로 대체:
  (a) 관측된 효과 크기가 "의미 있는" 수준인지 해석적으로 판단
  (b) 시뮬레이션으로 "80% 검정력을 달성하려면 시나리오가 몇 개 필요한가" 계산
  → 이것은 미래 연구 설계를 위한 정보이므로 학술적으로 적절

## 구현 사항

### Step 1: 원본 에피소드 데이터 수집
- `results/` 디렉토리에서 4개 모델의 에피소드별 결과 로드
- 각 에피소드에서: CGA Score, Coverage, Composite A (k=2.0), Actions/ep, Efficiency
- 데이터 구조: model × scenario × run → metric values

### Step 2: 부트스트랩 95% CI
- **리샘플링 단위: scenario** (Friedman 검정의 블록 구조와 일관)
  - 15개 시나리오에서 15개를 복원추출 (scenario-level bootstrap)
  - 각 리샘플에서 모델별 평균 메트릭 계산
- **3 runs 처리**: 각 시나리오의 3 runs 평균을 먼저 구한 뒤 부트스트랩
  (run 내 변동은 시나리오 내 노이즈로 취급)
- **CI 방법: percentile method** (BCa는 n=15에서 가속도 추정이 불안정하므로 사용 안 함)
- 10,000회 리샘플링
- 모델 간 pairwise 차이에 대한 CI도 계산 (6쌍)

### Step 3: 필요 시나리오 수 시뮬레이션 (Post-hoc Power 대체)
- 관측된 데이터로부터 모델 간 효과 구조(scenario-level score 분포)를 추정
- Monte Carlo 시뮬레이션:
  - n = 10, 15, 20, 25, 30, 40, 50 시나리오
  - 각 n에서 10,000회 시뮬레이션
  - 각 시뮬레이션에서 Friedman 검정 수행, p<0.05 비율 = 추정 검정력
- 결과: n vs 추정 검정력 곡선
- **보고 문구**: "현재 관측된 효과 크기에서, Friedman 검정이 80% 확률로
  유의한 결과를 산출하려면 약 N개 시나리오가 필요하다"

### Step 4: 결과 포맷
- 메인 테이블: Model × Metric (점추정 [95% CI]) — LaTeX
  ```
  | Model      | CGA Score       | Composite A     | Coverage        |
  |------------|-----------------|-----------------|-----------------|
  | oss-120b   | 0.664 [.61,.72] | 0.620 [.57,.67] | 2.052 [1.8,2.3] |
  ```
- 모델 간 pairwise 차이 테이블: 6쌍 각각의 차이 [95% CI]
  → CI가 0을 포함하면 "통계적으로 구별 불가" 명시
- 시나리오 수 vs 검정력 곡선 (Figure)
- 해석 paragraph: limitation section 삽입용

## 기술 제약
- numpy 기반 부트스트랩 (간단한 구현이면 충분, sklearn 불필요)
- matplotlib로 검정력 곡선 + CI가 포함된 bar chart
- 기존 `eval_harness/metrics_reporter.py` 참조하되 직접 구현해도 무방

## 산출물
1. `scripts/experiments/bootstrap_ci.py`
2. `evidence_pack/analysis/bootstrap_confidence_intervals.json`
3. `evidence_pack/analysis/required_sample_size.json`
4. `evidence_pack/tables/main_results_with_ci.tex`
5. `evidence_pack/figures/sample_size_vs_power.pdf`
6. 해석 paragraph (limitation section 삽입용, 2-3 sentences)
```

---

## P0-3. CGA Sub-construct 분해 + 구성 타당도 분석

**왜 필수인가:** "4B 모델이 CGA 최고점 → 메트릭이 신중함을 보상" 비판에 직접 대응.

```
프로젝트 코드베이스를 분석하여 다음 실험을 구현하고 실행해줘.

## 목표
C1-C5 sub-construct별 모델 프로필 분해 + 판별 타당도 검증

## 배경
- CGA Score는 C1(Path Selection), C2(Mandatory Completion), C3(Forbidden Avoidance),
  C4(Timing Compliance), C5(Sequence Integrity)의 가중합
- 4B 모델 CGA=0.748 (1위), 120B 모델 CGA=0.664 (4위)
- 리뷰어 비판: "CGA가 신중함을 보상하고, 임상적 적절성을 측정하지 못한다"

## 구현 사항

### Step 1: Sub-construct 점수 추출
- 각 에피소드의 scoring 결과에서 C1-C5 개별 점수 추출
- `assessor_core/harm_scorer.py`의 compute_score()가 반환하는 sub_scores 필드 확인
  - 만약 sub_scores가 에피소드 결과 JSON에 저장되어 있지 않으면,
    원본 violation 데이터로부터 재계산 필요
  - harm_scorer.py의 코드를 읽어 C1-C5 각각의 계산 로직을 파악해줘
- 15 scenarios × 4 models × 3 runs 전체 데이터 수집

### Step 2: Sub-construct별 모델 비교
- 각 C1-C5에 대해:
  - 모델별 평균 ± std (3 runs의 scenario 평균 기반)
  - Friedman 검정 (C별로 모델 순위 차이가 유의한지)
  - 모델 순위 (1-4위)
- **핵심 예측**: 4B 모델은 C1(높음, 허용 범위 내 행동) + C3(높음, 금기 회피)에서 강하지만,
  C2(낮음, 필수 행동 미완료)에서 약할 것. 120B는 반대 패턴.

### Step 3: "보수적 전략 프로필" 정량화
- 각 모델에 대해:
  - 평균 수행 action 수
  - 평균 mandatory action 수 (시나리오별 expected_actions에서)
  - mandatory completion rate (= C2의 원천 데이터)
  - deviation count (expected 외 추가 action 수)
- 이를 2D 공간에 매핑: x축 = action 시도량, y축 = CGA Score
  → 4B는 좌상단(적게 하고 높은 CGA), 120B는 우하단(많이 하고 낮은 CGA)

### Step 4: 판별 타당도 (Discriminant Validity)
- **주의: 부분-전체 상관 함정 회피**
  - CGA 전체와 C2의 상관은 C2가 CGA의 구성요소이므로 인위적으로 높게 나옴
  - 대신, 다음 두 가지를 분석:
  (a) **외부 메트릭과의 판별 타당도**:
      Task Completion (C2 ≥ 1.0 여부, binary)과 CGA Score (continuous)의
      point-biserial 상관. r < 0.5면 "서로 다른 구성개념을 측정"
  (b) **Q2 에피소드 분석**:
      22개 Q2 에피소드(Task PASS / CGA FAIL)에서
      어떤 sub-construct가 FAIL의 원인인지 분해
      → "Q2 에피소드의 X%는 C4(timing)에 의해, Y%는 C1(deviation)에 의해 발생"

### Step 5: 시각화
- Figure 1: 4개 모델의 C1-C5 레이더 차트
  - **정규화**: 각 축을 [0, 1]로 정규화 (min-max across models)하여 축간 비교 가능하게
  - 또는 모든 축이 이미 0-1 범위이면 그대로 사용 (코드 확인 후 결정)
- Figure 2: Action 시도량 vs CGA Score 산점도
  - 각 점 = 모델×시나리오 (색상=모델, 크기=mandatory completion rate)
  - 4B의 "보수적 코너" 영역 시각적 강조
- Figure 3: Q2 에피소드의 sub-construct failure 분포 (stacked bar)

## 핵심 서사 목표
"4B의 높은 CGA는 '진짜 준수'가 아니라 '회피에 의한 안전'이다.
Sub-construct 분해가 이를 명확히 드러내며, 이것이 composite metric의 존재 이유다."

## 산출물
1. `scripts/experiments/subconstruct_analysis.py`
2. `evidence_pack/analysis/subconstruct_profiles.json`
3. `evidence_pack/analysis/discriminant_validity.json`
4. `evidence_pack/figures/radar_chart_models.pdf`
5. `evidence_pack/figures/activity_vs_cga.pdf`
6. `evidence_pack/figures/q2_failure_decomposition.pdf`
```

---

## P0-4. 시나리오 복잡도 정량화

**왜 필수인가:** "15개 시나리오는 너무 적다" 비판을 재프레이밍. YAML 파싱만으로 가능한 저비용 분석.

```
프로젝트 코드베이스를 분석하여 다음 분석을 구현하고 실행해줘.

## 목표
각 시나리오의 평가 복잡도를 **차원별로 개별 보고**하여,
CGA-Bench의 시나리오가 단순 MCQ와 질적으로 다름을 입증

## 주의사항
- "평가 축 = X × Y + Z" 같은 자의적 합산 공식을 만들지 않는다
- 대신, 각 복잡도 차원을 독립적으로 보고하고 독자가 판단하게 한다
- 비교 벤치마크의 "항목당 평가 차원"도 가능한 한 원 논문에서 검증 가능한 수치만 사용

## 구현 사항

### Step 1: CPG 그래프 복잡도 추출
- `cpg_model/graphs/` 디렉토리의 14개 YAML 파일 각각에서:
  - 총 노드 수
  - mandatory action 수 (그래프 전체)
  - forbidden action 수
  - timing constraint 수 (deadline이 정의된 action 수)
  - sequence dependency 수 (required_prior_actions 관계 수)
  - 조건부 분기 수 (if/applicability 조건)
  - evidence strength 분포 (STRONG/MODERATE/WEAK 각 비율)

### Step 2: 시나리오별 실효 복잡도
- `configs/scenarios/` 의 각 시나리오 YAML에서:
  - expected_actions 수
  - 활성 deadline 수 (해당 시나리오에서 적용되는 timing constraints)
  - 활성 sequence dependency 수
  - forbidden action 수 (해당 시나리오에서 적용 가능한)
  - 가능한 violation type 수 (5종 중 해당 시나리오에서 trigger 가능한 것)
- CPG 그래프의 reachability 분석이 필요할 수 있음 —
  `cpg_engine/reachability.py`를 활용하여 patient state 기반 적격 노드 필터링

### Step 3: 비교 테이블 (검증 가능한 수치만)
| 벤치마크 | 항목 수 | 평가 유형 | 시간 제약 | 순서 제약 | 금기 행위 |
|---------|--------|----------|----------|----------|----------|
| MedQA | 11,450 | 단일 정답 MCQ | 없음 | 없음 | 없음 |
| AgentClinic | 321 | Dx + Tx 평가 | 없음 | 없음 | 없음 |
| HealthBench | 5,000 | 루브릭 기반 | 없음 | 없음 | 부분적 |
| MedAgentBench | 300 | FHIR 성공률 | 없음 | 없음 | 없음 |
| CGA-Bench | 15 | CPG 전체 준수 | 92 constraints | 14+ deps | 12+ domains |

- "없음"으로 표기한 셀은 해당 벤치마크 논문에서 명시적으로 해당 차원을
  평가하지 않음이 확인된 경우만. 불확실하면 "미보고"로 표기

### Step 4: 산출물
1. `scripts/experiments/scenario_complexity.py`
2. `evidence_pack/analysis/scenario_complexity.json` — 시나리오별 상세
3. `evidence_pack/analysis/cpg_graph_complexity.json` — 그래프별 상세
4. `evidence_pack/tables/scenario_complexity.tex` — 시나리오별 복잡도 테이블
5. `evidence_pack/tables/benchmark_dimension_comparison.tex` — 벤치마크 비교
6. 1-paragraph 요약: "CGA-Bench의 시나리오는 시간·순서·금기 차원을 포함하는
   다차원 평가 단위로, 기존 벤치마크에서 평가하지 않는 프로세스 차원을 측정한다"
```

---

## P1-1. HealthBench 50-Sample 재현 가능 검증 패키지

**왜 중요한가:** "262명 의사가 만든 HealthBench에 84% 과분류라니, 증거를 보여달라"

```
프로젝트 코드베이스를 분석하여 다음을 구현해줘.

## 목표
HealthBench 50-sample 수동 분류 결과를 독립 검증 가능한 형태로 패키징

## Step 0: 데이터 존재 확인 (가장 먼저 수행)
- 다음 위치들을 탐색하여 50-sample 수동 분류 데이터가 실제로 존재하는지 확인:
  - `evidence_pack/sampling/`
  - `evidence_pack/experiments/`
  - `semantic_layer/external/` 관련 테스트 출력
  - `results/` 하위 healthbench 관련 디렉토리
  - git log에서 "50-sample", "manual", "audit", "healthbench" 관련 커밋
- **만약 원본 수동 분류 데이터가 존재하지 않으면**:
  → 이 실험의 방향을 전환하여, CGA-Bench의 HealthBench 어댑터
    (`semantic_layer/external/healthbench.py`)를 분석하고,
    keyword matching 로직의 false positive 패턴을 자동으로 식별하는
    스크립트를 대신 작성
  → "50-sample 수동 분류"를 새로 수행할 수 있는 프레임워크를 구축
- **데이터가 존재하면** 아래 Step 1부터 진행

### Step 1: 기존 분류 결과 구조화
- 각 샘플에 대해 기록할 필드:
  - episode_id (HealthBench 원본 ID)
  - original_healthbench_score
  - cga_bench_domain_classification
  - cga_bench_discordant_label (concordant/discordant)
  - manual_review_label (true_discordant / over_classified / matching_failure)
  - manual_review_reasoning (1-2 sentence)

### Step 2: 과분류 유형 세분화
- keyword_false_positive: "give" ↔ "given", "order" ↔ "disorder" 등
- domain_misattribution: 다른 도메인으로 잘못 매칭
- granularity_mismatch: CGA가 더 세분화된 기준을 적용
- other
- 각 유형의 빈도 + 대표 예시 1-2건

### Step 3: 한계 인정
- 수동 분류가 단일 리뷰어에 의해 수행된 경우, 이를 명시적으로 인정:
  "단일 리뷰어의 분류이므로 inter-rater reliability를 보고할 수 없다.
   향후 추가 리뷰어 확보 시 Krippendorff alpha를 산출할 예정이다."
- 이 한계를 JSON 메타데이터에 포함

### Step 4: 재현 스크립트
- 입력: HealthBench 원본 데이터 + CGA-Bench 분류 결과
- 출력: keyword matching 과정 재현 + discordant 판정 과정 추적
- 제3자가 keyword matching의 각 단계를 확인할 수 있어야 함

## 산출물
1. `evidence_pack/sampling/healthbench_50sample_audit.json`
2. `evidence_pack/sampling/healthbench_50sample_audit.csv` (리뷰어용)
3. `scripts/experiments/reproduce_healthbench_audit.py`
4. `evidence_pack/tables/healthbench_overclassification_breakdown.tex`
5. 한계 인정 paragraph (supplementary material용)
```

---

## P1-2. Sequence Violation 구조적 부재 분석

**왜 중요한가:** violation taxonomy 5종 중 하나가 독립 측정 불가 → "taxonomy가 과장" 비판 대응.

```
프로젝트 코드베이스를 분석하여 다음 분석을 구현하고 실행해줘.

## 목표
Sequence violation의 구조적 co-occurrence 패턴을 정량화하고,
이것이 taxonomy 결함이 아니라 LLM 행동 패턴에 대한 발견임을 논증

## 구현 사항

### Step 1: 전체 에피소드의 violation co-occurrence matrix
- 239+ 에피소드 전체에서 violation 추출
  - `assessor_core/violations.py`의 ViolationExtractor 사용
  - 또는 이미 추출된 violation 결과가 results/ 에 저장되어 있으면 그것 사용
- 5×5 co-occurrence matrix:
  각 셀 (i,j) = violation type i와 j가 동시 발생한 에피소드 수
- 대각선 = 각 type의 단독 발생 수

### Step 2: Sequence violation 심층 분석
- Sequence violation이 발생한 모든 에피소드 식별
- 각 에피소드에서:
  - 구체적 sequence 위반 내용 (어떤 required_prior_action이 미충족)
  - 동반 omission의 내용 (어떤 mandatory action이 누락)
  - **인과 관계 판정**: 누락된 action이 sequence의 선행 조건인가?
    (예: blood_culture 누락 → antibiotics가 blood_culture 전에 투여 = sequence 위반)

### Step 3: 반사실 분석 (Counterfactual) — 구체적 알고리즘
- 목적: "만약 모든 mandatory action이 수행되었다면, sequence 위반이 남는가?"
- 알고리즘:
  1. 에피소드의 action sequence를 가져옴
  2. 누락된 mandatory action을 식별
  3. 각 sequence violation에 대해:
     - 해당 violation의 `required_prior_action`이 누락된 action 목록에 있는지 확인
     - 있으면: "omission-caused sequence violation" (선행 action을 안 해서 발생)
     - 없으면: "independent sequence violation" (action을 했으나 순서가 잘못됨)
  4. independent sequence violation 수를 보고
- **주의**: 이 분석은 ViolationExtractor의 내부 로직에 의존하므로,
  먼저 violations.py에서 SEQUENCE violation이 어떻게 판정되는지
  (required_prior_actions 필드 기반인지) 코드를 읽고 확인해줘

### Step 4: 결과 요약 + 논문 language
- co-occurrence matrix 히트맵
- Sequence violation의 omission-caused vs independent 비율
- 논문 삽입용 paragraph:
  "현재 LLM 에이전트에서 관측된 sequence violation은 XX%가 선행 단계의
  누락에 의해 촉발되었다. 이는 현세대 LLM이 임상 단계를 의도적으로
  재배열하기보다 단계를 건너뛰는 경향이 있음을 시사하며,
  에이전트 아키텍처 설계에 시사점을 제공한다."

## 산출물
1. `scripts/experiments/sequence_violation_analysis.py`
2. `evidence_pack/analysis/violation_cooccurrence_matrix.json`
3. `evidence_pack/analysis/sequence_counterfactual.json`
4. `evidence_pack/figures/violation_cooccurrence_heatmap.pdf`
5. 논문 삽입용 paragraph
```

---

## P2-1. 모델 추가 실험 프레임 (GPT-4o / Claude)

**카메라레디 시 실행. 여기서는 실험 인프라만 준비.**

```
프로젝트 코드베이스를 분석하여 다음을 구현해줘.

## 목표
GPT-4o와 Claude 3.5 Sonnet을 기존 파이프라인에 추가하기 위한
설정 파일 + 예산 추정 + 실행 스크립트 준비

## 구현 사항

### Step 1: 에이전트 설정 파일 생성
- `configs/agents/` 에 다음 추가:
  - `rag_gpt4o.yaml` — GPT-4o backend, 기존 RAG agent 구조
  - `rag_claude35.yaml` — Claude 3.5 Sonnet backend
- 기존 `rag_*.yaml` 파일 구조를 정확히 참조하여 필드 일관성 유지
- `agent_runner/llm_provider.py`의 LLMBackend enum에
  해당 모델이 이미 지원되는지 확인 (OPENAI, ANTHROPIC 백엔드)

### Step 2: 예산 추정
- 기존 4개 모델의 에피소드당 평균 토큰 사용량 분석
  (`eval_harness/budget_tracker.py` 로그 또는 results/ 메타데이터에서)
- 15 scenarios × 3 runs × 2 new models = 90 에피소드
- GPT-4o: input $2.50/M, output $10.00/M (2026-03 기준, 확인 필요)
- Claude 3.5 Sonnet: input $3.00/M, output $15.00/M (확인 필요)
- 총 비용 추정 + budget_tracker 설정값 도출

### Step 3: 실행 및 통합 스크립트
- `scripts/experiments/run_frontier_models.py`
  - --model gpt4o / --model claude35 옵션
  - --dry-run 모드 (API 호출 없이 예산만 계산)
- `scripts/experiments/integrate_frontier_results.py`
  - 기존 4개 + 새 2개 = 6개 모델 통합
  - Friedman 검정 재실행 (k=6, n=15) — 검정력 향상 예상
  - 기존 모든 분석 (k-space, bootstrap CI, subconstruct) 재실행

## 산출물
1. `configs/agents/rag_gpt4o.yaml`
2. `configs/agents/rag_claude35.yaml`
3. `scripts/experiments/run_frontier_models.py`
4. `scripts/experiments/integrate_frontier_results.py`
5. `evidence_pack/analysis/budget_estimate_frontier.json`
```

---

## 실행 순서 요약

```bash
# === P0: 제출 전 반드시 (1-2주) ===
# 순서 중요: 1→2는 독립이지만, 3은 1의 데이터 로딩 코드를 재사용

# 1. k-space 민감도 + 다중비교 보정
PYTHONPATH=. python scripts/experiments/k_space_sensitivity.py

# 2. 부트스트랩 CI + 필요 표본 크기 시뮬레이션
PYTHONPATH=. python scripts/experiments/bootstrap_ci.py

# 3. Sub-construct 분해 + 구성타당도
PYTHONPATH=. python scripts/experiments/subconstruct_analysis.py

# 4. 시나리오 복잡도 정량화 (가장 빠름, YAML 파싱만)
PYTHONPATH=. python scripts/experiments/scenario_complexity.py

# === P1: 강력 권장 (2-4주) ===

# 5. HealthBench 감사 패키지 (Step 0에서 데이터 존재 먼저 확인)
PYTHONPATH=. python scripts/experiments/reproduce_healthbench_audit.py

# 6. Sequence violation 구조 분석
PYTHONPATH=. python scripts/experiments/sequence_violation_analysis.py

# === P2: 카메라레디 ===

# 7. 프론티어 모델 인프라 준비 (dry-run으로 비용 확인)
PYTHONPATH=. python scripts/experiments/run_frontier_models.py --dry-run

# 8. 실제 실행 (API 비용 확보 후)
PYTHONPATH=. python scripts/experiments/run_frontier_models.py --model gpt4o
PYTHONPATH=. python scripts/experiments/run_frontier_models.py --model claude35
PYTHONPATH=. python scripts/experiments/integrate_frontier_results.py
```

---

## 검토 수정 사항 요약

| # | 초판 문제 | 수정 내용 |
|---|----------|----------|
| P0-1 | 데이터 소스가 집계 JSON만 참조 | 원본 에피소드(`results/`) 기반으로 변경, `exp` 출처 명시 |
| P0-1 | primary/secondary 분석 미구분 | multi-run means = primary, single-run = secondary 명시 |
| P0-1 | k-space 36개 테스트에 보정 적용 모호 | 탐색적(스윕) vs 확인적(4개) 분리, 보정은 확인적에만 |
| P0-2 | BCa CI를 n=3 runs에 적용 | BCa → percentile로 변경 (소표본 불안정성) |
| P0-2 | Post-hoc power analysis 학술 논쟁 무시 | Hoenig & Heisey 비판 반영, 시뮬레이션 기반 필요 표본 크기로 전환 |
| P0-3 | 부분-전체 상관(C2 ⊂ CGA) 함정 | 외부 메트릭(binary Task Completion)과의 point-biserial로 변경 |
| P0-3 | 레이더 차트 정규화 미명시 | min-max 정규화 또는 원래 0-1 범위 확인 후 결정 |
| P0-4 | 자의적 "평가 축 공식" | 합산 공식 삭제, 차원별 개별 보고 |
| P0-4 | 비교 벤치마크 수치가 저자 추정 | 검증 불가한 수치 제거, "없음/미보고" 구분 |
| P1-1 | 50-sample 데이터 존재 가정 | Step 0 추가: 데이터 존재 확인 후 분기 |
| P1-1 | 다수 리뷰어 가정 | 단일 리뷰어 가능성 인정, 한계 명시 |
| P1-2 | 반사실 분석이 모호 | 구체적 4단계 알고리즘 명시, ViolationExtractor 코드 확인 선행 |