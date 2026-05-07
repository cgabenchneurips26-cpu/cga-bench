"""Tests for enhanced error classification with chains, contextual severity, recovery."""
import json
import pytest

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.conformance.error_taxonomy import (
    ClassifiedError,
    ErrorCategory,
    classify_error,
)
from cga_bench.semantic_layer.conformance.error_classifier import (
    ContextualSeverity,
    EnrichedClassifiedError,
    ErrorChain,
    ErrorClassificationConfig,
    ErrorClassifier,
    RecoveryInfo,
    _BASE_SEVERITY_MAP,
    _RECOVERABILITY_MAP,
)


def _make_event(name, timestamp_min=0.0, url="", response_text=None):
    """Create an ActivityEvent for testing."""
    raw = {}
    if url:
        raw["tool_call"] = {"method": "GET", "url": url}
    if response_text:
        raw["response_text"] = response_text
    return ActivityEvent(name=name, timestamp_min=timestamp_min, raw_event=raw)


def _make_error_event(name, timestamp_min=0.0, url="/fhir/Observation", issue_code="not-found"):
    """Create an event with a FHIR OperationOutcome error."""
    payload = {
        "resourceType": "OperationOutcome",
        "issue": [{"severity": "error", "code": issue_code}],
    }
    return ActivityEvent(
        name=name,
        timestamp_min=timestamp_min,
        raw_event={
            "tool_call": {"method": "GET", "url": url},
            "response_text": json.dumps(payload),
        },
    )


def _make_text_error_event(name, timestamp_min=0.0, url="/fhir/Observation", error_text="404 Client Error"):
    """Create an event with a text-based error."""
    return ActivityEvent(
        name=name,
        timestamp_min=timestamp_min,
        raw_event={
            "tool_call": {"method": "GET", "url": url},
            "response_text": error_text,
        },
    )


class TestErrorClassifierBasic:
    """Test basic error classification without enrichment."""

    def test_no_errors_returns_empty(self):
        events = [_make_event("QUERY_PATIENT", 0.0, "/fhir/Patient")]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert result == []

    def test_single_error_classified(self):
        events = [_make_error_event("QUERY_OBSERVATION", 0.0, "/fhir/Observation", "not-found")]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert len(result) == 1
        assert result[0].error_category == ErrorCategory.NOT_FOUND

    def test_non_error_events_excluded(self):
        events = [
            _make_event("QUERY_PATIENT", 0.0, "/fhir/Patient"),
            _make_error_event("QUERY_OBS", 1.0, "/fhir/Observation", "invalid"),
            _make_event("ORDER_LAB", 2.0, "/fhir/ServiceRequest"),
        ]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert len(result) == 1
        assert result[0].event_index == 1

    def test_default_config_no_enrichment(self):
        events = [_make_error_event("QUERY_OBS", 0.0)]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert result[0].contextual_severity is None
        assert result[0].chain_id is None
        assert result[0].recovery_info is None

    def test_preserves_error_category(self):
        events = [_make_error_event("QUERY_OBS", 0.0, issue_code="invalid")]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert result[0].error_category == ErrorCategory.INVALID

    def test_preserves_environment_constraint(self):
        events = [_make_error_event("QUERY_OBS", 0.0, issue_code="not-found")]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert result[0].is_environment_constraint is True

    def test_text_error_classified(self):
        events = [_make_text_error_event("QUERY_OBS", 0.0, error_text="500 Server Error")]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert len(result) == 1
        assert result[0].error_category == ErrorCategory.SERVER_ERROR


