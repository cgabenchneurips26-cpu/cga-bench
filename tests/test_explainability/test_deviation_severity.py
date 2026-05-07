"""
Tests for DeviationSeverityClassifier: stopword-filtered Jaccard similarity
and episode_scope isolation.
"""

import pytest
from cga_bench.eval_harness.explainability.deviation_severity import (
    DeviationSeverityClassifier,
    STOPWORDS,
)


class TestJaccardStopwordFix:
    """Verify stopword removal produces correct similarity behaviour."""

    def setup_method(self):
        self.clf = DeviationSeverityClassifier()

    def test_give_medication_heparin_vs_nacl_is_zero(self):
        """After removing stopwords 'give' and 'medication', only substance tokens
        remain: {'heparin'} vs {'nacl'} → no overlap → 0.0 similarity."""
        score = self.clf._jaccard_similarity(
            "give_medication_heparin", "give_medication_nacl"
        )
        assert score == 0.0, f"Expected 0.0, got {score}"

    def test_order_lab_troponin_vs_creatinine_is_zero(self):
        """After removing 'order' and 'lab', {'troponin'} vs {'creatinine'} → 0.0."""
        score = self.clf._jaccard_similarity(
            "order_lab_troponin", "order_lab_creatinine"
        )
        assert score == 0.0, f"Expected 0.0, got {score}"

    def test_urine_electrolytes_vs_urinalysis_partial_match(self):
        """'order_lab_urine_electrolytes' vs 'order_lab_urinalysis':
        after stopword removal: {'urine','electrolytes'} vs {'urinalysis'}
        → intersection=0, union=3 → 0.0 (no exact token match).
        Jaccard > 0 requires shared tokens; 'urine' != 'urinalysis'."""
        score = self.clf._jaccard_similarity(
            "order_lab_urine_electrolytes", "order_lab_urinalysis"
        )
        # No exact shared tokens after stopword removal
        assert score == 0.0, f"Expected 0.0 (no exact token overlap), got {score}"

    def test_classify_high_severity_for_unrelated_medication(self):
        """give_medication_heparin vs allowed={give_medication_nacl} → HIGH severity."""
        with self.clf.episode_scope():
            label, weight = self.clf.classify(
                "give_medication_heparin",
                cpg_allowed={"give_medication_nacl"},
                cpg_forbidden=set(),
            )
        assert label == "HIGH", f"Expected HIGH, got {label}"

    def test_classify_high_severity_for_unrelated_lab(self):
        """order_lab_troponin vs allowed={order_lab_creatinine} → HIGH severity."""
        with self.clf.episode_scope():
            label, weight = self.clf.classify(
                "order_lab_troponin",
                cpg_allowed={"order_lab_creatinine"},
                cpg_forbidden=set(),
            )
        assert label == "HIGH", f"Expected HIGH, got {label}"


class TestEpisodeScopeIsolation:
    """Verify that two episodes processed sequentially are independent."""

    def setup_method(self):
        self.clf = DeviationSeverityClassifier()

    def test_episodes_are_independent(self):
        """Same action repeated across two episodes should be HIGH in both,
        not INFORMATIONAL in the second (which would happen if seen-state leaked)."""
        allowed = {"give_normal_saline"}
        forbidden = set()

        # Episode 1
        with self.clf.episode_scope():
            label1, _ = self.clf.classify("give_heparin", allowed, forbidden)

        # Episode 2 — fresh scope, give_heparin not yet seen
        with self.clf.episode_scope():
            label2, _ = self.clf.classify("give_heparin", allowed, forbidden)

        assert label1 == label2, (
            f"Episodes not independent: episode1={label1}, episode2={label2}"
        )
        assert label1 != "INFORMATIONAL", (
            "First occurrence in any episode must not be INFORMATIONAL"
        )
        assert label2 != "INFORMATIONAL", (
            "First occurrence in second episode must not be INFORMATIONAL (state leaked)"
        )

    def test_repeat_within_episode_is_informational(self):
        """Same action twice within one episode → second is INFORMATIONAL."""
        allowed = set()
        forbidden = set()

        with self.clf.episode_scope():
            label_first, _ = self.clf.classify("give_heparin", allowed, forbidden)
            label_repeat, _ = self.clf.classify("give_heparin", allowed, forbidden)

        assert label_repeat == "INFORMATIONAL", (
            f"Repeat within episode should be INFORMATIONAL, got {label_repeat}"
        )

    def test_compute_weighted_deviation_score_independent(self):
        """compute_weighted_deviation_score uses episode_scope internally;
        two calls with the same inputs must return the same score."""
        deviations = ["give_heparin", "order_troponin", "give_heparin"]
        allowed = set()
        forbidden = set()

        score1 = self.clf.compute_weighted_deviation_score(deviations, allowed, forbidden)
        score2 = self.clf.compute_weighted_deviation_score(deviations, allowed, forbidden)

        assert score1 == score2, (
            f"Repeated calls returned different scores: {score1} vs {score2}"
        )

    def test_scope_in_scope_flag(self):
        """_in_scope is True inside episode_scope and False outside."""
        assert self.clf._in_scope is False
        with self.clf.episode_scope():
            assert self.clf._in_scope is True
        assert self.clf._in_scope is False
