"""Tests for trajectory analysis (phases, bottlenecks, critical path)."""
import pytest

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.conformance.temporal_verifier import (
    TemporalConstraint,
    TemporalConstraintType,
    TemporalVerifier,
)
from cga_bench.semantic_layer.conformance.trajectory_analyzer import (
    BottleneckInfo,
    ClinicalPhase,
    CriticalPath,
    CriticalPathStep,
    PhaseDetector,
    SensitivityResult,
    TrajectoryAnalysis,
    TrajectoryAnalyzer,
    TrajectoryConfig,
    TrajectoryMetrics,
)


def _make_event(name, timestamp_min=0.0):
    """Create an ActivityEvent for testing."""
    return ActivityEvent(name=name, timestamp_min=timestamp_min, raw_event={})


def _make_events(*specs):
    """Create multiple events from (name, timestamp) tuples."""
    return [_make_event(name, ts) for name, ts in specs]


# ==================================================================
# TestPhaseDetector
# ==================================================================

class TestPhaseDetector:
    """Test clinical phase detection."""

    def test_single_phase_all_same_pattern(self):
        events = _make_events(
            ("QUERY_PATIENT", 0.0), ("QUERY_LABS", 2.0), ("QUERY_VITALS", 4.0),
        )
        detector = PhaseDetector()
        phases = detector.detect_phases(events)
        assert len(phases) == 1
        assert phases[0].phase_name == "assessment"
        assert phases[0].activity_count == 3

    def test_two_phases_by_pattern(self):
        events = _make_events(
            ("QUERY_PATIENT", 0.0), ("QUERY_LABS", 2.0),
            ("GIVE_MEDICATION", 5.0), ("PRESCRIBE_DRUG", 7.0),
        )
        detector = PhaseDetector()
        phases = detector.detect_phases(events)
        assert len(phases) == 2
        assert phases[0].phase_name == "assessment"
        assert phases[1].phase_name == "treatment"

    def test_gap_based_boundary_detection(self):
        events = _make_events(
            ("QUERY_PATIENT", 0.0), ("QUERY_LABS", 2.0),
            ("QUERY_FOLLOW", 20.0),  # 18 min gap > default 10 min threshold
        )
        config = TrajectoryConfig(phase_gap_threshold_minutes=10.0)
        detector = PhaseDetector(config)
        phases = detector.detect_phases(events)
        # Gap causes split even though same pattern type
        assert len(phases) >= 2

    def test_unknown_activities_grouped_separately(self):
        events = _make_events(
            ("QUERY_PATIENT", 0.0),
            ("CUSTOM_ACTION", 2.0),
            ("GIVE_DRUG", 4.0),
        )
        detector = PhaseDetector()
        phases = detector.detect_phases(events)
        assert any(p.phase_name == "unknown" for p in phases)

    def test_adjacent_same_phases_merged(self):
        events = _make_events(
            ("QUERY_A", 0.0),
            ("CUSTOM_X", 2.0),  # unknown
            ("QUERY_B", 4.0),
        )
        detector = PhaseDetector()
        phases = detector.detect_phases(events)
        # assessment, unknown, assessment -> after merge: only if adjacent
        # With "unknown" in between, they won't merge
        assert len(phases) == 3

    def test_empty_events_no_phases(self):
        detector = PhaseDetector()
        phases = detector.detect_phases([])
        assert len(phases) == 0

    def test_custom_phase_patterns(self):
        events = _make_events(
            ("BLOOD_DRAW", 0.0), ("BLOOD_TEST", 2.0),
        )
        config = TrajectoryConfig(
            phase_patterns={"lab_work": ["BLOOD_"]}
        )
        detector = PhaseDetector(config)
        phases = detector.detect_phases(events)
        assert len(phases) == 1
        assert phases[0].phase_name == "lab_work"

    def test_phase_ids_sequential(self):
        events = _make_events(
            ("QUERY_A", 0.0), ("GIVE_B", 2.0), ("MONITOR_C", 4.0),
        )
        detector = PhaseDetector()
        phases = detector.detect_phases(events)
        for i, phase in enumerate(phases):
            assert phase.phase_id == f"phase_{i + 1:03d}"


# ==================================================================
# TestBottleneckDetection
# ==================================================================

