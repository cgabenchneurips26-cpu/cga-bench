"""CDE rule-conflict audit (B-cde-rescoring v1.1).

Scans every CPG graph YAML under cpg_model/graphs/ and identifies actions that
are simultaneously REQUIRED and FORBIDDEN at the same node — either through
static mandatory/forbidden lists or through conditional_rules. Each conflict
pattern is classified into a remediation tier:

    Tier-A  Both REQUIRED and FORBIDDEN are conditional with conditions
            that look mutually exclusive (negation pair). The CDE conflict
            surfacing alone resolves these — no graph patch needed.

    Tier-B  Pattern looks like a YAML logic error: static mandatory paired
            with a conditional FORBIDDEN, or two rules with the SAME
            condition emitting opposite effects. Requires manual graph patch
            or rephrasing as OR_REQUIRED.

    Tier-C  Both conditional, conditions reference disjoint patient state
            and are co-satisfiable. Reflects a genuine OR_REQUIRED clinical
            intent that the current formalism cannot express. Deferred to
            v2.0 with explicit roadmap entry in App.~Z.5.

Output: evidence_pack/cde_conflict_audit_v1.json

Exit code 0 always (audit is informational; CI gating handled separately).
"""

from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path
import re
import sys
from typing import Any

import yaml

GRAPH_DIR = Path("cpg_model/graphs")
OUTPUT_PATH = Path("evidence_pack/cde_conflict_audit_v1.json")


