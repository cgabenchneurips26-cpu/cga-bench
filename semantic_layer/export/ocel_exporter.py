"""
OCEL 2.0 JSON exporter for clinical episode logs.

Converts ActivityEvents and PatientState into Object-Centric Event Log
(OCEL 2.0) format for multi-object process mining analysis.

Reference: https://ocel-standard.org/
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Set

from ..conformance.activity import ActivityEvent


@dataclass
class OCELExportConfig:
    """Configuration for OCEL 2.0 export.

    All fields optional for backward compatibility.
    """
    ocel_version: str = "2.0"
    include_object_attributes: bool = True
    base_timestamp: Optional[datetime] = None
    default_resource: str = "agent"
    indent: int = 2  # JSON indentation
    object_type_config: Optional[Any] = None  # ObjectTypeConfig (lazy import)


@dataclass
class OCELObject:
    """An OCEL object (patient, order, medication, etc.)."""
    object_id: str
    object_type: str
    attributes: Dict[str, Any] = field(default_factory=dict)


class OCELExporter:
    """Exports ActivityEvents to OCEL 2.0 JSON format.

    Produces Object-Centric Event Logs that capture relationships
    between events and multiple object types (patients, orders, tests, etc.).
    """

    # Default object types for clinical episodes
    DEFAULT_OBJECT_TYPES = ["patient", "order", "test", "medication", "procedure"]

    def __init__(self, config: Optional[OCELExportConfig] = None):
        self._config = config or OCELExportConfig()
        self._type_resolver = None

    def export_episode(
        self,
        episode_id: str,
        events: List[ActivityEvent],
        patient_id: Optional[str] = None,
        objects: Optional[List[OCELObject]] = None,
        resource: Optional[str] = None,
    ) -> str:
        """Export a single episode as OCEL 2.0 JSON string.

        Args:
            episode_id: Unique episode identifier
            events: List of ActivityEvent objects
            patient_id: Patient identifier (creates patient object)
            objects: Additional OCEL objects
            resource: Agent/resource identifier

        Returns:
            OCEL 2.0 JSON string
        """
        ocel = self._build_ocel(episode_id, events, patient_id, objects, resource)
        return json.dumps(ocel, indent=self._config.indent, ensure_ascii=False)

    def export_episode_sqlite(
        self,
        episode_id: str,
        events: List[ActivityEvent],
        db_path: str,
        patient_id: Optional[str] = None,
        objects: Optional[List[OCELObject]] = None,
        resource: Optional[str] = None,
    ) -> str:
        """Export a single episode as OCEL 2.0 SQLite database.

        Args:
            episode_id: Unique episode identifier
            events: List of ActivityEvent objects
            db_path: Path to output SQLite file
            patient_id: Patient identifier
            objects: Additional OCEL objects
            resource: Agent/resource identifier

        Returns:
            Path to the created SQLite file.
        """
        ocel = self._build_ocel(episode_id, events, patient_id, objects, resource)

        conn = sqlite3.connect(db_path)
        c = conn.cursor()

        c.execute(
            """CREATE TABLE IF NOT EXISTS event (
            ocel_id TEXT PRIMARY KEY,
            ocel_type TEXT,
            ocel_time TEXT
        )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS object (
            ocel_id TEXT PRIMARY KEY,
            ocel_type TEXT
        )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS event_object (
            ocel_event_id TEXT,
            ocel_object_id TEXT,
            ocel_qualifier TEXT,
            FOREIGN KEY (ocel_event_id) REFERENCES event(ocel_id),
            FOREIGN KEY (ocel_object_id) REFERENCES object(ocel_id)
        )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS event_attribute (
            ocel_event_id TEXT,
            ocel_key TEXT,
            ocel_value TEXT,
            FOREIGN KEY (ocel_event_id) REFERENCES event(ocel_id)
        )"""
        )
        c.execute(
            """CREATE TABLE IF NOT EXISTS object_attribute (
            ocel_object_id TEXT,
            ocel_key TEXT,
            ocel_value TEXT,
            FOREIGN KEY (ocel_object_id) REFERENCES object(ocel_id)
        )"""
        )

        for obj_id, obj_data in ocel.get("ocel:objects", {}).items():
            obj_type = obj_data.get("ocel:type", "unknown")
            c.execute("INSERT OR REPLACE INTO object VALUES (?, ?)", (obj_id, obj_type))
            for key, val in obj_data.items():
                if key != "ocel:type":
                    c.execute("INSERT INTO object_attribute VALUES (?, ?, ?)", (obj_id, key, str(val)))

        for evt_id, evt_data in ocel.get("ocel:events", {}).items():
            activity = evt_data.get("ocel:activity", "")
            timestamp = evt_data.get("ocel:timestamp", "")
            c.execute("INSERT OR REPLACE INTO event VALUES (?, ?, ?)", (evt_id, activity, timestamp))

            for obj_id in evt_data.get("ocel:omap", []):
                c.execute("INSERT INTO event_object VALUES (?, ?, ?)", (evt_id, obj_id, ""))

            for key, val in evt_data.items():
                if key not in ("ocel:activity", "ocel:timestamp", "ocel:omap"):
                    c.execute("INSERT INTO event_attribute VALUES (?, ?, ?)", (evt_id, key, str(val)))

        conn.commit()
        conn.close()
        return db_path

    def export_episodes(
        self,
        episodes: Dict[str, List[ActivityEvent]],
        resource: Optional[str] = None,
    ) -> str:
        """Export multiple episodes as a single OCEL log.

        Args:
            episodes: Dict of episode_id -> event list
            resource: Agent/resource identifier

        Returns:
            OCEL 2.0 JSON string with all episodes merged
        """
        all_events: Dict[str, Dict[str, Any]] = {}
        all_objects: Dict[str, Dict[str, Any]] = {}
        object_types: Set[str] = set(self.DEFAULT_OBJECT_TYPES)

        for episode_id, events in episodes.items():
            patient_id = f"patient_{episode_id}"
            all_objects[patient_id] = {"ocel:type": "patient"}

            base_ts = self._config.base_timestamp or datetime(2024, 1, 1, tzinfo=timezone.utc)
            agent_resource = resource or self._config.default_resource
            sorted_events = sorted(events, key=lambda e: e.timestamp_min)

            for idx, event in enumerate(sorted_events):
                event_id = f"e_{episode_id}_{idx:04d}"
                ocel_event = self._convert_event(event, base_ts, agent_resource, patient_id)
                all_events[event_id] = ocel_event

        ocel = {
            "ocel:global-log": {
                "ocel:version": self._config.ocel_version,
                "ocel:ordering": "timestamp",
            },
            "ocel:object-types": sorted(object_types),
            "ocel:objects": all_objects,
            "ocel:events": all_events,
        }

        return json.dumps(ocel, indent=self._config.indent, ensure_ascii=False)

    def _build_ocel(
        self,
        episode_id: str,
        events: List[ActivityEvent],
        patient_id: Optional[str] = None,
        objects: Optional[List[OCELObject]] = None,
        resource: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build the OCEL 2.0 structure."""
        base_ts = self._config.base_timestamp or datetime(2024, 1, 1, tzinfo=timezone.utc)
        agent_resource = resource or self._config.default_resource

        # Build objects
        ocel_objects: Dict[str, Dict[str, Any]] = {}
        object_types: Set[str] = set(self.DEFAULT_OBJECT_TYPES)

        # Add patient object
        pid = patient_id or f"patient_{episode_id}"
        ocel_objects[pid] = {"ocel:type": "patient"}

        # Add custom objects
        if objects:
            for obj in objects:
                obj_entry: Dict[str, Any] = {"ocel:type": obj.object_type}
                if self._config.include_object_attributes and obj.attributes:
                    obj_entry["ocel:ovmap"] = obj.attributes
                ocel_objects[obj.object_id] = obj_entry
                object_types.add(obj.object_type)

        # Build events
        ocel_events: Dict[str, Dict[str, Any]] = {}
        sorted_events = sorted(events, key=lambda e: e.timestamp_min)

        for idx, event in enumerate(sorted_events):
            event_id = f"e_{episode_id}_{idx:04d}"
            ocel_event = self._convert_event(event, base_ts, agent_resource, pid)

            # Auto-generate related objects from event type
            related_objects = self._resolve_objects(event, episode_id, idx)
            for obj_id, obj_type in related_objects:
                if obj_id not in ocel_objects:
                    ocel_objects[obj_id] = {"ocel:type": obj_type}
                    object_types.add(obj_type)
                ocel_event["ocel:omap"].append(obj_id)

            ocel_events[event_id] = ocel_event

        return {
            "ocel:global-log": {
                "ocel:version": self._config.ocel_version,
                "ocel:ordering": "timestamp",
            },
            "ocel:object-types": sorted(object_types),
            "ocel:objects": ocel_objects,
            "ocel:events": ocel_events,
        }

    def _convert_event(
        self,
        event: ActivityEvent,
        base_ts: datetime,
        resource: str,
        patient_id: str,
    ) -> Dict[str, Any]:
        """Convert an ActivityEvent to OCEL event dict."""
        timestamp = base_ts + timedelta(minutes=event.timestamp_min)
        ts_str = timestamp.strftime("%Y-%m-%dT%H:%M:%SZ")

        ocel_event: Dict[str, Any] = {
            "ocel:activity": event.name,
            "ocel:timestamp": ts_str,
            "cga:timestamp_min": event.timestamp_min,
            "ocel:omap": [patient_id],
            "ocel:vmap": {
                "resource": resource,
                "timestamp_min": event.timestamp_min,
            },
        }

        # Add tool_call info if available
        raw = event.raw_event or {}
        if raw.get("tool_call"):
            tool_call = raw["tool_call"]
            if tool_call.get("method"):
                ocel_event["ocel:vmap"]["method"] = tool_call["method"]
            if tool_call.get("url"):
                ocel_event["ocel:vmap"]["url"] = tool_call["url"]

        return ocel_event

    def _resolve_objects(
        self,
        event: ActivityEvent,
        episode_id: str,
        idx: int,
    ) -> List[tuple[str, str]]:
        """Resolve related objects using enhanced resolver or fallback.

        Uses ObjectTypeResolver when object_type_config is provided,
        otherwise falls back to the original _infer_related_objects.
        """
        if self._config.object_type_config is not None:
            if self._type_resolver is None:
                from .ocel_object_typing import ObjectTypeResolver
                self._type_resolver = ObjectTypeResolver(self._config.object_type_config)
            return self._type_resolver.resolve_objects(event, episode_id, idx)
        return self._infer_related_objects(event, episode_id, idx)

    def _infer_related_objects(
        self,
        event: ActivityEvent,
        episode_id: str,
        idx: int,
    ) -> List[tuple[str, str]]:
        """Infer related objects from event activity name."""
        related: List[tuple[str, str]] = []
        name = event.name.upper()

        if "ORDER" in name or "QUERY" in name:
            obj_id = f"order_{episode_id}_{idx:04d}"
            if "LAB" in name or "TEST" in name or "OBSERVATION" in name:
                related.append((obj_id, "test"))
            elif "IMAGING" in name or "ECG" in name or "XRAY" in name:
                related.append((obj_id, "test"))
            else:
                related.append((obj_id, "order"))

        elif "PRESCRIBE" in name or "MEDICATION" in name:
            obj_id = f"med_{episode_id}_{idx:04d}"
            related.append((obj_id, "medication"))

        elif "PROCEDURE" in name:
            obj_id = f"proc_{episode_id}_{idx:04d}"
            related.append((obj_id, "procedure"))

        return related
