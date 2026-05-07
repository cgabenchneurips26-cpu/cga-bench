"""Coverage tracker: extract and track coverage types from atoms and seeds.

Extracts ``CoverageItem`` instances from atoms, seeds, and families,
tracks which items are covered, and reports gaps.

10 ``CoverageType`` dimensions are actively extracted:
RECOMMENDATION, CONSTRAINT, GUARD_TRUE, GUARD_FALSE, BOUNDARY,
ALTERNATIVE, MUTATION, SOURCE, TIMING_COMPLIANT, TIMING_VIOLATED.
GUARD (legacy singleton) is preserved for backward compatibility.
ORDER_COMPLIANT and ORDER_VIOLATED are extracted when sequence constraints exist.
"""

from __future__ import annotations

from sgsc.schemas.atom import RecommendationAtom
from sgsc.schemas.coverage import CoverageItem, CoverageType, CoverageVector
from sgsc.schemas.family import CounterfactualFamily
from sgsc.schemas.seed import ScenarioSeed

# ------------------------------------------------------------------
# Item extraction
# ------------------------------------------------------------------


def extract_recommendation_items(
    atoms: list[RecommendationAtom],
) -> list[CoverageItem]:
    """Extract RECOMMENDATION coverage items — one per atom."""
    return [
        CoverageItem(
            item_id=f"rec:{atom.atom_id}",
            coverage_type=CoverageType.RECOMMENDATION,
            source_atom_id=atom.atom_id,
            description=f"Recommendation {atom.action.canonical_id}",
        )
        for atom in atoms
    ]


def extract_constraint_items(
    atoms: list[RecommendationAtom],
) -> list[CoverageItem]:
    """Extract CONSTRAINT items — one per unique constraint type + action."""
    items: list[CoverageItem] = []
    for atom in atoms:
        items.append(
            CoverageItem(
                item_id=f"cst:{atom.constraint.type}:{atom.action.canonical_id}",
                coverage_type=CoverageType.CONSTRAINT,
                source_atom_id=atom.atom_id,
                description=f"{atom.constraint.type}({atom.action.canonical_id})",
            )
        )
        if atom.constraint.type == "WITHIN" and atom.constraint.deadline_minutes is not None:
            items.append(
                CoverageItem(
                    item_id=f"cst:WITHIN:{atom.action.canonical_id}:{atom.constraint.deadline_minutes}",
                    coverage_type=CoverageType.CONSTRAINT,
                    source_atom_id=atom.atom_id,
                    description=(f"WITHIN({atom.action.canonical_id}, {atom.constraint.deadline_minutes}min)"),
                )
            )
    return items


def extract_guard_items(
    atoms: list[RecommendationAtom],
) -> list[CoverageItem]:
    """Extract GUARD items — one per atom with exclusion criteria."""
    return [
        CoverageItem(
            item_id=f"guard:{atom.atom_id}:{excl}",
            coverage_type=CoverageType.GUARD,
            source_atom_id=atom.atom_id,
            description=f"Guard {excl} for {atom.action.canonical_id}",
        )
        for atom in atoms
        for excl in atom.population.exclusion
    ]


def extract_boundary_items(
    atoms: list[RecommendationAtom],
) -> list[CoverageItem]:
    """Extract BOUNDARY items — one per boundary variable per atom."""
    return [
        CoverageItem(
            item_id=f"bnd:{atom.atom_id}:{var}",
            coverage_type=CoverageType.BOUNDARY,
            source_atom_id=atom.atom_id,
            description=f"Boundary {var} for {atom.action.canonical_id}",
        )
        for atom in atoms
        for var in atom.scenario_hooks.boundary_variables
    ]


def extract_mutation_items(
    seeds: list[ScenarioSeed],
) -> list[CoverageItem]:
    """Extract MUTATION items — one per mutation template per seed."""
    return [
        CoverageItem(
            item_id=f"mut:{seed.seed_id}:{mut.mutation_id}",
            coverage_type=CoverageType.MUTATION,
            source_atom_id=seed.source_atoms[0] if seed.source_atoms else "",
            description=f"{mut.mutation_type} on {mut.target_action}",
        )
        for seed in seeds
        for mut in seed.mutation_templates
    ]


