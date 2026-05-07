"""Cross-reference validator for CPG graphs.

Validates new/candidate CPG graphs against the existing 25-graph corpus for:
  1. Action ID namespace conflicts (same ID, different clinical meaning)
  2. Deadline inconsistencies (same action with wildly different deadlines)
  3. Forbidden/allowed contradictions across graphs
  4. Graph connectivity (all nodes reachable from entry_node)
  5. Conditional rule ID uniqueness across entire corpus

Usage:
    # Validate all graphs against each other
    PYTHONPATH=. python scripts/ci/validate_cross_ref.py

    # Validate candidate graphs against existing corpus
    PYTHONPATH=. python scripts/ci/validate_cross_ref.py \
        --candidate-dir cpg_model/graphs/auto/ \
        --corpus-dir cpg_model/graphs/

    # Validate a single candidate graph
    PYTHONPATH=. python scripts/ci/validate_cross_ref.py \
        --candidate cpg_model/graphs/auto/test_graph.yaml
"""

from __future__ import annotations

import argparse
from collections import defaultdict
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger("validate_cross_ref")

BASE_DIR = Path(__file__).resolve().parent.parent.parent
DEFAULT_CORPUS_DIR = BASE_DIR / "cpg_model" / "graphs"

# Deadline tolerance: flag if same action has deadlines differing by more than
# this factor (e.g., 3.0 means one graph says 60min and another says >180min).
DEADLINE_DIVERGENCE_FACTOR = 3.0

# Actions that are legitimately shared across domains (universal clinical ops).
# These are excluded from namespace conflict checks.
UNIVERSAL_ACTIONS: frozenset[str] = frozenset(
    {
        "assess_vital_signs",
        "reassess_perfusion",
        "determine_disposition",
        "admit_to_icu",
        "admit_to_ward",
        "discharge_home",
        "request_consultation",
        "order_lab_cbc",
        "order_lab_bmp",
        "order_lab_cmp",
        "order_lab_coagulation",
        "order_lab_blood_gas",
        "order_imaging_chest_xray",
        "place_central_line",
        "place_arterial_line",
        "order_lab_urinalysis",
        "order_lab_urine_culture",
        "order_lab_liver_function_tests",
        "order_imaging_ct_abdomen",
        "order_imaging_ct_chest",
        "order_imaging_ultrasound_abdomen",
        "order_lab_procalcitonin",
        "order_lab_creatinine",
        "order_lab_troponin",
        "order_imaging_ct_head",
        "obtain_ecg",
    }
)


# ---------------------------------------------------------------------------
# Graph loading
# ---------------------------------------------------------------------------


def load_graph(path: Path) -> dict[str, Any] | None:
    """Load a single CPG graph YAML file. Returns None on error."""
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
        if isinstance(data, dict) and "nodes" in data:
            return data
        logger.warning("Skipping %s: no 'nodes' key", path.name)
        return None
    except Exception as e:
        logger.warning("Failed to load %s: %s", path.name, e)
        return None


def load_corpus(corpus_dir: Path) -> dict[str, dict[str, Any]]:
    """Load all YAML graphs from a directory. Returns {graph_id: data}."""
    corpus: dict[str, dict[str, Any]] = {}
    for path in sorted(corpus_dir.glob("*.yaml")):
        data = load_graph(path)
        if data:
            gid = data.get("graph_id", path.stem)
            corpus[gid] = data
    return corpus


# ---------------------------------------------------------------------------
# Index builders
# ---------------------------------------------------------------------------


def _extract_domain(graph: dict[str, Any]) -> str:
    """Best-effort domain extraction from graph metadata."""
    meta = graph.get("metadata") or {}
    domain = meta.get("domain", "")
    if domain:
        return domain
    # Fallback: infer from graph_id
    gid = graph.get("graph_id", "")
    if "sepsis" in gid:
        return "sepsis"
    if "chest_pain" in gid or "aha_chest" in gid:
        return "chest_pain"
    if "stroke" in gid:
        return "stroke"
    if "aki" in gid or "kdigo" in gid:
        return "aki"
    return "unknown"


