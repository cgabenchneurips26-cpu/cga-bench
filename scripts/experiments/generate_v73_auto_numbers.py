#!/usr/bin/env python3
"""Generate auto_numbers_v7_3.tex from SGSC v7.3 episode JSONs.

Pool: SGSC v7.3 (9 models, 418 scenarios, 49 graphs, 3 runs)
Source: results/v73_full/{model}/*.json (post-CAV, canonical)

Computes macros from raw episode data:
  - Core counts (episodes, models, scenarios, graphs)
  - Per-model CGA / sub-scores / violation distributions
  - Aggregate violation rates by type
  - Termination reason distribution
  - Token usage statistics
  - Per-graph CGA breakdown

Output:
  paper/auto_numbers_v7_3.tex
  evidence_pack/analysis/v7_3_macros.json   (raw computed values)

Usage:
  PYTHONPATH=. python scripts/experiments/generate_v73_auto_numbers.py
"""

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

UTC = timezone.utc
import json
from pathlib import Path
import re
import statistics

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results" / "v73_full"
PAPER_TEX = ROOT / "paper" / "auto_numbers_v73_full.tex"
EVIDENCE_JSON = ROOT / "evidence_pack" / "analysis" / "v7_3_macros.json"
VERDICT_MATRIX = ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v7_3.json"

CANONICAL_MODELS = [
    "deepseek_r1_7b",
    "gemma31b",
    "llama4scout",
    "nemotron30b",
    "oss120b",
    "qwen27b",
    "qwen35b",
    "qwen397b",
    "qwen4b",
]

MODEL_LATEX_KEY = {
    "deepseek_r1_7b": "DS",
    "gemma31b": "Gemma",
    "llama4scout": "Llama",
    "nemotron30b": "Nemo",
    "oss120b": "OSS",
    "qwen27b": "Qtwentyseven",
    "qwen35b": "Qthirtyfive",
    "qwen397b": "Qthreenine",
    "qwen4b": "Qfour",
}

PASS_THRESHOLD_CGA = 0.5
FNAME_RE = re.compile(r"^(.+?)_([a-z0-9_]+?)_r(\d+)_\d{8}_\d{6}\.json$")


def fmt_int(n: int) -> str:
    return f"{n:,}".replace(",", "{,}")


def fmt_pct(x: float, prec: int = 1) -> str:
    return f"{x * 100:.{prec}f}"


def fmt_float(x: float, prec: int = 4) -> str:
    return f"{x:.{prec}f}"


def load_episodes(model_dir: Path, model_key: str, original_key: str) -> list[dict]:
    """Load valid v7.3 episodes for a model, deduped by (scenario_id, run_index).

    For duplicate (scenario, run) pairs, keep the LATEST timestamp file.
    Filter by corpus="sgsc_v73" and skip checkpoint/summary/claim files.
    """
    by_key: dict[tuple[str, int], tuple[str, dict, Path]] = {}
    for f in model_dir.glob("*.json"):
        name = f.name
        if name.startswith(("checkpoint", "model_summary", ".claim")):
            continue
        m = FNAME_RE.match(name)
        if not m:
            continue
        try:
            d = json.loads(f.read_text())
        except Exception:
            continue
        if d.get("corpus") != "sgsc_v73":
            continue
        sid = d.get("scenario_id", "")
        ridx = d.get("run_index", -1)
        ts = d.get("timestamp", "")
        key = (sid, ridx)
        # Keep latest timestamp per (scen, run)
        if key not in by_key or ts > by_key[key][0]:
            by_key[key] = (ts, d, f)
    return [v[1] for v in by_key.values()]


SGSC_YAML_DIR = ROOT / "configs" / "scenarios" / "sgsc"

_SCEN_TO_GRAPH_CACHE: dict[str, str] | None = None


def _load_scen_to_graph_map() -> dict[str, str]:
    """Build mapping scenario_id -> graph_name (yaml file stem without _scenarios)."""
    global _SCEN_TO_GRAPH_CACHE
    if _SCEN_TO_GRAPH_CACHE is not None:
        return _SCEN_TO_GRAPH_CACHE
    import yaml

    mapping: dict[str, str] = {}
    for y in sorted(SGSC_YAML_DIR.glob("*.yaml")):
        graph_name = y.stem
        if graph_name.endswith("_scenarios"):
            graph_name = graph_name[: -len("_scenarios")]
        try:
            data = yaml.safe_load(y.read_text())
        except Exception:
            continue
        scens = data if isinstance(data, list) else (data.get("scenarios") or [])
        if isinstance(scens, dict):
            scens = list(scens.values())
        for sc in scens:
            if isinstance(sc, dict):
                sid = sc.get("id") or sc.get("scenario_id")
                if sid:
                    mapping[sid] = graph_name
    _SCEN_TO_GRAPH_CACHE = mapping
    return mapping


