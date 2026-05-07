# CGA-Bench Tier S Pre-Registration (2026-04-23)

**Authority**: This document is the pre-registration artifact for the CGA-Bench
primary benchmark inclusion set. It implements the protocol defined in the
`Rubric Version Lock` section of [`06_selection_criteria_v2.md`](./06_selection_criteria_v2.md)
(frozen 2026-04-23 — Tier thresholds S >= 15, A 11-14, B 7-10, Excluded < 7).

This supersedes the reverted `09_tier_s_plus_preregistration.md` (commit
f623eaa0, reverted at b9fbe31f).

**Inclusion threshold**: the frozen official Tier S (score >= 15). No tier change.

**Freeze commitment**: the commit introducing this file is the citable
pre-registration SHA. The final `{core_ids, heldout_ids}` list below is
authoritative as of that commit. Any subsequent change requires (a) a documented
rationale, (b) a new commit with a new pre-registration SHA, (c) re-run of affected
experiments.

---

## 1. Annotation-Quality Tiers (alpha / beta)

CGA-Bench requires every included CPG to have `data/cpg_source_properties*.json`
annotations that a reviewer can trace to the original guideline publication.
Two annotation tiers are defined:

| Tier  | Provenance | Required Evidence |
|-------|-----------|-------------------|
| **alpha** | Expert read the published source document end-to-end, assigned per-criterion scores, and recorded a verbatim `source_text` quotation for C7-C12 | Every C1-C12 field populated from source; `source_text` quotes present and reviewer-verifiable |
| **beta**  | LLM-assisted pipeline extracted per-criterion source quotes; two independent LLMs scored the 12 criteria; all disagreements human-adjudicated; all quotes human-verified against the source PDF | Per-criterion score, verbatim `source_text` quote, dual-LLM agreement record (kappa), human-verification sign-off log — all committed to the repo |

Both tiers are "authoritative" for benchmark inclusion. The distinction is
methodology, not quality; it is disclosed in the paper so reviewers can
compute tier-specific sub-analyses if they wish.

**beta is not an estimate**. The existing `bulk_A` and `bulk_B` entries are
metadata-derived estimates and are *not* beta. They are the **input pool** from
which beta candidates are promoted via the
[annotation pipeline](./10_annotation_pipeline.md) (see that doc for Method A
+ Method B specifications).

## 2. Candidate Pool (frozen at this commit)

Computed from `reports/cpg_scores_v2_full_124.json` (123-CPG merged result of
core + draft + bulk_A + bulk_B at Phase 2b completion) filtered by Tier S >= 15.

| Category | Count | Notes |
|---|--:|---|
| `core-25` CPGs at Tier S, not in current held-out | 14 | alpha; directly included in core |
| `core-25` CPGs at Tier S, in current held-out | 3 | alpha; pals, tox, apa — retained as held-out |
| `draft_auth` CPGs at Tier S, YAML present | 2 | alpha; erc_hypothermia_2021, ukka_hyperkalemia_2023 |
| `bulk_A/B` CPGs at Tier S, YAML present | 29 | beta candidates — all must be promoted through annotation pipeline before first run |
| `bulk_A/B` CPGs at Tier S, YAML absent | 28 | Deferred (YAML generation out of scope for this pre-registration) |

**Total eligible pool**: 48 CPGs with YAMLs at Tier S.

## 3. Final Inclusion Set

### 3.1 Core (43 CPGs = 16 alpha + 27 beta)

**alpha core (16)** — authoritative source-read annotation, unchanged from v2 freeze:

| graph_id | Score | Axis |
|---|--:|---|
| aha_chest_pain_evaluation | 19 | 7-6-6 |
| ssc_sepsis_hour1_bundle   | 19 | 7-6-6 |
| aha_heart_failure_2022    | 18 | 7-5-6 |
| aha_stroke_2019           | 18 | 6-6-6 |
| anaphylaxis_management    | 18 | 7-6-5 |
| gi_bleeding               | 18 | 7-6-5 |
| pulmonary_embolism        | 18 | 6-6-6 |
| acls_cardiac_arrest       | 17 | 7-5-5 |
| idsa_meningitis           | 17 | 7-6-4 |
| kdigo_contrast_aki        | 17 | 7-5-5 |
| aabb_transfusion          | 16 | ... |
| ada_dka_management        | 16 | ... |
| cap_pneumonia             | 16 | ... |
| kdigo_aki_full            | 15 | ... |
| erc_hypothermia_2021      | 18 | 7-5-6 (draft_auth) |
| ukka_hyperkalemia_2023    | 18 | 6-6-6 (draft_auth) |

