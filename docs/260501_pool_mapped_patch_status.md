# Pool-Mapped Patch Status Report

**Date**: 2026-05-01 14:30 UTC
**Scope**: All 15 patches from `docs/06_paper_modification_plan.md` cross-referenced against completed experiment data and episode pool provenance.
**Pools**: Phase A (19,062 ep, 9 models, 706 scn) | v6 Baseline (16,944 ep, 8 models, 706 scn) | Phase B (76,464 ep, 8 models, 3,186 scn)

---

## Executive Summary

| Phase | Patches | Data Ready | Macros Ready | Text Ready | Blocked |
|-------|:-------:|:----------:|:------------:|:----------:|:-------:|
| A     | 7       | 6/7        | 4/7          | 0/7        | 0       |
| B     | 5       | 1/5        | 0/5          | 0/5        | 4 (DET) |
| C     | 3       | 0/3        | 0/3          | 0/3        | 3 (B5)  |

**Legend**: Data Ready = raw JSON/CSV exists; Macros Ready = `\providecommand` defined in `auto_numbers.tex`; Text Ready = LaTeX prose written in paper; Blocked = depends on unfinished upstream.

---

## Phase A Patches (no v7 results required)

### Patch A1: AY disclosure (HIGH)

**Status**: DATA READY, MACROS PARTIALLY MISSING

**Pool**: Phase A 9-model (19,062 episodes) for strict-FA; v6 Baseline 8-model (16,944 episodes) for CAV v0.5 keyset fix evidence

| Planned Macro | Value | Source Pool | In `auto_numbers.tex`? | Status |
|---|---|---|---|---|
| `\CStrictFaVanilla` | -- | Phase A 9m | Defined elsewhere? | VERIFY |
| `\CStrictFaFixed` | -- | Phase A 9m | Defined elsewhere? | VERIFY |
| `\CDeltaTotal` | -- | Phase A 9m | Defined elsewhere? | VERIFY |
| `\vSixFlippedEpisodes{602}` | 602 | v6 Baseline 8m | **NO** | MISSING |
| `\vSixToPassEpisodes{340}` | 340 | v6 Baseline 8m | **NO** | MISSING |
| `\vSixToFailEpisodes{262}` | 262 | v6 Baseline 8m | **NO** | MISSING |
| `\vSixOverCorrectionRate{47%}` | 47% | v6 Baseline 8m | **NO** | MISSING |
| `\vSixGenuineNoncomplianceRate{40%}` | 40% | v6 Baseline 8m | **NO** | MISSING |
| `\vSixAuthorInjectionRate{39.0%}` | 39.0% | v6 Baseline 8m | **NO** | MISSING |
| `\bThreeNHardDelta{-1,608}` | -1,608 | v6 Baseline 8m | **NO** | MISSING |
| `\bThreeMABDelta{-14.98}` | -14.98 | v6 Baseline 8m | **NO** | MISSING |
| `\bThreeLooseFADelta{+568}` | +568 | v6 Baseline 8m | **NO** | MISSING |

**Evidence source**: `01_paper_AY_B6_evidence.md` (completed analysis).
**Data available**: Yes, from S101 session (obs 536-539: keyset fix, trace audit, violation breakdown, B3 clinical review).
**Action**: Define 9 new macros in `auto_numbers.tex`, write LaTeX prose.

---

### Patch A2: App AV temperature sensitivity (HIGH)

**Status**: DATA READY, MACROS MISSING

**Pool**: v6 Baseline 8-model subset (Qwen + Gemma only, 1,620 episodes across 4 CPGs)

