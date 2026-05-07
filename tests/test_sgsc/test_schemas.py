"""Tests for SGSC schema definitions — serialization, validation, edge cases."""

from __future__ import annotations

import hashlib
import json

from pydantic import ValidationError
import pytest
from sgsc.schemas.atom import (
    AtomAction,
    AtomConstraint,
    AtomEvidence,
    PopulationCriteria,
    RecommendationAtom,
    SourceReference,
)
from sgsc.schemas.coverage import (
    CoverageReport,
    CoverageType,
    CoverageVector,
)
from sgsc.schemas.family import (
    CounterfactualFamily,
    FamilyMember,
    TraceStep,
)
from sgsc.schemas.quality import (
    AGREEScores,
    ExtractionRisk,
    GuidelineQualityCard,
    RIGHTItems,
    ScenarioPolicy,
)
from sgsc.schemas.seed import (
    BoundarySpec,
    MutationTemplate,
    ScenarioSeed,
)

# ============================================================
# SourceReference
# ============================================================


class TestSourceReference:
    def test_auto_quote_hash(self) -> None:
        ref = SourceReference(guideline_id="ssc", section="Hour-1", quote="Give antibiotics.")
        expected_hash = hashlib.sha256(b"Give antibiotics.").hexdigest()
        assert ref.quote_hash == expected_hash

    def test_explicit_quote_hash_preserved(self) -> None:
        ref = SourceReference(
            guideline_id="ssc",
            section="Hour-1",
            quote="Give antibiotics.",
            quote_hash="custom_hash_value",
        )
        assert ref.quote_hash == "custom_hash_value"

    def test_empty_quote_rejected(self) -> None:
        with pytest.raises(ValidationError):
            SourceReference(guideline_id="ssc", section="Hour-1", quote="")


# ============================================================
# AtomConstraint
# ============================================================


class TestAtomConstraint:
    @pytest.mark.parametrize("ctype", ["FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN", "EXPECTED"])
    def test_valid_constraint_types(self, ctype: str) -> None:
        c = AtomConstraint(type=ctype)
        assert c.type == ctype

    def test_invalid_constraint_type_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AtomConstraint(type="INVALID")

    def test_within_with_deadline(self) -> None:
        c = AtomConstraint(type="WITHIN", deadline_minutes=60, activation_event="sepsis_recognition")
        assert c.deadline_minutes == 60

    def test_negative_deadline_rejected(self) -> None:
        with pytest.raises(ValidationError):
            AtomConstraint(type="WITHIN", deadline_minutes=-10)


# ============================================================
# RecommendationAtom
# ============================================================


class TestRecommendationAtom:
    def test_roundtrip_json(self, sample_atom: RecommendationAtom) -> None:
        """JSON serialize -> deserialize -> identical."""
        json_str = sample_atom.model_dump_json()
        restored = RecommendationAtom.model_validate_json(json_str)
        assert restored.atom_id == sample_atom.atom_id
        assert restored.source.quote_hash == sample_atom.source.quote_hash
        assert restored.constraint.type == sample_atom.constraint.type

    def test_roundtrip_dict(self, sample_atom: RecommendationAtom) -> None:
        d = sample_atom.model_dump()
        restored = RecommendationAtom.model_validate(d)
        assert restored == sample_atom

    def test_to_flat_dict(self, sample_atom: RecommendationAtom) -> None:
        flat = sample_atom.to_flat_dict()
        assert flat["source_guideline_id"] == "ssc_sepsis_hour1"
        assert flat["action_canonical_id"] == "give_broad_spectrum_antibiotics"
        assert flat["constraint_type"] == "WITHIN"

    def test_mutable_provenance_fields(self, sample_atom: RecommendationAtom) -> None:
        sample_atom.agreement_score = 0.85
        sample_atom.entailment_status = "entailed"
        assert sample_atom.agreement_score == 0.85
        assert sample_atom.entailment_status == "entailed"

    def test_agreement_score_bounds(self) -> None:
        with pytest.raises(ValidationError):
            RecommendationAtom(
                atom_id="test",
                source=SourceReference(guideline_id="x", section="y", quote="z"),
                population=PopulationCriteria(),
                action=AtomAction(canonical_id="a", action_type="lab"),
                constraint=AtomConstraint(type="REQUIRED"),
                evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="A"),
                agreement_score=1.5,
            )

    def test_multiple_atoms_unique_hashes(
        self, sample_atom: RecommendationAtom, sample_atom_lactate: RecommendationAtom
    ) -> None:
        assert sample_atom.source.quote_hash != sample_atom_lactate.source.quote_hash


# ============================================================
# ScenarioSeed
# ============================================================


class TestScenarioSeed:
    def test_roundtrip_json(self, sample_seed: ScenarioSeed) -> None:
        json_str = sample_seed.model_dump_json()
        restored = ScenarioSeed.model_validate_json(json_str)
        assert restored.seed_id == sample_seed.seed_id
        assert len(restored.mutation_templates) == 2

    def test_private_fields_separate(self, sample_seed: ScenarioSeed) -> None:
        d = sample_seed.model_dump()
        assert "private_fields" in d
        assert "activated_constraint_ids" in d["private_fields"]
        # Simulate stripping private fields for agent-visible YAML
        d_visible = {k: v for k, v in d.items() if k != "private_fields"}
        assert "private_fields" not in d_visible

    def test_empty_source_atoms_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ScenarioSeed(seed_id="bad", source_atoms=[])

    def test_boundary_spec_requires_values(self) -> None:
        with pytest.raises(ValidationError):
            BoundarySpec(variable="x", values=[])


