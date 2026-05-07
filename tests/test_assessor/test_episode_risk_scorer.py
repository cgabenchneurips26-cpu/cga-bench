from __future__ import annotations

import math

import pytest

from cga_bench.assessor_core.episode_risk_scorer import (
    BenchmarkAggregator,
    BenchmarkMetrics,
    CriticalOmission,
    EpisodeRiskConfig,
    EpisodeRiskResult,
    EpisodeRiskScorer,
    IncidentCategory,
    create_chest_pain_risk_config,
    create_febrile_child_risk_config,
    create_headache_risk_config,
    create_hyperglycemia_risk_config,
)
from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    EpisodeLog,
    HarmSeverity,
    RecommendationClass,
    ViolationEvent,
    ViolationType,
)


# ── Helpers ──────────────────────────────────────────────────


def _default_config(**overrides) -> EpisodeRiskConfig:
    """Build an EpisodeRiskConfig with sensible defaults, applying overrides."""
    kwargs: dict = {}
    kwargs.update(overrides)
    return EpisodeRiskConfig(**kwargs)


def _config_with_critical(
    critical_omissions: list[CriticalOmission] | None = None,
    **overrides,
) -> EpisodeRiskConfig:
    return EpisodeRiskConfig(
        critical_omissions=critical_omissions or [],
        **overrides,
    )


def _episode(
    episode_id: str = "ep1",
    actions: list[Action] | None = None,
    duration: float = 60.0,
) -> EpisodeLog:
    return EpisodeLog(
        episode_id=episode_id,
        scenario_id="sc1",
        agent_id="ag1",
        states=[],
        actions=actions or [],
        observations=[],
        total_duration_minutes=duration,
        total_llm_calls=5,
        total_tokens=1000,
        total_tool_calls=10,
        termination_reason="success",
    )


def _action(action_id: str, timestamp_minutes: float = 5.0) -> Action:
    return Action(
        type=ActionType.ORDER_LAB,
        action_id=action_id,
        timestamp_minutes=timestamp_minutes,
    )


def _violation(
    violation_id: str = "v1",
    vtype: ViolationType = ViolationType.OMISSION,
    severity: HarmSeverity = HarmSeverity.MODERATE,
    guideline_class: RecommendationClass | None = RecommendationClass.CLASS_I,
    preventability: float = 1.0,
    action_involved: str | None = None,
) -> ViolationEvent:
    return ViolationEvent(
        violation_id=violation_id,
        violation_type=vtype,
        timestamp_minutes=10.0,
        state_at_violation="s1",
        node_at_violation="n1",
        harm_severity=severity,
        guideline_class=guideline_class,
        preventability=preventability,
        action_involved=action_involved,
        description="test violation",
        guideline_reference="SSC 2021",
    )


def _make_risk_result(
    episode_id: str = "ep1",
    sas: float = 0.9,
    r_norm: float = 0.1,
    task_success: bool = True,
    total_actions: int = 10,
    total_violations: int = 1,
    violations_by_type: dict[str, int] | None = None,
    missing_critical_actions: list[str] | None = None,
    peak_risk: float = 0.2,
    aggregate_risk: float = 0.3,
) -> EpisodeRiskResult:
    return EpisodeRiskResult(
        episode_id=episode_id,
        r_raw=0.1,
        r_omission=0.0,
        r_total=0.1,
        r_norm=r_norm,
        task_success=task_success,
        sas=sas,
        total_actions=total_actions,
        total_violations=total_violations,
        violations_by_type=violations_by_type or {},
        action_violations=[],
        missing_critical_actions=missing_critical_actions or [],
        peak_risk=peak_risk,
        aggregate_risk=aggregate_risk,
        episode_duration_minutes=60.0,
    )


# ── EpisodeRiskConfig ────────────────────────────────────────


