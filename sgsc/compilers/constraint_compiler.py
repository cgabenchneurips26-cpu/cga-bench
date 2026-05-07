"""Atom -> DerivedConstraint bridge.

Converts ``RecommendationAtom`` instances into ``DerivedConstraint``
dataclass instances compatible with the existing ``cpg_model.constraint_derivation``
module.
"""

from __future__ import annotations

from sgsc.schemas.atom import RecommendationAtom

from cga_bench.cpg_model.constraint_derivation import DerivedConstraint

# ------------------------------------------------------------------
# Authority classification (mirrors constraint_derivation.py logic)
# ------------------------------------------------------------------

_HIGH_AUTHORITY_CLASSES = frozenset({"I", "1", "IIa", "2a"})
_HIGH_AUTHORITY_LEVELS = frozenset({"A", "B", "B-R", "B-NR"})


def _classify_authority(
    recommendation_class: str,
    evidence_level: str,
    source_guideline: str,
) -> str:
    """Classify authority tier based on recommendation class and evidence level.

    Returns 'high' if Class I/IIa AND Level A/B, else 'low'.
    """
    cls_high = recommendation_class in _HIGH_AUTHORITY_CLASSES
    lvl_high = evidence_level in _HIGH_AUTHORITY_LEVELS
    if cls_high and lvl_high:
        return "high"
    return "low"


# ------------------------------------------------------------------
# Severity mapping
# ------------------------------------------------------------------

_CONSTRAINT_TYPE_SEVERITY: dict[str, str] = {
    "FORBIDDEN": "CRITICAL",
    "REQUIRED": "HIGH",
    "WITHIN": "HIGH",
    "BEFORE": "MODERATE",
    "EXPECTED": "LOW",
}


def _evidence_to_severity(constraint_type: str, evidence_level: str) -> str:
    """Map constraint type and evidence level to severity."""
    base = _CONSTRAINT_TYPE_SEVERITY.get(constraint_type, "MODERATE")
    # Downgrade severity for low-quality evidence
    if evidence_level in ("C", "D", "C-LD", "C-EO"):
        if base == "CRITICAL":
            return "HIGH"
        if base == "HIGH":
            return "MODERATE"
    return base


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def atom_to_derived_constraint(atom: RecommendationAtom) -> DerivedConstraint:
    """Convert a RecommendationAtom into a DerivedConstraint with provenance.

    The output ``DerivedConstraint`` is a plain ``@dataclass`` from
    ``cpg_model.constraint_derivation`` — not a Pydantic model.
    """
    return DerivedConstraint(
        constraint_type=atom.constraint.type,
        actions=[atom.action.canonical_id],
        provenance=f"sgsc:atom:{atom.atom_id}:source:{atom.source.guideline_id}",
        evidence=f"{atom.source.section} (page {atom.source.page or 'N/A'})",
        severity=_evidence_to_severity(atom.constraint.type, atom.evidence.level),
        description=atom.source.quote[:200],
        condition_met="population_criteria" if atom.population.exclusion else "unconditional",
        is_conditional=len(atom.population.exclusion) > 0,
        recommendation_class=atom.evidence.recommendation_class,
        evidence_level=atom.evidence.level,
        source_guideline=atom.source.guideline_id,
        authority_tier=_classify_authority(
            atom.evidence.recommendation_class,
            atom.evidence.level,
            atom.source.guideline_id,
        ),
    )


def atoms_to_derived_constraints(
    atoms: list[RecommendationAtom],
) -> list[DerivedConstraint]:
    """Convert a list of atoms into DerivedConstraint instances."""
    return [atom_to_derived_constraint(a) for a in atoms]
