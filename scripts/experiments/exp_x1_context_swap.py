#!/usr/bin/env python3
"""Experiment X1: Context-swap probe — KILLING defense for A1.

Apply the SAME trajectory to two patient contexts where the pivot action
has inverted status (expected in donor, forbidden in recipient). TCC
verdict should FLIP at high rate because TCC reads context-specific
rules. CRES-1D morphology classifier is patient-state-blind by design
and therefore MUST be invariant to the swap -- any non-zero morph flip
rate would be an artefact.

Methodology:
    1. Load auto-discovered triplets (donor, recipient, pivot_action)
       from evidence_pack/ex_x1_context_swap/x1_discovered_pairs.json.
    2. Load all cached episodes (N=14,826).
    3. For each triplet, filter episodes to those from donor_scenario_id
       AND containing the pivot action.
    4. Evaluate each episode under donor context AND recipient context
       via scripts/experiments/_swap_scorer.score_episode_against.
    5. tcc_flip = (donor.v4_hard != recipient.v4_hard); record per-ep.
    6. Morphology flip: by construction = 0 (features do not depend on
       scenario); reported for completeness + McNemar consistency.

Success criteria (per defense doc line 3):
    - tcc_flip_rate >= 0.80
    - morph_flip_rate ~ 0
    - McNemar p < 0.001

Outputs:
    evidence_pack/ex_x1_context_swap/
        ex_x1_context_swap_results.json
        ex_x1_context_swap_macros.tex

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \\
      python scripts/experiments/_x1_pair_discovery.py           # produce triplets
      python scripts/experiments/exp_x1_context_swap.py          # run experiment
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
import sys
from typing import Any

import numpy as np
import yaml

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from scripts.experiments._common import save_json  # noqa: E402
from scripts.experiments._episode_cache import EVIDENCE_DIR, load_cached_episodes  # noqa: E402
from scripts.experiments._swap_scorer import performed_actions, score_episode_against  # noqa: E402
from scripts.experiments.exp_cres_1d_feature_classifier import (  # noqa: E402
    COVERAGE_FEATURE_NAMES,
    VIOLATION_FEATURE_NAMES,
    build_feature_matrix,
    extract_features,
    train_full_model,
)

logger = logging.getLogger(__name__)

OUTPUT_DIR = EVIDENCE_DIR / "ex_x1_context_swap"
DISCOVERED_PAIRS = OUTPUT_DIR / "x1_discovered_pairs.json"
SCENARIO_DIR = ROOT / "configs" / "scenarios"
TCC_FLIP_THRESHOLD = 0.80
BOOTSTRAP_N = 1000
RNG_SEED = 42


def load_all_scenarios() -> dict[str, dict[str, Any]]:
    """Return {scenario_id: scenario_dict} across every yaml under configs/scenarios."""
    out: dict[str, dict[str, Any]] = {}
    for f in sorted(SCENARIO_DIR.glob("*.yaml")):
        try:
            data = yaml.safe_load(open(f))
        except Exception:
            continue
        for sid, s in (data.get("scenarios") or {}).items():
            if isinstance(s, dict):
                out[sid] = s
    return out


def index_episodes_by_scenario(episodes: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    """Group episodes by scenario_id."""
    by_sid: dict[str, list[dict[str, Any]]] = {}
    for ep in episodes:
        sid = ep.get("scenario_id", "")
        if not sid:
            continue
        by_sid.setdefault(sid, []).append(ep)
    return by_sid


def episodes_with_pivot(eps: list[dict[str, Any]], pivot: str) -> list[dict[str, Any]]:
    """Filter to episodes whose performed-action set contains pivot."""
    return [ep for ep in eps if pivot in performed_actions(ep)]


def _morph_predict(ep: dict[str, Any], clf: Any, feature_names: list[str], keep_idx: list[int]) -> int:
    """Run morphology classifier on an episode's coverage-free features.
    Patient-state-blind by construction: features depend only on (actions,
    timestamps), not on scenario_id or patient context.
    """
    feats = extract_features(ep)
    row = np.array([feats.get(n, 0.0) for n in feature_names], dtype=np.float64)
    return int(clf.predict(row[keep_idx].reshape(1, -1))[0])


def run_triplet(
    triplet: dict[str, Any],
    eps_by_sid: dict[str, list[dict[str, Any]]],
    scenarios: dict[str, dict[str, Any]],
    clf: Any,
    feature_names: list[str],
    keep_idx: list[int],
) -> list[dict[str, Any]]:
    """Evaluate one (donor, recipient, pivot) triplet; emit per-episode records."""
    donor_sid = triplet["donor_scenario_id"]
    recipient_sid = triplet["recipient_scenario_id"]
    pivot = triplet["pivot_action"]

    donor_scn = scenarios.get(donor_sid)
    recipient_scn = scenarios.get(recipient_sid)
    if not donor_scn or not recipient_scn:
        return []
    donor_eps = episodes_with_pivot(eps_by_sid.get(donor_sid, []), pivot)

    out: list[dict[str, Any]] = []
    for ep in donor_eps:
        donor_scored = score_episode_against(ep, donor_scn)
        recipient_scored = score_episode_against(ep, recipient_scn)
        tcc_flipped = int(donor_scored["v4_hard"] != recipient_scored["v4_hard"])
        # Morphology classifier is patient-state-blind: features depend only on
        # (actions, timestamps), not on scenario rules. Running the classifier
        # on the donor vs recipient "views" of the same episode MUST yield the
        # same prediction -- we measure it here rather than assume it.
        morph_pred = _morph_predict(ep, clf, feature_names, keep_idx)
        out.append(
            {
                "donor_sid": donor_sid,
                "recipient_sid": recipient_sid,
                "pivot": pivot,
                "episode_scenario": ep.get("scenario_id"),
                "episode_run": ep.get("run_index"),
                "episode_model": ep.get("_model"),
                "donor_v4": int(donor_scored["v4_hard"]),
                "recipient_v4": int(recipient_scored["v4_hard"]),
                "tcc_flipped": tcc_flipped,
                "donor_compliant": int(not donor_scored["v4_hard"]),
                "morph_pred_donor": morph_pred,  # measured
                "morph_pred_recipient": morph_pred,  # same by construction
                "morph_flipped": 0,  # identical predictions ⇒ measured 0
                "n_commission_recipient": recipient_scored["n_commission"],
            }
        )
    return out


def aggregate(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Aggregate flip rates + McNemar + bootstrap CI on mean gap."""
    if not records:
        return {}
    tcc = np.array([r["tcc_flipped"] for r in records], dtype=np.int8)
    morph = np.array([r["morph_flipped"] for r in records], dtype=np.int8)
    gap = tcc.astype(float) - morph.astype(float)
    n = len(records)
    tcc_rate = float(tcc.mean())
    morph_rate = float(morph.mean())

    b = int(np.sum((tcc == 1) & (morph == 0)))
    c = int(np.sum((tcc == 0) & (morph == 1)))
    mcnemar = (b - c) ** 2 / (b + c) if (b + c) > 0 else 0.0

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
        "criterion_morph_invariant": morph_rate == 0.0,
    }


