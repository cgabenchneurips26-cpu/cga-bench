"""
Synergistic Harm Interaction Tests.

Tests for ClinicalInteractionDetector and HarmScorer synergy integration.
Covers: baseline (no interactions), pairwise detection, triple jeopardy,
aggregate risk modification, clinical scenarios, and edge cases.
"""
from __future__ import annotations

from typing import Dict, List, Optional

import pytest

from cga_bench.cpg_model.schemas.base import (
    Action, ActionType, CGAScore, EpisodeLog, HarmSeverity,
    PatientState, RecommendationClass, SynergyPenalty,
    ViolationEvent, ViolationType, VitalSigns,
)
from cga_bench.assessor_core.harm_scorer import HarmScorer, HarmScorerConfig
from cga_bench.assessor_core.clinical_interaction_detector import (
    ClinicalInteractionDetector, InteractionConfig, InteractionGroup,
    InteractionPattern, InteractionType,
)


# --- Fixtures ---

def _make_violation(
    violation_id: str = "v1",
    violation_type: ViolationType = ViolationType.OMISSION,
    timestamp: float = 5.0,
    action_involved: Optional[str] = None,
    expected_action: Optional[str] = None,
    severity: HarmSeverity = HarmSeverity.MAJOR,
    node: str = "node1",
) -> ViolationEvent:
    return ViolationEvent(
        violation_id=violation_id,
        violation_type=violation_type,
        timestamp_minutes=timestamp,
        action_involved=action_involved,
        expected_action=expected_action,
        state_at_violation="state1",
        node_at_violation=node,
        harm_severity=severity,
        guideline_class=RecommendationClass.CLASS_I,
        preventability=1.0,
        description=f"Test violation {violation_id}",
        guideline_reference="Test Guideline",
    )


def _make_config(
    interaction_config: Optional[InteractionConfig] = None,
) -> HarmScorerConfig:
    return HarmScorerConfig(
        severity_weights={
            HarmSeverity.MINOR: 0.1,
            HarmSeverity.MODERATE: 0.3,
            HarmSeverity.MAJOR: 0.5,
            HarmSeverity.SEVERE: 0.8,
            HarmSeverity.CATASTROPHIC: 1.0,
        },
        guideline_strength_weights={
            RecommendationClass.CLASS_I: 1.0,
            RecommendationClass.CLASS_IIA: 0.7,
            RecommendationClass.CLASS_IIB: 0.4,
            RecommendationClass.CLASS_III: 0.0,
            None: 0.5,
        },
        violation_type_weights={
            ViolationType.OMISSION: 0.7,
            ViolationType.COMMISSION: 1.0,
            ViolationType.TIMING: 0.5,
            ViolationType.SEQUENCE: 0.6,
            ViolationType.DEVIATION: 0.3,
        },
        interaction_config=interaction_config,
    )


def _make_episode(num_actions: int = 1) -> EpisodeLog:
    vitals = VitalSigns(
        heart_rate=80, blood_pressure_systolic=120,
        blood_pressure_diastolic=80, respiratory_rate=16,
        temperature=37.0, oxygen_saturation=98,
    )
    state = PatientState(
        state_id="s1", age=50, sex="M",
        vitals=vitals, chief_complaint="test",
    )
    actions = [
        Action(
            type=ActionType.PROCEDURE,
            action_id=f"action_{i}",
            args={},
            timestamp_minutes=i * 5.0,
        )
        for i in range(num_actions)
    ]
    return EpisodeLog(
        episode_id="test_ep",
        scenario_id="test_scenario",
        agent_id="test_agent",
        states=[state],
        actions=actions,
        observations=[{}],
        total_duration_minutes=60.0,
        total_llm_calls=0,
        total_tokens=0,
        total_tool_calls=num_actions,
        termination_reason="success",
    )


def _make_temporal_pattern(
    window: float = 15.0,
    multiplier: float = 1.5,
) -> InteractionPattern:
    return InteractionPattern(
        pattern_id="temporal_test",
        interaction_type=InteractionType.TEMPORAL_PROXIMITY,
        temporal_window_minutes=window,
        multiplier=multiplier,
        max_multiplier=3.0,
        clinical_rationale="Temporal proximity interaction",
    )


