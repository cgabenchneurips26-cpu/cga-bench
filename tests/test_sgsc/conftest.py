"""Shared fixtures for SGSC tests."""

from __future__ import annotations

import pytest
from sgsc.schemas.atom import (
    AtomAction,
    AtomConstraint,
    AtomEvidence,
    AtomSequence,
    PopulationCriteria,
    RecommendationAtom,
    ScenarioHooks,
    SourceReference,
)
from sgsc.schemas.coverage import CoverageItem, CoverageType, CoverageVector
from sgsc.schemas.family import (
    CounterfactualFamily,
    FamilyMember,
    TraceStep,
)
from sgsc.schemas.seed import (
    BoundarySpec,
    MutationTemplate,
    PrivateFields,
    ScenarioSeed,
)

# ------------------------------------------------------------------
# Atom fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def sample_source() -> SourceReference:
    return SourceReference(
        guideline_id="ssc_sepsis_hour1",
        section="Hour-1 Bundle",
        page="e53",
        quote="Administer broad-spectrum antibiotics within 1 hour of sepsis recognition.",
    )


@pytest.fixture()
def sample_atom(sample_source: SourceReference) -> RecommendationAtom:
    return RecommendationAtom(
        atom_id="ssc_2021_rec_hour1_abx",
        source=sample_source,
        population=PopulationCriteria(
            inclusion=["sepsis", "suspected_infection"],
            exclusion=["known_viral_only"],
        ),
        action=AtomAction(
            canonical_id="give_broad_spectrum_antibiotics",
            action_type="medication",
        ),
        constraint=AtomConstraint(
            type="WITHIN",
            activation_event="sepsis_recognition",
            deadline_minutes=60,
        ),
        sequence=AtomSequence(
            required_prior=["obtain_blood_cultures"],
        ),
        evidence=AtomEvidence(
            system="GRADE",
            recommendation_class="I",
            level="B",
        ),
        scenario_hooks=ScenarioHooks(
            boundary_variables=["time_to_abx"],
            counterfactual_pairs=["sepsis_vs_viral"],
        ),
        proposed_by="gemma-4-31b-it",
    )


@pytest.fixture()
def sample_atom_lactate() -> RecommendationAtom:
    return RecommendationAtom(
        atom_id="ssc_2021_rec_hour1_lactate",
        source=SourceReference(
            guideline_id="ssc_sepsis_hour1",
            section="Hour-1 Bundle",
            quote="Measure serum lactate level; remeasure if initial lactate is elevated (>2 mmol/L).",
        ),
        population=PopulationCriteria(
            inclusion=["sepsis", "suspected_infection"],
            exclusion=[],
        ),
        action=AtomAction(
            canonical_id="measure_serum_lactate",
            action_type="lab",
        ),
        constraint=AtomConstraint(type="REQUIRED"),
        evidence=AtomEvidence(
            system="GRADE",
            recommendation_class="I",
            level="C",
        ),
        scenario_hooks=ScenarioHooks(
            boundary_variables=["lactate"],
        ),
    )


@pytest.fixture()
def sample_atom_forbidden() -> RecommendationAtom:
    """Atom representing a forbidden action (contrast in AKI)."""
    return RecommendationAtom(
        atom_id="kdigo_aki_no_contrast",
        source=SourceReference(
            guideline_id="kdigo_aki_full",
            section="Contrast-Induced AKI Prevention",
            quote="Avoid iodinated contrast agents in patients with AKI stage 2 or higher.",
        ),
        population=PopulationCriteria(
            inclusion=["aki_stage_2_or_higher"],
            exclusion=[],
        ),
        action=AtomAction(
            canonical_id="order_ct_with_contrast",
            action_type="imaging",
        ),
        constraint=AtomConstraint(type="FORBIDDEN"),
        evidence=AtomEvidence(
            system="KDIGO",
            recommendation_class="I",
            level="B",
        ),
        scenario_hooks=ScenarioHooks(
            boundary_variables=["creatinine", "gfr"],
            counterfactual_pairs=["aki_vs_normal_renal"],
        ),
    )


@pytest.fixture()
def sample_atoms(
    sample_atom: RecommendationAtom,
    sample_atom_lactate: RecommendationAtom,
    sample_atom_forbidden: RecommendationAtom,
) -> list[RecommendationAtom]:
    """A list of atoms covering WITHIN+sequence, REQUIRED, and FORBIDDEN cases."""
    return [sample_atom, sample_atom_lactate, sample_atom_forbidden]


