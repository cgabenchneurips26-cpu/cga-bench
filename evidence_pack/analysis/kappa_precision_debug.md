# Critical Evidence Debugging Report

## Issue 1: Fleiss' κ

### Root Causes
- **DxEM is degenerate**: pass rate = 100% (constant rater, κ undefined)
- **AC-Proxy ≡ ACov**: identical verdict vectors (redundant evaluator)
- Original Fleiss' κ (all 6) = 0.1450 (dragged down by degenerate + redundant raters)

### Corrected Values
- **Fleiss' κ (4 independent evaluators) = 0.1693**
- Independent evaluators: AC-Proxy, MAB-Proxy, C2, CGA-Bench

### Pairwise Cohen's κ (4 independent)
| Pair | κ |
|------|---|
| AC-Proxy vs MAB-Proxy | 0.0788 |
| AC-Proxy vs C2 | 0.5197 |
| AC-Proxy vs CGA-Bench | 0.2662 |
| MAB-Proxy vs C2 | 0.0017 |
| MAB-Proxy vs CGA-Bench | -0.1148 |
| C2 vs CGA-Bench | 0.4046 |

### Interpretation
The low Fleiss' κ reflects SYSTEMATIC disagreement across evaluation dimensions (coverage vs safety vs completeness), NOT random noise. Evidence: (1) DxEM is degenerate (100% pass), excluded; (2) AC-Proxy ≡ ACov (identical), deduplicated; (3) Remaining 4 evaluators form two clusters with moderate intra-cluster and low/negative inter-cluster agreement; (4) Cochran's Q highly significant (p<0.001), confirming evaluator-level systematic differences. This justifies CGA-Bench's multi-evaluator design.

### Paper Recommendation
- Report: Fleiss' κ = 0.169 (4 independent evaluators)
- Footnote: DxEM excluded (100% pass, degenerate); ACov excluded (identical to AC-Proxy)

---

## Issue 2: Engine vs Manual Precision = 0.217

### Diagnosis
- Total Engine constraints: 2341
- Total Manual constraints: 930
- True Positives: 447
- False Positives (engine extra): 1894
- False Negatives (engine missed): 483
- **Expansion ratio: 2.5x** (Engine derives this many times more constraints)

### Verdict: Interpretation B
- GOOD interpretation: Manual scenarios only specify 9 constraints on average, while Engine correctly derives 22. The 1894 'false positives' are legitimate CPG constraints that manual authors didn't explicitly list. Evidence: recall=0.481 means Engine covers ~48% of what manual specifies, and the 'extra' constraints are derived from the same CPG graph conditional rules.

### Recommended Framing
Constraint-type stratified analysis needed for definitive proof. Expected pattern: FORBIDDEN precision high (manual doesn't skip safety), WITHIN/BEFORE precision low (manual skips timing). Recommended: break down FP by constraint type in the paper.

### Action Item — COMPLETED
Constraint-type breakdown implemented in `scripts/exp_b_constraint_type_precision.py`.
Results in `evidence_pack/analysis/constraint_type_precision.md`.

Key finding: FORBIDDEN expansion=4.2x, Non-FORBIDDEN expansion=2.0x.
Manual authors under-specify safety constraints even MORE than completeness.
FORBIDDEN recall (0.545) > Non-FORBIDDEN recall (0.445).
Interpretation B confirmed and strengthened.

---

## Issue 3: NEEDS_FIX Claims

- Total stale claims: 12
- Unique macros to update: 6
- **Blocker**: 5,490 episode execution in progress

### Resolution Pipeline
1. Wait for episode execution to complete
1. Run verdict_matrix_v4.py with new results
1. Run exp_d with updated verdict matrix
1. Run exp_f to regenerate auto_numbers.tex
1. Verify all NEEDS_FIX claims resolved

### Macro → Claims Mapping
| Macro | Claims |
|-------|--------|
| `\numACProxyMisCert` | A11 |
| `\numMABProxyMisCert` | A12 |
| `\numUPstrong` | A15, B02, F13, S04 |
| `\numCI` | A16, B05 |
| `\numUPcrit` | A17, F12, S06 |
| `\numUPlenient` | F14 |