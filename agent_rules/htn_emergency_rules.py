"""
Hypertensive Emergency Decision Table: AHA 2017 가이드라인 기반 독립적 규칙

출처: 2017 ACC/AHA High Blood Pressure Guideline
DOI: 10.1161/HYP.0000000000000065

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


class HTNEmergencyDecisionTable(RuleBasedDecisionTable):
    """
    AHA 2017 기반 Hypertensive Emergency 의사결정 테이블

    참조 가이드라인:
    - 2017 ACC/AHA Hypertension Guidelines
    - 고혈압 응급 시 IV 강압제 사용 원칙

    이 구현은 채점용 CPG-Engine과 완전히 독립적입니다.
    """

    def _load_rulesets(self) -> None:
        """AHA 2017 고혈압 응급 규칙 로드"""

        ruleset = ClinicalRuleSet(
            ruleset_id="aha_htn_emergency_2017",
            name="AHA 2017 Hypertensive Emergency Management",
            description="고혈압 응급 — 표적 장기 손상 평가 및 IV 강압 치료",
            source_guidelines=[
                "2017 ACC/AHA Hypertension Guidelines",
                "DOI:10.1161/HYP.0000000000000065",
            ],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_vital_signs",
                    action_type="assessment",
                    parameters={"type": "vital_signs"},
                    priority=100,
                    deadline_minutes=5,
                    is_mandatory=True,
                    source_guideline="AHA 2017 HTN",
                    source_recommendation="Immediate BP measurement in both arms",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="assess_end_organ_damage",
                    action_type="assessment",
                    parameters={"type": "end_organ_damage"},
                    priority=95,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="AHA 2017 HTN",
                    source_recommendation="End-organ damage assessment — neurologic, cardiac, renal",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="continuous_bp_monitoring",
                    action_type="procedure",
                    parameters={"type": "intra_arterial_or_continuous_noninvasive_bp"},
                    priority=90,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="AHA 2017 HTN",
                    source_recommendation="Continuous BP monitoring during IV antihypertensive therapy",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_lab_bmp",
                    action_type="order_lab",
                    parameters={"test_code": "basic_metabolic_panel"},
                    priority=88,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="AHA 2017 HTN",
                    source_recommendation="Renal function assessment",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_lab_troponin",
                    action_type="order_lab",
                    parameters={"test_code": "troponin"},
                    priority=85,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="AHA 2017 HTN",
                    source_recommendation="Cardiac biomarkers for hypertensive emergency",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_imaging_ct_head",
                    action_type="order_imaging",
                    parameters={"modality": "ct_head_noncontrast"},
                    priority=80,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="AHA 2017 HTN",
                    source_recommendation="CT head to rule out hemorrhagic stroke",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="give_iv_antihypertensive",
                    action_type="give_medication",
                    parameters={
                        "medication_class": "iv_antihypertensive",
                        "goal": "reduce_map_by_25_percent_in_1h",
                    },
                    priority=85,
                    deadline_minutes=60,
                    is_mandatory=True,
                    required_prior_actions=["continuous_bp_monitoring"],
                    source_guideline="AHA 2017 HTN",
                    source_recommendation="IV antihypertensive — reduce MAP by 25% in first hour",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="admit_to_icu",
                    action_type="disposition",
                    parameters={"destination": "icu"},
                    priority=70,
                    deadline_minutes=120,
                    is_mandatory=True,
                    source_guideline="AHA 2017 HTN",
                    source_recommendation="ICU admission for continuous monitoring",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_oral_antihypertensive_only",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA 2017 HTN",
                    source_recommendation="Oral agents are insufficient for hypertensive emergency — use IV",
                ),
                ActionRecommendation(
                    action_id="rapid_bp_reduction",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA 2017 HTN",
                    source_recommendation="Rapid BP reduction risks end-organ ischemia — max 25% reduction in 1h",
                ),
            ],

            decision_entries=[
                # 고혈압 뇌증: IV 라베탈롤 또는 니카르디핀
                DecisionTableEntry(
                    entry_id="labetalol_or_nicardipine_encephalopathy",
                    description="고혈압 뇌증 또는 뇌졸중 시 IV 라베탈롤 또는 니카르디핀",
                    conditions=[
                        ClinicalCondition(
                            variable="end_organ_damage_type",
                            operator=ConditionOperator.IN,
                            value=["hypertensive_encephalopathy", "hemorrhagic_stroke", "ischemic_stroke"],
                            description="Neurologic end-organ damage",
                            source_guideline="AHA 2017 HTN",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_iv_labetalol",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "labetalol",
                                "route": "intravenous",
                            },
                            priority=80,
                            deadline_minutes=60,
                            is_mandatory=False,
                            required_prior_actions=["continuous_bp_monitoring"],
                            source_guideline="AHA 2017 HTN",
                            source_recommendation="IV labetalol for hypertensive encephalopathy",
                            evidence_level="1B",
                        ),
                        ActionRecommendation(
                            action_id="give_iv_nicardipine",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "nicardipine",
                                "route": "intravenous_infusion",
                            },
                            priority=80,
                            deadline_minutes=60,
                            is_mandatory=False,
                            required_prior_actions=["continuous_bp_monitoring"],
                            source_guideline="AHA 2017 HTN",
                            source_recommendation="IV nicardipine — alternative to labetalol",
                            evidence_level="1B",
                        ),
                    ],
                    priority=80,
                    source_guideline="AHA 2017 HTN",
                ),

                # 급성 심부전 동반: 니트로프루시드 또는 니트로글리세린
                DecisionTableEntry(
                    entry_id="nitroprusside_acute_heart_failure",
                    description="고혈압 응급 + 급성 심부전: 니트로프루시드 또는 니트로글리세린",
                    conditions=[
                        ClinicalCondition(
                            variable="end_organ_damage_type",
                            operator=ConditionOperator.EQUALS,
                            value="acute_heart_failure",
                            description="Acute heart failure as end-organ damage",
                            source_guideline="AHA 2017 HTN",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_iv_nitroprusside",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "sodium_nitroprusside",
                                "route": "intravenous_infusion",
                            },
                            priority=75,
                            deadline_minutes=60,
                            is_mandatory=False,
                            required_prior_actions=["continuous_bp_monitoring"],
                            source_guideline="AHA 2017 HTN",
                            source_recommendation="Sodium nitroprusside for HTN emergency with acute HF",
                            evidence_level="2C",
                        ),
                    ],
                    priority=75,
                    source_guideline="AHA 2017 HTN",
                ),
            ],

            allergy_contraindications={
                "sulfa": ["hydrochlorothiazide"],
            },

            comorbidity_contraindications={
                "aortic_dissection": ["rapid_bp_reduction"],
                "bradycardia": ["give_iv_labetalol"],
                "asthma": ["labetalol", "metoprolol"],
            },
        )

        self.rulesets["default"] = ruleset

    def _determine_scenario_type(self, context: Dict[str, Any]) -> str:
        """시나리오 유형 결정 (단일 기본 룰셋 사용)"""
        return "default"
