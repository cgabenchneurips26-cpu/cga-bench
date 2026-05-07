# CGA-Bench 필수 실험 — Claude-Code 실행 프롬프트

> **사용법**: 각 프롬프트를 claude-code에 순서대로 전달. 
> **의존 관계**: EXP-A,B,C는 episode 실행 전 즉시 착수 가능. EXP-D,E,F는 episode 실행 후.
> 각 프롬프트는 독립적으로 실행 가능하되, 출력 경로는 통일되어 있음.

---

## EXP-A: Manual vs Auto-generated 시나리오 구조적 동등성 검증 (Pre-episode)

```
프로젝트 컨텍스트:
- configs/scenarios/*.yaml 에 수동 작성 시나리오 105개
- configs/scenarios/auto_generated_scenarios.yaml 에 자동 생성 시나리오 254개
- cpg_model/constraint_derivation.py 에 ConstraintDerivationEngine
- cpg_model/graphs/*.yaml 에 25개 CPG graph (20 main + 5 held-out)
- cpg_model/schemas/base.py 에 ConstraintType (FORBIDDEN, REQUIRED, BEFORE, WITHIN)

목표: episode 실행 없이 시나리오 자체의 구조적 동등성을 검증하는 분석 스크립트 작성.

=== 작업 1: scripts/experiments/exp_a_scenario_equivalence.py 생성 ===

다음 6가지 분석을 수행하는 단일 스크립트를 작성하라:

1. **Constraint density 비교**
   - manual 시나리오별 (FORBIDDEN, REQUIRED, BEFORE, WITHIN) constraint 개수 분포
   - auto 시나리오별 동일 분포
   - Mann-Whitney U test로 각 constraint type별 분포 차이 검증
   - 출력: p-value, effect size (Cohen's d), 분포 히스토그램 (matplotlib)

2. **Domain coverage 비교**
   - manual이 커버하는 CPG graph set vs auto가 커버하는 CPG graph set
   - Jaccard similarity
   - domain별 시나리오 수 비교 (chi-square test)

3. **Patient complexity 비교**
   - 시나리오별 active condition 수, 활성화된 conditional rule 수
   - manual vs auto의 complexity 분포 비교 (KS test)

4. **Expected action count 비교**
   - 시나리오별 expected action 수 (이미 mean 13.6, max 28로 보정됨)
   - manual vs auto 분포 비교

5. **Trap scenario 비율 비교**
   - FORBIDDEN constraint를 trigger하는 "trap" 시나리오의 비율
   - manual vs auto에서 trap 비율이 통계적으로 다른지

6. **Constraint provenance 완전성**
   - auto 시나리오의 모든 constraint가 CPG graph node까지 traceable한지
   - manual 시나리오 중 derived constraint로 커버되지 않는 비율 (handoff에서 "29%"로 언급됨)
   - 커버되지 않는 constraint의 유형 분류

출력 파일:
- evidence_pack/exp_a_scenario_equivalence.json (모든 수치)
- evidence_pack/exp_a_scenario_equivalence.md (사람이 읽는 보고서)
- evidence_pack/figures/exp_a_*.png (분포 히스토그램 4개)
- evidence_pack/tables/scenario_equivalence.tex (LaTeX 비교 테이블)

코드 요구사항:
- 기존 scenario YAML 로더를 재사용 (configs/ 구조 확인 후)
- ConstraintDerivationEngine을 import해서 auto 시나리오의 constraint를 재도출하여 결정론성 검증
- 모든 통계 검정은 scipy.stats 사용, 다중 비교 보정은 Bonferroni
- LaTeX 테이블은 booktabs 스타일
- seed=42로 reproducibility 확보
```

---

## EXP-B: Constraint Derivation Engine Ablation Study (Pre-episode)

