from __future__ import annotations

from dataclasses import dataclass
from math import erf, sqrt
from typing import TypedDict, cast

from .provenance import QuoteSpan
from .schema import EvidenceRecord, validate_evidence_record


class RetrievalMetadata(TypedDict):
    method: str
    top_k: int
    passage_ids: list[str]
    retrieval_score: float
    latency_ms: float


class ExtendedEvidenceRecord(TypedDict):
    """EvidenceRecord + retrieval metadata + uncertainty."""

    action_id: str
    guideline_id: str
    clause_id: str
    quote_span: QuoteSpan
    quote_hash: str
    confidence: float
    retrieval: RetrievalMetadata
    uncertainty: dict[str, object]


def validate_extended_record(record: ExtendedEvidenceRecord) -> list[str]:
    """Validate all fields including retrieval metadata."""
    errors: list[str] = []
    raw_record: dict[str, object] = dict(record)

    base_record = cast(
        EvidenceRecord,
        cast(
            object,
        {
            "action_id": raw_record.get("action_id", ""),
            "guideline_id": raw_record.get("guideline_id", ""),
            "clause_id": raw_record.get("clause_id", ""),
            "quote_span": raw_record.get("quote_span", {}),
            "quote_hash": raw_record.get("quote_hash", ""),
            "confidence": raw_record.get("confidence", -1.0),
        },
        ),
    )
    errors.extend(validate_evidence_record(base_record))

    retrieval = raw_record.get("retrieval")
    if not isinstance(retrieval, dict):
        errors.append("retrieval:not_dict")
    else:
        retrieval_data = cast(dict[str, object], retrieval)
        required_retrieval = {
            "method",
            "top_k",
            "passage_ids",
            "retrieval_score",
            "latency_ms",
        }
        missing = required_retrieval - set(retrieval_data.keys())
        if missing:
            errors.append(f"retrieval:missing_fields:{','.join(sorted(missing))}")
        method = retrieval_data.get("method")
        if not isinstance(method, str) or method not in {"bm25", "dense", "hybrid"}:
            errors.append("retrieval.method:invalid")

        top_k = retrieval_data.get("top_k")
        if not isinstance(top_k, int) or top_k <= 0:
            errors.append("retrieval.top_k:invalid")

        passage_ids = retrieval_data.get("passage_ids")
        if not isinstance(passage_ids, list):
            errors.append("retrieval.passage_ids:invalid")
        else:
            for pid in cast(list[object], passage_ids):
                if not isinstance(pid, str):
                    errors.append("retrieval.passage_ids:invalid")
                    break

        retrieval_score = retrieval_data.get("retrieval_score")
        if not isinstance(retrieval_score, (int, float)):
            errors.append("retrieval.retrieval_score:not_numeric")

        latency_ms = retrieval_data.get("latency_ms")
        if not isinstance(latency_ms, (int, float)) or latency_ms < 0:
            errors.append("retrieval.latency_ms:invalid")

    uncertainty = raw_record.get("uncertainty")
    if not isinstance(uncertainty, dict):
        errors.append("uncertainty:not_dict")

    return errors


def compute_overconfidence_rate(
    confidences: list[float],
    correctness: list[bool],
    threshold: float = 0.8,
) -> float:
    """Fraction where confidence > threshold but answer wrong."""
    if not confidences or not correctness or len(confidences) != len(correctness):
        return 0.0

    overconfident_wrong = sum(
        1
        for conf, is_correct in zip(confidences, correctness)
        if conf > threshold and not is_correct
    )
    return overconfident_wrong / len(confidences)


@dataclass
class StatisticalTestResult:
    """Result of a statistical comparison."""

    test_name: str
    statistic: float
    p_value: float
    effect_size: float
    significant: bool
    n_samples: int

    def summary(self) -> dict[str, object]:
        return {
            "test_name": self.test_name,
            "statistic": round(self.statistic, 6),
            "p_value": round(self.p_value, 6),
            "effect_size": round(self.effect_size, 6),
            "significant": self.significant,
            "n_samples": self.n_samples,
        }


def cohens_kappa(rater1: list[int], rater2: list[int]) -> float:
    """Cohen's kappa for inter-rater agreement."""
    if not rater1 or not rater2 or len(rater1) != len(rater2):
        return 0.0

    n = len(rater1)
    po = sum(1 for a, b in zip(rater1, rater2) if a == b) / n

    categories = set(rater1) | set(rater2)
    p1: dict[int, float] = {}
    p2: dict[int, float] = {}
    for category in categories:
        p1[category] = sum(1 for item in rater1 if item == category) / n
        p2[category] = sum(1 for item in rater2 if item == category) / n

    pe = sum(p1[c] * p2[c] for c in categories)
    if pe >= 1.0:
        return 1.0 if po >= 1.0 else 0.0
    return (po - pe) / (1.0 - pe)


def _normal_cdf(z: float) -> float:
    return 0.5 * (1.0 + erf(z / sqrt(2.0)))


def paired_proportion_test(
    successes_a: int,
    total_a: int,
    successes_b: int,
    total_b: int,
) -> StatisticalTestResult:
    """McNemar-like test for paired proportions."""
    if total_a <= 0 or total_b <= 0:
        return StatisticalTestResult(
            test_name="paired_proportion_z",
            statistic=0.0,
            p_value=1.0,
            effect_size=0.0,
            significant=False,
            n_samples=0,
        )

    p_a = successes_a / total_a
    p_b = successes_b / total_b
    effect_size = p_b - p_a

    pooled = (successes_a + successes_b) / (total_a + total_b)
    standard_error = sqrt(max(pooled * (1.0 - pooled) * (1.0 / total_a + 1.0 / total_b), 0.0))

    if standard_error == 0.0:
        statistic = 0.0
        p_value = 1.0
    else:
        statistic = effect_size / standard_error
        p_value = 2.0 * (1.0 - _normal_cdf(abs(statistic)))

    return StatisticalTestResult(
        test_name="paired_proportion_z",
        statistic=statistic,
        p_value=p_value,
        effect_size=effect_size,
        significant=p_value < 0.05,
        n_samples=min(total_a, total_b),
    )
