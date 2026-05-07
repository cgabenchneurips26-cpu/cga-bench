"""Auto-discovery of (donor, recipient, pivot_action) triplets for X1.

Scans configs/scenarios/*.yaml and emits candidate triplets where a
pivot action is labelled in one scenario's expected/optional set and
in another scenario's forbidden set. Each triplet is a potential
"context inversion": the SAME trajectory evaluated against scenario A
vs scenario B should yield different TCC verdicts if the pivot action
is performed.

The discovery is static — no episodes required. Output is a JSON file
that exp_x1_context_swap.py consumes.

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/_x1_pair_discovery.py
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

SCENARIO_DIR = ROOT / "configs" / "scenarios"
OUTPUT_FILE = ROOT / "evidence_pack" / "ex_x1_context_swap" / "x1_discovered_pairs.json"


def _norm(aid: str) -> str:
    return aid.strip().lower().replace("-", "_").replace(" ", "_")


def _as_set(actions: list[Any] | None) -> set[str]:
    out: set[str] = set()
    for a in actions or []:
        if isinstance(a, dict):
            aid = a.get("action_id", "")
        else:
            aid = str(a)
        if aid:
            out.add(_norm(aid))
    return out


def load_scenarios() -> dict[str, dict[str, Any]]:
    """Load every scenario file and flatten into {scenario_id: scenario_dict}."""
    scenarios: dict[str, dict[str, Any]] = {}
    for f in sorted(SCENARIO_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(open(f))
        except Exception as exc:
            print(f"  WARN: failed to parse {f.name}: {exc}")
            continue
        for sid, s in (data.get("scenarios") or {}).items():
            if not isinstance(s, dict):
                continue
            scenarios[sid] = s
    return scenarios


def discover_pairs(scenarios: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Find (donor, recipient, pivot_action) triplets.

    A triplet is emitted when action `a` is in donor's expected set AND in
    recipient's forbidden set (or vice versa).
    """
    expected_map: dict[str, set[str]] = {sid: _as_set(s.get("expected_actions")) for sid, s in scenarios.items()}
    forbidden_map: dict[str, set[str]] = {sid: _as_set(s.get("forbidden_actions")) for sid, s in scenarios.items()}
    triplets: list[dict[str, Any]] = []
    sids = sorted(scenarios.keys())
    for donor_sid in sids:
        donor_expected = expected_map[donor_sid]
        if not donor_expected:
            continue
        for recipient_sid in sids:
            if recipient_sid == donor_sid:
                continue
            recipient_forbidden = forbidden_map[recipient_sid]
            if not recipient_forbidden:
                continue
            pivots = donor_expected & recipient_forbidden
            for pivot in sorted(pivots):
                triplets.append(
                    {
                        "donor_scenario_id": donor_sid,
                        "recipient_scenario_id": recipient_sid,
                        "pivot_action": pivot,
                        "donor_graph": scenarios[donor_sid].get("guideline_graph"),
                        "recipient_graph": scenarios[recipient_sid].get("guideline_graph"),
                    }
                )
    return triplets


def deduplicate_by_pivot(triplets: list[dict[str, Any]], max_per_pivot: int = 3) -> list[dict[str, Any]]:
    """Keep at most `max_per_pivot` triplets for each pivot action to reduce
    overrepresentation of popular pivot actions.
    """
    by_pivot: dict[str, list[dict[str, Any]]] = {}
    for t in triplets:
        by_pivot.setdefault(t["pivot_action"], []).append(t)
    kept: list[dict[str, Any]] = []
    for pivot, lst in sorted(by_pivot.items()):
        kept.extend(lst[:max_per_pivot])
    return kept


def main() -> int:
    """Run pair discovery and emit JSON."""
    parser = argparse.ArgumentParser()
    parser.add_argument("--max-per-pivot", type=int, default=3, help="Cap triplets per pivot action")
    parser.add_argument("--output", default=str(OUTPUT_FILE))
    args = parser.parse_args()

    print(f"Scanning {SCENARIO_DIR} ...")
    scenarios = load_scenarios()
    print(f"  Loaded {len(scenarios)} scenarios")

    triplets = discover_pairs(scenarios)
    print(f"  Discovered {len(triplets)} raw triplets")

    dedup = deduplicate_by_pivot(triplets, max_per_pivot=args.max_per_pivot)
    print(f"  Dedup to {len(dedup)} triplets (max {args.max_per_pivot} per pivot action)")

    pivot_counts: dict[str, int] = {}
    for t in triplets:
        pivot_counts[t["pivot_action"]] = pivot_counts.get(t["pivot_action"], 0) + 1
    top = sorted(pivot_counts.items(), key=lambda kv: -kv[1])[:10]
    print("  Top 10 most-represented pivots (raw counts):")
    for p, c in top:
        print(f"    {p:<40s} {c}")

    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w") as f:
        json.dump(
            {
                "n_scenarios": len(scenarios),
                "n_raw_triplets": len(triplets),
                "n_deduplicated_triplets": len(dedup),
                "max_per_pivot": args.max_per_pivot,
                "triplets": dedup,
            },
            f,
            indent=2,
        )
    print(f"  Saved: {output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
