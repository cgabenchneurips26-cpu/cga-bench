#!/usr/bin/env python3
"""EXP-D: Evaluation Disagreement Quantification.

Quantifies evaluator disagreement across 6 evaluators to NeurIPS-proof level.
Computes pairwise and multi-rater agreement, rank reversal analysis,
effect size analysis, statistical significance tests, and disagreement taxonomy.

Outputs:
  evidence_pack/exp_d_disagreement.json
  evidence_pack/exp_d_disagreement.md
  evidence_pack/figures/exp_d_kappa_heatmap.png
  evidence_pack/figures/exp_d_rank_reversal.png
  evidence_pack/figures/exp_d_passrate_by_evaluator.png
  evidence_pack/figures/exp_d_disagreement_taxonomy.png
  evidence_pack/tables/evaluator_agreement.tex
  evidence_pack/tables/rank_reversal.tex
  evidence_pack/tables/disagreement_taxonomy.tex

Usage:
    PYTHONPATH=. python scripts/experiments/exp_d_disagreement_quantification.py
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np
from scipy import stats as sp_stats

# ---------------------------------------------------------------------------
# Reuse from existing modules
# ---------------------------------------------------------------------------
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import matplotlib
from scripts.evaluator_agreement import (
    EVALUATOR_KEYS,
    EVALUATOR_LABELS,
    cohens_kappa,
    fleiss_kappa,
    load_per_episode,
)
from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    N_BOOTSTRAP,
    RESULTS_DIR,
    SEED,
    TABLES_DIR,
    bootstrap_ci,
    fmt_f,
    fmt_p,
    save_figure,
    save_json,
    save_latex_table,
    save_markdown,
    setup_matplotlib,
)

matplotlib.use("Agg")
import matplotlib.pyplot as plt

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]
MODEL_LABELS = {"oss120b": "120B", "qwen27b": "27B", "qwen35b": "35B", "qwen4b": "4B"}
# Reverse: verdict matrix uses short labels like "120B"
LABEL_TO_DIR = {v: k for k, v in MODEL_LABELS.items()}

N_EVALUATORS = len(EVALUATOR_KEYS)


# ---------------------------------------------------------------------------
# Domain extraction
# ---------------------------------------------------------------------------
def get_domain(scenario_id: str) -> str:
    """Map scenario_id to clinical domain.

    Args:
        scenario_id: Scenario identifier string.

    Returns:
        Domain string.
    """
    prefixes = {
        "septic_shock": "sepsis",
        "stemi": "chest_pain",
        "nstemi": "chest_pain",
        "stroke": "stroke",
        "hemorrhagic_stroke": "stroke",
        "dka": "dka",
        "aki": "aki",
        "contrast_aki": "aki",
        "adhf": "heart_failure",
        "hfref": "heart_failure",
        "af_": "atrial_fibrillation",
        "cap_": "pneumonia",
        "copd_": "copd",
        "gi_": "gi_bleeding",
        "pe_": "pulmonary_embolism",
        "htn_": "hypertensive_emergency",
    }
    for prefix, domain in prefixes.items():
        if scenario_id.startswith(prefix):
            return domain
    return "other"


# ---------------------------------------------------------------------------
# Verdict extraction (with CGA-Bench inversion)
# ---------------------------------------------------------------------------
def extract_binary_verdicts(episodes: list[dict]) -> dict[str, list[int]]:
    """Extract binary pass/fail verdicts for each evaluator.

    For CGA-Bench (v4_hard), PASS = NOT v4_hard (inverted).
    For all others, PASS = True.

    Args:
        episodes: Per-episode records from verdict matrix.

    Returns:
        Dict mapping evaluator key to list of binary verdicts (1=pass, 0=fail).
    """
    verdicts: dict[str, list[int]] = {k: [] for k in EVALUATOR_KEYS}
    for ep in episodes:
        for key in EVALUATOR_KEYS:
            val = ep.get(key, False)
            if key == "v4_hard":
                # CGA-Bench: PASS = NOT v4_hard
                verdicts[key].append(1 if not val else 0)
            else:
                verdicts[key].append(1 if val else 0)
    return verdicts


# ---------------------------------------------------------------------------
# 1. Pairwise agreement
# ---------------------------------------------------------------------------
def pairwise_agreement(
    verdicts: dict[str, list[int]],
) -> list[dict[str, Any]]:
    """Compute pairwise Cohen's kappa, agreement %, and asymmetry for all pairs.

    Args:
        verdicts: Binary verdict vectors keyed by evaluator key.

    Returns:
        List of dicts with pair metrics for all C(6,2)=15 pairs.
    """
    results: list[dict[str, Any]] = []
    for (k1, lab1), (k2, lab2) in combinations(
        zip(EVALUATOR_KEYS, EVALUATOR_LABELS, strict=True), 2
    ):
        v1 = verdicts[k1]
        v2 = verdicts[k2]
        n = len(v1)

        kappa = cohens_kappa(v1, v2)
        agree_pct = (
            sum(a == b for a, b in zip(v1, v2, strict=True)) / n if n else 0.0
        )

        # Asymmetry: a=pass/b=fail vs b=pass/a=fail
        a_pass_b_fail = sum(
            1 for a, b in zip(v1, v2, strict=True) if a == 1 and b == 0
        )
        b_pass_a_fail = sum(
            1 for a, b in zip(v1, v2, strict=True) if a == 0 and b == 1
        )

        results.append({
            "evaluator_a": lab1,
            "evaluator_b": lab2,
            "key_a": k1,
            "key_b": k2,
            "kappa": round(kappa, 4),
            "agreement_pct": round(agree_pct, 4),
            "a_pass_b_fail": a_pass_b_fail,
            "b_pass_a_fail": b_pass_a_fail,
            "asymmetry": abs(a_pass_b_fail - b_pass_a_fail),
        })

    return results


# ---------------------------------------------------------------------------
# 2. Multi-evaluator agreement
# ---------------------------------------------------------------------------
def _build_rating_matrix(verdicts: dict[str, list[int]]) -> np.ndarray:
    """Build Fleiss kappa rating matrix from binary verdicts.

    Args:
        verdicts: Binary verdict vectors.

    Returns:
        N x 2 matrix (col 0 = fail count, col 1 = pass count).
    """
    n = len(next(iter(verdicts.values())))
    matrix = np.zeros((n, 2), dtype=float)
    for i in range(n):
        pass_count = sum(verdicts[k][i] for k in EVALUATOR_KEYS)
        matrix[i, 1] = pass_count
        matrix[i, 0] = N_EVALUATORS - pass_count
    return matrix


def multi_evaluator_agreement(
    episodes: list[dict],
    verdicts: dict[str, list[int]],
) -> dict[str, Any]:
    """Compute Fleiss' kappa overall, per-domain, and per-model.

    Args:
        episodes: Per-episode records.
        verdicts: Binary verdict vectors.

    Returns:
        Dict with overall, per_domain, and per_model Fleiss' kappa.
    """
    # Overall
    matrix = _build_rating_matrix(verdicts)
    overall_fk = fleiss_kappa(matrix)

    # Group indices by domain
    domain_indices: dict[str, list[int]] = defaultdict(list)
    model_indices: dict[str, list[int]] = defaultdict(list)
    for i, ep in enumerate(episodes):
        domain = get_domain(ep["scenario_id"])
        domain_indices[domain].append(i)
        model_indices[ep["model"]].append(i)

    def _fleiss_for_subset(indices: list[int]) -> float:
        """Compute Fleiss' kappa for a subset of episodes."""
        if len(indices) < 2:
            return float("nan")
        sub_matrix = matrix[indices]
        return fleiss_kappa(sub_matrix)

    per_domain = {
        d: round(_fleiss_for_subset(idx), 4)
        for d, idx in sorted(domain_indices.items())
    }
    per_model = {
        m: round(_fleiss_for_subset(idx), 4)
        for m, idx in sorted(model_indices.items())
    }

    return {
        "overall": round(overall_fk, 4),
        "per_domain": per_domain,
        "per_model": per_model,
    }


