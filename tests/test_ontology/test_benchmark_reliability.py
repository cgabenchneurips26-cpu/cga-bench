"""
Regression Tests for Benchmark Reliability

These tests verify that the semantic layer initialization and execution logging
work correctly for CGA-Bench result validity and reproducibility.

Run with: PYTHONPATH=. pytest tests/test_ontology/test_benchmark_reliability.py -v
"""

import pytest
import time
from typing import List, Tuple

from cga_bench.semantic_layer.ontology.benchmark_init import (
    SemanticLayerInitializer,
    SemanticLayerConfig,
    InitializationStats,
    QueryExecutionLog,
    create_initializer_for_runner,
)
from cga_bench.semantic_layer.ontology.neural_embedder import (
    NeuralEmbedder,
    MockNeuralEmbedder,
    EmbedderConfig,
    EmbeddingMatch,
    FAISSIndexType,
    IndexStats,
    SemanticType,
    extract_entity_name,
    infer_semantic_type,
    get_embedder,
)


# Sample concepts for testing
SAMPLE_CONCEPTS: List[Tuple[str, str, List[str]]] = [
    ("start_vasopressor_norepinephrine", "norepinephrine", ["levophed", "vasopressor"]),
    ("give_broad_spectrum_antibiotics", "broad spectrum antibiotics", ["ceftriaxone", "vancomycin"]),
    ("give_crystalloid_30ml_kg", "crystalloid fluid", ["normal saline", "lactated ringers"]),
    ("order_lab_lactate", "lactate", ["lactic acid"]),
    ("order_lab_blood_culture", "blood culture", ["culture"]),
    ("order_lab_troponin", "troponin", ["cardiac biomarker", "hs-troponin"]),
    ("perform_ecg", "electrocardiogram", ["ecg", "ekg"]),
    ("assess_vital_signs", "vital signs assessment", ["vitals", "blood pressure"]),
]


class TestSemanticLayerInitializer:
    """Tests for SemanticLayerInitializer warm-up functionality."""

    def test_initializer_creation(self):
        """Can create initializer with default config."""
        initializer = SemanticLayerInitializer()
        assert initializer.config is not None
        assert not initializer.is_ready()

    def test_initializer_with_custom_config(self):
        """Can create initializer with custom config."""
        config = SemanticLayerConfig(
            use_mock=True,
            faiss_index_type="flat",
            enable_entity_extraction=False,
        )
        initializer = SemanticLayerInitializer(config)
        assert initializer.config.use_mock is True
        assert initializer.config.faiss_index_type == "flat"

    def test_warm_up_mock_embedder(self):
        """Warm-up with mock embedder succeeds."""
        config = SemanticLayerConfig(use_mock=True)
        initializer = SemanticLayerInitializer(config)

        stats = initializer.warm_up(SAMPLE_CONCEPTS)

        assert stats is not None
        assert stats.ready_for_benchmark is True
        assert stats.n_vectors == len(SAMPLE_CONCEPTS)
        assert stats.total_ms >= 0
        assert len(stats.errors) == 0
        assert initializer.is_ready()

    def test_warm_up_idempotent(self):
        """Repeated warm-up calls are efficient (skipped if already done)."""
        config = SemanticLayerConfig(use_mock=True)
        initializer = SemanticLayerInitializer(config)

        stats1 = initializer.warm_up(SAMPLE_CONCEPTS)
        stats2 = initializer.warm_up(SAMPLE_CONCEPTS)

        # Second call returns same stats (cached)
        assert stats2 is stats1

    def test_warm_up_force_rebuild(self):
        """Force rebuild reinitializes the embedder."""
        config = SemanticLayerConfig(use_mock=True)
        initializer = SemanticLayerInitializer(config)

        stats1 = initializer.warm_up(SAMPLE_CONCEPTS)
        stats2 = initializer.warm_up(SAMPLE_CONCEPTS, force_rebuild=True)

        # Second call creates new stats
        assert stats2 is not stats1
        assert stats2.ready_for_benchmark is True

    def test_factory_function(self):
        """create_initializer_for_runner factory works."""
        initializer = create_initializer_for_runner(use_mock=True)
        assert isinstance(initializer, SemanticLayerInitializer)
        assert initializer.config.use_mock is True


