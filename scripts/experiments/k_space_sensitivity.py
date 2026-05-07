#!/usr/bin/env python3
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""P0-1 k-space sensitivity analysis for CGA-Bench composite metric.

Sweeps the action-coverage scaling factor k in Composite_A = CGA * min(1, acts/(exp*k))
and tests whether Friedman ranking stability holds across the sweep.

Data source modes:
  --canonical (default): Load single-run data from composite_metric.json and
      multi-run data from compute_final_stats.py directory config.  This ensures
      k=2.0 p-values match the verified canonical values (single p=0.043,
      multi p=0.013).
  --raw-episodes: Load from raw episode JSON files using alphabetical glob
      (legacy behavior; may produce different p-values due to episode selection).

Outputs:
  - evidence_pack/analysis/k_space_sensitivity.json
  - evidence_pack/tables/multiple_comparison_correction.tex
  - evidence_pack/figures/k_sensitivity_pvalue.pdf
  - evidence_pack/figures/k_sensitivity_effect_size.pdf
  - evidence_pack/figures/k_sensitivity_composite_by_model.pdf
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from dataclasses import dataclass, field
import json
from pathlib import Path
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats
import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BASE_DIR = Path(__file__).resolve().parents[2]  # cga_bench/
RESULTS_DIR = BASE_DIR / "results"
CONFIGS_DIR = BASE_DIR / "configs" / "scenarios"
EVIDENCE_DIR = BASE_DIR / "evidence_pack"
ANALYSIS_DIR = EVIDENCE_DIR / "analysis"
FIGURES_DIR = EVIDENCE_DIR / "figures"
TABLES_DIR = EVIDENCE_DIR / "tables"

# Raw-episode directory config (legacy, --raw-episodes mode)
MODEL_DIRS: dict[str, dict[str, list[str]]] = {
    "oss-120b": {
        "dirs": [
            "eval_science_rag_oss120b/baseline",
            "eval_science_rag_oss120b/patch_S",
            "eval_science_rag_oss120b/patch_T",
        ],
    },
    "Qwen3.5-35B": {
        "dirs": ["eval_science_rag_qwen35/baseline"],
    },
    "oss-20b": {
        "dirs": ["eval_science_rag_oss20b/baseline"],
    },
    "Qwen3-4B": {
        "dirs": ["eval_science_rag_qwen3_4b/baseline"],
    },
}

# Canonical multi-run directory config (matches compute_final_stats.py)
CANONICAL_MULTI_DIRS: dict[str, list[str]] = {
    "oss-120b": [
        "eval_science_rag_oss120b/baseline",
        "expansion_3run/run0",
        "expansion_3run/run1",
        "expansion_3run/run2",
    ],
    "Qwen3.5-35B": [
        "eval_science_qwen35/baseline",
        "eval_science_rag_qwen35/baseline",
    ],
    "oss-20b": [
        "eval_science_rag_oss20b/baseline",
    ],
    "Qwen3-4B": [
        "eval_science_rag_qwen3_4b/baseline",
    ],
}

RUNS_PER_SCENARIO = 3
K_MIN = 0.5
K_MAX = 4.0
K_STEP = 0.1
ALPHA = 0.05
NUM_MODELS = 4

# Matplotlib publication style
PLT_PARAMS = {
    "font.family": "serif",
    "font.size": 10,
    "axes.labelsize": 11,
    "axes.titlesize": 12,
    "legend.fontsize": 9,
    "xtick.labelsize": 9,
    "ytick.labelsize": 9,
    "figure.dpi": 300,
    "savefig.dpi": 300,
    "savefig.bbox": "tight",
    "savefig.pad_inches": 0.05,
}

# Model display colors
MODEL_COLORS = {
    "oss-120b": "#1f77b4",
    "Qwen3.5-35B": "#ff7f0e",
    "oss-20b": "#2ca02c",
    "Qwen3-4B": "#d62728",
}


# ---------------------------------------------------------------------------
# Multiple testing correction (replaces statsmodels dependency)
# ---------------------------------------------------------------------------

def _holm_bonferroni(p_values: list[float], alpha: float = 0.05) -> list[float]:
    """Bonferroni-Holm step-down correction.

    Args:
        p_values: Raw p-values.
        alpha: Family-wise error rate.

    Returns:
        Adjusted p-values (capped at 1.0).
    """
    n = len(p_values)
    order = sorted(range(n), key=lambda i: p_values[i])
    adjusted = [0.0] * n
    cummax = 0.0
    for rank, idx in enumerate(order):
        adj_p = p_values[idx] * (n - rank)
        cummax = max(cummax, adj_p)
        adjusted[idx] = min(cummax, 1.0)
    return adjusted


def _benjamini_hochberg(p_values: list[float], alpha: float = 0.05) -> list[float]:
    """Benjamini-Hochberg FDR correction.

    Args:
        p_values: Raw p-values.
        alpha: False discovery rate.

    Returns:
        Adjusted p-values (capped at 1.0).
    """
    n = len(p_values)
    order = sorted(range(n), key=lambda i: p_values[i], reverse=True)
    adjusted = [0.0] * n
    cummin = 1.0
    for idx in order:
        rank = sorted(range(n), key=lambda i: p_values[i]).index(idx) + 1
        adj_p = p_values[idx] * n / rank
        cummin = min(cummin, adj_p)
        adjusted[idx] = min(cummin, 1.0)
    return adjusted


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class Episode:
    """Single evaluation episode."""

    scenario_id: str
    compliance_score: float
    actions_count: int
    source_file: str


