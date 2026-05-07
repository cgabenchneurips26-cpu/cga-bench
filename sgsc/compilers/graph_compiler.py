"""Deterministic graph compiler: atoms -> YAML-compatible graph dict.

Groups atoms by clinical phase, creates nodes, wires edges from
sequence constraints and deadlines. Output matches the existing
``cpg_model/graphs/*.yaml`` format.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sgsc.schemas.atom import RecommendationAtom

logger = logging.getLogger(__name__)


class GraphCompilerConfig(BaseModel):
    """Configuration for the deterministic graph compiler."""

    model_config = ConfigDict(frozen=True)

    min_atoms_per_node: int = Field(1, ge=1)
    max_nodes: int = Field(15, ge=1)


# ------------------------------------------------------------------
# Recommendation class normalization
# ------------------------------------------------------------------

_REC_CLASS_MAP: dict[str, str] = {
    "I": "I",
    "II": "IIa",
    "IIa": "IIa",
    "IIb": "IIb",
    "III": "III",
    "1": "I",
    "2": "IIa",
    "Strong": "I",
    "strong": "I",
    "Weak": "IIa",
    "weak": "IIa",
    "Conditional": "IIb",
    "conditional": "IIb",
    "Category 1": "I",
    "Category 2A": "IIa",
    "Category 2B": "IIb",
    "Category 3": "III",
}


def _normalize_recommendation_class(raw: str) -> str:
    """Map various guideline grading systems to AHA-style classes."""
    return _REC_CLASS_MAP.get(raw.strip(), raw)


# ------------------------------------------------------------------
# Node construction helpers
# ------------------------------------------------------------------


def _group_atoms_by_section(
    atoms: list[RecommendationAtom],
) -> dict[str, list[RecommendationAtom]]:
    """Group atoms by their source section for node clustering."""
    groups: dict[str, list[RecommendationAtom]] = {}
    for atom in atoms:
        key = atom.source.section.strip() or "General"
        groups.setdefault(key, []).append(atom)
    return groups


def _section_to_node_id(section: str) -> str:
    """Convert a section name to a snake_case node_id."""
    cleaned = re.sub(r"[^a-zA-Z0-9\s]", "", section)
    parts = cleaned.lower().split()
    return "_".join(parts[:5]) or "unnamed_node"


def _build_node(
    node_id: str,
    section: str,
    atoms: list[RecommendationAtom],
) -> dict[str, Any]:
    """Build a single graph node from a group of atoms."""
    mandatory: list[str] = []
    allowed: list[str] = []
    forbidden: list[str] = []
    deadlines: dict[str, int] = {}
    required_prior: dict[str, list[str]] = {}
    source_rec_ids: list[str] = []

    for atom in atoms:
        action_id = atom.action.canonical_id

        if atom.constraint.type == "FORBIDDEN":
            forbidden.append(action_id)
        else:
            if atom.constraint.type in ("REQUIRED", "WITHIN"):
                mandatory.append(action_id)
            allowed.append(action_id)

        if atom.constraint.type == "WITHIN" and atom.constraint.deadline_minutes is not None:
            deadlines[action_id] = atom.constraint.deadline_minutes

        # required_prior_actions: {action_needing_prior: [list_of_prior_actions]}
        if atom.sequence.required_prior:
            existing = required_prior.get(action_id, [])
            for prior in atom.sequence.required_prior:
                if prior not in existing:
                    existing.append(prior)
            required_prior[action_id] = existing

        # BEFORE constraints: the atom's action must come before atom.sequence.before actions,
        # which means those after-actions require this action as a prior
        if atom.constraint.type == "BEFORE":
            for after_action in atom.sequence.before:
                existing = required_prior.get(after_action, [])
                if action_id not in existing:
                    existing.append(action_id)
                required_prior[after_action] = existing

        source_rec_ids.append(atom.atom_id)

    # Collect auto-transition hints from scenario hooks
    auto_transitions: list[dict[str, str]] = []
    for atom in atoms:
        for label in atom.scenario_hooks.auto_transitions:
            entry = {
                "condition": label,
                "target_node": "",  # wired later by _wire_sequence_edges
                "description": f"Auto-transition from atom {atom.atom_id}: {label}",
            }
            if entry not in auto_transitions:
                auto_transitions.append(entry)

    # Deduplicate while preserving order
    mandatory = list(dict.fromkeys(mandatory))
    allowed = list(dict.fromkeys(allowed))
    forbidden = list(dict.fromkeys(forbidden))

    # Use first atom's evidence as representative
    rep = atoms[0]

    return {
        "node_id": node_id,
        "node_type": "plan" if len(mandatory) > 1 else "action",
        "name": section,
        "description": f"Actions derived from {section}.",
        "mandatory_actions": mandatory,
        "allowed_actions": allowed,
        "forbidden_actions": forbidden,
        "deadlines": deadlines,
        "required_prior_actions": required_prior,
        "recommendation_class": _normalize_recommendation_class(rep.evidence.recommendation_class),
        "evidence_level": rep.evidence.level,
        "source_guideline": rep.source.guideline_id,
        "source_section": section,
        "source_page": rep.source.page,
        "source_quote": rep.source.quote[:300],
        "source_recommendation_ids": source_rec_ids,
        "next_nodes": [],
        "conditional_next": {},
        "auto_transition_conditions": auto_transitions,
    }


# ------------------------------------------------------------------
# Edge wiring
# ------------------------------------------------------------------


def _wire_sequence_edges(
    nodes: dict[str, dict[str, Any]],
    atoms: list[RecommendationAtom],
) -> None:
    """Wire next_nodes based on BEFORE constraints and atom sequence."""
    # Build action -> node_id mapping
    action_to_node: dict[str, str] = {}
    for nid, node in nodes.items():
        for action_id in node.get("mandatory_actions", []) + node.get("allowed_actions", []):
            action_to_node[action_id] = nid

    # Wire BEFORE constraints
    for atom in atoms:
        if atom.constraint.type == "BEFORE":
            src_node = action_to_node.get(atom.action.canonical_id)
            for after_action in atom.sequence.before:
                dst_node = action_to_node.get(after_action)
                if src_node and dst_node and src_node != dst_node:
                    if dst_node not in nodes[src_node]["next_nodes"]:
                        nodes[src_node]["next_nodes"].append(dst_node)

    # Wire required_prior as edges
    for atom in atoms:
        for prior in atom.sequence.required_prior:
            prior_node = action_to_node.get(prior)
            current_node = action_to_node.get(atom.action.canonical_id)
            if prior_node and current_node and prior_node != current_node:
                if current_node not in nodes[prior_node]["next_nodes"]:
                    nodes[prior_node]["next_nodes"].append(current_node)

    # If no edges exist, create a linear chain
    node_ids = list(nodes.keys())
    has_any_edge = any(bool(n.get("next_nodes")) for n in nodes.values())
    if not has_any_edge and len(node_ids) > 1:
        for i in range(len(node_ids) - 1):
            nodes[node_ids[i]]["next_nodes"] = [node_ids[i + 1]]


# ------------------------------------------------------------------
# Defensive action-ID normalization (2-layer strategy per Track-alpha B3)
# ------------------------------------------------------------------


def _defensive_normalize_graph(graph: dict[str, Any]) -> dict[str, Any]:
    """Normalize all action IDs in a compiled graph through ActionNormalizer.

    Defensive layer: atoms are already normalized by pipeline Step 2b,
    but direct callers of ``GraphCompiler.compile()`` may skip that step.
    Uses lazy import with graceful fallback so SGSC can run standalone.
    """
    try:
        from cga_bench.assessor_core.action_normalizer import ActionNormalizer
    except ImportError:
        return graph

    normalizer = ActionNormalizer()
    nodes = graph.get("nodes", {})
    n_changed = 0

    for node in nodes.values():
        for key in ("mandatory_actions", "allowed_actions", "forbidden_actions"):
            original_list = node.get(key, [])
            normalized_list = [normalizer.normalize(a) for a in original_list]
            if normalized_list != original_list:
                n_changed += sum(1 for o, n in zip(original_list, normalized_list, strict=True) if o != n)
                node[key] = normalized_list

        # Normalize deadlines keys
        deadlines = node.get("deadlines", {})
        if deadlines:
            new_deadlines = {normalizer.normalize(k): v for k, v in deadlines.items()}
            if new_deadlines != deadlines:
                node["deadlines"] = new_deadlines

        # Normalize required_prior_actions keys and values
        rpa = node.get("required_prior_actions", {})
        if rpa:
            new_rpa = {normalizer.normalize(k): [normalizer.normalize(p) for p in v] for k, v in rpa.items()}
            if new_rpa != rpa:
                node["required_prior_actions"] = new_rpa

    if n_changed:
        logger.info("Defensive graph normalization: %d action IDs canonicalized", n_changed)

    return graph


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


class GraphCompiler:
    """Deterministic compiler: atoms -> YAML-compatible graph dict."""

    def __init__(self, config: GraphCompilerConfig | None = None) -> None:
        self.config = config or GraphCompilerConfig()

    def compile(
        self,
        atoms: list[RecommendationAtom],
        guideline_id: str,
        guideline_name: str,
    ) -> dict[str, Any]:
        """Compile atoms into a graph dict matching cpg_model/graphs/*.yaml format.

        Algorithm:
        1. Group atoms by source section
        2. Create one node per section group
        3. Wire edges from sequence constraints
        4. Set entry_node to the first node
        """
        if not atoms:
            return {
                "graph_id": guideline_id,
                "guideline_name": guideline_name,
                "version": "sgsc-0.1.0",
                "metadata": {"source": "SGSC", "description": "Empty graph — no atoms provided."},
                "entry_node": "",
                "nodes": {},
            }

        # Step 1: Group
        section_groups = _group_atoms_by_section(atoms)

        # Step 2: Build nodes
        nodes: dict[str, dict[str, Any]] = {}
        node_order: list[str] = []

        for section, section_atoms in section_groups.items():
            if len(section_atoms) < self.config.min_atoms_per_node:
                continue
            node_id = _section_to_node_id(section)
            # Handle duplicate node_ids
            if node_id in nodes:
                node_id = f"{node_id}_{len(nodes)}"
            nodes[node_id] = _build_node(node_id, section, section_atoms)
            node_order.append(node_id)

        # Enforce max_nodes by merging smallest groups
        while len(nodes) > self.config.max_nodes and len(node_order) > 1:
            last_id = node_order.pop()
            prev_id = node_order[-1]
            # Merge last into prev
            last_node = nodes.pop(last_id)
            prev_node = nodes[prev_id]
            prev_node["mandatory_actions"].extend(last_node["mandatory_actions"])
            prev_node["allowed_actions"].extend(last_node["allowed_actions"])
            prev_node["forbidden_actions"].extend(last_node["forbidden_actions"])
            prev_node["deadlines"].update(last_node["deadlines"])
            prev_node["source_recommendation_ids"].extend(last_node["source_recommendation_ids"])
            # Merge required_prior_actions
            for action, priors in last_node.get("required_prior_actions", {}).items():
                existing = prev_node["required_prior_actions"].get(action, [])
                for p in priors:
                    if p not in existing:
                        existing.append(p)
                prev_node["required_prior_actions"][action] = existing
            # Deduplicate action lists after merge
            prev_node["mandatory_actions"] = list(dict.fromkeys(prev_node["mandatory_actions"]))
            prev_node["allowed_actions"] = list(dict.fromkeys(prev_node["allowed_actions"]))
            prev_node["forbidden_actions"] = list(dict.fromkeys(prev_node["forbidden_actions"]))

        # Step 3: Wire edges
        _wire_sequence_edges(nodes, atoms)

        # Step 4: Build graph
        entry_node = node_order[0] if node_order else ""
        metadata_source = atoms[0].source.guideline_id if atoms else ""

        graph = {
            "graph_id": guideline_id,
            "guideline_name": guideline_name,
            "version": "sgsc-0.1.0",
            "metadata": {
                "source": metadata_source,
                "description": f"Auto-compiled graph for {guideline_name} from {len(atoms)} atoms.",
            },
            "entry_node": entry_node,
            "nodes": nodes,
            "_generation_pipeline": {
                "method": "sgsc",
                "version": "0.1.0",
                "atom_count": len(atoms),
                "node_count": len(nodes),
            },
        }

        # Defensive normalization: ensure all action IDs are canonical
        return _defensive_normalize_graph(graph)
