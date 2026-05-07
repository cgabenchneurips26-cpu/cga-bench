"""
Enhanced error classification with chain detection, contextual severity,
and recovery attempt evaluation.

Operates on sequences of ActivityEvent, extending the per-event
ClassifiedError from error_taxonomy.py with contextual analysis.

All features opt-in via ErrorClassificationConfig.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse

from .activity import ActivityEvent
from .error_taxonomy import (
    ClassifiedError,
    ErrorCategory,
    ENVIRONMENT_CONSTRAINT_CATEGORIES,
    classify_error,
)


@dataclass
class ErrorClassificationConfig:
    """Configuration for enhanced error classification.

    All defaults preserve backward-compatible behavior (no enrichment).
    """
    enable_contextual_severity: bool = False
    enable_chain_detection: bool = False
    enable_recovery_evaluation: bool = False
    max_chain_window: int = 5
    chain_time_window_minutes: float = 2.0
    severity_weights: Dict[str, float] = field(default_factory=lambda: {
        "base": 0.4,
        "context": 0.3,
        "recoverability": 0.2,
        "timing": 0.1,
    })


@dataclass
class ContextualSeverity:
    """Multi-factor severity assessment for a classified error."""
    base_severity: float          # 0-1 from error category
    context_multiplier: float     # 1.0-2.0 based on clinical urgency
    recoverability: float         # 0-1, higher = more recoverable
    clinical_impact: float        # 0-1 based on what was attempted
    final_severity: float         # weighted composite [0,1]


@dataclass
class RecoveryInfo:
    """Information about agent recovery attempts after an error."""
    attempted: bool
    successful: bool
    retry_count: int
    recovery_events: List[int]    # indices of recovery attempt events
    time_to_recovery_minutes: Optional[float]


@dataclass
class ErrorChain:
    """A chain of causally-related errors."""
    chain_id: str
    error_indices: List[int]      # indices into the event list
    root_cause_index: int
    chain_length: int
    root_category: ErrorCategory
    target_resource: Optional[str]
    recovery_info: Optional[RecoveryInfo] = None


@dataclass
class EnrichedClassifiedError:
    """ClassifiedError extended with contextual analysis.

    Wraps the original ClassifiedError via composition to maintain
    clean separation and avoid dataclass inheritance issues.
    """
    base_error: ClassifiedError
    event_index: int
    contextual_severity: Optional[ContextualSeverity] = None
    chain_id: Optional[str] = None
    is_chain_root: bool = False
    recovery_info: Optional[RecoveryInfo] = None
    clinical_context: Optional[str] = None

    @property
    def error_category(self) -> ErrorCategory:
        return self.base_error.error_category

    @property
    def is_environment_constraint(self) -> bool:
        return self.base_error.is_environment_constraint

    @property
    def issue_code(self) -> Optional[str]:
        return self.base_error.issue_code

    @property
    def issue_severity(self) -> Optional[str]:
        return self.base_error.issue_severity


# Base severity by error category (static, no external deps)
_BASE_SEVERITY_MAP: Dict[ErrorCategory, float] = {
    ErrorCategory.AUTH: 0.3,
    ErrorCategory.NOT_FOUND: 0.2,
    ErrorCategory.INVALID: 0.7,
    ErrorCategory.RATE_LIMIT: 0.2,
    ErrorCategory.SERVER_ERROR: 0.4,
    ErrorCategory.TIMEOUT: 0.5,
    ErrorCategory.UNKNOWN: 0.5,
}

# Recoverability by error category (higher = more recoverable)
_RECOVERABILITY_MAP: Dict[ErrorCategory, float] = {
    ErrorCategory.AUTH: 0.2,
    ErrorCategory.NOT_FOUND: 0.8,
    ErrorCategory.INVALID: 0.9,
    ErrorCategory.RATE_LIMIT: 0.95,
    ErrorCategory.SERVER_ERROR: 0.6,
    ErrorCategory.TIMEOUT: 0.7,
    ErrorCategory.UNKNOWN: 0.5,
}


class ErrorClassifier:
    """Sequence-aware error classifier with chain detection and contextual severity.

    Processes a list of ActivityEvents, extracts ClassifiedErrors,
    then enriches them with chain detection, contextual severity,
    and recovery evaluation.

    Usage:
        config = ErrorClassificationConfig(
            enable_chain_detection=True,
            enable_contextual_severity=True,
            enable_recovery_evaluation=True,
        )
        classifier = ErrorClassifier(config)
        enriched = classifier.classify_events(events)
    """

    def __init__(self, config: Optional[ErrorClassificationConfig] = None):
        self._config = config or ErrorClassificationConfig()

    def classify_events(
        self,
        events: List[ActivityEvent],
    ) -> List[EnrichedClassifiedError]:
        """Classify all errors in an event sequence with enrichment.

        Args:
            events: Ordered list of ActivityEvents

        Returns:
            List of EnrichedClassifiedError for events that contain errors.
            Events without errors are not included.
        """
        indexed_errors = self._extract_errors(events)

        if not indexed_errors:
            return []

        # Detect chains (if enabled)
        chains: List[ErrorChain] = []
        if self._config.enable_chain_detection:
            chains = self.detect_chains(indexed_errors, events)

        # Build chain lookup: event_index -> chain_id
        chain_lookup = self._build_chain_lookup(chains)

        # Build root set for recovery assignment
        root_indices: Set[int] = {c.root_cause_index for c in chains}

        # Enrich each error
        enriched: List[EnrichedClassifiedError] = []
        for idx, base_error in indexed_errors:
            chain_id = chain_lookup.get(idx)
            is_root = idx in root_indices

            # Contextual severity
            ctx_severity = None
            if self._config.enable_contextual_severity:
                ctx_severity = self.compute_contextual_severity(
                    base_error, events[idx], events, idx
                )

            # Clinical context
            clinical_ctx = self._infer_clinical_context(events[idx])

            # Recovery info (assigned to chain root only)
            recovery = None
            if self._config.enable_recovery_evaluation and is_root:
                chain = next((c for c in chains if c.root_cause_index == idx), None)
                if chain:
                    recovery = self.evaluate_recovery(chain, events)

            enriched.append(EnrichedClassifiedError(
                base_error=base_error,
                event_index=idx,
                contextual_severity=ctx_severity,
                chain_id=chain_id,
                is_chain_root=is_root,
                recovery_info=recovery,
                clinical_context=clinical_ctx,
            ))

        return enriched

    def detect_chains(
        self,
        indexed_errors: List[Tuple[int, ClassifiedError]],
        events: List[ActivityEvent],
    ) -> List[ErrorChain]:
        """Detect cascading error chains from consecutive error events.

        Groups consecutive error events that share the same target
        resource and occur within the configured time/index window.

        Args:
            indexed_errors: List of (event_index, ClassifiedError) tuples
            events: Full event list for timestamp access

        Returns:
            List of ErrorChain objects
        """
        if len(indexed_errors) < 2:
            return []

        chains: List[ErrorChain] = []
        chain_counter = 0
        current_chain_indices: List[int] = [indexed_errors[0][0]]
        current_resource = self._extract_target_resource(events[indexed_errors[0][0]])

        for i in range(1, len(indexed_errors)):
            prev_idx = indexed_errors[i - 1][0]
            curr_idx = indexed_errors[i][0]
            curr_event = events[curr_idx]

            # Check event index gap
            index_gap = curr_idx - prev_idx
            if index_gap > self._config.max_chain_window:
                if len(current_chain_indices) >= 2:
                    chains.append(self._finalize_chain(
                        chain_counter, current_chain_indices,
                        indexed_errors, events, current_resource
                    ))
                    chain_counter += 1
                current_chain_indices = [curr_idx]
                current_resource = self._extract_target_resource(curr_event)
                continue

            # Check time proximity
            time_gap = events[curr_idx].timestamp_min - events[prev_idx].timestamp_min
            if time_gap > self._config.chain_time_window_minutes:
                if len(current_chain_indices) >= 2:
                    chains.append(self._finalize_chain(
                        chain_counter, current_chain_indices,
                        indexed_errors, events, current_resource
                    ))
                    chain_counter += 1
                current_chain_indices = [curr_idx]
                current_resource = self._extract_target_resource(curr_event)
                continue

            # Check resource similarity
            curr_resource = self._extract_target_resource(curr_event)
            if (current_resource and curr_resource
                    and current_resource != curr_resource):
                if len(current_chain_indices) >= 2:
                    chains.append(self._finalize_chain(
                        chain_counter, current_chain_indices,
                        indexed_errors, events, current_resource
                    ))
                    chain_counter += 1
                current_chain_indices = [curr_idx]
                current_resource = curr_resource
                continue

            # Extend current chain
            current_chain_indices.append(curr_idx)

        # Finalize last chain
        if len(current_chain_indices) >= 2:
            chains.append(self._finalize_chain(
                chain_counter, current_chain_indices,
                indexed_errors, events, current_resource
            ))

        return chains

    def evaluate_recovery(
        self,
        chain: ErrorChain,
        events: List[ActivityEvent],
    ) -> RecoveryInfo:
        """Evaluate whether the agent recovered from an error chain.

        Looks for events after the chain that target the same resource
        and succeed (no error classification).

        Args:
            chain: ErrorChain to evaluate
            events: Full event list

        Returns:
            RecoveryInfo with attempt/success details
        """
        last_error_idx = max(chain.error_indices)
        target_resource = chain.target_resource
        recovery_events: List[int] = []
        recovery_successful = False
        time_to_recovery: Optional[float] = None

        search_end = min(
            last_error_idx + self._config.max_chain_window + 1,
            len(events)
        )
        for i in range(last_error_idx + 1, search_end):
            event = events[i]
            event_resource = self._extract_target_resource(event)

            # Check if this targets the same resource
            if target_resource and event_resource == target_resource:
                recovery_events.append(i)
                # Check if this event is an error
                err = self._classify_single_event(event)
                if err is None:
                    recovery_successful = True
                    time_to_recovery = (
                        events[i].timestamp_min -
                        events[chain.root_cause_index].timestamp_min
                    )
                    break

        return RecoveryInfo(
            attempted=len(recovery_events) > 0,
            successful=recovery_successful,
            retry_count=len(recovery_events),
            recovery_events=recovery_events,
            time_to_recovery_minutes=time_to_recovery,
        )

    def compute_contextual_severity(
        self,
        error: ClassifiedError,
        event: ActivityEvent,
        all_events: List[ActivityEvent],
        event_index: int,
    ) -> ContextualSeverity:
        """Compute multi-factor contextual severity for an error.

        Factors:
        - base_severity: From error category (static)
        - context_multiplier: Clinical urgency of the attempted action
        - recoverability: How recoverable this error type is
        - clinical_impact: Impact based on what the action was trying to do

        Args:
            error: Base ClassifiedError
            event: The event that produced the error
            all_events: Full event sequence for context
            event_index: Index of this event in the sequence

        Returns:
            ContextualSeverity with computed final_severity
        """
        base = _BASE_SEVERITY_MAP.get(error.error_category, 0.5)
        context_mult = self._compute_context_multiplier(event)
        recoverability = _RECOVERABILITY_MAP.get(error.error_category, 0.5)
        impact = self._compute_clinical_impact(event)

        weights = self._config.severity_weights
        final = (
            weights.get("base", 0.4) * base +
            weights.get("context", 0.3) * (base * context_mult) +
            weights.get("recoverability", 0.2) * (1.0 - recoverability) +
            weights.get("timing", 0.1) * impact
        )
        final = max(0.0, min(1.0, final))

        return ContextualSeverity(
            base_severity=base,
            context_multiplier=context_mult,
            recoverability=recoverability,
            clinical_impact=impact,
            final_severity=final,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_errors(
        self,
        events: List[ActivityEvent],
    ) -> List[Tuple[int, ClassifiedError]]:
        """Extract ClassifiedError for each event that contains an error."""
        result: List[Tuple[int, ClassifiedError]] = []
        for idx, event in enumerate(events):
            error = self._classify_single_event(event)
            if error is not None:
                result.append((idx, error))
        return result

    def _classify_single_event(self, event: ActivityEvent) -> Optional[ClassifiedError]:
        """Classify a single event using existing classify_error()."""
        raw = event.raw_event or {}
        response_text = raw.get("response_text")
        response_payload = None
        if isinstance(response_text, str):
            try:
                response_payload = json.loads(response_text)
            except (json.JSONDecodeError, TypeError):
                pass
        return classify_error(response_text, response_payload)

    def _build_chain_lookup(self, chains: List[ErrorChain]) -> Dict[int, str]:
        """Build event_index -> chain_id lookup."""
        lookup: Dict[int, str] = {}
        for chain in chains:
            for idx in chain.error_indices:
                lookup[idx] = chain.chain_id
        return lookup

    def _finalize_chain(
        self,
        chain_id: int,
        indices: List[int],
        indexed_errors: List[Tuple[int, ClassifiedError]],
        events: List[ActivityEvent],
        resource: Optional[str],
    ) -> ErrorChain:
        """Create ErrorChain from accumulated indices."""
        root_idx = indices[0]
        root_error = next(e for i, e in indexed_errors if i == root_idx)

        return ErrorChain(
            chain_id=f"chain_{chain_id:03d}",
            error_indices=list(indices),
            root_cause_index=root_idx,
            chain_length=len(indices),
            root_category=root_error.error_category,
            target_resource=resource,
        )

    def _extract_target_resource(self, event: ActivityEvent) -> Optional[str]:
        """Extract target resource identifier from event for chain grouping."""
        raw = event.raw_event or {}
        tool_call = raw.get("tool_call") or {}
        url = tool_call.get("url") or ""
        if not url:
            return None
        parsed = urlparse(url)
        path = parsed.path.strip("/")
        parts = path.split("/")
        for part in parts:
            if part.lower() not in ("fhir", "api", "v1", "v2", "r4", ""):
                return part
        return path or None

    def _compute_context_multiplier(self, event: ActivityEvent) -> float:
        """Urgency multiplier based on the type of action being attempted."""
        name = event.name.upper()
        if any(kw in name for kw in ("PRESCRIBE", "MEDICATION", "ADMINISTER")):
            return 1.8
        if any(kw in name for kw in ("PROCEDURE", "PERFORM", "ACTIVATE")):
            return 1.6
        if any(kw in name for kw in ("ORDER", "REQUEST")):
            return 1.3
        if any(kw in name for kw in ("QUERY", "OBSERVE", "GET")):
            return 1.0
        return 1.0

    def _compute_clinical_impact(self, event: ActivityEvent) -> float:
        """Estimate clinical impact of the failed action."""
        name = event.name.upper()
        if any(kw in name for kw in ("PRESCRIBE", "GIVE", "ADMINISTER")):
            return 0.9
        if any(kw in name for kw in ("PROCEDURE", "ACTIVATE")):
            return 0.8
        if any(kw in name for kw in ("ORDER_", "REQUEST")):
            return 0.6
        if any(kw in name for kw in ("DIAGNOSE", "CONDITION")):
            return 0.5
        return 0.3

    def _infer_clinical_context(self, event: ActivityEvent) -> Optional[str]:
        """Infer what the event was attempting for context annotation."""
        name = event.name.upper()
        if "PRESCRIBE" in name or "MEDICATION" in name:
            return "medication_management"
        if "ORDER" in name or "SERVICE" in name:
            return "diagnostic_ordering"
        if "QUERY" in name or "GET" in name:
            return "information_retrieval"
        if "PROCEDURE" in name:
            return "procedural_intervention"
        if "DIAGNOSE" in name:
            return "diagnostic_assessment"
        return None
