                                                                                                                                                                          
  Paper Baseline Analysis                                                                                                                                                                           
                                                                                                                                                                                                    
  Latest files (the active \input chain)                                                                                                                                                            
   
  ┌──────────────────────┬─────────────┬────────────────────────────────────┐                                                                                                                       
  │         File         │  Modified   │                Role                │                                                                                                                     
  ├──────────────────────┼─────────────┼────────────────────────────────────┤
  │ main_final_v18.tex   │ May 1 05:10 │ Main paper                         │
  ├──────────────────────┼─────────────┼────────────────────────────────────┤
  │ auto_numbers.tex     │ May 1 04:37 │ Primary macros (91KB, ~1500 lines) │
  ├──────────────────────┼─────────────┼────────────────────────────────────┤
  │ auto_numbers_cav.tex │ May 1 05:07 │ CAV extension macros               │
  ├──────────────────────┼─────────────┼────────────────────────────────────┤
  │ appendix_v18.tex     │ May 1 05:10 │ Appendix                           │
  └──────────────────────┴─────────────┴────────────────────────────────────┘

  v17 and appendix.tex exist but are NOT used by v18.

  The baseline is NEITHER v5 NOR v6a — it's a 3-tier hybrid

  The paper uses three distinct episode pools, and most macros are computed on whichever pool is largest:

  ┌─────────────────────────┬──────────┬─────────────────────────┬──────────────────────────────┬──────┬────────────────────────────────────────────────────────────────┐
  │          Pool           │ Episodes │         Models          │          Scenarios           │ Runs │                            Used For                            │
  ├─────────────────────────┼──────────┼─────────────────────────┼──────────────────────────────┼──────┼────────────────────────────────────────────────────────────────┤
  │ Phase A (headline)      │ 19,062   │ 9 (incl. Llama-4-Scout) │ 706 manual                   │ 3    │ Headline table, verdict flip, BSR, consensus FA                │
  ├─────────────────────────┼──────────┼─────────────────────────┼──────────────────────────────┼──────┼────────────────────────────────────────────────────────────────┤
  │ Phase B (auto-expanded) │ 76,464   │ 8                       │ 3,186 (706+2480 Tier-S auto) │ 3    │ η², ranking flip, typed-CwT robustness, variance decomposition │
  ├─────────────────────────┼──────────┼─────────────────────────┼──────────────────────────────┼──────┼────────────────────────────────────────────────────────────────┤
  │ v6 baseline (legacy)    │ 16,944   │ 8                       │ 706                          │ 3    │ \solverSubsetN, normalizer ablation, \normalizerMMEpisodes     │
  ├─────────────────────────┼──────────┼─────────────────────────┼──────────────────────────────┼──────┼────────────────────────────────────────────────────────────────┤
  │ W8 (phase1 CwT)         │ 14,826   │ 7 (v5 era)              │ 706                          │ 3    │ CwT-typed sensitivity only (appendix)                          │
  └─────────────────────────┴──────────┴─────────────────────────┴──────────────────────────────┴──────┴────────────────────────────────────────────────────────────────┘

  Inconsistency Map

  Problem 1: Pass rates are v6 8-model but headline is Phase A 9-model
  Line 248: % Pass rates per evaluator (v6, 8 models)
  Line 249: \passtrateACProxy{76.9}        ← computed on 8 models
  Line 229: \numEpisodes{19,062}           ← 9 models
  The pass rates in the paper body use 8-model numbers, but \numEpisodes says 19,062 (9 models). The reader sees "19,062 episodes" and "76.9% AC pass rate" in the same section, but they come from
  different pools.

  Problem 2: Key effect-size metrics silently moved to Phase B
  Line 262: \etaEvaluator{0.190}  % v6 Phase B (n=76,464). Phase A 5-eval was 0.078.
  Line 311: \reversalRate{96.4}   % v6 Phase B (27/28). Phase A was 75.0.
  The paper's headline η²(eval)=0.190 and reversal=96.4% are from Phase B (76,464 ep) — but the text says "19,062 episodes" in the setup section. These numbers were silently upgraded from Phase A
  values.

  Problem 3: CRES-1D still uses v5 era count
  Line 883: \cresOneDNEpisodes{14,826}  ← v5/W8 era (7 models)
  This is the structural classifier experiment, still showing 14,826 episodes (v5 era, 7 models). Never recomputed for 8 or 9 models.

  Problem 4: Scenario counts inconsistency
  Line 4:  \numManualScenarios{105}   ← "107 in YAML minus 2 e2e-test-only"
  Line 5:  \numAutoScenarios{601}
  Line 218: \numTotalScenarios{706}    ← 105+601=706
  But MEMORY says "manual 107 + auto 583 = 690". The paper's 105+601=706 doesn't match the project's canonical 107+583=690 at all. The paper added 18 auto scenarios (601 vs 583) while subtracting
  2 manual (107→105).

  Problem 5: Line 1 says "Auto-generated by exp_f_evidence_pack_v5.py"
  The file header still references the v5-era generator script, even though most macros have been overwritten by later scripts.

  Problem 6: Per-model episode counts are Phase B, not Phase A
  Lines 824-831: \numEpisodesDS{9558} through \numEpisodesQwenThreeNineSeven{9558}
  9,558 = 3,186 scenarios × 3 runs = Phase B per model. But these are 8 models (no Llama-4-Scout), inconsistent with the headline 9-model count.

  Summary Table

  ┌───────────────────────┬────────┬───────────────┬───────────────────────────┐
  │         Macro         │ Value  │  Source Pool  │ Consistent with headline? │
  ├───────────────────────┼────────┼───────────────┼───────────────────────────┤
  │ \numEpisodes          │ 19,062 │ Phase A (9m)  │ HEADLINE                  │
  ├───────────────────────┼────────┼───────────────┼───────────────────────────┤
  │ \numModels            │ 9      │ Phase A       │ HEADLINE                  │
  ├───────────────────────┼────────┼───────────────┼───────────────────────────┤
  │ \passtrateACProxy     │ 76.9%  │ v6 (8m)       │ NO — 8 models, not 9      │
  ├───────────────────────┼────────┼───────────────┼───────────────────────────┤
  │ \passrateCGABench     │ 44.6%  │ v6 (8m)       │ NO — 8 models, not 9      │
  ├───────────────────────┼────────┼───────────────┼───────────────────────────┤
  │ \etaEvaluator         │ 0.190  │ Phase B (76k) │ NO — different pool       │
  ├───────────────────────┼────────┼───────────────┼───────────────────────────┤
  │ \reversalRate         │ 96.4%  │ Phase B (76k) │ NO — different pool       │
  ├───────────────────────┼────────┼───────────────┼───────────────────────────┤
  │ \verdictFlipRate      │ 92.0%  │ Phase A?      │ Unclear                   │
  ├───────────────────────┼────────┼───────────────┼───────────────────────────┤
  │ \solverSubsetN        │ 16,944 │ v6 (8m)       │ NO — different pool       │
  ├───────────────────────┼────────┼───────────────┼───────────────────────────┤
  │ \normalizerMMEpisodes │ 16,944 │ v6 (8m)       │ NO — different pool       │
  ├───────────────────────┼────────┼───────────────┼───────────────────────────┤
  │ \cresOneDNEpisodes    │ 14,826 │ W8/v5 (7m)    │ NO — stale era            │
  ├───────────────────────┼────────┼───────────────┼───────────────────────────┤
  │ \numEpisodesDS etc.   │ 9,558  │ Phase B (8m)  │ NO — different pool       │
  ├───────────────────────┼────────┼───────────────┼───────────────────────────┤
  │ \consensusFATotal     │ 2,106  │ Phase A (9m)  │ YES                       │
  └───────────────────────┴────────┴───────────────┴───────────────────────────┘

  Verdict

  The baselines are not unified. The paper presents a 9-model headline (19,062 episodes) but most computed metrics come from either:
  - 8-model Phase B (76,464 ep) for effect sizes / ranking
  - 8-model v6 (16,944 ep) for pass rates and solver experiments
  - 7-model v5/W8 (14,826 ep) for CRES-1D and CwT-typed

  A reader who sees "19,062 episodes across 9 models" would expect all numbers to come from that pool, but they don't. The pass rates come from 8 models, the effect sizes come from 76,464 episodes
   (8 models × 3,186 scenarios), and CRES-1D still uses the 7-model v5 era.