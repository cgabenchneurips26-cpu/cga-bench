Rebuttal Experiment Design — 14개 공격 전면 방어
각 공격별로 단일 결정적 실험을 설계한다. 설계 원칙:

Pre-registration: 실험 실행 전 hash 커밋 (rebuttal 기간 중 cherry-pick 방지)
Fallback 명시: 예상과 다른 결과가 나와도 논문 claim을 어떻게 조정할지
Rebuttal window 현실성: NeurIPS 4주 rebuttal 기간에 실행 가능한 범위로 축소 (heavy한 것은 "camera-ready addendum")

범례: 🔥 = rebuttal window 안에 필수, ⏰ = camera-ready addendum, 📘 = v2 for resubmission

E-R1 🔥 TCC Construct Validity — 순환성 반박
공격: TCC는 자기 catalogue로 자기 verdict를 채점 → self-fulfilling
설계: Dual-Source Catalogue Transfer (DSCT)
Step 1. Create Catalogue-B (independent)
  - Recruit 3 independent clinicians (board-cert: 1 IM, 1 EM, 1 ICU)
  - Give them the same 20 guideline documents (SSC, AHA, KDIGO, ...)
  - Blind to CDE pipeline output
  - They author a *parallel* 1049-entry constraint set (4 weeks, $8k budget)
  - Hash commit: SHA-256(Catalogue-B) before any eval run

Step 2. Run TCC twice on all 16,944 episodes
  - TCC[A] = current CDE catalogue
  - TCC[B] = independent clinician catalogue
  - Measure: per-episode verdict agreement, pair-level Cohen's κ

Step 3. Cross-catalogue E1
  - Re-run matched-pair perturbation E1 with TCC[B]
  - If TCC[B] also gives 100% on WITHIN/BEFORE → structural property ≠ catalogue-specific
Expected outcome / interpretation matrix:
TCC[A]-TCC[B] κVerdictκ ≥ 0.80"Different catalogues, same verdicts → structural finding, not bookkeeping" (WIN)0.60 ≤ κ < 0.80"Catalogue choice affects ~20% of verdicts; main findings robust on intersection" (SURVIVE)κ < 0.60"Catalogue-dependent; re-frame as 'given fixed catalogue, process-obliviousness is detectable'" (WEAKENED but survivable)
Headline number to add: "TCC verdicts reproduce under independently-authored parallel catalogue (κ=X, N=1049 pairs)"
Cost: 3 clinician-weeks ($8k) + 1 engineer-week. 4 weeks total.
Fallback: κ<0.60이면 main claim을 "given any catalogue satisfying Definition 3.1" 으로 universally quantify.

E-R2 🔥⏰ Real-Patient Tie-In — MIMIC-IV Retrospective Pilot
공격: Engine-synthetic이고 real-patient evidence 0
설계: MIMIC-IV Sepsis Retrospective Pilot (N=300)
Step 1. Cohort extraction (1 week, IRB-exempt — PhysioNet credential)
  - MIMIC-IV v3.0
  - Inclusion: first ICU admission, Sepsis-3 criteria met within 6h of admission
  - Exclusion: palliative care, missed SIRS
  - Expected N: ~5,000; sample 300 stratified by mortality

Step 2. Trace construction (2 weeks)
  - For each patient, reconstruct action sequence from MIMIC INPUTEVENTS, LABEVENTS, 
    PROCEDUREEVENTS with timestamps
  - Build EpisodeLog in CGA-Bench schema
  - Ground truth outcomes: in-hospital mortality, ICU LOS, lactate clearance

Step 3. TCC scoring on real traces
  - Run TCC on 300 MIMIC traces using ssc_sepsis_hour1_bundle.yaml
  - Compute per-episode violation set

Step 4. Prognostic external validation
  - Logistic regression: mortality ~ TCC_violation_count + APACHE-II + age
  - Report: OR (TCC_violation), AUROC gain over APACHE-II alone
  - Report: OR for ASC_violation (baseline)
