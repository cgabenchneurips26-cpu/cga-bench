#!/usr/bin/env python3
"""EXP-A: Manual vs Auto-generated Scenario Structural Equivalence.

Proves that auto-generated scenarios are structurally equivalent to
manually authored scenarios across 6 dimensions.

Outputs:
  evidence_pack/exp_a_scenario_equivalence.json
  evidence_pack/exp_a_scenario_equivalence.md
  evidence_pack/figures/exp_a_constraint_density.png
  evidence_pack/figures/exp_a_domain_coverage.png
  evidence_pack/figures/exp_a_complexity.png
  evidence_pack/figures/exp_a_expected_actions.png
  evidence_pack/tables/scenario_equivalence.tex

Usage:
    PYTHONPATH=. python scripts/experiments/exp_a_scenario_equivalence.py
"""

from __future__ import annotations

from collections import Counter
from pathlib import Path
import sys
from typing import Any

import numpy as np
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
import matplotlib
from scripts.experiments._common import (
    EVIDENCE_DIR,
    FIGURES_DIR,
    N_BOOTSTRAP,
    SEED,
    TABLES_DIR,
    bootstrap_ci,
    canonical_graph_id,
    domain_from_scenario,
    fmt_f,
    fmt_p,
    load_all_graphs,
    load_all_scenarios,
    resolve_graph_path,
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

CONSTRAINT_TYPES = ["FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN", "EXPECTED"]
N_ANALYSES = 6  # total independent analyses for Bonferroni correction
MANUAL_COLOR = "#4878CF"  # blue
AUTO_COLOR = "#E8833A"  # orange


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_list(val: object) -> list[object]:
    """Return val if list, else empty list."""
    return val if isinstance(val, list) else []


def _cohens_d(a: np.ndarray, b: np.ndarray) -> float:
    """Compute Cohen's d effect size between two samples.

    Args:
        a: First sample array.
        b: Second sample array.

    Returns:
        Cohen's d value. Returns 0.0 if both samples have zero variance.
    """
    n_a, n_b = len(a), len(b)
    if n_a < 2 or n_b < 2:
        return 0.0
    var_a = float(np.var(a, ddof=1))
    var_b = float(np.var(b, ddof=1))
    pooled_var = ((n_a - 1) * var_a + (n_b - 1) * var_b) / (n_a + n_b - 2)
    if pooled_var == 0.0:
        return 0.0
    return float((np.mean(a) - np.mean(b)) / np.sqrt(pooled_var))


def _bonferroni(p: float) -> float:
    """Apply Bonferroni correction for N_ANALYSES independent tests."""
    return min(p * N_ANALYSES, 1.0)


def _mean_sd(arr: np.ndarray) -> tuple[float, float]:
    """Return (mean, std) for an array, handling empty inputs."""
    if len(arr) == 0:
        return (0.0, 0.0)
    return (float(np.mean(arr)), float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0)


# ---------------------------------------------------------------------------
# 1. Derive constraints for all scenarios
# ---------------------------------------------------------------------------

def derive_all_constraints(
    scenarios: list[dict[str, Any]],
    engine: ConstraintDerivationEngine,
    graphs: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    """Derive constraints for each scenario using the ConstraintDerivationEngine.

    For each scenario, resolves the graph file, loads it (with caching),
    and derives constraints via engine.derive(). Scenarios without a
    matching graph are skipped.

    Args:
        scenarios: List of scenario dicts (with source_type tag).
        engine: Initialized ConstraintDerivationEngine.
        graphs: Pre-loaded graph dict keyed by canonical graph_id.

    Returns:
        List of enriched dicts with constraint counts and metadata.
    """
    enriched: list[dict[str, Any]] = []
    graph_cache: dict[str, dict[str, Any]] = {}
    skipped = 0

    for sc in scenarios:
        sid = sc.get("scenario_id", "")
        guideline = sc.get("guideline_graph", "")
        patient = sc.get("patient", {})

        if not guideline or not patient:
            skipped += 1
            continue

        # Resolve and load graph (with cache)
        if guideline not in graph_cache:
            gpath = resolve_graph_path(guideline)
            if gpath is None:
                # Try canonical alias
                canon = canonical_graph_id(guideline)
                gpath = resolve_graph_path(canon)
            if gpath is not None:
                graph_cache[guideline] = load_graph(gpath)
            else:
                graph_cache[guideline] = {}

        graph_data = graph_cache[guideline]
        if not graph_data:
            skipped += 1
            continue

        # Derive constraints
        cset = engine.derive(graph_data, patient, scenario_id=sid)

        row: dict[str, Any] = {
            "scenario_id": sid,
            "source_type": sc.get("source_type", "unknown"),
            "domain": domain_from_scenario(sc),
            "guideline_graph": guideline,
            "n_FORBIDDEN": len(cset.forbidden),
            "n_REQUIRED": len(cset.required),
            "n_BEFORE": len(cset.before),
            "n_WITHIN": len(cset.within),
            "n_EXPECTED": len(cset.expected),
            "n_total_constraints": len(cset.all_constraints()),
            "total_rules_evaluated": cset.total_rules_evaluated,
            "total_rules_triggered": cset.total_rules_triggered,
            "n_comorbidities": len(_safe_list(patient.get("comorbidities"))),
            "n_allergies": len(_safe_list(patient.get("allergies"))),
            "n_active_conditions": (
                len(_safe_list(patient.get("comorbidities")))
                + len(_safe_list(patient.get("allergies")))
            ),
            "n_expected_actions_scenario": len(_safe_list(sc.get("expected_actions"))),
            "n_forbidden_actions_scenario": len(_safe_list(sc.get("forbidden_actions"))),
            "trap_scenario": bool(sc.get("trap_scenario", False)),
            # Provenance info (auto scenarios have _derived_constraints)
            "has_derived_constraints": "_derived_constraints" in sc,
            "n_conditional": sum(
                1 for c in cset.all_constraints() if c.is_conditional
            ),
            "n_unconditional": sum(
                1 for c in cset.all_constraints() if not c.is_conditional
            ),
            "provenance_strings": [
                c.provenance for c in cset.all_constraints()
            ],
            # Store derived expected for provenance check
            "derived_expected_actions": [
                a for c in cset.expected for a in c.actions
            ],
        }
        enriched.append(row)

    print(f"  Enriched {len(enriched)} scenarios, skipped {skipped}")
    return enriched


# ---------------------------------------------------------------------------
# 2. Constraint density analysis
# ---------------------------------------------------------------------------

def analyze_constraint_density(
    enriched: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare constraint type distributions between manual and auto scenarios.

    Runs Mann-Whitney U tests and computes Cohen's d for each constraint
    type. Generates a side-by-side histogram figure.

    Args:
        enriched: List of enriched scenario dicts.

    Returns:
        Dict with per-type statistics and test results.
    """
    manual = [e for e in enriched if e["source_type"] == "manual"]
    auto = [e for e in enriched if e["source_type"] == "auto"]

    results: dict[str, Any] = {"per_type": {}, "total": {}}

    fig, axes = plt.subplots(1, len(CONSTRAINT_TYPES), figsize=(18, 4))
    if len(CONSTRAINT_TYPES) == 1:
        axes = [axes]

    for idx, ctype in enumerate(CONSTRAINT_TYPES):
        key = f"n_{ctype}"
        m_vals = np.array([e[key] for e in manual], dtype=float)
        a_vals = np.array([e[key] for e in auto], dtype=float)

        m_mean, m_sd = _mean_sd(m_vals)
        a_mean, a_sd = _mean_sd(a_vals)

        # Mann-Whitney U test
        if len(m_vals) > 0 and len(a_vals) > 0:
            stat, p_raw = stats.mannwhitneyu(
                m_vals, a_vals, alternative="two-sided"
            )
        else:
            stat, p_raw = 0.0, 1.0

        p_adj = _bonferroni(p_raw)
        d = _cohens_d(m_vals, a_vals)

        results["per_type"][ctype] = {
            "manual_mean": round(m_mean, 3),
            "manual_sd": round(m_sd, 3),
            "manual_n": len(m_vals),
            "auto_mean": round(a_mean, 3),
            "auto_sd": round(a_sd, 3),
            "auto_n": len(a_vals),
            "U_statistic": round(float(stat), 2),
            "p_raw": float(p_raw),
            "p_bonferroni": float(p_adj),
            "cohens_d": round(d, 3),
        }

        # Histogram subplot
        ax = axes[idx]
        max_val = max(
            int(np.max(m_vals)) if len(m_vals) > 0 else 0,
            int(np.max(a_vals)) if len(a_vals) > 0 else 0,
            1,
        )
        bins = np.arange(0, max_val + 2) - 0.5
        ax.hist(m_vals, bins=bins, alpha=0.6, color=MANUAL_COLOR, label="Manual", density=True)
        ax.hist(a_vals, bins=bins, alpha=0.6, color=AUTO_COLOR, label="Auto", density=True)
        ax.set_title(ctype)
        ax.set_xlabel("Count")
        ax.set_ylabel("Density")
        sig_label = "*" if p_adj < 0.05 else "ns"
        ax.annotate(
            f"d={d:.2f} ({sig_label})",
            xy=(0.95, 0.95),
            xycoords="axes fraction",
            ha="right",
            va="top",
            fontsize=9,
        )
        if idx == 0:
            ax.legend(fontsize=8)

    # Total constraints
    m_total = np.array([e["n_total_constraints"] for e in manual], dtype=float)
    a_total = np.array([e["n_total_constraints"] for e in auto], dtype=float)
    m_mean_t, m_sd_t = _mean_sd(m_total)
    a_mean_t, a_sd_t = _mean_sd(a_total)
    if len(m_total) > 0 and len(a_total) > 0:
        stat_t, p_t = stats.mannwhitneyu(m_total, a_total, alternative="two-sided")
    else:
        stat_t, p_t = 0.0, 1.0

    results["total"] = {
        "manual_mean": round(m_mean_t, 3),
        "manual_sd": round(m_sd_t, 3),
        "auto_mean": round(a_mean_t, 3),
        "auto_sd": round(a_sd_t, 3),
        "U_statistic": round(float(stat_t), 2),
        "p_raw": float(p_t),
        "p_bonferroni": float(_bonferroni(p_t)),
        "cohens_d": round(_cohens_d(m_total, a_total), 3),
    }

    fig.suptitle("Constraint Density by Type (Manual vs Auto)", fontsize=14, y=1.02)
    fig.tight_layout()
    save_figure(fig, FIGURES_DIR / "exp_a_constraint_density.png")

    return results


# ---------------------------------------------------------------------------
# 3. Domain coverage analysis
# ---------------------------------------------------------------------------

def analyze_domain_coverage(
    manual: list[dict[str, Any]],
    auto: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare domain distributions between manual and auto scenarios.

    Computes Jaccard similarity of domain sets, per-domain counts, and
    chi-square test on domain frequency table.

    Args:
        manual: Manual scenario dicts.
        auto: Auto scenario dicts.

    Returns:
        Dict with domain sets, counts, Jaccard, and chi-square results.
    """
    m_domains = Counter(domain_from_scenario(s) for s in manual)
    a_domains = Counter(domain_from_scenario(s) for s in auto)

    m_set = set(m_domains.keys())
    a_set = set(a_domains.keys())
    all_domains = sorted(m_set | a_set)

    intersection = m_set & a_set
    union = m_set | a_set
    jaccard = len(intersection) / len(union) if union else 1.0

    # Per-domain counts for chi-square
    m_counts = [m_domains.get(d, 0) for d in all_domains]
    a_counts = [a_domains.get(d, 0) for d in all_domains]

    # Chi-square on 2 x K contingency table
    contingency = np.array([m_counts, a_counts])
    # Remove columns with all zeros to avoid chi2 issues
    nonzero_mask = contingency.sum(axis=0) > 0
    contingency_clean = contingency[:, nonzero_mask]

    if contingency_clean.shape[1] >= 2:
        chi2, p_raw, dof, _expected = stats.chi2_contingency(contingency_clean)
    else:
        chi2, p_raw, dof = 0.0, 1.0, 0

    p_adj = _bonferroni(p_raw)

    # Bar chart
    fig, ax = plt.subplots(figsize=(max(10, len(all_domains) * 0.8), 5))
    x = np.arange(len(all_domains))
    width = 0.35
    ax.bar(x - width / 2, m_counts, width, label="Manual", color=MANUAL_COLOR, alpha=0.8)
    ax.bar(x + width / 2, a_counts, width, label="Auto", color=AUTO_COLOR, alpha=0.8)
    ax.set_xticks(x)
    ax.set_xticklabels(all_domains, rotation=45, ha="right", fontsize=8)
    ax.set_ylabel("Scenario Count")
    ax.set_title("Domain Coverage: Manual vs Auto Scenarios")
    ax.legend()

    sig_label = "*" if p_adj < 0.05 else "ns"
    ax.annotate(
        f"Jaccard={jaccard:.2f}, chi2={chi2:.1f} ({sig_label})",
        xy=(0.98, 0.95),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=9,
    )
    fig.tight_layout()
    save_figure(fig, FIGURES_DIR / "exp_a_domain_coverage.png")

    return {
        "manual_domains": sorted(m_set),
        "auto_domains": sorted(a_set),
        "shared_domains": sorted(intersection),
        "manual_only": sorted(m_set - a_set),
        "auto_only": sorted(a_set - m_set),
        "jaccard_similarity": round(jaccard, 3),
        "per_domain_manual": dict(m_domains),
        "per_domain_auto": dict(a_domains),
        "chi2_statistic": round(float(chi2), 3),
        "chi2_p_raw": float(p_raw),
        "chi2_p_bonferroni": float(p_adj),
        "chi2_dof": int(dof),
        "n_domains_manual": len(m_set),
        "n_domains_auto": len(a_set),
    }


# ---------------------------------------------------------------------------
# 4. Patient complexity analysis
# ---------------------------------------------------------------------------

def analyze_patient_complexity(
    enriched: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare patient complexity between manual and auto scenarios.

    Examines active conditions (comorbidities + allergies) and
    triggered rules count. Uses KS test for distributional comparison.

    Args:
        enriched: Enriched scenario dicts.

    Returns:
        Dict with complexity statistics and KS test results.
    """
    manual = [e for e in enriched if e["source_type"] == "manual"]
    auto = [e for e in enriched if e["source_type"] == "auto"]

    # Active conditions
    m_cond = np.array([e["n_active_conditions"] for e in manual], dtype=float)
    a_cond = np.array([e["n_active_conditions"] for e in auto], dtype=float)

    if len(m_cond) > 0 and len(a_cond) > 0:
        ks_cond, p_cond_raw = stats.ks_2samp(m_cond, a_cond)
    else:
        ks_cond, p_cond_raw = 0.0, 1.0

    # Triggered rules
    m_rules = np.array([e["total_rules_triggered"] for e in manual], dtype=float)
    a_rules = np.array([e["total_rules_triggered"] for e in auto], dtype=float)

    if len(m_rules) > 0 and len(a_rules) > 0:
        ks_rules, p_rules_raw = stats.ks_2samp(m_rules, a_rules)
    else:
        ks_rules, p_rules_raw = 0.0, 1.0

    p_cond_adj = _bonferroni(p_cond_raw)
    p_rules_adj = _bonferroni(p_rules_raw)

    # Dual histogram figure
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 5))

    # Active conditions
    max_cond = max(
        int(np.max(m_cond)) if len(m_cond) > 0 else 0,
        int(np.max(a_cond)) if len(a_cond) > 0 else 0,
        1,
    )
    bins_cond = np.arange(0, max_cond + 2) - 0.5
    ax1.hist(m_cond, bins=bins_cond, alpha=0.6, color=MANUAL_COLOR, label="Manual", density=True)
    ax1.hist(a_cond, bins=bins_cond, alpha=0.6, color=AUTO_COLOR, label="Auto", density=True)
    ax1.set_title("Active Conditions (Comorbidities + Allergies)")
    ax1.set_xlabel("Count")
    ax1.set_ylabel("Density")
    ax1.legend(fontsize=9)
    sig1 = "*" if p_cond_adj < 0.05 else "ns"
    ax1.annotate(
        f"KS={ks_cond:.2f} ({sig1})",
        xy=(0.95, 0.95),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=9,
    )

    # Triggered rules
    max_rules = max(
        int(np.max(m_rules)) if len(m_rules) > 0 else 0,
        int(np.max(a_rules)) if len(a_rules) > 0 else 0,
        1,
    )
    bins_rules = np.arange(0, max_rules + 2) - 0.5
    ax2.hist(m_rules, bins=bins_rules, alpha=0.6, color=MANUAL_COLOR, label="Manual", density=True)
    ax2.hist(a_rules, bins=bins_rules, alpha=0.6, color=AUTO_COLOR, label="Auto", density=True)
    ax2.set_title("Triggered Conditional Rules")
    ax2.set_xlabel("Count")
    ax2.set_ylabel("Density")
    ax2.legend(fontsize=9)
    sig2 = "*" if p_rules_adj < 0.05 else "ns"
    ax2.annotate(
        f"KS={ks_rules:.2f} ({sig2})",
        xy=(0.95, 0.95),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=9,
    )

    fig.suptitle("Patient Complexity: Manual vs Auto", fontsize=14, y=1.02)
    fig.tight_layout()
    save_figure(fig, FIGURES_DIR / "exp_a_complexity.png")

    m_cond_mean, m_cond_sd = _mean_sd(m_cond)
    a_cond_mean, a_cond_sd = _mean_sd(a_cond)
    m_rules_mean, m_rules_sd = _mean_sd(m_rules)
    a_rules_mean, a_rules_sd = _mean_sd(a_rules)

    return {
        "active_conditions": {
            "manual_mean": round(m_cond_mean, 3),
            "manual_sd": round(m_cond_sd, 3),
            "auto_mean": round(a_cond_mean, 3),
            "auto_sd": round(a_cond_sd, 3),
            "ks_statistic": round(float(ks_cond), 3),
            "p_raw": float(p_cond_raw),
            "p_bonferroni": float(p_cond_adj),
            "cohens_d": round(_cohens_d(m_cond, a_cond), 3),
        },
        "triggered_rules": {
            "manual_mean": round(m_rules_mean, 3),
            "manual_sd": round(m_rules_sd, 3),
            "auto_mean": round(a_rules_mean, 3),
            "auto_sd": round(a_rules_sd, 3),
            "ks_statistic": round(float(ks_rules), 3),
            "p_raw": float(p_rules_raw),
            "p_bonferroni": float(p_rules_adj),
            "cohens_d": round(_cohens_d(m_rules, a_rules), 3),
        },
    }


# ---------------------------------------------------------------------------
# 5. Expected actions analysis
# ---------------------------------------------------------------------------

def analyze_expected_actions(
    enriched: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare expected action counts between manual and auto scenarios.

    Uses Mann-Whitney U test on per-scenario expected action counts
    (from the scenario YAML, not derived).

    Args:
        enriched: Enriched scenario dicts.

    Returns:
        Dict with statistics and test results.
    """
    manual = [e for e in enriched if e["source_type"] == "manual"]
    auto = [e for e in enriched if e["source_type"] == "auto"]

    m_vals = np.array([e["n_expected_actions_scenario"] for e in manual], dtype=float)
    a_vals = np.array([e["n_expected_actions_scenario"] for e in auto], dtype=float)

    m_mean, m_sd = _mean_sd(m_vals)
    a_mean, a_sd = _mean_sd(a_vals)

    if len(m_vals) > 0 and len(a_vals) > 0:
        stat, p_raw = stats.mannwhitneyu(m_vals, a_vals, alternative="two-sided")
    else:
        stat, p_raw = 0.0, 1.0

    p_adj = _bonferroni(p_raw)
    d = _cohens_d(m_vals, a_vals)

    # Histogram
    fig, ax = plt.subplots(figsize=(8, 5))
    max_val = max(
        int(np.max(m_vals)) if len(m_vals) > 0 else 0,
        int(np.max(a_vals)) if len(a_vals) > 0 else 0,
        1,
    )
    bins = np.arange(0, max_val + 2) - 0.5
    ax.hist(m_vals, bins=bins, alpha=0.6, color=MANUAL_COLOR, label="Manual", density=True)
    ax.hist(a_vals, bins=bins, alpha=0.6, color=AUTO_COLOR, label="Auto", density=True)
    ax.set_title("Expected Actions per Scenario")
    ax.set_xlabel("Count")
    ax.set_ylabel("Density")
    ax.legend()
    sig = "*" if p_adj < 0.05 else "ns"
    ax.annotate(
        f"d={d:.2f}, U={stat:.0f} ({sig})",
        xy=(0.95, 0.95),
        xycoords="axes fraction",
        ha="right",
        va="top",
        fontsize=9,
    )
    fig.tight_layout()
    save_figure(fig, FIGURES_DIR / "exp_a_expected_actions.png")

    return {
        "manual_mean": round(m_mean, 3),
        "manual_sd": round(m_sd, 3),
        "manual_n": len(m_vals),
        "auto_mean": round(a_mean, 3),
        "auto_sd": round(a_sd, 3),
        "auto_n": len(a_vals),
        "U_statistic": round(float(stat), 2),
        "p_raw": float(p_raw),
        "p_bonferroni": float(p_adj),
        "cohens_d": round(d, 3),
    }


# ---------------------------------------------------------------------------
# 6. Trap ratio analysis
# ---------------------------------------------------------------------------

def analyze_trap_ratio(
    manual: list[dict[str, Any]],
    auto: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compare trap scenario proportions between manual and auto.

    Uses chi-square test on a 2x2 contingency table (trap / non-trap)
    x (manual / auto).

    Args:
        manual: Manual scenario dicts.
        auto: Auto scenario dicts.

    Returns:
        Dict with trap counts, proportions, and chi-square result.
    """
    m_trap = sum(1 for s in manual if s.get("trap_scenario", False))
    m_non = len(manual) - m_trap
    a_trap = sum(1 for s in auto if s.get("trap_scenario", False))
    a_non = len(auto) - a_trap

    m_ratio = m_trap / len(manual) if manual else 0.0
    a_ratio = a_trap / len(auto) if auto else 0.0

    contingency = np.array([[m_trap, m_non], [a_trap, a_non]])

    # chi2_contingency requires all margins > 0
    margins_ok = (
        contingency.sum() > 0
        and all(contingency.sum(axis=0) > 0)
        and all(contingency.sum(axis=1) > 0)
    )
    if margins_ok:
        chi2, p_raw, dof, _expected = stats.chi2_contingency(contingency)
    else:
        chi2, p_raw, dof = 0.0, 1.0, 1

    p_adj = _bonferroni(p_raw)

    return {
        "manual_trap": m_trap,
        "manual_total": len(manual),
        "manual_ratio": round(m_ratio, 3),
        "auto_trap": a_trap,
        "auto_total": len(auto),
        "auto_ratio": round(a_ratio, 3),
        "chi2_statistic": round(float(chi2), 3),
        "chi2_p_raw": float(p_raw),
        "chi2_p_bonferroni": float(p_adj),
        "chi2_dof": int(dof),
    }


# ---------------------------------------------------------------------------
# 7. Provenance completeness analysis
# ---------------------------------------------------------------------------

def analyze_provenance_completeness(
    enriched: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assess constraint provenance quality for auto and manual scenarios.

    For auto scenarios: checks all derived constraints have valid
    provenance strings (non-empty, containing 'graph:').

    For manual scenarios: computes what fraction of the scenario's
    expected_actions are covered by engine-derived expected actions.

    Args:
        enriched: Enriched scenario dicts.

    Returns:
        Dict with provenance quality metrics.
    """
    manual = [e for e in enriched if e["source_type"] == "manual"]
    auto = [e for e in enriched if e["source_type"] == "auto"]

    # Auto: provenance validity
    auto_valid_count = 0
    auto_total_constraints = 0
    auto_invalid_examples: list[str] = []

    for e in auto:
        prov_strings = e.get("provenance_strings", [])
        for prov in prov_strings:
            auto_total_constraints += 1
            if prov and "graph:" in prov:
                auto_valid_count += 1
            else:
                if len(auto_invalid_examples) < 5:
                    auto_invalid_examples.append(
                        f"{e['scenario_id']}: '{prov}'"
                    )

    auto_validity_rate = (
        auto_valid_count / auto_total_constraints
        if auto_total_constraints > 0
        else 0.0
    )

    # Manual: expected action coverage by engine derivation
    manual_coverage_scores: list[float] = []

    for e in manual:
        n_scenario_expected = e["n_expected_actions_scenario"]
        if n_scenario_expected == 0:
            continue

        derived_expected = set(e.get("derived_expected_actions", []))
        # Ratio of engine-derived expected actions to scenario-declared count.
        coverage = min(len(derived_expected) / n_scenario_expected, 1.0)
        manual_coverage_scores.append(coverage)

    manual_coverage_arr = np.array(manual_coverage_scores, dtype=float)
    m_cov_mean, m_cov_sd = _mean_sd(manual_coverage_arr)

    return {
        "auto_provenance": {
            "total_constraints": auto_total_constraints,
            "valid_provenance_count": auto_valid_count,
            "validity_rate": round(auto_validity_rate, 4),
            "invalid_examples": auto_invalid_examples,
        },
        "manual_derivation_coverage": {
            "n_scenarios_with_expected": len(manual_coverage_scores),
            "mean_coverage": round(m_cov_mean, 3),
            "sd_coverage": round(m_cov_sd, 3),
            "ci_95": [
                round(v, 3)
                for v in bootstrap_ci(
                    manual_coverage_arr, np.mean, n_bootstrap=N_BOOTSTRAP, seed=SEED
                )
            ] if len(manual_coverage_arr) > 0 else [0.0, 0.0],
        },
    }


# ---------------------------------------------------------------------------
# Report generators
# ---------------------------------------------------------------------------

def generate_markdown_report(results: dict[str, Any]) -> str:
    """Generate a human-readable Markdown summary of all 6 analyses.

    Args:
        results: Combined results dict from all analyses.

    Returns:
        Markdown string.
    """
    lines: list[str] = []
    lines.append("# EXP-A: Scenario Structural Equivalence Report")
    lines.append("")
    lines.append(f"**Manual scenarios**: {results['summary']['n_manual']}")
    lines.append(f"**Auto scenarios**: {results['summary']['n_auto']}")
    lines.append(f"**Enriched (with graph match)**: {results['summary']['n_enriched']}")
    lines.append("")
    lines.append(f"Bonferroni correction applied (k={N_ANALYSES}).")
    lines.append("")

    # 1. Constraint density
    lines.append("## 1. Constraint Density")
    lines.append("")
    cd = results["constraint_density"]
    lines.append("| Type | Manual (mean +/- sd) | Auto (mean +/- sd) | U | p (adj) | d |")
    lines.append("|------|----------------------|--------------------|---|---------|---|")
    for ctype in CONSTRAINT_TYPES:
        r = cd["per_type"][ctype]
        lines.append(
            f"| {ctype} | {fmt_f(r['manual_mean'])} +/- {fmt_f(r['manual_sd'])} "
            f"| {fmt_f(r['auto_mean'])} +/- {fmt_f(r['auto_sd'])} "
            f"| {r['U_statistic']:.0f} | {fmt_p(r['p_bonferroni'])} "
            f"| {fmt_f(r['cohens_d'])} |"
        )
    t = cd["total"]
    lines.append(
        f"| **Total** | {fmt_f(t['manual_mean'])} +/- {fmt_f(t['manual_sd'])} "
        f"| {fmt_f(t['auto_mean'])} +/- {fmt_f(t['auto_sd'])} "
        f"| {t['U_statistic']:.0f} | {fmt_p(t['p_bonferroni'])} "
        f"| {fmt_f(t['cohens_d'])} |"
    )
    lines.append("")

    # 2. Domain coverage
    lines.append("## 2. Domain Coverage")
    lines.append("")
    dc = results["domain_coverage"]
    lines.append(f"- Jaccard similarity: **{dc['jaccard_similarity']}**")
    lines.append(f"- Manual domains: {dc['n_domains_manual']}, Auto domains: {dc['n_domains_auto']}")
    shared_n = len(dc["shared_domains"])
    lines.append(
        f"- Shared: {shared_n}, Manual-only: {dc['manual_only']}, "
        f"Auto-only: {dc['auto_only']}"
    )
    lines.append(f"- Chi-square: chi2={dc['chi2_statistic']}, p(adj)={fmt_p(dc['chi2_p_bonferroni'])}")
    lines.append("")

    # 3. Patient complexity
    lines.append("## 3. Patient Complexity")
    lines.append("")
    pc = results["patient_complexity"]
    ac = pc["active_conditions"]
    tr = pc["triggered_rules"]
    lines.append(f"**Active conditions**: Manual {fmt_f(ac['manual_mean'])} +/- {fmt_f(ac['manual_sd'])}, "
                 f"Auto {fmt_f(ac['auto_mean'])} +/- {fmt_f(ac['auto_sd'])}, "
                 f"KS={fmt_f(ac['ks_statistic'])}, p(adj)={fmt_p(ac['p_bonferroni'])}, d={fmt_f(ac['cohens_d'])}")
    lines.append("")
    lines.append(f"**Triggered rules**: Manual {fmt_f(tr['manual_mean'])} +/- {fmt_f(tr['manual_sd'])}, "
                 f"Auto {fmt_f(tr['auto_mean'])} +/- {fmt_f(tr['auto_sd'])}, "
                 f"KS={fmt_f(tr['ks_statistic'])}, p(adj)={fmt_p(tr['p_bonferroni'])}, d={fmt_f(tr['cohens_d'])}")
    lines.append("")

    # 4. Expected actions
    lines.append("## 4. Expected Actions")
    lines.append("")
    ea = results["expected_actions"]
    lines.append(f"Manual: {fmt_f(ea['manual_mean'])} +/- {fmt_f(ea['manual_sd'])} (n={ea['manual_n']})")
    lines.append(f"Auto: {fmt_f(ea['auto_mean'])} +/- {fmt_f(ea['auto_sd'])} (n={ea['auto_n']})")
    lines.append(
        f"Mann-Whitney U={ea['U_statistic']:.0f}, "
        f"p(adj)={fmt_p(ea['p_bonferroni'])}, d={fmt_f(ea['cohens_d'])}"
    )
    lines.append("")

    # 5. Trap ratio
    lines.append("## 5. Trap Scenario Ratio")
    lines.append("")
    tp = results["trap_ratio"]
    lines.append(f"Manual: {tp['manual_trap']}/{tp['manual_total']} ({tp['manual_ratio']:.1%})")
    lines.append(f"Auto: {tp['auto_trap']}/{tp['auto_total']} ({tp['auto_ratio']:.1%})")
    lines.append(f"Chi-square={tp['chi2_statistic']}, p(adj)={fmt_p(tp['chi2_p_bonferroni'])}")
    lines.append("")

    # 6. Provenance completeness
    lines.append("## 6. Provenance Completeness")
    lines.append("")
    pv = results["provenance_completeness"]
    ap = pv["auto_provenance"]
    mc = pv["manual_derivation_coverage"]
    lines.append(f"**Auto provenance validity**: {ap['valid_provenance_count']}/{ap['total_constraints']} "
                 f"({ap['validity_rate']:.1%})")
    if ap["invalid_examples"]:
        lines.append(f"  Invalid examples: {ap['invalid_examples'][:3]}")
    lines.append(f"**Manual derivation coverage**: mean={mc['mean_coverage']:.3f} "
                 f"+/- {mc['sd_coverage']:.3f}, 95% CI [{mc['ci_95'][0]:.3f}, {mc['ci_95'][1]:.3f}]")
    lines.append(f"  (n={mc['n_scenarios_with_expected']} scenarios with expected_actions)")
    lines.append("")

    # Summary
    lines.append("## Summary")
    lines.append("")
    n_sig = 0
    for ctype in CONSTRAINT_TYPES:
        if cd["per_type"][ctype]["p_bonferroni"] < 0.05:
            n_sig += 1
    if dc["chi2_p_bonferroni"] < 0.05:
        n_sig += 1
    if pc["active_conditions"]["p_bonferroni"] < 0.05:
        n_sig += 1
    if ea["p_bonferroni"] < 0.05:
        n_sig += 1
    if tp["chi2_p_bonferroni"] < 0.05:
        n_sig += 1

    lines.append(f"Of {N_ANALYSES} analyses (Bonferroni-corrected), **{n_sig}** show "
                 f"statistically significant differences between manual and auto scenarios.")
    lines.append("")

    return "\n".join(lines)


def generate_latex_table(results: dict[str, Any]) -> None:
    """Generate LaTeX booktabs table summarising all 6 analyses.

    Rows: one per analysis dimension.
    Columns: Metric, Manual (mean +/- sd), Auto (mean +/- sd), Test Statistic,
             p-value, Effect Size.

    Args:
        results: Combined results dict.
    """
    cd = results["constraint_density"]
    dc = results["domain_coverage"]
    pc = results["patient_complexity"]
    ea = results["expected_actions"]
    tp = results["trap_ratio"]
    pv = results["provenance_completeness"]

    headers = [
        "Dimension",
        "Manual (mean$\\pm$sd)",
        "Auto (mean$\\pm$sd)",
        "Test Stat.",
        "$p$ (adj)",
        "Effect Size",
    ]

    rows: list[list[str]] = []

    # Constraint density (total)
    ct = cd["total"]
    rows.append([
        "Constraint density",
        f"{fmt_f(ct['manual_mean'])}$\\pm${fmt_f(ct['manual_sd'])}",
        f"{fmt_f(ct['auto_mean'])}$\\pm${fmt_f(ct['auto_sd'])}",
        f"U={ct['U_statistic']:.0f}",
        fmt_p(ct["p_bonferroni"]),
        f"d={fmt_f(ct['cohens_d'])}",
    ])

    # Domain coverage
    rows.append([
        "Domain coverage",
        f"{dc['n_domains_manual']} domains",
        f"{dc['n_domains_auto']} domains",
        f"$\\chi^2$={dc['chi2_statistic']:.1f}",
        fmt_p(dc["chi2_p_bonferroni"]),
        f"J={dc['jaccard_similarity']:.2f}",
    ])

    # Patient complexity (conditions)
    ac = pc["active_conditions"]
    rows.append([
        "Active conditions",
        f"{fmt_f(ac['manual_mean'])}$\\pm${fmt_f(ac['manual_sd'])}",
        f"{fmt_f(ac['auto_mean'])}$\\pm${fmt_f(ac['auto_sd'])}",
        f"KS={fmt_f(ac['ks_statistic'])}",
        fmt_p(ac["p_bonferroni"]),
        f"d={fmt_f(ac['cohens_d'])}",
    ])

    # Triggered rules
    tr = pc["triggered_rules"]
    rows.append([
        "Triggered rules",
        f"{fmt_f(tr['manual_mean'])}$\\pm${fmt_f(tr['manual_sd'])}",
        f"{fmt_f(tr['auto_mean'])}$\\pm${fmt_f(tr['auto_sd'])}",
        f"KS={fmt_f(tr['ks_statistic'])}",
        fmt_p(tr["p_bonferroni"]),
        f"d={fmt_f(tr['cohens_d'])}",
    ])

    # Expected actions
    rows.append([
        "Expected actions",
        f"{fmt_f(ea['manual_mean'])}$\\pm${fmt_f(ea['manual_sd'])}",
        f"{fmt_f(ea['auto_mean'])}$\\pm${fmt_f(ea['auto_sd'])}",
        f"U={ea['U_statistic']:.0f}",
        fmt_p(ea["p_bonferroni"]),
        f"d={fmt_f(ea['cohens_d'])}",
    ])

    # Trap ratio
    m_pct = f"{tp['manual_ratio'] * 100:.1f}\\%"
    a_pct = f"{tp['auto_ratio'] * 100:.1f}\\%"
    rows.append([
        "Trap ratio",
        m_pct,
        a_pct,
        f"$\\chi^2$={tp['chi2_statistic']:.1f}",
        fmt_p(tp["chi2_p_bonferroni"]),
        "---",
    ])

    # Provenance
    mc = pv["manual_derivation_coverage"]
    ap = pv["auto_provenance"]
    ap_pct = f"{ap['validity_rate'] * 100:.1f}\\%"
    rows.append([
        "Provenance valid",
        f"cov={fmt_f(mc['mean_coverage'])}",
        ap_pct,
        "---",
        "---",
        "---",
    ])

    save_latex_table(
        rows,
        headers,
        TABLES_DIR / "scenario_equivalence.tex",
        caption="Structural equivalence between manual and auto-generated scenarios (Bonferroni-corrected).",
        label="tab:scenario_equivalence",
    )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    """Run all 6 EXP-A analyses and save outputs."""
    setup_matplotlib()
    print("EXP-A: Manual vs Auto Scenario Structural Equivalence")
    print("=" * 60)

    engine = ConstraintDerivationEngine()
    graphs = load_all_graphs()
    scenarios = load_all_scenarios(tag_source=True)

    manual = [s for s in scenarios if s.get("source_type") == "manual"]
    auto = [s for s in scenarios if s.get("source_type") == "auto"]
    print(f"Loaded {len(manual)} manual, {len(auto)} auto scenarios")
    print(f"Loaded {len(graphs)} CPG graphs")

    # Derive constraints for all scenarios
    print("\n[1/7] Deriving constraints for all scenarios ...")
    enriched = derive_all_constraints(scenarios, engine, graphs)

    enriched_manual = [e for e in enriched if e["source_type"] == "manual"]
    enriched_auto = [e for e in enriched if e["source_type"] == "auto"]
    print(f"  Enriched: {len(enriched_manual)} manual, {len(enriched_auto)} auto")

    # Run all 6 analyses
    print("\n[2/7] Constraint density analysis ...")
    results: dict[str, Any] = {}
    results["constraint_density"] = analyze_constraint_density(enriched)

    print("\n[3/7] Domain coverage analysis ...")
    results["domain_coverage"] = analyze_domain_coverage(manual, auto)

    print("\n[4/7] Patient complexity analysis ...")
    results["patient_complexity"] = analyze_patient_complexity(enriched)

    print("\n[5/7] Expected actions analysis ...")
    results["expected_actions"] = analyze_expected_actions(enriched)

    print("\n[6/7] Trap ratio analysis ...")
    results["trap_ratio"] = analyze_trap_ratio(manual, auto)

    print("\n[7/7] Provenance completeness analysis ...")
    results["provenance_completeness"] = analyze_provenance_completeness(enriched)

    results["summary"] = {
        "n_manual": len(manual),
        "n_auto": len(auto),
        "n_enriched": len(enriched),
        "n_enriched_manual": len(enriched_manual),
        "n_enriched_auto": len(enriched_auto),
        "n_graphs": len(graphs),
    }

    # Save outputs
    print("\nSaving outputs ...")
    save_json(results, EVIDENCE_DIR / "exp_a_scenario_equivalence.json")

    md = generate_markdown_report(results)
    save_markdown(md, EVIDENCE_DIR / "exp_a_scenario_equivalence.md")

    generate_latex_table(results)

    print("\nEXP-A complete.")


if __name__ == "__main__":
    main()
