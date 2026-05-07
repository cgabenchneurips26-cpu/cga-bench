"""Clinician Review Packet Generator for v7 CPG Expansion.

Produces human-readable Markdown + structured CSV for clinician sign-off
on auto-generated CPG graph YAMLs.  Covers the full graph structure:
mandatory/forbidden actions, deadlines, conditional rules, and branching.

Usage:
    # Single graph
    PYTHONPATH=.. python scripts/generate_review_packet.py \
        --graph cpg_model/graphs/auto/test_sepsis_mini.yaml

    # Batch: all graphs in a directory
    PYTHONPATH=.. python scripts/generate_review_packet.py \
        --graphs-dir cpg_model/graphs/auto/

    # With comparison to hand-crafted gold standard
    PYTHONPATH=.. python scripts/generate_review_packet.py \
        --graphs-dir cpg_model/graphs/auto/ \
        --compare-dir cpg_model/graphs/

    # CSV-only output
    PYTHONPATH=.. python scripts/generate_review_packet.py \
        --graphs-dir cpg_model/graphs/auto/ --format csv
"""

from __future__ import annotations

import argparse
import csv
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("generate_review_packet")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "evidence_pack" / "clinician_review"


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------


def _load_graph(path: Path) -> dict[str, Any]:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def _node_summary(node: dict[str, Any]) -> dict[str, Any]:
    """Extract review-relevant fields from a node."""
    return {
        "node_id": node.get("node_id", "?"),
        "name": node.get("name", "?"),
        "node_type": node.get("node_type", "?"),
        "mandatory": node.get("mandatory_actions", []),
        "allowed": node.get("allowed_actions", []),
        "forbidden": node.get("forbidden_actions", []),
        "deadlines": node.get("deadlines", {}),
        "next_nodes": node.get("next_nodes", []),
        "conditional_next": node.get("conditional_next", {}),
        "conditional_rules": node.get("conditional_rules", []),
        "source_guideline": node.get("source_guideline", ""),
        "source_section": node.get("source_section", ""),
    }


# ---------------------------------------------------------------------------
# Markdown generation
# ---------------------------------------------------------------------------


