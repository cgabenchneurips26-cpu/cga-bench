# E9 Follow-up G Batch Session Summary (G1/G2/G3)

**Date**: 2026-04-30
**Branch**: `eval_science`
**Spec source**: `docs/attack_gap_exp_exp/260430_add_contribution_exp.md`
**Parent report**: `docs/260430_e9_high_authority_audit_report.md` §11

---

## 0. Headline

| Item | Status |
|---|---|
| 3 generators implemented (G1/G2/G3) | ✅ all reproduce pre-flight numbers |
| 9 output artefacts in `evidence_pack/analysis/` | ✅ all present |
| 22/22 follow-up tests pass (11 F batch + 11 G batch) | ✅ green |
| §11 (8 sub-sections, 292 lines) appended to audit report | ✅ |
| 5 caveats addressed | ✅ |

---

## 1. Pre-flight findings (decided pivots)

| Caveat | Pre-flight result | Decision |
|---|---|---|
| C1 — 12.8% framing exposure | 144/1124 = 12.8% safety-core (Wilson [11.0%, 14.9%]) | accept; explicit in main one-liner with absolute count + CI |
| **C2 — G2 retention sufficient?** | **S2 154/238 well-formed (5× threshold)**, **17/238 graphs (2× threshold)** | proceed |
| C3 — `1258` provenance | comment-only `6.6% × 19062` in `auto_numbers_v18.tex:581`; canonical macro = 1124 | sync unnecessary; documented in §11.8 |
| C4 — S1/S2 cut definitions | confirmed verbatim from yaml | written into §11.7 |
| C5 — G3 90% top-3 concentration | 91.4% (anaph 35.6, asthma 32.8, acls 23.0) | reported honestly with tail |

**G1 critical pivot**: original spec (S2 × safety-core) produced n=4 (below threshold). Pivoted to **S1 × safety-core** with S2 collapse as strictness-gradient meta-finding. Retains the F3-defense purpose at 144 episodes (main-eligible).

---

## 2. Reproduced numbers

### G1 — `exp_e9_safety_core.{json,md,tex}` (492 LOC generator)

| Metric | Value |
|---|---|
| S1 strict-FA | 1124 |
| **S1 safety-core (FORBID ∪ BEFORE)** | **144 (12.8%)** |
| S1 family breakdown | FORBID-only=139, FORBID+WITHIN=5, BEFORE-only=0 |
| S1 MUST-only (WITHIN-only) | 980 |
| S1 Wilson 95% CI on safety-core | [11.0%, 14.9%] |
| S2 strict-FA | 548 |
| S2 safety-core | 4 |
| **Collapse delta** | **-140 episodes (-97.22%)** |

### G2 — `exp_e9_context_swap_strictest.{json,md,tex}` (438 LOC generator)

| Metric | Value |
|---|---|
| Total conditional FORBIDDEN rules | 240 |
| Well-formed pairs | 238 |
| S1 default retained | 231 / 238 (24 graphs) |
| **S2 strictest retained** | **154 / 238 (17 graphs)** |
| S2 severity | HIGH=85, CRITICAL=67, MODERATE=2 (98.7% high or critical) |
| S2 condition_type | comorbidity=60, lab_value=34, medication=19, allergy=3, etc. |
| 5 pre-reg gates | all pass ✅ (≥30, ≥8, 0%, 0%, 0%, 100%) |

### G3 — `exp_e9_s2_diversity.{json,md,tex}` (406 LOC generator)

| Metric | Value |
|---|---|
| S2 strict-FA total | 548 |
| Distinct models | 9 |
| Distinct scenarios | 122 |
| Distinct domain prefixes | 9 |
| Distinct CPG sources | 9+ (AHA, ADA, KDIGO, AABB, IDSA, GINA, ESC, WAO, etc.) |
| Top-3 domains (anaph + asthma + acls) | 91.4% |
| Top-1 model (qwen397b) | 28.5% |

---

## 3. Paper-ready sentences (in §11 of audit report)

**G1 (main one-liner)**:
> Even excluding completion-only omissions, **\GoneSafetyCoreSOneCount\ episodes (\GoneSafetyCoreSOnePct\\%, 95\% Wilson CI [\GoneSafetyCoreSOneWilsonLo, \GoneSafetyCoreSOneWilsonHi])** of strict false-accepts at the default high-authority cut carry FORBIDDEN or BEFORE violations; under the strictest cut this collapses to \GoneSafetyCoreSTwoCount\ (-\GoneCollapsePct\\%), indicating that strict-authority filtering amplifies the process-omission share of the FA composition.

