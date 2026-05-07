"""
Integration tests for PostScoringPipeline + EvaluationRunner.

Tests:
- Backward compatibility (no pipeline config)
- Pipeline config parsing
- Per-episode pipeline (XES, LTL)
- Batch-level pipeline (pathway mining)
- Runner integration (save_results with pipeline data)
"""
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    CGAScore,
    EpisodeLog,
    PatientState,
    ViolationEvent,
    ViolationType,
    HarmSeverity,
    VitalSigns,
    RecommendationClass,
)
from cga_bench.eval_harness.pipeline import (
    BatchPipelineResult,
    EpisodePipelineResult,
    PipelineConfig,
    PostScoringPipeline,
)
from cga_bench.eval_harness.runner import (
    EvaluationRunner,
    ExperimentConfig,
    ExperimentResult,
)


# ============================================
# Fixtures
# ============================================

def _make_actions(action_ids, start_time=0.0, step=5.0):
    """Create a list of Action objects."""
    actions = []
    for i, aid in enumerate(action_ids):
        actions.append(Action(
            type=ActionType.ORDER_LAB if "order" in aid.lower() else ActionType.GIVE_MEDICATION,
            action_id=aid,
            args={},
            timestamp_minutes=start_time + i * step,
        ))
    return actions


def _make_patient_state():
    """Create a minimal PatientState."""
    return PatientState(
        state_id="s0",
        age=65,
        sex="M",
        vitals=VitalSigns(heart_rate=90),
        chief_complaint="chest pain",
    )


def _make_episode_log(action_ids=None):
    """Create a minimal EpisodeLog."""
    if action_ids is None:
        action_ids = ["order_ecg", "order_troponin", "give_aspirin", "activate_cath_lab"]
    return EpisodeLog(
        episode_id="test_ep_001",
        scenario_id="test_scenario",
        agent_id="test_agent",
        states=[_make_patient_state()],
        actions=_make_actions(action_ids),
        observations=[{}],
        total_duration_minutes=len(action_ids) * 5.0,
        total_llm_calls=1,
        total_tokens=100,
        total_tool_calls=len(action_ids),
        termination_reason="success",
    )


def _make_violations():
    """Create sample ViolationEvent objects matching schema."""
    return [
        ViolationEvent(
            violation_id="v1",
            violation_type=ViolationType.OMISSION,
            timestamp_minutes=10.0,
            action_involved=None,
            expected_action="order_blood_culture",
            state_at_violation="s0",
            node_at_violation="n1",
            harm_severity=HarmSeverity.MODERATE,
            description="Missing blood culture",
            guideline_reference="SSC 2021",
        ),
        ViolationEvent(
            violation_id="v2",
            violation_type=ViolationType.TIMING,
            timestamp_minutes=65.0,
            action_involved="give_antibiotics",
            state_at_violation="s0",
            node_at_violation="n2",
            harm_severity=HarmSeverity.MAJOR,
            description="Antibiotics delayed",
            guideline_reference="SSC 2021",
        ),
    ]


def _make_score(compliance=0.85, peak_risk=0.4, aggregate_risk=0.3):
    """Create a minimal CGAScore."""
    return CGAScore(
        episode_id="test_ep_001",
        compliance_score=compliance,
        peak_risk=peak_risk,
        aggregate_risk=aggregate_risk,
        total_violations=2,
        sub_scores={"C1": 0.9, "C2": 0.8},
        violations_by_type={"OMISSION": 1, "TIMING": 1},
        violation_events=_make_violations(),
        justified_deviations=0,
        budget_usage={"tokens": 100, "tool_calls": 4},
    )


# ============================================
# Test: PipelineConfig defaults (backward compat)
# ============================================

class TestPipelineConfigDefaults:
    def test_all_disabled_by_default(self):
        config = PipelineConfig()
        assert not config.enable_xes_export
        assert not config.enable_ltl_verification
        assert not config.enable_llm_judge
        assert not config.enable_pathway_mining

    def test_no_op_pipeline(self):
        """Pipeline with all disabled is a no-op."""
        pipeline = PostScoringPipeline(PipelineConfig())
        result = pipeline.process_episode(
            episode_id="ep1",
            raw_events=[{"activity": "ORDER_ECG", "timestamp_ms": 0}],
            score=_make_score(),
            violations=_make_violations(),
        )
        assert result.episode_id == "ep1"
        assert result.xes_path is None
        assert result.ltl_satisfied is None
        assert result.ltl_violated is None
        assert not result.llm_judge_applied

    def test_batch_no_op(self):
        pipeline = PostScoringPipeline(PipelineConfig())
        result = pipeline.process_batch([])
        assert result.total_pathways == 0
        assert result.num_clusters == 0


