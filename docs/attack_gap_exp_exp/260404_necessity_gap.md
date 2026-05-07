> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# E3/E4/E5 실험 — Claude-Code 프롬프트

> 모두 기존 180 episode (results/clean_slate_rescored/) + verdict_matrix_v4.json으로 실행 가능.
> Episode 재실행 후 경로만 바꿔서 재실행하면 최종 수치.

---

## E3: Instrumentation Ablation

```
프로젝트 컨텍스트:
- results/clean_slate_rescored/ 에 기존 180 episode JSON
- 각 episode JSON은 agent trace를 포함: actions, timestamps, patient state
- cpg_model/constraint_derivation.py — ConstraintDerivationEngine
- 기존 EXP-3 결과: no-timestamp 시 UP_any 61.5% → 15.4% (results/instrumentation_mimic/)
- 6개 evaluator의 scoring 로직이 각각 어떤 trace 정보를 사용하는지 확인 필요

목표: trace에서 정보를 단계적으로 제거하며 각 evaluator의 violation 탐지율 변화를 측정.
논문에서의 역할: "왜 기존 benchmark에 richer scorer만 얹으면 안 되는가" — artifact 자체에 observable이 없으면 어떤 scorer도 탐지 불가.

=== scripts/experiments/exp_e3_instrumentation_ablation.py 생성 ===

5가지 조건에서 전 evaluator를 재실행:

Condition 1: Full trace (baseline)
  - 원본 episode 그대로 채점
  - 모든 evaluator의 pass rate 및 violation 탐지 수 기록

Condition 2: No timestamps (-timestamps)
  - episode JSON의 모든 timestamp 필드를 None 또는 0으로 대체
  - WITHIN constraint 검사가 불가능해짐
  - 재채점 후 각 evaluator의 pass rate 변화 측정
  - 탐지 불가능해진 violation 수 = Full에서 잡혔지만 여기서 안 잡힌 것

Condition 3: No action ordering (-ordering)
  - episode의 action 순서를 무작위 셔플 (seed=42로 deterministic)
  - 또는: BEFORE constraint 검사를 비활성화
  - 선택: BEFORE checker를 mock하는 것이 더 깨끗함
  - 재채점 후 변화 측정

Condition 4: No state gating (-state)
  - patient context에서 allergy, contraindication 등 조건부 필드를 제거
  - conditional rules가 모두 비활성화됨 → FORBIDDEN constraint가 사라짐
  - 재채점 후 변화 측정

Condition 5: Terminal only (-all)
  - 최종 진단 + 최종 관리 계획만 남기고 전체 trace 제거
  - DxEM만 채점 가능, 나머지 evaluator는 정보 부족으로 default pass
  - BSR(terminal) = 이 조건에서 pass인데 Full에서 hard violation 있는 비율

각 조건에서 측정:
  - 각 evaluator별 pass rate
  - 각 evaluator별 탐지된 violation 수
  - BSR(evaluator, condition) = P(pass_condition ∧ HardViol_full)
  - 조건 간 차이의 McNemar test

구현 방법:
  - episode JSON을 deep copy → 필드 제거/변조 → 기존 scorer에 다시 통과
  - scorer가 어떤 인터페이스로 episode를 받는지 먼저 확인
    (아마 scripts/experiments/ 기존 코드에서 scorer import 패턴 확인)
  - 각 조건은 독립적으로 실행 가능해야 함 (병렬화 대비)

출력:
- evidence_pack/exp_e3_instrumentation_ablation.json
  {
    "conditions": {
      "full": { "pass_rates": {...}, "violations_detected": {...}, "bsr": {...} },
      "no_timestamps": { ... },
      "no_ordering": { ... },
      "no_state": { ... },
      "terminal_only": { ... }
    },
    "pairwise_mcnemar": { ... },
    "violation_loss_by_type": {
      "no_timestamps": { "WITHIN": N, "BEFORE": 0, "FORBIDDEN": 0 },
      "no_ordering": { "WITHIN": 0, "BEFORE": N, "FORBIDDEN": 0 },
      ...
    }
  }
- evidence_pack/exp_e3_instrumentation_ablation.md (보고서)
- evidence_pack/figures/exp_e3_ablation_heatmap.png
  (rows = conditions, cols = evaluators, values = BSR)
- evidence_pack/figures/exp_e3_violation_loss.png
  (stacked bar: 각 조건에서 탐지 불가능해진 violation 수 by type)
- evidence_pack/tables/instrumentation_ablation.tex (논문 Table 4용)

코드 요구사항:
- scorer의 import 경로를 먼저 확인 (ls scripts/ 또는 기존 실험 코드 참고)
- episode JSON 구조를 1개 파일 파싱하여 확인 후 시작
- deep copy로 원본 훼손 방지
- 모든 random shuffle은 seed=42
- 결과 JSON에 episode 수, 조건별 N 포함
```