class ActionIndex:
    """Global index of all action IDs across a CPG corpus."""

    def __init__(self) -> None:
        # action_id -> list of (graph_id, context) tuples
        self.mandatory: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.forbidden: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.allowed: dict[str, list[tuple[str, str]]] = defaultdict(list)
        self.deadlines: dict[str, list[tuple[str, int]]] = defaultdict(list)
        self.rule_ids: dict[str, list[str]] = defaultdict(list)  # rule_id -> [graph_id]
        self.graph_domains: dict[str, str] = {}  # graph_id -> domain

    def index_graph(self, graph_id: str, graph: dict[str, Any]) -> None:
        """Index all action references from a single graph."""
        domain = _extract_domain(graph)
        self.graph_domains[graph_id] = domain

        for nid, node in (graph.get("nodes") or {}).items():
            if not isinstance(node, dict):
                continue

            ctx = f"{graph_id}:{nid}"

            for action in node.get("mandatory_actions") or []:
                self.mandatory[action].append((graph_id, ctx))

            for action in node.get("forbidden_actions") or []:
                self.forbidden[action].append((graph_id, ctx))

            for action in node.get("allowed_actions") or []:
                self.allowed[action].append((graph_id, ctx))

            for action, deadline in (node.get("deadlines") or {}).items():
                if isinstance(deadline, (int, float)):
                    self.deadlines[action].append((graph_id, int(deadline)))

            for rule in node.get("conditional_rules") or []:
                if isinstance(rule, dict):
                    rid = rule.get("rule_id", "")
                    if rid:
                        self.rule_ids[rid].append(graph_id)


# ---------------------------------------------------------------------------
# Validation checks
# ---------------------------------------------------------------------------


def check_connectivity(graph: dict[str, Any], graph_id: str) -> list[str]:
    """Check that all nodes are reachable from entry_node via BFS."""
    errors: list[str] = []
    nodes = graph.get("nodes") or {}
    entry = graph.get("entry_node")

    if not entry or entry not in nodes:
        errors.append(f"{graph_id}: entry_node '{entry}' not found in nodes")
        return errors

    # BFS from entry
    visited: set[str] = set()
    queue: list[str] = [entry]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        node = nodes.get(current)
        if not node or not isinstance(node, dict):
            continue
        for nxt in node.get("next_nodes") or []:
            if nxt in nodes:
                queue.append(nxt)
        for _cond, target in (node.get("conditional_next") or {}).items():
            if target in nodes:
                queue.append(target)

    unreachable = set(nodes.keys()) - visited
    if unreachable:
        errors.append(
            f"{graph_id}: {len(unreachable)} unreachable node(s) from entry_node '{entry}': {sorted(unreachable)}"
        )
    return errors


def check_deadline_consistency(index: ActionIndex) -> list[str]:
    """Flag actions whose deadlines diverge wildly across graphs."""
    warnings: list[str] = []
    for action_id, entries in index.deadlines.items():
        if len(entries) < 2:
            continue
        deadlines_only = [d for _, d in entries]
        min_d = min(deadlines_only)
        max_d = max(deadlines_only)
        if min_d > 0 and max_d / min_d > DEADLINE_DIVERGENCE_FACTOR:
            sources = ", ".join(f"{gid}={d}min" for gid, d in entries)
            warnings.append(
                f"deadline divergence for '{action_id}': "
                f"range [{min_d}, {max_d}] min "
                f"(factor {max_d / min_d:.1f}x > {DEADLINE_DIVERGENCE_FACTOR}x) — {sources}"
            )
    return warnings


