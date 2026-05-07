from __future__ import annotations

from cga_bench.semantic_layer.external.fhir_parser import (
    parse_fhir_bundle,
    parse_fhir_condition,
    parse_fhir_diagnostic_report,
    parse_fhir_medication_request,
    parse_fhir_observation,
    parse_fhir_patient,
    parse_fhir_resource,
    parse_fhir_service_request,
    try_parse_fhir_payload,
)
from cga_bench.semantic_layer.external.medagentbench import _parse_observed_event_actions


class TestParseFhirPatient:
    def test_patient_with_name_and_dob(self):
        resource = {
            "resourceType": "Patient",
            "name": [{"family": "Smith", "given": ["John"]}],
            "birthDate": "1990-01-15",
        }
        actions, evidence = parse_fhir_patient(resource)
        assert "search_by_name_dob" in actions
        assert evidence.get("history") is True

    def test_patient_with_identifier_only(self):
        resource = {
            "resourceType": "Patient",
            "identifier": [{"system": "http://hospital.org", "value": "12345"}],
        }
        actions, evidence = parse_fhir_patient(resource)
        assert "get_patient_birthdate" in actions
        assert evidence.get("history") is True


class TestParseFhirObservation:
    def test_post_observation_is_vital_sign(self):
        resource = {"resourceType": "Observation"}
        actions, evidence = parse_fhir_observation(resource, method="POST")
        assert "post_vital_sign" in actions
        assert evidence.get("vitals") is True

    def test_observation_with_loinc_potassium(self):
        resource = {
            "resourceType": "Observation",
            "code": {"coding": [{"code": "2823-3", "display": "Potassium"}]},
        }
        actions, evidence = parse_fhir_observation(resource)
        assert "check_potassium_level" in actions
        assert evidence.get("labs") is True

    def test_observation_with_loinc_hba1c(self):
        resource = {
            "resourceType": "Observation",
            "code": {"coding": [{"code": "4548-4", "display": "HbA1c"}]},
        }
        actions, evidence = parse_fhir_observation(resource)
        assert "retrieve_hba1c" in actions

    def test_observation_with_ecg_code(self):
        resource = {
            "resourceType": "Observation",
            "code": {"coding": [{"code": "11524-6", "display": "ECG study"}]},
        }
        actions, evidence = parse_fhir_observation(resource)
        assert "order_ecg" in actions
        assert evidence.get("imaging") is True

    def test_observation_vital_signs_category(self):
        resource = {
            "resourceType": "Observation",
            "code": {"coding": [{"code": "99999-9", "display": "Unknown"}]},
            "category": [{"coding": [{"code": "vital-signs"}]}],
        }
        actions, evidence = parse_fhir_observation(resource)
        assert "query_vital_signs" in actions
        assert evidence.get("vitals") is True

    def test_observation_fallback_to_lab(self):
        resource = {
            "resourceType": "Observation",
            "code": {"coding": [{"code": "99999-9", "display": "Unknown test"}]},
        }
        actions, evidence = parse_fhir_observation(resource)
        assert "query_lab_results" in actions
        assert evidence.get("labs") is True

    def test_observation_blood_pressure(self):
        resource = {
            "resourceType": "Observation",
            "code": {"coding": [{"code": "55284-4", "display": "Blood Pressure"}]},
        }
        actions, evidence = parse_fhir_observation(resource)
        assert "measure_blood_pressure" in actions
        assert evidence.get("vitals") is True


class TestParseFhirServiceRequest:
    def test_basic_service_request(self):
        resource = {"resourceType": "ServiceRequest"}
        actions, evidence = parse_fhir_service_request(resource)
        assert "create_referral_with_given_text" in actions

    def test_service_request_with_ecg(self):
        resource = {
            "resourceType": "ServiceRequest",
            "code": {"coding": [{"code": "ECG", "display": "12-lead ECG"}]},
        }
        actions, evidence = parse_fhir_service_request(resource)
        assert "order_ecg" in actions
        assert evidence.get("imaging") is True


class TestParseFhirMedicationRequest:
    def test_medication_with_codeable_concept(self):
        resource = {
            "resourceType": "MedicationRequest",
            "medicationCodeableConcept": {
                "coding": [{"code": "rxnorm:1234", "display": "Metformin"}],
            },
        }
        actions, evidence = parse_fhir_medication_request(resource)
        assert any("prescribe_" in a for a in actions)
        assert evidence.get("medications") is True

    def test_medication_without_concept(self):
        resource = {"resourceType": "MedicationRequest"}
        actions, evidence = parse_fhir_medication_request(resource)
        assert "prescribe_medication" in actions
        assert evidence.get("medications") is True


class TestParseFhirCondition:
    def test_condition_resource(self):
        resource = {"resourceType": "Condition"}
        actions, evidence = parse_fhir_condition(resource)
        assert "document_diagnosis" in actions
        assert evidence.get("diagnosis") is True


