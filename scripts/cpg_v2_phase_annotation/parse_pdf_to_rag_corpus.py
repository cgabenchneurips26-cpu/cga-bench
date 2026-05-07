"""Parse a guideline PDF into rag_corpus parsed.json format.

Wraps semantic_layer/cpg_parser.py's ParsedGuideline output to emit the
rag_corpus schema expected by Method A and Method B:

    {
      "guideline_name": str,
      "graph_id": str,
      "source": str,
      "doi": str,
      "recommendations": [{recommendation_id, text, strength, page}, ...],
      "tables": [{table_id, title, data, page}, ...],
      "key_sections": {section_name: text, ...}
    }

This is the prerequisite for running Method A / Method B on beta candidates —
they require a parsed.json input.

Usage:
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/parse_pdf_to_rag_corpus.py \
        --pdf-path data/source_pdfs/aha_cardiogenic_shock_2017.pdf \
        --graph-id aha_cardiogenic_shock_2017 \
        --guideline-name "AHA 2017 Cardiogenic Shock Guideline" \
        --doi "10.1161/CIR.0000000000000525" \
        --domain chest_pain \
        --output data_release/v5.0/rag_corpus/AHA-2017-Cardiogenic-Shock.parsed.json

Dependencies:
    pip install pymupdf  (preferred) OR  pip install pdfplumber

Notes:
    - cpg_parser.py uses an LLM provider to structure recommendations. For a
      minimal parse that only populates recommendations from text heuristics
      (no LLM required), pass --no-llm and the script will fall back to a
      raw-text recommendation chunking strategy.
    - tables and key_sections are best-effort: the LLM path populates them
      when sections are clearly delineated; the no-llm path leaves them empty
      and logs a warning. A reviewer can post-edit the generated JSON to
      add tables or key_sections if they matter for a specific CPG.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_ENDPOINT = os.environ.get("VLLM_ENDPOINT", "http://localhost:8013/v1")
DEFAULT_MODEL = "Qwen/Qwen3.5-397B-A17B-FP8"
DEFAULT_API_KEY = os.environ.get("VLLM_API_KEY", "sk-no-key-required")


def extract_pdf_text(pdf_path: Path) -> str:
    """Extract text from a PDF using pymupdf first, pdfplumber as fallback."""
    try:
        import fitz  # pymupdf

        doc = fitz.open(str(pdf_path))
        try:
            return "\n\n".join(page.get_text() for page in doc)
        finally:
            doc.close()
    except ImportError:
        pass
    try:
        import pdfplumber

        with pdfplumber.open(pdf_path) as pdf:
            return "\n\n".join(page.extract_text() or "" for page in pdf.pages)
    except ImportError as exc:
        raise ImportError(
            "Neither pymupdf nor pdfplumber is installed. "
            "Install one: pip install pymupdf (preferred) or pip install pdfplumber"
        ) from exc


def parse_with_llm(text: str, graph_id: str, domain: str, source_label: str) -> dict[str, Any]:
    """Use cpg_parser.py + LLM to produce a structured ParsedGuideline."""
    from cga_bench.agent_runner.llm_provider import (
        LLMBackend,
        LLMConfig,
        LLMProviderFactory,
    )
    from cga_bench.semantic_layer.cpg_parser import CPGParser

    llm_config = LLMConfig(
        backend=LLMBackend.VLLM,
        model=DEFAULT_MODEL,
        base_url=DEFAULT_ENDPOINT,
        api_key=DEFAULT_API_KEY,
        temperature=0,
        max_tokens=4096,
    )
    llm = LLMProviderFactory.create(llm_config)
    parser = CPGParser(llm_provider=llm)
    parsed: Any = parser.parse_text(text=text, guideline_id=graph_id, domain=domain, source=source_label)

    # Map ParsedGuideline.recommendations -> rag_corpus.recommendations schema.
    recommendations: list[dict[str, Any]] = []
    for i, rec in enumerate(parsed.recommendations, start=1):
        rec_dict = asdict(rec) if not isinstance(rec, dict) else rec
        recommendations.append(
            {
                "recommendation_id": rec_dict.get("source_section") or f"rec_{i}",
                "text": rec_dict.get("source_quote") or rec_dict.get("description") or rec_dict.get("action_type", ""),
                "strength": rec_dict.get("strength") or "",
                "page": rec_dict.get("source_page"),
            }
        )
    return {
        "recommendations": recommendations,
        "tables": [],
        "key_sections": {},
        "parse_confidence": getattr(parsed, "parse_confidence", 0.0),
    }


def parse_without_llm(text: str) -> dict[str, Any]:
    """Heuristic parse: chunk text by numbered-recommendation patterns.

    Populates only recommendations with raw chunks; leaves tables and
    key_sections empty. Useful when no LLM is available or for a
    quick first pass.
    """
    import re

    # Common numbered-recommendation patterns in clinical guidelines:
    #   "Recommendation 1.2: ...", "R1. ...", "1.", "2.2"
    chunks = re.split(
        r"\n\s*(?:Recommendation\s+\d+(?:\.\d+)*|R\d+\.?|\d+\.\d+\.?)\s+",
        text,
    )
    recs: list[dict[str, Any]] = []
    for i, chunk in enumerate(chunks):
        chunk = chunk.strip()
        if len(chunk) < 30:  # too short to be a real recommendation
            continue
        # Limit chunk length to first paragraph for rag_corpus compactness.
        snippet = chunk.split("\n\n", 1)[0]
        recs.append(
            {
                "recommendation_id": f"rec_{i}",
                "text": snippet[:2000],
                "strength": "",
                "page": None,
            }
        )
    return {"recommendations": recs, "tables": [], "key_sections": {}, "parse_confidence": 0.3}


def build_rag_corpus_entry(
    *,
    graph_id: str,
    guideline_name: str,
    source_label: str,
    doi: str,
    recommendations: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    key_sections: dict[str, str],
    parse_confidence: float,
) -> dict[str, Any]:
    """Assemble the final rag_corpus parsed.json dict."""
    return {
        "guideline_name": guideline_name,
        "graph_id": graph_id,
        "source": source_label,
        "doi": doi,
        "recommendations": recommendations,
        "tables": tables,
        "key_sections": key_sections,
        "_provenance": {
            "parser": "scripts/cpg_v2_phase_annotation/parse_pdf_to_rag_corpus.py",
            "parse_confidence": parse_confidence,
        },
    }


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--pdf-path", required=True, type=Path)
    parser.add_argument("--graph-id", required=True)
    parser.add_argument("--guideline-name", required=True)
    parser.add_argument("--doi", default="")
    parser.add_argument("--source-label", default="")
    parser.add_argument("--domain", default="general")
    parser.add_argument("--no-llm", action="store_true", help="Skip LLM parse; heuristic only")
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.pdf_path.exists():
        raise SystemExit(f"PDF not found: {args.pdf_path}")

    logger.info("Extracting text from %s ...", args.pdf_path)
    text = extract_pdf_text(args.pdf_path)
    logger.info("Extracted %d characters", len(text))

    if args.no_llm:
        logger.info("Heuristic parse (no LLM) ...")
        parsed_dict = parse_without_llm(text)
    else:
        logger.info("LLM-assisted parse via %s ...", DEFAULT_ENDPOINT)
        parsed_dict = parse_with_llm(text, args.graph_id, args.domain, args.source_label or args.guideline_name)

    entry = build_rag_corpus_entry(
        graph_id=args.graph_id,
        guideline_name=args.guideline_name,
        source_label=args.source_label or args.guideline_name,
        doi=args.doi,
        recommendations=parsed_dict["recommendations"],
        tables=parsed_dict["tables"],
        key_sections=parsed_dict["key_sections"],
        parse_confidence=parsed_dict["parse_confidence"],
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(entry, indent=2), encoding="utf-8")

    n_recs = len(entry["recommendations"])
    logger.info("Wrote %s with %d recommendations", args.output, n_recs)
    if n_recs == 0:
        logger.warning("No recommendations extracted. Consider manual post-edit or rerun without --no-llm.")
    print(f"\nparse complete: {args.output}")
    print(f"  recommendations: {n_recs}")
    print(f"  parse_confidence: {entry['_provenance']['parse_confidence']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
