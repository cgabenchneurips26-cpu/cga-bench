> **HISTORICAL DOCUMENT** — Written during the v3 era (180 episodes, 4 models,
> `results/clean_slate_rescored/`). Current baseline is v6 (16,944 episodes,
> 8 models). Numbers in this file reflect the v3 era and should NOT be cited
> in the paper. See `docs/RESULT_LINEAGE_AUDIT.md` for the full era map.

---

================================================================================
auto_numbers.tex 전수 검증 보고서
매크로 수: 295
에피소드 수: 10660
그래프 수: 25
================================================================================

──────────────────────────────────────────────────────────────────────
## Level A: System Numbers (from graph YAMLs)
  🔴[A] numBefore                     : stated=          65  computed=          10
  🔴[A] numConditionalRules           : stated=         312  computed=           0
  ✅ numDomains                    : stated=          25  computed=          25
  ✅ numForbidden                  : stated=         212  computed=         212
  ✅ numGraphsHeldout              : stated=           5  computed=           5
  ✅ numGraphsMain                 : stated=          20  computed=          20
  ✅ numGraphsTotal                : stated=          25  computed=          25
  🔴[A] numHardConstraints            : stated=        1049  computed=         994
  ✅ numMust                       : stated=         557  computed=         557
  ✅ numNodes                      : stated=         167  computed=         167
  ✅ numWithin                     : stated=         215  computed=         215

──────────────────────────────────────────────────────────────────────
## Level A: Verdict Stats (from episodes)
  🔴[A] bsrAC                         : stated=        59.3  computed=        67.7
  🔴[A] bsrCTwo                       : stated=        25.1  computed=        36.2
  🔴[A] bsrCondAC                     : stated=        74.4  computed=        96.1
  🔴[A] bsrCondCTwo                   : stated=        67.8  computed=        95.0
  🔴[A] bsrCondDxEM                   : stated=        74.7  computed=        96.8
  🔴[A] bsrCondMAB                    : stated=        75.8  computed=        96.1
  🔴[A] bsrDxEM                       : stated=        74.7  computed=        96.8
  🔴[A] bsrMAB                        : stated=        44.2  computed=        67.7
  🔴[A] bsrNAC                        : stated=        5918  computed=        7214
  🔴[A] bsrNCTwo                      : stated=        2506  computed=        3864
  🔴[A] bsrNDxEM                      : stated=        7458  computed=       10315
  🔴[A] bsrNMAB                       : stated=        4415  computed=        7214
  🔴[A] faAllOblivious                : stated=        25.1  computed=        36.2
  🔴[A] faAllObliviousCount           : stated=        2506  computed=        3864
  🔴[A] numEpisodes                   : stated=        9982  computed=       10660
  🔴[A] passrateCGABench              : stated=        25.3  computed=         3.2
  ✅ passrateCTwo                  : stated=        37.0  computed=        38.2
  ✅ passrateDxEM                  : stated=       100.0  computed=       100.0
  🔴[A] passtrateACProxy              : stated=        79.7  computed=        70.5
  🔴[A] passtrateMABProxy             : stated=        58.3  computed=        70.5
  🔴[A] verdictFlipCount              : stated=        9144  computed=       10455
  🔴[A] verdictFlipRate               : stated=        91.6  computed=        98.1
  🔴[A] vfACvsCGA                     : stated=        6405  computed=        7263
  🔴[A] vfACvsCGAPct                  : stated=        64.2  computed=        68.1
  🔴[A] vfACvsCTwo                    : stated=        4260  computed=        3441
  🔴[A] vfACvsCTwoPct                 : stated=        42.7  computed=        32.3
  🔴[A] vfACvsMAB                     : stated=        2859  computed=           0
  🔴[A] vfACvsMABPct                  : stated=        28.6  computed=         0.0
  ✅ vfCTwovsCGA                   : stated=        3841  computed=        4004
  ✅ vfCTwovsCGAPct                : stated=        38.5  computed=        37.6
  🔴[A] vfMABvsCGA                    : stated=        5532  computed=        7263
  🔴[A] vfMABvsCGAPct                 : stated=        55.4  computed=        68.1
  🔴[A] vfMABvsCTwo                   : stated=        4185  computed=        3441
  🔴[A] vfMABvsCTwoPct                : stated=        41.9  computed=        32.3

