"""
Deviation Severity Classifier: Severity-weighted deviation scoring for CGA-Bench.

Classifies action deviations by severity using Jaccard similarity against
the CPG allowed action set and forbidden action list.
"""

from contextlib import contextmanager
from typing import Optional
import re
import logging

logger = logging.getLogger(__name__)

STOPWORDS = {
    "give", "order", "start", "stop", "check", "assess", "monitor",
    "evaluate", "perform", "obtain", "measure", "review", "calculate",
    "medication", "med", "drug", "lab", "test", "imaging",
    "patient", "result", "results", "basic", "standard",
}


class DeviationSeverityClassifier:
    """Classify deviation severity using ActionNormalizer fuzzy match + CPG context."""

    # Weights are expert-initialized based on clinical harm gradient:
    # CRITICAL = direct patient harm (e.g., contraindicated drug)
    # HIGH = unrelated action in acute setting
    # MODERATE = partially related but off-protocol
    # LOW = clinically related but non-standard (e.g., extra lab test)
    # INFORMATIONAL = repeated/benign (e.g., duplicate order)
    # Frozen before evaluation; not tuned to maximize any model's scores.
    # Sensitivity analysis: see evidence_pack/analysis/difficulty_calibration.json
    SEVERITY_WEIGHTS = {
        "CRITICAL": 1.0,
        "HIGH": 0.7,
        "MODERATE": 0.4,
        "LOW": 0.15,
        "INFORMATIONAL": 0.05,
    }

    def __init__(self):
        from cga_bench.assessor_core.action_normalizer import ActionNormalizer
        self.normalizer = ActionNormalizer()
        self._seen_actions: set = set()
        self._in_scope: bool = False

    def _jaccard_similarity(self, a: str, b: str) -> float:
        """Compute Jaccard similarity between two action IDs using token overlap.

        Tokenizes on underscores, removes stopwords, then computes Jaccard.
        Returns 0.0 if both token sets are empty after stopword removal.
        """
        def tokenize(s: str) -> set:
            tokens = set(s.lower().split("_"))
            filtered = tokens - STOPWORDS
            return filtered

        tokens_a = tokenize(a)
        tokens_b = tokenize(b)

        if not tokens_a and not tokens_b:
            return 0.0

        intersection = len(tokens_a & tokens_b)
        union = len(tokens_a | tokens_b)
        if union == 0:
            return 0.0
        return intersection / union

    def _best_match_score(self, action_id: str, candidate_set: set) -> float:
        """Return the best Jaccard similarity score against a set of action IDs."""
        if not candidate_set:
            return 0.0
        return max(self._jaccard_similarity(action_id, c) for c in candidate_set)

    @contextmanager
    def episode_scope(self):
        """Context manager that resets per-episode state for a clean scoring pass.

        Sets _seen_actions to an empty set and marks _in_scope=True for the
        duration of the block, then restores _in_scope=False on exit.
        """
        self._seen_actions = set()
        self._in_scope = True
        try:
            yield self
        finally:
            self._in_scope = False

    def classify(self, action_id: str, cpg_allowed: set, cpg_forbidden: set) -> tuple:
        """
        Classify a deviation action and return (severity_label, weight).

        Priority order:
        1. If action_id is in cpg_forbidden -> CRITICAL
        2. If action_id is a repeat of an already-seen action -> INFORMATIONAL
        3. Fuzzy match against cpg_allowed:
           - score > 0.7  -> LOW (related deviation)
           - score > 0.4  -> MODERATE (partially related)
           - score <= 0.4 -> HIGH (unrelated)
        """
        if not self._in_scope:
            logger.warning(
                "classify() called outside episode_scope(); seen-action state may be stale. "
                "Use episode_scope() context manager for reliable per-episode scoring."
            )

        # 1. Forbidden check
        if action_id in cpg_forbidden:
            return ("CRITICAL", self.SEVERITY_WEIGHTS["CRITICAL"])

        # 2. Repeat check
        if action_id in self._seen_actions:
            return ("INFORMATIONAL", self.SEVERITY_WEIGHTS["INFORMATIONAL"])
        self._seen_actions.add(action_id)

        # 3. Fuzzy match against allowed set
        score = self._best_match_score(action_id, cpg_allowed)
        if score > 0.7:
            label = "LOW"
        elif score > 0.4:
            label = "MODERATE"
        else:
            label = "HIGH"

        return (label, self.SEVERITY_WEIGHTS[label])

    def reset(self):
        """Clear seen-actions state between episodes."""
        self._seen_actions = set()

    def compute_weighted_deviation_score(
        self,
        deviations: list,
        cpg_allowed: set,
        cpg_forbidden: set,
    ) -> float:
        """
        Sum of severity weights for all deviation action IDs.

        Args:
            deviations: list of action_id strings that are deviations
            cpg_allowed: set of CPG-allowed action IDs
            cpg_forbidden: set of CPG-forbidden action IDs

        Returns:
            Total weighted deviation score (float).
        """
        with self.episode_scope():
            total = 0.0
            for action_id in deviations:
                _, weight = self.classify(action_id, cpg_allowed, cpg_forbidden)
                total += weight
        return total
