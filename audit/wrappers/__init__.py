"""Alternative evaluator wrappers for audit harness extensibility.

Two families of wrappers live here:

1. **Metric-threshold evaluators** — threshold a continuous metric from
   ``verdict_matrix_v6.json`` into a boolean verdict
   (``metric_evaluators.py``).

2. **External-benchmark evaluators** — bridge arbitrary external
   benchmark scoring styles into the audit harness via
   ``ExternalBenchmarkEvaluator`` and the
   ``@register_external_benchmark`` decorator (``external.py``).

Any concrete ``ExternalBenchmarkEvaluator`` subclass decorated with
``@register_external_benchmark("<name>")`` is automatically registered
as shim ``ext_<name>`` in the audit CLI.
"""

from audit.wrappers.external import (  # noqa: F401
    EXTERNAL_BENCHMARK_REGISTRY,
    ExternalBenchmarkEvaluator,
    register_external_benchmark,
)

# Side-effect imports: populate EXTERNAL_BENCHMARK_REGISTRY via decorators.
from audit.wrappers import external_examples  # noqa: F401
from audit.wrappers import native_adapter_examples  # noqa: F401
from audit.wrappers.metric_evaluators import (
    ActionCoverageEvaluator,
    AlwaysTrueEvaluator,
    C2ScoreEvaluator,
    MABF1Evaluator,
)

__all__ = [
    "ActionCoverageEvaluator",
    "AlwaysTrueEvaluator",
    "C2ScoreEvaluator",
    "EXTERNAL_BENCHMARK_REGISTRY",
    "ExternalBenchmarkEvaluator",
    "MABF1Evaluator",
    "register_external_benchmark",
]

WRAPPER_REGISTRY: dict[str, type] = {
    "action_coverage": ActionCoverageEvaluator,
    "c2_score": C2ScoreEvaluator,
    "mab_f1": MABF1Evaluator,
    "always_true": AlwaysTrueEvaluator,
    **{f"ext_{name}": cls for name, cls in EXTERNAL_BENCHMARK_REGISTRY.items()},
}
