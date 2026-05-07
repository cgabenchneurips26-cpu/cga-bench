"""Tests for enhanced conformance scoring features."""
import math
import pytest

from cga_bench.cpg_model.schemas.conformance import (
    ConstraintTemplate,
    HardGraph,
    HardPhase,
    SoftConstraint,
    SoftConstraints,
)
from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.conformance.scorer import (
    ConformanceReport,
    ConstraintViolation,
    ScoringConfig,
    SubScores,
    SynergisticRule,
    TimingPenaltyConfig,
    evaluate_conformance,
    _apply_evidence_weight,
    _apply_synergistic_harm,
    _compute_sub_scores,
    _graduated_timing_weight,
)


# --- Fixtures ---

def _make_hard_graph(
    phases=None, edges=None, required_phases=None, phase_map=None
):
    return HardGraph(
        cpg_id="test_cpg",
        phases=phases or [
            HardPhase(phase_id="assessment", name="Assessment"),
            HardPhase(phase_id="treatment", name="Treatment"),
            HardPhase(phase_id="monitoring", name="Monitoring"),
        ],
        edges=edges or [["assessment", "treatment"], ["treatment", "monitoring"]],
        required_phases=required_phases or ["assessment", "treatment", "monitoring"],
        phase_map=phase_map or {
            "QUERY_PATIENT": "assessment",
            "QUERY_OBSERVATION": "assessment",
            "PRESCRIBE": "treatment",
            "ORDER_TEST": "treatment",
            "QUERY_LACTATE": "monitoring",
        },
    )


def _make_soft_constraints(constraints=None, activity_aliases=None):
    return SoftConstraints(
        cpg_id="test_cpg",
        constraints=constraints or [],
        activity_aliases=activity_aliases or {},
    )


def _make_event(name, timestamp_min=0.0):
    return ActivityEvent(
        name=name, timestamp_min=timestamp_min, raw_event={}
    )


# --- TestGraduatedTiming ---

class TestGraduatedTiming:
    """Test graduated timing penalty modes."""

    def test_binary_mode_returns_base_weight(self):
        config = TimingPenaltyConfig(mode="binary")
        result = _graduated_timing_weight(5.0, 20.0, 10.0, config)
        assert result == 5.0

    def test_linear_within_grace_returns_zero(self):
        config = TimingPenaltyConfig(mode="linear", grace_period_minutes=5.0)
        # Actual delay=12, window=10, grace=5 → overshoot=12-10-5=-3 → 0
        result = _graduated_timing_weight(5.0, 12.0, 10.0, config)
        assert result == 0.0

    def test_linear_small_overshoot(self):
        config = TimingPenaltyConfig(mode="linear", grace_period_minutes=0.0)
        # Actual delay=12, window=10 → overshoot=2, scale=2/10=0.2
        result = _graduated_timing_weight(5.0, 12.0, 10.0, config)
        assert abs(result - 5.0 * 0.2) < 0.01

    def test_linear_large_overshoot_capped(self):
        config = TimingPenaltyConfig(
            mode="linear", grace_period_minutes=0.0, max_penalty_multiplier=2.0
        )
        # Actual delay=50, window=10 → overshoot=40, scale=40/10=4 → capped at 2
        result = _graduated_timing_weight(5.0, 50.0, 10.0, config)
        assert abs(result - 5.0 * 2.0) < 0.01

    def test_linear_minimum_10_percent(self):
        config = TimingPenaltyConfig(mode="linear", grace_period_minutes=0.0)
        # Very small overshoot → scale might be < 0.1 → clamped to 0.1
        result = _graduated_timing_weight(10.0, 10.01, 10.0, config)
        assert result >= 10.0 * 0.1

    def test_logarithmic_mode_basic(self):
        config = TimingPenaltyConfig(
            mode="logarithmic", half_life_minutes=30.0, grace_period_minutes=0.0
        )
        # Actual delay=40, window=10 → overshoot=30
        # scale = log2(1 + 30/30) = log2(2) = 1.0
        result = _graduated_timing_weight(5.0, 40.0, 10.0, config)
        assert abs(result - 5.0 * 1.0) < 0.01

    def test_logarithmic_capped(self):
        config = TimingPenaltyConfig(
            mode="logarithmic", half_life_minutes=5.0,
            max_penalty_multiplier=2.0, grace_period_minutes=0.0,
        )
        # Very large overshoot → log2 would be huge → capped at 2.0
        result = _graduated_timing_weight(5.0, 500.0, 10.0, config)
        assert abs(result - 5.0 * 2.0) < 0.01

    def test_logarithmic_within_grace(self):
        config = TimingPenaltyConfig(
            mode="logarithmic", half_life_minutes=30.0, grace_period_minutes=10.0
        )
        # Actual delay=15, window=10, grace=10 → overshoot=15-10-10=-5 → 0
        result = _graduated_timing_weight(5.0, 15.0, 10.0, config)
        assert result == 0.0

    def test_unknown_mode_returns_base_weight(self):
        config = TimingPenaltyConfig(mode="unknown_mode")
        result = _graduated_timing_weight(5.0, 20.0, 10.0, config)
        assert result == 5.0


