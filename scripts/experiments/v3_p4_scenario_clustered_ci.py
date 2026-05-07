
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""V3-P4: Scenario-Clustered Bootstrap Confidence Intervals.

Upgrades from naive episode-level resampling to scenario-clustered bootstrap,
which correctly accounts for the within-scenario correlation structure of the
15-scenario × 3-run CGA-Bench design.

Outputs:
  evidence_pack/analysis/v3_scenario_clustered_ci.json
  evidence_pack/analysis/v3_scenario_clustered_ci.md
  evidence_pack/tables/scenario_clustered_ci.tex

Run: PYTHONPATH=. python scripts/experiments/v3_p4_scenario_clustered_ci.py
"""

from __future__ import annotations

import json
from pathlib import Path
import time

import numpy as np
from scipy import stats as scipy_stats  # type: ignore[import-untyped]

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).parent.parent.parent
RESULTS_DIR = REPO_ROOT / "results" / "clean_slate_rescored"
ANALYSIS_DIR = REPO_ROOT / "evidence_pack" / "analysis"
TABLES_DIR = REPO_ROOT / "evidence_pack" / "tables"

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODELS: list[str] = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]
MODEL_LABELS: dict[str, str] = {
    "oss120b": "DeepSeek-V3 (120B)",
    "qwen27b": "R1-Distill (27B)",
    "qwen35b": "Qwen3.5 (35B)",
    "qwen4b": "Qwen3 (4B)",
}
N_SCENARIOS = 15
RUNS_PER_SCENARIO = 3
EPISODES_PER_MODEL = N_SCENARIOS * RUNS_PER_SCENARIO  # 45
B = 10_000
SEED = 42
ALPHA = 0.05
SUB_SCORES = [
    "C1_path_selection",
    "C2_mandatory_completion",
    "C3_forbidden_avoidance",
    "C4_timing_compliance",
    "C5_sequence_integrity",
]
SUB_SCORE_LABELS = ["C1", "C2", "C3", "C4", "C5"]

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_all_episodes() -> list[dict]:
    """Load all rescored episodes from the 4 model subdirectories."""
    episodes: list[dict] = []
    for model_dir_name in MODELS:
        model_dir = RESULTS_DIR / model_dir_name
        if not model_dir.exists():
            print(f"  WARNING: directory not found: {model_dir}")
            continue
        for fpath in sorted(model_dir.glob("*.json")):
            with fpath.open() as fh:
                ep: dict = json.load(fh)
            ep["_model_dir"] = model_dir_name
            episodes.append(ep)
    return episodes


def build_model_data(
    episodes: list[dict],
) -> dict[str, dict[str, list[float]]]:
    """Organise episodes into {model_dir: {scenario_id: [cga_scores]}}.

    Returns a nested dict where the inner list always has length
    RUNS_PER_SCENARIO (3).
    """
    data: dict[str, dict[str, list[float]]] = {m: {} for m in MODELS}
    for ep in episodes:
        model = ep["_model_dir"]
        sid = ep["scenario_id"]
        score = float(ep["new_compliance_score"])
        data[model].setdefault(sid, []).append(score)
    return data


def build_model_sub_data(
    episodes: list[dict],
    sub_key: str,
) -> dict[str, dict[str, list[float]]]:
    """Same as build_model_data but for a single sub-score."""
    data: dict[str, dict[str, list[float]]] = {m: {} for m in MODELS}
    for ep in episodes:
        model = ep["_model_dir"]
        sid = ep["scenario_id"]
        val = float(ep.get("new_sub_scores", {}).get(sub_key, 0.0))
        data[model].setdefault(sid, []).append(val)
    return data


# ---------------------------------------------------------------------------
# Bootstrap helpers
# ---------------------------------------------------------------------------


def scenario_mean(
    scenario_scores: dict[str, list[float]],
    sampled_scenarios: list[str],
) -> float:
    """Mean CGA score across all runs of the sampled scenarios."""
    values: list[float] = []
    for sid in sampled_scenarios:
        values.extend(scenario_scores[sid])
    return float(np.mean(values)) if values else 0.0


def percentile_ci(
    boot_dist: np.ndarray,
    alpha: float = ALPHA,
) -> tuple[float, float]:
    """Percentile-method CI: (lower, upper)."""
    lo = float(np.percentile(boot_dist, 100 * alpha / 2))
    hi = float(np.percentile(boot_dist, 100 * (1 - alpha / 2)))
    return lo, hi


def bca_ci(
    boot_dist: np.ndarray,
    theta_hat: float,
    jackknife_stats: np.ndarray,
    alpha: float = ALPHA,
) -> tuple[float, float]:
    """Bias-corrected and accelerated (BCa) CI."""
    # Bias correction z0
    prop_less = float(np.mean(boot_dist < theta_hat))
    # Guard against degenerate cases
    prop_less = np.clip(prop_less, 1e-6, 1.0 - 1e-6)
    z0 = float(scipy_stats.norm.ppf(prop_less))

    # Acceleration a via jackknife
    jack_mean = float(np.mean(jackknife_stats))
    diff = jack_mean - jackknife_stats  # shape (n,)
    num = float(np.sum(diff**3))
    denom = 6.0 * float(np.sum(diff**2) ** 1.5)
    a = num / denom if abs(denom) > 1e-12 else 0.0

    z_lo = scipy_stats.norm.ppf(alpha / 2)
    z_hi = scipy_stats.norm.ppf(1.0 - alpha / 2)

    def adjusted_alpha(z: float) -> float:
        numer = z0 + z
        denom2 = 1.0 - a * (z0 + z)
        if abs(denom2) < 1e-12:
            return alpha / 2
        return float(scipy_stats.norm.cdf(z0 + numer / denom2))

    a1 = np.clip(adjusted_alpha(z_lo), 1e-4, 1.0 - 1e-4)
    a2 = np.clip(adjusted_alpha(z_hi), 1e-4, 1.0 - 1e-4)

    ci_lo = float(np.percentile(boot_dist, 100 * a1))
    ci_hi = float(np.percentile(boot_dist, 100 * a2))
    return ci_lo, ci_hi


# ---------------------------------------------------------------------------
# Scenario-clustered bootstrap
# ---------------------------------------------------------------------------


def scenario_clustered_bootstrap(
    scenario_scores: dict[str, list[float]],
    rng: np.random.Generator,
    n_bootstrap: int = B,
) -> dict[str, float | list[float]]:
    """Scenario-clustered bootstrap CI for mean CGA.

    Resampling unit = scenario.  Each iteration samples 15 scenarios WITH
    replacement, includes ALL 3 runs per sampled scenario, then computes the
    grand mean.

    Returns a dict with keys: mean, lower_pct, upper_pct, lower_bca, upper_bca,
    ci_width_pct, ci_width_bca, boot_dist (list for JSON serialisation).
    """
    scenarios = sorted(scenario_scores.keys())
    n = len(scenarios)

    theta_hat = float(np.mean([s for runs in scenario_scores.values() for s in runs]))

    # Bootstrap distribution
    boot_dist = np.zeros(n_bootstrap)
    for i in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        sampled = [scenarios[j] for j in idx]
        boot_dist[i] = scenario_mean(scenario_scores, sampled)

    # Jackknife for BCa acceleration (leave-one-scenario-out)
    jack_stats = np.zeros(n)
    for k in range(n):
        leave_out = [scenarios[j] for j in range(n) if j != k]
        jack_stats[k] = scenario_mean(scenario_scores, leave_out)

    lo_pct, hi_pct = percentile_ci(boot_dist)
    lo_bca, hi_bca = bca_ci(boot_dist, theta_hat, jack_stats)

    return {
        "mean": round(theta_hat, 6),
        "lower_pct": round(lo_pct, 6),
        "upper_pct": round(hi_pct, 6),
        "lower_bca": round(lo_bca, 6),
        "upper_bca": round(hi_bca, 6),
        "ci_width_pct": round(hi_pct - lo_pct, 6),
        "ci_width_bca": round(hi_bca - lo_bca, 6),
        "boot_dist_p2_5": round(float(np.percentile(boot_dist, 2.5)), 6),
        "boot_dist_p97_5": round(float(np.percentile(boot_dist, 97.5)), 6),
    }


# ---------------------------------------------------------------------------
# Episode-level bootstrap (comparison)
# ---------------------------------------------------------------------------


def episode_level_bootstrap(
    episode_scores: list[float],
    rng: np.random.Generator,
    n_bootstrap: int = B,
) -> dict[str, float]:
    """Standard episode-level bootstrap CI for mean CGA."""
    arr = np.array(episode_scores, dtype=float)
    n = len(arr)
    theta_hat = float(np.mean(arr))

    boot_dist = np.zeros(n_bootstrap)
    for i in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        boot_dist[i] = float(np.mean(arr[idx]))

    lo_pct, hi_pct = percentile_ci(boot_dist)

    return {
        "mean": round(theta_hat, 6),
        "lower_pct": round(lo_pct, 6),
        "upper_pct": round(hi_pct, 6),
        "ci_width_pct": round(hi_pct - lo_pct, 6),
    }


# ---------------------------------------------------------------------------
# Friedman test with scenario-level means
# ---------------------------------------------------------------------------


def build_friedman_matrix(
    model_data: dict[str, dict[str, list[float]]],
) -> tuple[np.ndarray, list[str], list[str]]:
    """Build (n_scenarios × n_models) matrix of per-scenario mean CGA scores."""
    all_scenarios = sorted(set(sid for m in MODELS for sid in model_data[m]))
    matrix = np.zeros((len(all_scenarios), len(MODELS)), dtype=float)
    for j, model in enumerate(MODELS):
        for i, sid in enumerate(all_scenarios):
            scores = model_data[model].get(sid, [0.0])
            matrix[i, j] = float(np.mean(scores))
    return matrix, all_scenarios, MODELS


def friedman_p(matrix: np.ndarray) -> float:
    """Compute Friedman test p-value on a (n_blocks × k_treatments) matrix."""
    result = scipy_stats.friedmanchisquare(*[matrix[:, j] for j in range(matrix.shape[1])])
    return float(result.pvalue)


def bootstrap_friedman_p(
    matrix: np.ndarray,
    rng: np.random.Generator,
    n_bootstrap: int = B,
) -> dict[str, float | list[float]]:
    """Bootstrap the Friedman p-value by resampling scenarios (rows)."""
    n_scenarios, n_models = matrix.shape
    observed_p = friedman_p(matrix)

    boot_ps = np.zeros(n_bootstrap)
    for i in range(n_bootstrap):
        row_idx = rng.integers(0, n_scenarios, size=n_scenarios)
        boot_mat = matrix[row_idx, :]
        try:
            boot_ps[i] = friedman_p(boot_mat)
        except Exception:
            boot_ps[i] = 1.0

    lo, hi = percentile_ci(boot_ps)
    return {
        "observed_p": round(observed_p, 6),
        "boot_p_mean": round(float(np.mean(boot_ps)), 6),
        "boot_p_median": round(float(np.median(boot_ps)), 6),
        "boot_p_ci_lower": round(lo, 6),
        "boot_p_ci_upper": round(hi, 6),
        "boot_p_dist_p2_5": round(float(np.percentile(boot_ps, 2.5)), 6),
        "boot_p_dist_p97_5": round(float(np.percentile(boot_ps, 97.5)), 6),
        "n_bootstrap": n_bootstrap,
        "n_scenarios": n_scenarios,
    }


# ---------------------------------------------------------------------------
# Formatting helpers
# ---------------------------------------------------------------------------


def fmt_ci(mean: float, lo: float, hi: float, decimals: int = 3) -> str:
    """Format as 'mean [lo, hi]'."""
    fmt = f".{decimals}f"
    return f"{mean:{fmt}} [{lo:{fmt}}, {hi:{fmt}}]"


def fmt_pct(x: float) -> str:
    return f"{x:.4f}"


# ---------------------------------------------------------------------------
# Markdown report builder
# ---------------------------------------------------------------------------


def build_md_report(results: dict) -> str:
    lines: list[str] = []
    lines.append("# V3-P4: Scenario-Clustered Bootstrap Confidence Intervals")
    lines.append("")
    lines.append("**Data**: 180 rescored episodes · 4 models · 15 scenarios × 3 runs each")
    lines.append(f"**Bootstrap**: B = {B:,} iterations · seed = {SEED} · percentile + BCa methods")
    lines.append("")

    # --- Main CGA table ---
    lines.append("## 1. Mean CGA Score — Scenario-Clustered vs Episode-Level CI")
    lines.append("")
    lines.append("| Model | Mean CGA | Scenario CI (pct) | Episode CI (pct) | Width Ratio | Scenario CI (BCa) |")
    lines.append("|---|---|---|---|---|---|")

    for model in MODELS:
        r = results["cga_bootstrap"][model]
        sc = r["scenario_clustered"]
        ep = r["episode_level"]
        ratio = sc["ci_width_pct"] / ep["ci_width_pct"] if ep["ci_width_pct"] > 0 else float("inf")
        bca_str = fmt_ci(sc["mean"], sc["lower_bca"], sc["upper_bca"])
        lines.append(
            f"| {MODEL_LABELS[model]} "
            f"| {sc['mean']:.4f} "
            f"| [{sc['lower_pct']:.4f}, {sc['upper_pct']:.4f}] "
            f"| [{ep['lower_pct']:.4f}, {ep['upper_pct']:.4f}] "
            f"| {ratio:.2f}x "
            f"| [{sc['lower_bca']:.4f}, {sc['upper_bca']:.4f}] |"
        )

    lines.append("")
    lines.append(
        "> **Width ratio > 1.0** indicates scenario-clustered CIs are wider than "
        "episode-level CIs, as expected when within-scenario episodes are positively "
        "correlated.  A ratio near 1.0 indicates low intra-cluster correlation."
    )
    lines.append("")

    # --- Sub-score table ---
    lines.append("## 2. Sub-Score CIs (Scenario-Clustered, Percentile Method)")
    lines.append("")
    header = "| Model | " + " | ".join(SUB_SCORE_LABELS) + " |"
    sep = "|---|" + "---|" * len(SUB_SCORE_LABELS)
    lines.append(header)
    lines.append(sep)

    for model in MODELS:
        cells = [MODEL_LABELS[model]]
        for sub in SUB_SCORES:
            r = results["sub_score_bootstrap"][model][sub]["scenario_clustered"]
            cells.append(f"[{r['lower_pct']:.3f}, {r['upper_pct']:.3f}]")
        lines.append("| " + " | ".join(cells) + " |")

    lines.append("")
    lines.append(
        "Sub-score key: C1=path selection · C2=mandatory completion · "
        "C3=forbidden avoidance · C4=timing · C5=sequence integrity"
    )
    lines.append("")

    # --- Friedman ---
    fr = results["friedman"]
    lines.append("## 3. Friedman Test with Bootstrap p-value CI")
    lines.append("")
    lines.append(
        f"- **Observed Friedman p-value**: {fr['observed_p']:.4f}"
        + (" (significant at α=0.05)" if fr["observed_p"] < 0.05 else " (not significant at α=0.05)")
    )
    lines.append(f"- **Bootstrap 95% CI for p-value**: [{fr['boot_p_ci_lower']:.4f}, {fr['boot_p_ci_upper']:.4f}]")
    lines.append(f"- Bootstrap mean p: {fr['boot_p_mean']:.4f} · median p: {fr['boot_p_median']:.4f}")
    lines.append(f"- n_scenarios (blocks) = {fr['n_scenarios']}, n_models (treatments) = 4")
    lines.append("")

    # --- Key findings ---
    lines.append("## 4. Key Findings")
    lines.append("")
    ratios = []
    for model in MODELS:
        r = results["cga_bootstrap"][model]
        sc_w = r["scenario_clustered"]["ci_width_pct"]
        ep_w = r["episode_level"]["ci_width_pct"]
        if ep_w > 0:
            ratios.append(sc_w / ep_w)

    mean_ratio = float(np.mean(ratios)) if ratios else 0.0
    max_ratio = float(np.max(ratios)) if ratios else 0.0
    min_ratio = float(np.min(ratios)) if ratios else 0.0

    lines.append(
        f"- Scenario-clustered CIs are on average **{mean_ratio:.2f}x wider** "
        f"than episode-level CIs (range: {min_ratio:.2f}x–{max_ratio:.2f}x)."
    )

    if mean_ratio > 1.05:
        lines.append(
            "- This confirms **positive intra-scenario correlation**: episodes from "
            "the same scenario are not exchangeable, validating the choice of "
            "scenario-clustered resampling as the statistically conservative approach."
        )
    else:
        lines.append(
            "- The width ratio is close to 1.0, suggesting low intra-scenario "
            "correlation in this dataset. Episode-level and scenario-clustered "
            "bootstrap give similar uncertainty estimates."
        )

    fr_sig = fr["observed_p"] < 0.05
    boot_ci_excludes_05 = fr["boot_p_ci_upper"] < 0.05
    lines.append(
        f"- Friedman test p={fr['observed_p']:.4f} is "
        + ("statistically significant" if fr_sig else "not significant")
        + f"; bootstrap CI [{fr['boot_p_ci_lower']:.4f}, {fr['boot_p_ci_upper']:.4f}] "
        + ("entirely below 0.05 — result is robust." if boot_ci_excludes_05 else "spans 0.05 — interpret with caution.")
    )
    lines.append("")
    lines.append("_Generated by `scripts/experiments/v3_p4_scenario_clustered_ci.py`_")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LaTeX table builder
# ---------------------------------------------------------------------------


def build_latex_table(results: dict) -> str:
    lines: list[str] = []
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(
        r"\caption{Scenario-clustered vs.\ episode-level 95\% bootstrap confidence "
        r"intervals for mean CGA score. Resampling unit for scenario-clustered CI is "
        r"the scenario (15 units); episode-level CI resamples individual runs (45 units). "
        r"Width ratio $> 1$ indicates positive intra-scenario correlation. "
        r"$B = 10{,}000$ bootstrap iterations.}"
    )
    lines.append(r"\label{tab:scenario-clustered-ci}")
    lines.append(r"\begin{tabular}{lcccc}")
    lines.append(r"\toprule")
    lines.append(r"Model & Mean CGA & Scenario-Clustered CI & Episode-Level CI & Width Ratio \\")
    lines.append(r"\midrule")

    for model in MODELS:
        r = results["cga_bootstrap"][model]
        sc = r["scenario_clustered"]
        ep = r["episode_level"]
        ratio = sc["ci_width_pct"] / ep["ci_width_pct"] if ep["ci_width_pct"] > 0 else float("inf")
        label = MODEL_LABELS[model].replace("(", r"\small(").replace(")", r"\small)")
        lines.append(
            f"{label} & {sc['mean']:.4f} "
            f"& [{sc['lower_pct']:.4f}, {sc['upper_pct']:.4f}] "
            f"& [{ep['lower_pct']:.4f}, {ep['upper_pct']:.4f}] "
            f"& {ratio:.2f}$\\times$ \\\\"
        )

    lines.append(r"\midrule")
    # Sub-score header
    lines.append(r"\multicolumn{5}{l}{\textit{Sub-score CIs (scenario-clustered, percentile)}} \\")
    lines.append(r"\midrule")
    lines.append(r"Model & C1 & C2 & C3 & C4/C5 \\")
    lines.append(r"\midrule")

    for model in MODELS:
        label = MODEL_LABELS[model].replace("(", r"\small(").replace(")", r"\small)")
        sub_cells = []
        for sub in SUB_SCORES[:4]:
            r_sub = results["sub_score_bootstrap"][model][sub]["scenario_clustered"]
            sub_cells.append(f"[{r_sub['lower_pct']:.3f}, {r_sub['upper_pct']:.3f}]")
        # C4 and C5 together in last column — just C4 fits; use C4
        lines.append(f"{label} & " + " & ".join(sub_cells) + r" \\")

    lines.append(r"\midrule")
    fr = results["friedman"]
    lines.append(
        r"\multicolumn{5}{l}{Friedman $\chi^2$ test (scenario-level means): "
        f"$p = {fr['observed_p']:.4f}$, "
        f"bootstrap 95\\% CI $[{fr['boot_p_ci_lower']:.4f}, {fr['boot_p_ci_upper']:.4f}]$"
        r"} \\"
    )
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    t_start = time.perf_counter()
    rng = np.random.default_rng(SEED)

    print("=" * 70)
    print("V3-P4: Scenario-Clustered Bootstrap Confidence Intervals")
    print(f"  B = {B:,}  seed = {SEED}  alpha = {ALPHA}")
    print("=" * 70)

    # ------------------------------------------------------------------
    # Load data
    # ------------------------------------------------------------------
    print("\n[1/6] Loading episodes...", flush=True)
    episodes = load_all_episodes()
    print(f"  Loaded {len(episodes)} episodes from {len(MODELS)} model dirs")

    model_data = build_model_data(episodes)
    for m in MODELS:
        n_sc = len(model_data[m])
        n_ep = sum(len(v) for v in model_data[m].values())
        print(f"  {m}: {n_sc} scenarios, {n_ep} episodes")

    # ------------------------------------------------------------------
    # Scenario-clustered + episode-level bootstrap for CGA
    # ------------------------------------------------------------------
    print("\n[2/6] CGA scenario-clustered bootstrap (B=10,000)...", flush=True)
    cga_results: dict[str, dict] = {}

    for model in MODELS:
        t0 = time.perf_counter()
        scenario_scores = model_data[model]
        all_episode_scores = [s for runs in scenario_scores.values() for s in runs]

        # Scenario-clustered (primary)
        sc_r = scenario_clustered_bootstrap(scenario_scores, rng)

        # Episode-level (comparison)
        ep_r = episode_level_bootstrap(all_episode_scores, rng)

        ratio = sc_r["ci_width_pct"] / ep_r["ci_width_pct"] if ep_r["ci_width_pct"] > 0 else float("inf")

        cga_results[model] = {
            "scenario_clustered": sc_r,
            "episode_level": ep_r,
            "ci_width_ratio": round(ratio, 4),
            "n_scenarios": len(scenario_scores),
            "n_episodes": len(all_episode_scores),
        }

        elapsed = time.perf_counter() - t0
        print(
            f"  {MODEL_LABELS[model]}: mean={sc_r['mean']:.4f}  "
            f"SC CI=[{sc_r['lower_pct']:.4f}, {sc_r['upper_pct']:.4f}]  "
            f"EP CI=[{ep_r['lower_pct']:.4f}, {ep_r['upper_pct']:.4f}]  "
            f"ratio={ratio:.2f}x  ({elapsed:.1f}s)",
            flush=True,
        )

    # ------------------------------------------------------------------
    # Sub-score CIs
    # ------------------------------------------------------------------
    print("\n[3/6] Sub-score scenario-clustered bootstrap...", flush=True)
    sub_results: dict[str, dict[str, dict]] = {m: {} for m in MODELS}

    for sub_key, sub_label in zip(SUB_SCORES, SUB_SCORE_LABELS):
        sub_data = build_model_sub_data(episodes, sub_key)
        for model in MODELS:
            scenario_scores = sub_data[model]
            all_ep_scores = [s for runs in scenario_scores.values() for s in runs]

            sc_r = scenario_clustered_bootstrap(scenario_scores, rng)
            ep_r = episode_level_bootstrap(all_ep_scores, rng)
            ratio = sc_r["ci_width_pct"] / ep_r["ci_width_pct"] if ep_r["ci_width_pct"] > 0 else float("inf")

            sub_results[model][sub_key] = {
                "sub_label": sub_label,
                "scenario_clustered": sc_r,
                "episode_level": ep_r,
                "ci_width_ratio": round(ratio, 4),
            }

        print(
            f"  {sub_label} ({sub_key}): "
            + "  ".join(
                f"{MODEL_LABELS[m][:12]}=[{sub_results[m][sub_key]['scenario_clustered']['lower_pct']:.3f},"
                f"{sub_results[m][sub_key]['scenario_clustered']['upper_pct']:.3f}]"
                for m in MODELS
            ),
            flush=True,
        )

    # ------------------------------------------------------------------
    # Friedman test with bootstrap
    # ------------------------------------------------------------------
    print("\n[4/6] Friedman test + bootstrap p-value CI...", flush=True)
    t0 = time.perf_counter()
    matrix, scenario_list, model_list = build_friedman_matrix(model_data)
    friedman_results = bootstrap_friedman_p(matrix, rng)
    elapsed = time.perf_counter() - t0

    print(
        f"  Observed p = {friedman_results['observed_p']:.4f}  "
        f"Boot CI = [{friedman_results['boot_p_ci_lower']:.4f}, "
        f"{friedman_results['boot_p_ci_upper']:.4f}]  "
        f"({elapsed:.1f}s)",
        flush=True,
    )
    print(f"  Scenario matrix shape: {matrix.shape}  (rows=scenarios, cols=models)")
    # Print scenario-level means for transparency
    print("  Per-model mean CGA (scenario-level matrix row-means):")
    for j, model in enumerate(model_list):
        print(f"    {MODEL_LABELS[model]}: {matrix[:, j].mean():.4f}")

    # ------------------------------------------------------------------
    # Compile results
    # ------------------------------------------------------------------
    print("\n[5/6] Compiling results...", flush=True)
    results: dict = {
        "meta": {
            "description": "Scenario-clustered bootstrap CI for CGA-Bench",
            "n_bootstrap": B,
            "seed": SEED,
            "alpha": ALPHA,
            "n_models": len(MODELS),
            "n_scenarios": N_SCENARIOS,
            "runs_per_scenario": RUNS_PER_SCENARIO,
            "total_episodes": len(episodes),
            "models": MODELS,
            "model_labels": MODEL_LABELS,
            "sub_scores": SUB_SCORES,
        },
        "cga_bootstrap": cga_results,
        "sub_score_bootstrap": sub_results,
        "friedman": friedman_results,
        "scenario_order": scenario_list,
        "scenario_level_matrix": {
            model: {scenario_list[i]: round(float(matrix[i, j]), 6) for i in range(len(scenario_list))}
            for j, model in enumerate(model_list)
        },
    }

    # ------------------------------------------------------------------
    # Write outputs
    # ------------------------------------------------------------------
    print("\n[6/6] Writing output files...", flush=True)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    # JSON
    json_path = ANALYSIS_DIR / "v3_scenario_clustered_ci.json"
    with json_path.open("w") as f:
        json.dump(results, f, indent=2)
    print(f"  JSON  -> {json_path}")

    # Markdown
    md_report = build_md_report(results)
    md_path = ANALYSIS_DIR / "v3_scenario_clustered_ci.md"
    with md_path.open("w") as f:
        f.write(md_report)
    print(f"  MD    -> {md_path}")

    # LaTeX
    latex_str = build_latex_table(results)
    tex_path = TABLES_DIR / "scenario_clustered_ci.tex"
    with tex_path.open("w") as f:
        f.write(latex_str)
    print(f"  LaTeX -> {tex_path}")

    # ------------------------------------------------------------------
    # Summary
    # ------------------------------------------------------------------
    t_total = time.perf_counter() - t_start
    print("\n" + "=" * 70)
    print(f"DONE in {t_total:.1f}s")
    print("=" * 70)

    print("\nKey results:")
    print(f"{'Model':<25} {'Mean':>6} {'SC-CI':>22} {'EP-CI':>22} {'Ratio':>7}")
    print("-" * 85)
    for model in MODELS:
        r = results["cga_bootstrap"][model]
        sc = r["scenario_clustered"]
        ep = r["episode_level"]
        ratio = r["ci_width_ratio"]
        print(
            f"{MODEL_LABELS[model]:<25} "
            f"{sc['mean']:>6.4f} "
            f"[{sc['lower_pct']:.4f}, {sc['upper_pct']:.4f}]  "
            f"[{ep['lower_pct']:.4f}, {ep['upper_pct']:.4f}]  "
            f"{ratio:>6.2f}x"
        )

    fr = results["friedman"]
    print(
        f"\nFriedman p = {fr['observed_p']:.4f}  "
        f"bootstrap CI = [{fr['boot_p_ci_lower']:.4f}, {fr['boot_p_ci_upper']:.4f}]"
    )


if __name__ == "__main__":
    main()
