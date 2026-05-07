"""Source fidelity audit: entailment rate and hallucination rate reporting."""

from __future__ import annotations

from dataclasses import dataclass

from sgsc.verification.hallucination_detector import HallucinationReport, compute_hallucination_rate
from sgsc.verification.quote_verifier import QuoteVerificationResult

# ------------------------------------------------------------------
# Fidelity report
# ------------------------------------------------------------------


@dataclass
class SourceFidelityReport:
    """Combined source fidelity metrics."""

    hallucination_report: HallucinationReport
    entailment_rate: float = 0.0
    """Fraction of atoms with ENTAILED verdict (if entailment was run)."""

    total_atoms_checked: int = 0

    @property
    def is_acceptable(self) -> bool:
        """True if hallucination rate < 0.1 and entailment rate > 0.8."""
        return self.hallucination_report.hallucination_rate < 0.1 and (
            self.entailment_rate > 0.8 or self.total_atoms_checked == 0
        )


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def compute_source_fidelity(
    verification_results: list[QuoteVerificationResult],
    entailment_verdicts: list[str] | None = None,
) -> SourceFidelityReport:
    """Compute source fidelity from verification and entailment results.

    Args:
        verification_results: Quote verification results.
        entailment_verdicts: Optional list of verdict strings (ENTAILED/NOT_ENTAILED/PARTIAL).

    Returns:
        SourceFidelityReport with combined metrics.
    """
    hallucination = compute_hallucination_rate(verification_results)

    entailment_rate = 0.0
    total_checked = 0
    if entailment_verdicts:
        total_checked = len(entailment_verdicts)
        entailed = sum(1 for v in entailment_verdicts if v == "ENTAILED")
        entailment_rate = entailed / total_checked if total_checked > 0 else 0.0

    return SourceFidelityReport(
        hallucination_report=hallucination,
        entailment_rate=round(entailment_rate, 4),
        total_atoms_checked=total_checked,
    )
