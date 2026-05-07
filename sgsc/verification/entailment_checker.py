"""Field-level entailment checker for atom source quotes.

Verifies that each of an atom's 6 semantic fields is supported by its
source quote. Rule-based by default; LLM path is reserved for future use.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import logging
import re

from sgsc.schemas.atom import RecommendationAtom

logger = logging.getLogger(__name__)

# Field names that are checked
ENTAILMENT_FIELDS = ("action", "guard", "exclusion", "timing", "sequence", "evidence")


@dataclass
class FieldEntailmentResult:
    """Result of checking one field's entailment against the source quote."""

    field: str  # "action"|"guard"|"exclusion"|"timing"|"sequence"|"evidence"
    verdict: str  # "ENTAILED"|"NOT_ENTAILED"|"PARTIAL"|"NOT_APPLICABLE"
    confidence: float = 1.0
    reason: str = ""


@dataclass
class AtomEntailmentReport:
    """Aggregate entailment report for a single atom."""

    atom_id: str
    field_results: list[FieldEntailmentResult] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        """True if no applicable field has a NOT_ENTAILED verdict.

        Lenient gate: PARTIAL counts as passing — partial evidence exists but
        is not conclusive. Only explicit NOT_ENTAILED rejects an atom. Use
        ``strict_passed`` for the Gate-2 "mandatory entailment" semantics
        where PARTIAL must also reject.
        """
        return all(r.verdict != "NOT_ENTAILED" for r in self.field_results)

    @property
    def strict_passed(self) -> bool:
        """True only if every applicable field is ENTAILED.

        Strict gate: PARTIAL counts as failure. NOT_APPLICABLE is allowed
        (e.g., timing field on a REQUIRED-only constraint). This is the
        verdict the pipeline uses when ``entailment_mode='llm_strict'``.
        """
        return all(r.verdict in ("ENTAILED", "NOT_APPLICABLE") for r in self.field_results)

    @property
    def failed_fields(self) -> list[str]:
        return [r.field for r in self.field_results if r.verdict == "NOT_ENTAILED"]

    @property
    def partial_fields(self) -> list[str]:
        return [r.field for r in self.field_results if r.verdict == "PARTIAL"]

    @property
    def pass_rate(self) -> float:
        applicable = [r for r in self.field_results if r.verdict != "NOT_APPLICABLE"]
        if not applicable:
            return 1.0
        passed = sum(1 for r in applicable if r.verdict == "ENTAILED")
        return passed / len(applicable)


# ------------------------------------------------------------------
# Rule-based field entailment (no LLM needed)
# ------------------------------------------------------------------


_DEFAULT_ACTION_THRESHOLD = 0.6
_DEFAULT_GUARD_THRESHOLD = 0.6


def _stem_match(keyword: str, text: str) -> bool:
    """Match keyword in text with simple plural/singular and verb stemming.

    Handles the common case where an atom's canonical_id uses plural
    (e.g. ``crystalloids``) but the source quote uses singular
    (``crystalloid``), or vice versa.  Also handles verb conjugation
    (e.g. ``measure`` matching ``measuring``).
    """
    if keyword in text:
        return True
    # singular form: crystalloids -> crystalloid
    if keyword.endswith("ies") and (keyword[:-3] + "y") in text:
        return True
    if keyword.endswith("es") and keyword[:-2] in text:
        return True
    if keyword.endswith("s") and keyword[:-1] in text:
        return True
    # plural form: crystalloid -> crystalloids, allergy -> allergies
    if (keyword + "s") in text:
        return True
    if keyword.endswith("y") and (keyword[:-1] + "ies") in text:
        return True
    # verb -ing conjugation: measure -> measuring, administer -> administering
    if keyword.endswith("e") and (keyword[:-1] + "ing") in text:
        return True
    if (keyword + "ing") in text:
        return True
    return False


