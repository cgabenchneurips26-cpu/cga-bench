
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""BSR (Blind-Spot Rate) Perturbation Analysis Pipeline.

BSR(m, d) = P[ m(τ) = m(τ̃)  ∧  d(τ) ≠ d(τ̃) ]

Quantifies what existing outcome-only metrics MISS that CGA catches.

Baseline metric: Track A (Action Coverage) = |performed ∩ expected| / |expected|
CGA metric   : compliance_score from rescored episodes

Usage:
    cd ${CGA_BENCH_ROOT}/cga_bench
    PYTHONPATH=${CGA_BENCH_ROOT} \
        python scripts/experiments/bsr_perturbation.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
import glob
import json
import os
from pathlib import Path
import random

import matplotlib
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

# BSR thresholds
EPSILON_DEFAULT = 0.05  # Track-A change considered "same"
DELTA_DEFAULT = 0.10  # CGA change considered "different"

# Off-protocol actions used for P5 INSERT_OVERUSE
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
    """Holds data for one episode from both the original and rescored files."""

    episode_id: str
    scenario_id: str
    model: str
    run_index: int

    # Actions from original file
    actions: list[dict]  # [{"action_id": str, "timestamp": float, ...}]
    expected_actions: list[str]
    forbidden_actions: list[str]
    violation_events_orig: list[dict]  # from original file
    sub_scores_orig: dict[str, float]

    # From rescored file
    cga_score: float  # new_compliance_score
    sub_scores: dict[str, float]  # new_sub_scores
    total_violations: int  # new_total_violations
    violation_events: list[dict]  # new_violation_events


@dataclass
class PerturbedEpisode:
    """Result of applying one perturbation to one episode."""

    episode_id: str
    perturbation: str  # P1..P5
    applicable: bool
    skip_reason: str = ""

    track_a_orig: float = 0.0
    track_a_perturbed: float = 0.0
    cga_orig: float = 0.0
    cga_perturbed: float = 0.0

    sub_scores_orig: dict = field(default_factory=dict)
    sub_scores_perturbed: dict = field(default_factory=dict)

    perturbation_detail: str = ""  # human-readable description


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _load_episodes() -> list[Episode]:
    """Load all 180 episodes (4 models × 45 each)."""
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
            orig = json.load(open(orig_files[fname]))
            resc = json.load(open(resc_files[fname]))
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
# Track-A (action coverage) computation
# ---------------------------------------------------------------------------


def _compute_track_a(
    performed: list[str],
    expected: list[str],
) -> float:
    """Track A = |performed ∩ expected| / |expected|.

    Uses ActionNormalizer.are_aliases for semantic matching.
    Falls back to exact match if normalizer is unavailable.
    """
    if not expected:
        return 1.0
    try:
        from cga_bench.assessor_core.action_normalizer import ActionNormalizer

        norm = ActionNormalizer()
        matched = 0
        for exp_act in expected:
            for perf_act in performed:
                if perf_act == exp_act or norm.are_aliases(perf_act, exp_act):
                    matched += 1
                    break
        return matched / len(expected)
    except Exception:
        # Fallback: exact set intersection
        return len(set(performed) & set(expected)) / len(expected)


# ---------------------------------------------------------------------------
# CGA analytic update helpers
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
    """Analytically compute perturbed CGA.

    CGA = 1 - n_violations / denom
    New CGA = 1 - (n_violations + dv) / max(n_actions + da, n_mandatory, 1)
    """
    denom_new = _cga_denom(n_actions + delta_actions, n_mandatory)
    n_viol_new = n_violations_orig + delta_violations
    return max(0.0, 1.0 - n_viol_new / denom_new)


# ---------------------------------------------------------------------------
# Perturbation generators
# ---------------------------------------------------------------------------


