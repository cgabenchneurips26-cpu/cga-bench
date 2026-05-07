#!/usr/bin/env python3
"""Bootstrap confidence intervals and required-sample-size simulation for CGA-Bench.

Produces:
  - evidence_pack/analysis/bootstrap_confidence_intervals.json
  - evidence_pack/analysis/required_sample_size.json
  - evidence_pack/tables/main_results_with_ci.tex
  - evidence_pack/figures/sample_size_vs_power.pdf

Usage:
  PYTHONPATH=. python scripts/experiments/bootstrap_ci.py
"""
from __future__ import annotations

from itertools import combinations
import json
from pathlib import Path

import numpy as np
from scipy import stats

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
BASE_DIR = Path(__file__).resolve().parents[2]  # cga_bench/
RESULTS_DIR = BASE_DIR / "results"
COMPOSITE_PATH = BASE_DIR / "evidence_pack" / "analysis" / "composite_metric.json"

OUT_CI = BASE_DIR / "evidence_pack" / "analysis" / "bootstrap_confidence_intervals.json"
OUT_SS = BASE_DIR / "evidence_pack" / "analysis" / "required_sample_size.json"
OUT_TEX = BASE_DIR / "evidence_pack" / "tables" / "main_results_with_ci.tex"
OUT_FIG = BASE_DIR / "evidence_pack" / "figures" / "sample_size_vs_power.pdf"

MODEL_DIRS: dict[str, str] = {
    "oss-120b": "eval_science_rag_oss120b",
    "Qwen3.5-35B": "eval_science_rag_qwen35",
    "oss-20b": "eval_science_rag_oss20b",
    "Qwen3-4B": "eval_science_rag_qwen3_4b",
}

N_BOOTSTRAP = 10_000
N_POWER_SIM = 10_000
ALPHA = 0.05
COMPOSITE_K = 2.0
RNG_SEED = 42

SAMPLE_SIZES = [10, 15, 20, 25, 30, 40, 50]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_composite_meta() -> tuple[list[str], dict[str, int]]:
    """Load the 15 target scenarios and their expected-action counts.

    Returns:
        Tuple of (scenario list, {scenario: expected_actions}).
    """
    with open(COMPOSITE_PATH) as fh:
        data = json.load(fh)
    per_scenario = data["per_scenario"]
    scenarios = list(per_scenario.keys())
    exp_actions: dict[str, int] = {}
    for sc in scenarios:
        # grab exp_actions from first model that has it
        for model_data in per_scenario[sc].values():
            if "exp_actions" in model_data:
                exp_actions[sc] = int(model_data["exp_actions"])
                break
    return scenarios, exp_actions


def _load_episodes_from_dir(directory: Path) -> list[dict]:
    """Load all episode JSON files from a directory."""
    episodes: list[dict] = []
    if not directory.is_dir():
        return episodes
    for fp in sorted(directory.glob("*.json")):
        if fp.name.startswith("eval_science_"):
            continue  # skip summary files
        try:
            with open(fp) as fh:
                ep = json.load(fh)
            ep["_filename"] = fp.name
            episodes.append(ep)
        except (json.JSONDecodeError, OSError):
            continue
    return episodes


