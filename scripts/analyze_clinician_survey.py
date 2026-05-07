#!/usr/bin/env python3
"""
Clinician Survey Analysis Script

Analyzes clinician pairwise preference survey results and computes
alignment between CGA ranking, task-completion ranking, and clinician preference.

Usage:
    python scripts/analyze_clinician_survey.py --responses survey_responses.csv
    python scripts/analyze_clinician_survey.py --responses dir_of_csvs/
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import statistics
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)


def load_responses(path: Path) -> List[Dict]:
    """Load survey responses from CSV file(s)."""
    responses: List[Dict] = []
    if path.is_dir():
        files = sorted(path.glob("*.csv"))
    else:
        files = [path]

    for csv_file in files:
        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                responses.append(row)
    logger.info(f"Loaded {len(responses)} responses from {len(files)} file(s)")
    return responses


def compute_majority_vote(
    responses: List[Dict],
    question_key: str,
    pair_id_key: str = "pair_id",
) -> Dict[str, str]:
    """Compute majority vote per pair for a given question."""
    votes: Dict[str, Dict[str, int]] = {}
    for r in responses:
        pid = r.get(pair_id_key, "")
        answer = r.get(question_key, "").strip()
        if not pid or not answer:
            continue
        votes.setdefault(pid, {})
        votes[pid][answer] = votes[pid].get(answer, 0) + 1

    majority: Dict[str, str] = {}
    for pid, v in votes.items():
        majority[pid] = max(v.items(), key=lambda x: x[1])[0]
    return majority


def kendall_tau(ranking_a: List[str], ranking_b: List[str]) -> float:
    """Compute Kendall's tau-b between two rankings."""
    items = list(set(ranking_a) & set(ranking_b))
    if len(items) < 2:
        return 0.0

    rank_a = {item: i for i, item in enumerate(ranking_a) if item in items}
    rank_b = {item: i for i, item in enumerate(ranking_b) if item in items}

    concordant = 0
    discordant = 0
    for i, j in combinations(items, 2):
        diff_a = rank_a[i] - rank_a[j]
        diff_b = rank_b[i] - rank_b[j]
        if diff_a * diff_b > 0:
            concordant += 1
        elif diff_a * diff_b < 0:
            discordant += 1

    n = concordant + discordant
    if n == 0:
        return 0.0
    return (concordant - discordant) / n


def cohens_kappa(
    rater_a: List[str],
    rater_b: List[str],
) -> float:
    """Compute Cohen's kappa between two raters."""
    if len(rater_a) != len(rater_b) or len(rater_a) == 0:
        return 0.0

    categories = sorted(set(rater_a) | set(rater_b))
    n = len(rater_a)

    # Observed agreement
    po = sum(1 for a, b in zip(rater_a, rater_b) if a == b) / n

    # Expected agreement
    pe = sum(
        (sum(1 for x in rater_a if x == c) / n)
        * (sum(1 for x in rater_b if x == c) / n)
        for c in categories
    )

    if pe == 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def fleiss_kappa(ratings_matrix: List[List[str]]) -> float:
    """Compute Fleiss' kappa for multiple raters.

    Args:
        ratings_matrix: List of [rater1_answer, rater2_answer, ...] per item.
    """
    if not ratings_matrix:
        return 0.0

    n_items = len(ratings_matrix)
    n_raters = len(ratings_matrix[0])
    categories = sorted(set(a for row in ratings_matrix for a in row))

    if n_raters < 2:
        return 0.0

    # Proportion of assignments to each category per item
    p_bar = {}
    for c in categories:
        p_bar[c] = sum(
            sum(1 for a in row if a == c) for row in ratings_matrix
        ) / (n_items * n_raters)

    # Per-item agreement
    p_i = []
    for row in ratings_matrix:
        agreement = sum(
            sum(1 for a in row if a == c) ** 2 - sum(1 for a in row if a == c)
            for c in categories
        ) / (n_raters * (n_raters - 1))
        p_i.append(agreement)

    p_bar_total = sum(p_i) / n_items
    pe = sum(p ** 2 for p in p_bar.values())

    if pe == 1.0:
        return 1.0
    return (p_bar_total - pe) / (1 - pe)


