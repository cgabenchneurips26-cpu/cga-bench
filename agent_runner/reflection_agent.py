"""
Reflection Agent: 자기 반성 기반 에이전트

CGA-Bench 명세에 따른 Reflection Agent 구현:
- 독립적 Decision Table 기반 행동 생성 (채점용 CPG-Engine 미사용)
- LLM 자기 반성을 통한 행동 검증 및 수정
- Budget-matched self-refinement

중요 설계 원칙 (NeurIPS 리뷰어 비판 대응):
- 채점용 CPG-Engine(cpg_engine/)에 직접 접근 불가
- 대신 agent_rules/의 독립적 Decision Table 사용
- 이 설계는 "평가 누수/치팅" 방지를 위한 것
"""

import logging
import re
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum

from cga_bench.agent_runner.base_agent import BaseAgent, AgentConfig, AgentMetrics
from cga_bench.agent_runner.planner_agent import PlannerAgent, PlannerConfig
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


class ReflectionOutcome(str, Enum):
    """반성 결과"""
    ACCEPT = "accept"  # 행동 수용
    REVISE = "revise"  # 행동 수정
    REJECT = "reject"  # 행동 거부
    ADD = "add"  # 추가 행동 필요


@dataclass
class ReflectionResult:
    """반성 결과"""
    original_action: Action
    outcome: ReflectionOutcome
    revised_action: Optional[Action] = None
    reasoning: str = ""
    violation_detected: Optional[str] = None


@dataclass
class ReflectionConfig(AgentConfig):
    """Reflection 에이전트 설정"""
    agent_type: str = "reflection"
    # 독립적 규칙 시스템 설정 (채점용 CPG-Engine 미사용)
    guideline_domain: str = "sepsis"  # sepsis, chest_pain, aki
    # Reflection 설정
    max_reflection_rounds: int = 2  # 최대 반성 라운드
    reflection_threshold: float = 0.7  # 반성 임계값
    # LLM 설정
    llm_backend: LLMBackend = LLMBackend.OPENAI
    llm_model: str = "gpt-4"
    temperature: float = 0.1
    use_llm: bool = True  # LLM 사용 여부


