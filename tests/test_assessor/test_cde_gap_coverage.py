"""M3 gap-coverage tests for CDE rescoring (B-cde-rescoring v1.1).

Addresses four test gaps identified in the 260430_CDE_rescoring_gap.md audit:
  M3-a. E2E eval_harness integration (enable_cde_rescoring=True, SCN-012 scenario)
  M3-b. Patient context deficit → graceful degradation (derived_constraints=None)
  M3-c. C6 sub-construct isolation from compliance_score (no double-counting)
  M3-d. HarmScorer CONFLICT type weight injection + scoring correctness
"""

from __future__ import annotations

import copy

from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig
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
    CGAScore,
    EpisodeLog,
    HarmSeverity,
    PatientState,
    RecommendationClass,
    ViolationType,
    VitalSigns,
)

# ---------------------------------------------------------------------------
# Shared fixtures
# ---------------------------------------------------------------------------


def _scn012_graph() -> dict:
    """Synthesised PE graph with REQ ∩ FORB overlap on give_alteplase_pe."""
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
                "allowed_actions": [
                    "order_imaging_ctpa",
                    "give_alteplase_pe",
                    "anticoagulation",
                ],
                "mandatory_actions": [],
                "forbidden_actions": [],
                "deadlines": {},
                "conditional_rules": [
                    {
                        "rule_id": "PE-MASSIVE-THROMBOLYSIS",
                        "condition": "patient.vitals.sbp < 90",
                        "effect": {
                            "type": "REQUIRED",
                            "actions": ["give_alteplase_pe"],
                        },
                        "evidence": "ESC 2019 Class I",
                        "severity": "CRITICAL",
                        "description": "Massive PE thrombolysis required",
                    },
                    {
                        "rule_id": "PE-RECENT-SURGERY-NO-THROMBOLYSIS",
                        "condition": "'recent_surgery' in patient.comorbidities",
                        "effect": {
                            "type": "FORBIDDEN",
                            "actions": ["give_alteplase_pe"],
                        },
                        "evidence": "ESC 2019 absolute contraindication",
                        "severity": "CRITICAL",
                        "description": "Recent surgery contraindication",
                    },
                ],
            }
        },
    }


def _patient_conflict() -> dict:
    """Patient matching BOTH conditions → CONFLICT on give_alteplase_pe."""
    return {
        "vitals": {"sbp": 80, "map_mmhg": 55},
        "comorbidities": ["recent_surgery"],
        "allergies": [],
    }