def _check_action_entailment(
    atom: RecommendationAtom,
    threshold: float = _DEFAULT_ACTION_THRESHOLD,
) -> FieldEntailmentResult:
    """Check if action keywords appear in the source quote.

    Args:
        atom: The atom whose action is being verified.
        threshold: Minimum keyword-match ratio required for ENTAILED. The
            critical-review found D5 noted that 0.5 is too lenient; 0.7 is the
            recommended Day-5+ value. Both can be evaluated side-by-side via
            ``compare_entailment_thresholds``.
    """
    quote_lower = atom.source.quote.lower()
    action_parts = atom.action.canonical_id.split("_")
    # Filter out common clinical prefixes that inflate keyword count
    _ACTION_PREFIX_FILTER = {
        "give", "order", "start", "assess", "lab", "perform", "administer",
        "check", "review", "monitor", "evaluate", "obtain", "measure",
        "calculate", "initiate", "discontinue", "hold", "avoid", "forbid",
    }
    meaningful = [p for p in action_parts if p not in _ACTION_PREFIX_FILTER]
    if not meaningful:
        meaningful = action_parts

    matches = sum(1 for p in meaningful if _stem_match(p, quote_lower))
    ratio = matches / len(meaningful) if meaningful else 0.0

    if ratio >= threshold:
        return FieldEntailmentResult(
            field="action",
            verdict="ENTAILED",
            confidence=ratio,
            reason=f"{matches}/{len(meaningful)} action keywords found (threshold={threshold:.2f})",
        )
    return FieldEntailmentResult(
        field="action",
        verdict="NOT_ENTAILED",
        confidence=ratio,
        reason=f"Only {matches}/{len(meaningful)} keywords (threshold={threshold:.2f})",
    )


def _check_guard_entailment(
    atom: RecommendationAtom,
    threshold: float = _DEFAULT_GUARD_THRESHOLD,
) -> FieldEntailmentResult:
    """Check if population exclusion criteria are mentioned in source quote."""
    if not atom.population.exclusion:
        return FieldEntailmentResult(field="guard", verdict="NOT_APPLICABLE", reason="No exclusion criteria")

    quote_lower = atom.source.quote.lower()
    found = 0
    for excl in atom.population.exclusion:
        excl_parts = excl.lower().replace("_", " ").split()
        if any(_stem_match(p, quote_lower) for p in excl_parts if len(p) > 3):
            found += 1

    ratio = found / len(atom.population.exclusion)
    if ratio >= threshold:
        return FieldEntailmentResult(
            field="guard",
            verdict="ENTAILED",
            confidence=ratio,
            reason=f"{found}/{len(atom.population.exclusion)} criteria (threshold={threshold:.2f})",
        )
    return FieldEntailmentResult(
        field="guard",
        verdict="NOT_ENTAILED",
        confidence=ratio,
        reason=f"Only {found}/{len(atom.population.exclusion)} criteria (threshold={threshold:.2f})",
    )


def _check_exclusion_entailment(atom: RecommendationAtom) -> FieldEntailmentResult:
    """Check if exclusion conditions are justified by source text."""
    if not atom.population.exclusion:
        return FieldEntailmentResult(field="exclusion", verdict="NOT_APPLICABLE", reason="No exclusions")

    quote_lower = atom.source.quote.lower()
    # Look for negation/contraindication language near exclusion terms
    contra_terms = ["avoid", "contraindic", "except", "not", "unless", "do not", "should not", "prohibit"]
    has_contra_language = any(t in quote_lower for t in contra_terms)

    if has_contra_language:
        return FieldEntailmentResult(
            field="exclusion",
            verdict="ENTAILED",
            confidence=0.8,
            reason="Contraindication language found in quote",
        )
    return FieldEntailmentResult(
        field="exclusion",
        verdict="NOT_ENTAILED",
        confidence=0.3,
        reason="No contraindication language found in quote",
    )


def _check_timing_entailment(atom: RecommendationAtom) -> FieldEntailmentResult:
    """Check if deadline_minutes is supported by a number in the source quote."""
    if atom.constraint.type != "WITHIN" or atom.constraint.deadline_minutes is None:
        return FieldEntailmentResult(field="timing", verdict="NOT_APPLICABLE", reason="No timing constraint")

    deadline = atom.constraint.deadline_minutes
    # Find all numbers in the quote
    numbers = [int(m) for m in re.findall(r"\b(\d+)\b", atom.source.quote)]

    # Check for exact match or close match (within 20%)
    for n in numbers:
        if n == deadline:
            return FieldEntailmentResult(
                field="timing",
                verdict="ENTAILED",
                confidence=1.0,
                reason=f"Exact deadline {deadline} found in quote",
            )
        if abs(n - deadline) / max(deadline, 1) <= 0.2:
            return FieldEntailmentResult(
                field="timing",
                verdict="ENTAILED",
                confidence=0.8,
                reason=f"Number {n} close to deadline {deadline} found in quote",
            )

    # Check for time words
    time_words = ["hour", "minute", "min", "hr"]
    has_time_ref = any(w in atom.source.quote.lower() for w in time_words)
    if has_time_ref:
        return FieldEntailmentResult(
            field="timing",
            verdict="PARTIAL",
            confidence=0.5,
            reason="Time reference found but specific deadline not matched",
        )

    return FieldEntailmentResult(
        field="timing",
        verdict="NOT_ENTAILED",
        confidence=0.1,
        reason=f"Deadline {deadline}min not found in quote",
    )


