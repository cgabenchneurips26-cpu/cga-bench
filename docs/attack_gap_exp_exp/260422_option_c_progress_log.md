# Option C: Public Audit Artifact — Progress Log

**Date**: 2026-04-22
**Status**: ALL COMPLETE (C1/C2/C3/C6/C5/Cross-step)

---

## Overview

Option C amplifies Contribution 4 from "a CLI + 6 worked examples" into a richer audit artifact with:
- **C1**: Alternative evaluator wrappers (extensibility demo)
- **C2**: Repair-distance d_G correlation analysis
- **C3**: Blindspot cluster grid (domain x constraint_type)
- **C6**: Audit-guided evaluator selection experiment
- **C5**: Paper integration (Appendix E)
- **Cross-step**: 8-angle verification matrix

---

## C1: Alternative Evaluator Wrappers — COMPLETE

**Tests**: 19/19 passed
**Date completed**: 2026-04-22 ~14:55 UTC

### What was built
4 metric-threshold evaluators demonstrating "any evaluator" extensibility:

| Wrapper | Metric Field | Threshold | Pi-class Hypothesis |
|---------|-------------|-----------|---------------------|
| ActionCoverageEvaluator | action_coverage | >= 0.8 | aset |
| C2ScoreEvaluator | c2_score | >= 0.5 | nord |
| MABF1Evaluator | mab_f1 | >= 0.5 | aset |
| AlwaysTrueEvaluator | (none) | always True | trivial |

### Files
- `audit/wrappers/__init__.py`
- `audit/wrappers/metric_evaluators.py` (~100 LOC)
- `audit/wrappers/calibration.yaml` (~20 lines)
- `tests/test_audit/test_wrappers.py` (~80 LOC)

### Key decision
Original plan: wrap 8 external benchmark adapters. **Pivoted** because adapters lack native scoring (`native_score()` only on 2/11). Using verdict_matrix metric columns is more honest and demonstrates the same extensibility pattern.

---

## C2: Repair-Distance d_G as Audit Column — COMPLETE

**Tests**: 22/22 passed
**Date completed**: 2026-04-22

### What was built
- `audit/metrics/repair.py` — d_G proxy loader, Pearson correlation, monotonicity violations, proxy statistics
- `tests/test_audit/test_repair_distance.py` — 22 tests across 5 classes
- Integration into `evaluator_audit.py` as Step 5

### Critical Discovery: n_viols Proxy Direction

**Initial assumption (WRONG)**: n_viols=0 implies safe, higher n_viols implies more harmful, rho should be negative.

**Actual data relationship**:
```
v4_hard=True  (SAFE):    7,175 episodes → mostly n_viols > 0
v4_hard=False (HARMFUL):  7,651 episodes → mostly n_viols = 0
Pearson rho(v4_hard, n_viols) = +0.7383 (POSITIVE)
```

**Root cause**: n_viols counts commission/timing violations only, NOT omissions. Episodes with n_viols=0 are typically from agents that did NOTHING (no actions → no commissions) but FAILED because they omitted mandatory actions. Active agents that take actions accumulate some commission violations (n_viols > 0) but also complete mandatory actions, so they PASS v4_hard.

**Fix applied**:
1. Updated docstrings to document positive correlation
2. Flipped monotonicity check direction
3. Replaced strict compliance invariant with informational proxy statistics
4. Rewrote all 6 failing test expectations

### Key metrics
| Evaluator | rho(verdict, n_viols) | Monotonicity |
|-----------|-----------------------|--------------|
| v4_hard | +0.7383 | < 25% violations |
| dxem | 0.0000 | 0 informative pairs (constant) |
| AlwaysTrue | 0.0000 | 0 informative pairs (constant) |

### DxEM is constant
DxEM returns True for ALL 14,826 W8-filtered episodes. This means:
- rho = 0.0 (zero variance → undefined, returns 0)
- No informative pairs for monotonicity (all verdicts identical)
- BSR = fraction of v4_hard=False episodes (~51.6%)

---

## C3: Blindspot Cluster Grid — COMPLETE

**Tests**: 34/34 passed
**Date completed**: 2026-04-22

### What was built
- `audit/metrics/blindspot.py` — domain extraction, constraint-type priority, grid computation, markdown rendering
- `tests/test_audit/test_blindspot_clusters.py` — 34 tests across 4 classes
- Integration into `evaluator_audit.py` as Step 6

