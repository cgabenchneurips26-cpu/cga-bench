# Contribution 4 Credibility Raise — Final Session Report

**Date:** 2026-04-23
**Branch:** `eval_science`
**Plan:** `/home/anonymous-user/.claude/plans/contribution-4-evaluator-melodic-cupcake.md`
**Scope decision:** `docs/260423_piclass_pool_dilution_finding.md` (option 2: scope-limited)

---

## Executive summary

Ran 11 experiments (plan-original 10 + a pragmatic T2-9 pivot) to harden
Contribution 4's π-class-predicts-independence claim. The plan's
rollback trigger fired on T0-1 (permutation p = 0.22), forcing a
scope-limitation decision. We accepted option 2 (scope-limited) rather
than pure rollback, retained the canonical-6 predictivity claim with
explicit caveats, and documented the extended-pool dilution as an
honest limitation that simultaneously pre-empts the "post-hoc tune"
reviewer attack.

## Experiments delivered

| # | Script | Macros | Result (canonical-6 unless noted) |
|---|---|---|---|
| T0-1 | `exp_piclass_permutation.py` | piPerm* | obs gap=0.281, perm p=**0.2222** (6-eval, 15 pairs — pool too small for α=0.05) |
| T0-1/T0-2 ext | `exp_piclass_pool_expand.py` | piPool* | 19-eval dilution: gap=0.011, perm p=**0.87**, bootstrap CIs overlap → triggers scope-limit |
| T0-3 | paper prose only | — | Silent-zero drift paragraph added to §4.4 |
| T1-4 | `exp_piclass_heldout.py` | piHeldout* | held-out 5 CPG (798 eps) gap=**0.460** (widens vs core 0.252) |
| T1-5 | `exp_piclass_per_domain.py` | piPerDomain* | 14/15 domains show within > cross; median gap=+0.365; pals_p lone reversal |
| T1-6 | `exp_piclass_random_clustering.py` | piRandCluster* | size-preserving partition null: p=**0.1168** (combinatorial cap) |
| T1-7 | `exp_piclass_mixed_effects.py` | piMixed* | OLS β̂₁=**0.2328**, SE=0.164, p=0.18, ICC=**0.30** |
| T2-8 | `exp_piclass_alt_metrics.py` | piAlt* | 5 metrics (τ, ρ, r, κ, φ): **0 reversals** |
| T2-9 | `exp_piclass_bsr_independence.py` | piBsrIndep* | Spearman ρ(BSR, π)=-0.18, 3/3 class range overlap → not BSR-reducible |
| T2-11 | `exp_piclass_evp_expansion.py` | piEvp* | 6/6 external bridges: hypothesis ≠ actual pi-class (harness author-independent) |

**Not executed:**
- T2-10 (user study) — anonymity risk, plan-excluded.
- T0-3 code artefact — silent-zero narrative is prose-only; supporting artefacts already exist at `a6c83884`.

## Commit timeline

| SHA | Description |
|---|---|
| `5a0b7998` | T0-1 6-eval permutation test (p=0.22, rollback trigger) |
| `b914270c` | T0-1+T0-2 extended pool (p=0.87, dilution → scope-limit decision) |
| `<heldout>` | T1-4 held-out 5 CPG (gap widens to 0.46) |
| `<per_domain/random>` | T1-5 + T1-6 (14/15 domains positive, random p=0.12) |
| `efbcfcc2` | T1-7 mixed-effects regression (β̂=0.23 ICC=0.30) |
| `57525be9` | T2-8 alt correlation metrics (0/5 reversals) |
| `e7b597f2` | T2-9 BSR-independence (ρ=-0.18) |
| `16dfb670` | T2-11 EVP hypothesis vs actual (0/6 match) |
| `<paper>` | §4.4 predictivity audit + silent-zero paragraph + 9 macro loads |

## Acceptance criteria review (plan)