class TestEvidenceWeighting:
    """Test evidence level multipliers."""

    def test_1a_full_weight(self):
        assert _apply_evidence_weight(10.0, "1A") == 10.0

    def test_1b_95_percent(self):
        assert abs(_apply_evidence_weight(10.0, "1B") - 9.5) < 0.01

    def test_2a_85_percent(self):
        assert abs(_apply_evidence_weight(10.0, "2A") - 8.5) < 0.01

    def test_2b_75_percent(self):
        assert abs(_apply_evidence_weight(10.0, "2B") - 7.5) < 0.01

    def test_2c_65_percent(self):
        assert abs(_apply_evidence_weight(10.0, "2C") - 6.5) < 0.01

    def test_3_50_percent(self):
        assert abs(_apply_evidence_weight(10.0, "3") - 5.0) < 0.01

    def test_none_returns_full_weight(self):
        assert _apply_evidence_weight(10.0, None) == 10.0

    def test_unknown_level_returns_full_weight(self):
        assert _apply_evidence_weight(10.0, "unknown") == 10.0

    def test_case_insensitive(self):
        assert abs(_apply_evidence_weight(10.0, "1a") - 10.0) < 0.01
        assert abs(_apply_evidence_weight(10.0, "2c") - 6.5) < 0.01


class TestSynergisticHarm:
    """Test synergistic harm penalty computation."""

    def test_no_rules_returns_zero(self):
        violations = [
            ConstraintViolation("c1", "existence", "req", "detail", 5.0),
        ]
        assert _apply_synergistic_harm(violations, []) == 0.0

    def test_partial_match_no_penalty(self):
        violations = [
            ConstraintViolation("c1", "existence", "req", "detail", 5.0),
        ]
        rule = SynergisticRule(
            rule_id="combo", required_violations=["c1", "c2"], multiplier=1.5
        )
        assert _apply_synergistic_harm(violations, [rule]) == 0.0

    def test_full_match_applies_penalty(self):
        violations = [
            ConstraintViolation("c1", "existence", "req", "detail", 5.0),
            ConstraintViolation("c2", "response", "req", "detail", 3.0),
        ]
        rule = SynergisticRule(
            rule_id="combo", required_violations=["c1", "c2"], multiplier=1.5
        )
        # Combined weight = 5+3=8, extra = 8*(1.5-1.0) = 4.0
        result = _apply_synergistic_harm(violations, [rule])
        assert abs(result - 4.0) < 0.01

    def test_multiple_rules(self):
        violations = [
            ConstraintViolation("c1", "existence", "req", "detail", 5.0),
            ConstraintViolation("c2", "response", "req", "detail", 3.0),
            ConstraintViolation("c3", "precedence", "req", "detail", 2.0),
        ]
        rules = [
            SynergisticRule(rule_id="r1", required_violations=["c1", "c2"], multiplier=1.5),
            SynergisticRule(rule_id="r2", required_violations=["c2", "c3"], multiplier=2.0),
        ]
        # r1: combined=8, extra=8*0.5=4.0
        # r2: combined=5, extra=5*1.0=5.0
        result = _apply_synergistic_harm(violations, rules)
        assert abs(result - 9.0) < 0.01

    def test_high_multiplier(self):
        violations = [
            ConstraintViolation("c1", "existence", "req", "detail", 10.0),
            ConstraintViolation("c2", "response", "req", "detail", 10.0),
        ]
        rule = SynergisticRule(
            rule_id="severe", required_violations=["c1", "c2"], multiplier=3.0
        )
        # Combined=20, extra=20*(3-1)=40
        result = _apply_synergistic_harm(violations, [rule])
        assert abs(result - 40.0) < 0.01


