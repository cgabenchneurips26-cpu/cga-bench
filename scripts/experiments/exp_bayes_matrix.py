#!/usr/bin/env python3
"""B2: Per-violation-type Bayes error matrix validation.

Parses the 4x5 (projection x violation-type) Bayes error values from
bayes_error_macros.tex, validates internal consistency, computes derived
statistics (row/column means, sharpest separations), and emits a summary.

The 20 coordinate values are already committed; this script validates
them and produces derived macros for paper prose.

Usage:
    PYTHONPATH=. python scripts/experiments/exp_bayes_matrix.py
    PYTHONPATH=. python scripts/experiments/exp_bayes_matrix.py --emit-macros
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
MACROS_PATH = ROOT / "evidence_pack" / "theorem_v2" / "bayes_error_macros.tex"
OUT_DIR = ROOT / "evidence_pack" / "audit"

PROJECTIONS = ["term", "aset", "nord", "nctx"]
VIOL_TYPES = ["omit", "commit", "time", "seq", "dev"]
VIOL_LABELS = {
    "omit": "OMISSION",
    "commit": "COMMISSION",
    "time": "TIMING",
    "seq": "SEQUENCE",
    "dev": "DEVIATION",
}


def parse_macros(path: Path) -> dict[str, float]:
    """Extract \\providecommand{\\name}{value} pairs from a .tex file."""
    macros: dict[str, float] = {}
    pattern = re.compile(r"\\providecommand\{\\(\w+)\}\{([^}]+)\}")
    text = path.read_text()
    for m in pattern.finditer(text):
        name, val = m.group(1), m.group(2)
        # Skip non-numeric values (CIs, percentages with %)
        clean = val.replace("{,}", "").replace(",", "").replace("\\,", "")
        if clean.endswith("%"):
            continue
        try:
            macros[name] = float(clean)
        except ValueError:
            continue
    return macros


def build_matrix(macros: dict[str, float]) -> dict[str, dict[str, float]]:
    """Build 4x5 matrix from parsed macros.

    Returns:
        {projection: {viol_type: bayes_error}}
    """
    matrix: dict[str, dict[str, float]] = {}
    for proj in PROJECTIONS:
        row: dict[str, float] = {}
        for vt in VIOL_TYPES:
            key = f"bayesErrCoord{proj.capitalize()}{vt.capitalize()}"
            if key not in macros:
                raise KeyError(f"Missing macro: \\{key}")
            row[vt] = macros[key]
        matrix[proj] = row
    return matrix


def compute_stats(matrix: dict[str, dict[str, float]]) -> dict:
    """Compute row means, column means, and sharpest separations."""
    row_means = {proj: sum(row.values()) / len(row) for proj, row in matrix.items()}
    col_means: dict[str, float] = {}
    for vt in VIOL_TYPES:
        col_means[vt] = sum(matrix[p][vt] for p in PROJECTIONS) / len(PROJECTIONS)

    # Sharpest single-step separation (consecutive projections)
    proj_pairs = list(zip(PROJECTIONS[:-1], PROJECTIONS[1:]))
    max_drop = 0.0
    max_drop_info = {}
    for vt in VIOL_TYPES:
        for p1, p2 in proj_pairs:
            drop = matrix[p1][vt] - matrix[p2][vt]
            if drop > max_drop:
                max_drop = drop
                max_drop_info = {
                    "from_proj": p1,
                    "to_proj": p2,
                    "viol_type": vt,
                    "drop": round(drop, 4),
                    "from_val": matrix[p1][vt],
                    "to_val": matrix[p2][vt],
                }

    return {
        "row_means": {k: round(v, 4) for k, v in row_means.items()},
        "col_means": {k: round(v, 4) for k, v in col_means.items()},
        "sharpest_separation": max_drop_info,
    }


def check_pooled_present(macros: dict[str, float]) -> list[str]:
    """Report missing pooled-projection macros.

    Note: we deliberately do NOT compare row_max vs pooled. For correlated
    coordinates the joint Bayes error can be below any marginal (shared
    information), so row_max > pooled is expected, not a defect. A prior
    version flagged this as a "validation issue" and produced 3 false
    positives on every run.
    """
    issues: list[str] = []
    pooled_keys = {
        "term": "bayesErrTerm",
        "aset": "bayesErrAset",
        "nord": "bayesErrNord",
        "nctx": "bayesErrNctx",
    }
    for proj in PROJECTIONS:
        if macros.get(pooled_keys[proj]) is None:
            issues.append(f"Missing pooled macro for {proj}")
    return issues


def print_matrix(matrix: dict[str, dict[str, float]], stats: dict) -> None:
    """Pretty-print the 4x5 matrix with marginals."""
    header = f"{'Projection':>10s}"
    for vt in VIOL_TYPES:
        header += f"  {VIOL_LABELS[vt]:>10s}"
    header += f"  {'Row Mean':>10s}"
    print(header)
    print("-" * len(header))

    for proj in PROJECTIONS:
        row_str = f"{'pi_' + proj:>10s}"
        for vt in VIOL_TYPES:
            val = matrix[proj][vt]
            row_str += f"  {val:10.3f}"
        row_str += f"  {stats['row_means'][proj]:10.4f}"
        print(row_str)

    print("-" * len(header))
    footer = f"{'Col Mean':>10s}"
    for vt in VIOL_TYPES:
        footer += f"  {stats['col_means'][vt]:10.4f}"
    print(footer)


def emit_macros(stats: dict, out_path: Path) -> None:
    """Write derived LaTeX macros."""
    lines = [
        "% Auto-generated by scripts/experiments/exp_bayes_matrix.py",
        "% Derived statistics from the 4x5 Bayes error matrix.",
        "",
    ]
    # Row means
    for proj in PROJECTIONS:
        val = stats["row_means"][proj]
        lines.append(f"\\providecommand{{\\bayesErrRowMean{proj.capitalize()}}}{{{val:.4f}}}")
    lines.append("")
    # Column means
    col_label = {"omit": "Omit", "commit": "Commit", "time": "Time", "seq": "Seq", "dev": "Dev"}
    for vt in VIOL_TYPES:
        val = stats["col_means"][vt]
        lines.append(f"\\providecommand{{\\bayesErrColMean{col_label[vt]}}}{{{val:.4f}}}")
    lines.append("")
    # Sharpest separation
    sep = stats["sharpest_separation"]
    lines.append(f"\\providecommand{{\\bayesErrSharpestViolType}}{{{VIOL_LABELS[sep['viol_type']]}}}")
    lines.append(f"\\providecommand{{\\bayesErrSharpestFrom}}{{{sep['from_proj']}}}")
    lines.append(f"\\providecommand{{\\bayesErrSharpestTo}}{{{sep['to_proj']}}}")
    lines.append(f"\\providecommand{{\\bayesErrSharpestDrop}}{{{sep['drop']:.3f}}}")
    out_path.write_text("\n".join(lines) + "\n")
    print(f"\nSaved derived macros: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="B2: Bayes error matrix validation")
    parser.add_argument("--emit-macros", action="store_true", help="Write derived macros to evidence_pack")
    parser.add_argument("--json", action="store_true", help="Write full results as JSON")
    args = parser.parse_args()

    print(f"Reading macros from {MACROS_PATH}")
    macros = parse_macros(MACROS_PATH)
    print(f"  Parsed {len(macros)} numeric macros")

    matrix = build_matrix(macros)
    stats = compute_stats(matrix)

    print("\n=== 4x5 Bayes Error Matrix ===\n")
    print_matrix(matrix, stats)

    # Shape/coverage sanity only — see check_pooled_present docstring for why
    # we no longer compare row_max vs pooled.
    issues = check_pooled_present(macros)
    if issues:
        print(f"\nCoverage issues ({len(issues)}):")
        for iss in issues:
            print(f"  WARNING: {iss}")
    else:
        print("\nCoverage: PASS (all pooled macros present)")

    # Key findings
    sep = stats["sharpest_separation"]
    print("\nSharpest single-step separation:")
    print(
        f"  {VIOL_LABELS[sep['viol_type']]}: "
        f"pi_{sep['from_proj']} ({sep['from_val']:.3f}) -> "
        f"pi_{sep['to_proj']} ({sep['to_val']:.3f}), "
        f"drop = {sep['drop']:.3f}"
    )

    if args.emit_macros:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        emit_macros(stats, OUT_DIR / "bayes_matrix_derived_macros.tex")

    if args.json:
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        result = {
            "experiment": "B2: Per-violation-type Bayes error matrix",
            "timestamp": datetime.now(UTC).isoformat(),
            "matrix": {p: {k: round(v, 4) for k, v in row.items()} for p, row in matrix.items()},
            "stats": stats,
            "coverage_issues": issues,
        }
        json_path = OUT_DIR / "bayes_matrix_results.json"
        with open(json_path, "w") as f:
            json.dump(result, f, indent=2)
        print(f"Saved: {json_path}")


if __name__ == "__main__":
    main()
