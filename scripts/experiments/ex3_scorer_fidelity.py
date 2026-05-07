#!/usr/bin/env python3
"""EX-3: Native Scorer Fidelity — Part A (Toy Traces) + Part C (Structural Blindness)

Part A: 20 controlled trace pairs scored by MAB-like, AC-like, CwT, and TCC.
Shows that proxy scorers agree with their design definitions.

Part C: Same action multiset, perturbed timing → MAB unchanged, TCC changed.
Proves structural blindness is design-inherent.

Usage:
    PYTHONPATH=. python scripts/experiments/ex3_scorer_fidelity.py
"""

import json
from pathlib import Path

OUTPUT_DIR = Path("evidence_pack/ex3_scorer_fidelity")


def compute_mab_f1(performed: set, expected: set) -> float:
    """MAB-like: F1 of action set overlap."""
    if not performed and not expected:
        return 1.0
    tp = len(performed & expected)
    if tp == 0:
        return 0.0
    precision = tp / len(performed) if performed else 0
    recall = tp / len(expected) if expected else 0
    return 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0


def compute_ac_coverage(performed: set, expected: set) -> float:
    """AC-like: coverage = |performed ∩ expected| / |expected|."""
    if not expected:
        return 1.0
    return len(performed & expected) / len(expected)


def compute_cwt(performed: set, expected: set, n_timing_violations: int) -> float:
    """CwT: coverage - timing penalty."""
    coverage = compute_ac_coverage(performed, expected)
    return coverage - n_timing_violations * 0.05


def compute_tcc(has_omission: bool, has_commission: bool, has_timing: bool, has_sequence: bool) -> bool:
    """TCC: any hard violation → fail."""
    return not (has_omission or has_commission or has_timing or has_sequence)


# ═══════════════════════════════════════════════════════════════════
# Part A: 20 Controlled Toy Traces
# ═══════════════════════════════════════════════════════════════════

