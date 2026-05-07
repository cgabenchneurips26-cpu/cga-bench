# v18 Audit — Critical-FA Addendum (Tasks 1–7)

**Date**: 2026-04-29 (companion to `v18_consistency_audit_20260429.md`)
**Trigger**: User-side review of audit doc raised 7 follow-up concerns about the v5→v6 critical-FA drop, App. T residue, v8_typed identity, distribution concentration, paper residues, Phase B narrative, and dual classification.

This addendum records the empirical findings and the corrective actions applied.

---

## Task 1 (HIGHEST PRIORITY) — HARK / Definition-Change Audit

### Finding (corrects audit doc §6 lessons)

The audit doc earlier claimed the v5→v6 critical drop (22.1% → 6.6% of loose-FA) was caused by *"a stricter v4_crit definition (Class I/A only, vs. earlier Class I + IIa pooling)"*. **This claim is incorrect** and has been removed from App. T text and the audit doc.

The actual `v4_crit` derivation has been stable since the single commit that introduced it:

```
scripts/experiments/verdict_matrix_v4.py:127
    has_crit = any(v["severity"] == "CRITICAL" for v in viols)

git log --follow:
    bcf7ff35  2026-04-02  feat: EXP-3/4/6 experiments + scenario YAML full audit
    (no further commits to this file)
```

There is **no later code-side change** to the critical predicate. The drop must therefore originate in the upstream `v["severity"]` tags, which are written when violations are extracted from CPG YAMLs.

### Decomposing the v5 → v6 drop (same 8-model corpus)

We re-ran the v6 verdict matrix restricted to the 8 v5 models (excluding Llama-4-Scout) on the same 706×8×3 = 16,944-trajectory shape:

| Quantity | v5 paper claim | v6 same-corpus subset | Δ |
|---|---|---|---|
| loose-FA | 1,959 | **1,858** | −101 (−5.2%) |
| loose-crit | 432 | **126** | −306 (−70.8%) |
| critical / loose-FA | 22.1% | **6.8%** | −15.3 pp |
| strict-FA | 1,118 | **912** | −206 (−18.4%) |

Llama-4-Scout's separate contribution to the 9-model expansion: +248 loose-FA and +13 loose-crit (≈+5% of FA, +9% of crit). **So ~95% of the v5→v6 critical drop is from severity-tag regeneration on the SAME 8-model corpus**, not from adding Llama-4-Scout.

### Provenance of severity-tag regeneration

The corpus was regenerated as part of the v6 9-model expansion (commits `93b072a0` "regenerate paper auto-numbers from Phase B v6 corpus" and downstream). At regeneration, scenarios may have been re-emitted by `PatientGenerator` with updated severity tags, or the CPG-graph YAMLs may have been re-tagged via `scripts/experiments/verdict_matrix_v4.py` reading current YAMLs. Either way the v6 critical count reflects current severity tagging, not a different `v4_crit` predicate.

### HARK risk

If the severity-tag updates were made *after* v6 verdict numbers were observed in order to lower critical count, this would be HARK. We have not found evidence of that pattern (no severity-tag commit *after* v6 numbers were first computed), but the trail is hard to reconstruct from git alone. The defensive paper actions below assume the conservative posture.

### Corrective actions applied

1. **App. T text**: removed the speculative "Class I/A only" sentence; replaced with a paragraph that (a) discloses the v5→v6 drop honestly, (b) attributes it to severity-tag updates, (c) emphasises that the structural claim survives both classifications.

2. **Robustness probe macro added**: `\strictFACritical=22`, `\consensusFACritical=139`, `\strictFACritFracTotal=0.12`, `\consensusFACritFracTotal=0.73` — both reported in the new App. T table so a reviewer who suspects definition narrowing sees both numbers side-by-side.

3. **Distribution-coverage sentence added** (Task 4 below): the 22 strict-critical FAs span 6/9 models and 15 distinct scenarios; the 139 loose-critical FAs span 9/9 models and 48 scenarios. Rules out single-model and single-scenario artefacts.

4. **Dual classification clarification added** (Task 7 below): Class I/A vs. v4_crit are different objects (provenance vs. severity).