| Planned Macro | Value | Source Pool | In `auto_numbers.tex`? | Status |
|---|---|---|---|---|
| `\avSweepEpisodes{1,620}` | 1,620 | v6 Baseline 8m subset | **NO** | MISSING |
| `\avSweepCPGs{4}` | 4 | Design constant | **NO** | MISSING |
| `\avQwenMaxDelta{1.74}` | 1.74 | v6 Baseline 8m subset | **NO** | MISSING |
| `\avQwenMaxDeltaT{0.7}` | 0.7 | v6 Baseline 8m subset | **NO** | MISSING |
| `\avGemmaMaxDelta{15.60}` | 15.60 | v6 Baseline 8m subset | **NO** | MISSING |
| `\avGemmaCollapsePp{15}` | 15 | v6 Baseline 8m subset | **NO** | MISSING |
| `\avGemmaSweetSpot{0.1}` | 0.1 | v6 Baseline 8m subset | **NO** | MISSING |
| `\avPilotBoundPp{1.5}` | 1.5 | v6 Baseline 8m subset | **NO** | MISSING |

**Evidence source**: `04_paper_App_AV_temp_sensitivity.md` (completed analysis, session obs S97).
**Data available**: Yes, experiment completed per memory. Report finalized for Appendix AV.
**Action**: Define 8 new macros, replace deferred footnote with completed analysis.

---

### Patch A3: Contribution 5 (CAV) finalize (HIGH)

**Status**: DATA READY, MACROS PARTIALLY AVAILABLE

**Pool**: Cross-pool (CAV is a vocabulary, not an episode-pool metric)

| Planned Macro | Value | Source Pool | In `auto_numbers.tex`? | Status |
|---|---|---|---|---|
| `\CNTotalCav` | -- | Cross-pool | VERIFY | Needs check |
| `\CNExtension` | -- | Cross-pool | VERIFY | Needs check |
| `\CRxnormMatchRate` | -- | Cross-pool | VERIFY | Needs check |

**Evidence source**: `01_paper_AY_B6_evidence.md` + `02_paper_SGSC_contribution.md`.
**Data available**: Yes, CAV v0.5 analysis complete (39% author-injection rate from LLM judge, obs 523-524).
**Action**: Verify 3 macros exist, write contribution 5 paragraph.

---

### Patch A4: Contribution 6 (SGSC) placeholder (MEDIUM)

**Status**: PARTIALLY BLOCKED (placeholder only; fill-in after DET rollout)

**Pool**: N/A until v7 DET rollout completes

| Planned Macro | Value | Source Pool | In `auto_numbers.tex`? | Status |
|---|---|---|---|---|
| `\vSevenScenarios{??}` | TBD | v7 DET corpus | **NO** | BLOCKED |
| `\vSevenAtoms{??}` | TBD | v7 DET corpus | **NO** | BLOCKED |
| `\vSevenGraphs{25}` | 25 | Design constant | `\numGraphsTotal{25}` exists | OK |
| `\vSevenHallucinationRate{0%}` | 0% | v7 DET audit | **NO** | BLOCKED |
| `\vSevenLeakageStatus{PASS}` | PASS | v7 DET audit | **NO** | BLOCKED |
| `\vSevenTruncatedStemRate{0%}` | 0% | v7 DET audit | **NO** | BLOCKED |

**Evidence source**: `02_paper_SGSC_contribution.md`.
**Data available**: Partial. SGSC pipeline code and trust gates implemented (commit `adad0dea`). 14-graph pilot completed (`sgsc_output/pilot_14_report.json`). Full 25-graph DET rollout NOT YET DONE.
**Action**: Write placeholder paragraph (5/2), fill macros after DET (5/3 Phase B1).

---

### Patch A5: Section 4.3 source-grounded wording (HIGH)

**Status**: TEXT-ONLY CHANGE, NO NEW DATA NEEDED

**Pool**: N/A (wording fix acknowledging 481 orphan actions)

**Data available**: Yes, 481 orphan count from CAV v0.5 analysis.
**Action**: Replace the "All scenario actions are source-grounded" claim with qualified statement.

---

### Patch A6: App L "100% provenance" claim correction (HIGH)

**Status**: TEXT-ONLY CHANGE, NO NEW DATA NEEDED

**Pool**: N/A (wording fix restricting claim to graph-encoded constraints)

**Data available**: Yes, same evidence as A5.
**Action**: Restrict "100%" claim to graph-encoded constraints.

---

### Patch A7: Section 5.6 Kendall W footnote (MEDIUM)

**Status**: DATA READY, MACROS EXIST

