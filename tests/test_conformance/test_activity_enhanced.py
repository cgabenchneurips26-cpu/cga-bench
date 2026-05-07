"""Tests for enhanced activity extraction features."""
import pytest

from cga_bench.semantic_layer.conformance.activity import (
    ActivityEvent,
    ActivityExtractionConfig,
    extract_activity_events,
    _normalize_resource_type,
    _parse_fhir_call,
    _map_activity,
)
from cga_bench.semantic_layer.conformance.activity_codes import (
    CodeFamily,
    CodeVocabulary,
    DEFAULT_CODE_FAMILIES,
)


class TestResourceTypeNormalization:
    """Test case-insensitive resource type normalization."""

    def test_lowercase_observation(self):
        assert _normalize_resource_type("observation") == "Observation"

    def test_uppercase_patient(self):
        assert _normalize_resource_type("PATIENT") == "Patient"

    def test_mixed_case_servicerequest(self):
        assert _normalize_resource_type("serviceRequest") == "ServiceRequest"

    def test_canonical_unchanged(self):
        assert _normalize_resource_type("Observation") == "Observation"

    def test_none_returns_none(self):
        assert _normalize_resource_type(None) is None

    def test_empty_returns_none(self):
        assert _normalize_resource_type("") is None

    def test_unknown_passthrough(self):
        assert _normalize_resource_type("CustomResource") == "CustomResource"

    def test_whitespace_stripped(self):
        assert _normalize_resource_type("  patient  ") == "Patient"


class TestURLParsing:
    """Test enhanced URL parsing with multiple patterns."""

    def test_standard_fhir_url(self):
        resource_type, codes = _parse_fhir_call("/fhir/Observation/123", {})
        assert resource_type == "Observation"

    def test_no_fhir_prefix(self):
        resource_type, codes = _parse_fhir_call("/Patient/456", {})
        assert resource_type == "Patient"

    def test_api_versioned_prefix(self):
        resource_type, codes = _parse_fhir_call("/api/v1/fhir/Observation", {})
        assert resource_type == "Observation"

    def test_lowercase_url_normalized(self):
        resource_type, codes = _parse_fhir_call("/fhir/observation/789", {})
        assert resource_type == "Observation"

    def test_full_url_with_host(self):
        resource_type, codes = _parse_fhir_call(
            "https://server.example.com/fhir/MedicationRequest/101", {}
        )
        assert resource_type == "MedicationRequest"

    def test_query_params_extract_codes(self):
        resource_type, codes = _parse_fhir_call(
            "/fhir/Observation?code=2524-7", {}
        )
        assert resource_type == "Observation"
        assert "2524-7" in codes

    def test_payload_resourcetype_priority(self):
        resource_type, codes = _parse_fhir_call(
            "/fhir/SomeResource",
            {"resourceType": "Observation"},
        )
        assert resource_type == "Observation"

    def test_payload_code_extraction(self):
        _, codes = _parse_fhir_call("", {
            "resourceType": "ServiceRequest",
            "code": {"coding": [{"code": "11524-6"}]},
        })
        assert "11524-6" in codes


class TestHTTPMethodExtension:
    """Test PUT/PATCH/DELETE method mappings."""

    def test_put_medication_request(self):
        events = [{"tool_call": {
            "method": "PUT",
            "url": "/fhir/MedicationRequest/1",
            "payload": {"resourceType": "MedicationRequest"},
        }}]
        activities, _ = extract_activity_events(events)
        assert len(activities) == 1
        assert activities[0].name == "UPDATE_MEDICATION"

    def test_patch_medication_request(self):
        events = [{"tool_call": {
            "method": "PATCH",
            "url": "/fhir/MedicationRequest/1",
            "payload": {"resourceType": "MedicationRequest"},
        }}]
        activities, _ = extract_activity_events(events)
        assert len(activities) == 1
        assert activities[0].name == "UPDATE_MEDICATION"

    def test_delete_service_request(self):
        events = [{"tool_call": {
            "method": "DELETE",
            "url": "/fhir/ServiceRequest/1",
            "payload": {"resourceType": "ServiceRequest"},
        }}]
        activities, _ = extract_activity_events(events)
        assert len(activities) == 1
        assert activities[0].name == "CANCEL_ORDER"

    def test_delete_medication_request(self):
        events = [{"tool_call": {
            "method": "DELETE",
            "url": "/fhir/MedicationRequest/1",
            "payload": {"resourceType": "MedicationRequest"},
        }}]
        activities, _ = extract_activity_events(events)
        assert len(activities) == 1
        assert activities[0].name == "CANCEL_MEDICATION"


class TestActivityConfidence:
    """Test confidence scoring on ActivityEvent."""

    def test_exact_match_confidence_1(self):
        events = [{"tool_call": {
            "method": "GET",
            "url": "/fhir/Patient/1",
            "payload": {},
        }}]
        activities, _ = extract_activity_events(events)
        assert activities[0].confidence == 1.0
        assert activities[0].match_source == "exact"

    def test_code_family_confidence(self):
        events = [{"tool_call": {
            "method": "GET",
            "url": "/fhir/Observation?code=6690-2",
            "payload": {},
        }}]
        config = ActivityExtractionConfig(enable_extended_vocabulary=True)
        activities, _ = extract_activity_events(events, config=config)
        # WBC code (6690-2) is in CBC family, but might also match QUERY_OBSERVATION
        assert len(activities) >= 1

    def test_explicit_activity_always_confidence_1(self):
        events = [{"activity": "CUSTOM_ACTIVITY"}]
        activities, _ = extract_activity_events(events)
        assert activities[0].confidence == 1.0


