from __future__ import annotations

import pytest

from cga_bench.assessor_core.dka_violation_detector import (
    DKATrapViolation,
    DKAViolationDetector,
    DKAViolationDetectorConfig,
    create_dka_violation_detector,
)
from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    EpisodeLog,
    HarmSeverity,
    PatientState,
    VitalSigns,
)


# ---------------------------------------------------------------------------
# Helper factories
# ---------------------------------------------------------------------------

def _make_action(action_id: str, timestamp: float = 5.0) -> Action:
    return Action(
        type=ActionType.GIVE_MEDICATION,
        action_id=action_id,
        args={},
        timestamp_minutes=timestamp,
    )


def _make_state(comorbidities: list[str] | None = None) -> PatientState:
    return PatientState(
        state_id="s0",
        age=55,
        sex="M",
        vitals=VitalSigns(),
        chief_complaint="dka",
        comorbidities=comorbidities or [],
    )


def _make_episode(
    actions: list[Action] | None = None,
    states: list[PatientState] | None = None,
) -> EpisodeLog:
    return EpisodeLog(
        episode_id="ep_dka_test",
        scenario_id="dka_001",
        agent_id="test_agent",
        states=states or [],
        actions=actions or [],
        observations=[],
        total_duration_minutes=120.0,
        total_llm_calls=3,
        total_tokens=500,
        total_tool_calls=5,
        termination_reason="success",
    )


# ===========================================================================
# Config Tests
# ===========================================================================

class TestDKAViolationDetectorConfig:
    def test_default_thresholds(self):
        cfg = DKAViolationDetectorConfig()
        assert cfg.hypokalemia_threshold == 3.3
        assert cfg.hyperkalemia_threshold == 5.5
        assert cfg.severe_dka_ph_threshold == 7.0
        assert cfg.euglycemic_glucose_threshold == 200
        assert cfg.iv_fluid_deadline == 15
        assert cfg.insulin_deadline == 60

    def test_custom_config_injection(self):
        cfg = DKAViolationDetectorConfig(
            hypokalemia_threshold=3.0,
            hyperkalemia_threshold=6.0,
            severe_dka_ph_threshold=6.9,
            euglycemic_glucose_threshold=180,
        )
        assert cfg.hypokalemia_threshold == 3.0
        assert cfg.hyperkalemia_threshold == 6.0
        assert cfg.severe_dka_ph_threshold == 6.9
        assert cfg.euglycemic_glucose_threshold == 180


# ===========================================================================
# Init Tests
# ===========================================================================

class TestDKAViolationDetectorInit:
    def test_default_config_when_none(self):
        det = DKAViolationDetector(config=None)
        assert isinstance(det.config, DKAViolationDetectorConfig)
        assert det.config.hypokalemia_threshold == 3.3

    def test_custom_config_preserved(self):
        cfg = DKAViolationDetectorConfig(hypokalemia_threshold=2.5)
        det = DKAViolationDetector(config=cfg)
        assert det.config.hypokalemia_threshold == 2.5


# ===========================================================================
# Trap Violation Tests
# ===========================================================================

