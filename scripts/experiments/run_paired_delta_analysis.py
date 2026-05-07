#!/usr/bin/env python3
"""E7: Paired Delta Analysis — manual vs engine-generated scenarios.

Compares evaluator verdicts between manual (author-written) and auto
(engine-generated) scenarios that share the same CPG graph, using the
same model and run index for paired comparison.

Outputs:
  evidence_pack/analysis/paired_delta_analysis.json
  evidence_pack/analysis/paired_delta_analysis.md
  evidence_pack/tables/paired_delta.tex

Usage:
    PYTHONPATH=. python scripts/experiments/run_paired_delta_analysis.py \
        --episodes-dir results/full_706_v5 \
        [--tex-output paper/auto_numbers.tex]
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.experiments._common import (
    EVIDENCE_DIR,
    HELD_OUT_GRAPH_IDS,
    bootstrap_ci,
    load_all_scenarios,
    save_json,
    save_markdown,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HARD_VIOL_TYPES = {"commission", "timing", "sequence"}
C2_THRESHOLD = 0.7
AC_THRESHOLD = 0.5
MAB_THRESHOLD = 0.5

REPO = Path(__file__).resolve().parents[2]
DEFAULT_EPISODES_DIR = REPO / "results" / "full_706_v5"


# ---------------------------------------------------------------------------
# Episode loading
# ---------------------------------------------------------------------------


def load_episodes(episodes_dir: Path) -> list[dict[str, Any]]:
    """Load all episode JSONs with computed evaluator verdicts."""
    episodes: list[dict[str, Any]] = []
    for model_dir in sorted(episodes_dir.iterdir()):
        if not model_dir.is_dir():
            continue
        model_name = model_dir.name
        for ep_file in sorted(model_dir.glob("*.json")):
            try:
                with open(ep_file) as f:
                    ep = json.load(f)
            except (OSError, json.JSONDecodeError):
                continue
            if not isinstance(ep, dict):
                continue

            scenario_id = ep.get("scenario_id", ep_file.stem)
            run_idx = ep.get("run_index", ep.get("run_id", 0))

            # Compute evaluator verdicts
            viols = ep.get("violation_events", [])
            has_hard_viol = any(v.get("violation_type", "").lower() in HARD_VIOL_TYPES for v in viols)
            sub = ep.get("sub_scores", {})
            c2_score = sub.get("C2_mandatory_completion", 0)
            compliance = ep.get("compliance_score", 0)

            # Action coverage proxy
            expected = ep.get("expected_actions", [])
            actions = ep.get("actions", [])
            action_ids = {a.get("action_id", "") for a in actions}
            ac_coverage = len(action_ids & set(expected)) / max(len(expected), 1) if expected else 0

            # TCC ground truth: no hard violations AND compliance > 0.5
            tcc_pass = not has_hard_viol and compliance >= 0.5

            episodes.append(
                {
                    "scenario_id": scenario_id,
                    "model": model_name,
                    "run_index": run_idx,
                    "compliance_score": compliance,
                    "c2_score": c2_score,
                    "ac_coverage": ac_coverage,
                    "n_violations": len(viols),
                    "has_hard_viol": has_hard_viol,
                    "violation_types": [v.get("violation_type", "") for v in viols],
                    "tcc_pass": tcc_pass,
                    "ac_pass": ac_coverage >= AC_THRESHOLD,
                    "c2_pass": c2_score >= C2_THRESHOLD,
                }
            )

    return episodes


# ---------------------------------------------------------------------------
# Scenario source mapping
# ---------------------------------------------------------------------------


def build_scenario_source_map() -> dict[str, dict[str, Any]]:
    """Map scenario_id -> {source_type, graph_id, ...}."""
    scenarios = load_all_scenarios(tag_source=True)
    mapping: dict[str, dict[str, Any]] = {}
    for sc in scenarios:
        sid = sc.get("scenario_id", "")
        if sid:
            mapping[sid] = {
                "source_type": sc.get("source_type", "unknown"),
                "graph_id": sc.get("_canonical_graph_id", ""),
                "guideline_graph": sc.get("guideline_graph", ""),
            }
    return mapping


# ---------------------------------------------------------------------------
# Paired analysis
# ---------------------------------------------------------------------------


def compute_paired_deltas(
    episodes: list[dict[str, Any]],
    scenario_map: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    """Compute paired delta metrics between manual and auto scenarios.

    Groups by (graph_id, model) and compares manual vs auto false-accept rates.
    """
    # Tag episodes with source info
    for ep in episodes:
        sid = ep["scenario_id"]
        info = scenario_map.get(sid, {})
        ep["source_type"] = info.get("source_type", "unknown")
        ep["graph_id"] = info.get("graph_id", "")

    # Separate manual vs auto
    manual_eps = [e for e in episodes if e["source_type"] == "manual"]
    auto_eps = [e for e in episodes if e["source_type"] == "auto"]

    # --- Aggregate metrics ---
    def fa_rate(eps: list[dict]) -> float:
        """False-accept rate: AC passes but TCC fails."""
        if not eps:
            return 0.0
        fa = sum(1 for e in eps if e["ac_pass"] and not e["tcc_pass"])
        return fa / len(eps)

    def all_oblivious_fa(eps: list[dict]) -> float:
        """All-oblivious FA: AC+C2 both pass but TCC fails."""
        if not eps:
            return 0.0
        fa = sum(1 for e in eps if e["ac_pass"] and e["c2_pass"] and not e["tcc_pass"])
        return fa / len(eps)

    def hard_viol_rate(eps: list[dict]) -> float:
        """Episodes with at least one hard violation."""
        if not eps:
            return 0.0
        return sum(1 for e in eps if e["has_hard_viol"]) / len(eps)

    manual_fa = fa_rate(manual_eps)
    auto_fa = fa_rate(auto_eps)
    manual_ao = all_oblivious_fa(manual_eps)
    auto_ao = all_oblivious_fa(auto_eps)

    # --- Per-graph paired analysis ---
    # Group by (graph_id, model)
    manual_by_gm: dict[tuple[str, str], list[dict]] = defaultdict(list)
    auto_by_gm: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for ep in manual_eps:
        key = (ep["graph_id"], ep["model"])
        manual_by_gm[key].append(ep)
    for ep in auto_eps:
        key = (ep["graph_id"], ep["model"])
        auto_by_gm[key].append(ep)

    # Find paired (graph, model) keys
    paired_keys = set(manual_by_gm.keys()) & set(auto_by_gm.keys())

    # For each paired key: does auto expose violations that manual misses?
    newly_exposed_count = 0
    paired_total = 0
    per_graph_deltas: dict[str, dict[str, Any]] = {}

    graph_groups: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for gid, model in paired_keys:
        graph_groups[gid].append((gid, model))

    for gid in sorted(graph_groups.keys()):
        keys = graph_groups[gid]
        g_manual_fa = 0
        g_auto_fa = 0
        g_manual_n = 0
        g_auto_n = 0
        g_newly_exposed = 0

        for key in keys:
            m_eps = manual_by_gm[key]
            a_eps = auto_by_gm[key]

            m_fa = sum(1 for e in m_eps if e["ac_pass"] and not e["tcc_pass"])
            a_fa = sum(1 for e in a_eps if e["ac_pass"] and not e["tcc_pass"])

            # "Newly exposed": auto scenario fails TCC but manual passes TCC
            m_tcc_fail_rate = sum(1 for e in m_eps if not e["tcc_pass"]) / max(len(m_eps), 1)
            a_tcc_fail_rate = sum(1 for e in a_eps if not e["tcc_pass"]) / max(len(a_eps), 1)

            if a_tcc_fail_rate > m_tcc_fail_rate:
                g_newly_exposed += len(a_eps)

            g_manual_fa += m_fa
            g_auto_fa += a_fa
            g_manual_n += len(m_eps)
            g_auto_n += len(a_eps)

        paired_total += g_auto_n
        newly_exposed_count += g_newly_exposed

        per_graph_deltas[gid] = {
            "manual_n": g_manual_n,
            "auto_n": g_auto_n,
            "manual_fa": g_manual_fa,
            "auto_fa": g_auto_fa,
            "manual_fa_rate": round(g_manual_fa / max(g_manual_n, 1), 4),
            "auto_fa_rate": round(g_auto_fa / max(g_auto_n, 1), 4),
            "delta_fa": round(g_auto_fa / max(g_auto_n, 1) - g_manual_fa / max(g_manual_n, 1), 4),
            "newly_exposed": g_newly_exposed,
            "held_out": gid in HELD_OUT_GRAPH_IDS,
        }

    # --- Violation type breakdown for newly exposed ---
    auto_only_viols: dict[str, int] = defaultdict(int)
    for ep in auto_eps:
        if not ep["tcc_pass"]:
            for vt in ep["violation_types"]:
                auto_only_viols[vt.lower()] += 1

    manual_only_viols: dict[str, int] = defaultdict(int)
    for ep in manual_eps:
        if not ep["tcc_pass"]:
            for vt in ep["violation_types"]:
                manual_only_viols[vt.lower()] += 1

    # --- Bootstrap CIs for delta FA ---
    manual_fa_arr = np.array([1 if (e["ac_pass"] and not e["tcc_pass"]) else 0 for e in manual_eps])
    auto_fa_arr = np.array([1 if (e["ac_pass"] and not e["tcc_pass"]) else 0 for e in auto_eps])

    if len(manual_fa_arr) > 0 and len(auto_fa_arr) > 0:
        manual_ci = bootstrap_ci(manual_fa_arr, np.mean)
        auto_ci = bootstrap_ci(auto_fa_arr, np.mean)
    else:
        manual_ci = (0.0, 0.0)
        auto_ci = (0.0, 0.0)

    # --- McNemar-like test (paired by graph) ---
    # Count concordant/discordant pairs at graph level
    b_count = 0  # manual pass, auto fail
    c_count = 0  # manual fail, auto pass
    for key in paired_keys:
        m_eps = manual_by_gm[key]
        a_eps = auto_by_gm[key]
        m_pass_rate = sum(1 for e in m_eps if e["tcc_pass"]) / max(len(m_eps), 1)
        a_pass_rate = sum(1 for e in a_eps if e["tcc_pass"]) / max(len(a_eps), 1)
        if m_pass_rate > a_pass_rate:
            b_count += 1
        elif a_pass_rate > m_pass_rate:
            c_count += 1

    mcnemar_stat = (abs(b_count - c_count) - 1) ** 2 / max(b_count + c_count, 1)

    # --- Model × source interaction ---
    model_source: dict[str, dict[str, float]] = {}
    models = sorted({e["model"] for e in episodes})
    for model in models:
        m_eps = [e for e in manual_eps if e["model"] == model]
        a_eps = [e for e in auto_eps if e["model"] == model]
        model_source[model] = {
            "manual_fa_rate": round(fa_rate(m_eps), 4),
            "auto_fa_rate": round(fa_rate(a_eps), 4),
            "delta": round(fa_rate(a_eps) - fa_rate(m_eps), 4),
            "manual_n": len(m_eps),
            "auto_n": len(a_eps),
        }

    return {
        "summary": {
            "total_episodes": len(episodes),
            "manual_episodes": len(manual_eps),
            "auto_episodes": len(auto_eps),
            "unmatched_episodes": len(episodes) - len(manual_eps) - len(auto_eps),
            "paired_graph_model_keys": len(paired_keys),
            "n_graphs_with_pairs": len(graph_groups),
        },
        "aggregate": {
            "manual_fa_rate": round(manual_fa, 4),
            "auto_fa_rate": round(auto_fa, 4),
            "delta_fa": round(auto_fa - manual_fa, 4),
            "manual_fa_ci": [round(x, 4) for x in manual_ci],
            "auto_fa_ci": [round(x, 4) for x in auto_ci],
            "manual_all_oblivious_fa": round(manual_ao, 4),
            "auto_all_oblivious_fa": round(auto_ao, 4),
            "delta_all_oblivious": round(auto_ao - manual_ao, 4),
            "manual_hard_viol_rate": round(hard_viol_rate(manual_eps), 4),
            "auto_hard_viol_rate": round(hard_viol_rate(auto_eps), 4),
        },
        "newly_exposed": {
            "count": newly_exposed_count,
            "total_auto_paired": paired_total,
            "rate": round(newly_exposed_count / max(paired_total, 1), 4),
        },
        "violation_type_breakdown": {
            "auto_failing": dict(auto_only_viols),
            "manual_failing": dict(manual_only_viols),
        },
        "mcnemar": {
            "b_manual_pass_auto_fail": b_count,
            "c_manual_fail_auto_pass": c_count,
            "chi2_stat": round(mcnemar_stat, 4),
        },
        "per_graph": per_graph_deltas,
        "model_x_source": model_source,
    }


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(results: dict[str, Any]) -> str:
    """Generate markdown report."""
    s = results["summary"]
    a = results["aggregate"]
    ne = results["newly_exposed"]
    mc = results["mcnemar"]

    lines = [
        "# E7: Paired Delta Analysis — Manual vs Engine Scenarios",
        "",
        "## Summary",
        f"- Total episodes: {s['total_episodes']} (manual={s['manual_episodes']}, auto={s['auto_episodes']})",
        f"- Paired (graph, model) keys: {s['paired_graph_model_keys']}",
        f"- Graphs with pairs: {s['n_graphs_with_pairs']}",
        "",
        "## Aggregate Metrics",
        "| Metric | Manual | Auto | Delta |",
        "|--------|--------|------|-------|",
        f"| FA rate | {a['manual_fa_rate']:.4f} | {a['auto_fa_rate']:.4f} | {a['delta_fa']:+.4f} |",
        f"| All-oblivious FA | {a['manual_all_oblivious_fa']:.4f} | {a['auto_all_oblivious_fa']:.4f} | {a['delta_all_oblivious']:+.4f} |",
        f"| Hard-viol rate | {a['manual_hard_viol_rate']:.4f} | {a['auto_hard_viol_rate']:.4f} | — |",
        "",
        f"Manual FA 95% CI: [{a['manual_fa_ci'][0]:.4f}, {a['manual_fa_ci'][1]:.4f}]",
        f"Auto FA 95% CI: [{a['auto_fa_ci'][0]:.4f}, {a['auto_fa_ci'][1]:.4f}]",
        "",
        "## Newly Exposed by Engine",
        f"- Count: {ne['count']} / {ne['total_auto_paired']} = {ne['rate']:.1%}",
        "",
        "## McNemar Test (Graph-Level)",
        f"- Manual-pass / Auto-fail: {mc['b_manual_pass_auto_fail']}",
        f"- Manual-fail / Auto-pass: {mc['c_manual_fail_auto_pass']}",
        f"- Chi2: {mc['chi2_stat']:.4f}",
        "",
        "## Per-Graph Deltas",
        "| Graph | Manual FA | Auto FA | Delta | Newly Exposed | Held-out |",
        "|-------|-----------|---------|-------|---------------|----------|",
    ]

    for gid, gd in sorted(results["per_graph"].items()):
        ho = "yes" if gd["held_out"] else ""
        lines.append(
            f"| {gid} | {gd['manual_fa_rate']:.3f} ({gd['manual_n']}) "
            f"| {gd['auto_fa_rate']:.3f} ({gd['auto_n']}) "
            f"| {gd['delta_fa']:+.3f} | {gd['newly_exposed']} | {ho} |"
        )

    lines += [
        "",
        "## Model x Source Interaction",
        "| Model | Manual FA | Auto FA | Delta |",
        "|-------|-----------|---------|-------|",
    ]
    for model, ms in sorted(results["model_x_source"].items()):
        lines.append(
            f"| {model} | {ms['manual_fa_rate']:.4f} ({ms['manual_n']}) "
            f"| {ms['auto_fa_rate']:.4f} ({ms['auto_n']}) "
            f"| {ms['delta']:+.4f} |"
        )

    return "\n".join(lines) + "\n"


def update_tex_macros(tex_path: Path, results: dict[str, Any]) -> None:
    """Update auto_numbers.tex with paired delta macros."""
    import re

    a = results["aggregate"]
    ne = results["newly_exposed"]

    macros = {
        "deltaFAManual": round(a["manual_fa_rate"] * 100, 1),
        "deltaFAAuto": round(a["auto_fa_rate"] * 100, 1),
        "deltaFADelta": round(a["delta_fa"] * 100, 1),
        "deltaAOManual": round(a["manual_all_oblivious_fa"] * 100, 1),
        "deltaAOAuto": round(a["auto_all_oblivious_fa"] * 100, 1),
        "newlyExposedCount": ne["count"],
        "newlyExposedRate": round(ne["rate"] * 100, 1),
    }

    if not tex_path.exists():
        print(f"  WARNING: {tex_path} not found, skipping TeX update")
        return

    content = tex_path.read_text()

    # Append new macros if not already present
    new_lines = []
    for macro, value in macros.items():
        pattern = rf"\\newcommand{{\\{macro}}}\{{[^}}]*\}}"
        replacement = rf"\\newcommand{{\\{macro}}}{{{value}}}"
        content_new, n = re.subn(pattern, replacement, content)
        if n > 0:
            content = content_new
        else:
            new_lines.append(f"\\newcommand{{\\{macro}}}{{{value}}}  % E7 paired delta")

    if new_lines:
        # Find E7 section or append at end
        marker = "% E7: Paired Delta"
        if marker not in content:
            content += "\n% ---------------------------------------------------------------------------\n"
            content += f"% {marker}\n"
            content += "% ---------------------------------------------------------------------------\n"
        content += "\n".join(new_lines) + "\n"

    tex_path.write_text(content)
    print(f"  Updated {len(macros)} macros in {tex_path}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="E7: Paired Delta Analysis")
    parser.add_argument(
        "--episodes-dir",
        type=Path,
        default=DEFAULT_EPISODES_DIR,
        help="Directory with model subdirs of episode JSONs",
    )
    parser.add_argument(
        "--tex-output",
        type=Path,
        default=REPO / "paper" / "auto_numbers.tex",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=== E7: Paired Delta Analysis ===")
    print(f"Episodes dir: {args.episodes_dir}")

    # Load data
    scenario_map = build_scenario_source_map()
    print(f"Loaded {len(scenario_map)} scenario definitions")

    episodes = load_episodes(args.episodes_dir)
    print(f"Loaded {len(episodes)} episodes")

    # Run analysis
    results = compute_paired_deltas(episodes, scenario_map)

    # Output
    if args.dry_run:
        print("\n--- DRY RUN ---")
        print(json.dumps(results["summary"], indent=2))
        print(json.dumps(results["aggregate"], indent=2))
        print(json.dumps(results["newly_exposed"], indent=2))
        return

    out_json = EVIDENCE_DIR / "analysis" / "paired_delta_analysis.json"
    out_md = EVIDENCE_DIR / "analysis" / "paired_delta_analysis.md"

    save_json(results, out_json)
    save_markdown(generate_report(results), out_md)
    update_tex_macros(args.tex_output, results)

    print("\nDone.")


if __name__ == "__main__":
    main()
