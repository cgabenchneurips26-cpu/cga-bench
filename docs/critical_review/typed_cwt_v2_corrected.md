# Typed CwT (Option C) — Corrected Hero Numbers

**Date**: 2026-04-26 (corrected from earlier draft)
**Severity**: paper-level decision — Option C has a major η² narrative cost
**Supersedes**: portions of `evaluator_audit_VII.md` §Robustness check table that
used inverted FA semantics

---

## Bug discovered in earlier hero recompute

`scripts/experiments/recompute_hero_numbers.py` originally used
`not ep["v4_hard"]` for the TCC-fail half of the FA condition. Empirical check
proves this inverts FA semantics:

```
v4_hard=True ⟺ n_viols>0 ⟺ TCC FAILS the episode (8553 episodes)
v4_hard=False ⟺ n_viols=0 ⟺ TCC PASSES the episode (8391 episodes)
```

Therefore FA = `evaluator_pass AND ep["v4_hard"]==True` (no `not`).

`exp_strict_consensus_fa.py:39,45,51` was correct from the start; my earlier
recompute was wrong by inversion. The macro `\strictFAThree{6.6}` (1118
episodes) is the **correct** strict 3-way FA rate.

`recompute_hero_numbers.py` is now fixed (commit forthcoming).

---

## Corrected hero numbers

### A. Strict consensus FA (TCC fail + evaluator pass)