@dataclass
class SweepPoint:
    """Result for a single k value."""

    k: float
    friedman_stat_multi: float
    p_value_multi: float
    epsilon_sq_multi: float
    friedman_stat_single: float
    p_value_single: float
    epsilon_sq_single: float
    model_means: dict[str, float] = field(default_factory=dict)


@dataclass
class ComparisonTest:
    """One pre-specified comparison test."""

    label: str
    test_statistic: float
    p_value: float
    epsilon_sq: float
    holm_p: float = 0.0
    bh_p: float = 0.0


# ---------------------------------------------------------------------------
# Step 1: Data Loading
# ---------------------------------------------------------------------------

def load_expected_actions(target_scenarios: list[str]) -> dict[str, int]:
    """Load expected_actions counts from scenario YAML configs.

    Args:
        target_scenarios: List of scenario IDs to load.

    Returns:
        Mapping from scenario_id to count of expected actions.
    """
    result: dict[str, int] = {}
    for yaml_path in sorted(CONFIGS_DIR.glob("*.yaml")):
        with open(yaml_path) as fh:
            data = yaml.safe_load(fh)
        if not isinstance(data, dict) or "scenarios" not in data:
            continue
        scenarios = data["scenarios"]
        if not isinstance(scenarios, dict):
            continue
        for sid, sdata in scenarios.items():
            if sid in target_scenarios and isinstance(sdata, dict):
                ea = sdata.get("expected_actions", [])
                result[sid] = len(ea)
    return result


def load_episodes(model_name: str, model_cfg: dict) -> dict[str, list[Episode]]:
    """Load episode JSONs for a model, grouped by scenario_id.

    Args:
        model_name: Display name of the model.
        model_cfg: Config dict with 'dirs' key listing subdirectories.

    Returns:
        Mapping from scenario_id to list of Episode objects, sorted by filename.
    """
    episodes: dict[str, list[Episode]] = defaultdict(list)
    for subdir in model_cfg["dirs"]:
        full_dir = RESULTS_DIR / subdir
        if not full_dir.exists():
            print(f"  [WARN] Directory not found: {full_dir}", file=sys.stderr)
            continue
        for fpath in sorted(full_dir.glob("*.json")):
            with open(fpath) as fh:
                data = json.load(fh)
            sid = data.get("scenario_id", "")
            cga = data.get("compliance_score", 0.0)
            acts = data.get("actions_count", 0)
            episodes[sid].append(Episode(
                scenario_id=sid,
                compliance_score=cga,
                actions_count=acts,
                source_file=str(fpath),
            ))
    return dict(episodes)


def load_all_data(
    target_scenarios: list[str],
) -> tuple[
    dict[str, dict[str, list[Episode]]],
    dict[str, int],
]:
    """Load all model episodes and expected actions.

    Args:
        target_scenarios: The 15 scenario IDs to include.

    Returns:
        Tuple of (model_episodes, expected_actions).
        model_episodes: {model_name: {scenario_id: [Episode, ...]}}.
        expected_actions: {scenario_id: int}.
    """
    exp_actions = load_expected_actions(target_scenarios)
    missing = set(target_scenarios) - set(exp_actions.keys())
    if missing:
        print(f"  [WARN] Missing expected_actions for: {missing}", file=sys.stderr)

    all_episodes: dict[str, dict[str, list[Episode]]] = {}
    for model_name, model_cfg in MODEL_DIRS.items():
        raw = load_episodes(model_name, model_cfg)
        # Filter to target scenarios, limit to RUNS_PER_SCENARIO
        filtered: dict[str, list[Episode]] = {}
        for sid in target_scenarios:
            if sid in raw and len(raw[sid]) > 0:
                filtered[sid] = raw[sid][:RUNS_PER_SCENARIO]
        all_episodes[model_name] = filtered
    return all_episodes, exp_actions


def validate_against_reference(
    all_episodes: dict[str, dict[str, list[Episode]]],
    exp_actions: dict[str, int],
) -> None:
    """Validate loaded data against composite_metric.json reference.

    Prints comparison; does not abort on mismatch since reference used
    single representative runs while we use first-N selection.
    """
    ref_path = ANALYSIS_DIR / "composite_metric.json"
    if not ref_path.exists():
        print("  [WARN] composite_metric.json not found, skipping validation")
        return

    ref = json.load(open(ref_path))
    ref_per = ref.get("per_scenario", {})

    mismatches = 0
    for sid in sorted(ref_per.keys()):
        for model_name in ref_per[sid]:
            ref_data = ref_per[sid][model_name]
            ref_cga = ref_data["cga"]
            ref_acts = ref_data["actions"]

            eps = all_episodes.get(model_name, {}).get(sid, [])
            if not eps:
                continue
            # Check if first episode matches reference
            ep0 = eps[0]
            cga_match = abs(ep0.compliance_score - ref_cga) < 0.01
            acts_match = ep0.actions_count == ref_acts
            if not cga_match or not acts_match:
                mismatches += 1
                if mismatches <= 5:
                    print(
                        f"  [INFO] {sid}/{model_name}: "
                        f"loaded=({ep0.compliance_score:.4f}, {ep0.actions_count}) "
                        f"vs ref=({ref_cga}, {ref_acts})"
                    )

    if mismatches > 0:
        print(f"  [INFO] {mismatches} first-episode mismatches vs reference "
              f"(expected: reference used specific run selection)")
    else:
        print("  [OK] All first-episode values match reference")


# ---------------------------------------------------------------------------
# Step 1b: Canonical Data Loading
# ---------------------------------------------------------------------------

