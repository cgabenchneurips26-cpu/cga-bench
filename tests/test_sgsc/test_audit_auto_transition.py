"""Tests for scripts/sgsc/audit_auto_transition_semantics.py (P0-4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from scripts.sgsc.audit_auto_transition_semantics import (
    audit_graph,
    check_ambiguous_multi_fire,
    check_hidden_state_references,
    check_missing_provenance,
    check_missing_target_nodes,
    check_unbounded_cycles,
    run_audit,
)


def _make_graph(
    graph_id: str = "test_graph",
    nodes: dict | None = None,
    auto_transitions: list[dict] | None = None,
) -> dict:
    """Build a minimal graph dict."""
    if nodes is None:
        nodes = {
            "node_a": {
                "node_id": "node_a",
                "node_type": "action",
                "name": "Node A",
                "auto_transition_conditions": auto_transitions or [],
            },
            "node_b": {
                "node_id": "node_b",
                "node_type": "action",
                "name": "Node B",
                "auto_transition_conditions": [],
            },
        }
    return {
        "graph_id": graph_id,
        "guideline_name": "Test Guideline",
        "version": "1.0",
        "entry_node": "node_a",
        "nodes": nodes,
    }


@pytest.fixture()
def sgsc_dir_with_graph(tmp_path: Path) -> Path:
    """Create sgsc_output with a clean graph."""
    gdir = tmp_path / "test_guideline"
    gdir.mkdir()
    graph = _make_graph()
    (gdir / "test_guideline_graph.json").write_text(json.dumps(graph))
    return tmp_path


class TestCheckMissingTargetNodes:
    """Tests for check_missing_target_nodes."""

    def test_valid_target_passes(self) -> None:
        transitions = [{"target_node": "node_b"}]
        failures = check_missing_target_nodes(transitions, {"node_a", "node_b"}, "test")
        assert failures == []

    def test_missing_target_fails(self) -> None:
        transitions = [{"target_node": "node_missing"}]
        failures = check_missing_target_nodes(transitions, {"node_a", "node_b"}, "test")
        assert len(failures) == 1
        assert failures[0]["check"] == "missing_target_node"

    def test_empty_transitions_passes(self) -> None:
        failures = check_missing_target_nodes([], {"node_a"}, "test")
        assert failures == []


class TestCheckHiddenStateReferences:
    """Tests for check_hidden_state_references."""

    def test_clean_transition_passes(self) -> None:
        transitions = [{"condition": {"vital": "hr > 120"}, "target_node": "node_b"}]
        failures = check_hidden_state_references(transitions, "test")
        assert failures == []

    def test_expected_actions_reference_fails(self) -> None:
        transitions = [{"condition": {"check": "expected_actions contains X"}}]
        failures = check_hidden_state_references(transitions, "test")
        assert len(failures) == 1
        assert failures[0]["check"] == "hidden_state_before_reveal"

    def test_ground_truth_reference_fails(self) -> None:
        transitions = [{"condition": {"ref": "ground_truth score"}}]
        failures = check_hidden_state_references(transitions, "test")
        assert len(failures) >= 1


class TestCheckAmbiguousMultiFire:
    """Tests for check_ambiguous_multi_fire."""

    def test_single_transition_passes(self) -> None:
        transitions = [{"condition": {"x": 1}, "target_node": "a"}]
        failures = check_ambiguous_multi_fire(transitions, "test")
        assert failures == []

    def test_duplicate_condition_no_priority_fails(self) -> None:
        cond = {"x": 1}
        transitions = [
            {"condition": cond, "target_node": "a"},
            {"condition": cond, "target_node": "b"},
        ]
        failures = check_ambiguous_multi_fire(transitions, "test")
        assert len(failures) == 1

    def test_duplicate_condition_with_priority_passes(self) -> None:
        cond = {"x": 1}
        transitions = [
            {"condition": cond, "target_node": "a", "priority": 1},
            {"condition": cond, "target_node": "b", "priority": 2},
        ]
        failures = check_ambiguous_multi_fire(transitions, "test")
        assert failures == []


class TestCheckUnboundedCycles:
    """Tests for check_unbounded_cycles."""

    def test_no_transitions_passes(self) -> None:
        failures = check_unbounded_cycles([], "test")
        assert failures == []

    def test_acyclic_transitions_passes(self) -> None:
        transitions = [
            {"source_node": "a", "target_node": "b"},
            {"source_node": "b", "target_node": "c"},
        ]
        failures = check_unbounded_cycles(transitions, "test")
        assert failures == []

    def test_cycle_detected_fails(self) -> None:
        transitions = [
            {"source_node": "a", "target_node": "b"},
            {"source_node": "b", "target_node": "a"},
        ]
        failures = check_unbounded_cycles(transitions, "test")
        assert len(failures) == 1
        assert failures[0]["check"] == "unbounded_cycle"


class TestCheckMissingProvenance:
    """Tests for check_missing_provenance."""

    def test_with_atom_ids_passes(self) -> None:
        transitions = [{"source_atom_ids": ["atom_001"]}]
        failures = check_missing_provenance(transitions, "test")
        assert failures == []

    def test_with_author_override_passes(self) -> None:
        transitions = [{"author_override": "manual_review"}]
        failures = check_missing_provenance(transitions, "test")
        assert failures == []

    def test_missing_both_warns(self) -> None:
        transitions = [{"target_node": "b"}]
        failures = check_missing_provenance(transitions, "test")
        assert len(failures) == 1
        assert failures[0]["check"] == "missing_provenance"


class TestAuditGraph:
    """Tests for audit_graph."""

    def test_empty_transitions_passes(self, tmp_path: Path) -> None:
        graph = _make_graph()
        gf = tmp_path / "test_graph.json"
        gf.write_text(json.dumps(graph))

        n_trans, failures = audit_graph(gf)
        assert n_trans == 0
        assert failures == []

    def test_graph_with_violations(self, tmp_path: Path) -> None:
        transitions = [
            {"target_node": "missing_node", "condition": {"check": "expected_actions"}},
        ]
        graph = _make_graph(auto_transitions=transitions)
        gf = tmp_path / "test_graph.json"
        gf.write_text(json.dumps(graph))

        n_trans, failures = audit_graph(gf)
        assert n_trans == 1
        assert len(failures) >= 2  # missing_target + hidden_state + missing_provenance


class TestRunAudit:
    """Tests for run_audit end-to-end."""

    def test_clean_audit_passes(self, sgsc_dir_with_graph: Path) -> None:
        report = run_audit(sgsc_dir_with_graph)
        assert report["status"] == "pass"
        assert report["metrics"]["graphs_scanned"] == 1
        assert report["metrics"]["total_auto_transitions"] == 0

    def test_json_output_schema(self, sgsc_dir_with_graph: Path) -> None:
        report = run_audit(sgsc_dir_with_graph)
        required_keys = {"check_name", "status", "commit", "metrics", "failures"}
        assert required_keys.issubset(report.keys())
        assert report["status"] in ("pass", "warn", "fail")
        assert "graphs_scanned" in report["metrics"]
        assert "total_auto_transitions" in report["metrics"]

    def test_output_hash_present(self, sgsc_dir_with_graph: Path) -> None:
        report = run_audit(sgsc_dir_with_graph)
        assert "output_hash" in report
        assert len(report["output_hash"]) == 64

    def test_empty_dir_scans_zero(self, tmp_path: Path) -> None:
        report = run_audit(tmp_path)
        assert report["status"] == "pass"
        assert report["metrics"]["graphs_scanned"] == 0
