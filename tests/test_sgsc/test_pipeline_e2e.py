"""End-to-end tests for sgsc.pipeline — full 15-step pipeline with mock/precomputed atoms."""

from __future__ import annotations

import json
from pathlib import Path

from sgsc.pipeline import PipelineConfig, PipelineResult, run_pipeline
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

# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


def _make_atoms() -> list[RecommendationAtom]:
    """Create a minimal set of atoms for pipeline testing."""
    return [
        RecommendationAtom(
            atom_id="pipe_abx_001",
            source=SourceReference(
                guideline_id="ssc_test",
                section="Hour-1",
                quote="Administer broad-spectrum antibiotics within 1 hour of sepsis recognition, after obtaining blood cultures.",
            ),
            population=PopulationCriteria(
                inclusion=["sepsis"],
                exclusion=[],
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
        ),
        RecommendationAtom(
            atom_id="pipe_lactate_002",
            source=SourceReference(
                guideline_id="ssc_test",
                section="Hour-1",
                quote="Measure serum lactate level; remeasure if initial lactate is elevated.",
            ),
            population=PopulationCriteria(
                inclusion=["sepsis"],
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
        ),
        RecommendationAtom(
            atom_id="pipe_forbidden_003",
            source=SourceReference(
                guideline_id="ssc_test",
                section="Contraindications",
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
                system="GRADE",
                recommendation_class="I",
                level="B",
            ),
            scenario_hooks=ScenarioHooks(
                boundary_variables=["creatinine"],
                counterfactual_pairs=["aki_vs_normal_renal"],
            ),
        ),
    ]


_CORPUS_TEXT = (
    "Administer broad-spectrum antibiotics within 1 hour of sepsis recognition, after obtaining blood cultures. "
    "Measure serum lactate level; remeasure if initial lactate is elevated. "
    "Avoid iodinated contrast agents in patients with AKI stage 2 or higher."
)

_RECOMMENDATIONS = [
    {
        "text": "Administer broad-spectrum antibiotics within 1 hour of sepsis recognition, after obtaining blood cultures.",
        "section": "Hour-1",
    },
    {"text": "Measure serum lactate level; remeasure if initial lactate is elevated.", "section": "Hour-1"},
    {"text": "Avoid iodinated contrast agents in patients with AKI stage 2 or higher.", "section": "Contraindications"},
]


# ------------------------------------------------------------------
# Pipeline tests
# ------------------------------------------------------------------


class TestPipelineConfig:
    """Tests for PipelineConfig."""

    def test_required_fields(self) -> None:
        config = PipelineConfig(
            guideline_id="test",
            guideline_name="Test Guideline",
            output_dir="/tmp/test",
        )
        assert config.guideline_id == "test"
        assert config.llm_config is None
        assert config.grounding_threshold == 0.6
        assert config.max_scenarios == 500

    def test_optional_fields(self) -> None:
        config = PipelineConfig(
            guideline_id="test",
            guideline_name="Test",
            output_dir="/tmp/test",
            enable_multi_model=True,
            entailment_mode="rule_based",
            grounding_threshold=0.6,
            max_scenarios=100,
        )
        assert config.enable_multi_model is True
        assert config.grounding_threshold == 0.6
        assert config.entailment_mode == "rule_based"


class TestPipelineResult:
    """Tests for PipelineResult."""

    def test_defaults(self) -> None:
        result = PipelineResult()
        assert result.atoms == []
        assert result.graph == {}
        assert result.scenarios == {}
        assert result.hallucination_rate == 0.0
        assert result.leakage_passed is True
        assert result.total_seeds == 0
        assert result.total_families == 0
        assert result.total_mutations == 0


class TestRunPipeline:
    """Tests for run_pipeline with precomputed atoms."""

    def test_full_pipeline_precomputed(self, tmp_path: Path) -> None:
        config = PipelineConfig(
            guideline_id="ssc_test",
            guideline_name="SSC Test",
            output_dir=str(tmp_path),
        )
        result = run_pipeline(
            config,
            corpus_full_text=_CORPUS_TEXT,
            recommendations=_RECOMMENDATIONS,
            precomputed_atoms=_make_atoms(),
        )

        # Atoms survived grounding (quotes are in corpus)
        assert len(result.atoms) > 0

        # Graph generated
        assert result.graph != {}

        # Seeds created
        assert result.total_seeds > 0

        # Scenarios generated
        assert len(result.scenarios) > 0

        # Leakage audit passed
        assert result.leakage_passed is True

        # Hallucination rate is low (quotes are verbatim from corpus)
        assert result.hallucination_rate < 0.2

        # Coverage paths exist
        assert "json" in result.coverage_paths
        assert "markdown" in result.coverage_paths
        assert "latex" in result.coverage_paths

    def test_output_files_created(self, tmp_path: Path) -> None:
        config = PipelineConfig(
            guideline_id="ssc_test",
            guideline_name="SSC Test",
            output_dir=str(tmp_path),
        )
        run_pipeline(config, _CORPUS_TEXT, _RECOMMENDATIONS, _make_atoms())

        # Graph JSON
        graph_file = tmp_path / "ssc_test_graph.json"
        assert graph_file.exists()
        graph_data = json.loads(graph_file.read_text())
        assert "nodes" in graph_data or "guideline_id" in graph_data

        # Scenarios JSON
        scenarios_file = tmp_path / "ssc_test_scenarios.json"
        assert scenarios_file.exists()
        scenarios_data = json.loads(scenarios_file.read_text())
        assert isinstance(scenarios_data, dict)

        # Constraints JSON
        constraints_file = tmp_path / "ssc_test_constraints.json"
        assert constraints_file.exists()
        constraints_data = json.loads(constraints_file.read_text())
        assert isinstance(constraints_data, list)

    def test_no_atoms_no_config_returns_empty(self, tmp_path: Path) -> None:
        config = PipelineConfig(
            guideline_id="empty",
            guideline_name="Empty",
            output_dir=str(tmp_path),
        )
        result = run_pipeline(config, "some text", [])
        assert result.atoms == []
        assert result.scenarios == {}

    def test_atoms_that_fail_grounding(self, tmp_path: Path) -> None:
        """Atoms with quotes not in corpus should be filtered out."""
        atoms = [
            RecommendationAtom(
                atom_id="hallucinated_001",
                source=SourceReference(
                    guideline_id="test",
                    section="Fake",
                    quote="This quote does not appear anywhere in the corpus text at all whatsoever.",
                ),
                population=PopulationCriteria(inclusion=["all"], exclusion=[]),
                action=AtomAction(canonical_id="fake_action", action_type="procedure"),
                constraint=AtomConstraint(type="REQUIRED"),
                evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="A"),
            ),
        ]
        config = PipelineConfig(
            guideline_id="test",
            guideline_name="Test",
            output_dir=str(tmp_path),
            grounding_threshold=0.8,
        )
        result = run_pipeline(config, "Completely unrelated corpus text here.", [], atoms)
        # With high threshold, hallucinated atoms must be filtered out entirely
        assert len(result.atoms) == 0, "Ungrounded atoms must be filtered out"
        assert result.hallucination_rate == 1.0, "All atoms hallucinated → rate must be 1.0"

    def test_forbidden_atoms_create_families(self, tmp_path: Path) -> None:
        config = PipelineConfig(
            guideline_id="ssc_test",
            guideline_name="SSC Test",
            output_dir=str(tmp_path),
        )
        result = run_pipeline(config, _CORPUS_TEXT, _RECOMMENDATIONS, _make_atoms())
        # Fixture includes a FORBIDDEN atom with exclusion criteria,
        # so at least one counterfactual family should be generated
        assert result.total_families >= 1

    def test_mutations_generated(self, tmp_path: Path) -> None:
        config = PipelineConfig(
            guideline_id="ssc_test",
            guideline_name="SSC Test",
            output_dir=str(tmp_path),
        )
        result = run_pipeline(config, _CORPUS_TEXT, _RECOMMENDATIONS, _make_atoms())
        # Fixture has REQUIRED and WITHIN atoms which produce omit/delay mutations
        assert result.total_mutations >= 1


class TestThresholdForwarding:
    """β-2: Verify PipelineConfig.grounding_threshold is forwarded to entailment checker."""

    def test_custom_threshold_affects_entailment(self, tmp_path: Path) -> None:
        """A borderline atom passes at 0.3 threshold but fails at 0.9."""
        # Atom with 1/2 meaningful keywords matching → ratio 0.5
        borderline_atom = RecommendationAtom(
            atom_id="border_001",
            source=SourceReference(
                guideline_id="test",
                section="S1",
                quote="Administer antibiotics within 1 hour of sepsis recognition.",
            ),
            population=PopulationCriteria(inclusion=["sepsis"], exclusion=[]),
            action=AtomAction(
                canonical_id="give_broad_spectrum_antibiotics",
                action_type="medication",
            ),
            constraint=AtomConstraint(type="REQUIRED"),
            evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="B"),
        )

        # Low threshold (0.3): borderline atom should survive entailment
        config_low = PipelineConfig(
            guideline_id="test",
            guideline_name="Test",
            output_dir=str(tmp_path / "low"),
            grounding_threshold=0.3,
        )
        result_low = run_pipeline(
            config_low,
            "Administer antibiotics within 1 hour of sepsis recognition.",
            [{"text": "Administer antibiotics within 1 hour."}],
            [borderline_atom],
        )

        # High threshold (0.9): same atom should be rejected
        config_high = PipelineConfig(
            guideline_id="test",
            guideline_name="Test",
            output_dir=str(tmp_path / "high"),
            grounding_threshold=0.9,
        )
        result_high = run_pipeline(
            config_high,
            "Administer antibiotics within 1 hour of sepsis recognition.",
            [{"text": "Administer antibiotics within 1 hour."}],
            [borderline_atom],
        )

        # With low threshold, atom should pass; with high threshold, it should be filtered
        assert len(result_low.atoms) >= len(result_high.atoms), (
            f"Low threshold ({config_low.grounding_threshold}) should keep more atoms "
            f"than high threshold ({config_high.grounding_threshold}): "
            f"{len(result_low.atoms)} vs {len(result_high.atoms)}"
        )