class TestSubScores:
    """Test sub-score computation."""

    def test_perfect_compliance(self):
        phase_result = {
            "phases_present": ["assessment", "treatment", "monitoring"],
            "missing_phases": [],
            "phase_order_violations": [],
        }
        hard_graph = _make_hard_graph()
        violations = []
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="timing1",
                template=ConstraintTemplate.RESPONSE_WITHIN,
                A="QUERY_PATIENT", B="PRESCRIBE",
                window_minutes=10.0,
            ),
        ])
        sub = _compute_sub_scores(phase_result, hard_graph, violations, soft)
        assert sub.completeness == 1.0
        assert sub.ordering == 1.0
        assert sub.timeliness == 1.0
        assert sub.safety == 1.0

    def test_missing_phase_reduces_completeness(self):
        phase_result = {
            "phases_present": ["assessment", "treatment"],
            "missing_phases": ["monitoring"],
            "phase_order_violations": [],
        }
        hard_graph = _make_hard_graph()
        sub = _compute_sub_scores(
            phase_result, hard_graph, [], _make_soft_constraints()
        )
        # 2 of 3 required present
        assert abs(sub.completeness - 2.0/3.0) < 0.01

    def test_order_violation_reduces_ordering(self):
        phase_result = {
            "phases_present": ["assessment", "treatment", "monitoring"],
            "missing_phases": [],
            "phase_order_violations": ["treatment before assessment"],
        }
        hard_graph = _make_hard_graph()  # 2 edges
        sub = _compute_sub_scores(
            phase_result, hard_graph, [], _make_soft_constraints()
        )
        # 1 violation out of 2 edges
        assert abs(sub.ordering - 0.5) < 0.01

    def test_timing_violation_reduces_timeliness(self):
        phase_result = {
            "phases_present": ["assessment"],
            "missing_phases": [],
            "phase_order_violations": [],
        }
        hard_graph = _make_hard_graph()
        violations = [
            ConstraintViolation("c1", "response_within", "req", "late", 5.0),
        ]
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="c1",
                template=ConstraintTemplate.RESPONSE_WITHIN,
                A="A", B="B", window_minutes=10.0,
            ),
            SoftConstraint(
                constraint_id="c2",
                template=ConstraintTemplate.RESPONSE_WITHIN,
                A="C", B="D", window_minutes=5.0,
            ),
        ])
        sub = _compute_sub_scores(phase_result, hard_graph, violations, soft)
        # 1 violation out of 2 timing constraints
        assert abs(sub.timeliness - 0.5) < 0.01

    def test_safety_violation_reduces_safety(self):
        phase_result = {
            "phases_present": [],
            "missing_phases": [],
            "phase_order_violations": [],
        }
        hard_graph = _make_hard_graph()
        violations = [
            ConstraintViolation("s1", "not_succession", "req", "bad", 10.0),
        ]
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="s1",
                template=ConstraintTemplate.NOT_SUCCESSION,
                A="A", B="B",
            ),
        ])
        sub = _compute_sub_scores(phase_result, hard_graph, violations, soft)
        assert sub.safety == 0.0

    def test_no_timing_constraints_timeliness_1(self):
        phase_result = {
            "phases_present": [],
            "missing_phases": [],
            "phase_order_violations": [],
        }
        hard_graph = _make_hard_graph()
        # Only existence constraints, no timing
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="e1",
                template=ConstraintTemplate.EXISTENCE,
                A="QUERY_PATIENT",
            ),
        ])
        sub = _compute_sub_scores(phase_result, hard_graph, [], soft)
        assert sub.timeliness == 1.0

    def test_no_safety_constraints_safety_1(self):
        phase_result = {
            "phases_present": [],
            "missing_phases": [],
            "phase_order_violations": [],
        }
        hard_graph = _make_hard_graph()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="e1",
                template=ConstraintTemplate.EXISTENCE,
                A="QUERY_PATIENT",
            ),
        ])
        sub = _compute_sub_scores(phase_result, hard_graph, [], soft)
        assert sub.safety == 1.0


