"""
LLM-Assist Agent: Semantic Layer 기반 하이브리드 에이전트

rule_based의 정확도와 LLM의 확장성을 결합합니다.

아키텍처:
┌─────────────────────────────────────────────────────────────┐
│                     LLM-Assist Agent                         │
├─────────────────────────────────────────────────────────────┤
│  1. CPG Parser                                               │
│     - 새 도메인 가이드라인 자동 파싱                           │
│                                                              │
│  2. Constraint Synthesizer                                   │
│     - 동적 규칙 생성 (Decision Table 대체)                    │
│                                                              │
│  3. Action Normalizer                                        │
│     - LLM 출력 → 유효한 액션 ID                              │
│                                                              │
│  4. Semantic Validator                                       │
│     - 임상 안전성 검증                                        │
│                                                              │
│  5. LLM Decision Engine                                      │
│     - 환자 상태 기반 행동 결정                                │
└─────────────────────────────────────────────────────────────┘

설계 목표:
- rule_based 수준의 정확도 (90%+)
- 새 도메인에 대한 자동 확장
- 수동 Decision Table 작성 불필요
"""

import logging
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set
from pathlib import Path

from cga_bench.agent_runner.base_agent import BaseAgent, AgentConfig, AgentMetrics
from cga_bench.agent_runner.llm_provider import (
    BaseLLMProvider,
    LLMMessage,
    LLMConfig,
    LLMBackend,
    LLMProviderFactory,
    CLINICAL_SYSTEM_PROMPT,
    ACTION_RECOMMENDATION_SCHEMA,
)
from cga_bench.cpg_model.schemas.base import Action, ActionType
from cga_bench.scenario_engine.environment import Observation

from .cpg_parser import CPGParser, ParsedGuideline
from .constraint_synthesizer import (
    ConstraintSynthesizer,
    SynthesizedConstraints,
)
from .action_normalizer import SemanticActionNormalizer
from .semantic_validator import SemanticValidator

logger = logging.getLogger(__name__)


@dataclass
class LLMAssistConfig(AgentConfig):
    """LLM-Assist 에이전트 설정"""
    agent_type: str = "llm_assist"

    # LLM 설정
    llm_backend: LLMBackend = LLMBackend.VLLM
    llm_model: str = "Qwen/Qwen3-30B-A3B-Instruct-2507"
    base_url: Optional[str] = "http://localhost:8013/v1"
    temperature: float = 0.1

    # 도메인 설정
    domain: str = "general"  # Will be auto-detected
    cpg_sources_path: Optional[str] = None

    # 기능 토글
    use_semantic_validation: bool = True
    use_constraint_synthesis: bool = True
    use_action_normalization: bool = True

    # 성능 설정
    max_actions_per_step: int = 5
    cache_parsed_guidelines: bool = True

    # Strict mode: LLM 없으면 에러 발생 (False면 rule-based fallback 허용)
    strict_mode: bool = False


