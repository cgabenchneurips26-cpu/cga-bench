"""Tests for Experiment A: Outcome-Preserving Perturbation."""
from __future__ import annotations

import pytest

from cga_bench.cpg_model.schemas.base import (
    Action,
    ActionType,
    EpisodeLog,
    PatientState,
    VitalSigns,
)
from cga_bench.eval_harness.experiments.perturbation import (
    EpisodePerturbator,
    PerturbationType,
    TaskCompletionMetric,
    SCENARIO_PERTURBATION_MAP,
)


@pytest.fixture()
def sample_episode() -> EpisodeLog:
    """Create a sample episode for testing."""
    state = PatientState(
        state_id="test_state",
        age=65,
        sex="M",
        vitals=VitalSigns(heart_rate=110.0, map_mmhg=65.0),
        chief_complaint="septic shock",
    )
    actions = [
        Action(
            type=ActionType.ORDER_LAB,
            action_id="order_lab_blood_culture",
            args={},
            timestamp_minutes=5.0,
        ),
        Action(
            type=ActionType.GIVE_MEDICATION,
            action_id="give_broad_spectrum_antibiotics",
            args={},
            timestamp_minutes=15.0,
        ),
        Action(
            type=ActionType.ORDER_LAB,
            action_id="order_lab_lactate",
            args={},
            timestamp_minutes=10.0,
        ),
        Action(
            type=ActionType.GIVE_MEDICATION,
            action_id="give_crystalloid_30ml_kg",
            args={},
            timestamp_minutes=20.0,
        ),
        Action(
            type=ActionType.GIVE_MEDICATION,
            action_id="start_vasopressor_norepinephrine",
            args={},
            timestamp_minutes=30.0,
        ),
    ]
    return EpisodeLog(
        episode_id="test_episode",
        scenario_id="septic_shock_basic",
        agent_id="test_agent",
        states=[state],
        actions=actions,
        observations=[],
        total_duration_minutes=60.0,
        total_llm_calls=0,
        total_tokens=0,
        total_tool_calls=0,
        termination_reason="success",
    )


@pytest.fixture()
def perturbator() -> EpisodePerturbator:
    return EpisodePerturbator()


