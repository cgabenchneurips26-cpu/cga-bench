"""Tests for Experiment D: Evaluator Actionability."""
from __future__ import annotations

import pytest

from cga_bench.eval_harness.experiments.actionability import (
    ActionabilityExperiment,
    ActionabilityResult,
    PromptPatchType,
    PROMPT_PATCHES,
    EXPECTED_IMPACT,
)


@pytest.fixture()
def experiment() -> ActionabilityExperiment:
    return ActionabilityExperiment(output_dir="/tmp/test_actionability")


class TestPromptPatches:
    """Test prompt patch definitions."""

    def test_baseline_patch_is_empty(self) -> None:
        assert PROMPT_PATCHES[PromptPatchType.BASELINE] == ""

    def test_all_patches_defined(self) -> None:
        for pt in PromptPatchType:
            assert pt in PROMPT_PATCHES

    def test_timing_patch_mentions_deadline(self) -> None:
        patch = PROMPT_PATCHES[PromptPatchType.TIMING]
        assert "60 minutes" in patch or "time window" in patch

    def test_sequence_patch_mentions_order(self) -> None:
        patch = PROMPT_PATCHES[PromptPatchType.SEQUENCE]
        assert "blood cultures BEFORE" in patch

    def test_overaction_patch_mentions_scope(self) -> None:
        patch = PROMPT_PATCHES[PromptPatchType.OVERACTION]
        assert "explicitly recommended" in patch


class TestExpectedImpact:
    """Test expected dimension mapping."""

    def test_timing_targets_c4(self) -> None:
        assert EXPECTED_IMPACT[PromptPatchType.TIMING] == "C4_timing_compliance"

    def test_sequence_targets_c5(self) -> None:
        assert EXPECTED_IMPACT[PromptPatchType.SEQUENCE] == "C5_sequence_integrity"

    def test_overaction_targets_c1(self) -> None:
        assert EXPECTED_IMPACT[PromptPatchType.OVERACTION] == "C1_path_selection"


class TestActionabilityAnalysis:
    """Test actionability computation."""

    def test_targeted_improvement_detection(
        self, experiment: ActionabilityExperiment
    ) -> None:
        """Patch T should detect C4 improvement."""
        # Baseline: C4 = 0.6
        experiment.add_result(
            scenario_id="septic_shock_basic",
            patch_type=PromptPatchType.BASELINE,
            compliance_score=0.6,
            sub_scores={
                "C1_path_selection": 0.8,
                "C2_mandatory_completion": 1.0,
                "C3_forbidden_avoidance": 1.0,
                "C4_timing_compliance": 0.6,
                "C5_sequence_integrity": 1.0,
            },
        )
        # Patch T: C4 = 0.9 (improved), others same
        experiment.add_result(
            scenario_id="septic_shock_basic",
            patch_type=PromptPatchType.TIMING,
            compliance_score=0.8,
            sub_scores={
                "C1_path_selection": 0.8,
                "C2_mandatory_completion": 1.0,
                "C3_forbidden_avoidance": 1.0,
                "C4_timing_compliance": 0.9,
                "C5_sequence_integrity": 1.0,
            },
        )

        analyses = experiment.analyze()
        timing_analysis = next(
            a for a in analyses if a.patch_type == PromptPatchType.TIMING
        )
        assert timing_analysis.targeted_improvement_rate == 1.0
        assert timing_analysis.specificity == 1.0
        assert timing_analysis.mean_target_delta > 0

    def test_no_improvement_when_same(
        self, experiment: ActionabilityExperiment
    ) -> None:
        """No improvement when scores are identical."""
        scores = {
            "C1_path_selection": 0.8,
            "C2_mandatory_completion": 1.0,
            "C3_forbidden_avoidance": 1.0,
            "C4_timing_compliance": 1.0,
            "C5_sequence_integrity": 1.0,
        }
        experiment.add_result("test", PromptPatchType.BASELINE, 0.8, scores)
        experiment.add_result("test", PromptPatchType.TIMING, 0.8, scores)

        analyses = experiment.analyze()
        timing = next(a for a in analyses if a.patch_type == PromptPatchType.TIMING)
        assert timing.targeted_improvement_rate == 0.0

    def test_specificity_drops_with_coupling(
        self, experiment: ActionabilityExperiment
    ) -> None:
        """Specificity < 1.0 when non-target dimensions also change."""
        experiment.add_result(
            "test",
            PromptPatchType.BASELINE,
            0.5,
            {"C1_path_selection": 0.5, "C2_mandatory_completion": 0.5,
             "C3_forbidden_avoidance": 1.0, "C4_timing_compliance": 0.5,
             "C5_sequence_integrity": 1.0},
        )
        experiment.add_result(
            "test",
            PromptPatchType.TIMING,
            0.7,
            {"C1_path_selection": 0.7, "C2_mandatory_completion": 0.5,
             "C3_forbidden_avoidance": 1.0, "C4_timing_compliance": 0.8,
             "C5_sequence_integrity": 1.0},
        )

        analyses = experiment.analyze()
        timing = next(a for a in analyses if a.patch_type == PromptPatchType.TIMING)
        assert timing.targeted_improvement_rate == 1.0
        assert timing.specificity == 0.0  # C1 also changed
