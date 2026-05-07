"""
Clinical Scenario Environment
시간 흐름, 부분 관측, 행동 부작용을 포함한 시뮬레이션 환경
"""
from typing import Dict, List, Optional, Tuple, Any, Set
from dataclasses import dataclass, field
from copy import deepcopy
import random
import logging
from abc import ABC

from cga_bench.cpg_model.schemas.base import (
    PatientState, VitalSigns, LabResult, Action, ActionType
)

logger = logging.getLogger(__name__)

# VitalSigns 모델에 정의된 유효한 속성들
VALID_VITAL_SIGNS: Set[str] = {
    'heart_rate',
    'blood_pressure_systolic',
    'blood_pressure_diastolic',
    'respiratory_rate',
    'temperature',
    'oxygen_saturation',
    'map_mmhg'
}

@dataclass
class MedicationEffectConfig:
    """약물 효과 설정 - 외부에서 주입"""
    medication_pattern: str  # 약물 코드 패턴 (예: "norepinephrine")
    target_vital: str  # 영향 받는 바이탈 (예: "map_mmhg")
    effect_min: float  # 최소 효과
    effect_max: float  # 최대 효과

@dataclass
class DeteriorationConfig:
    """상태 악화 설정 - 외부에서 주입"""
    vital: str  # 바이탈 이름
    rate_min: float  # 최소 변화율
    rate_max: float  # 최대 변화율
    direction: str  # "increase" or "decrease"

@dataclass
class TerminationConfig:
    """종료 조건 설정 - 외부에서 주입"""
    vital: str  # 바이탈 이름
    threshold: float  # 임계값
    condition: str  # "less_than" or "greater_than"
    reason: str  # 종료 사유

@dataclass
class LabThreshold:
    """검사 결과 정상 범위 - 외부에서 주입"""
    test_code: str
    low: float
    high: float

@dataclass
class EnvironmentConfig:
    """환경 설정 - 모든 값은 외부에서 명시적으로 주입"""
    max_duration_minutes: int
    time_step_minutes: float
    lab_result_delay_minutes: float
    imaging_result_delay_minutes: float
    enable_state_deterioration: bool
    medication_effects: List[MedicationEffectConfig] = field(default_factory=list)
    deterioration_rules: List[DeteriorationConfig] = field(default_factory=list)
    termination_conditions: List[TerminationConfig] = field(default_factory=list)
    lab_thresholds: List[LabThreshold] = field(default_factory=list)
    random_seed: Optional[int] = None
    cds_assistance: bool = False  # Gate 4: when False, mandatory_actions hidden from agent

@dataclass
class Observation:
    """에이전트에게 제공되는 관측"""
    timestamp_minutes: float
    visible_state: Dict[str, Any]
    new_results: List[Dict[str, Any]]
    alerts: List[str]
    available_actions: List[str]
    mandatory_actions: List[str] = field(default_factory=list)  # P1 Fix: CPG에서 동적 로드

