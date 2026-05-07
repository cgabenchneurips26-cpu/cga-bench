#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""EXP-E: Manual vs Auto Scenario Difficulty Equivalence.

Proves auto-generated scenarios are not systematically easier than manual
ones, using structural difficulty proxies and existing episode data.

Strategy: Episode results exist only for 15 manual scenarios (180 episodes).
Auto scenario episodes don't exist yet. We use:
  1. Structural difficulty proxy (no episodes needed)
  2. Model ordering stability on manual subset
  3. IRT-inspired Item-Total Correlation (manual baseline)
  4. Domain-stratified structural comparison
  5. Edge case coverage analysis

Outputs:
  evidence_pack/exp_e_difficulty_equivalence.json
  evidence_pack/exp_e_difficulty_equivalence.md
  evidence_pack/figures/exp_e_structural_difficulty.png
  evidence_pack/figures/exp_e_model_ordering.png
  evidence_pack/figures/exp_e_difficulty_distribution.png
  evidence_pack/figures/exp_e_domain_stratified.png
  evidence_pack/tables/difficulty_equivalence.tex
  evidence_pack/tables/model_ordering.tex

Usage:
    PYTHONPATH=. python scripts/experiments/exp_e_difficulty_equivalence.py
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
import matplotlib
from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    RESULTS_DIR,
    TABLES_DIR,
    bootstrap_ci,
    domain_from_scenario,
    fmt_p,
    load_all_scenarios,
    resolve_graph_path,
    save_figure,
    save_json,
    save_latex_table,
    save_markdown,
    setup_matplotlib,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt

MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]
MODEL_LABELS = {"oss120b": "120B", "qwen27b": "27B", "qwen35b": "35B", "qwen4b": "4B"}

# Structural difficulty weights
W_FORBIDDEN = 1.5
W_BEFORE = 1.2
W_WITHIN = 1.0
W_REQUIRED = 0.8
W_EXPECTED = 0.3


# ============================================================
# Data loading
# ============================================================


def load_episode_results() -> list[dict[str, Any]]:
    """Load all episode JSON results from clean_slate_rescored."""
    episodes: list[dict[str, Any]] = []
    for model_dir in sorted(RESULTS_DIR.iterdir()):
        if not model_dir.is_dir():
            continue
        model = model_dir.name
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                with open(ep_file) as f:
                    data = json.load(f)
                data["_model"] = model
                episodes.append(data)
            except (OSError, json.JSONDecodeError):
                continue
    return episodes


def compute_structural_difficulty(scenario: dict[str, Any]) -> float:
    """Compute weighted structural difficulty score for a scenario.

    Higher = harder. Weights reflect clinical impact:
    FORBIDDEN(1.5) > BEFORE(1.2) > WITHIN(1.0) > REQUIRED(0.8) > EXPECTED(0.3)
    """
    n_forbidden = len(scenario.get("forbidden_actions", []))
    n_expected = len(scenario.get("expected_actions", []))

    # For manual scenarios without explicit fields, try derivation
    # But here we use pre-computed fields from YAML
    difficulty = (
        n_forbidden * W_FORBIDDEN
        + n_expected * W_EXPECTED
    )

    # Add complexity from trap scenario flag
    if scenario.get("trap_scenario", False):
        difficulty += 2.0

    # Add complexity from triggered rules
    n_triggered = len(scenario.get("triggered_rules", []))
    difficulty += n_triggered * 0.5

    return difficulty


