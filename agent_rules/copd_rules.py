"""
COPD Exacerbation Decision Table: GOLD 2024 가이드라인 기반 독립적 규칙

출처: Global Initiative for Chronic Obstructive Lung Disease 2024 Report
URL: https://goldcopd.org/2024-gold-report/

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


class COPDDecisionTable(RuleBasedDecisionTable):
    """
    GOLD 2024 기반 COPD Exacerbation 의사결정 테이블

    참조 가이드라인:
    - GOLD 2024 AECOPD Management
    - NIV 적응증 기준

    이 구현은 채점용 CPG-Engine과 완전히 독립적입니다.
    """

    def _load_rulesets(self) -> None:
        """GOLD 2024 COPD 급성 악화 규칙 로드"""

        ruleset = ClinicalRuleSet(
            ruleset_id="gold_copd_2024",
            name="GOLD 2024 COPD Acute Exacerbation Management",
            description="COPD 급성 악화 평가 및 치료 가이드라인",
            source_guidelines=[
                "GOLD 2024 Report",
                "URL:https://goldcopd.org/2024-gold-report/",
            ],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_vital_signs",
                    action_type="assessment",
                    parameters={"type": "vital_signs"},
                    priority=100,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="GOLD 2024",
                    source_recommendation="Initial assessment",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="assess_respiratory_status",
                    action_type="assessment",
                    parameters={"type": "respiratory_status"},
                    priority=95,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="GOLD 2024",
                    source_recommendation="Severity assessment — dyspnea, RR, SpO2",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_lab_abg",
                    action_type="order_lab",
                    parameters={"test_code": "arterial_blood_gas"},
                    priority=90,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="GOLD 2024",
                    source_recommendation="ABG to assess respiratory failure and acid-base",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_lab_bmp",
                    action_type="order_lab",
                    parameters={"test_code": "basic_metabolic_panel"},
                    priority=85,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="GOLD 2024",
                    source_recommendation="Metabolic panel",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_imaging_chest_xray",
                    action_type="order_imaging",
                    parameters={"modality": "chest_xray"},
                    priority=80,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="GOLD 2024",
                    source_recommendation="CXR to exclude alternative diagnoses",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="give_bronchodilator",
                    action_type="give_medication",
                    parameters={"medication_class": "short_acting_bronchodilator"},
                    priority=90,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="GOLD 2024",
                    source_recommendation="SABA/SAMA bronchodilators — first-line",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="give_systemic_corticosteroid",
                    action_type="give_medication",
                    parameters={
                        "medication_code": "prednisolone",
                        "dose": "40mg",
                        "duration_days": 5,
                    },
                    priority=80,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="GOLD 2024",
                    source_recommendation="Systemic corticosteroids shorten recovery",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="give_supplemental_oxygen",
                    action_type="give_medication",
                    parameters={
                        "medication_code": "oxygen",
                        "target_spo2": "88-92%",
                    },
                    priority=85,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="GOLD 2024",
                    source_recommendation="Controlled O2 — target SpO2 88-92%",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_high_flow_oxygen_without_monitoring",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="GOLD 2024",
                    source_recommendation="Uncontrolled high-flow O2 may cause hypercapnic respiratory failure",
                ),
            ],

            decision_entries=[
                # 항생제 적응증: 농성 가래 또는 감염 징후
                DecisionTableEntry(
                    entry_id="antibiotics_purulent_sputum",
                    description="농성 가래 또는 감염 징후 시 항생제 투여",
                    conditions=[
                        ClinicalCondition(
                            variable="purulent_sputum",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Purulent sputum or signs of infection",
                            source_guideline="GOLD 2024",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_antibiotics",
                            action_type="give_medication",
                            parameters={"medication_class": "antibiotic"},
                            priority=75,
                            deadline_minutes=120,
                            is_mandatory=True,
                            source_guideline="GOLD 2024",
                            source_recommendation="Antibiotics for purulent exacerbation",
                            evidence_level="1B",
                        ),
                    ],
                    priority=75,
                    source_guideline="GOLD 2024",
                ),

                # NIV 적응증: pH < 7.35 또는 PaCO2 > 45
                DecisionTableEntry(
                    entry_id="niv_respiratory_acidosis",
                    description="호흡성 산증(pH < 7.35) 또는 고탄산혈증 시 NIV 평가 및 시작",
                    conditions=[
                        ClinicalCondition(
                            variable="arterial_ph",
                            operator=ConditionOperator.LESS_THAN,
                            value=7.35,
                            description="Respiratory acidosis pH < 7.35",
                            source_guideline="GOLD 2024",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="assess_niv_eligibility",
                            action_type="assessment",
                            parameters={"type": "niv_contraindications"},
                            priority=90,
                            deadline_minutes=30,
                            is_mandatory=True,
                            required_prior_actions=["order_lab_abg"],
                            source_guideline="GOLD 2024",
                            source_recommendation="NIV assessment for acute hypercapnic respiratory failure",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="initiate_niv",
                            action_type="procedure",
                            parameters={"type": "non_invasive_ventilation"},
                            priority=85,
                            deadline_minutes=60,
                            is_mandatory=True,
                            required_prior_actions=["assess_niv_eligibility"],
                            source_guideline="GOLD 2024",
                            source_recommendation="NIV reduces mortality in AECOPD with acidosis",
                            evidence_level="1A",
                        ),
                    ],
                    priority=90,
                    source_guideline="GOLD 2024",
                ),
            ],

            allergy_contraindications={
                "penicillin": ["amoxicillin", "amoxicillin_clavulanate"],
            },

            comorbidity_contraindications={
                "bullous_emphysema": ["niv_high_pressure"],
                "copd_stable": ["systemic_corticosteroid_long_term"],
            },
        )

        self.rulesets["default"] = ruleset

    def _determine_scenario_type(self, context: Dict[str, Any]) -> str:
        """시나리오 유형 결정 (단일 기본 룰셋 사용)"""
        return "default"
