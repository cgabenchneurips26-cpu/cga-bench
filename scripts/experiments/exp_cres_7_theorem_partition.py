#!/usr/bin/env python3
"""CRES-7: Theorem-Empirical Partition.

Classifies blind spots by ASC atomic visibility.  Some scenarios have
violations that AC-Proxy (Action Set Coverage) can structurally see vs
violations it structurally cannot see:

  Class-A (ASC-visible)  : OMISSION violations — a missing action reduces
                           coverage, so ASC can in principle detect it.
  Class-B (ASC-invisible): COMMISSION, TIMING, SEQUENCE violations — the
                           agent performed an action (coverage unchanged),
                           or acted at the wrong time / in the wrong order.
                           Coverage stays high even when the episode fails
                           CGA-Bench.

This partitioning is theorem-level (structural) rather than empirical: it
does not depend on threshold choices.

Also analyses PAF (Penalised Action F1) false-accept episodes:
  For episodes where PAF passes but contains forbidden actions, how does
  the -0.1 per-forbidden-action penalty compare to the threshold?

Outputs:
  evidence_pack/cres_7/cres_7_results.json
  evidence_pack/cres_7/cres_7_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/exp_cres_7_theorem_partition.py
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._common import save_json
from scripts.experiments._episode_cache import (
    EVIDENCE_DIR,
    MAB_F1_THRESHOLD,
    load_cached_verdicts,
)

# ---------------------------------------------------------------------------
# Output paths
# ---------------------------------------------------------------------------

OUT_DIR = EVIDENCE_DIR / "cres_7"

# PAF penalty per forbidden action (fixed design constant)
PAF_FORBIDDEN_PENALTY = 0.1

# PAF passes if penalised F1 >= MAB threshold
PAF_PASS_THRESHOLD = MAB_F1_THRESHOLD


# ---------------------------------------------------------------------------
# Violation class helpers
# ---------------------------------------------------------------------------

# ASC-visible: omission drives coverage down
CLASS_A_TYPES: frozenset[str] = frozenset({"omission"})

# ASC-invisible: action performed (or timing/order wrong, or off-protocol) — coverage unchanged
CLASS_B_TYPES: frozenset[str] = frozenset({"commission", "timing", "sequence", "deviation"})


def _classify_violations(violation_types: list[str]) -> tuple[bool, bool]:
    """Classify violation types present into Class-A and Class-B membership.

    Args:
        violation_types: List of violation type strings for one episode.

    Returns:
        (has_class_a, has_class_b) booleans.
    """
    vset = {vt.lower() for vt in violation_types}
    has_a = bool(vset & CLASS_A_TYPES)
    has_b = bool(vset & CLASS_B_TYPES)
    return has_a, has_b


# ---------------------------------------------------------------------------
# PAF (Penalised Action F1) scoring
# ---------------------------------------------------------------------------


def _paf_score(rec: dict) -> float:
    """Compute PAF score for one episode.

    PAF = max(0, F1 - n_forbidden * penalty)

    where n_forbidden is the number of commission violations (forbidden
    actions performed).

    Args:
        rec: Scored episode record from score_episode().

    Returns:
        PAF score in [0, 1].
    """
    f1 = rec.get("f1", 0.0)
    n_forbidden = rec.get("n_forbidden", 0)
    paf = max(0.0, f1 - n_forbidden * PAF_FORBIDDEN_PENALTY)
    return paf


def _paf_pass(rec: dict) -> bool:
    """Return True if PAF score >= threshold."""
    return _paf_score(rec) >= PAF_PASS_THRESHOLD


# ---------------------------------------------------------------------------
# ASC false-accept analysis
# ---------------------------------------------------------------------------


def _analyse_asc_false_accepts(records: list[dict]) -> dict:
    """Analyse episodes where AC-Proxy passes but CGA-Bench fails.

    These are ASC false-accepts: the coverage metric is fooled by a
    scenario that CGA-Bench correctly flags.

    For each such episode, classify the violation types into Class-A,
    Class-B, or Mixed.

    Returns:
        Dict with counts and fractions.
    """
    # ASC false-accepts: ac_proxy passes, cga fails
    asc_fa = [r for r in records if r["ac_proxy"] and not r["cga_pass"]]
    n_asc_fa = len(asc_fa)

    # n_class_a_only is structurally zero: CGA-Bench failure requires at least
    # one hard violation (commission/timing/sequence/deviation), which is
    # Class-B by definition. Omission-only episodes always pass CGA-Bench.
    n_class_a_only = 0
    n_class_b_only = 0
    n_mixed = 0
    n_neither = 0  # has hard violation but not in A or B (unexpected)
    vtype_counter: Counter[str] = Counter()

    for rec in asc_fa:
        vtypes = rec.get("violation_types", [])
        has_a, has_b = _classify_violations(vtypes)

        for vt in vtypes:
            vtype_counter[vt.lower()] += 1

        if has_a and has_b:
            n_mixed += 1
        elif has_b and not has_a:
            n_class_b_only += 1
        elif has_a and not has_b:
            n_class_a_only += 1
        else:
            # Has hard violation but violation_types list is empty or unknown
            n_neither += 1

    class_b_frac = n_class_b_only / n_asc_fa if n_asc_fa > 0 else 0.0
    class_a_frac = n_class_a_only / n_asc_fa if n_asc_fa > 0 else 0.0
    mixed_frac = n_mixed / n_asc_fa if n_asc_fa > 0 else 0.0

    return {
        "n_asc_false_accepts": n_asc_fa,
        "n_class_a_only": n_class_a_only,
        "n_class_b_only": n_class_b_only,
        "n_mixed": n_mixed,
        "n_neither": n_neither,
        "class_a_only_frac": round(class_a_frac, 4),
        "class_b_only_frac": round(class_b_frac, 4),
        "mixed_frac": round(mixed_frac, 4),
        "violation_type_counts": dict(vtype_counter),
    }


# ---------------------------------------------------------------------------
# Full partition analysis
# ---------------------------------------------------------------------------


def _compute_partition(records: list[dict]) -> dict:
    """Compute Class-A / Class-B partition over all episodes with violations.

    For all episodes that CGA-Bench flags (cga_pass=False), classify them
    and compute structural visibility.

    Returns:
        Dict with total failing episodes, per-class counts and fractions.
    """
    failing = [r for r in records if not r["cga_pass"]]
    n_failing = len(failing)

    # n_class_a_only is structurally zero: CGA-Bench failure requires at least
    # one hard violation (commission/timing/sequence/deviation), which is
    # Class-B by definition. Omission-only episodes always pass CGA-Bench.
    n_class_a_only = 0
    n_class_b_only = 0
    n_mixed = 0
    n_neither = 0

    for rec in failing:
        vtypes = rec.get("violation_types", [])
        has_a, has_b = _classify_violations(vtypes)

        if has_a and has_b:
            n_mixed += 1
        elif has_b and not has_a:
            n_class_b_only += 1
        elif has_a and not has_b:
            n_class_a_only += 1
        else:
            n_neither += 1

    # Invisible fraction: Class-B only (structurally undetectable by ASC)
    invisible_pct = (n_class_b_only / n_failing * 100.0) if n_failing > 0 else 0.0

    return {
        "n_failing": n_failing,
        "n_class_a_only": n_class_a_only,
        "n_class_b_only": n_class_b_only,
        "n_mixed": n_mixed,
        "n_neither": n_neither,
        "invisible_pct": round(invisible_pct, 2),
        "class_a_only_frac": round(n_class_a_only / n_failing, 4) if n_failing else 0.0,
        "class_b_only_frac": round(n_class_b_only / n_failing, 4) if n_failing else 0.0,
        "mixed_frac": round(n_mixed / n_failing, 4) if n_failing else 0.0,
    }


# ---------------------------------------------------------------------------
# PAF false-accept analysis
# ---------------------------------------------------------------------------


def _analyse_paf_false_accepts(records: list[dict]) -> dict:
    """Analyse PAF false-accepts: episodes where PAF passes but CGA fails.

    For these episodes, examine whether the false-accept is due to:
      (a) insufficient penalty — n_forbidden * penalty < threshold gap
      (b) threshold sensitivity — PAF score is close to threshold

    Returns:
        Dict with PAF FA counts, penalty-vs-gap analysis.
    """
    # PAF false-accepts: paf passes, cga fails
    paf_scores = [(r, _paf_score(r)) for r in records]
    paf_fa = [(r, s) for r, s in paf_scores if s >= PAF_PASS_THRESHOLD and not r["cga_pass"]]
    n_paf_fa = len(paf_fa)

    # Count: how many are due to insufficient penalty vs threshold sensitivity
    n_insufficient_penalty = 0  # n_forbidden > 0 but penalty didn't drop below threshold
    n_no_forbidden = 0  # PAF FA with zero forbidden actions (pure coverage/F1 issue)
    n_threshold_sensitive = 0  # PAF score in (threshold, threshold+0.1] (close call)

    forbidden_action_counts: list[int] = []
    paf_score_values: list[float] = []

    for rec, paf in paf_fa:
        n_fb = rec.get("n_forbidden", 0)
        forbidden_action_counts.append(n_fb)
        paf_score_values.append(paf)

        if n_fb == 0:
            n_no_forbidden += 1
        else:
            n_insufficient_penalty += 1

        # Close to threshold: within 0.1 of passing boundary
        if PAF_PASS_THRESHOLD <= paf < PAF_PASS_THRESHOLD + 0.1:
            n_threshold_sensitive += 1

    # Fraction of PAF FAs that have forbidden actions (insufficient penalty)
    insuf_frac = n_insufficient_penalty / n_paf_fa if n_paf_fa else 0.0

    # Mean penalty applied in FA episodes with forbidden actions
    fa_with_fb = [(r, s) for r, s in paf_fa if r.get("n_forbidden", 0) > 0]
    if fa_with_fb:
        mean_penalty_applied = sum(r.get("n_forbidden", 0) * PAF_FORBIDDEN_PENALTY for r, _s in fa_with_fb) / len(
            fa_with_fb
        )
        mean_n_forbidden_in_fa = sum(r.get("n_forbidden", 0) for r, _s in fa_with_fb) / len(fa_with_fb)
    else:
        mean_penalty_applied = 0.0
        mean_n_forbidden_in_fa = 0.0

    return {
        "n_paf_false_accepts": n_paf_fa,
        "n_insufficient_penalty": n_insufficient_penalty,
        "n_no_forbidden_actions": n_no_forbidden,
        "n_threshold_sensitive": n_threshold_sensitive,
        "insufficient_penalty_frac": round(insuf_frac, 4),
        "mean_n_forbidden_in_paf_fa": round(mean_n_forbidden_in_fa, 3),
        "mean_penalty_applied_in_paf_fa": round(mean_penalty_applied, 4),
        "paf_penalty_per_action": PAF_FORBIDDEN_PENALTY,
        "paf_pass_threshold": PAF_PASS_THRESHOLD,
    }


# ---------------------------------------------------------------------------
# LaTeX macro writing
# ---------------------------------------------------------------------------


def _write_macros(
    partition: dict,
    asc_fa: dict,
    paf_fa: dict,
    path: Path,
) -> None:
    """Write LaTeX newcommand macros for CRES-7 results.

    Macros:
      \\cresSevenClassA       -- n_class_a_only in failing episodes
      \\cresSevenClassB       -- n_class_b_only in failing episodes
      \\cresSevenClassBFrac   -- class_b_only_frac (0-1)
      \\cresSevenASCFA        -- n_asc_false_accepts
      \\cresSevenInvisiblePct -- invisible_pct (Class-B percentage of failing)
    """
    lines = [
        "% CRES-7 Theorem-Empirical Partition — auto-generated macros",
        "% DO NOT EDIT — regenerate with exp_cres_7_theorem_partition.py",
        "",
        f"\\newcommand{{\\cresSevenClassA}}{{{partition['n_class_a_only']}}}",
        f"\\newcommand{{\\cresSevenClassB}}{{{partition['n_class_b_only']}}}",
        f"\\newcommand{{\\cresSevenClassBFrac}}{{{partition['class_b_only_frac']:.3f}}}",
        f"\\newcommand{{\\cresSevenASCFA}}{{{asc_fa['n_asc_false_accepts']}}}",
        f"\\newcommand{{\\cresSevenInvisiblePct}}{{{partition['invisible_pct']:.1f}}}",
        f"\\newcommand{{\\cresSevenASCFAClassBFrac}}{{{asc_fa['class_b_only_frac']:.3f}}}",
        f"\\newcommand{{\\cresSevenPAFFA}}{{{paf_fa['n_paf_false_accepts']}}}",
        f"\\newcommand{{\\cresSevenPAFInsufFrac}}{{{paf_fa['insufficient_penalty_frac']:.3f}}}",
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
    """Run CRES-7: Theorem-Empirical Partition."""
    print("=" * 60)
    print("CRES-7: Theorem-Empirical Partition")
    print("=" * 60)

    print("\n[1/5] Loading episodes and scoring...")
    _episodes, records = load_cached_verdicts()
    n = len(records)
    print(f"  Loaded {n} scored records")

    # Summary of evaluator verdicts
    n_ac_pass = sum(1 for r in records if r["ac_proxy"])
    n_cga_fail = sum(1 for r in records if not r["cga_pass"])
    print(f"  AC-Proxy pass: {n_ac_pass} ({n_ac_pass / n * 100:.1f}%)")
    print(f"  CGA-Bench fail: {n_cga_fail} ({n_cga_fail / n * 100:.1f}%)")

    print("\n[2/5] Computing Class-A / Class-B partition over all failing episodes...")
    partition = _compute_partition(records)
    print(f"  Failing episodes   : {partition['n_failing']}")
    print(
        f"  Class-A only (ASC-visible)  : {partition['n_class_a_only']} ({partition['class_a_only_frac'] * 100:.1f}%)"
    )
    print(
        f"  Class-B only (ASC-invisible): {partition['n_class_b_only']} ({partition['class_b_only_frac'] * 100:.1f}%)"
    )
    print(f"  Mixed (A+B)        : {partition['n_mixed']} ({partition['mixed_frac'] * 100:.1f}%)")
    print(f"  Structurally invisible (Class-B only): {partition['invisible_pct']:.1f}%")

    print("\n[3/5] Analysing ASC false-accepts (AC passes, CGA fails)...")
    asc_fa = _analyse_asc_false_accepts(records)
    print(f"  ASC false-accepts total: {asc_fa['n_asc_false_accepts']}")
    print(f"  Class-A only : {asc_fa['n_class_a_only']} ({asc_fa['class_a_only_frac'] * 100:.1f}%)")
    print(f"  Class-B only : {asc_fa['n_class_b_only']} ({asc_fa['class_b_only_frac'] * 100:.1f}%)")
    print(f"  Mixed        : {asc_fa['n_mixed']} ({asc_fa['mixed_frac'] * 100:.1f}%)")
    print("  Violation type counts in ASC-FA episodes:")
    for vt, cnt in sorted(asc_fa["violation_type_counts"].items(), key=lambda x: -x[1]):
        print(f"    {vt}: {cnt}")

    print("\n[4/5] Analysing PAF false-accepts...")
    paf_fa = _analyse_paf_false_accepts(records)
    print(f"  PAF false-accepts total          : {paf_fa['n_paf_false_accepts']}")
    print(
        f"  Due to insufficient penalty      : {paf_fa['n_insufficient_penalty']} "
        f"({paf_fa['insufficient_penalty_frac'] * 100:.1f}%)"
    )
    print(f"  No forbidden actions (pure F1 FA): {paf_fa['n_no_forbidden_actions']}")
    print(f"  Threshold-sensitive (PAF < thresh+0.1): {paf_fa['n_threshold_sensitive']}")
    print(f"  Mean n_forbidden in PAF FA       : {paf_fa['mean_n_forbidden_in_paf_fa']:.2f}")
    print(f"  Mean penalty applied             : {paf_fa['mean_penalty_applied_in_paf_fa']:.4f}")

    print("\n[5/5] Saving outputs...")

    results = {
        "experiment": "cres_7_theorem_partition",
        "description": (
            "Classifies CGA-Bench failing episodes by ASC structural visibility: "
            "Class-A (omission, ASC-visible) vs Class-B (commission/timing/sequence, "
            "ASC-invisible). Proves structural blind spots are not threshold artefacts."
        ),
        "n_episodes": n,
        "class_definitions": {
            "class_a": {
                "name": "ASC-visible",
                "violation_types": sorted(CLASS_A_TYPES),
                "rationale": (
                    "Omission = missing action reduces action coverage, so ASC can in principle detect this failure."
                ),
            },
            "class_b": {
                "name": "ASC-invisible",
                "violation_types": sorted(CLASS_B_TYPES),
                "rationale": (
                    "Commission/timing/sequence = agent performed an action "
                    "(coverage stays high) or acted at wrong time/order. "
                    "Coverage metric cannot distinguish these from correct behaviour."
                ),
            },
        },
        "partition_all_failing": partition,
        "asc_false_accept_analysis": asc_fa,
        "paf_false_accept_analysis": paf_fa,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(results, OUT_DIR / "cres_7_results.json")

    _write_macros(partition, asc_fa, paf_fa, OUT_DIR / "cres_7_macros.tex")

    # Final summary
    print("\nSummary:")
    print(f"  Structurally invisible to ASC (Class-B only, of failing): {partition['invisible_pct']:.1f}%")
    print(f"  ASC false-accepts where only Class-B violations present: {asc_fa['class_b_only_frac'] * 100:.1f}%")
    print(f"  PAF FA due to insufficient penalty: {paf_fa['insufficient_penalty_frac'] * 100:.1f}%")
    print("\nDone.")


if __name__ == "__main__":
    main()
