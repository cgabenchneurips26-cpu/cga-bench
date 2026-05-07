"""Coverage report generation: JSON, markdown, and LaTeX outputs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sgsc.schemas.coverage import CoverageReport, CoverageType

# ------------------------------------------------------------------
# JSON report
# ------------------------------------------------------------------


def report_to_json(report: CoverageReport) -> dict[str, Any]:
    """Convert a CoverageReport to a JSON-serializable dict."""
    by_type: dict[str, dict[str, int]] = {}
    for ctype in CoverageType:
        type_items = [i for i in report.coverage_items if i.coverage_type == ctype]
        covered_ids: set[str] = set()
        for v in report.vectors:
            for item in type_items:
                if item.item_id in v.covered_items:
                    covered_ids.add(item.item_id)
        by_type[ctype.value] = {
            "total": len(type_items),
            "covered": len(covered_ids),
        }

    return {
        "total_items": report.total_items,
        "covered_count": report.covered_count,
        "coverage_ratio": round(report.covered_count / max(report.total_items, 1), 4),
        "is_fully_covered": report.is_fully_covered,
        "by_type": by_type,
        "scenario_count": len(report.vectors),
    }


# ------------------------------------------------------------------
# Markdown report
# ------------------------------------------------------------------


def report_to_markdown(report: CoverageReport, title: str = "SGSC Coverage Report") -> str:
    """Generate a markdown coverage report."""
    data = report_to_json(report)
    lines: list[str] = [
        f"# {title}",
        "",
        f"**Total items**: {data['total_items']}",
        f"**Covered**: {data['covered_count']} ({data['coverage_ratio']:.1%})",
        f"**Fully covered**: {'Yes' if data['is_fully_covered'] else 'No'}",
        f"**Scenarios**: {data['scenario_count']}",
        "",
        "## Coverage by Type",
        "",
        "| Type | Total | Covered | Rate |",
        "|------|-------|---------|------|",
    ]

    for ctype_name, counts in data["by_type"].items():
        total = counts["total"]
        covered = counts["covered"]
        rate = covered / max(total, 1)
        lines.append(f"| {ctype_name} | {total} | {covered} | {rate:.1%} |")

    lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------
# LaTeX macros
# ------------------------------------------------------------------


def report_to_latex_macros(report: CoverageReport, prefix: str = "sgsc") -> str:
    """Generate LaTeX \\providecommand macros from coverage report."""
    data = report_to_json(report)
    lines: list[str] = [
        "% SGSC coverage macros (auto-generated)",
        f"\\providecommand{{\\{prefix}TotalItems}}{{{data['total_items']}}}",
        f"\\providecommand{{\\{prefix}CoveredCount}}{{{data['covered_count']}}}",
        f"\\providecommand{{\\{prefix}CoverageRatio}}{{{data['coverage_ratio']:.3f}}}",
        f"\\providecommand{{\\{prefix}ScenarioCount}}{{{data['scenario_count']}}}",
    ]

    for ctype_name, counts in data["by_type"].items():
        safe_name = ctype_name.replace("_", "")
        lines.append(f"\\providecommand{{\\{prefix}{safe_name}Total}}{{{counts['total']}}}")
        lines.append(f"\\providecommand{{\\{prefix}{safe_name}Covered}}{{{counts['covered']}}}")

    lines.append("")
    return "\n".join(lines)


# ------------------------------------------------------------------
# File writer
# ------------------------------------------------------------------


def write_coverage_report(
    report: CoverageReport,
    output_dir: str | Path,
    prefix: str = "sgsc",
) -> dict[str, str]:
    """Write all coverage report formats to output_dir.

    Returns dict of format -> file path.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    paths: dict[str, str] = {}

    # JSON
    json_path = out / f"{prefix}_coverage.json"
    json_path.write_text(json.dumps(report_to_json(report), indent=2))
    paths["json"] = str(json_path)

    # Markdown
    md_path = out / f"{prefix}_coverage.md"
    md_path.write_text(report_to_markdown(report))
    paths["markdown"] = str(md_path)

    # LaTeX
    tex_path = out / f"{prefix}_coverage_macros.tex"
    tex_path.write_text(report_to_latex_macros(report, prefix))
    paths["latex"] = str(tex_path)

    return paths
