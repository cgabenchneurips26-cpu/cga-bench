# v6 Baseline Freeze — Reference State for SGSC v7 Transition

**Date**: 2026-04-30
**Purpose**: Canonical reference for all v6 paper numbers before SGSC v7 pipeline changes alter the episode corpus or macro values.

---

## Git Reference

| Field | Value |
|---|---|
| Tag | `paper-macro-recompute-20260430` |
| Commit hash | `6b3c1e5f8f44849fdd28d80b8d4e5a4795496a29` |
| Short hash | `6b3c1e5f` |
| Commit date | 2026-04-30 08:19:12 UTC |
| Commit message | `fix(paper+scripts): P-series close-out — schema-drift guard + duplicate-writer warning + Tier-B v2 roadmap + submission checklist` |
| Branch | `eval_science` |

---

## Paper Identity

**Title**: CGA-Bench: When Do Clinical AI Agents Actually Follow Guidelines?
Trace-Level Conformance Auditing Exposes Blind Spots in Medical Benchmarks
**Venue**: NeurIPS 2026 Evaluations & Datasets Track
**Active version**: `paper/main_final_v18.tex`
**Macro source**: `paper/auto_numbers.tex` (sole `\input` target at line 84 of v18)

---

## Canonical v6 Numbers

### Episode Corpus

| Dimension | Value |
|---|---|
| Scenarios (total) | 706 |
| Models | 8 (canonical Phase A/B corpus; 9 with Llama-4-Scout Phase A only) |
| Runs per model | 3 |
| Episodes (8-model Phase B) | 16,944 |
| Episodes (9-model Phase A headline) | 19,062 |
| Episodes (Phase B full, 76,464) | `\vSixFullN` = 76,464 |

### Model List (8-model canonical)

1. `oss120b` (GPT-OSS-120B)
2. `qwen35b` (Qwen3.5-35B)
3. `qwen27b` (Qwen3.5-27B)
4. `qwen4b` (Qwen4B)
5. `qwen397b` (Qwen3.5-397B)
6. `gemma31b` (Gemma-4-31B-IT)
7. `nemotron30b` (Nemotron3-Nano-30B)
8. `deepseek_r1_7b` (DeepSeek-R1-7B)

Phase A 9th model (not in Phase B): `llama4scout` (Llama-4-Scout)

### Held-Out Composition (5 guidelines, Phase B)

| Guideline | Graph file | Episodes (8 models × ~199 ep) |
|---|---|---|
| AABB Transfusion 2024 | `aabb_transfusion.yaml` | 288 ep |
| ABA Burn Resuscitation 2018 | `aba_burn_resuscitation.yaml` | 480 ep |
| ACOG Obstetric Hemorrhage 2017 | `acog_obstetric_hemorrhage.yaml` | 216 ep |
| APA Agitation Management 2024 | `apa_agitation_management.yaml` | 360 ep |
| PALS Pediatric Emergency 2020 | `pals_pediatric_emergency.yaml` | 240 ep |
| **Total** | | **1,584 episodes** |

Note: `\heldoutN` in auto_numbers.tex shows `1584` (Phase B 8-model count); the `\providecommand{\heldoutN}{1387}` override (line 1284) reflects 7-model heldout for the heldout FA analysis sub-set.

---

## Complete Macro Table

All macros extracted from `paper/auto_numbers.tex` at the freeze commit, grouped by category.

### Category 1: Episode / Scenario Counts

