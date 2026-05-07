"""Metric-threshold evaluators for audit harness extensibility.

Each evaluator reads a continuous score from verdict_matrix_v6.json and
thresholds it into a binary verdict. This demonstrates that the audit
harness accepts any episode -> bool function, not just the 6 built-in shims.

These evaluators are deliberately simple: they exist to prove the harness
works on arbitrary verdict functions, not to be clinically meaningful.
"""

from __future__ import annotations

from typing import Any

from audit.evaluator_base import Evaluator, EvaluatorMeta
from audit.shims._verdict_cache import load_w8_episodes


class _MetricThresholdEvaluator(Evaluator):
    """Base class: verdict = (metric >= threshold).

    Subclasses set _FIELD and _THRESHOLD class attributes.
    """

    _FIELD: str = ""
    _THRESHOLD: float = 0.5

    def verdict(self, ep: dict[str, Any]) -> bool:
        episodes = load_w8_episodes()
        ep_data = episodes.get(ep["episode_id"])
        if ep_data is None:
            return False
        val = ep_data.get(self._FIELD)
        if val is None:
            return False
        return float(val) >= self._THRESHOLD


class ActionCoverageEvaluator(_MetricThresholdEvaluator):
    """Verdict = action_coverage >= 0.8.

    Action coverage measures the fraction of expected actions performed.
    High threshold (0.8) means the agent completed most expected actions.
    """

    _FIELD = "action_coverage"
    _THRESHOLD = 0.8

    meta = EvaluatorMeta(
        name="ActionCoverage",
        family="ACov-threshold",
        source="verdict_matrix_v6.json:action_coverage",
    )

    def observed_features(self) -> frozenset[str]:
        return frozenset({"action_coverage"})


class C2ScoreEvaluator(_MetricThresholdEvaluator):
    """Verdict = c2_score >= 0.5.

    C2 score captures mandatory action completion compliance.
    """

    _FIELD = "c2_score"
    _THRESHOLD = 0.5

    meta = EvaluatorMeta(
        name="C2Score",
        family="CwT-threshold",
        source="verdict_matrix_v6.json:c2_score",
    )

    def observed_features(self) -> frozenset[str]:
        return frozenset({"c2_score"})


class MABF1Evaluator(_MetricThresholdEvaluator):
    """Verdict = mab_f1 >= 0.5.

    MAB F1 measures the harmonic mean of precision and recall for
    mandatory action completion.
    """

    _FIELD = "mab_f1"
    _THRESHOLD = 0.5

    meta = EvaluatorMeta(
        name="MABF1",
        family="PAF-threshold",
        source="verdict_matrix_v6.json:mab_f1",
    )

    def observed_features(self) -> frozenset[str]:
        return frozenset({"mab_f1"})


class AlwaysTrueEvaluator(Evaluator):
    """Negative control: always returns True (safe/passing).

    Expected audit results:
    - pi-class: "term" (cannot distinguish any separating pairs)
    - BSR: ~0.48 (fraction of v4_hard=True in corpus)
    - rho(d_G): ~0 (no correlation with repair distance)
    - Blindspot grid: all cells red (misses every violation)
    """

    meta = EvaluatorMeta(
        name="AlwaysTrue",
        family="trivial",
        source="negative_control",
    )

    def verdict(self, ep: dict[str, Any]) -> bool:
        return True

    def observed_features(self) -> frozenset[str]:
        return frozenset()