class TestScoringConfigIntegration:
    """Test ScoringConfig integration with evaluate_conformance."""

    def test_no_config_backward_compatible(self):
        events = [
            _make_event("QUERY_PATIENT", 0.0),
            _make_event("PRESCRIBE", 5.0),
        ]
        hard_graph = _make_hard_graph()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="exist_patient",
                template=ConstraintTemplate.EXISTENCE,
                A="QUERY_PATIENT", weight=3.0,
            ),
        ])
        report = evaluate_conformance(events, hard_graph, soft, {})
        assert report.sub_scores is None  # No config → no sub_scores
        assert report.compliance_score > 0

    def test_config_enables_sub_scores(self):
        events = [
            _make_event("QUERY_PATIENT", 0.0),
            _make_event("PRESCRIBE", 5.0),
        ]
        hard_graph = _make_hard_graph()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="exist_patient",
                template=ConstraintTemplate.EXISTENCE,
                A="QUERY_PATIENT", weight=3.0,
            ),
        ])
        config = ScoringConfig(enable_sub_scores=True)
        report = evaluate_conformance(events, hard_graph, soft, {}, scoring_config=config)
        assert report.sub_scores is not None
        assert isinstance(report.sub_scores, SubScores)

    def test_evidence_weighting_reduces_violation_cost(self):
        events = [_make_event("QUERY_PATIENT", 0.0)]
        hard_graph = _make_hard_graph()
        # Missing PRESCRIBE existence constraint with evidence_level="3"
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="exist_prescribe",
                template=ConstraintTemplate.EXISTENCE,
                A="PRESCRIBE", weight=10.0,
                evidence_level="3",  # 50% multiplier
            ),
        ])

        # Without evidence weighting
        config_no_ew = ScoringConfig(enable_evidence_weighting=False)
        report_no_ew = evaluate_conformance(
            events, hard_graph, soft, {}, scoring_config=config_no_ew
        )

        # With evidence weighting
        config_ew = ScoringConfig(enable_evidence_weighting=True)
        report_ew = evaluate_conformance(
            events, hard_graph, soft, {}, scoring_config=config_ew
        )

        # Evidence weighting should reduce the cost
        assert report_ew.compliance_cost < report_no_ew.compliance_cost
        # The violation weight should be 10*0.5=5.0
        assert abs(report_ew.compliance_cost - 5.0) < 0.01
        assert abs(report_no_ew.compliance_cost - 10.0) < 0.01

    def test_synergistic_harm_increases_cost(self):
        events = [_make_event("QUERY_PATIENT", 0.0)]
        hard_graph = _make_hard_graph()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="c1",
                template=ConstraintTemplate.EXISTENCE,
                A="PRESCRIBE", weight=5.0,
            ),
            SoftConstraint(
                constraint_id="c2",
                template=ConstraintTemplate.EXISTENCE,
                A="ORDER_TEST", weight=3.0,
            ),
        ])

        # Without synergistic rules
        config_no_synergy = ScoringConfig(synergistic_rules=[])
        report_no = evaluate_conformance(
            events, hard_graph, soft, {}, scoring_config=config_no_synergy
        )

        # With synergistic rules
        config_synergy = ScoringConfig(synergistic_rules=[
            SynergisticRule(
                rule_id="double_omission",
                required_violations=["c1", "c2"],
                multiplier=1.5,
            ),
        ])
        report_yes = evaluate_conformance(
            events, hard_graph, soft, {}, scoring_config=config_synergy
        )

        # Synergy should increase cost
        assert report_yes.compliance_cost > report_no.compliance_cost
        # Base cost = 5+3=8, synergy extra = 8*0.5=4 → total=12
        assert abs(report_yes.compliance_cost - 12.0) < 0.01

    def test_graduated_timing_in_response_within(self):
        # A occurs at t=0, B occurs at t=15 → 5min late for 10min window
        events = [
            _make_event("QUERY_PATIENT", 0.0),
            _make_event("PRESCRIBE", 15.0),
        ]
        hard_graph = _make_hard_graph()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="timing_c",
                template=ConstraintTemplate.RESPONSE_WITHIN,
                A="QUERY_PATIENT", B="PRESCRIBE",
                window_minutes=10.0, weight=10.0,
            ),
        ])

        # Binary mode: full penalty
        config_binary = ScoringConfig(
            timing_penalty=TimingPenaltyConfig(mode="binary")
        )
        report_binary = evaluate_conformance(
            events, hard_graph, soft, {}, scoring_config=config_binary
        )

        # Linear mode: reduced penalty (overshoot=5, scale=5/10=0.5)
        config_linear = ScoringConfig(
            timing_penalty=TimingPenaltyConfig(mode="linear")
        )
        report_linear = evaluate_conformance(
            events, hard_graph, soft, {}, scoring_config=config_linear
        )

        assert report_binary.compliance_cost == 10.0
        assert abs(report_linear.compliance_cost - 5.0) < 0.01

    def test_custom_cost_scale(self):
        events = [_make_event("QUERY_PATIENT", 0.0)]
        hard_graph = _make_hard_graph()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="c1",
                template=ConstraintTemplate.EXISTENCE,
                A="PRESCRIBE", weight=5.0,
            ),
        ])

        config_small_scale = ScoringConfig(cost_scale=5.0)
        report = evaluate_conformance(
            events, hard_graph, soft, {}, scoring_config=config_small_scale
        )
        expected_score = math.exp(-5.0 / 5.0)
        assert abs(report.compliance_score - expected_score) < 0.001

    def test_response_within_no_b_activity_records_delay(self):
        # A occurs at t=0, no B at all
        events = [_make_event("QUERY_PATIENT", 0.0)]
        hard_graph = _make_hard_graph()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="timing_c",
                template=ConstraintTemplate.RESPONSE_WITHIN,
                A="QUERY_PATIENT", B="PRESCRIBE",
                window_minutes=10.0, weight=10.0,
            ),
        ])
        config = ScoringConfig(
            timing_penalty=TimingPenaltyConfig(mode="linear")
        )
        report = evaluate_conformance(
            events, hard_graph, soft, {}, scoring_config=config
        )
        # B never occurred → best_delay is None → falls through to base weight
        assert len(report.constraint_violations) == 1
        v = report.constraint_violations[0]
        assert v.actual_delay_minutes is None
        assert v.weight == 10.0  # No graduated timing when B is absent


