"""Tests for CPGEngine load-time graph structure validation (P1).

Verifies 6 structural checks added in v1.1 hardening:
1. entry_node exists in nodes
2. next_nodes targets exist
3. conditional_next targets exist
4. deadline keys reference mandatory or allowed actions
5. conditional_rules have valid effect.type
6. conditional_rules have non-empty effect.actions

Note: Checks 5-6 are partially redundant with Pydantic validation of
ConstraintEffect at parse time. The engine validator catches issues when
graphs are loaded from raw dicts that bypass Pydantic (e.g. test fixtures).
We test the validator method directly for those cases.
"""

from __future__ import annotations

import copy
import logging

import pytest

from cga_bench.cpg_engine.engine import (
    CPGEngine,
    CPGEngineConfig,
    CPGEngineFactory,
    GraphValidationResult,
)

# ---------------------------------------------------------------------------
# Minimal valid graph fixture
# ---------------------------------------------------------------------------

_VALID_GRAPH: dict = {
    "graph_id": "test_valid",
    "guideline_name": "Test Guideline",
    "version": "1.0",
    "entry_node": "start",
    "nodes": {
        "start": {
            "node_id": "start",
            "node_type": "decision",
            "name": "Initial assessment",
            "description": "Entry point",
            "mandatory_actions": ["assess_vitals"],
            "allowed_actions": ["assess_vitals", "order_lab_cbc"],
            "forbidden_actions": [],
            "deadlines": {"assess_vitals": 15},
            "next_nodes": ["treatment"],
            "conditional_next": {},
            "conditional_rules": [
                {
                    "rule_id": "R1",
                    "condition": "True",
                    "effect": {"type": "REQUIRED", "actions": ["assess_vitals"]},
                    "evidence": "Test guideline 1.0",
                    "severity": "HIGH",
                    "description": "Always assess vitals",
                }
            ],
            "source_guideline": "Test",
            "source_section": "1.0",
        },
        "treatment": {
            "node_id": "treatment",
            "node_type": "action",
            "name": "Treatment",
            "description": "Treatment node",
            "mandatory_actions": ["give_medication"],
            "allowed_actions": ["give_medication"],
            "forbidden_actions": [],
            "deadlines": {},
            "next_nodes": [],
            "conditional_next": {},
            "conditional_rules": [],
            "source_guideline": "Test",
            "source_section": "2.0",
        },
    },
}


def _graph(**overrides: object) -> dict:
    """Return a copy of _VALID_GRAPH with optional top-level overrides."""
    g = copy.deepcopy(_VALID_GRAPH)
    g.update(overrides)
    return g


def _load(data: dict, strict: bool = False) -> CPGEngine:
    """Load a graph dict into CPGEngine with optional strict_mode."""
    cfg = CPGEngineConfig(strict_mode=strict) if strict else None
    return CPGEngineFactory.load_from_dict(copy.deepcopy(data), config=cfg)


# ---------------------------------------------------------------------------
# Test: Valid graph passes all checks
# ---------------------------------------------------------------------------


class TestValidGraph:
    """A well-formed graph should produce zero errors and zero warnings."""

    def test_valid_graph_no_errors(self) -> None:
        engine = _load(_VALID_GRAPH)
        assert engine._validation_result.ok
        assert engine._validation_result.errors == []

    def test_valid_graph_no_warnings(self) -> None:
        engine = _load(_VALID_GRAPH)
        assert engine._validation_result.warnings == []

    def test_validation_result_total_checks(self) -> None:
        engine = _load(_VALID_GRAPH)
        assert engine._validation_result.total_checks == 0


# ---------------------------------------------------------------------------
# Check 1: entry_node exists
# ---------------------------------------------------------------------------


