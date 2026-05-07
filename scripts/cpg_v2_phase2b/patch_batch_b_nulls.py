"""Patch Batch B null fields with conservative heuristic estimates.

Batch B (44 candidates) has null values for c9, c11, c12 because
full-text access was not available during initial annotation. This
script fills nulls using conservative inferences from already-populated
fields (c1, c7, c8, c10) — the same logic as estimate_c1_c12_for_99.py
but grounded in the actual annotated metadata rather than M1-M6 proxies.

Rules:
  c9 (algorithm figure):
    - c7 == "critical" and c1_tier1_society → 2 (critical emergencies always have algorithms)
    - c1_tier1_society → 1 (Tier-1 guidelines usually have at least a simple flowchart)
    - else → 1 (conservative: most CPGs include some decision aid)

  c11 (sequence dependency):
    - c10_time_constraints_explicit == True → 1 (time constraints imply ordered steps)
    - c7 in ("critical", "moderate") → 1 (emergency guidelines have "X before Y")
    - else → 0

  c12 (conditional branching):
    - c8_contraindication_explicit >= 1 → 1 (contraindications imply "if X then Y")
    - c7 == "critical" → 1 (critical emergencies always branch on patient status)
    - else → 0

Also patches any other null scoring fields (c2, c4, c8, c10) with 0.

Usage:
    python scripts/cpg_v2_phase2b/patch_batch_b_nulls.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

BATCH_B_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "cpg_source_properties_candidates_bulk_B.json"


def infer_c9(entry: dict) -> int:
    """Conservative c9 estimate from c1 + c7."""
    c7 = (entry.get("c7_time_to_harm") or "").lower()
    c1 = entry.get("c1_tier1_society", False)
    if c7 == "critical" and c1:
        return 2
    if c1:
        return 1
    return 1  # Most CPGs include some decision aid


def infer_c11(entry: dict) -> int:
    """Conservative c11 estimate from c10 + c7."""
    c10_explicit = entry.get("c10_time_constraints_explicit")
    c7 = (entry.get("c7_time_to_harm") or "").lower()
    if c10_explicit:
        return 1
    if c7 in ("critical", "moderate"):
        return 1
    return 0


def infer_c12(entry: dict) -> int:
    """Conservative c12 estimate from c8 + c7."""
    c8 = entry.get("c8_contraindication_explicit")
    c7 = (entry.get("c7_time_to_harm") or "").lower()
    if c8 is not None and c8 >= 1:
        return 1
    if c7 == "critical":
        return 1
    return 0


def patch_entry(graph_id: str, entry: dict) -> list[str]:
    """Patch null fields in a single entry. Returns list of changes."""
    changes: list[str] = []

    # c9 fields
    if entry.get("c9_score") is None:
        score = infer_c9(entry)
        entry["c9_score"] = score
        entry["c9_has_algorithm_figure"] = score > 0
        entry["c9_figure_count"] = score
        entry["_c9_patched"] = "heuristic from c1+c7"
        changes.append(f"c9_score={score}")

    # c11 fields
    if entry.get("c11_sequence_dependency_explicit") is None:
        val = infer_c11(entry)
        entry["c11_sequence_dependency_explicit"] = bool(val)
        if val and not entry.get("c11_source_text"):
            entry["c11_source_text"] = "[inferred from c10/c7 — reviewer TODO]"
        entry["_c11_patched"] = "heuristic from c10+c7"
        changes.append(f"c11={val}")

    # c12 fields
    if entry.get("c12_conditional_branching_explicit") is None:
        val = infer_c12(entry)
        entry["c12_conditional_branching_explicit"] = bool(val)
        if val and not entry.get("c12_source_text"):
            entry["c12_source_text"] = "[inferred from c8+c7 — reviewer TODO]"
        entry["_c12_patched"] = "heuristic from c8+c7"
        changes.append(f"c12={val}")

    # Other null scoring fields → 0
    for field, default in [
        ("c2_evidence_system_score", 0),
        ("c4_recency_year", 2000),
        ("c8_contraindication_explicit", 0),
        ("c10_time_constraints_explicit", False),
        ("c10_time_statements_count", 0),
        ("c10_score", 0),
    ]:
        if entry.get(field) is None:
            entry[field] = default
            changes.append(f"{field}={default}")

    return changes


def main() -> None:
    parser = argparse.ArgumentParser(description="Patch Batch B null fields")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing")
    args = parser.parse_args()

    with open(BATCH_B_PATH) as f:
        data = json.load(f)

    total_changes = 0
    for graph_id, entry in data["graphs"].items():
        changes = patch_entry(graph_id, entry)
        if changes:
            total_changes += len(changes)
            if args.dry_run:
                print(f"  {graph_id}: {', '.join(changes)}")

    # Update metadata
    data["_metadata"]["status"] = (
        data["_metadata"].get("status", "DRAFT") + " | PATCHED: c9/c11/c12 nulls filled with conservative heuristics"
    )
    data["_metadata"]["scoring_discipline"]["c7_c9_c11_c12_status"] = (
        "PATCHED — c9/c11/c12 filled with conservative heuristic estimates "
        "from c1/c7/c8/c10. All entries include _c*_patched marker."
    )

    if args.dry_run:
        print(f"\n[DRY RUN] Would apply {total_changes} changes to {len(data['graphs'])} entries")
    else:
        with open(BATCH_B_PATH, "w") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"Patched {total_changes} null fields across {len(data['graphs'])} entries")
        print(f"Written to: {BATCH_B_PATH}")


if __name__ == "__main__":
    main()
