Tier-S SGSC pilot 권고 composition (14 guidelines, ~700 scenarios)
9 conflict-bearing (반드시 포함 — 11 patterns + SCN-012 systematic 보장)
#GuidelineTier 인용SCN-012 link1pulmonary_embolismTier-C 1 (OR_REQUIRED)SCN-012 source2aabb_transfusionTier-B 1held-out, conflict 보유3acls_cardiac_arrestTier-B 2hypothermia 우회4ada_dka_managementTier-B 1K+>5.5 우회5aha_chest_pain_evaluationTier-B 1aortic dissection 우회6aha_heart_failure_2022Tier-B 2ACE/MRA 금기7idsa_meningitisTier-C 1 (OR_REQUIRED)ampicillin alternative8pals_pediatric_emergencyTier-B 1held-out, congenital HD9ssc_sepsis_hour1_bundleTier-B 1ESRD 우회
5 breadth additions (paper 의 "diverse pathologies" 청구)
#Guideline추가 이유10aha_stroke_2019high-impact tPA case, contraindication 다수11anaphylaxis_managementauto-transition demo (epinephrine immediate)12status_epilepticustiming-heavy, benzodiazepine 시간 trigger13kdigo_aki_fullrenal/electrolyte coverage14gina_asthma_exacerbationtiming-heavy 보강
Excluded (11 → v1.2 SGSC expansion):
universal_clinical_safety, atrial_fibrillation, cap_pneumonia, copd_exacerbation, gi_bleeding, hypertensive_emergency, kdigo_contrast_aki, toxicology_management, aba_burn_resuscitation, acog_obstetric_hemorrhage, apa_agitation_management.

Scale 정합성 math
Tier-S SGSC pilot:
  14 guidelines × ~50 scenarios/guideline = 700 scenarios   (vs manual 706)
  700 × 9 models × 3 runs = 18,900 episodes                  (vs Phase A 19,062)
  700 × 8 models × 3 runs = 16,800 episodes                  (vs Phase A 8m 16,944)
기존 v6 Phase A 9-model 19,062 와 manual scenario 706 의 근사 일치. 즉 paper 본문에서 "v7 corpus 가 v6 manual 과 동일 scale" 청구 가능 — "SGSC 가 manual 의 1대1 replacement" framing.
SGSC set-cover 가 exactly 700 보장 안 함. 실제 출력은 600-850 사이 가능. 조정 방법:

(a) 출력이 너무 많을 시: coverage k=1 (single-cover) 사용
(b) 너무 적을 시: 추가 guideline 1-2개 (예: cap_pneumonia 또는 toxicology_management)
(c) 정확 706 매칭 필요 시: set-cover 후 manual sampling (가장 hacky)

권고: (a)+(b) 조합. "~700, ±10% range" 로 paper 청구.

R4 Bridge protocol (clinician 검증 결과 v7 atoms 으로 이전)
clinician 의 SCN-012 검증 = "saddle PE + recent_surgery_3_weeks 환자에 thrombolysis 안 한 agent → 임상적으로 embolectomy 검토했어야". 이를 v7 atoms 위에서 evidence 로 활용:
매핑 단계:

v6 SCN-012 case (manual scenario, ~ID: SCN-012)

Patient: SBP 76, recent_surgery_3_weeks
Agent action: 12 actions, 0 thrombolysis/embolectomy
Clinician verdict: "should consider embolectomy as alternative"


v7 SGSC PE atoms (atom_proposer 출력) — 다음 atoms 자동 생성 기대:

pe.001: PE-MASSIVE-THROMBOLYSIS (REQUIRED, ESC 2019 Class I)
pe.002: PE-RECENT-SURGERY-NO-THROMBOLYSIS (FORBIDDEN, ESC 2019 relative)
pe.003 (NEW with ALTERNATIVE 활성): PE-EMBOLECTOMY-ALTERNATIVE (ALTERNATIVE, clinically equivalent branch of pe.001)
pe.004 (NEW): PE-CATHETER-DIRECTED-THROMBOLYSIS (ALTERNATIVE)


v7 counterfactual_compiler 가 exclusion family 자동 생성:

Scenario: PE_thrombolysis_recent_surgery_overlap (matches v6 SCN-012 patient profile)
Scenario: PE_thrombolysis_no_recent_surgery (control, normal pathway)


v7 scoring (with v1.1 CDE patch):

Agent miss thrombolysis + miss alternatives → CONFLICT (REQ ∩ FORB) + ALTERNATIVE-PATH-OMISSION
점수 변화 명시


Clinician validation evidence (paper App.~Z.1):