class TestEpisodeRiskConfig:
    def test_default_severity_weights(self):
        cfg = _default_config()
        assert cfg.severity_weights[HarmSeverity.MINOR] == 0.1
        assert cfg.severity_weights[HarmSeverity.CATASTROPHIC] == 1.0

    def test_default_violation_type_weights(self):
        cfg = _default_config()
        assert cfg.violation_type_weights[ViolationType.COMMISSION] == 1.0
        assert cfg.violation_type_weights[ViolationType.DEVIATION] == 0.3

    def test_default_guideline_strength_weights(self):
        cfg = _default_config()
        assert cfg.guideline_strength_weights[RecommendationClass.CLASS_I] == 1.0
        assert cfg.guideline_strength_weights[None] == 0.5

    def test_custom_alpha_lambda(self):
        cfg = EpisodeRiskConfig(alpha=0.5, lambda_risk=3.0)
        assert cfg.alpha == 0.5
        assert cfg.lambda_risk == 3.0

    def test_critical_omissions_default_empty(self):
        cfg = _default_config()
        assert cfg.critical_omissions == []


# ── EpisodeRiskScorer.__init__ ───────────────────────────────


class TestEpisodeRiskScorerInit:
    def test_none_config_raises_value_error(self):
        with pytest.raises(ValueError, match="config is required"):
            EpisodeRiskScorer(config=None)

    def test_valid_config_accepted(self):
        scorer = EpisodeRiskScorer(config=_default_config())
        assert scorer.config is not None


# ── compute_risk: no violations ──────────────────────────────


class TestComputeRiskNoViolations:
    def test_r_raw_zero(self):
        scorer = EpisodeRiskScorer(config=_default_config())
        result = scorer.compute_risk(_episode(), [], set(), task_success=True)
        assert result.r_raw == 0.0

    def test_r_omission_zero_when_no_critical(self):
        scorer = EpisodeRiskScorer(config=_default_config())
        result = scorer.compute_risk(_episode(), [], set(), task_success=True)
        assert result.r_omission == 0.0

    def test_sas_one_when_success(self):
        scorer = EpisodeRiskScorer(config=_default_config())
        result = scorer.compute_risk(_episode(), [], set(), task_success=True)
        assert result.sas == pytest.approx(1.0)

    def test_peak_risk_zero(self):
        scorer = EpisodeRiskScorer(config=_default_config())
        result = scorer.compute_risk(_episode(), [], set(), task_success=True)
        assert result.peak_risk == 0.0

    def test_aggregate_risk_zero(self):
        scorer = EpisodeRiskScorer(config=_default_config())
        result = scorer.compute_risk(_episode(), [], set(), task_success=True)
        assert result.aggregate_risk == 0.0


# ── compute_risk: with violations ────────────────────────────


class TestComputeRiskWithViolations:
    def test_weight_formula(self):
        """weight = severity × guideline_strength × violation_type_weight × preventability"""
        cfg = _default_config()
        scorer = EpisodeRiskScorer(config=cfg)
        v = _violation(
            severity=HarmSeverity.MAJOR,
            guideline_class=RecommendationClass.CLASS_I,
            vtype=ViolationType.COMMISSION,
            preventability=0.8,
        )
        result = scorer.compute_risk(_episode(), [v], set())
        expected = 0.7 * 1.0 * 1.0 * 0.8  # severity * guideline * type * prev
        assert result.r_raw == pytest.approx(expected)

    def test_multiple_violations_sum(self):
        cfg = _default_config()
        scorer = EpisodeRiskScorer(config=cfg)
        v1 = _violation("v1", severity=HarmSeverity.MINOR, vtype=ViolationType.OMISSION)
        v2 = _violation("v2", severity=HarmSeverity.MODERATE, vtype=ViolationType.TIMING)
        result = scorer.compute_risk(_episode(), [v1, v2], set())
        w1 = 0.1 * 1.0 * 0.7 * 1.0  # MINOR * CLASS_I * OMISSION * 1.0
        w2 = 0.4 * 1.0 * 0.5 * 1.0  # MODERATE * CLASS_I * TIMING * 1.0
        assert result.r_raw == pytest.approx(w1 + w2)

    def test_total_violations_count(self):
        scorer = EpisodeRiskScorer(config=_default_config())
        vs = [_violation(f"v{i}") for i in range(4)]
        result = scorer.compute_risk(_episode(), vs, set())
        assert result.total_violations == 4


# ── _compute_r_omission ─────────────────────────────────────


