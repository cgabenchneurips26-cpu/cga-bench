"""
Pulmonary Embolism Decision Table: ESC 2019 가이드라인 기반 독립적 규칙

출처: 2019 ESC Guidelines for the diagnosis and management of acute pulmonary embolism
DOI: 10.1093/eurheartj/ehz405

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


class PEDecisionTable(RuleBasedDecisionTable):
    """
    ESC 2019 기반 Pulmonary Embolism 의사결정 테이블

    참조 가이드라인:
    - ESC 2019 PE Guidelines
    - PESI / sPESI risk stratification

    이 구현은 채점용 CPG-Engine과 완전히 독립적입니다.
    """

    def _load_rulesets(self) -> None:
        """ESC 2019 PE 규칙 로드"""

        ruleset = ClinicalRuleSet(
            ruleset_id="esc_pe_2019",
            name="ESC 2019 Pulmonary Embolism Management",
            description="급성 폐색전증 진단 및 치료 가이드라인",
            source_guidelines=[
                "ESC 2019 PE Guidelines",
                "DOI:10.1093/eurheartj/ehz405",
            ],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_vital_signs",
                    action_type="assessment",
                    parameters={"type": "vital_signs"},
                    priority=100,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="ESC 2019 PE Guidelines",
                    source_recommendation="Initial assessment",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="assess_wells_score",
                    action_type="assessment",
                    parameters={"type": "wells_pe_score"},
                    priority=95,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="ESC 2019 PE Guidelines",
                    source_recommendation="Clinical probability assessment",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_lab_d_dimer",
                    action_type="order_lab",
                    parameters={"test_code": "d_dimer"},
                    priority=90,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="ESC 2019 PE Guidelines",
                    source_recommendation="Diagnostic workup — D-dimer",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_lab_troponin",
                    action_type="order_lab",
                    parameters={"test_code": "troponin"},
                    priority=85,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="ESC 2019 PE Guidelines",
                    source_recommendation="Risk stratification",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_lab_bnp",
                    action_type="order_lab",
                    parameters={"test_code": "bnp"},
                    priority=80,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="ESC 2019 PE Guidelines",
                    source_recommendation="Risk stratification — BNP/NT-proBNP",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_imaging_ct_pa",
                    action_type="order_imaging",
                    parameters={"modality": "ct_pulmonary_angiography"},
                    priority=75,
                    deadline_minutes=120,
                    is_mandatory=True,
                    source_guideline="ESC 2019 PE Guidelines",
                    source_recommendation="Confirmatory imaging — CTPA",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="give_anticoagulation",
                    action_type="give_medication",
                    parameters={"medication_class": "anticoagulant"},
                    priority=70,
                    deadline_minutes=120,
                    is_mandatory=True,
                    source_guideline="ESC 2019 PE Guidelines",
                    source_recommendation="Anticoagulation — initiate immediately",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="delay_anticoagulation",
                    action_type="delay",
                    is_forbidden=True,
                    source_guideline="ESC 2019 PE Guidelines",
                    source_recommendation="Strong recommendation against delaying anticoagulation",
                ),
            ],

            decision_entries=[
                # 대규모 PE (massive PE): 혈역학적 불안정 시 혈전 용해제
                DecisionTableEntry(
                    entry_id="thrombolysis_massive_pe",
                    description="혈역학적 불안정(대규모 PE) 시 혈전 용해제 투여",
                    conditions=[
                        ClinicalCondition(
                            variable="hemodynamic_instability",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Hemodynamic instability (massive PE)",
                            source_guideline="ESC 2019 PE Guidelines",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_thrombolysis",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "alteplase",
                                "indication": "massive_pe",
                            },
                            priority=95,
                            deadline_minutes=60,
                            is_mandatory=True,
                            required_prior_actions=["order_imaging_ct_pa"],
                            source_guideline="ESC 2019 PE Guidelines",
                            source_recommendation="Reperfusion — systemic thrombolysis for massive PE",
                            evidence_level="1B",
                        ),
                    ],
                    priority=95,
                    source_guideline="ESC 2019 PE Guidelines",
                ),

                # 저위험 PE: 경구 항응고제로 전환
                DecisionTableEntry(
                    entry_id="oral_anticoagulation_low_risk",
                    description="저위험 PE 시 경구 항응고제 전환 고려",
                    conditions=[
                        ClinicalCondition(
                            variable="pe_risk_category",
                            operator=ConditionOperator.EQUALS,
                            value="low",
                            description="Low-risk PE (sPESI = 0)",
                            source_guideline="ESC 2019 PE Guidelines",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_oral_anticoagulant",
                            action_type="give_medication",
                            parameters={"medication_class": "doac"},
                            priority=60,
                            deadline_minutes=240,
                            is_mandatory=False,
                            required_prior_actions=["give_anticoagulation"],
                            source_guideline="ESC 2019 PE Guidelines",
                            source_recommendation="Early discharge with oral anticoagulation for low-risk PE",
                            evidence_level="2B",
                        ),
                    ],
                    priority=60,
                    source_guideline="ESC 2019 PE Guidelines",
                ),
            ],

            allergy_contraindications={
                "heparin": ["unfractionated_heparin", "lmwh"],
            },

            comorbidity_contraindications={
                "active_bleeding": ["give_thrombolysis", "give_anticoagulation"],
                "recent_intracranial_surgery": ["give_thrombolysis"],
            },
        )

        self.rulesets["default"] = ruleset

    def _determine_scenario_type(self, context: Dict[str, Any]) -> str:
        """시나리오 유형 결정 (단일 기본 룰셋 사용)"""
        return "default"