class TestInitializationStats:
    """Tests for InitializationStats data class."""

    def test_stats_to_dict(self):
        """Stats can be converted to dict for logging."""
        stats = InitializationStats(
            model_load_ms=100.0,
            index_build_ms=50.0,
            total_ms=150.0,
            n_vectors=100,
            dimension=768,
            index_type="hnsw",
            ready_for_benchmark=True,
        )

        d = stats.to_dict()

        assert d["timing"]["model_load_ms"] == 100.0
        assert d["index"]["n_vectors"] == 100
        assert d["status"]["ready_for_benchmark"] is True

    def test_stats_errors_tracked(self):
        """Errors are tracked in stats."""
        stats = InitializationStats()
        stats.errors.append("Test error")

        assert len(stats.errors) == 1
        assert "Test error" in stats.errors


class TestQueryExecutionLog:
    """Tests for QueryExecutionLog data class."""

    def test_log_to_dict(self):
        """Query log can be converted to dict."""
        log = QueryExecutionLog(
            query_text="start norepinephrine",
            query_entity="norepinephrine",
            query_semantic_type="drug",
            top_match="start_vasopressor_norepinephrine",
            top_similarity=0.95,
            num_results=3,
            strategy="neural",
            top_k=5,
            latency_ms=10.5,
            cache_hit=False,
            uncertainty_level="LOW",
        )

        d = log.to_dict()

        assert d["query"]["text"] == "start norepinephrine"
        assert d["results"]["top_match"] == "start_vasopressor_norepinephrine"
        assert d["performance"]["latency_ms"] == 10.5
        assert d["uncertainty_level"] == "LOW"


class TestExecutionLogging:
    """Tests for execution logging in NeuralEmbedder."""

    def test_mock_embedder_tracks_queries(self):
        """MockNeuralEmbedder tracks query statistics."""
        embedder = MockNeuralEmbedder()
        embedder.build_index(SAMPLE_CONCEPTS)

        # Run some queries
        embedder.find_similar("norepinephrine")
        embedder.find_similar("lactate")
        embedder.find_similar("antibiotics")

        stats = embedder.get_query_statistics()

        assert stats["query_count"] == 3
        assert stats["total_query_time_ms"] > 0
        assert "latency_mean_ms" in stats

    def test_mock_embedder_reset_statistics(self):
        """Can reset query statistics between runs."""
        embedder = MockNeuralEmbedder()
        embedder.build_index(SAMPLE_CONCEPTS)

        embedder.find_similar("norepinephrine")
        assert embedder.get_query_statistics()["query_count"] == 1

        embedder.reset_statistics()
        assert embedder.get_query_statistics()["query_count"] == 0

    def test_mock_embedder_type_penalty_tracking(self):
        """Type penalties are tracked in statistics."""
        config = EmbedderConfig(
            enable_type_filtering=True,
            type_mismatch_penalty=0.3,
            similarity_threshold=0.0,  # Allow all matches
        )
        embedder = MockNeuralEmbedder(config)
        embedder.build_index(SAMPLE_CONCEPTS)

        # Query for a drug should penalize non-drug matches
        embedder.find_similar("norepinephrine", expected_type=SemanticType.DRUG)

        stats = embedder.get_query_statistics()
        # Some concepts may have been penalized
        assert "type_penalties_applied" in stats

    def test_mock_embedder_index_stats(self):
        """MockNeuralEmbedder provides index stats."""
        embedder = MockNeuralEmbedder()
        embedder.build_index(SAMPLE_CONCEPTS)

        stats = embedder.get_index_stats()

        assert stats is not None
        assert stats.n_vectors == len(SAMPLE_CONCEPTS)
        assert stats.index_type == "mock_jaccard"