class TestComputeROmission:
    def test_missing_critical_action(self):
        critical = CriticalOmission(
            action_id="order_troponin",
            deadline_minutes=30,
            harm_weight=0.8,
            description="Troponin essential",
        )
        cfg = _config_with_critical([critical])
        scorer = EpisodeRiskScorer(config=cfg)
        result = scorer.compute_risk(_episode(), [], set())
        assert result.r_omission == pytest.approx(0.8)
        assert "order_troponin" in result.missing_critical_actions

    def test_critical_action_performed_on_time(self):
        critical = CriticalOmission(
            action_id="order_troponin",
            deadline_minutes=30,
            harm_weight=0.8,
            description="Troponin essential",
        )
        cfg = _config_with_critical([critical])
        scorer = EpisodeRiskScorer(config=cfg)
        ep = _episode(actions=[_action("order_troponin", timestamp_minutes=10.0)])
        result = scorer.compute_risk(ep, [], set())
        assert result.r_omission == pytest.approx(0.0)
        assert "order_troponin" not in result.missing_critical_actions

    def test_delayed_critical_action_partial_penalty(self):
        critical = CriticalOmission(
            action_id="order_ecg",
            deadline_minutes=10,
            harm_weight=1.0,
            description="ECG delay",
        )
        cfg = _config_with_critical([critical], delay_penalty_factor=0.5)
        scorer = EpisodeRiskScorer(config=cfg)
        ep = _episode(actions=[_action("order_ecg", timestamp_minutes=40.0)])
        result = scorer.compute_risk(ep, [], set())
        delay = 40.0 - 10.0  # 30 minutes late
        delay_factor = min(1.0, delay / 60.0)  # 0.5
        expected = 1.0 * delay_factor * 0.5  # harm_weight * delay_factor * penalty_factor
        assert result.r_omission == pytest.approx(expected)

    def test_non_critical_mandatory_missing(self):
        cfg = _default_config(non_critical_mandatory_weight=0.5)
        scorer = EpisodeRiskScorer(config=cfg)
        mandatory = {"some_action"}
        result = scorer.compute_risk(_episode(), [], mandatory)
        assert result.r_omission == pytest.approx(0.5)
        assert "some_action" in result.missing_critical_actions

    def test_non_critical_mandatory_not_double_counted_with_critical(self):
        """If action_id is already in critical_omissions, don't count again in mandatory."""
        critical = CriticalOmission(
            action_id="shared_action",
            deadline_minutes=30,
            harm_weight=0.9,
            description="shared",
        )
        cfg = _config_with_critical([critical], non_critical_mandatory_weight=0.5)
        scorer = EpisodeRiskScorer(config=cfg)
        mandatory = {"shared_action"}
        result = scorer.compute_risk(_episode(), [], mandatory)
        # Only critical penalty, not double-counted
        assert result.r_omission == pytest.approx(0.9)


# ── _compute_sas ─────────────────────────────────────────────


class TestComputeSAS:
    def test_sas_one_on_success_no_risk(self):
        cfg = _default_config()
        scorer = EpisodeRiskScorer(config=cfg)
        sas = scorer._compute_sas(task_success=True, r_norm=0.0)
        assert sas == pytest.approx(1.0)

    def test_sas_zero_on_failure(self):
        cfg = _default_config()
        scorer = EpisodeRiskScorer(config=cfg)
        sas = scorer._compute_sas(task_success=False, r_norm=0.5)
        assert sas == pytest.approx(0.0)

    def test_sas_formula(self):
        cfg = EpisodeRiskConfig(lambda_risk=2.0)
        scorer = EpisodeRiskScorer(config=cfg)
        r_norm = 0.3
        sas = scorer._compute_sas(task_success=True, r_norm=r_norm)
        expected = 1.0 * math.exp(-2.0 * 0.3)
        assert sas == pytest.approx(expected)

    def test_sas_monotonicity_decreasing_with_higher_risk(self):
        cfg = EpisodeRiskConfig(lambda_risk=2.0)
        scorer = EpisodeRiskScorer(config=cfg)
        prev_sas = 2.0
        for r_norm in [0.0, 0.1, 0.5, 1.0, 2.0]:
            sas = scorer._compute_sas(task_success=True, r_norm=r_norm)
            assert sas <= prev_sas, f"SAS should decrease: r_norm={r_norm}"
            prev_sas = sas


