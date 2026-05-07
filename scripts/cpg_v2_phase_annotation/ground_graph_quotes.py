"""Option A: Ground existing graph source_quotes against rag_corpus.

For each node in an auto-generated graph YAML, verify its source_quote
against the corresponding rag_corpus parsed.json.  Replace developer-
paraphrased quotes with verbatim text from the corpus, and fill
source_page from the recommendation's page field.

Three-tier matching:
  1. Exact substring  → VERIFIED (quote already verbatim)
  2. Keyword overlap   → GROUNDED (replace with best verbatim span)
  3. No match          → UNGROUNDED (flagged for manual review)

Usage:
    # Single graph
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/ground_graph_quotes.py \\
        --graph cpg_model/graphs/auto/ats_esicm_sccm_ards_2023.yaml \\
        --corpus data_release/v5.0/rag_corpus/ATS-ESICM-SCCM-2023-ARDS.parsed.json

    # Batch (all auto graphs)
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/ground_graph_quotes.py \\
        --graphs-dir cpg_model/graphs/auto/ \\
        --corpus-dir data_release/v5.0/rag_corpus/ \\
        --report reports/grounding_report.json
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import logging
from pathlib import Path
import re
from typing import Any

import yaml

logger = logging.getLogger(__name__)

RAG_CORPUS_DIR = Path("data_release/v5.0/rag_corpus")

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass
class GroundingResult:
    """Result of grounding a single node's source_quote."""

    status: str  # VERIFIED | GROUNDED | GROUNDED_SECTION | GROUNDED_TABLE | UNGROUNDED | SKIPPED
    source_quote: str = ""
    source_page: int | str | None = None
    match_method: str = ""
    match_score: float = 0.0
    matched_rec_id: str = ""
    match_source: str = ""  # "recommendation" | "key_section" | "table" | ""
    old_quote: str = ""


@dataclass
class GroundingReport:
    """Aggregate report for an entire graph."""

    graph_id: str = ""
    total_nodes: int = 0
    verified: int = 0
    grounded: int = 0
    ungrounded: int = 0
    skipped: int = 0
    pages_filled: int = 0
    nodes: dict[str, dict[str, Any]] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

_STOP_WORDS = frozenset(
    [
        "a",
        "an",
        "the",
        "is",
        "are",
        "was",
        "were",
        "be",
        "been",
        "being",
        "have",
        "has",
        "had",
        "do",
        "does",
        "did",
        "will",
        "would",
        "shall",
        "should",
        "may",
        "might",
        "can",
        "could",
        "of",
        "in",
        "on",
        "at",
        "to",
        "for",
        "with",
        "by",
        "from",
        "and",
        "or",
        "but",
        "not",
        "no",
        "nor",
        "so",
        "yet",
        "if",
        "then",
        "than",
        "that",
        "this",
        "it",
        "its",
        "as",
    ]
)


def _tokenize(text: str) -> set[str]:
    """Lowercase token set, filtering stop words and short tokens."""
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    return {t for t in tokens if t not in _STOP_WORDS and len(t) > 2}


def _normalize(text: str) -> str:
    """Collapse whitespace for forgiving substring matching."""
    return re.sub(r"\s+", " ", text).strip().lower()


