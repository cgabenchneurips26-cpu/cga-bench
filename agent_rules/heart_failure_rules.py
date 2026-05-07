"""Heart Failure Decision Table: AHA/ACC/HFSA 2022 가이드라인 기반 독립적 규칙

출처: 2022 AHA/ACC/HFSA Guideline for the Management of Heart Failure
DOI: 10.1016/j.jacc.2021.12.012

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


class HeartFailureDecisionTable(RuleBasedDecisionTable):
    """AHA/ACC/HFSA 2022 기반 Heart Failure 의사결정 테이블

    참조 가이드라인:
    - AHA/ACC/HFSA 2022 Heart Failure Guideline
    - GDMT for HFrEF
    - Management of Acute Decompensated HF (ADHF)

    이 구현은 채점용 CPG-Engine과 완전히 독립적입니다.
    """

    def _load_rulesets(self):
        """AHA/ACC/HFSA 2022 규칙 로드"""
        # ========================================
        # HFrEF (EF <= 40%) Ruleset
        # ========================================
        hfref_ruleset = ClinicalRuleSet(
            ruleset_id="aha_hfref",
            name="AHA HFrEF GDMT",
            description="Heart Failure with Reduced Ejection Fraction - GDMT",
            source_guidelines=["AHA/ACC/HFSA 2022", "DOI:10.1016/j.jacc.2021.12.012"],

            always_mandatory=[
                # Initial Assessment - History & Physical
                ActionRecommendation(
                    action_id="obtain_history",
                    action_type="assessment",
                    parameters={"type": "history"},
                    priority=105,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Section 4.1",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="physical_examination",
                    action_type="assessment",
                    parameters={"type": "physical_exam"},
                    priority=104,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Section 4.1",
                    evidence_level="1C",
                ),
                # Initial Assessment - Labs
                ActionRecommendation(
                    action_id="order_bnp_or_ntprobnp",
                    action_type="order_lab",
                    parameters={"test_code": "bnp_or_ntprobnp"},
                    priority=100,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Section 4.1",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_basic_metabolic_panel",
                    action_type="order_lab",
                    parameters={"test_code": "bmp"},
                    priority=103,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="order_cbc",
                    action_type="order_lab",
                    parameters={"test_code": "cbc"},
                    priority=102,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="order_tsh",
                    action_type="order_lab",
                    parameters={"test_code": "tsh"},
                    priority=101,
                    deadline_minutes=1440,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="order_ecg",
                    action_type="order_diagnostic",
                    parameters={"diagnostic_type": "12_lead_ecg"},
                    priority=99,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="order_chest_xray",
                    action_type="order_diagnostic",
                    parameters={"diagnostic_type": "chest_xray"},
                    priority=98,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="order_echocardiogram",
                    action_type="order_diagnostic",
                    parameters={"diagnostic_type": "echocardiogram"},
                    priority=97,
                    deadline_minutes=1440,  # 24 hours
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Section 4.2",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="assess_lvef",
                    action_type="assessment",
                    parameters={"type": "lvef"},
                    priority=96,
                    is_mandatory=True,
                    required_prior_actions=["order_echocardiogram"],
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="initiate_ace_or_arb_or_arni",
                    action_type="give_medication",
                    parameters={"medication_class": "raas_inhibitor"},
                    priority=95,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="GDMT Class I",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="initiate_beta_blocker",
                    action_type="give_medication",
                    parameters={"medication_class": "beta_blocker"},
                    priority=94,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="GDMT Class I",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="initiate_mra",
                    action_type="give_medication",
                    parameters={"medication_class": "mineralocorticoid_receptor_antagonist"},
                    priority=93,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="GDMT Class I",
                    evidence_level="1A",
                ),
                ActionRecommendation(
                    action_id="initiate_sglt2i",
                    action_type="give_medication",
                    parameters={"medication_class": "sglt2_inhibitor"},
                    priority=92,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="GDMT Class I",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_nsaid",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Class III - Harm",
                ),
                ActionRecommendation(
                    action_id="give_diltiazem",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Class III - Non-dihydropyridine CCBs contraindicated",
                ),
                ActionRecommendation(
                    action_id="give_verapamil",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Class III - Non-dihydropyridine CCBs contraindicated",
                ),
                ActionRecommendation(
                    action_id="give_thiazolidinedione",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Class III - Harm (fluid retention)",
                ),
            ],

            decision_entries=[
                # Device therapy evaluation for LVEF <= 35%
                DecisionTableEntry(
                    entry_id="device_therapy_evaluation",
                    description="LVEF <= 35% 시 Device Therapy 평가",
                    conditions=[
                        ClinicalCondition(
                            variable="lvef",
                            operator=ConditionOperator.LESS_EQUAL,
                            value=35,
                            description="LVEF <= 35%",
                        ),
                        ClinicalCondition(
                            variable="nyha_class",
                            operator=ConditionOperator.GREATER_EQUAL,
                            value=2,
                            description="NYHA Class >= II",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="assess_icd_indication",
                            action_type="assessment",
                            parameters={"type": "icd_indication"},
                            priority=80,
                            is_mandatory=True,
                            source_guideline="AHA HF 2022",
                            source_recommendation="Section 8",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="assess_crt_indication",
                            action_type="assessment",
                            parameters={"type": "crt_indication"},
                            priority=79,
                            is_mandatory=True,
                            source_guideline="AHA HF 2022",
                            evidence_level="1A",
                        ),
                    ],
                    priority=80,
                    source_guideline="AHA HF 2022",
                ),

                # ACEi/ARB intolerance - use Hydralazine/Isosorbide
                DecisionTableEntry(
                    entry_id="acei_arb_intolerance",
                    description="ACEi/ARB 불내성 시 대체 요법",
                    conditions=[
                        ClinicalCondition(
                            variable="acei_arb_intolerant",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="ACEi/ARB intolerant",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="add_hydralazine_isdn_if_intolerant",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "hydralazine_isosorbide",
                            },
                            priority=85,
                            is_mandatory=True,
                            source_guideline="AHA HF 2022",
                            evidence_level="1A",
                        ),
                    ],
                    priority=85,
                    source_guideline="AHA HF 2022",
                ),

                # Elevated HR with beta-blocker - consider Ivabradine
                DecisionTableEntry(
                    entry_id="elevated_hr_ivabradine",
                    description="Beta-blocker 최대용량에도 HR >= 70 시 Ivabradine",
                    conditions=[
                        ClinicalCondition(
                            variable="heart_rate",
                            operator=ConditionOperator.GREATER_EQUAL,
                            value=70,
                            description="HR >= 70 bpm",
                        ),
                        ClinicalCondition(
                            variable="on_max_beta_blocker",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="On maximal beta-blocker",
                        ),
                        ClinicalCondition(
                            variable="sinus_rhythm",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="In sinus rhythm",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="add_ivabradine_if_indicated",
                            action_type="give_medication",
                            parameters={"medication_code": "ivabradine"},
                            priority=70,
                            is_mandatory=False,
                            source_guideline="AHA HF 2022",
                            evidence_level="2aB",
                        ),
                    ],
                    priority=70,
                    source_guideline="AHA HF 2022",
                ),
            ],

            allergy_contraindications={
                "ace_inhibitor": ["lisinopril", "enalapril", "ramipril", "captopril"],
                "arb": ["losartan", "valsartan", "candesartan", "irbesartan"],
                "beta_blocker": ["carvedilol", "metoprolol", "bisoprolol"],
                "mra": ["spironolactone", "eplerenone"],
            },

            comorbidity_contraindications={
                "severe_asthma": ["beta_blocker"],
                "hyperkalemia": ["mra", "ace_inhibitor", "arb", "arni"],
                "severe_renal_failure": ["mra", "sglt2i"],
                "bilateral_renal_artery_stenosis": ["ace_inhibitor", "arb", "arni"],
            },
        )

        # ========================================
        # HFmrEF (EF 41-49%) Ruleset
        # ========================================
        hfmref_ruleset = ClinicalRuleSet(
            ruleset_id="aha_hfmref",
            name="AHA HFmrEF Treatment",
            description="Heart Failure with Mildly Reduced Ejection Fraction",
            source_guidelines=["AHA/ACC/HFSA 2022"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="order_bnp_or_ntprobnp",
                    action_type="order_lab",
                    parameters={"test_code": "bnp_or_ntprobnp"},
                    priority=100,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_echocardiogram",
                    action_type="order_diagnostic",
                    parameters={"diagnostic_type": "echocardiogram"},
                    priority=97,
                    deadline_minutes=1440,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="initiate_sglt2i",
                    action_type="give_medication",
                    parameters={"medication_class": "sglt2_inhibitor"},
                    priority=92,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Class I for HFmrEF",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_nsaid",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA HF 2022",
                ),
            ],

            decision_entries=[
                # Consider RAAS inhibitors
                DecisionTableEntry(
                    entry_id="hfmref_raas_consideration",
                    description="HFmrEF에서 RAAS 억제제 고려",
                    conditions=[
                        ClinicalCondition(
                            variable="symptoms_persistent",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Persistent symptoms",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="consider_ace_or_arb_or_arni",
                            action_type="give_medication",
                            parameters={"medication_class": "raas_inhibitor"},
                            priority=85,
                            is_mandatory=False,
                            source_guideline="AHA HF 2022",
                            source_recommendation="Class IIa",
                            evidence_level="2aB",
                        ),
                        ActionRecommendation(
                            action_id="consider_beta_blocker",
                            action_type="give_medication",
                            parameters={"medication_class": "beta_blocker"},
                            priority=84,
                            is_mandatory=False,
                            source_guideline="AHA HF 2022",
                            evidence_level="2aB",
                        ),
                        ActionRecommendation(
                            action_id="consider_mra",
                            action_type="give_medication",
                            parameters={"medication_class": "mra"},
                            priority=83,
                            is_mandatory=False,
                            source_guideline="AHA HF 2022",
                            evidence_level="2aB",
                        ),
                    ],
                    priority=85,
                    source_guideline="AHA HF 2022",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # HFpEF (EF >= 50%) Ruleset
        # ========================================
        hfpef_ruleset = ClinicalRuleSet(
            ruleset_id="aha_hfpef",
            name="AHA HFpEF Treatment",
            description="Heart Failure with Preserved Ejection Fraction",
            source_guidelines=["AHA/ACC/HFSA 2022"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="order_bnp_or_ntprobnp",
                    action_type="order_lab",
                    parameters={"test_code": "bnp_or_ntprobnp"},
                    priority=100,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_echocardiogram",
                    action_type="order_diagnostic",
                    parameters={"diagnostic_type": "echocardiogram"},
                    priority=97,
                    deadline_minutes=1440,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="initiate_sglt2i",
                    action_type="give_medication",
                    parameters={"medication_class": "sglt2_inhibitor"},
                    priority=92,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Class IIa for HFpEF",
                    evidence_level="2aA",
                ),
                ActionRecommendation(
                    action_id="manage_comorbidities",
                    action_type="assessment",
                    parameters={"type": "comorbidity_management"},
                    priority=90,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="manage_volume_status",
                    action_type="assessment",
                    parameters={"type": "volume_management"},
                    priority=89,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1C",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_nsaid",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA HF 2022",
                ),
            ],

            decision_entries=[
                # Diuretics for congestion
                DecisionTableEntry(
                    entry_id="hfpef_diuretics",
                    description="울혈 시 이뇨제",
                    conditions=[
                        ClinicalCondition(
                            variable="congestion",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Signs of congestion",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="diuretics_for_congestion",
                            action_type="give_medication",
                            parameters={"medication_class": "diuretic"},
                            priority=85,
                            is_mandatory=True,
                            source_guideline="AHA HF 2022",
                            evidence_level="1B",
                        ),
                    ],
                    priority=85,
                    source_guideline="AHA HF 2022",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # ADHF Warm-Wet Ruleset
        # ========================================
        adhf_warm_wet_ruleset = ClinicalRuleSet(
            ruleset_id="aha_adhf_warm_wet",
            name="AHA ADHF Warm-Wet Management",
            description="Acute Decompensated HF - Warm and Wet Profile",
            source_guidelines=["AHA/ACC/HFSA 2022"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_hemodynamic_profile",
                    action_type="assessment",
                    parameters={"type": "hemodynamic_profile"},
                    priority=100,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Section 9",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="identify_precipitating_factors",
                    action_type="assessment",
                    parameters={"type": "precipitating_factors"},
                    priority=99,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="iv_diuretics",
                    action_type="give_medication",
                    parameters={"medication_class": "iv_loop_diuretic"},
                    priority=95,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Section 9.2",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="fluid_restrict",
                    action_type="order",
                    parameters={"type": "fluid_restriction"},
                    priority=90,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="daily_weights",
                    action_type="monitoring",
                    parameters={"type": "daily_weight"},
                    priority=85,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="monitor_urine_output",
                    action_type="monitoring",
                    parameters={"type": "urine_output"},
                    priority=84,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="monitor_electrolytes",
                    action_type="order_lab",
                    parameters={"test_code": "electrolytes"},
                    priority=83,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_iv_inotropes",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Not indicated in warm-wet (adequate perfusion)",
                ),
            ],

            decision_entries=[
                # Hypertensive - add vasodilator
                DecisionTableEntry(
                    entry_id="warm_wet_hypertensive",
                    description="고혈압 동반 시 혈관확장제 추가",
                    conditions=[
                        ClinicalCondition(
                            variable="sbp_mmhg",
                            operator=ConditionOperator.GREATER_THAN,
                            value=140,
                            description="SBP > 140 mmHg",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="add_vasodilator_if_hypertensive",
                            action_type="give_medication",
                            parameters={"medication_class": "vasodilator"},
                            priority=80,
                            is_mandatory=False,
                            source_guideline="AHA HF 2022",
                            evidence_level="2aB",
                        ),
                    ],
                    priority=80,
                    source_guideline="AHA HF 2022",
                ),
            ],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # ADHF Cold-Wet Ruleset
        # ========================================
        adhf_cold_wet_ruleset = ClinicalRuleSet(
            ruleset_id="aha_adhf_cold_wet",
            name="AHA ADHF Cold-Wet Management",
            description="Acute Decompensated HF - Cold and Wet Profile",
            source_guidelines=["AHA/ACC/HFSA 2022"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_hemodynamic_profile",
                    action_type="assessment",
                    parameters={"type": "hemodynamic_profile"},
                    priority=100,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="iv_diuretics",
                    action_type="give_medication",
                    parameters={"medication_class": "iv_loop_diuretic"},
                    priority=95,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="consider_inotropes",
                    action_type="give_medication",
                    parameters={"medication_class": "inotrope"},
                    priority=90,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Section 9.3",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="consider_vasodilators",
                    action_type="give_medication",
                    parameters={"medication_class": "vasodilator"},
                    priority=85,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="2aB",
                ),
                ActionRecommendation(
                    action_id="hemodynamic_monitoring",
                    action_type="monitoring",
                    parameters={"type": "hemodynamic"},
                    priority=80,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_high_dose_beta_blocker",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Avoid in low output state",
                ),
            ],

            decision_entries=[],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # ADHF Cold-Dry Ruleset
        # ========================================
        adhf_cold_dry_ruleset = ClinicalRuleSet(
            ruleset_id="aha_adhf_cold_dry",
            name="AHA ADHF Cold-Dry Management",
            description="Acute Decompensated HF - Cold and Dry Profile",
            source_guidelines=["AHA/ACC/HFSA 2022"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="assess_hemodynamic_profile",
                    action_type="assessment",
                    parameters={"type": "hemodynamic_profile"},
                    priority=100,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="careful_fluid_challenge",
                    action_type="give_medication",
                    parameters={"medication_class": "crystalloid", "dose": "250ml_bolus"},
                    priority=95,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Section 9.4",
                    evidence_level="2aC",
                ),
                ActionRecommendation(
                    action_id="hemodynamic_monitoring",
                    action_type="monitoring",
                    parameters={"type": "hemodynamic"},
                    priority=90,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1C",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_diuretics",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Diuretics contraindicated in cold-dry (no congestion)",
                ),
            ],

            decision_entries=[],

            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        # ========================================
        # Cardiogenic Shock Ruleset
        # ========================================
        cardiogenic_shock_ruleset = ClinicalRuleSet(
            ruleset_id="aha_cardiogenic_shock",
            name="AHA Cardiogenic Shock Management",
            description="Cardiogenic Shock due to Heart Failure",
            source_guidelines=["AHA/ACC/HFSA 2022"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="icu_admission",
                    action_type="disposition",
                    parameters={"unit": "icu"},
                    priority=100,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Section 9.5",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="invasive_hemodynamic_monitoring",
                    action_type="procedure",
                    parameters={"procedure_code": "pulmonary_artery_catheter"},
                    priority=98,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="vasopressor_support",
                    action_type="give_medication",
                    parameters={"medication_class": "vasopressor"},
                    priority=95,
                    deadline_minutes=30,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="inotrope_support",
                    action_type="give_medication",
                    parameters={"medication_class": "inotrope"},
                    priority=94,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="mechanical_circulatory_support_evaluation",
                    action_type="assessment",
                    parameters={"type": "mcs_evaluation"},
                    priority=90,
                    is_mandatory=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Section 9.6",
                    evidence_level="2aB",
                ),
            ],

            always_forbidden=[
                ActionRecommendation(
                    action_id="give_beta_blocker",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Beta-blockers contraindicated in cardiogenic shock",
                ),
                ActionRecommendation(
                    action_id="give_high_dose_diuretics_if_hypotensive",
                    action_type="give_medication",
                    is_forbidden=True,
                    source_guideline="AHA HF 2022",
                    source_recommendation="Avoid diuretics if hypotensive",
                ),
            ],

            decision_entries=[
                # MCS device selection
                DecisionTableEntry(
                    entry_id="mcs_selection",
                    description="MCS 필요 시 장치 선택",
                    conditions=[
                        ClinicalCondition(
                            variable="mcs_indicated",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="MCS indicated",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="select_mcs_device",
                            action_type="procedure",
                            parameters={"procedure_code": "mcs_selection"},
                            priority=85,
                            is_mandatory=True,
                            source_guideline="AHA HF 2022",
                            evidence_level="2aB",
                        ),
                        ActionRecommendation(
                            action_id="multidisciplinary_team_evaluation",
                            action_type="consultation",
                            parameters={"consult_type": "mcs_team"},
                            priority=84,
                            is_mandatory=True,
                            source_guideline="AHA HF 2022",
                            evidence_level="1C",
                        ),
                    ],
                    priority=85,
                    source_guideline="AHA HF 2022",
                ),
            ],

            allergy_contraindications={},

            comorbidity_contraindications={
                "active_bleeding": ["anticoagulation", "mcs"],
                "severe_peripheral_vascular_disease": ["iabp", "impella"],
            },
        )

        # Register all rulesets
        self.rulesets["hfref"] = hfref_ruleset
        self.rulesets["hfmref"] = hfmref_ruleset
        self.rulesets["hfpef"] = hfpef_ruleset
        self.rulesets["adhf_warm_wet"] = adhf_warm_wet_ruleset
        self.rulesets["adhf_cold_wet"] = adhf_cold_wet_ruleset
        self.rulesets["adhf_cold_dry"] = adhf_cold_dry_ruleset
        self.rulesets["cardiogenic_shock"] = cardiogenic_shock_ruleset

    def _determine_scenario_type(self, context: dict[str, Any]) -> str:
        """시나리오 유형 결정"""
        diagnosis = (context.get("working_diagnosis") or "").lower()
        lvef = context.get("lvef")
        hemodynamic_profile = (context.get("hemodynamic_profile") or "").lower()
        acute_decompensation = context.get("acute_decompensation", False)
        sbp = context.get("sbp_mmhg", 120)
        perfusion_status = (context.get("perfusion_status") or "").lower()
        congestion_status = (context.get("congestion_status") or "").lower()

        # Check for cardiogenic shock first (highest priority)
        cardiogenic_indicators = [
            "cardiogenic_shock", "cardiogenic shock",
            "shock", "severe_hypoperfusion"
        ]
        if any(ind in diagnosis for ind in cardiogenic_indicators):
            return "cardiogenic_shock"
        if sbp < 90 and ("cold" in perfusion_status or "hypoperfused" in perfusion_status):
            return "cardiogenic_shock"

        # Check for ADHF with hemodynamic profiles
        if acute_decompensation or "adhf" in diagnosis or "decompensated" in diagnosis:
            # First check for explicit ADHF subtypes in diagnosis
            if "cold_wet" in diagnosis or "cold-wet" in diagnosis:
                return "adhf_cold_wet"
            if "cold_dry" in diagnosis or "cold-dry" in diagnosis:
                return "adhf_cold_dry"
            if "warm_wet" in diagnosis or "warm-wet" in diagnosis:
                return "adhf_warm_wet"

            # Determine hemodynamic profile
            if hemodynamic_profile:
                if "warm" in hemodynamic_profile and "wet" in hemodynamic_profile:
                    return "adhf_warm_wet"
                if "cold" in hemodynamic_profile and "wet" in hemodynamic_profile:
                    return "adhf_cold_wet"
                if "cold" in hemodynamic_profile and "dry" in hemodynamic_profile:
                    return "adhf_cold_dry"

            # Infer from perfusion and congestion status
            is_cold = "cold" in perfusion_status or "hypoperfused" in perfusion_status
            is_wet = "wet" in congestion_status or "congested" in congestion_status

            if is_cold and is_wet:
                return "adhf_cold_wet"
            if is_cold and not is_wet:
                return "adhf_cold_dry"
            if not is_cold and is_wet:
                return "adhf_warm_wet"

            # Default ADHF profile
            return "adhf_warm_wet"

        # Chronic HF classification based on LVEF
        if lvef is not None:
            if lvef <= 40:
                return "hfref"
            elif lvef <= 49:
                return "hfmref"
            else:
                return "hfpef"

        # Infer from diagnosis text
        if "hfref" in diagnosis or "reduced" in diagnosis:
            return "hfref"
        if "hfmref" in diagnosis or "mildly_reduced" in diagnosis:
            return "hfmref"
        if "hfpef" in diagnosis or "preserved" in diagnosis:
            return "hfpef"

        # Default to HFrEF (most common and requires most intervention)
        return "hfref"

    def is_cardiogenic_shock(self, context: dict[str, Any]) -> bool:
        """심인성 쇼크 여부 확인"""
        return self._determine_scenario_type(context) == "cardiogenic_shock"

    def is_adhf(self, context: dict[str, Any]) -> bool:
        """급성 비대상성 심부전 여부 확인"""
        scenario_type = self._determine_scenario_type(context)
        return scenario_type.startswith("adhf_") or scenario_type == "cardiogenic_shock"

    def get_forbidden_actions(self, context: dict[str, Any]) -> list[str]:
        """현재 상태에서 금기인 행동 목록 반환"""
        forbidden = super().get_forbidden_actions(context)
        scenario_type = self._determine_scenario_type(context)
        lvef = context.get("lvef")

        # HFrEF specific forbidden actions
        if scenario_type == "hfref" or (lvef is not None and lvef <= 40):
            forbidden.extend([
                "give_nsaid",
                "nsaid",
                "give_diltiazem",
                "diltiazem",
                "give_verapamil",
                "verapamil",
                "give_thiazolidinedione",
                "thiazolidinedione",
                "pioglitazone",
                "rosiglitazone",
            ])

        # ADHF warm-wet: no inotropes
        if scenario_type == "adhf_warm_wet":
            forbidden.extend([
                "give_iv_inotropes",
                "dobutamine",
                "milrinone",
                "inotrope",
            ])

        # ADHF cold-dry: no diuretics
        if scenario_type == "adhf_cold_dry":
            forbidden.extend([
                "give_diuretics",
                "furosemide",
                "bumetanide",
                "torsemide",
            ])

        # Cardiogenic shock: no beta-blockers
        if scenario_type == "cardiogenic_shock":
            forbidden.extend([
                "give_beta_blocker",
                "beta_blocker",
                "carvedilol",
                "metoprolol",
                "bisoprolol",
            ])

        return list(set(forbidden))

    def get_hemodynamic_profile(self, context: dict[str, Any]) -> str:
        """Hemodynamic profile 반환"""
        scenario_type = self._determine_scenario_type(context)
        if scenario_type == "adhf_warm_wet":
            return "warm_wet"
        elif scenario_type == "adhf_cold_wet":
            return "cold_wet"
        elif scenario_type == "adhf_cold_dry":
            return "cold_dry"
        elif scenario_type == "cardiogenic_shock":
            return "cardiogenic_shock"
        return "stable"
