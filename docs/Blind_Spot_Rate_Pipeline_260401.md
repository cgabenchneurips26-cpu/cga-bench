> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

BSR(Blind-Spot Rate) 계산을 위한 perturbation + disagreement 분석을
구현하고 실행해줘.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
배경과 목적
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

BSR = "baseline metric은 같다고 판정하지만 CGA는 다르다고 판정하는 비율"

정의:
  BSR(m, d) = P[ m(τ) = m(τ̃)  ∧  d(τ) ≠ d(τ̃) ]

여기서:
  - τ = 원본 에피소드, τ̃ = perturbation 적용 에피소드
  - m = baseline metric (CGA 외부의 독립 메트릭 — 아래 정의)
  - d = CGA Score

강건성 분석 결과 Composite A p=0.000081, leave-one-out 15/15 유의,
run 3/3 유의가 확인되었으므로, CGA의 측정 능력은 확립됨.
BSR은 "CGA가 측정하는 것을 기존 metric은 놓친다"를 정량화하는 실험.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 0 (중요): Baseline Metric 정의 — CGA 외부 메트릭
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 왜 CGA 외부여야 하는가
BSR에서 baseline metric이 CGA의 하위 구성요소(예: C2)이면,
부분-전체 상관으로 BSR이 인위적으로 왜곡된다.
baseline은 CGA와 완전히 독립적인 메트릭이어야 한다.

## Baseline metric 후보 — 시나리오 config 확인 후 결정

### 후보 A: Track A (Action Coverage)
- Track A = |performed ∩ expected| / |expected|
- 이것은 DualTrack의 한 축이며 CGA Score 계산에 직접 사용되지 않음
  (CGA = Track B, Composite = Track A × Track B)
- 단, Composite A에는 포함되므로 Composite 기준 BSR에서는 부적절
- CGA alone 기준 BSR에서는 사용 가능

### 후보 B: 최종 진단 정확도
- 에피소드 종료 시 에이전트의 working_diagnosis가
  시나리오의 correct_diagnosis와 일치하는지 (binary)
- 완전히 CGA 외부
- 시나리오 config에 correct_diagnosis 필드가 있는지 확인 필요

### 후보 C: 필수 행동 수행 여부 (binary task success)
- expected_actions 중 50% 이상을 수행했는지 (binary)
- Track A ≥ 0.5 → PASS
- CGA Score와 독립은 아니지만, binary화하면 상관이 약해짐

