"""Compute typed CwT η²(eval) and η²(run) on v73_expanded corpus.

Pre-frontier sanity check: verify paper §App AP narrative is preserved
under V7.3 expanded scenarios.

Typed CwT excludes DEVIATION from compliance denominator (4-type:
OMISSION + COMMISSION + TIMING + SEQUENCE). DEVIATION is observer-
dependent on allowed_actions and should not contribute to C2.

Output:
    evidence_pack/analysis/v73_expanded_typed_cwt.json

Usage:
    PYTHONPATH=. python scripts/experiments/compute_typed_cwt.py
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import glob
import json
import os
from pathlib import Path
import time

import numpy as np

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TYPED_VIOL_TYPES = frozenset({"omission", "commission", "timing", "sequence"})
HARD_VIOL_TYPES = frozenset({"commission", "timing", "sequence"})
C2_THRESHOLD = 0.7
AC_THRESHOLD = 0.5
MAB_THRESHOLD = 0.5

SKIP_FILES = {"checkpoint.json", "model_summary.json"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class NumpyEncoder(json.JSONEncoder):
    """Handle numpy types in json.dump."""

    def default(self, obj):
        if isinstance(obj, (np.integer,)):
            return int(obj)
        if isinstance(obj, (np.floating,)):
            return float(obj)
        if isinstance(obj, (np.bool_,)):
            return bool(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def _normalize_action(aid: str) -> str:
    return aid.strip().lower().replace("-", "_").replace(" ", "_")


def _classify_vtype(raw: str) -> str:
    lower = raw.lower().strip()
    for canonical in ("omission", "commission", "timing", "sequence", "deviation"):
        if canonical in lower:
            return canonical
    return "unknown"


def _count_violations(ep: dict) -> dict[str, int]:
    """Count violations by type from violations_by_type or violation_events."""
    # Prefer pre-computed violations_by_type
    vbt = ep.get("violations_by_type")
    if vbt and isinstance(vbt, dict):
        counts: dict[str, int] = {}
        for raw_k, v in vbt.items():
            canonical = _classify_vtype(raw_k)
            counts[canonical] = counts.get(canonical, 0) + int(v)
        return counts

    # Fallback: parse violation_events
    counts = {}
    for v in ep.get("violation_events", []) or []:
        if not isinstance(v, dict):
            continue
        raw = str(v.get("violation_type", v.get("type", "")))
        vtype = _classify_vtype(raw)
        counts[vtype] = counts.get(vtype, 0) + 1
    return counts


def _action_coverage(ep: dict) -> float:
    performed = {
        _normalize_action(a["action_id"] if isinstance(a, dict) else str(a))
        for a in ep.get("actions", [])
        if (a.get("action_id") if isinstance(a, dict) else a)
    }
    expected = {_normalize_action(a) for a in ep.get("expected_actions", []) if a}
    if not expected:
        return 1.0
    return len(performed & expected) / len(expected)


def _mab_f1(ep: dict) -> float:
    performed = {
        _normalize_action(a["action_id"] if isinstance(a, dict) else str(a))
        for a in ep.get("actions", [])
        if (a.get("action_id") if isinstance(a, dict) else a)
    }
    expected = {_normalize_action(a) for a in ep.get("expected_actions", []) if a}
    if not expected:
        return 0.0
    tp = len(performed & expected)
    prec = tp / len(performed) if performed else 0.0
    rec = tp / len(expected)
    if prec + rec == 0:
        return 0.0
    return 2.0 * prec * rec / (prec + rec)


# ---------------------------------------------------------------------------
# Core computation
# ---------------------------------------------------------------------------


def load_episodes(results_dir: str) -> list[dict]:
    """Load all episode JSONs from results_dir/{model}/*.json."""
    episodes = []
    for model_dir in sorted(os.listdir(results_dir)):
        md = os.path.join(results_dir, model_dir)
        if not os.path.isdir(md) or model_dir.startswith("_"):
            continue
        for fpath in sorted(glob.glob(os.path.join(md, "*.json"))):
            base = os.path.basename(fpath)
            if base in SKIP_FILES or base.startswith(".claim"):
                continue
            try:
                d = json.load(open(fpath))
            except Exception:
                continue
            d["_model_dir"] = model_dir
            d["_file"] = fpath
            episodes.append(d)
    return episodes


def compute_verdicts(episodes: list[dict]) -> list[dict]:
    """Compute all verdict columns for each episode."""
    records = []
    for ep in episodes:
        viols = _count_violations(ep)
        n_actions = ep.get("actions_count", len(ep.get("actions", [])))
        n_mandatory = ep.get("n_expected_actions", 5)
        denom = max(n_actions, n_mandatory, 1)

        # Original compliance (all 5 types)
        orig_comp = ep.get("compliance_score", 0.0) or 0.0

        # Typed compliance (DEVIATION excluded — 4 types)
        typed_count = sum(viols.get(t, 0) for t in TYPED_VIOL_TYPES)
        typed_comp = max(0.0, 1.0 - typed_count / denom)

        # v4_hard: has any hard violations (commission/timing/sequence)
        hard_count = sum(viols.get(t, 0) for t in HARD_VIOL_TYPES)
        v4_hard = hard_count > 0

        # AC proxy
        ac_cov = _action_coverage(ep)
        ac_pass = ac_cov >= AC_THRESHOLD

        # MAB proxy
        f1 = _mab_f1(ep)
        mab_pass = f1 >= MAB_THRESHOLD

        records.append(
            {
                "scenario_id": ep.get("scenario_id", ""),
                "run_index": ep.get("run_index", 0),
                "model_dir": ep["_model_dir"],
                "orig_compliance": round(orig_comp, 4),
                "typed_compliance": round(typed_comp, 4),
                "c2_pass_orig": orig_comp >= C2_THRESHOLD,
                "c2_pass_typed": typed_comp >= C2_THRESHOLD,
                "ac_proxy": ac_pass,
                "mab_proxy": mab_pass,
                "v4_hard": v4_hard,
                "cga_pass": not v4_hard,
                "viols": viols,
            }
        )
    return records


def compute_eta_eval(records: list[dict], c2_key: str = "c2_pass_orig") -> float:
    """η²(eval): variance decomposition over (AC, MAB, C2, CGA) verdicts."""
    rows = np.array(
        [[int(r["ac_proxy"]), int(r["mab_proxy"]), int(r[c2_key]), int(r["cga_pass"])] for r in records], dtype=float
    )
    n_ep = rows.shape[0]
    gm = float(rows.mean())
    em = rows.mean(axis=0)
    ss_eval = n_ep * float(np.sum((em - gm) ** 2))
    ss_total = float(np.sum((rows - gm) ** 2))
    return ss_eval / ss_total if ss_total > 0 else 0.0


def compute_eta_run(records: list[dict]) -> float:
    """η²(run): between-group variance for CGA pass, grouped by (scenario, model)."""
    cga_arr = np.array([int(r["cga_pass"]) for r in records], dtype=float)
    groups: dict[tuple[str, str], list[float]] = defaultdict(list)
    for i, r in enumerate(records):
        groups[(r["scenario_id"], r["model_dir"])].append(float(cga_arr[i]))

    gm = float(cga_arr.mean())
    ss_total = float(np.sum((cga_arr - gm) ** 2))
    ss_within = sum(sum((v - sum(g) / len(g)) ** 2 for v in g) for g in groups.values() if g)
    return (ss_total - ss_within) / ss_total if ss_total > 0 else 0.0


def compute_kendall_w(records: list[dict]) -> float:
    """Kendall W: model ranking consistency over scenarios for CGA pass."""
    models_sorted = sorted({r["model_dir"] for r in records})
    m_n = len(models_sorted)
    if m_n <= 1:
        return 0.0

    # Build scenario -> {model: [cga_pass values]}
    sm: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for r in records:
        sm[r["scenario_id"]][r["model_dir"]].append(int(r["cga_pass"]))

    scenarios_sorted = sorted(sm.keys())
    n_s = len(scenarios_sorted)
    if n_s == 0:
        return 0.0

    # Average across runs, build rank matrix
    rmat = []
    for s in scenarios_sorted:
        scores = []
        for m in models_sorted:
            vals = sm[s].get(m, [0.0])
            scores.append(sum(vals) / len(vals))
        order = sorted(range(m_n), key=lambda i: scores[i])
        ranks = [0.0] * m_n
        for rk, i in enumerate(order):
            ranks[i] = rk + 1
        rmat.append(ranks)

    rmat_np = np.array(rmat)
    rj = rmat_np.sum(axis=0)
    rmean = rj.mean()
    s_stat = float(np.sum((rj - rmean) ** 2))
    return (12 * s_stat) / (n_s * n_s * (m_n**3 - m_n))


def compute_model_rankings(records: list[dict]) -> dict[str, dict]:
    """Per-model CGA pass rates and rankings."""
    model_stats: dict[str, dict[str, int]] = defaultdict(lambda: {"n": 0, "cga": 0})
    for r in records:
        m = r["model_dir"]
        model_stats[m]["n"] += 1
        model_stats[m]["cga"] += int(r["cga_pass"])

    rankings = {}
    for m, s in model_stats.items():
        rankings[m] = {
            "n": s["n"],
            "cga_pass": s["cga"],
            "cga_rate": round(s["cga"] / s["n"], 4) if s["n"] > 0 else 0.0,
        }

    # Sort by cga_rate descending
    sorted_models = sorted(rankings.keys(), key=lambda k: rankings[k]["cga_rate"], reverse=True)
    for rank, m in enumerate(sorted_models, 1):
        rankings[m]["rank"] = rank

    return rankings


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--results-dir", default="results/v73_expanded")
    p.add_argument("--output", default="evidence_pack/analysis/v73_expanded_typed_cwt.json")
    args = p.parse_args()

    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Loading episodes from {args.results_dir}")
    episodes = load_episodes(args.results_dir)
    n_total = len(episodes)
    n_models = len({ep["_model_dir"] for ep in episodes})
    print(f"  loaded: {n_total} episodes, {n_models} models")

    print(f"[{time.strftime('%H:%M:%S')}] Computing verdicts")
    records = compute_verdicts(episodes)

    # --- Original (C2 = overall compliance) ---
    eta_eval_orig = compute_eta_eval(records, "c2_pass_orig")
    eta_run_orig = compute_eta_run(records)
    kw_orig = compute_kendall_w(records)

    # --- Typed (C2 = DEVIATION-excluded compliance) ---
    eta_eval_typed = compute_eta_eval(records, "c2_pass_typed")
    # η²(run) and Kendall W are on CGA pass (v4_hard), unchanged by C2 definition
    # But we report them for completeness

    # Pass rates
    n_ac = sum(1 for r in records if r["ac_proxy"])
    n_mab = sum(1 for r in records if r["mab_proxy"])
    n_c2_orig = sum(1 for r in records if r["c2_pass_orig"])
    n_c2_typed = sum(1 for r in records if r["c2_pass_typed"])
    n_cga = sum(1 for r in records if r["cga_pass"])
    n_v4_hard = sum(1 for r in records if r["v4_hard"])

    # Model rankings
    rankings = compute_model_rankings(records)

    # C2 flip analysis: episodes where orig and typed disagree
    c2_flips = sum(1 for r in records if r["c2_pass_orig"] != r["c2_pass_typed"])
    c2_gain = sum(1 for r in records if not r["c2_pass_orig"] and r["c2_pass_typed"])
    c2_loss = sum(1 for r in records if r["c2_pass_orig"] and not r["c2_pass_typed"])

    result = {
        "metadata": {
            "generated": time.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "script": "scripts/experiments/compute_typed_cwt.py",
            "results_dir": args.results_dir,
            "n_episodes": n_total,
            "n_models": n_models,
            "typed_definition": "CwT-typed excludes DEVIATION; counts OMISSION+COMMISSION+TIMING+SEQUENCE",
            "c2_threshold": C2_THRESHOLD,
        },
        "pass_rates": {
            "ac_proxy": round(n_ac / n_total, 4),
            "mab_proxy": round(n_mab / n_total, 4),
            "c2_orig": round(n_c2_orig / n_total, 4),
            "c2_typed": round(n_c2_typed / n_total, 4),
            "cga_pass": round(n_cga / n_total, 4),
            "v4_hard": round(n_v4_hard / n_total, 4),
        },
        "eta_squared": {
            "original": {
                "eta_eval": round(eta_eval_orig, 4),
                "eta_run": round(eta_run_orig, 4),
                "kendall_w": round(kw_orig, 4),
                "note": "C2 = overall compliance >= 0.7",
            },
            "typed": {
                "eta_eval": round(eta_eval_typed, 4),
                "eta_run": round(eta_run_orig, 4),  # same (CGA unchanged)
                "kendall_w": round(kw_orig, 4),  # same (CGA unchanged)
                "note": "C2 = typed compliance (DEVIATION excluded) >= 0.7",
            },
            "delta_eta_eval": round(eta_eval_typed - eta_eval_orig, 4),
        },
        "c2_flip_analysis": {
            "total_flips": c2_flips,
            "flip_rate": round(c2_flips / n_total, 4),
            "gained_pass": c2_gain,
            "lost_pass": c2_loss,
            "net_gain": c2_gain - c2_loss,
        },
        "model_rankings": rankings,
        "comparison_to_baseline": {
            "baseline_eta_eval": 0.1561,
            "baseline_eta_run": 0.9212,
            "baseline_source": "paper/auto_numbers_v73_expanded.tex",
            "narrative_preserved": None,  # filled below
        },
    }

    # Narrative check: is η²(eval) under typed still showing evaluator disagreement?
    # Paper narrative: "moderate evaluator disagreement" = η²(eval) > 0.05
    narrative_ok = eta_eval_typed > 0.05
    result["comparison_to_baseline"]["narrative_preserved"] = narrative_ok
    result["comparison_to_baseline"]["typed_vs_baseline_delta"] = round(eta_eval_typed - 0.1561, 4)

    # Print summary
    print(f"\n{'=' * 60}")
    print("  V7.3 Expanded Typed CwT Analysis")
    print(f"  Episodes: {n_total} | Models: {n_models}")
    print(f"{'=' * 60}")
    print("\n  Pass rates:")
    print(f"    AC proxy:   {n_ac}/{n_total} = {100 * n_ac / n_total:.1f}%")
    print(f"    MAB proxy:  {n_mab}/{n_total} = {100 * n_mab / n_total:.1f}%")
    print(f"    C2 (orig):  {n_c2_orig}/{n_total} = {100 * n_c2_orig / n_total:.1f}%")
    print(f"    C2 (typed): {n_c2_typed}/{n_total} = {100 * n_c2_typed / n_total:.1f}%")
    print(f"    CGA pass:   {n_cga}/{n_total} = {100 * n_cga / n_total:.1f}%")
    print(f"    v4_hard:    {n_v4_hard}/{n_total} = {100 * n_v4_hard / n_total:.1f}%")

    print("\n  eta-squared (evaluator disagreement):")
    print(f"    Original:  eta_eval={eta_eval_orig:.4f}  eta_run={eta_run_orig:.4f}  W={kw_orig:.4f}")
    print(f"    Typed:     eta_eval={eta_eval_typed:.4f}  (delta={eta_eval_typed - eta_eval_orig:+.4f})")
    print("    Baseline:  eta_eval=0.1561  eta_run=0.9212")

    print("\n  C2 flip analysis:")
    print(f"    Flips: {c2_flips} ({100 * c2_flips / n_total:.1f}%)")
    print(f"    Gained pass: {c2_gain} | Lost pass: {c2_loss} | Net: {c2_gain - c2_loss:+d}")

    print("\n  Model rankings (CGA pass rate):")
    for m in sorted(rankings.keys(), key=lambda k: rankings[k]["rank"]):
        r = rankings[m]
        print(f"    #{r['rank']} {m}: {100 * r['cga_rate']:.1f}% ({r['cga_pass']}/{r['n']})")

    print(f"\n  Narrative preserved: {narrative_ok}")
    print(f"    (eta_eval_typed={eta_eval_typed:.4f} > 0.05 threshold)")

    # Save
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(result, f, indent=2, cls=NumpyEncoder)
    print(f"\n[{time.strftime('%H:%M:%S')}] Saved -> {args.output}  ({time.time() - t0:.1f}s)")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
