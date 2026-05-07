#!/usr/bin/env python3
"""Compute missing V7.3 paper macros: M11, M12, M15-M19.

M11: Replay loss MAB-style (among v4_hard episodes, % where mab_proxy=True)
M12: Replay loss AC-style  (among v4_hard episodes, % where ac_proxy=True)
M15: Bayes-floor epsilon*_term
M16: Bayes-floor epsilon*_aset
M17: Bayes-floor epsilon*_nord
M18: Bayes-floor epsilon*_nctx
M19: Bayes-floor N (episode count used)

Reads from:
  - evidence_pack/analysis/verdict_matrix_v7_3.json  (V7.3 Full, 11,286 episodes)

Outputs:
  - evidence_pack/analysis/v73_replay_loss.json
  - evidence_pack/analysis/v73_bayes_floor.json
  - paper/auto_numbers_v73_paper_macros.tex

Usage:
    PYTHONPATH=. python scripts/experiments/compute_v73_paper_macros.py
"""

from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]

VERDICT_MATRIX_V73 = REPO_ROOT / "evidence_pack/analysis/verdict_matrix_v7_3.json"
OUTPUT_REPLAY = REPO_ROOT / "evidence_pack/analysis/v73_replay_loss.json"
OUTPUT_BAYES = REPO_ROOT / "evidence_pack/analysis/v73_bayes_floor.json"
OUTPUT_TEX = REPO_ROOT / "paper/auto_numbers_v73_paper_macros.tex"


def load_episodes(path: Path) -> list[dict]:
    """Load per-episode data from verdict matrix JSON."""
    with open(path) as f:
        data = json.load(f)
    if isinstance(data, dict):
        if "per_episode" in data:
            return data["per_episode"]
        if "episodes" in data:
            v = data["episodes"]
            return list(v.values()) if isinstance(v, dict) else v
    if isinstance(data, list):
        return data
    raise ValueError(f"Cannot parse episodes from {path}")


# ──────────────────────────────────────────────────────────────────────
# M11 + M12: Replay Loss
# ──────────────────────────────────────────────────────────────────────


def compute_replay_loss(episodes: list[dict]) -> dict:
    """Compute replay loss rates (M11, M12).

    Among episodes where v4_hard=True (TCC detections = has hard violations),
    what fraction of MAB-proxy / AC-proxy still say "pass"?
    Higher = more blindness = worse evaluator.

    V6 paper: MAB miss=84.2%, AC miss=63.2%
    """
    n_total = len(episodes)
    tcc_detections = [e for e in episodes if e.get("v4_hard")]
    n_tcc = len(tcc_detections)

    # Among TCC detections, count how many pass each proxy evaluator
    mab_pass_in_tcc = [e for e in tcc_detections if e.get("mab_proxy")]
    ac_pass_in_tcc = [e for e in tcc_detections if e.get("ac_proxy")]

    mab_miss_pct = 100.0 * len(mab_pass_in_tcc) / max(n_tcc, 1)
    ac_miss_pct = 100.0 * len(ac_pass_in_tcc) / max(n_tcc, 1)

    # Also compute C2 miss rate for context
    c2_pass_in_tcc = [e for e in tcc_detections if e.get("c2_pass")]
    c2_miss_pct = 100.0 * len(c2_pass_in_tcc) / max(n_tcc, 1)

    # DxEM miss rate (always 100% since DxEM passes everything)
    dxem_pass_in_tcc = [e for e in tcc_detections if e.get("dxem", True)]
    dxem_miss_pct = 100.0 * len(dxem_pass_in_tcc) / max(n_tcc, 1)

    # Try both label mappings (V6 had swapped labels)
    # Paper convention: "MAB-style" = action-set F1, "AC-style" = action coverage
    # Field names: mab_proxy = MAB F1 evaluator, ac_proxy = action coverage evaluator
    result = {
        "corpus": str(VERDICT_MATRIX_V73),
        "n_total": n_total,
        "n_tcc_detections": n_tcc,
        "tcc_rate_pct": round(100.0 * n_tcc / max(n_total, 1), 2),
        "mab_proxy_pass_in_tcc": len(mab_pass_in_tcc),
        "mab_miss_pct": round(mab_miss_pct, 2),
        "ac_proxy_pass_in_tcc": len(ac_pass_in_tcc),
        "ac_miss_pct": round(ac_miss_pct, 2),
        "c2_pass_in_tcc": len(c2_pass_in_tcc),
        "c2_miss_pct": round(c2_miss_pct, 2),
        "dxem_miss_pct": round(dxem_miss_pct, 2),
        "v6_paper_mab_miss": 84.2,
        "v6_paper_ac_miss": 63.2,
        "note": (
            "Miss rate = % of v4_hard episodes where evaluator still says pass. "
            "Higher = more blind. V6 had swapped field-to-label mapping "
            "(ac_proxy field matched MAB-style paper label). "
            "V7.3 mab_proxy near 0% due to MAB collapse on SGSC."
        ),
    }
    return result


