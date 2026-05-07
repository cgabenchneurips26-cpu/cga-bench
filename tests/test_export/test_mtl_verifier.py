"""Tests for MTL (Metric Temporal Logic) bounded operators.

Verifies time-bounded temporal formulas: F[a,b], G[a,b], U[a,b]
and clinical property library functions: response_within, existence_within, etc.
"""
import pytest

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.export.temporal_logic_verifier import (
    LTLVerifier,
    TLFormula,
    TemporalOp,
    atom,
    not_,
    and_,
    implies,
    globally,
    finally_within,
    globally_within,
    until_within,
    response_within_property,
    existence_within_property,
    absence_after_property,
    bounded_response_chain_property,
)


def _timed_trace(*events):
    """Create timed trace: events are (name, timestamp_min) tuples."""
    return [
        ActivityEvent(name=name, timestamp_min=t, raw_event={})
        for name, t in events
    ]


# ============================================
# Test: F[lo,hi] (Finally Bounded)
# ============================================

class TestFinallyBounded:
    def test_satisfied_within_window(self):
        """Event occurs within time window → satisfied."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("B", 30.0))
        formula = finally_within(atom("B"), 0.0, 60.0)
        assert v.verify(trace, formula).satisfied is True

    def test_violated_outside_window(self):
        """Event occurs after time window → violated."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("B", 90.0))
        formula = finally_within(atom("B"), 0.0, 60.0)
        assert v.verify(trace, formula).satisfied is False

    def test_exactly_at_upper_bound(self):
        """Event at exactly upper bound → satisfied (inclusive)."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("B", 60.0))
        formula = finally_within(atom("B"), 0.0, 60.0)
        assert v.verify(trace, formula).satisfied is True

    def test_before_lower_bound(self):
        """Event occurs before lower bound → not counted."""
        v = LTLVerifier()
        # B at time 5 is before [10, 60] window
        trace = _timed_trace(("B", 5.0), ("A", 20.0))
        formula = finally_within(atom("B"), 10.0, 60.0)
        assert v.verify(trace, formula).satisfied is False

    def test_multiple_events_first_in_window(self):
        """First matching event in window → satisfied."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("B", 25.0), ("B", 90.0))
        formula = finally_within(atom("B"), 0.0, 60.0)
        assert v.verify(trace, formula).satisfied is True

    def test_empty_trace(self):
        """Empty trace → F[] is never satisfied."""
        v = LTLVerifier()
        formula = finally_within(atom("B"), 0.0, 60.0)
        assert v.verify([], formula).satisfied is False

    def test_event_not_present(self):
        """Required event absent → violated."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("C", 30.0))
        formula = finally_within(atom("B"), 0.0, 60.0)
        assert v.verify(trace, formula).satisfied is False


# ============================================
# Test: G[lo,hi] (Globally Bounded)
# ============================================

class TestGloballyBounded:
    def test_all_in_window_satisfy(self):
        """All events in window satisfy → satisfied."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("A", 10.0), ("A", 20.0), ("B", 70.0))
        formula = globally_within(atom("A"), 0.0, 30.0)
        assert v.verify(trace, formula).satisfied is True

    def test_violation_in_window(self):
        """Non-A event within window → violated."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("B", 15.0), ("A", 25.0))
        formula = globally_within(atom("A"), 0.0, 30.0)
        assert v.verify(trace, formula).satisfied is False

    def test_violation_outside_window_ok(self):
        """Non-A event outside window doesn't matter."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("A", 20.0), ("B", 50.0))
        formula = globally_within(atom("A"), 0.0, 30.0)
        assert v.verify(trace, formula).satisfied is True

    def test_negation_in_window(self):
        """G[0,60](¬NITRATES): no nitrates in first 60 min."""
        v = LTLVerifier()
        # Good: no nitrates
        trace = _timed_trace(("ASSESS", 0.0), ("TREAT", 30.0))
        formula = globally_within(not_(atom("NITRATES")), 0.0, 60.0)
        assert v.verify(trace, formula).satisfied is True

        # Bad: nitrates at 30 min
        trace2 = _timed_trace(("ASSESS", 0.0), ("NITRATES", 30.0))
        assert v.verify(trace2, formula).satisfied is False

    def test_empty_window(self):
        """No events in window → vacuously true."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("B", 100.0))
        # Window [50, 80] has no events
        formula = globally_within(atom("X"), 50.0, 80.0)
        assert v.verify(trace, formula).satisfied is True


# ============================================
# Test: U[lo,hi] (Until Bounded)
# ============================================

class TestUntilBounded:
    def test_psi_within_window(self):
        """ψ holds within window, φ holds before → satisfied."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("A", 10.0), ("B", 30.0))
        formula = until_within(atom("A"), atom("B"), 0.0, 60.0)
        assert v.verify(trace, formula).satisfied is True

    def test_psi_after_window(self):
        """ψ holds after window → violated."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("A", 10.0), ("B", 90.0))
        formula = until_within(atom("A"), atom("B"), 0.0, 60.0)
        assert v.verify(trace, formula).satisfied is False

    def test_phi_broken_before_psi(self):
        """φ fails before ψ → violated."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("C", 10.0), ("B", 30.0))
        formula = until_within(atom("A"), atom("B"), 0.0, 60.0)
        assert v.verify(trace, formula).satisfied is False

    def test_immediate_psi(self):
        """ψ immediately at pos → satisfied (trivial)."""
        v = LTLVerifier()
        trace = _timed_trace(("B", 0.0), ("A", 10.0))
        formula = until_within(atom("A"), atom("B"), 0.0, 60.0)
        assert v.verify(trace, formula).satisfied is True


