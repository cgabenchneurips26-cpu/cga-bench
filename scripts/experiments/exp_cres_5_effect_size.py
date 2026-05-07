#!/usr/bin/env python3
"""CRES-5: Effect Size Multi-Metric Experiment (NeurIPS Rebuttal Defense).

Computes multiple effect size metrics quantifying evaluator disagreement
magnitude, all with bootstrap 95% CIs.

Metrics computed:
  a. Cohen's f2 from eta2(evaluator)
  b. Cliff's delta: CGA-Bench vs AC-Proxy episode-level verdicts
  c. Variance Partition Coefficient (VPC): analogous to ICC
  d. Rank-biserial correlation r: TCC verdict vs coverage score
  e. Null-calibrated ratio: observed eta2 / mean(permuted eta2)
  f. eta2(evaluator): sanity-check reproduction of 0.284
  g. eta2(run): sanity-check reproduction of 0.0091

Outputs:
  evidence_pack/cres_5/cres_5_results.json
  evidence_pack/cres_5/cres_5_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/exp_cres_5_effect_size.py
"""

from __future__ import annotations

from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from collections import defaultdict
from typing import Any

import numpy as np
from scipy import stats
from scripts.experiments._common import save_json
from scripts.experiments._episode_cache import EVIDENCE_DIR, load_cached_verdicts

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTPUT_DIR = EVIDENCE_DIR / "cres_5"
N_BOOTSTRAP = 10_000
N_PERMUTATIONS = 10_000
SEED = 42

