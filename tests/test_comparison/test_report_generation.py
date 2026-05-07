"""Tests for ComparisonReportGenerator."""

import json
import pytest

try:
    import numpy as np
    HAS_NUMPY = True
except ImportError:
    HAS_NUMPY = False

pytestmark = pytest.mark.skipif(not HAS_NUMPY, reason="numpy required")

from cga_bench.eval_harness.comparison import (
    ModelComparisonAnalyzer,
    PairwiseComparison,
    StatisticalTestResult,
    EffectSizeResult,
)
from cga_bench.eval_harness.report_generator import ComparisonReportGenerator


@pytest.fixture
def sample_comparisons():
    return [
        PairwiseComparison(
            agent1="rag_gpt4",
            agent2="oracle",
            scenario="septic_shock_basic",
            n_samples=5,
            mean_diff=-0.10,
            ci_lower=-0.15,
            ci_upper=-0.05,
            tests=[
                StatisticalTestResult("Paired t-test", -3.5, 0.02, True),
                StatisticalTestResult("Wilcoxon signed-rank", 1.0, 0.03, True),
            ],
            effect_sizes=[
                EffectSizeResult("Cohen's d", -1.5, "large"),
                EffectSizeResult("Cliff's delta", -0.8, "large"),
            ],
            winner="oracle",
        ),
    ]


class TestMarkdownReport:
    def test_generates_markdown_table(self, sample_comparisons):
        gen = ComparisonReportGenerator(sample_comparisons)
        md = gen.generate_markdown_table()
        assert "# Multi-Agent Comparison Results" in md
        assert "rag_gpt4" in md
        assert "oracle" in md
        assert "***" in md

    def test_empty_comparisons(self):
        gen = ComparisonReportGenerator([])
        md = gen.generate_markdown_table()
        assert "# Multi-Agent Comparison Results" in md


class TestLatexReport:
    def test_generates_latex_table(self, sample_comparisons):
        gen = ComparisonReportGenerator(sample_comparisons)
        tex = gen.generate_latex_table()
        assert r"\begin{table}" in tex
        assert r"\end{table}" in tex
        assert "rag_gpt4" in tex
        assert "Cohen" in tex


class TestSummaryStatistics:
    def test_generates_summary(self, sample_comparisons):
        gen = ComparisonReportGenerator(sample_comparisons)
        summary_data = {
            "statistics": {
                "rag_gpt4": {
                    "overall_mean": 0.82,
                    "overall_std": 0.05,
                    "by_scenario": {"s1": {}, "s2": {}},
                },
                "oracle": {
                    "overall_mean": 0.95,
                    "overall_std": 0.02,
                    "by_scenario": {"s1": {}},
                },
            }
        }
        result = gen.generate_summary_statistics(summary_data)
        assert "rag_gpt4" in result
        assert "0.8200" in result

    def test_empty_statistics(self, sample_comparisons):
        gen = ComparisonReportGenerator(sample_comparisons)
        result = gen.generate_summary_statistics({})
        assert "No statistics available" in result


class TestTokenEfficiency:
    def test_generates_efficiency(self, sample_comparisons):
        gen = ComparisonReportGenerator(sample_comparisons)
        data = {
            "results": [
                {"agent_id": "rag_gpt4", "compliance_score": 0.8, "total_tokens": 5000},
                {"agent_id": "rag_gpt4", "compliance_score": 0.85, "total_tokens": 6000},
            ]
        }
        result = gen.generate_token_efficiency(data)
        assert "Token Efficiency" in result
        assert "rag_gpt4" in result

    def test_no_token_data(self, sample_comparisons):
        gen = ComparisonReportGenerator(sample_comparisons)
        result = gen.generate_token_efficiency({"results": []})
        assert "No token usage data" in result


class TestSaveReport:
    def test_saves_md_and_tex(self, sample_comparisons, tmp_path):
        gen = ComparisonReportGenerator(sample_comparisons)
        output = tmp_path / "report"
        gen.save_report(output)

        md_path = output.with_suffix(".md")
        tex_path = output.with_suffix(".tex")
        assert md_path.exists()
        assert tex_path.exists()
        assert len(md_path.read_text()) > 0
        assert len(tex_path.read_text()) > 0

    def test_saves_with_summary(self, sample_experiment_summary, sample_comparisons, tmp_path):
        gen = ComparisonReportGenerator(sample_comparisons)
        output = tmp_path / "full_report"
        gen.save_report(output, summary_path=sample_experiment_summary)

        md_path = output.with_suffix(".md")
        assert md_path.exists()
        content = md_path.read_text()
        assert "rag_gpt4" in content
