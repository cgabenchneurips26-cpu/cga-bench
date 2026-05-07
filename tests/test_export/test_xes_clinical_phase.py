"""Tests for clinical phase perspective and process mining hints in XES export."""
import pytest
from xml.etree.ElementTree import fromstring

from cga_bench.semantic_layer.conformance.activity import ActivityEvent
from cga_bench.semantic_layer.export.xes_exporter import (
    XESExporter,
    XESExportConfig,
    XESPerspectiveConfig,
    ClinicalPhaseConfig,
    ProcessMiningHints,
)


# XES namespace handling
_XES = "{http://www.xes-standard.org/}"


def _make_event(name, timestamp_min=0.0, confidence=1.0, match_source="exact"):
    """Create an ActivityEvent for testing."""
    return ActivityEvent(
        name=name,
        timestamp_min=timestamp_min,
        raw_event={},
        confidence=confidence,
        match_source=match_source,
    )


def _parse_xes(xml_str):
    """Parse XES XML string and return root element."""
    return fromstring(xml_str)


def _get_trace(root):
    """Get first trace element."""
    for child in root:
        tag = child.tag.replace(_XES, "")
        if tag == "trace":
            return child
    return None


def _get_events(trace):
    """Get all event elements from a trace."""
    return [child for child in trace if child.tag.replace(_XES, "") == "event"]


def _get_attr(elem, key, attr_type="string"):
    """Get an attribute value from an element."""
    for child in elem:
        tag = child.tag.replace(_XES, "")
        if tag == attr_type and child.get("key") == key:
            return child.get("value")
    return None


def _get_extensions(root):
    """Get all extension names from the log element."""
    exts = [child for child in root if child.tag.replace(_XES, "") == "extension"]
    return [ext.get("name") for ext in exts]


# ============================================
# Test Class: Clinical Phase Perspective
# ============================================

class TestClinicalPhasePerspective:
    """Tests for clinical phase annotations on events."""

    def test_clinical_phase_disabled_by_default(self):
        """Phase attributes not added when perspective not configured."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "clinical:phase") is None

    def test_clinical_phase_enabled_adds_phase(self):
        """Clinical phase enabled adds phase attribute to events."""
        phase_config = ClinicalPhaseConfig(
            phase_definitions={
                "assessment": {"start_time": 0, "end_time": 30},
            },
            default_phase="unknown",
        )
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_clinical_phases=True,
                clinical_phase_config=phase_config,
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 5.0)]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "clinical:phase") == "assessment"

    def test_sepsis_phases_preset(self):
        """Test sepsis_phases() preset configuration."""
        phase_config = ClinicalPhaseConfig.sepsis_phases()
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_clinical_phases=True,
                clinical_phase_config=phase_config,
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [
            _make_event("order_lab_lactate", 5.0),  # Should match initial_assessment
        ]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "clinical:phase") == "initial_assessment"

    def test_stemi_phases_preset(self):
        """Test stemi_phases() preset configuration."""
        phase_config = ClinicalPhaseConfig.stemi_phases()
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_clinical_phases=True,
                clinical_phase_config=phase_config,
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [
            _make_event("activate_cath_lab", 15.0),
        ]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "clinical:phase") == "pci_preparation"

    def test_default_phase_used_when_no_match(self):
        """Default phase used when no pattern matches."""
        phase_config = ClinicalPhaseConfig(
            phase_definitions={
                "specific_phase": {"start_patterns": ["specific_action"]},
            },
            default_phase="general",
        )
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_clinical_phases=True,
                clinical_phase_config=phase_config,
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [_make_event("unrelated_action", 0.0)]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "clinical:phase") == "general"

    def test_clinical_extension_declared(self):
        """Clinical extension declared in log when enabled."""
        phase_config = ClinicalPhaseConfig.sepsis_phases()
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_clinical_phases=True,
                clinical_phase_config=phase_config,
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        extensions = _get_extensions(root)

        assert "Clinical" in extensions


# ============================================
# Test Class: Process Mining Hints
# ============================================

class TestProcessMiningHints:
    """Tests for BPMN activity type hints."""

    def test_process_hints_disabled_by_default(self):
        """BPMN hints not added when disabled."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "bpmn:activityType") is None

    def test_activity_type_mapping(self):
        """Activity type inferred from mapping patterns."""
        hints = ProcessMiningHints(
            activity_type_mappings={
                "assess_*": "userTask",
                "order_*": "serviceTask",
            }
        )
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_process_hints=True,
                process_hints=hints,
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [
            _make_event("assess_vitals", 0.0),
            _make_event("order_lab_lactate", 5.0),
        ]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "bpmn:activityType") == "userTask"
        assert _get_attr(event_elems[1], "bpmn:activityType") == "serviceTask"

    def test_clinical_defaults_preset(self):
        """Test clinical_defaults() preset configuration."""
        hints = ProcessMiningHints.clinical_defaults()
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_process_hints=True,
                process_hints=hints,
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [
            _make_event("assess_nihss", 0.0),
            _make_event("give_aspirin", 5.0),
            _make_event("consult_cardiology", 10.0),
        ]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "bpmn:activityType") == "userTask"
        assert _get_attr(event_elems[1], "bpmn:activityType") == "manualTask"
        assert _get_attr(event_elems[2], "bpmn:activityType") == "sendTask"

    def test_gateway_hint_added(self):
        """Gateway hint added for decision point activities."""
        hints = ProcessMiningHints(
            activity_type_mappings={"assess_*": "userTask"},
            gateway_patterns=["assess_*"],
        )
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_process_hints=True,
                process_hints=hints,
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_severity", 0.0)]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "bpmn:isGateway") == "true"

    def test_loop_hint_added(self):
        """Loop hint added for loop activities."""
        hints = ProcessMiningHints(
            activity_type_mappings={"reassess_*": "userTask"},
            loop_patterns=["reassess_*"],
        )
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_process_hints=True,
                process_hints=hints,
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [_make_event("reassess_volume_status", 30.0)]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        assert _get_attr(event_elems[0], "bpmn:isLoop") == "true"

    def test_bpmn_extension_declared(self):
        """BPMN extension declared in log when enabled."""
        hints = ProcessMiningHints.clinical_defaults()
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_process_hints=True,
                process_hints=hints,
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        extensions = _get_extensions(root)

        assert "BPMN" in extensions


