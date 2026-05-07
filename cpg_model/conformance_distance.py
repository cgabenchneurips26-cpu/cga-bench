"""Exact Minimal-Repair Conformance Distance d_G.

Computes d_G(τ, p) = min_{τ' ∈ L(G,p)} cost(τ → τ') via tiered repair:
  Phase 1: FORBID — delete forbidden actions (deterministic)
  Phase 2: MUST   — insert missing required actions (deterministic)
  Phase 3: BEFORE — fix ordering inversions (topological sort)
  Phase 4: WITHIN — fix timing overruns (deterministic)

Interactions handled by recalculating phases 3-4 after phases 1-2.
No external dependencies — pure algorithmic computation.
"""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from enum import Enum
import logging
from typing import Any

from cga_bench.cpg_model.schemas.base import Action, ActionType

logger = logging.getLogger(__name__)


# ============================================================
# Cost Configuration
# ============================================================


@dataclass
class CostConfig:
    """Tiered cost weights reflecting clinical priority."""

    forbid: float = 1000.0  # Patient safety — highest priority
    within_critical: float = 100.0  # Time-urgent (e.g., antibiotics ≤60min)
    before: float = 10.0  # Sequence violation
    must: float = 5.0  # Omission (required action missing)
    within_soft: float = 1.0  # Non-urgent timing


# ============================================================
# Constraint Types
# ============================================================


class ConstraintType(str, Enum):
    """The four hard-constraint operators."""

    FORBID = "FORBID"
    MUST = "MUST"
    BEFORE = "BEFORE"
    WITHIN = "WITHIN"


@dataclass
class HardConstraint:
    """Unified constraint for d_G computation.

    Args:
        type: Constraint operator.
        actions: [a] for FORBID/MUST/WITHIN; [a, b] for BEFORE(a before b).
        deadline: Minutes from arrival. Only for WITHIN.
        severity: CRITICAL, HIGH, MODERATE, LOW.
        provenance: Traceability string (graph:X:node:Y:rule:Z).
    """

    type: ConstraintType
    actions: list[str]
    deadline: float | None = None
    severity: str = "HIGH"
    provenance: str = ""


# ============================================================
# Repair Operations & Result
# ============================================================


@dataclass
class RepairOp:
    """A single repair operation in the minimum-cost repair plan."""

    op_type: str  # "delete", "insert", "reorder", "shift"
    target_action: str
    cost: float
    constraint_ref: str
    description: str


@dataclass
class ConformanceResult:
    """Output of d_G computation."""

    distance: float  # d_G(τ, p) — 0.0 means conformant
    is_conformant: bool
    violations: list[dict[str, Any]]
    repair_plan: list[RepairOp]
    repair_trace: list[Action]  # Conformant trace after repairs
    cost_breakdown: dict[str, float]  # Per-tier costs
    n_repairs: int


# ============================================================
# Solver
# ============================================================


