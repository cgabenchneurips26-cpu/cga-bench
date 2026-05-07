
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""v3_p8_core_vs_expansion.py

Stratified analysis comparing Core scenarios vs Expansion scenarios in CGA-Bench.

Core (original 6 CPG domains): Sepsis, ChestPain, Stroke, HeartFailure, AKI, DKA
Expansion (Phase 7, 7 domains): AF, CAP, COPD, GIBleed, HTNEmergency, ContrastAKI, PE

A known finding is that Friedman significance comes primarily from expansion scenarios.
This script quantifies that split transparently.

Outputs:
  evidence_pack/analysis/v3_core_vs_expansion.json
  evidence_pack/analysis/v3_core_vs_expansion.md
  evidence_pack/tables/core_vs_expansion.tex

Run: PYTHONPATH=. python scripts/experiments/v3_p8_core_vs_expansion.py
"""

from __future__ import annotations

from collections import defaultdict
import json
import math
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats
import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
RESCORED_DIR = ROOT / "results" / "clean_slate_rescored"
SCENARIOS_DIR = ROOT / "configs" / "scenarios"
ANALYSIS_DIR = ROOT / "evidence_pack" / "analysis"
TABLES_DIR = ROOT / "evidence_pack" / "tables"

MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]
MODEL_LABELS: dict[str, str] = {
    "oss120b": "OSS-120B",
    "qwen27b": "Qwen-27B",
    "qwen35b": "Qwen-35B",
    "qwen4b": "Qwen-4B",
}

# guideline_graph → domain label
GRAPH_TO_DOMAIN: dict[str, str] = {
    "ssc_sepsis_hour1": "Sepsis",
    "aha_chest_pain": "ChestPain",
    "aha_stroke": "Stroke",
    "aha_heart_failure": "HeartFailure",
    "kdigo_aki_full": "AKI",
    "ada_dka_management": "DKA",
    "atrial_fibrillation": "AF",
    "cap_pneumonia": "CAP",
    "copd_exacerbation": "COPD",
    "gi_bleeding": "GIBleed",
    "hypertensive_emergency": "HTNEmergency",
    "kdigo_contrast_aki": "ContrastAKI",
    "pulmonary_embolism": "PE",
    "universal_clinical_safety": "Universal",
}

# Core guidelines (original 6 founding CPG domains)
CORE_GRAPHS: frozenset[str] = frozenset(
    {
        "ssc_sepsis_hour1",
        "aha_chest_pain",
        "aha_stroke",
        "aha_heart_failure",
        "kdigo_aki_full",
        "ada_dka_management",
    }
)

# Expansion guidelines (Phase 7 additions)
EXPANSION_GRAPHS: frozenset[str] = frozenset(
    {
        "atrial_fibrillation",
        "cap_pneumonia",
        "copd_exacerbation",
        "gi_bleeding",
        "hypertensive_emergency",
        "kdigo_contrast_aki",
        "pulmonary_embolism",
    }
)

# Hard violation types: commission, timing, sequence
HARD_VIOLATION_TYPES: frozenset[str] = frozenset({"commission", "timing", "sequence"})

# C2 completion threshold
C2_COMPLETION_THRESHOLD = 0.7

# Trap scenarios: forbidden action that is also mandatory under different conditions.
# Identified by clinical review — insulin is forbidden before K+ correction but
# mandatory for DKA in general; nitrates are forbidden in RV infarct.
KNOWN_TRAP_SCENARIOS: frozenset[str] = frozenset(
    {
        "dka_hypokalemia_trap",  # insulin forbidden before K+ correction (K<3.3)
        "stemi_inferior_rv_trap",  # nitrates forbidden in RV infarct
        "septic_shock_penicillin_allergy",  # penicillin forbidden due to allergy
        "stroke_tpa_eligible",  # tPA forbidden if contraindicated
    }
)


# ---------------------------------------------------------------------------
# Data loading helpers
# ---------------------------------------------------------------------------


def load_all_episodes() -> list[dict[str, Any]]:
    """Load all rescored episode JSON files from all model subdirs."""
    episodes: list[dict[str, Any]] = []
    for model_dir in RESCORED_DIR.iterdir():
        if not model_dir.is_dir():
            continue
        model_key = model_dir.name
        if model_key not in MODELS:
            continue
        for json_file in sorted(model_dir.glob("*.json")):
            with json_file.open() as fh:
                episode = json.load(fh)
            episode["_model_key"] = model_key
            episodes.append(episode)
    return episodes


def load_scenario_metadata() -> dict[str, dict[str, Any]]:
    """Parse all scenario YAML files and return metadata keyed by scenario_id."""
    metadata: dict[str, dict[str, Any]] = {}
    for yaml_file in SCENARIOS_DIR.glob("*.yaml"):
        with yaml_file.open() as fh:
            doc = yaml.safe_load(fh)
        if not doc or "scenarios" not in doc:
            continue
        for sid, cfg in doc["scenarios"].items():
            if not isinstance(cfg, dict):
                continue
            graph = cfg.get("guideline_graph", "unknown")
            forbidden: list[str] = []
            if "forbidden_actions" in cfg:
                fa = cfg["forbidden_actions"]
                if isinstance(fa, list):
                    forbidden = fa
                elif isinstance(fa, dict):
                    # forbidden_actions may be nested {action: reason}
                    forbidden = list(fa.keys())
            metadata[sid] = {
                "scenario_id": sid,
                "guideline_graph": graph,
                "domain": GRAPH_TO_DOMAIN.get(graph, graph),
                "forbidden_actions": forbidden,
                "expected_actions": cfg.get("expected_actions", []),
            }
    return metadata


def classify_scenario(scenario_id: str, meta: dict[str, Any]) -> str:
    """Return 'core', 'expansion', or 'other'."""
    graph = meta.get("guideline_graph", "unknown")
    if graph in CORE_GRAPHS:
        return "core"
    if graph in EXPANSION_GRAPHS:
        return "expansion"
    return "other"


def is_trap(scenario_id: str, meta: dict[str, Any]) -> bool:
    """Return True if scenario is a known trap (mandatory-yet-conditional forbidden)."""
    if scenario_id in KNOWN_TRAP_SCENARIOS:
        return True
    # Heuristic: has forbidden_actions AND expected_actions share at least one action_id root
    forbidden = set(meta.get("forbidden_actions", []))
    expected = set(meta.get("expected_actions", []))
    if forbidden and expected:
        # Check overlap (same root verb/noun)
        for f in forbidden:
            f_root = f.split("_")[0]
            for e in expected:
                e_root = e.split("_")[0]
                if f_root == e_root and len(f_root) > 3:
                    return True
    return False


# ---------------------------------------------------------------------------
# Statistical helpers
# ---------------------------------------------------------------------------


def mean_std(values: list[float]) -> tuple[float, float]:
    if not values:
        return 0.0, 0.0
    arr = np.array(values, dtype=float)
    return float(arr.mean()), float(arr.std(ddof=1) if len(arr) > 1 else 0.0)


def friedman_test(
    scenario_means: dict[str, dict[str, float]],
) -> dict[str, float]:
    """Run Friedman test over scenarios x models.

    scenario_means: {scenario_id: {model_key: mean_cga}}
    Returns: {chi2, p_value, n_scenarios, n_models, df}
    """
    # Only scenarios present for ALL models
    all_models = MODELS
    valid_scenarios = [sid for sid, model_map in scenario_means.items() if all(m in model_map for m in all_models)]
    if len(valid_scenarios) < 3:
        return {
            "chi2": float("nan"),
            "p_value": float("nan"),
            "n_scenarios": len(valid_scenarios),
            "n_models": len(all_models),
            "df": len(all_models) - 1,
            "note": f"insufficient scenarios ({len(valid_scenarios)} < 3)",
        }

    # Build matrix: rows=scenarios, cols=models
    matrix = np.array(
        [[scenario_means[sid].get(m, float("nan")) for m in all_models] for sid in valid_scenarios],
        dtype=float,
    )
    # Drop rows with any NaN
    valid_rows = ~np.isnan(matrix).any(axis=1)
    matrix = matrix[valid_rows]
    valid_count = int(matrix.shape[0])

    if valid_count < 3:
        return {
            "chi2": float("nan"),
            "p_value": float("nan"),
            "n_scenarios": valid_count,
            "n_models": len(all_models),
            "df": len(all_models) - 1,
            "note": f"too few complete rows ({valid_count})",
        }

    chi2, p_value = stats.friedmanchisquare(*[matrix[:, j] for j in range(matrix.shape[1])])
    return {
        "chi2": float(chi2),
        "p_value": float(p_value),
        "n_scenarios": valid_count,
        "n_models": len(all_models),
        "df": len(all_models) - 1,
        "note": "ok",
    }


def model_ranks(mean_cga_by_model: dict[str, float]) -> dict[str, int]:
    """Rank models by mean CGA (1 = highest)."""
    sorted_models = sorted(mean_cga_by_model, key=lambda m: mean_cga_by_model[m], reverse=True)
    return {m: rank + 1 for rank, m in enumerate(sorted_models)}


def kendall_tau(ranks_a: dict[str, int], ranks_b: dict[str, int]) -> float:
    """Compute Kendall's tau between two model rank dicts."""
    common = sorted(set(ranks_a) & set(ranks_b))
    if len(common) < 2:
        return float("nan")
    x = [ranks_a[m] for m in common]
    y = [ranks_b[m] for m in common]
    tau, _ = stats.kendalltau(x, y)
    return float(tau)


