
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""Shared utilities for EXP-A through EXP-F experiment scripts.

Provides:
- Graph ID aliasing (manual vs auto naming conventions)
- Scenario loading with source tagging
- Bootstrap CI computation
- Output helpers (JSON, Markdown, LaTeX booktabs)
- Matplotlib style setup
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import matplotlib
import numpy as np
import yaml

matplotlib.use("Agg")
import matplotlib.pyplot as plt

ROOT = Path(__file__).resolve().parents[2]
GRAPHS_DIR = ROOT / "cpg_model" / "graphs"
SCENARIOS_DIR = ROOT / "configs" / "scenarios"
AUTO_SCENARIOS_FILE = SCENARIOS_DIR / "auto_generated_scenarios.yaml"
EVIDENCE_DIR = ROOT / "evidence_pack"
FIGURES_DIR = EVIDENCE_DIR / "figures"
TABLES_DIR = EVIDENCE_DIR / "tables"
RESULTS_DIR = ROOT / "results" / "clean_slate_rescored"  # DEPRECATED — use RESULTS_DIR_V5
RESULTS_DIR_V5 = ROOT / "results" / "full_706_v5"
VM_PATH = ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"

# 8 complete models (706 scenarios × 3 runs = 2,118 each = 16,944 total)
COMPLETE_MODELS: frozenset[str] = frozenset(
    {
        "oss120b",
        "qwen27b",
        "qwen35b",
        "qwen4b",
        "qwen397b",
        "gemma31b",
        "nemotron30b",
        "deepseek_r1_7b",
    }
)

SEED = 42
N_BOOTSTRAP = 10000

# --- Graph ID aliasing ---
# Manual scenarios reference graphs by file-stem; auto scenarios use graph_id.
# This map normalises both to graph_id (canonical).
_STEM_TO_GRAPH_ID: dict[str, str] = {
    "ssc_sepsis_hour1": "ssc_sepsis_hour1_bundle",
    "aha_chest_pain": "aha_chest_pain_evaluation",
    "aha_heart_failure": "aha_heart_failure_2022",
    "aha_stroke": "aha_stroke_2019",
}

# Reverse map for graph_id -> file-stem
_GRAPH_ID_TO_STEM: dict[str, str] = {v: k for k, v in _STEM_TO_GRAPH_ID.items()}

HELD_OUT_GRAPH_IDS: set[str] = {
    "aba_burn_resuscitation",
    "aabb_transfusion",
    "acog_obstetric_hemorrhage",
    "pals_pediatric_emergency",
    "apa_agitation_management",
}


def canonical_graph_id(raw: str) -> str:
    """Normalise a guideline_graph reference to its canonical graph_id."""
    return _STEM_TO_GRAPH_ID.get(raw, raw)


def resolve_graph_path(guideline_graph: str) -> Path | None:
    """Return the graph YAML path for a given guideline_graph reference.

    Handles both file-stem and graph_id naming conventions.
    """
    # Direct match by file stem
    p = GRAPHS_DIR / f"{guideline_graph}.yaml"
    if p.exists():
        return p

    # Try reverse alias (graph_id -> stem)
    stem = _GRAPH_ID_TO_STEM.get(guideline_graph)
    if stem:
        p = GRAPHS_DIR / f"{stem}.yaml"
        if p.exists():
            return p

    # Try forward alias (stem -> graph_id won't help with file name)
    # Scan all graph files for matching graph_id
    for gp in GRAPHS_DIR.glob("*.yaml"):
        try:
            with open(gp) as f:
                data = yaml.safe_load(f)
            if data and data.get("graph_id") == guideline_graph:
                return gp
        except (OSError, yaml.YAMLError):
            continue

    return None


def load_all_graphs() -> dict[str, dict[str, Any]]:
    """Load all graph YAMLs, keyed by canonical graph_id."""
    graphs: dict[str, dict[str, Any]] = {}
    for gp in sorted(GRAPHS_DIR.glob("*.yaml")):
        try:
            with open(gp) as f:
                data = yaml.safe_load(f)
            gid = data.get("graph_id", gp.stem)
            graphs[gid] = data
        except (OSError, yaml.YAMLError):
            continue
    return graphs