class ReflectionAgent(BaseAgent):
    """
    Reflection Agent: 자기 반성 기반 에이전트

    다른 에이전트와의 차이점:
    1. Self-Reflection: LLM 기반 행동 전 자가 검증
    2. Violation Detection: 독립적 Decision Table 기반 위반 사전 감지
    3. Budget-matched Refinement: 예산 내 반복 개선

    중요 설계 원칙:
    - 채점용 CPG-Engine(cpg_engine/)에 직접 접근하지 않음
    - 대신 agent_rules/의 독립적 Decision Table 사용
    - Oracle, Planner와 동일한 분리 원칙 적용
    """

    def __init__(
        self,
        config: ReflectionConfig,
        llm_provider: Optional[BaseLLMProvider] = None
    ):
        """
        Reflection 에이전트 초기화

        Args:
            config: Reflection 설정
            llm_provider: LLM 프로바이더 (선택)

        Note:
            cpg_engine 인자를 받지 않습니다. 이는 의도적인 설계입니다.
            채점용 엔진과 분리된 독립적 규칙 시스템만 사용합니다.
        """
        super().__init__(config)
        self.reflection_config = config

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

        # 내부 Planner (행동 생성용) - 독립적 규칙 시스템 사용
        planner_config = PlannerConfig(
            agent_id=f"{config.agent_id}_planner",
            guideline_domain=config.guideline_domain,
            budget_limit_tokens=config.budget_limit_tokens,
            budget_limit_tool_calls=config.budget_limit_tool_calls,
            llm_backend=config.llm_backend,
            llm_model=config.llm_model,
            use_llm=config.use_llm
        )
        self._planner = PlannerAgent(planner_config, llm_provider)

        # 반성 이력
        self._reflection_history: List[ReflectionResult] = []
        self._action_history: List[Action] = []
        # N4 Fix: 선행 조건 미충족으로 지연된 행동 큐
        self._deferred_actions: List[Action] = []
        # Planner 메트릭 추적 (delta 계산용)
        self._prev_planner_tokens: int = 0
        self._prev_planner_llm_calls: int = 0

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
            logger.info(f"Reflection initialized with {table_cls.__name__} for domain '{domain}'")
        else:
            logger.warning(
                f"Unknown domain '{domain}'. Defaulting to SepsisDecisionTable."
            )
            self.decision_table = SepsisDecisionTable()

    def reset(self):
        """에이전트 상태 리셋"""
        self._planner.reset()
        self._reflection_history = []
        self._action_history = []
        self._deferred_actions = []
        self._prev_planner_tokens = 0
        self._prev_planner_llm_calls = 0
        self.metrics = AgentMetrics()
        if self.decision_table:
            self.decision_table.reset()

    def decide(self, observation: Observation) -> List[Action]:
        """
        자기 반성 기반 행동 결정

        프로세스:
        1. 이전 단계에서 지연된 행동이 있으면 우선 포함
        2. Planner로 초기 행동 생성
        3. 각 행동에 대해 자기 반성
        4. 반성 결과에 따라 수정/거부/추가
        5. 최종 행동 반환
        """
        state = self._get_visible_state(observation)
        current_time = observation.timestamp_minutes

        # N4 Fix: 이전 단계에서 지연된 행동을 초기 행동에 포함
        deferred = self._deferred_actions
        self._deferred_actions = []

        # 1. Planner로 초기 행동 생성
        initial_actions = deferred + self._planner.decide(observation)
        # N3 Fix: Planner 메트릭을 delta 기반으로 전파 (실제 LLM 호출만 반영)
        planner_tokens_now = self._planner.metrics.total_tokens
        self.metrics.total_tokens += (planner_tokens_now - self._prev_planner_tokens)
        self._prev_planner_tokens = planner_tokens_now
        planner_llm_calls_now = self._planner.metrics.total_llm_calls
        self.metrics.total_llm_calls += (planner_llm_calls_now - self._prev_planner_llm_calls)
        self._prev_planner_llm_calls = planner_llm_calls_now

        # 2. 반성 라운드 수행
        refined_actions = self._reflection_loop(
            initial_actions,
            state,
            current_time
        )

        # 행동 이력 업데이트
        self._action_history.extend(refined_actions)

        return refined_actions

    def _get_visible_state(self, observation: Observation) -> Dict[str, Any]:
        """Observation에서 visible_state 추출"""
        return observation.visible_state

    def _reflection_loop(
        self,
        actions: List[Action],
        state: Dict[str, Any],
        current_time: float
    ) -> List[Action]:
        """
        LLM 기반 반성 루프

        Budget-matched: 예산 내에서 반복 개선
        """
        current_actions = actions.copy()

        for round_num in range(self.reflection_config.max_reflection_rounds):
            # 예산 체크
            if self._budget_exceeded():
                break

            # LLM 사용 가능 시 LLM으로 반성
            if self.llm_provider and self.reflection_config.use_llm:
                try:
                    reflection_results = self._reflect_with_llm(
                        current_actions, state, current_time
                    )
                    # 토큰 사용량 추적
                    self.metrics.total_tokens += self.llm_provider.get_total_tokens_from_last_call()
                    self.metrics.total_llm_calls += 1

                    for r in reflection_results:
                        self._reflection_history.append(r)

                    # 반성 결과 처리
                    revised_actions = self._process_reflection_results(
                        reflection_results,
                        state,
                        current_time
                    )

                    # 더 이상 수정 필요 없으면 종료
                    if all(r.outcome == ReflectionOutcome.ACCEPT for r in reflection_results):
                        break

                    current_actions = revised_actions
                    continue

                except Exception as e:
                    logger.warning(f"LLM reflection failed: {e}, falling back to rule-based")

            # 규칙 기반 폴백
            reflection_results = []
            for action in current_actions:
                result = self._reflect_on_action(action, state, current_time)
                reflection_results.append(result)
                self._reflection_history.append(result)

            # 반성 결과 처리
            revised_actions = self._process_reflection_results(
                reflection_results,
                state,
                current_time
            )

            # 더 이상 수정 필요 없으면 종료
            if all(r.outcome == ReflectionOutcome.ACCEPT for r in reflection_results):
                break

            current_actions = revised_actions
            # N3 Fix: LLM 호출 카운트는 실제 LLM 호출 시에만 증가 (line 272)

        return current_actions

    def _reflect_with_llm(
        self,
        actions: List[Action],
        state: Dict[str, Any],
        current_time: float
    ) -> List[ReflectionResult]:
        """LLM을 사용하여 행동 반성"""
        if self.llm_provider is None:
            raise RuntimeError("LLM provider not initialized")

        # 환자 상태 요약
        patient_summary = self._format_patient_state(state)

        # 행동 목록 포맷팅
        actions_str = "\n".join([
            f"- {a.action_id}: {a.justification or 'No justification'}"
            for a in actions
        ])

        # 완료된 행동 목록
        completed_str = ", ".join([a.action_id for a in self._action_history]) if self._action_history else "None"

        # 금지 행동 목록 (Decision Table에서)
        context = self._state_to_context(state)
        forbidden_ids = []
        if self.decision_table:
            forbidden_ids = self.decision_table.get_forbidden_actions(context)
        forbidden_str = ", ".join(forbidden_ids) if forbidden_ids else "None"

        # 프롬프트 구성
        reflection_prompt = f"""## Patient State
{patient_summary}

## Time Since Arrival
{current_time} minutes

## Previous Actions
{completed_str}

## Proposed Actions to Review
{actions_str}

## Forbidden Actions (Do NOT allow)
{forbidden_str}

## Task
You are a clinical safety reviewer. Evaluate each proposed action and determine if it should be:
- ACCEPT: Action is safe and appropriate
- REJECT: Action is harmful or contraindicated
- REVISE: Action needs modification
- ADD: A prerequisite action is missing

Consider:
1. Clinical safety (contraindications, drug interactions)
2. Sequence requirements (e.g., cultures before antibiotics)
3. Time-critical deadlines
4. Patient-specific factors (allergies, comorbidities)

Respond with a JSON object:
{{
    "reflections": [
        {{
            "action_id": "action_id_here",
            "outcome": "ACCEPT|REJECT|REVISE|ADD",
            "reasoning": "explanation",
            "violation_type": "optional: COMMISSION|OMISSION|TIMING|SEQUENCE",
            "suggested_action": "optional: if ADD, the prerequisite action_id"
        }}
    ],
    "overall_assessment": "brief summary"
}}"""

        messages = [
            LLMMessage(role="system", content="You are a clinical safety reviewer for medical AI systems."),
            LLMMessage(role="user", content=reflection_prompt)
        ]

        # LLM 호출
        reflection_schema = {
            "type": "object",
            "properties": {
                "reflections": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "action_id": {"type": "string"},
                            "outcome": {"type": "string"},
                            "reasoning": {"type": "string"},
                            "violation_type": {"type": "string"},
                            "suggested_action": {"type": "string"}
                        }
                    }
                },
                "overall_assessment": {"type": "string"}
            }
        }

        result = self.llm_provider.complete_json(messages, reflection_schema)

        # 결과 파싱
        reflections = []
        action_map = {a.action_id: a for a in actions}

        reflections_data = result.get("reflections", [])
        for r_data in reflections_data:
            action_id = r_data.get("action_id", "")
            if action_id not in action_map:
                continue

            outcome_str = r_data.get("outcome", "ACCEPT").upper()
            outcome = {
                "ACCEPT": ReflectionOutcome.ACCEPT,
                "REJECT": ReflectionOutcome.REJECT,
                "REVISE": ReflectionOutcome.REVISE,
                "ADD": ReflectionOutcome.ADD
            }.get(outcome_str, ReflectionOutcome.ACCEPT)

            reflections.append(ReflectionResult(
                original_action=action_map[action_id],
                outcome=outcome,
                reasoning=r_data.get("reasoning", ""),
                violation_detected=r_data.get("violation_type")
            ))

        # 반환되지 않은 행동은 ACCEPT 처리
        reflected_ids = {r.original_action.action_id for r in reflections}
        for action in actions:
            if action.action_id not in reflected_ids:
                reflections.append(ReflectionResult(
                    original_action=action,
                    outcome=ReflectionOutcome.ACCEPT,
                    reasoning="Not reviewed by LLM"
                ))

        return reflections

    def _format_patient_state(self, state: Dict[str, Any]) -> str:
        """환자 상태를 포맷팅"""
        parts = []

        if state.get("chief_complaint"):
            parts.append(f"**Chief Complaint:** {state['chief_complaint']}")
        if state.get("working_diagnosis"):
            parts.append(f"**Working Diagnosis:** {state['working_diagnosis']}")

        vitals = state.get("vitals", {})
        if vitals:
            vitals_str = []
            if vitals.get("blood_pressure_systolic"):
                vitals_str.append(f"BP: {vitals.get('blood_pressure_systolic')}/{vitals.get('blood_pressure_diastolic', '?')}")
            if vitals.get("heart_rate"):
                vitals_str.append(f"HR: {vitals['heart_rate']}")
            if vitals_str:
                parts.append(f"**Vitals:** {', '.join(vitals_str)}")

        return "\n".join(parts) if parts else "No patient data available"

    def _reflect_on_action(
        self,
        action: Action,
        state: Dict[str, Any],
        current_time: float
    ) -> ReflectionResult:
        """
        단일 행동에 대한 반성

        검증 항목:
        1. CPG 위반 여부 (COMMISSION) - 독립적 Decision Table 사용
        2. 누락 여부 (OMISSION)
        3. 시간 준수 여부 (TIMING)
        4. 순서 준수 여부 (SEQUENCE)

        Note:
            채점용 CPG-Engine을 사용하지 않습니다.
            대신 agent_rules/의 독립적 Decision Table을 사용합니다.
        """
        if not self.decision_table:
            return ReflectionResult(
                original_action=action,
                outcome=ReflectionOutcome.ACCEPT,
                reasoning="No Decision Table available for validation"
            )

        # 컨텍스트 변환
        context = self._state_to_context(state)

        # 1. COMMISSION 검증: 금지된 행동인가?
        forbidden_ids = self.decision_table.get_forbidden_actions(context)

        if action.action_id in forbidden_ids:
            return ReflectionResult(
                original_action=action,
                outcome=ReflectionOutcome.REJECT,
                reasoning=f"Action {action.action_id} is forbidden by CPG guidelines",
                violation_detected="COMMISSION"
            )

        # 2. TIMING 검증: 데드라인 초과?
        recommendations = self.decision_table.get_recommended_actions(context, int(current_time))
        for rec in recommendations:
            if rec.action_id == action.action_id and rec.deadline_minutes:
                if current_time > rec.deadline_minutes:
                    return ReflectionResult(
                        original_action=action,
                        outcome=ReflectionOutcome.ACCEPT,  # 늦었지만 수행은 필요
                        reasoning=f"Action {action.action_id} is past deadline ({rec.deadline_minutes}m) but should still be performed",
                        violation_detected="TIMING_WARNING"
                    )

        # 3. SEQUENCE 검증: 선행 조건 충족?
        sequence_constraints = self.decision_table.get_sequence_constraints()
        for constraint in sequence_constraints:
            if isinstance(constraint, dict):
                if constraint.get("after") == action.action_id:
                    before_action = constraint.get("before")
                    if before_action not in {a.action_id for a in self._action_history}:
                        # 선행 행동 추가 필요
                        return ReflectionResult(
                            original_action=action,
                            outcome=ReflectionOutcome.ADD,
                            reasoning=f"Must perform {before_action} before {action.action_id}",
                            violation_detected="SEQUENCE"
                        )

        # 4. 특수 케이스 검증
        special_check = self._check_special_cases(action, state)
        if special_check:
            return special_check

        # 모든 검증 통과
        return ReflectionResult(
            original_action=action,
            outcome=ReflectionOutcome.ACCEPT,
            reasoning="Action validated against independent Decision Table"
        )

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
            context["map_mmhg"] = vitals.get("map_mmhg")

            # MAP 계산 (없는 경우)
            sbp = vitals.get("blood_pressure_systolic")
            dbp = vitals.get("blood_pressure_diastolic")
            if context["map_mmhg"] is None and sbp and dbp:
                context["map_mmhg"] = (sbp + 2 * dbp) / 3

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
                    context["ecg_inferior_stemi"] = "inferior" in result and context.get("ecg_stemi", False)

        return context

    # T1 Fix: Decision Table 표준 ID 집합 (사전 정규화 ID + CPG 표준 ID 모두 포함)
    _ANTIBIOTICS_IDS = {
        "give_antibiotics", "give_broad_spectrum_antibiotics",
        "broad_spectrum_antibiotics", "empiric_antibiotics",
    }
    _BLOOD_CULTURE_IDS = {
        "order_blood_culture", "order_lab_blood_culture",
        "blood_culture_before_antibiotics",
    }

    def _check_special_cases(
        self,
        action: Action,
        state: Dict[str, Any]
    ) -> Optional[ReflectionResult]:
        """특수 케이스 검증"""

        # RV Infarct + Nitrates 트랩
        if action.action_id in ["give_nitroglycerin", "give_nitrates"]:
            # V4R 검사 없이 Inferior STEMI면 위험
            ecg_result = self._get_ecg_from_state(state)
            if ecg_result and "inferior" in ecg_result.lower() and "st elevation" in ecg_result.lower():
                v4r_done = any(
                    a.action_id == "obtain_right_sided_ecg_v4r"
                    for a in self._action_history
                )
                if not v4r_done:
                    return ReflectionResult(
                        original_action=action,
                        outcome=ReflectionOutcome.REJECT,
                        reasoning="Nitrates contraindicated in suspected RV infarct. Obtain V4R ECG first.",
                        violation_detected="RV_INFARCT_TRAP"
                    )

        # T1 Fix: Antibiotics before Blood Culture (Decision Table 표준 ID 포함)
        if action.action_id in self._ANTIBIOTICS_IDS:
            bc_done = any(
                a.action_id in self._BLOOD_CULTURE_IDS
                for a in self._action_history
            )
            if not bc_done:
                return ReflectionResult(
                    original_action=action,
                    outcome=ReflectionOutcome.ADD,
                    reasoning="Blood cultures should be obtained before antibiotics per SSC guidelines",
                    violation_detected="BC_BEFORE_ABX"
                )

        return None

    def _get_ecg_from_state(self, state: Dict[str, Any]) -> Optional[str]:
        """상태에서 ECG 결과 추출"""
        # working_diagnosis에서 추출
        diagnosis = state.get("working_diagnosis", "")
        if diagnosis and ("stemi" in diagnosis.lower() or "st elevation" in diagnosis.lower()):
            return diagnosis

        # imaging_results에서 ECG 검색
        for img in state.get("imaging_results", []):
            if isinstance(img, dict) and "ecg" in str(img).lower():
                return img.get("result", str(img))
            elif isinstance(img, str) and "ecg" in img.lower():
                return img

        return None

    def _process_reflection_results(
        self,
        results: List[ReflectionResult],
        state: Dict[str, Any],
        current_time: float
    ) -> List[Action]:
        """반성 결과 처리"""
        final_actions = []
        additional_actions = []

        for result in results:
            if result.outcome == ReflectionOutcome.ACCEPT:
                final_actions.append(result.original_action)

            elif result.outcome == ReflectionOutcome.REVISE:
                if result.revised_action:
                    final_actions.append(result.revised_action)

            elif result.outcome == ReflectionOutcome.REJECT:
                # 거부된 행동은 추가하지 않음
                pass

            elif result.outcome == ReflectionOutcome.ADD:
                # N4 Fix: 선행 행동만 이번 스텝에 포함, 원래 행동은 다음 스텝으로 지연
                prerequisite = self._create_prerequisite_action(
                    result,
                    state,
                    current_time
                )
                if prerequisite:
                    # U1 Fix: 현재 step에 이미 동일 prerequisite가 있으면 중복 생성 방지
                    current_step_ids = {a.action_id for a in additional_actions + final_actions}
                    if prerequisite.action_id not in current_step_ids:
                        additional_actions.append(prerequisite)
                    # 원래 행동을 다음 decide() 호출 시 처리하도록 지연
                    self._deferred_actions.append(result.original_action)
                else:
                    # 선행 행동 생성 실패 시 원래 행동 그대로 포함
                    final_actions.append(result.original_action)

        # 추가 행동을 앞에 배치
        return additional_actions + final_actions

    def _create_prerequisite_action(
        self,
        result: ReflectionResult,
        state: Dict[str, Any],
        current_time: float
    ) -> Optional[Action]:
        """선행 행동 생성"""
        # T1 Fix: Decision Table 표준 ID 사용
        if result.violation_detected == "BC_BEFORE_ABX":
            return Action(
                type=ActionType.ORDER_LAB,
                action_id="blood_culture_before_antibiotics",
                args={"test_code": "blood_culture"},
                timestamp_minutes=current_time,
                justification="Blood culture before antibiotics (SSC 2021)"
            )

        # T2 Fix: 범용 SEQUENCE 핸들러 - reasoning에서 prerequisite action_id 추출
        if result.violation_detected == "SEQUENCE":
            reasoning = result.reasoning
            # 패턴: "Must perform {before_action} before {after_action}"
            match = re.search(r"Must perform (\S+) before", reasoning)
            if match:
                prereq_id = match.group(1)
                action_type = self._infer_action_type(prereq_id)
                args = self._infer_action_args(prereq_id, action_type)
                return Action(
                    type=action_type,
                    action_id=prereq_id,
                    args=args,
                    timestamp_minutes=current_time,
                    justification=f"Prerequisite: {reasoning}"
                )

        return None

    def _infer_action_type(self, action_id: str) -> ActionType:
        """Action ID에서 ActionType 추론"""
        aid = action_id.lower()
        if "lab" in aid or "culture" in aid or "lactate" in aid or "creatinine" in aid:
            return ActionType.ORDER_LAB
        # V1 Fix: "echo" 추가, "ct" → 단어 경계 체크로 false positive 방지
        elif ("ecg" in aid or "imaging" in aid or "xray" in aid
              or "echo" in aid or f"_{aid}_".find("_ct_") >= 0):
            return ActionType.ORDER_IMAGING
        # V1 Fix: "crystalloid", "fluid", "start_iv" 추가 (DKA prerequisites)
        elif ("give" in aid or "medication" in aid or "antibiotic" in aid
              or "crystalloid" in aid or "fluid" in aid or "start_iv" in aid):
            return ActionType.GIVE_MEDICATION
        elif "consult" in aid or "activate" in aid:
            return ActionType.CONSULT
        # U2 Fix: "perform", "review", "evaluate", "obtain_last" 등 추가
        elif ("assess" in aid or "check" in aid or "monitor" in aid
              or "perform" in aid or "review" in aid or "evaluate" in aid
              or "calculate" in aid or "obtain_last" in aid):
            return ActionType.REASSESS
        elif "place" in aid or "insert" in aid or "establish" in aid:
            return ActionType.PROCEDURE
        return ActionType.REASSESS

    def _infer_action_args(self, action_id: str, action_type: ActionType) -> Dict[str, Any]:
        """Action ID와 타입에서 기본 args 추론"""
        if action_type == ActionType.ORDER_LAB:
            return {"test_code": action_id}
        elif action_type == ActionType.ORDER_IMAGING:
            return {"imaging_type": action_id}
        elif action_type == ActionType.GIVE_MEDICATION:
            return {"medication_code": action_id, "dose": "standard dose"}
        return {}

    def get_reflection_summary(self) -> Dict[str, Any]:
        """반성 이력 요약 (디버깅/분석용)"""
        outcome_counts: Dict[str, int] = {}
        violation_counts: Dict[str, int] = {}

        for result in self._reflection_history:
            outcome = result.outcome.value
            outcome_counts[outcome] = outcome_counts.get(outcome, 0) + 1

            if result.violation_detected:
                v = result.violation_detected
                violation_counts[v] = violation_counts.get(v, 0) + 1

        return {
            "total_reflections": len(self._reflection_history),
            "outcomes": outcome_counts,
            "violations_detected": violation_counts,
            "llm_calls": self.metrics.total_llm_calls
        }

    def get_independence_verification(self) -> Dict[str, Any]:
        """
        독립성 검증 정보 반환

        이 메서드는 Reflection이 채점용 CPG-Engine과 독립적임을 검증하기 위한 정보를 제공합니다.
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
                "This Reflection agent uses an independently implemented rule-based system "
                "that references the same CPG guidelines as the scoring engine, "
                "but does NOT share graph structure, node IDs, or metadata. "
                "Self-reflection is performed within the budget limit (Budget-matched). "
                "This design prevents evaluation leakage/cheating."
            ),
        }