TOY_TRACES = [
    # --- 1-4: OMISSION only ---
    {
        "id": 1,
        "category": "OMISSION",
        "description": "1 of 4 mandatory actions missing",
        "expected": {"blood_culture", "antibiotics", "lactate", "fluid_bolus"},
        "performed": {"blood_culture", "antibiotics", "lactate"},
        "forbidden": set(),
        "timing": {},  # action: (performed_time, deadline)
        "sequence": [],  # (before, after)
    },
    {
        "id": 2,
        "category": "OMISSION",
        "description": "2 of 4 mandatory actions missing",
        "expected": {"blood_culture", "antibiotics", "lactate", "fluid_bolus"},
        "performed": {"blood_culture", "antibiotics"},
        "forbidden": set(),
        "timing": {},
        "sequence": [],
    },
    {
        "id": 3,
        "category": "OMISSION",
        "description": "All mandatory actions missing",
        "expected": {"blood_culture", "antibiotics", "lactate", "fluid_bolus"},
        "performed": {"check_vitals", "assess_airway"},
        "forbidden": set(),
        "timing": {},
        "sequence": [],
    },
    {
        "id": 4,
        "category": "OMISSION",
        "description": "All mandatory actions present",
        "expected": {"blood_culture", "antibiotics", "lactate", "fluid_bolus"},
        "performed": {"blood_culture", "antibiotics", "lactate", "fluid_bolus", "check_vitals"},
        "forbidden": set(),
        "timing": {},
        "sequence": [],
    },
    # --- 5-8: COMMISSION only ---
    {
        "id": 5,
        "category": "COMMISSION",
        "description": "1 forbidden action performed",
        "expected": {"assess_airway", "give_epinephrine"},
        "performed": {"assess_airway", "give_epinephrine", "give_nitroglycerin"},
        "forbidden": {"give_nitroglycerin"},
        "timing": {},
        "sequence": [],
    },
    {
        "id": 6,
        "category": "COMMISSION",
        "description": "Forbidden action not performed",
        "expected": {"assess_airway", "give_epinephrine"},
        "performed": {"assess_airway", "give_epinephrine"},
        "forbidden": {"give_nitroglycerin"},
        "timing": {},
        "sequence": [],
    },
    {
        "id": 7,
        "category": "COMMISSION",
        "description": "2 forbidden actions performed",
        "expected": {"ecg", "troponin"},
        "performed": {"ecg", "troponin", "give_haloperidol", "give_nitroglycerin"},
        "forbidden": {"give_haloperidol", "give_nitroglycerin"},
        "timing": {},
        "sequence": [],
    },
    {
        "id": 8,
        "category": "COMMISSION",
        "description": "Forbidden action present, mandatory missing",
        "expected": {"ecg", "troponin", "aspirin"},
        "performed": {"ecg", "give_haloperidol"},
        "forbidden": {"give_haloperidol"},
        "timing": {},
        "sequence": [],
    },
    # --- 9-12: TIMING only ---
    {
        "id": 9,
        "category": "TIMING",
        "description": "1 action late (antibiotics at 90min, deadline 60min)",
        "expected": {"blood_culture", "antibiotics", "lactate"},
        "performed": {"blood_culture", "antibiotics", "lactate"},
        "forbidden": set(),
        "timing": {"antibiotics": (90, 60)},
        "sequence": [],
    },
    {
        "id": 10,
        "category": "TIMING",
        "description": "All actions on time",
        "expected": {"blood_culture", "antibiotics", "lactate"},
        "performed": {"blood_culture", "antibiotics", "lactate"},
        "forbidden": set(),
        "timing": {"antibiotics": (30, 60)},
        "sequence": [],
    },
    {
        "id": 11,
        "category": "TIMING",
        "description": "2 actions late",
        "expected": {"blood_culture", "antibiotics", "lactate"},
        "performed": {"blood_culture", "antibiotics", "lactate"},
        "forbidden": set(),
        "timing": {"antibiotics": (90, 60), "lactate": (45, 30)},
        "sequence": [],
    },
    {
        "id": 12,
        "category": "TIMING",
        "description": "Action at exact deadline (boundary)",
        "expected": {"blood_culture", "antibiotics"},
        "performed": {"blood_culture", "antibiotics"},
        "forbidden": set(),
        "timing": {"antibiotics": (60, 60)},
        "sequence": [],
    },
    # --- 13-16: SEQUENCE only ---
    {
        "id": 13,
        "category": "SEQUENCE",
        "description": "Blood culture after antibiotics (wrong order)",
        "expected": {"blood_culture", "antibiotics"},
        "performed": {"blood_culture", "antibiotics"},
        "forbidden": set(),
        "timing": {},
        "sequence": [("blood_culture", "antibiotics")],  # blood_culture must be BEFORE antibiotics
        "performed_order": ["antibiotics", "blood_culture"],  # actual: reversed
    },
    {
        "id": 14,
        "category": "SEQUENCE",
        "description": "Correct order: blood culture then antibiotics",
        "expected": {"blood_culture", "antibiotics"},
        "performed": {"blood_culture", "antibiotics"},
        "forbidden": set(),
        "timing": {},
        "sequence": [("blood_culture", "antibiotics")],
        "performed_order": ["blood_culture", "antibiotics"],  # correct
    },
    {
        "id": 15,
        "category": "SEQUENCE",
        "description": "2 sequence violations",
        "expected": {"ecg", "troponin", "aspirin"},
        "performed": {"ecg", "troponin", "aspirin"},
        "forbidden": set(),
        "timing": {},
        "sequence": [("ecg", "troponin"), ("ecg", "aspirin")],
        "performed_order": ["aspirin", "troponin", "ecg"],  # ecg last = 2 violations
    },
    {
        "id": 16,
        "category": "SEQUENCE",
        "description": "Correct ordering for all",
        "expected": {"ecg", "troponin", "aspirin"},
        "performed": {"ecg", "troponin", "aspirin"},
        "forbidden": set(),
        "timing": {},
        "sequence": [("ecg", "troponin"), ("ecg", "aspirin")],
        "performed_order": ["ecg", "troponin", "aspirin"],
    },
    # --- 17-18: Mixed ---
    {
        "id": 17,
        "category": "MIXED",
        "description": "OMISSION + TIMING: 1 missing + 1 late",
        "expected": {"blood_culture", "antibiotics", "lactate", "fluid_bolus"},
        "performed": {"blood_culture", "antibiotics", "lactate"},
        "forbidden": set(),
        "timing": {"antibiotics": (90, 60)},
        "sequence": [],
    },
    {
        "id": 18,
        "category": "MIXED",
        "description": "COMMISSION + SEQUENCE: forbidden + wrong order",
        "expected": {"ecg", "troponin"},
        "performed": {"ecg", "troponin", "give_haloperidol"},
        "forbidden": {"give_haloperidol"},
        "timing": {},
        "sequence": [("ecg", "troponin")],
        "performed_order": ["troponin", "ecg", "give_haloperidol"],
    },
    # --- 19-20: Clean ---
    {
        "id": 19,
        "category": "CLEAN",
        "description": "Perfect: all mandatory, no forbidden, on time, correct order",
        "expected": {"blood_culture", "antibiotics", "lactate"},
        "performed": {"blood_culture", "antibiotics", "lactate"},
        "forbidden": {"give_nitroglycerin"},
        "timing": {"antibiotics": (30, 60)},
        "sequence": [("blood_culture", "antibiotics")],
        "performed_order": ["blood_culture", "antibiotics", "lactate"],
    },
    {
        "id": 20,
        "category": "CLEAN",
        "description": "Perfect with extra actions (not harmful)",
        "expected": {"blood_culture", "antibiotics"},
        "performed": {"blood_culture", "antibiotics", "check_vitals", "order_cbc"},
        "forbidden": set(),
        "timing": {},
        "sequence": [],
    },
]


