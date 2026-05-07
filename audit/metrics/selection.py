"""Audit-guided evaluator selection: pi-class diversity predicts independence.

Demonstrates that the audit harness is actionable: pi-class classification
from step1 predicts evaluator independence (Kendall tau-b / phi coefficient),
enabling informed ensemble construction.

For binary verdicts, Kendall tau-b == Pearson r == Matthews phi coefficient.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

from audit.evaluator_base import Evaluator
from audit.shims._verdict_cache import load_w8_episodes

PI_CLASS_ORDER: list[str] = ["term", "aset", "nord", "nctx"]


def pi_class_distance(a: str, b: str) -> int:
    """Ordinal distance between two pi-classes (0=same, 3=max diversity).

    Args:
        a: First pi-class string.
        b: Second pi-class string.

    Returns:
        Integer distance in [0, 3].
    """
    ia = PI_CLASS_ORDER.index(a) if a in PI_CLASS_ORDER else 0
    ib = PI_CLASS_ORDER.index(b) if b in PI_CLASS_ORDER else 0
    return abs(ia - ib)


def binary_tau(va: list[bool], vb: list[bool]) -> float:
    """Kendall tau-b for binary verdict vectors (== phi coefficient).

    For binary data, tau-b equals the Pearson r and Matthews correlation
    coefficient (phi). Computed from the 2x2 contingency table in O(n).

    Returns 0.0 if either vector has zero variance (constant evaluator).

    Args:
        va: First evaluator's verdict vector.
        vb: Second evaluator's verdict vector.

    Returns:
        Correlation in [-1, 1].
    """
    a = b = c = d = 0
    for x, y in zip(va, vb):
        if x and y:
            a += 1
        elif x and not y:
            b += 1
        elif not x and y:
            c += 1
        else:
            d += 1
    num = a * d - b * c
    denom_sq = (a + b) * (c + d) * (a + c) * (b + d)
    if denom_sq == 0:
        return 0.0
    return num / math.sqrt(denom_sq)


def _mean(xs: list[float]) -> float:
    """Safe mean that returns 0.0 for empty lists."""
    return sum(xs) / len(xs) if xs else 0.0


def audit_guided_selection(
    evaluators: dict[str, Evaluator],
    pi_classes: dict[str, str],
    episodes: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run audit-guided selection experiment.

    Protocol:
      1. Precompute all verdict vectors
      2. Compute all C(n,2) pairwise tau values
      3. Group pairs by pi-class distance
      4. Audit-guided = max-distance pair with lowest tau
      5. Compare same-class vs cross-class agreement

    Args:
        evaluators: {name: Evaluator} dict.
        pi_classes: {name: pi_class_str} from step1.
        episodes: W8-filtered episodes. Loaded from cache if None.

    Returns:
        Experiment results dict with pair-level data and summary stats.
    """
    if episodes is None:
        episodes = load_w8_episodes()

    ep_ids = sorted(episodes.keys())
    names = sorted(evaluators.keys())

    # Precompute all verdicts
    verdicts: dict[str, list[bool]] = {}
    for name in names:
        ev = evaluators[name]
        verdicts[name] = [ev.verdict({"episode_id": eid}) for eid in ep_ids]

    # Compute all pairwise tau
    pairs = list(itertools.combinations(names, 2))
    pair_results: list[dict[str, Any]] = []

    for a, b in pairs:
        tau = binary_tau(verdicts[a], verdicts[b])
        dist = pi_class_distance(pi_classes[a], pi_classes[b])
        pair_results.append(
            {
                "evaluator_a": a,
                "evaluator_b": b,
                "pi_class_a": pi_classes[a],
                "pi_class_b": pi_classes[b],
                "pi_distance": dist,
                "tau": round(tau, 4),
            }
        )

    # Group by distance
    same_class = [p for p in pair_results if p["pi_distance"] == 0]
    cross_class = [p for p in pair_results if p["pi_distance"] > 0]

    # Identify max-diversity pair (audit-guided)
    max_dist = max(p["pi_distance"] for p in pair_results)
    max_diversity_pairs = [p for p in pair_results if p["pi_distance"] == max_dist]
    audit_guided = min(max_diversity_pairs, key=lambda p: p["tau"])

    # Statistics (all pairs)
    all_taus = sorted(p["tau"] for p in pair_results)
    same_taus = [p["tau"] for p in same_class]
    cross_taus = [p["tau"] for p in cross_class]

    # Non-degenerate stats (exclude constant-evaluator pairs with tau=0)
    nondegen_same = [t for t in same_taus if abs(t) > 0.001]
    nondegen_cross = [t for t in cross_taus if abs(t) > 0.001]

    same_mean = _mean(same_taus)
    cross_mean = _mean(cross_taus)
    nondegen_same_mean = _mean(nondegen_same)
    nondegen_cross_mean = _mean(nondegen_cross)

    # Degenerate pairs (containing constant evaluators like DxEM)
    degenerate_pairs = [p for p in pair_results if abs(p["tau"]) < 0.001]

    # Separation confirmed: same-class evaluators agree MORE (higher tau)
    # than cross-class evaluators, using non-degenerate pairs
    separation_confirmed = nondegen_same_mean > nondegen_cross_mean if nondegen_same and nondegen_cross else False

    return {
        "n_evaluators": len(names),
        "n_pairs": len(pairs),
        "pi_classes": pi_classes,
        "pairs": pair_results,
        "audit_guided_pair": {
            "evaluators": [audit_guided["evaluator_a"], audit_guided["evaluator_b"]],
            "pi_classes": [audit_guided["pi_class_a"], audit_guided["pi_class_b"]],
            "pi_distance": audit_guided["pi_distance"],
            "tau": audit_guided["tau"],
        },
        "same_class_stats": {
            "n_pairs": len(same_class),
            "mean_tau": round(same_mean, 4),
            "mean_tau_nondegen": round(nondegen_same_mean, 4),
        },
        "cross_class_stats": {
            "n_pairs": len(cross_class),
            "mean_tau": round(cross_mean, 4),
            "mean_tau_nondegen": round(nondegen_cross_mean, 4),
        },
        "null_distribution": {
            "mean": round(_mean(all_taus), 4),
            "min": round(all_taus[0], 4) if all_taus else 0.0,
            "max": round(all_taus[-1], 4) if all_taus else 0.0,
            "all_taus": [round(t, 4) for t in all_taus],
        },
        "degenerate_pairs": {
            "n_pairs": len(degenerate_pairs),
            "evaluators": sorted(
                {
                    p["evaluator_a"]
                    for p in degenerate_pairs
                    if all(
                        abs(pp["tau"]) < 0.001
                        for pp in pair_results
                        if pp["evaluator_a"] == p["evaluator_a"] or pp["evaluator_b"] == p["evaluator_a"]
                    )
                }
            ),
        },
        "separation_confirmed": separation_confirmed,
    }
