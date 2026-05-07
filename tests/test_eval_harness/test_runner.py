"""Tests for EvaluationRunner and ExperimentConfig."""
from __future__ import annotations

import json
import tempfile
import yaml
import pytest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cga_bench.eval_harness.runner import (
    BudgetExceededError,
    ExperimentConfig,
    ExperimentResult,
    EvaluationRunner,
)
from cga_bench.eval_harness.pipeline import PipelineConfig
from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    EpisodeLog,
    HarmSeverity,
    PatientState,
    RecommendationClass,
    ViolationType,
    VitalSigns,
)


# ============================================================================
# ExperimentConfig
# ============================================================================

class TestExperimentConfig:
    def test_basic_creation(self):
        cfg = ExperimentConfig(
            experiment_id="test_001",
            scenarios=["sepsis_001"],
            agents=["oracle"],
        )
        assert cfg.experiment_id == "test_001"
        assert cfg.enforce_budget_matching is False

    def test_budget_enforcement_requires_limits(self):
        with pytest.raises(ValueError, match="Budget matching is enforced"):
            ExperimentConfig(
                experiment_id="test_budget",
                scenarios=["s1"],
                agents=["a1"],
                enforce_budget_matching=True,
                # No budget limits set → error
            )

    def test_budget_enforcement_with_tokens(self):
        cfg = ExperimentConfig(
            experiment_id="test_budget_ok",
            scenarios=["s1"],
            agents=["a1"],
            enforce_budget_matching=True,
            budget_limit_tokens=50000,
        )
        assert cfg.budget_limit_tokens == 50000

    def test_budget_enforcement_with_tool_calls(self):
        cfg = ExperimentConfig(
            experiment_id="test_budget_tools",
            scenarios=["s1"],
            agents=["a1"],
            enforce_budget_matching=True,
            budget_limit_tool_calls=100,
        )
        assert cfg.budget_limit_tool_calls == 100

    def test_seed_sets_random(self):
        cfg = ExperimentConfig(
            experiment_id="test_seed",
            scenarios=["s1"],
            agents=["a1"],
            random_seed=42,
        )
        assert cfg.random_seed == 42

    def test_defaults(self):
        cfg = ExperimentConfig(
            experiment_id="test_defaults",
            scenarios=[],
            agents=[],
        )
        assert cfg.num_runs_per_scenario == 1
        assert cfg.output_dir == "results"
        assert cfg.save_logs is True
        assert cfg.save_scores is True
        assert cfg.pipeline_config is None


# ============================================================================
# BudgetExceededError
# ============================================================================

class TestBudgetExceededError:
    def test_is_runtime_error(self):
        err = BudgetExceededError("tokens exceeded")
        assert isinstance(err, RuntimeError)
        assert "tokens exceeded" in str(err)


# ============================================================================
# EvaluationRunner Initialization
# ============================================================================

class TestEvaluationRunnerInit:
    def test_basic_init(self):
        cfg = ExperimentConfig(
            experiment_id="test",
            scenarios=["s1"],
            agents=["a1"],
        )
        runner = EvaluationRunner(cfg)
        assert runner.config == cfg
        assert runner.results == []
        assert runner._pipeline is None

    def test_init_with_pipeline(self):
        from cga_bench.eval_harness.pipeline import PipelineConfig
        cfg = ExperimentConfig(
            experiment_id="test_pipe",
            scenarios=["s1"],
            agents=["a1"],
            pipeline_config=PipelineConfig(),
        )
        runner = EvaluationRunner(cfg)
        assert runner._pipeline is not None


# ============================================================================
# create_patient_from_config
# ============================================================================

