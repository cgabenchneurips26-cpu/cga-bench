"""ILP vs Tiered d_G Solver Comparison.

Compares ILPConformanceDistanceSolver (joint optimization) against the tiered
ConformanceDistanceSolver across all 180 episodes and reports agreement,
Spearman correlation, and cases where ILP finds a strictly cheaper repair.
"""

from __future__ import annotations

from pathlib import Path
import sys

_SCRIPT_DIR = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_SCRIPT_DIR))  # cga_bench/ for scripts.*
sys.path.insert(0, str(_SCRIPT_DIR.parent))  # AnonProject/ for cga_bench.*

import numpy as np
from scipy.stats import spearmanr
from scripts.experiments._common import EVIDENCE_DIR, save_json, save_markdown
from scripts.experiments.gap_experiments import (
    SCENARIO_GRAPH,
    _load_cpg_graph_constraints,
    _load_original_action_traces,
    load_episodes,
)

from cga_bench.cpg_model.conformance_distance import (
    ConformanceDistanceSolver,
    ConstraintType,
    CostConfig,
    HardConstraint,
)
from cga_bench.cpg_model.conformance_distance_ilp import ILPConformanceDistanceSolver
from cga_bench.cpg_model.schemas.base import Action, ActionType

# ---------------------------------------------------------------------------
# Constraint builder
# ---------------------------------------------------------------------------


def _build_constraints_from_graph(gdata: dict) -> list[HardConstraint]:
    """Build HardConstraint list from graph constraint data.

    Args:
        gdata: Dict with keys forbidden, mandatory, deadlines, prior_actions,
               evidence, all_forbidden_set, all_mandatory_set.

    Returns:
        Deduplicated list of HardConstraint objects.
    """
    constraints: list[HardConstraint] = []

    # FORBID: from forbidden dict (node_id -> [action_ids])
    for node_id, forbidden_list in gdata.get("forbidden", {}).items():
        for action_id in forbidden_list:
            constraints.append(
                HardConstraint(
                    type=ConstraintType.FORBID,
                    actions=[action_id],
                    severity="CRITICAL",
                    provenance=f"graph:{node_id}:forbidden:{action_id}",
                )
            )

    # MUST: from mandatory dict (node_id -> [action_ids])
    for node_id, mandatory_list in gdata.get("mandatory", {}).items():
        for action_id in mandatory_list:
            constraints.append(
                HardConstraint(
                    type=ConstraintType.MUST,
                    actions=[action_id],
                    severity="HIGH",
                    provenance=f"graph:{node_id}:mandatory:{action_id}",
                )
            )

    # BEFORE: from prior_actions (node_id -> {dependent: priors})
    for node_id, prior_map in gdata.get("prior_actions", {}).items():
        for dependent, priors in prior_map.items():
            if isinstance(priors, str):
                priors = [priors]
            for prior in priors:
                constraints.append(
                    HardConstraint(
                        type=ConstraintType.BEFORE,
                        actions=[prior, dependent],
                        severity="HIGH",
                        provenance=f"graph:{node_id}:before:{prior}->{dependent}",
                    )
                )

    # WITHIN: from deadlines (node_id -> {action_id: deadline_minutes})
    evidence_map = gdata.get("evidence", {})
    for node_id, dl_map in gdata.get("deadlines", {}).items():
        evidence = evidence_map.get(node_id, "MODERATE")
        severity = "CRITICAL" if evidence == "STRONG" else "HIGH"
        for action_id, deadline_min in dl_map.items():
            constraints.append(
                HardConstraint(
                    type=ConstraintType.WITHIN,
                    actions=[action_id],
                    deadline=float(deadline_min),
                    severity=severity,
                    provenance=f"graph:{node_id}:within:{action_id}@{deadline_min}m",
                )
            )

    # Deduplicate by (type, tuple(actions), deadline)
    seen: set[tuple] = set()
    unique: list[HardConstraint] = []
    for c in constraints:
        key = (c.type.value, tuple(c.actions), c.deadline)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


# ---------------------------------------------------------------------------
# Trace builder
# ---------------------------------------------------------------------------


def _build_action_trace(raw_trace: list[tuple[str, float]]) -> list[Action]:
    """Convert (action_id, timestamp) pairs to Action objects.

    Args:
        raw_trace: List of (action_id, timestamp_minutes) tuples.

    Returns:
        List of Action objects sorted by timestamp.
    """
    return [
        Action(
            type=ActionType.PROCEDURE,
            action_id=aid,
            args={},
            timestamp_minutes=ts,
        )
        for aid, ts in raw_trace
    ]


# ---------------------------------------------------------------------------
# Main comparison logic
# ---------------------------------------------------------------------------


