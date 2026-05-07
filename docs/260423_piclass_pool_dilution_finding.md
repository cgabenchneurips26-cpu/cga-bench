# π-class pool-dilution finding — decision log

**Date:** 2026-04-23
**Branch:** `eval_science`
**Related commits:** `5a0b7998` (T0-1 on 6-eval), `<pending>` (T0-1+T0-2 on 19-eval)

---

## Finding

Under the current full `SHIM_REGISTRY` (19 evaluators excluding `llm_judge`), the within/cross-class mean Kendall-τ gap that motivates Contribution 4 **collapses to effectively zero**, eliminating the statistical basis for the "π-class predicts verdict independence" claim.

### Side-by-side

| Pool | N eval | N pairs | same τ̄ | cross τ̄ | gap | perm p | bootstrap CI overlap |
|---|---|---|---|---|---|---|---|
| Original c6 (6 canonical) | 6 | 15 | 0.4729 | 0.1915 | **0.281** | 0.2222 | — |
| Extended SHIM_REGISTRY | 19 | 171 | **0.2117** | **0.2029** | **0.011** | **0.8710** | True |

### Extended-pool pi-class census

- **aset (2):** `c2_shim`, `pi_nord_witness`
- **nctx (10):** `ac_proxy`, `acov_shim`, `action_coverage`, `active_agent`, `c2_score`, `ext_healthbench_style`, `ext_medagent_style`, `mab_f1`, `v4_hard`, `viol_count`
- **term (7):** `always_true`, `dxem`, `ext_agentehr_native`, `ext_art_native`, `ext_healthbench_native`, `ext_medagent_native`, `mab_proxy`

## Diagnosis

The 0.281 gap on the original 6-evaluator pool is **not generalisable**. Three mechanisms likely contribute to the dilution:

1. **Metric-threshold wrappers collapse same-class agreement.** `action_coverage`, `c2_score`, `mab_f1`, `always_true` all fall into `nctx` by the step-1 behavioural test, but are continuous-metric thresholds of the *same* verdict matrix columns. Their pair-wise τ is high with each other and with `ac_proxy`/`acov_shim`, inflating same-class variance.
2. **External-benchmark bridges are over-classified into `term`.** Four of the six `ext_*` native bridges classify as `term` because the audit separating-pair behavioural test collapses them early — but their τ with `always_true` or `dxem` is moderate, not high.
3. **Style emulators split between aset/nctx** despite being aset by construction (`pi_family_hypothesis`), widening the effective class definition.

Taken together: the step-1 classifier places many heterogeneous evaluators into the same π-class, and pair-wise τ within that mixed class is no longer tight.

## Decision

Adopt **scope-limited framing (option 2)** over pure rollback.

**Rationale:**
- The 6-evaluator c6 separation is real within that family; it should not be erased.
- Reviewers will ask "does this generalise?" — honest scope limitation with the extended-pool null result pre-empts the question rather than inviting it.
- Paper already uses "six canonical evaluator families (TOM/ASC/PAF/CwT/ACov/TCC)" framing; tightening §4.4 to make the scope explicit is a surface edit, not a structural rewrite.

**Plan:**
1. Paper §4.4 amendment: state that the within > cross τ̄ separation is observed **on the six canonical families** and is **diluted** on an arbitrary hybrid pool (report extended-pool numbers inline as limitation).
2. Remaining experiments T1-4 / T1-5 / T1-6 / T1-7 / T2-8 / T2-9 / T2-11 re-scoped to the 6-evaluator canonical pool (matching the actual c6 artefact).
3. T1-4 (held-out 5 CPG) still valuable: checks that the 6-eval separation holds on unseen guidelines — a real generalisation axis even if not over pool composition.
4. T2-11 (EVP expansion) **reframes to a null observation**: "when we plug 13 additional evaluators through the harness, the taxonomy does not discriminate them; the harness is honest about this and surfaces it via the dilution result."
5. Contribution 4 positioning stays as "audit harness as a diagnostic tool that returns π-class + BSR + Bayes floor + blind-spot grid" — the tool's value is not predicated on the separation claim being universal.

## Rejected alternatives

- **Pure rollback (option 1):** erases real signal in the canonical family and over-corrects.
- **Deeper diagnostic (option 3):** post-hoc subset analysis invites A3 ("post-hoc tune") directly; avoided.
- **Silent restriction to 6-eval:** would be dishonest given the 19-eval run now exists in the repo and in `evidence_pack/audit/piclass_pool_expand_*`.

## What stays / what changes

| Component | Status |
|---|---|
| `audit/metrics/selection.py` | unchanged |
| `evidence_pack/audit/c6_audit_guided_selection.json` | keep (6-eval canonical) |
| `evidence_pack/audit/piclass_pool_expand_*` | keep (the null result itself is a reported artefact) |
| Paper §4.4 pi-class paragraph | amend: add "canonical-family scope" + "extended-pool dilutes to Δ=0.011 (p=0.87)" sentence |
| T1-4 held-out | keep, 6-eval scope |
| T1-5 per-domain boxplot | keep, 6-eval scope |
| T1-6 random clustering | keep, 6-eval scope |
| T1-7 mixed-effects | keep, 6-eval scope |
| T2-8 alt correlation metrics | keep, 6-eval scope |
| T2-9 adversarial pair | keep, 6-eval scope |
| T2-11 EVP expansion | **reframe** as null observation / dilution evidence |
| T0-1 on 6-eval (commit `5a0b7998`) | stays — p=0.22 on small pool is honest reporting |

## Acceptance checkpoint for remaining experiments

The 6-eval canonical pool is the evaluation universe for T1/T2. All p-values and CIs will be reported with explicit "(6 canonical evaluators)" annotation. Any T1/T2 result that relies on the dilution being absent will be flagged.

## References

- Extended-pool artefacts: `evidence_pack/audit/piclass_pool_expand_*.json`, `...macros.tex`
- Experiment script: `scripts/experiments/exp_piclass_pool_expand.py`
- Original 6-eval: `evidence_pack/audit/c6_audit_guided_selection.json`
- T0-1 report (6-eval): commit `5a0b7998`
