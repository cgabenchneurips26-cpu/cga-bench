"""Tests for PostScoringPipeline and related config/result types."""
from __future__ import annotations

import pytest
from unittest.mock import MagicMock, patch

from cga_bench.eval_harness.pipeline import (
    BatchPipelineResult,
    EpisodePipelineResult,
    PipelineConfig,
    PostScoringPipeline,
)
from cga_bench.cpg_model.schemas.base import CGAScore


# ============================================================================
# PipelineConfig Defaults
# ============================================================================

class TestPipelineConfig:
    def test_all_disabled_by_default(self):
        cfg = PipelineConfig()
        assert cfg.enable_xes_export is False
        assert cfg.enable_ltl_verification is False
        assert cfg.enable_llm_judge is False
        assert cfg.enable_pathway_mining is False

    def test_xes_defaults(self):
        cfg = PipelineConfig()
        assert cfg.xes_output_dir is None
        assert cfg.xes_enable_outcome is True
        assert cfg.xes_enable_violation_overlay is True

    def test_llm_judge_defaults(self):
        cfg = PipelineConfig()
        assert cfg.llm_judge_backend == "mock"
        assert cfg.llm_judge_model == "gpt-4"
        assert cfg.llm_judge_api_key is None

    def test_mining_defaults(self):
        cfg = PipelineConfig()
        assert cfg.mining_ged_threshold == 3.0
        assert cfg.mining_min_cluster_size == 2

    def test_custom_values(self):
        cfg = PipelineConfig(
            enable_xes_export=True,
            xes_output_dir="/tmp/xes",
            enable_ltl_verification=True,
            ontology_domain="sepsis",
        )
        assert cfg.enable_xes_export is True
        assert cfg.xes_output_dir == "/tmp/xes"
        assert cfg.ontology_domain == "sepsis"


# ============================================================================
# Result Dataclasses
# ============================================================================

class TestEpisodePipelineResult:
    def test_default_values(self):
        r = EpisodePipelineResult(episode_id="ep_001")
        assert r.episode_id == "ep_001"
        assert r.xes_path is None
        assert r.ltl_satisfied is None
        assert r.ltl_violated is None
        assert r.ltl_violations == []
        assert r.llm_judge_applied is False
        assert r.severity_changes == 0

    def test_populated_values(self):
        r = EpisodePipelineResult(
            episode_id="ep_002",
            xes_path="/tmp/ep_002.xes",
            ltl_satisfied=5,
            ltl_violated=1,
            ltl_violations=["blood_culture_before_abx"],
            llm_judge_applied=True,
            severity_changes=2,
        )
        assert r.ltl_satisfied == 5
        assert len(r.ltl_violations) == 1


class TestBatchPipelineResult:
    def test_default_values(self):
        r = BatchPipelineResult()
        assert r.total_pathways == 0
        assert r.num_clusters == 0
        assert r.high_performing == []
        assert r.low_performing == []
        assert r.significant_correlations == []


# ============================================================================
# PostScoringPipeline — All Disabled
# ============================================================================

class TestPipelineAllDisabled:
    def test_init_no_components(self):
        cfg = PipelineConfig()
        pipeline = PostScoringPipeline(cfg)
        assert pipeline._xes_exporter is None
        assert pipeline._ltl_verifier is None
        assert pipeline._llm_judge is None
        assert pipeline._miner is None

    def test_process_episode_noop(self):
        cfg = PipelineConfig()
        pipeline = PostScoringPipeline(cfg)
        score = CGAScore(
            episode_id="ep_test",
            compliance_score=0.9,
            peak_risk=0.1,
            aggregate_risk=0.2,
            total_violations=1,
            sub_scores={},
            violations_by_type={},
            violation_events=[],
            justified_deviations=0,
            budget_usage={},
        )
        result = pipeline.process_episode(
            episode_id="ep_test",
            raw_events=[],
            score=score,
            violations=[],
        )
        assert isinstance(result, EpisodePipelineResult)
        assert result.episode_id == "ep_test"
        assert result.xes_path is None
        assert result.ltl_satisfied is None
        assert result.llm_judge_applied is False

    def test_process_batch_noop(self):
        cfg = PipelineConfig()
        pipeline = PostScoringPipeline(cfg)
        result = pipeline.process_batch(episode_data=[])
        assert isinstance(result, BatchPipelineResult)
        assert result.total_pathways == 0


# ============================================================================
# PostScoringPipeline — XES Enabled
# ============================================================================

class TestPipelineXES:
    def test_xes_init_attempt(self, tmp_path):
        cfg = PipelineConfig(
            enable_xes_export=True,
            xes_output_dir=str(tmp_path / "xes_out"),
        )
        pipeline = PostScoringPipeline(cfg)
        # XES exporter may or may not init depending on dependencies
        # But pipeline should not crash
        assert pipeline is not None


# ============================================================================
# PostScoringPipeline — LTL Enabled
# ============================================================================

class TestPipelineLTL:
    def test_ltl_init_no_properties(self):
        cfg = PipelineConfig(enable_ltl_verification=True)
        pipeline = PostScoringPipeline(cfg)
        # Should not crash even without properties file
        assert pipeline is not None

    def test_ltl_with_ontology_domain(self):
        cfg = PipelineConfig(
            enable_ltl_verification=True,
            ontology_domain="sepsis",
        )
        pipeline = PostScoringPipeline(cfg)
        assert pipeline is not None


# ============================================================================
# PostScoringPipeline — Pathway Mining Disabled
# ============================================================================

class TestPipelineMining:
    def test_mining_disabled_batch_noop(self):
        cfg = PipelineConfig(enable_pathway_mining=False)
        pipeline = PostScoringPipeline(cfg)
        result = pipeline.process_batch([
            {"episode_id": "ep1", "raw_events": [], "score": None},
        ])
        assert result.total_pathways == 0
