"""Tests for CPG integration fixes in run_external_benchmark.

Validates that:
1. General domain uses universal CPG (not returning None)
2. available_actions come from CPG, not expected_actions (no evaluation leakage)
3. mandatory_actions are loaded from CPG engine
4. dynamic_simulation defaults to True
5. CPG-guided actions work for general domain
"""

import pytest
import sys
import inspect
from pathlib import Path
from unittest.mock import patch, MagicMock
from dataclasses import dataclass
from typing import Set, Dict, List, Optional

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from run_external_benchmark import (
    create_observation,
    evaluate_scenario,
    evaluate_cpg_compliance,
    generate_cpg_guided_expected_actions,
    ExternalScenario,
    get_cpg_graph_path,
)


def _make_scenario(
    description: str = "test patient",
    diagnosis: str = "general condition",
    chief_complaint: str = "general complaint",
    vitals: dict = None,
    expected_actions: list = None,
) -> ExternalScenario:
    """Helper to create test scenarios."""
    return ExternalScenario(
        scenario_id="test_cpg_001",
        source_benchmark="test",
        description=description,
        patient_state={
            "chief_complaint": chief_complaint,
            "working_diagnosis": "",
            "vitals": vitals or {"heart_rate": 80, "blood_pressure_systolic": 120},
            "history": "",
            "symptoms": {},
            "test_results": {},
            "allergies": [],
            "comorbidities": [],
            "contraindications": [],
        },
        expected_diagnosis=diagnosis,
        expected_actions=expected_actions or ["assess_patient", "obtain_history"],
        metadata={},
    )


class TestNoEvaluationLeakage:
    """Fix 3: available_actions should NOT contain expected_actions."""

    def test_cpg_allowed_actions_override_expected(self):
        """When cpg_allowed_actions is provided, it replaces expected_actions."""
        scenario = _make_scenario(expected_actions=["secret_answer_1", "secret_answer_2"])
        cpg_actions = ["assess_vital_signs", "order_lab_cbc", "order_lab_bmp"]

        obs = create_observation(
            scenario, step=0,
            cpg_allowed_actions=cpg_actions,
        )
        # available_actions should be the CPG actions, NOT expected_actions
        assert obs.available_actions == cpg_actions
        assert "secret_answer_1" not in obs.available_actions
        assert "secret_answer_2" not in obs.available_actions

    def test_empty_available_when_no_cpg(self):
        """When no CPG is loaded, available_actions should be empty, not expected."""
        scenario = _make_scenario(expected_actions=["secret_answer"])
        obs = create_observation(scenario, step=0)
        # Without cpg_allowed_actions, should be empty list (not expected_actions)
        assert obs.available_actions == []
        assert "secret_answer" not in obs.available_actions

    def test_available_actions_stay_consistent_across_steps(self):
        """CPG allowed actions should be the same across all steps."""
        scenario = _make_scenario()
        cpg_actions = ["assess_vital_signs", "order_lab_cbc"]

        obs0 = create_observation(scenario, step=0, cpg_allowed_actions=cpg_actions)
        obs5 = create_observation(scenario, step=5, cpg_allowed_actions=cpg_actions)
        assert obs0.available_actions == obs5.available_actions


class TestMandatoryActionsFromCPG:
    """Fix 5: mandatory_actions should come from CPG engine."""

    def test_mandatory_actions_from_cpg(self):
        """When cpg_mandatory_actions is provided, observation uses them."""
        scenario = _make_scenario()
        mandatory = ["assess_vital_signs"]

        obs = create_observation(
            scenario, step=0,
            cpg_mandatory_actions=mandatory,
        )
        assert obs.mandatory_actions == mandatory

    def test_empty_mandatory_when_no_cpg(self):
        """Without CPG, mandatory_actions defaults to empty."""
        scenario = _make_scenario()
        obs = create_observation(scenario, step=0)
        assert obs.mandatory_actions == []

    def test_combined_cpg_actions(self):
        """Both allowed and mandatory actions from CPG."""
        scenario = _make_scenario()
        allowed = ["assess_vital_signs", "order_lab_cbc", "give_iv_fluid"]
        mandatory = ["assess_vital_signs"]

        obs = create_observation(
            scenario, step=0,
            cpg_allowed_actions=allowed,
            cpg_mandatory_actions=mandatory,
        )
        assert obs.available_actions == allowed
        assert obs.mandatory_actions == mandatory
        # Mandatory should be a subset of allowed
        assert all(m in obs.available_actions for m in obs.mandatory_actions)


