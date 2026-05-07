#!/usr/bin/env python3
"""CRES-9: Two One-Sided Tests (TOST) equivalence test for W8 scaffold independence.

Applies TOST at ±3pp equivalence margin on AO-FA rates for all 6 scaffold pairs
(from 4 scaffolds: react, direct, checklist, tooluse). Also power analysis and
Qwen-family drilldown.

Outputs:
    evidence_pack/cres_9/cres_9_results.json
    evidence_pack/cres_9/cres_9_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/exp_cres_9_tost.py
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from itertools import combinations

import numpy as np
from scipy import stats
from scripts.experiments._common import save_json
from scripts.experiments._episode_cache import EVIDENCE_DIR, W8_SCAFFOLDS, load_w8_verdicts

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

EPSILON = 0.03  # 3 percentage-point equivalence margin (on 0-1 scale)
ALPHA = 0.05  # significance level
POWER_TARGET = 0.80
OUTPUT_DIR = EVIDENCE_DIR / "cres_9"
SEED = 42

EVALUATOR_FIELDS: list[tuple[str, str]] = [
    ("AO-FA", "ao_fa"),
    ("Verdict-Flip", "verdict_flip"),
    ("AC-Proxy", "ac_proxy"),
    ("MAB-Proxy", "mab_proxy"),
    ("C2", "c2_pass"),
    ("CGA-Bench", "cga_pass"),
]

QWEN_MODEL = "qwen35b"


# ---------------------------------------------------------------------------
# TOST core
# ---------------------------------------------------------------------------


def tost_proportions(
    n1: int,
    p1: float,
    n2: int,
    p2: float,
    epsilon: float = EPSILON,
) -> dict:
    """Two One-Sided Tests for equivalence of two proportions.

    Tests H0_lower: delta <= -epsilon  and  H0_upper: delta >= +epsilon
    where delta = p1 - p2.

    Equivalence is declared when both one-sided tests reject at alpha=0.05,
    i.e. p_TOST = max(p_lower, p_upper) < 0.05.

    Returns:
        dict with delta, se, z_lower, z_upper, p_lower, p_upper,
        p_tost, equivalent, ci90_lower, ci90_upper.
    """
    delta = p1 - p2

    # Pooled SE for difference of proportions
    if n1 == 0 or n2 == 0:
        return {
            "n1": n1,
            "n2": n2,
            "p1": p1,
            "p2": p2,
            "delta": delta,
            "se": None,
            "z_lower": None,
            "z_upper": None,
            "p_lower": None,
            "p_upper": None,
            "p_tost": None,
            "equivalent": False,
            "ci90_lower": None,
            "ci90_upper": None,
            "error": "insufficient data",
        }

    # Use unpooled SE (appropriate for TOST on difference of proportions)
    var1 = p1 * (1.0 - p1) / n1 if n1 > 0 else 0.0
    var2 = p2 * (1.0 - p2) / n2 if n2 > 0 else 0.0

    # Handle degenerate case where both rates are identical (or both 0/1)
    se = float(np.sqrt(var1 + var2))
    if se == 0.0:
        # Perfect equivalence: both proportions are identical extreme values
        equivalent = abs(delta) < epsilon
        return {
            "n1": n1,
            "n2": n2,
            "p1": round(p1, 6),
            "p2": round(p2, 6),
            "delta": round(delta, 6),
            "se": 0.0,
            "z_lower": None,
            "z_upper": None,
            "p_lower": 0.0 if delta > -epsilon else 1.0,
            "p_upper": 0.0 if delta < epsilon else 1.0,
            "p_tost": 0.0 if equivalent else 1.0,
            "equivalent": equivalent,
            "ci90_lower": round(delta, 6),
            "ci90_upper": round(delta, 6),
            "note": "degenerate: SE=0",
        }

    # TOST z-statistics
    # H0_lower: delta <= -epsilon  -> reject if z_lower is large
    z_lower = (delta - (-epsilon)) / se
    # H0_upper: delta >= +epsilon  -> reject if z_upper is small (left tail)
    z_upper = (delta - epsilon) / se

    # One-sided p-values
    # p_lower = P(Z > z_lower) = 1 - Phi(z_lower)  [right tail]
    p_lower = float(1.0 - stats.norm.cdf(z_lower))
    # p_upper = P(Z < z_upper) = Phi(z_upper)       [left tail]
    p_upper = float(stats.norm.cdf(z_upper))

    p_tost = max(p_lower, p_upper)
    equivalent = p_tost < ALPHA

    # 90% CI for delta (standard for TOST presentation)
    z90 = stats.norm.ppf(0.95)  # 1.645
    ci90_lower = delta - z90 * se
    ci90_upper = delta + z90 * se

    return {
        "n1": n1,
        "n2": n2,
        "p1": round(p1, 6),
        "p2": round(p2, 6),
        "delta": round(delta, 6),
        "se": round(se, 6),
        "z_lower": round(z_lower, 4),
        "z_upper": round(z_upper, 4),
        "p_lower": round(p_lower, 6),
        "p_upper": round(p_upper, 6),
        "p_tost": round(p_tost, 6),
        "equivalent": equivalent,
        "ci90_lower": round(ci90_lower, 6),
        "ci90_upper": round(ci90_upper, 6),
    }


# ---------------------------------------------------------------------------
# Power / MDE analysis
# ---------------------------------------------------------------------------


def compute_mde(n1: int, n2: int, p_ref: float, epsilon: float = EPSILON) -> float:
    """Minimum Detectable Effect at 80% power for TOST.

    For TOST, the effective test has alpha=0.05 (one-sided), power=0.80.
    We use the standard formula for the MDE of a difference in proportions
    given the TOST equivalence margin epsilon.

    MDE is the smallest |delta| detectable above epsilon at 80% power.

    Args:
        n1: Sample size group 1.
        n2: Sample size group 2.
        p_ref: Reference proportion (used to estimate SE).
        epsilon: Equivalence margin.

    Returns:
        Minimum detectable effect (on 0-1 scale).
    """
    if n1 == 0 or n2 == 0:
        return float("nan")

    # z_alpha for one-sided test (alpha=0.05)
    z_alpha = stats.norm.ppf(1.0 - ALPHA)  # 1.645
    # z_beta for power=0.80
    z_beta = stats.norm.ppf(POWER_TARGET)  # 0.842

    # SE at reference proportion
    se = float(np.sqrt(p_ref * (1.0 - p_ref) / n1 + p_ref * (1.0 - p_ref) / n2))
    if se == 0.0:
        return float("nan")

    # Standard MDE formula for TOST:
    # power = Phi(epsilon/SE - z_alpha) - Phi(-epsilon/SE - z_alpha)
    # Solving for the true delta that achieves target power is complex.
    # Use the approximation: MDE ≈ epsilon - (z_alpha + z_beta) * SE
    # (the delta at which we have 80% power to detect non-equivalence vs the margin)
    mde = epsilon - (z_alpha + z_beta) * se
    return max(0.0, round(mde, 6))


# ---------------------------------------------------------------------------
# Scaffold rate computation
# ---------------------------------------------------------------------------


def compute_scaffold_rate(
    records: list[dict],
    scaffold: str,
    field: str,
    model_filter: str | None = None,
) -> tuple[int, float]:
    """Compute binary rate for a given scaffold and field.

    Args:
        records: List of scored W8 records.
        scaffold: Scaffold name to filter on.
        field: Binary field name (e.g. "ao_fa").
        model_filter: If provided, restrict to this model.

    Returns:
        (n, rate) where rate = sum(field) / n.
    """
    subset = [r for r in records if r.get("scaffold") == scaffold]
    if model_filter is not None:
        subset = [r for r in subset if r.get("model") == model_filter]
    n = len(subset)
    if n == 0:
        return 0, 0.0
    rate = sum(1 for r in subset if r.get(field)) / n
    return n, rate


# ---------------------------------------------------------------------------
# Per-pair TOST analysis
# ---------------------------------------------------------------------------


def run_tost_all_pairs(
    records: list[dict],
    field: str,
    scaffolds: list[str],
    model_filter: str | None = None,
    label: str = "",
) -> dict:
    """Run TOST for all pairs of scaffolds on a given field.

    Returns dict with per-pair results and summary.
    """
    pair_results: list[dict] = []
    n_equivalent = 0
    max_delta = 0.0
    all_mde: list[float] = []

    for s1, s2 in combinations(scaffolds, 2):
        n1, p1 = compute_scaffold_rate(records, s1, field, model_filter)
        n2, p2 = compute_scaffold_rate(records, s2, field, model_filter)

        tost_res = tost_proportions(n1, p1, n2, p2, epsilon=EPSILON)

        # Power/MDE analysis
        p_ref = (p1 + p2) / 2.0 if (p1 + p2) > 0 else 0.1
        mde = compute_mde(n1, n2, p_ref)
        all_mde.append(mde)

        if tost_res["equivalent"]:
            n_equivalent += 1

        abs_delta = abs(tost_res["delta"])
        if abs_delta > max_delta:
            max_delta = abs_delta

        pair_result = {
            "scaffold_a": s1,
            "scaffold_b": s2,
            "field": field,
            "label": label,
            **tost_res,
            "mde_80pct": round(mde, 6) if not np.isnan(mde) else None,
        }
        pair_results.append(pair_result)

        equiv_str = "EQUIVALENT" if tost_res["equivalent"] else "not-equivalent"
        print(f"    {s1} vs {s2}: delta={tost_res['delta']:+.4f}, p_TOST={tost_res['p_tost']:.4f} -> {equiv_str}")

    valid_mde = [m for m in all_mde if not np.isnan(m) and m > 0]
    mean_mde = float(np.mean(valid_mde)) if valid_mde else float("nan")

    return {
        "field": field,
        "label": label,
        "model_filter": model_filter,
        "n_pairs": len(pair_results),
        "n_equivalent": n_equivalent,
        "max_abs_delta": round(max_delta, 6),
        "mean_mde_80pct": round(mean_mde, 6) if not np.isnan(mean_mde) else None,
        "epsilon": EPSILON,
        "alpha": ALPHA,
        "pairs": pair_results,
    }


# ---------------------------------------------------------------------------
# Scaffold summary table
# ---------------------------------------------------------------------------


def scaffold_summary_table(
    records: list[dict],
    scaffolds: list[str],
    field: str,
    model_filter: str | None = None,
) -> list[dict]:
    """Compute per-scaffold rate statistics for a field."""
    rows: list[dict] = []
    for scaffold in scaffolds:
        n, rate = compute_scaffold_rate(records, scaffold, field, model_filter)
        rows.append(
            {
                "scaffold": scaffold,
                "n": n,
                "rate": round(rate, 6),
                "rate_pct": round(rate * 100, 2),
                "field": field,
                "model_filter": model_filter,
            }
        )
    return rows


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run CRES-9 TOST equivalence analysis for W8 scaffold independence."""
    print("=" * 70)
    print("CRES-9: TOST Equivalence Test -- W8 Scaffold Independence")
    print(f"Equivalence margin: ε = ±{EPSILON * 100:.0f}pp")
    print("=" * 70)

    rng = np.random.default_rng(SEED)  # noqa: F841  (seed set for reproducibility)

    # Load W8 verdicts
    print("\nLoading W8 verdicts...")
    _, scored_records = load_w8_verdicts()
    print(f"  Total W8 records: {len(scored_records)}")

    if not scored_records:
        print("ERROR: No W8 records found. Exiting.")
        return

    # Verify scaffold coverage
    scaffold_counts: dict[str, int] = {}
    for r in scored_records:
        s = r.get("scaffold", "")
        scaffold_counts[s] = scaffold_counts.get(s, 0) + 1

    print(f"  Scaffolds found: {scaffold_counts}")

    scaffolds = [s for s in W8_SCAFFOLDS if s in scaffold_counts]
    if len(scaffolds) < 2:
        print(f"ERROR: Need at least 2 scaffolds, found {scaffolds}")
        return

    n_pairs_total = len(list(combinations(scaffolds, 2)))
    print(f"  Active scaffolds: {scaffolds}")
    print(f"  Scaffold pairs: {n_pairs_total}")

    # -----------------------------------------------------------------------
    # Section 1: Primary analysis — AO-FA rate, all models pooled
    # -----------------------------------------------------------------------
    print("\n--- Section 1: Primary TOST — AO-FA rate (all models pooled) ---")
    primary_tost = run_tost_all_pairs(scored_records, "ao_fa", scaffolds, label="all_models")

    # -----------------------------------------------------------------------
    # Section 2: All evaluator fields
    # -----------------------------------------------------------------------
    print("\n--- Section 2: All evaluator fields ---")
    all_field_results: list[dict] = []
    for field_label, field_key in EVALUATOR_FIELDS:
        print(f"\n  Field: {field_label} ({field_key})")
        result = run_tost_all_pairs(scored_records, field_key, scaffolds, label=field_label)
        all_field_results.append(result)

    # -----------------------------------------------------------------------
    # Section 3: Qwen-family drilldown (qwen35b only)
    # -----------------------------------------------------------------------
    print(f"\n--- Section 3: Qwen drilldown ({QWEN_MODEL} only) ---")
    qwen_records = [r for r in scored_records if r.get("model") == QWEN_MODEL]
    print(f"  Qwen35b records: {len(qwen_records)}")

    qwen_tost_results: list[dict] = []
    if qwen_records:
        for field_label, field_key in EVALUATOR_FIELDS:
            print(f"\n  Qwen drilldown — {field_label}:")
            result = run_tost_all_pairs(
                scored_records,
                field_key,
                scaffolds,
                model_filter=QWEN_MODEL,
                label=f"qwen35b_{field_label}",
            )
            qwen_tost_results.append(result)
    else:
        print(f"  WARNING: No records found for model={QWEN_MODEL}")

    # -----------------------------------------------------------------------
    # Section 4: Power analysis summary
    # -----------------------------------------------------------------------
    print("\n--- Section 4: Power Analysis ---")
    power_rows: list[dict] = []
    for s1, s2 in combinations(scaffolds, 2):
        n1, p1 = compute_scaffold_rate(scored_records, s1, "ao_fa")
        n2, p2 = compute_scaffold_rate(scored_records, s2, "ao_fa")
        p_ref = (p1 + p2) / 2.0 if (p1 + p2) > 0 else 0.1
        mde = compute_mde(n1, n2, p_ref)
        row = {
            "scaffold_a": s1,
            "scaffold_b": s2,
            "n1": n1,
            "n2": n2,
            "p_ref": round(p_ref, 4),
            "mde_80pct": round(mde, 6) if not np.isnan(mde) else None,
            "mde_80pct_pp": round(mde * 100, 3) if not np.isnan(mde) else None,
        }
        power_rows.append(row)
        print(f"  {s1} vs {s2}: n=({n1},{n2}), p_ref={p_ref:.3f}, MDE@80%={mde * 100:.2f}pp")

    valid_mdes = [r["mde_80pct"] for r in power_rows if r["mde_80pct"] is not None and r["mde_80pct"] > 0]
    overall_mde = float(np.mean(valid_mdes)) if valid_mdes else float("nan")
    print(f"  Overall mean MDE@80%: {overall_mde * 100:.2f}pp")

    # -----------------------------------------------------------------------
    # Section 5: Per-scaffold summary table
    # -----------------------------------------------------------------------
    scaffold_tables: dict[str, list[dict]] = {}
    for field_label, field_key in EVALUATOR_FIELDS:
        scaffold_tables[field_label] = scaffold_summary_table(scored_records, scaffolds, field_key)

    # -----------------------------------------------------------------------
    # Assemble results
    # -----------------------------------------------------------------------
    n_equivalent_primary = primary_tost["n_equivalent"]
    max_delta_primary = primary_tost["max_abs_delta"]

    results: dict = {
        "experiment": "CRES-9",
        "description": "TOST equivalence test for W8 scaffold independence",
        "config": {
            "epsilon": EPSILON,
            "epsilon_pp": EPSILON * 100,
            "alpha": ALPHA,
            "power_target": POWER_TARGET,
            "scaffolds": scaffolds,
            "n_scaffold_pairs": n_pairs_total,
            "evaluator_fields": [f for f, _ in EVALUATOR_FIELDS],
            "qwen_model": QWEN_MODEL,
            "seed": SEED,
        },
        "primary_ao_fa": primary_tost,
        "all_evaluator_fields": all_field_results,
        "qwen_drilldown": {
            "model": QWEN_MODEL,
            "n_records": len(qwen_records),
            "tost_by_field": qwen_tost_results,
        },
        "power_analysis": {
            "epsilon": EPSILON,
            "power_target": POWER_TARGET,
            "alpha": ALPHA,
            "per_pair": power_rows,
            "overall_mean_mde": round(overall_mde, 6) if not np.isnan(overall_mde) else None,
            "overall_mean_mde_pp": round(overall_mde * 100, 3) if not np.isnan(overall_mde) else None,
        },
        "scaffold_summary_tables": scaffold_tables,
        "conclusion": _build_conclusion(
            n_equivalent=n_equivalent_primary,
            n_pairs=n_pairs_total,
            max_delta=max_delta_primary,
            epsilon=EPSILON,
            all_results=all_field_results,
        ),
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(results, OUTPUT_DIR / "cres_9_results.json")

    # -----------------------------------------------------------------------
    # LaTeX macros
    # -----------------------------------------------------------------------
    mde_pp = round(overall_mde * 100, 1) if not np.isnan(overall_mde) else 0.0
    _write_macros(
        n_equivalent_primary=n_equivalent_primary,
        n_pairs=n_pairs_total,
        mde_pp=mde_pp,
        max_delta_pp=round(max_delta_primary * 100, 1),
        epsilon_pp=EPSILON * 100,
        all_field_results=all_field_results,
        qwen_tost_results=qwen_tost_results,
    )

    # -----------------------------------------------------------------------
    # Print summary
    # -----------------------------------------------------------------------
    _print_summary(primary_tost, all_field_results, qwen_tost_results, power_rows, overall_mde)

    print("\n" + "=" * 70)
    print("CRES-9 COMPLETE")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _build_conclusion(
    n_equivalent: int,
    n_pairs: int,
    max_delta: float,
    epsilon: float,
    all_results: list[dict],
) -> str:
    """Build human-readable conclusion string."""
    eq_frac = f"{n_equivalent}/{n_pairs}"
    max_delta_pp = round(max_delta * 100, 1)
    epsilon_pp = round(epsilon * 100, 0)

    lines = [
        f"Primary (AO-FA): {eq_frac} scaffold pairs declared equivalent "
        f"at ε=±{epsilon_pp:.0f}pp. "
        f"Max |Δ| = {max_delta_pp}pp.",
    ]

    # Count total equivalences across all fields
    total_equiv = sum(r["n_equivalent"] for r in all_results)
    total_tests = sum(r["n_pairs"] for r in all_results)
    lines.append(
        f"Across all {len(all_results)} evaluator fields: "
        f"{total_equiv}/{total_tests} pair x field combinations equivalent."
    )

    return " ".join(lines)


def _write_macros(
    n_equivalent_primary: int,
    n_pairs: int,
    mde_pp: float,
    max_delta_pp: float,
    epsilon_pp: float,
    all_field_results: list[dict],
    qwen_tost_results: list[dict],
) -> None:
    """Write LaTeX macros for CRES-9 results."""
    lines: list[str] = [
        "% CRES-9: TOST Scaffold Equivalence Macros",
        "% Auto-generated by exp_cres_9_tost.py",
        "%",
    ]

    def macro(name: str, value: str, comment: str = "") -> str:
        base = f"\\newcommand{{\\{name}}}{{{value}}}"
        if comment:
            return f"{base}  % {comment}"
        return base

    lines.append(
        macro(
            "cresNineTOSTPass",
            str(n_equivalent_primary),
            f"equivalent pairs (AO-FA) out of {n_pairs}",
        )
    )
    lines.append(
        macro(
            "cresNineTOSTTotal",
            str(n_pairs),
            "total scaffold pairs tested",
        )
    )
    lines.append(
        macro(
            "cresNineMDE",
            f"{mde_pp:.1f}",
            "mean MDE at 80% power (percentage points)",
        )
    )
    lines.append(
        macro(
            "cresNineMaxDelta",
            f"{max_delta_pp:.1f}",
            "max absolute delta across AO-FA pairs (percentage points)",
        )
    )
    lines.append(
        macro(
            "cresNineEpsilon",
            f"{epsilon_pp:.0f}",
            "TOST equivalence margin (percentage points)",
        )
    )

    # Total equivalences across all fields
    total_equiv = sum(r["n_equivalent"] for r in all_field_results)
    total_tests = sum(r["n_pairs"] for r in all_field_results)
    lines.append(
        macro(
            "cresNineTotalEquiv",
            str(total_equiv),
            f"equivalent pair-field combinations out of {total_tests}",
        )
    )
    lines.append(
        macro(
            "cresNineTotalTests",
            str(total_tests),
            "total pair-field combinations tested",
        )
    )

    # Qwen drilldown: AO-FA
    if qwen_tost_results:
        ao_fa_qwen = next((r for r in qwen_tost_results if "AO-FA" in r.get("label", "")), None)
        if ao_fa_qwen:
            lines.append(
                macro(
                    "cresNineQwenEquiv",
                    str(ao_fa_qwen["n_equivalent"]),
                    f"Qwen35b AO-FA equivalent pairs out of {ao_fa_qwen['n_pairs']}",
                )
            )
            lines.append(
                macro(
                    "cresNineQwenMaxDelta",
                    f"{ao_fa_qwen['max_abs_delta'] * 100:.1f}",
                    "Qwen35b max AO-FA delta (pp)",
                )
            )

    macros_path = OUTPUT_DIR / "cres_9_macros.tex"
    macros_path.parent.mkdir(parents=True, exist_ok=True)
    with open(macros_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Saved: {macros_path}")


def _print_summary(
    primary_tost: dict,
    all_field_results: list[dict],
    qwen_tost_results: list[dict],
    power_rows: list[dict],
    overall_mde: float,
) -> None:
    """Print human-readable summary to stdout."""
    print("\n" + "=" * 70)
    print("CRES-9 SUMMARY")
    print("=" * 70)

    print(f"\nEquivalence margin: eps = +/-{EPSILON * 100:.0f}pp (on 0-1 scale)")
    print(f"Significance level: alpha = {ALPHA}")

    print(f"\n--- Primary: AO-FA rate ({primary_tost['n_equivalent']}/{primary_tost['n_pairs']} pairs equivalent) ---")
    print(f"  Max |Δ|: {primary_tost['max_abs_delta'] * 100:.2f}pp")
    print(
        f"  Mean MDE@80%: {primary_tost.get('mean_mde_80pct', 0.0) * 100:.2f}pp"
        if primary_tost.get("mean_mde_80pct")
        else "  Mean MDE@80%: N/A"
    )

    for pair in primary_tost["pairs"]:
        equiv_mark = "✓" if pair["equivalent"] else "✗"
        p_tost = pair.get("p_tost")
        p_str = f"{p_tost:.4f}" if p_tost is not None else "N/A"
        ci_lo = pair.get("ci90_lower")
        ci_hi = pair.get("ci90_upper")
        ci_str = f"[{ci_lo * 100:+.2f}pp, {ci_hi * 100:+.2f}pp]" if ci_lo is not None and ci_hi is not None else "N/A"
        print(
            f"  {equiv_mark} {pair['scaffold_a']} vs {pair['scaffold_b']}: "
            f"δ={pair['delta'] * 100:+.2f}pp, 90%CI={ci_str}, p_TOST={p_str}"
        )

    print("\n--- All evaluator fields summary ---")
    print(f"  {'Field':<20} {'Equiv/Total':<15} {'Max|Δ|pp'}")
    for r in all_field_results:
        print(f"  {r['label']:<20} {r['n_equivalent']}/{r['n_pairs']:<10} {r['max_abs_delta'] * 100:.2f}pp")

    if qwen_tost_results:
        print("\n--- Qwen35b drilldown ---")
        for r in qwen_tost_results:
            label = r["label"].replace(f"{QWEN_MODEL}_", "")
            print(f"  {label:<20} {r['n_equivalent']}/{r['n_pairs']:<10} max|Δ|={r['max_abs_delta'] * 100:.2f}pp")

    print("\n--- Power analysis ---")
    print(
        f"  Overall mean MDE@80% power: {overall_mde * 100:.2f}pp"
        if not np.isnan(overall_mde)
        else "  Overall mean MDE: N/A"
    )

    total_equiv = sum(r["n_equivalent"] for r in all_field_results)
    total_tests = sum(r["n_pairs"] for r in all_field_results)
    print("\n--- Overall verdict ---")
    print(
        f"  {total_equiv}/{total_tests} pair x field combinations declared equivalent "
        f"at eps=+/-{EPSILON * 100:.0f}pp (alpha={ALPHA})"
    )


if __name__ == "__main__":
    main()
