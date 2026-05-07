#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""Comprehensive robustness analysis for rescored clean-slate 180 episodes.

Outputs:
  - evidence_pack/analysis/robustness_clean_v2.json  (machine-readable)
  - evidence_pack/FINAL_NUMBERS_CLEAN_V2.md          (human-readable report)

Analyses:
  1. Leave-one-scenario-out Friedman (15x)
  2. Run-level consistency (per-run Friedman, 3x)
  3. Holm correction on pre-defined family
  4. k-space sensitivity (k=0.5..4.0)
  5. Bootstrap 95% CI (10,000 iterations)
  6. Sub-construct C1-C5 profiles per model
  7. Point-biserial r (CGA vs task completion, C2>=threshold)
  8. Q2 re-derivation (optimal C2 threshold)
  9. Violation co-occurrence matrix
  10. Required sample size simulation
"""

from collections import defaultdict
from datetime import datetime
from itertools import combinations
import json
import logging
from pathlib import Path
import statistics

import numpy as np
from scipy import stats as sp_stats

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

RESCORED_DIR = Path("results/clean_slate_rescored")
OUTPUT_JSON = Path("evidence_pack/analysis/robustness_clean_v2.json")
OUTPUT_MD = Path("evidence_pack/FINAL_NUMBERS_CLEAN_V2.md")

MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]
MODEL_LABELS = {
    "oss120b": "DeepSeek-R1-671B (oss-120b)",
    "qwen27b": "Qwen3.5-27B",
    "qwen35b": "Qwen3.5-35B",
    "qwen4b": "Qwen3-4B",
}
SCENARIOS = [
    "septic_shock_basic",
    "septic_shock_penicillin_allergy",
    "stemi_inferior_rv_trap",
    "dka_moderate_basic",
    "dka_hypokalemia_trap",
    "stroke_tpa_eligible",
    "contrast_aki_prevention_basic",
    "aki_stage1_basic",
    "af_new_onset_basic",
    "gi_bleeding_upper_basic",
    "htn_emergency_basic",
    "pe_submassive_basic",
    "copd_moderate_exacerbation",
    "adhf_warm_wet",
    "hemorrhagic_stroke",
]
N_RUNS = 3


def load_all_episodes() -> list[dict]:
    """Load all 180 rescored episodes."""
    episodes = []
    for model in MODELS:
        model_dir = RESCORED_DIR / model
        for f in sorted(model_dir.glob("*.json")):
            ep = json.loads(f.read_text())
            ep["model_key"] = model
            episodes.append(ep)
    return episodes


def build_scenario_means(
    episodes: list[dict], metric: str = "new_compliance_score", scenarios: list[str] | None = None
) -> dict[str, list[float]]:
    """Build {model: [scenario_mean_1, ..., scenario_mean_N]} for Friedman."""
    if scenarios is None:
        scenarios = SCENARIOS
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for ep in episodes:
        if ep["scenario_id"] in scenarios:
            grouped[ep["model_key"]][ep["scenario_id"]].append(ep[metric])
    result = {}
    for model in MODELS:
        means = []
        for sc in scenarios:
            vals = grouped[model].get(sc, [])
            means.append(statistics.mean(vals) if vals else 0.0)
        result[model] = means
    return result


def composite_a(ep: dict) -> float:
    """CGA * min(1, actions / (expected * 2))."""
    cga = ep["new_compliance_score"]
    acts = ep["actions_count"]
    exp = ep["n_expected_actions"]
    efficiency = min(1.0, acts / (exp * 2)) if exp > 0 else 0.0
    return cga * efficiency


def build_composite_scenario_means(
    episodes: list[dict], k: float = 2.0, scenarios: list[str] | None = None
) -> dict[str, list[float]]:
    """Build Composite A scenario means with configurable k."""
    if scenarios is None:
        scenarios = SCENARIOS
    grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for ep in episodes:
        if ep["scenario_id"] in scenarios:
            cga = ep["new_compliance_score"]
            acts = ep["actions_count"]
            exp = ep["n_expected_actions"]
            eff = min(1.0, acts / (exp * k)) if exp > 0 else 0.0
            val = cga * eff
            grouped[ep["model_key"]][ep["scenario_id"]].append(val)
    result = {}
    for model in MODELS:
        means = []
        for sc in scenarios:
            vals = grouped[model].get(sc, [])
            means.append(statistics.mean(vals) if vals else 0.0)
        result[model] = means
    return result


def friedman_test(scenario_means: dict[str, list[float]]) -> dict:
    """Run Friedman test. Returns stat, p, rankings."""
    arrays = [np.array(scenario_means[m]) for m in MODELS]
    # Guard: if all values identical across groups per scenario, Friedman is undefined
    stacked = np.column_stack(arrays)
    row_ranges = stacked.max(axis=1) - stacked.min(axis=1)
    if np.all(row_ranges < 1e-12):
        ranking = {MODELS[j]: 2.5 for j in range(len(MODELS))}
        return {"statistic": 0.0, "p_value": 1.0, "mean_ranks": ranking, "note": "constant_data"}
    stat, p = sp_stats.friedmanchisquare(*arrays)
    # Compute mean ranks
    n_scenarios = len(arrays[0])
    ranks = np.zeros((n_scenarios, len(MODELS)))
    for i in range(n_scenarios):
        vals = [arrays[j][i] for j in range(len(MODELS))]
        ranks[i] = sp_stats.rankdata([-v for v in vals])  # negative for descending
    mean_ranks = ranks.mean(axis=0)
    ranking = {MODELS[j]: round(float(mean_ranks[j]), 3) for j in range(len(MODELS))}
    return {"statistic": round(float(stat), 4), "p_value": round(float(p), 6), "mean_ranks": ranking}


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------


def analysis_1_loso_friedman(episodes: list[dict]) -> dict:
    """Leave-one-scenario-out Friedman (15 iterations)."""
    logger.info("Analysis 1: Leave-one-scenario-out Friedman")
    results = {}
    for drop_sc in SCENARIOS:
        remaining = [sc for sc in SCENARIOS if sc != drop_sc]
        sm = build_composite_scenario_means(episodes, k=2.0, scenarios=remaining)
        ft = friedman_test(sm)
        results[drop_sc] = {"p_value": ft["p_value"], "statistic": ft["statistic"]}

    p_vals = [v["p_value"] for v in results.values()]
    return {
        "iterations": results,
        "min_p": round(min(p_vals), 6),
        "max_p": round(max(p_vals), 6),
        "median_p": round(float(np.median(p_vals)), 6),
        "all_significant_005": all(p < 0.05 for p in p_vals),
        "n_significant_005": sum(1 for p in p_vals if p < 0.05),
    }


def analysis_2_run_consistency(episodes: list[dict]) -> dict:
    """Per-run Friedman (r0, r1, r2 separately)."""
    logger.info("Analysis 2: Run-level consistency")
    results = {}
    for run_idx in range(N_RUNS):
        run_eps = [ep for ep in episodes if ep["run_index"] == run_idx]
        sm = build_composite_scenario_means(run_eps, k=2.0)
        ft = friedman_test(sm)
        results[f"run_{run_idx}"] = ft

    # Also test CGA alone per run
    cga_results = {}
    for run_idx in range(N_RUNS):
        run_eps = [ep for ep in episodes if ep["run_index"] == run_idx]
        sm = build_scenario_means(run_eps, "new_compliance_score")
        ft = friedman_test(sm)
        cga_results[f"run_{run_idx}"] = ft

    return {"composite_a": results, "cga_alone": cga_results}


def analysis_3_holm_correction(episodes: list[dict]) -> dict:
    """Holm-Bonferroni correction on pre-defined 2-test family."""
    logger.info("Analysis 3: Holm correction")
    # Test 1: CGA alone Friedman
    sm_cga = build_scenario_means(episodes, "new_compliance_score")
    ft_cga = friedman_test(sm_cga)

    # Test 2: Composite A Friedman
    sm_comp = build_composite_scenario_means(episodes, k=2.0)
    ft_comp = friedman_test(sm_comp)

    p_values = [("CGA_alone", ft_cga["p_value"]), ("Composite_A", ft_comp["p_value"])]
    # Sort by p-value ascending
    p_sorted = sorted(p_values, key=lambda x: x[1])
    m = len(p_sorted)
    holm_results = []
    for i, (name, p) in enumerate(p_sorted):
        adjusted_alpha = 0.05 / (m - i)
        significant = p < adjusted_alpha
        holm_results.append(
            {
                "test": name,
                "raw_p": round(p, 6),
                "holm_alpha": round(adjusted_alpha, 6),
                "significant": significant,
            }
        )

    return {
        "family_size": m,
        "results": holm_results,
        "cga_friedman": ft_cga,
        "composite_friedman": ft_comp,
    }


def analysis_4_k_sensitivity(episodes: list[dict]) -> dict:
    """k-space sensitivity: k=0.5 to 4.0."""
    logger.info("Analysis 4: k-space sensitivity")
    k_values = [round(0.5 + i * 0.1, 1) for i in range(36)]  # 0.5 to 4.0 step 0.1
    results = {}
    for k in k_values:
        sm = build_composite_scenario_means(episodes, k=k)
        ft = friedman_test(sm)
        # Model averages
        model_avgs = {m: round(float(np.mean(sm[m])), 4) for m in MODELS}
        results[str(k)] = {
            "p_value": ft["p_value"],
            "statistic": ft["statistic"],
            "mean_ranks": ft["mean_ranks"],
            "model_averages": model_avgs,
        }

    sig_range = [k for k in k_values if results[str(k)]["p_value"] < 0.05]
    return {
        "k_results": results,
        "significant_k_range": [min(sig_range), max(sig_range)] if sig_range else [],
        "n_significant": len(sig_range),
        "n_total": len(k_values),
    }


def analysis_5_bootstrap_ci(episodes: list[dict], n_iter: int = 10000) -> dict:
    """Bootstrap 95% CI for each model's mean CGA and Composite A."""
    logger.info(f"Analysis 5: Bootstrap 95% CI ({n_iter} iterations)")
    rng = np.random.default_rng(42)

    results = {}
    for model in MODELS:
        model_eps = [ep for ep in episodes if ep["model_key"] == model]
        cga_vals = np.array([ep["new_compliance_score"] for ep in model_eps])
        comp_vals = np.array([composite_a(ep) for ep in model_eps])

        # Bootstrap CGA
        cga_boots = np.array([np.mean(rng.choice(cga_vals, size=len(cga_vals), replace=True)) for _ in range(n_iter)])
        # Bootstrap Composite A
        comp_boots = np.array(
            [np.mean(rng.choice(comp_vals, size=len(comp_vals), replace=True)) for _ in range(n_iter)]
        )

        results[model] = {
            "cga_mean": round(float(np.mean(cga_vals)), 4),
            "cga_ci_lower": round(float(np.percentile(cga_boots, 2.5)), 4),
            "cga_ci_upper": round(float(np.percentile(cga_boots, 97.5)), 4),
            "composite_mean": round(float(np.mean(comp_vals)), 4),
            "composite_ci_lower": round(float(np.percentile(comp_boots, 2.5)), 4),
            "composite_ci_upper": round(float(np.percentile(comp_boots, 97.5)), 4),
        }

    # Check CI overlap between adjacent ranked models
    ranked = sorted(MODELS, key=lambda m: results[m]["composite_mean"], reverse=True)
    overlaps = []
    for i in range(len(ranked) - 1):
        m1, m2 = ranked[i], ranked[i + 1]
        overlap = results[m1]["composite_ci_lower"] < results[m2]["composite_ci_upper"]
        overlaps.append(
            {
                "pair": f"{m1} vs {m2}",
                "overlap": overlap,
                "gap": round(results[m1]["composite_ci_lower"] - results[m2]["composite_ci_upper"], 4),
            }
        )

    return {"models": results, "ranking": ranked, "ci_overlaps": overlaps}


