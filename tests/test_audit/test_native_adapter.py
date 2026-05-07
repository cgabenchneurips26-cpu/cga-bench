"""Tests for NativeAdapterEvaluator bridge and the MedAgentBench native example."""

from __future__ import annotations

from audit.evaluator_base import Evaluator
from audit.shims import SHIM_REGISTRY
from audit.wrappers.native_adapter import NativeAdapterEvaluator
import pytest


class _ToyBridge(NativeAdapterEvaluator):
    benchmark_name = "Toy"
    pass_threshold = 0.5
    pi_family_hypothesis = "aset"

    def _build_adapter_input(self, trajectory: dict) -> dict:
        return {"taken": len(trajectory.get("actions") or [])}

    def _score_from_adapter(self, adapter_input: dict) -> float:
        return 1.0 if adapter_input["taken"] >= 3 else 0.0


class TestNativeAdapterEvaluator:
    def test_is_evaluator(self) -> None:
        assert isinstance(_ToyBridge(), Evaluator)

    def test_meta_autopopulated(self) -> None:
        ev = _ToyBridge()
        assert ev.meta.name == "Toy"
        assert ev.meta.family == "external:aset"

    def test_verdict_pass_when_score_meets_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        traj = {"actions": [{"action_id": str(i)} for i in range(5)]}
        monkeypatch.setattr("audit.wrappers.external.load_trajectory", lambda eid: traj)
        assert _ToyBridge().verdict({"episode_id": "x"}) is True

    def test_verdict_fail_when_score_below_threshold(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        traj = {"actions": [{"action_id": "a"}]}
        monkeypatch.setattr("audit.wrappers.external.load_trajectory", lambda eid: traj)
        assert _ToyBridge().verdict({"episode_id": "x"}) is False

    def test_verdict_fail_on_exception_in_scorer(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        class Broken(NativeAdapterEvaluator):
            benchmark_name = "Broken"
            pi_family_hypothesis = "aset"

            def _build_adapter_input(self, trajectory: dict) -> dict:
                return {}

            def _score_from_adapter(self, adapter_input: dict) -> float:
                raise RuntimeError("native scorer unavailable")

        monkeypatch.setattr("audit.wrappers.external.load_trajectory", lambda eid: {})
        assert Broken().verdict({"episode_id": "x"}) is False


class TestMedAgentBenchNativeBridge:
    def test_registered(self) -> None:
        assert "ext_medagent_native" in SHIM_REGISTRY

    def test_instantiates(self) -> None:
        cls = SHIM_REGISTRY["ext_medagent_native"]
        ev = cls()
        assert ev.meta.name == "MedAgentBench-native"

    def test_builds_task_dict(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from audit.wrappers.native_adapter_examples import MedAgentBenchNativeBridge

        ev = MedAgentBenchNativeBridge()
        traj = {
            "scenario_id": "abc_scenario",
            "actions": [{"action_id": "give_abx"}],
            "expected_actions": ["give_abx", "order_cbc"],
            "forbidden_actions": ["delay"],
        }
        task = ev._build_adapter_input(traj)
        assert task["case_id"] == "abc_scenario"
        assert "give_abx" in task["instruction"]
        assert task["observed"]["actions"] == ["give_abx"]
        assert task["observed"]["observed_source"] == "cga_bench_trajectory"

    def test_score_exception_returns_zero(self) -> None:
        """If the native scorer raises, score_trajectory catches and returns 0."""
        from audit.wrappers.native_adapter_examples import MedAgentBenchNativeBridge

        ev = MedAgentBenchNativeBridge()

        # Replace instance method with one that raises.
        def raising_score(*args, **kwargs):
            raise ValueError("simulated native scorer failure")

        ev._score_from_adapter = raising_score  # type: ignore[assignment]
        score = ev.score_trajectory(
            {"scenario_id": "x", "actions": [], "expected_actions": [], "forbidden_actions": []}
        )
        assert score == 0.0
