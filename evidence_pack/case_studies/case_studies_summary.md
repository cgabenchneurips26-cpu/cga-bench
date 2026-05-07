# Case Studies: Maximum Evaluator Disagreement

## Case 1: contrast_aki_prevention_basic_27B_0

- **Scenario**: contrast_aki_prevention_basic
- **Domain**: aki
- **Model**: 27B
- **Disagreement**: 3 pass / 3 fail

| Evaluator | Verdict |
|-----------|---------|
| DxEM | PASS |
| AC-Proxy | FAIL |
| MAB-Proxy | FAIL |
| C2 | PASS |
| ACov | FAIL |
| CGA-Bench | PASS |

**Analysis**: PASS evaluators: DxEM, C2, CGA-Bench
FAIL evaluators: AC-Proxy, MAB-Proxy, ACov

## Case 2: contrast_aki_prevention_basic_27B_1

- **Scenario**: contrast_aki_prevention_basic
- **Domain**: aki
- **Model**: 27B
- **Disagreement**: 3 pass / 3 fail

| Evaluator | Verdict |
|-----------|---------|
| DxEM | PASS |
| AC-Proxy | FAIL |
| MAB-Proxy | FAIL |
| C2 | PASS |
| ACov | FAIL |
| CGA-Bench | PASS |

**Analysis**: PASS evaluators: DxEM, C2, CGA-Bench
FAIL evaluators: AC-Proxy, MAB-Proxy, ACov

## Case 3: contrast_aki_prevention_basic_27B_2

- **Scenario**: contrast_aki_prevention_basic
- **Domain**: aki
- **Model**: 27B
- **Disagreement**: 3 pass / 3 fail

| Evaluator | Verdict |
|-----------|---------|
| DxEM | PASS |
| AC-Proxy | FAIL |
| MAB-Proxy | FAIL |
| C2 | PASS |
| ACov | FAIL |
| CGA-Bench | PASS |

**Analysis**: PASS evaluators: DxEM, C2, CGA-Bench
FAIL evaluators: AC-Proxy, MAB-Proxy, ACov

## Case 4: gi_bleeding_upper_basic_120B_0

- **Scenario**: gi_bleeding_upper_basic
- **Domain**: gi_bleeding
- **Model**: 120B
- **Disagreement**: 3 pass / 3 fail

| Evaluator | Verdict |
|-----------|---------|
| DxEM | PASS |
| AC-Proxy | PASS |
| MAB-Proxy | FAIL |
| C2 | FAIL |
| ACov | PASS |
| CGA-Bench | FAIL |

**Analysis**: PASS evaluators: DxEM, AC-Proxy, ACov
FAIL evaluators: MAB-Proxy, C2, CGA-Bench
Key: DxEM passes (diagnosis correct) but CGA-Bench fails (constraint violations detected). This illustrates that correct diagnosis alone does not guarantee safe treatment.
AC-Proxy passes on coverage threshold but MAB-Proxy fails on F1, suggesting actions were taken but not precisely matched.

## Case 5: gi_bleeding_upper_basic_120B_1

- **Scenario**: gi_bleeding_upper_basic
- **Domain**: gi_bleeding
- **Model**: 120B
- **Disagreement**: 3 pass / 3 fail

| Evaluator | Verdict |
|-----------|---------|
| DxEM | PASS |
| AC-Proxy | PASS |
| MAB-Proxy | FAIL |
| C2 | FAIL |
| ACov | PASS |
| CGA-Bench | FAIL |

**Analysis**: PASS evaluators: DxEM, AC-Proxy, ACov
FAIL evaluators: MAB-Proxy, C2, CGA-Bench
Key: DxEM passes (diagnosis correct) but CGA-Bench fails (constraint violations detected). This illustrates that correct diagnosis alone does not guarantee safe treatment.
AC-Proxy passes on coverage threshold but MAB-Proxy fails on F1, suggesting actions were taken but not precisely matched.