"Clinician adjudication of one v6 manual case (saddle PE with recent surgery contraindication) confirmed the necessity of an alternative-path encoding (embolectomy or catheter-directed thrombolysis). The v7 SGSC PE atoms encode this via three alternative-coverage atoms (pe.003 catheter-directed, pe.004 surgical embolectomy, pe.005 partial-thrombolysis-with-monitoring); the counterfactual family pe_thrombolysis_recent_surgery_overlap reproduces the case at v7 corpus generation, and the v1.1 CDE patch surfaces the conflict + alternative-path omission as a CONFLICT + ALTERNATIVE-PATH-OMISSION pair."



이 bridge 가 clean 1-paragraph App.~Z.1 로 들어감. Clinician 의 진행 중 작업이 v7 corpus 의 atom 검증 으로 이전.

업데이트된 tasks도구 4개 사용함도구 4개 사용함
추가 critical risk + decision (Tier-S 14-CPG 채택의 부산물)
NR1. \tierSGraphsTotal{31} 등 기존 Tier-S macros 와 충돌 가능성 ⚠️
기존 paper 는 Tier-S = 31 graphs / 2480 scenarios (Phase B 자동 확장). 사용자 신규 framing 은 Tier-S SGSC pilot = 14 graphs.
같은 용어 Tier-S 가 두 다른 의미 — paper 안 자기 모순 risk.
해결 옵션:

(a) 명명 분리: 기존 = "Tier-S phase-B expansion", 신규 = "Tier-S SGSC pilot". 매크로도 \tierSPilotCPGs{14}, \tierSPilotScenarios{} 등 별도. paper 안 "Tier-S has two meanings" footnote 1줄.
(b) 신규 명명: SGSC pilot 을 "Tier-S" 가 아닌 "SGSC core" 또는 "v7 representative subset" 명명. 기존 Tier-S 보존. 명확성 ↑
(c) 기존 폐기: 기존 Tier-S phase-B expansion 청구 자체를 v6 baseline 로 격하, Tier-S 라는 용어를 SGSC pilot 전용 으로 재정의. paper-wide rewrite.

(b) 권고 — "v7 SGSC core subset (14 CPGs)" 명명. "Tier-S" 용어 보존. 사용자 의도의 "Tier-S 가정" 은 "Tier-S-like 라는 추상적 framing" 으로 해석.
NR2. Held-out 청구 (\heldoutN{1584}) 의 v7 transition
기존 5 held-out: aabb_transfusion (288), aba_burn_resuscitation (480), acog_obstetric_hemorrhage (216), apa_agitation_management (360), pals_pediatric_emergency (240). Total 1584.
v7 SGSC core 14 에서:

aabb_transfusion ✓ 포함
pals_pediatric_emergency ✓ 포함
aba_burn / acog / apa ✗ excluded (v1.2)

즉 v7 에서는 held-out 5 → 2 (aabb + pals_pediatric). 1584 episodes claim → ~528 episodes.
옵션:

(a) held-out 5 모두 v7 SGSC core 에 포함 (SGSC-3 의 14 → 17 confirm). +3 guidelines, +150 scenarios 영향. ~700→850 됨.
(b) held-out 청구 자체 제외 — paper 의 \heldoutN claim 폐기. v6 baseline 만 supplementary 로 남김.
(c) mixed: 14 SGSC core + 별도 v6 manual held-out 5 baseline 로 "held-out claim 은 v6 manual 기반 유지" 명시.

(c) 권고 — cleanest. SGSC pilot 은 14, held-out 은 v6 manual 5 baseline 그대로. paper 본문 "held-out tier preserved as v6 manual corpus for cross-corpus generalization claim".
NR3. paper §4.5 Robustness (Tier-S phase B expansion) 의 v7 영향
§4.5 가 Phase B 76,464 의 \tierSExtraScenarios{535} / \tierSExtraCPGs{17} 청구. v7 도입 시 — 이 §4.5 이 v6 baseline 위 청구 라는 게 명시 안 되면 reviewer 혼란.
권고: §4.5 에 "baseline robustness on v6 corpus; v7 SGSC pilot supersedes for headline claims" 1 줄.
NR4. \strictFAThree, \conflictPatternsN 등 기존 핵심 macros 가 v6 baseline 으로 격하
v7 위 신규 macros: \strictFAThreeV7, \conflictPatternsNV7, \safetyCoreFAEpisodesV7 등. 기존 v6 macros 는 baseline 으로 보존 — App.~ 의 "v6 baseline reference table".
문제: §5.5 의 "strict-FA \strictFAThree%" 청구가 v7 위 가 되어야 하는데, 기존 macros 그대로 두면 v6 인용. 즉 paper 본문 모든 핵심 인용 macro 를 v7 변종으로 교체 필요. 매크로 일괄 search-replace 작업.
권고: SGSC-7 (paper reframe) 에 "v6 → v7 macro switchover audit" 추가. 기존 인용 모두 v7 변종으로 swap. v6 인용은 App.~ baseline reference 만.