def extract_source_items(
    atoms: list[RecommendationAtom],
) -> list[CoverageItem]:
    """Extract SOURCE items — one per atom (verifies source linkage)."""
    return [
        CoverageItem(
            item_id=f"src:{atom.atom_id}",
            coverage_type=CoverageType.SOURCE,
            source_atom_id=atom.atom_id,
            description=f"Source quote for {atom.action.canonical_id}",
        )
        for atom in atoms
    ]


def extract_guard_pair_items(
    atoms: list[RecommendationAtom],
) -> list[CoverageItem]:
    """Extract GUARD_TRUE + GUARD_FALSE paired items per exclusion."""
    items: list[CoverageItem] = []
    for atom in atoms:
        for excl in atom.population.exclusion:
            items.append(
                CoverageItem(
                    item_id=f"guard_true:{atom.atom_id}:{excl}",
                    coverage_type=CoverageType.GUARD_TRUE,
                    source_atom_id=atom.atom_id,
                    description=f"Guard TRUE (exclusion met) for {excl} on {atom.action.canonical_id}",
                )
            )
            items.append(
                CoverageItem(
                    item_id=f"guard_false:{atom.atom_id}:{excl}",
                    coverage_type=CoverageType.GUARD_FALSE,
                    source_atom_id=atom.atom_id,
                    description=f"Guard FALSE (eligible) for {excl} on {atom.action.canonical_id}",
                )
            )
    return items


def extract_timing_pair_items(
    atoms: list[RecommendationAtom],
) -> list[CoverageItem]:
    """Extract TIMING_COMPLIANT + TIMING_VIOLATED paired items."""
    items: list[CoverageItem] = []
    for atom in atoms:
        if atom.constraint.type == "WITHIN" and atom.constraint.deadline_minutes is not None:
            items.append(
                CoverageItem(
                    item_id=f"timing_ok:{atom.atom_id}",
                    coverage_type=CoverageType.TIMING_COMPLIANT,
                    source_atom_id=atom.atom_id,
                    description=f"Timely {atom.action.canonical_id} within {atom.constraint.deadline_minutes}min",
                )
            )
            items.append(
                CoverageItem(
                    item_id=f"timing_viol:{atom.atom_id}",
                    coverage_type=CoverageType.TIMING_VIOLATED,
                    source_atom_id=atom.atom_id,
                    description=f"Late {atom.action.canonical_id} past {atom.constraint.deadline_minutes}min",
                )
            )
    return items


def extract_order_pair_items(
    atoms: list[RecommendationAtom],
) -> list[CoverageItem]:
    """Extract ORDER_COMPLIANT + ORDER_VIOLATED paired items for sequence constraints."""
    items: list[CoverageItem] = []
    for atom in atoms:
        has_sequence = bool(atom.sequence.required_prior) or (
            atom.constraint.type == "BEFORE" and bool(atom.sequence.before)
        )
        if has_sequence:
            items.append(
                CoverageItem(
                    item_id=f"order_ok:{atom.atom_id}",
                    coverage_type=CoverageType.ORDER_COMPLIANT,
                    source_atom_id=atom.atom_id,
                    description=f"Correct order for {atom.action.canonical_id}",
                )
            )
            items.append(
                CoverageItem(
                    item_id=f"order_viol:{atom.atom_id}",
                    coverage_type=CoverageType.ORDER_VIOLATED,
                    source_atom_id=atom.atom_id,
                    description=f"Wrong order for {atom.action.canonical_id}",
                )
            )
    return items


def extract_alternative_items(
    atoms: list[RecommendationAtom],
) -> list[CoverageItem]:
    """Extract ALTERNATIVE items from atoms with counterfactual_pairs."""
    items: list[CoverageItem] = []
    for atom in atoms:
        for pair in atom.scenario_hooks.counterfactual_pairs:
            items.append(
                CoverageItem(
                    item_id=f"alt:{atom.atom_id}:{pair}",
                    coverage_type=CoverageType.ALTERNATIVE,
                    source_atom_id=atom.atom_id,
                    description=f"Alternative branch {pair} for {atom.action.canonical_id}",
                )
            )
    return items