def load_all_scenarios(tag_source: bool = True) -> list[dict[str, Any]]:
    """Load all scenarios from configs/scenarios/, tagging manual vs auto.

    Args:
        tag_source: If True, adds 'source_type' key ("manual"|"auto") to each.

    Returns:
        List of scenario dicts with unified graph_id.
    """
    scenarios: list[dict[str, Any]] = []

    # Manual scenario files
    for yf in sorted(SCENARIOS_DIR.glob("*.yaml")):
        if yf.name == "auto_generated_scenarios.yaml":
            continue
        try:
            with open(yf) as f:
                data = yaml.safe_load(f)
        except (OSError, yaml.YAMLError):
            continue
        if not data:
            continue

        items = data.get("scenarios", {})
        if isinstance(items, dict):
            for sid, sc in items.items():
                sc.setdefault("scenario_id", sid)
                sc["_canonical_graph_id"] = canonical_graph_id(sc.get("guideline_graph", ""))
                if tag_source:
                    sc["source_type"] = "manual"
                scenarios.append(sc)

    # Auto-generated scenarios
    if AUTO_SCENARIOS_FILE.exists():
        try:
            with open(AUTO_SCENARIOS_FILE) as f:
                data = yaml.safe_load(f)
        except Exception:
            data = None
        if data:
            items = data.get("scenarios", {})
            if isinstance(items, dict):
                for sid, sc in items.items():
                    sc.setdefault("scenario_id", sid)
                    sc["_canonical_graph_id"] = canonical_graph_id(sc.get("guideline_graph", ""))
                    if tag_source:
                        sc["source_type"] = "auto"
                    scenarios.append(sc)

    return scenarios


def domain_from_scenario(scenario: dict[str, Any]) -> str:
    """Extract canonical domain (graph_id) from a scenario dict."""
    return scenario.get("_canonical_graph_id", canonical_graph_id(scenario.get("guideline_graph", "unknown")))


# --- Bootstrap ---


def bootstrap_ci(
    data: np.ndarray,
    statistic_fn: Callable[[np.ndarray], float],
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = SEED,
    alpha: float = 0.05,
) -> tuple[float, float]:
    """Compute bootstrap confidence interval.

    Args:
        data: 1-D array of observations.
        statistic_fn: Function computing the statistic from a sample.
        n_bootstrap: Number of bootstrap resamples.
        seed: Random seed.
        alpha: Significance level (default 5% -> 95% CI).

    Returns:
        (lower, upper) bounds.
    """
    rng = np.random.default_rng(seed)
    n = len(data)
    if n == 0:
        return (0.0, 0.0)
    stats = np.array([statistic_fn(data[rng.integers(0, n, size=n)]) for _ in range(n_bootstrap)])
    lo = float(np.percentile(stats, 100 * alpha / 2))
    hi = float(np.percentile(stats, 100 * (1 - alpha / 2)))
    return (lo, hi)


# --- Output helpers ---


def save_json(data: dict | list, path: Path) -> None:
    """Save data as JSON with consistent formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Saved: {path}")


def save_markdown(text: str, path: Path) -> None:
    """Save markdown report."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write(text)
    print(f"  Saved: {path}")


def save_latex_table(
    rows: list[list[str]],
    headers: list[str],
    path: Path,
    caption: str = "",
    label: str = "",
) -> None:
    """Save a LaTeX booktabs table.

    Args:
        rows: List of rows, each a list of cell strings.
        headers: Column headers.
        path: Output .tex file.
        caption: Table caption.
        label: Table label.
    """
    path.parent.mkdir(parents=True, exist_ok=True)

    col_spec = "l" + "r" * (len(headers) - 1)
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
    ]
    if caption:
        lines.append(f"\\caption{{{caption}}}")
    if label:
        lines.append(f"\\label{{{label}}}")
    lines += [
        f"\\begin{{tabular}}{{{col_spec}}}",
        r"\toprule",
        " & ".join(headers) + r" \\",
        r"\midrule",
    ]
    for row in rows:
        lines.append(" & ".join(row) + r" \\")
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]

    with open(path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Saved: {path}")


# --- Matplotlib ---


def setup_matplotlib() -> None:
    """Configure matplotlib for consistent paper-quality figures."""
    plt.rcParams.update(
        {
            "figure.figsize": (8, 5),
            "figure.dpi": 150,
            "savefig.dpi": 300,
            "savefig.bbox": "tight",
            "font.size": 11,
            "axes.titlesize": 13,
            "axes.labelsize": 12,
            "xtick.labelsize": 10,
            "ytick.labelsize": 10,
            "legend.fontsize": 10,
            "axes.grid": True,
            "grid.alpha": 0.3,
        }
    )


def save_figure(fig: plt.Figure, path: Path) -> None:
    """Save figure with standard settings."""
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=300, bbox_inches="tight")
    plt.close(fig)
    print(f"  Saved: {path}")


# --- Stats formatting ---


def fmt_p(p: float) -> str:
    """Format p-value for display."""
    if p < 0.001:
        return f"{p:.2e}"
    return f"{p:.4f}"


def fmt_f(val: float, decimals: int = 3) -> str:
    """Format float for display."""
    return f"{val:.{decimals}f}"


def count_constraint_types(
    constraints: list[dict[str, Any]],
) -> Counter[str]:
    """Count constraint types from a list of constraint dicts."""
    return Counter(c.get("constraint_type", "UNKNOWN") for c in constraints)
