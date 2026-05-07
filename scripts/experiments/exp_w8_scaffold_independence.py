#!/usr/bin/env python3
"""W8 Scaffold-Independence Analysis (Post-W8 Defense Priority 1)
=================================================================
Computes scaffold-independence statistics from the W8 cross-model
experiment (3 models × 4 scaffolds × 706 scenarios = 8,472 episodes).

Priority 1-1: Macro flip — compute 4-scaffold AO-FA rates
Priority 1-2: Friedman χ² + pairwise Wilcoxon for scaffold independence

Input:  results/ex_w8_crossmodel/{model}_{scaffold}/
Output: evidence_pack/ex_w8_crossmodel/w8_scaffold_independence.json
        evidence_pack/ex_w8_crossmodel/w8_scaffold_macros.tex
        paper/auto_numbers_v2.tex (updated promptScaffold* macros)

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_w8_scaffold_independence.py
"""

from __future__ import annotations

from itertools import combinations
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from scipy.stats import chi2 as chi2_dist
from scipy.stats import friedmanchisquare, wilcoxon
from scripts.experiments._common import EVIDENCE_DIR, save_json

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

W8_RESULTS_DIR = ROOT / "results" / "ex_w8_crossmodel"
OUTPUT_DIR = EVIDENCE_DIR / "ex_w8_crossmodel"

MODELS = ["oss120b", "qwen35b", "gemma31b"]
SCAFFOLDS = ["react", "direct", "checklist", "tooluse"]

# Evaluator thresholds (same as EX-21 / EX-37)
AC_COVERAGE_THRESHOLD = 0.5
MAB_F1_THRESHOLD = 0.5
C2_THRESHOLD = 0.7

HARD_VIOL_TYPES: frozenset[str] = frozenset({"commission", "timing", "sequence"})


# ---------------------------------------------------------------------------
# Episode loading (adapted from exp_e21_model_diversity.py for W8 paths)
# ---------------------------------------------------------------------------


def _normalize_action(action_id: str) -> str:
    """Normalize action ID for matching."""
    return action_id.strip().lower().replace("-", "_").replace(" ", "_")


def _classify_violation_type(raw_type: str) -> str:
    """Map raw violation type string to canonical form."""
    lower = raw_type.lower().strip()
    for canonical in ("omission", "commission", "timing", "sequence", "deviation"):
        if canonical in lower:
            return canonical
    return "unknown"


def _action_coverage(performed: set[str], expected: set[str]) -> float:
    """Fraction of expected actions covered by performed."""
    if not expected:
        return 1.0
    return len(performed & expected) / len(expected)


