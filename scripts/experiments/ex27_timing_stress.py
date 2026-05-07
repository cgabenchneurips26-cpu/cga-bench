#!/usr/bin/env python3
"""EX-27: Timing Duration Stress Test
===================================
v6 episodes 위에서 실행. GPU 불필요 (trace 재처리만).

3개 Sub-experiment:
  Sub-A: keyword-based variable duration → WITHIN 재판정
  Sub-B: parallelizable action batch → 동시실행 가정 하 재판정
  Sub-C: reasoning-step exclusion → <think> 제거 후 재판정

Input:  results/full_706_v6/ (8 models × episodes)
Output: evidence_pack/ex27_timing_stress/ex27_results.json
        evidence_pack/ex27_timing_stress/macros.tex
"""

from collections import defaultdict
import json
import os
from pathlib import Path
import sys

# ============================================================================
# Configuration
# ============================================================================

# Sub-A: Keyword-based duration model (minutes)
# Source: clinical workflow estimates from published time-motion studies
ACTION_DURATIONS = {
    # Immediate actions (1-2 min)
    "check_vital_signs": 2,
    "check_pulse": 1,
    "check_airway": 1,
    "assess_consciousness": 1,
    "check_pupil_response": 1,
    "apply_oxygen": 2,
    "attach_monitor": 2,

    # Orders / decisions (2-3 min)
    "order_cbc": 2,
    "order_bmp": 2,
    "order_coagulation": 2,
    "order_blood_culture": 2,
    "order_urinalysis": 2,
    "order_abg": 2,
    "order_lactate": 2,
    "order_troponin": 2,
    "order_bnp": 2,
    "order_ct_head": 3,
    "order_ct_angiography": 3,
    "order_chest_xray": 2,
    "order_ecg": 2,
    "order_echo": 3,
    "order_mri": 3,
    "order_lumbar_puncture": 3,

    # Medication administration (3-5 min)
    "administer_tpa": 5,
    "administer_antibiotics": 5,
    "administer_aspirin": 3,
    "administer_heparin": 3,
    "administer_insulin": 3,
    "administer_epinephrine": 2,
    "administer_amiodarone": 3,
    "administer_nitroglycerin": 3,
    "administer_morphine": 3,
    "administer_furosemide": 3,
    "start_iv_fluids": 3,
    "administer_vasopressors": 5,
    "administer_dexamethasone": 3,
    "administer_mannitol": 5,
    "administer_vancomycin": 5,
    "administer_ceftriaxone": 5,

    # Procedures (10-30 min)
    "perform_intubation": 10,
    "perform_cpr": 15,
    "perform_cardioversion": 10,
    "perform_lumbar_puncture": 20,
    "perform_chest_tube": 20,
    "perform_central_line": 25,
    "perform_pericardiocentesis": 30,
    "perform_thoracentesis": 20,

    # Imaging completion (15-45 min wait)
    "obtain_ct_results": 30,
    "obtain_xray_results": 15,
    "obtain_mri_results": 45,
    "obtain_echo_results": 30,
    "obtain_ecg_results": 10,

    # Lab result waits (30-60 min)
    "obtain_cbc_results": 30,
    "obtain_bmp_results": 30,
    "obtain_troponin_results": 45,
    "obtain_blood_culture_results": 60,
    "obtain_lactate_results": 20,
    "obtain_abg_results": 15,
    "obtain_coagulation_results": 30,

    # Consults (variable, use median)
    "consult_neurology": 15,
    "consult_cardiology": 15,
    "consult_surgery": 15,
    "consult_icu": 10,
}

DEFAULT_DURATION = 5  # fallback for unmatched actions

# Sub-B: Parallelizable action groups
# Actions within the same group can execute concurrently
PARALLEL_GROUPS = [
    # Lab orders (can be ordered simultaneously)
    {"order_cbc", "order_bmp", "order_coagulation", "order_blood_culture",
     "order_urinalysis", "order_abg", "order_lactate", "order_troponin", "order_bnp"},
    # Monitoring setup (concurrent)
    {"check_vital_signs", "attach_monitor", "apply_oxygen", "check_pulse"},
    # Imaging orders (can be ordered together)
    {"order_ct_head", "order_ct_angiography", "order_chest_xray", "order_ecg", "order_echo"},
    # Concurrent med admin by different staff
    {"start_iv_fluids", "apply_oxygen", "attach_monitor"},
]


