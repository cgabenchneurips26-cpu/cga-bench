#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""Integrate frontier model results into the 6-model analysis pipeline.

Loads results from existing 4 OSS models + 2 new frontier models and
recomputes all statistical analyses with k=6:
  - Friedman test (k=6 instead of k=4)
  - Composite metrics (CGA, coverage, efficiency)
  - Model rankings
  - Statistical power improvement estimate

Usage:
    PYTHONPATH=. python scripts/experiments/integrate_frontier_results.py
    PYTHONPATH=. python scripts/experiments/integrate_frontier_results.py --dry-run
"""
from __future__ import annotations

import json
from pathlib import Path
import statistics

import numpy as np
from scipy import stats as scipy_stats

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]  # cga_bench/
RESULTS_DIR = BASE_DIR / "results"
COMPOSITE_PATH = BASE_DIR / "evidence_pack" / "analysis" / "composite_metric.json"
OUTPUT_PATH = BASE_DIR / "evidence_pack" / "analysis" / "frontier_integrated_stats.json"

ALL_15: list[str] = [
    "septic_shock_basic",
    "septic_shock_penicillin_allergy",
    "stemi_inferior_rv_trap",
    "dka_moderate_basic",
    "dka_hypokalemia_trap",
    "stroke_tpa_eligible",
    "contrast_aki_prevention_basic",
    "aki_stage1_basic",
    "af_new_onset_basic",
    "gi_bleeding_upper_basic",
    "htn_emergency_basic",
    "pe_submassive_basic",
    "copd_moderate_exacerbation",
    "adhf_warm_wet",
    "hemorrhagic_stroke",
]

# Original 4 OSS models
OSS_MODELS: list[tuple[str, int, list[str]]] = [
    ("oss-120b", 120, [
        "eval_science_rag_oss120b/baseline",
        "expansion_3run/run0",
        "expansion_3run/run1",
        "expansion_3run/run2",
    ]),
    ("Qwen3.5-35B", 35, [
        "eval_science_qwen35/baseline",
        "eval_science_rag_qwen35/baseline",
    ]),
    ("oss-20b", 20, [
        "eval_science_rag_oss20b/baseline",
    ]),
    ("Qwen3-4B", 4, [
        "eval_science_rag_qwen3_4b/baseline",
    ]),
]

# Frontier models (P2-1)
FRONTIER_MODELS: list[tuple[str, int, list[str]]] = [
    ("GPT-4o", 0, [
        "eval_science_rag_gpt4o/baseline",
    ]),
    ("Claude-3.5-Sonnet", 0, [
        "eval_science_rag_claude35/baseline",
    ]),
]

ALL_MODELS = OSS_MODELS + FRONTIER_MODELS


def load_results_for_model(
    dirs: list[str],
) -> dict[str, list[dict]]:
    """Load episode results from directories.

    Args:
        dirs: List of result directory paths relative to RESULTS_DIR.

    Returns:
        Dict mapping scenario_id to list of result dicts.
    """
    model_data: dict[str, list[dict]] = {}
    for d in dirs:
        p = RESULTS_DIR / d
        if not p.exists():
            continue
        for jf in sorted(p.glob("*.json")):
            if jf.name.endswith("summary.json"):
                continue
            with open(jf, encoding="utf-8") as f:
                r = json.load(f)
            sid = r.get("scenario_id", "")
            if sid in ALL_15 and "compliance_score" in r:
                model_data.setdefault(sid, []).append(r)
    return model_data


def load_all_results() -> dict[str, dict[str, list[dict]]]:
    """Load results for all 6 models.

    Returns:
        Dict mapping model label to {scenario_id: [results]}.
    """
    all_data: dict[str, dict[str, list[dict]]] = {}
    for label, _params, dirs in ALL_MODELS:
        all_data[label] = load_results_for_model(dirs)
    return all_data


def compute_scenario_means(
    all_data: dict[str, dict[str, list[dict]]],
) -> dict[str, dict[str, float]]:
    """Compute mean compliance per model per scenario.

    Args:
        all_data: Full results dict.

    Returns:
        Dict mapping model label to {scenario_id: mean_compliance}.
    """
    means: dict[str, dict[str, float]] = {}
    for label in all_data:
        means[label] = {}
        for sid in ALL_15:
            runs = all_data[label].get(sid, [])
            if runs:
                scores = [r["compliance_score"] for r in runs]
                means[label][sid] = statistics.mean(scores)
    return means


def bootstrap_ci(
    values: list[float],
    n_boot: int = 10_000,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Compute bootstrap confidence interval.

    Args:
        values: Sample values.
        n_boot: Number of bootstrap iterations.
        alpha: Significance level.

    Returns:
        Tuple of (mean, lower_ci, upper_ci).
    """
    if len(values) < 2:
        m = values[0] if values else 0.0
        return m, m, m
    arr = np.array(values)
    boot_means = np.array([
        np.mean(np.random.choice(arr, size=len(arr), replace=True))
        for _ in range(n_boot)
    ])
    lo = float(np.percentile(boot_means, 100 * alpha / 2))
    hi = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    return float(np.mean(arr)), lo, hi


