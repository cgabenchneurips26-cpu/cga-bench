from __future__ import annotations

# pyright: reportMissingImports=false, reportUnknownVariableType=false, reportUnknownParameterType=false, reportUnknownMemberType=false, reportUnknownArgumentType=false

import math

import pytest

from cga_bench.semantic_layer.external.healthbench_quality import (
    AccuracyScoreResult,
    EmpathyScaleResult,
    EmpathyScoreResult,
    JudgeEndpoint,
    ModelTier,
    MultiJudgeConfig,
    RAGConfig,
    QualityAssessment,
    QualityScoreConfig,
    SentimentResult,
    TieringConfig,
    aggregate_quality_scores,
    compute_accuracy_score,
    compute_empathy_score,
    compute_empathy_scale,
    compute_sentiment,
    compute_quality_assessment,
    estimate_complexity,
    evaluate_with_multi_judge,
    retrieve_context,
    select_model_tier,
)


@pytest.fixture
def default_config() -> QualityScoreConfig:
    return QualityScoreConfig.default()


@pytest.fixture
def empathetic_text() -> str:
    return (
        "I'm really sorry to hear about your symptoms. I understand this must be very "
        "worrying for you. Let me explain what we can do to help."
    )


@pytest.fixture
def clinical_text() -> str:
    return "Take ibuprofen 400mg every 6 hours. Follow up in 2 weeks. Order CBC and CMP."


@pytest.fixture
def sample_rubrics() -> list[dict[str, object]]:
    return [
        {"criterion": "Recommends seeing a doctor", "points": 10},
        {"criterion": "Mentions medication", "points": 5},
        {"criterion": "Provides false reassurance", "points": -8},
    ]


class TestQualityScoreConfig:
    def test_default_factory_returns_config(self) -> None:
        config = QualityScoreConfig.default()
        assert isinstance(config, QualityScoreConfig)

    def test_default_weights_and_min_length(self) -> None:
        config = QualityScoreConfig.default()
        assert math.isclose(config.empathy_weight, 0.4)
        assert math.isclose(config.accuracy_weight, 0.6)
        assert config.min_text_length == 10

    def test_default_has_keyword_lists(self) -> None:
        config = QualityScoreConfig.default()
        assert isinstance(config.empathy_keywords, list)
        assert isinstance(config.non_empathy_keywords, list)

    def test_llm_fields_are_optional(self) -> None:
        config = QualityScoreConfig.default()
        assert config.llm_endpoint is None
        assert config.llm_model is None


class TestComputeEmpathyScore:
    def test_highly_empathetic_text_scores_high(self, default_config: QualityScoreConfig) -> None:
        text = (
            "I'm so sorry you're going through this. I understand how frightening "
            "these symptoms must be. Let me help you."
        )
        result: EmpathyScoreResult = compute_empathy_score(text, default_config)
        assert result["empathy_score"] > 0.6

    def test_cold_clinical_text_scores_low(self, default_config: QualityScoreConfig) -> None:
        text = "Take medication X. Follow up in 2 weeks."
        result: EmpathyScoreResult = compute_empathy_score(text, default_config)
        assert result["empathy_score"] < 0.3

    def test_mixed_text_scores_mid_range(self, default_config: QualityScoreConfig) -> None:
        text = "I understand your concern. Take ibuprofen 400mg."
        result: EmpathyScoreResult = compute_empathy_score(text, default_config)
        assert 0.3 <= result["empathy_score"] <= 0.7

    def test_empty_text_returns_zero(self, default_config: QualityScoreConfig) -> None:
        result: EmpathyScoreResult = compute_empathy_score("", default_config)
        assert result["empathy_score"] == 0.0
        assert result["text_length"] == 0

    def test_short_text_below_min_length_returns_zero(self, default_config: QualityScoreConfig) -> None:
        result: EmpathyScoreResult = compute_empathy_score("Thanks", default_config)
        assert result["empathy_score"] == 0.0
        assert result["text_length"] < default_config.min_text_length

    def test_method_is_keyword_without_llm_endpoint(self, default_config: QualityScoreConfig) -> None:
        result: EmpathyScoreResult = compute_empathy_score("I understand your concern.", default_config)
        assert result["method"] == "keyword"

    def test_empathy_result_contract_fields(self, default_config: QualityScoreConfig) -> None:
        result: EmpathyScoreResult = compute_empathy_score("I understand this is stressful.", default_config)
        assert set(result.keys()) == {
            "empathy_score",
            "keyword_hits",
            "negative_hits",
            "text_length",
            "method",
            "sentiment",
        }


