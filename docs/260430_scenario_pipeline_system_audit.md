# Scenario Generation Pipeline — System-Wide Audit Report

**Date**: 2026-04-30
**Scope**: 25 CPG graphs, 708 scenarios, 3 generation pipelines, scoring path
**Status**: 444 HIGH-severity + 722 MEDIUM-severity issues identified
**Trigger**: Action normalizer audit revealed pipeline-wide defects beyond normalization

---

## Executive Summary

Following the action normalizer audit (715 false OMISSIONs from synonym divergence), this audit examines the **entire guideline-to-scenario generation pipeline** for structural bugs. Ten bug classes were tested (B1–B10). Six produced findings:

| Bug Class | Severity | Count | Scoring Impact |
|-----------|----------|-------|----------------|
| **B1**: Mutually exclusive branch collection | HIGH | 13 | False OMISSIONs from unreachable branch actions |
| **B3**: Forbidden actions not normalized | MEDIUM | 691 | Missed COMMISSION violations |
| **B4**: 3 generators produce different expected_actions | HIGH | 14 | Inconsistent evaluation criteria |
| **B5**: state-precondition default True | MEDIUM | 31 | Inflated expected_actions |
| **B6**: Orphan expected_actions (not in graph) | HIGH | 397 | **481 guaranteed false OMISSIONs** |
| **B7**: global_union includes exclusive branches | HIGH | 20 | False OMISSIONs on fallback path |

Three checks returned clean: **B2** (substring ambiguity: 0), **B8** (missing graph references: 0), **B9** (exact duplicates: 0), **B10** (expected∩forbidden conflicts: 0).

### Impact Estimate

| Source | False OMISSIONs | Episodes Affected |
|--------|----------------|-------------------|
| Action normalizer (prior audit) | 715 | 712 |
| **B6**: True orphan actions | ~481 × 24 ep/scn ≈ **11,544** | ~4,728 (197 scn × 24) |
| **B1+B7**: Branch exclusivity | variable | ~360 (15 scn × 24) |
| **Total estimated** | **~12,700+** | **~5,800+** |

B6 alone potentially accounts for **10-15× more false OMISSIONs** than the normalizer bug.

---

## Bug Class Details

### B1: walk_reachable_path ALL-branch Collection (13 findings, HIGH)

**Root cause**: `walk_reachable_path(graph, working_diagnosis=None)` follows ALL conditional_next branches, collecting mandatory_actions from mutually exclusive treatment paths.

**Example** — `aha_chest_pain_evaluation`, branch node `risk_stratification`:
- **High risk branch**: `activate_cath_lab`, `arrange_pci`, `give_aspirin_loading`, `give_p2y12_inhibitor` (13 exclusive actions)
- **Intermediate risk branch**: `serial_troponin`, `stress_testing_or_cta` (4 exclusive actions)
- **Low risk branch**: `provide_discharge_instructions` (2 exclusive actions)

When `generate_scenarios_v3.py` calls `walk_reachable_path(graph, dx)` and the walk returns empty (no branch match), it falls back to `global_union` which includes ALL 19 actions. An agent treating a low-risk patient gets penalized for not activating the cath lab.

**Affected graphs** (6): `acls_cardiac_arrest`, `ada_dka_management`, `aha_chest_pain_evaluation`, `gina_asthma_exacerbation`, `kdigo_contrast_aki`, `ssc_sepsis_hour1_bundle`

### B3: forbidden_actions Never Normalized (691 findings, MEDIUM)

**Root cause**: Graph nodes store `forbidden_actions` as raw strings. `_extract_node_forbidden_actions()` in `generate_scenarios_from_cpg.py` passes them through unchanged. But `ViolationExtractor` normalizes performed actions before matching.

**Asymmetry**:
```
Graph:   forbidden_actions: ["give_nitrates"]
Agent:   performs "give_nitroglycerin"
Scorer:  normalize("give_nitroglycerin") → "give_nitroglycerin" (or different form)
         compare with "give_nitrates" → NO MATCH → COMMISSION missed
```

- 15 graph-level raw forbidden actions that normalize differently
- 676 scenario-level raw forbidden actions that normalize differently

**Scoring impact**: COMMISSION violations (agent does something forbidden) may be **missed** because the stored forbidden form doesn't match the normalized performed form. This is the **inverse** of the normalizer false-OMISSION bug: here the system is too lenient rather than too strict.

### B4: 3 Generators Produce Different expected_actions (14 findings, HIGH)

**Root cause**: Three independent scenario generators derive expected_actions using different algorithms:

| Generator | File | Method |
|-----------|------|--------|
| v3 cross-product | `generate_scenarios_v3.py` | `walk_reachable_path()` → fallback to `global_union` |
| v5 branch/trigger | `generate_scenarios_from_cpg.py` | `walk_reachable_path(dx)` per diagnosis |
| CDE-based | `generate_all_scenarios.py` | `ConstraintDerivationEngine` → activated nodes |

