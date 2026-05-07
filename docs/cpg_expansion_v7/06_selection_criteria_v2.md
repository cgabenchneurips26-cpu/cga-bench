# CPG Selection Criteria v2 (C1-C12): Source-Document Framework

## Overview

CGA-Bench v2 replaces the original M1-M6 binary metrics (max 6 points) with a 12-criterion, 3-Axis framework (C1-C12, max 19 points) that scores **published CPG source documents**, not YAML encoding artifacts. This eliminates circular reasoning: selection criteria evaluate properties verifiable from the original guideline publication, completely independent of how the guideline was subsequently encoded into YAML graph format.

**Design principle — 3-stage separation:**

| Stage | Question | Input |
|-------|----------|-------|
| **Stage 1: Selection** (this document) | Why include this CPG? | Published source document |
| Stage 2: YAML Fidelity | Is the encoding faithful? | YAML graph vs. source document |
| Stage 3: Benchmark Contribution | Does it discriminate models? | Benchmark run results |

C1-C12 live entirely in Stage 1. No criterion reads YAML node counts, deadline fields, forbidden_actions lists, decision node types, or conditional_next dictionaries.

## 3-Axis Framework

| Axis | Criteria | Max | What it measures |
|------|----------|-----|------------------|
| **Axis 1: Trustworthiness** | C1 + C2 + C3 + C4 + C5 | 7 | Is the source guideline credible and current? |
| **Axis 2: Clinical Significance** | C6 + C7 + C8 | 6 | Does the condition matter enough to benchmark? |
| **Axis 3: Formalizability** | C9 + C10 + C11 + C12 | 6 | Can the guideline be computationally encoded? |
| **Total** | C1-C12 | **19** | |

## Tier Classification

| Tier | Score Range | Meaning |
|------|------------|---------|
| **S** | >= 15 | Flagship benchmark CPGs |
| **A** | 11-14 | Strong candidates for inclusion |
| **B** | 7-10 | Acceptable with caveats |
| **Excluded** | < 7 | Not suitable for benchmarking |

## Criterion Definitions

### Axis 1: Trustworthiness (C1-C5, max 7)

These criteria evaluate the methodological rigor and currency of the published guideline.

| Criterion | Name | Scale | Scoring |
|-----------|------|-------|---------|
| **C1** | Tier-1 Society | 0/1 | 1 if issued by a recognized Tier-1 medical society (AHA, ESC, WHO, IDSA, KDIGO, ADA, GOLD, GINA, ATS, ACOG, ABA, APA, AABB, ACMT, AES, WAO, EAACI, ACG, etc.) |
| **C2** | Evidence Grading System | 0/1/2 | 2 if formal system (GRADE, SIGN, OCEBM, ILCOR, Cochrane, NHMRC); 1 if society system (AHA Class/LOE, ESC Class/LOE, ADA grading, ACOG LOE, GINA, GOLD); 0 if none |
| **C3** | Systematic Review | 0/1 | 1 if guideline was based on systematic literature review (AGREE II Domain 3) |
| **C4** | Recency | 0/1/2 | 2 if publication year >= 2020; 1 if 2015-2019; 0 if < 2015 or unknown |
| **C5** | Documented Source | 0/1 | 1 if DOI or persistent URL exists |

**C4 Year Extraction**: Publication year is determined by a 6-level cascade from YAML metadata fields: (1) `metadata.last_update_year`, (2) `metadata.publication_year`, (3) `metadata.primary_source.year`, (4) `version` field regex, (5) `guideline_name` regex, (6) `metadata.source` regex. If all fail, score = 0.

### Axis 2: Clinical Significance (C6-C8, max 6)

These criteria evaluate whether the clinical condition warrants inclusion in an emergency medicine benchmark.

| Criterion | Name | Scale | Scoring |
|-----------|------|-------|---------|
| **C6** | Disease Burden | 0/1/2 | 2 if GBD Top-15 cause of death OR Lancet emergency condition; 1 if GBD Top-30; 0 if not ranked |
| **C7** | Time-to-Harm Severity | 0/1/2 | 2 if critical (minutes-to-hours, delay causes death/permanent disability); 1 if moderate (hours-to-days); 0 if mild (days-to-weeks) |
| **C8** | Contraindication Rules | 0/1/2 | 2 if source document explicitly lists >= 5 contraindication/forbidden-action rules; 1 if 2-4; 0 if <= 1 |

