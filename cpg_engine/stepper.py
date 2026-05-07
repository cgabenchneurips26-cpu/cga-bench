"""CPGStepper: Step-by-step CPG graph walker wrapping CPGEngine.

Tracks node traversal history, issued/completed obligations,
and produces StepResult per action for audit trail.
"""

from dataclasses import dataclass
import logging

from cga_bench.cpg_engine.engine import CPGEngine
from cga_bench.cpg_model.schemas.base import Action, PatientState

logger = logging.getLogger(__name__)


@dataclass
class StepResult:
    """Result of a single CPGStepper step."""

    advanced: bool
    new_node: str | None
    new_obligations: list[str]
    completed_obligations: list[str]
    violations: list[dict]


class CPGStepper:
    """Wraps CPGEngine with step-by-step tracking.

    Maintains:
    - node_history: ordered list of visited nodes
    - issued_obligations: all mandatory actions ever issued
    - completed_obligations: mandatory actions completed so far
    """

    def __init__(self, engine: CPGEngine) -> None:
        self.engine = engine
        self.node_history: list[str] = [engine.current_node_id]
        self.issued_obligations: set[str] = set()
        self.completed_obligations: set[str] = set()

    @property
    def current_node(self) -> str:
        return self.engine.current_node_id

    @property
    def progress_rate(self) -> float:
        """Fraction of issued obligations completed."""
        if not self.issued_obligations:
            return 1.0
        return len(self.completed_obligations) / len(self.issued_obligations)

    def step(self, state: PatientState, action: Action) -> StepResult:
        """Execute one step: evaluate CPG, detect node advance, track obligations.

        Args:
            state: Current PatientState (after StateReducer applied the action).
            action: The action just performed.

        Returns:
            StepResult with advance status, new obligations, completed obligations,
            and any violations detected.
        """
        old_node = self.engine.current_node_id

        # Evaluate CPG engine with updated state
        cpg_output = self.engine.evaluate(state)

        # Track mandatory obligations
        new_obligations = []
        for m in cpg_output.mandatory_actions:
            if m not in self.issued_obligations:
                self.issued_obligations.add(m)
                new_obligations.append(m)

        # Check if this action completes any obligation
        # B3 fix: normalize action_id symmetrically with engine forbidden/mandatory sets
        # (engine post-processes forbidden via _normalize_action_key). Without this,
        # action.action_id.lower() differs from the canonical form stored in
        # cpg_output.forbidden_actions and the COMMISSION check below silently misses.
        completed = []
        action_id = self.engine._normalize_action_key(action.action_id)
        for obligation in self.issued_obligations:
            if obligation not in self.completed_obligations:
                if self._action_satisfies(action_id, obligation):
                    self.completed_obligations.add(obligation)
                    completed.append(obligation)

        # Try to advance node
        advanced = False
        new_node = None
        try:
            self.engine.advance_node(state, action)
            if self.engine.current_node_id != old_node:
                advanced = True
                new_node = self.engine.current_node_id
                self.node_history.append(new_node)
        except Exception as e:
            logger.debug(f"CPGStepper: advance_node failed: {e}")

        # Detect violations from forbidden actions.
        # B3 fix: cpg_output.forbidden_actions is now pre-normalized by the engine
        # and action_id was normalized above (symmetric set-membership).
        violations = []
        if action_id in cpg_output.forbidden_actions:
            violations.append(
                {
                    "type": "COMMISSION",
                    "action": action_id,
                    "node": old_node,
                    "timestamp": action.timestamp_minutes,
                }
            )

        logger.debug(
            f"CPGStepper: node={old_node}→{new_node or old_node}, "
            f"advanced={advanced}, new_oblig={len(new_obligations)}, "
            f"completed={len(completed)}, violations={len(violations)}"
        )

        return StepResult(
            advanced=advanced,
            new_node=new_node,
            new_obligations=new_obligations,
            completed_obligations=completed,
            violations=violations,
        )

    @staticmethod
    def _action_satisfies(action_id: str, obligation: str) -> bool:
        """Check if an action satisfies an obligation.

        Supports exact match and conditional pattern matching
        (e.g., 'start_norepinephrine' satisfies 'start_vasopressor_if_hypotensive').
        """
        obligation_lower = obligation.lower().strip()
        if action_id == obligation_lower:
            return True

        # Handle conditional patterns: "X_if_Y" matches "X" or specific variants
        if "_if_" in obligation_lower:
            base = obligation_lower.split("_if_")[0]
            if action_id.startswith(base):
                return True

        return False
