"""Tests for multi-perspective XES export."""
import pytest
from datetime import datetime, timezone
from xml.etree.ElementTree import fromstring

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.export.xes_exporter import (
    XESExporter,
    XESExportConfig,
    XESPerspectiveConfig,
)

# XES namespace handling
_XES = "{http://www.xes-standard.org/}"


def _make_event(name, timestamp_min=0.0, url="", method="GET", payload=None,
                response_text=None, new_results=None, confidence=1.0, match_source="exact"):
    """Create an ActivityEvent for testing."""
    raw = {}
    if url or payload:
        raw["tool_call"] = {
            "method": method,
            "url": url,
            "payload": payload or {},
        }
    if response_text:
        raw["response_text"] = response_text
    if new_results:
        raw["new_results"] = new_results
    return ActivityEvent(
        name=name,
        timestamp_min=timestamp_min,
        raw_event=raw,
        confidence=confidence,
        match_source=match_source,
    )


def _find(root, tag):
    """Find element with or without namespace."""
    result = root.find(f"{_XES}{tag}")
    if result is None:
        result = root.find(tag)
    return result


def _find_all(root, tag):
    """Find all elements with or without namespace."""
    results = root.findall(f"{_XES}{tag}")
    if not results:
        results = root.findall(tag)
    return results


def _parse_xes(xml_str):
    """Parse XES XML string and return root element."""
    return fromstring(xml_str)


def _get_events(root):
    """Get all event elements from the first trace."""
    trace = _find(root, "trace")
    if trace is None:
        return []
    return _find_all(trace, "event")


def _get_attr(event_elem, key, attr_type="string"):
    """Get an attribute value from an event element."""
    for attr in event_elem:
        tag = attr.tag.replace(_XES, "")
        if tag == attr_type and attr.get("key") == key:
            return attr.get("value")
    return None


def _get_extensions(root):
    """Get all extension names from the log element."""
    exts = _find_all(root, "extension")
    return [ext.get("name") for ext in exts]


class TestLifecyclePerspective:
    """Test lifecycle transition inference."""

    def test_normal_event_complete_transition(self):
        config = XESExportConfig(perspective_config=XESPerspectiveConfig(), pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0, "/fhir/Observation")]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "lifecycle:transition") == "complete"

    def test_error_event_abort_transition(self):
        config = XESExportConfig(perspective_config=XESPerspectiveConfig(), pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "QUERY_OBS", 0.0, "/fhir/Observation",
            response_text='{"resourceType": "OperationOutcome", "issue": []}'
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "lifecycle:transition") == "abort"

    def test_client_error_abort(self):
        config = XESExportConfig(perspective_config=XESPerspectiveConfig(), pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "QUERY_OBS", 0.0, "/fhir/Observation",
            response_text="404 Client Error: Not Found"
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "lifecycle:transition") == "abort"

    def test_server_error_abort(self):
        config = XESExportConfig(perspective_config=XESPerspectiveConfig(), pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "QUERY_OBS", 0.0, "/fhir/Observation",
            response_text="500 Server Error: Internal"
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "lifecycle:transition") == "abort"

    def test_no_perspective_config_always_complete(self):
        exporter = XESExporter(XESExportConfig(pretty_print=False))
        events = [_make_event(
            "QUERY_OBS", 0.0, "/fhir/Observation",
            response_text="404 Client Error"
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        # Without perspective_config, always "complete"
        assert _get_attr(event_elems[0], "lifecycle:transition") == "complete"

    def test_lifecycle_disabled_no_transition(self):
        config = XESExportConfig(
            include_lifecycle=False,
            perspective_config=XESPerspectiveConfig(),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "lifecycle:transition") is None

    def test_error_in_sending_abort(self):
        config = XESExportConfig(perspective_config=XESPerspectiveConfig(), pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "QUERY_OBS", 0.0, "/fhir/Observation",
            response_text="Error in sending the GET request to /fhir/Observation"
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "lifecycle:transition") == "abort"


class TestResourcePerspective:
    """Test enhanced resource attributes."""

    def test_role_attribute_added(self):
        pc = XESPerspectiveConfig(resource_role="physician")
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "org:role") == "physician"

    def test_group_attribute_added(self):
        pc = XESPerspectiveConfig(resource_group="emergency")
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "org:group") == "emergency"

    def test_both_role_and_group(self):
        pc = XESPerspectiveConfig(resource_role="nurse", resource_group="icu")
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "org:role") == "nurse"
        assert _get_attr(event_elems[0], "org:group") == "icu"

    def test_no_role_no_group_only_resource(self):
        pc = XESPerspectiveConfig(resource_role=None, resource_group=None)
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "org:resource") == "agent"
        assert _get_attr(event_elems[0], "org:role") is None
        assert _get_attr(event_elems[0], "org:group") is None

    def test_resource_perspective_disabled(self):
        pc = XESPerspectiveConfig(
            enable_resource_attributes=False,
            resource_role="physician",
            resource_group="icu",
        )
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "org:resource") == "agent"
        assert _get_attr(event_elems[0], "org:role") is None


