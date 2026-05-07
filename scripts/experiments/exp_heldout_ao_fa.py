#!/usr/bin/env python3
"""Exp 6 — Held-out All-Oblivious False-Accept Rate.

Defence target: Attack #18 "Held-out = parsing only"
Demonstrates that the all-oblivious false-accept pattern generalises to
held-out CPG domains (5 graphs not used during benchmark development).

All-oblivious FA := DxEM=pass AND AC-Proxy=pass AND C2=pass AND v4_hard=True
(i.e., every oblivious evaluator says PASS but the episode has hard violations)

Outputs:
    evidence_pack/heldout_ao_fa/heldout_ao_fa.json
    evidence_pack/heldout_ao_fa/heldout_ao_fa.md

Usage:
    PYTHONPATH=${CGA_BENCH_ROOT} \
      python scripts/experiments/exp_heldout_ao_fa.py
"""

from __future__ import annotations

import json
from pathlib import Path
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
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

ROOT = Path(__file__).resolve().parents[2]
VM_PATH = ROOT / "evidence_pack" / "analysis" / "verdict_matrix_v6.json"
OUTPUT_DIR = EVIDENCE_DIR / "heldout_ao_fa"


# ---------------------------------------------------------------------------
# Scenario → graph mapping
# ---------------------------------------------------------------------------


def build_scenario_graph_map() -> dict[str, str]:
    """Map scenario_id → canonical graph_id."""
    scenarios = load_all_scenarios(tag_source=True)
    mapping: dict[str, str] = {}
    for sc in scenarios:
        sid = sc.get("scenario_id", "")
        gid = sc.get("_canonical_graph_id", "")
        if sid and gid:
            mapping[sid] = gid
    return mapping


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------


def run_analysis() -> dict[str, Any]:
    """Run held-out vs in-domain all-oblivious FA comparison."""
    # Load canonical episode set
    vm = json.loads(VM_PATH.read_text())
    episodes: list[dict[str, Any]] = vm["per_episode"]
    n_total = len(episodes)
    print(f"Loaded {n_total} canonical episodes from verdict_matrix_v6.json")

    # Map scenario → graph
    sg_map = build_scenario_graph_map()

    # Tag each episode
    for ep in episodes:
        gid = sg_map.get(ep.get("scenario_id", ""), "")
        ep["graph_id"] = gid
        ep["is_held_out"] = gid in HELD_OUT_GRAPH_IDS

    held_out = [e for e in episodes if e["is_held_out"]]
    in_domain = [e for e in episodes if not e["is_held_out"] and e["graph_id"]]
    unmapped = [e for e in episodes if not e["graph_id"]]

    print(f"  held-out: {len(held_out)}, in-domain: {len(in_domain)}, unmapped: {len(unmapped)}")

    def compute_ao_fa(eps: list[dict[str, Any]], label: str) -> dict[str, Any]:
        """Compute all-oblivious FA metrics for a group."""
        n = len(eps)
        if n == 0:
            return {"label": label, "n": 0, "ao_fa_rate": 0.0, "ao_fa_count": 0, "cond_fa_rate": 0.0}

        # All-oblivious pass: DxEM + AC-Proxy + C2 all pass
        # DxEM is always True (degenerate), so effectively AC + C2
        ao_pass = [e for e in eps if e.get("dxem", True) and e.get("ac_proxy", False) and e.get("c2_pass", False)]
        # FA: all-oblivious pass AND has hard violation
        ao_fa = [e for e in ao_pass if e.get("v4_hard", False)]

        ao_fa_rate = len(ao_fa) / n
        ao_pass_rate = len(ao_pass) / n

        # Conditional FA rate: P(hard | AO-pass)
        cond_fa_rate = len(ao_fa) / len(ao_pass) if len(ao_pass) > 0 else 0.0

        # Bootstrap CI on FA rate
        fa_arr = np.array(
            [
                1
                if (
                    e.get("dxem", True)
                    and e.get("ac_proxy", False)
                    and e.get("c2_pass", False)
                    and e.get("v4_hard", False)
                )
                else 0
                for e in eps
            ]
        )
        ci = bootstrap_ci(fa_arr, np.mean) if n > 1 else (ao_fa_rate, ao_fa_rate)

        # Hard violation rate
        hard_rate = sum(1 for e in eps if e.get("v4_hard", False)) / n

        return {
            "label": label,
            "n": n,
            "ao_pass_count": len(ao_pass),
            "ao_pass_rate": round(ao_pass_rate * 100, 1),
            "ao_fa_count": len(ao_fa),
            "ao_fa_rate": round(ao_fa_rate * 100, 1),
            "ao_fa_ci_95": [round(x * 100, 1) for x in ci],
            "hard_viol_rate": round(hard_rate * 100, 1),
            "cond_fa_rate": round(cond_fa_rate * 100, 1),
        }

    held_out_metrics = compute_ao_fa(held_out, "held-out")
    in_domain_metrics = compute_ao_fa(in_domain, "in-domain")
    overall_metrics = compute_ao_fa(episodes, "overall")

    # Fisher exact test: held-out vs in-domain AO FA rate
    # Contingency table: [[ao_fa_heldout, not_ao_fa_heldout], [ao_fa_indomain, not_ao_fa_indomain]]
    a = held_out_metrics["ao_fa_count"]
    b = held_out_metrics["n"] - a
    c = in_domain_metrics["ao_fa_count"]
    d = in_domain_metrics["n"] - c
    odds_ratio, fisher_p = sp_stats.fisher_exact([[a, b], [c, d]])

    # Per held-out domain breakdown
    domain_breakdown: dict[str, dict[str, Any]] = {}
    for gid in sorted(HELD_OUT_GRAPH_IDS):
        domain_eps = [e for e in held_out if e["graph_id"] == gid]
        if domain_eps:
            domain_breakdown[gid] = compute_ao_fa(domain_eps, gid)

    result = {
        "description": "Held-out All-Oblivious False-Accept Rate (Attack #18 defense)",
        "n_total": n_total,
        "held_out": held_out_metrics,
        "in_domain": in_domain_metrics,
        "overall": overall_metrics,
        "fisher_exact": {
            "odds_ratio": round(odds_ratio, 4),
            "p_value": float(f"{fisher_p:.6g}"),
            "contingency": [[a, b], [c, d]],
        },
        "domain_breakdown": domain_breakdown,
        "auto_numbers": {
            "heldoutAllObliviousFA": held_out_metrics["ao_fa_rate"],
            "heldoutAllObliviousCount": held_out_metrics["ao_fa_count"],
            "heldoutAOPassRate": held_out_metrics["ao_pass_rate"],
            "heldoutCondFA": held_out_metrics["cond_fa_rate"],
            "indomainAllObliviousFA": in_domain_metrics["ao_fa_rate"],
            "indomainCondFA": in_domain_metrics["cond_fa_rate"],
            "fisherPHeldoutAOFA": float(f"{fisher_p:.6g}"),
        },
    }

    return result


