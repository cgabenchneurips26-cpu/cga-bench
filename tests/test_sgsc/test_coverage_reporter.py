"""Tests for sgsc.audit.coverage_reporter — JSON/markdown/LaTeX report generation."""

from __future__ import annotations

import json
from pathlib import Path

from sgsc.audit.coverage_reporter import (
    report_to_json,
    report_to_latex_macros,
    report_to_markdown,
    write_coverage_report,
)
from sgsc.schemas.coverage import (
    CoverageItem,
    CoverageReport,
    CoverageType,
    CoverageVector,
)


def _make_report() -> CoverageReport:
    """Create a sample CoverageReport for testing."""
    cov_items = [
        CoverageItem(item_id="rec:abx", coverage_type=CoverageType.RECOMMENDATION, description="ABX rec"),
        CoverageItem(item_id="cst:within_60", coverage_type=CoverageType.CONSTRAINT, description="WITHIN"),
        CoverageItem(item_id="mut:omit_abx", coverage_type=CoverageType.MUTATION, description="Omit ABX"),
        CoverageItem(item_id="src:abx_quote", coverage_type=CoverageType.SOURCE, description="Quote link"),
    ]
    vectors = [
        CoverageVector(
            scenario_id="s1",
            covered_items=frozenset({"rec:abx", "cst:within_60", "src:abx_quote"}),
        ),
        CoverageVector(
            scenario_id="s2",
            covered_items=frozenset({"rec:abx", "mut:omit_abx"}),
        ),
    ]
    return CoverageReport(
        total_items=len(cov_items),
        covered_count=4,
        coverage_items=cov_items,
        vectors=vectors,
    )


class TestReportToJson:
    """Tests for report_to_json."""

    def test_basic_structure(self) -> None:
        data = report_to_json(_make_report())
        assert data["total_items"] == 4
        assert data["covered_count"] == 4
        assert data["coverage_ratio"] == 1.0
        assert data["is_fully_covered"] is True
        assert data["scenario_count"] == 2

    def test_by_type_breakdown(self) -> None:
        data = report_to_json(_make_report())
        by_type = data["by_type"]
        assert by_type["recommendation"]["total"] == 1
        assert by_type["recommendation"]["covered"] == 1
        assert by_type["constraint"]["total"] == 1
        assert by_type["mutation"]["total"] == 1

    def test_partial_coverage(self) -> None:
        cov_items = [
            CoverageItem(item_id="i1", coverage_type=CoverageType.RECOMMENDATION, description="A"),
            CoverageItem(item_id="i2", coverage_type=CoverageType.RECOMMENDATION, description="B"),
        ]
        vectors = [
            CoverageVector(scenario_id="s1", covered_items=frozenset({"i1"})),
        ]
        report = CoverageReport(
            total_items=2,
            covered_count=1,
            coverage_items=cov_items,
            vectors=vectors,
        )
        data = report_to_json(report)
        assert data["covered_count"] == 1
        assert data["is_fully_covered"] is False
        assert data["coverage_ratio"] == 0.5

    def test_empty_report(self) -> None:
        report = CoverageReport()
        data = report_to_json(report)
        assert data["total_items"] == 0
        assert data["coverage_ratio"] == 0.0


class TestReportToMarkdown:
    """Tests for report_to_markdown."""

    def test_contains_header(self) -> None:
        md = report_to_markdown(_make_report())
        assert "# SGSC Coverage Report" in md

    def test_custom_title(self) -> None:
        md = report_to_markdown(_make_report(), title="Custom Title")
        assert "# Custom Title" in md

    def test_contains_table(self) -> None:
        md = report_to_markdown(_make_report())
        assert "| Type |" in md
        assert "recommendation" in md

    def test_contains_counts(self) -> None:
        md = report_to_markdown(_make_report())
        assert "**Total items**: 4" in md
        assert "**Scenarios**: 2" in md


class TestReportToLatexMacros:
    """Tests for report_to_latex_macros."""

    def test_providecommand_format(self) -> None:
        tex = report_to_latex_macros(_make_report())
        assert "\\providecommand" in tex

    def test_default_prefix(self) -> None:
        tex = report_to_latex_macros(_make_report())
        assert "\\sgscTotalItems" in tex
        assert "\\sgscCoveredCount" in tex
        assert "\\sgscCoverageRatio" in tex
        assert "\\sgscScenarioCount" in tex

    def test_custom_prefix(self) -> None:
        tex = report_to_latex_macros(_make_report(), prefix="myprefix")
        assert "\\myprefixTotalItems" in tex

    def test_per_type_macros(self) -> None:
        tex = report_to_latex_macros(_make_report())
        assert "\\sgscrecommendationTotal" in tex
        assert "\\sgscrecommendationCovered" in tex


class TestWriteCoverageReport:
    """Tests for write_coverage_report to filesystem."""

    def test_writes_all_formats(self, tmp_path: Path) -> None:
        report = _make_report()
        paths = write_coverage_report(report, str(tmp_path), "test")
        assert "json" in paths
        assert "markdown" in paths
        assert "latex" in paths
        # Verify files exist and are non-empty
        for fmt, fpath in paths.items():
            p = Path(fpath)
            assert p.exists(), f"{fmt} file not created"
            assert p.stat().st_size > 0, f"{fmt} file is empty"

    def test_json_file_valid(self, tmp_path: Path) -> None:
        report = _make_report()
        paths = write_coverage_report(report, str(tmp_path), "test")
        data = json.loads(Path(paths["json"]).read_text())
        assert data["total_items"] == 4

    def test_creates_output_dir(self, tmp_path: Path) -> None:
        out = tmp_path / "nested" / "dir"
        report = _make_report()
        paths = write_coverage_report(report, str(out), "test")
        assert out.exists()
        assert len(paths) == 3
