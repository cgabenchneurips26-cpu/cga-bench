"""AC-Proxy (Action Coverage) evaluator shim — ASC family.

Action coverage >= 0.5 threshold. Column 'AC-Proxy' in verdict_matrix_v6.json.
"""

from __future__ import annotations

from typing import Any

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims._verdict_cache import get_verdict


class ACProxyShim(Evaluator):
    """Frozen cache of AC-Proxy verdicts."""

    meta = EvaluatorMeta(
        name="AC-Proxy",
        family="ASC",
        source="verdict_matrix_v6.json",
    )

    def verdict(self, ep: dict[str, Any]) -> bool:
        return get_verdict(ep["episode_id"], "ac_proxy")

    def observed_features(self) -> frozenset[str]:
        return frozenset({"actions"})
