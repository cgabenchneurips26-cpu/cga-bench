"""Tests for enhanced OCEL object typing with FHIR, CodeFamily, and type hierarchy."""
import json
import pytest

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.export.ocel_object_typing import (
    CODE_FAMILY_TO_SUBTYPE,
    FHIR_TO_OBJECT_TYPE,
    TYPE_HIERARCHY,
    EnrichedOCELObject,
    ObjectTypeConfig,
    ObjectTypeHierarchy,
    ObjectTypeResolver,
)
from cga_bench.semantic_layer.export.ocel_exporter import (
    OCELExportConfig,
    OCELExporter,
)


def _make_event(name, url="", payload=None, method="GET"):
    raw = {}
    if url or payload:
        raw["tool_call"] = {
            "method": method,
            "url": url,
            "payload": payload or {},
        }
    return ActivityEvent(name=name, timestamp_min=0.0, raw_event=raw)


class TestFHIRObjectTyping:
    """Test FHIR resource type -> OCEL object type mapping."""

    def test_medication_request_typed(self):
        event = _make_event("PRESCRIBE", "/fhir/MedicationRequest", {"resourceType": "MedicationRequest"}, "POST")
        resolver = ObjectTypeResolver(ObjectTypeConfig(enable_code_subtypes=False))
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert objects[0][1] == "medication_order"

    def test_service_request_typed(self):
        event = _make_event("ORDER_TEST", "/fhir/ServiceRequest", {"resourceType": "ServiceRequest"}, "POST")
        resolver = ObjectTypeResolver(ObjectTypeConfig(enable_code_subtypes=False))
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert objects[0][1] == "lab_order"

    def test_observation_typed(self):
        event = _make_event("QUERY_OBSERVATION", "/fhir/Observation/123", {}, "GET")
        resolver = ObjectTypeResolver(ObjectTypeConfig(enable_code_subtypes=False))
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert objects[0][1] == "observation"

    def test_procedure_typed(self):
        event = _make_event("PERFORM_PROCEDURE", "/fhir/Procedure", {"resourceType": "Procedure"}, "POST")
        resolver = ObjectTypeResolver(ObjectTypeConfig(enable_code_subtypes=False))
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert objects[0][1] == "procedure"

    def test_condition_typed_as_diagnosis(self):
        event = _make_event("DIAGNOSE", "/fhir/Condition", {"resourceType": "Condition"}, "POST")
        resolver = ObjectTypeResolver(ObjectTypeConfig(enable_code_subtypes=False))
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert objects[0][1] == "diagnosis"

    def test_unknown_resource_fallback(self):
        event = _make_event("QUERY_CUSTOM", "/fhir/CustomResource/1", {}, "GET")
        resolver = ObjectTypeResolver(ObjectTypeConfig(enable_code_subtypes=False))
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert objects[0][1] == "order"  # Fallback from QUERY_ pattern

    def test_no_url_no_payload_fallback(self):
        event = _make_event("PRESCRIBE")
        resolver = ObjectTypeResolver(ObjectTypeConfig())
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert "medication" in objects[0][1]


class TestCodeFamilySubtyping:
    """Test CodeVocabulary-driven specific subtypes."""

    def test_cbc_code_produces_cbc_test(self):
        event = _make_event(
            "QUERY_OBSERVATION", "/fhir/Observation?code=6690-2", {}, "GET"
        )
        resolver = ObjectTypeResolver(ObjectTypeConfig())
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert objects[0][1] == "cbc_test"

    def test_cardiac_code_produces_cardiac_markers(self):
        event = _make_event(
            "QUERY_OBSERVATION", "/fhir/Observation?code=TROPONIN-I", {}, "GET"
        )
        resolver = ObjectTypeResolver(ObjectTypeConfig())
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert objects[0][1] == "cardiac_markers"

    def test_imaging_code_produces_imaging_test(self):
        event = _make_event(
            "ORDER_IMAGING", "/fhir/ServiceRequest",
            {"resourceType": "ServiceRequest", "code": {"coding": [{"code": "CT"}]}},
            "POST"
        )
        resolver = ObjectTypeResolver(ObjectTypeConfig())
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert objects[0][1] == "imaging_test"

    def test_ecg_code_produces_ecg_test(self):
        event = _make_event(
            "QUERY_ECG", "/fhir/Observation?code=11524-6", {}, "GET"
        )
        resolver = ObjectTypeResolver(ObjectTypeConfig())
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert objects[0][1] == "ecg_test"

    def test_no_code_falls_through_to_fhir(self):
        event = _make_event(
            "QUERY_OBSERVATION", "/fhir/Observation/123", {}, "GET"
        )
        resolver = ObjectTypeResolver(ObjectTypeConfig())
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert objects[0][1] == "observation"

    def test_code_subtypes_disabled_uses_fhir(self):
        event = _make_event(
            "QUERY_OBSERVATION", "/fhir/Observation?code=6690-2", {}, "GET"
        )
        resolver = ObjectTypeResolver(ObjectTypeConfig(enable_code_subtypes=False))
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert len(objects) == 1
        assert objects[0][1] == "observation"  # FHIR type, not cbc_test


