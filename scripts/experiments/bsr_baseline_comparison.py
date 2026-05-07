
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""BSR Baseline Metric Comparison & Re-analysis.

Problem: Track A (r=0.861 with CGA) is too correlated → BSR underestimated.
Solution: Evaluate 3 candidate baselines, pick r < 0.5, re-run BSR.

Candidates:
  B1: Track A (action coverage) = |performed ∩ expected| / |expected|  [current]
  B2: Jaccard similarity = |performed ∩ expected| / |performed ∪ expected|  [set-only]
  B3: Binary task completion = 1 if Track A >= 0.7 else 0  [coarsened]

Key property:
  B2 (Jaccard) ignores timing, sequence, forbidden → orthogonal to CGA's
  process-quality dimensions (C3, C4, C5). It penalizes action overuse
  (large |performed|) which CGA does not weight heavily.

Usage:
    cd ${CGA_BENCH_ROOT}/cga_bench
    PYTHONPATH=${CGA_BENCH_ROOT} \
        python scripts/experiments/bsr_baseline_comparison.py
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
import glob
import json
import os
from pathlib import Path
import random

import matplotlib
from matplotlib.patches import Rectangle
import matplotlib.pyplot as plt
import numpy as np
from scipy import stats

matplotlib.use("Agg")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO = Path(__file__).resolve().parents[2]  # cga_bench/
ORIG_ROOT = _REPO / "results" / "clean_slate_20260331_210910"
RESC_ROOT = _REPO / "results" / "clean_slate_rescored"
OUT_ANALYSIS = _REPO / "evidence_pack" / "analysis"
OUT_FIGURES = _REPO / "evidence_pack" / "figures"
OUT_TABLES = _REPO / "evidence_pack" / "tables"

MODELS = ["oss120b", "qwen27b", "qwen35b", "qwen4b"]

EPSILON_DEFAULT = 0.05
DELTA_DEFAULT = 0.10
BINARY_THRESHOLD = 0.7

_OVERUSE_ACTIONS = [
    "order_lab_lipid_panel",
    "order_lab_thyroid",
    "order_imaging_mri_brain",
    "order_lab_uric_acid",
    "order_imaging_ct_abdomen",
]

random.seed(42)
np.random.seed(42)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------


@dataclass
class Episode:
    episode_id: str
    scenario_id: str
    model: str
    run_index: int
    actions: list[dict]
    expected_actions: list[str]
    forbidden_actions: list[str]
    violation_events_orig: list[dict]
    sub_scores_orig: dict[str, float]
    cga_score: float
    sub_scores: dict[str, float]
    total_violations: int
    violation_events: list[dict]


@dataclass
class PerturbedEpisode:
    episode_id: str
    perturbation: str
    applicable: bool
    skip_reason: str = ""
    baseline_orig: float = 0.0
    baseline_perturbed: float = 0.0
    cga_orig: float = 0.0
    cga_perturbed: float = 0.0
    sub_scores_orig: dict = field(default_factory=dict)
    sub_scores_perturbed: dict = field(default_factory=dict)
    perturbation_detail: str = ""


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _load_episodes() -> list[Episode]:
    episodes: list[Episode] = []
    for model in MODELS:
        orig_files = {
            os.path.basename(p): p for p in glob.glob(str(ORIG_ROOT / model / "*.json")) if "model_summary" not in p
        }
        resc_files = {
            os.path.basename(p): p for p in glob.glob(str(RESC_ROOT / model / "*.json")) if "model_summary" not in p
        }
        common = set(orig_files) & set(resc_files)
        for fname in sorted(common):
            with open(orig_files[fname]) as f:
                orig = json.load(f)
            with open(resc_files[fname]) as f:
                resc = json.load(f)
            ep = Episode(
                episode_id=fname.replace(".json", ""),
                scenario_id=orig.get("scenario_id", ""),
                model=model,
                run_index=int(orig.get("run_index", 0)),
                actions=orig.get("actions", []),
                expected_actions=orig.get("expected_actions", []),
                forbidden_actions=orig.get("forbidden_actions", []),
                violation_events_orig=orig.get("violation_events", []),
                sub_scores_orig=orig.get("sub_scores", {}),
                cga_score=resc.get("new_compliance_score", orig.get("compliance_score", 0.0)),
                sub_scores=resc.get("new_sub_scores", orig.get("sub_scores", {})),
                total_violations=resc.get("new_total_violations", orig.get("total_violations", 0)),
                violation_events=resc.get("new_violation_events", orig.get("violation_events", [])),
            )
            episodes.append(ep)
    return episodes


# ---------------------------------------------------------------------------
# Baseline metric functions
# ---------------------------------------------------------------------------


def _get_normalizer():
    """Lazy-load ActionNormalizer."""
    try:
        from cga_bench.assessor_core.action_normalizer import ActionNormalizer

        return ActionNormalizer()
    except Exception:
        return None


def _match_count(performed: list[str], expected: list[str], norm) -> int:
    """Count how many expected actions are matched by performed actions."""
    matched = 0
    for exp_act in expected:
        for perf_act in performed:
            if perf_act == exp_act or (norm and norm.are_aliases(perf_act, exp_act)):
                matched += 1
                break
    return matched


def compute_track_a(performed: list[str], expected: list[str], norm=None) -> float:
    """B1: Track A = |performed ∩ expected| / |expected|."""
    if not expected:
        return 1.0
    return _match_count(performed, expected, norm) / len(expected)


