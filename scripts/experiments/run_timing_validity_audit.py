#!/usr/bin/env python3
"""E-TIMING: Timing Validity Audit — Post-Episode Analysis

Addresses reviewer attack #19: "timing violation이 scenario-clock artifact가 아닌가?"

Analysis:
1. Action-class duration distribution: group actions by clinical category,
   compute per-class duration statistics
2. Parallelizable action batching: identify action pairs that could be
   concurrent in real practice but are sequential in simulation
3. Timing violation margin analysis: how far past deadline each violation is
4. Cross-model timing consistency: same scenario, different models → same
   timing pattern?

Usage:
    python scripts/experiments/run_timing_validity_audit.py \
        --episodes-dir results/full_706_final \
        --output evidence_pack/analysis/timing_validity_audit.json \
        --tex-output paper/auto_numbers.tex

Requires: episode JSONs with action detail (Bug 5 fixed)
"""

import argparse
from collections import Counter, defaultdict
import glob
import json
import os
import sys

import numpy as np

# === Clinical action categories ===
ACTION_CATEGORIES = {
    "diagnostic_lab": [
        "order_cbc",
        "order_bmp",
        "order_cmp",
        "order_troponin",
        "order_bnp",
        "order_lactate",
        "order_blood_cultures",
        "order_urinalysis",
        "order_abg",
        "order_coagulation",
        "order_lipase",
    ],
    "diagnostic_imaging": [
        "order_ct_head",
        "order_ct_chest",
        "order_cta",
        "order_xray_chest",
        "order_echocardiogram",
        "order_mri_brain",
        "order_ct_abdomen",
    ],
    "medication_stat": [
        "administer_epinephrine",
        "administer_aspirin",
        "administer_heparin",
        "administer_tpa",
        "administer_insulin",
        "administer_vasopressor",
        "administer_antibiotics",
        "administer_naloxone",
    ],
    "medication_routine": [
        "start_iv_fluids",
        "administer_antiemetic",
        "administer_analgesic",
        "administer_ppi",
        "start_maintenance_fluids",
    ],
    "procedure": [
        "perform_intubation",
        "perform_cardioversion",
        "perform_lumbar_puncture",
        "insert_central_line",
        "perform_thoracentesis",
    ],
    "monitoring": [
        "continuous_cardiac_monitoring",
        "pulse_oximetry",
        "arterial_line",
        "serial_neuro_checks",
        "hourly_vitals",
    ],
    "disposition": [
        "admit_icu",
        "admit_ward",
        "consult_cardiology",
        "consult_neurology",
        "consult_surgery",
        "transfer_cath_lab",
    ],
}

# Invert for lookup
ACTION_TO_CATEGORY = {}
for cat, actions in ACTION_CATEGORIES.items():
    for a in actions:
        ACTION_TO_CATEGORY[a] = cat

COMPLETE_MODELS = frozenset(
    {
        "oss120b",
        "qwen27b",
        "qwen35b",
        "qwen4b",
        "qwen397b",
        "gemma31b",
        "nemotron30b",
        "deepseek_r1_7b",
    }
)


def load_episodes(episodes_dir: str) -> list:
    """Load all episode JSONs from results directory."""
    episodes = []
    seen_keys: set[str] = set()
    for model_dir in sorted(glob.glob(os.path.join(episodes_dir, "*"))):
        if not os.path.isdir(model_dir):
            continue
        model_name = os.path.basename(model_dir)
        if model_name not in COMPLETE_MODELS:
            continue
        for ep_file in sorted(glob.glob(os.path.join(model_dir, "*.json"))):
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                if not isinstance(ep, dict):
                    continue
                key = f"{model_name}_{ep.get('scenario_id', '')}_{ep.get('run_index', 0)}"
                if key in seen_keys:
                    continue
                seen_keys.add(key)
                ep["_model"] = model_name
                ep["_file"] = ep_file
                episodes.append(ep)
            except (OSError, json.JSONDecodeError):
                continue
    return episodes