class TestTypeHierarchy:
    """Test type hierarchy resolution."""

    def test_cbc_test_hierarchy(self):
        resolver = ObjectTypeResolver()
        path = resolver.get_type_hierarchy("cbc_test")
        assert path == ["cbc_test", "lab_test", "order"]

    def test_ecg_test_hierarchy(self):
        resolver = ObjectTypeResolver()
        path = resolver.get_type_hierarchy("ecg_test")
        assert path == ["ecg_test", "imaging_test", "order"]

    def test_medication_order_hierarchy(self):
        resolver = ObjectTypeResolver()
        path = resolver.get_type_hierarchy("medication_order")
        assert path == ["medication_order", "order"]

    def test_patient_no_parent(self):
        resolver = ObjectTypeResolver()
        path = resolver.get_type_hierarchy("patient")
        assert path == ["patient"]

    def test_unknown_type_returns_self(self):
        resolver = ObjectTypeResolver()
        path = resolver.get_type_hierarchy("unknown_xyz")
        assert path == ["unknown_xyz"]

    def test_procedure_no_parent(self):
        resolver = ObjectTypeResolver()
        path = resolver.get_type_hierarchy("procedure")
        assert path == ["procedure"]

    def test_all_type_hierarchies_populated(self):
        resolver = ObjectTypeResolver()
        hierarchies = resolver.get_all_type_hierarchies()
        assert len(hierarchies) > 15
        assert "cbc_test" in hierarchies
        assert "patient" in hierarchies


class TestEnrichment:
    """Test attribute enrichment with clinical codes."""

    def test_enriched_object_has_fhir_type(self):
        event = _make_event(
            "QUERY_OBSERVATION", "/fhir/Observation?code=6690-2", {}, "GET"
        )
        resolver = ObjectTypeResolver(ObjectTypeConfig())
        enriched = resolver.resolve_enriched(event, "ep1", 0)
        assert len(enriched) == 1
        assert enriched[0].fhir_resource_type == "Observation"

    def test_enriched_object_has_clinical_domain(self):
        event = _make_event(
            "QUERY_OBSERVATION", "/fhir/Observation?code=6690-2", {}, "GET"
        )
        resolver = ObjectTypeResolver(ObjectTypeConfig())
        enriched = resolver.resolve_enriched(event, "ep1", 0)
        assert enriched[0].clinical_domain == "hematology"

    def test_enriched_object_has_codes(self):
        event = _make_event(
            "QUERY_OBSERVATION", "/fhir/Observation?code=6690-2", {}, "GET"
        )
        resolver = ObjectTypeResolver(ObjectTypeConfig())
        enriched = resolver.resolve_enriched(event, "ep1", 0)
        assert "6690-2" in enriched[0].codes

    def test_enriched_object_has_parent_type(self):
        event = _make_event(
            "QUERY_OBSERVATION", "/fhir/Observation?code=6690-2", {}, "GET"
        )
        resolver = ObjectTypeResolver(ObjectTypeConfig())
        enriched = resolver.resolve_enriched(event, "ep1", 0)
        assert enriched[0].parent_type == "lab_test"

    def test_enriched_no_hierarchy_when_disabled(self):
        event = _make_event(
            "QUERY_OBSERVATION", "/fhir/Observation?code=6690-2", {}, "GET"
        )
        config = ObjectTypeConfig(enable_type_hierarchy=False)
        resolver = ObjectTypeResolver(config)
        enriched = resolver.resolve_enriched(event, "ep1", 0)
        assert enriched[0].parent_type is None


