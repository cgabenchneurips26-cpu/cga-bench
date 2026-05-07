"""Tests for XES outcome perspective and violation overlay export."""
import pytest
from xml.etree.ElementTree import fromstring

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.export.xes_exporter import (
    XESExporter,
    XESExportConfig,
    XESPerspectiveConfig,
)
from cga_bench.cpg_model.schemas.base import (
    CGAScore,
    HarmSeverity,
    ViolationEvent,
    ViolationType,
)


# ============================================
# Test Helpers
# ============================================

def _make_event(name, timestamp_min=0.0, confidence=1.0, match_source="exact"):
    """Create an ActivityEvent for testing."""
    return ActivityEvent(
        name=name,
        timestamp_min=timestamp_min,
        raw_event={},
        confidence=confidence,
        match_source=match_source,
    )


def _make_score(
    episode_id="ep_001",
    compliance=0.85,
    peak_risk=0.7,
    aggregate_risk=1.2,
    total_violations=3,
    violations_by_type=None,
    sub_scores=None,
    synergistic_risk=0.0,
):
    """Create a CGAScore for testing."""
    return CGAScore(
        episode_id=episode_id,
        compliance_score=compliance,
        peak_risk=peak_risk,
        aggregate_risk=aggregate_risk,
        total_violations=total_violations,
        violations_by_type=violations_by_type or {"omission": 2, "commission": 1},
        violation_events=[],
        justified_deviations=0,
        budget_usage={"tokens": 1000},
        sub_scores=sub_scores or {"C1": 0.9, "C2": 0.8, "C3": 1.0, "C4": 0.7, "C5": 0.85},
        synergistic_risk=synergistic_risk,
    )


def _make_violation(
    violation_id="v_001",
    violation_type=ViolationType.OMISSION,
    timestamp_minutes=5.0,
    action_involved=None,
    expected_action=None,
    expected_deadline=None,
    severity=HarmSeverity.MAJOR,
):
    """Create a ViolationEvent for testing."""
    return ViolationEvent(
        violation_id=violation_id,
        violation_type=violation_type,
        timestamp_minutes=timestamp_minutes,
        action_involved=action_involved,
        expected_action=expected_action,
        expected_deadline=expected_deadline,
        state_at_violation="state_initial",
        node_at_violation="node_assessment",
        harm_severity=severity,
        description=f"Test violation {violation_id}",
        guideline_reference="Test Guideline",
    )


_XES_NS = "{http://www.xes-standard.org/}"


def _parse_xes(xml_str):
    """Parse XES XML string."""
    return fromstring(xml_str)


def _tag_match(tag, name):
    """Check if tag matches name with or without namespace."""
    return tag == name or tag == f"{_XES_NS}{name}"


def _get_trace(root):
    """Get first trace element."""
    for child in root:
        if _tag_match(child.tag, "trace"):
            return child
    return None


def _get_traces(root):
    """Get all trace elements."""
    return [child for child in root if _tag_match(child.tag, "trace")]


def _get_events(trace):
    """Get all event elements from a trace."""
    return [child for child in trace if _tag_match(child.tag, "event")]


def _get_attr(elem, key, attr_type="string"):
    """Get attribute value from an element."""
    for child in elem:
        tag = child.tag.replace(_XES_NS, "")
        if tag == attr_type and child.get("key") == key:
            return child.get("value")
    return None


def _get_float_attr(elem, key):
    """Get float attribute value."""
    val = _get_attr(elem, key, "float")
    return float(val) if val is not None else None


# ============================================
# Test Class: Outcome Perspective
# ============================================

