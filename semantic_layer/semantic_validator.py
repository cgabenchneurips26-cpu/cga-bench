"""
Semantic Validator: 임상 컨텍스트 기반 검증기

LLM을 사용하여 액션의 임상적 적절성을 검증합니다.

기능:
- 환자 상태 기반 적절성 검증
- 금기 사항 체크
- 시퀀스 위반 감지
- 누락된 필수 액션 감지
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set
from enum import Enum

from cga_bench.agent_runner.llm_provider import BaseLLMProvider, LLMMessage
from .constraint_synthesizer import SynthesizedConstraints
from cga_bench.cpg_model.schemas.base import Action

logger = logging.getLogger(__name__)


class ValidationSeverity(str, Enum):
    """검증 결과 심각도"""
    CRITICAL = "critical"  # Must not proceed
    WARNING = "warning"  # Proceed with caution
    INFO = "info"  # Informational


class ViolationType(str, Enum):
    """위반 유형"""
    FORBIDDEN_ACTION = "forbidden_action"
    MISSING_MANDATORY = "missing_mandatory"
    SEQUENCE_VIOLATION = "sequence_violation"
    TIMING_VIOLATION = "timing_violation"
    CONTRAINDICATION = "contraindication"
    CLINICAL_INAPPROPRIATENESS = "clinical_inappropriateness"


@dataclass
class ValidationIssue:
    """검증 이슈"""
    issue_type: ViolationType
    severity: ValidationSeverity
    action_id: str
    message: str
    suggestion: Optional[str] = None
    related_guideline: Optional[str] = None


@dataclass
class ValidationResult:
    """검증 결과"""
    is_valid: bool
    issues: List[ValidationIssue] = field(default_factory=list)
    approved_actions: List[str] = field(default_factory=list)
    rejected_actions: List[str] = field(default_factory=list)
    suggested_additions: List[str] = field(default_factory=list)
    confidence: float = 0.0
    validation_mode: str = "full"  # "full" (LLM+rules), "rule_based_only" (fallback)

    @property
    def critical_issues(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.CRITICAL]

    @property
    def warnings(self) -> List[ValidationIssue]:
        return [i for i in self.issues if i.severity == ValidationSeverity.WARNING]

    @property
    def is_fallback(self) -> bool:
        """LLM 없이 rule-based fallback으로 동작했는지 여부"""
        return self.validation_mode == "rule_based_only"


class SemanticValidator:
    """
    시맨틱 검증기

    제약 조건과 LLM을 조합하여 액션의 임상적 적절성을 검증합니다.
    """

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        use_llm_validation: bool = True,
        strict_mode: bool = False
    ):
        """
        Args:
            llm_provider: LLM 프로바이더 (None이면 rule-based만 사용)
            use_llm_validation: LLM 검증 활성화 여부
            strict_mode: True면 LLM 없을 때 에러 발생, False면 경고 후 rule-based fallback
        """
        self.llm_provider = llm_provider
        self.use_llm_validation = use_llm_validation
        self.strict_mode = strict_mode

        # LLM 필요한데 없으면 경고
        if use_llm_validation and llm_provider is None:
            if strict_mode:
                raise ValueError(
                    "SemanticValidator: strict_mode=True but llm_provider is None. "
                    "LLM validation requires a valid LLM provider."
                )
            else:
                logger.warning(
                    "⚠️ SemanticValidator: use_llm_validation=True but llm_provider is None. "
                    "Falling back to RULE-BASED validation only. Results may be less accurate."
                )

    def validate(
        self,
        proposed_actions: List[Action],
        patient_state: Dict[str, Any],
        completed_actions: Set[str],
        constraints: SynthesizedConstraints,
        current_time_minutes: float = 0
    ) -> ValidationResult:
        """
        제안된 액션 검증

        Args:
            proposed_actions: 제안된 액션 목록
            patient_state: 환자 상태
            completed_actions: 완료된 액션 집합
            constraints: 합성된 제약 조건
            current_time_minutes: 현재 시간 (분)

        Returns:
            ValidationResult: 검증 결과
        """
        issues = []
        approved = []
        rejected = []
        suggestions = []

        # Step 1: Rule-based validation
        for action in proposed_actions:
            action_issues = self._validate_action_rules(
                action,
                patient_state,
                completed_actions,
                constraints,
                current_time_minutes
            )

            if any(i.severity == ValidationSeverity.CRITICAL for i in action_issues):
                rejected.append(action.action_id)
            else:
                approved.append(action.action_id)

            issues.extend(action_issues)

        # Step 2: Check for missing mandatory actions
        mandatory = constraints.get_mandatory_for_state(patient_state, completed_actions)
        proposed_ids = {a.action_id for a in proposed_actions}

        for mandatory_action in mandatory:
            if mandatory_action not in proposed_ids and mandatory_action not in completed_actions:
                deadline = constraints.action_deadlines.get(mandatory_action)
                if deadline and current_time_minutes < deadline:
                    issues.append(ValidationIssue(
                        issue_type=ViolationType.MISSING_MANDATORY,
                        severity=ValidationSeverity.WARNING,
                        action_id=mandatory_action,
                        message=f"Mandatory action '{mandatory_action}' not included",
                        suggestion=f"Consider adding {mandatory_action}"
                    ))
                    suggestions.append(mandatory_action)

        # Step 3: LLM-based clinical validation (optional)
        if self.use_llm_validation and self.llm_provider:
            llm_issues = self._validate_with_llm(
                proposed_actions,
                patient_state,
                completed_actions
            )
            issues.extend(llm_issues)

            # Update rejected based on LLM critical issues
            for issue in llm_issues:
                if issue.severity == ValidationSeverity.CRITICAL:
                    if issue.action_id in approved:
                        approved.remove(issue.action_id)
                        rejected.append(issue.action_id)

        # Calculate overall validity
        is_valid = len([i for i in issues if i.severity == ValidationSeverity.CRITICAL]) == 0
        confidence = self._calculate_confidence(issues, approved, rejected)

        # Determine validation mode
        llm_was_used = self.use_llm_validation and self.llm_provider is not None
        validation_mode = "full" if llm_was_used else "rule_based_only"

        if validation_mode == "rule_based_only":
            logger.info("📋 Validation completed using RULE-BASED mode only (no LLM)")

        return ValidationResult(
            is_valid=is_valid,
            issues=issues,
            approved_actions=approved,
            rejected_actions=rejected,
            suggested_additions=suggestions,
            confidence=confidence,
            validation_mode=validation_mode
        )

    def _validate_action_rules(
        self,
        action: Action,
        patient_state: Dict[str, Any],
        completed_actions: Set[str],
        constraints: SynthesizedConstraints,
        current_time: float
    ) -> List[ValidationIssue]:
        """규칙 기반 액션 검증"""
        issues = []

        # Check forbidden
        forbidden = constraints.get_forbidden_for_state(patient_state)
        if action.action_id in forbidden:
            issues.append(ValidationIssue(
                issue_type=ViolationType.FORBIDDEN_ACTION,
                severity=ValidationSeverity.CRITICAL,
                action_id=action.action_id,
                message=f"Action '{action.action_id}' is forbidden for this patient",
                related_guideline=constraints.source_guideline
            ))

        # Check sequence
        required_before = constraints.check_sequence_violation(
            action.action_id, completed_actions
        )
        if required_before:
            issues.append(ValidationIssue(
                issue_type=ViolationType.SEQUENCE_VIOLATION,
                severity=ValidationSeverity.CRITICAL,
                action_id=action.action_id,
                message=f"'{required_before}' must be completed before '{action.action_id}'",
                suggestion=f"First complete: {required_before}"
            ))

        # Check timing
        deadline = constraints.action_deadlines.get(action.action_id)
        if deadline and current_time > deadline:
            issues.append(ValidationIssue(
                issue_type=ViolationType.TIMING_VIOLATION,
                severity=ValidationSeverity.WARNING,
                action_id=action.action_id,
                message=f"Action '{action.action_id}' is past deadline ({deadline} min)"
            ))

        # Check contraindications
        allergies = patient_state.get("allergies", [])
        comorbidities = patient_state.get("comorbidities", [])

        for condition in allergies + comorbidities:
            condition_lower = condition.lower()
            for key, forbidden_actions in constraints.contraindication_map.items():
                if key in condition_lower and action.action_id in forbidden_actions:
                    issues.append(ValidationIssue(
                        issue_type=ViolationType.CONTRAINDICATION,
                        severity=ValidationSeverity.CRITICAL,
                        action_id=action.action_id,
                        message=f"'{action.action_id}' contraindicated due to '{condition}'"
                    ))

        # Check drug interactions based on patient state
        drug_issues = self._check_drug_interactions(action, patient_state)
        issues.extend(drug_issues)

        return issues

    def _check_drug_interactions(
        self,
        action: Action,
        patient_state: Dict[str, Any]
    ) -> List[ValidationIssue]:
        """환자 상태 기반 약물 상호작용 및 임상 상태 검증"""
        issues = []
        action_lower = action.action_id.lower()
        labs = patient_state.get("labs", {})
        comorbidities = [c.lower() for c in patient_state.get("comorbidities", [])]
        diagnosis = patient_state.get("working_diagnosis", "").lower()

        potassium = labs.get("potassium")

        # === DKA: Insulin when K+ < 3.3 ===
        if potassium is not None and potassium < 3.3:
            if any(kw in action_lower for kw in ["insulin", "start_insulin"]):
                if "hold" not in action_lower and "stop" not in action_lower:
                    issues.append(ValidationIssue(
                        issue_type=ViolationType.CONTRAINDICATION,
                        severity=ValidationSeverity.CRITICAL,
                        action_id=action.action_id,
                        message=(f"Insulin CONTRAINDICATED: K+ = {potassium} mEq/L (< 3.3). "
                                 f"Must replace potassium first."),
                        suggestion="give_potassium_iv before starting insulin"
                    ))

        # === DKA: SGLT2i continuation in DKA ===
        if "sglt2" in action_lower and "stop" not in action_lower and "discontinue" not in action_lower:
            if "dka" in diagnosis or "ketoacidosis" in diagnosis:
                issues.append(ValidationIssue(
                    issue_type=ViolationType.CONTRAINDICATION,
                    severity=ValidationSeverity.CRITICAL,
                    action_id=action.action_id,
                    message="SGLT2 inhibitor CONTRAINDICATED in DKA. Must discontinue.",
                    suggestion="stop_sglt2_inhibitor"
                ))

        # === HF: NSAIDs in Heart Failure ===
        if any(kw in action_lower for kw in ["nsaid", "ibuprofen", "naproxen", "ketorolac"]):
            if any("heart_failure" in c or "hfref" in c or "hf" == c for c in comorbidities):
                issues.append(ValidationIssue(
                    issue_type=ViolationType.CONTRAINDICATION,
                    severity=ValidationSeverity.CRITICAL,
                    action_id=action.action_id,
                    message="NSAIDs CONTRAINDICATED in heart failure (Class III Harm, AHA 2022)",
                    suggestion="Use alternative analgesic"
                ))

        # === HF: Non-DHP CCBs in HFrEF ===
        if any(kw in action_lower for kw in ["diltiazem", "verapamil"]):
            if any("hfref" in c or "reduced_ef" in c for c in comorbidities):
                issues.append(ValidationIssue(
                    issue_type=ViolationType.CONTRAINDICATION,
                    severity=ValidationSeverity.CRITICAL,
                    action_id=action.action_id,
                    message="Non-DHP CCBs CONTRAINDICATED in HFrEF (negative inotropic effect)",
                    suggestion="Consider alternative rate control"
                ))

        # === HF: Beta-blockers in cardiogenic shock ===
        if any(kw in action_lower for kw in ["beta_blocker", "carvedilol", "metoprolol", "bisoprolol"]):
            if "cardiogenic_shock" in diagnosis or "cardiogenic shock" in diagnosis:
                issues.append(ValidationIssue(
                    issue_type=ViolationType.CONTRAINDICATION,
                    severity=ValidationSeverity.CRITICAL,
                    action_id=action.action_id,
                    message="Beta-blockers CONTRAINDICATED in cardiogenic shock",
                    suggestion="vasopressor_support or inotrope_support"
                ))

        # === AKI: Contrast in eGFR < 30 ===
        egfr = labs.get("egfr")
        if egfr is not None and egfr < 30:
            if any(kw in action_lower for kw in ["contrast", "ct_with_contrast"]):
                issues.append(ValidationIssue(
                    issue_type=ViolationType.CONTRAINDICATION,
                    severity=ValidationSeverity.CRITICAL,
                    action_id=action.action_id,
                    message=(f"Contrast CONTRAINDICATED: eGFR = {egfr} (< 30). "
                             f"Consider alternative imaging."),
                    suggestion="consider_alternative_imaging"
                ))

        # === AKI: Potassium in hyperkalemia ===
        if potassium is not None and potassium > 5.5:
            if any(kw in action_lower for kw in ["potassium", "kcl"]):
                if "monitor" not in action_lower and "treat" not in action_lower:
                    issues.append(ValidationIssue(
                        issue_type=ViolationType.CONTRAINDICATION,
                        severity=ValidationSeverity.CRITICAL,
                        action_id=action.action_id,
                        message=(f"Potassium CONTRAINDICATED: K+ = {potassium} mEq/L (> 5.5). "
                                 f"Treat hyperkalemia first."),
                        suggestion="treat_hyperkalemia_temporizing"
                    ))

        return issues

    def _validate_with_llm(
        self,
        actions: List[Action],
        patient_state: Dict[str, Any],
        completed_actions: Set[str]
    ) -> List[ValidationIssue]:
        """LLM 기반 임상 검증"""
        if not self.llm_provider:
            return []

        # Format patient state
        patient_summary = self._format_patient_state(patient_state)

        # Format proposed actions
        actions_str = "\n".join([
            f"- {a.action_id}: {a.justification or 'No justification'}"
            for a in actions
        ])

        # Format completed actions
        completed_str = ", ".join(completed_actions) if completed_actions else "None"

        prompt = f"""Review these proposed clinical actions for safety and appropriateness.

