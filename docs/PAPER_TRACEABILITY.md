# Paper-to-Code Traceability Map

Every number in the NeurIPS 2026 paper traces back through a deterministic
chain: **TeX macro -> JSON artifact -> generator script -> raw episode data**.
This document records every link in that chain.

**Paper version**: `paper/main_final_v17.tex` (current)
**Macro hub**: `paper/auto_numbers.tex` (904 lines, ~300 macros)

---

## 1. TeX Input Chain

```
main_final_v17.tex
 |
 +-- \input{auto_numbers.tex}                                 (L52, ~300 macros)
 +-- \IfFileExists ../evidence_pack/normalizer_ablation/multimodel_macros.tex  (L54, 10 macros)
 +-- \IfFileExists ../evidence_pack/cres_1d/cres_1d_macros.tex                (L57, 15 macros)
 +-- \IfFileExists ../evidence_pack/paper_footnotes.tex                       (L60,  3 footnotes)
 +-- \IfFileExists ../evidence_pack/theorem_v2/bayes_error_macros.tex         (L63, 45 macros)
 +-- \IfFileExists ../evidence_pack/audit/audit_macros.tex                    (L66, 41 macros)
 +-- \IfFileExists ../evidence_pack/audit/c6_selection_macros.tex             (L69,  8 macros)
 +-- \input{figures/figure1.tex}                              (L192, TikZ, no external data)
 +-- \input{observation_coarsening_v2.tex}                    (L273, standalone section)
 +-- \input{figures/figure3.tex}                              (L310, -> figure3.png)
 +-- \input{appendix.tex}                                     (L539)
      |
      +-- \input ../evidence_pack/theorem_v2/appendix_theorem_proofs.tex  (L37)
      +-- \input distribution_check_table.tex                             (L931)
      +-- \input heldout_ordering_table.tex                               (L971)
      +-- \input rank_bootstrap_table.tex                                 (L1006)
      +-- \input oracle_per_domain_table.tex                              (L1065)
      +-- \input figures/figure6.tex    -> figure6.pdf                    (L1267)
      +-- \input prompt_sensitivity_agent_table.tex                       (L1279)
      +-- \input figures/figure5.tex    -> figure5.pdf                    (L1470)
      +-- \input figures/figure4.tex    -> figure4.pdf                    (L1575)
```

---

## 2. Main Experiments (E1-E5)

These five experiments form the paper's core analysis (Section 4).
All macros flow through `extract_auto_numbers.py` into `auto_numbers.tex`.

### E1: Verdict Flip (Section 4.1)

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_e1_verdict_flip.py` |
| **JSON** | `evidence_pack/exp_e1_verdict_flip.json` |
| **Table** | `evidence_pack/tables/verdict_flip_matrix.tex` |
| **Macro aggregator** | `scripts/experiments/extract_auto_numbers.py` |

**Key macros**: `\verdictFlipRate{84.0}`, `\verdictFlipCount{14240}`,
`\faAC{42.5}`, `\faMAB{31.9}`, `\faCTwo{14.0}`, `\faCGA{0.0}`,
`\faAllOblivious{11.6}`, `\faAllObliviousCount{1959}`,
`\medianViolFalseAccept{2.0}`, `\pairDisagreeMax{10231}`,
`\vfACvsCGA{10186}` / `\vfACvsCGAPct{60.1}`,
`\vfMABvsCGA{10231}` / `\vfMABvsCGAPct{60.4}`

### E2: Blind-Spot Rate (Section 4.2)

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_e2_bsr.py` |
| **JSON** | `evidence_pack/exp_e2_bsr.json` |
| **Table** | `evidence_pack/tables/bsr_by_evaluator.tex` |

**Key macros**: `\bsrDxEM{50.5}`, `\bsrAC{42.5}`, `\bsrMAB{31.9}`,
`\bsrCTwo{14.0}`, `\bsrCGA{0.0}`,
`\bsrMaxOblivious{50.5}`, `\bsrMinOblivious{14.0}`,
`\medDgAC{2.0}`, `\medDgCGA{0.0}`