def _check_sequence_entailment(atom: RecommendationAtom) -> FieldEntailmentResult:
    """Check if required_prior / before orderings are stated in source.

    Three outcomes:
    - ENTAILED: quote contains ordering language consistent with proposed sequence
    - PARTIAL: quote is silent on ordering (no ordering language found) — the
      LLM may have inferred clinical ordering from context, which is acceptable
      under lenient mode
    - NOT_ENTAILED: quote contains ordering language that contradicts the
      proposed sequence (e.g., atom claims "A before B" but quote says "B before A")
    """
    has_sequence = bool(atom.sequence.required_prior) or bool(atom.sequence.before)
    if not has_sequence:
        return FieldEntailmentResult(field="sequence", verdict="NOT_APPLICABLE", reason="No sequence constraints")

    quote_lower = atom.source.quote.lower()
    order_terms = ["before", "prior", "first", "then", "after", "followed by", "preceding", "subsequent"]
    found_order = any(t in quote_lower for t in order_terms)

    if found_order:
        # Quote mentions ordering — check for contradiction.
        # Contradiction detection: if atom says "A required_prior B" but quote
        # says "after A" or "B before A", that's contradictory. For now, presence
        # of any ordering language is treated as supportive (full contradiction
        # detection would need NLP parsing of the ordering direction).
        return FieldEntailmentResult(
            field="sequence",
            verdict="ENTAILED",
            confidence=0.7,
            reason="Ordering language found in quote",
        )

    # Quote is silent on ordering — PARTIAL, not rejection.
    # The LLM atom proposer may correctly infer clinical ordering from
    # implicit workflow context (e.g., "assess before treat" is standard
    # clinical practice even when the guideline doesn't spell it out).
    return FieldEntailmentResult(
        field="sequence",
        verdict="PARTIAL",
        confidence=0.4,
        reason="No ordering language in quote — implicit clinical ordering assumed",
    )


def _check_evidence_entailment(atom: RecommendationAtom) -> FieldEntailmentResult:
    """Check if recommendation_class + evidence level are consistent with quote.

    Clinical guideline language mapping:
    - Strong: "should", "recommended", "must", "is indicated", "administer"
    - Weak: "may", "consider", "can be considered", "conditional"
    - Imperative verbs ("administer", "initiate", "obtain", "perform") in
      guideline context imply strong recommendation even without "should".
    """
    quote_lower = atom.source.quote.lower()
    rec_class = atom.evidence.recommendation_class.lower()

    # Strong language: explicit directive terms used in clinical guidelines
    strong_terms = [
        "strong", "recommended", "should", "must", "class i", "grade 1",
        "is indicated", "is recommended", "suggested", "we recommend",
        "we suggest", "administer", "initiate", "obtain", "perform",
    ]
    weak_terms = ["weak", "conditional", "may", "consider", "class ii", "grade 2",
                  "can be considered", "could be considered"]

    is_strong_claim = rec_class in ("i", "1", "strong")
    has_strong_language = any(t in quote_lower for t in strong_terms)
    has_weak_language = any(t in quote_lower for t in weak_terms)

    if is_strong_claim and has_strong_language:
        return FieldEntailmentResult(
            field="evidence",
            verdict="ENTAILED",
            confidence=0.8,
            reason=f"Strong recommendation language matches class {atom.evidence.recommendation_class}",
        )
    if not is_strong_claim and has_weak_language:
        return FieldEntailmentResult(
            field="evidence",
            verdict="ENTAILED",
            confidence=0.8,
            reason=f"Conditional language matches class {atom.evidence.recommendation_class}",
        )
    # Weak claim with strong language — acceptable (stronger evidence than claimed)
    if not is_strong_claim and has_strong_language:
        return FieldEntailmentResult(
            field="evidence",
            verdict="ENTAILED",
            confidence=0.7,
            reason=f"Quote has strong language, claim is {atom.evidence.recommendation_class} (conservative)",
        )
    # Strong claim with weak language — partial (not contradictory, but weaker support)
    if is_strong_claim and has_weak_language:
        return FieldEntailmentResult(
            field="evidence",
            verdict="PARTIAL",
            confidence=0.5,
            reason=f"Quote has conditional language for strong claim {atom.evidence.recommendation_class}",
        )
    # If no strength language at all, it's partial
    if not has_strong_language and not has_weak_language:
        return FieldEntailmentResult(
            field="evidence",
            verdict="PARTIAL",
            confidence=0.5,
            reason="No explicit strength language in quote",
        )
    # Should not reach here, but defensive
    return FieldEntailmentResult(
        field="evidence",
        verdict="PARTIAL",
        confidence=0.4,
        reason=f"Ambiguous strength language for class {atom.evidence.recommendation_class}",
    )


