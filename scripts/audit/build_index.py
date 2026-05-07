#!/usr/bin/env python3
"""Generate INDEX.md summary table from evaluator audit reports.

Walks audit/reports/ and collects report.json from each subdirectory
to produce a summary table.

Usage:
    PYTHONPATH=. python scripts/audit/build_index.py audit/reports
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
import sys


def build_index(reports_dir: Path) -> str:
    """Walk reports_dir, collect report.json, generate INDEX.md content."""
    rows: list[dict] = []

    for report_json in sorted(reports_dir.glob("*/report.json")):
        with open(report_json) as f:
            report = json.load(f)

        ev = report.get("evaluator", {})
        s1 = report.get("step1_pi_class", {})
        s2 = report.get("step2_bsr", {})
        s3 = report.get("step3_bayes_floor", {})
        s4 = report.get("step4_witnesses", {})

        rows.append(
            {
                "name": ev.get("name", "?"),
                "family": ev.get("family", "?"),
                "pi_class": s1.get("pi_class", "?"),
                "bsr": s2.get("bsr", -1),
                "bayes_floor": s3.get("epsilon_star", -1),
                "false_accepts": s4.get("total_false_accepts", -1),
                "corpus_size": report.get("corpus_size", 0),
                "dir": report_json.parent.name,
            }
        )

    lines = [
        "# Evaluator Audit Index",
        "",
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}  ",
        f"Reports: {len(rows)} evaluators  ",
        f"Corpus: {rows[0]['corpus_size']:,} episodes" if rows else "",
        "",
        "| Evaluator | Family | pi-class | BSR | Bayes Floor | False Accepts |",
        "|-----------|--------|----------|-----|-------------|---------------|",
    ]

    for r in rows:
        bsr_str = f"{r['bsr']:.4f}" if r["bsr"] >= 0 else "?"
        bf_str = f"{r['bayes_floor']:.3f}" if r["bayes_floor"] >= 0 else "?"
        fa_str = str(r["false_accepts"]) if r["false_accepts"] >= 0 else "?"
        lines.append(
            f"| [{r['name']}]({r['dir']}/report.md) | {r['family']} | {r['pi_class']} | {bsr_str} | {bf_str} | {fa_str} |"
        )

    lines.extend(
        [
            "",
            "## Bayes-Error Floor Reference",
            "",
            "| Projection | epsilon_star |",
            "|------------|-------------|",
            "| term       | 0.436       |",
            "| aset       | 0.024       |",
            "| nord       | 0.003       |",
            "| nctx       | 0.003       |",
            "",
        ]
    )

    return "\n".join(lines)


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: python scripts/audit/build_index.py <reports_dir>")
        sys.exit(1)

    reports_dir = Path(sys.argv[1])
    if not reports_dir.is_dir():
        print(f"Error: {reports_dir} is not a directory")
        sys.exit(1)

    content = build_index(reports_dir)
    index_path = reports_dir / "INDEX.md"
    index_path.write_text(content)
    print(f"Wrote {index_path} ({len(content)} bytes)")


if __name__ == "__main__":
    main()