### E3: Instrumentation Ablation (Section 4.3)

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/extract_auto_numbers.py` (reads `exp_e3_instrumentation_ablation.json`) |
| **JSON** | `evidence_pack/exp_e3_instrumentation_ablation.json` |
| **Related** | `scripts/experiments/instrumentation_mimic_ablation.py` (runner) |

**Key macros**: `\instrFullHard{8553}`, `\instrFullHardRate{50.5}`,
`\instrHardNoTime{1632}`, `\instrNoTimeLoss{80.9}`,
`\instrWithinOnlyN{6921}`, `\instrViolLostWithin{14989}`,
`\ablationPassFull{49.5}`, `\ablationPassNoTiming{90.4}`,
`\ablationGapActionFull{40.9}`, `\mcnemarTimestampP{<0.001}`

### E4: Operating-Point Matching (Section 4.4)

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_e4_operating_point.py` |
| **JSON** | `evidence_pack/exp_e4_operating_point.json` |
| **Figures** | `evidence_pack/figures/exp_e4_kappa_vs_passrate.png`, `exp_e4_matched_heatmaps.png` |
| **Table** | `evidence_pack/tables/operating_point_matched.tex` |

**Key macros**: `\fleissKappaMatchedFifty{0.056}`,
`\verdictFlipRateMatchedFifty{82.9}`,
`\kappaACvsCGAMatched{-0.125}`, `\kappaMABvsCGAOpFifty{-0.186}`,
`\opPassRateCGAFifty{49.5}`, `\opPassRateACFifty{49.1}`

### E5: Evaluator Expansion (Section 4.5)

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_e5_evaluator_expansion.py` |
| **JSON** | `evidence_pack/exp_e5_evaluator_expansion.json` |
| **Figures** | `evidence_pack/figures/exp_e5_dendrogram.png`, `exp_e5_bootstrap_ari.png` |
| **Table** | `evidence_pack/tables/evaluator_expansion.tex` |

**Key macros**: `\numEvaluatorsExpanded{12}`, `\numClusters{3}`,
`\cophenetic{0.852}`, `\silhouetteScore{0.379}`,
`\bootstrapARI{1.0}`, `\clusterPreservedPct{100.0}`,
`\passRateCGABenchhard{49.5}`

---

## 3. Supplementary Experiments (Appendix)

### EX-20: No-Context Pair

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_e20_no_context.py` (or related) |
| **Evidence** | `evidence_pack/ex20_no_context/` |

**Key macros**: `\noContextPairs{238}`, `\noContextTCCDetect{100.0}`, `\noContextASCDetect{0.0}`

### EX-23: Artifact Mimic Ablation

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_e18_artifact_mimic.py` |
| **Evidence** | `evidence_pack/ex23_artifact_ablation/` |

**Key macros**: `\mimicACDetectionLoss{84.2}`, `\mimicMABDetectionLoss{63.2}`,
`\mimicACFA{42.5}`, `\mimicMABFA{31.9}`,
`\mimicACWithinDetect{15.3}`, `\mimicMABForbidDetect{60.0}`

### EX-24: Consensus FA Severity

| Item | Path |
|------|------|
| **Evidence** | `evidence_pack/ex24_fa_severity/` |
| **Macros** | `evidence_pack/ex24_fa_severity/macros.tex` |

**Key macros**: `\consensusFATotal{1959}`, `\consensusFARate{11.6}`,
`\consensusFACritical{432}`, `\consensusFACriticalPct{22.1}`,
`\consensusFAModelRange{4.6--17.5}`,
`\consensusFAOss{14.3}`, `\consensusFANemotron{4.6}`, `\consensusFADeepseek{17.5}`

### EX-25: Engine Structural Audit

| Item | Path |
|------|------|
| **Evidence** | `evidence_pack/ex25_engine_audit/` |
| **Macros** | `evidence_pack/ex25_engine_audit/macros.tex` |

**Key macros**: `\auditNGraphs{25}`, `\auditTotalRules{1049}`,
`\auditUnreachableRate{36.5}`, `\auditContradictoryRate{0.0}`,
`\auditProvenanceComplete{100.0}`, `\auditDeadNodes{96}`, `\auditDuplicates{98}`

### EX-27: Timing Stress Suite

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_e27_timing_stress.py` |
| **JSON** | `evidence_pack/ex27_timing_stress/timing_stress.json` |
| **Macros** | `evidence_pack/ex27_timing_stress/macros.tex` |