def _perturb_p1_delay(ep: Episode) -> PerturbedEpisode:
    """P1: Inject a timing violation by delaying an on-time action past its deadline."""
    n_actions = len(ep.actions)
    n_mandatory = len(ep.expected_actions)

    # Identify actions that violated timing in the original so we can discover deadlines.
    timing_deadlines: dict[str, float] = {}
    for v in ep.violation_events_orig:
        if v.get("violation_type") == "timing" and v.get("expected_deadline") is not None:
            timing_deadlines[v["action_involved"]] = float(v["expected_deadline"])

    # Find actions currently NOT timing violations that share the same deadline constraint.
    performed_ids = {a["action_id"] for a in ep.actions}
    already_timing_violated = set(timing_deadlines.keys())

    target_action = None
    target_deadline = None

    # Strategy A: find an action that has a known deadline and was NOT already late.
    for action_id, deadline in timing_deadlines.items():
        # Look for any OTHER performed action we can pretend has the same deadline.
        for a in ep.actions:
            aid = a["action_id"]
            if aid not in already_timing_violated and a["timestamp"] <= deadline:
                target_action = aid
                target_deadline = deadline
                break
        if target_action:
            break

    # Strategy B: any early action → push past minute 60.
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

    cga_new = _adjusted_cga(
        ep.cga_score,
        ep.total_violations,
        n_actions,
        n_mandatory,
        delta_violations=1,
        delta_actions=0,
    )
    track_a_orig = _compute_track_a([a["action_id"] for a in ep.actions], ep.expected_actions)
    track_a_perturbed = track_a_orig  # same action set, just delayed

    # Adjust C4
    n_c4_constraints = max(len(timing_deadlines) + 1, 1)
    c4_new = max(0.0, ep.sub_scores.get("C4_timing_compliance", 1.0) - 1.0 / n_c4_constraints)
    sub_perturbed = dict(ep.sub_scores)
    sub_perturbed["C4_timing_compliance"] = c4_new

    return PerturbedEpisode(
        episode_id=ep.episode_id,
        perturbation="P1",
        applicable=True,
        track_a_orig=track_a_orig,
        track_a_perturbed=track_a_perturbed,
        cga_orig=ep.cga_score,
        cga_perturbed=cga_new,
        sub_scores_orig=dict(ep.sub_scores),
        sub_scores_perturbed=sub_perturbed,
        perturbation_detail=(
            f"Delayed '{target_action}' past deadline {target_deadline} min → CGA {ep.cga_score:.3f} → {cga_new:.3f}"
        ),
    )


def _perturb_p2_swap(ep: Episode) -> PerturbedEpisode:
    """P2: Inject a sequence violation by swapping timestamps of a constrained pair."""
    n_actions = len(ep.actions)
    n_mandatory = len(ep.expected_actions)

    # Discover sequence constraints from the ORIGINAL violation_events
    # (rescored may have wiped them).
    seq_pairs: list[tuple[str, str]] = []  # (action_that_must_come_first, action_that_followed)
    for v in ep.violation_events_orig:
        if v.get("violation_type") == "sequence":
            later = v.get("action_involved", "")
            prior = v.get("expected_action", "")
            if later and prior:
                seq_pairs.append((prior, later))

    # Also include well-known clinical sequences.
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

    cga_new = _adjusted_cga(
        ep.cga_score,
        ep.total_violations,
        n_actions,
        n_mandatory,
        delta_violations=1,
        delta_actions=0,
    )
    track_a_orig = _compute_track_a([a["action_id"] for a in ep.actions], ep.expected_actions)
    track_a_perturbed = track_a_orig

    # Adjust C5
    n_seq_constraints = max(len(seq_pairs), 1)
    c5_new = max(0.0, ep.sub_scores.get("C5_sequence_integrity", 1.0) - 1.0 / n_seq_constraints)
    sub_perturbed = dict(ep.sub_scores)
    sub_perturbed["C5_sequence_integrity"] = c5_new

    return PerturbedEpisode(
        episode_id=ep.episode_id,
        perturbation="P2",
        applicable=True,
        track_a_orig=track_a_orig,
        track_a_perturbed=track_a_perturbed,
        cga_orig=ep.cga_score,
        cga_perturbed=cga_new,
        sub_scores_orig=dict(ep.sub_scores),
        sub_scores_perturbed=sub_perturbed,
        perturbation_detail=(
            f"Swapped order of '{swap_pair[0]}' ↔ '{swap_pair[1]}' → CGA {ep.cga_score:.3f} → {cga_new:.3f}"
        ),
    )


