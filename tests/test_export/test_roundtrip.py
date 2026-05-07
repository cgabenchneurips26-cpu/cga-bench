import json
from xml.etree import ElementTree

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.export.ocel_exporter import OCELExportConfig, OCELExporter
from cga_bench.semantic_layer.export.reimport import import_from_ocel, import_from_xes
from cga_bench.semantic_layer.export.xes_exporter import XESExportConfig, XESExporter


def make_sample_events(n: int = 20) -> list[ActivityEvent]:
    return [
        ActivityEvent(
            name=f"action_{i:03d}",
            timestamp_min=float(i * 5),
            raw_event={"step": i, "source": "test"},
        )
        for i in range(n)
    ]


def _iter_xes_events(root: ElementTree.Element) -> list[ElementTree.Element]:
    events = root.findall(".//{*}event")
    if not events:
        events = root.findall(".//event")
    return events


def _event_concept_name(event_elem: ElementTree.Element) -> str | None:
    for child in event_elem:
        tag = child.tag
        if tag.endswith("string") and child.get("key") == "concept:name":
            return child.get("value")
    return None


class TestXESRoundtrip:
    def test_xes_export_creates_valid_xml(self):
        events = make_sample_events(20)
        exporter = XESExporter(XESExportConfig(pretty_print=False))
        xml_str = exporter.export_episode("test_ep", events)

        root = ElementTree.fromstring(xml_str)
        assert root.tag == "log" or root.tag.endswith("}log")

        traces = root.findall(".//{*}trace") or root.findall(".//trace")
        assert len(traces) == 1

    def test_xes_roundtrip_event_count(self):
        events = make_sample_events(50)
        exporter = XESExporter(XESExportConfig(pretty_print=False))
        xml_str = exporter.export_episode("roundtrip_test", events)

        root = ElementTree.fromstring(xml_str)
        xml_events = _iter_xes_events(root)
        assert len(xml_events) == len(events)

    def test_xes_roundtrip_action_names_preserved_in_order(self):
        events = make_sample_events(10)
        exporter = XESExporter(XESExportConfig(pretty_print=False))
        xml_str = exporter.export_episode("name_test", events)

        root = ElementTree.fromstring(xml_str)
        xml_events = _iter_xes_events(root)
        xml_names = [_event_concept_name(evt) for evt in xml_events]
        expected_names = [f"action_{i:03d}" for i in range(10)]

        assert xml_names == expected_names


class TestOCELRoundtrip:
    def test_ocel_export_creates_valid_json(self):
        events = make_sample_events(20)
        exporter = OCELExporter(OCELExportConfig(indent=2))
        json_str = exporter.export_episode("test_ep", events)

        data = json.loads(json_str)
        assert "ocel:events" in data
        assert "ocel:objects" in data

    def test_ocel_roundtrip_event_count(self):
        events = make_sample_events(30)
        exporter = OCELExporter()
        json_str = exporter.export_episode("roundtrip_test", events)

        data = json.loads(json_str)
        ocel_events = data.get("ocel:events", {})
        assert len(ocel_events) == len(events)

    def test_ocel_roundtrip_action_names_preserved_in_order(self):
        events = make_sample_events(10)
        exporter = OCELExporter()
        json_str = exporter.export_episode("name_test", events)

        data = json.loads(json_str)
        ocel_events = data.get("ocel:events", {})
        activity_names = [evt.get("ocel:activity", "") for evt in ocel_events.values()]

        expected = [f"action_{i:03d}" for i in range(10)]
        assert activity_names == expected


class TestXESReimportRoundtrip:
    def test_xes_reimport_preserves_action_names(self):
        events = make_sample_events(10)
        exporter = XESExporter()
        xml_str = exporter.export_episode("reimport_test", events)

        reimported = import_from_xes(xml_str)
        original_names = [e.name for e in events]
        reimported_names = [e.name for e in reimported]
        assert set(original_names).issubset(set(reimported_names))

    def test_xes_reimport_event_count(self):
        events = make_sample_events(20)
        exporter = XESExporter()
        xml_str = exporter.export_episode("count_test", events)

        reimported = import_from_xes(xml_str)
        assert len(reimported) >= len(events)