class TestCustomMappings:
    """Test custom type mappings override."""

    def test_custom_mapping_takes_priority(self):
        config = ObjectTypeConfig(
            custom_type_mappings={"MY_ACTIVITY": "my_custom_type"}
        )
        event = _make_event("MY_ACTIVITY", "/fhir/Observation/1")
        resolver = ObjectTypeResolver(config)
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert objects[0][1] == "my_custom_type"

    def test_custom_mapping_does_not_affect_others(self):
        config = ObjectTypeConfig(
            custom_type_mappings={"MY_ACTIVITY": "my_custom_type"}
        )
        event = _make_event("QUERY_OBSERVATION", "/fhir/Observation/1")
        resolver = ObjectTypeResolver(config)
        objects = resolver.resolve_objects(event, "ep1", 0)
        assert objects[0][1] == "observation"


class TestOCELExporterIntegration:
    """Test integration with OCELExporter."""

    def test_config_none_uses_original_logic(self):
        exporter = OCELExporter()
        events = [_make_event("ORDER_LAB")]
        result = json.loads(exporter.export_episode("ep1", events))
        objects = result["ocel:objects"]
        # Original logic: "ORDER" + "LAB" = "test"
        test_objs = [v for v in objects.values() if v["ocel:type"] == "test"]
        assert len(test_objs) == 1

    def test_fhir_typing_produces_richer_types(self):
        config = OCELExportConfig(
            object_type_config=ObjectTypeConfig(enable_code_subtypes=False)
        )
        exporter = OCELExporter(config)
        events = [_make_event(
            "PRESCRIBE", "/fhir/MedicationRequest",
            {"resourceType": "MedicationRequest"}, "POST"
        )]
        result = json.loads(exporter.export_episode("ep1", events))
        objects = result["ocel:objects"]
        med_objs = [v for v in objects.values() if v["ocel:type"] == "medication_order"]
        assert len(med_objs) == 1

    def test_code_subtyping_in_exporter(self):
        config = OCELExportConfig(
            object_type_config=ObjectTypeConfig()
        )
        exporter = OCELExporter(config)
        events = [_make_event(
            "QUERY_OBSERVATION", "/fhir/Observation?code=6690-2", {}, "GET"
        )]
        result = json.loads(exporter.export_episode("ep1", events))
        objects = result["ocel:objects"]
        # Should have cbc_test type
        cbc_objs = [v for v in objects.values() if v["ocel:type"] == "cbc_test"]
        assert len(cbc_objs) == 1

    def test_backward_compatible_output_structure(self):
        config = OCELExportConfig(
            object_type_config=ObjectTypeConfig()
        )
        exporter = OCELExporter(config)
        events = [_make_event("ORDER_TEST")]
        result = json.loads(exporter.export_episode("ep1", events))
        # OCEL 2.0 structure preserved
        assert "ocel:global-log" in result
        assert "ocel:objects" in result
        assert "ocel:events" in result
        assert "ocel:object-types" in result

    def test_no_config_same_as_before(self):
        exporter_original = OCELExporter()
        exporter_none = OCELExporter(OCELExportConfig(object_type_config=None))
        events = [_make_event("ORDER_LAB"), _make_event("PRESCRIBE")]
        result1 = json.loads(exporter_original.export_episode("ep1", events))
        result2 = json.loads(exporter_none.export_episode("ep1", events))
        # Same object types inferred
        types1 = set(v["ocel:type"] for v in result1["ocel:objects"].values())
        types2 = set(v["ocel:type"] for v in result2["ocel:objects"].values())
        assert types1 == types2


class TestBackwardCompatibility:
    """Ensure original OCEL export behavior unchanged without config."""

    def test_default_object_types_preserved(self):
        exporter = OCELExporter()
        events = [_make_event("QUERY_PATIENT")]
        result = json.loads(exporter.export_episode("ep1", events))
        # Default types always present
        assert "patient" in result["ocel:object-types"]

    def test_infer_related_objects_unchanged(self):
        exporter = OCELExporter()
        event = _make_event("ORDER_LAB")
        related = exporter._infer_related_objects(event, "ep1", 0)
        assert len(related) == 1
        assert related[0][1] == "test"

    def test_medication_infer_unchanged(self):
        exporter = OCELExporter()
        event = _make_event("PRESCRIBE")
        related = exporter._infer_related_objects(event, "ep1", 0)
        assert len(related) == 1
        assert related[0][1] == "medication"

    def test_procedure_infer_unchanged(self):
        exporter = OCELExporter()
        event = _make_event("PERFORM_PROCEDURE")
        related = exporter._infer_related_objects(event, "ep1", 0)
        assert len(related) == 1
        assert related[0][1] == "procedure"
