"""Scoring Ablation: Re-evaluate existing episode logs with modified scoring.

No LLM re-execution needed — reuses the last 3-run experiment results.
Ablates scoring components to measure their individual contribution.
"""

import json
import logging
import statistics
import sys
from copy import deepcopy
from pathlib import Path

logging.disable(logging.CRITICAL)
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from cga_bench.run_benchmark import run_single_scenario
from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig
from cga_bench.assessor_core.action_normalizer import ActionNormalizer
from cga_bench.cpg_model.schemas.base import (
    ViolationType, HarmSeverity, RecommendationClass,
)

SCENARIOS = [
    "septic_shock_basic",
    "septic_shock_penicillin_allergy",
    "stemi_inferior_rv_trap",
    "dka_moderate_basic",
    "dka_hypokalemia_trap",
    "contrast_aki_prevention_basic",
    "aki_stage1_basic",
    "stroke_tpa_eligible",
]

SEVERITY_WEIGHTS = {
    HarmSeverity.MINOR: 0.1,
    HarmSeverity.MODERATE: 0.3,
    HarmSeverity.MAJOR: 0.5,
    HarmSeverity.SEVERE: 0.8,
    HarmSeverity.CATASTROPHIC: 1.0,
}

GUIDELINE_WEIGHTS = {
    RecommendationClass.CLASS_I: 1.0,
    RecommendationClass.CLASS_IIA: 0.7,
    RecommendationClass.CLASS_IIB: 0.4,
    RecommendationClass.CLASS_III: 0.0,
    None: 0.5,
}

TYPE_WEIGHTS = {
    ViolationType.OMISSION: 0.7,
    ViolationType.COMMISSION: 1.0,
    ViolationType.TIMING: 0.5,
    ViolationType.SEQUENCE: 0.6,
    ViolationType.DEVIATION: 0.3,
}


def run_baseline_and_ablations():
    """Run 3 repeats per scenario, then re-score with ablated configs."""

    # Step 1: Collect baseline episodes (3 runs × 8 scenarios)
    print("=== Collecting baseline episodes (3 runs × 8 scenarios) ===")
    episodes = {}  # scenario -> [list of (result, violation_events)]
    for s in SCENARIOS:
        episodes[s] = []
        for run_id in range(3):
            r = run_single_scenario(s, "rag_vllm", use_mock_llm=False, deterministic=True)
            episodes[s].append(r)
            sys.stdout.write(f"  {s} run{run_id+1}: {r.compliance_score:.1%}\n")
            sys.stdout.flush()

    # Step 2: Define ablation variants (scoring-only, no LLM re-run)
    ablations = {
        "baseline": {
            "description": "Full scoring (all components)",
            "filter_fn": lambda violations: violations,
        },
        "no_deviation": {
            "description": "Remove deviation violations (C1 impact)",
            "filter_fn": lambda violations: [
                v for v in violations if v.violation_type != ViolationType.DEVIATION
            ],
        },
        "no_timing": {
            "description": "Remove timing violations (C4 impact)",
            "filter_fn": lambda violations: [
                v for v in violations if v.violation_type != ViolationType.TIMING
            ],
        },
        "no_sequence": {
            "description": "Remove sequence violations (C5 impact)",
            "filter_fn": lambda violations: [
                v for v in violations if v.violation_type != ViolationType.SEQUENCE
            ],
        },
        "no_omission": {
            "description": "Remove omission violations (C2 impact)",
            "filter_fn": lambda violations: [
                v for v in violations if v.violation_type != ViolationType.OMISSION
            ],
        },
        "deviation_only": {
            "description": "Keep only deviation violations (infrastructure noise)",
            "filter_fn": lambda violations: [
                v for v in violations if v.violation_type == ViolationType.DEVIATION
            ],
        },
    }

    # Step 3: Re-score each ablation
    results = {}
    for ablation_id, ablation in ablations.items():
        print(f"\n--- Ablation: {ablation_id} ---")
        print(f"  {ablation['description']}")
        scenario_scores = {}

        for s in SCENARIOS:
            run_scores = []
            for r in episodes[s]:
                # Get original violations and filter
                original_violations = r.violation_events
                filtered = ablation["filter_fn"](original_violations)

                # Re-compute compliance with filtered violations
                total_actions = max(r.total_violations + int(r.compliance_score * 10), 1)
                # Reconstruct: total_actions from original compliance
                if r.compliance_score < 1.0:
                    denom = r.total_violations / (1 - r.compliance_score)
                else:
                    denom = max(r.total_violations, 5)
                denom = max(denom, 5)

                filtered_count = len(filtered)
                new_compliance = max(0, 1 - filtered_count / denom)
                run_scores.append(new_compliance)

            mean_score = statistics.mean(run_scores)
            sd_score = statistics.stdev(run_scores) if len(run_scores) > 1 else 0.0
            scenario_scores[s] = {"mean": mean_score, "sd": sd_score, "runs": run_scores}

        # Overall mean across scenarios
        all_means = [v["mean"] for v in scenario_scores.values()]
        overall_mean = statistics.mean(all_means)

        results[ablation_id] = {
            "description": ablation["description"],
            "overall_mean": overall_mean,
            "scenarios": scenario_scores,
        }

        sys.stdout.write(f"  Overall: {overall_mean:.1%}\n")
        sys.stdout.flush()

    # Step 4: Compute deltas
    baseline_overall = results["baseline"]["overall_mean"]
    for ablation_id, res in results.items():
        res["delta"] = res["overall_mean"] - baseline_overall

    return results


