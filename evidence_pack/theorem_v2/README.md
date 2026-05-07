# Theorem 3.4 v2 — Projection-Induced Irreducible Error

This directory contains the v2 rewrite of Theorem 3.4, upgrading the
original "Observation-Coarsening Blindness" from a definition-level
restatement into an information-theoretic irreducible-error result
with a population-level quantitative core.

## Deliverables (completed in-session, math only)

| File | Purpose |
|------|---------|
| `../paper/observation_coarsening_v2.tex`                | Drop-in replacement for §3.4 main body. Definition + Lemma + **Main Theorem** + 3 corollaries + framing. |
| `appendix_theorem_proofs.tex`                           | Full proofs (measure-theoretic). Constructive separating pairs. Empirical estimator formula. CRES-1D relation. |
| `bayes_error_macros.tex`                                | Placeholder macros for the four empirical Bayes error numbers. Overwritten by local compute run. |

## What this replaces

- **Removes:** the definitional Theorem 3.4 ("Observation-Coarsening
  Blindness"), whose four cases followed directly from the definition
  of each projection. Reviewer A13 attack: "this is a tautology."
- **Adds:** Theorem 3.4 v2 (Projection-Induced Irreducible Error), a
  Bayes-error lower bound that is strictly positive whenever
  separating pairs exist, with an explicit closed form and a
  population-level entropy bound. The old observation-coarsening
  statement becomes a **Corollary** of the new theorem.

## Why this is non-definitional

The new theorem's content is:

1. **Closed-form Bayes error** (eq. (1) in the rewrite): the infimum
   error of any π-measurable evaluator equals the expected minority
   conditional probability over π-fibres. This is not trivially true
   — it required the measurable-factorisation argument in Step 1 of
   the proof.
2. **Strict positivity bounded below by data support** (Step 3): on
   the CGA-Bench distribution, the Bayes error is lower-bounded by
   min(D(τ₁), D(τ₂)) for the separating pair (τ₁, τ₂) — a
   population-level quantity, not a definition.
3. **Entropy lower bound** (Corollary `cor:fano-bound`):
   H(V_G | π) ≥ 2ε*_π(G, D), via h_b(x) ≥ 2x on [0, 1/2].
   Non-trivial because h_b is not linear.
4. **Empirical plug-in estimator** (`cor:empirical-bayes`): gives a
   directly computable number on the CGA-Bench corpus.

Reviewer A13 ("definitional") now has a concrete counter: the theorem
states a numerical quantity and provides a population-level bound, not
a restatement of surjection non-injectivity.

## What you (anonymous-user) need to run locally

To land real numbers in `bayes_error_macros.tex`, produce a script that
implements the estimator in
`appendix_theorem_proofs.tex` §"Empirical plug-in estimator".

### Pseudocode

```python
# compute_bayes_error.py
# PYTHONPATH=. python scripts/compute_bayes_error.py \
#     --episodes results/full_706_v5/all_episodes.jsonl \
#     --out evidence_pack/theorem_v2/bayes_error_results.json

from collections import Counter, defaultdict
import hashlib, json

def tau_term(episode):
    """Terminal state only. Canonicalise to (disposition, final_vitals_bucket)."""
    final = episode["terminal_state"]
    return (final["disposition"], _bucket(final["map_mmhg"]), _bucket(final["hr_bpm"]))

def tau_aset(episode):
    """Action multiset — sorted tuple of action_ids."""
    return tuple(sorted(a["action_id"] for a in episode["actions"]))

def tau_nord(episode):
    """Ordered actions, no wall-clock timestamps."""
    return tuple(a["action_id"] for a in episode["actions"])

def tau_nctx(episode):
    """Actions + timestamps, patient state stripped.
    Timestamps rounded to 5-min bins to align with episode time resolution."""
    return tuple((a["action_id"], int(a["timestamp_minutes"] / 5) * 5)
                 for a in episode["actions"])

def bayes_error(projection_fn, episodes, verdict_fn):
    """Empirical plug-in estimator of Bayes error under projection_fn."""
    fibres = defaultdict(list)
    for ep in episodes:
        key = hashlib.md5(str(projection_fn(ep)).encode()).hexdigest()
        fibres[key].append(verdict_fn(ep))

    N = len(episodes)
    total_minority = 0
    mixed_mass = 0
    for key, verdicts in fibres.items():
        counts = Counter(verdicts)
        if len(counts) >= 2:
            mixed_mass += sum(counts.values())
            total_minority += sum(counts.values()) - counts.most_common(1)[0][1]

    eps_star = total_minority / N
    mu_mix = mixed_mass / N
    return {
        "bayes_error": eps_star,
        "mixed_fibre_mass": mu_mix,
        "n_fibres": len(fibres),
        "n_mixed_fibres": sum(1 for v in fibres.values()
                               if len(set(v)) >= 2),
    }

# Run:
projections = {
    "term": tau_term,
    "aset": tau_aset,
    "nord": tau_nord,
    "nctx": tau_nctx,
}
results = {
    name: bayes_error(fn, episodes, lambda ep: int(ep["hard_violation"]))
    for name, fn in projections.items()
}

# Bootstrap CIs (B=1000)
import numpy as np
rng = np.random.default_rng(42)
for name, fn in projections.items():
    samples = [bayes_error(fn, rng.choice(episodes, N, replace=True),
                           lambda ep: int(ep["hard_violation"]))["bayes_error"]
               for _ in range(1000)]
    results[name]["ci95"] = (float(np.percentile(samples, 2.5)),
                              float(np.percentile(samples, 97.5)))
```

### Verdict function

`verdict_fn` should return a binary verdict (or the multi-bit violation
tuple for the per-coordinate variant). For the headline table, use
`int(hard_violation)` — any OMIT/COMMIT/TIME/SEQ fired.

For the per-type table in the appendix, report the Bayes error under
each coordinate V_{G,k} ∈ {0,1} for k ∈ {OMIT, COMMIT, TIME, SEQ, DEV}
separately. Under `π_nord`, for instance, the TIME coordinate should
have a notably higher Bayes error than the COMMIT coordinate.

### Expected qualitative pattern

If the theorem is working as claimed, we should see:

|                | term        | aset     | nord     | nctx        |
|----------------|-------------|----------|----------|-------------|
| Bayes error    | **highest** | moderate | moderate | **high**    |
| Mixed-fibre mass | **highest** | moderate | low      | **high**    |

- `term` highest because terminal states are coarse (many episodes end
  at the same disposition).
- `nctx` high because context-stripped fibres collapse conditionally-
  activated constraints.
- `nord` lowest because ordered-action fibres already separate many
  episodes; only TIME violations contribute.
- `aset` between: separates ordering differences but collapses all
  timing.

If you get `nord` lower than `nctx`, the theorem's qualitative story
holds; if they are comparable or reversed, that's a finding worth
noting in the paper (context-erasure less costly than expected — could
indicate TCC is under-weighting context).

### Output → macros

Once `bayes_error_results.json` is produced, render the macro file:

```python
# render_bayes_macros.py
import json
r = json.load(open("evidence_pack/theorem_v2/bayes_error_results.json"))
out = f"""
\\renewcommand{{\\bayesErrTerm}}{{{r['term']['bayes_error']:.3f}}}
\\renewcommand{{\\bayesErrAset}}{{{r['aset']['bayes_error']:.3f}}}
\\renewcommand{{\\bayesErrNord}}{{{r['nord']['bayes_error']:.3f}}}
\\renewcommand{{\\bayesErrNctx}}{{{r['nctx']['bayes_error']:.3f}}}
\\renewcommand{{\\bayesErrMixedFracTerm}}{{{r['term']['mixed_fibre_mass']*100:.1f}\\%}}
\\renewcommand{{\\bayesErrMixedFracAset}}{{{r['aset']['mixed_fibre_mass']*100:.1f}\\%}}
\\renewcommand{{\\bayesErrMixedFracNord}}{{{r['nord']['mixed_fibre_mass']*100:.1f}\\%}}
\\renewcommand{{\\bayesErrMixedFracNctx}}{{{r['nctx']['mixed_fibre_mass']*100:.1f}\\%}}
\\renewcommand{{\\bayesErrNEpisodes}}{{{N:,}}}
"""
open("evidence_pack/theorem_v2/bayes_error_macros.tex", "w").write(out)
```

## What you still need to do manually in the paper

After the macros land, update `paper/main_final_v17.tex`:

1. **Switch the `\input`** for Theorem 3.4:
   - Before: `\input{observation_coarsening}`
   - After:  `\input{observation_coarsening_v2}`
2. **Add the macro import** near the top (after `\input{auto_numbers.tex}`):
   ```latex
   \IfFileExists{../evidence_pack/theorem_v2/bayes_error_macros.tex}
     {\input{../evidence_pack/theorem_v2/bayes_error_macros.tex}}{}
   ```
3. **Add the proofs appendix** to `paper/appendix.tex`:
   ```latex
   \section{Proofs for Theorem~\ref{thm:coarsening}}
   \label{app:thm-proofs}
   \input{../evidence_pack/theorem_v2/appendix_theorem_proofs}
   ```
4. **Check cross-references**: `thm:coarsening` label is preserved;
   downstream refs (e.g., in §3, §5, §7) do not need changes.
5. **Remove `paper/figures/figure2.tex`** (theorem witness) references
   if any remain — the new Lemma statement is textual, not figure-based.
   (Task #21 already removed it; verify no regressions.)

## Witness episode IDs (for Table A1)

The four witness episode pairs listed in
`appendix_theorem_proofs.tex` Table `tab:thm-witnesses` use placeholder
IDs (`sepsis_hr1_0412`, etc.). These must resolve to real episodes in
your corpus. Verify by grep:

```bash
grep -l "sepsis_hr1_0412" results/full_706_v5/*.jsonl
```

If these IDs are not in the corpus, replace with four real IDs that
satisfy the separating-pair conditions. Any four episodes matching
the constructions in §A.2 will do; the witnesses are not cherry-picks,
they are existence demonstrations.

## Attack-map

| Reviewer attack | How this rewrite addresses it |
|-----------------|-------------------------------|
| A13 "Theorem is definitional" | Theorem now states a Bayes-error bound with closed form, positivity proof, and empirical estimator. Old theorem = corollary. |
| A1 "CRES-1D 0.994 AUC makes TCC redundant with morphology" | §A.5 shows CRES-1D classifier is NOT π-measurable, so the theorem's bound does not apply to it; its high AUC is a property of the CGA-Bench distribution, not of TCC's construct validity. The attack's logical step from "morphology predicts TCC" to "TCC measures morphology" is blocked. |
| A14 "TCC is its own gold standard" | The theorem quantifies what any process-oblivious evaluator *must* miss, without assuming TCC is the gold standard. ε*_π > 0 holds for the Bayes-optimal π-measurable predictor, not just TCC. |

## Time estimate

- Math write-up (this directory): **done** (4-5 hours equivalent).
- Local compute run (anonymous-user's PC): ~30 min (single pass over episode
  corpus + B=1000 bootstrap).
- LaTeX integration (swap `\input`, add appendix section, verify
  compile): ~1 hour.
- Witness ID verification + grep + possible replacement: ~30 min.

Total remaining: **~2 hours of anonymous-user time** post-compute.