# ============================================================================
# Core functions
# ============================================================================

def load_episodes(episode_dir: str) -> list[dict]:
    """Load all v6 episode JSON files."""
    episodes = []
    episode_path = Path(episode_dir)
    if not episode_path.exists():
        print(f"ERROR: {episode_dir} not found", file=sys.stderr)
        sys.exit(1)

    for f in sorted(episode_path.rglob("*.json")):
        try:
            with open(f) as fp:
                ep = json.load(fp)
                ep["_source_file"] = str(f)
                episodes.append(ep)
        except (OSError, json.JSONDecodeError):
            continue
    return episodes


def get_action_name(action: dict) -> str:
    """Extract normalized action name from episode action record."""
    # Adapt to your episode schema
    return action.get("normalized_action", action.get("action", "UNKNOWN")).lower().strip()


def get_action_duration(action_name: str) -> tuple[int, bool]:
    """Returns (duration_minutes, is_default_fallback)."""
    # Try exact match
    if action_name in ACTION_DURATIONS:
        return ACTION_DURATIONS[action_name], False

    # Try prefix match (e.g., "administer_empiric_antibiotics" → "administer_antibiotics")
    for key, dur in ACTION_DURATIONS.items():
        if action_name.startswith(key.rsplit("_", 1)[0]):
            return dur, False

    # Try keyword match
    keywords = {
        "administer": 4, "order": 2, "check": 2, "assess": 2,
        "perform": 15, "obtain": 25, "consult": 15, "start": 3,
        "discontinue": 1, "monitor": 2, "evaluate": 3,
    }
    for kw, dur in keywords.items():
        if kw in action_name:
            return dur, False

    return DEFAULT_DURATION, True


def find_parallel_batches(actions: list[str]) -> list[list[int]]:
    """Identify consecutive action indices that belong to the same parallel group.
    Returns list of batches, each batch is a list of action indices.
    """
    batches = []
    i = 0
    while i < len(actions):
        # Check if current action belongs to any parallel group
        current_groups = [g for g in PARALLEL_GROUPS if actions[i] in g]
        if not current_groups:
            i += 1
            continue

        # Extend batch while consecutive actions are in the same group
        batch = [i]
        for j in range(i + 1, len(actions)):
            in_same_group = any(actions[j] in g for g in current_groups)
            if in_same_group:
                batch.append(j)
            else:
                break

        if len(batch) > 1:
            batches.append(batch)
            i = batch[-1] + 1
        else:
            i += 1

    return batches


def has_reasoning_steps(action: dict) -> bool:
    """Check if action is a reasoning/thinking step with no clinical time."""
    raw = action.get("raw_output", action.get("raw", ""))
    name = get_action_name(action)
    # Already stripped by v6 think-strip, but check residuals
    if name in ("think", "reason", "plan", "reflect", ""):
        return True
    if name == "UNKNOWN" or name.startswith("_"):
        return True
    return False


# ============================================================================
# Sub-experiments
# ============================================================================