class TestEpisodePerturbator:
    """Test perturbation methods."""

    def test_delay_action_increases_timestamp(
        self, perturbator: EpisodePerturbator, sample_episode: EpisodeLog
    ) -> None:
        """P1: Delayed action should have later timestamp."""
        original_time = next(
            a.timestamp_minutes
            for a in sample_episode.actions
            if a.action_id == "start_vasopressor_norepinephrine"
        )
        perturbed = perturbator.delay_action(
            sample_episode, "start_vasopressor_norepinephrine", 30
        )
        new_time = next(
            a.timestamp_minutes
            for a in perturbed.actions
            if a.action_id == "start_vasopressor_norepinephrine"
        )
        assert new_time == original_time + 30

    def test_delay_preserves_other_actions(
        self, perturbator: EpisodePerturbator, sample_episode: EpisodeLog
    ) -> None:
        """P1: Other actions should be unchanged."""
        perturbed = perturbator.delay_action(
            sample_episode, "start_vasopressor_norepinephrine", 30
        )
        original_ids = {a.action_id for a in sample_episode.actions}
        perturbed_ids = {a.action_id for a in perturbed.actions}
        assert original_ids == perturbed_ids

    def test_swap_order_exchanges_timestamps(
        self, perturbator: EpisodePerturbator, sample_episode: EpisodeLog
    ) -> None:
        """P2: Swapped actions should have exchanged timestamps."""
        perturbed = perturbator.swap_order(
            sample_episode,
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
        )
        culture_time = next(
            a.timestamp_minutes
            for a in perturbed.actions
            if a.action_id == "order_lab_blood_culture"
        )
        abx_time = next(
            a.timestamp_minutes
            for a in perturbed.actions
            if a.action_id == "give_broad_spectrum_antibiotics"
        )
        # Original: culture=5, abx=15 → swapped: culture=15, abx=5
        assert culture_time == 15.0
        assert abx_time == 5.0

    def test_remove_action_decreases_count(
        self, perturbator: EpisodePerturbator, sample_episode: EpisodeLog
    ) -> None:
        """P3: Removed action should reduce count by 1."""
        original_count = len(sample_episode.actions)
        perturbed = perturbator.remove_action(sample_episode, "order_lab_lactate")
        assert len(perturbed.actions) == original_count - 1
        assert "order_lab_lactate" not in {a.action_id for a in perturbed.actions}

    def test_add_action_increases_count(
        self, perturbator: EpisodePerturbator, sample_episode: EpisodeLog
    ) -> None:
        """P4: Added action should increase count by 1."""
        original_count = len(sample_episode.actions)
        perturbed = perturbator.add_action(
            sample_episode, "order_imaging_ct_head", 25.0
        )
        assert len(perturbed.actions) == original_count + 1
        assert "order_imaging_ct_head" in {a.action_id for a in perturbed.actions}

    def test_add_contraindicated_increases_count(
        self, perturbator: EpisodePerturbator, sample_episode: EpisodeLog
    ) -> None:
        """P5: Contraindicated action should increase count by 1."""
        original_count = len(sample_episode.actions)
        perturbed = perturbator.add_contraindicated(
            sample_episode, "discharge_home", 25.0
        )
        assert len(perturbed.actions) == original_count + 1
        assert "discharge_home" in {a.action_id for a in perturbed.actions}

    def test_perturbation_does_not_mutate_original(
        self, perturbator: EpisodePerturbator, sample_episode: EpisodeLog
    ) -> None:
        """Perturbation should create a deep copy, not mutate original."""
        original_count = len(sample_episode.actions)
        original_times = [a.timestamp_minutes for a in sample_episode.actions]

        perturbator.delay_action(sample_episode, "order_lab_lactate", 100)
        perturbator.remove_action(sample_episode, "order_lab_lactate")

        assert len(sample_episode.actions) == original_count
        assert [a.timestamp_minutes for a in sample_episode.actions] == original_times

    def test_actions_sorted_after_perturbation(
        self, perturbator: EpisodePerturbator, sample_episode: EpisodeLog
    ) -> None:
        """Actions should be chronologically sorted after perturbation."""
        perturbed = perturbator.delay_action(
            sample_episode, "order_lab_blood_culture", 50
        )
        times = [a.timestamp_minutes for a in perturbed.actions]
        assert times == sorted(times)


class TestTaskCompletionMetric:
    """Test the simple task completion metric."""

    def test_all_mandatory_present(self) -> None:
        mandatory = {"order_lab_lactate", "order_lab_blood_culture", "give_broad_spectrum_antibiotics"}
        performed = {"order_lab_lactate", "order_lab_blood_culture", "give_broad_spectrum_antibiotics", "extra_action"}
        metric = TaskCompletionMetric()
        assert metric.evaluate(performed, mandatory) is True

    def test_mandatory_missing(self) -> None:
        mandatory = {"order_lab_lactate", "order_lab_blood_culture"}
        performed = {"order_lab_lactate"}
        metric = TaskCompletionMetric()
        assert metric.evaluate(performed, mandatory) is False

    def test_empty_mandatory(self) -> None:
        metric = TaskCompletionMetric()
        assert metric.evaluate({"some_action"}, set()) is True


class TestScenarioPerturbationMap:
    """Test scenario perturbation mappings completeness."""

    def test_all_8_scenarios_have_mappings(self) -> None:
        assert len(SCENARIO_PERTURBATION_MAP) == 8

    def test_each_scenario_has_5_perturbations(self) -> None:
        for scenario_id, pmap in SCENARIO_PERTURBATION_MAP.items():
            for ptype in PerturbationType:
                assert ptype.value in pmap, (
                    f"Missing {ptype.value} for {scenario_id}"
                )

    def test_delay_perturbations_have_required_fields(self) -> None:
        for scenario_id, pmap in SCENARIO_PERTURBATION_MAP.items():
            delay = pmap["P1_delay"]
            assert "action_id" in delay
            assert "delay_minutes" in delay
            assert delay["delay_minutes"] > 0

    def test_swap_perturbations_have_two_actions(self) -> None:
        for scenario_id, pmap in SCENARIO_PERTURBATION_MAP.items():
            swap = pmap["P2_swap_order"]
            assert "action_id_1" in swap
            assert "action_id_2" in swap
            assert swap["action_id_1"] != swap["action_id_2"]
