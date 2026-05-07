"""Phase 1.I — Pose-B robustness check across 3 CwT-variant catalogues.

For each of {Original 5-type, 4-type, 3-type} CwT verdict catalogues, compute
plug-in Bayes error under each of the 4 π-class projections (term, aset,
nord, nctx). Verify whether the canonical CDE ordering
(term > aset > nord ≈ nctx) is preserved across all three CwT catalogues.

This is the "catalogue robustness" companion to Phase 1.G: instead of asking
"do the hero numbers shift between CwT variants?" (Phase 1.G), it asks
"does the π-class projection structure (Pillar 3) survive a CwT-variant
relabel?".

Inputs:
    evidence_pack/verdicts/verdict_matrix_v6_typed_phase1.json
        (must contain c2_pass, cwt_typed_pass, cwt_typed_4type_pass)
    audit/shims/_trajectory_cache (W8 episodes -> trajectories)

Output:
    evidence_pack/phase1i/phase1i_bayes_3variants.json
    evidence_pack/phase1i/phase1i_bayes_3variants_macros.tex
    evidence_pack/phase1i/phase1i_bayes_3variants_table.tex

Usage:
    PYTHONPATH=..:. /home/anonymous-org/anaconda3/bin/python3.13 \
        scripts/experiments/phase1i_bayes_3variants.py
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TYPED_VM = ROOT / "evidence_pack" / "verdicts" / "verdict_matrix_v6_typed_phase1.json"
OUTPUT_DIR = ROOT / "evidence_pack" / "phase1i"

# CDE reference (from existing Pose-B / bayes_error_macros.tex)
CDE_BAYES = {"term": 0.436, "aset": 0.024, "nord": 0.003, "nctx": 0.003}

CATALOGUES = [
    ("original", "c2_pass", "Original (5-type)"),
    ("four_type", "cwt_typed_4type_pass", "4-type"),
    ("three_type", "cwt_typed_pass", "3-type"),
]


def _actions_of(traj: dict[str, Any]) -> list[dict[str, Any]]:
    return traj.get("actions") or []


def pi_term(traj: dict[str, Any]) -> str:
    acts = _actions_of(traj)
    if not acts:
        return "__empty__"
    return str(acts[-1].get("action_id") or "__unknown__")


def pi_aset(traj: dict[str, Any]) -> frozenset[str]:
    return frozenset(a.get("action_id") for a in _actions_of(traj) if a.get("action_id"))


def pi_nord(traj: dict[str, Any]) -> tuple:
    bins: list[tuple[int, str]] = []
    for a in _actions_of(traj):
        aid = a.get("action_id")
        if not aid:
            continue
        ts = float(a.get("timestamp_minutes") or 0.0)
        bins.append((int(ts // 5), aid))
    return tuple(bins)


def pi_nctx(traj: dict[str, Any]) -> tuple[str, ...]:
    return tuple(a.get("action_id") for a in _actions_of(traj) if a.get("action_id"))


PROJECTIONS = {"term": pi_term, "aset": pi_aset, "nord": pi_nord, "nctx": pi_nctx}


def plugin_bayes_error(labels: list[bool], fibres: list) -> dict[str, Any]:
    n = len(labels)
    by_fibre: dict[object, list[bool]] = {}
    for lbl, y in zip(labels, fibres):
        by_fibre.setdefault(y, []).append(lbl)
    total = 0.0
    n_mixed = 0
    mixed_mass = 0
    for members in by_fibre.values():
        m = len(members)
        t = sum(members)
        p1 = t / m
        p0 = 1.0 - p1
        total += min(p0, p1) * (m / n)
        if 0 < t < m:
            n_mixed += 1
            mixed_mass += m
    return {
        "epsilon_star": round(total, 4),
        "n_fibres": len(by_fibre),
        "n_mixed_fibres": n_mixed,
        "mixed_fibre_mass_pct": round(100.0 * mixed_mass / max(n, 1), 2),
    }


def ordering_preserved(eps: dict[str, float]) -> bool:
    """term > aset > nord ≈ nctx (allow 0.01 tolerance for nord vs nctx)."""
    et, ea, en, ec = eps["term"], eps["aset"], eps["nord"], eps["nctx"]
    return et > ea > max(en, ec) - 0.01 and abs(en - ec) < 0.05


def main() -> int:
    DEEPSEEK_MODEL = "deepseek_r1_7b"

    print(f"[{time.strftime('%H:%M:%S')}] Loading typed VM: {TYPED_VM}")
    with open(TYPED_VM) as f:
        vm = json.load(f)
    pe = [ep for ep in vm["per_episode"] if ep.get("model_dir", ep.get("model", "")) != DEEPSEEK_MODEL]
    print(f"  W8 episodes (post-filter): {len(pe)}")

    # Load trajectories from cache
    print(f"[{time.strftime('%H:%M:%S')}] Loading trajectories...")
    from audit.shims._trajectory_cache import load_trajectory  # type: ignore[import-not-found]

    eids: list[str] = []
    trajectories: list[dict[str, Any]] = []
    labels_per_cat: dict[str, list[bool]] = {k: [] for k, _, _ in CATALOGUES}
    v4_hard: list[bool] = []
    skipped = 0
    for ep in pe:
        eid = ep.get("episode_id") or ep.get("episode_file") or ""
        if not eid:
            skipped += 1
            continue
        traj = load_trajectory(eid)
        if traj is None:
            skipped += 1
            continue
        eids.append(eid)
        trajectories.append(traj)
        for k, col, _ in CATALOGUES:
            labels_per_cat[k].append(bool(ep.get(col, False)))
        # CDE = NOT v4_hard (TCC pass = no hard violations)
        v4_hard.append(not bool(ep.get("v4_hard", True)))
    print(f"  trajectories: {len(trajectories)}, skipped: {skipped}")

    # Precompute fibres per projection
    fibres_per_proj: dict[str, list] = {}
    for name, fn in PROJECTIONS.items():
        fibres_per_proj[name] = [fn(t) for t in trajectories]

    # Compute Bayes error per (catalogue × projection)
    results: dict[str, dict[str, Any]] = {}
    for cat_key, _col, cat_disp in CATALOGUES:
        per_proj: dict[str, dict[str, Any]] = {}
        for proj_name in PROJECTIONS:
            per_proj[proj_name] = plugin_bayes_error(labels_per_cat[cat_key], fibres_per_proj[proj_name])
        eps = {p: per_proj[p]["epsilon_star"] for p in PROJECTIONS}
        results[cat_key] = {
            "display": cat_disp,
            "per_projection": per_proj,
            "epsilon_star": eps,
            "ordering_preserved": ordering_preserved(eps),
            "ordering": [k for k, _ in sorted(eps.items(), key=lambda kv: -kv[1])],
            "label_pass_rate": round(sum(labels_per_cat[cat_key]) / max(len(labels_per_cat[cat_key]), 1), 4),
        }

    # CDE reference (TCC labels)
    cde_per_proj: dict[str, dict[str, Any]] = {}
    for proj_name in PROJECTIONS:
        cde_per_proj[proj_name] = plugin_bayes_error(v4_hard, fibres_per_proj[proj_name])
    cde_eps = {p: cde_per_proj[p]["epsilon_star"] for p in PROJECTIONS}

    # Print summary
    print(f"\n=== Phase 1.I Pose-B Robustness ({len(trajectories)} W8 episodes) ===")
    print(f"  {'catalogue':<24s}  pass_rate   term     aset     nord     nctx     ordering_pres")
    print(f"  {'CDE (v4_hard)':<24s}  {(sum(v4_hard) / len(v4_hard)) * 100:>6.2f}%   "
          f"{cde_eps['term']:.4f}   {cde_eps['aset']:.4f}   {cde_eps['nord']:.4f}   {cde_eps['nctx']:.4f}   "
          f"{ordering_preserved(cde_eps)}")
    for k, _, disp in CATALOGUES:
        r = results[k]
        e = r["epsilon_star"]
        print(f"  {disp:<24s}  {r['label_pass_rate'] * 100:>6.2f}%   "
              f"{e['term']:.4f}   {e['aset']:.4f}   {e['nord']:.4f}   {e['nctx']:.4f}   "
              f"{r['ordering_preserved']}")

    # Catalogue ratio: ε_term / ε_aset (Pillar 3 indicator)
    print(f"\n=== Pillar 3 catalogue ratio (term / aset) ===")
    cde_ratio = cde_eps["term"] / max(cde_eps["aset"], 1e-9)
    print(f"  CDE: {cde_ratio:.2f}x")
    ratios = {}
    for k, _, disp in CATALOGUES:
        e = results[k]["epsilon_star"]
        r = e["term"] / max(e["aset"], 1e-9)
        ratios[k] = round(r, 2)
        print(f"  {disp}: {r:.2f}x")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_episodes": len(trajectories),
        "skipped": skipped,
        "cde_reference": {
            "epsilon_star": cde_eps,
            "ordering_preserved": ordering_preserved(cde_eps),
            "term_over_aset": round(cde_ratio, 2),
        },
        "catalogues": results,
        "pillar3_ratios_term_over_aset": ratios,
        "all_orderings_preserved": all(r["ordering_preserved"] for r in results.values()),
    }
    (OUTPUT_DIR / "phase1i_bayes_3variants.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")

    # LaTeX macros
    macro_lines = [
        "% Phase 1.I — Pose-B robustness across 3 CwT catalogues",
        f"% Generated: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
        "",
    ]
    for k, _, _ in CATALOGUES:
        kk = "Orig" if k == "original" else ("FourType" if k == "four_type" else "ThreeType")
        e = results[k]["epsilon_star"]
        prefix = f"\\providecommand{{\\phaseOneI{kk}"
        macro_lines.append(f"{prefix}EpsTerm}}{{{e['term']:.4f}}}")
        macro_lines.append(f"{prefix}EpsAset}}{{{e['aset']:.4f}}}")
        macro_lines.append(f"{prefix}EpsNord}}{{{e['nord']:.4f}}}")
        macro_lines.append(f"{prefix}EpsNctx}}{{{e['nctx']:.4f}}}")
        macro_lines.append(f"{prefix}TermOverAset}}{{{ratios[k]:.2f}}}")
        macro_lines.append(f"{prefix}OrderingPreserved}}{{{str(results[k]['ordering_preserved']).lower()}}}")
    macro_lines.append(f"\\providecommand{{\\phaseOneIAllOrderingPreserved}}{{{str(summary['all_orderings_preserved']).lower()}}}")
    (OUTPUT_DIR / "phase1i_bayes_3variants_macros.tex").write_text("\n".join(macro_lines) + "\n")

    # LaTeX table
    table_lines = [
        r"\begin{table}[htbp]",
        r"\centering\small",
        r"\caption{Pose-B robustness: plug-in Bayes error $\varepsilon^{\star}$ per $\pi$-class projection across 3 CwT-variant catalogues. CDE reference shown for comparison. Ordering preservation = (term > aset > nord $\approx$ nctx).}",
        r"\label{tab:phase1i_bayes_3variants}",
        r"\begin{tabular}{lrrrrrl}",
        r"\toprule",
        r"Catalogue & $\varepsilon^{\star}_{\text{term}}$ & $\varepsilon^{\star}_{\text{aset}}$ & $\varepsilon^{\star}_{\text{nord}}$ & $\varepsilon^{\star}_{\text{nctx}}$ & term/aset & Ordering pres. \\",
        r"\midrule",
        f"  CDE (v4\\_hard) & {cde_eps['term']:.4f} & {cde_eps['aset']:.4f} & {cde_eps['nord']:.4f} & {cde_eps['nctx']:.4f} & {cde_ratio:.2f}$\\times$ & {str(ordering_preserved(cde_eps)).lower()} \\\\",
    ]
    for k, _, disp in CATALOGUES:
        e = results[k]["epsilon_star"]
        table_lines.append(
            f"  {disp} & {e['term']:.4f} & {e['aset']:.4f} & {e['nord']:.4f} & {e['nctx']:.4f} & "
            f"{ratios[k]:.2f}$\\times$ & {str(results[k]['ordering_preserved']).lower()} \\\\"
        )
    table_lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    (OUTPUT_DIR / "phase1i_bayes_3variants_table.tex").write_text("\n".join(table_lines) + "\n")

    print(f"\n[{time.strftime('%H:%M:%S')}] All orderings preserved: {summary['all_orderings_preserved']}")
    print(f"[{time.strftime('%H:%M:%S')}] Saved to {OUTPUT_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
