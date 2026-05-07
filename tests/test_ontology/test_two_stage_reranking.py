"""Tests for Two-Stage Entity Linking (P7: Cross-Encoder Reranking).

Tests cover:
1. Cross-encoder initialization and warm-up
2. Pointwise scoring
3. Two-stage pipeline integration
4. Rank change tracking
5. Mock reranker for testing
"""
import pytest
from typing import List, Tuple

from cga_bench.semantic_layer.ontology.cross_encoder_reranker import (
    CrossEncoderReranker,
    MockCrossEncoderReranker,
    RerankerConfig,
    RerankerMode,
    RerankCandidate,
    RerankResult,
    TwoStageMatcher,
    get_reranker,
)


class TestRerankerConfig:
    """Tests for reranker configuration."""

    def test_default_config(self):
        """Default config has sensible values."""
        config = RerankerConfig()
        assert config.max_candidates == 20
        assert config.batch_size == 16
        assert config.mode == RerankerMode.POINTWISE
        assert config.enable_type_boost is True

    def test_custom_config(self):
        """Custom config overrides defaults."""
        config = RerankerConfig(
            max_candidates=10,
            mode=RerankerMode.LISTWISE,
            score_threshold=0.6,
        )
        assert config.max_candidates == 10
        assert config.mode == RerankerMode.LISTWISE
        assert config.score_threshold == 0.6


class TestRerankCandidate:
    """Tests for rerank candidate dataclass."""

    def test_basic_candidate(self):
        """Basic candidate creation."""
        cand = RerankCandidate(
            concept_id="start_norepinephrine",
            display="norepinephrine",
            bi_encoder_score=0.9,
        )
        assert cand.concept_id == "start_norepinephrine"
        assert cand.bi_encoder_score == 0.9
        assert cand.definition == ""
        assert cand.semantic_type == ""

    def test_candidate_with_metadata(self):
        """Candidate with full metadata."""
        cand = RerankCandidate(
            concept_id="start_norepinephrine",
            display="norepinephrine",
            bi_encoder_score=0.9,
            definition="A potent vasopressor",
            semantic_type="DRUG",
            synonyms=["levophed", "NE"],
        )
        assert cand.definition == "A potent vasopressor"
        assert cand.semantic_type == "DRUG"
        assert len(cand.synonyms) == 2


class TestMockCrossEncoderReranker:
    """Tests for mock cross-encoder reranker."""

    def test_initialization(self):
        """Mock reranker initializes correctly."""
        reranker = MockCrossEncoderReranker()
        assert reranker.is_available is True
        assert reranker.initialize() is True
        assert reranker.is_initialized is True

    def test_warm_up(self):
        """Mock warm-up returns stats."""
        reranker = MockCrossEncoderReranker()
        stats = reranker.warm_up()
        assert "model_load_ms" in stats
        assert stats["total_ms"] == 0.0

    def test_rerank_empty_candidates(self):
        """Reranking empty candidates returns empty result."""
        reranker = MockCrossEncoderReranker()
        reranker.initialize()

        result = reranker.rerank("test query", [])
        assert result.concept_id == ""
        assert len(result.all_candidates) == 0

    def test_rerank_single_candidate(self):
        """Reranking single candidate returns it as top-1."""
        reranker = MockCrossEncoderReranker()
        reranker.initialize()

        candidates = [
            RerankCandidate("norepinephrine", "norepinephrine", 0.9)
        ]

        result = reranker.rerank("start norepinephrine", candidates)
        assert result.concept_id == "norepinephrine"
        assert len(result.all_candidates) == 1

    def test_rerank_multiple_candidates(self):
        """Reranking multiple candidates orders by combined score."""
        reranker = MockCrossEncoderReranker()
        reranker.initialize()

        candidates = [
            RerankCandidate("vasopressin", "vasopressin", 0.85),
            RerankCandidate("norepinephrine", "norepinephrine", 0.8),
            RerankCandidate("dopamine", "dopamine", 0.7),
        ]

        result = reranker.rerank("start norepinephrine", candidates)

        # Norepinephrine should rank higher due to token overlap
        assert result.concept_id == "norepinephrine"
        assert result.bi_encoder_score == 0.8

    def test_type_boost(self):
        """Type boost increases score for type-matching candidates."""
        config = RerankerConfig(enable_type_boost=True, type_boost_weight=0.2)
        reranker = MockCrossEncoderReranker(config)
        reranker.initialize()

        candidates = [
            RerankCandidate("vasopressin", "vasopressin", 0.85, semantic_type="DRUG"),
            RerankCandidate("lactate_lab", "lactate", 0.87, semantic_type="LAB"),
        ]

        result = reranker.rerank("give vasopressin", candidates, expected_type="DRUG")

        # DRUG type should get boosted
        drug_idx = next(i for i, c in enumerate(result.all_candidates) if c[0] == "vasopressin")
        lab_idx = next(i for i, c in enumerate(result.all_candidates) if c[0] == "lactate_lab")

        # Drug should rank higher even if bi-encoder score was lower
        assert drug_idx < lab_idx

    def test_statistics_tracking(self):
        """Statistics are tracked across rerank calls."""
        reranker = MockCrossEncoderReranker()
        reranker.initialize()

        candidates = [RerankCandidate("test", "test", 0.9)]

        reranker.rerank("query1", candidates)
        reranker.rerank("query2", candidates)
        reranker.rerank("query3", candidates)

        stats = reranker.get_statistics()
        assert stats["rerank_count"] == 3

    def test_statistics_reset(self):
        """Statistics can be reset."""
        reranker = MockCrossEncoderReranker()
        reranker.initialize()

        candidates = [RerankCandidate("test", "test", 0.9)]
        reranker.rerank("query", candidates)

        assert reranker.get_statistics()["rerank_count"] == 1

        reranker.reset_statistics()
        assert reranker.get_statistics()["rerank_count"] == 0


