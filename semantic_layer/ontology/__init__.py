"""Clinical Ontology Layer for multi-level semantic abstraction.

Implements SNOMED-CT-inspired IS-A hierarchy for clinical actions,
enabling subsumption-based matching and multi-level conformance checking.

Architecture follows:
- Dwyer et al. (2025): Ontology-informed event log generation
- Leonardi et al. (2018): Multi-level abstraction in medical process mining
- SapBERT pattern: Embedding-ready concept representations
- Entity Linking (EL) / Concept Normalization patterns

Abstraction Levels:
  L0: Raw events (e.g., give_norepinephrine_0.1mcg_kg_min)
  L1: Normalized actions (e.g., start_vasopressor_norepinephrine)
  L2: Semantic categories (e.g., VASOPRESSOR_SUPPORT)
  L3: Clinical goals (e.g., HEMODYNAMIC_RESUSCITATION)
  L4: Care pathway phases (e.g., SEPSIS_HOUR1_BUNDLE)

Architectural Separation (EL-inspired):
  1. Mapper: "What concept is this?" (Entity Linking)
     - ConceptMapper with neural embeddings + conformal prediction
  2. Policy: "Is it allowed/forbidden/mandatory?" (Conformance)
     - ClinicalPolicy with patient context evaluation
"""
from .concept import (
    AbstractionLevel,
    ClinicalConcept,
    ConceptRelation,
    MatchResult,
)
from .clinical_ontology import (
    ClinicalOntology,
    OntologyConfig,
    OntologyMatcher,
    MatchStrategy,
)
from .neural_embedder import (
    EmbedderConfig,
    EmbeddingMatch,
    EmbeddingModel,
    FAISSIndexType,
    IndexStats,
    MockNeuralEmbedder,
    NeuralEmbedder,
    SemanticType,
    extract_entity_name,
    get_embedder,
    infer_semantic_type,
)
from .conformal_matcher import (
    ConformalConfig,
    ConformalMatcher,
    PredictionSet,
    CalibrationResult,
    SiblingReranker,
    EvaluationMetrics,
    evaluate_matcher,
    print_evaluation_report,
)
from .mapper import (
    ConceptMapper,
    MapperConfig,
    MappingResult,
    MappingStrategy,
    UncertaintyLevel,
    create_mapper,
)
from .policy import (
    ClinicalPolicy,
    PolicyConfig,
    PolicyDecision,
    PolicyStatus,
    PolicyConstraint,
    ConstraintType,
    Severity,
    PatientContext,
    AllergyMapping,
    ComorbidityMapping,
    DrugInteraction,
    ClinicalStateRule,
    create_default_policy,
    create_rv_trap_policy,
)
from .benchmark_init import (
    SemanticLayerInitializer,
    SemanticLayerConfig,
    InitializationStats,
    InitializationPhase,
    QueryExecutionLog,
    create_initializer_for_runner,
)
from .cross_encoder_reranker import (
    CrossEncoderReranker,
    MockCrossEncoderReranker,
    RerankerConfig,
    RerankerMode,
    RerankCandidate,
    RerankResult,
    TwoStageMatcher,
    get_reranker,
)
from .hard_negative_miner import (
    HardNegativeMiner,
    HardNegative,
    MiningConfig,
    NegativeType,
    TrainingTriple,
    CGA_TYPE_TRAPS,
    CGA_BRAND_MAPPINGS,
    create_cga_hard_negatives,
)
from .mondrian_conformal import (
    MondrianConformalMatcher,
    MondrianConfig,
    MondrianPredictionSet,
    MondrianCalibrationResult,
    TypeCalibration,
    UncertaintyLevel as MondrianUncertaintyLevel,
    calibrate_mondrian_from_goldset,
)
from .anchor_normalizer import (
    AnchorBasedNormalizer,
    NormalizationResult,
)

__all__ = [
    # Core concepts
    "AbstractionLevel",
    "ClinicalConcept",
    "ConceptRelation",
    "MatchResult",
    # Ontology
    "ClinicalOntology",
    "OntologyConfig",
    "OntologyMatcher",
    "MatchStrategy",
    # Neural embeddings
    "EmbedderConfig",
    "EmbeddingMatch",
    "EmbeddingModel",
    "FAISSIndexType",
    "IndexStats",
    "MockNeuralEmbedder",
    "NeuralEmbedder",
    "SemanticType",
    "extract_entity_name",
    "get_embedder",
    "infer_semantic_type",
    # Conformal prediction
    "ConformalConfig",
    "ConformalMatcher",
    "PredictionSet",
    "CalibrationResult",
    "SiblingReranker",
    "EvaluationMetrics",
    "evaluate_matcher",
    "print_evaluation_report",
    # Mapper (Entity Linking)
    "ConceptMapper",
    "MapperConfig",
    "MappingResult",
    "MappingStrategy",
    "UncertaintyLevel",
    "create_mapper",
    # Policy (Conformance)
    "ClinicalPolicy",
    "PolicyConfig",
    "PolicyDecision",
    "PolicyStatus",
    "PolicyConstraint",
    "ConstraintType",
    "Severity",
    "PatientContext",
    "AllergyMapping",
    "ComorbidityMapping",
    "DrugInteraction",
    "ClinicalStateRule",
    "create_default_policy",
    "create_rv_trap_policy",
    # Benchmark initialization
    "SemanticLayerInitializer",
    "SemanticLayerConfig",
    "InitializationStats",
    "InitializationPhase",
    "QueryExecutionLog",
    "create_initializer_for_runner",
    # Cross-encoder reranking (Two-stage EL)
    "CrossEncoderReranker",
    "MockCrossEncoderReranker",
    "RerankerConfig",
    "RerankerMode",
    "RerankCandidate",
    "RerankResult",
    "TwoStageMatcher",
    "get_reranker",
    # Hard negative mining
    "HardNegativeMiner",
    "HardNegative",
    "MiningConfig",
    "NegativeType",
    "TrainingTriple",
    "CGA_TYPE_TRAPS",
    "CGA_BRAND_MAPPINGS",
    "create_cga_hard_negatives",
    # Mondrian conformal prediction
    "MondrianConformalMatcher",
    "MondrianConfig",
    "MondrianPredictionSet",
    "MondrianCalibrationResult",
    "TypeCalibration",
    "MondrianUncertaintyLevel",
    "calibrate_mondrian_from_goldset",
    # Anchor-based normalization
    "AnchorBasedNormalizer",
    "NormalizationResult",
]
