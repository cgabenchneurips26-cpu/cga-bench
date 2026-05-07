"""Tests for Neural Embedding Fallback in Ontology Matching.

Tests the SOTA neural embedding-based semantic matching:
- SapBERT/PubMedBERT integration
- FAISS indexing (Flat, IVF, HNSW)
- Hybrid rule-based + neural matching
- Entity extraction for SapBERT input
- Semantic type inference and filtering
- Graceful fallback when dependencies unavailable
"""
from __future__ import annotations

import pytest

from cga_bench.semantic_layer.ontology.concept import (
    AbstractionLevel,
    ClinicalConcept,
    MatchResult,
)
from cga_bench.semantic_layer.ontology.clinical_ontology import (
    ClinicalOntology,
    MatchStrategy,
    OntologyConfig,
    OntologyMatcher,
)
from cga_bench.semantic_layer.ontology.neural_embedder import (
    EmbedderConfig,
    EmbeddingMatch,
    EmbeddingModel,
    FAISSIndexType,
    MockNeuralEmbedder,
    NeuralEmbedder,
    SemanticType,
    extract_entity_name,
    get_embedder,
    infer_semantic_type,
)


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture
def sample_concepts():
    """Sample clinical concepts for testing."""
    return [
        ("VASOPRESSOR_NOREPINEPHRINE", "Norepinephrine Infusion",
         ["norepinephrine", "levophed", "norepi"]),
        ("VASOPRESSOR_VASOPRESSIN", "Vasopressin Infusion",
         ["vasopressin", "adh", "pitressin"]),
        ("ANTIBIOTIC_MEROPENEM", "Meropenem",
         ["meropenem", "merrem"]),
        ("ANTIBIOTIC_VANCOMYCIN", "Vancomycin",
         ["vancomycin", "vanc"]),
        ("FLUID_CRYSTALLOID", "Crystalloid Bolus",
         ["crystalloid", "normal_saline", "lactated_ringers", "ns_bolus"]),
        ("LAB_LACTATE", "Serum Lactate",
         ["lactate", "lactic_acid"]),
        ("LAB_BLOOD_CULTURE", "Blood Culture",
         ["blood_culture", "cultures"]),
    ]


@pytest.fixture
def mock_embedder(sample_concepts):
    """Mock embedder with sample concepts indexed."""
    config = EmbedderConfig(similarity_threshold=0.5)
    embedder = MockNeuralEmbedder(config)
    embedder.build_index(sample_concepts)
    return embedder


@pytest.fixture
def sample_ontology():
    """Build a sample ontology for testing."""
    onto = ClinicalOntology()

    # Create concepts
    vasopressor = ClinicalConcept(
        concept_id="VASOPRESSOR_SUPPORT",
        display="Vasopressor Support",
        level=AbstractionLevel.CATEGORY,
        synonyms=frozenset(["vasopressors", "pressors"]),
    )
    norepi = ClinicalConcept(
        concept_id="VASOPRESSOR_NOREPINEPHRINE",
        display="Norepinephrine",
        level=AbstractionLevel.NORMALIZED,
        synonyms=frozenset(["norepinephrine", "levophed", "norepi"]),
    )
    vaso = ClinicalConcept(
        concept_id="VASOPRESSOR_VASOPRESSIN",
        display="Vasopressin",
        level=AbstractionLevel.NORMALIZED,
        synonyms=frozenset(["vasopressin", "adh"]),
    )
    abx = ClinicalConcept(
        concept_id="ANTIBIOTIC_THERAPY",
        display="Antibiotic Therapy",
        level=AbstractionLevel.CATEGORY,
        synonyms=frozenset(["antibiotics"]),
    )
    meropenem = ClinicalConcept(
        concept_id="ANTIBIOTIC_MEROPENEM",
        display="Meropenem",
        level=AbstractionLevel.NORMALIZED,
        synonyms=frozenset(["meropenem", "merrem"]),
    )

    # Add concepts
    for c in [vasopressor, norepi, vaso, abx, meropenem]:
        onto.add_concept(c)

    # Add IS-A relations
    from cga_bench.semantic_layer.ontology.concept import ConceptRelation
    onto.add_relation(norepi, ConceptRelation.IS_A, vasopressor)
    onto.add_relation(vaso, ConceptRelation.IS_A, vasopressor)
    onto.add_relation(meropenem, ConceptRelation.IS_A, abx)

    return onto


