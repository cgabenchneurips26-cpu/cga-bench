"""Trajectory loader: maps episode_id -> trajectory JSON path.

Trajectories live under results/full_706_v6_aliasfix_*/<model_dir>_react/
(deepseek has no _react suffix). Filename format:
    {scenario_id}_{subdir_name}_r{run_index}_{YYYYMMDD_HHMMSS}.json

This loader scans the directory once, parses filenames, and joins them
to the verdict_matrix episode_id via (scenario_id, model_dir, run_index).
"""

from __future__ import annotations

from functools import lru_cache
import json
from pathlib import Path
import re
from typing import Any

from audit.shims._verdict_cache import load_all_episodes

_ROOT = Path(__file__).resolve().parents[2]
_RESULTS_DIR = _ROOT / "results"
_V6_DIR_GLOB = "full_706_v6_aliasfix_*"

_FILENAME_RUN_RE = re.compile(r"_r(\d+)_\d{8}_\d{6}$")


@lru_cache(maxsize=1)
def _v6_root() -> Path:
    matches = sorted(_RESULTS_DIR.glob(_V6_DIR_GLOB))
    if not matches:
        raise FileNotFoundError(
            f"No trajectory directory matching {_V6_DIR_GLOB!r} under {_RESULTS_DIR}"
        )
    return matches[0]


@lru_cache(maxsize=1)
def build_trajectory_index() -> dict[str, Path]:
    """Return {episode_id: trajectory_json_path} for all episodes that have files."""
    key_to_eid: dict[tuple[str, str, int], str] = {}
    for ep in load_all_episodes().values():
        key = (ep["scenario_id"], ep["model_dir"], int(ep["run_index"]))
        key_to_eid[key] = ep["episode_id"]

    idx: dict[str, Path] = {}
    root = _v6_root()
    for subdir in root.iterdir():
        if not subdir.is_dir():
            continue
        subdir_name = subdir.name
        model_dir = (
            subdir_name[: -len("_react")] if subdir_name.endswith("_react") else subdir_name
        )
        suffix_re = re.compile(rf"_{re.escape(subdir_name)}_r(\d+)_\d{{8}}_\d{{6}}$")
        for f in subdir.glob("*.json"):
            m = suffix_re.search(f.stem)
            if not m:
                continue
            run = int(m.group(1))
            scenario = f.stem[: m.start()]
            eid = key_to_eid.get((scenario, model_dir, run))
            if eid is not None:
                idx[eid] = f
    return idx


@lru_cache(maxsize=4096)
def load_trajectory(episode_id: str) -> dict[str, Any] | None:
    """Load a trajectory JSON by episode_id (returns None if not found)."""
    idx = build_trajectory_index()
    p = idx.get(episode_id)
    if p is None:
        return None
    with open(p) as f:
        return json.load(f)


def iter_available_episode_ids() -> list[str]:
    """All episode_ids whose trajectory file we can locate."""
    return sorted(build_trajectory_index().keys())
