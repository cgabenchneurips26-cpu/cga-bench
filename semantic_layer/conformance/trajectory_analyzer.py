"""
Trajectory-level analysis for ActivityEvent sequences.

Provides:
- Phase detection: segments event sequences into clinical phases
- Bottleneck identification: finds actions with tightest timing margins
- Critical path: longest constraint-driven path through events
- Temporal sensitivity: how timing changes affect outcomes

All features opt-in via TrajectoryConfig.
"""
from __future__ import annotations

import copy
from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple

from .activity import ActivityEvent
from .temporal_verifier import (
    TemporalConstraint,
    TemporalConstraintType,
    TemporalVerificationConfig,
    TemporalVerificationResult,
    TemporalVerifier,
)


@dataclass
class TrajectoryConfig:
    """Configuration for trajectory analysis.

    All defaults produce meaningful analysis when config is passed.
    """
    enable_phase_detection: bool = True
    enable_bottleneck_detection: bool = True
    enable_critical_path: bool = True
    enable_sensitivity_analysis: bool = False
    phase_gap_threshold_minutes: float = 10.0
    phase_patterns: Dict[str, List[str]] = field(default_factory=dict)
    bottleneck_margin_threshold: float = 5.0
    sensitivity_delta_minutes: float = 1.0


@dataclass
class ClinicalPhase:
    """A detected clinical phase in the trajectory."""
    phase_id: str
    phase_name: str
    start_time: float
    end_time: float
    duration_minutes: float
    activities: List[ActivityEvent]
    activity_count: int
    dominant_activity_type: Optional[str] = None


@dataclass
class BottleneckInfo:
    """Information about a timing-critical action."""
    activity_name: str
    event_index: int
    timestamp_min: float
    timing_margin_minutes: float
    constraint_id: Optional[str] = None
    is_violated: bool = False
    urgency_score: float = 0.0


@dataclass
class CriticalPathStep:
    """A step in the critical path through the trajectory."""
    activity_name: str
    event_index: int
    timestamp_min: float
    slack_minutes: float
    is_on_critical_path: bool = True
    predecessor: Optional[str] = None
    successor: Optional[str] = None


@dataclass
class CriticalPath:
    """The critical path through a trajectory."""
    steps: List[CriticalPathStep]
    total_duration_minutes: float
    bottleneck_step: Optional[CriticalPathStep] = None
    path_length: int = 0
    constraint_coverage: List[str] = field(default_factory=list)


@dataclass
class SensitivityResult:
    """Result of temporal sensitivity analysis for one action."""
    activity_name: str
    original_penalty: float
    perturbed_penalty: float
    sensitivity: float
    is_critical: bool = False


@dataclass
class TrajectoryMetrics:
    """Aggregate metrics for the trajectory."""
    total_duration_minutes: float
    event_count: int
    unique_activities: int
    avg_inter_event_gap: float
    max_inter_event_gap: float
    phase_count: int = 0
    bottleneck_count: int = 0
    critical_path_length: int = 0
    overall_urgency: float = 0.0


@dataclass
class TrajectoryAnalysis:
    """Complete trajectory analysis result."""
    phases: List[ClinicalPhase]
    bottlenecks: List[BottleneckInfo]
    critical_path: Optional[CriticalPath]
    metrics: TrajectoryMetrics
    sensitivity_results: List[SensitivityResult] = field(default_factory=list)
    phase_transitions: List[Dict[str, Any]] = field(default_factory=list)


# Default phase patterns (activity name prefix matching)
_DEFAULT_PHASE_PATTERNS: Dict[str, List[str]] = {
    "assessment": ["QUERY_", "OBSERVE_", "ASSESS_", "GET_"],
    "diagnosis": ["DIAGNOSE", "CONDITION", "INTERPRET_"],
    "treatment": ["PRESCRIBE", "GIVE_", "MEDICATION", "ADMINISTER"],
    "procedure": ["PROCEDURE", "PERFORM_", "ACTIVATE_"],
    "monitoring": ["MONITOR_", "REASSESS_", "REMEASURE_", "RECHECK_"],
    "disposition": ["DISPOSITION", "DISCHARGE", "ADMIT_", "TRANSFER_"],
}