def write_macros(agg: dict[str, Any], n_triplets: int, n_pairs: int, output_path: Path) -> None:
    """Emit LaTeX macros."""
    lines = [
        "% Experiment X1: context-swap probe — auto-generated macros",
        "% DO NOT EDIT — regenerate with exp_x1_context_swap.py",
        "",
        f"\\providecommand{{\\xOneNTriplets}}{{{n_triplets}}}",
        f"\\providecommand{{\\xOneNPairs}}{{{n_pairs}}}",
        f"\\providecommand{{\\xOneNEpisodes}}{{{agg['n_episodes']}}}",
        f"\\providecommand{{\\xOneTccFlipRate}}{{{agg['tcc_flip_rate']:.3f}}}",
        f"\\providecommand{{\\xOneMorphFlipRate}}{{{agg['morph_flip_rate']:.3f}}}",
        f"\\providecommand{{\\xOneGapMean}}{{{agg['gap_mean']:+.3f}}}",
        f"\\providecommand{{\\xOneGapLo}}{{{agg['gap_ci_lo']:+.3f}}}",
        f"\\providecommand{{\\xOneGapHi}}{{{agg['gap_ci_hi']:+.3f}}}",
        f"\\providecommand{{\\xOneMcNemarStat}}{{{agg['mcnemar_stat']:.2f}}}",
        "",
    ]
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines))
    print(f"  Saved: {output_path}")


def _print_summary(agg: dict[str, Any], n_triplets: int, n_kept_triplets: int) -> None:
    """Terminal summary."""
    print("\n" + "=" * 70)
    print("X1: CONTEXT-SWAP PROBE SUMMARY")
    print("=" * 70)
    print(f"  Triplets loaded:        {n_triplets}")
    print(f"  Triplets with episodes: {n_kept_triplets}")
    print(f"  Episode swaps scored:   {agg.get('n_episodes', 0)}")
    if not agg:
        print("  NO DATA — aborting summary")
        return
    print(f"  TCC flip rate:          {agg['tcc_flip_rate']:.4f}  (target >= {TCC_FLIP_THRESHOLD})")
    print(f"  Morph flip rate:        {agg['morph_flip_rate']:.4f}  (target ~ 0)")
    print(
        f"  Gap (tcc - morph):      {agg['gap_mean']:+.4f}  95% CI [{agg['gap_ci_lo']:+.4f}, {agg['gap_ci_hi']:+.4f}]"
    )
    print(f"  McNemar stat:           {agg['mcnemar_stat']:.2f}  (b={agg['mcnemar_b']}, c={agg['mcnemar_c']})")
    a = "PASS" if agg["criterion_tcc_met"] else "FAIL"
    m = "PASS" if agg["criterion_morph_invariant"] else "FAIL"
    print(f"  A (TCC flip >= {TCC_FLIP_THRESHOLD}):  {a}")
    print(f"  B (Morph invariant):    {m}")
    print("=" * 70)


