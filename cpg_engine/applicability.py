"""
ApplicabilityFilter: Clinical applicability checking beyond structural reachability.

Determines whether a CPG node's mandatory actions are clinically applicable
given the current patient state, not just structurally reachable via BFS.

MandatoryObligation: Enriched obligation with reachability metadata.
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set

from cga_bench.cpg_model.schemas.base import CPGGraph, PatientState

logger = logging.getLogger(__name__)


@dataclass
class MandatoryObligation:
    """Enriched mandatory action with applicability metadata."""

    action: str
    node: str
    depth: int
    reachability_type: str  # 'AF' (always-forward) | 'EF' (eventually-forward)
    severity: str  # from the node's associated harm severity


class ApplicabilityFilter:
    """Checks clinical applicability of CPG nodes beyond structural reachability."""

    @staticmethod
    def is_clinically_applicable(
        node_data: dict,
        state: Optional[PatientState] = None,
    ) -> bool:
        """Check if a CPG node's entry criteria are met by the patient state.

        Conservative: if conditions are unknown or state is None, returns True
        (applicable by default — avoids false negatives).

        Args:
            node_data: dict with optional 'entry_criteria' field.
            state: Current PatientState. If None, defaults to applicable.

        Returns:
            True if the node should be considered applicable.
        """
        if state is None:
            return True

        entry_criteria = node_data.get("entry_criteria", {})
        if not entry_criteria:
            return True

        # Check each criterion — any unknown criterion is conservatively treated as met
        for criterion_key, criterion_value in entry_criteria.items():
            if not _evaluate_criterion(criterion_key, criterion_value, state):
                logger.debug(
                    f"ApplicabilityFilter: node excluded — "
                    f"criterion '{criterion_key}' not met"
                )
                return False

        return True


def _evaluate_criterion(
    key: str, expected: any, state: PatientState
) -> bool:
    """Evaluate a single entry criterion against patient state.

    Supports:
    - vitals checks (e.g., 'sbp_below_90')
    - lab presence checks (e.g., 'has_lab_X')
    - age/sex checks

    Unknown criteria default to True (conservative).
    """
    key_lower = key.lower()

    # Vital sign thresholds
    if key_lower == "sbp_below" and state.vitals:
        sbp = state.vitals.blood_pressure_systolic
        return sbp < float(expected) if sbp is not None else True
    if key_lower == "sbp_above" and state.vitals:
        sbp = state.vitals.blood_pressure_systolic
        return sbp > float(expected) if sbp is not None else True
    if key_lower == "hr_above" and state.vitals:
        hr = state.vitals.heart_rate
        return hr > float(expected) if hr is not None else True
    if key_lower == "temperature_above" and state.vitals:
        temp = state.vitals.temperature
        return temp > float(expected) if temp is not None else True
    if key_lower == "spo2_below" and state.vitals:
        spo2 = state.vitals.oxygen_saturation
        return spo2 < float(expected) if spo2 is not None else True

    # Age check
    if key_lower == "age_above":
        return (state.age or 0) > int(expected)
    if key_lower == "age_below":
        return (state.age or 100) < int(expected)

    # Sex check
    if key_lower == "sex":
        return (state.sex or "").lower() == str(expected).lower()

    # Lab presence
    if key_lower.startswith("has_lab_"):
        lab_name = key_lower[len("has_lab_"):]
        return any(
            getattr(lr, "test_code", "").lower() == lab_name
            for lr in state.lab_results
        )

    # Unknown criterion — conservatively applicable
    return True