def score_trace(trace: dict) -> dict:
    """Score a toy trace with all 4 evaluator types."""
    performed = trace["performed"]
    expected = trace["expected"]
    forbidden = trace["forbidden"]

    # OMISSION
    has_omission = bool(expected - performed)

    # COMMISSION
    has_commission = bool(forbidden & performed)

    # TIMING
    n_timing = 0
    has_timing = False
    for action, (actual_time, deadline) in trace.get("timing", {}).items():
        if actual_time > deadline:
            n_timing += 1
            has_timing = True

    # SEQUENCE
    has_sequence = False
    performed_order = trace.get("performed_order", list(performed))
    for before_action, after_action in trace.get("sequence", []):
        if before_action in performed_order and after_action in performed_order:
            if performed_order.index(before_action) > performed_order.index(after_action):
                has_sequence = True

    # Score with each evaluator
    mab_f1 = compute_mab_f1(performed, expected)
    ac_cov = compute_ac_coverage(performed, expected)
    cwt = compute_cwt(performed, expected, n_timing)

    mab_pass = mab_f1 >= 0.5
    ac_pass = ac_cov >= 0.5
    cwt_pass = cwt >= 0.7
    tcc_pass = compute_tcc(has_omission, has_commission, has_timing, has_sequence)

    return {
        "mab_f1": round(mab_f1, 3),
        "mab_pass": mab_pass,
        "ac_cov": round(ac_cov, 3),
        "ac_pass": ac_pass,
        "cwt": round(cwt, 3),
        "cwt_pass": cwt_pass,
        "tcc_pass": tcc_pass,
        "violations": {
            "OMISSION": has_omission,
            "COMMISSION": has_commission,
            "TIMING": has_timing,
            "SEQUENCE": has_sequence,
        },
    }


# ═══════════════════════════════════════════════════════════════════
# Part C: Structural Blindness Confirmation
# ═══════════════════════════════════════════════════════════════════

