"""
StateReducer: Action → PatientState 인과 연결

에이전트의 행동을 PatientState 필드 변경으로 매핑하여
CPGEngine._mandatory_completed()가 행동 수행을 인식할 수 있도록 한다.

CPGEngine._mandatory_completed() 키 생성 규칙 (engine.py:166-190):
  - state.lab_results → f"order_lab_{lab.test_code}"
  - state.medications_given → f"give_{med['medication_code']}"
  - state.procedures_done → 직접 문자열 사용

따라서 StateReducer의 역방향 매핑:
  - "order_lab_X" action → LabResult(test_code="X") 추가
  - "give_X" action → {"medication_code": "X"} 추가
  - 기타 모든 action → procedures_done에 직접 추가
"""

import logging
from typing import Optional

from cga_bench.cpg_model.schemas.base import Action, PatientState, LabResult

logger = logging.getLogger(__name__)


_NORMAL_LAB_DEFAULTS: dict[str, tuple[float, str]] = {
    "blood_culture": (0.0, ""),
    "lactate": (1.2, "mmol/L"),
    "blood_glucose": (100.0, "mg/dL"),
    "cbc": (14.0, "g/dL"),
    "bmp": (140.0, "mEq/L"),
    "cmp": (4.0, "mEq/L"),
    "troponin": (0.01, "ng/mL"),
    "bnp": (50.0, "pg/mL"),
    "creatinine": (1.0, "mg/dL"),
    "inr": (1.0, ""),
    "abg": (7.40, ""),
    "procalcitonin": (0.1, "ng/mL"),
    "d_dimer": (250.0, "ng/mL"),
    "hemoglobin": (14.0, "g/dL"),
    "platelet": (250.0, "×10³/µL"),
    "potassium": (4.0, "mEq/L"),
    "sodium": (140.0, "mEq/L"),
    "magnesium": (2.0, "mg/dL"),
    "calcium": (9.5, "mg/dL"),
    "phosphate": (3.5, "mg/dL"),
    "bilirubin": (0.8, "mg/dL"),
    "albumin": (4.0, "g/dL"),
    "ast": (25.0, "U/L"),
    "alt": (25.0, "U/L"),
    "lipase": (30.0, "U/L"),
    "tsh": (2.0, "mIU/L"),
    "hba1c": (5.5, "%"),
    "pt": (12.0, "sec"),
    "ptt": (30.0, "sec"),
    "fibrinogen": (300.0, "mg/dL"),
    "esr": (10.0, "mm/hr"),
    "crp": (3.0, "mg/L"),
    "wbc": (7.5, "×10³/µL"),
}


class StateReducer:
    """
    Action → PatientState 변환.

    CPGEngine._mandatory_completed()와 호환되는 키를 생성하여
    PatientState 필드를 채운다.

    Design principle: Only `order_lab_` and `give_` prefixed actions use
    structured fields (lab_results, medications_given). All other actions
    go to procedures_done as direct strings, because _mandatory_completed()
    uses the raw string for comparison (after normalization).
    """

    def apply(
        self,
        state: PatientState,
        action: Action,
        normalizer=None,
    ) -> PatientState:
        """
        Apply action to state, returning a new PatientState with updated fields.

        Args:
            state: Current patient state (not modified).
            action: The action performed.
            normalizer: Optional ActionNormalizer instance. If provided,
                normalizes action.action_id before mapping.

        Returns:
            New PatientState with action effects applied.
        """
        new_state = state.model_copy(deep=True)

        # Normalize action_id if normalizer provided
        action_id = action.action_id
        if normalizer:
            action_id = normalizer.normalize(action_id)

        action_id_lower = action_id.lower().strip()

        # Update timestamp
        new_state.time_since_arrival_minutes = action.timestamp_minutes

        # Route to appropriate PatientState field
        if action_id_lower.startswith("order_lab_"):
            self._apply_lab_order(new_state, action_id_lower, action)
        elif action_id_lower.startswith("give_"):
            self._apply_medication(new_state, action_id_lower, action)
        else:
            self._apply_procedure(new_state, action_id_lower)

        return new_state

    def _apply_lab_order(
        self, state: PatientState, action_id: str, action: Action
    ) -> None:
        """order_lab_X → lab_results with test_code="X".

        _mandatory_completed() reconstructs: f"order_lab_{lab.test_code}"
        """
        test_code = action_id[len("order_lab_"):]
        if not test_code:
            return

        # Avoid duplicates
        if any(
            getattr(lab, "test_code", "") == test_code
            for lab in state.lab_results
        ):
            return

        default_value, default_unit = _NORMAL_LAB_DEFAULTS.get(test_code, (0.0, ""))
        lab = LabResult(
            test_code=test_code,
            test_name=test_code.replace("_", " ").title(),
            value=default_value,
            unit=default_unit,
            timestamp_minutes=action.timestamp_minutes,
            is_abnormal=False,
        )
        state.lab_results.append(lab)
        logger.debug(f"StateReducer: lab_results += {test_code}")

    def _apply_medication(
        self, state: PatientState, action_id: str, action: Action
    ) -> None:
        """give_X → medications_given with medication_code="X".

        _mandatory_completed() reconstructs: f"give_{med['medication_code']}"
        """
        med_code = action_id[len("give_"):]
        if not med_code:
            return

        # Avoid duplicates
        if any(
            med.get("medication_code", "") == med_code
            for med in state.medications_given
        ):
            return

        state.medications_given.append({
            "medication_code": med_code,
            "timestamp_minutes": action.timestamp_minutes,
        })
        logger.debug(f"StateReducer: medications_given += {med_code}")

    def _apply_procedure(self, state: PatientState, action_id: str) -> None:
        """All other actions → procedures_done as direct string.

        _mandatory_completed() uses the raw string (after normalization).
        This covers: start_*, assess_*, obtain_*, initiate_*, perform_*,
        monitor_*, admit_*, determine_*, etc.
        """
        if action_id in state.procedures_done:
            return

        state.procedures_done.append(action_id)
        logger.debug(f"StateReducer: procedures_done += {action_id}")