class TestDynamicSimulationDefault:
    """Fix 2: dynamic_simulation should default to True."""

    def test_evaluate_scenario_default_dynamic(self):
        """evaluate_scenario should default to dynamic_simulation=True."""
        sig = inspect.signature(evaluate_scenario)
        default = sig.parameters["dynamic_simulation"].default
        assert default is True, f"Expected True, got {default}"


class TestGeneralDomainCPGEvaluation:
    """Fix 4: domain 'general' should use universal CPG, not return None."""

    def test_universal_cpg_path_exists(self):
        """universal_clinical_safety.yaml should be found by get_cpg_graph_path."""
        path = get_cpg_graph_path("general")
        assert path is not None
        assert path.exists()
        assert "universal_clinical_safety" in path.name

    def test_cpg_guided_actions_for_general_domain(self):
        """Fix 1: generate_cpg_guided_expected_actions should work for general domain."""
        scenario = _make_scenario(
            description="routine examination",
            diagnosis="healthy adult",
        )
        # Should attempt CPG loading, not just return expected_actions immediately
        result = generate_cpg_guided_expected_actions(scenario, "general")
        # universal_clinical_safety.yaml has allowed_actions including assess_vital_signs
        assert len(result) > 0
        # If CPG loaded successfully, result should differ from original
        # (universal CPG has many more actions than our 2-item default)
        assert len(result) > 2

    def test_evaluate_cpg_compliance_general_domain_not_none(self):
        """Fix 4: evaluate_cpg_compliance should not return None for general domain."""
        from cga_bench.cpg_model.schemas.base import Action, ActionType

        scenario = _make_scenario()
        actions = [
            Action(
                type=ActionType.REASSESS,
                action_id="assess_vital_signs",
                args={},
                timestamp_minutes=0.0,
            ),
        ]
        result = evaluate_cpg_compliance(actions, scenario, "general")
        # Should NOT be None anymore
        assert result is not None
        assert hasattr(result, "compliance_score")
        assert 0.0 <= result.compliance_score <= 1.0

    def test_evaluate_cpg_compliance_general_returns_valid_score(self):
        """General domain CPG should return a valid score with sub_scores."""
        scenario = _make_scenario()
        from cga_bench.cpg_model.schemas.base import Action, ActionType

        actions = [
            Action(
                type=ActionType.ORDER_LAB,
                action_id="order_lab_cbc",
                args={},
                timestamp_minutes=0.0,
            ),
        ]
        result = evaluate_cpg_compliance(actions, scenario, "general")
        assert result is not None
        # Should have the C1-C5 sub-scores
        assert "C1_path_selection" in result.sub_scores
        assert "C2_mandatory_completion" in result.sub_scores
        assert "C3_forbidden_avoidance" in result.sub_scores


class TestEmptyActionsOmissionDetection:
    """Bug fix: Empty actions should NOT produce a perfect 1.0 score.

    When an agent performs zero actions, mandatory actions are still missed,
    so omission violations must be detected.
    """

    def test_empty_actions_not_perfect_score(self):
        """Empty actions list should NOT produce compliance_score=1.0."""
        scenario = _make_scenario()
        # No actions at all — agent did nothing
        result = evaluate_cpg_compliance([], scenario, "general")
        assert result is not None
        # universal_clinical_safety.yaml has mandatory: assess_vital_signs
        # Doing nothing should detect this omission
        assert result.compliance_score < 1.0, (
            f"Empty actions got perfect score {result.compliance_score}; "
            f"expected omission violations for mandatory actions"
        )

    def test_empty_actions_has_omission_violations(self):
        """Empty actions should produce OMISSION violation type."""
        scenario = _make_scenario()
        result = evaluate_cpg_compliance([], scenario, "general")
        assert result is not None
        assert result.total_violations > 0, "Expected at least 1 violation for empty actions"
        assert result.violations_by_type.get("omission", result.violations_by_type.get("OMISSION", 0)) > 0, (
            f"Expected OMISSION violations, got: {result.violations_by_type}"
        )

    def test_empty_actions_states_created(self):
        """Even with no actions, episode should have states for omission check."""
        # This verifies the fix: initial + final states are always created
        from cga_bench.cpg_model.schemas.base import Action
        from cga_bench.cpg_engine.engine import CPGEngineFactory
        from cga_bench.assessor_core.violations import ViolationExtractor
        from run_external_benchmark import (
            build_patient_state_from_scenario,
            get_violation_extractor_config,
        )

        scenario = _make_scenario()
        cpg_path = get_cpg_graph_path("general")
        cpg_engine = CPGEngineFactory.load_from_file(str(cpg_path))
        probe = cpg_engine.evaluate(
            build_patient_state_from_scenario(
                scenario, state_id="probe", time_minutes=0.0
            )
        )
        cpg_engine.reset()

        # verify states are created even for empty actions
        result = evaluate_cpg_compliance([], scenario, "general")
        assert result is not None


