> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# Track A: 숫자 정합성 + 재계산 (담당자 1명, Day 1-2)

---

## A-1. Verdict Matrix Severity Tier 통일 (2h)

```
verdict matrix (Table 5)에서 C2>=0.7의 unsafe-pass=15, mis-cert=19.2%가
UP_strong=27/78=34.6%과 다른 tier를 사용하고 있다.
모든 evaluator에 대해 동일 severity tier로 재계산해줘.

1. 현재 verdict matrix 코드를 열어서 확인:
   파일: scripts/experiments/v3_p1c_verdict_integration.py
   - 각 evaluator의 "unsafe-pass" 정의가 무엇인지 (어떤 violation type/tier)
   - C2 행의 15/78 = 19.2%가 어떤 tier인지 추적
   - DxEM 행의 81/180 = 45.0%가 어떤 tier인지 추적

2. Exp11 canonical method (event_level_hardviol_v2.json)를 사용해서
   모든 evaluator × 3개 tier 전부 재계산:

   각 evaluator에 대해:
   - N_pass: 해당 evaluator가 pass로 판정한 episode 수
   - UP_crit: N_pass 중 Exp11 CRITICAL violation이 있는 episode 수
   - UP_strong: N_pass 중 Exp11 STRONG violation이 있는 episode 수  
   - UP_any: N_pass 중 Exp11 ANY hard violation이 있는 episode 수

   | Evaluator | N_pass | UP_crit (n/%) | UP_strong (n/%) | UP_any (n/%) |
   | DxEM | 180 | ?/? | ?/? | 81/45.0% |
   | AC-Proxy | 114 | ?/? | ?/? | 35/30.7% |
   | MAB-Proxy (F1>=0.4) | 32 | ?/? | ?/? | 9/28.1% |
   | C2>=0.7 | 78 | 13/16.7% | 27/34.6% | 48/61.5% |
   | ACov>=0.5 | 102 | ?/? | ?/? | 31/30.4% |

3. 논문용 verdict matrix는 UP_strong tier로 통일:
   | Evaluator | N_pass | STRONG viol | Mis-cert |
   (이것이 Table 5의 최종 형태)

4. 19.2%의 정체를 문서화:
   "C2 행의 기존 19.2%는 [정확한 정의]로, 
    UP_strong 34.6%와는 다른 tier"

출력:
- results/verdict_matrix_all_tiers.csv (전체 3-tier matrix)
- evidence_pack/tables/verdict_matrix_strong.tex (논문용)
- results/verdict_matrix_19pct_explanation.md

데이터:
- Exp11 canonical: evidence_pack/additional/event_level/event_level_hardviol_v2.json
- Verdict data: evidence_pack/analysis/v3_verdict_integration.json
- P1C 코드: scripts/experiments/v3_p1c_verdict_integration.py
```

---

## A-2. Stratification 합계 수정 (1h)

```
Table 12에서 Core CP=60, Expansion CP=21, All CP=78인데
60+21=81≠78. 원인을 찾고 수정해줘.

1. P8 코드를 열어서 Core/Expansion 분류 기준 확인:
   파일: scripts/experiments/v3_p8_core_vs_expansion.py
   - Core에 포함되는 scenario 목록 (9개?)
   - Expansion에 포함되는 scenario 목록 (6개?)
   - 이 분류가 15개를 빠짐없이 커버하는지

2. 180 episode 전부에 대해:
   - scenario → Core/Expansion 매핑
   - C2>=0.7 여부
   - subset별 CP count 계산
   - Core_CP + Expansion_CP = All_CP 인지 확인

3. 불일치 원인 추적:
   가능성 (a): Core가 9개가 아님 (일부 scenario가 빠짐)
   가능성 (b): C2 threshold가 다르게 적용됨
   가능성 (c): P8이 다른 episode set을 사용함 (clean_slate가 아닌)

4. 정확한 숫자로 교체:
   | Subset | Scenarios | Episodes | CP | Hard% | UP_strong | UP_crit | Friedman p |
   | Core | ? | ? | ? | ? | ? | ? | ? |
   | Expansion | ? | ? | ? | ? | ? | ? | ? |
   | All | 15 | 180 | 78 | 45.0% | 34.6% | 16.7% | 0.205 |
   
   반드시 Core_CP + Expansion_CP = 78.

5. Core/Expansion의 UP_strong도 Exp11 canonical로 재계산.

출력:
- results/stratification_corrected.csv
- evidence_pack/tables/stratification.tex
- results/stratification_discrepancy.md (원인 문서)

데이터:
- P8 코드: scripts/experiments/v3_p8_core_vs_expansion.py
- Exp11: evidence_pack/additional/event_level/event_level_hardviol_v2.json
- Episode 데이터: results/clean_slate_rescored/
```

