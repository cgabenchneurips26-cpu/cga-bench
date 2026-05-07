"""Tests for ILP-Based Exact Minimal-Repair Conformance Distance d_G.

10 test cases mirroring test_conformance_distance.py structure:
  1. Conformant trace (d_G = 0)
  2. Single FORBID violation
  3. Single MUST violation
  4. Single BEFORE violation
  5. Single WITHIN violation
  6. Joint repair — FORBID deletion resolves BEFORE (no double-count)
  7. Cascading BEFORE (a->b->c, trace=[c,a,b])
  8. Monotonicity (adding violations does not decrease d_G)
  9. Determinism (3 runs → same d_G)
  10. ILP d_G ≤ tiered d_G (ILP is at least as good)
"""

from __future__ import annotations

import pytest

from cga_bench.cpg_model.conformance_distance import (
    ConformanceDistanceSolver,
    ConstraintType,
    HardConstraint,
)
from cga_bench.cpg_model.conformance_distance_ilp import ILPConformanceDistanceSolver
from cga_bench.cpg_model.schemas.base import Action, ActionType

# ── Helpers ──────────────────────────────────────────────────


def _action(aid: str, t: float = 0.0) -> Action:
    return Action(type=ActionType.PROCEDURE, action_id=aid, args={}, timestamp_minutes=t)


def _forbid(action_id: str, severity: str = "CRITICAL") -> HardConstraint:
    return HardConstraint(
        type=ConstraintType.FORBID,
        actions=[action_id],
        severity=severity,
        provenance=f"test:forbid:{action_id}",
    )


def _must(action_id: str, severity: str = "HIGH") -> HardConstraint:
    return HardConstraint(
        type=ConstraintType.MUST,
        actions=[action_id],
        severity=severity,
        provenance=f"test:must:{action_id}",
    )


def _before(a: str, b: str, severity: str = "HIGH") -> HardConstraint:
    return HardConstraint(
        type=ConstraintType.BEFORE,
        actions=[a, b],
        severity=severity,
        provenance=f"test:before:{a}->{b}",
    )


def _within(
    action_id: str,
    deadline: float,
    severity: str = "CRITICAL",
) -> HardConstraint:
    return HardConstraint(
        type=ConstraintType.WITHIN,
        actions=[action_id],
        deadline=deadline,
        severity=severity,
        provenance=f"test:within:{action_id}@{deadline}",
    )


# ── Fixtures ──────────────────────────────────────────────────


@pytest.fixture
def solver() -> ILPConformanceDistanceSolver:
    return ILPConformanceDistanceSolver()


@pytest.fixture
def tiered() -> ConformanceDistanceSolver:
    return ConformanceDistanceSolver()


# ── Test 1: Conformant trace → d_G = 0 ───────────────────────


class TestConformantTrace:
    def test_conformant_trace(self, solver: ILPConformanceDistanceSolver) -> None:
        trace = [
            _action("blood_culture", t=2.0),
            _action("antibiotics", t=5.0),
            _action("fluid_bolus", t=10.0),
        ]
        constraints = [
            _must("blood_culture"),
            _must("antibiotics"),
            _before("blood_culture", "antibiotics"),
            _within("antibiotics", deadline=60.0),
        ]
        result = solver.compute(trace, constraints)

        assert result.distance == 0.0
        assert result.is_conformant is True
        assert len(result.violations) == 0
        assert result.n_repairs == 0


# ── Test 2: Single FORBID violation ──────────────────────────


class TestSingleForbid:
    def test_single_forbid(self, solver: ILPConformanceDistanceSolver) -> None:
        trace = [_action("nitroglycerin", t=5.0)]
        constraints = [_forbid("nitroglycerin")]

        result = solver.compute(trace, constraints)

        assert result.distance == 1000.0
        assert result.is_conformant is False
        forbid_violations = [v for v in result.violations if v["type"] == "FORBID"]
        assert len(forbid_violations) == 1
        assert forbid_violations[0]["action"] == "nitroglycerin"
        delete_ops = [r for r in result.repair_plan if r.op_type == "delete"]
        assert len(delete_ops) == 1
        assert result.cost_breakdown["forbid"] == 1000.0

    def test_forbidden_not_in_trace_is_zero(self, solver: ILPConformanceDistanceSolver) -> None:
        trace = [_action("aspirin", t=5.0)]
        constraints = [_forbid("nitroglycerin")]

        result = solver.compute(trace, constraints)
        assert result.distance == 0.0
        assert result.is_conformant is True


# ── Test 3: Single MUST missing → d_G = 5.0 ─────────────────


class TestSingleMustMissing:
    def test_single_must_missing(self, solver: ILPConformanceDistanceSolver) -> None:
        trace = [_action("aspirin", t=5.0)]
        constraints = [_must("blood_culture")]

        result = solver.compute(trace, constraints)

        assert result.distance == 5.0
        assert result.is_conformant is False
        must_violations = [v for v in result.violations if v["type"] == "MUST"]
        assert len(must_violations) == 1
        assert must_violations[0]["action"] == "blood_culture"
        insert_ops = [r for r in result.repair_plan if r.op_type == "insert"]
        assert len(insert_ops) == 1
        assert result.cost_breakdown["must"] == 5.0

    def test_must_present_is_zero(self, solver: ILPConformanceDistanceSolver) -> None:
        trace = [_action("blood_culture", t=5.0)]
        constraints = [_must("blood_culture")]

        result = solver.compute(trace, constraints)
        assert result.distance == 0.0
        assert result.is_conformant is True


