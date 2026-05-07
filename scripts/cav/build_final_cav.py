"""CAV v0.5 Phase 4 — Build final CAV artifact.

Merges Phase 2 (tier labels) + Phase 3 (RxNorm mappings) into the canonical
artifact `cav_v0_5/cav_v0_5.json` (Strict policy: extension entries dropped),
and writes `cav_v0_5/cav_v0_5_dropped.json` for paper disclosure.
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

CAV_VERSION = "0.5"
CAV_POLICY = "strict"


def build(labeled: dict[str, Any], rxnorm: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    rxnorm_mappings = rxnorm.get("mappings", {})

    by_tier = {"explicit": 0, "implicit": 0}
    by_kind: dict[str, int] = {}
    rxnorm_mapped = 0
    final_entries: dict[str, dict[str, Any]] = {}
    dropped_entries: dict[str, dict[str, Any]] = {}

    for canonical_id, entry in labeled["entries"].items():
        tier = entry["tier"]
        kind = entry["action_kind"]

        if tier == "extension":
            dropped_entries[canonical_id] = {
                "action_kind": kind,
                "raw_forms": entry["raw_forms"],
                "occurrences": entry["occurrences"],
            }
            continue

        rxnorm_payload = rxnorm_mappings.get(canonical_id)
        if rxnorm_payload:
            rxnorm_mapped += 1

        final_entries[canonical_id] = {
            "tier": tier,
            "action_kind": kind,
            "raw_forms": entry["raw_forms"],
            "rxnorm": rxnorm_payload,  # may be None
            "occurrences": entry["occurrences"],
        }
        by_tier[tier] = by_tier.get(tier, 0) + 1
        by_kind[kind] = by_kind.get(kind, 0) + 1

    final = {
        "version": CAV_VERSION,
        "policy": CAV_POLICY,
        "build_date": datetime.now(UTC).isoformat(),
        "summary": {
            "total_entries": len(final_entries),
            "by_tier": by_tier,
            "by_kind": by_kind,
            "rxnorm_mapped": rxnorm_mapped,
        },
        "metadata": {
            **labeled.get("metadata", {}),
            "rxnorm_metadata": rxnorm.get("metadata", {}),
        },
        "entries": final_entries,
    }

    dropped = {
        "version": CAV_VERSION,
        "policy": CAV_POLICY,
        "n_dropped": len(dropped_entries),
        "build_date": final["build_date"],
        "metadata": {
            "note": "Extension-tier entries dropped under Strict policy. "
            "These are scenario-injected actions never present in any "
            "graph_mandatory / graph_allowed / graph_forbidden field. "
            "Use this file for paper disclosure / spot-check (Phase 5).",
        },
        "dropped_entries": dropped_entries,
    }
    return final, dropped


def _print_summary(final: dict[str, Any], dropped: dict[str, Any]) -> None:
    s = final["summary"]
    print("=== CAV Phase 4: Final Artifact ===")
    print(f"  Version:        {final['version']}")
    print(f"  Policy:         {final['policy']}")
    print(f"  Build date:     {final['build_date']}")
    print()
    print(f"  Final CAV size: {s['total_entries']} entries")
    print("    by tier:")
    for t, n in s["by_tier"].items():
        print(f"      {t:10s} {n:5d}")
    print("    by kind:")
    for k, n in sorted(s["by_kind"].items(), key=lambda kv: -kv[1]):
        print(f"      {k:12s} {n:5d}")
    print()
    print(f"  RxNorm-mapped:  {s['rxnorm_mapped']} / {s['by_kind'].get('medication', 0)} medications")
    print(f"  Dropped:        {dropped['n_dropped']} extension-tier entries (paper disclosure)")


def main() -> int:
    parser = argparse.ArgumentParser(description="CAV v0.5 Phase 4: build final CAV artifact")
    parser.add_argument(
        "--labeled",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "02_labeled.json",
        help="Phase 2 labeled output JSON.",
    )
    parser.add_argument(
        "--rxnorm",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "03_rxnorm_mapping.json",
        help="Phase 3 RxNorm mapping output JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "cav_v0_5.json",
        help="Final canonical CAV artifact path.",
    )
    parser.add_argument(
        "--dropped-output",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "cav_v0_5_dropped.json",
        help="Path for the dropped extension-tier subset.",
    )
    args = parser.parse_args()

    if not args.labeled.is_file():
        print(f"[ERROR] --labeled not found: {args.labeled}", file=sys.stderr)
        return 2
    if not args.rxnorm.is_file():
        print(f"[ERROR] --rxnorm not found: {args.rxnorm}", file=sys.stderr)
        return 2

    labeled = json.loads(args.labeled.read_text(encoding="utf-8"))
    rxnorm = json.loads(args.rxnorm.read_text(encoding="utf-8"))
    final, dropped = build(labeled, rxnorm)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(final, indent=2, sort_keys=False), encoding="utf-8")
    args.dropped_output.write_text(json.dumps(dropped, indent=2, sort_keys=False), encoding="utf-8")
    print(f"[INFO] Wrote {args.output} ({final['summary']['total_entries']} entries)")
    print(f"[INFO] Wrote {args.dropped_output} ({dropped['n_dropped']} dropped)")
    print()
    _print_summary(final, dropped)
    return 0


if __name__ == "__main__":
    sys.exit(main())
