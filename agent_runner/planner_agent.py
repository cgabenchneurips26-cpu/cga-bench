"""
Planner Agent: 독립적 규칙 기반 계획 에이전트

CGA-Bench 명세에 따른 Planner Agent 구현:
- 독립적 Decision Table 기반 제약 조건 활용 (채점용 CPG-Engine 미사용)
- Constraint 검증 후 행동 선택
- LLM을 활용한 다단계 계획 수립

중요 설계 원칙 (NeurIPS 리뷰어 비판 대응):
- 채점용 CPG-Engine(cpg_engine/)에 직접 접근 불가
- 대신 agent_rules/의 독립적 Decision Table 사용
- 이 설계는 "평가 누수/치팅" 방지를 위한 것
"""

import logging
from typing import Dict, Any, List, Optional, Set
from dataclasses import dataclass, field
from enum import Enum

from cga_bench.agent_runner.base_agent import BaseAgent, AgentConfig, AgentMetrics
from cga_bench.agent_runner.llm_provider import (
    LLMConfig, LLMBackend, LLMMessage, BaseLLMProvider, LLMProviderFactory,
    CLINICAL_SYSTEM_PROMPT
)
from cga_bench.cpg_model.schemas.base import Action, ActionType, PatientState
from cga_bench.scenario_engine.environment import Observation

# 독립적 규칙 시스템 (채점용 CPG-Engine과 분리)
from cga_bench.agent_rules.decision_table import RuleBasedDecisionTable
from cga_bench.agent_rules.sepsis_rules import SepsisDecisionTable
from cga_bench.agent_rules.chest_pain_rules import ChestPainDecisionTable
from cga_bench.agent_rules.aki_rules import AKIDecisionTable
from cga_bench.agent_rules.heart_failure_rules import HeartFailureDecisionTable
from cga_bench.agent_rules.stroke_rules import StrokeDecisionTable
from cga_bench.agent_rules.dka_rules import DKADecisionTable

logger = logging.getLogger(__name__)


class PlanStatus(str, Enum):
    """계획 상태"""
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    BLOCKED = "blocked"


@dataclass
class PlannedAction:
    """계획된 행동"""
    action: Action
    priority: int  # 낮을수록 높은 우선순위
    status: PlanStatus = PlanStatus.PENDING
    dependencies: List[str] = field(default_factory=list)  # 의존하는 action_id들
    deadline_minutes: Optional[float] = None
    is_mandatory: bool = False
    source_recommendation: Optional[str] = None


@dataclass
class PlannerConfig(AgentConfig):
    """Planner 에이전트 설정"""
    agent_type: str = "planner"
    # 독립적 규칙 시스템 설정 (채점용 CPG-Engine 미사용)
    guideline_domain: str = "sepsis"  # sepsis, chest_pain, aki
    # Planning 설정
    plan_horizon_minutes: float = 60  # 계획 기간
    replan_threshold: float = 0.5  # 재계획 임계값
    # LLM 설정
    llm_backend: LLMBackend = LLMBackend.OPENAI
    llm_model: str = "gpt-4"
    temperature: float = 0.1
    use_llm: bool = True  # LLM 사용 여부