---

## A-3. 230 vs 112 관계 명시 (1h)

```
논문에 230 hard constraints와 112 activation conditions가 동시에 등장하는데
관계가 불명확하다. 정확한 매핑을 문서화해줘.

1. "112"의 출처 추적:
   - evidence_pack/analysis/ 에서 z1_approximation 관련 파일 검색
   - 또는 cpg_engine/applicability.py에서 activation condition 카운트
   - "112 constraint-activation conditions"가 정확히 무엇인지:
     (a) 230 hard constraints를 activation condition으로 그룹핑한 수?
     (b) conditional transition(27) + unconditional deadline(92) + ??
     (c) unique constraint pattern 수?

2. 230 → 112 매핑 로직:
   - 같은 activation condition을 공유하는 constraint들이 있는지
   - 예: 같은 z1 조건에서 활성화되는 WITHIN 3개가 1개 condition으로 카운트?

3. 논문에 넣을 정확한 문장:
   "14 CPG graphs define 230 hard constraint instances 
    (109 FORBIDDEN, 92 WITHIN, 29 BEFORE).
    For presenting-state activation analysis, these map to 
    112 unique activation conditions, of which 105 (94%) 
    are fully determined by z1, 3 (2.7%) require dynamic 
    state, and 4 (3.6%) are borderline."

4. 혹시 112가 outdated 숫자라면 (230 기준으로 재계산 필요하면):
   - 230개 constraint의 activation condition을 전수 분석
   - z1-determined / dynamic / borderline 재분류
   - 새 비율 산출

출력:
- results/constraint_activation_mapping.md
- 논문 문장 확정

데이터:
- V0 결과: evidence_pack/analysis/v3_constraint_audit.json
- z1 분석: evidence_pack/analysis/ 내 관련 파일
- CPG YAML: cpg_model/graphs/*.yaml
```

---

## A-4. EXP-SPREAD: Table 4 채우기 (1h)

```
이전에 프롬프트 제공됨 (exp-spread-prompt artifact 참조).

핵심 요약:
1. 15 scenario → 6 domain groupby
2. domain별 UP_strong (Exp11 canonical) 집계
3. violation type 목록
4. intro 문장: "X/6 domains, Y/15 scenarios"
5. domain 난이도: mean CGA

입력: 
- scripts/experiments/exp_spread.py (이미 존재)
- evidence_pack/analysis/exp_spread_results.json (이미 존재할 수 있음)
- Exp11: evidence_pack/additional/event_level/event_level_hardviol_v2.json

exp_spread.py를 실행하거나, 결과가 이미 있으면 그것을 Table 4 형식으로 변환.

출력:
- evidence_pack/tables/violation_spread.tex
- results/spread_by_domain.csv
- intro 문장: "Guideline-strong violations occur in X/6 domains 
  and Y/15 scenarios"
```

---

# Track B: Instrumentation & Ablation 실험 (담당자 1명, Day 1-3)

---

## B-1. Instrumentation Ablation (3h) ⭐

```
목적: "왜 새 metric이 아니라 새 benchmark instrumentation이 필요한가"를 실증.
이것이 논문에서 가장 효과 높은 신규 실험.

설계:
78개 completion-passing episode (C2>=0.7)에 대해 5가지 조건으로 재채점.

구현:
기존 evaluation pipeline (assessor_core/violations.py 또는 
cpg_engine/temporal_constraints.py)에서 constraint type별 
on/off toggle을 추가.

각 조건:
(a) FULL: 모든 hard constraint 사용
    - HardViol 계산 그대로
    - UP_strong = 34.6% (baseline)

(b) NO_TIMING: WITHIN constraint 전부 무시
    - temporal_constraints에서 WITHIN 체크 skip
    - 또는 violation type == "timing"인 violation을 무시
    - UP_strong_notime = ??%

(c) NO_ORDERING: BEFORE constraint 전부 무시  
    - sequence violation을 무시
    - UP_strong_noorder = ??%

(d) NO_FORBIDDEN: FORBIDDEN constraint 전부 무시
    - commission violation을 무시
    - UP_strong_noforb = ??%

(e) NO_HARD: 모든 hard constraint 무시
    - UP = 0% (by definition, sanity check)

각 조건에서 계산:
- HardViol status per episode
- UP_strong, UP_crit, UP_any
- Verdict divergence (몇 개 evaluator가 pass하는데 HardViol인지)

결과 table:

| Condition | UP_strong | UP_crit | UP_any | Detection loss vs Full |
| (a) Full | 34.6% | 16.7% | 61.5% | — |
| (b) No timing | ??% | ??% | ??% | -??pp |
| (c) No ordering | ??% | ??% | ??% | -??pp |
| (d) No forbidden | ??% | ??% | ??% | -??pp |
| (e) No hard | 0% | 0% | 0% | -100% |

핵심 문장:
"Removing timing instrumentation alone reduces UP_strong from 
34.6% to X%, losing Y% of safety-critical detections.
This confirms that timing observability—absent in all existing 
medical-agent benchmarks—is necessary for process-safety evaluation."

출력:
- scripts/experiments/instrumentation_ablation.py
- results/instrumentation_ablation.csv
- evidence_pack/tables/instrumentation_ablation.tex
- 논문 문장

데이터:
- Episode 데이터: results/clean_slate_rescored/
- Exp11 결과: evidence_pack/additional/event_level/event_level_hardviol_v2.json
- Evaluation pipeline: assessor_core/, cpg_engine/
```

