# main_final_v18.tex Hardcoded Numbers Audit

**Date**: 2026-05-01
**Scope**: `paper/main_final_v18.tex` body text (lines 258-510, excluding bibliography and preamble macro definitions)
**Method**: Automated regex scan + manual cross-check against `auto_numbers.tex` macro inventory

---

## Summary

| Severity | Count | Description |
|----------|:-----:|-------------|
| P0 | 6 | Computed statistic with **no macro defined** anywhere |
| P1 | 9 | Macro **exists** but hardcoded value used instead |
| P2 | 5 | Structural/design constant (arguably acceptable) |
| **Total** | **20** | |

---

## P0: Computed Statistics With No Macro

These numbers appear in the paper body as bare literals. No corresponding `\providecommand` or `\newcommand` exists in any `.tex` file. If the underlying data changes, these will silently go stale.

### P0-1. Typed-CwT eta-squared (manual 706-scenario subset)
- **Line 465**: `$\eta^{2}_{\mathrm{eval}}{=}0.059$`
- **Line 465**: `$\eta^{2}_{\mathrm{run}}{=}0.076$`
- **Context**: "Removing the deviation channel reverses the variance ordering on the manual 706-scenario subset ($\eta^2_{eval}=0.059$ vs $\eta^2_{run}=0.076$, $N=16,944$)"
- **Risk**: HIGH. These are the typed-CwT variant eta values for the Phase A 8-model manual-only subset. The *Phase B* typed-CwT values DO have macros (`\cresFiveEtaSqTyped{0.100}`, `\cresFiveEtaRunTyped{0.088}`), but this Phase A subset has none.
- **Fix**: Define `\typedCwtManualEtaEval{0.059}` and `\typedCwtManualEtaRun{0.076}`.

### P0-2. Cell-level pair-reversal rate (Phase A manual)
- **Line 470**: `$46.3$\%`
- **Line 503**: `$46.3$\%` (repeated)
- **Context**: "cell-level pair-reversal rate drops from $46.3$% on the manual-only Phase A subset to $\cellPairReversal{}$%"
- **Risk**: HIGH. The Phase B counterpart has a macro (`\cellPairReversal{26.5}`), but the Phase A baseline value does not.
- **Fix**: Define `\cellPairReversalPhaseA{46.3}`.

### P0-3. Phase B / manual corpus ratio
- **Line 503**: `$4.5{\times}$`
- **Context**: "Phase B auto-expansion (... $4.5\times$ the manual 706-scenario base)"
- **Risk**: MEDIUM. A macro `\bayesErrFindingAsetOmissionRatio{4.5}` exists but is a *different quantity* (Bayes error omission ratio). This is 3186/706 = 4.51x.
- **Fix**: Define `\phaseBExpansionRatio{4.5}`.

### P0-4. PAF forbid detection rate
- **Line 279**: `$1.4$\%`
- **Line 417**: `$\le 1.4$\%`
- **Context**: "PAF nevertheless detects only 1.4%" (E1 controlled perturbation)
- **Risk**: MEDIUM. This is a key E1 result cited twice with no macro.
- **Fix**: Define `\eOneForbidPAFRate{1.4}`.

### P0-5. TCC 100% detection rate
- **Line 279**: `$100$\%`
- **Line 417**: `$100$\%` (repeated)
- **Context**: "TCC flags 100% of all four perturbation types"
- **Risk**: LOW (structural by design, unlikely to change). But still a result.
- **Fix**: Define `\eOneTCCDetectAll{100}` for consistency.

### P0-6. Nemotron empty rate (body text)
- **Line 503**: `0.99\%`
- **Context**: "Three v6 disclosures (nemotron empty 0.99%, ...)"
- **Risk**: LOW. Macro `\nemotronEmptyPct{0.99}` **does exist** in `auto_numbers.tex` (line ~170) but is not used here. This is technically P1 but the value will go stale if the macro is updated.
- **Fix**: Replace with `\nemotronEmptyPct{}`.

---

## P1: Macro Exists But Hardcoded Value Used

These numbers have a corresponding macro in `auto_numbers.tex` or `main_final_v18.tex` preamble, but the body text uses a bare literal instead.