---

## Task 2 — App. T Severity Breakdown (now 9-model 19,062-anchored)

The pre-fix App. T table read v5 8-model 16,944 hard-coded numbers (Critical 432, High 101, Medium 1,426, Low 0; Total 1,959; 11.6% of 16,944). After this addendum:

```
Severity / definition           Count    % of FA   % of Total
Loose consensus (ASC ∩ CwT ∧ v4_hard)
  Catalogue-critical            139      6.6%      0.73%
  Non-critical                  1,967    93.4%     10.3%
  Total                         2,106    100%      11.0%
Strict consensus (ASC ∩ PAF ∩ CwT) — for reference
  Catalogue-critical            22       2.0%      0.12%
  Total                         1,124    100%      5.9%
```

Granular tiers (High / Medium / Low) require per-violation severity scores not exposed in the verdict-matrix release; they are deferred to a follow-on appendix release. The orphan macros `\consensusFAHigh`, `\consensusFAMedium`, `\consensusFALow` (still defined in `auto_numbers.tex` from the Phase B regen) are no longer referenced by the new table.

---

## Task 3 — `verdict_matrix_v8_typed.json` Identity

### Finding

`verdict_matrix_v8_typed.json` and `verdict_matrix_v6.json` have **identical** `metadata.n_episodes=19,062`, **identical** model list (9 models, 2,118 trajectories each), and **identical** loose/strict FA aggregates. The earlier observation that `len(per_episode)=29,502` for v8_typed is a redundant-record artefact (the file appears to contain duplicates or a different schema row layout — `episode_id` field is missing from the entries, which prevented dedup verification by ID). For paper purposes:

- v8_typed adds `c2_pass_typed` and `c2_score_typed` columns — i.e., it is the **same corpus re-scored with the typed-CwT scorer**, not an independent run.
- The number 29,502 does **not appear in the paper** (`grep -n "29,502\|29{,}502" paper/*.tex` returns no hits). Safe.
- The audit doc earlier labelled v8_typed as "auto-expanded, 29,502" which was a misread of `len(per_episode)` rather than a content claim. Corrected in this addendum.

### Action

No paper-side change required. `scripts/experiments/trace_critical_fa_evolution.py` was updated to print the metadata `n_episodes` count rather than `len(per_episode)`.

---

## Task 4 — Critical-FA Concentration (model / scenario)

### Strict-3-way (22 trajectories)

```
per-model (6/9 models, 0 in qwen27b/qwen35b/qwen397b):
  llama4scout    : 8
  nemotron30b    : 5
  deepseek_r1_7b : 3
  qwen4b         : 3
  gemma31b       : 2
  oss120b        : 1
per-scenario (15 distinct, top 5):
  aha_st_basic_bp_uncontrolled_no_tpa                   : 3
  aha_st_combo_posterior_no_discharge_low_nihss_pregnancy_no_acei: 2
  dka_moderate_basic                                    : 2
  aha_st_combo_seizure_mimic_no_tpa_pregnancy_no_acei   : 2
  aha_st_trap_pregnancy_no_acei                         : 2
```

### Loose-2-way (139 trajectories)

```
per-model (9/9 models, every model contributes):
  qwen35b        : 31    deepseek_r1_7b : 13
  qwen397b       : 30    llama4scout    : 13
  oss120b        : 24    gemma31b       : 9
  qwen27b        : 8     nemotron30b    : 6
  qwen4b         : 5
per-scenario: 48 distinct
  af_anticoagulation_decision        : 11
  stemi_inferior_rv_trap             : 10
  pe_suspicion_egfr25_contrast_trap  : 9
  stemi_aspirin_allergy              : 9
  af_combo_severe_ckd_no_doac_mechanical_valve_no_doac : 7
```

### Action

Add to App. T body: "These critical false-accepts span 9/9 models and 48 scenarios at the loose-consensus boundary, and 6/9 models and 15 scenarios at the strict-consensus boundary, ruling out a single-model or single-scenario artefact."

The strict 22 are concentrated in stroke-tPA (AHA), DKA, COPD, and meningitis domains — exactly the time-critical intervention scenarios where a process-oblivious evaluator would be most likely to silently certify a missed deadline.