def _make_causal_pattern(
    action_a: str = "nitrates",
    action_b: str = "right_leads",
    multiplier: float = 2.0,
) -> InteractionPattern:
    return InteractionPattern(
        pattern_id="causal_test",
        interaction_type=InteractionType.CAUSAL_CHAIN,
        violation_type_a=ViolationType.COMMISSION,
        violation_type_b=ViolationType.OMISSION,
        action_pattern_a=action_a,
        action_pattern_b=action_b,
        temporal_window_minutes=60.0,
        causal_direction="a_before_b",
        multiplier=multiplier,
        max_multiplier=3.0,
        clinical_rationale="Causal chain interaction",
    )


def _make_phase_pattern(multiplier: float = 1.5) -> InteractionPattern:
    return InteractionPattern(
        pattern_id="phase_test",
        interaction_type=InteractionType.PHASE_COMPOUNDING,
        require_same_phase=True,
        temporal_window_minutes=30.0,
        multiplier=multiplier,
        max_multiplier=3.0,
        clinical_rationale="Phase compounding interaction",
    )


def _make_interaction_config(
    patterns: Optional[List[InteractionPattern]] = None,
    **kwargs,
) -> InteractionConfig:
    return InteractionConfig(
        interaction_patterns=patterns or [_make_temporal_pattern()],
        phase_definitions={
            "assessment": ["order_lab.*", "obtain.*", "assess.*"],
            "treatment": ["give_.*", "start_.*", "activate.*"],
            "monitoring": ["serial_.*", "reassess.*", "monitor.*"],
        },
        **kwargs,
    )


# =====================================================
# TEST CATEGORY 1: Baseline (No Interactions)
# =====================================================

class TestNoInteractions:
    """When no interactions are detected, scores should be unchanged"""

    def test_single_violation_no_synergy(self):
        """A single violation cannot form an interaction group"""
        config = _make_config(interaction_config=_make_interaction_config())
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [_make_violation("v1")]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert score.synergistic_penalties == []
        assert score.synergistic_risk == 0.0

    def test_violations_outside_temporal_window(self):
        """Two violations far apart in time do not interact"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_temporal_pattern(window=15.0)]
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0),
            _make_violation("v2", timestamp=120.0),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert score.synergistic_penalties == []
        assert score.synergistic_risk == 0.0

    def test_no_interaction_config_backward_compat(self):
        """HarmScorerConfig with interaction_config=None behaves identically"""
        config_no_interaction = _make_config(interaction_config=None)
        scorer = HarmScorer(total_mandatory_count=5, config=config_no_interaction)
        violations = [
            _make_violation("v1", timestamp=5.0),
            _make_violation("v2", timestamp=10.0),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert score.synergistic_penalties == []
        assert score.synergistic_risk == 0.0
        # Aggregate risk should be pure sum of individual weights
        assert score.aggregate_risk > 0.0

    def test_empty_violations_no_crash(self):
        """No violations produces no interactions"""
        config = _make_config(interaction_config=_make_interaction_config())
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        score = scorer.compute_score([], _make_episode())
        assert score.synergistic_penalties == []
        assert score.synergistic_risk == 0.0
        assert score.compliance_score == 1.0

    def test_violations_different_phases_with_phase_required(self):
        """Violations in different phases with require_same_phase=True don't match"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_phase_pattern()]
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0, expected_action="order_lab_lactate"),
            _make_violation("v2", timestamp=10.0, expected_action="give_antibiotics"),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert score.synergistic_penalties == []


# =====================================================
# TEST CATEGORY 2: Pairwise Interactions
# =====================================================