| Macro | Value | Notes |
|---|---|---|
| `\numManualScenarios` | 105 | expert-authored (107 YAML minus 2 e2e-test-only) |
| `\numAutoScenarios` | 601 | auto-generated (PatientGenerator) |
| `\numTotalScenarios` | 706 | |
| `\numGraphsMain` / `\numMainGraphs` | 20 | core CPG graphs |
| `\numGraphsHeldout` / `\numHoldoutGraphs` | 5 | held-out CPG graphs |
| `\numGraphsTotal` | 25 | total CPG graphs |
| `\numDomains` | 25 | |
| `\numNodes` | 167 | |
| `\numModels` | 9 | Phase A headline (9-model incl. Llama-4-Scout) |
| `\numRuns` | 3 | |
| `\numEpisodes` | 19,062 | Phase A 9-model headline |
| `\numEvaluators` | 4 | non-degenerate evaluators in main analysis |
| `\numEvaluatorsAll` | 6 | including DxEM and ACov |
| `\numEvaluatorsExpanded` | 12 | E5 expanded set |
| `\numComboCandidates` | 1,237 | |
| `\heldoutN` | 1,584 / 1,387 | 1584 = Phase B 8-model; 1387 = 7-model heldout FA subset |
| `\numEpisodes` (Phase B) | 76,464 | `\vSixFullN` |
| `\phaseBEpisodes` | *(referenced, not defined in this file directly)* | Phase B 8-model |
| `\wEightTotalEpisodes` | 8,472 | W8: 12 cells × 706 |
| `\wEightNPerCell` | 706 | W8 episodes per cell |
| `\numScaffolds` | 4 | react, direct, checklist, tooluse |
| `\cresOneDNEpisodes` / `\cresThirteenTotalEpisodes` | 14,826 | CRES subset |

### Category 2: Constraint Counts

| Macro | Value | Notes |
|---|---|---|
| `\numForbidden` | 212 | CPG FORBIDDEN constraints |
| `\numMust` | 557 | CPG MUST constraints |
| `\numShould` | 0 | |
| `\numBefore` | 65 | CPG BEFORE constraints |
| `\numWithin` | 215 | CPG WITHIN (deadline) constraints |
| `\numShouldWithin` | 0 | |
| `\numHardConstraints` | 1,049 | |
| `\numSoftConstraints` | 0 | |
| `\numTotalConstraints` | 1,049 | |
| `\numConditionalRules` | 312 | |
| `\numExtraForbidden` | 927 | engine-generated extras |
| `\numExtraRequired` | 3,066 | engine-generated extras |
| `\numExtraBefore` | 0 | |
| `\numExtraWithin` | 888 | |
| `\numExtraAll` | 4,881 | |
| `\auditTotalRules` | 1,049 | EX-25 engine audit |
| `\auditUniqueActions` | 611 | distinct action IDs across 25 graphs |

### Category 3: Core CGA / Compliance Metrics

| Macro | Value | Notes |
|---|---|---|
| `\passrateCGABench` / `\passRateCGABenchhard` | 44.6 | CGA-Bench pass rate (%) |
| `\passrateDxEM` | 100.0 | DxEM pass rate (%) |
| `\passtrateACProxy` | 76.9 | AC-Proxy pass rate (%) |
| `\passrateCTwo` | 27.8 | C2 pass rate (%) |
| `\passtrateMABProxy` | 52.7 | MAB-Proxy pass rate (%) |
| `\heldoutCompliance` | 0.580 | held-out mean compliance |
| `\indomainCompliance` | 0.511 | in-domain (Phase B) mean compliance |
| `\heldoutFARate` | 18.82 | held-out FA rate (%) |
| `\indomainFARate` | 5.38 | in-domain Phase B FA rate (%) |
| `\heldoutFlipRate` | 98.34 | held-out verdict-flip rate (%) |
| `\heldoutFisherP` | <0.001 | heldout vs in-domain FA comparison |
| `\heldoutOddsRatio` | 4.07 | |

### Category 4: Per-Model Statistics

