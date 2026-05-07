"""Tests for OCEL 2.0 exporter."""
import json

import pytest

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.export.ocel_exporter import (
    OCELExporter,
    OCELExportConfig,
    OCELObject,
)


@pytest.fixture
def sample_events():
    """Create sample ActivityEvents for testing."""
    return [
        ActivityEvent(name="ORDER_LAB", timestamp_min=5.0, raw_event={}),
        ActivityEvent(name="PRESCRIBE", timestamp_min=10.0, raw_event={
            "tool_call": {"method": "POST", "url": "/fhir/MedicationRequest"}
        }),
        ActivityEvent(name="QUERY_OBSERVATION", timestamp_min=15.0, raw_event={}),
        ActivityEvent(name="PERFORM_PROCEDURE", timestamp_min=20.0, raw_event={}),
    ]


@pytest.fixture
def exporter():
    """Create an OCELExporter with default config."""
    return OCELExporter(OCELExportConfig())


class TestOCELExport:
    """Test OCEL 2.0 JSON export."""

    def test_basic_structure(self, exporter, sample_events):
        result = exporter.export_episode("test_001", sample_events)
        data = json.loads(result)

        assert "ocel:global-log" in data
        assert data["ocel:global-log"]["ocel:version"] == "2.0"
        assert "ocel:object-types" in data
        assert "ocel:objects" in data
        assert "ocel:events" in data

    def test_event_count(self, exporter, sample_events):
        result = exporter.export_episode("test_001", sample_events)
        data = json.loads(result)
        assert len(data["ocel:events"]) == 4

    def test_event_activity_names(self, exporter, sample_events):
        result = exporter.export_episode("test_001", sample_events)
        data = json.loads(result)
        activities = [e["ocel:activity"] for e in data["ocel:events"].values()]
        assert "ORDER_LAB" in activities
        assert "PRESCRIBE" in activities
        assert "QUERY_OBSERVATION" in activities
        assert "PERFORM_PROCEDURE" in activities

    def test_patient_object_created(self, exporter, sample_events):
        result = exporter.export_episode(
            "test_001", sample_events, patient_id="patient_123"
        )
        data = json.loads(result)
        assert "patient_123" in data["ocel:objects"]
        assert data["ocel:objects"]["patient_123"]["ocel:type"] == "patient"

    def test_default_patient_id(self, exporter, sample_events):
        result = exporter.export_episode("ep_42", sample_events)
        data = json.loads(result)
        assert "patient_ep_42" in data["ocel:objects"]

    def test_timestamps(self, exporter, sample_events):
        result = exporter.export_episode("test_001", sample_events)
        data = json.loads(result)
        events = list(data["ocel:events"].values())
        # First event at 5 minutes from 2024-01-01T00:00:00Z
        assert "2024-01-01T00:05:00Z" in events[0]["ocel:timestamp"]

    def test_object_map_includes_patient(self, exporter, sample_events):
        result = exporter.export_episode(
            "test_001", sample_events, patient_id="pat_1"
        )
        data = json.loads(result)
        for event in data["ocel:events"].values():
            assert "pat_1" in event["ocel:omap"]

    def test_inferred_objects_for_order(self, exporter):
        events = [
            ActivityEvent(name="ORDER_LAB", timestamp_min=5.0, raw_event={}),
        ]
        result = exporter.export_episode("test_001", events)
        data = json.loads(result)
        # Should have inferred a test object
        object_types = {obj["ocel:type"] for obj in data["ocel:objects"].values()}
        assert "test" in object_types

    def test_inferred_objects_for_prescribe(self, exporter):
        events = [
            ActivityEvent(name="PRESCRIBE", timestamp_min=5.0, raw_event={}),
        ]
        result = exporter.export_episode("test_001", events)
        data = json.loads(result)
        object_types = {obj["ocel:type"] for obj in data["ocel:objects"].values()}
        assert "medication" in object_types

    def test_inferred_objects_for_procedure(self, exporter):
        events = [
            ActivityEvent(name="PERFORM_PROCEDURE", timestamp_min=5.0, raw_event={}),
        ]
        result = exporter.export_episode("test_001", events)
        data = json.loads(result)
        object_types = {obj["ocel:type"] for obj in data["ocel:objects"].values()}
        assert "procedure" in object_types

    def test_custom_objects(self, exporter, sample_events):
        objects = [
            OCELObject(object_id="custom_1", object_type="device", attributes={"name": "ECG Monitor"}),
        ]
        result = exporter.export_episode("test_001", sample_events, objects=objects)
        data = json.loads(result)
        assert "custom_1" in data["ocel:objects"]
        assert data["ocel:objects"]["custom_1"]["ocel:type"] == "device"

    def test_vmap_attributes(self, exporter, sample_events):
        result = exporter.export_episode(
            "test_001", sample_events, resource="agent_v1"
        )
        data = json.loads(result)
        first_event = list(data["ocel:events"].values())[0]
        assert first_event["ocel:vmap"]["resource"] == "agent_v1"
        assert "timestamp_min" in first_event["ocel:vmap"]

    def test_tool_call_in_vmap(self, exporter, sample_events):
        result = exporter.export_episode("test_001", sample_events)
        data = json.loads(result)
        # Second event (PRESCRIBE) has tool_call
        events = list(data["ocel:events"].values())
        prescribe_event = next(
            e for e in events if e["ocel:activity"] == "PRESCRIBE"
        )
        assert prescribe_event["ocel:vmap"]["method"] == "POST"
        assert "/fhir/MedicationRequest" in prescribe_event["ocel:vmap"]["url"]

    def test_multiple_episodes(self, exporter, sample_events):
        episodes = {
            "ep_001": sample_events[:2],
            "ep_002": sample_events[2:],
        }
        result = exporter.export_episodes(episodes)
        data = json.loads(result)
        assert len(data["ocel:events"]) == 4
        assert "patient_ep_001" in data["ocel:objects"]
        assert "patient_ep_002" in data["ocel:objects"]

    def test_empty_events(self, exporter):
        result = exporter.export_episode("empty_001", [])
        data = json.loads(result)
        assert len(data["ocel:events"]) == 0
        # Patient object should still exist
        assert "patient_empty_001" in data["ocel:objects"]

    def test_json_valid(self, exporter, sample_events):
        result = exporter.export_episode("test_001", sample_events)
        # Should not raise
        data = json.loads(result)
        assert isinstance(data, dict)

    def test_object_types_sorted(self, exporter, sample_events):
        result = exporter.export_episode("test_001", sample_events)
        data = json.loads(result)
        types = data["ocel:object-types"]
        assert types == sorted(types)
