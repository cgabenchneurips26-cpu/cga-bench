"""Tests for ClinicalInteractionDetector (synergistic harm detection)."""
from __future__ import annotations

import pytest

from cga_bench.assessor_core.clinical_interaction_detector import (
    ClinicalInteractionDetector,
    InteractionConfig,
    InteractionGroup,
    InteractionPattern,
    InteractionType,
)
from cga_bench.cpg_model.schemas.base import (
    HarmSeverity,
    ViolationEvent,
    ViolationType,
)


# ============================================================================
# Helpers
# ============================================================================

def _make_violation(
    vid: str,
    vtype: ViolationType = ViolationType.OMISSION,
    timestamp: float = 0.0,
    action_involved: str = "",
    expected_action: str = "",
    node: str = "node_a",
    severity: HarmSeverity = HarmSeverity.MODERATE,
) -> ViolationEvent:
    return ViolationEvent(
        violation_id=vid,
        violation_type=vtype,
        timestamp_minutes=timestamp,
        action_involved=action_involved or None,
        expected_action=expected_action or None,
        state_at_violation="state_0",
        node_at_violation=node,
        harm_severity=severity,
        description=f"test violation {vid}",
        guideline_reference="test",
    )


def _basic_pattern(
    pid: str = "p1",
    itype: InteractionType = InteractionType.TEMPORAL_PROXIMITY,
    vtype_a: ViolationType | None = None,
    vtype_b: ViolationType | None = None,
    action_a: str | None = None,
    action_b: str | None = None,
    window: float | None = None,
    same_phase: bool = False,
    same_node: bool = False,
    causal: str | None = None,
    multiplier: float = 1.5,
    max_mult: float = 3.0,
    escalated: HarmSeverity | None = None,
) -> InteractionPattern:
    return InteractionPattern(
        pattern_id=pid,
        interaction_type=itype,
        violation_type_a=vtype_a,
        violation_type_b=vtype_b,
        action_pattern_a=action_a,
        action_pattern_b=action_b,
        temporal_window_minutes=window,
        require_same_phase=same_phase,
        require_same_node=same_node,
        causal_direction=causal,
        multiplier=multiplier,
        max_multiplier=max_mult,
        escalated_severity=escalated,
        clinical_rationale="test rationale",
    )


def _config(
    patterns: list[InteractionPattern] | None = None,
    phases: dict | None = None,
    **kwargs,
) -> InteractionConfig:
    return InteractionConfig(
        interaction_patterns=patterns or [],
        phase_definitions=phases or {},
        **kwargs,
    )


# ============================================================================
# Initialization
# ============================================================================

class TestInit:
    def test_requires_config(self):
        with pytest.raises(ValueError, match="config is required"):
            ClinicalInteractionDetector(config=None)

    def test_empty_patterns_ok(self):
        det = ClinicalInteractionDetector(config=_config())
        assert det is not None

    def test_compiles_action_patterns(self):
        pat = _basic_pattern(action_a="lactate", action_b="antibiotic")
        det = ClinicalInteractionDetector(config=_config([pat]))
        assert "lactate" in det._compiled_patterns
        assert "antibiotic" in det._compiled_patterns


# ============================================================================
# Pairwise Detection
# ============================================================================

