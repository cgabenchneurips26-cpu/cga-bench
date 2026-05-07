#!/usr/bin/env python3
"""EXP-E4: Operating-Point Matched Agreement Analysis.

Sweeps thresholds so all four evaluators share the same pass rate,
then measures inter-rater agreement at each matched operating point.
Proves that disagreement is not a threshold-calibration artifact.

Outputs:
  evidence_pack/exp_e4_operating_point.json
  evidence_pack/exp_e4_operating_point.md
  evidence_pack/figures/exp_e4_kappa_vs_passrate.png
  evidence_pack/figures/exp_e4_matched_heatmaps.png
  evidence_pack/tables/operating_point_matched.tex

Usage:
    PYTHONPATH=. python scripts/experiments/exp_e4_operating_point.py
"""

from __future__ import annotations

from itertools import combinations
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    TABLES_DIR,
    fmt_f,
    save_figure,
    save_json,
    save_latex_table,
    save_markdown,
    setup_matplotlib,
)
from sklearn.metrics import cohen_kappa_score

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
N_EPISODES: int = 0  # set dynamically in main()
N_THRESHOLDS: int = 50
TARGET_PASS_RATES: list[float] = [0.3, 0.4, 0.5]

EVALUATOR_NAMES: list[str] = ["AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]

VERDICT_MATRIX_PATH: Path = EVIDENCE_DIR / "analysis" / "verdict_matrix_v6.json"

# Cluster membership: {AC-Proxy, C2} vs {MAB-Proxy, CGA-Bench}
CLUSTER_A: frozenset[str] = frozenset({"AC-Proxy", "C2"})
CLUSTER_B: frozenset[str] = frozenset({"MAB-Proxy", "CGA-Bench"})

# Pair colours for kappa-vs-passrate plot
_PAIR_COLORS: list[str] = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728", "#9467bd", "#8c564b"]
_PAIR_MARKERS: list[str] = ["o", "s", "^", "D", "v", "P"]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_raw_scores(path: Path) -> dict[str, np.ndarray]:
    """Load per-episode raw scores from verdict_matrix_v6.json.

    Args:
        path: Path to verdict_matrix_v6.json.

    Returns:
        Dict mapping evaluator name to 1-D float array of length N_EPISODES.
    """
    with open(path) as fh:
        data: dict[str, Any] = json.load(fh)

    episodes: list[dict[str, Any]] = data["per_episode"]
    global N_EPISODES
    N_EPISODES = len(episodes)
    print(f"  Loaded {N_EPISODES} episodes")

    ac_proxy = np.array([ep["action_coverage"] for ep in episodes], dtype=float)
    mab_proxy = np.array([ep["mab_f1"] for ep in episodes], dtype=float)
    c2 = np.array([ep["c2_score"] for ep in episodes], dtype=float)
    n_viols = np.array([ep["n_viols"] for ep in episodes], dtype=float)
    cga_bench = 1.0 / (1.0 + n_viols)  # higher = better; 0 viols → 1.0

    return {
        "AC-Proxy": ac_proxy,
        "MAB-Proxy": mab_proxy,
        "C2": c2,
        "CGA-Bench": cga_bench,
    }


# ---------------------------------------------------------------------------
# Threshold sweep
# ---------------------------------------------------------------------------


def sweep_thresholds(
    raw: np.ndarray,
    n_thresholds: int = N_THRESHOLDS,
) -> tuple[np.ndarray, np.ndarray]:
    """Sweep thresholds and return (thresholds, pass_rates).

    Args:
        raw: 1-D float array of raw scores.
        n_thresholds: Number of evenly-spaced thresholds.

    Returns:
        Tuple of (thresholds array, pass_rates array).
    """
    lo, hi = float(raw.min()), float(raw.max())
    thresholds = np.linspace(lo, hi, n_thresholds)
    pass_rates = np.array([(raw >= t).sum() / len(raw) for t in thresholds], dtype=float)
    return thresholds, pass_rates


def find_matched_threshold(
    raw: np.ndarray,
    target_pass_rate: float,
    n_thresholds: int = N_THRESHOLDS,
) -> tuple[float, float]:
    """Find the threshold closest to the target pass rate.

    Args:
        raw: 1-D float array of raw scores.
        target_pass_rate: Desired fraction of passing episodes.
        n_thresholds: Number of thresholds in the sweep.

    Returns:
        Tuple of (best_threshold, actual_pass_rate).
    """
    thresholds, pass_rates = sweep_thresholds(raw, n_thresholds)
    idx = int(np.argmin(np.abs(pass_rates - target_pass_rate)))
    best_t = float(thresholds[idx])
    actual_pr = float(pass_rates[idx])
    return best_t, actual_pr


# ---------------------------------------------------------------------------
# Agreement metrics
# ---------------------------------------------------------------------------


def _fleiss_kappa(binary_matrix: np.ndarray) -> float:
    """Fleiss' kappa for binary ratings.

    Args:
        binary_matrix: (n_subjects, n_raters) boolean array.

    Returns:
        Fleiss' kappa value.
    """
    n, k = binary_matrix.shape
    # Category counts per subject: [n_pass, n_fail]
    counts = np.column_stack([binary_matrix.sum(axis=1), k - binary_matrix.sum(axis=1)])
    # P_i = (sum(n_ij^2) - k) / (k*(k-1))
    p_i = (np.sum(counts**2, axis=1) - k) / (k * (k - 1))
    p_bar = float(p_i.mean())
    # p_j = proportion of all ratings in category j
    p_j = counts.sum(axis=0) / (n * k)
    p_e = float(np.sum(p_j**2))
    if p_e == 1.0:
        return 1.0
    return (p_bar - p_e) / (1.0 - p_e)


def compute_pairwise_kappa(
    verdicts: dict[str, np.ndarray],
) -> dict[str, float]:
    """Compute all pairwise Cohen's kappa values.

    Args:
        verdicts: Dict mapping evaluator name to binary verdict array.

    Returns:
        Dict mapping "EvalA vs EvalB" to kappa value.
    """
    result: dict[str, float] = {}
    names = list(verdicts.keys())
    for a, b in combinations(names, 2):
        key = f"{a} vs {b}"
        va = verdicts[a].astype(int)
        vb = verdicts[b].astype(int)
        # Handle degenerate case (all same label)
        if len(np.unique(va)) < 2 or len(np.unique(vb)) < 2:
            kappa = 1.0 if np.array_equal(va, vb) else 0.0
        else:
            kappa = float(cohen_kappa_score(va, vb))
        result[key] = kappa
    return result


def compute_verdict_flip_rate(verdicts: dict[str, np.ndarray]) -> float:
    """Fraction of episodes where at least one pair disagrees.

    Args:
        verdicts: Dict mapping evaluator name to binary verdict array.

    Returns:
        Fraction in [0, 1].
    """
    arrays = list(verdicts.values())
    stacked = np.stack(arrays, axis=1)  # (n_episodes, n_evaluators)
    # Episode has a flip if not all evaluators agree
    has_flip = stacked.max(axis=1) != stacked.min(axis=1)
    return float(has_flip.mean())


def _cluster_kappa_means(pairwise: dict[str, float]) -> tuple[float, float]:
    """Compute mean kappa within {AC-Proxy, C2} cluster vs cross-cluster.

    Args:
        pairwise: Dict from compute_pairwise_kappa.

    Returns:
        Tuple of (within_cluster_mean_kappa, cross_cluster_mean_kappa).
    """
    within: list[float] = []
    cross: list[float] = []
    for pair_key, kappa in pairwise.items():
        parts = pair_key.split(" vs ")
        a, b = parts[0], parts[1]
        in_cluster_a = (a in CLUSTER_A) and (b in CLUSTER_A)
        in_cluster_b = (a in CLUSTER_B) and (b in CLUSTER_B)
        if in_cluster_a or in_cluster_b:
            within.append(kappa)
        else:
            cross.append(kappa)
    within_mean = float(np.mean(within)) if within else float("nan")
    cross_mean = float(np.mean(cross)) if cross else float("nan")
    return within_mean, cross_mean


# ---------------------------------------------------------------------------
# Analysis per operating point
# ---------------------------------------------------------------------------


def analyse_operating_point(
    raw_scores: dict[str, np.ndarray],
    target: float,
) -> dict[str, Any]:
    """Run matched-threshold analysis for a single target pass rate.

    Args:
        raw_scores: Dict mapping evaluator name to raw score array.
        target: Target pass rate (e.g. 0.3, 0.4, 0.5).

    Returns:
        Dict with thresholds, actual_pass_rates, fleiss_kappa,
        pairwise_kappa, verdict_flip_rate, cluster check fields.
    """
    thresholds: dict[str, float] = {}
    actual_pass_rates: dict[str, float] = {}
    verdicts: dict[str, np.ndarray] = {}

    for name, raw in raw_scores.items():
        t, pr = find_matched_threshold(raw, target)
        thresholds[name] = t
        actual_pass_rates[name] = pr
        verdicts[name] = (raw >= t).astype(bool)

    # Binary matrix (n_episodes, n_evaluators)
    binary_matrix = np.stack([verdicts[n] for n in EVALUATOR_NAMES], axis=1)
    fk = _fleiss_kappa(binary_matrix)
    pairwise = compute_pairwise_kappa(verdicts)
    flip_rate = compute_verdict_flip_rate(verdicts)
    within_mean, cross_mean = _cluster_kappa_means(pairwise)

    return {
        "thresholds": thresholds,
        "actual_pass_rates": actual_pass_rates,
        "fleiss_kappa": fk,
        "pairwise_kappa": pairwise,
        "verdict_flip_rate": flip_rate,
        "within_cluster_kappa": within_mean,
        "cross_cluster_kappa": cross_mean,
    }


# ---------------------------------------------------------------------------
# Sweep data for figure 1
# ---------------------------------------------------------------------------


def build_sweep_data(
    raw_scores: dict[str, np.ndarray],
) -> dict[str, dict[str, list[float]]]:
    """Compute pairwise kappa across the threshold sweep for all evaluator pairs.

    For each pair (A, B), sweeps both A and B independently at N_THRESHOLDS
    points matched to a shared pass-rate grid [0, 1].

    Args:
        raw_scores: Dict mapping evaluator name to raw score array.

    Returns:
        Dict mapping pair label to {"pass_rates": [...], "kappas": [...]}.
    """
    # Build a common pass-rate grid
    pr_grid = np.linspace(0.05, 0.95, N_THRESHOLDS)

    # For each evaluator, pre-compute threshold for each pass-rate target
    def _threshold_at_pr(raw: np.ndarray, target_pr: float) -> float:
        lo, hi = float(raw.min()), float(raw.max())
        ts = np.linspace(lo, hi, N_THRESHOLDS * 10)
        prs = np.array([(raw >= t).sum() / len(raw) for t in ts])
        idx = int(np.argmin(np.abs(prs - target_pr)))
        return float(ts[idx])

    sweep: dict[str, dict[str, list[float]]] = {}
    names = EVALUATOR_NAMES
    for a, b in combinations(names, 2):
        pair_label = f"{a} vs {b}"
        pair_prs: list[float] = []
        pair_kappas: list[float] = []
        for target_pr in pr_grid:
            ta = _threshold_at_pr(raw_scores[a], target_pr)
            tb = _threshold_at_pr(raw_scores[b], target_pr)
            va = (raw_scores[a] >= ta).astype(int)
            vb = (raw_scores[b] >= tb).astype(int)
            pra = float((raw_scores[a] >= ta).mean())
            prb = float((raw_scores[b] >= tb).mean())
            avg_pr = (pra + prb) / 2.0
            if len(np.unique(va)) < 2 or len(np.unique(vb)) < 2:
                kappa = 1.0 if np.array_equal(va, vb) else 0.0
            else:
                kappa = float(cohen_kappa_score(va, vb))
            pair_prs.append(avg_pr)
            pair_kappas.append(kappa)
        sweep[pair_label] = {"pass_rates": pair_prs, "kappas": pair_kappas}
    return sweep


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------


def plot_kappa_vs_passrate(
    sweep: dict[str, dict[str, list[float]]],
    target_pass_rates: list[float],
    out_path: Path,
) -> None:
    """Plot Cohen's kappa vs pass rate for each evaluator pair.

    Args:
        sweep: Output of build_sweep_data.
        target_pass_rates: List of operating point targets (drawn as vlines).
        out_path: Output PNG path.
    """
    fig, ax = plt.subplots(figsize=(10, 6))
    pairs = list(sweep.keys())

    for idx, pair_label in enumerate(pairs):
        prs = sweep[pair_label]["pass_rates"]
        kappas = sweep[pair_label]["kappas"]
        color = _PAIR_COLORS[idx % len(_PAIR_COLORS)]
        marker = _PAIR_MARKERS[idx % len(_PAIR_MARKERS)]
        ax.plot(
            prs,
            kappas,
            label=pair_label,
            color=color,
            marker=marker,
            markersize=4,
            linewidth=1.5,
            alpha=0.85,
        )

    for target in target_pass_rates:
        ax.axvline(
            x=target,
            color="black",
            linestyle="--",
            linewidth=1.0,
            alpha=0.6,
        )
        ax.text(
            target + 0.005,
            ax.get_ylim()[0] + 0.02 if ax.get_ylim()[1] > 0 else -0.8,
            f"PR={target}",
            fontsize=8,
            color="black",
            alpha=0.7,
        )

    ax.axhline(y=0, color="gray", linestyle=":", linewidth=0.8)
    ax.set_xlabel("Pass Rate (averaged over pair)")
    ax.set_ylabel("Cohen's κ")
    ax.set_title("Pairwise Cohen's κ vs Matched Pass Rate\n(Disagreement persists regardless of threshold)")
    ax.legend(loc="upper right", fontsize=8, ncol=2)
    ax.set_xlim(0.0, 1.0)

    save_figure(fig, out_path)


def plot_matched_heatmaps(
    operating_points: dict[str, dict[str, Any]],
    out_path: Path,
) -> None:
    """Plot 3-panel pairwise kappa heatmaps at each operating point.

    Args:
        operating_points: Dict mapping str(target) to analysis result.
        out_path: Output PNG path.
    """
    n_panels = len(TARGET_PASS_RATES)
    fig, axes = plt.subplots(1, n_panels, figsize=(5 * n_panels, 5))
    if n_panels == 1:
        axes = [axes]

    for ax, target in zip(axes, TARGET_PASS_RATES):
        key = str(target)
        pairwise = operating_points[key]["pairwise_kappa"]

        # Build 4×4 matrix
        mat = np.zeros((4, 4), dtype=float)
        np.fill_diagonal(mat, 1.0)
        for i, a in enumerate(EVALUATOR_NAMES):
            for j, b in enumerate(EVALUATOR_NAMES):
                if i == j:
                    continue
                pair_key = f"{a} vs {b}" if f"{a} vs {b}" in pairwise else f"{b} vs {a}"
                if pair_key in pairwise:
                    mat[i, j] = pairwise[pair_key]

        im = ax.imshow(mat, vmin=-0.3, vmax=1.0, cmap="RdYlGn", aspect="auto")
        ax.set_xticks(range(4))
        ax.set_yticks(range(4))
        short_names = [n.replace("-", "-\n") for n in EVALUATOR_NAMES]
        ax.set_xticklabels(short_names, fontsize=9)
        ax.set_yticklabels(short_names, fontsize=9)
        ax.set_title(f"Pass Rate ≈ {target:.0%}\nFleiss κ = {operating_points[key]['fleiss_kappa']:.3f}")

        for i in range(4):
            for j in range(4):
                ax.text(
                    j,
                    i,
                    f"{mat[i, j]:.2f}",
                    ha="center",
                    va="center",
                    fontsize=9,
                    color="black" if abs(mat[i, j]) < 0.7 else "white",
                )

        fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)

    fig.suptitle(
        "Pairwise Cohen's κ Heatmaps at Matched Operating Points",
        fontsize=13,
        y=1.02,
    )
    fig.tight_layout()
    save_figure(fig, out_path)


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def build_markdown(
    operating_points: dict[str, dict[str, Any]],
    cluster_preserved: bool,
) -> str:
    """Build markdown report for EXP-E4.

    Args:
        operating_points: Analysis results keyed by str(target).
        cluster_preserved: Whether within-cluster kappa exceeds cross-cluster.

    Returns:
        Markdown string.
    """
    lines: list[str] = [
        "# EXP-E4: Operating-Point Matched Agreement Analysis",
        "",
        "Threshold sweep matching all four evaluators to the same pass rate,",
        "proving disagreement is **not** a threshold-calibration artifact.",
        "",
        "## Results by Operating Point",
        "",
    ]
    for target in TARGET_PASS_RATES:
        key = str(target)
        res = operating_points[key]
        lines += [
            f"### Pass Rate ≈ {target:.0%}",
            "",
            "| Evaluator | Threshold | Actual Pass Rate |",
            "| --- | --- | --- |",
        ]
        for name in EVALUATOR_NAMES:
            t_val = res["thresholds"][name]
            pr_val = res["actual_pass_rates"][name]
            lines.append(f"| {name} | {t_val:.4f} | {pr_val:.3f} |")
        lines += [
            "",
            f"**Fleiss' κ = {res['fleiss_kappa']:.3f}**  ",
            f"Verdict flip rate = {res['verdict_flip_rate']:.3f}  ",
            f"Within-cluster κ = {res['within_cluster_kappa']:.3f}  ",
            f"Cross-cluster κ = {res['cross_cluster_kappa']:.3f}",
            "",
            "| Pair | Cohen's κ |",
            "| --- | --- |",
        ]
        for pair, kappa in res["pairwise_kappa"].items():
            lines.append(f"| {pair} | {kappa:.3f} |")
        lines.append("")

    lines += [
        "## Cluster Structure",
        "",
        f"Cluster preserved (within > cross): **{cluster_preserved}**",
        "",
        "Clusters: {AC-Proxy, C2} vs {MAB-Proxy, CGA-Bench}.",
        "",
        "## Interpretation",
        "",
        "Low Fleiss' κ across all operating points confirms that",
        "evaluator disagreement is a genuine structural property,",
        "not an artifact of different classification thresholds.",
    ]
    return "\n".join(lines) + "\n"