BLINDNESS_PAIRS = [
    {
        "id": "B1",
        "description": "Same action set, timing changed: on-time → late",
        "safe": {
            "expected": {"antibiotics", "blood_culture", "lactate"},
            "performed": {"antibiotics", "blood_culture", "lactate"},
            "forbidden": set(),
            "timing": {"antibiotics": (30, 60)},
            "sequence": [],
        },
        "unsafe": {
            "expected": {"antibiotics", "blood_culture", "lactate"},
            "performed": {"antibiotics", "blood_culture", "lactate"},
            "forbidden": set(),
            "timing": {"antibiotics": (90, 60)},
            "sequence": [],
        },
        "blind_evaluators": ["MAB", "AC"],  # These should give same score
        "detecting_evaluators": ["CwT", "TCC"],  # These should differ
    },
    {
        "id": "B2",
        "description": "Same action set, ordering changed: correct → reversed",
        "safe": {
            "expected": {"blood_culture", "antibiotics"},
            "performed": {"blood_culture", "antibiotics"},
            "forbidden": set(),
            "timing": {},
            "sequence": [("blood_culture", "antibiotics")],
            "performed_order": ["blood_culture", "antibiotics"],
        },
        "unsafe": {
            "expected": {"blood_culture", "antibiotics"},
            "performed": {"blood_culture", "antibiotics"},
            "forbidden": set(),
            "timing": {},
            "sequence": [("blood_culture", "antibiotics")],
            "performed_order": ["antibiotics", "blood_culture"],
        },
        "blind_evaluators": ["MAB", "AC"],
        "detecting_evaluators": ["TCC"],
    },
    {
        "id": "B3",
        "description": "Same actions, 2 timing violations added",
        "safe": {
            "expected": {"ecg", "troponin", "aspirin"},
            "performed": {"ecg", "troponin", "aspirin"},
            "forbidden": set(),
            "timing": {"ecg": (5, 10), "troponin": (10, 15)},
            "sequence": [],
        },
        "unsafe": {
            "expected": {"ecg", "troponin", "aspirin"},
            "performed": {"ecg", "troponin", "aspirin"},
            "forbidden": set(),
            "timing": {"ecg": (30, 10), "troponin": (45, 15)},
            "sequence": [],
        },
        "blind_evaluators": ["MAB", "AC"],
        "detecting_evaluators": ["CwT", "TCC"],
    },
]


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    print("=" * 70)
    print("EX-3: NATIVE SCORER FIDELITY")
    print("=" * 70)

    # Part A
    print("\n## Part A: 20 Toy Traces\n")
    print(f"{'#':>3} {'Cat':>10} {'MAB':>6} {'AC':>6} {'CwT':>6} {'TCC':>6} {'Violations':>25} {'Description'}")
    print(f"{'─' * 3} {'─' * 10} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 6} {'─' * 25} {'─' * 40}")

    all_results = []
    for trace in TOY_TRACES:
        result = score_trace(trace)
        result["id"] = trace["id"]
        result["category"] = trace["category"]
        result["description"] = trace["description"]
        all_results.append(result)

        viols = "+".join(k for k, v in result["violations"].items() if v) or "none"
        mab = "PASS" if result["mab_pass"] else "FAIL"
        ac = "PASS" if result["ac_pass"] else "FAIL"
        cwt = "PASS" if result["cwt_pass"] else "FAIL"
        tcc = "PASS" if result["tcc_pass"] else "FAIL"
        print(
            f"{trace['id']:>3} {trace['category']:>10} {mab:>6} {ac:>6} {cwt:>6} {tcc:>6} {viols:>25} {trace['description'][:40]}"
        )

    # Fidelity check: do scorers behave as their definitions prescribe?
    print("\n## Fidelity Verification\n")

    checks = [
        (
            "Traces 9,11 (TIMING only): MAB/AC should PASS, TCC should FAIL",
            all(
                all_results[i - 1]["mab_pass"] and all_results[i - 1]["ac_pass"] and not all_results[i - 1]["tcc_pass"]
                for i in [9, 11]
            ),
        ),
        (
            "Traces 13,15 (SEQUENCE only): MAB/AC should PASS, TCC should FAIL",
            all(
                all_results[i - 1]["mab_pass"] and all_results[i - 1]["ac_pass"] and not all_results[i - 1]["tcc_pass"]
                for i in [13, 15]
            ),
        ),
        (
            "Trace 4 (all present): all should PASS",
            all_results[3]["mab_pass"] and all_results[3]["ac_pass"] and all_results[3]["tcc_pass"],
        ),
        ("Trace 3 (all missing): MAB/AC should FAIL", not all_results[2]["mab_pass"] and not all_results[2]["ac_pass"]),
        ("Trace 5 (forbidden done): TCC should FAIL", not all_results[4]["tcc_pass"]),
        ("Trace 6 (forbidden not done): TCC should PASS", all_results[5]["tcc_pass"]),
        (
            "Trace 19 (perfect): all PASS",
            all_results[18]["mab_pass"] and all_results[18]["ac_pass"] and all_results[18]["tcc_pass"],
        ),
    ]

    n_pass = 0
    for desc, passed in checks:
        marker = "✅" if passed else "🔴"
        print(f"  {marker} {desc}")
        if passed:
            n_pass += 1

    print(f"\n  Fidelity: {n_pass}/{len(checks)} checks pass")

    # Part C
    print("\n## Part C: Structural Blindness Confirmation\n")
    blindness_results = []
    for pair in BLINDNESS_PAIRS:
        safe_result = score_trace(pair["safe"])
        unsafe_result = score_trace(pair["unsafe"])

        blind_confirmed = []
        detect_confirmed = []

        # MAB/AC should give SAME score for safe/unsafe
        if safe_result["mab_f1"] == unsafe_result["mab_f1"]:
            blind_confirmed.append("MAB")
        if safe_result["ac_cov"] == unsafe_result["ac_cov"]:
            blind_confirmed.append("AC")

        # CwT/TCC should DIFFER
        if safe_result["cwt_pass"] != unsafe_result["cwt_pass"]:
            detect_confirmed.append("CwT")
        if safe_result["tcc_pass"] != unsafe_result["tcc_pass"]:
            detect_confirmed.append("TCC")

        all_blind_ok = all(e in blind_confirmed for e in pair["blind_evaluators"])
        all_detect_ok = all(e in detect_confirmed for e in pair["detecting_evaluators"])

        marker = "✅" if (all_blind_ok and all_detect_ok) else "🟡"
        print(f"  {marker} {pair['id']}: {pair['description']}")
        print(f"      Blind (same score): {blind_confirmed} (expected: {pair['blind_evaluators']})")
        print(f"      Detect (different): {detect_confirmed} (expected: {pair['detecting_evaluators']})")

        blindness_results.append(
            {
                "id": pair["id"],
                "blind_confirmed": blind_confirmed,
                "detect_confirmed": detect_confirmed,
                "all_ok": all_blind_ok and all_detect_ok,
            }
        )

    n_confirmed = sum(1 for r in blindness_results if r["all_ok"])
    print(f"\n  Blindness confirmed: {n_confirmed}/{len(blindness_results)} pairs")

    # Save
    with open(OUTPUT_DIR / "ex3_report.md", "w") as f:
        f.write(
            f"# EX-3: Scorer Fidelity\n\nPart A: {n_pass}/{len(checks)} fidelity checks pass\nPart C: {n_confirmed}/{len(blindness_results)} blindness pairs confirmed\n"
        )
    with open(OUTPUT_DIR / "ex3_results.json", "w") as f:
        json.dump(
            {
                "part_a": {"traces": all_results, "fidelity_checks": n_pass, "total_checks": len(checks)},
                "part_c": {"blindness_results": blindness_results, "n_confirmed": n_confirmed},
            },
            f,
            indent=2,
            default=str,
        )
    print(f"\n[SAVED] {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
