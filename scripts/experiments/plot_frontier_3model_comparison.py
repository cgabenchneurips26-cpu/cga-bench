"""V7.3 frontier 3-model rank-reversal visualization.

Shows that the 3 endpoints (Opus / GPT-5.4 / Sonnet) rank differently across
3 metrics (TCC pass, Compliance mean, Mean violations) — within-vendor
inverse-scaling for Anthropic + cross-metric rank reversal.

Outputs:
  - paper/figures/frontier_3model_rankreversal.pdf
  - paper/figures/frontier_3model_rankreversal.png
"""

from __future__ import annotations

import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "evidence_pack" / "analysis" / "verdict_matrix_v73_frontier.json"
OUT_DIR = REPO / "paper" / "figures"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Hardcoded compatible-with-existing-paper hex palette (Anthropic warm/OpenAI cool).
COLORS = {
    "claude_opus47": "#C84B31",  # Anthropic warm-red flagship
    "gpt54": "#3B7DD8",  # OpenAI blue flagship
    "claude_sonnet46": "#E69138",  # Anthropic warm-orange mid
    "gpt54mini": "#7DB3E8",  # OpenAI light-blue mid
}
LABELS = {
    "claude_opus47": "Opus 4.7",
    "gpt54": "GPT-5.4",
    "claude_sonnet46": "Sonnet 4.6",
    "gpt54mini": "GPT-5.4-mini",
}
ORDER_BY_TIER = ["claude_opus47", "gpt54", "claude_sonnet46", "gpt54mini"]


def _load_stats() -> dict:
    data = json.load(open(SRC))
    pm = data["per_model"]
    # Re-derive mean violations from per_episode (per_model summary doesn't store it directly)
    eps = data["per_episode"]
    viol_by_model: dict[str, list[int]] = {m: [] for m in pm}
    for e in eps:
        viol_by_model[e["model"]].append(e["total_violations"])
    return {
        "tcc": {m: 100 * pm[m]["tcc_pass_rate"] for m in pm},
        "compl_mean": {m: pm[m]["compl_mean"] for m in pm},
        "compl_std": {m: pm[m]["compl_std"] for m in pm},
        "viol_mean": {m: float(np.mean(viol_by_model[m])) for m in pm},
        "n": {m: pm[m]["n"] for m in pm},
    }


def _add_rank_badge(ax, x: float, y: float, rank: int, color: str = "#222"):
    ax.annotate(
        f"#{rank}",
        (x, y),
        textcoords="offset points",
        xytext=(0, 8),
        ha="center",
        fontsize=10,
        fontweight="bold",
        color=color,
    )


def plot_grouped_bars(stats: dict) -> None:
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2), constrained_layout=True)

    metrics = [
        ("tcc", "TCC pass rate (%)", "higher = better", False),
        ("compl_mean", "Compliance mean", "higher = better", False),
        ("viol_mean", "Mean violations / episode", "lower = better", True),
    ]

    for ax, (key, title, hint, lower_better) in zip(axes, metrics):
        vals = stats[key]
        # Rank: lower_better → ascending; otherwise descending
        ranked = sorted(vals.items(), key=lambda kv: kv[1], reverse=not lower_better)
        rank_map = {m: r + 1 for r, (m, _) in enumerate(ranked)}

        x_pos = np.arange(len(ORDER_BY_TIER))
        heights = [vals[m] for m in ORDER_BY_TIER]
        colors = [COLORS[m] for m in ORDER_BY_TIER]
        bars = ax.bar(
            x_pos,
            heights,
            color=colors,
            edgecolor="#222",
            linewidth=0.8,
            width=0.62,
        )

        for bar, m in zip(bars, ORDER_BY_TIER):
            h = bar.get_height()
            ax.text(
                bar.get_x() + bar.get_width() / 2,
                h * 1.01,
                f"{h:.{2 if key != 'tcc' else 1}f}",
                ha="center",
                va="bottom",
                fontsize=10,
            )
            _add_rank_badge(
                ax,
                bar.get_x() + bar.get_width() / 2,
                h * 1.06 + (0.05 if key == "compl_mean" else 0),
                rank_map[m],
            )

        # Highlight rank-1 winner
        winner_m = ranked[0][0]
        winner_idx = ORDER_BY_TIER.index(winner_m)
        bars[winner_idx].set_edgecolor("#000")
        bars[winner_idx].set_linewidth(2.2)

        ax.set_xticks(x_pos)
        ax.set_xticklabels([LABELS[m] for m in ORDER_BY_TIER], rotation=10)
        ax.set_title(f"{title}\n({hint})", fontsize=11)
        ax.spines[["top", "right"]].set_visible(False)
        ax.tick_params(axis="y", labelsize=9)
        ax.grid(axis="y", linestyle=":", alpha=0.5)

        ymin, ymax = min(heights), max(heights)
        pad = (ymax - ymin) * 0.18 + (1 if key == "tcc" else 0.05)
        if lower_better:
            ax.set_ylim(0, ymax + pad)
        else:
            ax.set_ylim(max(0, ymin - pad * 0.5), ymax + pad)

    fig.suptitle(
        "V7.3 frontier 4-endpoint comparison across metrics  (n $\\approx$ 1{,}254 episodes per model)",
        fontsize=12,
        fontweight="bold",
        y=1.04,
    )

    pdf_path = OUT_DIR / "frontier_3model_rankreversal.pdf"
    png_path = OUT_DIR / "frontier_3model_rankreversal.png"
    fig.savefig(pdf_path, bbox_inches="tight", dpi=200)
    fig.savefig(png_path, bbox_inches="tight", dpi=200)
    print(f"PDF: {pdf_path}")
    print(f"PNG: {png_path}")


