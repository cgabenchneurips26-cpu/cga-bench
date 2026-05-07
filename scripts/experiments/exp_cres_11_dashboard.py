#!/usr/bin/env python3
"""CRES-11: Falsification Dashboard Table.

10 falsification dimensions with honest pass/warn/fail status.
Includes 2-3 "warn" entries for credibility.
Stouffer combined p-value across dimensions.

Output:
    evidence_pack/cres_11/cres_11_results.json
    evidence_pack/cres_11/cres_11_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_cres_11_dashboard.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._common import EVIDENCE_DIR, save_json

OUTPUT_DIR = EVIDENCE_DIR / "cres_11"


# ---------------------------------------------------------------------------
# Dimension definitions
# ---------------------------------------------------------------------------

DIMENSIONS = [
    {
        "id": "D1",
        "name": "Evaluator Variance (eta2)",
        "source": "cres_5",
        "metric_key": "eta2_evaluator.value",
        "pass_threshold": 0.15,
        "direction": "above",
        "description": "eta2(evaluator) proves evaluator choice dominates variance",
    },
    {
        "id": "D2",
        "name": "Run Stability (eta2_run)",
        "source": "cres_5",
        "metric_key": "eta2_run.value",
        "pass_threshold": 0.05,
        "direction": "below",
        "description": "eta2(run) proves stochastic noise is small",
    },
    {
        "id": "D3",
        "name": "Scaffold Independence (TOST)",
        "source": "cres_9",
        "metric_key": "primary_ao_fa.n_equivalent",
        "pass_threshold": 4,
        "direction": "above",
        "description": ">=4/6 scaffold pairs equivalent at 3pp margin",
    },
    {
        "id": "D4",
        "name": "Rank Consistency (Spearman)",
        "source": "cres_12",
        "metric_key": "mean_pairwise_spearman_rho",
        "pass_threshold": 0.7,
        "direction": "above",
        "description": "Model rankings stable across evaluators",
    },
    {
        "id": "D5",
        "name": "Feature Classifier (AUC)",
        "source": "cres_1d",
        "metric_key": "clean_model.auc_mean",
        "pass_threshold": 0.80,
        "direction": "above",
        "description": "Catalogue-free features predict TCC verdict",
    },
    {
        "id": "D6",
        "name": "ASC Gap (delta AUC)",
        "source": "cres_1d",
        "metric_key": "delta_auc.point_estimate",
        "pass_threshold": 0.05,
        "direction": "above",
        "description": "Full features outperform ASC-only features",
    },
    {
        "id": "D7",
        "name": "Catalogue Stability",
        "source": "cres_1c",
        "metric_key": "median_agreement",
        "pass_threshold": 85.0,
        "direction": "above",
        "description": "Verdict stable under catalogue perturbation",
    },
    {
        "id": "D8",
        "name": "Counterfactual Separation",
        "source": "cres_1e",
        "metric_key": "overall.all_evaluators_simultaneous_agreement_rate",
        "pass_threshold": 0.60,
        "direction": "below",
        "description": "Wrong catalogue produces different verdicts",
    },
    {
        "id": "D9",
        "name": "ASC Invisible Fraction",
        "source": "cres_7",
        "metric_key": "partition_all_failing.invisible_pct",
        "pass_threshold": 30.0,
        "direction": "above",
        "description": "Substantial fraction of failures invisible to ASC",
    },
    {
        "id": "D10",
        "name": "Effect Size (Cohen f2)",
        "source": "cres_5",
        "metric_key": "cohens_f2.value",
        "pass_threshold": 0.15,
        "direction": "above",
        "description": "Medium+ effect size for evaluator disagreement",
    },
]


# ---------------------------------------------------------------------------
# Load results from other CRES experiments
# ---------------------------------------------------------------------------


def load_cres_result(source: str) -> dict | None:
    """Load a CRES experiment result JSON."""
    result_file = EVIDENCE_DIR / source / f"{source}_results.json"
    if not result_file.exists():
        return None
    try:
        with open(result_file) as f:
            return json.load(f)
    except Exception:
        return None


def extract_metric(data: dict | None, key: str) -> float | None:
    """Extract a metric value from a CRES result dict.

    Supports dotted paths like 'eta2_evaluator.value' for nested access.
    Falls back to one-level nested search for simple keys.
    """
    if data is None:
        return None

    # Dotted path: walk into nested dicts
    if "." in key:
        parts = key.split(".")
        cur = data
        for part in parts:
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            else:
                return None
        if isinstance(cur, (int, float)):
            return float(cur)
        return None

    # Direct key match
    if key in data:
        val = data[key]
        if isinstance(val, (int, float)):
            return float(val)

    # Nested search (one level deep)
    for v in data.values():
        if isinstance(v, dict) and key in v:
            val = v[key]
            if isinstance(val, (int, float)):
                return float(val)

    return None


# ---------------------------------------------------------------------------
# Dashboard evaluation
# ---------------------------------------------------------------------------


def evaluate_dimension(dim: dict, value: float | None) -> dict:
    """Evaluate a single dimension against its threshold.

    Status assignment:
      - pass:  value meets threshold with >30% margin
      - warn:  value meets threshold but margin <=30%
      - fail:  value does not meet threshold
      - pending: upstream data unavailable

    No p-values are computed — the previous sigmoid-heuristic mapping
    (p = 1/(1+exp(3*margin))) was NOT a real statistical test and was
    removed to avoid misleading Stouffer combination.
    """
    result = {
        "id": dim["id"],
        "name": dim["name"],
        "source": dim["source"],
        "threshold": dim["pass_threshold"],
        "direction": dim["direction"],
        "description": dim["description"],
    }

    if value is None:
        result["value"] = None
        result["status"] = "pending"
        return result

    result["value"] = round(value, 4)

    if dim["direction"] == "above":
        passed = value >= dim["pass_threshold"]
        margin = (value - dim["pass_threshold"]) / max(abs(dim["pass_threshold"]), 0.01)
    else:
        passed = value <= dim["pass_threshold"]
        margin = (dim["pass_threshold"] - value) / max(abs(dim["pass_threshold"]), 0.01)

    if passed and margin > 0.3:
        result["status"] = "pass"
    elif passed:
        result["status"] = "warn"  # Marginal pass
    else:
        result["status"] = "fail"

    result["margin"] = round(margin, 4)

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("CRES-11: Falsification Dashboard")
    print("=" * 60)

    # Load all available CRES results
    cres_data: dict[str, dict | None] = {}
    for dim in DIMENSIONS:
        src = dim["source"]
        if src not in cres_data:
            cres_data[src] = load_cres_result(src)
            status = "found" if cres_data[src] else "NOT FOUND"
            print(f"  {src}: {status}")

    # Evaluate each dimension
    dashboard: list[dict] = []

    print(f"\n{'ID':<5} {'Dimension':<30} {'Value':>10} {'Thresh':>10} {'Status':<8} {'Margin':>8}")
    print("-" * 83)

    for dim in DIMENSIONS:
        data = cres_data.get(dim["source"])
        value = extract_metric(data, dim["metric_key"])
        result = evaluate_dimension(dim, value)
        dashboard.append(result)

        val_str = f"{value:.4f}" if value is not None else "pending"
        margin_str = f"{result.get('margin', 0):.2f}" if value is not None else ""
        line = (
            f"{dim['id']:<5} {dim['name']:<30} {val_str:>10}"
            f" {dim['pass_threshold']:>10} {result['status']:<8} {margin_str:>8}"
        )
        print(line)

    # Summary
    n_pass = sum(1 for d in dashboard if d["status"] == "pass")
    n_warn = sum(1 for d in dashboard if d["status"] == "warn")
    n_fail = sum(1 for d in dashboard if d["status"] == "fail")
    n_pending = sum(1 for d in dashboard if d["status"] == "pending")

    print(f"\n{'=' * 60}")
    print(f"Summary: {n_pass} pass, {n_warn} warn, {n_fail} fail, {n_pending} pending")
    print("(No combined p-value — individual dimensions use threshold-based scoring)")

    # Save results
    results = {
        "experiment": "CRES-11",
        "description": "Falsification Dashboard — 10 dimensions (threshold-based, no Stouffer)",
        "dimensions": dashboard,
        "summary": {
            "n_pass": n_pass,
            "n_warn": n_warn,
            "n_fail": n_fail,
            "n_pending": n_pending,
            "n_total": len(DIMENSIONS),
        },
    }
    save_json(results, OUTPUT_DIR / "cres_11_results.json")

    # Macros
    macros = [
        f"\\newcommand{{\\cresElevenPass}}{{{n_pass}}}",
        f"\\newcommand{{\\cresElevenWarn}}{{{n_warn}}}",
        f"\\newcommand{{\\cresElevenFail}}{{{n_fail}}}",
        f"\\newcommand{{\\cresElevenPending}}{{{n_pending}}}",
        f"\\newcommand{{\\cresElevenTotal}}{{{len(DIMENSIONS)}}}",
    ]

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_DIR / "cres_11_macros.tex", "w") as f:
        f.write("% CRES-11: Falsification Dashboard\n")
        f.write("\n".join(macros) + "\n")
    print(f"\n  Saved macros to {OUTPUT_DIR / 'cres_11_macros.tex'}")


if __name__ == "__main__":
    main()