| Family | Original | Typed | Δ (pp) | Δ (relative) |
|---|---:|---:|---:|---:|
| TOM ∩ ASC ∩ CwT  (paper's `\consensusFARate{11.6}`) | 11.56% (1959) | **21.79%** (3692) | +10.23 | +88.5% |
| ASC ∩ PAF ∩ CwT  (paper's `\strictFAThree{6.6}`)    | **6.60%** (1118) | **13.56%** (2298) | +6.96  | +105.5% |
| ASC ∩ PAF ∩ CwT ∩ TOM (paper's `\strictFAFour{6.6}`)| 6.60%  (1118) | 13.56%  (2298) | +6.96 | +105.5% |
| TCC pass rate | 49.52% | 49.52% | 0 | 0 |

### B. Variance decomposition — paper's CRES-5 macros (n=14826)

| Metric | Original (paper) | Typed | Effect |
|---|---:|---:|---|
| `\cresFiveEtaSq{}` (η²(eval)) | 0.0725 | **0.0321** | -55.7% |
| `\cresFiveEtaRun{}` (η²(run)) | 0.0515 | 0.0515 | **invariant** |
| Ratio η²(eval) / η²(run) | **1.41×** | **0.62×** | **DIRECTIONAL REVERSAL** |
| Cohen's f² (`\cresFiveCohenF{0.078}`) | needs recompute | needs recompute | TBD |

### C. Pair ranking reversal

| Metric | Original | Typed | Δ |
|---|---:|---:|---:|
| Pair reversal rate | 46.31% | 44.27% | -2.04 pp |
| n_comparisons | 12,267 | 11,736 | -531 |

η²(run) = 0.0515 invariance proof: η²(run) is computed over the cga_pass column
only (the within-(scenario,model) deviations of TCC verdicts), and `c2_pass`
does not enter that computation. Changing C2 to typed shifts only the C2 column
of the verdict matrix, leaving CGA-Bench's run-variance untouched.

---

## What this means for the paper

### Hero claim: "11.6% false-accept" (`\consensusFARate{11.6}`)

- Original (TOM ∩ ASC ∩ CwT, with degenerate TOM): 11.56%
- Typed: **21.79%** (almost double)

The headline "11.6%" already includes degenerate TOM. Strict non-degenerate is
6.6% (paper's `\strictFAThree`). Under typed CwT:
- Degenerate consensus → 21.8%
- Strict non-degenerate → 13.6%

If the paper presents typed CwT as primary, the headline shifts. Honest
disclosure of the CwT-correction strengthens the methodological argument; the
larger FA rate is consistent with "stricter compliance criterion catches more
false accepts."

### Variance decomposition narrative

The paper currently argues:
> Evaluator disagreement (η²=0.072) dominates run-to-run noise (η²=0.052)
> by a factor of 1.4×, supporting the claim that evaluator choice — not
> stochastic decoding — is the primary source of disagreement.

Under typed CwT this **reverses**: η²(eval) = 0.032 < η²(run) = 0.052
(ratio 0.62×). The cleaner C2 verdict is more reproducible across evaluators
because the DEVIATION-driven authoring confound is removed, but run-to-run
TCC noise remains the same.

This means **Option C has a paper-narrative cost**, not just a macro shift.

### Three honest paths forward

1. **Option C-strict** — adopt typed CwT as primary throughout. Rewrite the
   variance-decomposition section to: *"Under the source-grounded typed
   compliance criterion, evaluator disagreement and run-to-run noise are
   comparable in magnitude (η²(eval) = 0.032 vs η²(run) = 0.052). The
   evaluator-disagreement effect under the older overall-compliance criterion
   (η²(eval) = 0.072) was inflated by an authoring-dependent confound that
   typed compliance eliminates."*
   Cost: weakens the headline VPC argument.
   Benefit: methodological rigor; removes one-line confound.

2. **Option C-mixed** — keep original CwT as primary for variance decomposition
   and rank-correlation analyses (where evaluator-pool consistency matters),
   adopt typed CwT for FA-rate claims (where DEVIATION confound matters most).
   Cost: inconsistent C2 definition across the paper.
   Benefit: preserves headline VPC.
   Risk: reviewer attack on inconsistency.

3. **Option C-sensitivity** — keep original CwT primary throughout, add a
   §Robustness Check appendix that reports typed CwT as a sensitivity analysis.
   Cost: typed numbers stay in the appendix.
   Benefit: minimal narrative disruption; fully honest.

**My recommendation**: Option C-sensitivity for v1 submission. Promote typed
CwT to primary for v2/camera-ready once the variance narrative has been
rewritten. Reasoning:
- The reversal is a load-bearing finding for the η² argument.
- Reviewers can attack either C2 definition; we should be ready to defend whichever we ship as primary.
- §Robustness disclosure pre-empts the "you used overall compliance for CwT?"
  reviewer comment without forcing a same-week paper rewrite.

---

## Macros to update if Option C-strict

Direct paper macro updates (strict adoption path):

```
% paper/auto_numbers.tex
\newcommand{\consensusFATotal}{1959}      → 3692     (+88.5%)
\newcommand{\consensusFARate}{11.6}        → 21.8     (+10.2 pp)
\newcommand{\strictFAThree}{6.6}           → 13.6     (+7.0 pp)
\newcommand{\strictFAThreeCount}{1118}     → 2298
\newcommand{\strictFAFour}{6.6}            → 13.6
\newcommand{\strictFAFourCount}{1118}      → 2298
\newcommand{\etaEvaluator}{0.078}          → 0.038    (close to typed 0.0377; v6-style decomp)
\providecommand{\cresFiveEtaSq}{0.072}     → 0.032    (CRES-5 4-evaluator decomp)
\providecommand{\cresFiveEtaRun}{0.0515}   → 0.0515   (invariant)
\providecommand{\cresFiveVPC}{0.072}       → 0.032
```

Macros NOT to touch (verdict-decomposition independent):
- `\bsrCondAC{57.1}`, `\bsrCondMAB{60.3}` (BSR conditional, depend on TCC only)
- `\etaRun{<0.001}` (v6-style binary η²(run), already unchanged)
- `\reversalRate{75.0}` (different metric; need separate verification)
- `\strictFACriticalPct{6.2}` (severity-conditional; needs typed recompute)

---

## Files corrected

- `scripts/experiments/recompute_hero_numbers.py` — fixed `not ep["v4_hard"]`
  → `ep["v4_hard"]` for FA condition
- `evidence_pack/analysis/hero_numbers_typed_vs_original.json` — regenerated
  with correct semantics; now also reports TOM∩ASC∩CwT (paper's headline
  consensus)

## Files needing update

- `docs/critical_review/evaluator_audit_VII.md` §Robustness check table —
  update the "Strict 4-way consensus FA" row from 11.60%→15.11% to
  6.60%→13.56% (the inverted-FA confusion was inherited from
  recompute_hero_numbers.py)
- Memory `project_typed_cwt_recompute.md` — same correction