def load_canonical_single_run(
    target_scenarios: list[str],
) -> tuple[dict[str, dict[str, list[Episode]]], dict[str, int]]:
    """Load single-run data from composite_metric.json (canonical source).

    This ensures single-run p-values match the verified values:
    k=2.0 -> p=0.043, k=1.9 -> p=0.073.

    Args:
        target_scenarios: Ordered list of scenario IDs.

    Returns:
        Tuple of (model_episodes, expected_actions).
    """
    ref_path = ANALYSIS_DIR / "composite_metric.json"
    ref = json.load(open(ref_path))
    per_scenario = ref["per_scenario"]

    exp_actions: dict[str, int] = {}
    all_episodes: dict[str, dict[str, list[Episode]]] = {
        m: {} for m in MODEL_DIRS
    }

    for sid in target_scenarios:
        if sid not in per_scenario:
            continue
        for model_name in MODEL_DIRS:
            if model_name not in per_scenario[sid]:
                continue
            entry = per_scenario[sid][model_name]
            cga = entry["cga"]
            actions = entry["actions"]
            exp_act = entry["exp_actions"]
            exp_actions[sid] = exp_act

            ep = Episode(
                scenario_id=sid,
                compliance_score=cga,
                actions_count=actions,
                source_file=f"composite_metric.json:{sid}/{model_name}",
            )
            all_episodes[model_name][sid] = [ep]

    return all_episodes, exp_actions


def load_canonical_multi_run(
    target_scenarios: list[str],
) -> tuple[dict[str, dict[str, list[Episode]]], dict[str, int]]:
    """Load multi-run data using canonical directory config from compute_final_stats.py.

    This uses the same directory layout that produced final_stats.json,
    ensuring multi-run k=2.0 matches the verified p=0.013.

    Args:
        target_scenarios: Ordered list of scenario IDs.

    Returns:
        Tuple of (model_episodes, expected_actions).
    """
    exp_actions = load_expected_actions(target_scenarios)

    all_episodes: dict[str, dict[str, list[Episode]]] = {}
    for model_name, dirs in CANONICAL_MULTI_DIRS.items():
        episodes: dict[str, list[Episode]] = defaultdict(list)
        for subdir in dirs:
            full_dir = RESULTS_DIR / subdir
            if not full_dir.exists():
                print(f"  [WARN] Multi-run dir not found: {full_dir}",
                      file=sys.stderr)
                continue
            for fpath in sorted(full_dir.glob("*.json")):
                if fpath.name.endswith("summary.json"):
                    continue
                with open(fpath) as fh:
                    data = json.load(fh)
                sid = data.get("scenario_id", "")
                if sid not in target_scenarios:
                    continue
                if "compliance_score" not in data:
                    continue
                cga = data["compliance_score"]
                acts = data.get("actions_count", 0)
                episodes[sid].append(Episode(
                    scenario_id=sid,
                    compliance_score=cga,
                    actions_count=acts,
                    source_file=str(fpath),
                ))
        all_episodes[model_name] = dict(episodes)

    return all_episodes, exp_actions


# ---------------------------------------------------------------------------
# Step 2: k-space Sweep
# ---------------------------------------------------------------------------

def compute_composite_a(
    cga: float, actions: int, exp_actions: int, k: float,
) -> float:
    """Compute Composite_A = CGA * min(1, acts / (exp * k)).

    Args:
        cga: Compliance score.
        actions: Number of actions taken.
        exp_actions: Number of expected actions.
        k: Scaling factor.

    Returns:
        Composite_A score.
    """
    denominator = exp_actions * k
    if denominator <= 0:
        return cga
    coverage = min(1.0, actions / denominator)
    return cga * coverage


def compute_composite_b(cga: float, actions: int, exp_actions: int) -> float:
    """Compute Composite_B = harmonic mean of CGA and capped coverage.

    Args:
        cga: Compliance score.
        actions: Number of actions taken.
        exp_actions: Number of expected actions.

    Returns:
        Composite_B score (harmonic mean).
    """
    coverage = min(1.0, actions / exp_actions) if exp_actions > 0 else 0.0
    if cga + coverage <= 0:
        return 0.0
    return 2.0 * cga * coverage / (cga + coverage)


def build_scenario_means(
    all_episodes: dict[str, dict[str, list[Episode]]],
    exp_actions: dict[str, int],
    target_scenarios: list[str],
    k: float,
    use_multi_run: bool = True,
) -> dict[str, list[float]]:
    """Build per-scenario composite scores for each model.

    Args:
        all_episodes: Model -> scenario -> episodes.
        exp_actions: Expected actions per scenario.
        target_scenarios: Ordered list of scenario IDs.
        k: Scaling factor for composite.
        use_multi_run: If True, average across runs; if False, use run 0 only.

    Returns:
        {model_name: [score_for_scenario_0, score_for_scenario_1, ...]}.
    """
    model_names = list(MODEL_DIRS.keys())
    result: dict[str, list[float]] = {m: [] for m in model_names}

    for sid in target_scenarios:
        exp = exp_actions.get(sid, 1)
        for model_name in model_names:
            eps = all_episodes.get(model_name, {}).get(sid, [])
            if not eps:
                result[model_name].append(0.0)
                continue
            if use_multi_run:
                # Match compute_final_stats.py: average CGA and actions
                # separately, then compute composite from the means.
                mean_cga = float(np.mean([e.compliance_score for e in eps]))
                mean_acts = float(np.mean([e.actions_count for e in eps]))
                denominator = exp * k
                if denominator <= 0:
                    result[model_name].append(mean_cga)
                else:
                    cov = min(1.0, mean_acts / denominator)
                    result[model_name].append(mean_cga * cov)
            else:
                e = eps[0]
                result[model_name].append(
                    compute_composite_a(e.compliance_score, e.actions_count, exp, k)
                )
    return result


