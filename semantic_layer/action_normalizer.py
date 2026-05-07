"""
Semantic Action Normalizer: LLM 기반 액션 매핑

LLM이 생성한 자유형식 액션을 유효한 액션 ID로 변환합니다.

기능:
- 시맨틱 유사도 기반 매핑
- 약어/동의어 처리
- 컨텍스트 인식 매핑
- 새 도메인 자동 적응
"""

import logging
from dataclasses import dataclass
from typing import Dict, Any, List, Optional, Tuple
from difflib import SequenceMatcher

from cga_bench.agent_runner.llm_provider import BaseLLMProvider, LLMMessage
from .cpg_parser import ParsedGuideline

logger = logging.getLogger(__name__)


@dataclass
class NormalizationResult:
    """정규화 결과"""
    original_action: str
    normalized_action: str
    confidence: float
    mapping_method: str  # exact, fuzzy, semantic, llm
    alternatives: List[str] = None


class SemanticActionNormalizer:
    """
    시맨틱 액션 정규화기

    LLM 출력을 유효한 Decision Table 액션으로 매핑합니다.
    """

    def __init__(
        self,
        llm_provider: Optional[BaseLLMProvider] = None,
        use_llm_fallback: bool = True,
        strict_mode: bool = False
    ):
        """
        Args:
            llm_provider: LLM 프로바이더 (None이면 rule-based만 사용)
            use_llm_fallback: LLM fallback 활성화 여부
            strict_mode: True면 LLM 없을 때 에러 발생
        """
        self.llm_provider = llm_provider
        self.use_llm_fallback = use_llm_fallback
        self.strict_mode = strict_mode

        # LLM fallback 요청했는데 없으면 경고
        if use_llm_fallback and llm_provider is None:
            if strict_mode:
                raise ValueError(
                    "SemanticActionNormalizer: strict_mode=True but llm_provider is None. "
                    "LLM fallback requires a valid LLM provider."
                )
            else:
                logger.warning(
                    "⚠️ SemanticActionNormalizer: use_llm_fallback=True but llm_provider is None. "
                    "LLM semantic matching will be DISABLED. Using rule-based matching only."
                )

        # 도메인별 액션 어휘
        self._action_vocabulary: Dict[str, List[str]] = {}

        # 약어 매핑
        self._abbreviation_map = self._build_abbreviation_map()

        # 동의어 매핑
        self._synonym_map = self._build_synonym_map()

        # 도메인별 직접 매핑 (핵심 수정)
        self._domain_direct_mappings = self._build_domain_direct_mappings()

        # 캐시
        self._cache: Dict[str, NormalizationResult] = {}

    def register_vocabulary(
        self,
        domain: str,
        valid_actions: List[str],
        from_guideline: Optional[ParsedGuideline] = None
    ):
        """도메인별 유효한 액션 어휘 등록"""
        self._action_vocabulary[domain] = valid_actions

        # 가이드라인에서 추가 매핑 추출
        if from_guideline:
            for rec in from_guideline.recommendations:
                # Add original text as alias
                self._synonym_map[rec.text.lower()[:50]] = rec.action_id

    def normalize(
        self,
        action_id: str,
        domain: str = "general",
        context: Optional[Dict[str, Any]] = None
    ) -> NormalizationResult:
        """
        액션 ID 정규화

        Args:
            action_id: LLM이 생성한 액션 ID
            domain: 임상 도메인
            context: 환자 컨텍스트

        Returns:
            NormalizationResult: 정규화 결과
        """
        cache_key = f"{domain}:{action_id}"
        if cache_key in self._cache:
            return self._cache[cache_key]

        # Get valid actions for domain
        valid_actions = self._action_vocabulary.get(domain, [])
        if not valid_actions:
            valid_actions = self._get_default_actions()

        # Step 0: Domain-specific direct mapping (HIGHEST PRIORITY)
        action_lower = action_id.lower().replace("-", "_").replace(" ", "_")
        domain_mappings = self._domain_direct_mappings.get(domain, {})
        if action_lower in domain_mappings:
            mapped_action = domain_mappings[action_lower]
            result = NormalizationResult(
                original_action=action_id,
                normalized_action=mapped_action,
                confidence=0.98,
                mapping_method="domain_direct"
            )
            self._cache[cache_key] = result
            logger.info(f"Domain direct mapping: '{action_id}' -> '{mapped_action}' (domain={domain})")
            return result

        # Also check without common prefixes
        for prefix in ["order_", "give_", "check_", "assess_", "obtain_", "start_"]:
            if action_lower.startswith(prefix):
                stripped = action_lower[len(prefix):]
                if stripped in domain_mappings:
                    mapped_action = domain_mappings[stripped]
                    result = NormalizationResult(
                        original_action=action_id,
                        normalized_action=mapped_action,
                        confidence=0.95,
                        mapping_method="domain_direct_stripped"
                    )
                    self._cache[cache_key] = result
                    logger.info(f"Domain direct mapping (stripped): '{action_id}' -> '{mapped_action}'")
                    return result

        # Step 1: Exact match
        if action_id in valid_actions:
            result = NormalizationResult(
                original_action=action_id,
                normalized_action=action_id,
                confidence=1.0,
                mapping_method="exact"
            )
            self._cache[cache_key] = result
            return result

        # Step 2: Case-insensitive match
        # action_lower already defined in Step 0
        for valid in valid_actions:
            if action_lower == valid.lower():
                result = NormalizationResult(
                    original_action=action_id,
                    normalized_action=valid,
                    confidence=0.95,
                    mapping_method="case_insensitive"
                )
                self._cache[cache_key] = result
                return result

        # Step 3: Abbreviation expansion
        expanded = self._expand_abbreviations(action_lower)
        for valid in valid_actions:
            if expanded == valid.lower() or expanded in valid.lower():
                result = NormalizationResult(
                    original_action=action_id,
                    normalized_action=valid,
                    confidence=0.9,
                    mapping_method="abbreviation"
                )
                self._cache[cache_key] = result
                return result

        # Step 4: Synonym matching
        synonym_match = self._find_synonym_match(action_lower, valid_actions)
        if synonym_match:
            result = NormalizationResult(
                original_action=action_id,
                normalized_action=synonym_match,
                confidence=0.85,
                mapping_method="synonym"
            )
            self._cache[cache_key] = result
            return result

        # Step 5: Fuzzy matching
        fuzzy_match, fuzzy_score = self._fuzzy_match(action_lower, valid_actions)
        if fuzzy_score > 0.6:
            result = NormalizationResult(
                original_action=action_id,
                normalized_action=fuzzy_match,
                confidence=fuzzy_score,
                mapping_method="fuzzy"
            )
            self._cache[cache_key] = result
            return result

        # Step 6: LLM-based semantic matching (fallback)
        if self.llm_provider and self.use_llm_fallback:
            llm_match = self._semantic_match_with_llm(
                action_id, valid_actions, context
            )
            if llm_match:
                result = NormalizationResult(
                    original_action=action_id,
                    normalized_action=llm_match,
                    confidence=0.75,
                    mapping_method="llm_semantic"
                )
                self._cache[cache_key] = result
                return result

        # No match found
        result = NormalizationResult(
            original_action=action_id,
            normalized_action=action_id,  # Return original
            confidence=0.0,
            mapping_method="no_match",
            alternatives=self._get_top_alternatives(action_lower, valid_actions, n=3)
        )
        self._cache[cache_key] = result
        return result

    def normalize_batch(
        self,
        action_ids: List[str],
        domain: str = "general",
        context: Optional[Dict[str, Any]] = None
    ) -> List[NormalizationResult]:
        """여러 액션 일괄 정규화"""
        return [self.normalize(aid, domain, context) for aid in action_ids]

    def _build_abbreviation_map(self) -> Dict[str, str]:
        """약어 매핑 구축"""
        return {
            # Labs
            "ecg": "electrocardiogram",
            "ekg": "electrocardiogram",
            "cbc": "complete_blood_count",
            "bmp": "basic_metabolic_panel",
            "cmp": "comprehensive_metabolic_panel",
            "bnp": "brain_natriuretic_peptide",
            "ntprobnp": "n_terminal_pro_bnp",
            "tsh": "thyroid_stimulating_hormone",
            "cxr": "chest_xray",
            "ct": "computed_tomography",
            "mri": "magnetic_resonance_imaging",
            "ua": "urinalysis",
            "abg": "arterial_blood_gas",
            "vbg": "venous_blood_gas",
            "pt": "prothrombin_time",
            "inr": "international_normalized_ratio",
            "ptt": "partial_thromboplastin_time",

            # Medications
            "abx": "antibiotics",
            "ns": "normal_saline",
            "lr": "lactated_ringers",
            "epi": "epinephrine",
            "norepi": "norepinephrine",
            "levo": "levofloxacin",
            "vanc": "vancomycin",
            "pip_tazo": "piperacillin_tazobactam",
            "zosyn": "piperacillin_tazobactam",
            "ntg": "nitroglycerin",
            "asa": "aspirin",
            "tpa": "alteplase",
            "rtpa": "alteplase",

            # Procedures
            "pci": "percutaneous_coronary_intervention",
            "cabg": "coronary_artery_bypass_graft",
            "rrt": "renal_replacement_therapy",
            "niv": "non_invasive_ventilation",
            "bipap": "bilevel_positive_airway_pressure",
            "cpap": "continuous_positive_airway_pressure",

            # Clinical terms
            "bp": "blood_pressure",
            "hr": "heart_rate",
            "rr": "respiratory_rate",
            "spo2": "oxygen_saturation",
            "map": "mean_arterial_pressure",
            "cvp": "central_venous_pressure",
        }

    def _build_domain_direct_mappings(self) -> Dict[str, Dict[str, str]]:
        """
        도메인별 직접 매핑 구축

        LLM이 생성하는 액션 ID와 CPG에서 기대하는 액션 ID 간의 차이를 해소
        """
        return {
            "medagentbench": {
                # Electrolyte checks
                "check_potassium_level": "check_electrolyte_levels",
                "check_magnesium_level": "check_electrolyte_levels",
                "order_potassium_if_low": "check_electrolyte_levels",
                "order_magnesium_if_low": "check_electrolyte_levels",
                # Diabetes/glucose checks
                "retrieve_glucose_value": "check_blood_glucose",
                "retrieve_glucose_values": "check_blood_glucose",
                "retrieve_hba1c": "check_blood_glucose",
                "calculate_average": "check_blood_glucose",
                # EHR identity workflows
                "search_by_name_dob": "verify_patient_identity",
                "get_patient_birthdate": "verify_patient_identity",
                "calculate_age": "verify_patient_identity",
                # Documentation
                "post_vital_sign": "document_vitals",
                "query_lab_results": "view_lab_results",
            },
            "chest_pain": {
                # ECG 관련
                "order_imaging_ecg": "obtain_12_lead_ecg",
                "order_ecg": "obtain_12_lead_ecg",
                "get_ecg": "obtain_12_lead_ecg",
                "12_lead_ecg": "obtain_12_lead_ecg",
                "ecg_12_lead": "obtain_12_lead_ecg",
                "obtain_ecg": "obtain_12_lead_ecg",
                # Right-sided ECG (RV infarct)
                "order_right_sided_ecg": "obtain_right_sided_ecg_v4r",
                "right_sided_ecg": "obtain_right_sided_ecg_v4r",
                "v4r_ecg": "obtain_right_sided_ecg_v4r",
                # Troponin
                "order_lab_troponin": "order_troponin",
                "check_troponin": "order_troponin",
                "get_troponin": "order_troponin",
                # Aspirin
                "give_aspirin_loading": "give_aspirin",
                "aspirin_loading": "give_aspirin",
                "administer_aspirin": "give_aspirin",
                "give_aspirin_325": "give_aspirin",
                # Anticoagulation
                "give_heparin": "give_anticoagulation",
                "start_heparin": "give_anticoagulation",
                "give_enoxaparin": "give_anticoagulation",
                # P2Y12 inhibitor
                "give_clopidogrel": "give_p2y12_inhibitor",
                "give_ticagrelor": "give_p2y12_inhibitor",
                "give_prasugrel": "give_p2y12_inhibitor",
                # Cath lab
                "call_cath_lab": "activate_cath_lab",
                "notify_cath_lab": "activate_cath_lab",
                # Vitals
                "check_vital_signs": "assess_vital_signs",
                "measure_vitals": "assess_vital_signs",
                "obtain_vital_signs": "assess_vital_signs",
                # History
                "get_chest_pain_history": "obtain_chest_pain_history",
                "chest_pain_history": "obtain_chest_pain_history",
                # IV fluid for RV infarct
                "give_iv_fluid_bolus": "start_iv_fluid_bolus",
                "give_normal_saline": "start_iv_fluid_bolus",
                "iv_fluid_bolus": "start_iv_fluid_bolus",
            },
            "stroke": {
                # CT Head
                "order_ct_head": "order_stat_ct_head",
                "ct_head": "order_stat_ct_head",
                "order_imaging_ct_head": "order_stat_ct_head",
                "get_ct_head": "order_stat_ct_head",
                "stat_ct_head": "order_stat_ct_head",
                "order_head_ct": "order_stat_ct_head",
                # NIHSS
                "assess_nihss": "perform_nihss",
                "nihss": "perform_nihss",
                "calculate_nihss": "perform_nihss",
                "nihss_score": "perform_nihss",
                "check_nihss": "perform_nihss",
                # Glucose
                "order_lab_glucose": "check_glucose",
                "check_blood_glucose": "check_glucose",
                "order_lab_bmp": "check_glucose",
                "glucose_level": "check_glucose",
                "measure_glucose": "check_glucose",
                # tPA/Alteplase
                "give_tpa": "give_alteplase_0.9mg_kg",
                "give_alteplase": "give_alteplase_0.9mg_kg",
                "start_tpa": "give_alteplase_0.9mg_kg",
                "administer_alteplase": "give_alteplase_0.9mg_kg",
                "tpa_infusion": "give_alteplase_0.9mg_kg",
                # Stroke team
                "call_stroke_team": "activate_stroke_team",
                "notify_stroke_team": "activate_stroke_team",
                "stroke_alert": "activate_stroke_team",
                # Last known well
                "get_last_known_well": "obtain_last_known_well_time",
                "last_known_well": "obtain_last_known_well_time",
                "time_last_seen_normal": "obtain_last_known_well_time",
                # IV access
                "start_iv": "establish_iv_access",
                "iv_access": "establish_iv_access",
                "obtain_iv_access": "establish_iv_access",
                # Labs
                "order_cbc": "order_cbc_bmp_coag",
                "order_coags": "order_cbc_bmp_coag",
                "order_labs": "order_cbc_bmp_coag",
                # ECG (stroke often needs it too)
                "order_imaging_ecg": "obtain_12_lead_ecg",
                "order_ecg": "obtain_12_lead_ecg",
                # Thrombectomy
                "call_interventional": "consider_thrombectomy",
                "mechanical_thrombectomy": "consider_thrombectomy",
            },
            "aki": {
                # eGFR/Creatinine
                "order_lab_creatinine": "check_baseline_egfr",
                "check_creatinine": "check_baseline_egfr",
                "order_lab_egfr": "check_baseline_egfr",
                "measure_egfr": "check_baseline_egfr",
                "get_creatinine": "check_baseline_egfr",
                "order_renal_function": "check_baseline_egfr",
                # Risk assessment
                "assess_aki_risk": "review_risk_factors",
                "evaluate_risk": "review_risk_factors",
                "aki_risk_assessment": "review_risk_factors",
                "check_risk_factors": "review_risk_factors",
                # Hydration
                "check_hydration": "assess_hydration_status",
                "assess_volume_status": "assess_hydration_status",
                "evaluate_hydration": "assess_hydration_status",
                "volume_status": "assess_hydration_status",
                # IV fluid
                "start_iv_hydration": "initiate_iv_fluid",
                "give_iv_fluids": "initiate_iv_fluid",
                "iv_hydration": "initiate_iv_fluid",
                "fluid_resuscitation": "initiate_iv_fluid",
                # Nephrotoxic meds
                "hold_nsaids": "hold_nephrotoxic_medications",
                "stop_nephrotoxins": "hold_nephrotoxic_medications",
                "discontinue_nephrotoxic": "hold_nephrotoxic_medications",
                # Contrast
                "minimize_contrast": "use_lowest_contrast_dose",
                "low_contrast_dose": "use_lowest_contrast_dose",
                "reduce_contrast": "use_lowest_contrast_dose",
                # Nephrology consult
                "nephrology_consult": "consult_nephrology",
                "renal_consult": "consult_nephrology",
                "call_nephrology": "consult_nephrology",
                "urgent_renal_consult": "urgent_nephrology_consult",
                "emergent_nephrology": "urgent_nephrology_consult",
                "stat_nephrology_consult": "urgent_nephrology_consult",
                # RRT
                "evaluate_dialysis": "assess_rrt_need",
                "dialysis_evaluation": "assess_rrt_need",
                "rrt_assessment": "assess_rrt_need",
                "need_for_dialysis": "assess_rrt_need",
                "start_dialysis": "initiate_emergency_rrt",
                "emergency_hemodialysis": "initiate_emergency_rrt",
                "start_rrt": "initiate_emergency_rrt",
                "emergent_dialysis": "initiate_emergency_rrt",
                # Hyperkalemia temporizing
                "calcium_for_hyperkalemia": "treat_hyperkalemia_temporizing",
                "insulin_glucose_for_k": "treat_hyperkalemia_temporizing",
                "temporizing_measures": "treat_hyperkalemia_temporizing",
                "kayexalate": "treat_hyperkalemia_temporizing",
                # Monitoring
                "check_potassium_q6h": "monitor_potassium_q6h",
                "frequent_potassium": "monitor_potassium_q6h",
                "serial_potassium": "monitor_potassium_q6h",
                "repeat_creatinine": "monitor_creatinine_q6h",
                "serial_creatinine": "monitor_creatinine_q6h",
                # Alternative imaging
                "non_contrast_imaging": "consider_alternative_imaging",
                "ultrasound_instead": "consider_alternative_imaging",
                "mri_without_contrast": "consider_alternative_imaging",
                "avoid_contrast": "consider_alternative_imaging",
                # Nephrotoxin review
                "check_medications": "check_current_medications",
                "medication_review": "check_current_medications",
                "review_medications": "check_current_medications",
            },
            "heart_failure": {
                # BNP
                "order_lab_bnp": "order_bnp",
                "check_bnp": "order_bnp",
                "get_bnp": "order_bnp",
                "order_ntprobnp": "order_bnp_or_ntprobnp",
                "check_ntprobnp": "order_bnp_or_ntprobnp",
                # Echo
                "order_echo": "order_echocardiogram",
                "get_echo": "order_echocardiogram",
                "echocardiogram": "order_echocardiogram",
                # CXR
                "order_cxr": "order_chest_xray",
                "chest_xray": "order_chest_xray",
                "get_cxr": "order_chest_xray",
                # Diuretics
                "give_furosemide": "give_diuretics",
                "give_lasix": "give_diuretics",
                "start_diuretics": "give_diuretics",
                # Volume
                "check_volume": "assess_volume_status",
                "assess_fluid_status": "assess_volume_status",
                # GDMT - ACEi/ARB/ARNI
                "start_ace_inhibitor": "initiate_ace_or_arb_or_arni",
                "start_arb": "initiate_ace_or_arb_or_arni",
                "start_arni": "initiate_ace_or_arb_or_arni",
                "give_sacubitril_valsartan": "initiate_ace_or_arb_or_arni",
                "give_lisinopril": "initiate_ace_or_arb_or_arni",
                "give_enalapril": "initiate_ace_or_arb_or_arni",
                "give_losartan": "initiate_ace_or_arb_or_arni",
                "raas_inhibitor": "initiate_ace_or_arb_or_arni",
                # GDMT - Beta-blocker
                "start_beta_blocker": "initiate_beta_blocker",
                "give_carvedilol": "initiate_beta_blocker",
                "give_metoprolol_succinate": "initiate_beta_blocker",
                "give_bisoprolol": "initiate_beta_blocker",
                # GDMT - MRA
                "start_spironolactone": "initiate_mra",
                "give_eplerenone": "initiate_mra",
                "start_mra": "initiate_mra",
                # GDMT - SGLT2i
                "start_sglt2_inhibitor": "initiate_sglt2i",
                "give_empagliflozin": "initiate_sglt2i",
                "give_dapagliflozin": "initiate_sglt2i",
                # ADHF - IV Diuretics
                "iv_lasix": "iv_diuretics",
                "iv_furosemide": "iv_diuretics",
                "start_iv_diuretics": "iv_diuretics",
                "give_iv_loop_diuretic": "iv_diuretics",
                # ADHF - Fluid restriction
                "restrict_fluids": "fluid_restrict",
                "fluid_restriction": "fluid_restrict",
                # ADHF - Inotropes
                "start_inotropes": "consider_inotropes",
                "give_dobutamine": "consider_inotropes",
                "give_milrinone": "consider_inotropes",
                "start_inotrope": "inotrope_support",
                "inotropic_support": "inotrope_support",
                # Hemodynamic monitoring
                "hemodynamic_monitor": "hemodynamic_monitoring",
                "invasive_monitoring": "hemodynamic_monitoring",
                "pa_catheter": "invasive_hemodynamic_monitoring",
                "swan_ganz": "invasive_hemodynamic_monitoring",
                # Cardiogenic Shock
                "start_vasopressor": "vasopressor_support",
                "start_norepinephrine": "vasopressor_support",
                "give_vasopressor": "vasopressor_support",
                "mcs_evaluation": "mechanical_circulatory_support_evaluation",
                "consider_mcs": "mechanical_circulatory_support_evaluation",
                "consider_impella": "mechanical_circulatory_support_evaluation",
                "consider_iabp": "mechanical_circulatory_support_evaluation",
            },
            # DKA 도메인 - ADA 2024 DKA Management 기반
            "dka": {
                # === Initial Assessment ===
                "check_vitals": "assess_vital_signs",
                "measure_vital_signs": "assess_vital_signs",
                "obtain_vitals": "assess_vital_signs",
                "assess_consciousness": "assess_mental_status",
                "check_mental_status": "assess_mental_status",
                "gcs": "assess_mental_status",
                "glasgow_coma_scale": "assess_mental_status",
                "start_iv": "establish_iv_access",
                "iv_access": "establish_iv_access",
                "obtain_iv_access": "establish_iv_access",
                # === Lab Orders ===
                "check_glucose": "order_lab_glucose",
                "measure_glucose": "order_lab_glucose",
                "finger_stick_glucose": "order_lab_glucose",
                "blood_glucose": "order_lab_glucose",
                "order_bmp": "order_lab_bmp",
                "check_electrolytes": "order_lab_bmp",
                "basic_metabolic_panel": "order_lab_bmp",
                "order_potassium": "order_lab_bmp",
                "check_potassium": "order_lab_bmp",
                "check_ketones": "order_lab_ketones",
                "measure_ketones": "order_lab_ketones",
                "beta_hydroxybutyrate": "order_lab_ketones",
                "serum_ketones": "order_lab_ketones",
                "order_bhb": "order_lab_ketones",
                "check_abg": "order_lab_abg",
                "arterial_blood_gas": "order_lab_abg",
                "blood_gas": "order_lab_abg",
                "order_blood_gas": "order_lab_abg",
                "order_creatinine": "order_lab_creatinine",
                "check_renal_function": "order_lab_creatinine",
                # === IV Fluid ===
                "give_normal_saline": "start_iv_fluid_ns",
                "iv_normal_saline": "start_iv_fluid_ns",
                "start_ns": "start_iv_fluid_ns",
                "ns_bolus": "start_iv_fluid_ns",
                "fluid_resuscitation": "start_iv_fluid_ns",
                "iv_fluid_bolus": "start_iv_fluid_ns",
                "saline_infusion": "start_iv_fluid_ns",
                "give_iv_fluids": "start_iv_fluid_ns",
                "cautious_fluids": "start_iv_fluid_ns_cautious",
                "cautious_iv_fluids": "start_iv_fluid_ns_cautious",
                # === Insulin (CRITICAL - hypokalemia trap) ===
                "start_insulin": "start_insulin_infusion",
                "insulin_drip": "start_insulin_infusion",
                "insulin_infusion": "start_insulin_infusion",
                "regular_insulin_iv": "start_insulin_infusion",
                "give_insulin": "start_insulin_infusion",
                "iv_insulin": "start_insulin_infusion",
                "insulin_0.1_u_kg_h": "start_insulin_infusion",
                # === Potassium (CRITICAL - hypokalemia trap) ===
                "give_potassium": "give_potassium_iv",
                "potassium_replacement": "give_potassium_iv",
                "replace_potassium": "give_potassium_iv",
                "kcl_infusion": "give_potassium_iv",
                "potassium_chloride": "give_potassium_iv",
                "potassium_20_meq": "give_potassium_iv",
                "add_potassium": "add_potassium_to_iv",
                "potassium_in_iv_fluid": "add_potassium_to_iv",
                "maintenance_potassium": "add_potassium_to_iv",
                # === Hold Insulin (CRITICAL - K+ < 3.3 trap) ===
                "hold_insulin": "hold_insulin_until_k_above_3.3",
                "withhold_insulin": "hold_insulin_until_k_above_3.3",
                "do_not_give_insulin": "hold_insulin_until_k_above_3.3",
                "delay_insulin": "hold_insulin_until_k_above_3.3",
                "insulin_contraindicated": "hold_insulin_until_k_above_3.3",
                # === SGLT2 Inhibitor (euglycemic DKA trap) ===
                "stop_sglt2": "stop_sglt2_inhibitor",
                "discontinue_sglt2": "stop_sglt2_inhibitor",
                "hold_sglt2": "stop_sglt2_inhibitor",
                "stop_empagliflozin": "stop_sglt2_inhibitor",
                "stop_dapagliflozin": "stop_sglt2_inhibitor",
                "stop_canagliflozin": "stop_sglt2_inhibitor",
                # === Monitoring ===
                "hourly_glucose": "monitor_glucose_hourly",
                "glucose_monitoring": "monitor_glucose_hourly",
                "glucose_q1h": "monitor_glucose_hourly",
                "frequent_glucose_checks": "monitor_glucose_hourly",
                "potassium_monitoring": "monitor_potassium_q2h",
                "check_potassium_q2h": "monitor_potassium_q2h",
                "frequent_potassium": "monitor_potassium_q2h",
                # === DKA Resolution ===
                "check_anion_gap": "assess_anion_gap_closure",
                "anion_gap_assessment": "assess_anion_gap_closure",
                "dka_resolution_check": "assess_anion_gap_closure",
                "assess_resolution": "assess_anion_gap_closure",
                "give_bicarbonate": "consider_bicarbonate",
                "sodium_bicarbonate": "consider_bicarbonate",
                "bicarb": "consider_bicarbonate",
                # === Transition ===
                "subq_insulin": "start_subcutaneous_insulin",
                "subcutaneous_insulin": "start_subcutaneous_insulin",
                "transition_to_subq": "start_subcutaneous_insulin",
                "insulin_glargine": "start_subcutaneous_insulin",
                "lantus": "start_subcutaneous_insulin",
                "overlap_insulin": "overlap_iv_insulin_2h",
                "insulin_overlap": "overlap_iv_insulin_2h",
                "maintain_iv_insulin_2h": "overlap_iv_insulin_2h",
                # === Hyperkalemia (CKD trap) ===
                "treat_high_potassium": "treat_hyperkalemia",
                "calcium_gluconate": "treat_hyperkalemia",
                "hyperkalemia_treatment": "treat_hyperkalemia",
                # === Disposition ===
                "icu_admission": "admit_to_icu",
                "transfer_to_icu": "admit_to_icu",
                "cardiac_monitor": "continuous_cardiac_monitoring",
                "telemetry": "continuous_cardiac_monitoring",
                # === Dextrose (euglycemic DKA) ===
                "start_d5": "start_dextrose_containing_iv",
                "dextrose_iv": "start_dextrose_containing_iv",
                "d5_half_ns": "start_dextrose_containing_iv",
                "add_dextrose": "start_dextrose_containing_iv",
            },
            # Sepsis 도메인 - Oracle Decision Table과 LLM 출력 모두 지원
            "sepsis": {
                # Lactate 관련
                "measure_lactate": "order_lab_lactate",
                "get_lactate": "order_lab_lactate",
                "check_lactate": "order_lab_lactate",
                "serum_lactate": "order_lab_lactate",
                "order_lactate": "order_lab_lactate",
                # Blood culture 관련 (Oracle: blood_culture_before_antibiotics)
                "blood_culture": "order_lab_blood_culture",
                "get_blood_cultures": "order_lab_blood_culture",
                "blood_culture_before_antibiotics": "order_lab_blood_culture",
                "draw_blood_culture": "order_lab_blood_culture",
                "obtain_blood_cultures": "order_lab_blood_culture",
                "order_blood_culture": "order_lab_blood_culture",
                # Antibiotics 관련 (중요: give_antibiotics 매핑 추가)
                "empiric_antibiotics": "give_broad_spectrum_antibiotics",
                "start_antibiotics": "give_broad_spectrum_antibiotics",
                "give_antibiotics": "give_broad_spectrum_antibiotics",
                "administer_antibiotics": "give_broad_spectrum_antibiotics",
                "broad_spectrum_antibiotics": "give_broad_spectrum_antibiotics",
                "iv_antibiotics": "give_broad_spectrum_antibiotics",
                # Fluid 관련
                "fluid_bolus": "give_crystalloid_30ml_kg",
                "iv_fluids": "give_crystalloid_30ml_kg",
                "crystalloid_30ml_kg": "give_crystalloid_30ml_kg",
                "give_iv_fluids": "give_crystalloid_30ml_kg",
                "fluid_resuscitation": "give_crystalloid_30ml_kg",
                "bolus_fluids": "give_crystalloid_30ml_kg",
                # Vasopressor 관련
                "start_norepinephrine": "start_vasopressor_norepinephrine",
                "start_norepi": "start_vasopressor_norepinephrine",
                "start_pressors": "start_vasopressor_norepinephrine",
                "start_vasopressors": "start_vasopressor_norepinephrine",
                "norepinephrine": "start_vasopressor_norepinephrine",
                "give_norepinephrine": "start_vasopressor_norepinephrine",
                "start_vasopressor": "start_vasopressor_norepinephrine",
            }
        }

    def _build_synonym_map(self) -> Dict[str, str]:
        """동의어 매핑 구축"""
        return {
            # Actions
            "give": "administer",
            "order": "request",
            "start": "initiate",
            "stop": "discontinue",
            "check": "measure",
            "get": "obtain",
            "send": "order",

            # Labs
            "lactic_acid": "lactate",
            "serum_lactate": "lactate",
            "blood_lactate": "lactate",
            "cardiac_troponin": "troponin",
            "trop": "troponin",
            "serum_creatinine": "creatinine",

            # Medications
            "iv_fluids": "crystalloid",
            "saline": "crystalloid",
            "pressors": "vasopressor",
            "vasopressors": "vasopressor",
            "broad_spectrum_abx": "broad_spectrum_antibiotics",
            "empiric_antibiotics": "broad_spectrum_antibiotics",

            # Imaging
            "12_lead_ecg": "ecg_12_lead",
            "twelve_lead_ecg": "ecg_12_lead",
            "chest_x_ray": "chest_xray",
            "head_ct": "ct_head",
            "ct_brain": "ct_head",

            # Procedures
            "cath_lab": "catheterization_lab",
            "cardiac_cath": "percutaneous_coronary_intervention",
        }

    def _expand_abbreviations(self, text: str) -> str:
        """약어 확장"""
        words = text.split("_")
        expanded_words = []
        for word in words:
            if word in self._abbreviation_map:
                expanded_words.append(self._abbreviation_map[word])
            else:
                expanded_words.append(word)
        return "_".join(expanded_words)

    def _find_synonym_match(
        self,
        action: str,
        valid_actions: List[str]
    ) -> Optional[str]:
        """동의어 매칭"""
        # Apply synonym substitutions
        words = action.split("_")
        substituted_words = []
        for word in words:
            if word in self._synonym_map:
                substituted_words.append(self._synonym_map[word])
            else:
                substituted_words.append(word)
        substituted = "_".join(substituted_words)

        # Check if substituted matches
        for valid in valid_actions:
            valid_lower = valid.lower()
            if substituted == valid_lower:
                return valid
            if substituted in valid_lower or valid_lower in substituted:
                return valid

        return None

    def _fuzzy_match(
        self,
        action: str,
        valid_actions: List[str]
    ) -> Tuple[str, float]:
        """퍼지 매칭"""
        best_match = None
        best_score = 0.0

        for valid in valid_actions:
            valid_lower = valid.lower()

            # Sequence matcher score
            score = SequenceMatcher(None, action, valid_lower).ratio()

            # Boost score for substring matches
            if action in valid_lower or valid_lower in action:
                score = max(score, 0.8)

            # Boost for common prefix
            common_prefix_len = 0
            for a, b in zip(action, valid_lower):
                if a == b:
                    common_prefix_len += 1
                else:
                    break
            if common_prefix_len > 5:
                score += 0.1

            if score > best_score:
                best_score = score
                best_match = valid

        return best_match or action, best_score

    def _semantic_match_with_llm(
        self,
        action: str,
        valid_actions: List[str],
        context: Optional[Dict[str, Any]]
    ) -> Optional[str]:
        """LLM을 사용한 시맨틱 매칭 (보수적 접근)"""
        if not self.llm_provider:
            return None

        # Skip LLM matching for actions that are clearly administrative/non-clinical
        skip_patterns = [
            "transfer", "document", "review", "discuss", "consider",
            "monitor", "reassess", "follow_up", "discharge", "admit"
        ]
        action_lower = action.lower()
        if any(pat in action_lower for pat in skip_patterns):
            logger.debug(f"Skipping LLM match for administrative action: {action}")
            return None

        # Limit valid actions for prompt
        valid_str = "\n".join([f"- {a}" for a in valid_actions[:30]])

        context_str = ""
        if context:
            diagnosis = context.get("working_diagnosis", "")
            if diagnosis:
                context_str = f"\nPatient diagnosis: {diagnosis}"

        prompt = f"""Match this clinical action to the EXACT EQUIVALENT action from the list.

IMPORTANT: Only match if the actions are SEMANTICALLY IDENTICAL (same clinical intent).
Do NOT match:
- Administrative actions (transfer, discharge) to treatment actions
- Different types of interventions (e.g., imaging vs medication)
- Monitoring/documentation to ordering/giving

Action to match: "{action}"
{context_str}

Valid actions:
{valid_str}

Return JSON with matched_action ONLY if there's a semantically identical match:
{{"matched_action": "exact_matching_action_id" or null, "confidence": 0.0-1.0, "reason": "why this matches or null"}}"""

        messages = [
            LLMMessage(role="system", content="You are a strict clinical action matcher. Only match semantically identical actions."),
            LLMMessage(role="user", content=prompt)
        ]

        schema = {
            "type": "object",
            "properties": {
                "matched_action": {"type": "string"},
                "confidence": {"type": "number"},
                "reason": {"type": "string"}
            }
        }

        try:
            result = self.llm_provider.complete_json(messages, schema)
            matched = result.get("matched_action")
            confidence = result.get("confidence", 0)
            reason = result.get("reason", "")

            # Much stricter threshold: 0.85 instead of 0.5
            if matched and confidence > 0.85 and matched in valid_actions:
                logger.info(f"LLM matched '{action}' to '{matched}' (conf={confidence}, reason={reason})")
                return matched
            elif matched and confidence > 0.5:
                logger.debug(f"LLM match rejected (low confidence): '{action}' to '{matched}' (conf={confidence})")

        except Exception as e:
            logger.warning(f"LLM semantic matching failed: {e}")

        return None

    def _get_top_alternatives(
        self,
        action: str,
        valid_actions: List[str],
        n: int = 3
    ) -> List[str]:
        """상위 N개 대안 반환"""
        scores = []
        for valid in valid_actions:
            score = SequenceMatcher(None, action, valid.lower()).ratio()
            scores.append((valid, score))

        scores.sort(key=lambda x: x[1], reverse=True)
        return [s[0] for s in scores[:n]]

    def _get_default_actions(self) -> List[str]:
        """기본 액션 목록 (LLM 생성 이름 + CPG 표준 이름 모두 포함)"""
        return [
            # ===== Sepsis Domain =====
            "order_lab_lactate", "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics", "give_crystalloid_30ml_kg",
            "start_vasopressor_norepinephrine", "start_vasopressor_if_hypotensive",
            "assess_infection_source", "assess_organ_dysfunction",

            # ===== Chest Pain / STEMI Domain =====
            # ECG (both LLM and CPG names)
            "order_imaging_ecg", "obtain_12_lead_ecg", "obtain_right_sided_ecg_v4r",
            # Troponin
            "order_lab_troponin", "order_troponin",
            # Medications
            "give_aspirin_loading", "give_aspirin",
            "give_p2y12_inhibitor", "give_anticoagulation",
            "start_iv_fluid_bolus",
            # Assessments
            "assess_vital_signs", "obtain_chest_pain_history",
            # Cath lab
            "activate_cath_lab",

            # ===== Stroke Domain =====
            # CT Head
            "order_imaging_ct_head", "order_stat_ct_head",
            # NIHSS
            "perform_nihss", "assess_nihss",
            # Glucose
            "order_lab_glucose", "check_glucose",
            # tPA/Alteplase
            "give_alteplase", "give_alteplase_0.9mg_kg",
            # Stroke team & process
            "activate_stroke_team", "establish_iv_access",
            "obtain_last_known_well_time", "order_cbc_bmp_coag",
            "review_inclusion_criteria", "review_exclusion_criteria",
            "obtain_informed_consent", "consider_thrombectomy",
            "order_ct_angiography",

            # ===== AKI Domain =====
            "order_lab_creatinine", "check_baseline_egfr",
            "assess_hydration_status", "review_risk_factors",
            "initiate_iv_fluid", "hold_nephrotoxic_medications",
            "use_lowest_contrast_dose", "check_current_medications",
            "consult_nephrology", "urgent_nephrology_consult",
            "assess_rrt_need", "initiate_emergency_rrt",
            "treat_hyperkalemia_temporizing",
            "monitor_potassium_q6h", "monitor_creatinine_q6h",
            "consider_alternative_imaging",

            # ===== Heart Failure Domain =====
            "order_lab_bnp", "order_bnp", "order_bnp_or_ntprobnp",
            "order_imaging_echocardiogram", "order_echocardiogram",
            "order_imaging_chest_xray", "order_chest_xray",
            "give_diuretics", "assess_volume_status",
            "initiate_ace_or_arb_or_arni", "initiate_beta_blocker",
            "initiate_mra", "initiate_sglt2i",
            "iv_diuretics", "fluid_restrict",
            "consider_inotropes", "hemodynamic_monitoring",
            "vasopressor_support", "inotrope_support",
            "mechanical_circulatory_support_evaluation",
            "assess_hemodynamic_profile",

            # ===== DKA Domain =====
            "assess_vital_signs", "assess_mental_status", "establish_iv_access",
            "order_lab_glucose", "order_lab_bmp", "order_lab_ketones",
            "order_lab_abg", "order_lab_creatinine",
            "start_iv_fluid_ns", "start_iv_fluid_ns_cautious",
            "start_insulin_infusion", "give_potassium_iv",
            "hold_insulin_until_k_above_3.3", "stop_sglt2_inhibitor",
            "monitor_glucose_hourly", "monitor_potassium_q2h",
            "assess_anion_gap_closure", "consider_bicarbonate",
            "start_subcutaneous_insulin", "overlap_iv_insulin_2h",
            "treat_hyperkalemia", "admit_to_icu",
            "continuous_cardiac_monitoring", "start_dextrose_containing_iv",

            # ===== General =====
            "order_lab_cbc", "order_lab_bmp", "order_lab_coagulation",
            "assess_neurological_status",
            "consult_cardiology", "consult_neurology", "consult_icu",
            "arrange_pci", "arrange_thrombectomy",
        ]
