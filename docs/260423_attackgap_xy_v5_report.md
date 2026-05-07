# Attack-gap X + Y session v5 — gpt-oss chunked recovery + verification

**Date:** 2026-04-23 (v5)
**Branch:** `eval_science`
**Prior reports:** `260423_attackgap_xy_{report, v3_report, v4_report}.md`
**User prompts this round:** chunked recovery for 7 persistent gpt-oss failures + verification of 3 numeric claims.

## Round 5 additions

| # | Item | Result |
|---|---|---|
| R1 | **Chunked recovery** (7 persistent gpt-oss CPGs) | **7/7 recovered** via paragraph-snapped 6000-char chunks + dedupe |
| R2 | v2 main-finding full-catalogue recomputation | triple FA 41.08% → **36.95%**, ratio 6.22× → **5.60×** |
| R3 | Paper pdflatex + macro refresh | pdflatex clean, macros auto-updated (no paper prose edit needed) |
| R4 | Verification of 3 numeric claims | see §Verification below |

## Key numbers (after v5)

| | v1 Qwen-397B | v2 gpt-oss-120b (13/25) | **v2 gpt-oss-120b (25/25)** |
|---|---|---|---|
| CPGs extracted | 25/25 | 13/25 | **25/25** |
| Total constraints | 1,268 | 468 | 1,957 (estimated; includes 689 new) |
| Triple strict-FA | 36.31% | 41.08% | **36.95%** |
| Ratio vs CDE 6.6% | **5.50×** | 6.22× | **5.60×** |
| Δ between families | — | 0.72× | **0.10×** |

Dual-LLM replication converges to within 0.10× at full catalogue coverage. Pose-B §4.3 pillar 3 robust.

## Chunked recovery details

Each persistent CPG split into ≤ 6000-char chunks at paragraph boundaries with 400-char overlap. Per-chunk gpt-oss-120b call + merge + dedupe by (type, normalised action).

```
CPG                                  chars → chunks   recovered   elapsed
AACT-Toxicology-Management           19,119 → 4           73      36.0s
ADA-2009-DKA-Management              18,231 → 4          105      53.9s
AHA-2019-Stroke-Guidelines           27,043 → 5          138      68.0s
AHA-2020-ACLS-Guidelines             20,490 → 4           74      51.2s
AHA-2022-Heart-Failure-Guidelines    21,480 → 4          166     106.9s
GINA-2024-Asthma-Exacerbation        21,405 → 4           76      54.0s
KDIGO-2012-Contrast-AKI              16,481 → 3           57      34.4s
                                     ---------        ------
                                     total          689 new
```

## Verification of 3 claims (round 4 residuals)

### Claim 1: η² ratio (\etaRatio)

Ran `scripts/verify_friedman_eta.py` against current v6 corpus:

| metric | auto_numbers.tex | computed (v6 current) |
|---|---|---|
| η²(evaluator) | 0.312 | **0.3386** (33.9%, +2.7 pp) |
| η²(run) | 0.036 | **0.0000** (essentially zero) |
| η² ratio (derived) | 8.7× (= 0.312/0.036) | **94,112.7×** |
| Paper `\etaRatio` macro | **200,000** | — |

**Three-way mismatch**:
- `\etaRatio = 200,000` in paper's auto_numbers.tex.
- Script-computed ratio = 94,112.7× on current corpus.
- Derived from `auto_numbers` (0.312/0.036) would be 8.7×.

The script emits a warning `η²(run) 불일치: |0.000 - 0.036| > 0.01`. Either:
- the 0.036 entry is stale from a pre-greedy-decoding run, or
- `\etaRatio` = 200,000 is a rounded / ceiling value that doesn't directly follow from the η² ratio numbers.

**Camera-ready action needed**: reconcile `\etaRatio`. Either update to 94,113× (current greedy-decoding corpus) or document how the 200,000 figure was derived.

### Claim 2: LLM ε values and fibre mass

LLM plug-in Bayes error on 14,826 W8 episodes under LLMCatalogueShim labels (v1 Qwen):

| projection | LLM ε | LLM fibre mass (my recompute) | Published CDE (paper) | User-cited (pillar 2) |
|---|---|---|---|---|
| term | 0.0150 ✅ | 15.68% | 100.0% | 82% |
| aset | 0.0001 ✅ | 0.03% | 9.8% | 2.5% |
| nord | 0.0000 ✅ | 0.00% | 1.0% | 0% |
| nctx | 0.0000 ✅ | 0.00% | 1.0% | 0% |

**LLM ε values match exactly.** ✅

**Fibre mass mismatches on three axes**:
- My recompute used a *self-contained* projection (exp_piclass_bayes_llm_catalogue.py) that differs from scripts/_projections.py on 5-min binning / canonicalisation — mass numbers are NOT directly comparable to canonical.
- Published CDE fibre mass (100/9.8/1/1) is for CDE labels, not LLM labels; the user-cited (82/2.5/0/0) doesn't match either my recompute or published values.

**Camera-ready action**: if pillar 2 paper prose cites "82%/2.5%/0%/0%", either source this from the canonical projection pipeline or replace with actual LLM-label mass (16/0.03/0/0). Current paper §4.4 pillar 2 cites only ε values, not fibre mass — so this is a safety check for author drafts only.

### Claim 3: Bootstrap 95% CI (B=1000)

From `evidence_pack/theorem_v2/bayes_error_macros.tex`:

| projection | ε | 95% CI (B=1000) |
|---|---|---|
| term | 0.436 | [0.428, 0.444] |
| aset | 0.024 | [0.019, 0.024] |
| nord | 0.003 | [0.002, 0.003] |
| nctx | 0.003 | [0.002, 0.003] |

Tight intervals. These are the committed canonical numbers — the paper cites these via macros (Table `tab:bayes_error`). ✅

## Paper status

pdflatex --interaction=nonstopmode clean (commit 986aca84 + macro refresh).
Paper now reads (5.50× Qwen / 5.60× gpt-oss) at 25/25 catalogue coverage — tight dual-LLM citation.

## Deferred (session handoff)

See `260423_attackgap_xy_session_handoff.md` for the next-session task list.

## Round-5 commits (this report's scope)

- gpt-oss chunked recovery (7/7) + full v2 catalogue (just committed this round)
- 986aca84 paper §2 + §4.4 + appendix Friedman updates (prior)
- all prior v4 artefacts remain

Branch `eval_science` push-ready. anonymous-org shell only.