def friedman_test(
    means: dict[str, dict[str, float]],
    model_labels: list[str],
) -> dict:
    """Run Friedman test across models.

    Args:
        means: Per-model per-scenario mean scores.
        model_labels: List of model labels to include.

    Returns:
        Dict with Friedman test results.
    """
    matrix: list[list[float]] = []
    valid_scenarios: list[str] = []

    for sid in ALL_15:
        row: list[float] = []
        all_present = True
        for label in model_labels:
            if sid in means.get(label, {}):
                row.append(means[label][sid])
            else:
                all_present = False
                break
        if all_present:
            matrix.append(row)
            valid_scenarios.append(sid)

    if len(matrix) < 3:
        return {
            "error": f"Insufficient data: {len(matrix)} scenarios with all models present",
            "valid_scenarios": valid_scenarios,
            "k": len(model_labels),
        }

    arr = np.array(matrix)
    columns = [arr[:, i] for i in range(arr.shape[1])]
    stat, p_value = scipy_stats.friedmanchisquare(*columns)

    return {
        "statistic": round(float(stat), 4),
        "p_value": float(p_value),
        "significant": bool(p_value < 0.05),
        "k": len(model_labels),
        "n_scenarios": len(valid_scenarios),
        "valid_scenarios": valid_scenarios,
    }


