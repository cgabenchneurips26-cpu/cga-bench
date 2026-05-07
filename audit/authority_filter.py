"""Authority filter for the E9 High-Authority Core Robustness audit.

Reads ``audit/authority_taxonomy.yaml`` and provides:

- ``tier_for(constraint)`` -- classify a single ``DerivedConstraint`` as
  ``"high"``, ``"low"``, or ``"unknown"`` using the declarative rule set.
- ``filter_high_authority(set)`` -- return a new ``DerivedConstraintSet``
  containing only the high-authority constraints (low and unknown dropped).

The two helpers are the only audit-side surface area introduced by E9. They
deliberately re-use the ``recommendation_class``, ``evidence_level``,
``source_guideline`` and ``authority_tier`` fields propagated by
``cpg_model.constraint_derivation``; this module never re-walks the YAML
graph.

Spec: docs/attack_gap_exp_exp/260430_e9_High-Authority_Core_Robustness.md
"""

from __future__ import annotations

from dataclasses import replace
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from cpg_model.constraint_derivation import DerivedConstraint, DerivedConstraintSet

_DEFAULT_TAXONOMY_PATH = Path(__file__).parent / "authority_taxonomy.yaml"

HIGH = "high"
LOW = "low"
UNKNOWN = "unknown"

# Active taxonomy path -- mutable so threshold-sweep callers can swap files
# without rebuilding the module. ``set_taxonomy_path`` clears the lru_cache.
_ACTIVE_TAXONOMY_PATH: Path = _DEFAULT_TAXONOMY_PATH


def set_taxonomy_path(path: Path | str | None) -> None:
    """Override which taxonomy YAML ``tier_for`` consults.

    Pass ``None`` to revert to the default path. Always clears the cache.
    """
    global _ACTIVE_TAXONOMY_PATH
    _ACTIVE_TAXONOMY_PATH = (
        Path(path) if path is not None else _DEFAULT_TAXONOMY_PATH
    )
    _load_taxonomy.cache_clear()


def clear_taxonomy_cache() -> None:
    """Drop the cached taxonomy contents (forces re-read on next call)."""
    _load_taxonomy.cache_clear()


def get_taxonomy_path() -> Path:
    """Return the currently active taxonomy path (for logging / metadata)."""
    return _ACTIVE_TAXONOMY_PATH


@lru_cache(maxsize=1)
def _load_taxonomy() -> dict[str, Any]:
    path = _ACTIVE_TAXONOMY_PATH
    with open(path) as f:
        data = yaml.safe_load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Authority taxonomy at {path} is not a mapping")
    return data


def _rule_matches(rule: dict[str, Any], constraint: DerivedConstraint) -> bool:
    match = rule.get("match", {}) or {}

    rc_in = match.get("recommendation_class_in")
    if rc_in is not None:
        if (constraint.recommendation_class or "").strip() not in rc_in:
            return False

    el_in = match.get("evidence_level_in")
    if el_in is not None:
        if (constraint.evidence_level or "").strip() not in el_in:
            return False

    sg_contains = match.get("source_guideline_contains_any")
    if sg_contains is not None:
        sg = (constraint.source_guideline or "").lower()
        if not any(tok.lower() in sg for tok in sg_contains):
            return False

    prov_prefix = match.get("provenance_starts_with")
    if prov_prefix is not None:
        if not constraint.provenance.startswith(prov_prefix):
            return False

    # If a rule declares no match keys, treat it as no-op (defensive).
    if not match:
        return False

    return True


def tier_for(constraint: DerivedConstraint) -> str:
    """Classify a single constraint per ``authority_taxonomy.yaml``.

    The taxonomy file is the source of truth. The engine-side
    ``authority_tier`` is ignored here so taxonomy edits propagate without
    re-deriving.
    """
    taxonomy = _load_taxonomy()
    for rule in taxonomy.get("high_authority_rules", []) or []:
        if _rule_matches(rule, constraint):
            return HIGH

    has_any_metadata = bool(
        (constraint.recommendation_class or "").strip()
        or (constraint.evidence_level or "").strip()
        or (constraint.source_guideline or "").strip()
    )
    return LOW if has_any_metadata else UNKNOWN


def annotate(constraints: list[DerivedConstraint]) -> list[DerivedConstraint]:
    """Return a new list with ``authority_tier`` overwritten by the taxonomy."""
    return [replace(c, authority_tier=tier_for(c)) for c in constraints]


def filter_high_authority(
    cset: DerivedConstraintSet,
    keep_unknown: bool = False,
) -> DerivedConstraintSet:
    """Return a copy of ``cset`` with only high-authority constraints retained.

    ``keep_unknown=True`` keeps constraints whose tier is ``"unknown"`` -- used
    for the "unknown" sensitivity column in the appendix table.
    """
    keep_tiers = {HIGH, UNKNOWN} if keep_unknown else {HIGH}

    def _keep(c: DerivedConstraint) -> DerivedConstraint | None:
        tier = tier_for(c)
        if tier in keep_tiers:
            return replace(c, authority_tier=tier)
        return None

    out = DerivedConstraintSet(scenario_id=cset.scenario_id, graph_id=cset.graph_id)
    for src, dst_attr in (
        (cset.forbidden, "forbidden"),
        (cset.required, "required"),
        (cset.before, "before"),
        (cset.within, "within"),
        (cset.expected, "expected"),
        (cset.conflicts, "conflicts"),
    ):
        kept: list[DerivedConstraint] = []
        for c in src:
            updated = _keep(c)
            if updated is not None:
                kept.append(updated)
        getattr(out, dst_attr).extend(kept)

    out.total_rules_evaluated = cset.total_rules_evaluated
    out.total_rules_triggered = cset.total_rules_triggered
    return out


def tier_counts(cset: DerivedConstraintSet) -> dict[str, int]:
    """Return ``{tier: count}`` summary across the whole set."""
    counts: dict[str, int] = {HIGH: 0, LOW: 0, UNKNOWN: 0}
    for c in cset.all_constraints():
        counts[tier_for(c)] = counts.get(tier_for(c), 0) + 1
    return counts