def sub_a_variable_duration(episodes: list[dict], constraints: dict) -> dict:
    """Sub-A: Replace fixed 5-min step with keyword-based durations.
    Re-evaluate all WITHIN constraints under variable timing.

    Returns dict with:
      - n_within_violations_baseline: original count
      - n_within_violations_variable: count under variable duration
      - n_resolved: violations resolved (agent was actually faster)
      - n_new: new violations introduced (action took longer than 5min)
      - default_fallback_rate: % of actions using DEFAULT duration
      - coverage_rate: % of actions with explicit duration mapping
    """
    total_actions = 0
    default_fallback_count = 0
    matched_count = 0
    duration_distribution = defaultdict(int)

    baseline_within_viols = 0
    variable_within_viols = 0
    resolved = 0
    new_viols = 0

    for ep in episodes:
        actions = ep.get("actions", ep.get("trace", []))
        if not actions:
            continue

        # Build variable-duration timeline
        var_timestamps = []
        current_time = 0.0
        for act in actions:
            name = get_action_name(act)
            duration, is_default = get_action_duration(name)
            var_timestamps.append(current_time)
            current_time += duration
            total_actions += 1
            if is_default:
                default_fallback_count += 1
            else:
                matched_count += 1
            duration_distribution[duration] += 1

        # Re-evaluate WITHIN constraints
        ep_constraints = ep.get("active_constraints", [])
        for c in ep_constraints:
            if c.get("type", "").upper() != "WITHIN":
                continue

            target_action = c.get("target", c.get("action", ""))
            deadline = c.get("deadline", c.get("window", float("inf")))

            # Find action in trace
            for idx, act in enumerate(actions):
                if get_action_name(act) == target_action:
                    baseline_time = idx * 5  # fixed 5-min step
                    variable_time = var_timestamps[idx] if idx < len(var_timestamps) else idx * 5

                    baseline_violates = baseline_time > deadline
                    variable_violates = variable_time > deadline

                    if baseline_violates:
                        baseline_within_viols += 1
                    if variable_violates:
                        variable_within_viols += 1

                    if baseline_violates and not variable_violates:
                        resolved += 1
                    elif not baseline_violates and variable_violates:
                        new_viols += 1
                    break

    fallback_rate = (default_fallback_count / total_actions * 100) if total_actions > 0 else 0
    coverage_rate = (matched_count / total_actions * 100) if total_actions > 0 else 0

    return {
        "total_actions": total_actions,
        "matched_actions": matched_count,
        "default_fallback_count": default_fallback_count,
        "default_fallback_rate": round(fallback_rate, 1),
        "coverage_rate": round(coverage_rate, 1),
        "baseline_within_violations": baseline_within_viols,
        "variable_within_violations": variable_within_viols,
        "resolved": resolved,
        "new_violations": new_viols,
        "net_change": variable_within_viols - baseline_within_viols,
        "net_change_pct": round((variable_within_viols - baseline_within_viols)
                                / max(baseline_within_viols, 1) * 100, 1),
        "duration_distribution": dict(sorted(duration_distribution.items())),
    }


def sub_b_parallel_batching(episodes: list[dict]) -> dict:
    """Sub-B: Identify parallelizable action sequences, compress their
    timestamps, and re-evaluate WITHIN constraints.
    """
    total_episodes = 0
    episodes_with_batches = 0
    total_batches = 0
    total_actions_batched = 0
    time_saved_minutes = []

    baseline_viols = 0
    parallel_viols = 0
    resolved = 0

    for ep in episodes:
        actions = ep.get("actions", ep.get("trace", []))
        if not actions:
            continue
        total_episodes += 1

        action_names = [get_action_name(a) for a in actions]
        batches = find_parallel_batches(action_names)

        if batches:
            episodes_with_batches += 1
            total_batches += len(batches)

            # Calculate time savings: batch of N actions compressed to max(durations)
            ep_saved = 0
            for batch in batches:
                batch_names = [action_names[i] for i in batch]
                durations = [get_action_duration(n)[0] for n in batch_names]
                sequential_time = sum(durations)
                parallel_time = max(durations)
                ep_saved += (sequential_time - parallel_time)
                total_actions_batched += len(batch)

            time_saved_minutes.append(ep_saved)

        # Re-evaluate WITHIN under parallel timing
        # (simplified: compress batch timestamps)
        par_timestamps = []
        current_time = 0.0
        i = 0
        batch_map = {}
        for batch in batches:
            for idx in batch:
                batch_map[idx] = batch

        while i < len(actions):
            if i in batch_map:
                batch = batch_map[i]
                batch_names = [action_names[j] for j in batch]
                durations = [get_action_duration(n)[0] for n in batch_names]
                # All actions in batch start at current_time
                for j in batch:
                    par_timestamps.append(current_time)
                current_time += max(durations)
                i = batch[-1] + 1
            else:
                dur, _ = get_action_duration(action_names[i])
                par_timestamps.append(current_time)
                current_time += dur
                i += 1

        # Check WITHIN constraints
        for c in ep.get("active_constraints", []):
            if c.get("type", "").upper() != "WITHIN":
                continue
            target = c.get("target", c.get("action", ""))
            deadline = c.get("deadline", c.get("window", float("inf")))

            for idx, act in enumerate(actions):
                if get_action_name(act) == target:
                    baseline_time = idx * 5
                    par_time = par_timestamps[idx] if idx < len(par_timestamps) else idx * 5

                    if baseline_time > deadline:
                        baseline_viols += 1
                    if par_time > deadline:
                        parallel_viols += 1
                    if baseline_time > deadline and par_time <= deadline:
                        resolved += 1
                    break

    mean_saved = sum(time_saved_minutes) / max(len(time_saved_minutes), 1)
    batch_rate = episodes_with_batches / max(total_episodes, 1) * 100

    return {
        "total_episodes": total_episodes,
        "episodes_with_batches": episodes_with_batches,
        "batch_rate": round(batch_rate, 1),
        "total_batches": total_batches,
        "total_actions_batched": total_actions_batched,
        "mean_time_saved_minutes": round(mean_saved, 1),
        "baseline_within_violations": baseline_viols,
        "parallel_within_violations": parallel_viols,
        "resolved_by_parallelism": resolved,
        "resolved_pct": round(resolved / max(baseline_viols, 1) * 100, 1),
    }