def extract_all_items(
    atoms: list[RecommendationAtom],
    seeds: list[ScenarioSeed] | None = None,
) -> list[CoverageItem]:
    """Extract all coverage types from atoms and seeds."""
    items: list[CoverageItem] = []
    items.extend(extract_recommendation_items(atoms))
    items.extend(extract_constraint_items(atoms))
    items.extend(extract_guard_items(atoms))  # Legacy singleton
    items.extend(extract_guard_pair_items(atoms))  # MC/DC pairs
    items.extend(extract_boundary_items(atoms))
    items.extend(extract_alternative_items(atoms))  # Now active
    items.extend(extract_source_items(atoms))
    items.extend(extract_timing_pair_items(atoms))  # Timing pairs
    items.extend(extract_order_pair_items(atoms))  # Order pairs
    if seeds:
        items.extend(extract_mutation_items(seeds))
    return items


# ------------------------------------------------------------------
# Coverage vector construction
# ------------------------------------------------------------------


def build_seed_coverage_vector(
    seed: ScenarioSeed,
    atoms: list[RecommendationAtom],
) -> CoverageVector:
    """Compute which coverage items a single seed covers."""
    atom_map = {a.atom_id: a for a in atoms}
    covered: set[str] = set()

    for aid in seed.source_atoms:
        atom = atom_map.get(aid)
        if not atom:
            continue

        # RECOMMENDATION
        covered.add(f"rec:{aid}")

        # CONSTRAINT
        covered.add(f"cst:{atom.constraint.type}:{atom.action.canonical_id}")
        if atom.constraint.type == "WITHIN" and atom.constraint.deadline_minutes is not None:
            covered.add(f"cst:WITHIN:{atom.action.canonical_id}:{atom.constraint.deadline_minutes}")

        # SOURCE (if quote present)
        if atom.source.quote:
            covered.add(f"src:{aid}")

    # BOUNDARY
    for bnd in seed.boundaries:
        for aid in seed.source_atoms:
            atom = atom_map.get(aid)
            if atom and bnd.variable in atom.scenario_hooks.boundary_variables:
                covered.add(f"bnd:{aid}:{bnd.variable}")

    # MUTATION
    for mut in seed.mutation_templates:
        covered.add(f"mut:{seed.seed_id}:{mut.mutation_id}")

    return CoverageVector(
        scenario_id=seed.seed_id,
        covered_items=frozenset(covered),
    )


def build_family_coverage_vector(
    family: CounterfactualFamily,
    atoms: list[RecommendationAtom],
) -> CoverageVector:
    """Compute which coverage items a counterfactual family covers."""
    atom_map = {a.atom_id: a for a in atoms}
    covered: set[str] = set()

    for aid in family.source_atoms:
        atom = atom_map.get(aid)
        if not atom:
            continue
        covered.add(f"rec:{aid}")
        covered.add(f"cst:{atom.constraint.type}:{atom.action.canonical_id}")

        # GUARD (exclusion-based families) — legacy
        for excl in atom.population.exclusion:
            covered.add(f"guard:{aid}:{excl}")

    # Guard pairs (from exclusion families)
    for aid in family.source_atoms:
        atom = atom_map.get(aid)
        if not atom:
            continue
        for excl in atom.population.exclusion:
            verdicts = {m.expected_verdict for m in family.members}
            if "commission_violation" in verdicts:
                covered.add(f"guard_true:{aid}:{excl}")
            if "conformant" in verdicts:
                covered.add(f"guard_false:{aid}:{excl}")

    # Timing pairs (from timing families)
    for aid in family.source_atoms:
        atom = atom_map.get(aid)
        if not atom:
            continue
        if atom.constraint.type == "WITHIN":
            verdicts = {m.expected_verdict for m in family.members}
            if "conformant" in verdicts:
                covered.add(f"timing_ok:{aid}")
            if "timing_violation" in verdicts:
                covered.add(f"timing_viol:{aid}")

    # Alternative (from counterfactual_pairs)
    for aid in family.source_atoms:
        atom = atom_map.get(aid)
        if not atom:
            continue
        for pair in atom.scenario_hooks.counterfactual_pairs:
            covered.add(f"alt:{aid}:{pair}")

    return CoverageVector(
        scenario_id=family.family_id,
        covered_items=frozenset(covered),
    )