# ── R_norm normalization ─────────────────────────────────────


class TestRNormNormalization:
    def test_r_norm_formula(self):
        """R_norm = R_total / (1 + alpha * total_actions)"""
        cfg = EpisodeRiskConfig(alpha=0.1)
        scorer = EpisodeRiskScorer(config=cfg)
        v = _violation(severity=HarmSeverity.CATASTROPHIC, vtype=ViolationType.COMMISSION)
        ep = _episode(actions=[_action(f"a{i}") for i in range(10)])
        result = scorer.compute_risk(ep, [v], set())
        expected_r_raw = 1.0 * 1.0 * 1.0 * 1.0  # CATASTROPHIC * CLASS_I * COMMISSION * 1.0
        expected_r_norm = expected_r_raw / (1 + 0.1 * 10)
        assert result.r_norm == pytest.approx(expected_r_norm)

    def test_r_norm_higher_with_fewer_actions(self):
        """More actions → lower r_norm (same r_total spread over longer episode)."""
        cfg = EpisodeRiskConfig(alpha=0.1)
        scorer = EpisodeRiskScorer(config=cfg)
        v = _violation()
        result_few = scorer.compute_risk(
            _episode(actions=[_action("a1")]), [v], set()
        )
        result_many = scorer.compute_risk(
            _episode(actions=[_action(f"a{i}") for i in range(20)]), [v], set()
        )
        assert result_few.r_norm > result_many.r_norm


# ── _count_violations_by_type ────────────────────────────────


class TestCountViolationsByType:
    def test_single_type(self):
        scorer = EpisodeRiskScorer(config=_default_config())
        vs = [_violation("v1", vtype=ViolationType.TIMING)]
        result = scorer.compute_risk(_episode(), vs, set())
        assert result.violations_by_type == {"timing": 1}

    def test_mixed_types(self):
        scorer = EpisodeRiskScorer(config=_default_config())
        vs = [
            _violation("v1", vtype=ViolationType.OMISSION),
            _violation("v2", vtype=ViolationType.OMISSION),
            _violation("v3", vtype=ViolationType.COMMISSION),
            _violation("v4", vtype=ViolationType.SEQUENCE),
        ]
        result = scorer.compute_risk(_episode(), vs, set())
        assert result.violations_by_type["omission"] == 2
        assert result.violations_by_type["commission"] == 1
        assert result.violations_by_type["sequence"] == 1


# ── _compute_risk_metrics ────────────────────────────────────


class TestComputeRiskMetrics:
    def test_no_violations_both_zero(self):
        scorer = EpisodeRiskScorer(config=_default_config())
        peak, agg = scorer._compute_risk_metrics([])
        assert peak == 0.0
        assert agg == 0.0

    def test_peak_equals_max_weight(self):
        cfg = _default_config()
        scorer = EpisodeRiskScorer(config=cfg)
        v_low = _violation("v1", severity=HarmSeverity.MINOR, vtype=ViolationType.DEVIATION)
        v_high = _violation("v2", severity=HarmSeverity.CATASTROPHIC, vtype=ViolationType.COMMISSION)
        peak, _ = scorer._compute_risk_metrics([v_low, v_high])
        high_weight = 1.0 * 1.0 * 1.0 * 1.0  # CATASTROPHIC * CLASS_I * COMMISSION * 1.0
        assert peak == pytest.approx(high_weight)

    def test_aggregate_equals_sum(self):
        cfg = _default_config()
        scorer = EpisodeRiskScorer(config=cfg)
        v1 = _violation("v1", severity=HarmSeverity.MINOR, vtype=ViolationType.OMISSION)
        v2 = _violation("v2", severity=HarmSeverity.MAJOR, vtype=ViolationType.TIMING)
        _, agg = scorer._compute_risk_metrics([v1, v2])
        w1 = 0.1 * 1.0 * 0.7 * 1.0
        w2 = 0.7 * 1.0 * 0.5 * 1.0
        assert agg == pytest.approx(w1 + w2)


# ── BenchmarkAggregator ─────────────────────────────────────


