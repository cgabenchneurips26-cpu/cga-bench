#!/usr/bin/env python3
"""EX-26: Native Scorer Fidelity Audit — synthetic trace validation.

Defines 40 toy traces across 8 categories, each with manually-derived
expected verdicts for AC-Proxy, MAB-Proxy, and TCC.  Runs replay scorers
and reports agreement rate + Cohen's kappa.

Categories (5 traces each):
  1. timing_only:  all actions present, some late
  2. order_only:   all present, wrong sequence
  3. forbid_only:  forbidden action performed
  4. omission_only: required action missing
  5. mixed:        2+ violation types
  6. clean:        no violations
  7. partial:      some required, some missing
  8. boundary:     exactly at scoring thresholds

Output: evidence_pack/ex26_scorer_fidelity/
Macros: fidelityNTraces, fidelityMABExactAgree, etc.

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_e26_scorer_fidelity.py
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._common import save_json, save_markdown

OUTPUT_DIR = ROOT / "evidence_pack" / "ex26_scorer_fidelity"

AC_THRESHOLD = 0.5
MAB_F1_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Scorer implementations (replay versions)
# ---------------------------------------------------------------------------


def ac_score(trace: dict) -> dict:
    """AC-Proxy: coverage >= 0.5."""
    performed = set(trace["actions"])
    required = set(trace["required"])
    if not required:
        return {"score": 1.0, "verdict": "PASS"}
    coverage = len(performed & required) / len(required)
    return {
        "score": round(coverage, 4),
        "verdict": "PASS" if coverage >= AC_THRESHOLD else "FAIL",
    }


def mab_score(trace: dict) -> dict:
    """MAB-Proxy: F1 >= 0.5."""
    performed = set(trace["actions"])
    required = set(trace["required"])
    if not required:
        return {"score": 1.0, "verdict": "PASS"}
    tp = len(performed & required)
    precision = tp / len(performed) if performed else 0.0
    recall = tp / len(required)
    denom = precision + recall
    if denom == 0:
        f1 = 0.0
    else:
        f1 = 2 * precision * recall / denom
    return {
        "score": round(f1, 4),
        "verdict": "PASS" if f1 >= MAB_F1_THRESHOLD else "FAIL",
    }


def tcc_score(trace: dict) -> dict:
    """TCC: any hard violation -> FAIL."""
    performed = set(trace["actions"])
    forbidden = set(trace.get("forbidden", []))
    timestamps = trace.get("timestamps", {})
    deadlines = trace.get("deadlines", {})
    before_constraints = trace.get("before_constraints", [])

    violations: list[str] = []

    # COMMISSION: performed a forbidden action
    commission = performed & forbidden
    for a in commission:
        violations.append(f"COMMISSION({a})")

    # TIMING: action performed after deadline
    for action, deadline in deadlines.items():
        if action in performed:
            ts = timestamps.get(action, 0)
            if ts > deadline:
                violations.append(f"TIMING({action}@{ts}>{deadline})")

    # SEQUENCE: action performed before its prerequisite
    for prereq, action in before_constraints:
        if prereq in performed and action in performed:
            ts_prereq = timestamps.get(prereq, 0)
            ts_action = timestamps.get(action, 0)
            if ts_action < ts_prereq:
                violations.append(f"SEQUENCE({action}<{prereq})")
        elif action in performed and prereq not in performed:
            violations.append(f"SEQUENCE({action} without {prereq})")

    return {
        "score": 0.0 if violations else 1.0,
        "verdict": "FAIL" if violations else "PASS",
        "violations": violations,
    }


SCORERS = {
    "ac": ac_score,
    "mab": mab_score,
    "tcc": tcc_score,
}


# ---------------------------------------------------------------------------
# Trace definitions: 40 traces across 8 categories
# ---------------------------------------------------------------------------


TRACES: list[dict] = [
    # ===== Category 1: timing_only (5) =====
    {
        "id": "T01",
        "category": "timing_only",
        "desc": "Antibiotics late (65 > 60 min deadline)",
        "actions": ["blood_culture", "antibiotics", "lactate"],
        "required": ["blood_culture", "antibiotics", "lactate"],
        "forbidden": [],
        "timestamps": {"blood_culture": 5, "antibiotics": 65, "lactate": 10},
        "deadlines": {"antibiotics": 60},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T02",
        "category": "timing_only",
        "desc": "Lactate late (70 > 60 min deadline)",
        "actions": ["blood_culture", "antibiotics", "lactate"],
        "required": ["blood_culture", "antibiotics", "lactate"],
        "forbidden": [],
        "timestamps": {"blood_culture": 5, "antibiotics": 30, "lactate": 70},
        "deadlines": {"lactate": 60},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T03",
        "category": "timing_only",
        "desc": "Two actions late",
        "actions": ["assess_abc", "epinephrine", "iv_access"],
        "required": ["assess_abc", "epinephrine", "iv_access"],
        "forbidden": [],
        "timestamps": {"assess_abc": 1, "epinephrine": 25, "iv_access": 35},
        "deadlines": {"epinephrine": 10, "iv_access": 15},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T04",
        "category": "timing_only",
        "desc": "Exactly at deadline (not late)",
        "actions": ["blood_culture", "antibiotics"],
        "required": ["blood_culture", "antibiotics"],
        "forbidden": [],
        "timestamps": {"blood_culture": 5, "antibiotics": 60},
        "deadlines": {"antibiotics": 60},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T05",
        "category": "timing_only",
        "desc": "One action barely late (61 > 60)",
        "actions": ["troponin", "ecg", "aspirin"],
        "required": ["troponin", "ecg", "aspirin"],
        "forbidden": [],
        "timestamps": {"troponin": 5, "ecg": 61, "aspirin": 30},
        "deadlines": {"ecg": 60},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    # ===== Category 2: order_only (5) =====
    {
        "id": "T06",
        "category": "order_only",
        "desc": "Insulin before potassium correction",
        "actions": ["insulin", "potassium"],
        "required": ["potassium", "insulin"],
        "forbidden": [],
        "timestamps": {"insulin": 5, "potassium": 10},
        "deadlines": {},
        "before_constraints": [("potassium", "insulin")],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T07",
        "category": "order_only",
        "desc": "Antibiotics before blood culture",
        "actions": ["antibiotics", "blood_culture"],
        "required": ["blood_culture", "antibiotics"],
        "forbidden": [],
        "timestamps": {"antibiotics": 5, "blood_culture": 10},
        "deadlines": {},
        "before_constraints": [("blood_culture", "antibiotics")],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T08",
        "category": "order_only",
        "desc": "Correct order (prereq first)",
        "actions": ["blood_culture", "antibiotics"],
        "required": ["blood_culture", "antibiotics"],
        "forbidden": [],
        "timestamps": {"blood_culture": 5, "antibiotics": 10},
        "deadlines": {},
        "before_constraints": [("blood_culture", "antibiotics")],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T09",
        "category": "order_only",
        "desc": "tPA before NIHSS assessment",
        "actions": ["tpa", "nihss"],
        "required": ["nihss", "tpa"],
        "forbidden": [],
        "timestamps": {"tpa": 5, "nihss": 20},
        "deadlines": {},
        "before_constraints": [("nihss", "tpa")],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T10",
        "category": "order_only",
        "desc": "Action without its prerequisite performed at all",
        "actions": ["insulin"],
        "required": ["potassium", "insulin"],
        "forbidden": [],
        "timestamps": {"insulin": 5},
        "deadlines": {},
        "before_constraints": [("potassium", "insulin")],
        # AC: 1/2=0.5→PASS, MAB: P=1,R=0.5,F1=0.667→PASS, TCC: SEQUENCE→FAIL
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    # ===== Category 3: forbid_only (5) =====
    {
        "id": "T11",
        "category": "forbid_only",
        "desc": "Nitrates given (forbidden in RV infarct)",
        "actions": ["ecg", "troponin", "nitrates"],
        "required": ["ecg", "troponin"],
        "forbidden": ["nitrates"],
        "timestamps": {"ecg": 5, "troponin": 10, "nitrates": 15},
        "deadlines": {},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T12",
        "category": "forbid_only",
        "desc": "Discharge home (forbidden in sepsis)",
        "actions": ["blood_culture", "antibiotics", "discharge_home"],
        "required": ["blood_culture", "antibiotics"],
        "forbidden": ["discharge_home"],
        "timestamps": {"blood_culture": 5, "antibiotics": 10, "discharge_home": 60},
        "deadlines": {},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T13",
        "category": "forbid_only",
        "desc": "No forbidden actions performed",
        "actions": ["ecg", "troponin"],
        "required": ["ecg", "troponin"],
        "forbidden": ["nitrates", "discharge_home"],
        "timestamps": {"ecg": 5, "troponin": 10},
        "deadlines": {},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T14",
        "category": "forbid_only",
        "desc": "Two forbidden actions performed",
        "actions": ["ecg", "nitrates", "morphine"],
        "required": ["ecg"],
        "forbidden": ["nitrates", "morphine"],
        "timestamps": {"ecg": 5, "nitrates": 10, "morphine": 15},
        "deadlines": {},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T15",
        "category": "forbid_only",
        "desc": "Epinephrine IV bolus (forbidden route)",
        "actions": ["assess_abc", "epi_iv_bolus"],
        "required": ["assess_abc", "epi_im"],
        "forbidden": ["epi_iv_bolus"],
        "timestamps": {"assess_abc": 1, "epi_iv_bolus": 5},
        "deadlines": {},
        "before_constraints": [],
        # AC: 1/2=0.5→PASS, MAB: P=0.5,R=0.5,F1=0.5→PASS, TCC: COMMISSION→FAIL
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    # ===== Category 4: omission_only (5) =====
    {
        "id": "T16",
        "category": "omission_only",
        "desc": "Missing 1 of 3 required actions",
        "actions": ["blood_culture", "lactate"],
        "required": ["blood_culture", "antibiotics", "lactate"],
        "forbidden": [],
        "timestamps": {"blood_culture": 5, "lactate": 10},
        "deadlines": {},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T17",
        "category": "omission_only",
        "desc": "Missing 2 of 3 required actions",
        "actions": ["lactate"],
        "required": ["blood_culture", "antibiotics", "lactate"],
        "forbidden": [],
        "timestamps": {"lactate": 10},
        "deadlines": {},
        "before_constraints": [],
        # AC: 1/3=0.333→FAIL, MAB: P=1,R=0.333,F1=0.5→PASS
        "expected": {"ac": "FAIL", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T18",
        "category": "omission_only",
        "desc": "All required missing",
        "actions": ["check_vitals"],
        "required": ["blood_culture", "antibiotics", "lactate"],
        "forbidden": [],
        "timestamps": {"check_vitals": 5},
        "deadlines": {},
        "before_constraints": [],
        "expected": {"ac": "FAIL", "mab": "FAIL", "tcc": "PASS"},
    },
    {
        "id": "T19",
        "category": "omission_only",
        "desc": "Empty action set",
        "actions": [],
        "required": ["blood_culture", "antibiotics"],
        "forbidden": [],
        "timestamps": {},
        "deadlines": {},
        "before_constraints": [],
        "expected": {"ac": "FAIL", "mab": "FAIL", "tcc": "PASS"},
    },
    {
        "id": "T20",
        "category": "omission_only",
        "desc": "Missing 1 of 2 required (50% coverage)",
        "actions": ["ecg"],
        "required": ["ecg", "troponin"],
        "forbidden": [],
        "timestamps": {"ecg": 5},
        "deadlines": {},
        "before_constraints": [],
        # AC: 1/2=0.5→PASS, MAB: P=1,R=0.5,F1=0.667→PASS
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    # ===== Category 5: mixed (5) =====
    {
        "id": "T21",
        "category": "mixed",
        "desc": "Late antibiotics + forbidden discharge",
        "actions": ["blood_culture", "antibiotics", "discharge_home"],
        "required": ["blood_culture", "antibiotics"],
        "forbidden": ["discharge_home"],
        "timestamps": {"blood_culture": 5, "antibiotics": 65, "discharge_home": 70},
        "deadlines": {"antibiotics": 60},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T22",
        "category": "mixed",
        "desc": "Missing action + wrong order + forbidden",
        "actions": ["insulin", "nitrates"],
        "required": ["potassium", "insulin"],
        "forbidden": ["nitrates"],
        "timestamps": {"insulin": 5, "nitrates": 10},
        "deadlines": {},
        "before_constraints": [("potassium", "insulin")],
        # AC: 1/2=0.5→PASS, MAB: P=0.5,R=0.5,F1=0.5→PASS, TCC: COMMISSION+SEQUENCE→FAIL
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T23",
        "category": "mixed",
        "desc": "Late + wrong order",
        "actions": ["antibiotics", "blood_culture"],
        "required": ["blood_culture", "antibiotics"],
        "forbidden": [],
        "timestamps": {"antibiotics": 65, "blood_culture": 70},
        "deadlines": {"antibiotics": 60, "blood_culture": 60},
        "before_constraints": [("blood_culture", "antibiotics")],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T24",
        "category": "mixed",
        "desc": "Omission + timing",
        "actions": ["ecg"],
        "required": ["ecg", "troponin", "aspirin"],
        "forbidden": [],
        "timestamps": {"ecg": 65},
        "deadlines": {"ecg": 60},
        "before_constraints": [],
        # AC: 1/3=0.333→FAIL, MAB: P=1,R=0.333,F1=0.5→PASS, TCC: TIMING→FAIL
        "expected": {"ac": "FAIL", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T25",
        "category": "mixed",
        "desc": "All violation types simultaneously",
        "actions": ["insulin", "nitrates"],
        "required": ["potassium", "insulin", "ecg"],
        "forbidden": ["nitrates"],
        "timestamps": {"insulin": 65, "nitrates": 10},
        "deadlines": {"insulin": 60},
        "before_constraints": [("potassium", "insulin")],
        "expected": {"ac": "FAIL", "mab": "FAIL", "tcc": "FAIL"},
    },
    # ===== Category 6: clean (5) =====
    {
        "id": "T26",
        "category": "clean",
        "desc": "Perfect sepsis bundle",
        "actions": ["blood_culture", "antibiotics", "lactate", "fluids"],
        "required": ["blood_culture", "antibiotics", "lactate"],
        "forbidden": ["discharge_home"],
        "timestamps": {"blood_culture": 5, "antibiotics": 15, "lactate": 10, "fluids": 20},
        "deadlines": {"antibiotics": 60, "lactate": 60},
        "before_constraints": [("blood_culture", "antibiotics")],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T27",
        "category": "clean",
        "desc": "Perfect anaphylaxis management",
        "actions": ["assess_abc", "epi_im", "iv_access"],
        "required": ["assess_abc", "epi_im", "iv_access"],
        "forbidden": ["epi_iv_bolus"],
        "timestamps": {"assess_abc": 1, "epi_im": 3, "iv_access": 5},
        "deadlines": {"epi_im": 10},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T28",
        "category": "clean",
        "desc": "Single required action done on time",
        "actions": ["aspirin"],
        "required": ["aspirin"],
        "forbidden": [],
        "timestamps": {"aspirin": 5},
        "deadlines": {"aspirin": 30},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T29",
        "category": "clean",
        "desc": "Extra actions beyond required (all clean)",
        "actions": ["blood_culture", "antibiotics", "lactate", "cbc", "bmp", "xray"],
        "required": ["blood_culture", "antibiotics", "lactate"],
        "forbidden": [],
        "timestamps": {"blood_culture": 5, "antibiotics": 15, "lactate": 10, "cbc": 8, "bmp": 8, "xray": 12},
        "deadlines": {"antibiotics": 60},
        "before_constraints": [("blood_culture", "antibiotics")],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T30",
        "category": "clean",
        "desc": "No required actions (empty requirements)",
        "actions": ["check_vitals"],
        "required": [],
        "forbidden": [],
        "timestamps": {"check_vitals": 5},
        "deadlines": {},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    # ===== Category 7: partial (5) =====
    {
        "id": "T31",
        "category": "partial",
        "desc": "3 of 5 required (60% coverage)",
        "actions": ["a1", "a2", "a3"],
        "required": ["a1", "a2", "a3", "a4", "a5"],
        "forbidden": [],
        "timestamps": {"a1": 5, "a2": 10, "a3": 15},
        "deadlines": {},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T32",
        "category": "partial",
        "desc": "2 of 5 required (40% coverage)",
        "actions": ["a1", "a2"],
        "required": ["a1", "a2", "a3", "a4", "a5"],
        "forbidden": [],
        "timestamps": {"a1": 5, "a2": 10},
        "deadlines": {},
        "before_constraints": [],
        # AC: 2/5=0.4→FAIL, MAB: P=1,R=0.4,F1=0.571→PASS
        "expected": {"ac": "FAIL", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T33",
        "category": "partial",
        "desc": "4 of 5 required + extra actions (80% cov, lower precision)",
        "actions": ["a1", "a2", "a3", "a4", "x1", "x2", "x3"],
        "required": ["a1", "a2", "a3", "a4", "a5"],
        "forbidden": [],
        "timestamps": {"a1": 5, "a2": 10, "a3": 15, "a4": 20, "x1": 25, "x2": 30, "x3": 35},
        "deadlines": {},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T34",
        "category": "partial",
        "desc": "1 of 4 required (25% coverage)",
        "actions": ["a1", "x1"],
        "required": ["a1", "a2", "a3", "a4"],
        "forbidden": [],
        "timestamps": {"a1": 5, "x1": 10},
        "deadlines": {},
        "before_constraints": [],
        "expected": {"ac": "FAIL", "mab": "FAIL", "tcc": "PASS"},
    },
    {
        "id": "T35",
        "category": "partial",
        "desc": "All required + partial timing violation",
        "actions": ["a1", "a2", "a3"],
        "required": ["a1", "a2", "a3"],
        "forbidden": [],
        "timestamps": {"a1": 5, "a2": 10, "a3": 65},
        "deadlines": {"a3": 60},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    # ===== Category 8: boundary (5) =====
    {
        "id": "T36",
        "category": "boundary",
        "desc": "50% coverage but F1<0.5 due to spurious actions",
        "actions": ["a1", "a2", "x1", "x2", "x3"],
        "required": ["a1", "a2", "a3", "a4"],
        "forbidden": [],
        "timestamps": {"a1": 5, "a2": 10, "x1": 15, "x2": 20, "x3": 25},
        "deadlines": {},
        "before_constraints": [],
        # AC: 2/4=0.5→PASS, MAB: P=2/5=0.4,R=2/4=0.5,F1=0.444→FAIL
        "expected": {"ac": "PASS", "mab": "FAIL", "tcc": "PASS"},
    },
    {
        "id": "T37",
        "category": "boundary",
        "desc": "Just below 50% coverage (1/3), MAB passes at F1=0.5",
        "actions": ["a1"],
        "required": ["a1", "a2", "a3"],
        "forbidden": [],
        "timestamps": {"a1": 5},
        "deadlines": {},
        "before_constraints": [],
        # AC: 1/3=0.333→FAIL, MAB: P=1,R=0.333,F1=0.5→PASS (precision=1 inflates F1)
        "expected": {"ac": "FAIL", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T38",
        "category": "boundary",
        "desc": "Exactly at deadline (not violation)",
        "actions": ["a1"],
        "required": ["a1"],
        "forbidden": [],
        "timestamps": {"a1": 60},
        "deadlines": {"a1": 60},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
    {
        "id": "T39",
        "category": "boundary",
        "desc": "1ms over deadline",
        "actions": ["a1"],
        "required": ["a1"],
        "forbidden": [],
        "timestamps": {"a1": 60.01},
        "deadlines": {"a1": 60},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "FAIL"},
    },
    {
        "id": "T40",
        "category": "boundary",
        "desc": "F1 exactly 0.5 (1 TP, 1 FP, 1 FN => P=0.5,R=0.5,F1=0.5)",
        "actions": ["a1", "x1"],
        "required": ["a1", "a2"],
        "forbidden": [],
        "timestamps": {"a1": 5, "x1": 10},
        "deadlines": {},
        "before_constraints": [],
        "expected": {"ac": "PASS", "mab": "PASS", "tcc": "PASS"},
    },
]


# ---------------------------------------------------------------------------
# Cohen's kappa
# ---------------------------------------------------------------------------


def cohens_kappa(y_true: list[str], y_pred: list[str]) -> float:
    """Compute Cohen's kappa for two raters."""
    n = len(y_true)
    if n == 0:
        return 0.0
    labels = sorted(set(y_true) | set(y_pred))
    # Confusion matrix
    matrix: dict[tuple[str, str], int] = Counter()
    for t, p in zip(y_true, y_pred):
        matrix[(t, p)] += 1
    # Observed agreement
    po = sum(matrix[(l, l)] for l in labels) / n
    # Expected agreement
    pe = 0.0
    for l in labels:
        row_sum = sum(matrix[(l, l2)] for l2 in labels) / n
        col_sum = sum(matrix[(l2, l)] for l2 in labels) / n
        pe += row_sum * col_sum
    if pe >= 1.0:
        return 1.0
    return round((po - pe) / (1.0 - pe), 4)


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def run_audit() -> dict:
    """Run all scorers against all traces and compute agreement."""
    n_traces = len(TRACES)
    n_categories = len({t["category"] for t in TRACES})

    results_per_trace: list[dict] = []
    per_scorer: dict[str, dict] = {}

    for scorer_name, scorer_fn in SCORERS.items():
        expected_verdicts: list[str] = []
        actual_verdicts: list[str] = []
        exact_matches = 0
        mismatches: list[dict] = []

        for trace in TRACES:
            actual = scorer_fn(trace)
            expected_verdict = trace["expected"][scorer_name]
            actual_verdict = actual["verdict"]

            expected_verdicts.append(expected_verdict)
            actual_verdicts.append(actual_verdict)

            is_match = actual_verdict == expected_verdict
            if is_match:
                exact_matches += 1
            else:
                mismatches.append(
                    {
                        "trace_id": trace["id"],
                        "category": trace["category"],
                        "desc": trace["desc"],
                        "expected": expected_verdict,
                        "actual": actual_verdict,
                        "score": actual.get("score"),
                        "violations": actual.get("violations", []),
                    }
                )

            results_per_trace.append(
                {
                    "trace_id": trace["id"],
                    "category": trace["category"],
                    "scorer": scorer_name,
                    "expected": expected_verdict,
                    "actual": actual_verdict,
                    "match": is_match,
                }
            )

        kappa = cohens_kappa(expected_verdicts, actual_verdicts)
        per_scorer[scorer_name] = {
            "exact_matches": exact_matches,
            "total": n_traces,
            "exact_rate": round(exact_matches / max(n_traces, 1) * 100, 1),
            "kappa": kappa,
            "mismatches": mismatches,
        }

    # Per-category breakdown
    per_category: dict[str, dict] = {}
    for cat in sorted({t["category"] for t in TRACES}):
        cat_traces = [r for r in results_per_trace if r["category"] == cat]
        cat_matches = sum(1 for r in cat_traces if r["match"])
        per_category[cat] = {
            "total_checks": len(cat_traces),
            "matches": cat_matches,
            "rate": round(cat_matches / max(len(cat_traces), 1) * 100, 1),
        }

    return {
        "n_traces": n_traces,
        "n_categories": n_categories,
        "n_scorers": len(SCORERS),
        "total_checks": n_traces * len(SCORERS),
        "per_scorer": per_scorer,
        "per_category": per_category,
        "per_trace": results_per_trace,
    }


