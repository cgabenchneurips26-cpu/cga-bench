"""Phase 1.H — Model-pair level pair reversal under 3 CwT variants.

For each unordered pair of the 8 models, computes the cross-evaluator pair
reversal rate (the canonical paper "75% hero claim" metric, restricted to a
single model-pair) under each CwT variant. This pinpoints which model
comparisons are most/least sensitive to the evaluator-CwT choice.

Inputs:
    evidence_pack/verdicts/verdict_matrix_v6_typed_phase1.json
    (must already contain c2_pass, cwt_typed_pass, cwt_typed_4type_pass)

Outputs:
    evidence_pack/phase1h/phase1h_modelpair_reversal_{full,w8}.json
    evidence_pack/phase1h/phase1h_modelpair_reversal_{full,w8}_table.tex

Usage:
    PYTHONPATH=..:. /home/anonymous-org/anaconda3/bin/python3.13 \
        scripts/experiments/phase1h_modelpair_reversal.py
    PYTHONPATH=..:. /home/anonymous-org/anaconda3/bin/python3.13 \
        scripts/experiments/phase1h_modelpair_reversal.py --w8
"""

from __future__ import annotations

import argparse
from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path
import time
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
TYPED_VM = REPO_ROOT / "evidence_pack" / "verdicts" / "verdict_matrix_v6_typed_phase1.json"
OUTPUT_DIR = REPO_ROOT / "evidence_pack" / "phase1h"

DEEPSEEK_MODEL = "deepseek_r1_7b"

VARIANTS = [
    ("original", "c2_pass"),
    ("four_type", "cwt_typed_4type_pass"),
    ("three_type", "cwt_typed_pass"),
]


def load_vm(path: Path) -> list[dict[str, Any]]:
    with open(path) as f:
        data = json.load(f)
    return data["per_episode"]


def filter_w8(pe: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [ep for ep in pe if ep.get("model_dir", ep.get("model", "")) != DEEPSEEK_MODEL]


def model_pair_reversal(pe: list[dict[str, Any]], cwt_col: str) -> dict[str, dict[str, float]]:
    """For each (model_a, model_b), compute pair reversal rate within their cells.

    Returns {(model_a, model_b): {n_comparisons, n_reversals, rate_pct}}.
    """
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

    pair_stats: dict[str, dict[str, float]] = {}
    for ma, mb in combinations(models, 2):
        total = 0
        reversals = 0
        for sc in scenarios:
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
        rate = round(100 * reversals / max(total, 1), 2)
        pair_stats[f"{ma}__{mb}"] = {
            "n_comparisons": total,
            "n_reversals": reversals,
            "reversal_rate_pct": rate,
        }
    return pair_stats


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w8", action="store_true")
    parser.add_argument("--typed-vm", type=Path, default=TYPED_VM)
    args = parser.parse_args()

    suffix = "w8" if args.w8 else "full"
    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Loading VM: {args.typed_vm}")
    pe = load_vm(args.typed_vm)
    print(f"  Episodes: {len(pe)}")
    if args.w8:
        pe = filter_w8(pe)
        print(f"  W8 filter: {len(pe)}")
    n = len(pe)

    results: dict[str, dict[str, dict[str, float]]] = {}
    for var_key, col in VARIANTS:
        print(f"\n=== Variant {var_key} ({col}) ===")
        results[var_key] = model_pair_reversal(pe, col)
        # Summary
        rates = [v["reversal_rate_pct"] for v in results[var_key].values()]
        if rates:
            mean_rate = sum(rates) / len(rates)
            min_rate = min(rates)
            max_rate = max(rates)
            print(f"  Pairs: {len(rates)}  Mean: {mean_rate:.2f}%  Range: [{min_rate:.2f}, {max_rate:.2f}]")

    # Compute robustness: how many model-pairs change reversal rate by >=10pp across variants?
    pairs = sorted(results["original"].keys())
    print(f"\n=== Cross-variant robustness ({suffix} corpus) ===")
    big_swing = 0
    for p in pairs:
        o = results["original"][p]["reversal_rate_pct"]
        ft = results["four_type"][p]["reversal_rate_pct"]
        tt = results["three_type"][p]["reversal_rate_pct"]
        rng = max(o, ft, tt) - min(o, ft, tt)
        if rng >= 10.0:
            big_swing += 1
    print(f"  Model-pairs with >=10pp range across variants: {big_swing}/{len(pairs)}")

    # LaTeX table
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    out_json = OUTPUT_DIR / f"phase1h_modelpair_reversal_{suffix}.json"
    out_tex = OUTPUT_DIR / f"phase1h_modelpair_reversal_{suffix}_table.tex"

    full_payload = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_episodes": n,
        "w8_filtered": args.w8,
        "n_pairs": len(pairs),
        "n_pairs_big_swing": big_swing,
        "by_variant": results,
    }
    with open(out_json, "w") as f:
        json.dump(full_payload, f, indent=2, default=str)

    # Table: rows=pairs, cols=variants
    lines = [
        r"\begin{table}[htbp]",
        r"\centering\small",
        r"\caption{Model-pair pair reversal rate (\%) across CwT variants (" + suffix.upper() + r" corpus).}",
        r"\label{tab:phase1h_modelpair_" + suffix + "}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"Model pair & Original & 4-type & 3-type \\",
        r"\midrule",
    ]
    for p in pairs:
        o = results["original"][p]["reversal_rate_pct"]
        ft = results["four_type"][p]["reversal_rate_pct"]
        tt = results["three_type"][p]["reversal_rate_pct"]
        ma, mb = p.split("__")
        lines.append(f"  {ma} vs {mb} & {o:.2f} & {ft:.2f} & {tt:.2f} \\\\")
    lines += [r"\bottomrule", r"\end{tabular}", r"\end{table}"]
    with open(out_tex, "w") as f:
        f.write("\n".join(lines) + "\n")

    print(f"\n[{time.strftime('%H:%M:%S')}] Saved:")
    print(f"  {out_json}")
    print(f"  {out_tex}")
    elapsed = time.time() - t0
    print(f"[{time.strftime('%H:%M:%S')}] Done in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
