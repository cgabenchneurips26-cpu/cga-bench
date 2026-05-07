# Session B Starter Prompt

You are working on Track-B of CGA-Bench Path D Day 2-3 expansion: extracting patient profile catalog from v6 manual scenarios, adjusting cluster bounds, and implementing patient profile expansion in SGSC compilation.

## Context

We've completed Track-3 SGSC determinism (DET 25-graph rollout: 787 atoms, 142 scenarios). anonymous-user identified that:
1. v6 706 scenarios contain implicit patient profiles that v7 SGSC compilation should capture
2. Patent-state conditioning is paper §1 contribution Theorem 1 Case (iv) — currently 0 in v7
3. Cluster bound (3-10) is conservative; could extract 250+ scenarios with 2-8

This session implements all three corrections to produce v7.1 corpus.

## Critical constraints

- DO NOT re-run atom_proposer (787 atoms are frozen as DET production artifact)
- DO NOT change atom_proposer code
- DO NOT change ActionNormalizer (sanity checks PASS, fixes are validated)
- All work is post-extraction compilation logic

## Repo layout (verify first)

- v6 scenarios: `configs/scenarios/*.yaml` + `configs/scenarios/auto/*.yaml` (skip auto_v2/)
- v7 atoms: `sgsc_output/v7_e3_combined_overnight/{25 graphs}/atoms_smoke.json`
- SGSC scenario_compiler: locate via `grep -rn "CLUSTER_MIN\|CLUSTER_MAX" sgsc/`
- Tests: `tests/test_sgsc/`

After each task, STOP and print "B-N COMPLETE" with 3-line summary. Wait for user confirmation.

═════════════════════════════════════════════════════════════════
TASK B-1: v6 patient profile catalog extraction (45 min)
═════════════════════════════════════════════════════════════════

OBJECTIVE: Extract patient profile distribution from v6 706 manual scenarios to create a catalog SGSC compilation can reference.

STEPS:

1. Locate v6 scenarios. Verify count:
   find configs/scenarios -name "*.yaml" -not -path "*auto_v2*" | wc -l
   Expected: 706 (or close; report exact count)

2. Schema discovery: Read 5 random scenario YAMLs. Identify which fields hold patient profile information. Common candidates:
   - population_criteria
   - inclusion_criteria
   - exclusion_criteria
   - patient_context
   - patient_state
   - clinical_context
   Document actual field names found.

3. Create scripts/sgsc/extract_v6_profiles.py:
   - Walk all 706 v6 scenario YAMLs (skip auto_v2/)
   - For each scenario, extract patient profile fields identified in step 2
   - Categorize each profile into the following dimensions (regex + heuristics):
     * age_group: neonate (<28d), pediatric (<18), adult (18-64), elderly (>=65), unspecified
     * pregnancy: pregnant, breastfeeding, postpartum, none
     * comorbidity: ckd (stage), diabetes, hypertension, cad, chf, copd, asthma,
                    immunocompromised, pregnancy_related, none
     * allergy: penicillin, sulfa, contrast, aspirin, latex, multiple, none
     * severity: mild, moderate, severe, critical, life_threatening, unspecified
     * special_state: anticoagulated, on_steroids, intubated, septic_shock, none
   - Produce frequency table per dimension
   - Identify top-N most frequent profile combinations (where combination = age_group × pregnancy × dominant_comorbidity × severity)

4. Output:
   data/v6_patient_profile_catalog.json with schema:
   {
     "metadata": {"n_scenarios": 706, "extraction_date": "..."},
     "dimensions": {
       "age_group": {"neonate": N, "pediatric": N, ...},
       "pregnancy": {...},
       "comorbidity": {...},
       "allergy": {...},
       "severity": {...},
       "special_state": {...}
     },
     "profile_combinations": [
       {"name": "elderly_ckd_severe_anticoagulated", "n_scenarios": 47, "dimensions": {...}},
       ...
     ]
   }
   reports/path_d_day2/v6_profile_extraction.md (human-readable)

5. Validation: Top 15 profile combinations should account for >=60% of v6 scenarios. If not, profile categorization may be too narrow; consider adding dimensions.

DELIVERABLES:
- scripts/sgsc/extract_v6_profiles.py
- data/v6_patient_profile_catalog.json
- reports/path_d_day2/v6_profile_extraction.md

STOP. Print "B-1 COMPLETE — N profile dimensions, M profile combinations, top-15 covers X% of v6 scenarios". Wait.

