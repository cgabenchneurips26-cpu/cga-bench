"""
Benchmark Initialization Module for Semantic Layer

This module provides warm-up and initialization routines that ensure:
1. No p95 latency spikes during benchmark execution (model pre-loading)
2. FAISS index built before first query
3. Standardized execution logging for result validity

Usage in benchmark runner:
    from .benchmark_init import SemanticLayerInitializer

    # At benchmark startup (before any episodes)
    initializer = SemanticLayerInitializer(config)
    stats = initializer.warm_up(ontology)

    # After warm-up, all queries will have consistent latency
"""

import logging
import time
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Tuple
from enum import Enum

logger = logging.getLogger(__name__)


class InitializationPhase(str, Enum):
    """Phases of semantic layer initialization."""
    MODEL_LOAD = "model_load"
    INDEX_BUILD = "index_build"
    WARM_QUERY = "warm_query"


@dataclass
class InitializationStats:
    """Statistics from semantic layer initialization."""
    model_load_ms: float = 0.0
    index_build_ms: float = 0.0
    warm_query_ms: float = 0.0
    total_ms: float = 0.0

    # Index details
    n_vectors: int = 0
    dimension: int = 0
    index_type: str = "unknown"
    ram_estimate_mb: float = 0.0

    # Config used
    model_name: str = ""
    faiss_index_type: str = "hnsw"
    entity_extraction_enabled: bool = True
    type_filtering_enabled: bool = True
    type_mismatch_penalty: float = 0.3

    # Validation
    warm_query_success: bool = False
    ready_for_benchmark: bool = False
    errors: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging/serialization."""
        return {
            "timing": {
                "model_load_ms": self.model_load_ms,
                "index_build_ms": self.index_build_ms,
                "warm_query_ms": self.warm_query_ms,
                "total_ms": self.total_ms,
            },
            "index": {
                "n_vectors": self.n_vectors,
                "dimension": self.dimension,
                "index_type": self.index_type,
                "ram_estimate_mb": self.ram_estimate_mb,
            },
            "config": {
                "model_name": self.model_name,
                "faiss_index_type": self.faiss_index_type,
                "entity_extraction_enabled": self.entity_extraction_enabled,
                "type_filtering_enabled": self.type_filtering_enabled,
                "type_mismatch_penalty": self.type_mismatch_penalty,
            },
            "status": {
                "warm_query_success": self.warm_query_success,
                "ready_for_benchmark": self.ready_for_benchmark,
                "errors": self.errors,
            }
        }


@dataclass
class QueryExecutionLog:
    """Standardized log for each neural embedding query."""
    query_text: str
    query_entity: str  # After entity extraction
    query_semantic_type: str

    # Results
    top_match: Optional[str] = None
    top_similarity: float = 0.0
    num_results: int = 0

    # Strategy and config used
    strategy: str = "neural"
    top_k: int = 5
    type_penalty_applied: float = 0.0

    # Timing
    latency_ms: float = 0.0
    cache_hit: bool = False

    # For conformal prediction
    uncertainty_level: str = "unknown"

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for logging."""
        return {
            "query": {
                "text": self.query_text,
                "entity": self.query_entity,
                "semantic_type": self.query_semantic_type,
            },
            "results": {
                "top_match": self.top_match,
                "top_similarity": round(self.top_similarity, 4),
                "num_results": self.num_results,
            },
            "config": {
                "strategy": self.strategy,
                "top_k": self.top_k,
                "type_penalty_applied": round(self.type_penalty_applied, 4),
            },
            "performance": {
                "latency_ms": round(self.latency_ms, 2),
                "cache_hit": self.cache_hit,
            },
            "uncertainty_level": self.uncertainty_level,
        }


@dataclass
class SemanticLayerConfig:
    """Configuration for semantic layer initialization."""
    # Model selection
    model_name: str = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
    use_mock: bool = False

    # FAISS index config
    faiss_index_type: str = "hnsw"
    hnsw_m: int = 32
    hnsw_ef_construction: int = 200
    hnsw_ef_search: int = 100

    # Entity extraction
    enable_entity_extraction: bool = True
    enable_type_filtering: bool = True
    type_mismatch_penalty: float = 0.3

    # Warm-up validation
    warm_query_text: str = "norepinephrine"
    validate_warm_query: bool = True