class TestBottleneckDetection:
    """Test bottleneck identification."""

    def test_tight_margin_is_bottleneck(self):
        events = _make_events(("A", 0.0), ("B", 28.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
            ),
        ]
        config = TrajectoryConfig(bottleneck_margin_threshold=5.0)
        analyzer = TrajectoryAnalyzer(config)
        bottlenecks = analyzer.detect_bottlenecks(events, constraints)
        # Margin = 30 - 28 = 2.0 < 5.0 threshold
        assert len(bottlenecks) == 1
        assert bottlenecks[0].timing_margin_minutes == pytest.approx(2.0)

    def test_wide_margin_not_bottleneck(self):
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
        config = TrajectoryConfig(bottleneck_margin_threshold=5.0)
        analyzer = TrajectoryAnalyzer(config)
        bottlenecks = analyzer.detect_bottlenecks(events, constraints)
        # Margin = 30 - 10 = 20.0 > 5.0 threshold
        assert len(bottlenecks) == 0

    def test_violated_constraint_max_urgency(self):
        events = _make_events(("A", 0.0), ("B", 40.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
            ),
        ]
        config = TrajectoryConfig(bottleneck_margin_threshold=5.0)
        analyzer = TrajectoryAnalyzer(config)
        bottlenecks = analyzer.detect_bottlenecks(events, constraints)
        assert len(bottlenecks) == 1
        assert bottlenecks[0].is_violated
        assert bottlenecks[0].urgency_score == 1.0

    def test_multiple_bottlenecks_sorted_by_urgency(self):
        events = _make_events(
            ("A", 0.0), ("B", 28.0), ("C", 0.0), ("D", 55.0),
        )
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
            ),
            TemporalConstraint(
                constraint_id="c2",
                constraint_type=TemporalConstraintType.MAX_DELAY,
                target_activity="D",
                max_minutes=60.0,
            ),
        ]
        config = TrajectoryConfig(bottleneck_margin_threshold=10.0)
        analyzer = TrajectoryAnalyzer(config)
        bottlenecks = analyzer.detect_bottlenecks(events, constraints)
        assert len(bottlenecks) == 2
        # Both have margin < 10: B has 2.0, D has 5.0
        assert bottlenecks[0].urgency_score >= bottlenecks[1].urgency_score

    def test_no_constraints_no_bottlenecks(self):
        events = _make_events(("A", 0.0), ("B", 10.0))
        analyzer = TrajectoryAnalyzer()
        bottlenecks = analyzer.detect_bottlenecks(events, [])
        assert len(bottlenecks) == 0

    def test_urgency_score_computation(self):
        events = _make_events(("A", 0.0), ("B", 27.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
            ),
        ]
        config = TrajectoryConfig(bottleneck_margin_threshold=10.0)
        analyzer = TrajectoryAnalyzer(config)
        bottlenecks = analyzer.detect_bottlenecks(events, constraints)
        # Margin = 3.0, threshold = 10.0, urgency = 1 - 3/10 = 0.7
        assert len(bottlenecks) == 1
        assert bottlenecks[0].urgency_score == pytest.approx(0.7)


# ==================================================================
# TestCriticalPath
# ==================================================================

class TestCriticalPath:
    """Test critical path computation."""

    def test_single_edge_critical_path(self):
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
        analyzer = TrajectoryAnalyzer()
        cp = analyzer.compute_critical_path(events, constraints)
        assert cp.path_length == 2
        assert cp.steps[0].activity_name == "A"
        assert cp.steps[1].activity_name == "B"

    def test_linear_chain_all_critical(self):
        events = _make_events(("A", 0.0), ("B", 10.0), ("C", 25.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.DEADLINE_CHAIN,
                chain_activities=["A", "B", "C"],
                chain_deadlines=[15.0, 20.0],
            ),
        ]
        analyzer = TrajectoryAnalyzer()
        cp = analyzer.compute_critical_path(events, constraints)
        assert cp.path_length == 3
        assert all(s.is_on_critical_path for s in cp.steps)

    def test_parallel_paths_longest_is_critical(self):
        events = _make_events(
            ("A", 0.0), ("B", 10.0), ("C", 20.0), ("D", 15.0),
        )
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=20.0,
            ),
            TemporalConstraint(
                constraint_id="c2",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="B",
                target_activity="C",
                max_minutes=30.0,
            ),
            TemporalConstraint(
                constraint_id="c3",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="D",
                max_minutes=10.0,
            ),
        ]
        analyzer = TrajectoryAnalyzer()
        cp = analyzer.compute_critical_path(events, constraints)
        # Path A->B->C has total weight 50, A->D has weight 10
        # Critical path should be A->B->C
        assert cp.total_duration_minutes == pytest.approx(50.0)
        activity_names = [s.activity_name for s in cp.steps]
        assert "A" in activity_names
        assert "C" in activity_names

    def test_empty_constraints_empty_path(self):
        events = _make_events(("A", 0.0), ("B", 10.0))
        analyzer = TrajectoryAnalyzer()
        cp = analyzer.compute_critical_path(events, [])
        assert cp.path_length == 0

    def test_bottleneck_step_identified(self):
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
        analyzer = TrajectoryAnalyzer()
        cp = analyzer.compute_critical_path(events, constraints)
        assert cp.bottleneck_step is not None

    def test_constraint_coverage_tracked(self):
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
        analyzer = TrajectoryAnalyzer()
        cp = analyzer.compute_critical_path(events, constraints)
        assert "c1" in cp.constraint_coverage

    def test_non_temporal_constraints_ignored(self):
        events = _make_events(("A", 0.0), ("B", 10.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.FREQUENCY,
                source_activity="A",
                min_count=2,
                max_minutes=60.0,
            ),
        ]
        analyzer = TrajectoryAnalyzer()
        cp = analyzer.compute_critical_path(events, constraints)
        # FREQUENCY doesn't create DAG edges
        assert cp.path_length == 0