class TestPairwiseInteractions:
    """Pairwise synergistic interaction detection"""

    def test_temporal_proximity_within_window(self):
        """Two violations within temporal window are detected"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_temporal_pattern(window=15.0, multiplier=1.5)]
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0),
            _make_violation("v2", timestamp=12.0),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert len(score.synergistic_penalties) == 1
        assert score.synergistic_penalties[0].multiplier == 1.5
        assert score.synergistic_risk > 0.0

    def test_commission_omission_causal_chain(self):
        """Commission causing downstream omission (causal chain)"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_causal_pattern(
                    action_a="nitrates",
                    action_b="right_leads",
                    multiplier=2.0,
                )]
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation(
                "v1", violation_type=ViolationType.COMMISSION,
                timestamp=5.0, action_involved="give_nitrates",
            ),
            _make_violation(
                "v2", violation_type=ViolationType.OMISSION,
                timestamp=30.0, expected_action="obtain_right_leads",
            ),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert len(score.synergistic_penalties) == 1
        assert score.synergistic_penalties[0].interaction_type == "causal_chain"
        assert score.synergistic_penalties[0].multiplier == 2.0

    def test_causal_chain_wrong_direction_no_match(self):
        """Causal chain with wrong temporal order does not match"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_causal_pattern(
                    action_a="nitrates",
                    action_b="right_leads",
                    multiplier=2.0,
                )]
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        # v_b occurs BEFORE v_a (wrong direction for "a_before_b")
        violations = [
            _make_violation(
                "v1", violation_type=ViolationType.COMMISSION,
                timestamp=30.0, action_involved="give_nitrates",
            ),
            _make_violation(
                "v2", violation_type=ViolationType.OMISSION,
                timestamp=5.0, expected_action="obtain_right_leads",
            ),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert len(score.synergistic_penalties) == 0

    def test_phase_compounding_same_phase(self):
        """Two violations in same clinical phase (treatment)"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_phase_pattern(multiplier=1.5)]
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation(
                "v1", violation_type=ViolationType.TIMING,
                timestamp=5.0, expected_action="give_antibiotics",
            ),
            _make_violation(
                "v2", violation_type=ViolationType.OMISSION,
                timestamp=10.0, expected_action="give_crystalloid",
            ),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert len(score.synergistic_penalties) == 1
        assert score.synergistic_penalties[0].interaction_type == "phase_compounding"

    def test_additional_risk_calculation(self):
        """Verify additional_risk = base_combined * (multiplier - 1)"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_temporal_pattern(window=15.0, multiplier=1.5)]
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0, severity=HarmSeverity.MAJOR),
            _make_violation("v2", timestamp=10.0, severity=HarmSeverity.MAJOR),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        penalty = score.synergistic_penalties[0]

        # Each MAJOR violation weight: severity(0.5) * guideline(1.0) * preventability(1.0) * type(0.7) = 0.35
        # harm = severity(0.5)
        # weighted_score = 0.35 * 0.5 = 0.175 per violation
        # base_combined = 0.175 + 0.175 = 0.35
        # additional_risk = 0.35 * (1.5 - 1.0) = 0.175
        expected_individual = 0.5 * 1.0 * 1.0 * 0.7 * 0.5  # 0.175
        expected_additional = (expected_individual * 2) * 0.5  # 0.175
        assert abs(penalty.additional_risk - expected_additional) < 1e-6
        assert abs(score.synergistic_risk - expected_additional) < 1e-6

    def test_multiple_patterns_best_multiplier_wins(self):
        """When multiple patterns match, highest multiplier is used"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[
                    _make_temporal_pattern(window=15.0, multiplier=1.3),
                    _make_temporal_pattern(window=20.0, multiplier=1.8),
                ]
            )
        )
        # Make patterns distinguishable
        config.interaction_config.interaction_patterns[0].pattern_id = "low_mult"
        config.interaction_config.interaction_patterns[1].pattern_id = "high_mult"

        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0),
            _make_violation("v2", timestamp=10.0),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert len(score.synergistic_penalties) == 1
        assert score.synergistic_penalties[0].multiplier == 1.8

    def test_same_node_required(self):
        """Violations at different CPG nodes don't match with require_same_node=True"""
        pattern = _make_temporal_pattern(window=15.0, multiplier=1.5)
        pattern.require_same_node = True
        config = _make_config(
            interaction_config=_make_interaction_config(patterns=[pattern])
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0, node="node_a"),
            _make_violation("v2", timestamp=10.0, node="node_b"),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert len(score.synergistic_penalties) == 0


# =====================================================
# TEST CATEGORY 3: Triple Jeopardy
# =====================================================

