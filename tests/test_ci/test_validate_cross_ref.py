"""Tests for scripts/ci/validate_cross_ref.py — CPG cross-reference validator."""

from __future__ import annotations

import pytest
from scripts.ci.validate_cross_ref import (
    ActionIndex,
    check_action_namespace,
    check_connectivity,
    check_deadline_consistency,
    check_forbidden_mandatory_conflict,
    check_orphan_deadlines,
    check_rule_id_uniqueness,
    validate_cross_references,
)

# ---------------------------------------------------------------------------
# Fixtures: minimal graph builders
# ---------------------------------------------------------------------------


def _minimal_graph(
    graph_id: str = "test_graph",
    nodes: dict | None = None,
    entry_node: str = "n1",
    domain: str = "sepsis",
) -> dict:
    """Build a minimal valid CPG graph dict."""
    if nodes is None:
        nodes = {
            "n1": {
                "node_id": "n1",
                "node_type": "plan",
                "name": "Node 1",
                "mandatory_actions": ["action_a"],
                "allowed_actions": ["action_a", "action_b"],
                "forbidden_actions": [],
                "deadlines": {"action_a": 60},
                "next_nodes": [],
                "conditional_next": {},
                "source_guideline": "Test",
                "source_section": "Section 1",
            }
        }
    return {
        "graph_id": graph_id,
        "guideline_name": f"Test Guideline {graph_id}",
        "entry_node": entry_node,
        "metadata": {"domain": domain},
        "nodes": nodes,
    }


# ---------------------------------------------------------------------------
# check_connectivity
# ---------------------------------------------------------------------------


class TestCheckConnectivity:
    def test_single_node_reachable(self) -> None:
        graph = _minimal_graph()
        errors = check_connectivity(graph, "test")
        assert errors == []

    def test_chain_reachable(self) -> None:
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": [],
                    "next_nodes": ["n2"],
                    "conditional_next": {},
                    "source_guideline": "T",
                    "source_section": "S",
                },
                "n2": {
                    "node_id": "n2",
                    "node_type": "action",
                    "name": "N2",
                    "mandatory_actions": [],
                    "next_nodes": [],
                    "conditional_next": {},
                    "source_guideline": "T",
                    "source_section": "S",
                },
            }
        )
        assert check_connectivity(graph, "test") == []

    def test_unreachable_node(self) -> None:
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": [],
                    "next_nodes": [],
                    "conditional_next": {},
                    "source_guideline": "T",
                    "source_section": "S",
                },
                "orphan": {
                    "node_id": "orphan",
                    "node_type": "action",
                    "name": "Orphan",
                    "mandatory_actions": [],
                    "next_nodes": [],
                    "conditional_next": {},
                    "source_guideline": "T",
                    "source_section": "S",
                },
            }
        )
        errors = check_connectivity(graph, "test")
        assert len(errors) == 1
        assert "orphan" in errors[0]

    def test_conditional_next_reachable(self) -> None:
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "decision",
                    "name": "N1",
                    "mandatory_actions": [],
                    "next_nodes": [],
                    "conditional_next": {"cond_a": "n2", "cond_b": "n3"},
                    "source_guideline": "T",
                    "source_section": "S",
                },
                "n2": {
                    "node_id": "n2",
                    "node_type": "plan",
                    "name": "N2",
                    "mandatory_actions": [],
                    "next_nodes": [],
                    "conditional_next": {},
                    "source_guideline": "T",
                    "source_section": "S",
                },
                "n3": {
                    "node_id": "n3",
                    "node_type": "action",
                    "name": "N3",
                    "mandatory_actions": [],
                    "next_nodes": [],
                    "conditional_next": {},
                    "source_guideline": "T",
                    "source_section": "S",
                },
            }
        )
        assert check_connectivity(graph, "test") == []

    def test_missing_entry_node(self) -> None:
        graph = _minimal_graph(entry_node="nonexistent")
        errors = check_connectivity(graph, "test")
        assert len(errors) == 1
        assert "nonexistent" in errors[0]


# ---------------------------------------------------------------------------
# check_deadline_consistency
# ---------------------------------------------------------------------------


class TestDeadlineConsistency:
    def test_consistent_deadlines(self) -> None:
        idx = ActionIndex()
        idx.deadlines["action_a"] = [("g1", 60), ("g2", 60)]
        assert check_deadline_consistency(idx) == []

    def test_divergent_deadlines(self) -> None:
        idx = ActionIndex()
        idx.deadlines["action_a"] = [("g1", 10), ("g2", 60)]
        warnings = check_deadline_consistency(idx)
        assert len(warnings) == 1
        assert "divergence" in warnings[0]
        assert "action_a" in warnings[0]

    def test_single_entry_no_warning(self) -> None:
        idx = ActionIndex()
        idx.deadlines["action_a"] = [("g1", 60)]
        assert check_deadline_consistency(idx) == []


# ---------------------------------------------------------------------------
# check_forbidden_mandatory_conflict
# ---------------------------------------------------------------------------


