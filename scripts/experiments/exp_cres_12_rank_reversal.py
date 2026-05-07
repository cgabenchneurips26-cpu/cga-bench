#!/usr/bin/env python3
"""CRES-12: Rank-Reversal Multi-Metric for NeurIPS defense.

Quantifies how much model rankings change across evaluators (AC-Proxy,
MAB-Proxy, C2, CGA-Bench). Demonstrates that no single evaluator provides
a stable ranking of model quality.

Metrics computed:
  a) Mean pairwise Spearman rho across 6 evaluator pairs
  b) Per-model rank CI width (bootstrap)
  c) Top-k Jaccard (k=3) across evaluator pairs
  d) Normalized Kendall tau distance across evaluator pairs
  e) Number of rank reversals (model pairs reversed in >= 1 evaluator pair)
  f) Worst-case reversal depth (max rank change for any single model)

Outputs:
  evidence_pack/cres_12/cres_12_results.json
  evidence_pack/cres_12/cres_12_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/exp_cres_12_rank_reversal.py
"""

from __future__ import annotations

from itertools import combinations
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from scipy.stats import kendalltau, spearmanr
from scripts.experiments._common import EVIDENCE_DIR, save_json
from scripts.experiments._episode_cache import COMPLETE_MODELS, load_cached_verdicts

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

OUTPUT_DIR = EVIDENCE_DIR / "cres_12"

