#!/usr/bin/env python3
"""CGA Sub-construct Decomposition and Construct Validity Analysis.

Produces:
  - evidence_pack/analysis/subconstruct_profiles.json
  - evidence_pack/analysis/discriminant_validity.json
  - evidence_pack/figures/radar_chart_models.pdf
  - evidence_pack/figures/activity_vs_cga.pdf
  - evidence_pack/figures/q2_failure_decomposition.pdf

Usage:
    PYTHONPATH=. python scripts/experiments/subconstruct_analysis.py
"""
from __future__ import annotations

from collections import defaultdict
import json
import os
import pathlib

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_DIR = pathlib.Path(__file__).resolve().parents[2]  # cga_bench root
RESULTS_DIR = BASE_DIR / "results"
EVIDENCE_DIR = BASE_DIR / "evidence_pack" / "analysis"
FIGURES_DIR = BASE_DIR / "evidence_pack" / "figures"

SUBCONSTRUCTS = ["C1_path_selection", "C2_mandatory_completion",
                 "C3_forbidden_avoidance", "C4_timing_compliance",
                 "C5_sequence_integrity"]

SUBCONSTRUCT_LABELS = ["C1\nPath", "C2\nMandatory", "C3\nForbidden",
                       "C4\nTiming", "C5\nSequence"]

MODEL_DIRS: dict[str, dict[str, pathlib.Path]] = {
    "oss-120b": {
        "run0": RESULTS_DIR / "eval_science_rag_oss120b" / "baseline",
        "run1": RESULTS_DIR / "eval_science_rag_oss120b" / "patch_S",
        "run2": RESULTS_DIR / "eval_science_rag_oss120b" / "patch_T",
    },
    "Qwen3.5-35B": {
        "baseline": RESULTS_DIR / "eval_science_rag_qwen35" / "baseline",
    },
    "oss-20b": {
        "baseline": RESULTS_DIR / "eval_science_rag_oss20b" / "baseline",
    },
    "Qwen3-4B": {
        "baseline": RESULTS_DIR / "eval_science_rag_qwen3_4b" / "baseline",
    },
}

MODEL_COLORS = {
    "oss-120b": "#1f77b4",
    "Qwen3.5-35B": "#ff7f0e",
    "oss-20b": "#2ca02c",
    "Qwen3-4B": "#d62728",
}

RUNS_PER_SCENARIO = 3
MIN_FRIEDMAN_MODELS = 3


# ---------------------------------------------------------------------------
# Data Loading
# ---------------------------------------------------------------------------

def load_episodes(model: str, dirs: dict[str, pathlib.Path]) -> dict[str, list[dict]]:
    """Load episode JSONs grouped by scenario_id, assigning run indices.

    Args:
        model: Model display name.
        dirs: Mapping of run-label to directory path.

    Returns:
        Dict mapping scenario_id to list of episode dicts (max 3 per scenario).
    """
    episodes_by_scenario: dict[str, list[dict]] = defaultdict(list)

    if len(dirs) >= RUNS_PER_SCENARIO:
        # oss-120b style: separate directories per run
        for run_label in sorted(dirs.keys()):
            d = dirs[run_label]
            if not d.exists():
                continue
            for fp in sorted(d.glob("*.json")):
                ep = _load_json(fp)
                if ep and "sub_scores" in ep:
                    episodes_by_scenario[ep["scenario_id"]].append(ep)
        # Truncate to RUNS_PER_SCENARIO per scenario (same as single-dir path)
        for sid in episodes_by_scenario:
            episodes_by_scenario[sid] = episodes_by_scenario[sid][:RUNS_PER_SCENARIO]
    else:
        # Single baseline directory: sort by filename, split into runs
        d = dirs.get("baseline")
        if d is None or not d.exists():
            return episodes_by_scenario
        by_scenario: dict[str, list[dict]] = defaultdict(list)
        for fp in sorted(d.glob("*.json")):
            ep = _load_json(fp)
            if ep and "sub_scores" in ep:
                by_scenario[ep["scenario_id"]].append(ep)
        for sid, eps in by_scenario.items():
            # Take first 3 episodes (sorted by filename = chronological)
            episodes_by_scenario[sid] = eps[:RUNS_PER_SCENARIO]

    return dict(episodes_by_scenario)