# ── Test 4: Single BEFORE violation → d_G = 10.0 ────────────


class TestSingleBeforeViolation:
    def test_single_before_violation(self, solver: ILPConformanceDistanceSolver) -> None:
        # blood_culture must come before antibiotics, but antibiotics is first
        trace = [
            _action("antibiotics", t=2.0),
            _action("blood_culture", t=5.0),
        ]
        constraints = [_before("blood_culture", "antibiotics")]

        result = solver.compute(trace, constraints)

        assert result.distance == 10.0
        assert result.is_conformant is False
        before_violations = [v for v in result.violations if v["type"] == "BEFORE"]
        assert len(before_violations) >= 1
        reorder_ops = [r for r in result.repair_plan if r.op_type == "reorder"]
        assert len(reorder_ops) == 1
        assert result.cost_breakdown["before"] == 10.0

    def test_correct_order_is_zero(self, solver: ILPConformanceDistanceSolver) -> None:
        trace = [
            _action("blood_culture", t=2.0),
            _action("antibiotics", t=5.0),
        ]
        constraints = [_before("blood_culture", "antibiotics")]

        result = solver.compute(trace, constraints)
        assert result.distance == 0.0
        assert result.is_conformant is True


# ── Test 5: Single WITHIN violation → d_G = overtime * unit ──


class TestSingleWithinViolation:
    def test_single_within_violation(self, solver: ILPConformanceDistanceSolver) -> None:
        # antibiotics at t=70, deadline=60 → overtime=10min
        trace = [_action("antibiotics", t=70.0)]
        constraints = [_within("antibiotics", deadline=60.0, severity="CRITICAL")]

        result = solver.compute(trace, constraints)

        expected_cost = 100.0 * 10.0  # within_critical * overtime
        assert result.distance == pytest.approx(expected_cost, abs=1e-3)
        assert result.is_conformant is False
        within_violations = [v for v in result.violations if v["type"] == "WITHIN"]
        assert len(within_violations) == 1
        assert within_violations[0]["overtime"] == 10.0
        assert result.cost_breakdown["within"] == pytest.approx(expected_cost, abs=1e-3)

    def test_within_deadline_is_zero(self, solver: ILPConformanceDistanceSolver) -> None:
        trace = [_action("antibiotics", t=50.0)]
        constraints = [_within("antibiotics", deadline=60.0)]

        result = solver.compute(trace, constraints)
        assert result.distance == 0.0


# ── Test 6: Joint repair — FORBID deletion resolves BEFORE ───


class TestJointRepairForbidResolvesBefore:
    def test_joint_repair_forbid_resolves_before(self, solver: ILPConformanceDistanceSolver) -> None:
        """Deleting the forbidden action also eliminates the BEFORE violation.

        If computed independently: 1000 (forbid) + 10 (before) = 1010.
        ILP joint: only 1000, because deletion resolves BEFORE constraint.
        """
        trace = [
            _action("forbidden_drug", t=2.0),
            _action("blood_culture", t=5.0),
        ]
        constraints = [
            _forbid("forbidden_drug"),
            # blood_culture must come before forbidden_drug — resolved by deletion
            _before("blood_culture", "forbidden_drug"),
        ]

        result = solver.compute(trace, constraints)

        # Only FORBID cost; BEFORE is resolved for free by deletion
        assert result.distance == 1000.0
        assert result.cost_breakdown["forbid"] == 1000.0
        assert result.cost_breakdown["before"] == 0.0
        # Repair trace must not contain the forbidden drug
        repair_ids = {a.action_id for a in result.repair_trace}
        assert "forbidden_drug" not in repair_ids


# ── Test 7: Cascading BEFORE (a→b→c, trace=[c,a,b]) ─────────


class TestCascadingBefore:
    def test_cascading_before(self, solver: ILPConformanceDistanceSolver) -> None:
        """BEFORE(step_a, step_b) + BEFORE(step_b, step_c), trace=[step_c, step_a, step_b].

        At least one BEFORE violated (step_b → step_c inverted).
        Repair trace must have step_a < step_b < step_c.
        """
        trace = [
            _action("step_c", t=1.0),
            _action("step_a", t=2.0),
            _action("step_b", t=3.0),
        ]
        constraints = [
            _before("step_a", "step_b"),
            _before("step_b", "step_c"),
        ]

        result = solver.compute(trace, constraints)

        assert result.is_conformant is False
        before_violations = [v for v in result.violations if v["type"] == "BEFORE"]
        assert len(before_violations) >= 1
        assert result.cost_breakdown["before"] > 0

        repair_ids = [a.action_id for a in result.repair_trace]
        assert repair_ids.index("step_a") < repair_ids.index("step_b")
        assert repair_ids.index("step_b") < repair_ids.index("step_c")