**Pool**: Phase A 8-model (16,944 ep) for W=0.408; Phase B 8-model (76,464 ep) for W=0.219

| Existing Macro | Value | Source Pool | Line | Status |
|---|---|---|---|---|
| `\rankBootstrapKendallW{0.408}` | 0.408 | Phase A 8m (bootstrap) | L645 | OK |
| `\rankBootstrapKendallWLo{0.342}` | 0.342 | Phase A 8m | L646 | OK |
| `\rankBootstrapKendallWHi{0.461}` | 0.461 | Phase A 8m | L647 | OK |
| `\kendallW{0.219}` | 0.219 | Phase B 8m | L310 | OK |
| `\reversalRate{96.4}` | 96.4% | Phase B 8m | L311 | OK |

**Pool note**: The paper's body text (Section 5.6) cites W=0.408 and 75% reversal. Per session obs 530-532, these are from Phase A 8-model with 4 evaluators (AC, MAB, C2, CGA). The v6-fixed equivalent is W=0.381, 78.6% reversal.

**Evidence source**: `01_paper_AY_B6_evidence.md` section 5, `evidence_pack/analysis/rank_bootstrap.json`.
**Data available**: Yes, all numbers computed.
**Action**: Add footnote explaining computation method + Fixed-scoring equivalents.

---

## Phase B Patches (after DET rollout)

### Patch B1: Contribution 6 macro fill-in

**Status**: BLOCKED on 25-graph DET rollout

**Pool**: v7 DET corpus (TBD)

**Data available**: No. Requires DET rollout + quality verification.
**Action**: Run aggregate metrics on `sgsc_output/v7_e3_det_overnight/`, fill A4 macros.

---

### Patch B2: App SGSC methodology section

**Status**: PARTIALLY READY (code architecture documented, no v7 numbers)

**Pool**: N/A (methodology description, not episode data)

**Data available**: SGSC pipeline code fully implemented and tested (225+ tests, trust gates 1-8 closed). Architecture documented in `docs/specs/source_grounded_scenario_compiler.md`.
**Action**: Write full methodology appendix section (pipeline architecture, atom extraction, entailment, graph compilation, scenario compilation, quality gates, reproducibility config).

---

### Patch B3: App Reproducibility section

**Status**: BLOCKED on DET rollout (needs git commit + artifact SHA)

**Pool**: N/A (reproducibility methodology)

| Planned Macro | Value | Source Pool | In `auto_numbers.tex`? | Status |
|---|---|---|---|---|
| `\sgscGitCommit` | TBD | v7 DET | **NO** | BLOCKED |
| `\sgscArtifactSha` | TBD | v7 DET | **NO** | BLOCKED |
| `\sgscNondetCV{4.2%}` | 4.2% | v7 NONDET 3-run | **NO** | BLOCKED |

**Action**: Write section after DET rollout; fill commit hash + artifact SHA.

---

### Patch B4: App DET vs NONDET comparison

**Status**: BLOCKED on DET rollout

**Pool**: v7 DET vs NONDET comparison

**Data available**: No. Requires 5/3 morning DET vs NONDET comparison report.
**Action**: Build per-graph comparison table + aggregate metrics + vocabulary turnover (Jaccard).

---

### Patch B5: V7 Replication section

**Status**: BLOCKED on v7 verdict matrix (expected 5/3 17:00)

**Pool**: v7 corpus (TBD)

**Data available**: No. Requires v7 episode rerun + verdict matrix.
**Action**: Compute v7 strict consensus FA, Kendall W, pairwise rank reversal, Bayes floor. Build 3-axis comparison table (v6-vanilla, v6-fixed, v7-SGSC).

---

## Phase C Patches (5/4-5/5)

### Patch C1: 3-axis comparison polish
**Status**: BLOCKED on B5 (v7 numbers)

### Patch C2: Reviewer-perspective re-read
**Status**: BLOCKED on all Phase A+B completion

### Patch C3: Cross-references + bibliography + appendix renumbering
**Status**: BLOCKED on C1+C2

---

## Pool-Consistency Issues in Current `auto_numbers.tex`