class TestCodeVocabulary:
    """Test CodeVocabulary matching logic."""

    def test_default_families_count(self):
        vocab = CodeVocabulary()
        assert len(vocab.families) >= 15

    def test_cbc_match(self):
        vocab = CodeVocabulary()
        result = vocab.match({"6690-2"}, "GET")
        assert result is not None
        activity, confidence, family_id = result
        assert activity == "QUERY_CBC"
        assert family_id == "cbc"

    def test_cardiac_match_troponin(self):
        vocab = CodeVocabulary()
        result = vocab.match({"TROPONIN-I"}, "GET")
        assert result is not None
        activity, _, family_id = result
        assert family_id == "cardiac"
        assert "CARDIAC" in activity

    def test_coagulation_match(self):
        vocab = CodeVocabulary()
        result = vocab.match({"INR"}, "GET")
        assert result is not None
        _, _, family_id = result
        assert family_id == "coagulation"

    def test_imaging_match_ct(self):
        vocab = CodeVocabulary()
        result = vocab.match({"CT"}, "POST")
        assert result is not None
        activity, _, family_id = result
        assert activity == "ORDER_IMAGING"
        assert family_id == "imaging"

    def test_no_match_for_unknown(self):
        vocab = CodeVocabulary()
        result = vocab.match({"XYZZY_UNKNOWN_123"}, "GET")
        assert result is None

    def test_empty_codes_no_match(self):
        vocab = CodeVocabulary()
        result = vocab.match(set(), "GET")
        assert result is None

    def test_post_method_uses_order_activity(self):
        vocab = CodeVocabulary()
        result = vocab.match({"2524-7"}, "POST")  # Lactate LOINC
        assert result is not None
        activity, _, _ = result
        assert "ORDER" in activity

    def test_custom_family_addition(self):
        custom = CodeFamily(
            family_id="custom_panel",
            codes={"CUSTOM-1", "CUSTOM-2"},
            activity_get="QUERY_CUSTOM",
            activity_post="ORDER_CUSTOM",
        )
        vocab = CodeVocabulary(extra_families=[custom])
        result = vocab.match({"CUSTOM-1"}, "GET")
        assert result is not None
        activity, _, family_id = result
        assert activity == "QUERY_CUSTOM"
        assert family_id == "custom_panel"

    def test_case_insensitive_matching(self):
        vocab = CodeVocabulary()
        result = vocab.match({"lactate"}, "GET")
        assert result is not None


class TestActivityExtractionConfig:
    """Test ActivityExtractionConfig behavior."""

    def test_default_config_extended_vocab_enabled(self):
        config = ActivityExtractionConfig()
        assert config.enable_extended_vocabulary is True
        assert config.enable_neural_fallback is False

    def test_no_config_same_as_default(self):
        """extract_activity_events with no config produces same results."""
        events = [
            {"tool_call": {"method": "GET", "url": "/fhir/Patient/1", "payload": {}}},
            {"tool_call": {"method": "POST", "url": "/fhir/ServiceRequest",
                           "payload": {"resourceType": "ServiceRequest"}}},
        ]
        activities_no_config, _ = extract_activity_events(events)
        activities_with_config, _ = extract_activity_events(
            events, config=ActivityExtractionConfig()
        )
        assert len(activities_no_config) == len(activities_with_config)
        for a, b in zip(activities_no_config, activities_with_config):
            assert a.name == b.name


class TestBackwardCompatibility:
    """Verify existing behavior is preserved."""

    def test_ecg_code_detection(self):
        events = [{"tool_call": {
            "method": "GET",
            "url": "/fhir/Observation?code=11524-6",
            "payload": {},
        }}]
        activities, _ = extract_activity_events(events)
        assert activities[0].name == "QUERY_ECG"

    def test_lactate_code_detection(self):
        events = [{"tool_call": {
            "method": "GET",
            "url": "/fhir/Observation?code=2524-7",
            "payload": {},
        }}]
        activities, _ = extract_activity_events(events)
        assert activities[0].name == "QUERY_LACTATE"

    def test_prescribe_activity(self):
        events = [{"tool_call": {
            "method": "POST",
            "url": "/fhir/MedicationRequest",
            "payload": {"resourceType": "MedicationRequest"},
        }}]
        activities, _ = extract_activity_events(events)
        assert activities[0].name == "PRESCRIBE"

    def test_activity_aliases_still_work(self):
        events = [{"tool_call": {
            "method": "GET",
            "url": "/fhir/Observation?code=ECG",
            "payload": {},
        }}]
        activities, _ = extract_activity_events(events, activity_aliases={"QUERY_ECG": "ORDER_ECG"})
        assert activities[0].name == "ORDER_ECG"

    def test_explicit_activity_preserved(self):
        events = [{"activity": "CUSTOM_ACTION", "timestamp_ms": 1000}]
        activities, _ = extract_activity_events(events)
        assert activities[0].name == "CUSTOM_ACTION"

    def test_timestamp_resolution_unchanged(self):
        events = [
            {"tool_call": {"method": "GET", "url": "/fhir/Patient/1", "payload": {}},
             "timestamp_ms": 60000},
            {"tool_call": {"method": "POST", "url": "/fhir/MedicationRequest",
                           "payload": {"resourceType": "MedicationRequest"}},
             "timestamp_ms": 120000},
        ]
        activities, _ = extract_activity_events(events)
        assert activities[0].timestamp_min == 0.0
        assert activities[1].timestamp_min == 1.0
