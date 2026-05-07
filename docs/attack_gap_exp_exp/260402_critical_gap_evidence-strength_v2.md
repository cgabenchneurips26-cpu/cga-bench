# 최종 재채점: UP_any=48/78(61.5%), UP_crit=14/78(17.9%)

## 배경

Evidence fix 후 확정된 수치:
- UP_any = 48/78 = 61.5% (= UP_strong, all Class I)
- UP_crit = 14/78 = 17.9%
- 3-tier → 사실상 2-tier (Critical vs All-Hard)

## Step 1: 모든 downstream 재계산 (2h)

```
새 Exp11 결과 (event_level_hardviol_v4.json 또는 최신)를 사용해서
모든 논문 수치를 재계산해줘.

=== 1. Per-Model Table ===

| Model | N_pass | UP_crit (n/%) | UP_any (n/%) |
| 120B | 22 | ?/22 | ?/22 |
| 27B | 21 | ?/21 | ?/21 |
| 35B | 20 | ?/20 | ?/20 |
| 4B | 15 | ?/15 | ?/15 |
| All | 78 | 14/78 (17.9%) | 48/78 (61.5%) |

=== 2. Scenario-Clustered Bootstrap CI ===

B=10,000, BCa, resampling unit = scenario

| Tier | Rate | 95% CI |
| UP_any | 61.5% | [?, ?] |
| UP_crit | 17.9% | [?, ?] |

=== 3. Verdict Matrix (UP_any tier로 통일) ===

| Evaluator | N_pass | Hard viol (any) | Mis-cert |
| DxEM | 180 | ?/180 | ?% |
| AC-Proxy | 114 | ?/114 | ?% |
| MAB-Proxy | 32 | ?/32 | ?% |
| C2>=0.7 | 78 | 48/78 | 61.5% |
| ACov>=0.5 | 102 | ?/102 | ?% |

=== 4. Stratification ===

| Subset | Ep | CP | UP_crit | UP_any |
| Core (9 scen) | 108 | 60 | ?/60 | ?/60 |
| Expansion (6 scen) | 72 | 18 | ?/18 | ?/18 |
| All | 180 | 78 | 14/78 | 48/78 |

Core + Expansion = All 확인!

=== 5. Instrumentation Ablation (B-1 재계산) ===

새 severity 기준으로:
| Condition | UP_any | UP_crit | Loss vs Full |
| Full | 48/78 | 14/78 | baseline |
| No timing | ?/78 | ?/78 | -?pp |
| No ordering | ?/78 | ?/78 | -?pp |
| No forbidden | ?/78 | ?/78 | -?pp |
| Timing only | ?/78 | ?/78 | |
| Forbidden only | ?/78 | ?/78 | |

=== 6. Domain Spread ===

| Domain | Scen | CP | UP_crit | UP_any | Violation types |
(11 domains × 위 columns)

intro 문장: "Hard violations occur in X/11 domains and Y/15 scenarios"

=== 7. Domain-Removal Robustness ===

각 domain 제거 후 UP_any, verdict divergence.

=== 8. Absolute Prevalence ===

전체 180 episode 기준:
- hard violation: ?/180 = ?%
- CP AND hard: 48/180 = 26.7%

=== 9. Poster-Child 재확인 ===

모든 process-oblivious evaluator가 pass하면서 hard violation인 episode 수.
(새 수치에서 바뀔 수 있음)

=== 10. z1-only Subset ===

105/112 z1-determined constraints만 사용:
| Metric | All | z1-only |
| UP_any | 61.5% | ?% |
| UP_crit | 17.9% | ?% |
```

## Step 2: 결과 정리 (30min)

```
모든 결과를 하나의 보고서로:

evidence_pack/analysis/final_rescore_v4.md

내용:
1. 수정 사항 요약 (4개 버그)
2. 새 수치 전체
3. 이전 수치와의 비교 delta
4. severity taxonomy 변경 설명:
   "All violation-producing nodes carry Class I recommendation.
    UP_strong = UP_any. Paper uses 2-tier: Critical vs All-Hard."
5. 논문에서 수정해야 하는 모든 위치 목록
```

## Step 3: Tracking Sheet 업데이트 (30min)

```
tracking/tracking_sheet.md의 모든 수치를 새 값으로 업데이트.
상태: CONFIRMED (verified with corrected evidence pipeline)
```