**G2 (main one-liner)**:
> Among 238 conditional FORBIDDEN matched pairs, **154 (64.7\%) retain a Class-I + LOE-A or strong-society source-node under the strictest authority cut**, spanning 17 clinical guideline graphs; 98.7\% of retained pairs are HIGH or CRITICAL severity. ASC/PAF/CwT detect 0\% by construction; TCC detects 100\%.

**G3 (main one-liner, honest framing)**:
> The 548 S2 strict-FA span 9 models, 9 clinical domain prefixes, and 9 CPG sources; the dominant trio (anaphylaxis 35.6\%, asthma 32.8\%, ACLS 23.0\%) accounts for 91.4\%, with the remaining 6 domains (PE, contrast-AKI, DKA, etc.) contributing \(\leq\)2\% each — ruling out a single-guideline or single-model artefact.

---

## 4. Reviewer attack-surface coverage (cumulative F + G)

| Reviewer attack | Defended by | Headline counter |
|---|---|---|
| "IIa+B is too permissive" | F1 (S2) | 548 strict-FA + 76.81% MAB loss survive |
| "Drug-allergy auto-promotion drives the headline" | F1 (S3) | S3 = S1 byte-identical |
| "Authority is node-level not edge-level" | F2 | 0/60 promotion cases |
| "High-authority might not be harm-relevant" | F3 | 9.52% critical+major (appendix-only) |
| **"FA dominated by minor / process omissions — F3 weakness"** | **G1** | 144 safety-core at S1 |
| **"No-context witness fails under stricter authority"** | **G2** | 154/238 retained, 98.7% HIGH+CRITICAL |
| **"Single-guideline or single-model artefact"** | **G3** | 9 domains, 9 CPG sources, 9 models |

---

## 5. Files added/modified

| Type | Path | LOC |
|---|---|---|
| Generator | `scripts/experiments/exp_e39e_safety_core_overlay.py` | 492 |
| Generator | `scripts/experiments/exp_e39f_context_swap_strictest.py` | 438 |
| Generator | `scripts/experiments/exp_e39g_s2_diversity.py` | 406 |
| Tests | `tests/test_experiments/test_exp_e9_followups.py` (+11 tests) | 346 (was ~230) |
| Audit report | `docs/260430_e9_high_authority_audit_report.md` (+§11) | 778 (was 486) |
| Output artefacts | `evidence_pack/analysis/exp_e9_safety_core.{json,md,tex}` | — |
| Output artefacts | `evidence_pack/analysis/exp_e9_context_swap_strictest.{json,md,tex}` | — |
| Output artefacts | `evidence_pack/analysis/exp_e9_s2_diversity.{json,md,tex}` | — |
| This summary | `docs/260430_e9_g_batch_session_summary.md` | this file |

Total new/modified: 5 source files + 9 artefact files + 1 docs append.

---

## 6. Reproduction (full G batch ≈ 5 min)

```bash
cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench

# G1 — safety-core overlay
PYTHONPATH=. python scripts/experiments/exp_e39e_safety_core_overlay.py

# G2 — context-swap × strictest
PYTHONPATH=. python scripts/experiments/exp_e39f_context_swap_strictest.py

# G3 — S2 diversity
PYTHONPATH=. python scripts/experiments/exp_e39g_s2_diversity.py

# Tests (F + G batches)
PYTHONPATH=. pytest tests/test_experiments/test_exp_e9_followups.py -v
# → 22 passed
```

---

## 7. Strictness-gradient meta-finding (new)

A side-product of the G1 dual-cut comparison surfaced a publishable observation:

> Strict authority filtering shifts the FA composition toward process-omission patterns: the safety-core fraction (FORBIDDEN + BEFORE) drops by **97.2%** when moving from default high-authority (S1) to strictest (S2). This suggests Class I + LOE A recommendations cluster around concrete contraindication and ordering rules, not completion mandates — a structural property of the curated CPG corpus.

This is reported in §11.1 of the audit report as a "strictness gradient" supplementary contribution.

---

## 8. Outstanding (future / out-of-scope)

- **E11 (Patient-State Context Swap main-text figure)**: deferred per spec §6 — promote 238 conditional FORBID matched-pair pool to main-text figure. G2 already provides the quantitative quartet (154 retained, 17 graphs, 98.7% high+critical, 5 gates pass).
- **Wire `\Gone*`/`\Gtwo*`/`\Gthree*` macros into paper body**: needs decision on which sections (likely §5.5 main + appendix Z.6/Z.7/Z.8).
- **Appendix Z.6/Z.7/Z.8 stubs**: tables for G1 (safety-core breakdown), G2 (per-graph S2 retention), G3 (full diversity matrix).

---

**End of summary. All G-batch deliverables verified.**
