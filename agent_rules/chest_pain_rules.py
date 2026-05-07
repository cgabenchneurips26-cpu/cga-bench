"""Chest Pain Decision Table: AHA/ACC 2021 가이드라인 기반 독립적 규칙

출처: 2021 AHA/ACC Guideline for Chest Pain
DOI: 10.1161/CIR.0000000000001029

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


class ChestPainDecisionTable(RuleBasedDecisionTable):
    """AHA/ACC 2021 기반 Chest Pain 의사결정 테이블

    참조 가이드라인:
    - AHA/ACC 2021 Chest Pain Guideline
    - AHA 2013 STEMI Guideline

    이 구현은 채점용 CPG-Engine과 완전히 독립적입니다.
    """

    def _load_rulesets(self):
        """AHA/ACC 2021 규칙 로드"""
        # ========================================
        # STEMI Ruleset
        # ========================================
        stemi_ruleset = ClinicalRuleSet(
            ruleset_id="aha_stemi",
            name="AHA STEMI Management",
            description="ST상승 심근경색 응급 관리",
            source_guidelines=["AHA 2021", "AHA 2013 STEMI"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="obtain_ecg",
                    action_type="order_diagnostic",
                    parameters={"diagnostic_type": "12_lead_ecg"},
                    priority=100,
                    deadline_minutes=10,  # Door-to-ECG < 10분
                    is_mandatory=True,
                    source_guideline="AHA 2021",
                    source_recommendation="Class I, LOE B",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="check_vital_signs",
                    action_type="assessment",
                    parameters={"type": "vital_signs"},
                    priority=99,
                    deadline_minutes=5,
                    is_mandatory=True,
                    source_guideline="AHA 2021",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="obtain_chest_pain_history",
                    action_type="assessment",
                    parameters={"type": "history"},
                    priority=98,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="AHA 2021",
                    evidence_level="1C",
                ),
                ActionRecommendation(
                    action_id="order_troponin",
                    action_type="order_lab",
                    parameters={"test_code": "troponin"},
                    priority=95,
                    deadline_minutes=60,
                    is_mandatory=True,
                    source_guideline="AHA 2021",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[],

            decision_entries=[
                # STEMI 확인 시 Cath Lab 활성화
                DecisionTableEntry(
                    entry_id="activate_cath_lab_stemi",
                    description="STEMI 확인 시 Cath Lab 활성화",
                    conditions=[
                        ClinicalCondition(
                            variable="ecg_stemi",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="ECG shows STEMI",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="activate_cath_lab",
                            action_type="procedure",
                            parameters={"procedure_code": "cath_lab_activation"},
                            priority=100,
                            deadline_minutes=10,  # STEMI 인지 후 10분
                            is_mandatory=True,
                            required_prior_actions=["obtain_ecg"],
                            source_guideline="AHA 2013 STEMI",
                            source_recommendation="Door-to-balloon < 90min",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="aspirin_loading",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "aspirin",
                                "dose": "325mg",
                                "route": "chew",
                            },
                            priority=95,
                            deadline_minutes=15,
                            is_mandatory=True,
                            source_guideline="AHA 2013 STEMI",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="p2y12_loading",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "p2y12_inhibitor",
                            },
                            priority=90,
                            deadline_minutes=30,
                            is_mandatory=True,
                            source_guideline="AHA 2013 STEMI",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="anticoagulation",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "heparin",
                            },
                            priority=85,
                            deadline_minutes=30,
                            is_mandatory=True,
                            source_guideline="AHA 2013 STEMI",
                            evidence_level="1B",
                        ),
                        ActionRecommendation(
                            action_id="arrange_pci",
                            action_type="procedure",
                            parameters={"procedure_code": "primary_pci"},
                            priority=80,
                            deadline_minutes=90,  # Door-to-balloon < 90min
                            is_mandatory=True,
                            required_prior_actions=["activate_cath_lab"],
                            source_guideline="AHA 2013 STEMI",
                            source_recommendation="Primary PCI is recommended",
                            evidence_level="1A",
                        ),
                    ],
                    priority=100,
                    source_guideline="AHA 2013 STEMI",
                ),

                # Inferior STEMI + RV involvement 시 니트로글리세린 금기
                DecisionTableEntry(
                    entry_id="rv_infarct_contraindication",
                    description="RV 경색 시 니트로글리세린/전부하 감소제 금기",
                    conditions=[
                        ClinicalCondition(
                            variable="ecg_inferior_stemi",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Inferior STEMI",
                        ),
                        ClinicalCondition(
                            variable="rv_involvement",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="RV involvement (V4R ST elevation)",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="contraindicate_nitroglycerin",
                            action_type="contraindication",
                            parameters={
                                "contraindicated_medication": "nitroglycerin",
                                "reason": "RV infarction - preload dependent",
                            },
                            is_forbidden=True,
                            source_guideline="AHA 2013 STEMI",
                            source_recommendation="Class III - Harm",
                            evidence_level="1B",
                        ),
                        ActionRecommendation(
                            action_id="contraindicate_morphine",
                            action_type="contraindication",
                            parameters={
                                "contraindicated_medication": "morphine",
                                "reason": "RV infarction - preload dependent",
                            },
                            is_forbidden=True,
                            source_guideline="AHA 2013 STEMI",
                        ),
                    ],
                    priority=100,
                    source_guideline="AHA 2013 STEMI",
                ),

                # 저혈압 시 니트로글리세린 금기
                DecisionTableEntry(
                    entry_id="hypotension_nitrate_contraindication",
                    description="저혈압 시 니트로글리세린 금기",
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
                            action_id="contraindicate_nitroglycerin_hypotension",
                            action_type="contraindication",
                            parameters={
                                "contraindicated_medication": "nitroglycerin",
                                "reason": "Hypotension",
                            },
                            is_forbidden=True,
                            source_guideline="AHA 2021",
                        ),
                    ],
                    priority=95,
                    source_guideline="AHA 2021",
                ),
            ],

            allergy_contraindications={
                "aspirin": ["aspirin"],
                "nsaid": ["aspirin", "ibuprofen", "ketorolac"],
                "heparin": ["heparin", "enoxaparin"],
            },

            comorbidity_contraindications={
                "active_bleeding": ["aspirin", "heparin", "p2y12_inhibitor"],
                "recent_stroke": ["thrombolysis"],
            },
        )

        # ========================================
        # NSTE-ACS Ruleset
        # ========================================
        nste_acs_ruleset = ClinicalRuleSet(
            ruleset_id="aha_nste_acs",
            name="AHA NSTE-ACS Management",
            description="비ST상승 급성관상동맥증후군 관리",
            source_guidelines=["AHA 2021"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="obtain_ecg",
                    action_type="order_diagnostic",
                    parameters={"diagnostic_type": "12_lead_ecg"},
                    priority=100,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="AHA 2021",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="serial_troponin",
                    action_type="order_lab",
                    parameters={"test_code": "troponin", "serial": True},
                    priority=95,
                    is_mandatory=True,
                    source_guideline="AHA 2021",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[],

            decision_entries=[
                # Troponin 상승 시 NSTEMI 진단
                DecisionTableEntry(
                    entry_id="nstemi_management",
                    description="NSTEMI 진단 및 관리",
                    conditions=[
                        ClinicalCondition(
                            variable="troponin_elevated",
                            operator=ConditionOperator.IS_TRUE,
                            value=True,
                            description="Troponin elevated",
                        ),
                    ],
                    actions=[
                        ActionRecommendation(
                            action_id="aspirin_loading",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "aspirin",
                                "dose": "325mg",
                            },
                            priority=95,
                            deadline_minutes=30,
                            is_mandatory=True,
                            source_guideline="AHA 2021",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="anticoagulation",
                            action_type="give_medication",
                            parameters={
                                "medication_code": "anticoagulant",
                            },
                            priority=90,
                            is_mandatory=True,
                            source_guideline="AHA 2021",
                            evidence_level="1A",
                        ),
                        ActionRecommendation(
                            action_id="risk_stratification",
                            action_type="assessment",
                            parameters={"tool": "TIMI_or_GRACE"},
                            priority=85,
                            is_mandatory=True,
                            source_guideline="AHA 2021",
                            evidence_level="1B",
                        ),
                    ],
                    priority=90,
                    source_guideline="AHA 2021",
                ),
            ],

            allergy_contraindications={
                "aspirin": ["aspirin"],
            },

            comorbidity_contraindications={},
        )

        # ========================================
        # Low Risk Chest Pain Ruleset
        # ========================================
        low_risk_ruleset = ClinicalRuleSet(
            ruleset_id="aha_low_risk",
            name="AHA Low Risk Chest Pain",
            description="저위험 흉통 평가",
            source_guidelines=["AHA 2021"],

            always_mandatory=[
                ActionRecommendation(
                    action_id="obtain_ecg",
                    action_type="order_diagnostic",
                    parameters={"diagnostic_type": "12_lead_ecg"},
                    priority=100,
                    deadline_minutes=10,
                    is_mandatory=True,
                    source_guideline="AHA 2021",
                    evidence_level="1B",
                ),
                ActionRecommendation(
                    action_id="order_troponin",
                    action_type="order_lab",
                    parameters={"test_code": "troponin"},
                    priority=95,
                    is_mandatory=True,
                    source_guideline="AHA 2021",
                    evidence_level="1A",
                ),
            ],

            always_forbidden=[],
            decision_entries=[],
            allergy_contraindications={},
            comorbidity_contraindications={},
        )

        self.rulesets["stemi"] = stemi_ruleset
        self.rulesets["nste_acs"] = nste_acs_ruleset
        self.rulesets["low_risk_chest_pain"] = low_risk_ruleset

    def _determine_scenario_type(self, context: dict[str, Any]) -> str:
        """시나리오 유형 결정"""
        diagnosis = (context.get("working_diagnosis") or "").lower()
        ecg_stemi = context.get("ecg_stemi", False)
        troponin_elevated = context.get("troponin_elevated", False)

        if "stemi" in diagnosis or ecg_stemi:
            return "stemi"

        if "nstemi" in diagnosis or "nste_acs" in diagnosis or troponin_elevated:
            return "nste_acs"

        return "low_risk_chest_pain"

    def is_rv_infarct_scenario(self, context: dict[str, Any]) -> bool:
        """RV 경색 시나리오인지 확인 (니트로글리세린 금기 판단용)"""
        return (
            context.get("ecg_inferior_stemi", False) and
            context.get("rv_involvement", False)
        )

    def get_forbidden_actions(self, context: dict[str, Any]) -> list[str]:
        """현재 상태에서 금기인 행동 목록 반환 (RV 경색 특별 처리)"""
        forbidden = super().get_forbidden_actions(context)

        # RV 경색 시 니트로글리세린 금기
        if self.is_rv_infarct_scenario(context):
            forbidden.extend([
                "nitroglycerin",
                "morphine",
                "give_nitroglycerin",
                "nitrate",
            ])

        # 저혈압 시 니트로글리세린 금기
        sbp = context.get("sbp_mmhg", 120)
        if sbp < 90:
            forbidden.extend([
                "nitroglycerin",
                "give_nitroglycerin",
                "nitrate",
            ])

        return list(set(forbidden))
