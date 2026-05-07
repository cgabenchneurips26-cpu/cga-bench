"""Tests for LTL/CTL Formal Verification."""
import pytest

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.export.temporal_logic_verifier import (
    CTLVerifier,
    KripkeState,
    KripkeStructure,
    LTLVerifier,
    PropertySpec,
    TLFormula,
    TemporalOp,
    VerificationReport,
    VerificationResult,
    a_until,
    absence_property,
    af,
    ag,
    and_,
    atom,
    ax,
    e_until,
    ef,
    eg,
    ex,
    existence_property,
    finally_,
    globally,
    implies,
    next_,
    not_,
    not_succession_property,
    or_,
    precedence_property,
    response_property,
    until,
    weak_until,
)


# ============================================
# Helpers
# ============================================

def _trace(*names):
    """Create a trace from activity names."""
    return [
        ActivityEvent(name=n, timestamp_min=float(i), raw_event={},
                      confidence=1.0, match_source="exact")
        for i, n in enumerate(names)
    ]


# ============================================
# Test Class: Propositional Logic
# ============================================

class TestPropositional:
    """Tests for propositional operators (no temporal)."""

    def test_atom_true(self):
        """Atom matches when activity name equals."""
        v = LTLVerifier()
        trace = _trace("A", "B", "C")
        assert v.verify(trace, atom("A")).satisfied is True

    def test_atom_false(self):
        """Atom fails when activity name differs."""
        v = LTLVerifier()
        trace = _trace("A", "B", "C")
        assert v.verify(trace, atom("X")).satisfied is False

    def test_not_true(self):
        """Negation of false atom is true."""
        v = LTLVerifier()
        trace = _trace("A", "B")
        assert v.verify(trace, not_(atom("X"))).satisfied is True

    def test_not_false(self):
        """Negation of true atom is false."""
        v = LTLVerifier()
        trace = _trace("A", "B")
        assert v.verify(trace, not_(atom("A"))).satisfied is False

    def test_and_both_true(self):
        """AND: both children true."""
        v = LTLVerifier()
        trace = _trace("A")
        assert v.verify(trace, and_(atom("A"), not_(atom("X")))).satisfied is True

    def test_and_one_false(self):
        """AND: one child false."""
        v = LTLVerifier()
        trace = _trace("A")
        assert v.verify(trace, and_(atom("A"), atom("B"))).satisfied is False

    def test_or_one_true(self):
        """OR: one child true suffices."""
        v = LTLVerifier()
        trace = _trace("A")
        assert v.verify(trace, or_(atom("A"), atom("B"))).satisfied is True

    def test_implies_true(self):
        """Implication: antecedent false → true."""
        v = LTLVerifier()
        trace = _trace("A")
        assert v.verify(trace, implies(atom("X"), atom("Y"))).satisfied is True

    def test_implies_false(self):
        """Implication: antecedent true, consequent false."""
        v = LTLVerifier()
        trace = _trace("A")
        assert v.verify(trace, implies(atom("A"), atom("B"))).satisfied is False


# ============================================
# Test Class: LTL Next Operator
# ============================================

class TestLTLNext:
    """Tests for the X (neXt) operator."""

    def test_next_holds(self):
        """X(B) at position 0 when trace is [A, B, ...]."""
        v = LTLVerifier()
        trace = _trace("A", "B", "C")
        assert v.verify(trace, next_(atom("B"))).satisfied is True

    def test_next_fails(self):
        """X(C) at position 0 fails when second element is B."""
        v = LTLVerifier()
        trace = _trace("A", "B", "C")
        assert v.verify(trace, next_(atom("C"))).satisfied is False

    def test_next_at_end(self):
        """X at last position is false (finite trace semantics)."""
        v = LTLVerifier()
        trace = _trace("A")
        assert v.verify(trace, next_(atom("A"))).satisfied is False

    def test_nested_next(self):
        """X(X(C)) = third element is C."""
        v = LTLVerifier()
        trace = _trace("A", "B", "C")
        assert v.verify(trace, next_(next_(atom("C")))).satisfied is True


# ============================================
# Test Class: LTL Finally (F) Operator
# ============================================