def _generate_markdown(graph: dict[str, Any], graph_path: Path, compare_graph: dict[str, Any] | None = None) -> str:
    """Generate a Markdown review packet for one CPG graph."""
    lines: list[str] = []
    graph_id = graph.get("graph_id", graph_path.stem)
    guideline = graph.get("guideline_name", graph_id)
    nodes = graph.get("nodes", {})

    # Header
    lines.append(f"# Clinician Review: {guideline}")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append(f"| Graph ID | `{graph_id}` |")
    lines.append(f"| Source | {graph.get('source_guideline', 'N/A')} |")
    lines.append(f"| Version | {graph.get('version', 'N/A')} |")
    lines.append(f"| Entry Node | `{graph.get('entry_node', 'N/A')}` |")
    lines.append(f"| Total Nodes | {len(nodes)} |")
    n_mandatory = sum(len(n.get("mandatory_actions", [])) for n in nodes.values())
    n_forbidden = sum(len(n.get("forbidden_actions", [])) for n in nodes.values())
    n_rules = sum(len(n.get("conditional_rules", [])) for n in nodes.values())
    lines.append(f"| Total Mandatory Actions | {n_mandatory} |")
    lines.append(f"| Total Forbidden Actions | {n_forbidden} |")
    lines.append(f"| Total Conditional Rules | {n_rules} |")
    lines.append("")

    # Comparison summary (if available)
    if compare_graph:
        lines.append("## Comparison with Hand-Crafted Graph")
        lines.append("")
        c_nodes = compare_graph.get("nodes", {})
        c_mandatory = sum(len(n.get("mandatory_actions", [])) for n in c_nodes.values())
        c_forbidden = sum(len(n.get("forbidden_actions", [])) for n in c_nodes.values())
        c_rules = sum(len(n.get("conditional_rules", [])) for n in c_nodes.values())
        lines.append("| Metric | Auto-Generated | Hand-Crafted | Delta |")
        lines.append("|--------|---------------|--------------|-------|")
        lines.append(f"| Nodes | {len(nodes)} | {len(c_nodes)} | {len(nodes) - len(c_nodes):+d} |")
        lines.append(f"| Mandatory | {n_mandatory} | {c_mandatory} | {n_mandatory - c_mandatory:+d} |")
        lines.append(f"| Forbidden | {n_forbidden} | {c_forbidden} | {n_forbidden - c_forbidden:+d} |")
        lines.append(f"| Conditional Rules | {n_rules} | {c_rules} | {n_rules - c_rules:+d} |")

        # Action-level diff
        auto_mand = set()
        gold_mand = set()
        for n in nodes.values():
            auto_mand.update(n.get("mandatory_actions", []))
        for n in c_nodes.values():
            gold_mand.update(n.get("mandatory_actions", []))
        added = auto_mand - gold_mand
        removed = gold_mand - auto_mand
        if added:
            lines.append(f"| Mandatory Added | {len(added)} | — | `{'`, `'.join(sorted(added))}` |")
        if removed:
            lines.append(f"| Mandatory Missing | — | {len(removed)} | `{'`, `'.join(sorted(removed))}` |")
        lines.append("")

    # Per-node review
    lines.append("## Node-by-Node Review")
    lines.append("")

    for nid, node_data in nodes.items():
        ns = _node_summary(node_data)
        lines.append(f"### Node: `{nid}` — {ns['name']}")
        lines.append("")
        lines.append(f"- **Type**: {ns['node_type']}")
        lines.append(f"- **Source**: {ns['source_guideline']} / {ns['source_section']}")
        lines.append(f"- **Next**: {', '.join(f'`{n}`' for n in ns['next_nodes']) or '(terminal)'}")
        lines.append("")

        # Mandatory actions
        if ns["mandatory"]:
            lines.append("**Mandatory Actions** (clinician: verify completeness)")
            lines.append("")
            for i, act in enumerate(ns["mandatory"], 1):
                deadline = ns["deadlines"].get(act, "—")
                deadline_str = f" (deadline: {deadline} min)" if deadline != "—" else ""
                lines.append(f"{i}. `{act}`{deadline_str}")
                lines.append("   - [ ] Correct  [ ] Should remove  [ ] Missing prerequisite")
            lines.append("")

        # Forbidden actions
        if ns["forbidden"]:
            lines.append("**Forbidden Actions** (clinician: verify contraindications)")
            lines.append("")
            for act in ns["forbidden"]:
                lines.append(f"- `{act}`")
                lines.append("  - [ ] Correct contraindication  [ ] Should NOT be forbidden")
            lines.append("")

        # Conditional rules
        if ns["conditional_rules"]:
            lines.append("**Conditional Rules** (clinician: verify safety logic)")
            lines.append("")
            for rule in ns["conditional_rules"]:
                rid = rule.get("rule_id", "?")
                cond = rule.get("condition", "?")
                effect = rule.get("effect", {})
                severity = rule.get("severity", "?")
                desc = rule.get("description", "")
                actions = ", ".join(f"`{a}`" for a in effect.get("actions", []))
                lines.append(f"- **{rid}** [{severity}]: `{cond}`")
                lines.append(f"  - Effect: {effect.get('type', '?')} {actions}")
                if desc:
                    lines.append(f"  - Description: {desc}")
                lines.append("  - [ ] Correct  [ ] Incorrect  [ ] Needs modification")
            lines.append("")

        # Conditional next
        if ns["conditional_next"]:
            lines.append("**Branching Logic**")
            lines.append("")
            for cond, target in ns["conditional_next"].items():
                lines.append(f"- `{cond}` → `{target}`")
            lines.append("  - [ ] Branching correct  [ ] Needs revision")
            lines.append("")

    # Sign-off section
    lines.append("---")
    lines.append("")
    lines.append("## Clinician Sign-off")
    lines.append("")
    lines.append("| Field | Value |")
    lines.append("|-------|-------|")
    lines.append("| Reviewer Name | |")
    lines.append("| Specialty | |")
    lines.append("| Date | |")
    lines.append(f"| Graph Reviewed | `{graph_id}` |")
    lines.append("| Overall Verdict | [ ] Approved  [ ] Approved with changes  [ ] Rejected |")
    lines.append("| Comments | |")
    lines.append("")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CSV generation
# ---------------------------------------------------------------------------


