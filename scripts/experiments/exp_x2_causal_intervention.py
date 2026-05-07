#!/usr/bin/env python3
"""Experiment X2: Violation-event ablation on hard-violation traces.

Defense target: A1 "TCC reduces to morphology" — reinforcement of X1.
For each hard-violation episode, ablate the trace's violation-carrying
action AND its paired violation_event record, then re-score. TCC's
v4_hard is computed from violation_events (see _episode_cache.score_
episode), so the ablation is a verdict-driving intervention by
construction on the single-hard stratum; the interesting measurement
is the morphology classifier's response. If TCC were reducible to
morphology, the classifier should flip at a comparable rate; it does
not (morph flip << TCC flip on single-hard), showing aggregate
morphological features are insensitive to single-event changes.

Note on naming: earlier drafts called this experiment a "single-action
causal intervention". The honest framing is "violation-event ablation":
the scorer reads violation_events, the ablation removes the matched
record, so TCC flip on single-hard is mechanical. The substantive
result is the TCC-vs-morph GAP (+0.828 on single_hard, +0.416 overall
excluding orphans), not the absolute TCC flip rate.

Methodology:
    1. Train CRES-1D coverage-free morphology classifier on ALL episodes.
    2. Filter episodes with v4_hard == 1.
    3. For each hard-violation episode E:
         a. Pick the first hard-type violation_event (commission|timing|sequence).
         b. Build E' = E minus (the triggering action, the violation_event).
         c. TCC verdict flip = (score_episode(E').v4_hard != E.v4_hard).
         d. Morphology flip  = (clf.predict(E').pred != clf.predict(E).pred).
    4. Paired McNemar test on (tcc_flip, morph_flip).

Success criteria:
    - TCC flip rate >= 0.70 (target per defense doc)
    - Morphology flip rate < 0.20
    - Mean gap (tcc - morph) with 95% CI excluding 0

Outputs:
    evidence_pack/ex_x2_causal_intervention/
        ex_x2_results.json
        ex_x2_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/exp_x2_causal_intervention.py
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
    HARD_VIOL_TYPES,
    _classify_violation_type,
    load_cached_episodes,
    score_episode,
)
from scripts.experiments.exp_cres_1d_feature_classifier import (  # noqa: E402
    COVERAGE_FEATURE_NAMES,
    VIOLATION_FEATURE_NAMES,
    build_feature_matrix,
    extract_features,
    train_full_model,
)

logger = logging.getLogger(__name__)

OUTPUT_DIR = EVIDENCE_DIR / "ex_x2_causal_intervention"
TCC_FLIP_THRESHOLD = 0.70
MORPH_FLIP_THRESHOLD = 0.20
BOOTSTRAP_N = 1000
RNG_SEED = 42
MAX_PERTURBATIONS_PER_EPISODE = 1


def first_hard_violation(ep: dict[str, Any]) -> dict[str, Any] | None:
    """Return first violation event with type in HARD_VIOL_TYPES, or None."""
    for v in ep.get("violation_events") or []:
        if not isinstance(v, dict):
            continue
        vtype = _classify_violation_type(str(v.get("violation_type", "")))
        if vtype in HARD_VIOL_TYPES:
            return v
    return None


def perturb_remove_action(ep: dict[str, Any], target_action_id: str) -> tuple[dict[str, Any], bool]:
    """Return (perturbed_episode, action_actually_removed).

    Remove the first matching action from actions list AND remove violation
    events referencing that action. action_actually_removed=False when the
    target_action_id appears in violation_events.action_involved but NOT in
    ep.actions (orphan case — happens when assessor synthesizes a violation
    referencing an action that was never performed, ~6% of single-hard
    episodes in v5 data).
    """
    new_actions: list[dict[str, Any]] = []
    removed_one = False
    for a in ep.get("actions") or []:
        aid = a.get("action_id", "") if isinstance(a, dict) else ""
        if not removed_one and aid == target_action_id:
            removed_one = True
            continue
        new_actions.append(a)
    new_violations = [
        v
        for v in (ep.get("violation_events") or [])
        if not (isinstance(v, dict) and v.get("action_involved") == target_action_id)
    ]
    perturbed = dict(ep)
    perturbed["actions"] = new_actions
    perturbed["violation_events"] = new_violations
    return perturbed, removed_one


def _pick_clean_indices(feature_names: list[str]) -> list[int]:
    """Return column indices excluding leakage-prone violation + coverage features."""
    drop = set(VIOLATION_FEATURE_NAMES) | set(COVERAGE_FEATURE_NAMES)
    return [i for i, n in enumerate(feature_names) if n not in drop]


def _features_vector(ep: dict[str, Any], feature_names: list[str], keep: list[int]) -> np.ndarray:
    """Extract coverage-free feature vector for one episode."""
    feats = extract_features(ep)
    row = np.array([feats.get(n, 0.0) for n in feature_names], dtype=np.float64)
    return row[keep].reshape(1, -1)


def _count_hard_violations(ep: dict[str, Any]) -> int:
    """Count distinct hard-type violations in an episode."""
    n = 0
    for v in ep.get("violation_events") or []:
        if not isinstance(v, dict):
            continue
        if _classify_violation_type(str(v.get("violation_type", ""))) in HARD_VIOL_TYPES:
            n += 1
    return n


def _violation_action_ids(ep: dict[str, Any]) -> set[str]:
    """Return set of action_ids tied to any violation_event (hard or soft)."""
    out: set[str] = set()
    for v in ep.get("violation_events") or []:
        if isinstance(v, dict):
            aid = v.get("action_involved") or ""
            if aid:
                out.add(aid)
    return out


def run_placebo_perturbation(
    ep: dict[str, Any],
    clf: Any,
    feature_names: list[str],
    keep_idx: list[int],
    rng: np.random.Generator,
) -> dict[str, Any] | None:
    """Placebo: remove a RANDOM non-violation action from the trace.

    Differentiates TCC's violation-specific sensitivity from "TCC flips on
    any action removal". If TCC is specific to the violation event, placebo
    flip rate should be near 0. Morph classifier flip rate should be
    comparable to the treatment (morph is insensitive to any single-action
    change).
    """
    performed_list = [
        a.get("action_id", "") for a in (ep.get("actions") or []) if isinstance(a, dict) and a.get("action_id")
    ]
    viol_actions = _violation_action_ids(ep)
    candidates = [a for a in performed_list if a not in viol_actions]
    if not candidates:
        return None
    target = str(rng.choice(candidates))

    sc_orig = score_episode(ep)
    ep_perturbed, action_removed = perturb_remove_action(ep, target)
    sc_pert = score_episode(ep_perturbed)

    x_orig = _features_vector(ep, feature_names, keep_idx)
    x_pert = _features_vector(ep_perturbed, feature_names, keep_idx)
    morph_orig = int(clf.predict(x_orig)[0])
    morph_pert = int(clf.predict(x_pert)[0])

    return {
        "scenario_id": ep.get("scenario_id"),
        "run_index": ep.get("run_index"),
        "model": ep.get("_model"),
        "removed_action": target,
        "action_actually_removed": int(action_removed),
        "n_hard_violations_orig": _count_hard_violations(ep),
        "tcc_before": int(sc_orig["v4_hard"]),
        "tcc_after": int(sc_pert["v4_hard"]),
        "tcc_flipped": int(sc_orig["v4_hard"] != sc_pert["v4_hard"]),
        "morph_before": morph_orig,
        "morph_after": morph_pert,
        "morph_flipped": int(morph_orig != morph_pert),
    }


def run_perturbation(
    ep: dict[str, Any],
    clf: Any,
    feature_names: list[str],
    keep_idx: list[int],
) -> dict[str, Any] | None:
    """Perturb one hard-violation action from episode; return flip stats or None."""
    viol = first_hard_violation(ep)
    if viol is None:
        return None
    action_id = viol.get("action_involved") or ""
    if not action_id:
        return None
    vtype = _classify_violation_type(str(viol.get("violation_type", "")))

    sc_orig = score_episode(ep)
    n_hard_orig = _count_hard_violations(ep)
    ep_perturbed, action_removed = perturb_remove_action(ep, action_id)
    sc_pert = score_episode(ep_perturbed)

    x_orig = _features_vector(ep, feature_names, keep_idx)
    x_pert = _features_vector(ep_perturbed, feature_names, keep_idx)
    morph_orig = int(clf.predict(x_orig)[0])
    morph_pert = int(clf.predict(x_pert)[0])

    return {
        "scenario_id": ep.get("scenario_id"),
        "run_index": ep.get("run_index"),
        "model": ep.get("_model"),
        "violation_type": vtype,
        "removed_action": action_id,
        "action_actually_removed": int(action_removed),
        "n_hard_violations_orig": n_hard_orig,
        "tcc_before": int(sc_orig["v4_hard"]),
        "tcc_after": int(sc_pert["v4_hard"]),
        "tcc_flipped": int(sc_orig["v4_hard"] != sc_pert["v4_hard"]),
        "morph_before": morph_orig,
        "morph_after": morph_pert,
        "morph_flipped": int(morph_orig != morph_pert),
    }


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate flip-rate statistics + McNemar + bootstrap CI."""
    if not records:
        return {}
    tcc = np.array([r["tcc_flipped"] for r in records], dtype=np.int8)
    morph = np.array([r["morph_flipped"] for r in records], dtype=np.int8)
    gap = tcc.astype(float) - morph.astype(float)
    n = len(records)
    tcc_rate = float(tcc.mean())
    morph_rate = float(morph.mean())

    # McNemar: discordant pairs
    b = int(np.sum((tcc == 1) & (morph == 0)))
    c = int(np.sum((tcc == 0) & (morph == 1)))
    mcnemar = (b - c) ** 2 / (b + c) if (b + c) > 0 else 0.0

    # Bootstrap CI on mean gap
    rng = np.random.default_rng(RNG_SEED)
    boot = [float(np.mean(gap[rng.integers(0, n, n)])) for _ in range(BOOTSTRAP_N)]
    ci_lo = float(np.percentile(boot, 2.5))
    ci_hi = float(np.percentile(boot, 97.5))

    return {
        "n_episodes": n,
        "tcc_flip_rate": round(tcc_rate, 4),
        "morph_flip_rate": round(morph_rate, 4),
        "gap_mean": round(float(gap.mean()), 4),
        "gap_ci_lo": round(ci_lo, 4),
        "gap_ci_hi": round(ci_hi, 4),
        "mcnemar_b": b,
        "mcnemar_c": c,
        "mcnemar_stat": round(mcnemar, 4),
        "criterion_tcc_met": tcc_rate >= TCC_FLIP_THRESHOLD,
        "criterion_morph_met": morph_rate < MORPH_FLIP_THRESHOLD,
        "criterion_ci_excludes_zero": ci_lo > 0.0,
    }