class TestMutationTemplate:
    def test_valid_mutation_types(self) -> None:
        for mt in ("omit", "delay", "swap", "sequence_break"):
            m = MutationTemplate(mutation_id="t", mutation_type=mt, target_action="a")
            assert m.mutation_type == mt

    def test_invalid_mutation_type_rejected(self) -> None:
        with pytest.raises(ValueError, match="mutation_type must be one of"):
            MutationTemplate(mutation_id="t", mutation_type="invalid", target_action="a")


# ============================================================
# CounterfactualFamily
# ============================================================


class TestCounterfactualFamily:
    def test_roundtrip_json(self, sample_family: CounterfactualFamily) -> None:
        json_str = sample_family.model_dump_json()
        restored = CounterfactualFamily.model_validate_json(json_str)
        assert restored.family_id == sample_family.family_id
        assert len(restored.members) == 2

    def test_min_two_members(self) -> None:
        with pytest.raises(ValidationError):
            CounterfactualFamily(
                family_id="bad",
                source_atoms=["a"],
                shared_trace_template=[TraceStep(time_minutes=0, action_id="x")],
                members=[FamilyMember(scenario_id="only_one", patient_state={}, expected_verdict="conformant")],
                pivot_variable="x",
            )

    def test_min_one_trace_step(self) -> None:
        with pytest.raises(ValidationError):
            CounterfactualFamily(
                family_id="bad",
                source_atoms=["a"],
                shared_trace_template=[],
                members=[
                    FamilyMember(scenario_id="m1", patient_state={}, expected_verdict="conformant"),
                    FamilyMember(scenario_id="m2", patient_state={}, expected_verdict="commission_violation"),
                ],
                pivot_variable="x",
            )

    def test_different_verdicts_in_members(self, sample_family: CounterfactualFamily) -> None:
        verdicts = {m.expected_verdict for m in sample_family.members}
        assert len(verdicts) >= 2, "Family members should have different expected verdicts"


# ============================================================
# Coverage
# ============================================================


class TestCoverageModels:
    def test_coverage_type_values(self) -> None:
        assert len(CoverageType) == 13

    def test_coverage_vector_frozenset(self) -> None:
        v = CoverageVector(scenario_id="s1", covered_items=frozenset({"a", "b"}))
        assert "a" in v.covered_items

    def test_coverage_report_fully_covered(self) -> None:
        r = CoverageReport(total_items=5, covered_count=5, coverage_ratio=1.0)
        assert r.is_fully_covered

    def test_coverage_report_not_covered(self) -> None:
        r = CoverageReport(
            total_items=5,
            covered_count=3,
            uncovered_item_ids=["x", "y"],
            coverage_ratio=0.6,
        )
        assert not r.is_fully_covered

    def test_coverage_report_empty(self) -> None:
        r = CoverageReport()
        assert not r.is_fully_covered


# ============================================================
# GuidelineQualityCard
# ============================================================


class TestGuidelineQualityCard:
    def test_roundtrip(self) -> None:
        card = GuidelineQualityCard(
            source_id="ssc_2021",
            agree_ii=AGREEScores(scope_purpose=6, rigor_development=7, applicability=5),
            right_items=RIGHTItems(recommendation_clarity=True, evidence_linkage=True),
            extraction_risk=ExtractionRisk(layout_complexity="high", recommendation_tables_present=True),
            scenario_policy=ScenarioPolicy(allow_hard_constraints=True),
        )
        d = card.model_dump()
        restored = GuidelineQualityCard.model_validate(d)
        assert restored.source_id == "ssc_2021"
        assert restored.agree_ii.rigor_development == 7

    def test_agree_score_bounds(self) -> None:
        with pytest.raises(ValidationError):
            AGREEScores(scope_purpose=0, rigor_development=7, applicability=5)
        with pytest.raises(ValidationError):
            AGREEScores(scope_purpose=8, rigor_development=7, applicability=5)

    def test_defaults(self) -> None:
        card = GuidelineQualityCard(
            source_id="test",
            agree_ii=AGREEScores(scope_purpose=4, rigor_development=4, applicability=4),
        )
        assert card.right_items.recommendation_clarity is False
        assert card.scenario_policy.allow_hard_constraints is True


# ============================================================
# Cross-schema integration
# ============================================================


class TestCrossSchemaIntegration:
    def test_atom_to_seed_atom_id_linkage(
        self,
        sample_atom: RecommendationAtom,
        sample_seed: ScenarioSeed,
    ) -> None:
        """Seed source_atoms should reference valid atom_ids."""
        assert sample_atom.atom_id in sample_seed.source_atoms

    def test_atom_to_family_atom_id_linkage(
        self,
        sample_atom_forbidden: RecommendationAtom,
        sample_family: CounterfactualFamily,
    ) -> None:
        assert sample_atom_forbidden.atom_id in sample_family.source_atoms

    def test_full_json_export(
        self,
        sample_atom: RecommendationAtom,
        sample_seed: ScenarioSeed,
        sample_family: CounterfactualFamily,
    ) -> None:
        """All schemas can be serialized into a single JSON document."""
        bundle = {
            "atoms": [sample_atom.model_dump()],
            "seeds": [sample_seed.model_dump()],
            "families": [sample_family.model_dump()],
        }
        json_str = json.dumps(bundle, default=str)
        restored = json.loads(json_str)
        assert len(restored["atoms"]) == 1
        assert len(restored["seeds"]) == 1
        assert len(restored["families"]) == 1