class TestComputeAccuracyScore:
    def test_all_satisfied_returns_full_accuracy(
        self,
        default_config: QualityScoreConfig,
        sample_rubrics: list[dict[str, object]],
    ) -> None:
        result: AccuracyScoreResult = compute_accuracy_score(sample_rubrics, [True, True, True], default_config)
        assert result["accuracy_score"] == 1.0
        assert result["criteria_satisfied"] == 3
        assert result["criteria_total"] == 3

    def test_none_satisfied_returns_zero_accuracy(
        self,
        default_config: QualityScoreConfig,
        sample_rubrics: list[dict[str, object]],
    ) -> None:
        result: AccuracyScoreResult = compute_accuracy_score(sample_rubrics, [False, False, False], default_config)
        assert result["accuracy_score"] == 0.0
        assert result["criteria_satisfied"] == 0

    def test_half_satisfied_is_about_half(self, default_config: QualityScoreConfig) -> None:
        rubrics = [
            {"criterion": "A", "points": 3},
            {"criterion": "B", "points": 3},
            {"criterion": "C", "points": 3},
            {"criterion": "D", "points": 3},
        ]
        result: AccuracyScoreResult = compute_accuracy_score(rubrics, [True, False, True, False], default_config)
        assert result["criteria_satisfied"] == 2
        assert result["criteria_total"] == 4
        assert abs(result["accuracy_score"] - 0.5) < 0.01

    def test_weighted_score_respects_points(self, default_config: QualityScoreConfig) -> None:
        rubrics = [
            {"criterion": "High value", "points": 10},
            {"criterion": "Low value", "points": 2},
        ]
        result: AccuracyScoreResult = compute_accuracy_score(rubrics, [True, False], default_config)
        assert result["weighted_score"] > 0.5

    def test_empty_rubrics_returns_zero(self, default_config: QualityScoreConfig) -> None:
        result: AccuracyScoreResult = compute_accuracy_score([], [], default_config)
        assert result["accuracy_score"] == 0.0
        assert result["criteria_total"] == 0

    def test_length_mismatch_raises_value_error(self, default_config: QualityScoreConfig) -> None:
        rubrics = [{"criterion": "A", "points": 1}]
        with pytest.raises(ValueError):
            _ = compute_accuracy_score(rubrics, [True, False], default_config)

    def test_accuracy_result_contract_fields(
        self,
        default_config: QualityScoreConfig,
        sample_rubrics: list[dict[str, object]],
    ) -> None:
        result: AccuracyScoreResult = compute_accuracy_score(sample_rubrics, [True, False, False], default_config)
        assert set(result.keys()) == {
            "accuracy_score",
            "criteria_satisfied",
            "criteria_total",
            "weighted_score",
            "method",
        }


