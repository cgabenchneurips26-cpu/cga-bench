#!/usr/bin/env python3
"""EXP-E1: Verdict-Flip Prevalence and False-Accept Rate Analysis.

Quantifies verdict-flip prevalence and false-accept rates across 4 independent
evaluators (AC-Proxy, MAB-Proxy, C2, CGA-Bench) over 180 episodes.

Definitions:
  - Verdict-flip: episode where >= 1 evaluator pair disagrees
  - False-Accept: evaluator passes an episode that v4_hard=True flagged
  - All-process-oblivious FA: DxEM+AC-Proxy+C2 all pass AND v4_hard=True

Outputs:
  evidence_pack/exp_e1_verdict_flip.json
  evidence_pack/tables/verdict_flip_matrix.tex

Usage:
    PYTHONPATH=. python scripts/experiments/exp_e1_verdict_flip.py
"""

from __future__ import annotations

from itertools import combinations
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
OUTPUT_JSON_PATH = EVIDENCE_DIR / "exp_e1_verdict_flip.json"
OUTPUT_TEX_PATH = TABLES_DIR / "verdict_flip_matrix.tex"

N_EPISODES: int = 0  # set dynamically in main()

# 4-evaluator names and their episode field accessors
EVALUATOR_NAMES: list[str] = ["AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]

# All C(4,2) = 6 pairs
EVALUATOR_PAIRS: list[tuple[str, str]] = list(combinations(EVALUATOR_NAMES, 2))


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
# Verdict extraction
# ---------------------------------------------------------------------------


def extract_verdict_vector(ep: dict[str, Any]) -> dict[str, bool]:
    """Extract 4-evaluator pass/fail vector from an episode dict.

    Args:
        ep: Single episode dict from per_episode array.

    Returns:
        Dict mapping evaluator name to bool (True = pass).
    """
    return {
        "AC-Proxy": bool(ep["ac_proxy"]),
        "MAB-Proxy": bool(ep["mab_proxy"]),
        "C2": bool(ep["c2_pass"]),
        "CGA-Bench": not bool(ep["v4_hard"]),
    }


# ---------------------------------------------------------------------------
# Metric computation
# ---------------------------------------------------------------------------


def compute_verdict_flip_prevalence(
    episodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute verdict-flip prevalence across all episodes.

    A verdict-flip occurs when >= 1 evaluator pair disagrees within
    the 4-evaluator vector for a given episode.

    Args:
        episodes: List of episode dicts.

    Returns:
        Dict with flip_count, flip_fraction, and per-pair disagreement counts.
    """
    flip_count = 0
    pair_disagree: dict[str, int] = {f"{a} vs {b}": 0 for a, b in EVALUATOR_PAIRS}

    for ep in episodes:
        vec = extract_verdict_vector(ep)
        episode_has_flip = False

        for a, b in EVALUATOR_PAIRS:
            if vec[a] != vec[b]:
                pair_disagree[f"{a} vs {b}"] += 1
                episode_has_flip = True

        if episode_has_flip:
            flip_count += 1

    flip_fraction = flip_count / N_EPISODES

    return {
        "flip_count": flip_count,
        "flip_fraction": round(flip_fraction, 4),
        "pair_disagreement_counts": pair_disagree,
    }


def compute_false_accept_rates(
    episodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute false-accept rate per evaluator and all-process-oblivious FA.

    False-Accept (FA) for evaluator e:
        count(e=pass AND v4_hard=True) / N_EPISODES

    All-process-oblivious FA:
        count(dxem=pass AND ac_proxy=pass AND c2_pass=pass AND v4_hard=True) / N_EPISODES

    Args:
        episodes: List of episode dicts.

    Returns:
        Dict with per-evaluator FA counts/rates and all-oblivious FA.
    """
    fa_counts: dict[str, int] = dict.fromkeys(EVALUATOR_NAMES, 0)
    all_oblivious_fa_count = 0

    for ep in episodes:
        v4_hard = bool(ep["v4_hard"])
        if not v4_hard:
            continue

        vec = extract_verdict_vector(ep)
        for name in EVALUATOR_NAMES:
            if vec[name]:
                fa_counts[name] += 1

        # All-process-oblivious: DxEM (always true) + AC-Proxy + C2 all pass
        if ep["dxem"] and ep["ac_proxy"] and ep["c2_pass"]:
            all_oblivious_fa_count += 1

    per_evaluator: dict[str, dict[str, Any]] = {}
    for name in EVALUATOR_NAMES:
        per_evaluator[name] = {
            "fa_count": fa_counts[name],
            "fa_rate": round(fa_counts[name] / N_EPISODES, 4),
        }

    return {
        "per_evaluator": per_evaluator,
        "all_oblivious_fa_count": all_oblivious_fa_count,
        "all_oblivious_fa_rate": round(all_oblivious_fa_count / N_EPISODES, 4),
    }


def compute_median_viols_in_fa_episodes(
    episodes: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compute median violation count among false-accept episodes per evaluator.

    A false-accept episode for evaluator e is one where e passes AND v4_hard=True.

    Args:
        episodes: List of episode dicts.

    Returns:
        Dict mapping evaluator name to median n_viols among their FA episodes.
    """
    fa_viols: dict[str, list[int]] = {name: [] for name in EVALUATOR_NAMES}

    for ep in episodes:
        if not ep["v4_hard"]:
            continue
        vec = extract_verdict_vector(ep)
        n_viols = int(ep.get("n_viols", 0))
        for name in EVALUATOR_NAMES:
            if vec[name]:
                fa_viols[name].append(n_viols)

    result: dict[str, Any] = {}
    for name in EVALUATOR_NAMES:
        viols = fa_viols[name]
        if viols:
            sorted_viols = sorted(viols)
            mid = len(sorted_viols) // 2
            if len(sorted_viols) % 2 == 0:
                median_val = (sorted_viols[mid - 1] + sorted_viols[mid]) / 2.0
            else:
                median_val = float(sorted_viols[mid])
        else:
            median_val = 0.0
        result[name] = {"fa_episode_count": len(viols), "median_n_viols": median_val}

    return result


# ---------------------------------------------------------------------------
# LaTeX table generation
# ---------------------------------------------------------------------------


def build_latex_table(
    flip_results: dict[str, Any],
    fa_results: dict[str, Any],
    median_results: dict[str, Any],
) -> None:
    """Generate LaTeX booktabs table for verdict-flip and FA metrics.

    Args:
        flip_results: Output of compute_verdict_flip_prevalence().
        fa_results: Output of compute_false_accept_rates().
        median_results: Output of compute_median_viols_in_fa_episodes().
    """
    headers = ["Evaluator", "FA Count", "FA Rate", "Median Viols (FA eps)"]
    rows: list[list[str]] = []
    for name in EVALUATOR_NAMES:
        fa = fa_results["per_evaluator"][name]
        med = median_results[name]
        rows.append(
            [
                name,
                str(fa["fa_count"]),
                f"{fa['fa_rate']:.4f}",
                f"{med['median_n_viols']:.1f}",
            ]
        )

    # Append all-oblivious row
    rows.append(
        [
            "All-Oblivious (DxEM+AC+C2)",
            str(fa_results["all_oblivious_fa_count"]),
            f"{fa_results['all_oblivious_fa_rate']:.4f}",
            "--",
        ]
    )

    save_latex_table(
        rows=rows,
        headers=headers,
        path=OUTPUT_TEX_PATH,
        caption=(
            f"Verdict-flip prevalence: {flip_results['flip_count']}/{N_EPISODES} "
            f"episodes ({flip_results['flip_fraction']:.1%}). "
            "False-accept rate per evaluator (FA = pass AND v4\\_hard=True) "
            f"over {N_EPISODES} episodes."
        ),
        label="tab:verdict_flip_matrix",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run EXP-E1: verdict-flip prevalence and false-accept rate analysis."""
    print("=" * 60)
    print("EXP-E1: Verdict-Flip & False-Accept Rate Analysis")
    print("=" * 60)

    global N_EPISODES
    print("\n[1/4] Loading verdict matrix...")
    episodes = load_per_episode(VERDICT_MATRIX_PATH)
    N_EPISODES = len(episodes)
    print(f"  N_EPISODES = {N_EPISODES}")

    print("\n[2/4] Computing verdict-flip prevalence...")
    flip_results = compute_verdict_flip_prevalence(episodes)
    print(f"  Flip count:    {flip_results['flip_count']} / {N_EPISODES}")
    print(f"  Flip fraction: {flip_results['flip_fraction']:.4f} ({flip_results['flip_fraction']:.1%})")
    print("  Per-pair disagreement counts:")
    for pair, count in flip_results["pair_disagreement_counts"].items():
        print(f"    {pair}: {count}")

    print("\n[3/4] Computing false-accept rates...")
    fa_results = compute_false_accept_rates(episodes)
    print("  Per-evaluator false-accept rates (FA = pass AND v4_hard=True):")
    for name in EVALUATOR_NAMES:
        fa = fa_results["per_evaluator"][name]
        print(f"    {name}: {fa['fa_count']}/{N_EPISODES} = {fa['fa_rate']:.4f}")
    print(
        f"  All-oblivious FA: "
        f"{fa_results['all_oblivious_fa_count']}/{N_EPISODES} = "
        f"{fa_results['all_oblivious_fa_rate']:.4f}"
    )

    median_results = compute_median_viols_in_fa_episodes(episodes)
    print("  Median n_viols among FA episodes per evaluator:")
    for name in EVALUATOR_NAMES:
        med = median_results[name]
        print(f"    {name}: {med['median_n_viols']:.1f} (over {med['fa_episode_count']} FA episodes)")

    print("\n[4/4] Saving outputs...")
    output = {
        "experiment": "exp_e1_verdict_flip",
        "n_episodes": N_EPISODES,
        "flip_results": flip_results,
        "false_accept_results": fa_results,
        "median_viols_in_fa_episodes": median_results,
    }
    save_json(output, OUTPUT_JSON_PATH)
    build_latex_table(flip_results, fa_results, median_results)

    print("\nDone.")
    print(
        f"  Flip prevalence : {flip_results['flip_fraction']:.1%} ({flip_results['flip_count']}/{N_EPISODES} episodes)"
    )
    print(
        "  Highest FA rate : "
        + max(
            (f"{name} {fa_results['per_evaluator'][name]['fa_rate']:.4f}" for name in EVALUATOR_NAMES),
            key=lambda s: float(s.split()[-1]),
        )
    )


if __name__ == "__main__":
    main()