# ============================================
# Test: XES Export Integration
# ============================================

class TestXESExportIntegration:
    def test_xes_export_creates_file(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            config = PipelineConfig(
                enable_xes_export=True,
                xes_output_dir=tmpdir,
            )
            pipeline = PostScoringPipeline(config)
            raw_events = [
                {"activity": "ORDER_ECG", "timestamp_ms": 0},
                {"activity": "ORDER_TROPONIN", "timestamp_ms": 60000},
                {"activity": "GIVE_ASPIRIN", "timestamp_ms": 120000},
            ]
            result = pipeline.process_episode(
                episode_id="xes_test_001",
                raw_events=raw_events,
                score=_make_score(),
                violations=_make_violations(),
            )
            assert result.xes_path is not None
            xes_file = Path(result.xes_path)
            assert xes_file.exists()
            content = xes_file.read_text()
            assert "xes_test_001" in content

    def test_xes_export_no_output_dir(self):
        """XES export without output dir returns None path."""
        config = PipelineConfig(
            enable_xes_export=True,
            xes_output_dir=None,
        )
        pipeline = PostScoringPipeline(config)
        result = pipeline.process_episode(
            episode_id="no_dir",
            raw_events=[{"activity": "ASSESS", "timestamp_ms": 0}],
            score=_make_score(),
            violations=[],
        )
        assert result.xes_path is None


# ============================================
# Test: LTL Verification Integration
# ============================================

class TestLTLVerificationIntegration:
    def test_ltl_no_properties_file(self):
        """LTL enabled without properties file: 0 satisfied, 0 violated."""
        config = PipelineConfig(
            enable_ltl_verification=True,
            ltl_properties_file=None,
        )
        pipeline = PostScoringPipeline(config)
        result = pipeline.process_episode(
            episode_id="ltl_no_file",
            raw_events=[{"activity": "ORDER_ECG", "timestamp_ms": 0}],
            score=_make_score(),
            violations=[],
        )
        assert result.ltl_satisfied == 0
        assert result.ltl_violated == 0

    def test_ltl_with_chest_pain_properties(self):
        """LTL verification against chest pain property file."""
        props_file = str(
            Path(__file__).resolve().parents[2]
            / "configs" / "ltl_properties_chest_pain.yaml"
        )
        if not Path(props_file).exists():
            pytest.skip("ltl_properties_chest_pain.yaml not found")

        config = PipelineConfig(
            enable_ltl_verification=True,
            ltl_properties_file=props_file,
        )
        pipeline = PostScoringPipeline(config)
        # Trace that satisfies existence_ecg, existence_troponin, existence_aspirin
        raw_events = [
            {"activity": "ASSESS_VITALS", "timestamp_ms": 0},
            {"activity": "ORDER_ECG", "timestamp_ms": 60000},
            {"activity": "ORDER_TROPONIN", "timestamp_ms": 120000},
            {"activity": "GIVE_ASPIRIN", "timestamp_ms": 180000},
        ]
        result = pipeline.process_episode(
            episode_id="ltl_chest_pain",
            raw_events=raw_events,
            score=_make_score(),
            violations=[],
        )
        assert result.ltl_satisfied is not None
        assert result.ltl_satisfied >= 3  # At least the 3 existence properties

    def test_ltl_violation_detected(self):
        """Trace violating existence property."""
        props_file = str(
            Path(__file__).resolve().parents[2]
            / "configs" / "ltl_properties_chest_pain.yaml"
        )
        if not Path(props_file).exists():
            pytest.skip("ltl_properties_chest_pain.yaml not found")

        config = PipelineConfig(
            enable_ltl_verification=True,
            ltl_properties_file=props_file,
        )
        pipeline = PostScoringPipeline(config)
        # Minimal trace: no ECG, no troponin, no aspirin
        raw_events = [
            {"activity": "ASSESS_VITALS", "timestamp_ms": 0},
        ]
        result = pipeline.process_episode(
            episode_id="ltl_violation",
            raw_events=raw_events,
            score=_make_score(),
            violations=[],
        )
        assert result.ltl_violated is not None
        assert result.ltl_violated >= 3  # Missing existence properties
        assert len(result.ltl_violations) >= 3


# ============================================
# Test: Pathway Mining Integration
# ============================================

class TestPathwayMiningIntegration:
    def test_mining_single_episode(self):
        """Single episode: pathway extracted but no clustering."""
        config = PipelineConfig(
            enable_pathway_mining=True,
            mining_ged_threshold=3.0,
            mining_min_cluster_size=2,
        )
        pipeline = PostScoringPipeline(config)
        episode_data = [
            {
                "episode_id": "ep1",
                "raw_events": [
                    {"activity": "ASSESS", "timestamp_ms": 0},
                    {"activity": "DIAGNOSE", "timestamp_ms": 60000},
                    {"activity": "TREAT", "timestamp_ms": 120000},
                ],
                "score": _make_score(compliance=0.9),
            }
        ]
        result = pipeline.process_batch(episode_data)
        assert result.total_pathways == 1
        # Single pathway can't cluster
        assert result.num_clusters == 0

    def test_mining_multiple_similar_episodes(self):
        """Similar episodes should cluster together."""
        config = PipelineConfig(
            enable_pathway_mining=True,
            mining_ged_threshold=3.0,
            mining_min_cluster_size=2,
        )
        pipeline = PostScoringPipeline(config)
        episode_data = []
        for i in range(5):
            episode_data.append({
                "episode_id": f"ep_{i}",
                "raw_events": [
                    {"activity": "ASSESS", "timestamp_ms": 0},
                    {"activity": "DIAGNOSE", "timestamp_ms": 60000},
                    {"activity": "TREAT", "timestamp_ms": 120000},
                ],
                "score": _make_score(compliance=0.8 + i * 0.02),
            })
        result = pipeline.process_batch(episode_data)
        assert result.total_pathways == 5
        # Identical pathways should all cluster
        assert result.num_clusters >= 1

    def test_mining_disabled(self):
        """Mining disabled returns empty result."""
        config = PipelineConfig(enable_pathway_mining=False)
        pipeline = PostScoringPipeline(config)
        result = pipeline.process_batch([{
            "episode_id": "ep1",
            "raw_events": [{"activity": "X", "timestamp_ms": 0}],
            "score": _make_score(),
        }])
        assert result.total_pathways == 0


# ============================================
# Test: Runner Integration
# ============================================

class TestRunnerPipelineIntegration:
    def test_runner_no_pipeline(self):
        """Runner without pipeline_config is backward compatible."""
        config = ExperimentConfig(
            experiment_id="test_no_pipe",
            scenarios=["s1"],
            agents=["a1"],
            pipeline_config=None,
        )
        runner = EvaluationRunner(config)
        assert runner._pipeline is None
        assert runner._last_batch_result is None

    def test_runner_with_pipeline_config(self):
        """Runner with pipeline_config initializes pipeline."""
        config = ExperimentConfig(
            experiment_id="test_with_pipe",
            scenarios=["s1"],
            agents=["a1"],
            pipeline_config=PipelineConfig(
                enable_xes_export=True,
                xes_output_dir="/tmp/xes_test",
            ),
        )
        runner = EvaluationRunner(config)
        assert runner._pipeline is not None

    def test_actions_to_raw_events(self):
        """_actions_to_raw_events produces correct format."""
        runner = EvaluationRunner(ExperimentConfig(
            experiment_id="test",
            scenarios=[],
            agents=[],
        ))
        episode_log = _make_episode_log(["order_ecg", "give_aspirin"])
        raw_events = runner._actions_to_raw_events(episode_log)
        assert len(raw_events) == 2
        assert raw_events[0]["activity"] == "ORDER_ECG"
        assert raw_events[1]["activity"] == "GIVE_ASPIRIN"
        assert raw_events[0]["timestamp_ms"] == 0.0
        assert raw_events[1]["timestamp_ms"] == 5.0 * 60000

    def test_parse_pipeline_config(self):
        """_parse_pipeline_config converts dict to PipelineConfig."""
        runner = EvaluationRunner(ExperimentConfig(
            experiment_id="test",
            scenarios=[],
            agents=[],
        ))
        config_dict = {
            "enable_xes_export": True,
            "xes_output_dir": "/tmp/xes",
            "enable_ltl_verification": True,
            "ltl_properties_file": "/some/path.yaml",
            "enable_pathway_mining": True,
            "mining_ged_threshold": 2.5,
        }
        pc = runner._parse_pipeline_config(config_dict)
        assert pc.enable_xes_export is True
        assert pc.xes_output_dir == "/tmp/xes"
        assert pc.enable_ltl_verification is True
        assert pc.ltl_properties_file == "/some/path.yaml"
        assert pc.enable_pathway_mining is True
        assert pc.mining_ged_threshold == 2.5
        # Defaults preserved
        assert pc.enable_llm_judge is False
        assert pc.mining_min_cluster_size == 2

    def test_save_results_with_pipeline(self):
        """save_results includes pipeline and batch data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ExperimentConfig(
                experiment_id="save_test",
                scenarios=[],
                agents=[],
                output_dir=tmpdir,
            )
            runner = EvaluationRunner(config)

            # Inject a result with pipeline data
            ep_result = EpisodePipelineResult(
                episode_id="ep1",
                xes_path="/tmp/ep1.xes",
                ltl_satisfied=5,
                ltl_violated=2,
                ltl_violations=["existence_ecg", "existence_troponin"],
                llm_judge_applied=True,
                severity_changes=1,
            )
            runner.results.append(ExperimentResult(
                experiment_id="save_test",
                scenario_id="s1",
                agent_id="a1",
                run_number=0,
                episode_log=_make_episode_log(),
                score=_make_score(),
                timestamp="2024-01-01T00:00:00",
                pipeline_result=ep_result,
            ))

            # Inject batch result
            runner._last_batch_result = BatchPipelineResult(
                total_pathways=3,
                num_clusters=1,
                high_performing=["ep1"],
                low_performing=["ep3"],
                significant_correlations=[
                    {"feature": "length", "dimension": "compliance",
                     "correlation": 0.85, "p_value": 0.01}
                ],
            )

            runner.save_results()

            # Verify saved JSON
            summary_path = Path(tmpdir) / "save_test_summary.json"
            assert summary_path.exists()
            data = json.loads(summary_path.read_text())

            # Per-episode pipeline data
            assert "pipeline" in data["results"][0]
            pipe = data["results"][0]["pipeline"]
            assert pipe["xes_path"] == "/tmp/ep1.xes"
            assert pipe["ltl_satisfied"] == 5
            assert pipe["ltl_violated"] == 2
            assert pipe["llm_judge_applied"] is True

            # Batch pipeline data
            assert "batch_pipeline" in data
            batch = data["batch_pipeline"]
            assert batch["total_pathways"] == 3
            assert batch["num_clusters"] == 1
            assert len(batch["significant_correlations"]) == 1

    def test_save_results_no_pipeline(self):
        """save_results without pipeline data is backward compatible."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = ExperimentConfig(
                experiment_id="no_pipe",
                scenarios=[],
                agents=[],
                output_dir=tmpdir,
            )
            runner = EvaluationRunner(config)
            runner.results.append(ExperimentResult(
                experiment_id="no_pipe",
                scenario_id="s1",
                agent_id="a1",
                run_number=0,
                episode_log=_make_episode_log(),
                score=_make_score(),
                timestamp="2024-01-01T00:00:00",
            ))
            runner.save_results()

            summary_path = Path(tmpdir) / "no_pipe_summary.json"
            data = json.loads(summary_path.read_text())
            assert "pipeline" not in data["results"][0]
            assert "batch_pipeline" not in data


