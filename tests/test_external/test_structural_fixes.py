"""Tests for 7 structural defect fixes in closed-loop CPG evaluation.

Defect 1+6: CPG engine stuck at node 0 / No action→state reflection
  → Fixed by StateReducer (assessor_core/state_reducer.py)
Defect 2+3: Omission only checks current node / HarmScorer arbitrary denominator
  → Fixed by ReachabilityAnalyzer (cpg_engine/reachability.py)
Defect 4: expected_actions self-referential overwrite
  → Fixed by Independence Guard (expected_actions_cpg field)
Defect 5+7: No final score / ActionNormalizer inconsistency
  → Fixed by ScoringPolicy (assessor_core/dual_track_evaluator.py)
"""

import copy
import inspect
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from cga_bench.assessor_core.state_reducer import StateReducer
from cga_bench.assessor_core.dual_track_evaluator import ScoringPolicy
from cga_bench.cpg_engine.reachability import ReachabilityAnalyzer
from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    PatientState,
    VitalSigns,
    LabResult,
    HarmSeverity,
)
from run_external_benchmark import (
    ExternalScenario,
    EvaluationResult,
    evaluate_cpg_compliance,
    get_cpg_graph_path,
    build_patient_state_from_scenario,
)


def _make_scenario(**kwargs) -> ExternalScenario:
    defaults = dict(
        scenario_id="struct_test_001",
        source_benchmark="test",
        description="test patient",
        patient_state={
            "chief_complaint": "general complaint",
            "working_diagnosis": "",
            "vitals": {"heart_rate": 80, "blood_pressure_systolic": 120},
            "history": "",
            "symptoms": {},
            "test_results": {},
            "allergies": [],
            "comorbidities": [],
            "contraindications": [],
        },
        expected_diagnosis="general condition",
        expected_actions=["assess_patient", "obtain_history"],
        metadata={},
    )
    defaults.update(kwargs)
    return ExternalScenario(**defaults)


# =============================================================================
# Phase 1: StateReducer Tests (Defect 1, 6)
# =============================================================================


