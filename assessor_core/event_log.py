"""
EventLog: Append-only, immutable event sourcing for clinical actions.

ActionEvent is a frozen dataclass representing a single clinical action.
EventLog provides:
  - append(): Add events during evaluation
  - freeze(): Lock the log against further modifications
  - replay(): Re-apply events via StateReducer for determinism verification

CompletedActions: Index categorizing completed actions by type.
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, List, Set, Tuple

from cga_bench.cpg_model.schemas.base import Action, ActionType, PatientState

logger = logging.getLogger(__name__)


def normalize_timestamp(value: float, unit: str = "seconds") -> float:
    """Convert relative time to epoch seconds (internal standard).

    Args:
        value: Time value.
        unit: "seconds" or "minutes"

    Returns:
        Time in seconds.
    """
    if unit == "minutes":
        return value * 60.0
    return value


@dataclass(frozen=True)
class ActionEvent:
    """Immutable record of a single clinical action."""

    step: int
    raw_action: str
    canonical_key: str
    timestamp: float
    source_benchmark: str
    metadata: Dict = field(default_factory=dict)


@dataclass
class CompletedActions:
    """Index of completed actions by clinical category."""

    ordered: Set[str] = field(default_factory=set)       # lab orders
    administered: Set[str] = field(default_factory=set)  # medications
    performed: Set[str] = field(default_factory=set)     # procedures
    resulted: Set[str] = field(default_factory=set)      # results received

    @property
    def all_keys(self) -> Set[str]:
        """Union of all completed action keys."""
        return self.ordered | self.administered | self.performed | self.resulted


class EventLog:
    """Append-only, freezable log of ActionEvents.

    After freeze(), no further events can be appended.
    Supports replay for determinism verification.
    """

    def __init__(self) -> None:
        self._events: List[ActionEvent] = []
        self._frozen: bool = False
        self._completed: CompletedActions = CompletedActions()

    def append(self, event: ActionEvent) -> None:
        """Add an event to the log.

        Raises:
            RuntimeError: If the log has been frozen.
        """
        if self._frozen:
            raise RuntimeError("EventLog is frozen; cannot append")
        self._events.append(event)
        self._classify_event(event)

    def _classify_event(self, event: ActionEvent) -> None:
        """Classify an event into CompletedActions categories."""
        key = event.canonical_key.lower()
        if key.startswith("order_lab_") or key.startswith("order_imaging_"):
            self._completed.ordered.add(key)
        elif key.startswith("give_") or key.startswith("administer_"):
            self._completed.administered.add(key)
        elif key.startswith("result_") or key.startswith("receive_result_"):
            self._completed.resulted.add(key)
        else:
            self._completed.performed.add(key)

    def freeze(self) -> None:
        """Lock the log against further modifications."""
        self._frozen = True
        logger.debug(f"EventLog frozen with {len(self._events)} events")

    @property
    def frozen(self) -> bool:
        return self._frozen

    @property
    def events(self) -> Tuple[ActionEvent, ...]:
        """Return events as an immutable tuple."""
        return tuple(self._events)

    @property
    def sorted_events(self) -> tuple[ActionEvent, ...]:
        """Return events sorted by timestamp (stable sort)."""
        return tuple(sorted(self._events, key=lambda e: e.timestamp))

    @property
    def completed(self) -> CompletedActions:
        """Return the completed actions index."""
        return self._completed

    def __len__(self) -> int:
        return len(self._events)

    def replay(
        self,
        reducer,
        initial_state: PatientState,
        normalizer=None,
    ) -> PatientState:
        """Replay all events through the StateReducer.

        Args:
            reducer: StateReducer instance.
            initial_state: Starting PatientState (not modified).
            normalizer: Optional ActionNormalizer.

        Returns:
            Final PatientState after replaying all events.
        """
        state = initial_state.model_copy(deep=True)
        for event in self._events:
            action = Action(
                type=ActionType.PROCEDURE,
                action_id=event.canonical_key,
                args={},
                timestamp_minutes=event.timestamp,
            )
            state = reducer.apply(state, action, normalizer=normalizer)
        return state