```
프로젝트 컨텍스트:
- cpg_model/constraint_derivation.py — ConstraintDerivationEngine
- cpg_model/patient_generator.py — PatientGenerator  
- cpg_model/graphs/*.yaml — 25개 CPG graph (conditional_rules 포함)
- cpg_model/schemas/base.py — ConditionalRule, ConstraintType
- 211 conditional rules → 451 constraints 도출 확인됨
- tests/test_constraint_derivation.py 등 기존 테스트 참고

목표: Derivation Engine의 각 구성 요소 기여도를 분리하고, 대안 방법과 비교.

=== 작업 1: scripts/experiments/exp_b_derivation_ablation.py 생성 ===

**Ablation 1: 구성 요소 제거 실험**

ConstraintDerivationEngine의 파이프라인을 3단계로 분리:
  (a) conditional_rules 파싱 + patient context 대입 → 활성 rule 결정
  (b) 활성 rule → constraint 인스턴스 생성 (FORBIDDEN/REQUIRED/BEFORE/WITHIN)
  (c) constraint 인스턴스 → 시나리오 합성 (PatientGenerator)

각 단계를 제거/단순화했을 때의 영향 측정:
  - Ablation A: conditional_rules 무시 (모든 rule을 unconditionally 활성화) → constraint 과잉 생성률
  - Ablation B: constraint type 구분 없이 모든 constraint를 REQUIRED로 통일 → 시나리오 차별화 손실률
  - Ablation C: PatientGenerator 없이 random patient context 사용 → constraint 활성화 정확도

측정 지표:
  - 각 ablation에서 도출되는 constraint 수 (vs 원본 451개)
  - False positive constraints (patient context에 맞지 않는 constraint 활성화) 비율
  - False negative constraints (활성화되어야 하는데 누락) 비율
  - 시나리오 내 trap/normal differentiation 정확도

**Ablation 2: LLM-only 대안 비교 (baseline)**

다음 baseline과 비교:
  - Baseline-LLM: CPG graph YAML 전체를 프롬프트로 주고, LLM에게 "이 가이드라인에서 
    FORBIDDEN/REQUIRED/BEFORE/WITHIN constraint를 추출하라"고 지시. 
    (실제 API 호출 불필요 — 이 비교는 구조적으로 설계만 하고, 
    실제 LLM 결과는 EXP-2에서 수행. 여기서는 Engine 결과를 gold로 사용하여
    "LLM이 놓칠 수 있는 constraint 유형"을 분석)
  - Baseline-Manual: 수동 작성 시나리오의 constraint set을 gold로,
    Engine이 도출한 constraint set의 recall/precision 계산

**Ablation 3: Scalability 분석**

25개 CPG graph를 graph 복잡도(node 수, edge 수, conditional_rules 수)로 정렬:
  - graph 복잡도 vs 도출된 constraint 수 scatter plot
  - graph 복잡도 vs constraint 도출 시간 scatter plot
  - 복잡도 구간별 constraint precision/recall (manual 기준)

출력 파일:
- evidence_pack/exp_b_derivation_ablation.json
- evidence_pack/exp_b_derivation_ablation.md
- evidence_pack/figures/exp_b_ablation_bars.png (ablation 결과 bar chart)
- evidence_pack/figures/exp_b_scalability.png (scatter plots)
- evidence_pack/tables/derivation_ablation.tex

코드 요구사항:
- ConstraintDerivationEngine을 monkey-patch 또는 subclass로 ablation 변형 생성
  (원본 코드 수정 금지 — ablation 변형은 별도 클래스)
- 기존 test suite (194 tests)가 깨지지 않는지 확인하는 guard 추가
- 실행 시간 측정은 time.perf_counter 사용
- Graph 복잡도 메트릭: nodes, edges, conditional_rules 수, max_depth (BFS)
```

---

## EXP-C: Held-out Domain Generalizability 정량 분석 (Pre-episode)