## 실행
- 먼저 configs/scenarios/*.yaml를 확인하여 correct_diagnosis 또는
  success_criteria 필드가 존재하는지 확인
- 존재하면 후보 B를 primary baseline으로 사용
- 존재하지 않으면 후보 A (Track A)를 CGA alone 기준으로 사용하되,
  이 한계를 명시적으로 보고
- 어떤 후보를 선택했는지와 그 이유를 산출물에 기록

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 1: Perturbation Generator
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 대상 에피소드 선택
- results/clean_slate_rescored/ 의 180 에피소드
- 두 그룹으로 BSR을 각각 계산:
  (a) 전체 180 에피소드 → BSR_all
  (b) CGA Score 상위 50% (90개) → BSR_high
  → 두 값을 모두 보고하여 선택 편향 투명하게

## 4+1가지 Perturbation

### P1: DELAY (timing violation 주입)
- deadline이 있는 action을 찾아 timestamp을 deadline + 30분으로 변경
- 다른 모든 action과 최종 결과(진단, 치료계획)는 유지
- 기대: CGA 하락 (C4 감소), baseline metric 동일

### P2: SWAP (sequence violation 주입)
- **사전 확인 필수**: 에피소드에서 required_prior_actions 관계가 있는
  action 쌍 중 **둘 다 실제로 수행된** 쌍이 있는지 확인
- 있으면: 두 action의 timestamp 교환
- 없으면: 해당 에피소드를 P2에서 스킵하고 기록
- 기대: CGA 하락 (C5 감소), baseline metric 동일 (같은 행동 집합)
- **P2 적용 가능 에피소드 수를 사전에 보고** — 너무 적으면 (< 20개)
  P2의 BSR은 통계적으로 불안정하므로 참고치로만 보고

### P3: DELETE (omission 주입) — ⚠️ sanity check 용도
- mandatory action 하나를 제거
- 기대: CGA 하락 AND baseline 하락 (둘 다 변해야 정상)
- BSR이 높으면 오히려 비정상 (baseline이 omission을 못 잡는다는 뜻)
- BSR이 낮으면 정상 (agreement)
- **이 perturbation의 BSR은 "sanity check"로만 보고, 핵심 주장에 사용하지 않음**

### P4: INSERT_FORBIDDEN (commission 주입)
- 해당 시나리오의 forbidden_actions에서 하나를 선택하여 중간 시점에 삽입
- forbidden_actions가 없는 시나리오는 스킵
- 기대: CGA 하락 (C3=0), baseline metric 동일 (추가 행동은 task를 해치지 않음)

### P5: INSERT_OVERUSE (과잉행동 주입)
- CPG allowed_actions에 없는 비유해 action 삽입
  (예: order_lab_lipid_panel — 불필요하지만 무해)
- 기대: CGA 소폭 하락 (C1 감소), baseline 동일

## 각 perturbation의 핵심 불변 조건
- P1, P2, P4, P5: **수행한 행동의 집합은 동일** (또는 상위집합)
  → terminal output이 바뀌지 않아야 함
- P3: 행동 하나 제거 → terminal output이 바뀔 수 있음

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 2: 채점
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 원본: 이미 채점된 결과 사용
## Perturbation: R1-R5 수정된 파이프라인으로 채점

각 에피소드에서 추출:
1. baseline_metric: Step 0에서 결정된 메트릭 (binary 또는 continuous)
2. cga_score: CGA Score (continuous)
3. composite_a: Composite A (continuous)
4. c1~c5: sub-construct 개별

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 3: BSR 계산
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## BSR 정의 (binary baseline 기준)
baseline이 binary인 경우 (후보 B 또는 C):
  blind_spot = (baseline(τ) == baseline(τ̃)) AND (|cga(τ) - cga(τ̃)| > δ)
  δ = 0.1 (민감도 threshold, 0.05와 0.15에서도 보고)

baseline이 continuous인 경우 (후보 A):
  blind_spot = (|baseline(τ) - baseline(τ̃)| < ε) AND (|cga(τ) - cga(τ̃)| > δ)
  ε = 0.05, δ = 0.1

## BSR per perturbation type × 에피소드 그룹
| Perturbation | BSR_all | BSR_high | N_valid | 해석 |
|-------------|---------|----------|---------|------|
| P1 DELAY | ? | ? | ? | timing blind spot |
| P2 SWAP | ? | ? | ? | sequence blind spot |
| P3 DELETE | ? | ? | ? | (sanity check) |
| P4 FORBIDDEN | ? | ? | ? | safety blind spot |
| P5 OVERUSE | ? | ? | ? | overuse blind spot |
| **Overall** | ? | ? | ? | |

## δ sensitivity
BSR_overall을 δ=0.05, 0.10, 0.15, 0.20에서 계산하여 sensitivity 곡선 보고

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 4: 시각화
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## Figure 1: BSR by perturbation type (bar chart)
- x축: P1, P2, P4, P5 (P3 제외 또는 별도 표시)
- y축: BSR (0~1)
- BSR_all과 BSR_high를 paired bars로
- 95% CI (Wilson 이항 CI, 단 같은 시나리오의 run들을 cluster로 처리 —
  방법: scenario를 cluster로 한 cluster-adjusted CI, 또는
  가장 단순하게는 scenario-level BSR의 bootstrap CI)

## Figure 2: Δbaseline vs ΔCGA 산점도 (4분면)
- x축: baseline(τ) - baseline(τ̃)
- y축: CGA(τ) - CGA(τ̃)
- 4분면 해석:
  - 우상: 둘 다 하락 감지 (agreement)
  - 좌상: CGA만 하락 감지 (BLIND SPOT ← 핵심)
  - 우하: baseline만 하락 감지 (CGA 둔감)
  - 좌하: 둘 다 변화 없음
- 점 색상: perturbation type별
- 좌상 영역에 점이 집중되면 강력한 증거

## Figure 3: δ sensitivity 곡선
- x축: δ threshold, y축: BSR_overall

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 5: 내장 검증
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

## 5-A: Perturbation 정확성 (각 type 1건씩 수동 확인)
- P1: timestamp이 실제로 deadline 이후로 변경되었는지
- P2: 두 action의 timestamp이 실제로 교환되었는지
- P4: forbidden action이 실제로 삽입되었는지

## 5-B: CGA가 perturbation을 감지하는가
- P1 에피소드: C4가 원본보다 낮아야 함
- P2 에피소드: C5가 원본보다 낮아야 함
- P4 에피소드: C3가 0이어야 함
- 하나라도 실패하면 중단하고 원인 보고

## 5-C: P3 sanity check
- P3의 BSR이 0.3 이상이면 비정상 → baseline이 omission을 못 잡고 있다는 뜻
- 이 경우 baseline metric 정의를 재검토

## 5-D: baseline metric과 CGA의 상관 확인
- Pearson r(baseline, cga)를 180개 원본에서 계산
- r > 0.8이면 두 메트릭이 너무 유사 → BSR이 구조적으로 낮아지므로
  baseline 선택이 부적절. 다른 후보로 교체.
- r < 0.5이면 충분히 독립적

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Step 6: 강건성 분석 결과와의 통합
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

강건성 분석에서 확인된 핵심 수치를 BSR 결과와 연결:

- "Composite A p=0.000081 (leave-one-out 15/15, run 3/3)"
  → CGA가 모델 간 차이를 강건하게 감지함이 확인됨
- "BSR = [X]%"
  → 기존 metric은 이 차이의 [X]%를 놓침

논문 문장:
"CGA-Bench robustly distinguishes models (Friedman p<0.001,
leave-one-out 15/15 significant). However, outcome-only metrics
miss [BSR]% of clinically meaningful process differences,
as measured by controlled perturbation experiments."

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
산출물
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. scripts/experiments/bsr_perturbation.py
2. results/bsr_perturbations/ — perturbation 에피소드들
3. evidence_pack/analysis/bsr_results.json
4. evidence_pack/figures/bsr_by_type.pdf
5. evidence_pack/figures/bsr_quadrant.pdf
6. evidence_pack/figures/bsr_delta_sensitivity.pdf
7. evidence_pack/tables/bsr_table.tex
8. 검증 5-A~D 결과
9. baseline metric 선택 근거 문서