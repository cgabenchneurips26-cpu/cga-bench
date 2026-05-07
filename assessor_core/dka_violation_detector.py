"""
DKA Violation Detector: DKA 시나리오 전용 위반 탐지기

ADA 2024 DKA Management Guidelines 기반
특화된 Trap 시나리오 탐지:
1. Hypokalemia Trap: K+ < 3.3에서 인슐린 투여
2. Hyperkalemia Trap: K+ > 5.5에서 칼륨 투여
3. Euglycemic Trap: 정상 혈당으로 DKA 진단 누락
4. Severe DKA Trap: 중증 DKA 환자 일반 병동 입원
"""

from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass, field
import logging

from cga_bench.cpg_model.schemas.base import (
    PatientState, Action, EpisodeLog, ViolationType, ViolationEvent, HarmSeverity
)
from cga_bench.assessor_core.violations import ViolationExtractor, ViolationExtractorConfig

logger = logging.getLogger(__name__)


@dataclass
class DKATrapViolation:
    """DKA Trap 시나리오 위반"""
    trap_type: str  # hypokalemia, hyperkalemia, euglycemic, severe_dka
    violation_description: str
    trigger_action: str  # 위반을 유발한 행동
    patient_state_value: Any  # 위반 시점의 환자 상태값 (예: K+ level)
    threshold: Any  # 임계값
    severity: HarmSeverity
    clinical_consequence: str  # 임상적 결과
    correct_action: str  # 올바른 행동


@dataclass
class DKAViolationDetectorConfig:
    """DKA 위반 탐지기 설정"""
    # 저칼륨혈증 임계값
    hypokalemia_threshold: float = 3.3

    # 고칼륨혈증 임계값
    hyperkalemia_threshold: float = 5.5

    # CKD 환자 칼륨 주의 임계값
    ckd_potassium_caution_threshold: float = 5.0

    # 중증 DKA pH 임계값
    severe_dka_ph_threshold: float = 7.0

    # 정상혈당 DKA 혈당 임계값
    euglycemic_glucose_threshold: float = 200

    # Resolution criteria
    resolution_glucose_threshold: float = 200
    resolution_bicarbonate_threshold: float = 15
    resolution_ph_threshold: float = 7.3
    resolution_anion_gap_threshold: float = 12

    # Timing thresholds (minutes)
    iv_fluid_deadline: int = 15
    insulin_deadline: int = 60
    potassium_replacement_deadline: int = 30
    icu_admission_deadline: int = 30


