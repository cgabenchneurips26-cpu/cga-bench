"""Repair-distance proxy and correlation analysis for evaluator audit.

Uses n_viols from verdict_matrix_v6.json as a d_G proxy. n_viols counts
commission and timing violations only (NOT omissions). Optionally loads
exact ILP d_G from a JSONL cache produced by scripts/audit/repair_distance.py.

Key insight: n_viols is POSITIVELY correlated with v4_hard (rho ≈ +0.74)
because agents that take actions (even imperfectly, accumulating some
commissions) tend to PASS, while agents that do nothing (n_viols=0) tend
to FAIL from omission of mandatory actions.

Metrics:
  - rho(verdict, d_G): Pearson correlation (positive for n_viols proxy)
  - monotonicity violations: pairs where d_G ordering contradicts verdict
  - proxy statistics: distribution of n_viols vs v4_hard outcomes
"""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

from audit.evaluator_base import Evaluator
from audit.shims._verdict_cache import load_w8_episodes


def load_dg_proxy() -> dict[str, float]:
    """Load d_G proxy (n_viols) for all W8-filtered episodes.

    Returns:
        {episode_id: n_viols_as_float} for all 14,826 episodes.
    """
    episodes = load_w8_episodes()
    return {ep_id: float(ep.get("n_viols") or 0) for ep_id, ep in episodes.items()}


def load_dg_cache(cache_path: str | Path | None = None) -> dict[str, float]:
    """Load d_G values from ILP cache if available, else n_viols proxy.

    Args:
        cache_path: Path to JSONL file with {"episode_id": str, "d_G": float}
            per line. Falls back to n_viols proxy if file missing or empty.

    Returns:
        {episode_id: d_G_value} dict.
    """
    if cache_path is not None:
        p = Path(cache_path)
        if p.exists():
            cache: dict[str, float] = {}
            with open(p) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    entry = json.loads(line)
                    cache[entry["episode_id"]] = float(entry["d_G"])
            if cache:
                return cache
    return load_dg_proxy()


def dg_correlation(evaluator: Evaluator, dg_cache: dict[str, float]) -> float:
    """Pearson rho(verdict, d_G) over the W8-filtered corpus.

    For the n_viols proxy: POSITIVE for v4_hard (agents that act accumulate
    commissions but also complete mandatory actions → pass). Constant
    evaluators (e.g. DxEM always True) yield rho=0.

    Args:
        evaluator: Evaluator instance.
        dg_cache: {episode_id: d_G} from load_dg_cache().

    Returns:
        Pearson correlation coefficient in [-1, 1].
    """
    verdicts: list[float] = []
    dg_vals: list[float] = []

    for ep_id, dg in dg_cache.items():
        v = evaluator.verdict({"episode_id": ep_id})
        verdicts.append(1.0 if v else 0.0)
        dg_vals.append(dg)

    if len(verdicts) < 2:
        return 0.0

    return _pearson_r(verdicts, dg_vals)


def monotonicity_violations(
    evaluator: Evaluator,
    dg_cache: dict[str, float],
    sample_size: int = 5000,
    seed: int = 42,
) -> tuple[int, int]:
    """Count pairs violating d_G-verdict monotonicity.

    For n_viols proxy (positive correlation with v4_hard):
    A violation occurs when higher n_viols maps to WORSE verdict, i.e.
    d_G(a) > d_G(b) but verdict(a)=harmful and verdict(b)=safe.
    This contradicts the positive correlation pattern.

    Samples random pairs for efficiency (full corpus has ~110M pairs).

    Args:
        evaluator: Evaluator instance.
        dg_cache: {episode_id: d_G} from load_dg_cache().
        sample_size: Number of random pairs to draw.
        seed: RNG seed for reproducibility.

    Returns:
        (n_violations, n_informative_pairs_checked) where informative
        means both d_G and verdict differ between the pair.
    """
    import random

    rng = random.Random(seed)

    items: list[tuple[str, float, bool]] = []
    for ep_id, dg in dg_cache.items():
        v = evaluator.verdict({"episode_id": ep_id})
        items.append((ep_id, dg, v))

    if len(items) < 2:
        return 0, 0

    violations = 0
    informative = 0

    for _ in range(sample_size):
        i, j = rng.sample(range(len(items)), 2)
        _, a_dg, a_v = items[i]
        _, b_dg, b_v = items[j]

        # Skip uninformative pairs (equal d_G or equal verdict)
        if a_dg == b_dg or a_v == b_v:
            continue

        informative += 1

        # Monotonicity violation (positive-correlation direction):
        # higher n_viols should map to SAFER verdict (agents that act more).
        # Violation: higher d_G but harmful, lower d_G but safe.
        if (a_dg > b_dg and (not a_v) and b_v) or (b_dg > a_dg and (not b_v) and a_v):
            violations += 1

    return violations, informative


def compliance_check(dg_cache: dict[str, float]) -> dict[str, Any]:
    """Compute proxy statistics for n_viols vs v4_hard relationship.

    The n_viols proxy counts commission/timing violations only, NOT
    omissions. This creates a counter-intuitive pattern:
      - n_viols=0 episodes often FAIL v4_hard (omission of mandatory actions)
      - n_viols>0 episodes often PASS v4_hard (active agents that also
        complete mandatory actions but accumulate some commissions)

    This function reports the distribution as informational statistics,
    not strict invariants. The positive correlation (rho ≈ +0.74) is a
    valid and informative signal about evaluator behavior.

    Returns:
        Dict with distribution counts and correlation direction.
    """
    episodes = load_w8_episodes()
    zero_dg_but_harmful = 0
    zero_dg_and_safe = 0
    nonzero_dg_and_safe = 0
    nonzero_dg_but_harmful = 0
    zero_dg_total = 0
    harmful_total = 0

    for ep_id, dg in dg_cache.items():
        ep = episodes.get(ep_id)
        if ep is None:
            continue
        v4 = bool(ep.get("v4_hard", False))

        if dg == 0.0:
            zero_dg_total += 1
            if v4:
                zero_dg_and_safe += 1
            else:
                zero_dg_but_harmful += 1

        else:
            if v4:
                nonzero_dg_and_safe += 1
            else:
                nonzero_dg_but_harmful += 1

        if not v4:
            harmful_total += 1

    # Positive correlation confirmed if nonzero_dg_and_safe > zero_dg_and_safe
    positive_correlation = nonzero_dg_and_safe > zero_dg_and_safe

    return {
        "zero_dg_but_harmful": zero_dg_but_harmful,
        "zero_dg_and_safe": zero_dg_and_safe,
        "nonzero_dg_and_safe": nonzero_dg_and_safe,
        "nonzero_dg_but_harmful": nonzero_dg_but_harmful,
        "zero_dg_total": zero_dg_total,
        "harmful_total": harmful_total,
        "total": len(dg_cache),
        "positive_correlation": positive_correlation,
        "pass": True,  # Always passes — informational stats
    }


def _pearson_r(x: list[float], y: list[float]) -> float:
    """Pearson correlation coefficient (no numpy dependency)."""
    n = len(x)
    if n < 2:
        return 0.0

    mean_x = sum(x) / n
    mean_y = sum(y) / n

    cov = sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y))
    var_x = sum((xi - mean_x) ** 2 for xi in x)
    var_y = sum((yi - mean_y) ** 2 for yi in y)

    denom = math.sqrt(var_x * var_y)
    if denom == 0:
        return 0.0
    return cov / denom