### Domain Extraction
Maps scenario_id prefix to 22 canonical domains covering all 25 CPG graphs:
```
sepsis, chest_pain, stroke, heart_failure, aki, dka, atrial_fibrillation,
copd, pulmonary_embolism, gi_bleeding, pneumonia, hypertensive_emergency,
anaphylaxis, asthma, meningitis, acls, epilepticus, toxicology,
transfusion, burn, obstetric, agitation, pediatric, other
```

### Constraint Type Priority
Each episode assigned to exactly ONE primary constraint type:
```
FORBIDDEN > WITHIN > BEFORE > NONE
```
This ensures marginal consistency: grid cell BSR weighted sum == scalar BSR.

### Marginal Consistency Verification
**All 6 core shims verified** (10^-4 tolerance):
- grid_marginal_bsr == scalar_bsr for dxem, ac_proxy, mab_proxy, c2_shim, acov_shim, v4_hard

### V4Hard Self-Reference
V4Hard grid: **uniformly green** (0% BSR in every cell) — confirms self-reference consistency.

### AlwaysTrue Negative Control
AlwaysTrue grid: **has red cells** (>20% BSR) — confirms harness detects garbage evaluators.

---

## Evaluator Audit: Extended to 6 Steps

`scripts/audit/evaluator_audit.py` now runs:
1. Pi-class classification (separating pairs)
2. BSR vs CGA-Bench reference
3. Bayes-error floor lookup
4. False-accept witnesses
5. **NEW** Repair-distance correlation (rho + monotonicity)
6. **NEW** Blindspot cluster grid (heatmap)

CLI output now includes rho(d_G) and red-cell count.
Markdown report includes Steps 5 and 6 sections.

---

## C6: Audit-Guided Evaluator Selection — COMPLETE

**Tests**: 20/20 passed
**Date completed**: 2026-04-22

### What was built
- `audit/metrics/selection.py` — binary_tau (phi coefficient), pi-class distance, selection experiment
- `scripts/experiments/exp_audit_guided_selection.py` — CLI with JSON + LaTeX macro output
- `tests/test_audit/test_audit_guided_selection.py` — 20 tests across 3 classes

### Experiment Results (6 core shims, 15 pairs)

**Pi-class classification**:
| Evaluator | Pi-class |
|-----------|----------|
| dxem | term |
| mab_proxy | term |
| c2_shim | aset |
| ac_proxy | nctx |
| acov_shim | nctx |
| v4_hard | nctx |

**Key findings**:
- Same-class mean tau (non-degenerate): **0.4729** (4 pairs)
- Cross-class mean tau (non-degenerate): **0.1915** (11 pairs)
- **Separation confirmed**: same-class evaluators agree MORE than cross-class
- Audit-guided pair: ac_proxy (nctx) vs dxem (term), tau=0.0000, distance=3
- 5 degenerate pairs (involving constant evaluators DxEM/mab_proxy → tau=0)

### Interpretation
Pi-class classification predicts evaluator independence: evaluators in the same pi-class produce correlated verdicts (tau ~0.47), while cross-class evaluators are more independent (tau ~0.19). This makes the audit actionable for ensemble construction.

### Output artifacts
- `evidence_pack/audit/c6_audit_guided_selection.json` — full results
- `evidence_pack/audit/c6_selection_macros.tex` — LaTeX macros

---

## Full Regression: 196/196 Passed

> The 172 count below was the snapshot at Option C completion (6 files). Current total is **196** across 10 files after EVP additions and test refactoring.

```
tests/test_audit/test_shims.py                     37 passed  (Option B)
tests/test_audit/test_separating_pairs.py          14 passed  (Option B)
tests/test_audit/test_compute_bayes_error.py        9 passed  (Option B)
tests/test_audit/test_evaluator_audit.py           21 passed  (Option B)
tests/test_audit/test_wrappers.py                  19 passed  (C1)
tests/test_audit/test_repair_distance.py           22 passed  (C2)
tests/test_audit/test_blindspot_clusters.py        34 passed  (C3)
tests/test_audit/test_audit_guided_selection.py    20 passed  (C6)
tests/test_audit/test_violation_count_shim.py      13 passed  (EVP)
tests/test_audit/test_llm_judge_shim.py             7 passed  (EVP)
─────────────────────────────────────────────────────────
TOTAL                                             196 passed
```

---

## C5: Paper Integration — COMPLETE

**Date completed**: 2026-04-22

### What was changed

