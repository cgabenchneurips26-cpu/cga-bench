"""
Rule-based Oracle Agent: 독립적 규칙 기반 에이전트

CGA-Bench 명세에 따른 Oracle Agent 구현:
- 채점용 CPG-Engine과 완전히 분리된 독립적 규칙 시스템 사용
- LLM 호출 없음 (순수 규칙 기반)
- 벤치마크 상한선(Upper Bound) 역할 - 비교 참고치로만 사용

중요 설계 원칙 (NeurIPS 리뷰어 비판 대응):
1. 채점용 CPG-Engine(그래프/DSL 런타임)에 직접 접근 불가
2. 동일 CPG 텍스트 참조하되, 채점용 엔진의 그래프 구조/노드ID/메타데이터 재사용 금지
3. 사람이 만든 독립적인 Decision Table만 사용
4. "Upper-bound 참고치(오라클)"로 위치 명확히 함
"""

from typing import Dict, Any, List, Optional, Set, Type
from dataclasses import dataclass, field
import logging

from cga_bench.agent_runner.base_agent import BaseAgent, AgentConfig, AgentMetrics
from cga_bench.cpg_model.schemas.base import Action, ActionType, PatientState
from cga_bench.scenario_engine.environment import Observation

# 독립적 규칙 시스템 (채점용 CPG-Engine과 분리)
from cga_bench.agent_rules.decision_table import (
    RuleBasedDecisionTable,
    ActionRecommendation,
)
from cga_bench.agent_rules.sepsis_rules import SepsisDecisionTable
from cga_bench.agent_rules.chest_pain_rules import ChestPainDecisionTable
from cga_bench.agent_rules.aki_rules import AKIDecisionTable
from cga_bench.agent_rules.heart_failure_rules import HeartFailureDecisionTable
from cga_bench.agent_rules.stroke_rules import StrokeDecisionTable
from cga_bench.agent_rules.dka_rules import DKADecisionTable
from cga_bench.agent_rules.pe_rules import PEDecisionTable
from cga_bench.agent_rules.af_rules import AFDecisionTable
from cga_bench.agent_rules.copd_rules import COPDDecisionTable
from cga_bench.agent_rules.gi_bleeding_rules import GIBleedingDecisionTable
from cga_bench.agent_rules.htn_emergency_rules import HTNEmergencyDecisionTable

logger = logging.getLogger(__name__)


@dataclass
class OracleConfig(AgentConfig):
    """Oracle 에이전트 설정"""
    agent_type: str = "oracle"
    # 규칙 기반 설정 (CPG-Engine 사용하지 않음)
    guideline_domain: str = "sepsis"  # sepsis, chest_pain, aki
    # Oracle은 LLM 사용 안함
    use_llm: bool = False