class TestLTLFinally:
    """Tests for the F (Finally/Eventually) operator."""

    def test_finally_immediate(self):
        """F(A) true when A is first."""
        v = LTLVerifier()
        trace = _trace("A", "B", "C")
        assert v.verify(trace, finally_(atom("A"))).satisfied is True

    def test_finally_later(self):
        """F(C) true when C appears at end."""
        v = LTLVerifier()
        trace = _trace("A", "B", "C")
        assert v.verify(trace, finally_(atom("C"))).satisfied is True

    def test_finally_absent(self):
        """F(X) false when X never appears."""
        v = LTLVerifier()
        trace = _trace("A", "B", "C")
        result = v.verify(trace, finally_(atom("X")))
        assert result.satisfied is False

    def test_finally_empty_trace(self):
        """F(X) false on empty trace."""
        v = LTLVerifier()
        result = v.verify([], finally_(atom("X")))
        assert result.satisfied is False


# ============================================
# Test Class: LTL Globally (G) Operator
# ============================================

class TestLTLGlobally:
    """Tests for the G (Globally/Always) operator."""

    def test_globally_all_same(self):
        """G(A) true when all elements are A."""
        v = LTLVerifier()
        trace = _trace("A", "A", "A")
        assert v.verify(trace, globally(atom("A"))).satisfied is True

    def test_globally_violated(self):
        """G(A) false when B appears."""
        v = LTLVerifier()
        trace = _trace("A", "B", "A")
        result = v.verify(trace, globally(atom("A")))
        assert result.satisfied is False
        assert result.witness_position == 1

    def test_globally_negation(self):
        """G(¬X) true when X never appears."""
        v = LTLVerifier()
        trace = _trace("A", "B", "C")
        assert v.verify(trace, globally(not_(atom("X")))).satisfied is True

    def test_globally_empty_trace(self):
        """G(X) vacuously true on empty trace."""
        v = LTLVerifier()
        assert v.verify([], globally(atom("X"))).satisfied is True


# ============================================
# Test Class: LTL Until (U) Operator
# ============================================

class TestLTLUntil:
    """Tests for the U (Until) operator."""

    def test_until_basic(self):
        """A U B: A holds until B appears."""
        v = LTLVerifier()
        trace = _trace("A", "A", "B", "C")
        assert v.verify(trace, until(atom("A"), atom("B"))).satisfied is True

    def test_until_immediate(self):
        """A U B: B appears immediately."""
        v = LTLVerifier()
        trace = _trace("B", "A")
        assert v.verify(trace, until(atom("A"), atom("B"))).satisfied is True

    def test_until_never_b(self):
        """A U B: B never appears."""
        v = LTLVerifier()
        trace = _trace("A", "A", "A")
        assert v.verify(trace, until(atom("A"), atom("B"))).satisfied is False

    def test_until_phi_breaks_before_psi(self):
        """A U B: A breaks before B appears."""
        v = LTLVerifier()
        trace = _trace("A", "C", "B")
        assert v.verify(trace, until(atom("A"), atom("B"))).satisfied is False


# ============================================
# Test Class: LTL Weak Until (W) Operator
# ============================================

class TestLTLWeakUntil:
    """Tests for the W (Weak Until) operator."""

    def test_weak_until_with_psi(self):
        """A W B: same as U when B appears."""
        v = LTLVerifier()
        trace = _trace("A", "A", "B")
        assert v.verify(trace, weak_until(atom("A"), atom("B"))).satisfied is True

    def test_weak_until_globally_phi(self):
        """A W B: true when A holds forever (B never appears)."""
        v = LTLVerifier()
        trace = _trace("A", "A", "A")
        assert v.verify(trace, weak_until(atom("A"), atom("B"))).satisfied is True

    def test_weak_until_phi_breaks(self):
        """A W B: A breaks before B, and not G(A) → false."""
        v = LTLVerifier()
        trace = _trace("A", "C", "A")
        assert v.verify(trace, weak_until(atom("A"), atom("B"))).satisfied is False


# ============================================
# Test Class: Clinical Property Library
# ============================================

