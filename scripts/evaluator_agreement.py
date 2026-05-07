"""Evaluator Agreement Analysis (Defense against Attack 1.1)

Computes inter-rater reliability metrics across 6 evaluators
from the verdict matrix to quantify evaluator agreement.

Outputs:
  - Pairwise Cohen's kappa for all 15 evaluator pairs
  - Fleiss' kappa across all 6 evaluators
  - Top-20 most-disagreed episodes
  - Agreement interpretation

Usage:
    PYTHONPATH=. python scripts/evaluator_agreement.py
"""

from __future__ import annotations

from itertools import combinations
import json
from pathlib import Path

import numpy as np

BASE_DIR = Path(__file__).parent.parent
VERDICT_PATH = BASE_DIR / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
OUTPUT_PATH = BASE_DIR / "evidence_pack" / "analysis" / "evaluator_agreement.json"

EVALUATOR_KEYS = ["dxem", "ac_proxy", "mab_proxy", "c2_pass", "acov_pass", "v4_hard"]
EVALUATOR_LABELS = ["DxEM", "AC-Proxy", "MAB-Proxy", "C2", "ACov", "CGA-Bench"]


def load_per_episode(path: Path = VERDICT_PATH) -> list[dict]:
    """Load per-episode verdict data from verdict matrix JSON."""
    with open(path) as f:
        data = json.load(f)
    return data["per_episode"]


def cohens_kappa(rater1: list[int], rater2: list[int]) -> float:
    """Compute Cohen's kappa for two binary raters.

    Args:
        rater1: Binary ratings (0/1) from rater 1.
        rater2: Binary ratings (0/1) from rater 2.

    Returns:
        Cohen's kappa coefficient.
    """
    n = len(rater1)
    if n == 0:
        return 0.0

    agree = sum(a == b for a, b in zip(rater1, rater2))
    po = agree / n

    p1_yes = sum(rater1) / n
    p2_yes = sum(rater2) / n
    pe = p1_yes * p2_yes + (1 - p1_yes) * (1 - p2_yes)

    if pe >= 1.0:
        return 1.0
    return (po - pe) / (1 - pe)


def fleiss_kappa(ratings: np.ndarray) -> float:
    """Compute Fleiss' kappa for multiple raters.

    Args:
        ratings: N x k matrix where N = subjects, k = categories.
                 ratings[i][j] = number of raters assigning subject i
                 to category j.

    Returns:
        Fleiss' kappa coefficient.
    """
    n_subjects, n_categories = ratings.shape
    n_raters = int(ratings.sum(axis=1)[0])

    p_j = ratings.sum(axis=0) / (n_subjects * n_raters)

    p_i = ((ratings**2).sum(axis=1) - n_raters) / (n_raters * (n_raters - 1))

    p_bar = p_i.mean()
    p_e = (p_j**2).sum()

    if p_e >= 1.0:
        return 1.0
    return float((p_bar - p_e) / (1 - p_e))


def interpret_kappa(kappa: float) -> str:
    """Interpret kappa value using Landis & Koch scale."""
    if kappa < 0.0:
        return "poor agreement"
    if kappa < 0.20:
        return "slight agreement"
    if kappa < 0.40:
        return "fair agreement"
    if kappa < 0.60:
        return "moderate agreement"
    if kappa < 0.80:
        return "substantial agreement"
    return "almost perfect agreement"


def extract_verdicts(
    episodes: list[dict],
) -> dict[str, list[int]]:
    """Extract binary verdict vectors for each evaluator.

    Returns:
        Dict mapping evaluator key to list of binary verdicts (0/1).
    """
    verdicts: dict[str, list[int]] = {k: [] for k in EVALUATOR_KEYS}
    for ep in episodes:
        for key in EVALUATOR_KEYS:
            val = ep.get(key, False)
            verdicts[key].append(1 if val else 0)
    return verdicts


