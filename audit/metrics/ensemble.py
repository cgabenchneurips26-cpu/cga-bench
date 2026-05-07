"""Ensemble BSR experiment: cross-pi-class consensus lowers BSR.

Demonstrates that the projection taxonomy is an ensemble design principle:
combining evaluators from different pi-classes via AND/OR consensus produces
lower BSR than combining same-class evaluators.
"""

from __future__ import annotations

import itertools
from typing import Any

from audit.evaluator_base import Evaluator
from audit.shims._verdict_cache import get_verdict, load_w8_episodes


def _bsr_from_verdicts(consensus: list[bool], reference: list[bool]) -> dict[str, float | int]:
    """Compute BSR between consensus verdicts and reference verdicts."""
    n = len(consensus)
    disagree = 0
    false_accept = 0
    false_reject = 0
    for cv, rv in zip(consensus, reference):
        if cv != rv:
            disagree += 1
            if cv and not rv:
                false_accept += 1
            else:
                false_reject += 1
    bsr = disagree / n if n > 0 else 0.0
    return {
        "bsr": round(bsr, 4),
        "n_total": n,
        "n_disagree": disagree,
        "false_accept": false_accept,
        "false_reject": false_reject,
    }


def ensemble_bsr_experiment(
    evaluators: dict[str, Evaluator],
    pi_classes: dict[str, str],
    episodes: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Run ensemble BSR experiment on all C(n,2) evaluator pairs.

    For each pair (E_i, E_j):
    - AND-consensus: verdict = E_i(ep) AND E_j(ep) (conservative)
    - OR-consensus:  verdict = E_i(ep) OR  E_j(ep) (permissive)
    - Compute BSR of each consensus vs TCC reference

    Args:
        evaluators: {name: Evaluator} dict.
        pi_classes: {name: pi_class_str} from step1.
        episodes: W8-filtered episodes. Loaded from cache if None.

    Returns:
        Full experiment results with pair-level and summary data.
    """
    if episodes is None:
        episodes = load_w8_episodes()

    # v4_hard is the TCC reference — including it as an ensemble member would
    # make (e, v4_hard) AND-BSR equal e's false-reject rate, tautologically
    # lowering the same-class mean. Reject early with an informative error.
    if "v4_hard" in evaluators:
        raise ValueError(
            "v4_hard is the TCC reference for BSR and cannot be an ensemble "
            "member. Remove it from `evaluators` before calling this function."
        )

    ep_ids = sorted(episodes.keys())
    names = sorted(evaluators.keys())

    # Precompute all verdict vectors
    verdicts: dict[str, list[bool]] = {}
    for name in names:
        ev = evaluators[name]
        verdicts[name] = [ev.verdict({"episode_id": eid}) for eid in ep_ids]

    # TCC reference vector
    ref = [get_verdict(eid, "v4_hard") for eid in ep_ids]

    # Individual BSRs for context
    individual_bsr: dict[str, float] = {}
    for name in names:
        stats = _bsr_from_verdicts(verdicts[name], ref)
        individual_bsr[name] = stats["bsr"]

    # All pairs
    pairs = list(itertools.combinations(names, 2))
    pair_results: list[dict[str, Any]] = []

    for a, b in pairs:
        va, vb = verdicts[a], verdicts[b]
        and_consensus = [x and y for x, y in zip(va, vb)]
        or_consensus = [x or y for x, y in zip(va, vb)]

        and_stats = _bsr_from_verdicts(and_consensus, ref)
        or_stats = _bsr_from_verdicts(or_consensus, ref)

        same_class = pi_classes[a] == pi_classes[b]

        pair_results.append(
            {
                "evaluator_a": a,
                "evaluator_b": b,
                "pi_class_a": pi_classes[a],
                "pi_class_b": pi_classes[b],
                "same_class": same_class,
                "and_bsr": and_stats["bsr"],
                "or_bsr": or_stats["bsr"],
                "and_fa": and_stats["false_accept"],
                "or_fa": or_stats["false_accept"],
                "individual_bsr_a": individual_bsr[a],
                "individual_bsr_b": individual_bsr[b],
                "min_individual_bsr": min(individual_bsr[a], individual_bsr[b]),
                "max_individual_bsr": max(individual_bsr[a], individual_bsr[b]),
            }
        )

    # Group by same/cross class
    same = [p for p in pair_results if p["same_class"]]
    cross = [p for p in pair_results if not p["same_class"]]

    def _mean(xs: list[float]) -> float:
        return sum(xs) / len(xs) if xs else 0.0

    same_and_bsrs = [p["and_bsr"] for p in same]
    cross_and_bsrs = [p["and_bsr"] for p in cross]
    same_or_bsrs = [p["or_bsr"] for p in same]
    cross_or_bsrs = [p["or_bsr"] for p in cross]

    # Key finding: cross-class AND-consensus should have lower BSR
    cross_and_mean = _mean(cross_and_bsrs)
    same_and_mean = _mean(same_and_bsrs)
    hypothesis_confirmed = cross_and_mean < same_and_mean if same and cross else False

    # Best pair: lowest AND-consensus BSR
    best_pair = min(pair_results, key=lambda p: p["and_bsr"])

    return {
        "n_evaluators": len(names),
        "n_pairs": len(pairs),
        "n_episodes": len(ep_ids),
        "individual_bsr": individual_bsr,
        "pairs": pair_results,
        "same_class_stats": {
            "n_pairs": len(same),
            "and_bsr_mean": round(same_and_mean, 4),
            "or_bsr_mean": round(_mean(same_or_bsrs), 4),
            "and_bsrs": [round(x, 4) for x in same_and_bsrs],
        },
        "cross_class_stats": {
            "n_pairs": len(cross),
            "and_bsr_mean": round(cross_and_mean, 4),
            "or_bsr_mean": round(_mean(cross_or_bsrs), 4),
            "and_bsrs": [round(x, 4) for x in cross_and_bsrs],
        },
        "best_and_pair": {
            "evaluators": [best_pair["evaluator_a"], best_pair["evaluator_b"]],
            "and_bsr": best_pair["and_bsr"],
            "same_class": best_pair["same_class"],
        },
        "hypothesis_confirmed": hypothesis_confirmed,
    }