def run_comparison() -> dict:
    """Run ILP vs tiered solver comparison across all episodes.

    Returns:
        Results dict with per-episode details and aggregate metrics.
    """
    print("Loading episodes...")
    episodes = load_episodes()
    print(f"  Loaded {len(episodes)} episodes")

    print("Loading action traces...")
    action_traces = _load_original_action_traces()
    print(f"  Loaded {len(action_traces)} trace files")

    print("Loading CPG graph constraints...")
    all_graphs = _load_cpg_graph_constraints()
    print(f"  Loaded {len(all_graphs)} graphs: {sorted(all_graphs.keys())}")

    cost_cfg = CostConfig()
    tiered = ConformanceDistanceSolver(cost_cfg)
    ilp = ILPConformanceDistanceSolver(cost_cfg)

    per_episode: list[dict] = []
    d_tiered_vals: list[float] = []
    d_ilp_vals: list[float] = []

    n_skipped = 0
    n_no_trace = 0
    n_no_graph = 0

    for i, ep in enumerate(episodes):
        if i % 20 == 0:
            print(f"  Progress: {i}/{len(episodes)} episodes processed...")

        # Resolve graph name for this scenario
        raw_graph = SCENARIO_GRAPH.get(ep.scenario_id)
        if raw_graph is None:
            n_no_graph += 1
            n_skipped += 1
            continue

        # _load_cpg_graph_constraints keys by file stem; SCENARIO_GRAPH values
        # are already file stems (e.g. "ssc_sepsis_hour1", "aha_chest_pain").
        gdata = all_graphs.get(raw_graph)
        if gdata is None:
            n_no_graph += 1
            n_skipped += 1
            continue

        # Find action trace by source_file
        raw_trace = action_traces.get(ep.source_file)
        if not raw_trace:
            n_no_trace += 1
            n_skipped += 1
            continue

        constraints = _build_constraints_from_graph(gdata)
        actions = _build_action_trace(raw_trace)

        try:
            result_tiered = tiered.compute(actions, constraints)
            result_ilp = ilp.compute(actions, constraints)
        except Exception as exc:
            print(f"  WARNING: solver error for {ep.source_file}: {exc}")
            n_skipped += 1
            continue

        d_t = result_tiered.distance
        d_i = result_ilp.distance

        d_tiered_vals.append(d_t)
        d_ilp_vals.append(d_i)

        per_episode.append(
            {
                "source_file": ep.source_file,
                "scenario_id": ep.scenario_id,
                "model": ep.model,
                "run_index": ep.run_index,
                "graph": raw_graph,
                "n_constraints": len(constraints),
                "n_actions": len(actions),
                "d_tiered": d_t,
                "d_ilp": d_i,
                "diff": d_i - d_t,
                "equal": abs(d_i - d_t) < 1e-6,
            }
        )

    print(
        f"  Processed: {len(per_episode)} episodes | Skipped: {n_skipped} "
        f"(no_graph={n_no_graph}, no_trace={n_no_trace})"
    )

    # Aggregate metrics
    n_total = len(per_episode)
    if n_total == 0:
        print("  ERROR: No episodes processed — cannot compute metrics.")
        return {"error": "No episodes processed", "per_episode": []}

    arr_t = np.array(d_tiered_vals)
    arr_i = np.array(d_ilp_vals)
    diffs = arr_i - arr_t

    n_equal = int(np.sum(np.abs(diffs) < 1e-6))
    n_ilp_better = int(np.sum(diffs < -1e-6))  # ILP < tiered (joint repair found)
    n_tiered_better = int(np.sum(diffs > 1e-6))  # tiered < ILP (bug indicator)

    rho, p_val = spearmanr(arr_t, arr_i)

    diverged_episodes = [ep for ep in per_episode if not ep["equal"]]

    aggregate = {
        "n_episodes": n_total,
        "n_skipped": n_skipped,
        "n_equal": n_equal,
        "n_ilp_better": n_ilp_better,
        "n_tiered_better": n_tiered_better,
        "pct_equal": round(100.0 * n_equal / n_total, 2),
        "pct_ilp_better": round(100.0 * n_ilp_better / n_total, 2),
        "pct_tiered_better": round(100.0 * n_tiered_better / n_total, 2),
        "spearman_rho": round(float(rho), 6),
        "spearman_p": float(p_val),
        "mean_d_tiered": round(float(arr_t.mean()), 4),
        "mean_d_ilp": round(float(arr_i.mean()), 4),
        "mean_diff_ilp_minus_tiered": round(float(diffs.mean()), 4),
        "max_diff_ilp_minus_tiered": round(float(diffs.max()), 4),
        "min_diff_ilp_minus_tiered": round(float(diffs.min()), 4),
    }

    return {
        "aggregate": aggregate,
        "diverged_episodes": diverged_episodes,
        "per_episode": per_episode,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def _build_markdown(results: dict) -> str:
    """Build markdown summary report from results dict.

    Args:
        results: Output of run_comparison().

    Returns:
        Markdown string.
    """
    agg = results.get("aggregate", {})
    diverged = results.get("diverged_episodes", [])

    lines = [
        "# ILP vs Tiered d_G Solver Comparison",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Episodes processed | {agg.get('n_episodes', 0)} |",
        f"| Episodes skipped | {agg.get('n_skipped', 0)} |",
        f"| Equal (\\|d_ILP − d_tiered\\| < 1e-6) | {agg.get('n_equal', 0)} ({agg.get('pct_equal', 0):.1f}%) |",
        f"| ILP strictly better (joint repair) | {agg.get('n_ilp_better', 0)} ({agg.get('pct_ilp_better', 0):.1f}%) |",
        f"| Tiered strictly better (bug indicator) | "
        f"{agg.get('n_tiered_better', 0)} ({agg.get('pct_tiered_better', 0):.1f}%) |",
        f"| Spearman ρ (d_ILP vs d_tiered) | {agg.get('spearman_rho', 0):.6f} |",
        f"| Spearman p-value | {agg.get('spearman_p', 0):.4e} |",
        f"| Mean d_tiered | {agg.get('mean_d_tiered', 0):.4f} |",
        f"| Mean d_ILP | {agg.get('mean_d_ilp', 0):.4f} |",
        f"| Mean diff (ILP − tiered) | {agg.get('mean_diff_ilp_minus_tiered', 0):.4f} |",
        "",
        "## Interpretation",
        "",
        "- **n_tiered_better = 0**: ILP is never worse than tiered (correctness check).",
        "- **n_ilp_better > 0**: ILP found joint repairs that tiered solver missed.",
        "- **Spearman ρ ≈ 1.0**: Both solvers produce consistent relative rankings.",
        "",
    ]

    if diverged:
        lines += [
            f"## Diverged Episodes ({len(diverged)} total)",
            "",
            "| source_file | scenario | model | d_tiered | d_ilp | diff |",
            "|-------------|----------|-------|----------|-------|------|",
        ]
        for ep in diverged[:50]:
            lines.append(
                f"| {ep['source_file']} | {ep['scenario_id']} | {ep['model']} "
                f"| {ep['d_tiered']:.2f} | {ep['d_ilp']:.2f} | {ep['diff']:+.2f} |"
            )
        if len(diverged) > 50:
            lines.append(f"| ... | *(+{len(diverged) - 50} more)* | | | | |")
        lines.append("")
    else:
        lines += [
            "## Diverged Episodes",
            "",
            "None — all episodes have identical d_ILP and d_tiered.",
            "",
        ]

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run ILP vs tiered comparison and write outputs."""
    print("=" * 60)
    print("ILP vs Tiered d_G Solver Comparison")
    print("=" * 60)

    results = run_comparison()

    out_dir = EVIDENCE_DIR / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_path = out_dir / "exp_ilp_vs_tiered.json"
    md_path = out_dir / "exp_ilp_vs_tiered.md"

    save_json(results, json_path)

    md_text = _build_markdown(results)
    save_markdown(md_text, md_path)

    # Print summary to stdout
    agg = results.get("aggregate", {})
    print()
    print("=" * 60)
    print("RESULTS SUMMARY")
    print("=" * 60)
    print(f"  Episodes processed : {agg.get('n_episodes', 0)}")
    print(f"  Episodes skipped   : {agg.get('n_skipped', 0)}")
    print(f"  Equal              : {agg.get('n_equal', 0)} ({agg.get('pct_equal', 0):.1f}%)")
    print(f"  ILP better         : {agg.get('n_ilp_better', 0)} ({agg.get('pct_ilp_better', 0):.1f}%)")
    print(f"  Tiered better (bug): {agg.get('n_tiered_better', 0)} ({agg.get('pct_tiered_better', 0):.1f}%)")
    print(f"  Spearman rho       : {agg.get('spearman_rho', 0):.6f}  (p={agg.get('spearman_p', 0):.4e})")
    print(f"  Mean d_tiered      : {agg.get('mean_d_tiered', 0):.4f}")
    print(f"  Mean d_ilp         : {agg.get('mean_d_ilp', 0):.4f}")
    print(f"  Mean diff          : {agg.get('mean_diff_ilp_minus_tiered', 0):.4f}")
    print("=" * 60)


if __name__ == "__main__":
    main()