class PhaseDetector:
    """Segments event sequences into clinical phases.

    Uses activity name pattern matching combined with temporal gap
    detection to identify phase boundaries.
    """

    def __init__(self, config: Optional[TrajectoryConfig] = None):
        self._config = config or TrajectoryConfig()
        self._patterns = (
            config.phase_patterns if config and config.phase_patterns
            else _DEFAULT_PHASE_PATTERNS
        )

    def detect_phases(self, events: List[ActivityEvent]) -> List[ClinicalPhase]:
        """Detect clinical phases from event sequence.

        Algorithm:
        1. Classify each event by pattern matching
        2. Detect gap boundaries
        3. Split at gaps, group consecutive same-phase events
        4. Merge adjacent same-type phases
        """
        if not events:
            return []

        # Step 1: Classify each event
        classifications = [self._classify_activity(e.name) for e in events]

        # Step 2: Detect gap boundaries
        boundaries = self._detect_gap_boundaries(events)

        # Step 3: Segment into phases
        segments: List[Tuple[str, List[int]]] = []
        current_phase = classifications[0]
        current_indices: List[int] = [0]

        for i in range(1, len(events)):
            is_boundary = i in boundaries
            phase_changed = classifications[i] != current_phase

            if is_boundary or phase_changed:
                segments.append((current_phase, list(current_indices)))
                current_phase = classifications[i]
                current_indices = [i]
            else:
                current_indices.append(i)

        segments.append((current_phase, list(current_indices)))

        # Step 4: Build ClinicalPhase objects
        phases: List[ClinicalPhase] = []
        for seg_idx, (phase_name, indices) in enumerate(segments):
            phase_events = [events[i] for i in indices]
            start_time = phase_events[0].timestamp_min
            end_time = phase_events[-1].timestamp_min
            dominant = self._compute_dominant_type(phase_events)
            phases.append(ClinicalPhase(
                phase_id=f"phase_{seg_idx + 1:03d}",
                phase_name=phase_name,
                start_time=start_time,
                end_time=end_time,
                duration_minutes=end_time - start_time,
                activities=phase_events,
                activity_count=len(phase_events),
                dominant_activity_type=dominant,
            ))

        # Step 5: Merge adjacent same-type phases
        phases = self._merge_adjacent_phases(phases)

        return phases

    def _classify_activity(self, activity_name: str) -> str:
        """Classify an activity name into a phase based on patterns."""
        upper = activity_name.upper()
        for phase_name, patterns in self._patterns.items():
            for pattern in patterns:
                if upper.startswith(pattern) or pattern in upper:
                    return phase_name
        return "unknown"

    def _detect_gap_boundaries(self, events: List[ActivityEvent]) -> Set[int]:
        """Find indices where temporal gaps exceed threshold."""
        boundaries: Set[int] = set()
        threshold = self._config.phase_gap_threshold_minutes
        for i in range(1, len(events)):
            gap = events[i].timestamp_min - events[i - 1].timestamp_min
            if gap > threshold:
                boundaries.add(i)
        return boundaries

    def _merge_adjacent_phases(
        self, phases: List[ClinicalPhase]
    ) -> List[ClinicalPhase]:
        """Merge adjacent phases of the same type (unless separated by gap)."""
        if len(phases) <= 1:
            return phases

        threshold = self._config.phase_gap_threshold_minutes
        merged: List[ClinicalPhase] = [phases[0]]
        for phase in phases[1:]:
            prev = merged[-1]
            gap = phase.start_time - prev.end_time
            if prev.phase_name == phase.phase_name and gap <= threshold:
                # Merge
                all_activities = prev.activities + phase.activities
                merged[-1] = ClinicalPhase(
                    phase_id=prev.phase_id,
                    phase_name=prev.phase_name,
                    start_time=prev.start_time,
                    end_time=phase.end_time,
                    duration_minutes=phase.end_time - prev.start_time,
                    activities=all_activities,
                    activity_count=len(all_activities),
                    dominant_activity_type=self._compute_dominant_type(all_activities),
                )
            else:
                merged.append(phase)

        # Reassign sequential IDs
        for i, phase in enumerate(merged):
            phase.phase_id = f"phase_{i + 1:03d}"

        return merged

    def _compute_dominant_type(
        self, activities: List[ActivityEvent]
    ) -> Optional[str]:
        """Find most common activity pattern in a phase."""
        if not activities:
            return None
        counts: Dict[str, int] = defaultdict(int)
        for act in activities:
            phase = self._classify_activity(act.name)
            counts[phase] += 1
        return max(counts, key=counts.get)  # type: ignore


