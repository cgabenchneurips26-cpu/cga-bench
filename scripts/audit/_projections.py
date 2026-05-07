"""Trace projection functions for evaluator audit harness.

Four canonical projections from Theorem 3.4:
  pi_term : termination reason only (coarsest)
  pi_aset : sorted multiset of performed action IDs
  pi_nord : ordered action ID sequence (timestamps stripped)
  pi_nctx : (action_id, timestamp_5min_bin) sequence (context stripped)
"""

from __future__ import annotations

from collections.abc import Callable, Hashable
from typing import Any

TIMESTAMP_BIN_MIN = 5.0


def _norm(aid: str) -> str:
    return aid.strip().lower().replace("-", "_").replace(" ", "_")


def pi_term(ep: dict[str, Any]) -> str:
    return str(ep.get("termination_reason") or "unknown")


def pi_aset(ep: dict[str, Any]) -> tuple[str, ...]:
    return tuple(sorted({_norm(a.get("action_id", "")) for a in ep.get("actions", []) if a.get("action_id")}))


def pi_nord(ep: dict[str, Any]) -> tuple[str, ...]:
    return tuple(_norm(a.get("action_id", "")) for a in ep.get("actions", []) if a.get("action_id"))


def pi_nctx(ep: dict[str, Any]) -> tuple[tuple[str, int], ...]:
    out: list[tuple[str, int]] = []
    for a in ep.get("actions", []):
        aid = _norm(a.get("action_id", ""))
        if not aid:
            continue
        try:
            ts = float(a.get("timestamp_minutes", 0.0))
        except (TypeError, ValueError):
            ts = 0.0
        bin_idx = int(ts // TIMESTAMP_BIN_MIN) * int(TIMESTAMP_BIN_MIN)
        out.append((aid, bin_idx))
    return tuple(out)


PROJECTIONS: dict[str, Callable[[dict[str, Any]], Hashable]] = {
    "term": pi_term,
    "aset": pi_aset,
    "nord": pi_nord,
    "nctx": pi_nctx,
}
