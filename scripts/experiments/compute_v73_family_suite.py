#!/usr/bin/env python3
"""Compute M13: E1 family suite perturbation detection rates on V7.3.

The E1 experiment tests whether action-set evaluators (ASC, PAF, CwT) can detect
single-type violations. By Theorem 1 (coarsening), timing and sequence violations
are structurally invisible to action-set evaluators.

Family types (from sgsc_output/v7_3_final/counterfactual_families.json):
  - timing (172):     WITHIN violations — action set unchanged → detection = 0%
  - sequence (348):   BEFORE violations — action set unchanged → detection = 0%
  - exclusion (64):   FORBID violations — adds forbidden action → PAF might detect
  - alternative (1276): MUST-omit violations — removes required action → ASC might detect

Approach:
  1. Structural: timing/sequence detection = 0% (Theorem 1)
  2. Empirical: For exclusion/alternative, compute from V7.3 episodes
     - Among episodes with ONLY commission violations → PAF detection rate
     - Among episodes with ONLY omission violations → ASC detection rate
  3. Wilson confidence intervals for all rates

Reads from:
  - evidence_pack/analysis/verdict_matrix_v7_3.json (V7.3 Full, 11,286 episodes)
  - sgsc_output/v7_3_final/counterfactual_families.json (family counts)

Outputs:
  - evidence_pack/analysis/v73_family_suite_detection.json
  - paper/auto_numbers_v73_family_suite.tex

Usage:
    PYTHONPATH=. python scripts/experiments/compute_v73_family_suite.py
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import math
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]

VERDICT_MATRIX = REPO_ROOT / "evidence_pack/analysis/verdict_matrix_v7_3.json"
FAMILIES_FILE = REPO_ROOT / "sgsc_output/v7_3_final/counterfactual_families.json"
OUTPUT_JSON = REPO_ROOT / "evidence_pack/analysis/v73_family_suite_detection.json"
OUTPUT_TEX = REPO_ROOT / "paper/auto_numbers_v73_family_suite.tex"


def load_episodes(path: Path) -> list[dict]:
    """Load per-episode data from verdict matrix JSON."""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict) and "per_episode" in data:
        return data["per_episode"]
    if isinstance(data, list):
        return data
    raise ValueError(f"Cannot parse episodes from {path}")


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score confidence interval for binomial proportion.

    Args:
        k: number of successes
        n: number of trials
        z: z-score (1.96 for 95% CI)

    Returns:
        (lower, upper) bounds as percentages
    """
    if n == 0:
        return 0.0, 0.0
    p_hat = k / n
    denom = 1 + z * z / n
    centre = (p_hat + z * z / (2 * n)) / denom
    spread = z * math.sqrt((p_hat * (1 - p_hat) + z * z / (4 * n)) / n) / denom
    lo = max(0.0, centre - spread) * 100
    hi = min(1.0, centre + spread) * 100
    return round(lo, 1), round(hi, 1)


