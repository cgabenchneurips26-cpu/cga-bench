# Orthogonal Perturbation Suite — Results

**Conformant base traces**: 74
**Seed**: 42

## Detection Rate Table

| Perturbation | n | DxEM | AC-Proxy | MAB | C2 | CGA-Bench |
|---|---|---|---|---|---|---|
| Null (control) | 74 | 0% | 34% | 86% | 92% | 7% |
| WITHIN-only | 50 | 0% | 0% | 0% | 0% | 96% |
| BEFORE-only | 0 | 0% | 0% | 0% | 0% | 0% |
| FORBID-only | 62 | 0% | 0% | 2% | 0% | 100% |
| MUST-omit | 62 | 0% | 53% | 6% | 8% | 100% |

## Key Findings

- **WITHIN-only**: 50 pairs — AC-Proxy 0% detection, CGA-Bench 96% detection
- **BEFORE-only**: 0 pairs — AC-Proxy 0% detection, CGA-Bench 0% detection

## Interpretation

WITHIN and BEFORE perturbations preserve the action multiset, so action-set evaluators (AC-Proxy, MAB-Proxy) cannot detect them. Only CGA-Bench (typed conformance) catches all violation types. This constructively proves Proposition 1: outcome-equivalent traces can have arbitrarily different safety profiles.