# ── Test 8: Monotonicity ──────────────────────────────────────


class TestMonotonicity:
    def test_monotonicity(self, solver: ILPConformanceDistanceSolver) -> None:
        """Adding a violation should not decrease d_G."""
        trace = [
            _action("antibiotics", t=70.0),
            _action("forbidden_drug", t=80.0),
        ]

        constraints_base = [_within("antibiotics", deadline=60.0, severity="CRITICAL")]
        d_base = solver.compute(trace, constraints_base).distance

        constraints_extended = [
            _within("antibiotics", deadline=60.0, severity="CRITICAL"),
            _forbid("forbidden_drug"),
        ]
        d_extended = solver.compute(trace, constraints_extended).distance

        assert d_extended >= d_base

        constraints_more = constraints_extended + [_must("missing_lab")]
        d_more = solver.compute(trace, constraints_more).distance

        assert d_more >= d_extended


# ── Test 9: Determinism ───────────────────────────────────────


class TestDeterminism:
    def test_determinism(self, solver: ILPConformanceDistanceSolver) -> None:
        """Three runs with the same inputs must yield identical d_G."""
        trace = [
            _action("step_c", t=1.0),
            _action("step_a", t=2.0),
            _action("forbidden", t=3.0),
            _action("step_b", t=4.0),
        ]
        constraints = [
            _forbid("forbidden"),
            _must("missing_lab"),
            _before("step_a", "step_b"),
            _before("step_b", "step_c"),
            _within("step_a", deadline=1.5, severity="CRITICAL"),
        ]

        results = [solver.compute(trace, constraints) for _ in range(3)]

        assert results[0].distance == results[1].distance == results[2].distance
        assert results[0].cost_breakdown == results[1].cost_breakdown == results[2].cost_breakdown


# ── Test 10: ILP d_G ≤ tiered d_G ────────────────────────────


class TestILPLeqTiered:
    """ILP finds joint-optimal solution; tiered is greedy sequential.

    By construction, d_G(ILP) ≤ d_G(tiered) for all inputs.
    """

    def _check(
        self,
        solver: ILPConformanceDistanceSolver,
        tiered: ConformanceDistanceSolver,
        trace: list[Action],
        constraints: list[HardConstraint],
    ) -> None:
        ilp_dist = solver.compute(trace, constraints).distance
        tiered_dist = tiered.compute(trace, constraints).distance
        assert ilp_dist <= tiered_dist + 1e-6, f"ILP distance {ilp_dist} > tiered distance {tiered_dist}"

    def test_ilp_leq_tiered_conformant(
        self,
        solver: ILPConformanceDistanceSolver,
        tiered: ConformanceDistanceSolver,
    ) -> None:
        trace = [_action("blood_culture", t=2.0), _action("antibiotics", t=5.0)]
        constraints = [_must("blood_culture"), _before("blood_culture", "antibiotics")]
        self._check(solver, tiered, trace, constraints)

    def test_ilp_leq_tiered_single_forbid(
        self,
        solver: ILPConformanceDistanceSolver,
        tiered: ConformanceDistanceSolver,
    ) -> None:
        trace = [_action("nitroglycerin", t=5.0)]
        constraints = [_forbid("nitroglycerin")]
        self._check(solver, tiered, trace, constraints)

    def test_ilp_leq_tiered_joint_repair(
        self,
        solver: ILPConformanceDistanceSolver,
        tiered: ConformanceDistanceSolver,
    ) -> None:
        """Key case: ILP must be strictly ≤ tiered for joint FORBID+BEFORE."""
        trace = [
            _action("forbidden_drug", t=2.0),
            _action("blood_culture", t=5.0),
        ]
        constraints = [
            _forbid("forbidden_drug"),
            _before("blood_culture", "forbidden_drug"),
        ]
        ilp_dist = solver.compute(trace, constraints).distance
        tiered_dist = tiered.compute(trace, constraints).distance
        # ILP correctly finds 1000; tiered also finds 1000 (it processes FORBID first)
        assert ilp_dist <= tiered_dist + 1e-6

    def test_ilp_leq_tiered_cascading(
        self,
        solver: ILPConformanceDistanceSolver,
        tiered: ConformanceDistanceSolver,
    ) -> None:
        trace = [_action("step_c", t=1.0), _action("step_a", t=2.0), _action("step_b", t=3.0)]
        constraints = [_before("step_a", "step_b"), _before("step_b", "step_c")]
        self._check(solver, tiered, trace, constraints)

    def test_ilp_leq_tiered_mixed(
        self,
        solver: ILPConformanceDistanceSolver,
        tiered: ConformanceDistanceSolver,
    ) -> None:
        trace = [
            _action("forbidden", t=1.0),
            _action("step_b", t=2.0),
            _action("step_a", t=3.0),
            _action("late_action", t=90.0),
        ]
        constraints = [
            _forbid("forbidden"),
            _must("missing_lab"),
            _before("step_a", "step_b"),
            _within("late_action", deadline=60.0, severity="CRITICAL"),
        ]
        self._check(solver, tiered, trace, constraints)
