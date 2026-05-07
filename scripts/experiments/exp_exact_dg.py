#!/usr/bin/env python3
"""EXP-dG: Exact Minimal-Repair Conformance Distance Analysis.

Compares exact d_G(τ,p) against violation-counting surrogate across episodes.

Two analysis modes:
  A. Constraint landscape: per-scenario constraint decomposition and d_G budget
  B. Surrogate comparison: weighted d_G vs flat violation count re-ranking

Data sources:
  - verdict_matrix_v6.json (180 episodes, per-episode violation data)
  - Scenario configs (expected/forbidden actions)
  - CPG graphs (deadlines, ordering via engine)

Outputs:
  evidence_pack/analysis/exp_exact_dg.json
  evidence_pack/analysis/exp_exact_dg.md
  evidence_pack/figures/exp_exact_dg_scatter.png
  evidence_pack/figures/exp_exact_dg_tier_breakdown.png
  evidence_pack/tables/exact_dg.tex

Usage:
    PYTHONPATH=. python scripts/experiments/exp_exact_dg.py [--limit N]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from scipy import stats as sp_stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cpg_model.conformance_distance import (
    ConformanceDistanceSolver,
    ConstraintType,
    CostConfig,
    HardConstraint,
)
from cpg_model.schemas.base import Action, ActionType
import matplotlib.pyplot as plt
from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    TABLES_DIR,
    fmt_f,
    load_all_scenarios,
    save_figure,
    save_json,
    save_latex_table,
    save_markdown,
    setup_matplotlib,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERDICT_MATRIX_PATH = EVIDENCE_DIR / "analysis" / "verdict_matrix_v6.json"
OUTPUT_JSON = EVIDENCE_DIR / "analysis" / "exp_exact_dg.json"
OUTPUT_MD = EVIDENCE_DIR / "analysis" / "exp_exact_dg.md"
OUTPUT_SCATTER = FIGURES_DIR / "exp_exact_dg_scatter.png"
OUTPUT_TIER = FIGURES_DIR / "exp_exact_dg_tier_breakdown.png"
OUTPUT_TEX = TABLES_DIR / "exact_dg.tex"

# Violation type → constraint tier mapping (verdict_matrix uses these names)
VIOL_TYPE_TO_TIER: dict[str, str] = {
    "FORBIDDEN": "forbid",
    "COMMISSION": "forbid",
    "OMISSION": "must",
    "TIMING": "within",
    "WITHIN": "within",
    "SEQUENCE": "before",
    "BEFORE": "before",
    "DEVIATION": "must",
}

DEFAULT_COST = CostConfig()


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_verdict_matrix(path: Path) -> list[dict[str, Any]]:
    """Load per-episode array from verdict_matrix_v6.json."""
    with open(path) as f:
        data = json.load(f)
    episodes = data["per_episode"]
    print(f"  Loaded {len(episodes)} episodes from {path.name}")
    return episodes


def build_scenario_constraints(
    scenarios: list[dict[str, Any]],
) -> dict[str, list[HardConstraint]]:
    """Build HardConstraint lists from scenario configs.

    Args:
        scenarios: List of scenario dicts from load_all_scenarios().

    Returns:
        {scenario_id: [HardConstraint, ...]}
    """
    result: dict[str, list[HardConstraint]] = {}

    for sc in scenarios:
        sid = sc.get("scenario_id", "")
        constraints: list[HardConstraint] = []

        # MUST from expected_actions
        for aid in sc.get("expected_actions", []):
            constraints.append(
                HardConstraint(
                    type=ConstraintType.MUST,
                    actions=[aid],
                    severity="HIGH",
                    provenance=f"scenario:{sid}:expected:{aid}",
                )
            )

        # FORBID from forbidden_actions
        for aid in sc.get("forbidden_actions", []):
            constraints.append(
                HardConstraint(
                    type=ConstraintType.FORBID,
                    actions=[aid],
                    severity="CRITICAL",
                    provenance=f"scenario:{sid}:forbidden:{aid}",
                )
            )

        # BEFORE from required_prior_actions
        rpa = sc.get("required_prior_actions", {})
        for action_id, priors in rpa.items():
            if isinstance(priors, list):
                for prior in priors:
                    constraints.append(
                        HardConstraint(
                            type=ConstraintType.BEFORE,
                            actions=[prior, action_id],
                            severity="HIGH",
                            provenance=f"scenario:{sid}:before:{prior}->{action_id}",
                        )
                    )

        # WITHIN from deadlines
        for aid, dl in sc.get("deadlines", {}).items():
            constraints.append(
                HardConstraint(
                    type=ConstraintType.WITHIN,
                    actions=[aid],
                    deadline=float(dl),
                    severity="CRITICAL" if float(dl) <= 60 else "HIGH",
                    provenance=f"scenario:{sid}:within:{aid}@{dl}",
                )
            )

        result[sid] = constraints

    return result


# ---------------------------------------------------------------------------
# d_G approximation from violation types
# ---------------------------------------------------------------------------


def approx_dg_from_violations(
    viol_types: list[str],
    cost: CostConfig,
) -> tuple[float, dict[str, float]]:
    """Approximate d_G from violation type list (no trace needed).

    Uses tier-weighted costs. For WITHIN violations without exact overtime,
    assumes 10-minute overtime as a conservative default.

    Args:
        viol_types: List of violation type strings from verdict_matrix.
        cost: Cost configuration.

    Returns:
        (total_distance, {tier: cost})
    """
    within_default_overtime = 10.0
    breakdown: dict[str, float] = {"forbid": 0.0, "must": 0.0, "before": 0.0, "within": 0.0}

    for vt in viol_types:
        tier = VIOL_TYPE_TO_TIER.get(vt, "must")
        if tier == "forbid":
            breakdown["forbid"] += cost.forbid
        elif tier == "must":
            breakdown["must"] += cost.must
        elif tier == "before":
            breakdown["before"] += cost.before
        elif tier == "within":
            breakdown["within"] += cost.within_critical * within_default_overtime

    total = sum(breakdown.values())
    return total, breakdown


# ---------------------------------------------------------------------------
# Synthetic trace generation for constraint-aware d_G
# ---------------------------------------------------------------------------


def generate_synthetic_traces(
    scenario_constraints: dict[str, list[HardConstraint]],
) -> list[dict[str, Any]]:
    """Generate per-scenario synthetic traces demonstrating d_G discrimination.

    For each scenario with constraints, generates:
      - conformant trace (d_G=0)
      - single-tier violation traces
      - multi-violation trace

    Returns list of {scenario_id, trace_label, d_G, n_viols, cost_breakdown}.
    """
    solver = ConformanceDistanceSolver()
    results: list[dict[str, Any]] = []

    for sid, constraints in sorted(scenario_constraints.items()):
        if not constraints:
            continue

        must_ids = [c.actions[0] for c in constraints if c.type == ConstraintType.MUST]
        forbid_ids = [c.actions[0] for c in constraints if c.type == ConstraintType.FORBID]

        # Conformant trace: all MUST actions present, no FORBID actions
        conformant_trace = [
            Action(type=ActionType.PROCEDURE, action_id=aid, args={}, timestamp_minutes=float(i * 5))
            for i, aid in enumerate(must_ids)
        ]
        r = solver.compute(conformant_trace, constraints)
        results.append(
            {
                "scenario_id": sid,
                "trace_label": "conformant",
                "d_G": r.distance,
                "n_viols": len(r.violations),
                "cost_breakdown": r.cost_breakdown,
            }
        )

        # Single FORBID violation: add one forbidden action
        if forbid_ids:
            trace_forbid = list(conformant_trace) + [
                Action(
                    type=ActionType.GIVE_MEDICATION,
                    action_id=forbid_ids[0],
                    args={},
                    timestamp_minutes=50.0,
                )
            ]
            r = solver.compute(trace_forbid, constraints)
            results.append(
                {
                    "scenario_id": sid,
                    "trace_label": "single_forbid",
                    "d_G": r.distance,
                    "n_viols": len(r.violations),
                    "cost_breakdown": r.cost_breakdown,
                }
            )

        # Single MUST violation: omit first expected action
        if len(must_ids) >= 2:
            trace_omit = [
                Action(type=ActionType.PROCEDURE, action_id=aid, args={}, timestamp_minutes=float(i * 5))
                for i, aid in enumerate(must_ids[1:])
            ]
            r = solver.compute(trace_omit, constraints)
            results.append(
                {
                    "scenario_id": sid,
                    "trace_label": "single_must_omit",
                    "d_G": r.distance,
                    "n_viols": len(r.violations),
                    "cost_breakdown": r.cost_breakdown,
                }
            )

        # All-violation: empty trace + forbidden action
        trace_worst: list[Action] = []
        if forbid_ids:
            trace_worst = [
                Action(
                    type=ActionType.GIVE_MEDICATION,
                    action_id=fid,
                    args={},
                    timestamp_minutes=float(i * 5),
                )
                for i, fid in enumerate(forbid_ids)
            ]
        r = solver.compute(trace_worst, constraints)
        results.append(
            {
                "scenario_id": sid,
                "trace_label": "worst_case",
                "d_G": r.distance,
                "n_viols": len(r.violations),
                "cost_breakdown": r.cost_breakdown,
            }
        )

    return results


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def analyze_episodes(
    episodes: list[dict[str, Any]],
    cost: CostConfig,
) -> dict[str, Any]:
    """Compute d_G approximation vs violation count for all episodes.

    Returns analysis dict with per-episode data and aggregate statistics.
    """
    per_episode: list[dict[str, Any]] = []

    for ep in episodes:
        viol_types = ep.get("viol_types", [])
        n_viols = ep.get("n_viols", len(viol_types))
        dg_approx, breakdown = approx_dg_from_violations(viol_types, cost)

        per_episode.append(
            {
                "episode_id": ep.get("episode_id", ""),
                "scenario_id": ep.get("scenario_id", ""),
                "model": ep.get("model", ""),
                "n_viols": n_viols,
                "d_G_approx": round(dg_approx, 2),
                "cost_breakdown": {k: round(v, 2) for k, v in breakdown.items()},
                "compliance_score": ep.get("c2_score", 0.0),
                "viol_types": viol_types,
            }
        )

    # Aggregate statistics
    dg_values = np.array([e["d_G_approx"] for e in per_episode])
    nviol_values = np.array([e["n_viols"] for e in per_episode])

    # Correlation between d_G and n_viols
    spearman_rho = float("nan")
    spearman_p = float("nan")
    pearson_r = float("nan")
    pearson_p = float("nan")

    nonzero_mask = (dg_values > 0) | (nviol_values > 0)
    if nonzero_mask.sum() >= 3:
        dg_nz = dg_values[nonzero_mask]
        nv_nz = nviol_values[nonzero_mask]
        if len(set(dg_nz)) > 1 and len(set(nv_nz)) > 1:
            sp_res = sp_stats.spearmanr(dg_nz, nv_nz)
            spearman_rho = float(sp_res.statistic)
            spearman_p = float(sp_res.pvalue)
            pe_res = sp_stats.pearsonr(dg_nz, nv_nz)
            pearson_r = float(pe_res.statistic)
            pearson_p = float(pe_res.pvalue)

    # Rank reversal: cases where n_viols ranking differs from d_G ranking
    rank_reversals = 0
    conformant_count = int((dg_values == 0).sum())
    nonconformant_count = int((dg_values > 0).sum())

    # Compare pairs for rank reversal
    for i in range(len(per_episode)):
        for j in range(i + 1, len(per_episode)):
            nv_i, nv_j = nviol_values[i], nviol_values[j]
            dg_i, dg_j = dg_values[i], dg_values[j]
            # Rank reversal: n_viols says i < j but d_G says i > j (or vice versa)
            if (nv_i < nv_j and dg_i > dg_j) or (nv_i > nv_j and dg_i < dg_j):
                rank_reversals += 1

    # Per-model mean d_G
    model_dg: dict[str, list[float]] = {}
    for ep in per_episode:
        model_dg.setdefault(ep["model"], []).append(ep["d_G_approx"])

    per_model = {
        m: {
            "mean_dG": round(float(np.mean(vals)), 2),
            "std_dG": round(float(np.std(vals)), 2),
            "n_conformant": sum(1 for v in vals if v == 0.0),
            "n_episodes": len(vals),
        }
        for m, vals in sorted(model_dg.items())
    }

    # Per-tier cost breakdown (aggregate)
    tier_totals: dict[str, float] = {"forbid": 0.0, "must": 0.0, "before": 0.0, "within": 0.0}
    for ep in per_episode:
        for tier, val in ep["cost_breakdown"].items():
            tier_totals[tier] += val

    # Verdict change analysis: d_G=0 vs compliance_score==1.0
    verdict_dg_pass = sum(1 for e in per_episode if e["d_G_approx"] == 0)
    verdict_compliance_pass = sum(
        1 for e in per_episode if e["compliance_score"] is not None and e["compliance_score"] >= 1.0
    )
    verdict_disagree = sum(1 for e in per_episode if (e["d_G_approx"] == 0) != (e.get("compliance_score", 0) >= 1.0))

    return {
        "n_episodes": len(per_episode),
        "conformant_count": conformant_count,
        "nonconformant_count": nonconformant_count,
        "mean_dG": round(float(np.mean(dg_values)), 2),
        "median_dG": round(float(np.median(dg_values)), 2),
        "std_dG": round(float(np.std(dg_values)), 2),
        "spearman_rho": round(spearman_rho, 4) if not np.isnan(spearman_rho) else None,
        "spearman_p": round(spearman_p, 6) if not np.isnan(spearman_p) else None,
        "pearson_r": round(pearson_r, 4) if not np.isnan(pearson_r) else None,
        "pearson_p": round(pearson_p, 6) if not np.isnan(pearson_p) else None,
        "rank_reversals": rank_reversals,
        "verdict_dg_pass": verdict_dg_pass,
        "verdict_compliance_pass": verdict_compliance_pass,
        "verdict_disagree": verdict_disagree,
        "per_model": per_model,
        "tier_totals": {k: round(v, 2) for k, v in tier_totals.items()},
        "per_episode": per_episode,
    }


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------


def plot_scatter(
    per_episode: list[dict[str, Any]],
    output_path: Path,
) -> None:
    """Scatter plot: d_G vs violation count, colored by model."""
    setup_matplotlib()
    fig, ax = plt.subplots(figsize=(8, 6))

    models = sorted({e["model"] for e in per_episode})
    colors = plt.cm.Set2(np.linspace(0, 1, max(len(models), 1)))
    model_color = dict(zip(models, colors))

    for ep in per_episode:
        ax.scatter(
            ep["n_viols"],
            ep["d_G_approx"],
            c=[model_color[ep["model"]]],
            alpha=0.6,
            s=40,
            edgecolors="gray",
            linewidths=0.5,
        )

    # Legend
    for m, c in model_color.items():
        ax.scatter([], [], c=[c], label=m, s=60)
    ax.legend(title="Model", loc="upper left")

    ax.set_xlabel("Violation Count (flat surrogate)")
    ax.set_ylabel("Approximate d_G (tiered cost)")
    ax.set_title("Conformance Distance d_G vs Violation Count")

    # Diagonal reference
    max_val = max(max(e["d_G_approx"] for e in per_episode), 1)
    ax.set_ylim(bottom=-max_val * 0.05)

    save_figure(fig, output_path)


def plot_tier_breakdown(
    tier_totals: dict[str, float],
    per_model: dict[str, dict[str, Any]],
    output_path: Path,
) -> None:
    """Stacked bar chart of per-tier cost breakdown."""
    setup_matplotlib()
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Left: aggregate tier breakdown (pie)
    ax1 = axes[0]
    tiers = ["forbid", "must", "before", "within"]
    tier_labels = ["FORBID (safety)", "MUST (omission)", "BEFORE (sequence)", "WITHIN (timing)"]
    tier_vals = [tier_totals.get(t, 0) for t in tiers]
    nonzero = [(l, v) for l, v in zip(tier_labels, tier_vals) if v > 0]

    if nonzero:
        labels_nz, vals_nz = zip(*nonzero)
        colors = ["#d32f2f", "#1976d2", "#f57c00", "#388e3c"]
        colors_nz = [c for c, v in zip(colors, tier_vals) if v > 0]
        ax1.pie(vals_nz, labels=labels_nz, colors=colors_nz, autopct="%1.1f%%", startangle=90)
    ax1.set_title("Aggregate d_G Cost by Tier")

    # Right: per-model mean d_G bar
    ax2 = axes[1]
    model_names = sorted(per_model.keys())
    mean_dgs = [per_model[m]["mean_dG"] for m in model_names]
    bars = ax2.bar(model_names, mean_dgs, color="#5c6bc0", alpha=0.8)
    ax2.set_ylabel("Mean d_G")
    ax2.set_title("Mean d_G by Model")
    for bar, val in zip(bars, mean_dgs):
        ax2.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.5,
            f"{val:.1f}",
            ha="center",
            va="bottom",
            fontsize=9,
        )

    fig.tight_layout()
    save_figure(fig, output_path)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_markdown_report(analysis: dict[str, Any], synthetic: list[dict[str, Any]]) -> str:
    """Generate markdown report."""
    lines = [
        "# EXP-dG: Exact Minimal-Repair Conformance Distance Analysis",
        "",
        "## Summary",
        "",
        f"- **Episodes analyzed**: {analysis['n_episodes']}",
        f"- **Conformant (d_G=0)**: {analysis['conformant_count']}",
        f"- **Non-conformant (d_G>0)**: {analysis['nonconformant_count']}",
        f"- **Mean d_G**: {analysis['mean_dG']} (std={analysis['std_dG']})",
        f"- **Median d_G**: {analysis['median_dG']}",
        "",
        "## Surrogate Comparison: d_G vs Violation Count",
        "",
        f"- **Spearman rho**: {analysis['spearman_rho']} (p={analysis['spearman_p']})",
        f"- **Pearson r**: {analysis['pearson_r']} (p={analysis['pearson_p']})",
        f"- **Rank reversals**: {analysis['rank_reversals']}",
        f"- **Verdict disagreements (d_G=0 vs compliance>=1.0)**: {analysis['verdict_disagree']}",
        "",
        "## Per-Model Results",
        "",
        "| Model | Mean d_G | Std d_G | Conformant | Episodes |",
        "|-------|----------|---------|------------|----------|",
    ]
    for m, stats in sorted(analysis["per_model"].items()):
        lines.append(
            f"| {m} | {stats['mean_dG']:.2f} | {stats['std_dG']:.2f} | "
            f"{stats['n_conformant']}/{stats['n_episodes']} | {stats['n_episodes']} |"
        )

    lines += [
        "",
        "## Cost Tier Breakdown (Aggregate)",
        "",
        "| Tier | Total Cost | Description |",
        "|------|-----------|-------------|",
        f"| FORBID | {analysis['tier_totals']['forbid']:.2f} | Patient safety violations |",
        f"| MUST | {analysis['tier_totals']['must']:.2f} | Required action omissions |",
        f"| BEFORE | {analysis['tier_totals']['before']:.2f} | Sequence violations |",
        f"| WITHIN | {analysis['tier_totals']['within']:.2f} | Timing violations |",
        "",
        "## Synthetic Trace Discrimination (Constraint-Aware d_G)",
        "",
        "Demonstrates that d_G discriminates between violation types",
        "that violation counting treats identically.",
        "",
        "| Scenario | Trace | d_G | n_viols | Dominant Tier |",
        "|----------|-------|-----|---------|---------------|",
    ]

    for s in synthetic[:30]:
        cb = s["cost_breakdown"]
        dominant = max(cb, key=cb.get) if any(v > 0 for v in cb.values()) else "none"
        lines.append(f"| {s['scenario_id'][:30]} | {s['trace_label']} | {s['d_G']:.1f} | {s['n_viols']} | {dominant} |")

    lines += [
        "",
        "## Key Finding",
        "",
        "d_G assigns 200x higher cost to safety violations (FORBID=1000) vs omissions",
        "(MUST=5), enabling severity-aware ranking that flat violation counting misses.",
        "Episodes with identical violation counts can differ by >100x in d_G when",
        "violation types differ (e.g., 1 FORBID vs 1 OMISSION).",
    ]

    return "\n".join(lines)


def generate_latex_table(analysis: dict[str, Any]) -> list[tuple[list[str], list[str]]]:
    """Generate LaTeX table rows."""
    headers = ["Model", "Mean $d_G$", "Std", "Conformant", "$n$"]
    rows = []
    for m, stats in sorted(analysis["per_model"].items()):
        rows.append(
            [
                m,
                fmt_f(stats["mean_dG"], 2),
                fmt_f(stats["std_dG"], 2),
                f"{stats['n_conformant']}/{stats['n_episodes']}",
                str(stats["n_episodes"]),
            ]
        )
    return rows, headers


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="EXP-dG: Conformance Distance Analysis")
    parser.add_argument("--limit", type=int, default=0, help="Limit episodes (0=all)")
    args = parser.parse_args()

    print("=" * 60)
    print("EXP-dG: Exact Minimal-Repair Conformance Distance")
    print("=" * 60)

    # 1. Load verdict matrix
    if not VERDICT_MATRIX_PATH.exists():
        print(f"ERROR: {VERDICT_MATRIX_PATH} not found")
        sys.exit(1)

    episodes = load_verdict_matrix(VERDICT_MATRIX_PATH)
    if args.limit > 0:
        episodes = episodes[: args.limit]

    # 2. Load scenarios and build constraint landscape
    print("\n[Phase 1] Building constraint landscape from scenarios...")
    scenarios = load_all_scenarios(tag_source=True)
    scenario_constraints = build_scenario_constraints(scenarios)
    n_with_constraints = sum(1 for cs in scenario_constraints.values() if cs)
    print(f"  {len(scenario_constraints)} scenarios, {n_with_constraints} with constraints")

    # 3. Analyze episodes (d_G approximation from violation types)
    print("\n[Phase 2] Computing d_G approximation for episodes...")
    analysis = analyze_episodes(episodes, DEFAULT_COST)
    print(f"  Mean d_G = {analysis['mean_dG']}, Median = {analysis['median_dG']}")
    print(f"  Spearman rho = {analysis['spearman_rho']}")
    print(f"  Rank reversals = {analysis['rank_reversals']}")

    # 4. Synthetic traces for discrimination demo
    print("\n[Phase 3] Generating synthetic traces for discrimination analysis...")
    synthetic = generate_synthetic_traces(scenario_constraints)
    print(f"  Generated {len(synthetic)} synthetic trace evaluations")

    # 5. Save outputs
    print("\n[Phase 4] Saving outputs...")
    output_data = {
        "experiment": "exp_exact_dg",
        "cost_config": {
            "forbid": DEFAULT_COST.forbid,
            "within_critical": DEFAULT_COST.within_critical,
            "before": DEFAULT_COST.before,
            "must": DEFAULT_COST.must,
            "within_soft": DEFAULT_COST.within_soft,
        },
        "analysis": {k: v for k, v in analysis.items() if k != "per_episode"},
        "synthetic_traces": synthetic,
        "per_episode": analysis["per_episode"],
    }
    save_json(output_data, OUTPUT_JSON)

    # Markdown report
    md_report = generate_markdown_report(analysis, synthetic)
    save_markdown(md_report, OUTPUT_MD)

    # Figures
    print("\n[Phase 5] Generating figures...")
    plot_scatter(analysis["per_episode"], OUTPUT_SCATTER)
    plot_tier_breakdown(analysis["tier_totals"], analysis["per_model"], OUTPUT_TIER)

    # LaTeX table
    rows, headers = generate_latex_table(analysis)
    save_latex_table(
        rows,
        headers,
        OUTPUT_TEX,
        caption="Per-model conformance distance $d_G$ statistics",
        label="tab:exact_dg",
    )

    print("\n" + "=" * 60)
    print("EXP-dG complete.")
    print(f"  JSON:    {OUTPUT_JSON}")
    print(f"  Report:  {OUTPUT_MD}")
    print(f"  Scatter: {OUTPUT_SCATTER}")
    print(f"  Tiers:   {OUTPUT_TIER}")
    print(f"  Table:   {OUTPUT_TEX}")
    print("=" * 60)


if __name__ == "__main__":
    main()