**C7 Categories** (from published source documents):

| Severity | Time Window | Examples |
|----------|-------------|----------|
| **Critical** | Minutes to hours | Cardiac arrest (ROSC), stroke (tPA 4.5h), anaphylaxis (epinephrine), sepsis (hour-1 bundle), status epilepticus |
| **Moderate** | Hours to days | DKA, pneumonia, AKI, heart failure, COPD exacerbation, GI bleeding |
| **Mild** | Days to weeks | Atrial fibrillation rate control, universal safety principles |

**C6 Data Source**: WHO Global Burden of Disease Study 2021 (GBD 2021 Causes of Death Collaborators, *Lancet* 2024;403:2100-2132) and Lancet Commission on Global Emergency Care (*Lancet* 2015;386:1867-78). Lookup table: `data/gbd_top30_causes.json`.

**C8 Source**: Expert-annotated from published source documents. The count reflects contraindication rules explicitly stated in the guideline text (e.g., "tPA contraindicated if INR > 1.7"), NOT YAML `forbidden_actions` list length.

### Axis 3: Formalizability (C9-C12, max 6)

These criteria evaluate whether the published guideline contains structural elements amenable to computational graph encoding. All scores are derived from expert review of the source document, not from the YAML encoding.

| Criterion | Name | Scale | Scoring |
|-----------|------|-------|---------|
| **C9** | Algorithm Figures | 0/1/2 | 2 if >= 3 algorithm/flowchart figures in source; 1 if 1-2; 0 if none |
| **C10** | Time Constraints | 0/1/2 | 2 if >= 5 explicit time-bound statements in source text; 1 if 2-4; 0 if <= 1 |
| **C11** | Sequence Dependency | 0/1 | 1 if source document explicitly states action ordering requirements (e.g., "obtain cultures BEFORE antibiotics") |
| **C12** | Conditional Branching | 0/1 | 1 if source document contains explicit conditional logic (e.g., "if MAP < 65 despite fluids, start vasopressor") |

**C9-C12 are NOT computed from YAML**: Even if a YAML graph has decision nodes, forbidden_actions, deadlines, or conditional_next fields, C9-C12 scores come exclusively from `data/cpg_source_properties.json`, an expert-annotated lookup table with `source_text` citations traceable to the original publication. If a graph_id is absent from the lookup table, C9-C12 all return 0.

## Source Properties Lookup Table

All C8-C12 scores (and some C1-C7 overrides) are sourced from `data/cpg_source_properties.json`. Each entry contains:

```json
{
  "graph_id": {
    "c1_tier1_society": true,
    "c2_evidence_system": "GRADE",
    "c2_evidence_system_score": 2,
    "c3_systematic_review": true,
    "c4_recency_year": 2021,
    "c5_has_doi": true,
    "c5_doi": "10.1097/CCM.0000000000004753",
    "c7_time_to_harm": "critical",
    "c7_source_text": "Each hour of delay...",
    "c8_contraindication_explicit": 2,
    "c8_source_text": "Contraindications to fibrinolysis include...",
    "c9_has_algorithm_figure": true,
    "c9_figure_count": 4,
    "c9_score": 2,
    "c10_time_constraints_explicit": true,
    "c10_time_statements_count": 8,
    "c10_score": 2,
    "c10_source_text": "Within 1 hour: blood cultures, lactate...",
    "c11_sequence_dependency_explicit": true,
    "c11_source_text": "Obtain blood cultures BEFORE antibiotic administration",
    "c12_conditional_branching_explicit": true,
    "c12_source_text": "If MAP <65 mmHg despite initial fluid..."
  }
}
```

Every `source_text` field provides a reviewer-verifiable quotation from the original CPG publication. This ensures a NeurIPS reviewer can independently confirm each score without examining the YAML encoding.

## Anti-Circular-Reasoning Guarantee

The following YAML fields are **never read** by C1-C12 scoring:

