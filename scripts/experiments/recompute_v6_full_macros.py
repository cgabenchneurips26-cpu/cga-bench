"""Recompute all hero macros on the Phase B verdict matrix (76,464 episodes).

For each macro family, compute (Phase A original, Phase B original, Phase B typed)
and emit side-by-side numbers. Outputs:
  evidence_pack/analysis/v6_full_macros.json   — all numbers
  evidence_pack/analysis/v6_full_per_cpg.json  — per-CPG breakdown
  evidence_pack/tables/v6_full_macros.tex      — LaTeX macros (with v6Full prefix)

FA semantics fix applied: v4_hard==True ⟺ TCC FAIL ⟺ FA = pass + ep['v4_hard'].
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path

import numpy as np


def cell_lookup(pe: list, c2_field: str) -> tuple[np.ndarray, list[dict]]:
    """Build records for v1-style 4-evaluator η² (cga_pass = NOT v4_hard)."""
    rows = []
    for ep in pe:
        rows.append(
            {
                "scenario_id": ep["scenario_id"],
                "model": ep.get("model_dir") or ep.get("model"),
                "run_index": ep["run_index"],
                "ac_proxy": int(ep["ac_proxy"]),
                "mab_proxy": int(ep["mab_proxy"]),
                "c2_pass": int(ep[c2_field]),
                "cga_pass": int(not ep["v4_hard"]),
                "v4_hard": int(ep["v4_hard"]),
                "dxem": int(ep["dxem"]),
            }
        )
    return rows


def hero_consensus_fa(pe: list, c2_field: str) -> dict:
    """Strict FA = pass on listed evaluators + TCC fail (= ep[v4_hard] True)."""
    n = len(pe)
    asc_paf_cwt = sum(1 for ep in pe if ep["ac_proxy"] and ep["mab_proxy"] and ep[c2_field] and ep["v4_hard"])
    tom_asc_paf_cwt = sum(
        1 for ep in pe if ep["dxem"] and ep["ac_proxy"] and ep["mab_proxy"] and ep[c2_field] and ep["v4_hard"]
    )
    tom_asc_cwt = sum(1 for ep in pe if ep["dxem"] and ep["ac_proxy"] and ep[c2_field] and ep["v4_hard"])
    return {
        "n": n,
        "fa_strict_3way_asc_paf_cwt": asc_paf_cwt,
        "fa_strict_3way_pct": round(100 * asc_paf_cwt / n, 2),
        "fa_strict_4way_tom_asc_paf_cwt": tom_asc_paf_cwt,
        "fa_strict_4way_pct": round(100 * tom_asc_paf_cwt / n, 2),
        "fa_consensus_tom_asc_cwt": tom_asc_cwt,
        "fa_consensus_tom_asc_cwt_pct": round(100 * tom_asc_cwt / n, 2),
    }


def cres5_eta2(rows: list[dict]) -> dict:
    """CRES-5 v1-style: 4-evaluator binary verdict matrix → η²(eval) and η²(run)."""
    mat = np.array(
        [[r["ac_proxy"], r["mab_proxy"], r["c2_pass"], r["cga_pass"]] for r in rows],
        dtype=float,
    )
    n, k = mat.shape
    gm = float(mat.mean())
    em = mat.mean(axis=0)
    ss_eval = n * float(np.sum((em - gm) ** 2))
    ss_total = float(np.sum((mat - gm) ** 2))
    eta_eval = ss_eval / ss_total if ss_total > 0 else 0.0

    cga = mat[:, 3]
    gm_run = float(cga.mean())
    ss_total_run = float(np.sum((cga - gm_run) ** 2))
    groups = defaultdict(list)
    for i, r in enumerate(rows):
        groups[(r["scenario_id"], r["model"])].append(float(cga[i]))
    ss_run = 0.0
    for vals in groups.values():
        if len(vals) >= 2:
            mu = np.mean(vals)
            ss_run += float(np.sum((np.array(vals) - mu) ** 2))
    eta_run = ss_run / ss_total_run if ss_total_run > 0 else 0.0
    return {
        "eta2_eval": round(eta_eval, 4),
        "eta2_run": round(eta_run, 4),
        "eta2_eval_run_ratio": round(eta_eval / max(eta_run, 1e-9), 2),
        "pass_rates": {
            "ac_proxy": round(em[0], 4),
            "mab_proxy": round(em[1], 4),
            "c2_pass": round(em[2], 4),
            "cga_pass": round(em[3], 4),
        },
    }


def v6_eta2_5eval(pe: list, c2_field: str) -> dict:
    """v6-style binary verdict η² across 5 evaluators (TOM/ASC/PAF/CwT/TCC).

    TCC enters as 'TCC pass' = NOT v4_hard.
    """
    evs = ["dxem", "ac_proxy", "mab_proxy", c2_field, "v4_hard"]
    rows = []
    for ep in pe:
        for ev in evs:
            v = ep[ev] if ev != "v4_hard" else (not ep[ev])
            rows.append(
                {
                    "scenario_id": ep["scenario_id"],
                    "model": ep.get("model_dir") or ep.get("model"),
                    "run_index": ep["run_index"],
                    "evaluator": ev,
                    "verdict": int(v),
                }
            )
    arr = np.array([r["verdict"] for r in rows])
    grand_mean = arr.mean()
    SS_total = float(((arr - grand_mean) ** 2).sum())

    ev_means = defaultdict(list)
    for r in rows:
        ev_means[r["evaluator"]].append(r["verdict"])
    SS_eval = sum(len(v) * (np.mean(v) - grand_mean) ** 2 for v in ev_means.values())

    run_means = defaultdict(list)
    for r in rows:
        run_means[r["run_index"]].append(r["verdict"])
    SS_run = sum(len(v) * (np.mean(v) - grand_mean) ** 2 for v in run_means.values())

    return {
        "eta2_eval": round(SS_eval / SS_total, 4) if SS_total > 0 else 0,
        "eta2_run": round(SS_run / SS_total, 4) if SS_total > 0 else 0,
        "ratio": round((SS_eval / SS_total) / max(SS_run / SS_total, 1e-9), 2) if SS_total > 0 else 0,
    }


def pair_reversal(pe: list, c2_field: str) -> dict:
    """Cell-level pair reversal across (model_a, model_b) within scenarios."""
    cells: dict = defaultdict(lambda: defaultdict(list))
    evs = ["ac_proxy", c2_field, "mab_proxy", "v4_hard"]
    for ep in pe:
        key = (ep.get("model_dir") or ep.get("model"), ep["scenario_id"])
        for ev in evs:
            v = ep[ev] if ev != "v4_hard" else (not ep[ev])
            cells[key][ev].append(v)
    cell_means: dict = defaultdict(dict)
    for k, vs in cells.items():
        for ev in evs:
            cell_means[k][ev] = sum(vs[ev]) / max(len(vs[ev]), 1)
    models = sorted({k[0] for k in cell_means})
    scenarios = sorted({k[1] for k in cell_means})
    total = 0
    rev = 0
    for sc in scenarios:
        for ma, mb in combinations(models, 2):
            ka, kb = (ma, sc), (mb, sc)
            if ka not in cell_means or kb not in cell_means:
                continue
            for ev_a, ev_b in combinations(evs, 2):
                a_diff = cell_means[ka][ev_a] - cell_means[kb][ev_a]
                b_diff = cell_means[ka][ev_b] - cell_means[kb][ev_b]
                if a_diff == 0 or b_diff == 0:
                    continue
                total += 1
                if (a_diff > 0) != (b_diff > 0):
                    rev += 1
    return {
        "n_comparisons": total,
        "n_reversals": rev,
        "reversal_rate_pct": round(100 * rev / max(total, 1), 2),
    }


def bsr_conditional(pe: list, c2_field: str) -> dict:
    """BSR conditional: P(TCC fail | evaluator pass) per evaluator."""
    out = {}
    for label, field in [("ASC", "ac_proxy"), ("PAF", "mab_proxy"), ("CwT", c2_field), ("TOM", "dxem")]:
        passing = [ep for ep in pe if ep[field]]
        n_pass = len(passing)
        n_tcc_fail = sum(1 for ep in passing if ep["v4_hard"])
        out[label] = {
            "n_pass": n_pass,
            "tcc_fail_in_pass": n_tcc_fail,
            "bsr_pct": round(100 * n_tcc_fail / max(n_pass, 1), 2),
        }
    return out


def per_cpg_breakdown(pe: list, c2_field: str) -> dict:
    """Group by CPG (extract from scenario_id) → per-evaluator pass/FA stats."""
    by_cpg = defaultdict(list)
    for ep in pe:
        sid = ep["scenario_id"]
        # CPG identifier: first 2-3 underscore tokens (heuristic)
        parts = sid.split("_")
        # Guideline cards prefix tends to be 2 tokens, sometimes longer
        cpg = "_".join(parts[:3]) if len(parts) >= 3 else "_".join(parts[:2])
        by_cpg[cpg].append(ep)

    out = {}
    for cpg, eps in by_cpg.items():
        n = len(eps)
        if n < 30:
            continue  # skip tiny groups
        n_v4 = sum(1 for ep in eps if ep["v4_hard"])
        n_ac = sum(1 for ep in eps if ep["ac_proxy"])
        n_paf = sum(1 for ep in eps if ep["mab_proxy"])
        n_cwt = sum(1 for ep in eps if ep[c2_field])
        n_fa3 = sum(1 for ep in eps if ep["ac_proxy"] and ep["mab_proxy"] and ep[c2_field] and ep["v4_hard"])
        out[cpg] = {
            "n": n,
            "tcc_fail_pct": round(100 * n_v4 / n, 2),
            "asc_pass_pct": round(100 * n_ac / n, 2),
            "paf_pass_pct": round(100 * n_paf / n, 2),
            "cwt_pass_pct": round(100 * n_cwt / n, 2),
            "fa_strict_3way_pct": round(100 * n_fa3 / n, 2),
            "fa_strict_3way_count": n_fa3,
        }
    return dict(sorted(out.items(), key=lambda kv: -kv[1]["fa_strict_3way_pct"]))


def per_model_fa(pe: list, c2_field: str) -> dict:
    """Per-model strict 3-way FA rate."""
    by_m = defaultdict(list)
    for ep in pe:
        by_m[ep.get("model_dir") or ep.get("model")].append(ep)
    out = {}
    for m, eps in by_m.items():
        n = len(eps)
        n_fa3 = sum(1 for ep in eps if ep["ac_proxy"] and ep["mab_proxy"] and ep[c2_field] and ep["v4_hard"])
        out[m] = {"n": n, "fa3_count": n_fa3, "fa3_pct": round(100 * n_fa3 / n, 2)}
    return out


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--vmatrix", default="evidence_pack/analysis/verdict_matrix_v6_full.json")
    p.add_argument("--vmatrix-typed", default="evidence_pack/analysis/verdict_matrix_v6_full_typed.json")
    p.add_argument(
        "--phase-a-vmatrix",
        default="evidence_pack/analysis/verdict_matrix_v6.json",
        help="Phase A reference matrix for side-by-side comparison",
    )
    p.add_argument("--phase-a-typed", default="evidence_pack/analysis/verdict_matrix_v6_typed.json")
    p.add_argument("--out-json", default="evidence_pack/analysis/v6_full_macros.json")
    p.add_argument("--out-per-cpg", default="evidence_pack/analysis/v6_full_per_cpg.json")
    p.add_argument("--out-tex", default="evidence_pack/tables/v6_full_macros.tex")
    args = p.parse_args()

    print("Loading verdict matrices...")
    vm_full = json.load(open(args.vmatrix))
    vm_full_typed = json.load(open(args.vmatrix_typed))
    pe_full = vm_full["per_episode"]
    pe_full_typed = vm_full_typed["per_episode"]
    print(f"  Phase B (full): {len(pe_full)} episodes")
    print(f"  Phase B typed:  {len(pe_full_typed)} episodes")

    pa_orig = pa_typed = None
    try:
        pa_orig = json.load(open(args.phase_a_vmatrix))["per_episode"]
        # filter to 8-model pool to match Phase B
        pa_orig = [ep for ep in pa_orig if ep.get("model_dir") != "llama4scout"]
        pa_typed = json.load(open(args.phase_a_typed))["per_episode"]
        pa_typed = [ep for ep in pa_typed if ep.get("model_dir") != "llama4scout"]
        print(f"  Phase A original (8mdl): {len(pa_orig)} episodes")
        print(f"  Phase A typed:           {len(pa_typed)} episodes")
    except Exception as e:
        print(f"  WARN: Phase A reference unavailable: {e}")

    out: dict = {}

    # ----- Strict FA family -----
    print("\n=== Strict FA ===")
    fa_pa_orig = hero_consensus_fa(pa_orig, "c2_pass") if pa_orig else None
    fa_pa_typed = hero_consensus_fa(pa_typed, "c2_pass_typed") if pa_typed else None
    fa_pb_orig = hero_consensus_fa(pe_full, "c2_pass")
    fa_pb_typed = hero_consensus_fa(pe_full_typed, "c2_pass_typed")
    out["fa"] = {
        "phase_a_original": fa_pa_orig,
        "phase_a_typed": fa_pa_typed,
        "phase_b_original": fa_pb_orig,
        "phase_b_typed": fa_pb_typed,
    }
    print(
        f"  Phase A original: ASC∩PAF∩CwT = {fa_pa_orig['fa_strict_3way_pct']}% / TOM∩ASC∩CwT = {fa_pa_orig['fa_consensus_tom_asc_cwt_pct']}%"
    )
    print(
        f"  Phase A typed:    ASC∩PAF∩CwT = {fa_pa_typed['fa_strict_3way_pct']}% / TOM∩ASC∩CwT = {fa_pa_typed['fa_consensus_tom_asc_cwt_pct']}%"
    )
    print(
        f"  Phase B original: ASC∩PAF∩CwT = {fa_pb_orig['fa_strict_3way_pct']}% / TOM∩ASC∩CwT = {fa_pb_orig['fa_consensus_tom_asc_cwt_pct']}%"
    )
    print(
        f"  Phase B typed:    ASC∩PAF∩CwT = {fa_pb_typed['fa_strict_3way_pct']}% / TOM∩ASC∩CwT = {fa_pb_typed['fa_consensus_tom_asc_cwt_pct']}%"
    )

    # ----- CRES-5 4-evaluator η² -----
    print("\n=== CRES-5 4-evaluator η² ===")
    rows_pa_orig = cell_lookup(pa_orig, "c2_pass") if pa_orig else None
    rows_pa_typed = cell_lookup(pa_typed, "c2_pass_typed") if pa_typed else None
    rows_pb_orig = cell_lookup(pe_full, "c2_pass")
    rows_pb_typed = cell_lookup(pe_full_typed, "c2_pass_typed")

    e_pa_orig = cres5_eta2(rows_pa_orig) if rows_pa_orig else None
    e_pa_typed = cres5_eta2(rows_pa_typed) if rows_pa_typed else None
    e_pb_orig = cres5_eta2(rows_pb_orig)
    e_pb_typed = cres5_eta2(rows_pb_typed)
    out["cres5_eta2"] = {
        "phase_a_original": e_pa_orig,
        "phase_a_typed": e_pa_typed,
        "phase_b_original": e_pb_orig,
        "phase_b_typed": e_pb_typed,
    }
    for lbl, e in [
        ("Phase A original", e_pa_orig),
        ("Phase A typed", e_pa_typed),
        ("Phase B original", e_pb_orig),
        ("Phase B typed", e_pb_typed),
    ]:
        if e:
            print(
                f"  {lbl}: η²(eval)={e['eta2_eval']:.4f} η²(run)={e['eta2_run']:.4f} ratio={e['eta2_eval_run_ratio']:.2f}×"
            )

    # ----- v6 5-evaluator η² -----
    print("\n=== v6-style 5-evaluator η² ===")
    e6_pa_orig = v6_eta2_5eval(pa_orig, "c2_pass") if pa_orig else None
    e6_pa_typed = v6_eta2_5eval(pa_typed, "c2_pass_typed") if pa_typed else None
    e6_pb_orig = v6_eta2_5eval(pe_full, "c2_pass")
    e6_pb_typed = v6_eta2_5eval(pe_full_typed, "c2_pass_typed")
    out["v6_eta2_5eval"] = {
        "phase_a_original": e6_pa_orig,
        "phase_a_typed": e6_pa_typed,
        "phase_b_original": e6_pb_orig,
        "phase_b_typed": e6_pb_typed,
    }
    for lbl, e in [
        ("Phase A original", e6_pa_orig),
        ("Phase A typed", e6_pa_typed),
        ("Phase B original", e6_pb_orig),
        ("Phase B typed", e6_pb_typed),
    ]:
        if e:
            print(f"  {lbl}: η²(eval)={e['eta2_eval']:.4f} η²(run)={e['eta2_run']:.4f}")

    # ----- BSR conditional -----
    print("\n=== BSR conditional (P(TCC fail | evaluator pass)) ===")
    out["bsr_conditional"] = {
        "phase_a_original": bsr_conditional(pa_orig, "c2_pass") if pa_orig else None,
        "phase_a_typed": bsr_conditional(pa_typed, "c2_pass_typed") if pa_typed else None,
        "phase_b_original": bsr_conditional(pe_full, "c2_pass"),
        "phase_b_typed": bsr_conditional(pe_full_typed, "c2_pass_typed"),
    }
    for lbl, b in out["bsr_conditional"].items():
        if b:
            print(
                f"  {lbl}: ASC={b['ASC']['bsr_pct']}% PAF={b['PAF']['bsr_pct']}% CwT={b['CwT']['bsr_pct']}% TOM={b['TOM']['bsr_pct']}%"
            )

    # ----- Pair reversal -----
    print("\n=== Pair reversal ===")
    out["pair_reversal"] = {
        "phase_b_original": pair_reversal(pe_full, "c2_pass"),
        "phase_b_typed": pair_reversal(pe_full_typed, "c2_pass_typed"),
    }
    for lbl, r in out["pair_reversal"].items():
        print(f"  {lbl}: {r['reversal_rate_pct']}% ({r['n_reversals']}/{r['n_comparisons']})")

    # ----- Per-model FA -----
    print("\n=== Per-model strict 3-way FA ===")
    out["per_model_fa"] = {
        "phase_b_original": per_model_fa(pe_full, "c2_pass"),
        "phase_b_typed": per_model_fa(pe_full_typed, "c2_pass_typed"),
    }
    print("  Phase B original:")
    for m, d in sorted(out["per_model_fa"]["phase_b_original"].items()):
        print(f"    {m}: {d['fa3_pct']}% ({d['fa3_count']}/{d['n']})")

    # ----- Per-CPG breakdown -----
    print("\n=== Per-CPG breakdown (Phase B original; top 10 by FA rate) ===")
    pcpg_orig = per_cpg_breakdown(pe_full, "c2_pass")
    pcpg_typed = per_cpg_breakdown(pe_full_typed, "c2_pass_typed")
    for i, (cpg, d) in enumerate(pcpg_orig.items()):
        if i >= 10:
            break
        print(
            f"  {cpg}: n={d['n']}, FA3={d['fa_strict_3way_pct']}%, TCC fail={d['tcc_fail_pct']}%, CwT pass={d['cwt_pass_pct']}%"
        )

    out["per_cpg"] = {
        "phase_b_original": pcpg_orig,
        "phase_b_typed": pcpg_typed,
    }

    # Save
    Path(args.out_json).parent.mkdir(parents=True, exist_ok=True)
    open(args.out_json, "w").write(json.dumps(out, indent=2, default=str))
    print(f"\nSaved → {args.out_json}")
    Path(args.out_per_cpg).parent.mkdir(parents=True, exist_ok=True)
    open(args.out_per_cpg, "w").write(json.dumps(out["per_cpg"], indent=2, default=str))
    print(f"Saved → {args.out_per_cpg}")

    # LaTeX macros
    tex = ["% v6 Full (Phase B) macros — auto-generated. Use \\v6Full prefix to disambiguate."]
    if fa_pb_orig:
        tex += [
            f"\\providecommand{{\\vSixFullStrictFAThree}}{{{fa_pb_orig['fa_strict_3way_pct']}}}",
            f"\\providecommand{{\\vSixFullStrictFAThreeCount}}{{{fa_pb_orig['fa_strict_3way_asc_paf_cwt']}}}",
            f"\\providecommand{{\\vSixFullStrictFAFour}}{{{fa_pb_orig['fa_strict_4way_pct']}}}",
            f"\\providecommand{{\\vSixFullConsensusFA}}{{{fa_pb_orig['fa_consensus_tom_asc_cwt_pct']}}}",
            f"\\providecommand{{\\vSixFullConsensusFACount}}{{{fa_pb_orig['fa_consensus_tom_asc_cwt']}}}",
            f"\\providecommand{{\\vSixFullN}}{{{fa_pb_orig['n']}}}",
        ]
    if fa_pb_typed:
        tex += [
            f"\\providecommand{{\\vSixFullTypedStrictFAThree}}{{{fa_pb_typed['fa_strict_3way_pct']}}}",
            f"\\providecommand{{\\vSixFullTypedConsensusFA}}{{{fa_pb_typed['fa_consensus_tom_asc_cwt_pct']}}}",
        ]
    if e_pb_orig:
        tex += [
            f"\\providecommand{{\\vSixFullCresFiveEtaSq}}{{{e_pb_orig['eta2_eval']:.4f}}}",
            f"\\providecommand{{\\vSixFullCresFiveEtaRun}}{{{e_pb_orig['eta2_run']:.4f}}}",
            f"\\providecommand{{\\vSixFullCresFiveRatio}}{{{e_pb_orig['eta2_eval_run_ratio']:.2f}}}",
        ]
    if e_pb_typed:
        tex += [
            f"\\providecommand{{\\vSixFullTypedCresFiveEtaSq}}{{{e_pb_typed['eta2_eval']:.4f}}}",
            f"\\providecommand{{\\vSixFullTypedCresFiveEtaRun}}{{{e_pb_typed['eta2_run']:.4f}}}",
            f"\\providecommand{{\\vSixFullTypedCresFiveRatio}}{{{e_pb_typed['eta2_eval_run_ratio']:.2f}}}",
        ]
    Path(args.out_tex).parent.mkdir(parents=True, exist_ok=True)
    open(args.out_tex, "w").write("\n".join(tex) + "\n")
    print(f"Saved → {args.out_tex}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