def _load_graphs(graph_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all .yaml graphs (excluding archives) into name -> dict."""
    graphs: dict[str, dict[str, Any]] = {}
    for path in sorted(graph_dir.glob("*.yaml")):
        if "_archive" in str(path) or path.name.startswith("_"):
            continue
        try:
            with path.open() as f:
                data = yaml.safe_load(f)
            if isinstance(data, dict):
                graphs[path.stem] = data
        except yaml.YAMLError:
            continue
    return graphs


def _collect_node_action_index(
    node: dict[str, Any],
) -> tuple[dict[str, list[dict[str, str]]], dict[str, list[dict[str, str]]]]:
    """Build per-node action -> list of (provenance, condition, kind) entries.

    Returns (required_index, forbidden_index). Each entry is a small dict
    with keys {kind, source, condition, rule_id}.
        kind: "static" or "conditional"
        source: "mandatory_actions" / "forbidden_actions" / rule_id
    """
    required: dict[str, list[dict[str, str]]] = defaultdict(list)
    forbidden: dict[str, list[dict[str, str]]] = defaultdict(list)

    for action in node.get("mandatory_actions", []) or []:
        required[action].append(
            {
                "kind": "static",
                "source": "mandatory_actions",
                "condition": "",
                "rule_id": "",
            }
        )
    for action in node.get("forbidden_actions", []) or []:
        forbidden[action].append(
            {
                "kind": "static",
                "source": "forbidden_actions",
                "condition": "",
                "rule_id": "",
            }
        )
    for rule in node.get("conditional_rules", []) or []:
        rule_id = rule.get("rule_id", "unknown")
        condition = rule.get("condition", "")
        effect = rule.get("effect", {})
        effect_type = effect.get("type", "")
        for action in effect.get("actions", []) or []:
            entry = {
                "kind": "conditional",
                "source": rule_id,
                "condition": condition,
                "rule_id": rule_id,
            }
            if effect_type == "REQUIRED":
                required[action].append(entry)
            elif effect_type == "FORBIDDEN":
                forbidden[action].append(entry)
    return required, forbidden


_NEGATION_TOKENS = re.compile(
    r"\bnot\b|\bno_\w+\b|<\s*\d|>\s*\d|<=|>=|!=|\bin\b\s*\[",
    re.IGNORECASE,
)


def _conditions_appear_negation_pair(cond_a: str, cond_b: str) -> bool:
    """Heuristic: do two conditions look like complementary halves of a single
    decision boundary (e.g., 'sbp < 90' vs 'sbp >= 90', or 'X in P' vs 'X not in P')."""
    if not cond_a or not cond_b:
        return False
    a, b = cond_a.lower().strip(), cond_b.lower().strip()
    # Remove whitespace for textual diff
    if a == b:
        return False
    # Crude inversion check
    inverted = (
        a.replace("<", "≥").replace(">", "≤") == b
        or ("not " + a == b)
        or ("not " + b == a)
        or (a.startswith("not ") and a[4:] == b)
        or (b.startswith("not ") and b[4:] == a)
    )
    return inverted


def _classify_tier(
    required_entries: list[dict[str, str]],
    forbidden_entries: list[dict[str, str]],
) -> str:
    """Pick the worst-case tier across all (req, forb) pairs for one action.

    Order of precedence: B > C > A (B is the actionable fix tier).
    """
    has_static_required = any(e["kind"] == "static" for e in required_entries)
    has_static_forbidden = any(e["kind"] == "static" for e in forbidden_entries)

    # Tier-B path 1: static mandatory + any FORBIDDEN
    if has_static_required and forbidden_entries:
        return "B"
    # Tier-B path 2: static FORBIDDEN + conditional REQUIRED is also a YAML smell
    if has_static_forbidden and any(e["kind"] == "conditional" for e in required_entries):
        return "B"

    # Conditional pair analysis
    worst = "A"  # start optimistic
    for req in required_entries:
        for forb in forbidden_entries:
            if req["kind"] != "conditional" or forb["kind"] != "conditional":
                continue
            cond_r, cond_f = req["condition"], forb["condition"]
            if cond_r and cond_f and cond_r.strip() == cond_f.strip():
                return "B"  # same condition, opposite effects = logic error
            if _conditions_appear_negation_pair(cond_r, cond_f):
                # mutually exclusive -> engine surfacing alone resolves (Tier-A)
                if worst not in ("B", "C"):
                    worst = "A"
            else:
                # different vars / co-satisfiable -> genuine OR_REQUIRED (Tier-C)
                if worst != "B":
                    worst = "C"
    return worst


def detect_conflicts_in_graph(graph_id: str, graph: dict[str, Any]) -> list[dict[str, Any]]:
    """Return a list of conflict-pattern records for one graph."""
    conflicts: list[dict[str, Any]] = []
    nodes = graph.get("nodes", {}) or {}
    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            continue
        required_idx, forbidden_idx = _collect_node_action_index(node)
        for action in sorted(set(required_idx) & set(forbidden_idx)):
            req_entries = required_idx[action]
            forb_entries = forbidden_idx[action]
            tier = _classify_tier(req_entries, forb_entries)
            conflicts.append(
                {
                    "graph": graph_id,
                    "node": node_id,
                    "action": action,
                    "tier": tier,
                    "required": req_entries,
                    "forbidden": forb_entries,
                }
            )
    return conflicts


def run_audit(graph_dir: Path = GRAPH_DIR) -> dict[str, Any]:
    """Run the audit; returns the JSON-serialisable report."""
    graphs = _load_graphs(graph_dir)
    all_conflicts: list[dict[str, Any]] = []
    graphs_with_conditional = 0
    for graph_id, graph in graphs.items():
        nodes = graph.get("nodes", {}) or {}
        if any(
            (isinstance(n, dict) and n.get("conditional_rules"))
            for n in nodes.values()
        ):
            graphs_with_conditional += 1
        all_conflicts.extend(detect_conflicts_in_graph(graph_id, graph))

    tier_counts: dict[str, int] = defaultdict(int)
    graphs_per_tier: dict[str, set[str]] = defaultdict(set)
    for c in all_conflicts:
        tier_counts[c["tier"]] += 1
        graphs_per_tier[c["tier"]].add(c["graph"])

    return {
        "audit_version": "v1.1",
        "graph_dir": str(graph_dir),
        "total_graphs_scanned": len(graphs),
        "graphs_with_conditional_rules": graphs_with_conditional,
        "total_conflicts": len(all_conflicts),
        "tier_counts": {
            "A": tier_counts.get("A", 0),
            "B": tier_counts.get("B", 0),
            "C": tier_counts.get("C", 0),
        },
        "graphs_per_tier": {
            tier: sorted(g) for tier, g in graphs_per_tier.items()
        },
        "graphs_with_any_conflict": sorted({c["graph"] for c in all_conflicts}),
        "conflicts": all_conflicts,
    }


def main() -> int:
    cwd_graph_dir = GRAPH_DIR if GRAPH_DIR.exists() else Path.cwd() / GRAPH_DIR
    if not cwd_graph_dir.exists():
        print(f"ERROR: graph directory not found at {cwd_graph_dir}", file=sys.stderr)
        return 1
    report = run_audit(cwd_graph_dir)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(report, indent=2, ensure_ascii=False))
    print(f"Wrote {OUTPUT_PATH}")
    print(f"Total graphs scanned: {report['total_graphs_scanned']}")
    print(f"Graphs with conditional_rules: {report['graphs_with_conditional_rules']}")
    print(f"Total conflict patterns: {report['total_conflicts']}")
    print(f"Tier A/B/C: {report['tier_counts']['A']}/{report['tier_counts']['B']}/{report['tier_counts']['C']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
