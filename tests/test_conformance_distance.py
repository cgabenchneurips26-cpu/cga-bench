"""Tests for Exact Minimal-Repair Conformance Distance d_G.

14 test cases covering:
  1. Conformant trace (d_G = 0)
  2. Single FORBID violation
  3. Single MUST violation
  4. Single BEFORE violation
  5. Single WITHIN violation
  6. Joint repair (FORBID deletion fixes BEFORE too)
  7. Cascading BEFORE (a->b->c, trace=[c,a,b])
  8. FORBID + MUST on different actions (additive)
  9. Monotonicity (Proposition 2)
  10. Determinism (3x same input -> same d_G)
  11. from_guideline_output converter
  12. from_derived_constraint_set converter
  13. Empty trace with MUST constraints
  14. Empty constraints -> d_G = 0
"""

from __future__ import annotations

import pytest

from cga_bench.cpg_model.conformance_distance import (
    ConformanceDistanceSolver,
    ConstraintType,
    CostConfig,
    HardConstraint,
    from_derived_constraint_set,
    from_guideline_output,
)
from cga_bench.cpg_model.schemas.base import Action, ActionType

# ── Helpers ──────────────────────────────────────────────────


def _action(aid: str, t: float = 0.0, atype: ActionType = ActionType.PROCEDURE) -> Action:
    """Create a minimal Action for testing."""
    return Action(type=atype, action_id=aid, args={}, timestamp_minutes=t)


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


# ── Fixtures ─────────────────────────────────────────────────


@pytest.fixture
def solver() -> ConformanceDistanceSolver:
    return ConformanceDistanceSolver()


@pytest.fixture
def custom_solver() -> ConformanceDistanceSolver:
    return ConformanceDistanceSolver(
        CostConfig(
            forbid=100.0,
            within_critical=50.0,
            before=5.0,
            must=3.0,
            within_soft=0.5,
        )
    )


# ── Test 1: Conformant trace -> d_G = 0 ─────────────────────


class TestConformantTrace:
    def test_all_constraints_met(self, solver: ConformanceDistanceSolver) -> None:
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
        assert len(result.repair_plan) == 0
        assert result.n_repairs == 0


# ── Test 2: Single FORBID violation ──────────────────────────


class TestSingleForbid:
    def test_forbidden_action_in_trace(self, solver: ConformanceDistanceSolver) -> None:
        trace = [_action("nitroglycerin", t=5.0)]
        constraints = [_forbid("nitroglycerin")]

        result = solver.compute(trace, constraints)

        assert result.distance == 1000.0  # cost_forbid
        assert result.is_conformant is False
        assert len(result.violations) == 1
        assert result.violations[0]["type"] == "FORBID"
        assert result.violations[0]["action"] == "nitroglycerin"
        assert result.n_repairs == 1
        assert result.repair_plan[0].op_type == "delete"
        assert result.cost_breakdown["forbid"] == 1000.0

    def test_forbidden_action_not_in_trace(self, solver: ConformanceDistanceSolver) -> None:
        trace = [_action("aspirin", t=5.0)]
        constraints = [_forbid("nitroglycerin")]

        result = solver.compute(trace, constraints)
        assert result.distance == 0.0
        assert result.is_conformant is True


# ── Test 3: Single MUST violation ────────────────────────────


class TestSingleMust:
    def test_required_action_missing(self, solver: ConformanceDistanceSolver) -> None:
        trace = [_action("aspirin", t=5.0)]
        constraints = [_must("blood_culture")]

        result = solver.compute(trace, constraints)

        assert result.distance == 5.0  # cost_must
        assert result.is_conformant is False
        assert len(result.violations) == 1
        assert result.violations[0]["type"] == "MUST"
        assert result.violations[0]["action"] == "blood_culture"
        assert result.repair_plan[0].op_type == "insert"
        assert result.cost_breakdown["must"] == 5.0

    def test_required_action_present(self, solver: ConformanceDistanceSolver) -> None:
        trace = [_action("blood_culture", t=5.0)]
        constraints = [_must("blood_culture")]

        result = solver.compute(trace, constraints)
        assert result.distance == 0.0
        assert result.is_conformant is True


# ── Test 4: Single BEFORE violation ──────────────────────────


