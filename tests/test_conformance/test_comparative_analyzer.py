"""Tests for comparative_analyzer.py - Comparative Conformance Analysis."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional

import pytest

from cga_bench.semantic_layer.conformance.comparative_analyzer import (
    AgentProfile,
    ComparativeAnalysis,
    ComparativeAnalyzer,
    ComparativeConfig,
    DomainBiasResult,
    FairnessMetrics,
    PairwiseComparison,
    ScenarioResult,
    _std,
    _variance,
)


# --- Test Fixtures ---

@dataclass
class MockSubScores:
    completeness: float = 1.0
    ordering: float = 1.0
    timeliness: float = 1.0
    safety: float = 1.0


@dataclass
class MockRubricScore:
    weighted_composite: float = 0.8
    dimension_scores: Dict[str, float] = field(default_factory=lambda: {
        "completeness": 0.9, "ordering": 0.8, "timeliness": 0.7, "safety": 1.0,
    })


@dataclass
class MockRubricReport:
    rubric_score: MockRubricScore = field(default_factory=MockRubricScore)


@dataclass
class MockReport:
    compliance_score: float = 0.8
    sub_scores: Optional[MockSubScores] = None


def make_result(
    scenario_id: str = "s1",
    agent_id: str = "agent_a",
    domain: str = "sepsis",
    score: float = 0.8,
    sub_scores: Optional[MockSubScores] = None,
    rubric_report: Optional[MockRubricReport] = None,
) -> ScenarioResult:
    """Helper to create ScenarioResult with configurable score."""
    return ScenarioResult(
        scenario_id=scenario_id,
        agent_id=agent_id,
        domain=domain,
        report=MockReport(compliance_score=score, sub_scores=sub_scores),
        rubric_report=rubric_report,
    )


# --- TestUtilityFunctions ---

class TestUtilityFunctions:
    """Tests for _variance and _std."""

    def test_variance_uniform(self):
        assert _variance([5.0, 5.0, 5.0]) == 0.0

    def test_variance_simple(self):
        # [0, 2, 4] → mean=2, variance = (4+0+4)/3 = 8/3
        assert abs(_variance([0.0, 2.0, 4.0]) - 8.0 / 3.0) < 1e-9

    def test_variance_single(self):
        assert _variance([3.0]) == 0.0

    def test_variance_empty(self):
        assert _variance([]) == 0.0

    def test_std_simple(self):
        assert abs(_std([0.0, 2.0, 4.0]) - (8.0 / 3.0) ** 0.5) < 1e-9


# --- TestPairwiseComparison ---

class TestPairwiseComparison:
    """Tests for compute_pairwise."""

    def setup_method(self):
        self.analyzer = ComparativeAnalyzer()

    def test_two_agents_one_domain(self):
        results = [
            make_result(agent_id="a", score=0.9),
            make_result(agent_id="b", score=0.7),
        ]
        comparisons = self.analyzer.compute_pairwise(results)
        assert len(comparisons) == 1
        c = comparisons[0]
        assert c.agent_a == "a"
        assert c.agent_b == "b"
        assert abs(c.score_diff - 0.2) < 1e-9
        assert c.significant  # 0.2 > default 0.1
        assert c.advantage == "a"

    def test_insignificant_difference(self):
        results = [
            make_result(agent_id="a", score=0.80),
            make_result(agent_id="b", score=0.82),
        ]
        comparisons = self.analyzer.compute_pairwise(results)
        assert len(comparisons) == 1
        assert not comparisons[0].significant
        assert comparisons[0].advantage is None

    def test_three_agents_combinatorial(self):
        results = [
            make_result(agent_id="a", score=0.9),
            make_result(agent_id="b", score=0.7),
            make_result(agent_id="c", score=0.5),
        ]
        comparisons = self.analyzer.compute_pairwise(results)
        # C(3,2) = 3 comparisons
        assert len(comparisons) == 3

    def test_multiple_scenarios_mean(self):
        results = [
            make_result(scenario_id="s1", agent_id="a", score=0.8),
            make_result(scenario_id="s2", agent_id="a", score=1.0),
            make_result(scenario_id="s1", agent_id="b", score=0.6),
            make_result(scenario_id="s2", agent_id="b", score=0.6),
        ]
        comparisons = self.analyzer.compute_pairwise(results)
        assert len(comparisons) == 1
        # mean_a=0.9, mean_b=0.6, diff=0.3
        assert abs(comparisons[0].score_diff - 0.3) < 1e-9

    def test_multiple_domains_separate_comparisons(self):
        results = [
            make_result(agent_id="a", domain="sepsis", score=0.9),
            make_result(agent_id="b", domain="sepsis", score=0.5),
            make_result(agent_id="a", domain="stroke", score=0.7),
            make_result(agent_id="b", domain="stroke", score=0.8),
        ]
        comparisons = self.analyzer.compute_pairwise(results)
        assert len(comparisons) == 2
        domains = {c.domain for c in comparisons}
        assert domains == {"sepsis", "stroke"}

    def test_b_advantage_negative_diff(self):
        results = [
            make_result(agent_id="a", score=0.3),
            make_result(agent_id="b", score=0.7),
        ]
        comparisons = self.analyzer.compute_pairwise(results)
        assert comparisons[0].advantage == "b"
        assert comparisons[0].score_diff < 0

    def test_custom_significance_threshold(self):
        config = ComparativeConfig(significance_threshold=0.3)
        analyzer = ComparativeAnalyzer(config)
        results = [
            make_result(agent_id="a", score=0.9),
            make_result(agent_id="b", score=0.7),
        ]
        comparisons = analyzer.compute_pairwise(results)
        # 0.2 < 0.3 → not significant
        assert not comparisons[0].significant

    def test_dimension_diffs_computed(self):
        results = [
            make_result(
                agent_id="a",
                sub_scores=MockSubScores(completeness=0.9, ordering=0.5, timeliness=0.8, safety=1.0),
            ),
            make_result(
                agent_id="b",
                sub_scores=MockSubScores(completeness=0.7, ordering=0.9, timeliness=0.6, safety=0.8),
            ),
        ]
        comparisons = self.analyzer.compute_pairwise(results)
        diffs = comparisons[0].dimension_diffs
        assert abs(diffs["completeness"] - 0.2) < 1e-9
        assert abs(diffs["ordering"] - (-0.4)) < 1e-9


# --- TestDomainBias ---

class TestDomainBias:
    """Tests for detect_domain_bias."""

    def setup_method(self):
        self.analyzer = ComparativeAnalyzer()

    def test_no_bias_uniform_scores(self):
        results = [
            make_result(agent_id="a", domain="sepsis", score=0.8),
            make_result(agent_id="a", domain="stroke", score=0.8),
        ]
        biases = self.analyzer.detect_domain_bias(results)
        assert all(not b.is_biased for b in biases)

    def test_bias_detected(self):
        results = [
            make_result(agent_id="a", domain="sepsis", score=0.9),
            make_result(agent_id="a", domain="stroke", score=0.5),
        ]
        biases = self.analyzer.detect_domain_bias(results)
        # overall_mean = 0.7
        # sepsis bias = 0.9 - 0.7 = 0.2 > 0.15
        biased = [b for b in biases if b.is_biased]
        assert len(biased) == 2  # Both domains show bias
        sepsis_bias = next(b for b in biases if b.domain == "sepsis")
        assert sepsis_bias.direction == "advantage"
        stroke_bias = next(b for b in biases if b.domain == "stroke")
        assert stroke_bias.direction == "disadvantage"

    def test_bias_per_agent(self):
        results = [
            make_result(agent_id="a", domain="sepsis", score=0.9),
            make_result(agent_id="a", domain="stroke", score=0.5),
            make_result(agent_id="b", domain="sepsis", score=0.6),
            make_result(agent_id="b", domain="stroke", score=0.6),
        ]
        biases = self.analyzer.detect_domain_bias(results)
        # Agent b has no bias (0.6 - 0.6 = 0)
        b_biases = [bias for bias in biases if bias.agent_id == "b"]
        assert all(not b.is_biased for b in b_biases)

    def test_custom_bias_threshold(self):
        config = ComparativeConfig(bias_threshold=0.3)
        analyzer = ComparativeAnalyzer(config)
        results = [
            make_result(agent_id="a", domain="sepsis", score=0.9),
            make_result(agent_id="a", domain="stroke", score=0.7),
        ]
        biases = analyzer.detect_domain_bias(results)
        # bias = 0.1, threshold = 0.3 → not biased
        assert all(not b.is_biased for b in biases)

    def test_single_domain_no_bias(self):
        results = [
            make_result(agent_id="a", domain="sepsis", score=0.9),
            make_result(agent_id="a", domain="sepsis", score=0.7),
        ]
        biases = self.analyzer.detect_domain_bias(results)
        # Only one domain → bias = 0
        assert all(b.bias == 0.0 for b in biases)


# --- TestAgentProfiles ---

class TestAgentProfiles:
    """Tests for build_agent_profiles."""

    def setup_method(self):
        self.analyzer = ComparativeAnalyzer()

    def test_single_agent_profile(self):
        results = [
            make_result(
                agent_id="a", scenario_id="s1",
                sub_scores=MockSubScores(completeness=0.9, ordering=0.7, timeliness=0.8, safety=1.0),
            ),
            make_result(
                agent_id="a", scenario_id="s2",
                sub_scores=MockSubScores(completeness=0.8, ordering=0.6, timeliness=0.7, safety=0.9),
            ),
        ]
        profiles = self.analyzer.build_agent_profiles(results)
        assert len(profiles) == 1
        p = profiles[0]
        assert p.agent_id == "a"
        assert p.scenario_count == 2
        assert abs(p.mean_scores["completeness"] - 0.85) < 1e-9
        assert abs(p.mean_scores["ordering"] - 0.65) < 1e-9

    def test_strengths_and_weaknesses(self):
        results = [
            make_result(
                agent_id="a",
                sub_scores=MockSubScores(completeness=0.9, ordering=0.5, timeliness=0.3, safety=1.0),
            ),
        ]
        profiles = self.analyzer.build_agent_profiles(results)
        p = profiles[0]
        # Strengths: safety (1.0), completeness (0.9)
        assert "safety" in p.strengths
        assert "completeness" in p.strengths
        # Weaknesses: timeliness (0.3), ordering (0.5)
        assert "timeliness" in p.weaknesses
        assert "ordering" in p.weaknesses

    def test_risk_aversion_score(self):
        results = [
            make_result(
                agent_id="a",
                sub_scores=MockSubScores(safety=0.95),
            ),
        ]
        profiles = self.analyzer.build_agent_profiles(results)
        assert profiles[0].risk_aversion_score == 0.95

    def test_domain_specialization(self):
        results = [
            make_result(agent_id="a", domain="sepsis", score=0.9),
            make_result(agent_id="a", domain="stroke", score=0.6),
            make_result(agent_id="a", domain="dka", score=0.7),
        ]
        profiles = self.analyzer.build_agent_profiles(results)
        assert profiles[0].domain_specialization == "sepsis"

    def test_multiple_agents(self):
        results = [
            make_result(agent_id="a", score=0.8, sub_scores=MockSubScores()),
            make_result(agent_id="b", score=0.6, sub_scores=MockSubScores(completeness=0.5)),
        ]
        profiles = self.analyzer.build_agent_profiles(results)
        assert len(profiles) == 2
        agents = {p.agent_id for p in profiles}
        assert agents == {"a", "b"}

    def test_std_scores_computed(self):
        results = [
            make_result(agent_id="a", scenario_id="s1", sub_scores=MockSubScores(completeness=0.6)),
            make_result(agent_id="a", scenario_id="s2", sub_scores=MockSubScores(completeness=1.0)),
        ]
        profiles = self.analyzer.build_agent_profiles(results)
        # std of [0.6, 1.0] = sqrt((0.04+0.04)/2) = 0.2
        assert abs(profiles[0].std_scores["completeness"] - 0.2) < 1e-9

    def test_disabled_profiles(self):
        config = ComparativeConfig(enable_agent_profiles=False)
        analyzer = ComparativeAnalyzer(config)
        results = [make_result(agent_id="a")]
        analysis = analyzer.analyze(results)
        assert analysis.agent_profiles == []


# --- TestFairnessMetrics ---

class TestFairnessMetrics:
    """Tests for compute_fairness."""

    def setup_method(self):
        self.analyzer = ComparativeAnalyzer()

    def test_single_agent_fair(self):
        results = [make_result(agent_id="a", score=0.8)]
        fairness = self.analyzer.compute_fairness(results)
        assert fairness.is_fair
        assert fairness.overall_variance == 0.0
        assert fairness.max_score_gap == 0.0

    def test_equal_agents_fair(self):
        results = [
            make_result(agent_id="a", score=0.8),
            make_result(agent_id="b", score=0.8),
        ]
        fairness = self.analyzer.compute_fairness(results)
        assert fairness.is_fair
        assert fairness.overall_variance == 0.0

    def test_unequal_agents_max_gap(self):
        results = [
            make_result(agent_id="a", score=0.9),
            make_result(agent_id="b", score=0.5),
        ]
        fairness = self.analyzer.compute_fairness(results)
        assert abs(fairness.max_score_gap - 0.4) < 1e-9

    def test_domain_parity_fair(self):
        results = [
            make_result(agent_id="a", domain="sepsis", score=0.8),
            make_result(agent_id="b", domain="sepsis", score=0.8),
            make_result(agent_id="a", domain="stroke", score=0.7),
            make_result(agent_id="b", domain="stroke", score=0.7),
        ]
        fairness = self.analyzer.compute_fairness(results)
        assert fairness.is_fair
        assert fairness.domain_parity["sepsis"] == 0.0

    def test_domain_parity_unfair(self):
        config = ComparativeConfig(significance_threshold=0.01)
        analyzer = ComparativeAnalyzer(config)
        results = [
            make_result(agent_id="a", domain="sepsis", score=0.9),
            make_result(agent_id="b", domain="sepsis", score=0.3),
        ]
        fairness = analyzer.compute_fairness(results)
        # variance of [0.9, 0.3] = (0.09+0.09)/2 = 0.09 > 0.01
        assert not fairness.is_fair
        assert "sepsis" in fairness.unfair_domains

    def test_disabled_fairness(self):
        config = ComparativeConfig(enable_fairness_analysis=False)
        analyzer = ComparativeAnalyzer(config)
        results = [make_result(agent_id="a", score=0.8)]
        analysis = analyzer.analyze(results)
        assert analysis.fairness.is_fair

    def test_overall_variance_multiple_agents(self):
        results = [
            make_result(agent_id="a", score=0.9),
            make_result(agent_id="b", score=0.7),
            make_result(agent_id="c", score=0.5),
        ]
        fairness = self.analyzer.compute_fairness(results)
        # means = [0.9, 0.7, 0.5], mean=0.7
        # variance = (0.04+0+0.04)/3 = 0.0267
        expected_var = (0.04 + 0.0 + 0.04) / 3.0
        assert abs(fairness.overall_variance - expected_var) < 1e-9


# --- TestComparativeAnalysis ---

class TestComparativeAnalysis:
    """Tests for full analyze() flow."""

    def setup_method(self):
        self.analyzer = ComparativeAnalyzer()

    def test_full_analysis_structure(self):
        results = [
            make_result(agent_id="a", domain="sepsis", score=0.9, sub_scores=MockSubScores()),
            make_result(agent_id="b", domain="sepsis", score=0.6, sub_scores=MockSubScores(completeness=0.5)),
            make_result(agent_id="a", domain="stroke", score=0.7, sub_scores=MockSubScores()),
            make_result(agent_id="b", domain="stroke", score=0.8, sub_scores=MockSubScores()),
        ]
        analysis = self.analyzer.analyze(results)
        assert isinstance(analysis, ComparativeAnalysis)
        assert len(analysis.scenario_results) == 4
        assert len(analysis.pairwise_comparisons) > 0
        assert len(analysis.agent_profiles) == 2
        assert isinstance(analysis.fairness, FairnessMetrics)
        assert isinstance(analysis.summary, dict)

    def test_summary_counts(self):
        results = [
            make_result(agent_id="a", domain="sepsis", score=0.9),
            make_result(agent_id="b", domain="stroke", score=0.7),
        ]
        analysis = self.analyzer.analyze(results)
        assert analysis.summary["total_scenarios"] == 2
        assert analysis.summary["num_agents"] == 2
        assert analysis.summary["num_domains"] == 2

    def test_empty_results(self):
        analysis = self.analyzer.analyze([])
        assert analysis.pairwise_comparisons == []
        assert analysis.domain_biases == []
        assert analysis.agent_profiles == []
        assert analysis.fairness.is_fair

    def test_rubric_report_used_for_score(self):
        rubric = MockRubricReport(rubric_score=MockRubricScore(weighted_composite=0.95))
        results = [
            ScenarioResult(
                scenario_id="s1", agent_id="a", domain="sepsis",
                report=MockReport(compliance_score=0.5),
                rubric_report=rubric,
            ),
            make_result(agent_id="b", domain="sepsis", score=0.7),
        ]
        comparisons = self.analyzer.compute_pairwise(results)
        # Agent a should use rubric weighted_composite (0.95), not compliance_score (0.5)
        assert comparisons[0].score_diff > 0  # 0.95 - 0.7 = 0.25

    def test_significant_comparisons_count(self):
        results = [
            make_result(agent_id="a", score=0.9),
            make_result(agent_id="b", score=0.5),
            make_result(agent_id="c", score=0.85),
        ]
        analysis = self.analyzer.analyze(results)
        sig_count = analysis.summary["significant_comparisons"]
        # a vs b: 0.4 > 0.1 ✓; a vs c: 0.05 < 0.1 ✗; b vs c: 0.35 > 0.1 ✓
        assert sig_count == 2


# --- TestScoreExtraction ---

class TestScoreExtraction:
    """Tests for score extraction from different report types."""

    def setup_method(self):
        self.analyzer = ComparativeAnalyzer()

    def test_compliance_score_fallback(self):
        r = make_result(score=0.75)
        assert abs(self.analyzer._extract_score(r) - 0.75) < 1e-9

    def test_rubric_composite_preferred(self):
        rubric = MockRubricReport(rubric_score=MockRubricScore(weighted_composite=0.85))
        r = ScenarioResult(
            scenario_id="s1", agent_id="a", domain="sepsis",
            report=MockReport(compliance_score=0.5),
            rubric_report=rubric,
        )
        assert abs(self.analyzer._extract_score(r) - 0.85) < 1e-9

    def test_none_report_zero(self):
        r = ScenarioResult(
            scenario_id="s1", agent_id="a", domain="sepsis",
            report=None,
        )
        assert self.analyzer._extract_score(r) == 0.0

    def test_dimension_scores_from_subscores(self):
        r = make_result(sub_scores=MockSubScores(completeness=0.6, timeliness=0.4))
        dims = self.analyzer._extract_dimension_scores(r)
        assert dims["completeness"] == 0.6
        assert dims["timeliness"] == 0.4

    def test_dimension_scores_from_rubric(self):
        rubric = MockRubricReport(
            rubric_score=MockRubricScore(dimension_scores={"completeness": 0.99})
        )
        r = ScenarioResult(
            scenario_id="s1", agent_id="a", domain="sepsis",
            report=MockReport(sub_scores=MockSubScores(completeness=0.1)),
            rubric_report=rubric,
        )
        dims = self.analyzer._extract_dimension_scores(r)
        assert dims["completeness"] == 0.99  # Rubric preferred over SubScores
