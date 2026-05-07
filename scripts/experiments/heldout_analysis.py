#!/usr/bin/env python3
r"""Experiment H: Held-out Generalization Analysis.

Compares model performance on 5 held-out CPG guidelines vs 20 core
guidelines to test benchmark generalization.

Hypotheses:
  H1: |delta-CGA| = |mean(held-out) - mean(core)| median across models < 0.05
  H2: Spearman rho between core and held-out model rankings is significant
  H3: Violation type distributions are similar (chi-squared test)

Metrics:
  - Per-model delta-CGA (held-out - core) with bootstrap 95% CI
  - Wilcoxon signed-rank per evaluator on pass rates
  - Spearman rho for model ranking stability
  - Chi-squared on violation type distributions (core vs held-out)

Outputs:
  evidence_pack/heldout_v1/heldout_results.json
  evidence_pack/heldout_v1/heldout_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/heldout_analysis.py
"""

from __future__ import annotations

from collections import Counter
import json
import logging
from pathlib import Path
import sys
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from collections.abc import Callable

import numpy as np
from scipy import stats as sp_stats

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._episode_cache import (  # noqa: E402
    COMPLETE_MODELS,
    load_cached_verdicts,
    score_episode,
    verdict_summary,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

HELDOUT_DIR = ROOT / "results" / "heldout_v1"
CORE_DIR = ROOT / "results" / "full_706_v5"
OUTPUT_DIR = ROOT / "evidence_pack" / "heldout_v1"

HELDOUT_MODELS = [*list(COMPLETE_MODELS), "deepseek_r1_7b"]

# Exclude aabb_transfusion scenarios from held-out analysis:
# aabb is core-20 (cpg-graphs.md #17), was erroneously included in heldout_runner.
# Filtering by scenario_id prefix to avoid contamination.
EXCLUDED_HELDOUT_PREFIXES = ("aabb_t_",)

MODEL_LABELS: dict[str, str] = {
    "oss120b": "OSS-120B",
    "qwen27b": "Qwen3.5-27B",
    "qwen35b": "Qwen3.5-35B",
    "qwen4b": "Qwen3-4B",
    "qwen397b": "Qwen3.5-397B",
    "gemma31b": "Gemma4-31B",
    "nemotron30b": "Nemotron-30B",
    "deepseek_r1_7b": "DeepSeek-R1-7B",
}

EVALUATOR_NAMES = ["AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]
EVALUATOR_KEYS = ["ac_proxy", "mab_proxy", "c2_pass", "cga_pass"]

N_BOOTSTRAP = 10000
SEED = 42

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _load_heldout_episodes() -> list[dict[str, Any]]:
    """Load held-out episodes with dedup."""
    episodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    for model_dir in sorted(HELDOUT_DIR.iterdir()):
        if not model_dir.is_dir() or model_dir.name.startswith("."):
            continue
        for ep_file in sorted(model_dir.glob("*.json")):
            if ep_file.name.startswith(("checkpoint", ".claim", "log_", "model_summary")):
                continue
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
                if not isinstance(ep, dict):
                    continue
                sid = ep.get("scenario_id", "")
                if not sid:
                    continue
                # Filter out contaminated core-20 scenarios
                if any(sid.startswith(pfx) for pfx in EXCLUDED_HELDOUT_PREFIXES):
                    continue
                key = f"{model_dir.name}_{sid}_{ep.get('run_index', 0)}"
                if key in seen:
                    continue
                seen.add(key)
                ep["_model"] = model_dir.name
                episodes.append(ep)
            except Exception:
                logger.debug("Failed to load %s", ep_file)

    return episodes


def _group_by_model(
    scored: list[dict[str, Any]],
) -> dict[str, list[dict[str, Any]]]:
    """Group scored records by model."""
    by_model: dict[str, list[dict[str, Any]]] = {}
    for r in scored:
        m = r["model"]
        by_model.setdefault(m, []).append(r)
    return by_model


def _pass_rate(records: list[dict[str, Any]], key: str) -> float:
    """Compute pass rate for a given evaluator key."""
    if not records:
        return 0.0
    return sum(1 for r in records if r[key]) / len(records)


def _bootstrap_ci(
    values: np.ndarray,
    stat_fn: Callable[..., float] = np.mean,
    n_boot: int = N_BOOTSTRAP,
    ci: float = 0.95,
    seed: int = SEED,
) -> tuple[float, float, float]:
    """Bootstrap confidence interval. Returns (estimate, lo, hi)."""
    rng = np.random.default_rng(seed)
    estimate = float(stat_fn(values))
    boot = np.array([float(stat_fn(rng.choice(values, size=len(values), replace=True))) for _ in range(n_boot)])
    alpha = (1 - ci) / 2
    lo = float(np.percentile(boot, alpha * 100))
    hi = float(np.percentile(boot, (1 - alpha) * 100))
    return estimate, lo, hi


def _holm_bonferroni(pvals: list[float]) -> list[float]:
    """Holm-Bonferroni correction for multiple comparisons."""
    n = len(pvals)
    indexed = sorted(enumerate(pvals), key=lambda x: x[1])
    adjusted = [0.0] * n
    running_max = 0.0
    for rank, (orig_idx, p) in enumerate(indexed):
        corrected = p * (n - rank)
        corrected = min(corrected, 1.0)
        running_max = max(running_max, corrected)
        adjusted[orig_idx] = running_max
    return adjusted


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def run_analysis() -> dict[str, Any]:
    """Run full held-out generalization analysis."""
    print("=" * 60)
    print("Experiment H: Held-out Generalization Analysis")
    print("=" * 60)

    # 1. Load held-out episodes
    print("\n[1/5] Loading held-out episodes...")
    heldout_eps = _load_heldout_episodes()
    print(f"  Loaded {len(heldout_eps)} held-out episodes")

    heldout_scored = [score_episode(ep) for ep in heldout_eps]
    heldout_by_model = _group_by_model(heldout_scored)

    # 2. Load core episodes (cached)
    print("\n[2/5] Loading core episodes...")
    _, core_scored = load_cached_verdicts(use_disk_cache=True)
    core_by_model = _group_by_model(core_scored)

    # Find models present in both, with minimum episode threshold
    min_heldout_episodes = 100
    all_common = sorted(set(heldout_by_model.keys()) & set(core_by_model.keys()))
    excluded = {m for m in all_common if len(heldout_by_model[m]) < min_heldout_episodes}
    if excluded:
        for m in sorted(excluded):
            print(f"  EXCLUDED {m}: only {len(heldout_by_model[m])} held-out episodes (min {min_heldout_episodes})")
    common_models = sorted(set(all_common) - excluded)
    print(f"  Common models: {common_models} ({len(common_models)})")

    # 3. Per-model comparison
    print("\n[3/5] Per-model core vs held-out comparison...")
    model_results: dict[str, dict[str, Any]] = {}

    for model in common_models:
        core_recs = core_by_model[model]
        held_recs = heldout_by_model[model]

        core_summary = verdict_summary(core_recs)
        held_summary = verdict_summary(held_recs)

        # Per-evaluator pass rates
        deltas: dict[str, float] = {}
        for name, key in zip(EVALUATOR_NAMES, EVALUATOR_KEYS, strict=True):
            core_pr = _pass_rate(core_recs, key)
            held_pr = _pass_rate(held_recs, key)
            deltas[name] = round(held_pr - core_pr, 4)

        # CGA pass rate delta with bootstrap CI
        core_cga = np.array([1.0 if r["cga_pass"] else 0.0 for r in core_recs])
        held_cga = np.array([1.0 if r["cga_pass"] else 0.0 for r in held_recs])
        delta_cga = float(np.mean(held_cga) - np.mean(core_cga))

        # Bootstrap CI on delta (resample both independently)
        rng = np.random.default_rng(SEED)
        boot_deltas = []
        for _ in range(N_BOOTSTRAP):
            bc = rng.choice(core_cga, size=len(core_cga), replace=True)
            bh = rng.choice(held_cga, size=len(held_cga), replace=True)
            boot_deltas.append(float(np.mean(bh) - np.mean(bc)))
        boot_deltas_arr = np.array(boot_deltas)
        ci_lo = float(np.percentile(boot_deltas_arr, 2.5))
        ci_hi = float(np.percentile(boot_deltas_arr, 97.5))

        # Violation type distribution
        core_vtypes = Counter(vt for r in core_recs for vt in r.get("violation_types", []))
        held_vtypes = Counter(vt for r in held_recs for vt in r.get("violation_types", []))

        model_results[model] = {
            "label": MODEL_LABELS.get(model, model),
            "n_core": len(core_recs),
            "n_heldout": len(held_recs),
            "core_summary": core_summary,
            "heldout_summary": held_summary,
            "delta_per_evaluator": deltas,
            "delta_cga": round(delta_cga, 4),
            "delta_cga_ci": [round(ci_lo, 4), round(ci_hi, 4)],
            "core_violation_types": dict(core_vtypes),
            "heldout_violation_types": dict(held_vtypes),
        }

        print(
            f"  {model}: dCGA={delta_cga:+.3f} [{ci_lo:+.3f}, {ci_hi:+.3f}]"
            f"  core={core_summary['cga_pass_pct']:.1f}%"
            f"  held={held_summary['cga_pass_pct']:.1f}%"
        )

    # 4. Aggregate tests
    print("\n[4/5] Statistical tests...")

    # H1: Median |dCGA| < 0.05
    abs_deltas = [abs(model_results[m]["delta_cga"]) for m in common_models]
    median_abs_delta = float(np.median(abs_deltas))
    mean_abs_delta = float(np.mean(abs_deltas))
    print(f"  H1: Median |dCGA| = {median_abs_delta:.4f} (threshold: 0.05)")

    # H2: Spearman rho on model rankings
    ranking_rho: dict[str, Any] = {}
    for name, key in zip(EVALUATOR_NAMES, EVALUATOR_KEYS, strict=True):
        core_rates = [_pass_rate(core_by_model[m], key) for m in common_models]
        held_rates = [_pass_rate(heldout_by_model[m], key) for m in common_models]
        if len(common_models) >= 3:
            rho, pval = sp_stats.spearmanr(core_rates, held_rates)
            ranking_rho[name] = {
                "rho": round(float(rho), 4),
                "p": round(float(pval), 4),
            }
            print(f"  H2 {name}: rho={rho:.3f}, p={pval:.4f}")
        else:
            ranking_rho[name] = {"rho": None, "p": None}

    # Overall ranking (CGA-Bench)
    core_cga_rates = [_pass_rate(core_by_model[m], "cga_pass") for m in common_models]
    held_cga_rates = [_pass_rate(heldout_by_model[m], "cga_pass") for m in common_models]
    if len(common_models) >= 3:
        overall_rho, overall_p = sp_stats.spearmanr(core_cga_rates, held_cga_rates)
    else:
        overall_rho, overall_p = 0.0, 1.0

    # H3: chi-squared on violation type distribution (pooled)
    all_vtypes = {"omission", "commission", "timing", "sequence", "deviation"}
    core_counts = Counter(vt for m in common_models for r in core_by_model[m] for vt in r.get("violation_types", []))
    held_counts = Counter(vt for m in common_models for r in heldout_by_model[m] for vt in r.get("violation_types", []))
    ordered_types = sorted(all_vtypes)
    obs_core = [core_counts.get(t, 0) for t in ordered_types]
    obs_held = [held_counts.get(t, 0) for t in ordered_types]

    # Chi-squared test of independence
    contingency = np.array([obs_core, obs_held])
    # Remove columns with all zeros
    nonzero_cols = contingency.sum(axis=0) > 0
    if nonzero_cols.sum() >= 2:
        chi2, chi2_p, chi2_dof, _ = sp_stats.chi2_contingency(contingency[:, nonzero_cols])
    else:
        chi2, chi2_p, chi2_dof = 0.0, 1.0, 0

    print(f"  H3: chi2={chi2:.2f}, df={chi2_dof}, p={chi2_p:.4f}")

    # Wilcoxon signed-rank per evaluator (paired by model)
    wilcoxon_results: dict[str, Any] = {}
    raw_pvals: list[float] = []
    for name, key in zip(EVALUATOR_NAMES, EVALUATOR_KEYS, strict=True):
        core_pr = np.array([_pass_rate(core_by_model[m], key) for m in common_models])
        held_pr = np.array([_pass_rate(heldout_by_model[m], key) for m in common_models])
        diff = held_pr - core_pr
        if np.any(diff != 0) and len(common_models) >= 6:
            w_stat, w_p = sp_stats.wilcoxon(diff)
            wilcoxon_results[name] = {
                "W": round(float(w_stat), 4),
                "p": round(float(w_p), 4),
            }
            raw_pvals.append(float(w_p))
        else:
            wilcoxon_results[name] = {
                "W": None,
                "p": None,
                "note": "too_few_or_zero_diff",
            }
            raw_pvals.append(1.0)

    adjusted_pvals = _holm_bonferroni(raw_pvals)
    for i, name in enumerate(EVALUATOR_NAMES):
        wilcoxon_results[name]["p_adjusted"] = round(adjusted_pvals[i], 4)
        sig = (
            "***"
            if adjusted_pvals[i] < 0.001
            else "**"
            if adjusted_pvals[i] < 0.01
            else "*"
            if adjusted_pvals[i] < 0.05
            else "ns"
        )
        print(f"  Wilcoxon {name}: p_adj={adjusted_pvals[i]:.4f} ({sig})")

    # 5. Build results
    print("\n[5/5] Writing output...")

    n_included_heldout = sum(len(heldout_by_model[m]) for m in common_models)
    results: dict[str, Any] = {
        "experiment": "H_heldout_generalization",
        "n_heldout_episodes": n_included_heldout,
        "n_heldout_episodes_total": len(heldout_scored),
        "n_core_episodes": len(core_scored),
        "n_common_models": len(common_models),
        "common_models": common_models,
        "excluded_models": sorted(excluded),
        "min_episode_threshold": min_heldout_episodes,
        "per_model": model_results,
        "h1_median_abs_delta_cga": round(median_abs_delta, 4),
        "h1_mean_abs_delta_cga": round(mean_abs_delta, 4),
        "h1_threshold": 0.05,
        "h1_pass": median_abs_delta < 0.05,
        "h2_ranking_rho_per_evaluator": ranking_rho,
        "h2_overall_rho": round(float(overall_rho), 4),
        "h2_overall_p": round(float(overall_p), 4),
        "h3_chi2": round(float(chi2), 2),
        "h3_chi2_dof": int(chi2_dof),
        "h3_chi2_p": round(float(chi2_p), 4),
        "h3_violation_types": ordered_types,
        "h3_core_counts": obs_core,
        "h3_held_counts": obs_held,
        "wilcoxon_per_evaluator": wilcoxon_results,
    }

    # Write JSON
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    json_path = OUTPUT_DIR / "heldout_results.json"
    with open(json_path, "w") as f:
        json.dump(results, f, indent=2, ensure_ascii=False, default=str)
    print(f"  Wrote {json_path}")

    # Write LaTeX macros
    _write_macros(results)

    print("\n" + "=" * 60)
    print("SUMMARY")
    h1_label = "PASS" if median_abs_delta < 0.05 else "FAIL"
    print(f"  H1 median |dCGA|: {median_abs_delta:.4f} {h1_label}")
    print(f"  H2 ranking rho (CGA): {overall_rho:.3f} (p={overall_p:.4f})")
    print(f"  H3 violation chi2: {chi2:.2f} (p={chi2_p:.4f})")
    print(f"  Models: {len(common_models)}, Held-out: {len(heldout_scored)}, Core: {len(core_scored)}")
    print("=" * 60)

    return results


def _write_macros(results: dict[str, Any]) -> None:
    """Write LaTeX macro file."""
    macros_path = OUTPUT_DIR / "heldout_macros.tex"
    lines: list[str] = [
        "% Auto-generated by heldout_analysis.py",
        f"\\providecommand{{\\heldoutNModels}}{{{results['n_common_models']}}}",
        f"\\providecommand{{\\heldoutNEpisodes}}{{{results['n_heldout_episodes']}}}",
        f"\\providecommand{{\\heldoutNCoreEpisodes}}{{{results['n_core_episodes']}}}",
        f"\\providecommand{{\\heldoutMedianAbsDelta}}{{{results['h1_median_abs_delta_cga']:.3f}}}",
        f"\\providecommand{{\\heldoutMeanAbsDelta}}{{{results['h1_mean_abs_delta_cga']:.3f}}}",
        f"\\providecommand{{\\heldoutHOnePass}}{{{('Yes' if results['h1_pass'] else 'No')}}}",
        f"\\providecommand{{\\heldoutRankingRho}}{{{results['h2_overall_rho']:.3f}}}",
        f"\\providecommand{{\\heldoutRankingP}}{{{results['h2_overall_p']:.4f}}}",
        f"\\providecommand{{\\heldoutChiSq}}{{{results['h3_chi2']:.2f}}}",
        f"\\providecommand{{\\heldoutChiSqDof}}{{{results['h3_chi2_dof']}}}",
        f"\\providecommand{{\\heldoutChiSqP}}{{{results['h3_chi2_p']:.4f}}}",
    ]

    # Per-model deltas
    for model, mr in results.get("per_model", {}).items():
        safe = model.replace("_", "")
        delta = mr["delta_cga"]
        ci_lo, ci_hi = mr["delta_cga_ci"]
        lines.append(f"\\providecommand{{\\heldoutDelta{safe}}}{{{delta:+.3f}}}")
        lines.append(f"\\providecommand{{\\heldoutCI{safe}}}{{[{ci_lo:+.3f}, {ci_hi:+.3f}]}}")

    # Per-evaluator Wilcoxon
    for name, wr in results.get("wilcoxon_per_evaluator", {}).items():
        safe = name.replace("-", "").replace(" ", "")
        p_adj = wr.get("p_adjusted", 1.0)
        lines.append(f"\\providecommand{{\\heldoutWilcoxon{safe}P}}{{{p_adj:.4f}}}")

    with open(macros_path, "w") as f:
        f.write("\n".join(lines) + "\n")
    print(f"  Wrote {macros_path}")


if __name__ == "__main__":
    run_analysis()