def analyze_action_class_duration(episodes: list) -> dict:
    """Analysis 1: Duration per action category.
    Since each action = 5 min fixed, this measures how many actions
    of each category occur and their position in the episode timeline.
    """
    category_positions = defaultdict(list)  # category → list of (relative_position, model)
    category_counts = defaultdict(list)  # category → list of counts per episode

    for ep in episodes:
        actions = ep.get("actions", [])
        if not actions:
            continue
        n_actions = len(actions)
        cat_count = Counter()

        for i, action in enumerate(actions):
            action_name = action.get("action_id", action.get("action", "")) if isinstance(action, dict) else str(action)
            # Normalize action name
            action_lower = action_name.lower().replace(" ", "_").replace("-", "_")
            cat = ACTION_TO_CATEGORY.get(action_lower, "other")
            cat_count[cat] += 1
            category_positions[cat].append(i / max(n_actions - 1, 1))

        for cat in ACTION_CATEGORIES:
            category_counts[cat].append(cat_count.get(cat, 0))

    result = {}
    for cat in ACTION_CATEGORIES:
        positions = category_positions.get(cat, [])
        counts = category_counts.get(cat, [])
        result[cat] = {
            "mean_relative_position": round(float(np.mean(positions)), 3) if positions else None,
            "std_relative_position": round(float(np.std(positions)), 3) if positions else None,
            "mean_count_per_episode": round(float(np.mean(counts)), 2),
            "total_occurrences": len(positions),
        }
    return result


def analyze_parallelizable_batching(episodes: list) -> dict:
    """Analysis 2: Identify action pairs that are frequently adjacent
    and could be parallelized in real clinical practice.
    """
    PARALLELIZABLE_PAIRS = [
        ("order_cbc", "order_bmp"),
        ("order_cbc", "order_blood_cultures"),
        ("order_troponin", "order_ecg"),
        ("order_cbc", "order_coagulation"),
        ("continuous_cardiac_monitoring", "pulse_oximetry"),
    ]

    pair_gaps = defaultdict(list)  # pair → list of step gaps

    for ep in episodes:
        actions = ep.get("actions", [])
        if not actions:
            continue
        action_positions = {}
        for i, action in enumerate(actions):
            name = action.get("action_id", action.get("action", "")) if isinstance(action, dict) else str(action)
            name_lower = str(name).lower().replace(" ", "_").replace("-", "_")
            if name_lower not in action_positions:
                action_positions[name_lower] = i

        for a1, a2 in PARALLELIZABLE_PAIRS:
            if a1 in action_positions and a2 in action_positions:
                gap = abs(action_positions[a1] - action_positions[a2])
                pair_gaps[(a1, a2)].append(gap)

    result = {}
    for (a1, a2), gaps in pair_gaps.items():
        result[f"{a1}_vs_{a2}"] = {
            "mean_step_gap": round(float(np.mean(gaps)), 2),
            "median_step_gap": int(np.median(gaps)),
            "pct_adjacent": round(100 * sum(1 for g in gaps if g <= 1) / len(gaps), 1),
            "n_episodes": len(gaps),
        }
    return result