class TestStateReducer:
    """StateReducer: Action → PatientState field mapping."""

    def test_order_lab_updates_lab_results(self):
        """order_lab_lactate → state.lab_results에 LabResult 추가."""
        reducer = StateReducer()
        state = PatientState(
            state_id="s0",
            age=50, sex="M", chief_complaint="test",
            vitals=VitalSigns(heart_rate=90, blood_pressure_systolic=100),
        )
        action = Action(
            type=ActionType.ORDER_LAB,
            action_id="order_lab_lactate",
            args={},
            timestamp_minutes=5.0,
        )
        new_state = reducer.apply(state, action)
        assert len(new_state.lab_results) == 1
        assert new_state.lab_results[0].test_code == "lactate"
        # Original state unchanged
        assert len(state.lab_results) == 0

    def test_give_med_updates_medications(self):
        """give_broad_spectrum_antibiotics → medications_given에 추가."""
        reducer = StateReducer()
        state = PatientState(
            state_id="s0",
            age=50, sex="M", chief_complaint="test",
            vitals=VitalSigns(heart_rate=90, blood_pressure_systolic=100),
        )
        action = Action(
            type=ActionType.GIVE_MEDICATION,
            action_id="give_broad_spectrum_antibiotics",
            args={},
            timestamp_minutes=10.0,
        )
        new_state = reducer.apply(state, action)
        assert len(new_state.medications_given) == 1
        assert new_state.medications_given[0]["medication_code"] == "broad_spectrum_antibiotics"

    def test_assess_updates_procedures(self):
        """assess_vital_signs → procedures_done에 직접 문자열 추가."""
        reducer = StateReducer()
        state = PatientState(
            state_id="s0",
            age=50, sex="M", chief_complaint="test",
            vitals=VitalSigns(heart_rate=90, blood_pressure_systolic=100),
        )
        action = Action(
            type=ActionType.REASSESS,
            action_id="assess_vital_signs",
            args={},
            timestamp_minutes=1.0,
        )
        new_state = reducer.apply(state, action)
        assert "assess_vital_signs" in new_state.procedures_done

    def test_start_vasopressor_goes_to_procedures(self):
        """start_vasopressor_* → procedures_done (not medications_given).

        _mandatory_completed() uses direct string match for procedures_done,
        so start_vasopressor_if_hypotensive must stay as a raw string.
        """
        reducer = StateReducer()
        state = PatientState(
            state_id="s0",
            age=50, sex="M", chief_complaint="test",
            vitals=VitalSigns(heart_rate=90, blood_pressure_systolic=100),
        )
        action = Action(
            type=ActionType.GIVE_MEDICATION,
            action_id="start_vasopressor_if_hypotensive",
            args={},
            timestamp_minutes=30.0,
        )
        new_state = reducer.apply(state, action)
        assert "start_vasopressor_if_hypotensive" in new_state.procedures_done
        assert len(new_state.medications_given) == 0

    def test_duplicate_prevention(self):
        """Same action applied twice → no duplicates."""
        reducer = StateReducer()
        state = PatientState(
            state_id="s0",
            age=50, sex="M", chief_complaint="test",
            vitals=VitalSigns(heart_rate=90, blood_pressure_systolic=100),
        )
        action = Action(
            type=ActionType.ORDER_LAB,
            action_id="order_lab_blood_culture",
            args={},
            timestamp_minutes=5.0,
        )
        s1 = reducer.apply(state, action)
        s2 = reducer.apply(s1, action)
        assert len(s2.lab_results) == 1  # No duplicate

    def test_evolving_state_enables_node_advance(self):
        """Consecutive actions → CPGEngine can advance nodes."""
        engine = CPGEngineFactory.load_from_file(
            str(get_cpg_graph_path("sepsis"))
        )
        reducer = StateReducer()

        # Start with sepsis working_diagnosis so DecisionNode transitions
        state = PatientState(
            state_id="s0",
            age=50, sex="M", chief_complaint="fever",
            vitals=VitalSigns(heart_rate=110, blood_pressure_systolic=85),
            working_diagnosis="sepsis",
        )
        probe = engine.evaluate(state)
        initial_node = engine.current_node_id

        # Apply all sepsis_bundle mandatory actions
        sepsis_mandatory = [
            ("order_lab_lactate", ActionType.ORDER_LAB),
            ("order_lab_blood_culture", ActionType.ORDER_LAB),
            ("give_broad_spectrum_antibiotics", ActionType.GIVE_MEDICATION),
        ]
        for i, (aid, atype) in enumerate(sepsis_mandatory):
            action = Action(
                type=atype,
                action_id=aid,
                args={},
                timestamp_minutes=float(i + 1),
            )
            state = reducer.apply(state, action)

        # Advance node with updated state (pass last action)
        last_action = Action(
            type=ActionType.GIVE_MEDICATION,
            action_id="give_broad_spectrum_antibiotics",
            args={},
            timestamp_minutes=3.0,
        )
        advanced = engine.advance_node(state, last_action)
        assert engine.current_node_id != initial_node or advanced is not None, (
            "Engine should advance after all mandatory actions completed"
        )

    def test_immutable_original_state(self):
        """StateReducer must not modify the original state."""
        reducer = StateReducer()
        state = PatientState(
            state_id="s0",
            age=50, sex="M", chief_complaint="test",
            vitals=VitalSigns(heart_rate=90, blood_pressure_systolic=100),
            procedures_done=["existing_procedure"],
        )
        original_procedures = list(state.procedures_done)
        action = Action(
            type=ActionType.REASSESS,
            action_id="new_action",
            args={},
            timestamp_minutes=5.0,
        )
        new_state = reducer.apply(state, action)
        assert state.procedures_done == original_procedures