def enrich_with_derivation(
    scenarios: list[dict[str, Any]],
    engine: ConstraintDerivationEngine,
) -> list[dict[str, Any]]:
    """Add derivation-based difficulty metrics to scenarios.

    For scenarios without expected/forbidden fields, derive them.
    """
    graph_cache: dict[str, Any] = {}

    for sc in scenarios:
        gid = sc.get("guideline_graph", "")
        if gid not in graph_cache:
            gp = resolve_graph_path(gid)
            if gp:
                graph_cache[gid] = load_graph(gp)
            else:
                graph_cache[gid] = None

        graph = graph_cache[gid]
        if graph is None:
            sc["_n_derived_forbidden"] = 0
            sc["_n_derived_expected"] = 0
            sc["_n_derived_before"] = 0
            sc["_n_derived_within"] = 0
            sc["_n_derived_required"] = 0
            continue

        patient = sc.get("patient", {})
        if not patient:
            sc["_n_derived_forbidden"] = 0
            sc["_n_derived_expected"] = 0
            sc["_n_derived_before"] = 0
            sc["_n_derived_within"] = 0
            sc["_n_derived_required"] = 0
            continue

        try:
            derived = engine.derive(graph, patient, sc.get("scenario_id", ""))
            sc["_n_derived_forbidden"] = len(derived.forbidden)
            sc["_n_derived_expected"] = len(derived.expected)
            sc["_n_derived_before"] = len(derived.before)
            sc["_n_derived_within"] = len(derived.within)
            sc["_n_derived_required"] = len(derived.required)
        except Exception:
            sc["_n_derived_forbidden"] = 0
            sc["_n_derived_expected"] = 0
            sc["_n_derived_before"] = 0
            sc["_n_derived_within"] = 0
            sc["_n_derived_required"] = 0

    return scenarios


def compute_derived_difficulty(scenario: dict[str, Any]) -> float:
    """Compute difficulty from derivation-based constraint counts."""
    return (
        scenario.get("_n_derived_forbidden", 0) * W_FORBIDDEN
        + scenario.get("_n_derived_before", 0) * W_BEFORE
        + scenario.get("_n_derived_within", 0) * W_WITHIN
        + scenario.get("_n_derived_required", 0) * W_REQUIRED
        + scenario.get("_n_derived_expected", 0) * W_EXPECTED
    )


# ============================================================
# Analysis 1: Structural difficulty comparison
# ============================================================