# ============================================
# Test: Full Pipeline Flow
# ============================================

class TestFullPipelineFlow:
    def test_combined_xes_and_ltl(self):
        """Run XES + LTL together in one pipeline call."""
        props_file = str(
            Path(__file__).resolve().parents[2]
            / "configs" / "ltl_properties_sepsis.yaml"
        )
        if not Path(props_file).exists():
            pytest.skip("ltl_properties_sepsis.yaml not found")

        with tempfile.TemporaryDirectory() as tmpdir:
            config = PipelineConfig(
                enable_xes_export=True,
                xes_output_dir=tmpdir,
                enable_ltl_verification=True,
                ltl_properties_file=props_file,
            )
            pipeline = PostScoringPipeline(config)
            raw_events = [
                {"activity": "ORDER_LACTATE", "timestamp_ms": 0},
                {"activity": "ORDER_BLOOD_CULTURE", "timestamp_ms": 30000},
                {"activity": "GIVE_ANTIBIOTICS", "timestamp_ms": 60000},
                {"activity": "GIVE_CRYSTALLOID", "timestamp_ms": 120000},
            ]
            result = pipeline.process_episode(
                episode_id="combined_test",
                raw_events=raw_events,
                score=_make_score(),
                violations=_make_violations(),
            )
            # XES exported
            assert result.xes_path is not None
            assert Path(result.xes_path).exists()
            # LTL verified
            assert result.ltl_satisfied is not None
            assert result.ltl_satisfied + result.ltl_violated > 0

    def test_combined_xes_ltl_mining(self):
        """Full flow: per-episode XES+LTL, then batch mining."""
        with tempfile.TemporaryDirectory() as tmpdir:
            config = PipelineConfig(
                enable_xes_export=True,
                xes_output_dir=tmpdir,
                enable_pathway_mining=True,
                mining_ged_threshold=5.0,
                mining_min_cluster_size=2,
            )
            pipeline = PostScoringPipeline(config)

            batch_data = []
            for i in range(4):
                raw_events = [
                    {"activity": "ASSESS", "timestamp_ms": 0},
                    {"activity": "DIAGNOSE", "timestamp_ms": 60000},
                    {"activity": "TREAT", "timestamp_ms": 120000},
                ]
                ep_id = f"batch_ep_{i}"
                result = pipeline.process_episode(
                    episode_id=ep_id,
                    raw_events=raw_events,
                    score=_make_score(compliance=0.7 + i * 0.05),
                    violations=[],
                )
                assert result.xes_path is not None
                batch_data.append({
                    "episode_id": ep_id,
                    "raw_events": raw_events,
                    "score": _make_score(compliance=0.7 + i * 0.05),
                })

            # Batch mining
            batch_result = pipeline.process_batch(batch_data)
            assert batch_result.total_pathways == 4