# ---------------------------------------------------------------------------
# 3. Rank reversal analysis
# ---------------------------------------------------------------------------
def rank_reversal_analysis(
    episodes: list[dict],
    verdicts: dict[str, list[int]],
) -> dict[str, Any]:
    """Analyse model ranking stability across evaluators.

    For each evaluator computes per-model pass rate, then tests rank
    concordance between all evaluator pairs via Spearman rho and Kendall tau.

    Args:
        episodes: Per-episode records.
        verdicts: Binary verdict vectors.

    Returns:
        Dict with pass_rates, rank_correlations, and rank_reversals.
    """
    models = sorted({ep["model"] for ep in episodes})

    # Per-model pass rate for each evaluator
    model_pass_rates: dict[str, dict[str, float]] = {}
    for key, label in zip(EVALUATOR_KEYS, EVALUATOR_LABELS, strict=True):
        rates: dict[str, float] = {}
        for model in models:
            model_idx = [i for i, ep in enumerate(episodes) if ep["model"] == model]
            if not model_idx:
                rates[model] = 0.0
                continue
            rates[model] = sum(verdicts[key][i] for i in model_idx) / len(model_idx)
        model_pass_rates[label] = {m: round(r, 4) for m, r in rates.items()}

    # Model ranks per evaluator (rank 1 = highest pass rate)
    model_ranks: dict[str, dict[str, int]] = {}
    for label in EVALUATOR_LABELS:
        rates = model_pass_rates[label]
        sorted_models = sorted(models, key=lambda m: -rates[m])
        model_ranks[label] = {m: rank + 1 for rank, m in enumerate(sorted_models)}

    # Rank correlation between evaluator pairs
    correlations: list[dict[str, Any]] = []
    reversals: list[dict[str, str]] = []

    for l1, l2 in combinations(EVALUATOR_LABELS, 2):
        ranks_1 = [model_ranks[l1][m] for m in models]
        ranks_2 = [model_ranks[l2][m] for m in models]

        if len(set(ranks_1)) < 2 or len(set(ranks_2)) < 2:
            # All same rank — correlation undefined
            rho, rho_p = float("nan"), 1.0
            tau, tau_p = float("nan"), 1.0
        else:
            rho, rho_p = sp_stats.spearmanr(ranks_1, ranks_2)
            tau, tau_p = sp_stats.kendalltau(ranks_1, ranks_2)

        # Count concrete rank reversals
        n_reversals = 0
        for m_a, m_b in combinations(models, 2):
            r1_a = model_ranks[l1][m_a]
            r1_b = model_ranks[l1][m_b]
            r2_a = model_ranks[l2][m_a]
            r2_b = model_ranks[l2][m_b]
            if (r1_a < r1_b and r2_a > r2_b) or (r1_a > r1_b and r2_a < r2_b):
                n_reversals += 1
                reversals.append({
                    "model_a": m_a,
                    "model_b": m_b,
                    "evaluator_x": l1,
                    "evaluator_y": l2,
                    "rank_x_a": r1_a,
                    "rank_x_b": r1_b,
                    "rank_y_a": r2_a,
                    "rank_y_b": r2_b,
                })

        correlations.append({
            "evaluator_a": l1,
            "evaluator_b": l2,
            "spearman_rho": round(float(rho), 4) if not np.isnan(rho) else None,
            "spearman_p": round(float(rho_p), 4) if not np.isnan(rho_p) else None,
            "kendall_tau": round(float(tau), 4) if not np.isnan(tau) else None,
            "kendall_p": round(float(tau_p), 4) if not np.isnan(tau_p) else None,
            "n_reversals": n_reversals,
        })

    return {
        "model_pass_rates": model_pass_rates,
        "model_ranks": model_ranks,
        "rank_correlations": correlations,
        "rank_reversals": reversals,
        "total_reversals": len(reversals),
    }