```
프로젝트 컨텍스트:
- cpg_model/graphs/ 에 20개 main graph + 5개 held-out graph
  (aba_burn_resuscitation.yaml, aabb_transfusion.yaml, 
   acog_obstetric_hemorrhage.yaml, pals_pediatric_emergency.yaml, 
   apa_agitation_management.yaml)
- Held-out graph는 개발에 사용되지 않은 진짜 held-out
- scripts/verify_holdout_scenarios.py 이미 존재 (결과 확인 필요)
- ConstraintDerivationEngine이 코드 변경 0으로 held-out graph를 처리하는지 검증 중

목표: held-out domain에서의 Derivation Engine 성능을 in-domain과 정량적으로 비교.

=== 작업 1: scripts/experiments/exp_c_generalizability.py 생성 ===

**분석 1: Constraint 도출 성공률 비교**

20개 main graph와 5개 held-out graph 각각에 대해:
  - 총 conditional rules 수
  - 도출된 constraint 수
  - constraint type별 분포 (FORBIDDEN/REQUIRED/BEFORE/WITHIN)
  - 도출 실패 (파서 에러, 조건 평가 실패 등) 비율
  
in-domain vs held-out의 각 지표를 비교:
  - 평균, 분산, Mann-Whitney U test
  - "코드 변경 0으로 처리됨"의 구체적 증거:
    어떤 graph에서 어떤 조건 패턴이 처리되었고, 실패한 것은 없는지

**분석 2: Auto-generated 시나리오 품질 비교**

held-out graph에서 자동 생성된 시나리오 vs main graph에서 자동 생성된 시나리오:
  - patient complexity (active conditions 수)
  - constraint density (시나리오당 constraint 수)
  - trap/normal 비율
  - expected action count

**분석 3: Structural coverage**

각 held-out graph에 대해:
  - graph의 모든 conditional_rules 중 시나리오에 의해 trigger되는 비율 (rule coverage)
  - graph의 모든 node 중 최소 1개 시나리오의 expected actions에 포함되는 비율 (node coverage)
  - main graph의 동일 메트릭과 비교

**분석 4: Edge case 카탈로그**

held-out graph에서 발견된 Derivation Engine의 한계:
  - 처리 못 한 조건 패턴이 있다면 목록화
  - main graph에는 없지만 held-out에만 있는 구조적 패턴
  - 이 차이가 domain-specific인지 engine의 일반적 한계인지 분류

출력 파일:
- evidence_pack/exp_c_generalizability.json
- evidence_pack/exp_c_generalizability.md
- evidence_pack/figures/exp_c_indomain_vs_holdout.png (grouped bar chart)
- evidence_pack/figures/exp_c_coverage_heatmap.png (graph × metric heatmap)
- evidence_pack/tables/generalizability.tex

코드 요구사항:
- held-out graph 파일명은 하드코딩하되 config에서 분리 가능하게
- main graph 목록은 cpg_model/graphs/ 에서 held-out 5개를 제외한 나머지로 자동 결정
- coverage 계산 시 graph YAML의 nodes/edges 구조를 직접 파싱
- 모든 비교에서 bootstrap 95% CI (n_bootstrap=10000) 포함
```

---

## EXP-D: Evaluation Disagreement 정량화 (Post-episode, episode 결과 필요)

