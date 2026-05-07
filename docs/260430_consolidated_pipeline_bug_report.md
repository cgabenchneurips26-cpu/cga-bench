# CGA-Bench Scoring Pipeline — Consolidated Bug Report

**Date**: 2026-04-30
**Version**: v1.0
**Scope**: Full guideline→scenario→scoring pipeline across v5 (21,723 episodes) and v6a (20,704 episodes)
**Total confirmed scoring bugs**: 8 classes, ~24,294 (v5) / ~28,142 (v6a) false violation events

---

## 1. Pipeline Architecture Overview

### 1.1 How the Pipeline Works

The CGA-Bench scoring pipeline has four major stages:

```
┌─────────────┐     ┌──────────────────┐     ┌─────────────────┐     ┌──────────────────┐
│  CPG Graph   │────▶│ Scenario Generator │────▶│ Episode Runner   │────▶│ ViolationExtractor│
│  (25 YAML)   │     │ (3 generators)     │     │ (full_690_runner) │     │ (violations.py)   │
└─────────────┘     └──────────────────┘     └─────────────────┘     └──────────────────┘
      │                      │                        │                        │
   nodes with             expected_actions          agent performs           compare expected
   mandatory/allowed/     forbidden_actions         actions via LLM         vs performed →
   forbidden actions      stored in YAML                                    OMISSION/COMMISSION
```

#### Stage 1: CPG Graphs (`cpg_model/graphs/*.yaml`)

25 YAML files define clinical protocol graphs. Each graph contains:
- **Nodes** (dict, not list): keyed by `node_id`, each with:
  - `mandatory_actions`: Actions the agent MUST perform
  - `allowed_actions`: Actions the agent MAY perform
  - `forbidden_actions`: Actions the agent MUST NOT perform
  - `conditional_next`: Branch transitions based on patient state
  - `preconditions`: Conditions for node activation (demographics or `state.*`)

#### Stage 2: Scenario Generators

Three independent generators derive `expected_actions` from graphs:

| Generator | File | Algorithm |
|-----------|------|-----------|
| **v3 cross-product** | `generate_scenarios_v3.py` | `walk_reachable_path()` → fallback to `global_union` of ALL nodes |
| **v5 branch/trigger** | `generate_scenarios_from_cpg.py` | `walk_reachable_path(dx)` per working diagnosis |
| **CDE-based** | `generate_all_scenarios.py` | `ConstraintDerivationEngine` → activated nodes via precondition eval |

**`walk_reachable_path()` implementation** (`generate_scenarios_from_cpg.py:442-517`):
- BFS traversal starting from `initial_assessment` node
- Collects `mandatory_actions` from each visited node
- When `working_diagnosis` is provided: follows only branches where `working_diagnosis in condition_string` (substring match)
- When `working_diagnosis` is `None`: follows ALL `conditional_next` branches (lines 507-510)
- Result: list of mandatory actions along the reachable path

**`global_union` fallback** (`generate_scenarios_v3.py:128-142`):
```python
global_union: list[str] = []
seen: set[str] = set()
for node in (graph.get("nodes") or {}).values():
    for a in node.get("mandatory_actions") or []:
        if a not in seen:
            global_union.append(a)
            seen.add(a)
```
When `walk_reachable_path(graph, dx)` returns empty, falls back to this union of ALL mandatory actions.

**CDE `_is_node_active()` logic** (`constraint_derivation.py:589-613`):
```python
if "state." in precond_str:
    return True  # Cannot evaluate runtime state → default True
```
State-based preconditions always default to `True`, including all node actions unconditionally.

#### Stage 3: Episode Runner (`full_690_runner.py:921-943`)

```python
expected_actions = scenario_def.expected_actions or []
# ... runs agent episode ...
result = runner.run_episode(
    scenario_expected_actions=expected_actions if expected_actions else None
)
```
Passes scenario-level `expected_actions` directly from YAML to the scoring pipeline.

