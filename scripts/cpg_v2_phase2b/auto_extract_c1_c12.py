"""Phase C: Auto-extract C1-C12 Source-Document properties from a CPG text file.

Takes a local HTML/text/PDF-converted-to-text file and produces a JSON
annotation block compatible with data/cpg_source_properties.json.

Automation budget per criterion:

    Fully automatable (regex / lookup table):
      C1  Tier-1 society            — publisher token match
      C2  Evidence grading system   — "GRADE" / "Class I" / "LOE" regex
      C3  Systematic review         — "systematic review" in Methods
      C4  Recency year              — publication_year (supplied)
      C5  DOI                       — DOI regex
      C6  GBD burden                — graph_id -> GBD lookup
      C8  Contraindication count    — "contraindicated" / "should not" count
      C10 Time constraints          — "within X minutes" count

    Semi-manual (LLM-assist or reviewer TODO):
      C7  Time-to-harm severity     — reviewer judgment
      C9  Algorithm figure count    — PDF figure detection required
      C11 Sequence dependency       — "before X" semantic read
      C12 Conditional branching     — "if X then" semantic read

The script emits a full annotation block with proposed values and a
``_reviewer_todo`` list highlighting the 4 fields that need spot-check.

Usage:
    PYTHONPATH=. python scripts/cpg_v2_phase2b/auto_extract_c1_c12.py \\
        --source-file /tmp/hhs_2024.html \\
        --graph-id ada_hhs_2024 \\
        --guideline-name "ADA Hyperglycemic Crises 2024" \\
        --publisher "ADA" \\
        --publication-year 2024 \\
        --output data/proposals/ada_hhs_2024.json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# Reuse scoring-side constants to keep detection aligned with score_cpg_v2.
from scripts.score_cpg_v2 import (  # noqa: E402
    FORMAL_EVIDENCE_SYSTEMS,
    SOCIETY_EVIDENCE_SYSTEMS,
    TIER_1_SOCIETIES,
    load_gbd_table,
)

DOI_RE = re.compile(r"\b10\.\d{4,9}/[-._;()/:A-Z0-9]+", re.IGNORECASE)
YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")
WITHIN_TIME_RE = re.compile(r"\bwithin\s+\d+\s*(minute|min|hour|hr)s?\b", re.IGNORECASE)
DEADLINE_PHRASE_RE = re.compile(
    r"(door[- ]to[- ](balloon|needle)|time[- ]to[- ][a-z]+|goal\s+of\s+\d+\s*(min|hour|hr))",
    re.IGNORECASE,
)
CONTRA_RE = re.compile(
    r"(contraindicat|should\s+not\s+be\s+(given|used|administered)|avoid\s+\w+|not\s+recommended)",
    re.IGNORECASE,
)
SYSREVIEW_RE = re.compile(
    r"(systematic\s+review|evidence\s+synthesis|literature\s+search\s+was|cochrane)",
    re.IGNORECASE,
)
GRADE_RE = re.compile(r"\bGRADE\b")
CLASS_LOE_RE = re.compile(r"\bClass\s+(I|II|III|IIa|IIb)\b", re.IGNORECASE)
LOE_RE = re.compile(r"\bLevel\s+of\s+Evidence\b", re.IGNORECASE)


def read_source(path: Path) -> str:
    """Read a local HTML / text / PDF-converted-to-text file into plain text."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    # Strip simple HTML tags if present.
    if "<html" in raw.lower() or "<body" in raw.lower() or "<p>" in raw.lower():
        raw = re.sub(r"<script.*?</script>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<style.*?</style>", " ", raw, flags=re.DOTALL | re.IGNORECASE)
        raw = re.sub(r"<[^>]+>", " ", raw)
    return raw


def propose_c1(publisher: str) -> dict:
    """C1: Tier-1 society issuance."""
    up = publisher.upper()
    matched = [tok for tok in TIER_1_SOCIETIES if tok in up]
    return {
        "value": bool(matched),
        "evidence": f"Publisher tokens matched: {matched}"
        if matched
        else f"No Tier-1 token in publisher '{publisher}'",
    }


