"""C2 (Mandatory Completion >= 0.7) evaluator shim — CwT family.

Mandatory action completion sub-score >= 0.7. Column 'C2' in verdict_matrix_v6.json.
"""

from __future__ import annotations

from typing import Any

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims._verdict_cache import get_verdict


class C2Shim(Evaluator):
    """Frozen cache of C2 verdicts."""

    meta = EvaluatorMeta(
        name="C2",
        family="CwT",
        source="verdict_matrix_v6.json",
    )

    def verdict(self, ep: dict[str, Any]) -> bool:
        return get_verdict(ep["episode_id"], "c2")

    def observed_features(self) -> frozenset[str]:
        return frozenset({"actions", "timestamps"})
