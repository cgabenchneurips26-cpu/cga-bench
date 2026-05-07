> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# Verdict Matrix: v4 UP_any 기준 전체 재계산

## 원칙

논문 전체에서 "hard violation" = v4 YAML graph constraint violation.
모든 evaluator의 mis-certification rate를 이 하나의 정의로 통일.

## Step 1: v4 hard violation status를 180 episode에 부여 (30min)

```
final_rescore_v4.json (또는 최신 Exp11 v4 결과)에서
180 episode 각각의 v4 hard violation 여부를 추출해줘.

출력: episode_id → v4_hard (True/False)
확인: True = 70개, False = 110개 (38.9%)
```

## Step 2: 각 evaluator의 verdict를 기존 P1C/P1A/P1B에서 가져오기 (30min)

```
각 evaluator의 pass/fail verdict는 이미 계산되어 있음.
다만 evaluator별로 어떤 threshold를 쓸지 확정:

| Evaluator | Source | Pass criteria | 사용할 값 |
| DxEM | structural | all pass | 180 pass |
| AC-Proxy | P1A 사용 | coverage>=0.5 AND diag>=0.8 | 102 pass |
| MAB-Proxy | P1B 사용 | F1>=0.5 | 16 pass |
| C2 | pipeline | C2>=0.7 | 78 pass |
| ACov | pipeline | ACov>=0.5 | 102 pass |

주의: P1A(102)와 P1C(114)가 다른 이유는 threshold 차이.
P1A의 threshold(coverage>=0.5, diag>=0.8)가 AgentClinic 
논문에 더 가까우므로 P1A를 사용.

MAB-Proxy도 P1B(F1>=0.5, 16 pass)가 MedAgentBench 
원본에 더 가까우므로 P1B를 사용.
```

## Step 3: 교차 집계 — v4 hard × evaluator verdict (30min)

```
180 episode에 대해:
| episode_id | v4_hard | DxEM | AC_Proxy | MAB_Proxy | C2 | ACov |

각 evaluator에 대해:
- N_pass: evaluator가 pass한 episode 수
- Hard_in_pass: pass한 episode 중 v4_hard=True인 수
- Mis_cert: Hard_in_pass / N_pass

결과:
| Evaluator | N_pass | v4_hard_in_pass | Mis-cert |
| DxEM | 180 | 70 | 38.9% |
| AC-Proxy (P1A) | 102 | ?? | ??% |
| MAB-Proxy (P1B) | 16 | ?? | ??% |
| C2>=0.7 | 78 | 48 | 61.5% |
| ACov>=0.5 | 102 | ?? | ??% |
| HardViol | — | — | Reference |

UP_crit도 같이:
| Evaluator | N_pass | v4_crit_in_pass | Crit_mis-cert |
```

## Step 4: Ablation 표 논리 검증 (15min)

```
ablation 표의 모순도 검증:

Full = 48/78
Timing only = 42/78
차이 = 6 episodes

이 6개 episode를 특정해줘:
- v4_hard = True
- timing violation = False  
- forbidden OR ordering violation = True
- C2>=0.7

이 6개가 존재하면: 
"6 episodes have forbidden/ordering violations without 
timing violations" — footnote 수정 필요.

이 6개가 존재하지 않으면:
ablation 코드에 버그.
```

## Step 5: 출력

```
1. evidence_pack/tables/verdict_matrix_v4.tex
   (v4 hard violation 기준, 전 evaluator)

2. evidence_pack/analysis/verdict_matrix_v4.json
   (machine-readable)

3. results/ablation_6ep_investigation.md
   (6개 차이 episode 분석)

4. 논문 intro table도 업데이트:
   DxEM + AC-Proxy + C2 + ACov + HV를 모두 포함

5. tracking_sheet 업데이트
```

## 파일 경로

- v4 결과: evidence_pack/additional/analysis/final_rescore_v4.json
- P1A: evidence_pack/analysis/v3_agentclinic_replay.json
- P1B: evidence_pack/analysis/v3_medagentbench_replay.json  
- P1C: evidence_pack/analysis/v3_verdict_integration.json
- Episode data: results/clean_slate_rescored/