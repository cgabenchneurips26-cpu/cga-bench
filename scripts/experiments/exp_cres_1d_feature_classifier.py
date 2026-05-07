#!/usr/bin/env python3
"""CRES-1D: Structural Feature Classifier

Extracts ~60 catalogue-free trace features from episode traces and trains a
GradientBoostingClassifier to predict the TCC verdict (has_hard_violation).
Uses 5-fold stratified CV AUC. Computes SHAP feature importance. Compares
a full-feature model against an ASC-only baseline (bag-of-actions count) to
show that ASC misses temporal structure captured by the richer feature set.

Outputs:
    evidence_pack/cres_1d/
        cres_1d_results.json   -- AUC scores, top features, SHAP ranking, CI
        cres_1d_macros.tex     -- LaTeX macros

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/exp_cres_1d_feature_classifier.py
"""

from __future__ import annotations

import logging
from pathlib import Path
import sys
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._common import save_json  # noqa: E402
from scripts.experiments._episode_cache import (  # noqa: E402
    EVIDENCE_DIR,
    load_cached_episodes,
    score_episode,
)

logger = logging.getLogger(__name__)

OUTPUT_DIR = EVIDENCE_DIR / "cres_1d"

# ---------------------------------------------------------------------------
# Feature extraction
# ---------------------------------------------------------------------------

VIOLATION_TYPES_CANONICAL = ("omission", "commission", "timing", "sequence", "deviation")


def _normalize_action(action_id: str) -> str:
    return action_id.strip().lower().replace("-", "_").replace(" ", "_")


def _extract_performed_list(ep: dict[str, Any]) -> list[str]:
    """Extract ordered list of performed action IDs (preserving order)."""
    result: list[str] = []
    for a in ep.get("actions", []):
        aid = a.get("action_id", "") if isinstance(a, dict) else str(a)
        if aid:
            result.append(_normalize_action(aid))
    return result


def _extract_expected_set(ep: dict[str, Any]) -> set[str]:
    result: set[str] = set()
    for a in ep.get("expected_actions", []):
        aid = a.get("action_id", "") if isinstance(a, dict) else str(a)
        if aid:
            result.add(_normalize_action(aid))
    return result


def _extract_timestamps(ep: dict[str, Any]) -> list[float]:
    """Extract action timestamps; fall back to index * 5 if missing."""
    timestamps: list[float] = []
    for i, a in enumerate(ep.get("actions", [])):
        if isinstance(a, dict):
            ts = a.get("timestamp_minutes")
            if ts is not None:
                try:
                    timestamps.append(float(ts))
                    continue
                except (TypeError, ValueError):
                    pass
        timestamps.append(float(i) * 5.0)
    return timestamps


def _kendall_tau_from_order(performed: list[str], expected_list: list[str]) -> float:
    """Compute Kendall tau between performed order and expected order.

    Maps each performed action that appears in expected to its index in
    expected, then computes Kendall tau of the resulting index sequence.
    Returns 0.0 when fewer than 2 matches exist.
    """
    expected_rank: dict[str, int] = {a: i for i, a in enumerate(expected_list)}
    matched_ranks: list[int] = []
    for a in performed:
        if a in expected_rank:
            matched_ranks.append(expected_rank[a])

    n = len(matched_ranks)
    if n < 2:
        return 0.0

    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            diff = matched_ranks[j] - matched_ranks[i]
            if diff > 0:
                concordant += 1
            elif diff < 0:
                discordant += 1
    total_pairs = n * (n - 1) // 2
    if total_pairs == 0:
        return 0.0
    return (concordant - discordant) / total_pairs


def _longest_increasing_subsequence_length(seq: list[int]) -> int:
    """Patience sorting LIS length in O(n log n)."""
    if not seq:
        return 0
    tails: list[int] = []
    import bisect

    for val in seq:
        pos = bisect.bisect_left(tails, val)
        if pos == len(tails):
            tails.append(val)
        else:
            tails[pos] = val
    return len(tails)


