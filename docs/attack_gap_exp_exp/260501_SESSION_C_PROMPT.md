# Session C Starter Prompt

You are working on Track-C of CGA-Bench Path D Day 2-3 expansion: extending SGSC to ~50 CPGs using the C1-C12 selection criteria, and verifying atom proposer recall via multi-shot sampling.

## Context

We've completed Track-3 SGSC determinism (DET 25-graph rollout: 787 atoms, 142 scenarios). anonymous-user identified that:
1. CPG selection should use the validated C1-C12 framework (`06_selection_criteria_v2.md`, freeze 2026-04-23)
2. ~50 CPGs available via Tier S (>=15 score) + Tier A (11-14) candidates
3. Atom proposer single-shot recall ceiling is unverified — multi-shot may extract more

This session expands SGSC to additional CPGs and tests atom recall.

## Critical constraints

- DO NOT change atom_proposer code (validated through DET rollout)
- DO NOT change ActionNormalizer (sanity checks PASS)
- LLM endpoint coordination: use port 30001 for C-2 (50-graph rollout) and port 30002 for C-3 (multi-shot)
- Atom proposer in DET mode (--deterministic --base-seed 42)

## Repo layout (verify first)

- C1-C12 scoring: `scripts/score_cpg_v2.py`
- CPG candidates: `data/cpg_source_properties_candidates_draft.json` (8 approved), `data/cpg_source_properties_candidates_bulk_{A,B}.json` (90)
- Existing 25 core: `data/cpg_source_properties.json`
- Graph YAMLs: `cpg_model/graphs/*.yaml`
- SGSC runner: `scripts/sgsc/run_full_25.py` (adapt for new graph list)
- Atom output: `sgsc_output/v7_e3_combined_overnight/{25 graphs}/atoms_smoke.json`

After each task, STOP and print "C-N COMPLETE" with 3-line summary. Wait for confirmation.
═════════════════════════════════════════════════════════════════
TASK C-1: Select expansion graphs from frozen 123-CPG scoring (15 min)
═════════════════════════════════════════════════════════════════

OBJECTIVE: From the frozen C1-C12 scoring of 123 CPGs (76 Tier S + 35 Tier A + 9 Tier B + 3 Excluded), select 25 expansion graphs to combine with 24 active core (universal_safety excluded) for a final 49-graph corpus.

PRECONDITION: 123-CPG scoring is frozen (/docs/cpg_expansion_v7/06_selection_criteria_v2.md, rubric lock 2026-04-23). Do NOT re-score.

STEPS:

1. Locate frozen scoring results:
   - reports/cpg_scores_v2.json (canonical output)
   - Or aggregate from data/cpg_source_properties{,_candidates_*}.json

2. Identify already-active 25 core. From those:
   - 24 active (universal_clinical_safety excluded)
   - These are NOT candidates for expansion

3. Identify 99 expansion candidates (123 - 24 active):
   - Tier S available: ~52 (76 total - 24 active in S)
   - Tier A available: ~35
   - Tier B available: ~9 (skip)

4. Selection rule: 25 highest-scoring graphs from Tier S + Tier A pool, with the following constraints:
   (a) Graph YAML must exist in cpg_model/graphs/<graph_id>.yaml
   (b) Source CPG document accessible (data/cpg_source_properties*.json entry complete)
   (c) Within Tier S, prefer those filling clinical-domain gaps not covered by 24 core (e.g., if all 24 core are critical-care, add some non-critical Tier S to broaden patient profile coverage)

5. Tie-breaking when multiple graphs at same score:
   - Prefer ones with patient-context-rich source (C12 conditional branching = 1)
   - Prefer ones with sequence dependency (C11 = 1)
   - Prefer non-overlapping clinical domains

6. Output:
   data/tier_s_expansion_list.json:
   {
     "active_core": [...24 graph_ids...],
     "expansion_25": [
       {"graph_id": "...", "tier": "S", "total": 19, "axis_scores": [7,6,6], 
        "yaml_exists": true, "source_props_complete": true, "rationale": "..."},
       ...
     ],
     "final_50_graph_list": [...49 or 50 graph_ids combined...],
     "domain_coverage": {"critical_care": N, "endocrine": M, ...}
   }
   reports/path_d_day2/tier_s_expansion_selection.md

7. YAML existence check:
   For each candidate in expansion_25, verify cpg_model/graphs/<graph_id>.yaml exists.
   If missing, document gap and replace with next-highest-score candidate.

DELIVERABLES:
- data/tier_s_expansion_list.json with 25 selected expansion graphs
- reports/path_d_day2/tier_s_expansion_selection.md
- Console: final 49 (or 50) graph list with score distribution

