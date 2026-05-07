"""Deterministic counterfactual family compiler.

Generates matched-pair ``CounterfactualFamily`` instances from atoms
with exclusion criteria or WITHIN constraints.
"""

from __future__ import annotations

from sgsc.schemas.atom import RecommendationAtom
from sgsc.schemas.family import (
    CounterfactualFamily,
    FamilyMember,
    TraceStep,
)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _build_trace_from_atom(atom: RecommendationAtom) -> list[TraceStep]:
    """Build a shared trace template from an atom's action and priors."""
    steps: list[TraceStep] = []
    time = 0.0

    # Required prior actions first
    for prior_id in atom.sequence.required_prior:
        steps.append(TraceStep(time_minutes=time, action_id=prior_id))
        time += 10.0

    # The atom's own action
    if atom.constraint.deadline_minutes is not None:
        # Place action at 60% of deadline to be compliant
        time = atom.constraint.deadline_minutes * 0.6
    else:
        time += 10.0

    steps.append(TraceStep(time_minutes=time, action_id=atom.action.canonical_id))
    return steps


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def compile_exclusion_families(
    atoms: list[RecommendationAtom],
) -> list[CounterfactualFamily]:
    """Generate families from atoms with population exclusion criteria.

    For each atom with exclusions:
    - "eligible" member: inclusion met, exclusion NOT met -> conformant
    - "contraindicated" member: inclusion met, exclusion IS met -> commission_violation
    """
    families: list[CounterfactualFamily] = []

    for atom in atoms:
        if not atom.population.exclusion:
            continue
        if not atom.scenario_hooks.counterfactual_pairs:
            continue

        trace = _build_trace_from_atom(atom)
        pivot_var = atom.population.exclusion[0]  # Use first exclusion as pivot

        eligible = FamilyMember(
            scenario_id=f"{atom.atom_id}_eligible",
            patient_state={"meets_inclusion": True, pivot_var: False},
            expected_verdict="conformant",
        )
        contraindicated = FamilyMember(
            scenario_id=f"{atom.atom_id}_contraindicated",
            patient_state={"meets_inclusion": True, pivot_var: True},
            expected_verdict="commission_violation",
        )

        family = CounterfactualFamily(
            family_id=f"{atom.atom_id}_exclusion_pair",
            source_atoms=[atom.atom_id],
            shared_trace_template=trace,
            members=[eligible, contraindicated],
            pivot_variable=pivot_var,
        )
        families.append(family)

    return families


def compile_timing_families(
    atoms: list[RecommendationAtom],
) -> list[CounterfactualFamily]:
    """Generate families from atoms with WITHIN deadline constraints.

    For each atom with WITHIN:
    - "timely" member: action within deadline -> conformant
    - "late" member: action past deadline -> timing_violation
    """
    families: list[CounterfactualFamily] = []

    for atom in atoms:
        if atom.constraint.type != "WITHIN":
            continue
        if atom.constraint.deadline_minutes is None:
            continue

        deadline = atom.constraint.deadline_minutes

        # Timely trace: action at 60% of deadline
        timely_trace = list(_build_trace_from_atom(atom))

        # Late trace: same priors but action at 150% of deadline
        late_trace: list[TraceStep] = []
        for step in timely_trace[:-1]:
            late_trace.append(step)
        late_trace.append(
            TraceStep(
                time_minutes=deadline * 1.5,
                action_id=atom.action.canonical_id,
            )
        )

        timely = FamilyMember(
            scenario_id=f"{atom.atom_id}_timely",
            patient_state={"action_time": deadline * 0.6},
            expected_verdict="conformant",
        )
        late = FamilyMember(
            scenario_id=f"{atom.atom_id}_late",
            patient_state={"action_time": deadline * 1.5},
            expected_verdict="timing_violation",
        )

        family = CounterfactualFamily(
            family_id=f"{atom.atom_id}_timing_pair",
            source_atoms=[atom.atom_id],
            shared_trace_template=timely_trace,
            members=[timely, late],
            pivot_variable="action_time",
            pivot_threshold=float(deadline),
        )
        families.append(family)

    return families


def compile_sequence_families(
    atoms: list[RecommendationAtom],
) -> list[CounterfactualFamily]:
    """Generate families from atoms with BEFORE/sequence constraints.

    For each atom with required_prior or BEFORE:
    - "correct_order" member: priors before action -> conformant
    - "wrong_order" member: action before priors -> sequence_violation
    """
    families: list[CounterfactualFamily] = []

    for atom in atoms:
        has_sequence = bool(atom.sequence.required_prior) or (
            atom.constraint.type == "BEFORE" and bool(atom.sequence.before)
        )
        if not has_sequence:
            continue

        # Build correct-order trace
        correct_trace: list[TraceStep] = []
        time = 0.0
        for prior_id in atom.sequence.required_prior:
            correct_trace.append(TraceStep(time_minutes=time, action_id=prior_id))
            time += 10.0
        correct_trace.append(TraceStep(time_minutes=time, action_id=atom.action.canonical_id))

        # Build wrong-order trace (action first, then priors)
        wrong_trace: list[TraceStep] = []
        wrong_trace.append(TraceStep(time_minutes=0.0, action_id=atom.action.canonical_id))
        time = 10.0
        for prior_id in atom.sequence.required_prior:
            wrong_trace.append(TraceStep(time_minutes=time, action_id=prior_id))
            time += 10.0

        correct = FamilyMember(
            scenario_id=f"{atom.atom_id}_correct_order",
            patient_state={"action_order": "correct"},
            expected_verdict="conformant",
        )
        wrong = FamilyMember(
            scenario_id=f"{atom.atom_id}_wrong_order",
            patient_state={"action_order": "reversed"},
            expected_verdict="sequence_violation",
        )

        family = CounterfactualFamily(
            family_id=f"{atom.atom_id}_sequence_pair",
            source_atoms=[atom.atom_id],
            shared_trace_template=correct_trace,
            members=[correct, wrong],
            pivot_variable="action_order",
        )
        families.append(family)

    return families


def compile_alternative_families(
    atoms: list[RecommendationAtom],
) -> list[CounterfactualFamily]:
    """Generate families from atoms with counterfactual_pairs in scenario_hooks.

    For each pair name, create a 2-member family with matching action
    vs alternative action.
    """
    families: list[CounterfactualFamily] = []

    for atom in atoms:
        for pair_name in atom.scenario_hooks.counterfactual_pairs:
            trace = _build_trace_from_atom(atom)

            primary = FamilyMember(
                scenario_id=f"{atom.atom_id}_{pair_name}_primary",
                patient_state={"branch": "primary", "pair": pair_name},
                expected_verdict="conformant",
            )
            alternative = FamilyMember(
                scenario_id=f"{atom.atom_id}_{pair_name}_alternative",
                patient_state={"branch": "alternative", "pair": pair_name},
                expected_verdict="alternative_path",
            )

            family = CounterfactualFamily(
                family_id=f"{atom.atom_id}_{pair_name}_branch",
                source_atoms=[atom.atom_id],
                shared_trace_template=trace,
                members=[primary, alternative],
                pivot_variable=pair_name,
            )
            families.append(family)

    return families


def compile_families(
    atoms: list[RecommendationAtom],
) -> list[CounterfactualFamily]:
    """Generate all counterfactual families from atoms.

    Combines exclusion-based, timing-based, sequence-based, and alternative families.
    """
    families: list[CounterfactualFamily] = []
    families.extend(compile_exclusion_families(atoms))
    families.extend(compile_timing_families(atoms))
    families.extend(compile_sequence_families(atoms))
    families.extend(compile_alternative_families(atoms))
    return families