def propose_c2(text: str, publisher: str) -> dict:
    """C2: Evidence grading system (0/1/2)."""
    up_text = text.upper()
    up_pub = publisher.upper()
    if any(fs in up_text for fs in FORMAL_EVIDENCE_SYSTEMS):
        matched = next(fs for fs in FORMAL_EVIDENCE_SYSTEMS if fs in up_text)
        return {"value": 2, "system": matched, "evidence": f"Found formal system: {matched}"}
    if CLASS_LOE_RE.search(text) or LOE_RE.search(text):
        return {
            "value": 1,
            "system": f"{up_pub} Class/LOE",
            "evidence": "Found Class I/II/III or Level of Evidence markers",
        }
    if any(ss in up_text for ss in SOCIETY_EVIDENCE_SYSTEMS):
        matched = next(ss for ss in SOCIETY_EVIDENCE_SYSTEMS if ss in up_text)
        return {"value": 1, "system": matched, "evidence": f"Matched society system: {matched}"}
    return {"value": 0, "system": None, "evidence": "No grading system detected"}


def propose_c3(text: str) -> dict:
    """C3: Systematic review performed."""
    match = SYSREVIEW_RE.search(text)
    if match:
        start = max(0, match.start() - 80)
        end = min(len(text), match.end() + 80)
        return {"value": True, "evidence": text[start:end].strip()}
    return {"value": False, "evidence": "No systematic-review marker in Methods text"}


def propose_c4(year: int | None) -> dict:
    """C4: Recency — supplied by caller, normalized to 0/1/2."""
    if year is None:
        return {"value": None, "score": 0, "evidence": "year unknown"}
    score = 2 if year >= 2020 else (1 if year >= 2015 else 0)
    return {"value": year, "score": score, "evidence": f"publication_year={year}"}


def propose_c5(text: str) -> dict:
    """C5: DOI presence."""
    match = DOI_RE.search(text)
    if match:
        doi = match.group(0).rstrip(".,;)")
        return {"value": True, "doi": doi, "evidence": f"Matched DOI: {doi}"}
    return {"value": False, "doi": "", "evidence": "No DOI pattern found"}


def propose_c6(graph_id: str, gbd_table: dict) -> dict:
    """C6: GBD burden — direct lookup in our table."""
    mapping = gbd_table.get("graph_id_mapping", {})
    entry = mapping.get(graph_id)
    if entry:
        return {
            "value": entry.get("m10_score", 0),
            "gbd_cause": entry.get("gbd_cause", ""),
            "evidence": f"GBD table hit for {graph_id}",
        }
    return {
        "value": None,
        "gbd_cause": None,
        "evidence": f"graph_id '{graph_id}' absent from GBD table — reviewer must assign",
    }


def propose_c8(text: str) -> dict:
    """C8: Contraindication explicit — count unique contra-phrases."""
    hits = [m.group(0) for m in CONTRA_RE.finditer(text)]
    n = len(hits)
    if n >= 3:
        score = 2
    elif n >= 1:
        score = 1
    else:
        score = 0
    sample = hits[:3]
    return {
        "value": score,
        "hit_count": n,
        "sample_hits": sample,
        "evidence": f"{n} contraindication-like phrases (C8={score})",
    }


def propose_c10(text: str) -> dict:
    """C10: Time constraints explicit — regex count of 'within X min/hr' and deadline phrases."""
    within_hits = list(WITHIN_TIME_RE.finditer(text))
    deadline_hits = list(DEADLINE_PHRASE_RE.finditer(text))
    n = len(within_hits) + len(deadline_hits)
    if n >= 3:
        score = 2
    elif n >= 1:
        score = 1
    else:
        score = 0
    samples = [m.group(0) for m in (within_hits + deadline_hits)[:3]]
    return {
        "value": bool(n),
        "hit_count": n,
        "score": score,
        "sample_hits": samples,
        "evidence": f"{n} time-constraint phrases (C10={score})",
    }