#### Stage 4: ViolationExtractor (`violations.py:630-752`)

**R2 design**: Uses `scenario_expected_actions` as the primary OMISSION source.

**`_action_satisfies_requirement()` (lines 630-667)** — 4-step matching:
1. **Exact match**: `performed_action == expected_action`
2. **Normalize both**: `normalize(performed) == normalize(expected)`
3. **Alias check**: `are_aliases(performed, expected)`
4. **Conditional match**: Pattern-based for conditional actions (e.g., `start_vasopressor_if_hypotensive`)

**`_check_omissions()` (lines 669-752)**:
- For each `expected_action`, checks if ANY performed action satisfies it via 4-step matching
- If no match found → records OMISSION violation
- Normalizes the expected_action before comparison: `normalize(raw_mandatory, cpg_id)`

**CDE rescoring** (`runner.py:298`):
```python
if self.config.enable_cde_rescoring and patient_context_for_cde is not None:
    # CDE supplements constraints — OPTIONAL
```
CDE-derived constraints are an optional supplement, not the primary scoring source.

---

## 2. Bug Inventory

### 2.1 Action Normalizer Bugs (715 confirmed false OMISSIONs)

Source: `docs/260430_action_normalizer_system_audit.md`

| Bug ID | Pattern | Graph | Actions | Mandatory | False OMISSIONs |
|--------|---------|-------|---------|-----------|-----------------|
| N1 | circular_alias | `kdigo_contrast_aki` | `assess_urine_output` ↔ `monitor_urine_output` | Yes | 217 |
| N2 | assessment_verb | `idsa_meningitis` | `assess_neurological_status` ↔ `monitor_neurological_status` | Yes | 477 |
| N3 | word_order_flip | `ada_dka_management` | `consult_endocrinology` ↔ `endocrinology_consult` | No | 18 |
| N4 | prefix_lab | `kdigo_contrast_aki` | `order_creatinine` ↔ `order_lab_creatinine` | No | 3 |
| N5 | prefix_imaging | `pulmonary_embolism` | `order_ecg` ↔ `order_imaging_ecg` | No | 0 (latent) |
| N6 | verb_dropped | `aha_stroke_2019` | `give_osmotic_therapy` ↔ `osmotic_therapy` | No | 0 (latent) |
| N7 | circular_alias | (normalizer-level) | `assess_urine_output` ↔ `monitor_urine_output` | Yes | (same as N1) |
| **Total** | | | | | **715** |

**Root cause**: ActionNormalizer performs single-pass lookup. Circular aliases (A→B, B→A) never converge. Synonym pairs from CPG graphs normalize to different canonical forms.

**Causal chain**:
```
CPG graph defines "assess_X" in node A + "monitor_X" in node B
  → Auto-generator collects BOTH into expected_actions (no semantic dedup)
    → Agent performs "monitor_X" (one form)
      → ViolationExtractor: normalize("assess_X") ≠ normalize("monitor_X")
        → FALSE OMISSION recorded
```

### 2.2 Pipeline Bugs (B1–B10)

Source: `docs/260430_scenario_pipeline_system_audit.md`

| Bug Class | Severity | Count | Description | Scoring Impact |
|-----------|----------|-------|-------------|----------------|
| **B1** | HIGH | 13 | `walk_reachable_path` follows ALL branches → collects mutually exclusive actions | False OMISSIONs from unreachable branch actions |
| **B2** | CLEAN | 0 | Substring ambiguity in conditional_next conditions | — |
| **B3** | MEDIUM | 691 | `forbidden_actions` stored raw, never normalized | Missed COMMISSION violations (system too lenient) |
| **B4** | HIGH | 14 | 3 generators produce DIFFERENT expected_actions for same graph | Inconsistent evaluation criteria |
| **B5** | MEDIUM | 31 | `_is_node_active()` defaults True for `state.*` preconditions | Inflated expected_actions |
| **B6** | HIGH | 397 | Orphan expected_actions not in ANY graph field | **481 guaranteed false OMISSIONs per episode** |
| **B7** | HIGH | 20 | `global_union` fallback includes exclusive branches | False OMISSIONs on fallback path |
| **B8** | CLEAN | 0 | Missing graph references | — |
| **B9** | CLEAN | 0 | Exact duplicate actions | — |
| **B10** | CLEAN | 0 | expected ∩ forbidden conflicts | — |