# ---------------------------------------------------------------------------
# Per-subset analysis
# ---------------------------------------------------------------------------


def analyze_subset(
    episodes: list[dict[str, Any]],
    label: str,
) -> dict[str, Any]:
    """Compute statistics for a subset of episodes.

    Returns a structured dict with aggregate and per-model breakdowns.
    """
    n_episodes = len(episodes)
    n_scenarios = len({ep["scenario_id"] for ep in episodes})

    # Per-model CGA scores
    model_cga: dict[str, list[float]] = defaultdict(list)
    # Per-model sub-scores
    model_sub: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    # Per-model violation counts
    model_violations: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    # Completion passing: C2 >= threshold
    model_completion_passing: dict[str, int] = defaultdict(int)
    # Hard violation episodes
    model_hard_viol: dict[str, int] = defaultdict(int)
    # UP_STRONG: hard violation AND completion passing
    model_up_strong: dict[str, int] = defaultdict(int)

    all_cga: list[float] = []
    total_violations_by_type: dict[str, int] = defaultdict(int)
    completion_passing_total = 0
    hard_viol_total = 0
    up_strong_total = 0

    # Scenario-level means for Friedman
    scenario_model_scores: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))

    for ep in episodes:
        model_key = ep["_model_key"]
        cga = ep.get("new_compliance_score", 0.0)
        sub_scores = ep.get("new_sub_scores", {})
        viol_by_type = ep.get("new_violations_by_type", {})
        c2 = sub_scores.get("C2_mandatory_completion", 0.0)
        sid = ep["scenario_id"]

        model_cga[model_key].append(cga)
        all_cga.append(cga)
        scenario_model_scores[sid][model_key].append(cga)

        for sub_key, sub_val in sub_scores.items():
            if isinstance(sub_val, (int, float)):
                model_sub[model_key][sub_key].append(float(sub_val))

        for vtype, count in viol_by_type.items():
            model_violations[model_key][vtype] += count
            total_violations_by_type[vtype] += count

        is_completion_passing = c2 >= C2_COMPLETION_THRESHOLD
        has_hard_viol = any(viol_by_type.get(vt, 0) > 0 for vt in HARD_VIOLATION_TYPES)

        if is_completion_passing:
            model_completion_passing[model_key] += 1
            completion_passing_total += 1
        if has_hard_viol:
            model_hard_viol[model_key] += 1
            hard_viol_total += 1
        if is_completion_passing and has_hard_viol:
            model_up_strong[model_key] += 1
            up_strong_total += 1

    # Friedman: use per-scenario mean CGA per model
    scenario_means: dict[str, dict[str, float]] = {
        sid: {m: float(np.mean(scores)) for m, scores in model_map.items()}
        for sid, model_map in scenario_model_scores.items()
    }
    friedman_result = friedman_test(scenario_means)

    # Model-level summary
    per_model: dict[str, dict[str, Any]] = {}
    for m in MODELS:
        cga_vals = model_cga.get(m, [])
        mu, sigma = mean_std(cga_vals)
        n_m = len(cga_vals)
        cp = model_completion_passing.get(m, 0)
        hv = model_hard_viol.get(m, 0)
        ups = model_up_strong.get(m, 0)
        per_model[m] = {
            "label": MODEL_LABELS[m],
            "n_episodes": n_m,
            "mean_cga": round(mu, 4),
            "std_cga": round(sigma, 4),
            "completion_passing": cp,
            "completion_passing_rate": round(cp / n_m, 4) if n_m else 0.0,
            "hard_violation_episodes": hv,
            "hard_violation_rate": round(hv / n_m, 4) if n_m else 0.0,
            "up_strong": ups,
            "up_strong_rate": round(ups / cp, 4) if cp else 0.0,
            "violations_by_type": dict(model_violations.get(m, {})),
            "sub_score_means": {k: round(float(np.mean(v)), 4) for k, v in model_sub.get(m, {}).items() if v},
        }

    global_mean, global_std = mean_std(all_cga)
    mean_by_model = {m: per_model[m]["mean_cga"] for m in MODELS if per_model[m]["n_episodes"] > 0}
    ranks = model_ranks(mean_by_model)

    return {
        "label": label,
        "n_episodes": n_episodes,
        "n_scenarios": n_scenarios,
        "mean_cga": round(global_mean, 4),
        "std_cga": round(global_std, 4),
        "completion_passing_total": completion_passing_total,
        "completion_passing_rate": round(completion_passing_total / n_episodes, 4) if n_episodes else 0.0,
        "hard_violation_total": hard_viol_total,
        "hard_violation_rate": round(hard_viol_total / n_episodes, 4) if n_episodes else 0.0,
        "up_strong_total": up_strong_total,
        "up_strong_rate": round(up_strong_total / completion_passing_total, 4) if completion_passing_total else 0.0,
        "violations_by_type": dict(total_violations_by_type),
        "friedman": friedman_result,
        "model_rankings": ranks,
        "per_model": per_model,
    }