STOP. Print "C-1 COMPLETE — 25 expansion selected (X Tier S + Y Tier A), all YAMLs verified, final corpus = 49 graphs (24 core + 25 expansion)". Wait.

═════════════════════════════════════════════════════════════════
TASK C-2: Atom proposer rollout on 24-25 expansion graphs (40 min)
═════════════════════════════════════════════════════════════════

OBJECTIVE: Run DET atom proposer on expansion graphs.

PRECONDITION: C-1 produced expansion list with verified graph YAMLs.

STEPS:

1. Endpoint check: 
   curl http://localhost:8013/v1/models
   Confirm Qwen/Qwen3.5-397B-A17B-FP8 is loaded.

2. Adapt run_full_25.py for arbitrary graph list:
   - Copy or modify to scripts/sgsc/run_graph_list.py
   - Accept --graph-list <path-to-tier_s_expansion_list.json> instead of hardcoded 25
   - Output to sgsc_output/v7_2_atoms_expansion/

3. Pre-flight (--dry-run):
   PYTHONPATH=. python scripts/sgsc/run_graph_list.py \
     --graph-list data/tier_s_expansion_list.json \
     --dry-run
   Confirm 24-25/24-25 validated.

4. Real kickoff (parallel-4, deterministic):
   nohup PYTHONPATH=. python scripts/sgsc/run_graph_list.py \
     --graph-list data/tier_s_expansion_list.json \
     --endpoint http://localhost:8013/v1 \
     --threshold 0.6 \
     --deterministic \
     --base-seed 42 \
     --top-p 1.0 \
     --parallel 4 \
     --output-dir sgsc_output/v7_2_atoms_expansion/ \
     > reports/path_d_day2/sgsc_expansion_rollout.log 2>&1 &
   echo $! > reports/path_d_day2/sgsc_expansion_pid.txt

5. Monitor: tail -f reports/path_d_day2/sgsc_expansion_rollout.log
   Expected wallclock: 24 graphs × 1.5min (parallel-4) ≈ 9-15 min
   Conservative estimate: 40 min

6. After completion, quality gate check on expansion atoms:
   - Hallucination rate per graph
   - Truncated stem rate per graph
   - Action type diversity
   - Atom count per graph
   
   Report any graph with issues (atoms < 5, hallucination > 0%, truncated stems > 5%).

7. Aggregate output: total atoms across 24-25 expansion graphs.
   Expected: ~600-800 atoms (similar density to 25 core: 787/25 = 31 atoms/graph average).

DELIVERABLES:
- sgsc_output/v7_2_atoms_expansion/{24-25 graphs}/atoms_smoke.json
- reports/path_d_day2/sgsc_expansion_rollout.log
- reports/path_d_day2/sgsc_expansion_quality_gate.md
- Console: total atoms, per-graph quality gate status

STOP. Print "C-2 COMPLETE — N expansion graphs, M total atoms, all quality gates PASS". Wait.

═════════════════════════════════════════════════════════════════
TASK C-3: Atom multi-shot ceiling test on kdigo_contrast_aki (40 min)
═════════════════════════════════════════════════════════════════

OBJECTIVE: Determine if multi-shot extraction (different seeds) increases atom recall, informing v7.2 corpus strategy decision.

STEPS:

1. Endpoint check (use endpoint 2 to avoid C-2 conflict):
   curl http://localhost:8013/v1/models

2. Run atom proposer 5 times on kdigo_contrast_aki with different seeds:
   PYTHONPATH=. python scripts/sgsc/run_graph_list.py \
     --graph-list <(echo '{"expansion_graphs":["kdigo_contrast_aki"]}') \
     --endpoint http://localhost:8013/v1 \
     --threshold 0.6 \
     --deterministic \
     --base-seed 42 \
     --output-dir sgsc_output/v7_multishot/seed_42/

   Repeat with --base-seed 43, 44, 45, 46 (each writes to different output dir).

3. Aggregate analysis:
   - Per-shot atom count: should be similar (~30-40)
   - Pairwise Jaccard between shots (10 pairs)
   - Cumulative union: 1 shot, 2 shots, ..., 5 shots
   - Atom growth curve

4. Decision criteria:
   - 5-shot union > 1.5× single-shot → multi-shot has meaningful recall gain
   - 5-shot union ≤ 1.2× single-shot → single-shot is near ceiling
   - Mid-range → judgment call (favor single-shot for simplicity)

5. Output:
   - reports/path_d_day2/atom_multi_shot_ceiling.md
   - Console: per-shot counts, cumulative union, decision recommendation