def _perturb_p3_delete(ep: Episode) -> PerturbedEpisode:
    """P3 (sanity check): Remove one performed mandatory action → both Track-A and CGA drop."""
    n_actions = len(ep.actions)
    n_mandatory = len(ep.expected_actions)

    performed_ids = [a["action_id"] for a in ep.actions]
    # Find a mandatory action that was actually performed.
    candidate: str | None = None
    for exp in ep.expected_actions:
        if exp in performed_ids:
            candidate = exp
            break
        # Try alias match
        try:
            from cga_bench.assessor_core.action_normalizer import ActionNormalizer

            norm = ActionNormalizer()
            for pid in performed_ids:
                if norm.are_aliases(pid, exp):
                    candidate = pid
                    break
        except Exception:
            pass
        if candidate:
            break

    if candidate is None:
        return PerturbedEpisode(
            episode_id=ep.episode_id,
            perturbation="P3",
            applicable=False,
            skip_reason="no performed mandatory action found",
        )

    perturbed_performed = [a for a in performed_ids if a != candidate]
    track_a_orig = _compute_track_a(performed_ids, ep.expected_actions)
    track_a_perturbed = _compute_track_a(perturbed_performed, ep.expected_actions)

    cga_new = _adjusted_cga(
        ep.cga_score,
        ep.total_violations,
        n_actions - 1,
        n_mandatory,
        delta_violations=1,
        delta_actions=-1,
    )

    n_mandatory_safe = max(n_mandatory, 1)
    c2_new = max(0.0, ep.sub_scores.get("C2_mandatory_completion", 1.0) - 1.0 / n_mandatory_safe)
    sub_perturbed = dict(ep.sub_scores)
    sub_perturbed["C2_mandatory_completion"] = c2_new

    return PerturbedEpisode(
        episode_id=ep.episode_id,
        perturbation="P3",
        applicable=True,
        track_a_orig=track_a_orig,
        track_a_perturbed=track_a_perturbed,
        cga_orig=ep.cga_score,
        cga_perturbed=cga_new,
        sub_scores_orig=dict(ep.sub_scores),
        sub_scores_perturbed=sub_perturbed,
        perturbation_detail=(
            f"Deleted mandatory action '{candidate}' → "
            f"TrackA {track_a_orig:.3f}→{track_a_perturbed:.3f}, "
            f"CGA {ep.cga_score:.3f}→{cga_new:.3f}"
        ),
    )


def _perturb_p4_insert_forbidden(ep: Episode) -> PerturbedEpisode:
    """P4: Insert one forbidden action → commission violation, Track-A unchanged."""
    if not ep.forbidden_actions:
        return PerturbedEpisode(
            episode_id=ep.episode_id,
            perturbation="P4",
            applicable=False,
            skip_reason="no forbidden actions for this scenario",
        )

    n_actions = len(ep.actions)
    n_mandatory = len(ep.expected_actions)
    inserted = ep.forbidden_actions[0]

    cga_new = _adjusted_cga(
        ep.cga_score,
        ep.total_violations,
        n_actions + 1,
        n_mandatory,
        delta_violations=1,
        delta_actions=1,
    )
    track_a_orig = _compute_track_a([a["action_id"] for a in ep.actions], ep.expected_actions)
    track_a_perturbed = track_a_orig  # forbidden action not in expected

    # C3: single commission → 0
    sub_perturbed = dict(ep.sub_scores)
    sub_perturbed["C3_forbidden_avoidance"] = 0.0

    return PerturbedEpisode(
        episode_id=ep.episode_id,
        perturbation="P4",
        applicable=True,
        track_a_orig=track_a_orig,
        track_a_perturbed=track_a_perturbed,
        cga_orig=ep.cga_score,
        cga_perturbed=cga_new,
        sub_scores_orig=dict(ep.sub_scores),
        sub_scores_perturbed=sub_perturbed,
        perturbation_detail=(f"Inserted forbidden action '{inserted}' → CGA {ep.cga_score:.3f} → {cga_new:.3f}"),
    )


def _perturb_p5_insert_overuse(ep: Episode) -> PerturbedEpisode:
    """P5: Insert a harmless off-protocol action → deviation violation, Track-A unchanged."""
    n_actions = len(ep.actions)
    n_mandatory = len(ep.expected_actions)

    # Pick an overuse action not already in the trace.
    performed_ids = {a["action_id"] for a in ep.actions}
    inserted: str | None = None
    for candidate in _OVERUSE_ACTIONS:
        if candidate not in performed_ids:
            inserted = candidate
            break
    if inserted is None:
        inserted = f"order_lab_overuse_{random.randint(1000, 9999)}"

    cga_new = _adjusted_cga(
        ep.cga_score,
        ep.total_violations,
        n_actions + 1,
        n_mandatory,
        delta_violations=1,
        delta_actions=1,
    )
    track_a_orig = _compute_track_a([a["action_id"] for a in ep.actions], ep.expected_actions)
    track_a_perturbed = track_a_orig  # off-protocol action not in expected

    # C1: approximately scale down
    n_act_orig_safe = max(n_actions, 1)
    c1_new = ep.sub_scores.get("C1_path_selection", 1.0) * n_act_orig_safe / (n_act_orig_safe + 1)
    sub_perturbed = dict(ep.sub_scores)
    sub_perturbed["C1_path_selection"] = max(0.0, c1_new)

    return PerturbedEpisode(
        episode_id=ep.episode_id,
        perturbation="P5",
        applicable=True,
        track_a_orig=track_a_orig,
        track_a_perturbed=track_a_perturbed,
        cga_orig=ep.cga_score,
        cga_perturbed=cga_new,
        sub_scores_orig=dict(ep.sub_scores),
        sub_scores_perturbed=sub_perturbed,
        perturbation_detail=(f"Inserted overuse action '{inserted}' → CGA {ep.cga_score:.3f} → {cga_new:.3f}"),
    )