```
프로젝트 컨텍스트:
- episode 실행 후 results/ 에 episode JSON 파일이 생성됨
- 6개 evaluator: DxEM, AC-Proxy, MAB-Proxy, C2, ACov, + CGA-Bench (constraint-based)
- evidence_pack/analysis/verdict_matrix_v4.json 에 기존 verdict matrix 존재
- 기존 수치: DxEM mis-cert 38.9%, AC-Proxy 51.0%, MAB-Proxy 12.5%, C2 61.5%, ACov 51.0%
- 핵심 주장: "같은 trace를 평가 방법에 따라 합격/불합격이 갈린다"

목표: 이 주장을 NeurIPS 리뷰어가 반박 불가능한 수준으로 정량화.

=== 작업 1: scripts/experiments/exp_d_disagreement_quantification.py 생성 ===

입력: results/ 디렉토리의 모든 episode JSON + verdict matrix
(verdict matrix 구조는 verdict_matrix_v4.json 참고)

**분석 1: Pairwise evaluator agreement**

모든 evaluator 쌍 (C(6,2) = 15쌍) 에 대해:
  - Cohen's κ (binary: pass/fail)
  - 일치율 (%)
  - 불일치 유형: (E1=pass, E2=fail) vs (E1=fail, E2=pass) 비대칭성
  → 15×15 κ 행렬 heatmap

**분석 2: Multi-evaluator agreement**

전체 6 evaluator에 대해:
  - Fleiss' κ (전체)
  - 도메인별 Fleiss' κ (20+ domains)
  - 모델별 Fleiss' κ (5+ models)
  → "disagreement가 특정 모델/도메인에 집중되는가, 전반적인가?"

**분석 3: Rank reversal 분석**

모델별로 각 evaluator의 pass rate를 계산하여:
  - 모든 evaluator 쌍에 대해 Spearman's ρ (model ranking)
  - Kendall's τ (model ranking)
  - 구체적 rank reversal 사례: "모델 A가 evaluator X에서는 1위이지만 Y에서는 꼴찌"
  - rank reversal이 발생하는 모델 쌍의 비율

**분석 4: Effect size 분석**

각 evaluator별:
  - 전체 pass rate
  - 모델별 pass rate
  - 도메인별 pass rate
  - evaluator 간 pass rate 차이의 최대/최소/평균

Evaluator를 "관대 → 엄격" 순서로 정렬하여:
  - 가장 관대한 evaluator와 가장 엄격한 evaluator의 pass rate 차이 (전체, 모델별)
  - 이 차이의 bootstrap 95% CI

**분석 5: 통계 검정**

  - McNemar test: 각 evaluator 쌍의 pass/fail 불일치가 유의한지
  - Cochran's Q test: 6개 evaluator의 pass rate가 전체적으로 유의하게 다른지
  - Bonferroni 보정 적용

**분석 6: Disagreement taxonomy**

불일치가 발생한 episode들을 분류:
  - Type A (Timing): 시간 constraint (BEFORE/WITHIN) 위반 여부에 따른 불일치
  - Type B (Forbidden): FORBIDDEN 행동 포함 여부에 따른 불일치
  - Type C (Completeness): REQUIRED 행동 누락에 따른 불일치
  - Type D (Partial credit): 부분 수행 시 evaluator별 판정 차이
  → 각 type별 빈도와 비율

출력 파일:
- evidence_pack/exp_d_disagreement.json (모든 수치)
- evidence_pack/exp_d_disagreement.md (보고서)
- evidence_pack/figures/exp_d_kappa_heatmap.png
- evidence_pack/figures/exp_d_rank_reversal.png (alluvial/bump chart)
- evidence_pack/figures/exp_d_passrate_by_evaluator.png (grouped bar)
- evidence_pack/figures/exp_d_disagreement_taxonomy.png (stacked bar)
- evidence_pack/tables/evaluator_agreement.tex
- evidence_pack/tables/rank_reversal.tex
- evidence_pack/tables/disagreement_taxonomy.tex

코드 요구사항:
- verdict_matrix_v4.json의 구조를 먼저 파싱하여 스키마 추론
- episode JSON 구조도 먼저 1개 파일 파싱하여 스키마 추론
- κ 계산: sklearn.metrics.cohen_kappa_score, 
  Fleiss' κ: statsmodels.stats.inter_rater 또는 직접 구현
- McNemar: scipy.stats, Cochran's Q: statsmodels 또는 직접 구현
- alluvial chart는 matplotlib로 구현 (plotly 사용 금지 — CI 환경)
- 보고서에 "Table X에 들어갈 수치" 형태로 논문 삽입 ready 포맷
```

---

## EXP-E: Manual vs Auto 시나리오 난이도 동등성 (Post-episode)