---

## B-2. Constraint-Type별 BSR Decomposition (2h)

```
목적: BSR을 evaluator × constraint type 전체 matrix로 확장.

기존 BSR (Table 7)은 violation type별로만 되어 있음.
이걸 evaluator별로도 분해.

설계:
기존 bsr_perturbation.py의 로직을 확장:

각 evaluator (DxEM, AC-Proxy, MAB-Proxy, C2, ACov, Jaccard)에 대해
각 perturbation type (timing shift, sequence swap, forbidden insert, 
omission insert)을 적용했을 때 evaluator verdict가 바뀌는지 측정.

| Evaluator | WITHIN BSR | BEFORE BSR | FORBIDDEN BSR | MUST BSR | Overall |
| DxEM | 100% | 100% | 100% | 100% | 100% |
| AC-Proxy | ??% | ??% | ??% | ??% | ??% |
| MAB-Proxy | ??% | ??% | ??% | ??% | ??% |
| C2 | 10.6% | 16.7% | 0% | 5.0% | 6.9% |
| ACov | 10.6% | 16.7% | 0% | 5.0% | 6.9% |
| Jaccard | 10.6% | 16.7% | 0% | 0% | 5.1% |

출력:
- scripts/experiments/bsr_full_decomposition.py
- results/bsr_full_matrix.csv
- evidence_pack/tables/bsr_full_matrix.tex

데이터:
- 기존 BSR: scripts/experiments/bsr_perturbation.py
- Evaluator verdict: scripts/experiments/v3_p1c_verdict_integration.py
```

---

## B-3. Domain-Removal Necessity Robustness (2h)

```
목적: "DKA 하나 때문에 생긴 결과 아니냐" 공격 방어.

설계:
6개 domain을 하나씩 제거하고 UP_strong, verdict divergence 재계산.

1. A-4 (EXP-SPREAD)의 domain 분류를 사용
2. 각 domain 제거 시:
   - 남은 episode 수, CP 수
   - UP_strong, UP_crit
   - DxEM mis-cert rate
   - AC-Proxy mis-cert rate
   - "verdict divergence가 여전히 존재하는가?"

| Removed | Ep | CP | UP_strong | DxEM mis | AC mis |
| None | 180 | 78 | 34.6% | 45.0% | 30.7% |
| DKA | ?? | ?? | ??% | ??% | ??% |
| Sepsis | ?? | ?? | ??% | ??% | ??% |
| ACS | ?? | ?? | ??% | ??% | ??% |
| AKI | ?? | ?? | ??% | ??% | ??% |
| Stroke | ?? | ?? | ??% | ??% | ??% |
| Others | ?? | ?? | ??% | ??% | ??% |

핵심 확인: 어떤 domain을 빼도 UP_strong > 0 이고 
verdict divergence가 남는지.

출력:
- scripts/experiments/domain_removal_necessity.py
- results/domain_removal.csv
- evidence_pack/tables/domain_removal.tex

데이터:
- A-4의 domain 분류 결과
- Exp11 canonical
- Verdict matrix (A-1 결과)
```

---

## B-4. Timing-Free Necessity Check (1h)

```
목적: timing 없이도 forbidden/ordering만으로 necessity가 남는지.

B-1의 (b) NO_TIMING 결과를 사용하되, 추가로:
- FORBIDDEN + BEFORE만으로 UP_strong 재계산
- verdict divergence 재계산 (이 조건에서도 evaluator 간 verdict가 다른가)

출력:
- B-1 결과의 subset 분석
- 논문 문장: "Even without timing constraints, X% of 
  completion-passing episodes violate forbidden or ordering 
  constraints invisible to process-oblivious evaluators."

데이터: B-1 결과 사용 (B-1 완료 후 실행)
```