For the same graph, these produce **different** expected_actions:

**Example** — `ssc_sepsis_hour1_bundle`:
- auto_generated (v3/CDE): `admit_to_icu`, `assess_infection_source`, `give_stress_dose_steroids`
- sepsis_scenarios (manual): `give_alternative_mrsa_coverage`, `give_cautious_fluid_bolus`

Neither set is wrong per se — they reflect different clinical interpretation paths. But mixing them in the same benchmark means **agents are evaluated against inconsistent criteria depending on which generator produced the scenario**.

**All 14 affected graphs**: aha_chest_pain, aha_heart_failure, aha_stroke, universal_clinical_safety, atrial_fibrillation, ada_dka, cap_pneumonia, copd_exacerbation, gi_bleeding, hypertensive_emergency, kdigo_aki_full, kdigo_contrast_aki, pulmonary_embolism, ssc_sepsis

### B5: _is_node_active() Defaults True for State Preconditions (31 findings, MEDIUM)

**Root cause**: `ConstraintDerivationEngine._is_node_active()` cannot evaluate `state.*` preconditions (they reference runtime state, not patient demographics). It defaults to `True`, meaning the node's mandatory_actions are included in expected_actions even when the state condition is unmet.

**Example** — `acls_cardiac_arrest`, node `rhythm_assessment`:
- Precondition: `state.cardiac_rhythm in ['vf', 'pvt']`
- Mandatory: `['assess_rhythm', 'resume_cpr_after_shock']`
- CDE includes these for ALL patients, including those with non-shockable rhythms

31 nodes across the 25 graphs have state-based preconditions guarding 119 mandatory_actions. All are included unconditionally by CDE.

### B6: Orphan Expected Actions (397 findings, HIGH) — **LARGEST BUG**

**Root cause**: 197 scenarios contain expected_actions that don't appear in ANY field of the referenced CPG graph. These were hand-authored using clinically reasonable but non-standard action IDs.

**Refined analysis**:
- **481 true orphans**: Action IDs not in ANY graph field (mandatory, allowed, expected, forbidden)
- **1,678 semi-orphans**: In graph's allowed/expected/forbidden but NOT in mandatory_actions (walk_reachable_path wouldn't collect them)

**Top affected graphs by true orphan count**:

| Graph | True Orphans | Example Actions |
|-------|-------------|-----------------|
| `kdigo_aki_full` | 76 | `consult_hepatology`, `discontinue_ace_inhibitor`, `discontinue_nsaid` |
| `kdigo_contrast_aki` | 66 | `hold_metformin`, `avoid_nephrotoxins`, `consider_dialysis` |
| `gi_bleeding` | 52 | `arrange_emergent_egd`, `calculate_glasgow_blatchford_score` |
| `cap_pneumonia` | 47 | `add_vancomycin`, `admit_to_icu`, `calculate_psi_score` |
| `aha_chest_pain` | 46 | `blood_pressure_control`, `consult_cardiology` |

**Why this matters**: These 481 orphan expected_actions will **always** produce OMISSION violations because:
1. The agent cannot perform them (they're not in the graph's action space)
2. Even if the agent somehow outputs the exact string, the CPG engine doesn't recognize it
3. Each orphan = 1 guaranteed false OMISSION × 24 episodes (8 models × 3 runs)

**Estimated scoring impact**: ~11,544 false OMISSIONs — **16× larger** than the normalizer bug (715).

### B7: global_union Fallback Excess (20 findings, HIGH)

**Root cause**: `generate_scenarios_v3.py` (line 142):
```python
expected_per_dx[dx] = path_actions if path_actions else list(global_union)
```