def _generate_csv_rows(graph: dict[str, Any], graph_path: Path) -> list[dict[str, str]]:
    """Generate flat CSV rows for structured review data collection."""
    rows: list[dict[str, str]] = []
    graph_id = graph.get("graph_id", graph_path.stem)
    guideline = graph.get("guideline_name", graph_id)

    for nid, node_data in graph.get("nodes", {}).items():
        ns = _node_summary(node_data)

        # Mandatory action rows
        for act in ns["mandatory"]:
            deadline = ns["deadlines"].get(act, "")
            rows.append(
                {
                    "graph_id": graph_id,
                    "guideline": guideline,
                    "node_id": nid,
                    "node_name": ns["name"],
                    "item_type": "mandatory_action",
                    "item_id": act,
                    "deadline_min": str(deadline) if deadline else "",
                    "severity": "",
                    "condition": "",
                    "effect_type": "",
                    "description": "",
                    "clinician_verdict": "",
                    "clinician_notes": "",
                }
            )

        # Forbidden action rows
        for act in ns["forbidden"]:
            rows.append(
                {
                    "graph_id": graph_id,
                    "guideline": guideline,
                    "node_id": nid,
                    "node_name": ns["name"],
                    "item_type": "forbidden_action",
                    "item_id": act,
                    "deadline_min": "",
                    "severity": "",
                    "condition": "",
                    "effect_type": "",
                    "description": "",
                    "clinician_verdict": "",
                    "clinician_notes": "",
                }
            )

        # Conditional rule rows
        for rule in ns["conditional_rules"]:
            effect = rule.get("effect", {})
            rows.append(
                {
                    "graph_id": graph_id,
                    "guideline": guideline,
                    "node_id": nid,
                    "node_name": ns["name"],
                    "item_type": "conditional_rule",
                    "item_id": rule.get("rule_id", ""),
                    "deadline_min": "",
                    "severity": rule.get("severity", ""),
                    "condition": rule.get("condition", ""),
                    "effect_type": effect.get("type", ""),
                    "description": rule.get("description", ""),
                    "clinician_verdict": "",
                    "clinician_notes": "",
                }
            )

    return rows


CSV_FIELDNAMES = [
    "graph_id",
    "guideline",
    "node_id",
    "node_name",
    "item_type",
    "item_id",
    "deadline_min",
    "severity",
    "condition",
    "effect_type",
    "description",
    "clinician_verdict",
    "clinician_notes",
]


def _write_csv(rows: list[dict[str, str]], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_argparser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    p = argparse.ArgumentParser(
        description="Generate clinician review packets for CPG graph sign-off.",
    )
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--graph", type=Path, help="Single YAML graph to review.")
    g.add_argument("--graphs-dir", type=Path, help="Directory of YAML graphs.")

    p.add_argument(
        "--compare-dir", type=Path, default=None, help="Hand-crafted graphs dir for comparison (matched by filename)."
    )
    p.add_argument("--output-dir", type=Path, default=None, help=f"Output directory (default: {DEFAULT_OUTPUT_DIR}).")
    p.add_argument(
        "--format", choices=["markdown", "csv", "both"], default="both", help="Output format (default: both)."
    )
    p.add_argument("--verbose", "-v", action="store_true")
    return p


def _find_comparison_graph(graph_path: Path, compare_dir: Path) -> dict[str, Any] | None:
    """Try to find a hand-crafted graph with the same stem."""
    candidate = compare_dir / graph_path.name
    if candidate.exists() and candidate != graph_path:
        return _load_graph(candidate)
    return None


def main(argv: list[str] | None = None) -> int:
    """Generate review packets for one or more CPG graph YAMLs."""
    args = build_argparser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    output_dir = args.output_dir or DEFAULT_OUTPUT_DIR
    output_dir.mkdir(parents=True, exist_ok=True)

    # Collect graphs
    if args.graph:
        graph_files = [args.graph]
    else:
        graph_files = sorted(args.graphs_dir.glob("*.yaml"))
        if not graph_files:
            logger.error("No .yaml files found in %s", args.graphs_dir)
            return 2

    all_csv_rows: list[dict[str, str]] = []

    for gf in graph_files:
        graph = _load_graph(gf)
        if not graph or "nodes" not in graph:
            logger.warning("Skipping %s (no nodes)", gf.name)
            continue

        graph_id = graph.get("graph_id", gf.stem)
        logger.info("Processing %s (%d nodes)", graph_id, len(graph.get("nodes", {})))

        # Optional comparison
        compare = None
        if args.compare_dir:
            compare = _find_comparison_graph(gf, args.compare_dir)
            if compare:
                logger.info("  Found comparison graph in %s", args.compare_dir)

        # Markdown
        if args.format in ("markdown", "both"):
            md = _generate_markdown(graph, gf, compare)
            md_path = output_dir / f"{graph_id}_review.md"
            md_path.write_text(md, encoding="utf-8")
            logger.info("  Wrote %s", md_path)

        # CSV rows
        if args.format in ("csv", "both"):
            rows = _generate_csv_rows(graph, gf)
            all_csv_rows.extend(rows)

    # Write combined CSV
    if args.format in ("csv", "both") and all_csv_rows:
        csv_path = output_dir / "review_items.csv"
        _write_csv(all_csv_rows, csv_path)
        logger.info("Wrote %d review items to %s", len(all_csv_rows), csv_path)

    # Summary
    logger.info("Review packets: %d graphs -> %s", len(graph_files), output_dir)
    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