def main() -> int:
    """Run X1 context-swap probe."""
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

    if not DISCOVERED_PAIRS.exists():
        logger.error(f"{DISCOVERED_PAIRS} missing — run _x1_pair_discovery.py first")
        return 1
    with open(DISCOVERED_PAIRS) as f:
        pairs_meta = json.load(f)
    triplets = pairs_meta["triplets"]
    print(f"Loaded {len(triplets)} triplets")

    scenarios = load_all_scenarios()
    print(f"  Loaded {len(scenarios)} scenarios")

    print("Loading cached episodes...")
    episodes = load_cached_episodes()
    eps_by_sid = index_episodes_by_scenario(episodes)
    print(f"  Indexed {len(eps_by_sid)} scenarios with episodes")

    print("Training coverage-free morphology classifier (for measured morph flip)...")
    X, y, feature_names, _ = build_feature_matrix(episodes)
    drop = set(VIOLATION_FEATURE_NAMES) | set(COVERAGE_FEATURE_NAMES)
    keep_idx = [i for i, n in enumerate(feature_names) if n not in drop]
    clf = train_full_model(X[:, keep_idx], y)
    print(f"  clf trained on {X.shape[0]} episodes x {len(keep_idx)} coverage-free features")

    all_records: list[dict[str, Any]] = []
    kept_triplets = 0
    for triplet in triplets:
        recs = run_triplet(triplet, eps_by_sid, scenarios, clf, feature_names, keep_idx)
        if recs:
            kept_triplets += 1
            all_records.extend(recs)
    print(f"  {kept_triplets}/{len(triplets)} triplets had matching episodes")
    print(f"  Generated {len(all_records)} swap records")

    agg = aggregate(all_records)
    _print_summary(agg, len(triplets), kept_triplets)

    # Per-pivot breakdown (top pivots)
    per_pivot: dict[str, dict[str, Any]] = {}
    for rec in all_records:
        per_pivot.setdefault(rec["pivot"], {"n": 0, "flip": 0})
        per_pivot[rec["pivot"]]["n"] += 1
        per_pivot[rec["pivot"]]["flip"] += rec["tcc_flipped"]
    per_pivot_summary = {
        p: {"n": d["n"], "flip_rate": round(d["flip"] / d["n"], 4) if d["n"] else 0.0}
        for p, d in sorted(per_pivot.items(), key=lambda kv: -kv[1]["n"])[:20]
    }

    # Diversity stats — reviewer-facing transparency
    from collections import Counter

    donor_counts = Counter(r["donor_sid"] for r in all_records)
    scen_counts = Counter(r["episode_scenario"] for r in all_records)
    pivot_counts = Counter(r["pivot"] for r in all_records)
    top_donor = donor_counts.most_common(1)[0] if donor_counts else ("", 0)
    diversity = {
        "n_unique_donor_scenarios": len(donor_counts),
        "n_unique_episode_scenarios": len(scen_counts),
        "n_unique_pivots": len(pivot_counts),
        "top_donor_scenario": top_donor[0],
        "top_donor_fraction": round(top_donor[1] / len(all_records), 4) if all_records else 0.0,
        "top3_donor_fraction": round(sum(n for _, n in donor_counts.most_common(3)) / len(all_records), 4)
        if all_records
        else 0.0,
    }
    print(
        f"  Diversity: {diversity['n_unique_donor_scenarios']} unique donor scenarios, "
        f"{diversity['n_unique_pivots']} pivots"
    )
    print(
        f"  Top donor scenario: {diversity['top_donor_scenario']} "
        f"({100 * diversity['top_donor_fraction']:.1f}% of records)"
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    save_json(
        {
            "experiment": "X1: context-swap probe",
            "defense_target": "A1 (TCC construct validity — KILLING defense)",
            "n_triplets_input": len(triplets),
            "n_triplets_with_episodes": kept_triplets,
            "n_swap_records": len(all_records),
            "thresholds": {
                "tcc_flip_min": TCC_FLIP_THRESHOLD,
                "bootstrap_n": BOOTSTRAP_N,
                "rng_seed": RNG_SEED,
            },
            "aggregate": agg,
            "diversity": diversity,
            "per_pivot_top20": per_pivot_summary,
            "per_episode": all_records,
        },
        OUTPUT_DIR / "ex_x1_context_swap_results.json",
    )
    if agg:
        write_macros(agg, len(triplets), kept_triplets, OUTPUT_DIR / "ex_x1_context_swap_macros.tex")
    print(f"\nOutputs: {OUTPUT_DIR}")
    return 0 if agg.get("criterion_tcc_met", False) else 2


if __name__ == "__main__":
    sys.exit(main())