class TestClinicalProperties:
    """Tests for pre-built clinical safety properties."""

    def test_response_property_satisfied(self):
        """Response: trigger followed by response."""
        v = LTLVerifier()
        prop = response_property("ORDER_LAB", "OBSERVE_RESULTS")
        trace = _trace("ORDER_LAB", "WAIT", "OBSERVE_RESULTS")
        assert v.verify(trace, prop.formula).satisfied is True

    def test_response_property_violated(self):
        """Response: trigger without subsequent response."""
        v = LTLVerifier()
        prop = response_property("ORDER_LAB", "OBSERVE_RESULTS")
        trace = _trace("ORDER_LAB", "PRESCRIBE", "DISCHARGE")
        result = v.verify(trace, prop.formula)
        assert result.satisfied is False

    def test_response_no_trigger(self):
        """Response: vacuously true when trigger absent."""
        v = LTLVerifier()
        prop = response_property("ORDER_LAB", "OBSERVE_RESULTS")
        trace = _trace("ASSESS", "PRESCRIBE")
        assert v.verify(trace, prop.formula).satisfied is True

    def test_precedence_property_satisfied(self):
        """Precedence: prerequisite before action."""
        v = LTLVerifier()
        prop = precedence_property("BLOOD_CULTURE", "ANTIBIOTICS")
        trace = _trace("BLOOD_CULTURE", "ANTIBIOTICS")
        assert v.verify(trace, prop.formula).satisfied is True

    def test_precedence_property_violated(self):
        """Precedence: action before prerequisite."""
        v = LTLVerifier()
        prop = precedence_property("BLOOD_CULTURE", "ANTIBIOTICS")
        trace = _trace("ANTIBIOTICS", "BLOOD_CULTURE")
        result = v.verify(trace, prop.formula)
        assert result.satisfied is False

    def test_absence_property_satisfied(self):
        """Absence: forbidden action never occurs."""
        v = LTLVerifier()
        prop = absence_property("GIVE_NITRATES")
        trace = _trace("ASSESS", "ORDER_ECG", "GIVE_FLUIDS")
        assert v.verify(trace, prop.formula).satisfied is True

    def test_absence_property_violated(self):
        """Absence: forbidden action occurs."""
        v = LTLVerifier()
        prop = absence_property("GIVE_NITRATES")
        trace = _trace("ASSESS", "GIVE_NITRATES", "MONITOR")
        result = v.verify(trace, prop.formula)
        assert result.satisfied is False
        assert result.witness_position == 1

    def test_existence_property_satisfied(self):
        """Existence: required action occurs."""
        v = LTLVerifier()
        prop = existence_property("ASSESS_VITALS")
        trace = _trace("TRIAGE", "ASSESS_VITALS", "ORDER_LAB")
        assert v.verify(trace, prop.formula).satisfied is True

    def test_existence_property_violated(self):
        """Existence: required action missing."""
        v = LTLVerifier()
        prop = existence_property("ASSESS_VITALS")
        trace = _trace("TRIAGE", "ORDER_LAB")
        assert v.verify(trace, prop.formula).satisfied is False

    def test_not_succession_satisfied(self):
        """Not succession: B never follows A."""
        v = LTLVerifier()
        prop = not_succession_property("RV_DIAGNOSED", "GIVE_NITRATES")
        trace = _trace("ASSESS", "RV_DIAGNOSED", "GIVE_FLUIDS")
        assert v.verify(trace, prop.formula).satisfied is True

    def test_not_succession_violated(self):
        """Not succession: B follows A."""
        v = LTLVerifier()
        prop = not_succession_property("RV_DIAGNOSED", "GIVE_NITRATES")
        trace = _trace("RV_DIAGNOSED", "GIVE_NITRATES")
        result = v.verify(trace, prop.formula)
        assert result.satisfied is False


# ============================================
# Test Class: Verification Report
# ============================================

class TestVerificationReport:
    """Tests for multi-property verification reports."""

    def test_all_satisfied(self):
        """Report shows all properties satisfied."""
        v = LTLVerifier()
        props = [
            existence_property("A"),
            absence_property("X"),
        ]
        trace = _trace("A", "B", "C")
        report = v.verify_properties(trace, props, trace_id="ep_001")

        assert report.trace_id == "ep_001"
        assert report.total_properties == 2
        assert report.satisfied == 2
        assert report.violated == 0

    def test_partial_violation(self):
        """Report shows mix of satisfied and violated."""
        v = LTLVerifier()
        props = [
            existence_property("A"),
            existence_property("X"),  # Missing
            absence_property("B"),    # B present → violated
        ]
        trace = _trace("A", "B", "C")
        report = v.verify_properties(trace, props, trace_id="ep_002")

        assert report.satisfied == 1
        assert report.violated == 2

    def test_empty_properties(self):
        """Empty property list → empty report."""
        v = LTLVerifier()
        trace = _trace("A")
        report = v.verify_properties(trace, [], trace_id="ep_003")
        assert report.total_properties == 0
        assert report.satisfied == 0


