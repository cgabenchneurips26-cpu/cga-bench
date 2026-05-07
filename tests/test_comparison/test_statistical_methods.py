"""Tests for ModelComparisonAnalyzer statistical methods.

Uses known data to verify correctness of statistical tests and effect sizes.
"""

import pytest

try:
    import numpy as np
    from scipy import stats as scipy_stats
    HAS_SCIPY = True
except ImportError:
    HAS_SCIPY = False

pytestmark = pytest.mark.skipif(not HAS_SCIPY, reason="scipy/numpy required")

from cga_bench.eval_harness.comparison import (
    ModelComparisonAnalyzer,
    StatisticalTestResult,
    EffectSizeResult,
    PairwiseComparison,
)


@pytest.fixture
def analyzer():
    return ModelComparisonAnalyzer(alpha=0.05, bootstrap_iterations=1000)


class TestPairedTTest:
    def test_identical_scores_not_significant(self, analyzer):
        scores = [0.8, 0.85, 0.82, 0.88, 0.81]
        result = analyzer.paired_t_test(scores, scores)
        assert not result.significant

    def test_very_different_scores_significant(self, analyzer):
        scores1 = [0.9, 0.91, 0.92, 0.93, 0.94, 0.95, 0.96]
        scores2 = [0.3, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36]
        result = analyzer.paired_t_test(scores1, scores2)
        assert result.significant
        assert result.p_value < 0.001

    def test_single_sample_not_significant(self, analyzer):
        result = analyzer.paired_t_test([0.5], [0.3])
        assert not result.significant

    def test_length_mismatch_raises(self, analyzer):
        with pytest.raises(ValueError):
            analyzer.paired_t_test([0.1, 0.2], [0.3])


class TestWilcoxonSignedRank:
    def test_identical_scores_not_significant(self, analyzer):
        scores = [0.8, 0.85, 0.82, 0.88, 0.81]
        result = analyzer.wilcoxon_signed_rank(scores, scores)
        assert not result.significant

    def test_different_scores(self, analyzer):
        scores1 = [0.9, 0.91, 0.92, 0.93, 0.94, 0.95, 0.96, 0.97]
        scores2 = [0.3, 0.31, 0.32, 0.33, 0.34, 0.35, 0.36, 0.37]
        result = analyzer.wilcoxon_signed_rank(scores1, scores2)
        assert result.p_value < 0.05


class TestBootstrapCI:
    def test_ci_contains_observed_mean(self, analyzer):
        scores1 = [0.9, 0.91, 0.92, 0.93, 0.94]
        scores2 = [0.8, 0.81, 0.82, 0.83, 0.84]
        mean_diff, ci_lo, ci_hi = analyzer.bootstrap_ci(scores1, scores2)
        assert ci_lo <= mean_diff <= ci_hi

    def test_ci_positive_for_higher_scores(self, analyzer):
        scores1 = [0.95, 0.96, 0.97, 0.98, 0.99]
        scores2 = [0.50, 0.51, 0.52, 0.53, 0.54]
        mean_diff, ci_lo, ci_hi = analyzer.bootstrap_ci(scores1, scores2)
        assert ci_lo > 0
        assert mean_diff > 0.4


class TestCohensD:
    def test_identical_distributions(self, analyzer):
        scores = [0.8, 0.85, 0.82, 0.88, 0.81]
        result = analyzer.cohens_d(scores, scores)
        assert abs(result.value) < 0.01
        assert result.interpretation == "negligible"

    def test_large_effect(self, analyzer):
        scores1 = [0.9, 0.91, 0.92, 0.93, 0.94]
        scores2 = [0.5, 0.51, 0.52, 0.53, 0.54]
        result = analyzer.cohens_d(scores1, scores2)
        assert result.value > 0.8
        assert result.interpretation == "large"

    def test_negative_d_when_second_is_better(self, analyzer):
        scores1 = [0.5, 0.51, 0.52]
        scores2 = [0.9, 0.91, 0.92]
        result = analyzer.cohens_d(scores1, scores2)
        assert result.value < 0


class TestCliffDelta:
    def test_identical_distributions(self, analyzer):
        scores = [0.8, 0.85, 0.82, 0.88, 0.81]
        result = analyzer.cliff_delta(scores, scores)
        assert result.value == 0.0
        assert result.interpretation == "negligible"

    def test_complete_dominance(self, analyzer):
        scores1 = [0.9, 0.91, 0.92]
        scores2 = [0.1, 0.11, 0.12]
        result = analyzer.cliff_delta(scores1, scores2)
        assert result.value == 1.0
        assert result.interpretation == "large"


class TestBonferroniCorrection:
    def test_single_p_value(self, analyzer):
        result = analyzer.bonferroni_correction([0.01])
        assert result == [True]

    def test_correction_raises_threshold(self, analyzer):
        # With 10 tests, alpha becomes 0.005
        p_values = [0.01] * 10
        result = analyzer.bonferroni_correction(p_values)
        # 0.01 > 0.05/10 = 0.005 → not significant after correction
        assert not any(result)

    def test_empty_list(self, analyzer):
        assert analyzer.bonferroni_correction([]) == []


class TestComparePair:
    def test_returns_pairwise_comparison(self, analyzer):
        s1 = [0.9, 0.91, 0.92, 0.93, 0.94]
        s2 = [0.5, 0.51, 0.52, 0.53, 0.54]
        result = analyzer.compare_pair(s1, s2, "agent_a", "agent_b", "scenario_1")
        assert isinstance(result, PairwiseComparison)
        assert result.agent1 == "agent_a"
        assert result.agent2 == "agent_b"
        assert result.n_samples == 5
        assert len(result.tests) == 2
        assert len(result.effect_sizes) == 2


class TestCompareAllAgents:
    def test_compare_from_summary(self, sample_experiment_summary):
        analyzer = ModelComparisonAnalyzer(alpha=0.05, bootstrap_iterations=500)
        comparisons = analyzer.compare_all_agents(sample_experiment_summary, per_scenario=True)
        assert len(comparisons) > 0

        for c in comparisons:
            assert isinstance(c, PairwiseComparison)
            assert c.n_samples > 0

    def test_compare_overall(self, sample_experiment_summary):
        analyzer = ModelComparisonAnalyzer(alpha=0.05, bootstrap_iterations=500)
        comparisons = analyzer.compare_all_agents(sample_experiment_summary, per_scenario=False)
        assert len(comparisons) > 0
        assert all(c.scenario == "overall" for c in comparisons)