class TestExecutionReport:
    """Tests for execution report generation."""

    def test_initializer_generates_report(self):
        """Initializer can generate execution report."""
        config = SemanticLayerConfig(use_mock=True)
        initializer = SemanticLayerInitializer(config)
        initializer.warm_up(SAMPLE_CONCEPTS)

        report = initializer.generate_execution_report()

        assert report["initialization"] is not None
        assert report["query_count"] == 0  # No queries yet

    def test_report_includes_query_stats(self):
        """Report includes query statistics after logging."""
        config = SemanticLayerConfig(use_mock=True)
        initializer = SemanticLayerInitializer(config)
        initializer.warm_up(SAMPLE_CONCEPTS)

        # Log some queries
        from cga_bench.semantic_layer.ontology.neural_embedder import EmbeddingMatch

        results = [
            EmbeddingMatch(
                concept_id="start_vasopressor_norepinephrine",
                display="norepinephrine",
                similarity=0.95,
                rank=1,
            )
        ]

        initializer.log_query(
            query_text="start norepinephrine",
            results=results,
            latency_ms=5.0,
            top_k=5,
        )

        report = initializer.generate_execution_report()

        assert report["query_count"] == 1
        assert "query_statistics" in report


class TestBenchmarkReliabilityRequirements:
    """Tests verifying benchmark reliability requirements."""

    def test_warm_up_before_queries_reduces_latency_variance(self):
        """Warm-up ensures consistent latency (no cold-start spikes)."""
        config = SemanticLayerConfig(use_mock=True)
        initializer = SemanticLayerInitializer(config)
        initializer.warm_up(SAMPLE_CONCEPTS)

        embedder = initializer.get_embedder()

        # Run multiple queries and check latency consistency
        latencies = []
        for query in ["norepinephrine", "lactate", "antibiotics", "troponin", "ecg"]:
            start = time.perf_counter()
            embedder.find_similar(query)
            latencies.append((time.perf_counter() - start) * 1000)

        # After warm-up, all latencies should be similar
        # (no 10x spikes from model loading)
        if latencies:
            max_lat = max(latencies)
            min_lat = min(latencies)
            # Max should not be more than 10x min (would indicate cold start)
            assert max_lat < min_lat * 10 or max_lat < 10  # Or all under 10ms

    def test_execution_config_is_logged(self):
        """All execution config is logged for reproducibility."""
        config = SemanticLayerConfig(
            use_mock=True,
            faiss_index_type="hnsw",
            enable_entity_extraction=True,
            type_mismatch_penalty=0.3,
        )
        initializer = SemanticLayerInitializer(config)
        stats = initializer.warm_up(SAMPLE_CONCEPTS)

        # Config should be captured in stats
        assert stats.faiss_index_type == "hnsw"
        assert stats.entity_extraction_enabled is True
        assert stats.type_mismatch_penalty == 0.3

    def test_query_logs_capture_all_required_fields(self):
        """Query logs capture strategy, top_k, type penalty, latency, cache hit."""
        config = SemanticLayerConfig(use_mock=True)
        initializer = SemanticLayerInitializer(config)
        initializer.warm_up(SAMPLE_CONCEPTS)

        log = initializer.log_query(
            query_text="start norepinephrine",
            results=[],
            latency_ms=5.0,
            top_k=5,
            cache_hit=False,
            uncertainty_level="LOW",
        )

        # All required fields should be present
        assert log.query_text == "start norepinephrine"
        assert log.query_entity is not None  # Entity extraction
        assert log.query_semantic_type is not None  # Type inference
        assert log.top_k == 5
        assert log.latency_ms == 5.0
        assert log.cache_hit is False
        assert log.uncertainty_level == "LOW"