# ============================================
# Test Class: CTL Kripke Structure
# ============================================

class TestKripkeStructure:
    """Tests for Kripke structure building from traces."""

    def test_single_trace(self):
        """Single trace builds linear Kripke structure."""
        ctl = CTLVerifier()
        traces = [_trace("A", "B", "C")]
        ks = ctl.build_kripke_from_traces(traces)

        # 4 states: _start, A, B, C
        assert len(ks.states) == 4
        assert ks.initial_state == 0

    def test_shared_prefix(self):
        """Traces with common prefix share states."""
        ctl = CTLVerifier()
        traces = [
            _trace("A", "B", "C"),
            _trace("A", "B", "D"),
        ]
        ks = ctl.build_kripke_from_traces(traces)

        # _start → A → B → (C, D): 5 states
        assert len(ks.states) == 5

    def test_no_shared_prefix(self):
        """Traces with no common prefix create separate branches."""
        ctl = CTLVerifier()
        traces = [
            _trace("A", "B"),
            _trace("X", "Y"),
        ]
        ks = ctl.build_kripke_from_traces(traces)

        # _start → (A → B, X → Y): 5 states
        assert len(ks.states) == 5
        assert len(ks.states[0].successors) == 2  # Two branches from root

    def test_empty_traces(self):
        """Empty trace list → single initial state."""
        ctl = CTLVerifier()
        ks = ctl.build_kripke_from_traces([])
        assert len(ks.states) == 1


# ============================================
# Test Class: CTL Verification
# ============================================

class TestCTLVerification:
    """Tests for CTL model checking on Kripke structures."""

    def test_ef_reachable(self):
        """EF(C): C is reachable from initial state."""
        ctl = CTLVerifier()
        traces = [_trace("A", "B", "C")]
        ks = ctl.build_kripke_from_traces(traces)
        result = ctl.verify(ks, ef(atom("C")))
        assert result.satisfied is True

    def test_ef_unreachable(self):
        """EF(X): X not reachable."""
        ctl = CTLVerifier()
        traces = [_trace("A", "B", "C")]
        ks = ctl.build_kripke_from_traces(traces)
        result = ctl.verify(ks, ef(atom("X")))
        assert result.satisfied is False

    def test_ag_holds(self):
        """AG(¬X): X never holds anywhere."""
        ctl = CTLVerifier()
        traces = [_trace("A", "B", "C")]
        ks = ctl.build_kripke_from_traces(traces)
        result = ctl.verify(ks, ag(not_(atom("X"))))
        assert result.satisfied is True

    def test_ag_violated(self):
        """AG(¬B): B exists somewhere."""
        ctl = CTLVerifier()
        traces = [_trace("A", "B", "C")]
        ks = ctl.build_kripke_from_traces(traces)
        result = ctl.verify(ks, ag(not_(atom("B"))))
        assert result.satisfied is False

    def test_branching_ef(self):
        """EF with branching: C reachable on one branch."""
        ctl = CTLVerifier()
        traces = [
            _trace("A", "B", "C"),
            _trace("A", "B", "D"),
        ]
        ks = ctl.build_kripke_from_traces(traces)
        # C is reachable via one path
        assert ctl.verify(ks, ef(atom("C"))).satisfied is True
        # D is also reachable
        assert ctl.verify(ks, ef(atom("D"))).satisfied is True

    def test_branching_af(self):
        """AF with branching: must hold on ALL paths."""
        ctl = CTLVerifier()
        traces = [
            _trace("A", "B", "C"),
            _trace("A", "B", "D"),
        ]
        ks = ctl.build_kripke_from_traces(traces)
        # C is NOT reached on all paths (D path exists)
        assert ctl.verify(ks, af(atom("C"))).satisfied is False
        # B is reached on all paths
        assert ctl.verify(ks, af(atom("B"))).satisfied is True

    def test_ex_successor(self):
        """EX: immediate successor has property."""
        ctl = CTLVerifier()
        traces = [_trace("A", "B")]
        ks = ctl.build_kripke_from_traces(traces)
        # From initial (_start), EX(A) should hold
        assert ctl.verify(ks, ex(atom("A"))).satisfied is True
        # From initial, EX(B) should not hold (B is 2 steps away)
        assert ctl.verify(ks, ex(atom("B"))).satisfied is False

    def test_eu_satisfied(self):
        """E[A U B]: there exists a path where A holds until B."""
        ctl = CTLVerifier()
        # Build Kripke: _start → A → A → B
        ks = KripkeStructure(states=[
            KripkeState(state_id=0, labels={"A"}, successors=[1]),
            KripkeState(state_id=1, labels={"A"}, successors=[2]),
            KripkeState(state_id=2, labels={"B"}, successors=[]),
        ], initial_state=0)
        result = ctl.verify(ks, e_until(atom("A"), atom("B")))
        assert result.satisfied is True

    def test_eu_not_satisfied(self):
        """E[A U B]: A breaks before B."""
        ctl = CTLVerifier()
        ks = KripkeStructure(states=[
            KripkeState(state_id=0, labels={"A"}, successors=[1]),
            KripkeState(state_id=1, labels={"C"}, successors=[2]),  # A breaks
            KripkeState(state_id=2, labels={"B"}, successors=[]),
        ], initial_state=0)
        result = ctl.verify(ks, e_until(atom("A"), atom("B")))
        assert result.satisfied is False