def stratified_by_type(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Per-violation-type flip rate stratification."""
    out: dict[str, Any] = {}
    for vt in ("commission", "timing", "sequence"):
        subset = [r for r in records if r["violation_type"] == vt]
        out[vt] = aggregate(subset)
    return out


def stratified_by_n_hard(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Stratify by number of hard violations in original episode.

    Expected: single-hard-violation episodes should flip at near-100%
    (the removed action IS the sole hard event), while multi-violation
    episodes flip at lower rates because other violations remain.
    """
    single = [r for r in records if r["n_hard_violations_orig"] == 1]
    multi = [r for r in records if r["n_hard_violations_orig"] > 1]
    return {
        "single_hard": aggregate(single),
        "multi_hard": aggregate(multi),
    }


def write_macros(
    agg: dict[str, Any],
    strat: dict[str, Any],
    output_path: Path,
    strat_n: dict[str, Any] | None = None,
    placebo: dict[str, Any] | None = None,
) -> None:
    """Emit LaTeX macros for the X2 numerical claims."""
    lines = [
        "% Experiment X2: causal intervention — auto-generated macros",
        "% DO NOT EDIT — regenerate with exp_x2_causal_intervention.py",
        "",
        f"\\providecommand{{\\xTwoNEpisodes}}{{{agg['n_episodes']}}}",
        f"\\providecommand{{\\xTwoTccFlipRate}}{{{agg['tcc_flip_rate']:.3f}}}",
        f"\\providecommand{{\\xTwoMorphFlipRate}}{{{agg['morph_flip_rate']:.3f}}}",
        f"\\providecommand{{\\xTwoGapMean}}{{{agg['gap_mean']:+.3f}}}",
        f"\\providecommand{{\\xTwoGapLo}}{{{agg['gap_ci_lo']:+.3f}}}",
        f"\\providecommand{{\\xTwoGapHi}}{{{agg['gap_ci_hi']:+.3f}}}",
        f"\\providecommand{{\\xTwoMcNemarStat}}{{{agg['mcnemar_stat']:.2f}}}",
        "",
        "% Per violation type",
    ]
    for vt, s in strat.items():
        if not s:
            continue
        short = vt[:4].capitalize()
        lines.append(f"\\providecommand{{\\xTwoNEpisodes{short}}}{{{s['n_episodes']}}}")
        lines.append(f"\\providecommand{{\\xTwoTccFlipRate{short}}}{{{s['tcc_flip_rate']:.3f}}}")
        lines.append(f"\\providecommand{{\\xTwoMorphFlipRate{short}}}{{{s['morph_flip_rate']:.3f}}}")
    if strat_n:
        lines.append("")
        lines.append("% Stratified by #hard-violations in original")
        for key, s in strat_n.items():
            if not s:
                continue
            short = "Single" if key == "single_hard" else "Multi"
            lines.append(f"\\providecommand{{\\xTwoNEpisodes{short}}}{{{s['n_episodes']}}}")
            lines.append(f"\\providecommand{{\\xTwoTccFlipRate{short}}}{{{s['tcc_flip_rate']:.3f}}}")
            lines.append(f"\\providecommand{{\\xTwoMorphFlipRate{short}}}{{{s['morph_flip_rate']:.3f}}}")
            lines.append(f"\\providecommand{{\\xTwoGapMean{short}}}{{{s['gap_mean']:+.3f}}}")
    if placebo:
        lines.append("")
        lines.append("% Placebo: random non-violation action removal")
        lines.append(f"\\providecommand{{\\xTwoPlaceboNEpisodes}}{{{placebo['n_episodes']}}}")
        lines.append(f"\\providecommand{{\\xTwoPlaceboTccFlipRate}}{{{placebo['tcc_flip_rate']:.3f}}}")
        lines.append(f"\\providecommand{{\\xTwoPlaceboMorphFlipRate}}{{{placebo['morph_flip_rate']:.3f}}}")
        lines.append(f"\\providecommand{{\\xTwoPlaceboGapMean}}{{{placebo['gap_mean']:+.3f}}}")
        diff_tcc = agg["tcc_flip_rate"] - placebo["tcc_flip_rate"]
        lines.append(f"\\providecommand{{\\xTwoTreatmentMinusPlaceboTcc}}{{{diff_tcc:+.3f}}}")
    lines.append("")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    print(f"  Saved: {output_path}")


def _print_summary(agg: dict[str, Any], strat: dict[str, Any], strat_n: dict[str, Any]) -> None:
    """Terminal summary table."""
    print("\n" + "=" * 70)
    print("X2: VIOLATION-EVENT ABLATION SUMMARY")
    print("=" * 70)
    print(f"  n_episodes (hard-violation, perturbed): {agg['n_episodes']}")
    print(f"  TCC flip rate:     {agg['tcc_flip_rate']:.4f}  (target >= {TCC_FLIP_THRESHOLD})")
    print(f"  Morph flip rate:   {agg['morph_flip_rate']:.4f}  (target <  {MORPH_FLIP_THRESHOLD})")
    print(f"  Gap (tcc-morph):   {agg['gap_mean']:+.4f}  95% CI [{agg['gap_ci_lo']:+.4f}, {agg['gap_ci_hi']:+.4f}]")
    print(f"  McNemar stat:      {agg['mcnemar_stat']:.2f}  (b={agg['mcnemar_b']}, c={agg['mcnemar_c']})")
    crit_tcc = "PASS" if agg["criterion_tcc_met"] else "FAIL"
    crit_morph = "PASS" if agg["criterion_morph_met"] else "FAIL"
    crit_ci = "PASS" if agg["criterion_ci_excludes_zero"] else "FAIL"
    print(f"  A (TCC flip >= {TCC_FLIP_THRESHOLD}): {crit_tcc}")
    print(f"  B (Morph flip < {MORPH_FLIP_THRESHOLD}): {crit_morph}")
    print(f"  C (95% CI excludes 0): {crit_ci}")
    print()
    print("  Per violation type:")
    print(f"  {'vtype':<12} {'n':>6} {'TCC':>7} {'Morph':>7} {'Gap':>8}")
    for vt, s in strat.items():
        if not s:
            print(f"  {vt:<12} (no episodes)")
            continue
        print(
            f"  {vt:<12} {s['n_episodes']:>6} {s['tcc_flip_rate']:>7.3f} "
            f"{s['morph_flip_rate']:>7.3f} {s['gap_mean']:>+8.3f}"
        )
    print()
    print("  Stratified by #hard-violations in original episode:")
    print(f"  {'stratum':<12} {'n':>6} {'TCC':>7} {'Morph':>7} {'Gap':>8}")
    for name, s in strat_n.items():
        if not s:
            print(f"  {name:<12} (no episodes)")
            continue
        print(
            f"  {name:<12} {s['n_episodes']:>6} {s['tcc_flip_rate']:>7.3f} "
            f"{s['morph_flip_rate']:>7.3f} {s['gap_mean']:>+8.3f}"
        )
    print("=" * 70)


def main() -> int:
    """Run X2 causal intervention on hard-violation episodes."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    print("Loading episodes...")
    episodes = load_cached_episodes()
    print(f"  Loaded {len(episodes)} episodes")
    if not episodes:
        logger.error("No episodes — aborting")
        return 1

    print("Building feature matrix + training coverage-free morphology classifier...")
    X, y, feature_names, _ = build_feature_matrix(episodes)
    keep_idx = _pick_clean_indices(feature_names)
    X_keep = X[:, keep_idx]
    print(f"  X: {X.shape}, kept {len(keep_idx)} coverage-free features")
    clf = train_full_model(X_keep, y)

    print("Running single-action perturbations on hard-violation episodes...")
    scored_all = [score_episode(ep) for ep in episodes]
    hard_episodes = [ep for ep, sc in zip(episodes, scored_all) if sc["v4_hard"]]
    print(f"  {len(hard_episodes)} episodes have v4_hard=1 (perturbation targets)")

    records: list[dict[str, Any]] = []
    for ep in hard_episodes:
        rec = run_perturbation(ep, clf, feature_names, keep_idx)
        if rec is not None:
            records.append(rec)
    print(f"  Generated {len(records)} treatment perturbation records")

    print("Running PLACEBO perturbations (random non-violation action)...")
    placebo_rng = np.random.default_rng(RNG_SEED)
    placebo_records: list[dict[str, Any]] = []
    for ep in hard_episodes:
        rec = run_placebo_perturbation(ep, clf, feature_names, keep_idx, placebo_rng)
        if rec is not None:
            placebo_records.append(rec)
    print(f"  Generated {len(placebo_records)} placebo records")

    # HONEST aggregate: only include perturbations where the target action
    # was actually present in the trace. ~5.9% of hard-violation episodes
    # reference a target action_involved that is NOT in ep.actions (assessor
    # synthesized the violation without a matching action record). For those
    # "orphan" cases, removing the target is a no-op on the action list and
    # only filters the violation_events record. Those flips are bookkeeping
    # artifacts, not causal action interventions.
    honest_records = [r for r in records if r.get("action_actually_removed") == 1]
    n_orphans = len(records) - len(honest_records)
    print(f"  {n_orphans} orphan perturbations (action not in trace) excluded from honest aggregate")

    agg_all = aggregate(records)
    agg = aggregate(honest_records)
    strat = stratified_by_type(honest_records)
    strat_n = stratified_by_n_hard(honest_records)
    _print_summary(agg, strat, strat_n)

    # Placebo aggregate (honest-filtered)
    placebo_honest = [r for r in placebo_records if r.get("action_actually_removed") == 1]
    agg_placebo = aggregate(placebo_honest)
    print("\n" + "=" * 70)
    print("X2-PLACEBO: Random non-violation action removal")
    print("=" * 70)
    if agg_placebo:
        print(
            f"  n={agg_placebo['n_episodes']}  "
            f"TCC flip={agg_placebo['tcc_flip_rate']:.4f}  "
            f"Morph flip={agg_placebo['morph_flip_rate']:.4f}  "
            f"gap={agg_placebo['gap_mean']:+.4f} [{agg_placebo['gap_ci_lo']:+.4f}, {agg_placebo['gap_ci_hi']:+.4f}]"
        )
        diff_tcc = agg["tcc_flip_rate"] - agg_placebo["tcc_flip_rate"]
        print(
            f"  Treatment-vs-placebo TCC flip diff: {diff_tcc:+.4f}  "
            f"(TCC is specific to violation action iff this is large)"
        )
    print("=" * 70)
    print(
        f"\n  (Pooled over ALL {len(records)} perturbations including orphans: "
        f"TCC {agg_all['tcc_flip_rate']:.3f}, Morph {agg_all['morph_flip_rate']:.3f})"
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(
        {
            "experiment": "X2: causal intervention",
            "defense_target": "A1 (reinforcement)",
            "n_episodes_total": len(episodes),
            "n_hard_violation_episodes": len(hard_episodes),
            "n_perturbations": len(records),
            "thresholds": {
                "tcc_flip_min": TCC_FLIP_THRESHOLD,
                "morph_flip_max": MORPH_FLIP_THRESHOLD,
                "bootstrap_n": BOOTSTRAP_N,
                "rng_seed": RNG_SEED,
            },
            "morphology_feature_set": "coverage_free (excludes violation + coverage features)",
            "n_morph_features_used": len(keep_idx),
            "n_orphan_excluded": n_orphans,
            "aggregate": agg,  # honest subset (action actually removed)
            "aggregate_pooled_incl_orphans": agg_all,
            "stratified_by_type": strat,
            "stratified_by_n_hard": strat_n,
            "placebo_aggregate": agg_placebo,
            "per_episode": records,
            "per_episode_placebo": placebo_records,
        },
        OUTPUT_DIR / "ex_x2_results.json",
    )
    write_macros(agg, strat, OUTPUT_DIR / "ex_x2_macros.tex", strat_n=strat_n, placebo=agg_placebo)
    print(f"\nOutputs: {OUTPUT_DIR}")
    return 0 if agg["criterion_tcc_met"] and agg["criterion_morph_met"] else 2


if __name__ == "__main__":
    sys.exit(main())
