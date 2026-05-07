#!/usr/bin/env python3
"""CRES-1E: Counterfactual Catalogue Test (Negative Control).

Builds a "wrong" catalogue by inverting rule semantics, then shows it
produces DIFFERENT verdicts from the correct catalogue.  This is a
sanity/falsification check proving the scoring catalogue actually matters.

Three inversion strategies:
  wrong_tcc  -- episodes WITH hard violations pass, WITHOUT fail
  wrong_cov  -- use (1 - coverage) as metric, so ac_proxy_wrong = (1-cov) >= 0.5
  wrong_f1   -- use (1 - f1) so mab_proxy_wrong = (1-f1) >= 0.5

Also tries a "scrambled deadlines" variant: timing violation status is
flipped per episode, then verdicts are recomputed.

Statistical test: McNemar's test between each correct evaluator and its
wrong counterpart.

Outputs:
  evidence_pack/cres_1e/cres_1e_results.json
  evidence_pack/cres_1e/cres_1e_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/exp_cres_1e_counterfactual.py
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from scripts.experiments._common import save_json
from scripts.experiments._episode_cache import (
    AC_COVERAGE_THRESHOLD,
    C2_THRESHOLD,
    EVIDENCE_DIR,
    MAB_F1_THRESHOLD,
    load_cached_verdicts,
)

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------

OUT_DIR = EVIDENCE_DIR / "cres_1e"


# ---------------------------------------------------------------------------
# Wrong-catalogue verdict construction
# ---------------------------------------------------------------------------


def _wrong_tcc(rec: dict) -> bool:
    """Inverted TCC: episodes WITH hard violations pass, WITHOUT fail."""
    return rec["v4_hard"]


def _wrong_coverage(rec: dict) -> bool:
    """Inverted coverage: ac_proxy_wrong = (1 - coverage) >= threshold."""
    return (1.0 - rec["coverage"]) >= AC_COVERAGE_THRESHOLD


def _wrong_f1(rec: dict) -> bool:
    """Inverted F1: mab_proxy_wrong = (1 - f1) >= threshold."""
    return (1.0 - rec["f1"]) >= MAB_F1_THRESHOLD


def _wrong_c2(rec: dict) -> bool:
    """Inverted C2: pass if c2_score < threshold (inverted sense)."""
    return rec["c2_score"] < C2_THRESHOLD


def _scrambled_timing_tcc(rec: dict) -> bool:
    """Scrambled-deadline variant: flip timing violation status.

    Episodes that had ONLY timing violations now pass (timing flipped off),
    episodes with no timing violations but other hard violations stay failing.
    Episodes with no hard violations at all get timing violations injected,
    making them fail.
    """
    vtypes = rec.get("violation_types", [])
    has_timing = rec.get("n_timing", 0) > 0
    has_other_hard = any(vt in ("commission", "sequence") for vt in vtypes)

    if has_other_hard:
        # Other hard violations unchanged, still fails
        return False
    if has_timing and not has_other_hard:
        # Only timing violations — flip: now no timing, so passes
        return True
    # No hard violations — inject a timing violation (flip: now fails)
    return False


# ---------------------------------------------------------------------------
# Cohen's kappa
# ---------------------------------------------------------------------------


def _cohen_kappa(correct: list[bool], wrong: list[bool]) -> float:
    """Compute Cohen's kappa between two binary verdict lists."""
    n = len(correct)
    if n == 0:
        return 0.0

    tp = sum(1 for c, w in zip(correct, wrong) if c and w)
    tn = sum(1 for c, w in zip(correct, wrong) if not c and not w)
    fp = sum(1 for c, w in zip(correct, wrong) if not c and w)
    fn = sum(1 for c, w in zip(correct, wrong) if c and not w)

    agree = (tp + tn) / n
    p_c = (tp + fn) / n * (tp + fp) / n + (tn + fp) / n * (tn + fn) / n
    if 1.0 - p_c < 1e-12:
        return 1.0 if agree == 1.0 else 0.0
    return (agree - p_c) / (1.0 - p_c)


