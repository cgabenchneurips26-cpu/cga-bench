"""Regression tests for Issue #3: ScenarioLoader dynamic effects loading.

Verifies that medication_effects, deterioration_rules, termination_conditions,
and lab_thresholds are properly loaded from scenario YAML configs.
"""
from __future__ import annotations

from pathlib import Path
from typing import Dict, Any

import pytest

from cga_bench.eval_harness.scenario_loader import ScenarioLoader, ScenarioDefinition


# --- Fixtures ---

SCENARIOS_DIR = Path(__file__).parent.parent.parent / "configs" / "scenarios"
E2E_TEST_FILE = SCENARIOS_DIR / "septic_shock_e2e_test.yaml"


def _has_e2e_test_scenario() -> bool:
    """Check if the septic_shock_e2e_test.yaml exists."""
    return E2E_TEST_FILE.exists()


def _get_loader_with_e2e() -> ScenarioLoader:
    """Create a ScenarioLoader with e2e test file manually loaded."""
    loader = ScenarioLoader(str(SCENARIOS_DIR))
    # load_all_scenarios only loads *_scenarios.yaml files,
    # so we manually load the e2e test file
    loader._load_scenarios_from_file(E2E_TEST_FILE)
    return loader


# --- Tests ---

class TestEnvironmentConfigCaptured:
    """Tests that _parse_scenario captures environment_config from YAML."""

    @pytest.mark.skipif(
        not _has_e2e_test_scenario(),
        reason="septic_shock_e2e_test.yaml not found"
    )
    def test_medication_effects_in_scenario_definition(self):
        """P6 재현: ScenarioDefinition.environment_config에 medication_effects 포함.

        Before fix: environment_config 필드 없음 → create_environment에서 빈 리스트
        After fix: environment_config에 YAML의 medication_effects 리스트 포함
        """
        loader = _get_loader_with_e2e()
        scenario = loader.get_scenario("septic_shock_e2e_001")
        assert scenario is not None
        assert "medication_effects" in scenario.environment_config
        assert len(scenario.environment_config["medication_effects"]) > 0

    @pytest.mark.skipif(
        not _has_e2e_test_scenario(),
        reason="septic_shock_e2e_test.yaml not found"
    )
    def test_deterioration_rules_captured(self):
        """deterioration_rules from YAML captured in environment_config."""
        loader = _get_loader_with_e2e()
        scenario = loader.get_scenario("septic_shock_e2e_001")
        assert scenario is not None
        assert len(scenario.environment_config.get("deterioration_rules", [])) > 0

    @pytest.mark.skipif(
        not _has_e2e_test_scenario(),
        reason="septic_shock_e2e_test.yaml not found"
    )
    def test_termination_conditions_captured(self):
        """termination_conditions from YAML captured in environment_config."""
        loader = _get_loader_with_e2e()
        scenario = loader.get_scenario("septic_shock_e2e_001")
        assert scenario is not None
        assert len(scenario.environment_config.get("termination_conditions", [])) > 0

    @pytest.mark.skipif(
        not _has_e2e_test_scenario(),
        reason="septic_shock_e2e_test.yaml not found"
    )
    def test_lab_thresholds_captured(self):
        """lab_thresholds from YAML captured in environment_config."""
        loader = _get_loader_with_e2e()
        scenario = loader.get_scenario("septic_shock_e2e_001")
        assert scenario is not None
        assert len(scenario.environment_config.get("lab_thresholds", [])) > 0


