"""V4-Hard (CGA-Bench TCC) evaluator shim — TCC family.

Full trace conformance checker. Ground-truth reference evaluator.
Column 'CGA-Bench' in verdict_matrix_v6.json.
"""

from __future__ import annotations

from typing import Any

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims._verdict_cache import get_verdict


class V4HardShim(Evaluator):
    """Frozen cache of CGA-Bench (v4_hard) verdicts."""

    meta = EvaluatorMeta(
        name="CGA-Bench",
        family="TCC",
        source="verdict_matrix_v6.json",
    )

    def verdict(self, ep: dict[str, Any]) -> bool:
        return get_verdict(ep["episode_id"], "v4_hard")

    def observed_features(self) -> frozenset[str]:
        return frozenset({"actions", "timestamps", "patient_state", "ordering"})
