II. Phase 0가 cover하지 않은 evaluator 영역 (residual gaps)
이 report는 6개 core evaluator (TCC, CwT, ASC, PAF, TOM, ACov)는 다뤘지만, paper의 다른 6개 evaluator-like measurement는 아직 audit 안 됐습니다. Phase 1 또는 Phase 0.B로 extend 필요:
II.1 LLM-Judge (T0/T1/T2/T3 prompts × Qwen/Gemma judges)
Paper에 영향 큰 measurement:

\termJudgeTzeroFA, \termJudgeToneFA, \termJudgeTtwoFA, \termJudgeTthreeFA — Qwen judge per-prompt
\gemmaJudgeTzeroFA, ... — Gemma judge per-prompt
\termJudgeTtwoTthreeGap, \gemmaJudgeTtwoTthreeGap — T2→T3 gap

Audit question: Each prompt template이 input으로 무엇을 받나?

Action list만? (action_list 만 보여주고 judge에게 pass/fail 묻기)
Action list + allowed_actions? (만약 후자면 author-dependent leak)
Action list + expected_actions? (expected_actions의 source-grounding 추가 question)

왜 critical: paper의 30.7% LLM-judge FA hero number가 author-dependent인지 결정.
Phase 0.B로 추가 권고: prompt template을 코드에서 grep해서 input field list 확인.
II.2 MedAgentBench (MAB) replay scorer
Paper hero number \mimicMABDetectionLoss{63.2}.
Audit question: replay scorer가 무엇을 reference로?

F1(performed, expected) — expected의 source는?
별도 task-specific gold standard?
Author-listed checklist?

Phase 0.B 권고: cga_bench/replay_adapters/medagentbench.py (또는 동등) 점검.
II.3 AgentClinic (AC) replay scorer
Paper hero number \mimicACDetectionLoss{84.2}.
Audit question: 동일 — diagnostic coverage의 reference set 정의.
II.4 OracleAgent results
Paper macros: \oracleMeanGap, \oracleNDomains, \oracleNDomainsTotal.
Audit question: OracleAgent score는 어느 sub-scores의 aggregate? Weighted average? Equal weight?
Phase 0.B 권고: cga_bench/agents/oracle.py (또는 동등) 점검. Score formula explicit하게 spec.
II.5 Constructive π_nord witness
Paper macros: \piNordWitnessBSR{0.4914}, \piNordFloor{0.003}, \piNordGapFactor{164}.
Audit question: V1_strict/V3_half_expected variant들의 verdict 함수 정의는? Tagged as aset (Table) but body framing as π_nord.
Phase 0.B 권고: audit/shims/pi_nord_shim.py 또는 spec 명시.
II.6 Pose B catalogue × evaluator measurements
Paper macros: \mainReplTriplePct{36.31}, \mainReplVTwoTriplePct{36.95}, ....
Audit question: Pose B에서 LLM catalogue × evaluator combination의 verdict 정의는? 동일 evaluator code 사용? 다른 prompt?
Phase 0.B 권고: Pose B re-execution을 Phase 1 spec에 포함.
II.7 75% pair reversal metric definition
Paper macro \reversalRate{75}. User가 verify_friedman_eta.py 언급.
Audit question: 정확한 metric 공식?

Per-pair (model_i, model_j) × (evaluator_a, evaluator_b) 조건부 rank inversion?
Friedman test signed-rank?
Kendall W on ranking pairs?

Phase 0.B 권고: paper의 75% 정의를 spec document에 명시. Phase 1에서 typed verdicts로 재계산.
II.8 X1/X2 violation ablation experiments
Paper macros: \xTwoTreatTCC, \xTwoTreatMorph, \xOneTCCFlipRate, ...
Audit question: 이 ablation 실험들의 verdict 함수 정의는?
Phase 0.B 권고: 코드 audit 또는 protocol document.
II.9 Robustness dashboard 10 probes
Paper macros: 다양한 probe-별 numbers (E5 op-point, E6 cluster, GEE, held-out, no-context, etc.).
Audit question: 각 probe의 verdict 의존성?
Phase 0.B 권고: probe-별 dependency 분석.
총 9개 evaluator-related areas가 Phase 0 audit에 cover 안 됐습니다. 이게 Phase 0의 가장 큰 gap. Phase 1로 들어가기 전에 적어도 §II.1-II.4 (LLM-judge, MAB/AC replay, Oracle, π_nord witness)는 audit 권고.

III. Report 내부의 Inconsistencies — Phase 1 전 해결 필요
가장 정직하게 짚어야 할 부분. 5개 발견:
III.1 n_viols +0.74 correlation 설명 — stale TCC definition 사용
Report §4.3:

"아무것도 안 하는 에이전트: n_viols = 0 (commission/timing 없음), 그러나 omission으로 TCC FAIL"

