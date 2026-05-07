#!/usr/bin/env python3
"""Track A v3 main-finding replication — generic LLM-family-parameterized.

Mirrors exp_mainfinding_llm_replication_v2.py but lets the caller point at
any llm_raw_<suffix>/ catalogue (default v3). Re-runs LlmAsc/LlmCwt/LlmPaf
shims against that catalogue and reports the consensus triple-FA inflation
ratio against the CDE anchor (paper anchor = 6.6%).

Used to verify the paper's pillar-3 ratio (5.50x Qwen v1 / 5.60x gpt-oss
v2) on a third (or fourth) LLM family. A ratio in the 5.0-6.0x band
across families would refute reviewer suspicion that the magnitude is a
Qwen+OpenAI coincidence.

Usage
-----
    PYTHONPATH=..:. python scripts/experiments/exp_mainfinding_llm_replication_v3.py \
        --output-suffix v3                 # uses llm_raw_v3/, default

    PYTHONPATH=..:. python scripts/experiments/exp_mainfinding_llm_replication_v3.py \
        --output-suffix v3_llama4 --catalogue-name "Llama-4-Scout"

Outputs
-------
    evidence_pack/constraint_comparison/main_finding_full_replication_<suffix>_results.json
    evidence_pack/constraint_comparison/main_finding_full_replication_<suffix>_macros.tex
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "evidence_pack" / "constraint_comparison"
PAPER_STRICT_FA_THREE_PCT = 6.6
PAPER_FA_ALL_OBLIVIOUS_PCT = 11.6


def _pct(vs: list[bool]) -> float:
    return 100.0 * sum(vs) / len(vs) if vs else 0.0


def _patch_catalogue_dir(suffix: str) -> Path:
    """Monkey-patch llm_catalogue_shim to read llm_raw_<suffix>/."""
    from audit.shims import llm_catalogue_shim as lcs  # type: ignore[import-not-found]

    new_dir = OUT_DIR / f"llm_raw_{suffix}"
    if not new_dir.exists():
        raise SystemExit(
            f"ERROR: catalogue dir does not exist: {new_dir}\n  Run extraction first via exp_cde_vs_llm_v3.py"
        )
    lcs._LLM_CATALOGUE_DIR = new_dir
    lcs._load_catalogue.cache_clear()
    return new_dir


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-suffix", type=str, default="v3", help="Catalogue suffix to read from llm_raw_<suffix>/."
    )
    parser.add_argument(
        "--catalogue-name",
        type=str,
        default=None,
        help="Display name for the catalogue (e.g., 'Llama-4-Scout'); used in summary metadata.",
    )
    parser.add_argument(
        "--n-cpgs-min",
        type=int,
        default=20,
        help="Warn if fewer than this many CPG catalogue files were extracted (default: 20).",
    )
    args = parser.parse_args()

    catalogue_dir = _patch_catalogue_dir(args.output_suffix)

    # Late imports so the monkey-patched module is picked up.
    from audit.shims._verdict_cache import get_verdict, load_w8_episodes  # type: ignore[import-not-found]
    from audit.shims.llm_family_shims import (  # type: ignore[import-not-found]
        LlmAscShim,
        LlmCwtShim,
        LlmPafShim,
    )

    eps = load_w8_episodes()
    eids = sorted(eps.keys())
    n_cpgs = len(list(catalogue_dir.glob("*.json")))
    print(f"Catalogue dir : {catalogue_dir}  ({n_cpgs} CPG files)")
    print(f"Episodes      : {len(eids)}")
    if n_cpgs < args.n_cpgs_min:
        print(f"  WARNING: only {n_cpgs} CPGs extracted (< {args.n_cpgs_min}); ratio may be sparse.")

    asc = LlmAscShim()
    cwt = LlmCwtShim()
    paf = LlmPafShim()
    v_asc = [asc.verdict({"episode_id": e}) for e in eids]
    v_cwt = [cwt.verdict({"episode_id": e}) for e in eids]
    v_paf = [paf.verdict({"episode_id": e}) for e in eids]
    v4 = [get_verdict(e, "v4_hard") for e in eids]

    print(f"  LlmAsc pass : {_pct(v_asc):.2f}%")
    print(f"  LlmCwt pass : {_pct(v_cwt):.2f}%")
    print(f"  LlmPaf pass : {_pct(v_paf):.2f}%")

    triple = [a and b and c for a, b, c in zip(v_asc, v_cwt, v_paf)]
    double = [a and b for a, b in zip(v_asc, v_cwt)]
    hard_count = sum(1 for r in v4 if not r)
    triple_fa_hard = sum(1 for t, r in zip(triple, v4) if t and not r)
    double_fa_hard = sum(1 for t, r in zip(double, v4) if t and not r)

    triple_fa_rate_total = 100.0 * triple_fa_hard / len(eids)
    double_fa_rate_total = 100.0 * double_fa_hard / len(eids)
    ratio_triple = triple_fa_rate_total / PAPER_STRICT_FA_THREE_PCT
    ratio_double = double_fa_rate_total / PAPER_FA_ALL_OBLIVIOUS_PCT

    print(
        f"\n  Triple consensus FA: {triple_fa_hard}/{hard_count} on-hard "
        f"({triple_fa_rate_total:.2f}% of total → {ratio_triple:.2f}× vs 6.6% anchor)"
    )
    print(
        f"  Double consensus FA: {double_fa_hard}/{hard_count} on-hard "
        f"({double_fa_rate_total:.2f}% of total → {ratio_double:.2f}× vs 11.6% anchor)"
    )

    summary = {
        "timestamp": datetime.now(UTC).isoformat(),
        "catalogue_version": args.output_suffix,
        "catalogue_name": args.catalogue_name or args.output_suffix,
        "catalogue_dir": str(catalogue_dir),
        "n_cpgs_extracted": n_cpgs,
        "n_episodes": len(eids),
        "n_cde_hard": hard_count,
        "per_family_pass_rate_pct": {
            "LlmAsc": round(_pct(v_asc), 4),
            "LlmCwt": round(_pct(v_cwt), 4),
            "LlmPaf": round(_pct(v_paf), 4),
        },
        "triple": {
            "pass_count": sum(triple),
            "fa_on_hard_count": triple_fa_hard,
            "fa_rate_on_hard_pct": round(100.0 * triple_fa_hard / hard_count, 4) if hard_count else 0.0,
            "fa_rate_on_total_pct": round(triple_fa_rate_total, 4),
        },
        "double": {
            "pass_count": sum(double),
            "fa_on_hard_count": double_fa_hard,
            "fa_rate_on_hard_pct": round(100.0 * double_fa_hard / hard_count, 4) if hard_count else 0.0,
            "fa_rate_on_total_pct": round(double_fa_rate_total, 4),
        },
        "ratio_vs_paper": {"triple": round(ratio_triple, 4), "double": round(ratio_double, 4)},
        "v1_qwen_anchor": {"triple_fa_total_pct": 36.31, "ratio_triple": 5.50},
        "v2_gptoss_anchor": {"triple_fa_total_pct": 36.95, "ratio_triple": 5.60},
    }
    out_json = OUT_DIR / f"main_finding_full_replication_{args.output_suffix}_results.json"
    out_json.write_text(json.dumps(summary, indent=2) + "\n")

    # Plain LaTeX macro names cannot contain underscores OR digits — `\foo3bar`
    # parses as `\foo` followed by literal `3bar`, breaking `\providecommand`.
    # Convert "v3_qwen4b" -> "VThreeQwenFourB" (matches existing v2 convention,
    # see `\mainReplVTwoRatioTriple` in paper/auto_numbers.tex).
    _DIGIT_NAMES = {
        "0": "Zero",
        "1": "One",
        "2": "Two",
        "3": "Three",
        "4": "Four",
        "5": "Five",
        "6": "Six",
        "7": "Seven",
        "8": "Eight",
        "9": "Nine",
    }
    parts = []
    for p in args.output_suffix.split("_"):
        token = p.capitalize()
        token = "".join(_DIGIT_NAMES.get(c, c) for c in token)
        parts.append(token)
    cap = "".join(parts)
    macros = [
        f"% Auto-generated by exp_mainfinding_llm_replication_v3.py (suffix={args.output_suffix})",
        f"\\providecommand{{\\mainRepl{cap}LlmAscPct}}{{{_pct(v_asc):.2f}}}",
        f"\\providecommand{{\\mainRepl{cap}LlmCwtPct}}{{{_pct(v_cwt):.2f}}}",
        f"\\providecommand{{\\mainRepl{cap}LlmPafPct}}{{{_pct(v_paf):.2f}}}",
        f"\\providecommand{{\\mainRepl{cap}TripleFATotal}}{{{triple_fa_rate_total:.2f}}}",
        f"\\providecommand{{\\mainRepl{cap}DoubleFATotal}}{{{double_fa_rate_total:.2f}}}",
        f"\\providecommand{{\\mainRepl{cap}RatioTriple}}{{{ratio_triple:.2f}}}",
        f"\\providecommand{{\\mainRepl{cap}RatioDouble}}{{{ratio_double:.2f}}}",
    ]
    out_macros = OUT_DIR / f"main_finding_full_replication_{args.output_suffix}_macros.tex"
    out_macros.write_text("\n".join(macros) + "\n")

    print(f"\nSaved: {out_json}")
    print(f"Saved: {out_macros}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
