"""DxEM (Diagnosis Extraction Match) evaluator shim — TOM family.

Terminal-output-only baseline: passes all episodes by construction
(always returns True). Column 'DxEM' in verdict_matrix_v6.json.
"""

from __future__ import annotations

from typing import Any

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims._verdict_cache import get_verdict


class DxEMShim(Evaluator):
    """Frozen cache of DxEM verdicts."""

    meta = EvaluatorMeta(
        name="DxEM",
        family="TOM",
        source="verdict_matrix_v6.json",
    )

    def verdict(self, ep: dict[str, Any]) -> bool:
        return get_verdict(ep["episode_id"], "dxem")

    def observed_features(self) -> frozenset[str]:
        return frozenset({"termination_reason", "final_disposition"})
