"""Tests for scripts/sgsc/audit_runtime_observation_leakage.py (P0-1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.sgsc.audit_runtime_observation_leakage import (
    run_audit,
    scan_config_yamls_for_cds,
    scan_for_canary_tokens,
    scan_sgsc_public_scenarios,
)


@pytest.fixture()
def sgsc_dir(tmp_path: Path) -> Path:
    """Create a minimal sgsc_output structure."""
    gdir = tmp_path / "test_guideline"
    gdir.mkdir()

    # Clean public scenario (no private fields)
    public = {
        "scenario_001": {
            "scenario_id": "scenario_001",
            "description": "Test scenario",
            "guideline_graph": "test_graph",
            "patient": {"age": 65},
            "optional_actions": [],
            "max_duration_minutes": 120,
        }
    }
    (gdir / "test_guideline_scenarios_public.json").write_text(json.dumps(public))

    return tmp_path


@pytest.fixture()
def config_dir(tmp_path: Path) -> Path:
    """Create a minimal configs directory."""
    cdir = tmp_path / "configs"
    cdir.mkdir()
    return cdir


class TestScanSGSCPublicScenarios:
    """Tests for scan_sgsc_public_scenarios."""

    def test_clean_public_passes(self, sgsc_dir: Path) -> None:
        scanned, leaks = scan_sgsc_public_scenarios(sgsc_dir)
        assert scanned == 1
        assert leaks == []

    def test_expected_actions_in_public_fails(self, sgsc_dir: Path) -> None:
        gdir = sgsc_dir / "test_guideline"
        public = {
            "scenario_bad": {
                "scenario_id": "scenario_bad",
                "expected_actions": ["give_antibiotics"],
                "description": "Leaking scenario",
            }
        }
        (gdir / "test_guideline_scenarios_public.json").write_text(json.dumps(public))

        scanned, leaks = scan_sgsc_public_scenarios(sgsc_dir)
        assert scanned >= 1
        assert len(leaks) > 0
        assert any("expected_actions" in l.get("pattern", "") for l in leaks)

    def test_forbidden_actions_in_public_fails(self, sgsc_dir: Path) -> None:
        gdir = sgsc_dir / "test_guideline"
        public = {
            "scenario_bad": {
                "scenario_id": "scenario_bad",
                "forbidden_actions": ["give_nitrates"],
            }
        }
        (gdir / "test_guideline_scenarios_public.json").write_text(json.dumps(public))

        scanned, leaks = scan_sgsc_public_scenarios(sgsc_dir)
        assert len(leaks) > 0

    def test_mandatory_actions_in_value_fails(self, sgsc_dir: Path) -> None:
        gdir = sgsc_dir / "test_guideline"
        public = {
            "scenario_bad": {
                "scenario_id": "scenario_bad",
                "description": "The mandatory_actions include antibiotics",
            }
        }
        (gdir / "test_guideline_scenarios_public.json").write_text(json.dumps(public))

        scanned, leaks = scan_sgsc_public_scenarios(sgsc_dir)
        assert len(leaks) > 0

    def test_ground_truth_in_public_fails(self, sgsc_dir: Path) -> None:
        gdir = sgsc_dir / "test_guideline"
        public = {
            "scenario_bad": {
                "scenario_id": "scenario_bad",
                "ground_truth": {"score": 1.0},
            }
        }
        (gdir / "test_guideline_scenarios_public.json").write_text(json.dumps(public))

        scanned, leaks = scan_sgsc_public_scenarios(sgsc_dir)
        assert len(leaks) > 0

    def test_empty_dir_returns_zero(self, tmp_path: Path) -> None:
        scanned, leaks = scan_sgsc_public_scenarios(tmp_path)
        assert scanned == 0
        assert leaks == []

    def test_multiple_guidelines(self, sgsc_dir: Path) -> None:
        # Add second guideline
        gdir2 = sgsc_dir / "test_guideline_2"
        gdir2.mkdir()
        public2 = {
            "scenario_002": {
                "scenario_id": "scenario_002",
                "description": "Another clean scenario",
            }
        }
        (gdir2 / "test_guideline_2_scenarios_public.json").write_text(json.dumps(public2))

        scanned, leaks = scan_sgsc_public_scenarios(sgsc_dir)
        assert scanned == 2
        assert leaks == []


class TestScanConfigYAMLs:
    """Tests for scan_config_yamls_for_cds."""

    def test_no_cds_passes(self, config_dir: Path) -> None:
        yaml_content = "scenario_id: test\ndescription: clean\n"
        (config_dir / "test.yaml").write_text(yaml_content)

        scanned, leaks = scan_config_yamls_for_cds(config_dir)
        assert scanned == 1
        assert leaks == []

    def test_cds_true_fails(self, config_dir: Path) -> None:
        yaml_content = "scenario_id: test\ncds_assistance: true\n"
        (config_dir / "test.yaml").write_text(yaml_content)

        scanned, leaks = scan_config_yamls_for_cds(config_dir)
        assert len(leaks) == 1
        assert leaks[0]["pattern"] == "cds_assistance_true"

    def test_cds_false_passes(self, config_dir: Path) -> None:
        yaml_content = "scenario_id: test\ncds_assistance: false\n"
        (config_dir / "test.yaml").write_text(yaml_content)

        scanned, leaks = scan_config_yamls_for_cds(config_dir)
        assert leaks == []

    def test_nested_cds_true_fails(self, config_dir: Path) -> None:
        yaml_content = "scenario_id: test\nenvironment:\n  cds_assistance: true\n"
        (config_dir / "test.yaml").write_text(yaml_content)

        scanned, leaks = scan_config_yamls_for_cds(config_dir)
        assert len(leaks) == 1


class TestScanCanaryTokens:
    """Tests for scan_for_canary_tokens."""

    def test_no_canary_passes(self, sgsc_dir: Path) -> None:
        leaks = scan_for_canary_tokens(sgsc_dir, ["CANARY_SECRET_123"])
        assert leaks == []

    def test_canary_found_fails(self, sgsc_dir: Path) -> None:
        gdir = sgsc_dir / "test_guideline"
        public = {"scenario_001": {"description": "Contains CANARY_SECRET_123 token"}}
        (gdir / "test_guideline_scenarios_public.json").write_text(json.dumps(public))

        leaks = scan_for_canary_tokens(sgsc_dir, ["CANARY_SECRET_123"])
        assert len(leaks) == 1

    def test_no_tokens_returns_empty(self, sgsc_dir: Path) -> None:
        leaks = scan_for_canary_tokens(sgsc_dir, None)
        assert leaks == []


class TestRunAudit:
    """Tests for run_audit end-to-end."""

    def test_clean_audit_passes(self, sgsc_dir: Path, config_dir: Path) -> None:
        report = run_audit(sgsc_dir, config_dir)
        assert report["status"] == "pass"
        assert report["check_name"] == "runtime_observation_leakage"
        assert report["metrics"]["total_failures"] == 0

    def test_audit_with_leak_fails(self, sgsc_dir: Path, config_dir: Path) -> None:
        gdir = sgsc_dir / "test_guideline"
        public = {"scenario_bad": {"expected_actions": ["give_abx"]}}
        (gdir / "test_guideline_scenarios_public.json").write_text(json.dumps(public))

        report = run_audit(sgsc_dir, config_dir)
        assert report["status"] == "fail"
        assert report["metrics"]["private_field_leaks"] > 0

    def test_json_output_schema(self, sgsc_dir: Path, config_dir: Path) -> None:
        report = run_audit(sgsc_dir, config_dir)
        required_keys = {"check_name", "status", "commit", "metrics", "failures"}
        assert required_keys.issubset(report.keys())
        assert report["status"] in ("pass", "warn", "fail")
        assert isinstance(report["metrics"], dict)
        assert isinstance(report["failures"], list)

    def test_output_hash_present(self, sgsc_dir: Path, config_dir: Path) -> None:
        report = run_audit(sgsc_dir, config_dir)
        assert "output_hash" in report
        assert len(report["output_hash"]) == 64  # SHA-256 hex