class TestSingleBefore:
    def test_order_reversed(self, solver: ConformanceDistanceSolver) -> None:
        # antibiotics BEFORE blood_culture — but constraint says blood_culture before antibiotics
        trace = [
            _action("antibiotics", t=2.0),
            _action("blood_culture", t=5.0),
        ]
        constraints = [_before("blood_culture", "antibiotics")]

        result = solver.compute(trace, constraints)

        assert result.distance == 10.0  # cost_before
        assert result.is_conformant is False
        assert len(result.violations) == 1
        assert result.violations[0]["type"] == "BEFORE"
        assert result.repair_plan[0].op_type == "reorder"
        assert result.cost_breakdown["before"] == 10.0

    def test_order_correct(self, solver: ConformanceDistanceSolver) -> None:
        trace = [
            _action("blood_culture", t=2.0),
            _action("antibiotics", t=5.0),
        ]
        constraints = [_before("blood_culture", "antibiotics")]

        result = solver.compute(trace, constraints)
        assert result.distance == 0.0
        assert result.is_conformant is True


# ── Test 5: Single WITHIN violation ──────────────────────────


class TestSingleWithin:
    def test_deadline_exceeded(self, solver: ConformanceDistanceSolver) -> None:
        # Action at t=70, deadline=60 -> 10min overtime
        trace = [_action("antibiotics", t=70.0)]
        constraints = [_within("antibiotics", deadline=60.0, severity="CRITICAL")]

        result = solver.compute(trace, constraints)

        expected_cost = 100.0 * 10.0  # within_critical * overtime
        assert result.distance == expected_cost
        assert result.is_conformant is False
        assert result.violations[0]["type"] == "WITHIN"
        assert result.violations[0]["overtime"] == 10.0
        assert result.cost_breakdown["within"] == expected_cost

    def test_within_deadline(self, solver: ConformanceDistanceSolver) -> None:
        trace = [_action("antibiotics", t=50.0)]
        constraints = [_within("antibiotics", deadline=60.0)]

        result = solver.compute(trace, constraints)
        assert result.distance == 0.0

    def test_soft_within_cost(self, solver: ConformanceDistanceSolver) -> None:
        # Non-critical severity -> within_soft cost
        trace = [_action("reassess", t=130.0)]
        constraints = [_within("reassess", deadline=120.0, severity="HIGH")]

        result = solver.compute(trace, constraints)

        expected_cost = 1.0 * 10.0  # within_soft * overtime
        assert result.distance == expected_cost


# ── Test 6: Joint repair — FORBID deletion fixes BEFORE too ──


class TestJointRepair:
    def test_forbid_deletion_resolves_before(self, solver: ConformanceDistanceSolver) -> None:
        """If deleting a forbidden action also eliminates a BEFORE violation,
        joint cost < sum(individual costs).
        """
        trace = [
            _action("forbidden_drug", t=2.0),
            _action("blood_culture", t=5.0),
        ]
        constraints = [
            _forbid("forbidden_drug"),
            # blood_culture must come before forbidden_drug
            # but since forbidden_drug gets deleted, this BEFORE is resolved
            _before("blood_culture", "forbidden_drug"),
        ]

        result = solver.compute(trace, constraints)

        # Only FORBID cost — BEFORE is resolved by deletion
        assert result.distance == 1000.0  # Just cost_forbid
        # If independent: 1000 (forbid) + 10 (before) = 1010
        # Joint: only 1000 because deletion resolves the BEFORE
        independent_sum = 1000.0 + 10.0
        assert result.distance < independent_sum


# ── Test 7: Cascading BEFORE — a->b->c, trace=[c,a,b] ───────


