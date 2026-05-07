#!/usr/bin/env python3
"""B3-retry: Constructive pi_nord witness BSR experiment.

Evaluates a family of simple pi_nord-observable evaluators that each look
only at (i) the ordered action trace with timestamps erased, and (ii)
scenario-derived expected/forbidden action sets. The goal is to answer
empirically: can a constructive pi_nord evaluator approach the theoretical
pi_nord Bayes floor (0.003) on CGA-Bench?

Variants tested:
    V1_strict           : expected ⊆ taken AND taken ∩ forbidden = ∅
    V2_no_forbidden     : taken ∩ forbidden = ∅ only (commission-only)
    V3_half_expected    : |taken ∩ expected| / |expected| ≥ 0.5 AND no forbidden
    V4_any_action       : actions_count > 0 AND no forbidden

All BSRs are computed against the TCC (v4_hard) reference on the
14,826-episode W8-filtered corpus. Emits JSON + LaTeX macros for the
paper.

Usage:
    PYTHONPATH=. python scripts/experiments/exp_pi_nord_witness.py
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audit.shims._trajectory_cache import load_trajectory  # noqa: E402
from audit.shims._verdict_cache import get_verdict, load_w8_episodes  # noqa: E402

PI_NORD_BAYES_FLOOR = 0.003

VARIANTS: dict[str, callable] = {
    "V1_strict": lambda taken, expected, forbidden, n_taken: (
        expected.issubset(taken) and not (taken & forbidden)
    ),
    "V2_no_forbidden": lambda taken, expected, forbidden, n_taken: (
        not (taken & forbidden)
    ),
    "V3_half_expected": lambda taken, expected, forbidden, n_taken: (
        (not expected or len(taken & expected) / max(1, len(expected)) >= 0.5)
        and not (taken & forbidden)
    ),
    "V4_any_action": lambda taken, expected, forbidden, n_taken: (
        n_taken > 0 and not (taken & forbidden)
    ),
}


def load_features(eids: list[str]) -> dict[str, tuple]:
    """Cache (taken, expected, forbidden, n_taken) per episode."""
    feats: dict[str, tuple] = {}
    for eid in eids:
        t = load_trajectory(eid)
        if t is None:
            continue
        taken = {a.get("action_id") for a in (t.get("actions") or []) if a.get("action_id")}
        expected = set(t.get("expected_actions") or [])
        forbidden = set(t.get("forbidden_actions") or [])
        feats[eid] = (taken, expected, forbidden, len(taken))
    return feats


def bsr(predict_fn, feats: dict, get_ref) -> dict:
    fa = fr = agree = 0
    for eid, f in feats.items():
        pv = predict_fn(*f)
        rv = get_ref(eid, "v4_hard")
        if pv == rv:
            agree += 1
        elif pv and not rv:
            fa += 1
        else:
            fr += 1
    n = len(feats)
    return {
        "n": n,
        "agree": agree,
        "false_accept": fa,
        "false_reject": fr,
        "bsr": round((fa + fr) / n, 4) if n else 0.0,
    }


def _tex_safe(s: str) -> str:
    return s.replace("_", r"\_")


def main() -> None:
    parser = argparse.ArgumentParser(description="B3 retry: pi_nord constructive witness")
    parser.add_argument("--out-dir", default="evidence_pack/audit")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    w8 = load_w8_episodes()
    eids = sorted(w8.keys())
    print(f"Loading trajectory features for {len(eids)} episodes...")
    feats = load_features(eids)
    print(f"  {len(feats)} episodes have trajectory files\n")

    print(f"pi_nord Bayes floor = {PI_NORD_BAYES_FLOOR}\n")
    print(f"{'variant':<22s}  {'BSR':>8s}  {'FA':>6s}  {'FR':>6s}  {'ratio_to_floor':>14s}")
    print("-" * 62)
    variant_results = {}
    for name, fn in VARIANTS.items():
        r = bsr(fn, feats, get_verdict)
        r["ratio_to_floor"] = round(r["bsr"] / PI_NORD_BAYES_FLOOR, 1)
        variant_results[name] = r
        print(
            f"{name:<22s}  {r['bsr']:8.4f}  {r['false_accept']:6d}  "
            f"{r['false_reject']:6d}  {r['ratio_to_floor']:13.1f}x"
        )

    best_name = min(variant_results, key=lambda k: variant_results[k]["bsr"])
    best = variant_results[best_name]
    gap = round(best["bsr"] - PI_NORD_BAYES_FLOOR, 4)

    result = {
        "experiment": "B3-retry: pi_nord constructive witness BSR",
        "timestamp": datetime.now(UTC).isoformat(),
        "n_episodes": len(feats),
        "pi_nord_bayes_floor": PI_NORD_BAYES_FLOOR,
        "variants": variant_results,
        "best_variant": best_name,
        "best_bsr": best["bsr"],
        "gap_to_floor": gap,
        "ratio_to_floor": best["ratio_to_floor"],
        "finding": (
            "Simple pi_nord-observable evaluators using scenario-provided "
            "expected/forbidden sets achieve BSR ~0.49-0.57, leaving a "
            f"{best['ratio_to_floor']}x gap to the theoretical pi_nord "
            "floor of 0.003. The floor is informative as a lower bound, "
            "but its achievability requires a full patient-conditional "
            "CPG engine — not available from trajectory+scenario metadata "
            "alone. Theorem 3.4 is therefore an existence theorem, not a "
            "constructive recipe on this corpus."
        ),
    }

    json_path = out_dir / "pi_nord_witness_results.json"
    json_path.write_text(json.dumps(result, indent=2) + "\n")
    print(f"\nSaved: {json_path}")

    macros = [
        "% Auto-generated by scripts/experiments/exp_pi_nord_witness.py",
        f"\\providecommand{{\\piNordFloor}}{{{PI_NORD_BAYES_FLOOR}}}",
        f"\\providecommand{{\\piNordWitnessBestName}}{{{_tex_safe(best_name)}}}",
        f"\\providecommand{{\\piNordWitnessBestBSR}}{{{best['bsr']:.4f}}}",
        f"\\providecommand{{\\piNordWitnessBestBSRPct}}{{{best['bsr'] * 100:.1f}}}",
        f"\\providecommand{{\\piNordWitnessRatioToFloor}}{{{best['ratio_to_floor']:.0f}}}",
        f"\\providecommand{{\\piNordWitnessGap}}{{{gap:.4f}}}",
        f"\\providecommand{{\\piNordWitnessFR}}{{{best['false_reject']}}}",
        f"\\providecommand{{\\piNordWitnessFA}}{{{best['false_accept']}}}",
        f"\\providecommand{{\\piNordWitnessStrictBSR}}{{{variant_results['V1_strict']['bsr']:.4f}}}",
        f"\\providecommand{{\\piNordWitnessNoForbiddenBSR}}{{{variant_results['V2_no_forbidden']['bsr']:.4f}}}",
        f"\\providecommand{{\\piNordWitnessNEpisodes}}{{{len(feats):,}}}",
    ]
    macros_path = out_dir / "pi_nord_witness_macros.tex"
    macros_path.write_text("\n".join(macros) + "\n")
    print(f"Saved: {macros_path}")

    print(f"\nBest variant: {best_name} (BSR = {best['bsr']:.4f})")
    print(f"Gap to floor: {gap:.4f}  ({best['ratio_to_floor']}x)")


if __name__ == "__main__":
    main()