def sub_c_reasoning_exclusion(episodes: list[dict]) -> dict:
    """Sub-C: Remove zero-duration reasoning/thinking steps from timeline.
    v6 already strips <think> blocks, so this checks residual impact.
    """
    total_episodes = 0
    episodes_with_reasoning = 0
    total_reasoning_steps = 0
    total_clinical_steps = 0

    baseline_viols = 0
    cleaned_viols = 0
    resolved = 0

    for ep in episodes:
        actions = ep.get("actions", ep.get("trace", []))
        if not actions:
            continue
        total_episodes += 1

        # Separate clinical vs reasoning actions
        clinical_actions = []
        reasoning_count = 0
        for act in actions:
            if has_reasoning_steps(act):
                reasoning_count += 1
            else:
                clinical_actions.append(act)

        total_reasoning_steps += reasoning_count
        total_clinical_steps += len(clinical_actions)

        if reasoning_count > 0:
            episodes_with_reasoning += 1

        # Re-evaluate: clinical-only timeline (each clinical action = 5 min)
        for c in ep.get("active_constraints", []):
            if c.get("type", "").upper() != "WITHIN":
                continue
            target = c.get("target", c.get("action", ""))
            deadline = c.get("deadline", c.get("window", float("inf")))

            # Baseline: all actions × 5 min
            for idx, act in enumerate(actions):
                if get_action_name(act) == target:
                    baseline_time = idx * 5
                    if baseline_time > deadline:
                        baseline_viols += 1

                    # Cleaned: only clinical action index × 5 min
                    clinical_idx = None
                    ci = 0
                    for orig_idx, a in enumerate(actions):
                        if not has_reasoning_steps(a):
                            if orig_idx == idx:
                                clinical_idx = ci
                                break
                            ci += 1

                    if clinical_idx is not None:
                        cleaned_time = clinical_idx * 5
                        if cleaned_time > deadline:
                            cleaned_viols += 1
                        if baseline_time > deadline and cleaned_time <= deadline:
                            resolved += 1
                    break

    reasoning_rate = total_reasoning_steps / max(total_reasoning_steps + total_clinical_steps, 1) * 100

    return {
        "total_episodes": total_episodes,
        "episodes_with_reasoning": episodes_with_reasoning,
        "total_reasoning_steps": total_reasoning_steps,
        "total_clinical_steps": total_clinical_steps,
        "reasoning_rate": round(reasoning_rate, 1),
        "baseline_within_violations": baseline_viols,
        "cleaned_within_violations": cleaned_viols,
        "resolved_by_exclusion": resolved,
        "resolved_pct": round(resolved / max(baseline_viols, 1) * 100, 1),
    }


# ============================================================================
# Output
# ============================================================================