# ---------------------------------------------------------------------------
# 4. Effect size analysis
# ---------------------------------------------------------------------------
def effect_size_analysis(
    episodes: list[dict],
    verdicts: dict[str, list[int]],
) -> dict[str, Any]:
    """Quantify leniency spread across evaluators.

    Orders evaluators by overall pass rate, computes max gap between most
    lenient and most strict, and bootstraps 95% CI on the gap.

    Args:
        episodes: Per-episode records.
        verdicts: Binary verdict vectors.

    Returns:
        Dict with ordered evaluators, gaps, and bootstrap CIs.
    """
    n = len(episodes)
    models = sorted({ep["model"] for ep in episodes})

    # Overall pass rate per evaluator
    evaluator_rates: dict[str, float] = {}
    for key, label in zip(EVALUATOR_KEYS, EVALUATOR_LABELS, strict=True):
        evaluator_rates[label] = sum(verdicts[key]) / n if n else 0.0

    # Order lenient -> strict
    ordered = sorted(evaluator_rates.items(), key=lambda x: -x[1])
    most_lenient = ordered[0]
    most_strict = ordered[-1]
    max_gap = most_lenient[1] - most_strict[1]

    # Per-model gap
    per_model_gap: dict[str, dict[str, Any]] = {}
    for model in models:
        model_idx = [i for i, ep in enumerate(episodes) if ep["model"] == model]
        n_m = len(model_idx)
        if n_m == 0:
            continue
        model_rates: dict[str, float] = {}
        for key, label in zip(EVALUATOR_KEYS, EVALUATOR_LABELS, strict=True):
            model_rates[label] = (
                sum(verdicts[key][i] for i in model_idx) / n_m
            )
        model_ordered = sorted(model_rates.items(), key=lambda x: -x[1])
        gap = model_ordered[0][1] - model_ordered[-1][1]
        per_model_gap[model] = {
            "most_lenient": model_ordered[0][0],
            "most_strict": model_ordered[-1][0],
            "gap": round(gap, 4),
            "rates": {k: round(v, 4) for k, v in model_rates.items()},
        }

    # Bootstrap 95% CI on max gap
    # Build per-episode gap array: for each episode, difference between
    # most-lenient and most-strict evaluator verdicts
    lenient_key = next(
        k for k, lab in zip(EVALUATOR_KEYS, EVALUATOR_LABELS, strict=True)
        if lab == most_lenient[0]
    )
    strict_key = next(
        k for k, lab in zip(EVALUATOR_KEYS, EVALUATOR_LABELS, strict=True)
        if lab == most_strict[0]
    )
    gap_array = np.array([
        verdicts[lenient_key][i] - verdicts[strict_key][i]
        for i in range(n)
    ], dtype=float)

    ci_lo, ci_hi = bootstrap_ci(gap_array, np.mean)

    return {
        "evaluator_order": [
            {"evaluator": name, "pass_rate": round(rate, 4)}
            for name, rate in ordered
        ],
        "most_lenient": most_lenient[0],
        "most_strict": most_strict[0],
        "max_gap": round(max_gap, 4),
        "max_gap_ci_95": [round(ci_lo, 4), round(ci_hi, 4)],
        "per_model_gap": per_model_gap,
    }


# ---------------------------------------------------------------------------
# 5. Statistical tests (manual McNemar + Cochran's Q)
# ---------------------------------------------------------------------------
def _mcnemar_test(v1: list[int], v2: list[int]) -> dict[str, float]:
    """Compute McNemar's test for paired binary data.

    Builds 2x2 contingency of discordant pairs:
        b = v1=pass, v2=fail
        c = v1=fail, v2=pass
    chi2 = (b - c)^2 / (b + c), p from chi2(df=1).

    Args:
        v1: Binary verdicts from evaluator 1.
        v2: Binary verdicts from evaluator 2.

    Returns:
        Dict with b, c, chi2, p_value.
    """
    b = sum(1 for a, x in zip(v1, v2, strict=True) if a == 1 and x == 0)
    c = sum(1 for a, x in zip(v1, v2, strict=True) if a == 0 and x == 1)

    if b + c == 0:
        return {"b": b, "c": c, "chi2": 0.0, "p_value": 1.0}

    chi2 = (b - c) ** 2 / (b + c)
    p_value = float(1.0 - sp_stats.chi2.cdf(chi2, df=1))
    return {"b": b, "c": c, "chi2": round(chi2, 4), "p_value": p_value}