def _load_json(fp: pathlib.Path) -> dict | None:
    """Load a single JSON file, returning None on failure."""
    try:
        with open(fp) as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def load_all_models() -> dict[str, dict[str, list[dict]]]:
    """Load episodes for all models.

    Returns:
        Dict[model_name, Dict[scenario_id, List[episode]]].
    """
    all_data: dict[str, dict[str, list[dict]]] = {}
    for model, dirs in MODEL_DIRS.items():
        all_data[model] = load_episodes(model, dirs)
        n_scenarios = len(all_data[model])
        n_eps = sum(len(v) for v in all_data[model].values())
        print(f"  {model}: {n_scenarios} scenarios, {n_eps} episodes")
    return all_data


def load_q2_episodes() -> list[dict]:
    """Load Q2 episodes from necessity_audit_final.json.

    Returns:
        List of Q2 episode dicts with sub-construct scores.
    """
    fp = EVIDENCE_DIR / "necessity_audit_final.json"
    if not fp.exists():
        print(f"  WARNING: {fp} not found, Q2 analysis skipped")
        return []
    with open(fp) as f:
        data = json.load(f)
    return data.get("q2_episodes", [])


# ---------------------------------------------------------------------------
# Step 1-2: Sub-construct Extraction and Model Comparison
# ---------------------------------------------------------------------------

def compute_model_profiles(
    all_data: dict[str, dict[str, list[dict]]],
) -> dict[str, dict[str, float]]:
    """Compute mean C1-C5 per model (average runs per scenario, then scenarios).

    Args:
        all_data: Loaded episode data.

    Returns:
        Dict[model, Dict[subconstruct, mean_score]].
    """
    profiles: dict[str, dict[str, float]] = {}
    for model, scenarios in all_data.items():
        scenario_means: dict[str, list[float]] = {c: [] for c in SUBCONSTRUCTS}
        for sid, eps in scenarios.items():
            for c in SUBCONSTRUCTS:
                vals = [ep["sub_scores"].get(c, 0.0) for ep in eps]
                if vals:
                    scenario_means[c].append(float(np.mean(vals)))
        profiles[model] = {}
        for c in SUBCONSTRUCTS:
            vals = scenario_means[c]
            profiles[model][c] = float(np.mean(vals)) if vals else 0.0
    return profiles


def compute_model_stats(
    all_data: dict[str, dict[str, list[dict]]],
) -> dict[str, dict[str, dict]]:
    """Compute per-model stats: mean actions, CGA, C2, deviations.

    Returns:
        Dict[model, Dict with keys mean_actions, mean_cga, mean_c2, mean_deviations].
    """
    result: dict[str, dict] = {}
    for model, scenarios in all_data.items():
        all_actions: list[float] = []
        all_cga: list[float] = []
        all_c2: list[float] = []
        all_deviations: list[int] = []
        for sid, eps in scenarios.items():
            for ep in eps:
                all_actions.append(ep.get("actions_count", 0))
                all_cga.append(ep.get("compliance_score", 0.0))
                all_c2.append(ep["sub_scores"].get("C2_mandatory_completion", 0.0))
                all_deviations.append(
                    ep.get("violations_by_type", {}).get("deviation", 0)
                )
        result[model] = {
            "mean_actions": float(np.mean(all_actions)) if all_actions else 0.0,
            "mean_cga": float(np.mean(all_cga)) if all_cga else 0.0,
            "mean_c2": float(np.mean(all_c2)) if all_c2 else 0.0,
            "mean_deviations": float(np.mean(all_deviations)) if all_deviations else 0.0,
            "n_episodes": len(all_actions),
        }
    return result


