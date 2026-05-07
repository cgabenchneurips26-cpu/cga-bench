#!/usr/bin/env python3
"""v73_cat_a_and_fa.py — 9-model Cat A reclassification + 2-way consensus FA.

Addresses paper priorities:
  P2: Cat A subset macros for 9 models (full corpus)
  P3: Ranking flip (Cat A vs full)
  P4: 2-way consensus FA (AC ∩ C2) for strict consensus reframe

Deduplicates by (scenario_id, run_index), keeping latest timestamp.
Filters by corpus="sgsc_v73".

Usage:
  PYTHONPATH=. python scripts/experiments/v73_cat_a_and_fa.py
"""

from __future__ import annotations

from collections import defaultdict
import glob
import json
import os
import re
import statistics

import yaml

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
RESULTS_DIR = os.path.join(ROOT, "results", "v73_full")
GRAPH_DIRS = [
    os.path.join(ROOT, "cpg_model", "graphs"),
    os.path.join(ROOT, "cpg_model", "graphs", "auto"),
]
SGSC_DIR = os.path.join(ROOT, "configs", "scenarios", "sgsc")
VERDICT_MATRIX = os.path.join(ROOT, "evidence_pack", "analysis", "verdict_matrix_v7_3.json")
OUTPUT_JSON = os.path.join(ROOT, "evidence_pack", "analysis", "v73_cat_a_9model.json")
OUTPUT_TEX = os.path.join(ROOT, "evidence_pack", "analysis", "v73_cat_a_macros.tex")

