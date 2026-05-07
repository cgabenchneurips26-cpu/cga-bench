# Option B Auto-Graph Quality Audit & Root Cause Analysis

**Date**: 2026-04-30
**Pipeline**: 2-step LLM (Gemma-4-31B-IT on 145:30210)
**Code**: `scripts/cpg_v2_phase_annotation/generate_graph_from_corpus.py` + `auto_graph_pipeline.py`

## 1. optB Graph Quality Summary (13 graphs)

| Graph | C1-C12 | Corpus Recs | Triaged→Actionable | Val Errors | V/G/U | Grade |
|-------|:------:|:-----------:|:------------------:|:----------:|:-----:|:-----:|
| esvs_aaa_2024 | 19/S | 265 | 197→160 | 1 | 6/1/0 | **A+** |
| aha_acc_aortic_dissection_2022 | 19/S | 139 | 87→78 | 3 | 4/3/0 | **A+** |
| pals_pediatric_traumatic_2020 | 19/S | 6 | 6→6 | 2 | 2/2/0 | **A** |
| ats_esicm_sccm_ards_2023 | 19/S | 65 | 6→6 | 0 | — | B+ |
| aha_ttm_post_arrest_2023 | 18/S | 17 | 7→7 | 0 | — | B+ |
| baveno_vii_varices_2022 | 17/S | 243 | 10→10 | 0 | — | B+ |
| idsa_cdi_2021 | 17/S | 30 | 10→10 | 0 | — | B+ |
| ncs_aha_sah_2023 | 19/S | 37 | 3→3 | 0 | — | B- |
| aha_cardiogenic_shock_2017 | 18/S | 6 | 6→1 | 6 | 0/4/2 | D |
| nrp_neonatal_resuscitation_2020 | 19/S | 3 | 3→1 | 3 | 1/2/1 | C |
| bts_pleural_disease_2023 | 18/S | ~~1~~ → 23 | ~~0→0~~ → 20→20 | ~~6~~ → 0 | ~~0/0/8~~ → 8/0/0 | ~~F~~ → **A** |
| sccm_pediatric_septic_shock_2020 | 19/S | ~~43~~ → 24 | ~~0→0~~ → 24→23 | ~~5~~ → 0 | ~~0/1/5~~ → 6/0/0 | ~~F~~ → **A** |
| wses_pelvic_trauma_reboa_2017 | 17/S | ~~1~~ → 31 | ~~0→0~~ → 24→22 | ~~6~~ → 0 | ~~0/1/5~~ → 6/0/0 | ~~F~~ → **A** |

### Grading Criteria

| Grade | Criteria |
|-------|----------|
| A+ | triaged>50, val_errors≤3, UNGROUNDED=0 |
| A | triaged>0, val_errors≤2, UNGROUNDED≤1, grounding run done |
| B+ | triaged>0, val_errors=0, NO grounding run yet |
| B- | triaged>0, val_errors=0, small actionable count |
| C | triaged>0, significant drop triaged→actionable, grounding mixed |
| D | triaged>0, heavy val_errors, mostly GROUNDED/UNGROUNDED |
| F | triaged=0, all quotes hallucinated, fully ungrounded |

### Legend
- **V/G/U**: VERIFIED / GROUNDED / UNGROUNDED quote counts (from `ground_graph_quotes.py`)
- **"—"**: grounding script not run on this graph
- **Val Errors**: `validation_errors` from `_generation_pipeline` metadata

## 2. Root Cause Analysis

### Primary Finding: Quality = f(corpus_quality)

The quality difference between A+ and F grades is **entirely determined by RAG corpus quality**, not the LLM pipeline itself.

```
Corpus Quality → Triage Output → Graph Quality
  (PDF parser)    (Step 1 LLM)    (Step 2 LLM)
```

### Three Bottlenecks Identified

#### BOTTLENECK 1: PDF Parser Output Quality

The `data_release/v5.0/rag_corpus/*.parsed.json` files contain recommendations extracted from guideline PDFs. The parser quality varies drastically:

