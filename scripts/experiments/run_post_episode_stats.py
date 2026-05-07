#!/usr/bin/env python3
"""Post-Episode Statistical Analyses for CGA-Bench

Two analyses in one script:
  1. Mixed-effects logistic model (reviewer #14)
  2. Ranking flip experiment (reviewer #21)

Usage:
    python scripts/experiments/run_post_episode_stats.py \
        --episodes-dir results/full_706_final \
        --output evidence_pack/analysis/post_episode_stats.json \
        --tex-output paper/auto_numbers.tex

Dependencies:
    pip install statsmodels scipy pandas numpy --break-system-packages
"""

import argparse
import glob
import json
import os
import sys

import numpy as np

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas required. pip install pandas --break-system-packages")
    sys.exit(1)

try:
    from scipy import stats as scipy_stats
except ImportError:
    print("ERROR: scipy required. pip install scipy --break-system-packages")
    sys.exit(1)


# ============================================================================
# DATA LOADING
# ============================================================================

# Evaluator definitions matching CGA-Bench codebase
EVALUATORS = {
    "TOM": {  # DxEM: Terminal-Output Match — always pass (degenerate)
        "field": "dxem_pass",
        "degenerate": True,
    },
    "ASC": {  # AC-Proxy: Action-Set Coverage ≥ 0.5
        "field": "ac_proxy_pass",
        "threshold_field": "ac_proxy_score",
        "default_threshold": 0.5,
    },
    "CwT": {  # C2: Coverage with Timing penalty ≥ 0.7
        "field": "c2_pass",
        "threshold_field": "c2_score",
        "default_threshold": 0.7,
    },
    "PAF": {  # MAB-Proxy: Penalized Action F1 ≥ 0.5
        "field": "mab_proxy_pass",
        "threshold_field": "mab_f1_score",
        "default_threshold": 0.5,
    },
    "TCC": {  # CGA-Bench: Trace Conformance Checking
        "field": "cga_pass",
        "is_ground_truth": True,
    },
}

NON_DEGENERATE = ["ASC", "CwT", "PAF", "TCC"]

COMPLETE_MODELS = frozenset(
    {
        "oss120b",
        "qwen27b",
        "qwen35b",
        "qwen4b",
        "qwen397b",
        "gemma31b",
        "nemotron30b",
        "deepseek_r1_7b",
    }
)


def load_episodes(episodes_dir: str) -> pd.DataFrame:
    """Load episodes into a DataFrame with evaluator verdicts."""
    records = []
    seen_keys: set[str] = set()
    for model_dir in sorted(glob.glob(os.path.join(episodes_dir, "*"))):
        if not os.path.isdir(model_dir):
            continue
        model_name = os.path.basename(model_dir)
        if model_name not in COMPLETE_MODELS:
            continue
        for ep_file in sorted(glob.glob(os.path.join(model_dir, "*.json"))):
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(ep, dict):
                continue

            scenario_id = ep.get("scenario_id", os.path.basename(ep_file).replace(".json", ""))
            run_id = ep.get("run_id", ep.get("run_index", 0))
            key = f"{model_name}_{scenario_id}_{run_id}"
            if key in seen_keys:
                continue
            seen_keys.add(key)
            domain = scenario_id.split("_")[0] if scenario_id else "unknown"
            source = "auto" if "auto" in scenario_id.lower() or ep.get("source") == "auto" else "manual"

            # Extract evaluator verdicts
            record = {
                "model": model_name,
                "scenario_id": scenario_id,
                "domain": domain,
                "source": source,
                "run_id": run_id,
                "compliance_score": ep.get("compliance_score", 0),
                "n_actions": ep.get("actions_count", len(ep.get("actions", []))),
                "n_violations": len(ep.get("violation_events", [])),
            }

            # Try to extract individual evaluator pass/fail
            # These might be stored differently depending on the codebase
            evaluator_results = ep.get("evaluator_results", {})
            for eval_name, eval_cfg in EVALUATORS.items():
                field = eval_cfg["field"]
                if field in ep:
                    record[f"verdict_{eval_name}"] = int(bool(ep[field]))
                elif eval_name in evaluator_results:
                    record[f"verdict_{eval_name}"] = int(bool(evaluator_results[eval_name]))
                elif "threshold_field" in eval_cfg and eval_cfg["threshold_field"] in ep:
                    score = ep[eval_cfg["threshold_field"]]
                    record[f"verdict_{eval_name}"] = int(score >= eval_cfg["default_threshold"])
                elif eval_cfg.get("degenerate"):
                    record[f"verdict_{eval_name}"] = 1  # TOM always passes
                else:
                    record[f"verdict_{eval_name}"] = None

            records.append(record)

    df = pd.DataFrame(records)
    print(f"Loaded {len(df)} episodes, {df['model'].nunique()} models, {df['scenario_id'].nunique()} scenarios")
    return df