그러나 spec §2.1 TCC 정의:

"Hard violation types: {commission, timing, sequence}, 제외: omission, deviation"
"아무것도 하지 않은 에이전트(omission만 있는)도 TCC를 통과한다"

모순: §4.3은 omission이 TCC fail을 발생시킨다고 설명. §2.1은 omission이 TCC pass라고 명시.
가능한 해결:

(a) +0.74 correlation은 이전 TCC 정의 (omission 포함)에서 측정된 것. New TCC에서는 다른 값일 가능성.
(b) §4.3 explanation은 stale text이고, new TCC 정의 하에서 +0.74 correlation의 새 explanation 필요.

Phase 1 action:

new TCC 정의로 n_viols + TCC verdict 상관 재측정
만약 +0.74가 여전히 보존되면 §4.3 explanation 새로 작성
만약 다른 값이면 paper의 \violCountSpuriousRho{0.74} 업데이트

이건 작은 수치 issue가 아닙니다 — paper의 audit kit에 "viol_count anti-correlation" finding이 cite되어 있어서, 그 finding이 어느 TCC 정의 하에서 측정된 것인지 paper에 명시 필요.
III.2 η² 값 — Phase 0 spec vs paper macro mismatch
Phase 0 §3.2와 §부록D:

η²(evaluator) = 0.078 (v6, 16,944 episodes)
η²(run) < 0.001

Paper main.tex (Option Z 적용 후 macro):

\cresFiveEtaSq{0.072}
\cresFiveEtaRun{0.0515}
\etaRatio{1.40} (이번 세션에서 lock)

모순:

Phase 0 spec 값 (0.078, <0.001)은 v6/residual-stripped style
Paper 현재 macro 값 (0.072, 0.0515)은 v1/full 4-way style

또 한 가지: Phase 0의 ANOVA는 "binary verdicts"에 대한 4-way ANOVA. 이전 paper의 cresFive computation도 binary verdicts였는지, 아니면 continuous compliance scores였는지 확인 필요.
해결 옵션:

(A) Phase 0 ANOVA setup이 paper의 cresFive computation과 다름 → 둘 다 보고. cresFive는 deprecated.
(B) Phase 0 ANOVA setup이 paper computation과 같은데 결과가 다름 → corpus 차이 또는 evaluator pool 차이 (paper는 6 evaluators, Phase 0은 4 non-degenerate).
(C) Paper's cresFive는 measurement bug였고, Phase 0의 0.078/<0.001가 정확.

Phase 1 priority: 이 셋 중 어느 것인지 확정. 그리고 paper Abstract에서 어느 number를 cite할지 lock.
중요: 이번 세션에서 우리가 "1.40× ratio"로 lock했는데, Phase 0 audit는 "evaluator 0.078, run <0.001 → ratio 78×+ very large"로 측정. 만약 후자가 correct이면 이전 lock은 invalid.
이 discrepancy는 paper Abstract에 직접 영향. 우선순위 매우 높음.
III.3 DxEM pass rate — paper macro stale
Phase 0 §6.2:

DxEM 16,944/16,944 = 100% (constant True)

Paper macro 추정:

\passrateDxEM{50.5} (이전 세션 context에서 인지)
audit kit 본문: "dxem returns pass on every episode (50.5%, equal to TOM)"

해석:

"every episode"라는 표현은 100% pass 의미
50.5%는 다른 수치 (혹시 실제로는 TCC pass rate? CwT? 다른 evaluator 수치를 잘못 attribute?)

가능한 history reconstruction:

초기 코드: DxEM이 selective (50.5% pass)
이후 변경: DxEM이 trivial True
50.5% 는 stale snapshot
또는: 50.5%는 different metric (예: agreement with TCC)이고 잘못 "pass rate"로 명명됨

Phase 1 action:

DxEM의 실제 코드 history 점검 (git blame 또는 commit log)
Paper에서 \passrateDxEM{50.5} cite하는 모든 location 확인
정확한 의미 명시 또는 수정

III.4 Pi-class assignment의 directness — paper와의 framing 충돌 가능
Phase 0 §부록 C:

ASC: pi-class nctx (가장 informative)
C2 (CwT): pi-class aset
TCC: pi-class nctx (same as ASC)

Paper의 audit kit shim inventory table에서도 동일한 분류 (ASC = nctx, CwT = aset).
그러나: ASC verdict 함수 (§2.1)는 len(performed & expected) / len(expected) >= 0.5 — 이건 action multiset 기반 coverage. 정의상 pi_aset 측정자.
모순 또는 설명 필요:

ASC가 multiset에서 verdict 도출 → pi_aset이 자연스러운 분류
그러나 behavioural classifier (Step 1 separating-pair test)는 nctx로 분류
이는 ASC가 expected_actions의 정의에 의존하기 때문 (만약 expected_actions가 patient-state-conditional하면 ASC는 effectively context-aware → nctx)
또는 다른 설명 (separating-pair behavioural test의 design choice)