class TrajectoryAnalyzer:
    """Full trajectory analysis: phases, bottlenecks, critical path.

    Usage:
        config = TrajectoryConfig(
            enable_phase_detection=True,
            enable_bottleneck_detection=True,
            enable_critical_path=True,
        )
        analyzer = TrajectoryAnalyzer(config)
        result = analyzer.analyze(events, constraints)
    """

    def __init__(self, config: Optional[TrajectoryConfig] = None):
        self._config = config or TrajectoryConfig()
        self._phase_detector = PhaseDetector(self._config)

    def analyze(
        self,
        events: List[ActivityEvent],
        constraints: Optional[List[TemporalConstraint]] = None,
        derived_flags: Optional[Dict[str, bool]] = None,
        verification_result: Optional[TemporalVerificationResult] = None,
    ) -> TrajectoryAnalysis:
        """Perform full trajectory analysis.

        Args:
            events: Ordered ActivityEvent sequence
            constraints: Temporal constraints (for bottleneck/critical path)
            derived_flags: Flags for constraint guards
            verification_result: Pre-computed verification (avoids re-computation)

        Returns:
            TrajectoryAnalysis with phases, bottlenecks, critical path, metrics
        """
        constraints = constraints or []

        # Phase detection
        phases: List[ClinicalPhase] = []
        if self._config.enable_phase_detection:
            phases = self._phase_detector.detect_phases(events)

        # Bottleneck detection
        bottlenecks: List[BottleneckInfo] = []
        if self._config.enable_bottleneck_detection and constraints:
            bottlenecks = self.detect_bottlenecks(events, constraints, derived_flags)

        # Critical path
        critical_path: Optional[CriticalPath] = None
        if self._config.enable_critical_path and constraints:
            critical_path = self.compute_critical_path(events, constraints)

        # Sensitivity analysis
        sensitivity_results: List[SensitivityResult] = []
        if self._config.enable_sensitivity_analysis and constraints:
            sensitivity_results = self.compute_sensitivity(
                events, constraints, derived_flags
            )

        # Phase transitions
        phase_transitions = self._detect_phase_transitions(phases)

        # Metrics
        metrics = self.compute_metrics(events, phases, bottlenecks, critical_path)

        return TrajectoryAnalysis(
            phases=phases,
            bottlenecks=bottlenecks,
            critical_path=critical_path,
            metrics=metrics,
            sensitivity_results=sensitivity_results,
            phase_transitions=phase_transitions,
        )

    def detect_bottlenecks(
        self,
        events: List[ActivityEvent],
        constraints: List[TemporalConstraint],
        derived_flags: Optional[Dict[str, bool]] = None,
    ) -> List[BottleneckInfo]:
        """Identify actions with tightest timing margins."""
        if not events or not constraints:
            return []

        verifier = TemporalVerifier()
        margins = verifier.compute_timing_margins(events, constraints)

        # Build activity index
        activity_index: Dict[str, List[Tuple[int, ActivityEvent]]] = {}
        for i, event in enumerate(events):
            if event.name not in activity_index:
                activity_index[event.name] = []
            activity_index[event.name].append((i, event))

        # Map constraints to target events
        bottlenecks: List[BottleneckInfo] = []
        seen_indices: Set[int] = set()
        threshold = self._config.bottleneck_margin_threshold

        for constraint in constraints:
            margin = margins.get(constraint.constraint_id)
            if margin is None:
                continue

            if margin >= threshold:
                continue  # Not a bottleneck

            # Find the target event for this constraint
            target_name = (
                constraint.target_activity or constraint.source_activity
            )
            if not target_name:
                continue

            target_events = activity_index.get(target_name, [])
            if not target_events:
                continue

            # Use first occurrence
            evt_idx, evt = target_events[0]
            if evt_idx in seen_indices:
                continue
            seen_indices.add(evt_idx)

            urgency = self._compute_urgency_score(margin, threshold)
            bottlenecks.append(BottleneckInfo(
                activity_name=target_name,
                event_index=evt_idx,
                timestamp_min=evt.timestamp_min,
                timing_margin_minutes=margin,
                constraint_id=constraint.constraint_id,
                is_violated=(margin < 0),
                urgency_score=urgency,
            ))

        # Sort by urgency descending
        bottlenecks.sort(key=lambda b: b.urgency_score, reverse=True)
        return bottlenecks

    def compute_critical_path(
        self,
        events: List[ActivityEvent],
        constraints: List[TemporalConstraint],
    ) -> CriticalPath:
        """Compute the critical path through the trajectory.

        Uses DAG-based longest path with topological sort.
        """
        if not events or not constraints:
            return CriticalPath(
                steps=[], total_duration_minutes=0.0, path_length=0
            )

        # Build DAG from constraints
        dag, constraint_map = self._build_constraint_dag(constraints)

        if not dag:
            return CriticalPath(
                steps=[], total_duration_minutes=0.0, path_length=0
            )

        # Get all nodes
        all_nodes: Set[str] = set()
        for src, edges in dag.items():
            all_nodes.add(src)
            for tgt, _ in edges:
                all_nodes.add(tgt)

        # Build event time map (first occurrence of each activity)
        event_times: Dict[str, Tuple[int, float]] = {}
        for i, event in enumerate(events):
            if event.name not in event_times:
                event_times[event.name] = (i, event.timestamp_min)

        # Topological sort
        topo_order = self._topological_sort(dag, all_nodes)
        if not topo_order:
            return CriticalPath(
                steps=[], total_duration_minutes=0.0, path_length=0
            )

        # Forward pass: compute earliest start
        earliest: Dict[str, float] = {node: 0.0 for node in all_nodes}
        predecessors: Dict[str, Optional[str]] = {node: None for node in all_nodes}

        for node in topo_order:
            for succ, weight in dag.get(node, []):
                new_earliest = earliest[node] + weight
                if new_earliest > earliest[succ]:
                    earliest[succ] = new_earliest
                    predecessors[succ] = node

        # Find total duration (max earliest)
        if not earliest:
            return CriticalPath(
                steps=[], total_duration_minutes=0.0, path_length=0
            )
        total_duration = max(earliest.values())

        # Backward pass: compute latest start
        latest: Dict[str, float] = {node: total_duration for node in all_nodes}
        for node in reversed(topo_order):
            for succ, weight in dag.get(node, []):
                new_latest = latest[succ] - weight
                if new_latest < latest[node]:
                    latest[node] = new_latest

        # Compute slack
        slack: Dict[str, float] = {}
        for node in all_nodes:
            slack[node] = latest[node] - earliest[node]

        # Build critical path (nodes with slack ~= 0)
        critical_nodes = [
            node for node in topo_order
            if abs(slack.get(node, float("inf"))) < 0.001
        ]

        steps: List[CriticalPathStep] = []
        for i, node in enumerate(critical_nodes):
            evt_info = event_times.get(node)
            evt_idx = evt_info[0] if evt_info else -1
            evt_time = evt_info[1] if evt_info else earliest.get(node, 0.0)

            step = CriticalPathStep(
                activity_name=node,
                event_index=evt_idx,
                timestamp_min=evt_time,
                slack_minutes=slack.get(node, 0.0),
                is_on_critical_path=True,
                predecessor=critical_nodes[i - 1] if i > 0 else None,
                successor=critical_nodes[i + 1] if i < len(critical_nodes) - 1 else None,
            )
            steps.append(step)

        # Find bottleneck step (the one with smallest realized margin)
        bottleneck_step = None
        if steps:
            bottleneck_step = steps[0]  # First step has zero slack by definition

        # Constraint coverage
        coverage = list(constraint_map.keys())

        return CriticalPath(
            steps=steps,
            total_duration_minutes=total_duration,
            bottleneck_step=bottleneck_step,
            path_length=len(steps),
            constraint_coverage=coverage,
        )

    def compute_sensitivity(
        self,
        events: List[ActivityEvent],
        constraints: List[TemporalConstraint],
        derived_flags: Optional[Dict[str, bool]] = None,
    ) -> List[SensitivityResult]:
        """Temporal sensitivity analysis.

        For each unique activity, perturb its timestamp by +delta and
        measure the change in total verification penalty.
        """
        if not events or not constraints:
            return []

        verifier = TemporalVerifier()
        delta = self._config.sensitivity_delta_minutes

        # Baseline
        baseline_result = verifier.verify(events, constraints, derived_flags)
        baseline_penalty = baseline_result.total_penalty

        # Get unique activities
        unique_activities: Set[str] = set()
        for event in events:
            unique_activities.add(event.name)

        results: List[SensitivityResult] = []
        for activity_name in sorted(unique_activities):
            # Create perturbed trace
            perturbed = []
            for event in events:
                if event.name == activity_name:
                    perturbed_event = ActivityEvent(
                        name=event.name,
                        timestamp_min=event.timestamp_min + delta,
                        raw_event=event.raw_event,
                        confidence=event.confidence,
                        match_source=event.match_source,
                    )
                    perturbed.append(perturbed_event)
                else:
                    perturbed.append(event)

            # Re-sort by timestamp
            perturbed.sort(key=lambda e: e.timestamp_min)

            # Re-verify
            perturbed_result = verifier.verify(perturbed, constraints, derived_flags)
            perturbed_penalty = perturbed_result.total_penalty

            sensitivity = (perturbed_penalty - baseline_penalty) / delta if delta > 0 else 0.0
            is_critical = abs(sensitivity) > 0.5

            results.append(SensitivityResult(
                activity_name=activity_name,
                original_penalty=baseline_penalty,
                perturbed_penalty=perturbed_penalty,
                sensitivity=sensitivity,
                is_critical=is_critical,
            ))

        # Sort by |sensitivity| descending
        results.sort(key=lambda r: abs(r.sensitivity), reverse=True)
        return results

    def compute_metrics(
        self,
        events: List[ActivityEvent],
        phases: List[ClinicalPhase],
        bottlenecks: List[BottleneckInfo],
        critical_path: Optional[CriticalPath],
    ) -> TrajectoryMetrics:
        """Compute aggregate trajectory metrics."""
        if not events:
            return TrajectoryMetrics(
                total_duration_minutes=0.0,
                event_count=0,
                unique_activities=0,
                avg_inter_event_gap=0.0,
                max_inter_event_gap=0.0,
            )

        total_duration = events[-1].timestamp_min - events[0].timestamp_min
        unique = len(set(e.name for e in events))

        # Inter-event gaps
        gaps = []
        for i in range(1, len(events)):
            gaps.append(events[i].timestamp_min - events[i - 1].timestamp_min)

        avg_gap = sum(gaps) / len(gaps) if gaps else 0.0
        max_gap = max(gaps) if gaps else 0.0

        # Overall urgency
        overall_urgency = 0.0
        if bottlenecks:
            overall_urgency = sum(b.urgency_score for b in bottlenecks) / len(bottlenecks)

        return TrajectoryMetrics(
            total_duration_minutes=total_duration,
            event_count=len(events),
            unique_activities=unique,
            avg_inter_event_gap=avg_gap,
            max_inter_event_gap=max_gap,
            phase_count=len(phases),
            bottleneck_count=len(bottlenecks),
            critical_path_length=critical_path.path_length if critical_path else 0,
            overall_urgency=overall_urgency,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _build_constraint_dag(
        self, constraints: List[TemporalConstraint]
    ) -> Tuple[Dict[str, List[Tuple[str, float]]], Dict[str, str]]:
        """Build adjacency list DAG from constraint dependencies.

        Returns:
            (dag, constraint_map): dag maps activity -> [(successor, weight)],
            constraint_map maps constraint_id -> description
        """
        dag: Dict[str, List[Tuple[str, float]]] = defaultdict(list)
        constraint_map: Dict[str, str] = {}

        for constraint in constraints:
            if constraint.constraint_type == TemporalConstraintType.BOUNDED_RESPONSE:
                if constraint.source_activity and constraint.target_activity:
                    weight = constraint.max_minutes or 0.0
                    dag[constraint.source_activity].append(
                        (constraint.target_activity, weight)
                    )
                    constraint_map[constraint.constraint_id] = (
                        f"{constraint.source_activity} -> {constraint.target_activity}"
                    )

            elif constraint.constraint_type == TemporalConstraintType.DEADLINE_CHAIN:
                for i in range(len(constraint.chain_activities) - 1):
                    src = constraint.chain_activities[i]
                    tgt = constraint.chain_activities[i + 1]
                    weight = (
                        constraint.chain_deadlines[i]
                        if i < len(constraint.chain_deadlines)
                        else 0.0
                    )
                    dag[src].append((tgt, weight))
                if constraint.chain_activities:
                    constraint_map[constraint.constraint_id] = (
                        " -> ".join(constraint.chain_activities)
                    )

        return dict(dag), constraint_map

    def _topological_sort(
        self,
        dag: Dict[str, List[Tuple[str, float]]],
        all_nodes: Set[str],
    ) -> List[str]:
        """Topological sort using Kahn's algorithm."""
        # Compute in-degree
        in_degree: Dict[str, int] = {node: 0 for node in all_nodes}
        for src, edges in dag.items():
            for tgt, _ in edges:
                in_degree[tgt] = in_degree.get(tgt, 0) + 1

        queue: deque = deque()
        for node in all_nodes:
            if in_degree.get(node, 0) == 0:
                queue.append(node)

        result: List[str] = []
        while queue:
            node = queue.popleft()
            result.append(node)
            for succ, _ in dag.get(node, []):
                in_degree[succ] -= 1
                if in_degree[succ] == 0:
                    queue.append(succ)

        # If result doesn't contain all nodes, there's a cycle
        if len(result) != len(all_nodes):
            # Return partial order (skip cycle nodes)
            return result

        return result

    def _compute_urgency_score(self, margin: float, threshold: float) -> float:
        """Convert timing margin to urgency score in [0, 1]."""
        if margin <= 0:
            return 1.0
        if threshold <= 0:
            return 0.0
        score = 1.0 - (margin / threshold)
        return max(0.0, min(1.0, score))

    def _detect_phase_transitions(
        self, phases: List[ClinicalPhase]
    ) -> List[Dict[str, Any]]:
        """Detect phase transition points."""
        transitions: List[Dict[str, Any]] = []
        for i in range(1, len(phases)):
            prev = phases[i - 1]
            curr = phases[i]
            transitions.append({
                "from_phase": prev.phase_name,
                "to_phase": curr.phase_name,
                "transition_time": curr.start_time,
                "gap_minutes": curr.start_time - prev.end_time,
            })
        return transitions
