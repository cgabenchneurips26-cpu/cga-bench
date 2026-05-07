# CAV / ActionNormalizer Gap Audit for v7.3 SGSC Benchmark

**Date**: 2026-05-02 03:20 UTC
**Auditor**: Claude Opus 4.6
**Scope**: 418 SGSC scenarios across 49 graphs vs. runtime `ActionNormalizer`
**Verdict**: **LAUNCH BLOCKER** -- 82.1% false OMISSION rate if run as-is

---

## 1. Executive Summary

The v7.3 SGSC benchmark runner (`full_v73_runner.py`) uses `assessor_core/action_normalizer.py` for all action ID matching during scoring. This normalizer contains ~1,147 hardcoded `_DEFAULT_DIRECT_MAPPINGS` entries. The SGSC compiler generates novel action IDs (e.g., `achieve_sustained_virological_response`, `apply_cirrhosis_prophylaxis_guidelines`) that do **not** exist in the normalizer's mappings.

| Metric | Value |
|--------|-------|
| SGSC unique expected_actions | **840** |
| SGSC unique forbidden_actions | **328** |
| Expected actions **UNMAPPED** by normalizer | **743 / 840 (88.5%)** |
| Forbidden actions **UNMAPPED** by normalizer | **324 / 328 (98.8%)** |
| Scenario-level expected_action references unmapped | **837 / 1,019 (82.1%)** |
| CAV v0.6 coverage of ALL unmapped actions | **100%** (1,067/1,067) |
| CAV v0.6 wired to scoring pipeline | **No** |

**Bottom line**: If v7.3 launches without a fix, ~82% of mandatory-action checks will produce false OMISSIONs. Every model will appear to "fail" on SGSC scenarios regardless of actual performance. CGA scores, FA counts, eta-squared, Kendall W will all be dominated by normalizer noise.

---

## 2. Architecture: Why This Happens

### 2.1 Runtime Scoring Path (NO CAV)

```
Agent output
  -> ActionNormalizer.normalize()       # assessor_core/action_normalizer.py
     -> _DEFAULT_DIRECT_MAPPINGS        # ~1,147 hardcoded Python dict entries
     -> domain_specific_mappings        # ~35 additional per-domain entries
     -> synonym_groups                  # ~20 synonym clusters
     -> pattern rules                   # ~15 regex patterns
     -> fuzzy matching (Jaccard 0.7)    # last resort
  -> ViolationExtractor._action_satisfies_requirement()
     -> exact match
     -> conditional_next prefix match
     -> ActionNormalizer alias check
  -> OMISSION if no match found
```

### 2.2 CAV v0.6 (BUILT but NOT WIRED)

```
cav_v0_6/cav_v0_6.json              # 2,276 entries (built for v7.3 corpus)
scripts/cav/cav_validator.py        # load_cav(), is_in_cav(), filter_action_list()
  -> ONLY imported by:
     - scripts/sgsc/rescore_v6_with_cav.py  (post-hoc analysis, not runtime)
     - tests/test_cav/test_cav_validator.py  (unit tests)
  -> NOT imported by:
     - assessor_core/*
     - eval_harness/*
     - full_v73_runner.py
     - full_690_runner.py
```

### 2.3 SGSC Action ID Origin

SGSC-generated action IDs are **NOT sourced from graph nodes**. The compiler invents novel, natural-language-style IDs based on guideline text:

| Graph | SGSC expected | In graph nodes | SGSC-only | Overlap |
|-------|---------------|----------------|-----------|---------|
| baveno_vii_varices_2022 | 115 | 16 | **114 (99.1%)** | 1 |
| esvs_aaa_2024 | 97 | 21 | **94 (96.9%)** | 3 |
| aha_stroke_2019 | 68 | 135 | **41 (60.3%)** | 27 |
| ssc_sepsis_hour1_bundle | 7 | 46 | **5 (71.4%)** | 2 |

This is the root cause: the SGSC compiler generates human-readable action IDs from guideline source text, while the scoring engine expects IDs matching graph node `mandatory_actions`/`allowed_actions`/`forbidden_actions` fields.

---

## 3. Coverage Analysis

### 3.1 Expected Actions (840 unique)

| Category | Count | % |
|----------|------:|---:|
| Mapped (normalizer transforms) | 1 | 0.1% |
| Identity (already a known canonical) | 96 | 11.4% |
| **UNMAPPED (pass-through, unknown)** | **743** | **88.5%** |

### 3.2 Forbidden Actions (328 unique)

| Category | Count | % |
|----------|------:|---:|
| Mapped (normalizer transforms) | 0 | 0.0% |
| Identity (already a known canonical) | 4 | 1.2% |
| **UNMAPPED (pass-through, unknown)** | **324** | **98.8%** |

### 3.3 CAV v0.6 Recovery Potential

