#!/usr/bin/env python3
"""P0-4: Structural audit of auto-transition fields in SGSC-compiled graphs.

Validates structural invariants for auto_transition_conditions across all
SGSC-compiled graphs. Currently all fields are empty (v2.0 deferred) so
the audit passes cleanly — it will catch violations when auto-transitions
are populated.

Usage:
    PYTHONPATH=. python scripts/sgsc/audit_auto_transition_semantics.py
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
from pathlib import Path
import subprocess
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent

logger = logging.getLogger("audit_auto_transition")

# Private state fields that must not appear in transition conditions
PRIVATE_STATE_FIELDS = {
    "expected_actions",
    "forbidden_actions",
    "mandatory_actions",
    "ground_truth",
    "passing_compliance_threshold",
    "coverage_targets",
    "_sgsc_metadata",
}


def _git_commit() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=str(REPO_ROOT), text=True).strip()
    except Exception:
        return "unknown"


def _hash_files(paths: list[Path]) -> str:
    h = hashlib.sha256()
    for p in sorted(paths):
        if p.exists():
            h.update(p.read_bytes())
    return h.hexdigest()


def _collect_node_ids(graph_data: dict) -> set[str]:
    """Collect all node IDs from a graph."""
    nodes = graph_data.get("nodes", {})
    if isinstance(nodes, dict):
        return set(nodes.keys())
    if isinstance(nodes, list):
        return {n.get("node_id", "") for n in nodes if isinstance(n, dict)}
    return set()


def check_missing_target_nodes(
    transitions: list[dict],
    node_ids: set[str],
    graph_id: str,
) -> list[dict[str, str]]:
    """Check that every transition target_node exists in the graph."""
    failures: list[dict[str, str]] = []
    for t in transitions:
        target = t.get("target_node", "")
        if target and target not in node_ids:
            failures.append(
                {
                    "graph_id": graph_id,
                    "check": "missing_target_node",
                    "detail": f"Transition targets missing node '{target}'",
                }
            )
    return failures


def check_hidden_state_references(
    transitions: list[dict],
    graph_id: str,
) -> list[dict[str, str]]:
    """Check that activation conditions don't reference private state."""
    failures: list[dict[str, str]] = []
    for t in transitions:
        condition_str = json.dumps(t).lower()
        for field in PRIVATE_STATE_FIELDS:
            if field in condition_str:
                failures.append(
                    {
                        "graph_id": graph_id,
                        "check": "hidden_state_before_reveal",
                        "detail": f"Transition references private field '{field}'",
                    }
                )
    return failures


def check_ambiguous_multi_fire(
    transitions: list[dict],
    graph_id: str,
) -> list[dict[str, str]]:
    """Check for overlapping conditions without distinct priorities."""
    failures: list[dict[str, str]] = []
    if len(transitions) < 2:
        return failures

    # Check if any transitions share the same source but lack priority
    seen_conditions: list[str] = []
    for t in transitions:
        cond_key = json.dumps(t.get("condition", {}), sort_keys=True)
        priority = t.get("priority")
        if cond_key in seen_conditions and priority is None:
            failures.append(
                {
                    "graph_id": graph_id,
                    "check": "ambiguous_multi_fire",
                    "detail": f"Duplicate condition without priority: {cond_key[:80]}",
                }
            )
        seen_conditions.append(cond_key)

    return failures


def check_unbounded_cycles(
    transitions: list[dict],
    graph_id: str,
) -> list[dict[str, str]]:
    """Check for unbounded cycles in the transition graph."""
    failures: list[dict[str, str]] = []
    if not transitions:
        return failures

    # Build adjacency list from transitions
    edges: dict[str, list[str]] = {}
    for t in transitions:
        source = t.get("source_node", "")
        target = t.get("target_node", "")
        if source and target:
            edges.setdefault(source, []).append(target)

    # DFS cycle detection
    visited: set[str] = set()
    in_stack: set[str] = set()

    def _dfs(node: str) -> bool:
        visited.add(node)
        in_stack.add(node)
        for neighbor in edges.get(node, []):
            if neighbor in in_stack:
                return True
            if neighbor not in visited and _dfs(neighbor):
                return True
        in_stack.discard(node)
        return False

    for start in edges:
        if start not in visited:
            if _dfs(start):
                failures.append(
                    {
                        "graph_id": graph_id,
                        "check": "unbounded_cycle",
                        "detail": "Cycle detected in auto-transition graph",
                    }
                )
                break

    return failures


def check_missing_provenance(
    transitions: list[dict],
    graph_id: str,
) -> list[dict[str, str]]:
    """Check that every transition has source_atom_ids or author_override."""
    failures: list[dict[str, str]] = []
    for t in transitions:
        has_atoms = bool(t.get("source_atom_ids"))
        has_author = bool(t.get("author_override"))
        if not has_atoms and not has_author:
            failures.append(
                {
                    "graph_id": graph_id,
                    "check": "missing_provenance",
                    "detail": "Transition lacks source_atom_ids and author_override",
                }
            )
    return failures