class TestOCELReimportRoundtrip:
    def test_ocel_reimport_preserves_action_names(self):
        events = make_sample_events(10)
        exporter = OCELExporter()
        json_str = exporter.export_episode("reimport_test", events)

        reimported = import_from_ocel(json_str)
        original_names = [e.name for e in events]
        reimported_names = [e.name for e in reimported]
        assert set(original_names) == set(reimported_names)

    def test_ocel_reimport_event_count(self):
        events = make_sample_events(15)
        exporter = OCELExporter()
        json_str = exporter.export_episode("count_test", events)

        reimported = import_from_ocel(json_str)
        assert len(reimported) == len(events)


class TestXESTimestampRoundtrip:
    def test_timestamp_preserved(self):
        events = make_sample_events(5)
        exporter = XESExporter()
        xml_str = exporter.export_episode("ts_test", events)
        reimported = import_from_xes(xml_str)
        for orig, reimp in zip(events, reimported):
            assert abs(orig.timestamp_min - reimp.timestamp_min) < 0.01


class TestOCELTimestampRoundtrip:
    def test_timestamp_preserved(self):
        events = make_sample_events(5)
        exporter = OCELExporter()
        json_str = exporter.export_episode("ts_test", events)
        reimported = import_from_ocel(json_str)
        for orig, reimp in zip(events, reimported):
            assert abs(orig.timestamp_min - reimp.timestamp_min) < 0.01


class TestFHIRLoader:
    def test_parse_minimal_bundle(self):
        from cga_bench.semantic_layer.export.fhir_loader import parse_fhir_bundle

        bundle = {
            "resourceType": "Bundle",
            "entry": [
                {
                    "resource": {
                        "resourceType": "Procedure",
                        "id": "p1",
                        "code": {"coding": [{"display": "Appendectomy"}]},
                        "performedDateTime": "2024-01-01T10:30:00",
                    }
                },
                {
                    "resource": {
                        "resourceType": "MedicationRequest",
                        "id": "m1",
                        "medicationCodeableConcept": {"coding": [{"display": "Aspirin"}]},
                        "authoredOn": "2024-01-01T11:00:00",
                    }
                },
            ],
        }
        events = parse_fhir_bundle(bundle)
        assert len(events) == 2
        assert events[0].timestamp_min < events[1].timestamp_min
        assert "appendectomy" in events[0].name

    def test_invalid_bundle_raises(self):
        import pytest
        from cga_bench.semantic_layer.export.fhir_loader import parse_fhir_bundle

        with pytest.raises(ValueError):
            parse_fhir_bundle({"resourceType": "Patient"})


class TestXESFileLoader:
    def test_load_xes_file(self, tmp_path):
        from cga_bench.semantic_layer.export.reimport import load_xes_file

        events = make_sample_events(10)
        exporter = XESExporter()
        xml_str = exporter.export_episode("file_test", events)
        xes_file = tmp_path / "test.xes"
        xes_file.write_text(xml_str)
        loaded = load_xes_file(xes_file)
        assert len(loaded) >= 10


class TestOCELSQLiteExport:
    def test_sqlite_export_creates_db(self, tmp_path):
        import sqlite3

        events = make_sample_events(5)
        exporter = OCELExporter()
        db_path = str(tmp_path / "test.sqlite")
        result = exporter.export_episode_sqlite("sqlite_test", events, db_path)
        conn = sqlite3.connect(result)
        c = conn.cursor()
        c.execute("SELECT COUNT(*) FROM event")
        count = c.fetchone()[0]
        conn.close()
        assert count == 5