| Macro | Value | Notes |
|---|---|---|
| `\faDeepSeek` | 0.56 | DeepSeek-R1-7B consensus FA rate (%) |
| `\faQwenFour` | 6.11 | Qwen4B consensus FA rate (%) |
| `\faQwenTwentySeven` | 4.48 | Qwen3.5-27B consensus FA rate (%) |
| `\faQwenThirtyFive` | 5.48 | Qwen3.5-35B consensus FA rate (%) |
| `\faNemo` | 1.80 | Nemotron-30B consensus FA rate (%) |
| `\faGemma` | 3.64 | Gemma-4-31B consensus FA rate (%) |
| `\faOSS` | 3.40 | OSS-120B consensus FA rate (%) |
| `\faQwenThreeNineSeven` | 5.64 | Qwen3.5-397B consensus FA rate (%) |
| `\consensusFAModelRange` | 0.56–6.11 | Phase B range (deepseek lowest, qwen4b highest) |
| `\bsrDSPct` | 80.4 | DeepSeek BSR (%) |
| `\bsrQfourPct` | 65.5 | Qwen4B BSR (%) |
| `\bsrQtwentysevenPct` | 55.3 | Qwen3.5-27B BSR (%) |
| `\bsrQthirtyfivePct` | 58.7 | Qwen3.5-35B BSR (%) |
| `\bsrNemoPct` | 64.2 | Nemotron BSR (%) |
| `\bsrGemmaPct` | 47.8 | Gemma BSR (%) |
| `\bsrOSSPct` | 61.2 | OSS-120B BSR (%) |
| `\bsrQthreeninePct` | 53.8 | Qwen3.5-397B BSR (%) |
| `\bsrAllPct` | 60.9 | all-model aggregate BSR (%) |
| `\hlAllDelta` | +8.1 | mean MAB-TCC delta across all models |
| `\hlNumModelsMABgtTCC` | 8 | models where MAB pass > TCC pass |
| `\llamaScoutCGA` | 42.4 | Llama-4-Scout TCC pass rate (%) |
| `\llamaScoutACFA` | 76.8 | Llama-4-Scout AC pass rate (%) |

### Category 5: Safety Metrics (strictFA, safetyCore)

| Macro | Value | Notes |
|---|---|---|
| `\strictFAThree` | 5.90 | Phase A 9m ASC∩PAF∩CwT FA rate (%) |
| `\strictFAThreeCount` | 1,124 | Phase A 9m strict-3-way FA count |
| `\strictFAFour` | 3.89 | Phase B 8m TOM∩ASC∩PAF∩CwT FA rate (%) |
| `\strictFAFourCount` | 2,974 | Phase B 8m strict-4-way FA count |
| `\strictFACriticalPct` | 1.96 | Phase A 9m: 22/1124 v4_crit (%) |
| `\strictFACritical` | 22 | Phase A 9m v4_crit count |
| `\strictFACritFracTotal` | 0.12 | strict FA crit as fraction of total episodes |
| `\strictFAThreePre` | 6.6 | alias for legacy Phase A 8m value |
| `\strictFAThreeFixed` | 6.6 | CDE-coupled (qualitatively unchanged) |
| `\safetyCorePctOfStrictFA` | 12.8 | safety-core (≥1 FORBIDDEN/BEFORE) as % of strict-3-FA |
| `\safetyCoreWilsonLo` | 11.0 | Wilson 95% CI lower |
| `\safetyCoreWilsonHi` | 14.9 | Wilson 95% CI upper |
| `\consensusFATotal` | 2,106 | Phase A 9m TOM∩ASC∩CwT FA count |
| `\consensusFARate` | 11.05 | Phase A 9m consensus FA rate (%) |
| `\consensusFACritical` | 139 | Phase A 9m v4_crit count |
| `\consensusFACriticalPct` | 6.60 | 139/2106 Phase A 9m (%) |
| `\consensusFACriticalPctPhaseB` | 3.86 | Phase B 8m (170/4405) |
| `\strictFACriticalPctPhaseB` | 1.88 | Phase B 8m strict-3-way v4_crit (%) |
| `\nonTimingNaturalCount` | 443 | FORBIDDEN|BEFORE TCC-fail, no WITHIN — Phase A 9m |
| `\nonTimingNaturalPct` | 2.32 | 443/19062 Phase A 9m (%) |
| `\nonTimingACBlindPct` | 69.1 | 306/443 Phase A 9m (%) |
| `\vSixFullConsensusFACritical` | 300 | Phase B original CwT |
| `\vSixFullConsensusFACriticalPct` | 6.81 | Phase B (%) |
| `\vSixFullStrictFACritical` | 123 | Phase B strict 3-way FA |
| `\vSixFullStrictFACriticalPct` | 4.14 | Phase B (%) |

### Category 6: Conflict / CDE Metrics

