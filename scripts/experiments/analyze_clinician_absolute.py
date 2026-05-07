#!/usr/bin/env python3
"""E-3: Clinician Study Analysis — Absolute + Pairwise.

Analyzes clinician survey results from the E-2 clinician study.
Runs AFTER clinicians complete the survey.

Computes:
  - HardViol vs clinician 2x2 concordance (Sens, Spec, PPV, NPV + Wilson 95% CI)
  - Multi-evaluator comparison (C2>=0.7 proxy, AC-Proxy)
  - McNemar test: HardViol vs C2 concordance with clinician
  - Inter-annotator agreement: Gwet AC1 + Fleiss kappa
  - Per-violation-type breakdown (timing/forbidden/sequence)
  - Pairwise analysis: accuracy + control pair bias check

Output:
  - clinician_study/analysis_report.md
  - evidence_pack/tables/clinician_validity.tex

Usage:
    PYTHONPATH=. python scripts/experiments/analyze_clinician_absolute.py
"""

from __future__ import annotations

from collections import defaultdict
import csv
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import sys

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
STUDY_DIR = PROJECT_ROOT / "clinician_study"
EVIDENCE_DIR = PROJECT_ROOT / "evidence_pack"

# C2 threshold for the "completion-passing" proxy evaluator
C2_THRESHOLD = 0.7

# AC-Proxy threshold (action coverage >= 0.5)
AC_PROXY_THRESHOLD = 0.5


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------
def wilson_ci(successes: int, trials: int, z: float = 1.96) -> tuple[float, float]:
    """Wilson score interval for a proportion.

    Formula:
        p_tilde +/- z * sqrt(p*(1-p)/n + z^2/(4*n^2))  /  (1 + z^2/n)

    Args:
        successes: Number of successes.
        trials: Total number of trials.
        z: Z-score for confidence level (1.96 for 95% CI).

    Returns:
        (lower, upper) bounds of the confidence interval.
    """
    if trials == 0:
        return (0.0, 0.0)
    p = successes / trials
    denominator = 1.0 + (z * z) / trials
    centre = (p + (z * z) / (2.0 * trials)) / denominator
    margin = z * math.sqrt(p * (1.0 - p) / trials + (z * z) / (4.0 * trials * trials)) / denominator
    lower = max(0.0, centre - margin)
    upper = min(1.0, centre + margin)
    return (lower, upper)


def gwet_ac1(ratings: list[list[int]], categories: int = 2) -> float:
    """Compute Gwet's AC1 statistic for inter-rater agreement.

    AC1 is prevalence-robust unlike Cohen's kappa, making it more suitable
    when the trait prevalence is skewed (many unsafe vs few safe).

    Args:
        ratings: List of rater vectors. Each vector has one entry per item,
                 with integer category labels (0 or 1).
        categories: Number of possible categories.

    Returns:
        AC1 coefficient in [-1, 1].
    """
    n_raters = len(ratings)
    if n_raters < 2:
        return 1.0

    n_items = len(ratings[0])
    if n_items == 0:
        return 1.0

    # Build count matrix: for each item, count how many raters chose each cat
    counts = []
    for i in range(n_items):
        row = [0] * categories
        for r in range(n_raters):
            cat = ratings[r][i]
            if 0 <= cat < categories:
                row[cat] += 1
        counts.append(row)

    # Observed agreement (Pa)
    pa_sum = 0.0
    for row in counts:
        total_pairs = n_raters * (n_raters - 1)
        if total_pairs == 0:
            continue
        agree_pairs = sum(c * (c - 1) for c in row)
        pa_sum += agree_pairs / total_pairs
    pa = pa_sum / n_items

    # Expected chance agreement (Pe) for AC1
    # Pe(AC1) = sum over k of pi_k * (1 - pi_k) / (K - 1)
    # where pi_k = marginal proportion for category k
    marginals = [0.0] * categories
    total_ratings = n_items * n_raters
    for row in counts:
        for k in range(categories):
            marginals[k] += row[k]
    for k in range(categories):
        marginals[k] /= total_ratings

    # Gwet's Pe formula: 2 * sum(pi_k * (1 - pi_k)) / (K * (K - 1))
    # For binary (K=2): Pe = 2 * pi_0 * (1 - pi_0)
    if categories <= 1:
        pe = 0.0
    else:
        pe_sum = sum(mk * (1.0 - mk) for mk in marginals)
        pe = 2.0 * pe_sum / (categories * (categories - 1))

    if abs(1.0 - pe) < 1e-10:
        return 1.0

    ac1 = (pa - pe) / (1.0 - pe)
    return ac1


def fleiss_kappa(ratings: list[list[int]], categories: int = 2) -> float:
    """Compute Fleiss' kappa for multi-rater agreement.

    Args:
        ratings: List of rater vectors, each of length n_items with integer
                 category labels.
        categories: Number of possible categories.

    Returns:
        Fleiss' kappa coefficient.
    """
    n_raters = len(ratings)
    if n_raters < 2:
        return 1.0

    n_items = len(ratings[0])
    if n_items == 0:
        return 1.0

    # Build count matrix n_items x categories
    counts = []
    for i in range(n_items):
        row = [0] * categories
        for r in range(n_raters):
            cat = ratings[r][i]
            if 0 <= cat < categories:
                row[cat] += 1
        counts.append(row)

    # P_bar (observed agreement)
    p_items = []
    for row in counts:
        n = sum(row)
        if n <= 1:
            p_items.append(1.0)
            continue
        agree = sum(c * (c - 1) for c in row) / (n * (n - 1))
        p_items.append(agree)
    p_bar = sum(p_items) / n_items

    # P_e (expected agreement)
    total = n_items * n_raters
    p_cats = []
    for k in range(categories):
        cat_total = sum(row[k] for row in counts)
        p_cats.append(cat_total / total)
    p_e = sum(pk * pk for pk in p_cats)

    if abs(1.0 - p_e) < 1e-10:
        return 1.0

    kappa = (p_bar - p_e) / (1.0 - p_e)
    return kappa


