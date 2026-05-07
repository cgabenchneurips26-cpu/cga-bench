"""Tests for R1-R5 scoring pipeline fixes.

R1: Strict action matching (no substring)
R2: Scenario expected_actions as omission source
R3: Deadline gate removal
R4: Consumed set prevents 1:N matching
R5: Both-side normalization
"""

from pathlib import Path

from cga_bench.assessor_core.action_normalizer import ActionNormalizer
from cga_bench.assessor_core.violations import (
    HarmSeverityMapping,
    TimingSeverityThreshold,
    ViolationExtractor,
    ViolationExtractorConfig,
)
from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    EpisodeLog,
    HarmSeverity,
    PatientState,
    ViolationType,
    VitalSigns,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _graph_path(name: str) -> str:
    return str(Path(__file__).parent.parent.parent / "cpg_model" / "graphs" / name)


def _make_state(
    time_min: float = 0.0,
    state_id: str = "s0",
    diagnosis: str = "septic_shock",
    map_mmhg: float = 62.0,
) -> PatientState:
    return PatientState(
        state_id=state_id,
        time_since_arrival_minutes=time_min,
        age=65,
        sex="M",
        weight_kg=70,
        vitals=VitalSigns(
            heart_rate=120,
            blood_pressure_systolic=85,
            blood_pressure_diastolic=50,
            respiratory_rate=24,
            temperature=38.9,
            oxygen_saturation=92,
            map_mmhg=map_mmhg,
        ),
        chief_complaint="fever",
        working_diagnosis=diagnosis,
    )


def _action(action_id: str, t: float = 5.0) -> Action:
    return Action(
        type=ActionType.PROCEDURE,
        action_id=action_id,
        args={},
        timestamp_minutes=t,
    )


def _episode(actions: list[Action], duration: float = 60.0) -> EpisodeLog:
    states = [_make_state(a.timestamp_minutes, f"s{i}") for i, a in enumerate(actions)]
    if not states:
        states = [_make_state()]
    return EpisodeLog(
        episode_id="test_ep_001",
        scenario_id="test",
        agent_id="test_agent",
        actions=actions,
        states=states,
        observations=[],
        total_duration_minutes=duration,
        total_llm_calls=0,
        total_tokens=0,
        total_tool_calls=0,
        termination_reason="max_time",
    )


def _ve_config() -> ViolationExtractorConfig:
    return ViolationExtractorConfig(
        harm_severity_mappings=[
            HarmSeverityMapping(action_pattern="", severity=HarmSeverity.MODERATE),
        ],
        timing_severity_thresholds=[
            TimingSeverityThreshold(max_delay_minutes=15, severity=HarmSeverity.MINOR),
            TimingSeverityThreshold(max_delay_minutes=30, severity=HarmSeverity.MODERATE),
            TimingSeverityThreshold(max_delay_minutes=60, severity=HarmSeverity.MAJOR),
        ],
        default_deviation_severity=HarmSeverity.MINOR,
        default_deviation_preventability=0.5,
    )


def _make_ve(graph_name: str = "ssc_sepsis_hour1_bundle.yaml") -> ViolationExtractor:
    engine = CPGEngineFactory.load_from_file(_graph_path(graph_name))
    return ViolationExtractor(engine, _ve_config())


# ---------------------------------------------------------------------------
# R1: No substring matching
# ---------------------------------------------------------------------------


class TestR1NoSubstringMatching:
    """R1: _action_satisfies_requirement uses strict matching, not substring."""

    def test_no_substring_matching(self) -> None:
        """order_ecg must NOT satisfy order_ecg_continuous_monitoring."""
        ve = _make_ve()
        state = _make_state()
        result = ve._action_satisfies_requirement("order_ecg", "order_ecg_continuous_monitoring", state)
        assert result is False, "Substring matching should be disabled"

    def test_no_reverse_action_matching(self) -> None:
        """hold_insulin_until_k_above_3.3 must NOT match start_insulin_infusion."""
        ve = _make_ve()
        state = _make_state()
        result = ve._action_satisfies_requirement("hold_insulin_until_k_above_3.3", "start_insulin_infusion", state)
        assert result is False, "Opposite actions must not match"

    def test_exact_match_still_works(self) -> None:
        """Exact match should still succeed."""
        ve = _make_ve()
        state = _make_state()
        result = ve._action_satisfies_requirement("order_lab_lactate", "order_lab_lactate", state)
        assert result is True


# ---------------------------------------------------------------------------
# R4: Consumed set prevents double matching
# ---------------------------------------------------------------------------


