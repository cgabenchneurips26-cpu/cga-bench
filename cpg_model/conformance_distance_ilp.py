"""ILP-Based Exact Minimal-Repair Conformance Distance d_G.

Computes d_G(τ, p) = min_{τ' ∈ L(G,p)} cost(τ → τ') via joint ILP optimization
using PuLP / CBC solver. Interactions between constraint types are modeled
explicitly so deletions that resolve multiple violations are not double-counted.

Falls back to the tiered ConformanceDistanceSolver if PuLP fails to find
an optimal solution.
"""

from __future__ import annotations

import logging
from typing import Any

import pulp

from cga_bench.cpg_model.conformance_distance import (
    ConformanceDistanceSolver,
    ConstraintType,
    CostConfig,
    HardConstraint,
    RepairOp,
    _find_provenance,
    _find_provenance_pair,
    _get_insertion_time,
    _topological_reorder,
)
from cga_bench.cpg_model.schemas.base import Action, ActionType

logger = logging.getLogger(__name__)


class ILPConformanceDistanceSolver:
    """Exact minimal-repair conformance distance solver via ILP joint optimization.

    Models all repair operations as ILP variables and jointly minimizes total
    cost, correctly accounting for interactions (e.g., deleting a forbidden
    action also resolves any BEFORE violations involving that action).

    Falls back to ConformanceDistanceSolver on PuLP solve failure.
    """

    def __init__(self, cost_config: CostConfig | None = None) -> None:
        self.cost = cost_config or CostConfig()
        self._fallback = ConformanceDistanceSolver(cost_config)

    def compute(
        self,
        trace: list[Action],
        constraints: list[HardConstraint],
    ) -> ConformanceResult:
        """Compute exact d_G via ILP joint optimization.

        Args:
            trace: Agent action sequence with timestamps.
            constraints: Active hard constraints for this patient/scenario.

        Returns:
            ConformanceResult with distance, repair plan, and repaired trace.
        """
        if not constraints:
            return ConformanceResult(
                distance=0.0,
                is_conformant=True,
                violations=[],
                repair_plan=[],
                repair_trace=list(trace),
                cost_breakdown={"forbid": 0.0, "must": 0.0, "before": 0.0, "within": 0.0},
                n_repairs=0,
            )

        # Partition constraints by type
        forbid_cs = [c for c in constraints if c.type == ConstraintType.FORBID]
        must_cs = [c for c in constraints if c.type == ConstraintType.MUST]
        before_cs = [c for c in constraints if c.type == ConstraintType.BEFORE]
        within_cs = [c for c in constraints if c.type == ConstraintType.WITHIN]

        trace_ids = {a.action_id for a in trace}
        trace_pos = {a.action_id: i for i, a in enumerate(trace)}
        trace_time = {a.action_id: a.timestamp_minutes for a in trace}

        # ── Identify violations ──────────────────────────────────────────────

        # FORBID: actions in trace that are forbidden
        forbidden_ids: set[str] = set()
        for c in forbid_cs:
            for aid in c.actions:
                forbidden_ids.add(aid)
        forbidden_in_trace = forbidden_ids & trace_ids

        # MUST: required actions not in trace
        required_ids: set[str] = set()
        for c in must_cs:
            for aid in c.actions:
                required_ids.add(aid)
        missing_required = required_ids - trace_ids

        # BEFORE: violated pairs (a should come before b, but b comes first or equal)
        violated_before: list[tuple[str, str]] = []
        for c in before_cs:
            if len(c.actions) >= 2:
                a, b = c.actions[0], c.actions[1]
                if a in trace_ids and b in trace_ids:
                    if trace_pos.get(a, -1) >= trace_pos.get(b, -1):
                        violated_before.append((a, b))

        # WITHIN: actions that exceeded their deadline
        # Skip forbidden actions — they will be deleted, so WITHIN is moot
        violated_within: list[tuple[str, float, str]] = []  # (action_id, overtime, severity)
        for c in within_cs:
            if c.deadline is None:
                continue
            for aid in c.actions:
                if aid in trace_time and aid not in forbidden_in_trace:
                    overtime = trace_time[aid] - c.deadline
                    if overtime > 0:
                        violated_within.append((aid, overtime, c.severity))

        # No violations at all → d_G = 0
        if not forbidden_in_trace and not missing_required and not violated_before and not violated_within:
            return ConformanceResult(
                distance=0.0,
                is_conformant=True,
                violations=[],
                repair_plan=[],
                repair_trace=list(trace),
                cost_breakdown={"forbid": 0.0, "must": 0.0, "before": 0.0, "within": 0.0},
                n_repairs=0,
            )

        # ── Build ILP ────────────────────────────────────────────────────────

        prob = pulp.LpProblem("ConformanceDistance", pulp.LpMinimize)

        # x_del[aid] = 1 iff forbidden action `aid` is deleted (forced = 1 for all)
        x_del: dict[str, pulp.LpVariable] = {}
        for aid in forbidden_in_trace:
            x_del[aid] = pulp.LpVariable(f"del_{aid}", cat="Binary")
            # Deletion is forced for all forbidden actions in trace
            prob += x_del[aid] == 1, f"force_del_{aid}"

        # x_ins[aid] = 1 iff missing required action `aid` is inserted (forced = 1)
        x_ins: dict[str, pulp.LpVariable] = {}
        for aid in sorted(missing_required):
            x_ins[aid] = pulp.LpVariable(f"ins_{aid}", cat="Binary")
            prob += x_ins[aid] == 1, f"force_ins_{aid}"

        # x_swap[a,b]: binary — whether the BEFORE(a,b) violation is fixed by reorder
        # Constraint: x_swap[a,b] + x_del[a] + x_del[b] >= 1
        # (at least one repair must resolve each violated BEFORE pair)
        x_swap: dict[tuple[str, str], pulp.LpVariable] = {}
        for a, b in violated_before:
            key = (a, b)
            x_swap[key] = pulp.LpVariable(f"swap_{a}_{b}", cat="Binary")
            # If neither a nor b is deleted, a swap must happen
            del_a = x_del.get(a, pulp.lpSum([]))
            del_b = x_del.get(b, pulp.lpSum([]))
            # Build RHS terms — use 0 if not a deletion variable
            del_a_term = x_del[a] if a in x_del else 0
            del_b_term = x_del[b] if b in x_del else 0
            prob += x_swap[key] >= 1 - del_a_term - del_b_term, f"before_repair_{a}_{b}"

        # x_shift[aid]: continuous >= 0 — overtime minutes (fixed to actual overtime)
        x_shift: dict[str, tuple[pulp.LpVariable, float, str]] = {}
        for aid, overtime, severity in violated_within:
            var = pulp.LpVariable(f"shift_{aid}", lowBound=overtime)
            x_shift[aid] = (var, overtime, severity)

        # ── Objective ────────────────────────────────────────────────────────

        obj_terms: list[Any] = []

        # Forbid costs (forced deletions)
        for aid, var in x_del.items():
            obj_terms.append(self.cost.forbid * var)

        # Must costs (forced insertions)
        for aid, var in x_ins.items():
            obj_terms.append(self.cost.must * var)

        # Before swap costs
        for (a, b), var in x_swap.items():
            obj_terms.append(self.cost.before * var)

        # Within shift costs
        for aid, (var, overtime, severity) in x_shift.items():
            unit = self.cost.within_critical if severity == "CRITICAL" else self.cost.within_soft
            obj_terms.append(unit * var)

        prob += pulp.lpSum(obj_terms), "TotalCost"

        # ── Solve ─────────────────────────────────────────────────────────────

        prob.solve(pulp.PULP_CBC_CMD(msg=0))

        if prob.status != pulp.LpStatusOptimal:
            logger.warning(
                "ILP solve failed with status %s; falling back to tiered solver",
                pulp.LpStatus[prob.status],
            )
            return self._fallback.compute(trace, constraints)

        # ── Extract solution ─────────────────────────────────────────────────

        cost_forbid = 0.0
        cost_must = 0.0
        cost_before = 0.0
        cost_within = 0.0
        violations: list[dict[str, Any]] = []
        repairs: list[RepairOp] = []

        # Process deletions
        deleted_ids: set[str] = set()
        for aid, var in x_del.items():
            if pulp.value(var) > 0.5:
                deleted_ids.add(aid)
                cost_forbid += self.cost.forbid
                violations.append(
                    {
                        "type": "FORBID",
                        "action": aid,
                        "description": f"Forbidden action '{aid}' present in trace",
                    }
                )
                repairs.append(
                    RepairOp(
                        op_type="delete",
                        target_action=aid,
                        cost=self.cost.forbid,
                        constraint_ref=_find_provenance(forbid_cs, aid),
                        description=f"Delete forbidden action '{aid}'",
                    )
                )

        # Process insertions
        inserted_ids: set[str] = set()
        for aid, var in x_ins.items():
            if pulp.value(var) > 0.5:
                inserted_ids.add(aid)
                cost_must += self.cost.must
                violations.append(
                    {
                        "type": "MUST",
                        "action": aid,
                        "description": f"Required action '{aid}' missing from trace",
                    }
                )
                repairs.append(
                    RepairOp(
                        op_type="insert",
                        target_action=aid,
                        cost=self.cost.must,
                        constraint_ref=_find_provenance(must_cs, aid),
                        description=f"Insert missing required action '{aid}'",
                    )
                )

        # Process swaps (BEFORE repairs)
        swapped_pairs: list[tuple[str, str]] = []
        for (a, b), var in x_swap.items():
            if pulp.value(var) > 0.5:
                swapped_pairs.append((a, b))
                cost_before += self.cost.before
                violations.append(
                    {
                        "type": "BEFORE",
                        "action": f"{a} -> {b}",
                        "description": f"'{a}' must precede '{b}' but order is reversed",
                    }
                )
                repairs.append(
                    RepairOp(
                        op_type="reorder",
                        target_action=f"{a},{b}",
                        cost=self.cost.before,
                        constraint_ref=_find_provenance_pair(before_cs, a, b),
                        description=f"Reorder '{a}' before '{b}'",
                    )
                )

        # Record BEFORE violations resolved by deletion (no swap cost)
        for a, b in violated_before:
            if (a, b) not in x_swap or pulp.value(x_swap[(a, b)]) <= 0.5:
                if a in deleted_ids or b in deleted_ids:
                    violations.append(
                        {
                            "type": "BEFORE",
                            "action": f"{a} -> {b}",
                            "description": (
                                f"'{a}' must precede '{b}' — resolved by deletion of "
                                f"{'`' + a + '`' if a in deleted_ids else '`' + b + '`'}"
                            ),
                        }
                    )

        # Process timing shifts
        for aid, (var, overtime, severity) in x_shift.items():
            unit = self.cost.within_critical if severity == "CRITICAL" else self.cost.within_soft
            shift_cost = unit * overtime  # We report minimum required shift cost
            cost_within += shift_cost

            deadline = _get_deadline(aid, within_cs)
            actual_time = trace_time[aid]
            violations.append(
                {
                    "type": "WITHIN",
                    "action": aid,
                    "deadline": deadline,
                    "actual_time": actual_time,
                    "overtime": round(overtime, 2),
                    "description": (
                        f"'{aid}' at t={actual_time:.1f}min exceeds deadline {deadline:.1f}min by {overtime:.1f}min"
                    ),
                }
            )
            repairs.append(
                RepairOp(
                    op_type="shift",
                    target_action=aid,
                    cost=shift_cost,
                    constraint_ref=_find_provenance(within_cs, aid),
                    description=(
                        f"Shift '{aid}' from t={actual_time:.1f} to t≤{deadline:.1f} (overtime={overtime:.1f}min)"
                    ),
                )
            )

        # ── Build repair_trace ────────────────────────────────────────────────

        surviving = [a for a in trace if a.action_id not in deleted_ids]

        # Insert missing required actions
        for aid in sorted(inserted_ids):
            insert_time = _get_insertion_time(aid, within_cs, trace)
            surviving.append(
                Action(
                    type=ActionType.PROCEDURE,
                    action_id=aid,
                    args={},
                    timestamp_minutes=insert_time,
                )
            )

        surviving.sort(key=lambda a: a.timestamp_minutes)

        # Apply topological reorder for BEFORE constraints
        surviving_id_set = {a.action_id for a in surviving}
        active_before: list[tuple[str, str]] = []
        for c in before_cs:
            if len(c.actions) >= 2:
                a, b = c.actions[0], c.actions[1]
                if a in surviving_id_set and b in surviving_id_set:
                    active_before.append((a, b))

        if active_before:
            surviving = _topological_reorder(surviving, active_before)

        total_distance = cost_forbid + cost_must + cost_before + cost_within
        cost_breakdown = {
            "forbid": round(cost_forbid, 4),
            "must": round(cost_must, 4),
            "before": round(cost_before, 4),
            "within": round(cost_within, 4),
        }

        result = ConformanceResult(
            distance=round(total_distance, 4),
            is_conformant=total_distance == 0.0,
            violations=violations,
            repair_plan=repairs,
            repair_trace=surviving,
            cost_breakdown=cost_breakdown,
            n_repairs=len(repairs),
        )

        if not self._verify_repair(result.repair_trace, constraints):
            logger.warning("Post-verification failed: ILP repair_trace does not satisfy all constraints")

        return result

    def _verify_repair(
        self,
        repair_trace: list[Action],
        constraints: list[HardConstraint],
    ) -> bool:
        """Verify the repaired trace satisfies all hard constraints."""
        trace_ids = {a.action_id for a in repair_trace}
        trace_order = {a.action_id: i for i, a in enumerate(repair_trace)}
        trace_times = {a.action_id: a.timestamp_minutes for a in repair_trace}

        for c in constraints:
            if c.type == ConstraintType.FORBID:
                for aid in c.actions:
                    if aid in trace_ids:
                        return False
            elif c.type == ConstraintType.MUST:
                for aid in c.actions:
                    if aid not in trace_ids:
                        return False
            elif c.type == ConstraintType.BEFORE:
                if len(c.actions) >= 2:
                    a, b = c.actions[0], c.actions[1]
                    if a in trace_order and b in trace_order:
                        if trace_order[a] >= trace_order[b]:
                            return False
            elif c.type == ConstraintType.WITHIN:
                if c.deadline is not None:
                    for aid in c.actions:
                        if aid in trace_times and trace_times[aid] > c.deadline:
                            return False
        return True


# Re-export ConformanceResult for convenience (same type, different solver)
from cga_bench.cpg_model.conformance_distance import ConformanceResult  # noqa: E402


def _get_deadline(action_id: str, within_cs: list[HardConstraint]) -> float:
    """Return deadline for action_id from WITHIN constraints."""
    for c in within_cs:
        if action_id in c.actions and c.deadline is not None:
            return c.deadline
    return 0.0