def analysis_6_subconstruct_profiles(episodes: list[dict]) -> dict:
    """C1-C5 sub-construct profiles per model."""
    logger.info("Analysis 6: Sub-construct C1-C5 profiles")
    constructs = [
        "C1_path_selection",
        "C2_mandatory_completion",
        "C3_forbidden_avoidance",
        "C4_timing_compliance",
        "C5_sequence_integrity",
    ]
    results = {}
    for model in MODELS:
        model_eps = [ep for ep in episodes if ep["model_key"] == model]
        profile = {}
        for c in constructs:
            vals = [ep["new_sub_scores"].get(c, 0.0) for ep in model_eps]
            profile[c] = {
                "mean": round(statistics.mean(vals), 4),
                "std": round(statistics.stdev(vals), 4) if len(vals) > 1 else 0.0,
                "min": round(min(vals), 4),
                "max": round(max(vals), 4),
            }
        results[model] = profile

    # Friedman per construct
    construct_friedman = {}
    for c in constructs:
        grouped: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
        for ep in episodes:
            grouped[ep["model_key"]][ep["scenario_id"]].append(ep["new_sub_scores"].get(c, 0.0))
        sm = {}
        for model in MODELS:
            means = []
            for sc in SCENARIOS:
                vals = grouped[model].get(sc, [])
                means.append(statistics.mean(vals) if vals else 0.0)
            sm[model] = means
        ft = friedman_test(sm)
        construct_friedman[c] = ft

    return {"profiles": results, "friedman_per_construct": construct_friedman}


