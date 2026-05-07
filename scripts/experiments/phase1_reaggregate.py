"""Phase 1.C — Re-aggregation: hero numbers, sensitivity table, verification.

Loads verdict_matrix_v6_typed_phase1.json (from Phase 1.B) and computes:
  C1: Hero numbers (FA, η², pair reversal, flip rate, pass rates)
  C3: Sensitivity table (original CwT vs typed CwT, per hero number)
  E1: Theorem 1 projection ordering (ε_term > ε_aset > ε_nord ≈ ε_nctx)
  E2: Matched-pair detection preservation

Outputs:
  evidence_pack/phase1/phase1_sensitivity.json     — full results
  evidence_pack/phase1/phase1_sensitivity_macros.tex — LaTeX macros
  evidence_pack/phase1/phase1_sensitivity_table.tex — LaTeX table

Usage:
    PYTHONPATH=..:. python scripts/experiments/phase1_reaggregate.py
    PYTHONPATH=..:. python scripts/experiments/phase1_reaggregate.py --w8  # exclude DeepSeek
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
ORIG_VM = REPO_ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
OUTPUT_DIR = REPO_ROOT / "evidence_pack" / "phase1"

DEEPSEEK_MODEL = "deepseek_r1_7b"

# Evaluator columns in verdict matrix
EVAL_COLS = {
    "ASC": "ac_proxy",
    "PAF": "mab_proxy",
    "CwT": "c2_pass",
    "CwT-typed": "cwt_typed_pass",
    "TOM": "dxem",
    "ACov": "acov_pass",
    "TCC": "v4_hard",
}


def load_vm(path: Path) -> list[dict[str, Any]]:
    """Load per_episode from verdict matrix JSON."""
    with open(path) as f:
        data = json.load(f)
    return data["per_episode"]


def filter_w8(pe: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Exclude DeepSeek episodes (W8 filter)."""
    return [ep for ep in pe if ep.get("model_dir", ep.get("model", "")) != DEEPSEEK_MODEL]


# ---------------------------------------------------------------------------
# C1: Hero numbers
# ---------------------------------------------------------------------------


def pass_rates(pe: list[dict[str, Any]], c2_field: str) -> dict[str, float]:
    """Per-evaluator pass rates."""
    n = len(pe)
    rates: dict[str, float] = {}
    for label, col in EVAL_COLS.items():
        if label == "CwT-typed" and c2_field == "c2_pass":
            continue  # skip typed when computing original
        if label == "CwT" and c2_field == "cwt_typed_pass":
            continue  # skip original when computing typed
        actual_col = c2_field if col in ("c2_pass", "cwt_typed_pass") else col
        count = sum(1 for ep in pe if ep.get(actual_col, False))
        rates[label if label not in ("CwT", "CwT-typed") else "CwT"] = round(100 * count / n, 2)
    return rates


def consensus_fa(pe: list[dict[str, Any]], c2_field: str) -> dict[str, Any]:
    """Consensus FA: pass on evaluator set + fail on TCC.

    v4_hard=True means episode HAS hard violations (TCC fails it).
    FA = evaluator passes but TCC fails → ep[eval]=True AND ep[v4_hard]=True.
    """
    n = len(pe)
    # 3-way: ASC ∩ CwT ∩ PAF (all pass, TCC fails)
    fa3 = sum(1 for ep in pe if ep["ac_proxy"] and ep[c2_field] and ep["mab_proxy"] and ep["v4_hard"])
    # 4-way: + TOM
    fa4 = sum(1 for ep in pe if ep["dxem"] and ep["ac_proxy"] and ep[c2_field] and ep["mab_proxy"] and ep["v4_hard"])
    # TOM ∩ ASC ∩ CwT (paper's current consensus — degenerate)
    fa_tom_asc_cwt = sum(1 for ep in pe if ep["dxem"] and ep["ac_proxy"] and ep[c2_field] and ep["v4_hard"])
    return {
        "strict_3way_fa": fa3,
        "strict_3way_fa_pct": round(100 * fa3 / n, 2),
        "strict_4way_fa": fa4,
        "strict_4way_fa_pct": round(100 * fa4 / n, 2),
        "consensus_fa_tom_asc_cwt": fa_tom_asc_cwt,
        "consensus_fa_tom_asc_cwt_pct": round(100 * fa_tom_asc_cwt / n, 2),
        "n": n,
    }


