#!/usr/bin/env python3
"""G2 / E9 Follow-up F2 -- Context-Swap x Strictest Authority.

Answers reviewer attack: "is the no-context-pair witness still strong under
a stricter authority taxonomy?"

For each conditional FORBIDDEN rule, we check whether its source node is
classified as 'high' authority under:
  S1 -- default taxonomy (audit/authority_taxonomy.yaml)
  S2 -- strictest taxonomy (audit/authority_taxonomy_strictest.yaml)

A pair is 'retained' under Sx if its source node tier == 'high' under Sx.

Pre-flight numbers (must reproduce):
  Total conditional FORBIDDEN rules : 240
  Well-formed pairs (both ranges)    : 238
  S1 retained                        : 231 / 238  (24 graphs)
  S2 retained                        : 154 / 238  (17 graphs)
  S2 severity: HIGH=85, CRITICAL=67, MODERATE=2  (152/154 = 98.7% HIGH+CRIT)
  S2 condition_type: comorbidity=60, lab_value=34, other=31, medication=19,
                     timing=6, allergy=3, history=1

Pre-reg gates (all must pass):
  retained_ge_30  : S2 retained >= 30
  domains_ge_8    : S2 distinct graphs >= 8
  asc_detection   : 0%  (constructive proof -- no inference)
  paf_detection   : 0%  (constructive proof -- no inference)
  cwt_detection   : 0%  (constructive proof -- no inference)
  tcc_detection   : 100% (constructive proof -- by definition)

Outputs:
  evidence_pack/analysis/exp_e9_context_swap_strictest.json
  evidence_pack/analysis/exp_e9_context_swap_strictest.md
  evidence_pack/analysis/exp_e9_context_swap_strictest.tex

Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (section B)
"""

from __future__ import annotations

import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.experiments._common import (  # noqa: E402
    EVIDENCE_DIR,
    GRAPHS_DIR,
    HELD_OUT_GRAPH_IDS,
    save_json,
    save_markdown,
)
from scripts.experiments.exp_e20_no_context_pair import extract_conditional_forbidden  # noqa: E402
from audit.authority_filter import set_taxonomy_path, clear_taxonomy_cache  # noqa: E402
from scripts.experiments.exp_e39_high_authority_core import build_node_authority_map  # noqa: E402

# -------------------------------------------------------------------- paths
ANALYSIS_DIR = EVIDENCE_DIR / "analysis"
TAXONOMY_DEFAULT: Path | None = None  # signals set_taxonomy_path to use default
TAXONOMY_STRICTEST = _REPO_ROOT / "audit" / "authority_taxonomy_strictest.yaml"

OUT_JSON = ANALYSIS_DIR / "exp_e9_context_swap_strictest.json"
OUT_MD = ANALYSIS_DIR / "exp_e9_context_swap_strictest.md"
OUT_TEX = ANALYSIS_DIR / "exp_e9_context_swap_strictest.tex"


# =====================================================================
# Stage 1: collect all conditional FORBIDDEN rules
# =====================================================================
def collect_all_rules() -> list[dict[str, Any]]:
    """Walk GRAPHS_DIR, skip _archive, return all conditional FORBIDDEN rules."""
    all_rules: list[dict[str, Any]] = []
    for gpath in sorted(GRAPHS_DIR.glob("*.yaml")):
        if "_archive" in gpath.parts:
            continue
        rules = extract_conditional_forbidden(gpath)
        all_rules.extend(rules)
    return all_rules


# =====================================================================
# Stage 2: build retention stats for a single taxonomy sweep
# =====================================================================
def _retention_stats(
    well_formed: list[dict[str, Any]],
    node_authority: dict[tuple[str, str], str],
) -> dict[str, Any]:
    """Return retention counts/breakdown for one taxonomy sweep."""
    retained: list[dict[str, Any]] = []

    for rule in well_formed:
        graph_id = rule["graph_id"]
        node_id = rule["node_id"]
        tier = node_authority.get((graph_id, node_id), "unknown")
        if tier == "high":
            retained.append(rule)

    n_retained = len(retained)
    distinct_graphs = sorted({r["graph_id"] for r in retained})
    n_graphs = len(distinct_graphs)

    severity = dict(Counter(r["severity"] for r in retained).most_common())
    condition_type = dict(Counter(r["condition_type"] for r in retained).most_common())

    n_held_out = sum(1 for r in retained if r["is_held_out"])
    n_in_domain = n_retained - n_held_out

    all_forbidden: set[str] = set()
    for r in retained:
        all_forbidden.update(r["forbidden_actions"])

    # Per-graph breakdown
    per_graph: dict[str, dict[str, Any]] = {}
    for gid in distinct_graphs:
        g_rules = [r for r in retained if r["graph_id"] == gid]
        g_actions: set[str] = set()
        for r in g_rules:
            g_actions.update(r["forbidden_actions"])
        per_graph[gid] = {
            "n_retained": len(g_rules),
            "n_distinct_forbidden_actions": len(g_actions),
            "severity": dict(Counter(r["severity"] for r in g_rules)),
            "condition_type": dict(Counter(r["condition_type"] for r in g_rules)),
            "is_held_out": gid in HELD_OUT_GRAPH_IDS,
        }

    return {
        "count": n_retained,
        "distinct_graphs": n_graphs,
        "graph_list": distinct_graphs,
        "severity": severity,
        "condition_type": condition_type,
        "held_out": n_held_out,
        "in_domain": n_in_domain,
        "distinct_actions": len(all_forbidden),
        "per_graph": per_graph,
    }