def run_friedman_tests(
    all_data: dict[str, dict[str, list[dict]]],
) -> dict[str, dict]:
    """Run Friedman test per sub-construct across models and scenarios.

    For each sub-construct, builds a matrix: rows=scenarios, cols=models.
    Cell value = mean of runs for that model+scenario.

    Returns:
        Dict[subconstruct, {statistic, p_value, rankings}].
    """
    models = sorted(all_data.keys())
    # Find common scenarios
    common_scenarios = set.intersection(
        *(set(all_data[m].keys()) for m in models)
    )
    common_scenarios = sorted(common_scenarios)
    print(f"  Friedman: {len(common_scenarios)} common scenarios, {len(models)} models")

    results: dict[str, dict] = {}
    for c in SUBCONSTRUCTS:
        matrix: list[list[float]] = []  # rows=scenarios, cols=models
        for sid in common_scenarios:
            row: list[float] = []
            for m in models:
                eps = all_data[m].get(sid, [])
                vals = [ep["sub_scores"].get(c, 0.0) for ep in eps]
                row.append(float(np.mean(vals)) if vals else 0.0)
            matrix.append(row)

        arr = np.array(matrix)  # (n_scenarios, n_models)
        if arr.shape[0] < 2 or arr.shape[1] < MIN_FRIEDMAN_MODELS:
            results[c] = {"statistic": None, "p_value": None, "rankings": {}}
            continue

        # Zero-variance check: if all values identical, Friedman is undefined
        if np.ptp(arr) < 1e-12:
            results[c] = {
                "statistic": 0.0,
                "p_value": 1.0,
                "rankings": {models[j]: 2.5 for j in range(len(models))},
                "note": "All values identical (zero variance); test not applicable",
            }
            continue

        # Friedman requires at least 3 groups
        try:
            stat_val, p_val = stats.friedmanchisquare(
                *[arr[:, i] for i in range(arr.shape[1])]
            )
        except ValueError:
            stat_val, p_val = float("nan"), float("nan")

        # Mean ranks (lower = better score)
        # Rank per scenario (higher score = lower rank number)
        ranks = np.zeros_like(arr)
        for i in range(arr.shape[0]):
            ranks[i] = stats.rankdata(-arr[i])  # negative so higher score = rank 1
        mean_ranks = {
            models[j]: float(ranks[:, j].mean()) for j in range(len(models))
        }

        results[c] = {
            "statistic": float(stat_val),
            "p_value": float(p_val),
            "rankings": mean_ranks,
        }
    return results


# ---------------------------------------------------------------------------
# Step 4: Discriminant Validity
# ---------------------------------------------------------------------------

def compute_discriminant_validity(
    all_data: dict[str, dict[str, list[dict]]],
    q2_episodes: list[dict],
) -> dict:
    """Compute discriminant validity evidence.

    (a) Point-biserial: Task Completion (C2>=1.0) vs CGA Score.
    (b) Q2 decomposition: which sub-construct caused CGA failure.

    Returns:
        Dict with point_biserial and q2_decomposition keys.
    """
    # (a) Point-biserial: collect all episodes
    task_complete: list[int] = []
    cga_scores: list[float] = []
    for model, scenarios in all_data.items():
        for sid, eps in scenarios.items():
            for ep in eps:
                c2 = ep["sub_scores"].get("C2_mandatory_completion", 0.0)
                task_complete.append(1 if c2 >= 1.0 else 0)
                cga_scores.append(ep.get("compliance_score", 0.0))

    if len(set(task_complete)) < 2:
        pb_r, pb_p = float("nan"), float("nan")
    else:
        pb_r, pb_p = stats.pointbiserialr(task_complete, cga_scores)

    # (b) Q2 decomposition
    q2_decomp = _decompose_q2_failures(q2_episodes)

    return {
        "point_biserial": {
            "r": float(pb_r),
            "p_value": float(pb_p),
            "n": len(cga_scores),
            "n_task_complete": sum(task_complete),
            "n_task_incomplete": len(task_complete) - sum(task_complete),
            "interpretation": (
                "r < 0.5 => CGA and Task Completion measure different constructs"
                if abs(pb_r) < 0.5
                else "r >= 0.5 => substantial overlap between CGA and Task Completion"
            ),
        },
        "q2_decomposition": q2_decomp,
    }


def _decompose_q2_failures(q2_episodes: list[dict]) -> dict:
    """Decompose Q2 episodes (Task PASS, CGA FAIL) by failing sub-construct.

    A sub-construct 'fails' if score < 1.0 (any imperfection).

    Returns:
        Dict with counts and per-episode breakdown.
    """
    THRESHOLD = 1.0
    sub_keys = ["c1", "c2", "c3", "c4", "c5"]
    sub_labels = ["C1_path_selection", "C2_mandatory_completion",
                  "C3_forbidden_avoidance", "C4_timing_compliance",
                  "C5_sequence_integrity"]

    failure_counts: dict[str, int] = dict.fromkeys(sub_labels, 0)
    episode_details: list[dict] = []

    for ep in q2_episodes:
        failing: list[str] = []
        for key, label in zip(sub_keys, sub_labels):
            val = ep.get(key, 1.0)
            if val < THRESHOLD:
                failure_counts[label] += 1
                failing.append(label)
        episode_details.append({
            "scenario": ep.get("scenario", ""),
            "model": ep.get("tag", ""),
            "cga": ep.get("cga", 0.0),
            "failing_subconstructs": failing,
        })

    return {
        "n_episodes": len(q2_episodes),
        "failure_counts": failure_counts,
        "episode_details": episode_details,
    }