# ============================================
# Test: response_within_property
# ============================================

class TestResponseWithin:
    def test_antibiotics_within_60min(self):
        """SSC 2021: Antibiotics within 60 min of blood culture."""
        v = LTLVerifier()
        prop = response_within_property("CULTURE", "ANTIBIOTICS", 60.0)

        # Good: antibiotics at 45 min after culture at 10 min (35 min gap)
        trace = _timed_trace(
            ("ASSESS", 0.0), ("CULTURE", 10.0), ("ANTIBIOTICS", 45.0)
        )
        assert v.verify(trace, prop.formula).satisfied is True

    def test_antibiotics_delayed(self):
        """Antibiotics 90 min after culture → violated."""
        v = LTLVerifier()
        prop = response_within_property("CULTURE", "ANTIBIOTICS", 60.0)

        trace = _timed_trace(
            ("CULTURE", 10.0), ("ANTIBIOTICS", 100.0)
        )
        assert v.verify(trace, prop.formula).satisfied is False

    def test_no_trigger_vacuously_true(self):
        """No trigger event → vacuously satisfied (G(false → ...) = true)."""
        v = LTLVerifier()
        prop = response_within_property("CULTURE", "ANTIBIOTICS", 60.0)
        trace = _timed_trace(("ASSESS", 0.0), ("TREAT", 30.0))
        assert v.verify(trace, prop.formula).satisfied is True

    def test_multiple_triggers(self):
        """Each trigger must have response within window."""
        v = LTLVerifier()
        prop = response_within_property("TRIGGER", "RESPONSE", 30.0)

        # First trigger gets response, second doesn't
        trace = _timed_trace(
            ("TRIGGER", 0.0), ("RESPONSE", 20.0),
            ("TRIGGER", 50.0),  # No response within 30 min
        )
        assert v.verify(trace, prop.formula).satisfied is False

    def test_multiple_triggers_all_responded(self):
        """All triggers get timely response → satisfied."""
        v = LTLVerifier()
        prop = response_within_property("TRIGGER", "RESPONSE", 30.0)

        trace = _timed_trace(
            ("TRIGGER", 0.0), ("RESPONSE", 20.0),
            ("TRIGGER", 50.0), ("RESPONSE", 70.0),
        )
        assert v.verify(trace, prop.formula).satisfied is True


# ============================================
# Test: existence_within_property
# ============================================

class TestExistenceWithin:
    def test_ecg_within_10min(self):
        """AHA: ECG within 10 minutes of arrival."""
        v = LTLVerifier()
        prop = existence_within_property("ORDER_ECG", 10.0)

        # ECG at 8 min → satisfied
        trace = _timed_trace(("ASSESS", 0.0), ("ORDER_ECG", 8.0))
        assert v.verify(trace, prop.formula).satisfied is True

    def test_ecg_delayed(self):
        """ECG at 15 min → violated."""
        v = LTLVerifier()
        prop = existence_within_property("ORDER_ECG", 10.0)
        trace = _timed_trace(("ASSESS", 0.0), ("ORDER_ECG", 15.0))
        assert v.verify(trace, prop.formula).satisfied is False

    def test_missing_entirely(self):
        """No ECG at all → violated."""
        v = LTLVerifier()
        prop = existence_within_property("ORDER_ECG", 10.0)
        trace = _timed_trace(("ASSESS", 0.0), ("TREAT", 5.0))
        assert v.verify(trace, prop.formula).satisfied is False


# ============================================
# Test: absence_after_property
# ============================================

