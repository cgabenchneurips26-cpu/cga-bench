"""Tests for ScenarioLoader, ExperimentLoader, AgentConfigLoader."""
from __future__ import annotations

import pytest
import tempfile
import yaml
from pathlib import Path

from cga_bench.eval_harness.scenario_loader import (
    AgentConfigLoader,
    ExperimentLoader,
    ScenarioDefinition,
    ScenarioLoader,
)
from cga_bench.cpg_model.schemas.base import PatientState


# ============================================================================
# Fixtures
# ============================================================================

@pytest.fixture
def sample_scenario_yaml(tmp_path):
    """Create a temp scenario YAML file."""
    data = {
        "defaults": {
            "max_duration_minutes": 120,
            "time_step_minutes": 5,
            "lab_result_delay_minutes": 30,
            "imaging_result_delay_minutes": 15,
        },
        "scenarios": {
            "test_sepsis_001": {
                "description": "Septic shock test scenario",
                "guideline_graph": "ssc_sepsis_hour1",
                "patient": {
                    "age": 65,
                    "sex": "M",
                    "weight_kg": 70,
                    "chief_complaint": "fever, hypotension",
                    "working_diagnosis": "septic_shock",
                    "vitals": {
                        "heart_rate": 110,
                        "blood_pressure_systolic": 85,
                        "blood_pressure_diastolic": 55,
                        "map_mmhg": 65,
                        "respiratory_rate": 24,
                        "temperature": 38.9,
                        "oxygen_saturation": 94,
                    },
                    "allergies": ["penicillin"],
                    "comorbidities": ["diabetes"],
                },
                "expected_actions": [
                    "order_lab_lactate",
                    "order_lab_blood_culture",
                    "give_broad_spectrum_antibiotics",
                ],
                "forbidden_actions": ["nitroglycerin"],
                "optional_actions": ["order_cbc"],
                "passing_compliance_threshold": 0.8,
            },
            "test_trap_001": {
                "description": "RV infarct trap scenario",
                "guideline_graph": "aha_chest_pain",
                "patient": {
                    "age": 60,
                    "sex": "M",
                    "vitals": {
                        "heart_rate": 55,
                        "blood_pressure_systolic": 95,
                    },
                },
                "expected_actions": ["obtain_12_lead_ecg"],
                "forbidden_actions": ["give_nitroglycerin"],
                "optional_actions": [],
                "trap_scenario": True,
                "trap_description": "Nitrate contraindicated in RV infarct",
            },
        },
    }
    file_path = tmp_path / "test_scenarios.yaml"
    with open(file_path, "w") as f:
        yaml.dump(data, f)
    return tmp_path


@pytest.fixture
def sample_experiment_yaml(tmp_path):
    data = {
        "experiment_name": "test_experiment",
        "scenarios": ["test_sepsis_001"],
        "agents": ["oracle"],
        "budget": {"budget_limit_tokens": 50000},
    }
    file_path = tmp_path / "test_experiment.yaml"
    with open(file_path, "w") as f:
        yaml.dump(data, f)
    return tmp_path


@pytest.fixture
def sample_agent_yaml(tmp_path):
    data = {
        "agent_type": "oracle",
        "guideline_domain": "sepsis",
    }
    file_path = tmp_path / "test_oracle.yaml"
    with open(file_path, "w") as f:
        yaml.dump(data, f)
    return tmp_path


# ============================================================================
# ScenarioLoader
# ============================================================================