def analysis_7_point_biserial(episodes: list[dict]) -> dict:
    """Point-biserial r: CGA vs task completion, C2 >= threshold."""
    logger.info("Analysis 7: Point-biserial correlations")

    # Task completion: actions_count > 0
    cga_vals = np.array([ep["new_compliance_score"] for ep in episodes])
    task_completed = np.array([1 if ep["actions_count"] > 0 else 0 for ep in episodes])

    # Point-biserial: CGA vs task completion
    if task_completed.sum() > 0 and task_completed.sum() < len(task_completed):
        r_task, p_task = sp_stats.pointbiserialr(task_completed, cga_vals)
    else:
        r_task, p_task = 0.0, 1.0

    # C2 >= threshold correlations
    thresholds = [0.5, 0.6, 0.7, 0.8, 0.9]
    c2_correlations = {}
    for t in thresholds:
        c2_vals = np.array([ep["new_sub_scores"].get("C2_mandatory_completion", 0.0) for ep in episodes])
        c2_binary = (c2_vals >= t).astype(int)
        if c2_binary.sum() > 0 and c2_binary.sum() < len(c2_binary):
            r, p = sp_stats.pointbiserialr(c2_binary, cga_vals)
        else:
            r, p = 0.0, 1.0
        c2_correlations[str(t)] = {
            "r": round(float(r), 4),
            "p": round(float(p), 6),
            "n_above": int(c2_binary.sum()),
            "pct_above": round(float(c2_binary.mean() * 100), 1),
        }

    # Spearman: model size vs mean CGA
    model_sizes = {"oss120b": 671, "qwen27b": 27, "qwen35b": 35, "qwen4b": 4}
    sizes = []
    mean_cgas = []
    for m in MODELS:
        sizes.append(model_sizes[m])
        model_cgas = [ep["new_compliance_score"] for ep in episodes if ep["model_key"] == m]
        mean_cgas.append(statistics.mean(model_cgas))
    rho, p_rho = sp_stats.spearmanr(sizes, mean_cgas)

    return {
        "cga_vs_task_completion": {"r": round(float(r_task), 4), "p": round(float(p_task), 6)},
        "c2_threshold_correlations": c2_correlations,
        "size_vs_cga_spearman": {"rho": round(float(rho), 4), "p": round(float(p_rho), 6)},
    }


