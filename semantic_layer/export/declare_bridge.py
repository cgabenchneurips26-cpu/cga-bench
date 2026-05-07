"""
Declare Bridge - converts SoftConstraints to Declare constraint templates
and provides cross-verification with Declare4Py or similar tools.

Declare is a constraint-based process modeling language that maps naturally
to the SoftConstraint templates used in CGA-Bench conformance checking.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from cga_bench.cpg_model.schemas.conformance import SoftConstraint, SoftConstraints
from ..conformance.activity import ActivityEvent


# Mapping from CGA-Bench constraint templates to Declare template names
_CGA_TO_DECLARE: Dict[str, str] = {
    "existence": "Existence",
    "response": "Response",
    "response_within": "Response",  # Declare doesn't natively support windows; use attribute
    "precedence": "Precedence",
    "not_succession": "Not Succession",
    "not_coexistence": "Not Co-Existence",
}


@dataclass
class DeclareConstraint:
    """A Declare constraint template instance."""
    template: str                   # Declare template name
    activities: List[str]           # [A] or [A, B]
    condition: Optional[str] = None  # Guard condition string
    time_window: Optional[float] = None  # Window in minutes (extension)
    weight: float = 1.0
    source_id: Optional[str] = None  # CGA-Bench constraint_id


@dataclass
class DeclareModel:
    """A complete Declare model with activities and constraints."""
    activities: List[str]
    constraints: List[DeclareConstraint]
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class CrossVerificationResult:
    """Result of cross-verification between CGA-Bench and Declare."""
    total_constraints: int
    matched: int
    mismatched: int
    cga_only_violations: List[str] = field(default_factory=list)
    declare_only_violations: List[str] = field(default_factory=list)
    agreement_rate: float = 0.0


class DeclareBridge:
    """Converts SoftConstraints to Declare model and performs cross-verification.

    Enhanced with optional alignment-based conformance checking,
    LTL formula generation, and fitness/precision metrics.
    """

    def __init__(self, alignment_config=None):
        """Initialize DeclareBridge with optional alignment configuration.

        Args:
            alignment_config: Optional AlignmentConfig for enhanced features.
                If None, only basic conversion and cross-verify are available.
        """
        self._alignment_config = alignment_config
        self._checker = None

    def _get_checker(self):
        """Lazy-init conformance checker."""
        if self._checker is None and self._alignment_config is not None:
            from .declare_conformance import (
                AlignmentConfig,
                DeclareConformanceChecker,
            )
            self._checker = DeclareConformanceChecker(self._alignment_config)
        return self._checker

    def align_trace(
        self,
        trace: List[ActivityEvent],
        soft_constraints: SoftConstraints,
    ):
        """Align a trace against the Declare model derived from constraints.

        Requires alignment_config to be set at initialization.

        Args:
            trace: List of ActivityEvent objects
            soft_constraints: CGA-Bench SoftConstraints

        Returns:
            AlignmentResult with fitness and diagnostics
        """
        checker = self._get_checker()
        if checker is None:
            from .declare_conformance import (
                AlignmentConfig,
                AlignmentResult,
                DeclareConformanceChecker,
            )
            checker = DeclareConformanceChecker(AlignmentConfig())
        model = self.to_declare_model(soft_constraints)
        return checker.check_conformance(trace, model)

    def compute_metrics(
        self,
        traces: List[List[ActivityEvent]],
        soft_constraints: SoftConstraints,
    ):
        """Compute fitness/precision/generalization over multiple traces.

        Args:
            traces: List of traces
            soft_constraints: CGA-Bench SoftConstraints

        Returns:
            FitnessPrecisionMetrics
        """
        checker = self._get_checker()
        if checker is None:
            from .declare_conformance import (
                AlignmentConfig,
                DeclareConformanceChecker,
            )
            checker = DeclareConformanceChecker(AlignmentConfig())
        model = self.to_declare_model(soft_constraints)
        return checker.compute_fitness_precision(traces, model)

    def to_ltl(self, soft_constraints: SoftConstraints) -> List:
        """Generate LTL formulas from SoftConstraints.

        Args:
            soft_constraints: CGA-Bench SoftConstraints

        Returns:
            List of LTLFormula objects
        """
        from .declare_conformance import (
            AlignmentConfig,
            DeclareConformanceChecker,
        )
        checker = self._get_checker()
        if checker is None:
            checker = DeclareConformanceChecker(AlignmentConfig())
        model = self.to_declare_model(soft_constraints)
        return checker.generate_ltl_formulas(model)

    def to_declare_model(self, soft_constraints: SoftConstraints) -> DeclareModel:
        """Convert CGA-Bench SoftConstraints to a Declare model.

        Args:
            soft_constraints: CGA-Bench SoftConstraints object

        Returns:
            DeclareModel with equivalent constraints
        """
        activities: set = set()
        declare_constraints: List[DeclareConstraint] = []

        for constraint in soft_constraints.constraints:
            dc = self._convert_constraint(constraint)
            if dc:
                declare_constraints.append(dc)
                activities.update(dc.activities)

        return DeclareModel(
            activities=sorted(activities),
            constraints=declare_constraints,
            metadata={
                "cpg_id": soft_constraints.cpg_id,
                "source": "cga_bench",
            },
        )

    def to_declare_text(self, soft_constraints: SoftConstraints) -> str:
        """Export SoftConstraints as Declare text format.

        Produces a human-readable Declare model specification
        compatible with Declare4Py and similar tools.

        Args:
            soft_constraints: CGA-Bench SoftConstraints object

        Returns:
            Declare model as text string
        """
        model = self.to_declare_model(soft_constraints)
        lines: List[str] = []

        # Header
        lines.append(f"# Declare Model: {soft_constraints.cpg_id}")
        lines.append("")

        # Activities
        lines.append("# Activities")
        for activity in model.activities:
            lines.append(f"activity {activity}")
        lines.append("")

        # Constraints
        lines.append("# Constraints")
        for dc in model.constraints:
            line = self._format_declare_constraint(dc)
            lines.append(line)

        return "\n".join(lines)

    def cross_verify(
        self,
        cga_violations: List[str],
        declare_violations: List[str],
        constraint_ids: Optional[List[str]] = None,
    ) -> CrossVerificationResult:
        """Cross-verify CGA-Bench violations against Declare checker results.

        Compares violation sets from both systems to identify
        agreements and discrepancies.

        Args:
            cga_violations: Constraint IDs violated per CGA-Bench
            declare_violations: Constraint IDs violated per Declare checker
            constraint_ids: All constraint IDs to consider

        Returns:
            CrossVerificationResult with agreement metrics
        """
        cga_set = set(cga_violations)
        declare_set = set(declare_violations)

        all_ids = set(constraint_ids) if constraint_ids else cga_set | declare_set
        total = len(all_ids)

        if total == 0:
            return CrossVerificationResult(
                total_constraints=0,
                matched=0,
                mismatched=0,
                agreement_rate=1.0,
            )

        matched = 0
        mismatched = 0
        cga_only: List[str] = []
        declare_only: List[str] = []

        for cid in all_ids:
            in_cga = cid in cga_set
            in_declare = cid in declare_set
            if in_cga == in_declare:
                matched += 1
            else:
                mismatched += 1
                if in_cga and not in_declare:
                    cga_only.append(cid)
                elif in_declare and not in_cga:
                    declare_only.append(cid)

        return CrossVerificationResult(
            total_constraints=total,
            matched=matched,
            mismatched=mismatched,
            cga_only_violations=sorted(cga_only),
            declare_only_violations=sorted(declare_only),
            agreement_rate=matched / total if total > 0 else 1.0,
        )

    def _convert_constraint(self, constraint: SoftConstraint) -> Optional[DeclareConstraint]:
        """Convert a single SoftConstraint to DeclareConstraint."""
        template_name = _CGA_TO_DECLARE.get(constraint.template.value)
        if not template_name:
            return None

        activities: List[str] = []
        if constraint.A:
            activities.append(constraint.A)
        if constraint.B:
            activities.append(constraint.B)

        if not activities:
            return None

        return DeclareConstraint(
            template=template_name,
            activities=activities,
            condition=constraint.guard,
            time_window=constraint.window_minutes,
            weight=constraint.weight,
            source_id=constraint.constraint_id,
        )

    def _format_declare_constraint(self, dc: DeclareConstraint) -> str:
        """Format a DeclareConstraint as text."""
        if len(dc.activities) == 1:
            line = f"{dc.template}[{dc.activities[0]}]"
        else:
            line = f"{dc.template}[{dc.activities[0]}, {dc.activities[1]}]"

        parts = [line]
        if dc.time_window is not None:
            parts.append(f"|window={dc.time_window}min")
        if dc.condition:
            parts.append(f"|guard={dc.condition}")
        if dc.source_id:
            parts.append(f"  # {dc.source_id}")

        return " ".join(parts)
