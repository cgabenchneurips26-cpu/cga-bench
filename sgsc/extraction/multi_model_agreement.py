"""N-model agreement filter for proposed atoms.

Runs atom proposal through multiple LLM endpoints and keeps only
atoms that appear in at least ``min_agreement`` proposals (by action ID).
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
import logging

from sgsc.extraction.atom_proposer import AtomProposerConfig, propose_atoms
from sgsc.schemas.atom import RecommendationAtom

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------


@dataclass(frozen=True)
class AgreementConfig:
    """Configuration for multi-model agreement filtering."""

    configs: tuple[AtomProposerConfig, ...]
    """LLM endpoint configurations (one per model)."""

    min_agreement: int = 2
    """Minimum number of models that must propose an atom (by action ID)."""


# ------------------------------------------------------------------
# Agreement result
# ------------------------------------------------------------------


@dataclass
class AgreementResult:
    """Result of multi-model agreement filtering."""

    agreed_atoms: list[RecommendationAtom] = field(default_factory=list)
    """Atoms that met the agreement threshold."""

    rejected_atoms: list[RecommendationAtom] = field(default_factory=list)
    """Atoms below the agreement threshold."""

    action_id_counts: dict[str, int] = field(default_factory=dict)
    """How many models proposed each action ID."""

    model_atom_counts: dict[str, int] = field(default_factory=dict)
    """How many atoms each model proposed."""


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def filter_by_agreement(
    agreement_config: AgreementConfig,
    guideline_id: str,
    recommendations: list[dict[str, str | int | None]],
) -> AgreementResult:
    """Run multi-model proposal and filter by agreement.

    Args:
        agreement_config: Endpoint configs and agreement threshold.
        guideline_id: Guideline identifier.
        recommendations: Recommendation dicts with 'text' keys.

    Returns:
        AgreementResult with agreed and rejected atoms.
    """
    all_atoms_by_model: dict[str, list[RecommendationAtom]] = {}
    action_counter: Counter[str] = Counter()

    for config in agreement_config.configs:
        model_key = f"{config.endpoint}:{config.model}"
        try:
            atoms = propose_atoms(config, guideline_id, recommendations)
            all_atoms_by_model[model_key] = atoms
            for atom in atoms:
                action_counter[atom.action.canonical_id] += 1
        except Exception:
            logger.warning("Model %s failed to propose atoms", model_key, exc_info=True)
            all_atoms_by_model[model_key] = []

    # Select atoms that meet threshold
    agreed_action_ids = {aid for aid, count in action_counter.items() if count >= agreement_config.min_agreement}

    # Pick the best atom for each agreed action (highest agreement_score or first seen)
    best_atoms: dict[str, RecommendationAtom] = {}
    rejected: list[RecommendationAtom] = []

    for atoms in all_atoms_by_model.values():
        for atom in atoms:
            aid = atom.action.canonical_id
            if aid in agreed_action_ids:
                if aid not in best_atoms:
                    atom.agreement_score = float(action_counter[aid])
                    best_atoms[aid] = atom
            else:
                rejected.append(atom)

    return AgreementResult(
        agreed_atoms=list(best_atoms.values()),
        rejected_atoms=rejected,
        action_id_counts=dict(action_counter),
        model_atom_counts={k: len(v) for k, v in all_atoms_by_model.items()},
    )