| YAML Field | Old M-metric that used it | C-metric replacement |
|------------|---------------------------|---------------------|
| `nodes[*].mandatory_actions` | M1 (deadline count) | C10 (source text time statements) |
| `nodes[*].required_prior_actions` | M2 (sequence constraint) | C11 (source text ordering) |
| `nodes[*].forbidden_actions` | M11 (forbidden count) | C8 (source text contraindications) |
| `nodes[*].node_type == "decision"` | M12 (decision nodes) | C12 (source text conditionals) |
| `nodes[*].conditional_next` | M12 (branch points) | C12 (source text conditionals) |
| `nodes[*].conditional_rules` | M6 (conditional richness) | C9 (source algorithm figures) |

This is enforced by the `TestNoCircularReasoning` test class (5 tests) which verifies that C8-C12 return 0 when no source properties are provided, regardless of how many YAML nodes, forbidden actions, or deadlines exist in the graph.

## Scoring Results (25 Active Graphs)

### Distribution
- **Tier S** (>= 15): 17 graphs
- **Tier A** (11-14): 7 graphs
- **Tier B** (7-10): 0 graphs
- **Excluded** (< 7): 1 graph (`universal_clinical_safety` — meta-graph, not a real CPG)

### Per-Axis Means
- **Trustworthiness** (C1-C5): 5.9 / 7
- **Clinical Significance** (C6-C8): 5.0 / 6
- **Formalizability** (C9-C12): 4.6 / 6

### Top Scorers

| Rank | Graph | Ax1 | Ax2 | Ax3 | Total | Tier |
|------|-------|:---:|:---:|:---:|:-----:|:----:|
| 1 | aha_chest_pain_evaluation | 7 | 6 | 6 | **19** | S |
| 1 | ssc_sepsis_hour1_bundle | 7 | 6 | 6 | **19** | S |
| 3 | aha_heart_failure_2022 | 7 | 5 | 6 | **18** | S |
| 3 | aha_stroke_2019 | 6 | 6 | 6 | **18** | S |
| 3 | anaphylaxis_management | 7 | 6 | 5 | **18** | S |
| 3 | gi_bleeding | 7 | 6 | 5 | **18** | S |
| 3 | pulmonary_embolism | 6 | 6 | 6 | **18** | S |
| 8 | acls_cardiac_arrest | 7 | 5 | 5 | **17** | S |
| 8 | idsa_meningitis | 7 | 6 | 4 | **17** | S |
| 8 | kdigo_contrast_aki | 7 | 5 | 5 | **17** | S |
| 8 | pals_pediatric_emergency | 7 | 6 | 4 | **17** | S |
| 8 | toxicology_management | 6 | 6 | 5 | **17** | S |

### Tier A Graphs (11-14)

| Graph | Ax1 | Ax2 | Ax3 | Total | Limiting Factor |
|-------|:---:|:---:|:---:|:-----:|-----------------|
| aba_burn_resuscitation | 5 | 5 | 4 | **14** | Ax1: society evidence (C2=1) |
| acog_obstetric_hemorrhage | 4 | 6 | 4 | **14** | Ax1: no systematic review (C3=0) |
| atrial_fibrillation | 7 | 3 | 4 | **14** | Ax2: mild time-to-harm (C7=0) |
| gina_asthma_exacerbation | 6 | 3 | 5 | **14** | Ax2: moderate severity only |
| hypertensive_emergency | 4 | 6 | 4 | **14** | Ax1: no systematic review (C3=0) |
| status_epilepticus | 5 | 5 | 4 | **14** | Ax1: society evidence (C2=1) |
| copd_exacerbation | 6 | 4 | 3 | **13** | Ax3: limited formalizability |

## Backward Compatibility

v1 score = C1 + min(C2, 1) + C3 + min(C4, 1) + C5 + (C9 > 0 ? 1 : 0) (max 6). C2 and C4 are capped to 1 for v1 equivalence since v1 used binary scoring.

**Invariant**: Any CPG that was v1 Tier-valid (>= 4/6) must remain >= Tier B (>= 7/19) in v2.

Status: **PASS** — all 25 current CPGs satisfy this constraint.

## Usage

```bash
# Score all graphs with source properties
PYTHONPATH=. python scripts/score_cpg_v2.py

# Custom paths
PYTHONPATH=. python scripts/score_cpg_v2.py \
    --graphs-dir cpg_model/graphs \
    --gbd-path data/gbd_top30_causes.json \
    --source-props-path data/cpg_source_properties.json \
    --output-dir reports
```

Output files:
- `reports/cpg_scores_v2.json` — machine-readable full results (per-criterion + per-axis)
- `reports/cpg_scores_v2.md` — human-readable summary table