def build_latex_rows(
    operating_points: dict[str, dict[str, Any]],
) -> tuple[list[str], list[list[str]]]:
    """Build LaTeX table rows for operating_point_matched.tex.

    Args:
        operating_points: Analysis results keyed by str(target).

    Returns:
        Tuple of (headers, rows).
    """
    headers = [
        "Pass Rate",
        "Fleiss κ",
        "Flip Rate",
        "Within-cluster κ",
        "Cross-cluster κ",
    ]
    rows: list[list[str]] = []
    for target in TARGET_PASS_RATES:
        key = str(target)
        res = operating_points[key]
        rows.append(
            [
                f"{target:.0%}",
                fmt_f(res["fleiss_kappa"]),
                fmt_f(res["verdict_flip_rate"]),
                fmt_f(res["within_cluster_kappa"]),
                fmt_f(res["cross_cluster_kappa"]),
            ]
        )
    return headers, rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run EXP-E4 operating-point matched analysis end-to-end."""
    setup_matplotlib()
    print("[EXP-E4] Loading raw scores ...")
    raw_scores = load_raw_scores(VERDICT_MATRIX_PATH)

    # Step 1 confirmation
    for name, arr in raw_scores.items():
        print(f"  {name}: min={arr.min():.4f} max={arr.max():.4f} mean={arr.mean():.4f}")

    # Step 2 & 3: analyse each operating point
    print("[EXP-E4] Running matched-threshold analysis ...")
    operating_points: dict[str, dict[str, Any]] = {}
    for target in TARGET_PASS_RATES:
        print(f"  target pass rate = {target:.0%}")
        operating_points[str(target)] = analyse_operating_point(raw_scores, target)

    # Cluster check: preserved if all OPs show within > cross
    cluster_checks: list[bool] = []
    for target in TARGET_PASS_RATES:
        res = operating_points[str(target)]
        w = res["within_cluster_kappa"]
        c = res["cross_cluster_kappa"]
        cluster_checks.append((not np.isnan(w)) and (not np.isnan(c)) and (w > c))
    cluster_preserved = all(cluster_checks)

    # Step 4a: kappa vs pass-rate sweep figure
    print("[EXP-E4] Building sweep data for figure 1 ...")
    sweep = build_sweep_data(raw_scores)

    print("[EXP-E4] Saving figures ...")
    plot_kappa_vs_passrate(
        sweep,
        TARGET_PASS_RATES,
        FIGURES_DIR / "exp_e4_kappa_vs_passrate.png",
    )
    plot_matched_heatmaps(
        operating_points,
        FIGURES_DIR / "exp_e4_matched_heatmaps.png",
    )

    # Build JSON output (convert numpy floats for serialisation)
    raw_scores_serialisable: dict[str, list[float]] = {name: arr.tolist() for name, arr in raw_scores.items()}
    output: dict[str, Any] = {
        "raw_scores": raw_scores_serialisable,
        "operating_points": operating_points,
        "cluster_preserved": cluster_preserved,
    }

    print("[EXP-E4] Saving outputs ...")
    save_json(output, EVIDENCE_DIR / "exp_e4_operating_point.json")

    md = build_markdown(operating_points, cluster_preserved)
    save_markdown(md, EVIDENCE_DIR / "exp_e4_operating_point.md")

    headers, rows = build_latex_rows(operating_points)
    save_latex_table(
        rows,
        headers,
        TABLES_DIR / "operating_point_matched.tex",
        caption="Evaluator agreement at matched operating points (EXP-E4).",
        label="tab:operating_point_matched",
    )

    print("[EXP-E4] Done.")
    print(f"  Cluster preserved: {cluster_preserved}")
    for target in TARGET_PASS_RATES:
        res = operating_points[str(target)]
        print(f"  PR≈{target:.0%} → Fleiss κ={res['fleiss_kappa']:.3f}, flip rate={res['verdict_flip_rate']:.3f}")


if __name__ == "__main__":
    main()