class PlannerAgent(BaseAgent):
    """
    Planner Agent: 독립적 규칙 기반 계획 에이전트

    RAG Agent와의 주요 차이점:
    1. 독립적 Decision Table 사용 (채점용 CPG-Engine 미사용)
    2. Constraint 검증: 금지 행동 필터링, 데드라인 확인
    3. LLM을 활용한 다단계 계획: 의존성 기반 행동 순서화

    중요 설계 원칙:
    - 채점용 CPG-Engine(cpg_engine/)에 직접 접근하지 않음
    - 대신 agent_rules/의 독립적 Decision Table 사용
    - Oracle과 동일한 분리 원칙 적용
    """

    def __init__(
        self,
        config: PlannerConfig,
        llm_provider: Optional[BaseLLMProvider] = None
    ):
        """
        Planner 에이전트 초기화

        Args:
            config: Planner 설정
            llm_provider: LLM 프로바이더 (선택)

        Note:
            cpg_engine 인자를 받지 않습니다. 이는 의도적인 설계입니다.
            채점용 엔진과 분리된 독립적 규칙 시스템만 사용합니다.
        """
        super().__init__(config)
        self.planner_config = config

        # 독립적 Decision Table 초기화 (채점용 CPG-Engine 아님)
        self.decision_table: Optional[RuleBasedDecisionTable] = None
        self._init_decision_table(config.guideline_domain)

        # LLM Provider 초기화
        self.llm_provider: Optional[BaseLLMProvider] = None
        if llm_provider:
            self.llm_provider = llm_provider
        elif config.use_llm:
            llm_config = LLMConfig(
                backend=config.llm_backend,
                model=config.llm_model,
                temperature=config.temperature,
                seed=config.llm_seed,
            )
            self.llm_provider = LLMProviderFactory.create(llm_config)

        # 계획 상태
        self._current_plan: List[PlannedAction] = []
        self._action_history: List[Action] = []
        self._completed_action_ids: Set[str] = set()

    # 도메인 -> Decision Table 클래스 매핑
    _DOMAIN_TABLE_MAP: Dict[str, type] = {
        "sepsis": SepsisDecisionTable,
        "ssc": SepsisDecisionTable,
        "septic_shock": SepsisDecisionTable,
        "ssc_sepsis": SepsisDecisionTable,
        "ssc_sepsis_hour1_bundle": SepsisDecisionTable,
        "chest_pain": ChestPainDecisionTable,
        "aha_chest_pain": ChestPainDecisionTable,
        "stemi": ChestPainDecisionTable,
        "nstemi": ChestPainDecisionTable,
        "aha_chest_pain_stemi": ChestPainDecisionTable,
        "aha_chest_pain_nstemi": ChestPainDecisionTable,
        "aki": AKIDecisionTable,
        "kdigo": AKIDecisionTable,
        "kidney": AKIDecisionTable,
        "kdigo_aki": AKIDecisionTable,
        "kdigo_contrast_aki": AKIDecisionTable,
        "heart_failure": HeartFailureDecisionTable,
        "hf": HeartFailureDecisionTable,
        "hfref": HeartFailureDecisionTable,
        "adhf": HeartFailureDecisionTable,
        "aha_heart_failure": HeartFailureDecisionTable,
        "cardiogenic_shock": HeartFailureDecisionTable,
        "stroke": StrokeDecisionTable,
        "aha_stroke": StrokeDecisionTable,
        "ischemic_stroke": StrokeDecisionTable,
        "tpa": StrokeDecisionTable,
        "thrombectomy": StrokeDecisionTable,
        "dka": DKADecisionTable,
        "ada_dka": DKADecisionTable,
        "dka_management": DKADecisionTable,
        "ada_dka_management": DKADecisionTable,
        "diabetic_ketoacidosis": DKADecisionTable,
    }

    def _init_decision_table(self, domain: str):
        """도메인별 독립적 Decision Table 초기화 (명시적 매핑 기반)"""
        domain_key = domain.lower().strip()
        table_cls = self._DOMAIN_TABLE_MAP.get(domain_key)

        if table_cls:
            self.decision_table = table_cls()
            logger.info(f"Planner initialized with {table_cls.__name__} for domain '{domain}'")
        else:
            logger.warning(
                f"Unknown domain '{domain}'. Defaulting to SepsisDecisionTable."
            )
            self.decision_table = SepsisDecisionTable()

    def reset(self):
        """에이전트 상태 리셋"""
        self._current_plan = []
        self._action_history = []
        self._completed_action_ids = set()
        self.metrics = AgentMetrics()
        if self.decision_table:
            self.decision_table.reset()

    def decide(self, observation: Observation) -> List[Action]:
        """
        LLM 기반 계획 및 행동 결정

        프로세스:
        1. 독립적 Decision Table에서 제약 조건 획득
        2. LLM으로 계획 수립 및 행동 선택
        3. 금지 행동 필터링

        Note:
            채점용 CPG-Engine을 사용하지 않습니다.
            대신 agent_rules/의 독립적 Decision Table을 사용합니다.
        """
        state = self._get_visible_state(observation)
        current_time = observation.timestamp_minutes

        # 1. 독립적 Decision Table에서 제약 조건 획득
        constraints = self._get_constraints_from_decision_table(state, current_time)

        # 2. LLM 사용 가능 시 LLM으로 행동 생성
        if self.llm_provider and self.planner_config.use_llm:
            try:
                actions = self._generate_actions_with_llm(
                    observation, state, current_time, constraints
                )
                # 토큰 사용량 추적 (Budget-matched 평가용)
                self.metrics.total_tokens += self.llm_provider.get_total_tokens_from_last_call()
                self.metrics.total_llm_calls += 1

                if actions:
                    # 금지 행동 필터링
                    forbidden_ids = {a.action_id for a in constraints.get("forbidden_actions", [])}
                    actions = [a for a in actions if a.action_id not in forbidden_ids]

                    self._action_history.extend(actions)
                    self._completed_action_ids.update(a.action_id for a in actions)
                    return actions
            except Exception as e:
                logger.warning(f"LLM action generation failed: {e}, falling back to rule-based")

        # 3. 규칙 기반 폴백
        # 현재 계획 업데이트 (완료된 행동 처리)
        self._update_plan_status(constraints)

        # 계획 수립 또는 재계획
        if self._should_replan(constraints):
            self._create_plan(state, current_time, constraints)

        # 다음 행동 선택
        actions = self._select_next_actions(current_time, constraints)

        # N3 Fix: LLM 호출 카운트는 실제 LLM 호출 시에만 증가 (line 211)
        return actions

    def _generate_actions_with_llm(
        self,
        observation: Observation,
        state: Dict[str, Any],
        current_time: float,
        constraints: Dict[str, Any]
    ) -> List[Action]:
        """LLM을 사용하여 행동 생성"""
        if self.llm_provider is None:
            raise RuntimeError("LLM provider not initialized")

        # 환자 상태 요약
        patient_summary = self._format_patient_state(state)

        # 완료된 행동 목록
        completed_str = ", ".join(self._completed_action_ids) if self._completed_action_ids else "None"

        # 추천 행동 (Decision Table에서)
        mandatory_actions = constraints.get("mandatory_actions", [])
        allowed_actions = constraints.get("allowed_actions", [])
        forbidden_actions = constraints.get("forbidden_actions", [])
        deadlines = constraints.get("deadlines", {})

        # Available Actions 포맷팅
        available_parts = ["## Available Actions\n"]
        available_parts.append("**MANDATORY (Must complete):**")
        for action in mandatory_actions:
            deadline = deadlines.get(action.action_id, "N/A")
            available_parts.append(f"- ★ {action.action_id} (deadline: {deadline}m)")

        available_parts.append("\n**RECOMMENDED:**")
        for action in allowed_actions[:10]:  # 상위 10개만
            available_parts.append(f"- {action.action_id}")

        available_parts.append("\n**FORBIDDEN (Do NOT select):**")
        for action in forbidden_actions[:5]:
            available_parts.append(f"- ⛔ {action.action_id}")

        available_actions_str = "\n".join(available_parts)

        # Build list of valid action IDs for validation
        valid_action_ids = set()
        for action in mandatory_actions:
            valid_action_ids.add(action.action_id)
        for action in allowed_actions:
            valid_action_ids.add(action.action_id)

        # 프롬프트 구성
        user_prompt = f"""## Current Patient State
{patient_summary}

## Time Since Arrival
{current_time} minutes

## Already Completed Actions
{completed_str}

{available_actions_str}

## Task
You are a clinical decision support AI using evidence-based guidelines.
Select actions ONLY from the Available Actions list above.

CRITICAL INSTRUCTIONS:
1. **COPY action_id EXACTLY** from the Available Actions list - do not paraphrase or modify
2. PRIORITIZE MANDATORY actions (marked with ★) - complete these FIRST
3. NEVER select FORBIDDEN actions (marked with ⛔)
4. Do NOT recommend actions already completed
5. Select up to {self.config.max_actions_per_step} actions

IMPORTANT: The action_id must be an EXACT match from the list above.
For example, if the list shows "order_bnp_or_ntprobnp", use exactly "order_bnp_or_ntprobnp" - not "order_bnp" or "bnp_test".

Respond with a JSON object:
{{
  "actions": [
    {{"action_id": "exact_id_from_list", "action_type": "order_lab|give_medication|...", "args": {{}}, "justification": "reason"}}
  ],
  "reasoning": "brief clinical reasoning"
}}"""

        messages = [
            LLMMessage(role="system", content=CLINICAL_SYSTEM_PROMPT),
            LLMMessage(role="user", content=user_prompt)
        ]

        # LLM 호출
        from cga_bench.agent_runner.llm_provider import ACTION_RECOMMENDATION_SCHEMA
        result = self.llm_provider.complete_json(messages, ACTION_RECOMMENDATION_SCHEMA)

        # 결과 파싱
        actions = []
        if isinstance(result, list):
            actions_data = result
        else:
            actions_data = result.get("actions", [])

        for action_data in actions_data:
            action_id = str(action_data.get("action_id", ""))
            if action_id in self._completed_action_ids:
                continue

            # Validate and normalize action_id
            normalized_id = self._normalize_action_id(action_id, constraints)
            if normalized_id is None:
                logger.warning(f"Invalid action_id from LLM: {action_id}, skipping")
                continue

            action_type_str = action_data.get("action_type", "")
            action_type = self._parse_action_type(action_type_str, normalized_id)

            actions.append(Action(
                type=action_type,
                action_id=normalized_id,
                args=action_data.get("args", {}),
                timestamp_minutes=current_time,
                justification=action_data.get("justification", "LLM recommendation")
            ))

        return actions[:self.config.max_actions_per_step]

    def _normalize_action_id(self, action_id: str, constraints: Dict[str, Any]) -> Optional[str]:
        """
        Normalize and validate action_id against valid actions from Decision Table.

        Returns the normalized action_id if valid, None otherwise.
        """
        # Get all valid action IDs
        valid_ids = set()
        for action in constraints.get("mandatory_actions", []):
            valid_ids.add(action.action_id)
        for action in constraints.get("allowed_actions", []):
            valid_ids.add(action.action_id)

        # Exact match
        if action_id in valid_ids:
            return action_id

        # Fuzzy matching - try to find best match
        action_id_lower = action_id.lower().replace("-", "_").replace(" ", "_")

        # Common normalization patterns
        for valid_id in valid_ids:
            valid_id_lower = valid_id.lower()

            # Exact match after normalization
            if action_id_lower == valid_id_lower:
                return valid_id

            # N2 Fix: Substring match with minimum length ratio to prevent false positives
            # Candidate must be >50% of target length to qualify as a valid subset
            if len(action_id_lower) >= 4 and len(valid_id_lower) >= 4:
                if action_id_lower in valid_id_lower:
                    ratio = len(action_id_lower) / len(valid_id_lower)
                    if ratio >= 0.5:
                        logger.info(f"Fuzzy matched '{action_id}' to '{valid_id}' (subset, ratio={ratio:.2f})")
                        return valid_id
                elif valid_id_lower in action_id_lower:
                    ratio = len(valid_id_lower) / len(action_id_lower)
                    if ratio >= 0.5:
                        logger.info(f"Fuzzy matched '{action_id}' to '{valid_id}' (superset, ratio={ratio:.2f})")
                        return valid_id

            # Check for common abbreviations
            if self._is_abbreviation_match(action_id_lower, valid_id_lower):
                logger.info(f"Abbreviation matched '{action_id}' to '{valid_id}'")
                return valid_id

        return None

    def _is_abbreviation_match(self, candidate: str, valid: str) -> bool:
        """Check if candidate is an abbreviation/variation of valid action ID."""
        # Remove common prefixes for comparison
        candidate_core = candidate.replace("order_", "").replace("give_", "").replace("lab_", "").replace("imaging_", "")
        valid_core = valid.replace("order_", "").replace("give_", "").replace("lab_", "").replace("imaging_", "")

        # Check if cores match
        if candidate_core == valid_core:
            return True

        # Check common abbreviations
        abbrev_map = {
            "ecg": "12_lead_ecg",
            "ekg": "12_lead_ecg",
            "cxr": "chest_xray",
            "bnp": "bnp_or_ntprobnp",
            "bmp": "basic_metabolic_panel",
            "metabolic_panel": "basic_metabolic_panel",
            "echo": "echocardiogram",
            "lactate": "serum_lactate",
        }

        for abbrev, full in abbrev_map.items():
            if abbrev in candidate_core and full in valid_core:
                return True

        return False

    def _format_patient_state(self, state: Dict[str, Any]) -> str:
        """환자 상태를 포맷팅"""
        parts = []

        # 기본 정보
        if state.get("chief_complaint"):
            parts.append(f"**Chief Complaint:** {state['chief_complaint']}")
        if state.get("working_diagnosis"):
            parts.append(f"**Working Diagnosis:** {state['working_diagnosis']}")

        # 활력징후
        vitals = state.get("vitals", {})
        if vitals:
            vitals_str = []
            if vitals.get("blood_pressure_systolic"):
                vitals_str.append(f"BP: {vitals.get('blood_pressure_systolic')}/{vitals.get('blood_pressure_diastolic', '?')}")
            if vitals.get("heart_rate"):
                vitals_str.append(f"HR: {vitals['heart_rate']}")
            if vitals.get("respiratory_rate"):
                vitals_str.append(f"RR: {vitals['respiratory_rate']}")
            if vitals.get("temperature"):
                vitals_str.append(f"Temp: {vitals['temperature']}")
            if vitals.get("oxygen_saturation"):
                vitals_str.append(f"SpO2: {vitals['oxygen_saturation']}%")
            if vitals_str:
                parts.append(f"**Vitals:** {', '.join(vitals_str)}")

        # 검사 결과
        labs = state.get("lab_results", [])
        if labs:
            lab_str = [f"{l.get('test_code')}: {l.get('value')}" for l in labs if isinstance(l, dict)]
            if lab_str:
                parts.append(f"**Labs:** {', '.join(lab_str[:5])}")

        return "\n".join(parts) if parts else "No patient data available"

    def _parse_action_type(self, action_type_str: str, action_id: str) -> ActionType:
        """행동 타입 문자열을 ActionType으로 변환"""
        type_map = {
            "order_lab": ActionType.ORDER_LAB,
            "order_imaging": ActionType.ORDER_IMAGING,
            "order_diagnostic": ActionType.ORDER_IMAGING,
            "give_medication": ActionType.GIVE_MEDICATION,
            "procedure": ActionType.PROCEDURE,
            "consult": ActionType.CONSULT,
            "assessment": ActionType.REASSESS,
            "reassess": ActionType.REASSESS,
            "monitoring": ActionType.ORDER_LAB,
            "disposition": ActionType.DISPOSITION,
        }

        # action_type_str에서 먼저 찾기
        for key, value in type_map.items():
            if key in action_type_str.lower():
                return value

        # action_id에서 추론
        action_id_lower = action_id.lower()
        if "lab" in action_id_lower or "culture" in action_id_lower or "lactate" in action_id_lower:
            return ActionType.ORDER_LAB
        elif "ecg" in action_id_lower or "imaging" in action_id_lower or "xray" in action_id_lower:
            return ActionType.ORDER_IMAGING
        elif "give" in action_id_lower or "medication" in action_id_lower or "antibiotic" in action_id_lower:
            return ActionType.GIVE_MEDICATION
        elif "assess" in action_id_lower:
            return ActionType.REASSESS
        elif "consult" in action_id_lower or "activate" in action_id_lower:
            return ActionType.CONSULT

        return ActionType.REASSESS

    def _get_constraints_from_decision_table(
        self,
        state: Dict[str, Any],
        current_time: float
    ) -> Dict[str, Any]:
        """
        독립적 Decision Table에서 제약 조건 획득

        Note:
            채점용 CPG-Engine을 사용하지 않습니다.
            대신 agent_rules/의 독립적 Decision Table을 사용합니다.

        Returns:
            {
                "allowed_actions": A_G,
                "mandatory_actions": M_G,
                "forbidden_actions": F_G,
                "deadlines": D_G,
                "sequence_constraints": S_G
            }
        """
        if not self.decision_table:
            return {
                "allowed_actions": [],
                "mandatory_actions": [],
                "forbidden_actions": [],
                "deadlines": {},
                "sequence_constraints": []
            }

        # 컨텍스트 변환
        context = self._state_to_context(state)

        # 독립적 Decision Table에서 권고 행동 획득
        recommendations = self.decision_table.get_recommended_actions(context, int(current_time))

        # 금지 행동 획득
        forbidden_ids = self.decision_table.get_forbidden_actions(context)

        # Action 객체로 변환
        allowed_actions = []
        mandatory_actions = []
        deadlines = {}

        for rec in recommendations:
            action = Action(
                type=self._map_action_type(rec.action_type),
                action_id=rec.action_id,
                args=rec.parameters,
                timestamp_minutes=current_time,
                justification=f"Source: {rec.source_guideline or 'Independent Decision Table'}"
            )

            if rec.is_mandatory:
                mandatory_actions.append(action)
            else:
                allowed_actions.append(action)

            if rec.deadline_minutes:
                deadlines[rec.action_id] = rec.deadline_minutes

        # 금지 행동을 Action 객체로 변환
        forbidden_actions = [
            Action(
                type=ActionType.REASSESS,
                action_id=fid,
                args={},
                timestamp_minutes=current_time,
                justification=None
            )
            for fid in forbidden_ids
        ]

        # 시퀀스 제약 획득
        sequence_constraints = self.decision_table.get_sequence_constraints()

        return {
            "allowed_actions": allowed_actions,
            "mandatory_actions": mandatory_actions,
            "forbidden_actions": forbidden_actions,
            "deadlines": deadlines,
            "sequence_constraints": sequence_constraints
        }

    def _state_to_context(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """상태를 Decision Table 컨텍스트로 변환"""
        context = {
            "timestamp_minutes": 0,
            "working_diagnosis": state.get("working_diagnosis", ""),
            "chief_complaint": state.get("chief_complaint", ""),
            "allergies": state.get("allergies", []),
            "comorbidities": state.get("comorbidities", []),
        }

        # Vitals 추출
        vitals = state.get("vitals", {})
        if isinstance(vitals, dict):
            context["heart_rate"] = vitals.get("heart_rate")
            context["sbp_mmhg"] = vitals.get("blood_pressure_systolic")
            context["dbp_mmhg"] = vitals.get("blood_pressure_diastolic")
            context["map_mmhg"] = vitals.get("map_mmhg")
            context["respiratory_rate"] = vitals.get("respiratory_rate")
            context["temperature"] = vitals.get("temperature")
            context["oxygen_saturation"] = vitals.get("oxygen_saturation")

            # MAP 계산 (없는 경우)
            if context["map_mmhg"] is None and context["sbp_mmhg"] and context["dbp_mmhg"]:
                context["map_mmhg"] = (context["sbp_mmhg"] + 2 * context["dbp_mmhg"]) / 3

        # Lab results 추출
        for lab in state.get("lab_results", []):
            if isinstance(lab, dict):
                test_code = lab.get("test_code", "").lower()
                value = lab.get("value")
                if test_code and value is not None:
                    context[test_code] = value
                    if "lactate" in test_code:
                        context["lactate"] = value
                    elif "troponin" in test_code:
                        context["troponin"] = value
                        context["troponin_elevated"] = value > 0.04

        # ECG 결과 추출
        for img in state.get("imaging_results", []):
            if isinstance(img, dict):
                img_type = img.get("imaging_type", "").lower()
                result = img.get("result", "").lower()
                if "ecg" in img_type:
                    context["ecg_result"] = result
                    context["ecg_stemi"] = "st elevation" in result or "stemi" in result
                    context["ecg_inferior_stemi"] = "inferior" in result and context["ecg_stemi"]

        return context

    def _map_action_type(self, action_type_str: str) -> ActionType:
        """행동 타입 문자열을 ActionType으로 변환"""
        type_map = {
            "order_lab": ActionType.ORDER_LAB,
            "order_diagnostic": ActionType.ORDER_IMAGING,
            "give_medication": ActionType.GIVE_MEDICATION,
            "procedure": ActionType.PROCEDURE,
            "consult": ActionType.CONSULT,
            "assessment": ActionType.REASSESS,
            "monitoring": ActionType.ORDER_LAB,
            "disposition": ActionType.DISPOSITION,
        }
        return type_map.get(action_type_str, ActionType.REASSESS)

    def _update_plan_status(self, constraints: Dict[str, Any]):
        """계획 상태 업데이트"""
        # 완료된 mandatory action 체크
        mandatory_ids = {a.action_id for a in constraints.get("mandatory_actions", [])}

        for planned in self._current_plan:
            if planned.action.action_id in self._completed_action_ids:
                planned.status = PlanStatus.COMPLETED

            # 금지된 행동은 BLOCKED 처리
            forbidden_ids = {a.action_id for a in constraints.get("forbidden_actions", [])}
            if planned.action.action_id in forbidden_ids:
                planned.status = PlanStatus.BLOCKED

    def _should_replan(self, constraints: Dict[str, Any]) -> bool:
        """재계획 필요 여부 판단"""
        # 계획이 없으면 재계획
        if not self._current_plan:
            return True

        # 모든 계획이 완료/블록되면 재계획
        pending_count = sum(
            1 for p in self._current_plan
            if p.status in [PlanStatus.PENDING, PlanStatus.IN_PROGRESS]
        )
        if pending_count == 0:
            return True

        # 새로운 mandatory action이 있으면 재계획
        current_mandatory_ids = {a.action_id for a in constraints.get("mandatory_actions", [])}
        planned_ids = {p.action.action_id for p in self._current_plan}
        if current_mandatory_ids - planned_ids - self._completed_action_ids:
            return True

        return False

    def _create_plan(
        self,
        state: Dict[str, Any],
        current_time: float,
        constraints: Dict[str, Any]
    ) -> None:
        """
        CPG 제약 기반 계획 수립

        우선순위:
        1. 긴급 mandatory actions (데드라인 임박)
        2. 일반 mandatory actions
        3. 권장 allowed actions
        """
        self._current_plan = []

        # 1. Mandatory actions 계획 (최우선)
        for action in constraints.get("mandatory_actions", []):
            if action.action_id in self._completed_action_ids:
                continue

            deadline = constraints.get("deadlines", {}).get(action.action_id)
            priority = 1 if deadline and deadline - current_time < 10 else 2

            # 시퀀스 의존성 확인
            dependencies = self._get_dependencies(action, constraints)

            self._current_plan.append(PlannedAction(
                action=action,
                priority=priority,
                is_mandatory=True,
                deadline_minutes=deadline,
                dependencies=dependencies,
                source_recommendation=getattr(action, 'justification', None)
            ))

        # 2. Allowed actions 중 권장 사항 계획
        for action in constraints.get("allowed_actions", []):
            if action.action_id in self._completed_action_ids:
                continue
            # Mandatory가 아니고 Forbidden이 아닌 경우만
            mandatory_ids = {a.action_id for a in constraints.get("mandatory_actions", [])}
            forbidden_ids = {a.action_id for a in constraints.get("forbidden_actions", [])}

            if action.action_id not in mandatory_ids and action.action_id not in forbidden_ids:
                self._current_plan.append(PlannedAction(
                    action=action,
                    priority=3,
                    is_mandatory=False
                ))

        # 우선순위로 정렬
        self._current_plan.sort(key=lambda p: (p.priority, p.deadline_minutes or float('inf')))

    def _get_dependencies(self, action: Action, constraints: Dict[str, Any]) -> List[str]:
        """행동의 선행 의존성 확인"""
        dependencies: List[str] = []

        sequence_constraints = constraints.get("sequence_constraints", [])
        for constraint in sequence_constraints:
            # constraint: {"before": action_id, "after": action_id}
            if isinstance(constraint, dict):
                if constraint.get("after") == action.action_id:
                    before = constraint.get("before")
                    if before is not None:
                        dependencies.append(before)

        return dependencies

    def _select_next_actions(
        self,
        current_time: float,
        constraints: Dict[str, Any]
    ) -> List[Action]:
        """
        다음 행동 선택

        제약 조건:
        - 의존성 충족된 행동만 선택
        - 금지 행동 제외
        - 데드라인 임박 행동 우선
        """
        selected = []
        forbidden_ids = {a.action_id for a in constraints.get("forbidden_actions", [])}

        for planned in self._current_plan:
            if planned.status != PlanStatus.PENDING:
                continue

            # 금지 행동 체크
            if planned.action.action_id in forbidden_ids:
                planned.status = PlanStatus.BLOCKED
                continue

            # 의존성 체크
            deps_satisfied = all(
                dep in self._completed_action_ids
                for dep in planned.dependencies
            )
            if not deps_satisfied:
                continue

            # 행동 선택
            action = planned.action
            action.timestamp_minutes = current_time

            selected.append(action)
            planned.status = PlanStatus.IN_PROGRESS
            self._completed_action_ids.add(action.action_id)
            self._action_history.append(action)

            if len(selected) >= self.config.max_actions_per_step:
                break

        # 계획이 비어있고 mandatory가 없으면 기본 행동
        if not selected and not any(p.is_mandatory for p in self._current_plan):
            selected = self._get_default_actions(current_time)

        return selected

    def _get_default_actions(self, current_time: float) -> List[Action]:
        """
        기본 행동 (계획 없을 때)

        Note:
            도메인별로 적절한 기본 행동을 반환합니다.
            잘못된 기본 행동은 DEVIATION 위반을 유발하므로,
            Decision Table에서 권고가 없으면 빈 리스트를 반환합니다.
        """
        # Decision Table이 권고하는 행동이 없으면 기본 행동도 반환하지 않음
        # 이는 DEVIATION 위반을 방지하기 위함
        # (잘못된 도메인의 기본 행동이 위반으로 카운트됨)
        return []

    def get_current_plan(self) -> List[Dict[str, Any]]:
        """현재 계획 상태 반환 (디버깅/분석용)"""
        return [
            {
                "action_id": p.action.action_id,
                "priority": p.priority,
                "status": p.status.value,
                "is_mandatory": p.is_mandatory,
                "deadline": p.deadline_minutes,
                "dependencies": p.dependencies
            }
            for p in self._current_plan
        ]

    def _get_visible_state(self, observation: Observation) -> Dict[str, Any]:
        """Observation에서 visible_state 추출"""
        return observation.visible_state

    def get_constraint_summary(self, observation: Observation) -> Dict[str, Any]:
        """제약 조건 요약 반환 (디버깅/분석용)"""
        constraints = self._get_constraints_from_decision_table(
            self._get_visible_state(observation),
            observation.timestamp_minutes
        )

        return {
            "allowed_count": len(constraints.get("allowed_actions", [])),
            "mandatory_count": len(constraints.get("mandatory_actions", [])),
            "forbidden_count": len(constraints.get("forbidden_actions", [])),
            "deadlines": list(constraints.get("deadlines", {}).keys()),
            "sequence_count": len(constraints.get("sequence_constraints", []))
        }

    def get_independence_verification(self) -> Dict[str, Any]:
        """
        독립성 검증 정보 반환

        이 메서드는 Planner가 채점용 CPG-Engine과 독립적임을 검증하기 위한 정보를 제공합니다.
        논문 심사자가 "치팅" 우려를 검증할 때 사용할 수 있습니다.
        """
        return {
            "uses_cpg_engine": False,
            "uses_assessor_core": False,
            "decision_table_source": "agent_rules/ (independent implementation)",
            "cpg_engine_import": False,
            "rule_system": "Human-authored Decision Table from CPG text",
            "graph_structure_reuse": False,
            "node_id_reuse": False,
            "decision_table_type": type(self.decision_table).__name__ if self.decision_table else None,
            "verification_note": (
                "This Planner uses an independently implemented rule-based system "
                "that references the same CPG guidelines as the scoring engine, "
                "but does NOT share graph structure, node IDs, or metadata. "
                "This design prevents evaluation leakage/cheating."
            ),
        }