def verdict_flip_rate(pe: list[dict[str, Any]], c2_field: str) -> dict[str, Any]:
    """Fraction of episodes where at least 2 evaluators disagree."""
    n = len(pe)
    evs = ["ac_proxy", c2_field, "mab_proxy", "v4_hard"]
    flips = 0
    for ep in pe:
        verdicts = set()
        for ev in evs:
            v = ep.get(ev, False) if ev != "v4_hard" else (not ep.get(ev, True))
            verdicts.add(v)
        if len(verdicts) > 1:
            flips += 1
    return {
        "flip_count": flips,
        "flip_rate_pct": round(100 * flips / n, 2),
        "n": n,
    }


def pair_reversal(pe: list[dict[str, Any]], c2_field: str) -> dict[str, Any]:
    """Cross-evaluator model-ranking reversal rate."""
    cells: dict[tuple[str, str], dict[str, list[bool]]] = defaultdict(lambda: defaultdict(list))
    evs = ["ac_proxy", c2_field, "mab_proxy", "v4_hard"]
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


def eta_squared(pe: list[dict[str, Any]], c2_field: str) -> dict[str, Any]:
    """RM-ANOVA-style η² for evaluator and run factors."""
    evs = ["ac_proxy", c2_field, "mab_proxy", "v4_hard"]
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


# ---------------------------------------------------------------------------
# E1: Projection ordering (Bayes error proxies)
# ---------------------------------------------------------------------------


def bsr_per_evaluator(pe: list[dict[str, Any]], c2_field: str) -> dict[str, float]:
    """Balanced Segregation Rate vs TCC for each evaluator."""
    n = len(pe)
    if n == 0:
        return {}
    results: dict[str, float] = {}
    eval_map = {
        "ASC": "ac_proxy",
        "PAF": "mab_proxy",
        "CwT": c2_field,
        "TOM": "dxem",
    }
    for label, col in eval_map.items():
        # BSR = (FP + FN) / (2 * min(P, N))  balanced error rate vs TCC
        tp = fn = fp = tn = 0
        for ep in pe:
            pred = ep.get(col, False)
            # TCC: v4_hard=True means violations (fail), so "pass" = not v4_hard
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


# ---------------------------------------------------------------------------
# E2: Matched-pair detection preservation
# ---------------------------------------------------------------------------


def matched_pair_detection(pe: list[dict[str, Any]], c2_field: str) -> dict[str, Any]:
    """Check how many evaluators detect the canonical matched-pair difference."""
    # Group by (scenario, run) to find model-pairs where only model differs
    groups: dict[tuple[str, int], dict[str, dict[str, bool]]] = defaultdict(dict)
    eval_cols_check = {
        "ASC": "ac_proxy",
        "PAF": "mab_proxy",
        "CwT": c2_field,
        "TCC": "v4_hard",
    }
    for ep in pe:
        sid = ep.get("scenario_id", "")
        ri = ep.get("run_index", 0)
        model = ep.get("model_dir", ep.get("model", ""))
        verdicts = {}
        for label, col in eval_cols_check.items():
            verdicts[label] = ep.get(col, False)
        groups[(sid, ri)][model] = verdicts

    # Count detection: for each (scenario, run), for each model pair,
    # how often each evaluator distinguishes them
    total_pairs = 0
    detections: dict[str, int] = dict.fromkeys(eval_cols_check, 0)
    for (_sid, _ri), model_verdicts in groups.items():
        models = sorted(model_verdicts.keys())
        for ma, mb in combinations(models, 2):
            total_pairs += 1
            for label in eval_cols_check:
                if model_verdicts[ma][label] != model_verdicts[mb][label]:
                    detections[label] += 1

    return {
        "total_pairs": total_pairs,
        "detection_rates": {label: round(100 * cnt / max(total_pairs, 1), 2) for label, cnt in detections.items()},
    }


# ---------------------------------------------------------------------------
# C3: Sensitivity table
# ---------------------------------------------------------------------------