def graph_id_from_scenario(scenario_id: str) -> str:
    """Resolve scenario_id -> graph name via YAML mapping."""
    return _load_scen_to_graph_map().get(scenario_id, "UNKNOWN")


def compute_per_model(eps: list[dict]) -> dict:
    """Aggregate metrics for one model's episodes."""
    n = len(eps)
    if n == 0:
        return {"n": 0}
    cga = [e.get("compliance_score", 0.0) for e in eps]
    peak = [e.get("peak_risk", 0.0) for e in eps]
    aggr = [e.get("aggregate_risk", 0.0) for e in eps]
    tv = [e.get("total_violations", 0) for e in eps]
    tokens = [e.get("total_tokens", 0) for e in eps]
    llm_calls = [e.get("total_llm_calls", 0) for e in eps]
    duration = [e.get("total_duration_minutes", 0.0) for e in eps]
    actions_count = [e.get("actions_count", 0) for e in eps]

    # Violation type distribution
    vt_total = defaultdict(int)
    for e in eps:
        for vt, count in (e.get("violations_by_type") or {}).items():
            vt_total[vt.lower()] += count

    # Sub-scores C1-C5 (episode JSON keys: C1_path_selection, C2_mandatory_completion, etc.)
    sub_key_map = {
        "C1": "C1_path_selection",
        "C2": "C2_mandatory_completion",
        "C3": "C3_forbidden_avoidance",
        "C4": "C4_timing_compliance",
        "C5": "C5_sequence_integrity",
    }
    sub_means = {}
    for short_k, full_k in sub_key_map.items():
        vals = [
            (e.get("sub_scores") or {}).get(full_k, 0.0)
            for e in eps
            if (e.get("sub_scores") or {}).get(full_k) is not None
        ]
        sub_means[short_k] = statistics.mean(vals) if vals else 0.0

    # Termination reason distribution
    term_dist = defaultdict(int)
    for e in eps:
        term_dist[e.get("termination_reason", "unknown")] += 1

    # CGA pass rate (>= threshold)
    n_pass_cga = sum(1 for c in cga if c >= PASS_THRESHOLD_CGA)

    # Empty/timeout count
    n_empty = sum(
        1 for e in eps if e.get("termination_reason") == "consecutive_empty_actions"
    )
    n_timeout = sum(1 for e in eps if e.get("termination_reason") == "timeout")

    # Forbidden commission count (subset of total violations)
    n_forbidden_commission = vt_total.get("commission", 0)

    return {
        "n": n,
        "cga_mean": statistics.mean(cga),
        "cga_median": statistics.median(cga),
        "cga_stdev": statistics.stdev(cga) if n > 1 else 0.0,
        "peak_mean": statistics.mean(peak),
        "aggregate_mean": statistics.mean(aggr),
        "violations_mean": statistics.mean(tv),
        "violations_total": sum(tv),
        "violations_by_type": dict(vt_total),
        "sub_means": sub_means,
        "tokens_mean": statistics.mean(tokens),
        "tokens_total": sum(tokens),
        "llm_calls_mean": statistics.mean(llm_calls),
        "duration_mean": statistics.mean(duration),
        "actions_count_mean": statistics.mean(actions_count),
        "termination_dist": dict(term_dist),
        "pass_cga_count": n_pass_cga,
        "pass_cga_rate": n_pass_cga / n,
        "empty_count": n_empty,
        "timeout_count": n_timeout,
        "forbidden_commission_count": n_forbidden_commission,
    }


def compute_per_graph(all_eps: dict[str, list[dict]]) -> dict:
    """Aggregate CGA per graph across all models."""
    graph_stats: dict[str, list[float]] = defaultdict(list)
    for model_key, eps in all_eps.items():
        for e in eps:
            sid = e.get("scenario_id", "")
            gid = graph_id_from_scenario(sid)
            graph_stats[gid].append(e.get("compliance_score", 0.0))
    return {
        gid: {
            "n": len(scores),
            "cga_mean": statistics.mean(scores) if scores else 0.0,
            "cga_stdev": statistics.stdev(scores) if len(scores) > 1 else 0.0,
        }
        for gid, scores in graph_stats.items()
    }


