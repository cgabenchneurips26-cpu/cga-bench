"""
Radar chart generator for CGA-Bench C1-C5 criterion scores.
Produces academic-style figures suitable for publication.
"""

import json
import logging
import matplotlib
matplotlib.use('Agg')  # non-interactive backend
import matplotlib.pyplot as plt
import numpy as np
from pathlib import Path

logger = logging.getLogger(__name__)

# Colorblind-friendly palette (Wong 2011)
_COLORS = [
    "#0072B2",  # blue
    "#D55E00",  # vermillion
    "#009E73",  # green
    "#CC79A7",  # pink
    "#56B4E9",  # sky blue
    "#E69F00",  # orange
    "#F0E442",  # yellow
    "#000000",  # black
]

_LINE_STYLES = ["solid", "dashed", "dotted", "dashdot",
                (0, (3, 1, 1, 1)), (0, (5, 2)), (0, (1, 1)), "solid"]

# Keyword → domain classification (checked in order)
_DOMAIN_KEYWORDS = [
    ("sepsis",   "Sepsis"),
    ("dka",      "Metabolic"),
    ("aki",      "Renal"),
    ("contrast", "Renal"),
    ("stemi",    "Cardiac"),
    ("chest",    "Cardiac"),
    ("stroke",   "Neuro"),
]


def _classify_domain(scenario_id: str) -> str:
    """Auto-classify a scenario_id string into a domain group by keyword."""
    lower = scenario_id.lower()
    for keyword, domain in _DOMAIN_KEYWORDS:
        if keyword in lower:
            return domain
    return "Other"


def _scenario_display_name(scenario_id: str) -> str:
    """Convert snake_case scenario_id to a human-readable display name."""
    return scenario_id.replace("_", " ").title()


def load_scores_from_summary(summary_path: str) -> dict:
    """Load per-scenario C1-C5 mean scores (0-100 scale) from summary.json.

    The summary JSON has the structure:
        { scenario_id: [ {run_id, C1, C2, C3, C4, C5, ...}, ... ], ... }

    Returns a dict mapping display_name -> {"C1": float, ..., "C5": float}
    with values on a 0-100 scale (raw values are 0-1 fractions).
    """
    path = Path(summary_path)
    with path.open() as fh:
        data = json.load(fh)

    scores: dict = {}
    for scenario_id, runs in data.items():
        if not runs:
            continue
        display_name = _scenario_display_name(scenario_id)
        means: dict = {}
        for key in ("C1", "C2", "C3", "C4", "C5"):
            values = [r[key] for r in runs if key in r]
            means[key] = (sum(values) / len(values) * 100) if values else 0.0
        scores[display_name] = means
    return scores


def _build_domain_groups(all_scores: dict) -> dict:
    """Build domain groups from loaded scores using keyword classification."""
    groups: dict = {}
    for display_name in all_scores:
        domain = _classify_domain(display_name)
        groups.setdefault(domain, []).append(display_name)
    return groups


# Fallback hardcoded scores (used when no summary.json is available)
FALLBACK_SCORES = {
    "Sepsis (basic)":     {"C1": 98.6, "C2": 100.0, "C3": 100.0, "C4": 73.3, "C5": 100.0},
    "Sepsis (allergy)":   {"C1": 100.0, "C2": 100.0, "C3": 100.0, "C4": 80.0, "C5": 100.0},
    "STEMI (RV trap)":    {"C1": 94.2,  "C2": 100.0, "C3": 100.0, "C4": 66.7, "C5": 100.0},
    "DKA (moderate)":     {"C1": 100.0, "C2": 80.0,  "C3": 100.0, "C4": 93.3, "C5": 90.0},
    "DKA (hypokalemia)":  {"C1": 100.0, "C2": 80.0,  "C3": 100.0, "C4": 93.3, "C5": 90.0},
    "Contrast AKI":       {"C1": 61.1,  "C2": 100.0, "C3": 100.0, "C4": 93.3, "C5": 100.0},
    "AKI (Stage 1)":      {"C1": 61.1,  "C2": 100.0, "C3": 100.0, "C4": 80.0, "C5": 100.0},
    "Stroke (tPA)":       {"C1": 100.0, "C2": 88.9,  "C3": 100.0, "C4": 100.0, "C5": 100.0},
}

# Domain grouping for fallback scores
_FALLBACK_DOMAIN_GROUPS = {
    "Sepsis":    ["Sepsis (basic)", "Sepsis (allergy)"],
    "Cardiac":   ["STEMI (RV trap)"],
    "Metabolic": ["DKA (moderate)", "DKA (hypokalemia)"],
    "Renal":     ["Contrast AKI", "AKI (Stage 1)"],
    "Neuro":     ["Stroke (tPA)"],
}

