"""
Neural embedding-based fallback for terminology grounding.

Uses SapBERT (or BGE-M3 fallback) to find the closest matching
standard terminology code when exact YAML lookup fails.

Architecture:
- Pre-computed embeddings stored as .npy + metadata JSON
- Lazy-loaded encoder for runtime query encoding
- FAISS for fast nearest-neighbor search (numpy fallback)
- Confidence threshold to prevent false positives

References:
- SapBERT: https://arxiv.org/abs/2010.11784
- SNOBERT: https://arxiv.org/abs/2405.16115
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

logger = logging.getLogger(__name__)

_TERMINOLOGY_DIR = Path(__file__).parent
_DEFAULT_EMBEDDINGS_DIR = _TERMINOLOGY_DIR / "embeddings"


@dataclass
class NeuralGroundingConfig:
    """Configuration for neural embedding-based grounding.

    All fields have sensible defaults but can be overridden.
    """
    # Model selection
    model_name: str = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
    fallback_model: str = "BAAI/bge-m3"

    # Matching thresholds
    confidence_threshold: float = 0.7
    top_k: int = 5

    # Pre-computed embeddings paths
    embeddings_dir: Optional[str] = None
    expanded_codes_path: Optional[str] = None

    # Performance tuning
    use_gpu: bool = True
    use_fp16: bool = True
    batch_size: int = 32
    max_length: int = 128

    # System filtering
    filter_by_system: bool = True


@dataclass
class NeuralMatch:
    """A neural embedding match result with confidence."""
    code: str
    internal_code: str
    display: str
    system: str  # "loinc", "snomed", "rxnorm"
    confidence: float  # cosine similarity [0, 1]
    matched_synonym: Optional[str] = None


class NeuralGroundingBackend:
    """Neural embedding-based terminology grounding fallback.

    Uses pre-computed SapBERT embeddings over expanded terminology codes
    to find approximate matches when exact YAML lookup fails.

    Designed as a fallback layer - YAML matches remain authoritative.
    """

    def __init__(self, config: Optional[NeuralGroundingConfig] = None):
        self._config = config or NeuralGroundingConfig()
        self._model = None
        self._tokenizer = None
        self._model_name_loaded: Optional[str] = None
        self._initialized = False

        # Pre-computed data (loaded lazily)
        self._embeddings: Optional[np.ndarray] = None
        self._metadata: Optional[List[Dict[str, str]]] = None
        self._faiss_index = None
        self._system_indices: Dict[str, np.ndarray] = {}

    def find_matches(
        self,
        query: str,
        system: Optional[str] = None,
        top_k: Optional[int] = None,
    ) -> List[NeuralMatch]:
        """Find closest terminology matches for a query string.

        Args:
            query: The mention/internal_code to ground (e.g., "Na", "levophed")
            system: Filter to specific system ("loinc", "snomed", "rxnorm")
            top_k: Override default top_k from config

        Returns:
            List of NeuralMatch sorted by confidence (descending),
            filtered by confidence_threshold
        """
        if not query or not query.strip():
            return []

        self._ensure_initialized()
        if self._embeddings is None or self._metadata is None:
            return []

        k = top_k or self._config.top_k
        query_vec = self._encode_query(query.strip())
        if query_vec is None:
            return []

        # Build system mask if filtering
        system_mask = None
        if system and self._config.filter_by_system:
            system_mask = self._build_system_mask(system)
            if system_mask is not None and not system_mask.any():
                return []

        # Search
        candidates = self._search(query_vec, k * 2, system_mask)

        # Build results
        results = []
        seen_codes = set()
        for idx, score in candidates:
            if score < self._config.confidence_threshold:
                continue
            if idx >= len(self._metadata):
                continue

            meta = self._metadata[idx]
            code_key = f"{meta['system']}:{meta['code']}"
            if code_key in seen_codes:
                continue
            seen_codes.add(code_key)

            results.append(NeuralMatch(
                code=meta["code"],
                internal_code=meta["internal_code"],
                display=meta["display"],
                system=meta["system"],
                confidence=float(score),
                matched_synonym=meta.get("source_text"),
            ))

            if len(results) >= k:
                break

        return results

    def find_best_match(
        self,
        query: str,
        system: Optional[str] = None,
    ) -> Optional[NeuralMatch]:
        """Find single best match above confidence threshold.

        Convenience wrapper around find_matches that returns only the
        top result, or None if no match exceeds threshold.
        """
        matches = self.find_matches(query, system=system, top_k=1)
        return matches[0] if matches else None

    def is_available(self) -> bool:
        """Check if pre-computed embeddings exist and can be loaded."""
        emb_dir = self._get_embeddings_dir()
        emb_path = emb_dir / "terminology_embeddings.npy"
        meta_path = emb_dir / "terminology_metadata.json"
        return emb_path.exists() and meta_path.exists()

    def _ensure_initialized(self):
        """Lazy initialization of embeddings and model."""
        if self._initialized:
            return

        self._initialized = True
        self._load_embeddings()
        if self._embeddings is not None:
            self._load_model()

    def _get_embeddings_dir(self) -> Path:
        """Get the embeddings directory path."""
        if self._config.embeddings_dir:
            return Path(self._config.embeddings_dir)
        return _DEFAULT_EMBEDDINGS_DIR

    def _load_embeddings(self) -> None:
        """Load pre-computed embeddings and metadata from disk."""
        emb_dir = self._get_embeddings_dir()
        emb_path = emb_dir / "terminology_embeddings.npy"
        meta_path = emb_dir / "terminology_metadata.json"

        if not emb_path.exists() or not meta_path.exists():
            logger.info(
                f"Neural grounding embeddings not found at {emb_dir}, "
                "neural fallback disabled"
            )
            return

        try:
            self._embeddings = np.load(str(emb_path)).astype(np.float32)
            with open(meta_path, "r", encoding="utf-8") as f:
                self._metadata = json.load(f)

            if len(self._embeddings) != len(self._metadata):
                logger.warning(
                    f"Embeddings/metadata size mismatch: "
                    f"{len(self._embeddings)} vs {len(self._metadata)}"
                )
                self._embeddings = None
                self._metadata = None
                return

            # Build FAISS index if available
            self._build_index()

            # Pre-compute system masks
            for system in ("loinc", "snomed", "rxnorm"):
                mask = np.array(
                    [m.get("system") == system for m in self._metadata],
                    dtype=bool,
                )
                if mask.any():
                    self._system_indices[system] = mask

            logger.info(
                f"Loaded {len(self._embeddings)} terminology embeddings "
                f"(dim={self._embeddings.shape[1]})"
            )
        except Exception as e:
            logger.warning(f"Failed to load embeddings: {e}")
            self._embeddings = None
            self._metadata = None

    def _build_index(self):
        """Build FAISS index for fast search, or use numpy fallback."""
        try:
            import faiss

            dim = self._embeddings.shape[1]
            self._faiss_index = faiss.IndexFlatIP(dim)
            self._faiss_index.add(self._embeddings)
            logger.debug(f"Built FAISS index with {self._embeddings.shape[0]} vectors")
        except ImportError:
            logger.debug("FAISS not available, using numpy cosine similarity")
            self._faiss_index = None

    def _load_model(self) -> None:
        """Lazy-load the SapBERT encoder model.

        Falls back to BGE-M3 via sentence-transformers if SapBERT unavailable.
        """
        # Try SapBERT first
        model_name = self._config.model_name
        if self._try_load_transformers(model_name):
            return

        # Fallback to sentence-transformers with BGE-M3
        fallback = self._config.fallback_model
        if self._try_load_sentence_transformers(fallback):
            return

        logger.warning(
            "No embedding model available. Neural grounding will use "
            "pre-computed embeddings only (no runtime encoding)."
        )

    def _try_load_transformers(self, model_name: str) -> bool:
        """Try loading model with HuggingFace transformers."""
        try:
            from transformers import AutoModel, AutoTokenizer
            import torch

            self._tokenizer = AutoTokenizer.from_pretrained(model_name)
            self._model = AutoModel.from_pretrained(model_name)

            device = "cpu"
            if self._config.use_gpu and torch.cuda.is_available():
                device = "cuda"
                if self._config.use_fp16:
                    self._model = self._model.half()

            self._model = self._model.to(device)
            self._model.eval()
            self._model_name_loaded = model_name
            logger.info(f"Loaded {model_name} on {device}")
            return True
        except Exception as e:
            logger.debug(f"Cannot load {model_name} with transformers: {e}")
            return False

    def _try_load_sentence_transformers(self, model_name: str) -> bool:
        """Try loading model with sentence-transformers."""
        try:
            from sentence_transformers import SentenceTransformer

            device = "cpu"
            if self._config.use_gpu:
                try:
                    import torch
                    if torch.cuda.is_available():
                        device = "cuda"
                except ImportError:
                    pass

            self._model = SentenceTransformer(model_name, device=device)
            self._model_name_loaded = model_name
            self._tokenizer = None  # sentence-transformers handles internally
            logger.info(f"Loaded {model_name} via sentence-transformers on {device}")
            return True
        except Exception as e:
            logger.debug(f"Cannot load {model_name} with sentence-transformers: {e}")
            return False

    def _encode_query(self, query: str) -> Optional[np.ndarray]:
        """Encode a single query string to embedding vector.

        Returns normalized (L2) embedding of shape (D,), or None if no model.
        """
        if self._model is None:
            return None

        try:
            if self._tokenizer is not None:
                # HuggingFace transformers path (SapBERT)
                import torch

                inputs = self._tokenizer(
                    query,
                    return_tensors="pt",
                    max_length=self._config.max_length,
                    truncation=True,
                    padding=True,
                )

                device = next(self._model.parameters()).device
                inputs = {k: v.to(device) for k, v in inputs.items()}

                with torch.no_grad():
                    outputs = self._model(**inputs)
                    # Use [CLS] token embedding
                    embedding = outputs.last_hidden_state[:, 0, :].cpu().numpy()
            else:
                # sentence-transformers path
                embedding = self._model.encode(
                    [query],
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )

            vec = embedding[0].astype(np.float32)
            # L2 normalize
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec = vec / norm

            # Validate dimension compatibility with pre-computed embeddings
            if self._embeddings is not None and vec.shape[0] != self._embeddings.shape[1]:
                logger.warning(
                    f"Model output dim ({vec.shape[0]}) != embeddings dim "
                    f"({self._embeddings.shape[1]}). Neural matching unavailable."
                )
                return None

            return vec

        except Exception as e:
            logger.warning(f"Failed to encode query '{query}': {e}")
            return None

    def _search(
        self,
        query_vec: np.ndarray,
        top_k: int,
        system_mask: Optional[np.ndarray] = None,
    ) -> List[Tuple[int, float]]:
        """Search for nearest neighbors using FAISS or numpy fallback.

        Returns list of (index, cosine_similarity) tuples.
        """
        if self._faiss_index is not None and system_mask is None:
            # FAISS search (fast, but doesn't support masking directly)
            query_vec_2d = query_vec.reshape(1, -1)
            scores, indices = self._faiss_index.search(query_vec_2d, top_k)
            results = []
            for i in range(min(top_k, len(indices[0]))):
                idx = int(indices[0][i])
                score = float(scores[0][i])
                if idx >= 0:  # FAISS returns -1 for empty slots
                    results.append((idx, score))
            return results

        # Numpy fallback with optional system mask
        embeddings = self._embeddings
        if system_mask is not None:
            valid_indices = np.where(system_mask)[0]
            embeddings = self._embeddings[valid_indices]
        else:
            valid_indices = np.arange(len(self._embeddings))

        if len(embeddings) == 0:
            return []

        # Cosine similarity (embeddings are L2-normalized)
        scores = embeddings @ query_vec
        top_indices = np.argsort(scores)[::-1][:top_k]

        results = []
        for i in top_indices:
            original_idx = int(valid_indices[i])
            score = float(scores[i])
            results.append((original_idx, score))

        return results

    def _build_system_mask(self, system: str) -> Optional[np.ndarray]:
        """Get pre-computed boolean mask for a terminology system."""
        return self._system_indices.get(system.lower())
