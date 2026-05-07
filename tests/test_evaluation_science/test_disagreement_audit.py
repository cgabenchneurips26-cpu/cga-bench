"""Tests for Experiment C: Disagreement Audit."""
from __future__ import annotations

import pytest

from cga_bench.eval_harness.experiments.disagreement_audit import (
    DisagreementAudit,
    EpisodeClassification,
    FailureMode,
    Quadrant,
    QuadrantResult,
    DEFAULT_CGA_THRESHOLD,
)


@pytest.fixture()
def audit() -> DisagreementAudit:
    return DisagreementAudit(output_dir="/tmp/test_audit")


@pytest.fixture()
def sample_episodes() -> list:
    """Episodes with known quadrant assignments."""
    return [
        # Q1: Task PASS, CGA PASS (compliance > 0.7)
        {
            "scenario_id": "septic_shock_basic",
            "agent_id": "oracle",
            "compliance_score": 0.85,
            "sub_scores": {"C2_mandatory_completion": 1.0},
            "violations_by_type": {},
        },
        # Q2: Task PASS, CGA FAIL (compliance < 0.7)
        {
            "scenario_id": "septic_shock_basic",
            "agent_id": "rag_vllm",
            "compliance_score": 0.3,
            "sub_scores": {"C2_mandatory_completion": 1.0},
            "violations_by_type": {"timing": 2},
        },
        # Q4: Task FAIL, CGA FAIL
        {
            "scenario_id": "dka_moderate_basic",
            "agent_id": "rag_vllm",
            "compliance_score": 0.2,
            "sub_scores": {"C2_mandatory_completion": 0.6},
            "violations_by_type": {"omission": 2, "timing": 1},
        },
    ]


class TestQuadrantClassification:
    """Test 4-quadrant classification logic."""

    def test_q1_both_pass(self, audit: DisagreementAudit) -> None:
        ep = EpisodeClassification(
            episode_id="ep1",
            scenario_id="test",
            agent_id="oracle",
            source="original",
            task_completion_pass=True,
            cga_compliance=0.85,
            cga_pass=False,
            quadrant=Quadrant.Q1_BOTH_PASS,
            failure_mode=None,
            sub_scores={},
            violations_by_type={},
        )
        audit.episodes = [ep]
        result = audit.classify(cga_threshold=0.7)
        assert result.q1_count == 1
        assert result.q2_count == 0

    def test_q2_cga_detects(self, audit: DisagreementAudit) -> None:
        ep = EpisodeClassification(
            episode_id="ep2",
            scenario_id="test",
            agent_id="rag",
            source="original",
            task_completion_pass=True,
            cga_compliance=0.4,
            cga_pass=False,
            quadrant=Quadrant.Q1_BOTH_PASS,
            failure_mode=None,
            sub_scores={},
            violations_by_type={"timing": 2},
        )
        audit.episodes = [ep]
        result = audit.classify(cga_threshold=0.7)
        assert result.q2_count == 1
        assert ep.quadrant == Quadrant.Q2_CGA_DETECTS

    def test_q3_cga_lenient(self, audit: DisagreementAudit) -> None:
        ep = EpisodeClassification(
            episode_id="ep3",
            scenario_id="test",
            agent_id="rag",
            source="original",
            task_completion_pass=False,
            cga_compliance=0.8,
            cga_pass=False,
            quadrant=Quadrant.Q1_BOTH_PASS,
            failure_mode=None,
            sub_scores={},
            violations_by_type={},
        )
        audit.episodes = [ep]
        result = audit.classify(cga_threshold=0.7)
        assert result.q3_count == 1

    def test_q4_both_fail(self, audit: DisagreementAudit) -> None:
        ep = EpisodeClassification(
            episode_id="ep4",
            scenario_id="test",
            agent_id="rag",
            source="original",
            task_completion_pass=False,
            cga_compliance=0.3,
            cga_pass=False,
            quadrant=Quadrant.Q1_BOTH_PASS,
            failure_mode=None,
            sub_scores={},
            violations_by_type={"omission": 1},
        )
        audit.episodes = [ep]
        result = audit.classify(cga_threshold=0.7)
        assert result.q4_count == 1

    def test_threshold_sensitivity_changes_quadrants(
        self, audit: DisagreementAudit
    ) -> None:
        """Changing threshold should shift episodes between quadrants."""
        ep = EpisodeClassification(
            episode_id="ep_edge",
            scenario_id="test",
            agent_id="rag",
            source="original",
            task_completion_pass=True,
            cga_compliance=0.65,  # Between 0.6 and 0.7
            cga_pass=False,
            quadrant=Quadrant.Q1_BOTH_PASS,
            failure_mode=None,
            sub_scores={},
            violations_by_type={"timing": 1},
        )
        audit.episodes = [ep]

        # At 0.6 threshold → CGA PASS → Q1
        result_60 = audit.classify(cga_threshold=0.6)
        assert result_60.q1_count == 1

        # At 0.7 threshold → CGA FAIL → Q2
        result_70 = audit.classify(cga_threshold=0.7)
        assert result_70.q2_count == 1


class TestFailureModeClassification:
    """Test Q2 failure mode detection."""

    def test_timing_mode(self) -> None:
        ep = EpisodeClassification(
            episode_id="test", scenario_id="s", agent_id="a",
            source="original", task_completion_pass=True,
            cga_compliance=0.3, cga_pass=False,
            quadrant=Quadrant.Q2_CGA_DETECTS, failure_mode=None,
            sub_scores={}, violations_by_type={"timing": 2},
        )
        mode = DisagreementAudit._classify_failure_mode(ep)
        assert mode == FailureMode.TIMING

    def test_safety_mode(self) -> None:
        ep = EpisodeClassification(
            episode_id="test", scenario_id="s", agent_id="a",
            source="original", task_completion_pass=True,
            cga_compliance=0.0, cga_pass=False,
            quadrant=Quadrant.Q2_CGA_DETECTS, failure_mode=None,
            sub_scores={}, violations_by_type={"commission": 1},
        )
        mode = DisagreementAudit._classify_failure_mode(ep)
        assert mode == FailureMode.SAFETY

    def test_mixed_mode(self) -> None:
        ep = EpisodeClassification(
            episode_id="test", scenario_id="s", agent_id="a",
            source="original", task_completion_pass=True,
            cga_compliance=0.2, cga_pass=False,
            quadrant=Quadrant.Q2_CGA_DETECTS, failure_mode=None,
            sub_scores={},
            violations_by_type={"timing": 1, "sequence": 1},
        )
        mode = DisagreementAudit._classify_failure_mode(ep)
        assert mode == FailureMode.MIXED


class TestLoadPerturbationResults:
    """Test loading perturbation results into audit."""

    def test_load_skips_baseline(self, audit: DisagreementAudit) -> None:
        results = [
            {"description": "Baseline (no perturbation)", "scenario_id": "test"},
            {
                "description": "Delay vasopressor",
                "scenario_id": "septic_shock_basic",
                "perturbation_type": "P1_delay",
                "task_completion_pass": True,
                "cga_compliance": 0.4,
                "cga_sub_scores": {},
                "violations_by_type": {"timing": 1},
            },
        ]
        count = audit.load_perturbation_results(results)
        assert count == 1
        assert audit.episodes[0].source == "perturbed"