def analysis_8_q2_rederivation(episodes: list[dict]) -> dict:
    """Q2 re-derivation: optimal C2 threshold for model differentiation."""
    logger.info("Analysis 8: Q2 re-derivation")
    thresholds = np.arange(0.1, 1.01, 0.05)
    results = {}

    for t in thresholds:
        t_val = round(float(t), 2)
        pass_rates = {}
        for model in MODELS:
            model_eps = [ep for ep in episodes if ep["model_key"] == model]
            c2_vals = [ep["new_sub_scores"].get("C2_mandatory_completion", 0.0) for ep in model_eps]
            n_pass = sum(1 for v in c2_vals if v >= t_val)
            pass_rates[model] = round(n_pass / len(model_eps), 4) if model_eps else 0.0

        # Spread = max - min pass rate (model differentiation)
        rates = list(pass_rates.values())
        spread = max(rates) - min(rates) if rates else 0.0
        overall_pass = sum(
            1 for ep in episodes if ep["new_sub_scores"].get("C2_mandatory_completion", 0.0) >= t_val
        ) / len(episodes)

        results[str(t_val)] = {
            "pass_rates": pass_rates,
            "spread": round(spread, 4),
            "overall_pass_rate": round(overall_pass, 4),
        }

    # Find optimal: maximize spread while keeping overall pass > 20% and < 80%
    best_threshold = 0.7
    best_score = -1
    for t_str, v in results.items():
        t_val = float(t_str)
        if 0.15 <= v["overall_pass_rate"] <= 0.85:
            score = v["spread"]
            if score > best_score:
                best_score = score
                best_threshold = t_val

    return {
        "thresholds": results,
        "recommended_threshold": round(best_threshold, 2),
        "recommended_spread": round(best_score, 4),
    }


def analysis_9_violation_cooccurrence(episodes: list[dict]) -> dict:
    """Violation co-occurrence matrix."""
    logger.info("Analysis 9: Violation co-occurrence matrix")
    vtypes = ["omission", "commission", "timing", "sequence", "deviation"]

    # Count episodes with each type
    type_counts = dict.fromkeys(vtypes, 0)
    cooccurrence = {t1: dict.fromkeys(vtypes, 0) for t1 in vtypes}

    for ep in episodes:
        vbt = ep.get("new_violations_by_type", {})
        present = {t for t in vtypes if vbt.get(t, 0) > 0}
        for t in present:
            type_counts[t] += 1
        for t1, t2 in combinations(present, 2):
            cooccurrence[t1][t2] += 1
            cooccurrence[t2][t1] += 1
        for t in present:
            cooccurrence[t][t] += 1

    # Normalize to percentages
    n = len(episodes)
    type_prevalence = {t: round(type_counts[t] / n * 100, 1) for t in vtypes}

    # Conditional probability: P(B | A)
    conditional = {}
    for t1 in vtypes:
        conditional[t1] = {}
        for t2 in vtypes:
            if t1 == t2:
                conditional[t1][t2] = 100.0
            elif type_counts[t1] > 0:
                conditional[t1][t2] = round(cooccurrence[t1][t2] / type_counts[t1] * 100, 1)
            else:
                conditional[t1][t2] = 0.0

    return {
        "type_prevalence_pct": type_prevalence,
        "cooccurrence_counts": cooccurrence,
        "conditional_probability_pct": conditional,
        "n_episodes": n,
    }


def analysis_10_sample_size_simulation(episodes: list[dict]) -> dict:
    """Required sample size simulation via power analysis."""
    logger.info("Analysis 10: Sample size simulation")
    rng = np.random.default_rng(42)

    # Get per-scenario composite means for each model
    sm = build_composite_scenario_means(episodes, k=2.0)

    # Simulation: subsample N scenarios, check if Friedman p < 0.05
    scenario_counts = [5, 7, 8, 9, 10, 11, 12, 13, 14, 15]
    n_simulations = 2000
    results = {}

    for n_sc in scenario_counts:
        sig_count = 0
        for _ in range(n_simulations):
            indices = rng.choice(len(SCENARIOS), size=n_sc, replace=False)
            sub_sm = {m: [sm[m][i] for i in indices] for m in MODELS}
            try:
                arrays = [np.array(sub_sm[m]) for m in MODELS]
                _, p = sp_stats.friedmanchisquare(*arrays)
                if p < 0.05:
                    sig_count += 1
            except Exception:
                pass
        power = sig_count / n_simulations
        results[str(n_sc)] = {
            "power": round(power, 3),
            "n_significant": sig_count,
            "n_simulations": n_simulations,
        }

    # Find minimum N for power >= 0.80
    min_n_80 = None
    for n_sc in scenario_counts:
        if results[str(n_sc)]["power"] >= 0.80:
            min_n_80 = n_sc
            break

    return {
        "scenario_counts": results,
        "min_scenarios_power_80": min_n_80,
        "current_scenarios": len(SCENARIOS),
    }


def analysis_11_q4_adhf_manual(episodes: list[dict]) -> dict:
    """Q4 manual verification: adhf_warm_wet / qwen4b / r0."""
    logger.info("Analysis 11: Q4 ADHF manual verification")
    ADHF_EXPECTED = [
        "iv_diuretics",
        "fluid_restrict",
        "daily_weights",
        "monitor_urine_output",
        "monitor_electrolytes",
        "continuous_monitoring",
    ]
    # Find the target episode
    target = None
    for ep in episodes:
        if ep["scenario_id"] == "adhf_warm_wet" and ep["model_key"] == "qwen4b" and ep["run_index"] == 0:
            target = ep
            break
    if target is None:
        return {"error": "Target episode not found"}

    # Load original episode for action list
    orig_dir = Path("results/clean_slate_20260331_210910/qwen4b")
    orig_actions = []
    for f in orig_dir.glob("adhf_warm_wet_*r0*.json"):
        orig_data = json.loads(f.read_text())
        orig_actions = [a["action_id"] for a in orig_data.get("actions", [])]
        break

    # Manual matching using ActionNormalizer logic (simplified)
    from cga_bench.assessor_core.action_normalizer import ActionNormalizer

    normalizer = ActionNormalizer()
    cpg_id = "aha_heart_failure"

    performed_norm = {normalizer.normalize(a, cpg_id) for a in orig_actions}
    manual_matches = {}
    for exp_act in ADHF_EXPECTED:
        exp_norm = normalizer.normalize(exp_act, cpg_id)
        matched = exp_norm in performed_norm
        manual_matches[exp_act] = {
            "normalized": exp_norm,
            "matched": matched,
        }

    n_matched = sum(1 for v in manual_matches.values() if v["matched"])
    manual_c2 = 1.0 - (len(ADHF_EXPECTED) - n_matched) / max(len(ADHF_EXPECTED), 1)
    code_c2 = target["new_sub_scores"].get("C2_mandatory_completion", 0.0)

    return {
        "scenario_id": "adhf_warm_wet",
        "model": "qwen4b",
        "run_index": 0,
        "expected_actions": ADHF_EXPECTED,
        "performed_actions_raw": orig_actions[:20],  # first 20 for display
        "performed_actions_count": len(orig_actions),
        "manual_matches": manual_matches,
        "manual_matched": n_matched,
        "manual_c2": round(manual_c2, 4),
        "code_c2": round(code_c2, 4),
        "code_cga": round(target["new_compliance_score"], 4),
        "old_cga": round(target["old_compliance_score"], 4),
        "agreement": abs(manual_c2 - code_c2) < 0.01,
    }