def extract_features(ep: dict[str, Any]) -> dict[str, float]:
    """Extract ~60 structural trace features from one episode dict.

    Groups:
      - action_count (~5)
      - timing (~15)
      - ordering (~10)
      - violation (~10)
      - dynamics (~10)
      - coverage (~5)
      - asc_only (~5, subset of above for ASC baseline)

    All NaN-prone values are guarded and replaced with 0.0.
    """
    performed_list = _extract_performed_list(ep)
    performed_set = set(performed_list)
    expected_set = _extract_expected_set(ep)
    timestamps = _extract_timestamps(ep)

    n_actions = len(performed_list)
    n_expected = len(expected_set)
    n_performed_not_expected = len(performed_set - expected_set)
    n_expected_not_performed = len(expected_set - performed_set)
    tp = len(performed_set & expected_set)
    coverage = tp / n_expected if n_expected > 0 else 1.0
    precision = tp / len(performed_set) if performed_set else 0.0
    recall = coverage
    f1 = 2.0 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    union_size = len(performed_set | expected_set)
    jaccard = tp / union_size if union_size > 0 else 1.0

    # ------------------------------------------------------------------
    # Timing features
    # ------------------------------------------------------------------
    if timestamps:
        ts_arr = np.array(timestamps)
        time_mean = float(np.mean(ts_arr))
        time_std = float(np.std(ts_arr)) if len(ts_arr) > 1 else 0.0
        time_min = float(np.min(ts_arr))
        time_max = float(np.max(ts_arr))
        time_span = time_max - time_min
        time_first = time_min
        time_last = time_max

        if len(ts_arr) > 1:
            gaps = np.diff(ts_arr)
            mean_gap = float(np.mean(gaps))
            std_gap = float(np.std(gaps)) if len(gaps) > 1 else 0.0
        else:
            mean_gap = 0.0
            std_gap = 0.0

        # Fraction of actions in each quartile of elapsed time
        if time_span > 0:
            q1 = time_min + 0.25 * time_span
            q2 = time_min + 0.50 * time_span
            q3 = time_min + 0.75 * time_span
            frac_q1 = float(np.mean(ts_arr <= q1))
            frac_q2 = float(np.mean((ts_arr > q1) & (ts_arr <= q2)))
            frac_q3 = float(np.mean((ts_arr > q2) & (ts_arr <= q3)))
            frac_q4 = float(np.mean(ts_arr > q3))
        else:
            frac_q1 = frac_q2 = frac_q3 = frac_q4 = 0.25

        # Number of "jumps": inter-action gaps > 2x mean
        if mean_gap > 0 and len(ts_arr) > 1:
            n_jumps = int(np.sum(np.diff(ts_arr) > 2.0 * mean_gap))
        else:
            n_jumps = 0
    else:
        time_mean = time_std = time_min = time_max = 0.0
        time_span = time_first = time_last = 0.0
        mean_gap = std_gap = 0.0
        frac_q1 = frac_q2 = frac_q3 = frac_q4 = 0.0
        n_jumps = 0

    # ------------------------------------------------------------------
    # Ordering features
    # ------------------------------------------------------------------
    expected_list = sorted(expected_set)  # canonical ordering by name

    # Count out-of-order action pairs: pairs (i,j) where i<j in performed
    # but action at i comes after action at j in expected order
    expected_rank_map: dict[str, int] = {a: idx for idx, a in enumerate(expected_list)}
    performed_expected_ranks: list[int] = [expected_rank_map[a] for a in performed_list if a in expected_rank_map]
    n_out_of_order = 0
    n_ordered_pairs = len(performed_expected_ranks)
    for i in range(n_ordered_pairs):
        for j in range(i + 1, n_ordered_pairs):
            if performed_expected_ranks[i] > performed_expected_ranks[j]:
                n_out_of_order += 1

    total_ordering_pairs = n_ordered_pairs * (n_ordered_pairs - 1) // 2
    out_of_order_ratio = n_out_of_order / total_ordering_pairs if total_ordering_pairs > 0 else 0.0

    kendall_tau = _kendall_tau_from_order(performed_list, expected_list)

    lis_len = _longest_increasing_subsequence_length(performed_expected_ranks)
    lis_ratio = lis_len / n_ordered_pairs if n_ordered_pairs > 0 else 0.0

    # ------------------------------------------------------------------
    # Violation features
    # ------------------------------------------------------------------
    violation_events = ep.get("violation_events", []) or []
    vtype_counts: dict[str, int] = dict.fromkeys(VIOLATION_TYPES_CANONICAL, 0)
    severity_values: list[float] = []
    n_hard = 0

    for v in violation_events:
        if not isinstance(v, dict):
            continue
        raw_type = str(v.get("violation_type", v.get("type", ""))).lower().strip()
        for canonical in VIOLATION_TYPES_CANONICAL:
            if canonical in raw_type:
                vtype_counts[canonical] += 1
                if canonical in ("commission", "timing", "sequence"):
                    n_hard += 1
                break

        # Severity numeric extraction
        raw_sev = v.get("severity")
        if raw_sev is not None:
            if isinstance(raw_sev, (int, float)):
                severity_values.append(float(raw_sev))
            elif isinstance(raw_sev, str):
                sev_map = {
                    "minor": 0.1,
                    "moderate": 0.4,
                    "major": 0.7,
                    "severe": 0.9,
                    "catastrophic": 1.0,
                }
                sv = sev_map.get(raw_sev.lower().strip())
                if sv is not None:
                    severity_values.append(sv)

    n_violations_total = len(violation_events)
    frac_hard = n_hard / n_violations_total if n_violations_total > 0 else 0.0
    max_severity = max(severity_values) if severity_values else 0.0
    mean_severity = sum(severity_values) / len(severity_values) if severity_values else 0.0

    # ------------------------------------------------------------------
    # Dynamics features
    # ------------------------------------------------------------------
    # Action type diversity: unique action types / total (type = prefix before first underscore)
    action_types: list[str] = []
    for a in performed_list:
        parts = a.split("_")
        action_types.append(parts[0] if parts else a)

    n_unique_types = len(set(action_types))
    action_type_diversity = n_unique_types / n_actions if n_actions > 0 else 0.0

    # Repeated action fraction (performed same action_id more than once)
    from collections import Counter as _Counter

    performed_counts = _Counter(performed_list)
    n_repeated = sum(1 for cnt in performed_counts.values() if cnt > 1)
    repeated_fraction = n_repeated / n_actions if n_actions > 0 else 0.0

    # Early-action bias: mandatory (expected) actions performed in first half of timestamps
    mandatory_performed = [a for a in performed_list if a in expected_set]
    if mandatory_performed and timestamps and time_span > 0:
        midpoint = time_min + 0.5 * time_span
        n_mandatory_early = sum(
            1
            for i, a in enumerate(performed_list)
            if a in expected_set and i < len(timestamps) and timestamps[i] <= midpoint
        )
        early_action_bias = n_mandatory_early / len(mandatory_performed)
    else:
        early_action_bias = 0.5

    # Late-action fraction: fraction of all actions in last quarter of episode
    late_action_fraction = frac_q4

    # Medication-before-lab ordering score: fraction of (med, lab) pairs where
    # medication action appears before lab order in the sequence.
    med_indices: list[int] = []
    lab_indices: list[int] = []
    for i, a in enumerate(performed_list):
        if a.startswith(("give_", "start_", "administer_", "initiate_")):
            med_indices.append(i)
        elif a.startswith(("order_lab", "order_imaging", "collect_")):
            lab_indices.append(i)

    if med_indices and lab_indices:
        pairs_checked = 0
        pairs_med_before_lab = 0
        for mi in med_indices:
            for li in lab_indices:
                pairs_checked += 1
                if mi < li:
                    pairs_med_before_lab += 1
        med_before_lab_score = pairs_med_before_lab / pairs_checked if pairs_checked > 0 else 0.5
    else:
        med_before_lab_score = 0.5

    # Action burst density: fraction of consecutive same-type action pairs
    burst_count = 0
    for i in range(len(action_types) - 1):
        if action_types[i] == action_types[i + 1]:
            burst_count += 1
    burst_density = burst_count / (n_actions - 1) if n_actions > 1 else 0.0

    # ------------------------------------------------------------------
    # Assemble feature dict
    # ------------------------------------------------------------------
    features: dict[str, float] = {
        # Action count features
        "n_actions": float(n_actions),
        "n_expected": float(n_expected),
        "n_performed_not_expected": float(n_performed_not_expected),
        "n_expected_not_performed": float(n_expected_not_performed),
        "coverage_ratio": coverage,
        # Timing features
        "time_mean": time_mean,
        "time_std": time_std,
        "time_min": time_min,
        "time_max": time_max,
        "time_span": time_span,
        "mean_inter_action_gap": mean_gap,
        "std_inter_action_gap": std_gap,
        "time_first_action": time_first,
        "time_last_action": time_last,
        "frac_actions_q1": frac_q1,
        "frac_actions_q2": frac_q2,
        "frac_actions_q3": frac_q3,
        "frac_actions_q4": frac_q4,
        "n_timing_jumps": float(n_jumps),
        # Ordering features
        "n_out_of_order_pairs": float(n_out_of_order),
        "out_of_order_ratio": out_of_order_ratio,
        "kendall_tau": kendall_tau,
        "lis_ratio": lis_ratio,
        "lis_length": float(lis_len),
        "n_ordered_pairs": float(n_ordered_pairs),
        "n_ordering_pairs_total": float(total_ordering_pairs),
        "ordering_concordance": max(0.0, kendall_tau),
        "ordering_discordance": max(0.0, -kendall_tau),
        "expected_rank_coverage": (n_ordered_pairs / n_expected if n_expected > 0 else 0.0),
        # Violation features
        "n_violations_total": float(n_violations_total),
        "n_omission": float(vtype_counts["omission"]),
        "n_commission": float(vtype_counts["commission"]),
        "n_timing_viol": float(vtype_counts["timing"]),
        "n_sequence": float(vtype_counts["sequence"]),
        "n_deviation": float(vtype_counts["deviation"]),
        "n_hard_violations": float(n_hard),
        "frac_hard_violations": frac_hard,
        "max_violation_severity": max_severity,
        "mean_violation_severity": mean_severity,
        # Dynamics features
        "action_type_diversity": action_type_diversity,
        "n_unique_action_types": float(n_unique_types),
        "repeated_action_fraction": repeated_fraction,
        "early_action_bias": early_action_bias,
        "late_action_fraction": late_action_fraction,
        "med_before_lab_score": med_before_lab_score,
        "burst_density": burst_density,
        "n_med_actions": float(len(med_indices)),
        "n_lab_actions": float(len(lab_indices)),
        "n_mandatory_performed": float(len(mandatory_performed)),
        # Coverage features
        "coverage": coverage,
        "f1": f1,
        "precision": precision,
        "recall": recall,
        "jaccard": jaccard,
        # ASC-only features (for baseline comparison)
        "asc_coverage": coverage,
        "asc_n_actions": float(n_actions),
        "asc_n_expected": float(n_expected),
        "asc_precision": precision,
        "asc_recall": recall,
    }

    # Replace any NaN / inf values with 0.0
    for key in list(features.keys()):
        val = features[key]
        if not np.isfinite(val):
            features[key] = 0.0

    return features