Implication:

Paper가 "ASC is pi_aset projection"이라고 cite하면 잘못된 framing
Paper가 "ASC behavioural class is pi_nctx"라고 cite하면 정확

Phase 1 action:

Paper의 ASC pi-class cite를 모두 점검
"pi-class"의 의미를 명시: "behavioural classifier output" vs "theoretical projection target"
만약 둘이 일관되게 다르면 disclose

III.5 Strict consensus FA 6.6% vs Looser 11.6% — 정의 verification 필요
Paper:

\strictFAThree{6.6} = 1118/16944 episodes
\faAllOblivious{11.6} = (likely 1959/16944)

Phase 0:

"Consensus FA (all-oblivious): 11.6% (1,959 에피소드)"
6.6%는 cite 안 됨 (적어도 직접적으로)

Question: 6.6%과 11.6%의 정확한 정의 차이?
내 추정:

6.6% strict: ASC ∩ CwT ∩ PAF pass + TCC fail (3-way intersect, 모두 동의해야 pass)
11.6% all-oblivious: 어느 식의 가장 permissive consensus? 또는 TOM 포함 4-way?

만약 TOM = always True이면, ASC ∩ CwT ∩ PAF ∩ TOM = ASC ∩ CwT ∩ PAF (TOM이 constraint 안 됨). 그러면 3-way = 4-way가 같은 1118 episodes.
하지만 1118 ≠ 1959. 다른 정의.
Phase 1 action: 두 macros의 정확한 computation 코드 점검. 정의 difference 명시.
III.6 추가 발견: Per-violation type Bayes matrix 미언급
Paper §App app:bayes_matrix_per_type에 4×5 = 20 cells의 per-projection × per-violation-type Bayes errors. 매크로:

\bayesErrTermOmission, \bayesErrTermCommission, \bayesErrTermTiming, \bayesErrTermSequence, \bayesErrTermDeviation × 4 projections = 20

Phase 0 §3.4는 4 aggregate Bayes errors만 cite. 20-cell matrix는 다루지 않음.
Phase 1 action: per-coord per-type Bayes errors도 typed verdicts로 재계산. Phase 3 에 포함.
III.7 Bootstrap CIs 미언급
Paper 매크로:

\bayesErrTermCI{[0.428,0.444]}, \bayesErrAsetCI{[0.019,0.024]}, \bayesErrNordCI{[0.002,0.003]}, \bayesErrNctxCI{[0.002,0.003]}

Phase 0 spec §부록 D는 "Bootstrap iterations B=1000, seed=42" 명시했지만, Bayes error CI 별 결과가 명시 안 됨. CI도 재계산 필요.

IV. Phase 0가 implicit하게 lock한 결정 (명시 권고)
이전 design에서 7 critical decisions로 enumerate한 것 중 Phase 0가 implicit하게 답한 것:
IV.1 Decision 1 (Corpus) — partial lock

Phase 0 spec: v6 = 16,944 episodes
이전 user audit: "Phase A v6 (n=18,586)" — 다른 snapshot
확인 필요: 16,944 v6과 18,586 v6이 동일한 corpus인가?

만약 다르면, Phase 0 spec은 16,944를 v6 final로 fix한 것. 이건 Decision 1 = Path I (v5 only) 와 동치 (16,944는 paper v17의 episode 수).
명시적 lock 필요: paper에 어느 corpus 사용?
IV.2 Decision 2 (d_G) — lock as α (typed)

Phase 0 §4: "d_G-typed" 명시
Decision 2 = α 채택

IV.3 Decision 3 (C1 handling) — lock as ε (keep + flag)

Phase 0 §부록 B: C1 sub-score 공식 그대로 유지 (1 - deviation_count / max(...))
Drop or decompose 안 함
Decision 3 = ε (keep + flag as author-dependent)

이는 이전 Phase 0 design과 약간 다름 (제가 이전에 Option α를 권장했음). 사용자가 ε를 implicit하게 선택. 좋은 결정 — backward-compatible하고 paper의 C1-C5 framework 유지.
IV.4 Decision 4 (TOM) — fully resolved

100% pass rate, ANOVA 제외

IV.5 Decision 5 (Pre-registration) — partial lock

Git tag re-experiment-v1-spec-frozen 생성
Internal repo registration (minimal scope)
arXiv 또는 OSF는 미결정 (보통 internal로 충분, 강한 governance 원하면 추가)

IV.6 Decision 6, 7 — open

Decision 6 (new experiments inclusion): Phase 0 spec에서 언급 안 됨. Phase 4/5/Future로 deferred.
Decision 7 (sensitivity reporting depth): Phase 0 spec에서 언급 안 됨.