**Key macros**: `\timingBaselineViolRate{66.04}`,
`\timingDurModelViolRate{65.66}`, `\timingDurModelVerdictChange{2.17}`,
`\timingParallelViolRate{65.1}`, `\timingParallelVerdictChange{2.73}`,
`\timingZeroReasonViolRate{66.03}`, `\timingZeroReasonVerdictChange{0.01}`,
`\clockCrossViolRange{46.44--90.0}`

### EX-28: Bug-Fix Invariance Matrix

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_e28_bugfix_invariance.py` |
| **JSON** | `evidence_pack/ex28_bugfix_invariance/invariance_matrix.json` |
| **Macros** | `evidence_pack/ex28_bugfix_invariance/macros.tex` |

**Key macros**: `\invarianceMaxFADelta{6.36}`, `\invarianceAllStable{6/8}`,
`\invarianceTCCFlips{0}`, `\invarianceAffectedPct{73.5}`

### EX-30: Non-Timing Traps

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_e30_non_timing_trap.py` |
| **JSON** | `evidence_pack/ex30_non_timing/non_timing_traps.json` |
| **Macros** | `evidence_pack/ex30_non_timing/macros.tex` |

**Key macros**: `\nonTimingNaturalCount{354}`, `\nonTimingNaturalPct{2.09}`,
`\nonTimingACBlindPct{72.0}`, `\nonTimingMABBlindPct{52.0}`

### EX-32: Solver Taxonomy

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_ilp_vs_tiered.py` / `exp_exact_dg.py` |
| **Evidence** | `evidence_pack/ex32_solver_taxonomy/` |
| **Macros** | `evidence_pack/ex32_solver_taxonomy/macros.tex` |

**Key macros**: `\solverILPRho{0.920}`, `\solverILPPct{20.4}`,
`\solverVerdictReversalN{0}`, `\solverTieredBetter{8.68}`,
`\solverEqualN{12025}`, `\solverILPBetterN{3449}`

### EX-33: Benchmark Survey

| Item | Path |
|------|------|
| **Evidence** | `evidence_pack/ex33_benchmark_survey/` |
| **Macros** | `evidence_pack/ex33_benchmark_survey/macros.tex` |

**Key macros**: `\surveyNBenchmarks{12}`, `\surveyNOthers{11}`,
`\surveyNProcessOblivious{8}`, `\surveyNTimingChecked{0}`

### EX-34: Strict Non-Degenerate FA

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_strict_consensus_fa.py` |
| **JSON** | `evidence_pack/ex34_strict_fa/strict_fa.json` |
| **Macros** | `evidence_pack/ex34_strict_fa/macros.tex` |

**Key macros**: `\strictFAThree{6.6}`, `\strictFAThreeCount{1118}`,
`\strictFAFour{6.6}`, `\strictFAFourCount{1118}`,
`\strictFACriticalPct{6.2}`, `\strictFAMedianViols{1}`

### EX-35: Replay Fidelity Audit

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_replay_fidelity_audit.py` |
| **JSON** | `evidence_pack/ex35_fidelity_audit/fidelity_audit.json` |
| **Macros** | `evidence_pack/ex35_fidelity_audit/macros.tex` |

**Key macros**: `\fidelityNTraces{15}`, `\fidelityNFail{14}`,
`\fidelityTCCDetect{14}`, `\fidelityMABDetect{1}`, `\fidelityACDetect{1}`

### EX-37: Scaffold Three-Way (W8 pilot)

| Item | Path |
|------|------|
| **Evidence** | `evidence_pack/ex37_scaffold_three_way/` |
| **Macros** | `evidence_pack/ex37_scaffold_three_way/macros.tex` |

**Key macros**: `\promptScaffoldN{2118}`,
`\promptScaffoldReactFlip{81.0}`, `\promptScaffoldDirectFlip{78.7}`,
`\promptScaffoldReactAOFA{12.8}`, `\promptScaffoldDirectAOFA{16.1}`,
`\promptScaffoldMcNemarP{0.032}`

### EX-39: AMEGA Forward-Direction

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_e39_amega_cross_benchmark.py` |
| **Note** | `evidence_pack/ex39_amega_forward/` referenced in comments but values hardcoded in `auto_numbers.tex` L789-798 |