# ---------------------------------------------------------------------------
# McNemar's test
# ---------------------------------------------------------------------------


def _mcnemar(correct: list[bool], wrong: list[bool]) -> tuple[float, float]:
    """McNemar's test between two paired binary verdict lists.

    Uses chi2_contingency on the 2x2 contingency table with correction=False
    to match the standard McNemar formula.

    Returns:
        (chi2_statistic, p_value)
    """
    b = sum(1 for c, w in zip(correct, wrong) if c and not w)
    c = sum(1 for c, w in zip(correct, wrong) if not c and w)

    # Degenerate: no discordant pairs
    if b + c == 0:
        return 0.0, 1.0

    # Standard McNemar chi2 = (b - c)^2 / (b + c)
    chi2 = (b - c) ** 2 / (b + c)
    # p-value from chi2 distribution with df=1
    from scipy.stats import chi2 as chi2_dist

    p = 1.0 - chi2_dist.cdf(chi2, df=1)
    return float(chi2), float(p)


# ---------------------------------------------------------------------------
# Agreement rate
# ---------------------------------------------------------------------------


def _agreement_rate(correct: list[bool], wrong: list[bool]) -> float:
    """Fraction of episodes where correct and wrong verdicts match."""
    if not correct:
        return 0.0
    return sum(1 for c, w in zip(correct, wrong) if c == w) / len(correct)


# ---------------------------------------------------------------------------
# Per-evaluator analysis
# ---------------------------------------------------------------------------


def _analyse_evaluator(
    records: list[dict],
    correct_key: str,
    wrong_fn,
    label: str,
) -> dict:
    """Compute agreement, kappa, McNemar for one evaluator vs its wrong version.

    Args:
        records: Scored episode records.
        correct_key: Key in record for the correct verdict (bool).
        wrong_fn: Callable(record) -> bool for the wrong verdict.
        label: Human-readable label for output.

    Returns:
        Dict with pass rates, agreement, kappa, McNemar stats.
    """
    correct = [bool(r[correct_key]) for r in records]
    wrong = [bool(wrong_fn(r)) for r in records]

    n = len(records)
    correct_pass_rate = sum(correct) / n if n else 0.0
    wrong_pass_rate = sum(wrong) / n if n else 0.0
    agree = _agreement_rate(correct, wrong)
    kappa = _cohen_kappa(correct, wrong)
    chi2_stat, p_val = _mcnemar(correct, wrong)

    return {
        "label": label,
        "n": n,
        "correct_pass_rate": round(correct_pass_rate, 4),
        "wrong_pass_rate": round(wrong_pass_rate, 4),
        "agreement_rate": round(agree, 4),
        "cohen_kappa": round(kappa, 4),
        "mcnemar_chi2": round(chi2_stat, 4),
        "mcnemar_p": round(p_val, 6),
    }


# ---------------------------------------------------------------------------
# Overall wrong-catalogue verdicts (all 4 evaluators inverted)
# ---------------------------------------------------------------------------


def _compute_wrong_catalogue_verdicts(records: list[dict]) -> list[dict]:
    """Compute per-episode wrong-catalogue verdict vector."""
    result = []
    for r in records:
        wrong_ac = _wrong_coverage(r)
        wrong_mab = _wrong_f1(r)
        wrong_c2 = _wrong_c2(r)
        wrong_cga = _wrong_tcc(r)

        correct_verdicts = [r["ac_proxy"], r["mab_proxy"], r["c2_pass"], r["cga_pass"]]
        wrong_verdicts = [wrong_ac, wrong_mab, wrong_c2, wrong_cga]

        # Overall agreement: all 4 evaluators simultaneously match
        all_agree = all(c == w for c, w in zip(correct_verdicts, wrong_verdicts))

        result.append(
            {
                "scenario_id": r["scenario_id"],
                "run_index": r["run_index"],
                "model": r["model"],
                "correct_all_pass": all(correct_verdicts),
                "wrong_all_pass": all(wrong_verdicts),
                "all_evaluators_agree": all_agree,
            }
        )
    return result


