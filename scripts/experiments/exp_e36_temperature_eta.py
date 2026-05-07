#!/usr/bin/env python3
"""EX-36: Temperature Sensitivity -- eta-squared Decomposition
=====================================================
Compares evaluator vs run variance at T=0.1 (existing qwen27b) and T=0.6
(new qwen27b_temp06) to show evaluator dominance is not a tautology of
near-greedy sampling.

Attack: "T=0.1 makes run variance trivially zero."
Defense: eta-squared(evaluator) >> eta-squared(run) even at T=0.6.

Input:  results/full_706_v5/qwen27b/       (T=0.1)
        results/full_706_v5/qwen27b_temp06/ (T=0.6)
Output: evidence_pack/ex36_temperature_eta/

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_e36_temperature_eta.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np
from scripts.experiments._common import (
    EVIDENCE_DIR,
    RESULTS_DIR_V5,
    bootstrap_ci,
    save_figure,
    save_json,
    save_markdown,
    setup_matplotlib,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

OUTPUT_DIR = EVIDENCE_DIR / "ex36_temperature_eta"

MODELS: dict[str, str] = {
    "qwen27b": "T=0.1",
    "qwen27b_temp06": "T=0.6",
}

EVALUATOR_NAMES: list[str] = ["AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]

HARD_VIOL_TYPES: frozenset[str] = frozenset({"OMISSION", "COMMISSION", "TIMING"})
AC_COVERAGE_THRESHOLD = 0.5
MAB_F1_THRESHOLD = 0.5
C2_THRESHOLD = 0.6


# ---------------------------------------------------------------------------
# Episode loading
# ---------------------------------------------------------------------------


def _normalize_action(action_id: str) -> str:
    """Normalise an action ID for set comparison."""
    return action_id.strip().lower().replace("-", "_").replace(" ", "_")


def _classify_violation_type(raw_type: str) -> str:
    """Map raw violation type string to canonical form."""
    upper = raw_type.upper().strip()
    for canonical in ("OMISSION", "COMMISSION", "TIMING", "SEQUENCE", "DEVIATION"):
        if canonical in upper:
            return canonical
    return "UNKNOWN"


def _action_coverage(performed: set[str], expected: set[str]) -> float:
    """Fraction of expected actions covered by performed actions."""
    if not expected:
        return 1.0
    return len(performed & expected) / len(expected)


def _mab_f1(performed: set[str], expected: set[str]) -> float:
    """F1 between performed and expected action sets."""
    if not expected:
        return 0.0
    tp = len(performed & expected)
    precision = tp / len(performed) if performed else 0.0
    recall = tp / len(expected)
    if precision + recall == 0:
        return 0.0
    return 2 * precision * recall / (precision + recall)


def load_model_episodes(model: str) -> list[dict[str, Any]]:
    """Load all episode JSONs for a specific model from RESULTS_DIR_V5.

    Args:
        model: Model directory name (e.g. "qwen27b").

    Returns:
        List of episode dicts with '_model' key injected.
    """
    model_dir = RESULTS_DIR_V5 / model
    if not model_dir.exists():
        print(f"  WARNING: Model dir not found: {model_dir}")
        return []

    episodes: list[dict[str, Any]] = []
    seen: set[str] = set()

    for f in sorted(model_dir.glob("*.json")):
        if f.name.startswith(("checkpoint", ".claim", "log_")):
            continue
        try:
            ep = json.loads(f.read_text())
        except (json.JSONDecodeError, UnicodeDecodeError):
            continue
        sid = ep.get("scenario_id", "")
        if not sid:
            continue
        run_idx = ep.get("run_index", 0)
        dedup_key = f"{sid}_{model}_r{run_idx}"
        if dedup_key in seen:
            continue
        seen.add(dedup_key)
        ep["_model"] = model
        episodes.append(ep)

    return episodes


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


def score_episode(ep: dict[str, Any]) -> dict[str, Any]:
    """Extract evaluator verdicts from one episode.

    Returns dict with keys: scenario_id, run_index, ac_proxy, mab_proxy,
    c2_pass, cga_pass, v4_hard, coverage, f1, c2_score.
    """
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
    c2_score: float = ep.get("compliance_score", 0.0) or 0.0

    has_hard = False
    for v in ep.get("violation_events", []):
        raw_type = str(v.get("violation_type", v.get("type", "")))
        vtype = _classify_violation_type(raw_type)
        if vtype in HARD_VIOL_TYPES:
            has_hard = True
            break

    ac_proxy = coverage >= AC_COVERAGE_THRESHOLD
    mab_proxy = f1 >= MAB_F1_THRESHOLD
    c2_pass = c2_score >= C2_THRESHOLD
    cga_pass = not has_hard

    return {
        "scenario_id": ep.get("scenario_id", ""),
        "run_index": ep.get("run_index", 0),
        "v4_hard": has_hard,
        "ac_proxy": ac_proxy,
        "mab_proxy": mab_proxy,
        "c2_pass": c2_pass,
        "cga_pass": cga_pass,
        "coverage": round(coverage, 4),
        "f1": round(f1, 4),
        "c2_score": round(c2_score, 4),
    }


# ---------------------------------------------------------------------------
# eta-squared decomposition
# ---------------------------------------------------------------------------


def eta_squared_decomposition(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Two-way ANOVA variance decomposition: evaluator x run.

    Treats each (scenario, evaluator, run) triple as one observation.
    DV is binary pass/fail (0/1) per evaluator.

    Factor 1: evaluator (4 levels: AC-Proxy, MAB-Proxy, C2, CGA-Bench)
    Factor 2: run (0, 1, 2)

    Returns:
        Dict with eta_sq_evaluator, eta_sq_run, eta_sq_residual,
        dominance_ratio, grand_mean, n_observations.
    """
    # Build long-form observation matrix: (evaluator_idx, run_idx, value)
    observations: list[tuple[int, int, float]] = []
    evaluator_keys = ["ac_proxy", "mab_proxy", "c2_pass", "cga_pass"]

    for rec in records:
        run_idx = rec["run_index"]
        for ev_idx, ev_key in enumerate(evaluator_keys):
            val = 1.0 if rec[ev_key] else 0.0
            observations.append((ev_idx, run_idx, val))

    if not observations:
        return {
            "eta_sq_evaluator": 0.0,
            "eta_sq_run": 0.0,
            "eta_sq_residual": 0.0,
            "dominance_ratio": 0.0,
            "grand_mean": 0.0,
            "n_observations": 0,
        }

    arr = np.array(observations)  # shape (N, 3)
    values = arr[:, 2]
    grand_mean = float(np.mean(values))
    ss_total = float(np.sum((values - grand_mean) ** 2))

    if ss_total < 1e-12:
        return {
            "eta_sq_evaluator": 0.0,
            "eta_sq_run": 0.0,
            "eta_sq_residual": 1.0,
            "dominance_ratio": 0.0,
            "grand_mean": round(grand_mean, 4),
            "n_observations": len(observations),
        }

    # SS evaluator: sum over evaluator groups
    evaluator_indices = arr[:, 0].astype(int)
    ss_evaluator = 0.0
    for ev_idx in range(len(EVALUATOR_NAMES)):
        mask = evaluator_indices == ev_idx
        if not np.any(mask):
            continue
        group_mean = np.mean(values[mask])
        ss_evaluator += np.sum(mask) * (group_mean - grand_mean) ** 2
    ss_evaluator = float(ss_evaluator)

    # SS run: sum over run groups
    run_indices = arr[:, 1].astype(int)
    unique_runs = np.unique(run_indices)
    ss_run = 0.0
    for run_idx in unique_runs:
        mask = run_indices == run_idx
        if not np.any(mask):
            continue
        group_mean = np.mean(values[mask])
        ss_run += np.sum(mask) * (group_mean - grand_mean) ** 2
    ss_run = float(ss_run)

    ss_residual = ss_total - ss_evaluator - ss_run
    ss_residual = max(ss_residual, 0.0)

    eta_sq_evaluator = ss_evaluator / ss_total
    eta_sq_run = ss_run / ss_total
    eta_sq_residual = ss_residual / ss_total

    dominance_ratio = eta_sq_evaluator / eta_sq_run if eta_sq_run > 1e-12 else float("inf")

    return {
        "eta_sq_evaluator": round(eta_sq_evaluator, 6),
        "eta_sq_run": round(eta_sq_run, 6),
        "eta_sq_residual": round(eta_sq_residual, 6),
        "dominance_ratio": round(dominance_ratio, 1) if dominance_ratio != float("inf") else "inf",
        "grand_mean": round(grand_mean, 4),
        "n_observations": len(observations),
        "ss_total": round(ss_total, 2),
        "ss_evaluator": round(ss_evaluator, 2),
        "ss_run": round(ss_run, 2),
        "ss_residual": round(ss_residual, 2),
    }