def generate_markdown(results: dict) -> str:
    lines = [
        "# EX-26: Native Scorer Fidelity Audit",
        "",
        f"**Traces:** {results['n_traces']}",
        f"**Categories:** {results['n_categories']}",
        f"**Scorers:** {results['n_scorers']}",
        f"**Total checks:** {results['total_checks']}",
        "",
        "## Per-Scorer Agreement",
        "",
        "| Scorer | Exact Match | Rate | Cohen's kappa |",
        "|--------|-------------|------|---------------|",
    ]
    for name, ps in results["per_scorer"].items():
        lines.append(f"| {name.upper()} | {ps['exact_matches']}/{ps['total']} | {ps['exact_rate']}% | {ps['kappa']} |")

    lines.extend(
        [
            "",
            "## Per-Category Agreement",
            "",
            "| Category | Checks | Matches | Rate |",
            "|----------|--------|---------|------|",
        ]
    )
    for cat, pc in sorted(results["per_category"].items()):
        lines.append(f"| {cat} | {pc['total_checks']} | {pc['matches']} | {pc['rate']}% |")

    # Mismatches
    any_mismatch = False
    for name, ps in results["per_scorer"].items():
        if ps["mismatches"]:
            if not any_mismatch:
                lines.extend(["", "## Mismatches", ""])
                any_mismatch = True
            lines.append(f"### {name.upper()}")
            for mm in ps["mismatches"]:
                lines.append(
                    f"- **{mm['trace_id']}** ({mm['category']}): "
                    f"expected={mm['expected']}, actual={mm['actual']}, "
                    f"score={mm.get('score')}"
                )
            lines.append("")

    if not any_mismatch:
        lines.extend(["", "## All checks passed — no mismatches."])

    return "\n".join(lines)


