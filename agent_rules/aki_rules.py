"""AKI Decision Table: KDIGO 2012 가이드라인 기반 독립적 규칙

출처: KDIGO Clinical Practice Guideline for Acute Kidney Injury 2012
DOI: 10.1038/kisup.2012.1

이 규칙은 CPG-Engine의 그래프 구조와 완전히 독립적으로 구현되었습니다.
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


class AKIDecisionTable(RuleBasedDecisionTable):
    """KDIGO 2012 기반 AKI 의사결정 테이블

    참조 가이드라인:
    - KDIGO 2012 AKI Guideline

    이 구현은 채점용 CPG-Engine과 완전히 독립적입니다.
    """

    def _load_rulesets(self):
        """KDIGO 2012 규칙 로드"""
        # ========================================
        # AKI Stage 1 Ruleset
        # ========================================
        aki_stage1_ruleset = ClinicalRuleSet(
            ruleset_id="kdigo_aki_stage1",
            name="KDIGO AKI Stage 1 Management",
            description="AKI Stage 1 관리 (Cr 1.5-1.9x baseline)",
            source_guidelines=["KDIGO 2012", "DOI:10.1038/kisup.2012.1"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="order_creatinine",
                    action_type="order_lab",
                    parameters={"test_code": "creatinine"},
                    priority=100,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    source_recommendation="Section 2.1",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="monitor_urine_output",
                    action_type="monitoring",
                    parameters={"type": "urine_output"},
                    priority=95,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="discontinue_nephrotoxins",
                    action_type="medication_review",
                    parameters={"action": "discontinue_nephrotoxic"},
                    priority=90,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    source_recommendation="Section 3.1",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="optimize_volume_status",
                    action_type="assessment",
                    parameters={"type": "volume_status"},
                    priority=85,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_nsaid",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="KDIGO 2012",
                    source_recommendation="Avoid nephrotoxins",
                ),
                ActionRecommendation(
                    action_id="give_aminoglycoside_without_monitoring",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="KDIGO 2012",
                ),
            ],

            decision_entries=[],

            allergy_contraindications={},

            comorbidity_contraindications={
                "diabetes": ["metformin_if_contrast"],
            },
        )

        # ========================================
        # AKI Stage 2 Ruleset
        # ========================================
        aki_stage2_ruleset = ClinicalRuleSet(
            ruleset_id="kdigo_aki_stage2",
            name="KDIGO AKI Stage 2 Management",
            description="AKI Stage 2 관리 (Cr 2.0-2.9x baseline)",
            source_guidelines=["KDIGO 2012"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="order_creatinine",
                    action_type="order_lab",
                    parameters={"test_code": "creatinine"},
                    priority=100,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="monitor_urine_output",
                    action_type="monitoring",
                    parameters={"type": "urine_output"},
                    priority=95,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="consult_nephrology",
                    action_type="consult",
                    parameters={"specialty": "nephrology"},
                    priority=90,
                    deadline_minutes=240,  # 4시간 내
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    source_recommendation="Section 3.2",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="monitor_potassium",
                    action_type="order_lab",
                    parameters={"test_code": "potassium"},
                    priority=85,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="monitor_acid_base",
                    action_type="order_lab",
                    parameters={"test_code": "blood_gas"},
                    priority=80,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_nsaid",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="KDIGO 2012",
                ),
                ActionRecommendation(
                    action_id="give_contrast_without_preparation",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="KDIGO 2012",
                    source_recommendation="Section 4",
                ),
            ],

            decision_entries=[
                # 고칼륨혈증 시 칼륨 보충 금기
                DecisionTableEntry(
                    entry_id="hyperkalemia_management",
                    description="고칼륨혈증 시 칼륨 보충 금기",
                    conditions=[
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.GREATER_THAN,
                            value=5.5,
                            description="K+ > 5.5 mEq/L",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="contraindicate_potassium",
                            action_type="contraindication",
                            parameters={
                                "contraindicated_medication": "potassium_supplement",
                            },
                            is_forbidden=True,
                            source_guideline="KDIGO 2012",
                        ),
                    ],
                    priority=95,
                    source_guideline="KDIGO 2012",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # AKI Stage 3 Ruleset
        # ========================================
        aki_stage3_ruleset = ClinicalRuleSet(
            ruleset_id="kdigo_aki_stage3",
            name="KDIGO AKI Stage 3 Management",
            description="AKI Stage 3 관리 (Cr >= 3x baseline or >= 4.0 or RRT)",
            source_guidelines=["KDIGO 2012"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="urgent_nephrology_consult",
                    action_type="consult",
                    parameters={"specialty": "nephrology", "urgency": "urgent"},
                    priority=100,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    source_recommendation="Section 3.3",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="monitor_creatinine_q6h",
                    action_type="order_lab",
                    parameters={"test_code": "creatinine", "frequency": "q6h"},
                    priority=95,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="monitor_potassium_q6h",
                    action_type="order_lab",
                    parameters={"test_code": "potassium", "frequency": "q6h"},
                    priority=90,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="assess_rrt_need",
                    action_type="assessment",
                    parameters={"type": "rrt_indication"},
                    priority=85,
                    deadline_minutes=120,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    source_recommendation="Section 5.1",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="ecg_for_hyperkalemia",
                    action_type="order_diagnostic",
                    parameters={"diagnostic_type": "ecg"},
                    priority=80,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_nsaid",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="KDIGO 2012",
                ),
                ActionRecommendation(
                    action_id="give_contrast",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="KDIGO 2012",
                ),
                ActionRecommendation(
                    action_id="give_potassium",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="KDIGO 2012",
                ),
            ],

            decision_entries=[
                # 응급 RRT 적응증
                DecisionTableEntry(
                    entry_id="emergency_rrt_indication",
                    description="응급 RRT 적응증",
                    conditions=[
                        ClinicalCondition(
                            variable="potassium",
                            operator=ConditionOperator.GREATER_THAN,
                            value=6.5,
                            description="Critical hyperkalemia (K+ > 6.5)",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="initiate_emergency_rrt",
                            action_type="procedure",
                            parameters={"procedure_code": "hemodialysis"},
                            priority=100,
                            deadline_minutes=60,
                            is_mandatory=True,
                            source_guideline="KDIGO 2012",
                            source_recommendation="Section 5.2",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="treat_hyperkalemia_temporizing",
                            action_type="give_medication",
                            parameters={
                                "medications": ["calcium_gluconate", "insulin_glucose"],
                            },
                            priority=100,
                            deadline_minutes=30,
                            is_mandatory=True,
                            source_guideline="KDIGO 2012",
                            evidence_level="1A",
                        ),
                    ],
                    priority=100,
                    source_guideline="KDIGO 2012",
                ),

                # 폐부종 시 응급 RRT
                DecisionTableEntry(
                    entry_id="pulmonary_edema_rrt",
                    description="폐부종 시 응급 RRT",
                    conditions=[
                        ClinicalCondition(
                            variable="pulmonary_edema",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Pulmonary edema unresponsive to diuretics",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="initiate_emergency_rrt",
                            action_type="procedure",
                            parameters={"procedure_code": "hemodialysis"},
                            priority=100,
                            deadline_minutes=60,
                            is_mandatory=True,
                            source_guideline="KDIGO 2012",
                            evidence_level="1A",
                        ),
                    ],
                    priority=100,
                    source_guideline="KDIGO 2012",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # Contrast-Induced AKI Prevention Ruleset
        # ========================================
        ci_aki_ruleset = ClinicalRuleSet(
            ruleset_id="kdigo_ci_aki",
            name="KDIGO Contrast-Induced AKI Prevention",
            description="조영제 유발 AKI 예방",
            source_guidelines=["KDIGO 2012 Section 4"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_ci_aki_risk",
                    action_type="assessment",
                    parameters={"type": "ci_aki_risk"},
                    priority=100,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    source_recommendation="Section 4.1",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_baseline_creatinine",
                    action_type="order_lab",
                    parameters={"test_code": "creatinine"},
                    priority=95,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="KDIGO 2012",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_high_osmolar_contrast",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="KDIGO 2012",
                    source_recommendation="Section 4.4",
                ),
            ],

            decision_entries=[
                # 고위험 (eGFR < 30)
                DecisionTableEntry(
                    entry_id="high_risk_ci_aki",
                    description="고위험 조영제 투여 (eGFR < 30)",
                    conditions=[
                        ClinicalCondition(
                            variable="egfr",
                            operator=ConditionOperator.LESS_THAN,
                            value=30,
                            description="eGFR < 30 mL/min/1.73m2",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="consider_alternative_imaging",
                            action_type="decision",
                            parameters={"type": "alternative_imaging"},
                            priority=100,
                            is_mandatory=True,
                            source_guideline="KDIGO 2012",
                            source_recommendation="Section 4.4",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="iv_hydration_if_proceeding",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "normal_saline",
                                "timing": "6h before if possible",
                            },
                            priority=95,
                            is_mandatory=True,
                            source_guideline="KDIGO 2012",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="use_iso_osmolar_contrast",
                            action_type="medication_preference",
                            parameters={"preferred": "iso_osmolar_contrast"},
                            priority=90,
                            is_mandatory=True,
                            source_guideline="KDIGO 2012",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="minimize_contrast_volume",
                            action_type="protocol",
                            parameters={"goal": "minimize_volume"},
                            priority=85,
                            is_mandatory=True,
                            source_guideline="KDIGO 2012",
                            evidence_level="1A",
                        ),
                    ],
                    priority=100,
                    source_guideline="KDIGO 2012 Section 4.4",
                ),
            ],

            allergy_contraindications={
                "contrast": ["iodinated_contrast"],
            },

            comorbidity_contraindications={
                "diabetes": ["hold_metformin_with_contrast"],
            },
        )

        self.rulesets["aki_stage_1"] = aki_stage1_ruleset
        self.rulesets["aki_stage_2"] = aki_stage2_ruleset
        self.rulesets["aki_stage_3"] = aki_stage3_ruleset
        self.rulesets["ci_aki_prevention"] = ci_aki_ruleset

    def _determine_scenario_type(self, context: dict[str, Any]) -> str:
        """시나리오 유형 결정 (AKI 단계)"""
        diagnosis = (context.get("working_diagnosis") or "").lower()
        chief_complaint = (context.get("chief_complaint") or "").lower()
        creatinine = context.get("creatinine", 0)
        creatinine_baseline = context.get("creatinine_baseline", 1.0)
        contrast_planned = context.get("contrast_exposure_planned", False)

        # 조영제 관련 시나리오 감지 (명시적 플래그 또는 진단/주소에서 추론)
        contrast_indicators = [
            "contrast", "ct ", "cta", "ct_", "angiogram", "angiography",
            "pulmonary_embolism", "pe ", "pe_workup", "coronary",
            "cardiac_catheterization", "pci", "contrast_exposure"
        ]

        is_contrast_scenario = contrast_planned or any(
            indicator in diagnosis or indicator in chief_complaint
            for indicator in contrast_indicators
        )

        # 조영제 계획 시 CI-AKI 예방
        if is_contrast_scenario:
            return "ci_aki_prevention"

        # AKI 단계 결정
        if creatinine_baseline > 0:
            ratio = creatinine / creatinine_baseline

            if ratio >= 3.0 or creatinine >= 4.0:
                return "aki_stage_3"
            elif ratio >= 2.0:
                return "aki_stage_2"
            elif ratio >= 1.5:
                return "aki_stage_1"

        # 진단명으로 판단
        if "aki_stage_3" in diagnosis or "severe" in diagnosis:
            return "aki_stage_3"
        elif "aki_stage_2" in diagnosis:
            return "aki_stage_2"
        elif "aki" in diagnosis:
            return "aki_stage_1"

        return "aki_stage_1"

    def get_aki_stage(self, creatinine: float, baseline: float) -> int:
        """AKI 단계 계산"""
        if baseline <= 0:
            return 0

        ratio = creatinine / baseline

        if ratio >= 3.0 or creatinine >= 4.0:
            return 3
        elif ratio >= 2.0:
            return 2
        elif ratio >= 1.5:
            return 1

        return 0
