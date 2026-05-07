"""
Clinical Interaction Detector: Synergistic harm interaction detection.

Detects when multiple violations interact clinically to produce compound harm
exceeding the sum of individual harms. Supports temporal proximity, causal chains,
contraindication compounds, phase compounding, and severity escalation.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional, Set, Tuple

from cga_bench.cpg_model.schemas.base import (
    HarmSeverity, ViolationEvent, ViolationType,
)


class InteractionType(str, Enum):
    """Types of synergistic harm interactions"""
    TEMPORAL_PROXIMITY = "temporal_proximity"
    CAUSAL_CHAIN = "causal_chain"
    CONTRAINDICATION_COMPOUND = "contraindication_compound"
    PHASE_COMPOUNDING = "phase_compounding"
    SEVERITY_ESCALATION = "severity_escalation"


@dataclass
class InteractionPattern:
    """A single interaction rule pattern - injected via config"""
    pattern_id: str
    interaction_type: InteractionType

    # Violation matching criteria (None = any)
    violation_type_a: Optional[ViolationType] = None
    violation_type_b: Optional[ViolationType] = None
    action_pattern_a: Optional[str] = None  # regex for action_involved/expected_action
    action_pattern_b: Optional[str] = None

    # Temporal constraints
    temporal_window_minutes: Optional[float] = None
    require_same_phase: bool = False
    require_same_node: bool = False

    # Causal constraints
    causal_direction: Optional[str] = None  # "a_before_b" or "b_before_a"

    # Output
    multiplier: float = 1.5
    max_multiplier: float = 3.0
    escalated_severity: Optional[HarmSeverity] = None
    clinical_rationale: str = ""
    source_guideline: str = ""


@dataclass
class InteractionConfig:
    """Configuration for synergistic harm detection - all values externally injected"""

    interaction_patterns: List[InteractionPattern]

    # Global enable flags
    enable_temporal_proximity: bool = True
    enable_causal_chain: bool = True
    enable_contraindication_compound: bool = True
    enable_phase_compounding: bool = True
    enable_severity_escalation: bool = True

    # Triple jeopardy settings
    enable_triple_jeopardy: bool = True
    triple_jeopardy_multiplier: float = 2.0
    max_group_size: int = 3

    # Phase detection
    phase_definitions: Dict[str, List[str]] = field(default_factory=dict)

    # Default temporal window
    default_temporal_window_minutes: float = 15.0


@dataclass
class InteractionGroup:
    """A group of 2-3 violations that interact synergistically"""
    group_id: str
    violation_ids: List[str]
    interaction_type: InteractionType
    pattern_id: str
    multiplier: float
    base_combined_weight: float  # Sum of individual weights before multiplier
    synergistic_weight: float    # Weight after multiplier
    clinical_rationale: str
    escalated_severity: Optional[HarmSeverity] = None


class ClinicalInteractionDetector:
    """
    Detects synergistic harm interactions between violations.

    All rules are injected via InteractionConfig - no hardcoded clinical rules.
    Supports pairwise and triple-jeopardy detection.
    """

    def __init__(self, config: InteractionConfig):
        if config is None:
            raise ValueError("config is required - no default interaction rules")
        self.config = config
        self._compiled_patterns: Dict[str, re.Pattern] = {}
        self._compile_patterns()

    def detect_interactions(
        self,
        violations: List[ViolationEvent],
        violation_weights: Optional[Dict[str, float]] = None,
    ) -> List[InteractionGroup]:
        """
        Detect all synergistic interactions in a violation list.

        Args:
            violations: List of extracted violations
            violation_weights: Mapping of violation_id -> computed weight

        Returns:
            List of InteractionGroup, each containing 2-3 interacting violations
        """
        if len(violations) < 2:
            return []

        weights = violation_weights or {}
        phase_assignments = self._assign_phases(violations)

        # Pairwise detection
        pairwise_groups = self._detect_pairwise(violations, phase_assignments, weights)

        # Triple jeopardy detection
        triple_groups: List[InteractionGroup] = []
        if (self.config.enable_triple_jeopardy
                and len(violations) >= 3
                and self.config.max_group_size >= 3):
            triple_groups = self._detect_triple_jeopardy(
                violations, pairwise_groups, phase_assignments, weights
            )

        return pairwise_groups + triple_groups

    def _detect_pairwise(
        self,
        violations: List[ViolationEvent],
        phase_assignments: Dict[str, str],
        weights: Dict[str, float],
    ) -> List[InteractionGroup]:
        """Detect all pairwise interactions"""
        groups: List[InteractionGroup] = []
        seen_pairs: Set[Tuple[str, str, str]] = set()  # (v_a_id, v_b_id, pattern_id)

        for i in range(len(violations)):
            for j in range(i + 1, len(violations)):
                v_a, v_b = violations[i], violations[j]
                best_match = self._find_best_matching_pattern(
                    v_a, v_b, phase_assignments
                )
                if best_match is not None:
                    pair_key = (v_a.violation_id, v_b.violation_id, best_match.pattern_id)
                    if pair_key not in seen_pairs:
                        seen_pairs.add(pair_key)
                        base_combined = (
                            weights.get(v_a.violation_id, 0.0)
                            + weights.get(v_b.violation_id, 0.0)
                        )
                        multiplier = min(best_match.multiplier, best_match.max_multiplier)
                        groups.append(InteractionGroup(
                            group_id=f"pair_{uuid.uuid4().hex[:8]}",
                            violation_ids=[v_a.violation_id, v_b.violation_id],
                            interaction_type=best_match.interaction_type,
                            pattern_id=best_match.pattern_id,
                            multiplier=multiplier,
                            base_combined_weight=base_combined,
                            synergistic_weight=base_combined * multiplier,
                            clinical_rationale=best_match.clinical_rationale,
                            escalated_severity=best_match.escalated_severity,
                        ))
        return groups

    def _detect_triple_jeopardy(
        self,
        violations: List[ViolationEvent],
        pairwise_groups: List[InteractionGroup],
        phase_assignments: Dict[str, str],
        weights: Dict[str, float],
    ) -> List[InteractionGroup]:
        """Detect triple jeopardy: 3+ violations in same phase/window"""
        groups: List[InteractionGroup] = []

        # Group violations by phase
        phase_to_violations: Dict[str, List[ViolationEvent]] = {}
        for v in violations:
            phase = phase_assignments.get(v.violation_id, "unknown")
            if phase != "unknown":
                phase_to_violations.setdefault(phase, []).append(v)

        # Check each phase for 3+ violations within temporal window
        window = self.config.default_temporal_window_minutes
        for phase, phase_violations in phase_to_violations.items():
            if len(phase_violations) < 3:
                continue

            # Find clusters within temporal window
            sorted_vs = sorted(phase_violations, key=lambda v: v.timestamp_minutes)
            for i in range(len(sorted_vs) - 2):
                cluster = [sorted_vs[i]]
                for j in range(i + 1, min(i + self.config.max_group_size, len(sorted_vs))):
                    if sorted_vs[j].timestamp_minutes - sorted_vs[i].timestamp_minutes <= window:
                        cluster.append(sorted_vs[j])

                if len(cluster) >= 3:
                    vids = [v.violation_id for v in cluster[:self.config.max_group_size]]
                    # Skip if already covered by existing triple group
                    vids_set = frozenset(vids)
                    if any(frozenset(g.violation_ids) == vids_set for g in groups):
                        continue

                    # Find best matching pattern for this triple
                    best_pattern = self._find_triple_pattern(cluster, phase_assignments)
                    if best_pattern is None:
                        # Use a generic phase_compounding pattern if available
                        best_pattern = self._find_phase_compound_pattern()

                    if best_pattern is not None:
                        base_combined = sum(weights.get(vid, 0.0) for vid in vids)
                        multiplier = self._compute_triple_multiplier(best_pattern)
                        groups.append(InteractionGroup(
                            group_id=f"triple_{uuid.uuid4().hex[:8]}",
                            violation_ids=vids,
                            interaction_type=InteractionType.PHASE_COMPOUNDING,
                            pattern_id=best_pattern.pattern_id,
                            multiplier=multiplier,
                            base_combined_weight=base_combined,
                            synergistic_weight=base_combined * multiplier,
                            clinical_rationale=(
                                f"Triple jeopardy in {phase} phase: "
                                f"{best_pattern.clinical_rationale}"
                            ),
                            escalated_severity=best_pattern.escalated_severity,
                        ))
        return groups

    def _find_best_matching_pattern(
        self,
        v_a: ViolationEvent,
        v_b: ViolationEvent,
        phase_assignments: Dict[str, str],
    ) -> Optional[InteractionPattern]:
        """Find the highest-multiplier pattern matching this violation pair"""
        best: Optional[InteractionPattern] = None

        for pattern in self.config.interaction_patterns:
            if not self._is_type_enabled(pattern.interaction_type):
                continue
            if self._matches_pattern(v_a, v_b, pattern, phase_assignments):
                if best is None or pattern.multiplier > best.multiplier:
                    best = pattern
            # Also check reversed order (a,b) vs (b,a)
            elif self._matches_pattern(v_b, v_a, pattern, phase_assignments):
                if best is None or pattern.multiplier > best.multiplier:
                    best = pattern
        return best

    def _matches_pattern(
        self,
        v_a: ViolationEvent,
        v_b: ViolationEvent,
        pattern: InteractionPattern,
        phase_assignments: Dict[str, str],
    ) -> bool:
        """Check if a violation pair matches an interaction pattern"""
        # Violation type check
        if pattern.violation_type_a is not None:
            if v_a.violation_type != pattern.violation_type_a:
                return False
        if pattern.violation_type_b is not None:
            if v_b.violation_type != pattern.violation_type_b:
                return False

        # Action pattern check
        if pattern.action_pattern_a is not None:
            if not self._action_matches(v_a, pattern.action_pattern_a):
                return False
        if pattern.action_pattern_b is not None:
            if not self._action_matches(v_b, pattern.action_pattern_b):
                return False

        # Temporal window check
        window = pattern.temporal_window_minutes or self.config.default_temporal_window_minutes
        if abs(v_a.timestamp_minutes - v_b.timestamp_minutes) > window:
            return False

        # Same phase check
        if pattern.require_same_phase:
            phase_a = phase_assignments.get(v_a.violation_id, "unknown")
            phase_b = phase_assignments.get(v_b.violation_id, "unknown")
            if phase_a != phase_b or phase_a == "unknown":
                return False

        # Same node check
        if pattern.require_same_node:
            if v_a.node_at_violation != v_b.node_at_violation:
                return False

        # Causal direction check
        if pattern.causal_direction == "a_before_b":
            if v_a.timestamp_minutes > v_b.timestamp_minutes:
                return False
        elif pattern.causal_direction == "b_before_a":
            if v_b.timestamp_minutes > v_a.timestamp_minutes:
                return False

        return True

    def _action_matches(self, violation: ViolationEvent, pattern: str) -> bool:
        """Check if a violation's action matches a regex pattern"""
        compiled = self._get_compiled_pattern(pattern)
        targets = [
            violation.action_involved or "",
            violation.expected_action or "",
        ]
        return any(compiled.search(t) for t in targets if t)

    def _get_compiled_pattern(self, pattern: str) -> re.Pattern:
        """Get or compile a regex pattern"""
        if pattern not in self._compiled_patterns:
            self._compiled_patterns[pattern] = re.compile(pattern, re.IGNORECASE)
        return self._compiled_patterns[pattern]

    def _assign_phases(
        self,
        violations: List[ViolationEvent],
    ) -> Dict[str, str]:
        """Assign clinical phases to violations based on config phase_definitions"""
        assignments: Dict[str, str] = {}
        if not self.config.phase_definitions:
            return assignments

        for v in violations:
            action_text = v.action_involved or v.expected_action or ""
            assigned_phase = "unknown"
            for phase_name, patterns in self.config.phase_definitions.items():
                for pat in patterns:
                    compiled = self._get_compiled_pattern(pat)
                    if compiled.search(action_text):
                        assigned_phase = phase_name
                        break
                if assigned_phase != "unknown":
                    break
            assignments[v.violation_id] = assigned_phase
        return assignments

    def _is_type_enabled(self, itype: InteractionType) -> bool:
        """Check if an interaction type is enabled in config"""
        enabled_map = {
            InteractionType.TEMPORAL_PROXIMITY: self.config.enable_temporal_proximity,
            InteractionType.CAUSAL_CHAIN: self.config.enable_causal_chain,
            InteractionType.CONTRAINDICATION_COMPOUND: self.config.enable_contraindication_compound,
            InteractionType.PHASE_COMPOUNDING: self.config.enable_phase_compounding,
            InteractionType.SEVERITY_ESCALATION: self.config.enable_severity_escalation,
        }
        return enabled_map.get(itype, True)

    def _find_triple_pattern(
        self,
        cluster: List[ViolationEvent],
        phase_assignments: Dict[str, str],
    ) -> Optional[InteractionPattern]:
        """Find a matching pattern for a triple cluster"""
        for pattern in self.config.interaction_patterns:
            if pattern.require_same_phase and self._is_type_enabled(pattern.interaction_type):
                # Check if all violations in cluster are in the same phase
                phases = {phase_assignments.get(v.violation_id, "unknown") for v in cluster}
                if len(phases) == 1 and "unknown" not in phases:
                    return pattern
        return None

    def _find_phase_compound_pattern(self) -> Optional[InteractionPattern]:
        """Find any phase_compounding pattern as fallback for triple jeopardy"""
        for pattern in self.config.interaction_patterns:
            if pattern.interaction_type == InteractionType.PHASE_COMPOUNDING:
                return pattern
        return None

    def _compute_triple_multiplier(self, pattern: InteractionPattern) -> float:
        """Compute effective multiplier for triple jeopardy"""
        multiplier = pattern.multiplier * self.config.triple_jeopardy_multiplier
        return min(multiplier, pattern.max_multiplier)

    def _compile_patterns(self):
        """Pre-compile regex patterns from all interaction patterns"""
        for pattern in self.config.interaction_patterns:
            if pattern.action_pattern_a:
                self._compiled_patterns[pattern.action_pattern_a] = re.compile(
                    pattern.action_pattern_a, re.IGNORECASE
                )
            if pattern.action_pattern_b:
                self._compiled_patterns[pattern.action_pattern_b] = re.compile(
                    pattern.action_pattern_b, re.IGNORECASE
                )
        # Pre-compile phase definition patterns
        for patterns in self.config.phase_definitions.values():
            for pat in patterns:
                if pat not in self._compiled_patterns:
                    self._compiled_patterns[pat] = re.compile(pat, re.IGNORECASE)