def plot_pairwise(stats: dict) -> None:
    """Pairwise comparison panel: 2 controlled pairs × 3 metrics = 6-cell grid.

    Pair 1: Cross-vendor flagship  (Opus 4.7 vs GPT-5.4)  — vendor differs, capacity matched
    Pair 2: Within-Anthropic scale (Opus 4.7 vs Sonnet 4.6) — vendor matched, capacity differs

    GPT-5.4 vs Sonnet-4.6 omitted: confounded (vendor AND capacity both differ).
    """
    pairs = [
        ("claude_opus47", "gpt54", "Cross-vendor flagship\n(family differs, capacity matched)"),
        ("claude_sonnet46", "gpt54mini", "Cross-vendor mid\n(family differs, capacity matched)"),
        ("claude_opus47", "claude_sonnet46", "Within-Anthropic scaling\n(family matched, capacity differs)"),
        ("gpt54", "gpt54mini", "Within-OpenAI scaling\n(family matched, capacity differs)"),
    ]
    metrics = [
        ("tcc", "TCC pass (%)", False),
        ("compl_mean", "Compliance mean", False),
        ("viol_mean", "Mean violations", True),
    ]

    fig, axes = plt.subplots(4, 3, figsize=(13, 14))

    for row, (m1, m2, row_label) in enumerate(pairs):
        for col, (mk, mlabel, lower_better) in enumerate(metrics):
            ax = axes[row, col]
            v1, v2 = stats[mk][m1], stats[mk][m2]
            heights = [v1, v2]
            colors = [COLORS[m1], COLORS[m2]]
            x_pos = [0, 1]
            bars = ax.bar(x_pos, heights, color=colors, edgecolor="#222", linewidth=1.0, width=0.55)

            # Annotate values + winner arrow
            for x, h in zip(x_pos, heights):
                ax.text(x, h * 1.02, f"{h:.{2 if mk != 'tcc' else 1}f}", ha="center", fontsize=10)
            winner_idx = (0 if v1 < v2 else 1) if lower_better else (0 if v1 > v2 else 1)
            bars[winner_idx].set_edgecolor("#000")
            bars[winner_idx].set_linewidth(2.5)

            delta = abs(v1 - v2)
            arrow = "←" if winner_idx == 0 else "→"
            ax.text(
                0.5,
                0.92,
                f"Δ {delta:.{2 if mk != 'tcc' else 1}f}  {arrow}",
                transform=ax.transAxes,
                ha="center",
                fontsize=11,
                fontweight="bold",
                color="#333",
                bbox=dict(facecolor="white", edgecolor="#ccc", boxstyle="round,pad=0.2"),
            )

            ax.set_xticks(x_pos)
            ax.set_xticklabels([LABELS[m1], LABELS[m2]], fontsize=10)
            if row == 0:
                ax.set_title(mlabel, fontsize=11, fontweight="bold", pad=8)
            if col == 0:
                ax.set_ylabel(row_label, fontsize=10, fontweight="bold", labelpad=8)
            ax.spines[["top", "right"]].set_visible(False)
            ax.tick_params(axis="y", labelsize=9)
            ax.grid(axis="y", linestyle=":", alpha=0.4)

            ymin, ymax = min(heights), max(heights)
            ymax_pad = ymax * 1.18 if not lower_better else ymax * 1.22
            ymin_pad = max(0, ymin * 0.88 if not lower_better else 0)
            ax.set_ylim(ymin_pad, ymax_pad)

    fig.suptitle(
        "V7.3 frontier 2$\\times$2 factorial: vendor (Anthropic/OpenAI) $\\times$ capacity (flagship/mid)",
        fontsize=13,
        fontweight="bold",
        y=0.99,
    )
    fig.tight_layout(rect=[0, 0, 1, 0.97])

    pdf_path = OUT_DIR / "frontier_3model_pairwise.pdf"
    png_path = OUT_DIR / "frontier_3model_pairwise.png"
    fig.savefig(pdf_path, bbox_inches="tight", dpi=200)
    fig.savefig(png_path, bbox_inches="tight", dpi=200)
    print(f"PDF: {pdf_path}")
    print(f"PNG: {png_path}")


def main() -> None:
    stats = _load_stats()
    print("Stats:")
    for k, v in stats.items():
        if k != "n":
            print(f"  {k}: " + ", ".join(f"{LABELS[m]}={v[m]:.3f}" for m in ORDER_BY_TIER))

    plot_grouped_bars(stats)
    plot_pairwise(stats)


if __name__ == "__main__":
    main()