class TestDataPerspective:
    """Test data perspective attributes."""

    def test_resource_type_extracted(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "PRESCRIBE", 0.0, "/fhir/MedicationRequest", "POST",
            payload={"resourceType": "MedicationRequest"}
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "data:resource_type") == "MedicationRequest"

    def test_code_extracted(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "ORDER_LAB", 0.0, "/fhir/ServiceRequest", "POST",
            payload={
                "resourceType": "ServiceRequest",
                "code": {"coding": [{"code": "6690-2", "system": "http://loinc.org"}]},
            }
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "data:code") == "6690-2"

    def test_code_system_extracted(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "ORDER_LAB", 0.0, "/fhir/ServiceRequest", "POST",
            payload={
                "resourceType": "ServiceRequest",
                "code": {"coding": [{"code": "X", "system": "http://loinc.org"}]},
            }
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "data:code_system") == "http://loinc.org"

    def test_code_display_extracted(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "ORDER_LAB", 0.0, "/fhir/ServiceRequest", "POST",
            payload={
                "resourceType": "ServiceRequest",
                "code": {"coding": [{"code": "X", "display": "CBC"}]},
            }
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "data:code_display") == "CBC"

    def test_lab_result_value(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "QUERY_OBS", 0.0, "/fhir/Observation",
            new_results=[{"code": "6690-2", "value": 12.5, "unit": "g/dL"}]
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "data:result_code") == "6690-2"
        val = _get_attr(event_elems[0], "data:result_value", "float")
        assert val is not None
        assert float(val) == pytest.approx(12.5)

    def test_lab_result_unit(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "QUERY_OBS", 0.0,
            new_results=[{"code": "X", "value": 5.0, "unit": "mmol/L"}]
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "data:result_unit") == "mmol/L"

    def test_no_data_when_disabled(self):
        pc = XESPerspectiveConfig(enable_data_perspective=False)
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "PRESCRIBE", 0.0, "/fhir/MedicationRequest", "POST",
            payload={"resourceType": "MedicationRequest"}
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "data:resource_type") is None

    def test_empty_payload_no_crash(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "data:resource_type") is None

    def test_reference_range_extracted(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "QUERY_OBS", 0.0,
            new_results=[{"code": "X", "value": 5.0, "unit": "mg/dL", "reference_range": "3.5-5.5"}]
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "data:reference_range") == "3.5-5.5"


class TestPerformancePerspective:
    """Test performance metrics in XES output."""

    def test_duration_computed_from_next_event(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [
            _make_event("QUERY_OBS", 0.0),
            _make_event("ORDER_LAB", 5.0),
        ]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        duration = _get_attr(event_elems[0], "perf:duration_minutes", "float")
        assert duration is not None
        assert float(duration) == pytest.approx(5.0)

    def test_last_event_no_duration(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [
            _make_event("QUERY_OBS", 0.0),
            _make_event("ORDER_LAB", 5.0),
        ]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        duration = _get_attr(event_elems[1], "perf:duration_minutes", "float")
        assert duration is None

    def test_confidence_included(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0, confidence=0.85)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        confidence = _get_attr(event_elems[0], "quality:confidence", "float")
        assert confidence is not None
        assert float(confidence) == pytest.approx(0.85)

    def test_match_source_included(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0, match_source="code_family")]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "quality:match_source") == "code_family"

    def test_error_flag_included(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event(
            "QUERY_OBS", 0.0, response_text="500 Server Error"
        )]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "quality:has_error") == "true"

    def test_no_error_no_flag(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "quality:has_error") is None

    def test_perf_extension_declared(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        extensions = _get_extensions(root)
        assert "Performance" in extensions

    def test_disabled_no_perf_attrs(self):
        pc = XESPerspectiveConfig(enable_performance_metrics=False)
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [
            _make_event("QUERY_OBS", 0.0, confidence=0.9),
            _make_event("ORDER_LAB", 5.0),
        ]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "perf:duration_minutes", "float") is None
        assert _get_attr(event_elems[0], "quality:confidence", "float") is None