def _cochrans_q(verdicts: dict[str, list[int]]) -> dict[str, float]:
    """Compute Cochran's Q test for k related binary samples.

    Q = k(k-1) * sum((Cj - C_bar)^2) / (k * sum(Ri) - sum(Ri^2))
    where Cj = column sum, Ri = row sum, k = number of evaluators.
    p from chi2(df=k-1).

    Args:
        verdicts: Binary verdict vectors keyed by evaluator key.

    Returns:
        Dict with Q statistic, df, and p_value.
    """
    keys = list(EVALUATOR_KEYS)
    k = len(keys)
    n = len(verdicts[keys[0]])

    # Build matrix: n_subjects x k_evaluators
    matrix = np.zeros((n, k), dtype=float)
    for j, key in enumerate(keys):
        for i in range(n):
            matrix[i, j] = verdicts[key][i]

    # Row sums (Ri) and column sums (Cj)
    row_sums = matrix.sum(axis=1)  # shape (n,)
    col_sums = matrix.sum(axis=0)  # shape (k,)

    c_bar = col_sums.mean()
    numerator = k * (k - 1) * np.sum((col_sums - c_bar) ** 2)
    denominator = k * np.sum(row_sums) - np.sum(row_sums ** 2)

    if denominator == 0:
        return {"Q": 0.0, "df": k - 1, "p_value": 1.0}

    q_stat = float(numerator / denominator)
    df = k - 1
    p_value = float(1.0 - sp_stats.chi2.cdf(q_stat, df=df))

    return {"Q": round(q_stat, 4), "df": df, "p_value": p_value}


def statistical_tests(
    verdicts: dict[str, list[int]],
) -> dict[str, Any]:
    """Run McNemar (all 15 pairs) and Cochran's Q tests.

    Applies Bonferroni correction on McNemar p-values.

    Args:
        verdicts: Binary verdict vectors.

    Returns:
        Dict with mcnemar_pairs, cochrans_q, and bonferroni_alpha.
    """
    n_pairs = 15  # C(6, 2)
    bonferroni_alpha = 0.05 / n_pairs

    mcnemar_results: list[dict[str, Any]] = []
    for (k1, lab1), (k2, lab2) in combinations(
        zip(EVALUATOR_KEYS, EVALUATOR_LABELS, strict=True), 2
    ):
        result = _mcnemar_test(verdicts[k1], verdicts[k2])
        corrected_significant = result["p_value"] < bonferroni_alpha
        mcnemar_results.append({
            "evaluator_a": lab1,
            "evaluator_b": lab2,
            **result,
            "bonferroni_significant": corrected_significant,
        })

    # Cochran's Q
    cq = _cochrans_q(verdicts)

    return {
        "mcnemar_pairs": mcnemar_results,
        "cochrans_q": cq,
        "bonferroni_alpha": round(bonferroni_alpha, 6),
        "n_significant_mcnemar": sum(
            1 for r in mcnemar_results if r["bonferroni_significant"]
        ),
    }


# ---------------------------------------------------------------------------
# 6. Disagreement taxonomy
# ---------------------------------------------------------------------------
def load_episode_jsons() -> dict[str, dict]:
    """Load all episode JSONs keyed by episode_id-like key.

    Key format: {scenario_id}_{model_dir}_r{run_index}

    Returns:
        Dict mapping key to episode JSON data.
    """
    results: dict[str, dict] = {}
    if not RESULTS_DIR.exists():
        print(f"  WARNING: Results directory not found: {RESULTS_DIR}")
        return results

    for model_dir in RESULTS_DIR.iterdir():
        if not model_dir.is_dir():
            continue
        for ep_file in model_dir.glob("*.json"):
            try:
                with open(ep_file) as f:
                    data = json.load(f)
            except (json.JSONDecodeError, OSError):
                continue
            key = (
                f"{data['scenario_id']}_{model_dir.name}"
                f"_r{data.get('run_index', 0)}"
            )
            results[key] = data

    return results


def _episode_key_from_verdict(ep: dict) -> str:
    """Build episode JSON lookup key from verdict matrix episode.

    Verdict matrix model labels (120B, 27B, ...) must map back to
    directory names (oss120b, qwen27b, ...).

    Args:
        ep: Per-episode record from verdict matrix.

    Returns:
        Key string matching load_episode_jsons format.
    """
    model_label = ep["model"]
    model_dir = LABEL_TO_DIR.get(model_label, model_label.lower())
    # episode_id format: {scenario_id}_{model_label}_{run_index}
    # Parse run index from episode_id
    eid = ep["episode_id"]
    parts = eid.rsplit("_", 1)
    run_idx = parts[-1] if len(parts) > 1 else "0"
    return f"{ep['scenario_id']}_{model_dir}_r{run_idx}"


def _classify_disagreement(
    violation_events: list[dict],
) -> list[str]:
    """Classify disagreement episode by violation types present.

    Type A (Timing): has timing or sequence violations.
    Type B (Forbidden): has commission violations.
    Type C (Completeness): has omission violations.
    Type D (Partial credit): has deviations only.

    An episode may belong to multiple types.

    Args:
        violation_events: List of violation event dicts from episode JSON.

    Returns:
        List of applicable type labels.
    """
    types_present: set[str] = set()
    for v in violation_events:
        vtype = v.get("violation_type", "").lower()
        if vtype in ("timing", "sequence"):
            types_present.add("Type A: Timing")
        elif vtype == "commission":
            types_present.add("Type B: Forbidden")
        elif vtype == "omission":
            types_present.add("Type C: Completeness")
        elif vtype == "deviation":
            types_present.add("Type D: Partial credit")

    if not types_present:
        types_present.add("Type D: Partial credit")

    return sorted(types_present)


