"""Tests for XES 2.0 exporter."""
import pytest
from xml.etree.ElementTree import fromstring

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.export.xes_exporter import XESExporter, XESExportConfig

# XES namespace for element queries
NS = {"xes": "http://www.xes-standard.org/"}
_XES = "{http://www.xes-standard.org/}"


def _find_all(root, tag):
    """Find all elements with or without namespace."""
    # Try with namespace first, then without
    results = root.findall(f"{_XES}{tag}")
    if not results:
        results = root.findall(tag)
    return results


def _find(root, tag):
    """Find single element with or without namespace."""
    result = root.find(f"{_XES}{tag}")
    if result is None:
        result = root.find(tag)
    return result


@pytest.fixture
def sample_events():
    """Create sample ActivityEvents for testing."""
    return [
        ActivityEvent(name="ORDER_LAB", timestamp_min=5.0, raw_event={}),
        ActivityEvent(name="PRESCRIBE", timestamp_min=10.0, raw_event={
            "tool_call": {"method": "POST", "url": "/fhir/MedicationRequest"}
        }),
        ActivityEvent(name="QUERY_OBSERVATION", timestamp_min=15.0, raw_event={
            "tool_call": {"method": "GET", "url": "/fhir/Observation?code=2524-7"}
        }),
    ]


@pytest.fixture
def exporter():
    """Create a XESExporter with default config."""
    return XESExporter(XESExportConfig(pretty_print=False))


class TestXESExport:
    """Test XES XML export."""

    def test_basic_export(self, exporter, sample_events):
        xml = exporter.export_episode("test_001", sample_events)
        assert "<log" in xml
        assert 'xes.version="2.0"' in xml
        assert "ORDER_LAB" in xml
        assert "PRESCRIBE" in xml
        assert "QUERY_OBSERVATION" in xml

    def test_trace_concept_name(self, exporter, sample_events):
        xml = exporter.export_episode("episode_42", sample_events)
        root = fromstring(xml)
        traces = _find_all(root, "trace")
        assert len(traces) == 1
        attrs = _find_all(traces[0], "string")
        concept_name = next(
            (a for a in attrs if a.get("key") == "concept:name"), None
        )
        assert concept_name is not None
        assert concept_name.get("value") == "episode_42"

    def test_event_count(self, exporter, sample_events):
        xml = exporter.export_episode("test_001", sample_events)
        root = fromstring(xml)
        trace = _find(root, "trace")
        events = _find_all(trace, "event")
        assert len(events) == 3

    def test_event_ordering(self, exporter):
        events = [
            ActivityEvent(name="B", timestamp_min=10.0, raw_event={}),
            ActivityEvent(name="A", timestamp_min=5.0, raw_event={}),
            ActivityEvent(name="C", timestamp_min=15.0, raw_event={}),
        ]
        xml = exporter.export_episode("test_001", events)
        root = fromstring(xml)
        trace = _find(root, "trace")
        event_elems = _find_all(trace, "event")
        names = []
        for ev in event_elems:
            str_attrs = _find_all(ev, "string")
            name_attr = next(
                (a for a in str_attrs if a.get("key") == "concept:name"),
                None,
            )
            if name_attr is not None:
                names.append(name_attr.get("value"))
        assert names == ["A", "B", "C"]

    def test_timestamps(self, exporter, sample_events):
        xml = exporter.export_episode("test_001", sample_events)
        root = fromstring(xml)
        trace = _find(root, "trace")
        events = _find_all(trace, "event")
        first_event = events[0]
        date_attrs = _find_all(first_event, "date")
        ts_attr = next(
            (a for a in date_attrs if a.get("key") == "time:timestamp"),
            None,
        )
        assert ts_attr is not None
        assert "00:05:00" in ts_attr.get("value")

    def test_resource_attribute(self, exporter, sample_events):
        xml = exporter.export_episode("test_001", sample_events, resource="agent_rag_gpt4")
        assert "agent_rag_gpt4" in xml

    def test_lifecycle_transition(self, sample_events):
        config = XESExportConfig(include_lifecycle=True, pretty_print=False)
        exporter = XESExporter(config)
        xml = exporter.export_episode("test_001", sample_events)
        assert "lifecycle:transition" in xml
        assert "complete" in xml

    def test_no_lifecycle(self, sample_events):
        config = XESExportConfig(include_lifecycle=False, pretty_print=False)
        exporter = XESExporter(config)
        xml = exporter.export_episode("test_001", sample_events)
        root = fromstring(xml)
        trace = _find(root, "trace")
        first_event = _find_all(trace, "event")[0]
        str_attrs = _find_all(first_event, "string")
        lifecycle_attrs = [
            a for a in str_attrs
            if a.get("key") == "lifecycle:transition"
        ]
        assert len(lifecycle_attrs) == 0

    def test_tool_call_attributes(self, sample_events):
        config = XESExportConfig(pretty_print=False)
        exporter = XESExporter(config)
        xml = exporter.export_episode("test_001", sample_events)
        assert "cga:method" in xml
        assert "cga:url" in xml

    def test_multiple_episodes(self, exporter, sample_events):
        episodes = {
            "ep_001": sample_events[:2],
            "ep_002": sample_events[1:],
        }
        xml = exporter.export_episodes(episodes)
        root = fromstring(xml)
        traces = _find_all(root, "trace")
        assert len(traces) == 2

    def test_empty_events(self, exporter):
        xml = exporter.export_episode("empty_001", [])
        root = fromstring(xml)
        trace = _find(root, "trace")
        events = _find_all(trace, "event")
        assert len(events) == 0

    def test_extensions_present(self, exporter, sample_events):
        xml = exporter.export_episode("test_001", sample_events)
        root = fromstring(xml)
        extensions = _find_all(root, "extension")
        ext_names = [e.get("name") for e in extensions]
        assert "Concept" in ext_names
        assert "Time" in ext_names

    def test_pretty_print(self, sample_events):
        config = XESExportConfig(pretty_print=True)
        exporter = XESExporter(config)
        xml = exporter.export_episode("test_001", sample_events)
        assert "\n" in xml
        assert "  " in xml

    def test_trace_attributes(self, exporter, sample_events):
        xml = exporter.export_episode(
            "test_001",
            sample_events,
            attributes={"cga:scenario": "sepsis_001"},
        )
        assert "cga:scenario" in xml
        assert "sepsis_001" in xml