class TestChainDetection:
    """Test error chain detection algorithm."""

    def test_two_consecutive_errors_form_chain(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 0.5, "/fhir/Observation", "timeout"),
        ]
        config = ErrorClassificationConfig(enable_chain_detection=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        assert result[0].chain_id is not None
        assert result[0].chain_id == result[1].chain_id

    def test_gap_breaks_chain(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_event("QUERY_PATIENT", 1.0, "/fhir/Patient"),
            _make_event("ORDER_LAB", 2.0, "/fhir/ServiceRequest"),
            _make_event("PRESCRIBE", 3.0, "/fhir/MedicationRequest"),
            _make_event("QUERY_VITAL", 4.0, "/fhir/Observation"),
            _make_event("QUERY_ECG", 5.0, "/fhir/Observation"),
            # Index 6, gap > max_chain_window=5
            _make_error_event("QUERY_OBS", 6.0, "/fhir/Observation", "timeout"),
        ]
        config = ErrorClassificationConfig(enable_chain_detection=True, max_chain_window=5)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        # Two errors, but gap is 6 indices apart
        assert len(result) == 2
        assert result[0].chain_id is None
        assert result[1].chain_id is None

    def test_different_resources_break_chain(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_MED", 0.5, "/fhir/MedicationRequest", "not-found"),
        ]
        config = ErrorClassificationConfig(enable_chain_detection=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        assert result[0].chain_id is None
        assert result[1].chain_id is None

    def test_time_window_breaks_chain(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 5.0, "/fhir/Observation", "timeout"),
        ]
        config = ErrorClassificationConfig(
            enable_chain_detection=True, chain_time_window_minutes=2.0
        )
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        assert result[0].chain_id is None
        assert result[1].chain_id is None

    def test_multiple_chains_detected(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 0.5, "/fhir/Observation", "timeout"),
            _make_event("NORMAL", 1.0, "/fhir/Patient"),
            _make_event("NORMAL2", 2.0, "/fhir/Patient"),
            _make_event("NORMAL3", 3.0, "/fhir/Patient"),
            _make_event("NORMAL4", 4.0, "/fhir/Patient"),
            _make_event("NORMAL5", 5.0, "/fhir/Patient"),
            _make_event("NORMAL6", 6.0, "/fhir/Patient"),
            # Second chain starts far away
            _make_error_event("QUERY_MED", 7.0, "/fhir/MedicationRequest", "not-found"),
            _make_error_event("QUERY_MED", 7.5, "/fhir/MedicationRequest", "not-found"),
        ]
        config = ErrorClassificationConfig(enable_chain_detection=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        assert len(result) == 4
        chain_ids = {r.chain_id for r in result if r.chain_id}
        assert len(chain_ids) == 2

    def test_single_error_no_chain(self):
        events = [_make_error_event("QUERY_OBS", 0.0, "/fhir/Observation")]
        config = ErrorClassificationConfig(enable_chain_detection=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        assert result[0].chain_id is None

    def test_chain_root_cause_is_first(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 0.5, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 1.0, "/fhir/Observation", "timeout"),
        ]
        config = ErrorClassificationConfig(enable_chain_detection=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        assert result[0].is_chain_root is True
        assert result[1].is_chain_root is False
        assert result[2].is_chain_root is False

    def test_chain_length_correct(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 0.5, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 1.0, "/fhir/Observation", "timeout"),
        ]
        config = ErrorClassificationConfig(enable_chain_detection=True)
        classifier = ErrorClassifier(config)
        indexed_errors = classifier._extract_errors(events)
        chains = classifier.detect_chains(indexed_errors, events)
        assert len(chains) == 1
        assert chains[0].chain_length == 3


class TestContextualSeverity:
    """Test contextual severity computation."""

    def test_prescribe_error_high_context(self):
        events = [_make_error_event("PRESCRIBE_MED", 0.0, issue_code="invalid")]
        config = ErrorClassificationConfig(enable_contextual_severity=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        severity = result[0].contextual_severity
        assert severity is not None
        assert severity.context_multiplier == 1.8

    def test_query_error_low_context(self):
        events = [_make_error_event("QUERY_OBS", 0.0, issue_code="not-found")]
        config = ErrorClassificationConfig(enable_contextual_severity=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        severity = result[0].contextual_severity
        assert severity.context_multiplier == 1.0

    def test_invalid_error_high_base_severity(self):
        events = [_make_error_event("QUERY_OBS", 0.0, issue_code="invalid")]
        config = ErrorClassificationConfig(enable_contextual_severity=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        severity = result[0].contextual_severity
        assert severity.base_severity == 0.7

    def test_rate_limit_low_base_severity(self):
        events = [_make_error_event("QUERY_OBS", 0.0, issue_code="throttled")]
        config = ErrorClassificationConfig(enable_contextual_severity=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        severity = result[0].contextual_severity
        assert severity.base_severity == 0.2

    def test_recoverability_rate_limit_high(self):
        events = [_make_error_event("QUERY_OBS", 0.0, issue_code="throttled")]
        config = ErrorClassificationConfig(enable_contextual_severity=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        severity = result[0].contextual_severity
        assert severity.recoverability == 0.95

    def test_recoverability_auth_low(self):
        events = [_make_error_event("QUERY_OBS", 0.0, issue_code="forbidden")]
        config = ErrorClassificationConfig(enable_contextual_severity=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        severity = result[0].contextual_severity
        assert severity.recoverability == 0.2

    def test_final_severity_bounded_0_1(self):
        # Use extreme values to test clamping
        events = [_make_error_event("PRESCRIBE_MED", 0.0, issue_code="invalid")]
        config = ErrorClassificationConfig(
            enable_contextual_severity=True,
            severity_weights={"base": 1.0, "context": 1.0, "recoverability": 1.0, "timing": 1.0},
        )
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        severity = result[0].contextual_severity
        assert 0.0 <= severity.final_severity <= 1.0

    def test_procedure_error_high_impact(self):
        events = [_make_error_event("PERFORM_PROCEDURE", 0.0, issue_code="invalid")]
        config = ErrorClassificationConfig(enable_contextual_severity=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        severity = result[0].contextual_severity
        assert severity.clinical_impact == 0.8

    def test_order_error_moderate_impact(self):
        events = [_make_error_event("ORDER_LAB", 0.0, issue_code="invalid")]
        config = ErrorClassificationConfig(enable_contextual_severity=True)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        severity = result[0].contextual_severity
        assert severity.clinical_impact == 0.6


class TestRecoveryEvaluation:
    """Test recovery attempt detection."""

    def test_successful_recovery_detected(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 0.5, "/fhir/Observation", "timeout"),
            # Successful retry
            _make_event("QUERY_OBS", 1.0, "/fhir/Observation"),
        ]
        config = ErrorClassificationConfig(
            enable_chain_detection=True, enable_recovery_evaluation=True
        )
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        root = next(r for r in result if r.is_chain_root)
        assert root.recovery_info is not None
        assert root.recovery_info.attempted is True
        assert root.recovery_info.successful is True

    def test_no_recovery_attempt(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 0.5, "/fhir/Observation", "timeout"),
            # Different resource, not a recovery
            _make_event("QUERY_PATIENT", 1.0, "/fhir/Patient"),
        ]
        config = ErrorClassificationConfig(
            enable_chain_detection=True, enable_recovery_evaluation=True
        )
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        root = next(r for r in result if r.is_chain_root)
        assert root.recovery_info is not None
        assert root.recovery_info.attempted is False

    def test_failed_recovery_detected(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 0.5, "/fhir/Observation", "timeout"),
            # Retry that also fails
            _make_error_event("QUERY_OBS", 1.0, "/fhir/Observation", "timeout"),
        ]
        config = ErrorClassificationConfig(
            enable_chain_detection=True, enable_recovery_evaluation=True,
            max_chain_window=2,
        )
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        # All three form one chain since they're consecutive
        root = next(r for r in result if r.is_chain_root)
        # Recovery looks past the chain end
        assert root.recovery_info is not None
        assert root.recovery_info.successful is False

    def test_recovery_time_computed(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 0.5, "/fhir/Observation", "timeout"),
            _make_event("QUERY_OBS", 3.0, "/fhir/Observation"),  # recovery at t=3
        ]
        config = ErrorClassificationConfig(
            enable_chain_detection=True, enable_recovery_evaluation=True
        )
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        root = next(r for r in result if r.is_chain_root)
        assert root.recovery_info.time_to_recovery_minutes == 3.0

    def test_recovery_retry_count(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 0.5, "/fhir/Observation", "timeout"),
            _make_event("QUERY_OBS", 1.0, "/fhir/Observation"),  # 1 recovery event
        ]
        config = ErrorClassificationConfig(
            enable_chain_detection=True, enable_recovery_evaluation=True
        )
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        root = next(r for r in result if r.is_chain_root)
        assert root.recovery_info.retry_count == 1

    def test_recovery_window_bounded(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 0.5, "/fhir/Observation", "timeout"),
            _make_event("NORMAL1", 1.0, "/fhir/Patient"),
            _make_event("NORMAL2", 2.0, "/fhir/Patient"),
            _make_event("NORMAL3", 3.0, "/fhir/Patient"),
            _make_event("NORMAL4", 4.0, "/fhir/Patient"),
            _make_event("NORMAL5", 5.0, "/fhir/Patient"),
            _make_event("NORMAL6", 6.0, "/fhir/Patient"),
            # Recovery too far away (beyond max_chain_window from last error)
            _make_event("QUERY_OBS", 10.0, "/fhir/Observation"),
        ]
        config = ErrorClassificationConfig(
            enable_chain_detection=True, enable_recovery_evaluation=True,
            max_chain_window=3,
        )
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        root = next(r for r in result if r.is_chain_root)
        assert root.recovery_info.attempted is False


class TestClinicalContext:
    """Test clinical context inference."""

    def test_prescribe_context(self):
        events = [_make_error_event("PRESCRIBE_MED", 0.0)]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert result[0].clinical_context == "medication_management"

    def test_query_context(self):
        events = [_make_error_event("QUERY_OBSERVATION", 0.0)]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert result[0].clinical_context == "information_retrieval"

    def test_procedure_context(self):
        events = [_make_error_event("PERFORM_PROCEDURE", 0.0)]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert result[0].clinical_context == "procedural_intervention"

    def test_order_context(self):
        events = [_make_error_event("ORDER_LAB", 0.0)]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert result[0].clinical_context == "diagnostic_ordering"

    def test_diagnose_context(self):
        events = [_make_error_event("DIAGNOSE_PATIENT", 0.0)]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert result[0].clinical_context == "diagnostic_assessment"

    def test_unknown_context_none(self):
        events = [_make_error_event("UNKNOWN_ACTIVITY", 0.0)]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert result[0].clinical_context is None


class TestBackwardCompatibility:
    """Ensure existing classify_error() behavior unchanged."""

    def test_default_config_same_as_classify_error(self):
        payload = json.dumps({
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "not-found"}],
        })
        events = [ActivityEvent(
            name="QUERY", timestamp_min=0.0,
            raw_event={"response_text": payload}
        )]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert result[0].error_category == ErrorCategory.NOT_FOUND

    def test_disabled_features_produce_none(self):
        events = [_make_error_event("QUERY_OBS", 0.0)]
        config = ErrorClassificationConfig(
            enable_contextual_severity=False,
            enable_chain_detection=False,
            enable_recovery_evaluation=False,
        )
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        assert result[0].contextual_severity is None
        assert result[0].chain_id is None
        assert result[0].recovery_info is None

    def test_chain_detection_off_no_chains(self):
        events = [
            _make_error_event("QUERY_OBS", 0.0, "/fhir/Observation", "timeout"),
            _make_error_event("QUERY_OBS", 0.5, "/fhir/Observation", "timeout"),
        ]
        config = ErrorClassificationConfig(enable_chain_detection=False)
        classifier = ErrorClassifier(config)
        result = classifier.classify_events(events)
        assert all(r.chain_id is None for r in result)

    def test_original_classify_error_unchanged(self):
        payload = {
            "resourceType": "OperationOutcome",
            "issue": [{"severity": "error", "code": "invalid"}],
        }
        result = classify_error(None, payload)
        assert result is not None
        assert result.error_category == ErrorCategory.INVALID
        assert result.is_environment_constraint is False

    def test_issue_severity_property(self):
        events = [_make_error_event("QUERY_OBS", 0.0, issue_code="invalid")]
        classifier = ErrorClassifier()
        result = classifier.classify_events(events)
        assert result[0].issue_severity == "error"