def analysis_12_q2_episodes(episodes: list[dict]) -> dict:
    """Q2 episode listing: C2>=0.7 AND CGA<0.5."""
    logger.info("Analysis 12: Q2 episode listing")
    c2_threshold = 0.7
    cga_threshold = 0.5

    q2_episodes = []
    for ep in episodes:
        c2 = ep["new_sub_scores"].get("C2_mandatory_completion", 0.0)
        cga = ep["new_compliance_score"]
        if c2 >= c2_threshold and cga < cga_threshold:
            q2_episodes.append(
                {
                    "scenario_id": ep["scenario_id"],
                    "model": ep["model_key"],
                    "run_index": ep["run_index"],
                    "c2": round(c2, 4),
                    "cga": round(cga, 4),
                    "actions_count": ep["actions_count"],
                    "total_violations": ep["new_total_violations"],
                }
            )

    # Distribution
    model_counts = defaultdict(int)
    scenario_counts = defaultdict(int)
    for q in q2_episodes:
        model_counts[q["model"]] += 1
        scenario_counts[q["scenario_id"]] += 1

    # Also count inverse: CGA>=0.5 but C2<0.7
    inverse = sum(
        1
        for ep in episodes
        if ep["new_compliance_score"] >= cga_threshold
        and ep["new_sub_scores"].get("C2_mandatory_completion", 0.0) < c2_threshold
    )

    return {
        "c2_threshold": c2_threshold,
        "cga_threshold": cga_threshold,
        "q2_count": len(q2_episodes),
        "q2_episodes": q2_episodes,
        "by_model": dict(model_counts),
        "by_scenario": dict(scenario_counts),
        "inverse_count": inverse,
        "total_episodes": len(episodes),
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(all_results: dict) -> str:
    """Generate FINAL_NUMBERS_CLEAN_V2.md."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S UTC")
    lines = [
        "# FINAL NUMBERS — Clean Slate V2 (Rescored)",
        "",
        f"**Generated**: {ts}",
        "**Pipeline**: R1-R5 fixes applied, R6 re-scored 180 episodes",
        "**Data**: `results/clean_slate_rescored/` (4 models x 15 scenarios x 3 runs)",
        "**JSON source**: `evidence_pack/analysis/robustness_clean_v2.json`",
        "",
        "---",
        "",
    ]

    # Section 1: LOSO Friedman
    loso = all_results["loso_friedman"]
    lines.extend(
        [
            "## 1. Leave-One-Scenario-Out Friedman (Composite A, k=2)",
            "",
            "| Dropped Scenario | Friedman p | Chi-sq |",
            "|:---|---:|---:|",
        ]
    )
    for sc, v in sorted(loso["iterations"].items()):
        sig = "***" if v["p_value"] < 0.001 else "**" if v["p_value"] < 0.01 else "*" if v["p_value"] < 0.05 else "ns"
        lines.append(f"| {sc} | {v['p_value']:.4f} {sig} | {v['statistic']:.2f} |")
    lines.extend(
        [
            "",
            f"- **p range**: [{loso['min_p']:.4f}, {loso['max_p']:.4f}], median={loso['median_p']:.4f}",
            f"- **Significant at 0.05**: {loso['n_significant_005']}/15 ({loso['all_significant_005']})",
            "",
        ]
    )

    # Section 2: Run-level consistency
    run_cons = all_results["run_consistency"]
    lines.extend(
        [
            "## 2. Run-Level Consistency",
            "",
            "### Composite A (per-run Friedman)",
            "",
            "| Run | Chi-sq | p-value | Rank 1 |",
            "|:---|---:|---:|:---|",
        ]
    )
    for run_key, ft in sorted(run_cons["composite_a"].items()):
        rank1 = min(ft["mean_ranks"], key=ft["mean_ranks"].get)
        sig = "*" if ft["p_value"] < 0.05 else "ns"
        lines.append(f"| {run_key} | {ft['statistic']:.2f} | {ft['p_value']:.4f} {sig} | {rank1} |")

    lines.extend(
        [
            "",
            "### CGA Alone (per-run Friedman)",
            "",
            "| Run | Chi-sq | p-value | Rank 1 |",
            "|:---|---:|---:|:---|",
        ]
    )
    for run_key, ft in sorted(run_cons["cga_alone"].items()):
        rank1 = min(ft["mean_ranks"], key=ft["mean_ranks"].get)
        sig = "*" if ft["p_value"] < 0.05 else "ns"
        lines.append(f"| {run_key} | {ft['statistic']:.2f} | {ft['p_value']:.4f} {sig} | {rank1} |")
    lines.append("")

    # Section 3: Holm correction
    holm = all_results["holm_correction"]
    lines.extend(
        [
            "## 3. Holm-Bonferroni Correction (2-test family)",
            "",
            "| Test | Raw p | Holm alpha | Significant |",
            "|:---|---:|---:|:---:|",
        ]
    )
    for r in holm["results"]:
        lines.append(
            f"| {r['test']} | {r['raw_p']:.6f} | {r['holm_alpha']:.4f} | {'Yes' if r['significant'] else 'No'} |"
        )
    lines.extend(
        [
            "",
            f"- CGA alone Friedman: chi-sq={holm['cga_friedman']['statistic']}, p={holm['cga_friedman']['p_value']}",
            f"- Composite A Friedman: chi-sq={holm['composite_friedman']['statistic']}, p={holm['composite_friedman']['p_value']}",
            "",
        ]
    )

    # Section 4: k-space sensitivity
    k_sens = all_results["k_sensitivity"]
    lines.extend(
        [
            "## 4. k-Space Sensitivity (Composite A = CGA * min(1, acts/(exp*k)))",
            "",
            "| k | Friedman p | Rank 1 | Rank 2 | Rank 3 | Rank 4 |",
            "|---:|---:|:---|:---|:---|:---|",
        ]
    )
    for k_str, v in sorted(k_sens["k_results"].items(), key=lambda x: float(x[0])):
        ranked = sorted(v["mean_ranks"].items(), key=lambda x: x[1])
        sig = "*" if v["p_value"] < 0.05 else "ns"
        lines.append(
            f"| {k_str} | {v['p_value']:.4f} {sig} | "
            f"{ranked[0][0]}({ranked[0][1]:.1f}) | "
            f"{ranked[1][0]}({ranked[1][1]:.1f}) | "
            f"{ranked[2][0]}({ranked[2][1]:.1f}) | "
            f"{ranked[3][0]}({ranked[3][1]:.1f}) |"
        )
    lines.extend(
        [
            "",
            f"- **Significant range**: k={k_sens['significant_k_range'][0]}..{k_sens['significant_k_range'][1]}"
            if k_sens["significant_k_range"]
            else "- **No significant k found**",
            f"- **Significant count**: {k_sens['n_significant']}/{k_sens['n_total']}",
            "",
        ]
    )

    # Section 5: Bootstrap CI
    boot = all_results["bootstrap_ci"]
    lines.extend(
        [
            "## 5. Bootstrap 95% Confidence Intervals (10,000 iterations)",
            "",
            "| Model | CGA Mean | CGA 95% CI | Comp A Mean | Comp A 95% CI |",
            "|:---|---:|:---|---:|:---|",
        ]
    )
    for m in boot["ranking"]:
        r = boot["models"][m]
        lines.append(
            f"| {MODEL_LABELS.get(m, m)} | {r['cga_mean']:.4f} | "
            f"[{r['cga_ci_lower']:.4f}, {r['cga_ci_upper']:.4f}] | "
            f"{r['composite_mean']:.4f} | "
            f"[{r['composite_ci_lower']:.4f}, {r['composite_ci_upper']:.4f}] |"
        )
    lines.extend(
        [
            "",
            "### CI Overlap Check",
            "",
        ]
    )
    for o in boot["ci_overlaps"]:
        lines.append(f"- {o['pair']}: {'OVERLAP' if o['overlap'] else 'SEPARATED'} (gap={o['gap']:.4f})")
    lines.append("")

    # Section 6: Sub-construct profiles
    profiles = all_results["subconstruct_profiles"]
    lines.extend(
        [
            "## 6. Sub-Construct C1-C5 Profiles",
            "",
            "| Model | C1 Path | C2 Mandatory | C3 Forbidden | C4 Timing | C5 Sequence |",
            "|:---|---:|---:|---:|---:|---:|",
        ]
    )
    for m in MODELS:
        p = profiles["profiles"][m]
        lines.append(
            f"| {MODEL_LABELS.get(m, m)} | "
            f"{p['C1_path_selection']['mean']:.3f} | "
            f"{p['C2_mandatory_completion']['mean']:.3f} | "
            f"{p['C3_forbidden_avoidance']['mean']:.3f} | "
            f"{p['C4_timing_compliance']['mean']:.3f} | "
            f"{p['C5_sequence_integrity']['mean']:.3f} |"
        )
    lines.extend(
        [
            "",
            "### Per-Construct Friedman",
            "",
            "| Construct | Chi-sq | p-value |",
            "|:---|---:|---:|",
        ]
    )
    for c, ft in profiles["friedman_per_construct"].items():
        sig = "*" if ft["p_value"] < 0.05 else "ns"
        lines.append(f"| {c} | {ft['statistic']:.2f} | {ft['p_value']:.4f} {sig} |")
    lines.append("")

    # Section 7: Point-biserial
    pb = all_results["point_biserial"]
    lines.extend(
        [
            "## 7. Point-Biserial Correlations",
            "",
            f"- **CGA vs Task Completion**: r={pb['cga_vs_task_completion']['r']}, p={pb['cga_vs_task_completion']['p']}",
            f"- **Model Size vs CGA (Spearman)**: rho={pb['size_vs_cga_spearman']['rho']}, p={pb['size_vs_cga_spearman']['p']}",
            "",
            "### C2 Threshold Correlations (C2 >= t vs CGA)",
            "",
            "| Threshold | r | p | N above | % above |",
            "|---:|---:|---:|---:|---:|",
        ]
    )
    for t, v in sorted(pb["c2_threshold_correlations"].items()):
        sig = "*" if v["p"] < 0.05 else "ns"
        lines.append(f"| {t} | {v['r']:.4f} | {v['p']:.6f} {sig} | {v['n_above']} | {v['pct_above']}% |")
    lines.append("")

    # Section 8: Q2 re-derivation
    q2 = all_results["q2_rederivation"]
    lines.extend(
        [
            "## 8. Q2 Re-Derivation: Optimal C2 Threshold",
            "",
            f"**Recommended threshold**: C2 >= {q2['recommended_threshold']}",
            f"**Spread (max differentiation)**: {q2['recommended_spread']}",
            "",
            "| Threshold | oss120b | qwen27b | qwen35b | qwen4b | Spread | Overall |",
            "|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for t_str in sorted(q2["thresholds"].keys(), key=float):
        v = q2["thresholds"][t_str]
        pr = v["pass_rates"]
        lines.append(
            f"| {t_str} | {pr.get('oss120b', 0):.2f} | {pr.get('qwen27b', 0):.2f} | "
            f"{pr.get('qwen35b', 0):.2f} | {pr.get('qwen4b', 0):.2f} | "
            f"{v['spread']:.3f} | {v['overall_pass_rate']:.2f} |"
        )
    lines.append("")

    # Section 9: Violation co-occurrence
    vc = all_results["violation_cooccurrence"]
    lines.extend(
        [
            "## 9. Violation Co-Occurrence Matrix",
            "",
            "### Type Prevalence",
            "",
        ]
    )
    for t, pct in vc["type_prevalence_pct"].items():
        lines.append(f"- **{t}**: {pct}% of episodes")
    lines.extend(
        [
            "",
            "### Conditional Probability P(col | row) %",
            "",
            "| | omission | commission | timing | sequence | deviation |",
            "|:---|---:|---:|---:|---:|---:|",
        ]
    )
    for t1 in ["omission", "commission", "timing", "sequence", "deviation"]:
        cp = vc["conditional_probability_pct"][t1]
        lines.append(
            f"| {t1} | {cp.get('omission', 0):.0f} | {cp.get('commission', 0):.0f} | "
            f"{cp.get('timing', 0):.0f} | {cp.get('sequence', 0):.0f} | {cp.get('deviation', 0):.0f} |"
        )
    lines.append("")

    # Section 10: Sample size
    ss = all_results["sample_size_simulation"]
    lines.extend(
        [
            "## 10. Sample Size Simulation (Power Analysis)",
            "",
            "| N Scenarios | Power | Significant/2000 |",
            "|---:|---:|---:|",
        ]
    )
    for n_str, v in sorted(ss["scenario_counts"].items(), key=lambda x: int(x[0])):
        marker = "<--" if int(n_str) == ss.get("min_scenarios_power_80") else ""
        lines.append(f"| {n_str} | {v['power']:.3f} | {v['n_significant']} | {marker}")
    lines.extend(
        [
            "",
            f"- **Minimum for 80% power**: {ss['min_scenarios_power_80']} scenarios",
            f"- **Current**: {ss['current_scenarios']} scenarios",
            "",
        ]
    )

    # Section 11: Q4 ADHF manual verification
    if "q4_adhf_manual" in all_results:
        q4 = all_results["q4_adhf_manual"]
        if "error" not in q4:
            lines.extend(
                [
                    "## 11. Q4 Manual Verification: ADHF warm_wet / qwen4b / r0",
                    "",
                    f"- **Old CGA**: {q4['old_cga']}, **New CGA**: {q4['code_cga']}",
                    f"- **Performed actions**: {q4['performed_actions_count']}",
                    f"- **Expected actions**: {len(q4['expected_actions'])}",
                    "",
                    "| Expected Action | Normalized | Matched |",
                    "|:---|:---|:---:|",
                ]
            )
            for act, info in q4["manual_matches"].items():
                mark = "Y" if info["matched"] else "N"
                lines.append(f"| {act} | {info['normalized']} | {mark} |")
            lines.extend(
                [
                    "",
                    f"- **Manual C2**: {q4['manual_c2']} ({q4['manual_matched']}/{len(q4['expected_actions'])})",
                    f"- **Code C2**: {q4['code_c2']}",
                    f"- **Agreement**: {'YES' if q4['agreement'] else 'NO (delta=' + str(round(abs(q4['manual_c2'] - q4['code_c2']), 4)) + ')'}",
                    "",
                ]
            )

    # Section 12: Q2 episodes
    if "q2_episodes" in all_results:
        q2e = all_results["q2_episodes"]
        lines.extend(
            [
                f"## 12. Q2 Episodes (C2>={q2e['c2_threshold']} AND CGA<{q2e['cga_threshold']})",
                "",
                f"- **Q2 count**: {q2e['q2_count']}/{q2e['total_episodes']} ({round(q2e['q2_count'] / q2e['total_episodes'] * 100, 1)}%)",
                f"- **Inverse (CGA>={q2e['cga_threshold']} but C2<{q2e['c2_threshold']})**: {q2e['inverse_count']}",
                "",
                "### By Model",
                "",
            ]
        )
        for m, c in sorted(q2e.get("by_model", {}).items()):
            lines.append(f"- **{MODEL_LABELS.get(m, m)}**: {c}")
        lines.extend(["", "### By Scenario", ""])
        for sc, c in sorted(q2e.get("by_scenario", {}).items(), key=lambda x: -x[1]):
            lines.append(f"- **{sc}**: {c}")

        if q2e["q2_episodes"]:
            lines.extend(
                [
                    "",
                    "### Episode List",
                    "",
                    "| Scenario | Model | Run | C2 | CGA | Actions | Violations |",
                    "|:---|:---|---:|---:|---:|---:|---:|",
                ]
            )
            for ep in sorted(q2e["q2_episodes"], key=lambda x: -x["c2"]):
                lines.append(
                    f"| {ep['scenario_id']} | {ep['model']} | {ep['run_index']} | "
                    f"{ep['c2']:.3f} | {ep['cga']:.3f} | {ep['actions_count']} | {ep['total_violations']} |"
                )
        lines.append("")

    # Summary table
    loso = all_results["loso_friedman"]
    run_cons = all_results["run_consistency"]
    holm = all_results["holm_correction"]
    k_sens = all_results["k_sensitivity"]
    boot = all_results["bootstrap_ci"]
    n_ci_separated = sum(1 for o in boot["ci_overlaps"] if not o["overlap"])
    q4 = all_results.get("q4_adhf_manual", {})
    q2e = all_results.get("q2_episodes", {})
    run_ps = [run_cons["composite_a"][f"run_{i}"]["p_value"] for i in range(3)]

    lines.extend(
        [
            "## Summary",
            "",
            "| Check | Result | Verdict |",
            "|:---|:---|:---:|",
            f"| LOSO 15/15 sig? | {loso['n_significant_005']}/15 | {'PASS' if loso['all_significant_005'] else 'PARTIAL'} |",
            f"| Run r0/r1/r2 consistency | p={run_ps[0]:.4f}/{run_ps[1]:.4f}/{run_ps[2]:.4f} | {'PASS' if all(p < 0.05 for p in run_ps) else 'PARTIAL'} |",
            f"| Holm Composite A | p={holm['composite_friedman']['p_value']} | {'PASS' if any(r['significant'] and r['test'] == 'Composite_A' for r in holm['results']) else 'FAIL'} |",
            f"| k-space sig range | k={k_sens['significant_k_range'][0]}..{k_sens['significant_k_range'][1]} | {'PASS' if k_sens['n_significant'] >= 5 else 'PARTIAL'} |"
            if k_sens["significant_k_range"]
            else "| k-space sig range | none | FAIL |",
            f"| Bootstrap CI separated | {n_ci_separated}/3 pairs | {'PASS' if n_ci_separated >= 2 else 'PARTIAL'} |",
            f"| ADHF manual match | {q4.get('manual_matched', '?')}/{len(q4.get('expected_actions', []))} (C2 agree: {q4.get('agreement', '?')}) | {'PASS' if q4.get('agreement') else 'CHECK'} |",
            f"| Q2 episodes | {q2e.get('q2_count', '?')} | INFO |",
            "",
        ]
    )

    # Footer
    lines.extend(
        [
            "---",
            "",
            "*Generated by `scripts/experiments/robustness_analysis.py`*",
            "*Source data: `results/clean_slate_rescored/` (180 episodes)*",
        ]
    )

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    logger.info("Loading 180 rescored episodes...")
    episodes = load_all_episodes()
    logger.info(f"Loaded {len(episodes)} episodes across {len(MODELS)} models")

    all_results = {}

    all_results["loso_friedman"] = analysis_1_loso_friedman(episodes)
    all_results["run_consistency"] = analysis_2_run_consistency(episodes)
    all_results["holm_correction"] = analysis_3_holm_correction(episodes)
    all_results["k_sensitivity"] = analysis_4_k_sensitivity(episodes)
    all_results["bootstrap_ci"] = analysis_5_bootstrap_ci(episodes)
    all_results["subconstruct_profiles"] = analysis_6_subconstruct_profiles(episodes)
    all_results["point_biserial"] = analysis_7_point_biserial(episodes)
    all_results["q2_rederivation"] = analysis_8_q2_rederivation(episodes)
    all_results["violation_cooccurrence"] = analysis_9_violation_cooccurrence(episodes)
    all_results["sample_size_simulation"] = analysis_10_sample_size_simulation(episodes)
    all_results["q4_adhf_manual"] = analysis_11_q4_adhf_manual(episodes)
    all_results["q2_episodes"] = analysis_12_q2_episodes(episodes)

    # Save JSON
    OUTPUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_JSON, "w") as f:
        json.dump(all_results, f, indent=2, default=str)
    logger.info(f"JSON saved: {OUTPUT_JSON}")

    # Generate report
    report = generate_report(all_results)
    with open(OUTPUT_MD, "w") as f:
        f.write(report)
    logger.info(f"Report saved: {OUTPUT_MD}")

    # Print summary
    logger.info("\n" + "=" * 60)
    logger.info("ROBUSTNESS ANALYSIS COMPLETE")
    logger.info("=" * 60)
    logger.info(f"  LOSO: {all_results['loso_friedman']['n_significant_005']}/15 significant")
    logger.info(f"  Holm: {sum(1 for r in all_results['holm_correction']['results'] if r['significant'])}/2 survive")
    logger.info(f"  k-range: {all_results['k_sensitivity']['significant_k_range']}")
    logger.info(f"  Min power 80%: {all_results['sample_size_simulation']['min_scenarios_power_80']} scenarios")
    logger.info(f"  Recommended C2 threshold: {all_results['q2_rederivation']['recommended_threshold']}")


if __name__ == "__main__":
    main()
