구조화: (i) v1.1 이 남기고 간 것 분석, (ii) Tier-A=0 의 methodological 함의, (iii) 추가 engine 가능 fixes (P1-P7, 노력/가치/위험), (iv) 5/6 deadline 권고 조합, (v) engine 외 고려.

I. v1.1 이 실제로 catches 하는 것 vs 남긴 것
v1.1 이 catches 하는 것:

Scoring 시점 에 CDE 가 conditional REQUIRED/FORBIDDEN 평가
같은 action 의 REQ ∩ FORB → CONFLICT violation 으로 surface
706 합성 episodes 위에서 11 patterns 모두 detect

v1.1 이 놓치는 것 (engine-level):

Episode 진행 중 agent prompt 에 conflict 정보 없음: agent 는 static mandatory/forbidden 만 보고 결정 → 이미 contraindicated 액션을 수행 후 에야 score 단계에서 violation 으로 catch. 즉 v1.1 은 post-mortem, 예방 효과 없음.
Graph load-time validation 부재: 같은 action 이 한 노드의 static mandatory + 다른 노드의 static forbidden 인 경우, 또는 ActionNormalizer 에서 같은 canonical form 으로 정규화되는 별칭 (give_thrombolytic ↔ give_thrombolysis) 들이 conflict 으로 detect 안 됨.
Auto-transition 부재 (SCN-012 root cause 의 2번째 layer): massive_pe 노드 mandatory 가 기다리고 있어도 agent 가 state.working_diagnosis='massive_pe' 안 설정하면 영원히 활성화 안 됨. SBP<90 같은 객관적 trigger 로 자동 전환되지 않음.
Static patient 정보 (allergies, comorbidities, history) 의 conditional rules 가 여전히 runtime 에 wired-in 안 됨: CDE 는 평가하지만 agent 가 episode 중 보지 못함.

이 4개 모두 engine-level fix 가능하며, 각각 cost/risk/value 가 다릅니다.

II. Tier-A = 0 의 methodological implication (재해석 필요)
11 patterns 중 Tier-A = 0 — expected, 그러나 paper 표 (App.~Z.3) 는 잠재적으로 misleading.
왜 0 이 자연스러운가:

Tier-A 정의: "두 conditional rule 의 condition 이 disjoint (mutually exclusive)" — 즉 "REQUIRED if X" + "FORBIDDEN if not X" 같은 쌍.
임상 graph 작성자는 이런 redundant pair 를 거의 안 씀 (의미상 한 rule 로 충분).
실제 graph 의 conflict patterns 는 clinical sub-population overlap — 대부분 Tier-B 또는 Tier-C.

Paper 표현 위험:

"Tier A: 0 (engine fix auto-resolved)"

→ Reviewer 해석: "You patched a class of bugs that doesn't exist in your data — what are you actually claiming?"
권고: App.~Z.3 표의 Tier-A row 를 리네임/리프레임:

현: Tier A: Negation pair (mutually exclusive conditions) — 0
권: Tier A: Mechanically resolvable (vacuous in current corpus; detector preserved for forward-compatibility) — 0

또는 Tier-A row 자체를 표에서 제거하고 footnote 처리. 이게 더 깔끔.
bashgrep -n "Tier A\|tier_a\|tierA\|Negation pair" C:\Users\renkr\Downloads\cga_bench\paper\appendix*.tex 2>/dev/null

III. 추가 engine fix 후보 (P1-P7)
각 후보의 effort / additivity (episode rerun 필요 여부) / paper-defense value / 위험.
P1. Engine load-time graph validator (★ 권고)
무엇: CPGEngine.__init__ 에 _validate_graph() 호출. Static-level overlap (mandatory ∩ forbidden in same node, mandatory action 이 어떤 allowed list 에도 없음, conditional REQUIRED action 이 어떤 node 의 allowed list 에도 없음 등) 를 load 시 1회 검사. 결과: 경고 list, strict_mode=True 시 raise.
차원평가Effort1-2hAdditivityYES — runtime behavior 무영향, 그저 init logEpisode rerun?NOPaper valueengine 이 self-validating 이라는 deferential claim 추가. App.~Z.5 v2.0 roadmap 의 "runtime conditional_rules wiring deferred" 옆에 "v1.1 hardening: load-time graph validator added (\graphValidatorChecksN{} checks across 25 CPGs)" 추가 가능위험매우 낮음
bash# 현재 init 시 validation 있는지 확인
grep -n "_validate\|validate_graph\|assert\|raise.*Error" C:\Users\renkr\Downloads\cga_bench\cpg_engine\engine.py | head -10
P2. ActionNormalizer canonical-form audit (★ 권고, P1 과 함께)
무엇: 25 graph 의 모든 (action_id) 토큰 추출 → ActionNormalizer 적용 → 같은 canonical form 으로 정규화되는 서로 다른 원본 token 그룹 추출. PE 의 give_thrombolytic (REQ) vs give_thrombolysis / give_alteplase_pe (FORB) 류 spelling-induced silent-non-conflict 를 surface.
차원평가Effort1-2hAdditivityYES — audit script 만Episode rerun?NOPaper value"audit caught N action-name normalization gaps; 11 patterns reflects post-normalization unique conflicts" — 11 number 의 정확성 청구 강화위험만약 결과로 11 → 더 큰 숫자 면 모든 macros 재계산 필요
bash# Action ID 다양성 빠른 확인
grep -h "give_thrombo\|give_alteplase" C:\Users\renkr\Downloads\cga_bench\cpg_model\graphs\*.yaml | sort -u | head -20