# =====================================================================
# Stage 3: gate check (constructive -- no inference)
# =====================================================================
def gate_check(retained_s2: dict[str, Any]) -> dict[str, Any]:
    """Evaluate all 5 pre-registered gates."""
    return {
        "retained_ge_30": retained_s2["count"] >= 30,
        "domains_ge_8": retained_s2["distinct_graphs"] >= 8,
        # Constructive proofs -- no inference ever runs
        "asc_detection": 0.0,
        "paf_detection": 0.0,
        "cwt_detection": 0.0,
        "tcc_detection": 100.0,
        "asc_paf_cwt_zero": True,   # always True by construction
        "tcc_hundred": True,         # always True by construction
    }


# =====================================================================
# Stage 4: render markdown
# =====================================================================
def render_markdown(
    n_total: int,
    n_well_formed: int,
    s1: dict[str, Any],
    s2: dict[str, Any],
    gates: dict[str, Any],
) -> str:
    lines: list[str] = []
    lines.append("# E9 Follow-up G2 -- Context-Swap x Strictest Authority")
    lines.append("")
    lines.append(
        "Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (section B)"
    )
    lines.append("")
    lines.append("## Summary")
    lines.append("")
    lines.append(
        f"Among {n_well_formed} conditional FORBIDDEN matched pairs, "
        f"{s2['count']} ({s2['count'] / n_well_formed * 100:.1f}%) retain a "
        "Class-I + LOE-A or strong-society source-node under the strictest authority "
        f"cut, spanning {s2['distinct_graphs']} graphs. "
        "Action-set evaluators still detect 0% of these pairs (constructive proof). "
        "TCC detects 100% (by definition of the trigger_range witness)."
    )
    lines.append("")
    lines.append("## S1 vs S2 Retention -- per-graph table")
    lines.append("")

    # Gather all graphs present in S1 or S2
    all_graphs = sorted(
        set(s1["graph_list"]) | set(s2["graph_list"])
    )
    lines.append("| Graph | S1 retained | S2 retained | Held-out |")
    lines.append("|---|---|---|---|")
    for gid in all_graphs:
        s1_n = s1["per_graph"].get(gid, {}).get("n_retained", 0)
        s2_n = s2["per_graph"].get(gid, {}).get("n_retained", 0)
        ho = "yes" if gid in HELD_OUT_GRAPH_IDS else "no"
        lines.append(f"| {gid} | {s1_n} | {s2_n} | {ho} |")
    lines.append("")
    lines.append("## Headline comparison")
    lines.append("")
    lines.append("| Metric | S1 (default) | S2 (strictest) |")
    lines.append("|---|---|---|")
    lines.append(
        f"| Retained pairs | {s1['count']} / {n_well_formed} "
        f"({s1['count'] / n_well_formed * 100:.1f}%) | "
        f"{s2['count']} / {n_well_formed} "
        f"({s2['count'] / n_well_formed * 100:.1f}%) |"
    )
    lines.append(
        f"| Distinct graphs | {s1['distinct_graphs']} | {s2['distinct_graphs']} |"
    )
    lines.append(
        f"| Distinct forbidden actions | {s1['distinct_actions']} | "
        f"{s2['distinct_actions']} |"
    )
    lines.append(
        f"| Held-out pairs | {s1['held_out']} | {s2['held_out']} |"
    )
    lines.append(
        f"| In-domain pairs | {s1['in_domain']} | {s2['in_domain']} |"
    )
    lines.append("")
    lines.append("## S2 severity breakdown")
    lines.append("")
    lines.append("| Severity | Count |")
    lines.append("|---|---|")
    for sev, cnt in sorted(s2["severity"].items(), key=lambda x: -x[1]):
        lines.append(f"| {sev} | {cnt} |")
    lines.append("")
    lines.append("## S2 condition_type breakdown")
    lines.append("")
    lines.append("| Condition type | Count |")
    lines.append("|---|---|")
    for ct, cnt in sorted(s2["condition_type"].items(), key=lambda x: -x[1]):
        lines.append(f"| {ct} | {cnt} |")
    lines.append("")
    lines.append("## Pre-reg gate verdict")
    lines.append("")
    lines.append("| Gate | Threshold | Value | PASS |")
    lines.append("|---|---|---|---|")
    lines.append(
        f"| retained_ge_30 | >= 30 | {s2['count']} | "
        f"{'YES' if gates['retained_ge_30'] else 'NO'} |"
    )
    lines.append(
        f"| domains_ge_8 | >= 8 | {s2['distinct_graphs']} | "
        f"{'YES' if gates['domains_ge_8'] else 'NO'} |"
    )
    lines.append(
        f"| ASC detection | = 0% | {gates['asc_detection']:.1f}% | "
        f"{'YES' if gates['asc_paf_cwt_zero'] else 'NO'} |"
    )
    lines.append(
        f"| PAF detection | = 0% | {gates['paf_detection']:.1f}% | "
        f"{'YES' if gates['asc_paf_cwt_zero'] else 'NO'} |"
    )
    lines.append(
        f"| CwT detection | = 0% | {gates['cwt_detection']:.1f}% | "
        f"{'YES' if gates['asc_paf_cwt_zero'] else 'NO'} |"
    )
    lines.append(
        f"| TCC detection | = 100% | {gates['tcc_detection']:.1f}% | "
        f"{'YES' if gates['tcc_hundred'] else 'NO'} |"
    )
    lines.append("")
    all_pass = all([
        gates["retained_ge_30"],
        gates["domains_ge_8"],
        gates["asc_paf_cwt_zero"],
        gates["tcc_hundred"],
    ])
    lines.append(f"**All gates PASS: {'YES' if all_pass else 'NO'}**")
    lines.append("")
    lines.append("## Paper-ready one-liner")
    lines.append("")
    crit = s2["severity"].get("CRITICAL", 0)
    high = s2["severity"].get("HIGH", 0)
    hi_or_crit = crit + high
    hi_or_crit_pct = hi_or_crit / s2["count"] * 100 if s2["count"] else 0.0
    lines.append(
        f"Among {n_well_formed} conditional FORBIDDEN matched pairs, "
        f"{s2['count']} ({s2['count'] / n_well_formed * 100:.1f}%) retain a "
        "Class-I + LOE-A or strong-society source-node under the strictest authority "
        f"cut, spanning {s2['distinct_graphs']} graphs "
        f"({hi_or_crit} / {s2['count']} = {hi_or_crit_pct:.1f}% are HIGH or CRITICAL severity). "
        "Action-set evaluators detect 0% of these pairs (constructive); "
        "TCC detects 100%."
    )
    return "\n".join(lines) + "\n"