| Unmapped set | In CAV v0.6 | Still missing |
|-------------|-------------|---------------|
| 743 expected | **743 (100%)** | 0 |
| 324 forbidden | **324 (100%)** | 0 |

CAV v0.6 (2,276 entries) was specifically built to cover v7.3 SGSC actions. Wiring it in would close the gap entirely.

### 3.4 Per-Graph Impact (Top 15 by unmapped count)

| Graph | Unmapped expected | Sample unmapped IDs |
|-------|------------------:|---------------------|
| baveno_vii_varices_2022 | 112 | achieve_sustained_virological_response, prescribe_nsbb |
| esvs_aaa_2024 | 97 | adjust_stent_graft_size, apply_alara_radioprotection |
| aha_stroke_2019 | 40 | achieve_tici_2b_reperfusion, admit_icu_stroke_unit |
| aha_acc_aortic_dissection_2022 | 38 | consider_aortic_root_surgery, add_acei_arb |
| aha_heart_failure_2022 | 37 | assess_advanced_therapy_candidacy, assess_gdmt_duration |
| ncs_aha_sah_2023 | 25 | counsel_cognitive_risk, elevate_systolic_bp |
| aba_burn_resuscitation | 24 | apply_clean_dry_dressing, assess_burn_center_criteria |
| gina_asthma_exacerbation | 23 | assess_inhaler_technique, ensure_ics_prescription |
| gina_pediatric_status_asthma_2024 | 23 | determine_disposition, give_continuous_salbutamol_nebulized |
| status_epilepticus | 22 | assess_antiepileptic_drug_levels, give_dextrose_50_percent |
| ada_dka_management | 21 | add_potassium_to_fluids, monitor_anion_gap |
| kdigo_contrast_aki | 21 | apply_restrictive_transfusion_threshold, assess_aki_risk_factors |
| toxicology_management | 21 | assess_decontamination_indication, give_iv_n_acetylcysteine |
| acls_cardiac_arrest | 18 | analyze_rhythm, apply_aed, give_amiodarone_300mg |
| ats_esicm_sccm_ards_2023 | 18 | apply_intermittent_sighs, initiate_prone_positioning |

### 3.5 Unmapped Action Prefix Distribution (Top 15)

| Prefix | Count | Pattern |
|--------|------:|---------|
| order_lab | 38 | `order_lab_*` (novel lab types not in mappings) |
| give_iv | 17 | `give_iv_*` (IV medication variants) |
| perform_aortic | 5 | vascular domain |
| monitor_bp | 4 | monitoring variants |
| assess_clinical | 3 | assessment variants |
| consider_aortic | 3 | aortic decision points |
| consider_tips | 3 | hepatology-specific |
| give_albumin | 3 | fluid variants |
| give_calcium | 3 | electrolyte correction |
| give_isotonic | 3 | crystalloid variants |
| measure_aortic | 3 | vascular measurements |
| monitor_blood | 3 | monitoring variants |
| perform_endoscopic | 3 | GI procedures |
| perform_liver | 3 | hepatology procedures |
| perform_primary | 3 | primary interventions |

---

## 4. Impact on v7.3 Results

### 4.1 Scoring Path Consequences

For each unmapped `expected_action`:
1. Agent outputs action → normalizer returns lowercased pass-through (e.g., `"give_iv_crystalloid"`)
2. Scenario expects `"give_iv_crystalloid"` in mandatory set
3. `_action_satisfies_requirement()` checks:
   - Exact match: **FAIL** (agent likely outputs different synonym)
   - Conditional prefix match: **FAIL** (no `_if_` pattern)
   - Normalizer alias check: **FAIL** (both sides unmapped, no alias resolution)
4. Result: **OMISSION violation** regardless of clinical correctness

For unmapped `forbidden_action`:
1. `_normalize_forbidden_set()` normalizes forbidden IDs
2. Unmapped forbidden IDs pass through as-is
3. Agent action normalized separately (also pass-through if unmapped)
4. Result: **Missed COMMISSION** if agent performs the forbidden action with a synonym

### 4.2 Metric Corruption Estimates

| Metric | Expected corruption |
|--------|-------------------|
| OMISSION count | +82% inflated (false positives) |
| CGA score | Depressed by ~0.3-0.5 across all models |
| FA (Full Adherence) rate | Near 0% for SGSC scenarios |
| eta-squared (evaluator) | Dominated by normalizer variance, not model variance |
| Kendall W (model ranking) | Meaningless if all models fail on same normalizer gap |
| COMMISSION detection | Reduced (missed forbidden matches) |

### 4.3 Cross-contamination Risk

If v7.3 SGSC results are mixed with v6 baseline results:
- v6 scenarios use graph-native action IDs (11.5% coverage is the existing v6 subset)
- SGSC scenarios use compiler-invented IDs (88.5% unmapped)
- Combined analysis would show artificial domain effect (expansion graphs "harder" due to normalizer gap)

