# Case Study 3: contrast_aki_prevention_basic_27B_0

### Scenario Summary

Scenario **contrast_aki_prevention_basic** (domain: aki) evaluated with model 27B. This episode had 1 violation(s) with types: WITHIN.

### Evaluator Verdicts

| Evaluator | Verdict |
|-----------|---------|
| DxEM | PASS |
| AC-Proxy | FAIL |
| MAB-Proxy | FAIL |
| C2 | PASS |
| ACov | FAIL |
| CGA-Bench | PASS |

**PASS**: DxEM, C2, CGA-Bench
**FAIL**: AC-Proxy, MAB-Proxy, ACov

### Agent Trace (Key Actions)

1. **[DEVIATION]** `assess_baseline_estimated_glomerular_filtration_rate` (severity: moderate)
   Action outside allowed set without justification: assess_baseline_estimated_glomerular_filtration_rate
2. **[DEVIATION]** `assess_hemodynamic_profile` (severity: moderate)
   Action outside allowed set without justification: assess_hemodynamic_profile
3. **[DEVIATION]** `assess_aki_risk_factors` (severity: moderate)
   Action outside allowed set without justification: assess_aki_risk_factors
4. **[DEVIATION]** `order_lab_urinalysis` (severity: moderate)
   Action outside allowed set without justification: order_lab_urinalysis
5. **[DEVIATION]** `order_lab_abg` (severity: moderate)
   Action outside allowed set without justification: order_lab_abg
6. **[DEVIATION]** `order_lab_fena` (severity: moderate)
   Action outside allowed set without justification: order_lab_fena
7. **[DEVIATION]** `order_urinalysis` (severity: moderate)
   Action outside allowed set without justification: order_urinalysis
8. **[DEVIATION]** `monitor_potassium` (severity: moderate)
   Action outside allowed set without justification: monitor_potassium
   ... and 9 more violations

**Sub-construct scores:**
- C1_path_selection: 0.571
- C2_mandatory_completion: 0.800
- C3_forbidden_avoidance: 1.000
- C4_timing_compliance: 0.800
- C5_sequence_integrity: 1.000

### What This Case Demonstrates

- High evaluator disagreement reveals that different evaluation criteria capture fundamentally different aspects of clinical quality.
- Multiple models fail on this scenario, suggesting inherent difficulty rather than model-specific weakness.
