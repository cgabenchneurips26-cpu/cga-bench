"""Merge Method A + Method B + auto_extract outputs into a beta source_properties entry.

Reads per-CPG JSON outputs from the three annotation stages and produces a
single entry compatible with ``data/cpg_source_properties.json``. Does NOT
modify the source_properties file directly — emits a staging JSON that a
human reviewer can inspect before merging.

Inputs (per-CPG):
    - Method A (LLM source-quote extraction):
        reports/method_a_outputs/<graph_id>.json
    - Method B (dual-LLM agreement):
        reports/method_b_outputs/<graph_id>.json
    - auto_extract_c1_c12 (metadata regex):
        data/proposals/<graph_id>.json  (optional; if absent, C1-C6/C8/C10
        left with None and flagged for manual entry)

Output:
    staging/beta_candidates/<graph_id>.json — a fully assembled source-
    properties entry with annotation_tier="beta", dual_llm_agreement
    metadata, and human_verified_by=None placeholder for the reviewer
    to fill in before committing to data/cpg_source_properties.json.

Usage:
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/merge_beta_annotations.py \
        --graph-id aha_cardiogenic_shock_2017 \
        --method-a reports/method_a_outputs/aha_cardiogenic_shock_2017.json \
        --method-b reports/method_b_outputs/aha_cardiogenic_shock_2017.json \
        --auto-extract data/proposals/aha_cardiogenic_shock_2017.json \
        --output staging/beta_candidates/aha_cardiogenic_shock_2017.json

Conflict-resolution policy for LLM-semantic criteria (C7, C9, C11, C12):
    - If Method A and Method B agree: accept the score. Use Method A's
      quote as ``source_text`` (Method B prompt is quote-free).
    - If they disagree: ``annotation_tier: "beta_pending_adjudication"``
      and ``disagreement_note`` is populated; reviewer picks one.

Metadata criteria (C1-C6, C8, C10):
    - Taken from auto_extract if present; otherwise set to None and
      listed under ``_reviewer_todo``.

The final reviewer must:
    1. Inspect every "_reviewer_todo" entry and fill a value.
    2. Resolve any "beta_pending_adjudication" cases.
    3. Flip annotation_tier to "beta" and set human_verified_by + date.
    4. Move file from staging/ to data/cpg_source_properties.json
       (as a new entry under graphs.<graph_id>).
"""

from __future__ import annotations

import argparse
import datetime
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

LLM_SEMANTIC_CRITERIA: list[str] = ["C7", "C9", "C11", "C12"]
METADATA_CRITERIA: list[str] = ["C1", "C2", "C3", "C4", "C5", "C6", "C8", "C10"]
ALL_CRITERIA: list[str] = sorted(LLM_SEMANTIC_CRITERIA + METADATA_CRITERIA)


def load_json(path: Path) -> dict[str, Any] | None:
    """Load a JSON file or return None if absent/invalid."""
    if not path or not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.warning("Invalid JSON in %s: %s", path, exc)
        return None