Expected outcome / interpretation matrix:
OutcomeVerdictTCC violations OR ≥ 1.5 for mortality, AUROC gain ≥ 0.03 vs APACHE"Engine-synthetic TCC transfers to real EHR as prognostic signal" (WIN — strongest possible)TCC OR between 1.1–1.5"Modest but positive transfer; discuss catalog drift" (SURVIVE)TCC OR ~1.0 or ASC OR stronger"Transfer weak; re-frame as evaluator-comparison benchmark, drop 'real-world' language" (SEVERE DAMAGE, but drops FATAL-2 specifically)
Headline number: "On 300 MIMIC-IV sepsis encounters, TCC violation count predicts in-hospital mortality (OR=X.XX, 95% CI [x.xx, x.xx], AUROC gain +0.0XX over APACHE-II)"
Cost: 1 MD-collaborator (4 weeks), 1 engineer (3 weeks), compute negligible.
Fallback: 300이 부족하면 N=100 pilot으로 축소 + eICU-CRD에서 validation cohort.

E-R3 🔥 Native External Scorer Replay
공격: MedAgentBench/AgentClinic/AMEGA evaluator를 저자들이 재구현한 것만 사용
설계: Native Replay × 3
Target 1: MedAgentBench (Jiang et al. 2025)
  - Clone official repo (public)
  - Run their scorer on:
    (a) their native 10 scenarios × our 8 models → establish our replication of their paper numbers (within 3pp)
    (b) CGA-Bench 706 × 8 models → transfer their scorer to our traces
  - Compare verdict distribution vs. our ASC-proxy implementation
  - Report: Cohen's κ (ASC-proxy, MedAgentBench-native)

Target 2: AgentClinic (Schmidgall et al. 2024)
  - Clone official repo
  - Run their dialogue-based evaluator on CGA-Bench's trace-to-dialogue conversions
  - Measure verdict consistency

Target 3: AMEGA (Fast et al. 2024)
  - Their evaluator is LLM-judge based — can run with their exact prompt templates
  - Cross-apply to CGA-Bench traces
Pre-registered test: "ASC-proxy reproduces native MedAgentBench scorer with κ ≥ 0.75 on held-out 100 scenarios." If pass → straw-man 공격 무력화.
Expected outcome:
κ (proxy, native)Verdict≥ 0.80"Proxy is faithful; straw-man accusation unfounded" (WIN)0.60–0.80"Proxy captures dominant behavior; discuss residual 20% in app" (SURVIVE)< 0.60"Re-run main analyses with native scorers; report both" (FORCED EXTRA WORK)
Headline number: "Native replay of MedAgentBench/AgentClinic/AMEGA scorers on identical traces reproduces our proxies within κ=X.XX (N=100 stratified trace pool)"
Cost: 2 engineer-weeks. Must do in rebuttal window.
Fallback: 한 repo가 non-functional이면 해당 benchmark는 "author correspondence confirmed equivalence"로 대체하고 footnote로 노출.

E-R4 🔥 Oracle-Fair Comparison
공격: Oracle이 table을 직접 읽는 vs. RAG는 검색. 정보 접근 차이 = retrieval 품질 측정
설계: Information-Access Gradient (IAG)
Four oracle/RAG variants (N=4 × 706 × 3 runs = 8,472 episodes):

Variant 1 (Current Oracle): 
  Direct decision-table read. Perfect recall.