def compute_jaccard(performed: list[str], expected: list[str], norm=None) -> float:
    """B2: Jaccard = |performed ∩ expected| / |performed ∪ expected|.

    Uses unique action IDs (set semantics). Ignores timing and sequence.
    Penalizes both missing expected actions AND performing excess actions.
    """
    perf_set = set(performed)
    exp_set = set(expected)

    if not perf_set and not exp_set:
        return 1.0

    # Semantic matching: build intersection and union
    matched_perf = set()
    matched_exp = set()
    for exp_act in exp_set:
        for perf_act in perf_set:
            if perf_act == exp_act or (norm and norm.are_aliases(perf_act, exp_act)):
                matched_perf.add(perf_act)
                matched_exp.add(exp_act)
                break

    intersection_size = len(matched_exp)
    # Union = |perf_set| + |exp_set| - |intersection|
    union_size = len(perf_set) + len(exp_set) - intersection_size
    if union_size == 0:
        return 1.0
    return intersection_size / union_size


def compute_binary(performed: list[str], expected: list[str], norm=None) -> float:
    """B3: Binary task completion = 1.0 if Track A >= threshold else 0.0."""
    ta = compute_track_a(performed, expected, norm)
    return 1.0 if ta >= BINARY_THRESHOLD else 0.0


BASELINE_FUNCS: dict[str, Callable] = {
    "B1_TrackA": compute_track_a,
    "B2_Jaccard": compute_jaccard,
    "B3_Binary": compute_binary,
}


# ---------------------------------------------------------------------------
# CGA analytic update
# ---------------------------------------------------------------------------


def _cga_denom(n_actions: int, n_mandatory: int) -> int:
    return max(n_actions, n_mandatory, 1)


def _adjusted_cga(
    cga_orig: float,
    n_violations_orig: int,
    n_actions: int,
    n_mandatory: int,
    delta_violations: int,
    delta_actions: int,
) -> float:
    denom_new = _cga_denom(n_actions + delta_actions, n_mandatory)
    n_viol_new = n_violations_orig + delta_violations
    return max(0.0, 1.0 - n_viol_new / denom_new)


# ---------------------------------------------------------------------------
# Perturbation generators (baseline-agnostic)
# ---------------------------------------------------------------------------


def _perturb_p1_delay(
    ep: Episode,
    baseline_fn: Callable,
    norm,
) -> PerturbedEpisode:
    """P1: Delay an on-time action past its deadline. Action set unchanged."""
    n_actions = len(ep.actions)
    n_mandatory = len(ep.expected_actions)
    performed = [a["action_id"] for a in ep.actions]

    timing_deadlines: dict[str, float] = {}
    for v in ep.violation_events_orig:
        if v.get("violation_type") == "timing" and v.get("expected_deadline") is not None:
            timing_deadlines[v["action_involved"]] = float(v["expected_deadline"])

    already_violated = set(timing_deadlines.keys())
    target_action = None
    target_deadline = None

    for action_id, deadline in timing_deadlines.items():
        for a in ep.actions:
            aid = a["action_id"]
            if aid not in already_violated and a["timestamp"] <= deadline:
                target_action = aid
                target_deadline = deadline
                break
        if target_action:
            break

    if target_action is None:
        for a in sorted(ep.actions, key=lambda x: x["timestamp"]):
            if a["timestamp"] < 30.0:
                target_action = a["action_id"]
                target_deadline = 30.0
                break

    if target_action is None:
        return PerturbedEpisode(
            episode_id=ep.episode_id,
            perturbation="P1",
            applicable=False,
            skip_reason="no suitable action for delay",
        )

    # Baseline: same action set → same baseline value
    bl_orig = baseline_fn(performed, ep.expected_actions, norm)
    bl_pert = bl_orig  # action set unchanged

    cga_new = _adjusted_cga(
        ep.cga_score, ep.total_violations, n_actions, n_mandatory, delta_violations=1, delta_actions=0
    )

    n_c4 = max(len(timing_deadlines) + 1, 1)
    sub_pert = dict(ep.sub_scores)
    sub_pert["C4_timing_compliance"] = max(0.0, ep.sub_scores.get("C4_timing_compliance", 1.0) - 1.0 / n_c4)

    return PerturbedEpisode(
        episode_id=ep.episode_id,
        perturbation="P1",
        applicable=True,
        baseline_orig=bl_orig,
        baseline_perturbed=bl_pert,
        cga_orig=ep.cga_score,
        cga_perturbed=cga_new,
        sub_scores_orig=dict(ep.sub_scores),
        sub_scores_perturbed=sub_pert,
        perturbation_detail=f"Delayed '{target_action}' past {target_deadline}min",
    )