def load_all_episodes(
    scenarios: list[str],
) -> dict[str, dict[str, list[dict]]]:
    """Load episodes grouped by model -> scenario -> list[episode].

    For oss-120b: baseline=run0, patch_S=run1, patch_T=run2.
    For others: sort by filename timestamp, take first 3 per scenario.

    Returns:
        {model_name: {scenario_id: [ep0, ep1, ep2]}}
    """
    result: dict[str, dict[str, list[dict]]] = {}
    scenario_set = set(scenarios)

    for model_name, dir_name in MODEL_DIRS.items():
        model_base = RESULTS_DIR / dir_name
        model_episodes: dict[str, list[dict]] = {sc: [] for sc in scenarios}

        if model_name == "oss-120b":
            # 3 runs from 3 subdirectories
            for run_idx, sub in enumerate(["baseline", "patch_S", "patch_T"]):
                for ep in _load_episodes_from_dir(model_base / sub):
                    sc = ep.get("scenario_id", "")
                    if sc in scenario_set:
                        ep["_run"] = run_idx
                        model_episodes[sc].append(ep)
            # keep first per run per scenario
            for sc in scenarios:
                seen_runs: dict[int, dict] = {}
                for ep in model_episodes[sc]:
                    r = ep["_run"]
                    if r not in seen_runs:
                        seen_runs[r] = ep
                model_episodes[sc] = [
                    seen_runs[r] for r in sorted(seen_runs.keys())
                ][:3]
        else:
            # single baseline directory, sort by filename, take first 3
            all_eps = _load_episodes_from_dir(model_base / "baseline")
            by_scenario: dict[str, list[dict]] = {sc: [] for sc in scenarios}
            for ep in all_eps:
                sc = ep.get("scenario_id", "")
                if sc in scenario_set:
                    by_scenario[sc].append(ep)
            for sc in scenarios:
                # already sorted by filename (contains timestamp)
                model_episodes[sc] = by_scenario[sc][:3]

        result[model_name] = model_episodes

    return result


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------
def compute_episode_metrics(
    ep: dict, exp_actions: int
) -> dict[str, float]:
    """Compute per-episode metrics.

    Args:
        ep: Episode dict with compliance_score, actions_count.
        exp_actions: Number of expected actions for the scenario.

    Returns:
        Dict with cga, coverage, composite_a, efficiency.
    """
    cga = float(ep.get("compliance_score", 0.0))
    acts = int(ep.get("actions_count", 1))
    acts = max(acts, 1)  # avoid division by zero

    coverage = acts / max(exp_actions, 1)
    capped_cov = min(coverage, 1.0)
    efficiency = exp_actions / acts if acts > 0 else 0.0
    efficiency = min(efficiency, 1.0)

    # Composite A = harmonic mean of CGA and capped_coverage, k=2.0
    if cga + COMPOSITE_K * capped_cov > 0:
        composite_a = (
            (1 + COMPOSITE_K) * cga * capped_cov
            / (cga + COMPOSITE_K * capped_cov)
        )
    else:
        composite_a = 0.0

    return {
        "cga": cga,
        "coverage": capped_cov,
        "composite_a": composite_a,
        "efficiency": efficiency,
    }


def build_scenario_level_data(
    all_episodes: dict[str, dict[str, list[dict]]],
    scenarios: list[str],
    exp_actions: dict[str, int],
) -> dict[str, dict[str, np.ndarray]]:
    """Build scenario-level averaged metrics per model.

    For each model and scenario, average the (up to 3) run-level metrics.

    Returns:
        {model: {metric: np.array of length len(scenarios)}}
    """
    metrics = ["cga", "coverage", "composite_a", "efficiency"]
    result: dict[str, dict[str, np.ndarray]] = {}

    for model_name in MODEL_DIRS:
        arrays: dict[str, list[float]] = {m: [] for m in metrics}
        for sc in scenarios:
            eps = all_episodes[model_name].get(sc, [])
            if not eps:
                for m in metrics:
                    arrays[m].append(0.0)
                continue
            ep_metrics = [
                compute_episode_metrics(ep, exp_actions.get(sc, 1))
                for ep in eps
            ]
            for m in metrics:
                avg = float(np.mean([em[m] for em in ep_metrics]))
                arrays[m].append(avg)

        result[model_name] = {
            m: np.array(arrays[m]) for m in metrics
        }

    return result


# ---------------------------------------------------------------------------
# Bootstrap CI (percentile method)
# ---------------------------------------------------------------------------
def bootstrap_ci(
    data: np.ndarray,
    n_boot: int,
    rng: np.random.Generator,
    alpha: float = 0.05,
) -> tuple[float, float, float]:
    """Compute bootstrap percentile CI for mean of scenario-level data.

    Args:
        data: 1-D array of scenario-level values.
        n_boot: Number of bootstrap resamples.
        rng: NumPy random generator.
        alpha: Significance level (two-sided).

    Returns:
        (point_estimate, ci_lower, ci_upper)
    """
    n = len(data)
    point = float(np.mean(data))
    boot_means = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_means[i] = np.mean(data[idx])
    lo = float(np.percentile(boot_means, 100 * alpha / 2))
    hi = float(np.percentile(boot_means, 100 * (1 - alpha / 2)))
    return point, lo, hi


def bootstrap_paired_diff(
    data_a: np.ndarray,
    data_b: np.ndarray,
    n_boot: int,
    rng: np.random.Generator,
    alpha: float = 0.05,
) -> tuple[float, float, float, bool]:
    """Bootstrap CI for paired difference (A - B) at scenario level.

    Returns:
        (mean_diff, ci_lower, ci_upper, includes_zero)
    """
    diff = data_a - data_b
    point = float(np.mean(diff))
    n = len(diff)
    boot_diffs = np.empty(n_boot)
    for i in range(n_boot):
        idx = rng.integers(0, n, size=n)
        boot_diffs[i] = np.mean(diff[idx])
    lo = float(np.percentile(boot_diffs, 100 * alpha / 2))
    hi = float(np.percentile(boot_diffs, 100 * (1 - alpha / 2)))
    includes_zero = lo <= 0.0 <= hi
    return point, lo, hi, includes_zero


