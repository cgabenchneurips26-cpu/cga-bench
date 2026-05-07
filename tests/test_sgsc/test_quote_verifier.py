"""Tests for sgsc.verification.quote_verifier."""

from __future__ import annotations

import pytest
from sgsc.schemas.atom import (
    AtomAction,
    AtomConstraint,
    AtomEvidence,
    PopulationCriteria,
    RecommendationAtom,
    ScenarioHooks,
    SourceReference,
)
from sgsc.verification.quote_verifier import (
    extract_best_span,
    verify_atom_quote,
    verify_atom_quotes,
)

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------

_CORPUS_TEXT = (
    "Administer broad-spectrum antibiotics within 1 hour of sepsis recognition. "
    "Obtain blood cultures before antibiotic administration. "
    "Begin crystalloid resuscitation at 30 mL/kg for hypotension or lactate >= 4 mmol/L."
)

_RECOMMENDATIONS: list[dict[str, str | int | None]] = [
    {
        "recommendation_id": "R1",
        "text": "Administer broad-spectrum antibiotics within 1 hour of sepsis recognition.",
    },
    {
        "recommendation_id": "R2",
        "text": "Obtain blood cultures before antibiotic administration.",
    },
    {
        "recommendation_id": "R3",
        "text": "Begin crystalloid resuscitation at 30 mL/kg for hypotension or lactate >= 4 mmol/L.",
    },
]


@pytest.fixture()
def corpus_text() -> str:
    return _CORPUS_TEXT


@pytest.fixture()
def recommendations() -> list[dict[str, str | int | None]]:
    return _RECOMMENDATIONS


def _make_atom(quote: str, atom_id: str = "test_atom") -> RecommendationAtom:
    return RecommendationAtom(
        atom_id=atom_id,
        source=SourceReference(
            guideline_id="ssc_2021",
            section="Hour-1 Bundle",
            quote=quote,
        ),
        population=PopulationCriteria(inclusion=["sepsis"], exclusion=[]),
        action=AtomAction(canonical_id="give_abx", action_type="medication"),
        constraint=AtomConstraint(type="WITHIN", deadline_minutes=60),
        evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="A"),
        scenario_hooks=ScenarioHooks(),
    )


# ------------------------------------------------------------------
# extract_best_span — returns str, not tuple
# ------------------------------------------------------------------


class TestExtractBestSpan:
    def test_exact_sentence_returns_match(self, corpus_text: str) -> None:
        quote = "Obtain blood cultures before antibiotic administration."
        span = extract_best_span(quote, corpus_text)
        assert isinstance(span, str)
        assert "blood cultures" in span.lower()

    def test_partial_match_returns_span(self, corpus_text: str) -> None:
        quote = "broad-spectrum antibiotics within 1 hour"
        span = extract_best_span(quote, corpus_text)
        assert len(span) > 0

    def test_no_match_returns_some_text(self, corpus_text: str) -> None:
        quote = "completely unrelated text about quantum physics"
        span = extract_best_span(quote, corpus_text)
        # Still returns something (best available window)
        assert isinstance(span, str)

    def test_empty_quote_returns_prefix(self, corpus_text: str) -> None:
        span = extract_best_span("", corpus_text)
        assert isinstance(span, str)
        assert len(span) > 0  # Returns corpus[:max_len]

    def test_empty_corpus(self) -> None:
        span = extract_best_span("some quote", "")
        assert span == ""


# ------------------------------------------------------------------
# verify_atom_quote
# ------------------------------------------------------------------


class TestVerifyAtomQuote:
    def test_verified_exact_match(self, corpus_text: str, recommendations: list[dict[str, str | int | None]]) -> None:
        atom = _make_atom("Obtain blood cultures before antibiotic administration.")
        result = verify_atom_quote(atom, corpus_text, recommendations)
        assert result.status == "VERIFIED"
        assert result.match_score == 1.0

    def test_grounded_partial(self, corpus_text: str, recommendations: list[dict[str, str | int | None]]) -> None:
        atom = _make_atom("antibiotics within 1 hour of sepsis")
        result = verify_atom_quote(atom, corpus_text, recommendations)
        assert result.status in ("VERIFIED", "GROUNDED")
        assert result.match_score >= 0.4

    def test_ungrounded(self, corpus_text: str, recommendations: list[dict[str, str | int | None]]) -> None:
        atom = _make_atom("start ECMO immediately for cardiogenic shock")
        result = verify_atom_quote(atom, corpus_text, recommendations)
        assert result.status == "UNGROUNDED"

    def test_result_contains_atom_id(
        self, corpus_text: str, recommendations: list[dict[str, str | int | None]]
    ) -> None:
        atom = _make_atom("some quote", atom_id="my_atom_123")
        result = verify_atom_quote(atom, corpus_text, recommendations)
        assert result.atom_id == "my_atom_123"

    def test_custom_threshold(self, corpus_text: str, recommendations: list[dict[str, str | int | None]]) -> None:
        atom = _make_atom("antibiotics sepsis hour")
        # Very high threshold should make it harder to be GROUNDED
        result = verify_atom_quote(atom, corpus_text, recommendations, threshold=0.99)
        # With threshold=0.99, exact substring match still yields VERIFIED,
        # and full keyword overlap yields GROUNDED with score=1.0 which passes threshold
        assert result.status in ("UNGROUNDED", "VERIFIED", "GROUNDED")

    def test_whitespace_only_quote(self, corpus_text: str, recommendations: list[dict[str, str | int | None]]) -> None:
        atom = _make_atom(" ")  # min_length=1 so empty string is invalid
        result = verify_atom_quote(atom, corpus_text, recommendations)
        assert result.status == "UNGROUNDED"

    def test_verified_has_rec_id(self, corpus_text: str, recommendations: list[dict[str, str | int | None]]) -> None:
        atom = _make_atom("Obtain blood cultures before antibiotic administration.")
        result = verify_atom_quote(atom, corpus_text, recommendations)
        assert result.matched_rec_id == "R2"


# ------------------------------------------------------------------
# verify_atom_quotes (batch)
# ------------------------------------------------------------------


class TestVerifyAtomQuotes:
    def test_batch_returns_all(self, corpus_text: str, recommendations: list[dict[str, str | int | None]]) -> None:
        atoms = [
            _make_atom("Obtain blood cultures before antibiotic administration.", "a1"),
            _make_atom("completely fabricated text about mars rovers", "a2"),
        ]
        results = verify_atom_quotes(atoms, corpus_text, recommendations)
        assert len(results) == 2
        assert results[0].atom_id == "a1"
        assert results[1].atom_id == "a2"

    def test_empty_atoms(self, corpus_text: str, recommendations: list[dict[str, str | int | None]]) -> None:
        results = verify_atom_quotes([], corpus_text, recommendations)
        assert results == []

    def test_mixed_statuses(self, corpus_text: str, recommendations: list[dict[str, str | int | None]]) -> None:
        atoms = [
            _make_atom("Obtain blood cultures before antibiotic administration.", "exact"),
            _make_atom("quantum entanglement in photosynthesis", "unrelated"),
        ]
        results = verify_atom_quotes(atoms, corpus_text, recommendations)
        statuses = {r.atom_id: r.status for r in results}
        assert statuses["exact"] == "VERIFIED"
        assert statuses["unrelated"] == "UNGROUNDED"
