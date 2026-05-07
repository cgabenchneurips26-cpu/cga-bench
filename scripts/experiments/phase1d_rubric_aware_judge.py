"""Phase 1.D — Rubric-aware LLM judge analysis (offline, no LLM call).

Uses the existing `LLMCatalogueShim` as a rubric-aware judge: the rubric is
the LLM-extracted MUSTs/FORBIDDEN list per CPG (in
`evidence_pack/constraint_comparison/llm_raw/*.json`), and the verdict is
PASS iff every MUST is fuzzy-matched in the trajectory and no FORBIDDEN
appears. This is the offline analogue of Oracle-Informed LLM Judge — the
LLM was the rubric extractor, not the per-episode judge.

Phase 1.D measures, on the W8 corpus:
    - Rubric-aware pass rate
    - Consensus FA against TCC (v4_hard)
    - Matched-pair detection
    - BSR vs TCC

Cross-tabulates with each of the 3 CwT-variant catalogues to assess whether
adding rubric-aware verdicts as a 5th evaluator strengthens or weakens the
consensus FA / matched-pair signal.

Output:
    evidence_pack/phase1d/phase1d_rubric_aware_results.json
    evidence_pack/phase1d/phase1d_rubric_aware_macros.tex
    evidence_pack/phase1d/phase1d_rubric_aware_table.tex

Usage:
    PYTHONPATH=..:. /home/anonymous-org/anaconda3/bin/python3.13 \
        scripts/experiments/phase1d_rubric_aware_judge.py
"""

from __future__ import annotations

from collections import defaultdict
from itertools import combinations
import json
from pathlib import Path
import sys
import time
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

TYPED_VM = ROOT / "evidence_pack" / "verdicts" / "verdict_matrix_v6_typed_phase1.json"
OUTPUT_DIR = ROOT / "evidence_pack" / "phase1d"

DEEPSEEK_MODEL = "deepseek_r1_7b"

CWT_VARIANTS = [
    ("original", "c2_pass", "Original (5-type)"),
    ("four_type", "cwt_typed_4type_pass", "4-type"),
    ("three_type", "cwt_typed_pass", "3-type"),
]


