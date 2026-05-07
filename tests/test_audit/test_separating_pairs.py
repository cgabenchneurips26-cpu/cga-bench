"""Tests for separating-pair witness catalogue."""

from __future__ import annotations

from pathlib import Path

from audit.separating_pairs import SeparatingPair, load_separating_pairs
import pytest

PAIRS_PATH = Path(__file__).resolve().parents[2] / "evidence_pack" / "separating_pairs.yaml"

_EXPECTED_TOTAL = 20
_EXPECTED_PER_CASE = 5
_VALID_CASES = ("case_i", "case_ii", "case_iii", "case_iv")
_VALID_VIOLATION_TYPES = {"TIMING", "SEQUENCE", "COMMISSION", "OMISSION", "DEVIATION", "unknown"}


class TestSeparatingPairsCatalogue:
    """Validate the separating-pair witness catalogue."""

    @pytest.fixture(scope="class")
    def pairs(self) -> list[SeparatingPair]:
        return load_separating_pairs(PAIRS_PATH)

    def test_yaml_loads(self, pairs: list[SeparatingPair]) -> None:
        assert len(pairs) > 0

    def test_total_count(self, pairs: list[SeparatingPair]) -> None:
        assert len(pairs) == _EXPECTED_TOTAL, f"Expected {_EXPECTED_TOTAL} pairs, got {len(pairs)}"

    def test_five_per_case(self, pairs: list[SeparatingPair]) -> None:
        by_case: dict[str, list[SeparatingPair]] = {}
        for p in pairs:
            by_case.setdefault(p.case, []).append(p)
        for case in _VALID_CASES:
            count = len(by_case.get(case, []))
            assert count == _EXPECTED_PER_CASE, f"{case} has {count} pairs, expected {_EXPECTED_PER_CASE}"

    def test_verdicts_differ(self, pairs: list[SeparatingPair]) -> None:
        for p in pairs:
            assert p.expected_verdict_a != p.expected_verdict_b, f"Pair {p.pair_id}: verdicts must differ"

    def test_unique_pair_ids(self, pairs: list[SeparatingPair]) -> None:
        ids = [p.pair_id for p in pairs]
        assert len(ids) == len(set(ids)), f"Duplicate pair_ids found: {[i for i in ids if ids.count(i) > 1]}"

    def test_invariants_pass(self, pairs: list[SeparatingPair]) -> None:
        for p in pairs:
            p.assert_invariants()

    def test_has_required_fields(self, pairs: list[SeparatingPair]) -> None:
        for p in pairs:
            assert p.pair_id, "Missing pair_id on entry"
            assert p.case, f"Pair {p.pair_id}: missing case"
            assert p.scenario_id, f"Pair {p.pair_id}: missing scenario_id"
            assert p.episode_a, f"Pair {p.pair_id}: missing episode_a"
            assert p.episode_b, f"Pair {p.pair_id}: missing episode_b"
            assert p.minimal_edit, f"Pair {p.pair_id}: missing minimal_edit"
            assert p.constraint_violated, f"Pair {p.pair_id}: missing constraint_violated"

    def test_episode_ids_differ_within_pair(self, pairs: list[SeparatingPair]) -> None:
        for p in pairs:
            assert p.episode_a != p.episode_b, f"Pair {p.pair_id}: episode_a == episode_b ({p.episode_a!r})"

    def test_case_values_are_valid(self, pairs: list[SeparatingPair]) -> None:
        for p in pairs:
            assert p.case in _VALID_CASES, f"Pair {p.pair_id}: invalid case {p.case!r}"

    def test_violation_types_are_known(self, pairs: list[SeparatingPair]) -> None:
        for p in pairs:
            assert p.violation_type in _VALID_VIOLATION_TYPES, (
                f"Pair {p.pair_id}: unexpected violation_type {p.violation_type!r}"
            )

    def test_verdict_a_always_true(self, pairs: list[SeparatingPair]) -> None:
        """By catalogue convention episode_a is always the safe trace."""
        for p in pairs:
            assert p.expected_verdict_a is True, f"Pair {p.pair_id}: expected_verdict_a should be True (safe trace)"

    def test_verdict_b_always_false(self, pairs: list[SeparatingPair]) -> None:
        """By catalogue convention episode_b is always the harmful trace."""
        for p in pairs:
            assert p.expected_verdict_b is False, (
                f"Pair {p.pair_id}: expected_verdict_b should be False (harmful trace)"
            )


class TestLoadSeparatingPairsEdgeCases:
    """Test loader robustness."""

    def test_missing_file_raises(self) -> None:
        with pytest.raises(FileNotFoundError):
            load_separating_pairs("/nonexistent/path/separating_pairs.yaml")

    def test_returns_list_of_separating_pair(self) -> None:
        pairs = load_separating_pairs(PAIRS_PATH)
        for p in pairs:
            assert isinstance(p, SeparatingPair)