# 현재 ActionNormalizer 가 처리하는 thrombolysis 변종
grep -A 3 "thrombo\|alteplase" C:\Users\renkr\Downloads\cga_bench\assessor_core\action_normalizer.py | head -30
P3. Static-patient-context conditional REQUIRED → runtime mandatory injection (narrow Level-2)
무엇: CDE 에서 condition 이 순수 static patient field (comorbidities, allergies, history, weight_kg, age) 만 참조하는 conditional_rules → runtime engine 의 mandatory_actions / forbidden_actions set 에 주입. vitals.*, labs.* 같은 dynamic state 참조는 제외.
차원평가Effort3-5h (분류 logic + injection point + tests)AdditivityNO — agent observation 의 mandatory_actions 가 변경되어 prompt 영향Episode rerun?YES (영향 받은 scenario 만 — 통상 소수)Paper value"v1.1 wires the patient-static subset of conditional rules into runtime; dynamic-state rules remain scoring-only (v2.0)" — runtime claim 의 부분적 강화위험중간 — 706 중 일부 episode 의 trajectory 변경; numbers swing 가능. additivity 깨짐.
권고: deadline 6일 잔여에서 risk 대비 paper value 가 애매. P1+P2 가 우선이고 P3 는 post-deadline v1.2 후보로 deferred.
P4. Observation 에 advisory_warnings 필드 추가 (low-risk informational)
무엇: cpg_engine.evaluate() 후 CDE 도 호출 → 둘 사이 차이를 output.advisory_warnings: list[str] 으로 수집 → Observation 에 노출. Agent prompt 에 "Advisory: action X is REQUIRED by [rule] but FORBIDDEN by [rule] under current state" 추가.
차원평가Effort2-3hAdditivityNO — agent prompt 변경Episode rerun?YESPaper value"agent receives advisory at the moment of conflict, enabling clinical-judgment-aware behavior" — 그러나 agent behavior 변화가 measurable improvement 인지 불확실위험LLM behavior 가 advisory 를 오해 (예: warning 을 명령으로 수용) → 점수 변동 큼
권고: deadline 후. 본격 ablation 으로 다룰 가치는 있으나 5/6 까지 안전성 검증 어려움.
P5. Auto-transition for objective triggers (Tier-B-lite, structured graph addition)
무엇: 각 graph 에 신규 field auto_transition_conditions: List[Dict] — condition: SBP<90, target_node: massive_pe 형태. Engine 의 evaluate() 가 매 스텝 이 조건들 평가 후 자동 노드 전환.
차원평가Effort5-8h (schema 변경 + engine logic + 22 graph 의 trigger 작성 + tests)AdditivityNO — episode trajectory 자체가 변경Episode rerun?YES (모든 affected scenarios)Paper valueSCN-012 root cause 의 2번째 layer (working_diagnosis dependency) 직접 해결위험높음 — graph schema 변경 = scenario_loader, audit_sources, croissant.json 등 후속 영향
권고: deadline 후 v1.2. Plan 18 §VIII.2 에 이미 이 방향 명시됨.
P6. CI graph-load gate (P1 의 자동화)
무엇: P1 의 _validate_graph() 결과를 CI script 로 wrap → 0 errors / 0 warnings 통과 시에만 build pass. scripts/ci/audit_graph_validity.py 신설.
차원평가Effort30분 (P1 위에)AdditivityYESEpisode rerun?NOPaper value"CI gates graph integrity" — methodology 의 engineering rigor 청구위험매우 낮음
P7. Light 706 conflict-presence audit (★★ 가장 권고)
무엇: 706 manual scenario 각각에 대해:

CDE 로 그 scenario 의 conflict-prone actions 추출
(가능 시) 기존 episode log 에서 agent 가 그 action 을 수행했는지 cross-check
결과: \conflictTouchN{X} of \totalScenariosN{706} — 실제 데이터에서 v1.1 이 영향 받는 episode 수