The unified audit (`auto_numbers_unified_audit.tex`) identified **9 cross-pool divergences**. Below are the most critical issues affecting patches:

### Issue 1: Mixed Pool Provenance in Headline Macros

| Macro | Value | Comment Says | Actual Pool | Paper Context |
|---|---|---|---|---|
| `\numEpisodes{19,062}` | 19,062 | Phase A 9m | Phase A 9m | Abstract headline |
| `\etaEvaluator{0.190}` | 0.190 | "v6 Phase B n=76,464" | Phase B 8m | Section 5 |
| `\etaRun{0.088}` | 0.088 | "v6 Phase B" | Phase B 8m | Section 5 |
| `\reversalRate{96.4}` | 96.4% | "v6 Phase B (27/28)" | Phase B 8m | Section 5.6 |
| `\kendallW{0.219}` | 0.219 | "v6 Phase B" | Phase B 8m | Section 5.6 |
| `\verdictFlipRate{92.0}` | 92.0% | No pool tag | **AMBIGUOUS** | Section 5 |
| `\bsrCondAC{60.9}` | 60.9 | "v6 Phase B" | **MISMATCH**: Value 60.9 = Phase A 9m, not Phase B | Section 5 |
| `\strictFAThree{5.90}` | 5.90% | "Phase A 9m (recomputed)" | Phase A 9m | Section 5 |
| `\consensusFATotal{2,106}` | 2,106 | "Phase A 9m" | Phase A 9m | Section 5 |

### Issue 2: BSR Conditional Pool Mismatch (CRITICAL)

`\bsrCondAC{60.9}` comment says "v6 Phase B" but:
- Phase A 9-model `bsr_conditional.phase_a_original.ASC.bsr_pct` = **60.34** (rounds to 60.3)
- Phase B 8-model `auto_numbers_phaseB.tex \phaseBBsrAC` = **33.7**
- The value 60.9 actually matches `\phaseABsrAC{60.9}` from `auto_numbers_phaseA.tex`

**Root cause**: Comment was wrong. The macro is Phase A, labeled as Phase B.

### Issue 3: `\cresOneDNEpisodes{14,826}` is STALE (v5 era, 7-model)

This is from the W8-filtered 7-model era. Current pools are 9-model (19,062) or 8-model (16,944 / 76,464). This macro is used in CRES-1D structural classifier appendix and should be acknowledged as a frozen W8 subset.

### Issue 4: Hardcoded Numbers in Main Body (from `260501_main_tex_hardcoded_numbers_audit.md`)

**6 P0 issues** (computed statistic with NO macro) that map to specific pools:

| Body Line | Value | Correct Pool | Macro to Define |
|---|---|---|---|
| L465 | `0.059` (eta2_eval typed) | v6 Base 8m typed | `\typedCwtManualEtaEval{0.059}` |
| L465 | `0.076` (eta2_run typed) | v6 Base 8m typed | `\typedCwtManualEtaRun{0.076}` |
| L470, L503 | `46.3%` (cell pair reversal) | Phase A 8m | `\cellPairReversalPhaseA{46.3}` |
| L503 | `4.5x` (expansion ratio) | Cross-pool (3186/706) | `\phaseBExpansionRatio{4.5}` |
| L279, L417 | `1.4%` (PAF forbid detect) | E1 controlled perturbation | `\eOneForbidPAFRate{1.4}` |
| L279, L417 | `100%` (TCC detect) | E1 controlled perturbation | `\eOneTCCDetectAll{100}` |

**Pool verification for L465 eta values**:
- `v6_full_macros.json` Phase A typed: `eta2_eval=0.0586, eta2_run=0.076`
- Paper says `0.059` = rounded from 0.0586. Correct pool = **v6 Baseline 8-model typed CwT**.
- The Phase B typed equivalent: `eta2_eval=0.1003, eta2_run=0.0881` (ratio 1.14, NO reversal).
- Key finding: eta reversal (eval < run) only occurs on **manual 706-scenario subset** with typed CwT.

**9 P1 issues** (macro exists but hardcoded value used):

