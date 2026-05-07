from __future__ import annotations

from typing import cast

from ...semantic_layer.evidence.counterfactual import (
    CounterfactualConfig,
    CounterfactualExplanation,
    ThresholdRule,
    clear_threshold_rules_cache,
    extract_threshold_rules,
    format_counterfactual_text,
    generate_counterfactuals,
    load_all_threshold_rules,
)
from ...semantic_layer.evidence.event_injection import (
    EventInjectionConfig,
    InjectedEvent,
    PlanRepairMetrics,
    apply_event_to_state,
    evaluate_plan_repair,
    select_events,
)


class TestThresholdRules:
    def test_common_rules_exist(self):
        rules = extract_threshold_rules({})
        assert any(r.vital == "map_mmhg" and r.threshold == 65.0 for r in rules)
        assert any(r.vital == "oxygen_saturation" and r.operator == "lt" for r in rules)

    def test_extract_from_precondition_expression(self):
        graph_data = {
            "graph_id": "test_graph",
            "nodes": {
                "n1": {
                    "source_guideline": "Test Guideline",
                    "precondition": "state.vitals.map_mmhg < 65",
                    "mandatory_actions": ["start_vasopressor"],
                }
            },
        }
        rules = extract_threshold_rules(graph_data)
        assert any(
            r.guideline_id == "test_graph"
            and r.vital == "map_mmhg"
            and r.operator == "lt"
            and r.action_if_true == "start_vasopressor"
            for r in rules
        )

    def test_extract_from_conditional_next_expression(self):
        graph_data = {
            "graph_id": "test_graph",
            "nodes": {
                "n1": {
                    "source_guideline": "Test Guideline",
                    "mandatory_actions": ["escalate_to_icu"],
                    "conditional_next": {"state.vitals.lactate > 2.5": "icu_path"},
                }
            },
        }
        rules = extract_threshold_rules(graph_data)
        assert any(
            r.vital == "lactate"
            and r.threshold == 2.5
            and r.operator == "gt"
            and r.action_if_true == "escalate_to_icu"
            for r in rules
        )


class TestLoadAllThresholdRules:
    def setup_method(self):
        clear_threshold_rules_cache()

    def teardown_method(self):
        clear_threshold_rules_cache()

    def test_returns_at_least_fallback_count(self):
        rules = load_all_threshold_rules()
        assert len(rules) >= 8

    def test_includes_fallback_rules(self):
        rules = load_all_threshold_rules()
        vitals = {r.vital for r in rules}
        assert "map_mmhg" in vitals
        assert "oxygen_saturation" in vitals
        assert "gcs" in vitals

    def test_extracts_rules_from_real_yaml_graphs(self):
        rules = load_all_threshold_rules()
        graph_sourced = [r for r in rules if r.guideline_id != "ssc_sepsis_hour1"
                         and r.guideline_id != "aha_chest_pain"
                         and r.guideline_id != "universal"
                         and r.guideline_id != "ada_dka"
                         and r.guideline_id != "aha_stroke"]
        if graph_sourced:
            assert any(r.guideline_id != "unknown" for r in graph_sourced)

    def test_caching_returns_same_content(self):
        first = load_all_threshold_rules()
        second = load_all_threshold_rules()
        assert len(first) == len(second)

    def test_cache_cleared_properly(self):
        load_all_threshold_rules()
        clear_threshold_rules_cache()
        rules = load_all_threshold_rules()
        assert len(rules) >= 8

    def test_no_duplicate_rules(self):
        rules = load_all_threshold_rules()
        keys = [
            (r.vital, r.threshold, r.operator, r.action_if_true, r.action_if_false, r.guideline_id)
            for r in rules
        ]
        assert len(keys) == len(set(keys))

    def test_nonexistent_dir_returns_fallback(self):
        from pathlib import Path
        rules = load_all_threshold_rules(graphs_dir=Path("/tmp/nonexistent_cpg_graphs"))
        assert len(rules) == 8


