"""
Conformance evaluation for Hard Graph + Soft Constraints.

Enhanced with:
- Multi-dimensional sub-scores (completeness, ordering, timeliness, safety)
- Graduated timing violations (linear/logarithmic penalty scaling)
- Evidence-weighted constraint penalties
- Synergistic harm detection for compound violations
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cga_bench.cpg_model.schemas.conformance import (
    ConstraintTemplate,
    HardGraph,
    SoftConstraint,
    SoftConstraints,
)
from .activity import ActivityEvent


# --- Enhanced Scoring Configuration ---

@dataclass
class TimingPenaltyConfig:
    """Configuration for graduated timing penalties.

    Modes:
    - binary: Original behavior (full penalty or none)
    - linear: Penalty scales linearly with delay overshoot
    - logarithmic: Penalty scales with diminishing returns
    """
    mode: str = "binary"
    grace_period_minutes: float = 0.0
    max_penalty_multiplier: float = 2.0
    half_life_minutes: float = 30.0


@dataclass
class SynergisticRule:
    """Defines compounding harm when multiple violations co-occur."""
    rule_id: str
    required_violations: List[str]
    multiplier: float = 1.5
    rationale: str = ""


@dataclass
class ScoringConfig:
    """Enhanced scoring configuration. All defaults preserve original behavior."""
    cost_scale: float = 10.0
    timing_penalty: TimingPenaltyConfig = field(default_factory=TimingPenaltyConfig)
    enable_evidence_weighting: bool = False
    synergistic_rules: List[SynergisticRule] = field(default_factory=list)
    enable_sub_scores: bool = True


@dataclass
class SubScores:
    """Multi-dimensional conformance sub-scores. All in [0.0, 1.0]."""
    completeness: float
    ordering: float
    timeliness: float
    safety: float


# Evidence level multipliers (stronger evidence = higher penalty)
_EVIDENCE_MULTIPLIERS = {
    "1A": 1.0, "1a": 1.0,
    "1B": 0.95, "1b": 0.95,
    "2A": 0.85, "2a": 0.85,
    "2B": 0.75, "2b": 0.75,
    "2C": 0.65, "2c": 0.65,
    "3": 0.5,
}


# --- Core Data Structures ---

@dataclass
class ConstraintViolation:
    constraint_id: str
    template: str
    channel: str
    detail: str
    weight: float
    timestamp_min: Optional[float] = None
    actual_delay_minutes: Optional[float] = None
    window_minutes: Optional[float] = None


@dataclass
class ConformanceReport:
    cpg_id: str
    activity_count: int
    phases_present: List[str]
    missing_phases: List[str]
    phase_order_violations: List[str]
    constraint_violations: List[ConstraintViolation]
    compliance_cost: float
    compliance_score: float
    compliance_cost_breakdown: Dict[str, float]
    compliance_score_breakdown: Dict[str, float]
    derived_flags: Dict[str, bool] = field(default_factory=dict)
    sub_scores: Optional[SubScores] = None


def evaluate_conformance(
    activity_events: List[ActivityEvent],
    hard_graph: HardGraph,
    soft_constraints: SoftConstraints,
    derived_flags: Dict[str, bool],
    cost_scale: float = 10.0,
    classified_errors: Optional[List] = None,
    scoring_config: Optional[ScoringConfig] = None,
) -> ConformanceReport:
    cfg = scoring_config
    effective_cost_scale = cfg.cost_scale if cfg else cost_scale

    phase_result = _evaluate_hard_graph(activity_events, hard_graph)
    constraint_result = _evaluate_constraints(
        activity_events, soft_constraints, derived_flags, scoring_config=cfg
    )
    error_penalty = _error_penalty(
        derived_flags,
        soft_constraints.error_weight,
        error_penalty_config=soft_constraints.error_penalty_config,
        classified_errors=classified_errors,
    )

    # Base cost
    compliance_cost = sum(v.weight for v in constraint_result) + error_penalty

    # Synergistic harm (additional penalty for compound violations)
    if cfg and cfg.synergistic_rules:
        synergy_extra = _apply_synergistic_harm(constraint_result, cfg.synergistic_rules)
        compliance_cost += synergy_extra

    compliance_score = math.exp(-compliance_cost / effective_cost_scale) if effective_cost_scale > 0 else 0.0
    breakdown_cost = _compliance_cost_breakdown(constraint_result, error_penalty)
    breakdown_score = {
        channel: math.exp(-cost / effective_cost_scale) if effective_cost_scale > 0 else 0.0
        for channel, cost in breakdown_cost.items()
    }

    # Sub-scores (opt-in via scoring_config)
    sub_scores = None
    if cfg and cfg.enable_sub_scores:
        sub_scores = _compute_sub_scores(
            phase_result, hard_graph, constraint_result, soft_constraints
        )

    return ConformanceReport(
        cpg_id=hard_graph.cpg_id,
        activity_count=len(activity_events),
        phases_present=phase_result["phases_present"],
        missing_phases=phase_result["missing_phases"],
        phase_order_violations=phase_result["phase_order_violations"],
        constraint_violations=constraint_result,
        compliance_cost=compliance_cost,
        compliance_score=compliance_score,
        compliance_cost_breakdown=breakdown_cost,
        compliance_score_breakdown=breakdown_score,
        derived_flags=derived_flags,
        sub_scores=sub_scores,
    )


def _evaluate_hard_graph(
    activity_events: List[ActivityEvent],
    hard_graph: HardGraph,
) -> Dict[str, Any]:
    phase_first_seen: Dict[str, float] = {}
    phases_present = set()

    for event in activity_events:
        phase = hard_graph.phase_map.get(event.name)
        if not phase:
            continue
        phases_present.add(phase)
        if phase not in phase_first_seen:
            phase_first_seen[phase] = event.timestamp_min

    missing = [phase for phase in hard_graph.required_phases if phase not in phases_present]

    order_violations = []
    for edge in hard_graph.edges:
        if len(edge) != 2:
            continue
        src, dst = edge
        if src in phase_first_seen and dst in phase_first_seen:
            if phase_first_seen[dst] < phase_first_seen[src]:
                order_violations.append(f"{dst} before {src}")

    return {
        "phases_present": sorted(phases_present),
        "missing_phases": missing,
        "phase_order_violations": order_violations,
    }


def _evaluate_constraints(
    activity_events: List[ActivityEvent],
    soft_constraints: SoftConstraints,
    derived_flags: Dict[str, bool],
    scoring_config: Optional[ScoringConfig] = None,
) -> List[ConstraintViolation]:
    violations: List[ConstraintViolation] = []
    index = _build_activity_index(activity_events)

    for constraint in soft_constraints.constraints:
        if constraint.guard and not derived_flags.get(constraint.guard, False):
            continue

        # Apply evidence weighting if enabled
        effective_weight = constraint.weight
        if scoring_config and scoring_config.enable_evidence_weighting:
            effective_weight = _apply_evidence_weight(
                constraint.weight, constraint.evidence_level
            )

        if constraint.template == "existence":
            violations.extend(_check_existence(constraint, index, effective_weight))
        elif constraint.template == "response":
            violations.extend(_check_response(constraint, index, effective_weight))
        elif constraint.template == "response_within":
            violations.extend(_check_response_within(
                constraint, index, effective_weight, scoring_config
            ))
        elif constraint.template == "precedence":
            violations.extend(_check_precedence(constraint, index, effective_weight))
        elif constraint.template == "not_succession":
            violations.extend(_check_not_succession(constraint, index, effective_weight))
        elif constraint.template == "not_coexistence":
            violations.extend(_check_not_coexistence(constraint, index, effective_weight))

    return violations


def _build_activity_index(activity_events: List[ActivityEvent]) -> Dict[str, List[ActivityEvent]]:
    index: Dict[str, List[ActivityEvent]] = {}
    for event in activity_events:
        index.setdefault(event.name, []).append(event)
    return index


def _check_existence(
    constraint: SoftConstraint, index: Dict[str, List[ActivityEvent]],
    effective_weight: Optional[float] = None,
):
    weight = effective_weight if effective_weight is not None else constraint.weight
    if not constraint.A:
        return []
    if constraint.A not in index:
        return [
            ConstraintViolation(
                constraint_id=constraint.constraint_id,
                template=constraint.template.value,
                channel=constraint.channel,
                detail=f"Missing required activity {constraint.A}",
                weight=weight,
            )
        ]
    return []


def _check_response(
    constraint: SoftConstraint, index: Dict[str, List[ActivityEvent]],
    effective_weight: Optional[float] = None,
):
    weight = effective_weight if effective_weight is not None else constraint.weight
    if not constraint.A or not constraint.B:
        return []
    violations = []
    events_a = index.get(constraint.A, [])
    events_b = index.get(constraint.B, [])
    for event_a in events_a:
        if not any(event_b.timestamp_min > event_a.timestamp_min for event_b in events_b):
            violations.append(
                ConstraintViolation(
                    constraint_id=constraint.constraint_id,
                    template=constraint.template.value,
                    channel=constraint.channel,
                    detail=f"{constraint.B} missing after {constraint.A}",
                    weight=weight,
                    timestamp_min=event_a.timestamp_min,
                )
            )
    return violations


def _check_response_within(
    constraint: SoftConstraint, index: Dict[str, List[ActivityEvent]],
    effective_weight: Optional[float] = None,
    scoring_config: Optional[ScoringConfig] = None,
):
    weight = effective_weight if effective_weight is not None else constraint.weight
    if not constraint.A or not constraint.B or constraint.window_minutes is None:
        return []
    violations = []
    events_a = index.get(constraint.A, [])
    events_b = index.get(constraint.B, [])
    for event_a in events_a:
        matched = False
        best_delay: Optional[float] = None
        for event_b in events_b:
            if event_b.timestamp_min > event_a.timestamp_min:
                delay = event_b.timestamp_min - event_a.timestamp_min
                if delay <= constraint.window_minutes:
                    matched = True
                    break
                if best_delay is None or delay < best_delay:
                    best_delay = delay
        if not matched:
            # Compute graduated weight if config provided
            violation_weight = weight
            if scoring_config and best_delay is not None:
                violation_weight = _graduated_timing_weight(
                    weight, best_delay, constraint.window_minutes,
                    scoring_config.timing_penalty,
                )
            violations.append(
                ConstraintViolation(
                    constraint_id=constraint.constraint_id,
                    template=constraint.template.value,
                    channel=constraint.channel,
                    detail=f"{constraint.B} not within {constraint.window_minutes} min of {constraint.A}",
                    weight=violation_weight,
                    timestamp_min=event_a.timestamp_min,
                    actual_delay_minutes=best_delay,
                    window_minutes=constraint.window_minutes,
                )
            )
    return violations


def _check_precedence(
    constraint: SoftConstraint, index: Dict[str, List[ActivityEvent]],
    effective_weight: Optional[float] = None,
):
    weight = effective_weight if effective_weight is not None else constraint.weight
    if not constraint.A or not constraint.B:
        return []
    violations = []
    events_a = index.get(constraint.A, [])
    events_b = index.get(constraint.B, [])
    for event_b in events_b:
        if not any(event_a.timestamp_min < event_b.timestamp_min for event_a in events_a):
            violations.append(
                ConstraintViolation(
                    constraint_id=constraint.constraint_id,
                    template=constraint.template.value,
                    channel=constraint.channel,
                    detail=f"{constraint.A} missing before {constraint.B}",
                    weight=weight,
                    timestamp_min=event_b.timestamp_min,
                )
            )
    return violations


def _check_not_succession(
    constraint: SoftConstraint, index: Dict[str, List[ActivityEvent]],
    effective_weight: Optional[float] = None,
):
    weight = effective_weight if effective_weight is not None else constraint.weight
    if not constraint.A or not constraint.B:
        return []
    violations = []
    events_a = index.get(constraint.A, [])
    events_b = index.get(constraint.B, [])
    for event_b in events_b:
        if any(event_a.timestamp_min < event_b.timestamp_min for event_a in events_a):
            violations.append(
                ConstraintViolation(
                    constraint_id=constraint.constraint_id,
                    template=constraint.template.value,
                    channel=constraint.channel,
                    detail=f"{constraint.B} occurred after {constraint.A}",
                    weight=weight,
                    timestamp_min=event_b.timestamp_min,
                )
            )
    return violations


def _check_not_coexistence(
    constraint: SoftConstraint, index: Dict[str, List[ActivityEvent]],
    effective_weight: Optional[float] = None,
):
    weight = effective_weight if effective_weight is not None else constraint.weight
    if not constraint.A or not constraint.B:
        return []
    if constraint.A in index and constraint.B in index:
        return [
            ConstraintViolation(
                constraint_id=constraint.constraint_id,
                template=constraint.template.value,
                channel=constraint.channel,
                detail=f"{constraint.A} and {constraint.B} both present",
                weight=weight,
            )
        ]
    return []


def _error_penalty(
    derived_flags: Dict[str, bool],
    weight: float,
    error_penalty_config=None,
    classified_errors: Optional[List] = None,
) -> float:
    if weight <= 0:
        return 0.0

    # If classified_errors provided with error_penalty_config, use fine-grained exemption
    if classified_errors and error_penalty_config:
        penalized_categories = set(error_penalty_config.penalized_categories)
        penalized_count = sum(
            1 for err in classified_errors
            if err.error_category.value in penalized_categories
        )
        return penalized_count * weight

    # Fallback: original behavior (count all error flags)
    error_count = sum(1 for key, hit in derived_flags.items() if hit and key.startswith("res.error_"))
    return error_count * weight


def _compliance_cost_breakdown(
    violations: List[ConstraintViolation],
    error_penalty: float,
) -> Dict[str, float]:
    costs = {"req": 0.0, "res": 0.0, "err": error_penalty}
    for violation in violations:
        channel = violation.channel if violation.channel in costs else "req"
        costs[channel] += violation.weight
    return costs


# --- Enhanced Scoring Helpers ---

def _graduated_timing_weight(
    base_weight: float,
    actual_delay: float,
    window_minutes: float,
    config: TimingPenaltyConfig,
) -> float:
    """Compute graduated timing violation weight based on overshoot.

    Args:
        base_weight: Base constraint weight
        actual_delay: Actual delay in minutes (may be > window)
        window_minutes: Required window in minutes
        config: Timing penalty configuration

    Returns:
        Adjusted weight (may be 0 if within grace, or > base_weight if severe)
    """
    if config.mode == "binary":
        return base_weight

    overshoot = actual_delay - window_minutes - config.grace_period_minutes
    if overshoot <= 0:
        return 0.0  # Within grace period

    if config.mode == "linear":
        scale = min(overshoot / max(window_minutes, 1.0), config.max_penalty_multiplier)
        return base_weight * max(scale, 0.1)  # Minimum 10% of base

    if config.mode == "logarithmic":
        half_life = max(config.half_life_minutes, 1.0)
        scale = min(
            math.log2(1.0 + overshoot / half_life),
            config.max_penalty_multiplier,
        )
        return base_weight * max(scale, 0.1)

    return base_weight


def _apply_evidence_weight(base_weight: float, evidence_level: Optional[str]) -> float:
    """Apply evidence level multiplier to constraint weight.

    Higher evidence levels (1A) retain full weight; lower levels (3) reduce penalty.
    """
    if not evidence_level:
        return base_weight
    multiplier = _EVIDENCE_MULTIPLIERS.get(evidence_level, 1.0)
    return base_weight * multiplier


def _apply_synergistic_harm(
    violations: List[ConstraintViolation],
    rules: List[SynergisticRule],
) -> float:
    """Compute additional penalty for compound violations.

    When all violations in a synergistic rule are present,
    applies a multiplier to their combined weight as extra cost.
    """
    extra_cost = 0.0
    violated_ids = {v.constraint_id for v in violations}

    for rule in rules:
        if all(rid in violated_ids for rid in rule.required_violations):
            combined_weight = sum(
                v.weight for v in violations
                if v.constraint_id in set(rule.required_violations)
            )
            extra_cost += combined_weight * (rule.multiplier - 1.0)

    return extra_cost


def _compute_sub_scores(
    phase_result: Dict[str, Any],
    hard_graph: HardGraph,
    violations: List[ConstraintViolation],
    soft_constraints: SoftConstraints,
) -> SubScores:
    """Compute multi-dimensional conformance sub-scores.

    Each dimension is in [0.0, 1.0] where 1.0 is perfect compliance.
    """
    # Completeness: fraction of required phases present
    required = hard_graph.required_phases
    present = set(phase_result["phases_present"])
    completeness = len(present & set(required)) / max(len(required), 1)

    # Ordering: fraction of edges not violated
    total_edges = len(hard_graph.edges)
    order_violations = len(phase_result["phase_order_violations"])
    ordering = 1.0 - (order_violations / max(total_edges, 1)) if total_edges > 0 else 1.0

    # Timeliness: fraction of response_within constraints satisfied
    timing_constraints = [
        c for c in soft_constraints.constraints
        if c.template == ConstraintTemplate.RESPONSE_WITHIN
    ]
    timing_violations = [
        v for v in violations if v.template == "response_within"
    ]
    timeliness = (
        1.0 - (len(timing_violations) / max(len(timing_constraints), 1))
        if timing_constraints else 1.0
    )

    # Safety: fraction of not_succession/not_coexistence constraints satisfied
    safety_templates = {ConstraintTemplate.NOT_SUCCESSION, ConstraintTemplate.NOT_COEXISTENCE}
    safety_constraints = [
        c for c in soft_constraints.constraints
        if c.template in safety_templates
    ]
    safety_violations = [
        v for v in violations
        if v.template in ("not_succession", "not_coexistence")
    ]
    safety = (
        1.0 - (len(safety_violations) / max(len(safety_constraints), 1))
        if safety_constraints else 1.0
    )

    return SubScores(
        completeness=completeness,
        ordering=ordering,
        timeliness=timeliness,
        safety=safety,
    )
