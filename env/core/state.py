"""
State Management Module
환자 상태, 에피소드 상태, 시간 관리
FHIR 리소스 매핑 지원
"""
from __future__ import annotations
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Any, Set
from datetime import datetime, timedelta
from enum import Enum


class DispositionStatus(str, Enum):
    """환자 배치 상태"""
    PENDING = "pending"
    ADMITTED = "admitted"
    DISCHARGED = "discharged"
    TRANSFERRED = "transferred"
    DECEASED = "deceased"


@dataclass
class VitalSigns2:
    """활력 징후 - FHIR Observation 매핑 지원"""
    heart_rate: Optional[float] = None
    blood_pressure_systolic: Optional[float] = None
    blood_pressure_diastolic: Optional[float] = None
    respiratory_rate: Optional[float] = None
    temperature_celsius: Optional[float] = None
    oxygen_saturation: Optional[float] = None
    map_mmhg: Optional[float] = None  # Mean Arterial Pressure
    gcs: Optional[int] = None  # Glasgow Coma Scale

    @property
    def mean_arterial_pressure(self) -> Optional[float]:
        """MAP 계산 (DBP + 1/3 * (SBP - DBP))"""
        if self.map_mmhg:
            return self.map_mmhg
        if self.blood_pressure_systolic and self.blood_pressure_diastolic:
            return self.blood_pressure_diastolic + (
                (self.blood_pressure_systolic - self.blood_pressure_diastolic) / 3
            )
        return None


@dataclass
class LabResult2:
    """검사 결과 - FHIR Observation 매핑"""
    test_code: str  # LOINC 코드 또는 내부 코드
    test_name: str
    value: Any  # 수치 또는 정성 결과
    unit: str
    timestamp_minutes: float  # 도착 후 분
    reference_low: Optional[float] = None
    reference_high: Optional[float] = None
    is_abnormal: bool = False
    is_critical: bool = False
    fhir_observation_id: Optional[str] = None
    # Terminology grounding (P0) - Optional for backward compatibility
    coded_concept: Optional[Any] = None   # CodedConcept from terminology.coding
    unit_ucum: Optional[str] = None       # UCUM-normalized unit string


@dataclass
class ImagingResult:
    """영상 검사 결과"""
    modality: str  # ECG, XRay, CT, MRI, Echo
    study_name: str
    findings: Dict[str, Any] = field(default_factory=dict)
    impression: str = ""
    timestamp_minutes: float = 0.0
    is_stat: bool = False
    fhir_imaging_study_id: Optional[str] = None


@dataclass
class MedicationAdministration:
    """약물 투여 기록 - FHIR MedicationAdministration"""
    medication_code: str
    medication_name: str
    dose: float
    dose_unit: str
    route: str  # IV, PO, IM, SQ
    timestamp_minutes: float
    infusion_rate: Optional[float] = None
    infusion_rate_unit: Optional[str] = None
    fhir_administration_id: Optional[str] = None


@dataclass
class PatientState2:
    """
    환자 상태 표현 - FHIR 리소스와 매핑 가능
    MedAgentBench/AgentClinic 어댑터 지원
    """
    state_id: str
    time_since_arrival_minutes: float = 0.0

    # Demographics (FHIR Patient)
    patient_id: str = ""
    age: int = 0
    sex: str = ""
    weight_kg: Optional[float] = None
    height_cm: Optional[float] = None

    # Vitals (FHIR Observation)
    vitals: VitalSigns2 = field(default_factory=VitalSigns2)

    # Labs (FHIR Observation)
    lab_results: List[LabResult2] = field(default_factory=list)

    # Imaging (FHIR ImagingStudy)
    imaging_results: List[ImagingResult] = field(default_factory=list)

    # Medications (FHIR MedicationAdministration)
    medications_given: List[MedicationAdministration] = field(default_factory=list)

    # Procedures (FHIR Procedure)
    procedures_done: List[str] = field(default_factory=list)

    # Pending orders
    pending_orders: Set[str] = field(default_factory=set)

    # Conditions (FHIR Condition)
    diagnoses: List[str] = field(default_factory=list)
    working_diagnosis: Optional[str] = None

    # Allergies (FHIR AllergyIntolerance)
    allergies: List[str] = field(default_factory=list)

    # Comorbidities
    comorbidities: List[str] = field(default_factory=list)

    # Contraindications
    contraindications: List[str] = field(default_factory=list)

    # Clinical context
    chief_complaint: str = ""
    setting: str = "ED"  # ED, clinic, ICU, floor
    acuity: str = "emergent"  # emergent, urgent, routine

    # Disposition
    disposition_status: DispositionStatus = DispositionStatus.PENDING

    # Hidden ground truth (에이전트 접근 불가)
    _ground_truth: Dict[str, Any] = field(default_factory=dict)

    def has_lab(self, test_code: str) -> bool:
        """특정 검사 결과 존재 여부"""
        return any(lab.test_code == test_code for lab in self.lab_results)

    def get_lab_value(self, test_code: str) -> Optional[Any]:
        """검사 결과 값 조회"""
        for lab in self.lab_results:
            if lab.test_code == test_code:
                return lab.value
        return None

    def has_imaging(self, modality: str) -> bool:
        """특정 영상 검사 존재 여부"""
        return any(img.modality == modality for img in self.imaging_results)

    def has_medication(self, medication_code: str) -> bool:
        """특정 약물 투여 여부"""
        return any(med.medication_code == medication_code for med in self.medications_given)

    def to_fhir_bundle(self) -> Dict[str, Any]:
        """FHIR Bundle로 변환"""
        entries: List[Dict[str, Any]] = []

        # Patient resource
        patient = {
            "resourceType": "Patient",
            "id": self.patient_id,
            "gender": self.sex.lower() if self.sex else "unknown",
            "birthDate": str(datetime.now().year - self.age) + "-01-01"
        }
        entries.append({"resource": patient})

        # Observation resources for vitals
        if self.vitals.heart_rate:
            entries.append({
                "resource": {
                    "resourceType": "Observation",
                    "code": {"coding": [{"system": "http://loinc.org", "code": "8867-4"}]},
                    "valueQuantity": {"value": self.vitals.heart_rate, "unit": "bpm"}
                }
            })

        # Add other observations...
        return {"resourceType": "Bundle", "type": "collection", "entry": entries}


