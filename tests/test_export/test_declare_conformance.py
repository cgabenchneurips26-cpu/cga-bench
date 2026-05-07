"""Tests for alignment-based Declare conformance checking and LTL generation."""
import pytest

from cga_bench.cpg_model.schemas.conformance import (
    ConstraintTemplate,
    SoftConstraint,
    SoftConstraints,
)
from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.export.declare_bridge import (
    DeclareBridge,
    DeclareConstraint,
    DeclareModel,
)
from cga_bench.semantic_layer.export.declare_conformance import (
    AlignmentConfig,
    AlignmentResult,
    AlignmentStep,
    DeclareConformanceChecker,
    FitnessPrecisionMetrics,
    LTLFormula,
)


def _make_event(name, timestamp_min=0.0):
    return ActivityEvent(name=name, timestamp_min=timestamp_min, raw_event={})


def _make_model(constraints, activities=None):
    if activities is None:
        activities = set()
        for c in constraints:
            activities.update(c.activities)
    return DeclareModel(
        activities=sorted(activities),
        constraints=constraints,
    )


def _make_soft_constraints(constraints):
    return SoftConstraints(cpg_id="test", constraints=constraints)


class TestAlignmentBasic:
    """Test basic alignment functionality."""

    def test_perfect_trace_full_fitness(self):
        model = _make_model([
            DeclareConstraint("Existence", ["QUERY_PATIENT"], source_id="c1"),
            DeclareConstraint("Existence", ["PRESCRIBE"], source_id="c2"),
        ])
        trace = [_make_event("QUERY_PATIENT"), _make_event("PRESCRIBE")]
        checker = DeclareConformanceChecker()
        result = checker.check_conformance(trace, model)
        assert result.fitness == 1.0
        assert result.total_cost == 0.0
        assert len(result.violated_constraints) == 0

    def test_missing_existence_model_move(self):
        model = _make_model([
            DeclareConstraint("Existence", ["QUERY_PATIENT"], source_id="c1"),
            DeclareConstraint("Existence", ["PRESCRIBE"], source_id="c2"),
        ])
        trace = [_make_event("QUERY_PATIENT")]
        checker = DeclareConformanceChecker()
        result = checker.check_conformance(trace, model)
        assert result.fitness < 1.0
        assert result.model_moves == 1
        assert "c2" in result.violated_constraints

    def test_response_satisfied(self):
        model = _make_model([
            DeclareConstraint("Response", ["QUERY_PATIENT", "PRESCRIBE"], source_id="r1"),
        ])
        trace = [_make_event("QUERY_PATIENT", 0.0), _make_event("PRESCRIBE", 5.0)]
        checker = DeclareConformanceChecker()
        result = checker.check_conformance(trace, model)
        assert result.fitness == 1.0
        assert len(result.violated_constraints) == 0

    def test_response_violated(self):
        model = _make_model([
            DeclareConstraint("Response", ["QUERY_PATIENT", "PRESCRIBE"], source_id="r1"),
        ])
        trace = [_make_event("QUERY_PATIENT", 0.0)]
        checker = DeclareConformanceChecker()
        result = checker.check_conformance(trace, model)
        assert result.fitness < 1.0
        assert "r1" in result.violated_constraints

    def test_precedence_satisfied(self):
        model = _make_model([
            DeclareConstraint("Precedence", ["QUERY_PATIENT", "PRESCRIBE"], source_id="p1"),
        ])
        trace = [_make_event("QUERY_PATIENT", 0.0), _make_event("PRESCRIBE", 5.0)]
        checker = DeclareConformanceChecker()
        result = checker.check_conformance(trace, model)
        assert result.fitness == 1.0

    def test_precedence_violated(self):
        model = _make_model([
            DeclareConstraint("Precedence", ["QUERY_PATIENT", "PRESCRIBE"], source_id="p1"),
        ])
        trace = [_make_event("PRESCRIBE", 0.0)]
        checker = DeclareConformanceChecker()
        result = checker.check_conformance(trace, model)
        assert "p1" in result.violated_constraints

    def test_not_succession_satisfied(self):
        model = _make_model([
            DeclareConstraint("Not Succession", ["PRESCRIBE", "CANCEL"], source_id="ns1"),
        ])
        trace = [_make_event("PRESCRIBE", 0.0), _make_event("QUERY_PATIENT", 5.0)]
        checker = DeclareConformanceChecker()
        result = checker.check_conformance(trace, model)
        assert result.fitness == 1.0

    def test_not_succession_violated(self):
        model = _make_model([
            DeclareConstraint("Not Succession", ["PRESCRIBE", "CANCEL"], source_id="ns1"),
        ])
        trace = [_make_event("PRESCRIBE", 0.0), _make_event("CANCEL", 5.0)]
        checker = DeclareConformanceChecker()
        result = checker.check_conformance(trace, model)
        assert "ns1" in result.violated_constraints

    def test_not_coexistence_satisfied(self):
        model = _make_model([
            DeclareConstraint("Not Co-Existence", ["DRUG_A", "DRUG_B"], source_id="nc1"),
        ])
        trace = [_make_event("DRUG_A", 0.0)]
        checker = DeclareConformanceChecker()
        result = checker.check_conformance(trace, model)
        assert result.fitness == 1.0

    def test_not_coexistence_violated(self):
        model = _make_model([
            DeclareConstraint("Not Co-Existence", ["DRUG_A", "DRUG_B"], source_id="nc1"),
        ])
        trace = [_make_event("DRUG_A", 0.0), _make_event("DRUG_B", 5.0)]
        checker = DeclareConformanceChecker()
        result = checker.check_conformance(trace, model)
        assert "nc1" in result.violated_constraints

    def test_empty_trace_all_existence_violated(self):
        model = _make_model([
            DeclareConstraint("Existence", ["A"], source_id="e1"),
            DeclareConstraint("Existence", ["B"], source_id="e2"),
        ])
        trace = []
        checker = DeclareConformanceChecker()
        result = checker.check_conformance(trace, model)
        assert result.fitness == 0.0
        assert set(result.violated_constraints) == {"e1", "e2"}

    def test_diagnostic_info_populated(self):
        model = _make_model([
            DeclareConstraint("Existence", ["MISSING"], source_id="diag1"),
        ])
        trace = [_make_event("OTHER")]
        checker = DeclareConformanceChecker()
        result = checker.check_conformance(trace, model)
        assert "diag1" in result.diagnostic_info
        assert result.diagnostic_info["diag1"]["type"] == "missing_activity"