# ---------------------------------------------------------------------------
# Step 3: Conservative Strategy Profile (scatter data)
# ---------------------------------------------------------------------------

def build_scatter_data(
    all_data: dict[str, dict[str, list[dict]]],
) -> list[dict]:
    """Build per-model-per-scenario scatter data (mean over runs).

    Returns:
        List of dicts with model, scenario, actions, cga keys.
    """
    points: list[dict] = []
    for model, scenarios in all_data.items():
        for sid, eps in scenarios.items():
            mean_actions = float(np.mean([ep.get("actions_count", 0) for ep in eps]))
            mean_cga = float(np.mean([ep.get("compliance_score", 0.0) for ep in eps]))
            points.append({
                "model": model,
                "scenario": sid,
                "actions": mean_actions,
                "cga": mean_cga,
            })
    return points


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

def _setup_style() -> None:
    """Configure matplotlib for publication-quality figures."""
    plt.rcParams.update({
        "font.family": "serif",
        "font.size": 10,
        "axes.labelsize": 11,
        "axes.titlesize": 12,
        "legend.fontsize": 9,
        "figure.dpi": 300,
        "savefig.dpi": 300,
        "savefig.bbox": "tight",
        "savefig.pad_inches": 0.1,
    })


def plot_radar_chart(
    profiles: dict[str, dict[str, float]],
    out_path: pathlib.Path,
) -> None:
    """Plot radar chart of C1-C5 profiles for all models.

    Args:
        profiles: Dict[model, Dict[subconstruct, score]].
        out_path: Output PDF path.
    """
    n_vars = len(SUBCONSTRUCTS)
    angles = np.linspace(0, 2 * np.pi, n_vars, endpoint=False).tolist()
    angles += angles[:1]  # close the polygon

    fig, ax = plt.subplots(figsize=(6, 6), subplot_kw={"polar": True})

    for model in sorted(profiles.keys()):
        vals = [profiles[model][c] for c in SUBCONSTRUCTS]
        vals += vals[:1]
        ax.plot(angles, vals, "o-", linewidth=1.8, markersize=5,
                label=model, color=MODEL_COLORS.get(model, "#333"))
        ax.fill(angles, vals, alpha=0.08, color=MODEL_COLORS.get(model, "#333"))

    ax.set_xticks(angles[:-1])
    ax.set_xticklabels(SUBCONSTRUCT_LABELS, fontsize=9)
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0.2, 0.4, 0.6, 0.8, 1.0])
    ax.set_yticklabels(["0.2", "0.4", "0.6", "0.8", "1.0"], fontsize=8)
    ax.set_title("CGA Sub-construct Profiles by Model", pad=20, fontsize=13)
    ax.legend(loc="upper right", bbox_to_anchor=(1.3, 1.1))

    fig.savefig(out_path, format="pdf")
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_activity_vs_cga(
    scatter_data: list[dict],
    out_path: pathlib.Path,
) -> None:
    """Plot scatter: action count vs CGA score, colored by model.

    Args:
        scatter_data: List of point dicts.
        out_path: Output PDF path.
    """
    fig, ax = plt.subplots(figsize=(7, 5))

    for model in sorted(MODEL_COLORS.keys()):
        pts = [p for p in scatter_data if p["model"] == model]
        if not pts:
            continue
        xs = [p["actions"] for p in pts]
        ys = [p["cga"] for p in pts]
        ax.scatter(xs, ys, c=MODEL_COLORS[model], label=model,
                   s=50, alpha=0.7, edgecolors="white", linewidths=0.5)

    ax.set_xlabel("Mean Action Count per Episode")
    ax.set_ylabel("Mean CGA Score")
    ax.set_title("Activity Level vs. Guideline Adherence")
    ax.set_ylim(-0.05, 1.1)
    ax.legend(loc="lower right")
    ax.grid(True, alpha=0.3)

    fig.savefig(out_path, format="pdf")
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_q2_failure_decomposition(
    q2_decomp: dict,
    out_path: pathlib.Path,
) -> None:
    """Plot stacked bar showing which sub-constructs caused Q2 failures.

    Args:
        q2_decomp: Output from _decompose_q2_failures().
        out_path: Output PDF path.
    """
    counts = q2_decomp.get("failure_counts", {})
    n_total = q2_decomp.get("n_episodes", 1)

    if not counts or n_total == 0:
        print("  WARNING: No Q2 data for failure decomposition plot")
        return

    labels = list(counts.keys())
    short_labels = [l.split("_")[0] for l in labels]
    values = [counts[l] for l in labels]

    fig, ax = plt.subplots(figsize=(7, 4))

    colors = ["#4e79a7", "#f28e2b", "#e15759", "#76b7b2", "#59a14f"]
    bars = ax.bar(short_labels, values, color=colors[:len(labels)],
                  edgecolor="white", linewidth=0.8)

    # Add count + percentage labels
    for bar, val in zip(bars, values):
        pct = val / n_total * 100
        ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.3,
                f"{val}\n({pct:.0f}%)", ha="center", va="bottom", fontsize=9)

    ax.set_xlabel("Sub-construct")
    ax.set_ylabel("Failure Count (score < 1.0)")
    ax.set_title(
        f"Q2 Failure Decomposition: Task PASS but CGA FAIL (n={n_total})"
    )
    ax.grid(True, axis="y", alpha=0.3)

    fig.savefig(out_path, format="pdf")
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run full sub-construct analysis pipeline."""
    os.chdir(BASE_DIR)
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    _setup_style()

    # Step 1: Load data
    print("[Step 1] Loading episodes...")
    all_data = load_all_models()

    # Step 2: Model comparison per sub-construct
    print("\n[Step 2] Computing model profiles and Friedman tests...")
    profiles = compute_model_profiles(all_data)
    friedman_results = run_friedman_tests(all_data)
    model_stats = compute_model_stats(all_data)

    for c in SUBCONSTRUCTS:
        fr = friedman_results[c]
        rank_str = ", ".join(
            f"{m}={r:.2f}" for m, r in sorted(
                fr["rankings"].items(), key=lambda x: x[1]
            )
        ) if fr["rankings"] else "N/A"
        p_str = f"{fr['p_value']:.4f}" if fr["p_value"] is not None else "N/A"
        print(f"  {c}: chi2={fr.get('statistic', 'N/A')}, p={p_str}")
        print(f"    Ranks: {rank_str}")

    # Step 3: Conservative strategy profile
    print("\n[Step 3] Building scatter data...")
    scatter_data = build_scatter_data(all_data)
    print(f"  {len(scatter_data)} model x scenario points")

    # Step 4: Discriminant validity
    print("\n[Step 4] Discriminant validity...")
    q2_episodes = load_q2_episodes()
    discriminant = compute_discriminant_validity(all_data, q2_episodes)
    pb = discriminant["point_biserial"]
    print(f"  Point-biserial r={pb['r']:.4f}, p={pb['p_value']:.4f}, n={pb['n']}")
    print(f"  {pb['interpretation']}")
    q2d = discriminant["q2_decomposition"]
    print(f"  Q2 episodes: {q2d['n_episodes']}")
    print(f"  Failure counts: {q2d['failure_counts']}")

    # Save JSON outputs
    print("\n[Output] Saving JSON artifacts...")
    subconstruct_output = {
        "profiles": profiles,
        "friedman_tests": friedman_results,
        "model_stats": model_stats,
        "scatter_data": scatter_data,
    }
    _save_json(subconstruct_output, EVIDENCE_DIR / "subconstruct_profiles.json")
    _save_json(discriminant, EVIDENCE_DIR / "discriminant_validity.json")

    # Step 5: Visualizations
    print("\n[Step 5] Generating figures...")
    plot_radar_chart(profiles, FIGURES_DIR / "radar_chart_models.pdf")
    plot_activity_vs_cga(scatter_data, FIGURES_DIR / "activity_vs_cga.pdf")
    plot_q2_failure_decomposition(
        discriminant["q2_decomposition"],
        FIGURES_DIR / "q2_failure_decomposition.pdf",
    )

    print("\nDone. All outputs written.")


def _save_json(data: dict, path: pathlib.Path) -> None:
    """Save dict as formatted JSON."""
    with open(path, "w") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    print(f"  Saved: {path}")


if __name__ == "__main__":
    main()