---

## 3. v5 vs v6a Comparative Impact Analysis

### 3.1 Dataset Overview

| Metric | v5 | v6a |
|--------|----|----|
| Total episodes | 21,723 | 20,704 |
| Total OMISSION events | 103,855 | 107,280 |
| Total expected_actions evaluated | 281,479 | 268,646 |
| Mean OMISSIONs per episode | 4.78 | 5.18 |

### 3.2 Bug Attribution

| Bug Source | v5 False OMISSIONs | % of Total | v6a False OMISSIONs | % of Total |
|------------|-------------------|------------|--------------------|-----------|
| **B6**: True orphan actions | 9,141 | 8.8% | 11,670 | 10.9% |
| **Normalizer**: Synonym divergence | 15,153 | 14.6% | 16,472 | 15.4% |
| **B6+Normalizer combined** | **24,294** | **23.4%** | **28,142** | **26.2%** |
| Remaining (legitimate + other bugs) | 79,561 | 76.6% | 79,138 | 73.8% |

### 3.3 B6 Orphan Analysis by Graph

Orphan expected_actions = action IDs in scenario `expected_actions` that do NOT appear in ANY field of the referenced CPG graph.

| Graph | True Orphans | Example Actions | v5 Orphan OMISSIONs | v6a Orphan OMISSIONs |
|-------|-------------|-----------------|--------------------|--------------------|
| `kdigo_aki_full` | 76 | `consult_hepatology`, `discontinue_ace_inhibitor`, `discontinue_nsaid` | High | High |
| `kdigo_contrast_aki` | 66 | `hold_metformin`, `avoid_nephrotoxins`, `consider_dialysis` | High | High |
| `gi_bleeding` | 52 | `arrange_emergent_egd`, `calculate_glasgow_blatchford_score` | High | High |
| `cap_pneumonia` | 47 | `add_vancomycin`, `admit_to_icu`, `calculate_psi_score` | Moderate | Moderate |
| `aha_chest_pain` | 46 | `blood_pressure_control`, `consult_cardiology` | Moderate | Moderate |
| Others (10+ graphs) | 194 | Various | Distributed | Distributed |
| **Total** | **481** | | **9,141** | **11,670** |

**Why B6 always causes false OMISSIONs**: These 481 action IDs are not in the graph's action space. The agent cannot perform them (the CPG engine doesn't recognize them), and even if the agent somehow outputs the exact string, the 4-step matching in ViolationExtractor cannot find them in any canonical form. Each orphan = 1 guaranteed false OMISSION per episode.

### 3.4 Normalizer Synonym Analysis

Synonym pairs = episodes where BOTH synonym forms appear in `expected_actions` (from different graph nodes).

| Metric | v5 | v6a |
|--------|----|----|
| Normalizer synonym pair occurrences | 13,666 | 13,321 |
| Confirmed false OMISSIONs from synonym divergence | 15,153 | 16,472 |
| Scenarios with orphan actions (B6) | 192 | 192 |

**v6a has MORE false OMISSIONs despite FEWER episodes** because:
1. v6a includes models that perform fewer actions overall (more OMISSIONs across the board)
2. The orphan/synonym ratio increases when agents perform fewer of the orphan-adjacent actions
3. Both datasets share the SAME scenario YAML files — the B6 orphan count (481) is identical

### 3.5 How Each Pipeline Stage Propagates Bugs

