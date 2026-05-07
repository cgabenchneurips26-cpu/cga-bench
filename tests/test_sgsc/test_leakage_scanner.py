"""Tests for sgsc.audit.leakage_scanner — private field leakage detection."""

from __future__ import annotations

from sgsc.audit.leakage_scanner import (
    scan_public_scenarios,
    scan_scenario_for_leakage,
    scan_scenarios,
)


class TestScanScenarioForLeakage:
    """Tests for scan_scenario_for_leakage."""

    def test_clean_scenario_no_leaks(self) -> None:
        scenario = {
            "scenario_id": "test_001",
            "description": "A clean patient scenario",
            "actions": ["give_medication", "order_lab"],
            "patient": {"age": 65, "diagnosis": "sepsis"},
        }
        leaks = scan_scenario_for_leakage(scenario, "test_001")
        assert leaks == []

    def test_activated_constraint_id_detected(self) -> None:
        scenario = {
            "scenario_id": "test_002",
            "description": "This has activated_constraint_id leakage",
        }
        leaks = scan_scenario_for_leakage(scenario, "test_002")
        assert len(leaks) == 1
        assert leaks[0]["pattern"] == "activated_constraint_id"

    def test_expected_trace_family_detected(self) -> None:
        scenario = {
            "actions": ["do_something"],
            "hint": "expected_trace_family is sepsis_compliant",
        }
        leaks = scan_scenario_for_leakage(scenario, "test_003")
        assert len(leaks) == 1
        assert leaks[0]["pattern"] == "expected_trace_family"

    def test_sgsc_private_detected(self) -> None:
        scenario = {
            "note": "Check _sgsc_private data",
        }
        leaks = scan_scenario_for_leakage(scenario)
        assert len(leaks) == 1

    def test_private_fields_detected(self) -> None:
        scenario = {
            "text": "The private_fields section contains constraints.",
        }
        leaks = scan_scenario_for_leakage(scenario)
        assert len(leaks) == 1

    def test_nested_dict_scanning(self) -> None:
        scenario = {
            "level1": {
                "level2": {
                    "level3": "leaked activated_constraint_id here",
                },
            },
        }
        leaks = scan_scenario_for_leakage(scenario, "nested")
        assert len(leaks) == 1
        assert "level3" in leaks[0]["path"]

    def test_nested_list_scanning(self) -> None:
        scenario = {
            "items": [
                "safe text",
                "activated_constraint_id in list",
                "another safe text",
            ],
        }
        leaks = scan_scenario_for_leakage(scenario, "list_test")
        assert len(leaks) == 1
        assert "[1]" in leaks[0]["path"]

    def test_sgsc_metadata_skipped(self) -> None:
        """_sgsc_metadata key is server-side only, should be skipped."""
        scenario = {
            "description": "Clean scenario",
            "_sgsc_metadata": {
                "activated_constraint_id": "should_not_leak",
                "expected_trace_family": "should_not_leak",
            },
        }
        leaks = scan_scenario_for_leakage(scenario, "metadata_skip")
        assert leaks == []

    def test_multiple_leaks_in_one_scenario(self) -> None:
        scenario = {
            "desc": "activated_constraint_id here",
            "note": "expected_trace_family there",
        }
        leaks = scan_scenario_for_leakage(scenario, "multi")
        assert len(leaks) == 2

    def test_value_preview_truncated(self) -> None:
        long_value = "activated_constraint_id " + "x" * 200
        scenario = {"text": long_value}
        leaks = scan_scenario_for_leakage(scenario)
        assert len(leaks[0]["value_preview"]) <= 100

    def test_non_string_values_ignored(self) -> None:
        scenario = {
            "count": 42,
            "active": True,
            "ratio": 3.14,
            "nothing": None,
        }
        leaks = scan_scenario_for_leakage(scenario)
        assert leaks == []


