> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

# 시나리오 전수 검토 + 재실행 설계

## Part 1: 15개 시나리오 전수 분석표

configs/scenarios/ 디렉토리의 모든 YAML 파일을 읽고,
아래 표를 작성해줘.

```
| # | scenario_id | domain | guideline_graph | 
|   | expected_actions (수) | expected_actions (목록) |
|   | forbidden_actions (수) | forbidden_actions (목록) |
|   | optional_actions (수) |
|   | trap_scenario (Y/N) | trap_description (한줄) |
|   | max_duration_minutes | time_step_minutes |
|   | passing_compliance_threshold |
|   | patient.working_diagnosis |
|   | patient.comorbidities (목록) |
|   | patient.allergies (목록) |
|   | patient.contraindications (목록) |
```

## Part 2: CPG Graph에서 오는 constraint 매핑

각 시나리오가 사용하는 guideline_graph의 constraint를 매핑:

```
| scenario_id | graph | FORBIDDEN (수) | WITHIN (수) | BEFORE (수) |
|             | FORBIDDEN 목록 (action name) |
|             | WITHIN 목록 (action: deadline_min) |
|             | BEFORE 목록 (action_a → action_b) |
```

이것은 cpg_model/graphs/{graph_name}.yaml에서 추출.

## Part 3: 기존 결과 기반 문제 진단

180 episode (clean_slate_rescored/) 결과와 교차해서:

```
| scenario_id | episodes | mean_C2 | C2>=0.7 (CP수) | 
|             | mean_C3 | C3_violations |
|             | mean_C4 | timing_violations |
|             | mean_C5 | sequence_violations |
|             | UP_any (CP 중) | UP_crit (CP 중) |
|             | 주요 violation type |
```

## Part 4: 문제 시나리오 식별

아래 기준으로 문제 시나리오를 분류:

```
Category A: CP=0 (C2가 구조적으로 <0.7)
  → 원인: expected_actions가 너무 많거나, agent가 못 하는 abstract action
  → 각 시나리오의 max(C2), min(C2) 보고
  → expected_actions 중 agent가 한 번도 수행하지 못한 action 목록

Category B: Violation=0 (CP>0이지만 hard violation 없음)
  → 원인: constraint가 약하거나, agent가 잘 지킴
  → 해당 scenario의 FORBIDDEN/WITHIN/BEFORE 목록과 
    agent 행동 교차 분석

Category C: 100% violation (모든 CP episode가 violation)
  → 원인: 구조적으로 피할 수 없는 trap인지, 모든 모델의 공통 실패인지

Category D: 정상 (CP>0, 0<violation<100%)
  → 가장 바람직한 상태
```

## Part 5: 시나리오 개선/추가 제안

```
1. CP=0 시나리오 수정 제안:
   - expected_actions를 줄이거나
   - abstract action을 concrete action으로 교체하거나
   - normalizer 매핑을 추가하거나

2. Forbidden trap 추가 제안:
   - 기존 graph에 이미 FORBIDDEN이 있지만 
     trigger되지 않는 것 중 scenario 수정으로 trigger 가능한 것
   - 새 FORBIDDEN 추가가 필요한 것

3. Sequence trap 추가 제안:
   - 기존 graph의 BEFORE constraint 중 
     trigger되지 않는 것

4. 새 시나리오 제안:
   - 기존 14개 graph로 만들 수 있는 variant
   - 예: DKA severe, STEMI anterior, Sepsis meningitis
   - 각 제안에 대해: 어떤 constraint를 테스트하는지,
     기존 시나리오와 뭐가 다른지
```

## Part 6: 사용 가능한 모델 정리

현재 repo의 agent configs를 확인:
```
| model_id | config_path | model_name | 
| 파라미터 수 | reasoning 여부 |
| 기존 실험에서 사용 여부 |
```

## 출력

하나의 markdown 파일로:
scenario_review/full_scenario_audit.md

각 Part를 section으로 구분.
Part 4의 Category A/B/C/D 분류가 가장 중요.

## 파일 경로

시나리오: configs/scenarios/*.yaml
CPG graphs: cpg_model/graphs/*.yaml  
기존 결과: results/clean_slate_rescored/
Agent configs: configs/agents/*.yaml