| Macro | Value | Notes |
|---|---|---|
| `\conflictPatternsN` | 11 | conflict patterns audited across 25 CPGs |
| `\conflictGraphsN` | 9 | CPGs with at least one conflict pattern |
| `\cdeNormIntersectionN` | 10 | CDE-and-normalizer intersection |
| `\tierAN` | 0 | engine-fix auto-resolved patterns |
| `\tierBN` | 9 | static mandatory + conditional FORBIDDEN (patch candidates) |
| `\tierCN` | 2 | genuine OR_REQUIRED semantics (v2.0 deferred) |
| `\conflictViolationN` | 11 | CONFLICT-type violations in 11 demo episodes |
| `\scnTwelveImpactN` | 7 | patterns with differing CDE-coupled scoring |
| `\meanCgaPre` | 52.9 | mean compliance, legacy mode (%, n=11 demo) |
| `\meanCgaPost` | 42.3 | mean compliance, CDE-coupled mode (%) |
| `\meanCgaDelta` | -10.7 | mean CGA delta (pp) |
| `\cdeAuditCpgsTotal` | 25 | CPGs scanned |
| `\conflictTouchEpisodes` | 3,584 | episodes with conflict-prone agent action |
| `\conflictTouchScenarios` | 264 | unique scenarios touched |
| `\conflictTouchPct` | 21.2 | % of 16,944 episodes (substring upper bound) |
| `\conflictTouchStrictPct` | 20.2 | exact-match lower bound (%) |
| `\conflictTouchActionsN` | 11 | conflict-prone actions tracked |

### Category 7: Statistical Tests (Kendall W, Friedman, Wilson CI)

| Macro | Value | Notes |
|---|---|---|
| `\friedmanChi` | 31.3 | Phase B Friedman chi-squared |
| `\friedmanP` | <0.001 | Phase B (p=2.7e-6) |
| `\kendallW` | 0.219 | Phase B Kendall W |
| `\reversalRate` | 96.4 | Phase B (27/28 model pairs reverse) (%) |
| `\topOneFlip` | yes | 5 distinct winners across 5 evaluators |
| `\rankBootstrapB` | 10,000 | bootstrap iterations |
| `\rankBootstrapKendallW` | 0.408 | point-estimate Kendall W (Phase A 8m) |
| `\rankBootstrapKendallWLo` | 0.342 | 95% CI lower |
| `\rankBootstrapKendallWHi` | 0.461 | 95% CI upper |
| `\rankBootstrapMaxCIWidth` | 3.0 | max rank 95%-CI width (positions) |
| `\rankBootstrapTopOneStable` | 3/4 | evaluators with ≥95% stable top-1 |
| `\fleissKappa` | 0.145 | EXP-D (slight agreement, 6 evaluators, 180 episodes) |
| `\fleissKappaMatched` | 0.091 | matched operating point |
| `\vSixFullFleissKappa` | 0.038 | Phase B full (76,464 ep) |
| `\etaEvaluator` | 0.190 | Phase B η² evaluator effect |
| `\etaRun` | 0.088 | Phase B η² run effect |
| `\etaRatio` | 2.15 | Phase B eval/run ratio |
| `\vSixFullEtaSq` | 0.190 | Phase B η² with CI 0.187–0.192 |
| `\vSixFullCohenF` | 0.234 | Phase B Cohen f |
| `\vSixFullCliffDelta` | -0.131 | Phase B Cliff's δ |
| `\wEightFriedmanChi` | 1.0 | W8 scaffold Friedman chi |
| `\wEightFriedmanP` | 0.80 | W8 scaffold Friedman p |
| `\wEightKendallW` | 0.11 | W8 scaffold Kendall W |
| `\wilcoxonP` | <0.001 | Wilcoxon p |
| `\mcnemarTimestampP` | <0.001 | McNemar p for timestamp removal |
| `\safetyCorePctOfStrictFA` | 12.8 | Wilson CI: 11.0–14.9% |

### Category 8: BSR (Blind-Spot Rate) Metrics