def _perturb_p2_swap(
    ep: Episode,
    baseline_fn: Callable,
    norm,
) -> PerturbedEpisode:
    """P2: Swap timestamps of a constrained pair. Action set unchanged."""
    n_actions = len(ep.actions)
    n_mandatory = len(ep.expected_actions)
    performed = [a["action_id"] for a in ep.actions]

    seq_pairs: list[tuple[str, str]] = []
    for v in ep.violation_events_orig:
        if v.get("violation_type") == "sequence":
            later = v.get("action_involved", "")
            prior = v.get("expected_action", "")
            if later and prior:
                seq_pairs.append((prior, later))

    clinical_sequences = [
        ("order_lab_blood_culture", "give_broad_spectrum_antibiotics"),
        ("establish_iv_access", "start_iv_fluid_ns"),
        ("obtain_12_lead_ecg", "activate_cath_lab"),
        ("assess_nihss", "give_alteplase_0.9mg_kg"),
        ("assess_vital_signs", "give_broad_spectrum_antibiotics"),
    ]
    seq_pairs.extend(clinical_sequences)

    action_map: dict[str, float] = {a["action_id"]: a["timestamp"] for a in ep.actions}
    swap_pair: tuple[str, str] | None = None
    for first_id, second_id in seq_pairs:
        if first_id in action_map and second_id in action_map:
            if action_map[first_id] < action_map[second_id]:
                swap_pair = (first_id, second_id)
                break

    if swap_pair is None:
        return PerturbedEpisode(
            episode_id=ep.episode_id,
            perturbation="P2",
            applicable=False,
            skip_reason="no valid in-order action pair found",
        )

    bl_orig = baseline_fn(performed, ep.expected_actions, norm)
    bl_pert = bl_orig  # same action set

    cga_new = _adjusted_cga(
        ep.cga_score, ep.total_violations, n_actions, n_mandatory, delta_violations=1, delta_actions=0
    )

    n_seq = max(len(seq_pairs), 1)
    sub_pert = dict(ep.sub_scores)
    sub_pert["C5_sequence_integrity"] = max(0.0, ep.sub_scores.get("C5_sequence_integrity", 1.0) - 1.0 / n_seq)

    return PerturbedEpisode(
        episode_id=ep.episode_id,
        perturbation="P2",
        applicable=True,
        baseline_orig=bl_orig,
        baseline_perturbed=bl_pert,
        cga_orig=ep.cga_score,
        cga_perturbed=cga_new,
        sub_scores_orig=dict(ep.sub_scores),
        sub_scores_perturbed=sub_pert,
        perturbation_detail=f"Swapped '{swap_pair[0]}' <-> '{swap_pair[1]}'",
    )


def _perturb_p3_delete(
    ep: Episode,
    baseline_fn: Callable,
    norm,
) -> PerturbedEpisode:
    """P3 (sanity): Delete one mandatory action → both metrics should drop."""
    n_actions = len(ep.actions)
    n_mandatory = len(ep.expected_actions)
    performed = [a["action_id"] for a in ep.actions]

    candidate: str | None = None
    for exp in ep.expected_actions:
        if exp in performed:
            candidate = exp
            break
        if norm:
            for pid in performed:
                if norm.are_aliases(pid, exp):
                    candidate = pid
                    break
        if candidate:
            break

    if candidate is None:
        return PerturbedEpisode(
            episode_id=ep.episode_id,
            perturbation="P3",
            applicable=False,
            skip_reason="no performed mandatory action found",
        )

    perturbed_performed = [a for a in performed if a != candidate]
    bl_orig = baseline_fn(performed, ep.expected_actions, norm)
    bl_pert = baseline_fn(perturbed_performed, ep.expected_actions, norm)

    cga_new = _adjusted_cga(
        ep.cga_score, ep.total_violations, n_actions - 1, n_mandatory, delta_violations=1, delta_actions=-1
    )

    n_m = max(n_mandatory, 1)
    sub_pert = dict(ep.sub_scores)
    sub_pert["C2_mandatory_completion"] = max(0.0, ep.sub_scores.get("C2_mandatory_completion", 1.0) - 1.0 / n_m)

    return PerturbedEpisode(
        episode_id=ep.episode_id,
        perturbation="P3",
        applicable=True,
        baseline_orig=bl_orig,
        baseline_perturbed=bl_pert,
        cga_orig=ep.cga_score,
        cga_perturbed=cga_new,
        sub_scores_orig=dict(ep.sub_scores),
        sub_scores_perturbed=sub_pert,
        perturbation_detail=f"Deleted mandatory '{candidate}'",
    )


def _perturb_p4_insert_forbidden(
    ep: Episode,
    baseline_fn: Callable,
    norm,
) -> PerturbedEpisode:
    """P4: Insert forbidden action. For set-based baselines, performed set grows by 1."""
    if not ep.forbidden_actions:
        return PerturbedEpisode(
            episode_id=ep.episode_id,
            perturbation="P4",
            applicable=False,
            skip_reason="no forbidden actions for this scenario",
        )

    n_actions = len(ep.actions)
    n_mandatory = len(ep.expected_actions)
    performed = [a["action_id"] for a in ep.actions]
    inserted = ep.forbidden_actions[0]

    # Forbidden action is NOT in expected_actions → Track A unchanged
    # But Jaccard denominator grows by 1 (unless inserted is already in performed)
    perturbed_performed = performed + [inserted]

    bl_orig = baseline_fn(performed, ep.expected_actions, norm)
    bl_pert = baseline_fn(perturbed_performed, ep.expected_actions, norm)

    cga_new = _adjusted_cga(
        ep.cga_score, ep.total_violations, n_actions + 1, n_mandatory, delta_violations=1, delta_actions=1
    )

    sub_pert = dict(ep.sub_scores)
    sub_pert["C3_forbidden_avoidance"] = 0.0

    return PerturbedEpisode(
        episode_id=ep.episode_id,
        perturbation="P4",
        applicable=True,
        baseline_orig=bl_orig,
        baseline_perturbed=bl_pert,
        cga_orig=ep.cga_score,
        cga_perturbed=cga_new,
        sub_scores_orig=dict(ep.sub_scores),
        sub_scores_perturbed=sub_pert,
        perturbation_detail=f"Inserted forbidden '{inserted}'",
    )


