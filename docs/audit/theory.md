# Theory: π-class + Bayes-error floor

## Projections

A projection π: X → Y is a measurable coarsening of the trajectory
space. CGA-Bench uses four:

| π | Name | What is preserved | What is erased |
|---|---|---|---|
| π_term | terminal | final disposition | all intermediate actions, timing, context |
| π_aset | action multiset | set of actions taken | order, timing, patient context |
| π_nord | ordered | ordered action sequence | timing (clock), patient state |
| π_nctx | timed | ordered + timed actions | patient state / derivation context |

π_nctx is the finest projection in CGA-Bench (its fibres correspond
to unique timed action traces).

## Data-processing inequality

An evaluator that factors through π (writes f(x) = g(π(x)) for some g)
cannot distinguish trajectories that agree on π. Its error rate is
lower-bounded by the plug-in Bayes error:

```
ε*_π = Σ_y min(p_0(y), p_1(y)) · m_y / N
```

where y ranges over π-fibres, m_y = |π⁻¹(y) ∩ corpus|, and p_k(y) is
the fraction of label-k items in the fibre.

## Empirical values on CGA-Bench (N = 14,826)

| π | ε̂*_π | Mixed-fibre mass | Dominant coord. |
|---|---|---|---|
| π_term | 0.436 | 100.0% | TIMING (0.429) |
| π_aset | 0.024 | 9.8% | OMISSION (0.109) |
| π_nord | 0.003 | 1.0% | OMISSION (0.031) |
| π_nctx | 0.003 | 1.0% | OMISSION (0.028) |

## Sharpest single-step separation

Between π_term and π_aset the TIMING coordinate drops from 0.429 to
0.018 — Δ = **0.411**. This is the sharpest single-step drop of any
(projection, violation-type) pair on the corpus, and motivates the
"action-set evaluators are blind to timing" narrative in §3.3 of the
paper.

## Existence vs constructive witness

The π_nord floor ε̂* = 0.003 is the **Bayes-optimal lower bound** for
any evaluator that observes only ordered actions (no timing, no
patient context).

**Is the floor achievable?** We attempt a constructive π_nord witness
(`pi_nord_witness` shim) using only trajectory action IDs and
scenario-derived expected/forbidden sets. Best-variant BSR = 0.4914,
leaving a **164× gap** to the floor. The gap is not an observation
bandwidth limit — ordered actions suffice in principle — but a
**specification cost**: reaching the floor requires re-deriving
patient-conditional mandatory/forbidden sets from the CPG, which is
the scorer side by construction. Theorem 3.4 is therefore an
**existence theorem**, not a constructive recipe on CGA-Bench.

## References

- Full theorem and proof: `paper/main_final_v17.tex` §3.4.
- Numeric sources: `evidence_pack/theorem_v2/bayes_error_macros.tex`
  (pooled), `evidence_pack/audit/bayes_matrix_derived_macros.tex`
  (per-violation-type).
- B3 retry report: `docs/260423_b3_retry_report.md`.