# ---------------------------------------------------------------------------
# Scrambled timing analysis
# ---------------------------------------------------------------------------


def _analyse_scrambled_timing(records: list[dict]) -> dict:
    """Analyse the scrambled-deadlines variant.

    Flips timing violation status and recomputes CGA-Bench verdicts,
    then measures agreement with the correct CGA-Bench verdict.

    Returns:
        Dict with scrambled pass rate, agreement, kappa, McNemar stats.
    """
    correct = [bool(r["cga_pass"]) for r in records]
    scrambled = [bool(_scrambled_timing_tcc(r)) for r in records]

    n = len(records)
    correct_pass_rate = sum(correct) / n if n else 0.0
    scrambled_pass_rate = sum(scrambled) / n if n else 0.0
    agree = _agreement_rate(correct, scrambled)
    kappa = _cohen_kappa(correct, scrambled)
    chi2_stat, p_val = _mcnemar(correct, scrambled)

    return {
        "label": "CGA-Bench (scrambled deadlines)",
        "n": n,
        "correct_pass_rate": round(correct_pass_rate, 4),
        "scrambled_pass_rate": round(scrambled_pass_rate, 4),
        "agreement_rate": round(agree, 4),
        "cohen_kappa": round(kappa, 4),
        "mcnemar_chi2": round(chi2_stat, 4),
        "mcnemar_p": round(p_val, 6),
    }


# ---------------------------------------------------------------------------
# LaTeX macro writing
# ---------------------------------------------------------------------------