```
프로젝트 컨텍스트:
- episode 실행 후 results/ 에 모든 episode 결과 존재
- 각 episode는 특정 시나리오 + 특정 모델 + run index로 식별
- 시나리오는 manual (105개) 또는 auto (254개)로 태깅 가능
- EXP-A의 결과 (evidence_pack/exp_a_scenario_equivalence.json) 참조

목표: "What Has Been Lost with Synthetic Evaluation?" (2025)의 비판에 선제 대응.
자동 생성 시나리오가 수동 작성 시나리오와 난이도 및 모델 순위 측면에서 동등함을 증명.

=== 작업 1: scripts/experiments/exp_e_difficulty_equivalence.py 생성 ===

**분석 1: 모델별 정답률 분포 비교**

각 모델에 대해:
  - manual 시나리오에서의 pass rate (CGA-Bench evaluator 기준)
  - auto 시나리오에서의 pass rate
  - 차이의 bootstrap 95% CI
  - Kolmogorov-Smirnov test (시나리오별 정답률 분포)
  - Mann-Whitney U test

→ 핵심 질문: "auto 시나리오가 체계적으로 더 쉬운가?"
   만약 그렇다면, 어떤 constraint type/domain에서 차이가 나는지까지 드릴다운

**분석 2: Model ordering 보존 검증**

  - manual-only 시나리오로 모델 순위 결정
  - auto-only 시나리오로 모델 순위 결정
  - 전체 시나리오로 모델 순위 결정
  - Spearman's ρ: manual-only vs auto-only 순위
  - Kendall's τ: 동일
  - ρ ≥ 0.85이면 ordering preserved로 판정
  → 각 evaluator별로도 동일 분석 반복

**분석 3: IRT-inspired 난이도 분석**

2PL IRT 모델 (item difficulty + discrimination) 피팅:
  - manual 시나리오의 difficulty 파라미터 분포
  - auto 시나리오의 difficulty 파라미터 분포
  - 두 분포의 KS test
  - discrimination 파라미터 비교: auto가 낮은 discrimination을 가지면 
    "쉽지만 모델을 잘 구별 못함"을 의미

IRT 피팅이 복잡하면 대안:
  - Item-Total Correlation (각 시나리오의 정답 여부와 전체 점수의 상관)
  - manual vs auto의 ITC 분포 비교

**분석 4: Domain-stratified 비교**

manual과 auto가 모두 존재하는 domain에 대해:
  - domain별 pass rate 차이 (manual vs auto)
  - domain 효과를 통제한 후에도 manual/auto 차이가 유의한지 (mixed-effects logistic regression)
    → 종속변수: pass/fail, 고정효과: scenario_type (manual/auto), 랜덤효과: domain, model

**분석 5: Edge case coverage**

  - 전체 모델이 실패한 시나리오(hardest items) 중 manual/auto 비율
  - 전체 모델이 성공한 시나리오(easiest items) 중 manual/auto 비율
  - auto에만 존재하는 "난이도 구간"이 있는지 (manual이 커버하지 못하는 영역)

출력 파일:
- evidence_pack/exp_e_difficulty_equivalence.json
- evidence_pack/exp_e_difficulty_equivalence.md
- evidence_pack/figures/exp_e_passrate_manual_vs_auto.png (paired scatter, 모델별)
- evidence_pack/figures/exp_e_model_ordering.png (rank comparison chart)
- evidence_pack/figures/exp_e_difficulty_distribution.png (IRT difficulty histograms)
- evidence_pack/figures/exp_e_domain_stratified.png (forest plot)
- evidence_pack/tables/difficulty_equivalence.tex
- evidence_pack/tables/model_ordering.tex

코드 요구사항:
- IRT 피팅: py-irt 또는 직접 MLE 구현 (numpy/scipy.optimize)
  fallback으로 ITC 사용
- Mixed-effects model: statsmodels.formula.api의 MixedLM 또는 
  간단한 logistic regression + domain dummy
- 시나리오의 manual/auto 태깅: 파일 경로 또는 시나리오 ID 패턴으로 결정
  (auto_generated_scenarios.yaml에서 온 것 = auto, 나머지 = manual)
- 모든 bootstrap: n=10000, seed=42
```

---

## EXP-F: 통합 Evidence Pack 생성기 (모든 실험 완료 후)

