"""Re-import utilities for XES/OCEL roundtrip verification."""

import json
from pathlib import Path
from typing import List
from xml.etree import ElementTree

from ..conformance.activity import ActivityEvent


def import_from_xes(xml_str: str) -> List[ActivityEvent]:
    """Parse XES XML back to ActivityEvent list."""
    root = ElementTree.fromstring(xml_str)
    events = []
    for event_el in root.iter():
        if not (event_el.tag == "event" or event_el.tag.endswith("}event")):
            continue

        name = ""
        timestamp_min = 0.0
        for child in event_el:
            tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            key = child.get("key", "")
            value = child.get("value", "")
            if tag == "string" and key == "concept:name":
                name = value
            elif tag == "float" and key == "cga:timestamp_min":
                try:
                    timestamp_min = float(value)
                except (ValueError, TypeError):
                    pass
            elif tag == "float" and key == "time:timestamp_min":
                if timestamp_min == 0.0:
                    try:
                        timestamp_min = float(value)
                    except (ValueError, TypeError):
                        pass
            elif tag == "date" and key == "time:timestamp" and timestamp_min == 0.0:
                timestamp_min = _iso_to_minutes(value)

        if name:
            events.append(ActivityEvent(name=name, timestamp_min=timestamp_min, raw_event={}))
    return events


def _iso_to_minutes(iso_str: str) -> float:
    """Convert ISO timestamp back to minutes from epoch/base."""
    from datetime import datetime, timezone

    try:
        normalized = iso_str.replace("+00:00", "+0000").replace("Z", "+0000")
        if "+" in normalized:
            dt_part = normalized.split("+")[0]
        else:
            dt_part = normalized
        dt = datetime.fromisoformat(dt_part).replace(tzinfo=timezone.utc)
        base = datetime(2024, 1, 1, tzinfo=timezone.utc)
        delta = dt - base
        return delta.total_seconds() / 60.0
    except Exception:
        return 0.0


def import_from_ocel(json_str: str) -> List[ActivityEvent]:
    """Parse OCEL JSON back to ActivityEvent list."""
    data = json.loads(json_str)
    ocel_events = data.get("ocel:events", data.get("ocelEvents", data.get("events", [])))
    events = []

    if isinstance(ocel_events, dict):
        for evt in ocel_events.values():
            name = evt.get("ocel:activity", evt.get("activity", ""))
            ts = evt.get("cga:timestamp_min", 0.0)
            try:
                ts = float(ts)
            except (ValueError, TypeError):
                ts = 0.0
            events.append(ActivityEvent(name=name, timestamp_min=ts, raw_event={}))
    elif isinstance(ocel_events, list):
        for evt in ocel_events:
            name = evt.get("ocel:activity", evt.get("activity", ""))
            ts = evt.get("cga:timestamp_min", 0.0)
            try:
                ts = float(ts)
            except (ValueError, TypeError):
                ts = 0.0
            events.append(ActivityEvent(name=name, timestamp_min=ts, raw_event={}))

    return events


def load_xes_file(path: str | Path) -> List[ActivityEvent]:
    """Load XES file from disk."""
    xml_str = Path(path).read_text(encoding="utf-8")
    return import_from_xes(xml_str)


def load_xes_file_streaming(path: str | Path) -> List[ActivityEvent]:
    """Load large XES file using iterative XML parsing."""
    import xml.etree.ElementTree as ET

    events: List[ActivityEvent] = []
    for _, elem in ET.iterparse(str(Path(path)), events=["end"]):
        tag = elem.tag.split("}")[-1] if "}" in elem.tag else elem.tag
        if tag != "event":
            continue

        name = ""
        timestamp_min = 0.0
        for child in elem:
            child_tag = child.tag.split("}")[-1] if "}" in child.tag else child.tag
            key = child.get("key", "")
            value = child.get("value", "")

            if child_tag == "string" and key == "concept:name":
                name = value
            elif child_tag == "float" and key == "cga:timestamp_min":
                try:
                    timestamp_min = float(value)
                except (ValueError, TypeError):
                    pass
            elif child_tag == "date" and key == "time:timestamp" and timestamp_min == 0.0:
                timestamp_min = _iso_to_minutes(value)

        if name:
            events.append(ActivityEvent(name=name, timestamp_min=timestamp_min, raw_event={}))

        elem.clear()

    return events
