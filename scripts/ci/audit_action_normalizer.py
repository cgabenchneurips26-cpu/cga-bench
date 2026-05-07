"""ActionNormalizer canonical-form audit across all CPG graphs.

Extracts every action_id token from 25 CPG graphs, runs through
ActionNormalizer, and reports:
  (a) unmapped actions (normalize to self)
  (b) canonical groups (multiple raw IDs → same canonical)
  (c) potential conflict blindspots (same canonical in mandatory + forbidden
      of different nodes)

Usage:
    PYTHONPATH=/home/anonymous-org/anonymous-project/AnonProject \
        python cga_bench/scripts/ci/audit_action_normalizer.py
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import sys

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))

from cga_bench.assessor_core.action_normalizer import ActionNormalizer  # noqa: E402


def _extract_actions_from_graph(graph_data: dict) -> dict:
    """Extract all action tokens from a graph, categorised by source.

    Returns dict with keys: mandatory, forbidden, allowed, conditional_req,
    conditional_forb, deadline_keys — each a set of (node_id, action_id).
    """
    result: dict[str, set[tuple[str, str]]] = {
        "mandatory": set(),
        "forbidden": set(),
        "allowed": set(),
        "conditional_req": set(),
        "conditional_forb": set(),
        "deadline_keys": set(),
    }
    for node_id, node in graph_data.get("nodes", {}).items():
        if not isinstance(node, dict):
            continue
        for a in node.get("mandatory_actions", []) or []:
            result["mandatory"].add((node_id, a))
        for a in node.get("forbidden_actions", []) or []:
            result["forbidden"].add((node_id, a))
        for a in node.get("allowed_actions", []) or []:
            result["allowed"].add((node_id, a))
        for dk in node.get("deadlines", {}) or {}:
            result["deadline_keys"].add((node_id, dk))
        for rule in node.get("conditional_rules", []) or []:
            effect = rule.get("effect", {})
            etype = effect.get("type", "")
            for a in effect.get("actions", []) or []:
                if etype == "REQUIRED":
                    result["conditional_req"].add((node_id, a))
                elif etype == "FORBIDDEN":
                    result["conditional_forb"].add((node_id, a))
    return result


def audit_normalizer(
    graphs_dir: str | Path | None = None,
) -> dict:
    """Run the canonical-form audit.

    Returns a structured report dict.
    """
    graphs_dir = REPO_ROOT / "cpg_model" / "graphs" if graphs_dir is None else Path(graphs_dir)

    normalizer = ActionNormalizer()

    # raw_id → canonical form
    all_raw_ids: set[str] = set()
    # canonical → set of raw IDs
    canonical_groups: dict[str, set[str]] = defaultdict(set)
    # Track per-graph mandatory/forbidden for conflict blindspot detection
    per_graph_mandatory: dict[str, set[str]] = defaultdict(set)
    per_graph_forbidden: dict[str, set[str]] = defaultdict(set)
    per_graph_actions: dict[str, dict] = {}

    unmapped: set[str] = set()
    n_graphs = 0

    for yaml_file in sorted(graphs_dir.glob("*.yaml")):
        graph_id = yaml_file.stem
        n_graphs += 1
        data = yaml.safe_load(yaml_file.read_text())
        actions = _extract_actions_from_graph(data)
        per_graph_actions[graph_id] = {k: len(v) for k, v in actions.items()}

        # Collect all unique action IDs across all categories
        graph_raw_ids: set[str] = set()
        for category_items in actions.values():
            for _node_id, action_id in category_items:
                graph_raw_ids.add(action_id)

        for raw_id in graph_raw_ids:
            all_raw_ids.add(raw_id)
            canonical = normalizer.normalize(raw_id, cpg_id=graph_id)
            canonical_groups[canonical].add(raw_id)
            if canonical == raw_id.lower().strip():
                unmapped.add(raw_id)

        # Collect mandatory/forbidden per graph (using canonical forms)
        for _node_id, aid in actions["mandatory"]:
            per_graph_mandatory[graph_id].add(normalizer.normalize(aid, cpg_id=graph_id))
        for _node_id, aid in actions["conditional_req"]:
            per_graph_mandatory[graph_id].add(normalizer.normalize(aid, cpg_id=graph_id))
        for _node_id, aid in actions["forbidden"]:
            per_graph_forbidden[graph_id].add(normalizer.normalize(aid, cpg_id=graph_id))
        for _node_id, aid in actions["conditional_forb"]:
            per_graph_forbidden[graph_id].add(normalizer.normalize(aid, cpg_id=graph_id))

    # Detect conflict blindspots: canonical form in both mandatory + forbidden
    conflict_blindspots: list[dict] = []
    for graph_id in per_graph_mandatory:
        overlap = per_graph_mandatory[graph_id] & per_graph_forbidden.get(graph_id, set())
        for canonical in overlap:
            raw_ids = canonical_groups.get(canonical, {canonical})
            conflict_blindspots.append(
                {
                    "graph_id": graph_id,
                    "canonical": canonical,
                    "raw_ids": sorted(raw_ids),
                }
            )

    # Multi-raw canonical groups (>1 raw ID normalizing to same canonical)
    multi_canonical = {canonical: sorted(raws) for canonical, raws in canonical_groups.items() if len(raws) > 1}

    return {
        "total_graphs": n_graphs,
        "total_unique_raw_ids": len(all_raw_ids),
        "total_canonical_forms": len(canonical_groups),
        "unmapped_count": len(unmapped),
        "unmapped_actions": sorted(unmapped),
        "multi_canonical_groups": multi_canonical,
        "multi_canonical_count": len(multi_canonical),
        "conflict_blindspots": conflict_blindspots,
        "conflict_blindspot_count": len(conflict_blindspots),
        "per_graph_action_counts": per_graph_actions,
    }


def main() -> int:
    """Run normalizer audit and print results."""
    report = audit_normalizer()

    print(f"ActionNormalizer Canonical-Form Audit — {report['total_graphs']} graphs")
    print(f"  Unique raw action IDs: {report['total_unique_raw_ids']}")
    print(f"  Canonical forms: {report['total_canonical_forms']}")
    print(f"  Unmapped (normalize to self): {report['unmapped_count']}")
    print(f"  Multi-raw canonical groups: {report['multi_canonical_count']}")
    print(f"  Conflict blindspots: {report['conflict_blindspot_count']}")

    if report["unmapped_actions"]:
        print("\n--- Unmapped actions (top 30) ---")
        for a in report["unmapped_actions"][:30]:
            print(f"  {a}")
        if len(report["unmapped_actions"]) > 30:
            print(f"  ... and {len(report['unmapped_actions']) - 30} more")

    if report["multi_canonical_groups"]:
        print("\n--- Multi-raw canonical groups ---")
        for canonical, raws in sorted(report["multi_canonical_groups"].items()):
            print(f"  {canonical} <- {raws}")

    if report["conflict_blindspots"]:
        print("\n--- Conflict blindspots (canonical in both mandatory + forbidden) ---")
        for bs in report["conflict_blindspots"]:
            print(f"  [{bs['graph_id']}] {bs['canonical']} (raw: {bs['raw_ids']})")

    # LaTeX macros
    print("\n% LaTeX macros")
    print(f"\\providecommand{{\\normalizerRawActionsN}}{{{report['total_unique_raw_ids']}}}")
    print(f"\\providecommand{{\\normalizerCanonicalN}}{{{report['total_canonical_forms']}}}")
    print(f"\\providecommand{{\\normalizerUnmappedN}}{{{report['unmapped_count']}}}")
    print(f"\\providecommand{{\\normalizerMultiCanonicalN}}{{{report['multi_canonical_count']}}}")
    print(f"\\providecommand{{\\normalizerBlindspotN}}{{{report['conflict_blindspot_count']}}}")

    # JSON report
    report_path = REPO_ROOT / "evidence_pack" / "analysis" / "normalizer_audit.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    with open(report_path, "w") as f:
        json.dump(report, f, indent=2)
    print(f"\nJSON report written to {report_path}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
