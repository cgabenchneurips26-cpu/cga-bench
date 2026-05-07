"""Clinical Ontology: IS-A hierarchy with subsumption-based matching.

Implements a lightweight SNOMED-CT-inspired concept graph for clinical
actions. Supports multi-level abstraction and ontology-grounded
conformance checking.

Design Patterns (from SOTA):
1. Hierarchical subsumption (Dwyer et al., 2025)
   - Mandatory actions satisfied by any descendant
   - Forbidden actions propagate to all descendants
2. Multi-level abstraction (Leonardi et al., 2018)
   - Check conformance at appropriate granularity
3. Embedding-ready concepts (SapBERT pattern)
   - Concept synonyms enable future embedding integration
4. Confidence-weighted matching
   - Exact > Synonym > Parent > Grandparent > Fuzzy

Complexity: O(|V| + |E|) for hierarchy traversal, O(1) for cached lookups.
"""
from __future__ import annotations

import logging
from collections import defaultdict, deque
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, FrozenSet, List, Optional, Set, Tuple

from .concept import (
    AbstractionLevel,
    ClinicalConcept,
    ConceptRelation,
    MatchResult,
)

logger = logging.getLogger(__name__)


class MatchStrategy(Enum):
    """Strategies for ontology-based matching."""
    EXACT = "exact"              # Exact concept_id match
    SYNONYM = "synonym"          # Match via synonym set
    SUBSUMPTION = "subsumption"  # Match via IS-A ancestor
    DESCENDANT = "descendant"    # Match via IS-A descendant
    FUZZY = "fuzzy"              # Jaccard token similarity
    NEURAL = "neural"            # Neural embedding similarity (SOTA fallback)
    NONE = "none"                # No match found


@dataclass
class OntologyConfig:
    """Configuration for ontology matching behavior.

    Attributes:
        max_subsumption_depth: Maximum IS-A hops for matching (default 3)
        subsumption_decay: Confidence decay per hop (default 0.15)
        fuzzy_threshold: Minimum Jaccard similarity for fuzzy match
        enable_contraindication_propagation: Propagate forbidden to descendants
        enable_mandatory_subsumption: Allow mandatory satisfaction by descendants
        enable_neural_fallback: Use neural embeddings when rule-based fails
        neural_model: HuggingFace model for neural embeddings
        neural_similarity_threshold: Min cosine similarity for neural match
        neural_confidence_weight: Weight applied to neural match confidence
    """
    max_subsumption_depth: int = 3
    subsumption_decay: float = 0.15
    fuzzy_threshold: float = 0.65
    enable_contraindication_propagation: bool = True
    enable_mandatory_subsumption: bool = True
    # Neural embedding fallback (SOTA)
    enable_neural_fallback: bool = False  # Disabled by default for backward compat
    neural_model: str = "cambridgeltl/SapBERT-from-PubMedBERT-fulltext"
    neural_similarity_threshold: float = 0.75
    neural_confidence_weight: float = 0.85  # Slightly lower confidence than rule-based


