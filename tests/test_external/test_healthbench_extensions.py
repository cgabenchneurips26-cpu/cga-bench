import pytest

from cga_bench.semantic_layer.external.healthbench import (
    _CATEGORY_TO_ACTION_TYPE,
    compute_rubric_grounded_track_a,
    normalize_extracted_actions,
    semantic_action_match,
)


class TestRubricGroundedTrackA:
    def test_all_mandatory_satisfied(self):
        rubrics = [{"points": 10}, {"points": 8}, {"points": 5}]
        result = compute_rubric_grounded_track_a(rubrics, [True, True, True])
        assert result["track_a_score"] == 1.0
        assert result["mandatory_coverage"] == 1.0

    def test_none_satisfied(self):
        rubrics = [{"points": 10}, {"points": 8}]
        result = compute_rubric_grounded_track_a(rubrics, [False, False])
        assert result["track_a_score"] == 0.0
        assert result["mandatory_coverage"] == 0.0

    def test_forbidden_avoided(self):
        rubrics = [{"points": 10}, {"points": -10}]
        result = compute_rubric_grounded_track_a(rubrics, [True, False])
        assert result["track_a_score"] == 1.0
        assert result["forbidden_avoidance"] == 1.0

    def test_forbidden_triggered(self):
        rubrics = [{"points": 10}, {"points": -10}]
        result = compute_rubric_grounded_track_a(rubrics, [True, True])
        assert result["track_a_score"] < 1.0
        assert result["forbidden_avoidance"] == 0.0

    def test_mixed_scoring(self):
        rubrics = [
            {"points": 10},
            {"points": 8},
            {"points": 5},
            {"points": -10},
            {"points": -6},
        ]
        result = compute_rubric_grounded_track_a(rubrics, [True, True, False, False, True])
        assert 0.0 < result["track_a_score"] < 1.0
        assert result["mandatory_satisfied"] == 2
        assert result["mandatory_total"] == 3
        assert result["forbidden_avoided"] == 1
        assert result["forbidden_total"] == 2

    def test_length_mismatch_raises(self):
        with pytest.raises(ValueError):
            compute_rubric_grounded_track_a([{"points": 5}], [True, False])


class TestSemanticActionMatch:
    def test_exact_match(self):
        result = semantic_action_match(["order_lab_cbc"], ["order_lab_cbc"])
        assert result["match_score"] == 1.0
        assert result["n_matched"] == 1

    def test_fuzzy_match(self):
        result = semantic_action_match(
            ["order_lab_cbc", "give_aspirin"],
            ["order_cbc_lab", "give_aspirin_loading"],
            threshold=0.3,
        )
        assert result["n_matched"] >= 1

    def test_no_match(self):
        result = semantic_action_match(
            ["order_lab_cbc"],
            ["completely_different_action"],
            threshold=0.5,
        )
        assert result["match_score"] == 0.0

    def test_empty_lists(self):
        result = semantic_action_match([], [])
        assert result["match_score"] == 0.0

    def test_partial_match(self):
        result = semantic_action_match(
            ["order_ecg", "give_aspirin", "consult_cardiology"],
            ["order_ecg", "unknown_action"],
        )
        assert 0.0 < result["match_score"] < 1.0
        assert len(result["unmatched_expected"]) >= 1


class TestNormalizeExtractedActions:
    def test_basic_normalization(self):
        extracted = [
            {"action": "see_a_doctor", "category": "referral"},
            {"action": "take_aspirin", "category": "medication"},
        ]
        result = normalize_extracted_actions(extracted)
        assert len(result) == 2
        assert any("consult" in a for a in result)
        assert any("give_medication" in a for a in result)

    def test_unknown_category(self):
        extracted = [{"action": "some_action", "category": "weird"}]
        result = normalize_extracted_actions(extracted)
        assert len(result) == 1
        assert result[0].startswith("action_")

    def test_empty_input(self):
        assert normalize_extracted_actions([]) == []


def test_category_mapping_is_exposed():
    assert _CATEGORY_TO_ACTION_TYPE["referral"] == "consult"