**Key macros**: `\amegaForwardNModels{3}`,
`\amegaForwardQwenMean{0.029}`, `\amegaForwardGemmaMean{0.003}`,
`\amegaForwardRankAgreement{3/3}`

---

## 4. W-Series & Defense Experiments

### W6: Rank Bootstrap

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/compute_rank_bootstrap.py` (referenced, not on disk) |
| **JSON** | `evidence_pack/analysis/rank_bootstrap.json` |

**Key macros**: `\rankBootstrapB{10000}`, `\rankBootstrapKendallW{0.408}`,
`\rankBootstrapKendallWLo{0.342}`, `\rankBootstrapKendallWHi{0.461}`,
`\rankBootstrapMaxCIWidth{3.0}`, `\rankBootstrapTopOneStable{3/4}`

### W7: Oracle Per-Domain Upper Bound

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/compute_oracle_per_domain.py` (referenced, not on disk) |
| **JSON** | `evidence_pack/analysis/oracle_per_domain.json` |

**Key macros**: `\oracleNDomains{5}`, `\oracleNScenarios{8}`,
`\oracleMeanGap{+11.4}`, `\oracleMaxGap{+38.9}`, `\oracleMinGap{-16.1}`

### W8: Scaffold Independence (4x3 cross-model)

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/exp_w8_scaffold_independence.py` |
| **JSON** | `evidence_pack/ex_w8_crossmodel/w8_results.json` |
| **Macros** | `evidence_pack/ex_w8_crossmodel/macros.tex` |

**Key macros**: `\wEightTotalEpisodes{8,472}`, `\wEightNPerCell{706}`,
`\wEightFriedmanChi{1.0}`, `\wEightFriedmanP{0.80}`, `\wEightKendallW{0.11}`,
`\wEightAggAOFARange{2.0}`, `\wEightComplianceSpread{25.7}`

### W9: Distribution Check / Held-out Ordering

| Item | Path |
|------|------|
| **Scripts** | `compute_distribution_check.py`, `compute_heldout_ordering.py` (referenced, not on disk) |
| **JSONs** | `evidence_pack/analysis/distribution_check.json`, `evidence_pack/analysis/heldout_ordering.json` |

**Key macros**: `\distCheckInsideRate{100.0}`, `\distCheckIqrOverlap{91.7}`,
`\heldoutOrderingMatch{5/5}`, `\heldoutOrderingMeanRho{0.50}`

### E7: Paired Delta (Manual vs Auto)

| Item | Path |
|------|------|
| **Script** | `scripts/experiments/run_paired_delta_analysis.py` |
| **JSON** | `evidence_pack/analysis/paired_delta_analysis.json` |

**Key macros**: `\deltaFAManual{23.9}`, `\deltaFAAuto{53.4}`,
`\deltaFADelta{29.4}`, `\newlyExposedCount{782}`, `\newlyExposedRate{20.7}`

### E8: Cross-Benchmark Portability

**Key macros** (in `auto_numbers.tex` L337-365):
`\crossReplayMABPass{52.9}`, `\crossReplayACFA{42.5}`,
`\crossMABConverted{1786}`, `\crossMABBlindPct{78.0}`,
`\mabNativePassRate{62.8}`, `\mabFalseAcceptRate{48.9}`

### Held-Out Domain

| Item | Path |
|------|------|
| **Runner** | `scripts/experiments/heldout_runner.py` |
| **Analysis** | `scripts/experiments/heldout_analysis.py` |
| **JSON** | `evidence_pack/heldout_v1/heldout_results.json` |
| **Macros** | `evidence_pack/heldout_v1/heldout_macros.tex` (29 macros, NOT \input'd) |
| **AO-FA** | `scripts/experiments/exp_heldout_ao_fa.py` -> `evidence_pack/heldout_ao_fa/` |

**Key macros**: `\heldoutN{1584}`, `\heldoutAllObliviousFA{5.8}`,
`\heldoutCondFA{62.2}`, `\fisherPHeldoutAOFA{<0.001}`

---

## 5. CRES Experiments (Compositional Robustness)

All CRES scripts follow the pattern `scripts/experiments/exp_cres_<N>_*.py`.

| CRES | Script | Evidence Dir | Macros in auto_numbers.tex? |
|------|--------|--------------|----------------------------|
| 1A | `exp_cres_1a_tcc_free.py` | `cres_1a/` | No (standalone) |
| 1C | `exp_cres_1c_catalogue_perturbation.py` | `cres_1c/` | No (standalone) |
| 1D | `exp_cres_1d_feature_classifier.py` | `cres_1d/` | **Yes** (L869-875) + separate `\IfFileExists` input (L57) |
| 1E | `exp_cres_1e_counterfactual.py` | `cres_1e/` | **Yes** (L890-895) |
| 4 | `exp_cres_4_oracle_fair.py` | `cres_4/` | No (standalone) |
| 5 | `exp_cres_5_effect_size.py` | `cres_5/` | **Yes** (L877-882) |
| 5-exp | `exp_cres_5_expansion.py` | `cres_5_expansion/` | No (standalone) |
| 6 | `exp_cres_6_before_analysis.py` | `cres_6/` | No (standalone) |
| 6-exp | `exp_cres_6_expansion.py` | `cres_6_expansion/` | No (standalone) |
| 7 | `exp_cres_7_theorem_partition.py` | `cres_7/` | **Yes** (L884-888) |
| 9 | `exp_cres_9_tost.py` | `cres_9/` | No (standalone) |
| 11 | `exp_cres_11_dashboard.py` | `cres_11/` | No (standalone) |
| 12 | `exp_cres_12_rank_reversal.py` | `cres_12/` | No (standalone) |
| 13 | `exp_cres_13_compute.py` | `cres_13/` | **Yes** (L897-903) |

---

## 6. Causal / X-Series Experiments

| Exp | Script | Evidence Dir | Macros in auto_numbers? |
|-----|--------|--------------|------------------------|
| X1 | `exp_x1_context_swap.py` | `ex_x1_context_swap/` | No |
| X2 | `exp_x2_causal_intervention.py` | `ex_x2_causal_intervention/` | No |
| X9 | `exp_x9_grid_reanalysis.py` | `ex_x9_grid/` | No |
| D1 | `exp_d1_projection_ablation.py` | `ex_d1_projection_ablation/` | Partially (L760-786 in auto_numbers.tex) |

---

## 7. Figure Data Sources

| Figure | Script | Input Data | Output |
|--------|--------|------------|--------|
| Fig 1 | TikZ in `figure1.tex` | None (hand-drawn) | inline |
| Fig 2 | `make_figure2_theorem.py` | None (hand-drawn) | `figure2_theorem.pdf` |
| Fig 3 | `make_figure3_cde.py` | None (hand-drawn) | `figure3.png` |
| Fig 4 | `make_figure4_ranking.py` | `evidence_pack/analysis/rank_bootstrap.json` | `figure4.pdf` |
| Fig 5 | `make_figure5_e1_only.py` | `evidence_pack/exp_orthogonal_perturbation.json` + `exp_before_only_perturbation.json` | `figure5.pdf` |
| Fig 6 | `make_figure6_w8_aofa_heatmap.py` | `evidence_pack/ex_w8_crossmodel/w8_results.json` | `figure6.pdf` |

**Note**: Figure 2's wrapper `figure2.tex` exists but is NOT `\input`'d from
`main_final_v17.tex` or `appendix.tex`. The figure is likely included via a
`\includegraphics` directly in the main tex or was dropped.

---

## 8. Supplementary Macro Files

Six files loaded via `\IfFileExists` in `main_final_v17.tex` (L54-70):

### `evidence_pack/normalizer_ablation/multimodel_macros.tex` (10 macros)

Generator: `scripts/ablations/normalizer_ablation_multimodel.py`

| Macro | Value |
|-------|-------|
| `\normMultiNModels` | 7 |
| `\normMultiNEpisodes` | 14826 |
| `\normMultiMeanDeltaCovPP` | +3.9 |
| `\normMultiMeanDeltaCompPP` | +3.7 |
| `\normMultiRankingRho` | 1.000 |

### `evidence_pack/cres_1d/cres_1d_macros.tex` (15 macros)

Generator: `scripts/experiments/exp_cres_1d_feature_classifier.py`

| Macro | Value |
|-------|-------|
| `\cresOneDNEpisodes` | 14826 |
| `\cresOneDAUCFull` | 0.995 |
| `\cresOneDAUCASC` | 0.947 |
| `\cresOneDDeltaAUC` | +0.048 |
| `\cresOneDTopFeature` | n\_med\_actions |
| `\cresOneDCovFreeAUC` | 0.994 |

### `evidence_pack/paper_footnotes.tex` (3 footnotes)

Hand-authored rebuttal-ready footnotes:
- `\footnoteEquivVsFriedman` -- TOST vs Friedman clarification
- `\footnoteTooluseDegenerate` -- qwen35b-tooluse outlier explanation
- `\footnoteHeldoutAOFA` -- elevated held-out AO-FA rate note

### `evidence_pack/theorem_v2/bayes_error_macros.tex` (45 macros)

Generator: `scripts/audit/compute_bayes_error.py`

| Macro family | Count | Example |
|-------------|-------|---------|
| Pooled Bayes error per projection | 4 | `\bayesErrAset{0.024}` |
| 95% bootstrap CIs | 4 | `\bayesErrAsetCI{[0.021, 0.027]}` |
| Mixed-fibre mass | 4 | `\bayesErrMixedFracAset{9.8}` |
| Per-coordinate (4 proj x 5 viol types) | 20 | `\bayesErrCoordAsetOmit{...}` |
| Per-coordinate CIs | 12 | `\bayesErrCoordAsetOmitCI{...}` |
| Sample size | 1 | `\bayesErrNEpisodes{14826}` |

### `evidence_pack/audit/audit_macros.tex` (41 macros)

Generator: `scripts/audit/build_index.py` + `evaluator_audit.py`

| Macro family | Count | Example |
|-------------|-------|---------|
| Per-evaluator pi-class | 6 | `\auditPiDxEM{...}` |
| Per-evaluator BSR | 12 | `\auditBSRACProxy{...}`, `\auditBSRPctACProxy{...}` |
| Per-evaluator Bayes error | 6 | `\auditBayesDxEM{...}` |
| Per-evaluator FA count | 6 | `\auditFADxEM{...}` |
| Detection loss | 5 | `\auditDetLossACProxy{...}` |
| Corpus stats | 4 | `\auditNEpisodes{14826}`, `\auditNSeparatingPairs{20}` |

### `evidence_pack/audit/c6_selection_macros.tex` (8 macros)

Generator: Audit pipeline C6 step

| Macro | Value |
|-------|-------|
| `\cSixNPairs` | 15 |
| `\cSixAuditTau` | 0.0000 |
| `\cSixSameClassMean` | 0.4729 |
| `\cSixCrossClassMean` | 0.1915 |
| `\cSixSeparation` | true |

---

## 9. System-Level Macros

These are episode-independent constants in `auto_numbers.tex` (L212-280),
set by `exp_f_evidence_pack_v5.py` or manually verified:

| Category | Macros |
|----------|--------|
| Corpus size | `\numTotalScenarios{706}`, `\numManualScenarios{105}`, `\numAutoScenarios{601}` |
| Graph library | `\numGraphsTotal{25}`, `\numGraphsMain{20}`, `\numGraphsHeldout{5}` |
| Constraint counts | `\numMust{557}`, `\numForbidden{212}`, `\numWithin{215}`, `\numBefore{65}`, `\numTotalConstraints{1049}` |
| Run configuration | `\numModels{8}`, `\numRuns{3}`, `\numEpisodes{16,944}`, `\numEvaluators{4}` |
| Derivation | `\overgenPercent{81.6}`, `\expansionRatio{8.0}` |

---

## 10. Macro Routing Summary

Macros reach the paper via two paths:

### Path A: Direct in `auto_numbers.tex`

Written by `extract_auto_numbers.py` and `exp_f_evidence_pack_v5.py`.
Covers E1-E5, system numbers, EXP-A through EXP-E, and manually curated
values from EX-23/24/25/27/28/30/32/33/34/35/37/39 and CRES-1D/1E/5/7/13.

### Path B: Separate `\IfFileExists` macro files

Loaded conditionally at paper compile time. Each file is generated by
its own script and NOT aggregated into `auto_numbers.tex`:

| File | Generator | Macros |
|------|-----------|--------|
| `normalizer_ablation/multimodel_macros.tex` | `normalizer_ablation_multimodel.py` | 10 |
| `cres_1d/cres_1d_macros.tex` | `exp_cres_1d_feature_classifier.py` | 15 |
| `paper_footnotes.tex` | Hand-authored | 3 |
| `theorem_v2/bayes_error_macros.tex` | `compute_bayes_error.py` | 45 |
| `audit/audit_macros.tex` | `build_index.py` | 41 |
| `audit/c6_selection_macros.tex` | Audit C6 pipeline | 8 |

### Orphaned macro files (NOT loaded by v17)

| File | Notes |
|------|-------|
| `paper/auto_numbers_v2.tex` | Legacy, used by v14/v16 |
| `paper/auto_numbers_defense.tex` | Not `\input`'d |
| `paper/auto_numbers_amega.tex` | Not `\input`'d |
| `paper/auto_numbers_resample.tex` | Not `\input`'d |
| `evidence_pack/heldout_v1/heldout_macros.tex` | 29 macros, not `\input`'d |

### Per-experiment standalone macros (evidence_pack only)

These `macros.tex` files exist in their evidence directories but are NOT
loaded by any paper `.tex` file. Their values were manually copied into
`auto_numbers.tex` where needed:

`ex23_artifact_ablation/`, `ex24_fa_severity/`, `ex25_engine_audit/`,
`ex26_scorer_fidelity/`, `ex27_timing_stress/`, `ex28_bugfix_invariance/`,
`ex29_heldout_domain/`, `ex30_non_timing/`, `ex32_solver_taxonomy/`,
`ex33_benchmark_survey/`, `ex34_strict_fa/`, `ex35_fidelity_audit/`,
`ex36_temperature_eta/`, `ex37_scaffold_three_way/`, `ex38_variable_duration/`,
`ex_d1_projection_ablation/`, `ex_w8_crossmodel/`

---

## 11. Missing Generator Scripts

The following scripts are referenced in `auto_numbers.tex` comments but
do **not exist on disk**. Their output JSONs exist (values were computed
in earlier sessions and committed):

| Referenced Script | Output JSON | Status |
|-------------------|-------------|--------|
| `compute_distribution_check.py` | `evidence_pack/analysis/distribution_check.json` | JSON exists, script missing |
| `compute_heldout_ordering.py` | `evidence_pack/analysis/heldout_ordering.json` | JSON exists, script missing |
| `compute_rank_bootstrap.py` | `evidence_pack/analysis/rank_bootstrap.json` | JSON exists, script missing |
| `compute_oracle_per_domain.py` | `evidence_pack/analysis/oracle_per_domain.json` | JSON exists, script missing |

These macros are hardcoded in `auto_numbers.tex` and reproducible from
the stored JSON data.

---

## 12. Full Pipeline Regeneration Order

To regenerate all paper numbers from raw episode data:

```
1. Raw episodes        results/full_706_v5/{model}/*.json
                        |
2. Episode analysis     scripts/experiments/full_690_runner.py
                        |
3. E1-E5 experiments    exp_e1_verdict_flip.py
                        exp_e2_bsr.py
                        (exp_e3 from extract_auto_numbers.py)
                        exp_e4_operating_point.py
                        exp_e5_evaluator_expansion.py
                        |
4. Macro extraction     extract_auto_numbers.py  -->  auto_numbers.tex
                        exp_f_evidence_pack_v5.py -->  auto_numbers.tex (system numbers)
                        |
5. Supplementary        exp_e27..exp_e39, exp_cres_*, exp_d1_*, exp_w8_*
   experiments          |
                        v
                   evidence_pack/ex*/macros.tex  (standalone)
                        |
                   Manual curation into auto_numbers.tex (selected values)
                        |
6. Audit pipeline       scripts/audit/build_index.py
                        scripts/audit/compute_bayes_error.py
                        |
                        v
                   evidence_pack/audit/audit_macros.tex
                   evidence_pack/theorem_v2/bayes_error_macros.tex
                        |
7. Figures              make_figure4_ranking.py   <-- rank_bootstrap.json
                        make_figure5_e1_only.py   <-- exp_orthogonal_perturbation.json
                        make_figure6_w8_aofa_heatmap.py <-- w8_results.json
                        |
8. Paper compile        pdflatex main_final_v17.tex
```