class TestParseFhirDiagnosticReport:
    def test_diagnostic_report_basic(self):
        resource = {"resourceType": "DiagnosticReport"}
        actions, evidence = parse_fhir_diagnostic_report(resource)
        assert "review_diagnostic_report" in actions

    def test_diagnostic_report_with_ecg(self):
        resource = {
            "resourceType": "DiagnosticReport",
            "code": {"coding": [{"code": "11524-6", "display": "ECG"}]},
        }
        actions, evidence = parse_fhir_diagnostic_report(resource)
        assert "order_ecg" in actions
        assert evidence.get("imaging") is True


class TestParseFhirBundle:
    def test_bundle_with_multiple_entries(self):
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Patient",
                        "name": [{"family": "Doe"}],
                        "birthDate": "1985-03-20",
                    },
                },
                {
                    "resource": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "2823-3", "display": "Potassium"}]},
                    },
                },
                {
                    "resource": {
                        "resourceType": "MedicationRequest",
                        "medicationCodeableConcept": {
                            "coding": [{"code": "rx1", "display": "Insulin"}],
                        },
                    },
                },
            ],
        }
        actions, evidence = parse_fhir_bundle(bundle)
        assert "search_by_name_dob" in actions
        assert "check_potassium_level" in actions
        assert any("prescribe_" in a for a in actions)
        assert evidence.get("history") is True
        assert evidence.get("labs") is True
        assert evidence.get("medications") is True

    def test_bundle_with_post_observation(self):
        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "request": {"method": "POST"},
                    "resource": {"resourceType": "Observation"},
                },
            ],
        }
        actions, evidence = parse_fhir_bundle(bundle)
        assert "post_vital_sign" in actions
        assert evidence.get("vitals") is True

    def test_empty_bundle(self):
        bundle = {"resourceType": "Bundle", "entry": []}
        actions, evidence = parse_fhir_bundle(bundle)
        assert actions == []
        assert evidence == {}


class TestTryParseFhirPayload:
    def test_bundle_payload(self):
        result = try_parse_fhir_payload({"resourceType": "Bundle", "entry": []})
        assert result is not None
        actions, evidence = result
        assert isinstance(actions, list)

    def test_single_resource_payload(self):
        result = try_parse_fhir_payload({"resourceType": "Condition"})
        assert result is not None
        actions, _ = result
        assert "document_diagnosis" in actions

    def test_non_fhir_payload_returns_none(self):
        assert try_parse_fhir_payload({"random": "data"}) is None

    def test_non_dict_returns_none(self):
        assert try_parse_fhir_payload("not a dict") is None
        assert try_parse_fhir_payload(None) is None


class TestFhirIntegrationWithMedAgentBench:
    def test_fhir_payload_takes_priority_over_url_parsing(self):
        events = [
            {
                "tool_call": {
                    "method": "GET",
                    "url": "http://fhir.server/Observation?code=2823-3",
                    "payload": {
                        "resourceType": "Observation",
                        "code": {"coding": [{"code": "4548-4", "display": "HbA1c"}]},
                    },
                },
            },
        ]
        actions, evidence = _parse_observed_event_actions(events)
        assert "retrieve_hba1c" in actions

    def test_url_fallback_when_no_fhir_payload(self):
        events = [
            {
                "tool_call": {
                    "method": "GET",
                    "url": "http://fhir.server/Observation?code=2823-3",
                },
            },
        ]
        actions, evidence = _parse_observed_event_actions(events)
        assert "check_potassium_level" in actions
        assert evidence["labs"] is True

    def test_fhir_bundle_payload_in_event(self):
        events = [
            {
                "tool_call": {
                    "method": "POST",
                    "url": "http://fhir.server/",
                    "payload": {
                        "resourceType": "Bundle",
                        "entry": [
                            {
                                "resource": {
                                    "resourceType": "MedicationRequest",
                                    "medicationCodeableConcept": {
                                        "coding": [{"code": "rx1", "display": "Aspirin"}],
                                    },
                                },
                            },
                        ],
                    },
                },
                "timestamp_ms": 1000,
            },
        ]
        actions, evidence = _parse_observed_event_actions(events)
        assert any("prescribe_" in a for a in actions)
        assert evidence["medications"] is True
        assert evidence["timestamps"] is True

    def test_mixed_fhir_and_url_events(self):
        events = [
            {
                "tool_call": {
                    "method": "GET",
                    "url": "http://fhir.server/Patient?family=Smith&given=John&birthdate=1990-01-01",
                },
            },
            {
                "tool_call": {
                    "method": "POST",
                    "url": "http://fhir.server/",
                    "payload": {
                        "resourceType": "Condition",
                        "code": {"coding": [{"code": "E11", "display": "Type 2 Diabetes"}]},
                    },
                },
            },
        ]
        actions, evidence = _parse_observed_event_actions(events)
        assert "search_by_name_dob" in actions
        assert "document_diagnosis" in actions
        assert evidence["history"] is True
        assert evidence["diagnosis"] is True
