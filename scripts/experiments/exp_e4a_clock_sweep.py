#!/usr/bin/env python3
"""EX-4A — Clock Sweep: Timing Constraint Robustness.

Defence target: Attack #11 "Timing dominance / timing = clock artifact"
Tests whether TCC WITHIN-constraint verdicts are robust to the choice of
clock step size (default = 5 min).

For step sizes [2, 5, 10, 15, 20] min, we remap each episode's action
timestamps (index * step) and re-evaluate all WITHIN deadline constraints.
If most episodes keep the same WITHIN-violation status across step sizes,
the timing signal is not a clock artifact.

Outputs:
    evidence_pack/ex4a_clock_sweep/ex4a_clock_sweep.json
    evidence_pack/ex4a_clock_sweep/ex4a_clock_sweep.md
    evidence_pack/figures/ex4a_clock_sweep.png

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_e4a_clock_sweep.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Any

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    GRAPHS_DIR,
    canonical_graph_id,
    load_all_scenarios,
    save_json,
    save_markdown,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
VM_PATH = ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
EPISODES_DIR = ROOT / "results" / "full_706_v5"
OUTPUT_DIR = EVIDENCE_DIR / "ex4a_clock_sweep"

STEP_SIZES = [2, 5, 10, 15, 20]
BASELINE_STEP = 5


# ---------------------------------------------------------------------------
# Graph deadline extraction
# ---------------------------------------------------------------------------


def load_graph_deadlines(graph_path: Path) -> dict[str, float]:
    """Extract action_id → deadline_minutes from a graph YAML."""
    with open(graph_path) as f:
        graph = yaml.safe_load(f)

    deadlines: dict[str, float] = {}
    nodes = graph.get("nodes", {})
    if isinstance(nodes, dict):
        node_items = list(nodes.values())
    elif isinstance(nodes, list):
        node_items = nodes
    else:
        return deadlines

    for node in node_items:
        if not isinstance(node, dict):
            continue
        dl = node.get("deadlines", {})
        if isinstance(dl, dict):
            for action_id, deadline in dl.items():
                try:
                    d = float(deadline)
                except (TypeError, ValueError):
                    continue
                # Keep the tightest deadline per action
                if action_id not in deadlines or d < deadlines[action_id]:
                    deadlines[action_id] = d
    return deadlines


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
# WITHIN evaluation at different step sizes
# ---------------------------------------------------------------------------


def evaluate_within_at_step(
    actions: list[dict[str, Any]],
    deadlines: dict[str, float],
    step_size: float,
) -> dict[str, Any]:
    """Evaluate WITHIN constraints for a trace with remapped timestamps.

    Returns:
        n_checked: number of actions with a deadline constraint
        n_violated: number of WITHIN violations
        violated_actions: list of (action_id, new_timestamp, deadline)
    """
    n_checked = 0
    n_violated = 0
    violated: list[tuple[str, float, float]] = []

    for idx, action in enumerate(actions):
        aid = action.get("action_id", "")
        if aid in deadlines:
            n_checked += 1
            new_ts = idx * step_size
            deadline = deadlines[aid]
            if new_ts > deadline:
                n_violated += 1
                violated.append((aid, new_ts, deadline))

    return {
        "n_checked": n_checked,
        "n_violated": n_violated,
        "has_within_violation": n_violated > 0,
        "violated_actions": violated,
    }


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def run_analysis() -> dict[str, Any]:
    """Run clock sweep analysis."""
    # Load canonical set
    vm = json.loads(VM_PATH.read_text())
    canonical_keys: set[str] = set()
    for rec in vm.get("per_episode", []):
        k = f"{rec.get('model_dir', '')}_{rec.get('scenario_id', '')}_{rec.get('run_index', 0)}"
        canonical_keys.add(k)
    print(f"Canonical set: {len(canonical_keys)} episodes")

    # Scenario → graph mapping
    sg_map = build_scenario_graph_map()

    # Pre-load all graph deadlines
    deadline_cache: dict[str, dict[str, float]] = {}
    n_total_deadlines = 0
    for gpath in GRAPHS_DIR.glob("*.yaml"):
        if gpath.parent.name == "_archive":
            continue
        gid = gpath.stem
        dls = load_graph_deadlines(gpath)
        if dls:
            deadline_cache[gid] = dls
            n_total_deadlines += len(dls)
    print(f"Loaded deadlines for {len(deadline_cache)} graphs ({n_total_deadlines} total)")

    # Load episode actions from disk (deduplicate: first file wins per canonical key)
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

    # Run sweep
    t0 = time.time()
    # For each episode, compute WITHIN results at each step size
    # Track: baseline verdict (step=5) vs other steps
    step_results: dict[int, dict[str, int]] = {}
    for s in STEP_SIZES:
        step_results[s] = {
            "n_evaluated": 0,
            "n_with_deadlines": 0,
            "n_within_violation": 0,
            "n_flip_from_baseline": 0,
        }

    n_skipped = 0
    n_no_deadlines = 0

    for i, ep in enumerate(episodes):
        if i % 2000 == 0:
            elapsed = time.time() - t0
            print(f"  [{i}/{len(episodes)}] {elapsed:.1f}s")

        sid = ep["scenario_id"]
        gid = canonical_graph_id(sg_map.get(sid, ""))
        if not gid or gid not in deadline_cache:
            n_skipped += 1
            continue

        deadlines = deadline_cache[gid]
        actions = ep.get("actions", [])
        if not actions:
            n_skipped += 1
            continue

        # Evaluate baseline first, then all step sizes
        baseline_result = evaluate_within_at_step(actions, deadlines, float(BASELINE_STEP))
        baseline_violated = baseline_result["has_within_violation"]

        for s in STEP_SIZES:
            if s == BASELINE_STEP:
                result = baseline_result
            else:
                result = evaluate_within_at_step(actions, deadlines, float(s))

            step_results[s]["n_evaluated"] += 1
            if result["n_checked"] > 0:
                step_results[s]["n_with_deadlines"] += 1
            if result["has_within_violation"]:
                step_results[s]["n_within_violation"] += 1

            if s != BASELINE_STEP and result["has_within_violation"] != baseline_violated:
                step_results[s]["n_flip_from_baseline"] += 1

    elapsed_total = time.time() - t0
    print(f"\nProcessed in {elapsed_total:.1f}s | Skipped: {n_skipped}")

    # Build aggregate table
    n_eval = step_results[BASELINE_STEP]["n_evaluated"]
    sweep_table: list[dict[str, Any]] = []
    max_flip_pct = 0.0

    for s in STEP_SIZES:
        sr = step_results[s]
        n_e = sr["n_evaluated"]
        viol_rate = 100.0 * sr["n_within_violation"] / n_e if n_e > 0 else 0.0
        flip_rate = 100.0 * sr["n_flip_from_baseline"] / n_e if n_e > 0 and s != BASELINE_STEP else 0.0

        if s != BASELINE_STEP:
            max_flip_pct = max(max_flip_pct, flip_rate)

        sweep_table.append(
            {
                "step_minutes": s,
                "n_evaluated": n_e,
                "n_with_deadlines": sr["n_with_deadlines"],
                "n_within_violation": sr["n_within_violation"],
                "within_violation_rate": round(viol_rate, 2),
                "n_flip_from_baseline": sr["n_flip_from_baseline"],
                "flip_rate": round(flip_rate, 2),
            }
        )

    auto_numbers = {
        "clockSweepMaxFlip": round(max_flip_pct, 1),
        "clockSweepSteps": len(STEP_SIZES),
        "clockSweepBaseline": BASELINE_STEP,
        "clockSweepN": n_eval,
    }

    return {
        "description": "EX-4A: Clock Sweep — Timing Constraint Robustness (Attack #11 defense)",
        "step_sizes": STEP_SIZES,
        "baseline_step": BASELINE_STEP,
        "n_episodes": n_eval,
        "n_skipped": n_skipped,
        "sweep_table": sweep_table,
        "max_flip_pct": round(max_flip_pct, 1),
        "elapsed_seconds": round(elapsed_total, 1),
        "auto_numbers": auto_numbers,
    }


# ---------------------------------------------------------------------------
# Plot
# ---------------------------------------------------------------------------


def make_plot(result: dict[str, Any]) -> None:
    """Generate clock sweep line plot."""
    table = result.get("sweep_table", [])
    if not table:
        return

    steps = [r["step_minutes"] for r in table]
    viol_rates = [r["within_violation_rate"] for r in table]
    flip_rates = [r["flip_rate"] for r in table]

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(10, 4))

    # Left: violation rate vs step size
    ax1.plot(steps, viol_rates, "o-", color="steelblue", linewidth=2)
    ax1.axvline(x=BASELINE_STEP, color="gray", linestyle="--", alpha=0.5, label="baseline (5 min)")
    ax1.set_xlabel("Step Size (minutes)")
    ax1.set_ylabel("WITHIN Violation Rate (%)")
    ax1.set_title("Violation Rate vs Clock Step")
    ax1.legend()
    ax1.set_xticks(steps)

    # Right: flip rate vs step size
    ax2.bar(
        [s for s in steps if s != BASELINE_STEP],
        [r for s, r in zip(steps, flip_rates) if s != BASELINE_STEP],
        color="coral",
        alpha=0.7,
    )
    ax2.set_xlabel("Step Size (minutes)")
    ax2.set_ylabel("Verdict Flip Rate vs Baseline (%)")
    ax2.set_title("Verdict Stability")
    ax2.set_xticks([s for s in steps if s != BASELINE_STEP])

    fig.suptitle(f"EX-4A: Clock Sweep (n={result['n_episodes']})", fontsize=12)
    fig.tight_layout()

    FIGURES_DIR.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIGURES_DIR / "ex4a_clock_sweep.png", dpi=150)
    plt.close(fig)
    print(f"Saved: {FIGURES_DIR / 'ex4a_clock_sweep.png'}")


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------


def build_markdown(result: dict[str, Any]) -> str:
    """Build markdown report."""
    an = result.get("auto_numbers", {})
    lines = [
        "# EX-4A: Clock Sweep — Timing Constraint Robustness",
        "",
        f"**Episodes**: {result['n_episodes']}",
        f"**Baseline step**: {result['baseline_step']} min",
        f"**Step sizes tested**: {result['step_sizes']}",
        f"**Max verdict flip**: {result['max_flip_pct']}%",
        "",
        "## Sweep Results",
        "",
        "| Step (min) | WITHIN Viol (%) | Flip vs Baseline (%) | N Violations | N Flips |",
        "|------------|-----------------|---------------------|--------------|---------|",
    ]

    for r in result.get("sweep_table", []):
        baseline_marker = " *" if r["step_minutes"] == BASELINE_STEP else ""
        lines.append(
            f"| {r['step_minutes']}{baseline_marker} | {r['within_violation_rate']} | "
            f"{r['flip_rate']} | {r['n_within_violation']} | {r['n_flip_from_baseline']} |"
        )

    lines.extend(
        [
            "",
            "## Interpretation",
            "",
            "If the max flip rate is low (<15%), the WITHIN-constraint verdicts are robust",
            "to clock granularity and the timing signal is NOT a clock artifact.",
            "",
            "## auto_numbers",
            "",
        ]
    )
    for k, v in an.items():
        lines.append(f"- `\\{k}` = {v}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 60)
    print("EX-4A: Clock Sweep — Timing Constraint Robustness")
    print("=" * 60)

    result = run_analysis()

    save_json(result, OUTPUT_DIR / "ex4a_clock_sweep.json")

    md = build_markdown(result)
    save_markdown(md, OUTPUT_DIR / "ex4a_clock_sweep.md")

    make_plot(result)

    an = result["auto_numbers"]
    print("\n=== Results ===")
    for r in result.get("sweep_table", []):
        marker = " <-- baseline" if r["step_minutes"] == BASELINE_STEP else ""
        print(f"  step={r['step_minutes']}min: viol={r['within_violation_rate']}%, flip={r['flip_rate']}%{marker}")
    print(f"\nMax flip: {result['max_flip_pct']}%")
    print("\nauto_numbers:")
    for k, v in an.items():
        print(f"  \\{k}{{{v}}}")