## Patient State
{patient_summary}

## Completed Actions
{completed_str}

## Proposed Actions
{actions_str}

## Task
Identify any clinical safety issues:
1. Contraindicated actions for this patient
2. Missing critical prerequisite actions
3. Potentially harmful action combinations
4. Actions inappropriate for the clinical context

Return JSON:
{{
    "issues": [
        {{
            "action_id": "action with issue",
            "severity": "critical|warning|info",
            "issue_type": "contraindication|sequence|clinical_inappropriateness",
            "message": "description of issue",
            "suggestion": "recommended action"
        }}
    ],
    "overall_assessment": "brief summary"
}}

Only include actual safety issues. Return empty issues array if actions are appropriate."""

        messages = [
            LLMMessage(role="system", content="You are a clinical safety reviewer."),
            LLMMessage(role="user", content=prompt)
        ]

        schema = {
            "type": "object",
            "properties": {
                "issues": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action_id": {"type": "string"},
                            "severity": {"type": "string"},
                            "issue_type": {"type": "string"},
                            "message": {"type": "string"},
                            "suggestion": {"type": "string"}
                        }
                    }
                },
                "overall_assessment": {"type": "string"}
            }
        }

        try:
            result = self.llm_provider.complete_json(messages, schema)
            issues_data = result.get("issues", [])

            issues = []
            for issue_data in issues_data:
                severity_str = issue_data.get("severity", "warning").lower()
                if "critical" in severity_str:
                    severity = ValidationSeverity.CRITICAL
                elif "warning" in severity_str:
                    severity = ValidationSeverity.WARNING
                else:
                    severity = ValidationSeverity.INFO

                issue_type_str = issue_data.get("issue_type", "clinical_inappropriateness")
                issue_type = ViolationType.CLINICAL_INAPPROPRIATENESS
                if "contra" in issue_type_str:
                    issue_type = ViolationType.CONTRAINDICATION
                elif "sequence" in issue_type_str:
                    issue_type = ViolationType.SEQUENCE_VIOLATION

                issues.append(ValidationIssue(
                    issue_type=issue_type,
                    severity=severity,
                    action_id=issue_data.get("action_id", "unknown"),
                    message=issue_data.get("message", ""),
                    suggestion=issue_data.get("suggestion")
                ))

            return issues

        except Exception as e:
            logger.warning(f"LLM validation failed: {e}")
            return []

    def _format_patient_state(self, state: Dict[str, Any]) -> str:
        """환자 상태 포맷팅"""
        parts = []

        if state.get("chief_complaint"):
            parts.append(f"Chief Complaint: {state['chief_complaint']}")
        if state.get("working_diagnosis"):
            parts.append(f"Diagnosis: {state['working_diagnosis']}")

        vitals = state.get("vitals", {})
        if vitals:
            vital_strs = []
            for key in ["heart_rate", "blood_pressure_systolic", "blood_pressure_diastolic",
                        "respiratory_rate", "temperature", "oxygen_saturation"]:
                if vitals.get(key):
                    vital_strs.append(f"{key}: {vitals[key]}")
            if vital_strs:
                parts.append(f"Vitals: {', '.join(vital_strs)}")

        if state.get("allergies"):
            parts.append(f"Allergies: {', '.join(state['allergies'])}")
        if state.get("comorbidities"):
            parts.append(f"Comorbidities: {', '.join(state['comorbidities'])}")

        labs = state.get("lab_results", [])
        if labs:
            lab_strs = []
            for lab in labs[:5]:
                if isinstance(lab, dict):
                    lab_strs.append(f"{lab.get('test_code')}: {lab.get('value')}")
            if lab_strs:
                parts.append(f"Labs: {', '.join(lab_strs)}")

        return "\n".join(parts) if parts else "No patient information available"

    def _calculate_confidence(
        self,
        issues: List[ValidationIssue],
        approved: List[str],
        rejected: List[str]
    ) -> float:
        """검증 신뢰도 계산"""
        if not approved and not rejected:
            return 0.0

        total = len(approved) + len(rejected)
        critical_count = len([i for i in issues if i.severity == ValidationSeverity.CRITICAL])
        warning_count = len([i for i in issues if i.severity == ValidationSeverity.WARNING])

        # Base confidence
        confidence = 0.9

        # Reduce for critical issues
        confidence -= critical_count * 0.2

        # Reduce for warnings
        confidence -= warning_count * 0.05

        return max(0.0, min(1.0, confidence))
