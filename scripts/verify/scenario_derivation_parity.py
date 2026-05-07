"""Scenario derivation parity — does patient_generator produce the same
scenarios from loader-regenerated YAMLs as from the original hand-crafted ones?

The existing `scripts/generate_all_scenarios.py` has hardcoded paths, so we
inline its core flow (PatientGenerator + ConstraintDerivationEngine) and
parameterise on --graphs-dir.

Pipeline:
    for each of two graph dirs:
        load each YAML → ConstraintDerivationEngine → PatientGenerator (seed=42)
        collect GeneratedScenario list

    compare two scenario sets:
        - count
        - scenario_id set equality
        - per-common-id field diff (expected_actions, forbidden_actions,
          trap_scenario, guideline_graph, patient['working_diagnosis'])

Usage:
    PYTHONPATH=. python scripts/verify/scenario_derivation_parity.py \\
        --orig-dir cpg_model/graphs \\
        --regen-dir cpg_model/graphs_regen_v1
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

# Allow importing cpg_model.* when run from cga_bench/ with PYTHONPATH=. from parent
# (follows the same pattern as generate_all_scenarios.py)
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from cga_bench.cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
from cga_bench.cpg_model.patient_generator import GeneratedScenario, PatientGenerator


def generate_scenarios_from_dir(graphs_dir: Path) -> list[GeneratedScenario]:
    """Replicates generate_all_scenarios.main() flow, parameterised on dir."""
    engine = ConstraintDerivationEngine()
    generator = PatientGenerator(engine, seed=42)
    all_generated: list[GeneratedScenario] = []
    for graph_path in sorted(graphs_dir.glob("*.yaml")):
        graph = load_graph(graph_path)
        scenarios = generator.generate_from_graph(graph)
        all_generated.extend(scenarios)
    return all_generated


def scenario_to_compact(s: GeneratedScenario) -> dict[str, Any]:
    """Compact representation for parity comparison (drops non-deterministic stuff)."""
    return {
        "scenario_id": s.scenario_id,
        "guideline_graph": s.guideline_graph,
        "trap_scenario": s.trap_scenario,
        "generation_method": s.generation_method,
        "triggered_rules": sorted(list(s.triggered_rules or [])),
        "expected_actions": sorted(list(s.expected_actions or [])),
        "forbidden_actions": sorted(list(s.forbidden_actions or [])),
        "working_diagnosis": (s.patient or {}).get("working_diagnosis"),
    }


def compare_sets(orig_list: list[GeneratedScenario], regen_list: list[GeneratedScenario]) -> dict[str, Any]:
    """Return parity report dict."""
    orig_map = {s.scenario_id: scenario_to_compact(s) for s in orig_list}
    regen_map = {s.scenario_id: scenario_to_compact(s) for s in regen_list}

    orig_ids = set(orig_map)
    regen_ids = set(regen_map)

    only_in_orig = sorted(orig_ids - regen_ids)
    only_in_regen = sorted(regen_ids - orig_ids)
    common = orig_ids & regen_ids

    field_stats: dict[str, dict[str, int]] = {}
    per_field_fields = (
        "guideline_graph",
        "trap_scenario",
        "generation_method",
        "triggered_rules",
        "expected_actions",
        "forbidden_actions",
        "working_diagnosis",
    )
    for f in per_field_fields:
        field_stats[f] = {"match": 0, "mismatch": 0}

    mismatches: list[dict[str, Any]] = []
    for sid in sorted(common):
        o = orig_map[sid]
        r = regen_map[sid]
        node_mismatch: dict[str, Any] = {"scenario_id": sid, "fields": {}}
        has_any = False
        for f in per_field_fields:
            if o.get(f) == r.get(f):
                field_stats[f]["match"] += 1
            else:
                field_stats[f]["mismatch"] += 1
                node_mismatch["fields"][f] = {"orig": o.get(f), "regen": r.get(f)}
                has_any = True
        if has_any and len(mismatches) < 50:
            mismatches.append(node_mismatch)

    # Per-graph counts
    def by_graph(lst: list[GeneratedScenario]) -> dict[str, int]:
        out: dict[str, int] = {}
        for s in lst:
            out[s.guideline_graph] = out.get(s.guideline_graph, 0) + 1
        return out

    return {
        "count_orig": len(orig_list),
        "count_regen": len(regen_list),
        "count_common": len(common),
        "count_only_orig": len(only_in_orig),
        "count_only_regen": len(only_in_regen),
        "only_in_orig_sample": only_in_orig[:20],
        "only_in_regen_sample": only_in_regen[:20],
        "field_stats": field_stats,
        "mismatches_sample": mismatches,
        "by_graph_orig": by_graph(orig_list),
        "by_graph_regen": by_graph(regen_list),
    }


def _render_summary_md(parity: dict[str, Any]) -> str:
    lines = [
        "# Scenario Derivation Parity — original vs loader-regenerated YAMLs",
        "",
        f"**Original graphs** → {parity['count_orig']} scenarios",
        f"**Regenerated graphs** → {parity['count_regen']} scenarios",
        f"**Common scenario_ids** → {parity['count_common']}",
        f"**Only in original** → {parity['count_only_orig']}",
        f"**Only in regen** → {parity['count_only_regen']}",
        "",
        "## Per-field parity (over common scenario_ids)",
        "",
        "| Field | Match | Mismatch | Pct |",
        "|---|---|---|---|",
    ]
    for f, s in parity["field_stats"].items():
        total = s["match"] + s["mismatch"]
        pct = round(100 * s["match"] / total, 2) if total else None
        lines.append(f"| `{f}` | {s['match']} | {s['mismatch']} | {pct}% |")
    lines.append("")
    lines.append("## Per-graph scenario counts")
    lines.append("")
    lines.append("| Graph | Orig | Regen | Δ |")
    lines.append("|---|---|---|---|")
    all_graphs = sorted(set(parity["by_graph_orig"]) | set(parity["by_graph_regen"]))
    for g in all_graphs:
        o = parity["by_graph_orig"].get(g, 0)
        r = parity["by_graph_regen"].get(g, 0)
        lines.append(f"| `{g}` | {o} | {r} | {r - o} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--orig-dir", default="cpg_model/graphs", type=Path)
    ap.add_argument("--regen-dir", default="cpg_model/graphs_regen_v1", type=Path)
    ap.add_argument("--output-dir", default="evidence_pack/round_trip_v1", type=Path)
    args = ap.parse_args(argv)

    if not args.orig_dir.is_dir():
        print(f"ERROR: --orig-dir not found: {args.orig_dir}", file=sys.stderr)
        return 2
    if not args.regen_dir.is_dir():
        print(f"ERROR: --regen-dir not found: {args.regen_dir}", file=sys.stderr)
        return 2

    print(f"[1/2] Generating from original: {args.orig_dir} ...", flush=True)
    orig_scens = generate_scenarios_from_dir(args.orig_dir)
    print(f"      → {len(orig_scens)} scenarios", flush=True)

    print(f"[2/2] Generating from regen:    {args.regen_dir} ...", flush=True)
    regen_scens = generate_scenarios_from_dir(args.regen_dir)
    print(f"      → {len(regen_scens)} scenarios", flush=True)

    parity = compare_sets(orig_scens, regen_scens)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "scenario_parity_results.json").write_text(
        json.dumps(parity, indent=2, ensure_ascii=False, default=str),
        encoding="utf-8",
    )
    (args.output_dir / "scenario_parity_summary.md").write_text(_render_summary_md(parity), encoding="utf-8")

    # Verdict: exact parity required (id-set equal + zero mismatches)
    id_parity = parity["count_only_orig"] == 0 and parity["count_only_regen"] == 0
    field_parity = all(s["mismatch"] == 0 for s in parity["field_stats"].values())
    verdict = "PASS" if (id_parity and field_parity) else "FAIL"
    print(
        f"{verdict}: orig={parity['count_orig']} regen={parity['count_regen']} "
        f"common={parity['count_common']} "
        f"only_orig={parity['count_only_orig']} only_regen={parity['count_only_regen']} "
        f"field_mismatches={sum(s['mismatch'] for s in parity['field_stats'].values())}"
    )
    return 0 if verdict == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