# ──────────────────────────────────────────────────────────────────────
# M15-M19: Bayes Floor
# ──────────────────────────────────────────────────────────────────────


def compute_bayes_floor(
    episodes: list[dict],
    projection_fn,
) -> tuple[float, int, int, int]:
    """Compute plug-in Bayes error floor for a projection.

    Returns: (bayes_err, mixed_fibers, n_fibers, total_used)
    """
    fibers: dict[str, list[int]] = defaultdict(list)
    skipped = 0
    for ep in episodes:
        try:
            pi_val = projection_fn(ep)
            if pi_val is None or pi_val == "" or pi_val == ():
                skipped += 1
                continue
            verdict = 1 if ep.get("v4_hard") else 0
            fibers[str(pi_val)].append(verdict)
        except Exception:
            skipped += 1
            continue

    if not fibers:
        return 0.0, 0, 0, 0

    total = sum(len(v) for v in fibers.values())
    bayes_err = 0.0
    mixed = 0
    for verdicts in fibers.values():
        n = len(verdicts)
        n_violate = sum(verdicts)
        p_violate = n_violate / n
        p_pass = 1 - p_violate
        if p_violate > 0 and p_pass > 0:
            mixed += 1
        bayes_err += (n / total) * min(p_violate, p_pass)

    return bayes_err, mixed, len(fibers), total


def pi_term(ep: dict) -> str:
    """Terminal state projection: (scenario, model)."""
    return f"{ep.get('scenario_id', '')}_{ep.get('model', '')}"


def pi_aset(ep: dict) -> str:
    """Action multiset projection: sorted unique violation types."""
    vt = ep.get("viol_types", [])
    if isinstance(vt, list):
        return str(tuple(sorted(set(vt))))
    return str(vt)


def pi_nord(ep: dict) -> str:
    """Ordered violation types projection."""
    vt = ep.get("viol_types", [])
    if isinstance(vt, list):
        return str(tuple(vt))
    return str(vt)


def pi_nctx(ep: dict) -> str:
    """Violation types + count (timed context) projection."""
    vt = ep.get("viol_types", [])
    nv = ep.get("n_viols", 0)
    if isinstance(vt, list):
        return f"{tuple(vt)}_n{nv}"
    return f"{vt}_n{nv}"