class TestCreateEnvironmentAppliesEffects:
    """Tests that create_environment uses scenario.environment_config."""

    @pytest.mark.skipif(
        not _has_e2e_test_scenario(),
        reason="septic_shock_e2e_test.yaml not found"
    )
    def test_medication_effects_loaded_to_environment(self):
        """P6 영향도: 환경에 medication_effects 적용.

        Before fix: env.config.medication_effects == [] (always empty)
        After fix: norepinephrine, vasopressor, crystalloid 등 효과 로드
        """
        loader = _get_loader_with_e2e()
        env = loader.create_environment("septic_shock_e2e_001")
        assert len(env.config.medication_effects) >= 3, (
            "At least norepinephrine, vasopressor, crystalloid effects expected"
        )

    @pytest.mark.skipif(
        not _has_e2e_test_scenario(),
        reason="septic_shock_e2e_test.yaml not found"
    )
    def test_norepinephrine_effect_present(self):
        """Specific medication effect: norepinephrine → map_mmhg."""
        loader = _get_loader_with_e2e()
        env = loader.create_environment("septic_shock_e2e_001")
        norepi = [
            e for e in env.config.medication_effects
            if e.medication_pattern == "norepinephrine"
        ]
        assert len(norepi) > 0
        assert norepi[0].target_vital == "map_mmhg"
        assert norepi[0].effect_min > 0

    @pytest.mark.skipif(
        not _has_e2e_test_scenario(),
        reason="septic_shock_e2e_test.yaml not found"
    )
    def test_deterioration_rules_loaded(self):
        """Deterioration rules loaded into environment."""
        loader = _get_loader_with_e2e()
        env = loader.create_environment("septic_shock_e2e_001")
        assert len(env.config.deterioration_rules) >= 1

    @pytest.mark.skipif(
        not _has_e2e_test_scenario(),
        reason="septic_shock_e2e_test.yaml not found"
    )
    def test_termination_conditions_loaded(self):
        """Termination conditions loaded into environment."""
        loader = _get_loader_with_e2e()
        env = loader.create_environment("septic_shock_e2e_001")
        assert len(env.config.termination_conditions) >= 1

    @pytest.mark.skipif(
        not _has_e2e_test_scenario(),
        reason="septic_shock_e2e_test.yaml not found"
    )
    def test_lab_thresholds_loaded(self):
        """Lab thresholds loaded into environment."""
        loader = _get_loader_with_e2e()
        env = loader.create_environment("septic_shock_e2e_001")
        assert len(env.config.lab_thresholds) >= 1


class TestEnvironmentConfigOverrides:
    """Tests that env_config_overrides still work with the fix."""

    @pytest.mark.skipif(
        not _has_e2e_test_scenario(),
        reason="septic_shock_e2e_test.yaml not found"
    )
    def test_override_replaces_scenario_config(self):
        """env_config_overrides take precedence over scenario.environment_config."""
        loader = _get_loader_with_e2e()
        env = loader.create_environment(
            "septic_shock_e2e_001",
            env_config_overrides={"medication_effects": []}
        )
        # Override with empty list
        assert len(env.config.medication_effects) == 0

    @pytest.mark.skipif(
        not _has_e2e_test_scenario(),
        reason="septic_shock_e2e_test.yaml not found"
    )
    def test_override_time_step(self):
        """time_step_minutes can be overridden."""
        loader = _get_loader_with_e2e()
        env = loader.create_environment(
            "septic_shock_e2e_001",
            env_config_overrides={"time_step_minutes": 10}
        )
        assert env.config.time_step_minutes == 10


class TestScenarioWithoutEffects:
    """Tests scenarios that don't define dynamic effects."""

    def test_empty_effects_for_minimal_scenario(self):
        """Scenarios without medication_effects get empty lists (no crash)."""
        loader = ScenarioLoader(str(SCENARIOS_DIR))
        loader._scenarios_cache = {}

        # Manually add a minimal scenario without effects
        from cga_bench.cpg_model.schemas.base import VitalSigns
        minimal_patient = PatientState(
            state_id="p1", age=50, sex="M",
            vitals=VitalSigns(
                heart_rate=80, blood_pressure_systolic=120,
                blood_pressure_diastolic=80, respiratory_rate=16,
                temperature=37.0, oxygen_saturation=98,
            ),
            chief_complaint="test",
        )
        loader._scenarios_cache["minimal"] = ScenarioDefinition(
            scenario_id="minimal",
            description="",
            guideline_graph="",
            patient=minimal_patient,
            ground_truth={"lab_results": {}},
            expected_actions=[],
            forbidden_actions=[],
            optional_actions=[],
            max_duration_minutes=60,
            passing_compliance_threshold=0.8,
            environment_config={},
        )

        env = loader.create_environment("minimal")
        assert len(env.config.medication_effects) == 0
        assert len(env.config.deterioration_rules) == 0


# Need PatientState import for the last test
from cga_bench.cpg_model.schemas.base import PatientState