| Macro | Value | Notes |
|---|---|---|
| `\bsrCGA` | 0.0 | CGA-Bench BSR (%) |
| `\bsrAC` | 46.8 | AC-Proxy BSR (%) |
| `\bsrMAB` | 34.3 | MAB-Proxy BSR (%) |
| `\bsrDxEM` | 55.4 | DxEM BSR (%) |
| `\bsrCTwo` | 11.9 | C2 BSR (%) |
| `\bsrCondAC` | 60.9 | Phase B P(TCC=fail | AC=pass) (%) |
| `\bsrCondMAB` | 65.1 | Phase B P(TCC=fail | MAB=pass) (%) |
| `\bsrCondCTwo` | 42.7 | Phase B P(TCC=fail | C2=pass) (%) |
| `\bsrCondDxEM` | 55.4 | Phase B P(TCC=fail | DxEM=pass) (%) |
| `\bsrMaxOblivious` | 55.4 | max BSR among oblivious evaluators |
| `\bsrMinOblivious` | 11.9 | min BSR among oblivious evaluators |

### Category 9: False-Accept (FA) Metrics

| Macro | Value | Notes |
|---|---|---|
| `\faAC` | 46.8 | AC-Proxy FA rate (%) |
| `\faCGA` | 0.0 | CGA-Bench FA rate (%) |
| `\faMAB` | 34.3 | MAB-Proxy FA rate (%) |
| `\faCTwo` | 11.9 | C2 FA rate (%) |
| `\faAllOblivious` | 11.0 | all-oblivious FA rate (%) |
| `\faAllObliviousCount` | 2,106 | all-oblivious FA count |
| `\faNAC` | 8,919 | AC-Proxy FA count |
| `\verdictFlipCount` | 16,331 | E1 flip count |
| `\verdictFlipRate` | 92.0 | E1 flip rate (%) |
| `\verdictFlipRateMatched` | 81.5 | E4 matched operating point flip rate (%) |
| `\heldoutAllObliviousFA` | 5.8 | held-out all-oblivious FA (%) |
| `\heldoutAllObliviousCount` | 92 | |
| `\heldoutCondFA` | 62.2 | held-out conditional FA (%) |
| `\indomainAllObliviousFA` | 12.2 | in-domain all-oblivious FA (%) |

### Category 10: Graph / Traceability Metrics

| Macro | Value | Notes |
|---|---|---|
| `\graphValidatorChecksN` | 6 | structural checks per graph |
| `\graphValidatorTotalN` | 150 | 6 × 25 graphs |
| `\graphValidatorGraphsN` | 25 | graphs validated |
| `\graphValidatorErrorsN` | 0 | errors found |
| `\graphValidatorWarningsN` | 0 | warnings found |
| `\cdeSanityAllGraphsN` | 25 | CDE derive() sanity-checked |
| `\traceGraphsN` | 97 | total graphs audited (25 core + 72 auto) |
| `\traceScenariosN` | 708 | total scenarios audited |
| `\traceCorpusCoverage` | 39/97 | graphs with matching corpus file |
| `\traceCorpusCoverageRate` | 40.2% | |
| `\traceQuoteCoverageRate` | 77.2% | quote verified or grounded rate |
| `\traceExactMatchRate` | 65.6% | exact substring match rate |
| `\traceLinkageRate` | 0.0% | nodes with source_recommendation_ids (new field) |
| `\traceReachabilityRate` | 55.2% | scenarios where expected_actions all reachable |
| `\traceProvenanceRate` | 100.0% | nodes with all required provenance fields |
| `\auditNGraphs` | 25 | EX-25 graphs audited |
| `\auditUnreachableRate` | 36.5 | EX-25 unreachable node rate (%) |
| `\auditContradictoryRate` | 0.0 | EX-25 contradictory rule rate (%) |
| `\auditProvenanceComplete` | 100.0 | EX-25 provenance complete (%) |
| `\auditDeadRate` | 57.5 | 96/167 dead-end nodes (%) |
| `\auditDeadNodes` | 96 | dead-end nodes count |
| `\auditUnreachableNodes` | 61 | unreachable nodes count |
| `\auditDuplicates` | 98 | duplicate constraint instances |
| `\auditDuplicateRate` | 9.3 | 98/1049 (%) |

### Category 11: Ablation / Instrumentation