def _perturb_p5_insert_overuse(
    ep: Episode,
    baseline_fn: Callable,
    norm,
) -> PerturbedEpisode:
    """P5: Insert harmless off-protocol action. Performed set grows by 1."""
    n_actions = len(ep.actions)
    n_mandatory = len(ep.expected_actions)
    performed = [a["action_id"] for a in ep.actions]

    performed_set = set(performed)
    inserted: str | None = None
    for cand in _OVERUSE_ACTIONS:
        if cand not in performed_set:
            inserted = cand
            break
    if inserted is None:
        inserted = f"order_lab_overuse_{random.randint(1000, 9999)}"

    perturbed_performed = performed + [inserted]

    bl_orig = baseline_fn(performed, ep.expected_actions, norm)
    bl_pert = baseline_fn(perturbed_performed, ep.expected_actions, norm)

    cga_new = _adjusted_cga(
        ep.cga_score, ep.total_violations, n_actions + 1, n_mandatory, delta_violations=1, delta_actions=1
    )

    n_act_safe = max(n_actions, 1)
    sub_pert = dict(ep.sub_scores)
    sub_pert["C1_path_selection"] = max(
        0.0, ep.sub_scores.get("C1_path_selection", 1.0) * n_act_safe / (n_act_safe + 1)
    )

    return PerturbedEpisode(
        episode_id=ep.episode_id,
        perturbation="P5",
        applicable=True,
        baseline_orig=bl_orig,
        baseline_perturbed=bl_pert,
        cga_orig=ep.cga_score,
        cga_perturbed=cga_new,
        sub_scores_orig=dict(ep.sub_scores),
        sub_scores_perturbed=sub_pert,
        perturbation_detail=f"Inserted overuse '{inserted}'",
    )


PERTURBATION_FNS = {
    "P1": _perturb_p1_delay,
    "P2": _perturb_p2_swap,
    "P3": _perturb_p3_delete,
    "P4": _perturb_p4_insert_forbidden,
    "P5": _perturb_p5_insert_overuse,
}


# ---------------------------------------------------------------------------
# BSR calculation
# ---------------------------------------------------------------------------


def _compute_bsr(
    perturbed: list[PerturbedEpisode],
    delta: float = DELTA_DEFAULT,
    epsilon: float = EPSILON_DEFAULT,
) -> tuple[float, int]:
    blind_spots = 0
    valid = 0
    for ep in perturbed:
        if not ep.applicable:
            continue
        valid += 1
        baseline_unchanged = abs(ep.baseline_orig - ep.baseline_perturbed) < epsilon
        cga_changed = abs(ep.cga_orig - ep.cga_perturbed) > delta
        if baseline_unchanged and cga_changed:
            blind_spots += 1
    return (blind_spots / valid if valid > 0 else 0.0), valid


def _bootstrap_bsr_ci(
    perturbed: list[PerturbedEpisode],
    episodes: list[Episode],
    delta: float = DELTA_DEFAULT,
    epsilon: float = EPSILON_DEFAULT,
    n_bootstrap: int = 1000,
) -> tuple[float, float]:
    ep_by_id = {ep.episode_id: ep for ep in episodes}
    by_scenario: dict[str, list[PerturbedEpisode]] = {}
    for pep in perturbed:
        orig_ep = ep_by_id.get(pep.episode_id)
        sid = orig_ep.scenario_id if orig_ep else pep.episode_id
        by_scenario.setdefault(sid, []).append(pep)

    scenario_ids = list(by_scenario.keys())
    if len(scenario_ids) < 2:
        bsr, _ = _compute_bsr(perturbed, delta, epsilon)
        return bsr, bsr

    bsr_samples = []
    for _ in range(n_bootstrap):
        sampled = random.choices(scenario_ids, k=len(scenario_ids))
        flat = [pep for sid in sampled for pep in by_scenario[sid]]
        bsr, _ = _compute_bsr(flat, delta, epsilon)
        bsr_samples.append(bsr)

    return float(np.percentile(bsr_samples, 2.5)), float(np.percentile(bsr_samples, 97.5))


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def _validate(
    all_perturbed: dict[str, list[PerturbedEpisode]],
    episodes: list[Episode],
    baseline_name: str,
    baseline_fn: Callable,
    norm,
) -> dict[str, str]:
    results: dict[str, str] = {}

    # 5-A: Sample details
    for ptag in ("P1", "P2", "P4"):
        peps = [p for p in all_perturbed.get(ptag, []) if p.applicable]
        results[f"5A_sample_{ptag}"] = peps[0].perturbation_detail if peps else "NO APPLICABLE"

    # 5-B: CGA detects perturbation
    for ptag, sub_key, direction in [
        ("P1", "C4_timing_compliance", "lt"),
        ("P2", "C5_sequence_integrity", "lt"),
        ("P4", "C3_forbidden_avoidance", "eq_zero"),
    ]:
        peps = [p for p in all_perturbed.get(ptag, []) if p.applicable]
        failures = 0
        for pep in peps:
            o = pep.sub_scores_orig.get(sub_key, 1.0)
            p_val = pep.sub_scores_perturbed.get(sub_key, 1.0)
            if (direction == "lt" and p_val >= o) or (direction == "eq_zero" and p_val != 0.0 and o > 0.0):
                failures += 1
        results[f"5B_cga_detects_{ptag}"] = "PASS" if failures == 0 else f"FAIL ({failures})"

    # 5-C: P3 sanity
    peps_p3 = [p for p in all_perturbed.get("P3", []) if p.applicable]
    if peps_p3:
        bsr_p3, _ = _compute_bsr(peps_p3)
        results["5C_p3_sanity"] = f"BSR_P3={bsr_p3:.3f}" + (" *** ABNORMAL ***" if bsr_p3 > 0.3 else "")
    else:
        results["5C_p3_sanity"] = "NO P3 APPLICABLE"

    # 5-D: Correlation between baseline and CGA
    all_valid = [p for plist in all_perturbed.values() for p in plist if p.applicable]
    bls = [p.baseline_orig for p in all_valid]
    cgas = [p.cga_orig for p in all_valid]
    if len(bls) > 5:
        r, pval = stats.pearsonr(bls, cgas)
        label = "too similar" if r > 0.8 else ("moderate" if r > 0.5 else "sufficiently independent")
        results["5D_correlation"] = f"r({baseline_name},CGA)={r:.3f}, p={pval:.3e} ({label})"
    else:
        results["5D_correlation"] = "insufficient data"

    return results


