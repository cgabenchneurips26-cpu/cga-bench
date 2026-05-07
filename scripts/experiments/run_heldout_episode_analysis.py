#!/usr/bin/env python3
"""Held-out Domain Episode Analysis.

Computes episode-level claim metrics (FA rate, verdict-flip, BSR) on
held-out domains (5 graphs) vs in-domain (20 graphs), testing whether
paper-level claims generalise to unseen CPG domains.

Outputs:
  evidence_pack/analysis/heldout_episode_analysis.json
  evidence_pack/analysis/heldout_episode_analysis.md

Usage:
    PYTHONPATH=. python scripts/experiments/run_heldout_episode_analysis.py \
        --episodes-dir results/full_706_v5 \
        [--tex-output paper/auto_numbers.tex]
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import re
import sys
from typing import Any

import numpy as np
from scipy import stats as sp_stats

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

REPO = Path(__file__).resolve().parents[2]
DEFAULT_EPISODES_DIR = REPO / "results" / "full_706_v5"


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def build_scenario_graph_map() -> dict[str, str]:
    """Map scenario_id -> canonical graph_id."""
    scenarios = load_all_scenarios(tag_source=True)
    mapping: dict[str, str] = {}
    for sc in scenarios:
        sid = sc.get("scenario_id", "")
        gid = sc.get("_canonical_graph_id", "")
        if sid and gid:
            mapping[sid] = gid
    return mapping


def load_episodes(episodes_dir: Path) -> list[dict[str, Any]]:
    """Load all episode JSONs with evaluator verdicts."""
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

            viols = ep.get("violation_events", [])
            has_hard_viol = any(v.get("violation_type", "").lower() in HARD_VIOL_TYPES for v in viols)
            sub = ep.get("sub_scores", {})
            c2_score = sub.get("C2_mandatory_completion", 0)
            compliance = ep.get("compliance_score", 0)

            expected = ep.get("expected_actions", [])
            actions = ep.get("actions", [])
            action_ids = {a.get("action_id", "") for a in actions}
            ac_coverage = len(action_ids & set(expected)) / max(len(expected), 1) if expected else 0

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
                    "tcc_pass": tcc_pass,
                    "ac_pass": ac_coverage >= AC_THRESHOLD,
                    "c2_pass": c2_score >= C2_THRESHOLD,
                }
            )

    return episodes


# ---------------------------------------------------------------------------
# Analysis
# ---------------------------------------------------------------------------


def compute_group_metrics(eps: list[dict[str, Any]], label: str) -> dict[str, Any]:
    """Compute claim metrics for a group of episodes."""
    n = len(eps)
    if n == 0:
        return {
            "label": label,
            "n": 0,
            "fa_rate": 0,
            "fa_count": 0,
            "fa_ci": [0, 0],
            "ao_rate": 0,
            "ao_count": 0,
            "verdict_flip_rate": 0,
            "verdict_flip_count": 0,
            "bsr_ac": 0,
            "bsr_c2": 0,
            "hard_viol_rate": 0,
            "mean_compliance": 0,
        }

    # False-accept: AC passes but TCC fails
    fa_eps = [e for e in eps if e["ac_pass"] and not e["tcc_pass"]]
    fa_rate = len(fa_eps) / n

    # All-oblivious FA: AC+C2 both pass but TCC fails
    ao_eps = [e for e in eps if e["ac_pass"] and e["c2_pass"] and not e["tcc_pass"]]
    ao_rate = len(ao_eps) / n

    # Verdict-flip: at least one evaluator disagrees with another
    flip_count = 0
    for e in eps:
        verdicts = [e["ac_pass"], e["c2_pass"], e["tcc_pass"]]
        if len(set(verdicts)) > 1:
            flip_count += 1
    flip_rate = flip_count / n

    # BSR per evaluator
    bsr_ac = sum(1 for e in eps if e["ac_pass"] and not e["tcc_pass"]) / n
    bsr_c2 = sum(1 for e in eps if e["c2_pass"] and not e["tcc_pass"]) / n

    # Hard-violation rate
    hard_rate = sum(1 for e in eps if e["has_hard_viol"]) / n

    # Mean compliance
    mean_compliance = float(np.mean([e["compliance_score"] for e in eps]))

    # Bootstrap CIs
    fa_arr = np.array([1 if (e["ac_pass"] and not e["tcc_pass"]) else 0 for e in eps])
    fa_ci = bootstrap_ci(fa_arr, np.mean) if n > 1 else (fa_rate, fa_rate)

    return {
        "label": label,
        "n": n,
        "fa_rate": round(fa_rate, 4),
        "fa_count": len(fa_eps),
        "fa_ci": [round(x, 4) for x in fa_ci],
        "ao_rate": round(ao_rate, 4),
        "ao_count": len(ao_eps),
        "verdict_flip_rate": round(flip_rate, 4),
        "verdict_flip_count": flip_count,
        "bsr_ac": round(bsr_ac, 4),
        "bsr_c2": round(bsr_c2, 4),
        "hard_viol_rate": round(hard_rate, 4),
        "mean_compliance": round(mean_compliance, 4),
    }


def run_analysis(
    episodes: list[dict[str, Any]],
    scenario_graph_map: dict[str, str],
) -> dict[str, Any]:
    """Run held-out vs in-domain comparison."""
    # Tag episodes with graph_id and domain type
    for ep in episodes:
        gid = scenario_graph_map.get(ep["scenario_id"], "")
        ep["graph_id"] = gid
        ep["is_held_out"] = gid in HELD_OUT_GRAPH_IDS

    in_domain = [e for e in episodes if not e["is_held_out"] and e["graph_id"]]
    held_out = [e for e in episodes if e["is_held_out"]]
    unmatched = [e for e in episodes if not e["graph_id"]]

    in_metrics = compute_group_metrics(in_domain, "in_domain")
    ho_metrics = compute_group_metrics(held_out, "held_out")

    # --- Statistical comparison: Fisher exact on FA counts ---
    if in_metrics["n"] > 0 and ho_metrics["n"] > 0:
        # 2x2: [FA, non-FA] x [in-domain, held-out]
        table = [
            [in_metrics["fa_count"], in_metrics["n"] - in_metrics["fa_count"]],
            [ho_metrics["fa_count"], ho_metrics["n"] - ho_metrics["fa_count"]],
        ]
        odds_ratio, fisher_p = sp_stats.fisher_exact(table)
    else:
        odds_ratio, fisher_p = float("nan"), float("nan")

    # --- Per held-out graph breakdown ---
    ho_by_graph: dict[str, list[dict]] = defaultdict(list)
    for ep in held_out:
        ho_by_graph[ep["graph_id"]].append(ep)

    per_graph = {}
    for gid in sorted(HELD_OUT_GRAPH_IDS):
        geps = ho_by_graph.get(gid, [])
        per_graph[gid] = compute_group_metrics(geps, gid)

    # --- Per-model breakdown for held-out ---
    models = sorted({e["model"] for e in episodes})
    per_model: dict[str, dict[str, Any]] = {}
    for model in models:
        m_in = [e for e in in_domain if e["model"] == model]
        m_ho = [e for e in held_out if e["model"] == model]
        per_model[model] = {
            "in_domain": compute_group_metrics(m_in, f"{model}_in"),
            "held_out": compute_group_metrics(m_ho, f"{model}_ho"),
        }

    return {
        "summary": {
            "total_episodes": len(episodes),
            "in_domain_episodes": len(in_domain),
            "held_out_episodes": len(held_out),
            "unmatched_episodes": len(unmatched),
            "held_out_graphs": sorted(HELD_OUT_GRAPH_IDS),
        },
        "in_domain": in_metrics,
        "held_out": ho_metrics,
        "statistical_comparison": {
            "fisher_exact_p": round(fisher_p, 6) if not np.isnan(fisher_p) else None,
            "odds_ratio": round(odds_ratio, 4) if not np.isnan(odds_ratio) else None,
            "test": "Fisher exact on FA count 2x2",
        },
        "per_held_out_graph": per_graph,
        "per_model": per_model,
    }


# ---------------------------------------------------------------------------
# Report
# ---------------------------------------------------------------------------


def generate_report(results: dict[str, Any]) -> str:
    """Generate markdown report."""
    s = results["summary"]
    ind = results["in_domain"]
    ho = results["held_out"]
    stat = results["statistical_comparison"]

    lines = [
        "# Held-out Domain Episode Analysis",
        "",
        "## Summary",
        f"- In-domain: {ind['n']} episodes ({s['total_episodes'] - ind['n'] - ho['n']} unmatched)",
        f"- Held-out: {ho['n']} episodes",
        f"- Held-out graphs: {', '.join(s['held_out_graphs'])}",
        "",
        "## Claim Metrics Comparison",
        "| Metric | In-Domain | Held-Out | Fisher p |",
        "|--------|-----------|----------|----------|",
        f"| FA rate | {ind['fa_rate']:.4f} [{ind['fa_ci'][0]:.3f}, {ind['fa_ci'][1]:.3f}] "
        f"| {ho['fa_rate']:.4f} [{ho['fa_ci'][0]:.3f}, {ho['fa_ci'][1]:.3f}] "
        f"| {stat['fisher_exact_p']} |",
        f"| All-oblivious FA | {ind['ao_rate']:.4f} | {ho['ao_rate']:.4f} | — |",
        f"| Verdict-flip rate | {ind['verdict_flip_rate']:.4f} | {ho['verdict_flip_rate']:.4f} | — |",
        f"| BSR (AC) | {ind['bsr_ac']:.4f} | {ho['bsr_ac']:.4f} | — |",
        f"| BSR (C2) | {ind['bsr_c2']:.4f} | {ho['bsr_c2']:.4f} | — |",
        f"| Hard-viol rate | {ind['hard_viol_rate']:.4f} | {ho['hard_viol_rate']:.4f} | — |",
        f"| Mean compliance | {ind['mean_compliance']:.4f} | {ho['mean_compliance']:.4f} | — |",
        "",
        "## Per Held-Out Graph",
        "| Graph | N | FA Rate | AO Rate | Flip Rate | Compliance |",
        "|-------|---|---------|---------|-----------|------------|",
    ]

    for gid, gm in sorted(results["per_held_out_graph"].items()):
        lines.append(
            f"| {gid} | {gm['n']} | {gm['fa_rate']:.3f} | {gm['ao_rate']:.3f} "
            f"| {gm['verdict_flip_rate']:.3f} | {gm['mean_compliance']:.3f} |"
            if gm["n"] > 0
            else f"| {gid} | 0 | — | — | — | — |"
        )

    lines += [
        "",
        "## Per-Model (In-Domain vs Held-Out)",
        "| Model | In FA | HO FA | In Compliance | HO Compliance |",
        "|-------|-------|-------|---------------|---------------|",
    ]
    for model, md in sorted(results["per_model"].items()):
        mi = md["in_domain"]
        mh = md["held_out"]
        lines.append(
            f"| {model} | {mi['fa_rate']:.3f} ({mi['n']}) "
            f"| {mh['fa_rate']:.3f} ({mh['n']}) "
            f"| {mi['mean_compliance']:.3f} | {mh['mean_compliance']:.3f} |"
            if mh["n"] > 0
            else f"| {model} | {mi['fa_rate']:.3f} ({mi['n']}) | — (0) | {mi['mean_compliance']:.3f} | — |"
        )

    return "\n".join(lines) + "\n"


def update_tex_macros(tex_path: Path, results: dict[str, Any]) -> None:
    """Append held-out macros to auto_numbers.tex."""
    ind = results["in_domain"]
    ho = results["held_out"]

    macros = {
        "heldoutN": ho["n"],
        "heldoutFARate": round(ho["fa_rate"] * 100, 1),
        "heldoutAORate": round(ho["ao_rate"] * 100, 1),
        "heldoutFlipRate": round(ho["verdict_flip_rate"] * 100, 1),
        "heldoutCompliance": round(ho["mean_compliance"], 3),
        "indomainFARate": round(ind["fa_rate"] * 100, 1),
        "indomainCompliance": round(ind["mean_compliance"], 3),
        "heldoutFisherP": results["statistical_comparison"]["fisher_exact_p"],
    }

    if not tex_path.exists():
        print(f"  WARNING: {tex_path} not found, skipping TeX update")
        return

    content = tex_path.read_text()

    new_lines = []
    for macro, value in macros.items():
        pattern = rf"\\newcommand{{\\{macro}}}\{{[^}}]*\}}"
        replacement = rf"\\newcommand{{\\{macro}}}{{{value}}}"
        content_new, n = re.subn(pattern, replacement, content)
        if n > 0:
            content = content_new
        else:
            new_lines.append(f"\\newcommand{{\\{macro}}}{{{value}}}  % held-out episode")

    if new_lines:
        marker = "% Held-out Episode Analysis"
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
    parser = argparse.ArgumentParser(description="Held-out Domain Episode Analysis")
    parser.add_argument(
        "--episodes-dir",
        type=Path,
        default=DEFAULT_EPISODES_DIR,
    )
    parser.add_argument(
        "--tex-output",
        type=Path,
        default=REPO / "paper" / "auto_numbers.tex",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    print("=== Held-out Domain Episode Analysis ===")
    print(f"Episodes dir: {args.episodes_dir}")

    scenario_graph_map = build_scenario_graph_map()
    print(f"Loaded {len(scenario_graph_map)} scenario->graph mappings")

    episodes = load_episodes(args.episodes_dir)
    print(f"Loaded {len(episodes)} episodes")

    results = run_analysis(episodes, scenario_graph_map)

    if args.dry_run:
        print("\n--- DRY RUN ---")
        print(json.dumps(results["summary"], indent=2))
        print(json.dumps(results["in_domain"], indent=2))
        print(json.dumps(results["held_out"], indent=2))
        print(json.dumps(results["statistical_comparison"], indent=2))
        return

    out_json = EVIDENCE_DIR / "analysis" / "heldout_episode_analysis.json"
    out_md = EVIDENCE_DIR / "analysis" / "heldout_episode_analysis.md"

    save_json(results, out_json)
    save_markdown(generate_report(results), out_md)
    update_tex_macros(args.tex_output, results)

    print("\nDone.")


if __name__ == "__main__":
    main()
