"""
Constraint Synthesizer: 동적 규칙 생성기

파싱된 CPG에서 Decision Table과 유사한 제약 조건을 동적으로 생성합니다.

기능:
- 환자 상태 기반 조건부 규칙 생성
- 필수/금지/권장 액션 분류
- 타이밍 제약 생성
- 시퀀스 규칙 생성
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set
from enum import Enum

from cga_bench.agent_runner.llm_provider import BaseLLMProvider, LLMMessage
from .cpg_parser import (
    ParsedGuideline,
    ExtractedRecommendation,
    RecommendationStrength,
    ActionCategory,
)

logger = logging.getLogger(__name__)


@dataclass
class ConditionalRule:
    """조건부 규칙"""
    rule_id: str
    description: str
    # Conditions (patient state requirements)
    conditions: List[Dict[str, Any]] = field(default_factory=list)
    # Actions triggered by this rule
    mandatory_actions: List[str] = field(default_factory=list)
    recommended_actions: List[str] = field(default_factory=list)
    forbidden_actions: List[str] = field(default_factory=list)
    # Timing
    deadline_minutes: Optional[int] = None
    priority: int = 50  # Higher = more urgent


@dataclass
class SynthesizedConstraints:
    """합성된 제약 조건 세트"""
    domain: str
    source_guideline: str
    # Always applicable
    always_mandatory: List[str] = field(default_factory=list)
    always_forbidden: List[str] = field(default_factory=list)
    always_recommended: List[str] = field(default_factory=list)
    # Conditional rules
    conditional_rules: List[ConditionalRule] = field(default_factory=list)
    # Sequence constraints
    sequence_rules: List[Dict[str, str]] = field(default_factory=list)
    # Action metadata
    action_deadlines: Dict[str, int] = field(default_factory=dict)
    action_priorities: Dict[str, int] = field(default_factory=dict)
    # Contraindications
    contraindication_map: Dict[str, List[str]] = field(default_factory=dict)

    def get_mandatory_for_state(
        self,
        patient_state: Dict[str, Any],
        completed_actions: Set[str]
    ) -> List[str]:
        """환자 상태에 따른 필수 액션 반환"""
        mandatory = set(self.always_mandatory)

        for rule in self.conditional_rules:
            if self._evaluate_conditions(rule.conditions, patient_state):
                mandatory.update(rule.mandatory_actions)

        # Remove completed actions
        return [a for a in mandatory if a not in completed_actions]

    def get_forbidden_for_state(
        self,
        patient_state: Dict[str, Any]
    ) -> List[str]:
        """환자 상태에 따른 금지 액션 반환"""
        forbidden = set(self.always_forbidden)

        for rule in self.conditional_rules:
            if self._evaluate_conditions(rule.conditions, patient_state):
                forbidden.update(rule.forbidden_actions)

        # Add contraindication-based forbidden actions
        allergies = patient_state.get("allergies", [])
        comorbidities = patient_state.get("comorbidities", [])

        for condition in allergies + comorbidities:
            condition_lower = condition.lower()
            for key, forbidden_actions in self.contraindication_map.items():
                if key.lower() in condition_lower:
                    forbidden.update(forbidden_actions)

        return list(forbidden)

    def get_recommended_for_state(
        self,
        patient_state: Dict[str, Any],
        completed_actions: Set[str]
    ) -> List[str]:
        """환자 상태에 따른 권장 액션 반환"""
        recommended = set(self.always_recommended)

        for rule in self.conditional_rules:
            if self._evaluate_conditions(rule.conditions, patient_state):
                recommended.update(rule.recommended_actions)

        return [a for a in recommended if a not in completed_actions]

    def check_sequence_violation(
        self,
        action_id: str,
        completed_actions: Set[str]
    ) -> Optional[str]:
        """시퀀스 위반 체크, 위반 시 필요한 선행 액션 반환"""
        for seq in self.sequence_rules:
            if seq.get("after") == action_id:
                required_before = seq.get("before")
                if required_before and required_before not in completed_actions:
                    return required_before
        return None

    def _evaluate_conditions(
        self,
        conditions: List[Dict[str, Any]],
        patient_state: Dict[str, Any]
    ) -> bool:
        """조건 평가"""
        if not conditions:
            return True

        for condition in conditions:
            variable = condition.get("variable", "")
            operator = condition.get("operator", "equals")
            value = condition.get("value")

            # Get actual value from patient state
            actual = self._get_nested_value(patient_state, variable)
            if actual is None:
                continue  # Skip if variable not found

            # Evaluate
            if not self._compare(actual, operator, value):
                return False

        return True

    def _get_nested_value(self, data: Dict[str, Any], path: str) -> Any:
        """중첩된 딕셔너리에서 값 추출"""
        keys = path.split(".")
        current = data
        for key in keys:
            if isinstance(current, dict):
                current = current.get(key)
            else:
                return None
        return current

    def _compare(self, actual: Any, operator: str, expected: Any) -> bool:
        """비교 연산"""
        try:
            if operator == "equals" or operator == "==":
                return actual == expected
            elif operator == "less_than" or operator == "<":
                return float(actual) < float(expected)
            elif operator == "greater_than" or operator == ">":
                return float(actual) > float(expected)
            elif operator == "less_equal" or operator == "<=":
                return float(actual) <= float(expected)
            elif operator == "greater_equal" or operator == ">=":
                return float(actual) >= float(expected)
            elif operator == "contains":
                return str(expected).lower() in str(actual).lower()
            elif operator == "in":
                return actual in expected
            else:
                return actual == expected
        except (ValueError, TypeError):
            return False


class ConstraintSynthesizer:
    """
    LLM 기반 제약 조건 합성기

    파싱된 CPG에서 환자 상태 기반 조건부 규칙을 생성합니다.
    """

    def __init__(self, llm_provider: BaseLLMProvider):
        self.llm_provider = llm_provider
        self._cache: Dict[str, SynthesizedConstraints] = {}

    def synthesize(
        self,
        parsed_guideline: ParsedGuideline,
        patient_context: Optional[Dict[str, Any]] = None
    ) -> SynthesizedConstraints:
        """
        파싱된 가이드라인에서 제약 조건 합성

        Args:
            parsed_guideline: 파싱된 CPG
            patient_context: 환자 컨텍스트 (옵션)

        Returns:
            SynthesizedConstraints: 합성된 제약 조건
        """
        cache_key = parsed_guideline.guideline_id
        if cache_key in self._cache and patient_context is None:
            return self._cache[cache_key]

        # Step 1: 기본 제약 조건 추출
        constraints = self._extract_base_constraints(parsed_guideline)

        # Step 2: 조건부 규칙 생성
        conditional_rules = self._generate_conditional_rules(
            parsed_guideline, patient_context
        )
        constraints.conditional_rules = conditional_rules

        # Step 3: 금기 사항 매핑
        constraints.contraindication_map = self._build_contraindication_map(
            parsed_guideline
        )

        if patient_context is None:
            self._cache[cache_key] = constraints

        return constraints

    def _extract_base_constraints(
        self,
        parsed: ParsedGuideline
    ) -> SynthesizedConstraints:
        """기본 제약 조건 추출"""
        always_mandatory = []
        always_forbidden = []
        always_recommended = []
        action_deadlines = {}
        action_priorities = {}
        sequence_rules = []

        for rec in parsed.recommendations:
            action_id = rec.action_id

            # Strength-based classification
            if rec.strength == RecommendationStrength.STRONG:
                always_mandatory.append(action_id)
                action_priorities[action_id] = 90
            elif rec.strength == RecommendationStrength.AGAINST:
                always_forbidden.append(action_id)
            elif rec.strength == RecommendationStrength.MODERATE:
                always_recommended.append(action_id)
                action_priorities[action_id] = 70
            else:
                always_recommended.append(action_id)
                action_priorities[action_id] = 50

            # Timing constraints
            if rec.deadline_minutes:
                action_deadlines[action_id] = rec.deadline_minutes

            # Sequence rules from prerequisites
            for prereq in rec.prerequisites:
                sequence_rules.append({
                    "before": prereq,
                    "after": action_id,
                    "reason": f"Prerequisite for {action_id}"
                })

        # Add parsed sequence rules
        sequence_rules.extend(parsed.sequence_rules)

        return SynthesizedConstraints(
            domain=parsed.domain,
            source_guideline=parsed.source,
            always_mandatory=always_mandatory,
            always_forbidden=always_forbidden,
            always_recommended=always_recommended,
            sequence_rules=sequence_rules,
            action_deadlines=action_deadlines,
            action_priorities=action_priorities
        )

    def _generate_conditional_rules(
        self,
        parsed: ParsedGuideline,
        patient_context: Optional[Dict[str, Any]]
    ) -> List[ConditionalRule]:
        """조건부 규칙 생성"""

        # 도메인별 기본 조건부 규칙 템플릿
        domain_templates = self._get_domain_templates(parsed.domain)

        # LLM으로 추가 규칙 생성
        llm_rules = self._generate_rules_with_llm(parsed, patient_context)

        return domain_templates + llm_rules

    def _get_domain_templates(self, domain: str) -> List[ConditionalRule]:
        """도메인별 기본 조건부 규칙 템플릿"""
        templates = []

        if "sepsis" in domain.lower():
            # Septic shock: MAP < 65
            templates.append(ConditionalRule(
                rule_id="septic_shock_hypotension",
                description="Septic shock with hypotension",
                conditions=[
                    {"variable": "vitals.map_mmhg", "operator": "<", "value": 65}
                ],
                mandatory_actions=[
                    "give_crystalloid_30ml_kg",
                    "start_vasopressor_norepinephrine"
                ],
                deadline_minutes=60,
                priority=95
            ))

            # Elevated lactate
            templates.append(ConditionalRule(
                rule_id="elevated_lactate",
                description="Elevated lactate requiring remeasurement",
                conditions=[
                    {"variable": "labs.lactate", "operator": ">", "value": 2}
                ],
                mandatory_actions=["remeasure_lactate"],
                deadline_minutes=240,
                priority=70
            ))

        elif "stroke" in domain.lower():
            # Ischemic stroke - tPA eligible
            templates.append(ConditionalRule(
                rule_id="tpa_eligible",
                description="tPA eligible ischemic stroke",
                conditions=[
                    {"variable": "working_diagnosis", "operator": "contains", "value": "ischemic"},
                    {"variable": "time_since_onset_minutes", "operator": "<", "value": 270}
                ],
                mandatory_actions=["give_alteplase"],
                forbidden_actions=["give_anticoagulation"],
                deadline_minutes=60,
                priority=95
            ))

            # Hemorrhagic stroke
            templates.append(ConditionalRule(
                rule_id="hemorrhagic_stroke",
                description="Hemorrhagic stroke - reverse anticoagulation",
                conditions=[
                    {"variable": "working_diagnosis", "operator": "contains", "value": "hemorrhagic"}
                ],
                mandatory_actions=["reverse_anticoagulation", "control_blood_pressure"],
                forbidden_actions=["give_alteplase", "give_anticoagulation"],
                priority=95
            ))

            # LVO with extended window (6-24h)
            templates.append(ConditionalRule(
                rule_id="lvo_extended_window",
                description="LVO with large vessel occlusion: thrombectomy up to 24h",
                conditions=[
                    {"variable": "nihss", "operator": ">=", "value": 6},
                    {"variable": "lvo_confirmed", "operator": "==", "value": True}
                ],
                mandatory_actions=[
                    "confirm_favorable_perfusion_imaging",
                    "activate_neurointerventional_team"
                ],
                forbidden_actions=["give_alteplase"],
                deadline_minutes=90,
                priority=90
            ))

        elif "heart_failure" in domain.lower() or "hf" in domain.lower():
            # Cardiogenic shock
            templates.append(ConditionalRule(
                rule_id="cardiogenic_shock",
                description="Cardiogenic shock management",
                conditions=[
                    {"variable": "vitals.sbp_mmhg", "operator": "<", "value": 90}
                ],
                mandatory_actions=["start_inotropes", "consider_mechanical_support"],
                forbidden_actions=["give_beta_blocker"],
                priority=95
            ))

            # ADHF Warm-Wet profile
            templates.append(ConditionalRule(
                rule_id="adhf_warm_wet",
                description="ADHF Warm-Wet: IV diuretics, NO inotropes",
                conditions=[
                    {"variable": "hemodynamic_profile", "operator": "contains", "value": "warm_wet"}
                ],
                mandatory_actions=["iv_diuretics", "fluid_restrict"],
                forbidden_actions=["give_iv_inotropes"],
                deadline_minutes=30,
                priority=90
            ))

            # ADHF Cold-Dry profile
            templates.append(ConditionalRule(
                rule_id="adhf_cold_dry",
                description="ADHF Cold-Dry: Careful fluid challenge, NO diuretics",
                conditions=[
                    {"variable": "hemodynamic_profile", "operator": "contains", "value": "cold_dry"}
                ],
                mandatory_actions=["careful_fluid_challenge", "hemodynamic_monitoring"],
                forbidden_actions=["give_diuretics", "iv_diuretics"],
                priority=90
            ))

            # HFrEF GDMT (EF <= 40%)
            templates.append(ConditionalRule(
                rule_id="hfref_gdmt",
                description="HFrEF: All 4 pillars of GDMT",
                conditions=[
                    {"variable": "lvef", "operator": "<=", "value": 40}
                ],
                mandatory_actions=[
                    "initiate_ace_or_arb_or_arni",
                    "initiate_beta_blocker",
                    "initiate_mra",
                    "initiate_sglt2i"
                ],
                forbidden_actions=[
                    "give_nsaid", "give_diltiazem",
                    "give_verapamil", "give_thiazolidinedione"
                ],
                priority=85
            ))

        elif "chest_pain" in domain.lower() or "stemi" in domain.lower():
            # STEMI
            templates.append(ConditionalRule(
                rule_id="stemi_pci",
                description="STEMI requiring PCI",
                conditions=[
                    {"variable": "working_diagnosis", "operator": "contains", "value": "stemi"}
                ],
                mandatory_actions=[
                    "activate_cath_lab",
                    "give_aspirin_loading",
                    "give_p2y12_inhibitor",
                    "give_anticoagulation"
                ],
                deadline_minutes=90,
                priority=95
            ))

            # RV infarct
            templates.append(ConditionalRule(
                rule_id="rv_infarct",
                description="RV infarct - avoid preload reduction",
                conditions=[
                    {"variable": "ecg_findings", "operator": "contains", "value": "inferior"},
                    {"variable": "ecg_v4r", "operator": "contains", "value": "st_elevation"}
                ],
                forbidden_actions=["give_nitroglycerin", "give_diuretics"],
                mandatory_actions=["give_iv_fluids"],
                priority=95
            ))

        elif "dka" in domain.lower() or "ketoacidosis" in domain.lower():
            # Hypokalemia Trap (CRITICAL - K+ < 3.3)
            templates.append(ConditionalRule(
                rule_id="dka_hypokalemia_trap",
                description="K+ < 3.3: Insulin FORBIDDEN, potassium MANDATORY",
                conditions=[
                    {"variable": "labs.potassium", "operator": "<", "value": 3.3}
                ],
                mandatory_actions=[
                    "give_potassium_iv",
                    "hold_insulin_until_k_above_3.3"
                ],
                forbidden_actions=[
                    "start_insulin_infusion",
                    "give_insulin_bolus"
                ],
                deadline_minutes=30,
                priority=99
            ))

            # K+ adequate - insulin safe
            templates.append(ConditionalRule(
                rule_id="dka_insulin_safe",
                description="K+ >= 3.3: Insulin infusion can start",
                conditions=[
                    {"variable": "labs.potassium", "operator": ">=", "value": 3.3}
                ],
                mandatory_actions=[
                    "start_insulin_infusion",
                    "monitor_glucose_hourly",
                    "monitor_potassium_q2h"
                ],
                deadline_minutes=60,
                priority=85
            ))

            # CKD + Hyperkalemia Trap (K+ > 5.5)
            templates.append(ConditionalRule(
                rule_id="dka_ckd_hyperkalemia_trap",
                description="K+ > 5.5: Potassium FORBIDDEN, treat hyperkalemia",
                conditions=[
                    {"variable": "labs.potassium", "operator": ">", "value": 5.5}
                ],
                mandatory_actions=[
                    "treat_hyperkalemia",
                    "order_ecg",
                    "start_insulin_infusion"
                ],
                forbidden_actions=[
                    "give_potassium_iv",
                    "add_potassium_to_iv"
                ],
                priority=95
            ))

            # Euglycemic DKA (SGLT2 trap)
            templates.append(ConditionalRule(
                rule_id="dka_euglycemic_sglt2_trap",
                description="SGLT2-associated euglycemic DKA: stop SGLT2, add dextrose",
                conditions=[
                    {"variable": "medications.sglt2_inhibitor", "operator": "==", "value": True}
                ],
                mandatory_actions=[
                    "stop_sglt2_inhibitor",
                    "order_lab_ketones",
                    "start_dextrose_containing_iv"
                ],
                forbidden_actions=[
                    "continue_sglt2_inhibitor"
                ],
                priority=93
            ))

            # Severe DKA (pH < 7.0)
            templates.append(ConditionalRule(
                rule_id="dka_severe_acidosis",
                description="Severe DKA (pH < 7.0): ICU, cardiac monitoring",
                conditions=[
                    {"variable": "labs.ph", "operator": "<", "value": 7.0}
                ],
                mandatory_actions=[
                    "admit_to_icu",
                    "continuous_cardiac_monitoring",
                    "start_iv_fluid_ns"
                ],
                forbidden_actions=[
                    "discharge_home",
                    "admit_to_ward"
                ],
                priority=95
            ))

        elif "aki" in domain.lower() or "kidney" in domain.lower():
            # Stage 3 AKI - urgent nephrology
            templates.append(ConditionalRule(
                rule_id="aki_stage3_urgent",
                description="AKI Stage 3: Urgent nephrology, assess RRT",
                conditions=[
                    {"variable": "labs.creatinine_ratio", "operator": ">=", "value": 3.0}
                ],
                mandatory_actions=[
                    "urgent_nephrology_consult",
                    "assess_rrt_need",
                    "monitor_potassium_q6h"
                ],
                forbidden_actions=[
                    "give_nsaid",
                    "give_contrast",
                    "give_potassium"
                ],
                deadline_minutes=60,
                priority=95
            ))

            # Emergency RRT indication (K+ > 6.5)
            templates.append(ConditionalRule(
                rule_id="aki_emergency_rrt",
                description="K+ > 6.5 with AKI: Emergency RRT + temporizing",
                conditions=[
                    {"variable": "labs.potassium", "operator": ">", "value": 6.5}
                ],
                mandatory_actions=[
                    "initiate_emergency_rrt",
                    "treat_hyperkalemia_temporizing",
                    "ecg_for_hyperkalemia"
                ],
                forbidden_actions=[
                    "give_potassium"
                ],
                deadline_minutes=30,
                priority=100
            ))

            # Contrast-induced AKI prevention (eGFR < 30)
            templates.append(ConditionalRule(
                rule_id="aki_contrast_prevention",
                description="eGFR < 30: Alternative imaging, minimize contrast",
                conditions=[
                    {"variable": "labs.egfr", "operator": "<", "value": 30}
                ],
                mandatory_actions=[
                    "consider_alternative_imaging",
                    "iv_hydration_if_proceeding"
                ],
                forbidden_actions=[
                    "give_high_osmolar_contrast"
                ],
                priority=90
            ))

            # Hyperkalemia with AKI (K+ > 5.5)
            templates.append(ConditionalRule(
                rule_id="aki_hyperkalemia",
                description="K+ > 5.5 with AKI: ECG + treat, potassium FORBIDDEN",
                conditions=[
                    {"variable": "labs.potassium", "operator": ">", "value": 5.5}
                ],
                mandatory_actions=[
                    "ecg_for_hyperkalemia",
                    "treat_hyperkalemia_temporizing"
                ],
                forbidden_actions=[
                    "give_potassium"
                ],
                priority=90
            ))

        return templates

    def _generate_rules_with_llm(
        self,
        parsed: ParsedGuideline,
        patient_context: Optional[Dict[str, Any]]
    ) -> List[ConditionalRule]:
        """LLM으로 추가 조건부 규칙 생성"""

        # 추천사항 요약
        rec_summary = "\n".join([
            f"- {rec.action_id}: {rec.text[:100]}..."
            for rec in parsed.recommendations[:20]
        ])

        prompt = f"""Based on these {parsed.domain} clinical guidelines, generate conditional rules.