def aggregate_global(per_model: dict[str, dict]) -> dict:
    """Compute aggregate metrics across all models."""
    total_eps = sum(m["n"] for m in per_model.values())
    if total_eps == 0:
        return {}
    weighted_cga = (
        sum(m["cga_mean"] * m["n"] for m in per_model.values()) / total_eps
    )
    pass_total = sum(m["pass_cga_count"] for m in per_model.values())
    violations_total = sum(m["violations_total"] for m in per_model.values())
    tokens_total = sum(m["tokens_total"] for m in per_model.values())

    vt_global = defaultdict(int)
    for m in per_model.values():
        for vt, c in m["violations_by_type"].items():
            vt_global[vt] += c

    return {
        "total_episodes": total_eps,
        "weighted_cga_mean": weighted_cga,
        "pass_cga_total": pass_total,
        "pass_cga_rate": pass_total / total_eps,
        "violations_total": violations_total,
        "violations_by_type": dict(vt_global),
        "tokens_total": tokens_total,
    }


def load_verdict_matrix() -> dict | None:
    if not VERDICT_MATRIX.is_file():
        return None
    return json.loads(VERDICT_MATRIX.read_text())


def compute_phase2_macros(vm: dict) -> dict:
    """Compute Phase 2 macros from verdict matrix episode-level records."""
    pe = vm.get("per_episode", [])
    n = len(pe)
    if n == 0:
        return {}

    # Aggregate evaluator pass counts
    n_dxem = sum(1 for ep in pe if ep["dxem"])
    n_ac = sum(1 for ep in pe if ep["ac_proxy"])
    n_mab = sum(1 for ep in pe if ep["mab_proxy"])
    n_c2 = sum(1 for ep in pe if ep["c2_pass"])
    n_acov = sum(1 for ep in pe if ep["acov_pass"])
    n_cga = sum(1 for ep in pe if not ep["v4_hard"])
    n_v4_hard = sum(1 for ep in pe if ep["v4_hard"])
    n_v4_crit = sum(1 for ep in pe if ep["v4_crit"])

    # BSR: P(v4_hard | eval=pass)
    def bsr(passes: list[dict]) -> float:
        if not passes:
            return 0.0
        return sum(1 for p in passes if p["v4_hard"]) / len(passes)

    bsr_dxem = bsr([ep for ep in pe if ep["dxem"]])
    bsr_ac = bsr([ep for ep in pe if ep["ac_proxy"]])
    bsr_mab = bsr([ep for ep in pe if ep["mab_proxy"]])
    bsr_c2 = bsr([ep for ep in pe if ep["c2_pass"]])
    bsr_acov = bsr([ep for ep in pe if ep["acov_pass"]])

    # Consensus FA (3-way: AC + MAB + C2 pass, TCC fail)
    fa_3way = sum(
        1 for ep in pe if ep["ac_proxy"] and ep["mab_proxy"] and ep["c2_pass"] and ep["v4_hard"]
    )
    # 4-way: + DxEM
    fa_4way = sum(
        1
        for ep in pe
        if ep["dxem"] and ep["ac_proxy"] and ep["mab_proxy"] and ep["c2_pass"] and ep["v4_hard"]
    )
    # Critical FA: 3-way pass + v4_crit
    fa_crit_3way = sum(
        1 for ep in pe if ep["ac_proxy"] and ep["mab_proxy"] and ep["c2_pass"] and ep["v4_crit"]
    )

    # Verdict flip: any evaluator pass but TCC fail = v4_hard
    flip_count = sum(
        1
        for ep in pe
        if (ep["ac_proxy"] or ep["mab_proxy"] or ep["c2_pass"] or ep["dxem"]) and ep["v4_hard"]
    )

    # Per-model verdict pass rates
    per_model_v: dict[str, dict] = {}
    for model in {ep["model_dir"] for ep in pe}:
        m_recs = [ep for ep in pe if ep["model_dir"] == model]
        m_n = len(m_recs)
        if m_n == 0:
            continue
        per_model_v[model] = {
            "n": m_n,
            "ac_pass": sum(1 for r in m_recs if r["ac_proxy"]),
            "mab_pass": sum(1 for r in m_recs if r["mab_proxy"]),
            "c2_pass": sum(1 for r in m_recs if r["c2_pass"]),
            "acov_pass": sum(1 for r in m_recs if r["acov_pass"]),
            "v4_hard": sum(1 for r in m_recs if r["v4_hard"]),
            "v4_crit": sum(1 for r in m_recs if r["v4_crit"]),
            "ac_pass_rate": sum(1 for r in m_recs if r["ac_proxy"]) / m_n,
            "mab_pass_rate": sum(1 for r in m_recs if r["mab_proxy"]) / m_n,
            "c2_pass_rate": sum(1 for r in m_recs if r["c2_pass"]) / m_n,
            "acov_pass_rate": sum(1 for r in m_recs if r["acov_pass"]) / m_n,
            "v4_hard_rate": sum(1 for r in m_recs if r["v4_hard"]) / m_n,
            "v4_crit_rate": sum(1 for r in m_recs if r["v4_crit"]) / m_n,
            "cga_pass_rate": sum(1 for r in m_recs if not r["v4_hard"]) / m_n,
        }

    # η² (eta squared) — variance decomposition over (AC, MAB, C2, CGA) verdicts
    try:
        import numpy as np

        rows = [
            (
                int(ep["ac_proxy"]),
                int(ep["mab_proxy"]),
                int(ep["c2_pass"]),
                int(not ep["v4_hard"]),
            )
            for ep in pe
        ]
        mat = np.array(rows, dtype=float)
        n_ep, k = mat.shape
        gm = float(mat.mean())
        em = mat.mean(axis=0)
        ss_eval = n_ep * float(np.sum((em - gm) ** 2))
        ss_total = float(np.sum((mat - gm) ** 2))
        eta_eval = ss_eval / ss_total if ss_total > 0 else 0.0

        # η²(run) for cga_pass dimension only, grouped by (scenario, model)
        cga_arr = mat[:, 3]
        groups: dict[tuple[str, str], list[float]] = defaultdict(list)
        for i, ep in enumerate(pe):
            groups[(ep["scenario_id"], ep["model_dir"])].append(float(cga_arr[i]))
        gm_run = float(cga_arr.mean())
        ss_total_run = float(np.sum((cga_arr - gm_run) ** 2))
        ss_within_run = sum(
            sum((v - sum(g) / len(g)) ** 2 for v in g) for g in groups.values() if g
        )
        eta_run = (
            (ss_total_run - ss_within_run) / ss_total_run if ss_total_run > 0 else 0.0
        )
    except Exception:
        eta_eval = 0.0
        eta_run = 0.0

    # Kendall W (model ranking consistency over scenarios for CGA pass)
    try:
        import numpy as np
        from collections import defaultdict as dd

        models_sorted = sorted({ep["model_dir"] for ep in pe})
        m_n = len(models_sorted)
        # Build scenario -> {model: cga_pass_avg}
        sm: dict[str, dict[str, float]] = dd(lambda: dd(list))
        for ep in pe:
            sm[ep["scenario_id"]][ep["model_dir"]].append(int(not ep["v4_hard"]))
        scenarios_sorted = sorted(sm.keys())
        # Average across runs
        sm_avg = {
            s: {m: sum(v) / len(v) for m, v in mm.items() if v} for s, mm in sm.items()
        }
        # Build rank matrix: rows=scenarios, cols=models
        rmat = []
        for s in scenarios_sorted:
            scores = [sm_avg[s].get(m, 0.0) for m in models_sorted]
            # rank ascending (higher score = lower rank index for ties handle simply)
            order = sorted(range(m_n), key=lambda i: scores[i])
            ranks = [0.0] * m_n
            for rk, i in enumerate(order):
                ranks[i] = rk + 1
            rmat.append(ranks)
        rmat = np.array(rmat)
        # Sum of ranks per model
        Rj = rmat.sum(axis=0)
        Rmean = Rj.mean()
        S = float(np.sum((Rj - Rmean) ** 2))
        n_s = len(scenarios_sorted)
        # Kendall W: m = judges (scenarios = n_s), n = items (models = m_n)
        # W = 12 * S / (m^2 * (n^3 - n))
        kw = (12 * S) / (n_s * n_s * (m_n ** 3 - m_n)) if m_n > 1 and n_s > 0 else 0.0
    except Exception:
        kw = 0.0

    return {
        "n": n,
        "n_dxem": n_dxem,
        "n_ac": n_ac,
        "n_mab": n_mab,
        "n_c2": n_c2,
        "n_acov": n_acov,
        "n_cga": n_cga,
        "n_v4_hard": n_v4_hard,
        "n_v4_crit": n_v4_crit,
        "rate_dxem": n_dxem / n,
        "rate_ac": n_ac / n,
        "rate_mab": n_mab / n,
        "rate_c2": n_c2 / n,
        "rate_acov": n_acov / n,
        "rate_cga": n_cga / n,
        "rate_v4_hard": n_v4_hard / n,
        "rate_v4_crit": n_v4_crit / n,
        "bsr_dxem": bsr_dxem,
        "bsr_ac": bsr_ac,
        "bsr_mab": bsr_mab,
        "bsr_c2": bsr_c2,
        "bsr_acov": bsr_acov,
        "fa_3way": fa_3way,
        "fa_4way": fa_4way,
        "fa_crit_3way": fa_crit_3way,
        "fa_3way_rate": fa_3way / n,
        "flip_count": flip_count,
        "flip_rate": flip_count / n,
        "eta_eval": eta_eval,
        "eta_run": eta_run,
        "kendall_w": kw,
        "per_model": per_model_v,
    }