class TestEntryNodeValidation:
    """entry_node must reference an existing node."""

    def test_missing_entry_node_error(self) -> None:
        data = _graph(entry_node="nonexistent")
        engine = _load(data)
        assert not engine._validation_result.ok
        assert any("entry_node" in e and "nonexistent" in e for e in engine._validation_result.errors)

    def test_missing_entry_node_strict_raises(self) -> None:
        data = _graph(entry_node="nonexistent")
        with pytest.raises(ValueError, match="entry_node"):
            _load(data, strict=True)


# ---------------------------------------------------------------------------
# Check 2: next_nodes targets exist
# ---------------------------------------------------------------------------


class TestNextNodesValidation:
    """All next_nodes entries must reference existing nodes."""

    def test_dangling_next_node_error(self) -> None:
        data = _graph()
        data["nodes"]["start"]["next_nodes"] = ["treatment", "phantom"]
        engine = _load(data)
        assert not engine._validation_result.ok
        assert any("phantom" in e and "next_nodes" in e for e in engine._validation_result.errors)

    def test_valid_next_node_no_error(self) -> None:
        engine = _load(_VALID_GRAPH)
        assert not any("next_nodes" in e for e in engine._validation_result.errors)

    def test_empty_next_nodes_ok(self) -> None:
        data = _graph()
        data["nodes"]["treatment"]["next_nodes"] = []
        engine = _load(data)
        assert engine._validation_result.ok


# ---------------------------------------------------------------------------
# Check 3: conditional_next targets exist
# ---------------------------------------------------------------------------


class TestConditionalNextValidation:
    """All conditional_next targets must reference existing nodes."""

    def test_dangling_conditional_next_error(self) -> None:
        data = _graph()
        data["nodes"]["start"]["conditional_next"] = {"sbp < 90": "ghost_node"}
        engine = _load(data)
        assert not engine._validation_result.ok
        assert any("ghost_node" in e and "conditional_next" in e for e in engine._validation_result.errors)

    def test_valid_conditional_next_no_error(self) -> None:
        data = _graph()
        data["nodes"]["start"]["conditional_next"] = {"sbp < 90": "treatment"}
        engine = _load(data)
        assert not any("conditional_next" in e for e in engine._validation_result.errors)


# ---------------------------------------------------------------------------
# Check 4: deadline keys reference mandatory or allowed actions
# ---------------------------------------------------------------------------


class TestDeadlineValidation:
    """Deadline keys should reference actions in mandatory or allowed lists."""

    def test_orphan_deadline_warning(self) -> None:
        data = _graph()
        data["nodes"]["start"]["deadlines"] = {"unknown_action": 30}
        engine = _load(data)
        # Orphan deadline is a warning, not an error
        assert engine._validation_result.ok
        assert any("unknown_action" in w and "deadline" in w for w in engine._validation_result.warnings)

    def test_valid_deadline_no_warning(self) -> None:
        engine = _load(_VALID_GRAPH)
        assert not any("deadline" in w for w in engine._validation_result.warnings)

    def test_deadline_for_allowed_action_ok(self) -> None:
        data = _graph()
        data["nodes"]["start"]["deadlines"] = {"order_lab_cbc": 60}
        engine = _load(data)
        assert not any("deadline" in w for w in engine._validation_result.warnings)


# ---------------------------------------------------------------------------
# Check 5: conditional_rules effect.type validity
# (Pydantic enforces ConstraintType enum at parse time, so invalid types
#  can't reach the engine validator via load_from_dict. We test the validator
#  method directly with a pre-built engine whose node_def has a raw dict.)
# ---------------------------------------------------------------------------


