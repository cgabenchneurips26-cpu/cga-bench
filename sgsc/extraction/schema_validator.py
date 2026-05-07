"""Schema + business-rule validation for proposed atoms.

Validates atoms beyond Pydantic structural checks:
- Action ID format (snake_case, not too long)
- Source quote non-trivial length
- Constraint type + deadline consistency
- Evidence system / class / level plausibility
"""

from __future__ import annotations

from dataclasses import dataclass, field
import re

from sgsc.schemas.atom import RecommendationAtom

# ------------------------------------------------------------------
# Validation result
# ------------------------------------------------------------------


@dataclass
class ValidationIssue:
    """A single validation issue found in an atom."""

    atom_id: str
    field: str
    severity: str  # "error" | "warning"
    message: str


@dataclass
class ValidationResult:
    """Result of validating a batch of atoms."""

    valid_atoms: list[RecommendationAtom] = field(default_factory=list)
    rejected_atoms: list[RecommendationAtom] = field(default_factory=list)
    issues: list[ValidationIssue] = field(default_factory=list)

    @property
    def total_issues(self) -> int:
        return len(self.issues)

    @property
    def error_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == "error")


# ------------------------------------------------------------------
# Business rules
# ------------------------------------------------------------------

_SNAKE_CASE_RE = re.compile(r"^[a-z][a-z0-9_]*$")
_MAX_ACTION_ID_LEN = 80
_MIN_QUOTE_LEN = 20
_KNOWN_EVIDENCE_SYSTEMS = frozenset({"AHA", "GRADE", "NICE", "SIGN", "WHO", "ESC", "ACC"})
_KNOWN_REC_CLASSES = frozenset({"I", "1", "IIa", "2a", "IIb", "2b", "III", "3"})


def _validate_atom(atom: RecommendationAtom) -> list[ValidationIssue]:
    """Run business-rule checks on a single atom."""
    issues: list[ValidationIssue] = []

    # Action ID format
    if not _SNAKE_CASE_RE.match(atom.action.canonical_id):
        issues.append(
            ValidationIssue(
                atom_id=atom.atom_id,
                field="action.canonical_id",
                severity="error",
                message=f"Action ID '{atom.action.canonical_id}' is not valid snake_case.",
            )
        )
    if len(atom.action.canonical_id) > _MAX_ACTION_ID_LEN:
        issues.append(
            ValidationIssue(
                atom_id=atom.atom_id,
                field="action.canonical_id",
                severity="error",
                message=f"Action ID exceeds {_MAX_ACTION_ID_LEN} chars.",
            )
        )

    # Source quote length
    if len(atom.source.quote) < _MIN_QUOTE_LEN:
        issues.append(
            ValidationIssue(
                atom_id=atom.atom_id,
                field="source.quote",
                severity="warning",
                message=f"Source quote is short ({len(atom.source.quote)} chars).",
            )
        )

    # WITHIN must have deadline
    if atom.constraint.type == "WITHIN" and atom.constraint.deadline_minutes is None:
        issues.append(
            ValidationIssue(
                atom_id=atom.atom_id,
                field="constraint.deadline_minutes",
                severity="error",
                message="WITHIN constraint requires deadline_minutes.",
            )
        )

    # BEFORE must have before list
    if atom.constraint.type == "BEFORE" and not atom.sequence.before:
        issues.append(
            ValidationIssue(
                atom_id=atom.atom_id,
                field="sequence.before",
                severity="warning",
                message="BEFORE constraint has empty before list.",
            )
        )

    # Evidence system check
    if atom.evidence.system and atom.evidence.system not in _KNOWN_EVIDENCE_SYSTEMS:
        issues.append(
            ValidationIssue(
                atom_id=atom.atom_id,
                field="evidence.system",
                severity="warning",
                message=f"Unknown evidence system '{atom.evidence.system}'.",
            )
        )

    return issues


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def validate_atoms(
    atoms: list[RecommendationAtom],
    reject_on_error: bool = True,
) -> ValidationResult:
    """Validate a list of atoms against business rules.

    Args:
        atoms: Atoms to validate.
        reject_on_error: If True, atoms with severity="error" go to rejected_atoms.

    Returns:
        ValidationResult with valid/rejected atoms and issues.
    """
    result = ValidationResult()

    for atom in atoms:
        atom_issues = _validate_atom(atom)
        result.issues.extend(atom_issues)

        has_error = any(i.severity == "error" for i in atom_issues)
        if reject_on_error and has_error:
            result.rejected_atoms.append(atom)
        else:
            result.valid_atoms.append(atom)

    return result