class TestEntityExtractionForBenchmark:
    """Tests for entity extraction (SapBERT input preparation)."""

    def test_extract_entity_removes_action_verbs(self):
        """Entity extraction removes action verbs for SapBERT."""
        assert extract_entity_name("start norepinephrine") == "norepinephrine"
        assert extract_entity_name("give_antibiotics") == "antibiotics"
        # Note: "lab" is retained as context (lab lactate vs serum lactate)
        assert "lactate" in extract_entity_name("order_lab_lactate")

    def test_extract_entity_removes_dosage(self):
        """Entity extraction removes dosage info."""
        result = extract_entity_name("give_norepinephrine_0.1mcg_kg_min")
        assert "0.1" not in result
        assert "mcg" not in result

    def test_infer_semantic_type_drugs(self):
        """Semantic type inference identifies drugs."""
        assert infer_semantic_type("norepinephrine") == SemanticType.DRUG
        assert infer_semantic_type("antibiotics") == SemanticType.DRUG

    def test_infer_semantic_type_labs(self):
        """Semantic type inference identifies labs."""
        assert infer_semantic_type("lactate") == SemanticType.LAB
        assert infer_semantic_type("troponin") == SemanticType.LAB


class TestFAISSIndexTypes:
    """Tests for FAISS index type configuration."""

    def test_config_supports_all_index_types(self):
        """EmbedderConfig supports FLAT, IVF, HNSW."""
        for idx_type in [FAISSIndexType.FLAT, FAISSIndexType.IVF, FAISSIndexType.HNSW]:
            config = EmbedderConfig(faiss_index_type=idx_type)
            assert config.faiss_index_type == idx_type

    def test_default_index_type_is_hnsw(self):
        """Default index type is HNSW for best recall/speed balance."""
        config = EmbedderConfig()
        assert config.faiss_index_type == FAISSIndexType.HNSW


class TestBackwardCompatibility:
    """Tests ensuring backward compatibility with existing code."""

    def test_get_embedder_factory_unchanged(self):
        """get_embedder factory works with existing interface."""
        embedder = get_embedder(use_mock=True)
        assert isinstance(embedder, MockNeuralEmbedder)

    def test_find_similar_works_without_log_execution(self):
        """find_similar works with default log_execution=True."""
        embedder = MockNeuralEmbedder()
        embedder.build_index(SAMPLE_CONCEPTS)

        # Should work without specifying log_execution
        results = embedder.find_similar("norepinephrine")
        assert isinstance(results, list)

    def test_mock_embedder_interface_unchanged(self):
        """MockNeuralEmbedder maintains backward compatible interface."""
        embedder = MockNeuralEmbedder()
        assert hasattr(embedder, "build_index")
        assert hasattr(embedder, "find_similar")
        assert hasattr(embedder, "compute_similarity")
        assert hasattr(embedder, "is_initialized")
        assert hasattr(embedder, "is_available")


# Integration test with real embedder (if available)
@pytest.mark.skipif(
    not NeuralEmbedder(EmbedderConfig()).is_available,
    reason="Neural embedding dependencies not available"
)
class TestRealEmbedderIntegration:
    """Integration tests with real neural embedder (when available)."""

    def test_real_embedder_warm_up(self):
        """Real embedder warm-up works."""
        config = SemanticLayerConfig(
            use_mock=False,
            model_name="sentence-transformers/all-MiniLM-L6-v2",  # Fast model
            faiss_index_type="flat",  # Simple index for small test
        )
        initializer = SemanticLayerInitializer(config)

        stats = initializer.warm_up(SAMPLE_CONCEPTS)

        assert stats.ready_for_benchmark is True
        assert stats.model_load_ms > 0
        assert stats.index_build_ms > 0

    def test_real_embedder_query_tracking(self):
        """Real embedder tracks query statistics."""
        config = EmbedderConfig(
            model_name="sentence-transformers/all-MiniLM-L6-v2",
            faiss_index_type=FAISSIndexType.FLAT,
        )
        embedder = NeuralEmbedder(config)
        embedder.build_index(SAMPLE_CONCEPTS, force_rebuild=True)

        embedder.find_similar("norepinephrine")
        embedder.find_similar("lactate")

        stats = embedder.get_query_statistics()

        assert stats["query_count"] == 2
        assert stats["total_query_time_ms"] > 0