## Test Suite

```bash
# Run all 80 tests
PYTHONPATH=. pytest tests/test_ci/test_score_cpg_v2.py -v
```

Key test classes:
- `TestC1` through `TestC12` — unit tests for each criterion
- `TestNoCircularReasoning` — 5 tests verifying C8-C12 never read YAML node structures
- `TestComputeAllScores` — integration tests with/without source properties
- `TestRealGraph` — end-to-end on SSC sepsis (19/19, Tier S), stroke (18/19, Tier S), universal_safety (2/19, Excluded)

## Rubric Version Lock

**Freeze date**: 2026-04-23
**Canonical implementation**: `scripts/score_cpg_v2.py` (base commit `b2ff0213`, JTA/JES whitelist expansion applied same session)
**Source data**: `data/cpg_source_properties.json` (25 core), `data/cpg_source_properties_candidates_draft.json` (8 approved), `data/cpg_source_properties_candidates_bulk_{A,B}.json` (90 candidates)

No criterion definitions (C1-C12), scoring formulas, tier thresholds (S>=15, A>=11, B>=7), or TIER_1_SOCIETIES membership may change after this freeze date. Any post-freeze modification requires:
1. A documented rationale in this section
2. Full re-scoring of all 123 CPGs
3. A diff report showing affected scores

**Reproduction**: Clone repo, run `PYTHONPATH=. python scripts/score_cpg_v2.py` from `cga_bench/`. Output must match `reports/cpg_scores_v2.json` (25 core: 17S/7A/0B/1Excl, mean 15.6/19).

## References

- **AGREE II**: Brouwers MC, et al. "AGREE II: Advancing guideline development, reporting and evaluation in health care." *CMAJ* 182.18 (2010): E839-E842.
- **GRADE**: Guyatt GH, et al. "GRADE guidelines: a new series of articles in the Journal of Clinical Epidemiology." *J Clin Epidemiol* 64.4 (2011): 383-394.
- **GBD 2021**: GBD 2021 Causes of Death Collaborators. "Global burden of 288 causes of death and life expectancy by country." *Lancet* 403.10440 (2024): 2100-2132.
- **Lancet Commission**: Hirshon JM, et al. "Health systems and services: the role of acute care." *Bull WHO* 91.5 (2013): 386-388.
- **SIGN**: Scottish Intercollegiate Guidelines Network. "SIGN 50: A guideline developer's handbook." (2019).
- **OCEBM**: OCEBM Levels of Evidence Working Group. "Oxford Centre for Evidence-Based Medicine Levels of Evidence." (2011).

---

## Full 123-CPG Score Distribution (Expansion Evaluation)

**Source**: `reports/cpg_scores_v2_full_124.json` (123 CPGs scored, excluding `universal_clinical_safety` meta-graph from clinical counts)

### Summary Table

| Score | Count | Cumulative (>=) | Tier |
|:-----:|:-----:|:---------------:|:----:|
| 19 | 10 | 10 | S |
| 18 | 13 | 23 | S |
| 17 | 20 | 43 | S |
| 16 | 17 | 60 | S |
| 15 | 16 | **76** | S |
| 14 | 16 | 92 | A |
| 13 | 6 | 98 | A |
| 12 | 9 | 107 | A |
| 11 | 4 | **111** | A |
| 10 | 1 | 112 | B |
| 9 | 3 | 115 | B |
| 8 | 2 | 117 | B |
| 7 | 3 | **120** | B |
| 5 | 1 | 121 | Excl |
| 4 | 1 | 122 | Excl |
| 2 | 1 | **123** | Excl |

### Per-Score CPG Lists

#### Score 19 (10 CPGs) — Perfect Score