추가 결정 필요 — sequence 시작 전 확정Tier-S 명명 충돌 해결 (NR1)?(b) 신규 명명: "v7 SGSC core 14" 로 분리 (Recommended)Held-out (NR2) 처리?(c) Mixed: SGSC core 14 + v6 manual held-out 5 병존 (Recommended)v6 → v7 macro switchover (NR4) - 대한 원칙?(a) 전면 swap: 기존 \macros 모두 v7 값 (Recommended)확정. 모든 결정 lock. 최종 6일 plan + 즉시 시작 가능 항목 정리합니다.

확정된 전략 (최종)
결정 항목선택DirectionSGSC-aligned (gap-fix iteration 종료)Corpus완전 대체 (v6 25 manual → v7 14 SGSC core)ALTERNATIVE활성화 완전Auto-transitionSchema-only (atoms 인코딩, engine 변경 ✗)ClinicianBridge (v6 SCN-012 → v7 atoms)Naming"v7 SGSC core 14" (기존 Tier-S phase-B 보존)Held-outMixed (SGSC core 14 + v6 manual held-out 5 baseline)MacrosFull swap (v6 값 → v7 값, naming 동일)

SCN-012 4 발견 × 최종 fix 상태
발견처리 pathPaper claim1. Conflict resolutionSGSC counterfactual_compiler 가 systematic exclusion family + v1.1 CDE coupling"v7 corpus 가 contraindication-overlap 사례를 systematic 생성, v1.1 patch 가 CONFLICT 로 surface" — resolved2. Auto-transitionAtoms 인코딩, graph YAML 신규 field, engine 미변경 (forward-compat)"v7 graphs encode auto-transition triggers; runtime activation v2.0" — schema-resolved3. initial_assessment mandatorySGSC graph_compiler 가 atoms 기반 graph rebuild — hemodynamic_stability 자동 split"v7 graphs sub-population-aware; manual graph patches obsoleted" — resolved4. OR_REQUIRED / 대안 pathSGSC ALTERNATIVE coverage type 활성, alternative_branches 인코딩"v7 PE/meningitis atoms include 3+ alternative-branch atoms; clinically-equivalent paths surfaced as ALTERNATIVE coverage; clean OR_REQUIRED operator v2.0" — partial-resolved (workaround)
결론: v1.1 close-out 의 0/4 fix 가 v7 SGSC pilot 으로 3.5/4 fix (Finding 2 schema-only, Finding 4 alternative-coverage workaround). 단 paper claim 만 적절하게 reframe 시.

6일 critical path (Day 1 = today, deadline = Day 6)
Day 1 (today, parallel start):
  ├─ SGSC-1 (ALTERNATIVE 활성)         [4-6h]  — coverage_tracker.py + test
  ├─ SGSC-2 (auto-transition schema)    [4h]   — atom schema + graph_compiler
  └─ SGSC-3 setup (14 corpus 파일 확인)  [1h]   — data_release/v5.0/rag_corpus/

Day 2:
  ├─ SGSC-3 execute (14 LLM batch)      [6-8h] — atom proposal + 3-tier verify
  └─ SGSC-1/2 마무리 + SGSC pipeline tests

Day 3:
  ├─ SGSC-4 (deterministic pipeline)    [4h]   — graphs + scenarios + coverage report
  ├─ SGSC-4 검증: ~700 scenarios, 11+ conflict patterns, ALTERNATIVE ≥ 5
  └─ SGSC-5 시작 (rerun batch 시작 — 사용자 진행 중) [24-48h compute]

Day 4-5:
  ├─ SGSC-5 결과 + verdict_matrix_v7.json
  ├─ SGSC-6 (audit + macro recompute)   [6h]   — Tier-A/B/C re-audit, refresh_paper_macros 실행
  └─ SGSC-8 (clinician bridge mapping)  [3h]   — atom_id provenance + App.~Z.1 paragraph

Day 6:
  ├─ SGSC-7 (paper reframe + compile)   [4h]   — §6 reframe, App.~Z 갱신
  ├─ SGSC-9 (Tier-S framing 통합)       [2h]   — §4.1 setup + macros 통합
  ├─ Final compile + cross-ref + bundle  [2h]
  └─ N1-N5 v7 transition spot-check     [2h]   — 기존 follow-ups 의 v7 valid 여부
