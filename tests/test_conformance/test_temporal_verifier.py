"""Tests for temporal constraint verification."""
import pytest

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.conformance.temporal_verifier import (
    TemporalConstraint,
    TemporalConstraintType,
    TemporalSeverity,
    TemporalVerificationConfig,
    TemporalVerificationResult,
    TemporalVerifier,
    TemporalViolation,
)


def _make_event(name, timestamp_min=0.0):
    """Create an ActivityEvent for testing."""
    return ActivityEvent(name=name, timestamp_min=timestamp_min, raw_event={})


def _make_events(*specs):
    """Create multiple events from (name, timestamp) tuples."""
    return [_make_event(name, ts) for name, ts in specs]


# ==================================================================
# TestTemporalConstraintType
# ==================================================================

class TestTemporalConstraintType:
    """Test enum values and constraint construction."""

    def test_all_constraint_types_defined(self):
        types = list(TemporalConstraintType)
        assert len(types) == 6

    def test_bounded_response_value(self):
        assert TemporalConstraintType.BOUNDED_RESPONSE == "bounded_response"

    def test_max_delay_value(self):
        assert TemporalConstraintType.MAX_DELAY == "max_delay"

    def test_periodic_value(self):
        assert TemporalConstraintType.PERIODIC == "periodic"

    def test_constraint_default_values(self):
        c = TemporalConstraint(
            constraint_id="test",
            constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
        )
        assert c.weight == 1.0
        assert c.severity == TemporalSeverity.MEDIUM
        assert c.source_activity is None
        assert c.chain_activities == []
        assert c.chain_deadlines == []

    def test_severity_enum_values(self):
        assert TemporalSeverity.INFO == "info"
        assert TemporalSeverity.CRITICAL == "critical"


# ==================================================================
# TestBoundedResponse
# ==================================================================