──────────────────────────────────────────────────────────────────────
## Level A: Variance Decomposition (η²)
  ✅ etaEvaluator                  : stated=       0.312  computed=      0.3109
  ✅ etaRatio                      : stated=       16262  computed=     17001.4
  ✅ etaRun                        : stated=     0.00002  computed=     1.8e-05
    _debug_eval_means: {'ASC': np.float64(0.7045), 'CwT': np.float64(0.3817), 'PAF': np.float64(0.7045), 'TCC': np.float64(0.0324)}
    _debug_run_means: {'0': np.float64(0.4544), '1': np.float64(0.4588), '2': np.float64(0.4542)}
    _debug_ss_eval: 3288.55
    _debug_ss_run: 0.19
    _debug_ss_total: 10576.58

──────────────────────────────────────────────────────────────────────
## Level A: Ranking (Friedman)
  ✅ friedmanChi                   : stated=        21.0  computed=        21.0
  🔴[A] friedmanP                     : stated=      0.0001  computed=    0.000105
  ✅ kendallW                      : stated=       0.000  computed=       0.411
  🔴[A] reversalRate                  : stated=        76.2  computed=        71.4
  ✅ topOneFlip                    : stated=         yes  computed=         yes
    _debug_models: ['gemma31b', 'nemotron30b', 'oss120b', 'qwen27b', 'qwen35b', 'qwen397b', 'qwen4b']
    _debug_pass_rates: {'gemma31b': {'ASC': np.float64(65.1), 'CwT': np.float64(33.1), 'PAF': np.float64(65.1), 'TCC': np.float64(4.5)}, 'nemotron30b': {'ASC': np.float64(48.8), 'CwT': np.float64(20.4), 'PAF': np.float64(48.8), 'TCC': np.float64(3.9)}, 'oss120b': {'ASC': np.float64(74.5), 'CwT': np.float64(41.0), 'PAF': np.float64(74.5), 'TCC': np.float64(3.6)}, 'qwen27b': {'ASC': np.float64(83.2), 'CwT': np.float64(48.3), 'PAF': np.float64(83.2), 'TCC': np.float64(2.0)}, 'qwen35b': {'ASC': np.float64(83.8), 'CwT': np.float64(49.2), 'PAF': np.float64(83.8), 'TCC': np.float64(3.7)}, 'qwen397b': {'ASC': np.float64(83.9), 'CwT': np.float64(52.6), 'PAF': np.float64(83.9), 'TCC': np.float64(0.1)}, 'qwen4b': {'ASC': np.float64(56.4), 'CwT': np.float64(26.4), 'PAF': np.float64(56.4), 'TCC': np.float64(3.4)}}
    _debug_ranks: {'gemma31b': {'ASC': 5, 'CwT': 5, 'PAF': 5, 'TCC': 1}, 'nemotron30b': {'ASC': 7, 'CwT': 7, 'PAF': 7, 'TCC': 2}, 'oss120b': {'ASC': 4, 'CwT': 4, 'PAF': 4, 'TCC': 4}, 'qwen27b': {'ASC': 3, 'CwT': 3, 'PAF': 3, 'TCC': 6}, 'qwen35b': {'ASC': 2, 'CwT': 2, 'PAF': 2, 'TCC': 3}, 'qwen397b': {'ASC': 1, 'CwT': 1, 'PAF': 1, 'TCC': 7}, 'qwen4b': {'ASC': 6, 'CwT': 6, 'PAF': 6, 'TCC': 5}}

──────────────────────────────────────────────────────────────────────
## Level A: Engine vs Manual
  🔴[A] bsrAutoAC                     : stated=        62.7  computed=        71.0
  🔴[A] bsrManualAC                   : stated=        44.3  computed=        50.9
  🔴[A] vfAuto                        : stated=        91.2  computed=        98.0
  🔴[A] vfManual                      : stated=        94.0  computed=        98.6
  ✅ violAuto                      : stated=         9.2  computed=         9.2
  ✅ violManual                    : stated=         7.7  computed=         7.7

──────────────────────────────────────────────────────────────────────
## Level A: Timing Audit

──────────────────────────────────────────────────────────────────────
## Level B: Arithmetic Consistency
  ✅ All arithmetic checks pass