class TestGenerateCounterfactuals:
    def test_near_threshold_produces_counterfactual(self):
        state = {"vitals": {"map_mmhg": 64.5}}
        rules = [
            ThresholdRule(
                vital="map_mmhg",
                threshold=65.0,
                operator="lt",
                action_if_true="start_vasopressor_norepinephrine",
                action_if_false="monitor_map",
                guideline_id="ssc_sepsis_hour1",
                source="SSC 2021",
            )
        ]
        cfs = generate_counterfactuals(state, ["start_vasopressor_norepinephrine"], rules)
        assert len(cfs) == 1
        assert cfs[0]["counterfactual_action"] == "monitor_map"
        assert 0.0 <= cfs[0]["sensitivity"] <= 1.0

    def test_far_from_threshold_does_not_produce_counterfactual(self):
        state = {"vitals": {"map_mmhg": 40.0}}
        rules = [
            ThresholdRule(
                vital="map_mmhg",
                threshold=65.0,
                operator="lt",
                action_if_true="start_vasopressor_norepinephrine",
                action_if_false="monitor_map",
                guideline_id="ssc_sepsis_hour1",
                source="SSC 2021",
            )
        ]
        cfs = generate_counterfactuals(state, [], rules)
        assert cfs == []

    def test_flat_patient_state_supported(self):
        state = {"temperature": 38.4}
        rules = [
            ThresholdRule(
                vital="temperature",
                threshold=38.3,
                operator="gt",
                action_if_true="assess_fever_source",
                action_if_false="monitor_temperature",
                guideline_id="ssc_sepsis_hour1",
                source="SSC 2021",
            )
        ]
        cfs = generate_counterfactuals(state, [], rules)
        assert len(cfs) == 1
        assert cfs[0]["original_action"] in {"assess_fever_source", "monitor_temperature"}

    def test_empty_rules_returns_empty(self):
        assert generate_counterfactuals({"vitals": {"map_mmhg": 65.0}}, [], []) == []

    def test_respects_max_counterfactuals(self):
        state = {"vitals": {"map_mmhg": 65.0, "heart_rate": 100.0, "oxygen_saturation": 94.0}}
        rules = [
            ThresholdRule("map_mmhg", 65.0, "lt", "a1", "b1", "g", "s"),
            ThresholdRule("heart_rate", 100.0, "gt", "a2", "b2", "g", "s"),
            ThresholdRule("oxygen_saturation", 94.0, "lt", "a3", "b3", "g", "s"),
        ]
        cfg = CounterfactualConfig(perturbation_range=0.2, max_counterfactuals=2, min_sensitivity=0.0)
        cfs = generate_counterfactuals(state, [], rules, config=cfg)
        assert len(cfs) == 2

    def test_min_sensitivity_filters_results(self):
        state = {"vitals": {"map_mmhg": 77.9}}
        rules = [ThresholdRule("map_mmhg", 65.0, "lt", "a", "b", "g", "s")]
        cfg = CounterfactualConfig(perturbation_range=0.2, max_counterfactuals=5, min_sensitivity=0.9)
        cfs = generate_counterfactuals(state, [], rules, config=cfg)
        assert cfs == []


class TestCounterfactualFormatting:
    def test_format_counterfactual_text(self):
        cf = cast(dict[str, object], {
            "condition": {"vital": "map_mmhg", "value": 65.1},
            "original_action": "start_vasopressor_norepinephrine",
            "counterfactual_action": "monitor_map",
            "reason": "test",
            "sensitivity": 0.88,
        })
        text = format_counterfactual_text(cast(CounterfactualExplanation, cast(object, cf)))
        assert "map_mmhg" in text
        assert "start_vasopressor_norepinephrine" in text
        assert "monitor_map" in text


class TestEventInjectionConfig:
    def test_default_factory(self):
        cfg = EventInjectionConfig.default()
        assert cfg.enabled is False
        assert cfg.max_events_per_episode == 3

    def test_stress_test_factory(self):
        cfg = EventInjectionConfig.stress_test()
        assert cfg.enabled is True
        assert cfg.max_events_per_episode == 5
        assert cfg.min_interval_minutes == 5.0


class TestSelectEvents:
    def test_disabled_config_returns_empty(self):
        cfg = EventInjectionConfig(enabled=False)
        assert select_events(cfg, episode_duration_minutes=60.0, seed=7) == []

    def test_zero_duration_returns_empty(self):
        cfg = EventInjectionConfig(enabled=True)
        assert select_events(cfg, episode_duration_minutes=0.0, seed=1) == []

    def test_respects_max_events(self):
        cfg = EventInjectionConfig(enabled=True, max_events_per_episode=2, min_interval_minutes=1.0)
        events = select_events(cfg, episode_duration_minutes=60.0, seed=3)
        assert len(events) <= 2

    def test_respects_min_interval(self):
        cfg = EventInjectionConfig(enabled=True, max_events_per_episode=4, min_interval_minutes=12.0)
        events = select_events(cfg, episode_duration_minutes=60.0, seed=10)
        for i in range(1, len(events)):
            delta = events[i]["timestamp_minutes"] - events[i - 1]["timestamp_minutes"]
            assert delta >= 12.0

    def test_deterministic_with_seed(self):
        cfg = EventInjectionConfig(enabled=True, max_events_per_episode=3, min_interval_minutes=10.0)
        first = select_events(cfg, episode_duration_minutes=60.0, seed=42)
        second = select_events(cfg, episode_duration_minutes=60.0, seed=42)
        assert first == second


