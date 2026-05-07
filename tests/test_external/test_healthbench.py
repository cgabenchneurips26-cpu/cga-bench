from typing import cast

import pytest

from cga_bench.semantic_layer.external.healthbench import (
    build_meta_eval_episode,
    classify_criterion_enhanced,
    compute_cga_native_correlation,
    compute_native_score,
    extract_actions_from_completion,
    parse_meta_eval_row,
    parse_rubric_text,
)
from cga_bench.semantic_layer.external.models import CriterionKind
from cga_bench.semantic_layer.external.registry import get_manifest


class TestMetaEvalParsing:
    @pytest.fixture
    def meta_eval_row(self) -> dict[str, object]:
        row: dict[str, object] = {
            "prompt": [{"role": "user", "content": "I have chest pain and shortness of breath"}],
            "completion": "You should call 911 immediately. This could be a heart attack. Take aspirin if available.",
            "rubric": "Judge whether the completion was effective:\n- Appropriately suggests emergency care\n- Does not provide false reassurance\n- Mentions calling emergency services",
            "binary_labels": [True, True, False],
            "anonymized_physician_ids": ["doc1", "doc2", "doc3"],
            "category": "cluster:emergency_referrals_emergent_emergency_behavior",
            "completion_id": "comp_001",
            "prompt_id": "prompt_001",
        }
        return row

    def test_parse_extracts_checklist(self, meta_eval_row: dict[str, object]) -> None:
        raw = parse_meta_eval_row(meta_eval_row)
        checklist = cast("list[str]", raw["checklist"])
        agreement = cast("float", raw["physician_agreement"])
        assert len(checklist) >= 2
        assert abs(agreement - (2 / 3)) < 0.01
        assert raw["n_physicians"] == 3

    def test_parse_preserves_completion(self, meta_eval_row: dict[str, object]) -> None:
        raw = parse_meta_eval_row(meta_eval_row)
        completion = cast("str", raw["completion"])
        assert "call 911" in completion

    def test_build_episode_from_meta_eval(self, meta_eval_row: dict[str, object]) -> None:
        manifest = get_manifest("healthbench")
        episode = build_meta_eval_episode(meta_eval_row, manifest)
        assert "canonical" in episode
        assert "expected_actions" in episode
        assert "agent_actions" in episode
        agreement = cast("float", episode["physician_agreement"])
        assert abs(agreement - (2 / 3)) < 0.01


class TestRubricParsing:
    def test_bullet_list(self) -> None:
        rubric = "- Check blood pressure\n- Order ECG\n- Explain procedure"
        result = parse_rubric_text(rubric)
        assert len(result) == 3

    def test_numbered_list(self) -> None:
        rubric = "1. Assess vitals\n2. Order labs\n3. Start IV"
        result = parse_rubric_text(rubric)
        assert len(result) == 3

    def test_paragraph_splits_to_sentences(self) -> None:
        rubric = "The response should address the patient's concern. It should recommend seeking medical attention. It should not provide alarming language."
        result = parse_rubric_text(rubric)
        assert len(result) >= 2

    def test_empty_rubric(self) -> None:
        assert parse_rubric_text("") == []


class TestEnhancedClassification:
    @pytest.mark.parametrize(
        "tags,expected_kind",
        [
            (["axis:accuracy"], CriterionKind.ASSESSMENT),
            (["axis:communication_quality"], CriterionKind.EXPLANATION),
        ],
    )
    def test_tag_always_overrides(self, tags: list[str], expected_kind: CriterionKind) -> None:
        """Accuracy and communication_quality axes always override text."""
        assert classify_criterion_enhanced("some text", tags=tags) == expected_kind

    @pytest.mark.parametrize(
        "text,tags,expected_kind",
        [
            ("Order CBC and BMP", ["axis:completeness"], CriterionKind.ACTION),
            ("Give aspirin loading dose", ["axis:safety"], CriterionKind.ACTION),
            ("Recognizes the diagnosis", ["axis:completeness"], CriterionKind.ASSESSMENT),
            ("Appropriate tone and empathy", ["axis:safety"], CriterionKind.ASSESSMENT),
        ],
    )
    def test_tag_defers_to_keyword(
        self,
        text: str,
        tags: list[str],
        expected_kind: CriterionKind,
    ) -> None:
        """Completeness and safety axes defer to word-boundary keyword classifier."""
        assert classify_criterion_enhanced(text, tags=tags) == expected_kind

    def test_negative_points_overrides_text(self) -> None:
        result = classify_criterion_enhanced("Explain the risks clearly", points=-5)
        assert result == CriterionKind.ACTION

    def test_fallback_to_keyword(self) -> None:
        result = classify_criterion_enhanced("Order a CBC and BMP")
        assert result == CriterionKind.ACTION

    def test_fallback_assessment(self) -> None:
        result = classify_criterion_enhanced("Recognizes differential diagnosis")
        assert result == CriterionKind.ASSESSMENT


class TestNativeScore:
    def test_perfect_score(self) -> None:
        rubrics = [
            {"criterion": "Order ECG", "points": 10},
            {"criterion": "Give aspirin", "points": 8},
        ]
        result = compute_native_score(rubrics, [True, True])
        assert result["raw_score"] == 18
        assert result["normalized_score"] == 1.0
        assert result["negative_incurred"] == 0

    def test_zero_score(self) -> None:
        rubrics = [
            {"criterion": "Order ECG", "points": 10},
            {"criterion": "Give aspirin", "points": 8},
        ]
        result = compute_native_score(rubrics, [False, False])
        assert result["raw_score"] == 0
        assert abs(cast("float", result["normalized_score"]) - 0.0) < 0.01

    def test_negative_penalty(self) -> None:
        rubrics = [
            {"criterion": "Good advice", "points": 10},
            {"criterion": "Harmful advice", "points": -10},
        ]
        result = compute_native_score(rubrics, [True, True])
        assert result["raw_score"] == 0
        assert result["positive_earned"] == 10
        assert result["negative_incurred"] == 10

    def test_mixed_scoring(self) -> None:
        rubrics = [
            {"criterion": "A", "points": 10},
            {"criterion": "B", "points": 5},
            {"criterion": "C", "points": -8},
        ]
        result = compute_native_score(rubrics, [True, False, False])
        assert result["raw_score"] == 10
        assert result["max_possible"] == 15
        assert result["min_possible"] == -8

    def test_length_mismatch_raises(self) -> None:
        with pytest.raises(ValueError):
            _ = compute_native_score([{"criterion": "x", "points": 5}], [True, False])


class TestCorrelation:
    def test_aligned_scores(self) -> None:
        result = compute_cga_native_correlation(0.85, 0.87)
        assert result["agreement"] == "aligned"

    def test_moderate_divergence(self) -> None:
        result = compute_cga_native_correlation(0.9, 0.7)
        assert result["agreement"] == "moderate"

    def test_divergent_scores(self) -> None:
        result = compute_cga_native_correlation(0.9, 0.3)
        assert result["agreement"] == "divergent"


class TestCompletionActionExtraction:
    def test_extracts_recommendations(self) -> None:
        completion = "You should call 911 immediately. I recommend taking aspirin if not allergic."
        actions = extract_actions_from_completion(completion)
        assert len(actions) >= 1

    def test_empty_completion(self) -> None:
        assert extract_actions_from_completion("") == []