def run_bootstrap_analysis(
    scenario_data: dict[str, dict[str, np.ndarray]],
    models: list[str],
    n_boot: int,
    rng: np.random.Generator,
) -> dict:
    """Run full bootstrap CI analysis.

    Args:
        scenario_data: {model: {metric: array}}.
        models: Ordered list of model names.
        n_boot: Number of resamples.
        rng: Random generator.

    Returns:
        Dict with per_model and pairwise results.
    """
    target_metrics = ["cga", "composite_a", "coverage"]

    per_model: dict[str, dict] = {}
    for model in models:
        per_model[model] = {}
        for metric in target_metrics:
            pt, lo, hi = bootstrap_ci(
                scenario_data[model][metric], n_boot, rng
            )
            per_model[model][metric] = {
                "point": round(pt, 4),
                "ci_lower": round(lo, 4),
                "ci_upper": round(hi, 4),
                "ci_width": round(hi - lo, 4),
            }

    pairwise: dict[str, dict] = {}
    for i, j in combinations(range(len(models)), 2):
        ma, mb = models[i], models[j]
        pair_key = f"{ma} - {mb}"
        pairwise[pair_key] = {}
        for metric in target_metrics:
            diff, lo, hi, incl_zero = bootstrap_paired_diff(
                scenario_data[ma][metric],
                scenario_data[mb][metric],
                n_boot,
                rng,
            )
            pairwise[pair_key][metric] = {
                "mean_diff": round(diff, 4),
                "ci_lower": round(lo, 4),
                "ci_upper": round(hi, 4),
                "includes_zero": incl_zero,
                "interpretation": (
                    "not statistically distinguishable"
                    if incl_zero
                    else f"{ma} {'>' if diff > 0 else '<'} {mb}"
                ),
            }

    return {
        "method": "percentile bootstrap",
        "n_bootstrap": n_boot,
        "n_scenarios": 15,
        "resampling_unit": "scenario (averaged over 3 runs)",
        "alpha": ALPHA,
        "per_model": per_model,
        "pairwise": pairwise,
    }


# ---------------------------------------------------------------------------
# Required sample-size simulation
# ---------------------------------------------------------------------------
def simulate_power_curve(
    scenario_data: dict[str, dict[str, np.ndarray]],
    models: list[str],
    metric: str,
    sample_sizes: list[int],
    n_sim: int,
    rng: np.random.Generator,
) -> dict[str, list[float]]:
    """Monte Carlo power simulation for Friedman test.

    For each candidate n, draw n scenarios with replacement from the
    observed 15, then run Friedman across all models. Record fraction
    of simulations where p < 0.05.

    Args:
        scenario_data: {model: {metric: array}}.
        models: List of model names.
        metric: Which metric to test.
        sample_sizes: List of n values to simulate.
        n_sim: Number of Monte Carlo iterations per n.
        rng: Random generator.

    Returns:
        {"sample_sizes": [...], "power": [...], "recommended_n": int}
    """
    n_observed = len(scenario_data[models[0]][metric])
    # Stack: shape (n_models, n_scenarios)
    stacked = np.array([scenario_data[m][metric] for m in models])

    powers: list[float] = []
    for n in sample_sizes:
        rejections = 0
        for _ in range(n_sim):
            idx = rng.integers(0, n_observed, size=n)
            samples = [stacked[k, idx] for k in range(len(models))]
            # Friedman requires at least 3 groups and n >= 2
            try:
                _, p = stats.friedmanchisquare(*samples)
                if p < ALPHA:
                    rejections += 1
            except ValueError:
                pass
        power = rejections / n_sim
        powers.append(round(power, 4))

    # Find smallest n with power >= 0.80
    recommended_n: int | None = None
    for n, pw in zip(sample_sizes, powers):
        if pw >= 0.80:
            recommended_n = n
            break

    return {
        "sample_sizes": sample_sizes,
        "power": powers,
        "recommended_n": recommended_n,
        "metric": metric,
        "test": "Friedman chi-square",
        "alpha": ALPHA,
        "n_simulations": n_sim,
        "n_models": len(models),
    }