| # | Graph ID | Guideline Name | Ax1 | Ax2 | Ax3 |
|---|----------|----------------|:---:|:---:|:---:|
| 1 | aha_acc_aortic_dissection_2022 | 2022 ACC/AHA Aortic Disease | 7 | 6 | 6 |
| 2 | aha_asa_ich_2022 | 2022 AHA/ASA Intracerebral Hemorrhage | 7 | 6 | 6 |
| 3 | aha_chest_pain_evaluation | AHA Chest Pain Evaluation | 7 | 6 | 6 |
| 4 | ats_esicm_sccm_ards_2023 | ESICM ARDS 2023 | 7 | 6 | 6 |
| 5 | esvs_aaa_2024 | ESVS Abdominal Aortic Aneurysm 2024 | 7 | 6 | 6 |
| 6 | ncs_aha_sah_2023 | 2023 AHA/NCS Subarachnoid Hemorrhage | 7 | 6 | 6 |
| 7 | nrp_neonatal_resuscitation_2020 | AHA/AAP Neonatal Resuscitation 2020 | 7 | 6 | 6 |
| 8 | pals_pediatric_traumatic_arrest_2020 | AHA PALS Traumatic Arrest 2020 | 7 | 6 | 6 |
| 9 | sccm_pediatric_septic_shock_2020 | SCCM Pediatric Septic Shock 2020 | 7 | 6 | 6 |
| 10 | ssc_sepsis_hour1_bundle | SSC Hour-1 Bundle | 7 | 6 | 6 |

#### Score 18 (13 CPGs)

| # | Graph ID | Guideline Name | Ax1 | Ax2 | Ax3 |
|---|----------|----------------|:---:|:---:|:---:|
| 1 | aha_cardiogenic_shock_2017 | AHA Cardiogenic Shock 2017 | 6 | 6 | 6 |
| 2 | aha_heart_failure_2022 | AHA/ACC/HFSA Heart Failure 2022 | 7 | 5 | 6 |
| 3 | aha_stroke_2019 | AHA/ASA Acute Ischemic Stroke 2019 | 6 | 6 | 6 |
| 4 | aha_ttm_post_arrest_2023 | AHA TTM Post-Arrest 2023 | 7 | 6 | 5 |
| 5 | anaphylaxis_management | WAO/EAACI Anaphylaxis | 7 | 6 | 5 |
| 6 | bts_pleural_disease_2023 | BTS Pleural Disease 2023 | 7 | 5 | 6 |
| 7 | erc_hypothermia_2021 | ERC Hypothermia 2021 | 7 | 5 | 6 |
| 8 | esvs_acute_limb_ischemia_2020 | ESVS Acute Limb Ischemia 2020 | 7 | 5 | 6 |
| 9 | gi_bleeding | ACG GI Bleeding 2021 | 7 | 6 | 5 |
| 10 | ispad_pediatric_dka_2022 | ISPAD Pediatric DKA 2022 | 6 | 6 | 6 |
| 11 | pulmonary_embolism | ESC Pulmonary Embolism 2019 | 6 | 6 | 6 |
| 12 | ukka_hyperkalemia_2023 | UKKA Hyperkalemia 2023 | 6 | 6 | 6 |
| 13 | who_severe_malaria_2023 | WHO Severe Malaria 2023 | 7 | 6 | 5 |

#### Score 17 (20 CPGs)

| # | Graph ID | Guideline Name | Ax1 | Ax2 | Ax3 |
|---|----------|----------------|:---:|:---:|:---:|
| 1 | acls_cardiac_arrest | AHA ACLS Cardiac Arrest | 7 | 5 | 5 |
| 2 | asam_alcohol_withdrawal_2020 | ASAM Alcohol Withdrawal 2020 | 6 | 6 | 5 |
| 3 | asco_tls_2023 | ASCO Tumor Lysis Syndrome 2023 | 6 | 6 | 5 |
| 4 | ash_sickle_cell_acs_2020 | ASH Sickle Cell ACS 2020 | 7 | 5 | 5 |
| 5 | baveno_vii_varices_2022 | Baveno VII Portal Hypertension 2022 | 5 | 6 | 6 |
| 6 | east_damage_control_mtp_2017 | EAST Damage Control / MTP 2017 | 6 | 6 | 5 |
| 7 | eau_obstructive_pyelonephritis_2024 | EAU Obstructive Pyelonephritis 2024 | 6 | 6 | 5 |
| 8 | erc_drowning_2021 | ERC Drowning 2021 | 7 | 5 | 5 |
| 9 | ers_ats_niv_2017 | ERS/ATS NIV 2017 | 6 | 6 | 5 |
| 10 | gina_pediatric_status_asthma_2024 | GINA Pediatric Status Asthma 2024 | 5 | 6 | 6 |
| 11 | hrs_vt_sd_2017 | AHA/ACC/HRS VT/SD 2017 | 6 | 6 | 5 |
| 12 | idsa_cdi_2021 | IDSA C. difficile 2021 | 7 | 6 | 4 |
| 13 | idsa_meningitis | IDSA Bacterial Meningitis | 7 | 6 | 4 |
| 14 | isth_ash_ttp_2020 | ISTH/ASH TTP 2020 | 7 | 5 | 5 |
| 15 | kdigo_contrast_aki | KDIGO Contrast-AKI | 7 | 5 | 5 |
| 16 | pals_pediatric_emergency | AHA PALS 2025 | 7 | 6 | 4 |
| 17 | sccm_rsi_2019 | SCCM Rapid Sequence Intubation 2019 | 7 | 5 | 5 |
| 18 | smfm_maternal_sepsis_2019 | SMFM Maternal Sepsis 2019 | 6 | 6 | 5 |
| 19 | toxicology_management | AACT/ACMT Toxicology | 6 | 6 | 5 |
| 20 | wses_pelvic_trauma_reboa_2017 | WSES Pelvic Trauma / REBOA 2017 | 6 | 6 | 5 |