class TestTrapViolations:
    def test_hypokalemia_trap_insulin_no_potassium(self):
        """K+ < 3.3, insulin given, no potassium replacement → CATASTROPHIC"""
        actions = [_make_action("start_insulin_infusion", 10.0)]
        episode = _make_episode(actions=actions)
        gt = {"lab_potassium": 2.8}

        det = DKAViolationDetector()
        traps = det._detect_trap_violations(episode, gt)

        cat_traps = [t for t in traps if t.severity == HarmSeverity.CATASTROPHIC
                     and t.trap_type == "hypokalemia"]
        assert len(cat_traps) >= 1
        assert "Insulin given with K+" in cat_traps[0].violation_description

    def test_hypokalemia_sequence_insulin_before_potassium(self):
        """K+ < 3.3, insulin given BEFORE potassium → MAJOR"""
        actions = [
            _make_action("start_insulin_infusion", 10.0),
            _make_action("give_potassium_iv", 20.0),
        ]
        episode = _make_episode(actions=actions)
        gt = {"lab_potassium": 3.0}

        det = DKAViolationDetector()
        traps = det._detect_trap_violations(episode, gt)

        major = [t for t in traps if t.severity == HarmSeverity.MAJOR
                 and t.trap_type == "hypokalemia"]
        assert len(major) >= 1
        assert "BEFORE" in major[0].violation_description

    def test_hypokalemia_no_violation_when_potassium_first(self):
        """K+ < 3.3, potassium given BEFORE insulin → no hypokalemia trap"""
        actions = [
            _make_action("give_potassium_iv", 5.0),
            _make_action("start_insulin_infusion", 15.0),
        ]
        episode = _make_episode(actions=actions)
        gt = {"lab_potassium": 3.0}

        det = DKAViolationDetector()
        traps = det._detect_trap_violations(episode, gt)

        hypokalemia = [t for t in traps if t.trap_type == "hypokalemia"]
        assert len(hypokalemia) == 0

    def test_hyperkalemia_trap_potassium_given(self):
        """K+ > 5.5, potassium given → CATASTROPHIC"""
        actions = [_make_action("give_potassium_iv", 10.0)]
        episode = _make_episode(actions=actions)
        gt = {"lab_potassium": 6.0}

        det = DKAViolationDetector()
        traps = det._detect_trap_violations(episode, gt)

        cat = [t for t in traps if t.trap_type == "hyperkalemia"
               and t.severity == HarmSeverity.CATASTROPHIC]
        assert len(cat) == 1
        assert "6.0" in cat[0].violation_description

    def test_ckd_potassium_caution(self):
        """CKD patient, 5.0 < K+ <= 5.5, potassium given → MAJOR"""
        actions = [_make_action("give_potassium_iv", 10.0)]
        states = [_make_state(comorbidities=["CKD stage 3"])]
        episode = _make_episode(actions=actions, states=states)
        gt = {"lab_potassium": 5.2}

        det = DKAViolationDetector()
        traps = det._detect_trap_violations(episode, gt)

        ckd = [t for t in traps if t.trap_type == "ckd_potassium_caution"]
        assert len(ckd) == 1
        assert ckd[0].severity == HarmSeverity.MAJOR

    def test_euglycemic_missed_ketones(self):
        """Glucose < 200, ketones > 3.0, no ketone check → MAJOR"""
        actions = [_make_action("assess_vital_signs", 5.0)]
        episode = _make_episode(actions=actions)
        gt = {"lab_glucose": 150, "lab_ketones": 4.5}

        det = DKAViolationDetector()
        traps = det._detect_trap_violations(episode, gt)

        missed = [t for t in traps if t.trap_type == "euglycemic_dka_missed_ketones"]
        assert len(missed) == 1
        assert missed[0].severity == HarmSeverity.MAJOR

    def test_euglycemic_untreated(self):
        """Glucose < 200, ketones > 3.0, no insulin/dka treatment → CATASTROPHIC"""
        actions = [_make_action("assess_vital_signs", 5.0)]
        episode = _make_episode(actions=actions)
        gt = {"lab_glucose": 180, "lab_ketones": 5.0}

        det = DKAViolationDetector()
        traps = det._detect_trap_violations(episode, gt)

        untreated = [t for t in traps if t.trap_type == "euglycemic_dka_untreated"]
        assert len(untreated) == 1
        assert untreated[0].severity == HarmSeverity.CATASTROPHIC

    def test_severe_dka_wrong_disposition(self):
        """pH < 7.0, ward admission without ICU → CATASTROPHIC"""
        actions = [_make_action("admit_to_ward", 30.0)]
        episode = _make_episode(actions=actions)
        gt = {"lab_ph": 6.8}

        det = DKAViolationDetector()
        traps = det._detect_trap_violations(episode, gt)

        wrong = [t for t in traps if t.trap_type == "severe_dka_wrong_disposition"]
        assert len(wrong) == 1
        assert wrong[0].severity == HarmSeverity.CATASTROPHIC

    def test_no_trap_normal_potassium(self):
        """K+ in normal range (3.3–5.5), insulin given → no trap"""
        actions = [_make_action("start_insulin_infusion", 10.0)]
        episode = _make_episode(actions=actions)
        gt = {"lab_potassium": 4.0}

        det = DKAViolationDetector()
        traps = det._detect_trap_violations(episode, gt)

        assert len(traps) == 0


# ===========================================================================
# Timing Violation Tests
# ===========================================================================