def build_annotation(
    graph_id: str,
    guideline_name: str,
    publisher: str,
    year: int | None,
    source_text: str,
    gbd_table: dict,
) -> dict:
    """Build a full C1-C12 annotation block."""
    c1 = propose_c1(publisher)
    c2 = propose_c2(source_text, publisher)
    c3 = propose_c3(source_text)
    c4 = propose_c4(year)
    c5 = propose_c5(source_text)
    c6 = propose_c6(graph_id, gbd_table)
    c8 = propose_c8(source_text)
    c10 = propose_c10(source_text)

    block = {
        "guideline_name": guideline_name,
        "publisher": publisher,
        "publication_year": year,
        # Axis 1 — Trustworthiness
        "c1_tier1_society": c1["value"],
        "_c1_evidence": c1["evidence"],
        "c2_evidence_system": c2.get("system"),
        "c2_evidence_system_score": c2["value"],
        "_c2_evidence": c2["evidence"],
        "c3_systematic_review": c3["value"],
        "_c3_evidence": c3["evidence"],
        "c4_recency_year": c4["value"],
        "_c4_evidence": c4["evidence"],
        "c5_has_doi": c5["value"],
        "c5_doi": c5.get("doi", ""),
        "_c5_evidence": c5["evidence"],
        # Axis 2 — Clinical Significance
        "c6_gbd_cause": c6.get("gbd_cause"),
        "c6_score": c6["value"] if c6["value"] is not None else 0,
        "_c6_evidence": c6["evidence"],
        "c7_time_to_harm": None,  # TODO reviewer
        "c7_source_text": None,
        "c8_contraindication_explicit": c8["value"],
        "c8_source_text": " / ".join(c8.get("sample_hits", [])),
        "_c8_evidence": c8["evidence"],
        # Axis 3 — Formalizability
        "c9_has_algorithm_figure": None,  # TODO reviewer (PDF figure detection)
        "c9_figure_count": None,
        "c9_score": None,
        "c10_time_constraints_explicit": c10["value"],
        "c10_time_statements_count": c10["hit_count"],
        "c10_source_text": " / ".join(c10.get("sample_hits", [])),
        "c10_score": c10["score"],
        "_c10_evidence": c10["evidence"],
        "c11_sequence_dependency_explicit": None,  # TODO reviewer
        "c11_source_text": None,
        "c12_conditional_branching_explicit": None,  # TODO reviewer
        "c12_source_text": None,
        # Reviewer checklist
        "_reviewer_todo": [
            "c7_time_to_harm (choose: critical/moderate/mild; quote source)",
            "c9_has_algorithm_figure + c9_figure_count + c9_score (inspect PDF figures)",
            "c11_sequence_dependency_explicit + c11_source_text (read for 'X before Y')",
            "c12_conditional_branching_explicit + c12_source_text (read for 'if X then Y')",
        ],
        "_auto_extract_note": (
            "Auto-generated by scripts/cpg_v2_phase2b/auto_extract_c1_c12.py. "
            "8/12 fields proposed from regex+lookup; 4 fields flagged for reviewer."
        ),
    }
    return block


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-file", type=Path, required=True, help="Local HTML/text source file")
    parser.add_argument("--graph-id", type=str, required=True)
    parser.add_argument("--guideline-name", type=str, required=True)
    parser.add_argument("--publisher", type=str, required=True)
    parser.add_argument("--publication-year", type=int, default=None)
    parser.add_argument("--gbd-path", type=Path, default=REPO_ROOT / "data" / "gbd_top30_causes.json")
    parser.add_argument("--output", type=Path, required=True, help="Output JSON path for the annotation block")
    args = parser.parse_args()

    if not args.source_file.exists():
        sys.exit(f"Source file not found: {args.source_file}")

    text = read_source(args.source_file)
    gbd = load_gbd_table(args.gbd_path) if args.gbd_path.exists() else {"graph_id_mapping": {}}

    block = build_annotation(
        graph_id=args.graph_id,
        guideline_name=args.guideline_name,
        publisher=args.publisher,
        year=args.publication_year,
        source_text=text,
        gbd_table=gbd,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps({args.graph_id: block}, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {args.output}")
    auto_fields = sum(
        1
        for k, v in block.items()
        if not k.startswith("_") and k not in {"guideline_name", "publisher", "publication_year"} and v is not None
    )
    print(f"Auto-filled {auto_fields} fields. Reviewer TODO: {len(block['_reviewer_todo'])} fields.")


if __name__ == "__main__":
    main()
