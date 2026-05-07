"""DKA Decision Table: ADA 2024 가이드라인 기반 독립적 규칙

출처: American Diabetes Association Standards of Care 2024
      Kitabchi AE, et al. Hyperglycemic Crises in Adult Patients With Diabetes
DOI: 10.2337/dc09-9032

이 규칙은 CPG-Engine의 그래프 구조와 완전히 독립적으로 구현되었습니다.
동일한 가이드라인 텍스트를 참조하지만, 노드ID/메타데이터를 재사용하지 않습니다.

핵심 Trap 시나리오:
1. Hypokalemia Trap (K+ < 3.3): 인슐린 투여 전 칼륨 보충 필수
2. CKD Trap (K+ > 5.5): 고칼륨혈증 시 칼륨 투여 금지
3. Euglycemic DKA Trap (SGLT2 inhibitor): 정상 혈당에서도 DKA 발생 가능
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


class DKADecisionTable(RuleBasedDecisionTable):
    """ADA 2024 기반 DKA 의사결정 테이블

    참조 가이드라인:
    - ADA Standards of Care 2024
    - Kitabchi AE, et al. Diabetes Care 2009
    - DOI: 10.2337/dc09-9032

    이 구현은 채점용 CPG-Engine과 완전히 독립적입니다.
    """

    def _load_rulesets(self):
        """ADA DKA 규칙 로드"""
        # ========================================
        # Severe DKA Ruleset (pH < 7.0 or obtunded)
        # ========================================
        severe_dka_ruleset = ClinicalRuleSet(
            ruleset_id="ada_severe_dka",
            name="ADA Severe DKA Management",
            description="중증 DKA (pH < 7.0 또는 의식 저하) 관리",
            source_guidelines=["ADA 2024", "DOI:10.2337/dc09-9032"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_vital_signs",
                    action_type="physical_exam",
                    parameters={"type": "vital_signs"},
                    priority=100,
                    deadline_minutes=5,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    source_recommendation="Initial Assessment",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="assess_mental_status",
                    action_type="physical_exam",
                    parameters={"type": "mental_status"},
                    priority=99,
                    deadline_minutes=5,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    source_recommendation="Initial Assessment",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="establish_iv_access",
                    action_type="procedure",
                    parameters={"type": "iv_access"},
                    priority=98,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    source_recommendation="Initial Assessment",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_glucose",
                    action_type="order_lab",
                    parameters={"test_code": "glucose"},
                    priority=95,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    source_recommendation="DKA Diagnosis",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_bmp",
                    action_type="order_lab",
                    parameters={"test_code": "bmp"},
                    priority=94,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    source_recommendation="DKA Diagnosis",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_ketones",
                    action_type="order_lab",
                    parameters={"test_code": "ketones"},
                    priority=93,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    source_recommendation="DKA Diagnosis",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_abg",
                    action_type="order_lab",
                    parameters={"test_code": "abg"},
                    priority=92,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    source_recommendation="DKA Diagnosis",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="start_iv_fluid_ns",
                    action_type="give_medication",
                    parameters={
                        "medication_code": "normal_saline",
                        "dose": "15-20 mL/kg/h",
                    },
                    priority=90,
                    deadline_minutes=15,
                    is_mandatory=True,
                    required_prior_actions=["establish_iv_access"],
                    source_guideline="ADA 2024",
                    source_recommendation="Fluid Therapy",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="admit_to_icu",
                    action_type="disposition",
                    parameters={"location": "icu"},
                    priority=85,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    source_recommendation="Severe DKA - ICU Admission",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="continuous_cardiac_monitoring",
                    action_type="procedure",
                    parameters={"type": "cardiac_monitor"},
                    priority=84,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    source_recommendation="Severe DKA Monitoring",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="discharge_home",
                    action_type="disposition",
                    is_forbidden=True,
                    source_guideline="ADA 2024",
                    source_recommendation="Never discharge DKA patient",
                ),
                ActionRecommendation(
                    action_id="admit_to_ward",
                    action_type="disposition",
                    is_forbidden=True,
                    source_guideline="ADA 2024",
                    source_recommendation="Severe DKA requires ICU",
                ),
                ActionRecommendation(
                    action_id="give_bicarbonate_if_ph_above_7.0",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="ADA 2024",
                    source_recommendation="Bicarbonate only if pH < 6.9",
                ),
            ],

            decision_entries=[
                # pH < 6.9일 때 bicarbonate 고려
                DecisionTableEntry(
                    entry_id="bicarbonate_for_severe_acidosis",
                    description="pH < 6.9일 때 bicarbonate 투여 고려",
                    conditions=[
                        ClinicalCondition(
                            variable="ph",
                            operator=ConditionOperator.LESS_THAN,
                            value=6.9,
                            description="pH < 6.9",
                            source_guideline="ADA 2024",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="consider_bicarbonate",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "sodium_bicarbonate",
                                "dose": "100 mmol in 400 mL with 20 mEq KCl",
                            },
                            priority=75,
                            is_mandatory=False,
                            source_guideline="ADA 2024",
                            source_recommendation="Bicarbonate Therapy",
                            evidence_level="2B",
                        ),
                    ],
                    priority=75,
                    source_guideline="ADA 2024",
                ),

                # 저칼륨혈증 시 인슐린 금지, 칼륨 보충 필수
                DecisionTableEntry(
                    entry_id="hypokalemia_trap",
                    description="K+ < 3.3 시 인슐린 금지, 칼륨 보충 필수 (CRITICAL TRAP)",
                    conditions=[
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.LESS_THAN,
                            value=3.3,
                            description="K+ < 3.3 mEq/L",
                            source_guideline="ADA 2024",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_potassium_iv",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "potassium_chloride",
                                "dose": "20-30 mEq/h",
                            },
                            priority=95,
                            deadline_minutes=30,
                            is_mandatory=True,
                            required_prior_actions=["order_lab_bmp", "establish_iv_access"],
                            source_guideline="ADA 2024",
                            source_recommendation="Potassium Therapy",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="hold_insulin_until_k_above_3.3",
                            action_type="clinical_decision",
                            parameters={"reason": "hypokalemia"},
                            priority=94,
                            is_mandatory=True,
                            source_guideline="ADA 2024",
                            source_recommendation="Hold insulin if K+ < 3.3",
                            evidence_level="1A",
                        ),
                    ],
                    priority=95,
                    source_guideline="ADA 2024",
                ),
            ],

            allergy_contraindications={},

            comorbidity_contraindications={
                "ckd_stage_4": ["aggressive_fluid_bolus"],
                "ckd_stage_5": ["aggressive_fluid_bolus"],
                "heart_failure": ["aggressive_fluid_bolus"],
            },
        )

        # ========================================
        # Moderate DKA Ruleset (pH 7.0-7.24)
        # ========================================
        moderate_dka_ruleset = ClinicalRuleSet(
            ruleset_id="ada_moderate_dka",
            name="ADA Moderate DKA Management",
            description="중등도 DKA (pH 7.0-7.24) 관리",
            source_guidelines=["ADA 2024", "DOI:10.2337/dc09-9032"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_vital_signs",
                    action_type="physical_exam",
                    parameters={"type": "vital_signs"},
                    priority=100,
                    deadline_minutes=5,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="assess_mental_status",
                    action_type="physical_exam",
                    parameters={"type": "mental_status"},
                    priority=99,
                    deadline_minutes=5,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="establish_iv_access",
                    action_type="procedure",
                    parameters={"type": "iv_access"},
                    priority=98,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_glucose",
                    action_type="order_lab",
                    parameters={"test_code": "glucose"},
                    priority=95,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_bmp",
                    action_type="order_lab",
                    parameters={"test_code": "bmp"},
                    priority=94,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_ketones",
                    action_type="order_lab",
                    parameters={"test_code": "ketones"},
                    priority=93,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_abg",
                    action_type="order_lab",
                    parameters={"test_code": "abg"},
                    priority=92,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="start_iv_fluid_ns",
                    action_type="give_medication",
                    parameters={
                        "medication_code": "normal_saline",
                        "dose": "15-20 mL/kg/h",
                    },
                    priority=90,
                    deadline_minutes=15,
                    is_mandatory=True,
                    required_prior_actions=["establish_iv_access"],
                    source_guideline="ADA 2024",
                    source_recommendation="Fluid Therapy",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="discharge_home",
                    action_type="disposition",
                    is_forbidden=True,
                    source_guideline="ADA 2024",
                ),
            ],

            decision_entries=[
                # 저칼륨혈증 시 인슐린 금지 (CRITICAL TRAP)
                DecisionTableEntry(
                    entry_id="hypokalemia_trap",
                    description="K+ < 3.3 시 인슐린 금지, 칼륨 보충 필수",
                    conditions=[
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.LESS_THAN,
                            value=3.3,
                            description="K+ < 3.3 mEq/L",
                            source_guideline="ADA 2024",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_potassium_iv",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "potassium_chloride",
                                "dose": "20-30 mEq/h",
                            },
                            priority=95,
                            deadline_minutes=30,
                            is_mandatory=True,
                            required_prior_actions=["order_lab_bmp", "establish_iv_access"],
                            source_guideline="ADA 2024",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="hold_insulin_until_k_above_3.3",
                            action_type="clinical_decision",
                            parameters={"reason": "hypokalemia"},
                            priority=94,
                            is_mandatory=True,
                            source_guideline="ADA 2024",
                            evidence_level="1A",
                        ),
                    ],
                    priority=95,
                    source_guideline="ADA 2024",
                ),

                # K+ >= 3.3 시 인슐린 시작
                DecisionTableEntry(
                    entry_id="start_insulin_adequate_k",
                    description="K+ >= 3.3 확인 후 인슐린 시작",
                    conditions=[
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.GREATER_EQUAL,
                            value=3.3,
                            description="K+ >= 3.3 mEq/L",
                            source_guideline="ADA 2024",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="start_insulin_infusion",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "regular_insulin",
                                "dose": "0.1 U/kg/h",
                                "route": "iv_infusion",
                            },
                            priority=85,
                            deadline_minutes=60,
                            is_mandatory=True,
                            required_prior_actions=["order_lab_bmp", "start_iv_fluid_ns"],
                            source_guideline="ADA 2024",
                            source_recommendation="Insulin Therapy",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="monitor_glucose_hourly",
                            action_type="order_lab",
                            parameters={"test_code": "glucose", "frequency": "hourly"},
                            priority=80,
                            deadline_minutes=60,
                            is_mandatory=True,
                            source_guideline="ADA 2024",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="monitor_potassium_q2h",
                            action_type="order_lab",
                            parameters={"test_code": "potassium", "frequency": "q2h"},
                            priority=79,
                            deadline_minutes=120,
                            is_mandatory=True,
                            source_guideline="ADA 2024",
                            evidence_level="1A",
                        ),
                    ],
                    priority=85,
                    source_guideline="ADA 2024",
                ),

                # 3.3 <= K+ < 5.3 시 칼륨 보충 병행
                DecisionTableEntry(
                    entry_id="potassium_maintenance",
                    description="정상-경계 칼륨 시 유지 보충",
                    conditions=[
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.GREATER_EQUAL,
                            value=3.3,
                            description="K+ >= 3.3 mEq/L",
                        ),
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.LESS_THAN,
                            value=5.3,
                            description="K+ < 5.3 mEq/L",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="add_potassium_to_iv",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "potassium_chloride",
                                "dose": "20-40 mEq/L IV fluid",
                            },
                            priority=70,
                            is_mandatory=False,
                            source_guideline="ADA 2024",
                            evidence_level="1B",
                        ),
                    ],
                    priority=70,
                    source_guideline="ADA 2024",
                ),
            ],

            allergy_contraindications={},

            comorbidity_contraindications={
                "ckd_stage_4": ["aggressive_fluid_bolus"],
                "ckd_stage_5": ["aggressive_fluid_bolus"],
                "heart_failure": ["aggressive_fluid_bolus"],
            },
        )

        # ========================================
        # Mild DKA Ruleset (pH 7.25-7.30)
        # ========================================
        mild_dka_ruleset = ClinicalRuleSet(
            ruleset_id="ada_mild_dka",
            name="ADA Mild DKA Management",
            description="경증 DKA (pH 7.25-7.30) 관리",
            source_guidelines=["ADA 2024"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_vital_signs",
                    action_type="physical_exam",
                    priority=100,
                    deadline_minutes=5,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="establish_iv_access",
                    action_type="procedure",
                    priority=98,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_bmp",
                    action_type="order_lab",
                    priority=94,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="start_iv_fluid_ns",
                    action_type="give_medication",
                    priority=90,
                    deadline_minutes=15,
                    is_mandatory=True,
                    required_prior_actions=["establish_iv_access"],
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="discharge_home",
                    action_type="disposition",
                    is_forbidden=True,
                    source_guideline="ADA 2024",
                ),
            ],

            decision_entries=[
                # 저칼륨혈증 Trap
                DecisionTableEntry(
                    entry_id="hypokalemia_trap",
                    description="K+ < 3.3 시 인슐린 금지",
                    conditions=[
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.LESS_THAN,
                            value=3.3,
                            description="K+ < 3.3 mEq/L",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_potassium_iv",
                            action_type="give_medication",
                            priority=95,
                            deadline_minutes=30,
                            is_mandatory=True,
                            source_guideline="ADA 2024",
                            evidence_level="1A",
                        ),
                    ],
                    priority=95,
                    source_guideline="ADA 2024",
                ),

                # 인슐린 시작
                DecisionTableEntry(
                    entry_id="start_insulin",
                    description="K+ >= 3.3 후 인슐린 시작",
                    conditions=[
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.GREATER_EQUAL,
                            value=3.3,
                            description="K+ >= 3.3 mEq/L",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="start_insulin_infusion",
                            action_type="give_medication",
                            priority=85,
                            deadline_minutes=60,
                            is_mandatory=True,
                            required_prior_actions=["order_lab_bmp", "start_iv_fluid_ns"],
                            source_guideline="ADA 2024",
                            evidence_level="1A",
                        ),
                    ],
                    priority=85,
                    source_guideline="ADA 2024",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # DKA with CKD Ruleset (Hyperkalemia Trap)
        # ========================================
        dka_ckd_ruleset = ClinicalRuleSet(
            ruleset_id="ada_dka_ckd",
            name="ADA DKA with CKD Management",
            description="CKD 동반 DKA 관리 (고칼륨혈증 Trap)",
            source_guidelines=["ADA 2024", "KDIGO CKD Guidelines"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_vital_signs",
                    action_type="physical_exam",
                    priority=100,
                    deadline_minutes=5,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="establish_iv_access",
                    action_type="procedure",
                    priority=98,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_bmp",
                    action_type="order_lab",
                    priority=94,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_creatinine",
                    action_type="order_lab",
                    parameters={"test_code": "creatinine"},
                    priority=93,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="KDIGO",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="start_iv_fluid_ns_cautious",
                    action_type="give_medication",
                    parameters={
                        "medication_code": "normal_saline",
                        "dose": "250-500 mL/h (cautious)",
                    },
                    priority=90,
                    deadline_minutes=15,
                    is_mandatory=True,
                    required_prior_actions=["establish_iv_access"],
                    source_guideline="ADA 2024 + KDIGO",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="discharge_home",
                    action_type="disposition",
                    is_forbidden=True,
                    source_guideline="ADA 2024",
                ),
                ActionRecommendation(
                    action_id="aggressive_fluid_bolus",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="KDIGO - CKD caution",
                ),
            ],

            decision_entries=[
                # 고칼륨혈증 Trap (K+ > 5.5)
                DecisionTableEntry(
                    entry_id="hyperkalemia_trap",
                    description="K+ > 5.5 시 칼륨 투여 금지 (CKD TRAP)",
                    conditions=[
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.GREATER_THAN,
                            value=5.5,
                            description="K+ > 5.5 mEq/L",
                            source_guideline="KDIGO",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="treat_hyperkalemia",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "calcium_gluconate",
                                "indication": "cardiac_protection",
                            },
                            priority=95,
                            is_mandatory=True,
                            source_guideline="KDIGO",
                            evidence_level="1B",
                        ),
                        ActionRecommendation(
                            action_id="start_insulin_infusion",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "regular_insulin",
                                "indication": "hyperkalemia_treatment",
                            },
                            priority=90,
                            deadline_minutes=60,
                            is_mandatory=True,
                            source_guideline="ADA 2024",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="order_ecg",
                            action_type="order_imaging",
                            parameters={"study_code": "ecg"},
                            priority=85,
                            is_mandatory=True,
                            source_guideline="KDIGO",
                            evidence_level="1B",
                        ),
                    ],
                    priority=95,
                    source_guideline="KDIGO",
                ),

                # 정상-경계 칼륨 시 신중한 관리
                DecisionTableEntry(
                    entry_id="normal_k_ckd",
                    description="CKD 환자에서 정상 칼륨 시 신중한 관리",
                    conditions=[
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.GREATER_EQUAL,
                            value=3.3,
                        ),
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.LESS_EQUAL,
                            value=5.5,
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="start_insulin_infusion",
                            action_type="give_medication",
                            priority=85,
                            deadline_minutes=60,
                            is_mandatory=True,
                            required_prior_actions=["order_lab_bmp", "start_iv_fluid_ns_cautious"],
                            source_guideline="ADA 2024",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="monitor_potassium_q2h",
                            action_type="order_lab",
                            priority=80,
                            is_mandatory=True,
                            source_guideline="ADA 2024 + KDIGO",
                            evidence_level="1B",
                        ),
                    ],
                    priority=85,
                    source_guideline="ADA 2024 + KDIGO",
                ),
            ],

            allergy_contraindications={},

            comorbidity_contraindications={
                "ckd_stage_4": [
                    "aggressive_fluid_bolus",
                    "give_potassium_replacement",
                    "nsaid",
                ],
                "ckd_stage_5": [
                    "aggressive_fluid_bolus",
                    "give_potassium_replacement",
                    "nsaid",
                ],
            },
        )

        # ========================================
        # Euglycemic DKA Ruleset (SGLT2 inhibitor)
        # ========================================
        euglycemic_dka_ruleset = ClinicalRuleSet(
            ruleset_id="ada_euglycemic_dka",
            name="ADA Euglycemic DKA Management",
            description="정상혈당 DKA (SGLT2 억제제) 관리",
            source_guidelines=["ADA 2024", "FDA Safety Alert"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_vital_signs",
                    action_type="physical_exam",
                    priority=100,
                    deadline_minutes=5,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="establish_iv_access",
                    action_type="procedure",
                    priority=98,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_ketones",
                    action_type="order_lab",
                    parameters={"test_code": "beta_hydroxybutyrate"},
                    priority=96,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    source_recommendation="Euglycemic DKA diagnosis",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_lab_abg",
                    action_type="order_lab",
                    priority=95,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="order_lab_bmp",
                    action_type="order_lab",
                    priority=94,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="stop_sglt2_inhibitor",
                    action_type="clinical_decision",
                    parameters={"reason": "euglycemic_dka"},
                    priority=93,
                    is_mandatory=True,
                    source_guideline="ADA 2024 + FDA",
                    source_recommendation="Discontinue SGLT2 inhibitor",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="start_iv_fluid_ns",
                    action_type="give_medication",
                    priority=90,
                    deadline_minutes=15,
                    is_mandatory=True,
                    required_prior_actions=["establish_iv_access"],
                    source_guideline="ADA 2024",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="start_dextrose_containing_iv",
                    action_type="give_medication",
                    parameters={
                        "medication_code": "d5_half_ns",
                        "indication": "euglycemic_dka",
                    },
                    priority=88,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    source_recommendation="Add dextrose early in euglycemic DKA",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="discharge_home",
                    action_type="disposition",
                    is_forbidden=True,
                    source_guideline="ADA 2024",
                ),
                ActionRecommendation(
                    action_id="continue_sglt2_inhibitor",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="FDA Safety Alert",
                ),
                ActionRecommendation(
                    action_id="dismiss_normal_glucose",
                    action_type="clinical_decision",
                    is_forbidden=True,
                    source_guideline="ADA 2024",
                    source_recommendation="Do not dismiss DKA due to normal glucose",
                ),
            ],

            decision_entries=[
                # 저칼륨혈증 Trap (정상혈당 DKA에서도 동일)
                DecisionTableEntry(
                    entry_id="hypokalemia_trap",
                    description="K+ < 3.3 시 인슐린 금지",
                    conditions=[
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.LESS_THAN,
                            value=3.3,
                            description="K+ < 3.3 mEq/L",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_potassium_iv",
                            action_type="give_medication",
                            priority=95,
                            deadline_minutes=30,
                            is_mandatory=True,
                            source_guideline="ADA 2024",
                            evidence_level="1A",
                        ),
                    ],
                    priority=95,
                    source_guideline="ADA 2024",
                ),

                # 인슐린 시작
                DecisionTableEntry(
                    entry_id="start_insulin",
                    description="K+ >= 3.3 후 인슐린 시작",
                    conditions=[
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.GREATER_EQUAL,
                            value=3.3,
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="start_insulin_infusion",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "regular_insulin",
                                "dose": "0.1 U/kg/h",
                                "note": "Lower rate may be needed in euglycemic DKA",
                            },
                            priority=85,
                            deadline_minutes=60,
                            is_mandatory=True,
                            required_prior_actions=["order_lab_bmp", "start_iv_fluid_ns"],
                            source_guideline="ADA 2024",
                            evidence_level="1A",
                        ),
                    ],
                    priority=85,
                    source_guideline="ADA 2024",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # DKA Resolution & Transition Ruleset
        # ========================================
        dka_resolution_ruleset = ClinicalRuleSet(
            ruleset_id="ada_dka_resolution",
            name="ADA DKA Resolution & Transition",
            description="DKA 해소 후 유지 치료로 전환",
            source_guidelines=["ADA 2024"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_anion_gap_closure",
                    action_type="assessment",
                    parameters={"criteria": "anion_gap <= 12"},
                    priority=100,
                    is_mandatory=True,
                    source_guideline="ADA 2024",
                    source_recommendation="DKA Resolution Criteria",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="stop_iv_insulin_without_overlap",
                    action_type="clinical_decision",
                    is_forbidden=True,
                    source_guideline="ADA 2024",
                    source_recommendation="Must overlap IV and SubQ insulin",
                ),
                ActionRecommendation(
                    action_id="discharge_without_insulin_plan",
                    action_type="disposition",
                    is_forbidden=True,
                    source_guideline="ADA 2024",
                ),
            ],

            decision_entries=[
                # DKA 해소 기준 충족 시 전환
                DecisionTableEntry(
                    entry_id="dka_resolved",
                    description="DKA 해소 기준: AG <= 12, pH > 7.3",
                    conditions=[
                        ClinicalCondition(
                            variable="anion_gap",
                            operator=ConditionOperator.LESS_EQUAL,
                            value=12,
                            description="Anion gap <= 12",
                        ),
                        ClinicalCondition(
                            variable="ph",
                            operator=ConditionOperator.GREATER_THAN,
                            value=7.3,
                            description="pH > 7.3",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="start_subcutaneous_insulin",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "insulin_glargine",
                                "route": "subcutaneous",
                            },
                            priority=90,
                            is_mandatory=True,
                            required_prior_actions=["assess_anion_gap_closure"],
                            source_guideline="ADA 2024",
                            source_recommendation="Transition to SubQ Insulin",
                            evidence_level="1B",
                        ),
                        ActionRecommendation(
                            action_id="overlap_iv_insulin_2h",
                            action_type="clinical_decision",
                            parameters={
                                "duration": "1-2 hours",
                                "reason": "prevent_rebound_hyperglycemia",
                            },
                            priority=89,
                            is_mandatory=True,
                            source_guideline="ADA 2024",
                            source_recommendation="Overlap IV insulin 1-2h",
                            evidence_level="1B",
                        ),
                        ActionRecommendation(
                            action_id="resume_oral_intake",
                            action_type="clinical_decision",
                            priority=85,
                            is_mandatory=True,
                            source_guideline="ADA 2024",
                            evidence_level="1C",
                        ),
                        ActionRecommendation(
                            action_id="diabetes_education",
                            action_type="consultation",
                            parameters={"type": "diabetes_education"},
                            priority=80,
                            is_mandatory=True,
                            source_guideline="ADA 2024",
                            source_recommendation="Patient Education",
                            evidence_level="1B",
                        ),
                    ],
                    priority=90,
                    source_guideline="ADA 2024",
                ),

                # 신규 진단 T1DM 시 추가 조치
                DecisionTableEntry(
                    entry_id="new_onset_t1dm",
                    description="신규 진단 T1DM 시 내분비 협진 필수",
                    conditions=[
                        ClinicalCondition(
                            variable="new_onset_diabetes",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="New onset diabetes",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="endocrinology_consult",
                            action_type="consultation",
                            parameters={"specialty": "endocrinology"},
                            priority=85,
                            is_mandatory=True,
                            source_guideline="ADA 2024",
                            evidence_level="1B",
                        ),
                        ActionRecommendation(
                            action_id="diabetes_education",
                            action_type="consultation",
                            priority=80,
                            is_mandatory=True,
                            source_guideline="ADA 2024",
                            evidence_level="1B",
                        ),
                    ],
                    priority=85,
                    source_guideline="ADA 2024",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # Rulesets 등록
        self.rulesets["severe_dka"] = severe_dka_ruleset
        self.rulesets["moderate_dka"] = moderate_dka_ruleset
        self.rulesets["mild_dka"] = mild_dka_ruleset
        self.rulesets["dka_ckd"] = dka_ckd_ruleset
        self.rulesets["euglycemic_dka"] = euglycemic_dka_ruleset
        self.rulesets["dka_resolution"] = dka_resolution_ruleset

    def _determine_scenario_type(self, context: dict[str, Any]) -> str:
        """시나리오 유형 결정 (단일 - 하위 호환성 유지)

        복합 시나리오의 경우 _get_applicable_scenario_types() 사용 권장
        """
        applicable = self._get_applicable_scenario_types(context)
        return applicable[0] if applicable else "moderate_dka"

    def _get_applicable_scenario_types(self, context: dict[str, Any]) -> list[str]:
        """적용 가능한 모든 시나리오 유형 반환 (복합 시나리오 지원)

        예: 중증 DKA + CKD 환자는 ["severe_dka", "dka_ckd"] 반환

        Returns:
            우선순위 순으로 정렬된 시나리오 유형 리스트
        """
        applicable = []

        diagnosis = (context.get("working_diagnosis") or "").lower()
        comorbidities = [c.lower() for c in context.get("comorbidities", [])]
        ph = context.get("ph", 7.3)
        mental_status = context.get("mental_status", "alert").lower()
        anion_gap = context.get("anion_gap")
        glucose = context.get("glucose")
        bicarbonate = context.get("bicarbonate")

        # 1. DKA 해소 상태 확인 (최우선)
        if self._check_resolution_criteria(context):
            applicable.append("dka_resolution")
            return applicable  # 해소 시 다른 ruleset 불필요

        # 2. Euglycemic DKA (SGLT2)
        if "euglycemic" in diagnosis or "sglt2" in diagnosis:
            applicable.append("euglycemic_dka")

        # 3. 중증도 분류 (항상 포함)
        if ph < 7.0 or mental_status in ["obtunded", "comatose", "unresponsive"]:
            applicable.append("severe_dka")
        elif ph < 7.25:
            applicable.append("moderate_dka")
        else:
            applicable.append("mild_dka")

        # 4. CKD 동반 (추가 ruleset)
        if any("ckd" in c for c in comorbidities):
            applicable.append("dka_ckd")

        return applicable

    def _check_resolution_criteria(self, context: dict[str, Any]) -> bool:
        """ADA DKA 해소 기준 확인

        기준: Glucose < 200 mg/dL PLUS 2 of:
            - Bicarbonate >= 15 mEq/L
            - pH > 7.3
            - Anion gap <= 12 mEq/L
        """
        glucose = context.get("glucose")
        bicarbonate = context.get("bicarbonate")
        ph = context.get("ph")
        anion_gap = context.get("anion_gap")

        if glucose is None or glucose >= 200:
            return False

        criteria_met = 0
        if bicarbonate is not None and bicarbonate >= 15:
            criteria_met += 1
        if ph is not None and ph > 7.3:
            criteria_met += 1
        if anion_gap is not None and anion_gap <= 12:
            criteria_met += 1

        return criteria_met >= 2

    def get_recommended_actions(
        self,
        context: dict[str, Any],
        current_time_minutes: int = 0
    ) -> list[ActionRecommendation]:
        """현재 상태에서 권고되는 행동 목록 반환 (복합 시나리오 지원)

        복합 시나리오의 경우 모든 적용 가능한 ruleset의 권고를 병합합니다.
        """
        recommendations: list[ActionRecommendation] = []
        seen_action_ids = set()

        # 모든 적용 가능한 시나리오 유형 가져오기
        scenario_types = self._get_applicable_scenario_types(context)

        for scenario_type in scenario_types:
            if scenario_type not in self.rulesets:
                continue

            ruleset = self.rulesets[scenario_type]

            # 1. 항상 필수인 행동 추가
            for action in ruleset.always_mandatory:
                if action.action_id not in self._completed_actions:
                    if action.action_id not in seen_action_ids:
                        if not self._is_contraindicated(action, context):
                            recommendations.append(action)
                            seen_action_ids.add(action.action_id)

            # 2. 조건부 규칙 평가
            for entry in ruleset.decision_entries:
                if entry.matches(context):
                    for action in entry.actions:
                        if action.action_id not in self._completed_actions:
                            if action.action_id not in seen_action_ids:
                                if not self._is_contraindicated(action, context):
                                    if self._prerequisites_met(action):
                                        recommendations.append(action)
                                        seen_action_ids.add(action.action_id)

        # 우선순위 및 데드라인 기준 정렬
        recommendations = self._sort_by_priority_and_deadline(
            recommendations, current_time_minutes
        )

        return recommendations

    def get_forbidden_actions(self, context: dict[str, Any]) -> list[str]:
        """현재 상태에서 금기인 행동 목록 반환 (복합 시나리오 지원)"""
        forbidden = set()

        # 모든 적용 가능한 시나리오 유형에서 금기 행동 수집
        scenario_types = self._get_applicable_scenario_types(context)

        for scenario_type in scenario_types:
            if scenario_type not in self.rulesets:
                continue

            ruleset = self.rulesets[scenario_type]

            # 항상 금기인 행동
            for action in ruleset.always_forbidden:
                forbidden.add(action.action_id)

            # 알러지 기반 금기
            allergies = context.get("allergies", [])
            for allergy in allergies:
                allergy_lower = allergy.lower()
                if allergy_lower in ruleset.allergy_contraindications:
                    forbidden.update(ruleset.allergy_contraindications[allergy_lower])

            # 동반질환 기반 금기
            comorbidities = context.get("comorbidities", [])
            for comorbidity in comorbidities:
                comorbidity_lower = comorbidity.lower()
                if comorbidity_lower in ruleset.comorbidity_contraindications:
                    forbidden.update(ruleset.comorbidity_contraindications[comorbidity_lower])

        # 저칼륨혈증 시 인슐린 금기 (글로벌 규칙)
        potassium = context.get("potassium")
        if potassium is not None and potassium < 3.3:
            forbidden.add("start_insulin_infusion")
            forbidden.add("give_insulin_bolus")

        # 고칼륨혈증 시 칼륨 투여 금기 (글로벌 규칙)
        if potassium is not None and potassium > 5.5:
            forbidden.add("give_potassium_iv")
            forbidden.add("give_potassium_replacement")

        return list(forbidden)

    def get_compound_scenario_info(self, context: dict[str, Any]) -> dict[str, Any]:
        """복합 시나리오 정보 반환 (진단/디버깅용)

        Returns:
            {
                "applicable_scenarios": List[str],
                "is_compound": bool,
                "primary_scenario": str,
                "modifiers": List[str],
                "resolution_status": Dict
            }
        """
        scenarios = self._get_applicable_scenario_types(context)
        resolution_check = self._check_resolution_criteria(context)

        return {
            "applicable_scenarios": scenarios,
            "is_compound": len(scenarios) > 1,
            "primary_scenario": scenarios[0] if scenarios else None,
            "modifiers": scenarios[1:] if len(scenarios) > 1 else [],
            "resolution_status": {
                "is_resolved": resolution_check,
                "glucose": context.get("glucose"),
                "bicarbonate": context.get("bicarbonate"),
                "ph": context.get("ph"),
                "anion_gap": context.get("anion_gap"),
            }
        }

    def get_insulin_forbidden_status(self, context: dict[str, Any]) -> dict[str, Any]:
        """인슐린 투여 금기 상태 확인 (Hypokalemia Trap 검증용)

        Returns:
            {
                "is_forbidden": bool,
                "reason": str,
                "potassium_level": float,
                "required_action": str
            }
        """
        potassium = context.get("potassium")

        if potassium is None:
            return {
                "is_forbidden": True,
                "reason": "Potassium level unknown - must check before insulin",
                "potassium_level": None,
                "required_action": "order_lab_bmp",
            }

        if potassium < 3.3:
            return {
                "is_forbidden": True,
                "reason": f"Hypokalemia (K+ = {potassium} mEq/L) - INSULIN CONTRAINDICATED",
                "potassium_level": potassium,
                "required_action": "give_potassium_iv",
            }

        return {
            "is_forbidden": False,
            "reason": f"Potassium adequate (K+ = {potassium} mEq/L)",
            "potassium_level": potassium,
            "required_action": None,
        }

    def get_potassium_forbidden_status(self, context: dict[str, Any]) -> dict[str, Any]:
        """칼륨 투여 금기 상태 확인 (CKD Hyperkalemia Trap 검증용)

        Returns:
            {
                "is_forbidden": bool,
                "reason": str,
                "potassium_level": float,
                "required_action": str
            }
        """
        potassium = context.get("potassium")
        comorbidities = [c.lower() for c in context.get("comorbidities", [])]

        if potassium is None:
            return {
                "is_forbidden": False,
                "reason": "Potassium level unknown",
                "potassium_level": None,
                "required_action": "order_lab_bmp",
            }

        has_ckd = any("ckd" in c for c in comorbidities)

        if potassium > 5.5:
            return {
                "is_forbidden": True,
                "reason": f"Hyperkalemia (K+ = {potassium} mEq/L) - POTASSIUM CONTRAINDICATED",
                "potassium_level": potassium,
                "required_action": "treat_hyperkalemia",
            }

        if has_ckd and potassium > 5.0:
            return {
                "is_forbidden": True,
                "reason": f"CKD with borderline K+ ({potassium} mEq/L) - use caution with potassium",
                "potassium_level": potassium,
                "required_action": "monitor_potassium_closely",
            }

        return {
            "is_forbidden": False,
            "reason": f"Potassium replacement safe (K+ = {potassium} mEq/L)",
            "potassium_level": potassium,
            "required_action": None,
        }