class SemanticLayerInitializer:
    """
    Initializes semantic layer components for benchmark execution.

    This class ensures:
    1. Model is loaded before any benchmarks run (no p95 spikes)
    2. FAISS index is built and ready
    3. Warm-up query validates the pipeline
    4. All config is logged for reproducibility
    """

    def __init__(self, config: Optional[SemanticLayerConfig] = None):
        self.config = config or SemanticLayerConfig()
        self._embedder = None
        self._initialized = False
        self._stats: Optional[InitializationStats] = None
        self._query_logs: List[QueryExecutionLog] = []

    def warm_up(
        self,
        concepts: List[Tuple[str, str, List[str]]],
        force_rebuild: bool = False
    ) -> InitializationStats:
        """
        Warm up semantic layer: load model, build index, validate.

        Args:
            concepts: List of (concept_id, display_name, synonyms) tuples
            force_rebuild: Force rebuild even if already initialized

        Returns:
            InitializationStats with timing and config details
        """
        if self._initialized and not force_rebuild:
            logger.info("Semantic layer already initialized, skipping warm-up")
            return self._stats

        stats = InitializationStats(
            model_name=self.config.model_name,
            faiss_index_type=self.config.faiss_index_type,
            entity_extraction_enabled=self.config.enable_entity_extraction,
            type_filtering_enabled=self.config.enable_type_filtering,
            type_mismatch_penalty=self.config.type_mismatch_penalty,
        )

        total_start = time.perf_counter()

        try:
            # Phase 1: Load model
            logger.info(f"[warm-up] Loading model: {self.config.model_name}")
            model_start = time.perf_counter()
            self._load_embedder()
            stats.model_load_ms = (time.perf_counter() - model_start) * 1000

            # Phase 2: Build index
            logger.info(f"[warm-up] Building FAISS index ({self.config.faiss_index_type}) with {len(concepts)} concepts")
            index_start = time.perf_counter()
            index_success = self._build_index(concepts, force_rebuild)
            stats.index_build_ms = (time.perf_counter() - index_start) * 1000

            if not index_success:
                stats.errors.append("Index build failed")

            # Get index stats
            if hasattr(self._embedder, 'get_index_stats'):
                idx_stats = self._embedder.get_index_stats()
                if idx_stats:
                    stats.n_vectors = idx_stats.n_vectors
                    stats.dimension = idx_stats.dimension
                    stats.index_type = idx_stats.index_type
                    stats.ram_estimate_mb = idx_stats.ram_estimate_mb

            # Phase 3: Warm query
            if self.config.validate_warm_query and index_success:
                logger.info(f"[warm-up] Running validation query: '{self.config.warm_query_text}'")
                query_start = time.perf_counter()
                warm_success = self._validate_warm_query()
                stats.warm_query_ms = (time.perf_counter() - query_start) * 1000
                stats.warm_query_success = warm_success

                if not warm_success:
                    stats.errors.append("Warm query validation failed")

            stats.total_ms = (time.perf_counter() - total_start) * 1000
            stats.ready_for_benchmark = (
                len(stats.errors) == 0 and
                stats.n_vectors > 0
            )

            self._stats = stats
            self._initialized = True

            # Log summary
            logger.info(
                f"[warm-up] Complete: model={stats.model_load_ms:.0f}ms, "
                f"index={stats.index_build_ms:.0f}ms ({stats.n_vectors} vectors), "
                f"total={stats.total_ms:.0f}ms, ready={stats.ready_for_benchmark}"
            )

        except Exception as e:
            stats.errors.append(f"Exception during warm-up: {str(e)}")
            stats.total_ms = (time.perf_counter() - total_start) * 1000
            logger.error(f"[warm-up] Failed: {e}")
            import traceback
            traceback.print_exc()
            self._stats = stats

        return stats

    def _load_embedder(self) -> None:
        """Load the neural embedder with configured settings."""
        from .neural_embedder import (
            EmbedderConfig,
            FAISSIndexType,
            get_embedder,
        )

        # Map config string to enum
        index_type_map = {
            "flat": FAISSIndexType.FLAT,
            "ivf": FAISSIndexType.IVF,
            "hnsw": FAISSIndexType.HNSW,
        }

        embedder_config = EmbedderConfig(
            model_name=self.config.model_name,
            faiss_index_type=index_type_map.get(
                self.config.faiss_index_type.lower(),
                FAISSIndexType.HNSW
            ),
            hnsw_m=self.config.hnsw_m,
            hnsw_ef_construction=self.config.hnsw_ef_construction,
            hnsw_ef_search=self.config.hnsw_ef_search,
            enable_entity_extraction=self.config.enable_entity_extraction,
            enable_type_filtering=self.config.enable_type_filtering,
            type_mismatch_penalty=self.config.type_mismatch_penalty,
        )

        self._embedder = get_embedder(embedder_config, use_mock=self.config.use_mock)

    def _build_index(
        self,
        concepts: List[Tuple[str, str, List[str]]],
        force_rebuild: bool
    ) -> bool:
        """Build FAISS index from concepts."""
        if self._embedder is None:
            return False

        return self._embedder.build_index(concepts, force_rebuild)

    def _validate_warm_query(self) -> bool:
        """Run a warm-up query to validate pipeline."""
        if self._embedder is None:
            return False

        try:
            results = self._embedder.find_similar(
                self.config.warm_query_text,
                top_k=3
            )
            return len(results) > 0
        except Exception as e:
            logger.warning(f"Warm query failed: {e}")
            return False

    def log_query(
        self,
        query_text: str,
        results: List[Any],
        latency_ms: float,
        top_k: int = 5,
        cache_hit: bool = False,
        uncertainty_level: str = "unknown"
    ) -> QueryExecutionLog:
        """
        Log a query execution for benchmark analysis.

        Args:
            query_text: Original query text
            results: List of EmbeddingMatch results
            latency_ms: Query latency in milliseconds
            top_k: Number of results requested
            cache_hit: Whether result was from cache
            uncertainty_level: From conformal prediction (LOW/MEDIUM/HIGH/ABSTAIN)

        Returns:
            QueryExecutionLog for analysis
        """
        from .neural_embedder import (
            extract_entity_name,
            infer_semantic_type,
        )

        # Extract entity and type from query
        entity = extract_entity_name(query_text)
        semantic_type = infer_semantic_type(query_text)

        log = QueryExecutionLog(
            query_text=query_text,
            query_entity=entity,
            query_semantic_type=semantic_type.value if hasattr(semantic_type, 'value') else str(semantic_type),
            top_k=top_k,
            latency_ms=latency_ms,
            cache_hit=cache_hit,
            uncertainty_level=uncertainty_level,
        )

        if results:
            best = results[0]
            log.top_match = best.concept_id
            log.top_similarity = best.similarity
            log.num_results = len(results)

            # Check if type penalty was applied
            if hasattr(best, 'type_penalty_applied'):
                log.type_penalty_applied = best.type_penalty_applied

        self._query_logs.append(log)
        return log

    def get_query_logs(self) -> List[QueryExecutionLog]:
        """Get all logged queries for analysis."""
        return self._query_logs

    def get_stats(self) -> Optional[InitializationStats]:
        """Get initialization statistics."""
        return self._stats

    def is_ready(self) -> bool:
        """Check if semantic layer is ready for benchmark."""
        return self._initialized and self._stats and self._stats.ready_for_benchmark

    def get_embedder(self):
        """Get the underlying embedder (for direct access if needed)."""
        return self._embedder

    def generate_execution_report(self) -> Dict[str, Any]:
        """
        Generate execution report for benchmark result validity.

        Returns:
            Dict with initialization stats and query statistics
        """
        report = {
            "initialization": self._stats.to_dict() if self._stats else None,
            "query_count": len(self._query_logs),
        }

        if self._query_logs:
            latencies = [q.latency_ms for q in self._query_logs]
            cache_hits = sum(1 for q in self._query_logs if q.cache_hit)

            report["query_statistics"] = {
                "total_queries": len(self._query_logs),
                "cache_hits": cache_hits,
                "cache_hit_rate": cache_hits / len(self._query_logs) if self._query_logs else 0,
                "latency_p50_ms": sorted(latencies)[len(latencies) // 2] if latencies else 0,
                "latency_p95_ms": sorted(latencies)[int(len(latencies) * 0.95)] if len(latencies) >= 20 else max(latencies) if latencies else 0,
                "latency_max_ms": max(latencies) if latencies else 0,
                "latency_mean_ms": sum(latencies) / len(latencies) if latencies else 0,
            }

            # Type distribution
            type_counts: Dict[str, int] = {}
            for q in self._query_logs:
                type_counts[q.query_semantic_type] = type_counts.get(q.query_semantic_type, 0) + 1
            report["query_type_distribution"] = type_counts

            # Uncertainty distribution
            uncertainty_counts: Dict[str, int] = {}
            for q in self._query_logs:
                uncertainty_counts[q.uncertainty_level] = uncertainty_counts.get(q.uncertainty_level, 0) + 1
            report["uncertainty_distribution"] = uncertainty_counts

        return report


def create_initializer_for_runner(
    use_mock: bool = False,
    model_name: Optional[str] = None,
    faiss_index_type: str = "hnsw"
) -> SemanticLayerInitializer:
    """
    Factory function to create initializer for benchmark runner.

    Args:
        use_mock: Use mock embedder (for testing)
        model_name: Override default model
        faiss_index_type: FAISS index type (flat, ivf, hnsw)

    Returns:
        Configured SemanticLayerInitializer
    """
    config = SemanticLayerConfig(
        use_mock=use_mock,
        faiss_index_type=faiss_index_type,
    )

    if model_name:
        config.model_name = model_name

    return SemanticLayerInitializer(config)