def extract_best_span(query: str, document: str, max_len: int = 300) -> str:
    """Find the substring in *document* that best covers *query* keywords.

    Uses a sliding-window approach over sentences.  Returns the window
    whose token overlap with *query* is highest, capped at *max_len* chars.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return document[:max_len]

    # Split document into sentences (rough)
    sentences = re.split(r"(?<=[.!?])\s+", document)
    if not sentences:
        return document[:max_len]

    best_score = -1.0
    best_span = ""

    # Sliding window of 1-3 sentences
    for window_size in (1, 2, 3):
        for i in range(len(sentences)):
            window = " ".join(sentences[i : i + window_size])
            if len(window) > max_len:
                window = window[:max_len]
            window_tokens = _tokenize(window)
            if not window_tokens:
                continue
            overlap = len(query_tokens & window_tokens)
            # Normalize by query size to prefer high coverage
            score = overlap / len(query_tokens)
            if score > best_score:
                best_score = score
                best_span = window

    return best_span.strip() if best_span else document[:max_len]


# ---------------------------------------------------------------------------
# Corpus loading
# ---------------------------------------------------------------------------


def load_corpus(path: Path) -> dict[str, Any]:
    """Load a rag_corpus parsed.json file."""
    return json.loads(path.read_text(encoding="utf-8"))


def find_corpus_for_graph(graph_id: str, corpus_dir: Path | None = None) -> Path | None:
    """Find the rag_corpus parsed.json for a graph_id.

    Reuses the same strategy as verify_beta_substring.py:
      1. Read graph_id field from each parsed.json
      2. Fallback: substring match on filename
    """
    search_dir = corpus_dir or RAG_CORPUS_DIR
    if not search_dir.exists():
        return None

    # Primary: match graph_id field
    for p in search_dir.glob("*.parsed.json"):
        try:
            content = json.loads(p.read_text(encoding="utf-8"))
            if content.get("graph_id") == graph_id:
                return p
        except (OSError, json.JSONDecodeError):
            continue

    # Fallback: token-based filename match with ratio guard
    gid_tokens = set(graph_id.replace("_", " ").lower().split())
    best_path: Path | None = None
    best_overlap = 0
    best_ratio = 0.0
    for p in search_dir.glob("*.parsed.json"):
        fname_tokens = set(p.stem.replace("-", " ").replace(".", " ").lower().split())
        overlap = len(gid_tokens & fname_tokens)
        ratio = overlap / max(len(gid_tokens), 1)
        if overlap > best_overlap or (overlap == best_overlap and ratio > best_ratio):
            best_overlap = overlap
            best_ratio = ratio
            best_path = p

    # Require meaningful overlap to avoid false positives.
    # >=3 tokens is always safe; 2 tokens only if ratio >= 0.5
    # (prevents "aha+acc" matching unrelated AHA-ACC guideline).
    if best_overlap >= 3:
        return best_path
    if best_overlap >= 2 and best_ratio > 0.5:
        return best_path
    return None


# ---------------------------------------------------------------------------
# Core grounding logic
# ---------------------------------------------------------------------------


def ground_node_quote(
    node_id: str,
    node: dict[str, Any],
    recommendations: list[dict[str, Any]],
    corpus_full_text: str,
    key_sections: dict[str, Any] | None = None,
    tables: list[dict[str, Any]] | None = None,
) -> GroundingResult:
    """Ground a single node's source_quote against corpus text.

    Search priority:
      1. Exact substring in full corpus text (VERIFIED)
      2. Keyword overlap against recommendations (GROUNDED)
      3. Keyword overlap against key_sections (GROUNDED_SECTION)
      4. Keyword overlap against tables (GROUNDED_TABLE)
      5. UNGROUNDED
    """
    existing_quote = (node.get("source_quote") or "").strip()
    if not existing_quote:
        return GroundingResult(status="SKIPPED", old_quote="")

    key_sections = key_sections or {}
    tables = tables or []

    # --- Tier 1: exact substring (normalized) ---
    norm_quote = _normalize(existing_quote)
    norm_corpus = _normalize(corpus_full_text)

    if norm_quote in norm_corpus:
        # Find which recommendation contains this quote (for page number)
        page = None
        rec_id = ""
        match_source = ""
        for rec in recommendations:
            rec_text = _normalize(rec.get("text", ""))
            if norm_quote in rec_text:
                page = rec.get("page")
                rec_id = rec.get("recommendation_id", "")
                match_source = "recommendation"
                break
        if not match_source:
            # Check key_sections
            for sec_name, sec_text in key_sections.items():
                if norm_quote in _normalize(str(sec_text)):
                    match_source = "key_section"
                    break
        if not match_source:
            # Check tables
            for tbl in tables:
                tbl_text = str(tbl.get("data", tbl.get("text", "")))
                if norm_quote in _normalize(tbl_text):
                    match_source = "table"
                    break
        if not match_source:
            match_source = "corpus_text"

        return GroundingResult(
            status="VERIFIED",
            source_quote=existing_quote,
            source_page=page,
            match_method="exact_substring",
            match_score=1.0,
            matched_rec_id=rec_id,
            match_source=match_source,
            old_quote=existing_quote,
        )

    # --- Tier 2: keyword overlap scoring against recommendations ---
    quote_tokens = _tokenize(existing_quote)
    if not quote_tokens:
        return GroundingResult(status="UNGROUNDED", source_quote=existing_quote, old_quote=existing_quote)

    scored: list[tuple[float, dict[str, Any]]] = []
    for rec in recommendations:
        rec_text = rec.get("text", "")
        if not rec_text or len(rec_text) < 20:
            continue
        rec_tokens = _tokenize(rec_text)
        if not rec_tokens:
            continue
        overlap = len(quote_tokens & rec_tokens) / len(quote_tokens)
        scored.append((overlap, rec))

    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        best_score, best_rec = scored[0]

        if best_score >= 0.4:
            verbatim = extract_best_span(existing_quote, best_rec["text"], max_len=300)
            return GroundingResult(
                status="GROUNDED",
                source_quote=verbatim,
                source_page=best_rec.get("page"),
                match_method="keyword_overlap",
                match_score=round(best_score, 3),
                matched_rec_id=best_rec.get("recommendation_id", ""),
                match_source="recommendation",
                old_quote=existing_quote,
            )

    # --- Tier 2b: keyword overlap against key_sections ---
    best_sec_score = 0.0
    best_sec_name = ""
    best_sec_text = ""
    for sec_name, sec_text in key_sections.items():
        sec_str = str(sec_text)
        if len(sec_str) < 20:
            continue
        sec_tokens = _tokenize(sec_str)
        if not sec_tokens:
            continue
        overlap = len(quote_tokens & sec_tokens) / len(quote_tokens)
        if overlap > best_sec_score:
            best_sec_score = overlap
            best_sec_name = sec_name
            best_sec_text = sec_str

    if best_sec_score >= 0.4:
        verbatim = extract_best_span(existing_quote, best_sec_text, max_len=300)
        return GroundingResult(
            status="GROUNDED_SECTION",
            source_quote=verbatim,
            match_method="keyword_overlap_section",
            match_score=round(best_sec_score, 3),
            matched_rec_id=best_sec_name,
            match_source="key_section",
            old_quote=existing_quote,
        )

    # --- Tier 2c: keyword overlap against tables ---
    best_tbl_score = 0.0
    best_tbl_text = ""
    best_tbl_idx = -1
    for idx, tbl in enumerate(tables):
        tbl_text = str(tbl.get("data", tbl.get("text", "")))
        if len(tbl_text) < 20:
            continue
        tbl_tokens = _tokenize(tbl_text)
        if not tbl_tokens:
            continue
        overlap = len(quote_tokens & tbl_tokens) / len(quote_tokens)
        if overlap > best_tbl_score:
            best_tbl_score = overlap
            best_tbl_text = tbl_text
            best_tbl_idx = idx

    if best_tbl_score >= 0.4:
        verbatim = extract_best_span(existing_quote, best_tbl_text, max_len=300)
        return GroundingResult(
            status="GROUNDED_TABLE",
            source_quote=verbatim,
            match_method="keyword_overlap_table",
            match_score=round(best_tbl_score, 3),
            matched_rec_id=f"table_{best_tbl_idx}",
            match_source="table",
            old_quote=existing_quote,
        )

    # --- Tier 3: ungrounded ---
    rec_best = round(scored[0][0], 3) if scored else 0.0
    all_best = max(rec_best, round(best_sec_score, 3), round(best_tbl_score, 3))
    return GroundingResult(
        status="UNGROUNDED",
        source_quote=existing_quote,
        match_score=all_best,
        old_quote=existing_quote,
    )


def ground_all_nodes(
    graph: dict[str, Any],
    corpus: dict[str, Any],
) -> GroundingReport:
    """Ground all nodes in a graph against a corpus."""
    graph_id = graph.get("graph_id", "unknown")
    nodes = graph.get("nodes", {})
    recommendations = corpus.get("recommendations", []) or []

    # Build full corpus text for substring matching
    parts: list[str] = []
    for rec in recommendations:
        if isinstance(rec, dict):
            parts.append(str(rec.get("text", "")))
    key_sections = corpus.get("key_sections", {}) or {}
    if isinstance(key_sections, dict):
        for v in key_sections.values():
            parts.append(str(v))
    tables = corpus.get("tables", []) or []
    for tbl in tables:
        if isinstance(tbl, dict):
            parts.append(str(tbl.get("data", tbl.get("text", ""))))
    corpus_full_text = "\n".join(parts)

    report = GroundingReport(graph_id=graph_id, total_nodes=len(nodes))

    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        result = ground_node_quote(
            node_id,
            node,
            recommendations,
            corpus_full_text,
            key_sections=key_sections if isinstance(key_sections, dict) else {},
            tables=tables,
        )

        if result.status == "VERIFIED":
            report.verified += 1
        elif result.status in ("GROUNDED", "GROUNDED_SECTION", "GROUNDED_TABLE"):
            report.grounded += 1
        elif result.status == "UNGROUNDED":
            report.ungrounded += 1
        else:
            report.skipped += 1

        if result.source_page is not None:
            report.pages_filled += 1

        report.nodes[node_id] = {
            "status": result.status,
            "old_quote": result.old_quote,
            "new_quote": result.source_quote,
            "source_page": result.source_page,
            "match_method": result.match_method,
            "match_score": result.match_score,
            "matched_rec_id": result.matched_rec_id,
            "match_source": result.match_source,
        }

    return report


# ---------------------------------------------------------------------------
# Graph update
# ---------------------------------------------------------------------------


def apply_grounding(graph: dict[str, Any], report: GroundingReport) -> dict[str, Any]:
    """Apply grounding results to a graph, updating source_quote and source_page."""
    nodes = graph.get("nodes", {})
    for node_id, info in report.nodes.items():
        node = nodes.get(node_id)
        if node is None or not isinstance(node, dict):
            continue

        status = info["status"]
        if status in ("VERIFIED", "GROUNDED"):
            node["source_quote"] = info["new_quote"]
            if info["source_page"] is not None:
                node["source_page"] = info["source_page"]
            node["_quote_verification"] = {
                "status": status,
                "method": info["match_method"],
                "score": info["match_score"],
            }
        elif status == "UNGROUNDED":
            node["_quote_verification"] = {
                "status": "UNGROUNDED",
                "score": info["match_score"],
            }

    return graph


def write_grounded_graph(graph: dict[str, Any], output_path: Path) -> None:
    """Write grounded graph to YAML."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(
            graph,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )
    logger.info("Written grounded graph: %s", output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _process_single(
    graph_path: Path,
    corpus_path: Path,
    output_path: Path | None,
    dry_run: bool,
) -> GroundingReport:
    """Process a single graph."""
    graph = yaml.safe_load(graph_path.read_text(encoding="utf-8"))
    corpus = load_corpus(corpus_path)
    report = ground_all_nodes(graph, corpus)

    total = report.verified + report.grounded + report.ungrounded
    logger.info(
        "%s: %d/%d verified, %d/%d grounded, %d ungrounded, %d pages filled",
        report.graph_id,
        report.verified,
        total,
        report.grounded,
        total,
        report.ungrounded,
        report.pages_filled,
    )

    if not dry_run:
        updated = apply_grounding(graph, report)
        out = output_path or graph_path
        write_grounded_graph(updated, out)

    return report


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--graph", type=Path, help="Path to a single graph YAML")
    group.add_argument("--graphs-dir", type=Path, help="Directory of graph YAMLs (batch mode)")
    parser.add_argument("--corpus", type=Path, help="Path to rag_corpus parsed.json (single mode)")
    parser.add_argument("--corpus-dir", type=Path, default=RAG_CORPUS_DIR, help="Directory of rag_corpus files (batch)")
    parser.add_argument("--output", type=Path, help="Output path (single mode; default: overwrite input)")
    parser.add_argument("--report", type=Path, help="Write JSON report (batch mode)")
    parser.add_argument("--dry-run", action="store_true", help="Report only, don't modify graphs")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    all_reports: dict[str, dict[str, Any]] = {}

    if args.graph:
        # Single mode
        corpus_path = args.corpus
        if corpus_path is None:
            # Auto-discover corpus
            graph_data = yaml.safe_load(args.graph.read_text(encoding="utf-8"))
            gid = graph_data.get("graph_id", args.graph.stem)
            corpus_path = find_corpus_for_graph(gid, args.corpus_dir)
            if corpus_path is None:
                logger.error("No rag_corpus found for graph_id=%s", gid)
                return 1
            logger.info("Auto-discovered corpus: %s", corpus_path)

        report = _process_single(args.graph, corpus_path, args.output, args.dry_run)
        all_reports[report.graph_id] = {
            "total_nodes": report.total_nodes,
            "verified": report.verified,
            "grounded": report.grounded,
            "ungrounded": report.ungrounded,
            "skipped": report.skipped,
            "pages_filled": report.pages_filled,
            "nodes": report.nodes,
        }
    else:
        # Batch mode
        graph_files = sorted(args.graphs_dir.glob("*.yaml"))
        if not graph_files:
            logger.error("No YAML files found in %s", args.graphs_dir)
            return 1

        for gf in graph_files:
            graph_data = yaml.safe_load(gf.read_text(encoding="utf-8"))
            gid = graph_data.get("graph_id", gf.stem)
            corpus_path = find_corpus_for_graph(gid, args.corpus_dir)
            if corpus_path is None:
                logger.warning("No corpus for %s — skipping", gid)
                continue

            report = _process_single(gf, corpus_path, None, args.dry_run)
            all_reports[report.graph_id] = {
                "total_nodes": report.total_nodes,
                "verified": report.verified,
                "grounded": report.grounded,
                "ungrounded": report.ungrounded,
                "skipped": report.skipped,
                "pages_filled": report.pages_filled,
                "nodes": report.nodes,
            }

    # Summary
    total_v = sum(r["verified"] for r in all_reports.values())
    total_g = sum(r["grounded"] for r in all_reports.values())
    total_u = sum(r["ungrounded"] for r in all_reports.values())
    total_p = sum(r["pages_filled"] for r in all_reports.values())
    total_n = sum(r["total_nodes"] for r in all_reports.values())

    print(f"\n=== Grounding Report ({len(all_reports)} graphs, {total_n} nodes) ===")
    print(f"  VERIFIED:   {total_v}")
    print(f"  GROUNDED:   {total_g}")
    print(f"  UNGROUNDED: {total_u}")
    print(f"  Pages filled: {total_p}")

    if args.report:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(all_reports, indent=2, ensure_ascii=False), encoding="utf-8")
        print(f"  Report: {args.report}")

    return 1 if total_u > 0 else 0


if __name__ == "__main__":
    raise SystemExit(main())