# ---------------------------------------------------------------------------
# ASC-only feature names
# ---------------------------------------------------------------------------

ASC_FEATURE_NAMES: list[str] = [
    "asc_coverage",
    "asc_n_actions",
    "asc_n_expected",
    "asc_precision",
    "asc_recall",
]

# ---------------------------------------------------------------------------
# Violation features that LEAK the label (must be excluded from clean model)
# ---------------------------------------------------------------------------
# The label is `has_hard_violation = (n_hard_violations > 0)` where hard types
# are {commission, timing, sequence}.  ALL violation-group features are derived
# from the assessor's post-hoc violation extraction and mechanically encode
# the label.  Including them produces AUC=1.0 — a tautological artefact,
# not meaningful prediction.
#
# The defense claim ("structural trace features predict TCC compliance") must
# use ONLY agent-observable features: what actions were taken, when, in what
# order, and how they relate to the expected action set.
# ---------------------------------------------------------------------------

VIOLATION_FEATURE_NAMES: list[str] = [
    "n_violations_total",
    "n_omission",
    "n_commission",
    "n_timing_viol",
    "n_sequence",
    "n_deviation",
    "n_hard_violations",
    "frac_hard_violations",
    "max_violation_severity",
    "mean_violation_severity",
]

# ---------------------------------------------------------------------------
# Coverage-adjacent features that constitute indirect leakage
# ---------------------------------------------------------------------------
# Coverage ≈ overlap with expected actions.  The TCC verdict (has_hard_violation)
# correlates strongly with coverage because agents that miss many expected actions
# accumulate OMISSION violations.  Including coverage-derived features therefore
# allows the model to recover the label through a one-hop proxy path:
#   n_expected_not_performed → OMISSION count → TCC fail
#
# The coverage_free_model removes these in addition to VIOLATION_FEATURE_NAMES
# to test whether genuine temporal/ordering structure drives AUC.  If AUC
# remains high (>0.90) the claim holds; if it collapses to ~ASC-level the
# ordering features were carrying very little independent signal.
# ---------------------------------------------------------------------------