# ============================================
# Test: Edge Cases
# ============================================

class TestPipelineEdgeCases:
    def test_empty_raw_events(self):
        """Pipeline handles empty event list gracefully."""
        config = PipelineConfig(
            enable_xes_export=True,
            enable_ltl_verification=True,
            enable_pathway_mining=True,
        )
        pipeline = PostScoringPipeline(config)
        result = pipeline.process_episode(
            episode_id="empty",
            raw_events=[],
            score=_make_score(),
            violations=[],
        )
        assert result.episode_id == "empty"

    def test_empty_batch(self):
        """Batch pipeline handles empty episode list."""
        config = PipelineConfig(enable_pathway_mining=True)
        pipeline = PostScoringPipeline(config)
        result = pipeline.process_batch([])
        assert result.total_pathways == 0

    def test_invalid_ltl_properties_file(self):
        """Invalid properties file path doesn't crash."""
        config = PipelineConfig(
            enable_ltl_verification=True,
            ltl_properties_file="/nonexistent/path.yaml",
        )
        pipeline = PostScoringPipeline(config)
        result = pipeline.process_episode(
            episode_id="bad_path",
            raw_events=[{"activity": "X", "timestamp_ms": 0}],
            score=_make_score(),
            violations=[],
        )
        # Should not crash, returns 0/0
        assert result.ltl_satisfied == 0
        assert result.ltl_violated == 0

    def test_experiment_result_optional_pipeline(self):
        """ExperimentResult works with and without pipeline_result."""
        r1 = ExperimentResult(
            experiment_id="e1",
            scenario_id="s1",
            agent_id="a1",
            run_number=0,
            episode_log=_make_episode_log(),
            score=_make_score(),
            timestamp="2024-01-01",
        )
        assert r1.pipeline_result is None

        r2 = ExperimentResult(
            experiment_id="e2",
            scenario_id="s1",
            agent_id="a1",
            run_number=0,
            episode_log=_make_episode_log(),
            score=_make_score(),
            timestamp="2024-01-01",
            pipeline_result=EpisodePipelineResult(episode_id="e2"),
        )
        assert r2.pipeline_result is not None