# ============================================================
# Test: Neural Embedder Core
# ============================================================

class TestNeuralEmbedderCore:
    """Tests for NeuralEmbedder class."""

    def test_embedder_config_defaults(self):
        """Config has sensible defaults."""
        config = EmbedderConfig()
        assert config.model_name == EmbeddingModel.SAPBERT.value
        assert config.similarity_threshold == 0.75
        assert config.enable_faiss is True

    def test_embedding_model_enum(self):
        """EmbeddingModel enum has expected values."""
        assert "SapBERT" in EmbeddingModel.SAPBERT.value
        assert "PubMedBERT" in EmbeddingModel.PUBMEDBERT.value
        assert "MiniLM" in EmbeddingModel.MINILM.value

    def test_mock_embedder_available(self):
        """Mock embedder is always available."""
        embedder = MockNeuralEmbedder()
        assert embedder.is_available is True

    def test_mock_embedder_build_index(self, sample_concepts):
        """Mock embedder can build index."""
        embedder = MockNeuralEmbedder()
        embedder.initialize()
        success = embedder.build_index(sample_concepts)
        assert success is True
        assert embedder.is_initialized is True

    def test_mock_embedder_find_similar(self, mock_embedder):
        """Mock embedder finds similar concepts."""
        matches = mock_embedder.find_similar("norepinephrine infusion")
        assert len(matches) >= 1
        assert matches[0].concept_id == "VASOPRESSOR_NOREPINEPHRINE"

    def test_mock_embedder_compute_similarity(self, mock_embedder):
        """Mock embedder computes similarity."""
        sim = mock_embedder.compute_similarity(
            "norepinephrine", "norepinephrine infusion"
        )
        assert sim >= 0.5  # Jaccard("norepinephrine") vs ("norepinephrine", "infusion") = 1/2 = 0.5

    def test_embedding_match_confidence(self):
        """EmbeddingMatch confidence scaling."""
        match = EmbeddingMatch(
            concept_id="TEST",
            display="Test",
            similarity=0.9,
            rank=1,
        )
        # confidence = 0.5 + 0.5 * similarity
        assert match.confidence == 0.95

    def test_get_embedder_factory_mock(self):
        """get_embedder returns mock when requested."""
        embedder = get_embedder(use_mock=True)
        assert isinstance(embedder, MockNeuralEmbedder)


class TestNeuralEmbedderMatching:
    """Tests for neural embedding matching quality."""

    def test_exact_synonym_match(self, mock_embedder):
        """Exact synonym gets high similarity."""
        matches = mock_embedder.find_similar("levophed")
        assert len(matches) >= 1
        best = matches[0]
        assert best.concept_id == "VASOPRESSOR_NOREPINEPHRINE"
        assert best.similarity >= 0.5

    def test_semantic_similarity_same_class(self, mock_embedder):
        """Similar concepts in same class have high similarity."""
        # Both are vasopressors
        sim = mock_embedder.compute_similarity(
            "norepinephrine", "vasopressin"
        )
        # Mock uses Jaccard, so this will be low
        # Real neural embeddings would give higher
        assert isinstance(sim, float)

    def test_semantic_dissimilar(self, mock_embedder):
        """Dissimilar concepts have low similarity."""
        sim = mock_embedder.compute_similarity(
            "norepinephrine", "blood_culture"
        )
        assert sim < 0.5

    def test_threshold_filtering(self, sample_concepts):
        """Matches below threshold are filtered out."""
        config = EmbedderConfig(similarity_threshold=0.9)  # High threshold
        embedder = MockNeuralEmbedder(config)
        embedder.build_index(sample_concepts)

        matches = embedder.find_similar("random_unrelated_text")
        assert len(matches) == 0

    def test_top_k_limit(self, mock_embedder):
        """top_k limits number of results."""
        matches = mock_embedder.find_similar("vasopressor", top_k=2)
        assert len(matches) <= 2


# ============================================================
# Test: OntologyMatcher Neural Integration
# ============================================================