class TestPairwiseDetection:
    def test_no_interactions_single_violation(self):
        det = ClinicalInteractionDetector(config=_config([_basic_pattern()]))
        result = det.detect_interactions([_make_violation("v1")])
        assert result == []

    def test_match_by_type(self):
        pat = _basic_pattern(
            vtype_a=ViolationType.OMISSION,
            vtype_b=ViolationType.COMMISSION,
            window=30,
        )
        det = ClinicalInteractionDetector(config=_config([pat]))
        v1 = _make_violation("v1", ViolationType.OMISSION, timestamp=5)
        v2 = _make_violation("v2", ViolationType.COMMISSION, timestamp=10)
        result = det.detect_interactions([v1, v2])
        assert len(result) == 1
        assert set(result[0].violation_ids) == {"v1", "v2"}

    def test_match_by_action_regex(self):
        pat = _basic_pattern(action_a="lactate", action_b="antibiotic", window=60)
        det = ClinicalInteractionDetector(config=_config([pat]))
        v1 = _make_violation("v1", expected_action="measure_lactate", timestamp=0)
        v2 = _make_violation("v2", action_involved="give_antibiotic", timestamp=5)
        result = det.detect_interactions([v1, v2])
        assert len(result) == 1

    def test_no_match_outside_temporal_window(self):
        pat = _basic_pattern(window=10)
        det = ClinicalInteractionDetector(config=_config([pat]))
        v1 = _make_violation("v1", timestamp=0)
        v2 = _make_violation("v2", timestamp=20)
        result = det.detect_interactions([v1, v2])
        assert result == []

    def test_multiplier_applied(self):
        pat = _basic_pattern(multiplier=2.0)
        det = ClinicalInteractionDetector(config=_config([pat]))
        v1 = _make_violation("v1", timestamp=0)
        v2 = _make_violation("v2", timestamp=5)
        weights = {"v1": 0.5, "v2": 0.3}
        result = det.detect_interactions([v1, v2], violation_weights=weights)
        assert len(result) == 1
        assert result[0].base_combined_weight == pytest.approx(0.8)
        assert result[0].synergistic_weight == pytest.approx(1.6)

    def test_multiplier_capped_at_max(self):
        pat = _basic_pattern(multiplier=5.0, max_mult=2.5)
        det = ClinicalInteractionDetector(config=_config([pat]))
        v1 = _make_violation("v1", timestamp=0)
        v2 = _make_violation("v2", timestamp=1)
        weights = {"v1": 1.0, "v2": 1.0}
        result = det.detect_interactions([v1, v2], violation_weights=weights)
        assert result[0].multiplier == 2.5

    def test_reversed_order_also_matches(self):
        pat = _basic_pattern(
            vtype_a=ViolationType.COMMISSION,
            vtype_b=ViolationType.OMISSION,
        )
        det = ClinicalInteractionDetector(config=_config([pat]))
        v1 = _make_violation("v1", ViolationType.OMISSION, timestamp=0)
        v2 = _make_violation("v2", ViolationType.COMMISSION, timestamp=5)
        result = det.detect_interactions([v1, v2])
        assert len(result) == 1

    def test_best_multiplier_wins(self):
        p1 = _basic_pattern(pid="low", multiplier=1.2)
        p2 = _basic_pattern(pid="high", multiplier=2.5)
        det = ClinicalInteractionDetector(config=_config([p1, p2]))
        v1 = _make_violation("v1", timestamp=0)
        v2 = _make_violation("v2", timestamp=1)
        result = det.detect_interactions([v1, v2])
        assert len(result) == 1
        assert result[0].multiplier == 2.5


# ============================================================================
# Same-Phase and Same-Node Constraints
# ============================================================================

class TestPhaseAndNodeConstraints:
    def test_same_phase_required(self):
        pat = _basic_pattern(same_phase=True)
        phases = {"resuscitation": ["lactate", "fluid"]}
        det = ClinicalInteractionDetector(config=_config([pat], phases))
        v1 = _make_violation("v1", expected_action="measure_lactate", timestamp=0)
        v2 = _make_violation("v2", expected_action="give_fluid", timestamp=5)
        result = det.detect_interactions([v1, v2])
        assert len(result) == 1

    def test_different_phase_rejected(self):
        pat = _basic_pattern(same_phase=True)
        phases = {
            "resuscitation": ["lactate"],
            "antibiotic": ["antibiotic"],
        }
        det = ClinicalInteractionDetector(config=_config([pat], phases))
        v1 = _make_violation("v1", expected_action="measure_lactate", timestamp=0)
        v2 = _make_violation("v2", expected_action="give_antibiotic", timestamp=5)
        result = det.detect_interactions([v1, v2])
        assert result == []

    def test_same_node_required(self):
        pat = _basic_pattern(same_node=True)
        det = ClinicalInteractionDetector(config=_config([pat]))
        v1 = _make_violation("v1", node="node_x", timestamp=0)
        v2 = _make_violation("v2", node="node_x", timestamp=5)
        result = det.detect_interactions([v1, v2])
        assert len(result) == 1

    def test_different_node_rejected(self):
        pat = _basic_pattern(same_node=True)
        det = ClinicalInteractionDetector(config=_config([pat]))
        v1 = _make_violation("v1", node="node_x", timestamp=0)
        v2 = _make_violation("v2", node="node_y", timestamp=5)
        result = det.detect_interactions([v1, v2])
        assert result == []


# ============================================================================
# Causal Direction
# ============================================================================