def generate_markdown(result: dict[str, Any]) -> str:
    """Generate human-readable report."""
    ho = result["held_out"]
    ind = result["in_domain"]
    fe = result["fisher_exact"]

    lines = [
        "# Held-out All-Oblivious False-Accept Rate",
        "",
        f"**Total episodes**: {result['n_total']}",
        f"**Held-out**: {ho['n']} episodes (5 graphs)",
        f"**In-domain**: {ind['n']} episodes (20 graphs)",
        "",
        "## All-Oblivious FA Rate",
        "",
        "All-oblivious FA = DxEM + AC-Proxy + C2 all pass, but episode has hard violations.",
        "",
        "| Group | N | AO Pass | AO FA | AO FA Rate | 95% CI | Hard Viol Rate |",
        "|-------|---|---------|-------|------------|--------|----------------|",
        f"| Held-out | {ho['n']} | {ho['ao_pass_count']} | {ho['ao_fa_count']} | "
        f"{ho['ao_fa_rate']}% | [{ho['ao_fa_ci_95'][0]}, {ho['ao_fa_ci_95'][1]}]% | {ho['hard_viol_rate']}% |",
        f"| In-domain | {ind['n']} | {ind['ao_pass_count']} | {ind['ao_fa_count']} | "
        f"{ind['ao_fa_rate']}% | [{ind['ao_fa_ci_95'][0]}, {ind['ao_fa_ci_95'][1]}]% | {ind['hard_viol_rate']}% |",
        "",
        "## Fisher Exact Test",
        "",
        f"- Odds ratio: {fe['odds_ratio']}",
        f"- p-value: {fe['p_value']}",
        f"- Contingency: {fe['contingency']}",
        "",
        "## Per Held-out Domain",
        "",
        "| Domain | N | AO FA Count | AO FA Rate | Hard Viol Rate |",
        "|--------|---|-------------|------------|----------------|",
    ]

    for gid, dm in result.get("domain_breakdown", {}).items():
        lines.append(f"| {gid} | {dm['n']} | {dm['ao_fa_count']} | {dm['ao_fa_rate']}% | {dm['hard_viol_rate']}% |")

    lines.extend(
        [
            "",
            "## auto_numbers",
            "",
        ]
    )
    for k, v in result.get("auto_numbers", {}).items():
        lines.append(f"- `\\{k}` = {v}")

    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    result = run_analysis()

    # Save JSON
    out_json = OUTPUT_DIR / "heldout_ao_fa.json"
    out_json.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    print(f"\nSaved: {out_json}")

    # Save Markdown
    md = generate_markdown(result)
    out_md = OUTPUT_DIR / "heldout_ao_fa.md"
    out_md.write_text(md)
    print(f"Saved: {out_md}")

    # Print summary
    ho = result["held_out"]
    ind = result["in_domain"]
    fe = result["fisher_exact"]
    print("\n=== Results ===")
    print(f"Held-out AO FA: {ho['ao_fa_rate']}% ({ho['ao_fa_count']}/{ho['n']})")
    print(f"In-domain AO FA: {ind['ao_fa_rate']}% ({ind['ao_fa_count']}/{ind['n']})")
    print(f"Fisher p = {fe['p_value']}")
    print("\nauto_numbers:")
    for k, v in result["auto_numbers"].items():
        print(f"  \\{k}{{{v}}}")