def disagreement_taxonomy(
    episodes: list[dict],
    verdicts: dict[str, list[int]],
    episode_jsons: dict[str, dict],
) -> dict[str, Any]:
    """Classify disagreement episodes by violation type.

    Identifies episodes where evaluators disagree (not all same verdict),
    then categorises them using violation events from result JSONs.

    Args:
        episodes: Per-episode records from verdict matrix.
        verdicts: Binary verdict vectors.
        episode_jsons: Loaded episode JSON data.

    Returns:
        Dict with type counts, examples, and disagree episodes list.
    """
    type_counts: dict[str, int] = defaultdict(int)
    type_examples: dict[str, list[dict]] = defaultdict(list)
    disagree_episodes: list[dict] = []
    n_matched = 0
    n_unmatched = 0

    for i, ep in enumerate(episodes):
        votes = [verdicts[k][i] for k in EVALUATOR_KEYS]
        if all(v == votes[0] for v in votes):
            continue  # Full agreement — skip

        # Disagreement episode
        key = _episode_key_from_verdict(ep)
        ep_json = episode_jsons.get(key)

        violation_events: list[dict] = []
        if ep_json:
            violation_events = ep_json.get("new_violation_events", [])
            n_matched += 1
        else:
            # Fall back to verdict matrix viol_types
            viol_types = ep.get("viol_types", [])
            for vt in viol_types:
                vt_lower = vt.lower()
                if vt_lower in ("within", "before"):
                    violation_events.append({"violation_type": "timing"})
                elif vt_lower == "forbidden":
                    violation_events.append({"violation_type": "commission"})
            n_unmatched += 1

        types = _classify_disagreement(violation_events)
        pass_count = sum(votes)
        fail_count = N_EVALUATORS - pass_count

        record = {
            "episode_id": ep["episode_id"],
            "scenario_id": ep["scenario_id"],
            "model": ep["model"],
            "pass_count": pass_count,
            "fail_count": fail_count,
            "types": types,
        }
        disagree_episodes.append(record)

        for t in types:
            type_counts[t] += 1
            if len(type_examples[t]) < 3:
                type_examples[t].append({
                    "episode_id": ep["episode_id"],
                    "scenario_id": ep["scenario_id"],
                    "pass_fail": f"{pass_count}/{fail_count}",
                })

    total_disagree = len(disagree_episodes)
    type_summary = []
    for t in ["Type A: Timing", "Type B: Forbidden",
              "Type C: Completeness", "Type D: Partial credit"]:
        count = type_counts.get(t, 0)
        pct = count / total_disagree if total_disagree else 0.0
        type_summary.append({
            "type": t,
            "count": count,
            "pct": round(pct, 4),
            "examples": type_examples.get(t, []),
        })

    return {
        "total_disagreement_episodes": total_disagree,
        "total_episodes": len(episodes),
        "disagreement_rate": (
            round(total_disagree / len(episodes), 4) if episodes else 0.0
        ),
        "type_summary": type_summary,
        "disagree_episodes": disagree_episodes,
        "matched_jsons": n_matched,
        "unmatched_jsons": n_unmatched,
    }


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------
def plot_kappa_heatmap(
    pairwise: list[dict[str, Any]],
) -> plt.Figure:
    """Plot 6x6 Cohen's kappa heatmap.

    Args:
        pairwise: Pairwise agreement results.

    Returns:
        Matplotlib figure.
    """
    n = N_EVALUATORS
    matrix = np.ones((n, n), dtype=float)

    label_to_idx = {lab: idx for idx, lab in enumerate(EVALUATOR_LABELS)}
    for pair in pairwise:
        i = label_to_idx[pair["evaluator_a"]]
        j = label_to_idx[pair["evaluator_b"]]
        matrix[i, j] = pair["kappa"]
        matrix[j, i] = pair["kappa"]

    fig, ax = plt.subplots(figsize=(8, 6.5))
    im = ax.imshow(matrix, cmap="viridis", vmin=-0.2, vmax=1.0, aspect="equal")

    ax.set_xticks(range(n))
    ax.set_yticks(range(n))
    ax.set_xticklabels(EVALUATOR_LABELS, rotation=45, ha="right")
    ax.set_yticklabels(EVALUATOR_LABELS)

    # Annotate
    for i in range(n):
        for j in range(n):
            val = matrix[i, j]
            color = "white" if val < 0.5 else "black"
            ax.text(j, i, f"{val:.2f}", ha="center", va="center",
                    color=color, fontsize=9)

    fig.colorbar(im, ax=ax, label="Cohen's kappa", shrink=0.8)
    ax.set_title("Pairwise Cohen's Kappa Between Evaluators")
    fig.tight_layout()
    return fig


def plot_rank_reversal(
    rank_data: dict[str, Any],
) -> plt.Figure:
    """Plot bump chart of model ranks across evaluators.

    Args:
        rank_data: Rank reversal analysis results.

    Returns:
        Matplotlib figure.
    """
    model_ranks = rank_data["model_ranks"]
    models = sorted(set().union(*(r.keys() for r in model_ranks.values())))
    evaluators = EVALUATOR_LABELS

    fig, ax = plt.subplots(figsize=(10, 5))
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
              "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]

    for m_idx, model in enumerate(models):
        ranks = [model_ranks[ev].get(model, N_EVALUATORS) for ev in evaluators]
        color = colors[m_idx % len(colors)]
        ax.plot(range(len(evaluators)), ranks, "o-",
                label=model, color=color, linewidth=2, markersize=8)

    ax.set_xticks(range(len(evaluators)))
    ax.set_xticklabels(evaluators, rotation=30, ha="right")
    ax.set_ylabel("Model Rank (1 = best)")
    ax.set_title("Model Rankings Across Evaluators")
    ax.invert_yaxis()
    ax.set_yticks(range(1, len(models) + 1))
    ax.legend(loc="upper right", title="Model")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    return fig