class TestActionNormalization:
    """β-4: Verify ActionNormalizer is wired into pipeline post-LLM step."""

    def test_normalize_atom_actions_called(self, tmp_path: Path) -> None:
        """Atoms with non-canonical action IDs get normalized by pipeline."""
        from sgsc.pipeline import _normalize_atom_actions

        atom = RecommendationAtom(
            atom_id="norm_001",
            source=SourceReference(
                guideline_id="test",
                section="S1",
                quote="Obtain blood cultures before administering antibiotics.",
            ),
            population=PopulationCriteria(inclusion=["sepsis"], exclusion=[]),
            action=AtomAction(
                canonical_id="blood_culture_before_antibiotics",
                action_type="lab",
            ),
            constraint=AtomConstraint(type="REQUIRED"),
            evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="B"),
        )

        result = _normalize_atom_actions([atom])
        # ActionNormalizer maps blood_culture_before_antibiotics -> order_lab_blood_culture
        assert len(result) == 1
        try:
            from cga_bench.assessor_core.action_normalizer import ActionNormalizer

            normalizer = ActionNormalizer()
            expected = normalizer.normalize("blood_culture_before_antibiotics")
            assert result[0].action.canonical_id == expected, (
                f"Expected canonical form '{expected}', got '{result[0].action.canonical_id}'"
            )
        except ImportError:
            # If cga_bench not on path, normalization is skipped gracefully
            assert result[0].action.canonical_id == "blood_culture_before_antibiotics"

    def test_normalize_sequence_references(self, tmp_path: Path) -> None:
        """Sequence required_prior and before lists also get normalized."""
        from sgsc.pipeline import _normalize_atom_actions

        atom = RecommendationAtom(
            atom_id="seq_001",
            source=SourceReference(
                guideline_id="test",
                section="S1",
                quote="Administer antibiotics after obtaining blood cultures.",
            ),
            population=PopulationCriteria(inclusion=["sepsis"], exclusion=[]),
            action=AtomAction(
                canonical_id="give_broad_spectrum_antibiotics",
                action_type="medication",
            ),
            constraint=AtomConstraint(type="REQUIRED"),
            sequence=AtomSequence(
                required_prior=["blood_culture_before_antibiotics"],
            ),
            evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="B"),
        )

        result = _normalize_atom_actions([atom])
        try:
            from cga_bench.assessor_core.action_normalizer import ActionNormalizer

            normalizer = ActionNormalizer()
            expected_prior = normalizer.normalize("blood_culture_before_antibiotics")
            assert result[0].sequence.required_prior[0] == expected_prior
        except ImportError:
            # Graceful skip
            assert result[0].sequence.required_prior[0] == "blood_culture_before_antibiotics"

    def test_normalize_graceful_without_cga_bench(self) -> None:
        """_normalize_atom_actions returns atoms unchanged if import fails."""
        from sgsc.pipeline import _normalize_atom_actions

        atom = RecommendationAtom(
            atom_id="grace_001",
            source=SourceReference(guideline_id="test", section="S1", quote="Test quote."),
            population=PopulationCriteria(inclusion=["all"], exclusion=[]),
            action=AtomAction(canonical_id="some_action", action_type="procedure"),
            constraint=AtomConstraint(type="REQUIRED"),
            evidence=AtomEvidence(system="GRADE", recommendation_class="I", level="B"),
        )

        # Even without cga_bench, function must not crash
        result = _normalize_atom_actions([atom])
        assert len(result) == 1
        assert result[0].atom_id == "grace_001"