EVALUATOR_KEYS = ["ac_proxy", "mab_proxy", "c2_pass", "cga_pass"]
EVALUATOR_NAMES = ["AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]


# ---------------------------------------------------------------------------
# eta2 computation helpers
# ---------------------------------------------------------------------------


def _build_verdict_matrix(records: list[dict[str, Any]]) -> np.ndarray:
    """Build (n_episodes x n_evaluators) binary verdict matrix.

    Returns float array shape (N, 4) with columns [ac, mab, c2, cga].
    """
    n = len(records)
    k = len(EVALUATOR_KEYS)
    mat = np.zeros((n, k), dtype=float)
    for i, rec in enumerate(records):
        for j, key in enumerate(EVALUATOR_KEYS):
            mat[i, j] = 1.0 if rec[key] else 0.0
    return mat


def _compute_eta2_evaluator(mat: np.ndarray) -> float:
    """Compute eta2(evaluator) from verdict matrix (N x K).

    SS_eval = N * sum_k (eval_mean_k - grand_mean)^2
    SS_total = sum over all cells (x_ij - grand_mean)^2
    eta2 = SS_eval / SS_total
    """
    n, k = mat.shape
    grand_mean = float(np.mean(mat))
    eval_means = mat.mean(axis=0)  # shape (K,)

    ss_eval = n * float(np.sum((eval_means - grand_mean) ** 2))
    ss_total = float(np.sum((mat - grand_mean) ** 2))

    return ss_eval / ss_total if ss_total > 0 else 0.0


def _compute_eta2_run(records: list[dict[str, Any]], mat: np.ndarray) -> float:
    """Compute eta2(run): within-(scenario, model) run variance.

    For each (scenario, model) group, compute within-group variance
    using CGA-Bench (cga_pass) as the outcome.  SS_run = sum of
    squared deviations from group means.  SS_total uses grand mean
    over all cga values.
    """
    cga_vals = mat[:, 3]  # cga_pass column
    grand_mean = float(np.mean(cga_vals))
    ss_total = float(np.sum((cga_vals - grand_mean) ** 2))

    run_groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for i, rec in enumerate(records):
        key = (rec.get("scenario_id", ""), rec.get("model", ""))
        run_groups[key].append(float(cga_vals[i]))

    ss_run = 0.0
    for vals in run_groups.values():
        if len(vals) >= 2:
            gm = np.mean(vals)
            ss_run += sum((v - gm) ** 2 for v in vals)

    return ss_run / ss_total if ss_total > 0 else 0.0


# ---------------------------------------------------------------------------
# Metric a: Cohen's f2 from eta2
# ---------------------------------------------------------------------------


def compute_cohens_f2(eta2: float) -> float:
    """f2 = eta2 / (1 - eta2)."""
    return eta2 / (1.0 - eta2) if eta2 < 1.0 else float("inf")


# ---------------------------------------------------------------------------
# Metric b: Cliff's delta
# ---------------------------------------------------------------------------


def compute_cliffs_delta(x: np.ndarray, y: np.ndarray) -> float:
    """Cliff's delta comparing two binary arrays episode-by-episode.

    Treats each episode as a pair (x_i, y_i).
    delta = (n_concordant - n_discordant) / n_pairs
    where concordant = x_i > y_i, discordant = x_i < y_i.
    """
    n = len(x)
    if n == 0:
        return 0.0
    concordant = int(np.sum(x > y))
    discordant = int(np.sum(x < y))
    return (concordant - discordant) / n


def cliffs_delta_stat(data: np.ndarray) -> float:
    """Statistic fn for bootstrap: data is stacked (N, 2) array."""
    x = data[:, 0]
    y = data[:, 1]
    return compute_cliffs_delta(x, y)


# ---------------------------------------------------------------------------
# Metric c: Variance Partition Coefficient (VPC)
# ---------------------------------------------------------------------------


def compute_vpc(mat: np.ndarray) -> float:
    """VPC_evaluator = var(evaluator means) / total variance.

    Analogous to ICC at the evaluator level.
    var(evaluator_means): variance of the K column means
    var(within_evaluator): mean within-evaluator variance
    VPC = var_between / (var_between + var_within)
    """
    eval_means = mat.mean(axis=0)  # (K,)
    var_between = float(np.var(eval_means, ddof=0))

    # Within-evaluator variance: mean of per-column variances
    within_vars = np.var(mat, axis=0, ddof=0)  # (K,)
    var_within = float(np.mean(within_vars))

    denom = var_between + var_within
    return var_between / denom if denom > 0 else 0.0


def vpc_stat(data: np.ndarray) -> float:
    """Statistic fn for bootstrap: data is (N, K) verdict matrix."""
    return compute_vpc(data)


# ---------------------------------------------------------------------------
# Metric d: Rank-biserial correlation r
# ---------------------------------------------------------------------------


def compute_rank_biserial(binary_verdict: np.ndarray, continuous_score: np.ndarray) -> float:
    """Rank-biserial correlation between binary TCC verdict and coverage score.

    r_rb = 2 * (mean_rank_pass - mean_rank_fail) / n
    Uses overall rank of continuous_score, then compares mean ranks
    between pass and fail groups.
    """
    n = len(binary_verdict)
    if n == 0:
        return 0.0

    # Rank the continuous scores (1-indexed, average ties)
    ranks = stats.rankdata(continuous_score)

    pass_mask = binary_verdict == 1
    fail_mask = binary_verdict == 0

    if not np.any(pass_mask) or not np.any(fail_mask):
        return 0.0

    mean_rank_pass = float(np.mean(ranks[pass_mask]))
    mean_rank_fail = float(np.mean(ranks[fail_mask]))

    return 2.0 * (mean_rank_pass - mean_rank_fail) / n


def rank_biserial_stat(data: np.ndarray) -> float:
    """Statistic fn for bootstrap: data is (N, 2), col0=verdict, col1=score."""
    return compute_rank_biserial(data[:, 0], data[:, 1])


# ---------------------------------------------------------------------------
# Metric e: Null-calibrated ratio via permutation
# ---------------------------------------------------------------------------


def compute_null_ratio(
    mat: np.ndarray,
    observed_eta2: float,
    n_permutations: int = N_PERMUTATIONS,
    seed: int = SEED,
) -> dict[str, float]:
    """Run permutation test: shuffle evaluator labels within each episode.

    For each permutation, randomly permute the K verdict columns within
    each row (episode), then recompute eta2(evaluator).

    Returns:
        null_ratio: observed / mean(permuted)
        null_ci_lo: 2.5th percentile of null distribution
        null_ci_hi: 97.5th percentile of null distribution
        null_mean: mean of permuted eta2 values
        null_std: std of permuted eta2 values
    """
    rng = np.random.default_rng(seed)
    n, k = mat.shape

    null_eta2_values = np.zeros(n_permutations)
    for i in range(n_permutations):
        # Permute evaluator column assignments within each episode
        perm_mat = mat.copy()
        idx = rng.permuted(np.arange(k) * np.ones((n, k), dtype=int), axis=1)
        perm_mat = mat[np.arange(n)[:, None], idx]
        null_eta2_values[i] = _compute_eta2_evaluator(perm_mat)

    null_mean = float(np.mean(null_eta2_values))
    null_std = float(np.std(null_eta2_values, ddof=1))
    null_ci_lo = float(np.percentile(null_eta2_values, 2.5))
    null_ci_hi = float(np.percentile(null_eta2_values, 97.5))
    null_ratio = observed_eta2 / null_mean if null_mean > 0 else float("inf")

    return {
        "null_ratio": round(null_ratio, 2),
        "null_mean": round(null_mean, 6),
        "null_std": round(null_std, 6),
        "null_ci_lo": round(null_ci_lo, 6),
        "null_ci_hi": round(null_ci_hi, 6),
        "null_n_permutations": n_permutations,
    }


# ---------------------------------------------------------------------------
# LaTeX macro helpers
# ---------------------------------------------------------------------------


def _fmt3(x: float) -> str:
    return f"{x:.3f}"


def _fmt2(x: float) -> str:
    return f"{x:.2f}"


def _fmt4(x: float) -> str:
    return f"{x:.4f}"


def write_macros(results: dict[str, Any], path: Path) -> None:
    """Write LaTeX macros for CRES-5 metrics."""
    path.parent.mkdir(parents=True, exist_ok=True)

    eta2 = results["eta2_evaluator"]["value"]
    eta2_lo, eta2_hi = results["eta2_evaluator"]["ci_95"]

    f2 = results["cohens_f2"]["value"]
    f2_lo, f2_hi = results["cohens_f2"]["ci_95"]

    delta = results["cliffs_delta"]["value"]
    delta_lo, delta_hi = results["cliffs_delta"]["ci_95"]

    vpc = results["vpc"]["value"]
    vpc_lo, vpc_hi = results["vpc"]["ci_95"]

    rb = results["rank_biserial"]["value"]
    rb_lo, rb_hi = results["rank_biserial"]["ci_95"]

    null_ratio = results["null_calibrated_ratio"]["null_ratio"]
    null_lo = results["null_calibrated_ratio"]["null_ci_lo"]
    null_hi = results["null_calibrated_ratio"]["null_ci_hi"]

    eta2_run = results["eta2_run"]["value"]

    lines = [
        r"% CRES-5: Effect Size Multi-Metric Macros",
        r"% Auto-generated by exp_cres_5_effect_size.py",
        "",
        rf"\newcommand{{\cresFiveEtaSq}}{{{_fmt3(eta2)}}}",
        rf"\newcommand{{\cresFiveEtaSqCI}}{{{_fmt3(eta2_lo)}--{_fmt3(eta2_hi)}}}",
        rf"\newcommand{{\cresFiveEtaRun}}{{{_fmt4(eta2_run)}}}",
        "",
        rf"\newcommand{{\cresFiveCohenF}}{{{_fmt3(f2)}}}",
        rf"\newcommand{{\cresFiveCohenFCI}}{{{_fmt3(f2_lo)}--{_fmt3(f2_hi)}}}",
        "",
        rf"\newcommand{{\cresFiveCliffDelta}}{{{_fmt3(delta)}}}",
        rf"\newcommand{{\cresFiveCliffDeltaCI}}{{{_fmt3(delta_lo)}--{_fmt3(delta_hi)}}}",
        "",
        rf"\newcommand{{\cresFiveVPC}}{{{_fmt3(vpc)}}}",
        rf"\newcommand{{\cresFiveVPCCI}}{{{_fmt3(vpc_lo)}--{_fmt3(vpc_hi)}}}",
        "",
        rf"\newcommand{{\cresFiveRankBiserial}}{{{_fmt3(rb)}}}",
        rf"\newcommand{{\cresFiveRankBiserialCI}}{{{_fmt3(rb_lo)}--{_fmt3(rb_hi)}}}",
        "",
        rf"\newcommand{{\cresFiveNullRatio}}{{{_fmt2(null_ratio)}}}",
        rf"\newcommand{{\cresFiveNullRatioCI}}{{{_fmt4(null_lo)}--{_fmt4(null_hi)}}}",
        "",
    ]

    with open(path, "w") as f:
        f.write("\n".join(lines))
    print(f"  Saved: {path}")


# ---------------------------------------------------------------------------
# Bootstrap wrappers using _common.bootstrap_ci
# ---------------------------------------------------------------------------


def _bootstrap_scalar(
    data: np.ndarray,
    stat_fn: Any,
    n_bootstrap: int = N_BOOTSTRAP,
    seed: int = SEED,
) -> tuple[float, float]:
    """Bootstrap CI for a scalar statistic on 1-D or 2-D data."""
    rng = np.random.default_rng(seed)
    n = len(data)
    if n == 0:
        return (0.0, 0.0)
    boot_stats = np.array([stat_fn(data[rng.integers(0, n, size=n)]) for _ in range(n_bootstrap)])
    lo = float(np.percentile(boot_stats, 2.5))
    hi = float(np.percentile(boot_stats, 97.5))
    return (lo, hi)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run CRES-5 effect size computation."""
    print("CRES-5: Effect Size Multi-Metric")
    print("=" * 50)

    # Load episodes and verdicts
    print("\nLoading episodes...")
    _episodes, records = load_cached_verdicts()
    print(f"  N episodes: {len(records)}")

    # Build verdict matrix (N x 4)
    mat = _build_verdict_matrix(records)
    n, k = mat.shape
    print(f"  Verdict matrix: {n} x {k}")

    results: dict[str, Any] = {"n_episodes": n, "n_evaluators": k}

    # ------------------------------------------------------------------
    # f) & g) Reproduce eta2(evaluator) and eta2(run) as sanity checks
    # ------------------------------------------------------------------
    print("\nComputing eta2(evaluator) and eta2(run)...")

    observed_eta2_eval = _compute_eta2_evaluator(mat)
    observed_eta2_run = _compute_eta2_run(records, mat)
    print(f"  eta2(evaluator) = {observed_eta2_eval:.4f}  (expected ~0.284)")
    print(f"  eta2(run)       = {observed_eta2_run:.4f}  (expected ~0.0091)")

    # Bootstrap CI for eta2(evaluator)
    def eta2_eval_stat(sample_mat: np.ndarray) -> float:
        return _compute_eta2_evaluator(sample_mat)

    eta2_eval_ci = _bootstrap_scalar(mat, eta2_eval_stat)

    # Bootstrap CI for eta2(run): need records too; approximate via mat only
    # For run CI, resample episodes and recompute
    records_arr = np.array(records, dtype=object)

    def eta2_run_stat_full(idx_sample: np.ndarray) -> float:
        sample_records = [records[i] for i in idx_sample]
        sample_mat = _build_verdict_matrix(sample_records)
        return _compute_eta2_run(sample_records, sample_mat)

    rng_run = np.random.default_rng(SEED)
    run_boot = np.array([eta2_run_stat_full(rng_run.integers(0, n, size=n)) for _ in range(N_BOOTSTRAP)])
    eta2_run_ci = (float(np.percentile(run_boot, 2.5)), float(np.percentile(run_boot, 97.5)))

    results["eta2_evaluator"] = {
        "value": round(observed_eta2_eval, 4),
        "ci_95": (round(eta2_eval_ci[0], 4), round(eta2_eval_ci[1], 4)),
        "expected": 0.284,
        "description": "Proportion of total verdict variance explained by evaluator choice",
    }
    results["eta2_run"] = {
        "value": round(observed_eta2_run, 4),
        "ci_95": (round(eta2_run_ci[0], 4), round(eta2_run_ci[1], 4)),
        "expected": 0.0091,
        "description": "Proportion of total verdict variance explained by run-to-run noise",
    }

    # ------------------------------------------------------------------
    # a) Cohen's f2 from eta2(evaluator)
    # ------------------------------------------------------------------
    print("\nComputing Cohen's f2...")

    observed_f2 = compute_cohens_f2(observed_eta2_eval)

    def f2_stat(sample_mat: np.ndarray) -> float:
        return compute_cohens_f2(_compute_eta2_evaluator(sample_mat))

    f2_ci = _bootstrap_scalar(mat, f2_stat)

    print(f"  f2 = {observed_f2:.4f}")
    results["cohens_f2"] = {
        "value": round(observed_f2, 4),
        "ci_95": (round(f2_ci[0], 4), round(f2_ci[1], 4)),
        "interpretation": (
            "large (>0.35)" if observed_f2 > 0.35 else "medium (>0.15)" if observed_f2 > 0.15 else "small"
        ),
        "description": "Cohen's f2 = eta2 / (1 - eta2); measures effect size of evaluator choice",
    }

    # ------------------------------------------------------------------
    # b) Cliff's delta: CGA-Bench (cga_pass) vs AC-Proxy (ac_proxy)
    # ------------------------------------------------------------------
    print("\nComputing Cliff's delta (CGA vs AC-Proxy)...")

    cga_arr = mat[:, 3]  # cga_pass
    ac_arr = mat[:, 0]  # ac_proxy
    paired_data = np.column_stack([cga_arr, ac_arr])

    observed_delta = compute_cliffs_delta(cga_arr, ac_arr)

    f2_ci_delta = _bootstrap_scalar(paired_data, cliffs_delta_stat)

    print(f"  Cliff's delta = {observed_delta:.4f}")
    results["cliffs_delta"] = {
        "value": round(observed_delta, 4),
        "ci_95": (round(f2_ci_delta[0], 4), round(f2_ci_delta[1], 4)),
        "comparison": "CGA-Bench vs AC-Proxy (episode-paired)",
        "description": (
            "Cliff's delta = (n_concordant - n_discordant) / n; positive = CGA passes more episodes than AC-Proxy"
        ),
    }

    # ------------------------------------------------------------------
    # c) VPC (Variance Partition Coefficient)
    # ------------------------------------------------------------------
    print("\nComputing VPC...")

    observed_vpc = compute_vpc(mat)

    vpc_ci = _bootstrap_scalar(mat, vpc_stat)

    print(f"  VPC = {observed_vpc:.4f}")
    results["vpc"] = {
        "value": round(observed_vpc, 4),
        "ci_95": (round(vpc_ci[0], 4), round(vpc_ci[1], 4)),
        "description": (
            "Variance Partition Coefficient: var(evaluator_means) / "
            "(var(evaluator_means) + mean(within_evaluator_var)); analogous to ICC"
        ),
    }

    # ------------------------------------------------------------------
    # d) Rank-biserial correlation: CGA verdict vs coverage score
    # ------------------------------------------------------------------
    print("\nComputing rank-biserial correlation...")

    cga_binary = mat[:, 3]  # cga_pass
    coverage_scores = np.array([r.get("coverage", 0.0) for r in records], dtype=float)
    rb_data = np.column_stack([cga_binary, coverage_scores])

    observed_rb = compute_rank_biserial(cga_binary, coverage_scores)

    rb_ci = _bootstrap_scalar(rb_data, rank_biserial_stat)

    print(f"  Rank-biserial r = {observed_rb:.4f}")
    results["rank_biserial"] = {
        "value": round(observed_rb, 4),
        "ci_95": (round(rb_ci[0], 4), round(rb_ci[1], 4)),
        "comparison": "CGA-Bench binary verdict vs continuous action-coverage score",
        "description": (
            "r_rb = 2*(mean_rank_pass - mean_rank_fail) / n; "
            "measures association between TCC verdict and AC-Proxy's continuous score"
        ),
    }

    # ------------------------------------------------------------------
    # e) Null-calibrated ratio via permutation test
    # ------------------------------------------------------------------
    print(f"\nRunning {N_PERMUTATIONS} permutations for null-calibrated ratio...")

    null_results = compute_null_ratio(mat, observed_eta2_eval, N_PERMUTATIONS, SEED)
    print(f"  null_ratio = {null_results['null_ratio']:.2f}x")
    print(f"  null mean eta2 = {null_results['null_mean']:.6f}")

    results["null_calibrated_ratio"] = {
        **null_results,
        "observed_eta2": round(observed_eta2_eval, 4),
        "description": (
            "observed_eta2 / mean(permuted_eta2) where permutation shuffles evaluator labels within each episode"
        ),
    }

    # ------------------------------------------------------------------
    # Save results JSON
    # ------------------------------------------------------------------
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    results_path = OUTPUT_DIR / "cres_5_results.json"
    save_json(results, results_path)

    # ------------------------------------------------------------------
    # Save LaTeX macros
    # ------------------------------------------------------------------
    macros_path = OUTPUT_DIR / "cres_5_macros.tex"
    write_macros(results, macros_path)

    # ------------------------------------------------------------------
    # Print summary table
    # ------------------------------------------------------------------
    print("\n" + "=" * 60)
    print("CRES-5 SUMMARY TABLE")
    print("=" * 60)
    print(f"{'Metric':<35} {'Value':>10}  {'95% CI'}")
    print("-" * 60)

    def _ci_str(lo: float, hi: float, decimals: int = 3) -> str:
        fmt = f".{decimals}f"
        return f"[{lo:{fmt}}, {hi:{fmt}}]"

    rows = [
        (
            "eta2(evaluator)",
            results["eta2_evaluator"]["value"],
            results["eta2_evaluator"]["ci_95"],
        ),
        (
            "eta2(run)",
            results["eta2_run"]["value"],
            results["eta2_run"]["ci_95"],
        ),
        (
            "Cohen's f2",
            results["cohens_f2"]["value"],
            results["cohens_f2"]["ci_95"],
        ),
        (
            "Cliff's delta (CGA vs AC)",
            results["cliffs_delta"]["value"],
            results["cliffs_delta"]["ci_95"],
        ),
        (
            "VPC (evaluator)",
            results["vpc"]["value"],
            results["vpc"]["ci_95"],
        ),
        (
            "Rank-biserial r",
            results["rank_biserial"]["value"],
            results["rank_biserial"]["ci_95"],
        ),
        (
            "Null-calibrated ratio",
            results["null_calibrated_ratio"]["null_ratio"],
            (
                results["null_calibrated_ratio"]["null_ci_lo"],
                results["null_calibrated_ratio"]["null_ci_hi"],
            ),
        ),
    ]

    for name, val, ci in rows:
        lo, hi = ci
        print(f"  {name:<33} {val:>10.4f}  {_ci_str(lo, hi)}")

    print("=" * 60)
    print(f"\nOutputs written to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
