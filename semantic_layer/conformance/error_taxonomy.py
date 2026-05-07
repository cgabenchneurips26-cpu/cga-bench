"""
Error Taxonomy for FHIR OperationOutcome classification.

Classifies errors into categories to distinguish environment constraints
(not the agent's fault) from agent errors (penalized).
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional


class ErrorCategory(str, Enum):
    """Error category classification based on OperationOutcome codes."""
    AUTH = "auth"                    # Authentication/authorization denied
    NOT_FOUND = "not_found"         # Resource not found
    INVALID = "invalid"             # Invalid request (agent error)
    RATE_LIMIT = "rate_limit"       # Environment rate limiting
    SERVER_ERROR = "server_error"   # Server-side failure
    TIMEOUT = "timeout"             # Request timeout
    UNKNOWN = "unknown"             # Unclassifiable


# OperationOutcome.issue[].code -> ErrorCategory mapping
# Reference: https://www.hl7.org/fhir/valueset-issue-type.html
_ISSUE_CODE_MAP: Dict[str, ErrorCategory] = {
    # Security/Auth codes
    "login": ErrorCategory.AUTH,
    "unknown": ErrorCategory.AUTH,
    "expired": ErrorCategory.AUTH,
    "forbidden": ErrorCategory.AUTH,
    "suppressed": ErrorCategory.AUTH,
    "security": ErrorCategory.AUTH,

    # Not-found codes
    "not-found": ErrorCategory.NOT_FOUND,
    "deleted": ErrorCategory.NOT_FOUND,
    "no-store": ErrorCategory.NOT_FOUND,
    "not-supported": ErrorCategory.NOT_FOUND,

    # Invalid request codes (agent error)
    "invalid": ErrorCategory.INVALID,
    "structure": ErrorCategory.INVALID,
    "required": ErrorCategory.INVALID,
    "value": ErrorCategory.INVALID,
    "invariant": ErrorCategory.INVALID,
    "business-rule": ErrorCategory.INVALID,
    "code-invalid": ErrorCategory.INVALID,
    "extension": ErrorCategory.INVALID,
    "too-costly": ErrorCategory.INVALID,
    "duplicate": ErrorCategory.INVALID,
    "multiple-matches": ErrorCategory.INVALID,
    "conflict": ErrorCategory.INVALID,

    # Rate limit / throttling
    "throttled": ErrorCategory.RATE_LIMIT,
    "too-long": ErrorCategory.RATE_LIMIT,

    # Server error codes
    "exception": ErrorCategory.SERVER_ERROR,
    "transient": ErrorCategory.SERVER_ERROR,
    "lock-error": ErrorCategory.SERVER_ERROR,
    "incomplete": ErrorCategory.SERVER_ERROR,

    # Timeout
    "timeout": ErrorCategory.TIMEOUT,
}

# Categories that represent environment constraints (agent not at fault)
ENVIRONMENT_CONSTRAINT_CATEGORIES = frozenset({
    ErrorCategory.NOT_FOUND,
    ErrorCategory.RATE_LIMIT,
    ErrorCategory.SERVER_ERROR,
    ErrorCategory.TIMEOUT,
    ErrorCategory.AUTH,
})


@dataclass
class ClassifiedError:
    """Result of error classification."""
    error_category: ErrorCategory
    issue_code: Optional[str]           # OperationOutcome.issue[].code
    issue_severity: Optional[str]       # fatal/error/warning/information
    is_environment_constraint: bool     # True -> penalty exemption
    diagnostics: Optional[str]
    raw_event: Dict[str, Any]


def classify_error(
    response_text: Optional[str],
    response_payload: Optional[Dict[str, Any]],
) -> Optional[ClassifiedError]:
    """
    Classify an error from FHIR OperationOutcome or response text.

    Args:
        response_text: Raw response text (may contain error messages)
        response_payload: Parsed JSON response (may be OperationOutcome)

    Returns:
        ClassifiedError if an error is detected, None otherwise
    """
    # Try OperationOutcome first
    if isinstance(response_payload, dict) and response_payload.get("resourceType") == "OperationOutcome":
        return _classify_operation_outcome(response_payload)

    # Try text-based detection
    if response_text:
        return _classify_text_error(response_text)

    return None


def _classify_operation_outcome(payload: Dict[str, Any]) -> ClassifiedError:
    """Parse FHIR OperationOutcome and classify the error."""
    issues: List[Dict[str, Any]] = payload.get("issue", [])

    # Use the most severe issue for classification
    best_issue: Optional[Dict[str, Any]] = None
    best_severity_rank = -1

    severity_ranks = {"fatal": 4, "error": 3, "warning": 2, "information": 1}

    for issue in issues:
        severity = issue.get("severity", "error")
        rank = severity_ranks.get(severity, 0)
        if rank > best_severity_rank:
            best_severity_rank = rank
            best_issue = issue

    if not best_issue:
        return ClassifiedError(
            error_category=ErrorCategory.UNKNOWN,
            issue_code=None,
            issue_severity=None,
            is_environment_constraint=False,
            diagnostics=None,
            raw_event=payload,
        )

    issue_code = best_issue.get("code")
    issue_severity = best_issue.get("severity")
    diagnostics = best_issue.get("diagnostics")

    category = _ISSUE_CODE_MAP.get(issue_code, ErrorCategory.UNKNOWN) if issue_code else ErrorCategory.UNKNOWN
    is_env = category in ENVIRONMENT_CONSTRAINT_CATEGORIES

    return ClassifiedError(
        error_category=category,
        issue_code=issue_code,
        issue_severity=issue_severity,
        is_environment_constraint=is_env,
        diagnostics=diagnostics,
        raw_event=payload,
    )


def _classify_text_error(text: str) -> Optional[ClassifiedError]:
    """Classify errors from response text patterns."""
    text_stripped = text.strip()

    # HTTP error patterns
    if "Client Error" in text_stripped:
        if "404" in text_stripped:
            category = ErrorCategory.NOT_FOUND
        elif "401" in text_stripped or "403" in text_stripped:
            category = ErrorCategory.AUTH
        elif "429" in text_stripped:
            category = ErrorCategory.RATE_LIMIT
        elif "400" in text_stripped or "422" in text_stripped:
            category = ErrorCategory.INVALID
        else:
            category = ErrorCategory.INVALID
    elif "Server Error" in text_stripped:
        if "504" in text_stripped or "timeout" in text_stripped.lower():
            category = ErrorCategory.TIMEOUT
        else:
            category = ErrorCategory.SERVER_ERROR
    elif text_stripped.startswith("Error in sending the GET request"):
        category = ErrorCategory.SERVER_ERROR
    elif "timeout" in text_stripped.lower() or "timed out" in text_stripped.lower():
        category = ErrorCategory.TIMEOUT
    else:
        return None

    is_env = category in ENVIRONMENT_CONSTRAINT_CATEGORIES

    return ClassifiedError(
        error_category=category,
        issue_code=None,
        issue_severity="error",
        is_environment_constraint=is_env,
        diagnostics=text_stripped[:200],
        raw_event={"response_text": text_stripped},
    )