---

## E4: Operating-Point Matched Disagreement

```
프로젝트 컨텍스트:
- evidence_pack/analysis/verdict_matrix_v4.json — 180 episodes × 6 evaluators
- evidence_pack/analysis/kappa_precision_debug.json — 기존 κ 분석
- 각 evaluator의 pass/fail은 내부 threshold 기반:
    AC-Proxy: coverage ≥ 0.5 → pass
    C2: coverage + timing score ≥ threshold → pass
    MAB-Proxy: F1-like score ≥ threshold → pass
    CGA-Bench: 0 hard violations → pass (binary, threshold 없음)
- 현재 pass rates: AC-Proxy 0.567, MAB-Proxy 0.089, C2 0.433, CGA-Bench 0.611

목표: 모든 evaluator를 동일 pass rate로 맞춘 후에도 disagreement가 유지되는지 확인.
논문에서의 역할: "disagreement가 threshold calibration artifact가 아님" 증명.

=== scripts/experiments/exp_e4_operating_point.py 생성 ===

**Step 1: 각 evaluator의 raw score 추출**

각 evaluator는 내부적으로 연속 점수를 계산한 후 threshold로 pass/fail을 결정함.
이 연속 점수(raw score)를 추출해야 함:
  - AC-Proxy: coverage ratio (0.0 ~ 1.0)
  - C2: coverage + timing composite score
  - MAB-Proxy: F1-like safety score
  - CGA-Bench: hard violation count (0이면 pass, 1+이면 fail)

CGA-Bench는 binary이므로 threshold sweep 불가 → soft violation count를 사용하거나,
"hard + soft violation 합계"를 연속 점수로 사용.

각 evaluator의 raw score를 180 episodes에 대해 추출 → numpy array.

**Step 2: Threshold sweep**

각 evaluator에 대해 threshold를 sweep:
  - 50개 threshold 포인트 (score의 min~max를 균등 분할)
  - 각 threshold에서의 pass rate 계산
  - target pass rate: 0.3, 0.4, 0.5 (3개 operating point)

각 target pass rate에 대해, 각 evaluator의 threshold를 해당 pass rate에 가장 가까운 값으로 설정.

**Step 3: Matched-point 분석**

각 operating point에서:
  - 새로운 binary verdict matrix 생성
  - Fleiss' κ (4 independent) 계산
  - 모든 pairwise Cohen's κ 계산
  - Verdict-flip rate 계산
  - Cluster 구조가 유지되는지 확인:
    AC-Proxy/C2 κ vs MAB/CGA κ

**Step 4: 시각화**

  - Figure 1: pass rate vs κ curve (각 evaluator 쌍)
  - Figure 2: operating point별 pairwise κ heatmap (3개 heatmap)
  - Figure 3: verdict-flip rate vs operating point

출력:
- evidence_pack/exp_e4_operating_point.json
  {
    "raw_scores": { "AC-Proxy": [...], "C2": [...], ... },
    "operating_points": {
      "0.3": { "thresholds": {...}, "fleiss_kappa": ..., "pairwise_kappa": {...}, "verdict_flip_rate": ... },
      "0.4": { ... },
      "0.5": { ... }
    },
    "cluster_preserved": true/false
  }
- evidence_pack/exp_e4_operating_point.md
- evidence_pack/figures/exp_e4_kappa_vs_passrate.png
- evidence_pack/figures/exp_e4_matched_heatmaps.png
- evidence_pack/tables/operating_point_matched.tex

코드 요구사항:
- verdict_matrix_v4.json 구조를 먼저 파싱하여 raw score 접근 방법 확인
- raw score가 verdict matrix에 없으면, episode JSON에서 재계산 필요
  (각 evaluator의 scoring 함수를 import하여 score 단계까지만 실행)
- interpolation으로 정확한 threshold 찾기 (binary search 또는 np.interp)
- 모든 κ 계산: sklearn.metrics.cohen_kappa_score
- Fleiss: statsmodels 또는 직접 구현
```