| Macro | Value | Notes |
|---|---|---|
| `\ablationOvergenPct` | 81.57 | EXP-B over-generation (%) |
| `\ablationFPRate` | 33.87 | EXP-B false positive rate (%) |
| `\ablationFNRate` | 35.16 | EXP-B false negative rate (%) |
| `\enginePrecision` | 0.217 | EXP-B |
| `\engineRecall` | 0.481 | EXP-B |
| `\overgenPercent` | 81.6 | derivation engine over-generation |
| `\expansionRatio` | 8.0 | engine vs manual constraint ratio |
| `\avgManualConstraints` | 6.6 | avg manual constraints per scenario |
| `\avgEngineConstraints` | 53.1 | avg engine constraints per scenario |
| `\instrFullHardRate` | 50.5 | full instrumentation hard rate (%) |
| `\instrNoTimeLoss` | 80.9 | timestamps-removed hard loss (%) |
| `\instrNoStateRetain` | 96.3 | no-state retain rate (%) |
| `\instrNoOrderRetain` | 99.5 | no-ordering retain rate (%) |
| `\ablationPassFull` | 49.5 | full ablation pass rate (%) |
| `\ablationPassActionOnly` | 90.4 | action-only pass rate (%) |
| `\ablationGapActionFull` | 40.9 | gap between action-only and full (pp) |

### Category 12: Constraint Precision (Engine vs Manual)

| Macro | Value | Notes |
|---|---|---|
| `\precForbidden` | 66.00% | 165/250 engine-FORBIDDEN ⊆ manual |
| `\precRequired` | 81.18% | 617/760 engine-REQUIRED ⊆ manual |
| `\precAll` | 77.43% | 782/1010 engine ⊆ manual aggregate |
| `\normalizerRawActionsN` | 1,458 | unique raw action IDs across 25 graphs |
| `\normalizerCanonicalN` | 1,366 | unique canonical forms |
| `\normalizerUnmappedN` | 1,279 | actions normalizing to self |
| `\normalizerUnmappedPct` | 87.7 | self-normalising rate (%) |
| `\normalizerMultiCanonicalN` | 59 | multi-ID groups sharing one canonical |
| `\normalizerBlindspotN` | 18 | canonical forms in both mandatory + forbidden |

### Category 13: Tier Classifications

| Macro | Value | Notes |
|---|---|---|
| `\tierAN` | 0 | CDE Tier A: engine-fix auto-resolved |
| `\tierBN` | 9 | CDE Tier B: graph patch candidates |
| `\tierCN` | 2 | CDE Tier C: OR_REQUIRED semantics deferred |
| `\tierSGraphsPassed` | 31 | Tier-S CPGs passed validation |
| `\tierSGraphsTotal` | 31 | |
| `\tierSScenariosPassed` | 2,480 | Tier-S auto scenarios passed |
| `\tierSScenariosTotal` | 2,480 | |
| `\tierSAggEpisodes` | 7,654 | Tier-S aggregate episodes |
| `\tierSExtraCPGs` | 17 | extra CPGs in Tier-S |
| `\tierSExtraEpisodes` | 11,235 | extra episodes from Tier-S |
| `\tierSExtraScenarios` | 535 | extra scenarios from Tier-S |
| `\tierSMaxMetricShift` | 3 | max metric shift (pp) |

### Category 14: W8 / Scaffold Ablation

| Macro | Value | Notes |
|---|---|---|
| `\wEightAggReactAOFA` | 19.5 | ReAct all-oblivious FA (%) |
| `\wEightAggDirectAOFA` | 17.5 | Direct all-oblivious FA (%) |
| `\wEightAggChecklistAOFA` | 19.0 | Checklist all-oblivious FA (%) |
| `\wEightAggToolUseAOFA` | 19.1 | ToolUse all-oblivious FA (%) |
| `\wEightAggAOFARange` | 2.0 | pp spread across scaffolds |
| `\wEightComplianceMin` | 0.539 | gemma31b direct |
| `\wEightComplianceMax` | 0.796 | oss120b tooluse |
| `\wEightComplianceSpread` | 25.7 | pp (max−min)×100 |

### Category 15: EXP-B / Derivation Ablation

