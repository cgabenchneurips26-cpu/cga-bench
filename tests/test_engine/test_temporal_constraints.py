"""Tests for TemporalConstraintChecker: Declare template-based temporal checks."""

import pytest

from cga_bench.cpg_engine.temporal_constraints import (
    TemporalConstraint,
    TemporalConstraintChecker,
    ConstraintResult,
)


@pytest.fixture
def checker():
    return TemporalConstraintChecker()


# Sepsis trace: blood_culture(1) → antibiotics(5) → reassess(30)
SEPSIS_TRACE = [
    ("order_lab_blood_culture", 1.0),
    ("order_lab_lactate", 2.0),
    ("give_broad_spectrum_antibiotics", 5.0),
    ("give_crystalloid_30ml_kg", 10.0),
    ("reassess_perfusion", 30.0),
]

# Bad trace: antibiotics before culture
BAD_SEQUENCE_TRACE = [
    ("give_broad_spectrum_antibiotics", 1.0),
    ("order_lab_blood_culture", 5.0),
]


class TestResponse:
    """Response(A, B): if A occurs, B must eventually occur."""

    def test_response_satisfied(self, checker):
        assert checker.check_response(
            SEPSIS_TRACE,
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
        ) is True

    def test_response_violated(self, checker):
        trace = [("order_lab_blood_culture", 1.0)]  # A occurs but B never
        assert checker.check_response(
            trace,
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
        ) is False

    def test_response_vacuously_true(self, checker):
        """If A never occurs, response is vacuously satisfied."""
        trace = [("give_broad_spectrum_antibiotics", 1.0)]
        assert checker.check_response(
            trace,
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
        ) is True


class TestPrecedence:
    """Precedence(A, B): if B occurs, A must have occurred before B."""

    def test_precedence_culture_before_antibiotics(self, checker):
        assert checker.check_precedence(
            SEPSIS_TRACE,
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
        ) is True

    def test_precedence_violated(self, checker):
        assert checker.check_precedence(
            BAD_SEQUENCE_TRACE,
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
        ) is False

    def test_precedence_b_never_occurs(self, checker):
        """If B never occurs, precedence is vacuously satisfied."""
        trace = [("order_lab_blood_culture", 1.0)]
        assert checker.check_precedence(
            trace,
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
        ) is True


class TestExistence:
    """Existence(A): A must occur at least once."""

    def test_existence_present(self, checker):
        assert checker.check_existence(
            SEPSIS_TRACE, "order_lab_blood_culture"
        ) is True

    def test_existence_absent(self, checker):
        assert checker.check_existence(
            SEPSIS_TRACE, "admit_to_icu"
        ) is False

    def test_existence_vital_signs(self, checker):
        trace = [("assess_vital_signs", 0.0)]
        assert checker.check_existence(trace, "assess_vital_signs") is True


class TestAbsence:
    """Absence(A): A must never occur."""

    def test_absence_satisfied(self, checker):
        assert checker.check_absence(SEPSIS_TRACE, "admit_to_icu") is True

    def test_absence_violated(self, checker):
        assert checker.check_absence(
            SEPSIS_TRACE, "order_lab_blood_culture"
        ) is False


class TestTimeBoundedResponse:
    """TimeBoundedResponse(A, B, max): B within max_minutes after A."""

    def test_antibiotics_within_60min(self, checker):
        assert checker.check_time_bounded_response(
            SEPSIS_TRACE,
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
            max_minutes=60.0,
        ) is True

    def test_antibiotics_within_3min_fails(self, checker):
        """Antibiotics at 5.0 - culture at 1.0 = 4.0 > 3.0 limit."""
        assert checker.check_time_bounded_response(
            SEPSIS_TRACE,
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
            max_minutes=3.0,
        ) is False

    def test_vacuously_true(self, checker):
        """A never occurs → vacuously satisfied."""
        assert checker.check_time_bounded_response(
            SEPSIS_TRACE,
            "admit_to_icu",
            "give_broad_spectrum_antibiotics",
            max_minutes=60.0,
        ) is True


class TestCheckAll:
    """Batch constraint checking."""

    def test_check_all_mixed(self, checker):
        constraints = [
            TemporalConstraint(
                template="precedence",
                action_a="order_lab_blood_culture",
                action_b="give_broad_spectrum_antibiotics",
                description="Culture before antibiotics",
            ),
            TemporalConstraint(
                template="existence",
                action_a="assess_vital_signs",
                description="Vital signs must be assessed",
            ),
            TemporalConstraint(
                template="time_bounded_response",
                action_a="order_lab_blood_culture",
                action_b="give_broad_spectrum_antibiotics",
                max_minutes=60.0,
                description="Antibiotics within 60 min of culture",
            ),
        ]

        trace = SEPSIS_TRACE + [("assess_vital_signs", 0.0)]
        results = checker.check_all(constraints, trace)

        assert len(results) == 3
        assert all(isinstance(r, ConstraintResult) for r in results)
        # Precedence: satisfied
        assert results[0].satisfied is True
        # Existence: satisfied
        assert results[1].satisfied is True
        # TimeBoundedResponse: satisfied
        assert results[2].satisfied is True