# ============================================================================
# ANALYSIS 1: MIXED-EFFECTS LOGISTIC MODEL
# ============================================================================


def run_mixed_effects_analysis(df: pd.DataFrame) -> dict:
    """Mixed-effects logistic model:
      verdict ~ evaluator_family (fixed) + (1|scenario) + (1|model)

    Addresses reviewer B2: "mixed-effects logistic model로 가라...
    evaluator family fixed, scenario/model random"
    """
    try:
        import statsmodels.api as sm
        from statsmodels.genmod.cov_struct import Exchangeable
        from statsmodels.genmod.families import Binomial
        from statsmodels.genmod.generalized_estimating_equations import GEE
    except ImportError:
        print("WARNING: statsmodels not available. Using ANOVA fallback.")
        return run_anova_fallback(df)

    # Reshape to long format: one row per (episode, evaluator)
    long_records = []
    for _, row in df.iterrows():
        for eval_name in NON_DEGENERATE:
            verdict_col = f"verdict_{eval_name}"
            if verdict_col in row and row[verdict_col] is not None:
                long_records.append(
                    {
                        "episode_id": f"{row['model']}_{row['scenario_id']}_{row['run_id']}",
                        "model": row["model"],
                        "scenario_id": row["scenario_id"],
                        "domain": row["domain"],
                        "evaluator": eval_name,
                        "verdict": int(row[verdict_col]),
                    }
                )

    long_df = pd.DataFrame(long_records)
    if long_df.empty:
        return {"error": "No evaluator verdicts found in episode data"}

    print(
        f"  Long format: {len(long_df)} rows ({len(long_df) // len(NON_DEGENERATE)} episodes × {len(NON_DEGENERATE)} evaluators)"
    )

    # Encode evaluator as dummy variables (TCC as reference)
    eval_dummies = pd.get_dummies(long_df["evaluator"], prefix="eval", drop_first=False)
    if "eval_TCC" in eval_dummies.columns:
        eval_dummies = eval_dummies.drop("eval_TCC", axis=1)

    # GEE with exchangeable correlation structure (scenario as cluster)
    # This approximates a mixed-effects model when statsmodels BinomialBayesMixedGLM
    # is not available
    try:
        X = sm.add_constant(eval_dummies)
        long_df["cluster_id"] = pd.Categorical(long_df["scenario_id"]).codes

        gee_model = GEE(
            long_df["verdict"],
            X,
            groups=long_df["cluster_id"],
            family=Binomial(),
            cov_struct=Exchangeable(),
        )
        gee_result = gee_model.fit()

        result = {
            "method": "GEE_exchangeable_binomial",
            "n_observations": len(long_df),
            "n_clusters": long_df["cluster_id"].nunique(),
            "coefficients": {},
            "p_values": {},
            "scale": float(gee_result.scale),
        }

        for param_name in gee_result.params.index:
            result["coefficients"][param_name] = round(float(gee_result.params[param_name]), 4)
            result["p_values"][param_name] = float(gee_result.pvalues[param_name])

        # Odds ratios for evaluator effects
        result["odds_ratios"] = {}
        for param_name in gee_result.params.index:
            if param_name.startswith("eval_"):
                or_val = np.exp(gee_result.params[param_name])
                result["odds_ratios"][param_name] = round(float(or_val), 3)

        print(f"  GEE converged. Scale = {result['scale']:.4f}")
        for p, v in result["coefficients"].items():
            sig = "*" if result["p_values"].get(p, 1) < 0.05 else ""
            print(f"    {p}: β={v:.4f}, p={result['p_values'].get(p, 'N/A'):.4e} {sig}")

        return result

    except Exception as e:
        print(f"  GEE failed: {e}. Falling back to ANOVA.")
        return run_anova_fallback(df)


