"""Stroke Decision Table: AHA/ASA 2019 가이드라인 기반 독립적 규칙

출처: 2019 Update to the 2018 Guidelines for the Early Management of Acute Ischemic Stroke
DOI: 10.1161/STR.0000000000000211

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


class StrokeDecisionTable(RuleBasedDecisionTable):
    """AHA/ASA 2019 기반 Stroke 의사결정 테이블

    참조 가이드라인:
    - AHA/ASA 2019 Acute Ischemic Stroke Guideline
    - AHA/ASA ICH Guideline 2015

    이 구현은 채점용 CPG-Engine과 완전히 독립적입니다.
    """

    def _load_rulesets(self):
        """AHA/ASA 2019 규칙 로드"""
        # ========================================
        # Ischemic Stroke - tPA Eligible Ruleset
        # ========================================
        ischemic_tpa_ruleset = ClinicalRuleSet(
            ruleset_id="aha_ischemic_tpa",
            name="AHA Ischemic Stroke - tPA Eligible",
            description="Acute ischemic stroke within tPA window (0-4.5 hours)",
            source_guidelines=["AHA/ASA 2019", "DOI:10.1161/STR.0000000000000211"],

            always_mandatory=[
                # CODE STROKE - Initial Assessment
                ActionRecommendation(
                    action_id="activate_stroke_team",
                    action_type="procedure",
                    parameters={"type": "code_stroke"},
                    priority=100,
                    deadline_minutes=5,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="Section 4",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="obtain_last_known_well_time",
                    action_type="assessment",
                    parameters={"type": "symptom_onset"},
                    priority=99,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="perform_nihss",
                    action_type="assessment",
                    parameters={"type": "nihss"},
                    priority=98,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="check_glucose",
                    action_type="order_lab",
                    parameters={"test_code": "glucose_poc"},
                    priority=97,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="establish_iv_access",
                    action_type="procedure",
                    parameters={"type": "iv_access"},
                    priority=96,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="order_stat_ct_head",
                    action_type="order_imaging",
                    parameters={"imaging_type": "ct_head_noncontrast"},
                    priority=95,
                    deadline_minutes=25,  # Door-to-CT < 25 min
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="Door-to-CT < 25 min target",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_cbc_bmp_coag",
                    action_type="order_lab",
                    parameters={"test_code": "stroke_panel"},
                    priority=90,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="obtain_12_lead_ecg",
                    action_type="order_diagnostic",
                    parameters={"diagnostic_type": "12_lead_ecg"},
                    priority=85,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                # tPA Eligibility Assessment
                ActionRecommendation(
                    action_id="review_inclusion_criteria",
                    action_type="assessment",
                    parameters={"type": "tpa_inclusion"},
                    priority=80,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="Section 5.1",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="review_exclusion_criteria",
                    action_type="assessment",
                    parameters={"type": "tpa_exclusion"},
                    priority=79,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1A",
                ),
                # tPA treatment actions - always mandatory for tPA-eligible scenario
                ActionRecommendation(
                    action_id="obtain_informed_consent",
                    action_type="procedure",
                    parameters={"type": "tpa_consent"},
                    priority=78,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="give_alteplase_0.9mg_kg",
                    action_type="give_medication",
                    parameters={
                        "medication_code": "alteplase",
                        "dose": "0.9mg/kg",
                        "max_dose": "90mg",
                    },
                    priority=77,
                    deadline_minutes=60,
                    is_mandatory=True,
                    required_prior_actions=["order_stat_ct_head", "review_exclusion_criteria"],
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="Door-to-needle < 60 min",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="delay_ct_for_labs",
                    action_type="delay",
                    is_forbidden=True,
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="Do not delay CT for lab results",
                ),
            ],

            decision_entries=[
                # tPA Administration when eligible
                DecisionTableEntry(
                    entry_id="administer_tpa",
                    description="tPA eligible - administer alteplase",
                    conditions=[
                        ClinicalCondition(
                            variable="tpa_eligible",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Meets tPA criteria",
                        ),
                        ClinicalCondition(
                            variable="symptom_onset_minutes",
                            operator=ConditionOperator.LESS_EQUAL,
                            value=270,  # 4.5 hours
                            description="Within tPA window",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="obtain_informed_consent",
                            action_type="procedure",
                            parameters={"type": "tpa_consent"},
                            priority=78,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1C",
                        ),
                        ActionRecommendation(
                            action_id="give_alteplase_0.9mg_kg",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "alteplase",
                                "dose": "0.9mg/kg",
                                "max_dose": "90mg",
                            },
                            priority=77,
                            deadline_minutes=60,  # Door-to-needle < 60 min
                            is_mandatory=True,
                            required_prior_actions=["order_stat_ct_head", "review_exclusion_criteria"],
                            source_guideline="AHA Stroke 2019",
                            source_recommendation="Door-to-needle < 60 min",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="admit_to_icu_or_stroke_unit",
                            action_type="disposition",
                            parameters={"unit": "stroke_unit_or_icu"},
                            priority=75,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1B",
                        ),
                        ActionRecommendation(
                            action_id="monitor_bp_q15min_x2h_then_q30min_x6h",
                            action_type="monitoring",
                            parameters={"type": "bp_monitoring_tpa"},
                            priority=74,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1B",
                        ),
                        ActionRecommendation(
                            action_id="neurological_checks_q15min",
                            action_type="monitoring",
                            parameters={"type": "neuro_checks"},
                            priority=73,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1B",
                        ),
                        ActionRecommendation(
                            action_id="hold_antiplatelet_anticoagulation_24h",
                            action_type="order",
                            parameters={"type": "hold_anticoagulation"},
                            priority=72,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1A",
                        ),
                    ],
                    priority=100,
                    source_guideline="AHA Stroke 2019",
                ),

                # BP management for tPA candidates
                DecisionTableEntry(
                    entry_id="bp_management_tpa",
                    description="BP > 185/110 - lower before tPA",
                    conditions=[
                        ClinicalCondition(
                            variable="sbp_mmhg",
                            operator=ConditionOperator.GREATER_THAN,
                            value=185,
                            description="SBP > 185 mmHg",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="reduce_bp_to_below_185_110_before_tpa",
                            action_type="give_medication",
                            parameters={"target": "BP < 185/110"},
                            priority=85,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            source_recommendation="Section 4.3",
                            evidence_level="1B",
                        ),
                        ActionRecommendation(
                            action_id="use_iv_labetalol_or_nicardipine",
                            action_type="give_medication",
                            parameters={"medication_class": "iv_antihypertensive"},
                            priority=84,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1B",
                        ),
                    ],
                    priority=90,
                    source_guideline="AHA Stroke 2019",
                ),
            ],

            allergy_contraindications={
                "alteplase": ["alteplase", "tpa", "activase"],
            },

            comorbidity_contraindications={
                "recent_intracranial_hemorrhage": ["alteplase"],
                "active_internal_bleeding": ["alteplase"],
                "recent_major_surgery": ["alteplase"],
                "known_bleeding_diathesis": ["alteplase"],
            },
        )

        # ========================================
        # Ischemic Stroke - LVO Thrombectomy Ruleset
        # ========================================
        thrombectomy_ruleset = ClinicalRuleSet(
            ruleset_id="aha_thrombectomy",
            name="AHA LVO Thrombectomy",
            description="Large vessel occlusion within thrombectomy window (0-6 hours)",
            source_guidelines=["AHA/ASA 2019"],

            always_mandatory=[
                # Same initial assessment as tPA
                ActionRecommendation(
                    action_id="activate_stroke_team",
                    action_type="procedure",
                    parameters={"type": "code_stroke"},
                    priority=100,
                    deadline_minutes=5,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="perform_nihss",
                    action_type="assessment",
                    parameters={"type": "nihss"},
                    priority=98,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_stat_ct_head",
                    action_type="order_imaging",
                    parameters={"imaging_type": "ct_head_noncontrast"},
                    priority=95,
                    deadline_minutes=25,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                # LVO-specific
                ActionRecommendation(
                    action_id="confirm_lvo_on_imaging",
                    action_type="assessment",
                    parameters={"type": "cta_lvo"},
                    priority=90,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="Section 6",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="assess_aspects_score",
                    action_type="assessment",
                    parameters={"type": "aspects"},
                    priority=89,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="assess_prestroke_mrs",
                    action_type="assessment",
                    parameters={"type": "prestroke_mrs"},
                    priority=88,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                # Thrombectomy treatment actions - always mandatory for LVO scenario
                ActionRecommendation(
                    action_id="give_alteplase_0.9mg_kg",
                    action_type="give_medication",
                    parameters={
                        "medication_code": "alteplase",
                        "dose": "0.9mg/kg",
                        "max_dose": "90mg",
                    },
                    priority=87,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="Bridging tPA before thrombectomy",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="activate_neurointerventional_team",
                    action_type="procedure",
                    parameters={"type": "neurointerventional_activation"},
                    priority=86,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="perform_thrombectomy_procedure",
                    action_type="procedure",
                    parameters={"procedure_code": "mechanical_thrombectomy"},
                    priority=85,
                    deadline_minutes=90,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="Section 6.2",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="delay_ct_for_labs",
                    action_type="delay",
                    is_forbidden=True,
                    source_guideline="AHA Stroke 2019",
                ),
            ],

            decision_entries=[
                # Thrombectomy when LVO confirmed
                DecisionTableEntry(
                    entry_id="perform_thrombectomy",
                    description="LVO confirmed - perform thrombectomy",
                    conditions=[
                        ClinicalCondition(
                            variable="lvo_confirmed",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="LVO on CTA",
                        ),
                        ClinicalCondition(
                            variable="aspects_score",
                            operator=ConditionOperator.GREATER_EQUAL,
                            value=6,
                            description="ASPECTS >= 6",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="activate_neurointerventional_team",
                            action_type="procedure",
                            parameters={"type": "neurointerventional_activation"},
                            priority=87,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="obtain_informed_consent",
                            action_type="procedure",
                            parameters={"type": "thrombectomy_consent"},
                            priority=86,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1C",
                        ),
                        ActionRecommendation(
                            action_id="perform_thrombectomy_procedure",
                            action_type="procedure",
                            parameters={"procedure_code": "mechanical_thrombectomy"},
                            priority=85,
                            deadline_minutes=60,  # Groin puncture within 60 min
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            source_recommendation="Section 6.2",
                            evidence_level="1A",
                        ),
                    ],
                    priority=100,
                    source_guideline="AHA Stroke 2019",
                ),

                # tPA before thrombectomy if eligible
                DecisionTableEntry(
                    entry_id="bridging_tpa",
                    description="tPA eligible with LVO - bridging therapy",
                    conditions=[
                        ClinicalCondition(
                            variable="tpa_eligible",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Meets tPA criteria",
                        ),
                        ClinicalCondition(
                            variable="symptom_onset_minutes",
                            operator=ConditionOperator.LESS_EQUAL,
                            value=270,
                            description="Within tPA window",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_alteplase_0.9mg_kg",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "alteplase",
                                "dose": "0.9mg/kg",
                            },
                            priority=90,
                            deadline_minutes=60,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1A",
                        ),
                    ],
                    priority=95,
                    source_guideline="AHA Stroke 2019",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # Extended Window Thrombectomy (6-24h)
        # ========================================
        extended_window_ruleset = ClinicalRuleSet(
            ruleset_id="aha_extended_window",
            name="AHA Extended Window Thrombectomy",
            description="Thrombectomy in extended time window (6-24 hours) with perfusion imaging",
            source_guidelines=["AHA/ASA 2019 (DAWN/DEFUSE-3)"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="activate_stroke_team",
                    action_type="procedure",
                    parameters={"type": "code_stroke"},
                    priority=100,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="perform_nihss",
                    action_type="assessment",
                    parameters={"type": "nihss"},
                    priority=98,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_stat_ct_head",
                    action_type="order_imaging",
                    parameters={"imaging_type": "ct_head_noncontrast"},
                    priority=95,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="confirm_lvo_on_imaging",
                    action_type="assessment",
                    parameters={"type": "cta_lvo"},
                    priority=90,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="confirm_favorable_perfusion_imaging",
                    action_type="order_imaging",
                    parameters={"imaging_type": "ct_perfusion"},
                    priority=89,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="DAWN/DEFUSE-3 criteria",
                    evidence_level="1A",
                ),
                # Extended window thrombectomy treatment actions - always mandatory
                ActionRecommendation(
                    action_id="activate_neurointerventional_team",
                    action_type="procedure",
                    parameters={"type": "neurointerventional_activation"},
                    priority=87,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="perform_thrombectomy_procedure",
                    action_type="procedure",
                    parameters={"procedure_code": "mechanical_thrombectomy"},
                    priority=85,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_alteplase",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="Beyond tPA window",
                ),
            ],

            decision_entries=[
                DecisionTableEntry(
                    entry_id="extended_window_thrombectomy",
                    description="Favorable perfusion - perform thrombectomy",
                    conditions=[
                        ClinicalCondition(
                            variable="favorable_perfusion",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Meets DAWN/DEFUSE-3 criteria",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="activate_neurointerventional_team",
                            action_type="procedure",
                            parameters={"type": "neurointerventional_activation"},
                            priority=87,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="perform_thrombectomy_procedure",
                            action_type="procedure",
                            parameters={"procedure_code": "mechanical_thrombectomy"},
                            priority=85,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1A",
                        ),
                    ],
                    priority=100,
                    source_guideline="AHA Stroke 2019",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # Hemorrhagic Stroke (ICH) Ruleset
        # ========================================
        hemorrhagic_ruleset = ClinicalRuleSet(
            ruleset_id="aha_hemorrhagic",
            name="AHA Intracerebral Hemorrhage",
            description="Intracerebral hemorrhage management",
            source_guidelines=["AHA/ASA ICH Guideline 2015"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="activate_stroke_team",
                    action_type="procedure",
                    parameters={"type": "code_stroke"},
                    priority=100,
                    is_mandatory=True,
                    source_guideline="AHA ICH 2015",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_stat_ct_head",
                    action_type="order_imaging",
                    parameters={"imaging_type": "ct_head_noncontrast"},
                    priority=95,
                    deadline_minutes=25,
                    is_mandatory=True,
                    source_guideline="AHA ICH 2015",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="icu_admission",
                    action_type="disposition",
                    parameters={"unit": "icu"},
                    priority=90,
                    is_mandatory=True,
                    source_guideline="AHA ICH 2015",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="bp_reduction_target_140",
                    action_type="give_medication",
                    parameters={"target": "SBP < 140"},
                    priority=88,
                    is_mandatory=True,
                    source_guideline="AHA ICH 2015",
                    source_recommendation="Rapid BP lowering",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="neurosurgery_consult",
                    action_type="consultation",
                    parameters={"consult_type": "neurosurgery"},
                    priority=85,
                    is_mandatory=True,
                    source_guideline="AHA ICH 2015",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="repeat_ct_6h_or_if_deterioration",
                    action_type="order_imaging",
                    parameters={"imaging_type": "ct_head_followup"},
                    priority=80,
                    is_mandatory=True,
                    source_guideline="AHA ICH 2015",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_tpa",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA ICH 2015",
                    source_recommendation="Absolute contraindication",
                ),
                ActionRecommendation(
                    action_id="give_antiplatelet",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA ICH 2015",
                ),
                ActionRecommendation(
                    action_id="give_anticoagulation",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA ICH 2015",
                ),
            ],

            decision_entries=[
                # Reversal for anticoagulated patients
                DecisionTableEntry(
                    entry_id="reverse_anticoagulation",
                    description="On anticoagulation - reverse urgently",
                    conditions=[
                        ClinicalCondition(
                            variable="on_anticoagulation",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Patient on anticoagulation",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="reverse_anticoagulation_if_applicable",
                            action_type="give_medication",
                            parameters={"type": "reversal_agent"},
                            priority=95,
                            deadline_minutes=60,
                            is_mandatory=True,
                            source_guideline="AHA ICH 2015",
                            evidence_level="1A",
                        ),
                    ],
                    priority=100,
                    source_guideline="AHA ICH 2015",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # Post-tPA Hemorrhagic Transformation Ruleset
        # ========================================
        hemorrhagic_transformation_ruleset = ClinicalRuleSet(
            ruleset_id="aha_hemorrhagic_transformation",
            name="AHA Post-tPA Hemorrhagic Transformation",
            description="Management of neurological deterioration post-tPA",
            source_guidelines=["AHA/ASA 2019"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="stop_tpa_infusion",
                    action_type="order",
                    parameters={"type": "stop_tpa"},
                    priority=100,
                    deadline_minutes=5,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="Section 5.5",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="stat_ct_head",
                    action_type="order_imaging",
                    parameters={"imaging_type": "ct_head_stat"},
                    priority=99,
                    deadline_minutes=15,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="stat_coagulation_panel",
                    action_type="order_lab",
                    parameters={"test_code": "coagulation_stat"},
                    priority=98,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="type_and_screen",
                    action_type="order_lab",
                    parameters={"test_code": "type_and_screen"},
                    priority=97,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1C",
                ),
            ],

            always_forbidden=[],

            decision_entries=[
                DecisionTableEntry(
                    entry_id="hemorrhage_confirmed_management",
                    description="Hemorrhage confirmed - reversal therapy",
                    conditions=[
                        ClinicalCondition(
                            variable="hemorrhage_confirmed",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Hemorrhage on CT",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="give_cryoprecipitate",
                            action_type="give_medication",
                            parameters={"medication_code": "cryoprecipitate"},
                            priority=95,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1C",
                        ),
                        ActionRecommendation(
                            action_id="give_tranexamic_acid",
                            action_type="give_medication",
                            parameters={"medication_code": "tranexamic_acid"},
                            priority=94,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1C",
                        ),
                        ActionRecommendation(
                            action_id="reverse_coagulopathy",
                            action_type="procedure",
                            parameters={"type": "coagulopathy_reversal"},
                            priority=93,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1C",
                        ),
                        ActionRecommendation(
                            action_id="neurosurgery_consult",
                            action_type="consultation",
                            parameters={"consult_type": "neurosurgery"},
                            priority=92,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1B",
                        ),
                        ActionRecommendation(
                            action_id="icu_management",
                            action_type="disposition",
                            parameters={"unit": "icu"},
                            priority=91,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1B",
                        ),
                    ],
                    priority=100,
                    source_guideline="AHA Stroke 2019",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # Non-Reperfusion Management Ruleset
        # ========================================
        non_reperfusion_ruleset = ClinicalRuleSet(
            ruleset_id="aha_non_reperfusion",
            name="AHA Non-Reperfusion Management",
            description="Stroke management without reperfusion therapy",
            source_guidelines=["AHA/ASA 2019"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="admit_to_stroke_unit",
                    action_type="disposition",
                    parameters={"unit": "stroke_unit"},
                    priority=100,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="Section 7",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="aspirin_within_24_48h",
                    action_type="give_medication",
                    parameters={
                        "medication_code": "aspirin",
                        "dose": "325mg",
                    },
                    priority=95,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="dvt_prophylaxis",
                    action_type="order",
                    parameters={"type": "dvt_prophylaxis"},
                    priority=90,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="swallow_screen",
                    action_type="assessment",
                    parameters={"type": "dysphagia_screen"},
                    priority=85,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="early_mobilization",
                    action_type="order",
                    parameters={"type": "early_mobilization"},
                    priority=80,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_anticoagulation_for_stroke_prevention_in_first_24h",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA Stroke 2019",
                ),
            ],

            decision_entries=[],

            allergy_contraindications={
                "aspirin": ["aspirin"],
            },

            comorbidity_contraindications={
                "active_gi_bleeding": ["aspirin"],
            },
        )

        # ========================================
        # Secondary Prevention Ruleset
        # ========================================
        secondary_prevention_ruleset = ClinicalRuleSet(
            ruleset_id="aha_secondary_prevention",
            name="AHA Stroke Secondary Prevention",
            description="Secondary stroke prevention",
            source_guidelines=["AHA/ASA 2019"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="antiplatelet_therapy",
                    action_type="give_medication",
                    parameters={"medication_class": "antiplatelet"},
                    priority=100,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    source_recommendation="Section 9",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="statin_therapy",
                    action_type="give_medication",
                    parameters={"medication_class": "statin"},
                    priority=95,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="bp_management_long_term",
                    action_type="give_medication",
                    parameters={"medication_class": "antihypertensive"},
                    priority=90,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="carotid_evaluation",
                    action_type="order_imaging",
                    parameters={"imaging_type": "carotid_duplex"},
                    priority=85,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="cardiac_monitoring_for_afib",
                    action_type="monitoring",
                    parameters={"type": "cardiac_monitoring"},
                    priority=80,
                    is_mandatory=True,
                    source_guideline="AHA Stroke 2019",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[],

            decision_entries=[
                # Afib detected - anticoagulation
                DecisionTableEntry(
                    entry_id="afib_anticoagulation",
                    description="Afib detected - start anticoagulation",
                    conditions=[
                        ClinicalCondition(
                            variable="afib_detected",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Atrial fibrillation detected",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="calculate_chadsvasc",
                            action_type="assessment",
                            parameters={"type": "chadsvasc"},
                            priority=75,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="calculate_hasbled",
                            action_type="assessment",
                            parameters={"type": "hasbled"},
                            priority=74,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="start_doac_preferred",
                            action_type="give_medication",
                            parameters={"medication_class": "doac"},
                            priority=73,
                            is_mandatory=True,
                            source_guideline="AHA Stroke 2019",
                            source_recommendation="DOAC preferred over warfarin",
                            evidence_level="1A",
                        ),
                    ],
                    priority=90,
                    source_guideline="AHA Stroke 2019",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # Register all rulesets
        self.rulesets["ischemic_tpa"] = ischemic_tpa_ruleset
        self.rulesets["thrombectomy"] = thrombectomy_ruleset
        self.rulesets["extended_window"] = extended_window_ruleset
        self.rulesets["hemorrhagic"] = hemorrhagic_ruleset
        self.rulesets["hemorrhagic_transformation"] = hemorrhagic_transformation_ruleset
        self.rulesets["non_reperfusion"] = non_reperfusion_ruleset
        self.rulesets["secondary_prevention"] = secondary_prevention_ruleset

    def _determine_scenario_type(self, context: dict[str, Any]) -> str:
        """시나리오 유형 결정"""
        diagnosis = (context.get("working_diagnosis") or "").lower()
        symptom_onset_minutes = context.get("symptom_onset_minutes")
        lvo_confirmed = context.get("lvo_confirmed", False)
        ct_head = (context.get("ct_head") or "").lower()
        tpa_administered = context.get("tpa_administered", False)
        post_tpa_deterioration = context.get("post_tpa_deterioration", False)
        favorable_perfusion = context.get("favorable_perfusion", False)

        # Check for hemorrhagic transformation first
        if tpa_administered and post_tpa_deterioration:
            return "hemorrhagic_transformation"

        # Check for hemorrhagic stroke
        hemorrhagic_indicators = [
            "hemorrhage", "hemorrhagic", "ich", "intracerebral_hemorrhage",
            "subarachnoid", "sah"
        ]
        if any(ind in diagnosis for ind in hemorrhagic_indicators):
            return "hemorrhagic"
        if "hemorrhage" in ct_head or "blood" in ct_head:
            return "hemorrhagic"

        # Check for secondary prevention phase
        if "secondary_prevention" in diagnosis or "follow_up" in diagnosis:
            return "secondary_prevention"

        # Ischemic stroke pathway
        if symptom_onset_minutes is not None:
            # Extended window (6-24h) with favorable perfusion
            if symptom_onset_minutes > 360 and lvo_confirmed and favorable_perfusion:
                return "extended_window"

            # Standard thrombectomy window (0-6h) with LVO
            if symptom_onset_minutes <= 360 and lvo_confirmed:
                return "thrombectomy"

            # tPA window (0-4.5h)
            if symptom_onset_minutes <= 270:
                return "ischemic_tpa"

        # Check for LVO indicators
        lvo_indicators = ["lvo", "large_vessel_occlusion", "m1", "ica", "basilar"]
        if any(ind in diagnosis for ind in lvo_indicators):
            return "thrombectomy"

        # Check wake-up stroke
        if "wake_up" in diagnosis or "unknown_onset" in diagnosis:
            if lvo_confirmed and favorable_perfusion:
                return "extended_window"

        # Default to non-reperfusion if beyond windows
        if symptom_onset_minutes is not None and symptom_onset_minutes > 270:
            if not lvo_confirmed:
                return "non_reperfusion"

        # Default to ischemic tPA pathway for acute ischemic stroke
        if "ischemic" in diagnosis or "stroke" in diagnosis:
            return "ischemic_tpa"

        # Default
        return "ischemic_tpa"

    def is_tpa_eligible(self, context: dict[str, Any]) -> bool:
        """TPA 적격 여부 확인"""
        symptom_onset_minutes = context.get("symptom_onset_minutes")
        if symptom_onset_minutes is None or symptom_onset_minutes > 270:
            return False

        # Check for contraindications
        contraindications = context.get("contraindications", [])
        absolute_contraindications = [
            "recent_intracranial_hemorrhage",
            "active_internal_bleeding",
            "recent_intracranial_surgery",
            "known_bleeding_diathesis",
        ]
        for contra in absolute_contraindications:
            if contra in contraindications:
                return False

        return True

    def is_thrombectomy_eligible(self, context: dict[str, Any]) -> bool:
        """Thrombectomy 적격 여부 확인"""
        lvo_confirmed = context.get("lvo_confirmed", False)
        aspects_score = context.get("aspects_score", 0)
        symptom_onset_minutes = context.get("symptom_onset_minutes")

        if not lvo_confirmed:
            return False

        if aspects_score < 6:
            return False

        if symptom_onset_minutes is not None and symptom_onset_minutes > 1440:
            return False

        return True

    def get_forbidden_actions(self, context: dict[str, Any]) -> list[str]:
        """현재 상태에서 금기인 행동 목록 반환"""
        forbidden = super().get_forbidden_actions(context)
        scenario_type = self._determine_scenario_type(context)
        tpa_administered = context.get("tpa_administered", False)
        ct_head = (context.get("ct_head") or "").lower()

        # Post-tPA forbidden actions (within 24h)
        if tpa_administered:
            forbidden.extend([
                "give_antiplatelet_within_24h",
                "give_anticoagulation_within_24h",
                "give_heparin_within_24h",
                "place_foley_within_30min",
                "place_ng_tube_within_30min",
                "place_arterial_line_within_30min",
                "aspirin",
                "heparin",
                "warfarin",
                "anticoagulation",
            ])

        # Hemorrhagic stroke - absolute tPA contraindication
        if scenario_type == "hemorrhagic" or "hemorrhage" in ct_head:
            forbidden.extend([
                "give_tpa",
                "give_alteplase",
                "alteplase",
                "tpa",
                "give_antiplatelet",
                "give_anticoagulation",
                "aspirin",
                "heparin",
            ])

        # Extended window - no tPA
        if scenario_type == "extended_window":
            forbidden.extend([
                "give_alteplase",
                "give_tpa",
                "alteplase",
            ])

        return list(set(forbidden))

    def get_time_critical_actions(self, context: dict[str, Any]) -> list[dict[str, Any]]:
        """시간 제한이 있는 중요 행동 목록 반환"""
        scenario_type = self._determine_scenario_type(context)
        time_critical = []

        if scenario_type in ["ischemic_tpa", "thrombectomy"]:
            time_critical.append({
                "action_id": "order_stat_ct_head",
                "deadline_minutes": 25,
                "description": "Door-to-CT < 25 min",
            })

        if scenario_type == "ischemic_tpa":
            time_critical.append({
                "action_id": "give_alteplase_0.9mg_kg",
                "deadline_minutes": 60,
                "description": "Door-to-needle < 60 min",
            })

        if scenario_type in ["thrombectomy", "extended_window"]:
            time_critical.append({
                "action_id": "perform_thrombectomy_procedure",
                "deadline_minutes": 60,
                "description": "Groin puncture < 60 min from arrival",
            })

        return time_critical