class TestTimingViolations:
    def test_iv_fluid_after_deadline(self):
        """IV fluid started after 15 min deadline → timing violation"""
        actions = [_make_action("start_iv_fluid_ns", 25.0)]
        episode = _make_episode(actions=actions)

        det = DKAViolationDetector()
        timing = det._detect_timing_violations(episode, {})

        assert len(timing) == 1
        assert timing[0]["action"] == "start_iv_fluid_ns"
        assert timing[0]["delay"] == pytest.approx(10.0)

    def test_insulin_after_deadline(self):
        """Insulin infusion started after 60 min, K+ >= 3.3 → timing violation"""
        actions = [_make_action("start_insulin_infusion", 75.0)]
        episode = _make_episode(actions=actions)
        gt = {"lab_potassium": 4.0}

        det = DKAViolationDetector()
        timing = det._detect_timing_violations(episode, gt)

        assert len(timing) == 1
        assert timing[0]["action"] == "start_insulin_infusion"
        assert timing[0]["delay"] == pytest.approx(15.0)

    def test_no_timing_violation_within_deadline(self):
        """Actions within deadlines → no timing violations"""
        actions = [
            _make_action("start_iv_fluid_ns", 10.0),
            _make_action("start_insulin_infusion", 50.0),
        ]
        episode = _make_episode(actions=actions)
        gt = {"lab_potassium": 4.0}

        det = DKAViolationDetector()
        timing = det._detect_timing_violations(episode, gt)

        assert len(timing) == 0

    def test_insulin_timing_skipped_when_hypokalemic(self):
        """K+ < 3.3 → insulin deadline check skipped (even if late)"""
        actions = [_make_action("start_insulin_infusion", 90.0)]
        episode = _make_episode(actions=actions)
        gt = {"lab_potassium": 2.5}

        det = DKAViolationDetector()
        timing = det._detect_timing_violations(episode, gt)

        insulin_timing = [v for v in timing if v["action"] == "start_insulin_infusion"]
        assert len(insulin_timing) == 0


# ===========================================================================
# Sequence Violation Tests
# ===========================================================================

class TestSequenceViolations:
    def test_iv_fluid_without_iv_access(self):
        """IV fluid started without any IV access → minor sequence violation"""
        actions = [_make_action("start_iv_fluid_ns", 10.0)]
        episode = _make_episode(actions=actions)

        det = DKAViolationDetector()
        seq = det._detect_sequence_violations(episode, {})

        fluid_seq = [v for v in seq if v["action"] == "start_iv_fluid_ns"]
        assert len(fluid_seq) == 1
        assert fluid_seq[0]["severity"] == "minor"

    def test_iv_fluid_before_iv_access(self):
        """IV fluid before IV access established → minor"""
        actions = [
            _make_action("start_iv_fluid_ns", 5.0),
            _make_action("establish_iv_access", 10.0),
        ]
        episode = _make_episode(actions=actions)

        det = DKAViolationDetector()
        seq = det._detect_sequence_violations(episode, {})

        fluid_seq = [v for v in seq if v["action"] == "start_iv_fluid_ns"]
        assert len(fluid_seq) == 1
        assert "before IV access" in fluid_seq[0]["description"]

    def test_insulin_without_bmp(self):
        """Insulin started without BMP → major sequence violation"""
        actions = [_make_action("start_insulin_infusion", 15.0)]
        episode = _make_episode(actions=actions)

        det = DKAViolationDetector()
        seq = det._detect_sequence_violations(episode, {})

        insulin_seq = [v for v in seq if v["action"] == "start_insulin_infusion"]
        assert len(insulin_seq) == 1
        assert insulin_seq[0]["severity"] == "major"

    def test_insulin_before_bmp(self):
        """Insulin started before BMP ordered → major"""
        actions = [
            _make_action("start_insulin_infusion", 10.0),
            _make_action("order_lab_bmp", 20.0),
        ]
        episode = _make_episode(actions=actions)

        det = DKAViolationDetector()
        seq = det._detect_sequence_violations(episode, {})

        insulin_seq = [v for v in seq if v["action"] == "start_insulin_infusion"]
        assert len(insulin_seq) == 1
        assert "before BMP" in insulin_seq[0]["description"]

    def test_no_sequence_violation_correct_order(self):
        """Correct order: IV access → IV fluid, BMP → insulin → no violations"""
        actions = [
            _make_action("establish_iv_access", 1.0),
            _make_action("order_lab_bmp", 2.0),
            _make_action("start_iv_fluid_ns", 5.0),
            _make_action("start_insulin_infusion", 15.0),
        ]
        episode = _make_episode(actions=actions)

        det = DKAViolationDetector()
        seq = det._detect_sequence_violations(episode, {})

        assert len(seq) == 0


