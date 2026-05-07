"""Tests for sgsc.audit.source_fidelity — combined fidelity metrics."""

from __future__ import annotations

from sgsc.audit.source_fidelity import compute_source_fidelity
from sgsc.verification.quote_verifier import QuoteVerificationResult


def _make_result(atom_id: str, status: str) -> QuoteVerificationResult:
    return QuoteVerificationResult(
        atom_id=atom_id,
        status=status,
        best_span="test span",
        score=0.5,
    )


class TestComputeSourceFidelity:
    """Tests for compute_source_fidelity."""

    def test_all_verified(self) -> None:
        results = [_make_result(f"a{i}", "VERIFIED") for i in range(5)]
        report = compute_source_fidelity(results)
        assert report.hallucination_report.hallucination_rate == 0.0
        assert report.hallucination_report.verified == 5
        assert report.entailment_rate == 0.0
        assert report.total_atoms_checked == 0

    def test_all_ungrounded(self) -> None:
        results = [_make_result(f"a{i}", "UNGROUNDED") for i in range(4)]
        report = compute_source_fidelity(results)
        assert report.hallucination_report.hallucination_rate == 1.0
        assert report.hallucination_report.ungrounded == 4

    def test_mixed_verification(self) -> None:
        results = [
            _make_result("a1", "VERIFIED"),
            _make_result("a2", "GROUNDED"),
            _make_result("a3", "UNGROUNDED"),
            _make_result("a4", "VERIFIED"),
        ]
        report = compute_source_fidelity(results)
        assert report.hallucination_report.hallucination_rate == 0.25

    def test_with_entailment_verdicts(self) -> None:
        results = [_make_result("a1", "VERIFIED")]
        verdicts = ["ENTAILED", "ENTAILED", "NOT_ENTAILED", "PARTIAL"]
        report = compute_source_fidelity(results, verdicts)
        assert report.entailment_rate == 0.5
        assert report.total_atoms_checked == 4

    def test_empty_results(self) -> None:
        report = compute_source_fidelity([])
        assert report.hallucination_report.hallucination_rate == 0.0
        assert report.hallucination_report.total_atoms == 0

    def test_is_acceptable_good(self) -> None:
        results = [_make_result(f"a{i}", "VERIFIED") for i in range(10)]
        report = compute_source_fidelity(results)
        assert report.is_acceptable is True

    def test_is_acceptable_high_hallucination(self) -> None:
        results = [_make_result(f"a{i}", "UNGROUNDED") for i in range(10)]
        report = compute_source_fidelity(results)
        assert report.is_acceptable is False

    def test_is_acceptable_with_entailment(self) -> None:
        results = [_make_result("a1", "VERIFIED")]
        # Low entailment rate should fail
        verdicts = ["NOT_ENTAILED"] * 10
        report = compute_source_fidelity(results, verdicts)
        assert report.is_acceptable is False

    def test_no_entailment_check_is_acceptable(self) -> None:
        """When entailment wasn't run (total_atoms_checked==0), it's acceptable."""
        results = [_make_result("a1", "VERIFIED")]
        report = compute_source_fidelity(results, None)
        assert report.is_acceptable is True
        assert report.total_atoms_checked == 0