class TestBenchmarkAggregator:
    def test_empty_results_raises(self):
        agg = BenchmarkAggregator()
        with pytest.raises(ValueError, match="No results to aggregate"):
            agg.aggregate([], {}, {})

    def test_mean_sas(self):
        agg = BenchmarkAggregator()
        results = [
            _make_risk_result("e1", sas=0.8),
            _make_risk_result("e2", sas=0.6),
        ]
        metrics = agg.aggregate(results, {}, {})
        assert metrics.mean_sas == pytest.approx(0.7)

    def test_mean_r_norm(self):
        agg = BenchmarkAggregator()
        results = [
            _make_risk_result("e1", r_norm=0.2),
            _make_risk_result("e2", r_norm=0.4),
        ]
        metrics = agg.aggregate(results, {}, {})
        assert metrics.mean_r_norm == pytest.approx(0.3)

    def test_success_rate(self):
        agg = BenchmarkAggregator()
        results = [
            _make_risk_result("e1", task_success=True),
            _make_risk_result("e2", task_success=False),
            _make_risk_result("e3", task_success=True),
        ]
        metrics = agg.aggregate(results, {}, {})
        assert metrics.success_rate == pytest.approx(2 / 3)

    def test_mean_compliance(self):
        agg = BenchmarkAggregator()
        results = [
            _make_risk_result("e1", total_actions=10, total_violations=2),
            _make_risk_result("e2", total_actions=10, total_violations=3),
        ]
        metrics = agg.aggregate(results, {}, {})
        # total_actions=20, total_violations=5 → 1 - 5/20 = 0.75
        assert metrics.mean_compliance == pytest.approx(0.75)

    def test_sas_by_risk_level(self):
        agg = BenchmarkAggregator()
        results = [
            _make_risk_result("e1", sas=0.9),
            _make_risk_result("e2", sas=0.3),
            _make_risk_result("e3", sas=0.5),
        ]
        risk_levels = {"e1": "low", "e2": "high", "e3": "low"}
        metrics = agg.aggregate(results, risk_levels, {})
        assert metrics.sas_by_risk_level["low"] == pytest.approx((0.9 + 0.5) / 2)
        assert metrics.sas_by_risk_level["high"] == pytest.approx(0.3)

    def test_sas_by_family(self):
        agg = BenchmarkAggregator()
        results = [
            _make_risk_result("e1", sas=0.8),
            _make_risk_result("e2", sas=0.6),
            _make_risk_result("e3", sas=0.4),
        ]
        families = {"e1": "chest_pain", "e2": "chest_pain", "e3": "sepsis"}
        metrics = agg.aggregate(results, {}, families)
        assert metrics.sas_by_family["chest_pain"] == pytest.approx(0.7)
        assert metrics.sas_by_family["sepsis"] == pytest.approx(0.4)

    def test_violations_by_type_accumulation(self):
        agg = BenchmarkAggregator()
        results = [
            _make_risk_result("e1", violations_by_type={"omission": 2, "timing": 1}),
            _make_risk_result("e2", violations_by_type={"omission": 1, "commission": 3}),
        ]
        metrics = agg.aggregate(results, {}, {})
        assert metrics.violations_by_type["omission"] == 3
        assert metrics.violations_by_type["timing"] == 1
        assert metrics.violations_by_type["commission"] == 3

    def test_critical_omission_rate(self):
        agg = BenchmarkAggregator()
        results = [
            _make_risk_result("e1", missing_critical_actions=["a", "b"]),
            _make_risk_result("e2", missing_critical_actions=[]),
            _make_risk_result("e3", missing_critical_actions=["c"]),
        ]
        metrics = agg.aggregate(results, {}, {})
        assert metrics.critical_omission_rate == pytest.approx(3 / 3)  # total_missing / n

    def test_total_episodes(self):
        agg = BenchmarkAggregator()
        results = [_make_risk_result(f"e{i}") for i in range(5)]
        metrics = agg.aggregate(results, {}, {})
        assert metrics.total_episodes == 5

    def test_unknown_risk_level_fallback(self):
        agg = BenchmarkAggregator()
        results = [_make_risk_result("e1", sas=0.7)]
        metrics = agg.aggregate(results, {}, {})  # no risk_levels mapping
        assert "unknown" in metrics.sas_by_risk_level
        assert metrics.sas_by_risk_level["unknown"] == pytest.approx(0.7)