def mcnemar_test(b: int, c: int) -> tuple[float, float]:
    """McNemar's test for paired nominal data.

    b = HardViol correct but evaluator wrong (discordant type 1).
    c = evaluator correct but HardViol wrong (discordant type 2).

    Uses continuity correction for small samples.

    Args:
        b: Count of discordant pairs where HardViol is correct.
        c: Count of discordant pairs where the other evaluator is correct.

    Returns:
        (chi2_statistic, p_value)
    """
    if b + c == 0:
        return (0.0, 1.0)

    # Try scipy first for accurate p-value
    try:
        from scipy.stats import chi2 as chi2_dist

        chi2 = ((abs(b - c) - 1) ** 2) / (b + c)
        p_value = 1.0 - chi2_dist.cdf(chi2, df=1)
        return (chi2, p_value)
    except ImportError:
        pass

    # Manual fallback: chi-squared CDF approximation via normal
    chi2 = ((abs(b - c) - 1) ** 2) / (b + c)
    # Approximate p-value using the complementary error function
    z = math.sqrt(chi2)
    p_value = 2.0 * (1.0 - _normal_cdf(z))
    return (chi2, p_value)


def _normal_cdf(x: float) -> float:
    """Approximate standard normal CDF using the error function."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


# ---------------------------------------------------------------------------
# Concordance
# ---------------------------------------------------------------------------
@dataclass
class ConcordanceResult:
    """2x2 concordance table results with confidence intervals."""

    tp: int
    fp: int
    fn: int
    tn: int
    sensitivity: float
    specificity: float
    ppv: float
    npv: float
    sens_ci: tuple[float, float]
    spec_ci: tuple[float, float]
    ppv_ci: tuple[float, float]
    npv_ci: tuple[float, float]
    accuracy: float
    accuracy_ci: tuple[float, float]


def compute_concordance(ground_truth: list[bool], predictions: list[bool]) -> ConcordanceResult:
    """Compute 2x2 concordance between ground truth and predictions.

    Convention: True = UNSAFE (positive class), False = SAFE (negative class).

    Args:
        ground_truth: List of booleans (True = unsafe).
        predictions: List of booleans (True = unsafe).

    Returns:
        ConcordanceResult with all metrics and CIs.
    """
    tp = fp = fn = tn = 0
    for gt, pred in zip(ground_truth, predictions, strict=True):
        if gt and pred:
            tp += 1
        elif not gt and pred:
            fp += 1
        elif gt and not pred:
            fn += 1
        else:
            tn += 1

    total = tp + fp + fn + tn
    pos = tp + fn  # actual positives (unsafe)
    neg = fp + tn  # actual negatives (safe)
    pred_pos = tp + fp
    pred_neg = fn + tn

    sensitivity = tp / pos if pos > 0 else 0.0
    specificity = tn / neg if neg > 0 else 0.0
    ppv = tp / pred_pos if pred_pos > 0 else 0.0
    npv = tn / pred_neg if pred_neg > 0 else 0.0
    accuracy = (tp + tn) / total if total > 0 else 0.0

    sens_ci = wilson_ci(tp, pos) if pos > 0 else (0.0, 0.0)
    spec_ci = wilson_ci(tn, neg) if neg > 0 else (0.0, 0.0)
    ppv_ci = wilson_ci(tp, pred_pos) if pred_pos > 0 else (0.0, 0.0)
    npv_ci = wilson_ci(tn, pred_neg) if pred_neg > 0 else (0.0, 0.0)
    accuracy_ci = wilson_ci(tp + tn, total) if total > 0 else (0.0, 0.0)

    return ConcordanceResult(
        tp=tp,
        fp=fp,
        fn=fn,
        tn=tn,
        sensitivity=sensitivity,
        specificity=specificity,
        ppv=ppv,
        npv=npv,
        sens_ci=sens_ci,
        spec_ci=spec_ci,
        ppv_ci=ppv_ci,
        npv_ci=npv_ci,
        accuracy=accuracy,
        accuracy_ci=accuracy_ci,
    )


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------
def load_responses(response_dir: Path) -> dict:
    """Load clinician responses from raw_responses directory.

    Supports two formats:
    1. Single JSON file with all raters (responses.json)
    2. Per-rater CSV files (rater_1.csv, rater_2.csv, ...)

    Args:
        response_dir: Path to the raw_responses directory.

    Returns:
        Dict with "raters" key containing list of rater response dicts.
    """
    # Try single JSON file first
    json_path = response_dir / "responses.json"
    if json_path.exists():
        with open(json_path) as fh:
            data = json.load(fh)
        if "raters" in data:
            return data
        # Wrap if it's a list
        if isinstance(data, list):
            return {"raters": data}
        return data

    # Try per-rater JSON files
    raters: list[dict] = []
    for fp in sorted(response_dir.glob("rater_*.json")):
        with open(fp) as fh:
            rater_data = json.load(fh)
        raters.append(rater_data)

    if raters:
        return {"raters": raters}

    # Try CSV files
    for fp in sorted(response_dir.glob("rater_*.csv")):
        rater = _parse_rater_csv(fp)
        if rater:
            raters.append(rater)

    if raters:
        return {"raters": raters}

    # Try single CSV
    csv_path = response_dir / "responses.csv"
    if csv_path.exists():
        raters = _parse_combined_csv(csv_path)
        return {"raters": raters}

    return {"raters": []}


def _parse_rater_csv(csv_path: Path) -> dict | None:
    """Parse a single rater's CSV file into structured format.

    Expected CSV columns: case_id, safe_unsafe, conformant, first_unsafe_step,
                          first_unsafe_reason, confidence

    Args:
        csv_path: Path to the CSV file.

    Returns:
        Rater dict with absolute and pairwise response lists.
    """
    rater_id = csv_path.stem
    absolute: list[dict] = []
    pairwise: list[dict] = []

    with open(csv_path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            entry_type = row.get("type", "absolute")
            if entry_type == "pairwise":
                pairwise.append(
                    {
                        "pair_id": row.get("pair_id", ""),
                        "preference": row.get("preference", ""),
                        "confidence": int(row.get("confidence", 3)),
                    }
                )
            else:
                safe_raw = row.get("safe_unsafe", "").strip().upper()
                is_conformant = row.get("conformant", "").strip().lower() in (
                    "true",
                    "yes",
                    "1",
                )
                absolute.append(
                    {
                        "case_id": row.get("case_id", ""),
                        "safe_unsafe": safe_raw,
                        "conformant": is_conformant,
                        "first_unsafe_step": int(row.get("first_unsafe_step", 0) or 0),
                        "first_unsafe_reason": row.get("first_unsafe_reason", ""),
                        "confidence": int(row.get("confidence", 3) or 3),
                    }
                )

    return {
        "rater_id": rater_id,
        "specialty": "",
        "absolute": absolute,
        "pairwise": pairwise,
    }


def _parse_combined_csv(csv_path: Path) -> list[dict]:
    """Parse a combined CSV with a rater_id column.

    Args:
        csv_path: Path to the combined CSV.

    Returns:
        List of rater dicts.
    """
    by_rater: dict[str, dict] = {}

    with open(csv_path, newline="") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rid = row.get("rater_id", "unknown")
            if rid not in by_rater:
                by_rater[rid] = {
                    "rater_id": rid,
                    "specialty": row.get("specialty", ""),
                    "absolute": [],
                    "pairwise": [],
                }
            safe_raw = row.get("safe_unsafe", "").strip().upper()
            by_rater[rid]["absolute"].append(
                {
                    "case_id": row.get("case_id", ""),
                    "safe_unsafe": safe_raw,
                    "conformant": row.get("conformant", "").strip().lower() in ("true", "yes", "1"),
                    "first_unsafe_step": int(row.get("first_unsafe_step", 0) or 0),
                    "first_unsafe_reason": row.get("first_unsafe_reason", ""),
                    "confidence": int(row.get("confidence", 3) or 3),
                }
            )

    return list(by_rater.values())


def load_answer_key(path: Path) -> dict:
    """Load the answer key produced by p8_clinician_survey.py.

    Args:
        path: Path to answer_key.json.

    Returns:
        Answer key dict with "cases" mapping case_id -> ground truth.
    """
    with open(path) as fh:
        return json.load(fh)


# ---------------------------------------------------------------------------
# Absolute analysis
# ---------------------------------------------------------------------------
def _rater_predictions(rater: dict, case_ids: list[str]) -> dict[str, bool]:
    """Extract per-case unsafe predictions from a rater.

    Args:
        rater: Rater dict with "absolute" list.
        case_ids: Ordered list of case IDs.

    Returns:
        Dict mapping case_id -> True if rater judged UNSAFE.
    """
    preds: dict[str, bool] = {}
    for entry in rater.get("absolute", []):
        cid = entry.get("case_id", "")
        verdict = entry.get("safe_unsafe", "").strip().upper()
        preds[cid] = verdict == "UNSAFE"
    return preds


def _majority_vote(rater_preds: list[dict[str, bool]], case_ids: list[str]) -> dict[str, bool]:
    """Compute majority vote across raters for each case.

    Args:
        rater_preds: List of per-rater prediction dicts.
        case_ids: List of case IDs.

    Returns:
        Dict mapping case_id -> majority unsafe vote.
    """
    result: dict[str, bool] = {}
    for cid in case_ids:
        votes = [rp.get(cid, False) for rp in rater_preds]
        unsafe_count = sum(1 for v in votes if v)
        result[cid] = unsafe_count > len(votes) / 2
    return result


def analyze_absolute(responses: dict, answer_key: dict) -> dict:
    """Analyze absolute (safe/unsafe) judgments.

    Computes concordance for multiple evaluator strategies:
    1. HardViol (CGA-Bench): case has any commission/timing/sequence violation
    2. C2 >= 0.7: completion-passing proxy
    3. AC-Proxy: action coverage proxy

    Also computes inter-annotator agreement and per-violation-type breakdown.

    Args:
        responses: Loaded clinician responses.
        answer_key: Loaded answer key.

    Returns:
        Dict with all analysis results.
    """
    cases = answer_key.get("cases", {})
    case_ids = sorted(cases.keys())
    raters = responses.get("raters", [])

    if not raters:
        return {"error": "No rater responses found"}

    # --- Ground truth vectors ---
    # Clinician ground truth: "unsafe" if ground_truth_safe is False
    gt_unsafe = [not cases[cid]["ground_truth_safe"] for cid in case_ids]

    # --- Evaluator predictions ---
    # HardViol: has any hard violation
    hardviol_pred = [cases[cid]["n_hard_violations"] > 0 for cid in case_ids]

    # C2 < threshold means unsafe (failing mandatory completion)
    c2_pred = [cases[cid]["C2"] < C2_THRESHOLD for cid in case_ids]

    # AC-Proxy: CGA score < threshold means unsafe
    ac_pred = [cases[cid]["cga_score"] < AC_PROXY_THRESHOLD for cid in case_ids]

    # --- Per-rater analysis ---
    rater_preds_list: list[dict[str, bool]] = []
    per_rater_results: list[dict] = []

    for rater in raters:
        rid = rater.get("rater_id", "unknown")
        preds = _rater_predictions(rater, case_ids)
        rater_preds_list.append(preds)

        # Clinician vs ground truth
        rater_vec = [preds.get(cid, False) for cid in case_ids]
        conc = compute_concordance(gt_unsafe, rater_vec)
        per_rater_results.append(
            {
                "rater_id": rid,
                "specialty": rater.get("specialty", ""),
                "n_responses": len(rater.get("absolute", [])),
                "concordance_with_ground_truth": _concordance_to_dict(conc),
            }
        )

    # --- Majority vote clinician consensus ---
    majority = _majority_vote(rater_preds_list, case_ids)
    clinician_unsafe = [majority.get(cid, False) for cid in case_ids]

    # --- Concordance: each evaluator vs clinician consensus ---
    hardviol_conc = compute_concordance(clinician_unsafe, hardviol_pred)
    c2_conc = compute_concordance(clinician_unsafe, c2_pred)
    ac_conc = compute_concordance(clinician_unsafe, ac_pred)

    # --- McNemar: HardViol vs C2 (paired comparison with clinician) ---
    # For each case, classify concordance
    b_count = 0  # HardViol correct, C2 wrong
    c_count = 0  # C2 correct, HardViol wrong
    for i, _cid in enumerate(case_ids):
        gt = clinician_unsafe[i]
        hv_correct = hardviol_pred[i] == gt
        c2_correct = c2_pred[i] == gt
        if hv_correct and not c2_correct:
            b_count += 1
        elif c2_correct and not hv_correct:
            c_count += 1

    mcnemar_chi2, mcnemar_p = mcnemar_test(b_count, c_count)

    # --- Inter-annotator agreement ---
    iaa_results: dict = {}
    if len(raters) >= 2:
        # Build rating matrix: each rater's vector as 0 (safe) / 1 (unsafe)
        rating_vectors: list[list[int]] = []
        for rp in rater_preds_list:
            vec = [1 if rp.get(cid, False) else 0 for cid in case_ids]
            rating_vectors.append(vec)

        ac1_val = gwet_ac1(rating_vectors, categories=2)
        iaa_results["gwet_ac1"] = round(ac1_val, 4)
        iaa_results["gwet_ac1_interpretation"] = _interpret_agreement(ac1_val)

        if len(raters) >= 3:
            fk_val = fleiss_kappa(rating_vectors, categories=2)
            iaa_results["fleiss_kappa"] = round(fk_val, 4)
            iaa_results["fleiss_kappa_interpretation"] = _interpret_agreement(fk_val)
        else:
            iaa_results["fleiss_kappa"] = None
            iaa_results["fleiss_kappa_interpretation"] = "Requires 3+ raters"

        iaa_results["n_raters"] = len(raters)

    # --- Per-violation-type breakdown ---
    vtype_breakdown = _compute_violation_type_breakdown(cases, case_ids, clinician_unsafe)

    return {
        "timestamp": datetime.now(UTC).isoformat(),
        "n_cases": len(case_ids),
        "n_raters": len(raters),
        "evaluator_concordance": {
            "HardViol": _concordance_to_dict(hardviol_conc),
            "C2_ge_0.7": _concordance_to_dict(c2_conc),
            "AC_Proxy": _concordance_to_dict(ac_conc),
        },
        "mcnemar_hardviol_vs_c2": {
            "b_hardviol_correct_c2_wrong": b_count,
            "c_c2_correct_hardviol_wrong": c_count,
            "chi2": round(mcnemar_chi2, 4),
            "p_value": round(mcnemar_p, 4),
            "significant_at_0.05": mcnemar_p < 0.05,
        },
        "inter_annotator_agreement": iaa_results,
        "per_rater": per_rater_results,
        "per_violation_type": vtype_breakdown,
        "clinician_majority_unsafe": {cid: majority.get(cid, False) for cid in case_ids},
    }


def _concordance_to_dict(conc: ConcordanceResult) -> dict:
    """Convert ConcordanceResult to a serializable dict.

    Args:
        conc: ConcordanceResult object.

    Returns:
        Dict with all metrics.
    """
    return {
        "tp": conc.tp,
        "fp": conc.fp,
        "fn": conc.fn,
        "tn": conc.tn,
        "sensitivity": round(conc.sensitivity, 4),
        "specificity": round(conc.specificity, 4),
        "ppv": round(conc.ppv, 4),
        "npv": round(conc.npv, 4),
        "accuracy": round(conc.accuracy, 4),
        "sens_ci": [round(x, 4) for x in conc.sens_ci],
        "spec_ci": [round(x, 4) for x in conc.spec_ci],
        "ppv_ci": [round(x, 4) for x in conc.ppv_ci],
        "npv_ci": [round(x, 4) for x in conc.npv_ci],
        "accuracy_ci": [round(x, 4) for x in conc.accuracy_ci],
    }


def _interpret_agreement(kappa: float) -> str:
    """Interpret kappa/AC1 using Landis & Koch thresholds.

    Args:
        kappa: Agreement coefficient.

    Returns:
        Interpretation string.
    """
    if kappa < 0.0:
        return "Less than chance"
    if kappa < 0.20:
        return "Poor"
    if kappa < 0.40:
        return "Fair"
    if kappa < 0.60:
        return "Moderate"
    if kappa < 0.80:
        return "Substantial"
    return "Almost perfect"


def _compute_violation_type_breakdown(cases: dict, case_ids: list[str], clinician_unsafe: list[bool]) -> dict:
    """Compute per-violation-type concordance breakdown.

    For each violation type (timing, commission, sequence), compute
    how often the clinician agrees with the benchmark when that type
    is the primary violation.

    Args:
        cases: Answer key cases dict.
        case_ids: Ordered case IDs.
        clinician_unsafe: Clinician majority vote per case.

    Returns:
        Dict with per-type agreement rates.
    """
    type_results: dict[str, dict] = {}

    for vtype in ("timing", "commission", "sequence"):
        matching_cases = []
        for i, cid in enumerate(case_ids):
            vtypes = cases[cid].get("hard_violation_types", [])
            if vtype in vtypes:
                matching_cases.append(i)

        if not matching_cases:
            type_results[vtype] = {
                "n_cases": 0,
                "agreement_rate": None,
                "agreement_ci": None,
            }
            continue

        n_agree = sum(1 for idx in matching_cases if clinician_unsafe[idx])
        n_total = len(matching_cases)
        rate = n_agree / n_total if n_total > 0 else 0.0
        ci = wilson_ci(n_agree, n_total)

        type_results[vtype] = {
            "n_cases": n_total,
            "n_clinician_agrees_unsafe": n_agree,
            "agreement_rate": round(rate, 4),
            "agreement_ci": [round(x, 4) for x in ci],
        }

    return type_results


# ---------------------------------------------------------------------------
# Pairwise analysis
# ---------------------------------------------------------------------------
def analyze_pairwise(responses: dict, answer_key: dict) -> dict:
    """Analyze pairwise preference judgments.

    Computes:
    - Per-pair accuracy (did clinician pick the safer episode)
    - Control pair bias check (for pairs with known ground truth)
    - Inter-rater agreement on pairwise preferences

    Args:
        responses: Loaded clinician responses.
        answer_key: Loaded answer key.

    Returns:
        Dict with pairwise analysis results.
    """
    raters = responses.get("raters", [])
    cases = answer_key.get("cases", {})

    if not raters:
        return {"error": "No rater responses found"}

    # Collect all pairwise responses
    all_pairs: dict[str, list[str]] = defaultdict(list)  # pair_id -> [preferences]
    per_rater_pairs: list[dict] = []

    for rater in raters:
        rid = rater.get("rater_id", "unknown")
        rater_pair_data: list[dict] = []

        for entry in rater.get("pairwise", []):
            pid = entry.get("pair_id", "")
            pref = entry.get("preference", "").strip().upper()
            confidence = entry.get("confidence", 3)
            all_pairs[pid].append(pref)
            rater_pair_data.append(
                {
                    "pair_id": pid,
                    "preference": pref,
                    "confidence": confidence,
                }
            )

        per_rater_pairs.append({"rater_id": rid, "n_pairs": len(rater_pair_data)})

    if not all_pairs:
        return {
            "n_pairs": 0,
            "per_rater": per_rater_pairs,
            "note": "No pairwise responses found",
        }

    # Compute agreement across raters per pair
    pair_agreement: dict[str, dict] = {}
    for pid, prefs in sorted(all_pairs.items()):
        if len(prefs) < 2:
            pair_agreement[pid] = {
                "n_raters": len(prefs),
                "unanimous": True,
                "majority": prefs[0] if prefs else None,
            }
            continue

        from collections import Counter

        counts = Counter(prefs)
        majority_pref = counts.most_common(1)[0][0]
        unanimous = len(counts) == 1

        pair_agreement[pid] = {
            "n_raters": len(prefs),
            "unanimous": unanimous,
            "majority": majority_pref,
            "vote_distribution": dict(counts),
        }

    n_unanimous = sum(1 for v in pair_agreement.values() if v.get("unanimous", False))
    n_total_pairs = len(pair_agreement)

    # Control pair bias check
    # If pair IDs contain case references, check against answer key
    control_pair_results = _check_control_pairs(pair_agreement, cases)

    return {
        "n_pairs": n_total_pairs,
        "n_unanimous": n_unanimous,
        "unanimity_rate": round(n_unanimous / n_total_pairs, 4) if n_total_pairs > 0 else 0.0,
        "pair_details": pair_agreement,
        "per_rater": per_rater_pairs,
        "control_pair_check": control_pair_results,
    }


def _check_control_pairs(pair_agreement: dict[str, dict], cases: dict) -> dict:
    """Check control pairs where one case is safe and the other unsafe.

    If pair_id format is "CXX_vs_CYY", look up ground truth to verify
    clinician picked the correct (safer) episode.

    Args:
        pair_agreement: Per-pair agreement results.
        cases: Answer key cases.

    Returns:
        Dict with control pair analysis.
    """
    control_pairs_found = 0
    control_pairs_correct = 0

    for pid, pdata in pair_agreement.items():
        # Try to parse pair_id as "CXX_vs_CYY" or "CXX_CYY"
        parts = pid.replace("_vs_", "_").split("_")
        case_a = None
        case_b = None
        for part in parts:
            if part.upper() in cases:
                if case_a is None:
                    case_a = part.upper()
                else:
                    case_b = part.upper()

        if case_a is None or case_b is None:
            continue

        a_safe = cases[case_a]["ground_truth_safe"]
        b_safe = cases[case_b]["ground_truth_safe"]

        # Control pair: one safe, one unsafe
        if a_safe == b_safe:
            continue

        control_pairs_found += 1
        majority = pdata.get("majority", "")

        # The "correct" preference is the safe episode
        expected = "A" if a_safe else "B"
        if majority == expected:
            control_pairs_correct += 1

    accuracy = control_pairs_correct / control_pairs_found if control_pairs_found > 0 else None
    ci = wilson_ci(control_pairs_correct, control_pairs_found) if control_pairs_found > 0 else None

    return {
        "n_control_pairs": control_pairs_found,
        "n_correct": control_pairs_correct,
        "accuracy": round(accuracy, 4) if accuracy is not None else None,
        "accuracy_ci": [round(x, 4) for x in ci] if ci is not None else None,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------
def generate_report(absolute_results: dict, pairwise_results: dict) -> str:
    """Generate the analysis report in markdown format.

    Args:
        absolute_results: Output of analyze_absolute().
        pairwise_results: Output of analyze_pairwise().

    Returns:
        Markdown report string.
    """
    lines: list[str] = [
        "# E-3: Clinician Study Analysis Report",
        "",
        f"**Generated**: {datetime.now(UTC).isoformat()}",
        f"**Cases evaluated**: {absolute_results.get('n_cases', 0)}",
        f"**Raters**: {absolute_results.get('n_raters', 0)}",
        "",
        "---",
        "",
        "## 1. Evaluator Concordance with Clinician Consensus",
        "",
        "Each automated evaluator is compared to the clinician majority vote.",
        "Positive class = UNSAFE.",
        "",
    ]

    evals = absolute_results.get("evaluator_concordance", {})
    for eval_name, metrics in evals.items():
        lines.append(f"### {eval_name}")
        lines.append("")
        lines.append("| Metric | Value | 95% Wilson CI |")
        lines.append("|--------|------:|---------------|")

        for metric_name in ("sensitivity", "specificity", "ppv", "npv", "accuracy"):
            val = metrics.get(metric_name, 0)
            # Map metric names to CI keys
            ci_key_map = {
                "sensitivity": "sens_ci",
                "specificity": "spec_ci",
                "ppv": "ppv_ci",
                "npv": "npv_ci",
                "accuracy": "accuracy_ci",
            }
            ci = metrics.get(ci_key_map[metric_name], [0, 0])
            label = metric_name.capitalize()
            lines.append(f"| {label} | {val:.3f} | [{ci[0]:.3f}, {ci[1]:.3f}] |")

        lines.append("")
        lines.append(f"2x2 Table: TP={metrics['tp']}, FP={metrics['fp']}, FN={metrics['fn']}, TN={metrics['tn']}")
        lines.append("")

    # McNemar test
    mcn = absolute_results.get("mcnemar_hardviol_vs_c2", {})
    lines.extend(
        [
            "## 2. McNemar Test: HardViol vs C2",
            "",
            "Tests whether HardViol and C2>=0.7 differ significantly in concordance with clinician judgments.",
            "",
            f"- Discordant pairs: b={mcn.get('b_hardviol_correct_c2_wrong', 0)}, "
            f"c={mcn.get('c_c2_correct_hardviol_wrong', 0)}",
            f"- Chi-squared: {mcn.get('chi2', 0):.4f}",
            f"- p-value: {mcn.get('p_value', 1):.4f}",
            f"- Significant at alpha=0.05: {'Yes' if mcn.get('significant_at_0.05') else 'No'}",
            "",
        ]
    )

    # Inter-annotator agreement
    iaa = absolute_results.get("inter_annotator_agreement", {})
    if iaa:
        lines.extend(
            [
                "## 3. Inter-Annotator Agreement",
                "",
                f"- Number of raters: {iaa.get('n_raters', 0)}",
                f"- Gwet AC1: {iaa.get('gwet_ac1', 'N/A')} ({iaa.get('gwet_ac1_interpretation', '')})",
            ]
        )
        if iaa.get("fleiss_kappa") is not None:
            lines.append(f"- Fleiss kappa: {iaa['fleiss_kappa']} ({iaa.get('fleiss_kappa_interpretation', '')})")
        else:
            lines.append(f"- Fleiss kappa: {iaa.get('fleiss_kappa_interpretation', 'N/A')}")
        lines.append("")
        lines.append(
            "**Note**: Gwet AC1 is preferred over Cohen/Fleiss kappa for "
            "prevalence-skewed data (80% unsafe / 20% safe controls)."
        )
        lines.append("")

    # Per-violation-type
    vtype = absolute_results.get("per_violation_type", {})
    if vtype:
        lines.extend(
            [
                "## 4. Per-Violation-Type Concordance",
                "",
                "Agreement rate = fraction of cases with that violation type where the clinician also judged UNSAFE.",
                "",
                "| Violation Type | N Cases | Agreement | 95% CI |",
                "|----------------|--------:|----------:|--------|",
            ]
        )
        for vt in ("commission", "timing", "sequence"):
            vdata = vtype.get(vt, {})
            n = vdata.get("n_cases", 0)
            rate = vdata.get("agreement_rate")
            ci = vdata.get("agreement_ci")
            if rate is not None and ci is not None:
                lines.append(f"| {vt.capitalize()} | {n} | {rate:.3f} | [{ci[0]:.3f}, {ci[1]:.3f}] |")
            else:
                lines.append(f"| {vt.capitalize()} | {n} | N/A | N/A |")
        lines.append("")

    # Per-rater
    per_rater = absolute_results.get("per_rater", [])
    if per_rater:
        lines.extend(
            [
                "## 5. Per-Rater Results",
                "",
                "| Rater | Specialty | N | Accuracy | Sensitivity | Specificity |",
                "|-------|-----------|--:|---------:|------------:|------------:|",
            ]
        )
        for rr in per_rater:
            conc = rr.get("concordance_with_ground_truth", {})
            lines.append(
                f"| {rr['rater_id']} | {rr.get('specialty', '')} | "
                f"{rr['n_responses']} | "
                f"{conc.get('accuracy', 0):.3f} | "
                f"{conc.get('sensitivity', 0):.3f} | "
                f"{conc.get('specificity', 0):.3f} |"
            )
        lines.append("")

    # Pairwise section
    lines.extend(
        [
            "## 6. Pairwise Analysis",
            "",
        ]
    )
    n_pairs = pairwise_results.get("n_pairs", 0)
    if n_pairs == 0:
        lines.append("No pairwise responses collected.")
    else:
        lines.extend(
            [
                f"- Total pairs: {n_pairs}",
                f"- Unanimous: {pairwise_results.get('n_unanimous', 0)} "
                f"({pairwise_results.get('unanimity_rate', 0):.1%})",
            ]
        )
        ctrl = pairwise_results.get("control_pair_check", {})
        if ctrl.get("n_control_pairs", 0) > 0:
            lines.extend(
                [
                    "",
                    "### Control Pair Bias Check",
                    "",
                    f"- Control pairs found: {ctrl['n_control_pairs']}",
                    f"- Correctly identified: {ctrl['n_correct']}",
                    f"- Accuracy: {ctrl.get('accuracy', 0):.3f}",
                ]
            )
            if ctrl.get("accuracy_ci"):
                lines.append(f"- 95% CI: [{ctrl['accuracy_ci'][0]:.3f}, {ctrl['accuracy_ci'][1]:.3f}]")
    lines.append("")

    # Summary
    lines.extend(
        [
            "---",
            "",
            "## Summary",
            "",
        ]
    )

    hardviol_acc = evals.get("HardViol", {}).get("accuracy", 0)
    c2_acc = evals.get("C2_ge_0.7", {}).get("accuracy", 0)
    best_eval = "HardViol" if hardviol_acc >= c2_acc else "C2>=0.7"
    lines.append(
        f"Best automated evaluator by accuracy: **{best_eval}** (HardViol={hardviol_acc:.3f}, C2={c2_acc:.3f})"
    )

    if iaa.get("gwet_ac1") is not None:
        lines.append(f"Inter-annotator agreement (AC1): {iaa['gwet_ac1']:.3f} ({iaa['gwet_ac1_interpretation']})")

    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# LaTeX table generation
# ---------------------------------------------------------------------------
def generate_latex_table(absolute_results: dict) -> str:
    """Generate booktabs LaTeX table for clinician validity results.

    Args:
        absolute_results: Output of analyze_absolute().

    Returns:
        LaTeX table string.
    """
    evals = absolute_results.get("evaluator_concordance", {})

    # Map internal names to display names
    display_names = {
        "HardViol": r"HardViol (CGA-Bench)",
        "C2_ge_0.7": r"C2 $\geq$ 0.7",
        "AC_Proxy": r"AC-Proxy",
    }

    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Clinician concordance with automated evaluators.",
        r"    Positive class = UNSAFE. Wilson score 95\% CI in brackets.",
        r"    $n="
        + str(absolute_results.get("n_cases", 0))
        + r"$ cases, "
        + str(absolute_results.get("n_raters", 0))
        + r" raters (majority vote).}",
        r"\label{tab:clinician-validity}",
        r"\small",
        r"\begin{tabular}{lcccc}",
        r"\toprule",
        r"Evaluator & Sens. & Spec. & PPV & NPV \\",
        r"\midrule",
    ]

    for eval_key in ("HardViol", "C2_ge_0.7", "AC_Proxy"):
        metrics = evals.get(eval_key, {})
        name = display_names.get(eval_key, eval_key)

        sens = metrics.get("sensitivity", 0)
        spec = metrics.get("specificity", 0)
        ppv_val = metrics.get("ppv", 0)
        npv_val = metrics.get("npv", 0)

        sens_ci = metrics.get("sens_ci", [0, 0])
        spec_ci = metrics.get("spec_ci", [0, 0])
        ppv_ci = metrics.get("ppv_ci", [0, 0])
        npv_ci = metrics.get("npv_ci", [0, 0])

        def _fmt(val: float, ci: list[float]) -> str:
            return f"{val:.2f} [{ci[0]:.2f}, {ci[1]:.2f}]"

        row = (
            f"{name} & "
            f"{_fmt(sens, sens_ci)} & "
            f"{_fmt(spec, spec_ci)} & "
            f"{_fmt(ppv_val, ppv_ci)} & "
            f"{_fmt(npv_val, npv_ci)} \\\\"
        )
        lines.append(row)

    # Add McNemar result as a note
    mcn = absolute_results.get("mcnemar_hardviol_vs_c2", {})

    lines.extend(
        [
            r"\bottomrule",
            r"\multicolumn{5}{l}{\footnotesize McNemar (HardViol vs C2): "
            + f"$\\chi^2={mcn.get('chi2', 0):.2f}$, "
            + f"$p={mcn.get('p_value', 1):.3f}$"
            + r"} \\",
            r"\end{tabular}",
            r"\end{table}",
        ]
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Template generation (when no responses exist yet)
# ---------------------------------------------------------------------------
def generate_response_template(study_dir: Path, answer_key: dict) -> None:
    """Generate a response template file showing the expected format.

    Args:
        study_dir: Path to the clinician_study directory.
        answer_key: Loaded answer key.
    """
    cases = answer_key.get("cases", {})
    case_ids = sorted(cases.keys())

    absolute_template = [
        {
            "case_id": cid,
            "safe_unsafe": "SAFE or UNSAFE",
            "conformant": False,
            "first_unsafe_step": 0,
            "first_unsafe_reason": "",
            "confidence": 3,
        }
        for cid in case_ids
    ]

    # Generate a few example pairwise pairs
    pairwise_template = []
    for i in range(0, min(len(case_ids) - 1, 5)):
        pairwise_template.append(
            {
                "pair_id": f"pair_{i + 1:02d}",
                "preference": "A or B",
                "confidence": 3,
            }
        )

    template = {
        "raters": [
            {
                "rater_id": "rater_1",
                "specialty": "Emergency Medicine",
                "absolute": absolute_template,
                "pairwise": pairwise_template,
            }
        ]
    }

    out_path = study_dir / "response_template.json"
    out_path.write_text(json.dumps(template, indent=2))
    print(f"  Template saved: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    """Run the clinician study analysis pipeline."""
    print("=" * 60)
    print("E-3: Clinician Study Analysis")
    print("=" * 60)

    # Load answer key
    answer_key_path = STUDY_DIR / "answer_key.json"
    if not answer_key_path.exists():
        print(f"ERROR: Answer key not found at {answer_key_path}")
        print("Run p8_clinician_survey.py first to generate survey materials.")
        sys.exit(1)

    print("\n[1/5] Loading answer key...")
    answer_key = load_answer_key(answer_key_path)
    n_cases = len(answer_key.get("cases", {}))
    print(f"  {n_cases} cases loaded")

    # Check for responses
    response_dir = STUDY_DIR / "raw_responses"
    if not response_dir.exists():
        print(f"\n  No responses found at {response_dir}")
        print("  Generating response template for expected format...")
        response_dir.mkdir(parents=True, exist_ok=True)
        generate_response_template(STUDY_DIR, answer_key)
        print("\n  Place clinician response files in:")
        print(f"    {response_dir}/")
        print("  Then re-run this script.")
        return

    # Load responses
    print("\n[2/5] Loading clinician responses...")
    responses = load_responses(response_dir)
    n_raters = len(responses.get("raters", []))
    if n_raters == 0:
        print("  WARNING: No rater responses found in raw_responses/")
        print("  Generating response template...")
        generate_response_template(STUDY_DIR, answer_key)
        return
    print(f"  {n_raters} raters loaded")

    for rater in responses.get("raters", []):
        rid = rater.get("rater_id", "?")
        n_abs = len(rater.get("absolute", []))
        n_pw = len(rater.get("pairwise", []))
        print(f"    {rid}: {n_abs} absolute, {n_pw} pairwise")

    # Absolute analysis
    print("\n[3/5] Analyzing absolute judgments...")
    abs_results = analyze_absolute(responses, answer_key)

    evals = abs_results.get("evaluator_concordance", {})
    for eval_name, metrics in evals.items():
        sens = metrics.get("sensitivity", 0)
        spec = metrics.get("specificity", 0)
        acc = metrics.get("accuracy", 0)
        print(f"  {eval_name}: Sens={sens:.3f} Spec={spec:.3f} Acc={acc:.3f}")

    iaa = abs_results.get("inter_annotator_agreement", {})
    if iaa.get("gwet_ac1") is not None:
        print(f"  Inter-annotator AC1: {iaa['gwet_ac1']:.3f} ({iaa['gwet_ac1_interpretation']})")

    # Pairwise analysis
    print("\n[4/5] Analyzing pairwise preferences...")
    pair_results = analyze_pairwise(responses, answer_key)
    n_pairs = pair_results.get("n_pairs", 0)
    print(f"  {n_pairs} pairs analyzed")
    if n_pairs > 0:
        print(
            f"  Unanimity: {pair_results.get('n_unanimous', 0)}/{n_pairs} ({pair_results.get('unanimity_rate', 0):.1%})"
        )

    # Generate outputs
    print("\n[5/5] Generating outputs...")

    # Analysis report
    report = generate_report(abs_results, pair_results)
    report_path = STUDY_DIR / "analysis_report.md"
    report_path.write_text(report)
    print(f"  Report: {report_path}")

    # LaTeX table
    latex = generate_latex_table(abs_results)
    tex_dir = EVIDENCE_DIR / "tables"
    tex_dir.mkdir(parents=True, exist_ok=True)
    tex_path = tex_dir / "clinician_validity.tex"
    tex_path.write_text(latex)
    print(f"  LaTeX: {tex_path}")

    # Full results JSON
    full_results = {
        "absolute": abs_results,
        "pairwise": pair_results,
    }
    json_path = STUDY_DIR / "analysis_results.json"
    json_path.write_text(json.dumps(full_results, indent=2))
    print(f"  JSON: {json_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("ANALYSIS COMPLETE")
    print("=" * 60)

    hardviol = evals.get("HardViol", {})
    c2 = evals.get("C2_ge_0.7", {})
    print(
        f"  HardViol accuracy: {hardviol.get('accuracy', 0):.3f} "
        f"[{hardviol.get('accuracy_ci', [0, 0])[0]:.3f}, "
        f"{hardviol.get('accuracy_ci', [0, 0])[1]:.3f}]"
    )
    print(
        f"  C2>=0.7 accuracy:  {c2.get('accuracy', 0):.3f} "
        f"[{c2.get('accuracy_ci', [0, 0])[0]:.3f}, "
        f"{c2.get('accuracy_ci', [0, 0])[1]:.3f}]"
    )

    mcn = abs_results.get("mcnemar_hardviol_vs_c2", {})
    print(
        f"  McNemar p-value:   {mcn.get('p_value', 1):.4f} "
        f"({'significant' if mcn.get('significant_at_0.05') else 'not significant'})"
    )


if __name__ == "__main__":
    main()