CANONICAL_MODELS = [
    "deepseek_r1_7b", "gemma31b", "llama4scout", "nemotron30b",
    "oss120b", "qwen27b", "qwen35b", "qwen397b", "qwen4b",
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

FNAME_RE = re.compile(r"^(.+?)_([a-z0-9_]+?)_r(\d+)_\d{8}_\d{6}\.json$")


# ── Graph vocabulary ─────────────────────────────────────────────────────


def load_graph_vocabs() -> dict[str, set[str]]:
    """Load all graph YAMLs and extract action vocabularies."""
    vocabs: dict[str, set[str]] = {}
    for gdir in GRAPH_DIRS:
        if not os.path.isdir(gdir):
            continue
        for gf in sorted(glob.glob(os.path.join(gdir, "*.yaml"))):
            try:
                with open(gf) as fh:
                    g = yaml.safe_load(fh)
            except Exception:
                continue
            gname = os.path.basename(gf).replace(".yaml", "")
            actions: set[str] = set()
            nodes = g.get("nodes", {})
            if isinstance(nodes, dict):
                for _nid, ndata in nodes.items():
                    if isinstance(ndata, dict):
                        actions.update(ndata.get("mandatory_actions", []))
                        actions.update(ndata.get("allowed_actions", []))
                        actions.update(ndata.get("forbidden_actions", []))
            vocabs[gname] = actions
    return vocabs


def load_sgsc_map() -> dict[str, str]:
    """Map scenario_id → graph_name from SGSC YAMLs."""
    mapping: dict[str, str] = {}
    if not os.path.isdir(SGSC_DIR):
        return mapping
    for f in sorted(glob.glob(os.path.join(SGSC_DIR, "*.yaml"))):
        try:
            with open(f) as fh:
                data = yaml.safe_load(fh)
        except Exception:
            continue
        scens = data if isinstance(data, list) else (data.get("scenarios") or [])
        if isinstance(scens, dict):
            for sid, s in scens.items():
                mapping[sid] = s.get("guideline_graph", "")
        elif isinstance(scens, list):
            for s in scens:
                if isinstance(s, dict):
                    sid = s.get("id") or s.get("scenario_id", "")
                    mapping[sid] = s.get("guideline_graph", "")
    return mapping


# ── Episode loading with dedup ───────────────────────────────────────────


def load_deduped_episodes() -> list[dict]:
    """Load all episodes from CANONICAL_MODELS dirs, dedup by (sid, run_index)."""
    all_eps: list[dict] = []

    for model_key in CANONICAL_MODELS:
        model_dir = os.path.join(RESULTS_DIR, model_key)
        if not os.path.isdir(model_dir):
            print(f"  SKIP {model_key}: directory not found")
            continue

        by_key: dict[tuple[str, int], tuple[str, dict]] = {}
        for f in sorted(glob.glob(os.path.join(model_dir, "*.json"))):
            name = os.path.basename(f)
            if name.startswith(("checkpoint", "model_summary", ".claim")):
                continue
            if not FNAME_RE.match(name):
                continue
            try:
                with open(f) as fh:
                    d = json.load(fh)
            except Exception:
                continue
            if d.get("corpus") != "sgsc_v73":
                continue
            sid = d.get("scenario_id", "")
            ridx = d.get("run_index", -1)
            ts = d.get("timestamp", "")
            key = (sid, ridx)
            if key not in by_key or ts > by_key[key][0]:
                by_key[key] = (ts, d)

        eps = [v[1] for v in by_key.values()]
        # Tag each with canonical model_key
        for e in eps:
            e["_model_key"] = model_key
        all_eps.extend(eps)
        print(f"  {model_key}: {len(eps)} episodes (deduped)")

    # Also merge qwen397b_s2 into qwen397b
    s2_dir = os.path.join(RESULTS_DIR, "qwen397b_s2")
    if os.path.isdir(s2_dir):
        # Get existing qwen397b keys
        q397_keys = {
            (e["scenario_id"], e["run_index"])
            for e in all_eps
            if e["_model_key"] == "qwen397b"
        }
        added = 0
        for f in sorted(glob.glob(os.path.join(s2_dir, "*.json"))):
            name = os.path.basename(f)
            if name.startswith(("checkpoint", "model_summary", ".claim")):
                continue
            if not FNAME_RE.match(name):
                continue
            try:
                with open(f) as fh:
                    d = json.load(fh)
            except Exception:
                continue
            if d.get("corpus") != "sgsc_v73":
                continue
            sid = d.get("scenario_id", "")
            ridx = d.get("run_index", -1)
            key = (sid, ridx)
            if key not in q397_keys:
                d["_model_key"] = "qwen397b"
                all_eps.append(d)
                q397_keys.add(key)
                added += 1
        if added:
            print(f"  qwen397b_s2: merged {added} additional episodes")

    return all_eps


# ── Classification ───────────────────────────────────────────────────────


def classify_episode(
    expected: set[str], graph_vocab: set[str]
) -> str:
    """A = all in graph, B = all SGSC-invented, M = mixed."""
    if not expected:
        return "B"
    in_graph = expected & graph_vocab
    if len(in_graph) == len(expected):
        return "A"
    if len(in_graph) == 0:
        return "B"
    return "M"


# ── Main ─────────────────────────────────────────────────────────────────


def main() -> None:
    print("Loading graph vocabularies...")
    graph_vocabs = load_graph_vocabs()
    print(f"  {len(graph_vocabs)} graphs loaded")

    print("Loading SGSC scenario map...")
    sgsc_map = load_sgsc_map()
    print(f"  {len(sgsc_map)} scenario→graph mappings")

    print("Loading episodes (with dedup)...")
    all_eps = load_deduped_episodes()
    print(f"Total: {len(all_eps)} deduped episodes")

    # Classify each episode
    for e in all_eps:
        sid = e.get("scenario_id", "")
        graph_name = sgsc_map.get(sid, "")
        g_vocab = graph_vocabs.get(graph_name, set())
        expected = set(e.get("expected_actions", []))
        e["_category"] = classify_episode(expected, g_vocab)
        e["_graph"] = graph_name

    # Category counts
    cat_counts = defaultdict(int)
    for e in all_eps:
        cat_counts[e["_category"]] += 1
    print(f"\nCategories: A={cat_counts['A']}  B={cat_counts['B']}  M={cat_counts['M']}")

    cat_a = [e for e in all_eps if e["_category"] == "A"]

    # ── Per-model stats ──────────────────────────────────────────────────
    def _mean(vals: list[float]) -> float:
        return statistics.mean(vals) if vals else 0.0

    def _sub(e: dict, key: str) -> float:
        return (e.get("sub_scores") or {}).get(key, 0.0)

    per_model_all: dict[str, dict] = {}
    per_model_cat_a: dict[str, dict] = {}

    for mk in CANONICAL_MODELS:
        m_all = [e for e in all_eps if e["_model_key"] == mk]
        m_cat_a = [e for e in cat_a if e["_model_key"] == mk]

        if m_all:
            per_model_all[mk] = {
                "n": len(m_all),
                "cga_mean": round(_mean([e.get("compliance_score", 0) for e in m_all]), 4),
            }
        if m_cat_a:
            per_model_cat_a[mk] = {
                "n": len(m_cat_a),
                "cga_mean": round(_mean([e.get("compliance_score", 0) for e in m_cat_a]), 4),
                "c2_mean": round(_mean([_sub(e, "C2_mandatory_completion") for e in m_cat_a]), 4),
                "c1_mean": round(_mean([_sub(e, "C1_path_selection") for e in m_cat_a]), 4),
                "c3_mean": round(_mean([_sub(e, "C3_forbidden_avoidance") for e in m_cat_a]), 4),
                "c4_mean": round(_mean([_sub(e, "C4_timing_compliance") for e in m_cat_a]), 4),
                "match_rate": round(_mean([
                    len(set(e.get("expected_actions", [])) &
                        {a.get("action_id", "") for a in e.get("actions", [])})
                    / max(len(e.get("expected_actions", [])), 1)
                    for e in m_cat_a
                ]), 4),
            }

    # ── Rankings ─────────────────────────────────────────────────────────
    rank_full = sorted(
        per_model_all.items(), key=lambda x: -x[1]["cga_mean"]
    )
    rank_cat_a = sorted(
        per_model_cat_a.items(), key=lambda x: -x[1]["cga_mean"]
    )

    print("\n" + "=" * 72)
    print("RANKING COMPARISON: Full corpus vs Cat A")
    print("=" * 72)
    print(f"\n{'Rank':>4}  {'Full corpus':>20} {'CGA':>6}  |  {'Cat A':>20} {'CGA':>6}")
    print("-" * 72)
    for i in range(len(CANONICAL_MODELS)):
        full_mk = rank_full[i][0] if i < len(rank_full) else "—"
        full_cga = f"{rank_full[i][1]['cga_mean']:.4f}" if i < len(rank_full) else "—"
        ca_mk = rank_cat_a[i][0] if i < len(rank_cat_a) else "—"
        ca_cga = f"{rank_cat_a[i][1]['cga_mean']:.4f}" if i < len(rank_cat_a) else "—"
        print(f"  {i+1:>2}   {full_mk:>20} {full_cga:>6}  |  {ca_mk:>20} {ca_cga:>6}")

    # ── Kendall tau between ranks ────────────────────────────────────────
    full_order = [mk for mk, _ in rank_full]
    cat_a_order = [mk for mk, _ in rank_cat_a]
    n = len(full_order)
    concordant = 0
    discordant = 0
    for i in range(n):
        for j in range(i + 1, n):
            a_i = full_order.index(cat_a_order[i])
            a_j = full_order.index(cat_a_order[j])
            if a_i < a_j:
                concordant += 1
            elif a_i > a_j:
                discordant += 1
    tau = (concordant - discordant) / (n * (n - 1) / 2)
    print(f"\nKendall τ (full vs Cat A): {tau:.4f}")

    # ── 2-way consensus FA (AC ∩ C2) ────────────────────────────────────
    print("\n" + "=" * 72)
    print("2-WAY CONSENSUS FA (Priority 4)")
    print("=" * 72)

    if os.path.exists(VERDICT_MATRIX):
        vm = json.load(open(VERDICT_MATRIX))
        pe = vm.get("per_episode", [])
        print(f"Verdict matrix: {len(pe)} episodes")

        n_ac = sum(1 for ep in pe if ep["ac_proxy"])
        n_c2 = sum(1 for ep in pe if ep["c2_pass"])
        n_ac_c2 = sum(1 for ep in pe if ep["ac_proxy"] and ep["c2_pass"])

        # 2-way FA: AC pass AND C2 pass AND TCC fail (v4_hard = True)
        n_fa_2way_hard = sum(
            1 for ep in pe
            if ep["ac_proxy"] and ep["c2_pass"] and ep["v4_hard"]
        )
        n_fa_2way_crit = sum(
            1 for ep in pe
            if ep["ac_proxy"] and ep["c2_pass"] and ep["v4_crit"]
        )

        # 3-way FA (original): AC ∩ MAB ∩ C2 pass, TCC fail
        n_fa_3way_hard = sum(
            1 for ep in pe
            if ep["ac_proxy"] and ep["mab_proxy"] and ep["c2_pass"] and ep["v4_hard"]
        )

        # Just AC ∩ C2 (ignoring TCC) - the population
        # FA = those in the AC∩C2 population that fail TCC
        n_ac_c2_tcc_fail = sum(
            1 for ep in pe
            if ep["ac_proxy"] and ep["c2_pass"] and ep["v4_hard"]
        )
        n_ac_c2_tcc_pass = sum(
            1 for ep in pe
            if ep["ac_proxy"] and ep["c2_pass"] and not ep["v4_hard"]
        )

        print(f"\n  AC pass:                    {n_ac:>5} ({n_ac / len(pe) * 100:.1f}%)")
        print(f"  C2 pass:                    {n_c2:>5} ({n_c2 / len(pe) * 100:.1f}%)")
        print(f"  AC ∩ C2 (2-way population): {n_ac_c2:>5} ({n_ac_c2 / len(pe) * 100:.1f}%)")
        print(f"    → TCC pass (not FA):      {n_ac_c2_tcc_pass:>5}")
        print(f"    → TCC fail (= FA):        {n_ac_c2_tcc_fail:>5} "
              f"({n_ac_c2_tcc_fail / max(n_ac_c2, 1) * 100:.1f}% of AC∩C2)")
        print(f"  AC ∩ C2 FA (v4_crit):       {n_fa_2way_crit:>5}")
        print(f"  3-way FA (AC∩MAB∩C2, hard): {n_fa_3way_hard:>5}")

        # FA rate as % of total
        fa_2way_pct = n_fa_2way_hard / len(pe) * 100
        fa_2way_crit_pct = n_fa_2way_crit / len(pe) * 100
        print(f"\n  2-way FA rate (hard): {fa_2way_pct:.2f}% of {len(pe)} episodes")
        print(f"  2-way FA rate (crit): {fa_2way_crit_pct:.2f}% of {len(pe)} episodes")
    else:
        print("  VERDICT MATRIX NOT FOUND - cannot compute FA")
        n_ac_c2 = 0
        n_fa_2way_hard = 0
        n_fa_2way_crit = 0
        fa_2way_pct = 0
        fa_2way_crit_pct = 0
        n_ac = 0
        n_c2 = 0

    # ── Generate output artifacts ────────────────────────────────────────
    artifact = {
        "generated": "2026-05-02",
        "generator": "v73_cat_a_and_fa.py",
        "total_episodes": len(all_eps),
        "categories": dict(cat_counts),
        "cat_a_episodes": len(cat_a),
        "cat_a_pct": round(len(cat_a) / len(all_eps) * 100, 1),
        "per_model_all": {mk: per_model_all[mk] for mk in CANONICAL_MODELS if mk in per_model_all},
        "per_model_cat_a": {mk: per_model_cat_a[mk] for mk in CANONICAL_MODELS if mk in per_model_cat_a},
        "ranking_full": [mk for mk, _ in rank_full],
        "ranking_cat_a": [mk for mk, _ in rank_cat_a],
        "kendall_tau": round(tau, 4),
        "fa_2way": {
            "n_ac": n_ac,
            "n_c2": n_c2,
            "n_ac_c2": n_ac_c2,
            "n_fa_hard": n_fa_2way_hard,
            "n_fa_crit": n_fa_2way_crit,
            "fa_hard_pct": round(fa_2way_pct, 2),
            "fa_crit_pct": round(fa_2way_crit_pct, 2),
        },
    }

    os.makedirs(os.path.dirname(OUTPUT_JSON), exist_ok=True)
    with open(OUTPUT_JSON, "w") as fh:
        json.dump(artifact, fh, indent=2)
    print(f"\nJSON: {OUTPUT_JSON}")

    # ── Generate TeX macros ──────────────────────────────────────────────
    lines = [
        "% Auto-generated by v73_cat_a_and_fa.py — DO NOT EDIT",
        f"% Date: 2026-05-02 | Episodes: {len(all_eps)} | Cat A: {len(cat_a)}",
        "",
        "% ── Cat A Episode Counts ──",
        f"\\providecommand{{\\vSevenThreeCatANEpisodes}}{{{len(cat_a)}}}",
        f"\\providecommand{{\\vSevenThreeCatAPct}}{{{len(cat_a) / len(all_eps) * 100:.1f}}}",
        f"\\providecommand{{\\vSevenThreeCatBN}}{{{cat_counts['B']}}}",
        f"\\providecommand{{\\vSevenThreeCatMN}}{{{cat_counts['M']}}}",
        "",
        "% ── Cat A Overall Scores ──",
        f"\\providecommand{{\\vSevenThreeCatAMeanCGA}}{{{_mean([e.get('compliance_score', 0) for e in cat_a]):.3f}}}",
        f"\\providecommand{{\\vSevenThreeCatAMeanCTwo}}{{{_mean([_sub(e, 'C2_mandatory_completion') for e in cat_a]):.3f}}}",
        f"\\providecommand{{\\vSevenThreeCatAMatchPct}}{{{_mean([len(set(e.get('expected_actions', [])) & {a.get('action_id', '') for a in e.get('actions', [])}) / max(len(e.get('expected_actions', [])), 1) for e in cat_a]) * 100:.1f}}}",
        "",
        "% ── Cat A Per-Model CGA (ranked) ──",
    ]

    for mk, stats in rank_cat_a:
        latex_key = MODEL_LATEX_KEY.get(mk, mk)
        lines.append(
            f"\\providecommand{{\\vSevenThreeCatACGA{latex_key}}}{{{stats['cga_mean']:.3f}}}"
        )
    lines.append("")

    lines.append("% ── Cat A Per-Model C2 ──")
    for mk, stats in rank_cat_a:
        latex_key = MODEL_LATEX_KEY.get(mk, mk)
        lines.append(
            f"\\providecommand{{\\vSevenThreeCatACTwo{latex_key}}}{{{stats['c2_mean']:.3f}}}"
        )
    lines.append("")

    lines.append("% ── Ranking Comparison ──")
    lines.append(f"\\providecommand{{\\vSevenThreeKendallTau}}{{{tau:.3f}}}")
    lines.append("")

    lines.append("% ── 2-way Consensus FA (AC ∩ C2) ──")
    lines.append(f"\\providecommand{{\\vSevenThreeTwoWayFAHard}}{{{n_fa_2way_hard}}}")
    lines.append(f"\\providecommand{{\\vSevenThreeTwoWayFACrit}}{{{n_fa_2way_crit}}}")
    lines.append(f"\\providecommand{{\\vSevenThreeTwoWayFAHardPct}}{{{fa_2way_pct:.2f}}}")
    lines.append(f"\\providecommand{{\\vSevenThreeTwoWayFACritPct}}{{{fa_2way_crit_pct:.2f}}}")
    lines.append(f"\\providecommand{{\\vSevenThreeACPassN}}{{{n_ac}}}")
    lines.append(f"\\providecommand{{\\vSevenThreeCTwoPassN}}{{{n_c2}}}")
    lines.append(f"\\providecommand{{\\vSevenThreeACCTwoN}}{{{n_ac_c2}}}")

    with open(OUTPUT_TEX, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    n_macros = sum(1 for l in lines if "providecommand" in l)
    print(f"TeX: {OUTPUT_TEX} ({n_macros} macros)")


if __name__ == "__main__":
    main()