```
Stage         │ v5 Path                      │ v6a Path                     │ Bug Exposure
──────────────┼──────────────────────────────┼──────────────────────────────┼─────────────
CPG Graphs    │ Same 25 YAML files           │ Same 25 YAML files           │ B1, B5, B7
              │                              │                              │ (identical)
──────────────┼──────────────────────────────┼──────────────────────────────┼─────────────
Scenario YAML │ Same 708 scenarios           │ Same 708 scenarios           │ B3, B4, B6
              │ 192 with B6 orphans          │ 192 with B6 orphans          │ (identical)
──────────────┼──────────────────────────────┼──────────────────────────────┼─────────────
CDE           │ enable_cde_rescoring=False   │ enable_cde_rescoring=False   │ B5 latent
              │ (not used in full_690_runner)│ (not used in full_690_runner)│ (not active)
──────────────┼──────────────────────────────┼──────────────────────────────┼─────────────
Runner        │ full_690_runner.py           │ full_690_runner.py           │ Passes
              │ scenario_def.expected_actions │ scenario_def.expected_actions│ bug-laden
              │ → ViolationExtractor         │ → ViolationExtractor         │ expected_actions
──────────────┼──────────────────────────────┼──────────────────────────────┼─────────────
Scoring       │ R2 design: scenario_expected │ R2 design: scenario_expected │ N1-N7 active
              │ as primary OMISSION source   │ as primary OMISSION source   │ (normalizer)
```

**Key finding**: CDE (`_is_node_active()` defaults True for state.*) is NOT active in either v5 or v6a runs. The `enable_cde_rescoring` flag is False in `full_690_runner.py`. Bug B5 (31 nodes with inflated expected_actions from state preconditions) is **latent** — it would surface only if CDE rescoring is enabled.

---

## 4. Detailed Bug Class Analysis

### 4.1 B1: Mutually Exclusive Branch Collection (13 findings, HIGH)

**Root cause**: `walk_reachable_path(graph, working_diagnosis=None)` follows ALL `conditional_next` branches, collecting mandatory_actions from mutually exclusive treatment paths.

**Example** — `aha_chest_pain_evaluation`, node `risk_stratification`:
- High risk branch: `activate_cath_lab`, `arrange_pci`, `give_aspirin_loading`, `give_p2y12_inhibitor` (13 exclusive actions)
- Intermediate risk branch: `serial_troponin`, `stress_testing_or_cta` (4 exclusive actions)
- Low risk branch: `provide_discharge_instructions` (2 exclusive actions)

When `generate_scenarios_v3.py` generates a low-risk patient scenario but `walk_reachable_path` returns empty (no branch match), the `global_union` fallback includes ALL 19 actions. The agent treating a low-risk patient gets penalized for not activating the cath lab.

**Affected graphs** (6): `acls_cardiac_arrest`, `ada_dka_management`, `aha_chest_pain_evaluation`, `gina_asthma_exacerbation`, `kdigo_contrast_aki`, `ssc_sepsis_hour1_bundle`

**Scoring impact**: Variable — depends on how many scenarios fall back to `global_union`. Estimated ~360 episodes affected (15 scenarios × 24 ep/scn).

### 4.2 B3: Forbidden Actions Never Normalized (691 findings, MEDIUM)

**Root cause**: Graph nodes store `forbidden_actions` as raw strings. The generation pipeline passes them through unchanged. But ViolationExtractor normalizes performed actions before matching.

**Asymmetry**:
```
Graph:   forbidden_actions: ["give_nitrates"]
Agent:   performs "give_nitroglycerin"
Scorer:  normalize("give_nitroglycerin") → "give_nitroglycerin" (or different form)
         compare with "give_nitrates" → NO MATCH → COMMISSION missed
```

- 15 graph-level raw forbidden actions that normalize differently
- 676 scenario-level raw forbidden actions that normalize differently

**Scoring impact**: COMMISSION violations (agent does something forbidden) may be **missed** because the stored forbidden form doesn't match the normalized performed form. This is the **inverse** of the normalizer false-OMISSION bug: the system is too lenient rather than too strict.