class TestCreatePatient:
    def test_valid_config(self):
        cfg = ExperimentConfig(
            experiment_id="test",
            scenarios=[],
            agents=[],
        )
        runner = EvaluationRunner(cfg)

        patient_config = {
            "age": 65,
            "sex": "M",
            "chief_complaint": "fever, hypotension",
            "vitals": {
                "heart_rate": 110,
                "blood_pressure_systolic": 85,
                "blood_pressure_diastolic": 55,
            },
            "allergies": ["penicillin"],
            "comorbidities": ["diabetes"],
        }
        patient = runner.create_patient_from_config(patient_config)
        assert isinstance(patient, PatientState)
        assert patient.age == 65
        assert patient.sex == "M"
        assert patient.vitals.heart_rate == 110
        assert "penicillin" in patient.allergies

    def test_missing_required_field_raises(self):
        cfg = ExperimentConfig(
            experiment_id="test",
            scenarios=[],
            agents=[],
        )
        runner = EvaluationRunner(cfg)

        patient_config = {
            "age": 65,
            "sex": "M",
            # Missing chief_complaint and vitals
        }
        with pytest.raises(ValueError, match="Required patient field"):
            runner.create_patient_from_config(patient_config)

    def test_optional_fields_default(self):
        cfg = ExperimentConfig(
            experiment_id="test",
            scenarios=[],
            agents=[],
        )
        runner = EvaluationRunner(cfg)

        patient_config = {
            "age": 30,
            "sex": "F",
            "chief_complaint": "cough",
            "vitals": {"heart_rate": 80},
        }
        patient = runner.create_patient_from_config(patient_config)
        assert patient.allergies == []
        assert patient.comorbidities == []


# ============================================================================
# create_environment
# ============================================================================

class TestCreateEnvironment:
    def test_missing_required_field_raises(self):
        cfg = ExperimentConfig(
            experiment_id="test",
            scenarios=[],
            agents=[],
        )
        runner = EvaluationRunner(cfg)

        patient = PatientState(
            state_id="p1",
            age=50,
            sex="M",
            chief_complaint="test",
            vitals=VitalSigns(heart_rate=80),
        )
        scenario_config = {
            "max_duration_minutes": 120,
            # Missing other required fields
        }
        with pytest.raises(ValueError, match="Required field"):
            runner.create_environment(patient, scenario_config)

    def test_empty_ground_truth_raises(self):
        cfg = ExperimentConfig(
            experiment_id="test",
            scenarios=[],
            agents=[],
        )
        runner = EvaluationRunner(cfg)

        patient = PatientState(
            state_id="p1",
            age=50,
            sex="M",
            chief_complaint="test",
            vitals=VitalSigns(heart_rate=80),
        )
        scenario_config = {
            "max_duration_minutes": 120,
            "time_step_minutes": 5,
            "lab_result_delay_minutes": 30,
            "imaging_result_delay_minutes": 15,
            "enable_state_deterioration": False,
            "ground_truth": {},
        }
        with pytest.raises(ValueError, match="ground_truth is required"):
            runner.create_environment(patient, scenario_config)


# ============================================================================
# load_scenario
# ============================================================================

class TestLoadScenario:
    def test_load_yaml_file(self, tmp_path):
        data = {"scenarios": {"s1": {"description": "test"}}}
        f = tmp_path / "test.yaml"
        with open(f, "w") as fp:
            yaml.dump(data, fp)

        cfg = ExperimentConfig(
            experiment_id="test",
            scenarios=[],
            agents=[],
        )
        runner = EvaluationRunner(cfg)
        loaded = runner.load_scenario(str(f))
        assert loaded["scenarios"]["s1"]["description"] == "test"

    def test_nonexistent_file_raises(self):
        cfg = ExperimentConfig(
            experiment_id="test",
            scenarios=[],
            agents=[],
        )
        runner = EvaluationRunner(cfg)
        with pytest.raises(FileNotFoundError):
            runner.load_scenario("/nonexistent/path.yaml")


# ============================================================================
# Helpers for orchestration tests
# ============================================================================

def _runner():
    return EvaluationRunner(ExperimentConfig(
        experiment_id="test", scenarios=[], agents=[],
    ))