class TestAbsenceAfter:
    def test_no_nitrates_after_rv_diagnosis(self):
        """RV infarct → no nitrates for 60 min."""
        v = LTLVerifier()
        prop = absence_after_property("DIAGNOSE_RV", "NITRATES", 60.0)

        # Good: no nitrates after RV diagnosis
        trace = _timed_trace(
            ("ASSESS", 0.0), ("DIAGNOSE_RV", 10.0), ("FLUID", 20.0)
        )
        assert v.verify(trace, prop.formula).satisfied is True

    def test_nitrates_within_window(self):
        """Nitrates 30 min after RV diagnosis → violated."""
        v = LTLVerifier()
        prop = absence_after_property("DIAGNOSE_RV", "NITRATES", 60.0)

        trace = _timed_trace(
            ("DIAGNOSE_RV", 10.0), ("NITRATES", 40.0)
        )
        assert v.verify(trace, prop.formula).satisfied is False

    def test_nitrates_after_window_ok(self):
        """Nitrates 90 min after RV diagnosis → allowed (outside window)."""
        v = LTLVerifier()
        prop = absence_after_property("DIAGNOSE_RV", "NITRATES", 60.0)

        trace = _timed_trace(
            ("DIAGNOSE_RV", 10.0), ("OTHER", 50.0), ("NITRATES", 100.0)
        )
        assert v.verify(trace, prop.formula).satisfied is True

    def test_no_trigger_vacuously_true(self):
        """No RV diagnosis → vacuously satisfied."""
        v = LTLVerifier()
        prop = absence_after_property("DIAGNOSE_RV", "NITRATES", 60.0)
        trace = _timed_trace(("ASSESS", 0.0), ("NITRATES", 30.0))
        assert v.verify(trace, prop.formula).satisfied is True


# ============================================
# Test: bounded_response_chain_property
# ============================================

class TestBoundedResponseChain:
    def test_full_chain_satisfied(self):
        """Culture → ABX within 60min → Reassess within 360min."""
        v = LTLVerifier()
        prop = bounded_response_chain_property(
            "CULTURE", "ABX", "REASSESS", 60.0, 360.0
        )
        trace = _timed_trace(
            ("CULTURE", 0.0), ("ABX", 30.0), ("REASSESS", 200.0)
        )
        assert v.verify(trace, prop.formula).satisfied is True

    def test_first_link_broken(self):
        """ABX 90 min after culture (>60) → violated."""
        v = LTLVerifier()
        prop = bounded_response_chain_property(
            "CULTURE", "ABX", "REASSESS", 60.0, 360.0
        )
        trace = _timed_trace(
            ("CULTURE", 0.0), ("ABX", 90.0), ("REASSESS", 200.0)
        )
        assert v.verify(trace, prop.formula).satisfied is False

    def test_second_link_broken(self):
        """Reassess 400 min after ABX (>360) → violated."""
        v = LTLVerifier()
        prop = bounded_response_chain_property(
            "CULTURE", "ABX", "REASSESS", 60.0, 360.0
        )
        trace = _timed_trace(
            ("CULTURE", 0.0), ("ABX", 30.0), ("REASSESS", 450.0)
        )
        assert v.verify(trace, prop.formula).satisfied is False

    def test_missing_middle(self):
        """No ABX → violated."""
        v = LTLVerifier()
        prop = bounded_response_chain_property(
            "CULTURE", "ABX", "REASSESS", 60.0, 360.0
        )
        trace = _timed_trace(
            ("CULTURE", 0.0), ("OTHER", 30.0), ("REASSESS", 200.0)
        )
        assert v.verify(trace, prop.formula).satisfied is False


# ============================================
# Test: Clinical Scenarios (MTL)
# ============================================

