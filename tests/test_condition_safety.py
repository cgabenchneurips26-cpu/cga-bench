"""Condition Safety Tests (Defense against Attack 3.5)

Tests that ConstraintDerivationEngine._evaluate_condition() blocks
malicious condition strings and prevents code injection.

Usage:
    PYTHONPATH=. pytest tests/test_condition_safety.py -v
"""

from __future__ import annotations

from cga_bench.cpg_model.constraint_derivation import ConstraintDerivationEngine

engine = ConstraintDerivationEngine()

SAFE_PATIENT: dict = {
    "age": 50,
    "sex": "M",
    "labs": {"potassium": 4.0, "glucose": 300, "ph": 7.2},
    "comorbidities": ["diabetes", "hypertension"],
    "allergies": ["penicillin"],
    "medications": ["metformin"],
    "vitals": {"sbp": 120, "hr": 80},
}


class TestInjectionPrevention:
    """Verify that dangerous patterns are blocked."""

    def test_no_import(self) -> None:
        result = engine._evaluate_condition("__import__('os').system('echo pwned')", SAFE_PATIENT)
        assert result is False

    def test_no_open(self) -> None:
        result = engine._evaluate_condition("open('/etc/passwd').read()", SAFE_PATIENT)
        assert result is False

    def test_no_exec(self) -> None:
        result = engine._evaluate_condition("exec('import os')", SAFE_PATIENT)
        assert result is False

    def test_no_eval_nested(self) -> None:
        result = engine._evaluate_condition("eval('1+1')", SAFE_PATIENT)
        assert result is False

    def test_no_lambda(self) -> None:
        result = engine._evaluate_condition("(lambda: True)()", SAFE_PATIENT)
        assert result is False

    def test_no_class_access(self) -> None:
        result = engine._evaluate_condition("''.__class__.__mro__[-1].__subclasses__()", SAFE_PATIENT)
        assert result is False

    def test_no_globals(self) -> None:
        result = engine._evaluate_condition("globals()", SAFE_PATIENT)
        assert result is False

    def test_no_subprocess(self) -> None:
        result = engine._evaluate_condition("__import__('subprocess').run(['ls'])", SAFE_PATIENT)
        assert result is False

    def test_no_builtins_escape(self) -> None:
        result = engine._evaluate_condition("__builtins__", SAFE_PATIENT)
        # Should not expose builtins dict as truthy
        assert result is False

    def test_no_getattr_trick(self) -> None:
        result = engine._evaluate_condition("getattr(__builtins__, '__import__')('os')", SAFE_PATIENT)
        assert result is False

    def test_no_compile(self) -> None:
        result = engine._evaluate_condition("compile('print(1)', '', 'exec')", SAFE_PATIENT)
        assert result is False

    def test_no_type_call(self) -> None:
        result = engine._evaluate_condition("type('X', (), {'__init__': lambda s: None})()", SAFE_PATIENT)
        assert result is False


class TestDoSPrevention:
    """Verify resilience against denial-of-service patterns."""

    def test_extremely_long_condition(self) -> None:
        """Very long condition string should not hang."""
        long_condition = "patient.age > 1 and " * 10000 + "True"
        try:
            engine._evaluate_condition(long_condition, SAFE_PATIENT)
        except Exception:
            pass  # Any exception is acceptable for DoS prevention

    def test_deeply_nested_parens(self) -> None:
        """Deeply nested parentheses should not hang."""
        nested = "(" * 500 + "True" + ")" * 500
        try:
            engine._evaluate_condition(nested, SAFE_PATIENT)
        except Exception:
            pass  # Any exception is acceptable


class TestNormalConditionsStillWork:
    """Verify that security measures don't break legitimate conditions."""

    def test_age_comparison(self) -> None:
        assert engine._evaluate_condition("patient.age > 18", {"age": 50}) is True

    def test_age_comparison_false(self) -> None:
        assert engine._evaluate_condition("patient.age > 18", {"age": 10}) is False

    def test_comorbidity_membership(self) -> None:
        assert (
            engine._evaluate_condition(
                "'diabetes' in patient.comorbidities",
                {"comorbidities": ["diabetes", "hypertension"]},
            )
            is True
        )

    def test_comorbidity_not_present(self) -> None:
        assert (
            engine._evaluate_condition(
                "'ckd' in patient.comorbidities",
                {"comorbidities": ["diabetes"]},
            )
            is False
        )

    def test_lab_value_less_than(self) -> None:
        assert (
            engine._evaluate_condition(
                "patient.labs.potassium < 3.3",
                {"labs": {"potassium": 2.9}},
            )
            is True
        )

    def test_lab_value_greater_than(self) -> None:
        assert (
            engine._evaluate_condition(
                "patient.labs.potassium > 5.5",
                {"labs": {"potassium": 6.0}},
            )
            is True
        )

    def test_compound_and_condition(self) -> None:
        assert (
            engine._evaluate_condition(
                "patient.age > 18 and patient.labs.potassium < 3.3",
                {"age": 50, "labs": {"potassium": 2.9}},
            )
            is True
        )

    def test_compound_or_condition(self) -> None:
        assert (
            engine._evaluate_condition(
                "patient.age < 18 or patient.labs.potassium < 3.3",
                {"age": 50, "labs": {"potassium": 2.9}},
            )
            is True
        )

    def test_medication_in_list(self) -> None:
        assert (
            engine._evaluate_condition(
                "'sglt2_inhibitor' in patient.medications",
                {"medications": ["sglt2_inhibitor", "metformin"]},
            )
            is True
        )

    def test_allergy_check(self) -> None:
        assert (
            engine._evaluate_condition(
                "'penicillin' in patient.allergies",
                {"allergies": ["penicillin"]},
            )
            is True
        )

    def test_missing_lab_returns_false(self) -> None:
        """Missing lab should return False, not crash."""
        assert (
            engine._evaluate_condition(
                "patient.labs.potassium < 3.3",
                {"labs": {}},
            )
            is False
        )

    def test_missing_field_returns_false(self) -> None:
        """Missing patient field should return False."""
        assert (
            engine._evaluate_condition(
                "patient.labs.potassium < 3.3",
                {},
            )
            is False
        )

    def test_boolean_true_condition(self) -> None:
        """Unconditional 'True' should work."""
        assert engine._evaluate_condition("True", {}) is True

    def test_sex_equality(self) -> None:
        assert (
            engine._evaluate_condition(
                "patient.sex == 'M'",
                {"sex": "M"},
            )
            is True
        )