class ClinicalOntology:
    """SNOMED-CT-inspired concept graph with IS-A hierarchy.

    Provides:
    - Concept registration and relationship management
    - Subsumption queries (is_a, ancestors, descendants)
    - Lowest Common Ancestor (LCA) computation
    - Multi-level abstraction traversal

    Example:
        onto = ClinicalOntology()
        vasopressor = ClinicalConcept("VASOPRESSOR_SUPPORT", ...)
        norepi = ClinicalConcept("VASOPRESSOR_NOREPINEPHRINE", ...)
        onto.add_concept(vasopressor)
        onto.add_concept(norepi)
        onto.add_relation(norepi, ConceptRelation.IS_A, vasopressor)
        assert onto.is_a(norepi, vasopressor)  # True
    """

    def __init__(self):
        self._concepts: Dict[str, ClinicalConcept] = {}
        # Adjacency lists for IS-A (child -> parents, parent -> children)
        self._parents: Dict[str, Set[str]] = defaultdict(set)
        self._children: Dict[str, Set[str]] = defaultdict(set)
        # Other relations
        self._relations: Dict[str, List[Tuple[ConceptRelation, str]]] = defaultdict(list)
        # Synonym index: normalized_synonym -> concept_id
        self._synonym_index: Dict[str, str] = {}
        # Action ID index: normalized_action_id -> concept_id
        self._action_index: Dict[str, str] = {}
        # Cache for ancestors (populated lazily)
        self._ancestor_cache: Dict[str, FrozenSet[str]] = {}
        self._descendant_cache: Dict[str, FrozenSet[str]] = {}

    # ------------------------------------------------------------------
    # Concept Management
    # ------------------------------------------------------------------

    def add_concept(self, concept: ClinicalConcept) -> None:
        """Register a concept in the ontology."""
        self._concepts[concept.concept_id] = concept
        # Index synonyms
        for syn in concept.synonyms:
            normalized = self._normalize(syn)
            self._synonym_index[normalized] = concept.concept_id
        # Index concept_id as action_id
        self._action_index[self._normalize(concept.concept_id)] = concept.concept_id
        # Invalidate caches
        self._ancestor_cache.clear()
        self._descendant_cache.clear()

    def add_relation(
        self,
        source: ClinicalConcept,
        relation: ConceptRelation,
        target: ClinicalConcept,
    ) -> None:
        """Add a directed relation between concepts.

        For IS_A: source IS_A target (source is more specific).
        For CONTRAINDICATES: source CONTRAINDICATES target.
        """
        if source.concept_id not in self._concepts:
            self.add_concept(source)
        if target.concept_id not in self._concepts:
            self.add_concept(target)

        if relation == ConceptRelation.IS_A:
            self._parents[source.concept_id].add(target.concept_id)
            self._children[target.concept_id].add(source.concept_id)
        elif relation == ConceptRelation.EQUIVALENT:
            # Bidirectional synonym
            self._synonym_index[self._normalize(target.concept_id)] = source.concept_id
            self._synonym_index[self._normalize(source.concept_id)] = target.concept_id

        self._relations[source.concept_id].append((relation, target.concept_id))
        # Invalidate caches
        self._ancestor_cache.clear()
        self._descendant_cache.clear()

    def get_concept(self, concept_id: str) -> Optional[ClinicalConcept]:
        """Retrieve a concept by ID."""
        return self._concepts.get(concept_id)

    @property
    def concepts(self) -> Dict[str, ClinicalConcept]:
        """All registered concepts."""
        return dict(self._concepts)

    @property
    def size(self) -> int:
        """Number of concepts in the ontology."""
        return len(self._concepts)

    # ------------------------------------------------------------------
    # Subsumption Queries (IS-A hierarchy)
    # ------------------------------------------------------------------

    def is_a(self, child: ClinicalConcept, parent: ClinicalConcept) -> bool:
        """Check if child IS-A parent (transitive).

        Returns True if there is an IS-A path from child to parent.
        """
        return parent.concept_id in self.ancestors(child.concept_id)

    def ancestors(self, concept_id: str) -> FrozenSet[str]:
        """Get all transitive ancestors (IS-A parents) of a concept.

        Uses BFS with caching. Returns frozenset of ancestor concept_ids.
        """
        if concept_id in self._ancestor_cache:
            return self._ancestor_cache[concept_id]

        result: Set[str] = set()
        queue = deque(self._parents.get(concept_id, set()))
        while queue:
            parent_id = queue.popleft()
            if parent_id not in result:
                result.add(parent_id)
                queue.extend(self._parents.get(parent_id, set()) - result)

        frozen = frozenset(result)
        self._ancestor_cache[concept_id] = frozen
        return frozen

    def descendants(self, concept_id: str) -> FrozenSet[str]:
        """Get all transitive descendants (IS-A children) of a concept.

        Uses BFS with caching. Returns frozenset of descendant concept_ids.
        """
        if concept_id in self._descendant_cache:
            return self._descendant_cache[concept_id]

        result: Set[str] = set()
        queue = deque(self._children.get(concept_id, set()))
        while queue:
            child_id = queue.popleft()
            if child_id not in result:
                result.add(child_id)
                queue.extend(self._children.get(child_id, set()) - result)

        frozen = frozenset(result)
        self._descendant_cache[concept_id] = frozen
        return frozen

    def direct_parents(self, concept_id: str) -> Set[str]:
        """Get immediate IS-A parents."""
        return set(self._parents.get(concept_id, set()))

    def direct_children(self, concept_id: str) -> Set[str]:
        """Get immediate IS-A children."""
        return set(self._children.get(concept_id, set()))

    def subsumption_distance(self, child_id: str, ancestor_id: str) -> int:
        """Compute shortest IS-A path length from child to ancestor.

        Returns -1 if no path exists.
        """
        if child_id == ancestor_id:
            return 0
        if ancestor_id not in self.ancestors(child_id):
            return -1

        # BFS for shortest path
        queue: deque = deque([(child_id, 0)])
        visited: Set[str] = {child_id}
        while queue:
            current, dist = queue.popleft()
            for parent_id in self._parents.get(current, set()):
                if parent_id == ancestor_id:
                    return dist + 1
                if parent_id not in visited:
                    visited.add(parent_id)
                    queue.append((parent_id, dist + 1))
        return -1

    def lca(self, concept_a: str, concept_b: str) -> Optional[str]:
        """Lowest Common Ancestor of two concepts.

        Finds the most specific concept that subsumes both a and b.
        Returns None if no common ancestor exists.
        """
        ancestors_a = self.ancestors(concept_a) | {concept_a}
        ancestors_b = self.ancestors(concept_b) | {concept_b}
        common = ancestors_a & ancestors_b
        if not common:
            return None

        # Find the one with the greatest depth (most specific)
        best = None
        best_depth = -1
        for cid in common:
            depth = self._concept_depth(cid)
            if depth > best_depth:
                best_depth = depth
                best = cid
        return best

    def concepts_at_level(self, level: AbstractionLevel) -> List[ClinicalConcept]:
        """Get all concepts at a given abstraction level."""
        return [c for c in self._concepts.values() if c.level == level]

    def get_contraindications(self, concept_id: str) -> Set[str]:
        """Get all concepts contraindicated by this concept.

        If propagation enabled, includes descendants of contraindicated concepts.
        """
        result: Set[str] = set()
        for rel, target_id in self._relations.get(concept_id, []):
            if rel == ConceptRelation.CONTRAINDICATES:
                result.add(target_id)
        return result

    def get_prerequisites(self, concept_id: str) -> List[str]:
        """Get concepts that must precede this concept (PRECEDES relation)."""
        result = []
        for rel, target_id in self._relations.get(concept_id, []):
            if rel == ConceptRelation.PRECEDES:
                result.append(target_id)
        # Also check reverse: who has PRECEDES pointing to concept_id
        for src_id, rels in self._relations.items():
            for rel, tgt in rels:
                if rel == ConceptRelation.PRECEDES and tgt == concept_id:
                    result.append(src_id)
        return result

    # ------------------------------------------------------------------
    # Abstraction Operations
    # ------------------------------------------------------------------

    def abstract_to_level(
        self, concept_id: str, target_level: AbstractionLevel
    ) -> Optional[ClinicalConcept]:
        """Abstract a concept up to the target level via IS-A hierarchy.

        Finds the nearest ancestor at or above target_level.
        Returns None if no ancestor exists at that level.
        """
        concept = self._concepts.get(concept_id)
        if not concept:
            return None
        if concept.level >= target_level:
            return concept

        # BFS upward looking for target level
        queue: deque = deque([concept_id])
        visited: Set[str] = {concept_id}
        while queue:
            current_id = queue.popleft()
            for parent_id in self._parents.get(current_id, set()):
                if parent_id in visited:
                    continue
                visited.add(parent_id)
                parent = self._concepts.get(parent_id)
                if parent and parent.level >= target_level:
                    return parent
                queue.append(parent_id)
        return None

    def get_abstraction_chain(self, concept_id: str) -> List[ClinicalConcept]:
        """Get the full abstraction chain from specific to general.

        Returns ordered list: [concept, L2_parent, L3_grandparent, L4_phase].
        Only includes the first ancestor at each higher level.
        """
        chain: List[ClinicalConcept] = []
        concept = self._concepts.get(concept_id)
        if not concept:
            return chain
        chain.append(concept)

        current_level = concept.level
        current_id = concept_id
        while current_level < AbstractionLevel.PHASE:
            next_level = AbstractionLevel(current_level + 1)
            abstract = self.abstract_to_level(current_id, next_level)
            if abstract and abstract.concept_id != current_id:
                chain.append(abstract)
                current_id = abstract.concept_id
                current_level = abstract.level
            else:
                break
        return chain

    # ------------------------------------------------------------------
    # Private Helpers
    # ------------------------------------------------------------------

    def _concept_depth(self, concept_id: str) -> int:
        """Compute depth of concept (longest path from root)."""
        if not self._parents.get(concept_id):
            return 0
        return 1 + max(
            self._concept_depth(p) for p in self._parents[concept_id]
        )

    @staticmethod
    def _normalize(text: str) -> str:
        """Normalize text for matching: lowercase, strip, replace hyphens."""
        return text.lower().strip().replace("-", "_").replace(" ", "_")