class TestForbiddenMandatoryConflict:
    def test_no_conflict(self) -> None:
        idx = ActionIndex()
        idx.mandatory["action_a"] = [("g1", "g1:n1")]
        idx.forbidden["action_b"] = [("g1", "g1:n1")]
        idx.graph_domains["g1"] = "sepsis"
        assert check_forbidden_mandatory_conflict(idx) == []

    def test_cross_graph_same_domain_conflict(self) -> None:
        idx = ActionIndex()
        idx.mandatory["action_a"] = [("g1", "g1:n1")]
        idx.forbidden["action_a"] = [("g2", "g2:n1")]
        idx.graph_domains["g1"] = "sepsis"
        idx.graph_domains["g2"] = "sepsis"
        errors = check_forbidden_mandatory_conflict(idx)
        assert len(errors) == 1
        assert "action_a" in errors[0]

    def test_cross_domain_no_error(self) -> None:
        """Mandatory in sepsis, forbidden in stroke is expected."""
        idx = ActionIndex()
        idx.mandatory["action_a"] = [("g1", "g1:n1")]
        idx.forbidden["action_a"] = [("g2", "g2:n1")]
        idx.graph_domains["g1"] = "sepsis"
        idx.graph_domains["g2"] = "stroke"
        errors = check_forbidden_mandatory_conflict(idx)
        assert errors == []


# ---------------------------------------------------------------------------
# check_rule_id_uniqueness
# ---------------------------------------------------------------------------


class TestRuleIdUniqueness:
    def test_unique_ids(self) -> None:
        idx = ActionIndex()
        idx.rule_ids["RULE-1"] = ["g1"]
        idx.rule_ids["RULE-2"] = ["g2"]
        assert check_rule_id_uniqueness(idx) == []

    def test_duplicate_ids(self) -> None:
        idx = ActionIndex()
        idx.rule_ids["RULE-1"] = ["g1", "g2"]
        warnings = check_rule_id_uniqueness(idx)
        assert len(warnings) == 1
        assert "RULE-1" in warnings[0]


# ---------------------------------------------------------------------------
# check_action_namespace
# ---------------------------------------------------------------------------


class TestActionNamespace:
    def test_domain_specific_ok(self) -> None:
        idx = ActionIndex()
        idx.mandatory["give_tpa"] = [("g1", "g1:n1"), ("g2", "g2:n1")]
        idx.graph_domains["g1"] = "stroke"
        idx.graph_domains["g2"] = "stroke"
        assert check_action_namespace(idx) == []

    def test_universal_action_no_warning(self) -> None:
        idx = ActionIndex()
        idx.mandatory["assess_vital_signs"] = [
            ("g1", "g1:n1"),
            ("g2", "g2:n1"),
            ("g3", "g3:n1"),
        ]
        idx.graph_domains["g1"] = "sepsis"
        idx.graph_domains["g2"] = "stroke"
        idx.graph_domains["g3"] = "aki"
        assert check_action_namespace(idx) == []

    def test_leaked_action_warning(self) -> None:
        idx = ActionIndex()
        idx.mandatory["specific_action"] = [
            ("g1", "g1:n1"),
            ("g2", "g2:n1"),
            ("g3", "g3:n1"),
        ]
        idx.graph_domains["g1"] = "sepsis"
        idx.graph_domains["g2"] = "stroke"
        idx.graph_domains["g3"] = "aki"
        warnings = check_action_namespace(idx)
        assert len(warnings) == 1
        assert "specific_action" in warnings[0]


# ---------------------------------------------------------------------------
# check_orphan_deadlines
# ---------------------------------------------------------------------------


class TestOrphanDeadlines:
    def test_no_orphans(self) -> None:
        graph = _minimal_graph()  # deadline for action_a which is in allowed
        assert check_orphan_deadlines(graph, "test") == []

    def test_orphan_deadline(self) -> None:
        graph = _minimal_graph(
            nodes={
                "n1": {
                    "node_id": "n1",
                    "node_type": "plan",
                    "name": "N1",
                    "mandatory_actions": ["action_a"],
                    "allowed_actions": ["action_a"],
                    "forbidden_actions": [],
                    "deadlines": {"action_a": 60, "ghost_action": 30},
                    "next_nodes": [],
                    "conditional_next": {},
                    "source_guideline": "T",
                    "source_section": "S",
                }
            }
        )
        warnings = check_orphan_deadlines(graph, "test")
        assert len(warnings) == 1
        assert "ghost_action" in warnings[0]


# ---------------------------------------------------------------------------
# validate_cross_references (integration)
# ---------------------------------------------------------------------------


class TestValidateCrossReferences:
    def test_clean_corpus(self) -> None:
        """Single clean graph passes validation."""
        corpus = {"g1": _minimal_graph("g1")}
        errors, warnings = validate_cross_references(corpus)
        assert errors == []

    def test_candidate_against_corpus(self) -> None:
        corpus = {"g1": _minimal_graph("g1", domain="sepsis")}
        candidate = {"g2": _minimal_graph("g2", domain="sepsis")}
        errors, warnings = validate_cross_references(corpus, candidate)
        assert errors == []

    def test_real_ssc_graph_connectivity(self) -> None:
        """SSC sepsis graph should pass connectivity check."""
        from pathlib import Path

        import yaml

        ssc_path = (
            Path(__file__).resolve().parent.parent.parent / "cpg_model" / "graphs" / "ssc_sepsis_hour1_bundle.yaml"
        )
        if not ssc_path.exists():
            pytest.skip("SSC graph not found")

        data = yaml.safe_load(ssc_path.read_text(encoding="utf-8"))
        corpus = {data["graph_id"]: data}
        errors, _warnings = validate_cross_references(corpus)
        assert errors == [], f"SSC graph should be fully connected: {errors}"
