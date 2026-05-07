"""Conditional action placeholders + runtime-consistent invariant policy.

Single source of truth for three static-check tools that must stay consistent
with the runtime scoring engine:

  - scripts/ci/validate_cpg_schema.py
  - semantic_layer/parsed_json_loader.py
  - semantic_layer/cpg_yaml_generator.py

## Why this module exists (see docs/cpg_expansion_v7/04_validator_runtime_dissonance.md)

The legacy validator enforced `mandatory_actions ⊆ allowed_actions` as a hard
error. Empirically this invariant is **not** a runtime invariant — the runtime
scoring engine (`assessor_core/violations.py::_action_satisfies_requirement`,
4-step semantic resolver) does not reference `allowed_actions` when matching
performed actions against mandatory requirements. Running the full engine test
suite against the 6 CPG YAMLs that violated the legacy invariant produced
**79/79 pass**, confirming runtime correctness. The static check was a false
positive on 203 distinct action identifiers across the 25-CPG corpus.

The policy encoded here replaces the over-strict check with the set of
invariants the runtime actually relies on.

## Runtime-critical invariants (keep enforced)

  - `forbidden_actions ∩ allowed_actions = ∅`  (stepper uses both sets)
  - `deadlines.keys() ⊆ mandatory_actions ∪ allowed_actions`  (deadline lookup)
  - `next_nodes / conditional_next` targets exist in the node set
  - Top-level required fields + per-node required fields + node_type validity

## Runtime-inconsistent invariant (remove)

  - `mandatory_actions ⊆ allowed_actions` — scoring ignores this.

## Semantic placeholders (documented, not enforced here)

Runtime has ONE explicit conditional handler:

  - `start_vasopressor_if_hypotensive` — matches any `start_vasopressor_*`
    concrete action when `state.vitals.map_mmhg < 65`
    (see violations.py:642)

Other `*_if_*` action_ids (e.g. `remeasure_lactate_if_elevated`,
`give_nitrates_if_indicated`) are resolved via the ActionNormalizer alias
layer or direct performed-key match, not by a dedicated handler. This module
documents them so reviewers can audit every placeholder.
"""

from __future__ import annotations

# Conditional placeholders with a dedicated runtime handler in
# `assessor_core/violations.py::_action_satisfies_requirement`.
# Keep this list in sync with the explicit `if required_key == "..."` branches.
RUNTIME_HANDLED_PLACEHOLDERS: frozenset[str] = frozenset(
    {
        "start_vasopressor_if_hypotensive",
    }
)

# Conditional placeholder suffixes observed across the 25-CPG corpus.
# Included for documentation only; the loader/validator do NOT use this list
# to gate anything (the over-strict check was removed entirely).
# Expand as new placeholders appear.
OBSERVED_CONDITIONAL_SUFFIXES: tuple[str, ...] = (
    "_if_applicable",
    "_if_appropriate",
    "_if_bp",  # matches phrases like "_if_bp_elevated", "_if_bp_controlled"
    "_if_deterioration",
    "_if_elevated",
    "_if_hypotensive",
    "_if_indicated",
    "_if_needed",
    "_if_no",  # matches phrases like "_if_no_contraindication"
    "_if_proceeding",
    "_if_unstable",
)


def is_runtime_handled_placeholder(action_id: str) -> bool:
    """True iff `action_id` has a dedicated runtime handler.

    Used only for documentation and reviewer-facing audit reports. The loader
    and validator do not gate on this — they trust the runtime resolver to
    handle unmatched mandatory actions via normalisation / alias / handler.
    """
    return action_id in RUNTIME_HANDLED_PLACEHOLDERS


def looks_like_conditional_placeholder(action_id: str) -> bool:
    """True iff `action_id` ends with one of the observed conditional suffixes.

    Documentation helper. Not used to gate validation.
    """
    return any(action_id.endswith(s) for s in OBSERVED_CONDITIONAL_SUFFIXES)
