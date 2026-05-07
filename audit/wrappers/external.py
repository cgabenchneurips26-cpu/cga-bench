"""Bridge external benchmarks into the audit harness as Evaluators.

The audit harness accepts any `Evaluator` that maps a CGA-Bench episode
to a boolean verdict. External benchmarks (MedAgentBench, AMEGA,
HealthBench, MedChain, AgentClinic, …) score their own datasets with
their own rubric. To bring such a scorer into our audit we either:

  (a) feed each CGA-Bench trajectory through the external adapter's
      scoring logic and threshold the score into a bool (this module);
  (b) re-implement the external benchmark's *scoring style* as a
      minimal evaluator (see metric_evaluators.py for examples).

`ExternalBenchmarkEvaluator` is the (a) bridge. Subclasses override
`score_trajectory(trajectory: dict) -> float` with the external
benchmark's native scoring logic (or a faithful approximation thereof)
applied to a CGA-Bench trajectory. `verdict()` thresholds the score.

Register new subclasses with `@register_external_benchmark("name")` and
they become accessible to the audit CLI via the `ext_<name>` shim key —
no further plumbing required.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Callable, ClassVar

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims._trajectory_cache import load_trajectory

EXTERNAL_BENCHMARK_REGISTRY: dict[str, type["ExternalBenchmarkEvaluator"]] = {}


def register_external_benchmark(
    name: str,
) -> Callable[[type["ExternalBenchmarkEvaluator"]], type["ExternalBenchmarkEvaluator"]]:
    """Decorator that adds a subclass to EXTERNAL_BENCHMARK_REGISTRY.

    The registered name must be unique; attempting to re-register raises
    ``KeyError``. The registered class becomes accessible as shim
    ``ext_<name>`` after ``audit.shims.__init__`` is re-imported.
    """

    def _register(cls: type["ExternalBenchmarkEvaluator"]) -> type["ExternalBenchmarkEvaluator"]:
        if name in EXTERNAL_BENCHMARK_REGISTRY:
            raise KeyError(f"External benchmark {name!r} already registered")
        EXTERNAL_BENCHMARK_REGISTRY[name] = cls
        return cls

    return _register


class ExternalBenchmarkEvaluator(Evaluator):
    """Base class for external benchmark scorers applied to CGA-Bench trajectories.

    Subclass contract:
      - Set ``benchmark_name: str`` (class attribute, appears in EvaluatorMeta.name).
      - Set ``pass_threshold: float`` (default 0.5). Verdict is ``score >= pass_threshold``.
      - Set ``pi_family_hypothesis: str`` (optional, documents the expected
        pi-class the benchmark factors through — verified by audit step 1).
      - Override ``score_trajectory(trajectory: dict) -> float``.

    The default ``verdict`` loads the trajectory via the shared trajectory
    cache (same source as PiNordShim) and threshold-tests the score.
    Trajectories with no file are treated as verdict=False (conservative).
    """

    benchmark_name: ClassVar[str] = "UnnamedExternal"
    pass_threshold: ClassVar[float] = 0.5
    pi_family_hypothesis: ClassVar[str] = "unknown"
    source_url: ClassVar[str | None] = None

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        # Auto-populate meta from class attributes so subclasses only need
        # to set benchmark_name / pass_threshold.
        cls.meta = EvaluatorMeta(
            name=cls.benchmark_name,
            family=f"external:{cls.pi_family_hypothesis}",
            source=cls.source_url,
        )

    @abstractmethod
    def score_trajectory(self, trajectory: dict[str, Any]) -> float:
        """Return the external benchmark's native score for the trajectory.

        Must be deterministic and side-effect free. Range should be [0, 1]
        unless the subclass overrides ``pass_threshold`` accordingly.
        """
        raise NotImplementedError

    def verdict(self, ep: dict[str, Any]) -> bool:
        traj = load_trajectory(ep["episode_id"])
        if traj is None:
            return False
        try:
            score = float(self.score_trajectory(traj))
        except Exception:
            return False
        return score >= self.pass_threshold

    def observed_features(self) -> frozenset[str]:
        return frozenset(
            {
                "actions[*].action_id",
                "expected_actions",
                "forbidden_actions",
                "scenario_id",
            }
        )
