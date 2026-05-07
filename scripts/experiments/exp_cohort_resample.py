#!/usr/bin/env python3
"""W9-3: Published-Cohort Re-sampling Defense Experiment

Defense against: "Your 706 scenarios are hand-crafted cherry-picks"

Approach:
  1. Load all V6 episode results (8 models × 706 scenarios × 3 runs)
  2. Apply two re-weighting strategies:
     a. Bootstrap re-sampling: random scenario subsets → ranking stability
     b. Published-prevalence weighting: weight by Rhee 2017 / Seymour 2016 distributions
  3. Compute Kendall τ between original and re-weighted model rankings

No GPU needed — pure re-analysis of existing results.

Usage:
    PYTHONPATH=. python scripts/experiments/exp_cohort_resample.py \
        --results-dir results/full_706_v5 \
        --n-resamples 1000 \
        --output evidence_pack/analysis/cohort_resample_results.json
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from scipy import stats

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))

# Published prevalence weights (proportion of ICU admissions by domain)
# Sources: Rhee 2017 (sepsis), Seymour 2016 (qSOFA), Vincent 2006 (ICU epidemiology)
PUBLISHED_PREVALENCE: dict[str, float] = {
    # Domain prefix → relative weight (normalized internally)
    "ssc": 3.0,  # Sepsis: ~6% of hospitalizations, ~30% of ICU (Rhee 2017)
    "sepsis": 3.0,
    "septic": 3.0,
    "aha": 2.0,  # ACS/Chest pain: ~15% of ED visits (Amsterdam 2010)
    "stemi": 2.0,
    "nstemi": 2.0,
    "chest": 2.0,
    "acls": 1.5,  # Cardiac arrest: ~1-2% of ICU (Andersen 2019)
    "pe": 1.2,  # PE: ~5% of ICU (Konstantinides 2020)
    "stroke": 1.5,  # Stroke: ~5% of ICU (Feigin 2021)
    "aki": 2.0,  # AKI: ~20-50% of ICU (Hoste 2015)
    "caki": 1.5,
    "kdigo": 1.5,
    "contrast": 1.5,
    "ckd": 1.0,
    "cap": 1.8,  # CAP: ~10-15% of ICU (Jain 2015)
    "copd": 1.5,  # COPD exacerbation: ~10% of ICU (GBD 2019)
    "gib": 1.0,  # GI bleeding: ~5% of ICU
    "gi": 1.0,
    "dka": 1.0,  # DKA: ~2-3% of ICU
    "htn": 0.8,  # Hypertensive emergency: ~1-2% of ICU
    "af": 1.2,  # AF: ~10% of ICU (Walkey 2014)
    "asthma": 0.8,  # Asthma exac: ~2% of ICU
    "anaph": 0.3,  # Anaphylaxis: rare in ICU
    "se": 0.5,  # Status epilepticus: ~1% of ICU
    "mening": 0.5,  # Meningitis: ~1% of ICU
    "safety": 1.0,  # Universal safety: baseline
    "aabb": 0.8,  # Transfusion
    "hf": 1.5,  # Heart failure
    "hfref": 1.5,
    "hfpef": 1.0,
    "adhf": 1.5,
    "cardiogenic": 1.0,
    "tox": 0.5,  # Toxicology
    "toxicology": 0.5,
    "pals": 0.3,  # Pediatric
    "acog": 0.3,  # Obstetric
    "apa": 0.5,  # Agitation/delirium
    "aba": 0.5,  # ARDS/misc
    "warfarin": 0.3,
    "emergency": 0.5,
    "unstable": 0.5,
    "hemorrhagic": 0.5,
}

# Canonical 8 models from V6
CANONICAL_MODELS = [
    "oss120b",
    "qwen35b",
    "qwen27b",
    "qwen4b",
    "qwen397b",
    "gemma31b",
    "nemotron30b",
    "deepseek_r1_7b",
]


def load_episodes(results_dir: str, models: list[str]) -> dict[str, dict[str, list[float]]]:
    """Load CGA scores grouped by model → scenario → [scores].

    Returns:
        {model: {scenario_id: [compliance_score_r0, r1, r2, ...]}}
    """
    data: dict[str, dict[str, list[float]]] = {}
    base = Path(results_dir)

    for model in models:
        model_dir = base / model
        if not model_dir.is_dir():
            print(f"  WARN: {model_dir} not found, skipping")
            continue

        model_data: dict[str, list[float]] = defaultdict(list)
        count = 0
        for fp in model_dir.glob("*.json"):
            try:
                ep = json.loads(fp.read_text())
            except (json.JSONDecodeError, OSError):
                continue

            if not isinstance(ep, dict):
                continue

            sid = ep.get("scenario_id", "")
            score = ep.get("compliance_score")
            if sid and score is not None:
                model_data[sid].append(float(score))
                count += 1

        data[model] = dict(model_data)
        print(f"  {model}: {count} episodes, {len(model_data)} scenarios")

    return data


def compute_model_ranking(
    data: dict[str, dict[str, list[float]]],
    scenario_weights: dict[str, float] | None = None,
) -> dict[str, float]:
    """Compute weighted mean CGA per model.

    Args:
        data: {model: {scenario_id: [scores]}}
        scenario_weights: {scenario_id: weight} or None for uniform
    """
    ranking: dict[str, float] = {}

    # Collect all scenario IDs
    all_scenarios: set[str] = set()
    for model_data in data.values():
        all_scenarios.update(model_data.keys())

    for model, model_data in data.items():
        weighted_sum = 0.0
        total_weight = 0.0

        for sid in all_scenarios:
            scores = model_data.get(sid, [])
            if not scores:
                continue
            mean_score = np.mean(scores)
            w = scenario_weights.get(sid, 1.0) if scenario_weights else 1.0
            weighted_sum += mean_score * w
            total_weight += w

        ranking[model] = weighted_sum / max(total_weight, 1e-9)

    return ranking


def get_domain_prefix(scenario_id: str) -> str:
    """Extract domain prefix from scenario_id."""
    return scenario_id.split("_")[0]


def prevalence_weights(scenarios: set[str]) -> dict[str, float]:
    """Assign published-prevalence weights to each scenario."""
    weights: dict[str, float] = {}
    for sid in scenarios:
        prefix = get_domain_prefix(sid)
        weights[sid] = PUBLISHED_PREVALENCE.get(prefix, 1.0)
    return weights


def bootstrap_resample(
    data: dict[str, dict[str, list[float]]],
    n_resamples: int,
    rng: np.random.Generator,
) -> list[dict[str, float]]:
    """Bootstrap re-sample scenarios and compute rankings."""
    all_scenarios = sorted(set().union(*(set(md.keys()) for md in data.values())))
    n = len(all_scenarios)
    rankings = []

    for _ in range(n_resamples):
        # Sample with replacement
        indices = rng.integers(0, n, size=n)
        sampled = [all_scenarios[i] for i in indices]

        # Count occurrences as weights
        weights: dict[str, float] = defaultdict(float)
        for sid in sampled:
            weights[sid] += 1.0

        ranking = compute_model_ranking(data, dict(weights))
        rankings.append(ranking)

    return rankings


def domain_subsample(
    data: dict[str, dict[str, list[float]]],
    n_resamples: int,
    fraction: float,
    rng: np.random.Generator,
) -> list[dict[str, float]]:
    """Sub-sample fraction of scenarios per domain, compute rankings."""
    # Group scenarios by domain
    all_scenarios = sorted(set().union(*(set(md.keys()) for md in data.values())))
    domain_groups: dict[str, list[str]] = defaultdict(list)
    for sid in all_scenarios:
        domain_groups[get_domain_prefix(sid)].append(sid)

    rankings = []
    for _ in range(n_resamples):
        selected: set[str] = set()
        for domain, sids in domain_groups.items():
            k = max(1, int(len(sids) * fraction))
            chosen = rng.choice(sids, size=k, replace=False)
            selected.update(chosen)

        weights = dict.fromkeys(selected, 1.0)
        ranking = compute_model_ranking(data, weights)
        rankings.append(ranking)

    return rankings


def ranking_stability(
    original: dict[str, float],
    resampled: list[dict[str, float]],
) -> dict[str, Any]:
    """Compute ranking stability metrics."""
    models = sorted(original.keys())
    orig_order = sorted(models, key=lambda m: original[m], reverse=True)
    orig_ranks = {m: i for i, m in enumerate(orig_order)}
    orig_rank_vec = [orig_ranks[m] for m in models]

    taus = []
    rank_changes: dict[str, list[int]] = {m: [] for m in models}
    top1_same = 0
    top3_same = 0

    for ranking in resampled:
        resamp_order = sorted(models, key=lambda m: ranking.get(m, 0), reverse=True)
        resamp_ranks = {m: i for i, m in enumerate(resamp_order)}
        resamp_rank_vec = [resamp_ranks[m] for m in models]

        tau, _p = stats.kendalltau(orig_rank_vec, resamp_rank_vec)
        taus.append(tau)

        if resamp_order[0] == orig_order[0]:
            top1_same += 1
        if set(resamp_order[:3]) == set(orig_order[:3]):
            top3_same += 1

        for m in models:
            rank_changes[m].append(resamp_ranks[m])

    n = len(resampled)
    return {
        "kendall_tau_mean": float(np.mean(taus)),
        "kendall_tau_std": float(np.std(taus)),
        "kendall_tau_ci95": [
            float(np.percentile(taus, 2.5)),
            float(np.percentile(taus, 97.5)),
        ],
        "top1_stability": top1_same / max(n, 1),
        "top3_stability": top3_same / max(n, 1),
        "original_ranking": orig_order,
        "rank_volatility": {
            m: {"mean": float(np.mean(rc)), "std": float(np.std(rc))} for m, rc in rank_changes.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="W9-3: Published-Cohort Re-sampling")
    parser.add_argument("--results-dir", default="results/full_706_v5")
    parser.add_argument("--n-resamples", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--output",
        default="evidence_pack/analysis/cohort_resample_results.json",
    )
    args = parser.parse_args()

    rng = np.random.default_rng(args.seed)

    print("Loading V6 episodes...")
    data = load_episodes(args.results_dir, CANONICAL_MODELS)
    if not data:
        print("ERROR: No data loaded")
        sys.exit(1)

    n_models = len(data)
    total_ep = sum(sum(len(v) for v in md.values()) for md in data.values())
    all_scenarios = sorted(set().union(*(set(md.keys()) for md in data.values())))
    print(f"\nLoaded {total_ep} episodes, {len(all_scenarios)} scenarios, {n_models} models")

    # --- Original (uniform) ranking ---
    print("\n1. Computing original (uniform) ranking...")
    original = compute_model_ranking(data)
    orig_order = sorted(original.keys(), key=lambda m: original[m], reverse=True)
    for i, m in enumerate(orig_order):
        print(f"   {i + 1}. {m:20s} CGA={original[m]:.4f}")

    # --- Published-prevalence weighted ranking ---
    print("\n2. Computing published-prevalence weighted ranking...")
    prev_weights = prevalence_weights(set(all_scenarios))
    prevalence_ranking = compute_model_ranking(data, prev_weights)
    prev_order = sorted(
        prevalence_ranking.keys(),
        key=lambda m: prevalence_ranking[m],
        reverse=True,
    )
    for i, m in enumerate(prev_order):
        print(f"   {i + 1}. {m:20s} CGA={prevalence_ranking[m]:.4f}")

    # Kendall τ: original vs prevalence-weighted
    models = sorted(original.keys())
    orig_vals = [original[m] for m in models]
    prev_vals = [prevalence_ranking[m] for m in models]
    tau_prev, p_prev = stats.kendalltau(orig_vals, prev_vals)
    print(f"   Kendall τ (uniform vs prevalence): {tau_prev:.4f} (p={p_prev:.4f})")

    # --- Bootstrap re-sampling ---
    print(f"\n3. Bootstrap re-sampling ({args.n_resamples} iterations)...")
    boot_rankings = bootstrap_resample(data, args.n_resamples, rng)
    boot_stats = ranking_stability(original, boot_rankings)
    print(f"   Kendall τ: {boot_stats['kendall_tau_mean']:.4f} ± {boot_stats['kendall_tau_std']:.4f}")
    print(f"   95% CI: [{boot_stats['kendall_tau_ci95'][0]:.4f}, {boot_stats['kendall_tau_ci95'][1]:.4f}]")
    print(f"   Top-1 stability: {boot_stats['top1_stability'] * 100:.1f}%")
    print(f"   Top-3 stability: {boot_stats['top3_stability'] * 100:.1f}%")

    # --- Domain sub-sampling (50%) ---
    print(f"\n4. Domain sub-sampling (50%, {args.n_resamples} iterations)...")
    subsample_rankings = domain_subsample(data, args.n_resamples, 0.5, rng)
    subsample_stats = ranking_stability(original, subsample_rankings)
    print(f"   Kendall τ: {subsample_stats['kendall_tau_mean']:.4f} ± {subsample_stats['kendall_tau_std']:.4f}")
    print(f"   95% CI: [{subsample_stats['kendall_tau_ci95'][0]:.4f}, {subsample_stats['kendall_tau_ci95'][1]:.4f}]")
    print(f"   Top-1 stability: {subsample_stats['top1_stability'] * 100:.1f}%")
    print(f"   Top-3 stability: {subsample_stats['top3_stability'] * 100:.1f}%")

    # --- Domain sub-sampling (25%) ---
    print(f"\n5. Aggressive sub-sampling (25%, {args.n_resamples} iterations)...")
    aggr_rankings = domain_subsample(data, args.n_resamples, 0.25, rng)
    aggr_stats = ranking_stability(original, aggr_rankings)
    print(f"   Kendall τ: {aggr_stats['kendall_tau_mean']:.4f} ± {aggr_stats['kendall_tau_std']:.4f}")
    print(f"   95% CI: [{aggr_stats['kendall_tau_ci95'][0]:.4f}, {aggr_stats['kendall_tau_ci95'][1]:.4f}]")
    print(f"   Top-1 stability: {aggr_stats['top1_stability'] * 100:.1f}%")
    print(f"   Top-3 stability: {aggr_stats['top3_stability'] * 100:.1f}%")

    # --- Save results ---
    results = {
        "n_models": n_models,
        "n_scenarios": len(all_scenarios),
        "n_episodes": total_ep,
        "n_resamples": args.n_resamples,
        "seed": args.seed,
        "original_ranking": {m: float(original[m]) for m in orig_order},
        "prevalence_weighted_ranking": {m: float(prevalence_ranking[m]) for m in prev_order},
        "prevalence_tau": float(tau_prev),
        "prevalence_p": float(p_prev),
        "bootstrap": boot_stats,
        "domain_subsample_50pct": subsample_stats,
        "domain_subsample_25pct": aggr_stats,
    }

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(results, indent=2))
    print(f"\nResults saved to {out_path}")

    # --- Generate LaTeX macros ---
    tex_path = Path("paper/auto_numbers_resample.tex")
    tex_lines = [
        "% Cohort re-sampling defense macros",
        f"% Auto-generated by {Path(__file__).name}",
        "",
        f"\\newcommand{{\\resampleNscenarios}}{{{len(all_scenarios)}}}",
        f"\\newcommand{{\\resampleNmodels}}{{{n_models}}}",
        f"\\newcommand{{\\resampleNboot}}{{{args.n_resamples}}}",
        f"\\newcommand{{\\resamplePrevTau}}{{{tau_prev:.3f}}}",
        f"\\newcommand{{\\resampleBootTau}}{{{boot_stats['kendall_tau_mean']:.3f}}}",
        f"\\newcommand{{\\resampleBootTauStd}}{{{boot_stats['kendall_tau_std']:.3f}}}",
        f"\\newcommand{{\\resampleBootTopOne}}{{{boot_stats['top1_stability'] * 100:.1f}}}",
        f"\\newcommand{{\\resampleBootTopThree}}{{{boot_stats['top3_stability'] * 100:.1f}}}",
        f"\\newcommand{{\\resampleSubFiftyTau}}{{{subsample_stats['kendall_tau_mean']:.3f}}}",
        f"\\newcommand{{\\resampleSubTwentyFiveTau}}{{{aggr_stats['kendall_tau_mean']:.3f}}}",
        f"\\newcommand{{\\resampleSubFiftyTopOne}}{{{subsample_stats['top1_stability'] * 100:.1f}}}",
        f"\\newcommand{{\\resampleSubTwentyFiveTopOne}}{{{aggr_stats['top1_stability'] * 100:.1f}}}",
    ]
    tex_path.write_text("\n".join(tex_lines) + "\n")
    print(f"LaTeX macros saved to {tex_path}")


if __name__ == "__main__":
    main()
