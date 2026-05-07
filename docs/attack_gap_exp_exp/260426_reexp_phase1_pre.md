III.1 Phase 1.A — Code Changes (Phase 0.C 권고 + 사용자 결정 반영)
A1: typed_compliance_score 구현 (Phase 0 §7.1)

assessor_core/harm_scorer.py 수정: compliance_score에서 DEVIATION/OMISSION 제외하는 옵션 추가
또는: 새 typed_compliance_score 함수 + cwt_verdict가 이걸 사용

A2: ACov 처리 (Phase 0 §7.2)

Phase 0 권고: backward-compat 유지
사용자 결정 필요: ACov column 완전 폐기 vs 유지? (default: 유지, paper에서 "5 effective" 명시)

A3: DxEM ANOVA exclusion (Phase 0 §7.3)

ANOVA factor에서 TOM/DxEM 제외 (already in Path 4)

A4: dg_typed_cost 신규 추가 (Phase 0 §7.4)

weights {commission: 1.0, timing: 0.5, sequence: 0.6}
assessor_core/spec/verdict_definitions.py에 export

A5: P0 fixes 적용 (Phase 0.B §VI.1)

\dxemPassRate{50.5} → \dxemPassRate{100.0} (auto_numbers.tex:994)
"anti-correlated" → "positively correlated" (tables_audit_kit_shim_inventory.tex:36)
Phase 0 report §4.3 omission paragraph 재작성
\normalizerMMEpisodes name fix

A6: Self-audit Contribution 5 LaTeX 추가 (위 §I Move 4)
A7: ASC pi-class footnote 추가 (위 §I Move 3)
A8: 25.1% guard comment 추가 (Phase 0.C §1)
III.2 Phase 1.B — Re-scoring (compute, GPU)
B1: Verdict 재계산 — 16,944 episodes × 5 evaluators × typed definitions

TCC (unchanged)
CwT (typed) ← NEW
ASC (unchanged)
PAF (unchanged)
TOM (always True, ANOVA exclude)
ACov (= ASC)

Output: evidence_pack/verdicts/verdict_matrix_v6_typed_phase1.json
B2: d_G 재계산 — 16,944 episodes

d_G-typed cost function (commission 1.0 + timing 0.5 + sequence 0.6)
Output: evidence_pack/dg/dg_typed_v1.parquet

B3: Sub-score 재계산

C2-C5: clean (typed verdicts 적용)
C1: keep formula (per Phase 0 ε), flag in paper

III.3 Phase 1.C — Re-aggregation
C1: Hero numbers

Strict consensus FA (3-way + 4-way variants)
Looser consensus FA (variants)
η² (Path 4 4-way ANOVA, locked) ← critical: see if 0.072 holds
Pair reversal (verify_friedman_eta.py with typed verdicts)
Per-projection Bayes errors + bootstrap CIs (1000 samples)
Per-coord per-type Bayes matrix (4×5 = 20 cells)

C2: Pose B re-execution

3 catalogues × typed CwT × 16,944 episodes
Pillar 1/2/3 evidence
Dual-family ratios (5.50× / 5.60×)

C3: Sensitivity table

All hero numbers: original (buggy CwT) vs typed (corrected CwT)
Per-row Δ + relative %
This is the §App app:cwt_correction content

III.4 Phase 1.D — EXP-2 Oracle-Informed LLM Judge (D2 채택)
D1: rubric_aware prompt with same trajectories

Compute: small (1000-2000 episodes sample 가능)
Output: per-temperature/per-prompt rubric-aware FA rates

D2: cot_judge prompt with same trajectories

Same protocol

D3: Compare blind (T0-T3) vs oracle-informed

Table in §App

III.5 Phase 1.E — Verification
E1: Theorem 1 4-projection ordering

ε_term > ε_aset > ε_nord ≈ ε_nctx 보존 확인

E2: E1 matched-pair detection

0%/0%/1.4% vs 100% 보존 확인 (typed CwT under)

E3: Constructive π_nord witness BSR 재계산

V3_half_expected = 0.4914 → ?
Floor 0.003 → ?
Gap factor 164 → ?

III.6 Phase 1.F — Paper Integration
F1: All Category B macros update (~1,166 macros)

Macro by macro check

F2: Affected sections rewrite

Abstract numbers
§1 Contributions (add Contribution 5)
§3 Theorem 1 (add ASC footnote)
§Methods (add CwT correction subsection)
§Limitations (Messick framework, audit governance)
§App: new sections (self_audit, cwt_correction, llm_judge_oracle, evaluator_audit_table)

F3: Cross-reference verify

All cite-points consistent
Macro values match in code + LaTeX

F4: Final compile + page count + integrity audit

IV. Open Decisions (smaller list)
Phase 0.C가 대부분 close했지만 남은 것들:
IV.1 ACov 처리 (Phase 1.A2)

Option α: 완전 폐기 (column 제거, ANOVA 제외, paper에서 "5 evaluators" 표기)
Option β: Backward-compat 유지 (column 유지하되 paper에서 "5 effective"라고 명시) ← Phase 0 권고
제 권고: β. 변경 비용 작고 backward-compat 유지.

IV.2 EXP-2 Oracle-informed LLM Judge depth

Option α: rubric_aware만 run
Option β: rubric_aware + cot_judge 둘 다
Option γ: Skip (D2 = "재실험"이지만 결과 weak이면 안 함)
제 권고: α (rubric_aware만 우선). 결과 strong이면 cot_judge 추가.

IV.3 Phase 1 Sensitivity Reporting Depth

All Category B macros sensitivity table (~1,166 rows)? Too much.
Hero numbers only (8개) sensitivity table? Too little.
제 권고: Hero + secondary (~25-30 macros) sensitivity table in §App.

IV.4 Pre-registration scope

Phase 0가 internal Git tag로 lock. arXiv preprint 또는 OSF DOI 추가 필요?
제 권고: 지금은 internal로 충분. 만약 reviewer가 강조하면 camera-ready에서 추가.