---

## 5. Root Causes

### RC-1: SGSC Compiler Generates Novel Action IDs
`sgsc/compilers/scenario_compiler.py` creates action IDs from guideline text spans, not from graph node fields. This produces IDs like `achieve_sustained_virological_response` that have no mapping in the normalizer.

### RC-2: ActionNormalizer is Hardcoded, Not Data-Driven
`_DEFAULT_DIRECT_MAPPINGS` is a 1,147-entry Python dict maintained manually. It was built for the original 25 CPG graphs (~690 scenarios) and was never extended for SGSC output.

### RC-3: CAV v0.6 Built but Not Integrated
`cav_v0_6.json` contains 2,276 entries covering 100% of SGSC actions, but exists only as a file artifact. No code imports it at runtime.

### RC-4: No Vocabulary Gate in SGSC Pipeline
The SGSC compiler has no validation step to ensure generated action IDs exist in the normalizer or CAV before emitting scenarios.

---

## 6. Fix Options

### Option A: Wire CAV v0.6 into ActionNormalizer (Recommended)

**Mechanism**: At `ActionNormalizer.__init__()`, load `cav_v0_6.json` entries as additional `direct_mappings`.

```python
# In ActionNormalizerConfig or ActionNormalizer.__init__
import json, os
cav_path = os.environ.get("CAV_PATH", "cav_v0_6/cav_v0_6.json")
if Path(cav_path).is_file():
    cav = json.loads(Path(cav_path).read_text())
    for entry_id, entry in cav.get("entries", {}).items():
        canonical = entry.get("canonical_id", entry_id)
        for alias in entry.get("aliases", []):
            self.config.direct_mappings[alias.lower()] = canonical.lower()
```

**Pros**: Zero-change to SGSC scenarios, full coverage, environment-variable switchable
**Cons**: Runtime dependency on JSON file, needs testing for collision with existing mappings
**Risk**: Low (additive only, existing mappings take precedence)

### Option B: Inject Graph-Native IDs into SGSC Scenarios

**Mechanism**: Post-process SGSC scenarios to replace compiler-generated IDs with their graph-node equivalents using CAV v0.6 as the translation table.

**Pros**: No runtime change needed
**Cons**: Lossy (SGSC IDs that map to no graph node get dropped), requires re-compilation
**Risk**: Medium (may change scenario semantics)

### Option C: Expand _DEFAULT_DIRECT_MAPPINGS Statically

**Mechanism**: Generate and paste ~1,000 new entries into `action_normalizer.py` from CAV v0.6.

**Pros**: No runtime file dependency
**Cons**: Massive dict growth (1,147 -> ~2,200), maintenance burden, merge conflicts
**Risk**: Low

### Option D: SGSC Compiler Vocabulary Gate (Prevention)

**Mechanism**: Add a validation pass in `scenario_compiler.py` that rejects or maps action IDs not in the normalizer/CAV before writing scenarios.

**Pros**: Prevents the problem at source
**Cons**: Does not fix existing 418 scenarios, requires SGSC recompile
**Risk**: Low (complementary to A/B/C)

---

## 7. Recommendation

**Immediate (pre-launch)**: Option A -- wire CAV v0.6 into ActionNormalizer via environment variable.
**Medium-term**: Option D -- add vocabulary gate to SGSC compiler.
**Verification**: Re-run this audit after fix to confirm 0% unmapped rate.

**Do NOT launch v7.3 benchmark without one of these fixes.**

---

## 8. Artifacts

| File | Description |
|------|-------------|
| `/tmp/cav_audit_full.json` | Full audit data (per-graph, per-action breakdown) |
| `cav_v0_6/cav_v0_6.json` | CAV v0.6 artifact (2,276 entries, 100% SGSC coverage) |
| `assessor_core/action_normalizer.py` | Runtime normalizer (1,147 direct mappings) |
| `scripts/cav/cav_validator.py` | CAV loader module (not wired to scoring) |

---

## Appendix A: CAV Artifact Comparison

| Property | CAV v0.5 | CAV v0.6 |
|----------|----------|----------|
| Entries | 1,364 | 2,276 |
| Built for | v6 (25 graphs, 690 scenarios) | v7.3 (49 graphs, 418 SGSC scenarios) |
| Default path | `cav_v0_5/cav_v0_5.json` | `cav_v0_6/cav_v0_6.json` |
| Runtime integration | None | None |
| SGSC unmapped coverage | Not tested | **100%** |

## Appendix B: Full Unmapped Action ID Lists

See `/tmp/cav_audit_full.json` for complete lists:
- `unmapped_expected`: 743 action IDs
- `unmapped_forbidden`: 324 action IDs
- `per_graph_unmapped_expected`: per-graph breakdown with full ID lists
