"""Phase 1.G — Re-aggregation across 3 CwT variants.

Computes hero numbers (FA, η², pair reversal, flip rate, BSR, matched-pair) for
all three CwT variants:
    Original (5-type): omission + commission + timing + sequence + deviation
    4-type:            commission + timing + sequence + deviation     (drops OMISSION)
    3-type:            commission + timing + sequence                 (drops OMISSION + DEVIATION)

This generalises phase1_reaggregate.py's two-variant comparison to three.

Outputs:
    evidence_pack/phase1g/phase1g_3variants.json     — full results
    evidence_pack/phase1g/phase1g_3variants_macros.tex — LaTeX macros
    evidence_pack/phase1g/phase1g_3variants_table.tex — Sensitivity table (3 rows)

Usage:
    PYTHONPATH=..:. /home/anonymous-org/anaconda3/bin/python3.13 \
        scripts/experiments/phase1g_reaggregate_3variants.py
    PYTHONPATH=..:. /home/anonymous-org/anaconda3/bin/python3.13 \
        scripts/experiments/phase1g_reaggregate_3variants.py --w8
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path
import time
from typing import Any

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[2]
TYPED_VM = REPO_ROOT / "evidence_pack" / "verdicts" / "verdict_matrix_v6_typed_phase1.json"
OUTPUT_DIR = REPO_ROOT / "evidence_pack" / "phase1g"

DEEPSEEK_MODEL = "deepseek_r1_7b"

VARIANTS = [
    ("original", "c2_pass", "Original (5-type)"),
    ("four_type", "cwt_typed_4type_pass", "4-type"),
    ("three_type", "cwt_typed_pass", "3-type"),
]


def load_vm(path: Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    with open(path) as f:
        data = json.load(f)
    return data["per_episode"], data.get("metadata", {})


def filter_w8(pe: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [ep for ep in pe if ep.get("model_dir", ep.get("model", "")) != DEEPSEEK_MODEL]


def pass_rate_for(pe: list[dict[str, Any]], col: str) -> float:
    n = len(pe)
    cnt = sum(1 for ep in pe if ep.get(col, False))
    return round(100 * cnt / max(n, 1), 2)


def consensus_fa(pe: list[dict[str, Any]], cwt_col: str) -> dict[str, Any]:
    n = len(pe)
    fa3 = sum(1 for ep in pe if ep["ac_proxy"] and ep[cwt_col] and ep["mab_proxy"] and ep["v4_hard"])
    fa4 = sum(1 for ep in pe if ep["dxem"] and ep["ac_proxy"] and ep[cwt_col] and ep["mab_proxy"] and ep["v4_hard"])
    fa_tom_asc_cwt = sum(1 for ep in pe if ep["dxem"] and ep["ac_proxy"] and ep[cwt_col] and ep["v4_hard"])
    return {
        "strict_3way_fa": fa3,
        "strict_3way_fa_pct": round(100 * fa3 / max(n, 1), 2),
        "strict_4way_fa": fa4,
        "strict_4way_fa_pct": round(100 * fa4 / max(n, 1), 2),
        "consensus_tom_asc_cwt": fa_tom_asc_cwt,
        "consensus_tom_asc_cwt_pct": round(100 * fa_tom_asc_cwt / max(n, 1), 2),
        "n": n,
    }


def verdict_flip_rate(pe: list[dict[str, Any]], cwt_col: str) -> dict[str, Any]:
    n = len(pe)
    evs = ["ac_proxy", cwt_col, "mab_proxy", "v4_hard"]
    flips = 0
    for ep in pe:
        verdicts = set()
        for ev in evs:
            v = ep.get(ev, False) if ev != "v4_hard" else (not ep.get(ev, True))
            verdicts.add(v)
        if len(verdicts) > 1:
            flips += 1
    return {"flip_count": flips, "flip_rate_pct": round(100 * flips / max(n, 1), 2), "n": n}


def pair_reversal(pe: list[dict[str, Any]], cwt_col: str) -> dict[str, Any]:
    cells: dict[tuple[str, str], dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    evs = ["ac_proxy", cwt_col, "mab_proxy", "v4_hard"]
    for ep in pe:
        model = ep.get("model_dir", ep.get("model", ""))
        sid = ep.get("scenario_id", "")
        key = (model, sid)
        for ev in evs:
            v = ep.get(ev, False) if ev != "v4_hard" else (not ep.get(ev, True))
            cells[key][ev].append(v)
    cell_means: dict[tuple[str, str], dict[str, float]] = {}
    for k, vs in cells.items():
        cell_means[k] = {ev: sum(vs[ev]) / max(len(vs[ev]), 1) for ev in evs}
    models = sorted({k[0] for k in cell_means})
    scenarios = sorted({k[1] for k in cell_means})
    total = 0
    reversals = 0
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
                    reversals += 1
    return {
        "n_comparisons": total,
        "n_reversals": reversals,
        "reversal_rate_pct": round(100 * reversals / max(total, 1), 2),
    }


def eta_squared(pe: list[dict[str, Any]], cwt_col: str) -> dict[str, Any]:
    evs = ["ac_proxy", cwt_col, "mab_proxy", "v4_hard"]
    rows: list[dict[str, Any]] = []
    for ep in pe:
        for ev in evs:
            v = ep.get(ev, False) if ev != "v4_hard" else (not ep.get(ev, True))
            rows.append(
                {
                    "model": ep.get("model_dir", ep.get("model", "")),
                    "scenario": ep.get("scenario_id", ""),
                    "run": ep.get("run_index", 0),
                    "evaluator": ev,
                    "verdict": int(v),
                }
            )
    arr = np.array([r["verdict"] for r in rows])
    grand_mean = arr.mean()
    ss_total = float(((arr - grand_mean) ** 2).sum())
    if ss_total == 0:
        return {"eta2_eval": 0.0, "eta2_run": 0.0, "eta2_ratio": 0.0}
    ev_means: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        ev_means[r["evaluator"]].append(r["verdict"])
    ss_eval = sum(len(v) * (np.mean(v) - grand_mean) ** 2 for v in ev_means.values())
    run_means: dict[int, list[int]] = defaultdict(list)
    for r in rows:
        run_means[r["run"]].append(r["verdict"])
    ss_run = sum(len(v) * (np.mean(v) - grand_mean) ** 2 for v in run_means.values())
    eta2_e = round(float(ss_eval / ss_total), 4)
    eta2_r = round(float(ss_run / ss_total), 6)
    return {
        "eta2_eval": eta2_e,
        "eta2_run": eta2_r,
        "eta2_ratio": round(eta2_e / max(eta2_r, 1e-9), 1),
    }


def bsr_per_evaluator(pe: list[dict[str, Any]], cwt_col: str) -> dict[str, float]:
    n = len(pe)
    if n == 0:
        return {}
    results: dict[str, float] = {}
    eval_map = {"ASC": "ac_proxy", "PAF": "mab_proxy", "CwT": cwt_col, "TOM": "dxem"}
    for label, col in eval_map.items():
        tp = fn = fp = tn = 0
        for ep in pe:
            pred = ep.get(col, False)
            truth = not ep.get("v4_hard", True)
            if pred and truth:
                tp += 1
            elif pred and not truth:
                fp += 1
            elif not pred and truth:
                fn += 1
            else:
                tn += 1
        total_pos = tp + fn
        total_neg = fp + tn
        if total_pos == 0 or total_neg == 0:
            results[label] = 0.5
            continue
        fpr = fp / total_neg
        fnr = fn / total_pos
        results[label] = round((fpr + fnr) / 2, 4)
    return results


def matched_pair_detection(pe: list[dict[str, Any]], cwt_col: str) -> dict[str, Any]:
    groups: dict[tuple[str, int], dict[str, dict[str, bool]]] = defaultdict(dict)
    eval_cols = {"ASC": "ac_proxy", "PAF": "mab_proxy", "CwT": cwt_col, "TCC": "v4_hard"}
    for ep in pe:
        sid = ep.get("scenario_id", "")
        ri = ep.get("run_index", 0)
        model = ep.get("model_dir", ep.get("model", ""))
        verdicts = {label: ep.get(col, False) for label, col in eval_cols.items()}
        groups[(sid, ri)][model] = verdicts
    total_pairs = 0
    detections: dict[str, int] = dict.fromkeys(eval_cols, 0)
    for (_sid, _ri), model_verdicts in groups.items():
        models = sorted(model_verdicts.keys())
        for ma, mb in combinations(models, 2):
            total_pairs += 1
            for label in eval_cols:
                if model_verdicts[ma][label] != model_verdicts[mb][label]:
                    detections[label] += 1
    return {
        "total_pairs": total_pairs,
        "detection_rates": {label: round(100 * cnt / max(total_pairs, 1), 2) for label, cnt in detections.items()},
    }


def compute_variant(pe: list[dict[str, Any]], cwt_col: str) -> dict[str, Any]:
    return {
        "cwt_pass_rate_pct": pass_rate_for(pe, cwt_col),
        "consensus_fa": consensus_fa(pe, cwt_col),
        "flip_rate": verdict_flip_rate(pe, cwt_col),
        "pair_reversal": pair_reversal(pe, cwt_col),
        "eta_squared": eta_squared(pe, cwt_col),
        "bsr": bsr_per_evaluator(pe, cwt_col),
        "matched_pair": matched_pair_detection(pe, cwt_col),
    }


def build_table(variants: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    """Three-row sensitivity table: each metric × {original, 4-type, 3-type}."""
    metrics = []
    for label_key, _, label_disp in VARIANTS:
        v = variants[label_key]
        metrics.append(
            {
                "variant": label_disp,
                "cwt_pass": v["cwt_pass_rate_pct"],
                "fa3": v["consensus_fa"]["strict_3way_fa_pct"],
                "fa4": v["consensus_fa"]["strict_4way_fa_pct"],
                "flip": v["flip_rate"]["flip_rate_pct"],
                "reversal": v["pair_reversal"]["reversal_rate_pct"],
                "eta_eval": v["eta_squared"]["eta2_eval"],
                "eta_ratio": v["eta_squared"]["eta2_ratio"],
                "bsr_cwt": v["bsr"].get("CwT", 0.5),
                "matched_cwt": v["matched_pair"]["detection_rates"].get("CwT", 0.0),
            }
        )
    return metrics


def generate_macros(variants: dict[str, dict[str, Any]], suffix: str) -> str:
    lines = [
        "% Phase 1.G 3-variant CwT macros",
        f"% Generated: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
        f"% Suffix: {suffix} (Full vs W8)",
        "",
    ]
    for var_key, _col, var_disp in VARIANTS:
        v = variants[var_key]
        kk = "Orig" if var_key == "original" else ("FourType" if var_key == "four_type" else "ThreeType")
        prefix = f"\\providecommand{{\\phaseOneG{kk}{suffix}"
        lines.append(f"{prefix}CwTPass}}{{{v['cwt_pass_rate_pct']}}}")
        lines.append(f"{prefix}FA3}}{{{v['consensus_fa']['strict_3way_fa_pct']}}}")
        lines.append(f"{prefix}FA4}}{{{v['consensus_fa']['strict_4way_fa_pct']}}}")
        lines.append(f"{prefix}Flip}}{{{v['flip_rate']['flip_rate_pct']}}}")
        lines.append(f"{prefix}Reversal}}{{{v['pair_reversal']['reversal_rate_pct']}}}")
        lines.append(f"{prefix}EtaEval}}{{{v['eta_squared']['eta2_eval']}}}")
        lines.append(f"{prefix}EtaRatio}}{{{v['eta_squared']['eta2_ratio']}}}")
        lines.append(f"{prefix}BSRCwT}}{{{v['bsr'].get('CwT', 0.5)}}}")
        lines.append(f"{prefix}MatchedCwT}}{{{v['matched_pair']['detection_rates'].get('CwT', 0.0)}}}")
    return "\n".join(lines) + "\n"


def generate_table(table_rows: list[dict[str, Any]], suffix: str) -> str:
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{CwT 3-variant sensitivity (" + suffix + r" corpus): Original (5-type), 4-type (drops OMISSION), 3-type (drops OMISSION+DEVIATION).}",
        r"\label{tab:cwt_3variants_" + suffix.lower() + "}",
        r"\begin{tabular}{lrrrrrrr}",
        r"\toprule",
        r"Variant & Pass\% & FA3\% & Flip\% & Rev.\% & $\eta^2_{\text{eval}}$ & BSR(CwT) & Det.(CwT)\% \\",
        r"\midrule",
    ]
    for r in table_rows:
        lines.append(
            f"  {r['variant']} & {r['cwt_pass']:.2f} & {r['fa3']:.2f} & {r['flip']:.2f} & "
            f"{r['reversal']:.2f} & {r['eta_eval']:.4f} & {r['bsr_cwt']:.4f} & {r['matched_cwt']:.2f} \\\\"
        )
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w8", action="store_true", help="Exclude DeepSeek (W8 filter)")
    parser.add_argument("--typed-vm", type=Path, default=TYPED_VM)
    args = parser.parse_args()

    suffix = "W8" if args.w8 else "Full"
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Loading VM: {args.typed_vm}")
    pe, _meta = load_vm(args.typed_vm)
    print(f"  Episodes: {len(pe)}")

    if args.w8:
        pe = filter_w8(pe)
        print(f"  After W8 filter: {len(pe)}")

    n = len(pe)

    # Compute all 3 variants
    variants: dict[str, dict[str, Any]] = {}
    for var_key, col, var_disp in VARIANTS:
        print(f"\n=== {var_disp} ({col}) ===")
        variants[var_key] = compute_variant(pe, col)
        v = variants[var_key]
        print(f"  CwT pass:        {v['cwt_pass_rate_pct']:.2f}%")
        print(f"  Strict FA3:      {v['consensus_fa']['strict_3way_fa_pct']:.2f}%")
        print(f"  Flip rate:       {v['flip_rate']['flip_rate_pct']:.2f}%")
        print(f"  Pair reversal:   {v['pair_reversal']['reversal_rate_pct']:.2f}%")
        print(f"  eta2(eval):      {v['eta_squared']['eta2_eval']:.4f}")
        print(f"  eta2 ratio:      {v['eta_squared']['eta2_ratio']:.1f}x")
        print(f"  BSR(CwT):        {v['bsr'].get('CwT', 0.5):.4f}")
        print(f"  Matched(CwT):    {v['matched_pair']['detection_rates'].get('CwT', 0.0):.2f}%")

    # Sensitivity decision
    o, ft, tt = variants["original"], variants["four_type"], variants["three_type"]
    fa_o = o["consensus_fa"]["strict_3way_fa_pct"]
    fa_ft = ft["consensus_fa"]["strict_3way_fa_pct"]
    fa_tt = tt["consensus_fa"]["strict_3way_fa_pct"]
    print(f"\n=== Scenario classification ===")
    range_total = abs(fa_tt - fa_o)
    if range_total > 0:
        ft_pos = abs(fa_ft - fa_o) / range_total
        print(f"  4-type FA position: {ft_pos:.2f} (0.0=Original, 1.0=3-type)")
        if ft_pos < 0.33:
            print("  Scenario A: 4-type close to Original — clean 4-type adoption recommended")
        elif ft_pos > 0.67:
            print("  Scenario C: 4-type close to 3-type — Original justified, OMISSION dominates")
        else:
            print("  Scenario B: 4-type middle — explicit trade-off; choose Original or 4-type")

    table_rows = build_table(variants)
    macros = generate_macros(variants, suffix)
    tex_table = generate_table(table_rows, suffix)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUTPUT_DIR / f"phase1g_3variants_{suffix.lower()}.json"
    out_macros = OUTPUT_DIR / f"phase1g_3variants_{suffix.lower()}_macros.tex"
    out_table = OUTPUT_DIR / f"phase1g_3variants_{suffix.lower()}_table.tex"

    full = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_episodes": n,
        "w8_filtered": args.w8,
        "variants": variants,
        "sensitivity_table": table_rows,
    }
    with open(out_json, "w") as f:
        json.dump(full, f, indent=2, default=str)
    with open(out_macros, "w") as f:
        f.write(macros)
    with open(out_table, "w") as f:
        f.write(tex_table)

    print(f"\n[{time.strftime('%H:%M:%S')}] Saved:")
    print(f"  {out_json}")
    print(f"  {out_macros}")
    print(f"  {out_table}")
    elapsed = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] Done in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