def run_friedman(
    model_scores: dict[str, list[float]],
) -> tuple[float, float, float]:
    """Run Friedman test across models (blocked by scenario).

    Args:
        model_scores: {model_name: [scenario_scores...]}.

    Returns:
        (chi2, p_value, epsilon_squared).
    """
    model_names = list(MODEL_DIRS.keys())
    arrays = [np.array(model_scores[m]) for m in model_names]

    n_scenarios = len(arrays[0])
    n_models = len(arrays)

    try:
        stat, p_val = stats.friedmanchisquare(*arrays)
    except ValueError:
        return 0.0, 1.0, 0.0

    # epsilon^2 = chi2 / (n * (k - 1))
    denom = n_scenarios * (n_models - 1)
    eps_sq = stat / denom if denom > 0 else 0.0

    return float(stat), float(p_val), float(eps_sq)


def sweep_k_space(
    all_episodes: dict[str, dict[str, list[Episode]]],
    exp_actions: dict[str, int],
    target_scenarios: list[str],
) -> list[SweepPoint]:
    """Sweep k from K_MIN to K_MAX and compute Friedman at each point.

    Args:
        all_episodes: Model -> scenario -> episodes.
        exp_actions: Expected actions per scenario.
        target_scenarios: Ordered list of scenario IDs.

    Returns:
        List of SweepPoint results.
    """
    k_values = np.arange(K_MIN, K_MAX + K_STEP / 2, K_STEP)
    results: list[SweepPoint] = []

    for k in k_values:
        k_round = round(float(k), 1)

        # Multi-run (3-run means)
        multi_scores = build_scenario_means(
            all_episodes, exp_actions, target_scenarios, k_round, use_multi_run=True,
        )
        stat_m, p_m, eps_m = run_friedman(multi_scores)

        # Single-run (run 0 only)
        single_scores = build_scenario_means(
            all_episodes, exp_actions, target_scenarios, k_round, use_multi_run=False,
        )
        stat_s, p_s, eps_s = run_friedman(single_scores)

        # Model means
        model_means = {
            m: float(np.mean(multi_scores[m])) for m in multi_scores
        }

        results.append(SweepPoint(
            k=k_round,
            friedman_stat_multi=stat_m,
            p_value_multi=p_m,
            epsilon_sq_multi=eps_m,
            friedman_stat_single=stat_s,
            p_value_single=p_s,
            epsilon_sq_single=eps_s,
            model_means=model_means,
        ))

    return results


def sweep_k_space_split(
    single_episodes: dict[str, dict[str, list[Episode]]],
    multi_episodes: dict[str, dict[str, list[Episode]]],
    exp_actions: dict[str, int],
    target_scenarios: list[str],
) -> list[SweepPoint]:
    """Sweep k using separate single-run and multi-run episode sources.

    Args:
        single_episodes: Canonical single-run episodes (1 per scenario/model).
        multi_episodes: Multi-run episodes (may have >1 per scenario/model).
        exp_actions: Expected actions per scenario.
        target_scenarios: Ordered list of scenario IDs.

    Returns:
        List of SweepPoint results.
    """
    k_values = np.arange(K_MIN, K_MAX + K_STEP / 2, K_STEP)
    results: list[SweepPoint] = []

    for k in k_values:
        k_round = round(float(k), 1)

        # Multi-run
        multi_scores = build_scenario_means(
            multi_episodes, exp_actions, target_scenarios, k_round,
            use_multi_run=True,
        )
        stat_m, p_m, eps_m = run_friedman(multi_scores)

        # Single-run (from canonical source)
        single_scores = build_scenario_means(
            single_episodes, exp_actions, target_scenarios, k_round,
            use_multi_run=False,
        )
        stat_s, p_s, eps_s = run_friedman(single_scores)

        # Model means from multi-run
        model_means = {
            m: float(np.mean(multi_scores[m])) for m in multi_scores
        }

        results.append(SweepPoint(
            k=k_round,
            friedman_stat_multi=stat_m,
            p_value_multi=p_m,
            epsilon_sq_multi=eps_m,
            friedman_stat_single=stat_s,
            p_value_single=p_s,
            epsilon_sq_single=eps_s,
            model_means=model_means,
        ))

    return results


# ---------------------------------------------------------------------------
# Step 3: Multiple Comparison Correction
# ---------------------------------------------------------------------------