def compute_all_bayes_floors(episodes: list[dict]) -> dict:
    """Compute Bayes floor for all 4 projections (M15-M19)."""
    projections = {
        "term": pi_term,
        "aset": pi_aset,
        "nord": pi_nord,
        "nctx": pi_nctx,
    }

    results = {}
    print(f"\n  {'Proj':<6}{'eps*':<12}{'Fibers':<10}{'Mixed':<8}{'N':<8}")
    print("  " + "-" * 42)

    for name, fn in projections.items():
        bayes_err, mixed, n_fibers, total = compute_bayes_floor(episodes, fn)
        print(f"  {name:<6}{bayes_err:<12.4f}{n_fibers:<10}{mixed:<8}{total:<8}")
        results[name] = {
            "epsilon_star": round(bayes_err, 6),
            "n_fibers": n_fibers,
            "mixed_fibers": mixed,
            "total_episodes": total,
        }

    # Order check
    order_ok = (
        results["term"]["epsilon_star"]
        > results["aset"]["epsilon_star"]
        > results["nord"]["epsilon_star"]
        >= results["nctx"]["epsilon_star"]
    )
    term_dominant = results["term"]["epsilon_star"] > 10 * max(
        results["aset"]["epsilon_star"],
        results["nord"]["epsilon_star"],
        results["nctx"]["epsilon_star"],
    )

    print(f"\n  Order term > aset > nord >= nctx: {order_ok}")
    print(f"  Term dominant (>10x others): {term_dominant}")

    return {
        "corpus": str(VERDICT_MATRIX_V73),
        "n_episodes": len(episodes),
        "projections": results,
        "order_preserved": order_ok,
        "term_dominant": term_dominant,
        "v6_paper_targets": {
            "term": 0.436,
            "aset": 0.024,
            "nord": 0.003,
            "nctx": 0.003,
            "N": 14826,
        },
    }


# ──────────────────────────────────────────────────────────────────────
# TeX Macro Generation
# ──────────────────────────────────────────────────────────────────────


def generate_tex_macros(replay: dict, bayes: dict) -> str:
    """Generate LaTeX macros for M11-M19."""
    ts = datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines = [
        "% V7.3 Paper Macros — M11, M12, M15-M19",
        f"% Generated: {ts}",
        "% Script: scripts/experiments/compute_v73_paper_macros.py",
        "% Source: evidence_pack/analysis/verdict_matrix_v7_3.json",
        f"% N = {replay['n_total']} episodes",
        "",
        "% --- M11: Replay loss MAB-style ---",
        f"\\providecommand{{\\vSevenThreeReplayMABMissPct}}{{{replay['mab_miss_pct']}}}",
        f"\\providecommand{{\\vSevenThreeReplayMABMissN}}{{{replay['mab_proxy_pass_in_tcc']}}}",
        "",
        "% --- M12: Replay loss AC-style ---",
        f"\\providecommand{{\\vSevenThreeReplayACMissPct}}{{{replay['ac_miss_pct']}}}",
        f"\\providecommand{{\\vSevenThreeReplayACMissN}}{{{replay['ac_proxy_pass_in_tcc']}}}",
        "",
        "% --- M12b: Replay loss C2 (bonus) ---",
        f"\\providecommand{{\\vSevenThreeReplayCTwoMissPct}}{{{replay['c2_miss_pct']}}}",
        f"\\providecommand{{\\vSevenThreeReplayCTwoMissN}}{{{replay['c2_pass_in_tcc']}}}",
        "",
        "% --- TCC detections ---",
        f"\\providecommand{{\\vSevenThreeTCCDetections}}{{{replay['n_tcc_detections']}}}",
        f"\\providecommand{{\\vSevenThreeTCCRate}}{{{replay['tcc_rate_pct']}}}",
        "",
    ]

    proj = bayes["projections"]
    lines.extend(
        [
            "% --- M15: Bayes-floor eps*_term ---",
            f"\\providecommand{{\\vSevenThreeBayesTerm}}{{{proj['term']['epsilon_star']}}}",
            "",
            "% --- M16: Bayes-floor eps*_aset ---",
            f"\\providecommand{{\\vSevenThreeBayesAset}}{{{proj['aset']['epsilon_star']}}}",
            "",
            "% --- M17: Bayes-floor eps*_nord ---",
            f"\\providecommand{{\\vSevenThreeBayesNord}}{{{proj['nord']['epsilon_star']}}}",
            "",
            "% --- M18: Bayes-floor eps*_nctx ---",
            f"\\providecommand{{\\vSevenThreeBayesNctx}}{{{proj['nctx']['epsilon_star']}}}",
            "",
            "% --- M19: Bayes-floor N ---",
            f"\\providecommand{{\\vSevenThreeBayesN}}{{{bayes['n_episodes']}}}",
            f"\\providecommand{{\\vSevenThreeBayesOrderPreserved}}{{{str(bayes['order_preserved']).lower()}}}",
            f"\\providecommand{{\\vSevenThreeBayesTermDominant}}{{{str(bayes['term_dominant']).lower()}}}",
            "",
        ]
    )

    return "\n".join(lines) + "\n"