class TestOutcomePerspective:
    """Tests for CGAScore outcome annotations on traces."""

    def test_outcome_disabled_by_default(self):
        """Outcome attributes not added when perspective not configured."""
        exporter = XESExporter(XESExportConfig())
        events = [_make_event("order_lab_lactate", 0.0)]
        score = _make_score()

        xml = exporter.export_with_outcomes("ep_001", events, score=score)
        root = _parse_xes(xml)
        trace = _get_trace(root)

        assert _get_float_attr(trace, "outcome:compliance_score") is None

    def test_outcome_enabled_adds_compliance(self):
        """Outcome perspective adds compliance_score to trace."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_outcome_perspective=True)
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]
        score = _make_score(compliance=0.92)

        xml = exporter.export_with_outcomes("ep_001", events, score=score)
        root = _parse_xes(xml)
        trace = _get_trace(root)

        val = _get_float_attr(trace, "outcome:compliance_score")
        assert val == pytest.approx(0.92, abs=1e-4)

    def test_outcome_adds_risk_metrics(self):
        """Outcome perspective adds peak_risk and aggregate_risk."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_outcome_perspective=True)
        )
        exporter = XESExporter(config)
        events = [_make_event("give_antibiotics", 5.0)]
        score = _make_score(peak_risk=0.9, aggregate_risk=1.5)

        xml = exporter.export_with_outcomes("ep_001", events, score=score)
        root = _parse_xes(xml)
        trace = _get_trace(root)

        assert _get_float_attr(trace, "outcome:peak_risk") == pytest.approx(0.9, abs=1e-4)
        assert _get_float_attr(trace, "outcome:aggregate_risk") == pytest.approx(1.5, abs=1e-4)

    def test_outcome_adds_total_violations(self):
        """Outcome perspective adds total_violations as string attr."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_outcome_perspective=True)
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]
        score = _make_score(total_violations=5)

        xml = exporter.export_with_outcomes("ep_001", events, score=score)
        root = _parse_xes(xml)
        trace = _get_trace(root)

        assert _get_attr(trace, "outcome:total_violations") == "5"

    def test_outcome_adds_sub_scores(self):
        """Outcome perspective adds C1-C5 sub-scores."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_outcome_perspective=True)
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]
        sub = {"C1": 0.95, "C2": 0.80, "C3": 1.0, "C4": 0.65, "C5": 0.90}
        score = _make_score(sub_scores=sub)

        xml = exporter.export_with_outcomes("ep_001", events, score=score)
        root = _parse_xes(xml)
        trace = _get_trace(root)

        assert _get_float_attr(trace, "outcome:C1") == pytest.approx(0.95, abs=1e-4)
        assert _get_float_attr(trace, "outcome:C4") == pytest.approx(0.65, abs=1e-4)

    def test_outcome_adds_violation_type_counts(self):
        """Outcome perspective adds violation type summary."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_outcome_perspective=True)
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]
        score = _make_score(violations_by_type={"omission": 3, "timing": 1})

        xml = exporter.export_with_outcomes("ep_001", events, score=score)
        root = _parse_xes(xml)
        trace = _get_trace(root)

        assert _get_attr(trace, "outcome:violations_omission") == "3"
        assert _get_attr(trace, "outcome:violations_timing") == "1"

    def test_outcome_synergistic_risk_included_when_positive(self):
        """Synergistic risk only added when > 0."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_outcome_perspective=True)
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]

        # Zero synergistic risk - should not appear
        score_zero = _make_score(synergistic_risk=0.0)
        xml = exporter.export_with_outcomes("ep_001", events, score=score_zero)
        trace = _get_trace(_parse_xes(xml))
        assert _get_float_attr(trace, "outcome:synergistic_risk") is None

        # Positive synergistic risk - should appear
        score_pos = _make_score(synergistic_risk=0.35)
        xml = exporter.export_with_outcomes("ep_001", events, score=score_pos)
        trace = _get_trace(_parse_xes(xml))
        assert _get_float_attr(trace, "outcome:synergistic_risk") == pytest.approx(0.35, abs=1e-4)

    def test_outcome_without_score_no_crash(self):
        """export_with_outcomes works even without a score."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_outcome_perspective=True)
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]

        xml = exporter.export_with_outcomes("ep_001", events, score=None)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        assert trace is not None
        assert _get_float_attr(trace, "outcome:compliance_score") is None


# ============================================
# Test Class: Violation Overlay
# ============================================

class TestViolationOverlay:
    """Tests for event-level violation annotations."""

    def test_overlay_disabled_by_default(self):
        """Violations not annotated when overlay disabled."""
        exporter = XESExporter(XESExportConfig())
        events = [_make_event("give_nitroglycerin", 10.0)]
        violations = [_make_violation(
            violation_id="v_001",
            violation_type=ViolationType.COMMISSION,
            timestamp_minutes=10.0,
            action_involved="give_nitroglycerin",
        )]

        xml = exporter.export_with_outcomes("ep_001", events, violations=violations)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)
        assert _get_attr(event_elems[0], "violation:type") is None

    def test_overlay_matches_by_timestamp(self):
        """Violation matched to event by timestamp."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_violation_overlay=True)
        )
        exporter = XESExporter(config)
        events = [
            _make_event("assess_vitals", 0.0),
            _make_event("give_nitroglycerin", 10.0),
            _make_event("order_ecg", 15.0),
        ]
        violations = [_make_violation(
            violation_id="v_ntg",
            violation_type=ViolationType.COMMISSION,
            timestamp_minutes=10.0,
            action_involved="give_nitroglycerin",
            severity=HarmSeverity.CATASTROPHIC,
        )]

        xml = exporter.export_with_outcomes("ep_001", events, violations=violations)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        # First event: no violation
        assert _get_attr(event_elems[0], "violation:type") is None
        # Second event: has violation
        assert _get_attr(event_elems[1], "violation:type") == "commission"
        assert _get_attr(event_elems[1], "violation:severity") == str(HarmSeverity.CATASTROPHIC.value)
        assert _get_attr(event_elems[1], "violation:id") == "v_ntg"
        # Third event: no violation
        assert _get_attr(event_elems[2], "violation:type") is None

    def test_overlay_matches_by_action_name(self):
        """Violation matched by action_involved when timestamp doesn't match."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_violation_overlay=True)
        )
        exporter = XESExporter(config)
        events = [
            _make_event("give_nitroglycerin", 12.5),  # Slightly different time
        ]
        violations = [_make_violation(
            violation_id="v_ntg",
            violation_type=ViolationType.COMMISSION,
            timestamp_minutes=10.0,  # Different time
            action_involved="give_nitroglycerin",
            severity=HarmSeverity.SEVERE,
        )]

        xml = exporter.export_with_outcomes("ep_001", events, violations=violations)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "violation:type") == "commission"
        assert _get_attr(event_elems[0], "violation:id") == "v_ntg"

    def test_overlay_includes_expected_action(self):
        """Omission violation includes expected_action attribute."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_violation_overlay=True)
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 5.0)]
        violations = [_make_violation(
            violation_id="v_omit",
            violation_type=ViolationType.OMISSION,
            timestamp_minutes=5.0,
            expected_action="order_lab_blood_culture",
            severity=HarmSeverity.MAJOR,
        )]

        xml = exporter.export_with_outcomes("ep_001", events, violations=violations)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "violation:expected") == "order_lab_blood_culture"

    def test_overlay_includes_deadline(self):
        """Timing violation includes deadline attribute."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_violation_overlay=True)
        )
        exporter = XESExporter(config)
        events = [_make_event("give_antibiotics", 75.0)]
        violations = [_make_violation(
            violation_id="v_timing",
            violation_type=ViolationType.TIMING,
            timestamp_minutes=75.0,
            action_involved="give_antibiotics",
            expected_deadline=60.0,
            severity=HarmSeverity.SEVERE,
        )]

        xml = exporter.export_with_outcomes("ep_001", events, violations=violations)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "violation:type") == "timing"
        assert _get_float_attr(event_elems[0], "violation:deadline_min") == pytest.approx(60.0)

    def test_overlay_no_violations_no_crash(self):
        """No crash when violations list is empty."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_violation_overlay=True)
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]

        xml = exporter.export_with_outcomes("ep_001", events, violations=[])
        root = _parse_xes(xml)
        trace = _get_trace(root)
        assert _get_events(trace)  # Events still present

    def test_overlay_multiple_violations_first_wins(self):
        """When multiple violations match same timestamp, first is used."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_violation_overlay=True)
        )
        exporter = XESExporter(config)
        events = [_make_event("give_nitroglycerin", 10.0)]
        violations = [
            _make_violation(
                violation_id="v_first",
                violation_type=ViolationType.COMMISSION,
                timestamp_minutes=10.0,
                severity=HarmSeverity.CATASTROPHIC,
            ),
            _make_violation(
                violation_id="v_second",
                violation_type=ViolationType.DEVIATION,
                timestamp_minutes=10.0,
                severity=HarmSeverity.MINOR,
            ),
        ]

        xml = exporter.export_with_outcomes("ep_001", events, violations=violations)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "violation:id") == "v_first"
        assert _get_attr(event_elems[0], "violation:type") == "commission"


# ============================================
# Test Class: Comparative Export
# ============================================

class TestComparativeExport:
    """Tests for multi-agent comparative XES export."""

    def test_comparative_basic_two_agents(self):
        """Comparative export produces one trace per agent."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig()
        )
        exporter = XESExporter(config)

        agent_episodes = {
            "rag_gpt4": [
                _make_event("assess_vitals", 0.0),
                _make_event("order_lab_lactate", 5.0),
            ],
            "oracle": [
                _make_event("assess_vitals", 0.0),
                _make_event("order_lab_blood_culture", 2.0),
                _make_event("give_antibiotics", 10.0),
            ],
        }

        xml = exporter.export_comparative("sepsis_001", agent_episodes)
        root = _parse_xes(xml)
        traces = _get_traces(root)

        assert len(traces) == 2

    def test_comparative_has_scenario_attribute(self):
        """Comparative log has scenario_id at log level."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig()
        )
        exporter = XESExporter(config)

        agent_episodes = {"agent_a": [_make_event("assess_vitals", 0.0)]}

        xml = exporter.export_comparative("rv_trap_001", agent_episodes)
        root = _parse_xes(xml)

        assert _get_attr(root, "cga:scenario_id") == "rv_trap_001"

    def test_comparative_traces_have_agent_id(self):
        """Each trace has agent_id attribute."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig()
        )
        exporter = XESExporter(config)

        agent_episodes = {
            "rag_gpt4": [_make_event("assess_vitals", 0.0)],
            "planner": [_make_event("assess_vitals", 0.0)],
        }

        xml = exporter.export_comparative("sepsis_001", agent_episodes)
        root = _parse_xes(xml)
        traces = _get_traces(root)

        agent_ids = [_get_attr(t, "cga:agent_id") for t in traces]
        assert "rag_gpt4" in agent_ids
        assert "planner" in agent_ids

    def test_comparative_with_scores(self):
        """Comparative export with outcome perspective includes scores."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_outcome_perspective=True)
        )
        exporter = XESExporter(config)

        agent_episodes = {
            "rag_gpt4": [_make_event("assess_vitals", 0.0)],
            "oracle": [_make_event("assess_vitals", 0.0)],
        }
        agent_scores = {
            "rag_gpt4": _make_score(compliance=0.75, peak_risk=0.9),
            "oracle": _make_score(compliance=0.98, peak_risk=0.1),
        }

        xml = exporter.export_comparative(
            "sepsis_001", agent_episodes, agent_scores=agent_scores
        )
        root = _parse_xes(xml)
        traces = _get_traces(root)

        # Find traces by agent_id
        rag_trace = next(t for t in traces if _get_attr(t, "cga:agent_id") == "rag_gpt4")
        oracle_trace = next(t for t in traces if _get_attr(t, "cga:agent_id") == "oracle")

        assert _get_float_attr(rag_trace, "outcome:compliance_score") == pytest.approx(0.75, abs=1e-4)
        assert _get_float_attr(oracle_trace, "outcome:compliance_score") == pytest.approx(0.98, abs=1e-4)

    def test_comparative_with_violations(self):
        """Comparative export with violation overlay annotates events."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(enable_violation_overlay=True)
        )
        exporter = XESExporter(config)

        agent_episodes = {
            "bad_agent": [
                _make_event("give_nitroglycerin", 10.0),
            ],
            "good_agent": [
                _make_event("order_right_ecg_v4r", 10.0),
            ],
        }
        agent_violations = {
            "bad_agent": [
                _make_violation(
                    violation_id="v_ntg",
                    violation_type=ViolationType.COMMISSION,
                    timestamp_minutes=10.0,
                    action_involved="give_nitroglycerin",
                    severity=HarmSeverity.CATASTROPHIC,
                )
            ],
            "good_agent": [],  # No violations
        }

        xml = exporter.export_comparative(
            "rv_trap_001", agent_episodes, agent_violations=agent_violations
        )
        root = _parse_xes(xml)
        traces = _get_traces(root)

        bad_trace = next(t for t in traces if _get_attr(t, "cga:agent_id") == "bad_agent")
        good_trace = next(t for t in traces if _get_attr(t, "cga:agent_id") == "good_agent")

        bad_events = _get_events(bad_trace)
        good_events = _get_events(good_trace)

        assert _get_attr(bad_events[0], "violation:type") == "commission"
        assert _get_attr(good_events[0], "violation:type") is None

    def test_comparative_without_scores_or_violations(self):
        """Comparative export works without scores or violations."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_outcome_perspective=True,
                enable_violation_overlay=True,
            )
        )
        exporter = XESExporter(config)

        agent_episodes = {
            "agent_a": [_make_event("assess_vitals", 0.0)],
        }

        xml = exporter.export_comparative("test_001", agent_episodes)
        root = _parse_xes(xml)
        traces = _get_traces(root)
        assert len(traces) == 1

    def test_comparative_trace_ids_use_scenario_agent(self):
        """Trace concept:name follows format scenario_agent."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig()
        )
        exporter = XESExporter(config)

        agent_episodes = {
            "rag_gpt4": [_make_event("assess_vitals", 0.0)],
        }

        xml = exporter.export_comparative("sepsis_001", agent_episodes)
        root = _parse_xes(xml)
        trace = _get_trace(root)

        assert _get_attr(trace, "concept:name") == "sepsis_001_rag_gpt4"