EVALUATOR_NAMES: list[str] = ["AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]
EVALUATOR_KEYS: list[str] = ["ac_proxy", "mab_proxy", "c2_pass", "cga_pass"]
EVAL_KEY_MAP: dict[str, str] = dict(zip(EVALUATOR_NAMES, EVALUATOR_KEYS))

TOP_K = 3
N_BOOTSTRAP = 2000
SEED = 42

MODEL_LABELS: dict[str, str] = {
    "oss120b": "OSS-120B",
    "qwen27b": "Qwen3.5-27B",
    "qwen35b": "Qwen3.5-35B",
    "qwen4b": "Qwen3-4B",
    "qwen397b": "Qwen3.5-397B",
    "gemma31b": "Gemma4-31B",
    "nemotron30b": "Nemotron-30B",
}


# ---------------------------------------------------------------------------
# Pass-rate computation
# ---------------------------------------------------------------------------


def compute_model_pass_rates(
    scored: list[dict[str, Any]],
) -> dict[str, dict[str, float]]:
    """Compute per-evaluator pass rate for each model.

    Returns:
        Nested dict: model -> evaluator_name -> pass_rate (0-1).
    """
    # Group records by model
    by_model: dict[str, list[dict[str, Any]]] = {}
    for r in scored:
        m = r.get("model", "")
        if m not in COMPLETE_MODELS:
            continue
        by_model.setdefault(m, []).append(r)

    rates: dict[str, dict[str, float]] = {}
    for model, records in by_model.items():
        n = len(records)
        if n == 0:
            rates[model] = dict.fromkeys(EVALUATOR_NAMES, 0.0)
            continue
        rates[model] = {ev: sum(1 for r in records if r[key]) / n for ev, key in EVAL_KEY_MAP.items()}
    return rates


# ---------------------------------------------------------------------------
# Rank utilities
# ---------------------------------------------------------------------------


def pass_rates_to_ranks(
    model_pass_rates: dict[str, dict[str, float]],
    evaluator: str,
) -> dict[str, int]:
    """Rank models by pass rate for a given evaluator (rank 1 = best).

    Ties broken by model name for determinism.
    """
    models = sorted(model_pass_rates.keys())
    sorted_models = sorted(
        models,
        key=lambda m: (-model_pass_rates[m][evaluator], m),
    )
    return {m: i + 1 for i, m in enumerate(sorted_models)}


def kendall_tau_distance_normalized(
    ranks_a: dict[str, int],
    ranks_b: dict[str, int],
) -> float:
    """Normalized Kendall tau distance in [0, 1].

    tau_distance = (1 - kendall_tau_correlation) / 2
    """
    models = sorted(ranks_a.keys())
    if len(models) < 2:
        return 0.0
    vec_a = np.array([ranks_a[m] for m in models], dtype=float)
    vec_b = np.array([ranks_b[m] for m in models], dtype=float)
    tau, _ = kendalltau(vec_a, vec_b)
    return float((1.0 - tau) / 2.0)


def jaccard_top_k(
    ranks_a: dict[str, int],
    ranks_b: dict[str, int],
    k: int = TOP_K,
) -> float:
    """Jaccard similarity of top-k model sets."""
    top_a = {m for m, r in ranks_a.items() if r <= k}
    top_b = {m for m, r in ranks_b.items() if r <= k}
    union = top_a | top_b
    if not union:
        return 1.0
    return len(top_a & top_b) / len(union)


# ---------------------------------------------------------------------------
# Bootstrap rank CI
# ---------------------------------------------------------------------------


def bootstrap_rank_ci_width(
    records_for_model: list[dict[str, Any]],
    target_model: str,
    evaluator: str,
    all_model_rates: dict[str, dict[str, float]],
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = SEED,
) -> float:
    """Estimate 95% CI width for a model's rank under a given evaluator.

    Bootstraps pass-rate uncertainty for the target model, then derives
    rank distribution assuming other models have fixed pass rates.

    Args:
        records_for_model: Scored episode records for the target model.
        target_model: Name of the target model.
        evaluator: Evaluator name (e.g., "AC-Proxy").
        all_model_rates: model_name -> {evaluator_name: pass_rate}.
    """
    key = EVAL_KEY_MAP[evaluator]
    arr = np.array([1.0 if r[key] else 0.0 for r in records_for_model])
    n = len(arr)
    if n == 0:
        return 0.0

    rng = np.random.default_rng(seed)
    # Fixed pass rates of OTHER models for this evaluator
    other_model_rates_for_eval: list[float] = [
        all_model_rates[m][evaluator] for m in all_model_rates if m != target_model
    ]

    boot_ranks: list[float] = []
    for _ in range(n_bootstrap):
        sample = arr[rng.integers(0, n, size=n)]
        boot_rate = float(sample.mean())
        # Count how many other models have a higher pass rate (rank = count_above + 1)
        rank = 1 + sum(1 for rate in other_model_rates_for_eval if rate > boot_rate)
        boot_ranks.append(float(rank))

    boot_ranks_arr = np.array(boot_ranks)
    lo = float(np.percentile(boot_ranks_arr, 2.5))
    hi = float(np.percentile(boot_ranks_arr, 97.5))
    return round(hi - lo, 3)


# ---------------------------------------------------------------------------
# Main computation
# ---------------------------------------------------------------------------


def compute_rank_reversal_metrics(
    model_pass_rates: dict[str, dict[str, float]],
) -> dict[str, Any]:
    """Compute all CRES-12 metrics from model pass rates.

    Args:
        model_pass_rates: model -> evaluator_name -> pass_rate.

    Returns:
        Dict with all CRES-12 metric values.
    """
    models = sorted(model_pass_rates.keys())
    n_models = len(models)
    eval_pairs = list(combinations(EVALUATOR_NAMES, 2))

    # Build rank tables: evaluator -> model -> rank
    rank_tables: dict[str, dict[str, int]] = {ev: pass_rates_to_ranks(model_pass_rates, ev) for ev in EVALUATOR_NAMES}

    # --- (a) Mean pairwise Spearman rho ---
    spearman_rhos: list[float] = []
    for ev_a, ev_b in eval_pairs:
        vec_a = np.array([rank_tables[ev_a][m] for m in models], dtype=float)
        vec_b = np.array([rank_tables[ev_b][m] for m in models], dtype=float)
        rho, _ = spearmanr(vec_a, vec_b)
        spearman_rhos.append(float(rho))
    mean_spearman = float(np.mean(spearman_rhos))

    # --- (c) Top-k Jaccard ---
    jaccard_scores: list[float] = []
    for ev_a, ev_b in eval_pairs:
        j = jaccard_top_k(rank_tables[ev_a], rank_tables[ev_b], k=TOP_K)
        jaccard_scores.append(j)
    mean_jaccard = float(np.mean(jaccard_scores))

    # --- (d) Normalized Kendall tau distance ---
    kendall_distances: list[float] = []
    for ev_a, ev_b in eval_pairs:
        d = kendall_tau_distance_normalized(rank_tables[ev_a], rank_tables[ev_b])
        kendall_distances.append(d)
    mean_kendall_dist = float(np.mean(kendall_distances))

    # --- (e) Number of rank reversals ---
    # A reversal: model pair (i, j) has reversed ordering in >= 1 evaluator pair
    reversals = 0
    reversed_pairs: list[tuple[str, str]] = []
    for m_a, m_b in combinations(models, 2):
        is_reversed = False
        for ev_a, ev_b in eval_pairs:
            rank_a_in_eva = rank_tables[ev_a][m_a]
            rank_b_in_eva = rank_tables[ev_a][m_b]
            rank_a_in_evb = rank_tables[ev_b][m_a]
            rank_b_in_evb = rank_tables[ev_b][m_b]
            # Ordering in ev_a vs ev_b
            order_in_eva = rank_a_in_eva < rank_b_in_eva  # True = m_a ranked better
            order_in_evb = rank_a_in_evb < rank_b_in_evb
            if order_in_eva != order_in_evb:
                is_reversed = True
                break
        if is_reversed:
            reversals += 1
            reversed_pairs.append((m_a, m_b))

    # --- (f) Worst-case reversal depth ---
    # Max rank change for any single model across evaluators
    worst_depth = 0
    worst_model = ""
    per_model_rank_range: dict[str, dict[str, Any]] = {}
    for m in models:
        model_ranks = [rank_tables[ev][m] for ev in EVALUATOR_NAMES]
        depth = max(model_ranks) - min(model_ranks)
        per_model_rank_range[m] = {
            "ranks": {ev: rank_tables[ev][m] for ev in EVALUATOR_NAMES},
            "min_rank": min(model_ranks),
            "max_rank": max(model_ranks),
            "depth": depth,
        }
        if depth > worst_depth:
            worst_depth = depth
            worst_model = m

    # Per-pair detail
    pair_details: list[dict[str, Any]] = []
    for (ev_a, ev_b), rho, jac, kd in zip(eval_pairs, spearman_rhos, jaccard_scores, kendall_distances):
        pair_details.append(
            {
                "evaluator_a": ev_a,
                "evaluator_b": ev_b,
                "spearman_rho": round(rho, 4),
                "top3_jaccard": round(jac, 4),
                "kendall_dist_normalized": round(kd, 4),
            }
        )

    return {
        "n_models": n_models,
        "n_evaluators": len(EVALUATOR_NAMES),
        "n_evaluator_pairs": len(eval_pairs),
        "evaluators": EVALUATOR_NAMES,
        "models": models,
        "rank_tables": {ev: rank_tables[ev] for ev in EVALUATOR_NAMES},
        "pass_rates": {m: {ev: round(model_pass_rates[m][ev] * 100, 2) for ev in EVALUATOR_NAMES} for m in models},
        "mean_pairwise_spearman_rho": round(mean_spearman, 4),
        "mean_top3_jaccard": round(mean_jaccard, 4),
        "mean_kendall_dist_normalized": round(mean_kendall_dist, 4),
        "n_rank_reversals": reversals,
        "total_model_pairs": n_models * (n_models - 1) // 2,
        "worst_case_reversal_depth": worst_depth,
        "worst_case_model": worst_model,
        "per_model_rank_range": per_model_rank_range,
        "pair_details": pair_details,
        "reversed_model_pairs": [list(p) for p in reversed_pairs],
    }


# ---------------------------------------------------------------------------
# Bootstrap rank CI (per model, averaged across evaluators)
# ---------------------------------------------------------------------------


def compute_rank_ci_widths(
    scored: list[dict[str, Any]],
    model_pass_rates: dict[str, dict[str, float]],
) -> dict[str, dict[str, float]]:
    """Compute per-model 95% rank CI width for each evaluator.

    Returns:
        model -> evaluator -> ci_width
    """
    by_model: dict[str, list[dict[str, Any]]] = {}
    for r in scored:
        m = r.get("model", "")
        if m in COMPLETE_MODELS:
            by_model.setdefault(m, []).append(r)

    ci_widths: dict[str, dict[str, float]] = {}
    for model in sorted(COMPLETE_MODELS):
        records = by_model.get(model, [])
        ci_widths[model] = {}
        for ev in EVALUATOR_NAMES:
            width = bootstrap_rank_ci_width(
                records_for_model=records,
                target_model=model,
                evaluator=ev,
                all_model_rates=model_pass_rates,
                n_bootstrap=N_BOOTSTRAP,
                seed=SEED,
            )
            ci_widths[model][ev] = width
    return ci_widths


# ---------------------------------------------------------------------------
# LaTeX macros
# ---------------------------------------------------------------------------


def write_macros(results: dict[str, Any], output_dir: Path) -> None:
    """Write LaTeX macros file for CRES-12 results."""
    spearman = results["mean_pairwise_spearman_rho"]
    jaccard = results["mean_top3_jaccard"]
    kendall = results["mean_kendall_dist_normalized"]
    reversals = results["n_rank_reversals"]
    max_depth = results["worst_case_reversal_depth"]

    lines = [
        "% CRES-12: Rank-Reversal Multi-Metric Macros",
        "% Auto-generated by exp_cres_12_rank_reversal.py",
        "",
        f"\\newcommand{{\\cresTwelveSpearman}}{{{spearman:.3f}}}",
        f"\\newcommand{{\\cresTwelveJaccard}}{{{jaccard:.3f}}}",
        f"\\newcommand{{\\cresTwelveKendall}}{{{kendall:.3f}}}",
        f"\\newcommand{{\\cresTwelveReversals}}{{{reversals}}}",
        f"\\newcommand{{\\cresTwelveMaxDepth}}{{{max_depth}}}",
        "",
    ]

    macro_path = output_dir / "cres_12_macros.tex"
    macro_path.parent.mkdir(parents=True, exist_ok=True)
    macro_path.write_text("\n".join(lines))
    print(f"  Saved: {macro_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 60)
    print("CRES-12: Rank-Reversal Multi-Metric")
    print("=" * 60)

    # Load episodes and verdicts
    print("\nLoading episodes and verdicts...")
    _episodes, scored = load_cached_verdicts()
    print(f"  Loaded {len(scored)} scored records")

    # Compute per-model pass rates
    print("\nComputing per-model pass rates...")
    model_pass_rates = compute_model_pass_rates(scored)
    for m in sorted(model_pass_rates):
        rates_str = ", ".join(f"{ev}: {model_pass_rates[m][ev] * 100:.1f}%" for ev in EVALUATOR_NAMES)
        print(f"  {MODEL_LABELS.get(m, m)}: {rates_str}")

    # Compute rank reversal metrics
    print("\nComputing rank reversal metrics...")
    metrics = compute_rank_reversal_metrics(model_pass_rates)

    print(f"\n  Mean pairwise Spearman rho:   {metrics['mean_pairwise_spearman_rho']:.4f}")
    print(f"  Mean top-3 Jaccard:            {metrics['mean_top3_jaccard']:.4f}")
    print(f"  Mean Kendall tau dist (norm):  {metrics['mean_kendall_dist_normalized']:.4f}")
    print(f"  Rank reversals:                {metrics['n_rank_reversals']} / {metrics['total_model_pairs']} pairs")
    print(f"  Worst-case reversal depth:     {metrics['worst_case_reversal_depth']} ranks")
    print(f"  Worst-case model:              {metrics['worst_case_model']}")

    # Rank CI widths (bootstrap)
    print("\nBootstrapping per-model rank CI widths...")
    ci_widths = compute_rank_ci_widths(scored, model_pass_rates)
    metrics["per_model_rank_ci_width"] = ci_widths

    # Mean CI width across models and evaluators
    all_widths = [w for m_widths in ci_widths.values() for w in m_widths.values()]
    metrics["mean_rank_ci_width"] = round(float(np.mean(all_widths)), 3) if all_widths else 0.0
    print(f"  Mean rank 95% CI width: {metrics['mean_rank_ci_width']:.3f}")

    # Save JSON
    output_dir = OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)
    save_json(metrics, output_dir / "cres_12_results.json")

    # Write LaTeX macros
    write_macros(metrics, output_dir)

    print("\n" + "=" * 60)
    print("CRES-12 COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
