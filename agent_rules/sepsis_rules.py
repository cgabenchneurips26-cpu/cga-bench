"""Sepsis Decision Table: SSC 2021 가이드라인 기반 독립적 규칙

출처: Surviving Sepsis Campaign: International Guidelines 2021
DOI: 10.1097/CCM.0000000000005337

이 규칙은 CPG-Engine의 그래프 구조와 완전히 독립적으로 구현되었습니다.
동일한 가이드라인 텍스트를 참조하지만, 노드ID/메타데이터를 재사용하지 않습니다.
"""

from typing import Any

from cga_bench.agent_rules.decision_table import (
    ActionRecommendation,
    ClinicalCondition,
    ClinicalRuleSet,
    ConditionOperator,
    DecisionTableEntry,
    RuleBasedDecisionTable,
)


class SepsisDecisionTable(RuleBasedDecisionTable):
    """SSC 2021 기반 Sepsis 의사결정 테이블

    참조 가이드라인:
    - SSC 2021 Hour-1 Bundle
    - SSC 2021 Septic Shock Management

    이 구현은 채점용 CPG-Engine과 완전히 독립적입니다.
    """

    def _load_rulesets(self):
        """SSC 2021 규칙 로드"""
        # ========================================
        # Septic Shock Ruleset
        # ========================================
        septic_shock_ruleset = ClinicalRuleSet(
            ruleset_id="ssc_septic_shock",
            name="SSC 2021 Septic Shock Hour-1 Bundle",
            description="패혈성 쇼크 환자를 위한 1시간 번들",
            source_guidelines=["SSC 2021", "DOI:10.1097/CCM.0000000000005337"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_infection_source",
                    action_type="assessment",
                    parameters={"type": "infection_source"},
                    priority=101,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="SSC 2021",
                    source_recommendation="Initial Recognition",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="assess_organ_dysfunction",
                    action_type="assessment",
                    parameters={"type": "organ_dysfunction"},
                    priority=100,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="SSC 2021",
                    source_recommendation="Initial Recognition",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="measure_lactate",
                    action_type="order_lab",
                    parameters={"test_code": "lactate"},
                    priority=99,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="SSC 2021",
                    source_recommendation="Hour-1 Bundle Item 1",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="blood_culture_before_antibiotics",
                    action_type="order_lab",
                    parameters={"test_code": "blood_culture"},
                    priority=95,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="SSC 2021",
                    source_recommendation="Hour-1 Bundle Item 2",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="broad_spectrum_antibiotics",
                    action_type="give_medication",
                    parameters={"medication_class": "broad_spectrum_antibiotic"},
                    priority=90,
                    deadline_minutes=60,
                    is_mandatory=True,
                    required_prior_actions=["blood_culture_before_antibiotics"],
                    source_guideline="SSC 2021",
                    source_recommendation="Hour-1 Bundle Item 3",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="delay_antibiotics_over_3h",
                    action_type="delay",
                    is_forbidden=True,
                    source_guideline="SSC 2021",
                    source_recommendation="Strong recommendation against delay",
                ),
            ],

            decision_entries=[
                # MAP < 65 또는 저혈압 시 수액 소생
                DecisionTableEntry(
                    entry_id="fluid_resuscitation_hypotension",
                    description="저혈압 시 수액 소생",
                    conditions=[
                        ClinicalCondition(
                            variable="map_mmhg",
                            operator=ConditionOperator.LESS_THAN,
                            value=65,
                            description="MAP < 65 mmHg",
                            source_guideline="SSC 2021",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="crystalloid_30ml_kg",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "crystalloid",
                                "dose": "30ml/kg",
                            },
                            priority=85,
                            deadline_minutes=60,
                            is_mandatory=True,
                            source_guideline="SSC 2021",
                            source_recommendation="Hour-1 Bundle Item 4",
                            evidence_level="1B",
                        ),
                    ],
                    priority=90,
                    source_guideline="SSC 2021",
                ),

                # 수액 불응성 저혈압 시 승압제
                DecisionTableEntry(
                    entry_id="vasopressor_refractory_hypotension",
                    description="수액 불응성 저혈압 시 승압제",
                    conditions=[
                        ClinicalCondition(
                            variable="map_mmhg",
                            operator=ConditionOperator.LESS_THAN,
                            value=65,
                            description="MAP < 65 mmHg after fluids",
                        ),
                        ClinicalCondition(
                            variable="fluid_resuscitation_complete",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="수액 소생 완료",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="start_norepinephrine",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "norepinephrine",
                                "target": "MAP >= 65",
                            },
                            priority=80,
                            deadline_minutes=60,
                            is_mandatory=True,
                            required_prior_actions=["crystalloid_30ml_kg"],
                            source_guideline="SSC 2021",
                            source_recommendation="First-line vasopressor",
                            evidence_level="1B",
                        ),
                    ],
                    priority=85,
                    source_guideline="SSC 2021",
                ),

                # Lactate > 2 시 재측정
                DecisionTableEntry(
                    entry_id="remeasure_lactate_if_elevated",
                    description="Lactate > 2 시 2-4시간 내 재측정",
                    conditions=[
                        ClinicalCondition(
                            variable="lactate",
                            operator=ConditionOperator.GREATER_THAN,
                            value=2,
                            description="Lactate > 2 mmol/L",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="remeasure_lactate",
                            action_type="order_lab",
                            parameters={"test_code": "lactate"},
                            priority=70,
                            deadline_minutes=240,  # 4시간
                            is_mandatory=True,
                            required_prior_actions=["measure_lactate"],
                            source_guideline="SSC 2021",
                            source_recommendation="Hour-1 Bundle Item 5",
                            evidence_level="2C",
                        ),
                    ],
                    priority=70,
                    source_guideline="SSC 2021",
                ),
            ],

            allergy_contraindications={
                "penicillin": [
                    "ampicillin",
                    "amoxicillin",
                    "piperacillin",
                    "piperacillin_tazobactam",
                ],
                "sulfa": [
                    "trimethoprim_sulfamethoxazole",
                ],
                "cephalosporin": [
                    "ceftriaxone",
                    "cefepime",
                    "cefazolin",
                ],
            },

            comorbidity_contraindications={
                "ckd_stage_4": ["nsaid", "aminoglycoside_high_dose"],
                "ckd_stage_5": ["nsaid", "aminoglycoside", "contrast_without_precaution"],
                "heart_failure": ["aggressive_fluid_bolus", "nsaid"],
            },
        )

        # ========================================
        # Sepsis without Shock Ruleset
        # ========================================
        sepsis_ruleset = ClinicalRuleSet(
            ruleset_id="ssc_sepsis",
            name="SSC 2021 Sepsis Management",
            description="쇼크 없는 패혈증 환자 관리",
            source_guidelines=["SSC 2021"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="measure_lactate",
                    action_type="order_lab",
                    parameters={"test_code": "lactate"},
                    priority=100,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="SSC 2021",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="blood_culture_before_antibiotics",
                    action_type="order_lab",
                    parameters={"test_code": "blood_culture"},
                    priority=95,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="SSC 2021",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="broad_spectrum_antibiotics",
                    action_type="give_medication",
                    parameters={"medication_class": "broad_spectrum_antibiotic"},
                    priority=90,
                    deadline_minutes=180,  # 3시간 (shock 없음)
                    is_mandatory=True,
                    required_prior_actions=["blood_culture_before_antibiotics"],
                    source_guideline="SSC 2021",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[],

            decision_entries=[
                # 저혈압 시 수액
                DecisionTableEntry(
                    entry_id="fluid_if_hypotension",
                    description="저혈압 시 수액 투여",
                    conditions=[
                        ClinicalCondition(
                            variable="sbp_mmhg",
                            operator=ConditionOperator.LESS_THAN,
                            value=90,
                            description="SBP < 90 mmHg",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="crystalloid_bolus",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "crystalloid",
                                "dose": "500ml bolus",
                            },
                            priority=80,
                            is_mandatory=False,
                            source_guideline="SSC 2021",
                        ),
                    ],
                    priority=80,
                    source_guideline="SSC 2021",
                ),
            ],

            allergy_contraindications={
                "penicillin": ["ampicillin", "amoxicillin", "piperacillin"],
            },

            comorbidity_contraindications={
                "ckd_stage_4": ["nsaid"],
            },
        )

        self.rulesets["septic_shock"] = septic_shock_ruleset
        self.rulesets["sepsis"] = sepsis_ruleset

    def _determine_scenario_type(self, context: dict[str, Any]) -> str:
        """시나리오 유형 결정"""
        # 패혈성 쇼크 기준: MAP < 65 또는 승압제 필요 또는 Lactate > 2
        map_mmhg = context.get("map_mmhg", 100)
        lactate = context.get("lactate", 0)
        vasopressor_required = context.get("vasopressor_required", False)
        diagnosis = (context.get("working_diagnosis") or "").lower()

        # Type safety: convert to numeric or use defaults
        try:
            map_mmhg = float(map_mmhg) if map_mmhg not in (None, "pending", "") else 100
        except (ValueError, TypeError):
            map_mmhg = 100

        try:
            lactate = float(lactate) if lactate not in (None, "pending", "") else 0
        except (ValueError, TypeError):
            lactate = 0

        if "septic_shock" in diagnosis:
            return "septic_shock"

        if map_mmhg < 65 or vasopressor_required or lactate > 2:
            return "septic_shock"

        return "sepsis"