When `walk_reachable_path(graph, dx)` returns empty (because the condition strings don't match via substring), the generator falls back to the global union of ALL mandatory_actions across ALL nodes. This includes actions from mutually exclusive branches.

**Example** — `kdigo_contrast_aki`, diagnosis `state.egfr < 60`:
- Branch-specific: 12 actions
- global_union: 21 actions (+9 excess from other branches)
- Excess: `hold_nephrotoxic_medications`, `serial_scr_monitoring`, `standard_contrast_administration` etc.

20 graph-diagnosis pairs affected across 6 graphs.

---

## Clean Checks

| Check | Result | Notes |
|-------|--------|-------|
| **B2**: Substring ambiguity | 0 | All conditional_next conditions use distinct strings |
| **B8**: Missing graph references | 0 | All 708 scenarios reference existing graphs |
| **B9**: Exact duplicate actions | 0 | No scenario has the same action listed twice |
| **B10**: expected∩forbidden conflict | 0 | No scenario has an action that is both expected and forbidden |

---

## Root Cause Analysis

The bugs cluster into three systemic failures:

### Failure 1: No Canonical Action Vocabulary

There is no single authoritative list of valid action IDs. Three independent sources define actions:
- CPG graph YAML fields (mandatory/allowed/forbidden)
- Manual scenario authors (expected_actions hand-written)
- CDE conditional rules (derived at generation time)

Without a shared vocabulary, manual scenarios freely invent action IDs (`calculate_glasgow_blatchford_score`) that don't exist in the graph (`gi_bleeding.yaml`).

### Failure 2: Generation-Scoring Asymmetry

The generation pipeline and scoring pipeline apply normalization inconsistently:
- **Generation**: Stores raw action IDs in `expected_actions` and `forbidden_actions`
- **Scoring (OMISSION)**: Normalizes both sides before comparison
- **Scoring (COMMISSION)**: Compares agent's normalized action against raw forbidden list

This creates blind spots in both directions.

### Failure 3: Branch-Unaware Expected Actions

All three generators struggle with branching graphs:
- v3 generator: Falls back to global_union (all branches)
- v5 generator: Depends on substring matching (`dx in cond`)
- CDE: Defaults to True for state-based preconditions

The result is that expected_actions include unreachable actions from branches the patient would never enter.

---

## Recommended Fixes

### P0: Fix True Orphan Actions (197 scenarios, 481 orphans)

**Option A** (conservative): Add orphan action IDs to graph `allowed_actions` where clinically valid.

**Option B** (preferred): Run a normalizer pass on scenario expected_actions against the graph action vocabulary. Remove or remap orphans:
```python
graph_vocab = collect_all_actions(graph)  # All fields
normalizer = ActionNormalizer()
valid_expected = []
for ea in scenario['expected_actions']:
    canonical = normalizer.normalize(ea)
    if canonical in graph_vocab or ea in graph_vocab:
        valid_expected.append(ea)
    else:
        # Try fuzzy match
        best = find_best_match(ea, graph_vocab, threshold=0.7)
        if best:
            valid_expected.append(best)
        else:
            log_warning(f"Dropping orphan: {ea}")
```

### P1: Branch-Aware Expected Actions

Replace `global_union` fallback with explicit branch tagging:
```python
# Instead of:
expected = path_actions if path_actions else global_union

# Do:
expected = path_actions  # Empty is OK — scenario belongs to no branch
scenario['branch_coverage'] = 'specific' if path_actions else 'unresolved'
```

### P2: Normalize Forbidden Actions

Apply normalizer to forbidden_actions in scenario YAML files, matching the scoring path:
```python
scenario['forbidden_actions'] = [
    normalizer.normalize(fa) for fa in scenario.get('forbidden_actions', [])
]
```

### P3: Canonical Action Vocabulary Registry

Create a per-graph action vocabulary file that all generators and manual authors must reference:
```yaml
# cpg_model/graphs/kdigo_aki_full.actions.yaml
canonical_actions:
  - order_lab_creatinine
  - order_lab_bmp
  - consult_nephrology
  # ...
aliases:
  discontinue_nsaid: hold_nephrotoxic_medications
  avoid_nephrotoxins: hold_nephrotoxic_medications
```

### P4: CI Gate

Add `scripts/ci/audit_scenario_pipeline_system.py` to CI. Gate: 0 CRITICAL, 0 B6 true orphans.

---

## Artifacts

| File | Description |
|------|-------------|
| `evidence_pack/analysis/scenario_pipeline_system_audit.json` | Full machine-readable report (1,166 findings) |
| `scripts/ci/audit_scenario_pipeline_system.py` | Audit script (10 bug classes) |
| `docs/260430_scenario_pipeline_system_audit.md` | This document |
| `docs/260430_action_normalizer_system_audit.md` | Prior action normalizer audit |

---

## Relationship to Action Normalizer Audit

| Dimension | Normalizer Audit | Pipeline Audit |
|-----------|-----------------|----------------|
| Scope | Normalizer DIRECT_MAPPINGS + synonym groups | Full generation pipeline |
| Root cause | Synonym divergence | Multiple: orphan IDs, branch collection, normalization asymmetry |
| False OMISSIONs | 715 confirmed | ~11,544 estimated (B6 alone) |
| False COMMISSIONs | 0 | Unknown (B3 creates blind spots) |
| Fix complexity | P0: 3 normalizer mappings | P0-P3: vocabulary registry + generation refactor |

The normalizer bug (715 false OMISSIONs) is a **subset** of the larger pipeline problem. B6 alone is estimated at **16× larger** impact. However, the normalizer bug is precisely confirmed while B6 is estimated and needs episode-level verification.