| Macro | Value | Notes |
|---|---|---|
| `\constraintDensityP` | 0.004 | EXP-A constraint density Bonferroni p |
| `\difficultyCohenD` | -0.3744 | EXP-E |
| `\difficultyKSP` | 0.000186 | EXP-E |
| `\looSpearman` | 0.96 | EXP-E LOO Spearman |
| `\cochransQP` | <0.001 | EXP-D Cochran's Q |
| `\numRankReversals` | 231 | EXP-D total rank reversals across evaluator pairs |
| `\bootstrapARI` | 0.991 | E5 bootstrap ARI mean |
| `\cophenetic` | 0.746 | E5 cophenetic correlation |
| `\numClusters` | 3 | E5 optimal clusters |
| `\silhouetteScore` | 0.28 | E5 silhouette at k=2 |
| `\clusterPreservedPct` | 100.0 | cluster preserved (%) |
| `\solverILPRho` | 0.920 | ILP solver Spearman rho |
| `\solverTieredBetter` | 8.68 | tiered vs ILP better (%) |
| `\solverRankReversals` | 0 | solver rank reversals |

---

## v7 Transition Instructions

### Macros that Get NEW v7 Values (headline claims in main text)

These macros appear in §4 and §5 of the paper and will update when the SGSC v7 pipeline generates new episodes. **Do not cite the v6 values in v7 paper prose without renaming the macros.**

| Macro | Current v6 Value | Used In |
|---|---|---|
| `\numTotalScenarios` | 706 | Abstract, §4 header |
| `\numEpisodes` | 19,062 | §4, Table 1 |
| `\numModels` | 9 | §4 |
| `\passrateCGABench` | 44.6 | §5 headline |
| `\verdictFlipRate` | 92.0 | §5 headline |
| `\faAllOblivious` | 11.0 | §5 |
| `\consensusFARate` | 11.05 | §5 |
| `\strictFAThree` | 5.90 | §5 |
| `\friedmanChi` / `\friedmanP` | 31.3 / <0.001 | §5 ranking |
| `\kendallW` | 0.219 | §5 ranking |
| `\bsrCondAC` / `\bsrCondMAB` | 60.9 / 65.1 | §5 BSR |
| `\etaEvaluator` / `\etaRun` | 0.190 / 0.088 | §5 variance decomp |
| `\heldoutFARate` | 18.82 | §5 generalizability |
| `\heldoutFisherP` | <0.001 | §5 generalizability |
| `\conflictTouchPct` | 21.2 | App. Z |
| Per-model `\fa*` macros | 0.56–6.11 range | App. per-model tables |

### Macros that STAY as v6 (appendix baseline references)

These macros document the v6 evaluation design and do not change with new episodes. They should remain as-is and be referenced as "v6 baseline" in v7 transition notes.

| Macro | Value | Reason |
|---|---|---|
| `\numGraphsTotal` / `\numMainGraphs` / `\numHoldoutGraphs` | 25 / 20 / 5 | CPG library unchanged unless expanded |
| `\numHardConstraints` | 1,049 | CPG constraint count unchanged |
| `\numForbidden` / `\numMust` / `\numBefore` / `\numWithin` | 212/557/65/215 | Same graphs |
| `\graphValidatorChecksN` / `\graphValidatorErrorsN` | 6 / 0 | Graph validator results |
| `\auditProvenanceComplete` | 100.0 | Provenance standard |
| `\oracleCodeCrossImports` | 0 | Oracle/engine separation verified |
| `\leakageScanDirsPassed` | 4 | Canary leakage results |
| `\normalizerBlindspotN` | 18 | Known normalizer blindspots |
| `\conflictPatternsN` / `\conflictGraphsN` | 11 / 9 | CDE conflict audit results |
| `\tierAN` / `\tierBN` / `\tierCN` | 0/9/2 | CDE tier classification |
| `\solverILPRho` / `\solverRankReversals` | 0.920 / 0 | Solver taxonomy |
| `\mimicProtocolHash` | 8e3875401bb1 | Pre-registration hash (immutable) |
| `\mimicProtocolDate` | 2026-04-18 | Pre-registration date (immutable) |
| CRES-13 compute footprint | 14.04 A100-hours, 1.68 kg CO₂ | Carbon accounting for v6 only |

