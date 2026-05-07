"""ACov (Action Coverage >= 0.5) evaluator shim — ACov family.

Same threshold as AC-Proxy but tracked separately. Column 'ACov' in verdict_matrix_v6.json.
"""

from __future__ import annotations

from typing import Any

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims._verdict_cache import get_verdict


class ACovShim(Evaluator):
    """Frozen cache of ACov verdicts."""

    meta = EvaluatorMeta(
        name="ACov",
        family="ACov",
        source="verdict_matrix_v6.json",
    )

    def verdict(self, ep: dict[str, Any]) -> bool:
        return get_verdict(ep["episode_id"], "acov")

    def observed_features(self) -> frozenset[str]:
        return frozenset({"actions"})