| Corpus File | Size | Rec Count | Content Quality |
|------------|------|-----------|-----------------|
| esvs_aaa_2024.parsed.json | 278 KB | 265 | Real clinical recommendations |
| aha_acc_aortic_dissection_2022.parsed.json | 164 KB | 139 | Real clinical recommendations |
| bts_pleural_disease_2023.parsed.json | 2.7 KB | 1 | Paper title/author block only |
| wses_pelvic_trauma_reboa_2017.parsed.json | 2.5 KB | 1 | Paper title/author block only |
| sccm_pediatric_septic_shock_2020.parsed.json | 16 KB | 43 | GRADE statistical table cells |

**Evidence**: BTS-2023-Pleural's single "recommendation" is literally the paper title and author list. SCCM-2020's 43 "recommendations" are all GRADE evidence table cells (e.g., "Weak recommendation, low-quality evidence") — not actual clinical recommendations.

#### BOTTLENECK 2: No Quality Gate at Triage Stage

When Step 1 (Triage) returns `actionable_count=0`, the pipeline still proceeds to Step 2 (Graph Structuring). Step 2 then generates a fully hallucinated graph with fabricated source_quotes.

**Code location**: `generate_graph_from_corpus.py` lines 346-348:
```python
actionable = triaged[:5]  # empty list when triaged=0
# Step 2 proceeds regardless
```

**Fix needed**: Abort when `actionable_count == 0` or `triaged_count < MIN_THRESHOLD`.

#### BOTTLENECK 3: Step 2 Hallucinates Without Input

When given an empty or near-empty triage output, Step 2 generates plausible-looking but completely fabricated clinical content:
- Invents source_quote text that doesn't exist in the corpus
- Creates reasonable-sounding action_ids from domain knowledge
- Assigns arbitrary recommendation_class and evidence_level

This is visible in the F-grade graphs where `_quote_verification.status = UNGROUNDED` for 5-8 out of 7-8 nodes.

## 3. Corpus Size vs Quality Correlation

```
Corpus Size (bytes)    Rec Count    Grade
───────────────────    ─────────    ─────
278,266 (esvs_aaa)      265          A+
163,533 (aha_aortic)    139          A+
101,643 (baveno_vii)    243          B+
 47,117 (ards_2023)      65          B+
 25,261 (ncs_sah)        37          B-
 16,099 (sccm_ped)       43*         F   ← *all GRADE tables
  9,430 (idsa_cdi)       30          B+
  8,074 (aha_ttm)        17          B+
  3,767 (pals_trauma)     6          A
  3,449 (aha_cs)           6          D
  2,737 (bts_pleural)     1*         F   ← *title only
  2,522 (wses_pelvic)     1*         F   ← *title only
  1,757 (nrp_neonatal)    3          C
```

Key observations:
- **Quantity matters**: >100 recs → A+ grade (when recs are real)
- **Quality trumps quantity**: sccm has 43 recs but all are GRADE tables → F
- **Small but valid corpora work**: pals has only 6 recs but they're real → A grade
- **Threshold**: ≥3 real clinical recommendations → C or better

## 4. 28 Unscored Auto Graphs

28 of the 59 auto-generated optA graphs were never submitted for C1-C12 scoring. These come from the RAG corpus directory but were not included in the scoring candidate pools (source_properties + bulk_A + bulk_B batches).

**Full list**: aagbi_perioperative_hemorrhage_2016, acc_aha_valvular_heart_disease_2020, acg_peptic_ulcer_bleed_2021, acs_colorectal_cancer_2021, acs_pancreatic_cancer_2021, aha_acc_coronary_revascularization_2021, aha_acc_peripheral_artery_disease_2024, asco_breast_cancer_adjuvant_2024, asco_lung_cancer_screening_2023, btf_severe_tbi_2020, bts_community_pneumonia_2009, eaaci_drug_allergy_2022, eacts_aortic_valve_2021, eacts_esc_myocardial_revascularization_2024, eanm_esc_cardiac_amyloidosis_2023, esc_acute_coronary_syndrome_2023, esc_hcm_2024, esc_infective_endocarditis_2023, esge_acute_lower_gi_bleed_2021, esmo_gastric_cancer_2022, eucast_antimicrobial_susceptibility_2024, ilcor_neonatal_resuscitation_2020, nccn_melanoma_2024, nsclc_molecular_testing_2023, sign_acute_coronary_syndrome_2023, who_hiv_2023, wses_acute_appendicitis_2020, wses_perforated_peptic_ulcer_2020