# ===========================================================================
# Omission Violation Tests
# ===========================================================================

class TestOmissionViolations:
    def test_missing_required_actions(self):
        """Empty episode → should flag missing required actions"""
        episode = _make_episode(actions=[])
        gt = {"lab_potassium": 4.0, "lab_ph": 7.3}

        det = DKAViolationDetector()
        omissions = det._detect_omission_violations(episode, gt)

        missing_ids = [v["missing_action"] for v in omissions]
        assert "assess_vital_signs" in missing_ids
        assert "establish_iv_access" in missing_ids
        assert "order_lab_bmp" in missing_ids
        assert "start_iv_fluid_ns" in missing_ids

    def test_hypokalemia_missing_potassium_replacement(self):
        """K+ < 3.3 without potassium replacement → catastrophic omission"""
        actions = [
            _make_action("assess_vital_signs", 1.0),
            _make_action("establish_iv_access", 2.0),
            _make_action("order_lab_bmp", 3.0),
            _make_action("start_iv_fluid_ns", 5.0),
        ]
        episode = _make_episode(actions=actions)
        gt = {"lab_potassium": 2.5}

        det = DKAViolationDetector()
        omissions = det._detect_omission_violations(episode, gt)

        k_omission = [v for v in omissions if v["missing_action"] == "give_potassium_iv"]
        assert len(k_omission) == 1
        assert k_omission[0]["severity"] == "catastrophic"

    def test_severe_dka_missing_icu(self):
        """pH < 7.0 without ICU admission → catastrophic omission"""
        actions = [
            _make_action("assess_vital_signs", 1.0),
            _make_action("establish_iv_access", 2.0),
            _make_action("order_lab_bmp", 3.0),
            _make_action("start_iv_fluid_ns", 5.0),
        ]
        episode = _make_episode(actions=actions)
        gt = {"lab_ph": 6.9}

        det = DKAViolationDetector()
        omissions = det._detect_omission_violations(episode, gt)

        icu_omission = [v for v in omissions if v["missing_action"] == "admit_to_icu"]
        assert len(icu_omission) == 1
        assert icu_omission[0]["severity"] == "catastrophic"

    def test_no_omission_all_present(self):
        """All required actions present, normal labs → no omissions"""
        actions = [
            _make_action("assess_vital_signs", 1.0),
            _make_action("establish_iv_access", 2.0),
            _make_action("order_lab_bmp", 3.0),
            _make_action("start_iv_fluid_ns", 5.0),
        ]
        episode = _make_episode(actions=actions)
        gt = {"lab_potassium": 4.0, "lab_ph": 7.3}

        det = DKAViolationDetector()
        omissions = det._detect_omission_violations(episode, gt)

        assert len(omissions) == 0


# ===========================================================================
# Risk Score Tests
# ===========================================================================

class TestRiskScore:
    def test_zero_score_no_violations(self):
        score = DKAViolationDetector()._calculate_risk_score([], [], [], [])
        assert score == 0.0

    def test_catastrophic_trap_adds_point_four(self):
        trap = DKATrapViolation(
            trap_type="hypokalemia",
            violation_description="test",
            trigger_action="insulin",
            patient_state_value=2.8,
            threshold=3.3,
            severity=HarmSeverity.CATASTROPHIC,
            clinical_consequence="arrhythmia",
            correct_action="give_potassium_iv",
        )
        score = DKAViolationDetector()._calculate_risk_score([trap], [], [], [])
        assert score == pytest.approx(0.4)

    def test_major_trap_adds_point_two_five(self):
        trap = DKATrapViolation(
            trap_type="hypokalemia",
            violation_description="test",
            trigger_action="insulin",
            patient_state_value=3.0,
            threshold=3.3,
            severity=HarmSeverity.MAJOR,
            clinical_consequence="transient",
            correct_action="give_potassium_iv",
        )
        score = DKAViolationDetector()._calculate_risk_score([trap], [], [], [])
        assert score == pytest.approx(0.25)

    def test_score_capped_at_one(self):
        traps = [
            DKATrapViolation(
                trap_type="t",
                violation_description="d",
                trigger_action="a",
                patient_state_value=0,
                threshold=0,
                severity=HarmSeverity.CATASTROPHIC,
                clinical_consequence="c",
                correct_action="x",
            )
            for _ in range(5)
        ]
        score = DKAViolationDetector()._calculate_risk_score(traps, [], [], [])
        assert score == 1.0

    def test_timing_major_adds_point_fifteen(self):
        timing = [{"severity": "major"}]
        score = DKAViolationDetector()._calculate_risk_score([], timing, [], [])
        assert score == pytest.approx(0.15)

    def test_sequence_major_adds_point_twelve(self):
        seq = [{"severity": "major"}]
        score = DKAViolationDetector()._calculate_risk_score([], [], seq, [])
        assert score == pytest.approx(0.12)

    def test_omission_catastrophic_adds_point_thirty_five(self):
        omission = [{"severity": "catastrophic"}]
        score = DKAViolationDetector()._calculate_risk_score([], [], [], omission)
        assert score == pytest.approx(0.35)


