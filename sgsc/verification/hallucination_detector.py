"""Hallucination rate computation from quote verification results."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field
from sgsc.verification.quote_verifier import QuoteVerificationResult


class HallucinationReport(BaseModel):
    """Aggregate hallucination metrics from atom verification."""

    model_config = ConfigDict(frozen=True)

    total_atoms: int = Field(0, ge=0)
    verified: int = Field(0, ge=0)
    grounded: int = Field(0, ge=0)
    ungrounded: int = Field(0, ge=0)
    hallucination_rate: float = Field(0.0, ge=0.0, le=1.0)


def compute_hallucination_rate(
    results: list[QuoteVerificationResult],
) -> HallucinationReport:
    """Compute hallucination rate from verification results.

    hallucination_rate = ungrounded / total (0.0 if total == 0).
    """
    total = len(results)
    verified = sum(1 for r in results if r.status == "VERIFIED")
    grounded = sum(1 for r in results if r.status == "GROUNDED")
    ungrounded = sum(1 for r in results if r.status == "UNGROUNDED")

    rate = ungrounded / total if total > 0 else 0.0

    return HallucinationReport(
        total_atoms=total,
        verified=verified,
        grounded=grounded,
        ungrounded=ungrounded,
        hallucination_rate=round(rate, 4),
    )
