"""Tests for projection functions and Bayes-error wrapper."""

from scripts.audit._projections import PROJECTIONS, pi_aset, pi_nctx, pi_nord, pi_term


class TestProjectionFunctions:
    """Verify projection functions return correct types."""

    def _make_ep(self, actions=None, termination_reason="completed"):
        return {
            "termination_reason": termination_reason,
            "actions": actions or [],
        }

    def test_pi_term_returns_string(self):
        ep = self._make_ep(termination_reason="timeout")
        assert pi_term(ep) == "timeout"

    def test_pi_term_missing_returns_unknown(self):
        assert pi_term({}) == "unknown"

    def test_pi_aset_returns_sorted_tuple(self):
        actions = [
            {"action_id": "give_aspirin"},
            {"action_id": "order_ecg"},
            {"action_id": "give_aspirin"},  # duplicate
        ]
        result = pi_aset(self._make_ep(actions=actions))
        assert result == ("give_aspirin", "order_ecg")
        assert isinstance(result, tuple)

    def test_pi_nord_preserves_order(self):
        actions = [
            {"action_id": "order_ecg"},
            {"action_id": "give_aspirin"},
            {"action_id": "order_ecg"},
        ]
        result = pi_nord(self._make_ep(actions=actions))
        assert result == ("order_ecg", "give_aspirin", "order_ecg")

    def test_pi_nctx_bins_timestamps(self):
        actions = [
            {"action_id": "give_aspirin", "timestamp_minutes": 3.0},
            {"action_id": "order_ecg", "timestamp_minutes": 7.5},
        ]
        result = pi_nctx(self._make_ep(actions=actions))
        assert result == (("give_aspirin", 0), ("order_ecg", 5))

    def test_pi_nctx_handles_bad_timestamp(self):
        actions = [{"action_id": "give_aspirin", "timestamp_minutes": "invalid"}]
        result = pi_nctx(self._make_ep(actions=actions))
        assert result == (("give_aspirin", 0),)

    def test_projections_dict_has_four_entries(self):
        assert set(PROJECTIONS.keys()) == {"term", "aset", "nord", "nctx"}

    def test_empty_actions(self):
        ep = self._make_ep(actions=[])
        assert pi_aset(ep) == ()
        assert pi_nord(ep) == ()
        assert pi_nctx(ep) == ()

    def test_action_id_normalization(self):
        actions = [{"action_id": "Give-Aspirin Loading"}]
        result = pi_aset(self._make_ep(actions=actions))
        assert result == ("give_aspirin_loading",)
