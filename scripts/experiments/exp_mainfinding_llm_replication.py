#!/usr/bin/env python3
"""Main-finding replication: LLM ASC∩CwT∩PAF strict-FA vs paper CDE 6.6%.

Builds three LLM-catalogue analogues (audit/shims/llm_family_shims.py),
runs them on the 14,826-episode W8 corpus, computes the three-way
consensus intersection, and reports the strict false-accept rate on
CDE-hard episodes (v4_hard=False) to compare against the paper's CDE
strictFAThree = 6.6%.

A catalogue-robust paper headline requires LLM_strictFAThree ≈ CDE_strictFAThree.
Large divergence implies the 6.6% is catalogue-specific.

Usage:
    PYTHONPATH=. python scripts/experiments/exp_mainfinding_llm_replication.py
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

from audit.shims._verdict_cache import get_verdict, load_w8_episodes  # noqa: E402
from audit.shims.llm_family_shims import LlmAscShim, LlmCwtShim, LlmPafShim  # noqa: E402

OUT_DIR = ROOT / "evidence_pack" / "constraint_comparison"

# Paper anchors (from paper/auto_numbers.tex)
PAPER_STRICT_FA_THREE_PCT = 6.6  # ASC∩PAF∩CwT FA rate
PAPER_STRICT_FA_THREE_COUNT = 1118
PAPER_FA_ALL_OBLIVIOUS_PCT = 11.6  # ASC∩CwT


def _triple_consensus(
    v_asc: list[bool], v_cwt: list[bool], v_paf: list[bool]
) -> list[bool]:
    return [a and b and c for a, b, c in zip(v_asc, v_cwt, v_paf)]


def _double_consensus_aset_only(v_asc: list[bool], v_cwt: list[bool]) -> list[bool]:
    return [a and b for a, b in zip(v_asc, v_cwt)]


def main() -> None:
    parser = argparse.ArgumentParser(description="Main-finding LLM replication")
    parser.add_argument("--out-dir", type=str, default=str(OUT_DIR))
    args = parser.parse_args()

    eps = load_w8_episodes()
    eids = sorted(eps.keys())
    print(f"Running 3 LLM shims × {len(eids)} episodes ...")

    asc = LlmAscShim()
    cwt = LlmCwtShim()
    paf = LlmPafShim()
    v_asc = [asc.verdict({"episode_id": e}) for e in eids]
    v_cwt = [cwt.verdict({"episode_id": e}) for e in eids]
    v_paf = [paf.verdict({"episode_id": e}) for e in eids]
    v4 = [get_verdict(e, "v4_hard") for e in eids]

    # Per-family pass rates
    def _pct(vs: list[bool]) -> float:
        return 100.0 * sum(vs) / len(vs)

    print(
        f"  LlmAsc pass        : {_pct(v_asc):.2f}% ({sum(v_asc)}/{len(eids)})"
    )
    print(
        f"  LlmCwt pass        : {_pct(v_cwt):.2f}% ({sum(v_cwt)}/{len(eids)})"
    )
    print(
        f"  LlmPaf pass        : {_pct(v_paf):.2f}% ({sum(v_paf)}/{len(eids)})"
    )
    print(f"  v4_hard (CDE) pass : {_pct(v4):.2f}% ({sum(v4)}/{len(eids)})")

    triple = _triple_consensus(v_asc, v_cwt, v_paf)
    double = _double_consensus_aset_only(v_asc, v_cwt)
    print(
        f"\n  LLM ASC∩CwT∩PAF pass : {_pct(triple):.2f}%  "
        f"({sum(triple)}/{len(eids)})"
    )
    print(
        f"  LLM ASC∩CwT pass     : {_pct(double):.2f}%  "
        f"({sum(double)}/{len(eids)})"
    )

    # Strict-FA on CDE-hard (v4_hard=False)
    hard_count = sum(1 for r in v4 if not r)
    triple_fa_on_hard = sum(1 for t, r in zip(triple, v4) if t and not r)
    double_fa_on_hard = sum(1 for t, r in zip(double, v4) if t and not r)

    triple_fa_rate = 100.0 * triple_fa_on_hard / hard_count if hard_count else 0.0
    double_fa_rate = 100.0 * double_fa_on_hard / hard_count if hard_count else 0.0
    # Also compute FA as fraction of total (matches paper's 1118/16944 ≈ 6.6%)
    triple_fa_rate_total = 100.0 * triple_fa_on_hard / len(eids)
    double_fa_rate_total = 100.0 * double_fa_on_hard / len(eids)

    print(f"\n  CDE-hard subset (v4_hard=False): {hard_count} / {len(eids)}")
    print(
        f"  LLM strictFAThree  (triple ∩ hard): "
        f"{triple_fa_on_hard} / {hard_count} on-hard = {triple_fa_rate:.2f}%  "
        f"({triple_fa_rate_total:.2f}% of total)"
    )
    print(
        f"  LLM faAllOblivious (double ∩ hard): "
        f"{double_fa_on_hard} / {hard_count} on-hard = {double_fa_rate:.2f}%  "
        f"({double_fa_rate_total:.2f}% of total)"
    )

    print("\n  Paper anchors (CDE):")
    print(f"    strictFAThree    = {PAPER_STRICT_FA_THREE_PCT}% ({PAPER_STRICT_FA_THREE_COUNT} eps, 1118/16944)")
    print(f"    faAllOblivious   = {PAPER_FA_ALL_OBLIVIOUS_PCT}% (ASC∩CwT)")

    # Comparison ratios (LLM total% vs paper total%)
    ratio_strict = (
        triple_fa_rate_total / PAPER_STRICT_FA_THREE_PCT
        if PAPER_STRICT_FA_THREE_PCT
        else 0
    )
    ratio_double = (
        double_fa_rate_total / PAPER_FA_ALL_OBLIVIOUS_PCT
        if PAPER_FA_ALL_OBLIVIOUS_PCT
        else 0
    )
    print("\n  Ratio LLM total / paper total:")
    print(f"    triple: {ratio_strict:.2f}×")
    print(f"    double: {ratio_double:.2f}×")

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "n_episodes": len(eids),
        "n_cde_hard": hard_count,
        "per_family_pass_rate_pct": {
            "LlmAsc": round(_pct(v_asc), 4),
            "LlmCwt": round(_pct(v_cwt), 4),
            "LlmPaf": round(_pct(v_paf), 4),
        },
        "triple_consensus": {
            "pass_count": sum(triple),
            "fa_on_hard_count": triple_fa_on_hard,
            "fa_rate_on_hard_pct": round(triple_fa_rate, 4),
            "fa_rate_on_total_pct": round(triple_fa_rate_total, 4),
        },
        "double_consensus": {
            "pass_count": sum(double),
            "fa_on_hard_count": double_fa_on_hard,
            "fa_rate_on_hard_pct": round(double_fa_rate, 4),
            "fa_rate_on_total_pct": round(double_fa_rate_total, 4),
        },
        "paper_anchors": {
            "strict_fa_three_pct": PAPER_STRICT_FA_THREE_PCT,
            "strict_fa_three_count": PAPER_STRICT_FA_THREE_COUNT,
            "fa_all_oblivious_pct": PAPER_FA_ALL_OBLIVIOUS_PCT,
        },
        "ratio_llm_vs_paper": {
            "triple": round(ratio_strict, 4),
            "double": round(ratio_double, 4),
        },
    }
    (out / "main_finding_full_replication_results.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    lines = [
        "% Auto-generated by exp_mainfinding_llm_replication.py",
        f"\\providecommand{{\\mainReplLlmAscPct}}{{{_pct(v_asc):.2f}}}",
        f"\\providecommand{{\\mainReplLlmCwtPct}}{{{_pct(v_cwt):.2f}}}",
        f"\\providecommand{{\\mainReplLlmPafPct}}{{{_pct(v_paf):.2f}}}",
        f"\\providecommand{{\\mainReplLlmTripleFAOnHard}}{{{triple_fa_rate:.2f}}}",
        f"\\providecommand{{\\mainReplLlmTripleFATotal}}{{{triple_fa_rate_total:.2f}}}",
        f"\\providecommand{{\\mainReplLlmDoubleFAOnHard}}{{{double_fa_rate:.2f}}}",
        f"\\providecommand{{\\mainReplLlmDoubleFATotal}}{{{double_fa_rate_total:.2f}}}",
        f"\\providecommand{{\\mainReplCdeTripleFA}}{{{PAPER_STRICT_FA_THREE_PCT}}}",
        f"\\providecommand{{\\mainReplCdeDoubleFA}}{{{PAPER_FA_ALL_OBLIVIOUS_PCT}}}",
        f"\\providecommand{{\\mainReplRatioTriple}}{{{ratio_strict:.2f}}}",
        f"\\providecommand{{\\mainReplRatioDouble}}{{{ratio_double:.2f}}}",
    ]
    (out / "main_finding_full_replication_macros.tex").write_text(
        "\n".join(lines) + "\n"
    )
    print(
        f"\nSaved: {out}/main_finding_full_replication_{{results.json, macros.tex}}"
    )


if __name__ == "__main__":
    main()
