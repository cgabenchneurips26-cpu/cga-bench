"""
Atrial Fibrillation Decision Table: ESC AF 2020 가이드라인 기반 독립적 규칙

출처: 2020 ESC Guidelines for the diagnosis and management of atrial fibrillation
DOI: 10.1093/eurheartj/ehaa612

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


class AFDecisionTable(RuleBasedDecisionTable):
    """
    ESC AF 2020 기반 Atrial Fibrillation 의사결정 테이블

    참조 가이드라인:
    - ESC 2020 AF Guidelines
    - CHA2DS2-VASc 기반 항응고 치료

    이 구현은 채점용 CPG-Engine과 완전히 독립적입니다.
    """

    def _load_rulesets(self) -> None:
        """ESC AF 2020 규칙 로드"""

        ruleset = ClinicalRuleSet(
            ruleset_id="esc_af_2020",
            name="ESC 2020 Atrial Fibrillation Management",
            description="심방세동 진단 및 치료 가이드라인",
            source_guidelines=[
                "ESC 2020 AF Guidelines",
                "DOI:10.1093/eurheartj/ehaa612",
            ],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_vital_signs",
                    action_type="assessment",
                    parameters={"type": "vital_signs"},
                    priority=100,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="ESC 2020 AF Guidelines",
                    source_recommendation="Initial assessment",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_ecg",
                    action_type="order_imaging",
                    parameters={"modality": "12_lead_ecg"},
                    priority=95,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="ESC 2020 AF Guidelines",
                    source_recommendation="ECG confirmation of AF",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="assess_chadsvasc_score",
                    action_type="assessment",
                    parameters={"type": "chadsvasc"},
                    priority=85,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="ESC 2020 AF Guidelines",
                    source_recommendation="Stroke risk assessment — CHA2DS2-VASc",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="assess_anticoagulation_need",
                    action_type="assessment",
                    parameters={"type": "anticoagulation_eligibility"},
                    priority=80,
                    deadline_minutes=60,
                    is_mandatory=True,
                    required_prior_actions=["assess_chadsvasc_score"],
                    source_guideline="ESC 2020 AF Guidelines",
                    source_recommendation="Anticoagulation decision",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="give_rate_control",
                    action_type="give_medication",
                    parameters={"medication_class": "rate_control_agent"},
                    priority=75,
                    deadline_minutes=120,
                    is_mandatory=True,
                    source_guideline="ESC 2020 AF Guidelines",
                    source_recommendation="Rate control as initial strategy",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[],

            decision_entries=[
                # CHA2DS2-VASc >= 2 (남성) 또는 >= 3 (여성): 항응고 치료 시작
                DecisionTableEntry(
                    entry_id="anticoagulation_high_stroke_risk",
                    description="고위험 뇌졸중 위험 시 항응고 치료",
                    conditions=[
                        ClinicalCondition(
                            variable="chadsvasc_score",
                            operator=ConditionOperator.GREATER_EQUAL,
                            value=2,
                            description="CHA2DS2-VASc >= 2",
                            source_guideline="ESC 2020 AF Guidelines",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_anticoagulation",
                            action_type="give_medication",
                            parameters={"medication_class": "oral_anticoagulant"},
                            priority=85,
                            deadline_minutes=120,
                            is_mandatory=True,
                            required_prior_actions=["assess_chadsvasc_score"],
                            source_guideline="ESC 2020 AF Guidelines",
                            source_recommendation="OAC recommended for CHA2DS2-VASc >= 2",
                            evidence_level="1A",
                        ),
                    ],
                    priority=85,
                    source_guideline="ESC 2020 AF Guidelines",
                ),

                # 혈역학적 불안정: 긴급 전기적 심율동전환
                DecisionTableEntry(
                    entry_id="cardioversion_hemodynamic_instability",
                    description="혈역학적 불안정 시 긴급 전기적 심율동전환",
                    conditions=[
                        ClinicalCondition(
                            variable="hemodynamic_instability",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Hemodynamic instability",
                            source_guideline="ESC 2020 AF Guidelines",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="perform_electrical_cardioversion",
                            action_type="procedure",
                            parameters={"type": "dc_cardioversion"},
                            priority=100,
                            deadline_minutes=30,
                            is_mandatory=True,
                            source_guideline="ESC 2020 AF Guidelines",
                            source_recommendation="Emergency electrical cardioversion for unstable AF",
                            evidence_level="1B",
                        ),
                    ],
                    priority=100,
                    source_guideline="ESC 2020 AF Guidelines",
                ),

                # 심부전 동반: 베타차단제 또는 디곡신
                DecisionTableEntry(
                    entry_id="rate_control_heart_failure",
                    description="심부전 동반 AF: 디곡신 또는 아미오다론으로 심박수 조절",
                    conditions=[
                        ClinicalCondition(
                            variable="heart_failure_present",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Concomitant heart failure",
                            source_guideline="ESC 2020 AF Guidelines",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_digoxin_or_amiodarone",
                            action_type="give_medication",
                            parameters={"medication_class": "digoxin_or_amiodarone"},
                            priority=70,
                            deadline_minutes=120,
                            is_mandatory=False,
                            source_guideline="ESC 2020 AF Guidelines",
                            source_recommendation="Rate control in AF with HF — digoxin or amiodarone",
                            evidence_level="2C",
                        ),
                    ],
                    priority=70,
                    source_guideline="ESC 2020 AF Guidelines",
                ),
            ],

            allergy_contraindications={
                "warfarin": ["warfarin"],
            },

            comorbidity_contraindications={
                "active_bleeding": ["give_anticoagulation"],
                "severe_renal_failure": ["dabigatran"],
            },
        )

        self.rulesets["default"] = ruleset

    def _determine_scenario_type(self, context: Dict[str, Any]) -> str:
        """시나리오 유형 결정 (단일 기본 룰셋 사용)"""
        return "default"
