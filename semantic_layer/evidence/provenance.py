from __future__ import annotations

import difflib
import hashlib
from dataclasses import dataclass
from typing import TypedDict


class QuoteSpan(TypedDict):
    start: int
    end: int
    text: str
    hash: str


@dataclass
class ProvenanceRecord:
    clause_id: str
    quote_span: QuoteSpan
    source_doc: str
    verified: bool


def compute_quote_hash(text: str) -> str:
    """SHA-256 hex digest of normalized quote text."""
    normalized = text.strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def verify_provenance(doc_text: str, span: QuoteSpan, expected_hash: str) -> bool:
    """Verify quote span against document text.

    1. Extract substring at span offsets from doc_text
    2. Compute hash of extracted text
    3. Compare with expected_hash
    4. Also verify span.text matches extracted text

    Returns False if:
    - span offsets out of range
    - extracted hash != expected_hash
    - span.text doesn't match extracted text
    """
    start, end = span["start"], span["end"]
    if start < 0 or end > len(doc_text) or start >= end:
        return False
    extracted = doc_text[start:end]
    actual_hash = compute_quote_hash(extracted)
    if actual_hash != expected_hash:
        return False
    if span["text"].strip().lower() != extracted.strip().lower():
        return False
    return True


def extract_quote_span(doc_text: str, clause_text: str) -> QuoteSpan | None:
    """Find clause_text in doc_text and return QuoteSpan.

    Strategy:
    1. Try exact substring match first
    2. If no exact match, try fuzzy match (difflib.SequenceMatcher >= 0.85)
    3. Return None if no match found

    For fuzzy matching:
    - Slide a window of len(clause_text) ± 20% over doc_text
    - Find the best matching window
    - Accept if ratio >= 0.85
    """
    if not doc_text or not clause_text:
        return None

    normalized_doc = doc_text.lower()
    normalized_clause = clause_text.strip().lower()

    idx = normalized_doc.find(normalized_clause)
    if idx >= 0:
        matched_text = doc_text[idx : idx + len(clause_text.strip())]
        return {
            "start": idx,
            "end": idx + len(matched_text),
            "text": matched_text,
            "hash": compute_quote_hash(matched_text),
        }

    clause_len = len(normalized_clause)
    if clause_len == 0:
        return None

    window_min = max(1, int(clause_len * 0.8))
    window_max = min(len(normalized_doc), int(clause_len * 1.2))

    best_ratio = 0.0
    best_start = -1
    best_end = -1

    step = max(1, clause_len // 10)

    for win_size in range(
        window_min,
        window_max + 1,
        max(1, (window_max - window_min) // 3),
    ):
        for start in range(0, len(normalized_doc) - win_size + 1, step):
            end = start + win_size
            window = normalized_doc[start:end]
            ratio = difflib.SequenceMatcher(None, normalized_clause, window).ratio()
            if ratio > best_ratio:
                best_ratio = ratio
                best_start = start
                best_end = end

    if best_ratio >= 0.85 and best_start >= 0:
        matched_text = doc_text[best_start:best_end]
        return {
            "start": best_start,
            "end": best_end,
            "text": matched_text,
            "hash": compute_quote_hash(matched_text),
        }

    return None