def analyze_timing_violation_margins(episodes: list) -> dict:
    """Analysis 3: For each WITHIN violation, compute margin = (actual_time - deadline).
    If margins are clustered near boundary → potential artifact.
    If margins are spread → genuine clinical delay.
    """
    margins = []
    margins_by_domain = defaultdict(list)

    for ep in episodes:
        violations = ep.get("violation_events", [])
        scenario_id = ep.get("scenario_id", "")
        domain = scenario_id.split("_")[0] if scenario_id else "unknown"

        for v in violations:
            if not isinstance(v, dict):
                continue
            vtype = v.get("type", "").upper()
            if vtype != "WITHIN":
                continue
            actual_time = v.get("actual_time", v.get("timestamp"))
            deadline = v.get("deadline", v.get("constraint_deadline"))
            if actual_time is not None and deadline is not None:
                margin = float(actual_time) - float(deadline)
                margins.append(margin)
                margins_by_domain[domain].append(margin)

    if not margins:
        return {"n_within_violations": 0, "note": "No WITHIN violations with timing data"}

    margins_arr = np.array(margins)
    return {
        "n_within_violations": len(margins),
        "mean_margin_minutes": round(float(np.mean(margins_arr)), 1),
        "median_margin_minutes": round(float(np.median(margins_arr)), 1),
        "std_margin_minutes": round(float(np.std(margins_arr)), 1),
        "pct_within_5min": round(100 * np.mean(margins_arr <= 5), 1),
        "pct_within_15min": round(100 * np.mean(margins_arr <= 15), 1),
        "pct_over_60min": round(100 * np.mean(margins_arr > 60), 1),
        "min_margin": round(float(np.min(margins_arr)), 1),
        "max_margin": round(float(np.max(margins_arr)), 1),
        "is_boundary_clustered": bool(np.mean(margins_arr <= 10) > 0.5),
        "domains_with_violations": len(margins_by_domain),
    }


def analyze_cross_model_consistency(episodes: list) -> dict:
    """Analysis 4: Same scenario, different models — do timing violations
    occur at the same constraint or different ones?
    """
    # Group by scenario
    scenario_violations = defaultdict(lambda: defaultdict(set))
    # scenario → model → set of violated constraint IDs

    for ep in episodes:
        scenario_id = ep.get("scenario_id", "")
        model = ep.get("_model", "unknown")
        violations = ep.get("violation_events", [])

        for v in violations:
            if not isinstance(v, dict):
                continue
            vtype = v.get("type", "").upper()
            if vtype == "WITHIN":
                constraint_id = v.get("constraint_id", v.get("action", "unknown"))
                scenario_violations[scenario_id][model].add(constraint_id)

    # Compute agreement
    n_scenarios_with_timing = 0
    n_scenarios_all_agree = 0
    n_scenarios_partial_agree = 0
    jaccard_scores = []

    for scenario_id, model_viols in scenario_violations.items():
        if len(model_viols) < 2:
            continue
        n_scenarios_with_timing += 1

        viol_sets = list(model_viols.values())
        # Pairwise Jaccard
        for i in range(len(viol_sets)):
            for j in range(i + 1, len(viol_sets)):
                union = viol_sets[i] | viol_sets[j]
                inter = viol_sets[i] & viol_sets[j]
                if union:
                    jaccard_scores.append(len(inter) / len(union))

        # All models agree on same violations?
        if len(set(frozenset(s) for s in viol_sets)) == 1:
            n_scenarios_all_agree += 1
        elif any(viol_sets[0] & viol_sets[k] for k in range(1, len(viol_sets))):
            n_scenarios_partial_agree += 1

    return {
        "n_scenarios_with_timing_violations": n_scenarios_with_timing,
        "n_scenarios_all_models_agree": n_scenarios_all_agree,
        "n_scenarios_partial_agreement": n_scenarios_partial_agree,
        "mean_jaccard": round(float(np.mean(jaccard_scores)), 3) if jaccard_scores else None,
        "interpretation": (
            "High Jaccard indicates timing violations are scenario-driven (genuine), "
            "not model-artifact. Low Jaccard would suggest model-specific timing behavior."
        ),
    }