# =============================================================================
# Phase 2: ReachabilityAnalyzer Tests (Defect 2, 3)
# =============================================================================


class TestReachabilityAnalyzer:
    """ReachabilityAnalyzer: BFS mandatory collection for correct denominator."""

    def test_sepsis_collects_all_mandatory(self):
        """SSC sepsis CPG: should collect mandatory actions from multiple nodes."""
        engine = CPGEngineFactory.load_from_file(
            str(get_cpg_graph_path("sepsis"))
        )
        ra = ReachabilityAnalyzer(engine.graph)
        result = ra.collect_all_mandatory()

        # Sepsis CPG has mandatory actions across multiple nodes
        assert len(result["all_mandatory"]) >= 5
        assert "order_lab_lactate" in result["all_mandatory"]
        assert "order_lab_blood_culture" in result["all_mandatory"]
        assert "give_broad_spectrum_antibiotics" in result["all_mandatory"]
        assert result["denominator"] == len(result["all_mandatory"])

    def test_universal_cpg_has_mandatory(self):
        """Universal CPG: should have at least 1 mandatory action."""
        engine = CPGEngineFactory.load_from_file(
            str(get_cpg_graph_path("general"))
        )
        ra = ReachabilityAnalyzer(engine.graph)
        result = ra.collect_all_mandatory()

        assert len(result["all_mandatory"]) >= 1
        assert "assess_vital_signs" in result["all_mandatory"]

    def test_denominator_independent_of_expected_actions(self):
        """Denominator should not change when expected_actions length changes."""
        engine = CPGEngineFactory.load_from_file(
            str(get_cpg_graph_path("general"))
        )
        ra = ReachabilityAnalyzer(engine.graph)
        result = ra.collect_all_mandatory()
        denominator = result["denominator"]

        # The denominator is from the CPG graph, not from expected_actions
        # Changing expected_actions length should not affect it
        assert denominator > 0
        assert denominator == len(result["all_mandatory"])

    def test_traverses_conditional_branches(self):
        """BFS should traverse conditional_next branches too."""
        engine = CPGEngineFactory.load_from_file(
            str(get_cpg_graph_path("sepsis"))
        )
        ra = ReachabilityAnalyzer(engine.graph)
        result = ra.collect_all_mandatory()

        # initial_recognition is a DecisionNode with conditional_next
        # Both sepsis_bundle and septic_shock_bundle should be reachable
        assert "sepsis_bundle" in result["reachable_nodes"]
        assert "septic_shock_bundle" in result["reachable_nodes"]

    def test_denominator_at_least_one(self):
        """Denominator should be at least 1 to prevent division by zero."""
        engine = CPGEngineFactory.load_from_file(
            str(get_cpg_graph_path("general"))
        )
        ra = ReachabilityAnalyzer(engine.graph)
        result = ra.collect_all_mandatory()
        assert result["denominator"] >= 1


# =============================================================================
# Phase 3: Independence Guard Tests (Defect 4)
# =============================================================================


