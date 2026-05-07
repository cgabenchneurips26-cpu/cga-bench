"""Evaluator audit harness — abstract base class.

Any evaluator (ours or reviewer-supplied) gets a uniform entry point:
    Evaluator.verdict(episode) -> bool

Implementations MUST be deterministic and side-effect free
(no network calls, no LLM calls at audit time — cache offline).

This module is deliberately decoupled — it never touches the scorer-side
packages (assessor_core, cpg_engine) to respect isolation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvaluatorMeta:
    """Metadata for an evaluator shim."""

    name: str  # "DxEM", "AC-Proxy", ...
    family: str  # "TOM", "ASC", "PAF", "CwT", "ACov", "TCC"
    version: str = "1.0"
    source: str | None = None  # file path or DOI


class Evaluator(ABC):
    """A pure function: episode dict -> {True (safe/pass), False (harmful/fail)}.

    Implementations operate on raw episode dicts (as stored in
    verdict_matrix_v6.json per_episode entries), not on Pydantic models,
    to keep the audit harness decoupled from scoring internals.
    """

    meta: EvaluatorMeta

    @abstractmethod
    def verdict(self, ep: dict[str, Any]) -> bool:
        """Return True if the evaluator considers this episode safe/passing."""
        ...

    def observed_features(self) -> frozenset[str]:
        """Return the set of trajectory fields the evaluator reads.

        Soft hint for pi-class classification; the behavioral test on
        separating pairs remains the ground truth.
        """
        return frozenset()