class TestLLMAccuracyScoring:
    def test_accuracy_method_is_rubric_without_llm(
        self,
        default_config: QualityScoreConfig,
        sample_rubrics: list[dict[str, object]],
    ) -> None:
        result: AccuracyScoreResult = compute_accuracy_score(sample_rubrics, [True, True, False], default_config)
        assert result["method"] == "rubric"

    def test_accuracy_result_has_method_field(
        self,
        default_config: QualityScoreConfig,
        sample_rubrics: list[dict[str, object]],
    ) -> None:
        result: AccuracyScoreResult = compute_accuracy_score(sample_rubrics, [True, False, False], default_config)
        assert "method" in result

    def test_accuracy_uses_hybrid_blend_when_llm_available(
        self,
        default_config: QualityScoreConfig,
        sample_rubrics: list[dict[str, object]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        default_config.llm_endpoint = "http://localhost:1234"
        default_config.llm_model = "test-model"

        def _fake_llm_score(
            text: str,
            rubrics: object,
            endpoint: str,
            model: str,
        ) -> float | None:
            _ = text, rubrics, endpoint, model
            return 0.5

        monkeypatch.setattr(
            "cga_bench.semantic_layer.external.healthbench_quality._llm_accuracy_score",
            _fake_llm_score,
        )

        result: AccuracyScoreResult = compute_accuracy_score(
            sample_rubrics,
            [True, False, False],
            default_config,
            text="Clinical response text",
        )

        rubric_weighted = 10.0 / 15.0
        expected = 0.6 * rubric_weighted + 0.4 * 0.5
        assert abs(result["weighted_score"] - expected) < 1e-9
        assert result["method"] == "hybrid"

    def test_accuracy_falls_back_to_rubric_when_llm_fails(
        self,
        default_config: QualityScoreConfig,
        sample_rubrics: list[dict[str, object]],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        default_config.llm_endpoint = "http://localhost:1234"
        default_config.llm_model = "test-model"

        def _fake_llm_score_fail(
            text: str,
            rubrics: object,
            endpoint: str,
            model: str,
        ) -> float | None:
            _ = text, rubrics, endpoint, model
            return None

        monkeypatch.setattr(
            "cga_bench.semantic_layer.external.healthbench_quality._llm_accuracy_score",
            _fake_llm_score_fail,
        )

        result: AccuracyScoreResult = compute_accuracy_score(
            sample_rubrics,
            [True, False, False],
            default_config,
            text="Clinical response text",
        )
        assert result["method"] == "rubric"


class TestSentimentAnalysis:
    def test_positive_text_has_positive_polarity(self) -> None:
        result: SentimentResult = compute_sentiment("Things are looking good, you should recover well.")
        assert result["polarity"] > 0

    def test_negative_text_has_negative_polarity(self) -> None:
        result: SentimentResult = compute_sentiment("This is a severe emergency with critical danger.")
        assert result["polarity"] < 0

    def test_neutral_text_has_near_zero_polarity(self) -> None:
        result: SentimentResult = compute_sentiment("The appointment is scheduled for Tuesday.")
        assert abs(result["polarity"]) < 0.3

    def test_empty_text_returns_zero(self) -> None:
        result: SentimentResult = compute_sentiment("")
        assert result["polarity"] == 0.0
        assert result["intensity"] == 0.0


class TestEmpathyScale:
    def test_empathy_scale_returns_correct_structure(
        self,
        default_config: QualityScoreConfig,
        empathetic_text: str,
    ) -> None:
        result: EmpathyScaleResult = compute_empathy_scale(empathetic_text, default_config)
        assert "scale_score" in result
        assert "normalized" in result
        assert "dimensions" in result
        assert 1.0 <= result["scale_score"] <= 10.0
        assert 0.0 <= result["normalized"] <= 1.0

    def test_empathetic_text_scores_higher(
        self,
        default_config: QualityScoreConfig,
        empathetic_text: str,
        clinical_text: str,
    ) -> None:
        emp_result: EmpathyScaleResult = compute_empathy_scale(empathetic_text, default_config)
        clin_result: EmpathyScaleResult = compute_empathy_scale(clinical_text, default_config)
        assert emp_result["scale_score"] > clin_result["scale_score"]

    def test_dimensions_are_heart_dimensions(
        self,
        default_config: QualityScoreConfig,
        empathetic_text: str,
    ) -> None:
        result: EmpathyScaleResult = compute_empathy_scale(empathetic_text, default_config)
        expected = {"hearing", "empathizing", "appreciating", "recommending", "transitioning"}
        assert set(result["dimensions"].keys()) == expected


class TestAggregateQualityScores:
    def test_average_of_multiple_scores(self) -> None:
        result = aggregate_quality_scores([0.2, 0.6, 1.0])
        assert abs(result - 0.6) < 0.01

    def test_single_score_returns_same_value(self) -> None:
        assert aggregate_quality_scores([0.75]) == 0.75

    def test_empty_scores_returns_zero(self) -> None:
        assert aggregate_quality_scores([]) == 0.0


class TestComputeQualityAssessment:
    def test_combines_empathy_and_accuracy(
        self,
        default_config: QualityScoreConfig,
        empathetic_text: str,
        sample_rubrics: list[dict[str, object]],
    ) -> None:
        assessment: QualityAssessment = compute_quality_assessment(
            empathetic_text,
            sample_rubrics,
            [True, True, False],
            default_config,
        )
        assert "empathy" in assessment
        assert "accuracy" in assessment
        assert "composite_quality" in assessment

    def test_composite_uses_weighted_formula(
        self,
        default_config: QualityScoreConfig,
        clinical_text: str,
        sample_rubrics: list[dict[str, object]],
    ) -> None:
        assessment: QualityAssessment = compute_quality_assessment(
            clinical_text,
            sample_rubrics,
            [True, False, False],
            default_config,
        )
        expected = (
            default_config.empathy_weight * assessment["empathy"]["empathy_score"]
            + default_config.accuracy_weight * assessment["accuracy"]["weighted_score"]
        )
        assert abs(assessment["composite_quality"] - expected) < 1e-9


class TestMultiJudgeAggregation:
    def test_default_config_has_no_judges(self) -> None:
        config = MultiJudgeConfig.default()
        assert config.judges == []

    def test_evaluate_no_judges_returns_zero(self) -> None:
        config = MultiJudgeConfig.default()
        result = evaluate_with_multi_judge("test", [], lambda t: t, config)
        assert result["final_score"] == 0.0
        assert result["n_judges"] == 0

    def test_result_has_correct_structure(self) -> None:
        config = MultiJudgeConfig.default()
        result = evaluate_with_multi_judge("test", [], lambda t: t, config)
        assert set(result.keys()) == {"final_score", "individual_scores", "agreement_ratio", "method", "n_judges"}

    def test_agreement_ratio_bounds(self) -> None:
        config = MultiJudgeConfig.default()
        result = evaluate_with_multi_judge("test", [], lambda t: t, config)
        assert 0.0 <= result["agreement_ratio"] <= 1.0

    def test_weighted_mean_uses_weights(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sequence = iter([0.2, 0.8])

        def _fake_call(prompt: str, endpoint: str, model: str) -> float | None:
            _ = prompt, endpoint, model
            return next(sequence)

        monkeypatch.setattr(
            "cga_bench.semantic_layer.external.healthbench_quality._call_multi_judge_score",
            _fake_call,
        )

        config = MultiJudgeConfig(judges=[], aggregation_method="weighted_mean", min_agreement=0.0)
        judges: list[JudgeEndpoint] = [
            {"endpoint": "http://a", "model": "m1", "weight": 1.0},
            {"endpoint": "http://b", "model": "m2", "weight": 3.0},
        ]
        result = evaluate_with_multi_judge("text", judges, lambda t: t, config)
        assert abs(result["final_score"] - 0.65) < 1e-9
        assert result["method"] == "weighted_mean"

    def test_majority_rounds_to_tenths(
        self,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sequence = iter([0.31, 0.34, 0.81])

        def _fake_call(prompt: str, endpoint: str, model: str) -> float | None:
            _ = prompt, endpoint, model
            return next(sequence)

        monkeypatch.setattr(
            "cga_bench.semantic_layer.external.healthbench_quality._call_multi_judge_score",
            _fake_call,
        )

        config = MultiJudgeConfig(judges=[], aggregation_method="majority", min_agreement=0.0)
        judges: list[JudgeEndpoint] = [
            {"endpoint": "http://a", "model": "m1", "weight": 1.0},
            {"endpoint": "http://b", "model": "m2", "weight": 1.0},
            {"endpoint": "http://c", "model": "m3", "weight": 1.0},
        ]
        result = evaluate_with_multi_judge("text", judges, lambda t: t, config)
        assert abs(result["final_score"] - 0.3) < 1e-9
        assert result["method"] == "majority"


class TestRAGContext:
    def test_default_config_has_no_path(self) -> None:
        config = RAGConfig.default()
        assert config.knowledge_base_path is None

    def test_retrieve_without_path_returns_empty(self) -> None:
        config = RAGConfig.default()
        result = retrieve_context("test query", config)
        assert result["chunks"] == []
        assert result["retrieval_score"] == 0.0

    def test_result_structure(self) -> None:
        config = RAGConfig.default()
        result = retrieve_context("test", config)
        assert set(result.keys()) == {"chunks", "source_files", "retrieval_score"}

    def test_retrieve_from_kb_returns_ranked_chunks(self, tmp_path_factory: pytest.TempPathFactory) -> None:
        kb_dir = tmp_path_factory.mktemp("kb")
        _ = (kb_dir / "a.md").write_text(
            "sepsis bundle includes blood culture and antibiotics",
            encoding="utf-8",
        )
        _ = (kb_dir / "b.txt").write_text(
            "headache workup includes CT and lumbar puncture",
            encoding="utf-8",
        )

        config = RAGConfig(
            knowledge_base_path=str(kb_dir),
            max_context_chunks=2,
            chunk_similarity_threshold=0.2,
        )
        result = retrieve_context("sepsis antibiotics", config)
        assert len(result["chunks"]) >= 1
        assert len(result["source_files"]) >= 1
        assert result["retrieval_score"] > 0.0


class TestModelTiering:
    def test_default_config_has_no_tiers(self) -> None:
        config = TieringConfig.default()
        assert config.slm_tier is None
        assert config.llm_tier is None

    def test_complexity_short_text_low(self) -> None:
        assert estimate_complexity("Hello.") < 0.3

    def test_complexity_long_text_higher(self) -> None:
        long_text = (
            "The patient presents with multiple comorbidities including diabetes mellitus "
            "type 2, hypertension, and chronic kidney disease stage 3. "
        ) * 5
        assert estimate_complexity(long_text) > estimate_complexity("Hello.")

    def test_select_returns_none_without_tiers(self) -> None:
        config = TieringConfig.default()
        assert select_model_tier("test", "empathy", config) is None

    def test_always_llm_tasks_override_complexity(self) -> None:
        llm_tier: ModelTier = {"tier": "llm", "endpoint": "http://x", "model": "big", "cost_weight": 10.0}
        config = TieringConfig(
            slm_tier=None,
            llm_tier=llm_tier,
            complexity_threshold=0.9,
            always_use_llm_for=["empathy_scale"],
        )
        result = select_model_tier("short", "empathy_scale", config)
        assert result is not None
        assert result["tier"] == "llm"

    def test_select_slm_for_low_complexity(self) -> None:
        slm_tier: ModelTier = {"tier": "slm", "endpoint": "http://s", "model": "small", "cost_weight": 1.0}
        llm_tier: ModelTier = {"tier": "llm", "endpoint": "http://l", "model": "large", "cost_weight": 10.0}
        config = TieringConfig(
            slm_tier=slm_tier,
            llm_tier=llm_tier,
            complexity_threshold=0.8,
            always_use_llm_for=[],
        )
        selected = select_model_tier("hello", "accuracy", config)
        assert selected is not None
        assert selected["tier"] == "slm"
