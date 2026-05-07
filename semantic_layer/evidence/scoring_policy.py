from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import TypedDict

from .schema import EvidenceRecord


class ScoringAdjustment(TypedDict):
    action_id: str
    base_score: float
    adjustment: float
    adjusted_score: float
    reason: str


@dataclass
class EvidenceScoringPolicy:
    """Policy for adjusting scores based on evidence verification status."""

    verified_bonus: float = 0.0
    unverified_penalty: float = 0.1
    no_evidence_penalty: float = 0.15
    abstain_protection: float = 0.05
    high_risk_actions: list[str] | None = None

    @classmethod
    def default(cls) -> EvidenceScoringPolicy:
        return cls()

    @classmethod
    def strict(cls) -> EvidenceScoringPolicy:
        """Strict policy for high-stakes scenarios."""
        return cls(
            verified_bonus=0.02,
            unverified_penalty=0.2,
            no_evidence_penalty=0.25,
            abstain_protection=0.1,
        )


def _is_verified_record(record: EvidenceRecord, verified_clause_ids: set[str] | None) -> bool:
    clause_id = record["clause_id"]
    if verified_clause_ids is not None:
        return clause_id in verified_clause_ids
    return bool(record["quote_hash"])


def _did_abstain(action: Mapping[str, object]) -> bool:
    abstain_keys = (
        "abstain",
        "abstained",
        "request_more_info",
        "requested_more_info",
        "abstain_recommendation",
    )
    for key in abstain_keys:
        if bool(action.get(key)):
            return True
    action_id = action.get("action_id")
    if isinstance(action_id, str):
        lowered = action_id.lower()
        return "abstain" in lowered or "request_more_info" in lowered
    return False


def _to_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    return default


def apply_evidence_scoring(
    action_scores: Sequence[Mapping[str, object]],
    evidence_records: list[EvidenceRecord],
    policy: EvidenceScoringPolicy,
    verified_clause_ids: set[str] | None = None,
) -> list[ScoringAdjustment]:
    """Apply evidence-based scoring adjustments."""
    records_by_action: dict[str, list[EvidenceRecord]] = {}
    for record in evidence_records:
        records_by_action.setdefault(record["action_id"], []).append(record)

    high_risk_set = set(policy.high_risk_actions or [])
    adjustments: list[ScoringAdjustment] = []

    for action in action_scores:
        action_id = str(action.get("action_id", ""))
        base_score = _to_float(action.get("score", 0.0), default=0.0)
        is_mandatory = bool(action.get("is_mandatory", False))

        reason = "non_mandatory_no_adjustment"
        adjustment = 0.0

        applies = is_mandatory and (
            policy.high_risk_actions is None or action_id in high_risk_set
        )
        if applies:
            action_records = records_by_action.get(action_id, [])
            has_evidence = len(action_records) > 0
            has_verified = any(
                _is_verified_record(record, verified_clause_ids)
                for record in action_records
            )

            if has_verified:
                adjustment = policy.verified_bonus
                reason = "verified_evidence_bonus"
            elif has_evidence:
                penalty = -policy.unverified_penalty
                if _did_abstain(action):
                    penalty = min(0.0, penalty + policy.abstain_protection)
                    reason = "unverified_evidence_penalty_with_abstain_protection"
                else:
                    reason = "unverified_evidence_penalty"
                adjustment = penalty
            else:
                penalty = -policy.no_evidence_penalty
                if _did_abstain(action):
                    penalty = min(0.0, penalty + policy.abstain_protection)
                    reason = "no_evidence_penalty_with_abstain_protection"
                else:
                    reason = "no_evidence_penalty"
                adjustment = penalty
        elif is_mandatory:
            reason = "mandatory_not_high_risk_no_adjustment"

        adjusted_score = max(0.0, min(1.0, base_score + adjustment))
        adjustments.append(
            {
                "action_id": action_id,
                "base_score": base_score,
                "adjustment": adjustment,
                "adjusted_score": adjusted_score,
                "reason": reason,
            }
        )

    return adjustments


def compute_evidence_adjusted_score(
    base_compliance_score: float,
    adjustments: Sequence[ScoringAdjustment],
) -> float:
    """Compute final score after all evidence adjustments. Clamp to [0, 1]."""
    total_adjustment = sum(adj["adjustment"] for adj in adjustments)
    return max(0.0, min(1.0, base_compliance_score + total_adjustment))
