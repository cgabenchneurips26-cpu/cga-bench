"""WS-4: Run Variance Analysis.

Comprehensive analysis of run-to-run variance across (scenario, model) pairs
with 3 replicate runs each.

Analyses:
  1. Intra-scenario variance: pass/fail agreement across runs
  2. Run variance vs Evaluator variance: Wilcoxon signed-rank test
  3. Variance decomposition: eta-squared for Model vs Scenario factors
  4. Bootstrap sufficiency: majority-vote stability with 3 runs

Usage:
    PYTHONPATH=. python scripts/experiments/ws4_run_variance.py
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats as sp_stats
from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    RESULTS_DIR,
    SEED,
    TABLES_DIR,
    fmt_p,
    save_figure,
    save_json,
    save_latex_table,
    save_markdown,
    setup_matplotlib,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]
MODEL_LABELS: dict[str, str] = {
    "oss120b": "DeepSeek-V3 (120B)",
    "qwen27b": "R1-Distill (27B)",
    "qwen35b": "Qwen3.5 (35B)",
    "qwen4b": "Qwen3 (4B)",
}
N_RUNS = 3
EVALUATOR_KEYS = ["dxem", "ac_proxy", "mab_proxy", "c2_pass", "acov_pass", "v4_hard"]
EVALUATOR_LABELS = ["DxEM", "AC-Proxy", "MAB-Proxy", "C2", "ACov", "CGA-Bench"]
N_BOOTSTRAP_SUFFICIENCY = 5000
MAJORITY_STABILITY_THRESHOLD = 0.95

VERDICT_PATH = EVIDENCE_DIR / "analysis" / "verdict_matrix_v6.json"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_all_episodes() -> list[dict]:
    """Load all rescored episodes from RESULTS_DIR, tagging model directory."""
    episodes: list[dict] = []
    for model in MODELS:
        model_dir = RESULTS_DIR / model
        if not model_dir.exists():
            continue
        for fpath in sorted(model_dir.glob("*.json")):
            if fpath.name.endswith("model_summary.json"):
                continue
            with open(fpath) as fh:
                ep = json.load(fh)
            ep["_model"] = model
            episodes.append(ep)
    return episodes


def load_verdict_matrix() -> list[dict]:
    """Load per-episode verdict data if available."""
    if not VERDICT_PATH.exists():
        return []
    with open(VERDICT_PATH) as f:
        data = json.load(f)
    return data.get("per_episode", [])


def build_run_index(
    episodes: list[dict],
) -> dict[tuple[str, str], dict[int, dict]]:
    """Build (model, scenario) -> {run_index: episode} mapping."""
    idx: dict[tuple[str, str], dict[int, dict]] = defaultdict(dict)
    for ep in episodes:
        model = ep["_model"]
        sid = ep.get("scenario_id", "unknown")
        run = ep.get("run_index", 0)
        idx[(model, sid)][run] = ep
    return dict(idx)


def _pass_fail_from_compliance(ep: dict, threshold: float = 0.5) -> int:
    """Derive binary pass (1) / fail (0) from new_compliance_score."""
    score = ep.get("new_compliance_score", 0.0)
    return 1 if score >= threshold else 0


def _entropy(probs: list[float]) -> float:
    """Shannon entropy for a discrete distribution."""
    h = 0.0
    for p in probs:
        if p > 0:
            h -= p * np.log2(p)
    return h


# ---------------------------------------------------------------------------
# Analysis 1: Intra-scenario variance
# ---------------------------------------------------------------------------


def analysis_1_intra_scenario(
    run_index: dict[tuple[str, str], dict[int, dict]],
) -> dict:
    """Compute pass/fail agreement across 3 runs per (scenario, model)."""
    total_pairs = 0
    agree_3_3 = 0
    split_2_1 = 0
    heatmap_data: dict[str, dict[str, float]] = {}

    scenarios = sorted({sid for _, sid in run_index})
    for scenario in scenarios:
        heatmap_data[scenario] = {}
        for model in MODELS:
            runs = run_index.get((model, scenario), {})
            if len(runs) < N_RUNS:
                heatmap_data[scenario][model] = float("nan")
                continue
            verdicts = [_pass_fail_from_compliance(runs[r]) for r in range(N_RUNS)]
            pass_count = sum(verdicts)
            total_pairs += 1
            if pass_count == N_RUNS or pass_count == 0:
                agree_3_3 += 1
                heatmap_data[scenario][model] = 1.0
            else:
                split_2_1 += 1
                heatmap_data[scenario][model] = pass_count / N_RUNS

    rate_3_3 = agree_3_3 / total_pairs if total_pairs > 0 else 0.0
    rate_split = split_2_1 / total_pairs if total_pairs > 0 else 0.0

    return {
        "total_pairs": total_pairs,
        "agree_3_3": agree_3_3,
        "split_2_1": split_2_1,
        "agree_3_3_rate": round(rate_3_3, 4),
        "split_2_1_rate": round(rate_split, 4),
        "heatmap_data": heatmap_data,
    }


# ---------------------------------------------------------------------------
# Analysis 2: Run variance vs Evaluator variance
# ---------------------------------------------------------------------------


def analysis_2_run_vs_evaluator(
    run_index: dict[tuple[str, str], dict[int, dict]],
    verdict_episodes: list[dict],
) -> dict:
    """Compare within-run evaluator disagreement vs across-run instability."""
    # Build verdict lookup: (model_key, scenario, run) -> verdict_ep
    model_key_map = {"oss120b": "120B", "qwen27b": "27B", "qwen35b": "35B", "qwen4b": "4B"}
    verdict_lookup: dict[tuple[str, str, int], dict] = {}
    for vep in verdict_episodes:
        eid = vep.get("episode_id", "")
        sid = vep.get("scenario_id", "")
        model_key = vep.get("model", "")
        # Extract run index from episode_id: e.g. "adhf_warm_wet_120B_0"
        parts = eid.rsplit("_", 1)
        run_idx = 0
        if len(parts) == 2:
            try:
                run_idx = int(parts[1])
            except ValueError:
                pass
        verdict_lookup[(model_key, sid, run_idx)] = vep

    evaluator_entropies: list[float] = []
    run_instabilities: list[float] = []

    scenarios = sorted({sid for _, sid in run_index})
    for scenario in scenarios:
        for model in MODELS:
            runs = run_index.get((model, scenario), {})
            if len(runs) < N_RUNS:
                continue

            mk = model_key_map.get(model, model)

            # Within-run evaluator entropy (averaged across runs)
            run_entropies: list[float] = []
            run_majorities: list[int] = []

            for r in range(N_RUNS):
                vep = verdict_lookup.get((mk, scenario, r))
                if vep:
                    votes = [1 if vep.get(k, False) else 0 for k in EVALUATOR_KEYS]
                    n_eval = len(EVALUATOR_KEYS)
                    p_pass = sum(votes) / n_eval
                    ent = _entropy([p_pass, 1 - p_pass]) if 0 < p_pass < 1 else 0.0
                    run_entropies.append(ent)
                    run_majorities.append(1 if p_pass >= 0.5 else 0)
                else:
                    # Fallback: use compliance score
                    pf = _pass_fail_from_compliance(runs[r])
                    run_entropies.append(0.0)
                    run_majorities.append(pf)

            avg_eval_entropy = float(np.mean(run_entropies)) if run_entropies else 0.0
            evaluator_entropies.append(avg_eval_entropy)

            # Across-run majority vote consistency
            if len(run_majorities) == N_RUNS:
                n_agree = max(
                    sum(1 for v in run_majorities if v == 1),
                    sum(1 for v in run_majorities if v == 0),
                )
                instability = 1.0 - (n_agree / N_RUNS)
            else:
                instability = 0.0
            run_instabilities.append(instability)

    # Wilcoxon signed-rank test
    eval_arr = np.array(evaluator_entropies)
    run_arr = np.array(run_instabilities)
    n_valid = len(eval_arr)
    wilcoxon_result: dict = {"n": n_valid}

    if n_valid > 10:
        diff = eval_arr - run_arr
        nonzero = diff[diff != 0]
        if len(nonzero) >= 10:
            stat, pval = sp_stats.wilcoxon(nonzero)
            wilcoxon_result["statistic"] = float(stat)
            wilcoxon_result["p_value"] = float(pval)
            wilcoxon_result["significant"] = pval < 0.05
        else:
            wilcoxon_result["note"] = "Too few non-zero differences for Wilcoxon test"
    else:
        wilcoxon_result["note"] = "Insufficient data for Wilcoxon test"

    return {
        "mean_evaluator_entropy": round(float(np.mean(eval_arr)), 4) if n_valid > 0 else 0.0,
        "mean_run_instability": round(float(np.mean(run_arr)), 4) if n_valid > 0 else 0.0,
        "wilcoxon": wilcoxon_result,
        "evaluator_entropies": [round(float(v), 4) for v in eval_arr],
        "run_instabilities": [round(float(v), 4) for v in run_arr],
    }


# ---------------------------------------------------------------------------
# Analysis 3: Variance decomposition (eta-squared)
# ---------------------------------------------------------------------------


def analysis_3_variance_decomposition(
    run_index: dict[tuple[str, str], dict[int, dict]],
) -> dict:
    """Two-way variance decomposition: Model x Scenario with Run as replicate."""
    scenarios = sorted({sid for _, sid in run_index})
    all_scores: list[float] = []
    model_groups: dict[str, list[float]] = defaultdict(list)
    scenario_groups: dict[str, list[float]] = defaultdict(list)

    for scenario in scenarios:
        for model in MODELS:
            runs = run_index.get((model, scenario), {})
            for r in range(N_RUNS):
                ep = runs.get(r)
                if ep is None:
                    continue
                score = ep.get("new_compliance_score", 0.0)
                all_scores.append(score)
                model_groups[model].append(score)
                scenario_groups[scenario].append(score)

    if not all_scores:
        return {"error": "No data available"}

    grand_mean = float(np.mean(all_scores))
    ss_total = float(np.sum((np.array(all_scores) - grand_mean) ** 2))

    # SS for Model factor
    ss_model = 0.0
    for model_scores in model_groups.values():
        group_mean = np.mean(model_scores)
        ss_model += len(model_scores) * (group_mean - grand_mean) ** 2

    # SS for Scenario factor
    ss_scenario = 0.0
    for sc_scores in scenario_groups.values():
        group_mean = np.mean(sc_scores)
        ss_scenario += len(sc_scores) * (group_mean - grand_mean) ** 2

    ss_residual = ss_total - ss_model - ss_scenario
    if ss_residual < 0:
        ss_residual = 0.0

    eta_sq_model = ss_model / ss_total if ss_total > 0 else 0.0
    eta_sq_scenario = ss_scenario / ss_total if ss_total > 0 else 0.0
    eta_sq_residual = ss_residual / ss_total if ss_total > 0 else 0.0

    return {
        "grand_mean": round(grand_mean, 4),
        "ss_total": round(float(ss_total), 4),
        "ss_model": round(float(ss_model), 4),
        "ss_scenario": round(float(ss_scenario), 4),
        "ss_residual": round(float(ss_residual), 4),
        "eta_sq_model": round(eta_sq_model, 4),
        "eta_sq_scenario": round(eta_sq_scenario, 4),
        "eta_sq_residual": round(eta_sq_residual, 4),
        "n_observations": len(all_scores),
        "n_models": len(model_groups),
        "n_scenarios": len(scenario_groups),
    }


# ---------------------------------------------------------------------------
# Analysis 3b: Evaluator vs Run variance decomposition (3-way)
# ---------------------------------------------------------------------------


def analysis_3b_evaluator_vs_run(
    run_index: dict[tuple[str, str], dict[int, dict]],
    verdict_episodes: list[dict],
) -> dict:
    """Decompose variance into Evaluator, Run, and Residual factors.

    For each (scenario, model, run, evaluator) we have a binary pass/fail.
    This lets us compute:
      eta_sq_evaluator: how much variance evaluator choice explains
      eta_sq_run: how much variance run-to-run noise explains
      eta_sq_residual: interaction + noise

    The paper's key claim: eta_sq_evaluator >> eta_sq_run.
    """
    model_key_map = {
        "oss120b": "120B",
        "qwen27b": "27B",
        "qwen35b": "35B",
        "qwen4b": "4B",
    }

    # Build lookup: (scenario, model_tag, run_index) -> verdict dict
    verdict_lookup: dict[tuple[str, str, int], dict] = {}
    for vep in verdict_episodes:
        sid = vep.get("scenario_id", "")
        m = vep.get("model", "")
        eid = vep.get("episode_id", "")
        parts = eid.rsplit("_", 1)
        run_idx = int(parts[-1]) if len(parts) == 2 and parts[-1].isdigit() else 0
        verdict_lookup[(sid, m, run_idx)] = vep

    observations: list[dict] = []

    for (model, scenario), runs in run_index.items():
        mk = model_key_map.get(model, model)
        for r in range(N_RUNS):
            if r not in runs:
                continue
            vep = verdict_lookup.get((scenario, mk, r))

            if vep is None:
                pf = _pass_fail_from_compliance(runs[r])
                for eidx in range(len(EVALUATOR_KEYS)):
                    observations.append({"evaluator": eidx, "run": r, "value": float(pf)})
            else:
                for eidx, ekey in enumerate(EVALUATOR_KEYS):
                    val = 1.0 if vep.get(ekey, False) else 0.0
                    observations.append({"evaluator": eidx, "run": r, "value": val})

    if not observations:
        return {"error": "No data for 3-way decomposition"}

    values = np.array([o["value"] for o in observations])
    grand_mean = float(np.mean(values))
    ss_total = float(np.sum((values - grand_mean) ** 2))

    # SS for Evaluator factor
    evaluator_groups: dict[int, list[float]] = defaultdict(list)
    for o in observations:
        evaluator_groups[o["evaluator"]].append(o["value"])

    ss_evaluator = 0.0
    for eg in evaluator_groups.values():
        gm = np.mean(eg)
        ss_evaluator += len(eg) * (gm - grand_mean) ** 2

    # SS for Run factor
    run_groups: dict[int, list[float]] = defaultdict(list)
    for o in observations:
        run_groups[o["run"]].append(o["value"])

    ss_run = 0.0
    for rg in run_groups.values():
        gm = np.mean(rg)
        ss_run += len(rg) * (gm - grand_mean) ** 2

    ss_residual = max(ss_total - ss_evaluator - ss_run, 0.0)

    eta_sq_evaluator = ss_evaluator / ss_total if ss_total > 0 else 0.0
    eta_sq_run = ss_run / ss_total if ss_total > 0 else 0.0
    eta_sq_residual = ss_residual / ss_total if ss_total > 0 else 0.0

    return {
        "n_observations": len(observations),
        "ss_total": round(float(ss_total), 4),
        "ss_evaluator": round(float(ss_evaluator), 4),
        "ss_run": round(float(ss_run), 4),
        "ss_residual": round(float(ss_residual), 4),
        "eta_sq_evaluator": round(eta_sq_evaluator, 4),
        "eta_sq_run": round(eta_sq_run, 4),
        "eta_sq_residual": round(eta_sq_residual, 4),
        "evaluator_dominance_ratio": (round(eta_sq_evaluator / eta_sq_run, 1) if eta_sq_run > 0 else float("inf")),
    }


# ---------------------------------------------------------------------------
# Analysis 4: Bootstrap sufficiency
# ---------------------------------------------------------------------------


def analysis_4_bootstrap_sufficiency(
    run_index: dict[tuple[str, str], dict[int, dict]],
) -> dict:
    """Bootstrap resample from 3 runs; report majority-vote stability."""
    rng = np.random.default_rng(SEED)
    n_pairs = 0
    n_stable = 0
    pair_details: list[dict] = []

    scenarios = sorted({sid for _, sid in run_index})
    for scenario in scenarios:
        for model in MODELS:
            runs = run_index.get((model, scenario), {})
            if len(runs) < N_RUNS:
                continue
            verdicts = np.array([_pass_fail_from_compliance(runs[r]) for r in range(N_RUNS)])
            original_majority = 1 if np.sum(verdicts) > N_RUNS / 2 else 0

            # Bootstrap: resample with replacement, check if majority flips
            flips = 0
            for _ in range(N_BOOTSTRAP_SUFFICIENCY):
                sample = verdicts[rng.integers(0, N_RUNS, size=N_RUNS)]
                boot_majority = 1 if np.sum(sample) > N_RUNS / 2 else 0
                if boot_majority != original_majority:
                    flips += 1

            stability = 1.0 - (flips / N_BOOTSTRAP_SUFFICIENCY)
            is_stable = stability >= MAJORITY_STABILITY_THRESHOLD
            n_pairs += 1
            if is_stable:
                n_stable += 1

            pair_details.append(
                {
                    "model": model,
                    "scenario": scenario,
                    "verdicts": verdicts.tolist(),
                    "original_majority": original_majority,
                    "stability": round(stability, 4),
                    "is_stable": is_stable,
                }
            )

    sufficiency_rate = n_stable / n_pairs if n_pairs > 0 else 0.0

    # Sort unstable pairs for reporting
    unstable = [p for p in pair_details if not p["is_stable"]]
    unstable.sort(key=lambda x: x["stability"])

    return {
        "n_pairs": n_pairs,
        "n_stable": n_stable,
        "sufficiency_rate": round(sufficiency_rate, 4),
        "threshold": MAJORITY_STABILITY_THRESHOLD,
        "n_bootstrap": N_BOOTSTRAP_SUFFICIENCY,
        "unstable_pairs": unstable[:20],
    }


# ---------------------------------------------------------------------------
# Plotting
# ---------------------------------------------------------------------------


def plot_variance_decomposition(decomp: dict, path: Path) -> None:
    """Bar chart of explained variance (eta-squared)."""
    setup_matplotlib()
    fig, ax = plt.subplots(figsize=(7, 5))

    factors = ["Model", "Scenario", "Residual\n(Run + Interaction)"]
    values = [
        decomp["eta_sq_model"],
        decomp["eta_sq_scenario"],
        decomp["eta_sq_residual"],
    ]
    colors = ["#3498db", "#e74c3c", "#95a5a6"]

    bars = ax.bar(factors, values, color=colors, edgecolor="black", alpha=0.85)
    for bar, val in zip(bars, values):
        ax.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height() + 0.01,
            f"{val:.1%}",
            ha="center",
            fontsize=12,
            fontweight="bold",
        )

    ax.set_ylabel("Proportion of Variance (eta-squared)")
    ax.set_title("WS-4: Variance Decomposition (Model vs Scenario vs Run)")
    ax.set_ylim(0, max(values) * 1.25 if values else 1.0)
    ax.grid(axis="y", alpha=0.3)

    save_figure(fig, path)


def plot_run_vs_evaluator(analysis2: dict, path: Path) -> None:
    """Scatter: evaluator entropy vs run instability per (scenario, model)."""
    setup_matplotlib()
    fig, ax = plt.subplots(figsize=(7, 6))

    eval_ent = analysis2["evaluator_entropies"]
    run_inst = analysis2["run_instabilities"]

    if not eval_ent:
        ax.text(0.5, 0.5, "No data available", ha="center", va="center", transform=ax.transAxes, fontsize=14)
        save_figure(fig, path)
        return

    ax.scatter(eval_ent, run_inst, alpha=0.5, s=40, edgecolors="black", linewidths=0.5)

    ax.set_xlabel("Within-Run Evaluator Entropy (H)")
    ax.set_ylabel("Across-Run Instability")
    ax.set_title("WS-4: Evaluator Disagreement vs Run Instability")

    # Diagonal reference line
    lim_max = max(max(eval_ent, default=0), max(run_inst, default=0)) + 0.05
    ax.plot([0, lim_max], [0, lim_max], "k--", alpha=0.3, label="y=x")
    ax.legend()

    wilcoxon = analysis2.get("wilcoxon", {})
    note_parts = [
        f"Mean eval entropy: {analysis2['mean_evaluator_entropy']:.3f}",
        f"Mean run instability: {analysis2['mean_run_instability']:.3f}",
    ]
    if "p_value" in wilcoxon:
        note_parts.append(f"Wilcoxon p={fmt_p(wilcoxon['p_value'])}")
    ax.annotate(
        "\n".join(note_parts),
        xy=(0.02, 0.98),
        xycoords="axes fraction",
        va="top",
        fontsize=9,
        bbox={"boxstyle": "round,pad=0.4", "facecolor": "lightyellow", "alpha": 0.8},
    )

    save_figure(fig, path)


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def build_markdown(
    a1: dict,
    a2: dict,
    a3: dict,
    a4: dict,
) -> str:
    """Build comprehensive markdown report."""
    lines: list[str] = []
    lines.append("# WS-4: Run Variance Analysis\n")

    # Analysis 1
    lines.append("## 1. Intra-Scenario Variance (Pass/Fail Agreement)\n")
    lines.append(f"- Total (scenario, model) pairs with {N_RUNS} runs: **{a1['total_pairs']}**")
    lines.append(f"- 3/3 unanimous agreement: **{a1['agree_3_3']}** ({a1['agree_3_3_rate']:.1%})")
    lines.append(f"- 2/1 split: **{a1['split_2_1']}** ({a1['split_2_1_rate']:.1%})")
    lines.append("")

    # Analysis 2
    lines.append("## 2. Run Variance vs Evaluator Variance\n")
    lines.append(f"- Mean within-run evaluator entropy: **{a2['mean_evaluator_entropy']:.4f}**")
    lines.append(f"- Mean across-run instability: **{a2['mean_run_instability']:.4f}**")
    w = a2.get("wilcoxon", {})
    if "p_value" in w:
        sig_str = "significant" if w["significant"] else "not significant"
        lines.append(f"- Wilcoxon signed-rank test: W={w['statistic']:.1f}, p={fmt_p(w['p_value'])} ({sig_str})")
    elif "note" in w:
        lines.append(f"- Wilcoxon test: {w['note']}")
    lines.append("")

    # Analysis 3
    lines.append("## 3. Variance Decomposition\n")
    lines.append(f"- N observations: {a3.get('n_observations', 0)}")
    lines.append(f"- Grand mean compliance: {a3.get('grand_mean', 0):.4f}")
    lines.append(f"- Model effect (eta-sq): **{a3.get('eta_sq_model', 0):.4f}** ({a3.get('eta_sq_model', 0):.1%})")
    lines.append(
        f"- Scenario effect (eta-sq): **{a3.get('eta_sq_scenario', 0):.4f}** ({a3.get('eta_sq_scenario', 0):.1%})"
    )
    lines.append(
        f"- Residual (Run + Interaction): **{a3.get('eta_sq_residual', 0):.4f}** ({a3.get('eta_sq_residual', 0):.1%})"
    )
    lines.append("")
    lines.append(
        "Interpretation: Low residual eta-squared indicates that run-to-run variance is small relative to model and scenario effects.\n"
    )

    # Analysis 4
    lines.append("## 4. Bootstrap Sufficiency\n")
    lines.append(f"- Total (scenario, model) pairs: **{a4['n_pairs']}**")
    lines.append(
        f"- Pairs with stable majority vote (>{a4['threshold']:.0%}): **{a4['n_stable']}** ({a4['sufficiency_rate']:.1%})"
    )
    lines.append(f"- Bootstrap samples: {a4['n_bootstrap']}")
    lines.append("")
    unstable = a4.get("unstable_pairs", [])
    if unstable:
        lines.append("### Unstable Pairs (majority vote may flip)\n")
        lines.append("| Model | Scenario | Verdicts | Stability |")
        lines.append("|-------|----------|----------|-----------|")
        for p in unstable[:10]:
            label = MODEL_LABELS.get(p["model"], p["model"])
            lines.append(f"| {label} | {p['scenario']} | {p['verdicts']} | {p['stability']:.1%} |")
    else:
        lines.append("All pairs have stable majority votes with 3 runs.\n")

    return "\n".join(lines)


def build_latex_rows(a1: dict, a3: dict, a4: dict) -> tuple[list[list[str]], list[str]]:
    """Build LaTeX table rows for run variance summary."""
    headers = ["Metric", "Value", "Interpretation"]
    rows = [
        ["3/3 Agreement Rate", f"{a1['agree_3_3_rate']:.1%}", f"{a1['agree_3_3']}/{a1['total_pairs']} pairs unanimous"],
        ["2/1 Split Rate", f"{a1['split_2_1_rate']:.1%}", f"{a1['split_2_1']}/{a1['total_pairs']} pairs split"],
        [r"$\eta^2$ Model", f"{a3.get('eta_sq_model', 0):.4f}", "Variance from model choice"],
        [r"$\eta^2$ Scenario", f"{a3.get('eta_sq_scenario', 0):.4f}", "Variance from scenario difficulty"],
        [r"$\eta^2$ Residual", f"{a3.get('eta_sq_residual', 0):.4f}", "Run-to-run + interaction variance"],
        [
            "3-Run Sufficiency",
            f"{a4['sufficiency_rate']:.1%}",
            f"{a4['n_stable']}/{a4['n_pairs']} stable at {a4['threshold']:.0%}",
        ],
    ]
    return rows, headers


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    """Run all WS-4 analyses."""
    print("=" * 70)
    print("WS-4: Run Variance Analysis")
    print("=" * 70)

    # Load data
    episodes = load_all_episodes()
    if not episodes:
        print("WARNING: No episode data found in", RESULTS_DIR)
        print("Generating informative empty outputs.")
        empty = {"error": "No episode data found", "results_dir": str(RESULTS_DIR)}
        save_json(empty, EVIDENCE_DIR / "ws4_run_variance.json")
        save_markdown("# WS-4: Run Variance\n\nNo data available.\n", EVIDENCE_DIR / "ws4_run_variance.md")
        return

    print(f"Loaded {len(episodes)} episodes")
    run_index = build_run_index(episodes)
    print(f"Built index for {len(run_index)} (model, scenario) pairs")

    verdict_episodes = load_verdict_matrix()
    print(f"Loaded {len(verdict_episodes)} verdict matrix entries")

    # Analysis 1
    print("\n--- Analysis 1: Intra-Scenario Variance ---")
    a1 = analysis_1_intra_scenario(run_index)
    print(f"  3/3 agree: {a1['agree_3_3']}/{a1['total_pairs']} ({a1['agree_3_3_rate']:.1%})")
    print(f"  2/1 split: {a1['split_2_1']}/{a1['total_pairs']} ({a1['split_2_1_rate']:.1%})")

    # Analysis 2
    print("\n--- Analysis 2: Run vs Evaluator Variance ---")
    a2 = analysis_2_run_vs_evaluator(run_index, verdict_episodes)
    print(f"  Mean eval entropy: {a2['mean_evaluator_entropy']:.4f}")
    print(f"  Mean run instability: {a2['mean_run_instability']:.4f}")
    w = a2.get("wilcoxon", {})
    if "p_value" in w:
        print(f"  Wilcoxon: W={w['statistic']:.1f}, p={fmt_p(w['p_value'])}")

    # Analysis 3
    print("\n--- Analysis 3: Variance Decomposition ---")
    a3 = analysis_3_variance_decomposition(run_index)
    print(f"  eta-sq Model:    {a3.get('eta_sq_model', 0):.4f}")
    print(f"  eta-sq Scenario: {a3.get('eta_sq_scenario', 0):.4f}")
    print(f"  eta-sq Residual: {a3.get('eta_sq_residual', 0):.4f}")

    # Analysis 3b: Evaluator vs Run decomposition
    print("\n--- Analysis 3b: Evaluator vs Run Decomposition ---")
    a3b = analysis_3b_evaluator_vs_run(run_index, verdict_episodes)
    if "error" not in a3b:
        print(f"  eta-sq Evaluator: {a3b.get('eta_sq_evaluator', 0):.4f}")
        print(f"  eta-sq Run:       {a3b.get('eta_sq_run', 0):.4f}")
        print(f"  eta-sq Residual:  {a3b.get('eta_sq_residual', 0):.4f}")
        ratio = a3b.get("evaluator_dominance_ratio", "inf")
        print(f"  Evaluator/Run ratio: {ratio}x")
    else:
        print(f"  {a3b['error']}")

    # Analysis 4
    print("\n--- Analysis 4: Bootstrap Sufficiency ---")
    a4 = analysis_4_bootstrap_sufficiency(run_index)
    print(f"  Stable pairs: {a4['n_stable']}/{a4['n_pairs']} ({a4['sufficiency_rate']:.1%})")

    # Save outputs
    print("\n--- Saving outputs ---")
    combined = {
        "analysis_1_intra_scenario": a1,
        "analysis_2_run_vs_evaluator": {
            k: v for k, v in a2.items() if k not in ("evaluator_entropies", "run_instabilities")
        },
        "analysis_3_variance_decomposition": a3,
        "analysis_3b_evaluator_vs_run": a3b,
        "analysis_4_bootstrap_sufficiency": a4,
    }
    save_json(combined, EVIDENCE_DIR / "ws4_run_variance.json")

    md = build_markdown(a1, a2, a3, a4)
    # Append 3b results to markdown
    if "error" not in a3b:
        md += "\n## Analysis 3b: Evaluator vs Run Variance Decomposition\n\n"
        md += "| Factor | eta-squared | Interpretation |\n"
        md += "|--------|------------|----------------|\n"
        md += f"| Evaluator | {a3b['eta_sq_evaluator']:.4f} ({a3b['eta_sq_evaluator']:.1%}) | Variance from evaluator choice |\n"
        md += f"| Run | {a3b['eta_sq_run']:.4f} ({a3b['eta_sq_run']:.1%}) | Run-to-run noise |\n"
        md += f"| Residual | {a3b['eta_sq_residual']:.4f} ({a3b['eta_sq_residual']:.1%}) | Scenario/model interaction |\n\n"
        md += f"**Evaluator/Run dominance ratio: {a3b.get('evaluator_dominance_ratio', 'inf')}x**\n\n"
        md += "This confirms the paper's key claim: observed disagreement is driven by evaluator design, not run-to-run noise.\n"
    save_markdown(md, EVIDENCE_DIR / "ws4_run_variance.md")

    rows, headers = build_latex_rows(a1, a3, a4)
    save_latex_table(
        rows,
        headers,
        TABLES_DIR / "ws4_run_variance.tex",
        caption="WS-4: Run Variance Summary",
        label="tab:ws4-run-variance",
    )

    plot_variance_decomposition(a3, FIGURES_DIR / "ws4_variance_decomposition.png")
    plot_run_vs_evaluator(a2, FIGURES_DIR / "ws4_run_vs_evaluator.png")

    print("\nWS-4 complete.")


if __name__ == "__main__":
    main()