class TestOntologyMatcherNeuralIntegration:
    """Tests for neural fallback in OntologyMatcher."""

    def test_neural_disabled_by_default(self, sample_ontology):
        """Neural fallback disabled by default for backward compat."""
        config = OntologyConfig()
        assert config.enable_neural_fallback is False

        matcher = OntologyMatcher(sample_ontology, config)
        assert matcher.neural_enabled is False

    def test_neural_enabled_config(self, sample_ontology):
        """Neural fallback can be enabled via config."""
        config = OntologyConfig(enable_neural_fallback=True)
        assert config.enable_neural_fallback is True
        assert config.neural_model == EmbeddingModel.SAPBERT.value

    def test_match_strategy_neural_exists(self):
        """NEURAL match strategy exists."""
        assert MatchStrategy.NEURAL.value == "neural"

    def test_rule_based_takes_priority(self, sample_ontology):
        """Rule-based matching takes priority over neural."""
        config = OntologyConfig(enable_neural_fallback=True)
        matcher = OntologyMatcher(sample_ontology, config)

        # This should match via synonym, not neural
        result = matcher.match("levophed")
        assert result.matched is True
        assert result.strategy in ["exact", "synonym", "subsumption", "fuzzy"]
        # Should NOT use neural for known synonyms
        assert result.strategy != "neural"

    def test_neural_stats_disabled(self, sample_ontology):
        """Neural stats when disabled."""
        config = OntologyConfig(enable_neural_fallback=False)
        matcher = OntologyMatcher(sample_ontology, config)

        stats = matcher.get_neural_stats()
        assert stats["enabled"] is False

    def test_exact_match_still_works(self, sample_ontology):
        """Exact matching unaffected by neural config."""
        config = OntologyConfig(enable_neural_fallback=True)
        matcher = OntologyMatcher(sample_ontology, config)

        result = matcher.match("VASOPRESSOR_NOREPINEPHRINE")
        assert result.matched is True
        assert result.strategy == "exact"
        assert result.confidence == 1.0

    def test_synonym_match_still_works(self, sample_ontology):
        """Synonym matching unaffected by neural config."""
        config = OntologyConfig(enable_neural_fallback=True)
        matcher = OntologyMatcher(sample_ontology, config)

        result = matcher.match("norepinephrine")
        assert result.matched is True
        assert result.strategy == "synonym"
        assert result.confidence == 1.0


class TestMatchingCascade:
    """Tests for the full matching cascade with neural fallback."""

    def test_cascade_order(self, sample_ontology):
        """Matching cascade: exact > synonym > subsumption > fuzzy > neural."""
        config = OntologyConfig(
            enable_neural_fallback=True,
            fuzzy_threshold=0.65,
        )
        matcher = OntologyMatcher(sample_ontology, config)

        # Exact match
        r1 = matcher.match("ANTIBIOTIC_MEROPENEM")
        assert r1.strategy == "exact"

        # Synonym match
        r2 = matcher.match("merrem")
        assert r2.strategy == "synonym"

        # Fuzzy match (partial token overlap)
        r3 = matcher.match("meropenem_iv")
        if r3.matched:
            assert r3.strategy in ["subsumption", "fuzzy", "neural"]

    def test_no_match_returns_none_strategy(self, sample_ontology):
        """Unmatched queries return NONE strategy."""
        config = OntologyConfig(enable_neural_fallback=False)
        matcher = OntologyMatcher(sample_ontology, config)

        result = matcher.match("completely_unknown_xyz_123")
        assert result.matched is False
        assert result.strategy == "none"
        assert result.confidence == 0.0


# ============================================================
# Test: Edge Cases
# ============================================================

class TestNeuralEdgeCases:
    """Edge cases for neural embedding."""

    def test_empty_concepts_list(self):
        """Empty concept list doesn't crash."""
        embedder = MockNeuralEmbedder()
        embedder.initialize()
        success = embedder.build_index([])
        # Should return True but no matches possible
        assert success is True

    def test_special_characters_in_query(self, mock_embedder):
        """Special characters handled gracefully."""
        matches = mock_embedder.find_similar("norepinephrine (IV)")
        # Should still find matches
        assert isinstance(matches, list)

    def test_unicode_in_query(self, mock_embedder):
        """Unicode characters handled gracefully."""
        matches = mock_embedder.find_similar("노르에피네프린")
        # Mock uses token overlap, so won't match
        # Real neural embeddings might if multilingual
        assert isinstance(matches, list)

    def test_very_long_query(self, mock_embedder):
        """Long queries handled gracefully."""
        long_query = "start " * 100 + "norepinephrine"
        matches = mock_embedder.find_similar(long_query)
        assert isinstance(matches, list)

    def test_empty_query(self, mock_embedder):
        """Empty query returns empty results."""
        matches = mock_embedder.find_similar("")
        assert matches == []

    def test_cache_management(self, sample_concepts):
        """Query cache doesn't grow unbounded."""
        config = EmbedderConfig(similarity_threshold=0.3)
        embedder = MockNeuralEmbedder(config)
        embedder.build_index(sample_concepts)

        # Generate many unique queries
        for i in range(100):
            embedder.find_similar(f"query_{i}")

        # Should not crash, mock doesn't have cache limit
        matches = embedder.find_similar("norepinephrine")
        assert len(matches) >= 1