def run_prespecified_tests(
    all_episodes: dict[str, dict[str, list[Episode]]],
    exp_actions: dict[str, int],
    target_scenarios: list[str],
) -> list[ComparisonTest]:
    """Run 4 pre-specified comparison tests with correction.

    Tests:
        (a) CGA alone (k -> infinity, i.e. coverage always 1)
        (b) Composite A at k=1.0
        (c) Composite A at k=2.0
        (d) Composite B (harmonic mean)

    Args:
        all_episodes: Model -> scenario -> episodes.
        exp_actions: Expected actions per scenario.
        target_scenarios: Ordered list of scenario IDs.

    Returns:
        List of ComparisonTest objects with corrected p-values.
    """
    model_names = list(MODEL_DIRS.keys())

    # (a) CGA alone — equivalent to k=infinity
    cga_scores: dict[str, list[float]] = {m: [] for m in model_names}
    for sid in target_scenarios:
        for m in model_names:
            eps = all_episodes.get(m, {}).get(sid, [])
            if eps:
                vals = [e.compliance_score for e in eps]
                cga_scores[m].append(float(np.mean(vals)))
            else:
                cga_scores[m].append(0.0)
    stat_a, p_a, eps_a = run_friedman(cga_scores)

    # (b) Composite A at k=1.0
    scores_k1 = build_scenario_means(
        all_episodes, exp_actions, target_scenarios, k=1.0, use_multi_run=True,
    )
    stat_b, p_b, eps_b = run_friedman(scores_k1)

    # (c) Composite A at k=2.0
    scores_k2 = build_scenario_means(
        all_episodes, exp_actions, target_scenarios, k=2.0, use_multi_run=True,
    )
    stat_c, p_c, eps_c = run_friedman(scores_k2)

    # (d) Composite B (harmonic mean)
    comp_b_scores: dict[str, list[float]] = {m: [] for m in model_names}
    for sid in target_scenarios:
        exp = exp_actions.get(sid, 1)
        for m in model_names:
            eps = all_episodes.get(m, {}).get(sid, [])
            if eps:
                vals = [
                    compute_composite_b(e.compliance_score, e.actions_count, exp)
                    for e in eps
                ]
                comp_b_scores[m].append(float(np.mean(vals)))
            else:
                comp_b_scores[m].append(0.0)
    stat_d, p_d, eps_d = run_friedman(comp_b_scores)

    tests = [
        ComparisonTest("CGA alone", stat_a, p_a, eps_a),
        ComparisonTest("Composite A (k=1.0)", stat_b, p_b, eps_b),
        ComparisonTest("Composite A (k=2.0)", stat_c, p_c, eps_c),
        ComparisonTest("Composite B (harmonic)", stat_d, p_d, eps_d),
    ]

    # Apply corrections
    raw_p = [t.p_value for t in tests]

    # Bonferroni-Holm
    holm_p = _holm_bonferroni(raw_p, alpha=ALPHA)
    # Benjamini-Hochberg FDR
    bh_p = _benjamini_hochberg(raw_p, alpha=ALPHA)

    for i, t in enumerate(tests):
        t.holm_p = float(holm_p[i])
        t.bh_p = float(bh_p[i])

    return tests


def run_prespecified_tests_split(
    single_episodes: dict[str, dict[str, list[Episode]]],
    multi_episodes: dict[str, dict[str, list[Episode]]],
    exp_actions: dict[str, int],
    target_scenarios: list[str],
) -> list[ComparisonTest]:
    """Run 4 pre-specified comparison tests using multi-run data.

    Uses multi_episodes for averaging (matches compute_final_stats.py behavior).

    Args:
        single_episodes: Canonical single-run episodes.
        multi_episodes: Multi-run episodes.
        exp_actions: Expected actions per scenario.
        target_scenarios: Ordered list of scenario IDs.

    Returns:
        List of ComparisonTest objects with corrected p-values.
    """
    model_names = list(MODEL_DIRS.keys())

    # (a) CGA alone — multi-run mean
    cga_scores: dict[str, list[float]] = {m: [] for m in model_names}
    for sid in target_scenarios:
        for m in model_names:
            eps = multi_episodes.get(m, {}).get(sid, [])
            if eps:
                vals = [e.compliance_score for e in eps]
                cga_scores[m].append(float(np.mean(vals)))
            else:
                cga_scores[m].append(0.0)
    stat_a, p_a, eps_a = run_friedman(cga_scores)

    # (b) Composite A at k=1.0 — multi-run
    scores_k1 = build_scenario_means(
        multi_episodes, exp_actions, target_scenarios, k=1.0, use_multi_run=True,
    )
    stat_b, p_b, eps_b = run_friedman(scores_k1)

    # (c) Composite A at k=2.0 — multi-run
    scores_k2 = build_scenario_means(
        multi_episodes, exp_actions, target_scenarios, k=2.0, use_multi_run=True,
    )
    stat_c, p_c, eps_c = run_friedman(scores_k2)

    # (d) Composite B (harmonic mean) — multi-run
    # Use mean CGA and mean actions, then compute harmonic mean
    comp_b_scores: dict[str, list[float]] = {m: [] for m in model_names}
    for sid in target_scenarios:
        exp = exp_actions.get(sid, 1)
        for m in model_names:
            eps = multi_episodes.get(m, {}).get(sid, [])
            if eps:
                mean_cga = float(np.mean([e.compliance_score for e in eps]))
                mean_acts = float(np.mean([e.actions_count for e in eps]))
                coverage = min(1.0, mean_acts / exp) if exp > 0 else 0.0
                if mean_cga + coverage <= 0:
                    comp_b_scores[m].append(0.0)
                else:
                    comp_b_scores[m].append(
                        2.0 * mean_cga * coverage / (mean_cga + coverage)
                    )
            else:
                comp_b_scores[m].append(0.0)
    stat_d, p_d, eps_d = run_friedman(comp_b_scores)

    tests = [
        ComparisonTest("CGA alone", stat_a, p_a, eps_a),
        ComparisonTest("Composite A (k=1.0)", stat_b, p_b, eps_b),
        ComparisonTest("Composite A (k=2.0)", stat_c, p_c, eps_c),
        ComparisonTest("Composite B (harmonic)", stat_d, p_d, eps_d),
    ]

    raw_p = [t.p_value for t in tests]
    holm_p = _holm_bonferroni(raw_p, alpha=ALPHA)
    bh_p = _benjamini_hochberg(raw_p, alpha=ALPHA)

    for i, t in enumerate(tests):
        t.holm_p = float(holm_p[i])
        t.bh_p = float(bh_p[i])

    return tests