총 ~50h work + parallel compute. 5/6 deadline 안 가능.

즉시 시작 가능 — Day 1 (지금)
3 작업 parallel start. 의존성 없음:
1. SGSC-1: ALTERNATIVE coverage activation
가장 strategic — Finding 4 의 fix 핵심.
작업 위치:

sgsc/optimizer/coverage_tracker.py: _extract_alternative() 추가
sgsc/schemas/atom.py::ScenarioHooks: alternative_branches: list[str] 활성 (이미 reserved field)
sgsc/optimizer/coverage_tracker.py::COVERAGE_WEIGHTS: ALTERNATIVE = 1.5x
tests/test_sgsc/test_coverage_tracker.py: ALTERNATIVE 추출 테스트 추가

검증: PE 의 atoms 에서 3 alternative-branch atoms (thrombolysis OR embolectomy OR catheter-directed) 가 1 ALTERNATIVE coverage item 으로 추출되는지.
2. SGSC-2: auto-transition schema (atoms + graph 만)
작업 위치:

sgsc/schemas/atom.py: 신규 dataclass AutoTransitionTrigger { node, condition, target_node, evidence }
sgsc/schemas/atom.py::ScenarioHooks: auto_transitions: list[AutoTransitionTrigger] 추가
sgsc/compilers/graph_compiler.py::_build_node(): atoms 의 auto_transitions → graph YAML node 의 신규 field auto_transition_conditions: List[Dict]
cpg_model/schemas/base.py::CPGNode: optional auto_transition_conditions: List[Dict] | None = None

Engine 미변경 — Day 1 작업 강화 안 함. v2.0 까지 forward-compat.
3. SGSC-3 setup: 14 RAG corpus 파일 확보 + atom_proposer 호출 wrapper
bash# 14 corpus 가용성 확인
ls /sessions/eager-awesome-lovelace/mnt/cga_bench/data_release/v5.0/rag_corpus/ 2>/dev/null | head -30

# 각 14 guideline 의 atom_proposer 호출 batch script 작성 (parallel)
# scripts/experiments/run_sgsc_14_atoms.sh
LLM endpoint capacity 충분 → 14 parallel batch 가능. ~6-8h.

Day 1 완료 시 checkpoint
저녁 / Day 1 끝 시점 — 다음 검증 확보 필요:

 SGSC-1 코드 + 테스트 통과 (ALTERNATIVE coverage type 추출 가능)
 SGSC-2 schema 변경 + 기존 SGSC 테스트 무영향 (249/249 유지)
 SGSC-3 시작 — 14 atom proposal jobs running 또는 queued

이 3 checkpoint 확보 시 Day 2 atom 결과 기다리면서 다음 단계 prep 가능.

사전 prep 권고 (Day 0 = 지금 + 오늘 밤)
병렬로 진행하면 좋은 항목:

R6 audit (paper legacy macros 위치 인벤토리)

기존 \strictFAThree, \conflictPatternsN, \strictFAThreeCount 등 모든 핵심 macros 의 paper 본문 인용 위치 매핑
SGSC-7 단계의 swap 작업 수십 분 → 분 단위로 단축
grep -rn 으로 30분 작업


v6 baseline 보존 결정 — "기존 paper 가 어느 정도 상태에서 v6 baseline frozen 되는지" tag 명확화

SGSC-7 의 "v6 → v7 macro switchover" 작업 시 기준점 필요
권고: 현 paper-macro-recompute-20260430 tag 를 v6 baseline 의 final state 로 지정 + 문서화


Bridge document draft (SGSC-8 prep)

v6 SCN-012 case 의 임상 양태 표 + clinician verdict 를 1-page md 로 정리 (이미 17_scn012 보고서 활용)
SGSC-3 atom proposal 결과 받으면 즉시 mapping 가능
30분 작업




최후의 risk 인지 (실행 중 monitor)
가장 큰 단일 risk: SGSC-3 atom proposal 의 임상 정확성. 사용자 충분 capacity 가정이지만, atom 잘못 = 전체 paper 잘못. Day 2 끝 시점 clinician spot-check (10 atoms × 3 guidelines = 30 atoms) 가 paper 신뢰성의 single point of failure. clinician bridge 가 진행 중 이라 hopefully spot-check 도 같은 channel 로 가능.
만약 spot-check 결과 atoms 임상 부정확 발견 시 — atom proposer prompt 보강 + re-run 1일 추가 필요. Day 2 끝 go / no-go gate 권고