def _write_macros(
    eval_results: list[dict],
    overall_agreement_rate: float,
    scrambled: dict,
    path: Path,
) -> None:
    """Write LaTeX newcommand macros for CRES-1E results.

    Macros:
      \\cresOneEAgreement      -- mean agreement rate across all 4 evaluators
      \\cresOneEKappa          -- mean Cohen's kappa across all 4 evaluators
      \\cresOneEWrongPassRate  -- wrong-catalogue pass rate (CGA-Bench inversion)
      \\cresOneEMcNemarP       -- minimum McNemar p across evaluators (most significant)
    """
    mean_agree = np.mean([r["agreement_rate"] for r in eval_results])
    mean_kappa = np.mean([r["cohen_kappa"] for r in eval_results])

    # Wrong TCC pass rate = fraction where wrong_tcc passes
    cga_row = next(r for r in eval_results if "CGA" in r["label"])
    wrong_pass_rate = cga_row["wrong_pass_rate"]

    min_p = min(r["mcnemar_p"] for r in eval_results)

    lines = [
        "% CRES-1E Counterfactual Catalogue — auto-generated macros",
        "% DO NOT EDIT — regenerate with exp_cres_1e_counterfactual.py",
        "",
        f"\\newcommand{{\\cresOneEAgreement}}{{{mean_agree:.3f}}}",
        f"\\newcommand{{\\cresOneEKappa}}{{{mean_kappa:.3f}}}",
        f"\\newcommand{{\\cresOneEWrongPassRate}}{{{wrong_pass_rate:.3f}}}",
        f"\\newcommand{{\\cresOneEMcNemarP}}{{{min_p:.2e}}}",
        f"\\newcommand{{\\cresOneEScrambledKappa}}{{{scrambled['cohen_kappa']:.3f}}}",
        f"\\newcommand{{\\cresOneEOverallAgreement}}{{{overall_agreement_rate:.3f}}}",
        "",
    ]

    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Saved: {path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run CRES-1E: Counterfactual Catalogue Test."""
    print("=" * 60)
    print("CRES-1E: Counterfactual Catalogue Test (Negative Control)")
    print("=" * 60)

    print("\n[1/5] Loading episodes and computing correct verdicts...")
    _episodes, records = load_cached_verdicts()
    print(f"  Loaded {len(records)} scored records")

    print("\n[2/5] Computing per-evaluator wrong-catalogue verdicts...")

    evaluator_specs = [
        ("ac_proxy", _wrong_coverage, "AC-Proxy (inverted coverage)"),
        ("mab_proxy", _wrong_f1, "MAB-Proxy (inverted F1)"),
        ("c2_pass", _wrong_c2, "C2 (inverted threshold)"),
        ("cga_pass", _wrong_tcc, "CGA-Bench (inverted hard violations)"),
    ]

    eval_results = []
    for correct_key, wrong_fn, label in evaluator_specs:
        result = _analyse_evaluator(records, correct_key, wrong_fn, label)
        eval_results.append(result)
        print(
            f"  {label}:\n"
            f"    correct pass={result['correct_pass_rate']:.3f}  "
            f"wrong pass={result['wrong_pass_rate']:.3f}  "
            f"agree={result['agreement_rate']:.3f}  "
            f"kappa={result['cohen_kappa']:.3f}  "
            f"McNemar p={result['mcnemar_p']:.2e}"
        )

    print("\n[3/5] Computing overall wrong-catalogue agreement...")
    wrong_verdicts = _compute_wrong_catalogue_verdicts(records)
    overall_agree = sum(1 for r in wrong_verdicts if r["all_evaluators_agree"]) / len(wrong_verdicts)
    wrong_all_pass = sum(1 for r in wrong_verdicts if r["wrong_all_pass"]) / len(wrong_verdicts)
    correct_all_pass = sum(1 for r in wrong_verdicts if r["correct_all_pass"]) / len(wrong_verdicts)
    print(f"  Overall (all 4 evaluators simultaneously agree): {overall_agree:.3f}")
    print(f"  Correct all-pass rate : {correct_all_pass:.3f}")
    print(f"  Wrong all-pass rate   : {wrong_all_pass:.3f}")

    print("\n[4/5] Analysing scrambled-deadlines variant...")
    scrambled_result = _analyse_scrambled_timing(records)
    print(
        f"  CGA-Bench (scrambled timing):\n"
        f"    correct pass={scrambled_result['correct_pass_rate']:.3f}  "
        f"scrambled pass={scrambled_result['scrambled_pass_rate']:.3f}  "
        f"agree={scrambled_result['agreement_rate']:.3f}  "
        f"kappa={scrambled_result['cohen_kappa']:.3f}  "
        f"McNemar p={scrambled_result['mcnemar_p']:.2e}"
    )

    print("\n[5/5] Saving outputs...")

    # Results JSON
    results = {
        "experiment": "cres_1e_counterfactual",
        "description": (
            "Negative control: invert scoring semantics and verify that "
            "wrong verdicts disagree strongly with correct verdicts."
        ),
        "n_episodes": len(records),
        "evaluator_results": eval_results,
        "overall": {
            "all_evaluators_simultaneous_agreement_rate": round(overall_agree, 4),
            "correct_all_pass_rate": round(correct_all_pass, 4),
            "wrong_all_pass_rate": round(wrong_all_pass, 4),
        },
        "scrambled_timing": scrambled_result,
        "interpretation": (
            "Agreement rates << 1.0 and kappa << 0 confirm that inverting "
            "catalogue semantics produces systematically different verdicts, "
            "falsifying the null hypothesis that the catalogue is arbitrary."
        ),
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(results, OUT_DIR / "cres_1e_results.json")

    _write_macros(eval_results, overall_agree, scrambled_result, OUT_DIR / "cres_1e_macros.tex")

    # Summary printout
    mean_agree = float(np.mean([r["agreement_rate"] for r in eval_results]))
    mean_kappa = float(np.mean([r["cohen_kappa"] for r in eval_results]))
    min_p = min(r["mcnemar_p"] for r in eval_results)

    print("\nSummary:")
    print(f"  Mean correct-vs-wrong agreement : {mean_agree:.3f}")
    print(f"  Mean Cohen's kappa              : {mean_kappa:.3f}")
    print(f"  Min McNemar p (most sig.)       : {min_p:.2e}")
    print(f"  Overall all-4 agreement         : {overall_agree:.3f}")
    print(f"  Scrambled-timing kappa          : {scrambled_result['cohen_kappa']:.3f}")
    print("\nDone.")


if __name__ == "__main__":
    main()