# ---------------------------------------------------------------------------
# Agreement metrics
# ---------------------------------------------------------------------------


def compute_agreement_metrics(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute verdict-flip rate, 3/3 agreement rate, and FA rate.

    Args:
        records: List of scored episode dicts.

    Returns:
        Dict with flip_rate, agree_3_3_rate, fa_rate, n_episodes.
    """
    n = len(records)
    if n == 0:
        return {
            "flip_rate": 0.0,
            "agree_3_3_rate": 0.0,
            "fa_rate": 0.0,
            "n_episodes": 0,
        }

    # Verdict-flip: any evaluator disagrees within an episode
    flip_count = 0
    for rec in records:
        verdicts = [rec["ac_proxy"], rec["mab_proxy"], rec["c2_pass"], rec["cga_pass"]]
        if len(set(verdicts)) > 1:
            flip_count += 1
    flip_rate = flip_count / n * 100

    # 3/3 agreement: for each (scenario, evaluator), all 3 runs agree
    # Group by scenario_id
    scenario_runs: dict[str, list[dict[str, Any]]] = {}
    for rec in records:
        sid = rec["scenario_id"]
        scenario_runs.setdefault(sid, []).append(rec)

    total_scenario_evaluator_pairs = 0
    agree_count = 0
    evaluator_keys = ["ac_proxy", "mab_proxy", "c2_pass", "cga_pass"]
    for _sid, runs in scenario_runs.items():
        if len(runs) < 3:
            continue
        for ev_key in evaluator_keys:
            verdicts_for_ev = [r[ev_key] for r in runs]
            total_scenario_evaluator_pairs += 1
            if len(set(verdicts_for_ev)) == 1:
                agree_count += 1
    agree_3_3_rate = (
        agree_count / total_scenario_evaluator_pairs * 100
        if total_scenario_evaluator_pairs > 0
        else 0.0
    )

    # FA rate: all-oblivious false accept (v4_hard AND ac_proxy AND c2_pass)
    fa_count = sum(
        1 for rec in records if rec["v4_hard"] and rec["ac_proxy"] and rec["c2_pass"]
    )
    fa_rate = fa_count / n * 100

    # Bootstrap CIs
    flip_arr = np.array([
        1 if len({r["ac_proxy"], r["mab_proxy"], r["c2_pass"], r["cga_pass"]}) > 1 else 0
        for r in records
    ])
    flip_ci = bootstrap_ci(flip_arr, np.mean)

    fa_arr = np.array([
        1 if r["v4_hard"] and r["ac_proxy"] and r["c2_pass"] else 0
        for r in records
    ])
    fa_ci = bootstrap_ci(fa_arr, np.mean)

    return {
        "flip_rate": round(flip_rate, 1),
        "flip_ci_95": [round(flip_ci[0] * 100, 1), round(flip_ci[1] * 100, 1)],
        "agree_3_3_rate": round(agree_3_3_rate, 1),
        "agree_3_3_pairs": total_scenario_evaluator_pairs,
        "agree_3_3_count": agree_count,
        "fa_rate": round(fa_rate, 1),
        "fa_ci_95": [round(fa_ci[0] * 100, 1), round(fa_ci[1] * 100, 1)],
        "fa_count": fa_count,
        "n_episodes": n,
    }


# ---------------------------------------------------------------------------
# Figure: eta-squared comparison bar chart
# ---------------------------------------------------------------------------


def make_eta_comparison_chart(
    eta_results: dict[str, dict[str, Any]],
) -> None:
    """Generate side-by-side bar chart comparing eta-squared decomposition."""
    setup_matplotlib()
    import matplotlib.pyplot as plt

    labels = list(eta_results.keys())
    if not labels:
        return

    evaluator_vals = [eta_results[k].get("eta_sq_evaluator", 0.0) for k in labels]
    run_vals = [eta_results[k].get("eta_sq_run", 0.0) for k in labels]
    residual_vals = [eta_results[k].get("eta_sq_residual", 0.0) for k in labels]

    x = np.arange(len(labels))
    width = 0.25

    fig, ax = plt.subplots(figsize=(8, 5))
    bars_ev = ax.bar(x - width, evaluator_vals, width, label="Evaluator", color="#2196F3")
    bars_run = ax.bar(x, run_vals, width, label="Run", color="#FF9800")
    bars_res = ax.bar(x + width, residual_vals, width, label="Residual", color="#9E9E9E")

    ax.set_ylabel("eta-squared (proportion of variance)")
    ax.set_title("EX-36: Variance Decomposition by Temperature")
    ax.set_xticks(x)
    ax.set_xticklabels(labels)
    ax.legend()
    ax.set_ylim(0, 1.05)

    # Value labels on bars
    for bars in (bars_ev, bars_run, bars_res):
        for bar in bars:
            height = bar.get_height()
            if height > 0.01:
                ax.annotate(
                    f"{height:.3f}",
                    xy=(bar.get_x() + bar.get_width() / 2, height),
                    xytext=(0, 3),
                    textcoords="offset points",
                    ha="center",
                    va="bottom",
                    fontsize=8,
                )

    save_figure(fig, OUTPUT_DIR / "ex36_eta_comparison.png")


# ---------------------------------------------------------------------------
# Macro generation
# ---------------------------------------------------------------------------


def generate_macros(
    eta_results: dict[str, dict[str, Any]],
    agreement_results: dict[str, dict[str, Any]],
) -> str:
    """Generate LaTeX macros for paper inclusion.

    Args:
        eta_results: Keyed by temperature label ("T=0.1", "T=0.6").
        agreement_results: Keyed by temperature label.

    Returns:
        LaTeX macro string.
    """
    lines = [
        "% EX-36: Temperature Sensitivity -- eta-squared Decomposition",
        "% Auto-generated by exp_e36_temperature_eta.py",
        "",
    ]

    t01 = eta_results.get("T=0.1", {})
    t06 = eta_results.get("T=0.6", {})
    ag06 = agreement_results.get("T=0.6", {})

    eta_eval_one = t01.get("eta_sq_evaluator", 0.0)
    eta_run_one = t01.get("eta_sq_run", 0.0)
    eta_eval_six = t06.get("eta_sq_evaluator", 0.0)
    eta_run_six = t06.get("eta_sq_run", 0.0)

    # Dominance ratio for T=0.6
    if isinstance(t06.get("dominance_ratio"), str):
        eta_ratio = t06["dominance_ratio"]
    else:
        eta_ratio = f"{t06.get('dominance_ratio', 0.0)}"

    lines.extend([
        "% T=0.1 decomposition",
        f"\\newcommand{{\\tempEtaSqEvalOne}}{{{eta_eval_one * 100:.2f}}}",
        f"\\newcommand{{\\tempEtaSqRunOne}}{{{eta_run_one * 100:.2f}}}",
        "",
        "% T=0.6 decomposition",
        f"\\newcommand{{\\tempEtaSqEvalSix}}{{{eta_eval_six * 100:.2f}}}",
        f"\\newcommand{{\\tempEtaSqRunSix}}{{{eta_run_six * 100:.2f}}}",
        "",
        "% T=0.6 evaluator/run dominance ratio",
        f"\\newcommand{{\\tempEtaRatio}}{{{eta_ratio}}}",
        "",
        "% T=0.6 agreement metrics",
        f"\\newcommand{{\\tempFARateSix}}{{{ag06.get('fa_rate', 0.0)}}}",
        f"\\newcommand{{\\tempFlipRateSix}}{{{ag06.get('flip_rate', 0.0)}}}",
        f"\\newcommand{{\\tempAgreeThreeThree}}{{{ag06.get('agree_3_3_rate', 0.0)}}}",
    ])

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------


def generate_markdown(
    eta_results: dict[str, dict[str, Any]],
    agreement_results: dict[str, dict[str, Any]],
    status: str,
) -> str:
    """Generate markdown report for evidence pack.

    Args:
        eta_results: Keyed by temperature label.
        agreement_results: Keyed by temperature label.
        status: "complete" or "pending".

    Returns:
        Markdown string.
    """
    lines = [
        "# EX-36: Temperature Sensitivity -- eta-squared Decomposition",
        "",
        f"**Status**: {status}",
        "",
        "## Attack",
        "",
        "> T=0.1 makes run variance trivially zero. Evaluator >> run is a tautology.",
        "",
        "## Defense",
        "",
        "> eta-squared(evaluator) >> eta-squared(run) even at T=0.6 with real run variance.",
        "",
        "## eta-squared Decomposition",
        "",
        "| Temperature | eta-sq(eval) | eta-sq(run) | eta-sq(resid) | Dominance Ratio |",
        "|------------|--------------|-------------|---------------|-----------------|",
    ]

    for label, eta in eta_results.items():
        ev = eta.get("eta_sq_evaluator", 0.0)
        ru = eta.get("eta_sq_run", 0.0)
        re = eta.get("eta_sq_residual", 0.0)
        dr = eta.get("dominance_ratio", 0.0)
        lines.append(f"| {label} | {ev:.4f} | {ru:.4f} | {re:.4f} | {dr} |")

    lines.extend([
        "",
        "## Agreement Metrics",
        "",
        "| Temperature | N | Flip% | 3/3 Agree% | FA% |",
        "|------------|---|-------|-----------|-----|",
    ])

    for label, ag in agreement_results.items():
        n = ag.get("n_episodes", 0)
        fl = ag.get("flip_rate", 0.0)
        agree = ag.get("agree_3_3_rate", 0.0)
        fa = ag.get("fa_rate", 0.0)
        lines.append(f"| {label} | {n} | {fl} | {agree} | {fa} |")

    lines.append("")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run EX-36 temperature sensitivity analysis."""
    print("=" * 60)
    print("EX-36: Temperature Sensitivity -- eta-squared Decomposition")
    print("=" * 60)

    eta_results: dict[str, dict[str, Any]] = {}
    agreement_results: dict[str, dict[str, Any]] = {}
    status = "complete"

    for model_key, temp_label in MODELS.items():
        print(f"\n--- {temp_label} ({model_key}) ---")
        episodes = load_model_episodes(model_key)

        if not episodes:
            print(f"  SKIP: no episodes found for {model_key}")
            eta_results[temp_label] = {
                "eta_sq_evaluator": 0.0,
                "eta_sq_run": 0.0,
                "eta_sq_residual": 0.0,
                "dominance_ratio": 0.0,
                "status": "no_data",
            }
            agreement_results[temp_label] = {
                "flip_rate": 0.0,
                "agree_3_3_rate": 0.0,
                "fa_rate": 0.0,
                "n_episodes": 0,
                "status": "no_data",
            }
            if temp_label == "T=0.6":
                status = "pending"
            continue

        print(f"  Loaded {len(episodes)} episodes")
        records = [score_episode(ep) for ep in episodes]

        # eta-squared decomposition
        eta = eta_squared_decomposition(records)
        eta_results[temp_label] = eta
        print(f"  eta-sq(eval)={eta['eta_sq_evaluator']:.4f}  "
              f"eta-sq(run)={eta['eta_sq_run']:.4f}  "
              f"ratio={eta['dominance_ratio']}")

        # Agreement metrics
        ag = compute_agreement_metrics(records)
        agreement_results[temp_label] = ag
        print(f"  Flip={ag['flip_rate']}%  3/3-agree={ag['agree_3_3_rate']}%  "
              f"FA={ag['fa_rate']}%")

    # Build full results
    results: dict[str, Any] = {
        "experiment": "EX-36",
        "description": "Temperature sensitivity eta-squared decomposition",
        "attack": "T=0.1 makes run variance trivially zero",
        "defense": "eta-sq(evaluator) >> eta-sq(run) even at T=0.6",
        "status": status,
        "eta_decomposition": eta_results,
        "agreement_metrics": agreement_results,
    }

    # Save outputs
    save_json(results, OUTPUT_DIR / "ex36_results.json")

    md = generate_markdown(eta_results, agreement_results, status)
    save_markdown(md, OUTPUT_DIR / "ex36_report.md")

    macros = generate_macros(eta_results, agreement_results)
    macros_path = OUTPUT_DIR / "macros.tex"
    macros_path.parent.mkdir(parents=True, exist_ok=True)
    macros_path.write_text(macros)
    print(f"  Saved: {macros_path}")

    # Generate chart (only if at least one model has data)
    has_data = any(
        eta.get("n_observations", 0) > 0
        for eta in eta_results.values()
    )
    if has_data:
        make_eta_comparison_chart(eta_results)

    # Print summary
    print("\n" + "=" * 60)
    print(f"EX-36 {status.upper()}")
    print("=" * 60)
    if status == "pending":
        print("  T=0.6 data not yet available. Run qwen27b_temp06 first.")
        print("  Re-run this script after results/full_706_v5/qwen27b_temp06/ is populated.")
    else:
        for label in ("T=0.1", "T=0.6"):
            eta = eta_results.get(label, {})
            print(f"  {label}: eta-sq(eval)={eta.get('eta_sq_evaluator', 0):.4f}  "
                  f"eta-sq(run)={eta.get('eta_sq_run', 0):.4f}")

    print("\n>>> Paste macros.tex contents into auto_numbers.tex <<<")


if __name__ == "__main__":
    main()
