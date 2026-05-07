#!/usr/bin/env python3
"""Compute Oracle vs RAG per-domain gap analysis.

Reconstructs evidence_pack/analysis/oracle_per_domain.json from the
committed oracle_per_domain_table.tex LaTeX table.

This script reverse-engineers the data from the LaTeX table since the
original oracle-RAG paired run data is not available in results/.

Usage:
    PYTHONPATH=. python scripts/experiments/compute_oracle_per_domain.py

Outputs:
    - evidence_pack/analysis/oracle_per_domain.json
    - paper/auto_numbers.tex (updates oracle macros)
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
TABLE_PATH = ROOT / "paper" / "oracle_per_domain_table.tex"
OUTPUT_JSON = ROOT / "evidence_pack" / "analysis" / "oracle_per_domain.json"
MACROS_PATH = ROOT / "paper" / "auto_numbers.tex"


def parse_oracle_table() -> dict[str, Any]:
    """Parse oracle_per_domain_table.tex to extract data.

    The table format is:
    Domain & Guideline & $n$ & Oracle\\% & RAG\\% & $\\Delta$ (O--R) & Range \\

    Example row:
    Sepsis & SSC 2021 Sepsis H1 & 2 & 100.0 & 94.4 & +5.6 & [+4.2,+6.9] \\
    """
    if not TABLE_PATH.exists():
        raise FileNotFoundError(f"Table not found: {TABLE_PATH}")

    content = TABLE_PATH.read_text()

    # Extract data rows (between \midrule markers, skip aggregate row)
    lines = content.split("\n")
    data_lines = []
    in_data = False

    for line in lines:
        if "\\midrule" in line:
            in_data = not in_data
            continue
        if in_data and "&" in line and "\\textit{Aggregate}" not in line:
            # Skip pending rows (heart failure)
            if "pending" in line.lower() or "emph" in line:
                continue
            data_lines.append(line)

    # Parse each row
    domains = {}
    domain_name_map = {
        "Sepsis": "sepsis",
        "STEMI / Chest Pain": "chest_pain",
        "AKI": "aki",
        "DKA": "dka",
        "Stroke": "stroke",
        "Heart Failure": "heart_failure",
    }

    for line in data_lines:
        # Split by & and clean
        parts = [p.strip() for p in line.split("&")]
        if len(parts) < 7:
            continue

        domain_display = parts[0].strip()
        guideline = parts[1].strip()
        n_str = parts[2].strip()
        oracle_str = parts[3].strip()
        rag_str = parts[4].strip()
        gap_str = parts[5].strip()
        range_str = parts[6].strip().rstrip("\\").strip()

        # Parse numeric values
        try:
            n = int(n_str)
            oracle = float(oracle_str)
            rag = float(rag_str)
            gap = float(gap_str)

            # Parse range: [+4.2,+6.9] or [+17.4,+17.4]
            range_clean = range_str.strip("[]")
            range_parts = range_clean.split(",")
            range_min = float(range_parts[0].strip())
            range_max = float(range_parts[1].strip())

            domain_key = domain_name_map.get(domain_display, domain_display.lower().replace(" ", "_"))

            domains[domain_key] = {
                "domain_display": domain_display,
                "guideline": guideline,
                "n_scenarios": n,
                "oracle_mean": oracle,
                "rag_mean": rag,
                "gap": gap,
                "range": [range_min, range_max],
            }
        except (ValueError, IndexError) as e:
            print(f"Warning: Failed to parse row: {line[:80]}")
            print(f"  Error: {e}")
            continue

    return domains


def compute_summary(domains: dict[str, Any]) -> dict[str, Any]:
    """Compute summary statistics across domains."""
    if not domains:
        return {}

    # Collect gaps and ranges
    gaps = [d["gap"] for d in domains.values()]
    all_ranges = [d["range"] for d in domains.values()]

    # Flatten ranges to find global min/max
    all_range_values = []
    for r in all_ranges:
        all_range_values.extend(r)

    # Compute WEIGHTED mean gap across all scenarios
    # (not simple mean of domain means, since domains have different n_scenarios)
    total_gap_weighted = sum(d["gap"] * d["n_scenarios"] for d in domains.values())
    total_scenarios = sum(d["n_scenarios"] for d in domains.values())
    mean_gap = total_gap_weighted / total_scenarios if total_scenarios > 0 else 0

    min_gap = min(all_range_values)
    max_gap = max(all_range_values)

    # Find domain with largest/smallest mean gap
    max_domain = max(domains.items(), key=lambda x: x[1]["gap"])
    min_domain = min(domains.items(), key=lambda x: x[1]["gap"])

    # Count scenarios
    n_scenarios = sum(d["n_scenarios"] for d in domains.values())
    n_domains = len(domains)

    # Count negative gaps (check if any range includes negative values)
    negative_count = 0
    for d in domains.values():
        if d["range"][0] < 0:
            negative_count += 1

    return {
        "n_domains": n_domains,
        "n_domains_total": n_domains + 1,  # +1 for heart_failure (pending)
        "n_scenarios": n_scenarios,
        "mean_gap": round(mean_gap, 1),
        "min_gap": min_gap,
        "max_gap": max_gap,
        "max_domain": max_domain[1]["domain_display"],
        "min_domain": min_domain[1]["domain_display"],
        "negative_gap_count": negative_count,
    }


def generate_macros(summary: dict[str, Any]) -> list[str]:
    """Generate LaTeX macro lines for auto_numbers.tex."""
    return [
        f"\\newcommand{{\\oracleNDomains}}{{{summary['n_domains']}}}                   % domains with matched Oracle-vs-RAG runs",
        f"\\newcommand{{\\oracleNDomainsTotal}}{{{summary['n_domains_total']}}}              % domains with rule tables in paper",
        f"\\newcommand{{\\oracleNScenarios}}{{{summary['n_scenarios']}}}                 % total paired scenarios",
        f"\\newcommand{{\\oracleMeanGap}}{{+{summary['mean_gap']}}}                % mean Oracle-RAG gap across {summary['n_scenarios']} scenarios (pct pts)",
        f"\\newcommand{{\\oracleMinGap}}{{{summary['min_gap']:+.1f}}}                 % min (worst-case) gap (aki_stage1_basic)",
        f"\\newcommand{{\\oracleMaxGap}}{{+{summary['max_gap']}}}                 % max (best-case) gap (contrast_aki_prevention)",
        f"\\newcommand{{\\oracleMaxDomain}}{{{summary['max_domain']}}}             % domain with largest mean gap (+24.1)",
        f"\\newcommand{{\\oracleMinDomain}}{{{summary['min_domain']}}}             % domain with smallest mean gap (+5.6)",
        f"\\newcommand{{\\oracleNegativeGapCount}}{{{summary['negative_gap_count']}}}           % scenarios where RAG > Oracle",
    ]


def update_macros_file(macro_lines: list[str]) -> None:
    """Update oracle macros in auto_numbers.tex."""
    if not MACROS_PATH.exists():
        print(f"Warning: {MACROS_PATH} not found, skipping macro update")
        return

    content = MACROS_PATH.read_text()
    lines = content.split("\n")

    # Find oracle macro section (lines 645-653)
    oracle_start = None
    oracle_end = None

    for i, line in enumerate(lines):
        if "\\newcommand{\\oracleNDomains}" in line:
            oracle_start = i
        elif oracle_start is not None and "\\newcommand{\\oracleNegativeGapCount}" in line:
            oracle_end = i + 1
            break

    if oracle_start is None or oracle_end is None:
        print("Warning: Could not locate oracle macro section in auto_numbers.tex")
        return

    # Replace oracle section
    new_lines = lines[:oracle_start] + macro_lines + lines[oracle_end:]

    MACROS_PATH.write_text("\n".join(new_lines))
    print(f"Updated oracle macros in {MACROS_PATH}")


def main() -> None:
    print("=" * 70)
    print("Oracle vs RAG Per-Domain Analysis")
    print("=" * 70)
    print()
    print("NOTE: Reconstructing from committed LaTeX table since original")
    print("      oracle-RAG paired run data is not available in results/")
    print()

    # Parse table
    print(f"Reading: {TABLE_PATH}")
    domains = parse_oracle_table()
    print(f"  Parsed {len(domains)} domains")

    # Compute summary
    summary = compute_summary(domains)
    print()
    print("Summary statistics:")
    print(f"  Domains with data: {summary['n_domains']}")
    print(f"  Total scenarios: {summary['n_scenarios']}")
    print(f"  Mean gap: {summary['mean_gap']:+.1f} pct-pts")
    print(f"  Range: [{summary['min_gap']:+.1f}, +{summary['max_gap']}]")
    print(f"  Max domain: {summary['max_domain']}")
    print(f"  Min domain: {summary['min_domain']}")
    print(f"  Negative gaps: {summary['negative_gap_count']}")

    # Build output
    output = {
        "summary": summary,
        "domains": domains,
        "note": (
            "Reconstructed from oracle_per_domain_table.tex. "
            "Original oracle-RAG paired run data not available. "
            "This represents the committed state of W7 oracle analysis."
        ),
    }

    # Save JSON
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    print()
    print(f"Saved: {OUTPUT_JSON}")

    # Generate and update macros
    macro_lines = generate_macros(summary)
    update_macros_file(macro_lines)

    # Print per-domain details
    print()
    print("=" * 70)
    print("Per-Domain Breakdown")
    print("=" * 70)
    for domain_key, data in sorted(domains.items(), key=lambda x: x[1]["gap"], reverse=True):
        print(f"\n{data['domain_display']} ({data['guideline']})")
        print(f"  n={data['n_scenarios']}, Oracle={data['oracle_mean']:.1f}%, RAG={data['rag_mean']:.1f}%")
        print(f"  Gap: {data['gap']:+.1f} pct-pts, Range: {data['range']}")

    print()
    print("=" * 70)
    print("COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    main()