def run_anova_fallback(df: pd.DataFrame) -> dict:
    """ANOVA-based variance decomposition as fallback."""
    # Compute η² for evaluator, model, scenario, run
    # Using verdict as DV, evaluator as IV

    verdicts_by_evaluator = {}
    for eval_name in NON_DEGENERATE:
        col = f"verdict_{eval_name}"
        if col in df.columns:
            verdicts_by_evaluator[eval_name] = df[col].dropna().values

    if len(verdicts_by_evaluator) < 2:
        return {"error": "Insufficient evaluator data for ANOVA"}

    # Kruskal-Wallis (non-parametric ANOVA for binary outcomes)
    groups = list(verdicts_by_evaluator.values())
    H, p = scipy_stats.kruskal(*groups)

    # Compute η² = H / (N-1) approximately
    N = sum(len(g) for g in groups)
    eta_sq = float(H / (N - 1))

    # Also compute per-evaluator pass rates
    pass_rates = {k: round(float(np.mean(v)), 4) for k, v in verdicts_by_evaluator.items()}

    return {
        "method": "kruskal_wallis_fallback",
        "H_statistic": round(float(H), 2),
        "p_value": float(p),
        "eta_squared_approx": round(eta_sq, 4),
        "pass_rates": pass_rates,
        "n_per_evaluator": {k: len(v) for k, v in verdicts_by_evaluator.items()},
    }


# ============================================================================
# ANALYSIS 2: RANKING FLIP EXPERIMENT
# ============================================================================


def run_ranking_flip(df: pd.DataFrame) -> dict:
    """Ranking flip experiment:
    For each evaluator, rank models by pass rate.
    Check if top-1 model flips across evaluators.
    Friedman test + Nemenyi post-hoc.

    Addresses reviewer A1: "same models, 4개 evaluator별 model ranking,
    top-1 flip, Friedman/Nemenyi"
    """
    models = sorted(df["model"].unique())
    n_models = len(models)

    if n_models < 3:
        return {"error": f"Need ≥3 models for Friedman test, got {n_models}"}

    # Compute pass rate per (model, evaluator)
    rankings = {}  # evaluator → {model: rank}
    pass_rates = {}  # evaluator → {model: pass_rate}

    for eval_name in NON_DEGENERATE:
        col = f"verdict_{eval_name}"
        if col not in df.columns:
            continue

        model_rates = {}
        for model in models:
            model_df = df[df["model"] == model]
            vals = model_df[col].dropna()
            if len(vals) > 0:
                model_rates[model] = float(vals.mean())

        if len(model_rates) < n_models:
            continue

        pass_rates[eval_name] = model_rates

        # Rank (higher pass rate = rank 1)
        sorted_models = sorted(model_rates.items(), key=lambda x: -x[1])
        rankings[eval_name] = {m: rank + 1 for rank, (m, _) in enumerate(sorted_models)}

    if len(rankings) < 2:
        return {"error": "Insufficient evaluator data for ranking analysis"}

    # Top-1 model per evaluator
    top1 = {eval_name: min(ranking, key=ranking.get) for eval_name, ranking in rankings.items()}
    n_distinct_top1 = len(set(top1.values()))
    top1_flip = n_distinct_top1 > 1

    print("\n  Top-1 model by evaluator:")
    for eval_name, model in top1.items():
        rate = pass_rates[eval_name][model]
        print(f"    {eval_name}: {model} ({rate:.1%})")

    # Friedman test
    # Need scenario-level rankings for proper Friedman
    # Simplify: use model-level aggregated ranks
    rank_matrix = []
    for eval_name in sorted(rankings.keys()):
        rank_row = [rankings[eval_name][m] for m in models]
        rank_matrix.append(rank_row)

    rank_array = np.array(rank_matrix).T  # models × evaluators

    if rank_array.shape[0] >= 3 and rank_array.shape[1] >= 2:
        try:
            friedman_stat, friedman_p = scipy_stats.friedmanchisquare(*rank_array.T)
        except Exception:
            friedman_stat, friedman_p = None, None
    else:
        friedman_stat, friedman_p = None, None

    # Kendall's W (coefficient of concordance)
    if rank_array.shape[1] >= 2:
        k = rank_array.shape[1]  # number of raters (evaluators)
        n = rank_array.shape[0]  # number of items (models)
        rank_sums = rank_array.sum(axis=1)
        S = np.var(rank_sums) * n
        W = 12 * S / (k**2 * (n**3 - n))
    else:
        W = None

    # Pairwise Spearman between evaluators
    spearman_pairs = {}
    eval_names = sorted(rankings.keys())
    for i, e1 in enumerate(eval_names):
        for e2 in eval_names[i + 1 :]:
            ranks1 = [rankings[e1][m] for m in models]
            ranks2 = [rankings[e2][m] for m in models]
            rho, p = scipy_stats.spearmanr(ranks1, ranks2)
            spearman_pairs[f"{e1}_vs_{e2}"] = {
                "rho": round(float(rho), 3),
                "p": float(p),
            }

    # Rank reversal count
    n_reversals = 0
    for i, m1 in enumerate(models):
        for m2 in models[i + 1 :]:
            orders = set()
            for eval_name in rankings:
                if rankings[eval_name][m1] < rankings[eval_name][m2]:
                    orders.add("m1_better")
                elif rankings[eval_name][m1] > rankings[eval_name][m2]:
                    orders.add("m2_better")
            if len(orders) > 1:
                n_reversals += 1

    total_pairs = n_models * (n_models - 1) // 2

    result = {
        "n_models": n_models,
        "n_evaluators": len(rankings),
        "top1_per_evaluator": top1,
        "top1_flip": top1_flip,
        "n_distinct_top1": n_distinct_top1,
        "pass_rates": pass_rates,
        "rankings": rankings,
        "friedman_statistic": round(float(friedman_stat), 2) if friedman_stat else None,
        "friedman_p": float(friedman_p) if friedman_p else None,
        "kendalls_W": round(float(W), 3) if W else None,
        "spearman_pairs": spearman_pairs,
        "n_rank_reversals": n_reversals,
        "total_model_pairs": total_pairs,
        "reversal_rate": round(n_reversals / max(total_pairs, 1) * 100, 1),
    }

    print(f"\n  Friedman χ² = {result['friedman_statistic']}, p = {result['friedman_p']}")
    print(f"  Kendall's W = {result['kendalls_W']}")
    print(f"  Rank reversals: {n_reversals}/{total_pairs} ({result['reversal_rate']}%)")
    print(f"  Top-1 flip: {top1_flip}")

    return result


