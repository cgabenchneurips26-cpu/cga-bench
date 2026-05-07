#!/usr/bin/env python3
"""EX-15: Constraint-Type Ablation — Circular Argument Defense

Proves TCC is action-set evaluation EXTENDED, not a different paradigm.
TCC-actionOnly ↔ ASC: high κ (agreement at action-set level)
TCC-full ↔ ASC: low κ (disagreement from BEFORE/WITHIN)

Usage:
    PYTHONPATH=. python scripts/experiments/ex15_constraint_ablation.py
"""

from collections import Counter
import json
from pathlib import Path

import numpy as np
from sklearn.metrics import cohen_kappa_score

from cga_bench.assessor_core.action_normalizer import ActionNormalizer

EPISODES_DIR = Path("results/full_706_v5")
OUTPUT_DIR = Path("evidence_pack/ex15_constraint_ablation")

NORMALIZER = ActionNormalizer()


def norm(name: str) -> str:
    return NORMALIZER.normalize(name.lower().strip()) if name else ""


def load_episodes() -> list:
    episodes = []
    for model_dir in sorted(EPISODES_DIR.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                ep = json.load(open(ep_file))
                if isinstance(ep, dict) and ep.get("scenario_id"):
                    episodes.append(ep)
            except Exception:
                pass
    return episodes


def classify_violation(v: dict) -> str | None:
    if not isinstance(v, dict):
        return None
    vt = v.get("violation_type", "").upper()
    if "OMISSION" in vt:
        return "OMISSION"
    elif "COMMISSION" in vt:
        return "COMMISSION"
    elif "TIMING" in vt:
        return "TIMING"
    elif "SEQUENCE" in vt:
        return "SEQUENCE"
    return None


def compute_tcc_mode(ep: dict, mode: str) -> bool:
    """TCC verdict under constraint-type ablation. True=PASS."""
    allowed = {
        "full": {"OMISSION", "COMMISSION", "SEQUENCE", "TIMING"},
        "actionOnly": {"OMISSION", "COMMISSION"},
        "noTiming": {"OMISSION", "COMMISSION", "SEQUENCE"},
        "noOrder": {"OMISSION", "COMMISSION", "TIMING"},
    }[mode]

    for v in ep.get("violation_events") or []:
        vtype = classify_violation(v)
        if vtype and vtype in allowed:
            return False  # FAIL
    return True  # PASS


def compute_asc(ep: dict) -> bool:
    """ASC: normalizer-aware coverage >= 0.5."""
    performed = set()
    for a in ep.get("actions") or []:
        if isinstance(a, dict):
            aid = a.get("action_id", "")
            if aid:
                performed.add(norm(aid))

    expected = set()
    for a in ep.get("expected_actions") or []:
        if isinstance(a, str):
            expected.add(norm(a))

    if not expected:
        return True
    coverage = len(performed & expected) / len(expected)
    return coverage >= 0.5


def compute_paf(ep: dict) -> bool:
    """PAF: normalizer-aware F1 >= 0.5."""
    performed = set()
    for a in ep.get("actions") or []:
        if isinstance(a, dict):
            aid = a.get("action_id", "")
            if aid:
                performed.add(norm(aid))

    expected = set()
    for a in ep.get("expected_actions") or []:
        if isinstance(a, str):
            expected.add(norm(a))

    if not expected and not performed:
        return True
    if not expected:
        return True
    if not performed:
        return False

    tp = len(performed & expected)
    precision = tp / len(performed)
    recall = tp / len(expected)
    if precision + recall == 0:
        return False
    f1 = 2 * precision * recall / (precision + recall)
    return f1 >= 0.5


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("EX-15: CONSTRAINT-TYPE ABLATION")
    print("=" * 70)

    episodes = load_episodes()
    print(f"Loaded {len(episodes)} episodes\n")

    modes = ["full", "actionOnly", "noTiming", "noOrder"]

    # Compute all verdicts
    tcc = {mode: [] for mode in modes}
    asc_v = []
    paf_v = []

    for ep in episodes:
        for mode in modes:
            tcc[mode].append(compute_tcc_mode(ep, mode))
        asc_v.append(compute_asc(ep))
        paf_v.append(compute_paf(ep))

    # Convert
    for mode in modes:
        tcc[mode] = np.array(tcc[mode], dtype=int)
    asc_v = np.array(asc_v, dtype=int)
    paf_v = np.array(paf_v, dtype=int)

    # Cohen's κ
    print(f"{'Mode':<20} {'vs ASC κ':>10} {'vs PAF κ':>10} {'Pass%':>8}")
    print("-" * 52)

    kappa_results = {}
    for mode in modes:
        k_asc = cohen_kappa_score(tcc[mode], asc_v)
        k_paf = cohen_kappa_score(tcc[mode], paf_v)
        pr = tcc[mode].mean() * 100
        print(f"TCC-{mode:<15} {k_asc:>10.3f} {k_paf:>10.3f} {pr:>7.1f}%")
        kappa_results[mode] = {
            "kappa_asc": round(k_asc, 3),
            "kappa_paf": round(k_paf, 3),
            "pass_rate": round(pr, 1),
        }

    k_asc_paf = cohen_kappa_score(asc_v, paf_v)
    print(f"{'ASC':<20} {'—':>10} {k_asc_paf:>10.3f} {asc_v.mean() * 100:>7.1f}%")
    print(f"{'PAF':<20} {k_asc_paf:>10.3f} {'—':>10} {paf_v.mean() * 100:>7.1f}%")

    # Key comparison
    k_action = kappa_results["actionOnly"]["kappa_asc"]
    k_full = kappa_results["full"]["kappa_asc"]
    delta = k_action - k_full

    print(f"\n{'=' * 50}")
    print("KEY RESULT:")
    print(f"  TCC-actionOnly ↔ ASC: κ = {k_action:.3f}")
    print(f"  TCC-full       ↔ ASC: κ = {k_full:.3f}")
    print(f"  Δκ = {delta:+.3f}")

    if k_action > 0.6 and k_full < 0.4:
        print("  ✅ CONFIRMED: Disagreement from BEFORE/WITHIN, not scoring idiosyncrasy")
    elif delta > 0.2:
        print(f"  🟡 PARTIAL: actionOnly closer to ASC (Δκ={delta:.3f})")
    else:
        print("  ⚠️ UNEXPECTED: ablation doesn't explain disagreement")

    # Disagreement attribution
    action_pass = tcc["actionOnly"].astype(bool)
    full_fail = ~tcc["full"].astype(bool)
    disagree = action_pass & full_fail

    n_disagree = disagree.sum()
    print(f"\n  Episodes: actionOnly=PASS but full=FAIL: {n_disagree} ({n_disagree / len(episodes) * 100:.1f}%)")

    # What type causes the flip?
    type_counts = Counter()
    for i, ep in enumerate(episodes):
        if disagree[i]:
            for v in ep.get("violation_events") or []:
                vtype = classify_violation(v)
                if vtype in ("TIMING", "SEQUENCE"):
                    type_counts[vtype] += 1

    print(f"  Caused by TIMING (WITHIN): {type_counts.get('TIMING', 0)}")
    print(f"  Caused by SEQUENCE (BEFORE): {type_counts.get('SEQUENCE', 0)}")
    print(f"{'=' * 50}")

    # Save
    output = {
        "n_episodes": len(episodes),
        "kappa_results": kappa_results,
        "kappa_asc_paf": round(k_asc_paf, 3),
        "key_result": {
            "kappa_actionOnly_asc": k_action,
            "kappa_full_asc": k_full,
            "delta_kappa": round(delta, 3),
        },
        "disagreement": {
            "n_actionPass_fullFail": int(n_disagree),
            "pct": round(n_disagree / len(episodes) * 100, 1),
            "by_type": dict(type_counts),
        },
    }
    with open(OUTPUT_DIR / "ex15_results.json", "w") as f:
        json.dump(output, f, indent=2, default=str)
    with open(OUTPUT_DIR / "ex15_macros.tex", "w") as f:
        f.write(f"\\newcommand{{\\ablationKappaActionOnly}}{{{k_action:.3f}}}\n")
        f.write(f"\\newcommand{{\\ablationKappaFull}}{{{k_full:.3f}}}\n")
        f.write(f"\\newcommand{{\\ablationKappaDelta}}{{{delta:+.3f}}}\n")
        f.write(f"\\newcommand{{\\ablationDisagreeN}}{{{int(n_disagree)}}}\n")
        f.write(f"\\newcommand{{\\ablationDisagreePct}}{{{n_disagree / len(episodes) * 100:.1f}}}\n")

    print(f"\n[SAVED] {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