# ---------------------------------------------------------------------------
# Figures
# ---------------------------------------------------------------------------

_PERT_LABELS = {"P1": "P1\nDELAY", "P2": "P2\nSWAP", "P4": "P4\nFORBIDDEN", "P5": "P5\nOVERUSE"}
_PERT_COLORS = {"P1": "#2196F3", "P2": "#FF9800", "P4": "#F44336", "P5": "#9C27B0", "P3": "#4CAF50"}


def _fig_bsr_by_type(bsr_all, bsr_high, ci_all, ci_high, n_valid, baseline_name, out_path):
    ptags = ["P1", "P2", "P4", "P5"]
    labels = [_PERT_LABELS[p] for p in ptags]
    ba_vals = [bsr_all.get(p, 0.0) for p in ptags]
    bh_vals = [bsr_high.get(p, 0.0) for p in ptags]

    err_a_lo = [max(0, bsr_all.get(p, 0) - ci_all.get(p, (0, 0))[0]) for p in ptags]
    err_a_hi = [max(0, ci_all.get(p, (0, 0))[1] - bsr_all.get(p, 0)) for p in ptags]
    err_h_lo = [max(0, bsr_high.get(p, 0) - ci_high.get(p, (0, 0))[0]) for p in ptags]
    err_h_hi = [max(0, ci_high.get(p, (0, 0))[1] - bsr_high.get(p, 0)) for p in ptags]

    x = np.arange(len(ptags))
    w = 0.35
    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor("white")
    ax.bar(x - w / 2, ba_vals, w, yerr=[err_a_lo, err_a_hi], color="#1565C0", alpha=0.85, capsize=4, label="BSR (all)")
    ax.bar(
        x + w / 2, bh_vals, w, yerr=[err_h_lo, err_h_hi], color="#E53935", alpha=0.85, capsize=4, label="BSR (high-CGA)"
    )
    for i, p in enumerate(ptags):
        ax.text(
            x[i] - w / 2,
            ba_vals[i] + max(err_a_hi[i], 0) + 0.03,
            f"n={n_valid.get(p, 0)}",
            ha="center",
            va="bottom",
            fontsize=7,
        )
    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("BSR (Blind-Spot Rate)", fontsize=11)
    ax.set_title(
        f"BSR by Perturbation Type — Baseline: {baseline_name}\n"
        r"($\varepsilon=0.05$, $\delta=0.10$, 95% CI via scenario-level bootstrap)",
        fontsize=10,
    )
    ax.set_ylim(0, 1.1)
    ax.axhline(0.5, color="gray", linestyle="--", linewidth=0.8, alpha=0.5)
    ax.legend(fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(out_path, format="pdf", dpi=150)
    plt.close()
    print(f"  Saved: {out_path}")


def _fig_quadrant(all_perturbed, baseline_name, out_path):
    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("white")
    for ptag, peps in all_perturbed.items():
        if ptag == "P3":
            continue
        valid = [p for p in peps if p.applicable]
        if not valid:
            continue
        dx = [p.baseline_orig - p.baseline_perturbed for p in valid]
        dy = [p.cga_orig - p.cga_perturbed for p in valid]
        ax.scatter(dx, dy, c=_PERT_COLORS.get(ptag, "black"), label=ptag, alpha=0.55, s=30, linewidths=0)

    ax.axvline(0, color="k", linewidth=0.8)
    ax.axhline(0, color="k", linewidth=0.8)
    ax.axvline(EPSILON_DEFAULT, color="gray", linewidth=0.5, linestyle=":")
    ax.axvline(-EPSILON_DEFAULT, color="gray", linewidth=0.5, linestyle=":")
    ax.axhline(DELTA_DEFAULT, color="gray", linewidth=0.5, linestyle=":")
    ax.axhline(-DELTA_DEFAULT, color="gray", linewidth=0.5, linestyle=":")

    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    ax.text(
        xlim[0] + 0.01,
        ylim[1] - 0.01,
        "CGA only\n(BLIND SPOT)",
        ha="left",
        va="top",
        fontsize=8,
        color="#C62828",
        bbox={"facecolor": "#FFCDD2", "alpha": 0.5, "boxstyle": "round,pad=0.3"},
    )
    ax.text(
        xlim[1] - 0.01,
        ylim[1] - 0.01,
        "Both detect\n(Agreement)",
        ha="right",
        va="top",
        fontsize=8,
        color="#1B5E20",
        bbox={"facecolor": "#C8E6C9", "alpha": 0.5, "boxstyle": "round,pad=0.3"},
    )
    ax.text(xlim[0] + 0.01, ylim[0] + 0.01, "Neither detects", ha="left", va="bottom", fontsize=8, color="gray")
    ax.text(xlim[1] - 0.01, ylim[0] + 0.01, "Baseline only", ha="right", va="bottom", fontsize=8, color="gray")

    blind_x = xlim[0]
    rect = Rectangle(
        (blind_x, DELTA_DEFAULT),
        EPSILON_DEFAULT - blind_x,
        ylim[1] - DELTA_DEFAULT,
        linewidth=1.2,
        edgecolor="#C62828",
        facecolor="#FFCDD2",
        alpha=0.15,
    )
    ax.add_patch(rect)

    ax.set_xlabel(f"$\\Delta${baseline_name} (orig - perturbed)", fontsize=11)
    ax.set_ylabel(r"$\Delta$CGA (orig - perturbed)", fontsize=11)
    ax.set_title(f"$\\Delta$Baseline vs $\\Delta$CGA — Baseline: {baseline_name}", fontsize=10)
    ax.legend(fontsize=9, title="Perturbation")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(out_path, format="pdf", dpi=150)
    plt.close()
    print(f"  Saved: {out_path}")


def _fig_delta_sensitivity(all_perturbed, baseline_name, out_path):
    ptags_main = ["P1", "P2", "P4", "P5"]
    delta_grid = np.linspace(0.01, 0.30, 60)
    bsr_curve = []
    for delta in delta_grid:
        flat = [p for ptag in ptags_main for p in all_perturbed.get(ptag, []) if p.applicable]
        bsr, _ = _compute_bsr(flat, delta=float(delta))
        bsr_curve.append(bsr)

    fig, ax = plt.subplots(figsize=(7, 4))
    fig.patch.set_facecolor("white")
    ax.plot(delta_grid, bsr_curve, color="#1565C0", linewidth=2)
    ax.axvline(DELTA_DEFAULT, color="#E53935", linestyle="--", linewidth=1.2, label=f"default delta={DELTA_DEFAULT}")
    ax.set_xlabel(r"$\delta$ threshold", fontsize=11)
    ax.set_ylabel("BSR overall (P1+P2+P4+P5)", fontsize=11)
    ax.set_title(f"BSR Sensitivity — Baseline: {baseline_name}", fontsize=11)
    ax.set_xlim(0.01, 0.30)
    ax.set_ylim(0, 1.05)
    ax.legend(fontsize=9)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(out_path, format="pdf", dpi=150)
    plt.close()
    print(f"  Saved: {out_path}")


# ---------------------------------------------------------------------------
# LaTeX table
# ---------------------------------------------------------------------------


def _bsr_table_latex(bsr_all, bsr_high, n_valid, baseline_name):
    labels = {
        "P1": "P1 DELAY",
        "P2": "P2 SWAP",
        "P3": "P3 DELETE (sanity)",
        "P4": "P4 FORBIDDEN",
        "P5": "P5 OVERUSE",
        "Overall": "\\textbf{Overall}",
    }
    interps = {
        "P1": "timing blind spot",
        "P2": "sequence blind spot",
        "P3": "(sanity check)",
        "P4": "safety blind spot",
        "P5": "overuse blind spot",
        "Overall": "weighted average",
    }
    rows = []
    for ptag in ("P1", "P2", "P3", "P4", "P5", "Overall"):
        ba = bsr_all.get(ptag, 0.0)
        bh = bsr_high.get(ptag, 0.0)
        nv = n_valid.get(ptag, 0)
        rows.append(f"  {labels[ptag]} & {ba:.3f} & {bh:.3f} & {nv} & {interps[ptag]} \\\\")

    header = (
        "\\begin{table}[h]\n\\centering\n"
        f"\\caption{{BSR by Perturbation Type — Baseline: {baseline_name} "
        r"($\varepsilon=0.05$, $\delta=0.10$)}}"
        "\n"
        "\\label{tab:bsr}\n"
        "\\begin{tabular}{lcccc}\n\\toprule\n"
        "Perturbation & BSR\\_all & BSR\\_high & N\\_valid & Interpretation \\\\\n"
        "\\midrule\n"
    )
    return header + "\n".join(rows) + "\n\\bottomrule\n\\end{tabular}\n\\end{table}"


# ---------------------------------------------------------------------------
# Full BSR pipeline for one baseline
# ---------------------------------------------------------------------------


def run_bsr_for_baseline(
    episodes: list[Episode],
    baseline_name: str,
    baseline_fn: Callable,
    norm,
    save_outputs: bool = False,
) -> dict:
    """Run the full BSR pipeline for a single baseline. Returns results dict."""
    all_perturbed: dict[str, list[PerturbedEpisode]] = {
        "P1": [],
        "P2": [],
        "P3": [],
        "P4": [],
        "P5": [],
    }

    for ep in episodes:
        for ptag, fn in PERTURBATION_FNS.items():
            all_perturbed[ptag].append(fn(ep, baseline_fn, norm))

    # BSR per type
    median_cga = float(np.median([ep.cga_score for ep in episodes]))
    high_ids = {ep.episode_id for ep in episodes if ep.cga_score >= median_cga}

    bsr_all: dict[str, float] = {}
    bsr_high: dict[str, float] = {}
    n_valid: dict[str, int] = {}
    ci_all: dict[str, tuple[float, float]] = {}
    ci_high: dict[str, tuple[float, float]] = {}

    for ptag, peps in all_perturbed.items():
        peps_high = [p for p in peps if p.episode_id in high_ids]
        ba, nv = _compute_bsr(peps)
        bh, _ = _compute_bsr(peps_high)
        bsr_all[ptag] = ba
        bsr_high[ptag] = bh
        n_valid[ptag] = nv
        ci_all[ptag] = _bootstrap_bsr_ci(peps, episodes)
        ci_high[ptag] = _bootstrap_bsr_ci(peps_high, episodes)

    # Overall
    flat_main = [p for ptag in ("P1", "P2", "P4", "P5") for p in all_perturbed[ptag] if p.applicable]
    flat_main_high = [p for p in flat_main if p.episode_id in high_ids]
    bsr_o, nv_o = _compute_bsr(flat_main)
    bsr_oh, _ = _compute_bsr(flat_main_high)
    bsr_all["Overall"] = bsr_o
    bsr_high["Overall"] = bsr_oh
    n_valid["Overall"] = nv_o
    ci_all["Overall"] = _bootstrap_bsr_ci(flat_main, episodes)
    ci_high["Overall"] = _bootstrap_bsr_ci(flat_main_high, episodes)

    # Validation
    val = _validate(all_perturbed, episodes, baseline_name, baseline_fn, norm)

    # Correlation
    all_valid = [p for plist in all_perturbed.values() for p in plist if p.applicable]
    bls = [p.baseline_orig for p in all_valid]
    cgas = [p.cga_orig for p in all_valid]
    r_val = float(stats.pearsonr(bls, cgas)[0]) if len(bls) > 5 else float("nan")

    # Delta sensitivity
    delta_sens = {}
    for d in (0.05, 0.10, 0.15, 0.20):
        bsr_d, _ = _compute_bsr(flat_main, delta=d)
        delta_sens[str(round(d, 2))] = round(bsr_d, 4)

    result = {
        "baseline_name": baseline_name,
        "r_baseline_cga": round(r_val, 4),
        "bsr_all": bsr_all,
        "bsr_high": bsr_high,
        "n_valid": n_valid,
        "ci_all": {k: list(v) for k, v in ci_all.items()},
        "ci_high": {k: list(v) for k, v in ci_high.items()},
        "delta_sensitivity": delta_sens,
        "validation": val,
    }

    if save_outputs:
        suffix = baseline_name.lower().replace(" ", "_")

        _fig_bsr_by_type(
            bsr_all, bsr_high, ci_all, ci_high, n_valid, baseline_name, OUT_FIGURES / f"bsr_by_type_{suffix}.pdf"
        )
        _fig_quadrant(all_perturbed, baseline_name, OUT_FIGURES / f"bsr_quadrant_{suffix}.pdf")
        _fig_delta_sensitivity(all_perturbed, baseline_name, OUT_FIGURES / f"bsr_delta_sensitivity_{suffix}.pdf")

        tex = _bsr_table_latex(bsr_all, bsr_high, n_valid, baseline_name)
        tex_path = OUT_TABLES / f"bsr_table_{suffix}.tex"
        with open(tex_path, "w") as f:
            f.write(tex)
        print(f"  Saved: {tex_path}")

        # Save per-episode data for the selected baseline
        def _pep_dict(p: PerturbedEpisode) -> dict:
            return {
                "episode_id": p.episode_id,
                "perturbation": p.perturbation,
                "applicable": p.applicable,
                "skip_reason": p.skip_reason,
                "baseline_orig": p.baseline_orig,
                "baseline_perturbed": p.baseline_perturbed,
                "cga_orig": p.cga_orig,
                "cga_perturbed": p.cga_perturbed,
                "detail": p.perturbation_detail,
            }

        result["perturbed_episodes"] = {ptag: [_pep_dict(p) for p in peps] for ptag, peps in all_perturbed.items()}

    return result


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 70)
    print("BSR Baseline Metric Comparison")
    print("=" * 70)

    OUT_ANALYSIS.mkdir(parents=True, exist_ok=True)
    OUT_FIGURES.mkdir(parents=True, exist_ok=True)
    OUT_TABLES.mkdir(parents=True, exist_ok=True)

    # Load data
    print("\n[1] Loading episodes ...")
    episodes = _load_episodes()
    print(f"  Loaded {len(episodes)} episodes")

    norm = _get_normalizer()
    print(f"  ActionNormalizer: {'loaded' if norm else 'unavailable (exact match only)'}")

    # ------------------------------------------------------------------
    # Step 1: Compute all 3 baselines for all episodes
    # ------------------------------------------------------------------
    print("\n[2] Computing baseline correlations with CGA ...")
    performed_lists = [[a["action_id"] for a in ep.actions] for ep in episodes]
    expected_lists = [ep.expected_actions for ep in episodes]
    cga_scores = [ep.cga_score for ep in episodes]

    baseline_values: dict[str, list[float]] = {}
    for bname, bfn in BASELINE_FUNCS.items():
        vals = [bfn(perf, exp, norm) for perf, exp in zip(performed_lists, expected_lists)]
        baseline_values[bname] = vals

    print(f"\n  {'Baseline':<16} {'Mean':>8} {'Std':>8} {'r(BL,CGA)':>10} {'p-value':>12} {'Verdict':>22}")
    print("  " + "-" * 80)

    correlations: dict[str, float] = {}
    for bname, vals in baseline_values.items():
        r, pval = stats.pearsonr(vals, cga_scores)
        correlations[bname] = r
        mean_v = float(np.mean(vals))
        std_v = float(np.std(vals))
        verdict = "TOO SIMILAR" if r > 0.8 else ("MODERATE" if r > 0.5 else "GOOD (independent)")
        print(f"  {bname:<16} {mean_v:>8.3f} {std_v:>8.3f} {r:>10.3f} {pval:>12.3e} {verdict:>22}")

    # ------------------------------------------------------------------
    # Step 2: Select best baseline (lowest r, preferring r < 0.5)
    # ------------------------------------------------------------------
    selected = min(correlations, key=correlations.get)
    print(f"\n  Selected baseline: {selected} (r={correlations[selected]:.3f})")

    if correlations[selected] > 0.5:
        print("  WARNING: No baseline has r < 0.5. Results may still underestimate BSR.")

    # ------------------------------------------------------------------
    # Step 3: Run BSR for all baselines (selected gets full outputs)
    # ------------------------------------------------------------------
    print("\n[3] Running BSR for all baselines ...")
    all_results: dict[str, dict] = {}

    for bname, bfn in BASELINE_FUNCS.items():
        is_selected = bname == selected
        print(f"\n  --- {bname} {'(SELECTED)' if is_selected else ''} ---")
        result = run_bsr_for_baseline(episodes, bname, bfn, norm, save_outputs=is_selected)
        all_results[bname] = result

        bsr_o = result["bsr_all"]["Overall"]
        ci = result["ci_all"]["Overall"]
        print(f"    Overall BSR = {bsr_o:.3f} (CI: [{ci[0]:.3f}, {ci[1]:.3f}])")
        print(f"    r(baseline, CGA) = {result['r_baseline_cga']:.3f}")

        for ptag in ("P1", "P2", "P3", "P4", "P5"):
            ba = result["bsr_all"][ptag]
            nv = result["n_valid"][ptag]
            print(f"    {ptag}: BSR={ba:.3f} (N={nv})")

    # ------------------------------------------------------------------
    # Step 4: Comparison summary
    # ------------------------------------------------------------------
    print("\n" + "=" * 70)
    print("[4] COMPARISON SUMMARY")
    print("=" * 70)

    print(
        f"\n  {'Baseline':<16} {'r(BL,CGA)':>10} {'BSR_overall':>12} {'BSR_P1':>8} {'BSR_P2':>8} {'BSR_P4':>8} {'BSR_P5':>8}"
    )
    print("  " + "-" * 75)
    for bname in BASELINE_FUNCS:
        r = all_results[bname]
        rc = r["r_baseline_cga"]
        bo = r["bsr_all"]["Overall"]
        b1 = r["bsr_all"]["P1"]
        b2 = r["bsr_all"]["P2"]
        b4 = r["bsr_all"]["P4"]
        b5 = r["bsr_all"]["P5"]
        marker = " <-- SELECTED" if bname == selected else ""
        print(f"  {bname:<16} {rc:>10.3f} {bo:>12.3f} {b1:>8.3f} {b2:>8.3f} {b4:>8.3f} {b5:>8.3f}{marker}")

    # ------------------------------------------------------------------
    # Step 5: Save combined results
    # ------------------------------------------------------------------
    print("\n[5] Saving outputs ...")

    combined = {
        "metadata": {
            "epsilon": EPSILON_DEFAULT,
            "delta": DELTA_DEFAULT,
            "binary_threshold": BINARY_THRESHOLD,
            "n_episodes": len(episodes),
            "models": MODELS,
            "selected_baseline": selected,
            "selection_criterion": "lowest r(baseline, CGA)",
            "note": (
                "Track A (B1) has r=0.861 with CGA — too correlated. "
                "Jaccard (B2) provides a genuinely external baseline that measures "
                "'what was done' without 'how' (timing/sequence/forbidden). "
                "Binary (B3) reduces correlation by coarsening but loses sensitivity."
            ),
        },
        "baseline_correlations": {k: round(v, 4) for k, v in correlations.items()},
        "baseline_means": {k: round(float(np.mean(v)), 4) for k, v in baseline_values.items()},
        "selected_result": all_results[selected],
        "all_results_summary": {
            bname: {
                "r_baseline_cga": r["r_baseline_cga"],
                "bsr_all": r["bsr_all"],
                "bsr_high": r["bsr_high"],
                "n_valid": r["n_valid"],
                "delta_sensitivity": r["delta_sensitivity"],
                "validation": r["validation"],
            }
            for bname, r in all_results.items()
        },
        "track_a_bsr_as_lower_bound": {
            "note": "Track A BSR (6.9%) is a conservative lower bound due to high correlation",
            "bsr_all": all_results["B1_TrackA"]["bsr_all"],
        },
    }

    json_path = OUT_ANALYSIS / "bsr_results.json"
    with open(json_path, "w") as f:
        json.dump(combined, f, indent=2, default=str)
    print(f"  Saved: {json_path}")

    # Also save the primary figures as the main bsr_*.pdf (overwriting old Track A versions)
    selected_fn = BASELINE_FUNCS[selected]
    suffix = selected.lower().replace(" ", "_")
    for src_name, dst_name in [
        (f"bsr_by_type_{suffix}.pdf", "bsr_by_type.pdf"),
        (f"bsr_quadrant_{suffix}.pdf", "bsr_quadrant.pdf"),
        (f"bsr_delta_sensitivity_{suffix}.pdf", "bsr_delta_sensitivity.pdf"),
    ]:
        src = OUT_FIGURES / src_name
        dst = OUT_FIGURES / dst_name
        if src.exists():
            import shutil

            shutil.copy2(src, dst)
            print(f"  Copied: {src_name} -> {dst_name}")

    # Overwrite main table
    tex = _bsr_table_latex(
        all_results[selected]["bsr_all"],
        all_results[selected]["bsr_high"],
        all_results[selected]["n_valid"],
        selected,
    )
    tex_path = OUT_TABLES / "bsr_table.tex"
    with open(tex_path, "w") as f:
        f.write(tex)
    print(f"  Saved: {tex_path}")

    # ------------------------------------------------------------------
    # Integration paragraph
    # ------------------------------------------------------------------
    sel_r = all_results[selected]
    bsr_pct = sel_r["bsr_all"]["Overall"] * 100
    old_bsr_pct = all_results["B1_TrackA"]["bsr_all"]["Overall"] * 100

    print("\n[6] Integration paragraph:")
    print(
        f"\n  Using {selected} (r={correlations[selected]:.3f}) as the external baseline, "
        f"BSR_overall = {bsr_pct:.1f}% (95% CI: "
        f"[{sel_r['ci_all']['Overall'][0] * 100:.1f}%, {sel_r['ci_all']['Overall'][1] * 100:.1f}%]). "
        f"Track-A-based BSR ({old_bsr_pct:.1f}%) serves as a conservative lower bound.\n"
        f'\n  Paper sentence: "Outcome-equivalent metrics miss {bsr_pct:.0f}% of '
        f"clinically meaningful process differences (BSR={sel_r['bsr_all']['Overall']:.2f}, "
        f"95% CI [{sel_r['ci_all']['Overall'][0]:.2f}, {sel_r['ci_all']['Overall'][1]:.2f}], "
        f'Jaccard baseline r={correlations[selected]:.2f} with CGA)."\n'
    )

    print("\n" + "=" * 70)
    print("BSR Baseline Comparison complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