def _runner_with_budget(tokens=50000, calls=100):
    return EvaluationRunner(ExperimentConfig(
        experiment_id="test",
        scenarios=[],
        agents=[],
        enforce_budget_matching=True,
        budget_limit_tokens=tokens,
        budget_limit_tool_calls=calls,
    ))


# ============================================================================
# run_episode (mocked orchestration)
# ============================================================================

class TestRunEpisode:
    @patch("cga_bench.eval_harness.runner.HarmScorer")
    @patch("cga_bench.eval_harness.runner.ViolationExtractor")
    @patch("cga_bench.eval_harness.runner.CPGEngineFactory")
    def test_returns_episode_log_score_violations(
        self, MockFactory, MockExtractor, MockScorer
    ):
        runner = _runner()

        # Mock agent
        agent = MagicMock()
        mock_log = MagicMock(spec=EpisodeLog)
        agent.run_episode.return_value = mock_log

        # Mock CPG engine factory
        mock_engine = MagicMock()
        MockFactory.load_from_file.return_value = mock_engine

        # Mock extractor
        mock_violations = [MagicMock()]
        MockExtractor.return_value.extract_violations.return_value = mock_violations

        # Mock scorer
        mock_score = MagicMock()
        MockScorer.return_value.compute_score.return_value = mock_score

        env = MagicMock()
        extractor_cfg = MagicMock()
        scorer_cfg = MagicMock()

        result = runner.run_episode(
            agent=agent,
            environment=env,
            scenario_id="test_scenario",
            guideline_graph_path="fake_graph.yaml",
            total_mandatory_count=5,
            violation_extractor_config=extractor_cfg,
            harm_scorer_config=scorer_cfg,
        )

        episode_log, score, violations = result
        assert episode_log is mock_log
        assert score is mock_score
        assert violations == mock_violations
        agent.run_episode.assert_called_once_with(env, "test_scenario")
        MockFactory.load_from_file.assert_called_once_with("fake_graph.yaml")

    @patch("cga_bench.eval_harness.runner.HarmScorer")
    @patch("cga_bench.eval_harness.runner.ViolationExtractor")
    @patch("cga_bench.eval_harness.runner.CPGEngineFactory")
    def test_budget_enforcement_sets_agent_limits(
        self, MockFactory, MockExtractor, MockScorer
    ):
        runner = _runner_with_budget(tokens=10000, calls=20)

        agent = MagicMock()
        agent.run_episode.return_value = MagicMock(spec=EpisodeLog)
        agent.metrics.total_tokens = 5000
        agent.metrics.total_tool_calls = 10
        MockFactory.load_from_file.return_value = MagicMock()
        MockExtractor.return_value.extract_violations.return_value = []
        MockScorer.return_value.compute_score.return_value = MagicMock()

        runner.run_episode(
            agent=agent,
            environment=MagicMock(),
            scenario_id="s1",
            guideline_graph_path="g.yaml",
            total_mandatory_count=3,
            violation_extractor_config=MagicMock(),
            harm_scorer_config=MagicMock(),
        )

        assert agent.config.budget_limit_tokens == 10000
        assert agent.config.budget_limit_tool_calls == 20

    @patch("cga_bench.eval_harness.runner.CPGEngineFactory")
    def test_budget_exceeded_raises(self, MockFactory):
        runner = _runner_with_budget(tokens=100, calls=5)

        agent = MagicMock()
        agent.run_episode.return_value = MagicMock(spec=EpisodeLog)
        agent.metrics.total_tokens = 500  # Exceeds 100
        agent.metrics.total_tool_calls = 2

        with pytest.raises(BudgetExceededError, match="Token budget exceeded"):
            runner.run_episode(
                agent=agent,
                environment=MagicMock(),
                scenario_id="s1",
                guideline_graph_path="g.yaml",
                total_mandatory_count=1,
                violation_extractor_config=MagicMock(),
                harm_scorer_config=MagicMock(),
            )


# ============================================================================
# _parse_violation_extractor_config
# ============================================================================