def analyze_survey(
    responses: List[Dict],
    pairs_file: Optional[Path] = None,
) -> Dict:
    """Run full analysis on survey responses."""
    # Load pair metadata if available
    pairs_meta = {}
    if pairs_file and pairs_file.exists():
        with open(pairs_file) as f:
            data = json.load(f)
        for p in data.get("pairs", []):
            pairs_meta[p["pair_id"]] = p

    questions = [
        ("Q1_guideline_adherence", "Guideline Adherence"),
        ("Q2_patient_safety", "Patient Safety"),
        ("Q3_supervisory_acceptance", "Supervisory Acceptance"),
    ]

    results: Dict = {"questions": {}, "inter_rater": {}}

    # Per-question majority vote
    for q_key, q_name in questions:
        majority = compute_majority_vote(responses, q_key)
        results["questions"][q_key] = {
            "name": q_name,
            "majority_votes": majority,
            "n_pairs": len(majority),
        }

        # CGA alignment: does majority prefer the trace with higher CGA?
        if pairs_meta:
            aligned = 0
            total = 0
            for pid, vote in majority.items():
                meta = pairs_meta.get(pid)
                if not meta:
                    continue
                total += 1
                cga_a = meta.get("trace_a_compliance", 0)
                cga_b = meta.get("trace_b_compliance", 0)
                cga_prefers = "Trace A" if cga_a > cga_b else "Trace B"
                if vote == cga_prefers or vote == "Equal":
                    aligned += 1

            results["questions"][q_key]["cga_alignment"] = round(
                aligned / max(total, 1), 4
            )

    # Inter-rater reliability
    raters = sorted(set(r.get("rater_id", "") for r in responses) - {""})
    if len(raters) >= 2:
        # Cohen's kappa for each pair of raters
        kappas = []
        for ra, rb in combinations(raters, 2):
            for q_key, _ in questions:
                answers_a = [
                    r[q_key]
                    for r in responses
                    if r.get("rater_id") == ra and q_key in r
                ]
                answers_b = [
                    r[q_key]
                    for r in responses
                    if r.get("rater_id") == rb and q_key in r
                ]
                min_len = min(len(answers_a), len(answers_b))
                if min_len > 0:
                    k = cohens_kappa(answers_a[:min_len], answers_b[:min_len])
                    kappas.append(k)

        if kappas:
            results["inter_rater"]["mean_cohens_kappa"] = round(
                statistics.mean(kappas), 4
            )
            results["inter_rater"]["n_rater_pairs"] = len(
                list(combinations(raters, 2))
            )

        # Fleiss' kappa
        pairs_answered = sorted(
            set(r.get("pair_id", "") for r in responses) - {""}
        )
        for q_key, _ in questions:
            matrix = []
            for pid in pairs_answered:
                answers = [
                    r[q_key]
                    for r in responses
                    if r.get("pair_id") == pid and q_key in r
                ]
                if len(answers) >= 2:
                    matrix.append(answers)

            if matrix:
                fk = fleiss_kappa(matrix)
                results["inter_rater"][f"fleiss_kappa_{q_key}"] = round(fk, 4)

    results["n_responses"] = len(responses)
    results["n_raters"] = len(raters)

    return results


def main() -> None:
    parser = argparse.ArgumentParser(description="Analyze clinician survey")
    parser.add_argument(
        "--responses",
        type=str,
        required=True,
        help="Path to CSV file or directory of CSVs",
    )
    parser.add_argument(
        "--pairs",
        type=str,
        default="evidence_pack/experiments/clinician_pairs.json",
        help="Path to pairs metadata JSON",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="evidence_pack/analysis/clinician_analysis.json",
        help="Output JSON path",
    )
    args = parser.parse_args()

    responses = load_responses(Path(args.responses))
    results = analyze_survey(responses, Path(args.pairs))

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    logger.info(f"Results saved to {output_path}")

    # Print summary
    print(f"\n{'='*60}")
    print("CLINICIAN SURVEY ANALYSIS")
    print(f"{'='*60}")
    print(f"Responses: {results['n_responses']}")
    print(f"Raters: {results['n_raters']}")

    for q_key, q_data in results.get("questions", {}).items():
        align = q_data.get("cga_alignment", "N/A")
        print(f"\n{q_data['name']}:")
        print(f"  Pairs evaluated: {q_data['n_pairs']}")
        print(f"  CGA alignment: {align}")

    irr = results.get("inter_rater", {})
    if irr:
        print(f"\nInter-rater reliability:")
        print(f"  Mean Cohen's κ: {irr.get('mean_cohens_kappa', 'N/A')}")
        for k, v in irr.items():
            if "fleiss" in k:
                print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
