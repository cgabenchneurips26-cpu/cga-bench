"""Frontier sensitivity: abstention-controlled subset (Option C).

Reads the same v73_frontier episode JSONs as compute_frontier_verdict_matrix.py
and emits a SECOND set of macros for the subset that excludes
``consecutive_empty_actions`` terminations -- matching the v6 quarantine policy
applied uniformly to open-weight Phase A/B nemotron empties.

Why
---
Mid-tier frontier endpoints (sonnet 7.9%, gpt-5.4-mini 29.5%) emit empty action
lists at 60x the rate of the worst v6 open-weight model (oss120b 0.48%). v6
treated such episodes as data-quality contamination (archive + re-extract).
The frontier appendix currently keeps them in the denominator, which (a)
mechanically inflates inverse-scaling because ``consecutive_empty_actions ->
trajectory incomplete -> TCC fail by construction'', and (b) is inconsistent
with how the open-weight runs were reported.

This script does NOT delete or move any data. It produces a parallel macro set
so that Table A.AY-2 / App.~AY can show BOTH denominators side-by-side
(reviewer-proof sensitivity report).

Inputs
------
results/v73_frontier/{claude_opus47,gpt54,claude_sonnet46,gpt54mini}/*.json

Outputs
-------
- evidence_pack/analysis/verdict_matrix_v73_frontier_abstention_controlled.json
- paper/auto_numbers_v73_frontier_abstention.tex
"""

from __future__ import annotations

from collections import Counter
import json
from pathlib import Path
import statistics
import sys

REPO_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO_ROOT.parent))

from cga_bench.assessor_core.spec.verdict_definitions import (
    AC_COVERAGE_THRESHOLD,
    C2_COMPLIANCE_THRESHOLD,
    CWT_TYPED_THRESHOLD,
    MAB_F1_THRESHOLD,
    action_coverage,
    asc_verdict,
    cwt_typed_verdict,
    cwt_verdict,
    mab_f1,
    paf_verdict,
    tcc_verdict,
    tom_verdict,
)

FRONTIER_MODELS = ["claude_opus47", "gpt54", "claude_sonnet46", "gpt54mini"]
RESULTS_DIR = REPO_ROOT / "results" / "v73_frontier"
OUT_MATRIX = REPO_ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v73_frontier_abstention_controlled.json"
OUT_MACROS = REPO_ROOT / "paper" / "auto_numbers_v73_frontier_abstention.tex"

ABSTENTION_TERMINATIONS = {"consecutive_empty_actions"}


def _load_model_episodes(model: str) -> list[dict]:
    files = [
        f for f in (RESULTS_DIR / model).glob("*.json") if "checkpoint" not in f.name and "model_summary" not in f.name
    ]
    eps: list[dict] = []
    for f in files:
        try:
            r = json.load(open(f))
            r["_model"] = model
            r["_file"] = f.name
            eps.append(r)
        except Exception as exc:
            print(f"WARN: skip {f}: {exc}")
    return eps


def _episode_verdicts(ep: dict) -> dict:
    return {
        "scenario_id": ep.get("scenario_id"),
        "model": ep.get("_model"),
        "run_index": ep.get("run_index"),
        "compliance_score": ep.get("compliance_score"),
        "termination_reason": ep.get("termination_reason"),
        "total_tokens": ep.get("total_tokens", 0),
        "total_violations": ep.get("total_violations", 0),
        "tcc_pass": tcc_verdict(ep),
        "cwt_pass": cwt_verdict(ep, threshold=C2_COMPLIANCE_THRESHOLD),
        "cwt_typed_pass": cwt_typed_verdict(ep, threshold=CWT_TYPED_THRESHOLD),
        "asc_pass": asc_verdict(ep, threshold=AC_COVERAGE_THRESHOLD),
        "paf_pass": paf_verdict(ep, threshold=MAB_F1_THRESHOLD),
        "tom_pass": tom_verdict(ep),
        "ac_score": action_coverage(ep),
        "mab_f1": mab_f1(ep),
        "v4_hard": not tcc_verdict(ep),
    }