```
프로젝트 컨텍스트:
- EXP-A ~ EXP-E 결과가 evidence_pack/ 에 존재
- paper/main_final_v7.tex 에 논문 최신본
- tracking/tracking_sheet.md 에 189 claims 추적

목표: 모든 실험 결과를 논문에 삽입 가능한 형태로 통합하고,
claim-evidence 매핑을 자동 검증.

=== 작업 1: scripts/generate_evidence_pack_v5.py 생성 ===

**Step 1: 수치 수집**

EXP-A ~ EXP-E의 모든 .json 결과를 읽어 단일 수치 딕셔너리 생성:
  {
    "scenario_equivalence": { ... },  // EXP-A
    "derivation_ablation": { ... },   // EXP-B
    "generalizability": { ... },      // EXP-C
    "disagreement": { ... },          // EXP-D
    "difficulty_equivalence": { ... } // EXP-E
  }

**Step 2: 논문 claim 검증**

tracking/tracking_sheet.md의 189 claims를 파싱하여:
  - 각 claim의 수치가 evidence_pack에서 검증 가능한지
  - 수치 불일치가 있으면 경고 (v4 수치 → v5 수치 변경 목록)
  - 새로 추가해야 할 claims (EXP-A~E에서 나온 새 수치)

**Step 3: LaTeX 매크로 파일 생성**

paper/auto_numbers.tex 생성:
  \newcommand{\numTotalConstraints}{451}
  \newcommand{\numManualScenarios}{105}
  \newcommand{\numAutoScenarios}{254}
  \newcommand{\kappaFleiss}{0.XX}  % EXP-D에서
  \newcommand{\rhoManualAuto}{0.XX}  % EXP-E에서
  ... 등 모든 논문 내 수치를 매크로화

이렇게 하면 main.tex에서 하드코딩된 수치를 매크로로 교체 가능.

**Step 4: Figure 인덱스**

evidence_pack/figures/ 의 모든 .png를 스캔하여:
  - 각 figure의 제목, 실험 출처, 논문 내 예상 위치 목록
  - evidence_pack/figure_index.md 생성

**Step 5: 종합 보고서**

evidence_pack/evidence_summary_v5.md 생성:
  - Executive summary (1페이지)
  - 실험별 핵심 수치 테이블
  - "논문에서 가장 강하게 주장할 수 있는 결과 Top 5"
  - "리뷰어가 공격할 수 있는 약점 Top 3 + 방어 전략"
  - 이전 v4 수치와의 변경 diff

출력 파일:
- evidence_pack/all_numbers_v5.json (통합 수치)
- evidence_pack/evidence_summary_v5.md (종합 보고서)
- evidence_pack/figure_index.md
- evidence_pack/claim_verification_v5.md (claim 검증 결과)
- paper/auto_numbers.tex (LaTeX 매크로)

코드 요구사항:
- tracking_sheet.md 파싱: regex로 수치 추출
- LaTeX 매크로: 특수문자 이스케이프 처리
- 변경 diff: v4 수치 (handoff-doc.md에서 추출) vs v5 수치 비교
```

---

## 실행 순서 요약

```
Phase 1 (즉시, episode 실행 전):
  EXP-A → EXP-B → EXP-C (병렬 가능)
  예상 소요: 각 2-4시간 구현 + 실행

Phase 2 (episode 실행 후):
  EXP-D → EXP-E (D 먼저, E는 D 결과 참조)
  예상 소요: 각 3-5시간 구현 + 실행

Phase 3 (모든 실험 후):
  EXP-F
  예상 소요: 2-3시간

총 예상: 구현 ~3-4일, 실행은 episode 실행 일정에 의존
```

---

## 참고: 기존 실험과의 관계

| 새 실험 | 대응하는 Gap | 기존 실험과의 관계 |
|---------|------------|-----------------|
| EXP-A | Gap 2 (동등성) | 신규 — cross_reference_manual_vs_derived.py 확장 |
| EXP-B | Gap 6 (ablation) | 신규 — 기존 V0-V7 코드 검증과 상보적 |
| EXP-C | Gap 7 (generalizability) | verify_holdout_scenarios.py 확장 |
| EXP-D | Gap 3 (disagreement) | verdict_matrix_v4 확장 — κ/rank reversal 추가 |
| EXP-E | Gap 2 (동등성) | 신규 — episode 결과 기반 난이도 분석 |
| EXP-F | 통합 | tracking_sheet.md + 모든 evidence 통합 |