def plot_passrate_by_evaluator(
    rank_data: dict[str, Any],
) -> plt.Figure:
    """Plot grouped bar chart of pass rates by evaluator and model.

    Args:
        rank_data: Rank reversal analysis results.

    Returns:
        Matplotlib figure.
    """
    model_pass_rates = rank_data["model_pass_rates"]
    evaluators = EVALUATOR_LABELS
    models = sorted(
        set().union(*(r.keys() for r in model_pass_rates.values()))
    )

    n_evaluators = len(evaluators)
    n_models = len(models)
    bar_width = 0.8 / n_models
    x = np.arange(n_evaluators)

    fig, ax = plt.subplots(figsize=(12, 5))
    colors = ["#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
              "#9467bd", "#8c564b", "#e377c2", "#7f7f7f"]

    for m_idx, model in enumerate(models):
        rates = [
            model_pass_rates[ev].get(model, 0.0) for ev in evaluators
        ]
        offset = (m_idx - n_models / 2 + 0.5) * bar_width
        ax.bar(x + offset, rates, bar_width,
               label=model, color=colors[m_idx % len(colors)])

    ax.set_xticks(x)
    ax.set_xticklabels(evaluators, rotation=30, ha="right")
    ax.set_ylabel("Pass Rate")
    ax.set_title("Pass Rate by Evaluator and Model")
    ax.set_ylim(0, 1.05)
    ax.legend(title="Model")
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    return fig


def plot_disagreement_taxonomy(
    taxonomy: dict[str, Any],
) -> plt.Figure:
    """Plot stacked bar chart of disagreement taxonomy.

    Args:
        taxonomy: Disagreement taxonomy results.

    Returns:
        Matplotlib figure.
    """
    type_summary = taxonomy["type_summary"]
    labels = [t["type"].split(": ")[1] for t in type_summary]
    counts = [t["count"] for t in type_summary]

    fig, ax = plt.subplots(figsize=(8, 5))
    colors = ["#4c72b0", "#dd8452", "#55a868", "#c44e52"]
    bars = ax.bar(labels, counts, color=colors[:len(labels)], edgecolor="black",
                  linewidth=0.5)

    # Add count labels on bars
    for bar, count in zip(bars, counts, strict=True):
        if count > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                    str(count), ha="center", va="bottom", fontsize=11)

    ax.set_ylabel("Number of Disagreement Episodes")
    ax.set_title("Disagreement Taxonomy by Violation Type")
    ax.grid(True, alpha=0.3, axis="y")
    fig.tight_layout()
    return fig


# ---------------------------------------------------------------------------
# LaTeX tables
# ---------------------------------------------------------------------------
def build_evaluator_agreement_table(
    pairwise: list[dict[str, Any]],
    mcnemar: list[dict[str, Any]],
) -> tuple[list[str], list[list[str]]]:
    """Build evaluator agreement LaTeX table data.

    Args:
        pairwise: Pairwise agreement results.
        mcnemar: McNemar test results.

    Returns:
        Tuple of (headers, rows).
    """
    headers = ["Pair", r"$\kappa$", "Agree \\%", "McNemar $p$"]
    rows: list[list[str]] = []

    mcnemar_map = {
        (r["evaluator_a"], r["evaluator_b"]): r for r in mcnemar
    }

    for pair in pairwise:
        key = (pair["evaluator_a"], pair["evaluator_b"])
        mc = mcnemar_map.get(key, {})
        p_val = mc.get("p_value", 1.0)
        sig = mc.get("bonferroni_significant", False)
        p_str = fmt_p(p_val)
        if sig:
            p_str = f"\\textbf{{{p_str}}}"

        rows.append([
            f"{pair['evaluator_a']} vs {pair['evaluator_b']}",
            fmt_f(pair["kappa"]),
            f"{pair['agreement_pct'] * 100:.1f}",
            p_str,
        ])

    return headers, rows


def build_rank_reversal_table(
    correlations: list[dict[str, Any]],
) -> tuple[list[str], list[list[str]]]:
    """Build rank reversal LaTeX table data.

    Args:
        correlations: Rank correlation results.

    Returns:
        Tuple of (headers, rows).
    """
    headers = [
        "Pair", r"Spearman $\rho$", r"Kendall $\tau$", "Reversals",
    ]
    rows: list[list[str]] = []

    for c in correlations:
        rho = fmt_f(c["spearman_rho"]) if c["spearman_rho"] is not None else "---"
        tau = fmt_f(c["kendall_tau"]) if c["kendall_tau"] is not None else "---"
        rows.append([
            f"{c['evaluator_a']} vs {c['evaluator_b']}",
            rho,
            tau,
            str(c["n_reversals"]),
        ])

    return headers, rows


def build_disagreement_taxonomy_table(
    taxonomy: dict[str, Any],
) -> tuple[list[str], list[list[str]]]:
    """Build disagreement taxonomy LaTeX table data.

    Args:
        taxonomy: Disagreement taxonomy results.

    Returns:
        Tuple of (headers, rows).
    """
    headers = ["Type", "Count", "\\%", "Example Episode"]
    rows: list[list[str]] = []

    for ts in taxonomy["type_summary"]:
        examples = ts.get("examples", [])
        example_str = examples[0]["episode_id"] if examples else "---"
        rows.append([
            ts["type"],
            str(ts["count"]),
            f"{ts['pct'] * 100:.1f}",
            example_str.replace("_", r"\_"),
        ])

    return headers, rows


