"""Build frontier verdict matrix for V7.3 3-model paper §App Frontier.

Loads 3,762 episode JSONs from results/v73_frontier/{opus47,gpt54,sonnet46}/
and applies the canonical verdict functions from
assessor_core/spec/verdict_definitions.py to produce a per-episode verdict
matrix matching the schema of evidence_pack/analysis/verdict_matrix_v7_3.json.

Outputs:
  - evidence_pack/analysis/verdict_matrix_v73_frontier.json  (full matrix)
  - paper/auto_numbers_v73_frontier.tex                       (paper macros)
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
OUT_MATRIX = REPO_ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v73_frontier.json"
OUT_MACROS = REPO_ROOT / "paper" / "auto_numbers_v73_frontier.tex"


def _load_model_episodes(model: str) -> list[dict]:
    files = [
        f for f in (RESULTS_DIR / model).glob("*.json") if "checkpoint" not in f.name and "model_summary" not in f.name
    ]
    eps = []
    for f in files:
        try:
            r = json.load(open(f))
            r["_model"] = model
            r["_file"] = f.name
            eps.append(r)
        except Exception as e:
            print(f"WARN: skip {f}: {e}")
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
        "ac_proxy": asc_verdict(ep, threshold=AC_COVERAGE_THRESHOLD),
        "mab_proxy": paf_verdict(ep, threshold=MAB_F1_THRESHOLD),
        "c2_pass": cwt_verdict(ep, threshold=C2_COMPLIANCE_THRESHOLD),
        "ac_score": action_coverage(ep),
        "mab_f1": mab_f1(ep),
        "v4_hard": not tcc_verdict(ep),
    }


def _build_verdict_matrix(per_episode: list[dict]) -> list[dict]:
    n = len(per_episode)
    n_v4_hard = sum(1 for e in per_episode if e["v4_hard"])
    n_v4_crit = sum(1 for e in per_episode if e["v4_hard"] and (e.get("compliance_score") or 0) < 0.5)

    def _row(name: str, predicate) -> dict:
        passing = [e for e in per_episode if predicate(e)]
        n_pass = len(passing)
        v4_in_pass = sum(1 for e in passing if e["v4_hard"])
        crit_in_pass = sum(1 for e in passing if e["v4_hard"] and (e.get("compliance_score") or 0) < 0.5)
        return {
            "evaluator": name,
            "n_pass": n_pass,
            "pass_rate": round(n_pass / n, 4) if n else 0.0,
            "v4_hard_in_pass": v4_in_pass,
            "mis_cert_any": round(v4_in_pass / max(n_pass, 1), 4),
            "v4_crit_in_pass": crit_in_pass,
            "mis_cert_crit": round(crit_in_pass / max(n_pass, 1), 4),
        }

    return [
        _row("DxEM", lambda e: e["tom_pass"]),
        _row("AC-Proxy", lambda e: e["asc_pass"]),
        _row("MAB-Proxy", lambda e: e["paf_pass"]),
        _row("C2>=0.7", lambda e: e["cwt_pass"]),
        _row("ACov>=0.5", lambda e: e["asc_pass"]),
        _row("CGA-Bench", lambda e: not e["v4_hard"]),
    ]


def _per_model_summary(per_episode: list[dict]) -> dict:
    out = {}
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
            "compl_min": round(min(compl), 4),
            "compl_max": round(max(compl), 4),
            "tokens_per_ep": round(statistics.mean(toks), 1),
            "tokens_total": sum(toks),
            "violations_per_ep": round(statistics.mean(viol), 2),
            "tcc_pass_rate": round(sum(1 for e in m_eps if e["tcc_pass"]) / n, 4),
            "cwt_pass_rate": round(sum(1 for e in m_eps if e["cwt_pass"]) / n, 4),
            "cwt_typed_pass_rate": round(sum(1 for e in m_eps if e["cwt_typed_pass"]) / n, 4),
            "asc_pass_rate": round(sum(1 for e in m_eps if e["asc_pass"]) / n, 4),
            "paf_pass_rate": round(sum(1 for e in m_eps if e["paf_pass"]) / n, 4),
            "termination_dist": dict(term.most_common()),
            "consecutive_empty_pct": round(100.0 * term.get("consecutive_empty_actions", 0) / n, 2),
        }
    return out


def _emit_macros(per_model: dict, matrix: list[dict], total_n: int) -> str:
    lines = [
        "% Auto-generated frontier macros for paper §App Frontier",
        "% V7.3 corpus, 3 frontier endpoints (Anthropic Opus + Sonnet, OpenAI GPT 5.4)",
        f"\\providecommand{{\\frontierTotalEpisodes}}{{{total_n:,}}}",
        f"\\providecommand{{\\frontierNumModels}}{{{len(per_model)}}}",
    ]
    name_map = {
        "claude_opus47": "Opus",
        "gpt54": "GPTfiveFour",
        "claude_sonnet46": "Sonnet",
        "gpt54mini": "GPTfiveFourMini",
    }
    for m, s in per_model.items():
        prefix = name_map.get(m, m)
        lines.extend(
            [
                f"\\providecommand{{\\frontier{prefix}N}}{{{s['n']:,}}}",
                f"\\providecommand{{\\frontier{prefix}ComplMean}}{{{s['compl_mean']:.3f}}}",
                f"\\providecommand{{\\frontier{prefix}ComplStd}}{{{s['compl_std']:.3f}}}",
                f"\\providecommand{{\\frontier{prefix}TokensPerEp}}{{{int(s['tokens_per_ep']):,}}}",
                f"\\providecommand{{\\frontier{prefix}TCCPassRate}}{{{100 * s['tcc_pass_rate']:.1f}}}",
                f"\\providecommand{{\\frontier{prefix}ASCPassRate}}{{{100 * s['asc_pass_rate']:.1f}}}",
                f"\\providecommand{{\\frontier{prefix}PAFPassRate}}{{{100 * s['paf_pass_rate']:.1f}}}",
                f"\\providecommand{{\\frontier{prefix}CwTPassRate}}{{{100 * s['cwt_pass_rate']:.1f}}}",
                f"\\providecommand{{\\frontier{prefix}EmptyPct}}{{{s['consecutive_empty_pct']:.1f}}}",
            ]
        )
    return "\n".join(lines) + "\n"


def main() -> None:
    print(f"Loading frontier episodes from {RESULTS_DIR}")
    per_episode_full = []
    for m in FRONTIER_MODELS:
        eps = _load_model_episodes(m)
        print(f"  {m}: {len(eps)} episodes")
        per_episode_full.extend(eps)

    per_episode = [_episode_verdicts(ep) for ep in per_episode_full]
    print(f"\nTotal episodes: {len(per_episode)}")

    matrix = _build_verdict_matrix(per_episode)
    per_model = _per_model_summary(per_episode)

    print("\n=== VERDICT MATRIX (V7.3 frontier 3-model) ===")
    print(f"{'Evaluator':<12} {'N_pass':>8} {'Pass%':>8} {'v4_hard':>9} {'Mis-cert':>9}")
    for row in matrix:
        print(
            f"{row['evaluator']:<12} {row['n_pass']:>8} "
            f"{100 * row['pass_rate']:>7.1f}% {row['v4_hard_in_pass']:>9} "
            f"{100 * row['mis_cert_any']:>8.1f}%"
        )

    print("\n=== PER-MODEL ===")
    for m, s in per_model.items():
        print(
            f"  {m:<18} n={s['n']} compl={s['compl_mean']:.3f}±{s['compl_std']:.3f} "
            f"tok/ep={int(s['tokens_per_ep']):,} empty%={s['consecutive_empty_pct']:.1f}"
        )

    out_obj = {
        "metadata": {
            "corpus": "v73_frontier",
            "n_episodes": len(per_episode),
            "n_models": len(per_model),
            "models": {m: s["n"] for m, s in per_model.items()},
            "n_v4_hard": sum(1 for e in per_episode if e["v4_hard"]),
            "n_v4_crit": sum(1 for e in per_episode if e["v4_hard"] and (e.get("compliance_score") or 0) < 0.5),
            "evaluator_thresholds": {
                "AC_coverage": AC_COVERAGE_THRESHOLD,
                "MAB_F1": MAB_F1_THRESHOLD,
                "C2": C2_COMPLIANCE_THRESHOLD,
                "CwT_typed": CWT_TYPED_THRESHOLD,
            },
        },
        "verdict_matrix": matrix,
        "per_model": per_model,
        "per_episode": per_episode,
    }

    OUT_MATRIX.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_MATRIX, "w") as f:
        json.dump(out_obj, f, indent=2)
    print(f"\nVerdict matrix written: {OUT_MATRIX}")

    macros = _emit_macros(per_model, matrix, len(per_episode))
    OUT_MACROS.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_MACROS, "w") as f:
        f.write(macros)
    print(f"Paper macros written: {OUT_MACROS}")


if __name__ == "__main__":
    main()