class TestBackwardCompatibility:
    """Ensure enhanced scorer doesn't break existing behavior."""

    def test_no_config_same_as_before(self):
        events = [
            _make_event("QUERY_PATIENT", 0.0),
            _make_event("PRESCRIBE", 5.0),
            _make_event("QUERY_LACTATE", 8.0),
        ]
        hard_graph = _make_hard_graph()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="exist",
                template=ConstraintTemplate.EXISTENCE,
                A="QUERY_PATIENT", weight=3.0,
            ),
            SoftConstraint(
                constraint_id="resp",
                template=ConstraintTemplate.RESPONSE,
                A="QUERY_PATIENT", B="PRESCRIBE", weight=5.0,
            ),
        ])
        report = evaluate_conformance(events, hard_graph, soft, {})
        # No violations expected (all satisfied)
        assert report.compliance_cost == 0.0
        assert report.compliance_score == 1.0
        assert report.sub_scores is None

    def test_violation_weight_unchanged_without_config(self):
        events = [_make_event("QUERY_PATIENT", 0.0)]
        hard_graph = _make_hard_graph()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="exist_prescribe",
                template=ConstraintTemplate.EXISTENCE,
                A="PRESCRIBE", weight=7.0,
                evidence_level="2C",  # Should be ignored without config
            ),
        ])
        report = evaluate_conformance(events, hard_graph, soft, {})
        # evidence_level ignored → full weight
        assert abs(report.compliance_cost - 7.0) < 0.01

    def test_cost_scale_parameter_still_works(self):
        events = [_make_event("QUERY_PATIENT", 0.0)]
        hard_graph = _make_hard_graph()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="c1",
                template=ConstraintTemplate.EXISTENCE,
                A="PRESCRIBE", weight=5.0,
            ),
        ])
        report = evaluate_conformance(
            events, hard_graph, soft, {}, cost_scale=20.0
        )
        expected = math.exp(-5.0 / 20.0)
        assert abs(report.compliance_score - expected) < 0.001

    def test_scoring_config_cost_scale_overrides_parameter(self):
        events = [_make_event("QUERY_PATIENT", 0.0)]
        hard_graph = _make_hard_graph()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="c1",
                template=ConstraintTemplate.EXISTENCE,
                A="PRESCRIBE", weight=5.0,
            ),
        ])
        config = ScoringConfig(cost_scale=20.0)
        report = evaluate_conformance(
            events, hard_graph, soft, {},
            cost_scale=10.0,  # Should be overridden by config
            scoring_config=config,
        )
        expected = math.exp(-5.0 / 20.0)
        assert abs(report.compliance_score - expected) < 0.001

    def test_constraint_violation_has_delay_fields(self):
        events = [
            _make_event("QUERY_PATIENT", 0.0),
            _make_event("PRESCRIBE", 20.0),
        ]
        hard_graph = _make_hard_graph()
        soft = _make_soft_constraints([
            SoftConstraint(
                constraint_id="timing",
                template=ConstraintTemplate.RESPONSE_WITHIN,
                A="QUERY_PATIENT", B="PRESCRIBE",
                window_minutes=10.0, weight=5.0,
            ),
        ])
        report = evaluate_conformance(events, hard_graph, soft, {})
        assert len(report.constraint_violations) == 1
        v = report.constraint_violations[0]
        assert v.actual_delay_minutes == 20.0
        assert v.window_minutes == 10.0