class TestAlignmentCostModels:
    """Test standard vs weighted cost models."""

    def test_standard_cost_uniform(self):
        model = _make_model([
            DeclareConstraint("Existence", ["A"], source_id="c1", weight=10.0),
            DeclareConstraint("Existence", ["B"], source_id="c2", weight=1.0),
        ])
        trace = []
        config = AlignmentConfig(cost_model="standard")
        checker = DeclareConformanceChecker(config)
        result = checker.check_conformance(trace, model)
        # Both violations cost 1.0 each
        assert result.total_cost == 2.0

    def test_weighted_cost_uses_constraint_weight(self):
        model = _make_model([
            DeclareConstraint("Existence", ["A"], source_id="c1", weight=10.0),
            DeclareConstraint("Existence", ["B"], source_id="c2", weight=1.0),
        ])
        trace = []
        config = AlignmentConfig(cost_model="weighted")
        checker = DeclareConformanceChecker(config)
        result = checker.check_conformance(trace, model)
        # Costs based on weights: 10 + 1 = 11
        assert result.total_cost == 11.0

    def test_weighted_fitness_calculation(self):
        model = _make_model([
            DeclareConstraint("Existence", ["A"], source_id="c1", weight=10.0),
            DeclareConstraint("Existence", ["B"], source_id="c2", weight=10.0),
        ])
        trace = [_make_event("A")]  # Only A present, B missing
        config = AlignmentConfig(cost_model="weighted")
        checker = DeclareConformanceChecker(config)
        result = checker.check_conformance(trace, model)
        # Max cost = 20, actual = 10, fitness = 1 - 10/20 = 0.5
        assert abs(result.fitness - 0.5) < 0.01