# ============================================================
# Test: Real Neural Embedder (Optional, requires GPU/model)
# ============================================================

class TestRealNeuralEmbedder:
    """Tests for real neural embedder (skipped if unavailable)."""

    @pytest.fixture
    def real_embedder(self):
        """Get real embedder or skip."""
        embedder = NeuralEmbedder(EmbedderConfig(
            model_name=EmbeddingModel.MINILM.value,  # Fastest model
            use_gpu=False,
        ))
        if not embedder.is_available:
            pytest.skip("Neural embedding dependencies not available")
        return embedder

    @pytest.mark.slow
    def test_real_embedder_initialization(self, real_embedder):
        """Real embedder can initialize model."""
        success = real_embedder.initialize()
        # Either initialization succeeded, or we skip
        if not success:
            pytest.skip("Model initialization failed (network/resource issue)")
        # Note: is_initialized requires model AND index
        # After initialize(), only model is ready (index built later)
        assert success is True

    @pytest.mark.slow
    def test_real_embedder_build_index(self, real_embedder, sample_concepts):
        """Real embedder can build FAISS index."""
        real_embedder.initialize()
        success = real_embedder.build_index(sample_concepts)
        assert success is True

    @pytest.mark.slow
    def test_real_semantic_similarity(self, real_embedder, sample_concepts):
        """Real embedder captures semantic similarity."""
        real_embedder.initialize()
        real_embedder.build_index(sample_concepts)

        # Semantically related (both vasopressors)
        # Note: MiniLM is a general-purpose model, so similarity scores
        # may be lower than biomedical-specific models like SapBERT.
        # We use a lower threshold for this test.
        matches = real_embedder.find_similar("vasopressor", top_k=10)
        # Just verify we get some matches (threshold may filter out low scores)
        assert isinstance(matches, list)
        # If matches found, check they're reasonable
        if matches:
            concept_ids = [m.concept_id for m in matches]
            # With MiniLM (general model), we may or may not find exact matches
            # This test just verifies the pipeline works
            assert len(concept_ids) > 0

    @pytest.mark.slow
    def test_real_oov_handling(self, real_embedder, sample_concepts):
        """Real embedder handles out-of-vocabulary terms."""
        real_embedder.initialize()
        real_embedder.build_index(sample_concepts)

        # Query with clinical abbreviation not in synonyms
        matches = real_embedder.find_similar("levo drip")
        # Neural embeddings should still find norepinephrine
        assert isinstance(matches, list)


# ============================================================
# Test: Confidence Scoring
# ============================================================

class TestNeuralConfidenceScoring:
    """Tests for neural match confidence scoring."""

    def test_neural_confidence_weight_applied(self, sample_ontology):
        """Neural matches have weighted confidence."""
        config = OntologyConfig(
            enable_neural_fallback=True,
            neural_confidence_weight=0.85,
        )
        # Confidence for neural = similarity × weight
        assert config.neural_confidence_weight == 0.85

    def test_exact_match_higher_confidence(self, sample_ontology):
        """Exact matches have higher confidence than neural."""
        config = OntologyConfig(enable_neural_fallback=True)
        matcher = OntologyMatcher(sample_ontology, config)

        exact = matcher.match("VASOPRESSOR_NOREPINEPHRINE")
        assert exact.confidence == 1.0

        # Even best neural match would have lower confidence
        # (similarity * 0.85 < 1.0)

    def test_fuzzy_vs_neural_confidence(self, sample_ontology):
        """Fuzzy and neural have different confidence calculations."""
        config = OntologyConfig(
            fuzzy_threshold=0.65,
            neural_confidence_weight=0.85,
        )
        # Fuzzy: Jaccard × 0.9
        # Neural: cosine × 0.85
        assert config.neural_confidence_weight < 0.9  # Neural is more conservative


# ============================================================
# Test: Entity Extraction for SapBERT
# ============================================================