### 4.3 B4: Generator Inconsistency (14 findings, HIGH)

Three generators derive different `expected_actions` for the same graph:

**Example** — `ssc_sepsis_hour1_bundle`:
- auto_generated (v3/CDE): `admit_to_icu`, `assess_infection_source`, `give_stress_dose_steroids`
- sepsis_scenarios (manual): `give_alternative_mrsa_coverage`, `give_cautious_fluid_bolus`

Neither set is wrong — they reflect different clinical interpretation paths. But mixing them in the same benchmark means agents are evaluated against inconsistent criteria.

**All 14 affected graphs**: aha_chest_pain, aha_heart_failure, aha_stroke, universal_clinical_safety, atrial_fibrillation, ada_dka, cap_pneumonia, copd_exacerbation, gi_bleeding, hypertensive_emergency, kdigo_aki_full, kdigo_contrast_aki, pulmonary_embolism, ssc_sepsis

### 4.4 B5: State-Precondition Default True (31 findings, MEDIUM)

**Root cause**: CDE `_is_node_active()` cannot evaluate `state.*` preconditions (runtime state, not demographics). Defaults to `True`.

**Example** — `acls_cardiac_arrest`, node `rhythm_assessment`:
- Precondition: `state.cardiac_rhythm in ['vf', 'pvt']`
- Mandatory: `['assess_rhythm', 'resume_cpr_after_shock']`
- CDE includes these for ALL patients, including non-shockable rhythms

31 nodes across 25 graphs have state-based preconditions guarding 119 mandatory_actions.

**v5/v6a impact**: **None** — CDE rescoring is disabled in `full_690_runner.py`. This bug is latent.

### 4.5 B6: Orphan Expected Actions (397 findings, HIGH) — LARGEST BUG

**Root cause**: 197 scenarios contain expected_actions that don't appear in ANY field of the referenced CPG graph. These were hand-authored using clinically reasonable but non-standard action IDs.

**Refined analysis**:
- **481 true orphans**: Action IDs not in ANY graph field (mandatory, allowed, expected, forbidden)
- **1,678 semi-orphans**: In graph's allowed/expected/forbidden but NOT in mandatory_actions

**Why this is guaranteed to produce false OMISSIONs**:
1. The action ID is not in the graph's vocabulary
2. `walk_reachable_path()` would never collect it
3. The agent has no way to "perform" an action not in the graph
4. ViolationExtractor's 4-step matching cannot resolve it
5. Each orphan = 1 guaranteed false OMISSION × N episodes

**Estimated scoring impact**:
- v5: **9,141 false OMISSIONs** (8.8% of all OMISSIONs)
- v6a: **11,670 false OMISSIONs** (10.9% of all OMISSIONs)

### 4.6 B7: global_union Fallback Excess (20 findings, HIGH)

**Root cause**: `generate_scenarios_v3.py` line 142:
```python
expected_per_dx[dx] = path_actions if path_actions else list(global_union)
```

When `walk_reachable_path(graph, dx)` returns empty (substring matching fails), falls back to the global union of ALL mandatory_actions from ALL nodes — including mutually exclusive branches.

20 graph-diagnosis pairs affected across 6 graphs.

---

## 5. Root Cause Taxonomy

### Failure 1: No Canonical Action Vocabulary

Three independent sources define action IDs without a shared vocabulary:
- CPG graph YAML fields (mandatory/allowed/forbidden) — authored by guideline experts
- Manual scenario `expected_actions` — hand-written by different authors
- CDE-derived constraints — computed at generation time

Without a single authoritative list, manual scenarios freely invent IDs (`calculate_glasgow_blatchford_score`) that don't exist in the graph (`gi_bleeding.yaml`).

### Failure 2: Generation-Scoring Asymmetry