def analyze_structural_difficulty(
    manual: list[dict[str, Any]],
    auto: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare structural difficulty distributions."""
    print("\n--- Analysis 1: Structural Difficulty ---")

    m_diff = np.array([compute_derived_difficulty(s) for s in manual])
    a_diff = np.array([compute_derived_difficulty(s) for s in auto])

    u_stat, u_p = stats.mannwhitneyu(m_diff, a_diff, alternative="two-sided")
    ks_stat, ks_p = stats.ks_2samp(m_diff, a_diff)

    pooled_std = np.sqrt((np.var(m_diff) + np.var(a_diff)) / 2)
    cohens_d = (np.mean(m_diff) - np.mean(a_diff)) / pooled_std if pooled_std > 0 else 0

    m_ci = bootstrap_ci(m_diff, np.mean)
    a_ci = bootstrap_ci(a_diff, np.mean)

    print(f"  Manual: mean={np.mean(m_diff):.2f} ± {np.std(m_diff):.2f}")
    print(f"  Auto:   mean={np.mean(a_diff):.2f} ± {np.std(a_diff):.2f}")
    print(f"  Mann-Whitney U: p={u_p:.4f}")
    print(f"  KS test: p={ks_p:.4f}")
    print(f"  Cohen's d: {cohens_d:.3f}")

    return {
        "manual_mean": round(float(np.mean(m_diff)), 3),
        "manual_std": round(float(np.std(m_diff)), 3),
        "manual_ci": [round(x, 3) for x in m_ci],
        "auto_mean": round(float(np.mean(a_diff)), 3),
        "auto_std": round(float(np.std(a_diff)), 3),
        "auto_ci": [round(x, 3) for x in a_ci],
        "mannwhitney_U": round(float(u_stat), 2),
        "mannwhitney_p": round(float(u_p), 6),
        "ks_statistic": round(float(ks_stat), 4),
        "ks_p": round(float(ks_p), 6),
        "cohens_d": round(float(cohens_d), 4),
        "n_manual": len(m_diff),
        "n_auto": len(a_diff),
    }


# ============================================================
# Analysis 2: Model ordering stability
# ============================================================


def analyze_model_ordering(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute model rankings from episodes, verify stability."""
    print("\n--- Analysis 2: Model Ordering ---")

    # Per-model compliance scores
    model_scores: dict[str, list[float]] = defaultdict(list)
    for ep in episodes:
        model = ep.get("_model", "")
        score = ep.get("new_compliance_score", 0)
        model_scores[model].append(score)

    # Overall ranking
    model_means = {m: float(np.mean(scores)) for m, scores in model_scores.items()}
    ranked = sorted(model_means.items(), key=lambda x: -x[1])
    ranking = {m: i + 1 for i, (m, _) in enumerate(ranked)}

    print(f"  Model rankings: {ranking}")

    # Leave-one-domain-out stability
    scenario_models: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for ep in episodes:
        sid = ep.get("scenario_id", "")
        model = ep.get("_model", "")
        scenario_models[sid][model].append(ep.get("new_compliance_score", 0))

    domains = list(scenario_models.keys())
    loo_rankings: list[dict[str, int]] = []

    for exclude_domain in domains:
        subset_scores: dict[str, list[float]] = defaultdict(list)
        for sid, model_data in scenario_models.items():
            if sid == exclude_domain:
                continue
            for model, scores in model_data.items():
                subset_scores[model].extend(scores)

        if not subset_scores:
            continue

        subset_means = {m: float(np.mean(s)) for m, s in subset_scores.items()}
        subset_ranked = sorted(subset_means.items(), key=lambda x: -x[1])
        loo_rank = {m: i + 1 for i, (m, _) in enumerate(subset_ranked)}
        loo_rankings.append(loo_rank)

    # Compute rank stability (fraction of LOO trials preserving original order)
    n_preserved = 0
    for loo_rank in loo_rankings:
        if loo_rank == ranking:
            n_preserved += 1
    stability = n_preserved / max(len(loo_rankings), 1)

    # Spearman rho between full and each LOO ranking
    rhos = []
    for loo_rank in loo_rankings:
        common = sorted(set(ranking.keys()) & set(loo_rank.keys()))
        if len(common) < 3:
            continue
        r1 = [ranking[m] for m in common]
        r2 = [loo_rank[m] for m in common]
        rho, _ = stats.spearmanr(r1, r2)
        rhos.append(rho)

    avg_rho = float(np.mean(rhos)) if rhos else 0.0

    print(f"  Stability (exact match): {stability:.2f}")
    print(f"  Avg Spearman rho (LOO): {avg_rho:.3f}")

    return {
        "overall_ranking": ranking,
        "model_means": {m: round(v, 4) for m, v in model_means.items()},
        "loo_exact_stability": round(stability, 3),
        "loo_avg_spearman": round(avg_rho, 4),
        "loo_spearman_values": [round(r, 4) for r in rhos],
        "n_loo_trials": len(loo_rankings),
    }


# ============================================================
# Analysis 3: IRT-inspired Item-Total Correlation
# ============================================================


def analyze_itc(episodes: list[dict[str, Any]]) -> dict[str, Any]:
    """Item-Total Correlation for each scenario.

    Measures how well each scenario discriminates between models.
    """
    print("\n--- Analysis 3: Item-Total Correlation ---")

    # Build scenario x model pass matrix
    # Using compliance_score > median as "pass"
    all_scores = [ep.get("new_compliance_score", 0) for ep in episodes]
    threshold = float(np.median(all_scores))

    # Group by (model, scenario) -> avg score
    model_scenario_scores: dict[tuple[str, str], list[float]] = defaultdict(list)
    for ep in episodes:
        key = (ep["_model"], ep.get("scenario_id", ""))
        model_scenario_scores[key].append(ep.get("new_compliance_score", 0))

    # Get unique scenarios and models
    scenarios_set = sorted({k[1] for k in model_scenario_scores})
    models_set = sorted({k[0] for k in model_scenario_scores})

    # Build binary pass matrix: models x scenarios
    n_models = len(models_set)
    n_scenarios = len(scenarios_set)

    if n_models < 2 or n_scenarios < 2:
        return {"n_scenarios": n_scenarios, "n_models": n_models, "itc_values": {}}

    pass_matrix = np.zeros((n_models, n_scenarios))
    for i, model in enumerate(models_set):
        for j, scenario in enumerate(scenarios_set):
            key = (model, scenario)
            if key in model_scenario_scores:
                avg = float(np.mean(model_scenario_scores[key]))
                pass_matrix[i, j] = 1 if avg > threshold else 0

    # Item-Total Correlation for each scenario
    total_scores = pass_matrix.sum(axis=1)
    itc_values: dict[str, float] = {}

    for j, scenario in enumerate(scenarios_set):
        item = pass_matrix[:, j]
        rest_total = total_scores - item
        if np.std(item) == 0 or np.std(rest_total) == 0:
            itc_values[scenario] = 0.0
            continue
        r, _ = stats.pearsonr(item, rest_total)
        itc_values[scenario] = round(float(r), 4)

    avg_itc = float(np.mean(list(itc_values.values())))
    high_disc = [s for s, v in itc_values.items() if v > 0.3]
    low_disc = [s for s, v in itc_values.items() if v < 0.0]

    print(f"  Avg ITC: {avg_itc:.3f}")
    print(f"  High discriminators (ITC>0.3): {len(high_disc)}")
    print(f"  Low discriminators (ITC<0): {len(low_disc)}")

    return {
        "threshold": round(threshold, 4),
        "n_scenarios": n_scenarios,
        "n_models": n_models,
        "avg_itc": round(avg_itc, 4),
        "itc_values": itc_values,
        "high_discriminators": high_disc,
        "low_discriminators": low_disc,
    }


# ============================================================
# Analysis 4: Domain-stratified comparison
# ============================================================


def analyze_domain_stratified(
    manual: list[dict[str, Any]],
    auto: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare constraint density per domain for manual vs auto."""
    print("\n--- Analysis 4: Domain-Stratified ---")

    manual_by_domain: dict[str, list[float]] = defaultdict(list)
    auto_by_domain: dict[str, list[float]] = defaultdict(list)

    for sc in manual:
        domain = domain_from_scenario(sc)
        diff = compute_derived_difficulty(sc)
        manual_by_domain[domain].append(diff)

    for sc in auto:
        domain = domain_from_scenario(sc)
        diff = compute_derived_difficulty(sc)
        auto_by_domain[domain].append(diff)

    # Only domains with both manual and auto
    common_domains = sorted(set(manual_by_domain) & set(auto_by_domain))

    per_domain: list[dict[str, Any]] = []
    for domain in common_domains:
        m_vals = np.array(manual_by_domain[domain])
        a_vals = np.array(auto_by_domain[domain])

        if len(m_vals) < 2 or len(a_vals) < 2:
            per_domain.append({
                "domain": domain,
                "manual_n": len(m_vals),
                "auto_n": len(a_vals),
                "manual_mean": round(float(np.mean(m_vals)), 2),
                "auto_mean": round(float(np.mean(a_vals)), 2),
                "p_value": None,
            })
            continue

        u, p = stats.mannwhitneyu(m_vals, a_vals, alternative="two-sided")

        per_domain.append({
            "domain": domain,
            "manual_n": len(m_vals),
            "auto_n": len(a_vals),
            "manual_mean": round(float(np.mean(m_vals)), 2),
            "auto_mean": round(float(np.mean(a_vals)), 2),
            "p_value": round(float(p), 4),
            "U_statistic": round(float(u), 2),
        })

    print(f"  Common domains: {len(common_domains)}")
    return {
        "n_common_domains": len(common_domains),
        "per_domain": per_domain,
    }


# ============================================================
# Analysis 5: Edge case coverage
# ============================================================


def analyze_edge_cases(
    manual: list[dict[str, Any]],
    auto: list[dict[str, Any]],
    episodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Identify difficulty gaps between manual and auto."""
    print("\n--- Analysis 5: Edge Case Coverage ---")

    m_diff = [compute_derived_difficulty(s) for s in manual]
    a_diff = [compute_derived_difficulty(s) for s in auto]

    m_range = (min(m_diff) if m_diff else 0, max(m_diff) if m_diff else 0)
    a_range = (min(a_diff) if a_diff else 0, max(a_diff) if a_diff else 0)

    # Hardest/easiest items from episodes
    scenario_scores: dict[str, list[float]] = defaultdict(list)
    for ep in episodes:
        sid = ep.get("scenario_id", "")
        scenario_scores[sid].append(ep.get("new_compliance_score", 0))

    scenario_means = {
        sid: float(np.mean(scores)) for sid, scores in scenario_scores.items()
    }

    # All-fail: lowest mean scores
    hardest = sorted(scenario_means.items(), key=lambda x: x[1])[:5]
    # All-pass: highest mean scores
    easiest = sorted(scenario_means.items(), key=lambda x: -x[1])[:5]

    # Manual difficulty coverage range
    manual_covers = (min(m_diff) if m_diff else 0, max(m_diff) if m_diff else 0)

    gaps = {
        "auto_below_manual_min": sum(1 for d in a_diff if d < manual_covers[0]),
        "auto_above_manual_max": sum(1 for d in a_diff if d > manual_covers[1]),
    }

    print(f"  Manual range: [{m_range[0]:.1f}, {m_range[1]:.1f}]")
    print(f"  Auto range: [{a_range[0]:.1f}, {a_range[1]:.1f}]")
    print(f"  Auto below manual min: {gaps['auto_below_manual_min']}")
    print(f"  Auto above manual max: {gaps['auto_above_manual_max']}")

    return {
        "manual_range": [round(x, 2) for x in m_range],
        "auto_range": [round(x, 2) for x in a_range],
        "hardest_episodes": [{"scenario_id": s, "mean_score": round(v, 3)} for s, v in hardest],
        "easiest_episodes": [{"scenario_id": s, "mean_score": round(v, 3)} for s, v in easiest],
        "difficulty_gaps": gaps,
    }


# ============================================================
# Figures
# ============================================================


def plot_structural_difficulty(results: dict[str, Any]) -> plt.Figure:
    """Histogram of structural difficulty: manual vs auto."""
    fig, ax = plt.subplots(figsize=(8, 5))

    # Recreate from summary stats (we'll pass raw arrays through)
    ax.set_xlabel("Structural Difficulty Score")
    ax.set_ylabel("Frequency")
    ax.set_title("Manual vs Auto Structural Difficulty Distribution")

    sd = results["structural_difficulty"]
    ax.text(0.02, 0.95,
            f"Manual: {sd['manual_mean']:.2f}±{sd['manual_std']:.2f} (n={sd['n_manual']})\n"
            f"Auto: {sd['auto_mean']:.2f}±{sd['auto_std']:.2f} (n={sd['n_auto']})\n"
            f"KS p={fmt_p(sd['ks_p'])}, d={sd['cohens_d']:.3f}",
            transform=ax.transAxes, fontsize=10, va="top",
            bbox={"boxstyle": "round", "facecolor": "wheat", "alpha": 0.5})

    return fig


def plot_structural_difficulty_with_data(
    manual_diffs: np.ndarray,
    auto_diffs: np.ndarray,
    results: dict[str, Any],
) -> plt.Figure:
    """Histogram with actual data arrays."""
    fig, ax = plt.subplots(figsize=(8, 5))

    bins = np.linspace(0, max(manual_diffs.max(), auto_diffs.max()) + 1, 30)
    ax.hist(manual_diffs, bins=bins, alpha=0.6, label=f"Manual (n={len(manual_diffs)})",
            color="steelblue", edgecolor="black", linewidth=0.5)
    ax.hist(auto_diffs, bins=bins, alpha=0.6, label=f"Auto (n={len(auto_diffs)})",
            color="coral", edgecolor="black", linewidth=0.5)

    ax.set_xlabel("Structural Difficulty Score")
    ax.set_ylabel("Frequency")
    ax.set_title("Manual vs Auto Structural Difficulty Distribution")
    ax.legend()

    sd = results["structural_difficulty"]
    ax.text(0.02, 0.95,
            f"Mann-Whitney p={fmt_p(sd['mannwhitney_p'])}\n"
            f"KS p={fmt_p(sd['ks_p'])}\n"
            f"Cohen's d={sd['cohens_d']:.3f}",
            transform=ax.transAxes, fontsize=9, va="top",
            bbox={"boxstyle": "round", "facecolor": "wheat", "alpha": 0.5})

    return fig


def plot_model_ordering(results: dict[str, Any]) -> plt.Figure:
    """Model ranking visualization."""
    mo = results["model_ordering"]
    ranking = mo["overall_ranking"]
    means = mo["model_means"]

    fig, ax = plt.subplots(figsize=(8, 5))

    models = sorted(ranking.keys(), key=lambda m: ranking[m])
    y = [means.get(m, 0) for m in models]
    colors = ["#2ecc71", "#3498db", "#f39c12", "#e74c3c"]

    bars = ax.barh(range(len(models)), y, color=colors[:len(models)],
                   edgecolor="black", linewidth=0.5)
    ax.set_yticks(range(len(models)))
    ax.set_yticklabels([f"#{ranking[m]} {MODEL_LABELS.get(m, m)}" for m in models])
    ax.set_xlabel("Mean Compliance Score")
    ax.set_title(f"Model Ordering (LOO rho={mo['loo_avg_spearman']:.3f})")

    for bar, val in zip(bars, y):
        ax.text(val + 0.005, bar.get_y() + bar.get_height() / 2,
                f"{val:.4f}", va="center", fontsize=9)

    fig.tight_layout()
    return fig


def plot_difficulty_distribution(results: dict[str, Any]) -> plt.Figure:
    """ITC values for scenarios."""
    itc = results["itc_analysis"]
    values = itc.get("itc_values", {})

    if not values:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.text(0.5, 0.5, "No ITC data", ha="center", va="center")
        return fig

    fig, ax = plt.subplots(figsize=(10, 5))

    scenarios = sorted(values.keys())
    itc_vals = [values[s] for s in scenarios]
    colors = ["#2ecc71" if v > 0.3 else "#e74c3c" if v < 0 else "#f39c12"
              for v in itc_vals]

    ax.bar(range(len(scenarios)), itc_vals, color=colors, edgecolor="black", linewidth=0.3)
    ax.set_xticks(range(len(scenarios)))
    ax.set_xticklabels([s[:15] for s in scenarios], rotation=45, ha="right", fontsize=7)
    ax.axhline(y=0.3, color="green", linestyle="--", alpha=0.5, label="Good discrimination")
    ax.axhline(y=0, color="red", linestyle="--", alpha=0.5, label="No discrimination")
    ax.set_ylabel("Item-Total Correlation")
    ax.set_title(f"Scenario Discrimination (Avg ITC={itc['avg_itc']:.3f})")
    ax.legend()

    fig.tight_layout()
    return fig


def plot_domain_stratified(results: dict[str, Any]) -> plt.Figure:
    """Forest plot of domain-level difficulty differences."""
    ds = results["domain_stratified"]
    per_domain = ds.get("per_domain", [])

    if not per_domain:
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.text(0.5, 0.5, "No domain data", ha="center", va="center")
        return fig

    fig, ax = plt.subplots(figsize=(10, max(4, len(per_domain) * 0.5)))

    domains = [d["domain"] for d in per_domain]
    manual_means = [d["manual_mean"] for d in per_domain]
    auto_means = [d["auto_mean"] for d in per_domain]

    y = range(len(domains))
    ax.barh([i - 0.15 for i in y], manual_means, 0.3, label="Manual",
            color="steelblue", edgecolor="black", linewidth=0.5)
    ax.barh([i + 0.15 for i in y], auto_means, 0.3, label="Auto",
            color="coral", edgecolor="black", linewidth=0.5)

    ax.set_yticks(list(y))
    ax.set_yticklabels(domains, fontsize=9)
    ax.set_xlabel("Mean Structural Difficulty")
    ax.set_title("Domain-Stratified Difficulty Comparison")
    ax.legend()

    # Annotate p-values
    for i, d in enumerate(per_domain):
        p = d.get("p_value")
        if p is not None:
            sig = "*" if p < 0.05 else ""
            ax.text(max(d["manual_mean"], d["auto_mean"]) + 0.5, i,
                    f"p={fmt_p(p)}{sig}", fontsize=8, va="center")

    fig.tight_layout()
    return fig


# ============================================================
# Report
# ============================================================


def generate_markdown(results: dict[str, Any]) -> str:
    """Generate markdown report."""
    sd = results["structural_difficulty"]
    mo = results["model_ordering"]
    itc = results["itc_analysis"]
    ds = results["domain_stratified"]
    ec = results["edge_cases"]

    lines = [
        "# EXP-E: Manual vs Auto Difficulty Equivalence",
        "",
        f"**Manual scenarios**: {sd['n_manual']}",
        f"**Auto scenarios**: {sd['n_auto']}",
        f"**Episodes**: {results['summary']['n_episodes']}",
        "",
        "## 1. Structural Difficulty Comparison",
        "",
        f"- Manual: {sd['manual_mean']:.3f} ± {sd['manual_std']:.3f} "
        f"(95% CI: [{sd['manual_ci'][0]:.3f}, {sd['manual_ci'][1]:.3f}])",
        f"- Auto: {sd['auto_mean']:.3f} ± {sd['auto_std']:.3f} "
        f"(95% CI: [{sd['auto_ci'][0]:.3f}, {sd['auto_ci'][1]:.3f}])",
        f"- Mann-Whitney U: p={fmt_p(sd['mannwhitney_p'])}",
        f"- KS test: p={fmt_p(sd['ks_p'])}",
        f"- Cohen's d: {sd['cohens_d']:.4f}",
        "",
        "## 2. Model Ordering Stability",
        "",
        f"- Overall ranking: {mo['overall_ranking']}",
        f"- LOO exact stability: {mo['loo_exact_stability']:.3f}",
        f"- LOO avg Spearman rho: {mo['loo_avg_spearman']:.4f}",
        "",
        "## 3. Item-Total Correlation (Manual Baseline)",
        "",
        f"- Avg ITC: {itc['avg_itc']:.4f}",
        f"- High discriminators (ITC>0.3): {len(itc.get('high_discriminators', []))}",
        f"- Low discriminators (ITC<0): {len(itc.get('low_discriminators', []))}",
        "",
        "## 4. Domain-Stratified Comparison",
        "",
        f"- Common domains: {ds['n_common_domains']}",
        "",
        "| Domain | Manual Mean | Auto Mean | p-value |",
        "|--------|------------|-----------|---------|",
    ]

    for d in ds.get("per_domain", []):
        p_str = fmt_p(d["p_value"]) if d.get("p_value") is not None else "N/A"
        lines.append(
            f"| {d['domain']} | {d['manual_mean']:.2f} | {d['auto_mean']:.2f} | {p_str} |"
        )

    lines += [
        "",
        "## 5. Edge Case Coverage",
        "",
        f"- Manual range: [{ec['manual_range'][0]}, {ec['manual_range'][1]}]",
        f"- Auto range: [{ec['auto_range'][0]}, {ec['auto_range'][1]}]",
        f"- Auto below manual min: {ec['difficulty_gaps']['auto_below_manual_min']}",
        f"- Auto above manual max: {ec['difficulty_gaps']['auto_above_manual_max']}",
    ]

    return "\n".join(lines) + "\n"


def generate_latex(results: dict[str, Any]) -> None:
    """Generate LaTeX tables."""
    sd = results["structural_difficulty"]
    rows = [
        [
            "Structural difficulty",
            f"{sd['manual_mean']:.2f} $\\pm$ {sd['manual_std']:.2f}",
            f"{sd['auto_mean']:.2f} $\\pm$ {sd['auto_std']:.2f}",
            fmt_p(sd["mannwhitney_p"]),
            f"{sd['cohens_d']:.3f}",
        ],
    ]
    save_latex_table(
        rows,
        ["Metric", "Manual", "Auto", "p-value", "Effect Size"],
        TABLES_DIR / "difficulty_equivalence.tex",
        caption="Manual vs auto scenario difficulty equivalence.",
        label="tab:difficulty",
    )

    mo = results["model_ordering"]
    mo_rows = []
    for model in sorted(mo["overall_ranking"], key=lambda m: mo["overall_ranking"][m]):
        mo_rows.append([
            MODEL_LABELS.get(model, model),
            str(mo["overall_ranking"][model]),
            f"{mo['model_means'].get(model, 0):.4f}",
        ])
    save_latex_table(
        mo_rows,
        ["Model", "Rank", "Mean Score"],
        TABLES_DIR / "model_ordering.tex",
        caption="Model ordering from manual scenarios.",
        label="tab:model-ordering",
    )


# ============================================================
# Main
# ============================================================


def main() -> None:
    """Run EXP-E difficulty equivalence analysis."""
    setup_matplotlib()

    print("EXP-E: Manual vs Auto Difficulty Equivalence")
    print("=" * 60)

    # Load scenarios
    engine = ConstraintDerivationEngine()
    scenarios = load_all_scenarios(tag_source=True)

    manual = [s for s in scenarios if s.get("source_type") == "manual"]
    auto = [s for s in scenarios if s.get("source_type") == "auto"]
    print(f"Loaded {len(manual)} manual, {len(auto)} auto scenarios")

    # Enrich with derivation data
    print("Enriching scenarios with derivation data...")
    manual = enrich_with_derivation(manual, engine)
    auto = enrich_with_derivation(auto, engine)

    # Load episodes
    episodes = load_episode_results()
    print(f"Loaded {len(episodes)} episodes")

    results: dict[str, Any] = {}

    # Analysis 1: Structural difficulty
    results["structural_difficulty"] = analyze_structural_difficulty(manual, auto)

    # Analysis 2: Model ordering
    results["model_ordering"] = analyze_model_ordering(episodes)

    # Analysis 3: ITC
    results["itc_analysis"] = analyze_itc(episodes)

    # Analysis 4: Domain-stratified
    results["domain_stratified"] = analyze_domain_stratified(manual, auto)

    # Analysis 5: Edge cases
    results["edge_cases"] = analyze_edge_cases(manual, auto, episodes)

    results["summary"] = {
        "n_manual": len(manual),
        "n_auto": len(auto),
        "n_episodes": len(episodes),
    }

    # Save outputs
    save_json(results, EVIDENCE_DIR / "exp_e_difficulty_equivalence.json")
    save_markdown(generate_markdown(results), EVIDENCE_DIR / "exp_e_difficulty_equivalence.md")
    generate_latex(results)

    # Figures
    m_diffs = np.array([compute_derived_difficulty(s) for s in manual])
    a_diffs = np.array([compute_derived_difficulty(s) for s in auto])

    fig1 = plot_structural_difficulty_with_data(m_diffs, a_diffs, results)
    save_figure(fig1, FIGURES_DIR / "exp_e_structural_difficulty.png")

    fig2 = plot_model_ordering(results)
    save_figure(fig2, FIGURES_DIR / "exp_e_model_ordering.png")

    fig3 = plot_difficulty_distribution(results)
    save_figure(fig3, FIGURES_DIR / "exp_e_difficulty_distribution.png")

    fig4 = plot_domain_stratified(results)
    save_figure(fig4, FIGURES_DIR / "exp_e_domain_stratified.png")

    print("\nEXP-E complete.")


if __name__ == "__main__":
    main()