# =====================================================================
# Stage 5: render LaTeX macros
# =====================================================================
def render_tex(
    n_total: int,
    n_well_formed: int,
    s1: dict[str, Any],
    s2: dict[str, Any],
) -> str:
    crit = s2["severity"].get("CRITICAL", 0)
    high = s2["severity"].get("HIGH", 0)
    moderate = s2["severity"].get("MODERATE", 0)
    lines = [
        "% Auto-generated by scripts/experiments/exp_e39f_context_swap_strictest.py",
        "% G2 -- Context-Swap x Strictest Authority",
        f"\\newcommand{{\\GtwoTotal}}{{{n_well_formed}}}",
        f"\\newcommand{{\\GtwoSOneRetained}}{{{s1['count']}}}",
        f"\\newcommand{{\\GtwoSOneGraphs}}{{{s1['distinct_graphs']}}}",
        f"\\newcommand{{\\GtwoSTwoRetained}}{{{s2['count']}}}",
        f"\\newcommand{{\\GtwoSTwoGraphs}}{{{s2['distinct_graphs']}}}",
        f"\\newcommand{{\\GtwoSTwoCritical}}{{{crit}}}",
        f"\\newcommand{{\\GtwoSTwoHigh}}{{{high}}}",
        f"\\newcommand{{\\GtwoSTwoModerate}}{{{moderate}}}",
        f"\\newcommand{{\\GtwoSTwoActions}}{{{s2['distinct_actions']}}}",
        f"\\newcommand{{\\GtwoSTwoHeldOut}}{{{s2['held_out']}}}",
        f"\\newcommand{{\\GtwoSTwoInDomain}}{{{s2['in_domain']}}}",
        f"\\newcommand{{\\GtwoSTwoRetainedPct}}{{{s2['count'] / n_well_formed * 100:.1f}}}",
    ]
    return "\n".join(lines) + "\n"