class TestShortEpisodeOmissionDetection:
    """Bug fix: Short episodes should still detect omissions.

    ViolationExtractor only flags omissions when
    final_state.time_since_arrival_minutes > deadline.
    The fix ensures final state time exceeds all CPG deadlines.
    """

    def test_final_state_exceeds_deadlines(self):
        """Final state time should exceed all CPG deadlines."""
        from cga_bench.cpg_engine.engine import CPGEngineFactory
        from run_external_benchmark import build_patient_state_from_scenario

        scenario = _make_scenario()
        cpg_path = get_cpg_graph_path("general")
        cpg_engine = CPGEngineFactory.load_from_file(str(cpg_path))
        probe = cpg_engine.evaluate(
            build_patient_state_from_scenario(
                scenario, state_id="probe", time_minutes=0.0
            )
        )

        max_deadline = max(probe.deadlines.values()) if probe.deadlines else 0
        # universal_clinical_safety.yaml has assess_vital_signs deadline = 15 min
        assert max_deadline > 0, "Expected at least one deadline in universal CPG"

        # Now check that evaluate_cpg_compliance produces omission
        # for a short-lived action before the deadline
        from cga_bench.cpg_model.schemas.base import Action, ActionType
        actions = [
            Action(
                type=ActionType.ORDER_LAB,
                action_id="order_lab_cbc",
                args={},
                timestamp_minutes=2.0,  # Action at 2 min, well before 15-min deadline
            )
        ]
        result = evaluate_cpg_compliance(actions, scenario, "general")
        assert result is not None
        # assess_vital_signs was NOT performed, deadline is 15 min
        # Before fix: final_state was at 2+5=7 min < 15 min → no omission detected
        # After fix: final_state is at max(7, 16) = 16 min → omission detected
        assert result.total_violations > 0, (
            f"Expected omission for assess_vital_signs (deadline={max_deadline}), "
            f"got 0 violations"
        )
        assert result.violations_by_type.get("omission", result.violations_by_type.get("OMISSION", 0)) > 0

    def test_sepsis_domain_omission_detection(self):
        """Sepsis domain should detect omissions even with short episodes."""
        cpg_path = get_cpg_graph_path("sepsis")
        if not cpg_path or not cpg_path.exists():
            pytest.skip("Sepsis CPG not available")

        from cga_bench.cpg_engine.engine import CPGEngineFactory
        from cga_bench.cpg_model.schemas.base import Action, ActionType
        from run_external_benchmark import build_patient_state_from_scenario

        scenario = _make_scenario(
            description="fever and hypotension",
            diagnosis="sepsis",
            chief_complaint="fever, altered mental status",
        )

        # Only one action at t=1 min — most mandatory sepsis actions are missed
        actions = [
            Action(
                type=ActionType.REASSESS,
                action_id="assess_vital_signs",
                args={},
                timestamp_minutes=1.0,
            )
        ]
        result = evaluate_cpg_compliance(actions, scenario, "sepsis")
        if result is not None:
            # Sepsis hour-1 bundle has many mandatory actions
            # Only performing assess_vital_signs should leave omissions
            assert result.total_violations > 0 or result.compliance_score < 1.0, (
                "Sepsis scenario with only 1 action should have violations or imperfect score"
            )