#### Score 16 (17 CPGs)

| # | Graph ID | Guideline Name | Ax1 | Ax2 | Ax3 |
|---|----------|----------------|:---:|:---:|:---:|
| 1 | aabb_transfusion | AABB RBC Transfusion 2024 | 7 | 4 | 5 |
| 2 | aao_acute_angle_closure_2020 | AAO Angle-Closure 2020 | 6 | 5 | 5 |
| 3 | acg_acute_liver_failure_2023 | ACG Acute Liver Failure 2023 | 7 | 5 | 4 |
| 4 | acg_acute_pancreatitis_2024 | ACG Acute Pancreatitis 2024 | 7 | 4 | 5 |
| 5 | acls_bradycardia_2020 | AHA ACLS Bradycardia 2020 | 7 | 5 | 4 |
| 6 | acog_preeclampsia_pb222_2020 | ACOG Preeclampsia PB222 2020 | 6 | 6 | 4 |
| 7 | ada_dka_management | ADA DKA Management | 5 | 5 | 6 |
| 8 | atls_primary_survey_acs_2018 | ATLS Primary Survey 2018 | 4 | 6 | 6 |
| 9 | btf_severe_tbi_2017 | BTF Severe TBI 2017 | 4 | 6 | 6 |
| 10 | cap_pneumonia | IDSA/ATS CAP 2019 | 6 | 5 | 5 |
| 11 | das_difficult_airway_2015 | DAS Difficult Airway 2015 | 5 | 5 | 6 |
| 12 | esc_pericardial_tamponade_2015 | ESC Pericardial Tamponade 2015 | 6 | 5 | 5 |
| 13 | extrip_lithium_2015 | EXTRIP Lithium 2015 | 6 | 5 | 5 |
| 14 | hrs_va_catheter_ablation_2019 | HRS/EHRA VA Catheter Ablation 2019 | 5 | 6 | 5 |
| 15 | idsa_asco_febrile_neutropenia_2018 | IDSA/ASCO Febrile Neutropenia 2018 | 5 | 6 | 5 |
| 16 | tokyo_cholangitis_2018 | Tokyo Guidelines Cholangitis 2018 | 5 | 5 | 6 |
| 17 | wses_mesenteric_ischemia_2017 | WSES Mesenteric Ischemia 2017 | 6 | 5 | 5 |

#### Score 15 (16 CPGs) — Tier S Boundary