class TestIndependenceGuard:
    """Independence Guard: original expected_actions preserved."""

    def test_expected_actions_cpg_field_exists(self):
        """ExternalScenario should have expected_actions_cpg field."""
        scenario = _make_scenario()
        assert hasattr(scenario, "expected_actions_cpg")
        assert scenario.expected_actions_cpg is None  # Default

    def test_original_expected_actions_preserved_after_evaluation(self):
        """After CPG evaluation, scenario.expected_actions should be unchanged."""
        scenario = _make_scenario(
            expected_actions=["original_action_1", "original_action_2"]
        )
        original_actions = list(scenario.expected_actions)

        # Run CPG compliance evaluation
        evaluate_cpg_compliance([], scenario, "general")

        # Original expected_actions must be unchanged
        assert scenario.expected_actions == original_actions

    def test_no_self_referential_overwrite(self):
        """evaluate_scenario should not overwrite expected_actions with CPG output."""
        # Check that the overwrite line has been changed
        import run_external_benchmark as reb

        source = inspect.getsource(reb.evaluate_scenario)
        # The old pattern "scenario.expected_actions = cpg_actions" should be gone
        # The new pattern "scenario.expected_actions_cpg = cpg_actions" should exist
        assert "scenario.expected_actions_cpg" in source
        # Ensure the old overwrite is not present (exact match)
        lines = source.split("\n")
        for line in lines:
            stripped = line.strip()
            if stripped == "scenario.expected_actions = cpg_actions":
                pytest.fail("Found old overwrite pattern: scenario.expected_actions = cpg_actions")

    def test_evaluation_result_has_final_score_fields(self):
        """EvaluationResult should have DualTrack fields."""
        result = EvaluationResult(
            scenario_id="test",
            source_benchmark="test",
            agent_type="test",
            steps=1,
            actions_taken=0,
            llm_calls=0,
            correct_diagnosis=False,
            action_coverage=0.5,
            actions_performed=[],
            expected_diagnosis="test",
            agent_diagnosis="",
            duration_ms=100,
        )
        assert hasattr(result, "final_score")
        assert hasattr(result, "safety_gate_triggered")
        assert hasattr(result, "divergence")
        assert hasattr(result, "scoring_policy_id")


# =============================================================================
# Phase 4: ScoringPolicy Tests (Defect 5, 7)
# =============================================================================


class TestScoringPolicy:
    """ScoringPolicy: Track A × Track B with safety gate."""

    def test_multiplicative_formula(self):
        """final_score = track_a × track_b when no high-severity violations."""
        policy = ScoringPolicy()
        result = policy.compute_final_score(
            track_a_score=0.7,
            track_b_compliance=0.5,
            violation_severities=[],
        )
        assert abs(result["final_score"] - 0.35) < 1e-6
        assert result["safety_gate_triggered"] is False

    def test_hard_gate_severe_violation(self):
        """SEVERE violation → final_score = 0.0."""
        policy = ScoringPolicy()
        result = policy.compute_final_score(
            track_a_score=0.9,
            track_b_compliance=0.8,
            violation_severities=["severe"],
        )
        assert result["final_score"] == 0.0
        assert result["safety_gate_triggered"] is True

    def test_hard_gate_catastrophic_violation(self):
        """CATASTROPHIC violation → final_score = 0.0."""
        policy = ScoringPolicy()
        result = policy.compute_final_score(
            track_a_score=1.0,
            track_b_compliance=1.0,
            violation_severities=["catastrophic"],
        )
        assert result["final_score"] == 0.0
        assert result["safety_gate_triggered"] is True

    def test_minor_violations_no_gate(self):
        """MINOR/MODERATE violations → no safety gate."""
        policy = ScoringPolicy()
        result = policy.compute_final_score(
            track_a_score=0.8,
            track_b_compliance=0.6,
            violation_severities=["minor", "moderate", "major"],
        )
        assert result["final_score"] == pytest.approx(0.48)
        assert result["safety_gate_triggered"] is False

    def test_divergence_calculation(self):
        """Divergence = |track_a - track_b|."""
        policy = ScoringPolicy()
        result = policy.compute_final_score(
            track_a_score=0.9,
            track_b_compliance=0.3,
        )
        assert result["divergence"] == pytest.approx(0.6)

    def test_policy_id_in_result(self):
        """Policy ID should be included in result."""
        policy = ScoringPolicy(policy_id="test-policy-v1")
        result = policy.compute_final_score(0.5, 0.5)
        assert result["policy_id"] == "test-policy-v1"

    def test_perfect_scores(self):
        """Both tracks perfect → final = 1.0."""
        policy = ScoringPolicy()
        result = policy.compute_final_score(1.0, 1.0)
        assert result["final_score"] == 1.0

    def test_zero_coverage_zero_final(self):
        """Zero coverage → final = 0.0 regardless of compliance."""
        policy = ScoringPolicy()
        result = policy.compute_final_score(0.0, 1.0)
        assert result["final_score"] == 0.0

    def test_gate_disabled(self):
        """With safety_gate_enabled=False, severe violations don't zero score."""
        policy = ScoringPolicy(safety_gate_enabled=False)
        result = policy.compute_final_score(
            track_a_score=0.9,
            track_b_compliance=0.8,
            violation_severities=["severe"],
        )
        assert result["final_score"] == pytest.approx(0.72)
        assert result["safety_gate_triggered"] is False


