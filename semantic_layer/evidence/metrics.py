"""Retrieval quality metrics for evidence grounding evaluation.

8 metrics measuring retrieval accuracy, provenance integrity,
and downstream compliance impact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Sequence

from .provenance import compute_quote_hash
from .schema import EvidenceRecord


def evidence_precision_at_k(
    retrieved: Sequence[str], gold: Sequence[str], k: int,
) -> float:
    """Fraction of top-k retrieved clause IDs that are in gold set."""
    if k <= 0:
        return 0.0
    top_k = list(retrieved)[:k]
    if not top_k:
        return 0.0
    gold_set = set(gold)
    hits = sum(1 for r in top_k if r in gold_set)
    return hits / k


def clause_recall_at_k(
    retrieved: Sequence[str], gold: Sequence[str], k: int,
) -> float:
    """Fraction of gold clause IDs found in top-k retrieved."""
    if not gold or k <= 0:
        return 0.0
    top_k = set(list(retrieved)[:k])
    hits = sum(1 for g in gold if g in top_k)
    return hits / len(gold)


def quote_span_f1(
    predicted_span: tuple[int, int], gold_span: tuple[int, int],
) -> float:
    """Token-overlap F1 between predicted and gold character spans.

    Treats character positions as the "token" set.
    """
    p_start, p_end = predicted_span
    g_start, g_end = gold_span

    if p_end <= p_start or g_end <= g_start:
        return 0.0

    overlap_start = max(p_start, g_start)
    overlap_end = min(p_end, g_end)
    overlap = max(0, overlap_end - overlap_start)

    if overlap == 0:
        return 0.0

    precision = overlap / (p_end - p_start)
    recall = overlap / (g_end - g_start)

    return 2 * precision * recall / (precision + recall)


def provenance_verified_rate(records: Sequence[EvidenceRecord]) -> float:
    """Fraction of records with valid provenance hash (non-empty quote_hash)."""
    if not records:
        return 0.0
    verified = sum(
        1 for r in records
        if isinstance(r.get("quote_hash"), str) and r["quote_hash"]
    )
    return verified / len(records)


def hallucinated_clause_rate(
    records: Sequence[EvidenceRecord], valid_ids: set[str],
) -> float:
    """Fraction of records whose clause_id is NOT in the valid set."""
    if not records:
        return 0.0
    hallucinated = sum(
        1 for r in records
        if r.get("clause_id") not in valid_ids
    )
    return hallucinated / len(records)


def version_correctness(
    records: Sequence[EvidenceRecord], expected_version: str,
) -> float:
    """Fraction of records where guideline_id contains expected version string."""
    if not records or not expected_version:
        return 0.0
    correct = sum(
        1 for r in records
        if isinstance(r.get("guideline_id"), str)
        and expected_version.lower() in r["guideline_id"].lower()
    )
    return correct / len(records)


def compliance_delta_vs_oracle(
    actual_score: float, oracle_score: float,
) -> float:
    """Relative compliance gap: (oracle - actual) / oracle.

    Returns 0.0 if oracle_score is 0 (no baseline).
    Positive = actual is worse than oracle.
    """
    if oracle_score == 0.0:
        return 0.0
    return (oracle_score - actual_score) / oracle_score


@dataclass
class EvidenceMetricsReport:
    """Aggregated evidence quality metrics."""

    precision_at_k: float = 0.0
    recall_at_k: float = 0.0
    span_f1: float = 0.0
    verified_rate: float = 0.0
    hallucinated_rate: float = 0.0
    version_correct: float = 0.0
    compliance_delta: float = 0.0
    k: int = 10

    def summary(self) -> dict[str, Any]:
        return {
            "evidence_precision_at_k": round(self.precision_at_k, 4),
            "clause_recall_at_k": round(self.recall_at_k, 4),
            "quote_span_f1": round(self.span_f1, 4),
            "provenance_verified_rate": round(self.verified_rate, 4),
            "hallucinated_clause_rate": round(self.hallucinated_rate, 4),
            "version_correctness": round(self.version_correct, 4),
            "compliance_delta_vs_oracle": round(self.compliance_delta, 4),
            "k": self.k,
        }

    def passes_thresholds(
        self,
        min_precision: float = 0.95,
        min_verified: float = 0.95,
        max_hallucinated: float = 0.005,
        max_compliance_delta: float = 0.02,
    ) -> dict[str, bool]:
        return {
            "precision_pass": self.precision_at_k >= min_precision,
            "verified_pass": self.verified_rate >= min_verified,
            "hallucination_pass": self.hallucinated_rate <= max_hallucinated,
            "compliance_delta_pass": abs(self.compliance_delta) <= max_compliance_delta,
        }


def compute_evidence_metrics(
    retrieved: Sequence[str],
    gold: Sequence[str],
    records: Sequence[EvidenceRecord],
    valid_ids: set[str],
    expected_version: str = "",
    actual_score: float = 0.0,
    oracle_score: float = 0.0,
    k: int = 10,
    predicted_span: tuple[int, int] | None = None,
    gold_span: tuple[int, int] | None = None,
) -> EvidenceMetricsReport:
    """Compute all 8 evidence quality metrics at once."""
    span_f1_val = 0.0
    if predicted_span and gold_span:
        span_f1_val = quote_span_f1(predicted_span, gold_span)

    return EvidenceMetricsReport(
        precision_at_k=evidence_precision_at_k(retrieved, gold, k),
        recall_at_k=clause_recall_at_k(retrieved, gold, k),
        span_f1=span_f1_val,
        verified_rate=provenance_verified_rate(records),
        hallucinated_rate=hallucinated_clause_rate(records, valid_ids),
        version_correct=version_correctness(records, expected_version),
        compliance_delta=compliance_delta_vs_oracle(actual_score, oracle_score),
        k=k,
    )