──────────────────────────────────────────────────────────────────────
## Level C: Old Data (180 episodes) — Cannot Verify
  🔵 instrFullHard                 :           36  (from old 180-ep data, re-run needed)
  🔵 instrNoTimestampsHard         :           24  (from old 180-ep data, re-run needed)
  🔵 instrTimingLoss               :         33.3  (from old 180-ep data, re-run needed)
  🔵 fleissKappaMatchedThirty      :        -0.01  (from old 180-ep data, re-run needed)
  🔵 fleissKappaMatchedForty       :         0.05  (from old 180-ep data, re-run needed)
  🔵 fleissKappaMatchedFifty       :        0.144  (from old 180-ep data, re-run needed)
  🔵 verdictFlipRateMatchedThirty  :         87.2  (from old 180-ep data, re-run needed)
  🔵 verdictFlipRateMatchedForty   :         87.8  (from old 180-ep data, re-run needed)
  🔵 verdictFlipRateMatchedFifty   :         81.1  (from old 180-ep data, re-run needed)
  🔵 numEvaluatorsExpanded         :           12  (from old 180-ep data, re-run needed)
  🔵 numClusters                   :            2  (from old 180-ep data, re-run needed)
  🔵 cophenetic                    :        0.941  (from old 180-ep data, re-run needed)
  🔵 silhouetteScore               :         0.63  (from old 180-ep data, re-run needed)
  🔵 bootstrapARI                  :        0.828  (from old 180-ep data, re-run needed)
  🔵 bootstrapARILow               :        0.641  (from old 180-ep data, re-run needed)
  🔵 bootstrapARIHigh              :          1.0  (from old 180-ep data, re-run needed)

======================================================================
## SUMMARY
  Total macros: 295
  Discrepancies found: 39
    Level A (raw mismatch): 39
    Level B (arithmetic):   0

  🔴 DISCREPANCIES:
    L272 numBefore                     : stated=65 → should be 10
    L255 numConditionalRules           : stated=312 → should be 0
    L275 numHardConstraints            : stated=1049 → should be 994
    L 39 bsrAC                         : stated=59.3 → should be 67.7
    L 41 bsrCTwo                       : stated=25.1 → should be 36.2
    L 45 bsrCondAC                     : stated=74.4 → should be 96.1
    L 47 bsrCondCTwo                   : stated=67.8 → should be 95.0
    L 48 bsrCondDxEM                   : stated=74.7 → should be 96.8
    L 46 bsrCondMAB                    : stated=75.8 → should be 96.1
    L 38 bsrDxEM                       : stated=74.7 → should be 96.8
    L 40 bsrMAB                        : stated=44.2 → should be 67.7
    L131 bsrNAC                        : stated=5918 → should be 7214
    L134 bsrNCTwo                      : stated=2506 → should be 3864
    L135 bsrNDxEM                      : stated=7458 → should be 10315
    L136 bsrNMAB                       : stated=4415 → should be 7214
    L 30 faAllOblivious                : stated=25.1 → should be 36.2
    L 31 faAllObliviousCount           : stated=2506 → should be 3864
    L 24 numEpisodes                   : stated=9982 → should be 10660
    L 55 passrateCGABench              : stated=25.3 → should be 3.2
    L 52 passtrateACProxy              : stated=79.7 → should be 70.5
    L 54 passtrateMABProxy             : stated=58.3 → should be 70.5
    L 26 verdictFlipCount              : stated=9144 → should be 10455
    L 25 verdictFlipRate               : stated=91.6 → should be 98.1
    L114 vfACvsCGA                     : stated=6405 → should be 7263
    L115 vfACvsCGAPct                  : stated=64.2 → should be 68.1
    L116 vfACvsCTwo                    : stated=4260 → should be 3441
    L117 vfACvsCTwoPct                 : stated=42.7 → should be 32.3
    L118 vfACvsMAB                     : stated=2859 → should be 0
    L119 vfACvsMABPct                  : stated=28.6 → should be 0.0
    L122 vfMABvsCGA                    : stated=5532 → should be 7263
    L123 vfMABvsCGAPct                 : stated=55.4 → should be 68.1
    L124 vfMABvsCTwo                   : stated=4185 → should be 3441
    L125 vfMABvsCTwoPct                : stated=41.9 → should be 32.3
    L360 friedmanP                     : stated=0.0001 → should be 0.000105
    L362 reversalRate                  : stated=76.2 → should be 71.4
    L301 bsrAutoAC                     : stated=62.7 → should be 71.0
    L300 bsrManualAC                   : stated=44.3 → should be 50.9
    L299 vfAuto                        : stated=91.2 → should be 98.0
    L298 vfManual                      : stated=94.0 → should be 98.6