# ------------------------------------------------------------------
# Seed fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def sample_seed() -> ScenarioSeed:
    return ScenarioSeed(
        seed_id="sepsis_abx_boundary_001",
        source_atoms=["ssc_2021_rec_hour1_abx", "ssc_2021_rec_hour1_lactate"],
        coverage_targets={
            "constraints": ["WITHIN(give_broad_spectrum_antibiotics, 60)", "REQUIRED(measure_serum_lactate)"],
            "boundaries": ["time_to_abx"],
        },
        boundaries=[
            BoundarySpec(variable="time_to_abx", values=[55, 60, 65]),
            BoundarySpec(variable="lactate", values=[1.9, 2.0, 2.1]),
        ],
        patient_state_constraints={"diagnosis": "sepsis", "suspected_infection": True},
        observability={"lactate_value": "measure_serum_lactate"},
        mutation_templates=[
            MutationTemplate(
                mutation_id="omit_abx",
                mutation_type="omit",
                target_action="give_broad_spectrum_antibiotics",
                description="Omit antibiotics entirely",
            ),
            MutationTemplate(
                mutation_id="delay_abx_95min",
                mutation_type="delay",
                target_action="give_broad_spectrum_antibiotics",
                description="Delay antibiotics to 95 minutes",
                delay_minutes=95,
            ),
        ],
        private_fields=PrivateFields(
            activated_constraint_ids=["ssc_within_abx_60", "ssc_required_lactate"],
            expected_trace_family=["sepsis_hour1_compliant"],
        ),
    )


# ------------------------------------------------------------------
# Family fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def sample_family() -> CounterfactualFamily:
    return CounterfactualFamily(
        family_id="aki_contrast_context_pair_001",
        source_atoms=["kdigo_aki_no_contrast"],
        shared_trace_template=[
            TraceStep(time_minutes=0, action_id="initial_assessment"),
            TraceStep(time_minutes=10, action_id="order_ct_with_contrast"),
        ],
        members=[
            FamilyMember(
                scenario_id="normal_renal_ct",
                patient_state={"creatinine": 0.9, "gfr": 90, "aki_stage": 0},
                expected_verdict="conformant",
            ),
            FamilyMember(
                scenario_id="aki_stage2_ct",
                patient_state={"creatinine": 3.5, "gfr": 25, "aki_stage": 2},
                expected_verdict="commission_violation",
            ),
        ],
        pivot_variable="aki_stage",
        pivot_threshold=2,
    )


# ------------------------------------------------------------------
# Coverage fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def sample_coverage_items() -> list[CoverageItem]:
    return [
        CoverageItem(
            item_id="rec:ssc_abx",
            coverage_type=CoverageType.RECOMMENDATION,
            description="SSC antibiotics recommendation covered",
            source_atom_id="ssc_2021_rec_hour1_abx",
        ),
        CoverageItem(
            item_id="cst:within_abx_60",
            coverage_type=CoverageType.CONSTRAINT,
            description="WITHIN(abx, 60min) tested",
            source_atom_id="ssc_2021_rec_hour1_abx",
        ),
        CoverageItem(
            item_id="bnd:time_to_abx_boundary",
            coverage_type=CoverageType.BOUNDARY,
            description="Boundary values for time_to_abx tested",
        ),
        CoverageItem(
            item_id="mut:omit_abx",
            coverage_type=CoverageType.MUTATION,
            description="Omission mutation for antibiotics",
        ),
        CoverageItem(
            item_id="src:ssc_abx_quote",
            coverage_type=CoverageType.SOURCE,
            description="Source quote link verified",
            source_atom_id="ssc_2021_rec_hour1_abx",
        ),
    ]


@pytest.fixture()
def sample_coverage_vectors() -> list[CoverageVector]:
    return [
        CoverageVector(
            scenario_id="sepsis_abx_boundary_001",
            covered_items=frozenset(
                {"rec:ssc_abx", "cst:within_abx_60", "bnd:time_to_abx_boundary", "src:ssc_abx_quote"}
            ),
        ),
        CoverageVector(
            scenario_id="sepsis_omit_abx_001",
            covered_items=frozenset({"rec:ssc_abx", "mut:omit_abx", "src:ssc_abx_quote"}),
        ),
    ]
