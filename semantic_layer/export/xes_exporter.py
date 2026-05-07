"""
XES 2.0 (IEEE 1849-2016) exporter for clinical episode logs.

Converts ActivityEvent sequences into standard XES XML format
for use with process mining tools (ProM, Disco, PM4Py, etc.).
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple
from xml.etree.ElementTree import Element, SubElement, tostring
from xml.dom import minidom

from ..conformance.activity import ActivityEvent
from cga_bench.cpg_model.schemas.base import CGAScore, ViolationEvent


@dataclass
class ClinicalPhaseConfig:
    """Configuration for clinical phase annotations.

    Defines phase boundaries based on timestamps or action patterns.
    """
    # Phase definitions: phase_name -> (start_pattern_or_time, end_pattern_or_time)
    phase_definitions: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    # Default phase if no pattern matches
    default_phase: str = "unknown"
    # Whether to emit phase transition events
    emit_phase_transitions: bool = False

    @classmethod
    def sepsis_phases(cls) -> "ClinicalPhaseConfig":
        """Standard sepsis hour-1 bundle phases."""
        return cls(
            phase_definitions={
                "initial_assessment": {
                    "start_time": 0,
                    "end_patterns": ["order_lab_lactate", "order_lab_blood_culture"],
                },
                "resuscitation": {
                    "start_patterns": ["give_crystalloid", "start_vasopressor"],
                    "end_patterns": ["reassess_volume_status"],
                },
                "antibiotic_administration": {
                    "start_patterns": ["give_broad_spectrum_antibiotics"],
                    "end_patterns": ["give_broad_spectrum_antibiotics"],
                },
                "stabilization": {
                    "start_time": 60,
                    "end_time": 180,
                },
            },
            default_phase="assessment",
            emit_phase_transitions=True,
        )

    @classmethod
    def stemi_phases(cls) -> "ClinicalPhaseConfig":
        """Standard STEMI management phases."""
        return cls(
            phase_definitions={
                "initial_assessment": {
                    "start_time": 0,
                    "end_patterns": ["order_ecg", "assess_vitals"],
                },
                "pci_preparation": {
                    "start_patterns": ["activate_cath_lab"],
                    "end_patterns": ["perform_pci"],
                },
                "adjunctive_therapy": {
                    "start_patterns": ["give_aspirin", "give_p2y12_inhibitor"],
                },
            },
            default_phase="assessment",
            emit_phase_transitions=True,
        )


@dataclass
class ProcessMiningHints:
    """Hints for process mining tools (ProM, Disco, PM4Py).

    Provides BPMN-like activity type annotations and pattern hints.
    """
    # BPMN activity type mappings: action_pattern -> activity_type
    # Types: task, userTask, serviceTask, manualTask, sendTask, receiveTask
    activity_type_mappings: Dict[str, str] = field(default_factory=dict)
    # Gateway hint patterns (decision points)
    gateway_patterns: List[str] = field(default_factory=list)
    # Parallel activity patterns (can occur concurrently)
    parallel_patterns: List[List[str]] = field(default_factory=list)
    # Loop detection patterns
    loop_patterns: List[str] = field(default_factory=list)

    @classmethod
    def clinical_defaults(cls) -> "ProcessMiningHints":
        """Default hints for clinical workflows."""
        return cls(
            activity_type_mappings={
                "assess_*": "userTask",
                "order_*": "serviceTask",
                "give_*": "manualTask",
                "start_*": "manualTask",
                "consult_*": "sendTask",
                "activate_*": "sendTask",
                "perform_*": "manualTask",
                "reassess_*": "userTask",
            },
            gateway_patterns=[
                "assess_*",  # Assessment often leads to decision
                "check_*",   # Explicit decision points
            ],
            parallel_patterns=[
                ["order_lab_lactate", "order_lab_blood_culture"],
                ["give_aspirin", "give_heparin"],
            ],
            loop_patterns=[
                "reassess_*",  # Reassessment may loop back
                "repeat_*",    # Explicit repetition
            ],
        )


@dataclass
class XESPerspectiveConfig:
    """Configuration for multi-perspective XES export.

    All features are opt-in. When None is passed as perspective_config
    in XESExportConfig, the exporter produces original output.
    """
    # Lifecycle perspective
    enable_lifecycle_transitions: bool = True
    infer_start_complete: bool = True

    # Resource perspective
    enable_resource_attributes: bool = True
    resource_role: Optional[str] = None
    resource_group: Optional[str] = None

    # Data perspective
    enable_data_perspective: bool = True
    include_fhir_resources: bool = True
    include_lab_values: bool = True
    include_vital_signs: bool = False
    max_payload_attributes: int = 20

    # Performance perspective
    enable_performance_metrics: bool = True
    include_confidence: bool = True
    include_match_source: bool = True
    include_error_info: bool = True

    # Cost perspective
    enable_cost_perspective: bool = False
    default_cost_per_event: float = 0.0

    # Outcome perspective (trace-level CGAScore annotations)
    enable_outcome_perspective: bool = False

    # Violation overlay (event-level violation annotations)
    enable_violation_overlay: bool = False

    # Clinical phase perspective (NEW)
    enable_clinical_phases: bool = False
    clinical_phase_config: Optional[ClinicalPhaseConfig] = None

    # Process mining hints (NEW)
    enable_process_hints: bool = False
    process_hints: Optional[ProcessMiningHints] = None

    # Variant classification (NEW)
    enable_variant_classification: bool = False
    variant_patterns: Dict[str, List[str]] = field(default_factory=dict)


@dataclass
class XESExportConfig:
    """Configuration for XES export.

    All fields optional for backward compatibility.
    """
    xes_version: str = "2.0"
    include_lifecycle: bool = True
    include_resource: bool = True
    default_resource: str = "agent"
    base_timestamp: Optional[datetime] = None  # Episode start time (defaults to epoch)
    pretty_print: bool = True
    perspective_config: Optional[XESPerspectiveConfig] = None


class XESExporter:
    """Exports ActivityEvent sequences to XES 2.0 XML format.

    Produces IEEE 1849-2016 compliant event logs suitable for
    process mining analysis and conformance checking tools.
    """

    XES_NAMESPACE = "http://www.xes-standard.org/"

    def __init__(self, config: Optional[XESExportConfig] = None):
        self._config = config or XESExportConfig()

    def export_episode(
        self,
        episode_id: str,
        events: List[ActivityEvent],
        resource: Optional[str] = None,
        attributes: Optional[Dict[str, str]] = None,
    ) -> str:
        """Export a single episode as XES XML string.

        Args:
            episode_id: Unique episode/case identifier
            events: List of ActivityEvent objects
            resource: Agent/resource identifier (overrides config default)
            attributes: Additional trace-level attributes

        Returns:
            XES XML string
        """
        log = self._create_log_element()
        trace = self._create_trace(episode_id, events, resource, attributes)
        log.append(trace)
        return self._serialize(log)

    def export_episodes(
        self,
        episodes: Dict[str, List[ActivityEvent]],
        resource: Optional[str] = None,
    ) -> str:
        """Export multiple episodes as a single XES log.

        Args:
            episodes: Dict of episode_id -> event list
            resource: Agent/resource identifier

        Returns:
            XES XML string with multiple traces
        """
        log = self._create_log_element()
        for episode_id, events in episodes.items():
            trace = self._create_trace(episode_id, events, resource)
            log.append(trace)
        return self._serialize(log)

    def export_with_outcomes(
        self,
        episode_id: str,
        events: List[ActivityEvent],
        score: Optional[CGAScore] = None,
        violations: Optional[List[ViolationEvent]] = None,
        resource: Optional[str] = None,
        attributes: Optional[Dict[str, str]] = None,
    ) -> str:
        """Export episode with outcome and violation annotations.

        Enriches the XES trace with:
        - Trace-level: CGAScore metrics (compliance, risk, sub-scores)
        - Event-level: Violation overlay (type, severity for violated events)

        Args:
            episode_id: Unique episode identifier
            events: List of ActivityEvent objects
            score: Optional CGAScore for outcome perspective
            violations: Optional list of violations for event overlay
            resource: Agent/resource identifier
            attributes: Additional trace-level attributes

        Returns:
            XES XML string with outcome annotations
        """
        log = self._create_log_element()
        trace = self._create_trace(episode_id, events, resource, attributes)

        # Outcome perspective: add CGAScore as trace attributes
        pc = self._config.perspective_config
        if score and pc and pc.enable_outcome_perspective:
            self._add_outcome_attributes(trace, score)

        # Violation overlay: annotate events with violation data
        if violations and pc and pc.enable_violation_overlay:
            self._apply_violation_overlay(trace, events, violations)

        log.append(trace)
        return self._serialize(log)

    def export_comparative(
        self,
        scenario_id: str,
        agent_episodes: Dict[str, List[ActivityEvent]],
        agent_scores: Optional[Dict[str, CGAScore]] = None,
        agent_violations: Optional[Dict[str, List[ViolationEvent]]] = None,
    ) -> str:
        """Export multiple agents' episodes for comparative process mining.

        Produces a single XES log where each trace represents one agent's
        episode for the same scenario. Agent ID is the resource attribute.

        Args:
            scenario_id: The scenario being compared
            agent_episodes: Dict of agent_id -> event list
            agent_scores: Optional dict of agent_id -> CGAScore
            agent_violations: Optional dict of agent_id -> violations

        Returns:
            XES XML string with comparative traces
        """
        log = self._create_log_element()

        # Add log-level scenario attribute
        self._add_string_attr(log, "cga:scenario_id", scenario_id)

        for agent_id, events in agent_episodes.items():
            trace_id = f"{scenario_id}_{agent_id}"
            trace = self._create_trace(trace_id, events, agent_id)

            # Add agent identifier
            self._add_string_attr(trace, "cga:agent_id", agent_id)

            # Outcome perspective
            pc = self._config.perspective_config
            if pc and pc.enable_outcome_perspective:
                score = (agent_scores or {}).get(agent_id)
                if score:
                    self._add_outcome_attributes(trace, score)

            # Violation overlay
            if pc and pc.enable_violation_overlay:
                violations = (agent_violations or {}).get(agent_id, [])
                if violations:
                    self._apply_violation_overlay(trace, events, violations)

            log.append(trace)

        return self._serialize(log)

    def _create_log_element(self) -> Element:
        """Create the root <log> element with extensions."""
        log = Element("log")
        log.set("xes.version", self._config.xes_version)
        log.set("xmlns", self.XES_NAMESPACE)

        # Standard extensions
        self._add_extension(log, "Concept", "concept", "http://www.xes-standard.org/concept.xesext")
        self._add_extension(log, "Time", "time", "http://www.xes-standard.org/time.xesext")
        if self._config.include_lifecycle:
            self._add_extension(log, "Lifecycle", "lifecycle", "http://www.xes-standard.org/lifecycle.xesext")
        if self._config.include_resource:
            self._add_extension(log, "Organizational", "org", "http://www.xes-standard.org/org.xesext")

        # Multi-perspective extensions
        pc = self._config.perspective_config
        if pc:
            if pc.enable_performance_metrics:
                self._add_extension(log, "Performance", "perf", "http://www.xes-standard.org/perf.xesext")
            if pc.enable_data_perspective:
                self._add_extension(log, "Data", "data", "http://cga-bench.org/xes/data.xesext")
            if pc.enable_cost_perspective:
                self._add_extension(log, "Cost", "cost", "http://www.xes-standard.org/cost.xesext")
            if pc.enable_clinical_phases:
                self._add_extension(log, "Clinical", "clinical", "http://cga-bench.org/xes/clinical.xesext")
            if pc.enable_process_hints:
                self._add_extension(log, "BPMN", "bpmn", "http://cga-bench.org/xes/bpmn.xesext")

        # Global event attributes
        global_event = SubElement(log, "global", scope="event")
        self._add_string_attr(global_event, "concept:name", "__INVALID__")
        self._add_date_attr(global_event, "time:timestamp", "1970-01-01T00:00:00.000+00:00")
        if self._config.include_lifecycle:
            self._add_string_attr(global_event, "lifecycle:transition", "complete")

        return log

    def _create_trace(
        self,
        episode_id: str,
        events: List[ActivityEvent],
        resource: Optional[str] = None,
        attributes: Optional[Dict[str, str]] = None,
    ) -> Element:
        """Create a <trace> element for one episode."""
        trace = Element("trace")
        self._add_string_attr(trace, "concept:name", episode_id)

        # Additional trace-level attributes
        if attributes:
            for key, value in attributes.items():
                self._add_string_attr(trace, key, value)

        # Sort events by timestamp
        sorted_events = sorted(events, key=lambda e: e.timestamp_min)

        # Variant classification (NEW)
        pc = self._config.perspective_config
        if pc and pc.enable_variant_classification and pc.variant_patterns:
            variant = self.classify_variant(sorted_events, pc.variant_patterns)
            self._add_string_attr(trace, "process:variant", variant)

        base_ts = self._config.base_timestamp or datetime(2024, 1, 1, tzinfo=timezone.utc)
        agent_resource = resource or self._config.default_resource

        for i, event in enumerate(sorted_events):
            prev_event = sorted_events[i - 1] if i > 0 else None
            next_event = sorted_events[i + 1] if i < len(sorted_events) - 1 else None
            event_elem = self._create_event_element(
                event, base_ts, agent_resource, prev_event, next_event
            )
            trace.append(event_elem)

        return trace

    def _create_event_element(
        self,
        event: ActivityEvent,
        base_ts: datetime,
        resource: str,
        prev_event: Optional[ActivityEvent] = None,
        next_event: Optional[ActivityEvent] = None,
    ) -> Element:
        """Create an <event> element with optional multi-perspective attributes."""
        event_elem = Element("event")

        # concept:name (activity name)
        self._add_string_attr(event_elem, "concept:name", event.name)

        # time:timestamp
        timestamp = base_ts + timedelta(minutes=event.timestamp_min)
        ts_str = timestamp.strftime("%Y-%m-%dT%H:%M:%S") + "+00:00"
        self._add_date_attr(event_elem, "time:timestamp", ts_str)
        # Preserve original timestamp_min as custom attribute for roundtrip fidelity
        self._add_float_attr(event_elem, "cga:timestamp_min", event.timestamp_min)

        pc = self._config.perspective_config

        # lifecycle:transition (enhanced when perspective_config set)
        if self._config.include_lifecycle:
            if pc and pc.enable_lifecycle_transitions:
                transition = self._infer_lifecycle_transition(event)
            else:
                transition = "complete"
            self._add_string_attr(event_elem, "lifecycle:transition", transition)

        # org:resource (enhanced with role/group)
        if self._config.include_resource:
            self._add_string_attr(event_elem, "org:resource", resource)
            if pc and pc.enable_resource_attributes:
                self._add_resource_perspective(event_elem, pc)

        # Data perspective
        if pc and pc.enable_data_perspective:
            self._add_data_perspective(event_elem, event, pc)

        # Performance perspective
        if pc and pc.enable_performance_metrics:
            self._add_performance_perspective(event_elem, event, next_event, pc)

        # Cost perspective
        if pc and pc.enable_cost_perspective:
            self._add_cost_perspective(event_elem, event, pc)

        # Standard tool_call attributes (always included)
        raw = event.raw_event or {}
        if raw.get("tool_call"):
            tool_call = raw["tool_call"]
            if tool_call.get("method"):
                self._add_string_attr(event_elem, "cga:method", tool_call["method"])
            if tool_call.get("url"):
                self._add_string_attr(event_elem, "cga:url", tool_call["url"])

        # Clinical phase perspective (NEW)
        if pc and pc.enable_clinical_phases and pc.clinical_phase_config:
            self._add_clinical_phase(event_elem, event, pc.clinical_phase_config)

        # Process mining hints (NEW)
        if pc and pc.enable_process_hints and pc.process_hints:
            self._add_process_hints(event_elem, event, pc.process_hints)

        return event_elem

    # ------------------------------------------------------------------
    # Multi-perspective handlers
    # ------------------------------------------------------------------

    def _infer_lifecycle_transition(self, event: ActivityEvent) -> str:
        """Infer lifecycle transition from event response data.

        Error responses produce "abort", otherwise "complete".
        """
        raw = event.raw_event or {}
        response_text = raw.get("response_text") or ""
        if self._is_error_response(response_text):
            return "abort"
        return "complete"

    def _is_error_response(self, response_text: str) -> bool:
        """Check if response indicates an error."""
        if not response_text:
            return False
        text = response_text.strip()
        if "Client Error" in text or "Server Error" in text:
            return True
        if text.startswith("Error in sending"):
            return True
        if '"resourceType": "OperationOutcome"' in text or '"resourceType":"OperationOutcome"' in text:
            return True
        return False

    def _add_resource_perspective(self, event_elem: Element, config: XESPerspectiveConfig):
        """Add enhanced resource attributes: role, group."""
        if config.resource_role:
            self._add_string_attr(event_elem, "org:role", config.resource_role)
        if config.resource_group:
            self._add_string_attr(event_elem, "org:group", config.resource_group)

    def _add_data_perspective(
        self,
        event_elem: Element,
        event: ActivityEvent,
        config: XESPerspectiveConfig,
    ):
        """Add data attributes from FHIR payload and results."""
        raw = event.raw_event or {}
        attr_count = 0

        if config.include_fhir_resources:
            tool_call = raw.get("tool_call") or {}
            payload = tool_call.get("payload") or {}

            if payload.get("resourceType"):
                self._add_string_attr(
                    event_elem, "data:resource_type", str(payload["resourceType"])
                )
                attr_count += 1

            if isinstance(payload.get("code"), dict):
                codings = payload["code"].get("coding", [])
                if codings and isinstance(codings, list):
                    first_coding = codings[0] if isinstance(codings[0], dict) else {}
                    if first_coding.get("code"):
                        self._add_string_attr(
                            event_elem, "data:code", str(first_coding["code"])
                        )
                        attr_count += 1
                    if first_coding.get("system"):
                        self._add_string_attr(
                            event_elem, "data:code_system", str(first_coding["system"])
                        )
                        attr_count += 1
                    if first_coding.get("display"):
                        self._add_string_attr(
                            event_elem, "data:code_display", str(first_coding["display"])
                        )
                        attr_count += 1

        if config.include_lab_values:
            for result in raw.get("new_results") or []:
                if attr_count >= config.max_payload_attributes:
                    break
                if isinstance(result, dict):
                    if result.get("code"):
                        self._add_string_attr(
                            event_elem, "data:result_code", str(result["code"])
                        )
                        attr_count += 1
                    if result.get("value") is not None:
                        try:
                            self._add_float_attr(
                                event_elem, "data:result_value", float(result["value"])
                            )
                            attr_count += 1
                        except (ValueError, TypeError):
                            pass
                    if result.get("unit"):
                        self._add_string_attr(
                            event_elem, "data:result_unit", str(result["unit"])
                        )
                        attr_count += 1
                    if result.get("reference_range"):
                        self._add_string_attr(
                            event_elem, "data:reference_range", str(result["reference_range"])
                        )
                        attr_count += 1
                    break  # Only first result to avoid attribute explosion

    def _add_performance_perspective(
        self,
        event_elem: Element,
        event: ActivityEvent,
        next_event: Optional[ActivityEvent],
        config: XESPerspectiveConfig,
    ):
        """Add performance metrics: duration, confidence, match source."""
        if next_event is not None:
            duration_min = next_event.timestamp_min - event.timestamp_min
            self._add_float_attr(event_elem, "perf:duration_minutes", duration_min)

        if config.include_confidence:
            self._add_float_attr(event_elem, "quality:confidence", event.confidence)

        if config.include_match_source:
            self._add_string_attr(event_elem, "quality:match_source", event.match_source)

        if config.include_error_info:
            raw = event.raw_event or {}
            response_text = raw.get("response_text") or ""
            if self._is_error_response(response_text):
                self._add_string_attr(event_elem, "quality:has_error", "true")

    def _add_cost_perspective(
        self,
        event_elem: Element,
        event: ActivityEvent,
        config: XESPerspectiveConfig,
    ):
        """Add cost attributes."""
        if config.default_cost_per_event > 0:
            self._add_float_attr(event_elem, "cost:total", config.default_cost_per_event)

    def _add_outcome_attributes(self, trace: Element, score: CGAScore):
        """Add CGAScore outcome metrics as trace-level attributes."""
        self._add_float_attr(trace, "outcome:compliance_score", score.compliance_score)
        self._add_float_attr(trace, "outcome:peak_risk", score.peak_risk)
        self._add_float_attr(trace, "outcome:aggregate_risk", score.aggregate_risk)
        self._add_string_attr(trace, "outcome:total_violations", str(score.total_violations))

        # Sub-scores
        for construct, value in score.sub_scores.items():
            self._add_float_attr(trace, f"outcome:{construct}", value)

        # Violation type summary
        for vtype, count in score.violations_by_type.items():
            self._add_string_attr(trace, f"outcome:violations_{vtype}", str(count))

        # Synergistic risk (if present)
        if score.synergistic_risk > 0:
            self._add_float_attr(trace, "outcome:synergistic_risk", score.synergistic_risk)

    def _apply_violation_overlay(
        self,
        trace: Element,
        events: List[ActivityEvent],
        violations: List[ViolationEvent],
    ):
        """Annotate trace events with violation data where timestamps match."""
        # Build violation lookup by timestamp (with tolerance)
        violation_by_time: Dict[float, List[ViolationEvent]] = {}
        for v in violations:
            key = round(v.timestamp_minutes, 1)
            violation_by_time.setdefault(key, []).append(v)

        # Also build action-based lookup
        violation_by_action: Dict[str, ViolationEvent] = {}
        for v in violations:
            if v.action_involved:
                violation_by_action[v.action_involved.lower()] = v

        # Iterate over event elements in trace
        event_elements = [elem for elem in trace if elem.tag == "event"]
        sorted_events = sorted(events, key=lambda e: e.timestamp_min)

        for i, event_elem in enumerate(event_elements):
            if i >= len(sorted_events):
                break
            event = sorted_events[i]

            # Match by timestamp
            time_key = round(event.timestamp_min, 1)
            matched_violations = violation_by_time.get(time_key, [])

            # Match by action name
            if not matched_violations:
                event_name = event.name.lower()
                if event_name in violation_by_action:
                    matched_violations = [violation_by_action[event_name]]

            for v in matched_violations:
                self._add_string_attr(event_elem, "violation:type", v.violation_type.value)
                self._add_string_attr(event_elem, "violation:severity", v.harm_severity.value)
                self._add_string_attr(event_elem, "violation:id", v.violation_id)
                if v.expected_action:
                    self._add_string_attr(event_elem, "violation:expected", v.expected_action)
                if v.expected_deadline:
                    self._add_float_attr(event_elem, "violation:deadline_min", v.expected_deadline)
                break  # Only annotate first matching violation per event

    def _add_extension(self, parent: Element, name: str, prefix: str, uri: str):
        """Add an <extension> element."""
        ext = SubElement(parent, "extension")
        ext.set("name", name)
        ext.set("prefix", prefix)
        ext.set("uri", uri)

    def _add_string_attr(self, parent: Element, key: str, value: str):
        """Add a <string> attribute element."""
        attr = SubElement(parent, "string")
        attr.set("key", key)
        attr.set("value", value)

    def _add_date_attr(self, parent: Element, key: str, value: str):
        """Add a <date> attribute element."""
        attr = SubElement(parent, "date")
        attr.set("key", key)
        attr.set("value", value)

    def _add_float_attr(self, parent: Element, key: str, value: float):
        """Add a <float> attribute element."""
        attr = SubElement(parent, "float")
        attr.set("key", key)
        attr.set("value", f"{value:.6f}")

    def _serialize(self, element: Element) -> str:
        """Serialize Element to XML string."""
        raw_xml = tostring(element, encoding="unicode", xml_declaration=False)
        if self._config.pretty_print:
            dom = minidom.parseString(raw_xml)
            pretty = dom.toprettyxml(indent="  ", encoding=None)
            # Remove extra XML declaration from minidom
            lines = pretty.split("\n")
            if lines and lines[0].startswith("<?xml"):
                lines = lines[1:]
            return "\n".join(line for line in lines if line.strip())
        return raw_xml

    # ------------------------------------------------------------------
    # Clinical Phase Perspective (NEW)
    # ------------------------------------------------------------------

    def _add_clinical_phase(
        self,
        event_elem: Element,
        event: ActivityEvent,
        config: ClinicalPhaseConfig,
    ):
        """Add clinical phase annotation to event.

        Determines phase based on timestamp and action pattern matching.
        """
        phase = self._determine_phase(event, config)
        if phase:
            self._add_string_attr(event_elem, "clinical:phase", phase)

    def _determine_phase(
        self,
        event: ActivityEvent,
        config: ClinicalPhaseConfig,
    ) -> str:
        """Determine clinical phase for an event."""
        event_name = event.name.lower()
        event_time = event.timestamp_min

        for phase_name, phase_def in config.phase_definitions.items():
            # Check time-based boundaries
            start_time = phase_def.get("start_time", 0)
            end_time = phase_def.get("end_time", float("inf"))

            if start_time <= event_time <= end_time:
                # Also check pattern-based boundaries
                start_patterns = phase_def.get("start_patterns", [])
                end_patterns = phase_def.get("end_patterns", [])

                # If no patterns defined, time match is sufficient
                if not start_patterns and not end_patterns:
                    return phase_name

                # Check if event matches start or end patterns
                for pattern in start_patterns + end_patterns:
                    if self._matches_pattern(event_name, pattern):
                        return phase_name

        return config.default_phase

    def _matches_pattern(self, event_name: str, pattern: str) -> bool:
        """Check if event name matches a pattern (supports wildcards)."""
        # Convert wildcard pattern to regex
        regex_pattern = pattern.replace("*", ".*").replace("?", ".")
        return bool(re.match(f"^{regex_pattern}$", event_name, re.IGNORECASE))

    # ------------------------------------------------------------------
    # Process Mining Hints (NEW)
    # ------------------------------------------------------------------

    def _add_process_hints(
        self,
        event_elem: Element,
        event: ActivityEvent,
        hints: ProcessMiningHints,
    ):
        """Add process mining hints to event.

        Provides BPMN activity type annotations and pattern hints.
        """
        event_name = event.name.lower()

        # Activity type hint
        activity_type = self._infer_activity_type(event_name, hints)
        if activity_type:
            self._add_string_attr(event_elem, "bpmn:activityType", activity_type)

        # Gateway hint (decision point)
        if self._is_gateway_activity(event_name, hints):
            self._add_string_attr(event_elem, "bpmn:isGateway", "true")

        # Loop hint
        if self._is_loop_activity(event_name, hints):
            self._add_string_attr(event_elem, "bpmn:isLoop", "true")

    def _infer_activity_type(
        self,
        event_name: str,
        hints: ProcessMiningHints,
    ) -> Optional[str]:
        """Infer BPMN activity type from event name."""
        for pattern, activity_type in hints.activity_type_mappings.items():
            if self._matches_pattern(event_name, pattern):
                return activity_type
        return None

    def _is_gateway_activity(
        self,
        event_name: str,
        hints: ProcessMiningHints,
    ) -> bool:
        """Check if event represents a decision gateway."""
        for pattern in hints.gateway_patterns:
            if self._matches_pattern(event_name, pattern):
                return True
        return False

    def _is_loop_activity(
        self,
        event_name: str,
        hints: ProcessMiningHints,
    ) -> bool:
        """Check if event represents a loop point."""
        for pattern in hints.loop_patterns:
            if self._matches_pattern(event_name, pattern):
                return True
        return False

    # ------------------------------------------------------------------
    # Variant Classification (NEW)
    # ------------------------------------------------------------------

    def classify_variant(
        self,
        events: List[ActivityEvent],
        variant_patterns: Dict[str, List[str]],
    ) -> str:
        """Classify event sequence into a process variant.

        Args:
            events: List of events in the trace
            variant_patterns: Dict of variant_name -> list of required action patterns

        Returns:
            Variant name or "other" if no pattern matches
        """
        event_names = [e.name.lower() for e in events]

        for variant_name, required_patterns in variant_patterns.items():
            if self._sequence_matches_patterns(event_names, required_patterns):
                return variant_name

        return "other"

    def _sequence_matches_patterns(
        self,
        event_names: List[str],
        patterns: List[str],
    ) -> bool:
        """Check if event sequence contains all required patterns in order."""
        pattern_idx = 0
        for event_name in event_names:
            if pattern_idx >= len(patterns):
                break
            if self._matches_pattern(event_name, patterns[pattern_idx]):
                pattern_idx += 1
        return pattern_idx >= len(patterns)