**beta core (27)** — promoted from `bulk_A/B` via the annotation pipeline. The
27 is the 29-member beta_pool minus the 2 selected for held-out duty (§3.2).
Frozen list:

| graph_id | Score | Source batch |
|---|--:|---|
| ats_esicm_sccm_ards_2023 | 19 | bulk_A |
| esvs_aaa_2024 | 19 | bulk_A |
| ncs_aha_sah_2023 | 19 | bulk_A |
| nrp_neonatal_resuscitation_2020 | 19 | bulk_B |
| pals_pediatric_traumatic_arrest_2020 | 19 | bulk_B |
| sccm_pediatric_septic_shock_2020 | 19 | bulk_B |
| aha_cardiogenic_shock_2017 | 18 | bulk_A |
| aha_ttm_post_arrest_2023 | 18 | bulk_A |
| bts_pleural_disease_2023 | 18 | bulk_A |
| esvs_acute_limb_ischemia_2020 | 18 | bulk_A |
| ispad_pediatric_dka_2022 | 18 | bulk_B |
| who_severe_malaria_2023 | 18 | bulk_B |
| asam_alcohol_withdrawal_2020 | 17 | bulk_A |
| asco_tls_2023 | 17 | bulk_B |
| ash_sickle_cell_acs_2020 | 17 | bulk_B |
| baveno_vii_varices_2022 | 17 | bulk_A |
| east_damage_control_mtp_2017 | 17 | bulk_A |
| eau_obstructive_pyelonephritis_2024 | 17 | bulk_B |
| erc_drowning_2021 | 17 | bulk_B |
| ers_ats_niv_2017 | 17 | bulk_A |
| gina_pediatric_status_asthma_2024 | 17 | bulk_B |
| hrs_vt_sd_2017 | 17 | bulk_A |
| idsa_cdi_2021 | 17 | bulk_A |
| isth_ash_ttp_2020 | 17 | bulk_B |
| sccm_rsi_2019 | 17 | bulk_B |
| smfm_maternal_sepsis_2019 | 17 | bulk_B |
| wses_pelvic_trauma_reboa_2017 | 17 | bulk_A |

### 3.2 Held-out (5 CPGs = 3 alpha + 2 beta)

Held-out composition: original held-out CPGs at Tier S are retained; Tier-A
members (aba_burn=14, acog_obstetric=14) are replaced with the two
highest-scoring beta candidates in clinical domains orthogonal to the alpha
held-out members (pediatric emergency, toxicology, psych agitation).

| graph_id | Score | Tier | Origin | Replaces |
|---|--:|---|---|---|
| pals_pediatric_emergency      | 17 | alpha | core-25, original held-out | — (retained) |
| toxicology_management         | 17 | alpha | core-25, original held-out | — (retained) |
| apa_agitation_management      | 15 | alpha | core-25, original held-out | — (retained) |
| aha_acc_aortic_dissection_2022 | 19 | beta  | bulk_A | aba_burn_resuscitation (14) |
| aha_asa_ich_2022              | 19 | beta  | bulk_A | acog_obstetric_hemorrhage (14) |

**Domain orthogonality**:
- pals: pediatric emergency
- tox: poisoning
- apa: psychiatric
- aha_acc_aortic_dissection_2022: vascular emergency
- aha_asa_ich_2022: neurocritical

No domain collision with the alpha core or alpha held-out.

**Held-out isolation guarantee**: none of the 5 CPG IDs above may appear in
(a) `agent_runner/rag_corpus/`, (b) the oracle decision table, (c) any training
or tuning data path. Enforced by `scripts/experiments/heldout_runner.py` and
audited by `audit/pipeline/audit_c_scorer.py`.

### 3.3 Dropped from core-25

| graph_id | Score | Tier | Reason | Disposition |
|---|--:|---|---|---|
| aba_burn_resuscitation     | 14 | A | Ax1 society evidence (C2=1) | Scenarios moved to `configs/scenarios/_history/pre_tier_s_2026_04_23/` |
| acog_obstetric_hemorrhage  | 14 | A | Ax1 no systematic review (C3=0) | Scenarios → `_history/` |
| atrial_fibrillation        | 14 | A | Ax2 mild time-to-harm (C7=0) — not an emergency | Scenarios → `_history/` |
| gina_asthma_exacerbation   | 14 | A | Ax2 moderate severity only (C7=1) | Scenarios → `_history/` |
| hypertensive_emergency     | 14 | A | Ax1 no systematic review (C3=0) | Scenarios → `_history/` |
| status_epilepticus         | 14 | A | Ax1 society evidence (C2=1) | Scenarios → `_history/` |
| copd_exacerbation          | 13 | A | Ax3 limited formalizability | Scenarios → `_history/` |
| universal_clinical_safety  |  2 | Excluded | Meta-graph, not a real CPG | Scenarios → `_history/` |

