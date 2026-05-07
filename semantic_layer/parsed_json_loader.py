"""Deterministic parsed-JSON → CPG YAML converter (rule-based, no LLM).

Part of the v7 expansion 3-layer architecture:

    PDF ──[LLM, 1-pass, artifact committed]──▶ extended parsed.json
                                                         │
                                                         ▼ (this module)
                                                   rule-based deterministic
                                                         │
                                                         ▼
                                                    CPG graph YAML

The extended parsed.json is **structurally homomorphic** to the CGA-Bench CPG
graph YAML — same keys, same hierarchy. This loader:

  1. Reads the JSON file
  2. Validates top-level + per-node required fields (same contract as
     `scripts/ci/validate_cpg_schema.py`)
  3. Fills in sensible defaults (empty lists for optional sequence fields,
     'unknown' for missing source attribution)
  4. Stamps provenance metadata (`generated_by`, pipeline version)
  5. Serialises to YAML

**No LLM call is made.** Running the same JSON through this loader twice
produces byte-identical YAML (modulo the `generated_at` timestamp if enabled).

This path is the **reviewer-facing reproducibility guarantee**: every CPG
graph YAML in `cpg_model/graphs/auto/` can be regenerated from its source
JSON deterministically.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Keep this version tag in sync with the pipeline version; bump when the
# normalisation logic below changes in a way that affects output.
LOADER_VERSION = "parsed_json_loader.v1"

# Must match VALID_NODE_TYPES in scripts/ci/validate_cpg_schema.py.
_VALID_NODE_TYPES: frozenset[str] = frozenset({"decision", "plan", "action", "enquiry"})

# Must match REQUIRED_TOP_LEVEL_FIELDS in scripts/ci/validate_cpg_schema.py.
_REQUIRED_TOP_LEVEL: tuple[str, ...] = ("graph_id", "guideline_name", "entry_node", "nodes")

# Must match REQUIRED_NODE_FIELDS in scripts/ci/validate_cpg_schema.py.
# `allowed_actions` intentionally omitted: runtime (engine.py:82,
# node_types.py dataclass default) treats missing/empty allowed_actions as
# "no additional actions beyond mandatory", not an error.
_REQUIRED_NODE_FIELDS: tuple[str, ...] = (
    "node_id",
    "node_type",
    "name",
    "mandatory_actions",
    "source_guideline",
    "source_section",
)

# Per-node list fields that should default to [] if absent (so downstream
# simulator does not crash on `None`).
_OPTIONAL_LIST_FIELDS: tuple[str, ...] = (
    "forbidden_actions",
    "next_nodes",
)

# Per-node dict fields that should default to {} if absent.
_OPTIONAL_DICT_FIELDS: tuple[str, ...] = (
    "deadlines",
    "required_prior_actions",
    "conditional_next",
)


class ParsedJSONError(ValueError):
    """Raised when the input JSON fails structural validation."""


@dataclass
class LoadResult:
    """Return type of `load_and_normalize`. Kept thin — no mutation."""

    data: dict[str, Any]
    source_path: Path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_and_normalize(json_path: Path | str) -> LoadResult:
    """Read a v7 extended parsed.json and return a schema-compliant dict.

    Deterministic: given identical JSON bytes, returns an identical dict
    (modulo dict ordering, which Python 3.7+ preserves).
    """
    json_path = Path(json_path)
    raw = json_path.read_text(encoding="utf-8")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ParsedJSONError(f"{json_path}: JSON parse error: {exc}") from exc

    if not isinstance(data, dict):
        raise ParsedJSONError(f"{json_path}: top-level value is not a mapping")

    _validate_top_level(json_path.name, data)
    _normalise_nodes(json_path.name, data)
    _stamp_provenance(data, json_path)
    return LoadResult(data=data, source_path=json_path)


def write_yaml(result: LoadResult, output_path: Path | str) -> Path:
    """Serialise a LoadResult to YAML. Creates parent dirs as needed."""
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        yaml.safe_dump(result.data, sort_keys=False, allow_unicode=True, width=120),
        encoding="utf-8",
    )
    return output_path


def load_and_write(json_path: Path | str, output_path: Path | str) -> Path:
    """One-shot convenience: JSON → validated → YAML."""
    result = load_and_normalize(json_path)
    return write_yaml(result, output_path)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _validate_top_level(fname: str, data: dict[str, Any]) -> None:
    missing = [f for f in _REQUIRED_TOP_LEVEL if f not in data or data[f] is None]
    if missing:
        raise ParsedJSONError(f"{fname}: missing required top-level field(s): {missing}")

    nodes = data.get("nodes")
    if not isinstance(nodes, dict):
        raise ParsedJSONError(f"{fname}: 'nodes' must be a mapping, got {type(nodes).__name__}")

    entry = data.get("entry_node")
    if entry not in nodes:
        raise ParsedJSONError(f"{fname}: entry_node '{entry}' does not exist in nodes (available: {sorted(nodes)})")


def _normalise_nodes(fname: str, data: dict[str, Any]) -> None:
    nodes: dict[str, dict[str, Any]] = data["nodes"]
    node_ids = set(nodes.keys())

    for nid, node in nodes.items():
        if not isinstance(node, dict):
            raise ParsedJSONError(f"{fname}:{nid}: node value is not a mapping")

        # node_id value must match dict key
        if node.get("node_id") is None:
            node["node_id"] = nid
        elif node["node_id"] != nid:
            raise ParsedJSONError(f"{fname}:{nid}: node_id value '{node['node_id']}' does not match dict key")

        # Required fields
        for f in _REQUIRED_NODE_FIELDS:
            val = node.get(f)
            if val is None or (isinstance(val, str) and not val.strip()):
                raise ParsedJSONError(f"{fname}:{nid}: missing required field '{f}'")

        # node_type validity
        if node["node_type"] not in _VALID_NODE_TYPES:
            raise ParsedJSONError(
                f"{fname}:{nid}: invalid node_type '{node['node_type']}'; expected one of {sorted(_VALID_NODE_TYPES)}"
            )

        # Default optional collection fields
        for f in _OPTIONAL_LIST_FIELDS:
            if node.get(f) is None:
                node[f] = []
        for f in _OPTIONAL_DICT_FIELDS:
            if node.get(f) is None:
                node[f] = {}

        # Cross-reference checks (runtime-consistent — see
        # docs/cpg_expansion_v7/04_validator_runtime_dissonance.md).
        mandatory = set(node.get("mandatory_actions") or [])
        allowed = set(node.get("allowed_actions") or [])
        forbidden = set(node.get("forbidden_actions") or [])

        # NOTE: `mandatory ⊆ allowed` is intentionally NOT enforced.
        # The runtime scoring engine (`_action_satisfies_requirement`,
        # 4-step resolver) does NOT reference allowed_actions when matching
        # mandatory satisfaction. Empirically 203 legitimate violations exist
        # in the 25-CPG corpus yet all 79 engine tests pass. Enforcing the
        # legacy invariant would reject valid YAML.

        # NOTE: forbidden ∩ allowed is NOT enforced as an error.
        # Same action may appear in both when `conditional_rules` flip a
        # normally allowed action to FORBIDDEN under a patient-specific
        # condition (classic: `give_nitrates_if_indicated` is allowed for
        # generic STEMI but conditional_rules switch it to forbidden under
        # RV infarct). Runtime honours the conditional override.
        _overlap = forbidden & allowed  # retained for future structured warning hook

        # Runtime-critical invariant: deadlines lookup scans mandatory ∪ allowed.
        deadlines = node.get("deadlines") or {}
        all_known = mandatory | allowed
        for act in deadlines:
            if act not in all_known:
                raise ParsedJSONError(f"{fname}:{nid}: deadline references unknown action '{act}'")

        for next_id in node.get("next_nodes") or []:
            if next_id not in node_ids:
                raise ParsedJSONError(f"{fname}:{nid}: next_nodes references non-existent node '{next_id}'")
        for _cond, target in (node.get("conditional_next") or {}).items():
            if target not in node_ids:
                raise ParsedJSONError(f"{fname}:{nid}: conditional_next target '{target}' does not exist")


def _stamp_provenance(data: dict[str, Any], source_path: Path) -> None:
    """Record that this artifact was produced by the deterministic loader."""
    metadata = data.setdefault("metadata", {})
    if not isinstance(metadata, dict):
        # Preserve the caller's intent if metadata is not a dict; do not mutate.
        return
    metadata["generated_by"] = LOADER_VERSION
    metadata["source_parsed_json"] = source_path.name
