"""Mutation trace compiler: ScenarioSeed mutation templates -> variant traces.

Each mutation template produces a scenario variant with a specific
perturbation (omission, delay, swap, sequence break) and its expected
violation type.
"""

from __future__ import annotations

from typing import Any

from sgsc.schemas.atom import RecommendationAtom
from sgsc.schemas.seed import MutationTemplate, ScenarioSeed

# ------------------------------------------------------------------
# Mutation -> violation type mapping
# ------------------------------------------------------------------

_MUTATION_VIOLATION_MAP: dict[str, str] = {
    "omit": "OMISSION",
    "delay": "TIMING",
    "swap": "COMMISSION",
    "sequence_break": "SEQUENCE",
}


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def compile_mutation_variant(
    seed: ScenarioSeed,
    mutation: MutationTemplate,
    atoms: list[RecommendationAtom],
) -> dict[str, Any]:
    """Generate a single mutation variant from a seed + mutation template.

    Returns a scenario-like dict describing the mutated trace
    and expected violation.
    """
    variant_id = f"{seed.seed_id}__{mutation.mutation_id}"
    expected_violation = _MUTATION_VIOLATION_MAP.get(mutation.mutation_type, "DEVIATION")

    trace_modifications: dict[str, Any] = {
        "mutation_type": mutation.mutation_type,
        "target_action": mutation.target_action,
    }

    if mutation.mutation_type == "omit":
        trace_modifications["action_removed"] = mutation.target_action
    elif mutation.mutation_type == "delay" and mutation.delay_minutes is not None:
        trace_modifications["delayed_to_minutes"] = mutation.delay_minutes
    elif mutation.mutation_type == "swap":
        trace_modifications["original_action"] = mutation.target_action
        trace_modifications["swapped_with"] = "incorrect_alternative"
    elif mutation.mutation_type == "sequence_break":
        # Find what the target action should come after
        atom_map = {a.atom_id: a for a in atoms}
        for aid in seed.source_atoms:
            atom = atom_map.get(aid)
            if atom and atom.action.canonical_id == mutation.target_action:
                trace_modifications["should_follow"] = atom.sequence.required_prior
                break

    return {
        "variant_id": variant_id,
        "base_seed_id": seed.seed_id,
        "mutation": {
            "mutation_id": mutation.mutation_id,
            "mutation_type": mutation.mutation_type,
            "target_action": mutation.target_action,
            "description": mutation.description,
        },
        "trace_modifications": trace_modifications,
        "expected_violation_type": expected_violation,
    }


def compile_mutations(
    seed: ScenarioSeed,
    atoms: list[RecommendationAtom],
) -> list[dict[str, Any]]:
    """Generate all mutation variants from a seed's templates."""
    return [compile_mutation_variant(seed, mut, atoms) for mut in seed.mutation_templates]


def compile_all_mutations(
    seeds: list[ScenarioSeed],
    atoms: list[RecommendationAtom],
) -> list[dict[str, Any]]:
    """Generate mutation variants across all seeds."""
    variants: list[dict[str, Any]] = []
    for seed in seeds:
        variants.extend(compile_mutations(seed, atoms))
    return variants