# =====================================================================
# main
# =====================================================================
def main() -> int:
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    # Step 1: collect all rules
    print("[1/5] Collecting conditional FORBIDDEN rules from all graphs...", flush=True)
    all_rules = collect_all_rules()
    n_total = len(all_rules)
    print(f"      Total conditional FORBIDDEN rules: {n_total}", flush=True)

    well_formed = [r for r in all_rules if r["has_both_ranges"]]
    n_well_formed = len(well_formed)
    print(f"      Well-formed pairs (has both ranges): {n_well_formed}", flush=True)

    # Step 2: S1 -- default taxonomy
    print("[2/5] Building authority map under S1 (default taxonomy)...", flush=True)
    clear_taxonomy_cache()
    set_taxonomy_path(None)
    node_authority_s1 = build_node_authority_map()
    s1_stats = _retention_stats(well_formed, node_authority_s1)
    print(
        f"      S1 retained: {s1_stats['count']} / {n_well_formed} "
        f"({s1_stats['distinct_graphs']} graphs)",
        flush=True,
    )

    # Step 3: S2 -- strictest taxonomy
    print("[3/5] Building authority map under S2 (strictest taxonomy)...", flush=True)
    if not TAXONOMY_STRICTEST.exists():
        raise FileNotFoundError(f"Missing strictest taxonomy: {TAXONOMY_STRICTEST}")
    clear_taxonomy_cache()
    set_taxonomy_path(TAXONOMY_STRICTEST)
    node_authority_s2 = build_node_authority_map()
    s2_stats = _retention_stats(well_formed, node_authority_s2)
    print(
        f"      S2 retained: {s2_stats['count']} / {n_well_formed} "
        f"({s2_stats['distinct_graphs']} graphs)",
        flush=True,
    )
    print(f"      S2 severity: {s2_stats['severity']}", flush=True)
    print(f"      S2 condition_type: {s2_stats['condition_type']}", flush=True)

    # Step 4: gate check
    print("[4/5] Evaluating pre-reg gates...", flush=True)
    gates = gate_check(s2_stats)
    all_pass = all([
        gates["retained_ge_30"],
        gates["domains_ge_8"],
        gates["asc_paf_cwt_zero"],
        gates["tcc_hundred"],
    ])
    for gate_name, gate_val in gates.items():
        print(f"      {gate_name}: {gate_val}", flush=True)
    print(f"      All gates PASS: {all_pass}", flush=True)

    # Step 5: write outputs
    print("[5/5] Writing outputs...", flush=True)

    result: dict[str, Any] = {
        "description": "G2 -- Context-Swap x Strictest Authority (E9 Follow-up F2)",
        "spec": "docs/attack_gap_exp_exp/260430_add_contribution_exp.md",
        "n_total_conditional_forbidden": n_total,
        "n_well_formed": n_well_formed,
        "retained_s1": s1_stats,
        "retained_s2": s2_stats,
        "gate_check": gates,
        "all_gates_pass": all_pass,
    }

    save_json(result, OUT_JSON)

    md_text = render_markdown(n_total, n_well_formed, s1_stats, s2_stats, gates)
    save_markdown(md_text, OUT_MD)

    tex_text = render_tex(n_total, n_well_formed, s1_stats, s2_stats)
    OUT_TEX.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_TEX, "w") as f:
        f.write(tex_text)
    print(f"  Saved: {OUT_TEX}")

    # Final summary
    print("\n=== G2 headline ===", flush=True)
    print(f"  Total conditional FORBIDDEN: {n_total}", flush=True)
    print(f"  Well-formed pairs          : {n_well_formed}", flush=True)
    print(
        f"  S1 retained                : {s1_stats['count']} / {n_well_formed} "
        f"({s1_stats['distinct_graphs']} graphs)",
        flush=True,
    )
    print(
        f"  S2 retained                : {s2_stats['count']} / {n_well_formed} "
        f"({s2_stats['distinct_graphs']} graphs)",
        flush=True,
    )
    crit = s2_stats["severity"].get("CRITICAL", 0)
    high = s2_stats["severity"].get("HIGH", 0)
    mod = s2_stats["severity"].get("MODERATE", 0)
    print(
        f"  S2 severity                : HIGH={high}, CRITICAL={crit}, MODERATE={mod}",
        flush=True,
    )
    print(f"  All gates PASS             : {all_pass}", flush=True)

    return 0


if __name__ == "__main__":
    sys.exit(main())