# ============================================
# Test Class: Variant Classification
# ============================================

class TestVariantClassification:
    """Tests for process variant classification on traces."""

    def test_variant_disabled_by_default(self):
        """Variant attribute not added when disabled."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [_make_event("assess_vitals", 0.0)]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)

        assert _get_attr(trace, "process:variant") is None

    def test_variant_classification_matches(self):
        """Variant classified when pattern matches."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_variant_classification=True,
                variant_patterns={
                    "standard_sepsis": ["assess_vitals", "order_lab_*", "give_*antibiotics*"],
                },
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [
            _make_event("assess_vitals", 0.0),
            _make_event("order_lab_lactate", 5.0),
            _make_event("give_broad_spectrum_antibiotics", 15.0),
        ]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)

        assert _get_attr(trace, "process:variant") == "standard_sepsis"

    def test_variant_other_when_no_match(self):
        """Variant is 'other' when no pattern matches."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_variant_classification=True,
                variant_patterns={
                    "specific_pattern": ["very_specific_action"],
                },
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [
            _make_event("assess_vitals", 0.0),
            _make_event("order_lab_lactate", 5.0),
        ]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)

        assert _get_attr(trace, "process:variant") == "other"

    def test_variant_first_match_wins(self):
        """First matching variant is used."""
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_variant_classification=True,
                variant_patterns={
                    "variant_a": ["assess_vitals"],
                    "variant_b": ["assess_vitals", "order_*"],
                },
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [
            _make_event("assess_vitals", 0.0),
            _make_event("order_lab_lactate", 5.0),
        ]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)

        # First pattern that matches is used
        assert _get_attr(trace, "process:variant") == "variant_a"


# ============================================
# Test Class: Combined New Features
# ============================================

class TestCombinedNewFeatures:
    """Tests for all new features working together."""

    def test_all_new_features_enabled(self):
        """All new perspectives work together."""
        phase_config = ClinicalPhaseConfig.sepsis_phases()
        hints = ProcessMiningHints.clinical_defaults()
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                enable_clinical_phases=True,
                clinical_phase_config=phase_config,
                enable_process_hints=True,
                process_hints=hints,
                enable_variant_classification=True,
                variant_patterns={
                    "early_treatment": ["assess_*", "order_*", "give_*"],
                },
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [
            _make_event("assess_vitals", 0.0),
            _make_event("order_lab_lactate", 5.0),
            _make_event("give_broad_spectrum_antibiotics", 15.0),
        ]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        # Trace-level variant
        assert _get_attr(trace, "process:variant") == "early_treatment"

        # Event-level clinical phase
        assert _get_attr(event_elems[0], "clinical:phase") is not None

        # Event-level BPMN hints
        assert _get_attr(event_elems[0], "bpmn:activityType") == "userTask"
        assert _get_attr(event_elems[1], "bpmn:activityType") == "serviceTask"
        assert _get_attr(event_elems[2], "bpmn:activityType") == "manualTask"

    def test_new_features_with_existing_perspectives(self):
        """New features work alongside existing perspectives."""
        phase_config = ClinicalPhaseConfig.sepsis_phases()
        hints = ProcessMiningHints.clinical_defaults()
        config = XESExportConfig(
            perspective_config=XESPerspectiveConfig(
                # Existing perspectives
                enable_performance_metrics=True,
                include_confidence=True,
                # New perspectives
                enable_clinical_phases=True,
                clinical_phase_config=phase_config,
                enable_process_hints=True,
                process_hints=hints,
            ),
            pretty_print=False,
        )
        exporter = XESExporter(config)
        events = [
            _make_event("assess_vitals", 0.0, confidence=0.95),
            _make_event("order_lab_lactate", 5.0, confidence=0.85),
        ]

        xml = exporter.export_episode("ep_001", events)
        root = _parse_xes(xml)
        trace = _get_trace(root)
        event_elems = _get_events(trace)

        # Existing perspective attributes
        assert _get_attr(event_elems[0], "quality:confidence", "float") is not None

        # New perspective attributes
        assert _get_attr(event_elems[0], "clinical:phase") is not None
        assert _get_attr(event_elems[0], "bpmn:activityType") is not None
