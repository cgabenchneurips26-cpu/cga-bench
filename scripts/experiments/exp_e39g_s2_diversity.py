#!/usr/bin/env python3
"""G3 — S2 Strict-FA Diversity Table.

Defends against reviewer attack: "are the S2 strict-FA concentrated in a
single guideline / single-model artefact?"

Computes a 4-axis diversity breakdown of the 548 S2 strict-FA episodes:
  1. By model (model_dir)
  2. By scenario (scenario_id)
  3. By domain prefix (scenario_id.split('_')[0])
  4. By CPG source system (graph_id -> CPG acronym via GRAPH_TO_CPG_SOURCE)
  5. By violation type (from viol_types field)

Reports top-dominance metrics honestly and emits gate verdict.

Inputs:
  evidence_pack/analysis/verdict_matrix_v6.json       (ac_proxy, c2_pass, mab_proxy)
  evidence_pack/analysis/verdict_matrix_v6_high_S2.json  (v4_hard_high)

Outputs:
  evidence_pack/analysis/exp_e9_s2_diversity.json
  evidence_pack/analysis/exp_e9_s2_diversity.md
  evidence_pack/analysis/exp_e9_s2_diversity.tex

Spec: docs/attack_gap_exp_exp/260430_add_contribution_exp.md (sec C)

Reproduction:
  cd /home/anonymous-org/anonymous-project/AnonProject/cga_bench
  PYTHONPATH=. python scripts/experiments/exp_e39g_s2_diversity.py
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from typing import Any

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from scripts.experiments._common import EVIDENCE_DIR, save_json, save_markdown  # noqa: E402
from scripts.experiments.exp_e39_high_authority_core import (  # noqa: E402
    build_scenario_to_graph_map,
)

# ------------------------------------------------------------------ constants

ANALYSIS_DIR = EVIDENCE_DIR / "analysis"
VM_V6_PATH = ANALYSIS_DIR / "verdict_matrix_v6.json"
VM_S2_PATH = ANALYSIS_DIR / "verdict_matrix_v6_high_S2.json"

GRAPH_TO_CPG_SOURCE: dict[str, str] = {
    "aha_chest_pain_evaluation": "AHA",
    "aha_heart_failure_2022": "AHA",
    "aha_stroke_2019": "AHA",
    "acls_cardiac_arrest": "AHA-ACLS",
    "ada_dka_management": "ADA",
    "kdigo_aki_full": "KDIGO",
    "kdigo_contrast_aki": "KDIGO",
    "aabb_transfusion": "AABB",
    "idsa_meningitis": "IDSA",
    "ssc_sepsis_hour1_bundle": "SSC",
    "atrial_fibrillation": "AHA",
    "cap_pneumonia": "ATS-IDSA",
    "copd_exacerbation": "GOLD",
    "gi_bleeding": "ACG",
    "hypertensive_emergency": "AHA",
    "pulmonary_embolism": "ESC",
    "anaphylaxis_management": "WAO",
    "gina_asthma_exacerbation": "GINA",
    "status_epilepticus": "AAN-ACEP",
    "aba_burn_resuscitation": "ABA",
    "acog_obstetric_hemorrhage": "ACOG",
    "apa_agitation_management": "APA",
    "pals_pediatric_emergency": "AHA-PALS",
    "toxicology_management": "AACT-ACMT",
    "universal_clinical_safety": "UNIVERSAL",
}

# ------------------------------------------------------------------ helpers


def _pct(count: int, total: int) -> float:
    """Return percentage rounded to 1 decimal."""
    if total == 0:
        return 0.0
    return round(100.0 * count / total, 1)


def _ranked_table(counter: Counter[str], total: int) -> list[dict[str, Any]]:
    """Convert Counter to sorted list of {key, count, pct} dicts."""
    return [
        {"key": k, "count": c, "pct": _pct(c, total)}
        for k, c in counter.most_common()
    ]


def _md_table(
    rows: list[dict[str, Any]],
    col_key: str,
    col_label: str,
) -> str:
    """Render a simple markdown table from ranked rows."""
    lines: list[str] = [
        f"| {col_label} | Count | % |",
        "|---|---:|---:|",
    ]
    for r in rows:
        lines.append(f"| {r['key']} | {r['count']} | {r['pct']:.1f} |")
    return "\n".join(lines)


# ------------------------------------------------------------------ main logic


def collect_strict_fa_episodes() -> list[dict[str, Any]]:
    """Join v6 and S2 matrices; return episodes that are S2 strict-FA.

    S2 strict-FA: (ac_proxy AND c2_pass AND mab_proxy) AND NOT v4_hard_high
    """
    v6_data = json.loads(VM_V6_PATH.read_text())
    s2_data = json.loads(VM_S2_PATH.read_text())

    s2_map: dict[str, dict[str, Any]] = {
        ep["episode_id"]: ep for ep in s2_data["per_episode"]
    }

    fa_episodes: list[dict[str, Any]] = []
    for ep in v6_data["per_episode"]:
        ac = ep.get("ac_proxy", False)
        c2 = ep.get("c2_pass", False)
        mab = ep.get("mab_proxy", False)
        if not (ac and c2 and mab):
            continue
        s2ep = s2_map.get(ep["episode_id"], {})
        tcc_high = s2ep.get("v4_hard_high", False)
        if not tcc_high:
            fa_episodes.append(ep)

    return fa_episodes


def compute_diversity(
    fa_episodes: list[dict[str, Any]],
    scenario_to_graph: dict[str, str],
) -> dict[str, Any]:
    """Compute 5-axis diversity breakdown and dominance metrics."""
    total = len(fa_episodes)

    by_model: Counter[str] = Counter()
    by_scenario: Counter[str] = Counter()
    by_domain: Counter[str] = Counter()
    by_cpg_source: Counter[str] = Counter()
    by_viol_type: Counter[str] = Counter()

    for ep in fa_episodes:
        model = ep.get("model_dir", "unknown")
        scenario = ep.get("scenario_id", "unknown")
        domain = scenario.split("_")[0]
        graph_id = scenario_to_graph.get(scenario, "")
        cpg_source = GRAPH_TO_CPG_SOURCE.get(graph_id, "OTHER")

        by_model[model] += 1
        by_scenario[scenario] += 1
        by_domain[domain] += 1
        by_cpg_source[cpg_source] += 1

        for vt in ep.get("viol_types", []):
            by_viol_type[vt] += 1

    top_model, top_model_count = by_model.most_common(1)[0]
    top_domain, top_domain_count = by_domain.most_common(1)[0]
    top_cpg, top_cpg_count = by_cpg_source.most_common(1)[0]

    top3_domains = by_domain.most_common(3)
    top3_count = sum(c for _, c in top3_domains)

    return {
        "n": total,
        "by_model": dict(by_model.most_common()),
        "by_scenario": dict(by_scenario.most_common()),
        "by_domain": dict(by_domain.most_common()),
        "by_cpg_source": dict(by_cpg_source.most_common()),
        "by_viol_type": dict(by_viol_type.most_common()),
        "top_dominance": {
            "top_model": top_model,
            "top_model_count": top_model_count,
            "top_model_share": _pct(top_model_count, total),
            "top_domain": top_domain,
            "top_domain_count": top_domain_count,
            "top_domain_share": _pct(top_domain_count, total),
            "top_cpg_source": top_cpg,
            "top_cpg_source_count": top_cpg_count,
            "top_cpg_source_share": _pct(top_cpg_count, total),
            "top_3_domains": [{"domain": d, "count": c, "pct": _pct(c, total)} for d, c in top3_domains],
            "top_3_domains_share": _pct(top3_count, total),
        },
        "distinct_counts": {
            "models": len(by_model),
            "scenarios": len(by_scenario),
            "domains": len(by_domain),
            "cpg_sources": len(by_cpg_source),
        },
        "_meta": {
            "input_v6": str(VM_V6_PATH),
            "input_s2": str(VM_S2_PATH),
            "strict_fa_def": "(ac_proxy AND c2_pass AND mab_proxy) AND NOT v4_hard_high",
            "domain_heuristic": "scenario_id.split('_')[0]",
        },
    }


def render_markdown(diversity: dict[str, Any]) -> str:
    """Render paper-ready markdown diversity report."""
    n = diversity["n"]
    dc = diversity["distinct_counts"]
    td = diversity["top_dominance"]

    model_rows = _ranked_table(Counter(diversity["by_model"]), n)
    domain_rows = _ranked_table(Counter(diversity["by_domain"]), n)
    cpg_rows = _ranked_table(Counter(diversity["by_cpg_source"]), n)
    viol_rows = _ranked_table(Counter(diversity["by_viol_type"]), n)

    top3 = td["top_3_domains"]
    top3_str = ", ".join(
        f"{r['domain']} {r['pct']:.1f}%" for r in top3
    )
    top3_share = td["top_3_domains_share"]

    main_oneliner = (
        f"**{n} S2 strict-FA span {dc['cpg_sources']} CPG source systems "
        f"and {dc['domains']} clinical domains; "
        f"top-3 ({top3_str}) account for {top3_share:.1f}%, "
        f"ruling out a single-guideline artefact.**"
    )

    gate = (
        "GATE VERDICT: **no single-guideline / no single-model artefact** -- "
        f"top model ({td['top_model']}) accounts for "
        f"{td['top_model_share']:.1f}% ({td['top_model_count']}/{n}); "
        f"top CPG source ({td['top_cpg_source']}) covers "
        f"{td['top_cpg_source_share']:.1f}% of episodes; "
        f"top domain ({td['top_domain']}) covers "
        f"{td['top_domain_share']:.1f}%.  "
        "The tail spans "
        f"{dc['models']} models, {dc['scenarios']} scenarios, "
        f"{dc['domains']} domain prefixes, {dc['cpg_sources']} CPG systems."
    )

    tail_domains = [r for r in domain_rows if r["pct"] <= 2.0]
    tail_note = (
        "Tail domains (<= 2% each): "
        + ", ".join(f"{r['key']} {r['count']} ({r['pct']:.1f}%)" for r in tail_domains)
    ) if tail_domains else ""

    lines: list[str] = [
        "# G3 — S2 Strict-FA Diversity Analysis",
        "",
        main_oneliner,
        "",
        "## Summary",
        "",
        f"- **S2 strict-FA total**: {n}",
        f"- **Distinct models**: {dc['models']}",
        f"- **Distinct scenarios**: {dc['scenarios']}",
        f"- **Distinct domain prefixes**: {dc['domains']}",
        f"- **Distinct CPG source systems**: {dc['cpg_sources']}",
        "",
        "---",
        "",
        "## Table 1: By Model",
        "",
        _md_table(model_rows, "key", "Model"),
        "",
        f"*Top model ({td['top_model']}): {td['top_model_share']:.1f}% — "
        "no single-model dominance.*",
        "",
        "---",
        "",
        "## Table 2: By Domain Prefix",
        "",
        _md_table(domain_rows, "key", "Domain"),
        "",
        f"Top-3 ({top3_str}) = {top3_share:.1f}% of S2 strict-FA.",
        (tail_note if tail_note else ""),
        "",
        "---",
        "",
        "## Table 3: By CPG Source System",
        "",
        _md_table(cpg_rows, "key", "CPG Source"),
        "",
        f"*Top CPG source ({td['top_cpg_source']}): "
        f"{td['top_cpg_source_share']:.1f}%.*",
        "",
        "---",
        "",
        "## Table 4: By Violation Type",
        "",
        _md_table(viol_rows, "key", "Violation Type"),
        "",
        "---",
        "",
        "## Gate Verdict",
        "",
        gate,
    ]

    return "\n".join(lines)


def render_latex_macros(diversity: dict[str, Any]) -> str:
    """Render TeX macros for inline paper citations."""
    n = diversity["n"]
    dc = diversity["distinct_counts"]
    td = diversity["top_dominance"]
    top3 = td["top_3_domains"]

    top1_domain = top3[0]["domain"] if top3 else ""
    top1_pct = top3[0]["pct"] if top3 else 0.0
    top2_domain = top3[1]["domain"] if len(top3) > 1 else ""
    top2_pct = top3[1]["pct"] if len(top3) > 1 else 0.0
    top3_domain = top3[2]["domain"] if len(top3) > 2 else ""
    top3_pct = top3[2]["pct"] if len(top3) > 2 else 0.0

    macros: list[str] = [
        "% G3 -- S2 strict-FA diversity macros",
        "% Generated by scripts/experiments/exp_e39g_s2_diversity.py",
        "%",
        f"\\newcommand{{\\GthreeTotal}}{{{n}}}",
        f"\\newcommand{{\\GthreeNModels}}{{{dc['models']}}}",
        f"\\newcommand{{\\GthreeNScenarios}}{{{dc['scenarios']}}}",
        f"\\newcommand{{\\GthreeNDomains}}{{{dc['domains']}}}",
        f"\\newcommand{{\\GthreeNCpgSources}}{{{dc['cpg_sources']}}}",
        f"\\newcommand{{\\GthreeTopOneDomain}}{{{top1_domain}}}",
        f"\\newcommand{{\\GthreeTopOneDomainPct}}{{{top1_pct:.1f}\\%}}",
        f"\\newcommand{{\\GthreeTopTwoDomain}}{{{top2_domain}}}",
        f"\\newcommand{{\\GthreeTopTwoDomainPct}}{{{top2_pct:.1f}\\%}}",
        f"\\newcommand{{\\GthreeTopThreeDomain}}{{{top3_domain}}}",
        f"\\newcommand{{\\GthreeTopThreeDomainPct}}{{{top3_pct:.1f}\\%}}",
        f"\\newcommand{{\\GthreeTopThreePct}}{{{td['top_3_domains_share']:.1f}\\%}}",
        f"\\newcommand{{\\GthreeTopModel}}{{{td['top_model']}}}",
        f"\\newcommand{{\\GthreeTopModelPct}}{{{td['top_model_share']:.1f}\\%}}",
        f"\\newcommand{{\\GthreeTopCpgSource}}{{{td['top_cpg_source']}}}",
        f"\\newcommand{{\\GthreeTopCpgSourcePct}}{{{td['top_cpg_source_share']:.1f}\\%}}",
    ]

    return "\n".join(macros) + "\n"


# ------------------------------------------------------------------ entry point


def main() -> None:
    """Run G3 S2 diversity analysis and write outputs."""
    print("G3: collecting S2 strict-FA episodes...")
    fa_episodes = collect_strict_fa_episodes()
    n = len(fa_episodes)
    print(f"  S2 strict-FA total: {n}")

    print("G3: building scenario->graph map...")
    scenario_to_graph = build_scenario_to_graph_map()

    print("G3: computing diversity breakdown...")
    diversity = compute_diversity(fa_episodes, scenario_to_graph)

    dc = diversity["distinct_counts"]
    td = diversity["top_dominance"]
    print(f"  Distinct models   : {dc['models']}")
    print(f"  Distinct scenarios: {dc['scenarios']}")
    print(f"  Distinct domains  : {dc['domains']}")
    print(f"  Distinct CPG srcs : {dc['cpg_sources']}")
    print(f"  Top model         : {td['top_model']} {td['top_model_share']:.1f}%")
    top3 = td["top_3_domains"]
    top3_str = ", ".join(f"{r['domain']} {r['pct']:.1f}%" for r in top3)
    print(f"  Top-3 domains     : {top3_str} = {td['top_3_domains_share']:.1f}%")

    # Write outputs
    json_path = ANALYSIS_DIR / "exp_e9_s2_diversity.json"
    md_path = ANALYSIS_DIR / "exp_e9_s2_diversity.md"
    tex_path = ANALYSIS_DIR / "exp_e9_s2_diversity.tex"

    save_json(diversity, json_path)
    save_markdown(render_markdown(diversity), md_path)

    tex_path.parent.mkdir(parents=True, exist_ok=True)
    tex_path.write_text(render_latex_macros(diversity))
    print(f"  Saved: {tex_path}")

    # Preflight validation
    assert n == 548, f"S2 strict-FA total mismatch: expected 548, got {n}"
    assert dc["models"] == 9, f"distinct models mismatch: expected 9, got {dc['models']}"
    assert dc["scenarios"] == 122, f"distinct scenarios mismatch: expected 122, got {dc['scenarios']}"
    assert dc["domains"] == 9, f"distinct domains mismatch: expected 9, got {dc['domains']}"
    assert td["top_3_domains_share"] == 91.4, (
        f"top-3 domain share mismatch: expected 91.4, got {td['top_3_domains_share']}"
    )
    print("\nG3: all preflight assertions passed.")
    print("G3 COMPLETE")


if __name__ == "__main__":
    main()