def check_forbidden_mandatory_conflict(index: ActionIndex) -> list[str]:
    """Flag actions that are mandatory in one graph but forbidden in another."""
    errors: list[str] = []
    conflict_actions = set(index.mandatory.keys()) & set(index.forbidden.keys())
    for action_id in sorted(conflict_actions):
        if action_id in UNIVERSAL_ACTIONS:
            continue
        mand_graphs = {gid for gid, _ in index.mandatory[action_id]}
        forb_graphs = {gid for gid, _ in index.forbidden[action_id]}
        # Only flag if DIFFERENT graphs conflict (same graph may use conditional rules)
        cross_conflict = mand_graphs & forb_graphs
        if cross_conflict:
            # Same graph mandatory+forbidden is handled by schema validator
            continue
        # Different graphs: check if domains differ (expected) vs same domain (problem)
        mand_domains = {index.graph_domains.get(g, "?") for g in mand_graphs}
        forb_domains = {index.graph_domains.get(g, "?") for g in forb_graphs}
        same_domain = mand_domains & forb_domains
        if same_domain:
            mand_src = ", ".join(f"{g}" for g, _ in index.mandatory[action_id])
            forb_src = ", ".join(f"{g}" for g, _ in index.forbidden[action_id])
            errors.append(
                f"'{action_id}' is mandatory in [{mand_src}] but forbidden in "
                f"[{forb_src}] within same domain(s) {same_domain}"
            )
    return errors


def check_rule_id_uniqueness(index: ActionIndex) -> list[str]:
    """Flag conditional rule IDs that appear in multiple graphs."""
    warnings: list[str] = []
    for rule_id, graph_ids in index.rule_ids.items():
        unique_graphs = set(graph_ids)
        if len(unique_graphs) > 1:
            warnings.append(f"conditional rule_id '{rule_id}' appears in multiple graphs: {sorted(unique_graphs)}")
    return warnings


def check_action_namespace(index: ActionIndex) -> list[str]:
    """Flag domain-specific actions that leak into unrelated domains.

    A domain-specific action (not in UNIVERSAL_ACTIONS) appearing in graphs
    from 3+ different domains suggests the action ID is too generic.
    """
    warnings: list[str] = []
    # Build action -> set of domains
    action_domains: dict[str, set[str]] = defaultdict(set)
    for action_id, entries in index.mandatory.items():
        for gid, _ in entries:
            action_domains[action_id].add(index.graph_domains.get(gid, "?"))
    for action_id, entries in index.allowed.items():
        for gid, _ in entries:
            action_domains[action_id].add(index.graph_domains.get(gid, "?"))

    for action_id, domains in action_domains.items():
        if action_id in UNIVERSAL_ACTIONS:
            continue
        domains_filtered = domains - {"unknown"}
        if len(domains_filtered) >= 3:
            warnings.append(
                f"action '{action_id}' appears in {len(domains_filtered)} domains "
                f"({sorted(domains_filtered)}); consider if this should be a UNIVERSAL_ACTION "
                f"or if domain-specific variants are needed"
            )
    return warnings


def check_orphan_deadlines(graph: dict[str, Any], graph_id: str) -> list[str]:
    """Flag deadlines referencing actions not in mandatory or allowed."""
    warnings: list[str] = []
    for nid, node in (graph.get("nodes") or {}).items():
        if not isinstance(node, dict):
            continue
        mandatory = set(node.get("mandatory_actions") or [])
        allowed = set(node.get("allowed_actions") or [])
        all_known = mandatory | allowed
        for action_id in node.get("deadlines") or {}:
            if action_id not in all_known:
                warnings.append(
                    f"{graph_id}:{nid}: deadline for '{action_id}' references action not in mandatory/allowed"
                )
    return warnings


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(
    errors: list[str],
    warnings: list[str],
    corpus_size: int,
    candidate_count: int,
) -> str:
    """Generate a human-readable validation report."""
    lines: list[str] = []
    lines.append("=" * 60)
    lines.append("CPG Cross-Reference Validation Report")
    lines.append("=" * 60)
    lines.append(f"Corpus graphs: {corpus_size}")
    lines.append(f"Candidate graphs validated: {candidate_count}")
    lines.append(f"Errors: {len(errors)}")
    lines.append(f"Warnings: {len(warnings)}")
    lines.append("")

    if errors:
        lines.append("--- ERRORS ---")
        for e in errors:
            lines.append(f"  ERROR: {e}")
        lines.append("")

    if warnings:
        lines.append("--- WARNINGS ---")
        for w in warnings[:50]:
            lines.append(f"  WARN: {w}")
        if len(warnings) > 50:
            lines.append(f"  ... and {len(warnings) - 50} more warnings")
        lines.append("")

    if not errors:
        lines.append("RESULT: PASSED (no errors)")
    else:
        lines.append(f"RESULT: FAILED ({len(errors)} error(s))")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Public API (for testing)