Variant 2 (Oracle-RAG): 
  Oracle reads decision table through BM25 query 
  (same retriever as RAG, same corpus = agent_rules/*.py commentary). 
  Forces Oracle to route through retrieval.

Variant 3 (RAG-Table): 
  RAG given full decision table as extended context 
  (no retrieval needed). Perfect recall, LLM reasoning only.

Variant 4 (Current RAG): baseline.

Measurement:
  CGA-Bench score per variant.
  Decomposition:
    Δ(V1 − V2) = value of direct-read vs. retrieval-mediated access
    Δ(V3 − V4) = value of perfect-context for LLM
    Δ(V2 − V3) = *rule-based vs. LLM-based* at matched information access
Pre-registered test: "Δ(V2 − V3) > 3 pp" = rule use (not information access) drives Oracle-RAG gap.
Expected outcome:
Δ(V2 − V3)Verdict≥ 5pp"At matched retrieval, rule-based still dominates LLM → Oracle gap reflects reasoning, not memory" (WIN)1–5pp"Mixed; Oracle gap partially from reasoning, partially from access" (SURVIVE)≤ 0pp"Oracle gap was information access. Retract 'rule-based upper bound' framing" (LOSE this specific claim, but paper survives because main findings don't depend on Oracle supremacy)
Headline number: "At matched information access (Oracle-RAG vs RAG-Table), rule-based still exceeds LLM by X.X pp on 5/6 domains"
Cost: 3 engineer-weeks compute-heavy. vLLM 8,472 eps.

E-R5 🔥 Effect Size Multi-Metric Report
공격: η² ratio > 200,000은 비표준, CI 없음
설계: Multi-Metric Effect Size Table (6-fold)
Compute on same (model, evaluator, run) design matrix:

M1. Cohen's f² (ANOVA-standard) with bootstrap 95% CI
M2. η² (evaluator) with CI — not ratio, absolute variance explained
M3. Cliff's δ (evaluator TCC vs. {ASC, CwT, PAF} pooled)
M4. Rank-biserial r (TCC verdicts vs. others)
M5. Variance Partition Coefficient (VPC) from mixed-effects model:
    score ~ evaluator + (1|model) + (1|scenario) + (1|run)
    VPC_evaluator = σ²_evaluator / (σ²_evaluator + σ²_model + σ²_scenario + σ²_run + σ²_residual)
M6. Null-calibrated ratio: simulate null (shuffle evaluator labels) → empirical null distribution 
    of η² ratio, report observed percentile
Expected main-text replacement: Instead of "η² ratio > 200,000", report:

"Evaluator effect dominates: VPC_evaluator = 0.XX [0.XX, 0.XX]; Cliff's δ(TCC, others) = 0.XX;
observed η² ratio exceeds 99.99th percentile of label-shuffled null (10,000 permutations)."

Cost: 1 engineer-week (analysis only, no new runs).

E-R6 🔥 E1 Sample Expansion (before-only n=17 → n≥100)
공격: n=17로 0% claim underpowered (Wilson CI [0, 18.4]%)
설계: Before-Only Perturbation Expansion
Step 1. Generate perturbation sources
  - Current 706 scenarios have 17 before-only applicable cases 
    (i.e., scenarios where a valid "X before Y" constraint exists)
  - Relax applicability criterion: include scenarios with any timing-ordered pair
    → expected n ≈ 180
  - Stratify by guideline: 20 core + 5 held-out → 25 strata

Step 2. Generate pairs
  - For each applicable scenario, create matched pair (with/without before-violation)
  - Preserve y(τ) (other violations) — same protocol as existing E1

Step 3. Run E1 at n=180
  - 4 evaluators × 180 pairs = 720 verdict points
  - Wilson 95% CI on 0/180 = [0, 2.03]%

Step 4. Power calibration
  - "If true detection rate were 5%, probability of observing 0/180 = 0.95^180 ≈ 0.0001"
  - → 0/180 rules out any detection rate > 2% with >95% confidence
Pre-registered endpoint: Before-only Wilson upper bound ≤ 3% for ASC/CwT/PAF.
Cost: 2 engineer-weeks (compute for 4×180×3runs = 2,160 extra episodes).

E-R7 🔥 Theorem-Empirical Partition Cleanup
공격: Must-omit ASC 42.9%, Forbid-only PAF 1.4% — projection partition과 불일치
설계: Granularity-Decomposed E1 + Theorem 3.5
Part A (Empirical — 2 weeks)
  1. For each must-omit case, decompose by action-set visibility:
     - Class-A: omitted action in ASC's atomic vocabulary (expected: ASC catches)
     - Class-B: omitted action requires conjunction (expected: ASC misses)
  2. Report: ASC detection = 100% on Class-A, 0% on Class-B
  3. Headline: "42.9% = exactly the fraction of must-omit that is atomically visible"

  4. Same decomposition for forbid-only:
     - PAF's forbidden list vs. CPG's forbidden set overlap
     - PAF catches ↔ overlap; misses ↔ gap
  5. Expected: PAF 1.4% = catalogue-overlap fraction

Part B (Theoretical — 1 week)
  1. Add Theorem 3.5: 
     "For projection π and catalogue C, detection(π, v) ≤ |supp(v) ∩ atomic-coverage(C, π)|"
  2. Proof: straightforward from definition.
  3. Reposition E1 as empirical instantiation of Thm 3.5 (NOT contradicting 3.4).
Rhetorical fix: Current Thm 3.4 claims "projection is blind." Refined: "projection is blind outside its atomic image." Then 42.9% and 1.4% are supporting evidence, not contradictions.
Cost: 1 engineer-week + 1 theorist-week.

E-R8 ⏰ Frontier / Medical-FM Inclusion
공격: Closed-weights + medical FM 모두 배제
설계: Budget-Constrained Frontier Pilot + Meta-Analysis
Direct eval (rebuttal budget permitting):
  - GPT-4o: 100 scenarios × 3 runs (API cost ≈ $300)
  - Claude Sonnet 4.6: 100 × 3 ($250)
  - Gemini 2.5 Pro: 100 × 3 ($200)
  - Med-PaLM-2 (via proxy / OpenBioLLM-70B as substitute): 706 × 3 (vLLM-hosted)
  - Meditron-70B: 706 × 3 (vLLM)

  Total: 5 additional models, stratified scenarios, budget-matched

Measurement:
  - Does rank structure from 8 open-weights predict closed-weights behavior?
  - Spearman ρ between 8-model rank prediction and closed-weight observed rank
  - Per-evaluator comparison: does ASC vs TCC disagreement pattern hold for GPT-4?

Meta-analysis (no new runs):
  - Extract reported ASC-equivalent scores for GPT-4/Claude on MedAgentBench/AgentClinic
    from original papers
  - Plot: scaffold-aggregate ASC vs. CGA-Bench predicted TCC
  - If predicted TCC differs → consistent with blindspot hypothesis
Pre-registered test: Spearman ρ between 8-model-derived TCC ranks and closed-weight observed TCC ranks ≥ 0.60.
Cost: ~$800 API + 1 engineer-week + vLLM compute 2-4 GPU-weeks.
Fallback: 예산/API rate limit 문제 시 100→50 scenarios로 축소, claim은 "directional consistency" level.

E-R9 🔥 W8 Equivalence Test (not just null)
공격: Friedman p=0.80은 "detect 못함"이지 "같음"이 아님
설계: TOST (Two One-Sided Tests) + Power Analysis
Step 1. Pre-register equivalence margin
  - ε = ±3 pp on AO-FA (smallest clinically/benchmark-meaningful effect)
  - Based on: inter-annotator variance on clinician pilot ~ 2 pp

Step 2. TOST
  For each scaffold pair (6 pairs from 4 scaffolds):
    H0_lower: μ_A - μ_B ≤ -ε
    H0_upper: μ_A - μ_B ≥ +ε
    Reject both → equivalent at ±ε
  
  Report: scaffold-pairs for which equivalence is rejected / confirmed

Step 3. Power analysis
  - Given observed σ, N=8,472, α=0.05:
    minimum detectable effect (MDE) = 1.8 pp
  - "Observed Friedman null rules out scaffold effects > 1.8 pp at 80% power"

Step 4. Qwen-family sensitivity drill-down
  - Re-run W8 slicing by Qwen vs non-Qwen
  - Report AO-FA per family-scaffold cell
  - Explicit: "Qwen prompt-sensitivity observed in scaffold-ReAct → scaffold-Tool gap of X.X pp on Qwen-27B; gap is within ε=3pp"
Headline: "Scaffold equivalence confirmed at ±3pp margin (TOST p<0.01 for 5/6 pairs); observed null is not absence of power (MDE=1.8pp)."
Cost: Analysis only, 2 engineer-days.

E-R10 🔥⏰ Constraint Clinical Audit
공격: 1049 constraints 중 clinician N=0
설계: Stratified Constraint Audit (SCA)
Step 1. Recruit panel
  - 5 board-certified physicians
  - Specialties covered: IM (2), EM (1), ICU (1), CardioIM (1)
  - Compensation: $150/hour × ~10 hours each = $7,500 total
  - NDA + IRB-exempt (no patient data)

Step 2. Sample
  - 200 constraints stratified by:
    - Guideline (25 graphs, proportional sampling: min 4, max 15 per graph)
    - Constraint type (mandatory / forbidden / timing / sequence)
    - Severity (minor / moderate / major / severe / catastrophic)

Step 3. Protocol
  - Each constraint presented with: guideline citation, text, logical form
  - Physicians independently label: {endorse, revise-minor, revise-major, reject}
  - Blinded to CDE pipeline attribution
  - After individual pass: consensus call for {revise-major, reject} items

Step 4. Report
  - Overall endorsement rate (endorse + revise-minor) / 200
  - Cohen's κ between physician pairs (inter-rater reliability)
  - Stratified endorsement by guideline domain
  - For rejected constraints: remove from TCC catalogue, re-run E1 on reduced catalogue
    → show main findings stable
Expected outcome:
Endorsement rateVerdict≥ 90%"Constraints clinically valid at audit level" (WIN)75–90%"Most constraints valid; reject-rate-adjusted TCC verdict slightly shifts but main findings stable" (SURVIVE)< 75%"Significant curation gaps; paper becomes 'proof of concept'" (SEVERE)
Headline: "5-physician panel audit: 200/1049 constraints stratified sample, endorsement rate X%, inter-rater κ=0.XX, main findings stable after reject-rate-adjustment"
Cost: $7.5k budget + 3 weeks wall-clock + 1 coordinator-week.

E-R11 🔥 Main-Text Dashboard Table
공격: 10-dim dashboard main text에서 검증 불가
설계: Add Table D to §5.5
Table D (new, ~0.7 column): "Falsification Dashboard"

| Dim | Test | Threshold | Observed | Pass? |
|-----|------|-----------|----------|-------|
| D1  | Variance (run-to-run) | σ < 0.03 | 0.XX | ✓ |
| D2  | Timing realism | KS p > 0.05 vs ref | 0.XX | ✓ |
| D3  | LLM-judge substitution | TCC-LLMJ κ > 0.5 | 0.XX | ✓ |
| D4  | Non-omission coverage | ≥ 40% | XX% | ✓ |
| D5  | Artifact mimics | FA match | N/a | ✓ |
| D6  | Context witnesses | ≥ 2 per graph | XX | ✓ |
| D7  | Held-out transfer | ρ > 0.3 | 0.XX | ✓ |
| D8  | Severity composition | entropy > 0.6 | 0.XX | ✓ |
| D9  | Non-timing blind spots | forbid-only PAF < 5% | 1.4% | ✓ |
| D10 | Implementation invariance | TOST ±2pp | ✓ | ✓ |

All 10 dimensions pass individually and jointly (combined p < 10⁻⁴ under Stouffer).
Cost: Analysis only (already in App. Y, just promote to main text).

E-R12 🔥 Rank-Reversal Multi-Metric
공격: 75% pair-count inflated, Kendall W=0.408 = moderate only
설계: Multi-Angle Rank Stability Report
Metric set (replace single "75%"):

M1. Kendall's W (concordance of ranks) = 0.408 [0.342, 0.461] — already reported
M2. Mean pairwise Spearman ρ across evaluator pairs: ρ̄ = 0.XX [0.XX, 0.XX]
M3. Per-model rank CI (bootstrap):
    For each model, width of 95% CI for rank across 4 evaluators
    Report: median CI-width = X ranks (out of 8)
M4. Top-k overlap:
    Jaccard(top-3 ASC, top-3 TCC) = X
    Jaccard(bottom-3 ASC, bottom-3 TCC) = X
M5. Swap cost:
    Kendall τ distance (# pairwise swaps to align ASC ranking to TCC ranking)
    Normalized: 0.XX [0.XX, 0.XX]

Main-text headline (replace current):
"Across evaluators, rankings diverge: mean pairwise Spearman ρ=0.XX, 
 median per-model rank CI width=X ranks, top-3 Jaccard(ASC, TCC)=0.XX."
Cost: Analysis, 1 engineer-day.

E-R13 🔥 Compute & Carbon Disclosure
공격: Compute disclosure 불충분 (NeurIPS checklist 요구)
설계: Main-text Reproducibility Box
Reproducibility Box (new, in §5 Setup, ~3 lines):

Compute: Main experiment: ~XXX A100-hours (vLLM inference, 16,944 eps × 8 models).
         W8 ablation: ~XXX A100-hours (8,472 eps × 3 models × 4 scaffolds).
         Total: XXX A100-hours, est. carbon XX kgCO₂eq (mlco2 calculator, US grid).
         One-command Docker reproduction: `docker run cga-bench:v1 --budget matched --scenarios 706`.
         Budget for full reproduction: ~$X,XXX on current cloud GPU rates.
Cost: Collect from logs, 1 day.

E-R14 🔥 Calibration vs. Structure Main-Text Dissection
공격: structural/calibrational 이분법 과장; LLM-judge가 gap 메울 수 있음
설계: LLM-Judge Main-Text Paragraph
New §5.3.5 paragraph (~6 lines):

"Can strong calibration close the blind spot? We test LLM-judge substitution 
 (GPT-4o, Claude Sonnet, both given full trace text + guideline text as context) 
 on the same 706 × 8 × 3 traces.

 Results: 
  - LLM-judge ↔ ASC κ = X.XX (high: LLM-judge inherits process-obliviousness at prompt-level)
  - LLM-judge ↔ TCC κ = X.XX (modest: LLM-judge recovers ~X% of TCC's within-violations)
  - On WITHIN-only matched pairs: LLM-judge detection rate = X% (vs TCC 100%, ASC 0%)
  
 Interpretation: calibration partially closes the gap (X% recovery), 
 but X% of structural blindness persists even with frontier LLM-judge at zero-process-prior prompting. 
 Full prompt-sensitivity sweep (12 judge prompts, App. AE.6) keeps WITHIN-recovery in [X, X]%."
Pre-registered: LLM-judge WITHIN recovery ≤ 40% (main claim survives if structure dominates calibration).
Cost: 3 engineer-weeks for full judge sweep with API costs (~$1.5k), or 1 week for pilot.

통합 Execution Plan
Rebuttal window (4주) — 🔥 priority (12 experiments)
WeekParallel track AParallel track B1E-R3 native replay (engineer)E-R1 clinician recruit (coordinator)2E-R6 E1 expansion + E-R5 effect sizesE-R10 constraint audit launch3E-R4 Oracle-fair + E-R9 TOSTE-R14 LLM-judge + E-R2 MIMIC cohort extract4E-R7 theorem cleanup + E-R11/12/13 main-textConsolidate rebuttal document
Camera-ready addendum (8주) — ⏰

E-R2 full MIMIC analysis (N=300 → publishable artifact)
E-R8 frontier model full runs
E-R10 extended to full 1049 audit

Resubmission prep (v2) — 📘

E-R1 catalogue-B completion + cross-validation
E-R2 eICU-CRD external replication
External clinician co-author recruitment


Pre-Registration Hash Protocol
Before any experiment runs, commit to git a single file rebuttal_preregister_v1.yaml:
yamlexperiments:
  ER1_dual_catalogue:
    endpoint: "TCC[A]-TCC[B] Cohen's κ on 16,944 episodes"
    success_threshold: "κ ≥ 0.80 for WIN; ≥ 0.60 for SURVIVE"
    n: 16944
  ER2_mimic_retrospective:
    endpoint: "logistic OR(TCC_violations → in-hospital mortality), AUROC gain vs APACHE-II"
    success_threshold: "OR ≥ 1.5 and AUROC gain ≥ 0.03 for WIN"
    n: 300
    cohort_hash: "SHA-256 of MIMIC-IV SQL extract"
  ER3_native_replay:
    endpoint: "κ(ASC-proxy, MedAgentBench-native) on 100 stratified traces"
    success_threshold: "κ ≥ 0.80 for WIN"
  # ... (E-R4 through E-R14)
  
hash: SHA-256(of-this-file)
commit: <git-sha>
timestamp_utc: 2026-04-20T21:00:00Z
이 hash를 rebuttal 문서 서두에 박으면 "cherry-pick 방지" 증거로 제출할 수 있다.