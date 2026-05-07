# Phase B Entry Decision Document (v5)

Date: 2026-03-31
Status: **BLOCKING ISSUES FOUND -- Phase B re-run required before paper claims**

---

## Problem 1: oss-120b Baseline/Patch Mixing

### Root Cause

The eval_harness defines 4 experimental conditions via `PromptPatchType`:

| Condition | System Prompt Addition | Target Dimension |
|-----------|----------------------|-----------------|
| `baseline` | (none) | N/A |
| `patch_T` | Timing priority instructions | C4 |
| `patch_S` | Sequence enforcement instructions | C5 |
| `patch_O` | Action scope restriction instructions | C1 |

These are **different prompt conditions**, not independent runs of the same experiment.

### Current Data State

oss-120b baseline covers only **8/15 scenarios**:

| Scenario | baseline | patch_O | patch_S | patch_T | total |
|----------|:--------:|:-------:|:-------:|:-------:|:-----:|
| septic_shock_basic | 4 | 1 | 2 | 2 | 9 |
| septic_shock_penicillin_allergy | 3 | 1 | 2 | 2 | 8 |
| stemi_inferior_rv_trap | 3 | 1 | 2 | 2 | 8 |
| dka_moderate_basic | 3 | 1 | 2 | 2 | 8 |
| dka_hypokalemia_trap | 3 | 1 | 2 | 2 | 8 |
| stroke_tpa_eligible | 2 | 1 | 2 | 2 | 7 |
| contrast_aki_prevention_basic | 2 | 1 | 1 | 2 | 6 |
| aki_stage1_basic | 2 | 1 | 1 | 2 | 6 |
| adhf_warm_wet | 0 | 1 | 1 | 1 | 3 |
| af_new_onset_basic | 0 | 1 | 1 | 1 | 3 |
| copd_moderate_exacerbation | 0 | 1 | 1 | 1 | 3 |
| gi_bleeding_upper_basic | 0 | 1 | 1 | 1 | 3 |
| hemorrhagic_stroke | 0 | 1 | 1 | 1 | 3 |
| htn_emergency_basic | 0 | 1 | 1 | 1 | 3 |
| pe_submassive_basic | 0 | 1 | 1 | 1 | 3 |

Other models (oss-20b, Qwen3.5-35B, Qwen3-4B): all have 3-6 baseline runs per 15 scenarios. Clean.

### Critical Bug in bootstrap_ci.py

Line 114: `for run_idx, sub in enumerate(["baseline", "patch_S", "patch_T"]):`

This treats different prompt conditions as "3 runs" for multi-run averaging. The multi-run p=0.013 is therefore **invalid** -- it averages across different experimental conditions for oss-120b.

### Friedman Under Clean Conditions

| Option | Scenarios | Models | Condition | p | Sig |
|--------|:---------:|:------:|-----------|:---:|:---:|
| A: Baseline-only, 8 scenarios | 8 | 4 | Clean baseline | 0.583 | No |
| B: patch_O for 120b, 15 scenarios | 15 | 4 | Mixed (patch_O for 120b) | 0.168 | No |
| E: Current (mixed, single-run) | 15 | 4 | Confounded | 0.073 | No |
| E: Current (mixed, multi-run) | 15 | 4 | Confounded | 0.013 | Yes |
| F: Drop oss-120b, 3 models | 15 | 3 | Clean baseline | 0.108 | No |

**Under any clean analysis, no Friedman result is statistically significant.**

### Recommendation

**Option: Re-run oss-120b baseline for all 15 scenarios (3 runs each)**

This is the only path to a defensible paper:
1. Run oss-120b with baseline (no prompt patch) across all 15 scenarios x 3 runs = 45 episodes
2. This creates a clean 4-model x 15-scenario x 3-run dataset
3. Re-compute all statistics from scratch

Until this re-run completes, the paper cannot claim Friedman significance.

---

## Problem 2: Q2 Episode Canonical Re-derivation

### Existing Q2 Provenance

The existing 22 Q2 episodes in `discriminant_validity.json` are **not from the canonical dataset**:

| Source | Count | Models |
|--------|:-----:|--------|
| Canonical (current baseline) | 4 | oss-120b |
| Non-canonical variants | 18 | oss-120b-old, -v2, -v3, -r0, -r1, -r2 |