# ---------------------------------------------------------------------------
# LaTeX table
# ---------------------------------------------------------------------------
def generate_latex_table(
    bootstrap_results: dict,
    models: list[str],
) -> str:
    """Generate LaTeX table with point estimates and 95% CIs.

    Args:
        bootstrap_results: Output of run_bootstrap_analysis.
        models: Ordered model list.

    Returns:
        LaTeX table string.
    """
    metrics = [
        ("cga", "CGA Score"),
        ("composite_a", "Composite A"),
        ("coverage", "Coverage"),
    ]

    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Main results with 95\% bootstrap confidence intervals "
        r"(10{,}000 resamples, scenario-level resampling).}",
        r"\label{tab:main_results_ci}",
        r"\begin{tabular}{l" + "c" * len(metrics) + "}",
        r"\toprule",
        r"Model & " + " & ".join(m[1] for m in metrics) + r" \\",
        r"\midrule",
    ]

    per_model = bootstrap_results["per_model"]
    for model in models:
        cells = [model.replace("_", r"\_")]
        for metric_key, _ in metrics:
            d = per_model[model][metric_key]
            cell = (
                f"{d['point']:.3f} "
                f"[{d['ci_lower']:.3f}, {d['ci_upper']:.3f}]"
            )
            cells.append(cell)
        lines.append(" & ".join(cells) + r" \\")

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ])
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Power curve figure
# ---------------------------------------------------------------------------
def plot_power_curve(power_results: dict, out_path: Path) -> None:
    """Plot sample size vs. statistical power and save as PDF.

    Args:
        power_results: Output of simulate_power_curve.
        out_path: Path for output PDF.
    """
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 11,
        "axes.labelsize": 12,
        "axes.titlesize": 13,
    })

    fig, ax = plt.subplots(figsize=(6, 4))
    sizes = power_results["sample_sizes"]
    powers = power_results["power"]

    ax.plot(sizes, powers, "o-", color="#2c3e50", linewidth=2, markersize=6)
    ax.axhline(y=0.80, color="#e74c3c", linestyle="--", linewidth=1,
               label="80% power threshold")

    rec_n = power_results.get("recommended_n")
    if rec_n is not None:
        rec_pow = powers[sizes.index(rec_n)]
        ax.annotate(
            f"n={rec_n} (power={rec_pow:.2f})",
            xy=(rec_n, rec_pow),
            xytext=(rec_n + 3, rec_pow - 0.08),
            arrowprops={"arrowstyle": "->", "color": "#2c3e50"},
            fontsize=10,
        )

    ax.set_xlabel("Number of scenarios (n)")
    ax.set_ylabel("Estimated power")
    ax.set_title(
        f"Power curve: Friedman test across 4 models\n"
        f"(metric: {power_results['metric']}, "
        f"{power_results['n_simulations']:,} simulations per n)"
    )
    ax.set_ylim(0, 1.05)
    ax.set_xticks(sizes)
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    fig.savefig(str(out_path), dpi=300, bbox_inches="tight")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Interpretation paragraph
# ---------------------------------------------------------------------------
def generate_interpretation(
    bootstrap_results: dict,
    power_results: dict,
    models: list[str],
) -> str:
    """Generate interpretation paragraph for the limitation section.

    Args:
        bootstrap_results: Bootstrap CI output.
        power_results: Power simulation output.
        models: Model name list.

    Returns:
        Plain-text paragraph.
    """
    pairwise = bootstrap_results["pairwise"]
    n_pairs = len(pairwise)
    n_indistinguishable = sum(
        1
        for pair_data in pairwise.values()
        for metric_data in pair_data.values()
        if metric_data["includes_zero"]
    )
    total_comparisons = n_pairs * 3  # 3 metrics per pair
    rec_n = power_results.get("recommended_n")

    parts = [
        f"Bootstrap analysis ({N_BOOTSTRAP:,} resamples, scenario-level "
        f"resampling unit, n=15 scenarios) reveals that "
        f"{n_indistinguishable}/{total_comparisons} pairwise model "
        f"comparisons include zero in their 95% CI, indicating these "
        f"differences are not statistically distinguishable at the current "
        f"sample size.",
    ]

    if rec_n is not None:
        parts.append(
            f"Monte Carlo power simulation estimates that approximately "
            f"{rec_n} scenarios are needed to achieve 80% power for the "
            f"Friedman test given the observed effect sizes."
        )
    else:
        parts.append(
            "Monte Carlo power simulation indicates that even with 50 "
            "scenarios, 80% power may not be achieved for the Friedman "
            "test, suggesting the observed inter-model differences are "
            "small relative to scenario-level variance."
        )

    # Identify widest CI
    widest_model = ""
    widest_metric = ""
    widest_width = 0.0
    for model in models:
        for metric in ["cga", "composite_a", "coverage"]:
            w = bootstrap_results["per_model"][model][metric]["ci_width"]
            if w > widest_width:
                widest_width = w
                widest_model = model
                widest_metric = metric

    parts.append(
        f"The widest CI is observed for {widest_model} on {widest_metric} "
        f"(width={widest_width:.3f}), reflecting high scenario-level variance."
    )

    return " ".join(parts)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    """Run bootstrap CI analysis and power simulation, write all outputs."""
    print("[1/5] Loading data...")
    scenarios, exp_actions = load_composite_meta()
    all_episodes = load_all_episodes(scenarios)

    # Report loading summary
    for model in MODEL_DIRS:
        counts = [len(all_episodes[model].get(sc, [])) for sc in scenarios]
        total = sum(counts)
        print(f"  {model}: {total} episodes across {sum(1 for c in counts if c > 0)}/15 scenarios")

    print("[2/5] Computing scenario-level metrics...")
    models = list(MODEL_DIRS.keys())
    scenario_data = build_scenario_level_data(
        all_episodes, scenarios, exp_actions
    )

    print(f"[3/5] Bootstrap CIs ({N_BOOTSTRAP:,} resamples)...")
    rng = np.random.default_rng(RNG_SEED)
    bootstrap_results = run_bootstrap_analysis(
        scenario_data, models, N_BOOTSTRAP, rng
    )

    print(f"[4/5] Power simulation ({N_POWER_SIM:,} sims per n)...")
    power_composite = simulate_power_curve(
        scenario_data, models, "composite_a",
        SAMPLE_SIZES, N_POWER_SIM, rng,
    )
    power_cga = simulate_power_curve(
        scenario_data, models, "cga",
        SAMPLE_SIZES, N_POWER_SIM, rng,
    )

    print("[5/5] Writing outputs...")

    # --- bootstrap_confidence_intervals.json ---
    interpretation = generate_interpretation(
        bootstrap_results, power_composite, models
    )
    bootstrap_results["interpretation"] = interpretation
    OUT_CI.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CI, "w") as fh:
        json.dump(bootstrap_results, fh, indent=2)
    print(f"  -> {OUT_CI}")

    # --- required_sample_size.json ---
    sample_size_output = {
        "composite_a": power_composite,
        "cga": power_cga,
        "interpretation": (
            f"For Composite A: recommended n={power_composite.get('recommended_n', 'N/A')} "
            f"for 80% power. "
            f"For CGA: recommended n={power_cga.get('recommended_n', 'N/A')} "
            f"for 80% power."
        ),
    }
    OUT_SS.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_SS, "w") as fh:
        json.dump(sample_size_output, fh, indent=2)
    print(f"  -> {OUT_SS}")

    # --- LaTeX table ---
    latex = generate_latex_table(bootstrap_results, models)
    OUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_TEX, "w") as fh:
        fh.write(latex)
    print(f"  -> {OUT_TEX}")

    # --- Power curve figure ---
    OUT_FIG.parent.mkdir(parents=True, exist_ok=True)
    plot_power_curve(power_composite, OUT_FIG)
    print(f"  -> {OUT_FIG}")

    # --- Print summary ---
    print("\n=== Summary ===")
    print(f"Scenarios: {len(scenarios)}")
    print(f"Models: {', '.join(models)}")
    print(f"Bootstrap resamples: {N_BOOTSTRAP:,}")
    print(f"Power simulations: {N_POWER_SIM:,} per n")
    print()

    for model in models:
        d = bootstrap_results["per_model"][model]
        print(
            f"  {model:20s}  "
            f"CGA={d['cga']['point']:.3f} [{d['cga']['ci_lower']:.3f}, {d['cga']['ci_upper']:.3f}]  "
            f"CompA={d['composite_a']['point']:.3f} [{d['composite_a']['ci_lower']:.3f}, {d['composite_a']['ci_upper']:.3f}]"
        )

    print()
    n_indist = sum(
        1
        for pd in bootstrap_results["pairwise"].values()
        for md in pd.values()
        if md["includes_zero"]
    )
    total_comp = len(bootstrap_results["pairwise"]) * 3
    print(f"Pairwise: {n_indist}/{total_comp} comparisons include zero in CI")
    print(f"Power (Composite A): {dict(zip(SAMPLE_SIZES, power_composite['power']))}")
    print(f"Recommended n (Composite A): {power_composite.get('recommended_n', 'N/A')}")
    print()
    print("Interpretation:")
    print(interpretation)


if __name__ == "__main__":
    main()