def build_sensitivity_table(
    orig_results: dict[str, Any],
    typed_results: dict[str, Any],
) -> list[dict[str, Any]]:
    """Build row-by-row sensitivity comparison."""
    rows: list[dict[str, Any]] = []

    def add_row(name: str, orig_val: float, typed_val: float, unit: str = "%") -> None:
        delta = typed_val - orig_val
        rel = round(100 * delta / max(abs(orig_val), 1e-9), 1) if orig_val != 0 else 0.0
        rows.append(
            {
                "metric": name,
                "original": orig_val,
                "typed": typed_val,
                "delta": round(delta, 2),
                "relative_pct": rel,
                "unit": unit,
            }
        )

    # Pass rates
    for ev in ["ASC", "CwT", "PAF", "TCC", "TOM"]:
        o = orig_results["pass_rates"].get(ev, 0)
        t = typed_results["pass_rates"].get(ev, 0)
        add_row(f"Pass rate ({ev})", o, t)

    # Consensus FA
    add_row(
        "Strict 3-way FA",
        orig_results["consensus_fa"]["strict_3way_fa_pct"],
        typed_results["consensus_fa"]["strict_3way_fa_pct"],
    )
    add_row(
        "Strict 4-way FA",
        orig_results["consensus_fa"]["strict_4way_fa_pct"],
        typed_results["consensus_fa"]["strict_4way_fa_pct"],
    )

    # Flip rate
    add_row(
        "Verdict flip rate", orig_results["flip_rate"]["flip_rate_pct"], typed_results["flip_rate"]["flip_rate_pct"]
    )

    # Pair reversal
    add_row(
        "Pair reversal rate",
        orig_results["pair_reversal"]["reversal_rate_pct"],
        typed_results["pair_reversal"]["reversal_rate_pct"],
    )

    # η²
    add_row(
        "η²(evaluator)", orig_results["eta_squared"]["eta2_eval"], typed_results["eta_squared"]["eta2_eval"], unit=""
    )
    add_row(
        "η²(eval)/η²(run) ratio",
        orig_results["eta_squared"]["eta2_ratio"],
        typed_results["eta_squared"]["eta2_ratio"],
        unit="×",
    )

    # BSR per evaluator
    for ev in ["ASC", "CwT", "PAF", "TOM"]:
        o = orig_results["bsr"].get(ev, 0)
        t = typed_results["bsr"].get(ev, 0)
        add_row(f"BSR ({ev})", o, t, unit="")

    return rows


# ---------------------------------------------------------------------------
# LaTeX generation
# ---------------------------------------------------------------------------


def generate_macros(
    orig: dict[str, Any],
    typed: dict[str, Any],
    sensitivity: list[dict[str, Any]],
) -> str:
    """Generate providecommand macros for Phase 1 results."""
    lines = [
        "% Phase 1.C Re-aggregation macros",
        "% Auto-generated by phase1_reaggregate.py",
        f"% Generated: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
        "",
        "% --- Original CwT hero numbers ---",
        f"\\providecommand{{\\phaseOneOrigCwTPass}}{{{orig['pass_rates'].get('CwT', 0)}}}",
        f"\\providecommand{{\\phaseOneOrigFA3}}{{{orig['consensus_fa']['strict_3way_fa_pct']}}}",
        f"\\providecommand{{\\phaseOneOrigFA4}}{{{orig['consensus_fa']['strict_4way_fa_pct']}}}",
        f"\\providecommand{{\\phaseOneOrigFlip}}{{{orig['flip_rate']['flip_rate_pct']}}}",
        f"\\providecommand{{\\phaseOneOrigReversal}}{{{orig['pair_reversal']['reversal_rate_pct']}}}",
        f"\\providecommand{{\\phaseOneOrigEtaEval}}{{{orig['eta_squared']['eta2_eval']}}}",
        f"\\providecommand{{\\phaseOneOrigEtaRatio}}{{{orig['eta_squared']['eta2_ratio']}}}",
        "",
        "% --- Typed CwT hero numbers ---",
        f"\\providecommand{{\\phaseOneTypedCwTPass}}{{{typed['pass_rates'].get('CwT', 0)}}}",
        f"\\providecommand{{\\phaseOneTypedFA3}}{{{typed['consensus_fa']['strict_3way_fa_pct']}}}",
        f"\\providecommand{{\\phaseOneTypedFA4}}{{{typed['consensus_fa']['strict_4way_fa_pct']}}}",
        f"\\providecommand{{\\phaseOneTypedFlip}}{{{typed['flip_rate']['flip_rate_pct']}}}",
        f"\\providecommand{{\\phaseOneTypedReversal}}{{{typed['pair_reversal']['reversal_rate_pct']}}}",
        f"\\providecommand{{\\phaseOneTypedEtaEval}}{{{typed['eta_squared']['eta2_eval']}}}",
        f"\\providecommand{{\\phaseOneTypedEtaRatio}}{{{typed['eta_squared']['eta2_ratio']}}}",
        "",
        "% --- Deltas (typed - original) ---",
    ]
    for row in sensitivity:
        safe_name = row["metric"].replace(" ", "").replace("(", "").replace(")", "")
        safe_name = safe_name.replace("/", "Over").replace("²", "Sq").replace("η", "Eta")
        lines.append(f"\\providecommand{{\\phaseOneDelta{safe_name}}}{{{row['delta']:+.2f}}}")
    return "\n".join(lines) + "\n"


