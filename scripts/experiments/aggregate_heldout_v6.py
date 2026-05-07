r"""Aggregate heldout episodes for Phase B v6 macros.

Reads results/heldout_v1/ (legacy heldout-5 scope: aabb_t, aba, acog, apa, pals).
Compares heldout vs in-domain FA rates using same evaluator stack as Phase B.

Output:
  evidence_pack/analysis/v6_full_heldout.json
  evidence_pack/tables/v6_full_heldout.tex   (\heldoutFARate, \heldoutFlipRate, ...)
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import glob
import json
import os
from pathlib import Path

import numpy as np
from scipy import stats

ROOT = Path(__file__).resolve().parents[2]
HARD_VIOL_TYPES = frozenset({"commission", "timing", "sequence"})

AC_THRESHOLD = 0.5
MAB_THRESHOLD = 0.5
C2_THRESHOLD = 0.7


def normalize(aid: str) -> str:
    return aid.strip().lower().replace("-", "_").replace(" ", "_")


def score_episode(ep: dict, model_dir: str) -> dict:
    """Compute evaluator verdicts for one heldout episode (mirrors verdict_matrix_v5)."""
    sid = ep.get("scenario_id", "")
    ri = ep.get("run_index", 0)
    performed = {
        normalize(a.get("action_id", "") if isinstance(a, dict) else str(a)) for a in ep.get("actions", []) or []
    }
    performed.discard("")
    expected = {
        normalize(a.get("action_id", "") if isinstance(a, dict) else str(a))
        for a in ep.get("expected_actions", []) or []
    }
    expected.discard("")

    coverage = len(performed & expected) / len(expected) if expected else 1.0
    if expected and performed:
        tp = len(performed & expected)
        prec = tp / len(performed)
        rec = tp / len(expected)
        f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0.0
    else:
        f1 = 0.0
    c2_score = float(ep.get("compliance_score") or 0.0)

    n_hard = 0
    for v in ep.get("violation_events", []) or []:
        vt = str(v.get("violation_type", v.get("type", ""))).lower().strip()
        if any(t in vt for t in HARD_VIOL_TYPES):
            n_hard += 1
    has_hard = n_hard > 0

    return {
        "scenario_id": sid,
        "run_index": ri,
        "model_dir": model_dir,
        "ac_proxy": coverage >= AC_THRESHOLD,
        "mab_proxy": f1 >= MAB_THRESHOLD,
        "c2_pass": c2_score >= C2_THRESHOLD,
        "c2_score": round(c2_score, 4),
        "dxem": True,
        "v4_hard": has_hard,
        "n_hard": n_hard,
        "action_coverage": round(coverage, 4),
        "mab_f1": round(f1, 4),
    }


def load_heldout(heldout_dir: str) -> list[dict]:
    out = []
    for m in sorted(os.listdir(heldout_dir)):
        md = os.path.join(heldout_dir, m)
        if not os.path.isdir(md) or m.startswith("_"):
            continue
        for f in glob.glob(os.path.join(md, "*.json")):
            base = os.path.basename(f)
            if base.startswith(("checkpoint", ".claim", "model_summary", "log_")):
                continue
            try:
                ep = json.load(open(f))
            except Exception:
                continue
            if not isinstance(ep, dict) or not ep.get("scenario_id"):
                continue
            out.append(score_episode(ep, m))
    return out


def fa_stats(records: list[dict], label: str) -> dict:
    n = len(records)
    if n == 0:
        return {"n": 0, "label": label}
    fa_consensus = sum(1 for r in records if r["dxem"] and r["ac_proxy"] and r["c2_pass"] and r["v4_hard"])
    fa_strict_3 = sum(1 for r in records if r["ac_proxy"] and r["mab_proxy"] and r["c2_pass"] and r["v4_hard"])
    n_v4 = sum(1 for r in records if r["v4_hard"])
    mean_comp = float(np.mean([r["c2_score"] for r in records]))
    return {
        "label": label,
        "n": n,
        "fa_consensus_count": fa_consensus,
        "fa_consensus_pct": round(100 * fa_consensus / n, 2),
        "fa_strict_3way_count": fa_strict_3,
        "fa_strict_3way_pct": round(100 * fa_strict_3 / n, 2),
        "tcc_fail_count": n_v4,
        "tcc_fail_pct": round(100 * n_v4 / n, 2),
        "mean_compliance": round(mean_comp, 3),
    }


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--heldout-dir", default="results/heldout_v1")
    p.add_argument("--vmatrix-full", default="evidence_pack/analysis/verdict_matrix_v6_full.json")
    p.add_argument("--out-json", default="evidence_pack/analysis/v6_full_heldout.json")
    p.add_argument("--out-tex", default="evidence_pack/tables/v6_full_heldout.tex")
    args = p.parse_args()

    print(f"Loading heldout episodes from {args.heldout_dir}...")
    heldout = load_heldout(args.heldout_dir)
    print(f"  Loaded: {len(heldout)} episodes")

    # Per-model breakdown (qwen397b might be incomplete)
    by_m = defaultdict(list)
    for r in heldout:
        by_m[r["model_dir"]].append(r)
    print("\nPer-model heldout episode counts:")
    for m in sorted(by_m):
        print(f"  {m}: {len(by_m[m])}")

    # Detect incomplete models (< 100 episodes = likely partial)
    complete_models = {m for m, eps in by_m.items() if len(eps) >= 100}
    incomplete_models = {m for m, eps in by_m.items() if len(eps) < 100}
    if incomplete_models:
        print(f"\nIncomplete models (< 100 ep): {sorted(incomplete_models)}")
        print(f"Complete models (>= 100 ep): {sorted(complete_models)}")

    # Heldout FA stats — complete models only
    heldout_complete = [r for r in heldout if r["model_dir"] in complete_models]
    heldout_stats = fa_stats(heldout_complete, "heldout (complete-models)")
    print("\n=== Heldout (complete-models only) ===")
    for k, v in heldout_stats.items():
        print(f"  {k}: {v}")

    # In-domain (Phase B) FA stats for the same models
    print("\nLoading Phase B verdict matrix for in-domain comparison...")
    pe = json.load(open(args.vmatrix_full))["per_episode"]
    indomain = [{**ep, "n_hard": ep["n_viols"]} for ep in pe if ep["model_dir"] in complete_models]
    indomain_stats = fa_stats(indomain, f"in-domain (Phase B, {sorted(complete_models)})")
    print("\n=== In-domain (Phase B) ===")
    for k, v in indomain_stats.items():
        print(f"  {k}: {v}")

    # Fisher exact test on heldout vs indomain consensus FA proportion
    a = heldout_stats["fa_consensus_count"]
    b = heldout_stats["n"] - a
    c = indomain_stats["fa_consensus_count"]
    d = indomain_stats["n"] - c
    odds_ratio, p_fisher = stats.fisher_exact([[a, b], [c, d]], alternative="greater")
    print(f"\nFisher exact (heldout > indomain): OR={odds_ratio:.3f}, p={p_fisher:.3e}")

    # Verdict-flip rate per heldout episode (does any evaluator pair disagree?)
    flips = 0
    for r in heldout_complete:
        verdicts = [r["dxem"], r["ac_proxy"], r["mab_proxy"], r["c2_pass"], not r["v4_hard"]]
        if len(set(verdicts)) > 1:
            flips += 1
    flip_rate = round(100 * flips / len(heldout_complete), 2) if heldout_complete else 0

    print(f"Verdict-flip rate (heldout): {flips}/{len(heldout_complete)} = {flip_rate}%")

    # Save
    out = {
        "heldout": heldout_stats,
        "indomain": indomain_stats,
        "complete_models": sorted(complete_models),
        "incomplete_models": sorted(incomplete_models),
        "incomplete_model_counts": {m: len(by_m[m]) for m in sorted(incomplete_models)},
        "fisher_odds_ratio": round(float(odds_ratio), 3),
        "fisher_p_value": float(p_fisher),
        "verdict_flip_rate_pct": flip_rate,
        "verdict_flip_count": flips,
    }
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_json).write_text(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {args.out_json}")

    # LaTeX macros — keep \heldout* names; comments document v6 status
    L = [
        r"% v6 Heldout macros — auto-generated by aggregate_heldout_v6.py",
        rf"% Heldout: {heldout_stats['n']} ep across {len(complete_models)} models",
        rf"% In-domain (Phase B): {indomain_stats['n']} ep",
        "",
        rf"\providecommand{{\heldoutFARate}}{{{heldout_stats['fa_consensus_pct']}}}",
        rf"\providecommand{{\heldoutFlipRate}}{{{flip_rate}}}",
        rf"\providecommand{{\heldoutCompliance}}{{{heldout_stats['mean_compliance']}}}",
        rf"\providecommand{{\indomainFARate}}{{{indomain_stats['fa_consensus_pct']}}}",
        rf"\providecommand{{\indomainCompliance}}{{{indomain_stats['mean_compliance']}}}",
        rf"\providecommand{{\heldoutFisherP}}{{{p_fisher:.3e}}}",
        rf"\providecommand{{\heldoutOddsRatio}}{{{odds_ratio:.2f}}}",
        rf"\providecommand{{\heldoutN}}{{{heldout_stats['n']}}}",
        rf"\providecommand{{\heldoutNumModels}}{{{len(complete_models)}}}",
        rf"\providecommand{{\heldoutStrictFA}}{{{heldout_stats['fa_strict_3way_pct']}}}",
        rf"\providecommand{{\heldoutTCCFailRate}}{{{heldout_stats['tcc_fail_pct']}}}",
    ]
    Path(args.out_tex).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out_tex).write_text("\n".join(L) + "\n")
    print(f"Saved → {args.out_tex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
