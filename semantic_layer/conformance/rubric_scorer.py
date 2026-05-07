"""
Domain-Specific Evidence-Weighted Rubric Scoring.

Extends the single compliance_score from ConformanceReport into a
multi-dimensional, evidence-tiered rubric score per domain (AMEGA-style).

Key concepts:
- EvidenceTier: Classifies constraints by (recommendation_class, evidence_level)
- RubricDimension: 6 evaluation axes (completeness, ordering, timeliness, safety, etc.)
- Domain-specific dimension weights (sepsis prioritizes timeliness; dka prioritizes safety)
- Priority adherence: fraction of top-25% weight constraints satisfied
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set


# --- Enums ---

class EvidenceTier(str, Enum):
    """Evidence tier derived from (recommendation_class, evidence_level)."""
    CRITICAL = "critical"
    STRONG = "strong"
    MODERATE = "moderate"
    DISCRETIONARY = "discretionary"


class RubricDimension(str, Enum):
    """Multi-dimensional rubric axes."""
    COMPLETENESS = "completeness"
    ORDERING = "ordering"
    TIMELINESS = "timeliness"
    SAFETY = "safety"
    EVIDENCE_ADHERENCE = "evidence_adherence"
    CLINICAL_PRIORITY = "clinical_priority"


# --- Configuration ---

@dataclass
class RubricScoringConfig:
    """Configuration for rubric scoring. Defaults provide sensible behavior."""
    enable_evidence_tiers: bool = True
    enable_domain_rubric: bool = True
    enable_priority_scoring: bool = True
    evidence_tier_weights: Dict[str, float] = field(default_factory=lambda: {
        "critical": 1.0,
        "strong": 0.8,
        "moderate": 0.6,
        "discretionary": 0.3,
    })
    recommendation_class_map: Dict[str, float] = field(default_factory=lambda: {
        "I": 1.0,
        "IIa": 0.85,
        "IIb": 0.7,
        "III": 0.4,
    })
    domain_weights: Dict[str, Dict[str, float]] = field(default_factory=dict)
    priority_top_fraction: float = 0.25


# --- Data Structures ---

@dataclass
class ViolationByTier:
    """Violations grouped by evidence tier."""
    tier: EvidenceTier
    violation_count: int
    total_weight: float
    constraint_ids: List[str]


@dataclass
class DomainRubricScore:
    """Full rubric score for a domain."""
    domain: str
    dimension_scores: Dict[str, float]
    evidence_tier_scores: Dict[str, float]
    violations_by_tier: List[ViolationByTier]
    priority_adherence: float
    weighted_composite: float
    tier_breakdown: Dict[str, int]


@dataclass
class RubricReport:
    """Final rubric report composing base ConformanceReport with rubric analysis."""
    base_report: Any
    domain: str
    rubric_score: DomainRubricScore
    evidence_coverage: float
    recommendation_coverage: float
    dimension_weights_used: Dict[str, float]


# --- Domain Weights ---

_DEFAULT_DOMAIN_WEIGHTS: Dict[str, Dict[str, float]] = {
    "sepsis": {
        "completeness": 0.25, "ordering": 0.10, "timeliness": 0.30,
        "safety": 0.15, "evidence_adherence": 0.10, "clinical_priority": 0.10,
    },
    "chest_pain": {
        "completeness": 0.20, "ordering": 0.15, "timeliness": 0.25,
        "safety": 0.20, "evidence_adherence": 0.10, "clinical_priority": 0.10,
    },
    "stroke": {
        "completeness": 0.20, "ordering": 0.15, "timeliness": 0.30,
        "safety": 0.15, "evidence_adherence": 0.10, "clinical_priority": 0.10,
    },
    "dka": {
        "completeness": 0.25, "ordering": 0.15, "timeliness": 0.20,
        "safety": 0.25, "evidence_adherence": 0.10, "clinical_priority": 0.05,
    },
    "aki": {
        "completeness": 0.25, "ordering": 0.10, "timeliness": 0.20,
        "safety": 0.25, "evidence_adherence": 0.10, "clinical_priority": 0.10,
    },
    "heart_failure": {
        "completeness": 0.25, "ordering": 0.15, "timeliness": 0.15,
        "safety": 0.20, "evidence_adherence": 0.15, "clinical_priority": 0.10,
    },
    "general": {
        "completeness": 0.25, "ordering": 0.15, "timeliness": 0.20,
        "safety": 0.20, "evidence_adherence": 0.10, "clinical_priority": 0.10,
    },
}


# --- Evidence Tier Classification ---

# Mapping: (recommendation_class_upper, evidence_level_normalized) -> EvidenceTier
_CRITICAL_EVIDENCE = {"1A", "A"}
_STRONG_CLASS_I_EVIDENCE = {"1B", "B"}
_STRONG_CLASS_IIA_EVIDENCE = {"1A", "A"}
_MODERATE_CLASS_IIA_EVIDENCE = {"1B", "B", "2A"}


def _normalize_evidence(evidence_level: Optional[str]) -> Optional[str]:
    """Normalize evidence level to uppercase form."""
    if not evidence_level:
        return None
    return evidence_level.strip().upper()


def _normalize_rec_class(recommendation_class: Optional[str]) -> Optional[str]:
    """Normalize recommendation class."""
    if not recommendation_class:
        return None
    rc = recommendation_class.strip()
    upper = rc.upper()
    if upper == "I":
        return "I"
    if upper == "IIA":
        return "IIa"
    if upper == "IIB":
        return "IIb"
    if upper == "III":
        return "III"
    return rc


# --- RubricScorer ---

class RubricScorer:
    """Computes domain-specific evidence-weighted rubric scores from ConformanceReport."""

    def __init__(self, config: Optional[RubricScoringConfig] = None):
        self.config = config or RubricScoringConfig()

    def score(
        self,
        report: Any,
        constraints: List[Any],
        domain: str = "general",
    ) -> RubricReport:
        """Score a ConformanceReport with rubric dimensions and evidence tiers.

        Args:
            report: ConformanceReport instance.
            constraints: List of SoftConstraint (or objects with constraint_id, weight,
                         evidence_level, and optionally recommendation_class).
            domain: Clinical domain for weight selection.

        Returns:
            RubricReport with multi-dimensional scores.
        """
        domain_weights = self._get_domain_weights(domain)
        dimension_scores = self.compute_dimension_scores(report, constraints)
        tier_scores, violations_by_tier, tier_breakdown = self._compute_tier_analysis(
            report, constraints
        )
        priority_adherence = self.compute_priority_adherence(report, constraints)
        evidence_coverage = self._compute_evidence_coverage(constraints)
        recommendation_coverage = self._compute_recommendation_coverage(constraints)
        weighted_composite = self._compute_weighted_composite(
            dimension_scores, tier_scores, domain_weights
        )

        rubric_score = DomainRubricScore(
            domain=domain,
            dimension_scores=dimension_scores,
            evidence_tier_scores=tier_scores,
            violations_by_tier=violations_by_tier,
            priority_adherence=priority_adherence,
            weighted_composite=weighted_composite,
            tier_breakdown=tier_breakdown,
        )

        return RubricReport(
            base_report=report,
            domain=domain,
            rubric_score=rubric_score,
            evidence_coverage=evidence_coverage,
            recommendation_coverage=recommendation_coverage,
            dimension_weights_used=domain_weights,
        )

    def classify_evidence_tier(
        self,
        evidence_level: Optional[str],
        recommendation_class: Optional[str],
    ) -> EvidenceTier:
        """Classify a constraint into an evidence tier.

        Classification rules:
        - CRITICAL: Class I + (1A or A)
        - STRONG: Class I + (1B/B) OR Class IIa + (A/1A)
        - MODERATE: Class IIa + (B/1B/2A) OR Class IIb + any
        - DISCRETIONARY: Class III OR evidence 2C/3 OR missing both
        """
        ev = _normalize_evidence(evidence_level)
        rc = _normalize_rec_class(recommendation_class)

        # Discretionary: Class III regardless of evidence
        if rc == "III":
            return EvidenceTier.DISCRETIONARY

        # Discretionary: Low evidence regardless of class
        if ev in ("2C", "3"):
            return EvidenceTier.DISCRETIONARY

        # Critical: Class I + high evidence
        if rc == "I" and ev in _CRITICAL_EVIDENCE:
            return EvidenceTier.CRITICAL

        # Strong: Class I + moderate evidence, or Class IIa + high evidence
        if rc == "I" and ev in _STRONG_CLASS_I_EVIDENCE:
            return EvidenceTier.STRONG
        if rc == "IIa" and ev in _STRONG_CLASS_IIA_EVIDENCE:
            return EvidenceTier.STRONG

        # Moderate: Class IIa + moderate evidence, or Class IIb + any
        if rc == "IIa" and ev in _MODERATE_CLASS_IIA_EVIDENCE:
            return EvidenceTier.MODERATE
        if rc == "IIb":
            return EvidenceTier.MODERATE

        # Class I with unknown evidence → Strong (benefit of the doubt for Class I)
        if rc == "I" and ev is not None:
            return EvidenceTier.STRONG

        # Class IIa with unknown evidence → Moderate
        if rc == "IIa":
            return EvidenceTier.MODERATE

        # Missing both → Discretionary
        if rc is None and ev is None:
            return EvidenceTier.DISCRETIONARY

        # Evidence present but no class → infer from evidence level
        if rc is None and ev is not None:
            if ev in _CRITICAL_EVIDENCE:
                return EvidenceTier.STRONG
            if ev in _STRONG_CLASS_I_EVIDENCE:
                return EvidenceTier.MODERATE
            return EvidenceTier.DISCRETIONARY

        return EvidenceTier.DISCRETIONARY

    def compute_dimension_scores(
        self,
        report: Any,
        constraints: List[Any],
    ) -> Dict[str, float]:
        """Compute per-dimension scores from report and constraints.

        Maps SubScores (completeness, ordering, timeliness, safety) and adds
        evidence_adherence and clinical_priority dimensions.
        """
        scores: Dict[str, float] = {}

        # Extract from SubScores if available
        sub = getattr(report, "sub_scores", None)
        if sub is not None:
            scores["completeness"] = getattr(sub, "completeness", 1.0)
            scores["ordering"] = getattr(sub, "ordering", 1.0)
            scores["timeliness"] = getattr(sub, "timeliness", 1.0)
            scores["safety"] = getattr(sub, "safety", 1.0)
        else:
            # Fallback: derive from compliance_score
            base = getattr(report, "compliance_score", 1.0)
            scores["completeness"] = base
            scores["ordering"] = base
            scores["timeliness"] = base
            scores["safety"] = base

        # Evidence adherence: weighted compliance based on evidence tiers
        scores["evidence_adherence"] = self._compute_evidence_adherence(
            report, constraints
        )

        # Clinical priority
        scores["clinical_priority"] = self.compute_priority_adherence(
            report, constraints
        )

        return scores

    def compute_priority_adherence(
        self,
        report: Any,
        constraints: List[Any],
    ) -> float:
        """Compute fraction of high-priority constraints that are satisfied.

        High-priority = top 25% by weight.
        Satisfied = constraint_id not in violation list.
        """
        if not constraints:
            return 1.0

        weights = [
            (getattr(c, "constraint_id", f"c_{i}"), getattr(c, "weight", 1.0))
            for i, c in enumerate(constraints)
        ]
        weights.sort(key=lambda x: x[1], reverse=True)

        top_n = max(1, int(len(weights) * self.config.priority_top_fraction))
        high_priority_ids = {w[0] for w in weights[:top_n]}

        violated_ids = self._get_violated_constraint_ids(report)
        satisfied = high_priority_ids - violated_ids
        return len(satisfied) / len(high_priority_ids) if high_priority_ids else 1.0

    # --- Private Methods ---

    def _get_domain_weights(self, domain: str) -> Dict[str, float]:
        """Get dimension weights for the given domain."""
        # Check config override first
        if domain in self.config.domain_weights:
            return self.config.domain_weights[domain]
        return _DEFAULT_DOMAIN_WEIGHTS.get(
            domain, _DEFAULT_DOMAIN_WEIGHTS["general"]
        )

    def _compute_weighted_composite(
        self,
        dimension_scores: Dict[str, float],
        tier_scores: Dict[str, float],
        domain_weights: Dict[str, float],
    ) -> float:
        """Compute final weighted composite score."""
        composite = 0.0
        total_weight = 0.0

        for dim, weight in domain_weights.items():
            score = dimension_scores.get(dim, 1.0)
            composite += weight * score
            total_weight += weight

        # Apply tier penalty: reduce composite proportionally to tier violations
        if self.config.enable_evidence_tiers and tier_scores:
            tier_penalty = self._compute_tier_penalty(tier_scores)
            composite *= (1.0 - tier_penalty)

        return composite / total_weight if total_weight > 0 else 0.0

    def _compute_tier_penalty(self, tier_scores: Dict[str, float]) -> float:
        """Compute an overall penalty from evidence tier violations.

        Penalty = weighted average of (1 - tier_score) across tiers.
        """
        tier_weights = self.config.evidence_tier_weights
        penalty_sum = 0.0
        weight_sum = 0.0

        for tier_name, tier_score in tier_scores.items():
            tw = tier_weights.get(tier_name, 0.3)
            penalty_sum += tw * (1.0 - tier_score)
            weight_sum += tw

        return penalty_sum / weight_sum if weight_sum > 0 else 0.0

    def _compute_tier_analysis(
        self,
        report: Any,
        constraints: List[Any],
    ) -> tuple:
        """Compute per-tier scores, violations, and tier breakdown.

        Returns:
            (tier_scores, violations_by_tier, tier_breakdown)
        """
        # Classify constraints by tier
        tier_constraints: Dict[str, List[Any]] = {t.value: [] for t in EvidenceTier}
        for c in constraints:
            ev = getattr(c, "evidence_level", None)
            rc = getattr(c, "recommendation_class", None)
            tier = self.classify_evidence_tier(ev, rc)
            tier_constraints[tier.value].append(c)

        violated_ids = self._get_violated_constraint_ids(report)
        violation_weights = self._get_violation_weight_map(report)

        tier_scores: Dict[str, float] = {}
        violations_by_tier: List[ViolationByTier] = []
        tier_breakdown: Dict[str, int] = {}

        for tier_val, cs in tier_constraints.items():
            tier_breakdown[tier_val] = len(cs)
            if not cs:
                tier_scores[tier_val] = 1.0
                continue

            violated_in_tier = []
            total_violation_weight = 0.0
            for c in cs:
                cid = getattr(c, "constraint_id", "")
                if cid in violated_ids:
                    violated_in_tier.append(cid)
                    total_violation_weight += violation_weights.get(
                        cid, getattr(c, "weight", 1.0)
                    )

            tier_scores[tier_val] = 1.0 - (len(violated_in_tier) / len(cs))
            if violated_in_tier:
                violations_by_tier.append(ViolationByTier(
                    tier=EvidenceTier(tier_val),
                    violation_count=len(violated_in_tier),
                    total_weight=total_violation_weight,
                    constraint_ids=violated_in_tier,
                ))

        return tier_scores, violations_by_tier, tier_breakdown

    def _compute_evidence_adherence(
        self,
        report: Any,
        constraints: List[Any],
    ) -> float:
        """Compute evidence-weighted adherence score.

        Higher-tier constraints contribute more to the score.
        """
        if not constraints:
            return 1.0

        violated_ids = self._get_violated_constraint_ids(report)
        tier_weights = self.config.evidence_tier_weights

        total_weighted = 0.0
        satisfied_weighted = 0.0

        for c in constraints:
            ev = getattr(c, "evidence_level", None)
            rc = getattr(c, "recommendation_class", None)
            tier = self.classify_evidence_tier(ev, rc)
            tw = tier_weights.get(tier.value, 0.3)
            total_weighted += tw

            cid = getattr(c, "constraint_id", "")
            if cid not in violated_ids:
                satisfied_weighted += tw

        return satisfied_weighted / total_weighted if total_weighted > 0 else 1.0

    def _compute_evidence_coverage(self, constraints: List[Any]) -> float:
        """Fraction of constraints that have an evidence_level."""
        if not constraints:
            return 0.0
        with_ev = sum(
            1 for c in constraints if getattr(c, "evidence_level", None) is not None
        )
        return with_ev / len(constraints)

    def _compute_recommendation_coverage(self, constraints: List[Any]) -> float:
        """Fraction of constraints that have a recommendation_class."""
        if not constraints:
            return 0.0
        with_rc = sum(
            1 for c in constraints
            if getattr(c, "recommendation_class", None) is not None
        )
        return with_rc / len(constraints)

    def _get_violated_constraint_ids(self, report: Any) -> Set[str]:
        """Extract violated constraint IDs from report."""
        violations = getattr(report, "constraint_violations", [])
        return {getattr(v, "constraint_id", "") for v in violations}

    def _get_violation_weight_map(self, report: Any) -> Dict[str, float]:
        """Map constraint_id -> violation weight from report."""
        violations = getattr(report, "constraint_violations", [])
        return {
            getattr(v, "constraint_id", ""): getattr(v, "weight", 1.0)
            for v in violations
        }
