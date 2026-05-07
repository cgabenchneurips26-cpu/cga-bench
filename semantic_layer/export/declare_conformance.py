"""
Alignment-based Declare conformance checking with LTL generation.

Provides:
- Constraint-driven trace alignment (no PM4Py dependency)
- LTL formula generation from Declare constraints
- Fitness/Precision/Generalization metrics

All features are opt-in via AlignmentConfig.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from ..conformance.activity import ActivityEvent
from .declare_bridge import DeclareConstraint, DeclareModel


@dataclass
class AlignmentConfig:
    """Configuration for alignment-based conformance checking.

    Attributes:
        enable_alignment: Enable trace alignment computation
        cost_model: "standard" (uniform cost=1) or "weighted" (uses constraint weight)
        max_alignment_steps: Bound for pathological traces
        enable_ltl_generation: Generate LTL formulas from constraints
        enable_fitness_precision: Compute fitness/precision metrics
    """
    enable_alignment: bool = True
    cost_model: str = "standard"
    max_alignment_steps: int = 1000
    enable_ltl_generation: bool = False
    enable_fitness_precision: bool = True


@dataclass
class AlignmentStep:
    """A single step in a trace-model alignment."""
    trace_event: Optional[str] = None
    model_event: Optional[str] = None
    move_type: str = "sync"  # "sync" | "log_move" | "model_move"
    cost: float = 0.0
    constraint_id: Optional[str] = None


@dataclass
class AlignmentResult:
    """Result of aligning a trace against a Declare model."""
    alignment: List[AlignmentStep]
    total_cost: float
    fitness: float
    synchronous_moves: int
    log_moves: int
    model_moves: int
    violated_constraints: List[str]
    diagnostic_info: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FitnessPrecisionMetrics:
    """Process mining fitness/precision/generalization metrics."""
    fitness: float
    precision: float
    generalization: float
    f_measure: float


@dataclass
class LTLFormula:
    """An LTL formula derived from a Declare constraint."""
    formula: str
    source_constraint_id: str
    template: str
    activities: List[str]


# LTL template patterns
_LTL_TEMPLATES: Dict[str, str] = {
    "Existence": "F({A})",
    "Response": "G({A} -> F({B}))",
    "Precedence": "(!{B} W {A})",
    "Not Succession": "G({A} -> !F({B}))",
    "Not Co-Existence": "!(F({A}) & F({B}))",
}


class DeclareConformanceChecker:
    """Alignment-based Declare conformance checking.

    Implements constraint-driven trace alignment without requiring PM4Py.
    Each constraint is independently checked against the trace,
    and violations are aggregated into an alignment result with
    fitness metrics.
    """

    def __init__(self, config: Optional[AlignmentConfig] = None):
        self._config = config or AlignmentConfig()

    def check_conformance(
        self,
        trace: List[ActivityEvent],
        declare_model: DeclareModel,
    ) -> AlignmentResult:
        """Check a single trace against a Declare model.

        Evaluates each constraint independently and builds
        a combined alignment with per-constraint diagnostics.

        Args:
            trace: Ordered list of ActivityEvent objects
            declare_model: DeclareModel with constraints

        Returns:
            AlignmentResult with alignment steps and fitness
        """
        trace_names = [e.name for e in trace]
        alignment_steps: List[AlignmentStep] = []
        violated: List[str] = []
        total_cost = 0.0
        diagnostics: Dict[str, Dict[str, Any]] = {}

        # Synchronous moves: each trace event maps to a sync move
        for name in trace_names:
            alignment_steps.append(AlignmentStep(
                trace_event=name, model_event=name, move_type="sync"
            ))

        max_cost = 0.0
        model_moves = 0

        for constraint in declare_model.constraints:
            cost_unit = (
                constraint.weight if self._config.cost_model == "weighted" else 1.0
            )
            max_cost += cost_unit

            violation = self._check_constraint(trace_names, constraint)
            if violation:
                violated.append(constraint.source_id or constraint.template)
                total_cost += cost_unit
                model_moves += 1
                alignment_steps.append(AlignmentStep(
                    trace_event=None,
                    model_event=violation["expected"],
                    move_type="model_move",
                    cost=cost_unit,
                    constraint_id=constraint.source_id,
                ))
                diagnostics[constraint.source_id or constraint.template] = violation

        fitness = 1.0 - (total_cost / max_cost) if max_cost > 0 else 1.0
        fitness = max(fitness, 0.0)

        return AlignmentResult(
            alignment=alignment_steps,
            total_cost=total_cost,
            fitness=fitness,
            synchronous_moves=len(trace_names),
            log_moves=0,
            model_moves=model_moves,
            violated_constraints=violated,
            diagnostic_info=diagnostics,
        )

    def compute_fitness_precision(
        self,
        traces: List[List[ActivityEvent]],
        declare_model: DeclareModel,
    ) -> FitnessPrecisionMetrics:
        """Compute fitness/precision/generalization over multiple traces.

        Args:
            traces: List of traces (each is a list of ActivityEvent)
            declare_model: DeclareModel to check against

        Returns:
            FitnessPrecisionMetrics with aggregated metrics
        """
        if not traces:
            return FitnessPrecisionMetrics(
                fitness=1.0, precision=1.0, generalization=1.0, f_measure=1.0
            )

        # Fitness: average per-trace fitness
        fitness_values: List[float] = []
        observed_patterns: Set[tuple] = set()

        for trace in traces:
            result = self.check_conformance(trace, declare_model)
            fitness_values.append(result.fitness)
            # Record observed activity pattern
            pattern = tuple(e.name for e in trace)
            observed_patterns.add(pattern)

        avg_fitness = sum(fitness_values) / len(fitness_values)

        # Precision: ratio of model-allowed behaviors actually observed
        # Approximated by: distinct patterns / model activities count
        model_activities = set(declare_model.activities)
        observed_activities = set()
        for trace in traces:
            for e in trace:
                observed_activities.add(e.name)
        # Precision = observed / allowed (capped at 1.0)
        precision = (
            len(observed_activities & model_activities) / max(len(model_activities), 1)
            if model_activities else 1.0
        )
        precision = min(precision, 1.0)

        # Generalization: 1 - variance of per-trace fitness
        if len(fitness_values) > 1:
            mean_f = avg_fitness
            variance = sum((f - mean_f) ** 2 for f in fitness_values) / len(fitness_values)
            generalization = max(1.0 - variance, 0.0)
        else:
            generalization = 1.0

        # F-measure: harmonic mean of fitness and precision
        if avg_fitness + precision > 0:
            f_measure = 2.0 * avg_fitness * precision / (avg_fitness + precision)
        else:
            f_measure = 0.0

        return FitnessPrecisionMetrics(
            fitness=avg_fitness,
            precision=precision,
            generalization=generalization,
            f_measure=f_measure,
        )

    def generate_ltl_formulas(
        self,
        declare_model: DeclareModel,
    ) -> List[LTLFormula]:
        """Convert Declare constraints to LTL formulas.

        Args:
            declare_model: DeclareModel with constraints

        Returns:
            List of LTLFormula objects
        """
        formulas: List[LTLFormula] = []

        for constraint in declare_model.constraints:
            formula = self._constraint_to_ltl(constraint)
            if formula:
                formulas.append(formula)

        return formulas

    def _check_constraint(
        self,
        trace_names: List[str],
        constraint: DeclareConstraint,
    ) -> Optional[Dict[str, Any]]:
        """Check if a single constraint is violated by the trace.

        Returns violation info dict if violated, None if satisfied.
        """
        template = constraint.template
        activities = constraint.activities
        trace_set = set(trace_names)

        if template == "Existence":
            a = activities[0] if activities else None
            if a and a not in trace_set:
                return {"type": "missing_activity", "expected": a, "template": template}

        elif template == "Response":
            if len(activities) < 2:
                return None
            a, b = activities[0], activities[1]
            if a in trace_set:
                # Find last occurrence of A, check if B appears after it
                last_a_idx = None
                for i, name in enumerate(trace_names):
                    if name == a:
                        last_a_idx = i
                if last_a_idx is not None:
                    b_after_a = any(
                        trace_names[j] == b
                        for j in range(last_a_idx + 1, len(trace_names))
                    )
                    if not b_after_a:
                        return {
                            "type": "missing_response",
                            "expected": b,
                            "after": a,
                            "template": template,
                            "last_a_position": last_a_idx,
                        }
                    # Also check if window constraint exists
                    if constraint.time_window is not None:
                        # For response_within, just note the window
                        pass  # Window checked by scorer, not alignment

        elif template == "Precedence":
            if len(activities) < 2:
                return None
            a, b = activities[0], activities[1]
            if b in trace_set:
                first_b_idx = next(
                    (i for i, name in enumerate(trace_names) if name == b), None
                )
                if first_b_idx is not None:
                    a_before_b = any(
                        trace_names[j] == a
                        for j in range(first_b_idx)
                    )
                    if not a_before_b:
                        return {
                            "type": "missing_precedence",
                            "expected": a,
                            "before": b,
                            "template": template,
                            "first_b_position": first_b_idx,
                        }

        elif template == "Not Succession":
            if len(activities) < 2:
                return None
            a, b = activities[0], activities[1]
            # Check if B occurs after any A
            found_a = False
            for name in trace_names:
                if name == a:
                    found_a = True
                elif name == b and found_a:
                    return {
                        "type": "forbidden_succession",
                        "expected": f"no {b} after {a}",
                        "template": template,
                    }

        elif template == "Not Co-Existence":
            if len(activities) < 2:
                return None
            a, b = activities[0], activities[1]
            if a in trace_set and b in trace_set:
                return {
                    "type": "forbidden_coexistence",
                    "expected": f"not both {a} and {b}",
                    "template": template,
                }

        return None

    def _constraint_to_ltl(self, constraint: DeclareConstraint) -> Optional[LTLFormula]:
        """Convert a single Declare constraint to LTL formula."""
        template = constraint.template
        activities = constraint.activities

        if not activities:
            return None

        a = activities[0]
        b = activities[1] if len(activities) > 1 else None

        # Handle response_within with window annotation
        if template == "Response" and constraint.time_window is not None:
            formula = f"G({a} -> F_<={constraint.time_window}({b}))"
            return LTLFormula(
                formula=formula,
                source_constraint_id=constraint.source_id or "",
                template=template,
                activities=list(activities),
            )

        pattern = _LTL_TEMPLATES.get(template)
        if not pattern:
            return None

        formula = pattern.replace("{A}", a)
        if b:
            formula = formula.replace("{B}", b)

        return LTLFormula(
            formula=formula,
            source_constraint_id=constraint.source_id or "",
            template=template,
            activities=list(activities),
        )