def _patient_no_conflict() -> dict:
    """Patient matching only REQ (sbp < 90) but NOT FORB → no conflict."""
    return {
        "vitals": {"sbp": 80, "map_mmhg": 55},
        "comorbidities": [],
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
    actions = [
        _action("order_imaging_ctpa", 10),
        _action("anticoagulation", 30),
    ]
    states = [_state(0, "s0")]
    for i, a in enumerate(actions, 1):
        states.append(_state(a.timestamp_minutes, f"s{i}"))
    return EpisodeLog(
        episode_id="scn012_gap",
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


def _violation_extractor_config() -> ViolationExtractorConfig:
    return ViolationExtractorConfig(
        harm_severity_mappings=[
            HarmSeverityMapping(action_pattern="alteplase", severity=HarmSeverity.SEVERE),
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


def _harm_scorer_config() -> HarmScorerConfig:
    return HarmScorerConfig(
        severity_weights={
            HarmSeverity.MINOR: 0.1,
            HarmSeverity.MODERATE: 0.4,
            HarmSeverity.MAJOR: 0.7,
            HarmSeverity.SEVERE: 0.9,
            HarmSeverity.CATASTROPHIC: 1.0,
        },
        guideline_strength_weights={
            RecommendationClass.CLASS_I: 1.0,
            RecommendationClass.CLASS_IIA: 0.8,
            RecommendationClass.CLASS_IIB: 0.5,
            RecommendationClass.CLASS_III: 1.0,
            None: 1.0,
        },
        violation_type_weights={
            ViolationType.OMISSION: 1.0,
            ViolationType.COMMISSION: 1.5,
            ViolationType.TIMING: 0.8,
            ViolationType.SEQUENCE: 0.6,
            ViolationType.DEVIATION: 0.4,
            # CONFLICT explicitly set to verify injection
            ViolationType.CONFLICT: 1.5,
        },
    )


def _engine():
    eng = CPGEngineFactory.load_from_dict(copy.deepcopy(_scn012_graph()))
    eng.current_node_id = "init"
    return eng


# ---------------------------------------------------------------------------
# M3-a: E2E integration — CDE-coupled scoring produces different results
# ---------------------------------------------------------------------------


class TestCDEE2EIntegration:
    """End-to-end: CDE-coupled scoring surfaces conflict violations.

    Legacy scoring misses these, resulting in a lower compliance score.
    """

    def test_cde_coupled_score_lower_than_legacy(self) -> None:
        """enable_cde_rescoring=True → compliance_score strictly <= legacy."""
        episode = _episode_skipping_thrombolysis()
        config = _violation_extractor_config()
        scorer_config = _harm_scorer_config()

        # Legacy path
        legacy_violations = ViolationExtractor(_engine(), config).extract_violations(episode)
        legacy_scorer = HarmScorer(total_mandatory_count=1, config=scorer_config)
        legacy_score: CGAScore = legacy_scorer.compute_score(legacy_violations, episode)

        # CDE-coupled path
        cde = ConstraintDerivationEngine()
        derived = cde.derive(_scn012_graph(), _patient_conflict(), scenario_id="scn012_e2e")
        cde_violations = ViolationExtractor(_engine(), config).extract_violations(episode, derived_constraints=derived)
        cde_scorer = HarmScorer(total_mandatory_count=1, config=scorer_config)
        cde_score: CGAScore = cde_scorer.compute_score(cde_violations, episode)

        # CDE path finds more violations
        assert len(cde_violations) > len(legacy_violations)
        # Compliance never improves with more violations
        assert cde_score.compliance_score <= legacy_score.compliance_score

    def test_cde_coupled_emits_conflict_type_in_score(self) -> None:
        """CDE-coupled CGAScore.violations_by_type includes 'conflict'."""
        episode = _episode_skipping_thrombolysis()
        config = _violation_extractor_config()
        scorer_config = _harm_scorer_config()

        cde = ConstraintDerivationEngine()
        derived = cde.derive(_scn012_graph(), _patient_conflict(), scenario_id="scn012_e2e")
        violations = ViolationExtractor(_engine(), config).extract_violations(episode, derived_constraints=derived)
        score = HarmScorer(total_mandatory_count=1, config=scorer_config).compute_score(violations, episode)

        assert "conflict" in score.violations_by_type
        assert score.violations_by_type["conflict"] >= 1


# ---------------------------------------------------------------------------
# M3-b: Patient context deficit → graceful degradation
# ---------------------------------------------------------------------------


class TestCDEGracefulDegradation:
    """When patient_context_for_cde is missing or malformed, graceful fallback.

    CDE derive() must either return an empty constraint set or raise a handled error.
    """

    def test_none_patient_context_returns_empty_or_raises(self) -> None:
        """derive() with None patient context → no crash, empty or error."""
        cde = ConstraintDerivationEngine()
        # The CDE should handle gracefully
        try:
            result = cde.derive(_scn012_graph(), None, scenario_id="ctx-none")
            # If it returns, should have no triggered rules
            assert result.total_rules_triggered == 0
        except (TypeError, AttributeError):
            # Acceptable: CDE raises on None context
            pass

    def test_empty_patient_context_no_rules_triggered(self) -> None:
        """Empty patient dict → no conditions evaluate True → no constraints."""
        cde = ConstraintDerivationEngine()
        result = cde.derive(_scn012_graph(), {}, scenario_id="ctx-empty")
        # No vitals → sbp condition fails, no comorbidities → comorbidity condition fails
        assert len(result.conflicts) == 0

    def test_partial_patient_context_still_works(self) -> None:
        """Patient with vitals but no comorbidities → only REQ fires, no FORB → no conflict."""
        cde = ConstraintDerivationEngine()
        result = cde.derive(_scn012_graph(), _patient_no_conflict(), scenario_id="ctx-partial")
        # REQ fires (sbp=80 < 90), FORB does not (no recent_surgery) → no conflict
        assert len(result.required) >= 1
        assert len(result.conflicts) == 0

    def test_runner_failsafe_none_constraint_produces_legacy(self) -> None:
        """When derived_constraints=None, ViolationExtractor produces legacy output.

        This tests the runner except-block fallback path.
        """
        episode = _episode_skipping_thrombolysis()
        config = _violation_extractor_config()

        extractor = ViolationExtractor(_engine(), config)
        legacy = extractor.extract_violations(episode)

        extractor2 = ViolationExtractor(_engine(), config)
        with_none = extractor2.extract_violations(episode, derived_constraints=None)

        assert len(legacy) == len(with_none)
        legacy_types = sorted(v.violation_type for v in legacy)
        none_types = sorted(v.violation_type for v in with_none)
        assert legacy_types == none_types


# ---------------------------------------------------------------------------
# M3-c: C6 sub-construct isolation from compliance_score
# ---------------------------------------------------------------------------


class TestC6Isolation:
    """C6_conflict_avoidance must be in sub_scores but NOT affect compliance_score.

    This prevents double-counting since CONFLICT violations already contribute
    to the compliance denominator via violation_count.
    """

    def test_c6_zero_when_conflict_present(self) -> None:
        """When CONFLICT violations exist, C6 = 0.0."""
        episode = _episode_skipping_thrombolysis()
        config = _violation_extractor_config()
        scorer_config = _harm_scorer_config()

        cde = ConstraintDerivationEngine()
        derived = cde.derive(_scn012_graph(), _patient_conflict(), scenario_id="c6-test")
        violations = ViolationExtractor(_engine(), config).extract_violations(episode, derived_constraints=derived)
        score = HarmScorer(total_mandatory_count=1, config=scorer_config).compute_score(violations, episode)

        assert score.sub_scores["C6_conflict_avoidance"] == 0.0

    def test_c6_one_when_no_conflict(self) -> None:
        """When no CONFLICT violations, C6 = 1.0."""
        episode = _episode_skipping_thrombolysis()
        config = _violation_extractor_config()
        scorer_config = _harm_scorer_config()

        # Legacy (no CDE) → no CONFLICT violations
        violations = ViolationExtractor(_engine(), config).extract_violations(episode)
        score = HarmScorer(total_mandatory_count=1, config=scorer_config).compute_score(violations, episode)

        assert score.sub_scores["C6_conflict_avoidance"] == 1.0

    def test_compliance_uses_violation_count_not_c6(self) -> None:
        """Compliance uses violation_count / denom, not C6.

        denom = max(total_actions, mandatory_count, 1). C6 does NOT enter this formula.
        """
        episode = _episode_skipping_thrombolysis()
        config = _violation_extractor_config()
        scorer_config = _harm_scorer_config()

        cde = ConstraintDerivationEngine()
        derived = cde.derive(_scn012_graph(), _patient_conflict(), scenario_id="c6-formula")
        violations = ViolationExtractor(_engine(), config).extract_violations(episode, derived_constraints=derived)
        total_mandatory = 1
        scorer = HarmScorer(total_mandatory_count=total_mandatory, config=scorer_config)
        score = scorer.compute_score(violations, episode)

        # Manually compute expected compliance
        n_violations = len(violations)
        n_actions = len(episode.actions)
        denom = max(n_actions, total_mandatory, 1)
        expected_compliance = max(0, 1 - n_violations / denom)

        assert abs(score.compliance_score - expected_compliance) < 1e-9, (
            f"compliance_score={score.compliance_score} != expected={expected_compliance}"
        )


# ---------------------------------------------------------------------------
# M3-d: HarmScorer CONFLICT weight injection
# ---------------------------------------------------------------------------


class TestConflictWeightInjection:
    """Verify that CONFLICT type is properly weighted in the scoring pipeline."""

    def test_conflict_default_weight_injected(self) -> None:
        """HarmScorerConfig.__post_init__ injects CONFLICT weight when absent."""
        cfg = HarmScorerConfig(
            severity_weights={HarmSeverity.MODERATE: 0.4, HarmSeverity.SEVERE: 0.9},
            guideline_strength_weights={None: 1.0},
            violation_type_weights={
                ViolationType.OMISSION: 1.0,
                ViolationType.COMMISSION: 1.5,
            },
            cde_conflict_default_weight=2.0,
        )
        assert ViolationType.CONFLICT in cfg.violation_type_weights
        assert cfg.violation_type_weights[ViolationType.CONFLICT] == 2.0

    def test_conflict_explicit_weight_preserved(self) -> None:
        """Explicit CONFLICT weight in config is NOT overwritten by default."""
        cfg = HarmScorerConfig(
            severity_weights={HarmSeverity.MODERATE: 0.4},
            guideline_strength_weights={None: 1.0},
            violation_type_weights={
                ViolationType.OMISSION: 1.0,
                ViolationType.CONFLICT: 3.0,
            },
            cde_conflict_default_weight=1.5,
        )
        assert cfg.violation_type_weights[ViolationType.CONFLICT] == 3.0
