"""Recompute paper's hero numbers under typed CwT (Option C).

For each metric, compute (a) original (using ep["c2_pass"]) vs
(b) typed (using ep["c2_pass_typed"]). Reports side-by-side.

Metrics:
  1. Strict 3-way consensus FA: ASC ∩ CwT ∩ PAF pass + TCC fail
  2. Strict 4-way consensus FA: + TOM
  3. Pair ranking reversal: per (model_a, model_b) pair, fraction of
     scenarios where evaluator-A and evaluator-B disagree on which
     model passes more often.
  4. η²(evaluator) / η²(run) — repeated-measures variance ratio.

Usage:
    PYTHONPATH=. python scripts/experiments/recompute_hero_numbers.py \\
        --vmatrix evidence_pack/analysis/verdict_matrix_v6_typed.json
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT.parent))

import numpy as np


def hero_consensus_fa(pe: list, c2_field: str) -> dict:
    """Consensus FA = pass on ALL listed evaluators + fail on TCC.

    v4_hard semantics: ep["v4_hard"]==True means episode HAS hard violations
    (TCC FAILS it). Verified empirically against verdict_matrix_v6.json:
    v4_hard=True iff n_viols>0 (8553 episodes). FA condition therefore
    requires ep["v4_hard"]==True (NOT `not ep["v4_hard"]`).
    """
    n = len(pe)
    fa3 = sum(1 for ep in pe if ep["ac_proxy"] and ep[c2_field] and ep["mab_proxy"] and ep["v4_hard"])
    fa4 = sum(1 for ep in pe if ep["dxem"] and ep["ac_proxy"] and ep[c2_field] and ep["mab_proxy"] and ep["v4_hard"])
    # Also report TOM∩ASC∩CwT (paper's main "consensusFA" — degenerate b/c TOM=100%)
    fa_tom_asc_cwt = sum(1 for ep in pe if ep["dxem"] and ep["ac_proxy"] and ep[c2_field] and ep["v4_hard"])
    return {
        "n": n,
        "strict_3way_fa": fa3,
        "strict_3way_fa_pct": round(100 * fa3 / n, 2),
        "strict_4way_fa": fa4,
        "strict_4way_fa_pct": round(100 * fa4 / n, 2),
        "consensus_fa_tom_asc_cwt": fa_tom_asc_cwt,
        "consensus_fa_tom_asc_cwt_pct": round(100 * fa_tom_asc_cwt / n, 2),
    }


def pair_reversal(pe: list, c2_field: str) -> dict:
    """For each (model_a, model_b) pair across scenarios, count how often
    evaluators disagree on which model passes more often.
    """
    # Build (model, scenario) → list of verdict-tuples (one per evaluator)
    # Per-evaluator: pass rate per (model, scenario) (0 or 1, since 1 run; or count/3 for 3 runs)
    # Group runs: model+scenario → 3 verdicts → mean
    cells: dict = defaultdict(lambda: defaultdict(list))
    evs = ["ac_proxy", c2_field, "mab_proxy", "v4_hard"]
    for ep in pe:
        key = (ep["model"], ep["scenario_id"])
        for ev in evs:
            v = ep[ev] if ev != "v4_hard" else (not ep[ev])  # convert v4_hard fail-as-pass
            cells[key][ev].append(v)
    # Aggregate: pass rate per cell per evaluator
    cell_means: dict = defaultdict(dict)
    for k, vs in cells.items():
        for ev in evs:
            cell_means[k][ev] = sum(vs[ev]) / max(len(vs[ev]), 1)

    # For each scenario, for each pair of models, check if evaluators agree on rank
    # Pair reversal: how many (scenario, eval_pair, model_pair) cells where eval_a says model_a > model_b but eval_b says model_a < model_b
    models = sorted({k[0] for k in cell_means})
    scenarios = sorted({k[1] for k in cell_means})
    total_comparisons = 0
    reversals = 0
    for sc in scenarios:
        for ma, mb in combinations(models, 2):
            ka, kb = (ma, sc), (mb, sc)
            if ka not in cell_means or kb not in cell_means:
                continue
            for ev_a, ev_b in combinations(evs, 2):
                a_diff = cell_means[ka][ev_a] - cell_means[kb][ev_a]
                b_diff = cell_means[ka][ev_b] - cell_means[kb][ev_b]
                if a_diff == 0 or b_diff == 0:
                    continue
                total_comparisons += 1
                if (a_diff > 0) != (b_diff > 0):
                    reversals += 1
    return {
        "n_comparisons": total_comparisons,
        "n_reversals": reversals,
        "reversal_rate_pct": round(100 * reversals / max(total_comparisons, 1), 2),
    }


def eta_squared(pe: list, c2_field: str) -> dict:
    """RM-ANOVA-style η² for evaluator factor and run factor."""
    evs = ["ac_proxy", c2_field, "mab_proxy", "v4_hard"]
    rows = []
    for ep in pe:
        for ev in evs:
            v = ep[ev] if ev != "v4_hard" else (not ep[ev])
            rows.append(
                {
                    "model": ep["model"],
                    "scenario": ep["scenario_id"],
                    "run": ep["run_index"],
                    "evaluator": ev,
                    "verdict": int(v),
                }
            )
    arr = np.array([r["verdict"] for r in rows])
    grand_mean = arr.mean()
    SS_total = ((arr - grand_mean) ** 2).sum()

    # Evaluator effect
    ev_means = defaultdict(list)
    for r in rows:
        ev_means[r["evaluator"]].append(r["verdict"])
    SS_eval = sum(len(v) * (np.mean(v) - grand_mean) ** 2 for v in ev_means.values())

    # Run effect
    run_means = defaultdict(list)
    for r in rows:
        run_means[r["run"]].append(r["verdict"])
    SS_run = sum(len(v) * (np.mean(v) - grand_mean) ** 2 for v in run_means.values())

    return {
        "eta2_eval": round(SS_eval / SS_total, 4) if SS_total > 0 else 0,
        "eta2_run": round(SS_run / SS_total, 4) if SS_total > 0 else 0,
        "eta2_eval_run_ratio": round((SS_eval / SS_total) / max(SS_run / SS_total, 1e-9), 2) if SS_total > 0 else 0,
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vmatrix", default="evidence_pack/analysis/verdict_matrix_v6_typed.json")
    args = p.parse_args()

    vm = json.load(open(args.vmatrix))
    pe = vm["per_episode"]

    print(f"verdict_matrix_v6_typed: {len(pe)} episodes\n")

    print("=" * 60)
    print("METRIC 1: Consensus FA")
    print("=" * 60)
    orig = hero_consensus_fa(pe, "c2_pass")
    typed = hero_consensus_fa(pe, "c2_pass_typed")
    print("  Strict 3-way (ASC ∩ CwT ∩ PAF, fail TCC):")
    print(f"    Original: {orig['strict_3way_fa_pct']:.2f}% ({orig['strict_3way_fa']}/{orig['n']})")
    print(f"    Typed:    {typed['strict_3way_fa_pct']:.2f}% ({typed['strict_3way_fa']}/{typed['n']})")
    print(f"    Δ:        {typed['strict_3way_fa_pct'] - orig['strict_3way_fa_pct']:+.2f} pp")
    print("  Strict 4-way (ASC ∩ CwT ∩ PAF ∩ TOM, fail TCC):")
    print(f"    Original: {orig['strict_4way_fa_pct']:.2f}%")
    print(f"    Typed:    {typed['strict_4way_fa_pct']:.2f}%")
    print(f"    Δ:        {typed['strict_4way_fa_pct'] - orig['strict_4way_fa_pct']:+.2f} pp")

    print("\n" + "=" * 60)
    print("METRIC 2: Pair ranking reversal")
    print("=" * 60)
    rv_orig = pair_reversal(pe, "c2_pass")
    rv_typed = pair_reversal(pe, "c2_pass_typed")
    print(f"  Original: {rv_orig['reversal_rate_pct']:.2f}% ({rv_orig['n_reversals']}/{rv_orig['n_comparisons']})")
    print(f"  Typed:    {rv_typed['reversal_rate_pct']:.2f}% ({rv_typed['n_reversals']}/{rv_typed['n_comparisons']})")
    print(f"  Δ:        {rv_typed['reversal_rate_pct'] - rv_orig['reversal_rate_pct']:+.2f} pp")

    print("\n" + "=" * 60)
    print("METRIC 3: η² decomposition")
    print("=" * 60)
    e_orig = eta_squared(pe, "c2_pass")
    e_typed = eta_squared(pe, "c2_pass_typed")
    print(
        f"  Original η²(eval)/η²(run) = {e_orig['eta2_eval']:.4f} / {e_orig['eta2_run']:.4f}  ratio {e_orig['eta2_eval_run_ratio']:.2f}×"
    )
    print(
        f"  Typed    η²(eval)/η²(run) = {e_typed['eta2_eval']:.4f} / {e_typed['eta2_run']:.4f}  ratio {e_typed['eta2_eval_run_ratio']:.2f}×"
    )

    out = {
        "consensus_fa_original": orig,
        "consensus_fa_typed": typed,
        "pair_reversal_original": rv_orig,
        "pair_reversal_typed": rv_typed,
        "eta_squared_original": e_orig,
        "eta_squared_typed": e_typed,
    }
    open("evidence_pack/analysis/hero_numbers_typed_vs_original.json", "w").write(json.dumps(out, indent=2))
    print("\nSaved → evidence_pack/analysis/hero_numbers_typed_vs_original.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
