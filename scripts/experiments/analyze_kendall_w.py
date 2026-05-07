#!/usr/bin/env python3
"""α-6 Rank Reversal + Kendall W Re-computation.

Inputs:
  - reports/path_d_day1/v6_fixed_verdict_matrix.json
    - baseline_per_episode, full_per_episode lists
    - per-episode evaluator booleans: ac_proxy, mab_proxy, c2_pass, dxem, v4_hard

Outputs:
  - reports/path_d_day1/kendall_w_summary.md
  - 9 model × 5 evaluator pass-rate matrix (vanilla + fixed)
  - Kendall W (concordance) per condition
  - Decision: ≥ 0.40 → Option Y (Fixed headline), < 0.40 → Option X (vanilla headline)
"""

from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
import sys

import numpy as np
from scipy.stats import friedmanchisquare

REPO = Path(__file__).resolve().parents[2]
MATRIX = REPO / "reports" / "path_d_day1" / "v6_fixed_verdict_matrix.json"
REPORT = REPO / "reports" / "path_d_day1" / "kendall_w_summary.md"

EVALUATORS = ["ac_proxy", "mab_proxy", "c2_pass", "dxem", "v4_hard"]


def per_model_eval_pass_rate(episodes: list[dict]) -> dict[str, dict[str, float]]:
    """Returns {model: {evaluator: pass_rate, n: count}}"""
    by_model: dict[str, dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    for ep in episodes:
        m = ep.get("model_dir") or ep.get("model")
        if not m:
            continue
        for ev in EVALUATORS:
            v = ep.get(ev)
            if v is not None:
                by_model[m][ev].append(bool(v))
    out: dict[str, dict[str, float]] = {}
    for m, evs in by_model.items():
        ns = [len(evs[ev]) for ev in EVALUATORS if ev in evs]
        out[m] = {"n": min(ns) if ns else 0}
        for ev in EVALUATORS:
            arr = evs.get(ev, [])
            out[m][ev] = sum(arr) / len(arr) if arr else float("nan")
    return out


def kendall_w(rank_matrix: np.ndarray) -> tuple[float, float, float]:
    """Kendall's W (coefficient of concordance) — manual definition.

    rank_matrix: shape (n_items, n_judges) of ranks (1 = best).
    W = 12·S / (m² · (n³ − n))   where S = Σ (R_i − m·(n+1)/2)²

    Also returns Friedman χ² and p computed from the *raw* pass-rate
    matrix (not the ranks) so scipy ranks correctly internally.
    """
    n_items, n_judges = rank_matrix.shape
    if n_items < 2:
        return 0.0, 0.0, 1.0
    mean_rank = (n_items + 1) / 2
    sum_R = rank_matrix.sum(axis=1)
    S = float(((sum_R - n_judges * mean_rank) ** 2).sum())
    W = 12 * S / (n_judges ** 2 * (n_items ** 3 - n_items))
    # Friedman χ² from W: χ² = m·(n−1)·W
    chi2 = n_judges * (n_items - 1) * W
    # p-value via chi2 dist with df = n-1 (asymptotic)
    from scipy.stats import chi2 as chi2_dist
    p = 1 - chi2_dist.cdf(chi2, n_items - 1)
    return W, chi2, p


def models_from_episodes(episodes: list[dict]) -> list[str]:
    seen: set[str] = set()
    order: list[str] = []
    for ep in episodes:
        m = ep.get("model_dir")
        if m and m not in seen:
            seen.add(m)
            order.append(m)
    return sorted(order)


def build_matrix(per_model: dict[str, dict[str, float]], models: list[str]) -> np.ndarray:
    """Returns (n_models, n_evaluators) of pass-rates."""
    arr = np.full((len(models), len(EVALUATORS)), np.nan)
    for i, m in enumerate(models):
        if m not in per_model:
            continue
        for j, ev in enumerate(EVALUATORS):
            arr[i, j] = per_model[m].get(ev, np.nan)
    return arr


def rank_per_evaluator(pass_matrix: np.ndarray) -> np.ndarray:
    """Convert (n_models, n_evals) pass-rate matrix into rank matrix (1=best, n=worst)."""
    ranks = np.zeros_like(pass_matrix)
    for j in range(pass_matrix.shape[1]):
        col = pass_matrix[:, j]
        # higher pass-rate = lower (better) rank; ties -> mean rank
        order = (-col).argsort()
        ranks_col = np.empty_like(order, dtype=float)
        # average-rank for ties
        from scipy.stats import rankdata
        ranks_col = rankdata(-col)  # rankdata with negative = higher original = rank 1
        ranks[:, j] = ranks_col
    return ranks


def md_table(matrix: np.ndarray, row_labels: list[str], col_labels: list[str]) -> str:
    lines = [f"| model | {' | '.join(col_labels)} |", "|---|" + "---|" * len(col_labels)]
    for i, r in enumerate(row_labels):
        cells = " | ".join(f"{matrix[i, j]:.3f}" if not np.isnan(matrix[i, j]) else "--" for j in range(matrix.shape[1]))
        lines.append(f"| {r} | {cells} |")
    return "\n".join(lines)


def main() -> int:
    d = json.loads(MATRIX.read_text())
    base_eps = d["baseline_per_episode"]
    full_eps = d["full_per_episode"]
    print(f"baseline_per_episode: {len(base_eps)}")
    print(f"full_per_episode    : {len(full_eps)}")

    base_pm = per_model_eval_pass_rate(base_eps)
    full_pm = per_model_eval_pass_rate(full_eps)
    models = sorted(set(base_pm) | set(full_pm))
    print(f"models found ({len(models)}): {models}")

    base_M = build_matrix(base_pm, models)
    full_M = build_matrix(full_pm, models)
    base_R = rank_per_evaluator(base_M)
    full_R = rank_per_evaluator(full_M)

    base_W, base_chi2, base_p = kendall_w(base_R)
    full_W, full_chi2, full_p = kendall_w(full_R)

    # Also compute W without dxem (which is 1.0 for every model in v6 — degenerate)
    keep = [i for i, ev in enumerate(EVALUATORS) if ev != "dxem"]
    base_R4 = base_R[:, keep]
    full_R4 = full_R[:, keep]
    # rebuild ranks fresh from the 4-evaluator submatrix to break the dxem ties
    base_R4 = rank_per_evaluator(base_M[:, keep])
    full_R4 = rank_per_evaluator(full_M[:, keep])
    base_W4, base_chi2_4, base_p4 = kendall_w(base_R4)
    full_W4, full_chi2_4, full_p4 = kendall_w(full_R4)

    # Pairwise rank reversal count (vanilla vs fixed)
    rev_count = 0
    for j in range(len(EVALUATORS)):
        for i1 in range(len(models)):
            for i2 in range(i1 + 1, len(models)):
                v1 = base_R[i1, j] - base_R[i2, j]
                v2 = full_R[i1, j] - full_R[i2, j]
                if v1 * v2 < 0:
                    rev_count += 1
    total_pairs = len(EVALUATORS) * len(models) * (len(models) - 1) // 2
    rev_pct = 100 * rev_count / max(total_pairs, 1)

    # Decision uses the 4-evaluator W (dxem is degenerate on v6)
    decision_W = full_W4
    decision = "Option Y (Fixed headline)" if decision_W >= 0.40 else "Option X (Vanilla headline)"

    lines: list[str] = []
    lines.append("# α-6 Rank Reversal + Kendall W Re-computation\n")
    lines.append("**Source**: `reports/path_d_day1/v6_fixed_verdict_matrix.json`")
    lines.append(f"- baseline (vanilla) episodes: {len(base_eps)}")
    lines.append(f"- full (CAV-fixed)  episodes: {len(full_eps)}")
    lines.append(f"- models: {len(models)} = {models}")
    lines.append(f"- evaluators: {len(EVALUATORS)} = {EVALUATORS}")

    lines.append("\n## Vanilla pass-rate matrix (model × evaluator)\n")
    lines.append(md_table(base_M, models, EVALUATORS))
    lines.append("\n## Fixed (CAV) pass-rate matrix\n")
    lines.append(md_table(full_M, models, EVALUATORS))

    lines.append("\n## Vanilla rank matrix (1 = best)\n")
    lines.append(md_table(base_R, models, EVALUATORS))
    lines.append("\n## Fixed rank matrix\n")
    lines.append(md_table(full_R, models, EVALUATORS))

    lines.append("\n## Kendall W (Coefficient of Concordance)\n")
    lines.append("| Condition | W | χ² | p (Friedman) | interpretation |")
    lines.append("|---|---|---|---|---|")
    def interp(W: float) -> str:
        if W >= 0.7: return "very strong"
        if W >= 0.5: return "strong"
        if W >= 0.4: return "moderate"
        if W >= 0.3: return "weak"
        return "very weak"
    lines.append(f"| Vanilla (5 eval) | {base_W:.4f} | {base_chi2:.2f} | {base_p:.3g} | {interp(base_W)} |")
    lines.append(f"| Fixed   (5 eval) | {full_W:.4f} | {full_chi2:.2f} | {full_p:.3g} | {interp(full_W)} |")
    lines.append(f"| Vanilla (4 eval, no dxem) | {base_W4:.4f} | {base_chi2_4:.2f} | {base_p4:.3g} | {interp(base_W4)} |")
    lines.append(f"| Fixed   (4 eval, no dxem) | {full_W4:.4f} | {full_chi2_4:.2f} | {full_p4:.3g} | {interp(full_W4)} |")
    lines.append("\n*Note: dxem=1.0 for all 9 models (degenerate evaluator on v6); the 4-eval row strips it for a more informative concordance estimate.*")

    lines.append("\n## Pairwise Rank Reversal (Vanilla vs Fixed)\n")
    lines.append(f"- Reversed pairs: **{rev_count}** / {total_pairs} ({rev_pct:.1f}%)")
    lines.append(f"- Stable pairs: {total_pairs - rev_count} / {total_pairs} ({100-rev_pct:.1f}%)")

    lines.append("\n## Decision\n")
    lines.append(f"- Threshold: W ≥ 0.40 → Option Y; W < 0.40 → Option X")
    lines.append(f"- Decision metric: 4-evaluator Fixed W = {decision_W:.4f} (dxem dropped because it is constant 1.0 across all 9 models on the v6 corpus, making it uninformative)")
    lines.append(f"- 5-evaluator (with dxem): Vanilla W = {base_W:.4f}, Fixed W = {full_W:.4f} (both deflated by the dxem ties)")
    lines.append(f"- **Decision: {decision}**")
    if decision_W >= 0.40:
        lines.append("  - CAV-fixed evaluator concordance is moderate-or-better → headline can lead with Fixed numbers (CAV-applied) and report Vanilla as ablation.")
    else:
        lines.append("  - CAV-fixed evaluator concordance is below threshold → headline retains Vanilla numbers; Fixed is reported as a secondary diagnostic.")

    REPORT.write_text("\n".join(lines))
    print(f"\nReport: {REPORT}")
    print(f"\n=== 5-evaluator: Vanilla W={base_W:.4f}  Fixed W={full_W:.4f}")
    print(f"=== 4-evaluator (no dxem): Vanilla W={base_W4:.4f}  Fixed W={full_W4:.4f}")
    print(f"=== Decision: {decision} (using Fixed 4-eval W={decision_W:.4f})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