class TestR4ConsumedSet:
    """R4: One performed action can satisfy at most one mandatory requirement."""

    def test_consumed_set_prevents_double_matching(self) -> None:
        """1 performed 'continuous_monitoring' cannot satisfy 3 different mandatories."""
        episode = _episode([_action("continuous_monitoring", 5.0)])
        ve = _make_ve("aha_heart_failure_2022.yaml")

        # Use scenario_expected_actions with 3 different requirements
        expected = [
            "continuous_monitoring",
            "monitor_electrolytes",
            "monitor_urine_output",
        ]

        violations = ve.extract_violations(
            episode,
            scenario_expected_actions=expected,
        )

        omissions = [v for v in violations if v.violation_type == ViolationType.OMISSION]
        # continuous_monitoring matches itself (1 match), but the other 2 are omissions
        assert len(omissions) >= 2, (
            f"Expected >= 2 omissions, got {len(omissions)}: {[v.expected_action for v in omissions]}"
        )


# ---------------------------------------------------------------------------
# R2: Scenario expected_actions as omission source
# ---------------------------------------------------------------------------


class TestR2ScenarioExpected:
    """R2: Omissions come from scenario expected_actions, not just CPG node."""

    def test_scenario_expected_as_omission_source(self) -> None:
        """ADHF scenario with 6 expected actions: unperformed ones generate omissions."""
        expected = [
            "iv_diuretics",
            "fluid_restrict",
            "daily_weights",
            "monitor_urine_output",
            "monitor_electrolytes",
            "continuous_monitoring",
        ]
        # Agent performs only iv_diuretics
        episode = _episode([_action("iv_diuretics", 5.0)])
        ve = _make_ve("aha_heart_failure_2022.yaml")

        violations = ve.extract_violations(
            episode,
            scenario_expected_actions=expected,
        )

        omissions = [v for v in violations if v.violation_type == ViolationType.OMISSION]
        omission_actions = {v.expected_action for v in omissions}

        # At least 4 of the 5 unperformed expected actions should be omissions
        assert len(omissions) >= 4, (
            f"Expected >= 4 omissions from scenario expected_actions, got {len(omissions)}: {omission_actions}"
        )


# ---------------------------------------------------------------------------
# R3: Deadline gate removal
# ---------------------------------------------------------------------------


class TestR3DeadlineGateRemoval:
    """R3: Missing mandatory generates OMISSION even without deadline."""

    def test_deadline_inf_still_creates_omission(self) -> None:
        """An expected action with no deadline should still create an omission if not performed."""
        expected = ["assess_vital_signs", "order_lab_bmp"]
        # Agent performs nothing
        episode = _episode([])
        ve = _make_ve("ada_dka_management.yaml")

        violations = ve.extract_violations(
            episode,
            scenario_expected_actions=expected,
        )

        omissions = [v for v in violations if v.violation_type == ViolationType.OMISSION]
        assert len(omissions) >= 2, f"Expected >= 2 omissions for unperformed expected actions, got {len(omissions)}"


# ---------------------------------------------------------------------------
# R1-R5 E2E: DKA manual alignment
# ---------------------------------------------------------------------------


class TestDkaE2EManualAlignment:
    """Integration test: DKA hypokalemia_trap scoring aligns with manual review."""

    def test_dka_e2e_manual_alignment(self) -> None:
        """Agent performing 5/10 expected DKA actions => C2 ~ 0.5."""
        normalizer = ActionNormalizer()
        cpg_id = "ada_dka_management"

        expected = [
            "assess_vital_signs",
            "establish_iv_access",
            "order_lab_bmp",
            "order_lab_abg",
            "start_iv_fluid_ns",
            "order_ecg",
            "give_potassium_iv",
            "hold_insulin_until_k_above_3.3",
            "recheck_potassium_in_1h",
            "continuous_cardiac_monitoring",
        ]

        # Simulate agent that performs 5 of the 10 (matching the oss120b r0 pattern)
        performed = [
            "assess_vital_signs",  # matches assess_vital_signs
            "order_lab_bmp",  # matches order_lab_bmp
            "order_lab_blood_gas",  # matches order_lab_abg (via normalization)
            "give_iv_fluid_bolus",  # matches start_iv_fluid_ns (via normalization)
            "give_potassium_replacement",  # matches give_potassium_iv (via normalization)
        ]

        # Count matches using normalizer
        performed_norm = {normalizer.normalize(a, cpg_id) for a in performed}
        expected_norm = [normalizer.normalize(e, cpg_id) for e in expected]

        matched = 0
        consumed = set()
        for en in expected_norm:
            if en in performed_norm and en not in consumed:
                matched += 1
                consumed.add(en)

        c2 = 1.0 - (len(expected) - matched) / max(len(expected), 1)
        assert matched == 5, f"Expected 5 matches, got {matched}"
        assert abs(c2 - 0.5) < 0.01, f"Expected C2 ~ 0.5, got {c2}"