def extract_method_a(data: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Extract per-criterion {score, source_text, confidence} from Method A output."""
    if not data:
        return {}
    out: dict[str, dict[str, Any]] = {}
    results = data.get("results", {})
    for c, r in results.items():
        out[c] = {
            "score": r.get("score"),
            "source_text": r.get("source_text"),
            "page_or_section": r.get("page_or_section"),
            "confidence": r.get("confidence"),
            "error": r.get("error"),
        }
    return out


def extract_method_b(data: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    """Extract per-criterion {score_a, score_b, justifications} from Method B."""
    if not data:
        return {}
    return data.get("per_criterion", {})


def extract_auto_extract(data: dict[str, Any] | None) -> dict[str, Any]:
    """Extract metadata-criteria proposals from auto_extract_c1_c12 output."""
    if not data:
        return {}
    return data


def score_field(criterion: str) -> str:
    """Map criterion ID to the cpg_source_properties.json field name."""
    return f"{criterion.lower()}_score"


def source_text_field(criterion: str) -> str:
    """Map criterion ID to the source_text field name."""
    return f"{criterion.lower()}_source_text"


def merge_llm_semantic(
    criterion: str,
    method_a: dict[str, dict[str, Any]],
    method_b: dict[str, dict[str, Any]],
) -> tuple[int | None, str | None, str | None]:
    """Merge one LLM-semantic criterion. Returns (score, source_text, note)."""
    a = method_a.get(criterion, {})
    b = method_b.get(criterion, {})
    score_a = a.get("score")
    score_b = b.get("score_a") if isinstance(b.get("score_a"), int) else b.get("score_a")
    # method_b per_criterion keeps score_a/score_b — pick the one from rater A (same family if needed).
    # For the merge we compare A (Method A) vs B (Method B rater B).
    raw_b_second = b.get("score_b")
    source_text = a.get("source_text")

    # If Method A and Method B's rater B agree on score, accept.
    if score_a is not None and raw_b_second is not None and score_a == raw_b_second:
        return score_a, source_text, None
    # If only Method A available, trust it (with a note).
    if raw_b_second is None and score_a is not None:
        return score_a, source_text, "method_b absent; method_a only"
    # If only Method B available, can't produce a quote.
    if score_a is None and raw_b_second is not None:
        return raw_b_second, None, "method_a absent; score from method_b only"
    # Both absent — criterion not run.
    if score_a is None and raw_b_second is None:
        return None, None, "both method_a and method_b missing this criterion"
    # Real disagreement — flag for adjudication.
    return (
        None,
        None,
        (f"disagreement: method_a={score_a} method_b_raterA={b.get('score_a')} method_b_raterB={raw_b_second}"),
    )


def merge_metadata(criterion: str, auto_extract: dict[str, Any]) -> tuple[int | None, str | None, str | None]:
    """Extract metadata criterion from auto_extract output.

    Returns (score, source_text, note).
    """
    if not auto_extract:
        return None, None, "auto_extract absent; manual entry required"
    # auto_extract_c1_c12 output shape: {cX_score: int, cX_source_text: str, ...}
    sf = score_field(criterion)
    tf = source_text_field(criterion)
    score = auto_extract.get(sf)
    text = auto_extract.get(tf)
    if score is None and text is None:
        return None, None, "auto_extract missing this criterion"
    return score, text, None


def build_entry(
    graph_id: str,
    guideline_name: str,
    method_a_path: Path | None,
    method_b_path: Path | None,
    auto_extract_path: Path | None,
) -> dict[str, Any]:
    """Assemble the merged entry."""
    method_a = extract_method_a(load_json(method_a_path) if method_a_path else None)
    method_b = extract_method_b(load_json(method_b_path) if method_b_path else None)
    auto_extract = extract_auto_extract(load_json(auto_extract_path) if auto_extract_path else None)

    entry: dict[str, Any] = {
        "graph_id": graph_id,
        "guideline_name": guideline_name,
        "annotation_tier": "beta",
        "human_verified_by": None,
        "verification_date": None,
        "dual_llm_agreement": {},
        "_reviewer_todo": [],
        "_source_provenance": {
            "method_a": str(method_a_path) if method_a_path else None,
            "method_b": str(method_b_path) if method_b_path else None,
            "auto_extract": str(auto_extract_path) if auto_extract_path else None,
        },
    }

    # Populate kappa + disagreements if Method B output present.
    if method_b_path and method_b_path.exists():
        b_full = load_json(method_b_path) or {}
        agreement = b_full.get("agreement", {})
        entry["dual_llm_agreement"] = {
            "cohen_kappa": agreement.get("cohen_kappa"),
            "exact_agreement_rate": agreement.get("exact_agreement_rate"),
            "disagreements": agreement.get("disagreements", []),
            "rater_a": b_full.get("rater_a"),
            "rater_b": b_full.get("rater_b"),
        }

    # LLM-semantic criteria: merge Method A + B.
    pending_adjudication = False
    for c in LLM_SEMANTIC_CRITERIA:
        score, text, note = merge_llm_semantic(c, method_a, method_b)
        entry[score_field(c)] = score
        entry[source_text_field(c)] = text
        if note:
            entry["_reviewer_todo"].append({"criterion": c, "note": note})
        if note and "disagreement" in note:
            pending_adjudication = True

    # Metadata criteria: from auto_extract.
    for c in METADATA_CRITERIA:
        score, text, note = merge_metadata(c, auto_extract)
        entry[score_field(c)] = score
        entry[source_text_field(c)] = text
        if note:
            entry["_reviewer_todo"].append({"criterion": c, "note": note})

    if pending_adjudication:
        entry["annotation_tier"] = "beta_pending_adjudication"

    entry["_generated_at"] = datetime.datetime.utcnow().isoformat(timespec="seconds") + "Z"
    return entry


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-id", required=True)
    parser.add_argument("--guideline-name", default="")
    parser.add_argument("--method-a", type=Path, default=None)
    parser.add_argument("--method-b", type=Path, default=None)
    parser.add_argument("--auto-extract", type=Path, default=None)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not any([args.method_a, args.method_b, args.auto_extract]):
        raise SystemExit("At least one of --method-a / --method-b / --auto-extract is required")

    entry = build_entry(
        graph_id=args.graph_id,
        guideline_name=args.guideline_name,
        method_a_path=args.method_a,
        method_b_path=args.method_b,
        auto_extract_path=args.auto_extract,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(entry, indent=2), encoding="utf-8")

    print(f"\nMerged entry for {args.graph_id} -> {args.output}")
    print(f"  annotation_tier: {entry['annotation_tier']}")
    print(f"  reviewer_todo items: {len(entry['_reviewer_todo'])}")
    for todo in entry["_reviewer_todo"]:
        print(f"    - {todo['criterion']}: {todo['note']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