def _per_model_summary(per_episode: list[dict]) -> dict:
    out: dict[str, dict] = {}
    for m in FRONTIER_MODELS:
        m_eps = [e for e in per_episode if e["model"] == m]
        n = len(m_eps)
        if not n:
            continue
        compl = [e["compliance_score"] for e in m_eps]
        toks = [e["total_tokens"] for e in m_eps]
        viol = [e["total_violations"] for e in m_eps]
        term = Counter(e["termination_reason"] for e in m_eps)
        out[m] = {
            "n": n,
            "compl_mean": round(statistics.mean(compl), 4),
            "compl_std": round(statistics.stdev(compl), 4) if n > 1 else 0,
            "tokens_per_ep": round(statistics.mean(toks), 1),
            "violations_per_ep": round(statistics.mean(viol), 2),
            "tcc_pass_rate": round(sum(1 for e in m_eps if e["tcc_pass"]) / n, 4),
            "cwt_pass_rate": round(sum(1 for e in m_eps if e["cwt_pass"]) / n, 4),
            "cwt_typed_pass_rate": round(sum(1 for e in m_eps if e["cwt_typed_pass"]) / n, 4),
            "asc_pass_rate": round(sum(1 for e in m_eps if e["asc_pass"]) / n, 4),
            "paf_pass_rate": round(sum(1 for e in m_eps if e["paf_pass"]) / n, 4),
            "termination_dist": dict(term.most_common()),
            "consecutive_empty_pct": round(100.0 * term.get("consecutive_empty_actions", 0) / n, 2),
            "n_excluded_empty": term.get("consecutive_empty_actions", 0),
        }
    return out