class TestBoundedResponse:
    """Test BOUNDED_RESPONSE verification."""

    def test_within_bounds_no_violation(self):
        events = _make_events(("ORDER_LAB", 0.0), ("RESULT_LAB", 25.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
            source_activity="ORDER_LAB",
            target_activity="RESULT_LAB",
            max_minutes=30.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert passed
        assert len(violations) == 0

    def test_exceeds_max_generates_violation(self):
        events = _make_events(("ORDER_LAB", 0.0), ("RESULT_LAB", 45.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
            source_activity="ORDER_LAB",
            target_activity="RESULT_LAB",
            max_minutes=30.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert len(violations) == 1
        assert violations[0].overshoot_minutes == pytest.approx(15.0)

    def test_below_min_strict_mode_violation(self):
        events = _make_events(("ORDER_LAB", 0.0), ("RESULT_LAB", 2.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
            source_activity="ORDER_LAB",
            target_activity="RESULT_LAB",
            min_minutes=5.0,
            max_minutes=30.0,
        )
        config = TemporalVerificationConfig(strict_bounds=True)
        verifier = TemporalVerifier(config)
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert "too early" in violations[0].detail

    def test_below_min_non_strict_no_violation(self):
        events = _make_events(("ORDER_LAB", 0.0), ("RESULT_LAB", 2.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
            source_activity="ORDER_LAB",
            target_activity="RESULT_LAB",
            min_minutes=5.0,
            max_minutes=30.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert passed

    def test_missing_target_full_penalty(self):
        events = _make_events(("ORDER_LAB", 0.0), ("OTHER_ACTION", 10.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
            source_activity="ORDER_LAB",
            target_activity="RESULT_LAB",
            max_minutes=30.0,
            weight=2.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert violations[0].weight == 2.0
        assert "No 'RESULT_LAB' found" in violations[0].detail

    def test_multiple_sources_checked_independently(self):
        events = _make_events(
            ("ORDER_LAB", 0.0),
            ("ORDER_LAB", 10.0),
            ("RESULT_LAB", 50.0),
        )
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
            source_activity="ORDER_LAB",
            target_activity="RESULT_LAB",
            max_minutes=30.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        # First ORDER_LAB at t=0 -> RESULT_LAB at t=50 (50 > 30, violation)
        assert any(v.overshoot_minutes == pytest.approx(20.0) for v in violations)

    def test_graduated_weight_linear(self):
        events = _make_events(("A", 0.0), ("B", 60.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
            source_activity="A",
            target_activity="B",
            max_minutes=30.0,
            weight=1.0,
        )
        config = TemporalVerificationConfig(timing_penalty_mode="linear")
        verifier = TemporalVerifier(config)
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        # overshoot=30, window=30, scale=30/30=1.0, weight=1.0*1.0=1.0
        assert violations[0].weight == pytest.approx(1.0)

    def test_no_source_no_violation(self):
        events = _make_events(("OTHER", 0.0), ("B", 10.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
            source_activity="A",
            target_activity="B",
            max_minutes=30.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert passed


# ==================================================================
# TestMaxDelay
# ==================================================================

class TestMaxDelay:
    """Test MAX_DELAY (absolute deadline) verification."""

    def test_within_deadline_no_violation(self):
        events = _make_events(("START", 0.0), ("TARGET", 50.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.MAX_DELAY,
            target_activity="TARGET",
            max_minutes=60.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert passed

    def test_exceeds_deadline_violation(self):
        events = _make_events(("START", 0.0), ("TARGET", 75.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.MAX_DELAY,
            target_activity="TARGET",
            max_minutes=60.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert violations[0].overshoot_minutes == pytest.approx(15.0)

    def test_missing_activity_violation(self):
        events = _make_events(("START", 0.0), ("OTHER", 10.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.MAX_DELAY,
            target_activity="TARGET",
            max_minutes=60.0,
            weight=3.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert violations[0].weight == 3.0
        assert "never performed" in violations[0].detail

    def test_graduated_weight_on_overshoot(self):
        events = _make_events(("START", 0.0), ("TARGET", 90.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.MAX_DELAY,
            target_activity="TARGET",
            max_minutes=60.0,
            weight=1.0,
        )
        config = TemporalVerificationConfig(timing_penalty_mode="linear")
        verifier = TemporalVerifier(config)
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        # overshoot=30, window=60, scale=30/60=0.5, weight=1.0*0.5=0.5
        assert violations[0].weight == pytest.approx(0.5)

    def test_exact_deadline_no_violation(self):
        events = _make_events(("START", 0.0), ("TARGET", 60.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.MAX_DELAY,
            target_activity="TARGET",
            max_minutes=60.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert passed

    def test_empty_trace_violation(self):
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.MAX_DELAY,
            target_activity="TARGET",
            max_minutes=60.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single([], constraint)
        assert not passed


# ==================================================================
# TestPeriodicAndFrequency
# ==================================================================

class TestPeriodicAndFrequency:
    """Test PERIODIC and FREQUENCY constraint types."""

    def test_periodic_satisfied_enough_occurrences(self):
        events = _make_events(
            ("MONITOR", 0.0), ("MONITOR", 10.0), ("MONITOR", 20.0),
            ("MONITOR", 30.0), ("MONITOR", 40.0),
        )
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.PERIODIC,
            source_activity="MONITOR",
            min_count=2,
            max_minutes=30.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert passed

    def test_periodic_violated_gap_in_window(self):
        events = _make_events(
            ("MONITOR", 0.0), ("MONITOR", 5.0),
            ("OTHER", 30.0),  # gap
            ("MONITOR", 80.0),
        )
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.PERIODIC,
            source_activity="MONITOR",
            min_count=2,
            max_minutes=30.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        # Window [15, 45) has 0 MONITOR events -> violation
        assert not passed

    def test_periodic_empty_source(self):
        events = _make_events(("OTHER", 0.0), ("OTHER", 30.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.PERIODIC,
            source_activity="MONITOR",
            min_count=2,
            max_minutes=30.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert "never occurred" in violations[0].detail

    def test_frequency_min_count_violation(self):
        events = _make_events(("ACTION", 0.0), ("OTHER", 10.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.FREQUENCY,
            source_activity="ACTION",
            min_count=3,
            max_minutes=60.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert "< required minimum 3" in violations[0].detail

    def test_frequency_max_count_violation(self):
        events = _make_events(
            ("ACTION", 0.0), ("ACTION", 5.0), ("ACTION", 10.0),
            ("ACTION", 15.0), ("ACTION", 20.0),
        )
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.FREQUENCY,
            source_activity="ACTION",
            max_count=3,
            max_minutes=60.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert "> allowed maximum 3" in violations[0].detail

    def test_frequency_within_bounds_no_violation(self):
        events = _make_events(
            ("ACTION", 0.0), ("ACTION", 10.0), ("ACTION", 20.0),
        )
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.FREQUENCY,
            source_activity="ACTION",
            min_count=2,
            max_count=5,
            max_minutes=60.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert passed

    def test_frequency_disabled_by_config(self):
        events = _make_events(("ACTION", 0.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.FREQUENCY,
            source_activity="ACTION",
            min_count=5,
        )
        config = TemporalVerificationConfig(enable_frequency_checks=False)
        verifier = TemporalVerifier(config)
        result = verifier.verify(events, [constraint])
        assert result.skipped_count == 1
        assert result.violated_count == 0

    def test_periodic_disabled_by_config(self):
        events = _make_events(("MONITOR", 0.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.PERIODIC,
            source_activity="MONITOR",
            min_count=5,
            max_minutes=30.0,
        )
        config = TemporalVerificationConfig(enable_frequency_checks=False)
        verifier = TemporalVerifier(config)
        result = verifier.verify(events, [constraint])
        assert result.skipped_count == 1


# ==================================================================
# TestDuration
# ==================================================================

class TestDuration:
    """Test DURATION constraint verification."""

    def test_sufficient_duration_no_violation(self):
        events = _make_events(
            ("INFUSION", 0.0), ("INFUSION", 5.0),
            ("INFUSION", 10.0), ("INFUSION", 15.0),
        )
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.DURATION,
            source_activity="INFUSION",
            min_minutes=10.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert passed

    def test_insufficient_duration_violation(self):
        events = _make_events(
            ("INFUSION", 0.0), ("INFUSION", 3.0),
        )
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.DURATION,
            source_activity="INFUSION",
            min_minutes=10.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert violations[0].actual_minutes == pytest.approx(3.0)

    def test_non_consecutive_events_gap_detection(self):
        events = _make_events(
            ("INFUSION", 0.0), ("INFUSION", 3.0),
            ("OTHER", 10.0),  # gap > 5 min from INFUSION at 3.0
            ("INFUSION", 20.0), ("INFUSION", 22.0),
        )
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.DURATION,
            source_activity="INFUSION",
            min_minutes=10.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        # Max span is max(3.0, 2.0) = 3.0 < 10.0
        assert not passed

    def test_single_event_zero_duration(self):
        events = _make_events(("INFUSION", 5.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.DURATION,
            source_activity="INFUSION",
            min_minutes=10.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert violations[0].actual_minutes == pytest.approx(0.0)

    def test_missing_activity_violation(self):
        events = _make_events(("OTHER", 0.0), ("OTHER", 10.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.DURATION,
            source_activity="INFUSION",
            min_minutes=10.0,
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert "never occurred" in violations[0].detail


# ==================================================================
# TestDeadlineChain
# ==================================================================

class TestDeadlineChain:
    """Test DEADLINE_CHAIN verification."""

    def test_chain_all_within_deadlines_no_violation(self):
        events = _make_events(
            ("TRIAGE", 0.0), ("ASSESS", 10.0), ("TREAT", 25.0),
        )
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.DEADLINE_CHAIN,
            chain_activities=["TRIAGE", "ASSESS", "TREAT"],
            chain_deadlines=[15.0, 20.0],
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert passed

    def test_chain_broken_at_step_2(self):
        events = _make_events(
            ("TRIAGE", 0.0), ("ASSESS", 10.0), ("TREAT", 50.0),
        )
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.DEADLINE_CHAIN,
            chain_activities=["TRIAGE", "ASSESS", "TREAT"],
            chain_deadlines=[15.0, 20.0],
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        # TREAT at t=50 - ASSESS at t=10 = 40 > 20
        assert violations[0].overshoot_minutes == pytest.approx(20.0)

    def test_chain_missing_first_activity(self):
        events = _make_events(("ASSESS", 10.0), ("TREAT", 25.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.DEADLINE_CHAIN,
            chain_activities=["TRIAGE", "ASSESS", "TREAT"],
            chain_deadlines=[15.0, 20.0],
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert "never occurred" in violations[0].detail

    def test_chain_missing_middle_activity(self):
        events = _make_events(("TRIAGE", 0.0), ("TREAT", 25.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.DEADLINE_CHAIN,
            chain_activities=["TRIAGE", "ASSESS", "TREAT"],
            chain_deadlines=[15.0, 20.0],
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        assert "Chain broken" in violations[0].detail

    def test_chain_disabled_by_config(self):
        events = _make_events(("TRIAGE", 0.0))
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.DEADLINE_CHAIN,
            chain_activities=["TRIAGE", "ASSESS"],
            chain_deadlines=[5.0],
        )
        config = TemporalVerificationConfig(enable_chain_checks=False)
        verifier = TemporalVerifier(config)
        result = verifier.verify(events, [constraint])
        assert result.skipped_count == 1

    def test_three_step_chain_partial_violation(self):
        events = _make_events(
            ("A", 0.0), ("B", 8.0), ("C", 12.0), ("D", 50.0),
        )
        constraint = TemporalConstraint(
            constraint_id="c1",
            constraint_type=TemporalConstraintType.DEADLINE_CHAIN,
            chain_activities=["A", "B", "C", "D"],
            chain_deadlines=[10.0, 10.0, 10.0],
        )
        verifier = TemporalVerifier()
        passed, violations = verifier.verify_single(events, constraint)
        assert not passed
        # A->B: 8 <= 10 OK, B->C: 4 <= 10 OK, C->D: 38 > 10 violation
        assert violations[0].overshoot_minutes == pytest.approx(28.0)


# ==================================================================
# TestConvertSoftConstraint
# ==================================================================

class TestConvertSoftConstraint:
    """Test conversion from existing SoftConstraint."""

    def test_response_within_converts(self):
        class MockSC:
            template = type("T", (), {"value": "response_within"})()
            constraint_id = "sc_1"
            A = "ORDER_LAB"
            B = "RESULT_LAB"
            window_minutes = 60.0
            weight = 1.5
            guard = None
            evidence_level = "1B"
            rationale = "Test rationale"
            description = None

        verifier = TemporalVerifier()
        tc = verifier.convert_soft_constraint(MockSC())
        assert tc is not None
        assert tc.constraint_type == TemporalConstraintType.BOUNDED_RESPONSE
        assert tc.source_activity == "ORDER_LAB"
        assert tc.target_activity == "RESULT_LAB"
        assert tc.min_minutes == 0.0
        assert tc.max_minutes == 60.0
        assert tc.weight == 1.5
        assert tc.evidence_level == "1B"

    def test_existence_returns_none(self):
        class MockSC:
            template = type("T", (), {"value": "existence"})()
            constraint_id = "sc_2"
            A = "ACTION"
            B = None
            window_minutes = None
            weight = 1.0
            guard = None
            evidence_level = None
            rationale = None
            description = None

        verifier = TemporalVerifier()
        tc = verifier.convert_soft_constraint(MockSC())
        assert tc is None

    def test_preserves_weight_and_guard(self):
        class MockSC:
            template = type("T", (), {"value": "response_within"})()
            constraint_id = "sc_3"
            A = "A"
            B = "B"
            window_minutes = 30.0
            weight = 2.5
            guard = "flag_hypotensive"
            evidence_level = None
            rationale = None
            description = "Test desc"

        verifier = TemporalVerifier()
        tc = verifier.convert_soft_constraint(MockSC())
        assert tc is not None
        assert tc.weight == 2.5
        assert tc.condition == "flag_hypotensive"

    def test_no_window_returns_none(self):
        class MockSC:
            template = type("T", (), {"value": "response_within"})()
            constraint_id = "sc_4"
            A = "A"
            B = "B"
            window_minutes = None
            weight = 1.0
            guard = None
            evidence_level = None
            rationale = None
            description = None

        verifier = TemporalVerifier()
        tc = verifier.convert_soft_constraint(MockSC())
        assert tc is None

    def test_no_template_returns_none(self):
        class MockSC:
            constraint_id = "sc_5"

        verifier = TemporalVerifier()
        tc = verifier.convert_soft_constraint(MockSC())
        assert tc is None


# ==================================================================
# TestVerificationResult
# ==================================================================

class TestVerificationResult:
    """Test aggregation and result computation."""

    def test_all_satisfied_perfect_score(self):
        events = _make_events(("A", 0.0), ("B", 10.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
            ),
        ]
        verifier = TemporalVerifier()
        result = verifier.verify(events, constraints)
        assert result.satisfied_count == 1
        assert result.violated_count == 0
        assert result.total_penalty == 0.0

    def test_mixed_violations_aggregated(self):
        events = _make_events(("A", 0.0), ("B", 50.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
                weight=1.0,
            ),
            TemporalConstraint(
                constraint_id="c2",
                constraint_type=TemporalConstraintType.MAX_DELAY,
                target_activity="B",
                max_minutes=60.0,
            ),
        ]
        verifier = TemporalVerifier()
        result = verifier.verify(events, constraints)
        assert result.satisfied_count == 1  # c2 OK
        assert result.violated_count == 1  # c1 violated
        assert result.total_penalty > 0

    def test_skipped_constraints_not_counted(self):
        events = _make_events(("A", 0.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
                condition="flag_active",
            ),
        ]
        verifier = TemporalVerifier()
        result = verifier.verify(events, constraints, derived_flags={"flag_active": False})
        assert result.skipped_count == 1
        assert result.satisfied_count == 0
        assert result.violated_count == 0

    def test_guard_condition_met_evaluates(self):
        events = _make_events(("A", 0.0), ("B", 50.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
                condition="flag_active",
            ),
        ]
        verifier = TemporalVerifier()
        result = verifier.verify(events, constraints, derived_flags={"flag_active": True})
        assert result.violated_count == 1

    def test_timing_margins_computed(self):
        events = _make_events(("A", 0.0), ("B", 20.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
            ),
        ]
        verifier = TemporalVerifier()
        result = verifier.verify(events, constraints)
        assert "c1" in result.timing_margins
        assert result.timing_margins["c1"] == pytest.approx(10.0)

    def test_total_penalty_sum_of_weights(self):
        events = _make_events(("A", 0.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.MAX_DELAY,
                target_activity="MISSING_1",
                max_minutes=60.0,
                weight=1.5,
            ),
            TemporalConstraint(
                constraint_id="c2",
                constraint_type=TemporalConstraintType.MAX_DELAY,
                target_activity="MISSING_2",
                max_minutes=60.0,
                weight=2.5,
            ),
        ]
        verifier = TemporalVerifier()
        result = verifier.verify(events, constraints)
        assert result.total_penalty == pytest.approx(4.0)

    def test_verification_disabled(self):
        events = _make_events(("A", 0.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.MAX_DELAY,
                target_activity="MISSING",
                max_minutes=60.0,
            ),
        ]
        config = TemporalVerificationConfig(enable_verification=False)
        verifier = TemporalVerifier(config)
        result = verifier.verify(events, constraints)
        assert result.skipped_count == 1
        assert result.violated_count == 0