def audit_graph(graph_path: Path) -> tuple[int, list[dict[str, str]]]:
    """Audit a single graph file for auto-transition invariants."""
    data = json.loads(graph_path.read_text())
    graph_id = data.get("graph_id", graph_path.stem)
    node_ids = _collect_node_ids(data)

    # Collect all auto_transition_conditions from nodes
    all_transitions: list[dict] = []
    nodes = data.get("nodes", {})
    if isinstance(nodes, dict):
        node_list = nodes.values()
    else:
        node_list = nodes

    for node in node_list:
        if not isinstance(node, dict):
            continue
        transitions = node.get("auto_transition_conditions", [])
        if isinstance(transitions, list):
            # Annotate with source_node for cycle detection
            for t in transitions:
                if isinstance(t, dict):
                    t.setdefault("source_node", node.get("node_id", ""))
            all_transitions.extend(t for t in transitions if isinstance(t, dict))

    failures: list[dict[str, str]] = []
    failures.extend(check_missing_target_nodes(all_transitions, node_ids, graph_id))
    failures.extend(check_hidden_state_references(all_transitions, graph_id))
    failures.extend(check_ambiguous_multi_fire(all_transitions, graph_id))
    failures.extend(check_unbounded_cycles(all_transitions, graph_id))
    failures.extend(check_missing_provenance(all_transitions, graph_id))

    return len(all_transitions), failures


def run_audit(sgsc_dir: Path) -> dict:
    """Run the full auto-transition semantics audit."""
    graph_files = sorted(sgsc_dir.rglob("*_graph.json"))
    input_files = list(graph_files)

    total_transitions = 0
    all_failures: list[dict[str, str]] = []
    graphs_scanned = 0

    for gf in graph_files:
        try:
            n_trans, failures = audit_graph(gf)
            total_transitions += n_trans
            all_failures.extend(failures)
            graphs_scanned += 1
        except (json.JSONDecodeError, OSError, KeyError) as e:
            all_failures.append(
                {
                    "graph_id": gf.stem,
                    "check": "parse_error",
                    "detail": str(e),
                }
            )

    # Count by check type
    check_counts: dict[str, int] = {}
    for f in all_failures:
        check = f.get("check", "unknown")
        check_counts[check] = check_counts.get(check, 0) + 1

    if all_failures:
        status = "fail" if any(f["check"] != "missing_provenance" for f in all_failures) else "warn"
    else:
        status = "pass"

    report = {
        "check_name": "auto_transition_semantics",
        "status": status,
        "commit": _git_commit(),
        "input_hash": _hash_files(input_files),
        "metrics": {
            "graphs_scanned": graphs_scanned,
            "total_auto_transitions": total_transitions,
            "missing_target_node": check_counts.get("missing_target_node", 0),
            "hidden_state_before_reveal": check_counts.get("hidden_state_before_reveal", 0),
            "ambiguous_multi_fire": check_counts.get("ambiguous_multi_fire", 0),
            "unbounded_cycles": check_counts.get("unbounded_cycle", 0),
            "missing_provenance": check_counts.get("missing_provenance", 0),
        },
        "failures": all_failures,
    }

    report_bytes = json.dumps(report, sort_keys=True).encode()
    report["output_hash"] = hashlib.sha256(report_bytes).hexdigest()

    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="P0-4: Auto-transition semantics audit")
    parser.add_argument("--sgsc-dir", default=str(REPO_ROOT / "sgsc_output"))
    parser.add_argument(
        "--output", default=str(REPO_ROOT / "evidence_pack" / "analysis" / "auto_transition_audit.json")
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    sgsc_dir = Path(args.sgsc_dir)
    if not sgsc_dir.is_dir():
        logger.error("SGSC output dir not found: %s", sgsc_dir)
        return 1

    report = run_audit(sgsc_dir)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    logger.info("Report written to %s", output_path)

    m = report["metrics"]
    print("\n=== Auto-Transition Semantics Audit ===")
    print(f"Status: {report['status'].upper()}")
    print(f"Graphs scanned: {m['graphs_scanned']}")
    print(f"Total auto-transitions: {m['total_auto_transitions']}")
    print(f"Missing target nodes: {m['missing_target_node']}")
    print(f"Hidden state refs: {m['hidden_state_before_reveal']}")
    print(f"Ambiguous multi-fire: {m['ambiguous_multi_fire']}")
    print(f"Unbounded cycles: {m['unbounded_cycles']}")
    print(f"Missing provenance: {m['missing_provenance']}")

    return 1 if report["status"] == "fail" else 0


if __name__ == "__main__":
    sys.exit(main())
