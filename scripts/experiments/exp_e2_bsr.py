#!/usr/bin/env python3
"""EXP-E2: Blind Spot Rate (BSR) per Evaluator.

Computes the Blind Spot Rate for each of 6 evaluators:
  DxEM, AC-Proxy, MAB-Proxy, C2>=0.7, ACov>=0.5, CGA-Bench

BSR(e) = count(pass_e AND v4_hard) / N_EPISODES

Also characterises false-accept episodes by violation count and
violation-type distribution per evaluator.

Outputs:
  evidence_pack/exp_e2_bsr.json
  evidence_pack/tables/bsr_by_evaluator.tex

Usage:
    PYTHONPATH=. python scripts/experiments/exp_e2_bsr.py
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import sys
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.experiments._common import (
    EVIDENCE_DIR,
    TABLES_DIR,
    save_json,
    save_latex_table,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

VERDICT_MATRIX_PATH = EVIDENCE_DIR / "analysis" / "verdict_matrix_v6.json"
OUTPUT_JSON_PATH = EVIDENCE_DIR / "exp_e2_bsr.json"
OUTPUT_TEX_PATH = TABLES_DIR / "bsr_by_evaluator.tex"

N_EPISODES: int = 0  # set dynamically in main()

# Ordered list of evaluator descriptors
EVALUATOR_NAMES: list[str] = [
    "DxEM",
    "AC-Proxy",
    "MAB-Proxy",
    "C2 (>=0.7)",
    "ACov (>=0.5)",
    "CGA-Bench",
]


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_per_episode(path: Path) -> list[dict[str, Any]]:
    """Load per_episode array from verdict_matrix_v6.json.

    Args:
        path: Path to verdict_matrix_v6.json.

    Returns:
        List of episode dicts.
    """
    with open(path) as f:
        data = json.load(f)
    episodes: list[dict[str, Any]] = data["per_episode"]
    print(f"  Loaded {len(episodes)} episodes from {path.name}")
    return episodes


# ---------------------------------------------------------------------------
# Evaluator pass determination
# ---------------------------------------------------------------------------


def evaluator_passes(ep: dict[str, Any], name: str) -> bool:
    """Return True if evaluator passes this episode.

    Pass criteria:
      DxEM       -> ep["dxem"]
      AC-Proxy   -> ep["ac_proxy"]
      MAB-Proxy  -> ep["mab_proxy"]
      C2 (>=0.7) -> ep["c2_pass"]   (field already encodes >= 0.7 threshold)
      ACov (>=0.5) -> ep["acov_pass"] (field already encodes >= 0.5 threshold)
      CGA-Bench  -> not ep["v4_hard"]

    Args:
        ep: Single episode dict.
        name: Evaluator name (must be one of EVALUATOR_NAMES).

    Returns:
        True if evaluator passes.

    Raises:
        ValueError: If name is not a recognised evaluator.
    """
    if name == "DxEM":
        return bool(ep["dxem"])
    if name == "AC-Proxy":
        return bool(ep["ac_proxy"])
    if name == "MAB-Proxy":
        return bool(ep["mab_proxy"])
    if name == "C2 (>=0.7)":
        return bool(ep["c2_pass"])
    if name == "ACov (>=0.5)":
        return bool(ep["acov_pass"])
    if name == "CGA-Bench":
        return not bool(ep["v4_hard"])
    raise ValueError(f"Unknown evaluator name: {name!r}")


# ---------------------------------------------------------------------------
# BSR computation
# ---------------------------------------------------------------------------


def compute_bsr(
    episodes: list[dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Compute Blind Spot Rate for each evaluator.

    BSR(e) = count(pass_e AND v4_hard=True) / N_EPISODES

    For each false-accept episode, records n_viols and viol_types.

    Args:
        episodes: List of episode dicts.

    Returns:
        Dict mapping evaluator name to BSR metrics.
    """
    results: dict[str, dict[str, Any]] = {}

    for name in EVALUATOR_NAMES:
        fa_episodes: list[dict[str, Any]] = []

        for ep in episodes:
            if evaluator_passes(ep, name) and ep["v4_hard"]:
                fa_episodes.append(ep)

        bsr_count = len(fa_episodes)
        bsr_rate = bsr_count / N_EPISODES

        # n_viols distribution across FA episodes
        n_viols_list = [int(ep.get("n_viols", 0)) for ep in fa_episodes]
        viol_type_counter: Counter[str] = Counter()
        for ep in fa_episodes:
            viol_type_counter.update(ep.get("viol_types", []))

        # Median n_viols
        if n_viols_list:
            sorted_viols = sorted(n_viols_list)
            mid = len(sorted_viols) // 2
            if len(sorted_viols) % 2 == 0:
                median_n_viols = (sorted_viols[mid - 1] + sorted_viols[mid]) / 2.0
            else:
                median_n_viols = float(sorted_viols[mid])
        else:
            median_n_viols = 0.0

        results[name] = {
            "bsr_count": bsr_count,
            "bsr_rate": round(bsr_rate, 4),
            "fa_episode_ids": [ep["episode_id"] for ep in fa_episodes],
            "n_viols_list": n_viols_list,
            "median_n_viols": median_n_viols,
            "viol_types_distribution": dict(viol_type_counter),
        }

    return results