class TestParseViolationExtractorConfig:
    def test_basic_parsing(self):
        runner = _runner()
        config_dict = {
            "harm_severity_mappings": [
                {"action_pattern": "lactate", "severity": "major"},
            ],
            "timing_severity_thresholds": [
                {"max_delay_minutes": 60, "severity": "moderate"},
            ],
            "default_deviation_severity": "minor",
            "default_deviation_preventability": 0.8,
        }
        result = runner._parse_violation_extractor_config(config_dict)
        assert result.default_deviation_severity == HarmSeverity.MINOR
        assert result.default_deviation_preventability == 0.8
        assert len(result.harm_severity_mappings) == 1
        assert len(result.timing_severity_thresholds) == 1

    def test_empty_mappings(self):
        runner = _runner()
        config_dict = {
            "harm_severity_mappings": [],
            "timing_severity_thresholds": [],
            "default_deviation_severity": "moderate",
            "default_deviation_preventability": 1.0,
        }
        result = runner._parse_violation_extractor_config(config_dict)
        assert result.harm_severity_mappings == []
        assert result.timing_severity_thresholds == []


# ============================================================================
# _parse_harm_scorer_config
# ============================================================================

class TestParseHarmScorerConfig:
    def test_basic_parsing(self):
        runner = _runner()
        config_dict = {
            "severity_weights": {"minor": 0.1, "moderate": 0.4, "major": 0.7},
            "guideline_strength_weights": {"I": 1.0, "null": 0.5},
            "violation_type_weights": {"omission": 1.0, "commission": 1.5},
        }
        result = runner._parse_harm_scorer_config(config_dict)
        assert HarmSeverity.MINOR in result.severity_weights
        assert result.severity_weights[HarmSeverity.MINOR] == 0.1
        assert None in result.guideline_strength_weights
        assert result.guideline_strength_weights[None] == 0.5
        assert ViolationType.OMISSION in result.violation_type_weights

    def test_with_interaction_config(self):
        runner = _runner()
        config_dict = {
            "severity_weights": {"minor": 0.1},
            "guideline_strength_weights": {"null": 1.0},
            "violation_type_weights": {"omission": 1.0},
            "interaction_config": {
                "interaction_patterns": [],
                "enable_temporal_proximity": False,
            },
        }
        result = runner._parse_harm_scorer_config(config_dict)
        assert result.interaction_config is not None
        assert result.interaction_config.enable_temporal_proximity is False


# ============================================================================
# _parse_interaction_config
# ============================================================================

class TestParseInteractionConfig:
    def test_empty_patterns(self):
        runner = _runner()
        result = runner._parse_interaction_config({
            "interaction_patterns": [],
        })
        assert result.interaction_patterns == []
        assert result.enable_temporal_proximity is True  # default

    def test_full_pattern(self):
        runner = _runner()
        result = runner._parse_interaction_config({
            "interaction_patterns": [{
                "pattern_id": "p1",
                "interaction_type": "temporal_proximity",
                "violation_type_a": "omission",
                "violation_type_b": "commission",
                "action_pattern_a": "lactate",
                "temporal_window_minutes": 30,
                "multiplier": 2.0,
                "max_multiplier": 3.0,
                "clinical_rationale": "test",
            }],
            "enable_triple_jeopardy": False,
            "triple_jeopardy_multiplier": 3.0,
        })
        assert len(result.interaction_patterns) == 1
        p = result.interaction_patterns[0]
        assert p.pattern_id == "p1"
        assert p.multiplier == 2.0
        assert result.enable_triple_jeopardy is False


# ============================================================================
# _compute_mandatory_count_from_graph
# ============================================================================