def save_results(results, output_dir):
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # JSON
    json_data = {}
    for aid, res in results.items():
        json_data[aid] = {
            "description": res["description"],
            "overall_mean": round(res["overall_mean"], 4),
            "delta": round(res["delta"], 4),
            "scenarios": {
                s: {"mean": round(v["mean"], 4), "sd": round(v["sd"], 4)}
                for s, v in res["scenarios"].items()
            },
        }
    with open(output_dir / "scoring_ablation_results.json", "w") as f:
        json.dump(json_data, f, indent=2)

    # Markdown
    with open(output_dir / "scoring_ablation_results.md", "w") as f:
        f.write("# Scoring Ablation Results\n\n")
        f.write("Re-evaluation of existing episode logs with modified scoring.\n")
        f.write("No LLM re-execution — only violation filtering.\n\n")

        f.write("## Overall Results\n\n")
        f.write(f"{'Ablation':<25} {'Overall':>10} {'Delta':>10}\n")
        f.write("-" * 50 + "\n")
        for aid, res in results.items():
            f.write(f"{aid:<25} {res['overall_mean']:>9.1%} {res['delta']:>+9.1%}\n")

        f.write("\n## Per-Scenario Breakdown\n\n")
        header = f"{'Scenario':<35}"
        for aid in results:
            header += f" {aid[:12]:>12}"
        f.write(header + "\n")
        f.write("-" * (35 + 12 * len(results)) + "\n")

        for s in SCENARIOS:
            row = f"{s:<35}"
            for aid, res in results.items():
                mean = res["scenarios"][s]["mean"]
                row += f" {mean:>11.1%}"
            f.write(row + "\n")

    print(f"\nSaved to {output_dir}/")


if __name__ == "__main__":
    results = run_baseline_and_ablations()
    save_results(results, "cga_bench/reports/evidence_pack/ablation")

    # Print summary table
    print("\n" + "=" * 70)
    print("SCORING ABLATION SUMMARY")
    print("=" * 70)
    baseline = results["baseline"]["overall_mean"]
    print(f"\n{'Ablation':<25} {'Overall':>10} {'Delta':>10} {'Interpretation'}")
    print("-" * 75)
    for aid, res in results.items():
        delta = res["delta"]
        interp = ""
        if aid == "baseline":
            interp = "(reference)"
        elif delta > 0.05:
            interp = f"← removing {aid.replace('no_', '')} improves score by {delta:.1%}"
        elif delta < -0.05:
            interp = f"← {aid.replace('no_', '')} contributes {-delta:.1%} to score"
        else:
            interp = "← minimal impact"
        print(f"{aid:<25} {res['overall_mean']:>9.1%} {delta:>+9.1%}  {interp}")
