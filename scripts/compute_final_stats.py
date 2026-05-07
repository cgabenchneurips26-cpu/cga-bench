#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""
Compute final statistics for 15-scenario × 4-model × 3-run experiments.

Produces:
- Friedman test (3-run mean basis)
- Bootstrap 95% CI per model
- Composite metric re-analysis
- Oracle vs RAG comparison table
- LaTeX output

Usage:
    cd ${CGA_BENCH_ROOT}
    PYTHONPATH=. python cga_bench/scripts/compute_final_stats.py
"""
from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Dict, List

import numpy as np
from scipy import stats as scipy_stats


ALL_15 = [
    "septic_shock_basic", "septic_shock_penicillin_allergy", "stemi_inferior_rv_trap",
    "dka_moderate_basic", "dka_hypokalemia_trap", "stroke_tpa_eligible",
    "contrast_aki_prevention_basic", "aki_stage1_basic",
    "af_new_onset_basic", "gi_bleeding_upper_basic", "htn_emergency_basic",
    "pe_submassive_basic", "copd_moderate_exacerbation", "adhf_warm_wet", "hemorrhagic_stroke",
]

MODELS = [
    ("oss-120b", 120, [
        "cga_bench/results/eval_science_rag_oss120b/baseline",
        "cga_bench/results/expansion_3run/run0",
        "cga_bench/results/expansion_3run/run1",
        "cga_bench/results/expansion_3run/run2",
    ]),
    ("Qwen3.5-35B", 35, [
        "cga_bench/results/eval_science_qwen35/baseline",
        "cga_bench/results/eval_science_rag_qwen35/baseline",
    ]),
    ("oss-20b", 20, [
        "cga_bench/results/eval_science_rag_oss20b/baseline",
    ]),
    ("Qwen3-4B", 4, [
        "cga_bench/results/eval_science_rag_qwen3_4b/baseline",
    ]),
]


def load_all_results() -> Dict[str, Dict[str, List[dict]]]:
    """Load all results: {model: {scenario: [result_dicts]}}"""
    all_data: Dict[str, Dict[str, List[dict]]] = {}

    for label, params, dirs in MODELS:
        model_data: Dict[str, List[dict]] = {}
        for d in dirs:
            p = Path(d)
            if not p.exists():
                continue
            for jf in sorted(p.glob("*.json")):
                if jf.name.endswith("summary.json"):
                    continue
                with open(jf) as f:
                    r = json.load(f)
                sid = r.get("scenario_id", "")
                if sid in ALL_15 and "compliance_score" in r:
                    model_data.setdefault(sid, []).append(r)
        all_data[label] = model_data

    return all_data


def compute_scenario_means(
    all_data: Dict[str, Dict[str, List[dict]]],
) -> Dict[str, Dict[str, float]]:
    """Compute mean compliance per model per scenario."""
    means: Dict[str, Dict[str, float]] = {}
    for label in all_data:
        means[label] = {}
        for sid in ALL_15:
            runs = all_data[label].get(sid, [])
            if runs:
                scores = [r["compliance_score"] for r in runs]
                means[label][sid] = statistics.mean(scores)
    return means


def bootstrap_ci(
    values: List[float],
    n_boot: int = 10000,
    alpha: float = 0.05,
) -> tuple:
    """Compute bootstrap confidence interval."""
    if len(values) < 2:
        m = values[0] if values else 0
        return m, m, m
    arr = np.array(values)
    boot_means = np.array([
        np.mean(np.random.choice(arr, size=len(arr), replace=True))
        for _ in range(n_boot)
    ])
    lo = np.percentile(boot_means, 100 * alpha / 2)
    hi = np.percentile(boot_means, 100 * (1 - alpha / 2))
    return float(np.mean(arr)), float(lo), float(hi)


def main() -> None:
    np.random.seed(42)
    all_data = load_all_results()
    means = compute_scenario_means(all_data)

    from cga_bench.eval_harness.scenario_loader import ScenarioLoader
    loader = ScenarioLoader()

    # ================================================================
    # Table 1: Mean ± SD per model per scenario
    # ================================================================
    print("=" * 120)
    print("TABLE 1: 15-SCENARIO × 4-MODEL (mean ± SD)")
    print("=" * 120)
    print(f"{'Scenario':<35}", end="")
    for label, _, _ in MODELS:
        print(f" {label:>15}", end="")
    print()

    model_all_means: Dict[str, List[float]] = {m[0]: [] for m in MODELS}

    for sid in ALL_15:
        print(f"{sid:<35}", end="")
        for label, _, _ in MODELS:
            runs = all_data[label].get(sid, [])
            if len(runs) >= 2:
                scores = [r["compliance_score"] for r in runs]
                m = statistics.mean(scores)
                s = statistics.stdev(scores)
                print(f" {m:>5.1%}±{s:>4.1%}", end="")
                model_all_means[label].append(m)
            elif runs:
                m = runs[0]["compliance_score"]
                print(f" {m:>5.1%}     ", end="")
                model_all_means[label].append(m)
            else:
                print(f" {'—':>10}", end="")
        print()

    print(f"\n{'Average':<35}", end="")
    for label, _, _ in MODELS:
        vals = model_all_means[label]
        if vals:
            print(f" {statistics.mean(vals):>5.1%}     ", end="")
    print()

    # ================================================================
    # Friedman test (3-run mean basis)
    # ================================================================
    print(f"\n{'='*80}")
    print("FRIEDMAN TESTS")
    print(f"{'='*80}")

    matrix = []
    valid_sids = []
    for sid in ALL_15:
        row = []
        all_present = True
        for label, _, _ in MODELS:
            if sid in means[label]:
                row.append(means[label][sid])
            else:
                all_present = False
                break
        if all_present:
            matrix.append(row)
            valid_sids.append(sid)

    if len(matrix) >= 5:
        arr = np.array(matrix)

        # CGA
        stat, pval = scipy_stats.friedmanchisquare(*[arr[:, i] for i in range(4)])
        print(f"\nCGA (N={len(matrix)}): χ²={stat:.3f}, p={pval:.4f}")

        # Composite A
        comp_matrix = []
        for i, sid in enumerate(valid_sids):
            row = []
            for j, (label, _, _) in enumerate(MODELS):
                cga = arr[i, j]
                runs = all_data[label].get(sid, [])
                if runs:
                    try:
                        exp = len(loader.get_scenario(sid).expected_actions)
                    except Exception:
                        exp = 5
                    avg_acts = statistics.mean([r.get("actions_count", 0) for r in runs])
                    cov = min(1.0, avg_acts / max(exp * 2, 1))
                else:
                    cov = 0.5
                row.append(cga * cov)
            comp_matrix.append(row)

        comp_arr = np.array(comp_matrix)
        stat_c, pval_c = scipy_stats.friedmanchisquare(*[comp_arr[:, i] for i in range(4)])
        print(f"Composite A (N={len(comp_matrix)}): χ²={stat_c:.3f}, p={pval_c:.4f}")

    # ================================================================
    # Bootstrap CI
    # ================================================================
    print(f"\n{'='*80}")
    print("BOOTSTRAP 95% CI")
    print(f"{'='*80}")

    for label, params, _ in MODELS:
        vals = model_all_means[label]
        if vals:
            mean, lo, hi = bootstrap_ci(vals)
            print(f"  {label:<15} ({params}B): {mean:.1%} [{lo:.1%}, {hi:.1%}]")

    # ================================================================
    # Oracle comparison
    # ================================================================
    print(f"\n{'='*80}")
    print("ORACLE vs RAG (15 scenarios)")
    print(f"{'='*80}")

    oracle_dirs = [
        "cga_bench/results/oracle_expansion_v2",
        "cga_bench/results/oracle_expansion",
        "cga_bench/results/oss120b_exp",
    ]
    oracle_scores: Dict[str, float] = {}
    for d in oracle_dirs:
        p = Path(d)
        if not p.exists():
            continue
        for jf in sorted(p.glob("*.json")):
            with open(jf) as f:
                r = json.load(f)
            if r.get("agent_id") == "oracle" and "compliance_score" in r:
                oracle_scores[r["scenario_id"]] = r["compliance_score"]

    print(f"{'Scenario':<35} {'Oracle':>8} {'RAG(120B)':>10} {'Gap':>8}")
    for sid in ALL_15:
        o = oracle_scores.get(sid)
        r = means.get("oss-120b", {}).get(sid)
        if o is not None and r is not None:
            print(f"{sid:<35} {o:>7.1%} {r:>9.1%} {o - r:>+7.1%}")
        else:
            print(f"{sid:<35} {'N/A' if o is None else f'{o:.1%}':>7} {'N/A' if r is None else f'{r:.1%}':>9}")

    # Save
    outdir = Path("cga_bench/evidence_pack/analysis")
    with open(outdir / "final_stats.json", "w") as f:
        json.dump({
            "model_means": {l: {s: round(v, 4) for s, v in means[l].items()} for l in means},
            "model_averages": {l: round(statistics.mean(model_all_means[l]), 4)
                               for l in model_all_means if model_all_means[l]},
            "friedman_cga": {"n": len(matrix), "p": round(pval, 4)} if len(matrix) >= 5 else {},
            "friedman_composite": {"n": len(comp_matrix), "p": round(pval_c, 4)} if len(matrix) >= 5 else {},
            "oracle_scores": oracle_scores,
        }, f, indent=2)
    print(f"\nSaved: final_stats.json")


if __name__ == "__main__":
    main()