COVERAGE_FEATURE_NAMES: list[str] = [
    "coverage_ratio",
    "coverage",
    "f1",
    "precision",
    "recall",
    "jaccard",
    "asc_coverage",
    "asc_n_actions",
    "asc_n_expected",
    "asc_precision",
    "asc_recall",
    "n_expected_not_performed",
    "n_performed_not_expected",
    "expected_rank_coverage",  # n_ordered_pairs / n_expected — coverage proxy
    "n_mandatory_performed",  # count of expected actions performed = coverage numerator
    "n_expected",  # denominator of coverage
]

# ---------------------------------------------------------------------------
# Build feature matrix
# ---------------------------------------------------------------------------


def build_feature_matrix(
    episodes: list[dict[str, Any]],
) -> tuple[np.ndarray, np.ndarray, list[str], list[dict[str, Any]]]:
    """Extract features and labels from episodes.

    Returns:
        X: (n_episodes, n_features) array
        y: (n_episodes,) binary label array (1=no hard violations, 0=has hard)
        feature_names: list of feature name strings
        scored: list of score dicts from score_episode()
    """
    all_features: list[dict[str, float]] = []
    scored: list[dict[str, Any]] = []

    for ep in episodes:
        feats = extract_features(ep)
        sc = score_episode(ep)
        all_features.append(feats)
        scored.append(sc)

    if not all_features:
        return np.zeros((0, 0)), np.zeros(0), [], []

    feature_names = list(all_features[0].keys())
    X = np.array([[f.get(name, 0.0) for name in feature_names] for f in all_features])
    y = np.array([0 if sc["v4_hard"] else 1 for sc in scored])

    # Replace any remaining NaN / inf
    X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

    return X, y, feature_names, scored


# ---------------------------------------------------------------------------
# Classifier training and evaluation
# ---------------------------------------------------------------------------