def generate_sensitivity_tex(sensitivity: list[dict[str, Any]]) -> str:
    """Generate LaTeX booktabs table for sensitivity analysis."""
    lines = [
        r"\begin{table}[htbp]",
        r"\centering",
        r"\caption{Sensitivity of hero numbers to CwT violation-type restriction (Phase~1 typed CwT excludes DEVIATION and OMISSION).}",
        r"\label{tab:cwt_sensitivity}",
        r"\begin{tabular}{lrrrl}",
        r"\toprule",
        r"Metric & Original & Typed & $\Delta$ & Unit \\",
        r"\midrule",
    ]
    for row in sensitivity:
        name = row["metric"].replace("η²", r"$\eta^2$").replace("≈", r"$\approx$")
        delta_str = f"{row['delta']:+.2f}"
        lines.append(f"  {name} & {row['original']:.2f} & {row['typed']:.2f} & {delta_str} & {row['unit']} \\\\")
    lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--w8", action="store_true", help="Exclude DeepSeek (W8 filter)")
    parser.add_argument("--typed-vm", type=Path, default=TYPED_VM)
    args = parser.parse_args()

    t0 = time.time()

    # Load typed verdict matrix (has both original + typed columns)
    print(f"[{time.strftime('%H:%M:%S')}] Loading typed verdict matrix: {args.typed_vm}")
    pe = load_vm(args.typed_vm)
    print(f"  Episodes: {len(pe)}")

    if args.w8:
        pe = filter_w8(pe)
        print(f"  After W8 filter: {len(pe)}")

    n = len(pe)

    # --- C1: Hero numbers (original CwT) ---
    print(f"\n{'=' * 60}")
    print("C1: Hero Numbers — Original CwT (c2_pass)")
    print(f"{'=' * 60}")
    orig = {
        "pass_rates": pass_rates(pe, "c2_pass"),
        "consensus_fa": consensus_fa(pe, "c2_pass"),
        "flip_rate": verdict_flip_rate(pe, "c2_pass"),
        "pair_reversal": pair_reversal(pe, "c2_pass"),
        "eta_squared": eta_squared(pe, "c2_pass"),
        "bsr": bsr_per_evaluator(pe, "c2_pass"),
        "matched_pair": matched_pair_detection(pe, "c2_pass"),
    }
    print(f"  CwT pass:       {orig['pass_rates'].get('CwT', 0):.1f}%")
    print(f"  Strict FA3:     {orig['consensus_fa']['strict_3way_fa_pct']:.1f}%")
    print(f"  Strict FA4:     {orig['consensus_fa']['strict_4way_fa_pct']:.1f}%")
    print(f"  Flip rate:      {orig['flip_rate']['flip_rate_pct']:.1f}%")
    print(f"  Pair reversal:  {orig['pair_reversal']['reversal_rate_pct']:.1f}%")
    print(f"  η²(eval):       {orig['eta_squared']['eta2_eval']:.4f}")
    print(f"  η² ratio:       {orig['eta_squared']['eta2_ratio']:.1f}×")

    # --- C1: Hero numbers (typed CwT) ---
    print(f"\n{'=' * 60}")
    print("C1: Hero Numbers — Typed CwT (cwt_typed_pass)")
    print(f"{'=' * 60}")
    typed = {
        "pass_rates": pass_rates(pe, "cwt_typed_pass"),
        "consensus_fa": consensus_fa(pe, "cwt_typed_pass"),
        "flip_rate": verdict_flip_rate(pe, "cwt_typed_pass"),
        "pair_reversal": pair_reversal(pe, "cwt_typed_pass"),
        "eta_squared": eta_squared(pe, "cwt_typed_pass"),
        "bsr": bsr_per_evaluator(pe, "cwt_typed_pass"),
        "matched_pair": matched_pair_detection(pe, "cwt_typed_pass"),
    }
    print(f"  CwT-typed pass: {typed['pass_rates'].get('CwT', 0):.1f}%")
    print(f"  Strict FA3:     {typed['consensus_fa']['strict_3way_fa_pct']:.1f}%")
    print(f"  Strict FA4:     {typed['consensus_fa']['strict_4way_fa_pct']:.1f}%")
    print(f"  Flip rate:      {typed['flip_rate']['flip_rate_pct']:.1f}%")
    print(f"  Pair reversal:  {typed['pair_reversal']['reversal_rate_pct']:.1f}%")
    print(f"  η²(eval):       {typed['eta_squared']['eta2_eval']:.4f}")
    print(f"  η² ratio:       {typed['eta_squared']['eta2_ratio']:.1f}×")

    # --- C3: Sensitivity table ---
    print(f"\n{'=' * 60}")
    print("C3: Sensitivity Table (Original → Typed)")
    print(f"{'=' * 60}")
    sensitivity = build_sensitivity_table(orig, typed)
    for row in sensitivity:
        d = row["delta"]
        print(f"  {row['metric']:<30s}  {row['original']:>8.2f} → {row['typed']:>8.2f}  Δ={d:+.2f}{row['unit']}")

    # --- E1: Projection ordering check ---
    print(f"\n{'=' * 60}")
    print("E1: Projection Ordering (BSR vs TCC)")
    print(f"{'=' * 60}")
    orig_bsr = orig["bsr"]
    typed_bsr = typed["bsr"]
    print("  Original CwT:")
    for ev in ["TOM", "CwT", "ASC", "PAF"]:
        print(f"    {ev}: BSR={orig_bsr.get(ev, 0):.4f}")
    print("  Typed CwT:")
    for ev in ["TOM", "CwT", "ASC", "PAF"]:
        print(f"    {ev}: BSR={typed_bsr.get(ev, 0):.4f}")

    # --- E2: Matched-pair detection ---
    print(f"\n{'=' * 60}")
    print("E2: Matched-pair Detection")
    print(f"{'=' * 60}")
    print("  Original CwT:", orig["matched_pair"]["detection_rates"])
    print("  Typed CwT:   ", typed["matched_pair"]["detection_rates"])

    # --- Save outputs ---
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    full_results = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_episodes": n,
        "w8_filtered": args.w8,
        "original_cwt": orig,
        "typed_cwt": typed,
        "sensitivity_table": sensitivity,
    }

    out_json = OUTPUT_DIR / "phase1_sensitivity.json"
    with open(out_json, "w") as f:
        json.dump(full_results, f, indent=2, default=str)
    print(f"\n[{time.strftime('%H:%M:%S')}] Saved: {out_json}")

    macros = generate_macros(orig, typed, sensitivity)
    out_macros = OUTPUT_DIR / "phase1_sensitivity_macros.tex"
    with open(out_macros, "w") as f:
        f.write(macros)
    print(f"[{time.strftime('%H:%M:%S')}] Saved: {out_macros}")

    tex_table = generate_sensitivity_tex(sensitivity)
    out_tex = OUTPUT_DIR / "phase1_sensitivity_table.tex"
    with open(out_tex, "w") as f:
        f.write(tex_table)
    print(f"[{time.strftime('%H:%M:%S')}] Saved: {out_tex}")

    elapsed = time.time() - t0
    print(f"\n[{time.strftime('%H:%M:%S')}] Done in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