# Safe filename mapping
_SAFE_NAMES = {
    "Sepsis (basic)":    "sepsis_basic",
    "Sepsis (allergy)":  "sepsis_allergy",
    "STEMI (RV trap)":   "stemi_rv_trap",
    "DKA (moderate)":    "dka_moderate",
    "DKA (hypokalemia)": "dka_hypokalemia",
    "Contrast AKI":      "contrast_aki",
    "AKI (Stage 1)":     "aki_stage1",
    "Stroke (tPA)":      "stroke_tpa",
}


def _make_axes(n: int):
    """Return evenly-spaced angles for n radar axes, closed."""
    angles = np.linspace(0, 2 * np.pi, n, endpoint=False).tolist()
    angles += angles[:1]  # close the loop
    return angles


def _score_values(scores: dict, keys: list) -> list:
    """Extract ordered values, closing the loop."""
    vals = [scores[k] for k in keys]
    vals += vals[:1]
    return vals


def _apply_paper_style():
    """Apply consistent paper-quality style."""
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 9,
        "axes.titlesize": 10,
        "axes.labelsize": 8,
        "xtick.labelsize": 8,
        "ytick.labelsize": 7,
        "legend.fontsize": 8,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "pdf.fonttype": 42,   # TrueType in PDF
        "ps.fonttype": 42,
    })


def _draw_radar(ax, angles, values, color, linestyle, label, alpha_fill=0.12):
    """Draw one radar trace on ax."""
    ax.plot(angles, values, color=color, linestyle=linestyle,
            linewidth=1.5, label=label)
    ax.fill(angles, values, color=color, alpha=alpha_fill)


def _configure_radar_ax(ax, angles, axis_labels, r_max=100):
    """Set up the polar axes with grid, labels and tick marks."""
    ax.set_theta_offset(np.pi / 2)
    ax.set_theta_direction(-1)
    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(axis_labels, size=8)
    ax.set_ylim(0, r_max)
    ax.set_yticks([20, 40, 60, 80, 100])
    ax.set_yticklabels(["20", "40", "60", "80", "100"], size=6, color="grey")
    ax.yaxis.set_tick_params(labelsize=6)
    ax.grid(color="grey", linestyle="--", linewidth=0.5, alpha=0.7)
    ax.spines["polar"].set_visible(True)