# ---------------------------------------------------------------------------
# Markdown report
# ---------------------------------------------------------------------------
def build_markdown_report(
    pairwise: list[dict[str, Any]],
    multi_eval: dict[str, Any],
    rank_data: dict[str, Any],
    effect: dict[str, Any],
    stat_tests: dict[str, Any],
    taxonomy: dict[str, Any],
) -> str:
    """Build comprehensive markdown report.

    Args:
        pairwise: Pairwise agreement results.
        multi_eval: Multi-evaluator agreement results.
        rank_data: Rank reversal analysis results.
        effect: Effect size analysis results.
        stat_tests: Statistical test results.
        taxonomy: Disagreement taxonomy results.

    Returns:
        Markdown report string.
    """
    lines: list[str] = []
    lines.append("# EXP-D: Evaluation Disagreement Quantification\n")

    # 1. Pairwise
    lines.append("## 1. Pairwise Cohen's Kappa\n")
    lines.append("| Pair | kappa | Agreement % | Asymmetry |")
    lines.append("|------|-------|-------------|-----------|")
    for p in pairwise:
        lines.append(
            f"| {p['evaluator_a']} vs {p['evaluator_b']} "
            f"| {p['kappa']:.4f} | {p['agreement_pct'] * 100:.1f}% "
            f"| {p['asymmetry']} |"
        )

    # 2. Multi-evaluator
    lines.append("\n## 2. Multi-Evaluator Agreement (Fleiss' Kappa)\n")
    lines.append(f"**Overall**: {multi_eval['overall']:.4f}\n")
    lines.append("### Per-Domain")
    lines.append("| Domain | Fleiss' kappa |")
    lines.append("|--------|---------------|")
    for d, fk in multi_eval["per_domain"].items():
        lines.append(f"| {d} | {fk:.4f} |")
    lines.append("\n### Per-Model")
    lines.append("| Model | Fleiss' kappa |")
    lines.append("|-------|---------------|")
    for m, fk in multi_eval["per_model"].items():
        lines.append(f"| {m} | {fk:.4f} |")

    # 3. Rank reversal
    lines.append("\n## 3. Rank Reversal Analysis\n")
    lines.append(f"**Total rank reversals**: {rank_data['total_reversals']}\n")
    lines.append("### Rank Correlations")
    lines.append("| Pair | Spearman rho | Kendall tau | Reversals |")
    lines.append("|------|-------------|-------------|-----------|")
    for c in rank_data["rank_correlations"]:
        rho = f"{c['spearman_rho']:.4f}" if c["spearman_rho"] is not None else "---"
        tau = f"{c['kendall_tau']:.4f}" if c["kendall_tau"] is not None else "---"
        lines.append(
            f"| {c['evaluator_a']} vs {c['evaluator_b']} "
            f"| {rho} | {tau} | {c['n_reversals']} |"
        )

    if rank_data["rank_reversals"]:
        lines.append("\n### Concrete Reversals (first 10)")
        for rv in rank_data["rank_reversals"][:10]:
            lines.append(
                f"- **{rv['model_a']}** vs **{rv['model_b']}**: "
                f"{rv['evaluator_x']} ranks {rv['rank_x_a']}/{rv['rank_x_b']}, "
                f"{rv['evaluator_y']} ranks {rv['rank_y_a']}/{rv['rank_y_b']}"
            )

    # 4. Effect size
    lines.append("\n## 4. Effect Size Analysis\n")
    lines.append(f"**Most lenient**: {effect['most_lenient']}")
    lines.append(f"**Most strict**: {effect['most_strict']}")
    lines.append(
        f"**Max gap**: {effect['max_gap']:.4f} "
        f"(95% CI: [{effect['max_gap_ci_95'][0]:.4f}, "
        f"{effect['max_gap_ci_95'][1]:.4f}])"
    )
    lines.append("\n### Per-Model Gap")
    lines.append("| Model | Gap | Most Lenient | Most Strict |")
    lines.append("|-------|-----|-------------|-------------|")
    for m, info in effect["per_model_gap"].items():
        lines.append(
            f"| {m} | {info['gap']:.4f} "
            f"| {info['most_lenient']} | {info['most_strict']} |"
        )

    # 5. Statistical tests
    lines.append("\n## 5. Statistical Tests\n")
    cq = stat_tests["cochrans_q"]
    lines.append(
        f"**Cochran's Q**: Q={cq['Q']:.4f}, df={cq['df']}, "
        f"p={fmt_p(cq['p_value'])}"
    )
    lines.append(
        f"\n**McNemar tests**: {stat_tests['n_significant_mcnemar']}/15 "
        f"significant after Bonferroni correction "
        f"(alpha={stat_tests['bonferroni_alpha']:.4f})"
    )
    lines.append("\n| Pair | chi2 | p | Significant |")
    lines.append("|------|------|---|-------------|")
    for mc in stat_tests["mcnemar_pairs"]:
        sig = "Yes" if mc["bonferroni_significant"] else "No"
        lines.append(
            f"| {mc['evaluator_a']} vs {mc['evaluator_b']} "
            f"| {mc['chi2']:.2f} | {fmt_p(mc['p_value'])} | {sig} |"
        )

    # 6. Taxonomy
    lines.append("\n## 6. Disagreement Taxonomy\n")
    lines.append(
        f"**Disagreement episodes**: {taxonomy['total_disagreement_episodes']} "
        f"/ {taxonomy['total_episodes']} "
        f"({taxonomy['disagreement_rate'] * 100:.1f}%)"
    )
    lines.append("\n| Type | Count | % | Examples |")
    lines.append("|------|-------|---|---------|")
    for ts in taxonomy["type_summary"]:
        examples = ", ".join(e["episode_id"] for e in ts.get("examples", [])[:2])
        lines.append(
            f"| {ts['type']} | {ts['count']} "
            f"| {ts['pct'] * 100:.1f}% | {examples} |"
        )

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
def main() -> None:
    """Run EXP-D disagreement quantification analysis."""
    setup_matplotlib()
    print("=" * 60)
    print("EXP-D: Evaluation Disagreement Quantification")
    print("=" * 60)

    # --- Load data ---
    print("\n[1/7] Loading data...")
    episodes = load_per_episode()
    verdicts = extract_binary_verdicts(episodes)
    episode_jsons = load_episode_jsons()
    print(f"  Loaded {len(episodes)} episodes, {len(episode_jsons)} result JSONs")

    # --- 1. Pairwise agreement ---
    print("\n[2/7] Pairwise agreement...")
    pairwise = pairwise_agreement(verdicts)
    kappas = [p["kappa"] for p in pairwise]
    print(f"  15 pairs computed. Mean kappa={np.mean(kappas):.4f}, "
          f"range=[{min(kappas):.4f}, {max(kappas):.4f}]")

    # --- 2. Multi-evaluator agreement ---
    print("\n[3/7] Multi-evaluator agreement...")
    multi_eval = multi_evaluator_agreement(episodes, verdicts)
    print(f"  Overall Fleiss' kappa={multi_eval['overall']:.4f}")
    for d, fk in multi_eval["per_domain"].items():
        print(f"    {d}: {fk:.4f}")

    # --- 3. Rank reversal ---
    print("\n[4/7] Rank reversal analysis...")
    rank_data = rank_reversal_analysis(episodes, verdicts)
    print(f"  Total rank reversals: {rank_data['total_reversals']}")
    for c in rank_data["rank_correlations"]:
        rho_str = (
            f"{c['spearman_rho']:.4f}" if c["spearman_rho"] is not None else "N/A"
        )
        print(f"    {c['evaluator_a']} vs {c['evaluator_b']}: "
              f"rho={rho_str}, reversals={c['n_reversals']}")

    # --- 4. Effect size ---
    print("\n[5/7] Effect size analysis...")
    effect = effect_size_analysis(episodes, verdicts)
    print(f"  Most lenient: {effect['most_lenient']} "
          f"({effect['evaluator_order'][0]['pass_rate']:.1%})")
    print(f"  Most strict:  {effect['most_strict']} "
          f"({effect['evaluator_order'][-1]['pass_rate']:.1%})")
    print(f"  Max gap: {effect['max_gap']:.4f} "
          f"(95% CI: [{effect['max_gap_ci_95'][0]:.4f}, "
          f"{effect['max_gap_ci_95'][1]:.4f}])")

    # --- 5. Statistical tests ---
    print("\n[6/7] Statistical tests...")
    stat_tests = statistical_tests(verdicts)
    cq = stat_tests["cochrans_q"]
    print(f"  Cochran's Q={cq['Q']:.4f}, p={fmt_p(cq['p_value'])}")
    print(f"  McNemar significant (Bonferroni): "
          f"{stat_tests['n_significant_mcnemar']}/15")

    # --- 6. Disagreement taxonomy ---
    print("\n[7/7] Disagreement taxonomy...")
    taxonomy = disagreement_taxonomy(episodes, verdicts, episode_jsons)
    print(f"  Disagreement episodes: {taxonomy['total_disagreement_episodes']}"
          f"/{taxonomy['total_episodes']} "
          f"({taxonomy['disagreement_rate'] * 100:.1f}%)")
    for ts in taxonomy["type_summary"]:
        print(f"    {ts['type']}: {ts['count']} ({ts['pct'] * 100:.1f}%)")

    # --- Save JSON ---
    print("\nSaving outputs...")
    all_results = {
        "metadata": {
            "experiment": "EXP-D",
            "n_episodes": len(episodes),
            "n_evaluators": N_EVALUATORS,
            "evaluators": EVALUATOR_LABELS,
            "n_result_jsons": len(episode_jsons),
            "n_bootstrap": N_BOOTSTRAP,
            "seed": SEED,
        },
        "pairwise_agreement": pairwise,
        "multi_evaluator_agreement": multi_eval,
        "rank_reversal": rank_data,
        "effect_size": effect,
        "statistical_tests": stat_tests,
        "disagreement_taxonomy": taxonomy,
    }
    save_json(all_results, EVIDENCE_DIR / "exp_d_disagreement.json")

    # --- Save markdown ---
    md = build_markdown_report(
        pairwise, multi_eval, rank_data, effect, stat_tests, taxonomy,
    )
    save_markdown(md, EVIDENCE_DIR / "exp_d_disagreement.md")

    # --- Save figures ---
    fig_kappa = plot_kappa_heatmap(pairwise)
    save_figure(fig_kappa, FIGURES_DIR / "exp_d_kappa_heatmap.png")

    fig_rank = plot_rank_reversal(rank_data)
    save_figure(fig_rank, FIGURES_DIR / "exp_d_rank_reversal.png")

    fig_passrate = plot_passrate_by_evaluator(rank_data)
    save_figure(fig_passrate, FIGURES_DIR / "exp_d_passrate_by_evaluator.png")

    fig_taxonomy = plot_disagreement_taxonomy(taxonomy)
    save_figure(fig_taxonomy, FIGURES_DIR / "exp_d_disagreement_taxonomy.png")

    # --- Save LaTeX tables ---
    headers, rows = build_evaluator_agreement_table(
        pairwise, stat_tests["mcnemar_pairs"],
    )
    save_latex_table(
        rows, headers,
        TABLES_DIR / "evaluator_agreement.tex",
        caption="Pairwise evaluator agreement with McNemar significance.",
        label="tab:evaluator-agreement",
    )

    headers, rows = build_rank_reversal_table(rank_data["rank_correlations"])
    save_latex_table(
        rows, headers,
        TABLES_DIR / "rank_reversal.tex",
        caption="Rank correlation and reversal counts between evaluator pairs.",
        label="tab:rank-reversal",
    )

    headers, rows = build_disagreement_taxonomy_table(taxonomy)
    save_latex_table(
        rows, headers,
        TABLES_DIR / "disagreement_taxonomy.tex",
        caption="Disagreement taxonomy by violation type.",
        label="tab:disagreement-taxonomy",
    )

    print("\nEXP-D complete.")


if __name__ == "__main__":
    main()
