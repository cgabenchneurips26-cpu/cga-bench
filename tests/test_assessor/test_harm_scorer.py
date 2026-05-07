from __future__ import annotations

import pytest

from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig, MetricsReporter
from cga_bench.cpg_model.schemas.base import (
    CGAScore,
    EpisodeLog,
    HarmSeverity,
    RecommendationClass,
    ViolationEvent,
    ViolationType,
)

_SEVERITY_WEIGHTS = {
    HarmSeverity.MINOR: 0.1,
    HarmSeverity.MODERATE: 0.4,
    HarmSeverity.MAJOR: 0.7,
    HarmSeverity.SEVERE: 0.9,
    HarmSeverity.CATASTROPHIC: 1.0,
}

_GUIDELINE_WEIGHTS = {
    RecommendationClass.CLASS_I: 1.0,
    RecommendationClass.CLASS_IIA: 0.8,
    RecommendationClass.CLASS_IIB: 0.6,
    RecommendationClass.CLASS_III: 0.3,
    None: 0.5,
}

_TYPE_WEIGHTS = {
    ViolationType.OMISSION: 1.0,
    ViolationType.COMMISSION: 1.5,
    ViolationType.TIMING: 0.8,
    ViolationType.SEQUENCE: 0.7,
    ViolationType.DEVIATION: 0.5,
}


def _config() -> HarmScorerConfig:
    return HarmScorerConfig(
        severity_weights=_SEVERITY_WEIGHTS,
        guideline_strength_weights=_GUIDELINE_WEIGHTS,
        violation_type_weights=_TYPE_WEIGHTS,
    )


def _episode(episode_id: str = "ep1") -> EpisodeLog:
    return EpisodeLog(
        episode_id=episode_id,
        scenario_id="sc1",
        agent_id="ag1",
        states=[],
        actions=[],
        observations=[],
        total_duration_minutes=60.0,
        total_llm_calls=5,
        total_tokens=1000,
        total_tool_calls=10,
        termination_reason="success",
    )


def _violation(
    violation_id: str = "v1",
    vtype: ViolationType = ViolationType.OMISSION,
    severity: HarmSeverity = HarmSeverity.MODERATE,
    guideline_class: RecommendationClass | None = RecommendationClass.CLASS_I,
    preventability: float = 1.0,
) -> ViolationEvent:
    return ViolationEvent(
        violation_id=violation_id,
        violation_type=vtype,
        timestamp_minutes=10.0,
        state_at_violation="s1",
        node_at_violation="n1",
        harm_severity=severity,
        guideline_class=guideline_class,
        preventability=preventability,
        description="test violation",
        guideline_reference="SSC 2021",
    )