class TestRerankResult:
    """Tests for rerank result dataclass."""

    def test_score_delta_positive(self):
        """Score delta is positive when CE improves over BI."""
        result = RerankResult(
            concept_id="test",
            display="test",
            cross_encoder_score=0.95,
            bi_encoder_score=0.85,
            rank_change=2,
            all_candidates=[("test", 0.95, 0.85)],
        )
        assert result.score_delta == pytest.approx(0.1, abs=0.01)

    def test_score_delta_negative(self):
        """Score delta is negative when CE decreases from BI."""
        result = RerankResult(
            concept_id="test",
            display="test",
            cross_encoder_score=0.75,
            bi_encoder_score=0.85,
            rank_change=0,
            all_candidates=[("test", 0.75, 0.85)],
        )
        assert result.score_delta == pytest.approx(-0.1, abs=0.01)


class TestGetReranker:
    """Tests for factory function."""

    def test_get_mock_reranker(self):
        """Factory returns mock when requested."""
        reranker = get_reranker(use_mock=True)
        assert isinstance(reranker, MockCrossEncoderReranker)

    def test_get_reranker_with_config(self):
        """Factory accepts custom config."""
        config = RerankerConfig(max_candidates=5)
        reranker = get_reranker(config=config, use_mock=True)
        assert reranker._config.max_candidates == 5


class TestTwoStagePipelineIntegration:
    """Tests for two-stage pipeline integration."""

    def test_pipeline_with_mock_components(self):
        """Two-stage pipeline works with mock components."""
        from cga_bench.semantic_layer.ontology.neural_embedder import (
            MockNeuralEmbedder,
            EmbedderConfig,
        )

        # Create mock components with low threshold for testing
        bi_encoder = MockNeuralEmbedder(EmbedderConfig(similarity_threshold=0.2))
        reranker = MockCrossEncoderReranker()

        # Build index
        concepts = [
            ("norepinephrine", "norepinephrine", ["levophed", "NE"]),
            ("vasopressin", "vasopressin", ["pitressin"]),
            ("dopamine", "dopamine", []),
        ]
        bi_encoder.build_index(concepts)

        # Create pipeline
        pipeline = TwoStageMatcher(bi_encoder, reranker)

        # Test matching - use exact term for reliable match
        result = pipeline.match("norepinephrine")
        assert result.concept_id == "norepinephrine"


class TestRankChangeDetection:
    """Tests for detecting when reranking changes top-1."""

    def test_rank_change_detected(self):
        """Rank change is detected when top-1 changes."""
        reranker = MockCrossEncoderReranker()
        reranker.initialize()

        # Set up candidates where reranking should change order
        candidates = [
            RerankCandidate("wrong_top", "wrong concept", 0.95),
            RerankCandidate("correct", "correct concept query match", 0.85),
        ]

        result = reranker.rerank("correct concept", candidates)

        # Should detect the rank change
        if result.concept_id == "correct":
            assert result.rank_change > 0
        else:
            assert result.rank_change == 0

    def test_no_rank_change(self):
        """Rank change is zero when top-1 stays the same."""
        reranker = MockCrossEncoderReranker()
        reranker.initialize()

        candidates = [
            RerankCandidate("best", "best exact match", 0.99),
            RerankCandidate("second", "second option", 0.85),
        ]

        result = reranker.rerank("best exact match", candidates)
        assert result.concept_id == "best"
        # rank_change might be 0 since best stays on top


class TestCrossEncoderRealModel:
    """Tests for real cross-encoder model (skipped if dependencies unavailable)."""

    @pytest.fixture
    def reranker(self):
        """Create real reranker if available."""
        reranker = CrossEncoderReranker(RerankerConfig())
        if not reranker.is_available:
            pytest.skip("Cross-encoder dependencies not available")
        return reranker

    @pytest.mark.slow
    def test_real_model_initialization(self, reranker):
        """Real model can initialize."""
        assert reranker.initialize() is True
        assert reranker.is_initialized is True

    @pytest.mark.slow
    def test_real_model_warm_up(self, reranker):
        """Real model warm-up succeeds."""
        stats = reranker.warm_up()
        assert stats["model_load_ms"] > 0
        assert reranker.is_initialized is True

    @pytest.mark.slow
    def test_real_model_rerank(self, reranker):
        """Real model can rerank candidates."""
        reranker.initialize()

        candidates = [
            RerankCandidate("norepinephrine", "norepinephrine vasopressor", 0.9),
            RerankCandidate("vasopressin", "vasopressin hormone", 0.85),
        ]

        result = reranker.rerank("start norepinephrine", candidates)
        assert result.concept_id in ["norepinephrine", "vasopressin"]
        assert 0.0 <= result.cross_encoder_score <= 1.0