# ---------------------------------------------------------------------------
# Step 4: Visualization
# ---------------------------------------------------------------------------

def plot_pvalue_curve(sweep: list[SweepPoint], tests: list[ComparisonTest]) -> None:
    """Figure 1: k vs p-value with significance thresholds.

    Args:
        sweep: k-space sweep results.
        tests: Pre-specified tests for Holm-corrected alpha.
    """
    plt.rcParams.update(PLT_PARAMS)
    fig, ax = plt.subplots(figsize=(6, 3.5))

    ks = [s.k for s in sweep]
    p_multi = [s.p_value_multi for s in sweep]
    p_single = [s.p_value_single for s in sweep]

    ax.plot(ks, p_multi, "-o", markersize=3, color="#1f77b4", label="3-run mean", linewidth=1.2)
    ax.plot(ks, p_single, "-s", markersize=3, color="#ff7f0e", label="Single run", linewidth=1.2)

    # Alpha line
    ax.axhline(y=ALPHA, color="red", linestyle="--", linewidth=0.8, label=f"$\\alpha$ = {ALPHA}")

    # Holm-corrected alpha: most stringent = alpha / n_tests
    holm_alpha = ALPHA / len(tests)
    ax.axhline(
        y=holm_alpha, color="darkred", linestyle=":", linewidth=0.8,
        label=f"Holm $\\alpha_{{min}}$ = {holm_alpha:.4f}",
    )

    ax.set_xlabel("Coverage scaling factor $k$")
    ax.set_ylabel("Friedman $p$-value")
    ax.set_title("k-space Sensitivity: Friedman $p$-value Stability")
    ax.set_yscale("log")
    ax.set_xlim(K_MIN - 0.1, K_MAX + 0.1)
    ax.legend(loc="upper right", frameon=True, framealpha=0.9)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    out_path = FIGURES_DIR / "k_sensitivity_pvalue.pdf"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_effect_size(sweep: list[SweepPoint]) -> None:
    """Figure 2: k vs effect size (epsilon-squared).

    Args:
        sweep: k-space sweep results.
    """
    plt.rcParams.update(PLT_PARAMS)
    fig, ax = plt.subplots(figsize=(6, 3.5))

    ks = [s.k for s in sweep]
    eps_multi = [s.epsilon_sq_multi for s in sweep]
    eps_single = [s.epsilon_sq_single for s in sweep]

    ax.plot(ks, eps_multi, "-o", markersize=3, color="#1f77b4", label="3-run mean", linewidth=1.2)
    ax.plot(ks, eps_single, "-s", markersize=3, color="#ff7f0e", label="Single run", linewidth=1.2)

    # Effect size thresholds (Cohen's benchmarks for epsilon^2)
    ax.axhline(y=0.01, color="gray", linestyle=":", linewidth=0.6, alpha=0.7)
    ax.axhline(y=0.06, color="gray", linestyle="--", linewidth=0.6, alpha=0.7)
    ax.axhline(y=0.14, color="gray", linestyle="-", linewidth=0.6, alpha=0.7)
    ax.text(K_MAX + 0.05, 0.01, "small", fontsize=7, va="center", color="gray")
    ax.text(K_MAX + 0.05, 0.06, "medium", fontsize=7, va="center", color="gray")
    ax.text(K_MAX + 0.05, 0.14, "large", fontsize=7, va="center", color="gray")

    ax.set_xlabel("Coverage scaling factor $k$")
    ax.set_ylabel("Effect size ($\\varepsilon^2$)")
    ax.set_title("k-space Sensitivity: Effect Size Stability")
    ax.set_xlim(K_MIN - 0.1, K_MAX + 0.3)
    ax.legend(loc="best", frameon=True, framealpha=0.9)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    out_path = FIGURES_DIR / "k_sensitivity_effect_size.pdf"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  Saved: {out_path}")


def plot_composite_by_model(sweep: list[SweepPoint]) -> None:
    """Figure 3: k vs mean composite per model.

    Args:
        sweep: k-space sweep results.
    """
    plt.rcParams.update(PLT_PARAMS)
    fig, ax = plt.subplots(figsize=(6, 3.5))

    ks = [s.k for s in sweep]
    model_names = list(MODEL_DIRS.keys())

    for model_name in model_names:
        means = [s.model_means[model_name] for s in sweep]
        ax.plot(
            ks, means, "-o", markersize=3, linewidth=1.2,
            color=MODEL_COLORS[model_name], label=model_name,
        )

    ax.set_xlabel("Coverage scaling factor $k$")
    ax.set_ylabel("Mean Composite A score")
    ax.set_title("k-space Sensitivity: Model Composite Scores")
    ax.set_xlim(K_MIN - 0.1, K_MAX + 0.1)
    ax.set_ylim(0, 1.0)
    ax.legend(loc="best", frameon=True, framealpha=0.9)
    ax.grid(True, alpha=0.3)

    fig.tight_layout()
    out_path = FIGURES_DIR / "k_sensitivity_composite_by_model.pdf"
    fig.savefig(out_path)
    plt.close(fig)
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Step 5: Output
# ---------------------------------------------------------------------------