# ---------------------------------------------------------------------------


def validate_cross_references(
    corpus: dict[str, dict[str, Any]],
    candidates: dict[str, dict[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    """Validate cross-references across a corpus of CPG graphs.

    Args:
        corpus: The existing corpus {graph_id: data}.
        candidates: Optional new/candidate graphs to validate against corpus.
            If None, validates the corpus against itself.

    Returns:
        (errors, warnings) lists.
    """
    errors: list[str] = []
    warnings: list[str] = []

    # Build index from corpus
    index = ActionIndex()
    for gid, graph in corpus.items():
        index.index_graph(gid, graph)

    # Add candidates to index
    if candidates:
        for gid, graph in candidates.items():
            index.index_graph(gid, graph)

    # Target graphs: candidates if provided, else entire corpus
    target = candidates if candidates else corpus

    # Per-graph checks
    for gid, graph in target.items():
        errors.extend(check_connectivity(graph, gid))
        warnings.extend(check_orphan_deadlines(graph, gid))

    # Cross-graph checks
    warnings.extend(check_deadline_consistency(index))
    errors.extend(check_forbidden_mandatory_conflict(index))
    warnings.extend(check_rule_id_uniqueness(index))
    warnings.extend(check_action_namespace(index))

    return errors, warnings


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_argparser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Cross-reference validation for CPG graphs.",
    )
    p.add_argument(
        "--corpus-dir",
        type=Path,
        default=None,
        help=f"Existing CPG graph directory (default: {DEFAULT_CORPUS_DIR})",
    )
    p.add_argument(
        "--candidate-dir",
        type=Path,
        default=None,
        help="Directory of candidate graphs to validate against corpus.",
    )
    p.add_argument(
        "--candidate",
        type=Path,
        default=None,
        help="Single candidate graph file to validate.",
    )
    p.add_argument(
        "--warnings-as-errors",
        action="store_true",
        help="Treat warnings as errors.",
    )
    p.add_argument("--verbose", "-v", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_argparser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    # Load corpus
    corpus_dir = args.corpus_dir or DEFAULT_CORPUS_DIR
    if not corpus_dir.is_dir():
        print(f"ERROR: corpus directory not found: {corpus_dir}")
        return 1
    corpus = load_corpus(corpus_dir)
    logger.info("Loaded %d corpus graphs from %s", len(corpus), corpus_dir)

    # Load candidates
    candidates: dict[str, dict[str, Any]] | None = None
    candidate_count = 0

    if args.candidate:
        data = load_graph(args.candidate)
        if data:
            gid = data.get("graph_id", args.candidate.stem)
            candidates = {gid: data}
            candidate_count = 1
    elif args.candidate_dir:
        if not args.candidate_dir.is_dir():
            print(f"ERROR: candidate directory not found: {args.candidate_dir}")
            return 1
        candidates = load_corpus(args.candidate_dir)
        candidate_count = len(candidates)
        logger.info("Loaded %d candidate graphs", candidate_count)

    # Validate
    errors, warnings = validate_cross_references(corpus, candidates)

    # Report
    report = generate_report(
        errors,
        warnings,
        corpus_size=len(corpus),
        candidate_count=candidate_count or len(corpus),
    )
    print(report)

    if args.warnings_as_errors:
        errors.extend(warnings)

    return 1 if errors else 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