class RadarChartGenerator:
    """Generate C1-C5 radar charts for CGA-Bench results."""

    CRITERION_KEYS = ["C1", "C2", "C3", "C4", "C5"]
    AXES = ["C1\nPath", "C2\nMandatory", "C3\nForbidden", "C4\nTiming", "C5\nSequence"]

    def __init__(self):
        _apply_paper_style()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def plot_single(self, scenario_name: str, scores: dict, output_path: str):
        """Single scenario radar chart saved to output_path (PNG + PDF)."""
        angles = _make_axes(len(self.CRITERION_KEYS))
        values = _score_values(scores, self.CRITERION_KEYS)

        fig, ax = plt.subplots(figsize=(3.5, 3.5),
                               subplot_kw={"polar": True})
        _configure_radar_ax(ax, angles, self.AXES)
        _draw_radar(ax, angles, values, color=_COLORS[0],
                    linestyle="solid", label=scenario_name, alpha_fill=0.18)

        ax.set_title(scenario_name, pad=14, fontsize=10, fontweight="bold")

        # Score annotations on each axis
        for i, (key, val) in enumerate(zip(self.CRITERION_KEYS, values[:-1])):
            angle = angles[i]
            ax.annotate(f"{val:.1f}",
                        xy=(angle, val),
                        xytext=(angle, min(val + 8, 108)),
                        fontsize=6, ha="center", va="center", color=_COLORS[0])

        fig.tight_layout()
        self._save(fig, output_path)
        plt.close(fig)

    def plot_comparison(self, scenarios: dict, output_path: str, title: str = ""):
        """Multiple scenarios overlaid on one radar chart."""
        angles = _make_axes(len(self.CRITERION_KEYS))
        names = list(scenarios.keys())

        fig, ax = plt.subplots(figsize=(4.5, 4.5),
                               subplot_kw={"polar": True})
        _configure_radar_ax(ax, angles, self.AXES)

        for idx, (name, scores) in enumerate(scenarios.items()):
            values = _score_values(scores, self.CRITERION_KEYS)
            color = _COLORS[idx % len(_COLORS)]
            ls = _LINE_STYLES[idx % len(_LINE_STYLES)]
            _draw_radar(ax, angles, values, color=color,
                        linestyle=ls, label=name, alpha_fill=0.08)

        if title:
            ax.set_title(title, pad=16, fontsize=10, fontweight="bold")

        ax.legend(loc="upper right",
                  bbox_to_anchor=(1.35, 1.15),
                  fontsize=7,
                  framealpha=0.8)

        fig.tight_layout()
        self._save(fig, output_path)
        plt.close(fig)

    def plot_all(
        self,
        all_scores: dict = None,
        output_dir: str = "evidence_pack/figures",
        summary_path: str = None,
    ):
        """
        Generate all charts:
          - Individual radar chart per scenario
          - 1 domain group comparison
          - 1 overview with all scenarios

        Args:
            all_scores: explicit scores dict; takes precedence over summary_path.
            output_dir: directory to write output files.
            summary_path: path to summary.json; scores are loaded from here when
                          all_scores is not provided. Falls back to FALLBACK_SCORES
                          with a warning if the file is missing or unreadable.
        """
        if all_scores is not None:
            domain_groups = _build_domain_groups(all_scores)
        elif summary_path is not None:
            try:
                all_scores = load_scores_from_summary(summary_path)
                domain_groups = _build_domain_groups(all_scores)
                print(f"  Loaded scores from {summary_path} ({len(all_scores)} scenarios)")
            except Exception as exc:
                logger.warning(
                    "Could not load scores from %s (%s); falling back to FALLBACK_SCORES.",
                    summary_path,
                    exc,
                )
                all_scores = FALLBACK_SCORES
                domain_groups = _FALLBACK_DOMAIN_GROUPS
        else:
            logger.warning(
                "No summary_path provided; using hardcoded FALLBACK_SCORES. "
                "Pass summary_path= to load live results."
            )
            all_scores = FALLBACK_SCORES
            domain_groups = _FALLBACK_DOMAIN_GROUPS

        out = Path(output_dir)
        out.mkdir(parents=True, exist_ok=True)

        # 1. Individual charts
        for name, scores in all_scores.items():
            safe = _SAFE_NAMES.get(name, name.lower().replace(" ", "_")
                                              .replace("(", "").replace(")", ""))
            path = str(out / f"radar_{safe}.png")
            self.plot_single(scenario_name=name, scores=scores, output_path=path)
            print(f"  Saved: {path}")

        # 2. Domain group comparison
        domain_avg = {}
        for domain, members in domain_groups.items():
            present = [m for m in members if m in all_scores]
            if not present:
                continue
            avg = {}
            for key in self.CRITERION_KEYS:
                avg[key] = np.mean([all_scores[m][key] for m in present])
            domain_avg[domain] = avg

        comp_path = str(out / "radar_domain_comparison.png")
        self.plot_comparison(
            scenarios=domain_avg,
            output_path=comp_path,
            title="Domain Comparison (C1–C5)"
        )
        print(f"  Saved: {comp_path}")

        # 3. Overview — all scenarios on one figure
        self._plot_overview(all_scores, str(out / "radar_overview.png"))
        print(f"  Saved: {out / 'radar_overview.png'}")

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _plot_overview(self, all_scores: dict, output_path: str):
        """2×4 subplot grid with all scenarios."""
        names = list(all_scores.keys())
        n = len(names)
        ncols = 4
        nrows = (n + ncols - 1) // ncols

        fig = plt.figure(figsize=(14, 7))
        angles = _make_axes(len(self.CRITERION_KEYS))

        for i, name in enumerate(names):
            ax = fig.add_subplot(nrows, ncols, i + 1, polar=True)
            _configure_radar_ax(ax, angles, self.AXES)
            values = _score_values(all_scores[name], self.CRITERION_KEYS)
            color = _COLORS[i % len(_COLORS)]
            _draw_radar(ax, angles, values, color=color,
                        linestyle="solid", label=name, alpha_fill=0.18)
            ax.set_title(name, pad=12, fontsize=8, fontweight="bold")

        fig.suptitle("CGA-Bench: C1–C5 Criterion Scores by Scenario",
                     fontsize=12, fontweight="bold", y=1.01)
        fig.tight_layout()
        self._save(fig, output_path)
        plt.close(fig)

    @staticmethod
    def _save(fig, base_path: str):
        """Save as PNG (300 dpi) and PDF."""
        png_path = base_path if base_path.endswith(".png") else base_path + ".png"
        pdf_path = png_path.replace(".png", ".pdf")
        fig.savefig(png_path, dpi=300, bbox_inches="tight")
        fig.savefig(pdf_path, bbox_inches="tight")