**`paper/main_final_v17.tex`**:
- §4.4: "four-step" → "six-step" evaluator runbook
- Added Steps 5 (repair-distance correlation) and 6 (blindspot cluster grid) to the enumeration
- Added paragraph on structural diagnostics: rho=0.74 for TCC, blindspot grid localisation, C6 selection experiment results (same-class tau=0.4729 vs cross-class tau=0.1915)
- Macro loading: added `\IfFileExists` for `c6_selection_macros.tex`

**`paper/appendix.tex`**:
- "Four-Step Runbook" → "Six-Step Runbook" (section title + intro)
- Added Step 5 paragraph: repair-distance correlation (rho, monotonicity-violation rate, n_viols positive correlation explanation)
- Added Step 6 paragraph: blindspot cluster grid (domain × constraint-type, marginal consistency, colour coding)
- Added subsection "Audit-Guided Evaluator Selection" (App D.6) with result paragraph and audit-guided pair analysis
- Updated "Adding a New Evaluator" to reference six-step runbook

**`evidence_pack/audit/c6_selection_macros.tex`**:
- Harmonized `\newcommand` → `\providecommand` (consistent with audit_macros.tex)
- Escaped underscores in evaluator names (ac\_proxy)

**`scripts/experiments/exp_audit_guided_selection.py`**:
- Updated macro emission: `\newcommand` → `\providecommand`
- Added `_tex_escape()` helper for LaTeX-safe evaluator names

### Verification
- LaTeX compiles with 0 errors, 0 undefined references for new labels (3rd pass clean)
- All 196 audit tests pass (10 files; was 172 at Option C completion, +24 from EVP and refactoring)
- Pre-existing `tab:bayes-error` undefined ref is NOT from our changes

---

## Cross-Step: 8-Angle Verification Matrix — COMPLETE

**Date completed**: 2026-04-22

| # | Angle | Check | Result | Status |
|---|-------|-------|--------|--------|
| 1 | d_G compliance | rho(v4_hard, n_viols) positive | rho = +0.7383, positive_correlation = True | PASS |
| 2 | Blindspot marginal | grid sum == scalar BSR per shim | 6/6 match (max diff = 4.7e-5) | PASS |
| 3 | Regression | Option B+C+EVP tests all pass | 196/196 passed (10 files) | PASS |
| 4 | Negative control | AlwaysTrue → BSR ~0.48, pi=term, red cells>0 | BSR=0.5161, pi=term, 17 red cells | PASS |
| 5 | C6 null control | same-class tau > cross-class tau | 0.4729 > 0.1915, separation=True | PASS |
| 6 | Monotonicity | v4_hard violation rate < 0.25 | 0/2481 = 0.0000 | PASS |
| 7 | Paper SSoT | no hardcoded digits in new sections | 0 new bare digits (3 pre-existing in examples) | PASS |
| 8 | Paper page limit | PDF compiles, main body within limit | 48pp total, new text +3 sentences in §4.4 | PASS |

**All 8 angles verified. Option C is complete.**

---

## Remaining Work

None — Option C fully complete.

---

## Files Summary (Option C)

### New Files (C1+C2+C3+C6)
| File | LOC | Step |
|------|-----|------|
| `audit/wrappers/__init__.py` | 5 | C1 |
| `audit/wrappers/metric_evaluators.py` | 100 | C1 |
| `audit/wrappers/calibration.yaml` | 20 | C1 |
| `audit/metrics/__init__.py` | 5 | C2 |
| `audit/metrics/repair.py` | 210 | C2 |
| `audit/metrics/blindspot.py` | 253 | C3 |
| `audit/metrics/selection.py` | 200 | C6 |
| `scripts/experiments/exp_audit_guided_selection.py` | 95 | C6 |
| `tests/test_audit/test_wrappers.py` | 80 | C1 |
| `tests/test_audit/test_repair_distance.py` | 155 | C2 |
| `tests/test_audit/test_blindspot_clusters.py` | 197 | C3 |
| `tests/test_audit/test_audit_guided_selection.py` | 165 | C6 |

### Modified Files
| File | Change |
|------|--------|
| `audit/shims/__init__.py` | +4 wrapper entries in SHIM_REGISTRY |
| `scripts/audit/evaluator_audit.py` | +step5 (d_G) +step6 (grid), 4→6 step |
| `paper/main_final_v17.tex` | §4.4 four→six step, +Steps 5-6, +C6 paragraph, +macro load |
| `paper/appendix.tex` | Four→Six-Step Runbook, +Steps 5-6, +C6 subsection |
| `evidence_pack/audit/c6_selection_macros.tex` | newcommand→providecommand, underscore escapes |
| `scripts/experiments/exp_audit_guided_selection.py` | newcommand→providecommand, +_tex_escape |
