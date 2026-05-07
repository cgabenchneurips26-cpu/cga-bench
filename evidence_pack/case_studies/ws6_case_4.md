# Case Study 4: af_new_onset_basic_27B_2

### Scenario Summary

Scenario **af_new_onset_basic** (domain: atrial_fibrillation) evaluated with model 27B. This episode had 1 violation(s) with types: WITHIN.

### Evaluator Verdicts

| Evaluator | Verdict |
|-----------|---------|
| DxEM | PASS |
| AC-Proxy | PASS |
| MAB-Proxy | FAIL |
| C2 | FAIL |
| ACov | PASS |
| CGA-Bench | PASS |

**PASS**: DxEM, AC-Proxy, ACov, CGA-Bench
**FAIL**: MAB-Proxy, C2

### Agent Trace (Key Actions)

1. **[DEVIATION]** `order_imaging_electrocardiogram` (severity: moderate)
   Action outside allowed set without justification: order_imaging_electrocardiogram
2. **[DEVIATION]** `order_lab_thyroid_function` (severity: moderate)
   Action outside allowed set without justification: order_lab_thyroid_function
3. **[DEVIATION]** `assess_mental_status` (severity: moderate)
   Action outside allowed set without justification: assess_mental_status
4. **[DEVIATION]** `order_lab_d_dimer` (severity: moderate)
   Action outside allowed set without justification: order_lab_d_dimer
5. **[DEVIATION]** `assess_hemodynamic_stability` (severity: moderate)
   Action outside allowed set without justification: assess_hemodynamic_stability
6. **[DEVIATION]** `request_consultation` (severity: moderate)
   Action outside allowed set without justification: request_consultation
7. **[DEVIATION]** `assess_rhythm_control_indication` (severity: moderate)
   Action outside allowed set without justification: assess_rhythm_control_indication
8. **[DEVIATION]** `assess_rate_control_indication` (severity: moderate)
   Action outside allowed set without justification: assess_rate_control_indication
   ... and 10 more violations

**Sub-construct scores:**
- C1_path_selection: 0.375
- C2_mandatory_completion: 0.600
- C3_forbidden_avoidance: 1.000
- C4_timing_compliance: 0.800
- C5_sequence_integrity: 1.000

### What This Case Demonstrates

- Multiple models fail on this scenario, suggesting inherent difficulty rather than model-specific weakness.
