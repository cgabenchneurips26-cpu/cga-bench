"""Importable CAV filter module.

Used by the v6 rescore pipeline (and future v7 corpus builds) to drop
non-CAV / extension-tier action IDs from scenario `expected_actions` and
`forbidden_actions` lists before scoring.

Path resolution:
- explicit `cav_path` argument wins
- else `os.environ["CAV_PATH"]`
- else default at `<repo_root>/cav_v0_5/cav_v0_5.json`
"""

from __future__ import annotations

from functools import lru_cache
import json
import os
from pathlib import Path
from typing import Any

_DEFAULT_CAV_PATH = Path(__file__).resolve().parent.parent.parent / "cav_v0_5" / "cav_v0_5.json"


def _resolve_path(cav_path: str | Path | None) -> Path:
    if cav_path is not None:
        return Path(cav_path)
    env = os.environ.get("CAV_PATH")
    if env:
        return Path(env)
    return _DEFAULT_CAV_PATH


@lru_cache(maxsize=8)
def _cached_load(path_str: str) -> dict[str, Any]:
    p = Path(path_str)
    if not p.is_file():
        raise FileNotFoundError(f"CAV artifact not found: {p}")
    return json.loads(p.read_text(encoding="utf-8"))


def load_cav(cav_path: str | Path | None = None) -> dict[str, Any]:
    """Load and cache the CAV artifact dict."""
    return _cached_load(str(_resolve_path(cav_path)))


def is_in_cav(action_id: str, cav: dict[str, Any] | None = None) -> bool:
    """True iff ``action_id`` is a key in the CAV `entries` dict."""
    if cav is None:
        cav = load_cav()
    return action_id in cav.get("entries", {})


def filter_action_list(
    actions: list[str],
    context: str = "",
    cav: dict[str, Any] | None = None,
) -> tuple[list[str], list[dict[str, Any]]]:
    """Partition `actions` into (kept, dropped_with_reasons).

    Order is preserved in `kept`. Each dropped entry is a dict
    {"action_id", "reason", "context"}. ``reason`` is always
    "not_in_cav" since the CAV artifact already encodes Strict policy
    (extension-tier entries pre-dropped at build time).
    """
    if cav is None:
        cav = load_cav()
    entries = cav.get("entries", {})
    kept: list[str] = []
    dropped: list[dict[str, Any]] = []
    for a in actions:
        if a in entries:
            kept.append(a)
        else:
            dropped.append({"action_id": a, "reason": "not_in_cav", "context": context})
    return kept, dropped


def clear_cache() -> None:
    """Clear the lru_cache (useful for tests that switch CAV paths)."""
    _cached_load.cache_clear()
