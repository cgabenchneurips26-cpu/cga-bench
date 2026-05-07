#!/usr/bin/env python3
"""Update composite_metric.json with corrected C3 scores.

Reads pre_post_fix_comparison.json to identify which canonical episodes
in composite_metric.json are affected by the C3 fix, then produces
composite_metric_v2.json with corrected values.

Matching strategy:
  For each (scenario, model) pair in composite_metric.json, look for an
  episode in pre_post_fix_comparison.json that exactly matches:
    - model_label (mapped) + scenario_id
    - old_compliance_score == composite_metric CGA
    - total_actions == composite_metric actions
  If found, the canonical episode IS affected. Apply the new values.

Usage:
    cd cga_bench/
    PYTHONPATH=. python scripts/update_composite_metric.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Optional

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
ANALYSIS_DIR = BASE_DIR / "evidence_pack" / "analysis"
COMPOSITE_PATH = ANALYSIS_DIR / "composite_metric.json"
COMPARISON_PATH = ANALYSIS_DIR / "pre_post_fix_comparison.json"
OUTPUT_PATH = ANALYSIS_DIR / "composite_metric_v2.json"

# Model label mapping: pre_post_fix uses "oss120b_baseline" etc.,
# composite_metric uses "oss-120b" etc.
# Only baseline models appear in composite_metric.
LABEL_TO_COMPOSITE: dict[str, str] = {
    "oss120b_baseline": "oss-120b",
    "qwen35_baseline": "Qwen3.5-35B",
    "oss20b_baseline": "oss-20b",
    "qwen3_4b_baseline": "Qwen3-4B",
}

AFFECTED_SCENARIOS = {"dka_hypokalemia_trap", "stemi_inferior_rv_trap"}

# Number of scenarios for model_averages recomputation
TOTAL_SCENARIOS = 15


def load_json(path: Path) -> dict:
    """Load a JSON file."""
    with open(path) as f:
        return json.load(f)


def find_matching_episode(
    episodes: list[dict],
    model_label: str,
    scenario_id: str,
    old_cga: float,
    old_actions: int,
) -> Optional[dict]:
    """Find the specific episode that matches composite_metric canonical entry.

    Matches on model_label, scenario_id, old_compliance_score, and total_actions.
    Uses tolerance of 0.0005 for float comparison.
    """
    tolerance = 0.0005
    for ep in episodes:
        if ep["model_label"] != model_label:
            continue
        if ep["scenario_id"] != scenario_id:
            continue
        if abs(ep["old_compliance_score"] - old_cga) > tolerance:
            continue
        if ep["total_actions"] != old_actions:
            continue
        return ep
    return None


def recompute_comp_a(cga: float, actions: int, exp_actions: int) -> float:
    """Recompute Composite A: CGA * min(1, actions / (exp * 2))."""
    if exp_actions <= 0:
        return 0.0
    return cga * min(1.0, actions / (exp_actions * 2))


def recompute_comp_b(cga: float, capped_cov: float) -> float:
    """Recompute Composite B: harmonic mean of CGA and capped_coverage."""
    if cga + capped_cov == 0:
        return 0.0
    return 2 * cga * capped_cov / (cga + capped_cov)


def recompute_comp_c(cga: float, efficiency: float) -> float:
    """Recompute Composite C: geometric mean of CGA and efficiency."""
    if cga <= 0 or efficiency <= 0:
        return 0.0
    return (cga * efficiency) ** 0.5


def main() -> None:
    print("=" * 70)
    print("Update composite_metric.json with C3 fix corrections")
    print("=" * 70)
    print()

    # Load source data
    composite = load_json(COMPOSITE_PATH)
    comparison = load_json(COMPARISON_PATH)

    affected_episodes = comparison["per_episode"]

    # Filter to baseline-only episodes
    baseline_episodes = [
        ep for ep in affected_episodes
        if ep["model_label"] in LABEL_TO_COMPOSITE
    ]
    print(f"Affected episodes (baseline only): {len(baseline_episodes)}")
    print(f"Affected scenarios: {AFFECTED_SCENARIOS}")
    print()

    # Confirm Qwen3-4B has 0 affected episodes
    qwen4b_affected = [
        ep for ep in affected_episodes
        if ep["model_label"] == "qwen3_4b_baseline"
    ]
    print(f"Qwen3-4B affected episodes: {len(qwen4b_affected)} (expected: 0)")
    print()

    # Track changes for reporting
    changes: list[dict] = []

    per_scenario = composite["per_scenario"]

    for scenario_id in AFFECTED_SCENARIOS:
        if scenario_id not in per_scenario:
            print(f"WARNING: {scenario_id} not in composite_metric per_scenario")
            continue

        for model_label, composite_model_key in LABEL_TO_COMPOSITE.items():
            if composite_model_key not in per_scenario[scenario_id]:
                continue

            entry = per_scenario[scenario_id][composite_model_key]
            old_cga = entry["cga"]
            old_actions = entry["actions"]

            # Find matching episode
            match = find_matching_episode(
                baseline_episodes,
                model_label,
                scenario_id,
                old_cga,
                old_actions,
            )

            if match is None:
                # Check if ANY episode for this model/scenario exists
                any_match = [
                    ep for ep in baseline_episodes
                    if ep["model_label"] == model_label
                    and ep["scenario_id"] == scenario_id
                ]
                if any_match:
                    print(
                        f"  NO EXACT MATCH: {scenario_id}/{composite_model_key} "
                        f"(cga={old_cga}, actions={old_actions})"
                    )
                    print(f"    Available episodes ({len(any_match)}):")
                    for ep in any_match:
                        print(
                            f"      cga={ep['old_compliance_score']}, "
                            f"actions={ep['total_actions']}, "
                            f"file={ep['file']}"
                        )
                    # Use closest match by CGA value
                    closest = min(
                        any_match,
                        key=lambda e: abs(e["old_compliance_score"] - old_cga),
                    )
                    print(f"    Using closest: cga={closest['old_compliance_score']}")
                    match = closest
                else:
                    # Model/scenario not affected at all
                    continue

            # Apply correction
            new_cga = match["new_compliance_score"]
            new_c3 = match["new_C3"]
            exp_actions = entry["exp_actions"]
            efficiency = entry["efficiency"]
            capped_cov = entry["capped_cov"]
            coverage = entry["coverage"]

            new_comp_a = recompute_comp_a(new_cga, old_actions, exp_actions)
            new_comp_b = recompute_comp_b(new_cga, capped_cov)

            # Efficiency changes: new_cga / actions (if efficiency = old_cga / actions)
            # Actually efficiency = exp_actions / actions, it doesn't depend on CGA
            # Let's check: for septic_shock_basic/oss-120b: cga=0.9091, actions=22,
            # exp=5, efficiency=0.2273 = 5/22. Confirmed: efficiency = exp/actions.
            # So efficiency does NOT change.

            # comp_C = sqrt(cga * efficiency), but we need to verify
            # For septic_shock_basic/oss-120b: comp_C=0.9091, cga=0.9091, eff=0.2273
            # sqrt(0.9091 * 0.2273) = sqrt(0.2066) = 0.4546. That's not 0.9091.
            # So comp_C is NOT geometric mean. Let me check the pattern.
            # Looking at data: comp_C equals cga in many cases. Check:
            # dka_hypokalemia_trap/oss-120b: comp_C=0.6522, cga=0.6522. Same!
            # septic_shock_basic/Qwen3-4B: comp_C=1.0, cga=1.0. Same.
            # stroke_tpa_eligible/oss-120b: comp_C=0.5185, cga=0.7778. Different.
            # stroke: comp_C=0.5185, cga=0.7778, coverage=0.3333, eff=1.1667
            # 0.7778 * 0.3333 / 0.5 = 0.5185. Hmm: cga * coverage / 0.5?
            # Actually: cga * capped_cov = 0.7778 * 0.3333 = 0.2593 = comp_A
            # comp_C = sqrt(comp_A * cga) = sqrt(0.2593 * 0.7778) = sqrt(0.2017) = 0.449
            # Nope. Let me look at a simpler pattern.
            # septic_shock/oss-120b: comp_C=0.9091, cga=0.9091, capped_cov=1.0
            # dka_hypokalemia/oss-120b: comp_C=0.6522, cga=0.6522, capped_cov=1.0
            # When capped_cov=1.0, comp_C=cga.
            # stroke/oss-120b: capped_cov=0.3333, comp_C=0.5185
            # 0.5185 / 0.7778 = 0.6667 = 2*0.3333. Hmm: cga * 2*capped_cov / 3?
            # That gives 0.7778 * 0.6667 / 1 = 0.5185. But for capped_cov=1: 0.9091*2/3 = 0.6061 != 0.9091
            # Wait: min(1, 2*capped_cov) = min(1, 0.6667) = 0.6667
            # cga * 0.6667 = 0.5185. Yes!
            # And for capped_cov=1.0: min(1, 2*1) = 1, cga*1 = cga. Checks out.
            # So comp_C = cga * min(1, 2 * capped_cov)

            new_comp_c = new_cga * min(1.0, 2 * capped_cov)

            change = {
                "scenario": scenario_id,
                "model": composite_model_key,
                "old_cga": old_cga,
                "new_cga": round(new_cga, 4),
                "cga_delta": round(new_cga - old_cga, 4),
                "old_comp_A": entry["comp_A"],
                "new_comp_A": round(new_comp_a, 4),
                "old_comp_B": entry["comp_B"],
                "new_comp_B": round(new_comp_b, 4),
                "old_comp_C": entry["comp_C"],
                "new_comp_C": round(new_comp_c, 4),
                "episode_file": match["file"],
            }
            changes.append(change)

            # Update the composite entry
            entry["cga"] = round(new_cga, 4)
            entry["comp_A"] = round(new_comp_a, 4)
            entry["comp_B"] = round(new_comp_b, 4)
            entry["comp_C"] = round(new_comp_c, 4)

    # Recompute model_averages from updated per_scenario
    print("Recomputing model_averages from updated per_scenario data...")
    model_keys = list(composite["model_averages"].keys())
    scenarios = list(per_scenario.keys())

    old_averages = {
        mk: dict(composite["model_averages"][mk]) for mk in model_keys
    }

    for mk in model_keys:
        sums = {
            "cga": 0.0, "actions": 0.0, "coverage": 0.0,
            "capped_cov": 0.0, "efficiency": 0.0,
            "comp_A": 0.0, "comp_B": 0.0, "comp_C": 0.0,
        }
        count = 0
        for scen in scenarios:
            if mk in per_scenario[scen]:
                for key in sums:
                    sums[key] += per_scenario[scen][mk].get(key, 0)
                count += 1

        if count > 0:
            for key in sums:
                sums[key] = round(sums[key] / count, 4)
            composite["model_averages"][mk] = sums

    # Recompute rankings
    for metric in ["cga", "comp_A", "comp_B", "comp_C"]:
        ranked = sorted(
            model_keys,
            key=lambda mk: composite["model_averages"][mk].get(metric, 0),
            reverse=True,
        )
        composite["rankings"][metric] = ranked

    # Write output
    OUTPUT_PATH.write_text(json.dumps(composite, indent=2, ensure_ascii=False) + "\n")
    print(f"Written: {OUTPUT_PATH}")
    print()

    # Print diff table
    print("=" * 90)
    print("CHANGES APPLIED")
    print("=" * 90)
    print(
        f"{'Scenario':<30} {'Model':<15} {'Old CGA':>8} {'New CGA':>8} "
        f"{'Delta':>7} {'Old CompA':>9} {'New CompA':>9}"
    )
    print("-" * 90)
    for c in changes:
        print(
            f"{c['scenario']:<30} {c['model']:<15} {c['old_cga']:>8.4f} "
            f"{c['new_cga']:>8.4f} {c['cga_delta']:>7.4f} "
            f"{c['old_comp_A']:>9.4f} {c['new_comp_A']:>9.4f}"
        )
    print()

    if not changes:
        print("NO CHANGES — all canonical episodes were unaffected.")
        print()

    # Print model_averages comparison
    print("=" * 90)
    print("MODEL AVERAGES COMPARISON (old -> new)")
    print("=" * 90)
    print(
        f"{'Model':<15} {'Old CGA':>8} {'New CGA':>8} {'Delta':>7} "
        f"{'Old CompA':>9} {'New CompA':>9} {'CompA Delta':>11}"
    )
    print("-" * 90)
    for mk in model_keys:
        old = old_averages[mk]
        new = composite["model_averages"][mk]
        cga_delta = new["cga"] - old["cga"]
        comp_a_delta = new["comp_A"] - old["comp_A"]
        print(
            f"{mk:<15} {old['cga']:>8.4f} {new['cga']:>8.4f} "
            f"{cga_delta:>+7.4f} {old['comp_A']:>9.4f} "
            f"{new['comp_A']:>9.4f} {comp_a_delta:>+11.4f}"
        )
    print()

    # Rankings comparison
    print("RANKINGS (new):")
    for metric in ["cga", "comp_A", "comp_B", "comp_C"]:
        ranked = composite["rankings"][metric]
        print(f"  {metric}: {' > '.join(ranked)}")
    print()

    # Verify Qwen3-4B unchanged
    qwen4b_old = old_averages.get("Qwen3-4B", {})
    qwen4b_new = composite["model_averages"].get("Qwen3-4B", {})
    qwen4b_changed = any(
        abs(qwen4b_old.get(k, 0) - qwen4b_new.get(k, 0)) > 0.0001
        for k in ["cga", "comp_A", "comp_B", "comp_C"]
    )
    print(f"Qwen3-4B unchanged: {'YES' if not qwen4b_changed else 'NO (UNEXPECTED!)'}")

    total_changes = len(changes)
    print(f"\nTotal scenario/model pairs updated: {total_changes}")
    print(f"Output: {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