# ============================================
# Test Class: Combined Features
# ============================================

class TestCombinedFeatures:
    """Tests for outcome + violation overlay together."""

    def test_outcome_and_overlay_together(self):
        """Both outcome perspective and violation overlay work simultaneously."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_outcome_perspective=True,
                enable_violation_overlay=True,
            )
        )
        exporter = XESExporter(config)

        events = [
            _make_event("assess_vitals", 0.0),
            _make_event("give_nitroglycerin", 10.0),
        ]
        score = _make_score(compliance=0.6, peak_risk=1.0, aggregate_risk=2.0)
        violations = [_make_violation(
            violation_id="v_ntg",
            violation_type=ViolationType.COMMISSION,
            timestamp_minutes=10.0,
            action_involved="give_nitroglycerin",
            severity=HarmSeverity.CATASTROPHIC,
        )]

        xml = exporter.export_with_outcomes(
            "rv_trap_001", events, score=score, violations=violations
        )
        root = _parse_xes(xml)
        trace = _get_trace(root)

        # Trace-level outcome
        assert _get_float_attr(trace, "outcome:compliance_score") == pytest.approx(0.6, abs=1e-4)
        assert _get_float_attr(trace, "outcome:peak_risk") == pytest.approx(1.0, abs=1e-4)

        # Event-level violation
        event_elems = _get_events(trace)
        assert _get_attr(event_elems[1], "violation:type") == "commission"
        assert _get_attr(event_elems[1], "violation:id") == "v_ntg"

    def test_backward_compatible_export_episode(self):
        """Original export_episode method unaffected by new features."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_outcome_perspective=True,
                enable_violation_overlay=True,
            )
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)

        # No outcome or violation attributes (not using export_with_outcomes)
        assert _get_float_attr(trace, "outcome:compliance_score") is None

    def test_export_with_outcomes_no_perspective_config(self):
        """export_with_outcomes works without perspective config (backward compat)."""
        exporter = XESExporter(XESExportConfig())
        events = [_make_event("assess_vitals", 0.0)]
        score = _make_score()

        xml = exporter.export_with_outcomes("ep_001", events, score=score)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        assert trace is not None
        # No outcome attrs since perspective_config is None
        assert _get_float_attr(trace, "outcome:compliance_score") is None

    def test_clinical_sepsis_scenario(self):
        """Full clinical scenario: sepsis with omissions and timing violations."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_outcome_perspective=True,
                enable_violation_overlay=True,
            )
        )
        exporter = XESExporter(config)

        events = [
            _make_event("assess_vitals", 0.0),
            _make_event("order_lab_lactate", 5.0),
            _make_event("give_antibiotics", 75.0),  # Late (deadline 60min)
        ]
        score = _make_score(
            compliance=0.65,
            peak_risk=0.9,
            aggregate_risk=1.8,
            total_violations=2,
            violations_by_type={"omission": 1, "timing": 1},
            sub_scores={"C1": 0.9, "C2": 0.6, "C3": 1.0, "C4": 0.4, "C5": 1.0},
        )
        violations = [
            _make_violation(
                violation_id="v_culture",
                violation_type=ViolationType.OMISSION,
                timestamp_minutes=75.0,
                expected_action="order_lab_blood_culture",
                severity=HarmSeverity.MAJOR,
            ),
            _make_violation(
                violation_id="v_abx_late",
                violation_type=ViolationType.TIMING,
                timestamp_minutes=75.0,
                action_involved="give_antibiotics",
                expected_deadline=60.0,
                severity=HarmSeverity.SEVERE,
            ),
        ]

        xml = exporter.export_with_outcomes(
            "sepsis_001", events, score=score, violations=violations
        )
        root = _parse_xes(xml)
        trace = _get_trace(root)

        # Outcome perspective
        assert _get_float_attr(trace, "outcome:compliance_score") == pytest.approx(0.65, abs=1e-4)
        assert _get_float_attr(trace, "outcome:C4") == pytest.approx(0.4, abs=1e-4)
        assert _get_attr(trace, "outcome:violations_omission") == "1"
        assert _get_attr(trace, "outcome:violations_timing") == "1"

        # Violation overlay on antibiotics event (timestamp 75.0)
        event_elems = _get_events(trace)
        # The violation at 75.0 should match the antibiotics event at 75.0
        # First violation in list at that timestamp wins
        abx_event = event_elems[2]
        assert _get_attr(abx_event, "violation:type") in ("omission", "timing")
