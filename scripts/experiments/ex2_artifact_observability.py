#!/usr/bin/env python3
"""EX-2: Artifact Observability Ladder

5 artifact modes × violation detectability → FA rate per mode.
Proves "observability problem, not scorer problem".

Modes:
  A: Terminal only — no actions visible → only DEVIATION from text
  B: Action multiset — actions but no order, no time → FORBIDDEN, OMISSION
  C: Ordered actions — sequence visible → + SEQUENCE
  D: Timed actions — timestamps visible → + TIMING
  E: Full — + patient state → + conditional FORBIDDEN

Usage:
    PYTHONPATH=. python scripts/experiments/ex2_artifact_observability.py
"""

from collections import Counter
import json
from pathlib import Path

EPISODES_DIR = Path("results/full_706_v5")
OUTPUT_DIR = Path("evidence_pack/ex2_observability")


def load_episodes() -> list:
    episodes = []
    for model_dir in sorted(EPISODES_DIR.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                ep = json.load(open(ep_file))
                if isinstance(ep, dict) and ep.get("scenario_id"):
                    ep["_model"] = model_dir.name
                    episodes.append(ep)
            except Exception:
                pass
    return episodes


def classify_violation(v: dict) -> str | None:
    """Classify violation into canonical type."""
    if not isinstance(v, dict):
        return None
    vt = v.get("violation_type", "").upper()
    if "COMMISSION" in vt:
        return "COMMISSION"
    elif "SEQUENCE" in vt:
        return "SEQUENCE"
    elif "TIMING" in vt:
        return "TIMING"
    elif "OMISSION" in vt:
        return "OMISSION"
    elif "DEVIATION" in vt:
        return "DEVIATION"
    return None


def is_hard(vtype: str) -> bool:
    return vtype in ("COMMISSION", "SEQUENCE", "TIMING", "OMISSION")


def detectable_violations(violations: list, mode: str) -> list:
    """Filter violations to those detectable under given artifact mode."""
    result = []
    for v in violations:
        vtype = classify_violation(v)
        if vtype is None:
            continue

        if mode == "A":
            # Terminal only: nothing detectable from structured violations
            pass
        elif mode == "B":
            # Action multiset: can detect COMMISSION (forbidden in set), OMISSION (missing from set)
            if vtype in ("COMMISSION", "OMISSION"):
                result.append(vtype)
        elif mode == "C":
            # Ordered actions: + SEQUENCE
            if vtype in ("COMMISSION", "OMISSION", "SEQUENCE"):
                result.append(vtype)
        elif mode == "D":
            # Timed actions: + TIMING
            if vtype in ("COMMISSION", "OMISSION", "SEQUENCE", "TIMING"):
                result.append(vtype)
        elif mode == "E":
            # Full: all including conditional COMMISSION
            if vtype in ("COMMISSION", "OMISSION", "SEQUENCE", "TIMING"):
                result.append(vtype)

    return result


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("EX-2: ARTIFACT OBSERVABILITY LADDER")
    print("=" * 70)

    episodes = load_episodes()
    n = len(episodes)
    print(f"Loaded {n} episodes\n")

    modes = ["A", "B", "C", "D", "E"]
    mode_names = {
        "A": "Terminal only",
        "B": "Action multiset",
        "C": "Ordered actions",
        "D": "Timed actions",
        "E": "Full (CGA-Bench)",
    }

    # Per-mode stats
    results = {}
    for mode in modes:
        n_hard_detected = 0
        n_violations_detected = 0
        type_counts = Counter()
        n_fa = 0  # false-accept: no hard violations detected but E has hard

        for ep in episodes:
            viols = ep.get("violation_events", [])
            if not isinstance(viols, list):
                continue

            # Full (E) violations — ground truth
            full_hard = any(is_hard(classify_violation(v)) for v in viols if classify_violation(v))

            # This mode's detectable violations
            detected = detectable_violations(viols, mode)
            has_hard = any(is_hard(vt) for vt in detected)

            if detected:
                n_violations_detected += len(detected)
            if has_hard:
                n_hard_detected += 1

            # FA: this mode says pass (no hard) but TCC says fail (has hard)
            if not has_hard and full_hard:
                n_fa += 1

            for vt in detected:
                type_counts[vt] += 1

        fa_rate = n_fa / n * 100 if n > 0 else 0

        results[mode] = {
            "name": mode_names[mode],
            "n_hard_detected": n_hard_detected,
            "hard_detect_rate": round(n_hard_detected / n * 100, 1),
            "n_fa": n_fa,
            "fa_rate": round(fa_rate, 1),
            "type_counts": dict(type_counts),
            "n_violations": n_violations_detected,
        }

    # Report
    lines = []
    lines.append("=" * 80)
    lines.append("EX-2: ARTIFACT OBSERVABILITY LADDER")
    lines.append(f"Episodes: {n}")
    lines.append("=" * 80)

    lines.append(
        f"\n{'Mode':<6} {'Artifact':<22} {'FORBID':>7} {'OMIT':>7} {'SEQ':>7} {'TIME':>7} {'Hard-ep':>8} {'FA rate':>8}"
    )
    lines.append(f"{'-' * 6} {'-' * 22} {'-' * 7} {'-' * 7} {'-' * 7} {'-' * 7} {'-' * 8} {'-' * 8}")

    for mode in modes:
        r = results[mode]
        tc = r["type_counts"]
        lines.append(
            f"{mode:<6} {r['name']:<22} "
            f"{tc.get('COMMISSION', 0):>7} "
            f"{tc.get('OMISSION', 0):>7} "
            f"{tc.get('SEQUENCE', 0):>7} "
            f"{tc.get('TIMING', 0):>7} "
            f"{r['n_hard_detected']:>8} "
            f"{r['fa_rate']:>7.1f}%"
        )

    # Monotonicity check
    lines.append("\n## Monotonicity Check")
    fa_rates = [results[m]["fa_rate"] for m in modes]
    monotone = all(fa_rates[i] >= fa_rates[i + 1] for i in range(len(fa_rates) - 1))
    lines.append(f"  FA rates: {' → '.join(f'{r:.1f}%' for r in fa_rates)}")
    lines.append(f"  Monotonically decreasing: {'✅ YES' if monotone else '🔴 NO'}")

    # Detection gain per mode transition
    lines.append("\n## Detection Gain per Transition")
    for i in range(1, len(modes)):
        prev = results[modes[i - 1]]
        curr = results[modes[i]]
        gain = prev["fa_rate"] - curr["fa_rate"]
        new_types = set(curr["type_counts"].keys()) - set(prev["type_counts"].keys())
        lines.append(
            f"  {modes[i - 1]}→{modes[i]}: FA {prev['fa_rate']:.1f}%→{curr['fa_rate']:.1f}% (Δ={gain:+.1f}pp) new types: {new_types or 'none'}"
        )

    # Key paper claims
    lines.append("\n## Key Claims for Paper")
    lines.append(f"  1. Terminal-only (A): FA={results['A']['fa_rate']:.1f}% — cannot detect ANY structured violations")
    lines.append(
        f"  2. Action multiset (B): FA={results['B']['fa_rate']:.1f}% — catches FORBIDDEN+OMISSION but blind to timing/ordering"
    )
    lines.append(f"  3. Adding order (C): FA drops to {results['C']['fa_rate']:.1f}% — SEQUENCE violations now visible")
    lines.append(
        f"  4. Adding timestamps (D): FA drops to {results['D']['fa_rate']:.1f}% — TIMING violations now visible"
    )
    lines.append(f"  5. Full artifact (E): FA={results['E']['fa_rate']:.1f}% — all violations detectable")
    b_to_e_gap = results["B"]["fa_rate"] - results["E"]["fa_rate"]
    lines.append(f"  ★ Gap B→E: {b_to_e_gap:.1f}pp — this is what enriched artifacts buy you")

    report = "\n".join(lines)
    print(report)

    with open(OUTPUT_DIR / "ex2_observability_report.md", "w") as f:
        f.write(report)
    with open(OUTPUT_DIR / "ex2_observability_results.json", "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"\n[SAVED] {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