class TestCostPerspective:
    """Test cost attributes in XES output."""

    def test_cost_attribute_added(self):
        pc = XESPerspectiveConfig(enable_cost_perspective=True, default_cost_per_event=10.5)
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        cost = _get_attr(event_elems[0], "cost:total", "float")
        assert cost is not None
        assert float(cost) == pytest.approx(10.5)

    def test_zero_cost_not_added(self):
        pc = XESPerspectiveConfig(enable_cost_perspective=True, default_cost_per_event=0.0)
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "cost:total", "float") is None

    def test_cost_extension_declared(self):
        pc = XESPerspectiveConfig(enable_cost_perspective=True, default_cost_per_event=5.0)
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        extensions = _get_extensions(root)
        assert "Cost" in extensions

    def test_disabled_no_cost(self):
        pc = XESPerspectiveConfig(enable_cost_perspective=False, default_cost_per_event=10.0)
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        assert _get_attr(event_elems[0], "cost:total", "float") is None


class TestBackwardCompatibility:
    """Ensure original XES output unchanged without perspective_config."""

    def test_no_perspective_config_identical_output(self):
        exporter = XESExporter(XESExportConfig(pretty_print=False))
        events = [_make_event("QUERY_OBS", 0.0, "/fhir/Observation")]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        # Should only have standard attributes
        assert _get_attr(event_elems[0], "concept:name") == "QUERY_OBS"
        assert _get_attr(event_elems[0], "lifecycle:transition") == "complete"
        assert _get_attr(event_elems[0], "org:resource") == "agent"
        # No multi-perspective attrs
        assert _get_attr(event_elems[0], "data:resource_type") is None
        assert _get_attr(event_elems[0], "perf:duration_minutes", "float") is None
        assert _get_attr(event_elems[0], "quality:confidence", "float") is None

    def test_no_extra_extensions_without_config(self):
        exporter = XESExporter(XESExportConfig(pretty_print=False))
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        extensions = _get_extensions(root)
        assert "Performance" not in extensions
        assert "Data" not in extensions
        assert "Cost" not in extensions

    def test_float_attr_format(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0, confidence=0.123456789)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        event_elems = _get_events(root)
        val = _get_attr(event_elems[0], "quality:confidence", "float")
        # Should be formatted to 6 decimal places
        assert "." in val
        assert len(val.split(".")[1]) == 6

    def test_multiple_episodes_with_perspectives(self):
        pc = XESPerspectiveConfig(resource_role="physician")
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        episodes = {
            "ep1": [_make_event("QUERY_OBS", 0.0)],
            "ep2": [_make_event("PRESCRIBE", 0.0)],
        }
        xml = exporter.export_episodes(episodes)
        root = _parse_xes(xml)
        traces = _find_all(root, "trace")
        assert len(traces) == 2
        # Both traces should have role attribute
        for trace in traces:
            event_elem = _find(trace, "event")
            assert _get_attr(event_elem, "org:role") == "physician"

    def test_empty_events_with_perspectives(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        xml = exporter.export_episode("ep1", [])
        root = _parse_xes(xml)
        trace = _find(root, "trace")
        assert trace is not None
        assert len(_find_all(trace, "event")) == 0

    def test_data_extension_declared(self):
        pc = XESPerspectiveConfig()
        config = XESExportConfig(perspective_config=pc, pretty_print=False)
        exporter = XESExporter(config)
        events = [_make_event("QUERY_OBS", 0.0)]
        xml = exporter.export_episode("ep1", events)
        root = _parse_xes(xml)
        extensions = _get_extensions(root)
        assert "Data" in extensions
