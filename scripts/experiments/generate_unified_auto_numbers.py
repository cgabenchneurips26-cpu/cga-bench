#!/usr/bin/env python3
"""Generate per-pool auto_numbers_*.tex files and a unified consistency audit.

Reads verdict matrices for four episode pools:
  Phase A  (9 models, 19,062 ep) — verdict_matrix_v6.json
  Phase B  (8 models, 76,464 ep) — verdict_matrix_v6_full.json
  v6 base  (8 models, 16,944 ep) — Phase A minus llama4scout
  v7.3 SGSC (9 models, 11,286 ep) — verdict_matrix_v7_3.json (post-CAV)

Outputs:
  paper/auto_numbers_phaseA.tex
  paper/auto_numbers_phaseB.tex
  paper/auto_numbers_v6base.tex
  paper/auto_numbers_v73.tex
  paper/auto_numbers_unified_audit.tex   (cross-pool comparison + divergence flags)

The v7.3 pool also has a richer macro file written by
`generate_v73_auto_numbers.py` (paper/auto_numbers_v73_full.tex) — that
script includes Phase 1 episode-derived metrics + Phase 2 verdict matrix
metrics. This script (generate_unified_auto_numbers.py) writes only the
unified-comparator subset (paper/auto_numbers_v73.tex), with macro names
following the same prefix style as phaseA/phaseB/v6base.

Usage:
    PYTHONPATH=. python scripts/experiments/generate_unified_auto_numbers.py
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

UTC = timezone.utc
from itertools import combinations
import json
from pathlib import Path
import sys
from typing import Any

# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass
class PoolMetrics:
    """Computed metrics for one episode pool."""

    name: str
    n_episodes: int
    n_models: int
    models: dict[str, int]  # model_key -> episode count
    n_scenarios: int

    # Evaluator pass rates
    pass_rates: dict[str, float] = field(default_factory=dict)
    pass_counts: dict[str, int] = field(default_factory=dict)

    # Per-model pass rates
    per_model_ac: dict[str, float] = field(default_factory=dict)
    per_model_mab: dict[str, float] = field(default_factory=dict)
    per_model_c2: dict[str, float] = field(default_factory=dict)
    per_model_cga: dict[str, float] = field(default_factory=dict)
    per_model_n: dict[str, int] = field(default_factory=dict)

    # Hard violation stats
    n_v4_hard: int = 0
    v4_hard_rate: float = 0.0
    n_v4_crit: int = 0

    # BSR (blind spot rate): P(v4_hard | evaluator=pass)
    bsr: dict[str, float] = field(default_factory=dict)
    bsr_counts: dict[str, int] = field(default_factory=dict)

    # Verdict flip
    flip_count: int = 0
    flip_rate: float = 0.0
    pair_disagreements: dict[str, int] = field(default_factory=dict)

    # Consensus FA (all non-TCC evaluators pass, TCC fails)
    consensus_fa_count: int = 0
    consensus_fa_rate: float = 0.0
    consensus_fa_crit: int = 0
    consensus_fa_crit_pct: float = 0.0

    # Variance decomposition (eta-squared)
    eta_eval: float = 0.0
    eta_run: float = 0.0
    eta_ratio: float = 0.0

    # Ranking stats
    friedman_n_reversals: int = 0
    top_one_flip: bool = False


# ---------------------------------------------------------------------------
# Computation helpers
# ---------------------------------------------------------------------------

EVALUATOR_MAP = {
    "DxEM": "dxem",
    "AC-Proxy": "ac_proxy",
    "MAB-Proxy": "mab_proxy",
    "C2>=0.7": "c2_pass",
    "ACov>=0.5": "acov_pass",
    "CGA-Bench": None,  # derived from v4_hard
}

NON_TCC_EVALS = ["ac_proxy", "mab_proxy", "c2_pass"]


def compute_pool_metrics(
    vm: dict[str, Any],
    name: str,
    exclude_models: set[str] | None = None,
) -> PoolMetrics:
    """Compute all metrics from a verdict matrix JSON."""
    meta = vm["metadata"]
    per_episode: list[dict] = vm["per_episode"]
    per_model_raw: dict[str, dict] = vm["per_model"]
    vmat_raw: list[dict] = vm["verdict_matrix"]

    # Filter episodes if needed
    if exclude_models:
        per_episode = [ep for ep in per_episode if ep["model_dir"] not in exclude_models]
        per_model_raw = {k: v for k, v in per_model_raw.items() if k not in exclude_models}

    n_episodes = len(per_episode)
    models = {}
    for ep in per_episode:
        md = ep["model_dir"]
        models[md] = models.get(md, 0) + 1
    n_models = len(models)

    # Scenarios: unique scenario_ids
    scenarios = set(ep["scenario_id"] for ep in per_episode)
    n_scenarios = len(scenarios)

    pm = PoolMetrics(
        name=name,
        n_episodes=n_episodes,
        n_models=n_models,
        models=models,
        n_scenarios=n_scenarios,
    )

    # --- Hard violation stats ---
    hard_count = sum(1 for ep in per_episode if ep.get("v4_hard"))
    crit_count = sum(1 for ep in per_episode if ep.get("v4_crit"))
    pm.n_v4_hard = hard_count
    pm.v4_hard_rate = hard_count / n_episodes if n_episodes else 0
    pm.n_v4_crit = crit_count

    # --- Evaluator pass rates (recompute from episodes) ---
    eval_fields = {
        "DxEM": "dxem",
        "AC-Proxy": "ac_proxy",
        "MAB-Proxy": "mab_proxy",
        "C2": "c2_pass",
        "ACov": "acov_pass",
    }
    for eval_name, field_name in eval_fields.items():
        n_pass = sum(1 for ep in per_episode if ep.get(field_name))
        pm.pass_counts[eval_name] = n_pass
        pm.pass_rates[eval_name] = n_pass / n_episodes if n_episodes else 0

    # CGA-Bench = NOT v4_hard
    cga_pass = n_episodes - hard_count
    pm.pass_counts["CGA-Bench"] = cga_pass
    pm.pass_rates["CGA-Bench"] = cga_pass / n_episodes if n_episodes else 0

    # --- Per-model pass rates ---
    for model_key, model_data in per_model_raw.items():
        pm.per_model_ac[model_key] = model_data.get("ac_pass_rate", 0)
        pm.per_model_mab[model_key] = model_data.get("mab_pass_rate", 0)
        pm.per_model_c2[model_key] = model_data.get("c2_pass_rate", 0) if "c2_pass_rate" in model_data else 0
        pm.per_model_cga[model_key] = model_data.get("cga_pass_rate", 0)
        pm.per_model_n[model_key] = model_data.get("n", 0)

    # --- BSR: P(v4_hard | evaluator=pass) ---
    for eval_name, field_name in eval_fields.items():
        passes_with_hard = sum(1 for ep in per_episode if ep.get(field_name) and ep.get("v4_hard"))
        n_eval_pass = pm.pass_counts[eval_name]
        pm.bsr[eval_name] = passes_with_hard / n_eval_pass if n_eval_pass else 0
        pm.bsr_counts[eval_name] = passes_with_hard

    # --- Verdict flip: how many episodes have at least one eval disagree? ---
    eval_keys_for_flip = ["ac_proxy", "mab_proxy", "c2_pass"]
    cga_key = "v4_hard"  # CGA pass = NOT v4_hard

    flip_count = 0
    for ep in per_episode:
        verdicts = set()
        for fk in eval_keys_for_flip:
            verdicts.add(ep.get(fk, False))
        # Add CGA verdict (inverted)
        verdicts.add(not ep.get(cga_key, True))
        if len(verdicts) > 1:
            flip_count += 1
    pm.flip_count = flip_count
    pm.flip_rate = flip_count / n_episodes if n_episodes else 0

    # Pair disagreements
    eval_combo_keys = eval_keys_for_flip + ["cga"]
    for e1, e2 in combinations(eval_combo_keys, 2):
        disagree = 0
        for ep in per_episode:
            v1 = ep.get(e1, False) if e1 != "cga" else (not ep.get("v4_hard", True))
            v2 = ep.get(e2, False) if e2 != "cga" else (not ep.get("v4_hard", True))
            if v1 != v2:
                disagree += 1
        pair_name = f"{e1} vs {e2}"
        pm.pair_disagreements[pair_name] = disagree

    # --- Consensus FA: all of AC, MAB, C2 pass but v4_hard = True ---
    consensus_fa = 0
    consensus_fa_crit = 0
    for ep in per_episode:
        if ep.get("ac_proxy") and ep.get("mab_proxy") and ep.get("c2_pass") and ep.get("v4_hard"):
            consensus_fa += 1
            if ep.get("v4_crit"):
                consensus_fa_crit += 1
    pm.consensus_fa_count = consensus_fa
    pm.consensus_fa_rate = consensus_fa / n_episodes if n_episodes else 0
    pm.consensus_fa_crit = consensus_fa_crit
    pm.consensus_fa_crit_pct = consensus_fa_crit / consensus_fa if consensus_fa else 0

    # --- Eta-squared (evaluator vs run variance decomposition) ---
    # Simplified: compute per-evaluator pass rate variance across models
    # Full ANOVA would require run-level data; we approximate from per_model
    model_cga_rates = [d.get("cga_pass_rate", 0) for d in per_model_raw.values()]
    if model_cga_rates:
        mean_cga = sum(model_cga_rates) / len(model_cga_rates)
        ss_model = sum((r - mean_cga) ** 2 for r in model_cga_rates)
        # We can't compute true eta_eval without per-episode evaluator labels
        # Store the model variance as a proxy
        pm.eta_eval = ss_model / len(model_cga_rates) if model_cga_rates else 0

    # --- Top-1 flip: does each evaluator pick a different top model? ---
    top_by_eval: dict[str, str] = {}
    rate_maps = {
        "AC": pm.per_model_ac,
        "MAB": pm.per_model_mab,
        "C2": pm.per_model_c2,
        "CGA": pm.per_model_cga,
    }
    for eval_name, rates in rate_maps.items():
        if rates:
            top_model = max(rates, key=rates.get)  # type: ignore[arg-type]
            top_by_eval[eval_name] = top_model
    unique_tops = set(top_by_eval.values())
    pm.top_one_flip = len(unique_tops) > 1

    # --- Ranking reversals (pairwise) ---
    reversal_count = 0
    model_keys = sorted(pm.per_model_cga.keys())
    for m1, m2 in combinations(model_keys, 2):
        orders: list[bool] = []
        for rates in rate_maps.values():
            if m1 in rates and m2 in rates:
                orders.append(rates[m1] > rates[m2])
        if orders and not all(o == orders[0] for o in orders):
            reversal_count += 1
    pm.friedman_n_reversals = reversal_count

    return pm


# ---------------------------------------------------------------------------
# TeX output
# ---------------------------------------------------------------------------


def fmt_pct(val: float) -> str:
    """Format as percentage string for TeX."""
    return f"{val * 100:.1f}"


def fmt_comma(val: int) -> str:
    """Format integer with TeX comma grouping."""
    s = f"{val:,}"
    return s.replace(",", "{,}")


def generate_pool_tex(pm: PoolMetrics, pool_tag: str) -> str:
    """Generate auto_numbers_<pool_tag>.tex content."""
    lines: list[str] = []
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    lines.append("% Auto-generated by generate_unified_auto_numbers.py")
    lines.append(f"% Pool: {pm.name} | Generated: {ts}")
    lines.append(f"% Episodes: {pm.n_episodes} | Models: {pm.n_models} | Scenarios: {pm.n_scenarios}")
    lines.append("")

    tag = pool_tag  # e.g. "phaseA", "phaseB", "vSixBase"
    Tag = tag[0].upper() + tag[1:]

    # --- Core counts ---
    lines.append(f"% --- {pm.name}: Core Counts ---")
    lines.append(f"\\providecommand{{\\{tag}NEpisodes}}{{{fmt_comma(pm.n_episodes)}}}")
    lines.append(f"\\providecommand{{\\{tag}NModels}}{{{pm.n_models}}}")
    lines.append(f"\\providecommand{{\\{tag}NScenarios}}{{{pm.n_scenarios}}}")
    lines.append(f"\\providecommand{{\\{tag}NHard}}{{{fmt_comma(pm.n_v4_hard)}}}")
    lines.append(f"\\providecommand{{\\{tag}HardRate}}{{{fmt_pct(pm.v4_hard_rate)}}}")
    lines.append(f"\\providecommand{{\\{tag}NCrit}}{{{fmt_comma(pm.n_v4_crit)}}}")
    lines.append("")

    # --- Evaluator pass rates ---
    lines.append(f"% --- {pm.name}: Evaluator Pass Rates ---")
    eval_short = {
        "DxEM": "DxEM",
        "AC-Proxy": "AC",
        "MAB-Proxy": "MAB",
        "C2": "CTwo",
        "ACov": "ACov",
        "CGA-Bench": "CGA",
    }
    for eval_name, short in eval_short.items():
        rate = pm.pass_rates.get(eval_name, 0)
        count = pm.pass_counts.get(eval_name, 0)
        lines.append(f"\\providecommand{{\\{tag}Pass{short}}}{{{fmt_pct(rate)}}}  % {count}/{pm.n_episodes}")
    lines.append("")

    # --- BSR ---
    lines.append(f"% --- {pm.name}: Blind Spot Rate P(v4_hard | eval=pass) ---")
    for eval_name, short in eval_short.items():
        if eval_name in pm.bsr:
            bsr_val = pm.bsr[eval_name]
            bsr_cnt = pm.bsr_counts[eval_name]
            n_pass = pm.pass_counts.get(eval_name, 0)
            lines.append(f"\\providecommand{{\\{tag}Bsr{short}}}{{{fmt_pct(bsr_val)}}}  % {bsr_cnt}/{n_pass}")
    lines.append("")

    # --- Verdict flip ---
    lines.append(f"% --- {pm.name}: Verdict Flip ---")
    lines.append(f"\\providecommand{{\\{tag}FlipCount}}{{{fmt_comma(pm.flip_count)}}}")
    lines.append(f"\\providecommand{{\\{tag}FlipRate}}{{{fmt_pct(pm.flip_rate)}}}")
    lines.append("")

    # --- Consensus FA ---
    lines.append(f"% --- {pm.name}: Consensus False Accept (AC+MAB+C2 pass, TCC fail) ---")
    lines.append(f"\\providecommand{{\\{tag}ConsensusFACount}}{{{fmt_comma(pm.consensus_fa_count)}}}")
    lines.append(f"\\providecommand{{\\{tag}ConsensusFARate}}{{{fmt_pct(pm.consensus_fa_rate)}}}")
    lines.append(f"\\providecommand{{\\{tag}ConsensusFACrit}}{{{pm.consensus_fa_crit}}}")
    lines.append(f"\\providecommand{{\\{tag}ConsensusFACritPct}}{{{pm.consensus_fa_crit_pct * 100:.2f}}}")
    lines.append("")

    # --- Per-model pass rates ---
    lines.append(f"% --- {pm.name}: Per-Model Pass Rates ---")
    model_tex_names = {
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
    for model_key in sorted(pm.per_model_ac.keys()):
        mname = model_tex_names.get(model_key, model_key)
        n = pm.per_model_n.get(model_key, 0)
        ac = pm.per_model_ac.get(model_key, 0)
        mab = pm.per_model_mab.get(model_key, 0)
        cga = pm.per_model_cga.get(model_key, 0)
        lines.append(f"\\providecommand{{\\{tag}N{mname}}}{{{fmt_comma(n)}}}  % {model_key}")
        lines.append(f"\\providecommand{{\\{tag}AC{mname}}}{{{ac * 100:.1f}}}  % {model_key} AC pass rate")
        lines.append(f"\\providecommand{{\\{tag}MAB{mname}}}{{{mab * 100:.1f}}}  % {model_key} MAB pass rate")
        lines.append(f"\\providecommand{{\\{tag}CGA{mname}}}{{{cga * 100:.1f}}}  % {model_key} CGA pass rate")
    lines.append("")

    # --- Ranking ---
    lines.append(f"% --- {pm.name}: Ranking ---")
    lines.append(f"\\providecommand{{\\{tag}RankReversals}}{{{pm.friedman_n_reversals}}}")
    lines.append(f"\\providecommand{{\\{tag}TopOneFlip}}{{{'yes' if pm.top_one_flip else 'no'}}}")

    # Top model per evaluator
    rate_maps = {
        "AC": pm.per_model_ac,
        "MAB": pm.per_model_mab,
        "CGA": pm.per_model_cga,
    }
    for eval_name, rates in rate_maps.items():
        if rates:
            top = max(rates, key=rates.get)  # type: ignore[arg-type]
            lines.append(f"\\providecommand{{\\{tag}Top{eval_name}}}{{{model_tex_names.get(top, top)}}}  % {top}")
    lines.append("")

    return "\n".join(lines) + "\n"


def generate_audit_tex(
    pools: dict[str, PoolMetrics],
) -> str:
    """Generate cross-pool consistency audit."""
    lines: list[str] = []
    ts = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")

    lines.append("% =======================================================================")
    lines.append("% UNIFIED CROSS-POOL CONSISTENCY AUDIT")
    lines.append(f"% Generated: {ts}")
    lines.append("% =======================================================================")
    lines.append("%")
    lines.append("% This file documents where each pool's metrics agree and diverge.")
    lines.append("% DIVERGENCE flags indicate metrics that differ by >2pp between pools.")
    lines.append("% Use this to verify which pool a paper macro should reference.")
    lines.append("")

    # --- Pool summary table ---
    lines.append("% --- Pool Overview ---")
    for pname, pm in pools.items():
        lines.append(f"% {pname:12s}: {pm.n_episodes:>7,} episodes, {pm.n_models} models, {pm.n_scenarios} scenarios")
    lines.append("")

    # --- Cross-pool pass rate comparison ---
    lines.append("% --- Pass Rate Comparison (% values) ---")
    lines.append("% Evaluator     | " + " | ".join(f"{p:>12s}" for p in pools) + " | Diverge?")
    eval_names = ["DxEM", "AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]
    divergences: list[str] = []

    for eval_name in eval_names:
        vals = {}
        for pname, pm in pools.items():
            vals[pname] = pm.pass_rates.get(eval_name, 0) * 100
        val_strs = " | ".join(f"{vals[p]:>11.1f}%" for p in pools)
        max_diff = max(vals.values()) - min(vals.values())
        flag = "DIVERGE" if max_diff > 2.0 else "ok"
        lines.append(f"% {eval_name:14s} | {val_strs} | {flag} ({max_diff:.1f}pp)")
        if flag == "DIVERGE":
            divergences.append(f"{eval_name}: {max_diff:.1f}pp spread")
    lines.append("")

    # --- Cross-pool BSR comparison ---
    lines.append("% --- BSR Comparison P(v4_hard | eval=pass) ---")
    lines.append("% Evaluator     | " + " | ".join(f"{p:>12s}" for p in pools) + " | Diverge?")
    for eval_name in ["AC-Proxy", "MAB-Proxy", "C2"]:
        vals = {}
        for pname, pm in pools.items():
            vals[pname] = pm.bsr.get(eval_name, 0) * 100
        val_strs = " | ".join(f"{vals[p]:>11.1f}%" for p in pools)
        max_diff = max(vals.values()) - min(vals.values())
        flag = "DIVERGE" if max_diff > 2.0 else "ok"
        lines.append(f"% {eval_name:14s} | {val_strs} | {flag} ({max_diff:.1f}pp)")
        if flag == "DIVERGE":
            divergences.append(f"BSR({eval_name}): {max_diff:.1f}pp spread")
    lines.append("")

    # --- Verdict flip ---
    lines.append("% --- Verdict Flip Comparison ---")
    for pname, pm in pools.items():
        lines.append(f"% {pname:12s}: {pm.flip_count:>7,} flips ({pm.flip_rate * 100:.1f}%)")
    flip_rates = [pm.flip_rate * 100 for pm in pools.values()]
    flip_diff = max(flip_rates) - min(flip_rates)
    if flip_diff > 2.0:
        divergences.append(f"Verdict flip rate: {flip_diff:.1f}pp spread")
    lines.append("")

    # --- Consensus FA ---
    lines.append("% --- Consensus FA Comparison ---")
    for pname, pm in pools.items():
        lines.append(
            f"% {pname:12s}: {pm.consensus_fa_count:>5,} FA ({pm.consensus_fa_rate * 100:.2f}%), "
            f"{pm.consensus_fa_crit} critical ({pm.consensus_fa_crit_pct * 100:.1f}%)"
        )
    lines.append("")

    # --- Ranking reversals ---
    lines.append("% --- Ranking Reversal Comparison ---")
    for pname, pm in pools.items():
        lines.append(
            f"% {pname:12s}: {pm.friedman_n_reversals} pairwise reversals, "
            f"top-1 flip={'yes' if pm.top_one_flip else 'no'}"
        )
    lines.append("")

    # --- Top model per evaluator ---
    lines.append("% --- Top Model by Evaluator ---")
    for eval_abbr in ["AC", "MAB", "CGA"]:
        row = f"% {eval_abbr:5s}: "
        tops = []
        for pname, pm in pools.items():
            rates = {"AC": pm.per_model_ac, "MAB": pm.per_model_mab, "CGA": pm.per_model_cga}[eval_abbr]
            if rates:
                top = max(rates, key=rates.get)  # type: ignore[arg-type]
                tops.append(top)
                row += f"{pname}={top:20s} "
            else:
                tops.append("")
                row += f"{pname}={'N/A':20s} "
        lines.append(row)
        if len(set(t for t in tops if t)) > 1:
            divergences.append(f"Top-1 model for {eval_abbr} differs across pools")
    lines.append("")

    # --- Summary of divergences ---
    lines.append("% =======================================================================")
    lines.append(f"% DIVERGENCE SUMMARY: {len(divergences)} issues found")
    lines.append("% =======================================================================")
    if divergences:
        for i, d in enumerate(divergences, 1):
            lines.append(f"% [{i}] {d}")
    else:
        lines.append("% No divergences > 2pp detected. All pools are consistent.")
    lines.append("")

    # --- Convenience macros mapping current auto_numbers.tex to correct pool ---
    lines.append("% =======================================================================")
    lines.append("% MACRO-TO-POOL MAPPING for current auto_numbers.tex")
    lines.append("% =======================================================================")
    mapping = [
        ("\\numEpisodes{19,062}", "phaseA", "CORRECT"),
        ("\\numModels{9}", "phaseA", "CORRECT"),
        ("\\passtrateACProxy{76.9}", "AMBIGUOUS", "v6base=76.9, phaseA has 9 models"),
        ("\\passrateCGABench{44.6}", "AMBIGUOUS", "v6base only (8 models)"),
        ("\\etaEvaluator{0.190}", "phaseB", "Comment says 'v6 Phase B n=76,464'"),
        ("\\reversalRate{96.4}", "phaseB", "Comment says 'v6 Phase B'"),
        ("\\verdictFlipRate{92.0}", "phaseA?", "No explicit pool tag"),
        ("\\solverSubsetN{16944}", "v6base", "8 models x 706 x 3"),
        ("\\normalizerMMEpisodes{16944}", "v6base", "Comment says '8 models'"),
        ("\\cresOneDNEpisodes{14,826}", "STALE(v5)", "7-model W8 era — never recomputed"),
        ("\\consensusFATotal{2,106}", "phaseA", "Comment says 'Phase A 9m'"),
        ("\\numEpisodesDS{9558}", "phaseB", "76464/8 = 9558 per model"),
        ("\\bsrCondAC{60.9}", "phaseB", "Comment says 'v6 Phase B'"),
    ]
    for macro, pool, note in mapping:
        lines.append(f"% {macro:45s} -> {pool:12s} | {note}")
    lines.append("")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    base = Path(__file__).resolve().parents[2]
    evidence = base / "evidence_pack" / "analysis"
    paper_dir = base / "paper"

    # Load verdict matrices
    vm_a_path = evidence / "verdict_matrix_v6.json"
    vm_b_path = evidence / "verdict_matrix_v6_full.json"
    vm_v73_path = evidence / "verdict_matrix_v7_3.json"

    if not vm_a_path.exists():
        print(f"ERROR: {vm_a_path} not found")
        return 1
    if not vm_b_path.exists():
        print(f"ERROR: {vm_b_path} not found")
        return 1

    with open(vm_a_path) as f:
        vm_a = json.load(f)
    with open(vm_b_path) as f:
        vm_b = json.load(f)
    vm_v73 = None
    if vm_v73_path.exists():
        with open(vm_v73_path) as f:
            vm_v73 = json.load(f)

    print("=" * 72)
    print("UNIFIED AUTO_NUMBERS GENERATOR")
    print("=" * 72)

    # --- Compute Phase A (9 models, all episodes) ---
    print("\n[1/3] Computing Phase A metrics (9 models, 19,062 episodes)...")
    phase_a = compute_pool_metrics(vm_a, "Phase A (9-model headline)")
    print(f"      {phase_a.n_episodes} episodes, {phase_a.n_models} models, {phase_a.n_scenarios} scenarios")

    # --- Compute v6 baseline (Phase A minus llama4scout) ---
    print("\n[2/3] Computing v6 baseline metrics (8 models, 16,944 episodes)...")
    v6_base = compute_pool_metrics(vm_a, "v6 Baseline (8-model)", exclude_models={"llama4scout"})
    print(f"      {v6_base.n_episodes} episodes, {v6_base.n_models} models, {v6_base.n_scenarios} scenarios")

    # --- Compute Phase B (8 models, 76,464 episodes) ---
    print("\n[3/3] Computing Phase B metrics (8 models, 76,464 episodes)...")
    phase_b = compute_pool_metrics(vm_b, "Phase B (8-model auto-expanded)")
    print(f"      {phase_b.n_episodes} episodes, {phase_b.n_models} models, {phase_b.n_scenarios} scenarios")

    # --- Compute v7.3 SGSC (9 models, 11,286 episodes, post-CAV) ---
    v73 = None
    if vm_v73 is not None:
        print("\n[4/4] Computing v7.3 SGSC metrics (9 models, 11,286 episodes, post-CAV)...")
        v73 = compute_pool_metrics(vm_v73, "v7.3 SGSC (9-model post-CAV)")
        print(
            f"      {v73.n_episodes} episodes, {v73.n_models} models, {v73.n_scenarios} scenarios"
        )
    else:
        print(
            f"\n[4/4] SKIP v7.3 — verdict_matrix_v7_3.json not found at {vm_v73_path}.\n"
            "       Run: CGA_VERDICT_RESULTS_DIR=results/v73_full \\\n"
            "         CGA_VERDICT_OUTPUT_JSON=evidence_pack/analysis/verdict_matrix_v7_3.json \\\n"
            "         python scripts/experiments/verdict_matrix_v5.py"
        )

    # --- Generate per-pool .tex files ---
    pools: dict[str, PoolMetrics] = {
        "phaseA": phase_a,
        "v6base": v6_base,
        "phaseB": phase_b,
    }
    if v73 is not None:
        pools["v73"] = v73

    for tag, pm in pools.items():
        tex_content = generate_pool_tex(pm, tag)
        out_path = paper_dir / f"auto_numbers_{tag}.tex"
        out_path.write_text(tex_content)
        print(f"\n  -> {out_path.name} ({len(tex_content)} bytes)")

    # --- Generate unified audit ---
    audit_content = generate_audit_tex(pools)
    audit_path = paper_dir / "auto_numbers_unified_audit.tex"
    audit_path.write_text(audit_content)
    print(f"\n  -> {audit_path.name} ({len(audit_content)} bytes)")

    # --- Print summary to console ---
    print("\n" + "=" * 72)
    print("CROSS-POOL PASS RATE SUMMARY")
    print("=" * 72)
    header = f"{'Evaluator':15s}"
    for tag in pools:
        header += f" | {tag:>12s}"
    print(header)
    print("-" * len(header))

    for eval_name in ["DxEM", "AC-Proxy", "MAB-Proxy", "C2", "CGA-Bench"]:
        row = f"{eval_name:15s}"
        vals = []
        for tag, pm in pools.items():
            v = pm.pass_rates.get(eval_name, 0) * 100
            vals.append(v)
            row += f" | {v:>11.1f}%"
        spread = max(vals) - min(vals)
        flag = " ** DIVERGE" if spread > 2.0 else ""
        row += f"  ({spread:.1f}pp){flag}"
        print(row)

    print("\n" + "=" * 72)
    print("VERDICT FLIP / CONSENSUS FA")
    print("=" * 72)
    for tag, pm in pools.items():
        print(
            f"  {tag:12s}: flip={pm.flip_rate * 100:.1f}%, "
            f"consensusFA={pm.consensus_fa_count} ({pm.consensus_fa_rate * 100:.2f}%)"
        )

    print("\n" + "=" * 72)
    print("TOP MODEL PER EVALUATOR")
    print("=" * 72)
    for eval_abbr in ["AC", "MAB", "CGA"]:
        row = f"  {eval_abbr:5s}: "
        for tag, pm in pools.items():
            rates = {"AC": pm.per_model_ac, "MAB": pm.per_model_mab, "CGA": pm.per_model_cga}[eval_abbr]
            if rates:
                top = max(rates, key=rates.get)  # type: ignore[arg-type]
                row += f"{tag}={top:18s} "
        print(row)

    print("\n" + "=" * 72)
    print("FILES WRITTEN")
    print("=" * 72)
    for tag in pools:
        print(f"  paper/auto_numbers_{tag}.tex")
    print("  paper/auto_numbers_unified_audit.tex")
    print()

    return 0


if __name__ == "__main__":
    sys.exit(main())