class TestHarmScorerInit:
    def test_config_required(self):
        with pytest.raises(ValueError, match="config is required"):
            HarmScorer(total_mandatory_count=5, config=None)

    def test_mandatory_count_must_be_positive(self):
        with pytest.raises(ValueError, match="total_mandatory_count must be positive"):
            HarmScorer(total_mandatory_count=0, config=_config())

    def test_valid_init(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        assert scorer.total_mandatory_count == 5


class TestComputeScore:
    def test_no_violations_perfect_score(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        score = scorer.compute_score([], _episode())
        assert score.compliance_score == 1.0
        assert score.peak_risk == 0.0
        assert score.aggregate_risk == 0.0
        assert score.total_violations == 0

    def test_single_violation_reduces_compliance(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        v = _violation()
        score = scorer.compute_score([v], _episode())
        assert score.compliance_score == pytest.approx(0.8)
        assert score.total_violations == 1
        assert score.peak_risk > 0
        assert score.aggregate_risk > 0

    def test_multiple_violations(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        violations = [_violation(f"v{i}") for i in range(3)]
        score = scorer.compute_score(violations, _episode())
        assert score.compliance_score == pytest.approx(0.4)
        assert score.total_violations == 3

    def test_violations_exceed_mandatory_compliance_floors_at_zero(self):
        scorer = HarmScorer(total_mandatory_count=2, config=_config())
        violations = [_violation(f"v{i}") for i in range(5)]
        score = scorer.compute_score(violations, _episode())
        assert score.compliance_score == 0.0

    def test_episode_id_propagated(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        score = scorer.compute_score([], _episode("my_ep"))
        assert score.episode_id == "my_ep"

    def test_budget_usage_populated(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        ep = _episode()
        score = scorer.compute_score([], ep)
        assert score.budget_usage["llm_calls"] == 5
        assert score.budget_usage["tokens"] == 1000
        assert score.budget_usage["tool_calls"] == 10

    def test_violations_by_type_counted(self):
        scorer = HarmScorer(total_mandatory_count=10, config=_config())
        violations = [
            _violation("v1", ViolationType.OMISSION),
            _violation("v2", ViolationType.OMISSION),
            _violation("v3", ViolationType.COMMISSION),
        ]
        score = scorer.compute_score(violations, _episode())
        assert score.violations_by_type["omission"] == 2
        assert score.violations_by_type["commission"] == 1


class TestComputeWeight:
    def test_weight_formula(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        v = _violation(
            severity=HarmSeverity.MODERATE,
            guideline_class=RecommendationClass.CLASS_I,
            preventability=1.0,
            vtype=ViolationType.OMISSION,
        )
        weight = scorer._compute_weight(v)
        expected = 0.4 * 1.0 * 1.0 * 1.0
        assert weight == pytest.approx(expected)

    def test_weight_with_partial_preventability(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        v = _violation(preventability=0.5)
        weight = scorer._compute_weight(v)
        expected = 0.4 * 1.0 * 0.5 * 1.0
        assert weight == pytest.approx(expected)

    def test_weight_none_guideline_class(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        v = _violation(guideline_class=None)
        weight = scorer._compute_weight(v)
        expected = 0.4 * 0.5 * 1.0 * 1.0
        assert weight == pytest.approx(expected)

    def test_commission_type_weight_higher(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        v_omission = _violation(vtype=ViolationType.OMISSION)
        v_commission = _violation(vtype=ViolationType.COMMISSION)
        assert scorer._compute_weight(v_commission) > scorer._compute_weight(v_omission)


class TestComputeHarm:
    def test_harm_returns_severity_weight(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        for sev, expected in _SEVERITY_WEIGHTS.items():
            v = _violation(severity=sev)
            assert scorer._compute_harm(v) == pytest.approx(expected)


class TestSubScores:
    def test_no_violations_all_perfect(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        score = scorer.compute_score([], _episode())
        for k, v in score.sub_scores.items():
            assert v == pytest.approx(1.0), f"{k} should be 1.0"

    def test_c1_path_selection_with_deviation(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        v = _violation(vtype=ViolationType.DEVIATION)
        score = scorer.compute_score([v], _episode())
        assert score.sub_scores["C1_path_selection"] == pytest.approx(0.8)

    def test_c2_mandatory_completion_with_omission(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        v = _violation(vtype=ViolationType.OMISSION)
        score = scorer.compute_score([v], _episode())
        assert score.sub_scores["C2_mandatory_completion"] == pytest.approx(0.8)

    def test_c3_forbidden_avoidance_with_commission(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        v = _violation(vtype=ViolationType.COMMISSION)
        score = scorer.compute_score([v], _episode())
        assert score.sub_scores["C3_forbidden_avoidance"] == pytest.approx(0.0)

    def test_c4_timing_with_timing_violation(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        v = _violation(vtype=ViolationType.TIMING)
        score = scorer.compute_score([v], _episode())
        assert score.sub_scores["C4_timing_compliance"] == pytest.approx(0.8)

    def test_c5_sequence_with_sequence_violation(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        v = _violation(vtype=ViolationType.SEQUENCE)
        score = scorer.compute_score([v], _episode())
        assert score.sub_scores["C5_sequence_integrity"] == pytest.approx(0.8)


class TestMonotonicity:
    def test_severity_increase_raises_risk(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        severities = [
            HarmSeverity.MINOR,
            HarmSeverity.MODERATE,
            HarmSeverity.MAJOR,
            HarmSeverity.SEVERE,
            HarmSeverity.CATASTROPHIC,
        ]
        prev_risk = -1.0
        for sev in severities:
            v = _violation(severity=sev)
            score = scorer.compute_score([v], _episode())
            assert score.aggregate_risk >= prev_risk, (
                f"Risk should increase: {sev.value} risk {score.aggregate_risk} < prev {prev_risk}"
            )
            prev_risk = score.aggregate_risk

    def test_more_violations_reduce_compliance(self):
        scorer = HarmScorer(total_mandatory_count=10, config=_config())
        prev_compliance = 2.0
        for n in range(0, 6):
            violations = [_violation(f"v{i}") for i in range(n)]
            score = scorer.compute_score(violations, _episode())
            assert score.compliance_score <= prev_compliance, (
                f"{n} violations: compliance {score.compliance_score} > prev {prev_compliance}"
            )
            prev_compliance = score.compliance_score

    def test_more_violations_increase_aggregate_risk(self):
        scorer = HarmScorer(total_mandatory_count=10, config=_config())
        prev_risk = -1.0
        for n in range(0, 6):
            violations = [_violation(f"v{i}") for i in range(n)]
            score = scorer.compute_score(violations, _episode())
            assert score.aggregate_risk >= prev_risk, (
                f"{n} violations: aggregate_risk {score.aggregate_risk} < prev {prev_risk}"
            )
            prev_risk = score.aggregate_risk

    def test_higher_type_weight_produces_higher_risk(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        type_order = [
            (ViolationType.DEVIATION, 0.5),
            (ViolationType.SEQUENCE, 0.7),
            (ViolationType.TIMING, 0.8),
            (ViolationType.OMISSION, 1.0),
            (ViolationType.COMMISSION, 1.5),
        ]
        prev_risk = -1.0
        for vtype, _ in type_order:
            v = _violation(vtype=vtype)
            score = scorer.compute_score([v], _episode())
            assert score.aggregate_risk >= prev_risk, (
                f"{vtype.value} risk {score.aggregate_risk} < prev {prev_risk}"
            )
            prev_risk = score.aggregate_risk

    def test_higher_guideline_class_produces_higher_risk(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        class_order = [
            RecommendationClass.CLASS_III,
            RecommendationClass.CLASS_IIB,
            RecommendationClass.CLASS_IIA,
            RecommendationClass.CLASS_I,
        ]
        prev_risk = -1.0
        for gc in class_order:
            v = _violation(guideline_class=gc)
            score = scorer.compute_score([v], _episode())
            assert score.aggregate_risk >= prev_risk, (
                f"{gc.value} risk {score.aggregate_risk} < prev {prev_risk}"
            )
            prev_risk = score.aggregate_risk

    def test_lower_preventability_reduces_risk(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        v_high = _violation(preventability=1.0)
        v_low = _violation(preventability=0.3)
        score_high = scorer.compute_score([v_high], _episode())
        score_low = scorer.compute_score([v_low], _episode())
        assert score_high.aggregate_risk >= score_low.aggregate_risk


class TestMetricsReporter:
    def test_format_score_report_contains_sections(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        score = scorer.compute_score(
            [_violation()],
            _episode(),
        )
        report = MetricsReporter.format_score_report(score)
        assert "CGA-Bench Score Report" in report
        assert "Compliance Score" in report
        assert "Peak Risk" in report
        assert "Aggregate Risk" in report
        assert "C1_path_selection" in report
        assert "Total Violations" in report
        assert "Budget Usage" in report

    def test_format_empty_violations(self):
        scorer = HarmScorer(total_mandatory_count=5, config=_config())
        score = scorer.compute_score([], _episode())
        report = MetricsReporter.format_score_report(score)
        assert "Total Violations: 0" in report