class OracleAgent(BaseAgent):
    """
    Rule-based Oracle Agent: 독립적 규칙 기반 의사결정

    특징:
    1. 채점용 CPG-Engine과 완전히 분리된 독립적 규칙 시스템 사용
    2. LLM 없이 순수 규칙 기반
    3. 벤치마크 상한선(Upper Bound) - 비교 참고치로만 사용
    4. 동일 CPG 텍스트 참조하되, 독립적으로 구현된 Decision Table 사용

    중요:
    - 이 에이전트는 "우리가 만든 엔진으로 우리가 이겼다" 비판을 방지하기 위해
      채점용 CPG-Engine(cpg_engine/)을 직접 사용하지 않습니다.
    - 대신 agent_rules/의 독립적인 규칙 시스템을 사용합니다.

    용도:
    - 다른 에이전트와의 비교 기준 (이론적 상한)
    - 시나리오 검증
    - 벤치마크 공정성 검증
    """

    def __init__(self, config: OracleConfig):
        """
        Oracle 에이전트 초기화

        Args:
            config: Oracle 설정

        Note:
            cpg_engine 인자를 받지 않습니다. 이는 의도적인 설계입니다.
            Oracle은 채점용 엔진과 분리된 독립적 규칙 시스템만 사용합니다.
        """
        super().__init__(config)
        self.oracle_config = config

        # 독립적 규칙 시스템 초기화 (채점용 CPG-Engine 아님)
        self.decision_table: Optional[RuleBasedDecisionTable] = None
        self._init_decision_table(config.guideline_domain)

        # 상태 추적
        self._completed_action_ids: Set[str] = set()
        self._action_history: List[Action] = []

    # 도메인 -> Decision Table 클래스 매핑 (명시적 키 기반)
    _DOMAIN_TABLE_MAP: Dict[str, type] = {
        # Sepsis (SSC 2021)
        "sepsis": SepsisDecisionTable,
        "ssc": SepsisDecisionTable,
        "septic_shock": SepsisDecisionTable,
        "ssc_sepsis": SepsisDecisionTable,
        "ssc_sepsis_hour1_bundle": SepsisDecisionTable,
        # Chest Pain (AHA 2021)
        "chest_pain": ChestPainDecisionTable,
        "aha_chest_pain": ChestPainDecisionTable,
        "stemi": ChestPainDecisionTable,
        "nstemi": ChestPainDecisionTable,
        "aha_chest_pain_stemi": ChestPainDecisionTable,
        "aha_chest_pain_nstemi": ChestPainDecisionTable,
        "aha_chest_pain_evaluation": ChestPainDecisionTable,
        # AKI (KDIGO)
        "aki": AKIDecisionTable,
        "kdigo": AKIDecisionTable,
        "kidney": AKIDecisionTable,
        "kdigo_aki": AKIDecisionTable,
        "kdigo_contrast_aki": AKIDecisionTable,
        "contrast_aki": AKIDecisionTable,
        # Heart Failure (AHA 2022)
        "heart_failure": HeartFailureDecisionTable,
        "hf": HeartFailureDecisionTable,
        "hfref": HeartFailureDecisionTable,
        "hfpef": HeartFailureDecisionTable,
        "adhf": HeartFailureDecisionTable,
        "cardiogenic_shock": HeartFailureDecisionTable,
        "aha_heart_failure": HeartFailureDecisionTable,
        # Stroke (AHA 2019)
        "stroke": StrokeDecisionTable,
        "aha_stroke": StrokeDecisionTable,
        "ischemic_stroke": StrokeDecisionTable,
        "hemorrhagic_stroke": StrokeDecisionTable,
        "tpa": StrokeDecisionTable,
        "thrombectomy": StrokeDecisionTable,
        # DKA (ADA 2024)
        "dka": DKADecisionTable,
        "ada_dka": DKADecisionTable,
        "dka_management": DKADecisionTable,
        "ada_dka_management": DKADecisionTable,
        "diabetic_ketoacidosis": DKADecisionTable,
        # Pulmonary Embolism (ESC 2019)
        "pulmonary_embolism": PEDecisionTable,
        "pe": PEDecisionTable,
        "esc_pe": PEDecisionTable,
        # Atrial Fibrillation (ESC 2020)
        "atrial_fibrillation": AFDecisionTable,
        "af": AFDecisionTable,
        "esc_af": AFDecisionTable,
        # COPD Exacerbation (GOLD 2024)
        "copd": COPDDecisionTable,
        "copd_exacerbation": COPDDecisionTable,
        "gold_copd": COPDDecisionTable,
        # GI Bleeding (ACG 2021)
        "gi_bleeding": GIBleedingDecisionTable,
        "gi_bleed": GIBleedingDecisionTable,
        "acg_gi_bleeding": GIBleedingDecisionTable,
        # Hypertensive Emergency (AHA 2017)
        "hypertensive_emergency": HTNEmergencyDecisionTable,
        "htn_emergency": HTNEmergencyDecisionTable,
        "aha_htn": HTNEmergencyDecisionTable,
    }

    def _init_decision_table(self, domain: str):
        """
        도메인별 독립적 Decision Table 초기화 (명시적 매핑 기반)

        이 테이블들은 채점용 CPG-Engine과 완전히 독립적으로 구현되었습니다.
        동일한 CPG 가이드라인 텍스트를 참조하지만, 그래프 구조/노드ID를 공유하지 않습니다.
        """
        domain_key = domain.lower().strip()
        table_cls = self._DOMAIN_TABLE_MAP.get(domain_key)

        if table_cls:
            self.decision_table = table_cls()
            logger.info(f"Oracle initialized with {table_cls.__name__} for domain '{domain}'")
        else:
            valid_domains = sorted(set(self._DOMAIN_TABLE_MAP.keys()))
            raise ValueError(
                f"Unknown domain '{domain}' for Oracle agent. "
                f"Valid domains: {valid_domains}. "
                f"Please use an explicit domain key from the supported list."
            )

    def reset(self):
        """에이전트 상태 리셋"""
        self._completed_action_ids = set()
        self._action_history = []
        self.metrics = AgentMetrics()
        if self.decision_table:
            self.decision_table.reset()

    def decide(self, observation: Observation) -> List[Action]:
        """
        독립적 규칙 기반 행동 결정

        알고리즘:
        1. 환자 상태를 컨텍스트로 변환
        2. 독립적 Decision Table에서 권고 행동 획득
        3. 금기 행동 회피
        4. 우선순위 및 데드라인 기준 정렬
        5. 선행 조건 준수

        Note:
            채점용 CPG-Engine을 사용하지 않습니다.
            대신 agent_rules/의 독립적 Decision Table을 사용합니다.
        """
        context = self._observation_to_context(observation)
        current_time = observation.timestamp_minutes

        if not self.decision_table:
            logger.warning("No decision table available, returning empty actions")
            return []

        # 독립적 Decision Table에서 권고 행동 획득
        recommendations = self.decision_table.get_recommended_actions(
            context, int(current_time)
        )

        # 금기 행동 목록
        forbidden_actions = self.decision_table.get_forbidden_actions(context)

        # 권고를 Action 객체로 변환
        actions = []
        for rec in recommendations:
            if rec.action_id in self._completed_action_ids:
                continue

            if rec.action_id in forbidden_actions:
                continue

            if rec.is_forbidden:
                continue

            # Action 생성
            action = self._recommendation_to_action(rec, current_time)
            if action:
                actions.append(action)
                self._completed_action_ids.add(action.action_id)
                self.decision_table.record_action(action.action_id, int(current_time))

                if len(actions) >= self.config.max_actions_per_step:
                    break

        # 행동 이력 업데이트
        self._action_history.extend(actions)

        return actions

    def _observation_to_context(self, observation: Observation) -> Dict[str, Any]:
        """Observation을 Decision Table 컨텍스트로 변환"""
        state = observation.visible_state

        context = {
            "timestamp_minutes": observation.timestamp_minutes,
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

                    # 특수 케이스
                    if "lactate" in test_code:
                        context["lactate"] = value
                    elif "creatinine" in test_code:
                        context["creatinine"] = value
                    elif "potassium" in test_code:
                        context["potassium"] = value
                    elif "troponin" in test_code:
                        context["troponin"] = value
                        context["troponin_elevated"] = (
                            isinstance(value, (int, float)) and value > 0.04
                        )

        # ECG 결과 추출
        for img in state.get("imaging_results", []):
            if isinstance(img, dict):
                img_type = img.get("imaging_type", "").lower()
                result = img.get("result", "").lower()

                if "ecg" in img_type:
                    context["ecg_result"] = result
                    context["ecg_stemi"] = "st elevation" in result or "stemi" in result
                    context["ecg_inferior_stemi"] = "inferior" in result and context["ecg_stemi"]

                    # RV involvement 체크 (V4R)
                    if "v4r" in result and "st elevation" in result:
                        context["rv_involvement"] = True

        # N8 Fix: 수액/승압제 상태를 단일 루프로 확인
        for med in state.get("medications_given", []):
            if isinstance(med, dict):
                med_code = med.get("medication_code", "").lower()
                if "crystalloid" in med_code or "saline" in med_code:
                    context["fluid_resuscitation_complete"] = True
                if "norepinephrine" in med_code or "vasopressor" in med_code:
                    context["vasopressor_started"] = True

        return context

    def _recommendation_to_action(
        self,
        rec: ActionRecommendation,
        current_time: float
    ) -> Optional[Action]:
        """ActionRecommendation을 Action 객체로 변환"""

        # 행동 타입 매핑
        action_type_map = {
            "order_lab": ActionType.ORDER_LAB,
            "order_diagnostic": ActionType.ORDER_IMAGING,
            "give_medication": ActionType.GIVE_MEDICATION,
            "procedure": ActionType.PROCEDURE,
            "consult": ActionType.CONSULT,
            "assessment": ActionType.REASSESS,
            "monitoring": ActionType.ORDER_LAB,
            "medication_review": ActionType.REASSESS,
            "decision": ActionType.REASSESS,
            "medication_preference": ActionType.REASSESS,
            "protocol": ActionType.REASSESS,
            "contraindication": ActionType.REASSESS,
            "disposition": ActionType.DISPOSITION,
        }

        action_type = action_type_map.get(rec.action_type, ActionType.ORDER_LAB)

        # args 정규화 (환경이 기대하는 키로 변환)
        args = dict(rec.parameters) if rec.parameters else {}
        if action_type == ActionType.GIVE_MEDICATION:
            # medication_class -> medication_code 변환
            if "medication_class" in args and "medication_code" not in args:
                args["medication_code"] = args.pop("medication_class")
            # medication_code 기본값 설정
            if "medication_code" not in args:
                args["medication_code"] = rec.action_id.replace("_", " ")
            # dose 기본값 설정
            if "dose" not in args:
                args["dose"] = "standard dose"
        elif action_type == ActionType.ORDER_LAB:
            if "test_code" not in args:
                args["test_code"] = rec.action_id
        elif action_type == ActionType.ORDER_IMAGING:
            if "imaging_type" not in args:
                args["imaging_type"] = rec.action_id

        # justification에 출처 포함
        justification_parts = [f"Oracle (Upper Bound): {rec.action_id}"]
        if rec.source_guideline:
            justification_parts.append(f"Source: {rec.source_guideline}")
        if rec.evidence_level:
            justification_parts.append(f"Evidence: {rec.evidence_level}")

        return Action(
            type=action_type,
            action_id=rec.action_id,
            args=args,
            timestamp_minutes=current_time,
            justification=" | ".join(justification_parts)
        )

    def get_oracle_status(self) -> Dict[str, Any]:
        """Oracle 상태 반환 (디버깅/분석용)"""
        status = {
            "completed_actions": list(self._completed_action_ids),
            "action_count": len(self._action_history),
            "llm_calls": 0,  # Oracle은 LLM 사용 안함
            "agent_type": "oracle_rule_based_independent",
            "uses_cpg_engine": False,  # 명시적으로 CPG-Engine 미사용
            "decision_table_type": type(self.decision_table).__name__ if self.decision_table else None,
        }

        if self.decision_table:
            status["decision_table_status"] = self.decision_table.get_status()

        return status

    def get_independence_verification(self) -> Dict[str, Any]:
        """
        독립성 검증 정보 반환

        이 메서드는 Oracle이 채점용 CPG-Engine과 독립적임을 검증하기 위한 정보를 제공합니다.
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
            "metadata_reuse": False,
            "verification_note": (
                "This Oracle uses an independently implemented rule-based system "
                "that references the same CPG guidelines as the scoring engine, "
                "but does NOT share graph structure, node IDs, or metadata. "
                "This design prevents the 'scoring with our own engine' criticism."
            ),
        }