class TestApplyEventToState:
    def test_returns_new_dict(self):
        state: dict[str, object] = {"vitals": {"map_mmhg": 68.0}, "allergies": []}
        event: InjectedEvent = {
            "event_id": "vital_crash_bp",
            "event_type": "vital_deterioration",
            "severity": "critical",
            "description": "drop",
            "state_changes": {"map_mmhg": 45.0},
            "expected_response": "start_vasopressor_norepinephrine",
            "timestamp_minutes": 0.0,
        }
        new_state = apply_event_to_state(state, event, current_time_minutes=8.0)
        assert new_state is not state
        assert cast(dict[str, float], state["vitals"])["map_mmhg"] == 68.0
        assert cast(dict[str, float], new_state["vitals"])["map_mmhg"] == 45.0

    def test_allergies_are_merged_without_duplicates(self):
        state: dict[str, object] = {"allergies": ["latex"]}
        event: InjectedEvent = {
            "event_id": "allergy_pcn",
            "event_type": "allergy_discovery",
            "severity": "severe",
            "description": "allergy",
            "state_changes": {"allergies": ["penicillin", "latex"]},
            "expected_response": "switch_to_alternative_antibiotic",
            "timestamp_minutes": 0.0,
        }
        new_state = apply_event_to_state(state, event, current_time_minutes=3.0)
        assert sorted(cast(list[str], new_state["allergies"])) == ["latex", "penicillin"]


class TestPlanRepairMetrics:
    def test_properties(self):
        metrics = PlanRepairMetrics(total_events=2, correct_responses=1, response_time_minutes=[4.0, 6.0])
        assert metrics.repair_success_rate == 0.5
        assert metrics.avg_response_time == 5.0

    def test_summary_shape(self):
        metrics = PlanRepairMetrics(total_events=1, correct_responses=1, response_time_minutes=[2.0])
        summary = metrics.summary()
        assert summary["total_events"] == 1
        assert summary["correct_responses"] == 1
        assert "repair_success_rate" in summary


class TestEvaluatePlanRepair:
    def test_correct_vs_incorrect_response_count(self):
        events: list[InjectedEvent] = [
            {
                "event_id": "e1",
                "event_type": "vital_deterioration",
                "severity": "critical",
                "description": "bp drop",
                "state_changes": {"map_mmhg": 45.0},
                "expected_response": "start_vasopressor_norepinephrine",
                "timestamp_minutes": 5.0,
            },
            {
                "event_id": "e2",
                "event_type": "allergy_discovery",
                "severity": "severe",
                "description": "allergy",
                "state_changes": {"allergies": ["penicillin"]},
                "expected_response": "switch_to_alternative_antibiotic",
                "timestamp_minutes": 20.0,
            },
        ]
        responses = [
            {"timestamp_minutes": 7.0, "action_id": "start_vasopressor_norepinephrine"},
            {"timestamp_minutes": 22.0, "action_id": "order_lab_lactate"},
        ]
        metrics = evaluate_plan_repair(events, responses)
        assert metrics.total_events == 2
        assert metrics.correct_responses == 1
        assert len(metrics.response_time_minutes) == 2

    def test_counts_safety_violations_post_event(self):
        events: list[InjectedEvent] = [
            {
                "event_id": "e1",
                "event_type": "drug_interaction",
                "severity": "moderate",
                "description": "interaction",
                "state_changes": {"drug_interaction_alert": True},
                "expected_response": "review_medication_order",
                "timestamp_minutes": 10.0,
            }
        ]
        responses = [
            {
                "timestamp_minutes": 11.0,
                "actions": [{"action_id": "review_medication_order"}],
                "safety_violation": True,
            }
        ]
        metrics = evaluate_plan_repair(events, responses)
        assert metrics.correct_responses == 1
        assert metrics.safety_violations_post_event == 1

    def test_empty_events(self):
        metrics = evaluate_plan_repair([], [{"timestamp_minutes": 1.0, "action_id": "x"}])
        assert metrics.total_events == 0
        assert metrics.correct_responses == 0

    def test_missing_post_event_response(self):
        events: list[InjectedEvent] = [
            {
                "event_id": "e1",
                "event_type": "new_symptom",
                "severity": "severe",
                "description": "new pain",
                "state_changes": {"chest_pain": True},
                "expected_response": "activate_cath_lab",
                "timestamp_minutes": 15.0,
            }
        ]
        responses = [{"timestamp_minutes": 10.0, "action_id": "order_ecg"}]
        metrics = evaluate_plan_repair(events, responses)
        assert metrics.correct_responses == 0
        assert metrics.response_time_minutes == []