# ============================================
# Test Class: Clinical Scenarios
# ============================================

class TestClinicalScenarios:
    """Tests with realistic clinical safety properties."""

    def test_sepsis_blood_culture_before_antibiotics(self):
        """Sepsis: blood culture must precede antibiotics."""
        v = LTLVerifier()
        prop = precedence_property("BLOOD_CULTURE", "GIVE_ANTIBIOTICS")

        # Good trace
        good = _trace("ASSESS", "BLOOD_CULTURE", "GIVE_ANTIBIOTICS")
        assert v.verify(good, prop.formula).satisfied is True

        # Bad trace (antibiotics first)
        bad = _trace("ASSESS", "GIVE_ANTIBIOTICS", "BLOOD_CULTURE")
        assert v.verify(bad, prop.formula).satisfied is False

    def test_rv_trap_no_nitrates_after_diagnosis(self):
        """RV Infarct: never give nitrates after RV diagnosis."""
        v = LTLVerifier()
        prop = not_succession_property("DIAGNOSE_RV_INFARCT", "GIVE_NITRATES")

        # Correct: fluids given instead
        correct = _trace("DIAGNOSE_RV_INFARCT", "GIVE_FLUIDS", "MONITOR")
        assert v.verify(correct, prop.formula).satisfied is True

        # Incorrect: nitrates given
        incorrect = _trace("DIAGNOSE_RV_INFARCT", "GIVE_NITRATES")
        assert v.verify(incorrect, prop.formula).satisfied is False

    def test_aki_contrast_avoidance(self):
        """AKI: contrast agent must never be given after AKI diagnosis."""
        v = LTLVerifier()
        prop = not_succession_property("DIAGNOSE_AKI", "GIVE_CONTRAST")

        safe = _trace("DIAGNOSE_AKI", "ORDER_RENAL_US", "MONITOR")
        assert v.verify(safe, prop.formula).satisfied is True

        unsafe = _trace("DIAGNOSE_AKI", "GIVE_CONTRAST")
        assert v.verify(unsafe, prop.formula).satisfied is False

    def test_sepsis_complete_bundle(self):
        """Sepsis bundle: all required actions must exist."""
        v = LTLVerifier()
        required = ["ASSESS_VITALS", "ORDER_LACTATE", "BLOOD_CULTURE", "GIVE_ANTIBIOTICS"]
        props = [existence_property(act) for act in required]

        # Complete bundle
        complete = _trace("ASSESS_VITALS", "ORDER_LACTATE", "BLOOD_CULTURE", "GIVE_ANTIBIOTICS")
        report = v.verify_properties(complete, props, "sepsis_complete")
        assert report.violated == 0

        # Missing actions
        incomplete = _trace("ASSESS_VITALS", "GIVE_ANTIBIOTICS")
        report = v.verify_properties(incomplete, props, "sepsis_incomplete")
        assert report.violated == 2  # Missing lactate and blood culture

    def test_combined_safety_liveness(self):
        """Combined safety + liveness properties for sepsis."""
        v = LTLVerifier()
        props = [
            # Liveness: antibiotics must eventually be given
            existence_property("GIVE_ANTIBIOTICS"),
            # Safety: no nitrates ever
            absence_property("GIVE_NITRATES"),
            # Ordering: culture before antibiotics
            precedence_property("BLOOD_CULTURE", "GIVE_ANTIBIOTICS"),
            # Response: if lactate ordered, results must be observed
            response_property("ORDER_LACTATE", "OBSERVE_LACTATE"),
        ]

        # Perfect trace
        perfect = _trace(
            "ASSESS", "ORDER_LACTATE", "BLOOD_CULTURE",
            "OBSERVE_LACTATE", "GIVE_ANTIBIOTICS"
        )
        report = v.verify_properties(perfect, props, "perfect")
        assert report.violated == 0

        # Flawed trace: missing observation, out-of-order
        flawed = _trace("ASSESS", "GIVE_ANTIBIOTICS", "ORDER_LACTATE")
        report = v.verify_properties(flawed, props, "flawed")
        assert report.violated >= 2  # Precedence + response violated

    def test_ctl_branching_clinical_scenario(self):
        """CTL: verify safety across multiple possible care pathways."""
        ctl = CTLVerifier()

        # Two possible pathways after diagnosis
        traces = [
            _trace("DIAGNOSE", "ORDER_LAB", "TREAT_A"),
            _trace("DIAGNOSE", "ORDER_LAB", "TREAT_B"),
        ]
        ks = ctl.build_kripke_from_traces(traces)

        # AG(¬GIVE_NITRATES): nitrates never given on any path
        assert ctl.verify(ks, ag(not_(atom("GIVE_NITRATES")))).satisfied is True

        # EF(TREAT_A): treatment A is reachable
        assert ctl.verify(ks, ef(atom("TREAT_A"))).satisfied is True

        # AF(ORDER_LAB): lab order is inevitable on all paths
        assert ctl.verify(ks, af(atom("ORDER_LAB"))).satisfied is True