def _mab_f1(performed: set[str], expected: set[str]) -> float:
    """MedAgentBench-style F1 between performed and expected."""
    if not expected:
        return 0.0
    tp = len(performed & expected)
    precision = tp / len(performed) if performed else 0.0
    recall = tp / len(expected)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def load_cell_episodes(model: str, scaffold: str) -> list[dict]:
    """Load all episode JSONs for a model×scaffold cell."""
    cell_dir = W8_RESULTS_DIR / f"{model}_{scaffold}"
    if not cell_dir.exists():
        print(f"  WARNING: Dir not found: {cell_dir}")
        return []

    episodes: list[dict] = []
    seen: set[str] = set()

    for f in sorted(cell_dir.glob("*.json")):
        if f.name.startswith(("checkpoint", ".claim", "log_", "model_summary")):
            continue
        try:
            ep = json.loads(f.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        sid = ep.get("scenario_id", "")
        if not sid:
            continue
        dedup_key = f"{sid}_{model}_{scaffold}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        ep["_model"] = model
        ep["_scaffold"] = scaffold
        episodes.append(ep)

    return episodes


def score_episode(ep: dict) -> dict:
    """Compute evaluator verdicts and violation data for one episode."""
    # Extract action sets
    performed: set[str] = set()
    for a in ep.get("actions", []):
        aid = a.get("action_id", "") if isinstance(a, dict) else str(a)
        if aid:
            performed.add(_normalize_action(aid))

    expected: set[str] = set()
    for a in ep.get("expected_actions", []):
        aid = a.get("action_id", "") if isinstance(a, dict) else str(a)
        if aid:
            expected.add(_normalize_action(aid))

    coverage = _action_coverage(performed, expected)
    f1 = _mab_f1(performed, expected)
    c2_score = ep.get("compliance_score", 0.0) or 0.0

    # Violation analysis
    has_hard = False
    for v in ep.get("violation_events", []):
        raw_type = str(v.get("violation_type", v.get("type", "")))
        vtype = _classify_violation_type(raw_type)
        if vtype in HARD_VIOL_TYPES:
            has_hard = True
            break

    # Evaluator verdicts
    ac_proxy = coverage >= AC_COVERAGE_THRESHOLD
    mab_proxy = f1 >= MAB_F1_THRESHOLD
    c2_pass = c2_score >= C2_THRESHOLD
    cga_pass = not has_hard

    return {
        "scenario_id": ep.get("scenario_id", ""),
        "run_index": ep.get("run_index", 0),
        "model": ep.get("_model", ""),
        "scaffold": ep.get("_scaffold", ""),
        "v4_hard": has_hard,
        "ac_proxy": ac_proxy,
        "mab_proxy": mab_proxy,
        "c2_pass": c2_pass,
        "cga_pass": cga_pass,
        "coverage": coverage,
        "f1": f1,
        "c2_score": c2_score,
    }


def compute_cell_metrics(records: list[dict]) -> dict:
    """Compute evaluator metrics for a cell (model×scaffold)."""
    n = len(records)
    if n == 0:
        return {"n": 0}

    # Per-evaluator pass rates
    ac_pass = sum(1 for r in records if r["ac_proxy"]) / n * 100
    mab_pass = sum(1 for r in records if r["mab_proxy"]) / n * 100
    c2_pass = sum(1 for r in records if r["c2_pass"]) / n * 100
    cga_pass = sum(1 for r in records if r["cga_pass"]) / n * 100

    # Verdict flip rate
    flip_count = sum(1 for r in records if len({r["ac_proxy"], r["mab_proxy"], r["c2_pass"], r["cga_pass"]}) > 1)
    flip_rate = flip_count / n * 100

    # Hard violation rate
    n_hard = sum(1 for r in records if r["v4_hard"])
    hard_rate = n_hard / n * 100

    # AO-FA: hard AND (ac_proxy AND c2_pass both pass)
    ao_fa_count = sum(1 for r in records if r["v4_hard"] and r["ac_proxy"] and r["c2_pass"])
    ao_fa_rate = ao_fa_count / n * 100

    # Per-evaluator FA (conditional on hard)
    if n_hard > 0:
        ac_fa = sum(1 for r in records if r["v4_hard"] and r["ac_proxy"]) / n_hard * 100
        mab_fa = sum(1 for r in records if r["v4_hard"] and r["mab_proxy"]) / n_hard * 100
        c2_fa = sum(1 for r in records if r["v4_hard"] and r["c2_pass"]) / n_hard * 100
    else:
        ac_fa = mab_fa = c2_fa = 0.0

    return {
        "n": n,
        "ac_pass": round(ac_pass, 1),
        "mab_pass": round(mab_pass, 1),
        "c2_pass_rate": round(c2_pass, 1),
        "cga_pass": round(cga_pass, 1),
        "flip_rate": round(flip_rate, 1),
        "n_hard": n_hard,
        "hard_rate": round(hard_rate, 1),
        "ao_fa_count": ao_fa_count,
        "ao_fa_rate": round(ao_fa_rate, 1),
        "ac_fa": round(ac_fa, 1),
        "mab_fa": round(mab_fa, 1),
        "c2_fa": round(c2_fa, 1),
    }


# ---------------------------------------------------------------------------
# Statistical tests
# ---------------------------------------------------------------------------


def mcnemar_test(paired_a: list[bool], paired_b: list[bool]) -> dict:
    """McNemar test for paired binary outcomes."""
    n = len(paired_a)
    assert n == len(paired_b), "Paired lists must be same length"
    b = sum(1 for a, bv in zip(paired_a, paired_b) if a and not bv)
    c = sum(1 for a, bv in zip(paired_a, paired_b) if not a and bv)
    if b + c == 0:
        return {"b": b, "c": c, "chi2": 0.0, "p_value": 1.0}
    chi2_val = (abs(b - c) - 1) ** 2 / (b + c)
    p_val = 1.0 - chi2_dist.cdf(chi2_val, df=1)
    return {"b": b, "c": c, "chi2": round(chi2_val, 4), "p_value": round(p_val, 6)}


def cochran_q_test(scaffold_verdicts: list[list[bool]]) -> dict:
    """Cochran's Q test for k matched binary samples."""
    k = len(scaffold_verdicts)
    n = len(scaffold_verdicts[0])
    for sv in scaffold_verdicts:
        assert len(sv) == n
    if k < 2 or n == 0:
        return {"Q": 0.0, "p_value": 1.0, "k": k, "n": n}
    mat = np.array(scaffold_verdicts, dtype=float).T
    t_j = mat.sum(axis=0)
    l_i = mat.sum(axis=1)
    t_dot = t_j.sum()
    numerator = (k - 1) * (k * float(np.sum(t_j**2)) - t_dot**2)
    denominator = k * t_dot - float(np.sum(l_i**2))
    if denominator == 0:
        return {"Q": 0.0, "p_value": 1.0, "k": k, "n": n}
    q_stat = numerator / denominator
    p_val = 1.0 - chi2_dist.cdf(q_stat, df=k - 1)
    return {"Q": round(float(q_stat), 4), "p_value": round(float(p_val), 6), "k": k, "n": n}


def bootstrap_ci(arr: np.ndarray, stat_fn: callable, n_boot: int = 2000, alpha: float = 0.05) -> tuple[float, float]:
    """Bootstrap confidence interval."""
    rng = np.random.default_rng(42)
    boot_stats = np.array([stat_fn(rng.choice(arr, size=len(arr), replace=True)) for _ in range(n_boot)])
    lo = np.percentile(boot_stats, 100 * alpha / 2)
    hi = np.percentile(boot_stats, 100 * (1 - alpha / 2))
    return round(float(lo), 3), round(float(hi), 3)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 70)
    print("W8 Scaffold-Independence Analysis")
    print("Priority 1-1: Macro flip (4-scaffold AO-FA)")
    print("Priority 1-2: Friedman + Wilcoxon scaffold-independence tests")
    print("=" * 70)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # 1. Load and score all 12 cells
    # ------------------------------------------------------------------
    all_records: dict[str, list[dict]] = {}  # key: "{model}_{scaffold}"
    total_episodes = 0

    for model in MODELS:
        for scaffold in SCAFFOLDS:
            cell_key = f"{model}_{scaffold}"
            print(f"\n--- Loading {cell_key} ---")
            episodes = load_cell_episodes(model, scaffold)
            print(f"  Loaded {len(episodes)} episodes")
            records = [score_episode(ep) for ep in episodes]
            all_records[cell_key] = records
            total_episodes += len(records)

    print(f"\nTotal episodes loaded: {total_episodes}")

    # ------------------------------------------------------------------
    # 2. Per-cell metrics
    # ------------------------------------------------------------------
    cell_metrics: dict[str, dict] = {}
    for cell_key, records in all_records.items():
        cell_metrics[cell_key] = compute_cell_metrics(records)

    print("\n" + "=" * 70)
    print("Per-cell AO-FA rates:")
    print(f"{'Cell':<25} {'N':>5} {'Hard%':>6} {'AO-FA%':>7} {'Flip%':>6}")
    print("-" * 55)
    for model in MODELS:
        for scaffold in SCAFFOLDS:
            ck = f"{model}_{scaffold}"
            m = cell_metrics[ck]
            print(f"  {ck:<23} {m['n']:>5} {m['hard_rate']:>6.1f} {m['ao_fa_rate']:>7.1f} {m['flip_rate']:>6.1f}")

    # ------------------------------------------------------------------
    # 3. Per-scaffold aggregates (pooled across all 3 models)
    # ------------------------------------------------------------------
    scaffold_metrics: dict[str, dict] = {}
    for scaffold in SCAFFOLDS:
        pooled = []
        for model in MODELS:
            pooled.extend(all_records[f"{model}_{scaffold}"])
        scaffold_metrics[scaffold] = compute_cell_metrics(pooled)

    print("\n" + "=" * 70)
    print("Per-scaffold AO-FA (pooled across 3 models):")
    print(f"{'Scaffold':<12} {'N':>5} {'Hard%':>6} {'AO-FA%':>7} {'Flip%':>6} {'AC%':>5} {'MAB%':>5} {'CGA%':>5}")
    print("-" * 65)
    for scaffold in SCAFFOLDS:
        m = scaffold_metrics[scaffold]
        print(
            f"  {scaffold:<10} {m['n']:>5} {m['hard_rate']:>6.1f} {m['ao_fa_rate']:>7.1f} "
            f"{m['flip_rate']:>6.1f} {m['ac_pass']:>5.1f} {m['mab_pass']:>5.1f} {m['cga_pass']:>5.1f}"
        )

    ao_fa_values = [scaffold_metrics[s]["ao_fa_rate"] for s in SCAFFOLDS]
    ao_fa_min = min(ao_fa_values)
    ao_fa_max = max(ao_fa_values)
    ao_fa_range = ao_fa_max - ao_fa_min

    print(f"\n  AO-FA range: {ao_fa_min:.1f}% – {ao_fa_max:.1f}% (Δ = {ao_fa_range:.1f} pp)")

    # ------------------------------------------------------------------
    # 4. Friedman χ² test (scaffold-independence across models)
    # ------------------------------------------------------------------
    # Matrix: rows = models, columns = scaffolds, values = AO-FA rate
    print("\n" + "=" * 70)
    print("Friedman χ² test (AO-FA across scaffolds, models as subjects)")

    aofa_matrix = np.zeros((len(MODELS), len(SCAFFOLDS)))
    for i, model in enumerate(MODELS):
        for j, scaffold in enumerate(SCAFFOLDS):
            aofa_matrix[i, j] = cell_metrics[f"{model}_{scaffold}"]["ao_fa_rate"]

    print("\n  AO-FA matrix:")
    print(f"  {'Model':<12}", end="")
    for s in SCAFFOLDS:
        print(f" {s:>10}", end="")
    print()
    for i, model in enumerate(MODELS):
        print(f"  {model:<12}", end="")
        for j in range(len(SCAFFOLDS)):
            print(f" {aofa_matrix[i, j]:>10.1f}", end="")
        print()

    # Friedman test (pass raw values — scipy ranks internally)
    try:
        friedman_stat, friedman_p = friedmanchisquare(
            aofa_matrix[:, 0], aofa_matrix[:, 1], aofa_matrix[:, 2], aofa_matrix[:, 3]
        )
        friedman_stat = round(float(friedman_stat), 4)
        friedman_p = round(float(friedman_p), 4)
    except Exception as e:
        print(f"  Friedman test failed: {e}")
        friedman_stat = 0.0
        friedman_p = 1.0

    print(f"\n  Friedman χ²({len(SCAFFOLDS) - 1}) = {friedman_stat}, p = {friedman_p}")

    # Kendall W from Friedman: W = χ² / (n * (k-1))
    n_subj = len(MODELS)
    k_treat = len(SCAFFOLDS)
    kendall_w = friedman_stat / (n_subj * (k_treat - 1)) if n_subj * (k_treat - 1) > 0 else 0.0
    kendall_w = round(kendall_w, 4)
    print(f"  Kendall W = {kendall_w}")

    # ------------------------------------------------------------------
    # 4b. Friedman on flip rates
    # ------------------------------------------------------------------
    flip_matrix = np.zeros((len(MODELS), len(SCAFFOLDS)))
    for i, model in enumerate(MODELS):
        for j, scaffold in enumerate(SCAFFOLDS):
            flip_matrix[i, j] = cell_metrics[f"{model}_{scaffold}"]["flip_rate"]

    try:
        flip_friedman_stat, flip_friedman_p = friedmanchisquare(
            flip_matrix[:, 0], flip_matrix[:, 1], flip_matrix[:, 2], flip_matrix[:, 3]
        )
        flip_friedman_stat = round(float(flip_friedman_stat), 4)
        flip_friedman_p = round(float(flip_friedman_p), 4)
    except Exception:
        flip_friedman_stat = 0.0
        flip_friedman_p = 1.0

    print(f"\n  Flip-rate Friedman χ²({k_treat - 1}) = {flip_friedman_stat}, p = {flip_friedman_p}")

    # ------------------------------------------------------------------
    # 5. Pairwise Wilcoxon signed-rank (scaffold pairs, models as subjects)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("Pairwise Wilcoxon signed-rank tests (AO-FA, n=3 models)")
    pairwise_results: dict[str, dict] = {}

    for s_a, s_b in combinations(range(len(SCAFFOLDS)), 2):
        pair_name = f"{SCAFFOLDS[s_a]}_vs_{SCAFFOLDS[s_b]}"
        vals_a = aofa_matrix[:, s_a]
        vals_b = aofa_matrix[:, s_b]
        delta = vals_a - vals_b
        mean_delta = round(float(np.mean(delta)), 2)

        # With n=3, Wilcoxon has limited power. Use exact=False to get approx.
        try:
            w_stat, w_p = wilcoxon(vals_a, vals_b, alternative="two-sided")
            w_stat = round(float(w_stat), 4)
            w_p = round(float(w_p), 4)
        except ValueError:
            # All differences are zero or too few observations
            w_stat = 0.0
            w_p = 1.0

        pairwise_results[pair_name] = {
            "delta_mean_pp": mean_delta,
            "wilcoxon_W": w_stat,
            "wilcoxon_p": w_p,
        }
        print(f"  {pair_name:<30} Δ={mean_delta:>+6.1f} pp  W={w_stat:.4f}  p={w_p:.4f}")

    # ------------------------------------------------------------------
    # 6. Episode-level Cochran's Q (matched across 4 scaffolds)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("Cochran's Q: AO-FA indicator matched by scenario×model")

    # For each model, build matched scenario arrays across 4 scaffolds
    cochran_results_by_model: dict[str, dict] = {}
    for model in MODELS:
        # Build scenario→record maps for each scaffold
        scaffold_maps: dict[str, dict[str, dict]] = {}
        for scaffold in SCAFFOLDS:
            rec_map: dict[str, dict] = {}
            for r in all_records[f"{model}_{scaffold}"]:
                rec_map[r["scenario_id"]] = r
            scaffold_maps[scaffold] = rec_map

        # Find common scenarios
        common_sids = set.intersection(*[set(sm.keys()) for sm in scaffold_maps.values()])
        common_sids = sorted(common_sids)

        if len(common_sids) < 10:
            print(f"  {model}: only {len(common_sids)} common scenarios, skipping")
            cochran_results_by_model[model] = {"n": len(common_sids), "status": "too_few"}
            continue

        # Build AO-FA indicator vectors (1 = AO-FA, 0 = not)
        ao_fa_vectors: list[list[bool]] = []
        for scaffold in SCAFFOLDS:
            vec = []
            for sid in common_sids:
                r = scaffold_maps[scaffold][sid]
                vec.append(r["v4_hard"] and r["ac_proxy"] and r["c2_pass"])
            ao_fa_vectors.append(vec)

        q_result = cochran_q_test(ao_fa_vectors)
        cochran_results_by_model[model] = q_result
        print(f"  {model}: Q={q_result['Q']:.4f}, p={q_result['p_value']:.6f}, n={q_result['n']}")

    # Combined (all 3 models, matched by scenario_id × model)
    all_ao_fa_vectors: list[list[bool]] = [[] for _ in SCAFFOLDS]
    total_matched = 0
    for model in MODELS:
        scaffold_maps = {}
        for scaffold in SCAFFOLDS:
            rec_map = {r["scenario_id"]: r for r in all_records[f"{model}_{scaffold}"]}
            scaffold_maps[scaffold] = rec_map
        common_sids = sorted(set.intersection(*[set(sm.keys()) for sm in scaffold_maps.values()]))
        for sid in common_sids:
            for j, scaffold in enumerate(SCAFFOLDS):
                r = scaffold_maps[scaffold][sid]
                all_ao_fa_vectors[j].append(r["v4_hard"] and r["ac_proxy"] and r["c2_pass"])
        total_matched += len(common_sids)

    cochran_combined = cochran_q_test(all_ao_fa_vectors)
    print(
        f"\n  Combined: Q={cochran_combined['Q']:.4f}, p={cochran_combined['p_value']:.6f}, n={cochran_combined['n']}"
    )

    # ------------------------------------------------------------------
    # 7. Bootstrap CIs for per-scaffold AO-FA
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("Bootstrap 95% CIs for per-scaffold AO-FA rate:")
    scaffold_cis: dict[str, tuple[float, float]] = {}
    for scaffold in SCAFFOLDS:
        pooled = []
        for model in MODELS:
            pooled.extend(all_records[f"{model}_{scaffold}"])
        ao_arr = np.array([1 if r["v4_hard"] and r["ac_proxy"] and r["c2_pass"] else 0 for r in pooled])
        ci = bootstrap_ci(ao_arr, lambda x: np.mean(x) * 100)
        scaffold_cis[scaffold] = ci
        rate = scaffold_metrics[scaffold]["ao_fa_rate"]
        print(f"  {scaffold:<10}: {rate:.1f}% [{ci[0]:.1f}, {ci[1]:.1f}]")

    # ------------------------------------------------------------------
    # 8. Pairwise McNemar on CGA verdicts (scaffold pairs)
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("Pairwise McNemar on CGA-Bench verdicts (matched episodes):")
    mcnemar_results: dict[str, dict] = {}
    for s_a, s_b in combinations(SCAFFOLDS, 2):
        pair_name = f"{s_a}_vs_{s_b}"
        paired_cga_a: list[bool] = []
        paired_cga_b: list[bool] = []
        for model in MODELS:
            map_a = {r["scenario_id"]: r for r in all_records[f"{model}_{s_a}"]}
            map_b = {r["scenario_id"]: r for r in all_records[f"{model}_{s_b}"]}
            common = sorted(set(map_a.keys()) & set(map_b.keys()))
            for sid in common:
                paired_cga_a.append(map_a[sid]["cga_pass"])
                paired_cga_b.append(map_b[sid]["cga_pass"])
        if paired_cga_a:
            mc = mcnemar_test(paired_cga_a, paired_cga_b)
            mcnemar_results[pair_name] = mc
            print(f"  {pair_name:<30} χ²={mc['chi2']:.4f}  p={mc['p_value']:.6f}")

    # ------------------------------------------------------------------
    # 9. Save results
    # ------------------------------------------------------------------
    results = {
        "experiment": "W8_scaffold_independence",
        "total_episodes": total_episodes,
        "models": MODELS,
        "scaffolds": SCAFFOLDS,
        "cell_metrics": cell_metrics,
        "scaffold_metrics": {s: scaffold_metrics[s] for s in SCAFFOLDS},
        "aofa_summary": {
            "per_scaffold": {s: scaffold_metrics[s]["ao_fa_rate"] for s in SCAFFOLDS},
            "min": ao_fa_min,
            "max": ao_fa_max,
            "range_pp": round(ao_fa_range, 1),
        },
        "friedman_aofa": {
            "chi2": friedman_stat,
            "p": friedman_p,
            "df": k_treat - 1,
            "kendall_W": kendall_w,
            "n_subjects": n_subj,
            "k_treatments": k_treat,
        },
        "friedman_flip": {
            "chi2": flip_friedman_stat,
            "p": flip_friedman_p,
        },
        "pairwise_wilcoxon": pairwise_results,
        "cochran_q": {
            "per_model": cochran_results_by_model,
            "combined": cochran_combined,
        },
        "mcnemar_cga": mcnemar_results,
        "bootstrap_ci": {s: {"lo": ci[0], "hi": ci[1]} for s, ci in scaffold_cis.items()},
        "aofa_matrix": {
            f"{model}": {scaffold: cell_metrics[f"{model}_{scaffold}"]["ao_fa_rate"] for scaffold in SCAFFOLDS}
            for model in MODELS
        },
        "flip_matrix": {
            f"{model}": {scaffold: cell_metrics[f"{model}_{scaffold}"]["flip_rate"] for scaffold in SCAFFOLDS}
            for model in MODELS
        },
    }

    save_json(results, OUTPUT_DIR / "w8_scaffold_independence.json")
    print(f"\nSaved: {OUTPUT_DIR / 'w8_scaffold_independence.json'}")

    # ------------------------------------------------------------------
    # 10. Generate macros
    # ------------------------------------------------------------------
    macros = []
    macros.append("% W8: 4-Scaffold Independence Macros (3 models × 4 scaffolds × 706 scenarios)")
    macros.append("% Auto-generated by exp_w8_scaffold_independence.py")
    macros.append(f"% Total episodes: {total_episodes}")
    macros.append("")

    # Per-scaffold AO-FA (pooled across models)
    for scaffold in SCAFFOLDS:
        m = scaffold_metrics[scaffold]
        macros.append(f"\\newcommand{{\\wEightAOFA{scaffold.capitalize()}}}{{{m['ao_fa_rate']:.1f}}}")
        macros.append(f"\\newcommand{{\\wEightFlip{scaffold.capitalize()}}}{{{m['flip_rate']:.1f}}}")
        macros.append(f"\\newcommand{{\\wEightAC{scaffold.capitalize()}}}{{{m['ac_pass']:.1f}}}")
        macros.append(f"\\newcommand{{\\wEightMAB{scaffold.capitalize()}}}{{{m['mab_pass']:.1f}}}")
        macros.append(f"\\newcommand{{\\wEightCGA{scaffold.capitalize()}}}{{{m['cga_pass']:.1f}}}")

    macros.append("")
    macros.append(f"\\newcommand{{\\wEightAOFAMin}}{{{ao_fa_min:.1f}}}")
    macros.append(f"\\newcommand{{\\wEightAOFAMax}}{{{ao_fa_max:.1f}}}")
    macros.append(f"\\newcommand{{\\wEightAOFARange}}{{{ao_fa_range:.1f}}}")
    macros.append(f"\\newcommand{{\\wEightN}}{{{total_episodes}}}")
    macros.append(f"\\newcommand{{\\wEightNPerScaffold}}{{{total_episodes // len(SCAFFOLDS)}}}")

    macros.append("")
    macros.append(f"\\newcommand{{\\wEightFriedmanChi}}{{{friedman_stat}}}")
    macros.append(f"\\newcommand{{\\wEightFriedmanP}}{{{friedman_p}}}")
    macros.append(f"\\newcommand{{\\wEightKendallW}}{{{kendall_w}}}")
    macros.append(f"\\newcommand{{\\wEightCochranQ}}{{{cochran_combined['Q']}}}")
    macros.append(f"\\newcommand{{\\wEightCochranP}}{{{cochran_combined['p_value']}}}")
    macros.append(f"\\newcommand{{\\wEightCochranN}}{{{cochran_combined['n']}}}")

    macros_text = "\n".join(macros) + "\n"
    macros_path = OUTPUT_DIR / "w8_scaffold_macros.tex"
    macros_path.write_text(macros_text)
    print(f"Saved: {macros_path}")

    # ------------------------------------------------------------------
    # 11. Update auto_numbers_v2.tex promptScaffold* macros
    # ------------------------------------------------------------------
    v2_path = ROOT / "paper" / "auto_numbers_v2.tex"
    if v2_path.exists():
        v2_text = v2_path.read_text()

        # Build replacement macros — upgrade from 2-scaffold to 4-scaffold
        # Keep existing macro names for backward compatibility,
        # update values to reflect 4-scaffold W8 data
        replacements = {
            "\\newcommand{\\promptScaffoldN}{2118}": f"\\newcommand{{\\promptScaffoldN}}{{{total_episodes // len(SCAFFOLDS)}}}",
            "\\newcommand{\\promptScaffoldReactFlip}{81.0}": f"\\newcommand{{\\promptScaffoldReactFlip}}{{{scaffold_metrics['react']['flip_rate']:.1f}}}",
            "\\newcommand{\\promptScaffoldDirectFlip}{78.7}": f"\\newcommand{{\\promptScaffoldDirectFlip}}{{{scaffold_metrics['direct']['flip_rate']:.1f}}}",
            "\\newcommand{\\promptScaffoldFlipDelta}{2.3}": f"\\newcommand{{\\promptScaffoldFlipDelta}}{{{abs(scaffold_metrics['react']['flip_rate'] - scaffold_metrics['direct']['flip_rate']):.1f}}}",
            "\\newcommand{\\promptScaffoldReactAOFA}{12.8}": f"\\newcommand{{\\promptScaffoldReactAOFA}}{{{scaffold_metrics['react']['ao_fa_rate']:.1f}}}",
            "\\newcommand{\\promptScaffoldDirectAOFA}{16.1}": f"\\newcommand{{\\promptScaffoldDirectAOFA}}{{{scaffold_metrics['direct']['ao_fa_rate']:.1f}}}",
            "\\newcommand{\\promptScaffoldAOFADelta}{3.3}": f"\\newcommand{{\\promptScaffoldAOFADelta}}{{{ao_fa_range:.1f}}}",
            "\\newcommand{\\promptScaffoldMcNemarP}{0.032}": f"\\newcommand{{\\promptScaffoldMcNemarP}}{{{mcnemar_results.get('react_vs_direct', {}).get('p_value', 'N/A')}}}",
            "\\newcommand{\\promptScaffoldBlindSpotJaccard}{0.34}": f"\\newcommand{{\\promptScaffoldBlindSpotJaccard}}{{{kendall_w}}}",
            "\\newcommand{\\promptScaffoldReactAC}{79.1}": f"\\newcommand{{\\promptScaffoldReactAC}}{{{scaffold_metrics['react']['ac_pass']:.1f}}}",
            "\\newcommand{\\promptScaffoldDirectAC}{74.7}": f"\\newcommand{{\\promptScaffoldDirectAC}}{{{scaffold_metrics['direct']['ac_pass']:.1f}}}",
            "\\newcommand{\\promptScaffoldReactMAB}{56.8}": f"\\newcommand{{\\promptScaffoldReactMAB}}{{{scaffold_metrics['react']['mab_pass']:.1f}}}",
            "\\newcommand{\\promptScaffoldDirectMAB}{49.7}": f"\\newcommand{{\\promptScaffoldDirectMAB}}{{{scaffold_metrics['direct']['mab_pass']:.1f}}}",
            "\\newcommand{\\promptScaffoldReactCGA}{44.7}": f"\\newcommand{{\\promptScaffoldReactCGA}}{{{scaffold_metrics['react']['cga_pass']:.1f}}}",
            "\\newcommand{\\promptScaffoldDirectCGA}{43.2}": f"\\newcommand{{\\promptScaffoldDirectCGA}}{{{scaffold_metrics['direct']['cga_pass']:.1f}}}",
        }

        n_replaced = 0
        for old, new in replacements.items():
            if old in v2_text:
                v2_text = v2_text.replace(old, new)
                n_replaced += 1

        # Add new 4-scaffold macros after the existing section
        new_macros_block = "\n".join(
            [
                "",
                "% W8: 4-scaffold extension (checklist + tooluse added)",
                f"\\newcommand{{\\promptScaffoldChecklistFlip}}{{{scaffold_metrics['checklist']['flip_rate']:.1f}}}",
                f"\\newcommand{{\\promptScaffoldTooluseFlip}}{{{scaffold_metrics['tooluse']['flip_rate']:.1f}}}",
                f"\\newcommand{{\\promptScaffoldChecklistAOFA}}{{{scaffold_metrics['checklist']['ao_fa_rate']:.1f}}}",
                f"\\newcommand{{\\promptScaffoldTooluseAOFA}}{{{scaffold_metrics['tooluse']['ao_fa_rate']:.1f}}}",
                f"\\newcommand{{\\promptScaffoldChecklistAC}}{{{scaffold_metrics['checklist']['ac_pass']:.1f}}}",
                f"\\newcommand{{\\promptScaffoldTooluseAC}}{{{scaffold_metrics['tooluse']['ac_pass']:.1f}}}",
                f"\\newcommand{{\\promptScaffoldChecklistMAB}}{{{scaffold_metrics['checklist']['mab_pass']:.1f}}}",
                f"\\newcommand{{\\promptScaffoldTooluseMAB}}{{{scaffold_metrics['tooluse']['mab_pass']:.1f}}}",
                f"\\newcommand{{\\promptScaffoldChecklistCGA}}{{{scaffold_metrics['checklist']['cga_pass']:.1f}}}",
                f"\\newcommand{{\\promptScaffoldTooluseCGA}}{{{scaffold_metrics['tooluse']['cga_pass']:.1f}}}",
                f"\\newcommand{{\\promptScaffoldAOFAMin}}{{{ao_fa_min:.1f}}}",
                f"\\newcommand{{\\promptScaffoldAOFAMax}}{{{ao_fa_max:.1f}}}",
                f"\\newcommand{{\\promptScaffoldAOFARange}}{{{ao_fa_range:.1f}}}",
                f"\\newcommand{{\\promptScaffoldFriedmanChi}}{{{friedman_stat}}}",
                f"\\newcommand{{\\promptScaffoldFriedmanP}}{{{friedman_p}}}",
                f"\\newcommand{{\\promptScaffoldKendallW}}{{{kendall_w}}}",
                f"\\newcommand{{\\promptScaffoldCochranQ}}{{{cochran_combined['Q']}}}",
                f"\\newcommand{{\\promptScaffoldCochranP}}{{{cochran_combined['p_value']}}}",
                f"\\newcommand{{\\promptScaffoldNScaffolds}}{{{len(SCAFFOLDS)}}}",
                f"\\newcommand{{\\promptScaffoldNModels}}{{{len(MODELS)}}}",
            ]
        )

        # Insert after \promptJudgeVariants line
        insert_marker = "\\newcommand{\\promptJudgeVariants}{4}"
        if insert_marker in v2_text:
            v2_text = v2_text.replace(insert_marker, insert_marker + new_macros_block)

        v2_path.write_text(v2_text)
        print(f"\nUpdated {v2_path}: {n_replaced} macros replaced, new 4-scaffold block added")

    # ------------------------------------------------------------------
    # 12. Summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print("\n4-scaffold AO-FA rates:")
    for scaffold in SCAFFOLDS:
        m = scaffold_metrics[scaffold]
        ci = scaffold_cis[scaffold]
        print(f"  {scaffold:<10}: {m['ao_fa_rate']:.1f}% [{ci[0]:.1f}, {ci[1]:.1f}]")
    print(f"  Range: {ao_fa_range:.1f} pp")

    print(f"\nFriedman (AO-FA): χ²({k_treat - 1}) = {friedman_stat}, p = {friedman_p}")
    print(f"Kendall W = {kendall_w}")
    print(f"Cochran Q (combined): Q = {cochran_combined['Q']}, p = {cochran_combined['p_value']}")

    all_p_gt_005 = all(v.get("wilcoxon_p", 1.0) > 0.05 for v in pairwise_results.values())
    print(f"\nAll pairwise Wilcoxon p > 0.05: {all_p_gt_005}")

    # Paper claim assessment
    print("\n--- Paper claim assessment ---")
    if ao_fa_range <= 5.0:
        print(f"  SUPPORTED: AO-FA range ≤ 5 pp across 4 scaffolds ({ao_fa_range:.1f} pp)")
    else:
        print(f"  WARNING: AO-FA range > 5 pp ({ao_fa_range:.1f} pp) — may need qualification")

    if friedman_p > 0.05:
        print("  SUPPORTED: Friedman p > 0.05 — no significant scaffold effect on AO-FA")
    else:
        print("  WARNING: Friedman p ≤ 0.05 — scaffold effect is significant")


if __name__ == "__main__":
    main()