class TestScanScenarios:
    """Tests for scan_scenarios (batch scanning)."""

    def test_all_clean_passes(self) -> None:
        scenarios = {
            "s1": {"description": "Clean 1"},
            "s2": {"description": "Clean 2"},
        }
        result = scan_scenarios(scenarios)
        assert result.passed is True
        assert result.leaks == []
        assert result.scenarios_scanned == 2

    def test_one_leak_fails(self) -> None:
        scenarios = {
            "clean": {"description": "Clean scenario"},
            "dirty": {"description": "Has activated_constraint_id leak"},
        }
        result = scan_scenarios(scenarios)
        assert result.passed is False
        assert len(result.leaks) == 1
        assert result.leaks[0]["scenario_id"] == "dirty"

    def test_empty_dict(self) -> None:
        result = scan_scenarios({})
        assert result.passed is True
        assert result.scenarios_scanned == 0

    def test_multiple_scenarios_multiple_leaks(self) -> None:
        scenarios = {
            "s1": {"text": "activated_constraint_id leak"},
            "s2": {"text": "expected_trace_family leak"},
            "s3": {"text": "clean"},
        }
        result = scan_scenarios(scenarios)
        assert result.passed is False
        assert len(result.leaks) == 2
        assert result.scenarios_scanned == 3


class TestPublicLeakageScanner:
    def test_expected_actions_detected(self) -> None:
        scenarios = {"s1": {"scenario_id": "s1", "expected_actions": ["give_med"]}}
        report = scan_public_scenarios(scenarios)
        assert not report.passed

    def test_forbidden_actions_detected(self) -> None:
        scenarios = {"s1": {"scenario_id": "s1", "forbidden_actions": ["bad_med"]}}
        report = scan_public_scenarios(scenarios)
        assert not report.passed

    def test_mandatory_actions_detected(self) -> None:
        scenarios = {"s1": {"scenario_id": "s1", "mandatory_actions": ["required_med"]}}
        report = scan_public_scenarios(scenarios)
        assert not report.passed

    def test_clean_public_scenario_passes(self) -> None:
        scenarios = {"s1": {"scenario_id": "s1", "description": "A test", "patient": {}}}
        report = scan_public_scenarios(scenarios)
        assert report.passed

    def test_ground_truth_key_detected(self) -> None:
        scenarios = {"s1": {"scenario_id": "s1", "ground_truth": {"expected": []}}}
        report = scan_public_scenarios(scenarios)
        assert not report.passed


class TestLeakageScannerWordBoundaries:
    """Patterns must use word boundaries — no false positives on innocent text."""

    def test_unexpected_actions_substring_does_not_false_positive(self) -> None:
        """Benign string containing 'expected_actions' as a sub-token must pass."""
        scenario = {
            "description": "The unexpected_actions_count metric tracks misfires."
        }
        leaks = scan_scenario_for_leakage(scenario, "fp1")
        assert leaks == [], (
            "Word-boundary pattern must not flag 'unexpected_actions_count'"
        )

    def test_inner_substring_does_not_false_positive(self) -> None:
        """A token embedded inside a longer identifier must not match."""
        scenario = {
            "note": "See pre_expected_actions_summary for upstream behaviour."
        }
        leaks = scan_scenario_for_leakage(scenario, "fp2")
        assert leaks == []

    def test_unexpected_key_in_public_scenario_does_not_false_positive(self) -> None:
        """Public-scenario key scan uses exact match: 'unexpected_actions' is fine."""
        scenarios = {"s1": {"unexpected_actions_count": 3, "description": "ok"}}
        report = scan_public_scenarios(scenarios)
        assert report.passed, (
            "Exact-match key scan must not flag 'unexpected_actions_count'"
        )

    def test_exact_token_with_punctuation_still_caught(self) -> None:
        """Word-boundary pattern still catches the real token in prose."""
        scenario = {
            "description": "Avoid leaking expected_actions, even in passing prose."
        }
        leaks = scan_scenario_for_leakage(scenario, "tp1")
        assert any(l["pattern"] == "expected_actions" for l in leaks)