def generate_macros(results: dict) -> str:
    ps = results["per_scorer"]
    ac = ps.get("ac", {})
    mab = ps.get("mab", {})
    tcc = ps.get("tcc", {})
    lines = [
        "",
        "% ---------------------------------------------------------------------------",
        "% EX-26: Native Scorer Fidelity Audit",
        "% ---------------------------------------------------------------------------",
        f"\\newcommand{{\\fidelityNTraces}}{{{results['n_traces']}}}",
        f"\\newcommand{{\\fidelityNCategories}}{{{results['n_categories']}}}",
        f"\\newcommand{{\\fidelityACExactAgree}}{{{ac.get('exact_rate', 0)}}}",
        f"\\newcommand{{\\fidelityACKappa}}{{{ac.get('kappa', 0)}}}",
        f"\\newcommand{{\\fidelityMABExactAgree}}{{{mab.get('exact_rate', 0)}}}",
        f"\\newcommand{{\\fidelityMABKappa}}{{{mab.get('kappa', 0)}}}",
        f"\\newcommand{{\\fidelityTCCExactAgree}}{{{tcc.get('exact_rate', 0)}}}",
        f"\\newcommand{{\\fidelityTCCKappa}}{{{tcc.get('kappa', 0)}}}",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 70)
    print("EX-26: NATIVE SCORER FIDELITY AUDIT")
    print("=" * 70)

    results = run_audit()

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(results, OUTPUT_DIR / "scorer_fidelity.json")

    md = generate_markdown(results)
    save_markdown(md, OUTPUT_DIR / "scorer_fidelity.md")

    macros = generate_macros(results)
    macros_path = OUTPUT_DIR / "macros.tex"
    macros_path.write_text(macros)
    print(f"  Saved: {macros_path}")

    # Summary
    print(f"\n  Traces: {results['n_traces']} across {results['n_categories']} categories")
    print(f"  Total checks: {results['total_checks']}")
    print()
    for name, ps in results["per_scorer"].items():
        status = "PERFECT" if ps["exact_matches"] == ps["total"] else "MISMATCH"
        print(
            f"  {name.upper():5s}: {ps['exact_matches']}/{ps['total']} "
            f"({ps['exact_rate']}%) kappa={ps['kappa']} [{status}]"
        )
        for mm in ps["mismatches"]:
            print(f"    ! {mm['trace_id']} ({mm['category']}): expected={mm['expected']} actual={mm['actual']}")

    print("=" * 70)


if __name__ == "__main__":
    main()