### New v7-Only Macros to Create

When SGSC v7 pipeline runs are complete, define these new macros (do NOT overwrite the v6 macros; use distinct names):

```latex
% v7 corpus
\newcommand{\vSevenNumScenarios}{???}       % v7 total scenario count
\newcommand{\vSevenNumEpisodes}{???}        % v7 total episodes
\newcommand{\vSevenNumModels}{???}          % models in v7 run
\newcommand{\vSevenPassrateCGA}{???}        % CGA-Bench pass rate
\newcommand{\vSevenVerdictFlipRate}{???}    % verdict flip rate
\newcommand{\vSevenStrictFAThree}{???}      % strict 3-way FA
\newcommand{\vSevenConsensusFA}{???}        % consensus FA rate
\newcommand{\vSevenKendallW}{???}           % Kendall W
\newcommand{\vSevenFriedmanChi}{???}        % Friedman chi
\newcommand{\vSevenConflictTouchPct}{???}   % conflict-touched episodes (%)

% v7 SGSC-specific (new to SGSC pipeline)
\newcommand{\sgscManifestVersion}{???}      % manifest schema version
\newcommand{\sgscValidationPacketN}{???}    % validation packets generated
\newcommand{\sgscE2ECoverageRate}{???}      % end-to-end coverage rate
\newcommand{\sgscEntailmentCheckN}{???}     % entailment checks run
```

---

## Paper Sections Affected by v7 Transition

### §4 (Dataset and Benchmark Design)
- **Changes**: `\numTotalScenarios`, `\numEpisodes`, `\numModels`, scenario composition table
- **Stays**: CPG graph counts, constraint counts, derivation ablation numbers (EXP-B)

### §5 (Experiments — Evaluator Disagreement)
- **Changes**: All headline pass rates, FA rates, BSR rates, Kendall W, Friedman statistics, per-model rankings
- **Stays**: Evaluator taxonomy, instrumentation ablation table (E3), operating-point analysis structure

### §5 (Experiments — Generalizability / Held-out)
- **Changes**: `\heldoutFARate`, `\heldoutCompliance`, `\heldoutFisherP`, `\heldoutOddsRatio`
- **Stays**: Held-out CPG list, Fisher test methodology description

### §6 (Limitations)
- **Changes**: Any quantitative limitations tied to episode count or model coverage
- **Stays**: Structural limitations (no patient simulation for external benchmarks, domain mismatch caveat)

### App. Z (CDE Conflict Resolution / SGSC Roadmap)
- **Changes**: `\conflictTouchPct`, `\meanCgaDelta`, per-graph conflict counts after Tier-B patches
- **Stays**: `\conflictPatternsN`, `\tierAN`/`\tierBN`/`\tierCN` classification until graph patches land

### App. T (Per-model FA Table)
- **Changes**: All `\fa*`, `\bsr*`, `\hl*` per-model macros
- **Stays**: Table structure, column definitions

### App. (Compute Footprint — CRES-13)
- **Changes**: Will need new v7 CRES-13 run for new episode count
- **Stays**: v6 footprint numbers remain valid as "v6 baseline" reference point

---

## Notes

1. `auto_numbers_v2.tex` is NOT imported by any paper version — only `auto_numbers.tex` is `\input`'d. Any macros defined only in `auto_numbers_v2.tex` are effectively dead from the paper's perspective.

2. The `\numEpisodes{19,062}` macro (Phase A 9-model headline) is the primary abstract/introduction claim. Phase B canonical is `\vSixFullN{76,464}`. These are distinct populations and must not be conflated.

3. `\heldoutN` appears twice in the file with different values (`1584` at line 469 and `1387` at line 1284 via `\providecommand`). The `\providecommand` at line 1284 wins only if `\heldoutN` is not already defined; since the `\newcommand` at line 469 defines it first, the effective value is `1584`. The `1387` value is the 7-model heldout FA analysis sub-corpus.

4. The freeze tag `paper-macro-recompute-20260430` points to the same commit as the working branch tip at freeze time (`6b3c1e5f`). This tag is the canonical reference for "what the paper claims as of 2026-04-30."