class TestCascadingBefore:
    def test_triple_chain_inversion(self, solver: ConformanceDistanceSolver) -> None:
        """BEFORE(a,b) + BEFORE(b,c) with trace [c, a, b].
        Violations: c appears before a and b.
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
        # At least one BEFORE violation: step_b -> step_c is inverted (c is before b)
        before_violations = [v for v in result.violations if v["type"] == "BEFORE"]
        assert len(before_violations) >= 1
        # Cost = n_inversions * cost_before
        assert result.cost_breakdown["before"] > 0

        # Repair trace should have correct order: step_a, step_b, step_c
        repair_ids = [a.action_id for a in result.repair_trace]
        assert repair_ids.index("step_a") < repair_ids.index("step_b")
        assert repair_ids.index("step_b") < repair_ids.index("step_c")


# ── Test 8: FORBID + MUST on different actions (additive) ────


class TestAdditiveRepairs:
    def test_forbid_plus_must(self, solver: ConformanceDistanceSolver) -> None:
        trace = [_action("forbidden_drug", t=5.0)]
        constraints = [
            _forbid("forbidden_drug"),
            _must("required_lab"),
        ]

        result = solver.compute(trace, constraints)

        # Both repairs needed independently
        expected = 1000.0 + 5.0  # forbid + must
        assert result.distance == expected
        assert result.n_repairs == 2
        assert result.cost_breakdown["forbid"] == 1000.0
        assert result.cost_breakdown["must"] == 5.0


# ── Test 9: Monotonicity (Proposition 2) ─────────────────────


class TestMonotonicity:
    def test_more_violations_higher_distance(self, solver: ConformanceDistanceSolver) -> None:
        """Adding violations should never decrease d_G."""
        trace = [
            _action("antibiotics", t=70.0),
            _action("forbidden_drug", t=80.0),
        ]

        # Base: just WITHIN
        constraints_base = [
            _within("antibiotics", deadline=60.0, severity="CRITICAL"),
        ]
        d_base = solver.compute(trace, constraints_base).distance

        # Extended: WITHIN + FORBID
        constraints_extended = [
            _within("antibiotics", deadline=60.0, severity="CRITICAL"),
            _forbid("forbidden_drug"),
        ]
        d_extended = solver.compute(trace, constraints_extended).distance

        assert d_extended >= d_base

        # Further extended: + MUST
        constraints_more = constraints_extended + [_must("missing_lab")]
        d_more = solver.compute(trace, constraints_more).distance

        assert d_more >= d_extended


# ── Test 10: Determinism — 3x same input -> same d_G ────────


class TestDeterminism:
    def test_reproducible_results(self, solver: ConformanceDistanceSolver) -> None:
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
        assert results[0].n_repairs == results[1].n_repairs == results[2].n_repairs
        assert results[0].cost_breakdown == results[1].cost_breakdown == results[2].cost_breakdown


# ── Test 11: from_guideline_output converter ─────────────────


class TestFromGuidelineOutput:
    def test_conversion(self) -> None:
        """GuidelineEngineOutput → list[HardConstraint]."""
        from cga_bench.cpg_model.schemas.base import GuidelineEngineOutput

        geo = GuidelineEngineOutput(
            current_node_id="node_1",
            mandatory_actions={"blood_culture", "antibiotics"},
            forbidden_actions={"nitroglycerin"},
            deadlines={"antibiotics": 60.0, "fluid_bolus": 120.0},
            required_prior_actions={"antibiotics": ["blood_culture"]},
        )

        constraints = from_guideline_output(geo)

        types = {c.type for c in constraints}
        assert ConstraintType.FORBID in types
        assert ConstraintType.MUST in types
        assert ConstraintType.BEFORE in types
        assert ConstraintType.WITHIN in types

        forbids = [c for c in constraints if c.type == ConstraintType.FORBID]
        assert len(forbids) == 1
        assert forbids[0].actions == ["nitroglycerin"]

        musts = [c for c in constraints if c.type == ConstraintType.MUST]
        assert len(musts) == 2
        must_ids = {c.actions[0] for c in musts}
        assert must_ids == {"blood_culture", "antibiotics"}

        befores = [c for c in constraints if c.type == ConstraintType.BEFORE]
        assert len(befores) == 1
        assert befores[0].actions == ["blood_culture", "antibiotics"]

        withins = [c for c in constraints if c.type == ConstraintType.WITHIN]
        assert len(withins) == 2

    def test_scenario_overrides(self) -> None:
        """Scenario-level forbidden/expected merge into constraints."""
        from cga_bench.cpg_model.schemas.base import GuidelineEngineOutput

        geo = GuidelineEngineOutput(
            current_node_id="node_1",
            forbidden_actions={"drug_a"},
            mandatory_actions={"lab_a"},
        )
        constraints = from_guideline_output(
            geo,
            scenario_forbidden=["drug_b"],
            scenario_expected=["lab_b"],
        )

        forbid_ids = {c.actions[0] for c in constraints if c.type == ConstraintType.FORBID}
        must_ids = {c.actions[0] for c in constraints if c.type == ConstraintType.MUST}

        assert forbid_ids == {"drug_a", "drug_b"}
        assert must_ids == {"lab_a", "lab_b"}


# ── Test 12: from_derived_constraint_set converter ───────────


class TestFromDerivedConstraintSet:
    def test_conversion(self) -> None:
        """DerivedConstraintSet + deadlines → list[HardConstraint]."""
        from types import SimpleNamespace

        # Mock DerivedConstraintSet structure
        dcs = SimpleNamespace(
            forbidden=[
                SimpleNamespace(
                    actions=["nitroglycerin"],
                    severity="CRITICAL",
                    provenance="graph:aha:node:rv_trap",
                ),
            ],
            required=[
                SimpleNamespace(
                    actions=["blood_culture"],
                    severity="HIGH",
                    provenance="graph:ssc:node:cultures",
                ),
            ],
            expected=[
                SimpleNamespace(
                    actions=["fluid_bolus"],
                    severity="MODERATE",
                    provenance="graph:ssc:node:fluids",
                ),
            ],
            before=[
                SimpleNamespace(
                    actions=["blood_culture", "antibiotics"],
                    severity="HIGH",
                    provenance="graph:ssc:node:cultures->abx",
                ),
            ],
            within=[
                SimpleNamespace(
                    actions=["antibiotics"],
                    severity="CRITICAL",
                    provenance="graph:ssc:node:abx_timing",
                ),
            ],
        )
        deadlines = {"antibiotics": 60.0, "fluid_bolus": 30.0}

        constraints = from_derived_constraint_set(dcs, deadlines)

        forbids = [c for c in constraints if c.type == ConstraintType.FORBID]
        musts = [c for c in constraints if c.type == ConstraintType.MUST]
        befores = [c for c in constraints if c.type == ConstraintType.BEFORE]
        withins = [c for c in constraints if c.type == ConstraintType.WITHIN]

        assert len(forbids) == 1
        assert forbids[0].actions == ["nitroglycerin"]

        assert len(musts) == 2  # required + expected
        must_ids = {c.actions[0] for c in musts}
        assert must_ids == {"blood_culture", "fluid_bolus"}

        assert len(befores) == 1
        assert befores[0].actions == ["blood_culture", "antibiotics"]

        # WITHIN: antibiotics from dcs.within + fluid_bolus from deadlines
        assert len(withins) == 2
        within_ids = {c.actions[0] for c in withins}
        assert within_ids == {"antibiotics", "fluid_bolus"}


# ── Test 13: Empty trace with MUST constraints ───────────────


class TestEmptyTrace:
    def test_empty_trace_must(self, solver: ConformanceDistanceSolver) -> None:
        trace: list[Action] = []
        constraints = [
            _must("blood_culture"),
            _must("antibiotics"),
            _must("fluid_bolus"),
        ]

        result = solver.compute(trace, constraints)

        expected = 3 * 5.0  # 3 × cost_must
        assert result.distance == expected
        assert result.n_repairs == 3
        assert all(r.op_type == "insert" for r in result.repair_plan)


# ── Test 14: Empty constraints -> d_G = 0 ────────────────────


class TestEmptyConstraints:
    def test_any_trace_zero_distance(self, solver: ConformanceDistanceSolver) -> None:
        trace = [
            _action("random_action_1", t=1.0),
            _action("random_action_2", t=50.0),
            _action("random_action_3", t=100.0),
        ]
        constraints: list[HardConstraint] = []

        result = solver.compute(trace, constraints)

        assert result.distance == 0.0
        assert result.is_conformant is True
        assert len(result.violations) == 0
        assert result.n_repairs == 0

    def test_empty_trace_empty_constraints(self, solver: ConformanceDistanceSolver) -> None:
        result = solver.compute([], [])
        assert result.distance == 0.0
        assert result.is_conformant is True


# ── Additional: Custom cost config ───────────────────────────


class TestCustomCostConfig:
    def test_custom_costs(self, custom_solver: ConformanceDistanceSolver) -> None:
        """Verify custom cost config is applied."""
        trace = [_action("forbidden_drug", t=5.0)]
        constraints = [_forbid("forbidden_drug")]

        result = custom_solver.compute(trace, constraints)

        assert result.distance == 100.0  # custom forbid cost
        assert result.cost_breakdown["forbid"] == 100.0


# ── Additional: Post-verification ────────────────────────────


class TestPostVerification:
    def test_repair_trace_is_conformant(self, solver: ConformanceDistanceSolver) -> None:
        """Repair trace should satisfy all constraints after repair."""
        trace = [
            _action("forbidden_drug", t=2.0),
            _action("antibiotics", t=5.0),
        ]
        constraints = [
            _forbid("forbidden_drug"),
            _must("blood_culture"),
            _must("antibiotics"),
        ]

        result = solver.compute(trace, constraints)

        # Verify repair_trace manually
        repair_ids = {a.action_id for a in result.repair_trace}
        assert "forbidden_drug" not in repair_ids  # deleted
        assert "blood_culture" in repair_ids  # inserted
        assert "antibiotics" in repair_ids  # kept

    def test_before_repair_trace_order(self, solver: ConformanceDistanceSolver) -> None:
        """After BEFORE repair, trace order respects constraints."""
        trace = [
            _action("step_b", t=1.0),
            _action("step_a", t=2.0),
        ]
        constraints = [_before("step_a", "step_b")]

        result = solver.compute(trace, constraints)

        repair_ids = [a.action_id for a in result.repair_trace]
        assert repair_ids.index("step_a") < repair_ids.index("step_b")
