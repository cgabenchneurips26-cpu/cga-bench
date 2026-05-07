"""Round-trip fidelity verification — does the rule-based loader preserve
every semantic field of each existing hand-crafted CPG YAML?

Pipeline per graph:
    original.yaml  →  original.json (format conversion, byte-level)
                   →  parsed_json_loader.load_and_normalize
                   →  regenerated dict
                   →  per-node, per-field comparison against original

Reports:
    - evidence_pack/round_trip_v1/fidelity_results.json   (raw, per-field)
    - evidence_pack/round_trip_v1/fidelity_summary.md     (human summary)
    - stdout: one-line verdict (overall fidelity %, exit code 0 if >= 0.95)

Usage:
    PYTHONPATH=. python scripts/verify/round_trip_fidelity.py
    PYTHONPATH=. python scripts/verify/round_trip_fidelity.py --graphs-dir cpg_model/graphs
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import json
from pathlib import Path
import sys
from typing import Any

import yaml

from cga_bench.semantic_layer.parsed_json_loader import load_and_normalize

# Fields on each node that we consider "semantic payload" — a round-trip
# mismatch here would indicate the loader is dropping or mutating meaning.
COMPARE_FIELDS: tuple[str, ...] = (
    "mandatory_actions",
    "allowed_actions",
    "forbidden_actions",
    "deadlines",
    "required_prior_actions",
    "next_nodes",
    "conditional_next",
    "recommendation_class",
    "evidence_level",
    "source_guideline",
    "source_section",
    "source_quote",
    "source_page",
    "precondition",
    "node_type",
    "name",
)

LIST_FIELDS: frozenset[str] = frozenset({"mandatory_actions", "allowed_actions", "forbidden_actions", "next_nodes"})
DICT_FIELDS: frozenset[str] = frozenset({"deadlines", "required_prior_actions", "conditional_next"})

FIDELITY_TARGET = 0.95


def _normalise_for_compare(value: Any, field: str) -> Any:
    """Normalise None → empty container of the expected type so that absent-vs-empty
    does not count as a mismatch. Lists are order-insensitive (semantic set).
    """
    if field in LIST_FIELDS:
        if value is None:
            return []
        return sorted(list(value))
    if field in DICT_FIELDS:
        if value is None:
            return {}
        return dict(value)
    return value


def compare_node(orig: dict[str, Any], regen: dict[str, Any]) -> dict[str, Any]:
    """Per-field diff. Each value is either 'match' or a {orig, regen} dict."""
    out: dict[str, Any] = {}
    for f in COMPARE_FIELDS:
        o = _normalise_for_compare(orig.get(f), f)
        r = _normalise_for_compare(regen.get(f), f)
        if o == r:
            out[f] = "match"
        else:
            out[f] = {"orig": o, "regen": r}
    return out


def audit_one_graph(yaml_path: Path, tmp_dir: Path) -> dict[str, Any]:
    """Round-trip one graph and return per-node diff + counts."""
    orig_data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
    js_path = tmp_dir / f"{yaml_path.stem}.json"
    js_path.write_text(json.dumps(orig_data, ensure_ascii=False, indent=2))

    try:
        result = load_and_normalize(js_path)
    except Exception as exc:
        return {
            "status": "loader_error",
            "error": str(exc),
            "node_count": 0,
            "field_total": 0,
            "field_match": 0,
        }

    regen_data = result.data
    orig_nodes = orig_data.get("nodes", {}) or {}
    regen_nodes = regen_data.get("nodes", {}) or {}

    per_node: dict[str, dict[str, Any]] = {}
    total_fields = 0
    match_fields = 0
    mismatched_fields: list[str] = []

    # Node-set comparison
    missing_in_regen = sorted(set(orig_nodes) - set(regen_nodes))
    extra_in_regen = sorted(set(regen_nodes) - set(orig_nodes))

    for nid, orig_node in orig_nodes.items():
        regen_node = regen_nodes.get(nid, {})
        diff = compare_node(orig_node, regen_node)
        per_node[nid] = diff
        for fname, res in diff.items():
            total_fields += 1
            if res == "match":
                match_fields += 1
            else:
                mismatched_fields.append(f"{nid}.{fname}")

    return {
        "status": "ok",
        "node_count": len(orig_nodes),
        "missing_in_regen": missing_in_regen,
        "extra_in_regen": extra_in_regen,
        "field_total": total_fields,
        "field_match": match_fields,
        "mismatched_fields": mismatched_fields,
        "per_node": per_node,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--graphs-dir", default="cpg_model/graphs", type=Path)
    ap.add_argument("--output-dir", default="evidence_pack/round_trip_v1", type=Path)
    ap.add_argument("--tmp-dir", default=None, type=Path)
    ap.add_argument("--target", type=float, default=FIDELITY_TARGET)
    args = ap.parse_args(argv)

    graphs = sorted(args.graphs_dir.glob("*.yaml"))
    if not graphs:
        print(f"ERROR: no YAML files found in {args.graphs_dir}", file=sys.stderr)
        return 2

    tmp_dir = args.tmp_dir or Path("/tmp/round_trip_fidelity")
    tmp_dir.mkdir(parents=True, exist_ok=True)

    report: dict[str, Any] = {"graphs": {}, "by_field": defaultdict(lambda: {"total": 0, "match": 0})}
    grand_total = 0
    grand_match = 0

    for g in graphs:
        res = audit_one_graph(g, tmp_dir)
        report["graphs"][g.name] = res
        grand_total += res.get("field_total", 0)
        grand_match += res.get("field_match", 0)
        # by-field aggregation
        for node_diff in (res.get("per_node") or {}).values():
            for fname, val in node_diff.items():
                report["by_field"][fname]["total"] += 1
                if val == "match":
                    report["by_field"][fname]["match"] += 1

    # Finalise summary
    fidelity = (grand_match / grand_total) if grand_total else 0.0
    summary = {
        "graphs_audited": len(graphs),
        "field_total": grand_total,
        "field_match": grand_match,
        "fidelity_pct": round(100 * fidelity, 4),
        "target_pct": round(100 * args.target, 2),
        "pass": fidelity >= args.target,
        "per_graph_fidelity": {
            name: (
                round(100 * g_res.get("field_match", 0) / g_res["field_total"], 2) if g_res.get("field_total") else None
            )
            for name, g_res in report["graphs"].items()
        },
        "by_field_fidelity": {
            fname: {
                "total": d["total"],
                "match": d["match"],
                "pct": round(100 * d["match"] / d["total"], 2) if d["total"] else None,
            }
            for fname, d in report["by_field"].items()
        },
    }
    report["summary"] = summary
    # Defaultdict is not JSON-serialisable via json.dumps when nested under a
    # dict in certain Python builds; convert before dumping.
    report["by_field"] = dict(report["by_field"])

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "fidelity_results.json").write_text(
        json.dumps(report, indent=2, ensure_ascii=False, default=str), encoding="utf-8"
    )

    md = _render_summary_md(summary, report)
    (args.output_dir / "fidelity_summary.md").write_text(md, encoding="utf-8")

    # One-line verdict
    verdict = "PASS" if summary["pass"] else "FAIL"
    print(
        f"{verdict}: round-trip fidelity {summary['fidelity_pct']}% "
        f"({summary['field_match']}/{summary['field_total']} fields) "
        f"across {summary['graphs_audited']} graphs "
        f"— target {summary['target_pct']}%"
    )
    return 0 if summary["pass"] else 1


def _render_summary_md(summary: dict[str, Any], full: dict[str, Any]) -> str:
    lines = [
        "# Round-trip Fidelity — 25 CPG Corpus",
        "",
        "**Target**: ≥ {target}% of per-field comparisons match after "
        "`original.yaml → JSON → parsed_json_loader → regenerated`.".format(target=summary["target_pct"]),
        "",
        f"**Overall**: {summary['fidelity_pct']}% "
        f"({summary['field_match']} / {summary['field_total']} fields)  "
        f"**{('PASS' if summary['pass'] else 'FAIL')}**",
        "",
        "## Per-field fidelity",
        "",
        "| Field | Match | Total | Pct |",
        "|---|---|---|---|",
    ]
    for fname, stats in sorted(summary["by_field_fidelity"].items()):
        pct = stats["pct"]
        lines.append(f"| `{fname}` | {stats['match']} | {stats['total']} | {pct}% |")
    lines.append("")
    lines.append("## Per-graph fidelity")
    lines.append("")
    lines.append("| Graph | Pct |")
    lines.append("|---|---|")
    for gname, pct in sorted(summary["per_graph_fidelity"].items()):
        lines.append(f"| `{gname}` | {pct}% |")
    # Worst-offending fields
    worst = [(name, g["mismatched_fields"]) for name, g in full["graphs"].items() if g.get("mismatched_fields")]
    if worst:
        lines.append("")
        lines.append("## Mismatches (first 20 per graph)")
        for name, fields in worst:
            if not fields:
                continue
            lines.append(f"- **{name}** — {len(fields)} mismatches")
            for f in fields[:20]:
                lines.append(f"  - `{f}`")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":
    sys.exit(main())