def write_tex(per_model: dict, glob: dict, per_graph: dict, output: Path, p2: dict | None = None) -> None:
    lines: list[str] = []
    lines.append("% Auto-generated by generate_v73_auto_numbers.py")
    lines.append(
        f"% Pool: SGSC v7.3 (9 models, 418 scenarios, 49 graphs, 3 runs) | "
        f"Generated: {datetime.now(UTC).strftime('%Y-%m-%d %H:%M UTC')}"
    )
    lines.append(
        f"% Episodes: {glob['total_episodes']} | Models: {len(per_model)} | "
        "Source: results/v73_full/ (post-CAV canonical)"
    )
    lines.append("")

    lines.append("% --- SGSC v7.3: Core Counts ---")
    lines.append(
        f"\\providecommand{{\\vSevenThreeNEpisodes}}{{{fmt_int(glob['total_episodes'])}}}"
    )
    lines.append("\\providecommand{\\vSevenThreeNModels}{9}")
    lines.append("\\providecommand{\\vSevenThreeNScenarios}{418}")
    lines.append("\\providecommand{\\vSevenThreeNGraphs}{49}")
    lines.append("\\providecommand{\\vSevenThreeNRuns}{3}")
    lines.append("")

    lines.append("% --- SGSC v7.3: Aggregate CGA & Pass Rate ---")
    lines.append(
        f"\\providecommand{{\\vSevenThreeMeanCGA}}{{{fmt_float(glob['weighted_cga_mean'], 4)}}}"
    )
    lines.append(
        f"\\providecommand{{\\vSevenThreePassCGA}}{{{fmt_pct(glob['pass_cga_rate'], 1)}}}  "
        f"% {glob['pass_cga_total']}/{glob['total_episodes']} (compliance >= 0.5)"
    )
    lines.append("")

    lines.append("% --- SGSC v7.3: Aggregate Violations by Type ---")
    vt = glob["violations_by_type"]
    total_violations = glob["violations_total"]
    lines.append(
        f"\\providecommand{{\\vSevenThreeViolTotal}}{{{fmt_int(total_violations)}}}"
    )
    for vt_name in ("omission", "commission", "timing", "sequence", "deviation"):
        c = vt.get(vt_name, 0)
        pct = (c / total_violations * 100) if total_violations else 0.0
        cap = vt_name.capitalize()
        lines.append(
            f"\\providecommand{{\\vSevenThreeViol{cap}}}{{{fmt_int(c)}}}  % {pct:.2f}% of all violations"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeViol{cap}Pct}}{{{pct:.2f}}}"
        )
    lines.append("")

    lines.append("% --- SGSC v7.3: Per-Model Counts ---")
    for mk in CANONICAL_MODELS:
        if mk not in per_model:
            continue
        latex_key = MODEL_LATEX_KEY[mk]
        m = per_model[mk]
        lines.append(
            f"\\providecommand{{\\vSevenThreeN{latex_key}}}{{{fmt_int(m['n'])}}}  % {mk}"
        )
    lines.append("")

    lines.append("% --- SGSC v7.3: Per-Model CGA Mean ---")
    for mk in CANONICAL_MODELS:
        if mk not in per_model:
            continue
        latex_key = MODEL_LATEX_KEY[mk]
        m = per_model[mk]
        lines.append(
            f"\\providecommand{{\\vSevenThreeCGA{latex_key}}}{{{fmt_float(m['cga_mean'], 4)}}}  % {mk}"
        )
    lines.append("")

    lines.append("% --- SGSC v7.3: Per-Model CGA Pass Rate (>= 0.5) ---")
    for mk in CANONICAL_MODELS:
        if mk not in per_model:
            continue
        latex_key = MODEL_LATEX_KEY[mk]
        m = per_model[mk]
        lines.append(
            f"\\providecommand{{\\vSevenThreePassCGA{latex_key}}}{{{fmt_pct(m['pass_cga_rate'], 1)}}}"
            f"  % {m['pass_cga_count']}/{m['n']}"
        )
    lines.append("")

    lines.append("% --- SGSC v7.3: Per-Model Sub-scores (C1-C5 means) ---")
    for k in ("C1", "C2", "C3", "C4", "C5"):
        for mk in CANONICAL_MODELS:
            if mk not in per_model:
                continue
            latex_key = MODEL_LATEX_KEY[mk]
            m = per_model[mk]
            v = m["sub_means"].get(k, 0.0)
            lines.append(
                f"\\providecommand{{\\vSevenThree{k}{latex_key}}}{{{fmt_float(v, 4)}}}"
            )
        lines.append("")

    lines.append("% --- SGSC v7.3: Per-Model Violations Mean ---")
    for mk in CANONICAL_MODELS:
        if mk not in per_model:
            continue
        latex_key = MODEL_LATEX_KEY[mk]
        m = per_model[mk]
        lines.append(
            f"\\providecommand{{\\vSevenThreeViolMean{latex_key}}}{{{fmt_float(m['violations_mean'], 2)}}}"
        )
    lines.append("")

    lines.append("% --- SGSC v7.3: Per-Model Token Usage ---")
    for mk in CANONICAL_MODELS:
        if mk not in per_model:
            continue
        latex_key = MODEL_LATEX_KEY[mk]
        m = per_model[mk]
        lines.append(
            f"\\providecommand{{\\vSevenThreeTokensMean{latex_key}}}{{{fmt_int(int(m['tokens_mean']))}}}"
        )
    lines.append("")

    lines.append("% --- SGSC v7.3: Per-Model Termination Distribution ---")
    for mk in CANONICAL_MODELS:
        if mk not in per_model:
            continue
        latex_key = MODEL_LATEX_KEY[mk]
        m = per_model[mk]
        empty_pct = (m["empty_count"] / m["n"] * 100) if m["n"] else 0.0
        timeout_pct = (m["timeout_count"] / m["n"] * 100) if m["n"] else 0.0
        lines.append(
            f"\\providecommand{{\\vSevenThreeEmptyPct{latex_key}}}{{{empty_pct:.2f}}}"
            f"  % consecutive_empty_actions"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeTimeoutPct{latex_key}}}{{{timeout_pct:.2f}}}"
        )
    lines.append("")

    lines.append("% --- SGSC v7.3: Per-Model Forbidden Commission Count ---")
    for mk in CANONICAL_MODELS:
        if mk not in per_model:
            continue
        latex_key = MODEL_LATEX_KEY[mk]
        m = per_model[mk]
        lines.append(
            f"\\providecommand{{\\vSevenThreeForbidden{latex_key}}}{{{fmt_int(m['forbidden_commission_count'])}}}"
        )
    lines.append("")

    lines.append("% --- SGSC v7.3: Top/Bottom Models by CGA ---")
    sorted_by_cga = sorted(
        [(mk, m["cga_mean"]) for mk, m in per_model.items()],
        key=lambda x: -x[1],
    )
    if sorted_by_cga:
        top_mk, top_cga = sorted_by_cga[0]
        bot_mk, bot_cga = sorted_by_cga[-1]
        lines.append(
            f"\\providecommand{{\\vSevenThreeTopCGAModel}}{{{MODEL_LATEX_KEY[top_mk]}}}  % {top_mk}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeTopCGAValue}}{{{fmt_float(top_cga, 4)}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeBotCGAModel}}{{{MODEL_LATEX_KEY[bot_mk]}}}  % {bot_mk}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeBotCGAValue}}{{{fmt_float(bot_cga, 4)}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeCGASpread}}{{{fmt_float(top_cga - bot_cga, 4)}}}"
        )
    lines.append("")

    lines.append("% --- SGSC v7.3: Per-Graph CGA Summary ---")
    lines.append(f"\\providecommand{{\\vSevenThreeNGraphsObserved}}{{{len(per_graph)}}}")
    if per_graph:
        graph_means = [g["cga_mean"] for g in per_graph.values()]
        lines.append(
            f"\\providecommand{{\\vSevenThreeGraphCGAMin}}{{{fmt_float(min(graph_means), 4)}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeGraphCGAMax}}{{{fmt_float(max(graph_means), 4)}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeGraphCGAMean}}{{{fmt_float(statistics.mean(graph_means), 4)}}}"
        )
    lines.append("")

    # === Phase 2: verdict-matrix-derived macros ===
    if p2:
        lines.append("% =========================================================")
        lines.append("% SGSC v7.3 — Phase 2 (verdict matrix derived)")
        lines.append("% Source: evidence_pack/analysis/verdict_matrix_v7_3.json")
        lines.append("% Thresholds: AC>=0.5, MAB-F1>=0.5, C2>=0.7, ACov>=0.5, TCC=hard violation absent")
        lines.append("% =========================================================")
        lines.append("")

        lines.append("% --- v7.3 Phase 2: Hard Violation Counts ---")
        lines.append(
            f"\\providecommand{{\\vSevenThreeNHard}}{{{fmt_int(p2['n_v4_hard'])}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeHardRate}}{{{fmt_pct(p2['rate_v4_hard'], 1)}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeNCrit}}{{{fmt_int(p2['n_v4_crit'])}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeCritRate}}{{{fmt_pct(p2['rate_v4_crit'], 2)}}}"
        )
        lines.append("")

        lines.append("% --- v7.3 Phase 2: Aggregate Evaluator Pass Rates ---")
        lines.append(
            f"\\providecommand{{\\vSevenThreePassDxEM}}{{{fmt_pct(p2['rate_dxem'], 1)}}}"
            f"  % {p2['n_dxem']}/{p2['n']}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreePassAC}}{{{fmt_pct(p2['rate_ac'], 1)}}}"
            f"  % {p2['n_ac']}/{p2['n']}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreePassMAB}}{{{fmt_pct(p2['rate_mab'], 1)}}}"
            f"  % {p2['n_mab']}/{p2['n']}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreePassCTwo}}{{{fmt_pct(p2['rate_c2'], 1)}}}"
            f"  % {p2['n_c2']}/{p2['n']}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreePassACov}}{{{fmt_pct(p2['rate_acov'], 1)}}}"
            f"  % {p2['n_acov']}/{p2['n']}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreePassCGAEval}}{{{fmt_pct(p2['rate_cga'], 1)}}}"
            f"  % {p2['n_cga']}/{p2['n']} (no hard violation)"
        )
        lines.append("")

        lines.append("% --- v7.3 Phase 2: Blind Spot Rate (BSR) P(v4_hard | eval=pass) ---")
        lines.append(
            f"\\providecommand{{\\vSevenThreeBsrDxEM}}{{{fmt_pct(p2['bsr_dxem'], 1)}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeBsrAC}}{{{fmt_pct(p2['bsr_ac'], 1)}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeBsrMAB}}{{{fmt_pct(p2['bsr_mab'], 1)}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeBsrCTwo}}{{{fmt_pct(p2['bsr_c2'], 1)}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeBsrACov}}{{{fmt_pct(p2['bsr_acov'], 1)}}}"
        )
        lines.append("")

        lines.append("% --- v7.3 Phase 2: Verdict Flip + Consensus FA ---")
        lines.append(
            f"\\providecommand{{\\vSevenThreeFlipCount}}{{{fmt_int(p2['flip_count'])}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeFlipRate}}{{{fmt_pct(p2['flip_rate'], 1)}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeConsensusFAThreeWay}}{{{fmt_int(p2['fa_3way'])}}}"
            f"  % AC + MAB + C2 pass, TCC fail"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeConsensusFAThreeWayRate}}{{{fmt_pct(p2['fa_3way_rate'], 2)}}}"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeConsensusFAFourWay}}{{{fmt_int(p2['fa_4way'])}}}"
            f"  % + DxEM"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeConsensusFACritThreeWay}}{{{fmt_int(p2['fa_crit_3way'])}}}"
            f"  % critical-severity v4_crit FA"
        )
        lines.append("")

        lines.append("% --- v7.3 Phase 2: Variance Decomposition + Ranking ---")
        lines.append(
            f"\\providecommand{{\\vSevenThreeEtaEval}}{{{fmt_float(p2['eta_eval'], 4)}}}"
            f"  % eta^2(eval) over (AC, MAB, C2, CGA)"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeEtaRun}}{{{fmt_float(p2['eta_run'], 4)}}}"
            f"  % eta^2(run) on cga_pass within (scenario, model)"
        )
        lines.append(
            f"\\providecommand{{\\vSevenThreeKendallW}}{{{fmt_float(p2['kendall_w'], 4)}}}"
            f"  % Kendall W model ranking consistency on cga_pass"
        )
        lines.append("")

        lines.append("% --- v7.3 Phase 2: Per-Model Evaluator Pass Rates ---")
        # Map model_dir name back to canonical key
        for mk in CANONICAL_MODELS:
            if mk not in p2["per_model"]:
                continue
            latex_key = MODEL_LATEX_KEY[mk]
            m = p2["per_model"][mk]
            lines.append(
                f"\\providecommand{{\\vSevenThreeAC{latex_key}}}{{{fmt_pct(m['ac_pass_rate'], 1)}}}  % {mk}"
            )
            lines.append(
                f"\\providecommand{{\\vSevenThreeMAB{latex_key}}}{{{fmt_pct(m['mab_pass_rate'], 1)}}}"
            )
            lines.append(
                f"\\providecommand{{\\vSevenThreeCTwoP{latex_key}}}{{{fmt_pct(m['c2_pass_rate'], 1)}}}"
            )
            lines.append(
                f"\\providecommand{{\\vSevenThreeHard{latex_key}}}{{{fmt_pct(m['v4_hard_rate'], 1)}}}"
            )
            lines.append(
                f"\\providecommand{{\\vSevenThreeCGAEval{latex_key}}}{{{fmt_pct(m['cga_pass_rate'], 1)}}}"
            )
        lines.append("")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text("\n".join(lines) + "\n")
    print(f"Wrote {output} ({len(lines)} lines)")


