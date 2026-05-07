"""SCN-012 CDE-rescoring tests (B-cde-rescoring v1.1).

Verifies that:
  1. Without CDE coupling, an SCN-012-like episode (massive PE with relative
     contraindication overlap, agent skips thrombolysis) escapes detection
     entirely (legacy score >= test threshold).
  2. With CDE coupling, the violation extractor surfaces:
       - OMISSION on the REQUIRED thrombolytic action (unmet)
       - CONFLICT on the same action (req∩forb under co-satisfiable conditions)
  3. Dedup: when runtime engine ALREADY catches a violation for a given action,
     the CDE pass does not double-count it.
  4. Per-episode additivity: CDE-coupled violation count >= legacy count.
"""

from __future__ import annotations

import copy

import pytest

from cga_bench.assessor_core.violations import (
    HarmSeverityMapping,
    TimingSeverityThreshold,
    ViolationExtractor,
    ViolationExtractorConfig,
)
from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_model.constraint_derivation import ConstraintDerivationEngine
from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    EpisodeLog,
    HarmSeverity,
    PatientState,
    ViolationType,
    VitalSigns,
)


def _scn012_graph() -> dict:
    return {
        "graph_id": "test_pe",
        "guideline_name": "ESC PE 2019 (test)",
        "version": "1.0",
        "entry_node": "init",
        "nodes": {
            "init": {
                "node_id": "init",
                "node_type": "decision",
                "name": "PE assessment",
                "description": "PE workup",
                "allowed_actions": ["order_imaging_ctpa", "give_alteplase_pe", "anticoagulation"],
                "mandatory_actions": [],
                "forbidden_actions": [],
                "deadlines": {},
                "conditional_rules": [
                    {
                        "rule_id": "PE-MASSIVE-THROMBOLYSIS",
                        "condition": "patient.vitals.sbp < 90",
                        "effect": {"type": "REQUIRED", "actions": ["give_alteplase_pe"]},
                        "evidence": "ESC 2019 Class I",
                        "severity": "CRITICAL",
                        "description": "Massive PE thrombolysis required",
                    },
                    {
                        "rule_id": "PE-RECENT-SURGERY-NO-THROMBOLYSIS",
                        "condition": "'recent_surgery' in patient.comorbidities",
                        "effect": {"type": "FORBIDDEN", "actions": ["give_alteplase_pe"]},
                        "evidence": "ESC 2019 absolute contraindication",
                        "severity": "CRITICAL",
                        "description": "Recent surgery is absolute contraindication",
                    },
                ],
            }
        },
    }


def _patient_dict() -> dict:
    return {
        "vitals": {"sbp": 80, "map_mmhg": 55},
        "comorbidities": ["recent_surgery"],
        "allergies": [],
    }


def _vitals() -> VitalSigns:
    return VitalSigns(
        heart_rate=130,
        blood_pressure_systolic=80,
        blood_pressure_diastolic=40,
        respiratory_rate=28,
        temperature=37.5,
        oxygen_saturation=88,
        map_mmhg=55,
    )


def _state(t: float, sid: str) -> PatientState:
    return PatientState(
        state_id=sid,
        time_since_arrival_minutes=t,
        age=70,
        sex="F",
        weight_kg=65,
        vitals=_vitals(),
        chief_complaint="dyspnea, hypotension",
        working_diagnosis="pulmonary_embolism",
        comorbidities=["recent_surgery"],
    )


def _action(aid: str, t: float) -> Action:
    return Action(type=ActionType.PROCEDURE, action_id=aid, args={}, timestamp_minutes=t)


def _episode_skipping_thrombolysis() -> EpisodeLog:
    """Agent does CTPA + anticoagulation but skips thrombolysis (SCN-012 case)."""
    actions = [
        _action("order_imaging_ctpa", 10),
        _action("anticoagulation", 30),
    ]
    states = [_state(0, "s0")]
    for i, a in enumerate(actions, 1):
        states.append(_state(a.timestamp_minutes, f"s{i}"))
    return EpisodeLog(
        episode_id="scn012",
        scenario_id="pulmonary_embolism",
        agent_id="test_agent",
        states=states,
        actions=actions,
        observations=[{}],
        total_duration_minutes=60,
        total_llm_calls=0,
        total_tokens=0,
        total_tool_calls=0,
        termination_reason="timeout",
    )


def _engine_for_graph(graph_dict: dict, entry: str = "init"):
    """Build a CPGEngine for a synthesised graph dict (test fixture).

    Deepcopies the input because load_from_dict mutates `data['nodes']` to
    convert dict entries into CPGNode instances.
    """
    eng = CPGEngineFactory.load_from_dict(copy.deepcopy(graph_dict))
    eng.current_node_id = entry
    return eng


def _engine():
    return _engine_for_graph(_scn012_graph(), entry="init")


def _violation_extractor_config() -> ViolationExtractorConfig:
    return ViolationExtractorConfig(
        harm_severity_mappings=[
            HarmSeverityMapping(action_pattern="alteplase", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="thrombolytic", severity=HarmSeverity.SEVERE),
            HarmSeverityMapping(action_pattern="", severity=HarmSeverity.MODERATE),
        ],
        timing_severity_thresholds=[
            TimingSeverityThreshold(max_delay_minutes=15, severity=HarmSeverity.MODERATE),
            TimingSeverityThreshold(max_delay_minutes=30, severity=HarmSeverity.MAJOR),
            TimingSeverityThreshold(max_delay_minutes=60, severity=HarmSeverity.SEVERE),
        ],
        default_deviation_severity=HarmSeverity.MINOR,
        default_deviation_preventability=0.5,
    )


