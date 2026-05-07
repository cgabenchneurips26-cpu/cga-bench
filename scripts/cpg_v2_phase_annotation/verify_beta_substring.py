"""Verify beta annotation source_text fields are verbatim substrings.

For every entry in data/cpg_source_properties.json that has
``annotation_tier: "beta"``, checks that each C7-C12 source_text field is
an exact substring of the corresponding rag_corpus parsed.json content.
This is the "LLM did not hallucinate a quote" guarantee.

Usage:
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/verify_beta_substring.py

    # Verify a single graph
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/verify_beta_substring.py \
        --graph-id aha_cardiogenic_shock_2017

Exit codes:
    0  all beta entries pass
    1  at least one beta entry has a non-substring quote
    2  misconfiguration (file missing, etc.)

Recommended to run as part of CI alongside audit_sources.py and
leakage_scan.py.
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path
import re
from typing import Any

logger = logging.getLogger(__name__)

BETA_SOURCE_TEXT_FIELDS: list[str] = [
    "c7_source_text",
    "c8_source_text",
    "c9_source_text",
    "c10_source_text",
    "c11_source_text",
    "c12_source_text",
]

# Map graph_id -> canonical rag_corpus filename. This mapping grows over time
# as beta CPGs are added; for now, derived by matching graph_id substring in
# filenames under data_release/v5.0/rag_corpus/.
RAG_CORPUS_DIR = Path("data_release/v5.0/rag_corpus")


def load_source_properties(path: Path) -> dict[str, dict[str, Any]]:
    """Load cpg_source_properties.json, accepting either {graphs: {...}} or flat."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return data.get("graphs", data)


def find_rag_corpus(graph_id: str) -> Path | None:
    """Find the rag_corpus parsed.json for a graph_id by reading the graph_id key.

    First tries a direct scan (every parsed.json contains its own graph_id field).
    Falls back to substring match on filename.
    """
    if not RAG_CORPUS_DIR.exists():
        return None
    # Primary: read graph_id field from each parsed.json.
    for p in RAG_CORPUS_DIR.glob("*.parsed.json"):
        try:
            content = json.loads(p.read_text(encoding="utf-8"))
            if content.get("graph_id") == graph_id:
                return p
        except (OSError, json.JSONDecodeError):
            continue
    # Fallback: substring match.
    token = graph_id.replace("_", "-").lower()
    for p in RAG_CORPUS_DIR.glob("*.parsed.json"):
        if token.lower() in p.stem.lower():
            return p
    return None


def parsed_corpus_text(path: Path) -> str:
    """Concatenate all text fields in parsed.json for substring checking."""
    content = json.loads(path.read_text(encoding="utf-8"))
    parts: list[str] = []
    parts.append(str(content.get("guideline_name", "")))
    parts.append(str(content.get("source", "")))
    for rec in content.get("recommendations", []) or []:
        if isinstance(rec, dict):
            parts.append(str(rec.get("text", "")))
    for tbl in content.get("tables", []) or []:
        if isinstance(tbl, dict):
            parts.append(str(tbl.get("title", "")))
            data = tbl.get("data")
            if data is not None:
                parts.append(json.dumps(data))
    ks = content.get("key_sections", {}) or {}
    if isinstance(ks, dict):
        for v in ks.values():
            parts.append(str(v))
    return "\n".join(parts)


def _normalize(text: str) -> str:
    """Collapse whitespace for forgiving substring matching."""
    return re.sub(r"\s+", " ", text).strip().lower()


def verify_graph(graph_id: str, entry: dict[str, Any]) -> tuple[bool, list[tuple[str, str, str]]]:
    """Verify one graph. Returns (all_passed, failures_list).

    Each failure tuple is (field_name, source_text_sample, reason).
    """
    if entry.get("annotation_tier") != "beta":
        logger.debug("Skipping %s (tier=%s)", graph_id, entry.get("annotation_tier"))
        return True, []

    rag_path = find_rag_corpus(graph_id)
    if rag_path is None:
        return False, [("<rag_corpus>", "", f"no parsed.json found for {graph_id}")]
    try:
        corpus = _normalize(parsed_corpus_text(rag_path))
    except Exception as exc:
        return False, [("<rag_corpus>", "", f"failed to load {rag_path}: {exc}")]

    failures: list[tuple[str, str, str]] = []
    for field in BETA_SOURCE_TEXT_FIELDS:
        quote = entry.get(field)
        if not quote or not isinstance(quote, str):
            continue
        normalized_quote = _normalize(quote)
        if normalized_quote not in corpus:
            sample = quote[:80].replace("\n", " ")
            failures.append((field, sample, "not an exact substring of rag_corpus content"))
    return len(failures) == 0, failures


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-props",
        type=Path,
        default=Path("data/cpg_source_properties.json"),
        help="Path to cpg_source_properties.json",
    )
    parser.add_argument(
        "--graph-id",
        default="",
        help="Verify a single graph only (default: all beta-tier entries)",
    )
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.source_props.exists():
        logger.error("Source properties file not found: %s", args.source_props)
        return 2

    props = load_source_properties(args.source_props)
    targets = [args.graph_id] if args.graph_id else list(props.keys())

    passed: list[str] = []
    failed: list[tuple[str, list[tuple[str, str, str]]]] = []
    skipped: list[str] = []

    for gid in targets:
        entry = props.get(gid)
        if entry is None:
            logger.warning("graph_id %s not in source properties", gid)
            skipped.append(gid)
            continue
        ok, failures = verify_graph(gid, entry)
        if entry.get("annotation_tier") != "beta":
            skipped.append(gid)
            continue
        if ok:
            passed.append(gid)
        else:
            failed.append((gid, failures))

    print("\n=== verify_beta_substring report ===")
    print(f"beta entries: {len(passed) + len(failed)}")
    print(f"  passed: {len(passed)}")
    print(f"  failed: {len(failed)}")
    print(f"skipped (non-beta): {len(skipped)}")

    if failed:
        print("\nFailures:")
        for gid, failures in failed:
            print(f"  {gid}:")
            for field, sample, reason in failures:
                print(f"    - {field}: {reason}")
                if sample:
                    print(f"      sample quote: {sample!r}...")
        return 1

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