| # | Graph ID | Guideline Name | Ax1 | Ax2 | Ax3 |
|---|----------|----------------|:---:|:---:|:---:|
| 1 | aao_aha_crao_2021 | AAO/AHA CRAO 2021 | 6 | 4 | 5 |
| 2 | ada_hhs_2024 | ADA HHS 2024 | 5 | 5 | 5 |
| 3 | ada_severe_hypoglycemia_2024 | ADA Severe Hypoglycemia 2024 | 6 | 5 | 4 |
| 4 | aha_bls_fbao_2020 | AHA BLS/FBAO 2020 | 7 | 4 | 4 |
| 5 | apa_agitation_management | APA Agitation 2024 | 7 | 4 | 4 |
| 6 | asco_hypercalcemia_malignancy_2023 | ASCO Hypercalcemia of Malignancy 2023 | 7 | 4 | 4 |
| 7 | aua_testicular_torsion_2023 | AUA/EAU Testicular Torsion 2023 | 6 | 4 | 5 |
| 8 | east_penetrating_abdominal_2010 | EAST Penetrating Abdominal 2010 | 4 | 6 | 5 |
| 9 | extrip_valproate_2015 | EXTRIP Valproate 2015 | 6 | 4 | 5 |
| 10 | idsa_nsti_2014 | IDSA NSTI 2014 | 5 | 5 | 5 |
| 11 | idsa_tss_2014 | IDSA TSS/SSTI 2014 | 5 | 5 | 5 |
| 12 | jta_jes_thyroid_storm_2016 | JTA/JES Thyroid Storm 2016 | 5 | 5 | 5 |
| 13 | kdigo_aki_full | KDIGO AKI 2012 | 5 | 5 | 5 |
| 14 | nice_msc_2023 | NICE Spinal Cord Compression 2023 | 5 | 5 | 5 |
| 15 | wms_hace_hape_2024 | WMS HACE/HAPE 2024 | 6 | 4 | 5 |
| 16 | wms_heat_stroke_2024 | WMS Heat Stroke 2024 | 6 | 5 | 4 |

#### Score 14 (16 CPGs) — Tier A

| # | Graph ID | Guideline Name | Ax1 | Ax2 | Ax3 |
|---|----------|----------------|:---:|:---:|:---:|
| 1 | aan_myasthenic_crisis_2021 | AAN Myasthenic Crisis 2021 | 6 | 4 | 4 |
| 2 | aasld_hepatic_encephalopathy_2014 | AASLD Hepatic Encephalopathy 2014 | 5 | 5 | 4 |
| 3 | aba_burn_resuscitation | ABA Burn Resuscitation 2024 | 5 | 5 | 4 |
| 4 | acog_obstetric_hemorrhage | ACOG Obstetric Hemorrhage 2024 | 4 | 6 | 4 |
| 5 | acog_shoulder_dystocia_pb178_2017 | ACOG Shoulder Dystocia PB178 | 5 | 4 | 5 |
| 6 | aha_esc_endocarditis_2023 | ESC Endocarditis 2023 | 6 | 4 | 4 |
| 7 | aha_peripartum_cardiomyopathy_2020 | AHA Peripartum Cardiomyopathy 2020 | 6 | 4 | 4 |
| 8 | ascrs_diverticulitis_2020 | ASCRS Diverticulitis 2020 | 6 | 4 | 4 |
| 9 | atrial_fibrillation | AHA/ACC/HRS AF 2023 | 7 | 3 | 4 |
| 10 | ean_guillain_barre_2023 | EAN Guillain-Barre 2023 | 6 | 4 | 4 |
| 11 | ese_hyponatremia_2014 | ESE Hyponatremia 2014 | 4 | 4 | 6 |
| 12 | gina_asthma_exacerbation | GINA Asthma Exacerbation | 6 | 3 | 5 |
| 13 | hypertensive_emergency | AHA/ACC Hypertensive Emergency 2017 | 4 | 6 | 4 |
| 14 | idsa_spinal_epidural_abscess_2020 | IDSA Spinal Epidural Abscess 2020 | 6 | 3 | 5 |
| 15 | smfm_afe_2016 | SMFM Amniotic Fluid Embolism 2016 | 5 | 4 | 5 |
| 16 | status_epilepticus | AES Status Epilepticus | 5 | 5 | 4 |

#### Score 13 (6 CPGs)

| # | Graph ID | Guideline Name | Ax1 | Ax2 | Ax3 |
|---|----------|----------------|:---:|:---:|:---:|
| 1 | aasld_aact_salicylate_2015 | AASLD/AACT Salicylate 2015 | 3 | 5 | 5 |
| 2 | aospine_acute_sci_2017 | AOSpine Acute SCI 2017 | 5 | 4 | 4 |
| 3 | copd_exacerbation | GOLD COPD Exacerbation 2024 | 6 | 4 | 3 |
| 4 | idsa_epiglottitis_supraglottitis | IDSA Epiglottitis | 5 | 4 | 4 |
| 5 | sccm_delirium_padis_2018 | SCCM Delirium PADIS 2018 | 6 | 4 | 3 |
| 6 | uhms_co_hbo_2017 | UHMS CO/HBO 2017 | 4 | 4 | 5 |