| Pipeline Stage | Normalization Applied |
|----------------|----------------------|
| Scenario generation (expected_actions) | **None** — stored raw |
| Scenario generation (forbidden_actions) | **None** — stored raw |
| Scoring: OMISSION check | Normalizes BOTH sides before comparison |
| Scoring: COMMISSION check | Normalizes agent action, compares against RAW forbidden list |

This asymmetry creates blind spots in both directions:
- Too strict: Raw expected_actions with non-standard IDs → false OMISSIONs (B6)
- Too lenient: Raw forbidden_actions that don't match normalized performed actions → missed COMMISSIONs (B3)

### Failure 3: Branch-Unaware Expected Actions

All three generators struggle with branching graphs:
- v3 generator: Falls back to `global_union` (all branches)
- v5 generator: Depends on substring matching (`dx in cond`)
- CDE: Defaults True for state-based preconditions

Result: `expected_actions` include unreachable actions from branches the patient would never enter.

---

## 6. Impact Summary

### 6.1 Quantitative Impact

| Source | v5 False OMISSIONs | v6a False OMISSIONs | Direction |
|--------|-------------------|--------------------|-----------|
| B6 orphan actions | 9,141 | 11,670 | Too strict (false penalty) |
| Normalizer divergence | 15,153 | 16,472 | Too strict (false penalty) |
| B3 forbidden normalization | Unknown | Unknown | Too lenient (missed penalty) |
| B1+B7 branch excess | Variable (~360 ep) | Variable (~360 ep) | Too strict (false penalty) |
| B5 state-precondition | 0 (latent) | 0 (latent) | Latent |
| **Total quantified** | **~24,294** | **~28,142** | |
| **% of all OMISSIONs** | **~23.4%** | **~26.2%** | |

### 6.2 Per-Graph Severity Ranking

| Graph | Bug Classes | Total Issues | Scoring Reliability |
|-------|------------|-------------|---------------------|
| `kdigo_aki_full` | B1, B4, B6 (76 orphans) | Very High | LOW |
| `kdigo_contrast_aki` | B1, B4, B6 (66 orphans), B7, N1, N4 | Very High | LOW |
| `gi_bleeding` | B4, B6 (52 orphans) | High | LOW |
| `cap_pneumonia` | B4, B6 (47 orphans) | High | LOW |
| `aha_chest_pain` | B1, B4, B6 (46 orphans), B7 | High | LOW |
| `idsa_meningitis` | N2 (477 false OMISSION) | High | MEDIUM |
| `ada_dka_management` | B1, B4, N3 | Moderate | MEDIUM |
| `ssc_sepsis` | B1, B4, B7 | Moderate | MEDIUM |
| `aha_stroke_2019` | B4, N6 | Low | HIGH |
| `pulmonary_embolism` | B4, N5 | Low | HIGH |
| Others (15 graphs) | B3, B5 only | Low | HIGH |

### 6.3 What This Means for Published Results

The canonical paper numbers (v6 baseline: 16,944 episodes) are computed from scoring that includes ~24-26% false OMISSIONs. This affects:

| Paper Metric | Current Value | Likely Direction After Fix |
|--------------|---------------|---------------------------|
| CGA pass rate | 52.1% | ↑ (fewer false OMISSIONs) |
| AC pass rate | 72.2% | Unchanged (action coverage is different metric) |
| MAB pass rate | 52.7% | ↑ (MAB uses mandatory action completion) |
| C2 mandatory completion | 47.7% | ↑ (direct impact from removing false OMISSIONs) |
| η²(eval) verdict flip | 0.284 | ↓ (less evaluator-driven variance) |

**Critical caveat**: The 24-26% estimate is for OMISSION events, not episodes. Many episodes have multiple OMISSIONs, and removing bug-induced OMISSIONs may not flip the overall episode verdict if legitimate OMISSIONs remain.

---

## 7. Recommended Remediation

### P0: Fix B6 True Orphan Actions (481 orphans, 197 scenarios)

**Option A** (conservative): Add orphan action IDs to graph `allowed_actions` where clinically valid.