class TestMTLClinicalScenarios:
    def test_sepsis_golden_hour_compliant(self):
        """Compliant sepsis Hour-1 Bundle within time bounds."""
        v = LTLVerifier()
        # All within 1 hour
        trace = _timed_trace(
            ("ORDER_LACTATE", 5.0),
            ("ORDER_BLOOD_CULTURE", 8.0),
            ("GIVE_ANTIBIOTICS", 40.0),
            ("GIVE_CRYSTALLOID", 50.0),
            ("START_VASOPRESSOR", 55.0),
        )
        # Antibiotics within 60 min of cultures
        prop = response_within_property(
            "ORDER_BLOOD_CULTURE", "GIVE_ANTIBIOTICS", 60.0
        )
        assert v.verify(trace, prop.formula).satisfied is True

        # Lactate within 60 min of start
        prop2 = existence_within_property("ORDER_LACTATE", 60.0)
        assert v.verify(trace, prop2.formula).satisfied is True

    def test_sepsis_golden_hour_violated(self):
        """Sepsis Hour-1: antibiotics delayed to 90 min."""
        v = LTLVerifier()
        trace = _timed_trace(
            ("ORDER_BLOOD_CULTURE", 10.0),
            ("OTHER_ACTION", 30.0),
            ("GIVE_ANTIBIOTICS", 100.0),  # 90 min after culture
        )
        prop = response_within_property(
            "ORDER_BLOOD_CULTURE", "GIVE_ANTIBIOTICS", 60.0
        )
        result = v.verify(trace, prop.formula)
        assert result.satisfied is False

    def test_stemi_door_to_balloon(self):
        """AHA: Door-to-balloon < 90 min."""
        v = LTLVerifier()
        prop = response_within_property(
            "DIAGNOSE_STEMI", "ACTIVATE_CATH_LAB", 90.0
        )

        # Good: cath lab activated 45 min after STEMI diagnosis
        trace = _timed_trace(
            ("ORDER_ECG", 5.0), ("DIAGNOSE_STEMI", 15.0),
            ("GIVE_ASPIRIN", 20.0), ("ACTIVATE_CATH_LAB", 60.0),
        )
        assert v.verify(trace, prop.formula).satisfied is True

        # Bad: 120 min delay
        trace2 = _timed_trace(
            ("DIAGNOSE_STEMI", 15.0), ("ACTIVATE_CATH_LAB", 140.0),
        )
        assert v.verify(trace2, prop.formula).satisfied is False

    def test_rv_infarct_nitrates_trap_timed(self):
        """RV infarct + nitrates within 60 min → safety violation."""
        v = LTLVerifier()
        prop = absence_after_property("DIAGNOSE_RV_INFARCT", "GIVE_NITRATES", 60.0)

        # Trap: nitrates 20 min after RV diagnosis
        trace = _timed_trace(
            ("ORDER_ECG_V4R", 5.0),
            ("DIAGNOSE_RV_INFARCT", 10.0),
            ("GIVE_NITRATES", 30.0),  # 20 min after diagnosis
        )
        assert v.verify(trace, prop.formula).satisfied is False

        # Safe: nitrates 90 min after (if ever appropriate)
        trace2 = _timed_trace(
            ("DIAGNOSE_RV_INFARCT", 10.0),
            ("GIVE_FLUID", 20.0),
            ("GIVE_NITRATES", 100.0),  # 90 min after, outside window
        )
        assert v.verify(trace2, prop.formula).satisfied is True


# ============================================
# Test: Edge Cases
# ============================================

class TestMTLEdgeCases:
    def test_zero_width_window(self):
        """F[t,t](φ) only satisfied if event exactly at t."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("B", 30.0))
        # Window [30, 30] — only matches if B at exactly 30
        formula = finally_within(atom("B"), 30.0, 30.0)
        assert v.verify(trace, formula).satisfied is True

    def test_large_window(self):
        """Large window acts like unbounded F."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 0.0), ("B", 999.0))
        formula = finally_within(atom("B"), 0.0, 10000.0)
        assert v.verify(trace, formula).satisfied is True

    def test_backward_compat_ltl_unchanged(self):
        """Existing LTL formulas still work correctly."""
        v = LTLVerifier()
        trace = _timed_trace(
            ("A", 0.0), ("B", 30.0), ("A", 60.0)
        )
        # Unbounded LTL: G(A → F B)
        from cga_bench.semantic_layer.export.temporal_logic_verifier import (
            finally_, response_property
        )
        prop = response_property("A", "B")
        # First A gets B, second A doesn't (no B after pos 2)
        assert v.verify(trace, prop.formula).satisfied is False

    def test_nested_bounded_in_globally(self):
        """G(trigger → F[0,60](response)): multiple triggers each bounded."""
        v = LTLVerifier()
        formula = globally(implies(
            atom("T"),
            finally_within(atom("R"), 0.0, 60.0),
        ))
        # First T→R in 30min, second T→R in 25min
        trace = _timed_trace(
            ("T", 0.0), ("R", 30.0),
            ("T", 100.0), ("R", 125.0),
        )
        assert v.verify(trace, formula).satisfied is True

    def test_property_name_and_category(self):
        """MTL properties have descriptive names and timing category."""
        prop = response_within_property("A", "B", 60.0)
        assert "60" in prop.name
        assert prop.category == "timing"

        prop2 = existence_within_property("ECG", 10.0)
        assert "10" in prop2.name
        assert prop2.category == "timing"

        prop3 = absence_after_property("RV", "NITRO", 30.0)
        assert prop3.category == "safety"

    def test_formula_repr_bounded(self):
        """Bounded formulas have readable repr."""
        f = finally_within(atom("B"), 0.0, 60.0)
        s = repr(f)
        assert "60" in s or "F[]" in s

    def test_single_event_trace(self):
        """Single-event trace behavior."""
        v = LTLVerifier()
        trace = _timed_trace(("A", 5.0))

        # F[0,10](A) starting at pos 0: t=5, delta=0, A present → True
        assert v.verify(trace, finally_within(atom("A"), 0.0, 10.0)).satisfied is True

        # F[0,10](B): B not present → False
        assert v.verify(trace, finally_within(atom("B"), 0.0, 10.0)).satisfied is False