def main() -> int:
    from audit.shims.llm_catalogue_shim import LLMCatalogueShim  # type: ignore[import-not-found]

    t0 = time.time()
    print(f"[{time.strftime('%H:%M:%S')}] Loading typed VM: {TYPED_VM}")
    with open(TYPED_VM) as f:
        vm = json.load(f)
    pe = [ep for ep in vm["per_episode"] if ep.get("model_dir", ep.get("model", "")) != DEEPSEEK_MODEL]
    print(f"  W8 episodes: {len(pe)}")

    shim = LLMCatalogueShim()
    print(f"[{time.strftime('%H:%M:%S')}] Computing rubric-aware verdicts...")
    rubric_pass: list[bool] = []
    n_resolved = 0
    n_unresolved = 0
    for ep in pe:
        eid = ep.get("episode_id", "")
        try:
            v = shim.verdict({"episode_id": eid})
            rubric_pass.append(bool(v))
            n_resolved += 1
        except Exception:
            rubric_pass.append(False)
            n_unresolved += 1
    print(f"  resolved={n_resolved} unresolved={n_unresolved}")

    n = len(pe)
    rubric_pass_rate = round(100 * sum(rubric_pass) / max(n, 1), 2)
    print(f"\n=== Rubric-aware judge (LLMCatalogueShim) ===")
    print(f"  pass rate: {rubric_pass_rate:.2f}% ({sum(rubric_pass)}/{n})")

    # Consensus FA per CwT variant: (rubric ∩ ASC ∩ MAB ∩ CwT) AND v4_hard
    print(f"\n=== Consensus FA — rubric-aware augmented (5-way) ===")
    fa_results: dict[str, dict[str, Any]] = {}
    for var_key, cwt_col, var_disp in CWT_VARIANTS:
        # 4-way (no rubric) baseline
        fa4 = sum(
            1
            for i, ep in enumerate(pe)
            if ep["ac_proxy"] and ep[cwt_col] and ep["mab_proxy"] and ep["dxem"] and ep["v4_hard"]
        )
        # 5-way augmented with rubric
        fa5 = sum(
            1
            for i, ep in enumerate(pe)
            if rubric_pass[i]
            and ep["ac_proxy"]
            and ep[cwt_col]
            and ep["mab_proxy"]
            and ep["dxem"]
            and ep["v4_hard"]
        )
        # 3-way + rubric (drop TOM since it's degenerate)
        fa3r = sum(
            1
            for i, ep in enumerate(pe)
            if rubric_pass[i] and ep["ac_proxy"] and ep[cwt_col] and ep["mab_proxy"] and ep["v4_hard"]
        )
        fa_results[var_key] = {
            "display": var_disp,
            "fa4_no_rubric": fa4,
            "fa4_no_rubric_pct": round(100 * fa4 / max(n, 1), 2),
            "fa5_with_rubric": fa5,
            "fa5_with_rubric_pct": round(100 * fa5 / max(n, 1), 2),
            "fa3plus_rubric": fa3r,
            "fa3plus_rubric_pct": round(100 * fa3r / max(n, 1), 2),
        }
        print(
            f"  {var_disp:<20s}  FA4={fa4} ({fa_results[var_key]['fa4_no_rubric_pct']:.2f}%)  "
            f"+rubric → FA5={fa5} ({fa_results[var_key]['fa5_with_rubric_pct']:.2f}%)"
        )

    # BSR(rubric) vs TCC
    tp = fn = fp = tn = 0
    for i, ep in enumerate(pe):
        pred = rubric_pass[i]
        truth = not ep.get("v4_hard", True)  # TCC pass = no hard violations
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
    if total_pos > 0 and total_neg > 0:
        bsr_rubric = round((fp / total_neg + fn / total_pos) / 2, 4)
    else:
        bsr_rubric = 0.5
    print(f"\nBSR(rubric-aware vs TCC): {bsr_rubric:.4f}")

    # Matched-pair detection for rubric-aware
    groups: dict[tuple[str, int], dict[str, dict[str, bool]]] = defaultdict(dict)
    for i, ep in enumerate(pe):
        sid = ep.get("scenario_id", "")
        ri = ep.get("run_index", 0)
        model = ep.get("model_dir", ep.get("model", ""))
        groups[(sid, ri)][model] = {"rubric": rubric_pass[i], "tcc": not ep.get("v4_hard", True)}
    total_pairs = 0
    rubric_detect = 0
    tcc_detect = 0
    for _, model_v in groups.items():
        models = sorted(model_v.keys())
        for ma, mb in combinations(models, 2):
            total_pairs += 1
            if model_v[ma]["rubric"] != model_v[mb]["rubric"]:
                rubric_detect += 1
            if model_v[ma]["tcc"] != model_v[mb]["tcc"]:
                tcc_detect += 1
    rubric_detect_pct = round(100 * rubric_detect / max(total_pairs, 1), 2)
    tcc_detect_pct = round(100 * tcc_detect / max(total_pairs, 1), 2)
    print(f"\nMatched-pair detection:")
    print(f"  rubric: {rubric_detect_pct:.2f}%  ({rubric_detect}/{total_pairs})")
    print(f"  TCC:    {tcc_detect_pct:.2f}%")

    # Decide if "strong" (FA ≥ 50% per user spec)
    max_fa5 = max(v["fa5_with_rubric_pct"] for v in fa_results.values())
    is_strong = max_fa5 >= 50.0
    print(f"\nStrong-result threshold (FA5 max >= 50%): max FA5 = {max_fa5:.2f}% → {'STRONG' if is_strong else 'NOT-STRONG'}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    summary = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "n_episodes": n,
        "n_resolved": n_resolved,
        "n_unresolved": n_unresolved,
        "rubric_pass_rate_pct": rubric_pass_rate,
        "rubric_pass_count": sum(rubric_pass),
        "bsr_rubric_vs_tcc": bsr_rubric,
        "matched_pair": {
            "total_pairs": total_pairs,
            "rubric_detect_pct": rubric_detect_pct,
            "tcc_detect_pct": tcc_detect_pct,
        },
        "consensus_fa_per_cwt_variant": fa_results,
        "is_strong_result": is_strong,
        "strong_threshold": 50.0,
        "max_fa5_pct": max_fa5,
        "judge_definition": "Rubric = LLM-extracted MUSTs/FORBIDDEN per CPG; verdict PASS if all MUSTs covered (>=0.5) + no FORBIDDEN performed. Source: LLMCatalogueShim.",
    }
    (OUTPUT_DIR / "phase1d_rubric_aware_results.json").write_text(json.dumps(summary, indent=2, default=str) + "\n")

    # Macros
    macro_lines = [
        "% Phase 1.D — Rubric-aware LLM judge (offline via LLMCatalogueShim)",
        f"% Generated: {time.strftime('%Y-%m-%dT%H:%M:%S')}",
        "",
        f"\\providecommand{{\\phaseDRubricPassRate}}{{{rubric_pass_rate}}}",
        f"\\providecommand{{\\phaseDRubricBSR}}{{{bsr_rubric}}}",
        f"\\providecommand{{\\phaseDRubricMatchedPair}}{{{rubric_detect_pct}}}",
        f"\\providecommand{{\\phaseDTCCMatchedPair}}{{{tcc_detect_pct}}}",
        f"\\providecommand{{\\phaseDMaxFAFive}}{{{max_fa5}}}",
        f"\\providecommand{{\\phaseDIsStrong}}{{{str(is_strong).lower()}}}",
    ]
    for var_key, _, _ in CWT_VARIANTS:
        kk = "Orig" if var_key == "original" else ("FourType" if var_key == "four_type" else "ThreeType")
        v = fa_results[var_key]
        macro_lines.append(f"\\providecommand{{\\phaseDFA{kk}NoRubric}}{{{v['fa4_no_rubric_pct']}}}")
        macro_lines.append(f"\\providecommand{{\\phaseDFA{kk}WithRubric}}{{{v['fa5_with_rubric_pct']}}}")
    (OUTPUT_DIR / "phase1d_rubric_aware_macros.tex").write_text("\n".join(macro_lines) + "\n")

    # Table
    table_lines = [
        r"\begin{table}[htbp]",
        r"\centering\small",
        r"\caption{Phase 1.D rubric-aware LLM judge: cross-tabulation of consensus False Accept under each CwT variant. ``+rubric'' adds the LLMCatalogueShim verdict (rubric = LLM-extracted MUSTs/FORBIDDEN) as a 5th evaluator in the consensus.}",
        r"\label{tab:phase1d_rubric_aware}",
        r"\begin{tabular}{lrrr}",
        r"\toprule",
        r"CwT variant & FA4 (no rubric)\% & FA5 (+rubric)\% & $\Delta$ \\",
        r"\midrule",
    ]
    for var_key, _, var_disp in CWT_VARIANTS:
        v = fa_results[var_key]
        delta = v["fa5_with_rubric_pct"] - v["fa4_no_rubric_pct"]
        table_lines.append(f"  {var_disp} & {v['fa4_no_rubric_pct']:.2f} & {v['fa5_with_rubric_pct']:.2f} & {delta:+.2f} \\\\")
    table_lines += [
        r"\bottomrule",
        r"\end{tabular}",
        r"\end{table}",
    ]
    (OUTPUT_DIR / "phase1d_rubric_aware_table.tex").write_text("\n".join(table_lines) + "\n")

    elapsed = time.time() - t0
    print(f"\n[{time.strftime('%H:%M:%S')}] Saved to {OUTPUT_DIR}/")
    print(f"[{time.strftime('%H:%M:%S')}] Done in {elapsed:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