class TestLTLGeneration:
    """Test Declare -> LTL formula conversion."""

    def test_existence_to_eventually(self):
        model = _make_model([
            DeclareConstraint("Existence", ["QUERY_PATIENT"], source_id="e1"),
        ])
        checker = DeclareConformanceChecker()
        formulas = checker.generate_ltl_formulas(model)
        assert len(formulas) == 1
        assert formulas[0].formula == "F(QUERY_PATIENT)"
        assert formulas[0].template == "Existence"

    def test_response_to_global_implies_eventually(self):
        model = _make_model([
            DeclareConstraint("Response", ["A", "B"], source_id="r1"),
        ])
        checker = DeclareConformanceChecker()
        formulas = checker.generate_ltl_formulas(model)
        assert formulas[0].formula == "G(A -> F(B))"

    def test_precedence_to_weak_until(self):
        model = _make_model([
            DeclareConstraint("Precedence", ["A", "B"], source_id="p1"),
        ])
        checker = DeclareConformanceChecker()
        formulas = checker.generate_ltl_formulas(model)
        assert formulas[0].formula == "(!B W A)"

    def test_not_succession_formula(self):
        model = _make_model([
            DeclareConstraint("Not Succession", ["A", "B"], source_id="ns1"),
        ])
        checker = DeclareConformanceChecker()
        formulas = checker.generate_ltl_formulas(model)
        assert formulas[0].formula == "G(A -> !F(B))"

    def test_not_coexistence_formula(self):
        model = _make_model([
            DeclareConstraint("Not Co-Existence", ["A", "B"], source_id="nc1"),
        ])
        checker = DeclareConformanceChecker()
        formulas = checker.generate_ltl_formulas(model)
        assert formulas[0].formula == "!(F(A) & F(B))"

    def test_response_within_includes_window(self):
        model = _make_model([
            DeclareConstraint(
                "Response", ["A", "B"], source_id="rw1", time_window=10.0
            ),
        ])
        checker = DeclareConformanceChecker()
        formulas = checker.generate_ltl_formulas(model)
        assert "F_<=10.0" in formulas[0].formula
        assert "A" in formulas[0].formula
        assert "B" in formulas[0].formula

    def test_multiple_constraints_multiple_formulas(self):
        model = _make_model([
            DeclareConstraint("Existence", ["A"], source_id="e1"),
            DeclareConstraint("Response", ["A", "B"], source_id="r1"),
            DeclareConstraint("Precedence", ["C", "D"], source_id="p1"),
        ])
        checker = DeclareConformanceChecker()
        formulas = checker.generate_ltl_formulas(model)
        assert len(formulas) == 3

    def test_source_constraint_id_preserved(self):
        model = _make_model([
            DeclareConstraint("Existence", ["X"], source_id="my_constraint_42"),
        ])
        checker = DeclareConformanceChecker()
        formulas = checker.generate_ltl_formulas(model)
        assert formulas[0].source_constraint_id == "my_constraint_42"