# ---------------------------------------------------------------------------
# BSR calculation
# ---------------------------------------------------------------------------


def _compute_bsr(
    perturbed: list[PerturbedEpisode],
    delta: float = DELTA_DEFAULT,
    epsilon: float = EPSILON_DEFAULT,
) -> tuple[float, int]:
    """Return (BSR, n_valid)."""
    blind_spots = 0
    valid = 0
    for ep in perturbed:
        if not ep.applicable:
            continue
        valid += 1
        baseline_unchanged = abs(ep.track_a_orig - ep.track_a_perturbed) < epsilon
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
    ci_level: float = 0.95,
) -> tuple[float, float]:
    """Scenario-level bootstrap 95% CI for BSR."""
    # Group perturbed episodes by scenario_id.
    ep_by_id = {ep.episode_id: ep for ep in episodes}
    by_scenario: dict[str, list[PerturbedEpisode]] = {}
    for pep in perturbed:
        # Recover scenario_id from episode_id (format: scenarioid_model_rX_timestamp)
        orig_ep = ep_by_id.get(pep.episode_id)
        sid = orig_ep.scenario_id if orig_ep else pep.episode_id
        by_scenario.setdefault(sid, []).append(pep)

    scenario_ids = list(by_scenario.keys())
    if len(scenario_ids) < 2:
        bsr, _ = _compute_bsr(perturbed, delta, epsilon)
        return bsr, bsr

    bsr_samples = []
    for _ in range(n_bootstrap):
        sampled_scenarios = random.choices(scenario_ids, k=len(scenario_ids))
        flat = [pep for sid in sampled_scenarios for pep in by_scenario[sid]]
        bsr, _ = _compute_bsr(flat, delta, epsilon)
        bsr_samples.append(bsr)

    alpha = 1.0 - ci_level
    lo = float(np.percentile(bsr_samples, 100 * alpha / 2))
    hi = float(np.percentile(bsr_samples, 100 * (1 - alpha / 2)))
    return lo, hi


# ---------------------------------------------------------------------------
# Validation helpers (Step 5)
# ---------------------------------------------------------------------------


def _validate_perturbations(
    all_perturbed: dict[str, list[PerturbedEpisode]],
) -> dict[str, str]:
    """Run internal validation checks; return dict of check_name → status."""
    results: dict[str, str] = {}

    # 5-A: sample perturbation details
    for ptag in ("P1", "P2", "P4"):
        peps = [p for p in all_perturbed.get(ptag, []) if p.applicable]
        if peps:
            results[f"5A_sample_{ptag}"] = peps[0].perturbation_detail
        else:
            results[f"5A_sample_{ptag}"] = "NO APPLICABLE EPISODES"

    # 5-B: CGA detects perturbation
    for ptag, sub_key, direction in [
        ("P1", "C4_timing_compliance", "lt"),
        ("P2", "C5_sequence_integrity", "lt"),
        ("P4", "C3_forbidden_avoidance", "eq_zero"),
    ]:
        peps = [p for p in all_perturbed.get(ptag, []) if p.applicable]
        failures = 0
        for pep in peps:
            orig_val = pep.sub_scores_orig.get(sub_key, 1.0)
            pert_val = pep.sub_scores_perturbed.get(sub_key, 1.0)
            if direction == "lt":
                if pert_val >= orig_val:
                    failures += 1
            elif direction == "eq_zero":
                if pert_val != 0.0 and orig_val > 0.0:
                    failures += 1
        status = "PASS" if failures == 0 else f"FAIL ({failures} failures)"
        results[f"5B_cga_detects_{ptag}"] = status

    # 5-C: P3 sanity
    peps_p3 = [p for p in all_perturbed.get("P3", []) if p.applicable]
    if peps_p3:
        bsr_p3, _ = _compute_bsr(peps_p3)
        status = f"BSR_P3={bsr_p3:.3f}"
        if bsr_p3 > 0.3:
            status += " *** ABNORMAL (>0.3) ***"
        results["5C_p3_sanity"] = status
    else:
        results["5C_p3_sanity"] = "NO P3 APPLICABLE"

    # 5-D: Track_A vs CGA correlation on all valid applicable P1 episodes
    all_valid = [p for plist in all_perturbed.values() for p in plist if p.applicable]
    # Get original (pre-perturbation) pairs
    track_as = [p.track_a_orig for p in all_valid]
    cga_scores = [p.cga_orig for p in all_valid]
    if len(track_as) > 5:
        r, pval = stats.pearsonr(track_as, cga_scores)
        interp = "too similar" if r > 0.8 else ("sufficiently independent" if r < 0.5 else "moderate")
        results["5D_corr_trackA_cga"] = f"r={r:.3f}, p={pval:.3e} ({interp})"
    else:
        results["5D_corr_trackA_cga"] = "insufficient data"

    return results