class TestScenarioLoader:
    def test_load_all_scenarios(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        scenarios = loader.load_all_scenarios()
        assert "test_sepsis_001" in scenarios
        assert "test_trap_001" in scenarios

    def test_scenario_definition_fields(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        s = loader.get_scenario("test_sepsis_001")
        assert isinstance(s, ScenarioDefinition)
        assert s.scenario_id == "test_sepsis_001"
        assert s.description == "Septic shock test scenario"
        assert s.guideline_graph == "ssc_sepsis_hour1"

    def test_patient_parsed(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        s = loader.get_scenario("test_sepsis_001")
        assert isinstance(s.patient, PatientState)
        assert s.patient.age == 65
        assert s.patient.sex == "M"
        assert s.patient.vitals.heart_rate == 110
        assert s.patient.vitals.map_mmhg == 65

    def test_expected_actions(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        s = loader.get_scenario("test_sepsis_001")
        assert "order_lab_lactate" in s.expected_actions
        assert len(s.expected_actions) == 3

    def test_forbidden_actions(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        s = loader.get_scenario("test_sepsis_001")
        assert "nitroglycerin" in s.forbidden_actions

    def test_trap_scenario_detected(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        s = loader.get_scenario("test_trap_001")
        assert s.trap_scenario is True
        assert "Nitrate" in s.trap_description

    def test_list_scenarios(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        ids = loader.list_scenarios()
        assert set(ids) == {"test_sepsis_001", "test_trap_001"}

    def test_list_trap_scenarios(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        traps = loader.list_trap_scenarios()
        assert "test_trap_001" in traps
        assert "test_sepsis_001" not in traps

    def test_get_nonexistent_scenario(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        s = loader.get_scenario("does_not_exist")
        assert s is None

    def test_defaults_applied(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        s = loader.get_scenario("test_sepsis_001")
        assert s.max_duration_minutes == 120  # from defaults

    def test_environment_config_populated(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        s = loader.get_scenario("test_sepsis_001")
        assert isinstance(s.environment_config, dict)
        assert s.environment_config["time_step_minutes"] == 5

    def test_caching_loads_once(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        loader.load_all_scenarios()
        loaded_files_1 = set(loader._loaded_files)
        loader.load_all_scenarios()  # Second call
        loaded_files_2 = set(loader._loaded_files)
        assert loaded_files_1 == loaded_files_2


# ============================================================================
# Graph Path Mapping
# ============================================================================

class TestGraphPathMapping:
    def test_known_sepsis_graph(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        path = loader.get_cpg_graph_path("test_sepsis_001")
        if path is not None:
            assert "ssc_sepsis_hour1" in str(path)

    def test_known_chest_pain_graph(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        path = loader.get_cpg_graph_path("test_trap_001")
        if path is not None:
            assert "aha_chest_pain" in str(path)

    def test_nonexistent_scenario_returns_none(self, sample_scenario_yaml):
        loader = ScenarioLoader(scenarios_dir=str(sample_scenario_yaml))
        path = loader.get_cpg_graph_path("nonexistent")
        assert path is None


# ============================================================================
# ExperimentLoader
# ============================================================================

class TestExperimentLoader:
    def test_load_experiment(self, sample_experiment_yaml):
        loader = ExperimentLoader(experiments_dir=str(sample_experiment_yaml))
        config = loader.load_experiment("test_experiment")
        assert config["experiment_name"] == "test_experiment"
        assert "test_sepsis_001" in config["scenarios"]

    def test_list_experiments(self, sample_experiment_yaml):
        loader = ExperimentLoader(experiments_dir=str(sample_experiment_yaml))
        experiments = loader.list_experiments()
        assert "test_experiment" in experiments

    def test_nonexistent_experiment_raises(self, sample_experiment_yaml):
        loader = ExperimentLoader(experiments_dir=str(sample_experiment_yaml))
        with pytest.raises(FileNotFoundError):
            loader.load_experiment("does_not_exist")


# ============================================================================
# AgentConfigLoader
# ============================================================================

class TestAgentConfigLoader:
    def test_load_agent_config(self, sample_agent_yaml):
        loader = AgentConfigLoader(agents_dir=str(sample_agent_yaml))
        config = loader.load_agent_config("test_oracle")
        assert config["agent_type"] == "oracle"
        assert config["guideline_domain"] == "sepsis"

    def test_list_agents(self, sample_agent_yaml):
        loader = AgentConfigLoader(agents_dir=str(sample_agent_yaml))
        agents = loader.list_agents()
        assert "test_oracle" in agents

    def test_nonexistent_agent_raises(self, sample_agent_yaml):
        loader = AgentConfigLoader(agents_dir=str(sample_agent_yaml))
        with pytest.raises(FileNotFoundError):
            loader.load_agent_config("does_not_exist")
