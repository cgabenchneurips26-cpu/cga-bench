"""Tests for scripts/sgsc/compare_old_new_verdicts.py (P0-2 supplement)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from scripts.sgsc.compare_old_new_verdicts import (
    compare_guideline,
    compute_action_overlap,
    load_sgsc_scenarios,
    match_v6_to_guideline,
    run_comparison,
)


def _make_v6_scenarios() -> dict[str, dict]:
    """Create mock v6 scenarios."""
    return {
        "sepsis_basic_001": {
            "scenario_id": "sepsis_basic_001",
            "description": "Basic sepsis scenario",
            "graph_file": "ssc_sepsis_hour1.yaml",
            "expected_actions": [
                "order_lab_blood_culture",
                "give_broad_spectrum_antibiotics",
                "give_crystalloid_30ml_kg",
            ],
            "forbidden_actions": ["give_nitrates"],
        },
        "chest_pain_001": {
            "scenario_id": "chest_pain_001",
            "description": "Chest pain evaluation",
            "graph_file": "aha_chest_pain.yaml",
            "expected_actions": ["order_ecg_12lead", "give_aspirin_loading"],
            "forbidden_actions": [],
        },
        "unrelated_scenario": {
            "scenario_id": "unrelated_scenario",
            "description": "Unrelated scenario",
            "graph_file": "other.yaml",
            "expected_actions": ["action_x"],
        },
    }


@pytest.fixture()
def sgsc_dir(tmp_path: Path) -> Path:
    """Create sgsc_output with private scenarios."""
    gdir = tmp_path / "ssc_sepsis_hour1_bundle"
    gdir.mkdir()

    private = {
        "sgsc_sepsis_001": {
            "scenario_id": "sgsc_sepsis_001",
            "expected_actions": [
                "order_lab_blood_culture",
                "give_broad_spectrum_antibiotics",
                "measure_lactate",
            ],
            "forbidden_actions": ["give_nitrates"],
        },
    }
    (gdir / "ssc_sepsis_hour1_bundle_scenarios_private.json").write_text(json.dumps(private))

    return tmp_path


class TestComputeActionOverlap:
    """Tests for compute_action_overlap."""

    def test_identical_sets(self) -> None:
        actions = {"a", "b", "c"}
        assert compute_action_overlap(actions, actions) == 1.0

    def test_disjoint_sets(self) -> None:
        assert compute_action_overlap({"a", "b"}, {"c", "d"}) == 0.0

    def test_partial_overlap(self) -> None:
        overlap = compute_action_overlap({"a", "b", "c"}, {"b", "c", "d"})
        # Jaccard: |{b,c}| / |{a,b,c,d}| = 2/4 = 0.5
        assert overlap == 0.5

    def test_both_empty(self) -> None:
        assert compute_action_overlap(set(), set()) == 1.0

    def test_one_empty(self) -> None:
        assert compute_action_overlap({"a"}, set()) == 0.0


class TestMatchV6ToGuideline:
    """Tests for match_v6_to_guideline."""

    def test_matches_by_domain_pattern(self) -> None:
        v6 = _make_v6_scenarios()
        matched = match_v6_to_guideline(v6, "ssc_sepsis_hour1_bundle")
        assert "sepsis_basic_001" in matched
        assert "unrelated_scenario" not in matched

    def test_no_match_for_unknown_guideline(self) -> None:
        v6 = _make_v6_scenarios()
        matched = match_v6_to_guideline(v6, "unknown_guideline")
        assert matched == {}

    def test_matches_by_graph_file(self) -> None:
        v6 = {
            "scenario_x": {
                "scenario_id": "scenario_x",
                "description": "Generic",
                "graph_file": "ssc_sepsis_hour1.yaml",
            }
        }
        matched = match_v6_to_guideline(v6, "ssc_sepsis_hour1_bundle")
        assert "scenario_x" in matched


class TestLoadSGSCScenarios:
    """Tests for load_sgsc_scenarios."""

    def test_loads_private_scenarios(self, sgsc_dir: Path) -> None:
        scenarios = load_sgsc_scenarios(sgsc_dir, "ssc_sepsis_hour1_bundle")
        assert len(scenarios) == 1
        assert "sgsc_sepsis_001" in scenarios

    def test_missing_guideline_returns_empty(self, sgsc_dir: Path) -> None:
        scenarios = load_sgsc_scenarios(sgsc_dir, "nonexistent_guideline")
        assert scenarios == {}


class TestCompareGuideline:
    """Tests for compare_guideline."""

    def test_identical_actions(self) -> None:
        v6 = {"s1": {"expected_actions": ["a", "b"], "forbidden_actions": ["x"]}}
        sgsc = {"s2": {"expected_actions": ["a", "b"], "forbidden_actions": ["x"]}}
        result = compare_guideline(v6, sgsc, "test")
        assert result["action_overlap"] == 1.0
        assert result["constraint_additions"] == 0
        assert result["constraint_removals"] == 0

    def test_sgsc_adds_actions(self) -> None:
        v6 = {"s1": {"expected_actions": ["a", "b"]}}
        sgsc = {"s2": {"expected_actions": ["a", "b", "c"]}}
        result = compare_guideline(v6, sgsc, "test")
        assert result["constraint_additions"] == 1
        assert "c" in result["added_actions"]

    def test_sgsc_removes_actions(self) -> None:
        v6 = {"s1": {"expected_actions": ["a", "b", "c"]}}
        sgsc = {"s2": {"expected_actions": ["a"]}}
        result = compare_guideline(v6, sgsc, "test")
        assert result["constraint_removals"] == 2

    def test_empty_both(self) -> None:
        result = compare_guideline({}, {}, "test")
        assert result["v6_scenario_count"] == 0
        assert result["sgsc_scenario_count"] == 0


class TestRunComparison:
    """Tests for run_comparison end-to-end."""

    def test_produces_report(self, sgsc_dir: Path, tmp_path: Path) -> None:
        config_dir = tmp_path / "configs"
        config_dir.mkdir()

        registry = {
            "guidelines": [
                {"guideline_id": "ssc_sepsis_hour1_bundle"},
            ]
        }
        with patch(
            "scripts.sgsc.compare_old_new_verdicts.REGISTRY_PATH",
            tmp_path / "registry.json",
        ):
            (tmp_path / "registry.json").write_text(json.dumps(registry))
            report = run_comparison(sgsc_dir, config_dir)

        assert report["check_name"] == "old_new_verdict_delta"
        assert report["status"] in ("pass", "warn", "fail")
        assert "metrics" in report

    def test_json_output_schema(self, sgsc_dir: Path, tmp_path: Path) -> None:
        config_dir = tmp_path / "configs"
        config_dir.mkdir()

        registry = {"guidelines": [{"guideline_id": "ssc_sepsis_hour1_bundle"}]}
        with patch(
            "scripts.sgsc.compare_old_new_verdicts.REGISTRY_PATH",
            tmp_path / "registry.json",
        ):
            (tmp_path / "registry.json").write_text(json.dumps(registry))
            report = run_comparison(sgsc_dir, config_dir)

        required_keys = {"check_name", "status", "commit", "metrics", "failures"}
        assert required_keys.issubset(report.keys())
        assert "output_hash" in report
        assert len(report["output_hash"]) == 64

    def test_empty_sgsc_dir(self, tmp_path: Path) -> None:
        sgsc_dir = tmp_path / "sgsc_output"
        sgsc_dir.mkdir()
        config_dir = tmp_path / "configs"
        config_dir.mkdir()

        registry = {"guidelines": [{"guideline_id": "ssc_sepsis_hour1_bundle"}]}
        with patch(
            "scripts.sgsc.compare_old_new_verdicts.REGISTRY_PATH",
            tmp_path / "registry.json",
        ):
            (tmp_path / "registry.json").write_text(json.dumps(registry))
            report = run_comparison(sgsc_dir, config_dir)

        assert report["status"] == "pass"
        assert report["metrics"]["sgsc_scenarios_total"] == 0