class TestTripleJeopardy:
    """Triple jeopardy: 3+ compounding violations"""

    def test_triple_violations_in_same_phase(self):
        """Three violations in treatment phase with triple multiplier"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_phase_pattern(multiplier=1.5)],
                enable_triple_jeopardy=True,
                triple_jeopardy_multiplier=2.0,
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0, expected_action="give_antibiotics"),
            _make_violation("v2", timestamp=10.0, expected_action="give_crystalloid"),
            _make_violation("v3", timestamp=15.0, expected_action="start_vasopressor"),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        # Should have pairwise groups + a triple group
        triple_groups = [p for p in score.synergistic_penalties if "triple" in p.group_id]
        assert len(triple_groups) >= 1

    def test_triple_multiplier_capped_at_max(self):
        """Triple multiplier is capped at max_multiplier"""
        pattern = _make_phase_pattern(multiplier=1.8)
        pattern.max_multiplier = 2.5
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[pattern],
                enable_triple_jeopardy=True,
                triple_jeopardy_multiplier=2.0,
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0, expected_action="give_a"),
            _make_violation("v2", timestamp=10.0, expected_action="give_b"),
            _make_violation("v3", timestamp=15.0, expected_action="give_c"),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        triple_groups = [p for p in score.synergistic_penalties if "triple" in p.group_id]
        if triple_groups:
            # multiplier should be min(1.8 * 2.0, 2.5) = 2.5
            assert triple_groups[0].multiplier <= 2.5

    def test_triple_jeopardy_disabled(self):
        """When enable_triple_jeopardy=False, only pairs are detected"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_phase_pattern(multiplier=1.5)],
                enable_triple_jeopardy=False,
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0, expected_action="give_a"),
            _make_violation("v2", timestamp=10.0, expected_action="give_b"),
            _make_violation("v3", timestamp=15.0, expected_action="give_c"),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        triple_groups = [p for p in score.synergistic_penalties if "triple" in p.group_id]
        assert len(triple_groups) == 0


# =====================================================
# TEST CATEGORY 4: Aggregate Risk Modification
# =====================================================

