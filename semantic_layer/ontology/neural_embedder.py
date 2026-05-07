"""Neural Embedding Provider for Clinical Concept Matching.

Implements SOTA neural embedding-based semantic matching using:
- SapBERT: Self-alignment pretraining for biomedical entity representations
- PubMedBERT: Domain-specific BERT pretrained on PubMed
- Sentence-Transformers: General-purpose sentence embeddings

Features:
- Lazy loading (model loaded on first use)
- FAISS indexing for O(log n) similarity search (HNSW or IVF)
- Caching for repeated queries
- Graceful fallback when models unavailable
- Entity extraction preprocessing for SapBERT
- Type/domain-aware filtering

IMPORTANT: Cosine Similarity Implementation
-------------------------------------------
This module uses L2-normalized embeddings with Inner Product (IP) index.
For L2-normalized vectors: cos(a,b) = a·b / (||a|| ||b||) = a·b (since ||a||=||b||=1)
Therefore IP on normalized vectors = cosine similarity.

References:
- Liu et al. (2021): SapBERT - Self-Alignment Pretraining for BERT
- Gu et al. (2021): Domain-Specific Pretraining for Biomedical NLP
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union

import numpy as np

logger = logging.getLogger(__name__)


# ============================================================
# Entity Extraction for SapBERT
# ============================================================

# Action verbs to remove (SapBERT expects entity names, not action phrases)
ACTION_VERBS = frozenset([
    "start", "give", "administer", "order", "perform", "obtain",
    "check", "monitor", "assess", "evaluate", "measure", "calculate",
    "discontinue", "stop", "hold", "titrate", "adjust", "increase",
    "decrease", "initiate", "continue", "repeat", "consider", "request",
])

# Semantic types for concepts
class SemanticType(str, Enum):
    """Semantic type for clinical concepts (UMLS-inspired)."""
    DRUG = "drug"               # Medications, infusions
    LAB = "lab"                 # Laboratory tests
    IMAGING = "imaging"         # Imaging studies
    PROCEDURE = "procedure"     # Clinical procedures
    ASSESSMENT = "assessment"   # Clinical assessments (NIHSS, GCS, etc.)
    VITAL = "vital"             # Vital signs
    FLUID = "fluid"             # IV fluids
    INTERVENTION = "intervention"  # General interventions
    UNKNOWN = "unknown"


def extract_entity_name(action_text: str) -> str:
    """Extract clinical entity name from action string for SapBERT.

    SapBERT is trained on biomedical entity names (drug names, lab tests, etc.),
    not action phrases. This function extracts the core entity.

    Examples:
        "start_norepinephrine_infusion" -> "norepinephrine"
        "order_blood_culture" -> "blood culture"
        "give_aspirin_325mg" -> "aspirin"
        "assess_nihss_score" -> "nihss"
    """
    # Normalize: underscore -> space, lowercase
    text = action_text.replace("_", " ").replace("-", " ").lower().strip()

    # Remove dosage patterns (e.g., "325mg", "0.1mcg/kg/min")
    text = re.sub(r'\d+\.?\d*\s*(mg|mcg|ml|l|g|kg|min|hr|units?|iu)\b', '', text, flags=re.IGNORECASE)
    text = re.sub(r'\d+\.?\d*\s*/\s*(kg|min|hr|l|ml)', '', text, flags=re.IGNORECASE)

    # Tokenize
    tokens = text.split()

    # Remove action verbs from the beginning
    while tokens and tokens[0] in ACTION_VERBS:
        tokens = tokens[1:]

    # Remove trailing modifiers
    trailing_modifiers = {"infusion", "bolus", "drip", "stat", "prn", "iv", "po", "im", "sq"}
    while tokens and tokens[-1] in trailing_modifiers:
        tokens = tokens[:-1]

    # Remove common prefixes/suffixes
    result = " ".join(tokens)
    result = re.sub(r'\s+', ' ', result).strip()

    return result if result else action_text.lower()


def infer_semantic_type(text: str) -> SemanticType:
    """Infer semantic type from text.

    Used for type-aware filtering to prevent false positive matches
    across different semantic categories.
    """
    text_lower = text.lower()

    # Drug indicators
    drug_patterns = [
        r"norepinephrine|vasopressin|dopamine|epinephrine|dobutamine",
        r"antibiotic|meropenem|vancomycin|piperacillin|ceftriaxone",
        r"aspirin|clopidogrel|heparin|enoxaparin|warfarin",
        r"insulin|metformin|furosemide|lasix|morphine|fentanyl",
        r"alteplase|tpa|tenecteplase",
    ]
    for pattern in drug_patterns:
        if re.search(pattern, text_lower):
            return SemanticType.DRUG

    # Lab indicators
    lab_patterns = [
        r"lactate|creatinine|troponin|bnp|glucose|potassium|sodium",
        r"blood.?culture|urine.?culture|cbc|bmp|cmp|coagulation",
        r"hemoglobin|hematocrit|platelet|wbc|inr|ptt",
    ]
    for pattern in lab_patterns:
        if re.search(pattern, text_lower):
            return SemanticType.LAB

    # Imaging indicators
    if re.search(r"ct|mri|x.?ray|ultrasound|echo|angiography|cta|ctp", text_lower):
        return SemanticType.IMAGING

    # Assessment indicators
    if re.search(r"nihss|gcs|sofa|apache|cam.?icu|rass|pain.?score", text_lower):
        return SemanticType.ASSESSMENT

    # Vital indicators
    if re.search(r"blood.?pressure|heart.?rate|temperature|spo2|respiratory", text_lower):
        return SemanticType.VITAL

    # Fluid indicators
    if re.search(r"crystalloid|saline|lactated|ringer|fluid|bolus", text_lower):
        return SemanticType.FLUID

    # Procedure indicators
    if re.search(r"intubation|catheter|central.?line|arterial.?line|dialysis", text_lower):
        return SemanticType.PROCEDURE

    return SemanticType.UNKNOWN


class EmbeddingModel(str, Enum):
    """Supported embedding models for clinical concept matching."""
    # Best for biomedical entity linking (UMLS-trained)
    SAPBERT = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
    # Good general biomedical understanding
    PUBMEDBERT = "microsoft/BiomedNLP-PubMedBERT-base-uncased-abstract-fulltext"
    # Lighter alternative, still good for medical
    BIOBERT = "dmis-lab/biobert-base-cased-v1.2"
    # Fastest, general purpose (fallback)
    MINILM = "sentence-transformers/all-MiniLM-L6-v2"
    # Clinical-specific
    CLINICAL_BERT = "emilyalsentzer/Bio_ClinicalBERT"


class FAISSIndexType(str, Enum):
    """FAISS index types with different performance characteristics."""
    FLAT = "flat"       # Exact search, O(n) - best for <10k vectors
    IVF = "ivf"         # Inverted file, O(sqrt(n)) - good for 10k-1M
    HNSW = "hnsw"       # Hierarchical NSW, O(log n) - best recall/speed balance


@dataclass
class EmbedderConfig:
    """Configuration for neural embedding provider.

    Attributes:
        model_name: HuggingFace model identifier
        use_gpu: Whether to use GPU if available
        cache_dir: Directory for model cache
        batch_size: Batch size for encoding
        normalize_embeddings: L2 normalize embeddings (REQUIRED for cosine sim)
        similarity_threshold: Minimum cosine similarity for match
        max_candidates: Maximum candidates to return
        enable_faiss: Use FAISS for efficient search
        faiss_index_type: Type of FAISS index (flat/ivf/hnsw)
        faiss_nprobe: Number of clusters to search (for IVF)
        hnsw_m: Number of connections per layer (for HNSW)
        hnsw_ef_construction: Size of dynamic candidate list (for HNSW build)
        hnsw_ef_search: Size of dynamic candidate list (for HNSW search)
        enable_entity_extraction: Extract entity names from action strings
        enable_type_filtering: Filter by semantic type
        type_mismatch_penalty: Penalty for type mismatch (0.0-1.0)

    Note on similarity_threshold:
        This is a RANKING score threshold, not a probability.
        For SapBERT cosine similarity:
        - 0.9+: Very high confidence (exact synonyms)
        - 0.75-0.9: High confidence (semantic equivalents)
        - 0.5-0.75: Moderate confidence (related concepts)
        - <0.5: Low confidence (weak association)
    """
    model_name: str = EmbeddingModel.SAPBERT.value
    use_gpu: bool = True
    cache_dir: Optional[str] = None
    batch_size: int = 32
    normalize_embeddings: bool = True  # MUST be True for cosine similarity
    similarity_threshold: float = 0.75
    max_candidates: int = 5
    enable_faiss: bool = True
    faiss_index_type: FAISSIndexType = FAISSIndexType.HNSW
    faiss_nprobe: int = 10  # For IVF
    hnsw_m: int = 32        # HNSW: connections per layer
    hnsw_ef_construction: int = 200  # HNSW: build quality
    hnsw_ef_search: int = 100        # HNSW: search quality
    enable_entity_extraction: bool = True  # Extract entity names for SapBERT
    enable_type_filtering: bool = True     # Filter by semantic type
    type_mismatch_penalty: float = 0.3     # Penalty for type mismatch


@dataclass
class EmbeddingMatch:
    """Result of neural embedding-based matching.

    IMPORTANT: Similarity vs Confidence
    ------------------------------------
    - similarity: Raw cosine similarity from embeddings (ranking score, NOT probability)
    - confidence: Deprecated alias for backward compatibility
    - semantic_type: Inferred semantic type of the matched concept

    For uncertainty quantification, use ConformalMatcher which provides
    calibrated prediction sets with coverage guarantees.
    """
    concept_id: str
    display: str
    similarity: float  # Cosine similarity (ranking score, NOT probability)
    rank: int
    semantic_type: SemanticType = SemanticType.UNKNOWN

    @property
    def confidence(self) -> float:
        """Legacy confidence score (DEPRECATED - use similarity + conformal sets).

        NOTE: This is NOT a calibrated probability. It's a heuristic transformation
        of cosine similarity for backward compatibility. For proper uncertainty
        quantification, use ConformalMatcher.predict() which returns calibrated
        prediction sets with coverage guarantees.
        """
        # Scale similarity [0, 1] -> [0.5, 1.0] for legacy compatibility
        return 0.5 + 0.5 * self.similarity


@dataclass
class IndexStats:
    """Statistics for FAISS index (for logging and debugging)."""
    n_vectors: int
    dimension: int
    index_type: str
    build_time_ms: float
    ram_estimate_mb: float


class NeuralEmbedder:
    """Neural embedding provider with FAISS-accelerated similarity search.

    Provides SOTA neural embedding-based matching for clinical concepts.
    Uses lazy loading to avoid memory overhead when not needed.

    IMPORTANT: Cosine Similarity Implementation
    -------------------------------------------
    We use L2-normalized embeddings (normalize_embeddings=True) with
    Inner Product (IP) index. For L2-normalized vectors:
        cos(a,b) = a·b / (||a|| ||b||) = a·b  (since ||a||=||b||=1)
    Therefore IP on normalized vectors == cosine similarity.

    Usage:
        embedder = NeuralEmbedder(EmbedderConfig())
        embedder.warm_up(concepts)  # Load model + build index (for benchmarks)
        matches = embedder.find_similar("norepinephrine infusion", top_k=5)
    """

    def __init__(self, config: EmbedderConfig):
        self._config = config
        self._model = None
        self._tokenizer = None
        self._index = None
        self._concept_ids: List[str] = []
        self._concept_texts: List[str] = []
        self._concept_types: List[SemanticType] = []  # Track semantic types
        self._embeddings: Optional[np.ndarray] = None
        self._query_cache: Dict[str, np.ndarray] = {}
        self._initialized = False
        self._device = None
        self._index_stats: Optional[IndexStats] = None
        self._load_time_ms: float = 0.0

        # Query execution tracking for benchmark analysis
        self._query_count: int = 0
        self._cache_hits: int = 0
        self._total_query_time_ms: float = 0.0
        self._query_latencies: List[float] = []  # For p50/p95 calculation
        self._type_penalties_applied: int = 0

    @property
    def is_available(self) -> bool:
        """Check if neural embedding is available."""
        try:
            import torch
            from sentence_transformers import SentenceTransformer
            return True
        except ImportError:
            return False

    @property
    def is_initialized(self) -> bool:
        """Check if model and index are ready."""
        return self._initialized and self._index is not None

    @property
    def index_stats(self) -> Optional[IndexStats]:
        """Get index statistics (for logging)."""
        return self._index_stats

    @property
    def load_time_ms(self) -> float:
        """Model load time in milliseconds."""
        return self._load_time_ms

    def get_query_statistics(self) -> Dict[str, Any]:
        """Get query execution statistics for benchmark analysis.

        Returns:
            Dict with query count, cache hits, latency percentiles, etc.
        """
        stats = {
            "query_count": self._query_count,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": self._cache_hits / self._query_count if self._query_count > 0 else 0.0,
            "total_query_time_ms": self._total_query_time_ms,
            "type_penalties_applied": self._type_penalties_applied,
        }

        if self._query_latencies:
            sorted_lat = sorted(self._query_latencies)
            n = len(sorted_lat)
            stats["latency_mean_ms"] = sum(sorted_lat) / n
            stats["latency_p50_ms"] = sorted_lat[n // 2]
            stats["latency_p95_ms"] = sorted_lat[int(n * 0.95)] if n >= 20 else sorted_lat[-1]
            stats["latency_max_ms"] = sorted_lat[-1]
            stats["latency_min_ms"] = sorted_lat[0]

        return stats

    def reset_statistics(self) -> None:
        """Reset query statistics (useful between benchmark runs)."""
        self._query_count = 0
        self._cache_hits = 0
        self._total_query_time_ms = 0.0
        self._query_latencies = []
        self._type_penalties_applied = 0

    def get_index_stats(self) -> Optional[IndexStats]:
        """Get index statistics for logging (method form for API consistency)."""
        return self._index_stats

    def initialize(self) -> bool:
        """Initialize the embedding model (lazy loading).

        Returns:
            True if initialization successful, False otherwise.
        """
        if self._initialized:
            return True

        if not self.is_available:
            logger.warning("Neural embedding dependencies not available")
            return False

        try:
            import torch
            from sentence_transformers import SentenceTransformer

            start_time = time.perf_counter()

            # Determine device
            if self._config.use_gpu and torch.cuda.is_available():
                self._device = "cuda"
            else:
                self._device = "cpu"

            logger.info(f"Loading embedding model: {self._config.model_name}")

            # Load model with cache directory
            cache_dir = self._config.cache_dir
            if cache_dir:
                os.makedirs(cache_dir, exist_ok=True)

            self._model = SentenceTransformer(
                self._config.model_name,
                cache_folder=cache_dir,
                device=self._device,
            )

            self._load_time_ms = (time.perf_counter() - start_time) * 1000
            self._initialized = True
            logger.info(
                f"Embedding model loaded on {self._device} "
                f"(load_time={self._load_time_ms:.1f}ms)"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to initialize embedding model: {e}")
            return False

    def warm_up(
        self,
        concepts: List[Tuple[str, str, List[str]]],
    ) -> Dict[str, float]:
        """Warm-up: Load model and build index in one call.

        Use this at benchmark runner start to avoid p95 latency spikes
        from lazy initialization during actual episodes.

        Args:
            concepts: List of (concept_id, display_name, synonyms)

        Returns:
            Dict with timing statistics: model_load_ms, index_build_ms, total_ms
        """
        stats = {"model_load_ms": 0.0, "index_build_ms": 0.0, "total_ms": 0.0}
        total_start = time.perf_counter()

        # Step 1: Initialize model
        init_start = time.perf_counter()
        if not self.initialize():
            logger.error("Warm-up failed: model initialization failed")
            return stats
        stats["model_load_ms"] = (time.perf_counter() - init_start) * 1000

        # Step 2: Build index
        index_start = time.perf_counter()
        if not self.build_index(concepts, force_rebuild=True):
            logger.error("Warm-up failed: index build failed")
            return stats
        stats["index_build_ms"] = (time.perf_counter() - index_start) * 1000

        stats["total_ms"] = (time.perf_counter() - total_start) * 1000

        logger.info(
            f"Warm-up complete: model={stats['model_load_ms']:.1f}ms, "
            f"index={stats['index_build_ms']:.1f}ms, total={stats['total_ms']:.1f}ms"
        )
        return stats

    def build_index(
        self,
        concepts: List[Tuple[str, str, List[str]]],
        force_rebuild: bool = False,
    ) -> bool:
        """Build FAISS index from concept list.

        IMPORTANT: Index Type Selection
        --------------------------------
        - FLAT (IndexFlatIP): Exact search, O(n). Best for <10k vectors.
        - IVF (IndexIVFFlat): Approximate, O(sqrt(n)). Good for 10k-1M.
        - HNSW (IndexHNSWFlat): Approximate, O(log n). Best recall/speed balance.

        All indices use Inner Product (IP) with L2-normalized embeddings,
        which is mathematically equivalent to cosine similarity.

        Args:
            concepts: List of (concept_id, display_name, synonyms)
            force_rebuild: Rebuild even if index exists

        Returns:
            True if index built successfully.
        """
        if self._index is not None and not force_rebuild:
            return True

        if not self.initialize():
            return False

        try:
            import faiss

            build_start = time.perf_counter()

            # Prepare texts for embedding with entity extraction
            self._concept_ids = []
            self._concept_texts = []
            self._concept_types = []

            for concept_id, display, synonyms in concepts:
                # Infer semantic type from display name
                semantic_type = infer_semantic_type(display)

                # Add main concept
                self._concept_ids.append(concept_id)
                self._concept_texts.append(self._prepare_text(display))
                self._concept_types.append(semantic_type)

                # Add synonyms (map to same concept_id)
                for syn in synonyms:
                    self._concept_ids.append(concept_id)
                    self._concept_texts.append(self._prepare_text(syn))
                    self._concept_types.append(semantic_type)

            if not self._concept_texts:
                logger.warning("No concepts to index")
                self._index_stats = IndexStats(0, 0, "empty", 0.0, 0.0)
                return True  # Empty index is valid

            logger.info(f"Encoding {len(self._concept_texts)} concept texts...")

            # Verify normalization config (critical for cosine similarity)
            if not self._config.normalize_embeddings:
                logger.warning(
                    "normalize_embeddings=False: Inner Product will NOT equal cosine similarity!"
                )

            # Encode all concepts
            self._embeddings = self._model.encode(
                self._concept_texts,
                batch_size=self._config.batch_size,
                normalize_embeddings=self._config.normalize_embeddings,
                show_progress_bar=True,
                convert_to_numpy=True,
            )

            # Verify embeddings are normalized (sanity check)
            norms = np.linalg.norm(self._embeddings[:10], axis=1)
            if self._config.normalize_embeddings and not np.allclose(norms, 1.0, atol=1e-5):
                logger.error(
                    f"Embedding normalization failed! Norms: {norms}. "
                    "Cosine similarity will be incorrect."
                )

            # Build FAISS index based on config
            dim = self._embeddings.shape[1]
            n_vectors = len(self._concept_texts)
            index_type = self._config.faiss_index_type

            if index_type == FAISSIndexType.HNSW or (
                index_type == FAISSIndexType.FLAT and n_vectors >= 10000
            ):
                # HNSW: Best recall/speed balance for most cases
                # Use IP variant for normalized embeddings (= cosine similarity)
                self._index = faiss.IndexHNSWFlat(dim, self._config.hnsw_m)
                self._index.hnsw.efConstruction = self._config.hnsw_ef_construction
                self._index.hnsw.efSearch = self._config.hnsw_ef_search
                actual_type = "HNSW"
            elif index_type == FAISSIndexType.IVF and n_vectors >= 1000:
                # IVF: Good for larger indices
                nlist = min(100, n_vectors // 10)
                quantizer = faiss.IndexFlatIP(dim)
                self._index = faiss.IndexIVFFlat(quantizer, dim, nlist)
                self._index.train(self._embeddings)
                self._index.nprobe = self._config.faiss_nprobe
                actual_type = f"IVF(nlist={nlist})"
            else:
                # FLAT: Exact search for small indices
                self._index = faiss.IndexFlatIP(dim)
                actual_type = "FlatIP"

            self._index.add(self._embeddings)

            build_time = (time.perf_counter() - build_start) * 1000
            ram_estimate = (self._embeddings.nbytes + n_vectors * 8) / (1024 * 1024)

            self._index_stats = IndexStats(
                n_vectors=n_vectors,
                dimension=dim,
                index_type=actual_type,
                build_time_ms=build_time,
                ram_estimate_mb=ram_estimate,
            )

            logger.info(
                f"FAISS index built: {n_vectors} vectors, dim={dim}, "
                f"type={actual_type}, build_time={build_time:.1f}ms, "
                f"RAM~{ram_estimate:.1f}MB"
            )
            return True

        except Exception as e:
            logger.error(f"Failed to build FAISS index: {e}")
            return False

    def find_similar(
        self,
        query: str,
        top_k: Optional[int] = None,
        expected_type: Optional[SemanticType] = None,
        log_execution: bool = True,
    ) -> List[EmbeddingMatch]:
        """Find most similar concepts to query.

        Args:
            query: Query text (action name, drug name, etc.)
            top_k: Number of results (default: config.max_candidates)
            expected_type: Expected semantic type for type-aware filtering
            log_execution: Whether to log execution details (for benchmarks)

        Returns:
            List of EmbeddingMatch sorted by similarity descending.

        Note:
            Similarity scores are cosine similarities (ranking scores),
            NOT calibrated probabilities. For uncertainty quantification,
            use ConformalMatcher.predict() instead.
        """
        if not self.is_initialized:
            return []

        if not query or not query.strip():
            return []

        query_start = time.perf_counter()
        top_k = top_k or self._config.max_candidates
        cache_hit = False
        type_penalty_count = 0

        try:
            # Infer query type if not provided
            if expected_type is None and self._config.enable_type_filtering:
                expected_type = infer_semantic_type(query)

            # Check if query embedding is cached
            cache_key = self._cache_key(query)
            cache_hit = cache_key in self._query_cache

            # Get query embedding (with caching)
            query_embedding = self._encode_query(query)

            # Search FAISS index (get extra candidates for filtering/dedup)
            search_k = min(top_k * 4, self._index.ntotal) if self._index.ntotal > 0 else 1
            similarities, indices = self._index.search(
                query_embedding.reshape(1, -1),
                search_k,
            )

            # Deduplicate by concept_id, apply type filtering
            seen_concepts: Dict[str, EmbeddingMatch] = {}

            for idx, sim in zip(indices[0], similarities[0]):
                if idx < 0:  # FAISS returns -1 for missing
                    continue

                concept_id = self._concept_ids[idx]
                similarity = float(sim)
                concept_type = self._concept_types[idx] if self._concept_types else SemanticType.UNKNOWN

                # Apply type mismatch penalty
                if (
                    self._config.enable_type_filtering
                    and expected_type is not None
                    and expected_type != SemanticType.UNKNOWN
                    and concept_type != SemanticType.UNKNOWN
                    and expected_type != concept_type
                ):
                    similarity -= self._config.type_mismatch_penalty
                    type_penalty_count += 1

                if similarity < self._config.similarity_threshold:
                    continue

                if concept_id not in seen_concepts or similarity > seen_concepts[concept_id].similarity:
                    seen_concepts[concept_id] = EmbeddingMatch(
                        concept_id=concept_id,
                        display=self._concept_texts[idx],
                        similarity=similarity,
                        rank=0,  # Will be set below
                        semantic_type=concept_type,
                    )

            # Sort by similarity and assign ranks
            results = sorted(
                seen_concepts.values(),
                key=lambda x: x.similarity,
                reverse=True,
            )[:top_k]

            for i, match in enumerate(results):
                match.rank = i + 1

            # Track execution statistics
            query_time_ms = (time.perf_counter() - query_start) * 1000
            if log_execution:
                self._query_count += 1
                self._total_query_time_ms += query_time_ms
                self._query_latencies.append(query_time_ms)
                if cache_hit:
                    self._cache_hits += 1
                if type_penalty_count > 0:
                    self._type_penalties_applied += 1

                # Log execution details for benchmark transparency
                if logger.isEnabledFor(logging.DEBUG):
                    top_match = results[0].concept_id if results else "none"
                    top_sim = results[0].similarity if results else 0.0
                    logger.debug(
                        f"[neural-query] query='{query[:40]}' top_k={top_k} "
                        f"type={expected_type.value if expected_type else 'unknown'} "
                        f"match='{top_match}' sim={top_sim:.3f} "
                        f"latency={query_time_ms:.1f}ms cache={cache_hit} "
                        f"type_penalty={type_penalty_count > 0}"
                    )

            return results

        except Exception as e:
            logger.error(f"Neural search failed: {e}")
            return []

    def compute_similarity(self, text_a: str, text_b: str) -> float:
        """Compute cosine similarity between two texts.

        Args:
            text_a: First text
            text_b: Second text

        Returns:
            Cosine similarity in [0, 1].
        """
        if not self.is_initialized:
            return 0.0

        try:
            emb_a = self._encode_query(text_a)
            emb_b = self._encode_query(text_b)

            # Cosine similarity (embeddings are normalized)
            similarity = float(np.dot(emb_a, emb_b))
            return max(0.0, min(1.0, similarity))

        except Exception as e:
            logger.error(f"Similarity computation failed: {e}")
            return 0.0

    def _encode_query(self, query: str) -> np.ndarray:
        """Encode query text with caching."""
        cache_key = self._cache_key(query)

        if cache_key in self._query_cache:
            return self._query_cache[cache_key]

        prepared = self._prepare_text(query)
        embedding = self._model.encode(
            prepared,
            normalize_embeddings=self._config.normalize_embeddings,
            convert_to_numpy=True,
        )

        # Cache management (LRU-like, keep last 1000)
        if len(self._query_cache) > 1000:
            # Remove oldest 100 entries
            keys = list(self._query_cache.keys())[:100]
            for k in keys:
                del self._query_cache[k]

        self._query_cache[cache_key] = embedding
        return embedding

    def _prepare_text(self, text: str) -> str:
        """Prepare text for embedding (normalization and entity extraction).

        For SapBERT-style models, the input should be biomedical entity names
        (e.g., "norepinephrine"), not action phrases (e.g., "start norepinephrine").
        When enable_entity_extraction=True, we extract the core entity.
        """
        if self._config.enable_entity_extraction:
            # Extract entity name for SapBERT
            text = extract_entity_name(text)
        else:
            # Basic normalization only
            text = text.replace("_", " ").replace("-", " ")
            text = text.lower().strip()
            text = " ".join(text.split())

        return text

    @staticmethod
    def _cache_key(text: str) -> str:
        """Generate cache key for text."""
        return hashlib.md5(text.lower().encode()).hexdigest()[:16]

    def save_index(self, path: Union[str, Path]) -> bool:
        """Save FAISS index and metadata to disk.

        Args:
            path: Directory path for saving.

        Returns:
            True if saved successfully.
        """
        if not self.is_initialized:
            return False

        try:
            import faiss
            import json

            path = Path(path)
            path.mkdir(parents=True, exist_ok=True)

            # Save FAISS index
            faiss.write_index(self._index, str(path / "faiss.index"))

            # Save metadata
            metadata = {
                "concept_ids": self._concept_ids,
                "concept_texts": self._concept_texts,
                "model_name": self._config.model_name,
            }
            with open(path / "metadata.json", "w") as f:
                json.dump(metadata, f)

            # Save embeddings (for rebuilding)
            np.save(path / "embeddings.npy", self._embeddings)

            logger.info(f"Index saved to {path}")
            return True

        except Exception as e:
            logger.error(f"Failed to save index: {e}")
            return False

    def load_index(self, path: Union[str, Path]) -> bool:
        """Load FAISS index and metadata from disk.

        Args:
            path: Directory path containing saved index.

        Returns:
            True if loaded successfully.
        """
        try:
            import faiss
            import json

            path = Path(path)

            if not (path / "faiss.index").exists():
                return False

            # Initialize model first
            if not self.initialize():
                return False

            # Load FAISS index
            self._index = faiss.read_index(str(path / "faiss.index"))

            # Load metadata
            with open(path / "metadata.json", "r") as f:
                metadata = json.load(f)

            self._concept_ids = metadata["concept_ids"]
            self._concept_texts = metadata["concept_texts"]

            # Load embeddings
            self._embeddings = np.load(path / "embeddings.npy")

            logger.info(f"Index loaded from {path}: {self._index.ntotal} vectors")
            return True

        except Exception as e:
            logger.error(f"Failed to load index: {e}")
            return False


class MockNeuralEmbedder:
    """Mock embedder for testing without GPU/model dependencies.

    Uses simple token overlap as a proxy for embedding similarity.
    Mirrors the NeuralEmbedder interface including query statistics.
    """

    def __init__(self, config: Optional[EmbedderConfig] = None):
        self._config = config or EmbedderConfig()
        self._concepts: Dict[str, Tuple[str, List[str]]] = {}
        self._initialized = False

        # Query tracking (mirrors NeuralEmbedder)
        self._query_count: int = 0
        self._cache_hits: int = 0
        self._total_query_time_ms: float = 0.0
        self._query_latencies: List[float] = []
        self._type_penalties_applied: int = 0
        self._index_stats: Optional[IndexStats] = None

    @property
    def is_available(self) -> bool:
        return True

    @property
    def is_initialized(self) -> bool:
        return self._initialized

    @property
    def index_stats(self) -> Optional[IndexStats]:
        """Get index statistics."""
        return self._index_stats

    def initialize(self) -> bool:
        self._initialized = True
        return True

    def get_query_statistics(self) -> Dict[str, Any]:
        """Get query execution statistics for benchmark analysis."""
        stats = {
            "query_count": self._query_count,
            "cache_hits": self._cache_hits,
            "cache_hit_rate": self._cache_hits / self._query_count if self._query_count > 0 else 0.0,
            "total_query_time_ms": self._total_query_time_ms,
            "type_penalties_applied": self._type_penalties_applied,
        }
        if self._query_latencies:
            sorted_lat = sorted(self._query_latencies)
            n = len(sorted_lat)
            stats["latency_mean_ms"] = sum(sorted_lat) / n
            stats["latency_p50_ms"] = sorted_lat[n // 2]
            stats["latency_p95_ms"] = sorted_lat[int(n * 0.95)] if n >= 20 else sorted_lat[-1]
            stats["latency_max_ms"] = sorted_lat[-1]
            stats["latency_min_ms"] = sorted_lat[0]
        return stats

    def reset_statistics(self) -> None:
        """Reset query statistics."""
        self._query_count = 0
        self._cache_hits = 0
        self._total_query_time_ms = 0.0
        self._query_latencies = []
        self._type_penalties_applied = 0

    def get_index_stats(self) -> Optional[IndexStats]:
        """Get index statistics for logging."""
        return self._index_stats

    def build_index(
        self,
        concepts: List[Tuple[str, str, List[str]]],
        force_rebuild: bool = False,
    ) -> bool:
        self._concepts = {
            cid: (display, list(synonyms))
            for cid, display, synonyms in concepts
        }
        # Create index stats for consistency with NeuralEmbedder
        self._index_stats = IndexStats(
            n_vectors=len(self._concepts),
            dimension=0,  # Mock doesn't use embeddings
            index_type="mock_jaccard",
            build_time_ms=0.0,
            ram_estimate_mb=0.0,
        )
        return True

    def find_similar(
        self,
        query: str,
        top_k: Optional[int] = None,
        expected_type: Optional[SemanticType] = None,
        log_execution: bool = True,
    ) -> List[EmbeddingMatch]:
        query_start = time.perf_counter()
        top_k = top_k or self._config.max_candidates
        query_tokens = set(query.lower().replace("_", " ").split())

        # Infer type if needed
        if expected_type is None and self._config.enable_type_filtering:
            expected_type = infer_semantic_type(query)

        matches = []
        type_penalty_count = 0
        for cid, (display, synonyms) in self._concepts.items():
            # Check display name
            display_tokens = set(display.lower().replace("_", " ").split())
            best_sim = self._jaccard(query_tokens, display_tokens)

            # Check synonyms
            for syn in synonyms:
                syn_tokens = set(syn.lower().replace("_", " ").split())
                sim = self._jaccard(query_tokens, syn_tokens)
                best_sim = max(best_sim, sim)

            # Apply type penalty if configured
            if self._config.enable_type_filtering and expected_type is not None:
                concept_type = infer_semantic_type(display)
                if (
                    expected_type != SemanticType.UNKNOWN
                    and concept_type != SemanticType.UNKNOWN
                    and expected_type != concept_type
                ):
                    best_sim -= self._config.type_mismatch_penalty
                    type_penalty_count += 1

            if best_sim >= self._config.similarity_threshold:
                matches.append(EmbeddingMatch(
                    concept_id=cid,
                    display=display,
                    similarity=best_sim,
                    rank=0,
                    semantic_type=infer_semantic_type(display),
                ))

        # Sort and assign ranks
        matches.sort(key=lambda x: x.similarity, reverse=True)
        for i, m in enumerate(matches[:top_k]):
            m.rank = i + 1

        # Track execution
        query_time_ms = (time.perf_counter() - query_start) * 1000
        if log_execution:
            self._query_count += 1
            self._total_query_time_ms += query_time_ms
            self._query_latencies.append(query_time_ms)
            if type_penalty_count > 0:
                self._type_penalties_applied += 1

        return matches[:top_k]

    def compute_similarity(self, text_a: str, text_b: str) -> float:
        tokens_a = set(text_a.lower().replace("_", " ").split())
        tokens_b = set(text_b.lower().replace("_", " ").split())
        return self._jaccard(tokens_a, tokens_b)

    @staticmethod
    def _jaccard(set_a, set_b) -> float:
        if not set_a or not set_b:
            return 0.0
        return len(set_a & set_b) / len(set_a | set_b)


def get_embedder(
    config: Optional[EmbedderConfig] = None,
    use_mock: bool = False,
) -> Union[NeuralEmbedder, MockNeuralEmbedder]:
    """Factory function to get appropriate embedder.

    Args:
        config: Embedder configuration
        use_mock: Force mock embedder (for testing)

    Returns:
        NeuralEmbedder if available, MockNeuralEmbedder otherwise.
    """
    config = config or EmbedderConfig()

    if use_mock:
        return MockNeuralEmbedder(config)

    embedder = NeuralEmbedder(config)
    if embedder.is_available:
        return embedder
    else:
        logger.warning("Neural embedder not available, using mock")
        return MockNeuralEmbedder(config)
