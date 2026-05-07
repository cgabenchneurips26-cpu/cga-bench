"""Tests for ExpectedActionsGuard: SHA-256 integrity + sentinel leakage detection."""

import copy
import hashlib
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pytest

from cga_bench.assessor_core.expected_actions_guard import ExpectedActionsGuard


@dataclass
class MockScenario:
    """Minimal mock of ExternalScenario for testing."""

    expected_actions: List[str]
    expected_actions_cpg: Optional[List[str]] = None
    original_expected_hash: Optional[str] = None
    _expected_actions_original: Optional[List[str]] = None


# ---------------------------------------------------------------------------
# SHA-256 Hash Integrity
# ---------------------------------------------------------------------------


class TestHashPreservation:
    """E7: SHA-256 hash preservation across evaluation."""

    def test_hash_preservation_across_evaluation(self):
        """Verify hash is set and matches after no modification."""
        scenario = MockScenario(
            expected_actions=["order_lab_lactate", "give_antibiotics"]
        )
        ExpectedActionsGuard.preserve_original(scenario)

        assert scenario.original_expected_hash is not None
        assert len(scenario.original_expected_hash) == 64  # SHA-256 hex

        # No modification → integrity should hold
        assert ExpectedActionsGuard.verify_integrity(scenario) is True

    def test_hash_detects_modification(self):
        """Verify hash detects tampering."""
        scenario = MockScenario(
            expected_actions=["order_lab_lactate", "give_antibiotics"]
        )
        ExpectedActionsGuard.preserve_original(scenario)

        # Tamper with expected_actions
        scenario.expected_actions.append("INJECTED_ACTION")

        assert ExpectedActionsGuard.verify_integrity(scenario) is False

    def test_hash_detects_reordering(self):
        """Verify hash detects list reordering."""
        scenario = MockScenario(
            expected_actions=["action_a", "action_b", "action_c"]
        )
        ExpectedActionsGuard.preserve_original(scenario)

        # Reverse order
        scenario.expected_actions.reverse()

        assert ExpectedActionsGuard.verify_integrity(scenario) is False

    def test_hash_detects_removal(self):
        """Verify hash detects element removal."""
        scenario = MockScenario(
            expected_actions=["action_a", "action_b"]
        )
        ExpectedActionsGuard.preserve_original(scenario)

        scenario.expected_actions.pop()

        assert ExpectedActionsGuard.verify_integrity(scenario) is False

    def test_deepcopy_isolation(self):
        """Verify deepcopy creates independent copy."""
        original_list = ["action_a", "action_b"]
        scenario = MockScenario(expected_actions=original_list)
        ExpectedActionsGuard.preserve_original(scenario)

        # Modify original list directly
        original_list.append("mutation")

        # The preserved copy should NOT be affected
        assert "mutation" not in scenario._expected_actions_original

    def test_no_hash_stored_returns_true(self):
        """When no hash was stored, verify_integrity returns True (skip)."""
        scenario = MockScenario(expected_actions=["x"])
        assert ExpectedActionsGuard.verify_integrity(scenario) is True

    def test_hash_determinism(self):
        """Same input always produces same hash."""
        scenario1 = MockScenario(expected_actions=["a", "b", "c"])
        scenario2 = MockScenario(expected_actions=["a", "b", "c"])

        ExpectedActionsGuard.preserve_original(scenario1)
        ExpectedActionsGuard.preserve_original(scenario2)

        assert scenario1.original_expected_hash == scenario2.original_expected_hash


# ---------------------------------------------------------------------------
# Sentinel Injection + Leakage Detection
# ---------------------------------------------------------------------------


