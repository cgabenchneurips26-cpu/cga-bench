"""Evidence output schema for CGA-Bench retrieval grounding.

Defines the minimum evidence record that agents/retrieval systems must produce
to prove their actions are grounded in actual CPG clauses.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, TypedDict

from .provenance import QuoteSpan


class EvidenceRecord(TypedDict):
    """Single evidence record linking an action to a CPG clause.

    Every field is required. Missing fields fail validation.
    """

    action_id: str
    guideline_id: str
    clause_id: str
    quote_span: QuoteSpan
    quote_hash: str
    confidence: float


_CLAUSE_ID_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]+$")


def validate_evidence_record(
    record: EvidenceRecord,
    valid_clause_ids: set[str] | None = None,
) -> list[str]:
    """Validate an evidence record for completeness and correctness.

    Returns a list of error strings. Empty list = valid.
    """
    errors: list[str] = []

    required_keys = {"action_id", "guideline_id", "clause_id", "quote_span", "quote_hash", "confidence"}
    missing = required_keys - set(record.keys())
    if missing:
        errors.append(f"missing_fields:{','.join(sorted(missing))}")
        return errors

    if not isinstance(record.get("action_id"), str) or not record["action_id"]:
        errors.append("action_id:empty_or_invalid")

    if not isinstance(record.get("guideline_id"), str) or not record["guideline_id"]:
        errors.append("guideline_id:empty_or_invalid")

    clause_id = record.get("clause_id")
    if not isinstance(clause_id, str) or not clause_id:
        errors.append("clause_id:empty_or_invalid")
    elif not _CLAUSE_ID_PATTERN.match(clause_id):
        errors.append(f"clause_id:bad_format:{clause_id}")

    confidence = record.get("confidence")
    if not isinstance(confidence, (int, float)):
        errors.append("confidence:not_numeric")
    elif confidence < 0.0 or confidence > 1.0:
        errors.append(f"confidence:out_of_range:{confidence}")

    if not isinstance(record.get("quote_hash"), str) or not record["quote_hash"]:
        errors.append("quote_hash:empty_or_invalid")

    span = record.get("quote_span")
    if not isinstance(span, dict):
        errors.append("quote_span:not_dict")
    else:
        for key in ("start", "end", "text", "hash"):
            if key not in span:
                errors.append(f"quote_span:missing_{key}")

    if valid_clause_ids is not None and isinstance(clause_id, str):
        if clause_id not in valid_clause_ids:
            errors.append(f"clause_id:not_in_index:{clause_id}")

    return errors


@dataclass
class EvidenceBundle:
    """Collection of evidence records for a single episode."""

    episode_id: str
    records: list[EvidenceRecord] = field(default_factory=list)

    def by_action_id(self, action_id: str) -> list[EvidenceRecord]:
        return [r for r in self.records if r.get("action_id") == action_id]

    def by_guideline(self, guideline_id: str) -> list[EvidenceRecord]:
        return [r for r in self.records if r.get("guideline_id") == guideline_id]

    def verified_count(self) -> int:
        return sum(
            1 for r in self.records
            if isinstance(r.get("quote_hash"), str) and r["quote_hash"]
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "episode_id": self.episode_id,
            "records": list(self.records),
            "total": len(self.records),
            "verified": self.verified_count(),
        }