class ConformanceDistanceSolver:
    """Exact minimal-repair conformance distance solver."""

    def __init__(self, cost_config: CostConfig | None = None) -> None:
        self.cost = cost_config or CostConfig()

    def compute(
        self,
        trace: list[Action],
        constraints: list[HardConstraint],
    ) -> ConformanceResult:
        """Compute d_G(τ, p).

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

        violations: list[dict[str, Any]] = []
        repairs: list[RepairOp] = []
        cost_forbid = 0.0
        cost_must = 0.0
        cost_before = 0.0
        cost_within = 0.0

        # Build mutable trace (list of action_ids with positions)
        surviving = list(trace)  # will be mutated

        # ── Phase 1: FORBID — delete forbidden actions ──
        forbidden_ids = set()
        for c in forbid_cs:
            for action_id in c.actions:
                forbidden_ids.add(action_id)

        to_delete_indices: list[int] = []
        for i, action in enumerate(surviving):
            if action.action_id in forbidden_ids:
                to_delete_indices.append(i)
                cost_forbid += self.cost.forbid
                violations.append(
                    {
                        "type": "FORBID",
                        "action": action.action_id,
                        "description": f"Forbidden action '{action.action_id}' present in trace",
                    }
                )
                repairs.append(
                    RepairOp(
                        op_type="delete",
                        target_action=action.action_id,
                        cost=self.cost.forbid,
                        constraint_ref=_find_provenance(forbid_cs, action.action_id),
                        description=f"Delete forbidden action '{action.action_id}'",
                    )
                )

        # Delete in reverse order to preserve indices
        for i in reversed(to_delete_indices):
            surviving.pop(i)

        # ── Phase 2: MUST — insert missing required actions ──
        surviving_ids = {a.action_id for a in surviving}
        inserted_actions: list[Action] = []

        # Collect all required action IDs
        required_ids: set[str] = set()
        for c in must_cs:
            for action_id in c.actions:
                required_ids.add(action_id)

        for action_id in sorted(required_ids):
            if action_id not in surviving_ids:
                # Determine insertion timestamp from WITHIN deadline if available
                insert_time = _get_insertion_time(action_id, within_cs, trace)
                inserted = Action(
                    type=ActionType.PROCEDURE,
                    action_id=action_id,
                    args={},
                    timestamp_minutes=insert_time,
                )
                inserted_actions.append(inserted)
                surviving_ids.add(action_id)
                cost_must += self.cost.must
                violations.append(
                    {
                        "type": "MUST",
                        "action": action_id,
                        "description": f"Required action '{action_id}' missing from trace",
                    }
                )
                repairs.append(
                    RepairOp(
                        op_type="insert",
                        target_action=action_id,
                        cost=self.cost.must,
                        constraint_ref=_find_provenance(must_cs, action_id),
                        description=f"Insert missing required action '{action_id}'",
                    )
                )

        # Merge inserted actions into surviving trace (sorted by timestamp)
        surviving.extend(inserted_actions)
        surviving.sort(key=lambda a: a.timestamp_minutes)

        # ── Phase 3: BEFORE — fix ordering inversions ──
        # Build DAG over actions present in surviving trace
        surviving_id_set = {a.action_id for a in surviving}
        active_before: list[tuple[str, str]] = []
        for c in before_cs:
            if len(c.actions) >= 2:
                a_before, b_after = c.actions[0], c.actions[1]
                # Only check if both actions are in surviving trace
                if a_before in surviving_id_set and b_after in surviving_id_set:
                    active_before.append((a_before, b_after))

        if active_before:
            n_inversions, inversion_details = _count_inversions(surviving, active_before)
            cost_before = n_inversions * self.cost.before
            for a_id, b_id in inversion_details:
                violations.append(
                    {
                        "type": "BEFORE",
                        "action": f"{a_id} -> {b_id}",
                        "description": f"'{a_id}' must precede '{b_id}' but order is reversed",
                    }
                )
                repairs.append(
                    RepairOp(
                        op_type="reorder",
                        target_action=f"{a_id},{b_id}",
                        cost=self.cost.before,
                        constraint_ref=_find_provenance_pair(before_cs, a_id, b_id),
                        description=f"Reorder '{a_id}' before '{b_id}'",
                    )
                )

            # Apply topological reorder to build repair_trace
            surviving = _topological_reorder(surviving, active_before)

        # ── Phase 4: WITHIN — fix timing overruns ──
        for c in within_cs:
            if c.deadline is None:
                continue
            for action_id in c.actions:
                action = _find_action(surviving, action_id)
                if action is None:
                    continue  # Not in trace (handled by MUST or not required)
                overtime = action.timestamp_minutes - c.deadline
                if overtime > 0:
                    unit_cost = self.cost.within_critical if c.severity == "CRITICAL" else self.cost.within_soft
                    shift_cost = unit_cost * overtime
                    cost_within += shift_cost
                    violations.append(
                        {
                            "type": "WITHIN",
                            "action": action_id,
                            "deadline": c.deadline,
                            "actual_time": action.timestamp_minutes,
                            "overtime": round(overtime, 2),
                            "description": (
                                f"'{action_id}' at t={action.timestamp_minutes:.1f}min "
                                f"exceeds deadline {c.deadline:.1f}min by {overtime:.1f}min"
                            ),
                        }
                    )
                    repairs.append(
                        RepairOp(
                            op_type="shift",
                            target_action=action_id,
                            cost=shift_cost,
                            constraint_ref=c.provenance,
                            description=(
                                f"Shift '{action_id}' from t={action.timestamp_minutes:.1f} "
                                f"to t≤{c.deadline:.1f} (overtime={overtime:.1f}min)"
                            ),
                        )
                    )

        # ── Aggregate ──
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

        # Post-verification
        if not self._verify_repair(result.repair_trace, constraints):
            logger.warning("Post-verification failed: repair_trace does not satisfy all constraints")

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


# ============================================================
# Converters: existing types → HardConstraint
# ============================================================


def from_guideline_output(
    geo: Any,
    scenario_forbidden: list[str] | None = None,
    scenario_expected: list[str] | None = None,
) -> list[HardConstraint]:
    """Convert GuidelineEngineOutput → list[HardConstraint].

    Args:
        geo: GuidelineEngineOutput instance.
        scenario_forbidden: Additional forbidden actions from scenario definition.
        scenario_expected: Additional expected/mandatory actions from scenario.
    """
    constraints: list[HardConstraint] = []

    # FORBID from engine + scenario
    all_forbidden = set(getattr(geo, "forbidden_actions", set()))
    if scenario_forbidden:
        all_forbidden.update(scenario_forbidden)
    for action_id in sorted(all_forbidden):
        constraints.append(
            HardConstraint(
                type=ConstraintType.FORBID,
                actions=[action_id],
                severity="CRITICAL",
                provenance=f"engine:forbidden:{action_id}",
            )
        )

    # MUST from engine + scenario
    all_mandatory = set(getattr(geo, "mandatory_actions", set()))
    if scenario_expected:
        all_mandatory.update(scenario_expected)
    for action_id in sorted(all_mandatory):
        constraints.append(
            HardConstraint(
                type=ConstraintType.MUST,
                actions=[action_id],
                severity="HIGH",
                provenance=f"engine:mandatory:{action_id}",
            )
        )

    # BEFORE from required_prior_actions
    rpa = getattr(geo, "required_prior_actions", {})
    for action_id, priors in rpa.items():
        for prior in priors:
            constraints.append(
                HardConstraint(
                    type=ConstraintType.BEFORE,
                    actions=[prior, action_id],
                    severity="HIGH",
                    provenance=f"engine:before:{prior}->{action_id}",
                )
            )

    # WITHIN from deadlines
    deadlines = getattr(geo, "deadlines", {})
    for action_id, deadline in deadlines.items():
        constraints.append(
            HardConstraint(
                type=ConstraintType.WITHIN,
                actions=[action_id],
                deadline=deadline,
                severity="CRITICAL" if deadline <= 60 else "HIGH",
                provenance=f"engine:within:{action_id}@{deadline}min",
            )
        )

    return constraints


def from_derived_constraint_set(
    dcs: Any,
    deadlines: dict[str, float] | None = None,
) -> list[HardConstraint]:
    """Convert DerivedConstraintSet + deadlines → list[HardConstraint].

    Args:
        dcs: DerivedConstraintSet instance.
        deadlines: Optional {action_id: deadline_minutes} for WITHIN constraints.
    """
    constraints: list[HardConstraint] = []

    # FORBIDDEN → FORBID
    for dc in getattr(dcs, "forbidden", []):
        for action_id in dc.actions:
            constraints.append(
                HardConstraint(
                    type=ConstraintType.FORBID,
                    actions=[action_id],
                    severity=dc.severity,
                    provenance=dc.provenance,
                )
            )

    # REQUIRED + EXPECTED → MUST
    for dc in getattr(dcs, "required", []) + getattr(dcs, "expected", []):
        for action_id in dc.actions:
            constraints.append(
                HardConstraint(
                    type=ConstraintType.MUST,
                    actions=[action_id],
                    severity=dc.severity,
                    provenance=dc.provenance,
                )
            )

    # BEFORE → BEFORE (actions=[prior, dependent])
    for dc in getattr(dcs, "before", []):
        if len(dc.actions) >= 2:
            constraints.append(
                HardConstraint(
                    type=ConstraintType.BEFORE,
                    actions=dc.actions[:2],
                    severity=dc.severity,
                    provenance=dc.provenance,
                )
            )

    # WITHIN from DerivedConstraintSet + external deadlines
    for dc in getattr(dcs, "within", []):
        for action_id in dc.actions:
            dl = deadlines.get(action_id) if deadlines else None
            if dl is not None:
                constraints.append(
                    HardConstraint(
                        type=ConstraintType.WITHIN,
                        actions=[action_id],
                        deadline=dl,
                        severity=dc.severity,
                        provenance=dc.provenance,
                    )
                )

    # Additional deadlines not covered by DerivedConstraintSet.within
    if deadlines:
        covered = {aid for c in constraints if c.type == ConstraintType.WITHIN for aid in c.actions}
        for action_id, dl in deadlines.items():
            if action_id not in covered:
                constraints.append(
                    HardConstraint(
                        type=ConstraintType.WITHIN,
                        actions=[action_id],
                        deadline=dl,
                        severity="CRITICAL" if dl <= 60 else "HIGH",
                        provenance=f"deadline:{action_id}@{dl}min",
                    )
                )

    return constraints


# ============================================================
# Internal Helpers
# ============================================================


def _find_provenance(constraints: list[HardConstraint], action_id: str) -> str:
    """Find provenance string for a constraint matching action_id."""
    for c in constraints:
        if action_id in c.actions:
            return c.provenance
    return ""


def _find_provenance_pair(
    constraints: list[HardConstraint],
    a_id: str,
    b_id: str,
) -> str:
    """Find provenance for a BEFORE constraint pair."""
    for c in constraints:
        if len(c.actions) >= 2 and c.actions[0] == a_id and c.actions[1] == b_id:
            return c.provenance
    return ""


def _find_action(trace: list[Action], action_id: str) -> Action | None:
    """Find first action with given ID in trace."""
    for a in trace:
        if a.action_id == action_id:
            return a
    return None


def _get_insertion_time(
    action_id: str,
    within_cs: list[HardConstraint],
    original_trace: list[Action],
) -> float:
    """Determine insertion timestamp for a missing required action.

    Uses WITHIN deadline if available, otherwise episode midpoint.
    """
    for c in within_cs:
        if action_id in c.actions and c.deadline is not None:
            return c.deadline * 0.5  # Insert at half the deadline
    # Fallback: use midpoint of original trace
    if original_trace:
        times = [a.timestamp_minutes for a in original_trace]
        return (min(times) + max(times)) / 2
    return 0.0


def _count_inversions(
    trace: list[Action],
    before_pairs: list[tuple[str, str]],
) -> tuple[int, list[tuple[str, str]]]:
    """Count BEFORE constraint inversions in the trace.

    Returns (count, list of inverted pairs).
    """
    # Map action_id → first position in trace
    pos: dict[str, int] = {}
    for i, action in enumerate(trace):
        if action.action_id not in pos:
            pos[action.action_id] = i

    inversions = 0
    details: list[tuple[str, str]] = []

    for a_before, b_after in before_pairs:
        if a_before in pos and b_after in pos:
            if pos[a_before] >= pos[b_after]:
                inversions += 1
                details.append((a_before, b_after))

    return inversions, details


def _topological_reorder(
    trace: list[Action],
    before_pairs: list[tuple[str, str]],
) -> list[Action]:
    """Reorder trace to satisfy BEFORE constraints using topological sort.

    Preserves original order for unconstrained actions.
    """
    action_ids = [a.action_id for a in trace]
    id_to_action = {a.action_id: a for a in trace}

    # Build adjacency list for constrained actions
    constrained = set()
    graph: dict[str, list[str]] = defaultdict(list)
    in_degree: dict[str, int] = defaultdict(int)

    for a, b in before_pairs:
        if a in id_to_action and b in id_to_action:
            graph[a].append(b)
            in_degree[b] += 1
            constrained.add(a)
            constrained.add(b)
            if a not in in_degree:
                in_degree[a] = in_degree.get(a, 0)

    if not constrained:
        return trace

    # Kahn's algorithm for topological sort
    queue: deque[str] = deque()
    for node in constrained:
        if in_degree.get(node, 0) == 0:
            queue.append(node)

    topo_order: list[str] = []
    while queue:
        node = queue.popleft()
        topo_order.append(node)
        for neighbor in graph.get(node, []):
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Cycle detection
    if len(topo_order) < len(constrained):
        logger.warning("Cycle detected in BEFORE constraints; returning original order for constrained actions")
        return trace

    # Build reordered trace: slot constrained actions in topo order,
    # keep unconstrained actions in their original positions
    result: list[Action] = []
    topo_iter = iter(topo_order)
    constrained_positions = [i for i, a in enumerate(trace) if a.action_id in constrained]
    topo_list = list(topo_order)

    # Place constrained actions at their original positions in topo order
    topo_idx = 0
    for i, action in enumerate(trace):
        if action.action_id in constrained:
            if topo_idx < len(topo_list):
                reordered_action = id_to_action[topo_list[topo_idx]]
                # Preserve original timestamp for the slot
                result.append(
                    Action(
                        type=reordered_action.type,
                        action_id=reordered_action.action_id,
                        args=reordered_action.args,
                        timestamp_minutes=action.timestamp_minutes,
                        justification=reordered_action.justification,
                    )
                )
                topo_idx += 1
            else:
                result.append(action)
        else:
            result.append(action)

    return result