# ===========================================================================
# Summary Tests
# ===========================================================================

class TestSummary:
    def test_no_violations_summary(self):
        summary = DKAViolationDetector()._generate_summary([], [], [], [])
        assert "No violations detected" in summary

    def test_summary_includes_trap_section(self):
        trap = DKATrapViolation(
            trap_type="hypokalemia",
            violation_description="Insulin given with K+ = 2.8",
            trigger_action="insulin",
            patient_state_value=2.8,
            threshold=3.3,
            severity=HarmSeverity.CATASTROPHIC,
            clinical_consequence="arrhythmia",
            correct_action="give_potassium_iv",
        )
        summary = DKAViolationDetector()._generate_summary([trap], [], [], [])
        assert "[CRITICAL]" in summary
        assert "hypokalemia" in summary

    def test_summary_includes_timing_section(self):
        timing = [{"action": "start_iv_fluid_ns", "delay": 10.0}]
        summary = DKAViolationDetector()._generate_summary([], timing, [], [])
        assert "[TIMING]" in summary

    def test_summary_includes_sequence_section(self):
        seq = [{"description": "IV fluid started without IV access"}]
        summary = DKAViolationDetector()._generate_summary([], [], seq, [])
        assert "[SEQUENCE]" in summary

    def test_summary_includes_omission_section(self):
        omission = [{"description": "Missing: Vital signs assessment"}]
        summary = DKAViolationDetector()._generate_summary([], [], [], omission)
        assert "[OMISSION]" in summary


# ===========================================================================
# Factory Function Tests
# ===========================================================================

class TestFactory:
    def test_factory_returns_detector(self):
        det = create_dka_violation_detector()
        assert isinstance(det, DKAViolationDetector)

    def test_factory_with_custom_config(self):
        cfg = DKAViolationDetectorConfig(hypokalemia_threshold=2.5)
        det = create_dka_violation_detector(config=cfg)
        assert det.config.hypokalemia_threshold == 2.5


# ===========================================================================
# Integration: detect_violations end-to-end
# ===========================================================================

class TestDetectViolationsIntegration:
    def test_clean_episode_returns_zero_risk(self):
        """Compliant episode → risk 0, summary says no violations"""
        actions = [
            _make_action("assess_vital_signs", 1.0),
            _make_action("establish_iv_access", 2.0),
            _make_action("order_lab_bmp", 3.0),
            _make_action("start_iv_fluid_ns", 10.0),
            _make_action("give_potassium_iv", 12.0),
            _make_action("start_insulin_infusion", 50.0),
        ]
        episode = _make_episode(actions=actions)
        gt = {"lab_potassium": 4.0, "lab_ph": 7.3, "lab_glucose": 450}

        result = DKAViolationDetector().detect_violations(episode, gt)

        assert result["total_risk_score"] == 0.0
        assert "No violations detected" in result["summary"]

    def test_multi_violation_episode(self):
        """Episode with multiple violations produces nonzero risk"""
        actions = [
            _make_action("start_insulin_infusion", 10.0),  # no BMP, no K+ replacement
        ]
        episode = _make_episode(actions=actions)
        gt = {"lab_potassium": 2.5, "lab_ph": 6.9}

        result = DKAViolationDetector().detect_violations(episode, gt)

        assert result["total_risk_score"] > 0
        assert len(result["trap_violations"]) > 0
        assert len(result["omission_violations"]) > 0

    def test_result_keys(self):
        """detect_violations returns all expected keys"""
        episode = _make_episode(actions=[])
        result = DKAViolationDetector().detect_violations(episode, {})

        expected_keys = {
            "trap_violations",
            "timing_violations",
            "sequence_violations",
            "omission_violations",
            "total_risk_score",
            "summary",
        }
        assert set(result.keys()) == expected_keys