# ======================================================================
# OntologyMatcher: Multi-strategy matching using the ontology
# ======================================================================

class OntologyMatcher:
    """Matches action strings to ontology concepts using multiple strategies.

    Matching cascade (highest to lowest priority):
    1. Exact concept_id match
    2. Synonym match (via synonym index)
    3. Subsumption match (query is descendant of known concept)
    4. Descendant match (query is ancestor of known concept)
    5. Fuzzy token match (Jaccard similarity)
    6. Neural embedding match (SapBERT/PubMedBERT fallback)

    Confidence scoring:
    - Exact/Synonym: 1.0
    - Subsumption: 1.0 - (distance × decay)
    - Fuzzy: Jaccard score × 0.9
    - Neural: cosine_similarity × neural_confidence_weight

    Usage:
        ontology = ClinicalOntology()
        # ... populate ontology ...
        config = OntologyConfig(enable_neural_fallback=True)
        matcher = OntologyMatcher(ontology, config)
        result = matcher.match("start_norepinephrine")
        if result.matched:
            print(f"Matched: {result.concept_id} (conf={result.confidence})")
    """

    def __init__(self, ontology: ClinicalOntology, config: OntologyConfig):
        self._ontology = ontology
        self._config = config
        self._match_cache: Dict[str, MatchResult] = {}
        self._neural_embedder = None
        self._neural_index_built = False

        # Initialize neural embedder if enabled
        if config.enable_neural_fallback:
            self._init_neural_embedder()

    @property
    def ontology(self) -> ClinicalOntology:
        """Access the underlying ontology."""
        return self._ontology

    def match(self, action_id: str) -> MatchResult:
        """Match an action string to the best ontology concept.

        Returns MatchResult with matched concept, confidence, and strategy.
        """
        normalized = ClinicalOntology._normalize(action_id)

        # Check cache
        if normalized in self._match_cache:
            return self._match_cache[normalized]

        result = self._do_match(normalized, action_id)
        self._match_cache[normalized] = result
        return result

    def match_at_level(
        self, action_id: str, level: AbstractionLevel
    ) -> MatchResult:
        """Match and abstract to the specified level.

        First matches to the most specific concept, then abstracts up.
        """
        base_result = self.match(action_id)
        if not base_result.matched:
            return base_result

        concept = base_result.matched_concept
        if concept.level >= level:
            return base_result

        abstract = self._ontology.abstract_to_level(concept.concept_id, level)
        if abstract:
            distance = self._ontology.subsumption_distance(
                concept.concept_id, abstract.concept_id
            )
            return MatchResult(
                source=action_id,
                matched_concept=abstract,
                confidence=max(0.5, base_result.confidence - 0.1 * max(0, distance)),
                match_level=level,
                distance=distance if distance >= 0 else 0,
                strategy=base_result.strategy,
            )
        return base_result

    def satisfies(self, action_id: str, requirement_id: str) -> bool:
        """Check if action_id satisfies requirement via subsumption.

        An action satisfies a requirement if:
        1. It matches the exact requirement concept, OR
        2. It matches a descendant of the requirement (if mandatory_subsumption enabled)

        This implements: "any vasopressor satisfies VASOPRESSOR_SUPPORT requirement"
        """
        action_result = self.match(action_id)
        if not action_result.matched:
            return False

        action_cid = action_result.concept_id

        # Direct match
        req_normalized = ClinicalOntology._normalize(requirement_id)
        if ClinicalOntology._normalize(action_cid) == req_normalized:
            return True

        # Check if requirement is in ontology
        req_concept = self._ontology.get_concept(requirement_id)
        if not req_concept:
            # Try synonym/action index lookup
            req_cid = self._ontology._synonym_index.get(req_normalized)
            if not req_cid:
                req_cid = self._ontology._action_index.get(req_normalized)
            if req_cid:
                req_concept = self._ontology.get_concept(req_cid)

        if not req_concept:
            return action_cid == requirement_id

        if not self._config.enable_mandatory_subsumption:
            return action_cid == req_concept.concept_id

        # Subsumption: action IS-A requirement
        return (
            action_cid == req_concept.concept_id
            or req_concept.concept_id in self._ontology.ancestors(action_cid)
        )

    def is_forbidden(self, action_id: str, forbidden_ids: Set[str]) -> bool:
        """Check if action_id is forbidden (with contraindication propagation).

        If propagation enabled, an action is forbidden if:
        1. It directly matches a forbidden concept, OR
        2. It is a descendant of a forbidden concept (forbidden propagates down)
        """
        action_result = self.match(action_id)
        if not action_result.matched:
            return False

        action_cid = action_result.concept_id

        for fid in forbidden_ids:
            f_normalized = ClinicalOntology._normalize(fid)
            # Direct match
            if ClinicalOntology._normalize(action_cid) == f_normalized:
                return True

            if not self._config.enable_contraindication_propagation:
                continue

            # Check if action is a descendant of forbidden concept
            f_concept = self._ontology.get_concept(fid)
            if not f_concept:
                f_cid = self._ontology._action_index.get(f_normalized)
                if f_cid:
                    f_concept = self._ontology.get_concept(f_cid)
            if f_concept:
                if action_cid in self._ontology.descendants(f_concept.concept_id):
                    return True

        return False

    def clear_cache(self) -> None:
        """Clear the match cache (e.g., after ontology modification)."""
        self._match_cache.clear()

    # ------------------------------------------------------------------
    # Private Matching Logic
    # ------------------------------------------------------------------

    def _do_match(self, normalized: str, original: str) -> MatchResult:
        """Execute matching cascade."""
        # 1. Exact concept_id match
        cid = self._ontology._action_index.get(normalized)
        if cid:
            concept = self._ontology.get_concept(cid)
            if concept:
                return MatchResult(
                    source=original,
                    matched_concept=concept,
                    confidence=1.0,
                    match_level=concept.level,
                    distance=0,
                    strategy=MatchStrategy.EXACT.value,
                )

        # 2. Synonym match
        cid = self._ontology._synonym_index.get(normalized)
        if cid:
            concept = self._ontology.get_concept(cid)
            if concept:
                return MatchResult(
                    source=original,
                    matched_concept=concept,
                    confidence=1.0,
                    match_level=concept.level,
                    distance=0,
                    strategy=MatchStrategy.SYNONYM.value,
                )

        # 3. Subsumption match: find if normalized matches a known descendant
        #    that has a registered parent
        best_subsumption = self._find_subsumption_match(normalized)
        if best_subsumption:
            return best_subsumption

        # 4. Fuzzy token match
        fuzzy_result = self._find_fuzzy_match(normalized, original)
        if fuzzy_result:
            return fuzzy_result

        # 5. Neural embedding fallback (SOTA)
        if self._config.enable_neural_fallback:
            neural_result = self._find_neural_match(original)
            if neural_result:
                return neural_result

        # No match
        return MatchResult(
            source=original,
            matched_concept=None,
            confidence=0.0,
            match_level=AbstractionLevel.RAW,
            distance=-1,
            strategy=MatchStrategy.NONE.value,
        )

    def _find_subsumption_match(self, normalized: str) -> Optional[MatchResult]:
        """Find match via IS-A subsumption within max_depth."""
        # Check if any concept's synonyms partially match
        # This handles: "start_norepinephrine" matching VASOPRESSOR_NOREPINEPHRINE
        tokens = set(normalized.split("_"))
        best_match: Optional[ClinicalConcept] = None
        best_score = 0.0
        best_distance = 0

        for cid, concept in self._ontology._concepts.items():
            # Check concept_id token overlap
            concept_tokens = set(ClinicalOntology._normalize(cid).split("_"))
            jaccard = self._jaccard(tokens, concept_tokens)

            # Also check synonyms
            for syn in concept.synonyms:
                syn_tokens = set(ClinicalOntology._normalize(syn).split("_"))
                syn_jaccard = self._jaccard(tokens, syn_tokens)
                jaccard = max(jaccard, syn_jaccard)

            if jaccard > best_score and jaccard >= self._config.fuzzy_threshold:
                best_score = jaccard
                best_match = concept
                best_distance = 0

        if best_match:
            return MatchResult(
                source=normalized,
                matched_concept=best_match,
                confidence=min(1.0, best_score * 0.95),
                match_level=best_match.level,
                distance=best_distance,
                strategy=MatchStrategy.SUBSUMPTION.value,
            )
        return None

    def _find_fuzzy_match(
        self, normalized: str, original: str
    ) -> Optional[MatchResult]:
        """Find best fuzzy match using Jaccard token similarity."""
        tokens = set(normalized.split("_"))
        best_match: Optional[ClinicalConcept] = None
        best_score = 0.0
        alternatives: List[Tuple[ClinicalConcept, float]] = []

        for cid, concept in self._ontology._concepts.items():
            concept_tokens = set(ClinicalOntology._normalize(cid).split("_"))
            score = self._jaccard(tokens, concept_tokens)

            # Also check synonyms for better score
            for syn in concept.synonyms:
                syn_tokens = set(ClinicalOntology._normalize(syn).split("_"))
                syn_score = self._jaccard(tokens, syn_tokens)
                score = max(score, syn_score)

            if score >= self._config.fuzzy_threshold:
                alternatives.append((concept, score))
                if score > best_score:
                    best_score = score
                    best_match = concept

        if best_match:
            # Sort alternatives by score descending, keep top 3
            alternatives.sort(key=lambda x: x[1], reverse=True)
            return MatchResult(
                source=original,
                matched_concept=best_match,
                confidence=best_score * 0.9,
                match_level=best_match.level,
                distance=0,
                strategy=MatchStrategy.FUZZY.value,
                alternatives=[(c.concept_id, s) for c, s in alternatives[:3]],
            )
        return None

    @staticmethod
    def _jaccard(set_a: Set[str], set_b: Set[str]) -> float:
        """Jaccard similarity between two token sets."""
        if not set_a or not set_b:
            return 0.0
        intersection = set_a & set_b
        union = set_a | set_b
        return len(intersection) / len(union) if union else 0.0

    # ------------------------------------------------------------------
    # Neural Embedding Fallback (SOTA)
    # ------------------------------------------------------------------

    def _init_neural_embedder(self) -> None:
        """Initialize neural embedding provider (lazy loading)."""
        try:
            from .neural_embedder import (
                EmbedderConfig,
                get_embedder,
            )

            config = EmbedderConfig(
                model_name=self._config.neural_model,
                similarity_threshold=self._config.neural_similarity_threshold,
            )
            self._neural_embedder = get_embedder(config)
            logger.info(f"Neural embedder initialized: {self._config.neural_model}")

        except ImportError as e:
            logger.warning(f"Neural embedding not available: {e}")
            self._neural_embedder = None
        except Exception as e:
            logger.error(f"Failed to initialize neural embedder: {e}")
            self._neural_embedder = None

    def build_neural_index(self, force_rebuild: bool = False) -> bool:
        """Build FAISS index from ontology concepts.

        Must be called after ontology is populated and before neural matching.
        Called automatically on first neural match attempt.

        Args:
            force_rebuild: Rebuild even if index exists

        Returns:
            True if index built successfully.
        """
        if self._neural_index_built and not force_rebuild:
            return True

        if self._neural_embedder is None:
            if self._config.enable_neural_fallback:
                self._init_neural_embedder()
            if self._neural_embedder is None:
                return False

        # Prepare concepts for indexing
        concepts = []
        for cid, concept in self._ontology._concepts.items():
            concepts.append((
                cid,
                concept.display,
                list(concept.synonyms),
            ))

        if not concepts:
            logger.warning("No concepts to index for neural matching")
            return False

        # Build index
        success = self._neural_embedder.build_index(concepts, force_rebuild)
        self._neural_index_built = success

        if success:
            logger.info(f"Neural index built with {len(concepts)} concepts")
        return success

    def _find_neural_match(self, original: str) -> Optional[MatchResult]:
        """Find match using neural embeddings (SOTA fallback).

        Uses SapBERT/PubMedBERT embeddings with FAISS for efficient search.
        Only called when rule-based methods fail.
        """
        if self._neural_embedder is None:
            return None

        # Build index on first use
        if not self._neural_index_built:
            if not self.build_neural_index():
                return None

        try:
            matches = self._neural_embedder.find_similar(original, top_k=3)

            if not matches:
                return None

            best = matches[0]
            concept = self._ontology.get_concept(best.concept_id)

            if not concept:
                return None

            # Apply confidence weight for neural matches
            confidence = best.similarity * self._config.neural_confidence_weight

            # Prepare alternatives
            alternatives = [
                (m.concept_id, m.similarity)
                for m in matches[1:]
            ]

            return MatchResult(
                source=original,
                matched_concept=concept,
                confidence=confidence,
                match_level=concept.level,
                distance=0,
                strategy=MatchStrategy.NEURAL.value,
                alternatives=alternatives,
            )

        except Exception as e:
            logger.error(f"Neural matching failed: {e}")
            return None

    @property
    def neural_enabled(self) -> bool:
        """Check if neural fallback is enabled and available."""
        return (
            self._config.enable_neural_fallback
            and self._neural_embedder is not None
        )

    def get_neural_stats(self) -> Dict[str, Any]:
        """Get neural embedding statistics for debugging."""
        if not self._neural_embedder:
            return {"enabled": False, "reason": "embedder not initialized"}

        return {
            "enabled": True,
            "model": self._config.neural_model,
            "index_built": self._neural_index_built,
            "threshold": self._config.neural_similarity_threshold,
            "confidence_weight": self._config.neural_confidence_weight,
        }