### P1-1. Scenario count "706" (6 occurrences)
- **Lines**: 406, 407, 408, 465, 473, 503
- **Macro available**: `\numTotalScenarios{706}` (auto_numbers.tex line 218)
- **Occurrences**:
  - L406: "Manual 706 scenarios $\times$ \numModels{}"
  - L407: "Same 706 scenarios with Llama-4-Scout dropped"
  - L408: "706 manual $+$ Tier-S CPGs"
  - L465: "the manual 706-scenario subset"
  - L473: "$706{\times}\numRuns{}$"
  - L503: "the manual 706-scenario base"
- **Fix**: Replace all with `\numTotalScenarios{}`.

### P1-2. Episode count "16,944" in typed-CwT paragraph
- **Line 465**: `$N{=}16{,}944$`
- **Macro available**: `\phaseAEpisodes{16{,}944}` (main_final_v18.tex line 224)
- **Fix**: Replace with `\phaseAEpisodes{}`.

### P1-3. Approximate Bayes error "~44%"
- **Line 367**: `${\sim}44$\%`
- **Macro available**: `\bayesErrTerm{0.436}` = 43.6%
- **Context**: "terminal-only evaluators irrecoverably misclassify ${\sim}44$% of trajectories"
- **Risk**: The "~44%" is a rounded approximation of 43.6%. If bayesErrTerm changes, this won't update.
- **Fix**: Replace with `${\sim}\bayesErrTermPct{}$\%` (define `\bayesErrTermPct{43.6}`) or use inline rounding.

---

## P2: Design Constants / Thresholds (Acceptable)

These are intentional design parameters, experimental settings, or structural identities. Hardcoding is defensible.

| Line | Value | Context | Reason acceptable |
|------|-------|---------|-------------------|
| 347 | `(10,5,3,1)` | Tier cost anchors | Design constants, defined once |
| 503 | `$T{=}0.1$` | Temperature setting | Experimental parameter |
| 429 | `30\%` | "exceed 30% FA" | Descriptive threshold |
| 451 | `$p{<}0.001$` | McNemar significance | Standard p-value threshold |
| 272 | `35\,min` | "antibiotics 35 min after deadline" | Clinical example narrative |

---

## Cross-Reference Integrity Check

| Body text value | Macro value | Match? | Note |
|-----------------|-------------|:------:|------|
| 706 (6x) | `\numTotalScenarios{706}` | Y | Macro exists, not used |
| 16,944 | `\phaseAEpisodes{16{,}944}` | Y | Macro exists, not used |
| 0.059 | (no macro) | -- | **MISSING** |
| 0.076 | (no macro) | -- | **MISSING** |
| 46.3% (2x) | (no macro) | -- | **MISSING** |
| 4.5x | (no macro for this quantity) | -- | **MISSING** |
| 1.4% (2x) | (no macro) | -- | **MISSING** |
| ~44% | `\bayesErrTerm{0.436}` | ~Y | Rounded, not linked |
| 0.99% | `\nemotronEmptyPct{0.99}` | Y | Macro exists, not used |
| 100% (2x) | (no macro) | -- | Structural identity |
| 0% (2x) | (no macro) | -- | Structural identity |

---

## Recommended Actions

1. **Define 4 missing macros** in `auto_numbers.tex`:
   ```latex
   \providecommand{\typedCwtManualEtaEval}{0.059}
   \providecommand{\typedCwtManualEtaRun}{0.076}
   \providecommand{\cellPairReversalPhaseA}{46.3}
   \providecommand{\eOneForbidPAFRate}{1.4}
   ```

2. **Replace 6 hardcoded "706"** with `\numTotalScenarios{}`.

3. **Replace hardcoded "16,944"** on L465 with `\phaseAEpisodes{}`.

4. **Replace hardcoded "0.99%"** on L503 with `\nemotronEmptyPct{}`.

5. **Link "~44%"** on L367 to `\bayesErrTerm`.

6. **Optionally define** `\phaseBExpansionRatio{4.5}` and `\eOneTCCDetectAll{100}`.

Total edits: ~15 substitutions + 4-6 new macro definitions.