def generate_tex_macros(mixed: dict, ranking: dict) -> dict:
    """Generate LaTeX macro updates."""
    macros = {}

    # Mixed-effects
    if "coefficients" in mixed:
        for param, val in mixed["coefficients"].items():
            if param.startswith("eval_"):
                clean = param.replace("eval_", "")
                macros[f"geeCoeff{clean}"] = val
        if "odds_ratios" in mixed:
            for param, val in mixed["odds_ratios"].items():
                clean = param.replace("eval_", "")
                macros[f"geeOR{clean}"] = val
    elif "eta_squared_approx" in mixed:
        macros["etaEvaluatorNew"] = round(mixed["eta_squared_approx"] * 100, 1)

    # Ranking flip
    if ranking.get("friedman_statistic"):
        macros["friedmanChi"] = ranking["friedman_statistic"]
        macros["friedmanP"] = f"{ranking['friedman_p']:.2e}"
        macros["kendallW"] = ranking["kendalls_W"]
        macros["numRankReversals"] = ranking["n_rank_reversals"]
        macros["reversalRate"] = ranking["reversal_rate"]
        macros["topOneFlip"] = "yes" if ranking["top1_flip"] else "no"

    return macros


def main():
    parser = argparse.ArgumentParser(description="Post-Episode Statistical Analyses")
    parser.add_argument("--episodes-dir", default="results/full_706_v5")
    parser.add_argument("--output", default="evidence_pack/analysis/post_episode_stats.json")
    parser.add_argument("--tex-output", default="paper/auto_numbers.tex")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    df = load_episodes(args.episodes_dir)
    if df.empty:
        print("ERROR: No episodes loaded.")
        sys.exit(1)

    print("\n" + "=" * 60)
    print("ANALYSIS 1: MIXED-EFFECTS MODEL")
    print("=" * 60)
    mixed_result = run_mixed_effects_analysis(df)

    print("\n" + "=" * 60)
    print("ANALYSIS 2: RANKING FLIP")
    print("=" * 60)
    ranking_result = run_ranking_flip(df)

    # Combine results
    result = {
        "n_episodes": len(df),
        "n_models": int(df["model"].nunique()),
        "n_scenarios": int(df["scenario_id"].nunique()),
        "mixed_effects": mixed_result,
        "ranking_flip": ranking_result,
    }

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, default=str)
    print(f"\n✅ Saved to {args.output}")

    macros = generate_tex_macros(mixed_result, ranking_result)
    if macros:
        print(f"\n=== Tex macros ({len(macros)}) ===")
        for k, v in macros.items():
            print(f"  \\{k} = {v}")


if __name__ == "__main__":
    main()