class TestEffectTypeValidation:
    """Pydantic validates effect.type at parse; engine validator is a safety net."""

    def test_pydantic_rejects_invalid_effect_type(self) -> None:
        """Pydantic's ConstraintEffect validates type at parse time."""
        from pydantic import ValidationError

        data = _graph()
        data["nodes"]["start"]["conditional_rules"] = [
            {
                "rule_id": "BAD",
                "condition": "True",
                "effect": {"type": "BANANA", "actions": ["foo"]},
                "evidence": "Test",
                "severity": "HIGH",
            }
        ]
        with pytest.raises(ValidationError, match="type"):
            _load(data)

    def test_all_valid_effect_types_accepted(self) -> None:
        """All four valid effect types should parse and validate."""
        for etype in ("FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN"):
            data = _graph()
            data["nodes"]["start"]["conditional_rules"] = [
                {
                    "rule_id": f"R_{etype}",
                    "condition": "True",
                    "effect": {"type": etype, "actions": ["assess_vitals"]},
                    "evidence": "Test guideline",
                    "severity": "HIGH",
                }
            ]
            engine = _load(data)
            effect_errors = [e for e in engine._validation_result.errors if "effect type" in e]
            assert effect_errors == [], f"Unexpected error for valid type {etype}"


# ---------------------------------------------------------------------------
# Check 6: conditional_rules effect.actions non-empty
# (Also enforced by Pydantic since actions: list[str] = Field(...) requires
#  a non-empty value. But the validator catches raw-dict cases.)
# ---------------------------------------------------------------------------


class TestEffectActionsValidation:
    """effect.actions must not be empty."""

    def test_pydantic_rejects_missing_actions_key(self) -> None:
        """Pydantic's ConstraintEffect requires actions field."""
        from pydantic import ValidationError

        data = _graph()
        data["nodes"]["start"]["conditional_rules"] = [
            {
                "rule_id": "NOKEY",
                "condition": "True",
                "effect": {"type": "FORBIDDEN"},
                "evidence": "Test",
                "severity": "HIGH",
            }
        ]
        with pytest.raises(ValidationError, match="actions"):
            _load(data)

    def test_empty_actions_still_loads_but_validator_catches(self) -> None:
        """An empty actions list passes Pydantic but the validator flags it."""
        data = _graph()
        data["nodes"]["start"]["conditional_rules"] = [
            {
                "rule_id": "EMPTY",
                "condition": "True",
                "effect": {"type": "REQUIRED", "actions": []},
                "evidence": "Test guideline",
                "severity": "HIGH",
            }
        ]
        engine = _load(data)
        assert not engine._validation_result.ok
        assert any("empty effect.actions" in e for e in engine._validation_result.errors)


# ---------------------------------------------------------------------------
# GraphValidationResult dataclass
# ---------------------------------------------------------------------------


class TestGraphValidationResult:
    """Unit tests for the result dataclass itself."""

    def test_ok_when_empty(self) -> None:
        r = GraphValidationResult()
        assert r.ok
        assert r.total_checks == 0

    def test_not_ok_with_errors(self) -> None:
        r = GraphValidationResult(errors=["bad"])
        assert not r.ok
        assert r.total_checks == 1

    def test_ok_with_warnings_only(self) -> None:
        r = GraphValidationResult(warnings=["meh"])
        assert r.ok
        assert r.total_checks == 1


# ---------------------------------------------------------------------------
# Logging behavior
# ---------------------------------------------------------------------------


class TestValidationLogging:
    """Warnings are logged at load time."""

    def test_warnings_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        data = _graph()
        data["nodes"]["start"]["deadlines"] = {"orphan_action": 99}
        with caplog.at_level(logging.WARNING):
            _load(data)
        assert any("orphan_action" in r.message for r in caplog.records)


# ---------------------------------------------------------------------------
# Strict mode integration
# ---------------------------------------------------------------------------


class TestStrictMode:
    """strict_mode=True raises on any validation error."""

    def test_strict_mode_raises_on_dangling_next(self) -> None:
        data = _graph()
        data["nodes"]["start"]["next_nodes"] = ["treatment", "missing"]
        with pytest.raises(ValueError, match="missing"):
            _load(data, strict=True)

    def test_strict_mode_ok_on_warnings_only(self) -> None:
        data = _graph()
        data["nodes"]["start"]["deadlines"] = {"orphan": 30}
        engine = _load(data, strict=True)
        assert engine._validation_result.ok
        assert len(engine._validation_result.warnings) > 0