def run_cv_auc(
    X: np.ndarray,
    y: np.ndarray,
    feature_indices: list[int] | None = None,
) -> tuple[float, float, list[float]]:
    """Run 5-fold stratified CV and return (mean_auc, std_auc, fold_aucs).

    Args:
        X: Full feature matrix.
        y: Label vector.
        feature_indices: If provided, use only these column indices.
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import roc_auc_score
    from sklearn.model_selection import StratifiedKFold

    X_subset = X[:, feature_indices] if feature_indices is not None else X

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    clf = GradientBoostingClassifier(n_estimators=200, max_depth=5, random_state=42)

    fold_aucs: list[float] = []
    for train_idx, val_idx in skf.split(X_subset, y):
        X_train, X_val = X_subset[train_idx], X_subset[val_idx]
        y_train, y_val = y[train_idx], y[val_idx]
        clf.fit(X_train, y_train)
        y_prob = clf.predict_proba(X_val)[:, 1]
        try:
            auc = roc_auc_score(y_val, y_prob)
        except ValueError:
            auc = 0.5
        fold_aucs.append(float(auc))

    mean_auc = float(np.mean(fold_aucs))
    std_auc = float(np.std(fold_aucs))
    return mean_auc, std_auc, fold_aucs


def train_full_model(
    X: np.ndarray,
    y: np.ndarray,
) -> Any:
    """Train a GradientBoostingClassifier on the full dataset for SHAP analysis."""
    from sklearn.ensemble import GradientBoostingClassifier

    clf = GradientBoostingClassifier(n_estimators=200, max_depth=5, random_state=42)
    clf.fit(X, y)
    return clf


def compute_shap_importance(
    model: Any,
    X: np.ndarray,
    feature_names: list[str],
    n_background: int = 200,
) -> list[dict[str, Any]]:
    """Compute SHAP feature importance, returning top-20 by mean |SHAP|.

    Returns empty list if shap is not installed.
    """
    try:
        import shap  # type: ignore[import]
    except ImportError:
        logger.warning("shap not installed — skipping SHAP analysis")
        return []

    rng = np.random.default_rng(42)
    n = X.shape[0]
    bg_idx = rng.choice(n, size=min(n_background, n), replace=False)
    background = X[bg_idx]

    explainer = shap.TreeExplainer(model, background)
    shap_values = explainer.shap_values(X)

    # For binary classifiers shap_values may be list[array]; take positive class
    if isinstance(shap_values, list):
        sv_arr = shap_values[1] if len(shap_values) > 1 else shap_values[0]
    else:
        sv_arr = shap_values

    mean_abs_shap = np.mean(np.abs(sv_arr), axis=0)
    ranked_idx = np.argsort(mean_abs_shap)[::-1]

    top_features: list[dict[str, Any]] = []
    for rank, idx in enumerate(ranked_idx[:20]):
        top_features.append(
            {
                "rank": rank + 1,
                "feature": feature_names[idx],
                "mean_abs_shap": float(mean_abs_shap[idx]),
            }
        )

    return top_features


# ---------------------------------------------------------------------------
# Bootstrap CI for AUC difference
# ---------------------------------------------------------------------------


def bootstrap_auc_delta_ci(
    X: np.ndarray,
    y: np.ndarray,
    full_indices: list[int],
    asc_indices: list[int],
    n_bootstrap: int = 1000,
    seed: int = 42,
) -> tuple[float, float]:
    """Bootstrap 95% CI for (full_AUC - ASC_AUC).

    Uses simple bootstrap of episode-level predictions from a model trained on
    the full dataset to keep runtime manageable.
    """
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.metrics import roc_auc_score

    clf_full = GradientBoostingClassifier(n_estimators=200, max_depth=5, random_state=42)
    clf_asc = GradientBoostingClassifier(n_estimators=200, max_depth=5, random_state=42)
    clf_full.fit(X[:, full_indices], y)
    clf_asc.fit(X[:, asc_indices], y)

    prob_full = clf_full.predict_proba(X[:, full_indices])[:, 1]
    prob_asc = clf_asc.predict_proba(X[:, asc_indices])[:, 1]

    rng = np.random.default_rng(seed)
    n = len(y)
    deltas: list[float] = []

    for _ in range(n_bootstrap):
        idx = rng.integers(0, n, size=n)
        y_boot = y[idx]
        if len(np.unique(y_boot)) < 2:
            continue
        try:
            auc_f = roc_auc_score(y_boot, prob_full[idx])
            auc_a = roc_auc_score(y_boot, prob_asc[idx])
            deltas.append(float(auc_f - auc_a))
        except ValueError:
            continue

    if not deltas:
        return (0.0, 0.0)

    deltas_arr = np.array(deltas)
    lo = float(np.percentile(deltas_arr, 2.5))
    hi = float(np.percentile(deltas_arr, 97.5))
    return lo, hi


# ---------------------------------------------------------------------------
# Output helpers
# ---------------------------------------------------------------------------


def write_macros(
    auc_full: float,
    auc_full_std: float,
    auc_asc: float,
    auc_asc_std: float,
    delta_auc: float,
    delta_ci: tuple[float, float],
    top_feature: str,
    n_episodes: int,
    n_features: int,
    output_path: Path,
    auc_covfree: float = 0.0,
    auc_covfree_std: float = 0.0,
    n_covfree_features: int = 0,
    delta_covfree_asc: float = 0.0,
    delta_covfree_asc_ci: tuple[float, float] = (0.0, 0.0),
) -> None:
    """Write LaTeX macros to file."""
    lines = [
        "% CRES-1D: Structural Feature Classifier (leakage-clean v3) — auto-generated macros",
        "% DO NOT EDIT — regenerate with exp_cres_1d_feature_classifier.py",
        "% v2: removed 10 violation features that mechanically encoded the label",
        "% v3: added coverage_free_model (removes coverage-adjacent features too)",
        "",
        f"\\newcommand{{\\cresOneDNEpisodes}}{{{n_episodes}}}",
        f"\\newcommand{{\\cresOneDNFeatures}}{{{n_features}}}",
        f"\\newcommand{{\\cresOneDAUCFull}}{{{auc_full:.3f}}}",
        f"\\newcommand{{\\cresOneDAUCFullStd}}{{{auc_full_std:.3f}}}",
        f"\\newcommand{{\\cresOneDAUCASC}}{{{auc_asc:.3f}}}",
        f"\\newcommand{{\\cresOneDAUCASCStd}}{{{auc_asc_std:.3f}}}",
        f"\\newcommand{{\\cresOneDDeltaAUC}}{{{delta_auc:+.3f}}}",
        f"\\newcommand{{\\cresOneDDeltaAUCLo}}{{{delta_ci[0]:+.3f}}}",
        f"\\newcommand{{\\cresOneDDeltaAUCHi}}{{{delta_ci[1]:+.3f}}}",
        f"\\newcommand{{\\cresOneDTopFeature}}{{{_escape_latex(top_feature)}}}",
        "% Coverage-free model macros",
        f"\\newcommand{{\\cresOneDCovFreeAUC}}{{{auc_covfree:.3f}}}",
        f"\\newcommand{{\\cresOneDCovFreeStd}}{{{auc_covfree_std:.3f}}}",
        f"\\newcommand{{\\cresOneDCovFreeNFeatures}}{{{n_covfree_features}}}",
        f"\\newcommand{{\\cresOneDDeltaCovFreeASC}}{{{delta_covfree_asc:+.3f}}}",
        f"\\newcommand{{\\cresOneDDeltaCovFreeASCLo}}{{{delta_covfree_asc_ci[0]:+.3f}}}",
        f"\\newcommand{{\\cresOneDDeltaCovFreeASCHi}}{{{delta_covfree_asc_ci[1]:+.3f}}}",
        "",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    print(f"  Saved: {output_path}")


def _escape_latex(text: str) -> str:
    """Escape underscores for LaTeX."""
    return text.replace("_", r"\_")


def print_summary(
    auc_full: float,
    auc_full_std: float,
    auc_asc: float,
    auc_asc_std: float,
    delta_auc: float,
    delta_ci: tuple[float, float],
    top_features: list[dict[str, Any]],
    fold_aucs_full: list[float],
    fold_aucs_asc: list[float],
) -> None:
    print()
    print("=" * 70)
    print("CRES-1D: STRUCTURAL FEATURE CLASSIFIER — RESULTS")
    print("=" * 70)
    print(f"  Full model AUC (5-fold):  {auc_full:.4f} ± {auc_full_std:.4f}")
    print(f"  Fold AUCs (full):         {[f'{a:.4f}' for a in fold_aucs_full]}")
    print(f"  ASC-only AUC (5-fold):   {auc_asc:.4f} ± {auc_asc_std:.4f}")
    print(f"  Fold AUCs (ASC):          {[f'{a:.4f}' for a in fold_aucs_asc]}")
    print(f"  Delta AUC (full - ASC):  {delta_auc:+.4f}  95% CI [{delta_ci[0]:+.4f}, {delta_ci[1]:+.4f}]")
    if top_features:
        print()
        print("  Top-10 features by mean |SHAP|:")
        for feat in top_features[:10]:
            print(f"    {feat['rank']:2d}. {feat['feature']:<40s}  {feat['mean_abs_shap']:.6f}")
    print("=" * 70)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    print("=" * 70)
    print("CRES-1D: STRUCTURAL FEATURE CLASSIFIER")
    print("=" * 70)

    # ------------------------------------------------------------------
    # 1. Load episodes
    # ------------------------------------------------------------------
    print("  Loading episodes...")
    episodes = load_cached_episodes()
    print(f"  Loaded {len(episodes)} episodes")

    if not episodes:
        logger.error("No episodes found — aborting")
        sys.exit(1)

    # ------------------------------------------------------------------
    # 2. Build feature matrix
    # ------------------------------------------------------------------
    print("  Extracting features...")
    X, y, feature_names, scored = build_feature_matrix(episodes)
    n_episodes, n_features = X.shape
    print(f"  Feature matrix: {n_episodes} x {n_features}")
    print(f"  Label distribution: {int(y.sum())} pass (no hard), {int((1 - y).sum())} fail (has hard)")

    # Index maps
    asc_indices = [feature_names.index(name) for name in ASC_FEATURE_NAMES if name in feature_names]
    leaky_indices = list(range(n_features))  # original (includes violation features)

    # CLEAN model: exclude violation features that leak the label
    violation_idx_set = {feature_names.index(name) for name in VIOLATION_FEATURE_NAMES if name in feature_names}
    clean_indices = [i for i in range(n_features) if i not in violation_idx_set]
    clean_feature_names = [feature_names[i] for i in clean_indices]
    n_clean = len(clean_indices)
    n_removed = n_features - n_clean
    print(f"  Removed {n_removed} violation features → {n_clean} clean features")

    # COVERAGE-FREE model: also exclude coverage-adjacent features
    coverage_idx_set = {feature_names.index(name) for name in COVERAGE_FEATURE_NAMES if name in feature_names}
    covfree_idx_set = violation_idx_set | coverage_idx_set
    covfree_indices = [i for i in range(n_features) if i not in covfree_idx_set]
    covfree_feature_names = [feature_names[i] for i in covfree_indices]
    n_covfree = len(covfree_indices)
    n_covfree_removed = n_features - n_covfree
    print(f"  Removed {n_covfree_removed} violation+coverage features → {n_covfree} coverage-free features")

    # ------------------------------------------------------------------
    # 3. 5-fold CV AUC — CLEAN model (primary, no leakage)
    # ------------------------------------------------------------------
    print("  Running 5-fold CV (CLEAN model — no violation features)...")
    auc_clean, auc_clean_std, fold_aucs_clean = run_cv_auc(X, y, clean_indices)
    print(f"    Clean AUC: {auc_clean:.4f} ± {auc_clean_std:.4f}")

    # ------------------------------------------------------------------
    # 4. 5-fold CV AUC — ASC-only model
    # ------------------------------------------------------------------
    print("  Running 5-fold CV (ASC-only model)...")
    auc_asc, auc_asc_std, fold_aucs_asc = run_cv_auc(X, y, asc_indices)
    print(f"    ASC-only AUC: {auc_asc:.4f} ± {auc_asc_std:.4f}")

    delta_auc = auc_clean - auc_asc

    # ------------------------------------------------------------------
    # 4b. AUDIT: leaky full model (for comparison / audit trail only)
    # ------------------------------------------------------------------
    print("  Running 5-fold CV (LEAKY model — audit only)...")
    auc_leaky, auc_leaky_std, fold_aucs_leaky = run_cv_auc(X, y, leaky_indices)
    print(f"    Leaky AUC: {auc_leaky:.4f} ± {auc_leaky_std:.4f}  [AUDIT — label leaked]")

    # ------------------------------------------------------------------
    # 5. Train clean model for SHAP
    # ------------------------------------------------------------------
    print("  Training clean model for SHAP analysis...")
    X_clean = X[:, clean_indices]
    clean_model = train_full_model(X_clean, y)

    print("  Computing SHAP feature importance (clean)...")
    top_features = compute_shap_importance(clean_model, X_clean, clean_feature_names)

    # Fallback: use GBM built-in feature importance if SHAP unavailable
    gbm_importance: list[dict[str, Any]] = []
    if hasattr(clean_model, "feature_importances_"):
        importances = clean_model.feature_importances_
        ranked = np.argsort(importances)[::-1]
        for rank, idx in enumerate(ranked[:20]):
            gbm_importance.append(
                {
                    "rank": rank + 1,
                    "feature": clean_feature_names[idx],
                    "importance": float(importances[idx]),
                }
            )

    if not top_features and gbm_importance:
        print("    SHAP unavailable — using GBM built-in feature importance")

    top_feature_name = (
        top_features[0]["feature"]
        if top_features
        else gbm_importance[0]["feature"]
        if gbm_importance
        else clean_feature_names[0]
    )

    # ------------------------------------------------------------------
    # 5b. Coverage-free model: CV AUC + GBM importance
    # ------------------------------------------------------------------
    print("  Running 5-fold CV (COVERAGE-FREE model — no violation or coverage features)...")
    auc_covfree, auc_covfree_std, fold_aucs_covfree = run_cv_auc(X, y, covfree_indices)
    print(f"    Coverage-free AUC: {auc_covfree:.4f} ± {auc_covfree_std:.4f}")

    print("  Training coverage-free model for GBM feature importance...")
    X_covfree = X[:, covfree_indices]
    covfree_model = train_full_model(X_covfree, y)

    gbm_importance_covfree: list[dict[str, Any]] = []
    if hasattr(covfree_model, "feature_importances_"):
        importances_cf = covfree_model.feature_importances_
        ranked_cf = np.argsort(importances_cf)[::-1]
        for rank, idx in enumerate(ranked_cf[:20]):
            gbm_importance_covfree.append(
                {
                    "rank": rank + 1,
                    "feature": covfree_feature_names[idx],
                    "importance": float(importances_cf[idx]),
                }
            )

    # ------------------------------------------------------------------
    # 6. Bootstrap CI for delta AUC (clean - ASC)
    # ------------------------------------------------------------------
    print("  Computing bootstrap 95% CI for delta AUC (1000 resamples)...")
    delta_ci = bootstrap_auc_delta_ci(X, y, clean_indices, asc_indices, n_bootstrap=1000, seed=42)
    print(f"    Delta AUC 95% CI: [{delta_ci[0]:+.4f}, {delta_ci[1]:+.4f}]")

    # ------------------------------------------------------------------
    # 6b. Bootstrap CI for delta AUC (coverage_free - ASC)
    # ------------------------------------------------------------------
    print("  Computing bootstrap 95% CI for delta AUC (coverage_free - ASC, 1000 resamples)...")
    delta_covfree_asc_ci = bootstrap_auc_delta_ci(X, y, covfree_indices, asc_indices, n_bootstrap=1000, seed=42)
    delta_covfree_asc = auc_covfree - auc_asc
    print(
        f"    Coverage-free vs ASC delta: {delta_covfree_asc:+.4f}  "
        f"95% CI [{delta_covfree_asc_ci[0]:+.4f}, {delta_covfree_asc_ci[1]:+.4f}]"
    )

    # ------------------------------------------------------------------
    # 7. Print summary
    # ------------------------------------------------------------------
    print_summary(
        auc_clean,
        auc_clean_std,
        auc_asc,
        auc_asc_std,
        delta_auc,
        delta_ci,
        top_features,
        fold_aucs_clean,
        fold_aucs_asc,
    )

    # ------------------------------------------------------------------
    # 8. Save outputs
    # ------------------------------------------------------------------
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    results: dict[str, Any] = {
        "meta": {
            "experiment": "CRES-1D: Structural Feature Classifier (leakage-clean v3)",
            "n_episodes": n_episodes,
            "n_features_original": n_features,
            "n_features_clean": n_clean,
            "n_features_covfree": n_covfree,
            "n_violation_features_removed": n_removed,
            "n_covfree_features_removed": n_covfree_removed,
            "feature_names_clean": clean_feature_names,
            "feature_names_covfree": covfree_feature_names,
            "violation_features_removed": VIOLATION_FEATURE_NAMES,
            "coverage_features_removed": COVERAGE_FEATURE_NAMES,
            "asc_feature_names": ASC_FEATURE_NAMES,
            "classifier": "GradientBoostingClassifier(n_estimators=200, max_depth=5)",
            "cv": "StratifiedKFold(n_splits=5, shuffle=True, random_state=42)",
            "label": "TCC verdict: 1=no hard violations (pass), 0=has hard violations (fail)",
            "leakage_fix": (
                "v1 included 10 violation-count features derived from the assessor's "
                "post-hoc scoring output.  Since the label IS the violation verdict, "
                "these features mechanically encoded the label (AUC=1.0).  v2 removes "
                "all 10 violation features so only agent-observable trace features "
                "(actions, timing, ordering, coverage) remain.  v3 adds a "
                "coverage_free_model that also removes 16 coverage-adjacent features "
                "to isolate the contribution of pure temporal/ordering structure."
            ),
        },
        "label_distribution": {
            "n_pass": int(y.sum()),
            "n_fail": int((1 - y).sum()),
            "pass_rate": float(y.mean()),
        },
        "clean_model": {
            "auc_mean": round(auc_clean, 6),
            "auc_std": round(auc_clean_std, 6),
            "fold_aucs": [round(a, 6) for a in fold_aucs_clean],
            "n_features": n_clean,
            "feature_names_used": clean_feature_names,
        },
        "asc_only_model": {
            "auc_mean": round(auc_asc, 6),
            "auc_std": round(auc_asc_std, 6),
            "fold_aucs": [round(a, 6) for a in fold_aucs_asc],
            "feature_names_used": ASC_FEATURE_NAMES,
        },
        "coverage_free_model": {
            "description": (
                "Clean model with additional removal of 16 coverage-adjacent features "
                "(coverage_ratio, coverage, f1, precision, recall, jaccard, asc_*, "
                "n_expected_not_performed, n_performed_not_expected, "
                "expected_rank_coverage, n_mandatory_performed, n_expected). "
                "Tests whether pure temporal/ordering structure drives AUC."
            ),
            "auc_mean": round(auc_covfree, 6),
            "auc_std": round(auc_covfree_std, 6),
            "fold_aucs": [round(a, 6) for a in fold_aucs_covfree],
            "n_features": n_covfree,
            "feature_names_used": covfree_feature_names,
            "delta_vs_asc": {
                "point_estimate": round(delta_covfree_asc, 6),
                "ci_95_lo": round(delta_covfree_asc_ci[0], 6),
                "ci_95_hi": round(delta_covfree_asc_ci[1], 6),
                "bootstrap_n": 1000,
            },
            "gbm_feature_importance": gbm_importance_covfree,
        },
        "delta_auc": {
            "description": "clean_model AUC minus asc_only_model AUC",
            "point_estimate": round(delta_auc, 6),
            "ci_95_lo": round(delta_ci[0], 6),
            "ci_95_hi": round(delta_ci[1], 6),
            "bootstrap_n": 1000,
        },
        "leaky_audit": {
            "description": "AUDIT ONLY — original model with violation features (AUC=1.0 expected)",
            "auc_mean": round(auc_leaky, 6),
            "auc_std": round(auc_leaky_std, 6),
            "fold_aucs": [round(a, 6) for a in fold_aucs_leaky],
            "n_features": n_features,
        },
        "shap_top_features": top_features if top_features else [],
        "shap_available": len(top_features) > 0,
        "gbm_feature_importance": gbm_importance,
        "top_feature": top_feature_name,
    }

    save_json(results, OUTPUT_DIR / "cres_1d_results.json")

    write_macros(
        auc_full=auc_clean,
        auc_full_std=auc_clean_std,
        auc_asc=auc_asc,
        auc_asc_std=auc_asc_std,
        delta_auc=delta_auc,
        delta_ci=delta_ci,
        top_feature=top_feature_name,
        n_episodes=n_episodes,
        n_features=n_clean,
        output_path=OUTPUT_DIR / "cres_1d_macros.tex",
        auc_covfree=auc_covfree,
        auc_covfree_std=auc_covfree_std,
        n_covfree_features=n_covfree,
        delta_covfree_asc=delta_covfree_asc,
        delta_covfree_asc_ci=delta_covfree_asc_ci,
    )

    print(f"\n  Outputs written to: {OUTPUT_DIR}")
    print("CRES-1D complete.")


if __name__ == "__main__":
    main()
