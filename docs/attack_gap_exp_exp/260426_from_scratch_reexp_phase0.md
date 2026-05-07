D.0 Phase 0 — Audit + Specification FreezeGoal: 재실험 전에 정확히 무엇을 measure하는지, 어떤 fields/code/data가 input인지 확정.Subphases:0.A — Code dependency audit (1-2일):

각 evaluator (TCC, CwT, ASC, PAF, TOM, plus any others)의 verdict 함수 추출
Verdict 함수가 사용하는 input fields 명시 (allowed_actions? expected_actions? mandatory_actions? forbidden_actions? WITHIN deadlines? BEFORE constraints?)
Source-grounding status per field (rule-based extraction vs author-listed)
d_G computation의 cost function audit (DEVIATION cost weight)
Each sub-score (C1-C5)의 input fields
Each macro의 computation chain trace
0.B — TOM/DxEM disambiguation (반나절):

DxEM/TOM source code locate
Pass rate empirical measurement: python -c "from cga_bench import TOM; print(TOM.pass_rate(episodes))"
결과 분류: (a) always True (b) selective ~50% (c) other
Paper macro \passrateDxEM{50.5} vs \dxemPassRate{50.5} 검증 + reconciliation
0.C — Corpus version commit (즉결):

결정: v5 (16,944), v6 (18,586), or both
Rationale documentation
Pre-registered corpus snapshot (Git tag)
0.D — d_G architectural decision (반나절):

Question: d_G에 DEVIATION cost를 포함하는가?
두 옵션:

Option d_G-typed: cost only on typed violations. Cleanest. Solver Spearman 등 모든 d_G 기반 numbers 재계산.
Option d_G-current: cost includes DEVIATION. Backward compatible. d_G 자체가 author-dependent.


권장: d_G-typed. CwT correction과 architectural consistent. 그러나 더 많은 numbers 재실행.
결정 lock.
0.E — Specification document drafting (1일):

위 0.A-0.D의 결정을 single document에 collect:

Each evaluator's exact verdict function (pseudocode)
Each sub-score's exact computation
d_G cost function
ANOVA decomposition method (v1 4-way, locked)
Pair reversal metric (paper의 정확한 metric, verify_friedman_eta.py 또는 동등)
Bootstrap CI procedure (sample size, seed)
Consensus FA definition variants (3-way, 4-way, etc.)


Pre-registration via Git commit + tag + (optional) anonymous arXiv/OSF upload
0.F — Paper macros catalog (반나절):

Category A (independent), B (dependent), C (borderline) 전수 list
Each macro의 source: 어느 Phase에서 재계산되는지
Cross-reference verification: paper의 모든 cite와 매핑
Phase 0 deliverables:

docs/re_experiment_protocol_v1.md
assessor_core/spec/verdict_definitions.py (formal pseudocode)
tests/test_verdict_definitions.py (unit tests for each)
auto_numbers_audit.csv (Category A/B/C label per macro)
Git tag: re-experiment-v1-spec-frozen
Phase 0 output: pre-registration documentD.1 Phase 1 — Code RefactorGoal: Phase 0 spec을 실제 production code로 implement + verify.
새 module: assessor_core/verdicts/ with one file per evaluator
각 verdict는 pure function (no shared state, deterministic)
Variable naming discipline: typed_compliance_score vs total_compliance_score etc.
Sub-score recomputation aware of construct binding
d_G refactor (Phase 0.D 결정에 따라)
Unit tests pass before any re-experiment
Backward-compat layer: old verdict function 보존하되 deprecated tag (sensitivity analysis용)
Phase 1 output: refactored scoring code + tests + deprecated old code path retained.D.2 Phase 2 — Re-scoreGoal: 모든 episode × 모든 evaluator × 모든 sub-score × d_G 재계산.Compute:

Episode당 ~20ms verdict + sub-score + d_G computation
16,944 episodes × {TCC, typed CwT, ASC, PAF, TOM} verdicts + {C2, C3, C4, C5} sub-scores + d_G + per-projection BSR
Total: ~3-6시간 single-thread, parallel하면 30분-1시간
Output:

verdicts_v2.parquet — per-episode × per-evaluator binary
subscores_v2.parquet — per-episode × per-sub-score scalar
dg_v2.parquet — per-episode d_G
violations_log_v2.parquet — per-violation events
bayes_partition_v2.parquet — per-episode × per-projection fibre identifier
이것들이 모든 hero number의 single source of truth.D.3 Phase 3 — Re-aggregatePhase 2 outputs 위에서 모든 verdict-dependent macros 재계산.D.3.1 Hero claims (Category B 핵심):

Strict consensus FA (3-way, 4-way variants)
Looser consensus FA
Pair reversal (paper's metric, verified definition)
η²(eval), η²(run) — v1 4-way ANOVA, locked
Per-projection Bayes errors + bootstrap CIs (1000 samples)
Per-coord per-type matrix (4×5)
Verdict-mixed fibre fractions
D.3.2 LLM-judge results:

Per-prompt T0/T1/T2/T3 FA rates (Qwen, Gemma)
Note: judge sees action lists; needs verification on whether judge prompt 자체가 allowed_actions를 reference 하는지
D.3.3 Replay results:

MAB-style replay (action-set F1 against expected_actions)
AC-style replay (diagnostic coverage)
Note: expected_actions의 source-grounding (Phase 0.A에서 audit)
D.3.4 Solver agreement:

ILP vs tiered Spearman ρ (under d_G-typed if Phase 0.D 결정)
0 verdict reversals confirmation
D.3.5 Severity & FA breakdown:

Median violations per FA episode
Critical severity %
Non-timing FA count
D.3.6 Robustness dashboard 10 probes:

E5 op-point match (κ)
E6 cluster preservation
GEE odds ratios
Held-out FA
Case 4 no-context witness
기타 5개
D.3.7 X1/X2 ablations:

X1 cross-scenario action substitution (TCC flip vs morph flip)
X2 violation-event ablation + placebo
Phase 3 output: 모든 Category B macros의 새 값 + sensitivity table (vs old values).D.4 Phase 4 — Pose B 재실행이전 설계와 같지만 Phase 0 spec lock 위에서 실행.
3 catalogues × 5 evaluators × all episodes = 보통 250K verdict computations
Per-catalogue consensus FA
Pillar 1, 2, 3 evidence 재산출
Per-catalogue Bayes floor (per-projection)
Phase 4 output: Pose B macros 재계산 (\mainReplTriplePct{} 등 ~10개).