# ==================================================================
# TestSensitivityAnalysis
# ==================================================================

class TestSensitivityAnalysis:
    """Test temporal sensitivity computation."""

    def test_tight_deadline_high_sensitivity(self):
        events = _make_events(("A", 0.0), ("B", 29.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
            ),
        ]
        config = TrajectoryConfig(
            enable_sensitivity_analysis=True,
            sensitivity_delta_minutes=2.0,
        )
        analyzer = TrajectoryAnalyzer(config)
        results = analyzer.compute_sensitivity(events, constraints)
        # Shifting B by +2 pushes from 29->31, exceeding 30 -> penalty increase
        b_result = next(r for r in results if r.activity_name == "B")
        assert b_result.sensitivity > 0

    def test_loose_deadline_low_sensitivity(self):
        events = _make_events(("A", 0.0), ("B", 5.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=60.0,
            ),
        ]
        config = TrajectoryConfig(
            enable_sensitivity_analysis=True,
            sensitivity_delta_minutes=1.0,
        )
        analyzer = TrajectoryAnalyzer(config)
        results = analyzer.compute_sensitivity(events, constraints)
        # B at 5+1=6, still well within 60 -> no penalty change
        b_result = next(r for r in results if r.activity_name == "B")
        assert b_result.sensitivity == pytest.approx(0.0)

    def test_no_constraints_zero_sensitivity(self):
        events = _make_events(("A", 0.0), ("B", 10.0))
        config = TrajectoryConfig(enable_sensitivity_analysis=True)
        analyzer = TrajectoryAnalyzer(config)
        results = analyzer.compute_sensitivity(events, [])
        assert len(results) == 0

    def test_critical_flag_set_correctly(self):
        events = _make_events(("A", 0.0), ("B", 29.5))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
                weight=5.0,
            ),
        ]
        config = TrajectoryConfig(
            enable_sensitivity_analysis=True,
            sensitivity_delta_minutes=1.0,
        )
        analyzer = TrajectoryAnalyzer(config)
        results = analyzer.compute_sensitivity(events, constraints)
        b_result = next(r for r in results if r.activity_name == "B")
        # Sensitivity = 5.0/1.0 = 5.0 > 0.5, so is_critical
        assert b_result.is_critical

    def test_results_sorted_by_sensitivity(self):
        events = _make_events(
            ("A", 0.0), ("B", 29.0), ("C", 5.0),
        )
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
            ),
        ]
        config = TrajectoryConfig(
            enable_sensitivity_analysis=True,
            sensitivity_delta_minutes=2.0,
        )
        analyzer = TrajectoryAnalyzer(config)
        results = analyzer.compute_sensitivity(events, constraints)
        # Should be sorted by |sensitivity| descending
        for i in range(len(results) - 1):
            assert abs(results[i].sensitivity) >= abs(results[i + 1].sensitivity)


# ==================================================================
# TestTrajectoryMetrics
# ==================================================================