def compute_disagreement_scores(
    episodes: list[dict],
    verdicts: dict[str, list[int]],
) -> list[dict]:
    """Compute per-episode disagreement scores.

    Disagreement = min(pass_count, fail_count) / n_evaluators.
    Maximum disagreement (0.5) when evaluators split 3-3.

    Returns:
        Sorted list of episode disagreement records (descending).
    """
    scores = []
    n_evaluators = len(EVALUATOR_KEYS)

    for i, ep in enumerate(episodes):
        votes = [verdicts[k][i] for k in EVALUATOR_KEYS]
        pass_count = sum(votes)
        fail_count = n_evaluators - pass_count
        disagreement = min(pass_count, fail_count) / n_evaluators

        per_evaluator = {}
        for key, label in zip(EVALUATOR_KEYS, EVALUATOR_LABELS):
            per_evaluator[label] = "PASS" if verdicts[key][i] else "FAIL"

        scores.append(
            {
                "episode_id": ep["episode_id"],
                "scenario_id": ep["scenario_id"],
                "model": ep.get("model", ""),
                "pass_count": pass_count,
                "fail_count": fail_count,
                "disagreement": round(disagreement, 4),
                "verdicts": per_evaluator,
            }
        )

    scores.sort(key=lambda x: (-x["disagreement"], x["episode_id"]))
    return scores


def main() -> None:
    """Run evaluator agreement analysis."""
    episodes = load_per_episode()
    verdicts = extract_verdicts(episodes)

    n_episodes = len(episodes)
    print(f"Loaded {n_episodes} episodes")

    # --- Pairwise Cohen's kappa ---
    print("\n=== Pairwise Cohen's Kappa ===")
    pairwise_kappa: dict[str, float] = {}
    for (k1, l1), (k2, l2) in combinations(zip(EVALUATOR_KEYS, EVALUATOR_LABELS), 2):
        k = cohens_kappa(verdicts[k1], verdicts[k2])
        pair_name = f"{l1}_vs_{l2}"
        pairwise_kappa[pair_name] = round(k, 4)
        print(f"  {l1} vs {l2}: kappa={k:.4f} ({interpret_kappa(k)})")

    # --- Fleiss' kappa ---
    rating_matrix = np.zeros((n_episodes, 2), dtype=float)
    for i in range(n_episodes):
        pass_count = sum(verdicts[k][i] for k in EVALUATOR_KEYS)
        rating_matrix[i, 1] = pass_count  # "pass" category
        rating_matrix[i, 0] = len(EVALUATOR_KEYS) - pass_count  # "fail" category

    fk = fleiss_kappa(rating_matrix)
    fk_interp = interpret_kappa(fk)
    print(f"\nFleiss' kappa (all {len(EVALUATOR_KEYS)} evaluators): kappa={fk:.4f}")
    print(f"Interpretation: {fk_interp}")

    # --- Per-evaluator pass rates ---
    print("\n=== Per-Evaluator Pass Rates ===")
    pass_rates: dict[str, float] = {}
    for key, label in zip(EVALUATOR_KEYS, EVALUATOR_LABELS):
        rate = sum(verdicts[key]) / n_episodes
        pass_rates[label] = round(rate, 4)
        print(f"  {label}: {sum(verdicts[key])}/{n_episodes} ({rate:.1%})")

    # --- Most-disagreed episodes ---
    disagreement_scores = compute_disagreement_scores(episodes, verdicts)
    print("\n=== Top 20 Most-Disagreed Episodes ===")
    for entry in disagreement_scores[:20]:
        print(
            f"  {entry['episode_id']}: "
            f"{entry['pass_count']} pass / {entry['fail_count']} fail "
            f"(disagreement={entry['disagreement']:.2f})"
        )

    # --- Agreement matrix (for heatmap) ---
    agreement_matrix: dict[str, dict[str, float]] = {}
    for l1 in EVALUATOR_LABELS:
        agreement_matrix[l1] = {}
        for l2 in EVALUATOR_LABELS:
            if l1 == l2:
                agreement_matrix[l1][l2] = 1.0
            else:
                pair_a = f"{l1}_vs_{l2}"
                pair_b = f"{l2}_vs_{l1}"
                kval = pairwise_kappa.get(pair_a) or pairwise_kappa.get(pair_b, 0.0)
                agreement_matrix[l1][l2] = kval

    # --- Save results ---
    results = {
        "n_episodes": n_episodes,
        "evaluators": EVALUATOR_LABELS,
        "pairwise_kappa": pairwise_kappa,
        "fleiss_kappa": round(fk, 4),
        "fleiss_interpretation": fk_interp,
        "pass_rates": pass_rates,
        "agreement_matrix": agreement_matrix,
        "top_disagreed_episodes": disagreement_scores[:20],
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"\nResults saved to {OUTPUT_PATH}")


if __name__ == "__main__":
    main()