def compute_detection_rates(episodes: list[dict]) -> dict:
    """Compute E1 perturbation detection rates from V7.3 episodes.

    For each violation type, find episodes where ONLY that type occurs,
    then check if evaluators detect (verdict = fail).
    """
    # Categorize episodes by violation type pattern
    # V7.3 uses CONSTRAINT-TYPE names (WITHIN, BEFORE, FORBIDDEN)
    # not standard violation types (TIMING, SEQUENCE, COMMISSION, OMISSION).
    # Mapping: WITHIN→TIMING, BEFORE→SEQUENCE, FORBIDDEN→COMMISSION
    only_timing = []  # WITHIN only (timing violation)
    only_sequence = []  # BEFORE only (sequence violation)
    only_commission = []  # FORBIDDEN only (commission/exclusion family)
    only_omission = []  # OMISSION or REQUIRED only (must-omit/alternative family)
    conformant = []  # No violations (v4_hard = False)

    # Accept both V6-style and V7.3-style type names
    timing_names = {"TIMING", "WITHIN"}
    sequence_names = {"SEQUENCE", "BEFORE"}
    commission_names = {"COMMISSION", "FORBIDDEN"}
    omission_names = {"OMISSION", "REQUIRED"}

    for ep in episodes:
        vt = ep.get("viol_types", [])
        if not isinstance(vt, list):
            vt = []
        vt_set = set(vt)
        v4_hard = ep.get("v4_hard", False)

        if not v4_hard and not vt:
            conformant.append(ep)
        elif vt_set and vt_set.issubset(timing_names):
            only_timing.append(ep)
        elif vt_set and vt_set.issubset(sequence_names):
            only_sequence.append(ep)
        elif vt_set and vt_set.issubset(commission_names):
            only_commission.append(ep)
        elif vt_set and vt_set.issubset(omission_names):
            only_omission.append(ep)

    # Detection = evaluator says FAIL (proxy=False) for violated episodes
    # For structural types (timing, sequence): ASC/PAF CANNOT detect
    # For empirical types: compute actual detection rates

    def detection_rate(eps_list: list[dict], evaluator_field: str, invert: bool = False) -> dict:
        """Compute detection rate for a set of single-type-violated episodes."""
        n = len(eps_list)
        if n == 0:
            return {"n": 0, "detected": 0, "rate_pct": 0.0, "ci_lo": 0.0, "ci_hi": 0.0}
        # Detection = evaluator says FAIL. For proxy fields, True=pass, False=fail.
        # So detection = proxy is False (evaluator correctly identifies violation)
        if invert:
            detected = sum(1 for e in eps_list if e.get(evaluator_field))
        else:
            detected = sum(1 for e in eps_list if not e.get(evaluator_field))
        rate = 100.0 * detected / n
        ci_lo, ci_hi = wilson_ci(detected, n)
        return {
            "n": n,
            "detected": detected,
            "rate_pct": round(rate, 1),
            "ci_lo": ci_lo,
            "ci_hi": ci_hi,
        }

    results = {
        "conformant": {"n": len(conformant)},
        "timing_only": {
            "n": len(only_timing),
            "note": "WITHIN violations — action set unchanged by Theorem 1",
            "asc_detection": detection_rate(only_timing, "ac_proxy"),
            "paf_detection": detection_rate(only_timing, "mab_proxy"),
            "cwt_detection": detection_rate(only_timing, "c2_pass"),
            "tcc_detection": detection_rate(only_timing, "v4_hard", invert=True),
        },
        "sequence_only": {
            "n": len(only_sequence),
            "note": "BEFORE violations — action set unchanged by Theorem 1",
            "asc_detection": detection_rate(only_sequence, "ac_proxy"),
            "paf_detection": detection_rate(only_sequence, "mab_proxy"),
            "cwt_detection": detection_rate(only_sequence, "c2_pass"),
            "tcc_detection": detection_rate(only_sequence, "v4_hard", invert=True),
        },
        "commission_only": {
            "n": len(only_commission),
            "note": "FORBID violations — adds forbidden action, PAF might detect",
            "asc_detection": detection_rate(only_commission, "ac_proxy"),
            "paf_detection": detection_rate(only_commission, "mab_proxy"),
            "cwt_detection": detection_rate(only_commission, "c2_pass"),
            "tcc_detection": detection_rate(only_commission, "v4_hard", invert=True),
        },
        "omission_only": {
            "n": len(only_omission),
            "note": "MUST-omit violations — removes required action, ASC might detect",
            "asc_detection": detection_rate(only_omission, "ac_proxy"),
            "paf_detection": detection_rate(only_omission, "mab_proxy"),
            "cwt_detection": detection_rate(only_omission, "c2_pass"),
            "tcc_detection": detection_rate(only_omission, "v4_hard", invert=True),
        },
    }
    return results