DELIVERABLES:
- sgsc_output/v7_multishot/seed_{42,43,44,45,46}/kdigo_contrast_aki/atoms_smoke.json (×5)
- reports/path_d_day2/atom_multi_shot_ceiling.md

STOP. Print "C-3 COMPLETE — 5-shot union/single ratio = X, recommendation = single-shot|multi-shot". Wait.

═════════════════════════════════════════════════════════════════
TASK C-4: (CONDITIONAL) Multi-shot aggregation implementation (30 min)
═════════════════════════════════════════════════════════════════

PRECONDITION: C-3 indicates multi-shot is beneficial (union/single > 1.5×).

If C-3 recommends single-shot, SKIP this task and proceed to C-5.

OBJECTIVE: Implement multi-shot aggregation as production option for v7.2.

STEPS:

1. Create scripts/sgsc/multi_shot_aggregator.py:
   - Input: directory containing multiple seed_X/ subdirectories with atoms_smoke.json each
   - Aggregation rules:
     * Group atoms by canonical_id
     * For duplicates, keep the one with highest entailment score
     * Atoms appearing in only 1 of N shots: include only if entailment > 0.7 (stricter threshold)
     * Atoms appearing in >= 2 shots: include if any has entailment >= 0.6
   - Quality gate validation on aggregated atoms

2. CLI:
   PYTHONPATH=. python scripts/sgsc/multi_shot_aggregator.py \
     --input-dirs sgsc_output/v7_multishot/seed_42 sgsc_output/v7_multishot/seed_43 ... \
     --output-dir sgsc_output/v7_multishot_aggregated/

3. Test on kdigo_contrast_aki 5-shot from C-3:
   - Aggregated atom count
   - Quality gate pass

4. Decision: if aggregated atoms have 0% hallucination + retain or improve diversity, multi-shot aggregation is production-ready.

DELIVERABLES:
- scripts/sgsc/multi_shot_aggregator.py
- sgsc_output/v7_multishot_aggregated/kdigo_contrast_aki/ smoke test
- reports/path_d_day2/multi_shot_aggregation_validation.md

STOP. Print "C-4 COMPLETE — multi-shot aggregator validated" or "C-4 SKIPPED per C-3". Wait.

═════════════════════════════════════════════════════════════════
TASK C-5: Final 50-graph corpus union preparation (15 min)
═════════════════════════════════════════════════════════════════

OBJECTIVE: Prepare for v7.2 final compilation (which depends on Session B-4/B-5 patient profile expansion).

STEPS:

1. Verify all atoms ready:
   - 25 core: sgsc_output/v7_e3_combined_overnight/{25}/
   - 24-25 expansion: sgsc_output/v7_2_atoms_expansion/{24-25}/
   - Total ~48-50 graphs with atoms

2. Optional: union all atom dirs into single canonical location:
   sgsc_output/v7_2_all_atoms/{50 graphs}/

3. Verify Session B status:
   - B-5 should have completed (25-graph compilation with cluster + profile)
   - Wait if B-5 not done

4. After B-5 complete:
   - Coordinate v7.2 final compilation:
     PYTHONPATH=. python scripts/sgsc/recompile_corpus.py \
       --atoms-dir sgsc_output/v7_2_all_atoms/ \
       --output-dir sgsc_output/v7_2_final/ \
       --enable-patient-profiles \
       --profile-catalog data/v6_patient_profile_catalog.json
   
   - Apply multi-shot aggregator if C-4 enabled
   - Quality gate check

5. Aggregate metrics:
   - Total scenarios across 50 graphs
   - Total atoms (after aggregation if applicable)
   - Per-graph scenario count distribution
   - Patient profile coverage (compare to v6 catalog)

DELIVERABLES:
- sgsc_output/v7_2_final/ (final v7.2 corpus, ready for episode rerun)
- reports/path_d_day2/v7_2_final_quality.md
- Console: total scenarios, atoms, profile coverage vs v6

STOP. Print "C-5 COMPLETE — v7.2 corpus: N scenarios on M graphs, ready for episode rerun". 

═════════════════════════════════════════════════════════════════

EXECUTION ORDER: C-1 → C-2 → C-3 → [C-4 conditional] → C-5

After C-5, signal anonymous-user that v7.2 corpus is ready for 5/3 09:00 episode rerun launch.

Begin with C-1. Confirm understanding by listing 5 tasks in order. Then start C-1.

Note: C-2 and C-3 can run in parallel (different LLM endpoints). Execute C-1 first, then launch C-2 in background and proceed with C-3.