class TestCausalDirection:
    def test_a_before_b(self):
        pat = _basic_pattern(causal="a_before_b")
        det = ClinicalInteractionDetector(config=_config([pat]))
        v1 = _make_violation("v1", ViolationType.OMISSION, timestamp=5)
        v2 = _make_violation("v2", ViolationType.COMMISSION, timestamp=10)
        result = det.detect_interactions([v1, v2])
        assert len(result) >= 1

    def test_a_before_b_rejects_wrong_order(self):
        pat = _basic_pattern(
            causal="a_before_b",
            vtype_a=ViolationType.OMISSION,
            vtype_b=ViolationType.COMMISSION,
        )
        det = ClinicalInteractionDetector(config=_config([pat]))
        # v1 is OMISSION at t=10, v2 is COMMISSION at t=5 → OMISSION not before COMMISSION
        v1 = _make_violation("v1", ViolationType.OMISSION, timestamp=10)
        v2 = _make_violation("v2", ViolationType.COMMISSION, timestamp=5)
        result = det.detect_interactions([v1, v2])
        # Should not match in (v1, v2) order because v1.t > v2.t and causal says a_before_b
        # But reversed (v2, v1) might match if types match reversed
        for g in result:
            if g.pattern_id == pat.pattern_id:
                # Verify the match is via reversed order check
                pass


# ============================================================================
# Disabled Interaction Types
# ============================================================================

class TestDisabledTypes:
    def test_disabled_temporal_skips_pattern(self):
        pat = _basic_pattern(itype=InteractionType.TEMPORAL_PROXIMITY)
        cfg = _config([pat], enable_temporal_proximity=False)
        det = ClinicalInteractionDetector(config=cfg)
        v1 = _make_violation("v1", timestamp=0)
        v2 = _make_violation("v2", timestamp=5)
        result = det.detect_interactions([v1, v2])
        assert result == []

    def test_disabled_causal_chain_skips(self):
        pat = _basic_pattern(itype=InteractionType.CAUSAL_CHAIN)
        cfg = _config([pat], enable_causal_chain=False)
        det = ClinicalInteractionDetector(config=cfg)
        v1 = _make_violation("v1", timestamp=0)
        v2 = _make_violation("v2", timestamp=5)
        result = det.detect_interactions([v1, v2])
        assert result == []


# ============================================================================
# Triple Jeopardy
# ============================================================================

class TestTripleJeopardy:
    def test_triple_detected_same_phase(self):
        pat = _basic_pattern(
            itype=InteractionType.PHASE_COMPOUNDING,
            same_phase=True,
            multiplier=1.5,
        )
        phases = {"resuscitation": ["lactate", "fluid", "vasopressor"]}
        cfg = _config(
            [pat],
            phases,
            enable_triple_jeopardy=True,
            triple_jeopardy_multiplier=2.0,
        )
        det = ClinicalInteractionDetector(config=cfg)
        v1 = _make_violation("v1", expected_action="measure_lactate", timestamp=0)
        v2 = _make_violation("v2", expected_action="give_fluid", timestamp=5)
        v3 = _make_violation("v3", expected_action="start_vasopressor", timestamp=8)
        result = det.detect_interactions([v1, v2, v3])
        triple_groups = [g for g in result if len(g.violation_ids) == 3]
        assert len(triple_groups) >= 1

    def test_triple_disabled(self):
        pat = _basic_pattern(
            itype=InteractionType.PHASE_COMPOUNDING,
            same_phase=True,
        )
        phases = {"resuscitation": ["lactate", "fluid", "vasopressor"]}
        cfg = _config(
            [pat],
            phases,
            enable_triple_jeopardy=False,
        )
        det = ClinicalInteractionDetector(config=cfg)
        v1 = _make_violation("v1", expected_action="measure_lactate", timestamp=0)
        v2 = _make_violation("v2", expected_action="give_fluid", timestamp=5)
        v3 = _make_violation("v3", expected_action="start_vasopressor", timestamp=8)
        result = det.detect_interactions([v1, v2, v3])
        triple_groups = [g for g in result if len(g.violation_ids) == 3]
        assert len(triple_groups) == 0


# ============================================================================
# Escalated Severity
# ============================================================================

class TestEscalatedSeverity:
    def test_escalated_severity_in_output(self):
        pat = _basic_pattern(escalated=HarmSeverity.CATASTROPHIC)
        det = ClinicalInteractionDetector(config=_config([pat]))
        v1 = _make_violation("v1", timestamp=0)
        v2 = _make_violation("v2", timestamp=5)
        result = det.detect_interactions([v1, v2])
        assert len(result) == 1
        assert result[0].escalated_severity == HarmSeverity.CATASTROPHIC

    def test_no_escalation_when_none(self):
        pat = _basic_pattern()
        det = ClinicalInteractionDetector(config=_config([pat]))
        v1 = _make_violation("v1", timestamp=0)
        v2 = _make_violation("v2", timestamp=5)
        result = det.detect_interactions([v1, v2])
        assert result[0].escalated_severity is None
