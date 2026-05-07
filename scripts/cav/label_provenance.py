"""CAV v0.5 Phase 2 — Provenance Tier Labeling.

Reads cav_v0_5/01_raw_harvest.json and assigns each canonical_id a tier
(explicit / implicit / extension) plus an action_kind classification.

Tier rules (priority: explicit > implicit > extension):
  explicit  : appears in any graph_mandatory OR graph_forbidden
  implicit  : appears only in graph_allowed (never mandatory/forbidden)
  extension : appears ONLY in scenario_* fields (never in any graph_* field)

Path-aware: --input / --output / --dropped flags so this script can be
re-pointed at a v6.1 / v7 harvest output for CAV v0.6 builds later.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

# Action-kind prefix rules (order matters — first match wins). Longer prefixes
# come first to disambiguate (e.g. "order_lab_" before "order_imaging_" before
# "order_").
_KIND_PREFIXES: list[tuple[str, tuple[str, ...]]] = [
    ("medication", ("give_", "administer_", "start_", "prescribe_", "infuse_", "bolus_")),
    ("lab", ("order_lab_", "draw_", "check_lab_", "measure_")),
    ("imaging", ("order_imaging_", "perform_ct", "perform_mri", "obtain_xray", "order_ecg")),
    ("procedure", ("perform_", "intubate_", "place_", "insert_", "cannulate_")),
    ("assessment", ("assess_", "monitor_", "evaluate_", "examine_")),
    ("consult", ("consult_",)),
    ("disposition", ("admit_", "discharge_", "transfer_")),
]


def classify_kind(canonical_id: str) -> str:
    cid = canonical_id.lower()
    for kind, prefixes in _KIND_PREFIXES:
        if any(cid.startswith(p) for p in prefixes):
            return kind
    return "other"


def assign_tier(occurrences: list[dict[str, Any]]) -> str:
    sources = {occ["source"] for occ in occurrences}
    has_mandatory = "graph_mandatory" in sources
    has_forbidden = "graph_forbidden" in sources
    has_allowed = "graph_allowed" in sources
    has_scenario = any(s.startswith("scenario_") for s in sources)
    if has_mandatory or has_forbidden:
        return "explicit"
    if has_allowed:
        return "implicit"
    if has_scenario:
        return "extension"
    # No source at all — shouldn't happen, but fall through to extension.
    return "extension"


def label(harvest_data: dict[str, Any]) -> dict[str, Any]:
    out_entries: dict[str, dict[str, Any]] = {}
    tier_counter: Counter[str] = Counter()
    kind_counter: Counter[str] = Counter()
    kind_by_tier: dict[str, Counter[str]] = defaultdict(Counter)

    for canonical_id, entry in harvest_data["entries"].items():
        tier = assign_tier(entry["occurrences"])
        kind = classify_kind(canonical_id)
        out_entries[canonical_id] = {
            "tier": tier,
            "action_kind": kind,
            "raw_forms": entry["raw_forms"],
            "occurrences": entry["occurrences"],
        }
        tier_counter[tier] += 1
        kind_counter[kind] += 1
        kind_by_tier[tier][kind] += 1

    return {
        "metadata": {
            **harvest_data.get("metadata", {}),
            "phase": "labeled",
            "labeled_at": datetime.now(UTC).isoformat(),
        },
        "tier_summary": dict(tier_counter),
        "kind_summary": dict(kind_counter),
        "kind_by_tier": {t: dict(c) for t, c in kind_by_tier.items()},
        "entries": out_entries,
    }


def build_dropped_view(labeled: dict[str, Any]) -> dict[str, Any]:
    """Return just the extension-tier entries, sorted by occurrence count desc."""
    rows: list[tuple[str, dict[str, Any]]] = []
    for cid, entry in labeled["entries"].items():
        if entry["tier"] != "extension":
            continue
        rows.append((cid, entry))
    rows.sort(key=lambda kv: -len(kv[1]["occurrences"]))
    return {
        "metadata": {
            **labeled["metadata"],
            "view": "extension_dropped",
            "n_dropped": len(rows),
        },
        "entries": {cid: entry for cid, entry in rows},
    }


def _print_summary(labeled: dict[str, Any], dropped: dict[str, Any]) -> tuple[int, int]:
    tiers = labeled["tier_summary"]
    kinds = labeled["kind_summary"]
    print("=== CAV Phase 2: Provenance Labeling ===")
    print(f"  Total entries: {sum(tiers.values())}")
    print("  Tier distribution:")
    for t in ("explicit", "implicit", "extension"):
        print(f"    {t:10s} {tiers.get(t, 0):5d}")
    print()
    print("  Kind distribution (overall):")
    for k, n in sorted(kinds.items(), key=lambda kv: -kv[1]):
        print(f"    {k:12s} {n:5d}")
    print()
    print("  Kind by tier:")
    print(f"    {'kind':12s}  {'explicit':>8s}  {'implicit':>8s}  {'extension':>9s}")
    all_kinds = set()
    for t in labeled["kind_by_tier"].values():
        all_kinds |= set(t.keys())
    for k in sorted(all_kinds):
        e = labeled["kind_by_tier"].get("explicit", {}).get(k, 0)
        i = labeled["kind_by_tier"].get("implicit", {}).get(k, 0)
        x = labeled["kind_by_tier"].get("extension", {}).get(k, 0)
        print(f"    {k:12s}  {e:>8d}  {i:>8d}  {x:>9d}")
    print()

    # Phase 3 workload preview
    med_explicit = labeled["kind_by_tier"].get("explicit", {}).get("medication", 0)
    med_implicit = labeled["kind_by_tier"].get("implicit", {}).get("medication", 0)
    print(
        f"  Phase 3 workload (RxNav-mappable medications): "
        f"{med_explicit + med_implicit} ({med_explicit} explicit + {med_implicit} implicit)"
    )
    print()

    # anonymous-user's request: extension-tier raw_forms breakdown
    ext_unique = 0
    ext_multi = 0
    for entry in dropped["entries"].values():
        if len(entry["raw_forms"]) <= 1:
            ext_unique += 1
        else:
            ext_multi += 1
    print("  Extension-tier raw_forms breakdown:")
    print(f"    raw_forms count == 1 (truly unique scenario-only ID): {ext_unique}")
    print(f"    raw_forms count >= 2 (multi-variant collapsed to scenario-only canonical): {ext_multi}")
    print()

    print("  Top 30 extension-tier entries by occurrence count:")
    print(f"    {'#':>3} {'n_occ':>5}  {'kind':12s}  {'#raw':>4}  canonical_id")
    for i, (cid, entry) in enumerate(list(dropped["entries"].items())[:30], 1):
        n_occ = len(entry["occurrences"])
        n_raw = len(entry["raw_forms"])
        kind = entry["action_kind"]
        print(f"    {i:>3} {n_occ:>5d}  {kind:12s}  {n_raw:>4d}  {cid}")
    print()

    return tiers.get("extension", 0), ext_multi


def main() -> int:
    parser = argparse.ArgumentParser(description="CAV v0.5 Phase 2: tier labeling")
    parser.add_argument(
        "--input",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "01_raw_harvest.json",
        help="Phase 1 harvest output JSON.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "02_labeled.json",
        help="Phase 2 labeled output JSON.",
    )
    parser.add_argument(
        "--dropped",
        type=Path,
        default=REPO_ROOT / "cav_v0_5" / "02_extension_dropped.json",
        help="Extension-tier subset (for spot-check).",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit non-zero if extension-tier count outside [50,250] (recalibrated 2026-05-01).",
    )
    args = parser.parse_args()

    if not args.input.is_file():
        print(f"[ERROR] --input not found: {args.input}", file=sys.stderr)
        return 2

    harvest_data = json.loads(args.input.read_text(encoding="utf-8"))
    labeled = label(harvest_data)
    dropped = build_dropped_view(labeled)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(labeled, indent=2, sort_keys=False), encoding="utf-8")
    args.dropped.write_text(json.dumps(dropped, indent=2, sort_keys=False), encoding="utf-8")
    print(f"[INFO] Wrote {args.output} ({sum(labeled['tier_summary'].values())} entries)")
    print(f"[INFO] Wrote {args.dropped} ({dropped['metadata']['n_dropped']} extension-tier entries)")
    print()

    extension_count, ext_multi = _print_summary(labeled, dropped)

    if args.strict:
        if not (50 <= extension_count <= 250):
            print(
                f"[STOP] extension-tier count {extension_count} outside expected [50,250]",
                file=sys.stderr,
            )
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