class TestComputeMandatoryCount:
    def test_counts_unique_mandatory_actions(self, tmp_path):
        graph = {
            "nodes": {
                "node_a": {"mandatory_actions": ["lactate", "antibiotics"]},
                "node_b": {"mandatory_actions": ["antibiotics", "blood_culture"]},
            }
        }
        f = tmp_path / "test_graph.yaml"
        with open(f, "w") as fp:
            yaml.dump(graph, fp)

        runner = _runner()
        count = runner._compute_mandatory_count_from_graph(str(f))
        assert count == 3  # lactate, antibiotics, blood_culture (unique)

    def test_no_mandatory_returns_one(self, tmp_path):
        graph = {"nodes": {"node_a": {"allowed_actions": ["something"]}}}
        f = tmp_path / "empty_graph.yaml"
        with open(f, "w") as fp:
            yaml.dump(graph, fp)

        runner = _runner()
        count = runner._compute_mandatory_count_from_graph(str(f))
        assert count == 1  # default to avoid division by zero

    def test_nonexistent_file_raises(self):
        runner = _runner()
        with pytest.raises(ValueError, match="file not found"):
            runner._compute_mandatory_count_from_graph("/nonexistent/graph.yaml")

    def test_invalid_yaml_raises(self, tmp_path):
        f = tmp_path / "bad.yaml"
        f.write_text("{bad yaml: [unclosed")
        runner = _runner()
        with pytest.raises(ValueError, match="YAML parse error"):
            runner._compute_mandatory_count_from_graph(str(f))


# ============================================================================
# _actions_to_raw_events
# ============================================================================

class TestActionsToRawEvents:
    def test_converts_actions_correctly(self):
        runner = _runner()
        episode_log = MagicMock(spec=EpisodeLog)
        episode_log.actions = [
            Action(
                type=ActionType.ORDER_LAB,
                action_id="order_lab_lactate",
                args={"urgency": "stat"},
                timestamp_minutes=5.0,
            ),
            Action(
                type=ActionType.GIVE_MEDICATION,
                action_id="give_antibiotics",
                args={},
                timestamp_minutes=10.0,
            ),
        ]

        events = runner._actions_to_raw_events(episode_log)
        assert len(events) == 2
        assert events[0]["activity"] == "ORDER_LAB_LACTATE"
        assert events[0]["timestamp_ms"] == 300000.0  # 5 * 60000
        assert events[1]["activity"] == "GIVE_ANTIBIOTICS"
        assert events[1]["timestamp_ms"] == 600000.0

    def test_empty_actions(self):
        runner = _runner()
        episode_log = MagicMock(spec=EpisodeLog)
        episode_log.actions = []
        events = runner._actions_to_raw_events(episode_log)
        assert events == []


# ============================================================================
# _parse_pipeline_config
# ============================================================================

class TestParsePipelineConfig:
    def test_all_defaults(self):
        runner = _runner()
        result = runner._parse_pipeline_config({})
        assert result.enable_xes_export is False
        assert result.enable_ltl_verification is False
        assert result.enable_llm_judge is False
        assert result.enable_pathway_mining is False

    def test_custom_values(self):
        runner = _runner()
        result = runner._parse_pipeline_config({
            "enable_xes_export": True,
            "xes_output_dir": "/tmp/xes",
            "enable_llm_judge": True,
            "llm_judge_backend": "anthropic",
            "llm_judge_model": "claude-3",
        })
        assert result.enable_xes_export is True
        assert result.xes_output_dir == "/tmp/xes"
        assert result.llm_judge_backend == "anthropic"
        assert result.llm_judge_model == "claude-3"


# ============================================================================
# save_results
# ============================================================================

class TestSaveResults:
    def test_save_creates_output_dir(self, tmp_path):
        cfg = ExperimentConfig(
            experiment_id="test_save",
            scenarios=[],
            agents=[],
            output_dir=str(tmp_path / "results"),
        )
        runner = EvaluationRunner(cfg)
        # No results to save, but directory should be created
        runner.save_results()
        assert (tmp_path / "results").exists()

    def test_save_to_custom_path(self, tmp_path):
        runner = _runner()
        custom_path = tmp_path / "custom_output"
        runner.save_results(output_path=str(custom_path))
        assert custom_path.exists()