@pytest.fixture
def config() -> ViolationExtractorConfig:
    return _violation_extractor_config()


def test_scn012_legacy_misses_thrombolysis_omission(config: ViolationExtractorConfig) -> None:
    """Legacy mode: runtime engine never reads conditional_rules, so the
    REQUIRED thrombolysis action is invisible -> no OMISSION for it."""
    episode = _episode_skipping_thrombolysis()
    extractor = ViolationExtractor(_engine(), config)
    legacy = extractor.extract_violations(episode)

    legacy_omission_targets = {
        v.expected_action for v in legacy if v.violation_type == ViolationType.OMISSION
    }
    assert "give_alteplase_pe" not in legacy_omission_targets, (
        f"Legacy mode unexpectedly already catches thrombolysis omission: {legacy_omission_targets}"
    )


def test_scn012_cde_surfaces_omission_and_conflict(config: ViolationExtractorConfig) -> None:
    """CDE-coupled mode: same episode -> at least one OMISSION on
    give_alteplase_pe AND one CONFLICT on the same action."""
    episode = _episode_skipping_thrombolysis()
    cde = ConstraintDerivationEngine()
    derived = cde.derive(_scn012_graph(), _patient_dict(), scenario_id="scn012")

    extractor = ViolationExtractor(_engine(), config)
    cde_coupled = extractor.extract_violations(episode, derived_constraints=derived)

    omissions = [
        v for v in cde_coupled
        if v.violation_type == ViolationType.OMISSION and v.expected_action == "give_alteplase_pe"
    ]
    conflicts = [
        v for v in cde_coupled
        if v.violation_type == ViolationType.CONFLICT and v.action_involved == "give_alteplase_pe"
    ]

    assert len(omissions) >= 1, f"Expected ≥1 thrombolysis OMISSION, got: {cde_coupled}"
    assert len(conflicts) == 1, f"Expected exactly 1 CONFLICT, got: {conflicts}"

    conflict = conflicts[0]
    assert conflict.source == "cde"
    assert conflict.conflict_provenance is not None
    assert any("PE-MASSIVE-THROMBOLYSIS" in p for p in conflict.conflict_provenance)
    assert any("PE-RECENT-SURGERY-NO-THROMBOLYSIS" in p for p in conflict.conflict_provenance)


def test_cde_additivity_per_episode(config: ViolationExtractorConfig) -> None:
    """Per-episode additivity: CDE-coupled count >= legacy count
    (CDE never *removes* violations, only adds)."""
    episode = _episode_skipping_thrombolysis()
    cde = ConstraintDerivationEngine()
    derived = cde.derive(_scn012_graph(), _patient_dict(), scenario_id="scn012")

    legacy = ViolationExtractor(_engine(), config).extract_violations(episode)
    cde_coupled = ViolationExtractor(_engine(), config).extract_violations(
        episode, derived_constraints=derived
    )

    assert len(cde_coupled) >= len(legacy)


def test_cde_dedup_when_runtime_already_caught(config: ViolationExtractorConfig) -> None:
    """When the runtime engine already emits an OMISSION for an action and the
    CDE REQUIRED set names the same action, the CDE pass must not double-count."""
    # Construct a graph where static mandatory + conditional REQUIRED both name
    # the same action. Runtime engine -> OMISSION (from static mandatory).
    # CDE -> REQUIRED. Combined -> still 1 OMISSION (deduped).
    graph = {
        "graph_id": "test_dedup",
        "guideline_name": "dedup",
        "version": "1.0",
        "entry_node": "init",
        "nodes": {
            "init": {
                "node_id": "init",
                "node_type": "decision",
                "name": "init",
                "description": "",
                "allowed_actions": ["give_x"],
                "mandatory_actions": ["give_x"],
                "forbidden_actions": [],
                "deadlines": {},
                "conditional_rules": [
                    {
                        "rule_id": "DUP",
                        "condition": "patient.age > 18",
                        "effect": {"type": "REQUIRED", "actions": ["give_x"]},
                        "evidence": "test evidence",
                        "severity": "HIGH",
                        "description": "Required for adults",
                    },
                ],
            }
        },
    }
    engine = _engine_for_graph(graph, entry="init")

    # Empty episode (action not performed) — runtime emits OMISSION on give_x
    episode = EpisodeLog(
        episode_id="dedup",
        scenario_id="test",
        agent_id="test",
        states=[_state(0, "s0")],
        actions=[],
        observations=[{}],
        total_duration_minutes=10,
        total_llm_calls=0,
        total_tokens=0,
        total_tool_calls=0,
        termination_reason="timeout",
    )
    cde = ConstraintDerivationEngine()
    derived = cde.derive(graph, {"age": 55, "comorbidities": [], "allergies": []})

    cde_coupled = ViolationExtractor(engine, config).extract_violations(
        episode, derived_constraints=derived
    )
    omissions_for_x = [
        v for v in cde_coupled
        if v.violation_type == ViolationType.OMISSION and v.expected_action == "give_x"
    ]
    # Exactly one OMISSION for 'give_x' (deduped, not 2)
    assert len(omissions_for_x) == 1, f"Dedup failed, got {len(omissions_for_x)}: {omissions_for_x}"