class LLMAssistAgent(BaseAgent):
    """
    LLM-Assist 에이전트

    Semantic Layer를 사용하여 새로운 도메인에도 자동 적응합니다.

    작동 방식:
    1. 첫 호출 시 도메인에 맞는 CPG 파싱 및 규칙 합성
    2. 환자 상태 기반으로 LLM이 액션 제안
    3. 시맨틱 정규화로 유효한 액션 ID 확보
    4. 시맨틱 검증으로 안전성 확인
    5. 승인된 액션만 반환
    """

    def __init__(
        self,
        config: LLMAssistConfig,
        llm_provider: Optional[BaseLLMProvider] = None
    ):
        super().__init__(config)
        self.assist_config = config

        # LLM Provider 초기화
        if llm_provider:
            self.llm_provider = llm_provider
        else:
            llm_config = LLMConfig(
                backend=config.llm_backend,
                model=config.llm_model,
                base_url=config.base_url,
                temperature=config.temperature,
                seed=config.llm_seed,
            )
            self.llm_provider = LLMProviderFactory.create(llm_config)

        # Semantic Layer 컴포넌트 초기화
        self.cpg_parser = CPGParser(self.llm_provider)
        self.constraint_synthesizer = ConstraintSynthesizer(self.llm_provider)
        self.action_normalizer = SemanticActionNormalizer(
            self.llm_provider,
            use_llm_fallback=True,
            strict_mode=config.strict_mode
        )
        self.semantic_validator = SemanticValidator(
            self.llm_provider,
            use_llm_validation=config.use_semantic_validation,
            strict_mode=config.strict_mode
        )

        # 상태
        self._action_history: List[Action] = []
        self._parsed_guidelines: Dict[str, ParsedGuideline] = {}
        self._synthesized_constraints: Dict[str, SynthesizedConstraints] = {}
        self._current_domain: Optional[str] = None

    def reset(self):
        """에이전트 상태 리셋"""
        self._action_history = []
        self.metrics = AgentMetrics()
        # 가이드라인 캐시는 유지 (재파싱 비용 절감)

    def decide(self, observation: Observation) -> List[Action]:
        """
        관측을 받아 행동 결정

        Args:
            observation: 환경 관측

        Returns:
            List[Action]: 검증된 액션 목록
        """
        state = observation.visible_state
        current_time = observation.timestamp_minutes
        completed_ids = {a.action_id for a in self._action_history}

        # Step 1: 도메인 감지 및 가이드라인 로드
        domain = self._detect_domain(state)
        constraints = self._get_or_synthesize_constraints(domain, state)

        # Step 2: 유효한 액션 목록 구성
        available_actions = self._get_available_actions(
            constraints, state, completed_ids
        )

        # Step 3: LLM으로 액션 생성
        proposed_actions = self._generate_actions_with_llm(
            state, current_time, completed_ids, available_actions, constraints
        )

        # Step 4: 액션 정규화
        normalized_actions = self._normalize_actions(
            proposed_actions, domain, state
        )

        # Step 5: 시맨틱 검증
        validation_result = self.semantic_validator.validate(
            normalized_actions,
            state,
            completed_ids,
            constraints,
            current_time
        )

        # Step 6: 승인된 액션만 반환
        approved_actions = [
            a for a in normalized_actions
            if a.action_id in validation_result.approved_actions
        ]

        # 누락된 필수 액션 추가
        for suggested in validation_result.suggested_additions[:2]:
            if suggested not in {a.action_id for a in approved_actions}:
                approved_actions.append(self._create_action(
                    suggested, current_time, "Mandatory action per guidelines"
                ))

        # 히스토리 업데이트
        self._action_history.extend(approved_actions)

        # 메트릭 업데이트
        self.metrics.total_llm_calls += 1
        self.metrics.total_tokens += self.llm_provider.get_total_tokens_from_last_call()

        return approved_actions[:self.assist_config.max_actions_per_step]

    def _detect_domain(self, state: Dict[str, Any]) -> str:
        """환자 상태에서 도메인 자동 감지"""
        diagnosis = state.get("working_diagnosis", "").lower()
        chief_complaint = state.get("chief_complaint", "").lower()
        combined = f"{diagnosis} {chief_complaint}"

        # 도메인 키워드 매칭
        domain_keywords = {
            "sepsis": ["sepsis", "septic", "infection", "fever", "lactate", "bacteremia"],
            "stroke": ["stroke", "tpa", "thrombectomy", "hemiparesis", "aphasia",
                       "nihss", "ischemic_stroke", "hemorrhagic"],
            "chest_pain": ["stemi", "nstemi", "acs", "chest pain", "troponin",
                           "myocardial", "inferior_mi", "anterior_mi"],
            "dka": ["dka", "ketoacidosis", "diabetic_ketoacidosis",
                    "anion_gap", "kussmaul", "euglycemic_dka",
                    "sglt2", "hyperglycemic_crisis"],
            "heart_failure": ["heart failure", "hf", "cardiogenic", "pulmonary edema",
                              "bnp", "hfref", "hfpef", "hfmref", "adhf",
                              "decompensated", "cardiogenic_shock",
                              "warm_wet", "cold_wet", "cold_dry"],
            "aki": ["aki", "acute kidney", "renal failure", "creatinine",
                    "oliguria", "anuria", "nephrotoxic", "contrast_nephropathy", "rrt"],
        }

        for domain, keywords in domain_keywords.items():
            if any(kw in combined for kw in keywords):
                self._current_domain = domain
                return domain

        return self.assist_config.domain or "general"

    def _get_or_synthesize_constraints(
        self,
        domain: str,
        state: Dict[str, Any]
    ) -> SynthesizedConstraints:
        """도메인에 대한 제약 조건 가져오기 또는 합성"""
        if domain in self._synthesized_constraints:
            return self._synthesized_constraints[domain]

        # 가이드라인 파싱 (캐시에 없으면)
        if domain not in self._parsed_guidelines:
            guideline = self._parse_or_load_guideline(domain)
            if guideline:
                self._parsed_guidelines[domain] = guideline

        # 제약 조건 합성
        if domain in self._parsed_guidelines:
            constraints = self.constraint_synthesizer.synthesize(
                self._parsed_guidelines[domain],
                patient_context=state
            )
        else:
            # 기본 제약 조건 사용
            constraints = self._get_default_constraints(domain)

        self._synthesized_constraints[domain] = constraints
        return constraints

    def _parse_or_load_guideline(self, domain: str) -> Optional[ParsedGuideline]:
        """가이드라인 파싱 또는 로드"""
        # 먼저 캐시된 파싱 결과 확인
        cache_path = Path(f"cpg_sources/{domain}_parsed_cache.json")
        if cache_path.exists() and self.assist_config.cache_parsed_guidelines:
            try:
                import json
                with open(cache_path) as f:
                    data = json.load(f)
                # Reconstruct ParsedGuideline from cache
                # (simplified - actual implementation would deserialize properly)
                logger.info(f"Loaded cached guideline for {domain}")
            except Exception as e:
                logger.warning(f"Failed to load cache: {e}")

        # CPG 소스 파일 찾기
        sources_path = Path(self.assist_config.cpg_sources_path or "cpg_sources")
        if sources_path.exists():
            for file in sources_path.glob("*.parsed.json"):
                if domain.lower() in file.name.lower():
                    try:
                        import json
                        with open(file) as f:
                            text = json.dumps(json.load(f))
                        return self.cpg_parser.parse_text(
                            text, domain, domain, source=file.name
                        )
                    except Exception as e:
                        logger.warning(f"Failed to parse {file}: {e}")

        return None

    def _get_default_constraints(self, domain: str) -> SynthesizedConstraints:
        """기본 제약 조건 반환"""
        return SynthesizedConstraints(
            domain=domain,
            source_guideline="default",
            always_mandatory=[],
            always_forbidden=[],
            always_recommended=[],
            conditional_rules=[],
            sequence_rules=[],
            action_deadlines={},
            action_priorities={},
            contraindication_map={}
        )

    def _get_available_actions(
        self,
        constraints: SynthesizedConstraints,
        state: Dict[str, Any],
        completed_ids: Set[str]
    ) -> List[str]:
        """사용 가능한 액션 목록 구성"""
        available = []

        # 필수 액션 (우선)
        mandatory = constraints.get_mandatory_for_state(state, completed_ids)
        available.extend(mandatory)

        # 권장 액션
        recommended = constraints.get_recommended_for_state(state, completed_ids)
        available.extend(recommended)

        # 도메인별 기본 액션
        domain_actions = self._get_domain_default_actions(constraints.domain)
        for action in domain_actions:
            if action not in available and action not in completed_ids:
                available.append(action)

        # 금지 액션 제외
        forbidden = constraints.get_forbidden_for_state(state)
        available = [a for a in available if a not in forbidden]

        return available

    def _get_domain_default_actions(self, domain: str) -> List[str]:
        """도메인별 기본 액션"""
        defaults = {
            "sepsis": [
                "order_lab_lactate", "order_lab_blood_culture", "give_broad_spectrum_antibiotics",
                "give_crystalloid_30ml_kg", "start_vasopressor_norepinephrine",
                "assess_infection_source", "assess_organ_dysfunction"
            ],
            "stroke": [
                # Core tPA eligibility actions
                "activate_stroke_team", "obtain_last_known_well_time", "perform_nihss",
                "check_glucose", "order_stat_ct_head", "establish_iv_access",
                "order_cbc_bmp_coag", "obtain_12_lead_ecg",
                # tPA administration
                "review_inclusion_criteria", "review_exclusion_criteria",
                "obtain_informed_consent", "give_alteplase_0.9mg_kg",
                # Thrombectomy consideration
                "consider_thrombectomy", "order_ct_angiography"
            ],
            "chest_pain": [
                # Core STEMI/NSTEMI actions
                "obtain_12_lead_ecg", "obtain_right_sided_ecg_v4r", "order_troponin",
                "give_aspirin", "give_p2y12_inhibitor", "give_anticoagulation",
                "activate_cath_lab", "assess_vital_signs", "obtain_chest_pain_history",
                # RV infarct specific
                "start_iv_fluid_bolus"
            ],
            "heart_failure": [
                # Diagnostics
                "order_bnp", "order_bnp_or_ntprobnp", "order_echocardiogram",
                "order_chest_xray", "assess_volume_status", "assess_hemodynamic_profile",
                # GDMT (HFrEF)
                "initiate_ace_or_arb_or_arni", "initiate_beta_blocker",
                "initiate_mra", "initiate_sglt2i",
                # ADHF
                "iv_diuretics", "fluid_restrict", "give_diuretics",
                "consider_inotropes", "hemodynamic_monitoring",
                # Cardiogenic shock
                "vasopressor_support", "inotrope_support",
                "mechanical_circulatory_support_evaluation"
            ],
            "aki": [
                # CPG mandatory actions
                "check_baseline_egfr", "assess_hydration_status", "review_risk_factors",
                # Therapeutic actions
                "initiate_iv_fluid", "hold_nephrotoxic_medications",
                "use_lowest_contrast_dose", "check_current_medications",
                # Consults
                "consult_nephrology", "urgent_nephrology_consult",
                # RRT pathway
                "assess_rrt_need", "initiate_emergency_rrt",
                "treat_hyperkalemia_temporizing",
                # Monitoring
                "monitor_potassium_q6h", "monitor_creatinine_q6h",
                # Contrast prevention
                "consider_alternative_imaging"
            ],
            "dka": [
                # Initial assessment
                "assess_vital_signs", "assess_mental_status", "establish_iv_access",
                # Labs
                "order_lab_glucose", "order_lab_bmp", "order_lab_ketones",
                "order_lab_abg", "order_lab_creatinine",
                # IV Fluid
                "start_iv_fluid_ns",
                # Insulin (requires K+ >= 3.3)
                "start_insulin_infusion",
                # Potassium management
                "give_potassium_iv", "hold_insulin_until_k_above_3.3",
                # Monitoring
                "monitor_glucose_hourly", "monitor_potassium_q2h",
                # SGLT2 (euglycemic DKA)
                "stop_sglt2_inhibitor",
                # Resolution
                "assess_anion_gap_closure", "start_subcutaneous_insulin",
                "overlap_iv_insulin_2h",
                # Disposition
                "admit_to_icu", "continuous_cardiac_monitoring"
            ],
        }
        return defaults.get(domain, [])

    def _generate_actions_with_llm(
        self,
        state: Dict[str, Any],
        current_time: float,
        completed_ids: Set[str],
        available_actions: List[str],
        constraints: SynthesizedConstraints
    ) -> List[Action]:
        """LLM으로 액션 생성"""
        # 환자 상태 요약
        patient_summary = self._format_patient_state(state)

        # 완료된 액션
        completed_str = ", ".join(completed_ids) if completed_ids else "None"

        # 사용 가능한 액션 (우선순위 표시)
        mandatory = constraints.get_mandatory_for_state(state, completed_ids)
        actions_str = "## Available Actions\n"
        actions_str += "**MANDATORY (complete first):**\n"
        for action in available_actions:
            if action in mandatory:
                deadline = constraints.action_deadlines.get(action)
                deadline_str = f" (deadline: {deadline}m)" if deadline else ""
                actions_str += f"  ★ {action}{deadline_str}\n"

        actions_str += "\n**Recommended:**\n"
        for action in available_actions:
            if action not in mandatory:
                actions_str += f"  ○ {action}\n"

        # 금지 액션
        forbidden = constraints.get_forbidden_for_state(state)
        if forbidden:
            actions_str += "\n**FORBIDDEN (do NOT select):**\n"
            for action in forbidden[:5]:
                actions_str += f"  ⛔ {action}\n"

        prompt = f"""## Patient State
{patient_summary}

## Time Since Arrival
{current_time} minutes

## Completed Actions
{completed_str}

{actions_str}

## Task
Based on the patient state and clinical guidelines, recommend the next clinical actions.

CRITICAL INSTRUCTIONS:
1. PRIORITIZE MANDATORY actions (marked with ★)
2. NEVER select FORBIDDEN actions (marked with ⛔)
3. Use EXACT action_id from the available list
4. Maximum 3-5 actions per response
5. Include clinical justification for each action

Respond with JSON:
{{
    "actions": [
        {{
            "action_id": "exact_action_id",
            "action_type": "order_lab|give_medication|order_imaging|assess|consult",
            "args": {{}},
            "justification": "clinical reasoning"
        }}
    ],
    "reasoning": "overall clinical reasoning"
}}"""

        messages = [
            LLMMessage(role="system", content=CLINICAL_SYSTEM_PROMPT),
            LLMMessage(role="user", content=prompt)
        ]

        try:
            result = self.llm_provider.complete_json(messages, ACTION_RECOMMENDATION_SCHEMA)

            actions = []
            actions_data = result.get("actions", []) if isinstance(result, dict) else result

            for action_data in actions_data:
                action_id = action_data.get("action_id", "")
                if isinstance(action_id, list):
                    action_id = action_id[0] if action_id else ""
                action_id = str(action_id)

                if action_id in completed_ids:
                    continue

                action_type_str = action_data.get("action_type", "")
                if isinstance(action_type_str, list):
                    action_type_str = action_type_str[0] if action_type_str else ""

                actions.append(Action(
                    type=self._parse_action_type(action_type_str, action_id),
                    action_id=action_id,
                    args=action_data.get("args", {}),
                    timestamp_minutes=current_time,
                    justification=action_data.get("justification", "LLM recommendation")
                ))

            return actions

        except Exception as e:
            logger.warning(f"LLM action generation failed: {e}")
            # 폴백: 필수 액션만 반환
            return [
                self._create_action(action, current_time, "Mandatory per guidelines")
                for action in mandatory[:3]
            ]

    def _normalize_actions(
        self,
        actions: List[Action],
        domain: str,
        state: Dict[str, Any]
    ) -> List[Action]:
        """액션 정규화"""
        if not self.assist_config.use_action_normalization:
            return actions

        # 도메인별 유효 액션 등록
        if domain in self._parsed_guidelines:
            valid_actions = [
                rec.action_id
                for rec in self._parsed_guidelines[domain].recommendations
            ]
            self.action_normalizer.register_vocabulary(domain, valid_actions)

        normalized = []
        for action in actions:
            result = self.action_normalizer.normalize(
                action.action_id,
                domain,
                context=state
            )

            if result.confidence > 0.5:
                normalized.append(Action(
                    type=action.type,
                    action_id=result.normalized_action,
                    args=action.args,
                    timestamp_minutes=action.timestamp_minutes,
                    justification=action.justification
                ))
            else:
                # 낮은 신뢰도면 원본 유지
                normalized.append(action)

        return normalized

    def _format_patient_state(self, state: Dict[str, Any]) -> str:
        """환자 상태 포맷팅"""
        parts = []

        if state.get("chief_complaint"):
            parts.append(f"**Chief Complaint:** {state['chief_complaint']}")
        if state.get("working_diagnosis"):
            parts.append(f"**Diagnosis:** {state['working_diagnosis']}")

        vitals = state.get("vitals", {})
        if vitals:
            vital_strs = []
            if vitals.get("blood_pressure_systolic"):
                vital_strs.append(f"BP: {vitals['blood_pressure_systolic']}/{vitals.get('blood_pressure_diastolic', '?')}")
            if vitals.get("heart_rate"):
                vital_strs.append(f"HR: {vitals['heart_rate']}")
            if vitals.get("oxygen_saturation"):
                vital_strs.append(f"SpO2: {vitals['oxygen_saturation']}%")
            if vital_strs:
                parts.append(f"**Vitals:** {', '.join(vital_strs)}")

        if state.get("allergies"):
            parts.append(f"**Allergies:** {', '.join(state['allergies'])}")
        if state.get("comorbidities"):
            parts.append(f"**Comorbidities:** {', '.join(state['comorbidities'])}")

        return "\n".join(parts) if parts else "No patient data available"

    def _parse_action_type(self, action_type_str: str, action_id: str) -> ActionType:
        """액션 타입 파싱"""
        if isinstance(action_type_str, list):
            action_type_str = action_type_str[0] if action_type_str else ""
        action_type_str = str(action_type_str).lower()

        type_map = {
            "order_lab": ActionType.ORDER_LAB,
            "order_imaging": ActionType.ORDER_IMAGING,
            "give_medication": ActionType.GIVE_MEDICATION,
            "consult": ActionType.CONSULT,
            "assess": ActionType.REASSESS,
        }

        if action_type_str in type_map:
            return type_map[action_type_str]

        # 키워드 기반 추론
        combined = f"{action_type_str} {action_id}".lower()
        if any(kw in combined for kw in ["lab", "measure", "order_", "check"]):
            return ActionType.ORDER_LAB
        if any(kw in combined for kw in ["imaging", "xray", "ct", "ecg", "echo"]):
            return ActionType.ORDER_IMAGING
        if any(kw in combined for kw in ["give", "administer", "start", "medication"]):
            return ActionType.GIVE_MEDICATION
        if any(kw in combined for kw in ["consult", "activate", "call"]):
            return ActionType.CONSULT

        return ActionType.REASSESS

    def _create_action(
        self,
        action_id: str,
        timestamp: float,
        justification: str
    ) -> Action:
        """액션 생성 헬퍼"""
        return Action(
            type=self._parse_action_type("", action_id),
            action_id=action_id,
            args={},
            timestamp_minutes=timestamp,
            justification=justification
        )

    def get_semantic_layer_status(self) -> Dict[str, Any]:
        """시맨틱 레이어 상태 반환"""
        return {
            "current_domain": self._current_domain,
            "parsed_guidelines": list(self._parsed_guidelines.keys()),
            "synthesized_constraints": list(self._synthesized_constraints.keys()),
            "action_history_count": len(self._action_history),
            "llm_calls": self.metrics.total_llm_calls,
            "tokens_used": self.metrics.total_tokens,
        }
