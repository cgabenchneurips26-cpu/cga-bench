"""Tests for the ExternalBenchmarkEvaluator bridge (Option C1)."""

from __future__ import annotations

from audit.evaluator_base import Evaluator
from audit.shims import SHIM_REGISTRY
from audit.wrappers.external import (
    EXTERNAL_BENCHMARK_REGISTRY,
    ExternalBenchmarkEvaluator,
    register_external_benchmark,
)
import pytest


class TestRegistry:
    def test_builtin_examples_registered(self) -> None:
        assert "medagent_style" in EXTERNAL_BENCHMARK_REGISTRY
        assert "healthbench_style" in EXTERNAL_BENCHMARK_REGISTRY

    def test_builtin_examples_exposed_as_ext_shims(self) -> None:
        assert "ext_medagent_style" in SHIM_REGISTRY
        assert "ext_healthbench_style" in SHIM_REGISTRY

    def test_duplicate_registration_raises(self) -> None:
        @register_external_benchmark("test_dup_once")
        class Once(ExternalBenchmarkEvaluator):
            benchmark_name = "DupOnce"

            def score_trajectory(self, trajectory: dict) -> float:
                return 1.0

        with pytest.raises(KeyError):

            @register_external_benchmark("test_dup_once")
            class Again(ExternalBenchmarkEvaluator):
                benchmark_name = "DupAgain"

                def score_trajectory(self, trajectory: dict) -> float:
                    return 0.0

        # Clean up so the test is idempotent if the suite is re-run in the
        # same interpreter (EXTERNAL_BENCHMARK_REGISTRY is a module-level dict).
        EXTERNAL_BENCHMARK_REGISTRY.pop("test_dup_once", None)


class _FakeExternal(ExternalBenchmarkEvaluator):
    benchmark_name = "FakeExt"
    pass_threshold = 0.5
    pi_family_hypothesis = "aset"

    def score_trajectory(self, trajectory: dict) -> float:
        return 0.7 if trajectory.get("pass") else 0.2


class TestVerdictLogic:
    def test_subclass_is_evaluator(self) -> None:
        assert isinstance(_FakeExternal(), Evaluator)

    def test_meta_autopopulated(self) -> None:
        ev = _FakeExternal()
        assert ev.meta.name == "FakeExt"
        assert ev.meta.family == "external:aset"

    def test_verdict_pass_when_score_geq_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "audit.wrappers.external.load_trajectory", lambda eid: {"pass": True}
        )
        assert _FakeExternal().verdict({"episode_id": "x"}) is True

    def test_verdict_fail_when_score_below_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr(
            "audit.wrappers.external.load_trajectory", lambda eid: {"pass": False}
        )
        assert _FakeExternal().verdict({"episode_id": "x"}) is False

    def test_verdict_false_when_trajectory_missing(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        monkeypatch.setattr("audit.wrappers.external.load_trajectory", lambda eid: None)
        assert _FakeExternal().verdict({"episode_id": "x"}) is False

    def test_verdict_false_on_scorer_exception(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Broken(ExternalBenchmarkEvaluator):
            benchmark_name = "Broken"

            def score_trajectory(self, trajectory: dict) -> float:
                raise RuntimeError("boom")

        monkeypatch.setattr("audit.wrappers.external.load_trajectory", lambda eid: {})
        assert Broken().verdict({"episode_id": "x"}) is False

    def test_observed_features_exclude_tcc_fields(self) -> None:
        """External wrappers must not claim to read TCC-derived fields."""
        feats = _FakeExternal().observed_features()
        forbidden = {"n_viols", "viol_types", "compliance_score", "sub_scores", "violation_events"}
        assert feats.isdisjoint(forbidden)


class TestBuiltinExamples:
    def test_medagent_style_pass_when_all_expected_taken(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from audit.wrappers.external_examples import MedAgentBenchStyleEvaluator

        traj = {
            "actions": [{"action_id": "a"}, {"action_id": "b"}],
            "expected_actions": ["a", "b"],
            "forbidden_actions": [],
        }
        monkeypatch.setattr("audit.wrappers.external.load_trajectory", lambda eid: traj)
        assert MedAgentBenchStyleEvaluator().verdict({"episode_id": "x"}) is True

    def test_medagent_style_fail_when_coverage_below_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from audit.wrappers.external_examples import MedAgentBenchStyleEvaluator

        traj = {
            "actions": [{"action_id": "a"}],
            "expected_actions": ["a", "b", "c", "d", "e"],  # 20% coverage
            "forbidden_actions": [],
        }
        monkeypatch.setattr("audit.wrappers.external.load_trajectory", lambda eid: traj)
        assert MedAgentBenchStyleEvaluator().verdict({"episode_id": "x"}) is False

    def test_healthbench_style_penalizes_forbidden(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from audit.wrappers.external_examples import HealthBenchRubricStyleEvaluator

        traj = {
            "actions": [{"action_id": "a"}, {"action_id": "bad"}],
            "expected_actions": ["a"],
            "forbidden_actions": ["bad"],
        }
        monkeypatch.setattr("audit.wrappers.external.load_trajectory", lambda eid: traj)
        # hits=1, penalties=1, possible=1 -> raw=0 -> fail
        assert HealthBenchRubricStyleEvaluator().verdict({"episode_id": "x"}) is False