# ---------------------------------------------------------------------------
# Mis-certification narrative
# ---------------------------------------------------------------------------


def find_miscertification_in_core(
    core_episodes: list[dict[str, Any]],
    scenario_meta: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Find episodes that are completion-passing but have hard violations (mis-certified)."""
    mis: list[dict[str, Any]] = []
    for ep in core_episodes:
        sub_scores = ep.get("new_sub_scores", {})
        viol_by_type = ep.get("new_violations_by_type", {})
        c2 = sub_scores.get("C2_mandatory_completion", 0.0)
        has_hard = any(viol_by_type.get(vt, 0) > 0 for vt in HARD_VIOLATION_TYPES)
        if c2 >= C2_COMPLETION_THRESHOLD and has_hard:
            sid = ep["scenario_id"]
            hard_types = [vt for vt in HARD_VIOLATION_TYPES if viol_by_type.get(vt, 0) > 0]
            mis.append(
                {
                    "scenario_id": sid,
                    "domain": scenario_meta.get(sid, {}).get("domain", "unknown"),
                    "model": MODEL_LABELS.get(ep["_model_key"], ep["_model_key"]),
                    "run_index": ep.get("run_index", -1),
                    "cga": round(ep.get("new_compliance_score", 0.0), 4),
                    "c2": round(c2, 4),
                    "hard_violation_types": hard_types,
                    "total_violations": ep.get("new_total_violations", 0),
                    "is_trap": is_trap(sid, scenario_meta.get(sid, {})),
                }
            )
    return mis


# ---------------------------------------------------------------------------
# Output formatting
# ---------------------------------------------------------------------------


def _pval_str(p: float) -> str:
    if math.isnan(p):
        return "N/A"
    if p < 0.001:
        return "<0.001"
    return f"{p:.3f}"


def _sig_stars(p: float) -> str:
    if math.isnan(p):
        return ""
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    if p < 0.10:
        return "†"
    return "ns"


def format_markdown(
    results: dict[str, Any],
    scenario_table: list[dict[str, Any]],
    miscertification: list[dict[str, Any]],
    rank_stability: dict[str, Any],
) -> str:
    lines: list[str] = []

    lines.append("# Core vs Expansion Stratification Analysis")
    lines.append("")
    lines.append(
        "CGA-Bench has 15 scenarios across 13 clinical domains. "
        "This analysis separates the original 6 **core** domains from the 7 **expansion** domains "
        "added in Phase 7, and quantifies how each subset contributes to statistical power."
    )
    lines.append("")

    # --- Scenario classification table ---
    lines.append("## 1. Scenario Classification")
    lines.append("")
    lines.append("| Scenario ID | Domain | Graph | Subset | Trap |")
    lines.append("|---|---|---|---|---|")
    for row in scenario_table:
        trap_str = "YES" if row["is_trap"] else "no"
        lines.append(f"| {row['scenario_id']} | {row['domain']} | {row['graph']} | **{row['subset']}** | {trap_str} |")
    lines.append("")

    # --- Per-subset statistics ---
    lines.append("## 2. Per-Subset Statistics")
    lines.append("")
    for subset_key in ("core", "expansion", "all"):
        s = results[subset_key]
        lines.append(f"### {s['label']}")
        lines.append("")
        lines.append(f"- **Episodes**: {s['n_episodes']}  |  **Scenarios**: {s['n_scenarios']}")
        lines.append(f"- **Mean CGA**: {s['mean_cga']:.3f} ± {s['std_cga']:.3f}")
        lines.append(
            f"- **Completion-passing** (C2 ≥ 0.7): "
            f"{s['completion_passing_total']} / {s['n_episodes']} "
            f"({s['completion_passing_rate'] * 100:.1f}%)"
        )
        lines.append(
            f"- **Any hard violation** (commission/timing/sequence): "
            f"{s['hard_violation_total']} / {s['n_episodes']} "
            f"({s['hard_violation_rate'] * 100:.1f}%)"
        )
        lines.append(
            f"- **UP_STRONG** (completion-passing + hard violation): "
            f"{s['up_strong_total']} / {s['completion_passing_total']} "
            f"({s['up_strong_rate'] * 100:.1f}% of completion-passing)"
        )
        lines.append("")

        # Per-model table
        lines.append("| Model | N | Mean CGA | Completion-pass | UP_STRONG | Rank |")
        lines.append("|---|---|---|---|---|---|")
        for m in MODELS:
            pm = s["per_model"][m]
            rank = s["model_rankings"].get(m, "-")
            ups = pm["up_strong"]
            cp = pm["completion_passing"]
            ups_str = f"{ups}/{cp} ({pm['up_strong_rate'] * 100:.0f}%)" if cp else "0/0"
            lines.append(
                f"| {pm['label']} | {pm['n_episodes']} "
                f"| {pm['mean_cga']:.3f} ± {pm['std_cga']:.3f} "
                f"| {pm['completion_passing']}/{pm['n_episodes']} "
                f"({pm['completion_passing_rate'] * 100:.0f}%) "
                f"| {ups_str} | #{rank} |"
            )
        lines.append("")

        # Violation breakdown
        vbt = s["violations_by_type"]
        total_v = sum(vbt.values()) or 1
        vtype_parts = [
            f"{vt}: {vbt.get(vt, 0)} ({vbt.get(vt, 0) / total_v * 100:.0f}%)"
            for vt in ["omission", "commission", "timing", "sequence", "deviation"]
            if vbt.get(vt, 0) > 0
        ]
        lines.append(f"- **Violation breakdown**: {', '.join(vtype_parts)}")
        lines.append("")

    # --- Friedman results ---
    lines.append("## 3. Friedman Test per Subset")
    lines.append("")
    lines.append("| Subset | N scenarios | chi² | p-value | Significance |")
    lines.append("|---|---|---|---|---|")
    for subset_key in ("core", "expansion", "all"):
        s = results[subset_key]
        fr = s["friedman"]
        chi2_str = f"{fr['chi2']:.3f}" if not math.isnan(fr["chi2"]) else "N/A"
        p_str = _pval_str(fr["p_value"])
        sig = _sig_stars(fr["p_value"])
        lines.append(f"| {s['label']} | {fr['n_scenarios']} | {chi2_str} | {p_str} | {sig} |")
    lines.append("")
    lines.append("Significance: *** p<0.001, ** p<0.01, * p<0.05, † p<0.10, ns not significant")
    lines.append("")

    # --- Rank stability ---
    lines.append("## 4. Model Ranking Stability")
    lines.append("")
    lines.append("| Model | Core rank | Expansion rank | All-15 rank |")
    lines.append("|---|---|---|---|")
    for m in MODELS:
        r_core = results["core"]["model_rankings"].get(m, "-")
        r_exp = results["expansion"]["model_rankings"].get(m, "-")
        r_all = results["all"]["model_rankings"].get(m, "-")
        lines.append(f"| {MODEL_LABELS[m]} | #{r_core} | #{r_exp} | #{r_all} |")
    lines.append("")
    tau_core_exp = rank_stability.get("kendall_tau_core_vs_expansion", float("nan"))
    tau_core_all = rank_stability.get("kendall_tau_core_vs_all", float("nan"))
    tau_exp_all = rank_stability.get("kendall_tau_expansion_vs_all", float("nan"))
    lines.append(
        f"- Kendall's τ (core vs expansion): **{tau_core_exp:.3f}**"
        if not math.isnan(tau_core_exp)
        else "- Kendall's τ (core vs expansion): N/A"
    )
    lines.append(
        f"- Kendall's τ (core vs all): **{tau_core_all:.3f}**"
        if not math.isnan(tau_core_all)
        else "- Kendall's τ (core vs all): N/A"
    )
    lines.append(
        f"- Kendall's τ (expansion vs all): **{tau_exp_all:.3f}**"
        if not math.isnan(tau_exp_all)
        else "- Kendall's τ (expansion vs all): N/A"
    )
    lines.append("")

    # --- Narrative claims ---
    lines.append("## 5. Key Narrative Claims")
    lines.append("")
    core = results["core"]
    exp = results["expansion"]
    all_s = results["all"]
    fr_core = core["friedman"]
    fr_exp = exp["friedman"]
    fr_all = all_s["friedman"]

    core_ups_pct = core["up_strong_rate"] * 100
    exp_ups_pct = exp["up_strong_rate"] * 100
    all_ups_pct = all_s["up_strong_rate"] * 100

    lines.append(
        f"> Core scenarios alone show **{core_ups_pct:.0f}%** unsafe-pass rate "
        f"(UP_STRONG among completion-passing) but Friedman p={_pval_str(fr_core['p_value'])} "
        f"({_sig_stars(fr_core['p_value'])})."
    )
    lines.append("")
    lines.append(
        f"> Expansion scenarios show **{exp_ups_pct:.0f}%** unsafe-pass rate "
        f"and add statistical power: Friedman p={_pval_str(fr_exp['p_value'])} "
        f"({_sig_stars(fr_exp['p_value'])})."
    )
    lines.append("")

    tau = rank_stability.get("kendall_tau_core_vs_expansion", float("nan"))
    if not math.isnan(tau) and tau >= 0.8:
        lines.append(
            f"> Expansion adds statistical power (Friedman p={_pval_str(fr_exp['p_value'])}) "
            f"without changing rank order (Kendall's τ = {tau:.3f} ≈ perfect concordance)."
        )
    elif not math.isnan(tau):
        lines.append(
            f"> Expansion reveals model-specific weaknesses: rank concordance "
            f"Kendall's τ = {tau:.3f} between core and expansion subsets."
        )
    lines.append("")
    lines.append(
        f"> Full 15-scenario benchmark: mean CGA = {all_s['mean_cga']:.3f} ± {all_s['std_cga']:.3f}, "
        f"UP_STRONG = {all_ups_pct:.0f}% of completion-passing episodes, "
        f"Friedman p={_pval_str(fr_all['p_value'])} ({_sig_stars(fr_all['p_value'])})."
    )
    lines.append("")

    # --- Mis-certification in core ---
    lines.append("## 6. Mis-certification in Core Scenarios")
    lines.append("")
    lines.append("Even if core-only Friedman is non-significant, unsafe-pass episodes exist:")
    lines.append("")
    if miscertification:
        lines.append("| Scenario | Domain | Model | Run | CGA | C2 | Hard violation types | Trap |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for mc in miscertification:
            trap_str = "YES" if mc["is_trap"] else "no"
            lines.append(
                f"| {mc['scenario_id']} | {mc['domain']} | {mc['model']} "
                f"| r{mc['run_index']} | {mc['cga']:.3f} | {mc['c2']:.2f} "
                f"| {', '.join(mc['hard_violation_types'])} | {trap_str} |"
            )
        lines.append("")
        lines.append(
            f"**{len(miscertification)} mis-certified episodes** in core scenarios: "
            "completion-passing (C2 ≥ 0.7) yet containing hard violations. "
            "Expansion provides the sample size for Friedman significance; "
            "the safety gap exists in both subsets."
        )
    else:
        lines.append("No mis-certified episodes found in core scenarios under current scoring.")
    lines.append("")

    return "\n".join(lines)


def format_latex(
    results: dict[str, Any],
    scenario_table: list[dict[str, Any]],
) -> str:
    """Generate LaTeX table for paper inclusion."""
    lines: list[str] = []
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"\centering")
    lines.append(r"\caption{Core vs Expansion Stratification}")
    lines.append(r"\label{tab:core_vs_expansion}")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{lcccccc}")
    lines.append(r"\hline")
    lines.append(
        r"\textbf{Subset} & \textbf{Scenarios} & \textbf{Episodes} "
        r"& \textbf{Mean CGA} & \textbf{UP-STRONG} "
        r"& \textbf{Friedman $\chi^2$} & \textbf{$p$-value} \\"
    )
    lines.append(r"\hline")

    for subset_key in ("core", "expansion", "all"):
        s = results[subset_key]
        fr = s["friedman"]
        chi2_str = f"{fr['chi2']:.2f}" if not math.isnan(fr["chi2"]) else "---"
        p_str = _pval_str(fr["p_value"])
        sig = _sig_stars(fr["p_value"])
        if sig and sig != "ns":
            p_display = f"{p_str}$^{{{sig}}}$"
        else:
            p_display = p_str
        ups_pct = s["up_strong_rate"] * 100
        lines.append(
            f"{s['label']} & {s['n_scenarios']} & {s['n_episodes']} "
            f"& ${s['mean_cga']:.3f} \\pm {s['std_cga']:.3f}$ "
            f"& {ups_pct:.0f}\\% "
            f"& {chi2_str} & {p_display} \\\\"
        )

    lines.append(r"\hline")
    lines.append(r"\end{tabular}")
    lines.append(r"\vspace{0.5em}")
    lines.append(r"\begin{minipage}{\linewidth}")
    lines.append(
        r"\footnotesize UP-STRONG: completion-passing (C2 $\geq$ 0.7) episodes with at "
        r"least one hard violation (commission/timing/sequence). "
        r"$^{*}p<0.05$, $^{**}p<0.01$, $^{***}p<0.001$, $^{\dagger}p<0.10$."
    )
    lines.append(r"\end{minipage}")
    lines.append(r"\end{table}")
    lines.append("")

    # Per-model breakdown table
    lines.append(r"\begin{table}[htbp]")
    lines.append(r"\centering")
    lines.append(r"\caption{Model Rankings: Core vs Expansion}")
    lines.append(r"\label{tab:core_vs_expansion_ranks}")
    lines.append(r"\small")
    lines.append(r"\begin{tabular}{lcccccc}")
    lines.append(r"\hline")
    lines.append(
        r"\textbf{Model} & \multicolumn{2}{c}{\textbf{Core}} "
        r"& \multicolumn{2}{c}{\textbf{Expansion}} "
        r"& \multicolumn{2}{c}{\textbf{All-15}} \\"
    )
    lines.append(r" & Mean CGA & Rank & Mean CGA & Rank & Mean CGA & Rank \\")
    lines.append(r"\hline")
    for m in MODELS:
        label = MODEL_LABELS[m]
        c_pm = results["core"]["per_model"][m]
        e_pm = results["expansion"]["per_model"][m]
        a_pm = results["all"]["per_model"][m]
        r_c = results["core"]["model_rankings"].get(m, "-")
        r_e = results["expansion"]["model_rankings"].get(m, "-")
        r_a = results["all"]["model_rankings"].get(m, "-")
        lines.append(
            f"{label} & ${c_pm['mean_cga']:.3f}$ & \\#{r_c} "
            f"& ${e_pm['mean_cga']:.3f}$ & \\#{r_e} "
            f"& ${a_pm['mean_cga']:.3f}$ & \\#{r_a} \\\\"
        )
    lines.append(r"\hline")
    lines.append(r"\end{tabular}")
    lines.append(r"\end{table}")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("Loading episodes...")
    episodes = load_all_episodes()
    print(f"  Loaded {len(episodes)} episodes")

    print("Loading scenario metadata...")
    scenario_meta = load_scenario_metadata()
    print(f"  Loaded {len(scenario_meta)} scenario configs")

    # Build scenario classification table (only for the 15 in rescored data)
    seen_scenarios: set[str] = {ep["scenario_id"] for ep in episodes}
    scenario_table: list[dict[str, Any]] = []
    for sid in sorted(seen_scenarios):
        meta = scenario_meta.get(sid, {})
        graph = meta.get("guideline_graph", "unknown")
        domain = meta.get("domain", GRAPH_TO_DOMAIN.get(graph, graph))
        subset = classify_scenario(sid, meta)
        trap = is_trap(sid, meta)
        scenario_table.append(
            {
                "scenario_id": sid,
                "domain": domain,
                "graph": graph,
                "subset": subset,
                "is_trap": trap,
            }
        )

    print("\nScenario classification:")
    core_ids = {r["scenario_id"] for r in scenario_table if r["subset"] == "core"}
    expansion_ids = {r["scenario_id"] for r in scenario_table if r["subset"] == "expansion"}
    other_ids = {r["scenario_id"] for r in scenario_table if r["subset"] == "other"}
    for row in scenario_table:
        print(f"  {row['scenario_id']:<40} {row['subset']:<10} trap={row['is_trap']} domain={row['domain']}")

    # Split episodes by subset
    core_episodes = [ep for ep in episodes if ep["scenario_id"] in core_ids]
    expansion_episodes = [ep for ep in episodes if ep["scenario_id"] in expansion_ids]
    all_episodes = episodes  # includes 'other' if any

    print(f"\nEpisode split: core={len(core_episodes)}, expansion={len(expansion_episodes)}, total={len(all_episodes)}")

    # Analyze each subset
    print("\nAnalyzing subsets...")
    results: dict[str, Any] = {
        "core": analyze_subset(core_episodes, "Core"),
        "expansion": analyze_subset(expansion_episodes, "Expansion"),
        "all": analyze_subset(all_episodes, "All-15"),
    }

    # Rank stability
    ranks_core = results["core"]["model_rankings"]
    ranks_exp = results["expansion"]["model_rankings"]
    ranks_all = results["all"]["model_rankings"]
    rank_stability: dict[str, Any] = {
        "core_ranks": ranks_core,
        "expansion_ranks": ranks_exp,
        "all_ranks": ranks_all,
        "kendall_tau_core_vs_expansion": kendall_tau(ranks_core, ranks_exp),
        "kendall_tau_core_vs_all": kendall_tau(ranks_core, ranks_all),
        "kendall_tau_expansion_vs_all": kendall_tau(ranks_exp, ranks_all),
    }

    # Mis-certification in core
    miscertification = find_miscertification_in_core(core_episodes, scenario_meta)

    # Print key results
    print("\n--- Friedman Results ---")
    for subset_key in ("core", "expansion", "all"):
        s = results[subset_key]
        fr = s["friedman"]
        p_str = _pval_str(fr["p_value"])
        sig = _sig_stars(fr["p_value"])
        chi2_str = f"{fr['chi2']:.3f}" if not math.isnan(fr["chi2"]) else "N/A"
        print(f"  {s['label']:12s}: chi2={chi2_str}, p={p_str} {sig}  (n_scenarios={fr['n_scenarios']})")

    print("\n--- Model Rankings ---")
    for subset_key in ("core", "expansion", "all"):
        s = results[subset_key]
        ranked = sorted(s["model_rankings"], key=lambda m: s["model_rankings"][m])
        print(
            f"  {s['label']:12s}: "
            + " > ".join(f"{MODEL_LABELS[m]}({s['per_model'][m]['mean_cga']:.3f})" for m in ranked)
        )

    tau = rank_stability["kendall_tau_core_vs_expansion"]
    print(f"\n  Kendall's tau (core vs expansion): {'N/A' if math.isnan(tau) else f'{tau:.3f}'}")

    print(f"\n--- Mis-certified in Core: {len(miscertification)} episodes ---")
    if miscertification:
        for mc in miscertification[:5]:
            print(
                f"  {mc['scenario_id']} | {mc['model']} r{mc['run_index']} "
                f"| CGA={mc['cga']:.3f} C2={mc['c2']:.2f} "
                f"| {mc['hard_violation_types']}"
            )
        if len(miscertification) > 5:
            print(f"  ... and {len(miscertification) - 5} more")

    # Build full JSON output
    json_output: dict[str, Any] = {
        "metadata": {
            "script": "v3_p8_core_vs_expansion.py",
            "n_total_episodes": len(all_episodes),
            "n_core_scenarios": len(core_ids),
            "n_expansion_scenarios": len(expansion_ids),
            "models": MODELS,
            "c2_completion_threshold": C2_COMPLETION_THRESHOLD,
        },
        "scenario_classification": scenario_table,
        "subsets": {k: v for k, v in results.items()},
        "rank_stability": rank_stability,
        "miscertification_in_core": miscertification,
    }

    # Write outputs
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)
    TABLES_DIR.mkdir(parents=True, exist_ok=True)

    json_path = ANALYSIS_DIR / "v3_core_vs_expansion.json"
    json_path.write_text(json.dumps(json_output, indent=2, default=str))
    print(f"\nWrote: {json_path}")

    md_path = ANALYSIS_DIR / "v3_core_vs_expansion.md"
    md_content = format_markdown(results, scenario_table, miscertification, rank_stability)
    md_path.write_text(md_content)
    print(f"Wrote: {md_path}")

    tex_path = TABLES_DIR / "core_vs_expansion.tex"
    tex_content = format_latex(results, scenario_table)
    tex_path.write_text(tex_content)
    print(f"Wrote: {tex_path}")

    print("\nDone.")


if __name__ == "__main__":
    main()
