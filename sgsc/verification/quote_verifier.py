"""3-tier source quote verification for RecommendationAtoms.

Reuses the matching logic from ``ground_graph_quotes.py``:

1. **VERIFIED** — exact substring match (normalized whitespace)
2. **GROUNDED** — keyword overlap >= threshold, best span extracted
3. **UNGROUNDED** — no match above threshold
"""

from __future__ import annotations

import re

from pydantic import BaseModel, ConfigDict, Field
from sgsc.schemas.atom import RecommendationAtom

# ------------------------------------------------------------------
# Text helpers (ported from ground_graph_quotes.py)
# ------------------------------------------------------------------

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
    """Find the document substring that best covers *query* keywords.

    Sliding-window approach over sentences; returns the window
    whose token overlap with *query* is highest, capped at *max_len* chars.
    """
    query_tokens = _tokenize(query)
    if not query_tokens:
        return document[:max_len]

    sentences = re.split(r"(?<=[.!?])\s+", document)
    if not sentences:
        return document[:max_len]

    best_score = -1.0
    best_span = ""

    for window_size in (1, 2, 3):
        for i in range(len(sentences)):
            window = " ".join(sentences[i : i + window_size])
            if len(window) > max_len:
                window = window[:max_len]
            window_tokens = _tokenize(window)
            if not window_tokens:
                continue
            overlap = len(query_tokens & window_tokens)
            score = overlap / len(query_tokens)
            if score > best_score:
                best_score = score
                best_span = window

    return best_span.strip() if best_span else document[:max_len]


# ------------------------------------------------------------------
# Result model
# ------------------------------------------------------------------


class QuoteVerificationResult(BaseModel):
    """Result of verifying one atom's source quote."""

    model_config = ConfigDict(frozen=True)

    atom_id: str
    status: str = Field(..., description="VERIFIED | GROUNDED | UNGROUNDED")
    match_score: float = Field(0.0, ge=0.0, le=1.0)
    matched_rec_id: str = ""
    verbatim_quote: str | None = Field(None, description="Replacement verbatim text when GROUNDED")


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------

DEFAULT_GROUNDING_THRESHOLD = 0.4


def verify_atom_quote(
    atom: RecommendationAtom,
    corpus_full_text: str,
    recommendations: list[dict[str, str | int | None]],
    threshold: float = DEFAULT_GROUNDING_THRESHOLD,
) -> QuoteVerificationResult:
    """Verify a single atom's ``source.quote`` against corpus text.

    Args:
        atom: The atom whose source quote to verify.
        corpus_full_text: Concatenated full text of the RAG corpus.
        recommendations: List of recommendation dicts with ``text`` keys.
        threshold: Minimum keyword-overlap score for GROUNDED status.

    Returns:
        QuoteVerificationResult with status and optional replacement quote.
    """
    quote = atom.source.quote.strip()
    if not quote:
        return QuoteVerificationResult(atom_id=atom.atom_id, status="UNGROUNDED")

    # --- Tier 1: exact substring (normalized) ---
    norm_quote = _normalize(quote)
    norm_corpus = _normalize(corpus_full_text)

    if norm_quote in norm_corpus:
        rec_id = ""
        for rec in recommendations:
            rec_text = _normalize(str(rec.get("text", "")))
            if norm_quote in rec_text:
                rec_id = str(rec.get("recommendation_id", ""))
                break
        return QuoteVerificationResult(
            atom_id=atom.atom_id,
            status="VERIFIED",
            match_score=1.0,
            matched_rec_id=rec_id,
        )

    # --- Tier 2: keyword overlap ---
    quote_tokens = _tokenize(quote)
    if not quote_tokens:
        return QuoteVerificationResult(atom_id=atom.atom_id, status="UNGROUNDED")

    best_score = 0.0
    best_rec: dict[str, str | int | None] = {}

    for rec in recommendations:
        rec_text = str(rec.get("text", ""))
        if len(rec_text) < 20:
            continue
        rec_tokens = _tokenize(rec_text)
        if not rec_tokens:
            continue
        overlap = len(quote_tokens & rec_tokens) / len(quote_tokens)
        if overlap > best_score:
            best_score = overlap
            best_rec = rec

    if best_score >= threshold and best_rec:
        verbatim = extract_best_span(quote, str(best_rec.get("text", "")), max_len=300)
        return QuoteVerificationResult(
            atom_id=atom.atom_id,
            status="GROUNDED",
            match_score=round(best_score, 3),
            matched_rec_id=str(best_rec.get("recommendation_id", "")),
            verbatim_quote=verbatim,
        )

    # --- Tier 3: ungrounded ---
    return QuoteVerificationResult(
        atom_id=atom.atom_id,
        status="UNGROUNDED",
        match_score=round(best_score, 3),
    )


def verify_atom_quotes(
    atoms: list[RecommendationAtom],
    corpus_full_text: str,
    recommendations: list[dict[str, str | int | None]],
    threshold: float = DEFAULT_GROUNDING_THRESHOLD,
) -> list[QuoteVerificationResult]:
    """Verify all atoms' source quotes against corpus text."""
    return [verify_atom_quote(atom, corpus_full_text, recommendations, threshold) for atom in atoms]