8 CPGs dropped (7 Tier A + 1 Excluded).

### 3.4 Deferred

**bulk Tier S candidates without YAML (28)** — listed in `docs/cpg_expansion_v7/08_phase2b_phase3_pilot_report.md §3.1`. YAML generation via
`scripts/cpg_v2_phase3/generate_expansion_graphs.py` is a separate
workstream; these are not part of this pre-registration.

**β candidates whose source document is inaccessible** — per the
accessibility policy in
[`10_annotation_pipeline.md §1.1`](./10_annotation_pipeline.md#11-accessibility-first-inclusion-policy-2026-04-23-amendment),
β candidates whose PDFs cannot be obtained via Unpaywall open-access
OR institutional access are moved here in a follow-up commit. The
specific list is populated after `acquire_source_pdf.py` runs; it is a
subset of the 29 β CPGs enumerated in §3. Exclusion is recorded here;
no replacement candidate is pulled from a lower-scoring pool (core β).
For the held-out β slot, a single-replacement swap from the top of the
accessible pool is permitted and disclosed.

Examples (first 10 of 28):
- aao_acute_angle_closure_2020 (16)
- acg_acute_liver_failure_2023 (16)
- acg_acute_pancreatitis_2024 (16)
- acls_bradycardia_2020 (16)
- acog_preeclampsia_pb222_2020 (16)
- atls_primary_survey_acs_2018 (16)
- btf_severe_tbi_2017 (16)
- das_difficult_airway_2015 (16)
- esc_pericardial_tamponade_2015 (16)
- extrip_lithium_2015 (16)

## 4. Promotion Protocol (alpha and beta Gates)

Before any CPG in §3 is used in `results/full_706_v6_tier_s_2026/`:

1. **alpha gate** (applies to all 19 alpha CPGs): `data/cpg_source_properties.json`
   contains the complete authoritative entry with `source_text` quotes for
   C7-C12. Verified during Phase 1 by
   `PYTHONPATH=. python scripts/ci/audit_sources.py`.
2. **beta gate** (applies to all 29 beta CPGs): per-CPG must pass the
   annotation pipeline defined in
   [`10_annotation_pipeline.md`](./10_annotation_pipeline.md):
   - Method A: source-PDF ingestion + Qwen3.5-397B per-criterion quote
     extraction.
   - Method B: dual-LLM (Qwen3.5-397B + GPT-oss-120B) score proposal +
     agreement measurement.
   - Human verification of all scores and all quotes; tier-flip cases
     adjudicated.
   - Entry written to `data/cpg_source_properties.json` with
     `annotation_tier: beta`, `dual_llm_agreement: {...}`,
     `human_verified_by: <annotator>`, `verification_date: <ISO-8601>`.

The pre-registration freeze means **neither the core nor the held-out
list changes based on what the annotation pipeline finds**. If a beta
candidate's score drops below Tier S after human-adjudicated scoring,
the CPG is still included but flagged as `tier: A (post-annotation)` for
paper transparency — the reviewer can decide whether to exclude it in
sub-analyses. This prevents the "we moved the goalposts after seeing the
scores" attack.

## 5. Reproducibility Commitment

```
PYTHONPATH=. python scripts/score_cpg_v2.py \
  --graphs-dir cpg_model/graphs \
  --source-props-path data/cpg_source_properties.json \
  --output-prefix cpg_scores_v2_tier_s_2026
```

After Method A + B complete for all 29 beta CPGs, the above command produces
`reports/cpg_scores_v2_tier_s_2026.json`. That JSON, plus the explicit
`{core_ids, heldout_ids}` list in §3, is the submission-time state.

## 6. Change Log

| Date | Commit | Author | Change |
|------|--------|--------|--------|
| 2026-04-23 | f623eaa0 | eval_science | Phase 0 (Tier S+): reverted (ad-hoc sub-tier not in frozen rubric) |
| 2026-04-23 | b9fbe31f | eval_science | Revert f623eaa0 with rationale |
| 2026-04-23 | *(this commit)* | eval_science | Tier S pre-registration: 43 core + 5 held-out = 48 CPGs, all alpha or beta-authoritative |