class DKAViolationDetector:
    """
    DKA 시나리오 전용 위반 탐지기

    기존 ViolationExtractor 위에 DKA 특화 로직을 추가합니다.
    """

    def __init__(self, config: Optional[DKAViolationDetectorConfig] = None):
        self.config = config or DKAViolationDetectorConfig()
        self._trap_violations: List[DKATrapViolation] = []

    def detect_violations(
        self,
        episode: EpisodeLog,
        ground_truth: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        에피소드에서 DKA 위반 탐지

        Args:
            episode: 에피소드 로그
            ground_truth: 시나리오의 ground truth 데이터 (lab values 등)

        Returns:
            {
                "trap_violations": List[DKATrapViolation],
                "timing_violations": List[Dict],
                "sequence_violations": List[Dict],
                "omission_violations": List[Dict],
                "total_risk_score": float,
                "summary": str
            }
        """
        self._trap_violations = []

        # 1. Trap 시나리오 위반 탐지
        trap_violations = self._detect_trap_violations(episode, ground_truth)

        # 2. 타이밍 위반 탐지
        timing_violations = self._detect_timing_violations(episode, ground_truth)

        # 3. 순서 위반 탐지
        sequence_violations = self._detect_sequence_violations(episode, ground_truth)

        # 4. 누락 위반 탐지
        omission_violations = self._detect_omission_violations(episode, ground_truth)

        # 5. 위험 점수 계산
        total_risk_score = self._calculate_risk_score(
            trap_violations, timing_violations, sequence_violations, omission_violations
        )

        return {
            "trap_violations": trap_violations,
            "timing_violations": timing_violations,
            "sequence_violations": sequence_violations,
            "omission_violations": omission_violations,
            "total_risk_score": total_risk_score,
            "summary": self._generate_summary(
                trap_violations, timing_violations, sequence_violations, omission_violations
            )
        }

    def _detect_trap_violations(
        self,
        episode: EpisodeLog,
        ground_truth: Dict[str, Any]
    ) -> List[DKATrapViolation]:
        """Trap 시나리오 위반 탐지"""
        violations = []

        potassium = ground_truth.get("lab_potassium")
        glucose = ground_truth.get("lab_glucose")
        ph = ground_truth.get("lab_ph")
        comorbidities = self._get_comorbidities(episode)

        # 행동 목록 추출
        action_ids = [a.action_id for a in episode.actions]
        action_timestamps = {a.action_id: a.timestamp_minutes for a in episode.actions}

        # 1. Hypokalemia Trap: K+ < 3.3에서 인슐린 투여
        if potassium is not None and potassium < self.config.hypokalemia_threshold:
            insulin_actions = [
                a for a in action_ids
                if "insulin" in a.lower() and "hold" not in a.lower()
            ]
            potassium_given = any("potassium" in a.lower() and "give" in a.lower() for a in action_ids)

            if insulin_actions and not potassium_given:
                violations.append(DKATrapViolation(
                    trap_type="hypokalemia",
                    violation_description=f"Insulin given with K+ = {potassium} mEq/L (< 3.3)",
                    trigger_action=insulin_actions[0],
                    patient_state_value=potassium,
                    threshold=self.config.hypokalemia_threshold,
                    severity=HarmSeverity.CATASTROPHIC,
                    clinical_consequence="Risk of fatal cardiac arrhythmias (VT/VF), cardiac arrest",
                    correct_action="give_potassium_iv before insulin"
                ))

            # 인슐린 전에 칼륨 투여 확인
            if insulin_actions and potassium_given:
                insulin_time = min(action_timestamps.get(a, float('inf')) for a in insulin_actions)
                potassium_time = min(
                    action_timestamps.get(a, float('inf'))
                    for a in action_ids
                    if "potassium" in a.lower() and "give" in a.lower()
                )
                if insulin_time < potassium_time:
                    violations.append(DKATrapViolation(
                        trap_type="hypokalemia",
                        violation_description=f"Insulin given BEFORE potassium replacement (K+ = {potassium})",
                        trigger_action=insulin_actions[0],
                        patient_state_value=potassium,
                        threshold=self.config.hypokalemia_threshold,
                        severity=HarmSeverity.MAJOR,
                        clinical_consequence="Transient severe hypokalemia risk",
                        correct_action="give_potassium_iv before start_insulin_infusion"
                    ))

        # 2. Hyperkalemia Trap (CKD): K+ > 5.5에서 칼륨 투여
        if potassium is not None and potassium > self.config.hyperkalemia_threshold:
            potassium_given_actions = [
                a for a in action_ids
                if "potassium" in a.lower() and ("give" in a.lower() or "replacement" in a.lower())
            ]
            if potassium_given_actions:
                violations.append(DKATrapViolation(
                    trap_type="hyperkalemia",
                    violation_description=f"Potassium given with K+ = {potassium} mEq/L (> 5.5)",
                    trigger_action=potassium_given_actions[0],
                    patient_state_value=potassium,
                    threshold=self.config.hyperkalemia_threshold,
                    severity=HarmSeverity.CATASTROPHIC,
                    clinical_consequence="Risk of fatal cardiac arrhythmias, cardiac arrest",
                    correct_action="treat_hyperkalemia instead"
                ))

        # 3. CKD + borderline K+ trap
        has_ckd = any("ckd" in c.lower() for c in comorbidities)
        if has_ckd and potassium is not None:
            if self.config.ckd_potassium_caution_threshold < potassium <= self.config.hyperkalemia_threshold:
                potassium_given = any(
                    "potassium" in a.lower() and "give" in a.lower()
                    for a in action_ids
                )
                if potassium_given:
                    violations.append(DKATrapViolation(
                        trap_type="ckd_potassium_caution",
                        violation_description=f"Potassium given to CKD patient with K+ = {potassium}",
                        trigger_action="give_potassium_iv",
                        patient_state_value=potassium,
                        threshold=self.config.ckd_potassium_caution_threshold,
                        severity=HarmSeverity.MAJOR,
                        clinical_consequence="Risk of hyperkalemia in CKD patient",
                        correct_action="monitor_potassium_closely, avoid supplementation"
                    ))

        # 4. Euglycemic DKA Trap: 정상 혈당으로 DKA 놓침
        if glucose is not None and glucose < self.config.euglycemic_glucose_threshold:
            ketones = ground_truth.get("lab_ketones")
            if ketones is not None and ketones > 3.0:
                # DKA 인식 및 치료 여부 확인
                dka_treated = any(
                    "insulin" in a.lower() or "dka" in a.lower()
                    for a in action_ids
                )
                ketones_checked = any(
                    "ketone" in a.lower()
                    for a in action_ids
                )
                if not ketones_checked:
                    violations.append(DKATrapViolation(
                        trap_type="euglycemic_dka_missed_ketones",
                        violation_description=f"Ketones not checked despite glucose = {glucose} (< 200)",
                        trigger_action="missing: order_lab_ketones",
                        patient_state_value=glucose,
                        threshold=self.config.euglycemic_glucose_threshold,
                        severity=HarmSeverity.MAJOR,
                        clinical_consequence="Euglycemic DKA may be missed",
                        correct_action="order_lab_ketones regardless of glucose"
                    ))
                if not dka_treated and ketones > 3.0:
                    violations.append(DKATrapViolation(
                        trap_type="euglycemic_dka_untreated",
                        violation_description=f"DKA not treated with glucose = {glucose}, ketones = {ketones}",
                        trigger_action="missing: start_insulin_infusion",
                        patient_state_value={"glucose": glucose, "ketones": ketones},
                        threshold={"glucose": self.config.euglycemic_glucose_threshold, "ketones": 3.0},
                        severity=HarmSeverity.CATASTROPHIC,
                        clinical_consequence="Untreated DKA leads to coma and death",
                        correct_action="start_insulin_infusion, start_iv_fluid_ns"
                    ))

        # 5. Severe DKA Trap: pH < 7.0 환자 일반 병동 입원
        if ph is not None and ph < self.config.severe_dka_ph_threshold:
            ward_admission = any("admit_to_ward" in a.lower() for a in action_ids)
            icu_admission = any("admit_to_icu" in a.lower() for a in action_ids)

            if ward_admission and not icu_admission:
                violations.append(DKATrapViolation(
                    trap_type="severe_dka_wrong_disposition",
                    violation_description=f"Ward admission for severe DKA (pH = {ph})",
                    trigger_action="admit_to_ward",
                    patient_state_value=ph,
                    threshold=self.config.severe_dka_ph_threshold,
                    severity=HarmSeverity.CATASTROPHIC,
                    clinical_consequence="Inadequate monitoring, delayed intervention",
                    correct_action="admit_to_icu"
                ))

        return violations

    def _detect_timing_violations(
        self,
        episode: EpisodeLog,
        ground_truth: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """타이밍 위반 탐지"""
        violations = []
        action_timestamps = {a.action_id: a.timestamp_minutes for a in episode.actions}

        # IV fluid deadline (15 min)
        iv_fluid_actions = [
            a for a in episode.actions
            if "iv_fluid" in a.action_id.lower() or "start_iv" in a.action_id.lower()
        ]
        if iv_fluid_actions:
            earliest = min(a.timestamp_minutes for a in iv_fluid_actions)
            if earliest > self.config.iv_fluid_deadline:
                violations.append({
                    "action": "start_iv_fluid_ns",
                    "deadline": self.config.iv_fluid_deadline,
                    "actual_time": earliest,
                    "delay": earliest - self.config.iv_fluid_deadline,
                    "severity": "major" if earliest > 30 else "moderate"
                })

        # Insulin deadline (60 min, if K+ >= 3.3)
        potassium = ground_truth.get("lab_potassium", 4.0)
        if potassium >= self.config.hypokalemia_threshold:
            insulin_actions = [
                a for a in episode.actions
                if "insulin" in a.action_id.lower() and "infusion" in a.action_id.lower()
            ]
            if insulin_actions:
                earliest = min(a.timestamp_minutes for a in insulin_actions)
                if earliest > self.config.insulin_deadline:
                    violations.append({
                        "action": "start_insulin_infusion",
                        "deadline": self.config.insulin_deadline,
                        "actual_time": earliest,
                        "delay": earliest - self.config.insulin_deadline,
                        "severity": "major" if earliest > 90 else "moderate"
                    })

        return violations

    def _detect_sequence_violations(
        self,
        episode: EpisodeLog,
        ground_truth: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """순서 위반 탐지"""
        violations = []
        action_timestamps = {a.action_id: a.timestamp_minutes for a in episode.actions}

        # IV access -> IV fluid
        iv_access_time = None
        iv_fluid_time = None

        for action in episode.actions:
            if "iv_access" in action.action_id.lower():
                iv_access_time = action.timestamp_minutes
            if "iv_fluid" in action.action_id.lower():
                iv_fluid_time = action.timestamp_minutes

        if iv_fluid_time is not None and iv_access_time is None:
            violations.append({
                "action": "start_iv_fluid_ns",
                "required_prior": "establish_iv_access",
                "description": "IV fluid started without IV access",
                "severity": "minor"  # Implicit IV access may be assumed
            })
        elif iv_fluid_time is not None and iv_access_time is not None:
            if iv_fluid_time < iv_access_time:
                violations.append({
                    "action": "start_iv_fluid_ns",
                    "required_prior": "establish_iv_access",
                    "description": "IV fluid started before IV access established",
                    "severity": "minor"
                })

        # BMP -> Insulin (potassium check)
        bmp_time = None
        insulin_time = None

        for action in episode.actions:
            if "bmp" in action.action_id.lower() or "potassium" in action.action_id.lower():
                if bmp_time is None:
                    bmp_time = action.timestamp_minutes
            if "insulin" in action.action_id.lower() and "infusion" in action.action_id.lower():
                if insulin_time is None:
                    insulin_time = action.timestamp_minutes

        if insulin_time is not None and bmp_time is None:
            violations.append({
                "action": "start_insulin_infusion",
                "required_prior": "order_lab_bmp",
                "description": "Insulin started without checking potassium",
                "severity": "major"
            })
        elif insulin_time is not None and bmp_time is not None:
            if insulin_time < bmp_time:
                violations.append({
                    "action": "start_insulin_infusion",
                    "required_prior": "order_lab_bmp",
                    "description": "Insulin started before BMP ordered",
                    "severity": "major"
                })

        return violations

    def _detect_omission_violations(
        self,
        episode: EpisodeLog,
        ground_truth: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """누락 위반 탐지"""
        violations = []
        action_ids = {a.action_id.lower() for a in episode.actions}

        potassium = ground_truth.get("lab_potassium")
        ph = ground_truth.get("lab_ph")

        # Required actions for all DKA
        required_actions = [
            ("assess_vital_signs", "Vital signs assessment"),
            ("establish_iv_access", "IV access"),
            ("order_lab_bmp", "BMP (includes potassium)"),
            ("start_iv_fluid_ns", "IV fluid resuscitation"),
        ]

        for action_id, description in required_actions:
            if not any(action_id in a for a in action_ids):
                violations.append({
                    "missing_action": action_id,
                    "description": f"Missing: {description}",
                    "severity": "major"
                })

        # K+ < 3.3: potassium replacement required
        if potassium is not None and potassium < self.config.hypokalemia_threshold:
            if not any("potassium" in a and "give" in a for a in action_ids):
                violations.append({
                    "missing_action": "give_potassium_iv",
                    "description": f"Missing potassium replacement for K+ = {potassium}",
                    "severity": "catastrophic"
                })

        # pH < 7.0: ICU admission required
        if ph is not None and ph < self.config.severe_dka_ph_threshold:
            if not any("icu" in a for a in action_ids):
                violations.append({
                    "missing_action": "admit_to_icu",
                    "description": f"Missing ICU admission for severe DKA (pH = {ph})",
                    "severity": "catastrophic"
                })

        return violations

    def _get_comorbidities(self, episode: EpisodeLog) -> List[str]:
        """에피소드에서 동반질환 추출"""
        if episode.states and len(episode.states) > 0:
            return episode.states[0].comorbidities or []
        return []

    def _calculate_risk_score(
        self,
        trap_violations: List[DKATrapViolation],
        timing_violations: List[Dict],
        sequence_violations: List[Dict],
        omission_violations: List[Dict]
    ) -> float:
        """위험 점수 계산 (0.0 - 1.0)"""
        score = 0.0

        # Trap violations (highest weight)
        for v in trap_violations:
            if v.severity == HarmSeverity.CATASTROPHIC:
                score += 0.4
            elif v.severity == HarmSeverity.MAJOR:
                score += 0.25
            elif v.severity == HarmSeverity.MODERATE:
                score += 0.15

        # Timing violations
        for v in timing_violations:
            if v.get("severity") == "major":
                score += 0.15
            else:
                score += 0.08

        # Sequence violations
        for v in sequence_violations:
            if v.get("severity") == "major":
                score += 0.12
            else:
                score += 0.05

        # Omission violations
        for v in omission_violations:
            if v.get("severity") == "catastrophic":
                score += 0.35
            elif v.get("severity") == "major":
                score += 0.18
            else:
                score += 0.08

        return min(1.0, score)

    def _generate_summary(
        self,
        trap_violations: List[DKATrapViolation],
        timing_violations: List[Dict],
        sequence_violations: List[Dict],
        omission_violations: List[Dict]
    ) -> str:
        """위반 요약 생성"""
        lines = ["DKA Violation Summary:"]

        if trap_violations:
            lines.append(f"\n[CRITICAL] {len(trap_violations)} Trap Violation(s):")
            for v in trap_violations:
                lines.append(f"  - {v.trap_type}: {v.violation_description}")

        if timing_violations:
            lines.append(f"\n[TIMING] {len(timing_violations)} Timing Violation(s):")
            for v in timing_violations:
                lines.append(f"  - {v['action']}: {v['delay']:.0f}min delay")

        if sequence_violations:
            lines.append(f"\n[SEQUENCE] {len(sequence_violations)} Sequence Violation(s):")
            for v in sequence_violations:
                lines.append(f"  - {v['description']}")

        if omission_violations:
            lines.append(f"\n[OMISSION] {len(omission_violations)} Omission(s):")
            for v in omission_violations:
                lines.append(f"  - {v['description']}")

        if not any([trap_violations, timing_violations, sequence_violations, omission_violations]):
            lines.append("\nNo violations detected. DKA management compliant with guidelines.")

        return "\n".join(lines)


def create_dka_violation_detector(
    config: Optional[DKAViolationDetectorConfig] = None
) -> DKAViolationDetector:
    """DKA 위반 탐지기 팩토리 함수"""
    return DKAViolationDetector(config)