def compute_composite(
    all_data: dict[str, dict[str, list[dict]]],
    means: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Compute composite metrics for all models.

    Args:
        all_data: Full results dict.
        means: Per-model per-scenario means.

    Returns:
        Dict mapping model label to composite metric dict.
    """
    # Load expected actions from existing composite_metric.json if available
    exp_actions: dict[str, int] = {}
    if COMPOSITE_PATH.exists():
        with open(COMPOSITE_PATH, encoding="utf-8") as f:
            comp_data = json.load(f)
        per_scenario = comp_data.get("per_scenario", {})
        for sc in per_scenario:
            for model_data in per_scenario[sc].values():
                if "exp_actions" in model_data:
                    exp_actions[sc] = int(model_data["exp_actions"])
                    break

    composites: dict[str, dict[str, float]] = {}

    for label in all_data:
        cga_scores: list[float] = []
        action_counts: list[float] = []
        coverage_values: list[float] = []

        for sid in ALL_15:
            if sid not in means.get(label, {}):
                continue
            cga_scores.append(means[label][sid])

            runs = all_data[label].get(sid, [])
            if runs:
                avg_actions = statistics.mean(
                    r.get("actions_count", 0) for r in runs
                )
                action_counts.append(avg_actions)

                ea = exp_actions.get(sid, 1)
                coverage_values.append(avg_actions / ea if ea > 0 else 0)

        if not cga_scores:
            continue

        avg_cga = statistics.mean(cga_scores)
        avg_actions = statistics.mean(action_counts) if action_counts else 0
        avg_coverage = statistics.mean(coverage_values) if coverage_values else 0
        capped_cov = min(avg_coverage, 1.0)
        efficiency = (avg_cga / avg_actions) if avg_actions > 0 else 0

        composites[label] = {
            "cga": round(avg_cga, 4),
            "actions": round(avg_actions, 4),
            "coverage": round(avg_coverage, 4),
            "capped_cov": round(capped_cov, 4),
            "efficiency": round(efficiency, 4),
            "num_scenarios": len(cga_scores),
        }

    return composites


def power_improvement_estimate() -> dict:
    """Estimate statistical power improvement from k=4 to k=6.

    Returns:
        Dict describing the expected power improvement.
    """
    # Friedman test power increases with k (number of groups)
    # Approximate: chi2 df = k-1, so df goes from 3 to 5
    # For same effect size and n=15 scenarios:
    k4_df = 3
    k6_df = 5

    # Critical values at alpha=0.05
    k4_critical = scipy_stats.chi2.ppf(0.95, df=k4_df)
    k6_critical = scipy_stats.chi2.ppf(0.95, df=k6_df)

    return {
        "k4_degrees_of_freedom": k4_df,
        "k6_degrees_of_freedom": k6_df,
        "k4_critical_value_alpha05": round(float(k4_critical), 4),
        "k6_critical_value_alpha05": round(float(k6_critical), 4),
        "note": (
            "With k=6 models (vs k=4), the Friedman test gains 2 additional "
            "degrees of freedom (df=5 vs df=3). This increases sensitivity to "
            "detect rank differences across models, especially between the OSS "
            "and frontier model performance tiers."
        ),
        "expected_benefits": [
            "Higher statistical power for detecting model-level differences",
            "Ability to test OSS vs frontier sub-group contrasts",
            "More robust rank ordering with 6 data points per scenario",
            "Post-hoc Nemenyi test gains resolution with more groups",
        ],
    }


def run_dry_analysis() -> None:
    """Run analysis showing expected structure without frontier data."""
    print("=" * 70)
    print("  P2-1 Integration — DRY RUN (frontier data not yet collected)")
    print("=" * 70)

    all_data = {}
    means: dict[str, dict[str, float]] = {}

    # Load existing 4 models
    for label, _params, dirs in OSS_MODELS:
        all_data[label] = load_results_for_model(dirs)

    for label in all_data:
        means[label] = {}
        for sid in ALL_15:
            runs = all_data[label].get(sid, [])
            if runs:
                scores = [r["compliance_score"] for r in runs]
                means[label][sid] = statistics.mean(scores)

    # Existing k=4 Friedman
    oss_labels = [m[0] for m in OSS_MODELS]
    friedman_k4 = friedman_test(means, oss_labels)

    print("\nExisting k=4 Friedman test:")
    print(f"  Statistic: {friedman_k4.get('statistic', 'N/A')}")
    print(f"  p-value:   {friedman_k4.get('p_value', 'N/A')}")
    print(f"  Scenarios: {friedman_k4.get('n_scenarios', 0)}/15")

    # Check frontier data availability
    frontier_available: dict[str, int] = {}
    for label, _params, dirs in FRONTIER_MODELS:
        data = load_results_for_model(dirs)
        n_scenarios = len([s for s in ALL_15 if s in data])
        frontier_available[label] = n_scenarios

    print("\nFrontier data availability:")
    for label, n in frontier_available.items():
        status = "READY" if n == 15 else f"MISSING ({n}/15)"
        print(f"  {label}: {status}")

    # Power improvement
    power = power_improvement_estimate()
    print("\nStatistical power improvement (k=4 -> k=6):")
    print(f"  k=4 df={power['k4_degrees_of_freedom']}, critical={power['k4_critical_value_alpha05']}")
    print(f"  k=6 df={power['k6_degrees_of_freedom']}, critical={power['k6_critical_value_alpha05']}")

    # Save dry-run output
    output = {
        "mode": "dry_run",
        "existing_friedman_k4": friedman_k4,
        "frontier_data_availability": frontier_available,
        "power_improvement": power,
        "expected_output_when_complete": {
            "friedman_k6": "Friedman test with all 6 models",
            "composite_6model": "Composite metrics for 6 models",
            "rankings_6model": "Full model rankings",
            "bootstrap_ci_6model": "95% CI per model",
        },
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nDry-run analysis saved: {OUTPUT_PATH}")


def run_full_analysis() -> None:
    """Run full 6-model integration analysis."""
    np.random.seed(42)

    print("=" * 70)
    print("  P2-1 Integration — Full 6-Model Analysis")
    print("=" * 70)

    all_data = load_all_results()
    means = compute_scenario_means(all_data)

    all_labels = [m[0] for m in ALL_MODELS]
    oss_labels = [m[0] for m in OSS_MODELS]

    # Check data completeness
    print("\nData completeness:")
    all_complete = True
    for label in all_labels:
        n = len([s for s in ALL_15 if s in means.get(label, {})])
        status = "OK" if n == 15 else f"INCOMPLETE ({n}/15)"
        if n < 15:
            all_complete = False
        print(f"  {label}: {n}/15 {status}")

    if not all_complete:
        print("\nWARNING: Not all models have complete data.")
        print("Running analysis with available data.\n")

    # Table: mean per model
    print(f"\n{'Scenario':<35}", end="")
    for label in all_labels:
        print(f" {label:>15}", end="")
    print()

    model_all_means: dict[str, list[float]] = {m: [] for m in all_labels}
    for sid in ALL_15:
        print(f"{sid:<35}", end="")
        for label in all_labels:
            if sid in means.get(label, {}):
                m = means[label][sid]
                print(f" {m:>14.1%}", end="")
                model_all_means[label].append(m)
            else:
                print(f" {'---':>14}", end="")
        print()

    print(f"\n{'Average':<35}", end="")
    for label in all_labels:
        vals = model_all_means[label]
        if vals:
            print(f" {statistics.mean(vals):>14.1%}", end="")
        else:
            print(f" {'---':>14}", end="")
    print()

    # Friedman k=4 (original)
    friedman_k4 = friedman_test(means, oss_labels)
    print(f"\nFriedman k=4 (OSS only): stat={friedman_k4.get('statistic', 'N/A')}, "
          f"p={friedman_k4.get('p_value', 'N/A')}")

    # Friedman k=6 (all models)
    friedman_k6 = friedman_test(means, all_labels)
    print(f"Friedman k=6 (all):      stat={friedman_k6.get('statistic', 'N/A')}, "
          f"p={friedman_k6.get('p_value', 'N/A')}")

    # Bootstrap CI
    print("\nBootstrap 95% CI (CGA compliance):")
    ci_results: dict[str, dict[str, float]] = {}
    for label in all_labels:
        vals = model_all_means[label]
        if vals:
            mean_val, lo, hi = bootstrap_ci(vals)
            ci_results[label] = {"mean": round(mean_val, 4), "ci_lo": round(lo, 4), "ci_hi": round(hi, 4)}
            print(f"  {label:<20} {mean_val:.1%} [{lo:.1%}, {hi:.1%}]")

    # Composite metrics
    composites = compute_composite(all_data, means)
    print("\nComposite Metrics:")
    print(f"  {'Model':<20} {'CGA':>8} {'Actions':>8} {'Coverage':>8} {'Efficiency':>8}")
    for label in all_labels:
        if label in composites:
            c = composites[label]
            print(f"  {label:<20} {c['cga']:>7.1%} {c['actions']:>8.1f} {c['coverage']:>8.3f} {c['efficiency']:>8.4f}")

    # Rankings
    ranked = sorted(
        [(label, composites[label]["cga"]) for label in composites],
        key=lambda x: x[1],
        reverse=True,
    )
    print("\nRankings by CGA:")
    for i, (label, score) in enumerate(ranked, 1):
        print(f"  {i}. {label}: {score:.1%}")

    # Power analysis
    power = power_improvement_estimate()

    # Save results
    output = {
        "mode": "full_analysis",
        "n_models": len(all_labels),
        "models": all_labels,
        "friedman_k4_oss": friedman_k4,
        "friedman_k6_all": friedman_k6,
        "bootstrap_ci": ci_results,
        "composite_metrics": composites,
        "rankings_by_cga": [{"rank": i + 1, "model": label, "cga": score}
                            for i, (label, score) in enumerate(ranked)],
        "power_improvement": power,
    }
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2)
    print(f"\nFull analysis saved: {OUTPUT_PATH}")


def main() -> None:
    """Entry point for frontier results integration."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Integrate frontier model results into 6-model analysis",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show expected analysis structure without requiring frontier data",
    )
    args = parser.parse_args()

    if args.dry_run:
        run_dry_analysis()
    else:
        run_full_analysis()


if __name__ == "__main__":
    main()