@dataclass
class StateTransition:
    """상태 전이 기록"""
    from_state_id: str
    to_state_id: str
    action_id: str
    timestamp_minutes: float
    changes: Dict[str, Any] = field(default_factory=dict)


@dataclass
class EpisodeState:
    """
    에피소드 전체 상태 관리
    상태-행동 시퀀스 추적
    """
    episode_id: str
    scenario_id: str
    agent_id: str

    # Current state
    current_state: PatientState2 = field(default_factory=lambda: PatientState2(state_id="initial"))

    # History
    state_history: List[PatientState2] = field(default_factory=list)
    action_history: List[str] = field(default_factory=list)  # action_ids
    transitions: List[StateTransition] = field(default_factory=list)

    # Time management
    current_time_minutes: float = 0.0
    start_time: Optional[datetime] = None

    # Step tracking
    current_step: int = 0

    # Budget tracking
    llm_calls: int = 0
    tokens_used: int = 0
    tool_calls: int = 0

    # Termination
    is_terminated: bool = False
    termination_reason: Optional[str] = None

    def advance_time(self, minutes: float):
        """시간 진행"""
        self.current_time_minutes += minutes
        self.current_state.time_since_arrival_minutes = self.current_time_minutes

    def record_action(self, action_id: str, resulting_state: PatientState2):
        """행동 기록 및 상태 전이"""
        self.state_history.append(self.current_state)
        self.action_history.append(action_id)

        transition = StateTransition(
            from_state_id=self.current_state.state_id,
            to_state_id=resulting_state.state_id,
            action_id=action_id,
            timestamp_minutes=self.current_time_minutes
        )
        self.transitions.append(transition)

        self.current_state = resulting_state
        self.current_step += 1

    def terminate(self, reason: str):
        """에피소드 종료"""
        self.is_terminated = True
        self.termination_reason = reason


class TimeManager:
    """
    Temporal constraint 처리
    마감 시간, 시간 창 검증
    """

    def __init__(self, start_time: Optional[datetime] = None):
        self.start_time = start_time or datetime.now()
        self.elapsed_minutes: float = 0.0
        self.deadlines: Dict[str, float] = {}  # action -> deadline_minutes
        self.completed_at: Dict[str, float] = {}  # action -> completion_minutes

    def advance(self, minutes: float):
        """시간 진행"""
        self.elapsed_minutes += minutes

    def set_deadline(self, action: str, minutes: float):
        """마감 시간 설정"""
        self.deadlines[action] = minutes

    def mark_completed(self, action: str):
        """행동 완료 기록"""
        self.completed_at[action] = self.elapsed_minutes

    def check_deadline(self, action: str) -> Optional[float]:
        """
        마감 시간 초과 확인
        Returns: 초과 시간 (분) 또는 None (미초과)
        """
        if action not in self.deadlines:
            return None

        deadline = self.deadlines[action]
        if action in self.completed_at:
            completed = self.completed_at[action]
            if completed > deadline:
                return completed - deadline
            return None

        # 미완료 행동
        if self.elapsed_minutes > deadline:
            return self.elapsed_minutes - deadline
        return None

    def check_within_window(
        self,
        action: str,
        window_start: float,
        window_end: float
    ) -> bool:
        """행동이 시간 창 내에 수행되었는지 확인"""
        if action not in self.completed_at:
            return False

        completed = self.completed_at[action]
        return window_start <= completed <= window_end

    def get_remaining_time(self, action: str) -> Optional[float]:
        """마감까지 남은 시간"""
        if action not in self.deadlines:
            return None
        return max(0, self.deadlines[action] - self.elapsed_minutes)

    def get_overdue_actions(self) -> List[tuple]:
        """기한 초과 행동 목록"""
        overdue = []
        for action, deadline in self.deadlines.items():
            if action not in self.completed_at and self.elapsed_minutes > deadline:
                overdue.append((action, self.elapsed_minutes - deadline))
        return overdue
