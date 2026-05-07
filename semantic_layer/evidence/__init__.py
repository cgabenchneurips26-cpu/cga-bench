"""Evidence verification layer for CGA-Bench retrieval grounding."""

from .clause_index import CanonicalClause, ClauseIndex, build_clause_index_from_cpg
from .metrics import (
    EvidenceMetricsReport,
    clause_recall_at_k,
    compliance_delta_vs_oracle,
    compute_evidence_metrics,
    evidence_precision_at_k,
    hallucinated_clause_rate,
    provenance_verified_rate,
    quote_span_f1,
    version_correctness,
)
from .provenance import (
    ProvenanceRecord,
    QuoteSpan,
    compute_quote_hash,
    extract_quote_span,
    verify_provenance,
)
from .schema import EvidenceBundle, EvidenceRecord, validate_evidence_record

__all__ = [
    "CanonicalClause",
    "ClauseIndex",
    "build_clause_index_from_cpg",
    "QuoteSpan",
    "ProvenanceRecord",
    "compute_quote_hash",
    "verify_provenance",
    "extract_quote_span",
    "EvidenceRecord",
    "EvidenceBundle",
    "validate_evidence_record",
    "evidence_precision_at_k",
    "clause_recall_at_k",
    "quote_span_f1",
    "provenance_verified_rate",
    "hallucinated_clause_rate",
    "version_correctness",
    "compliance_delta_vs_oracle",
    "EvidenceMetricsReport",
    "compute_evidence_metrics",
]
