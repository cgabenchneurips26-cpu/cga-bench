"""Bridge an external benchmark's native scoring function to the audit harness.

`ExternalBenchmarkEvaluator` (see external.py) expects the subclass to
implement `score_trajectory(trajectory) -> float`. When the external
benchmark already ships a scoring function (e.g. MedAgentBench's
`evaluate_medagentbench_task`, HealthBench's `compute_native_score`), a
thin bridge that converts a CGA-Bench trajectory into the external
function's expected input, runs the native scorer, and normalizes the
return to a [0, 1] float is often all that is needed.

`NativeAdapterEvaluator` is that base. Subclasses override:

  - ``_build_adapter_input(trajectory) -> Any`` — shape a CGA-Bench
    trajectory into whatever the native scorer expects (a dict, a
    NormalizedEpisode, etc.). Only read pi_nord-admissible fields to
    remain isolation-safe.
  - ``_score_from_adapter(adapter_input) -> float`` — call the native
    scorer and return a [0, 1] float (or adjust ``pass_threshold``).

The default ``score_trajectory`` wraps these two with exception
handling so a broken bridge yields verdict=False rather than crashing
the audit run.

Important: bridges MUST NOT import modules that violate scorer-agent
isolation (e.g. `cpg_engine`, `assessor_core`). If the native scorer
depends on such modules, the bridge cannot be used and a style-emulator
(see external_examples.py) is the correct path instead.
"""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, ClassVar

from audit.wrappers.external import ExternalBenchmarkEvaluator


class NativeAdapterEvaluator(ExternalBenchmarkEvaluator):
    """Base class for bridges that invoke an external benchmark's native scorer."""

    # Subclasses may override if a single shared adapter instance is useful.
    adapter_cls: ClassVar[type | None] = None

    def __init__(self) -> None:
        if self.adapter_cls is not None:
            self._adapter = self.adapter_cls()
        else:
            self._adapter = None

    @abstractmethod
    def _build_adapter_input(self, trajectory: dict[str, Any]) -> Any:
        """Shape a CGA-Bench trajectory into the native scorer's input format."""
        raise NotImplementedError

    @abstractmethod
    def _score_from_adapter(self, adapter_input: Any) -> float:
        """Run the native scorer and return a [0, 1] float."""
        raise NotImplementedError

    def score_trajectory(self, trajectory: dict[str, Any]) -> float:
        try:
            adapter_input = self._build_adapter_input(trajectory)
            score = self._score_from_adapter(adapter_input)
            return float(score)
        except Exception:
            return 0.0
