"""
GI Bleeding Decision Table: ACG 2021 가이드라인 기반 독립적 규칙

출처: ACG Clinical Guideline: Management of Patients with Acute Lower Gastrointestinal Bleeding (2023)
      ACG Clinical Guideline: Upper Gastrointestinal and Ulcer Bleeding (2021)
DOI: 10.14309/ajg.0000000000001136

이 규칙은 CPG-Engine의 그래프 구조와 완전히 독립적으로 구현되었습니다.
"""

from typing import Dict, Any, List
from cga_bench.agent_rules.decision_table import (
    RuleBasedDecisionTable,
    ClinicalRuleSet,
    DecisionTableEntry,
    ClinicalCondition,
    ActionRecommendation,
    ConditionOperator,
)


class GIBleedingDecisionTable(RuleBasedDecisionTable):
    """
    ACG 2021 기반 GI Bleeding 의사결정 테이블

    참조 가이드라인:
    - ACG 2021 Upper GI Bleeding Guidelines
    - ACG 2023 Lower GI Bleeding Guidelines

    이 구현은 채점용 CPG-Engine과 완전히 독립적입니다.
    """

    def _load_rulesets(self) -> None:
        """ACG GI 출혈 규칙 로드"""

        ruleset = ClinicalRuleSet(
            ruleset_id="acg_gi_bleeding_2021",
            name="ACG 2021 GI Bleeding Management",
            description="급성 위장관 출혈 초기 소생 및 평가 가이드라인",
            source_guidelines=[
                "ACG 2021 Upper GI Bleeding Guidelines",
                "DOI:10.14309/ajg.0000000000001136",
            ],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_vital_signs",
                    action_type="assessment",
                    parameters={"type": "vital_signs"},
                    priority=100,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="ACG 2021",
                    source_recommendation="Initial assessment",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="assess_hemodynamic_status",
                    action_type="assessment",
                    parameters={"type": "hemodynamic_stability"},
                    priority=95,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="ACG 2021",
                    source_recommendation="Hemodynamic assessment — shock index",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="establish_iv_access",
                    action_type="procedure",
                    parameters={"type": "large_bore_iv_access", "gauge": "18G_or_larger"},
                    priority=90,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="ACG 2021",
                    source_recommendation="Two large-bore IV access",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_lab_cbc",
                    action_type="order_lab",
                    parameters={"test_code": "complete_blood_count"},
                    priority=88,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="ACG 2021",
                    source_recommendation="CBC — hemoglobin, platelet",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_lab_bmp",
                    action_type="order_lab",
                    parameters={"test_code": "basic_metabolic_panel"},
                    priority=85,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="ACG 2021",
                    source_recommendation="BMP — BUN/creatinine ratio",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_type_and_crossmatch",
                    action_type="order_lab",
                    parameters={"test_code": "type_and_crossmatch"},
                    priority=83,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="ACG 2021",
                    source_recommendation="Type and crossmatch for transfusion preparation",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="give_iv_crystalloid_bolus",
                    action_type="give_medication",
                    parameters={
                        "medication_code": "crystalloid",
                        "dose": "1L_bolus",
                    },
                    priority=80,
                    deadline_minutes=30,
                    is_mandatory=True,
                    required_prior_actions=["establish_iv_access"],
                    source_guideline="ACG 2021",
                    source_recommendation="IV fluid resuscitation for hemodynamic instability",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="give_iv_ppi",
                    action_type="give_medication",
                    parameters={
                        "medication_class": "proton_pump_inhibitor",
                        "route": "intravenous",
                    },
                    priority=75,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="ACG 2021",
                    source_recommendation="IV PPI reduces need for endoscopic intervention",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="consult_gi",
                    action_type="consult",
                    parameters={"specialty": "gastroenterology"},
                    priority=70,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="ACG 2021",
                    source_recommendation="Early GI consultation",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="delay_resuscitation",
                    action_type="delay",
                    is_forbidden=True,
                    source_guideline="ACG 2021",
                    source_recommendation="Strong recommendation against delaying resuscitation in GI bleed",
                ),
            ],

            decision_entries=[
                # Hgb < 7: 농축 적혈구 수혈
                DecisionTableEntry(
                    entry_id="prbc_transfusion_low_hgb",
                    description="Hgb < 7 g/dL 시 농축 적혈구 수혈",
                    conditions=[
                        ClinicalCondition(
                            variable="hemoglobin",
                            operator=ConditionOperator.LESS_THAN,
                            value=7.0,
                            description="Hemoglobin < 7 g/dL",
                            source_guideline="ACG 2021",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_packed_rbc_if_hgb_below_7",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "packed_rbc",
                                "target_hgb": "7-9 g/dL",
                            },
                            priority=85,
                            deadline_minutes=60,
                            is_mandatory=True,
                            required_prior_actions=["order_type_and_crossmatch"],
                            source_guideline="ACG 2021",
                            source_recommendation="Restrictive transfusion strategy — transfuse at Hgb < 7",
                            evidence_level="1A",
                        ),
                    ],
                    priority=85,
                    source_guideline="ACG 2021",
                ),

                # 혈역학적 안정화 후 내시경
                DecisionTableEntry(
                    entry_id="endoscopy_after_stabilization",
                    description="소생 후 24시간 내 상부위장관 내시경",
                    conditions=[
                        ClinicalCondition(
                            variable="hemodynamic_stable",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Hemodynamically stable after resuscitation",
                            source_guideline="ACG 2021",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="perform_endoscopy",
                            action_type="procedure",
                            parameters={"type": "upper_endoscopy", "timing": "within_24h"},
                            priority=70,
                            deadline_minutes=1440,
                            is_mandatory=True,
                            required_prior_actions=["consult_gi"],
                            source_guideline="ACG 2021",
                            source_recommendation="Early endoscopy within 24h reduces LOS",
                            evidence_level="1B",
                        ),
                    ],
                    priority=70,
                    source_guideline="ACG 2021",
                ),
            ],

            allergy_contraindications={},

            comorbidity_contraindications={
                "coagulopathy": ["nsaid", "aspirin"],
                "ckd_stage_5": ["nsaid"],
            },
        )

        self.rulesets["default"] = ruleset

    def _determine_scenario_type(self, context: Dict[str, Any]) -> str:
        """시나리오 유형 결정 (단일 기본 룰셋 사용)"""
        return "default"