def write_json_results(
    sweep: list[SweepPoint],
    tests: list[ComparisonTest],
    single_episodes: dict[str, dict[str, list[Episode]]],
    multi_episodes: dict[str, dict[str, list[Episode]]],
    exp_actions: dict[str, int],
    target_scenarios: list[str],
    use_canonical: bool = True,
) -> None:
    """Write k_space_sensitivity.json with all results.

    Args:
        sweep: k-space sweep results.
        tests: Pre-specified comparison tests.
        single_episodes: Single-run episodes per model.
        multi_episodes: Multi-run episodes per model.
        exp_actions: Expected actions per scenario.
        target_scenarios: Ordered list of scenario IDs.
        use_canonical: Whether canonical data source was used.
    """
    # Build data summary
    data_summary: dict[str, dict[str, int]] = {}
    for model_name in MODEL_DIRS:
        s_eps = single_episodes.get(model_name, {})
        m_eps = multi_episodes.get(model_name, {})
        data_summary[model_name] = {
            "single_run_scenarios": len(s_eps),
            "single_run_episodes": sum(len(v) for v in s_eps.values()),
            "multi_run_scenarios": len(m_eps),
            "multi_run_episodes": sum(len(v) for v in m_eps.values()),
        }

    sweep_data = []
    for sp in sweep:
        sweep_data.append({
            "k": sp.k,
            "multi_run": {
                "friedman_chi2": round(sp.friedman_stat_multi, 4),
                "p_value": round(sp.p_value_multi, 6),
                "epsilon_sq": round(sp.epsilon_sq_multi, 4),
            },
            "single_run": {
                "friedman_chi2": round(sp.friedman_stat_single, 4),
                "p_value": round(sp.p_value_single, 6),
                "epsilon_sq": round(sp.epsilon_sq_single, 4),
            },
            "model_means": {m: round(v, 4) for m, v in sp.model_means.items()},
        })

    comparison_data = []
    for t in tests:
        comparison_data.append({
            "label": t.label,
            "friedman_chi2": round(t.test_statistic, 4),
            "p_raw": round(t.p_value, 6),
            "epsilon_sq": round(t.epsilon_sq, 4),
            "p_holm": round(t.holm_p, 6),
            "p_bh": round(t.bh_p, 6),
            "significant_raw": t.p_value < ALPHA,
            "significant_holm": t.holm_p < ALPHA,
            "significant_bh": t.bh_p < ALPHA,
        })

    # Key answers
    sig_range = [sp.k for sp in sweep if sp.p_value_multi < ALPHA]
    stable_range = (
        f"k={min(sig_range):.1f} to k={max(sig_range):.1f}"
        if sig_range
        else "No significant range found"
    )

    # Find k where ranking flips (check if model order changes)
    model_names = list(MODEL_DIRS.keys())
    rank_changes: list[float] = []
    prev_ranking: list[str] | None = None
    for sp in sweep:
        current_ranking = sorted(model_names, key=lambda m: sp.model_means[m], reverse=True)
        if prev_ranking is not None and current_ranking != prev_ranking:
            rank_changes.append(sp.k)
        prev_ranking = current_ranking

    # Best k: highest epsilon^2 among significant points
    best_k = 1.0
    best_eps = 0.0
    for sp in sweep:
        if sp.p_value_multi < ALPHA and sp.epsilon_sq_multi > best_eps:
            best_eps = sp.epsilon_sq_multi
            best_k = sp.k

    narrative = {
        "Q1_significance_range": stable_range,
        "Q2_ranking_stability": (
            f"Rankings change at k={rank_changes}" if rank_changes
            else "Rankings stable across entire k-space"
        ),
        "Q3_recommended_k": (
            f"k={best_k:.1f} (max epsilon^2={best_eps:.4f} among significant points)"
        ),
        "multi_comparison": (
            f"{sum(1 for t in tests if t.holm_p < ALPHA)}/4 tests significant "
            f"after Holm correction; "
            f"{sum(1 for t in tests if t.bh_p < ALPHA)}/4 after BH FDR"
        ),
    }

    output = {
        "metadata": {
            "n_scenarios": len(target_scenarios),
            "n_models": NUM_MODELS,
            "k_range": [K_MIN, K_MAX],
            "k_step": K_STEP,
            "alpha": ALPHA,
            "data_source": (
                "canonical (composite_metric.json single-run, "
                "compute_final_stats.py dirs multi-run)"
                if use_canonical
                else "raw-episodes (alphabetical glob)"
            ),
            "scenarios": target_scenarios,
        },
        "data_summary": data_summary,
        "k_sweep": sweep_data,
        "prespecified_comparisons": comparison_data,
        "narrative": narrative,
    }

    out_path = ANALYSIS_DIR / "k_space_sensitivity.json"
    with open(out_path, "w") as fh:
        json.dump(output, fh, indent=2)
    print(f"  Saved: {out_path}")