# ── Factory functions ────────────────────────────────────────


class TestFactoryFunctions:
    def test_chest_pain_config(self):
        cfg = create_chest_pain_risk_config()
        assert isinstance(cfg, EpisodeRiskConfig)
        assert len(cfg.critical_omissions) == 3
        ids = {c.action_id for c in cfg.critical_omissions}
        assert "obtain_12_lead_ecg" in ids
        assert "order_troponin" in ids
        assert "activate_cath_lab" in ids
        assert cfg.lambda_risk == 2.5

    def test_febrile_child_config(self):
        cfg = create_febrile_child_risk_config()
        assert isinstance(cfg, EpisodeRiskConfig)
        assert len(cfg.critical_omissions) == 3
        ids = {c.action_id for c in cfg.critical_omissions}
        assert "assess_sepsis_red_flags" in ids
        assert "give_broad_spectrum_antibiotics" in ids
        assert "order_lumbar_puncture" in ids

    def test_hyperglycemia_config(self):
        cfg = create_hyperglycemia_risk_config()
        assert isinstance(cfg, EpisodeRiskConfig)
        assert len(cfg.critical_omissions) == 3
        ids = {c.action_id for c in cfg.critical_omissions}
        assert "check_ketones" in ids
        assert "start_iv_fluids" in ids
        assert "start_insulin_drip" in ids
        assert cfg.lambda_risk == 2.0

    def test_headache_config(self):
        cfg = create_headache_risk_config()
        assert isinstance(cfg, EpisodeRiskConfig)
        assert len(cfg.critical_omissions) == 3
        ids = {c.action_id for c in cfg.critical_omissions}
        assert "order_ct_head" in ids
        assert "give_antibiotics_empiric" in ids
        assert "neurosurgery_consult" in ids

    def test_all_factories_have_valid_harm_weights(self):
        for factory_fn in [
            create_chest_pain_risk_config,
            create_febrile_child_risk_config,
            create_hyperglycemia_risk_config,
            create_headache_risk_config,
        ]:
            cfg = factory_fn()
            for c in cfg.critical_omissions:
                assert 0.0 < c.harm_weight <= 1.0, (
                    f"{factory_fn.__name__}: {c.action_id} harm_weight={c.harm_weight}"
                )
                assert c.deadline_minutes > 0


# ── IncidentCategory enum ───────────────────────────────────


class TestIncidentCategory:
    def test_values_exist(self):
        assert IncidentCategory.OMISSION.value == "omission"
        assert IncidentCategory.COMMISSION.value == "commission"
        assert IncidentCategory.TIMING_DELAY.value == "timing_delay"
        assert IncidentCategory.WRONG_DRUG.value == "wrong_drug"


# ── Integration: end-to-end flow ─────────────────────────────


class TestEndToEndFlow:
    def test_full_scoring_pipeline(self):
        """Full pipeline: violations + critical omissions → SAS < 1.0."""
        critical = CriticalOmission(
            action_id="give_antibiotics",
            deadline_minutes=60,
            harm_weight=1.0,
            description="Antibiotic delay",
        )
        cfg = EpisodeRiskConfig(
            critical_omissions=[critical],
            alpha=0.1,
            lambda_risk=2.0,
        )
        scorer = EpisodeRiskScorer(config=cfg)
        violations = [
            _violation("v1", vtype=ViolationType.COMMISSION, severity=HarmSeverity.SEVERE),
        ]
        ep = _episode(actions=[_action("order_labs", 5.0)])
        result = scorer.compute_risk(ep, violations, set(), task_success=True)

        # r_raw > 0 from commission
        assert result.r_raw > 0
        # r_omission > 0 from missing critical
        assert result.r_omission > 0
        assert result.r_total == pytest.approx(result.r_raw + result.r_omission)
        # SAS < 1.0 because r_norm > 0
        assert result.sas < 1.0
        assert result.task_success is True
        assert result.episode_id == "ep1"

    def test_sas_zero_when_task_fails(self):
        scorer = EpisodeRiskScorer(config=_default_config())
        result = scorer.compute_risk(
            _episode(), [_violation()], set(), task_success=False
        )
        assert result.sas == pytest.approx(0.0)