class ClinicalEnvironment:
    """
    임상 시뮬레이션 환경

    특징:
    - 시간의 흐름 (검사 결과 지연, 상태 변화)
    - 부분 관측 (숨겨진 정보는 검사로만 확인)
    - 행동의 부작용 (약물/수액이 상태를 바꿈)
    - 종료 조건 (안전한 disposition 또는 중대 이벤트)
    """

    def __init__(
        self,
        initial_state: PatientState,
        config: EnvironmentConfig,
        ground_truth: Dict[str, Any],
        cpg_available_actions: Optional[List[str]] = None,
        cpg_mandatory_actions: Optional[List[str]] = None,
        cpg_engine=None,
    ):
        """
        Args:
            initial_state: 초기 환자 상태
            config: 환경 설정 (필수 - 모든 설정은 외부에서 명시적으로 주입)
            ground_truth: 검사 결과 등의 실제 값 (필수 - mock 없음)
        """
        if config is None:
            raise ValueError("config is required - no default configuration")
        if ground_truth is None:
            raise ValueError("ground_truth is required - no mock simulation")

        self.config = config
        self.initial_state = deepcopy(initial_state)
        self.current_state = deepcopy(initial_state)
        self.ground_truth = ground_truth

        # CPG-derived actions (override hardcoded lists when provided)
        self._cpg_available_actions: Optional[List[str]] = cpg_available_actions
        self._cpg_mandatory_actions: Optional[List[str]] = cpg_mandatory_actions
        self._cpg_engine = cpg_engine  # CPG engine for dynamic state progression
        self._action_effects_registry = self._load_action_effects()

        # 대기 중인 결과 (지연 시뮬레이션)
        self.pending_results: List[Tuple[float, Dict]] = []

        # 이벤트 로그
        self.action_history: List[Action] = []
        self.state_history: List[PatientState] = [deepcopy(initial_state)]
        self.observation_history: List[Observation] = []

        # 상태
        self.current_time = 0.0
        self.terminated = False
        self.termination_reason: Optional[str] = None

        if self.config.random_seed:
            random.seed(self.config.random_seed)

    def reset(self) -> Observation:
        """환경 리셋"""
        self.current_state = deepcopy(self.initial_state)
        self.pending_results = []
        self.action_history = []
        self.state_history = [deepcopy(self.initial_state)]
        self.observation_history = []
        self.current_time = 0.0
        self.terminated = False
        self.termination_reason = None

        # Reset CPG engine to entry node
        if self._cpg_engine is not None:
            self._cpg_engine.reset()

        return self._get_observation()

    def step(self, action: Action) -> Tuple[Observation, float, bool, Dict]:
        """
        행동 수행 및 환경 업데이트

        Returns:
            observation: 새로운 관측
            reward: 보상 (CGA-Bench에서는 사용 안함)
            done: 종료 여부
            info: 추가 정보
        """
        if self.terminated:
            raise ValueError("Environment is terminated. Call reset().")

        # 시간 업데이트
        action.timestamp_minutes = self.current_time
        self.current_time += self.config.time_step_minutes
        self.current_state.time_since_arrival_minutes = self.current_time

        # 행동 처리
        self._process_action(action)
        self.action_history.append(action)

        # Advance CPG engine node after action processing
        if self._cpg_engine is not None:
            try:
                self._cpg_engine.advance_node(self.current_state, action)
            except Exception:
                pass

        # 대기 결과 확인 및 상태 업데이트
        self._process_pending_results()

        # 상태 악화/호전 (선택적)
        if self.config.enable_state_deterioration:
            self._update_patient_condition()

        # 종료 조건 체크
        self._check_termination()

        # 상태 기록
        self.state_history.append(deepcopy(self.current_state))

        # 관측 생성
        obs = self._get_observation()
        self.observation_history.append(obs)

        info = {
            "current_time": self.current_time,
            "pending_results_count": len(self.pending_results),
        }

        return obs, 0.0, self.terminated, info

    def _normalize_action_args(self, action: Action) -> Action:
        """액션 파라미터 정규화 - Decision Table과 환경 간 키 불일치 해결"""
        args = dict(action.args) if action.args else {}
        action_id = action.action_id or ""

        # ORDER_LAB: test → test_code (no fallback from action_id)
        if action.type == ActionType.ORDER_LAB:
            if "test_code" not in args:
                for alt_key in ["test", "lab_code", "lab_test"]:
                    if alt_key in args:
                        args["test_code"] = args.pop(alt_key)
                        break
                # No fallback - let _process_action raise ValueError

        # ORDER_IMAGING: diagnostic_type → imaging_type (no fallback from action_id)
        elif action.type == ActionType.ORDER_IMAGING:
            if "imaging_type" not in args:
                for alt_key in ["diagnostic_type", "imaging", "study_type"]:
                    if alt_key in args:
                        args["imaging_type"] = args.pop(alt_key)
                        break
                # No fallback - let _process_action raise ValueError

        # GIVE_MEDICATION: medication_class → medication_code (no fallback)
        elif action.type == ActionType.GIVE_MEDICATION:
            if "medication_code" not in args:
                for alt_key in ["medication_class", "medication", "med", "drug", "medications"]:
                    if alt_key in args:
                        val = args.pop(alt_key)
                        # medications 리스트인 경우 첫 번째 항목 사용
                        if isinstance(val, list):
                            if not val:
                                raise ValueError("GIVE_MEDICATION: 'medications' list cannot be empty")
                            args["medication_code"] = val[0]
                        else:
                            args["medication_code"] = val
                        break
                # No fallback - let _process_action raise ValueError
            # No default for dose - let _process_action raise ValueError

        # PROCEDURE: procedure → procedure_code (no fallback from action_id)
        elif action.type == ActionType.PROCEDURE:
            if "procedure_code" not in args:
                for alt_key in ["procedure", "procedure_type"]:
                    if alt_key in args:
                        args["procedure_code"] = args.pop(alt_key)
                        break
                # No fallback - let _process_action raise ValueError

        # DISPOSITION: no default - let _process_action raise ValueError
        elif action.type == ActionType.DISPOSITION:
            pass  # No default for disposition

        # 새 Action 반환 (불변성 유지)
        return Action(
            type=action.type,
            action_id=action.action_id,
            args=args,
            timestamp_minutes=action.timestamp_minutes,
            justification=action.justification
        )

    @staticmethod
    def _load_action_effects() -> dict:
        """Load action effects registry for data-driven state updates."""
        import yaml as _yaml
        import pathlib
        _path = pathlib.Path(__file__).parent.parent / "assessor_core" / "action_effects.yaml"
        if _path.exists():
            with open(_path) as _f:
                return _yaml.safe_load(_f) or {}
        return {}

    def _process_action(self, action: Action):
        """행동 처리 및 부작용 적용"""
        # 파라미터 정규화
        action = self._normalize_action_args(action)

        if action.type == ActionType.ORDER_LAB:
            # 검사 오더 -> 대기 결과 추가
            if "test_code" not in action.args:
                raise ValueError("ORDER_LAB action requires 'test_code' in args")
            test_code = action.args["test_code"]
            result_time = self.current_time + self.config.lab_result_delay_minutes

            # Ground truth에서 결과 가져오기, 없으면 기본값 사용
            lab_key = f"lab_{test_code}"
            if lab_key in self.ground_truth:
                result_value = self.ground_truth[lab_key]
            else:
                logger.warning(f"No ground truth for {lab_key}, using default 'pending' value")
                result_value = "pending"

            self.pending_results.append((result_time, {
                "type": "lab",
                "test_code": test_code,
                "value": result_value,
                "ordered_at": self.current_time,
            }))
            self.current_state.pending_orders.append(f"lab_{test_code}")

        elif action.type == ActionType.ORDER_IMAGING:
            if "imaging_type" not in action.args:
                raise ValueError("ORDER_IMAGING action requires 'imaging_type' in args")
            imaging_type = action.args["imaging_type"]
            result_time = self.current_time + self.config.imaging_result_delay_minutes

            # Ground truth에서 결과 가져오기, 없으면 기본값 사용
            imaging_key = f"imaging_{imaging_type}"
            if imaging_key in self.ground_truth:
                result = self.ground_truth[imaging_key]
            else:
                logger.warning(f"No ground truth for {imaging_key}, using default 'unremarkable' value")
                result = "unremarkable"

            self.pending_results.append((result_time, {
                "type": "imaging",
                "imaging_type": imaging_type,
                "result": result,
                "ordered_at": self.current_time,
            }))
            self.current_state.pending_orders.append(f"imaging_{imaging_type}")

        elif action.type == ActionType.GIVE_MEDICATION:
            if "medication_code" not in action.args:
                raise ValueError("GIVE_MEDICATION action requires 'medication_code' in args")
            if "dose" not in action.args:
                raise ValueError("GIVE_MEDICATION action requires 'dose' in args")
            med_code = action.args["medication_code"]
            dose = action.args["dose"]

            self.current_state.medications_given.append({
                "medication_code": med_code,
                "dose": dose,
                "given_at": self.current_time,
            })

            # 약물 효과 적용
            self._apply_medication_effect(med_code, dose)

        elif action.type == ActionType.DISPOSITION:
            disposition = action.args.get("disposition", action.action_id)
            self.current_state.disposition_status = disposition

        elif action.type == ActionType.PROCEDURE:
            procedure = action.args.get("procedure_code", action.action_id)
            self.current_state.procedures_done.append(procedure)

        elif action.type in (
            ActionType.PHYSICAL_EXAM,
            ActionType.REASSESS,
            ActionType.CONSULT,
            ActionType.ESCALATE,
            ActionType.ASK_QUESTION,
            ActionType.WRITE_NOTE,
        ):
            self.current_state.procedures_done.append(action.action_id)

        else:
            # Data-driven fallback using action_effects registry
            effect = self._action_effects_registry.get(action.action_id, {})
            etype = effect.get("effect_type", "procedure") if isinstance(effect, dict) else "procedure"
            if etype == "medication":
                self.current_state.medications_given.append({
                    "medication": action.action_id,
                    "dose": args.get("dose", "standard"),
                    "route": args.get("route", "IV"),
                    "timestamp": action.timestamp_minutes,
                })
            else:
                self.current_state.procedures_done.append(action.action_id)

    def _process_pending_results(self):
        """대기 중인 결과 처리"""
        ready_results = []
        still_pending = []

        for result_time, result in self.pending_results:
            if self.current_time >= result_time:
                ready_results.append(result)
            else:
                still_pending.append((result_time, result))

        self.pending_results = still_pending

        # 결과를 상태에 추가
        for result in ready_results:
            if result["type"] == "lab":
                self.current_state.lab_results.append(LabResult(
                    test_code=result["test_code"],
                    test_name=result["test_code"],
                    value=result["value"],
                    unit="",
                    timestamp_minutes=self.current_time,
                    is_abnormal=self._is_abnormal(result["test_code"], result["value"]),
                ))
                # pending에서 제거
                order_key = f"lab_{result['test_code']}"
                if order_key in self.current_state.pending_orders:
                    self.current_state.pending_orders.remove(order_key)

            elif result["type"] == "imaging":
                self.current_state.imaging_results.append(result)
                order_key = f"imaging_{result['imaging_type']}"
                if order_key in self.current_state.pending_orders:
                    self.current_state.pending_orders.remove(order_key)

    def _validate_vital_sign(self, vital_name: str, context: str) -> bool:
        """
        바이탈 사인 이름 유효성 검증

        Args:
            vital_name: 검증할 바이탈 사인 이름
            context: 오류 메시지에 사용할 컨텍스트 정보

        Returns:
            유효하면 True

        Raises:
            ValueError: 유효하지 않은 바이탈 사인 이름
        """
        if vital_name not in VALID_VITAL_SIGNS:
            raise ValueError(
                f"Invalid vital sign '{vital_name}' in {context}. "
                f"Valid vital signs are: {sorted(VALID_VITAL_SIGNS)}"
            )
        return True

    def _apply_medication_effect(self, med_code: str, dose: str):
        """약물 효과 적용 - 설정에 정의된 효과만 적용"""
        for effect in self.config.medication_effects:
            if effect.medication_pattern.lower() in med_code.lower():
                # 바이탈 사인 이름 유효성 검증
                self._validate_vital_sign(
                    effect.target_vital,
                    f"medication_effects (medication_pattern: {effect.medication_pattern})"
                )

                vital_value = getattr(self.current_state.vitals, effect.target_vital, None)
                if vital_value is not None:
                    change = random.uniform(effect.effect_min, effect.effect_max)
                    setattr(
                        self.current_state.vitals,
                        effect.target_vital,
                        vital_value + change
                    )

    def _update_patient_condition(self):
        """시간에 따른 환자 상태 변화 - 설정에 정의된 악화 규칙만 적용"""
        # 치료 없이 시간이 지나면 악화
        if not self.current_state.medications_given:
            for rule in self.config.deterioration_rules:
                # 바이탈 사인 이름 유효성 검증
                self._validate_vital_sign(
                    rule.vital,
                    f"deterioration_rules (direction: {rule.direction})"
                )

                vital_value = getattr(self.current_state.vitals, rule.vital, None)
                if vital_value is not None:
                    change = random.uniform(rule.rate_min, rule.rate_max)
                    if rule.direction == "decrease":
                        change = -change
                    setattr(
                        self.current_state.vitals,
                        rule.vital,
                        vital_value + change
                    )

    def _check_termination(self):
        """종료 조건 체크 - 설정에 정의된 조건만 적용"""
        # 시간 초과
        if self.current_time >= self.config.max_duration_minutes:
            self.terminated = True
            self.termination_reason = "timeout"
            return

        # Disposition 결정됨
        if self.current_state.disposition_status:
            self.terminated = True
            self.termination_reason = "disposition_decided"
            return

        # 설정된 종료 조건 체크
        for condition in self.config.termination_conditions:
            # 바이탈 사인 이름 유효성 검증
            self._validate_vital_sign(
                condition.vital,
                f"termination_conditions (reason: {condition.reason})"
            )

            vital_value = getattr(self.current_state.vitals, condition.vital, None)
            if vital_value is not None:
                should_terminate = False
                if condition.condition == "less_than" and vital_value < condition.threshold:
                    should_terminate = True
                elif condition.condition == "greater_than" and vital_value > condition.threshold:
                    should_terminate = True

                if should_terminate:
                    self.terminated = True
                    self.termination_reason = condition.reason
                    return

    def _get_observation(self) -> Observation:
        """현재 상태에서 관측 생성"""
        # 에이전트가 볼 수 있는 정보만 포함
        visible_state = {
            "time_since_arrival_minutes": self.current_state.time_since_arrival_minutes,
            "age": self.current_state.age,
            "sex": self.current_state.sex,
            "vitals": self.current_state.vitals.model_dump(),
            "chief_complaint": self.current_state.chief_complaint,
            "working_diagnosis": self.current_state.working_diagnosis,
            "lab_results": [lab.model_dump() for lab in self.current_state.lab_results],
            "medications_given": self.current_state.medications_given,
            "procedures_done": self.current_state.procedures_done,
            "pending_orders": self.current_state.pending_orders,
            "allergies": self.current_state.allergies,
            "comorbidities": self.current_state.comorbidities,
        }

        # 새로 도착한 결과
        new_results: List[Dict[str, Any]] = []

        # 알림 생성
        alerts = self._generate_alerts()

        mandatory: List[str] = (
            self._get_mandatory_actions() if self.config.cds_assistance else []
        )
        return Observation(
            timestamp_minutes=self.current_time,
            visible_state=visible_state,
            new_results=new_results,
            alerts=alerts,
            available_actions=self._get_available_actions(),
            mandatory_actions=mandatory,
        )

    def _generate_alerts(self) -> List[str]:
        """상태 기반 알림 생성"""
        alerts = []

        vitals = self.current_state.vitals

        if vitals.map_mmhg and vitals.map_mmhg < 65:
            alerts.append("ALERT: Hypotension (MAP < 65 mmHg)")

        if vitals.heart_rate and vitals.heart_rate > 120:
            alerts.append("ALERT: Tachycardia (HR > 120 bpm)")

        if vitals.temperature and vitals.temperature > 38.3:
            alerts.append("ALERT: Fever (Temp > 38.3°C)")

        if vitals.oxygen_saturation and vitals.oxygen_saturation < 92:
            alerts.append("ALERT: Hypoxemia (SpO2 < 92%)")

        return alerts

    def _get_available_actions(self) -> List[str]:
        # If CPG-derived actions are provided, use them ONLY as fallback
        # when the hardcoded domain-specific list is not available.
        # This preserves existing domain behavior while supporting new domains.
        # (CPG override deferred to after hardcoded attempt below)

        """
        현재 환자 상태와 완료된 action 기반으로 사용 가능한 구체적 action 목록 반환

        Returns:
            구체적 action_id 목록 (예: "order_lab_lactate", "give_broad_spectrum_antibiotics")
        """
        completed_action_ids = {a.action_id for a in self.action_history}
        diagnosis = (self.current_state.working_diagnosis or "").lower()

        available = []

        # ============================================================
        # Sepsis / Septic Shock - SSC Hour-1 Bundle
        # Action IDs aligned with cpg_model/graphs/ssc_sepsis_hour1.yaml
        # ============================================================
        if any(kw in diagnosis for kw in ["sepsis", "septic", "infection"]):
            sepsis_actions = [
                # Assessment (from initial_recognition node)
                "assess_infection_source",
                "assess_organ_dysfunction",
                "assess_vital_signs",
                # Labs - Hour-1 Bundle (from septic_shock_bundle node)
                "order_lab_lactate",
                "order_lab_blood_culture",
                "order_lab_cbc",
                "order_lab_bmp",
                "order_lab_coagulation",
                "order_lab_procalcitonin",
                # Treatment - Hour-1 Bundle
                "give_broad_spectrum_antibiotics",
                "give_crystalloid_30ml_kg",
                "give_crystalloid_fluid",
                "start_vasopressor_norepinephrine",
                "start_vasopressor_vasopressin",
                # Imaging and Procedures
                "order_imaging_chest_xray",
                "place_central_line",
                "place_arterial_line",
                # Reassessment (exact CPG action IDs)
                "reassess_perfusion",
                "remeasure_lactate_if_elevated",
            ]
            available.extend([a for a in sepsis_actions if a not in completed_action_ids])

        # ============================================================
        # STEMI / ACS - Chest Pain Guidelines
        # Action IDs aligned with cpg_model/graphs/aha_chest_pain.yaml
        # ============================================================
        if any(kw in diagnosis for kw in ["stemi", "nstemi", "acs", "chest_pain", "mi", "infarction"]):
            acs_actions = [
                # Initial Assessment (from initial_assessment node)
                "obtain_12_lead_ecg",
                "assess_vital_signs",
                "obtain_chest_pain_history",
                "establish_iv_access",
                "order_lab_troponin",
                "administer_oxygen_if_hypoxic",
                # ECG interpretation
                "interpret_ecg",
                "obtain_prior_ecg_comparison",
                "request_cardiology_consult",
                # STEMI Pathway (from stemi_pathway node)
                "activate_cath_lab",
                "give_aspirin_loading",
                "give_p2y12_inhibitor",
                "give_anticoagulation",
                "give_nitrates_if_indicated",  # Not for RV infarct
                "give_morphine_if_needed",
                "give_beta_blocker_if_stable",
                "arrange_pci",
                "consider_fibrinolysis_if_pci_delayed",
                # RV infarct specific
                "obtain_right_sided_ecg_v4r",
                "give_crystalloid_30ml_kg",
                "give_crystalloid_fluid",
            ]
            available.extend([a for a in acs_actions if a not in completed_action_ids])

            # Contraindication check: No nitrates for RV infarction
            if self._has_rv_involvement():
                available = [a for a in available if a != "give_nitrates_if_indicated"]

        # ============================================================
        # DKA - Diabetic Ketoacidosis
        # ============================================================
        if any(kw in diagnosis for kw in ["dka", "ketoacidosis", "diabetic"]):
            dka_actions = [
                # Assessment
                "assess_mental_status",
                "assess_hydration_status",
                # Labs
                "order_lab_glucose",
                "order_lab_bmp",
                "order_lab_ketones",
                "order_lab_blood_gas",
                "order_lab_anion_gap",
                # Treatment - Sequence matters!
                "give_iv_fluid_bolus",
                "give_potassium_replacement",  # MUST check K+ before insulin
                "start_insulin_infusion",
                "give_bicarbonate_if_severe",
                # Monitoring
                "monitor_glucose_hourly",
                "monitor_potassium",
                "reassess_anion_gap",
            ]
            available.extend([a for a in dka_actions if a not in completed_action_ids])

        # ============================================================
        # AKI - Acute Kidney Injury
        # ============================================================
        if any(kw in diagnosis for kw in ["aki", "renal", "kidney", "contrast_aki", "nephro"]):
            aki_actions = [
                # Assessment
                "assess_vital_signs",
                "assess_volume_status",
                "assess_hydration_status",
                "assess_aki_risk_factors",
                "review_nephrotoxic_medications",
                "check_current_medications",
                "check_baseline_egfr",
                "review_risk_factors",
                "review_recent_contrast_exposure",
                # Labs
                "order_creatinine",
                "order_lab_creatinine",
                "order_lab_bmp",
                "order_lab_cbc",
                "order_lab_blood_gas",
                "order_lab_urinalysis",
                "order_urinalysis",
                "order_lab_urine_culture",
                "order_lab_urine_electrolytes",
                "order_lab_lactate",
                "order_lab_coagulation",
                "order_lab_fena",
                "order_cystatin_c",
                "monitor_urine_output",
                "monitor_potassium",
                # Imaging
                "order_renal_ultrasound",
                "order_imaging_renal_ultrasound",
                "order_imaging_chest_xray",
                # Treatment
                "give_crystalloid_fluid",
                "start_iv_hydration",
                "discontinue_nephrotoxic_agents",
                "discontinue_nephrotoxins",
                "optimize_fluid_status",
                "use_low_osmolar_contrast",
                "calculate_contrast_volume_limit",
                # Consult
                "consult_nephrology",
                "request_consultation",
            ]
            available.extend([a for a in aki_actions if a not in completed_action_ids])

        # ============================================================
        # Heart Failure
        # ============================================================
        if any(kw in diagnosis for kw in ["heart_failure", "hf", "chf", "cardiogenic"]):
            hf_actions = [
                # Assessment
                "assess_volume_status",
                "assess_perfusion_status",
                # Labs
                "order_lab_bnp",
                "order_lab_troponin",
                "order_lab_bmp",
                # Imaging
                "order_imaging_cxr",
                "order_imaging_echo",
                # Treatment
                "give_iv_diuretic",
                "give_vasodilator",
                "start_inotrope_if_cardiogenic",
                "consult_cardiology",
            ]
            available.extend([a for a in hf_actions if a not in completed_action_ids])

        # ============================================================
        # Stroke
        # ============================================================
        if any(kw in diagnosis for kw in ["stroke", "cva", "tia"]):
            stroke_actions = [
                # Assessment
                "calculate_nihss_score",
                "determine_last_known_well",
                # Imaging
                "order_imaging_ct_head",
                "order_imaging_cta",
                "order_imaging_mri_dwi",
                # Labs
                "order_lab_glucose",
                "order_lab_coagulation",
                "order_lab_cbc",
                # Treatment
                "give_tpa_if_eligible",
                "activate_stroke_team",
                "consult_neurology",
                "arrange_thrombectomy",
            ]
            available.extend([a for a in stroke_actions if a not in completed_action_ids])

        # ============================================================
        # CPG engine dynamic actions (for all domains with graph)
        if not available and self._cpg_engine is not None:
            completed_action_ids = {a.action_id for a in self.action_history}
            # Repeatable actions (assessment, monitoring) should not be excluded
            repeatable_prefixes = ("assess_", "reassess_", "monitor_", "check_", "evaluate_", "measure_")
            return [
                a for a in sorted(self._cpg_engine.global_allowed_actions)
                if a not in completed_action_ids or a.startswith(repeatable_prefixes)
            ]

        # CPG static fallback (for domains without engine)
        if not available and self._cpg_available_actions:
            completed_action_ids = {a.action_id for a in self.action_history}
            return [a for a in self._cpg_available_actions if a not in completed_action_ids]

        # Default generic actions if no specific diagnosis
        # Note: These should be commonly allowed across multiple CPG graphs
        # ============================================================
        if not available:
            generic_actions = [
                "assess_vital_signs",
                "order_lab_cbc",
                "order_lab_bmp",
                "order_imaging_chest_xray",  # Aligned with CPG naming
            ]
            available.extend([a for a in generic_actions if a not in completed_action_ids])

        # Remove duplicates while preserving order
        seen = set()
        unique_available = []
        for action in available:
            if action not in seen:
                seen.add(action)
                unique_available.append(action)

        return unique_available

    def _get_mandatory_actions(self) -> List[str]:
        # CPG engine dynamic mandatory (current node's mandatory actions)
        if self._cpg_engine is not None:
            try:
                output = self._cpg_engine.evaluate(self.current_state)
                completed_action_ids = {a.action_id for a in self.action_history}
                cpg_mandatory = [a for a in sorted(output.mandatory_actions) if a not in completed_action_ids]
                if cpg_mandatory:
                    return cpg_mandatory
            except Exception:
                pass  # Fall through to hardcoded
        # CPG-derived mandatory deferred to after hardcoded attempt

        """
        현재 환자 진단 기반으로 mandatory actions 반환

        P1 Fix: RAG Agent의 hardcoded mandatory patterns 대신 환경에서 동적으로 제공
        이 목록은 CPG 그래프의 mandatory_actions와 동기화되어야 함

        Returns:
            mandatory action_id 목록 (deadline 내에 완료해야 하는 action)
        """
        diagnosis = (self.current_state.working_diagnosis or "").lower()
        completed_action_ids = {a.action_id for a in self.action_history}
        mandatory = []

        # ============================================================
        # Sepsis / Septic Shock - Hour-1 Bundle (deadline: 60 min)
        # Source: SSC 2021 Guidelines - Table 1
        # ============================================================
        if any(kw in diagnosis for kw in ["sepsis", "septic", "infection"]):
            sepsis_mandatory = [
                "order_lab_lactate",           # Measure lactate
                "order_lab_blood_culture",     # Obtain blood cultures before antibiotics
                "give_broad_spectrum_antibiotics",  # Administer antibiotics
            ]
            # Septic Shock에만 필요
            if "shock" in diagnosis:
                sepsis_mandatory.extend([
                    "give_crystalloid_30ml_kg",    # Fluid resuscitation
                    "start_vasopressor_norepinephrine",  # If hypotensive after fluids
                ])
            mandatory.extend([a for a in sepsis_mandatory if a not in completed_action_ids])

        # ============================================================
        # STEMI - Door-to-Balloon (deadline: 90 min)
        # Source: AHA STEMI Guidelines
        # ============================================================
        if any(kw in diagnosis for kw in ["stemi", "st_elevation", "inferior_stemi"]):
            stemi_mandatory = [
                "obtain_12_lead_ecg",          # ECG within 10 min
                "give_aspirin_loading",        # Aspirin 325mg
                "give_p2y12_inhibitor",        # P2Y12 inhibitor
                "give_anticoagulation",        # Heparin/Enoxaparin
                "activate_cath_lab",           # Activate cath lab for PCI
            ]
            mandatory.extend([a for a in stemi_mandatory if a not in completed_action_ids])

        # ============================================================
        # DKA - Initial Treatment (deadline: varies)
        # Source: ADA DKA Guidelines
        # ============================================================
        if any(kw in diagnosis for kw in ["dka", "ketoacidosis", "diabetic"]):
            dka_mandatory = [
                "give_iv_fluid_bolus",         # IV fluids
                "order_lab_glucose",           # Monitor glucose
                "order_lab_bmp",               # Check potassium before insulin
            ]
            mandatory.extend([a for a in dka_mandatory if a not in completed_action_ids])

        return mandatory

    def _has_rv_involvement(self) -> bool:
        """Check if patient has right ventricular involvement (contraindication for nitroglycerin)"""
        # Check ECG results for inferior STEMI or RV involvement
        for result in self.current_state.imaging_results:
            result_str = str(result).lower()
            if any(kw in result_str for kw in ["inferior", "rv", "right ventricular", "v4r"]):
                return True

        # Check diagnosis
        diagnosis = (self.current_state.working_diagnosis or "").lower()
        if "inferior" in diagnosis or "rv" in diagnosis:
            return True

        return False

    def _is_abnormal(self, test_code: str, value) -> bool:
        """검사 결과 이상 여부 판단 - 설정에 정의된 임계값 사용"""
        # 질적 결과 처리 (문자열)
        if isinstance(value, str):
            value_lower = value.lower()
            # 양성/비정상 키워드 체크
            abnormal_keywords = [
                "positive", "abnormal", "elevated", "high", "low",
                "present", "detected", "gram_positive", "gram_negative"
            ]
            for kw in abnormal_keywords:
                if kw in value_lower:
                    return True
            return False

        # 수치 결과 처리
        for threshold in self.config.lab_thresholds:
            if threshold.test_code.lower() == test_code.lower():
                return value < threshold.low or value > threshold.high

        # 설정에 없는 수치 검사는 기본적으로 정상으로 간주
        logger.warning(f"No threshold defined for {test_code}, assuming normal")
        return False
