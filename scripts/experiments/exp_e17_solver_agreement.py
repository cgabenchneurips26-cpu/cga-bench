#!/usr/bin/env python3
"""EX-17 — Solver Agreement: Tiered vs ILP on Full Dataset.

Defence target: Attack #4 "Solver exact/tiered conflation"
Previous result: ρ=0.965 on 108 episodes. This script runs on the full
canonical 14,826 episode set.

Outputs:
    evidence_pack/ex17_solver_agreement/ex17_solver_agreement.json
    evidence_pack/ex17_solver_agreement/ex17_solver_agreement.md
    evidence_pack/figures/ex17_scatter.png

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_e17_solver_agreement.py [--sample N]
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import sys
import time
from typing import Any

import numpy as np
from scipy.stats import spearmanr
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib
from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    GRAPHS_DIR,
    canonical_graph_id,
    load_all_scenarios,
    save_json,
    save_markdown,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from cga_bench.cpg_model.conformance_distance import (
    ConformanceDistanceSolver,
    ConstraintType,
    CostConfig,
    HardConstraint,
)
from cga_bench.cpg_model.conformance_distance_ilp import ILPConformanceDistanceSolver
from cga_bench.cpg_model.schemas.base import Action, ActionType

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
VM_PATH = ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
EPISODES_DIR = ROOT / "results" / "full_706_v5"
OUTPUT_DIR = EVIDENCE_DIR / "ex17_solver_agreement"


# ---------------------------------------------------------------------------
# Graph constraint extraction (standalone, no gap_experiments dependency)
# ---------------------------------------------------------------------------


def load_graph_constraints(graph_path: Path) -> dict[str, Any]:
    """Load a CPG graph YAML and extract constraint data."""
    with open(graph_path) as f:
        graph = yaml.safe_load(f)

    forbidden_map: dict[str, list[str]] = {}
    mandatory_map: dict[str, list[str]] = {}
    prior_map: dict[str, dict[str, list[str]]] = {}
    deadline_map: dict[str, dict[str, float]] = {}
    evidence_map: dict[str, str] = {}

    nodes = graph.get("nodes", {})
    if isinstance(nodes, dict):
        node_items = list(nodes.items())
    elif isinstance(nodes, list):
        node_items = [(n.get("node_id", f"node_{i}"), n) for i, n in enumerate(nodes)]
    else:
        return {}

    for node_id, node in node_items:
        if not isinstance(node, dict):
            continue

        # Evidence level
        ev = node.get("evidence_level", "B")
        evidence_map[node_id] = "STRONG" if ev == "A" else "MODERATE"

        # Forbidden
        fa = node.get("forbidden_actions", [])
        if fa and isinstance(fa, list):
            forbidden_map[node_id] = fa

        # Mandatory
        ma = node.get("mandatory_actions", [])
        if ma and isinstance(ma, list):
            mandatory_map[node_id] = ma

        # Deadlines
        dl = node.get("deadlines", {})
        if dl and isinstance(dl, dict):
            deadline_map[node_id] = {k: float(v) for k, v in dl.items()}

        # Prior actions (sequence constraints)
        pa = node.get("required_prior_actions", {})
        if pa and isinstance(pa, dict):
            prior_map[node_id] = {}
            for dep, priors in pa.items():
                if isinstance(priors, str):
                    priors = [priors]
                prior_map[node_id][dep] = priors

    return {
        "forbidden": forbidden_map,
        "mandatory": mandatory_map,
        "deadlines": deadline_map,
        "prior_actions": prior_map,
        "evidence": evidence_map,
    }


def build_constraints(gdata: dict[str, Any]) -> list[HardConstraint]:
    """Build HardConstraint list from graph constraint data."""
    constraints: list[HardConstraint] = []

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

    for node_id, prior_dict in gdata.get("prior_actions", {}).items():
        for dependent, priors in prior_dict.items():
            for prior in priors:
                constraints.append(
                    HardConstraint(
                        type=ConstraintType.BEFORE,
                        actions=[prior, dependent],
                        severity="HIGH",
                        provenance=f"graph:{node_id}:before:{prior}->{dependent}",
                    )
                )

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

    # Deduplicate
    seen: set[tuple[str, tuple[str, ...], float | None]] = set()
    unique: list[HardConstraint] = []
    for c in constraints:
        key = (c.type.value, tuple(c.actions), c.deadline)
        if key not in seen:
            seen.add(key)
            unique.append(c)
    return unique


def build_action_trace(ep: dict[str, Any]) -> list[Action]:
    """Extract Action trace from episode JSON."""
    actions: list[Action] = []
    for a in ep.get("actions", []):
        if not isinstance(a, dict):
            continue
        aid = a.get("action_id", "")
        if not aid:
            continue
        actions.append(
            Action(
                type=ActionType.PROCEDURE,
                action_id=aid,
                args=a.get("args", {}),
                timestamp_minutes=float(a.get("timestamp_minutes", 0.0)),
            )
        )
    return actions


# ---------------------------------------------------------------------------
# Scenario → graph mapping
# ---------------------------------------------------------------------------


def build_scenario_graph_map() -> dict[str, str]:
    """Map scenario_id → canonical graph_id."""
    scenarios = load_all_scenarios(tag_source=True)
    mapping: dict[str, str] = {}
    for sc in scenarios:
        sid = sc.get("scenario_id", "")
        gid = sc.get("_canonical_graph_id", "")
        if sid and gid:
            mapping[sid] = gid
    return mapping


# ---------------------------------------------------------------------------
# Main comparison
# ---------------------------------------------------------------------------


def run_comparison(sample_n: int = 0) -> dict[str, Any]:
    """Run tiered vs ILP solver on canonical episodes."""
    # Load canonical episode keys
    vm = json.loads(VM_PATH.read_text())
    canonical_keys: set[str] = set()
    for rec in vm.get("per_episode", []):
        k = f"{rec.get('model_dir', '')}_{rec.get('scenario_id', '')}_{rec.get('run_index', 0)}"
        canonical_keys.add(k)
    print(f"Canonical set: {len(canonical_keys)} episodes")

    # Scenario → graph mapping
    sg_map = build_scenario_graph_map()

    # Pre-load all graph constraints
    graph_cache: dict[str, list[HardConstraint]] = {}
    for gpath in GRAPHS_DIR.glob("*.yaml"):
        gid = gpath.stem
        gdata = load_graph_constraints(gpath)
        constraints = build_constraints(gdata)
        if constraints:
            graph_cache[gid] = constraints
    print(f"Loaded constraints for {len(graph_cache)} graphs")

    # Load episode JSONs (deduplicate: first file wins per canonical key)
    episodes: list[dict[str, Any]] = []
    seen_keys: set[str] = set()
    for model_dir in sorted(EPISODES_DIR.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        model_name = model_dir.name
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                ep = json.load(open(ep_file))
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(ep, dict) or not ep.get("scenario_id"):
                continue

            sid = ep["scenario_id"]
            run_idx = ep.get("run_index", 0)
            key = f"{model_name}_{sid}_{run_idx}"
            if key not in canonical_keys:
                continue
            if key in seen_keys:
                continue
            seen_keys.add(key)

            ep["_model"] = model_name
            ep["_key"] = key
            episodes.append(ep)

    print(f"Loaded {len(episodes)} canonical episodes from disk")

    # Optional sampling
    if sample_n > 0 and sample_n < len(episodes):
        rng = np.random.default_rng(42)
        indices = rng.choice(len(episodes), size=sample_n, replace=False)
        episodes = [episodes[i] for i in sorted(indices)]
        print(f"Sampled {len(episodes)} episodes")

    # Run solvers
    cost_cfg = CostConfig()
    tiered = ConformanceDistanceSolver(cost_cfg)
    ilp = ILPConformanceDistanceSolver(cost_cfg)

    per_episode: list[dict[str, Any]] = []
    d_tiered_vals: list[float] = []
    d_ilp_vals: list[float] = []
    n_skipped = 0
    n_no_graph = 0

    t0 = time.time()
    for i, ep in enumerate(episodes):
        if i % 500 == 0:
            elapsed = time.time() - t0
            rate = i / elapsed if elapsed > 0 else 0
            print(f"  [{i}/{len(episodes)}] {rate:.1f} ep/s | skipped={n_skipped}")

        sid = ep["scenario_id"]
        gid = canonical_graph_id(sg_map.get(sid, ""))
        if not gid or gid not in graph_cache:
            n_no_graph += 1
            n_skipped += 1
            continue

        constraints = graph_cache[gid]
        actions = build_action_trace(ep)
        if not actions:
            n_skipped += 1
            continue

        try:
            result_tiered = tiered.compute(actions, constraints)
            result_ilp = ilp.compute(actions, constraints)
        except Exception as exc:
            logger.warning("Solver error for %s: %s", sid, exc)
            n_skipped += 1
            continue

        d_t = result_tiered.distance
        d_i = result_ilp.distance

        d_tiered_vals.append(d_t)
        d_ilp_vals.append(d_i)

        per_episode.append(
            {
                "scenario_id": sid,
                "model": ep["_model"],
                "run_index": ep.get("run_index", 0),
                "graph": gid,
                "n_constraints": len(constraints),
                "n_actions": len(actions),
                "d_tiered": round(d_t, 2),
                "d_ilp": round(d_i, 2),
                "diff": round(d_i - d_t, 2),
                "equal": abs(d_i - d_t) < 1e-6,
            }
        )

    elapsed_total = time.time() - t0
    print(
        f"\nProcessed {len(per_episode)} episodes in {elapsed_total:.1f}s "
        f"({len(per_episode) / elapsed_total:.1f} ep/s) | Skipped: {n_skipped}"
    )

    # Aggregate
    n_total = len(per_episode)
    if n_total == 0:
        return {"error": "No episodes processed", "per_episode": []}

    arr_t = np.array(d_tiered_vals)
    arr_i = np.array(d_ilp_vals)
    diffs = arr_i - arr_t

    n_equal = int(np.sum(np.abs(diffs) < 1e-6))
    n_ilp_better = int(np.sum(diffs < -1e-6))
    n_tiered_better = int(np.sum(diffs > 1e-6))

    rho, p_val = spearmanr(arr_t, arr_i)

    aggregate = {
        "n_episodes": n_total,
        "n_skipped": n_skipped,
        "n_no_graph": n_no_graph,
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
        "elapsed_seconds": round(elapsed_total, 1),
    }

    # auto_numbers values
    auto_numbers = {
        "solverILPRho": aggregate["spearman_rho"],
        "solverILPPct": aggregate["pct_ilp_better"],
        "solverILPEqual": aggregate["pct_equal"],
        "solverTieredBetter": aggregate["pct_tiered_better"],
        "solverSubsetN": n_total,
    }

    # Save full per-episode pairs for scatter plot generation
    full_pairs_path = OUTPUT_DIR / "solver_pairs_full.json"
    full_pairs_path.parent.mkdir(parents=True, exist_ok=True)
    with open(full_pairs_path, "w") as fp:
        json.dump(per_episode, fp)
    print(f"Saved {len(per_episode)} full per-episode pairs → {full_pairs_path}")

    return {
        "aggregate": aggregate,
        "auto_numbers": auto_numbers,
        "diverged_episodes": [ep for ep in per_episode if not ep["equal"]][:100],
        "n_diverged_total": sum(1 for ep in per_episode if not ep["equal"]),
    }


# ---------------------------------------------------------------------------
# Scatter plot
# ---------------------------------------------------------------------------


def make_scatter(results: dict[str, Any]) -> None:
    """Generate tiered vs ILP scatter plot."""
    diverged = results.get("diverged_episodes", [])
    if not diverged:
        return

    d_t = [ep["d_tiered"] for ep in diverged]
    d_i = [ep["d_ilp"] for ep in diverged]

    fig, ax = plt.subplots(figsize=(6, 6))
    ax.scatter(d_t, d_i, alpha=0.3, s=10, color="steelblue")

    lim = max(max(d_t, default=1), max(d_i, default=1)) * 1.05
    ax.plot([0, lim], [0, lim], "k--", alpha=0.3, label="d_ILP = d_tiered")
    ax.set_xlabel("d_G (tiered)")
    ax.set_ylabel("d_G (ILP)")
    ax.set_title(f"EX-17: Solver Agreement (n={results['aggregate']['n_episodes']})")
    agg = results["aggregate"]
    ax.text(0.05, 0.92, f"ρ = {agg['spearman_rho']:.4f}", transform=ax.transAxes, fontsize=10)
    ax.legend(loc="lower right")
    ax.set_xlim(0, lim)
    ax.set_ylim(0, lim)
    fig.tight_layout()

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / "ex17_scatter.png", dpi=150)
    plt.close(fig)
    print(f"Saved: {FIGURES_DIR / 'ex17_scatter.png'}")


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def build_markdown(results: dict[str, Any]) -> str:
    """Build markdown report."""
    agg = results.get("aggregate", {})
    an = results.get("auto_numbers", {})

    lines = [
        "# EX-17: Solver Agreement — Tiered vs ILP (Full Dataset)",
        "",
        f"**Episodes processed**: {agg.get('n_episodes', 0)}",
        f"**Skipped**: {agg.get('n_skipped', 0)} (no_graph={agg.get('n_no_graph', 0)})",
        f"**Runtime**: {agg.get('elapsed_seconds', 0):.1f}s",
        "",
        "## Summary",
        "",
        "| Metric | Value |",
        "|--------|-------|",
        f"| Equal (|diff| < 1e-6) | {agg.get('n_equal', 0)} ({agg.get('pct_equal', 0)}%) |",
        f"| ILP strictly better | {agg.get('n_ilp_better', 0)} ({agg.get('pct_ilp_better', 0)}%) |",
        f"| Tiered strictly better | {agg.get('n_tiered_better', 0)} ({agg.get('pct_tiered_better', 0)}%) |",
        f"| Spearman ρ | {agg.get('spearman_rho', 0)} |",
        f"| Spearman p | {agg.get('spearman_p', 0):.4e} |",
        f"| Mean d_tiered | {agg.get('mean_d_tiered', 0)} |",
        f"| Mean d_ILP | {agg.get('mean_d_ilp', 0)} |",
        "",
        "## auto_numbers",
        "",
    ]
    for k, v in an.items():
        lines.append(f"- `\\{k}` = {v}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="EX-17 Solver Agreement")
    parser.add_argument("--sample", type=int, default=0, help="Sample N episodes (0 = all)")
    args = parser.parse_args()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("EX-17: Solver Agreement — Tiered vs ILP")
    print("=" * 60)

    results = run_comparison(sample_n=args.sample)

    save_json(results, OUTPUT_DIR / "ex17_solver_agreement.json")

    md = build_markdown(results)
    save_markdown(md, OUTPUT_DIR / "ex17_solver_agreement.md")

    make_scatter(results)

    agg = results.get("aggregate", {})
    an = results.get("auto_numbers", {})
    print("\n=== Results ===")
    print(f"  ρ = {agg.get('spearman_rho', 0)}")
    print(f"  Equal: {agg.get('pct_equal', 0)}%")
    print(f"  ILP better: {agg.get('pct_ilp_better', 0)}%")
    print(f"  Tiered better: {agg.get('pct_tiered_better', 0)}%")
    print("\nauto_numbers:")
    for k, v in an.items():
        print(f"  \\{k}{{{v}}}")