def write_latex_table(tests: list[ComparisonTest]) -> None:
    """Write LaTeX table for multiple comparison correction.

    Args:
        tests: Pre-specified comparison tests with corrected p-values.
    """
    lines = [
        r"\begin{table}[ht]",
        r"\centering",
        r"\caption{Multiple comparison correction for pre-specified metric tests "
        r"($\alpha=0.05$, $n=15$ scenarios, $k=4$ models).}",
        r"\label{tab:multiple_comparison}",
        r"\begin{tabular}{lcccccc}",
        r"\toprule",
        r"Metric & $\chi^2$ & $p_{\text{raw}}$ & $\varepsilon^2$ "
        r"& $p_{\text{Holm}}$ & $p_{\text{BH}}$ & Sig. \\",
        r"\midrule",
    ]

    for t in tests:
        sig_marker = ""
        if t.holm_p < ALPHA:
            sig_marker = r"$^{**}$"
        elif t.bh_p < ALPHA:
            sig_marker = r"$^{*}$"

        def fmt_p(p: float) -> str:
            if p < 0.001:
                return f"{p:.2e}"
            return f"{p:.4f}"

        lines.append(
            f"  {t.label} & {t.test_statistic:.2f} & {fmt_p(t.p_value)} "
            f"& {t.epsilon_sq:.4f} & {fmt_p(t.holm_p)} & {fmt_p(t.bh_p)} "
            f"& {sig_marker} \\\\"
        )

    lines.extend([
        r"\bottomrule",
        r"\end{tabular}",
        r"\begin{tablenotes}\small",
        r"\item $^{**}$ Significant after Holm correction; "
        r"$^{*}$ Significant after BH FDR only.",
        r"\end{tablenotes}",
        r"\end{table}",
    ])

    out_path = TABLES_DIR / "multiple_comparison_correction.tex"
    with open(out_path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="k-space sensitivity analysis for CGA-Bench composite metric.",
    )
    parser.add_argument(
        "--raw-episodes", action="store_true",
        help="Load from raw episode JSON files (legacy). Default uses canonical "
             "composite_metric.json for single-run data.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the full k-space sensitivity analysis pipeline."""
    args = parse_args()
    use_canonical = not args.raw_episodes

    print("=" * 60)
    print("P0-1 k-space Sensitivity Analysis")
    if use_canonical:
        print("  Mode: CANONICAL (composite_metric.json + compute_final_stats dirs)")
    else:
        print("  Mode: RAW-EPISODES (legacy glob)")
    print("=" * 60)

    # Determine target scenarios from reference
    ref_path = ANALYSIS_DIR / "composite_metric.json"
    ref = json.load(open(ref_path))
    target_scenarios = list(ref["per_scenario"].keys())
    print(f"\n[1/5] Loading data for {len(target_scenarios)} scenarios, "
          f"{NUM_MODELS} models...")

    if use_canonical:
        # Single-run: from composite_metric.json (canonical source)
        single_episodes, exp_actions = load_canonical_single_run(target_scenarios)
        print("  Single-run: loaded from composite_metric.json")
        for model_name in MODEL_DIRS:
            eps = single_episodes.get(model_name, {})
            print(f"    {model_name}: {len(eps)} scenarios, "
                  f"{sum(len(v) for v in eps.values())} episodes")

        # Multi-run: from canonical directory config
        multi_episodes, _ = load_canonical_multi_run(target_scenarios)
        print("  Multi-run: loaded from canonical directory config")
        for model_name in MODEL_DIRS:
            eps = multi_episodes.get(model_name, {})
            n_eps = sum(len(v) for v in eps.values())
            print(f"    {model_name}: {len(eps)} scenarios, {n_eps} episodes")

        # Use single_episodes as the primary data for the sweep
        all_episodes = single_episodes
    else:
        all_episodes, exp_actions = load_all_data(target_scenarios)
        single_episodes = all_episodes
        multi_episodes = all_episodes
        for model_name in MODEL_DIRS:
            eps = all_episodes.get(model_name, {})
            n_eps = sum(len(v) for v in eps.values())
            print(f"  {model_name}: {len(eps)} scenarios, {n_eps} episodes")

        print("\n[1b] Validating against composite_metric.json...")
        validate_against_reference(all_episodes, exp_actions)

    print(f"\n[2/5] Sweeping k = {K_MIN} to {K_MAX} (step {K_STEP})...")
    sweep = sweep_k_space_split(
        single_episodes, multi_episodes, exp_actions, target_scenarios,
    )
    n_sig = sum(1 for s in sweep if s.p_value_multi < ALPHA)
    print(f"  {n_sig}/{len(sweep)} k-values yield p < {ALPHA} (multi-run)")

    print("\n[3/5] Running 4 pre-specified comparison tests...")
    tests = run_prespecified_tests_split(
        single_episodes, multi_episodes, exp_actions, target_scenarios,
    )
    for t in tests:
        sig_str = "SIG" if t.holm_p < ALPHA else ("FDR" if t.bh_p < ALPHA else "n.s.")
        print(f"  {t.label}: chi2={t.test_statistic:.2f}, "
              f"p={t.p_value:.4f}, eps2={t.epsilon_sq:.4f} [{sig_str}]")

    print("\n[4/5] Generating publication figures...")
    plot_pvalue_curve(sweep, tests)
    plot_effect_size(sweep)
    plot_composite_by_model(sweep)

    print("\n[5/5] Writing output files...")
    write_json_results(
        sweep, tests, single_episodes, multi_episodes,
        exp_actions, target_scenarios, use_canonical,
    )
    write_latex_table(tests)

    # Print narrative summary
    print("\n" + "=" * 60)
    print("NARRATIVE SUMMARY")
    print("=" * 60)
    sig_range = [s.k for s in sweep if s.p_value_multi < ALPHA]
    if sig_range:
        print(f"  Significance range: k={min(sig_range):.1f} to k={max(sig_range):.1f}")
    else:
        print("  No k-value achieves significance at alpha=0.05")

    best_sp = max(sweep, key=lambda s: s.epsilon_sq_multi)
    print(f"  Peak effect size: eps2={best_sp.epsilon_sq_multi:.4f} at k={best_sp.k:.1f}")

    holm_sig = sum(1 for t in tests if t.holm_p < ALPHA)
    bh_sig = sum(1 for t in tests if t.bh_p < ALPHA)
    print(f"  Corrected significance: {holm_sig}/4 Holm, {bh_sig}/4 BH FDR")
    print("\nDone.")


if __name__ == "__main__":
    main()