# ============================================
# Test Class: Edge Cases
# ============================================

class TestEdgeCases:
    """Edge case tests."""

    def test_empty_trace_globally(self):
        """G(φ) vacuously true on empty trace."""
        v = LTLVerifier()
        assert v.verify([], globally(atom("X"))).satisfied is True

    def test_empty_trace_finally(self):
        """F(φ) false on empty trace."""
        v = LTLVerifier()
        assert v.verify([], finally_(atom("X"))).satisfied is False

    def test_single_element_trace(self):
        """Single-element trace works correctly."""
        v = LTLVerifier()
        trace = _trace("A")
        assert v.verify(trace, atom("A")).satisfied is True
        assert v.verify(trace, next_(atom("A"))).satisfied is False
        assert v.verify(trace, globally(atom("A"))).satisfied is True
        assert v.verify(trace, finally_(atom("A"))).satisfied is True

    def test_deeply_nested_formula(self):
        """Deeply nested formula evaluates correctly."""
        v = LTLVerifier()
        trace = _trace("A", "B", "C", "D", "E")
        # G(A → X(B → X(C → X(D → X(E)))))  — not quite right but tests nesting
        formula = globally(implies(atom("A"),
                                   next_(implies(atom("B"),
                                                 next_(atom("C"))))))
        # This checks: at every position where A holds, if next is B, then next-next is C
        # Position 0: A holds, next is B, next-next is C → true
        # Other positions: A doesn't hold → vacuously true
        assert v.verify(trace, formula).satisfied is True

    def test_violation_counterexample(self):
        """Counterexample provided for violated globally."""
        v = LTLVerifier()
        trace = _trace("A", "A", "B", "A")
        result = v.verify(trace, globally(atom("A")))
        assert result.satisfied is False
        assert result.witness_position == 2
        assert result.counterexample == ["A", "A", "B"]

    def test_formula_repr(self):
        """Formula string representation is readable."""
        f = globally(implies(atom("A"), finally_(atom("B"))))
        s = repr(f)
        assert "G" in s or "globally" in s.lower() or "F" in s