class TestTrajectoryMetrics:
    """Test aggregate metrics computation."""

    def test_basic_metrics_computed(self):
        events = _make_events(
            ("A", 0.0), ("B", 10.0), ("C", 25.0),
        )
        analyzer = TrajectoryAnalyzer()
        metrics = analyzer.compute_metrics(events, [], [], None)
        assert metrics.event_count == 3
        assert metrics.unique_activities == 3
        assert metrics.total_duration_minutes == pytest.approx(25.0)

    def test_duration_from_first_to_last_event(self):
        events = _make_events(("A", 5.0), ("B", 15.0), ("C", 35.0))
        analyzer = TrajectoryAnalyzer()
        metrics = analyzer.compute_metrics(events, [], [], None)
        assert metrics.total_duration_minutes == pytest.approx(30.0)

    def test_avg_gap_computation(self):
        events = _make_events(("A", 0.0), ("B", 10.0), ("C", 30.0))
        analyzer = TrajectoryAnalyzer()
        metrics = analyzer.compute_metrics(events, [], [], None)
        # Gaps: 10, 20 -> avg = 15
        assert metrics.avg_inter_event_gap == pytest.approx(15.0)

    def test_max_gap_computation(self):
        events = _make_events(("A", 0.0), ("B", 10.0), ("C", 30.0))
        analyzer = TrajectoryAnalyzer()
        metrics = analyzer.compute_metrics(events, [], [], None)
        assert metrics.max_inter_event_gap == pytest.approx(20.0)

    def test_overall_urgency_aggregation(self):
        bottlenecks = [
            BottleneckInfo("A", 0, 0.0, 2.0, urgency_score=0.8),
            BottleneckInfo("B", 1, 5.0, 1.0, urgency_score=0.6),
        ]
        events = _make_events(("A", 0.0), ("B", 5.0))
        analyzer = TrajectoryAnalyzer()
        metrics = analyzer.compute_metrics(events, [], bottlenecks, None)
        assert metrics.overall_urgency == pytest.approx(0.7)

    def test_empty_trace_zero_metrics(self):
        analyzer = TrajectoryAnalyzer()
        metrics = analyzer.compute_metrics([], [], [], None)
        assert metrics.event_count == 0
        assert metrics.total_duration_minutes == 0.0
        assert metrics.avg_inter_event_gap == 0.0


# ==================================================================
# TestTrajectoryAnalyzerIntegration
# ==================================================================

class TestTrajectoryAnalyzerIntegration:
    """Test full analysis pipeline."""

    def test_full_analysis_clinical_scenario(self):
        events = _make_events(
            ("QUERY_PATIENT", 0.0),
            ("QUERY_LABS", 2.0),
            ("DIAGNOSE_SEPSIS", 5.0),
            ("GIVE_ANTIBIOTICS", 8.0),
            ("GIVE_FLUIDS", 10.0),
            ("MONITOR_VITALS", 15.0),
            ("REASSESS_PATIENT", 25.0),
        )
        constraints = [
            TemporalConstraint(
                constraint_id="c_ab",
                constraint_type=TemporalConstraintType.MAX_DELAY,
                target_activity="GIVE_ANTIBIOTICS",
                max_minutes=60.0,
            ),
        ]
        config = TrajectoryConfig(
            enable_phase_detection=True,
            enable_bottleneck_detection=True,
            enable_critical_path=True,
        )
        analyzer = TrajectoryAnalyzer(config)
        result = analyzer.analyze(events, constraints)

        assert len(result.phases) > 0
        assert result.metrics.event_count == 7
        assert result.metrics.total_duration_minutes == pytest.approx(25.0)

    def test_analysis_with_no_constraints(self):
        events = _make_events(("A", 0.0), ("B", 5.0), ("C", 10.0))
        analyzer = TrajectoryAnalyzer()
        result = analyzer.analyze(events)
        assert len(result.bottlenecks) == 0
        # No constraints -> no critical path to compute
        assert result.critical_path is None

    def test_config_disables_components(self):
        events = _make_events(
            ("QUERY_A", 0.0), ("GIVE_B", 5.0),
        )
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="QUERY_A",
                target_activity="GIVE_B",
                max_minutes=30.0,
            ),
        ]
        config = TrajectoryConfig(
            enable_phase_detection=False,
            enable_bottleneck_detection=False,
            enable_critical_path=False,
        )
        analyzer = TrajectoryAnalyzer(config)
        result = analyzer.analyze(events, constraints)
        assert result.phases == []
        assert result.bottlenecks == []
        assert result.critical_path is None

    def test_phase_transitions_recorded(self):
        events = _make_events(
            ("QUERY_A", 0.0), ("QUERY_B", 2.0),
            ("GIVE_MED", 5.0), ("PRESCRIBE_X", 7.0),
        )
        analyzer = TrajectoryAnalyzer()
        result = analyzer.analyze(events)
        assert len(result.phase_transitions) > 0
        assert result.phase_transitions[0]["from_phase"] == "assessment"
        assert result.phase_transitions[0]["to_phase"] == "treatment"

    def test_metrics_include_phase_count(self):
        events = _make_events(
            ("QUERY_A", 0.0), ("GIVE_B", 5.0), ("MONITOR_C", 10.0),
        )
        analyzer = TrajectoryAnalyzer()
        result = analyzer.analyze(events)
        assert result.metrics.phase_count == len(result.phases)

    def test_sensitivity_enabled(self):
        events = _make_events(("A", 0.0), ("B", 29.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
            ),
        ]
        config = TrajectoryConfig(
            enable_sensitivity_analysis=True,
            sensitivity_delta_minutes=2.0,
        )
        analyzer = TrajectoryAnalyzer(config)
        result = analyzer.analyze(events, constraints)
        assert len(result.sensitivity_results) > 0