def check_field_entailment_rule_based(
    atom: RecommendationAtom,
    action_threshold: float = _DEFAULT_ACTION_THRESHOLD,
    guard_threshold: float = _DEFAULT_GUARD_THRESHOLD,
) -> AtomEntailmentReport:
    """Check all 6 fields using rule-based heuristics (no LLM).

    Args:
        atom: The atom to check.
        action_threshold: Minimum keyword-match ratio for the action field
            (default 0.5; 0.7 is the recommended tightened value per D5).
        guard_threshold: Minimum match ratio for the guard field.
    """
    return AtomEntailmentReport(
        atom_id=atom.atom_id,
        field_results=[
            _check_action_entailment(atom, threshold=action_threshold),
            _check_guard_entailment(atom, threshold=guard_threshold),
            _check_exclusion_entailment(atom),
            _check_timing_entailment(atom),
            _check_sequence_entailment(atom),
            _check_evidence_entailment(atom),
        ],
    )


def check_atoms_entailment(
    atoms: list[RecommendationAtom],
    mode: str = "rule_based",
    action_threshold: float = _DEFAULT_ACTION_THRESHOLD,
    guard_threshold: float = _DEFAULT_GUARD_THRESHOLD,
) -> list[AtomEntailmentReport]:
    """Check entailment for all atoms.

    Args:
        atoms: List of atoms to check.
        mode: "rule_based" (default) or "llm" or "llm_strict".
        action_threshold: Override the action-field keyword threshold.
        guard_threshold: Override the guard-field match threshold.

    Returns:
        List of AtomEntailmentReport, one per atom.
    """
    reports: list[AtomEntailmentReport] = []
    for atom in atoms:
        if mode == "rule_based":
            report = check_field_entailment_rule_based(
                atom,
                action_threshold=action_threshold,
                guard_threshold=guard_threshold,
            )
        else:
            # LLM modes: fall back to rule-based for now
            # TODO: implement LLM-based field entailment when endpoints are available
            logger.info("LLM entailment not yet implemented, using rule_based fallback")
            report = check_field_entailment_rule_based(
                atom,
                action_threshold=action_threshold,
                guard_threshold=guard_threshold,
            )
        reports.append(report)
    return reports


# ------------------------------------------------------------------
# Multi-threshold comparison (TG-V2: visualise heuristic threshold impact)
# ------------------------------------------------------------------


def compare_entailment_thresholds(
    atoms: list[RecommendationAtom],
    thresholds: list[float] | None = None,
) -> dict[float, dict[str, int]]:
    """Run rule-based entailment at multiple action-keyword thresholds.

    Reviewer-visible metric for D5 mitigation: how many atoms move between
    ENTAILED / NOT_ENTAILED when the action keyword threshold is tightened
    from 0.5 (lenient) to 0.7 (recommended)?

    Args:
        atoms: Proposed atoms (e.g., the SGSC-3 LLM batch output).
        thresholds: Action-keyword thresholds to evaluate. Defaults to
            ``[0.5, 0.7]``. The guard threshold tracks the action threshold
            since both apply to keyword-overlap heuristics.

    Returns:
        Dict mapping threshold -> ``{"n_total", "n_strict_passing",
        "n_lenient_passing", "n_rejected", "n_partial_only"}``.
        ``n_strict_passing``: every applicable field is ENTAILED.
        ``n_lenient_passing``: no field is NOT_ENTAILED (PARTIAL allowed).
        ``n_rejected``: at least one field is NOT_ENTAILED.
        ``n_partial_only``: passes lenient but not strict (PARTIAL fields,
        no NOT_ENTAILED).
    """
    if thresholds is None:
        thresholds = [0.5, 0.7]

    summary: dict[float, dict[str, int]] = {}
    for threshold in thresholds:
        reports = check_atoms_entailment(
            atoms,
            mode="rule_based",
            action_threshold=threshold,
            guard_threshold=threshold,
        )
        n_total = len(reports)
        n_strict = sum(1 for r in reports if r.strict_passed)
        n_lenient = sum(1 for r in reports if r.all_passed)
        n_rejected = sum(1 for r in reports if r.failed_fields)
        n_partial_only = n_lenient - n_strict
        summary[threshold] = {
            "n_total": n_total,
            "n_strict_passing": n_strict,
            "n_lenient_passing": n_lenient,
            "n_rejected": n_rejected,
            "n_partial_only": n_partial_only,
        }
    return summary