class TestFitnessPrecision:
    """Test fitness/precision/generalization metrics."""

    def test_perfect_traces_fitness_1(self):
        model = _make_model([
            DeclareConstraint("Existence", ["A"], source_id="e1"),
        ])
        traces = [
            [_make_event("A"), _make_event("B")],
            [_make_event("A"), _make_event("C")],
        ]
        checker = DeclareConformanceChecker()
        metrics = checker.compute_fitness_precision(traces, model)
        assert metrics.fitness == 1.0

    def test_all_violations_fitness_0(self):
        model = _make_model([
            DeclareConstraint("Existence", ["MISSING"], source_id="e1"),
        ])
        traces = [
            [_make_event("OTHER")],
            [_make_event("ANOTHER")],
        ]
        checker = DeclareConformanceChecker()
        metrics = checker.compute_fitness_precision(traces, model)
        assert metrics.fitness == 0.0

    def test_mixed_fitness(self):
        model = _make_model([
            DeclareConstraint("Existence", ["A"], source_id="e1"),
        ])
        traces = [
            [_make_event("A")],   # fitness 1.0
            [_make_event("B")],   # fitness 0.0
        ]
        checker = DeclareConformanceChecker()
        metrics = checker.compute_fitness_precision(traces, model)
        assert abs(metrics.fitness - 0.5) < 0.01

    def test_precision_reflects_model_usage(self):
        model = _make_model(
            [DeclareConstraint("Existence", ["A"], source_id="e1")],
            activities=["A", "B", "C"],
        )
        traces = [[_make_event("A")]]  # Only uses 1 of 3 activities
        checker = DeclareConformanceChecker()
        metrics = checker.compute_fitness_precision(traces, model)
        assert abs(metrics.precision - 1.0/3.0) < 0.01

    def test_f_measure_harmonic_mean(self):
        model = _make_model([
            DeclareConstraint("Existence", ["A"], source_id="e1"),
        ])
        traces = [[_make_event("A")]]
        checker = DeclareConformanceChecker()
        metrics = checker.compute_fitness_precision(traces, model)
        f = metrics.fitness
        p = metrics.precision
        expected_f_measure = 2 * f * p / (f + p) if (f + p) > 0 else 0
        assert abs(metrics.f_measure - expected_f_measure) < 0.01

    def test_empty_traces_returns_perfect(self):
        model = _make_model([
            DeclareConstraint("Existence", ["A"], source_id="e1"),
        ])
        checker = DeclareConformanceChecker()
        metrics = checker.compute_fitness_precision([], model)
        assert metrics.fitness == 1.0

    def test_generalization_perfect_when_all_same(self):
        model = _make_model([
            DeclareConstraint("Existence", ["A"], source_id="e1"),
        ])
        traces = [
            [_make_event("A")],
            [_make_event("A")],
            [_make_event("A")],
        ]
        checker = DeclareConformanceChecker()
        metrics = checker.compute_fitness_precision(traces, model)
        assert metrics.generalization == 1.0


class TestDeclareBridgeIntegration:
    """Test DeclareBridge integration with alignment."""

    def test_align_trace_via_bridge(self):
        from cga_bench.semantic_layer.export.declare_conformance import AlignmentConfig
        bridge = DeclareBridge(alignment_config=AlignmentConfig())
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="e1",
                template=ConstraintTemplate.EXISTENCE,
                A="QUERY_PATIENT",
            ),
        ])
        trace = [_make_event("QUERY_PATIENT")]
        result = bridge.align_trace(trace, soft)
        assert result.fitness == 1.0

    def test_align_trace_without_config(self):
        bridge = DeclareBridge()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="e1",
                template=ConstraintTemplate.EXISTENCE,
                A="QUERY_PATIENT",
            ),
        ])
        trace = [_make_event("QUERY_PATIENT")]
        result = bridge.align_trace(trace, soft)
        assert result.fitness == 1.0

    def test_compute_metrics_via_bridge(self):
        bridge = DeclareBridge()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="e1",
                template=ConstraintTemplate.EXISTENCE,
                A="QUERY_PATIENT",
            ),
        ])
        traces = [[_make_event("QUERY_PATIENT")], [_make_event("OTHER")]]
        metrics = bridge.compute_metrics(traces, soft)
        assert 0.0 < metrics.fitness < 1.0

    def test_to_ltl_via_bridge(self):
        bridge = DeclareBridge()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="e1",
                template=ConstraintTemplate.EXISTENCE,
                A="QUERY_PATIENT",
            ),
            SoftConstraint(
                constraint_id="r1",
                template=ConstraintTemplate.RESPONSE,
                A="QUERY_PATIENT", B="PRESCRIBE",
            ),
        ])
        formulas = bridge.to_ltl(soft)
        assert len(formulas) == 2

    def test_original_methods_unchanged(self):
        bridge = DeclareBridge()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="e1",
                template=ConstraintTemplate.EXISTENCE,
                A="QUERY_PATIENT",
            ),
        ])
        model = bridge.to_declare_model(soft)
        assert len(model.constraints) == 1
        text = bridge.to_declare_text(soft)
        assert "QUERY_PATIENT" in text

    def test_cross_verify_unchanged(self):
        bridge = DeclareBridge()
        result = bridge.cross_verify(["c1", "c2"], ["c1", "c3"], ["c1", "c2", "c3"])
        assert result.matched == 1
        assert result.mismatched == 2