## 5. Upgrade Path

| Current Grade | Action Required | Expected Outcome |
|:---:|---|---|
| B+ (4 graphs) | Run `ground_graph_quotes.py` only | → A or A- |
| B- (1 graph) | Run grounding + review triage | → B+ or A- |
| D (1 graph) | Review corpus, possibly re-triage | → B or C |
| C (1 graph) | Improve corpus quality | → B+ |
| F (3 graphs) | **Rebuild PDF corpus first** | → depends on PDF quality |

### F-Grade Remediation Plan

For the 3 F-grade graphs, the fix is **not** in the pipeline code — it's in the input data:

1. **Re-parse PDFs** for bts_pleural_disease_2023, sccm_pediatric_septic_shock_2020, wses_pelvic_trauma_reboa_2017
2. **Verify** extracted recommendations contain actual clinical content
3. **Re-run** optB pipeline on rebuilt corpora
4. **Ground** resulting graphs with `ground_graph_quotes.py`

### Pipeline Code Fix (prevent future F-grades)

Add quality gate in `generate_graph_from_corpus.py`:
```python
if len(actionable) == 0:
    logger.warning(f"No actionable recommendations for {graph_id} — aborting Step 2")
    return {"status": "FAIL", "reason": "no_actionable_recommendations"}
```

## 6. F-Grade Remediation Results (2026-04-30)

All 3 F-grade corpora were rebuilt and the optB pipeline re-run + grounded.

### Corpus Rebuild Summary

| CPG | Old Recs | Old Problem | New Recs | Source Method |
|-----|:--------:|-------------|:--------:|---------------|
| WSES Pelvic Trauma | 1 | Paper title/abstract only | **31** | BMC open-access PDF + custom `[Grade XY]` regex |
| SCCM Ped Septic Shock | 43 | All GRADE statistical table cells | **24** | SCCM.org public guidelines page (WebFetch) |
| BTS Pleural Disease | 1 | Paper title/author block only | **23** | PMC review article PMC11037506 (WebFetch) |

### Before → After Comparison

| Graph | Before | | | After | | | Grade |
|-------|:------:|:---:|:---:|:-----:|:---:|:---:|:-----:|
| | Triaged→Act | Val Err | V/G/U | Triaged→Act | Val Err | V/G/U | |
| wses_pelvic_trauma_reboa_2017 | 0→0 | 6 | 0/1/5 | 24→22 | 0 | **6/0/0** | F → **A** |
| sccm_pediatric_septic_shock_2020 | 0→0 | 5 | 0/1/5 | 24→23 | 0 | **6/0/0** | F → **A** |
| bts_pleural_disease_2023 | 0→0 | 6 | 0/0/8 | 20→20 | 0 | **8/0/0** | F → **A** |

### Key Findings

1. **100% VERIFIED**: All 20 source_quote fields across the 3 graphs matched corpus text exactly — zero GROUNDED or UNGROUNDED
2. **Zero validation errors**: All 3 regenerated graphs passed structural validation cleanly
3. **Root cause confirmed**: The pipeline itself (Gemma-4-31B-IT) works correctly when given real clinical recommendations. The F-grades were entirely a corpus input quality problem.

### Updated Grade Distribution (13 optB graphs)

| Grade | Count | Graphs |
|:-----:|:-----:|--------|
| A+ | 2 | esvs_aaa, aha_aortic_dissection |
| A | 4 | pals_traumatic, **wses_pelvic** ↑, **sccm_ped_septic** ↑, **bts_pleural** ↑ |
| B+ | 4 | ats_ards, aha_ttm, baveno_vii, idsa_cdi |
| B- | 1 | ncs_sah |
| C | 1 | nrp_neonatal |
| D | 1 | aha_cardiogenic_shock |
| F | 0 | *(all remediated)* |