═════════════════════════════════════════════════════════════════
TASK B-2: Same-graph parity diagnosis (kdigo_contrast_aki) (30 min)
═════════════════════════════════════════════════════════════════

OBJECTIVE: Quantify how v7 12 scenarios on kdigo_contrast_aki compares to v6 28 scenarios on the same graph.

STEPS:

1. Locate:
   - v6 kdigo_contrast_aki scenarios: configs/scenarios/*kdigo_contrast*.yaml + configs/scenarios/auto/*kdigo_contrast*.yaml (skip auto_v2/)
   - v7 kdigo_contrast_aki scenarios: sgsc_output/v7_e3_combined_overnight/kdigo_contrast_aki/scenarios.json

2. Per-scenario metrics:
   - n_mandatory_actions
   - n_forbidden_actions
   - n_total_constraints (mandatory + forbidden + sequence + timing)
   - patient profile dimensions (from B-1 catalog)

3. Aggregate comparison:

   | Metric                      | v6 (n=28) | v7 (n=12) | Ratio |
   |-----------------------------|-----------|-----------|-------|
   | Mean mandatory_actions      | ?         | ?         | ?     |
   | Mean forbidden_actions      | ?         | ?         | ?     |
   | Profile dimension coverage  | ?         | ?         | ?     |
   | Edge density (mand/forb)    | ?         | ?         | ?     |

4. Profile distribution comparison:
   - Which v6 patient profiles are present? Which absent in v7?
   - This identifies what patient profile expansion (B-4) needs to capture.

DELIVERABLES:
- reports/path_d_day2/v7_v6_same_graph_parity.md
- Console summary: "v7 covers X% of v6 patient profile distribution; gap is concentrated in Y dimension"

STOP. Print "B-2 COMPLETE". Wait.

═════════════════════════════════════════════════════════════════
TASK B-3: SGSC scenario_compiler cluster bound adjustment (5 min)
═════════════════════════════════════════════════════════════════

OBJECTIVE: Loosen cluster bounds to enable more scenarios per atom group.

STEPS:

1. Locate the scenario_compiler. Find CLUSTER_MIN, CLUSTER_MAX constants.

2. Change:
   CLUSTER_MIN: 3 → 2
   CLUSTER_MAX: 10 → 8
   (FORBIDDEN_ACTIONS_CAP: keep at 15)

3. Run existing tests: PYTHONPATH=. pytest tests/test_sgsc/ -v
   All must pass.

4. Re-compile 25-graph corpus (atoms unchanged):
   PYTHONPATH=. python scripts/sgsc/recompile_corpus.py \
     --atoms-dir sgsc_output/v7_e3_combined_overnight/ \
     --output-dir sgsc_output/v7_1_cluster_only/

   Or: locate the scenario_compiler script and run with new cluster bounds.

5. Per-graph scenario count comparison:
   v7.0 (cluster 3-10): 142 scenarios
   v7.1-cluster (cluster 2-8): expected ~200-250

DELIVERABLES:
- Modified scenario_compiler with new bounds
- Test pass confirmation
- sgsc_output/v7_1_cluster_only/ directory with re-compiled scenarios
- Console: per-graph scenario count delta table

STOP. Print "B-3 COMPLETE — total scenarios v7.0 142 → v7.1-cluster X". Wait.

═════════════════════════════════════════════════════════════════
TASK B-4: Patient profile expansion implementation (45-60 min)
═════════════════════════════════════════════════════════════════

OBJECTIVE: Implement profile-aware scenario compilation that creates one scenario per (atom-cluster × applicable patient profile) combination.

STEPS:

1. Create scripts/sgsc/patient_profile_expansion.py with:

```python
def extract_atom_applicable_profiles(atom: dict, profile_catalog: dict) -> list[str]:
    """Determine which patient profiles this atom applies to.
    
    Logic:
    1. Parse atom.source_quote for patient context cues:
       - "in patients with renal failure" → renal_failure profile activates
       - "for adults" → exclude pediatric
       - "avoid in pregnancy" → makes atom FORBIDDEN for pregnancy
    2. Default profile applies to all atoms (no special context).
    3. Return list of profile names from catalog.
    """
    applicable = ["default"]
    quote_lower = atom.get("source_quote", "").lower()
    
    # Pattern matching against profile catalog
    for profile_name, profile_data in profile_catalog["profile_combinations"].items():
        # Match logic per dimension (age, pregnancy, comorbidity, etc.)
        # ...
        pass
    
    return applicable

def expand_cluster_with_profiles(
    cluster: list[dict],
    profile_catalog: dict,
    max_profiles_per_cluster: int = 4
) -> list[dict]:
    """Generate one scenario per (cluster × applicable profile)."""
    # Find profiles applicable to ALL atoms in cluster (intersection)
    # OR profiles applicable to ANY atom (union)
    # Decision: intersection for medical safety (constraints must apply to all)
    # ...
    scenarios = []
    for profile in applicable_profiles[:max_profiles_per_cluster]:
        scenarios.append(compile_scenario(cluster, profile))
    return scenarios

def compile_scenario(cluster: list[dict], profile: str) -> dict:
    """Build scenario YAML with profile-specific population_criteria and forbidden_actions."""
    # Population criteria: union of atoms × intersection with profile
    # Forbidden actions: graph-level + profile-specific (e.g., pregnancy → avoid certain meds)
    # ...
    pass
```

2. Add patient_profile_expansion as a stage in scenario_compiler.py:
   - After cluster generation
   - Before final scenario serialization
   - Apply expand_cluster_with_profiles to each cluster

3. Add unit tests (tests/test_sgsc/test_patient_profile_expansion.py):
   - test_atom_with_explicit_pregnancy_excludes_pediatric
   - test_default_profile_applied_to_all
   - test_intersection_logic_constrains_safely
   - test_max_profiles_per_cluster_cap

4. Smoke test on kdigo_contrast_aki:
   PYTHONPATH=. python scripts/sgsc/recompile_corpus.py \
     --atoms-dir sgsc_output/v7_e3_combined_overnight/ \
     --output-dir sgsc_output/v7_1_with_profiles/ \
     --enable-patient-profiles \
     --profile-catalog data/v6_patient_profile_catalog.json
   
   Compare:
   - v7.0 kdigo: 12 scenarios
   - v7.1-cluster kdigo: ~16 scenarios
   - v7.1-cluster+profile kdigo: expected ~30-40 scenarios

5. Run all tests: PYTHONPATH=. pytest tests/test_sgsc/ -v

DELIVERABLES:
- scripts/sgsc/patient_profile_expansion.py
- Modified scenario_compiler.py
- tests/test_sgsc/test_patient_profile_expansion.py
- sgsc_output/v7_1_with_profiles/ smoke test output
- Console: kdigo scenario count v7.0 → v7.1-cluster → v7.1-cluster+profile

STOP. Print "B-4 COMPLETE — kdigo X→Y scenarios, profile coverage Z%". Wait.

═════════════════════════════════════════════════════════════════
TASK B-5: Quality gate verification on 25-graph compilation (15 min)
═════════════════════════════════════════════════════════════════

OBJECTIVE: Re-compile all 25 graphs with B-3 + B-4, verify quality gates still PASS.

STEPS:

1. Re-compile (atoms unchanged, only compilation logic):
   PYTHONPATH=. python scripts/sgsc/recompile_corpus.py \
     --atoms-dir sgsc_output/v7_e3_combined_overnight/ \
     --output-dir sgsc_output/v7_1_25_graph/ \
     --enable-patient-profiles \
     --profile-catalog data/v6_patient_profile_catalog.json

2. Quality gate check on the new corpus:
   - Hallucination rate (entailment-based): expect 0%
   - Truncated stem rate (canonical_id < 10 chars): expect 0% (atoms unchanged)
   - Action type diversity per graph: expect 5-9 (should be similar)
   - Population criteria coherence: no contradictions (e.g., pregnancy + male)
   - Forbidden actions consistency: profile-specific don't conflict with graph mandatory

3. Per-graph scenario count v7.0 → v7.1:
   Expected: ~3.4× expansion (cluster 1.7× × profile 2.0×)
   Total: 142 → ~480-500 on 25 graphs

4. Compare patient profile distribution to v6:
   - v7.1 profile distribution should match v6 within ±20%
   - Report discrepancies

DELIVERABLES:
- sgsc_output/v7_1_25_graph/ directory
- reports/path_d_day2/v7_1_quality_gate_25graph.md
- Console: total scenarios + 5-gate status

STOP. Print "B-5 COMPLETE — v7.1 25-graph: N scenarios, all gates PASS". Wait for sync with Session C (50-graph atom rollout).

═════════════════════════════════════════════════════════════════

EXECUTION ORDER: B-1 → B-2 → B-3 → B-4 → B-5

After B-5, wait for Session C to complete C-2 (50-graph atom rollout) and C-5 decision (multi-shot or single-shot). Then proceed to v7.2 final compilation in shared next step.

Begin with B-1. Confirm understanding by listing 5 tasks in order. Then start B-1.