class TestAggregateRiskModification:
    """Verify that aggregate_risk is correctly modified"""

    def test_aggregate_risk_increases_with_interaction(self):
        """aggregate_risk = sum(individual) + synergistic_risk"""
        config_no_interaction = _make_config(interaction_config=None)
        config_with_interaction = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_temporal_pattern(window=15.0, multiplier=1.5)]
            )
        )

        violations = [
            _make_violation("v1", timestamp=5.0),
            _make_violation("v2", timestamp=10.0),
        ]
        episode = _make_episode()

        scorer_no = HarmScorer(total_mandatory_count=5, config=config_no_interaction)
        scorer_with = HarmScorer(total_mandatory_count=5, config=config_with_interaction)

        score_no = scorer_no.compute_score(violations, episode)
        score_with = scorer_with.compute_score(violations, episode)

        assert score_with.aggregate_risk > score_no.aggregate_risk
        assert score_with.synergistic_risk > 0.0
        assert abs(
            score_with.aggregate_risk - (score_no.aggregate_risk + score_with.synergistic_risk)
        ) < 1e-6

    def test_peak_risk_unchanged_by_interactions(self):
        """peak_risk is NOT modified by interactions"""
        config_no = _make_config(interaction_config=None)
        config_with = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_temporal_pattern(window=15.0, multiplier=2.0)]
            )
        )
        violations = [
            _make_violation("v1", timestamp=5.0),
            _make_violation("v2", timestamp=10.0),
        ]
        episode = _make_episode()

        score_no = HarmScorer(total_mandatory_count=5, config=config_no).compute_score(violations, episode)
        score_with = HarmScorer(total_mandatory_count=5, config=config_with).compute_score(violations, episode)

        assert score_no.peak_risk == score_with.peak_risk

    def test_compliance_score_unchanged_by_interactions(self):
        """compliance_score is based on violation count, not weights"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_temporal_pattern(window=15.0, multiplier=3.0)]
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0),
            _make_violation("v2", timestamp=10.0),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        # compliance = 1 - 2/5 = 0.6
        assert abs(score.compliance_score - 0.6) < 1e-6

    def test_sub_scores_unchanged_by_interactions(self):
        """C1-C5 sub-scores are based on violation type counts, not weights"""
        config_no = _make_config(interaction_config=None)
        config_with = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_temporal_pattern(window=15.0, multiplier=2.0)]
            )
        )
        violations = [
            _make_violation("v1", timestamp=5.0, violation_type=ViolationType.OMISSION),
            _make_violation("v2", timestamp=10.0, violation_type=ViolationType.TIMING),
        ]
        episode = _make_episode()

        score_no = HarmScorer(total_mandatory_count=5, config=config_no).compute_score(violations, episode)
        score_with = HarmScorer(total_mandatory_count=5, config=config_with).compute_score(violations, episode)

        assert score_no.sub_scores == score_with.sub_scores


# =====================================================
# TEST CATEGORY 5: Clinical Scenarios
# =====================================================

class TestClinicalScenarios:
    """Clinically meaningful interaction scenarios"""

    def test_rv_infarct_nitrates_plus_missed_right_leads(self):
        """RV infarct: nitrates (COMMISSION) + not checking V4R (OMISSION)"""
        pattern = InteractionPattern(
            pattern_id="rv_nitrates_trap",
            interaction_type=InteractionType.CONTRAINDICATION_COMPOUND,
            violation_type_a=ViolationType.COMMISSION,
            violation_type_b=ViolationType.OMISSION,
            action_pattern_a="nitro",
            action_pattern_b="right_leads|v4r",
            temporal_window_minutes=30.0,
            multiplier=2.0,
            max_multiplier=3.0,
            escalated_severity=HarmSeverity.CATASTROPHIC,
            clinical_rationale="Nitrates in RV infarct without V4R - hemodynamic collapse",
            source_guideline="AHA 2013 STEMI",
        )
        config = _make_config(
            interaction_config=_make_interaction_config(patterns=[pattern])
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation(
                "v_nitrate", violation_type=ViolationType.COMMISSION,
                timestamp=10.0, action_involved="give_nitroglycerin",
                severity=HarmSeverity.SEVERE,
            ),
            _make_violation(
                "v_leads", violation_type=ViolationType.OMISSION,
                timestamp=5.0, expected_action="obtain_right_leads_v4r",
                severity=HarmSeverity.MAJOR,
            ),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert len(score.synergistic_penalties) == 1
        penalty = score.synergistic_penalties[0]
        assert penalty.interaction_type == "contraindication_compound"
        assert penalty.multiplier == 2.0
        assert score.synergistic_risk > 0.0

    def test_sepsis_delayed_antibiotics_plus_sequence_error(self):
        """Sepsis: TIMING on antibiotics + SEQUENCE on blood cultures"""
        patterns = [
            InteractionPattern(
                pattern_id="sepsis_abx_culture",
                interaction_type=InteractionType.CAUSAL_CHAIN,
                violation_type_a=ViolationType.TIMING,
                violation_type_b=ViolationType.SEQUENCE,
                action_pattern_a="antibiotics",
                action_pattern_b="blood_culture",
                temporal_window_minutes=60.0,
                multiplier=1.8,
                max_multiplier=3.0,
                clinical_rationale="Delayed antibiotics with sequence error compounds infection risk",
                source_guideline="SSC 2021",
            ),
        ]
        config = _make_config(
            interaction_config=_make_interaction_config(patterns=patterns)
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation(
                "v_timing", violation_type=ViolationType.TIMING,
                timestamp=45.0, expected_action="give_broad_spectrum_antibiotics",
                severity=HarmSeverity.SEVERE,
            ),
            _make_violation(
                "v_seq", violation_type=ViolationType.SEQUENCE,
                timestamp=40.0, action_involved="order_lab_blood_culture",
                severity=HarmSeverity.MAJOR,
            ),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert len(score.synergistic_penalties) == 1
        assert score.synergistic_penalties[0].multiplier == 1.8

    def test_aki_contrast_without_hydration(self):
        """AKI: OMISSION(hydration) + COMMISSION(contrast without protection)"""
        pattern = InteractionPattern(
            pattern_id="aki_contrast_hydration",
            interaction_type=InteractionType.CONTRAINDICATION_COMPOUND,
            violation_type_a=ViolationType.COMMISSION,
            violation_type_b=ViolationType.OMISSION,
            action_pattern_a="contrast",
            action_pattern_b="hydration|fluid",
            temporal_window_minutes=60.0,
            multiplier=1.8,
            max_multiplier=3.0,
            clinical_rationale="Contrast without pre-hydration doubles nephrotoxic risk",
            source_guideline="KDIGO AKI",
        )
        config = _make_config(
            interaction_config=_make_interaction_config(patterns=[pattern])
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation(
                "v_contrast", violation_type=ViolationType.COMMISSION,
                timestamp=30.0, action_involved="give_iodinated_contrast",
                severity=HarmSeverity.MAJOR,
            ),
            _make_violation(
                "v_hydration", violation_type=ViolationType.OMISSION,
                timestamp=60.0, expected_action="give_pre_hydration_fluid",
                severity=HarmSeverity.MODERATE,
            ),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert len(score.synergistic_penalties) == 1
        assert score.synergistic_risk > 0.0


# =====================================================
# TEST CATEGORY 6: Edge Cases
# =====================================================

class TestEdgeCases:
    """Edge cases and boundary conditions"""

    def test_all_violations_same_timestamp(self):
        """Multiple violations at exactly the same time match temporal"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_temporal_pattern(window=15.0, multiplier=1.5)]
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0),
            _make_violation("v2", timestamp=5.0),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert len(score.synergistic_penalties) == 1

    def test_violation_in_multiple_groups(self):
        """A violation can participate in multiple interaction groups"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_temporal_pattern(window=15.0, multiplier=1.5)]
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        # v1 interacts with both v2 and v3
        violations = [
            _make_violation("v1", timestamp=5.0),
            _make_violation("v2", timestamp=10.0),
            _make_violation("v3", timestamp=15.0),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        # v1-v2 and v2-v3 at minimum should match (v1-v3 is at boundary)
        assert len(score.synergistic_penalties) >= 2

    def test_detector_config_required(self):
        """ClinicalInteractionDetector raises on None config"""
        with pytest.raises(ValueError, match="config is required"):
            ClinicalInteractionDetector(None)

    def test_type_disabled_no_match(self):
        """Disabled interaction type is not detected"""
        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_temporal_pattern(window=15.0, multiplier=1.5)],
                enable_temporal_proximity=False,
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0),
            _make_violation("v2", timestamp=10.0),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        assert len(score.synergistic_penalties) == 0

    def test_synergy_penalty_in_score_report(self):
        """MetricsReporter displays synergistic interaction info"""
        from cga_bench.assessor_core.harm_scorer import MetricsReporter

        config = _make_config(
            interaction_config=_make_interaction_config(
                patterns=[_make_temporal_pattern(window=15.0, multiplier=1.5)]
            )
        )
        scorer = HarmScorer(total_mandatory_count=5, config=config)
        violations = [
            _make_violation("v1", timestamp=5.0),
            _make_violation("v2", timestamp=10.0),
        ]
        episode = _make_episode()

        score = scorer.compute_score(violations, episode)
        report = MetricsReporter.format_score_report(score)
        assert "Synergistic Interactions" in report
        assert "Interaction Groups: 1" in report


# =====================================================
# TEST CATEGORY 7: Detector Unit Tests
# =====================================================

class TestDetectorUnit:
    """Direct unit tests for ClinicalInteractionDetector"""

    def test_detect_interactions_returns_groups(self):
        """detect_interactions returns InteractionGroup list"""
        detector = ClinicalInteractionDetector(
            _make_interaction_config(
                patterns=[_make_temporal_pattern(window=15.0)]
            )
        )
        violations = [
            _make_violation("v1", timestamp=5.0),
            _make_violation("v2", timestamp=10.0),
        ]
        groups = detector.detect_interactions(violations)
        assert len(groups) == 1
        assert isinstance(groups[0], InteractionGroup)
        assert set(groups[0].violation_ids) == {"v1", "v2"}

    def test_phase_assignment(self):
        """Phase assignment correctly classifies actions"""
        detector = ClinicalInteractionDetector(
            _make_interaction_config()
        )
        violations = [
            _make_violation("v1", expected_action="order_lab_lactate"),
            _make_violation("v2", expected_action="give_antibiotics"),
            _make_violation("v3", expected_action="monitor_vitals"),
        ]
        assignments = detector._assign_phases(violations)
        assert assignments["v1"] == "assessment"
        assert assignments["v2"] == "treatment"
        assert assignments["v3"] == "monitoring"

    def test_action_regex_matching(self):
        """Action patterns use regex for flexible matching"""
        pattern = InteractionPattern(
            pattern_id="regex_test",
            interaction_type=InteractionType.TEMPORAL_PROXIMITY,
            action_pattern_a="nitro",  # partial match via regex
            temporal_window_minutes=15.0,
            multiplier=1.5,
            max_multiplier=3.0,
        )
        detector = ClinicalInteractionDetector(
            _make_interaction_config(patterns=[pattern])
        )
        violations = [
            _make_violation("v1", timestamp=5.0, action_involved="give_nitroglycerin"),
            _make_violation("v2", timestamp=10.0),
        ]
        groups = detector.detect_interactions(violations)
        assert len(groups) == 1