def generate_macros(results: dict) -> str:
    """Generate LaTeX macros from results."""
    a = results["sub_a"]
    b = results["sub_b"]
    c = results["sub_c"]

    lines = [
        "% EX-27: Timing Duration Stress Test",
        "% Auto-generated by ex27_timing_stress.py",
        "",
        "% Sub-A: Variable Duration",
        f"\\newcommand{{\\exTwentySevenCoverageRate}}{{{a['coverage_rate']}}}",
        f"\\newcommand{{\\exTwentySevenFallbackRate}}{{{a['default_fallback_rate']}}}",
        f"\\newcommand{{\\exTwentySevenBaselineViols}}{{{a['baseline_within_violations']}}}",
        f"\\newcommand{{\\exTwentySevenVariableViols}}{{{a['variable_within_violations']}}}",
        f"\\newcommand{{\\exTwentySevenResolved}}{{{a['resolved']}}}",
        f"\\newcommand{{\\exTwentySevenNewViols}}{{{a['new_violations']}}}",
        f"\\newcommand{{\\exTwentySevenNetChangePct}}{{{a['net_change_pct']}}}",
        "",
        "% Sub-B: Parallel Batching",
        f"\\newcommand{{\\exTwentySevenBatchRate}}{{{b['batch_rate']}}}",
        f"\\newcommand{{\\exTwentySevenBatchResolved}}{{{b['resolved_by_parallelism']}}}",
        f"\\newcommand{{\\exTwentySevenBatchResolvedPct}}{{{b['resolved_pct']}}}",
        f"\\newcommand{{\\exTwentySevenMeanSaved}}{{{b['mean_time_saved_minutes']}}}",
        "",
        "% Sub-C: Reasoning Exclusion",
        f"\\newcommand{{\\exTwentySevenReasoningRate}}{{{c['reasoning_rate']}}}",
        f"\\newcommand{{\\exTwentySevenReasonResolved}}{{{c['resolved_by_exclusion']}}}",
        f"\\newcommand{{\\exTwentySevenReasonResolvedPct}}{{{c['resolved_pct']}}}",
        "",
        "% Combined",
        f"\\newcommand{{\\exTwentySevenTotalResolved}}{{{a['resolved'] + b['resolved_by_parallelism'] + c['resolved_by_exclusion']}}}",
    ]
    return "\n".join(lines)


def main():
    import argparse
    parser = argparse.ArgumentParser(description="EX-27 Timing Duration Stress Test")
    parser.add_argument("--episode-dir", default="results/full_706_v6",
                        help="Path to v6 episode directory")
    parser.add_argument("--output-dir", default="evidence_pack/ex27_timing_stress",
                        help="Output directory")
    args = parser.parse_args()

    print("Loading episodes...")
    episodes = load_episodes(args.episode_dir)
    print(f"  Loaded {len(episodes)} episodes")

    print("\n=== Sub-A: Variable Duration Model ===")
    result_a = sub_a_variable_duration(episodes, {})
    print(f"  Coverage: {result_a['coverage_rate']}% (fallback: {result_a['default_fallback_rate']}%)")
    print(f"  Baseline violations: {result_a['baseline_within_violations']}")
    print(f"  Variable violations: {result_a['variable_within_violations']}")
    print(f"  Resolved: {result_a['resolved']}, New: {result_a['new_violations']}")

    print("\n=== Sub-B: Parallel Batching ===")
    result_b = sub_b_parallel_batching(episodes)
    print(f"  Episodes with batches: {result_b['episodes_with_batches']}/{result_b['total_episodes']} ({result_b['batch_rate']}%)")
    print(f"  Resolved by parallelism: {result_b['resolved_by_parallelism']} ({result_b['resolved_pct']}%)")

    print("\n=== Sub-C: Reasoning Exclusion ===")
    result_c = sub_c_reasoning_exclusion(episodes)
    print(f"  Reasoning rate: {result_c['reasoning_rate']}%")
    print(f"  Resolved by exclusion: {result_c['resolved_by_exclusion']} ({result_c['resolved_pct']}%)")

    # Save results
    os.makedirs(args.output_dir, exist_ok=True)

    results = {
        "sub_a": result_a,
        "sub_b": result_b,
        "sub_c": result_c,
        "metadata": {
            "n_episodes": len(episodes),
            "pipeline": "v6",
            "default_step_minutes": 5,
            "n_duration_mappings": len(ACTION_DURATIONS),
            "n_parallel_groups": len(PARALLEL_GROUPS),
        }
    }

    with open(os.path.join(args.output_dir, "ex27_results.json"), "w") as f:
        json.dump(results, f, indent=2)

    macros = generate_macros(results)
    with open(os.path.join(args.output_dir, "macros.tex"), "w") as f:
        f.write(macros)

    print(f"\nResults saved to {args.output_dir}/")
    print(f"Macros saved to {args.output_dir}/macros.tex")
    print("\n>>> Paste macros.tex contents into auto_numbers.tex <<<")


if __name__ == "__main__":
    main()