| Body Line | Value | Available Macro | Pool |
|---|---|---|---|
| L406-503 (6x) | `706` | `\numTotalScenarios{706}` | Design constant |
| L465 | `16,944` | `\phaseAEpisodes{16,944}` (main L224) | v6 Baseline 8m |
| L367 | `~44%` | `\bayesErrTerm{0.436}` = 43.6% | W8 14,826 ep |

---

## Completed Experiment Numbers by Pool

### Pool: Phase A 9-model (19,062 episodes)

| Experiment | Key Metrics | Macro(s) | JSON Source |
|---|---|---|---|
| E1 Verdict Flip | flip_count=16,331, flip_rate=92.0% | `\verdictFlipCount`, `\verdictFlipRate` | exp_e1 |
| E1 False Accept | all_oblivious FA=2,106 (11.05%) | `\consensusFATotal`, `\consensusFARate` | exp_e1 |
| E9 High-Authority | strict FA=5.90%, rank reversal=2.78% | `\Eninefastrictfull`, `\Eninerankreversal` | `exp_e9_high_authority_core.json` |
| E9 Severity Overlay | 1,124 strict FA: 828 minor/189 mod/85 major/22 severe | `\safetyCorePctOfStrictFA{12.8}` | `exp_e9_severity_overlay.json` |
| E30 Non-Timing | 443 natural traps (2.32%), AC blind 69.1% | `\nonTimingNaturalCount`, `\nonTimingACBlindPct` | verdict_matrix_v6.json |
| Per-model headline | 9 models x pass rates | `\hlDS*`, `\hlQfour*`, etc. | L1300-1343 |
| BSR per model | 9 models x BSR | `\bsrDS*`, `\bsrQfour*`, etc. | L844-870 |
| Rank bootstrap | W=0.408 [0.342,0.461], 75% reversal | `\rankBootstrapKendallW` + CI | rank_bootstrap.json |

### Pool: v6 Baseline 8-model (16,944 episodes)

| Experiment | Key Metrics | Macro(s) | JSON Source |
|---|---|---|---|
| CRES-5 eta2 (original) | eta2_eval=0.1234, eta2_run=0.076, ratio=1.62 | *No pool-specific macro* | `v6_full_macros.json` |
| CRES-5 eta2 (typed CwT) | eta2_eval=0.0586, eta2_run=0.076, ratio=0.77 (REVERSED) | *No pool-specific macro* | `v6_full_macros.json` |
| FA strict 3-way (original) | 912 (5.38%) | *No pool-specific macro* | `v6_full_macros.json` |
| Normalizer MM | 8 models, mean delta +3.6, rho=1.000 | `\normalizerMM*` series | multimodel_macros.tex |
| Phase 1 CwT-typed (W8) | pass 36.4%->99.0%, FA 6.2%->29.1% | `\cwtOrig*`, `\cwtTyped*` | phase1 evidence |
| Bayes error | term=0.436, aset=0.024, nctx=0.003 | `\bayesErr*` series | auto_numbers_v18.tex |

### Pool: Phase B 8-model (76,464 episodes)

| Experiment | Key Metrics | Macro(s) | JSON Source |
|---|---|---|---|
| CRES-5 eta2 (original) | eta2_eval=0.190, eta2_run=0.088, ratio=2.15 | `\cresFiveEtaSq`, `\cresFiveEtaRun` | `v6_full_macros.json` |
| CRES-5 eta2 (typed CwT) | eta2_eval=0.100, eta2_run=0.088, ratio=1.14 | `\vSixFullTypedEtaSq{0.100}` | `v6_full_macros.json` |
| FA strict 3-way | 2,974 (3.89%) | `\vSixFullStrictFAThree{3.89}` | `v6_full_macros.json` |
| FA consensus | 4,405 (5.76%) | `\vSixFullConsensusFA{5.76}` | recompute_v6_full_extras.py |
| Ranking | Friedman chi=31.3, W=0.219, 96.4% reversal | `\friedmanChi`, `\kendallW`, `\reversalRate` | exp_d/cres_12 |
| BSR conditional | AC=33.7%, MAB=37.3%, C2=23.7% | `\phaseBBsrAC` etc. in phaseB.tex | auto_numbers_phaseB.tex |
| Severity (consensus FA) | 300 crit, 144 high, 2674 med, 1287 low | `\vSixFullConsensusFACritical{300}` etc. | recompute_v6_full_severity.py |
| Per-model pass rates | 8 models x AC/MAB/CGA | `\phaseBAC*`, `\phaseBMAB*`, `\phaseBCGA*` | auto_numbers_phaseB.tex |
| v6 Full extras | bootstrap CIs on all effect sizes | `\vSixFull*CI` series | recompute_v6_full_extras.py |
| Heldout | FA=18.82%, flip=98.34%, Fisher p<0.001 | `\heldoutFARate`, `\heldoutFlipRate` | aggregate_heldout_v6.py |