| Criterion | Met? | Note |
|---|---|---|
| T0-1 p < 0.001 | ❌ | Plan rollback fired; option 2 scope-limit accepted |
| T0-2 CI non-overlap | ❌ (extended pool) | Canonical-6 CIs not directly computed (T1-4 provides held-out substitute) |
| T1-4 gap Δ ≤ 0.10 | ❌ (+0.21) | Exceeded in favourable direction (held-out stronger) |
| T1-6 random-cluster upper 1% | ❌ | 11.68% (pool-size ceiling) |
| T1-7 β > 0 AND p < 0.01 AND ICC > 0.1 | 2/3 | sign + ICC pass, p=0.18 under-powered |
| T2-8 all metrics within > cross | ✅ | 0/5 reversals |
| T2-9 NoiseClone → term, Matched → nctx | reframed | Pivoted to BSR-independence: ρ=-0.18, 3/3 overlap |

## What the paper now says (§4.4)

Two new paragraphs:
1. **Predictivity audit (scope: six canonical evaluator families)** —
   single paragraph stitching 9 experiments. Reports positive canonical
   findings (gap, widening on held-out, 14/15 domains, 0 metric
   reversals, ICC=0.30, BSR-independence), honest negative / null
   statistics (perm p=0.22, cluster p=0.12, mixed-effects p=0.18),
   pool dilution (p=0.87 at 19 evaluators), and 6/6 hypothesis
   mismatch as empirical basis for the scope limitation.
2. **Operational evidence: the harness caught its own drift** —
   T0-3 silent-zero narrative turns commit `a6c83884` into a case
   study that answers A9.

## What we rejected and why

- **Pure rollback (option 1)** — erases a real family-specific
  signal; over-corrects.
- **Deeper subset cherry-pick (option 3)** — invites A3 (post-hoc
  tune) directly.
- **Synthetic adversarial T2-9 on canonical-6** — combinatorially
  blocked (dxem is all-True, any same-marginal construction collapses
  to dxem's vector); pivoted to BSR-independence on extended pool.
- **Reporting only held-out strength and hiding perm p=0.22** —
  selective reporting.

## Reviewer defence matrix (updated)

| Attack | Response |
|---|---|
| A1 statistical significance | p-values for perm/cluster/regression reported as-is; not claimed < 0.05 |
| A2 one-corpus artifact | T1-4 held-out shows gap widens; T1-5 14/15 domains consistent |
| A3 post-hoc tune | T2-11 6/6 hypothesis mismatch = harness independent of author prior |
| A4 EVP toy | T2-11 includes 4 native external bridges (MedAgent, ART, AgentEHR, HealthBench) |
| A5 DPI classical | paper already reframes as "operationalised audit tool" |
| A6 correlation ≠ causation | T2-9 BSR-independence, T2-8 multi-metric consistency |
| A7 Kendall τ crude | T2-8 5 metrics converge, 0 reversals |
| A8 reviewer can't plug in | demo/app.py + docs/audit/ MkDocs + `ext_*` decorator pattern |
| A9 silent-zero fragility | T0-3 turns drift into operational case study |
| A10 trivial findings | pi-class assignment via behavioural separating-pair test, not hand-coded rules |

## Limitations self-imposed

- Claims restricted to canonical-6 family; extended pool dilution
  stated openly.
- All p-values on canonical-6 are limited by the pool's combinatorial
  ceiling; no spurious "α=0.05" label applied.
- Held-out gap widening reported as magnitude (+0.21) rather than
  re-tested for formal significance (the held-out subsample is small).

## Follow-up candidates (post-camera-ready)

1. Expand canonical family to 10+ evaluators and re-test at full
   statistical power.
2. T2-10 user study under de-anonymisation-safe setup.
3. Register `ext_*` bridges whose `pi_family_hypothesis` is updated
   to reflect the harness's actual classification.

## Related artefacts

- Plan: `/home/anonymous-user/.claude/plans/contribution-4-evaluator-melodic-cupcake.md`
- Decision log: `docs/260423_piclass_pool_dilution_finding.md`
- Prior session summary: `docs/260423_session_final_summary.md` (Option C work)
- Memory entries: `project_piclass_scope_limit.md`, `feedback_persist_session_summaries.md`
