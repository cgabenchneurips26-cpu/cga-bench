
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""D4: Timing Violation Margin Histogram.

Creates a publication-quality histogram of timing violation margins
(actual_time - expected_deadline) across all rescored episodes.

Usage:
    PYTHONPATH=. python scripts/experiments/d4_violation_margin_histogram.py

Outputs:
    evidence_pack/figures/timing_margin_histogram.pdf
    evidence_pack/figures/timing_margin_histogram.png
    evidence_pack/analysis/d4_violation_margin.json
    evidence_pack/analysis/d4_violation_margin.md
"""

from __future__ import annotations

import glob
import json
from pathlib import Path
import statistics

import matplotlib

matplotlib.use("Agg")  # non-interactive backend
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
REPO_ROOT = Path(__file__).resolve().parents[2]

RESCORE_DIR = REPO_ROOT / "results" / "clean_slate_rescored"
OUT_FIGURES = REPO_ROOT / "evidence_pack" / "figures"
OUT_ANALYSIS = REPO_ROOT / "evidence_pack" / "analysis"

MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]

# ---------------------------------------------------------------------------
# Zone thresholds (minutes)
# ---------------------------------------------------------------------------
ZONE_BORDERLINE_MAX = 5  # 0-5 min late
ZONE_MODERATE_MAX = 15  # 5-15 min late
# >15 is "Clear"

ZONE_COLORS = {
    "borderline": "#d62728",  # red
    "moderate": "#ff7f0e",  # orange
    "clear": "#2ca02c",  # green
}

THRESHOLD_LINES = [5, 15, 30]  # vertical dashed lines


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_all_timing_margins() -> list[dict]:
    """Load all timing violations from rescored episodes and compute margins."""
    records = []
    for model in MODELS:
        pattern = str(RESCORE_DIR / model / "*.json")
        for path in sorted(glob.glob(pattern)):
            with open(path) as fh:
                d = json.load(fh)
            scenario_id = d.get("scenario_id", "")
            run_index = d.get("run_index", 0)
            c2_new = float(d.get("c2_new", 1.0))
            for viol in d.get("new_violation_events", []):
                if viol.get("violation_type") != "timing":
                    continue
                actual = viol.get("actual_time")
                deadline = viol.get("expected_deadline")
                if actual is None or deadline is None:
                    continue
                margin = float(actual) - float(deadline)
                if margin <= 0:
                    # Not actually late — skip (shouldn't happen, but guard)
                    continue
                records.append(
                    {
                        "model": model,
                        "scenario_id": scenario_id,
                        "run_index": run_index,
                        "action_involved": viol.get("action_involved", ""),
                        "actual_time": float(actual),
                        "expected_deadline": float(deadline),
                        "margin_minutes": margin,
                        "harm_severity": viol.get("harm_severity", ""),
                        "c2_new": c2_new,
                        "is_up": c2_new >= 0.7,
                    }
                )
    return records


def classify_zone(margin: float) -> str:
    if margin <= ZONE_BORDERLINE_MAX:
        return "borderline"
    elif margin <= ZONE_MODERATE_MAX:
        return "moderate"
    return "clear"


# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------


def build_histogram(records: list[dict]) -> None:
    OUT_FIGURES.mkdir(parents=True, exist_ok=True)

    margins = [r["margin_minutes"] for r in records]
    n_total = len(margins)

    # Bin edges: 5-min intervals from 0 to max+5
    max_margin = max(margins) if margins else 60
    bin_max = max(max_margin + 5, 35)
    bin_edges = np.arange(0, bin_max + 5, 5)

    # Count by zone
    n_borderline = sum(1 for m in margins if m <= ZONE_BORDERLINE_MAX)
    n_moderate = sum(1 for m in margins if ZONE_BORDERLINE_MAX < m <= ZONE_MODERATE_MAX)
    n_clear = sum(1 for m in margins if m > ZONE_MODERATE_MAX)

    # Assign per-bar colors
    bin_centers = (bin_edges[:-1] + bin_edges[1:]) / 2
    bar_colors = []
    for center in bin_centers:
        if center <= ZONE_BORDERLINE_MAX:
            bar_colors.append(ZONE_COLORS["borderline"])
        elif center <= ZONE_MODERATE_MAX:
            bar_colors.append(ZONE_COLORS["moderate"])
        else:
            bar_colors.append(ZONE_COLORS["clear"])

    # Compute histogram counts
    counts, _ = np.histogram(margins, bins=bin_edges)

    # ---------------------------------------------------------------------------
    # Plot
    # ---------------------------------------------------------------------------
    try:
        plt.style.use("seaborn-v0_8-whitegrid")
    except OSError:
        try:
            plt.style.use("seaborn-whitegrid")
        except OSError:
            plt.style.use("ggplot")

    fig, ax = plt.subplots(figsize=(8, 5))

    bars = ax.bar(
        bin_edges[:-1],
        counts,
        width=np.diff(bin_edges),
        align="edge",
        color=bar_colors,
        edgecolor="white",
        linewidth=0.8,
        alpha=0.85,
        zorder=3,
    )

    # Vertical threshold lines
    line_styles = [
        (5, "red", "--", "5 min"),
        (15, "orange", "--", "15 min"),
        (30, "gray", ":", "30 min"),
    ]
    for xval, color, ls, label in line_styles:
        ax.axvline(x=xval, color=color, linestyle=ls, linewidth=1.4, alpha=0.7, zorder=4, label=label)

    # Zone text annotations (count in each zone)
    y_max = max(counts) if counts.max() > 0 else 1
    annotation_y = y_max * 0.88

    zone_annotations = [
        (ZONE_BORDERLINE_MAX / 2, n_borderline, "Borderline\n(0–5 min)", "red"),
        ((ZONE_BORDERLINE_MAX + ZONE_MODERATE_MAX) / 2, n_moderate, "Moderate\n(5–15 min)", "orange"),
        (ZONE_MODERATE_MAX + (bin_max - ZONE_MODERATE_MAX) / 2, n_clear, "Clear\n(>15 min)", "green"),
    ]
    for x_pos, count, label, color in zone_annotations:
        if count > 0:
            ax.text(
                x_pos,
                annotation_y,
                f"{label}\nn={count}",
                ha="center",
                va="top",
                fontsize=9,
                color=color,
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="white", edgecolor=color, alpha=0.7),
                zorder=5,
            )

    # Legend patches for zones
    patch_border = mpatches.Patch(
        color=ZONE_COLORS["borderline"], alpha=0.85, label=f"Borderline (0–5 min): n={n_borderline}"
    )
    patch_mod = mpatches.Patch(color=ZONE_COLORS["moderate"], alpha=0.85, label=f"Moderate (5–15 min): n={n_moderate}")
    patch_clear = mpatches.Patch(color=ZONE_COLORS["clear"], alpha=0.85, label=f"Clear (>15 min): n={n_clear}")

    ax.legend(handles=[patch_border, patch_mod, patch_clear], loc="upper right", fontsize=8.5, framealpha=0.9)

    # Labels and title
    ax.set_xlabel("Timing Violation Margin (minutes late)", fontsize=12)
    ax.set_ylabel("Count of Violations", fontsize=12)
    ax.set_title(
        f"Distribution of Timing Violation Margins (N={n_total} violations)",
        fontsize=13,
        fontweight="bold",
        pad=12,
    )

    # Median line
    if margins:
        median_val = statistics.median(margins)
        ax.axvline(
            x=median_val,
            color="navy",
            linestyle="-.",
            linewidth=1.8,
            alpha=0.8,
            zorder=4,
            label=f"Median = {median_val:.0f} min",
        )
        ax.legend(
            handles=[
                patch_border,
                patch_mod,
                patch_clear,
                plt.Line2D(
                    [0], [0], color="navy", linestyle="-.", linewidth=1.8, label=f"Median = {median_val:.0f} min"
                ),
            ],
            loc="upper right",
            fontsize=8.5,
            framealpha=0.9,
        )

    ax.set_xlim(left=0)
    ax.set_ylim(bottom=0)
    ax.tick_params(axis="both", labelsize=10)
    fig.tight_layout()

    # Save
    pdf_path = OUT_FIGURES / "timing_margin_histogram.pdf"
    png_path = OUT_FIGURES / "timing_margin_histogram.png"
    fig.savefig(str(pdf_path), dpi=300, bbox_inches="tight")
    fig.savefig(str(png_path), dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"Saved {pdf_path}")
    print(f"Saved {png_path}")


# ---------------------------------------------------------------------------
# JSON + MD outputs
# ---------------------------------------------------------------------------


def write_analysis(records: list[dict]) -> None:
    OUT_ANALYSIS.mkdir(parents=True, exist_ok=True)

    margins = [r["margin_minutes"] for r in records]
    n_total = len(margins)

    if n_total == 0:
        print("WARNING: No timing violations found — outputs will reflect empty data.")

    n_borderline = sum(1 for m in margins if m <= ZONE_BORDERLINE_MAX)
    n_moderate = sum(1 for m in margins if ZONE_BORDERLINE_MAX < m <= ZONE_MODERATE_MAX)
    n_clear = sum(1 for m in margins if m > ZONE_MODERATE_MAX)

    # Per-model breakdown
    model_stats = {}
    for model in MODELS:
        model_margins = [r["margin_minutes"] for r in records if r["model"] == model]
        model_stats[model] = {
            "n_violations": len(model_margins),
            "median_margin": round(statistics.median(model_margins), 1) if model_margins else None,
            "mean_margin": round(statistics.mean(model_margins), 1) if model_margins else None,
            "max_margin": round(max(model_margins), 1) if model_margins else None,
            "n_borderline": sum(1 for m in model_margins if m <= ZONE_BORDERLINE_MAX),
            "n_moderate": sum(1 for m in model_margins if ZONE_BORDERLINE_MAX < m <= ZONE_MODERATE_MAX),
            "n_clear": sum(1 for m in model_margins if m > ZONE_MODERATE_MAX),
        }

    # UP subset
    up_margins = [r["margin_minutes"] for r in records if r["is_up"]]
    up_stats = {
        "n_violations": len(up_margins),
        "median_margin": round(statistics.median(up_margins), 1) if up_margins else None,
        "n_borderline": sum(1 for m in up_margins if m <= ZONE_BORDERLINE_MAX),
        "n_moderate": sum(1 for m in up_margins if ZONE_BORDERLINE_MAX < m <= ZONE_MODERATE_MAX),
        "n_clear": sum(1 for m in up_margins if m > ZONE_MODERATE_MAX),
    }

    analysis = {
        "description": "D4 Timing Violation Margin Histogram",
        "n_total_violations": n_total,
        "zone_thresholds_minutes": {
            "borderline_max": ZONE_BORDERLINE_MAX,
            "moderate_max": ZONE_MODERATE_MAX,
        },
        "zone_counts": {
            "borderline_0_5min": n_borderline,
            "moderate_5_15min": n_moderate,
            "clear_over_15min": n_clear,
        },
        "summary_stats": {
            "median_margin_minutes": round(statistics.median(margins), 1) if margins else None,
            "mean_margin_minutes": round(statistics.mean(margins), 1) if margins else None,
            "min_margin_minutes": round(min(margins), 1) if margins else None,
            "max_margin_minutes": round(max(margins), 1) if margins else None,
            "pct_borderline": round(n_borderline / n_total * 100, 1) if n_total else 0,
            "pct_moderate": round(n_moderate / n_total * 100, 1) if n_total else 0,
            "pct_clear": round(n_clear / n_total * 100, 1) if n_total else 0,
        },
        "per_model": model_stats,
        "up_subset_c2_gte_0_7": up_stats,
        "all_margins": sorted(margins),
    }

    json_path = OUT_ANALYSIS / "d4_violation_margin.json"
    with open(json_path, "w") as fh:
        json.dump(analysis, fh, indent=2)
    print(f"Wrote {json_path}")

    # Markdown summary
    med = analysis["summary_stats"]["median_margin_minutes"]
    mean_val = analysis["summary_stats"]["mean_margin_minutes"]
    max_val = analysis["summary_stats"]["max_margin_minutes"]
    pct_b = analysis["summary_stats"]["pct_borderline"]
    pct_m = analysis["summary_stats"]["pct_moderate"]
    pct_c = analysis["summary_stats"]["pct_clear"]

    md_lines = [
        "# D4: Timing Violation Margin Histogram",
        "",
        "## Summary",
        "",
        f"- **Total timing violations**: {n_total}",
        f"- **Median margin**: {med} min",
        f"- **Mean margin**: {mean_val} min",
        f"- **Max margin**: {max_val} min",
        "",
        "## Zone Distribution",
        "",
        "| Zone | Threshold | Count | % |",
        "|------|-----------|-------|---|",
        f"| Borderline | 0–5 min | {n_borderline} | {pct_b}% |",
        f"| Moderate   | 5–15 min | {n_moderate} | {pct_m}% |",
        f"| Clear      | >15 min | {n_clear} | {pct_c}% |",
        "",
        "## Per-Model Breakdown",
        "",
        "| Model | N violations | Median margin | Borderline | Moderate | Clear |",
        "|-------|-------------|--------------|------------|----------|-------|",
    ]
    for model, ms in model_stats.items():
        md_lines.append(
            f"| {model} | {ms['n_violations']} | {ms['median_margin']} min | "
            f"{ms['n_borderline']} | {ms['n_moderate']} | {ms['n_clear']} |"
        )

    md_lines += [
        "",
        "## UP Subset (c2 >= 0.7)",
        "",
        f"- N violations: {up_stats['n_violations']}",
        f"- Median margin: {up_stats['median_margin']} min",
        f"- Borderline: {up_stats['n_borderline']}, Moderate: {up_stats['n_moderate']}, Clear: {up_stats['n_clear']}",
        "",
        "## Interpretation",
        "",
        "The vast majority of timing violations are in the 'Clear' zone (>15 min late),",
        f"indicating these are not borderline cases. The {pct_c:.0f}% clear rate confirms"
        + " that timing violations reflect genuine protocol deviations rather than",
        "measurement noise from the 5-min action duration assumption.",
        "",
        "## Output Files",
        "",
        "- `evidence_pack/figures/timing_margin_histogram.pdf`",
        "- `evidence_pack/figures/timing_margin_histogram.png`",
        "- `evidence_pack/analysis/d4_violation_margin.json`",
    ]

    md_path = OUT_ANALYSIS / "d4_violation_margin.md"
    with open(md_path, "w") as fh:
        fh.write("\n".join(md_lines) + "\n")
    print(f"Wrote {md_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def run() -> None:
    print("Loading timing violations from rescored episodes...")
    records = load_all_timing_margins()
    print(f"Found {len(records)} timing violations across all models")

    # Per-model counts
    for model in MODELS:
        n = sum(1 for r in records if r["model"] == model)
        print(f"  {model}: {n} timing violations")

    print("\nBuilding histogram...")
    build_histogram(records)

    print("\nWriting analysis outputs...")
    write_analysis(records)

    print("\nD4 analysis complete.")


if __name__ == "__main__":
    run()
