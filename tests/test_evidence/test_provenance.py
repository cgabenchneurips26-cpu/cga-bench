from __future__ import annotations

from cga_bench.semantic_layer.evidence.provenance import (
    QuoteSpan,
    compute_quote_hash,
    extract_quote_span,
    verify_provenance,
)


class TestComputeQuoteHash:
    def test_deterministic(self):
        h1 = compute_quote_hash("test clause text")
        h2 = compute_quote_hash("test clause text")
        assert h1 == h2

    def test_different_text_different_hash(self):
        assert compute_quote_hash("text a") != compute_quote_hash("text b")


class TestVerifyProvenance:
    def test_valid_provenance(self):
        doc = "The patient should receive lactate measurement within 1 hour."
        span = extract_quote_span(doc, "lactate measurement within 1 hour")
        assert span is not None
        assert verify_provenance(doc, span, span["hash"])

    def test_tampered_hash_rejected(self):
        doc = "The patient should receive lactate measurement within 1 hour."
        span = extract_quote_span(doc, "lactate measurement within 1 hour")
        assert span is not None
        assert not verify_provenance(doc, span, "tampered_hash_value")

    def test_out_of_range_span_rejected(self):
        doc = "Short text."
        bad_span: QuoteSpan = {"start": 0, "end": 999, "text": "Short text.", "hash": "x"}
        assert not verify_provenance(doc, bad_span, "x")


class TestExtractQuoteSpan:
    def test_exact_match(self):
        doc = "Order ECG within 10 minutes of arrival."
        span = extract_quote_span(doc, "ECG within 10 minutes")
        assert span is not None
        assert span["text"].lower().strip() == "ecg within 10 minutes"

    def test_fuzzy_match(self):
        doc = "Administer broad-spectrum antibiotics immediately."
        span = extract_quote_span(doc, "broad spectrum antibiotics immediately")
        assert span is not None

    def test_no_match_returns_none(self):
        doc = "Order ECG within 10 minutes."
        result = extract_quote_span(doc, "completely unrelated weather forecast text")
        assert result is None

    def test_empty_inputs(self):
        assert extract_quote_span("", "test") is None
        assert extract_quote_span("test", "") is None