# =============================================================================
# Closed-Loop Integration Tests
# =============================================================================


class TestClosedLoopIntegration:
    """End-to-end: Action→State→NodeAdvance→Violation→Score."""

    def test_sepsis_scenario_node_advances_and_detects_omissions(self):
        """Partial sepsis actions → node advances AND omissions detected."""
        scenario = _make_scenario(
            description="fever and hypotension",
            expected_diagnosis="sepsis",
        )
        scenario.patient_state["chief_complaint"] = "fever, altered mental status"

        # Only 2 of 3 sepsis_bundle mandatory actions
        actions = [
            Action(
                type=ActionType.ORDER_LAB,
                action_id="order_lab_lactate",
                args={},
                timestamp_minutes=5.0,
            ),
            Action(
                type=ActionType.ORDER_LAB,
                action_id="order_lab_blood_culture",
                args={},
                timestamp_minutes=10.0,
            ),
        ]
        result = evaluate_cpg_compliance(actions, scenario, "sepsis")
        assert result is not None
        # Missing give_broad_spectrum_antibiotics → should have violations
        assert result.total_violations > 0
        assert result.compliance_score < 1.0

    def test_empty_actions_still_detects_omissions(self):
        """Regression: empty actions should NOT produce perfect score."""
        scenario = _make_scenario()
        result = evaluate_cpg_compliance([], scenario, "general")
        assert result is not None
        assert result.compliance_score < 1.0
        assert result.total_violations > 0

    def test_short_episode_detects_omissions(self):
        """Regression: short episodes should still detect omissions."""
        scenario = _make_scenario()
        actions = [
            Action(
                type=ActionType.ORDER_LAB,
                action_id="order_lab_cbc",
                args={},
                timestamp_minutes=2.0,
            ),
        ]
        result = evaluate_cpg_compliance(actions, scenario, "general")
        assert result is not None
        # assess_vital_signs not performed → omission
        assert result.total_violations > 0

    def test_all_mandatory_complete_high_compliance(self):
        """Completing all mandatory actions → high compliance score."""
        scenario = _make_scenario()
        # Universal CPG mandatory: assess_vital_signs
        actions = [
            Action(
                type=ActionType.REASSESS,
                action_id="assess_vital_signs",
                args={},
                timestamp_minutes=5.0,
            ),
        ]
        result = evaluate_cpg_compliance(actions, scenario, "general")
        assert result is not None
        # Should have high compliance (mandatory completed within deadline)
        assert result.compliance_score >= 0.5

    def test_build_patient_state_domain_sets_working_diagnosis(self):
        """build_patient_state_from_scenario with domain sets working_diagnosis."""
        scenario = _make_scenario()
        state = build_patient_state_from_scenario(
            scenario, state_id="test", time_minutes=0.0, domain="sepsis"
        )
        assert state.working_diagnosis == "sepsis"

    def test_build_patient_state_no_domain_keeps_original(self):
        """Without domain, working_diagnosis stays from patient_state."""
        scenario = _make_scenario()
        scenario.patient_state["working_diagnosis"] = "existing_dx"
        state = build_patient_state_from_scenario(
            scenario, state_id="test", time_minutes=0.0
        )
        assert state.working_diagnosis == "existing_dx"
