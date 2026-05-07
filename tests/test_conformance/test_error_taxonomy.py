"""Tests for error taxonomy classification."""
import pytest

from cga_bench.semantic_layer.conformance.error_taxonomy import (
    ClassifiedError,
    ErrorCategory,
    ENVIRONMENT_CONSTRAINT_CATEGORIES,
    classify_error,
)
from cga_bench.semantic_layer.conformance.activity import classify_response_error


class TestClassifyError:
    """Test classify_error with OperationOutcome payloads."""

    def test_not_found_outcome(self):
        payload = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "not-found"}],
        }
        result = classify_error(None, payload)
        assert result is not None
        assert result.error_category == ErrorCategory.NOT_FOUND
        assert result.is_environment_constraint is True
        assert result.issue_code == "not-found"
        assert result.issue_severity == "error"

    def test_forbidden_outcome(self):
        payload = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "forbidden"}],
        }
        result = classify_error(None, payload)
        assert result is not None
        assert result.error_category == ErrorCategory.AUTH
        assert result.is_environment_constraint is True

    def test_invalid_outcome(self):
        payload = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "invalid"}],
        }
        result = classify_error(None, payload)
        assert result is not None
        assert result.error_category == ErrorCategory.INVALID
        assert result.is_environment_constraint is False

    def test_throttled_outcome(self):
        payload = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "warning", "code": "throttled"}],
        }
        result = classify_error(None, payload)
        assert result is not None
        assert result.error_category == ErrorCategory.RATE_LIMIT
        assert result.is_environment_constraint is True

    def test_server_exception(self):
        payload = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "fatal", "code": "exception"}],
        }
        result = classify_error(None, payload)
        assert result is not None
        assert result.error_category == ErrorCategory.SERVER_ERROR
        assert result.is_environment_constraint is True

    def test_timeout_outcome(self):
        payload = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "timeout"}],
        }
        result = classify_error(None, payload)
        assert result is not None
        assert result.error_category == ErrorCategory.TIMEOUT
        assert result.is_environment_constraint is True

    def test_multiple_issues_uses_most_severe(self):
        payload = {
            "resourceType": "OperationOutcome",
            "issue": [
                {"severity": "warning", "code": "not-found"},
                {"severity": "error", "code": "invalid"},
            ],
        }
        result = classify_error(None, payload)
        assert result is not None
        # "error" is more severe than "warning", so "invalid" wins
        assert result.error_category == ErrorCategory.INVALID
        assert result.issue_severity == "error"

    def test_empty_issues(self):
        payload = {
            "resourceType": "OperationOutcome",
            "issue": [],
        }
        result = classify_error(None, payload)
        assert result is not None
        assert result.error_category == ErrorCategory.UNKNOWN
        assert result.is_environment_constraint is False

    def test_diagnostics_preserved(self):
        payload = {
            "resourceType": "OperationOutcome",
            "issue": [
                {
                    "severity": "error",
                    "code": "not-found",
                    "diagnostics": "Patient/123 not found",
                }
            ],
        }
        result = classify_error(None, payload)
        assert result is not None
        assert result.diagnostics == "Patient/123 not found"

    def test_unknown_code(self):
        payload = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "something-new"}],
        }
        result = classify_error(None, payload)
        assert result is not None
        assert result.error_category == ErrorCategory.UNKNOWN

    def test_non_operation_outcome_returns_none(self):
        payload = {"resourceType": "Patient", "id": "123"}
        result = classify_error(None, payload)
        assert result is None

    def test_none_inputs(self):
        result = classify_error(None, None)
        assert result is None


class TestTextErrorClassification:
    """Test text-based error classification."""

    def test_404_client_error(self):
        result = classify_error("404 Client Error: Not Found", None)
        assert result is not None
        assert result.error_category == ErrorCategory.NOT_FOUND
        assert result.is_environment_constraint is True

    def test_400_client_error(self):
        result = classify_error("400 Client Error: Bad Request", None)
        assert result is not None
        assert result.error_category == ErrorCategory.INVALID
        assert result.is_environment_constraint is False

    def test_401_client_error(self):
        result = classify_error("401 Client Error: Unauthorized", None)
        assert result is not None
        assert result.error_category == ErrorCategory.AUTH
        assert result.is_environment_constraint is True

    def test_429_client_error(self):
        result = classify_error("429 Client Error: Too Many Requests", None)
        assert result is not None
        assert result.error_category == ErrorCategory.RATE_LIMIT
        assert result.is_environment_constraint is True

    def test_500_server_error(self):
        result = classify_error("500 Server Error: Internal Server Error", None)
        assert result is not None
        assert result.error_category == ErrorCategory.SERVER_ERROR
        assert result.is_environment_constraint is True

    def test_504_timeout(self):
        result = classify_error("504 Server Error: Gateway Timeout", None)
        assert result is not None
        assert result.error_category == ErrorCategory.TIMEOUT
        assert result.is_environment_constraint is True

    def test_get_request_error(self):
        result = classify_error("Error in sending the GET request to /fhir/Patient", None)
        assert result is not None
        assert result.error_category == ErrorCategory.SERVER_ERROR
        assert result.is_environment_constraint is True

    def test_timeout_text(self):
        result = classify_error("Request timed out after 30 seconds", None)
        assert result is not None
        assert result.error_category == ErrorCategory.TIMEOUT
        assert result.is_environment_constraint is True

    def test_normal_text_returns_none(self):
        result = classify_error("Patient data retrieved successfully", None)
        assert result is None


class TestClassifyResponseError:
    """Test the activity.py integration function."""

    def test_delegates_to_taxonomy(self):
        payload = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "not-found"}],
        }
        result = classify_response_error(None, payload)
        assert result is not None
        assert result.error_category == ErrorCategory.NOT_FOUND


class TestEnvironmentConstraintCategories:
    """Verify environment constraint category set."""

    def test_environment_categories(self):
        assert ErrorCategory.NOT_FOUND in ENVIRONMENT_CONSTRAINT_CATEGORIES
        assert ErrorCategory.RATE_LIMIT in ENVIRONMENT_CONSTRAINT_CATEGORIES
        assert ErrorCategory.SERVER_ERROR in ENVIRONMENT_CONSTRAINT_CATEGORIES
        assert ErrorCategory.TIMEOUT in ENVIRONMENT_CONSTRAINT_CATEGORIES
        assert ErrorCategory.AUTH in ENVIRONMENT_CONSTRAINT_CATEGORIES

    def test_non_environment_categories(self):
        assert ErrorCategory.INVALID not in ENVIRONMENT_CONSTRAINT_CATEGORIES
        assert ErrorCategory.UNKNOWN not in ENVIRONMENT_CONSTRAINT_CATEGORIES