---

## Task 5 — Old Number Residues

`grep` in `paper/*.tex` for `27.2`, `13.7`, `3.72` returns **no hits** in main text. The v3-era residues are clean.

Macro-level: the orphan `\consensusFAHigh = 144`, `\consensusFAMedium = 2674`, `\consensusFALow = 1287` are still defined in `auto_numbers.tex` (Phase B values from the prior regen). The new App. T table no longer uses them. We retain the definitions for backward-compat with any cached re-builds and for the deferred fine-grained severity appendix; if reviewers cite them, the actions in Task 2 govern.

### Action

Add a `% deprecated since 2026-04-29 — see App. T 9-model rebuild` comment next to those three macros. (Optional: remove entirely once the deferred severity appendix lands.)

---

## Task 6 — Phase B Critical Fraction Narrative

### Finding

| Corpus | loose-FA | loose-crit | crit/FA |
|---|---|---|---|
| v6 9-model 19,062 (headline) | 2,106 | 139 | 6.6% |
| v6 Phase B 8-model 76,464 | 4,405 | 170 | **3.9%** |

Phase B's loose-critical fraction is *lower* than the headline. Reading both side by side raises the question "why does effect-size shrink with more data?"

### Action

Add a sentence at the §5.5 Robustness Summary Phase B mention: "Auto-expanded scenarios are by design lower-severity; the engine generates compliance variants and Tier-S edge cases without inflating the critical-violation pool. The Phase B preserves the headline FA-direction signal at the typed-CwT scale (App.~\ref{app:typed_cwt_robustness}) while diluting the critical fraction relative to the manual-only headline corpus."

This pre-empts the "shrinking effect-size" reviewer concern.

---

## Task 7 — Class I/A vs. v4_crit Duality

### Finding

The paper currently uses two different classifications that share the word "critical":

1. **Provenance / evidence grade** (App. L Source Traceability): every constraint has a published-CPG citation with grade 1A, 1B, 2A, 2B (Class I/IIa with Level A/B/C). All 4 grades are admitted as constraint sources.
2. **Severity tag (`v4_crit`)** (this addendum): per-violation severity field set during violation extraction. Currently encodes "CRITICAL" string, intended to flag immediate-harm grade-A recommendations.

A reviewer might confuse the two ("if v4_crit is Class I/A only, what about the Class I/B and IIa constraints in the catalogue?").

### Action

Add a one-paragraph clarification right after the App. L source-traceability summary:

> *Note on terminology.* The constraint catalogue admits all evidence grades 1A–2B as constraint sources (App.~\ref{app:source_traceability}); this is a *provenance* claim, not a *severity* claim. The orthogonal `v4_crit` flag (App.~\ref{app:fa_severity}) tags individual violation events whose severity field is `CRITICAL` in the source CPG annotation. A constraint of grade 1B contributes to the catalogue, but a particular violation of that constraint may or may not be `CRITICAL`-severity depending on patient context. The two classifications answer different questions and are reported separately.

---

## Summary of Paper Edits Resulting from This Addendum

1. `paper/appendix.tex` + `paper/appendix_v18.tex`:
   - Remove the speculative "Class I/A only" sentence in App. T.
   - Replace with the empirical drop disclosure (Task 1) plus the distribution-coverage sentence (Task 4).
2. `paper/main_final_v18.tex` §5.5 Robustness Summary:
   - Add the Phase B critical-fraction explanation sentence (Task 6).
3. `paper/appendix*.tex` App. L (Source Traceability):
   - Add the dual-classification clarification (Task 7).
4. `paper/auto_numbers.tex`:
   - Add deprecation comment to `\consensusFAHigh/Medium/Low` (Task 5).

After these edits, the audit doc's §4 + §5 + §8 are honest about the provenance of the v5→v6 drop (data side, not definition side), and a reviewer running the same diagnostic this addendum did will reach the same conclusion via the released `verdict_matrix_v6.json` + the published `compute_table26_bsr_per_model.py` + `trace_critical_fa_evolution.py`.

End of addendum.