def generate_tex_macros(result: dict) -> dict:
    """Generate macro name → value pairs for auto_numbers.tex."""
    macros = {}
    margin = result.get("timing_margins", {})
    cross = result.get("cross_model_consistency", {})

    if margin.get("n_within_violations", 0) > 0:
        macros["timingNWithinViols"] = margin["n_within_violations"]
        macros["timingMeanMargin"] = margin["mean_margin_minutes"]
        macros["timingMedianMargin"] = margin["median_margin_minutes"]
        macros["timingPctBoundary"] = margin["pct_within_5min"]
        macros["timingPctOver60"] = margin["pct_over_60min"]
        macros["timingIsBoundary"] = "yes" if margin["is_boundary_clustered"] else "no"

    if cross.get("mean_jaccard") is not None:
        macros["timingJaccard"] = cross["mean_jaccard"]
        macros["timingNScenariosAgree"] = cross["n_scenarios_all_models_agree"]

    return macros


def main():
    parser = argparse.ArgumentParser(description="Timing Validity Audit")
    parser.add_argument("--episodes-dir", default="results/full_706_v5")
    parser.add_argument("--output", default="evidence_pack/analysis/timing_validity_audit.json")
    parser.add_argument("--tex-output", default="paper/auto_numbers.tex")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("Loading episodes...")
    episodes = load_episodes(args.episodes_dir)
    print(f"  Loaded {len(episodes)} episodes")

    if not episodes:
        print("ERROR: No episodes found. Check --episodes-dir path.")
        sys.exit(1)

    # Check that episodes have action detail
    has_actions = sum(1 for ep in episodes if ep.get("actions"))
    print(f"  Episodes with action detail: {has_actions}/{len(episodes)}")
    if has_actions == 0:
        print("ERROR: No episodes have action detail. Bug 5 fix required.")
        sys.exit(1)

    print("\n=== Analysis 1: Action-Class Duration ===")
    duration = analyze_action_class_duration(episodes)
    for cat, stats in duration.items():
        if stats["total_occurrences"] > 0:
            print(
                f"  {cat}: pos={stats['mean_relative_position']:.2f}±{stats['std_relative_position']:.2f}, "
                f"mean_count={stats['mean_count_per_episode']:.1f}, n={stats['total_occurrences']}"
            )

    print("\n=== Analysis 2: Parallelizable Action Batching ===")
    batching = analyze_parallelizable_batching(episodes)
    for pair, stats in batching.items():
        print(
            f"  {pair}: gap={stats['mean_step_gap']:.1f}, adjacent={stats['pct_adjacent']:.0f}%, n={stats['n_episodes']}"
        )

    print("\n=== Analysis 3: Timing Violation Margins ===")
    margins = analyze_timing_violation_margins(episodes)
    if margins.get("n_within_violations", 0) > 0:
        print(f"  N violations: {margins['n_within_violations']}")
        print(
            f"  Margin: {margins['mean_margin_minutes']:.1f}±{margins['std_margin_minutes']:.1f} min "
            f"(median {margins['median_margin_minutes']:.1f})"
        )
        print(f"  Within 5 min of deadline: {margins['pct_within_5min']:.0f}%")
        print(f"  Over 60 min past: {margins['pct_over_60min']:.0f}%")
        print(f"  Boundary clustered: {margins['is_boundary_clustered']}")
    else:
        print("  No WITHIN violations with timing data found")

    print("\n=== Analysis 4: Cross-Model Consistency ===")
    cross = analyze_cross_model_consistency(episodes)
    print(f"  Scenarios with timing violations (≥2 models): {cross['n_scenarios_with_timing_violations']}")
    print(f"  All models agree: {cross['n_scenarios_all_models_agree']}")
    print(f"  Mean Jaccard: {cross['mean_jaccard']}")

    # Compile result
    result = {
        "n_episodes": len(episodes),
        "n_with_actions": has_actions,
        "action_class_duration": duration,
        "parallelizable_batching": batching,
        "timing_margins": margins,
        "cross_model_consistency": cross,
    }

    # Save
    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2)
    print(f"\n✅ Saved to {args.output}")

    # Generate tex macros
    macros = generate_tex_macros(result)
    if macros:
        print(f"\n=== Tex macros ({len(macros)}) ===")
        for k, v in macros.items():
            print(f"  \\{k} = {v}")


if __name__ == "__main__":
    main()