def _emit_abstention_macros(
    per_model_full: dict,
    per_model_ctrl: dict,
    total_full: int,
    total_ctrl: int,
) -> str:
    lines = [
        "% Auto-generated frontier ABSTENTION-CONTROLLED macros for paper §App AY.",
        "% Subset = all frontier episodes EXCLUDING consecutive_empty_actions terminations,",
        "% matching the v6 open-weight quarantine policy (Phase A/B nemotron empties were",
        "% archived and re-extracted; this subset applies the same policy to frontier).",
        "%",
        "% Pair these with auto_numbers_v73_frontier.tex (full-denominator macros) for",
        "% the side-by-side sensitivity table in App.~AY (Option C reviewer-proof).",
        f"\\providecommand{{\\frontierAbstFullN}}{{{total_full:,}}}",
        f"\\providecommand{{\\frontierAbstCtrlN}}{{{total_ctrl:,}}}",
        f"\\providecommand{{\\frontierAbstExcluded}}{{{total_full - total_ctrl:,}}}",
    ]
    name_map = {
        "claude_opus47": "Opus",
        "gpt54": "GPTfiveFour",
        "claude_sonnet46": "Sonnet",
        "gpt54mini": "GPTfiveFourMini",
    }
    for m in FRONTIER_MODELS:
        prefix = name_map.get(m, m)
        sf = per_model_full.get(m, {})
        sc = per_model_ctrl.get(m, {})
        if not sf or not sc:
            continue
        lines.extend(
            [
                # Sample sizes
                f"\\providecommand{{\\frontier{prefix}NCtrl}}{{{sc['n']:,}}}",
                f"\\providecommand{{\\frontier{prefix}NExcluded}}{{{sf['n_excluded_empty']:,}}}",
                # Compliance (controlled)
                f"\\providecommand{{\\frontier{prefix}ComplMeanCtrl}}{{{sc['compl_mean']:.3f}}}",
                f"\\providecommand{{\\frontier{prefix}ComplStdCtrl}}{{{sc['compl_std']:.3f}}}",
                # Pass rates (controlled)
                f"\\providecommand{{\\frontier{prefix}TCCPassRateCtrl}}{{{100 * sc['tcc_pass_rate']:.1f}}}",
                f"\\providecommand{{\\frontier{prefix}ASCPassRateCtrl}}{{{100 * sc['asc_pass_rate']:.1f}}}",
                f"\\providecommand{{\\frontier{prefix}PAFPassRateCtrl}}{{{100 * sc['paf_pass_rate']:.1f}}}",
                f"\\providecommand{{\\frontier{prefix}CwTPassRateCtrl}}{{{100 * sc['cwt_pass_rate']:.1f}}}",
                f"\\providecommand{{\\frontier{prefix}CwTtypedPassRateCtrl}}{{{100 * sc['cwt_typed_pass_rate']:.1f}}}",
                # Deltas vs full denominator (full - ctrl, signed)
                f"\\providecommand{{\\frontier{prefix}TCCDelta}}{{{100 * (sf['tcc_pass_rate'] - sc['tcc_pass_rate']):+.1f}}}",
                f"\\providecommand{{\\frontier{prefix}CwTDelta}}{{{100 * (sf['cwt_pass_rate'] - sc['cwt_pass_rate']):+.1f}}}",
                f"\\providecommand{{\\frontier{prefix}ComplDelta}}{{{sf['compl_mean'] - sc['compl_mean']:+.3f}}}",
            ]
        )

    # Inverse-scaling effect-size deltas (mid - flagship compliance, controlled vs full)
    sf_o, sc_o = per_model_full.get("claude_opus47"), per_model_ctrl.get("claude_opus47")
    sf_s, sc_s = per_model_full.get("claude_sonnet46"), per_model_ctrl.get("claude_sonnet46")
    sf_g, sc_g = per_model_full.get("gpt54"), per_model_ctrl.get("gpt54")
    sf_gm, sc_gm = per_model_full.get("gpt54mini"), per_model_ctrl.get("gpt54mini")
    if all([sf_o, sc_o, sf_s, sc_s, sf_g, sc_g, sf_gm, sc_gm]):
        # Within-vendor compliance gap (mid - flagship)
        anth_full = sf_s["compl_mean"] - sf_o["compl_mean"]
        anth_ctrl = sc_s["compl_mean"] - sc_o["compl_mean"]
        oai_full = sf_gm["compl_mean"] - sf_g["compl_mean"]
        oai_ctrl = sc_gm["compl_mean"] - sc_g["compl_mean"]
        lines.extend(
            [
                f"\\providecommand{{\\frontierAnthInverseFull}}{{{anth_full:+.3f}}}",
                f"\\providecommand{{\\frontierAnthInverseCtrl}}{{{anth_ctrl:+.3f}}}",
                f"\\providecommand{{\\frontierOAIInverseFull}}{{{oai_full:+.3f}}}",
                f"\\providecommand{{\\frontierOAIInverseCtrl}}{{{oai_ctrl:+.3f}}}",
                # Within-vendor TCC gap (flagship - mid; positive = flagship wins TCC, original direction)
                f"\\providecommand{{\\frontierAnthTCCgapFull}}{{{100 * (sf_o['tcc_pass_rate'] - sf_s['tcc_pass_rate']):+.1f}}}",
                f"\\providecommand{{\\frontierAnthTCCgapCtrl}}{{{100 * (sc_o['tcc_pass_rate'] - sc_s['tcc_pass_rate']):+.1f}}}",
                f"\\providecommand{{\\frontierOAITCCgapFull}}{{{100 * (sf_g['tcc_pass_rate'] - sf_gm['tcc_pass_rate']):+.1f}}}",
                f"\\providecommand{{\\frontierOAITCCgapCtrl}}{{{100 * (sc_g['tcc_pass_rate'] - sc_gm['tcc_pass_rate']):+.1f}}}",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    print(f"Loading frontier episodes from {RESULTS_DIR}")
    per_episode_full: list[dict] = []
    for m in FRONTIER_MODELS:
        eps = _load_model_episodes(m)
        print(f"  {m}: {len(eps)} episodes loaded")
        per_episode_full.extend(eps)

    verdicts_full = [_episode_verdicts(ep) for ep in per_episode_full]
    verdicts_ctrl = [v for v in verdicts_full if v["termination_reason"] not in ABSTENTION_TERMINATIONS]

    print(f"\nFull denominator     : {len(verdicts_full):,} episodes")
    print(
        f"Abstention-controlled: {len(verdicts_ctrl):,} episodes "
        f"({len(verdicts_full) - len(verdicts_ctrl):,} consecutive_empty_actions excluded)"
    )

    pm_full = _per_model_summary(verdicts_full)
    pm_ctrl = _per_model_summary(verdicts_ctrl)

    print("\n=== PER-MODEL SUMMARY (FULL vs ABSTENTION-CONTROLLED) ===")
    print(
        f"{'Model':<18} {'N(full)':>8} {'N(ctrl)':>8} {'TCC f':>7} {'TCC c':>7} "
        f"{'CwT f':>7} {'CwT c':>7} {'Compl f':>8} {'Compl c':>8}"
    )
    for m in FRONTIER_MODELS:
        sf = pm_full.get(m, {})
        sc = pm_ctrl.get(m, {})
        if not sf or not sc:
            continue
        print(
            f"  {m:<16} {sf['n']:>8} {sc['n']:>8} "
            f"{100 * sf['tcc_pass_rate']:>6.1f}% {100 * sc['tcc_pass_rate']:>6.1f}% "
            f"{100 * sf['cwt_pass_rate']:>6.1f}% {100 * sc['cwt_pass_rate']:>6.1f}% "
            f"{sf['compl_mean']:>8.3f} {sc['compl_mean']:>8.3f}"
        )

    # Inverse-scaling check (within-vendor mid - flagship compliance)
    print("\n=== WITHIN-VENDOR COMPLIANCE GAPS (mid - flagship) ===")
    for vendor, fkey, mkey in [
        ("Anthropic", "claude_opus47", "claude_sonnet46"),
        ("OpenAI", "gpt54", "gpt54mini"),
    ]:
        full_gap = pm_full[mkey]["compl_mean"] - pm_full[fkey]["compl_mean"]
        ctrl_gap = pm_ctrl[mkey]["compl_mean"] - pm_ctrl[fkey]["compl_mean"]
        print(f"  {vendor:<10} full={full_gap:+.3f}  ctrl={ctrl_gap:+.3f}  shift={ctrl_gap - full_gap:+.3f}")

    out_obj = {
        "metadata": {
            "corpus": "v73_frontier",
            "policy": "abstention_controlled",
            "excluded_termination_reasons": sorted(ABSTENTION_TERMINATIONS),
            "rationale": (
                "Mirrors v6 open-weight quarantine policy. The Phase A/B nemotron 21-episode "
                "consecutive_empty_actions cluster (0.22%) was archived to "
                "_archive/nemotron_phase_b_empty_20260425/ and re-extracted with "
                "CGA_DEBUG_RAW_RESPONSE=1. Frontier mid-tier endpoints emit such terminations "
                "at 7.9% (sonnet) / 29.5% (gpt-5.4-mini); excluding them yields a denominator "
                "comparable to the v6 reporting convention."
            ),
            "n_full": len(verdicts_full),
            "n_ctrl": len(verdicts_ctrl),
            "n_excluded": len(verdicts_full) - len(verdicts_ctrl),
        },
        "per_model_full": pm_full,
        "per_model_abstention_controlled": pm_ctrl,
    }
    OUT_MATRIX.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_MATRIX, "w") as f:
        json.dump(out_obj, f, indent=2)
    print(f"\nVerdict matrix written: {OUT_MATRIX}")

    macros = _emit_abstention_macros(pm_full, pm_ctrl, total_full=len(verdicts_full), total_ctrl=len(verdicts_ctrl))
    OUT_MACROS.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_MACROS, "w") as f:
        f.write(macros)
    print(f"Paper macros written : {OUT_MACROS}")


if __name__ == "__main__":
    main()
