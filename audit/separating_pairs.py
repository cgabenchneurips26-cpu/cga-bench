"""Separating-pair witness catalogue loader and validator.

A separating pair (x_a, x_b) consists of two episodes that:
  - Share the same projection under a specific pi-class
  - But differ in clinical safety (one safe, one harmful)

Organized by Lemma case:
  case_i:   pi_term(a) == pi_term(b) but differ in action set
  case_ii:  pi_aset(a) == pi_aset(b) but differ in ordering
  case_iii: pi_nord(a) == pi_nord(b) but differ in timing
  case_iv:  pi_nctx(a) == pi_nctx(b) but differ in patient context
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml

_VALID_CASES = frozenset({"case_i", "case_ii", "case_iii", "case_iv"})

_DEFAULT_PAIRS_PATH = Path(__file__).resolve().parents[1] / "evidence_pack" / "separating_pairs.yaml"


@dataclass
class SeparatingPair:
    """A single separating pair with metadata."""

    pair_id: str
    case: str  # "case_i", "case_ii", "case_iii", "case_iv"
    scenario_id: str
    episode_a: str  # episode_id of the safe trace
    episode_b: str  # episode_id of the harmful trace
    expected_verdict_a: bool  # True = safe
    expected_verdict_b: bool  # True = safe
    minimal_edit: str  # Human-readable description of the distinguishing edit
    constraint_violated: str  # Which constraint is violated in episode_b
    violation_type: str  # TIMING, SEQUENCE, COMMISSION, OMISSION, DEVIATION

    def assert_invariants(self, projections: dict[str, Any] | None = None) -> None:
        """Validate structural invariants for this pair's case.

        Args:
            projections: Optional pre-computed projection dict for extended checks.

        Raises:
            AssertionError: If any invariant is violated.
        """
        assert self.expected_verdict_a != self.expected_verdict_b, (
            f"Pair {self.pair_id}: verdicts must differ (a={self.expected_verdict_a}, b={self.expected_verdict_b})"
        )
        assert self.case in _VALID_CASES, (
            f"Pair {self.pair_id}: invalid case {self.case!r}; must be one of {sorted(_VALID_CASES)}"
        )
        assert self.pair_id, "pair_id must be non-empty"
        assert self.scenario_id, f"Pair {self.pair_id}: scenario_id must be non-empty"
        assert self.episode_a, f"Pair {self.pair_id}: episode_a must be non-empty"
        assert self.episode_b, f"Pair {self.pair_id}: episode_b must be non-empty"
        assert self.episode_a != self.episode_b, f"Pair {self.pair_id}: episode_a and episode_b must differ"
        assert self.minimal_edit, f"Pair {self.pair_id}: minimal_edit must be non-empty"
        assert self.constraint_violated, f"Pair {self.pair_id}: constraint_violated must be non-empty"


def load_separating_pairs(
    path: str | Path = _DEFAULT_PAIRS_PATH,
) -> list[SeparatingPair]:
    """Load and validate the separating-pair catalogue.

    Args:
        path: Path to the separating_pairs.yaml catalogue file.

    Returns:
        List of validated SeparatingPair instances.

    Raises:
        FileNotFoundError: If the catalogue file does not exist.
        AssertionError: If the schema version is unexpected.
        KeyError: If a required field is missing from an entry.
    """
    path = Path(path)
    with open(path) as fh:
        raw = yaml.safe_load(fh)

    assert raw.get("schema_version") == "1.0", (
        f"Unexpected schema version: {raw.get('schema_version')!r}; expected '1.0'"
    )

    pairs: list[SeparatingPair] = []
    for case_key, case_entries in raw.get("cases", {}).items():
        for entry in case_entries:
            pair = SeparatingPair(
                pair_id=entry["pair_id"],
                case=case_key,
                scenario_id=entry["scenario_id"],
                episode_a=entry["episode_a"],
                episode_b=entry["episode_b"],
                expected_verdict_a=bool(entry["expected_verdict_a"]),
                expected_verdict_b=bool(entry["expected_verdict_b"]),
                minimal_edit=entry["minimal_edit"],
                constraint_violated=entry["constraint_violated"],
                violation_type=entry.get("violation_type", "unknown"),
            )
            pair.assert_invariants()
            pairs.append(pair)

    return pairs