class TestSentinelLeakage:
    """E8: Sentinel leakage detection."""

    def test_sentinel_injection(self):
        """Verify sentinel is appended to action list."""
        actions = ["assess_vital_signs", "order_lab_cbc"]
        injected = ExpectedActionsGuard.inject_sentinel(actions)

        assert len(injected) == len(actions) + 1
        assert injected[-1] == ExpectedActionsGuard._SENTINEL
        # Original should be unchanged
        assert len(actions) == 2

    def test_no_leakage_in_clean_scenario(self):
        """No sentinel in clean inputs → leaked=False."""
        result = ExpectedActionsGuard.detect_leakage(
            prompt="Evaluate the patient",
            action_space=["assess_vital_signs", "order_lab"],
            context="Sepsis scenario",
        )
        assert result["leaked"] is False
        assert result["leakage_points"] == []

    def test_leakage_in_prompt(self):
        """Sentinel found in prompt → leaked=True."""
        sentinel = ExpectedActionsGuard._SENTINEL
        result = ExpectedActionsGuard.detect_leakage(
            prompt=f"Do this: {sentinel}",
            action_space=[],
            context="",
        )
        assert result["leaked"] is True
        assert "prompt" in result["leakage_points"]

    def test_leakage_in_action_space(self):
        """Sentinel found in action_space → leaked=True."""
        sentinel = ExpectedActionsGuard._SENTINEL
        result = ExpectedActionsGuard.detect_leakage(
            prompt="",
            action_space=["action_a", sentinel, "action_b"],
            context="",
        )
        assert result["leaked"] is True
        assert "action_space" in result["leakage_points"]

    def test_leakage_in_context(self):
        """Sentinel found in context → leaked=True."""
        sentinel = ExpectedActionsGuard._SENTINEL
        result = ExpectedActionsGuard.detect_leakage(
            prompt="",
            action_space=[],
            context=f"some info {sentinel} more info",
        )
        assert result["leaked"] is True
        assert "context" in result["leakage_points"]

    def test_leakage_multiple_points(self):
        """Sentinel in multiple places → all listed."""
        sentinel = ExpectedActionsGuard._SENTINEL
        result = ExpectedActionsGuard.detect_leakage(
            prompt=sentinel,
            action_space=[sentinel],
            context=sentinel,
        )
        assert result["leaked"] is True
        assert len(result["leakage_points"]) == 3

    def test_sentinel_value_returned(self):
        """detect_leakage returns the sentinel value for inspection."""
        result = ExpectedActionsGuard.detect_leakage()
        assert result["sentinel_value"] == ExpectedActionsGuard._SENTINEL


# ---------------------------------------------------------------------------
# Prevent Overwrite
# ---------------------------------------------------------------------------


class TestPreventOverwrite:
    """Guard prevents CPG output from overwriting expected_actions."""

    def test_cpg_source_stores_separately(self):
        """source='cpg' stores in expected_actions_cpg, not expected_actions."""
        scenario = MockScenario(
            expected_actions=["benchmark_action_1", "benchmark_action_2"]
        )
        cpg_actions = ["cpg_action_1", "cpg_action_2"]

        ExpectedActionsGuard.prevent_overwrite(scenario, cpg_actions, source="cpg")

        # expected_actions untouched
        assert scenario.expected_actions == ["benchmark_action_1", "benchmark_action_2"]
        # CPG actions stored separately
        assert scenario.expected_actions_cpg == cpg_actions

    def test_non_cpg_source_raises(self):
        """source != 'cpg' raises ValueError."""
        scenario = MockScenario(expected_actions=["a"])

        with pytest.raises(ValueError, match="unexpected source"):
            ExpectedActionsGuard.prevent_overwrite(
                scenario, ["new_action"], source="benchmark"
            )


# ---------------------------------------------------------------------------
# Integration: Full Pipeline Guard
# ---------------------------------------------------------------------------


class TestFullPipelineGuard:
    """Integration test combining hash + sentinel + prevent_overwrite."""

    def test_full_guard_pipeline(self):
        """Simulate a full evaluation pipeline with all guards active."""
        # 1. Create scenario
        scenario = MockScenario(
            expected_actions=["order_lab_blood_culture", "give_antibiotics"]
        )

        # 2. Preserve original
        ExpectedActionsGuard.preserve_original(scenario)
        original_hash = scenario.original_expected_hash

        # 3. Generate CPG actions (stored separately)
        cpg_actions = ["assess_vital_signs", "order_lab_lactate"]
        ExpectedActionsGuard.prevent_overwrite(scenario, cpg_actions, source="cpg")

        # 4. Inject sentinel for leakage test
        sentinel_actions = ExpectedActionsGuard.inject_sentinel(cpg_actions)

        # 5. Verify no leakage
        leakage = ExpectedActionsGuard.detect_leakage(
            prompt="Evaluate the patient.",
            action_space=["assess_vital_signs", "order_lab"],
            context="Clinical scenario",
        )
        assert leakage["leaked"] is False

        # 6. Verify integrity
        assert ExpectedActionsGuard.verify_integrity(scenario) is True
        assert scenario.original_expected_hash == original_hash
