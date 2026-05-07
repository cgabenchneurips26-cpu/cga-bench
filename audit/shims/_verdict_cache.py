"""Singleton loader for verdict_matrix_v6.json with W8 filtering.

The verdict matrix contains 16,944 episodes (8 models x 706 scenarios x 3 runs).
W8 filtering excludes DeepSeek-R1-7B to yield 14,826 episodes (7 models),
matching the paper's canonical episode count.

Data format: per_episode is a LIST of dicts (not a dict). Each entry has:
  - episode_id: str
  - model: str  (e.g. "120B", "27B", "DeepSeek-R1-7B")
  - Flat boolean verdict columns: dxem, ac_proxy, mab_proxy, c2_pass, acov_pass, v4_hard
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_VERDICT_MATRIX_PATH = Path(__file__).resolve().parents[2] / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"

W8_EXCLUDED_MODEL = "DeepSeek-R1-7B"

# Maps shim column names to the actual JSON field names
COLUMN_MAP: dict[str, str] = {
    "dxem": "dxem",
    "ac_proxy": "ac_proxy",
    "mab_proxy": "mab_proxy",
    "c2": "c2_pass",
    "acov": "acov_pass",
    "v4_hard": "v4_hard",
}

# Singleton caches
_raw_list: list[dict[str, Any]] | None = None
_all_by_id: dict[str, dict[str, Any]] | None = None
_w8_by_id: dict[str, dict[str, Any]] | None = None


def _load_raw(path: Path | None = None) -> list[dict[str, Any]]:
    """Load the full per_episode list from verdict_matrix_v6.json."""
    global _raw_list
    if _raw_list is not None:
        return _raw_list
    p = path or _VERDICT_MATRIX_PATH
    with open(p) as f:
        data = json.load(f)
    _raw_list = data["per_episode"]
    return _raw_list


def load_all_episodes(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load ALL episodes (no W8 filter) as {episode_id: entry} dict."""
    global _all_by_id
    if _all_by_id is not None:
        return _all_by_id
    raw = _load_raw(path)
    _all_by_id = {ep["episode_id"]: ep for ep in raw}
    return _all_by_id


def load_w8_episodes(path: Path | None = None) -> dict[str, dict[str, Any]]:
    """Load W8-filtered episodes as {episode_id: entry} dict."""
    global _w8_by_id
    if _w8_by_id is not None:
        return _w8_by_id
    raw = _load_raw(path)
    _w8_by_id = {ep["episode_id"]: ep for ep in raw if ep.get("model") != W8_EXCLUDED_MODEL}
    return _w8_by_id


def get_verdict(episode_id: str, evaluator_col: str) -> bool:
    """Look up a single verdict by episode_id and column name.

    Searches the full corpus (not just W8-filtered) so that separating
    pairs referencing DeepSeek episodes still resolve correctly.

    Args:
        episode_id: The episode identifier.
        evaluator_col: Column name — one of the keys in COLUMN_MAP
            (e.g. "dxem", "ac_proxy", "v4_hard") or the raw JSON field
            name (e.g. "c2_pass", "acov_pass").

    Returns:
        True if the evaluator considers this episode safe/passing.
    """
    episodes = load_all_episodes()
    ep = episodes.get(episode_id)
    if ep is None:
        raise KeyError(f"Episode {episode_id!r} not found in corpus")

    # Resolve column name through COLUMN_MAP if needed
    json_field = COLUMN_MAP.get(evaluator_col, evaluator_col)
    if json_field not in ep:
        raise KeyError(
            f"Column {evaluator_col!r} (resolved: {json_field!r}) not found for "
            f"episode {episode_id!r}. Available: {[k for k in ep if k not in ('episode_id', 'scenario_id', 'model')]}"
        )
    v = ep[json_field]
    # Values are already booleans in the JSON
    return bool(v)


def get_verdict_full(episode_id: str, evaluator_col: str) -> bool:
    """Like get_verdict but searches the FULL corpus (no W8 filter).

    Used for separating-pair lookups which may reference DeepSeek episodes.
    """
    episodes = load_all_episodes()
    ep = episodes.get(episode_id)
    if ep is None:
        raise KeyError(f"Episode {episode_id!r} not found in full corpus")
    json_field = COLUMN_MAP.get(evaluator_col, evaluator_col)
    if json_field not in ep:
        raise KeyError(f"Column {evaluator_col!r} (resolved: {json_field!r}) not found")
    return bool(ep[json_field])


def get_all_episode_ids() -> list[str]:
    """Return all W8-filtered episode IDs."""
    return list(load_w8_episodes().keys())


def get_episode_count() -> int:
    """Return the number of W8-filtered episodes."""
    return len(load_w8_episodes())


def reset_cache() -> None:
    """Clear cached data (for testing)."""
    global _raw_list, _all_by_id, _w8_by_id
    _raw_list = None
    _all_by_id = None
    _w8_by_id = None
