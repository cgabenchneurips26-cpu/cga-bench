from __future__ import annotations

from cga_bench.semantic_layer.evidence.metrics import (
    EvidenceMetricsReport,
    clause_recall_at_k,
    compliance_delta_vs_oracle,
    compute_evidence_metrics,
    evidence_precision_at_k,
    hallucinated_clause_rate,
    provenance_verified_rate,
    quote_span_f1,
    version_correctness,
)
from cga_bench.semantic_layer.evidence.schema import EvidenceRecord


class TestPrecisionAtK:
    def test_all_relevant(self):
        assert evidence_precision_at_k(["a", "b"], ["a", "b"], 2) == 1.0

    def test_none_relevant(self):
        assert evidence_precision_at_k(["x", "y"], ["a", "b"], 2) == 0.0

    def test_half_relevant(self):
        assert evidence_precision_at_k(["a", "x"], ["a", "b"], 2) == 0.5


class TestRecallAtK:
    def test_all_recalled(self):
        assert clause_recall_at_k(["a", "b", "c"], ["a", "b"], 3) == 1.0

    def test_partial_recall(self):
        assert abs(clause_recall_at_k(["a", "x"], ["a", "b", "c"], 2) - (1 / 3)) < 1e-9


class TestSpanF1:
    def test_perfect_overlap(self):
        assert quote_span_f1((10, 20), (10, 20)) == 1.0

    def test_no_overlap(self):
        assert quote_span_f1((0, 10), (20, 30)) == 0.0

    def test_partial_overlap(self):
        f1 = quote_span_f1((0, 20), (10, 30))
        assert 0.0 < f1 < 1.0


class TestProvenanceVerifiedRate:
    def test_all_verified(self):
        records: list[EvidenceRecord] = [
            {
                "action_id": "a",
                "guideline_id": "g",
                "clause_id": "C",
                "quote_span": {"start": 0, "end": 1, "text": "x", "hash": "abc"},
                "quote_hash": "abc",
                "confidence": 0.9,
            },
        ]
        assert provenance_verified_rate(records) == 1.0

    def test_empty_records(self):
        assert provenance_verified_rate([]) == 0.0


class TestHallucinatedClauseRate:
    def test_no_hallucinations(self):
        records: list[EvidenceRecord] = [
            {
                "action_id": "a",
                "guideline_id": "g",
                "clause_id": "VALID_1",
                "quote_span": {"start": 0, "end": 1, "text": "x", "hash": "h"},
                "quote_hash": "h",
                "confidence": 0.9,
            },
        ]
        assert hallucinated_clause_rate(records, {"VALID_1"}) == 0.0

    def test_all_hallucinated(self):
        records: list[EvidenceRecord] = [
            {
                "action_id": "a",
                "guideline_id": "g",
                "clause_id": "FAKE_ID",
                "quote_span": {"start": 0, "end": 1, "text": "x", "hash": "h"},
                "quote_hash": "h",
                "confidence": 0.5,
            },
        ]
        assert hallucinated_clause_rate(records, {"VALID_1"}) == 1.0


class TestVersionCorrectness:
    def test_correct_version(self):
        records: list[EvidenceRecord] = [
            {
                "action_id": "a",
                "guideline_id": "ssc_sepsis_2021",
                "clause_id": "C",
                "quote_span": {"start": 0, "end": 1, "text": "x", "hash": "h"},
                "quote_hash": "h",
                "confidence": 0.9,
            },
        ]
        assert version_correctness(records, "2021") == 1.0

    def test_wrong_version(self):
        records: list[EvidenceRecord] = [
            {
                "action_id": "a",
                "guideline_id": "ssc_sepsis_2021",
                "clause_id": "C",
                "quote_span": {"start": 0, "end": 1, "text": "x", "hash": "h"},
                "quote_hash": "h",
                "confidence": 0.9,
            },
        ]
        assert version_correctness(records, "2023") == 0.0


class TestComputeEvidenceMetrics:
    def test_compute_bundle(self):
        records: list[EvidenceRecord] = [
            {
                "action_id": "a",
                "guideline_id": "ssc_sepsis_2021",
                "clause_id": "VALID_1",
                "quote_span": {"start": 0, "end": 1, "text": "x", "hash": "h"},
                "quote_hash": "h",
                "confidence": 1.0,
            },
        ]
        report = compute_evidence_metrics(
            retrieved=["VALID_1"],
            gold=["VALID_1"],
            records=records,
            valid_ids={"VALID_1"},
            expected_version="2021",
            actual_score=1.0,
            oracle_score=1.0,
            k=1,
        )
        assert report.precision_at_k == 1.0


class TestComplianceDelta:
    def test_perfect_match(self):
        assert compliance_delta_vs_oracle(1.0, 1.0) == 0.0

    def test_gap(self):
        assert abs(compliance_delta_vs_oracle(0.8, 1.0) - 0.2) < 1e-9

    def test_oracle_zero(self):
        assert compliance_delta_vs_oracle(0.5, 0.0) == 0.0


class TestPassFailThresholds:
    def test_passing_thresholds(self):
        report = EvidenceMetricsReport(
            precision_at_k=0.96,
            recall_at_k=0.9,
            span_f1=0.85,
            verified_rate=0.97,
            hallucinated_rate=0.001,
            version_correct=1.0,
            compliance_delta=0.01,
            k=10,
        )
        thresholds = report.passes_thresholds()
        assert thresholds["precision_pass"] is True
        assert thresholds["verified_pass"] is True
        assert thresholds["hallucination_pass"] is True
        assert thresholds["compliance_delta_pass"] is True

    def test_failing_thresholds(self):
        report = EvidenceMetricsReport(
            precision_at_k=0.5,
            recall_at_k=0.3,
            span_f1=0.2,
            verified_rate=0.5,
            hallucinated_rate=0.1,
            version_correct=0.0,
            compliance_delta=0.5,
            k=10,
        )
        thresholds = report.passes_thresholds()
        assert thresholds["precision_pass"] is False
        assert thresholds["hallucination_pass"] is False


class TestEmptyEdgeCases:
    def test_empty_retrieved(self):
        assert evidence_precision_at_k([], ["a"], 5) == 0.0

    def test_empty_gold(self):
        assert clause_recall_at_k(["a"], [], 5) == 0.0

    def test_k_zero(self):
        assert evidence_precision_at_k(["a"], ["a"], 0) == 0.0