---

## E5: Evaluator Family Expansion + Cluster Stability

```
프로젝트 컨텍스트:
- E4에서 추출한 raw scores 사용 (E4 먼저 실행 필요)
- 또는: verdict_matrix_v4.json + episode JSON에서 직접 계산
- 현재 4 independent evaluators로 2-cluster story
- 리뷰어 공격: "4개로 2 cluster는 discovery가 아니라 labeling"

목표: evaluator variant를 10~12개로 늘려 cluster 구조의 robustness 증명.
논문에서의 역할: "coverage vs safety 분리가 threshold 선택과 무관한 robust한 구조"

=== scripts/experiments/exp_e5_evaluator_expansion.py 생성 ===

**Step 1: Evaluator variant 생성**

기존 evaluator의 threshold를 변형하여 variant 생성:

  1. AC-Proxy @ 0.3  (lenient)
  2. AC-Proxy @ 0.4
  3. AC-Proxy @ 0.5  (original)
  4. AC-Proxy @ 0.6  (strict)
  5. C2 @ 0.5        (lenient)
  6. C2 @ 0.6
  7. C2 @ 0.7        (original에 가까운 값 확인)
  8. C2 @ 0.8        (strict)
  9. MAB-Proxy @ F1 0.3  (lenient)
  10. MAB-Proxy @ F1 0.5 (original에 가까운 값 확인)
  11. CGA-Bench (hard only, original)
  12. CGA-Bench-soft (hard + any soft violation → fail)

→ 12 evaluator variants × 180 episodes = 12×180 binary verdict matrix

**Step 2: Distance matrix 계산**

12 evaluator variant 간 distance matrix:
  - distance = 1 - Cohen's κ (또는 Jaccard distance on verdict vectors)
  - 12×12 symmetric matrix

**Step 3: Hierarchical clustering**

  - scipy.cluster.hierarchy.linkage (method='ward')
  - Dendrogram 생성
  - Cophenetic correlation 계산
  - Optimal cluster 수: silhouette score 또는 gap statistic

**Step 4: Bootstrap cluster stability**

  - 1,000 bootstrap resamples (episodes를 resample)
  - 각 resample에서 clustering 수행
  - Adjusted Rand Index (ARI)로 원본 clustering과의 일치도 측정
  - ARI 분포의 mean, 95% CI 보고
  - 핵심 질문: "coverage family"와 "safety family"의 분리가 
    bootstrap에서 몇 %의 확률로 유지되는가?

**Step 5: Consensus clustering (선택적)**

  - 1,000 bootstrap의 clustering 결과를 consensus matrix로 통합
  - consensus matrix[i][j] = i와 j가 같은 cluster에 속한 비율
  - 이 matrix의 heatmap이 2-block diagonal이면 robust

**Step 6: LLM Judge 위치 예측**

  - WS-3의 LLM judge (terminal-output based)는 아직 실행 안 됨
  - 예측: terminal-output judge는 process-oblivious family와 cluster해야 함
  - E5에서는 자리를 비워두고, WS-3 실행 후 추가

출력:
- evidence_pack/exp_e5_evaluator_expansion.json
  {
    "variants": [ { "name": "[email-redacted]", "threshold": 0.3, "pass_rate": ..., "verdicts": [...] }, ... ],
    "distance_matrix": [[...]],
    "linkage": [...],
    "cophenetic_correlation": ...,
    "optimal_clusters": ...,
    "bootstrap_ari": { "mean": ..., "ci_95": [...] },
    "consensus_matrix": [[...]],
    "cluster_assignments": { "[email-redacted]": "coverage", ... }
  }
- evidence_pack/exp_e5_evaluator_expansion.md
- evidence_pack/figures/exp_e5_dendrogram.png
- evidence_pack/figures/exp_e5_consensus_heatmap.png
- evidence_pack/figures/exp_e5_bootstrap_ari.png (histogram)
- evidence_pack/tables/evaluator_expansion.tex

코드 요구사항:
- E4의 raw scores를 입력으로 사용 (없으면 독립 계산)
- scipy.cluster.hierarchy 사용
- sklearn.metrics: adjusted_rand_score, silhouette_score, cohen_kappa_score
- bootstrap: seed=42, n=1000
- dendrogram: matplotlib, 색상으로 cluster 구분
- consensus heatmap: seaborn 또는 matplotlib imshow
- 12 variants의 이름을 명확하게 (e.g., "[email-redacted]", "[email-redacted]")
```

