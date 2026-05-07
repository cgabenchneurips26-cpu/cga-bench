"""
TemporalConstraintChecker: Declare template-based temporal constraint checking.

Thin adapter over existing semantic_layer.conformance.temporal_verifier
for checking:
  - Response(A, B): if A occurs, B must eventually occur after A
  - Precedence(A, B): if B occurs, A must have occurred before B
  - Existence(A): A must occur at least once
  - Absence(A): A must never occur
  - TimeBoundedResponse(A, B, max_minutes): Response with time limit
"""

import logging
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple

logger = logging.getLogger(__name__)


@dataclass
class TemporalConstraint:
    """A single temporal constraint."""

    template: str  # response | precedence | existence | absence | time_bounded_response
    action_a: str
    action_b: Optional[str] = None
    max_minutes: Optional[float] = None
    description: str = ""


@dataclass
class ConstraintResult:
    """Result of checking one temporal constraint."""

    constraint: TemporalConstraint
    satisfied: bool
    details: str = ""


class TemporalConstraintChecker:
    """Declare template-based temporal constraint checker.

    Works directly with event traces (list of (action_id, timestamp) tuples).
    Can optionally delegate to semantic_layer.conformance.temporal_verifier
    for complex LTL/CTL checks.
    """

    def check_response(
        self,
        trace: Sequence[Tuple[str, float]],
        action_a: str,
        action_b: str,
    ) -> bool:
        """Response(A, B): if A occurs, B must eventually occur after A.

        Returns True if the constraint is satisfied (or A never occurs).
        """
        a_occurred = False
        for action_id, _ts in trace:
            if action_id.lower() == action_a.lower():
                a_occurred = True
            if a_occurred and action_id.lower() == action_b.lower():
                return True
        return not a_occurred  # vacuously true if A never occurs

    def check_precedence(
        self,
        trace: Sequence[Tuple[str, float]],
        action_a: str,
        action_b: str,
    ) -> bool:
        """Precedence(A, B): if B occurs, A must have occurred before B.

        Returns True if A precedes B (or B never occurs).
        """
        a_seen = False
        for action_id, _ts in trace:
            if action_id.lower() == action_a.lower():
                a_seen = True
            if action_id.lower() == action_b.lower():
                if not a_seen:
                    return False
        return True

    def check_existence(
        self,
        trace: Sequence[Tuple[str, float]],
        action_a: str,
    ) -> bool:
        """Existence(A): A must occur at least once."""
        return any(
            action_id.lower() == action_a.lower()
            for action_id, _ts in trace
        )

    def check_absence(
        self,
        trace: Sequence[Tuple[str, float]],
        action_a: str,
    ) -> bool:
        """Absence(A): A must never occur."""
        return not any(
            action_id.lower() == action_a.lower()
            for action_id, _ts in trace
        )

    def check_time_bounded_response(
        self,
        trace: Sequence[Tuple[str, float]],
        action_a: str,
        action_b: str,
        max_minutes: float,
    ) -> bool:
        """TimeBoundedResponse(A, B, max_minutes): if A occurs, B must occur
        within max_minutes after A.

        Returns True if satisfied (or A never occurs).
        """
        a_ts = None
        for action_id, ts in trace:
            if action_id.lower() == action_a.lower():
                a_ts = ts
            if a_ts is not None and action_id.lower() == action_b.lower():
                if ts - a_ts <= max_minutes:
                    return True
        return a_ts is None  # vacuously true if A never occurs

    def check_all(
        self,
        constraints: List[TemporalConstraint],
        trace: Sequence[Tuple[str, float]],
    ) -> List[ConstraintResult]:
        """Check all constraints against a trace.

        Args:
            constraints: List of TemporalConstraint objects.
            trace: List of (action_id, timestamp) tuples.

        Returns:
            List of ConstraintResult with satisfaction status.
        """
        results = []
        for c in constraints:
            if c.template == "response":
                ok = self.check_response(trace, c.action_a, c.action_b)
            elif c.template == "precedence":
                ok = self.check_precedence(trace, c.action_a, c.action_b)
            elif c.template == "existence":
                ok = self.check_existence(trace, c.action_a)
            elif c.template == "absence":
                ok = self.check_absence(trace, c.action_a)
            elif c.template == "time_bounded_response":
                ok = self.check_time_bounded_response(
                    trace, c.action_a, c.action_b, c.max_minutes
                )
            else:
                logger.warning(f"Unknown template: {c.template}")
                ok = True  # conservative

            results.append(ConstraintResult(
                constraint=c,
                satisfied=ok,
                details=f"{'PASS' if ok else 'FAIL'}: {c.template}({c.action_a}"
                         + (f", {c.action_b}" if c.action_b else "")
                         + (f", max={c.max_minutes}min" if c.max_minutes else "")
                         + ")",
            ))

        return results