def compute_bsr_by_constraint_type(
    bsr_results: dict[str, dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Compute viol_types distribution (as fractions) among FA episodes per evaluator.

    Args:
        bsr_results: Output of compute_bsr().

    Returns:
        Dict mapping evaluator name to dict of viol_type -> fraction of FA episodes.
    """
    constraint_dist: dict[str, dict[str, float]] = {}

    for name, res in bsr_results.items():
        total_fa = res["bsr_count"]
        viol_dist_raw = res["viol_types_distribution"]

        if total_fa == 0:
            constraint_dist[name] = {}
            continue

        # Normalise counts by number of FA episodes
        constraint_dist[name] = {vtype: round(count / total_fa, 4) for vtype, count in viol_dist_raw.items()}

    return constraint_dist


# ---------------------------------------------------------------------------
# LaTeX table generation
# ---------------------------------------------------------------------------


def build_latex_table(
    bsr_results: dict[str, dict[str, Any]],
    constraint_dist: dict[str, dict[str, float]],
) -> None:
    """Generate LaTeX booktabs table for BSR by evaluator.

    Columns: Evaluator | BSR Count | BSR Rate | Median Viols | Top Constraint Type

    Args:
        bsr_results: Output of compute_bsr().
        constraint_dist: Output of compute_bsr_by_constraint_type().
    """
    headers = [
        "Evaluator",
        "BSR Count",
        "BSR Rate",
        "Median Viols",
        "Top Constraint Type",
    ]
    rows: list[list[str]] = []

    for name in EVALUATOR_NAMES:
        res = bsr_results[name]
        dist = constraint_dist.get(name, {})

        top_constraint = max(dist, key=lambda k: dist[k]) if dist else "--"

        rows.append(
            [
                name,
                str(res["bsr_count"]),
                f"{res['bsr_rate']:.4f}",
                f"{res['median_n_viols']:.1f}",
                top_constraint,
            ]
        )

    save_latex_table(
        rows=rows,
        headers=headers,
        path=OUTPUT_TEX_PATH,
        caption=(
            "Blind Spot Rate (BSR) per evaluator. "
            f"BSR = count(pass AND v4\\_hard=True) / {N_EPISODES}. "
            "Top Constraint Type is the most frequent violation type "
            "among false-accept episodes."
        ),
        label="tab:bsr_by_evaluator",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run EXP-E2: Blind Spot Rate per evaluator analysis."""
    print("=" * 60)
    print("EXP-E2: Blind Spot Rate (BSR) per Evaluator")
    print("=" * 60)

    global N_EPISODES
    print("\n[1/4] Loading verdict matrix...")
    episodes = load_per_episode(VERDICT_MATRIX_PATH)
    N_EPISODES = len(episodes)
    print(f"  N_EPISODES = {N_EPISODES}")

    print("\n[2/4] Computing BSR per evaluator...")
    bsr_results = compute_bsr(episodes)
    print(f"  {'Evaluator':<20} {'BSR Count':>10} {'BSR Rate':>10} {'Med Viols':>10}")
    print("  " + "-" * 52)
    for name in EVALUATOR_NAMES:
        res = bsr_results[name]
        print(f"  {name:<20} {res['bsr_count']:>10} {res['bsr_rate']:>10.4f} {res['median_n_viols']:>10.1f}")

    print("\n[3/4] Computing BSR by constraint type...")
    constraint_dist = compute_bsr_by_constraint_type(bsr_results)
    for name in EVALUATOR_NAMES:
        dist = constraint_dist.get(name, {})
        if dist:
            dist_str = ", ".join(f"{k}={v:.2f}" for k, v in sorted(dist.items(), key=lambda x: -x[1]))
            print(f"  {name}: {dist_str}")
        else:
            print(f"  {name}: (no FA episodes)")

    print("\n[4/4] Saving outputs...")
    output = {
        "experiment": "exp_e2_bsr",
        "n_episodes": N_EPISODES,
        "evaluators": EVALUATOR_NAMES,
        "bsr_results": bsr_results,
        "bsr_by_constraint_type": constraint_dist,
    }
    save_json(output, OUTPUT_JSON_PATH)
    build_latex_table(bsr_results, constraint_dist)

    print("\nDone.")
    highest_bsr = max(EVALUATOR_NAMES, key=lambda n: bsr_results[n]["bsr_rate"])
    lowest_bsr = min(EVALUATOR_NAMES, key=lambda n: bsr_results[n]["bsr_rate"])
    print(f"  Highest BSR: {highest_bsr} ({bsr_results[highest_bsr]['bsr_rate']:.4f})")
    print(f"  Lowest  BSR: {lowest_bsr} ({bsr_results[lowest_bsr]['bsr_rate']:.4f})")


if __name__ == "__main__":
    main()
