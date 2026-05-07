"""Deterministic tests for Gwet AC1/AC2 with hand-computed expected values.

Each fixture has a documented formula derivation so reviewers can verify
the expected values are not coincidental.

Formulas (from clinician_validation/analyze_validation.py):
    AC1 (binary):
        pa = sum(per_item_pairwise_agreement) / n_items
        pi = n_positive_cells / n_cells
        pe = 2 * pi * (1 - pi)
        AC1 = (pa - pe) / (1 - pe)

    AC2 (ordinal, quadratic weights):
        w(q, l) = 1 - (|q - l| / (k - 1))^2
        pa = sum(per_item_weighted_agreement) / n_items
        pe = sum_{q,l} w(q,l) * pi_q * pi_l
        AC2 = (pa - pe) / (1 - pe)
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from cga_bench.clinician_validation.analyze_validation import (
    compute_gwet_ac1,
    compute_gwet_ac2,
)

FIXTURES_PATH = Path(__file__).parent.parent / "fixtures" / "synthetic_raters.json"
Q4_ORDINAL = ["none", "minor", "moderate", "major"]


def _load_fixtures() -> dict:
    with open(FIXTURES_PATH) as f:
        return json.load(f)


# ── Fixture A: Perfect agreement (2 raters, 3 scenarios) ────────────
#
# All raters agree on every field.
#
# AC1 for Q1 (positive_value="yes"):
#   Each scenario: row_vals = [1, 1] → 1 pair, 1 agree → proportion = 1.0
#   n_agree = 3 × 1.0 = 3.0,  n_total = 3
#   pa = 3.0 / 3 = 1.0
#   n_cells = 6,  n_positive_cells = 6
#   pi = 6/6 = 1.0
#   pe = 2 × 1.0 × 0.0 = 0.0
#   AC1 = (1.0 - 0.0) / (1.0 - 0.0) = 1.0
#
# AC1 for Q3: identical structure → AC1 = 1.0
#
# AC2 for Q4 (k=4, all "none"):
#   Each scenario: indices = [0, 0] → dist=0, w=1.0
#   pa = 1.0
#   category_counts = [6, 0, 0, 0],  pi = [1.0, 0, 0, 0]
#   pe = w(0,0) × 1.0 × 1.0 = 1.0  (all other terms zero)
#   pe >= 1.0 and pa >= 1.0 → AC2 = 1.0
#


class TestFixtureAPerfect:
    @pytest.fixture(autouse=True)
    def _load(self) -> None:
        self.ratings = _load_fixtures()["fixture_a_perfect"]["ratings"]

    def test_ac1_q1(self) -> None:
        result = compute_gwet_ac1(self.ratings, "q1_follows_guideline")
        assert result["ac1"] == pytest.approx(1.0, abs=1e-4)
        assert result["pa"] == pytest.approx(1.0, abs=1e-4)
        assert result["pe"] == pytest.approx(0.0, abs=1e-4)
        assert result["n"] == 3

    def test_ac1_q3(self) -> None:
        result = compute_gwet_ac1(self.ratings, "q3_trainee_acceptable")
        assert result["ac1"] == pytest.approx(1.0, abs=1e-4)
        assert result["n"] == 3

    def test_ac2_q4(self) -> None:
        result = compute_gwet_ac2(self.ratings, "q4_worst_severity", Q4_ORDINAL)
        assert result["ac2"] == pytest.approx(1.0, abs=1e-4)
        assert result["pa"] == pytest.approx(1.0, abs=1e-4)
        assert result["pe"] == pytest.approx(1.0, abs=1e-4)
        assert result["n"] == 3


# ── Fixture B: Partial agreement (2 raters, 3 scenarios) ────────────
#
# AC1 for Q1:
#   s1: [1,1] → agree     s2: [1,1] → agree     s3: [1,0] → disagree
#   n_agree = 2,  n_total = 3,  n_cells = 6,  n_positive = 5
#   pa = 2/3
#   pi = 5/6,  pe = 2 × (5/6) × (1/6) = 5/18
#   AC1 = (2/3 - 5/18) / (1 - 5/18) = (7/18) / (13/18) = 7/13 ≈ 0.5385
#
# AC1 for Q3:
#   s1: [1,1] → agree     s2: [0,1] → disagree   s3: [1,0] → disagree
#   n_agree = 1,  n_total = 3,  n_cells = 6,  n_positive = 4
#   pa = 1/3
#   pi = 4/6 = 2/3,  pe = 2 × (2/3) × (1/3) = 4/9
#   AC1 = (1/3 - 4/9) / (1 - 4/9) = (-1/9) / (5/9) = -1/5 = -0.2
#
# AC2 for Q4 (k=4, ordinal = [none, minor, moderate, major]):
#   s1: [0,0] → w=1.0      s2: [1,1] → w=1.0      s3: [2,3] → dist=1, w=8/9
#   pa_sum = 1 + 1 + 8/9 = 26/9,  pa = 26/27
#
#   category_counts = [2, 2, 1, 1],  n_cells = 6
#   pi = [1/3, 1/3, 1/6, 1/6]
#
#   pe = sum_{q,l} w(q,l) × pi_q × pi_l
#   Using common denominator 324:
#     q=0: 36 + 32 + 10 + 0 = 78
#     q=1: 32 + 36 + 16 + 10 = 94
#     q=2: 10 + 16 + 9 + 8 = 43
#     q=3: 0 + 10 + 8 + 9 = 27
#     Total = 242/324 = 121/162
#   pe = 121/162 ≈ 0.7469
#
#   AC2 = (26/27 - 121/162) / (1 - 121/162)
#       = (156/162 - 121/162) / (41/162) = 35/41 ≈ 0.8537
#


class TestFixtureBPartial:
    @pytest.fixture(autouse=True)
    def _load(self) -> None:
        self.ratings = _load_fixtures()["fixture_b_partial"]["ratings"]

    def test_ac1_q1(self) -> None:
        result = compute_gwet_ac1(self.ratings, "q1_follows_guideline")
        assert result["ac1"] == pytest.approx(7 / 13, abs=1e-4)
        assert result["pa"] == pytest.approx(2 / 3, abs=1e-4)
        assert result["pe"] == pytest.approx(5 / 18, abs=1e-4)
        assert result["n"] == 3

    def test_ac1_q3(self) -> None:
        result = compute_gwet_ac1(self.ratings, "q3_trainee_acceptable")
        assert result["ac1"] == pytest.approx(-1 / 5, abs=1e-4)
        assert result["pa"] == pytest.approx(1 / 3, abs=1e-4)
        assert result["pe"] == pytest.approx(4 / 9, abs=1e-4)
        assert result["n"] == 3

    def test_ac2_q4(self) -> None:
        result = compute_gwet_ac2(self.ratings, "q4_worst_severity", Q4_ORDINAL)
        assert result["ac2"] == pytest.approx(35 / 41, abs=1e-4)
        assert result["pa"] == pytest.approx(26 / 27, abs=1e-4)
        assert result["pe"] == pytest.approx(121 / 162, abs=1e-4)
        assert result["n"] == 3


# ── Fixture C: Three raters, 2 scenarios ─────────────────────────────
#
# Tests multi-rater pairwise aggregation (3 pairs per scenario).
#
# AC1 for Q1:
#   s1: [1,1,1] → 3 pairs, all agree → proportion = 1.0
#   s2: [0,0,1] → 3 pairs, 1 agree (r1-r2) → proportion = 1/3
#   n_agree = 1 + 1/3 = 4/3,  n_total = 2
#   n_cells = 6,  n_positive = 4  (s1: 3 yes, s2: 1 yes)
#   pa = (4/3) / 2 = 2/3
#   pi = 4/6 = 2/3,  pe = 2 × (2/3) × (1/3) = 4/9
#   AC1 = (2/3 - 4/9) / (1 - 4/9) = (2/9) / (5/9) = 2/5 = 0.4
#
# AC1 for Q3:
#   s1: [1,1,0] → 3 pairs, 1 agree (r1-r2) → proportion = 1/3
#   s2: [0,0,1] → 3 pairs, 1 agree (r1-r2) → proportion = 1/3
#   n_agree = 2/3,  n_total = 2
#   n_cells = 6,  n_positive = 3  (s1: r1+r2=2, s2: r3=1)
#   pa = (2/3) / 2 = 1/3
#   pi = 3/6 = 1/2,  pe = 2 × 0.5 × 0.5 = 0.5
#   AC1 = (1/3 - 1/2) / (1 - 1/2) = (-1/6) / (1/2) = -1/3 ≈ -0.3333
#
# AC2 for Q4 (k=4):
#   s1: indices [1, 0, 1] (minor, none, minor)
#     Pairs: (1,0)→d=1→w=8/9, (1,1)→d=0→w=1, (0,1)→d=1→w=8/9
#     weighted = (8/9 + 1 + 8/9) / 3 = 25/27
#   s2: indices [3, 2, 3] (major, moderate, major)
#     Pairs: (3,2)→d=1→w=8/9, (3,3)→d=0→w=1, (2,3)→d=1→w=8/9
#     weighted = 25/27
#   pa = (25/27 + 25/27) / 2 = 25/27
#
#   category_counts = [1, 2, 1, 2],  n_cells = 6
#   pi = [1/6, 1/3, 1/6, 1/3]
#
#   pe (common denominator 324):
#     q=0: 9 + 16 + 5 + 0 = 30
#     q=1: 16 + 36 + 16 + 20 = 88
#     q=2: 5 + 16 + 9 + 16 = 46
#     q=3: 0 + 20 + 16 + 36 = 72
#     Total = 236/324 = 59/81
#   pe = 59/81 ≈ 0.7284
#
#   AC2 = (25/27 - 59/81) / (1 - 59/81)
#       = (75/81 - 59/81) / (22/81) = 16/22 = 8/11 ≈ 0.7273
#


class TestFixtureCThreeRaters:
    @pytest.fixture(autouse=True)
    def _load(self) -> None:
        self.ratings = _load_fixtures()["fixture_c_three_raters"]["ratings"]

    def test_ac1_q1(self) -> None:
        result = compute_gwet_ac1(self.ratings, "q1_follows_guideline")
        assert result["ac1"] == pytest.approx(2 / 5, abs=1e-4)
        assert result["pa"] == pytest.approx(2 / 3, abs=1e-4)
        assert result["pe"] == pytest.approx(4 / 9, abs=1e-4)
        assert result["n"] == 2

    def test_ac1_q3(self) -> None:
        result = compute_gwet_ac1(self.ratings, "q3_trainee_acceptable")
        assert result["ac1"] == pytest.approx(-1 / 3, abs=1e-4)
        assert result["pa"] == pytest.approx(1 / 3, abs=1e-4)
        assert result["pe"] == pytest.approx(1 / 2, abs=1e-4)
        assert result["n"] == 2

    def test_ac2_q4(self) -> None:
        result = compute_gwet_ac2(self.ratings, "q4_worst_severity", Q4_ORDINAL)
        assert result["ac2"] == pytest.approx(8 / 11, abs=1e-4)
        assert result["pa"] == pytest.approx(25 / 27, abs=1e-4)
        assert result["pe"] == pytest.approx(59 / 81, abs=1e-4)
        assert result["n"] == 2


# ── Edge cases ───────────────────────────────────────────────────────


class TestEdgeCases:
    def test_single_rater_returns_zero(self) -> None:
        """AC1 with < 2 raters should return 0."""
        ratings = {"r1": {"s1": {"q1_follows_guideline": "yes"}}}
        result = compute_gwet_ac1(ratings, "q1_follows_guideline")
        assert result["ac1"] == 0.0
        assert result["n"] == 0

    def test_all_missing_returns_zero(self) -> None:
        """AC1 with no valid data should return 0."""
        ratings = {
            "r1": {"s1": {"q1_follows_guideline": None}},
            "r2": {"s1": {"q1_follows_guideline": None}},
        }
        result = compute_gwet_ac1(ratings, "q1_follows_guideline")
        assert result["ac1"] == 0.0
        assert result["n"] == 0

    def test_ac2_single_category_returns_one(self) -> None:
        """AC2 when all raters agree on a single ordinal value → 1.0."""
        ratings = {
            "r1": {"s1": {"sev": "moderate"}, "s2": {"sev": "moderate"}},
            "r2": {"s1": {"sev": "moderate"}, "s2": {"sev": "moderate"}},
        }
        result = compute_gwet_ac2(ratings, "sev", Q4_ORDINAL)
        assert result["ac2"] == pytest.approx(1.0, abs=1e-4)
        assert result["n"] == 2