#### Score 12 (9 CPGs)

| # | Graph ID | Guideline Name | Ax1 | Ax2 | Ax3 |
|---|----------|----------------|:---:|:---:|:---:|
| 1 | aact_iron_overdose_2005 | AACT Iron Overdose 2005 | 4 | 4 | 4 |
| 2 | aap_bronchiolitis_2014 | AAP Bronchiolitis 2014 | 4 | 5 | 3 |
| 3 | aha_kawasaki_2017 | AHA Kawasaki 2017 | 5 | 3 | 4 |
| 4 | davidson_shojaee_massive_hemoptysis_2020 | Massive Hemoptysis (Chest 2020) | 3 | 5 | 4 |
| 5 | east_cervical_spine_2009 | EAST Cervical Spine 2009 | 4 | 4 | 4 |
| 6 | endocrine_society_adrenal_crisis_2016 | Endocrine Society Adrenal Crisis 2016 | 5 | 3 | 4 |
| 7 | ent_uk_epistaxis_2020 | AAO-HNS Epistaxis 2020 | 6 | 2 | 4 |
| 8 | rcog_cord_prolapse_2014 | RCOG Cord Prolapse 2014 | 3 | 4 | 5 |
| 9 | wms_elapid_coral_snake_2015 | WMS Coral Snake Envenomation 2015 | 5 | 3 | 4 |

#### Score 11 (4 CPGs) — Tier A Boundary

| # | Graph ID | Guideline Name | Ax1 | Ax2 | Ax3 |
|---|----------|----------------|:---:|:---:|:---:|
| 1 | aao_orbital_cellulitis_2023 | AAO Orbital Cellulitis 2023 | 4 | 3 | 4 |
| 2 | acmt_crotaline_envenomation_2011 | ACMT Crotaline Envenomation 2011 | 4 | 3 | 4 |
| 3 | east_blunt_cardiac_injury_2012 | EAST Blunt Cardiac Injury 2012 | 4 | 3 | 4 |
| 4 | endocrine_pheo_2014 | Endocrine Society Pheochromocytoma 2014 | 4 | 3 | 4 |

#### Score 7-10 (9 CPGs) — Tier B

| # | Score | Graph ID | Guideline Name | Ax1 | Ax2 | Ax3 |
|---|:-----:|----------|----------------|:---:|:---:|:---:|
| 1 | 10 | aace_myxedema_coma_2012 | AACE Myxedema Coma 2012 | 3 | 4 | 3 |
| 2 | 9 | bimdg_iem_crisis_2017 | BIMDG IEM Crisis 2017 | 1 | 4 | 4 |
| 3 | 9 | east_open_fracture_2012 | EAST Open Fracture 2012 | 3 | 3 | 3 |
| 4 | 9 | nsw_rhabdomyolysis_2022 | NSW Rhabdomyolysis 2022 | 2 | 3 | 4 |
| 5 | 8 | aace_sccm_icu_hypernatremia_2021 | AACE/SCCM Hypernatremia 2021 | 3 | 2 | 3 |
| 6 | 8 | isth_dic_2013 | ISTH DIC 2013 | 3 | 2 | 3 |
| 7 | 7 | atls_electrical_injury_2018 | ATLS Electrical Injury 2018 | 2 | 2 | 3 |
| 8 | 7 | nms_gurrera_consensus_2011 | NMS Consensus (Gurrera) 2011 | 1 | 3 | 3 |
| 9 | 7 | serotonin_syndrome_boyer_shannon_2005 | Serotonin Syndrome (Boyer) 2005 | 1 | 3 | 3 |

#### Score < 7 (3 CPGs) — Excluded

| # | Score | Graph ID | Guideline Name | Ax1 | Ax2 | Ax3 | Reason |
|---|:-----:|----------|----------------|:---:|:---:|:---:|--------|
| 1 | 5 | ludwig_peritonsillar_abscess | Ludwig Angina / PTA | 0 | 2 | 3 | No Tier-1 society, no evidence grading |
| 2 | 4 | asco_nccn_svc_syndrome | NCCN/ASCO SVC Syndrome | 0 | 2 | 2 | No Tier-1 society, no evidence grading |
| 3 | 2 | universal_clinical_safety | Universal Clinical Safety | 0 | 2 | 0 | Meta-graph, not a real CPG |