The `-old`, `-v2`, `-v3` variants are historical model checkpoints. The `-r0/-r1/-r2` labels mapped to baseline/patch_S/patch_T conditions.

### Canonical Re-derivation

Using baseline-only data (156 episodes: 21 oss-120b + 45 each for other 3 models):

| Metric | Value |
|--------|:-----:|
| Total episodes | 156 |
| Task PASS (C2 >= 0.9) | 91 |
| CGA FAIL (compliance < 0.7) | 88 |
| **Q2 = Task PASS AND CGA FAIL** | **34** |

Q2 breakdown by scenario:

| Scenario | Models affected | Count | Primary failure |
|----------|----------------|:-----:|-----------------|
| af_new_onset_basic | Qwen3.5-35B, oss-20b | 6 | C1 path_selection |
| aki_stage1_basic | oss-120b, oss-20b, Qwen3-4B | 4 | C1 path_selection |
| contrast_aki_prevention_basic | oss-120b, oss-20b, Qwen3.5-35B | 8 | C1 path_selection |
| copd_moderate_exacerbation | Qwen3.5-35B, oss-20b | 4 | C1 path_selection |
| dka_hypokalemia_trap | oss-120b, oss-20b | 4 | C3 forbidden_avoidance |
| dka_moderate_basic | oss-120b | 1 | (borderline) |
| pe_submassive_basic | Qwen3-4B, Qwen3.5-35B, oss-20b | 7 | C1 path_selection |

### Key Changes from Existing Q2

| Aspect | Existing | Canonical |
|--------|:--------:|:---------:|
| Count | 22 | **34** |
| Model diversity | oss-120b only | **All 4 models** |
| Scenario diversity | 9 scenarios | **7 scenarios** |
| Primary failure | C1 (21/22) | C1 (29/34), C3 (4/34) |

The canonical Q2 is **stronger** than the existing one: more episodes, more model diversity, now includes C3 (forbidden avoidance) failures from DKA.

### Necessity Claim

> "CGA-Bench identifies 34 episodes where agents complete mandatory actions (C2 >= 0.9) yet violate clinical guidelines -- failures invisible to task-completion metrics."

This claim is defensible and stronger than the original 22.

---

## Phase B Entry Checklist

| # | Item | Status | Detail |
|---|------|:------:|--------|
| 1 | oss-120b data integrity resolved | **BLOCKED** | Baseline covers 8/15 scenarios only. **Re-run required** for 7 expansion scenarios. |
| 2 | Q2 episodes canonical re-derived | **DONE** | Q2=34 from 156 baseline-only episodes. Saved to `q2_canonical_rederivation.json`. |
| 3 | C3 formula = binary confirmed | **DONE** | Binary C3 locked. Does not affect Composite A. |
| 4 | Clean Friedman with confirmed data | **BLOCKED** | All clean analyses give p > 0.05. Multi-run p=0.013 was confounded. |
| 5 | 2,768+ tests pass | **DONE** | 2,768 passed, 0 failed. |

### Phase B Entry Verdict: **NOT APPROVED**

**Reason**: oss-120b lacks baseline data for 7/15 expansion scenarios. The multi-run p=0.013 relied on averaging across different prompt conditions (baseline/patch_S/patch_T), which is methodologically invalid.

### Required Action Before Phase B

1. **Re-run oss-120b baseline** on all 15 scenarios x 3 runs (45 episodes)
   - Use `configs/agents/rag_oss120b.yaml` with NO prompt patches
   - Requires vLLM serving oss-120b on port 8099
   - Estimated: ~45 episodes x ~2 min each = ~90 minutes

2. After re-run:
   - Recompute composite_metric.json from clean baseline data
   - Recompute Friedman (single-run + multi-run)
   - Recompute discriminant validity (r) and Q2
   - Recompute bootstrap CIs

### Paper Impact Assessment

If clean Friedman remains ns (likely based on Option A/B/F results):

- **Primary contribution shifts to qualitative**: Q2=34 necessity episodes, sub-construct profiling, failure mode taxonomy
- **Effect size reporting**: Epsilon-squared as primary, p-value as secondary
- **Honest framing**: "At n=15 scenarios, inter-model differences are not statistically significant by Friedman test. CGA-Bench's contribution is the identification of clinically meaningful failure modes invisible to task-completion metrics."

This is still a strong paper -- the necessity argument (Q2=34) and the sub-construct analysis (C1 dominance, C4 timing differences) are the real contributions.
