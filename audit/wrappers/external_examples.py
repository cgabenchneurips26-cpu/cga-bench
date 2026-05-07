"""Two concrete external-benchmark-style evaluators.

These demonstrate the `@register_external_benchmark` extension path
end-to-end. Both run against the CGA-Bench v6 W8 corpus and appear in
the audit CLI as ``ext_medagent_style`` and ``ext_healthbench_style``.

They are *scoring-style emulators*, not true adapters — they replicate
how the respective external benchmarks assign a scalar score to a
sequential medical trace, so the audit harness can classify the style
by pi-class. Accuracy vs the benchmark's own dataset is out of scope
here; the point is the extension pattern works.
"""

from __future__ import annotations

from typing import Any

from audit.wrappers.external import (
    ExternalBenchmarkEvaluator,
    register_external_benchmark,
)


@register_external_benchmark("medagent_style")
class MedAgentBenchStyleEvaluator(ExternalBenchmarkEvaluator):
    """Emulates MedAgentBench's FHIR-action exact-match scoring style.

    MedAgentBench grades agents by counting expected action completions
    (precision+recall against an oracle action list). We approximate on
    CGA-Bench traces as:
        score = |taken ∩ expected| / |expected|  (1.0 when expected is empty)
    with no order or timing sensitivity — the scoring family is closest
    to pi_aset.
    """

    benchmark_name = "MedAgentBench-style"
    pass_threshold = 0.8
    pi_family_hypothesis = "aset"
    source_url = "https://arxiv.org/abs/2501.14654"

    def score_trajectory(self, trajectory: dict[str, Any]) -> float:
        taken = {a.get("action_id") for a in (trajectory.get("actions") or []) if a.get("action_id")}
        expected = set(trajectory.get("expected_actions") or [])
        if not expected:
            return 1.0
        return len(taken & expected) / len(expected)


@register_external_benchmark("healthbench_style")
class HealthBenchRubricStyleEvaluator(ExternalBenchmarkEvaluator):
    """Emulates HealthBench's rubric-point scoring style.

    HealthBench scores a completion by summing points earned against a
    rubric. We approximate on CGA-Bench traces as:
        score = expected-action hits - forbidden-action penalties
    normalized to [0, 1]. Ordering and timing are ignored.
    """

    benchmark_name = "HealthBench-rubric-style"
    pass_threshold = 0.6
    pi_family_hypothesis = "aset"
    source_url = "https://openai.com/index/healthbench/"

    def score_trajectory(self, trajectory: dict[str, Any]) -> float:
        taken = {a.get("action_id") for a in (trajectory.get("actions") or []) if a.get("action_id")}
        expected = set(trajectory.get("expected_actions") or [])
        forbidden = set(trajectory.get("forbidden_actions") or [])
        if not expected and not forbidden:
            return 1.0
        hits = len(taken & expected)
        penalties = len(taken & forbidden)
        possible = max(1, len(expected))
        raw = (hits - penalties) / possible
        return max(0.0, min(1.0, raw))