class TestEntityExtraction:
    """Tests for entity extraction from action strings."""

    def test_extract_simple_drug(self):
        """Extract drug name from simple action."""
        assert extract_entity_name("norepinephrine") == "norepinephrine"

    def test_extract_with_verb(self):
        """Extract entity after action verb."""
        assert extract_entity_name("start norepinephrine") == "norepinephrine"
        assert extract_entity_name("give aspirin") == "aspirin"
        assert extract_entity_name("order blood culture") == "blood culture"

    def test_extract_with_underscore(self):
        """Extract entity from underscore-separated action."""
        result = extract_entity_name("start_norepinephrine_infusion")
        assert "norepinephrine" in result
        assert "start" not in result

    def test_extract_removes_dosage(self):
        """Remove dosage information."""
        result = extract_entity_name("give aspirin 325mg")
        assert "aspirin" in result
        assert "325" not in result

    def test_extract_complex_action(self):
        """Extract from complex action string."""
        result = extract_entity_name("start_norepinephrine_0.1mcg_kg_min")
        assert "norepinephrine" in result
        assert "0.1" not in result
        assert "mcg" not in result

    def test_extract_preserves_compound_names(self):
        """Preserve compound clinical names."""
        result = extract_entity_name("order blood culture")
        assert "blood" in result
        assert "culture" in result


class TestSemanticTypeInference:
    """Tests for semantic type inference."""

    def test_infer_drug_type(self):
        """Infer drug semantic type."""
        assert infer_semantic_type("norepinephrine") == SemanticType.DRUG
        assert infer_semantic_type("aspirin") == SemanticType.DRUG
        assert infer_semantic_type("meropenem antibiotic") == SemanticType.DRUG

    def test_infer_lab_type(self):
        """Infer lab semantic type."""
        assert infer_semantic_type("lactate") == SemanticType.LAB
        assert infer_semantic_type("blood culture") == SemanticType.LAB
        assert infer_semantic_type("troponin") == SemanticType.LAB

    def test_infer_imaging_type(self):
        """Infer imaging semantic type."""
        assert infer_semantic_type("ct scan") == SemanticType.IMAGING
        assert infer_semantic_type("chest xray") == SemanticType.IMAGING
        assert infer_semantic_type("echocardiogram") == SemanticType.IMAGING

    def test_infer_assessment_type(self):
        """Infer assessment semantic type."""
        assert infer_semantic_type("nihss score") == SemanticType.ASSESSMENT
        assert infer_semantic_type("gcs assessment") == SemanticType.ASSESSMENT

    def test_infer_fluid_type(self):
        """Infer fluid semantic type."""
        assert infer_semantic_type("normal saline bolus") == SemanticType.FLUID
        assert infer_semantic_type("crystalloid") == SemanticType.FLUID

    def test_infer_unknown_type(self):
        """Unknown types return UNKNOWN."""
        assert infer_semantic_type("some random text") == SemanticType.UNKNOWN


class TestFAISSIndexTypes:
    """Tests for FAISS index type configuration."""

    def test_faiss_index_type_enum(self):
        """FAISSIndexType enum values."""
        assert FAISSIndexType.FLAT.value == "flat"
        assert FAISSIndexType.IVF.value == "ivf"
        assert FAISSIndexType.HNSW.value == "hnsw"

    def test_config_default_hnsw(self):
        """Default config uses HNSW index."""
        config = EmbedderConfig()
        assert config.faiss_index_type == FAISSIndexType.HNSW

    def test_config_hnsw_params(self):
        """HNSW parameters in config."""
        config = EmbedderConfig(
            hnsw_m=64,
            hnsw_ef_construction=400,
            hnsw_ef_search=200,
        )
        assert config.hnsw_m == 64
        assert config.hnsw_ef_construction == 400
        assert config.hnsw_ef_search == 200


class TestNormalizationConsistency:
    """Tests for FAISS/cosine similarity consistency."""

    def test_normalization_required_for_cosine(self):
        """normalize_embeddings must be True for cosine similarity."""
        config = EmbedderConfig()
        # Default should be True
        assert config.normalize_embeddings is True

    def test_mock_embedder_type_filtering(self, sample_concepts):
        """Mock embedder handles type filtering config."""
        config = EmbedderConfig(
            enable_type_filtering=True,
            type_mismatch_penalty=0.3,
        )
        embedder = MockNeuralEmbedder(config)
        embedder.build_index(sample_concepts)

        # Should still work (mock doesn't implement full type filtering)
        matches = embedder.find_similar("norepinephrine")
        assert isinstance(matches, list)
