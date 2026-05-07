# Option B: Evaluator Audit Harness — Completion Report

**Date**: 2026-04-22
**Status**: COMPLETE (later extended to 6-step in Option C)
**Tests**: 196/196 (10 files: Option B core + Option C + EVP)

---

## Summary

Option B delivers Contribution 4 of the CGA-Bench paper: a reusable evaluator audit harness that any future evaluator can plug into. Originally 4 steps; later extended to 6 steps in Option C (+ repair-distance correlation, blindspot cluster grid).

## Architecture

```
audit/
  evaluator_base.py       # Evaluator ABC + EvaluatorMeta
  separating_pairs.py     # 20 hand-curated episode pairs (4 cases × 5 pairs)
  shims/
    __init__.py           # SHIM_REGISTRY (6 core + 4 wrappers)
    _verdict_cache.py     # Singleton W8-filtered verdict_matrix loader
    dxem.py / ac_proxy.py / mab_proxy.py / c2_shim.py / acov_shim.py / v4_hard.py
scripts/audit/
  evaluator_audit.py      # CLI: 6-step runbook
  build_index.py          # INDEX.md generator
```

## Original 4-Step Runbook (Steps 1–4, later extended to 6 in Option C)

### Step 1: Pi-class Classification
- Uses 20 separating pairs across 4 cases (case_i → case_iv)
- Maps evaluator to projection class: term / aset / nord / nctx
- **Key result**: DxEM → term (coarsest), ACov → nctx (finest)

### Step 2: Blind-Spot Rate (BSR)
- Disagreement rate vs v4_hard reference on 14,826 W8-filtered episodes
- Formula: BSR = n_disagree / n_total
- Breaks down into false_accept_rate + false_reject_rate

### Step 3: Bayes-Error Floor
- Plug-in values from evidence_pack/theorem_v2/bayes_error_macros.tex
- Per pi-class: term=0.436, aset=0.024, nord=0.003, nctx=0.003

### Step 4: False-Accept Witnesses
- Top-K episodes where evaluator says PASS but v4_hard says FAIL
- Sorted by n_viols descending (most dangerous first)
- Domain distribution reported

## 6 Core Shims Audited

| Shim | Family | Pi-class | BSR | Description |
|------|--------|----------|-----|-------------|
| dxem | TOM | term | high | Diagnosis-exact-match |
| ac_proxy | ASC | nctx | low | Action coverage threshold |
| mab_proxy | PAF | term | medium | MAB F1 threshold |
| c2_shim | CwT | aset | medium | Constraint satisfaction score |
| acov_shim | ACov | nctx | low | Action coverage continuous |
| v4_hard | TCC | nctx | 0.0 | Reference (self-agreement) |

## Gate Verification (Pre-Option C)

| Gate | Check | Result |
|------|-------|--------|
| Gate 1a | All 69 Option B tests pass | PASS |
| Gate 1b | Bayes macros regeneration (core values) | PASS |
| Gate 2 | Cold-read §4.4 paper review | PASS (minor revisions) |
| Gate 3 | Clinician validation path assessment | PASS |

## Paper Integration
- **Section 4.4**: Evaluator audit methodology
- **Appendix D**: Per-evaluator reports
- **evidence_pack/audit/**: Report JSONs + audit_macros.tex

---

## Files Created (Option B)

| File | LOC | Purpose |
|------|-----|---------|
| `audit/evaluator_base.py` | ~50 | Evaluator ABC |
| `audit/separating_pairs.py` | ~80 | Pair catalogue loader |
| `audit/shims/__init__.py` | ~30 | Registry |
| `audit/shims/_verdict_cache.py` | ~120 | Singleton data loader |
| `audit/shims/{6 shim files}` | ~150 | Core evaluator shims |
| `scripts/audit/evaluator_audit.py` | ~470 | 6-step CLI |
| `scripts/audit/build_index.py` | ~80 | INDEX.md generator |
| `tests/test_audit/test_shims.py` | ~150 | Shim tests |
| `tests/test_audit/test_separating_pairs.py` | ~120 | Pair catalogue tests |