**Option B** (preferred): Normalizer pass on scenario expected_actions:
```python
graph_vocab = collect_all_actions(graph)  # mandatory + allowed + forbidden
normalizer = ActionNormalizer()
valid_expected = []
for ea in scenario['expected_actions']:
    canonical = normalizer.normalize(ea)
    if canonical in graph_vocab or ea in graph_vocab:
        valid_expected.append(ea)
    else:
        best = find_best_match(ea, graph_vocab, threshold=0.7)
        if best:
            valid_expected.append(best)
        else:
            log_warning(f"Dropping orphan: {ea}")
```

### P1: Fix Normalizer Divergences (3 fixes)

1. Add `"assess_neurological_status": "monitor_neurological_status"` to DIRECT_MAPPINGS
2. Add `"endocrinology_consult": "consult_endocrinology"` to DIRECT_MAPPINGS
3. Break `assess_urine_output` ↔ `monitor_urine_output` circular alias

### P2: Branch-Aware Expected Actions

Replace `global_union` fallback:
```python
# Instead of:
expected = path_actions if path_actions else global_union
# Do:
expected = path_actions  # Empty is OK
scenario['branch_coverage'] = 'specific' if path_actions else 'unresolved'
```

### P3: Normalize Forbidden Actions

```python
scenario['forbidden_actions'] = [
    normalizer.normalize(fa) for fa in scenario.get('forbidden_actions', [])
]
```

### P4: Canonical Action Vocabulary Registry + CI Gate

```yaml
# cpg_model/graphs/kdigo_aki_full.actions.yaml
canonical_actions:
  - order_lab_creatinine
  - consult_nephrology
aliases:
  discontinue_nsaid: hold_nephrotoxic_medications
```

CI script: `scripts/ci/audit_scenario_pipeline_system.py` — gate: 0 CRITICAL, 0 B6 true orphans.

---

## 8. Artifacts Index

| File | Description |
|------|-------------|
| `docs/260430_action_normalizer_system_audit.md` | Normalizer audit (715 false OMISSIONs) |
| `docs/260430_scenario_pipeline_system_audit.md` | Pipeline audit (B1-B10, 1,166 findings) |
| `docs/260430_consolidated_pipeline_bug_report.md` | This document |
| `evidence_pack/analysis/action_normalizer_system_audit.json` | Normalizer findings (machine-readable) |
| `evidence_pack/analysis/scenario_pipeline_system_audit.json` | Pipeline findings (machine-readable) |
| `evidence_pack/analysis/pipeline_bug_impact_v5_v6a.json` | v5/v6a quantitative impact |
| `scripts/ci/audit_action_normalizer_system.py` | Normalizer audit script |
| `scripts/ci/audit_scenario_pipeline_system.py` | Pipeline audit script (10 bug classes) |

---

## 9. Relationship Between Audits

```
                    ┌───────────────────────────────────────┐
                    │       Consolidated Bug Report         │
                    │          (this document)              │
                    └──────────────┬────────────────────────┘
                                   │
                    ┌──────────────┴────────────────────┐
                    │                                    │
          ┌─────────▼──────────┐            ┌───────────▼──────────┐
          │  Normalizer Audit  │            │   Pipeline Audit     │
          │  (715 false OMIS.) │            │   (B1-B10, 1,166)    │
          └─────────┬──────────┘            └───────────┬──────────┘
                    │                                    │
                    │   SUBSET                           │
                    │   ◄──────────────────────────────  │
                    │                                    │
                    │  The normalizer bug (715)           │
                    │  is a subset of B6 (9,141-11,670). │
                    │  B6 is the dominant source.         │
                    └────────────────────────────────────┘
```

The normalizer bug (715 confirmed false OMISSIONs) was discovered first but represents only ~3-5% of total bug-induced false OMISSIONs. B6 orphan actions (9,141-11,670) are ~16× larger in impact. Together, B6 + normalizer account for ~24-26% of all OMISSION events in v5/v6a datasets.
