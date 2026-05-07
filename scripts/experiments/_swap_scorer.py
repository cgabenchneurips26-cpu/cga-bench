"""Swap-scoring helpers for Experiment X1 (context-swap probe).

A swap-score applies a FOREIGN scenario's expected / forbidden action
lists to an episode's performed-action list, then computes a hard-
violation verdict. This is the minimal static-rule evaluator: it
measures COMMISSION (performed action in recipient's forbidden set)
without requiring cpg_engine evaluation of patient-state-conditioned
rules.

The function is adequate for the X1 test because the X1 design probes
context-inversion: scenarios with the SAME action labelled both
expected and forbidden under different patient contexts.

See scripts/experiments/exp_x1_context_swap.py for the driver.
"""

from __future__ import annotations

from typing import Any


def _norm(aid: str) -> str:
    return aid.strip().lower().replace("-", "_").replace(" ", "_")


def _as_set(action_list: list[Any] | None) -> set[str]:
    out: set[str] = set()
    for a in action_list or []:
        if isinstance(a, dict):
            aid = a.get("action_id", "")
        else:
            aid = str(a)
        if aid:
            out.add(_norm(aid))
    return out


def performed_actions(ep: dict[str, Any]) -> set[str]:
    """Extract performed action IDs from an episode's actions list."""
    return _as_set(ep.get("actions"))


def score_episode_against(ep: dict[str, Any], recipient: dict[str, Any]) -> dict[str, Any]:
    """Score an episode's performed actions against a DIFFERENT scenario's rules.

    Args:
        ep: episode dict with "actions" list.
        recipient: scenario dict with "expected_actions" + "forbidden_actions" lists
            (typically loaded directly from configs/scenarios/*.yaml).

    Returns:
        dict with keys v4_hard (bool), commission (set), omission (set),
        n_commission (int), n_omission (int).
    """
    performed = performed_actions(ep)
    expected = _as_set(recipient.get("expected_actions"))
    forbidden = _as_set(recipient.get("forbidden_actions"))

    commission = performed & forbidden
    omission = expected - performed

    # Hard verdict = any commission (forbidden action performed). Omission is
    # not universally hard; we follow the _episode_cache.score_episode
    # convention where only commission/timing/sequence are hard. Timing and
    # sequence are not determinable without cpg_engine state, so commission
    # is the operational proxy for X1's verdict-flip measurement.
    v4_hard = len(commission) > 0

    return {
        "v4_hard": bool(v4_hard),
        "commission": sorted(commission),
        "omission": sorted(omission),
        "n_commission": len(commission),
        "n_omission": len(omission),
        "n_performed": len(performed),
        "n_expected": len(expected),
        "n_forbidden": len(forbidden),
    }