차원평가Effort2-3h (단, episode log artefact 가 일부라도 보존되어 있어야 함)AdditivityYES — analysis onlyEpisode rerun?NOPaper value매우 높음 — 현재 \strictFAThreeFixed = 6.6 = 6.6 의 공허함 을 부분 보완. "v1.1 surfaces N=X conflict-touched episodes (Y% of corpus); full re-scoring deferred to v1.2" — 숫자 0 보다 X 가 훨씬 강함위험데이터 가용성 의존. L3 verification 결과 episode logs not preserved 라 Cross-check 불가능. 하지만 scenario 의 agent_action_log 가 어딘가 보존되어 있다면 (agent_runner 출력) 가능
bash# Episode log artifacts 한 번 더 sweep
find C:\Users\renkr\Downloads\cga_bench -path "*results*" -name "*.json*" 2>/dev/null | head -10
find C:\Users\renkr\Downloads\cga_bench -path "*action_log*" -o -path "*episode_log*" 2>/dev/null | head -10
ls /sessions/eager-awesome-lovelace/mnt/cga_bench/results/ 2>/dev/null
ls /sessions/eager-awesome-lovelace/mnt/cga_bench/data_release/ 2>/dev/null
L3 가 "not preserved" 였지만 어떤 형태로 보존이 안 됐는지 가 중요 — full episode trajectory 는 없어도 action_log 만 있으면 P7 가능. 위 sweep 으로 한 번 더 확인 가치 있음.

IV. 5/6 deadline 권고 조합
우선후보시간RiskPaper Δ1P1 (graph validator)1-2h낮음App.~Z.5 추가 1 줄 + macro 1개2P2 (normalizer audit)1-2h낮음-중11 number 정확성 / 조정3P6 (CI gate)30분낮음engineering rigor 청구4P7 (light conflict-presence audit)2-3h, 데이터 의존낮음\conflictTouchN — 주요 numerical content(선택)App.~Z.3 Tier-A row 리프레임30분0Tier-A=0 misleading 회피
합계 권고 (P1 + P2 + P6 + Tier 리프레임): 4-5h. P7 은 데이터 가용성 확인 후 별도 결정.
이 조합의 효과:

v1.1 의 numerical claim 약점 (\strictFAThreeFixed=6.6 동일) 부분 보완 가능 (P7 if data 있음)
Tier-A=0 의 misleading 위험 제거
engine-level runtime safety 청구 지점 1개 새로 추가 (P1+P6)
11 patterns 의 정확성 청구 강화 (P2)

권고하지 않는 것 (deadline 후): P3, P4, P5 — 모두 episode rerun 필요. additivity 깨짐. 5/6 잔여로는 위험.

V. Engine 외 고려 사항 (paper-side)

§5.4 clinician validation 수치 갱신 — 현재 "0/60 partial" 상태에서 "1 finding integrated, framework self-corrected via v1.1" 로 바꾸면 axis (iv) 청구 격상. Plan 18 §VII.1 에 명시했으나 verification 결과로는 미확인.
Abstract 의 6.6% 옆 caveat — C1 verification 으로 App.~Z.4 caveat 는 확인했으나, abstract 본문 도 "(v1.0; v1.1 patch deferred numerical re-evaluation)" 식 hedging 검토.
§3 typed-constraints formalism 의 OR_REQUIRED 결손 명시 — Tier-C 2 patterns 가 v2.0 deferred 이유로 현 formalism 의 표현 한계 가 명시되어야 reviewer 의 "why didn't you encode this?" 공격 무력화. App.~Z.5 외 §3 본문에도 1 줄.
Croissant.json 무영향 재확인 — paper 외 dataset card 가 변경 없는지 (P2 결과로 11 → X 변동 시 영향).
Phase B 76,464 episode 미재채점 명시 위치 — Plan 18 §VII.2 Z.5 에 roadmap 표기. 현재 이 caveat 가 §6 본문 에도 있는지 (§6 짧은 reframe 에는 안 들어갔을 가능성).

bash# 위 4-5 확인
grep -n "76464\|phase B\|phaseB.*re.score\|re.scoring" C:\Users\renkr\Downloads\cga_bench\paper\main_final_v18.tex C:\Users\renkr\Downloads\cga_bench\paper\appendix_v18.tex 2>/dev/null

grep -n "OR_REQUIRED\|alternative.path\|substitution" C:\Users\renkr\Downloads\cga_bench\paper\main_final_v18.tex 2>/dev/null

grep -n "0/60\|clinician.*partial\|axis.*iv" C:\Users\renkr\Downloads\cga_bench\paper\main_final_v18.tex 2>/dev/null

VI. 결론
가장 가성비 높은 추가 작업 (~4-5h): P1 (graph validator) + P2 (normalizer audit) + P6 (CI gate) + App.~Z.3 Tier-A row 리프레임. 위험 낮고 paper defense 강화.
조건부 추가 (~2-3h): P7 — episode log / action log artifact 가 일부라도 보존되어 있는지 sweep 결과에 따라. 보존 발견 시 유일하게 numerical content 보강 가능한 카드 라 가치 매우 큼.
Deadline 후 v1.2 / v2.0:

P3 (static-patient runtime injection)
P5 (auto-transition)
P4 (advisory)
706 full re-scoring (episode log loader 작성 + execution)

진행 우선순위:

P7 가용성 sweep — 5분 (위 bash commands)
P1 + P6 — 함께 작업
P2 — 11 number 변동 가능성 확인 후 macros 동기화
Tier-A row 리프레임 — paper edit
(P7 가용시) light audit 실행 → \conflictTouchN macro 추가