def generate_tex(detection: dict, families: dict) -> str:
    """Generate TeX macros for E1 family suite."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    fam_by_type = families.get("by_type", {})

    lines = [
        "% V7.3 E1 Family Suite Perturbation Detection — M13",
        f"% Generated: {ts}",
        "% Script: scripts/experiments/compute_v73_family_suite.py",
        "",
        "% --- Family counts ---",
        f"\\providecommand{{\\vSevenThreeFamilyTotal}}{{{families.get('total_families', 0)}}}",
        f"\\providecommand{{\\vSevenThreeFamilyExclusion}}{{{fam_by_type.get('exclusion', 0)}}}",
        f"\\providecommand{{\\vSevenThreeFamilyTiming}}{{{fam_by_type.get('timing', 0)}}}",
        f"\\providecommand{{\\vSevenThreeFamilySequence}}{{{fam_by_type.get('sequence', 0)}}}",
        f"\\providecommand{{\\vSevenThreeFamilyAlternative}}{{{fam_by_type.get('alternative', 0)}}}",
        "",
    ]

    # Map family types to detection result keys
    type_map = [
        ("Within", "timing_only", "WITHIN/timing"),
        ("Before", "sequence_only", "BEFORE/sequence"),
        ("Forbid", "commission_only", "FORBID/exclusion"),
        ("Must", "omission_only", "MUST/alternative"),
    ]

    for label, key, desc in type_map:
        det = detection.get(key, {})
        n = det.get("n", 0)
        lines.append(f"% --- E1 {desc}: n={n} single-type episodes ---")
        lines.append(f"\\providecommand{{\\eOneV73{label}N}}{{{n}}}")

        for eval_name, eval_key in [
            ("ASC", "asc_detection"),
            ("PAF", "paf_detection"),
            ("CwT", "cwt_detection"),
            ("TCC", "tcc_detection"),
        ]:
            ev = det.get(eval_key, {})
            rate = ev.get("rate_pct", 0.0)
            ci_lo = ev.get("ci_lo", 0.0)
            ci_hi = ev.get("ci_hi", 0.0)
            lines.append(f"\\providecommand{{\\eOneV73{label}{eval_name}}}{{{rate}}}")
            lines.append(f"\\providecommand{{\\eOneV73{label}{eval_name}Lo}}{{{ci_lo}}}")
            lines.append(f"\\providecommand{{\\eOneV73{label}{eval_name}Hi}}{{{ci_hi}}}")
        lines.append("")

    # Null control (conformant episodes)
    conf_n = detection.get("conformant", {}).get("n", 0)
    lines.append(f"\\providecommand{{\\eOneV73NullN}}{{{conf_n}}}")
    lines.append("")

    return "\n".join(lines) + "\n"


def main() -> int:
    print("=" * 70)
    print("M13: E1 Family Suite Perturbation Detection (V7.3)")
    print("=" * 70)

    if not VERDICT_MATRIX.exists():
        print(f"ERROR: {VERDICT_MATRIX} not found")
        return 1

    # Load family counts
    families = {}
    if FAMILIES_FILE.exists():
        with open(FAMILIES_FILE) as f:
            families = json.load(f)
        print(f"Family counts: {families.get('total_families', 0)} total")
        for ftype, count in families.get("by_type", {}).items():
            print(f"  {ftype}: {count}")
    else:
        print(f"WARNING: {FAMILIES_FILE} not found, using empty family counts")

    # Load episodes
    episodes = load_episodes(VERDICT_MATRIX)
    print(f"\nLoaded {len(episodes)} episodes from V7.3 Full")

    # Compute detection rates
    detection = compute_detection_rates(episodes)

    # Print results
    print(f"\nConformant episodes: {detection['conformant']['n']}")
    print()

    header = f"  {'Type':<18}{'N':<8}{'ASC%':<10}{'PAF%':<10}{'CwT%':<10}{'TCC%':<10}"
    print(header)
    print("  " + "-" * 60)
    for label, key in [
        ("WITHIN/timing", "timing_only"),
        ("BEFORE/sequence", "sequence_only"),
        ("FORBID/commission", "commission_only"),
        ("MUST/omission", "omission_only"),
    ]:
        det = detection[key]
        n = det["n"]
        asc = det["asc_detection"]["rate_pct"]
        paf = det["paf_detection"]["rate_pct"]
        cwt = det["cwt_detection"]["rate_pct"]
        tcc = det["tcc_detection"]["rate_pct"]
        print(f"  {label:<18}{n:<8}{asc:<10}{paf:<10}{cwt:<10}{tcc:<10}")

    # V6 comparison
    print("\n  V6 paper (E1): WITHIN=0%, BEFORE=0%, FORBID=1.4%, MUST=42.9%")

    # Save outputs
    output = {
        "generated": datetime.now(UTC).isoformat(),
        "script": "scripts/experiments/compute_v73_family_suite.py",
        "corpus": str(VERDICT_MATRIX),
        "n_episodes": len(episodes),
        "family_counts": families.get("by_type", {}),
        "family_total": families.get("total_families", 0),
        "detection_rates": detection,
        "v6_paper_comparison": {
            "within_asc": 0.0,
            "before_asc": 0.0,
            "forbid_paf": 1.4,
            "must_asc": 42.9,
        },
        "note": (
            "Detection rates computed on single-type-violation episodes from V7.3 Full. "
            "Timing and sequence detection by ASC/PAF should be ~0% by Theorem 1. "
            "TCC detection should be ~100% for all types (ground truth)."
        ),
    }

    with open(OUTPUT_JSON, "w") as f:
        json.dump(output, f, indent=2)
    print(f"\n  Saved: {OUTPUT_JSON}")

    tex = generate_tex(detection, families)
    with open(OUTPUT_TEX, "w") as f:
        f.write(tex)
    print(f"  Saved: {OUTPUT_TEX}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