# ==================================================================
# TestIntegrationWithTemporalVerifier
# ==================================================================

class TestIntegrationWithTemporalVerifier:
    """Test integration between trajectory analyzer and temporal verifier."""

    def test_bottleneck_matches_temporal_violation(self):
        events = _make_events(("A", 0.0), ("B", 35.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=30.0,
            ),
        ]
        # Verify violation
        verifier = TemporalVerifier()
        result = verifier.verify(events, constraints)
        assert result.violated_count == 1

        # Bottleneck should detect this too
        config = TrajectoryConfig(bottleneck_margin_threshold=10.0)
        analyzer = TrajectoryAnalyzer(config)
        bottlenecks = analyzer.detect_bottlenecks(events, constraints)
        assert len(bottlenecks) == 1
        assert bottlenecks[0].is_violated

    def test_critical_path_reflects_constraint_deadlines(self):
        events = _make_events(("A", 0.0), ("B", 10.0), ("C", 30.0))
        constraints = [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="A",
                target_activity="B",
                max_minutes=20.0,
            ),
            TemporalConstraint(
                constraint_id="c2",
                constraint_type=TemporalConstraintType.BOUNDED_RESPONSE,
                source_activity="B",
                target_activity="C",
                max_minutes=40.0,
            ),
        ]
        analyzer = TrajectoryAnalyzer()
        cp = analyzer.compute_critical_path(events, constraints)
        # Total critical path: A->B(20) + B->C(40) = 60
        assert cp.total_duration_minutes == pytest.approx(60.0)
        assert cp.path_length == 3

    def test_phase_detection_independent_of_constraints(self):
        events = _make_events(
            ("QUERY_A", 0.0), ("GIVE_B", 5.0),
        )
        analyzer = TrajectoryAnalyzer()
        result_no_constraints = analyzer.analyze(events)
        result_with_constraints = analyzer.analyze(events, [
            TemporalConstraint(
                constraint_id="c1",
                constraint_type=TemporalConstraintType.MAX_DELAY,
                target_activity="GIVE_B",
                max_minutes=60.0,
            ),
        ])
        assert len(result_no_constraints.phases) == len(result_with_constraints.phases)

    def test_deadline_chain_creates_critical_path(self):
        events = _make_events(
            ("TRIAGE", 0.0), ("ASSESS", 5.0), ("TREAT", 15.0),
        )
        constraints = [
            TemporalConstraint(
                constraint_id="chain_1",
                constraint_type=TemporalConstraintType.DEADLINE_CHAIN,
                chain_activities=["TRIAGE", "ASSESS", "TREAT"],
                chain_deadlines=[10.0, 20.0],
            ),
        ]
        analyzer = TrajectoryAnalyzer()
        cp = analyzer.compute_critical_path(events, constraints)
        # Chain: TRIAGE->(10)->ASSESS->(20)->TREAT, total=30
        assert cp.total_duration_minutes == pytest.approx(30.0)
        assert cp.path_length == 3
        activity_names = [s.activity_name for s in cp.steps]
        assert activity_names == ["TRIAGE", "ASSESS", "TREAT"]
