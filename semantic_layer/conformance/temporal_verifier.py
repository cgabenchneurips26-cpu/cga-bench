"""
Temporal constraint verification for ActivityEvent sequences.

Provides formal verification of bounded temporal constraints beyond
the basic RESPONSE_WITHIN supported by the scorer. Supports:
- BOUNDED_RESPONSE: A must be followed by B within [min, max] minutes
- MAX_DELAY: B must occur within max_minutes of trace start
- PERIODIC: A must occur at least min_count times per window
- DURATION: A must persist (consecutive span) for at least min_minutes
- DEADLINE_CHAIN: A1->A2->...->An each within chained deadlines
- FREQUENCY: A must occur [min_count, max_count] times in window

All features opt-in via TemporalVerificationConfig.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from .activity import ActivityEvent


class TemporalConstraintType(str, Enum):
    """Types of temporal constraints."""
    BOUNDED_RESPONSE = "bounded_response"
    MAX_DELAY = "max_delay"
    PERIODIC = "periodic"
    DURATION = "duration"
    DEADLINE_CHAIN = "deadline_chain"
    FREQUENCY = "frequency"


class TemporalSeverity(str, Enum):
    """Severity levels for temporal violations."""
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


@dataclass
class TemporalConstraint:
    """A temporal constraint to verify against an event sequence.

    Fields vary by constraint_type:
    - BOUNDED_RESPONSE: source_activity, target_activity, min_minutes, max_minutes
    - MAX_DELAY: target_activity, max_minutes
    - PERIODIC: source_activity, min_count, max_minutes (window)
    - DURATION: source_activity, min_minutes
    - DEADLINE_CHAIN: chain_activities, chain_deadlines
    - FREQUENCY: source_activity, min_count, max_count, max_minutes (window)
    """
    constraint_id: str
    constraint_type: TemporalConstraintType
    source_activity: Optional[str] = None
    target_activity: Optional[str] = None
    min_minutes: Optional[float] = None
    max_minutes: Optional[float] = None
    min_count: Optional[int] = None
    max_count: Optional[int] = None
    chain_activities: List[str] = field(default_factory=list)
    chain_deadlines: List[float] = field(default_factory=list)
    condition: Optional[str] = None
    weight: float = 1.0
    severity: TemporalSeverity = TemporalSeverity.MEDIUM
    evidence_level: Optional[str] = None
    rationale: Optional[str] = None


@dataclass
class TemporalViolation:
    """A violation of a temporal constraint."""
    constraint_id: str
    constraint_type: TemporalConstraintType
    detail: str
    severity: TemporalSeverity
    weight: float
    expected_minutes: Optional[float] = None
    actual_minutes: Optional[float] = None
    violating_event_index: Optional[int] = None
    source_event_index: Optional[int] = None
    overshoot_minutes: Optional[float] = None


@dataclass
class TemporalVerificationConfig:
    """Configuration for temporal verification.

    All defaults preserve backward-compatible behavior.
    """
    enable_verification: bool = True
    timing_penalty_mode: str = "binary"
    grace_period_minutes: float = 0.0
    max_penalty_multiplier: float = 2.0
    half_life_minutes: float = 30.0
    strict_bounds: bool = False
    enable_frequency_checks: bool = True
    enable_chain_checks: bool = True


@dataclass
class TemporalVerificationResult:
    """Aggregated result of temporal constraint verification."""
    total_constraints: int
    satisfied_count: int
    violated_count: int
    skipped_count: int
    violations: List[TemporalViolation]
    total_penalty: float
    constraint_results: Dict[str, bool] = field(default_factory=dict)
    timing_margins: Dict[str, float] = field(default_factory=dict)


class TemporalVerifier:
    """Verifies temporal constraints against ActivityEvent sequences.

    Usage:
        config = TemporalVerificationConfig()
        verifier = TemporalVerifier(config)
        result = verifier.verify(events, constraints)
    """

    # Maximum gap between events to consider them consecutive (for DURATION)
    _CONSECUTIVE_GAP_MINUTES = 5.0

    def __init__(self, config: Optional[TemporalVerificationConfig] = None):
        self._config = config or TemporalVerificationConfig()

    def verify(
        self,
        events: List[ActivityEvent],
        constraints: List[TemporalConstraint],
        derived_flags: Optional[Dict[str, bool]] = None,
    ) -> TemporalVerificationResult:
        """Verify all temporal constraints against the event sequence.

        Args:
            events: Ordered list of ActivityEvents (sorted by timestamp_min)
            constraints: Temporal constraints to check
            derived_flags: Flag values for guard conditions

        Returns:
            TemporalVerificationResult with all violations
        """
        if not self._config.enable_verification:
            return TemporalVerificationResult(
                total_constraints=len(constraints),
                satisfied_count=0,
                violated_count=0,
                skipped_count=len(constraints),
                violations=[],
                total_penalty=0.0,
            )

        flags = derived_flags or {}
        satisfied = 0
        violated = 0
        skipped = 0
        all_violations: List[TemporalViolation] = []
        constraint_results: Dict[str, bool] = {}

        for constraint in constraints:
            # Check guard condition
            if constraint.condition and not flags.get(constraint.condition, False):
                skipped += 1
                continue

            # Skip disabled types
            if (constraint.constraint_type in (TemporalConstraintType.PERIODIC,
                                                TemporalConstraintType.FREQUENCY)
                    and not self._config.enable_frequency_checks):
                skipped += 1
                continue
            if (constraint.constraint_type == TemporalConstraintType.DEADLINE_CHAIN
                    and not self._config.enable_chain_checks):
                skipped += 1
                continue

            passed, violations = self.verify_single(events, constraint, flags)
            constraint_results[constraint.constraint_id] = passed
            if passed:
                satisfied += 1
            else:
                violated += 1
                all_violations.extend(violations)

        total_penalty = sum(v.weight for v in all_violations)
        timing_margins = self.compute_timing_margins(events, constraints)

        return TemporalVerificationResult(
            total_constraints=len(constraints),
            satisfied_count=satisfied,
            violated_count=violated,
            skipped_count=skipped,
            violations=all_violations,
            total_penalty=total_penalty,
            constraint_results=constraint_results,
            timing_margins=timing_margins,
        )

    def verify_single(
        self,
        events: List[ActivityEvent],
        constraint: TemporalConstraint,
        derived_flags: Optional[Dict[str, bool]] = None,
    ) -> Tuple[bool, List[TemporalViolation]]:
        """Verify a single temporal constraint.

        Returns:
            Tuple of (satisfied: bool, violations: List[TemporalViolation])
        """
        dispatch = {
            TemporalConstraintType.BOUNDED_RESPONSE: self._check_bounded_response,
            TemporalConstraintType.MAX_DELAY: self._check_max_delay,
            TemporalConstraintType.PERIODIC: self._check_periodic,
            TemporalConstraintType.DURATION: self._check_duration,
            TemporalConstraintType.DEADLINE_CHAIN: self._check_deadline_chain,
            TemporalConstraintType.FREQUENCY: self._check_frequency,
        }

        handler = dispatch.get(constraint.constraint_type)
        if handler is None:
            return True, []

        violations = handler(events, constraint)
        return len(violations) == 0, violations

    def convert_soft_constraint(self, soft_constraint: Any) -> Optional[TemporalConstraint]:
        """Convert an existing SoftConstraint (RESPONSE_WITHIN) to TemporalConstraint.

        Args:
            soft_constraint: SoftConstraint with template == RESPONSE_WITHIN

        Returns:
            TemporalConstraint or None if not convertible
        """
        template = getattr(soft_constraint, "template", None)
        if template is None:
            return None

        # Check if it's RESPONSE_WITHIN (handle both enum and string)
        template_val = template.value if hasattr(template, "value") else str(template)
        if template_val != "response_within":
            return None

        window = getattr(soft_constraint, "window_minutes", None)
        if window is None:
            return None

        return TemporalConstraint(
            constraint_id=f"temporal_{getattr(soft_constraint, 'constraint_id', 'unknown')}",
            constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
            source_activity=getattr(soft_constraint, "A", None),
            target_activity=getattr(soft_constraint, "B", None),
            min_minutes=0.0,
            max_minutes=window,
            condition=getattr(soft_constraint, "guard", None),
            weight=getattr(soft_constraint, "weight", 1.0),
            evidence_level=getattr(soft_constraint, "evidence_level", None),
            rationale=getattr(soft_constraint, "rationale", None)
                or getattr(soft_constraint, "description", None),
        )

    def compute_timing_margins(
        self,
        events: List[ActivityEvent],
        constraints: List[TemporalConstraint],
    ) -> Dict[str, float]:
        """Compute timing slack/margin for each constraint.

        Positive margin = time remaining before deadline.
        Negative margin = deadline exceeded.
        """
        margins: Dict[str, float] = {}
        index = self._build_activity_index(events)

        for constraint in constraints:
            margin = self._compute_margin_for_constraint(constraint, events, index)
            if margin is not None:
                margins[constraint.constraint_id] = margin

        return margins

    # ------------------------------------------------------------------
    # Private verification methods
    # ------------------------------------------------------------------

    def _check_bounded_response(
        self, events: List[ActivityEvent], constraint: TemporalConstraint
    ) -> List[TemporalViolation]:
        """Check A -> B within [min_minutes, max_minutes]."""
        violations: List[TemporalViolation] = []
        if not constraint.source_activity or not constraint.target_activity:
            return violations

        index = self._build_activity_index(events)
        source_events = index.get(constraint.source_activity, [])
        target_events = index.get(constraint.target_activity, [])

        if not source_events:
            return violations  # No trigger, no violation

        max_min = constraint.max_minutes or float("inf")
        min_min = constraint.min_minutes or 0.0

        for src_idx, src_event in source_events:
            # Find first target after source
            best_target = None
            best_target_idx = None
            for tgt_idx, tgt_event in target_events:
                if tgt_event.timestamp_min > src_event.timestamp_min:
                    best_target = tgt_event
                    best_target_idx = tgt_idx
                    break

            if best_target is None:
                # No response found
                violations.append(TemporalViolation(
                    constraint_id=constraint.constraint_id,
                    constraint_type=constraint.constraint_type,
                    detail=(f"No '{constraint.target_activity}' found after "
                            f"'{constraint.source_activity}' at t={src_event.timestamp_min:.1f}"),
                    severity=constraint.severity,
                    weight=constraint.weight,
                    expected_minutes=max_min,
                    actual_minutes=None,
                    source_event_index=src_idx,
                ))
                continue

            delay = best_target.timestamp_min - src_event.timestamp_min

            # Check max bound
            if delay > max_min:
                overshoot = delay - max_min
                weight = self._compute_graduated_weight(
                    constraint.weight, overshoot, max_min
                )
                violations.append(TemporalViolation(
                    constraint_id=constraint.constraint_id,
                    constraint_type=constraint.constraint_type,
                    detail=(f"'{constraint.target_activity}' too late: "
                            f"{delay:.1f}min > {max_min:.1f}min deadline"),
                    severity=constraint.severity,
                    weight=weight,
                    expected_minutes=max_min,
                    actual_minutes=delay,
                    violating_event_index=best_target_idx,
                    source_event_index=src_idx,
                    overshoot_minutes=overshoot,
                ))

            # Check min bound (only if strict_bounds)
            elif self._config.strict_bounds and min_min > 0 and delay < min_min:
                violations.append(TemporalViolation(
                    constraint_id=constraint.constraint_id,
                    constraint_type=constraint.constraint_type,
                    detail=(f"'{constraint.target_activity}' too early: "
                            f"{delay:.1f}min < {min_min:.1f}min minimum"),
                    severity=TemporalSeverity.LOW,
                    weight=constraint.weight * 0.5,
                    expected_minutes=min_min,
                    actual_minutes=delay,
                    violating_event_index=best_target_idx,
                    source_event_index=src_idx,
                ))

        return violations

    def _check_max_delay(
        self, events: List[ActivityEvent], constraint: TemporalConstraint
    ) -> List[TemporalViolation]:
        """Check target_activity occurs before max_minutes from trace start."""
        violations: List[TemporalViolation] = []
        if not constraint.target_activity or constraint.max_minutes is None:
            return violations

        if not events:
            violations.append(TemporalViolation(
                constraint_id=constraint.constraint_id,
                constraint_type=constraint.constraint_type,
                detail=f"Empty trace, '{constraint.target_activity}' never performed",
                severity=constraint.severity,
                weight=constraint.weight,
            ))
            return violations

        trace_start = events[0].timestamp_min
        index = self._build_activity_index(events)
        target_events = index.get(constraint.target_activity, [])

        if not target_events:
            violations.append(TemporalViolation(
                constraint_id=constraint.constraint_id,
                constraint_type=constraint.constraint_type,
                detail=f"'{constraint.target_activity}' never performed",
                severity=constraint.severity,
                weight=constraint.weight,
                expected_minutes=constraint.max_minutes,
            ))
            return violations

        first_target_idx, first_target = target_events[0]
        delay = first_target.timestamp_min - trace_start

        if delay > constraint.max_minutes:
            overshoot = delay - constraint.max_minutes
            weight = self._compute_graduated_weight(
                constraint.weight, overshoot, constraint.max_minutes
            )
            violations.append(TemporalViolation(
                constraint_id=constraint.constraint_id,
                constraint_type=constraint.constraint_type,
                detail=(f"'{constraint.target_activity}' at t={delay:.1f}min "
                        f"exceeds {constraint.max_minutes:.1f}min deadline"),
                severity=constraint.severity,
                weight=weight,
                expected_minutes=constraint.max_minutes,
                actual_minutes=delay,
                violating_event_index=first_target_idx,
                overshoot_minutes=overshoot,
            ))

        return violations

    def _check_periodic(
        self, events: List[ActivityEvent], constraint: TemporalConstraint
    ) -> List[TemporalViolation]:
        """Check source_activity occurs >= min_count times per max_minutes window."""
        violations: List[TemporalViolation] = []
        if (not constraint.source_activity or constraint.min_count is None
                or constraint.max_minutes is None):
            return violations

        if not events:
            violations.append(TemporalViolation(
                constraint_id=constraint.constraint_id,
                constraint_type=constraint.constraint_type,
                detail=f"Empty trace, periodic '{constraint.source_activity}' not met",
                severity=constraint.severity,
                weight=constraint.weight,
            ))
            return violations

        index = self._build_activity_index(events)
        source_times = [e.timestamp_min for _, e in index.get(constraint.source_activity, [])]

        if not source_times:
            violations.append(TemporalViolation(
                constraint_id=constraint.constraint_id,
                constraint_type=constraint.constraint_type,
                detail=f"'{constraint.source_activity}' never occurred (need >= {constraint.min_count} per {constraint.max_minutes:.1f}min)",
                severity=constraint.severity,
                weight=constraint.weight,
                expected_minutes=constraint.max_minutes,
            ))
            return violations

        trace_start = events[0].timestamp_min
        trace_end = events[-1].timestamp_min
        trace_duration = trace_end - trace_start

        if trace_duration <= 0:
            # Single-point trace: just check total count
            if len(source_times) < constraint.min_count:
                violations.append(TemporalViolation(
                    constraint_id=constraint.constraint_id,
                    constraint_type=constraint.constraint_type,
                    detail=f"'{constraint.source_activity}' count {len(source_times)} < {constraint.min_count}",
                    severity=constraint.severity,
                    weight=constraint.weight,
                ))
            return violations

        # Sliding window with 50% overlap
        window = constraint.max_minutes
        step = window / 2.0
        window_start = trace_start

        while window_start < trace_end:
            window_end = window_start + window
            count = sum(1 for t in source_times if window_start <= t < window_end)
            if count < constraint.min_count:
                violations.append(TemporalViolation(
                    constraint_id=constraint.constraint_id,
                    constraint_type=constraint.constraint_type,
                    detail=(f"'{constraint.source_activity}' count {count} < {constraint.min_count} "
                            f"in window [{window_start:.1f}, {window_end:.1f})"),
                    severity=constraint.severity,
                    weight=constraint.weight,
                    expected_minutes=window,
                    actual_minutes=window_start,
                ))
                break  # Report first violation only
            window_start += step

        return violations

    def _check_duration(
        self, events: List[ActivityEvent], constraint: TemporalConstraint
    ) -> List[TemporalViolation]:
        """Check consecutive span of source_activity >= min_minutes."""
        violations: List[TemporalViolation] = []
        if not constraint.source_activity or constraint.min_minutes is None:
            return violations

        index = self._build_activity_index(events)
        source_events = index.get(constraint.source_activity, [])

        if not source_events:
            violations.append(TemporalViolation(
                constraint_id=constraint.constraint_id,
                constraint_type=constraint.constraint_type,
                detail=f"'{constraint.source_activity}' never occurred (need {constraint.min_minutes:.1f}min span)",
                severity=constraint.severity,
                weight=constraint.weight,
                expected_minutes=constraint.min_minutes,
                actual_minutes=0.0,
            ))
            return violations

        # Find longest consecutive span
        max_span = 0.0
        span_start = source_events[0][1].timestamp_min
        prev_time = span_start

        for i in range(1, len(source_events)):
            curr_time = source_events[i][1].timestamp_min
            gap = curr_time - prev_time
            if gap > self._CONSECUTIVE_GAP_MINUTES:
                # Gap too large, end current span
                span_duration = prev_time - span_start
                max_span = max(max_span, span_duration)
                span_start = curr_time
            prev_time = curr_time

        # Final span
        final_span = prev_time - span_start
        max_span = max(max_span, final_span)

        if max_span < constraint.min_minutes:
            overshoot = constraint.min_minutes - max_span
            weight = self._compute_graduated_weight(
                constraint.weight, overshoot, constraint.min_minutes
            )
            violations.append(TemporalViolation(
                constraint_id=constraint.constraint_id,
                constraint_type=constraint.constraint_type,
                detail=(f"'{constraint.source_activity}' max span {max_span:.1f}min "
                        f"< required {constraint.min_minutes:.1f}min"),
                severity=constraint.severity,
                weight=weight,
                expected_minutes=constraint.min_minutes,
                actual_minutes=max_span,
                overshoot_minutes=overshoot,
            ))

        return violations

    def _check_deadline_chain(
        self, events: List[ActivityEvent], constraint: TemporalConstraint
    ) -> List[TemporalViolation]:
        """Check chain_activities occur in order with chained deadlines."""
        violations: List[TemporalViolation] = []
        if not constraint.chain_activities or not constraint.chain_deadlines:
            return violations

        if len(constraint.chain_deadlines) < len(constraint.chain_activities) - 1:
            return violations  # Invalid constraint definition

        index = self._build_activity_index(events)

        # Find first occurrence of chain start
        first_activity = constraint.chain_activities[0]
        first_events = index.get(first_activity, [])
        if not first_events:
            violations.append(TemporalViolation(
                constraint_id=constraint.constraint_id,
                constraint_type=constraint.constraint_type,
                detail=f"Chain start '{first_activity}' never occurred",
                severity=constraint.severity,
                weight=constraint.weight,
            ))
            return violations

        anchor_idx, anchor_event = first_events[0]
        anchor_time = anchor_event.timestamp_min

        for step in range(1, len(constraint.chain_activities)):
            activity = constraint.chain_activities[step]
            deadline = constraint.chain_deadlines[step - 1]
            step_events = index.get(activity, [])

            # Find first occurrence after anchor
            found = False
            for evt_idx, evt in step_events:
                if evt.timestamp_min >= anchor_time:
                    delay = evt.timestamp_min - anchor_time
                    if delay > deadline:
                        overshoot = delay - deadline
                        weight = self._compute_graduated_weight(
                            constraint.weight, overshoot, deadline
                        )
                        violations.append(TemporalViolation(
                            constraint_id=constraint.constraint_id,
                            constraint_type=constraint.constraint_type,
                            detail=(f"Chain step {step}: '{activity}' at {delay:.1f}min "
                                    f"> {deadline:.1f}min deadline from '{constraint.chain_activities[step-1]}'"),
                            severity=constraint.severity,
                            weight=weight,
                            expected_minutes=deadline,
                            actual_minutes=delay,
                            violating_event_index=evt_idx,
                            source_event_index=anchor_idx,
                            overshoot_minutes=overshoot,
                        ))
                    anchor_time = evt.timestamp_min
                    anchor_idx = evt_idx
                    found = True
                    break

            if not found:
                violations.append(TemporalViolation(
                    constraint_id=constraint.constraint_id,
                    constraint_type=constraint.constraint_type,
                    detail=f"Chain broken at step {step}: '{activity}' never occurred",
                    severity=constraint.severity,
                    weight=constraint.weight,
                    expected_minutes=deadline,
                    source_event_index=anchor_idx,
                ))
                break  # Chain broken, stop checking

        return violations

    def _check_frequency(
        self, events: List[ActivityEvent], constraint: TemporalConstraint
    ) -> List[TemporalViolation]:
        """Check occurrence count within [min_count, max_count] per window."""
        violations: List[TemporalViolation] = []
        if not constraint.source_activity:
            return violations

        index = self._build_activity_index(events)
        source_events = index.get(constraint.source_activity, [])

        # Determine window
        if constraint.max_minutes is not None and events:
            trace_start = events[0].timestamp_min
            window_end = trace_start + constraint.max_minutes
            count = sum(1 for _, e in source_events
                        if trace_start <= e.timestamp_min < window_end)
        else:
            count = len(source_events)

        # Check min_count
        if constraint.min_count is not None and count < constraint.min_count:
            violations.append(TemporalViolation(
                constraint_id=constraint.constraint_id,
                constraint_type=constraint.constraint_type,
                detail=(f"'{constraint.source_activity}' count {count} "
                        f"< required minimum {constraint.min_count}"),
                severity=constraint.severity,
                weight=constraint.weight,
                expected_minutes=constraint.max_minutes,
            ))

        # Check max_count
        if constraint.max_count is not None and count > constraint.max_count:
            violations.append(TemporalViolation(
                constraint_id=constraint.constraint_id,
                constraint_type=constraint.constraint_type,
                detail=(f"'{constraint.source_activity}' count {count} "
                        f"> allowed maximum {constraint.max_count}"),
                severity=constraint.severity,
                weight=constraint.weight,
                expected_minutes=constraint.max_minutes,
            ))

        return violations

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_graduated_weight(
        self, base_weight: float, overshoot: float, window: float
    ) -> float:
        """Apply graduated timing penalty from config."""
        mode = self._config.timing_penalty_mode
        if mode == "binary":
            return base_weight

        grace = self._config.grace_period_minutes
        effective_overshoot = overshoot - grace
        if effective_overshoot <= 0:
            return 0.0

        if mode == "linear":
            scale = min(
                effective_overshoot / max(window, 1.0),
                self._config.max_penalty_multiplier,
            )
            return base_weight * max(scale, 0.1)

        if mode == "logarithmic":
            half_life = max(self._config.half_life_minutes, 1.0)
            scale = min(
                math.log2(1.0 + effective_overshoot / half_life),
                self._config.max_penalty_multiplier,
            )
            return base_weight * max(scale, 0.1)

        return base_weight

    def _build_activity_index(
        self, events: List[ActivityEvent]
    ) -> Dict[str, List[Tuple[int, ActivityEvent]]]:
        """Build name -> [(index, event)] index for fast lookup."""
        index: Dict[str, List[Tuple[int, ActivityEvent]]] = {}
        for i, event in enumerate(events):
            key = event.name
            if key not in index:
                index[key] = []
            index[key].append((i, event))
        return index

    def _compute_margin_for_constraint(
        self,
        constraint: TemporalConstraint,
        events: List[ActivityEvent],
        index: Dict[str, List[Tuple[int, ActivityEvent]]],
    ) -> Optional[float]:
        """Compute timing margin for a single constraint."""
        if constraint.constraint_type == TemporalConstraintType.BOUNDED_RESPONSE:
            return self._margin_bounded_response(constraint, events, index)
        elif constraint.constraint_type == TemporalConstraintType.MAX_DELAY:
            return self._margin_max_delay(constraint, events, index)
        return None

    def _margin_bounded_response(
        self,
        constraint: TemporalConstraint,
        events: List[ActivityEvent],
        index: Dict[str, List[Tuple[int, ActivityEvent]]],
    ) -> Optional[float]:
        """Margin for bounded response: min margin across all source events."""
        if not constraint.source_activity or not constraint.target_activity:
            return None
        max_min = constraint.max_minutes
        if max_min is None:
            return None

        source_events = index.get(constraint.source_activity, [])
        target_events = index.get(constraint.target_activity, [])
        if not source_events:
            return None

        min_margin: Optional[float] = None
        for _, src in source_events:
            best_delay: Optional[float] = None
            for _, tgt in target_events:
                if tgt.timestamp_min > src.timestamp_min:
                    best_delay = tgt.timestamp_min - src.timestamp_min
                    break
            if best_delay is None:
                margin = -max_min  # Never responded
            else:
                margin = max_min - best_delay

            if min_margin is None or margin < min_margin:
                min_margin = margin

        return min_margin

    def _margin_max_delay(
        self,
        constraint: TemporalConstraint,
        events: List[ActivityEvent],
        index: Dict[str, List[Tuple[int, ActivityEvent]]],
    ) -> Optional[float]:
        """Margin for max delay: deadline - actual delay."""
        if not constraint.target_activity or constraint.max_minutes is None:
            return None
        if not events:
            return -constraint.max_minutes

        target_events = index.get(constraint.target_activity, [])
        if not target_events:
            return -constraint.max_minutes

        trace_start = events[0].timestamp_min
        first_target = target_events[0][1]
        delay = first_target.timestamp_min - trace_start
        return constraint.max_minutes - delay