def main() -> None:
    if not RESULTS_DIR.is_dir():
        raise SystemExit(f"Results dir not found: {RESULTS_DIR}")

    all_eps: dict[str, list[dict]] = {}
    per_model: dict[str, dict] = {}

    print(f"Loading episodes from {RESULTS_DIR} ...")
    for mk in CANONICAL_MODELS:
        d = RESULTS_DIR / mk
        if not d.is_dir():
            print(f"  SKIP {mk}: dir not found")
            continue
        eps = load_episodes(d, mk, mk)
        all_eps[mk] = eps
        per_model[mk] = compute_per_model(eps)
        print(
            f"  {mk}: {per_model[mk]['n']:5d} eps, "
            f"CGA mean={per_model[mk].get('cga_mean', 0):.4f}"
        )

    glob = aggregate_global(per_model)
    per_graph = compute_per_graph(all_eps)

    print(f"\nGlobal: {glob['total_episodes']} eps, "
          f"weighted CGA={glob['weighted_cga_mean']:.4f}, "
          f"pass rate={glob['pass_cga_rate'] * 100:.2f}%")
    print(f"Graphs observed: {len(per_graph)}")

    # Phase 2: verdict matrix derived
    vm = load_verdict_matrix()
    p2 = None
    if vm:
        p2 = compute_phase2_macros(vm)
        print(
            f"\nPhase 2 (verdict matrix): n={p2['n']}, "
            f"v4_hard={p2['rate_v4_hard'] * 100:.1f}%, "
            f"AC={p2['rate_ac'] * 100:.1f}%, "
            f"flip={p2['flip_rate'] * 100:.1f}%, "
            f"eta_eval={p2['eta_eval']:.4f}, "
            f"Kendall W={p2['kendall_w']:.4f}"
        )
    else:
        print(
            f"\nPhase 2: SKIP (verdict matrix not found at {VERDICT_MATRIX}). "
            "Run scripts/experiments/verdict_matrix_v5.py with "
            "CGA_VERDICT_RESULTS_DIR=results/v73_full env vars first."
        )

    EVIDENCE_JSON.parent.mkdir(parents=True, exist_ok=True)
    EVIDENCE_JSON.write_text(
        json.dumps(
            {
                "generated_at": datetime.now(UTC).isoformat(),
                "pool": "sgsc_v73",
                "global": glob,
                "per_model": per_model,
                "per_graph": per_graph,
                "phase2": p2,
            },
            indent=2,
        )
    )
    print(f"Wrote {EVIDENCE_JSON}")

    write_tex(per_model, glob, per_graph, PAPER_TEX, p2=p2)


if __name__ == "__main__":
    main()
