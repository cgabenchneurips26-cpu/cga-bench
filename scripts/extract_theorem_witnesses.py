#!/usr/bin/env python3
"""Extract real CGA-Bench episode pairs that instantiate Lemma separating-pairs.

For each projection pi (term, aset, nord, nctx), finds the first verdict-
heterogeneous pi-fibre restricted to the guideline family specified by the
Lemma case (SSC sepsis for cases i-iii; AHA stroke for case iv), and emits
(episode_compliant, episode_violating) pair with resolvable episode IDs.

Output: evidence_pack/theorem_v2/witnesses.json (Table A1 source of truth).

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/extract_theorem_witnesses.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.compute_bayes_error import (  # noqa: E402
    PROJECTIONS,
    _hash_key,
    hard_violation_label,
)
from scripts.experiments._episode_cache import load_cached_episodes  # noqa: E402

OUTPUT_DIR = ROOT / "evidence_pack" / "theorem_v2"

CASE_FILTERS: dict[str, dict[str, Any]] = {
    "term": {"guideline": "SSC 2021 Hour-1", "scenario_prefix": "ssc_"},
    "aset": {"guideline": "SSC 2021 Hour-1", "scenario_prefix": "ssc_"},
    "nord": {"guideline": "SSC 2021 Hour-1", "scenario_prefix": "ssc_"},
    "nctx": {"guideline": "AHA 2019 Stroke", "scenario_prefix": "aha_stroke_"},
}


def episode_id(ep: dict[str, Any]) -> str:
    """Canonical episode identifier string."""
    return f"{ep.get('scenario_id', '?')}_r{ep.get('run_index', 0)}_{ep.get('_model', '?')}"


def find_mixed_fibre(
    episodes: list[dict[str, Any]],
    proj_name: str,
    scenario_prefix: str,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Return (compliant_ep, violating_ep) from first mixed pi-fibre matching prefix."""
    proj_fn = PROJECTIONS[proj_name]
    fibres: dict[str, list[dict[str, Any]]] = {}
    for ep in episodes:
        if not ep.get("scenario_id", "").startswith(scenario_prefix):
            continue
        key = _hash_key(proj_fn(ep))
        fibres.setdefault(key, []).append(ep)

    for _, members in fibres.items():
        labels = {hard_violation_label(e) for e in members}
        if 0 in labels and 1 in labels:
            compliant = next(e for e in members if hard_violation_label(e) == 0)
            violating = next(e for e in members if hard_violation_label(e) == 1)
            return compliant, violating
    return None


def main() -> int:
    """Extract 4 witness pairs, write witnesses.json."""
    print("Loading episodes...")
    episodes = load_cached_episodes()
    print(f"  Loaded {len(episodes)} episodes")

    witnesses: dict[str, Any] = {}
    for case_idx, (proj, cfg) in enumerate(CASE_FILTERS.items(), start=1):
        print(f"\nCase ({'i' * case_idx if case_idx <= 3 else 'iv'})  pi_{proj}  filter={cfg['scenario_prefix']!r}")
        pair = find_mixed_fibre(episodes, proj, cfg["scenario_prefix"])
        filter_used = cfg["scenario_prefix"]
        if pair is None:
            print("  NO narrow mixed fibre; falling back to any-guideline search")
            pair = find_mixed_fibre(episodes, proj, "")
            filter_used = "(any)"
        if pair is None:
            print(f"  NO mixed fibre found for pi_{proj} at all")
            witnesses[proj] = {"status": "not_found", "guideline": cfg["guideline"]}
            continue
        compliant, violating = pair
        print(f"  compliant: {episode_id(compliant)}")
        print(f"  violating: {episode_id(violating)}")
        witnesses[proj] = {
            "case_roman": {"term": "i", "aset": "ii", "nord": "iii", "nctx": "iv"}[proj],
            "guideline": cfg["guideline"],
            "filter_used": filter_used,
            "projection": f"pi_{proj}",
            "compliant_episode": episode_id(compliant),
            "violating_episode": episode_id(violating),
            "compliant_scenario_id": compliant.get("scenario_id"),
            "violating_scenario_id": violating.get("scenario_id"),
            "compliant_run": compliant.get("run_index"),
            "violating_run": violating.get("run_index"),
            "compliant_model": compliant.get("_model"),
            "violating_model": violating.get("_model"),
            "compliant_n_actions": len(compliant.get("actions", [])),
            "violating_n_actions": len(violating.get("actions", [])),
            "compliant_violation_types": _viol_types(compliant),
            "violating_violation_types": _viol_types(violating),
        }

    out = OUTPUT_DIR / "witnesses.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w") as f:
        json.dump(witnesses, f, indent=2)
    print(f"\nSaved: {out}")
    return 0


def _viol_types(ep: dict[str, Any]) -> list[str]:
    """Unique violation types in an episode."""
    return sorted(
        {str(v.get("violation_type", "")) for v in ep.get("violation_events", []) or [] if isinstance(v, dict)}
    )


if __name__ == "__main__":
    sys.exit(main())