## Recommendations
{rec_summary}

## Task
Generate JSON conditional rules for patient-state-dependent actions.
Each rule should specify:
1. Conditions (vital signs, lab values, diagnosis)
2. Mandatory actions when conditions are met
3. Forbidden actions when conditions are met
4. Priority (1-100, higher = more urgent)

## Output Format
{{
    "rules": [
        {{
            "rule_id": "rule_name",
            "description": "When to apply this rule",
            "conditions": [
                {{"variable": "vitals.sbp_mmhg", "operator": "<", "value": 90}}
            ],
            "mandatory_actions": ["action_id_1"],
            "recommended_actions": ["action_id_2"],
            "forbidden_actions": ["action_id_3"],
            "deadline_minutes": 60,
            "priority": 90
        }}
    ]
}}

Generate 3-5 important conditional rules."""

        messages = [
            LLMMessage(role="system", content="You are a clinical decision support system designer."),
            LLMMessage(role="user", content=prompt)
        ]

        schema = {
            "type": "object",
            "properties": {
                "rules": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "rule_id": {"type": "string"},
                            "description": {"type": "string"},
                            "conditions": {"type": "array"},
                            "mandatory_actions": {"type": "array"},
                            "recommended_actions": {"type": "array"},
                            "forbidden_actions": {"type": "array"},
                            "deadline_minutes": {"type": "integer"},
                            "priority": {"type": "integer"}
                        }
                    }
                }
            }
        }

        try:
            result = self.llm_provider.complete_json(messages, schema)
            rules_data = result.get("rules", [])

            rules = []
            for rule_data in rules_data:
                rule = ConditionalRule(
                    rule_id=rule_data.get("rule_id", "unknown"),
                    description=rule_data.get("description", ""),
                    conditions=rule_data.get("conditions", []),
                    mandatory_actions=rule_data.get("mandatory_actions", []),
                    recommended_actions=rule_data.get("recommended_actions", []),
                    forbidden_actions=rule_data.get("forbidden_actions", []),
                    deadline_minutes=rule_data.get("deadline_minutes"),
                    priority=rule_data.get("priority", 50)
                )
                rules.append(rule)

            return rules

        except Exception as e:
            logger.warning(f"LLM rule generation failed: {e}")
            return []

    def _build_contraindication_map(
        self,
        parsed: ParsedGuideline
    ) -> Dict[str, List[str]]:
        """금기 사항 매핑 생성"""
        contra_map = {}

        # 추천사항에서 금기 사항 추출
        for rec in parsed.recommendations:
            for contra in rec.contraindications:
                contra_lower = contra.lower()
                if contra_lower not in contra_map:
                    contra_map[contra_lower] = []
                contra_map[contra_lower].append(rec.action_id)

        # 공통 금기 사항 추가
        common_contras = {
            # Drug allergies
            "penicillin_allergy": ["give_penicillin", "give_ampicillin", "give_amoxicillin"],
            "nsaid_allergy": ["give_nsaid", "give_ibuprofen", "give_aspirin"],
            "sulfa_allergy": ["give_sulfonamide", "give_trimethoprim_sulfamethoxazole"],
            # Renal disease
            "ckd_stage_4": ["give_nsaid", "give_contrast_without_precaution"],
            "ckd_stage_5": ["give_nsaid", "give_aminoglycoside"],
            # Bleeding
            "gi_bleeding": ["give_anticoagulation", "give_aspirin"],
            "active_bleeding": ["give_anticoagulation", "give_thrombolytic"],
            # DKA-specific
            "hypokalemia": ["start_insulin_infusion", "give_insulin_bolus"],
            "hyperkalemia": ["give_potassium_iv", "add_potassium_to_iv"],
            "dka": ["continue_sglt2_inhibitor"],
            # Heart Failure-specific
            "heart_failure": ["give_nsaid", "give_aggressive_fluids"],
            "hfref": ["give_nsaid", "give_diltiazem", "give_verapamil",
                      "give_thiazolidinedione"],
            "cardiogenic_shock": ["give_beta_blocker", "initiate_beta_blocker",
                                  "give_high_dose_beta_blocker"],
            "adhf_cold_dry": ["give_diuretics", "iv_diuretics"],
            # AKI-specific
            "aki_stage_3": ["give_nsaid", "give_contrast",
                            "give_aminoglycoside", "give_potassium"],
            "egfr_below_30": ["give_contrast", "give_high_osmolar_contrast"],
        }

        for condition, actions in common_contras.items():
            if condition not in contra_map:
                contra_map[condition] = []
            contra_map[condition].extend(actions)

        return contra_map