# ──────────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────────


def main() -> int:
    print("=" * 70)
    print("V7.3 Paper Macros: M11, M12, M15-M19")
    print("=" * 70)

    if not VERDICT_MATRIX_V73.exists():
        print(f"ERROR: {VERDICT_MATRIX_V73} not found")
        return 1

    episodes = load_episodes(VERDICT_MATRIX_V73)
    print(f"Loaded {len(episodes)} episodes from V7.3 Full verdict matrix")

    # ── M11 + M12: Replay Loss ──
    print("\n" + "-" * 50)
    print("M11 + M12: Replay Loss")
    print("-" * 50)
    replay = compute_replay_loss(episodes)
    print(f"  TCC detections: {replay['n_tcc_detections']}/{replay['n_total']} ({replay['tcc_rate_pct']}%)")
    print(f"  MAB miss: {replay['mab_miss_pct']}% (V6 paper: 84.2%)")
    print(f"  AC miss:  {replay['ac_miss_pct']}% (V6 paper: 63.2%)")
    print(f"  C2 miss:  {replay['c2_miss_pct']}%")
    print(f"  DxEM miss: {replay['dxem_miss_pct']}%")

    replay["generated"] = datetime.now(UTC).isoformat()
    with open(OUTPUT_REPLAY, "w") as f:
        json.dump(replay, f, indent=2)
    print(f"\n  Saved: {OUTPUT_REPLAY}")

    # ── M15-M19: Bayes Floor ──
    print("\n" + "-" * 50)
    print("M15-M19: Bayes Floor")
    print("-" * 50)
    bayes = compute_all_bayes_floors(episodes)

    bayes["generated"] = datetime.now(UTC).isoformat()
    with open(OUTPUT_BAYES, "w") as f:
        json.dump(bayes, f, indent=2)
    print(f"\n  Saved: {OUTPUT_BAYES}")

    # ── TeX macros ──
    tex = generate_tex_macros(replay, bayes)
    with open(OUTPUT_TEX, "w") as f:
        f.write(tex)
    print(f"  Saved: {OUTPUT_TEX}")

    # ── Summary ──
    proj = bayes["projections"]
    print("\n" + "=" * 70)
    print("SUMMARY — V7.3 vs V6 Paper")
    print("=" * 70)
    print(f"  {'Macro':<8}{'V7.3':<15}{'V6 Paper':<15}{'Note'}")
    print("  " + "-" * 55)
    print(f"  M11    {replay['mab_miss_pct']:<15}{84.2:<15}MAB miss %")
    print(f"  M12    {replay['ac_miss_pct']:<15}{63.2:<15}AC miss %")
    print(f"  M15    {proj['term']['epsilon_star']:<15.4f}{0.436:<15}eps*_term")
    print(f"  M16    {proj['aset']['epsilon_star']:<15.4f}{0.024:<15}eps*_aset")
    print(f"  M17    {proj['nord']['epsilon_star']:<15.4f}{0.003:<15}eps*_nord")
    print(f"  M18    {proj['nctx']['epsilon_star']:<15.4f}{0.003:<15}eps*_nctx")
    print(f"  M19    {bayes['n_episodes']:<15}{14826:<15}N")

    return 0


if __name__ == "__main__":
    sys.exit(main())