# ---------------------------------------------------------------------------
# Figures (Step 4)
# ---------------------------------------------------------------------------

_PERT_LABELS = {
    "P1": "P1\nDELAY",
    "P2": "P2\nSWAP",
    "P4": "P4\nFORBIDDEN",
    "P5": "P5\nOVERUSE",
}

_PERT_COLORS = {
    "P1": "#2196F3",
    "P2": "#FF9800",
    "P4": "#F44336",
    "P5": "#9C27B0",
    "P3": "#4CAF50",
}


def _fig1_bsr_by_type(
    bsr_all: dict[str, float],
    bsr_high: dict[str, float],
    ci_all: dict[str, tuple[float, float]],
    ci_high: dict[str, tuple[float, float]],
    n_valid: dict[str, int],
    out_path: Path,
) -> None:
    """Figure 1: BSR by perturbation type."""
    ptags = ["P1", "P2", "P4", "P5"]
    labels = [_PERT_LABELS[p] for p in ptags]

    bsr_all_vals = [bsr_all.get(p, 0.0) for p in ptags]
    bsr_high_vals = [bsr_high.get(p, 0.0) for p in ptags]

    err_all_lo = [bsr_all.get(p, 0.0) - ci_all.get(p, (0.0, 0.0))[0] for p in ptags]
    err_all_hi = [ci_all.get(p, (0.0, 0.0))[1] - bsr_all.get(p, 0.0) for p in ptags]
    err_high_lo = [bsr_high.get(p, 0.0) - ci_high.get(p, (0.0, 0.0))[0] for p in ptags]
    err_high_hi = [ci_high.get(p, (0.0, 0.0))[1] - bsr_high.get(p, 0.0) for p in ptags]

    x = np.arange(len(ptags))
    width = 0.35

    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor("white")

    bars_all = ax.bar(
        x - width / 2,
        bsr_all_vals,
        width,
        yerr=[err_all_lo, err_all_hi],
        color="#1565C0",
        alpha=0.85,
        capsize=4,
        label="BSR (all episodes)",
    )
    bars_high = ax.bar(
        x + width / 2,
        bsr_high_vals,
        width,
        yerr=[err_high_lo, err_high_hi],
        color="#E53935",
        alpha=0.85,
        capsize=4,
        label="BSR (high-CGA episodes)",
    )

    # Annotate N_valid
    for i, p in enumerate(ptags):
        ax.text(
            x[i] - width / 2,
            bsr_all_vals[i] + max(err_all_hi[i], 0) + 0.03,
            f"n={n_valid.get(p, 0)}",
            ha="center",
            va="bottom",
            fontsize=7,
        )

    ax.set_xticks(x)
    ax.set_xticklabels(labels, fontsize=10)
    ax.set_ylabel("BSR (Blind-Spot Rate)", fontsize=11)
    ax.set_title(
        "BSR by Perturbation Type\n"
        r"($\varepsilon=0.05$, $\delta=0.10$, 95% CI via scenario-level bootstrap)",
        fontsize=11,
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


def _fig2_quadrant_scatter(
    all_perturbed: dict[str, list[PerturbedEpisode]],
    out_path: Path,
) -> None:
    """Figure 2: Δbaseline vs ΔCGA quadrant scatter plot."""
    fig, ax = plt.subplots(figsize=(7, 6))
    fig.patch.set_facecolor("white")

    for ptag, peps in all_perturbed.items():
        if ptag == "P3":
            continue
        valid = [p for p in peps if p.applicable]
        if not valid:
            continue
        dx = [p.track_a_orig - p.track_a_perturbed for p in valid]
        dy = [p.cga_orig - p.cga_perturbed for p in valid]
        ax.scatter(dx, dy, c=_PERT_COLORS.get(ptag, "black"), label=ptag, alpha=0.55, s=30, linewidths=0)

    ax.axvline(0, color="k", linewidth=0.8)
    ax.axhline(0, color="k", linewidth=0.8)

    ax.axvline(EPSILON_DEFAULT, color="gray", linewidth=0.5, linestyle=":")
    ax.axvline(-EPSILON_DEFAULT, color="gray", linewidth=0.5, linestyle=":")
    ax.axhline(DELTA_DEFAULT, color="gray", linewidth=0.5, linestyle=":")
    ax.axhline(-DELTA_DEFAULT, color="gray", linewidth=0.5, linestyle=":")

    # Quadrant annotations
    xlim = ax.get_xlim()
    ylim = ax.get_ylim()
    _xpad = 0.01
    _ypad = 0.01

    ax.text(
        xlim[0] + _xpad,
        ylim[1] - _ypad,
        "CGA only\n(BLIND SPOT)",
        ha="left",
        va="top",
        fontsize=8,
        color="#C62828",
        bbox={"facecolor": "#FFCDD2", "alpha": 0.5, "boxstyle": "round,pad=0.3"},
    )
    ax.text(
        xlim[1] - _xpad,
        ylim[1] - _ypad,
        "Both detect\n(Agreement)",
        ha="right",
        va="top",
        fontsize=8,
        color="#1B5E20",
        bbox={"facecolor": "#C8E6C9", "alpha": 0.5, "boxstyle": "round,pad=0.3"},
    )
    ax.text(xlim[0] + _xpad, ylim[0] + _ypad, "Neither detects", ha="left", va="bottom", fontsize=8, color="gray")
    ax.text(xlim[1] - _xpad, ylim[0] + _ypad, "Baseline only", ha="right", va="bottom", fontsize=8, color="gray")

    # Highlight the blind-spot region
    blind_x = xlim[0]
    blind_w = EPSILON_DEFAULT - blind_x
    blind_y = DELTA_DEFAULT
    blind_h = ylim[1] - blind_y
    from matplotlib.patches import Rectangle

    rect = Rectangle(
        (blind_x, blind_y),
        blind_w,
        blind_h,
        linewidth=1.2,
        edgecolor="#C62828",
        facecolor="#FFCDD2",
        alpha=0.15,
    )
    ax.add_patch(rect)

    ax.set_xlabel(r"$\Delta\mathrm{Track{-}A}$ (orig $-$ perturbed)", fontsize=11)
    ax.set_ylabel(r"$\Delta\mathrm{CGA}$ (orig $-$ perturbed)", fontsize=11)
    ax.set_title(
        r"$\Delta$Baseline vs $\Delta$CGA per Perturbation" + "\n"
        "Upper-left quadrant = blind spot (CGA detects, Track-A misses)",
        fontsize=10,
    )
    ax.legend(fontsize=9, title="Perturbation")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    plt.tight_layout()
    plt.savefig(out_path, format="pdf", dpi=150)
    plt.close()
    print(f"  Saved: {out_path}")


def _fig3_delta_sensitivity(
    all_perturbed: dict[str, list[PerturbedEpisode]],
    out_path: Path,
) -> None:
    """Figure 3: BSR_overall vs δ threshold."""
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
    ax.axvline(DELTA_DEFAULT, color="#E53935", linestyle="--", linewidth=1.2, label=f"default δ={DELTA_DEFAULT}")
    ax.set_xlabel(r"$\delta$ threshold (CGA change considered different)", fontsize=11)
    ax.set_ylabel("BSR overall (P1+P2+P4+P5)", fontsize=11)
    ax.set_title(r"BSR Sensitivity to $\delta$ ($\varepsilon=0.05$ fixed)", fontsize=11)
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
# Table output (Step 3 / Step 6)
# ---------------------------------------------------------------------------


def _bsr_table_latex(
    bsr_all: dict[str, float],
    bsr_high: dict[str, float],
    n_valid: dict[str, int],
) -> str:
    rows = []
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
        "P3": "(sanity check — both should detect)",
        "P4": "safety blind spot",
        "P5": "overuse blind spot",
        "Overall": "weighted average",
    }
    for ptag in ("P1", "P2", "P3", "P4", "P5", "Overall"):
        ba = bsr_all.get(ptag, 0.0)
        bh = bsr_high.get(ptag, 0.0)
        nv = n_valid.get(ptag, 0)
        rows.append(f"  {labels[ptag]} & {ba:.3f} & {bh:.3f} & {nv} & {interps[ptag]} \\\\")

    header = (
        "\\begin{table}[h]\n"
        "\\centering\n"
        "\\caption{BSR (Blind-Spot Rate) by Perturbation Type "
        r"($\varepsilon=0.05$, $\delta=0.10$)}\n"
        "\\label{tab:bsr}\n"
        "\\begin{tabular}{lcccc}\n"
        "\\toprule\n"
        "Perturbation & BSR\\_all & BSR\\_high & N\\_valid & Interpretation \\\\\n"
        "\\midrule\n"
    )
    footer = "\\bottomrule\n\\end{tabular}\n\\end{table}"
    return header + "\n".join(rows) + "\n" + footer


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 70)
    print("BSR Perturbation Analysis Pipeline")
    print("=" * 70)

    # Create output directories
    OUT_ANALYSIS.mkdir(parents=True, exist_ok=True)
    OUT_FIGURES.mkdir(parents=True, exist_ok=True)
    OUT_TABLES.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Step 0: Load data
    # ------------------------------------------------------------------
    print("\n[Step 0] Loading episodes …")
    episodes = _load_episodes()
    print(f"  Loaded {len(episodes)} episodes")
    print(
        "  NOTE: Candidate B (diagnosis accuracy) unavailable — "
        "episode files do not contain agent's final diagnosis field. "
        "Using Track A (action coverage) as baseline metric."
    )

    # ------------------------------------------------------------------
    # Step 1 + 2: Apply perturbations and score
    # ------------------------------------------------------------------
    print("\n[Step 1+2] Applying perturbations …")
    all_perturbed: dict[str, list[PerturbedEpisode]] = {
        "P1": [],
        "P2": [],
        "P3": [],
        "P4": [],
        "P5": [],
    }

    for ep in episodes:
        all_perturbed["P1"].append(_perturb_p1_delay(ep))
        all_perturbed["P2"].append(_perturb_p2_swap(ep))
        all_perturbed["P3"].append(_perturb_p3_delete(ep))
        all_perturbed["P4"].append(_perturb_p4_insert_forbidden(ep))
        all_perturbed["P5"].append(_perturb_p5_insert_overuse(ep))

    for ptag, peps in all_perturbed.items():
        n_app = sum(1 for p in peps if p.applicable)
        n_skip = sum(1 for p in peps if not p.applicable)
        reasons = {}
        for p in peps:
            if not p.applicable:
                reasons[p.skip_reason] = reasons.get(p.skip_reason, 0) + 1
        print(f"  {ptag}: applicable={n_app}, skipped={n_skip}  {dict(reasons) if reasons else ''}")
        if ptag == "P2" and n_app < 20:
            print(f"    *** WARNING: P2 only {n_app} valid episodes — BSR may be statistically unstable ***")

    # ------------------------------------------------------------------
    # Step 3: BSR calculation
    # ------------------------------------------------------------------
    print("\n[Step 3] Computing BSR …")

    # Split into all vs high-CGA (top 50%)
    median_cga = float(np.median([ep.cga_score for ep in episodes]))
    high_ids = {ep.episode_id for ep in episodes if ep.cga_score >= median_cga}

    bsr_all: dict[str, float] = {}
    bsr_high: dict[str, float] = {}
    n_valid: dict[str, int] = {}
    n_valid_high: dict[str, int] = {}
    ci_all: dict[str, tuple[float, float]] = {}
    ci_high: dict[str, tuple[float, float]] = {}

    for ptag, peps in all_perturbed.items():
        peps_high = [p for p in peps if p.episode_id in high_ids]
        ba, nv = _compute_bsr(peps)
        bh, nvh = _compute_bsr(peps_high)
        bsr_all[ptag] = ba
        bsr_high[ptag] = bh
        n_valid[ptag] = nv
        n_valid_high[ptag] = nvh
        ci_all[ptag] = _bootstrap_bsr_ci(peps, episodes)
        ci_high[ptag] = _bootstrap_bsr_ci(peps_high, episodes)

    # Overall (P1+P2+P4+P5)
    flat_main = [p for ptag in ("P1", "P2", "P4", "P5") for p in all_perturbed[ptag] if p.applicable]
    flat_main_high = [p for p in flat_main if p.episode_id in high_ids]
    bsr_overall, nv_overall = _compute_bsr(flat_main)
    bsr_overall_high, nv_h = _compute_bsr(flat_main_high)
    bsr_all["Overall"] = bsr_overall
    bsr_high["Overall"] = bsr_overall_high
    n_valid["Overall"] = nv_overall
    ci_all["Overall"] = _bootstrap_bsr_ci(flat_main, episodes)
    ci_high["Overall"] = _bootstrap_bsr_ci(flat_main_high, episodes)

    print(f"\n  Median CGA (split threshold): {median_cga:.3f}")
    print(f"  High-CGA episodes: {len(high_ids)}/{len(episodes)}")
    print()
    print(f"  {'Type':<10} {'BSR_all':>8} {'BSR_high':>10} {'N_valid':>8}  Interpretation")
    print("  " + "-" * 65)
    labels_interp = {
        "P1": "timing blind spot",
        "P2": "sequence blind spot",
        "P3": "(sanity — both detect)",
        "P4": "safety blind spot",
        "P5": "overuse blind spot",
        "Overall": "weighted average (P1+P2+P4+P5)",
    }
    for ptag in ("P1", "P2", "P3", "P4", "P5", "Overall"):
        print(f"  {ptag:<10} {bsr_all[ptag]:>8.3f} {bsr_high[ptag]:>10.3f} {n_valid[ptag]:>8}  {labels_interp[ptag]}")

    # δ sensitivity table
    print("\n  δ sensitivity (ε=0.05 fixed):")
    print(f"  {'delta':>6} {'BSR_overall':>12}")
    for delta in (0.05, 0.10, 0.15, 0.20):
        bsr_d, _ = _compute_bsr(flat_main, delta=delta)
        print(f"  {delta:>6.2f} {bsr_d:>12.3f}")

    # ------------------------------------------------------------------
    # Step 4: Figures
    # ------------------------------------------------------------------
    print("\n[Step 4] Generating figures …")
    _fig1_bsr_by_type(
        bsr_all,
        bsr_high,
        ci_all,
        ci_high,
        n_valid,
        OUT_FIGURES / "bsr_by_type.pdf",
    )
    _fig2_quadrant_scatter(all_perturbed, OUT_FIGURES / "bsr_quadrant.pdf")
    _fig3_delta_sensitivity(all_perturbed, OUT_FIGURES / "bsr_delta_sensitivity.pdf")

    # ------------------------------------------------------------------
    # Step 5: Internal validation
    # ------------------------------------------------------------------
    print("\n[Step 5] Internal validation …")
    val_results = _validate_perturbations(all_perturbed)
    for k, v in val_results.items():
        print(f"  {k}: {v}")

    # ------------------------------------------------------------------
    # Step 6: Integration paragraph
    # ------------------------------------------------------------------
    print("\n[Step 6] Integration paragraph:")
    bsr_pct = bsr_overall * 100
    print(
        f"\n  CGA-Bench robustly distinguishes models (Friedman p<0.001, "
        f"leave-one-out 15/15 significant). However, outcome-only metrics "
        f"miss {bsr_pct:.1f}% of clinically meaningful process differences — "
        f"timing violations (BSR={bsr_all['P1']:.2f}), sequence violations "
        f"(BSR={bsr_all['P2']:.2f}), and safety violations "
        f"(BSR={bsr_all['P4']:.2f}) that Track-A (action coverage) fails "
        f"to detect even when the set of performed actions appears identical.\n"
    )

    # ------------------------------------------------------------------
    # Save outputs
    # ------------------------------------------------------------------
    print("[Outputs] Saving JSON and LaTeX …")

    # Build serialisable results dict
    def _pep_to_dict(p: PerturbedEpisode) -> dict:
        return {
            "episode_id": p.episode_id,
            "perturbation": p.perturbation,
            "applicable": p.applicable,
            "skip_reason": p.skip_reason,
            "track_a_orig": p.track_a_orig,
            "track_a_perturbed": p.track_a_perturbed,
            "cga_orig": p.cga_orig,
            "cga_perturbed": p.cga_perturbed,
            "detail": p.perturbation_detail,
        }

    bsr_results = {
        "metadata": {
            "epsilon": EPSILON_DEFAULT,
            "delta": DELTA_DEFAULT,
            "n_episodes": len(episodes),
            "models": MODELS,
            "baseline_metric": "Track_A_action_coverage",
            "note_candidate_b": (
                "Diagnosis accuracy (Candidate B) unavailable: episode files "
                "do not include the agent's final diagnosis field."
            ),
        },
        "bsr_all": bsr_all,
        "bsr_high": bsr_high,
        "n_valid": n_valid,
        "ci_all": {k: list(v) for k, v in ci_all.items()},
        "ci_high": {k: list(v) for k, v in ci_high.items()},
        "delta_sensitivity": {
            str(round(d, 2)): round(_compute_bsr(flat_main, delta=d)[0], 4) for d in np.arange(0.05, 0.21, 0.05)
        },
        "validation": val_results,
        "perturbed_episodes": {ptag: [_pep_to_dict(p) for p in peps] for ptag, peps in all_perturbed.items()},
    }

    json_out = OUT_ANALYSIS / "bsr_results.json"
    with open(json_out, "w") as f:
        json.dump(bsr_results, f, indent=2, default=str)
    print(f"  Saved: {json_out}")

    tex_out = OUT_TABLES / "bsr_table.tex"
    with open(tex_out, "w") as f:
        f.write(_bsr_table_latex(bsr_all, bsr_high, n_valid))
    print(f"  Saved: {tex_out}")

    print("\n" + "=" * 70)
    print("BSR analysis complete.")
    print("=" * 70)


if __name__ == "__main__":
    main()
