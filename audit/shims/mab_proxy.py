"""MAB-Proxy (Mandatory Action Bundle F1) evaluator shim — PAF family.

MAB F1 >= 0.5 threshold. Column 'MAB-Proxy' in verdict_matrix_v6.json.
"""

from __future__ import annotations

from typing import Any

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims._verdict_cache import get_verdict


class MABProxyShim(Evaluator):
    """Frozen cache of MAB-Proxy verdicts."""

    meta = EvaluatorMeta(
        name="MAB-Proxy",
        family="PAF",
        source="verdict_matrix_v6.json",
    )

    def verdict(self, ep: dict[str, Any]) -> bool:
        return get_verdict(ep["episode_id"], "mab_proxy")

    def observed_features(self) -> frozenset[str]:
        return frozenset({"actions"})