---

## 실행 순서

```
Step 1: E4 실행 (raw score 추출 + threshold sweep)
  → E3, E5가 이 raw score를 참조할 수 있음

Step 2: E3 실행 (instrumentation ablation)
  → E4와 독립적이지만 scorer import 방식이 같으므로 E4 이후가 안전

Step 3: E5 실행 (E4의 raw scores 사용)

예상 소요: 각 3-5시간 (구현 + 180 episode 재채점)
```

---

## 추가: Verdict-Flip + BSR 계산 코드 (Episode 대기용)

```
이것은 E1/E2에 해당하지만, 코드만 먼저 작성하고 episode 완료 후 실행.

=== scripts/experiments/exp_e1_verdict_flip.py 생성 ===

입력: verdict matrix (episode × evaluator binary matrix)

계산:
1. 각 episode에 대해:
   - 모든 evaluator 쌍 (C(6,2)=15쌍) 중 verdict가 다른 쌍의 수
   - verdict_flip = 1 if 최소 1쌍이 불일치
   
2. Verdict-flip prevalence = 전체 episode 중 verdict_flip=1인 비율

3. False-Accept matrix:
   - 각 evaluator e에 대해: FA(e) = episodes where e=pass AND HardViol=True
   - HardViol = CGA-Bench evaluator가 fail인 episode (hard violation 존재)
   
4. All-process-oblivious false-accept:
   - episodes where DxEM=pass AND AC-Proxy=pass AND C2=pass AND HardViol=True
   
5. 각 false-accept episode의 violation 수 중앙값

출력:
- evidence_pack/exp_e1_verdict_flip.json
- evidence_pack/tables/verdict_flip_matrix.tex (논문 Table 1)

=== scripts/experiments/exp_e2_bsr.py 생성 ===

입력: verdict matrix + violation counts per episode

계산:
1. 각 evaluator e에 대해:
   BSR(e) = count(pass_e AND hard_violation) / count(all episodes)
   
2. 각 false-accept episode의 d_G 추정:
   - 현재 d_G 정확 계산은 미구현
   - proxy: hard violation 수 × tier weight
   
출력:
- evidence_pack/exp_e2_bsr.json
- evidence_pack/tables/bsr_by_evaluator.tex (논문 Table 2)

이 두 스크립트는 verdict_matrix path를 인자로 받으므로,
기존 180 episode로 preliminary, 새 episode로 final 실행 가능.
```