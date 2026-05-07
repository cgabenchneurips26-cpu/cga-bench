======================================================================
OMISSION/TIMING OVERLAP 정량화
======================================================================

  Total OMISSION violations: 54591
  Total TIMING violations: 8388

  ┌──────────────────────────────────────────────────┐
  │ FALSE OMISSION (performed but marked OMISSION)  │
  │   Count:   9895 /  54591 = 18.1%            │
  │   Episodes affected:   3828 /  12371        │
  ├──────────────────────────────────────────────────┤
  │ DOUBLE COUNT (same action: OMISSION + TIMING)   │
  │   Count:    193                                  │
  │   Episodes:    193                               │
  ├──────────────────────────────────────────────────┤
  │ MISCLASS (performed, OMISSION, no TIMING)       │
  │   Count:   9702                                  │
  │   = Should be TIMING but system missed it       │
  ├──────────────────────────────────────────────────┤
  │ TRUE OMISSION (genuinely not performed)         │
  │   Count:  44696 /  54591 = 81.9%            │
  └──────────────────────────────────────────────────┘

  ★ IMPACT:
    Current OMISSION rate: 86.7%
    If false OMISSIONs removed: 71.0%
    Reduction: 18.1% of OMISSIONs are false

  Top FALSE OMISSION actions:
    attach_defibrillator_pads                         :   962
    begin_high_quality_cpr                            :   962
    analyze_rhythm                                    :   924
    deliver_defibrillation                            :   803
    measure_oxygen_saturation                         :   753
    measure_peak_expiratory_flow                      :   753
    obtain_12_lead_ecg                                :   441
    assess_vital_signs                                :   420
    estimate_tbsa                                     :   420
    administer_oxygen_to_target_94_98                 :   373
    position_supine_legs_elevated                     :   316
    cover_with_clean_dry_dressing                     :   299
    attempt_verbal_deescalation                       :   270
    remove_trigger_if_identifiable                    :   265
    quantify_blood_loss                               :   243

  Top DOUBLE-COUNT actions:
    obtain_12_lead_ecg                                :   121
    assess_vital_signs                                :    72

  FALSE OMISSION by model:
    qwen35b             :  1786
    oss120b             :  1764
    gemma31b            :  1738
    nemotron30b         :  1532
    qwen27b             :  1059
    qwen4b              :  1029
    qwen397b            :   987

============================================================
진단:
  🟡 WARNING: 18%의 OMISSION이 false — 유의미한 비율
     → Normalizer matching 문제일 가능성
============================================================