---

## Missing Macros Summary (Actionable)

### Priority 1: New macros needed for Phase A patches

```latex
% Patch A1: AY disclosure (9 macros)
\providecommand{\vSixFlippedEpisodes}{602}
\providecommand{\vSixToPassEpisodes}{340}
\providecommand{\vSixToFailEpisodes}{262}
\providecommand{\vSixOverCorrectionRate}{47}
\providecommand{\vSixGenuineNoncomplianceRate}{40}
\providecommand{\vSixAuthorInjectionRate}{39.0}
\providecommand{\bThreeNHardDelta}{-1{,}608}
\providecommand{\bThreeMABDelta}{-14.98}
\providecommand{\bThreeLooseFADelta}{+568}

% Patch A2: Temperature sensitivity (8 macros)
\providecommand{\avSweepEpisodes}{1{,}620}
\providecommand{\avSweepCPGs}{4}
\providecommand{\avQwenMaxDelta}{1.74}
\providecommand{\avQwenMaxDeltaT}{0.7}
\providecommand{\avGemmaMaxDelta}{15.60}
\providecommand{\avGemmaCollapsePp}{15}
\providecommand{\avGemmaSweetSpot}{0.1}
\providecommand{\avPilotBoundPp}{1.5}
```

### Priority 2: Hardcoded-to-macro substitutions (from audit)

```latex
% P0 fixes: define missing macros
\providecommand{\typedCwtManualEtaEval}{0.059}     % v6 Base 8m typed
\providecommand{\typedCwtManualEtaRun}{0.076}       % v6 Base 8m typed
\providecommand{\cellPairReversalPhaseA}{46.3}       % Phase A 8m
\providecommand{\phaseBExpansionRatio}{4.5}          % 3186/706
\providecommand{\eOneForbidPAFRate}{1.4}             % E1 controlled perturbation
\providecommand{\eOneTCCDetectAll}{100}              % E1 structural

% P1 fixes: replace hardcoded body text with existing macros
% L406-503: "706" -> \numTotalScenarios{}  (6 occurrences)
% L465: "16,944" -> \phaseAEpisodes{} or \normalizerMMEpisodes{}
% L367: "~44%" -> link to \bayesErrTerm{0.436}
% L503: "0.99%" -> \nemotronEmptyPct{}
```

### Priority 3: Pool-label corrections

```latex
% Fix \bsrCondAC comment: it's Phase A, not Phase B
\providecommand{\bsrCondAC}{60.9}    % Phase A 9m (NOT Phase B as prev comment said)

% Fix \verdictFlipRate pool tag
\providecommand{\verdictFlipRate}{92.0}  % Phase A 9m (needs explicit pool tag)
```

---

## Recommended Execution Order

1. **Immediate (no blocking)**: Patches A5, A6 (text-only, 35 min combined)
2. **Short-term**: Define Priority 1+2 macros (17 new + 6 P0 fix = 23 macro definitions)
3. **Same session**: Patches A1 (90 min), A2 (60 min), A7 (20 min), A3 (30 min)
4. **A4 placeholder**: Write contribution 6 draft with `??` macros
5. **After DET**: B1 fill-in, B2 methodology, B3 reproducibility, B4 DET-vs-NONDET
6. **After v7 verdict matrix**: B5 replication section
7. **Final polish**: C1, C2, C3
