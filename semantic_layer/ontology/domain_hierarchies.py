"""Pre-built clinical ontology hierarchies for CGA-Bench domains.

Covers 6 clinical domains with SNOMED-CT-inspired IS-A hierarchies:
- Sepsis (SSC 2021 Hour-1 Bundle)
- Chest Pain / ACS (AHA 2021)
- Stroke (AHA 2019)
- AKI (KDIGO)
- Heart Failure (AHA 2022)
- DKA (ADA)

Each domain provides:
- L1 (NORMALIZED): CPG-standard action IDs
- L2 (CATEGORY): Semantic categories (drug classes, test types)
- L3 (GOAL): Clinical goals
- L4 (PHASE): Care pathway phases
- Synonym sets for robust matching
- IS-A, PRECEDES, CONTRAINDICATES relations

References:
- SNOMED CT concept model (Clinical finding, Procedure, Substance)
- RxNorm drug hierarchy (Ingredient → Clinical Drug)
- LOINC part hierarchy (Component → Lab Test)
"""
from __future__ import annotations

from typing import Dict, List, Tuple

from .concept import (
    AbstractionLevel,
    ClinicalConcept,
    ConceptRelation,
)
from .clinical_ontology import (
    ClinicalOntology,
    OntologyConfig,
    OntologyMatcher,
)


def _c(
    concept_id: str,
    display: str,
    level: AbstractionLevel,
    domain: str,
    synonyms: tuple = (),
    system: str = "CGA-Bench",
    code: str = None,
) -> ClinicalConcept:
    """Shortcut to create a ClinicalConcept."""
    return ClinicalConcept(
        concept_id=concept_id,
        display=display,
        level=level,
        system=system,
        code=code,
        synonyms=frozenset(synonyms),
        domain=domain,
    )


# ======================================================================
# SEPSIS Domain (SSC 2021 Hour-1 Bundle)
# ======================================================================

def build_sepsis_ontology() -> ClinicalOntology:
    """Build sepsis domain ontology with SSC Hour-1 Bundle hierarchy."""
    onto = ClinicalOntology()

    # --- L4: Phases ---
    phase_hour1 = _c("SEPSIS_HOUR1_BUNDLE", "Sepsis Hour-1 Bundle", AbstractionLevel.PHASE, "sepsis")
    phase_resus = _c("SEPSIS_RESUSCITATION", "Sepsis Resuscitation", AbstractionLevel.PHASE, "sepsis")
    phase_monitor = _c("SEPSIS_MONITORING", "Sepsis Monitoring", AbstractionLevel.PHASE, "sepsis")

    # --- L3: Goals ---
    goal_infection = _c("INFECTION_CONTROL", "Infection Control", AbstractionLevel.GOAL, "sepsis")
    goal_perfusion = _c("PERFUSION_SUPPORT", "Perfusion Support", AbstractionLevel.GOAL, "sepsis")
    goal_assessment = _c("SEPSIS_ASSESSMENT", "Sepsis Assessment", AbstractionLevel.GOAL, "sepsis")
    goal_hemodynamic = _c("HEMODYNAMIC_RESUSCITATION", "Hemodynamic Resuscitation", AbstractionLevel.GOAL, "sepsis")

    # --- L2: Categories ---
    cat_culture = _c("MICROBIOLOGY_WORKUP", "Microbiology Workup", AbstractionLevel.CATEGORY, "sepsis")
    cat_antibiotic = _c("ANTIBIOTIC_THERAPY", "Antibiotic Therapy", AbstractionLevel.CATEGORY, "sepsis")
    cat_fluid = _c("FLUID_RESUSCITATION", "Fluid Resuscitation", AbstractionLevel.CATEGORY, "sepsis")
    cat_vasopressor = _c("VASOPRESSOR_SUPPORT", "Vasopressor Support", AbstractionLevel.CATEGORY, "sepsis",
                         synonyms=("vasopressors", "pressor_support", "hemodynamic_support"))
    cat_lactate = _c("LACTATE_MONITORING", "Lactate Monitoring", AbstractionLevel.CATEGORY, "sepsis")
    cat_vitals = _c("VITAL_SIGNS_ASSESSMENT", "Vital Signs Assessment", AbstractionLevel.CATEGORY, "sepsis")

    # --- L1: Normalized Actions ---
    act_blood_culture = _c("ORDER_BLOOD_CULTURE", "Order Blood Culture",
                           AbstractionLevel.NORMALIZED, "sepsis",
                           synonyms=("blood_culture", "order_lab_blood_culture",
                                     "draw_blood_cultures", "obtain_blood_cultures",
                                     "blood_culture_before_antibiotics"))
    act_broad_abx = _c("GIVE_BROAD_SPECTRUM_ANTIBIOTICS", "Give Broad-Spectrum Antibiotics",
                        AbstractionLevel.NORMALIZED, "sepsis",
                        synonyms=("broad_spectrum_antibiotics", "empiric_antibiotics",
                                  "give_antibiotics", "start_antibiotics",
                                  "administer_antibiotics", "give_abx"))
    act_pip_tazo = _c("GIVE_PIPERACILLIN_TAZOBACTAM", "Give Piperacillin-Tazobactam",
                      AbstractionLevel.NORMALIZED, "sepsis",
                      synonyms=("pip_tazo", "zosyn", "piperacillin_tazobactam"),
                      system="RxNorm", code="139462")
    act_meropenem = _c("GIVE_MEROPENEM", "Give Meropenem",
                       AbstractionLevel.NORMALIZED, "sepsis",
                       synonyms=("meropenem",), system="RxNorm", code="29561")
    act_vancomycin = _c("GIVE_VANCOMYCIN", "Give Vancomycin",
                        AbstractionLevel.NORMALIZED, "sepsis",
                        synonyms=("vancomycin",), system="RxNorm", code="11124")
    act_crystalloid = _c("GIVE_CRYSTALLOID", "Give Crystalloid 30mL/kg",
                         AbstractionLevel.NORMALIZED, "sepsis",
                         synonyms=("crystalloid_30ml_kg", "give_crystalloid_30ml_kg",
                                   "give_ns_bolus", "give_lr_bolus", "fluid_bolus",
                                   "normal_saline_bolus", "iv_fluid_resuscitation",
                                   "give_crystalloid_fluid", "additional_fluid_bolus"))
    act_norepinephrine = _c("START_VASOPRESSOR_NOREPINEPHRINE", "Start Norepinephrine",
                            AbstractionLevel.NORMALIZED, "sepsis",
                            synonyms=("norepinephrine", "levophed", "start_norepinephrine",
                                      "start_vasopressor", "norepi",
                                      "start_vasopressor_if_hypotensive",
                                      "start_vasopressor_norepinephrine",
                                      "continue_vasopressor"),
                            system="RxNorm", code="7512")
    act_vasopressin = _c("START_VASOPRESSOR_VASOPRESSIN", "Start Vasopressin",
                         AbstractionLevel.NORMALIZED, "sepsis",
                         synonyms=("vasopressin", "adh"),
                         system="RxNorm", code="11149")
    act_order_lactate = _c("ORDER_LACTATE", "Order Serum Lactate",
                           AbstractionLevel.NORMALIZED, "sepsis",
                           synonyms=("order_lab_lactate", "lactate", "lactic_acid",
                                     "serum_lactate", "measure_lactate", "check_lactate"))
    # Additional common lab orders
    act_order_cbc = _c("ORDER_CBC", "Order Complete Blood Count",
                       AbstractionLevel.NORMALIZED, "sepsis",
                       synonyms=("cbc", "order_lab_cbc", "complete_blood_count",
                                 "order_lab_complete_blood_count", "blood_count",
                                 "hemoglobin", "wbc", "platelets"))
    act_order_bmp = _c("ORDER_BMP", "Order Basic Metabolic Panel",
                       AbstractionLevel.NORMALIZED, "sepsis",
                       synonyms=("bmp", "order_lab_bmp", "basic_metabolic_panel",
                                 "order_lab_metabolic_panel", "chem7", "electrolytes"))
    act_order_coag = _c("ORDER_COAGULATION", "Order Coagulation Studies",
                        AbstractionLevel.NORMALIZED, "sepsis",
                        synonyms=("coagulation", "order_lab_coagulation", "pt_inr",
                                  "order_lab_coagulation_studies", "ptt", "coag_panel",
                                  "inr", "order_lab_coag"))
    act_order_abg = _c("ORDER_ABG", "Order Arterial Blood Gas",
                       AbstractionLevel.NORMALIZED, "sepsis",
                       synonyms=("abg", "order_lab_abg", "arterial_blood_gas",
                                 "order_lab_arterial_blood_gas", "blood_gas"))
    act_order_procalcitonin = _c("ORDER_PROCALCITONIN", "Order Procalcitonin",
                                  AbstractionLevel.NORMALIZED, "sepsis",
                                  synonyms=("procalcitonin", "order_lab_procalcitonin",
                                            "pct", "procal"))
    act_repeat_lactate = _c("REPEAT_LACTATE", "Repeat Lactate (if >2)",
                            AbstractionLevel.NORMALIZED, "sepsis",
                            synonyms=("recheck_lactate", "lactate_clearance",
                                      "follow_up_lactate", "serial_lactate",
                                      "remeasure_lactate_if_elevated",
                                      "serial_lactate_monitoring"))
    act_assess_map = _c("ASSESS_MAP", "Assess Mean Arterial Pressure",
                        AbstractionLevel.NORMALIZED, "sepsis",
                        synonyms=("check_map", "map_assessment", "mean_arterial_pressure",
                                  "assess_blood_pressure"))
    act_assess_vitals = _c("ASSESS_VITALS", "Assess Vital Signs",
                           AbstractionLevel.NORMALIZED, "sepsis",
                           synonyms=("check_vitals", "vital_signs", "monitor_vitals",
                                     "assess_vital_signs", "assess_vitals"))
    act_reassess = _c("REASSESS_RESPONSE", "Reassess Clinical Response",
                      AbstractionLevel.NORMALIZED, "sepsis",
                      synonyms=("reassess", "clinical_reassessment", "reassess_perfusion",
                                "reassess_response"))
    # Assessment actions
    act_assess_infection = _c("ASSESS_INFECTION_SOURCE", "Assess Infection Source",
                              AbstractionLevel.NORMALIZED, "sepsis",
                              synonyms=("assess_infection_source", "infection_source",
                                        "source_control", "identify_infection"))
    act_assess_organ = _c("ASSESS_ORGAN_DYSFUNCTION", "Assess Organ Dysfunction",
                          AbstractionLevel.NORMALIZED, "sepsis",
                          synonyms=("assess_organ_dysfunction", "organ_dysfunction",
                                    "sofa_score", "qsofa", "assess_sofa"))
    # Admission/Disposition actions
    act_admit_icu = _c("ADMIT_TO_ICU", "Admit to ICU",
                       AbstractionLevel.NORMALIZED, "sepsis",
                       synonyms=("admit_to_icu", "icu_admission", "transfer_to_icu",
                                 "escalate_to_icu", "icu_transfer"))
    act_admit_ward = _c("ADMIT_TO_WARD", "Admit to Ward",
                        AbstractionLevel.NORMALIZED, "sepsis",
                        synonyms=("admit_to_ward", "ward_admission", "floor_admission",
                                  "admit_to_hospital", "hospital_admission"))
    # Monitoring/Procedure actions
    act_arterial_line = _c("PLACE_ARTERIAL_LINE", "Place Arterial Line",
                           AbstractionLevel.NORMALIZED, "sepsis",
                           synonyms=("arterial_line", "art_line", "arterial_line_monitoring",
                                     "place_arterial_line", "a_line"))
    act_central_line = _c("PLACE_CENTRAL_LINE", "Place Central Line",
                          AbstractionLevel.NORMALIZED, "sepsis",
                          synonyms=("central_line", "cvc", "central_line_access",
                                    "place_central_line", "central_venous_catheter"))
    # History/Exam actions (cross-domain)
    act_take_history = _c("TAKE_HISTORY", "Take Patient History",
                          AbstractionLevel.NORMALIZED, "sepsis",
                          synonyms=("take_history", "history", "obtain_history",
                                    "medical_history", "patient_history",
                                    "assess_chief_complaint", "chief_complaint"))
    act_physical_exam = _c("PHYSICAL_EXAM", "Perform Physical Examination",
                           AbstractionLevel.NORMALIZED, "sepsis",
                           synonyms=("physical_exam", "physical_examination", "exam",
                                     "physical_exam_cardiovascular", "physical_exam_respiratory",
                                     "physical_exam_abdominal", "physical_exam_neurological"))
    # Imaging actions
    act_chest_xray = _c("ORDER_CHEST_XRAY", "Order Chest X-Ray",
                        AbstractionLevel.NORMALIZED, "sepsis",
                        synonyms=("chest_xray", "cxr", "order_imaging_chest_xray",
                                  "chest_x_ray", "order_imaging_cxr"))

    # Additional categories for new concepts
    cat_lab_general = _c("GENERAL_LAB_WORKUP", "General Lab Workup", AbstractionLevel.CATEGORY, "sepsis")
    cat_disposition = _c("DISPOSITION", "Disposition", AbstractionLevel.CATEGORY, "sepsis")
    cat_procedures = _c("PROCEDURES", "Procedures", AbstractionLevel.CATEGORY, "sepsis")
    cat_history_exam = _c("HISTORY_EXAM", "History and Physical", AbstractionLevel.CATEGORY, "sepsis")
    cat_imaging = _c("IMAGING", "Imaging Studies", AbstractionLevel.CATEGORY, "sepsis")

    # Add all concepts
    all_concepts = [
        phase_hour1, phase_resus, phase_monitor,
        goal_infection, goal_perfusion, goal_assessment, goal_hemodynamic,
        cat_culture, cat_antibiotic, cat_fluid, cat_vasopressor, cat_lactate, cat_vitals,
        cat_lab_general, cat_disposition, cat_procedures, cat_history_exam, cat_imaging,
        act_blood_culture, act_broad_abx, act_pip_tazo, act_meropenem, act_vancomycin,
        act_crystalloid, act_norepinephrine, act_vasopressin,
        act_order_lactate, act_repeat_lactate,
        act_order_cbc, act_order_bmp, act_order_coag, act_order_abg, act_order_procalcitonin,
        act_assess_map, act_assess_vitals, act_reassess,
        act_assess_infection, act_assess_organ,
        act_admit_icu, act_admit_ward,
        act_arterial_line, act_central_line,
        act_take_history, act_physical_exam,
        act_chest_xray,
    ]
    for c in all_concepts:
        onto.add_concept(c)

    # --- IS-A Relations ---
    # L3 → L4
    onto.add_relation(goal_infection, ConceptRelation.IS_A, phase_hour1)
    onto.add_relation(goal_assessment, ConceptRelation.IS_A, phase_hour1)
    onto.add_relation(goal_perfusion, ConceptRelation.IS_A, phase_resus)
    onto.add_relation(goal_hemodynamic, ConceptRelation.IS_A, phase_resus)

    # L2 → L3
    onto.add_relation(cat_culture, ConceptRelation.IS_A, goal_infection)
    onto.add_relation(cat_antibiotic, ConceptRelation.IS_A, goal_infection)
    onto.add_relation(cat_fluid, ConceptRelation.IS_A, goal_perfusion)
    onto.add_relation(cat_vasopressor, ConceptRelation.IS_A, goal_hemodynamic)
    onto.add_relation(cat_lactate, ConceptRelation.IS_A, goal_assessment)
    onto.add_relation(cat_vitals, ConceptRelation.IS_A, goal_assessment)

    # L1 → L2
    onto.add_relation(act_blood_culture, ConceptRelation.IS_A, cat_culture)
    onto.add_relation(act_broad_abx, ConceptRelation.IS_A, cat_antibiotic)
    onto.add_relation(act_pip_tazo, ConceptRelation.IS_A, cat_antibiotic)
    onto.add_relation(act_meropenem, ConceptRelation.IS_A, cat_antibiotic)
    onto.add_relation(act_vancomycin, ConceptRelation.IS_A, cat_antibiotic)
    onto.add_relation(act_crystalloid, ConceptRelation.IS_A, cat_fluid)
    onto.add_relation(act_norepinephrine, ConceptRelation.IS_A, cat_vasopressor)
    onto.add_relation(act_vasopressin, ConceptRelation.IS_A, cat_vasopressor)
    onto.add_relation(act_order_lactate, ConceptRelation.IS_A, cat_lactate)
    onto.add_relation(act_repeat_lactate, ConceptRelation.IS_A, cat_lactate)
    onto.add_relation(act_assess_map, ConceptRelation.IS_A, cat_vitals)
    onto.add_relation(act_assess_vitals, ConceptRelation.IS_A, cat_vitals)
    onto.add_relation(act_reassess, ConceptRelation.IS_A, cat_vitals)

    # New categories → L3
    onto.add_relation(cat_lab_general, ConceptRelation.IS_A, goal_assessment)
    onto.add_relation(cat_disposition, ConceptRelation.IS_A, phase_monitor)
    onto.add_relation(cat_procedures, ConceptRelation.IS_A, goal_hemodynamic)
    onto.add_relation(cat_history_exam, ConceptRelation.IS_A, goal_assessment)
    onto.add_relation(cat_imaging, ConceptRelation.IS_A, goal_assessment)

    # New lab concepts → L2
    onto.add_relation(act_order_cbc, ConceptRelation.IS_A, cat_lab_general)
    onto.add_relation(act_order_bmp, ConceptRelation.IS_A, cat_lab_general)
    onto.add_relation(act_order_coag, ConceptRelation.IS_A, cat_lab_general)
    onto.add_relation(act_order_abg, ConceptRelation.IS_A, cat_lab_general)
    onto.add_relation(act_order_procalcitonin, ConceptRelation.IS_A, cat_lab_general)

    # Assessment concepts → L2
    onto.add_relation(act_assess_infection, ConceptRelation.IS_A, cat_vitals)
    onto.add_relation(act_assess_organ, ConceptRelation.IS_A, cat_vitals)

    # Admission concepts → disposition
    onto.add_relation(act_admit_icu, ConceptRelation.IS_A, cat_disposition)
    onto.add_relation(act_admit_ward, ConceptRelation.IS_A, cat_disposition)

    # Procedure concepts
    onto.add_relation(act_arterial_line, ConceptRelation.IS_A, cat_procedures)
    onto.add_relation(act_central_line, ConceptRelation.IS_A, cat_procedures)

    # History/Exam concepts
    onto.add_relation(act_take_history, ConceptRelation.IS_A, cat_history_exam)
    onto.add_relation(act_physical_exam, ConceptRelation.IS_A, cat_history_exam)

    # Imaging concepts
    onto.add_relation(act_chest_xray, ConceptRelation.IS_A, cat_imaging)

    # Specific antibiotics IS-A broad-spectrum
    onto.add_relation(act_pip_tazo, ConceptRelation.IS_A, act_broad_abx)
    onto.add_relation(act_meropenem, ConceptRelation.IS_A, act_broad_abx)

    # --- PRECEDES Relations ---
    onto.add_relation(act_blood_culture, ConceptRelation.PRECEDES, act_broad_abx)
    onto.add_relation(act_crystalloid, ConceptRelation.PRECEDES, act_norepinephrine)
    onto.add_relation(act_assess_map, ConceptRelation.PRECEDES, act_norepinephrine)

    return onto


# ======================================================================
# CHEST PAIN / ACS Domain (AHA 2021)
# ======================================================================

def build_chest_pain_ontology() -> ClinicalOntology:
    """Build chest pain/ACS domain ontology with AHA 2021 hierarchy."""
    onto = ClinicalOntology()

    # --- L4: Phases ---
    phase_initial = _c("ACS_INITIAL_ASSESSMENT", "ACS Initial Assessment", AbstractionLevel.PHASE, "chest_pain")
    phase_stemi = _c("STEMI_INTERVENTION", "STEMI Intervention", AbstractionLevel.PHASE, "chest_pain")
    phase_nstemi = _c("NSTEMI_MANAGEMENT", "NSTEMI Management", AbstractionLevel.PHASE, "chest_pain")

    # --- L3: Goals ---
    goal_diagnosis = _c("CARDIAC_DIAGNOSIS", "Cardiac Diagnosis", AbstractionLevel.GOAL, "chest_pain")
    goal_antiplatelet = _c("ANTIPLATELET_THERAPY", "Antiplatelet Therapy", AbstractionLevel.GOAL, "chest_pain")
    goal_reperfusion = _c("REPERFUSION_THERAPY", "Reperfusion Therapy", AbstractionLevel.GOAL, "chest_pain")
    goal_pain = _c("PAIN_MANAGEMENT", "Pain Management", AbstractionLevel.GOAL, "chest_pain")
    goal_anticoag = _c("ANTICOAGULATION", "Anticoagulation", AbstractionLevel.GOAL, "chest_pain")

    # --- L2: Categories ---
    cat_ecg = _c("ECG_ASSESSMENT", "ECG Assessment", AbstractionLevel.CATEGORY, "chest_pain")
    cat_biomarker = _c("CARDIAC_BIOMARKERS", "Cardiac Biomarkers", AbstractionLevel.CATEGORY, "chest_pain")
    cat_antiplatelet = _c("ANTIPLATELET_AGENTS", "Antiplatelet Agents", AbstractionLevel.CATEGORY, "chest_pain")
    cat_nitrate = _c("NITRATE_THERAPY", "Nitrate Therapy", AbstractionLevel.CATEGORY, "chest_pain",
                     synonyms=("nitrates", "nitroglycerin_therapy"))
    cat_anticoag_agents = _c("ANTICOAGULANT_AGENTS", "Anticoagulant Agents", AbstractionLevel.CATEGORY, "chest_pain")
    cat_reperfusion = _c("REPERFUSION_PROCEDURES", "Reperfusion Procedures", AbstractionLevel.CATEGORY, "chest_pain")
    cat_imaging = _c("CARDIAC_IMAGING", "Cardiac Imaging", AbstractionLevel.CATEGORY, "chest_pain")
    cat_vitals = _c("VITAL_ASSESSMENT", "Vital Signs Assessment", AbstractionLevel.CATEGORY, "chest_pain")

    # --- L1: Normalized Actions ---
    act_ecg = _c("ORDER_ECG", "Order 12-Lead ECG",
                 AbstractionLevel.NORMALIZED, "chest_pain",
                 synonyms=("ecg", "12_lead_ecg", "order_12_lead_ecg", "get_ecg",
                           "electrocardiogram", "ekg", "obtain_12_lead_ecg",
                           "order_imaging_ecg", "order_imaging_ekg"))
    act_ecg_v4r = _c("ORDER_ECG_V4R", "Order Right-Sided ECG (V4R)",
                     AbstractionLevel.NORMALIZED, "chest_pain",
                     synonyms=("right_sided_ecg", "v4r", "rv_leads", "right_ecg"))
    act_troponin = _c("ORDER_TROPONIN", "Order Troponin",
                      AbstractionLevel.NORMALIZED, "chest_pain",
                      synonyms=("troponin", "hs_troponin", "troponin_i", "troponin_t",
                                "order_lab_troponin", "cardiac_enzymes",
                                "order_serial_troponin", "serial_troponin"))
    act_aspirin = _c("GIVE_ASPIRIN", "Give Aspirin 325mg",
                     AbstractionLevel.NORMALIZED, "chest_pain",
                     synonyms=("aspirin", "aspirin_loading", "give_aspirin_loading",
                               "aspirin_325", "asa"),
                     system="RxNorm", code="1191")
    act_p2y12 = _c("GIVE_P2Y12_INHIBITOR", "Give P2Y12 Inhibitor",
                   AbstractionLevel.NORMALIZED, "chest_pain",
                   synonyms=("p2y12_inhibitor", "clopidogrel", "ticagrelor", "prasugrel",
                             "give_p2y12_inhibitor", "plavix"))
    act_nitrates = _c("GIVE_NITRATES", "Give Nitroglycerin",
                      AbstractionLevel.NORMALIZED, "chest_pain",
                      synonyms=("nitroglycerin", "ntg", "nitro", "sublingual_nitro",
                                "give_nitroglycerin"),
                      system="RxNorm", code="4917")
    act_heparin = _c("GIVE_HEPARIN", "Give Heparin",
                     AbstractionLevel.NORMALIZED, "chest_pain",
                     synonyms=("heparin", "unfractionated_heparin", "ufh",
                               "heparin_bolus", "anticoagulation"),
                     system="RxNorm", code="5224")
    act_enoxaparin = _c("GIVE_ENOXAPARIN", "Give Enoxaparin",
                        AbstractionLevel.NORMALIZED, "chest_pain",
                        synonyms=("enoxaparin", "lovenox", "lmwh"),
                        system="RxNorm", code="67108")
    act_cath_lab = _c("ACTIVATE_CATH_LAB", "Activate Cath Lab",
                      AbstractionLevel.NORMALIZED, "chest_pain",
                      synonyms=("cath_lab", "cardiac_catheterization", "pci",
                                "percutaneous_coronary_intervention", "angioplasty"))
    act_fibrinolysis = _c("GIVE_FIBRINOLYTIC", "Give Fibrinolytic",
                          AbstractionLevel.NORMALIZED, "chest_pain",
                          synonyms=("fibrinolytic", "tpa", "alteplase", "tenecteplase",
                                    "thrombolytic", "fibrinolysis"))
    act_assess_vitals = _c("ASSESS_VITALS_ACS", "Assess Vital Signs",
                           AbstractionLevel.NORMALIZED, "chest_pain",
                           synonyms=("check_vitals", "assess_vitals", "vital_signs",
                                     "assess_vital_signs", "check_vital_signs"))
    act_assess_bleeding = _c("ASSESS_BLEEDING_RISK", "Assess Bleeding Risk",
                             AbstractionLevel.NORMALIZED, "chest_pain",
                             synonyms=("bleeding_risk", "has_bled_score", "crusade_score"))
    act_diagnose_stemi = _c("DIAGNOSE_STEMI", "Diagnose STEMI",
                            AbstractionLevel.NORMALIZED, "chest_pain",
                            synonyms=("stemi", "st_elevation_mi", "stemi_diagnosis"),
                            system="SNOMED", code="401303003")
    act_diagnose_rv = _c("DIAGNOSE_RV_INFARCT", "Diagnose RV Infarction",
                         AbstractionLevel.NORMALIZED, "chest_pain",
                         synonyms=("rv_infarct", "right_ventricular_infarction",
                                   "rv_involvement", "rvi"),
                         system="SNOMED", code="57054005")
    act_give_medication = _c("GIVE_MEDICATION", "Give Medication (generic)",
                             AbstractionLevel.NORMALIZED, "chest_pain",
                             synonyms=("administer_medication",))

    all_concepts = [
        phase_initial, phase_stemi, phase_nstemi,
        goal_diagnosis, goal_antiplatelet, goal_reperfusion, goal_pain, goal_anticoag,
        cat_ecg, cat_biomarker, cat_antiplatelet, cat_nitrate, cat_anticoag_agents,
        cat_reperfusion, cat_imaging, cat_vitals,
        act_ecg, act_ecg_v4r, act_troponin, act_aspirin, act_p2y12,
        act_nitrates, act_heparin, act_enoxaparin,
        act_cath_lab, act_fibrinolysis,
        act_assess_vitals, act_assess_bleeding,
        act_diagnose_stemi, act_diagnose_rv, act_give_medication,
    ]
    for c in all_concepts:
        onto.add_concept(c)

    # --- IS-A Relations ---
    # L3 → L4
    onto.add_relation(goal_diagnosis, ConceptRelation.IS_A, phase_initial)
    onto.add_relation(goal_pain, ConceptRelation.IS_A, phase_initial)
    onto.add_relation(goal_antiplatelet, ConceptRelation.IS_A, phase_initial)
    onto.add_relation(goal_reperfusion, ConceptRelation.IS_A, phase_stemi)
    onto.add_relation(goal_anticoag, ConceptRelation.IS_A, phase_stemi)

    # L2 → L3
    onto.add_relation(cat_ecg, ConceptRelation.IS_A, goal_diagnosis)
    onto.add_relation(cat_biomarker, ConceptRelation.IS_A, goal_diagnosis)
    onto.add_relation(cat_imaging, ConceptRelation.IS_A, goal_diagnosis)
    onto.add_relation(cat_antiplatelet, ConceptRelation.IS_A, goal_antiplatelet)
    onto.add_relation(cat_nitrate, ConceptRelation.IS_A, goal_pain)
    onto.add_relation(cat_anticoag_agents, ConceptRelation.IS_A, goal_anticoag)
    onto.add_relation(cat_reperfusion, ConceptRelation.IS_A, goal_reperfusion)
    onto.add_relation(cat_vitals, ConceptRelation.IS_A, goal_diagnosis)

    # L1 → L2
    onto.add_relation(act_ecg, ConceptRelation.IS_A, cat_ecg)
    onto.add_relation(act_ecg_v4r, ConceptRelation.IS_A, cat_ecg)
    onto.add_relation(act_troponin, ConceptRelation.IS_A, cat_biomarker)
    onto.add_relation(act_aspirin, ConceptRelation.IS_A, cat_antiplatelet)
    onto.add_relation(act_p2y12, ConceptRelation.IS_A, cat_antiplatelet)
    onto.add_relation(act_nitrates, ConceptRelation.IS_A, cat_nitrate)
    onto.add_relation(act_heparin, ConceptRelation.IS_A, cat_anticoag_agents)
    onto.add_relation(act_enoxaparin, ConceptRelation.IS_A, cat_anticoag_agents)
    onto.add_relation(act_cath_lab, ConceptRelation.IS_A, cat_reperfusion)
    onto.add_relation(act_fibrinolysis, ConceptRelation.IS_A, cat_reperfusion)
    onto.add_relation(act_assess_vitals, ConceptRelation.IS_A, cat_vitals)
    onto.add_relation(act_assess_bleeding, ConceptRelation.IS_A, cat_vitals)

    # Specific IS-A
    onto.add_relation(act_ecg_v4r, ConceptRelation.IS_A, act_ecg)  # V4R is specialized ECG
    onto.add_relation(act_enoxaparin, ConceptRelation.IS_A, act_heparin)  # LMWH IS-A heparin class

    # --- PRECEDES ---
    onto.add_relation(act_ecg, ConceptRelation.PRECEDES, act_cath_lab)
    onto.add_relation(act_ecg, ConceptRelation.PRECEDES, act_nitrates)
    onto.add_relation(act_assess_bleeding, ConceptRelation.PRECEDES, act_heparin)
    onto.add_relation(act_assess_vitals, ConceptRelation.PRECEDES, act_give_medication)

    # --- CONTRAINDICATES ---
    onto.add_relation(act_diagnose_rv, ConceptRelation.CONTRAINDICATES, act_nitrates)

    return onto


# ======================================================================
# AKI Domain (KDIGO)
# ======================================================================

def build_aki_ontology() -> ClinicalOntology:
    """Build AKI domain ontology with KDIGO hierarchy."""
    onto = ClinicalOntology()

    # --- L4: Phases ---
    phase_detection = _c("AKI_DETECTION", "AKI Detection", AbstractionLevel.PHASE, "aki")
    phase_mgmt = _c("AKI_MANAGEMENT", "AKI Management", AbstractionLevel.PHASE, "aki")
    phase_prevention = _c("NEPHROTOXIN_PREVENTION", "Nephrotoxin Prevention", AbstractionLevel.PHASE, "aki")

    # --- L3: Goals ---
    goal_staging = _c("AKI_STAGING", "AKI Staging Assessment", AbstractionLevel.GOAL, "aki")
    goal_fluid = _c("VOLUME_MANAGEMENT", "Volume Management", AbstractionLevel.GOAL, "aki")
    goal_nephroprotect = _c("NEPHROPROTECTION", "Nephroprotection", AbstractionLevel.GOAL, "aki")
    goal_renal_replace = _c("RENAL_REPLACEMENT", "Renal Replacement Therapy", AbstractionLevel.GOAL, "aki")

    # --- L2: Categories ---
    cat_renal_labs = _c("RENAL_FUNCTION_LABS", "Renal Function Labs", AbstractionLevel.CATEGORY, "aki")
    cat_urine = _c("URINE_ASSESSMENT", "Urine Assessment", AbstractionLevel.CATEGORY, "aki")
    cat_iv_fluid = _c("IV_FLUID_THERAPY", "IV Fluid Therapy", AbstractionLevel.CATEGORY, "aki")
    cat_nephrotoxin = _c("NEPHROTOXIC_AGENTS", "Nephrotoxic Agents", AbstractionLevel.CATEGORY, "aki",
                         synonyms=("nephrotoxins", "nephrotoxic_drugs"))
    cat_rrt = _c("RRT_MODALITIES", "RRT Modalities", AbstractionLevel.CATEGORY, "aki")
    cat_imaging_renal = _c("RENAL_IMAGING", "Renal Imaging", AbstractionLevel.CATEGORY, "aki")

    # --- L1: Normalized Actions ---
    act_creatinine = _c("ORDER_CREATININE", "Order Serum Creatinine",
                        AbstractionLevel.NORMALIZED, "aki",
                        synonyms=("creatinine", "serum_creatinine", "order_lab_creatinine",
                                  "scr", "check_creatinine",
                                  "monitor_creatinine_daily", "monitor_creatinine_q12h",
                                  "monitor_creatinine_q6h", "check_baseline_egfr"))
    act_bun = _c("ORDER_BUN", "Order BUN",
                 AbstractionLevel.NORMALIZED, "aki",
                 synonyms=("bun", "blood_urea_nitrogen", "order_lab_bun"))
    act_egfr = _c("ORDER_EGFR", "Order eGFR",
                  AbstractionLevel.NORMALIZED, "aki",
                  synonyms=("egfr", "estimated_gfr", "glomerular_filtration"))
    act_urine_output = _c("MONITOR_URINE_OUTPUT", "Monitor Urine Output",
                          AbstractionLevel.NORMALIZED, "aki",
                          synonyms=("urine_output", "uo_monitoring", "hourly_urine",
                                    "foley_catheter", "uop",
                                    "monitor_fluid_balance_hourly",
                                    "monitor_urine_output"))
    act_urinalysis = _c("ORDER_URINALYSIS", "Order Urinalysis",
                        AbstractionLevel.NORMALIZED, "aki",
                        synonyms=("urinalysis", "ua", "urine_analysis", "order_lab_urinalysis"))
    act_ns_bolus = _c("GIVE_NS_BOLUS", "Give Normal Saline Bolus",
                      AbstractionLevel.NORMALIZED, "aki",
                      synonyms=("ns_bolus", "saline_bolus", "iv_ns", "fluid_bolus",
                                "iv_hydration_if_proceeding", "iv_hydration_periprocedure",
                                "optimize_volume_status"))
    act_stop_nephrotoxin = _c("STOP_NEPHROTOXIC_AGENT", "Stop Nephrotoxic Agent",
                              AbstractionLevel.NORMALIZED, "aki",
                              synonyms=("hold_nephrotoxins", "stop_nsaids",
                                        "discontinue_contrast", "hold_acei",
                                        "stop_nephrotoxic", "discontinue_nephrotoxins",
                                        "avoid_nephrotoxins", "hold_nsaids",
                                        "hold_nephrotoxic_medications",
                                        "avoid_additional_nephrotoxins"))
    act_give_nephrotoxin = _c("GIVE_NEPHROTOXIC_AGENT", "Give Nephrotoxic Agent",
                              AbstractionLevel.NORMALIZED, "aki",
                              synonyms=("give_nsaid", "give_contrast", "aminoglycoside",
                                        "give_gentamicin", "iv_contrast"))
    act_renal_us = _c("ORDER_RENAL_ULTRASOUND", "Order Renal Ultrasound",
                      AbstractionLevel.NORMALIZED, "aki",
                      synonyms=("renal_ultrasound", "kidney_ultrasound", "renal_us"))
    act_start_crrt = _c("START_CRRT", "Start CRRT",
                        AbstractionLevel.NORMALIZED, "aki",
                        synonyms=("crrt", "continuous_renal_replacement",
                                  "cvvh", "cvvhd", "cvvhdf"))
    act_start_hd = _c("START_HEMODIALYSIS", "Start Hemodialysis",
                      AbstractionLevel.NORMALIZED, "aki",
                      synonyms=("hemodialysis", "hd", "intermittent_hemodialysis"))
    act_electrolytes = _c("ORDER_ELECTROLYTES", "Order Electrolytes",
                          AbstractionLevel.NORMALIZED, "aki",
                          synonyms=("electrolytes", "bmp", "chem7", "order_lab_electrolytes",
                                    "potassium", "sodium"))

    all_concepts = [
        phase_detection, phase_mgmt, phase_prevention,
        goal_staging, goal_fluid, goal_nephroprotect, goal_renal_replace,
        cat_renal_labs, cat_urine, cat_iv_fluid, cat_nephrotoxin, cat_rrt, cat_imaging_renal,
        act_creatinine, act_bun, act_egfr, act_urine_output, act_urinalysis,
        act_ns_bolus, act_stop_nephrotoxin, act_give_nephrotoxin,
        act_renal_us, act_start_crrt, act_start_hd, act_electrolytes,
    ]
    for c in all_concepts:
        onto.add_concept(c)

    # IS-A
    onto.add_relation(goal_staging, ConceptRelation.IS_A, phase_detection)
    onto.add_relation(goal_fluid, ConceptRelation.IS_A, phase_mgmt)
    onto.add_relation(goal_renal_replace, ConceptRelation.IS_A, phase_mgmt)
    onto.add_relation(goal_nephroprotect, ConceptRelation.IS_A, phase_prevention)

    onto.add_relation(cat_renal_labs, ConceptRelation.IS_A, goal_staging)
    onto.add_relation(cat_urine, ConceptRelation.IS_A, goal_staging)
    onto.add_relation(cat_iv_fluid, ConceptRelation.IS_A, goal_fluid)
    onto.add_relation(cat_nephrotoxin, ConceptRelation.IS_A, goal_nephroprotect)
    onto.add_relation(cat_rrt, ConceptRelation.IS_A, goal_renal_replace)
    onto.add_relation(cat_imaging_renal, ConceptRelation.IS_A, goal_staging)

    onto.add_relation(act_creatinine, ConceptRelation.IS_A, cat_renal_labs)
    onto.add_relation(act_bun, ConceptRelation.IS_A, cat_renal_labs)
    onto.add_relation(act_egfr, ConceptRelation.IS_A, cat_renal_labs)
    onto.add_relation(act_electrolytes, ConceptRelation.IS_A, cat_renal_labs)
    onto.add_relation(act_urine_output, ConceptRelation.IS_A, cat_urine)
    onto.add_relation(act_urinalysis, ConceptRelation.IS_A, cat_urine)
    onto.add_relation(act_ns_bolus, ConceptRelation.IS_A, cat_iv_fluid)
    onto.add_relation(act_stop_nephrotoxin, ConceptRelation.IS_A, cat_nephrotoxin)
    onto.add_relation(act_give_nephrotoxin, ConceptRelation.IS_A, cat_nephrotoxin)
    onto.add_relation(act_renal_us, ConceptRelation.IS_A, cat_imaging_renal)
    onto.add_relation(act_start_crrt, ConceptRelation.IS_A, cat_rrt)
    onto.add_relation(act_start_hd, ConceptRelation.IS_A, cat_rrt)

    return onto


# ======================================================================
# STROKE Domain (AHA 2019)
# ======================================================================

def build_stroke_ontology() -> ClinicalOntology:
    """Build stroke domain ontology with AHA 2019 hierarchy."""
    onto = ClinicalOntology()

    # --- L4: Phases ---
    phase_initial = _c("STROKE_INITIAL", "Stroke Initial Assessment", AbstractionLevel.PHASE, "stroke")
    phase_intervention = _c("STROKE_INTERVENTION", "Stroke Intervention", AbstractionLevel.PHASE, "stroke")

    # --- L3: Goals ---
    goal_neuro_assess = _c("NEUROLOGICAL_ASSESSMENT", "Neurological Assessment", AbstractionLevel.GOAL, "stroke")
    goal_thrombolysis = _c("THROMBOLYSIS", "Thrombolysis", AbstractionLevel.GOAL, "stroke")
    goal_thrombectomy = _c("MECHANICAL_THROMBECTOMY", "Mechanical Thrombectomy", AbstractionLevel.GOAL, "stroke")
    goal_bp_management = _c("BP_MANAGEMENT_STROKE", "Blood Pressure Management", AbstractionLevel.GOAL, "stroke")

    # --- L2: Categories ---
    cat_neuro_exam = _c("NEURO_EXAMINATION", "Neurological Examination", AbstractionLevel.CATEGORY, "stroke")
    cat_brain_imaging = _c("BRAIN_IMAGING", "Brain Imaging", AbstractionLevel.CATEGORY, "stroke")
    cat_thrombolytic = _c("THROMBOLYTIC_AGENTS", "Thrombolytic Agents", AbstractionLevel.CATEGORY, "stroke")
    cat_antihypertensive = _c("ANTIHYPERTENSIVE_AGENTS", "Antihypertensive Agents", AbstractionLevel.CATEGORY, "stroke")
    cat_labs_stroke = _c("STROKE_LABS", "Stroke Laboratory Panel", AbstractionLevel.CATEGORY, "stroke")

    # --- L1: Normalized Actions ---
    act_nihss = _c("ASSESS_NIHSS", "Assess NIHSS Score",
                   AbstractionLevel.NORMALIZED, "stroke",
                   synonyms=("nihss", "nih_stroke_scale", "stroke_scale",
                             "calculate_nihss", "nihss_score", "perform_nihss",
                             "assess_nihss_score", "repeat_nihss"))
    act_ct_head = _c("ORDER_CT_HEAD", "Order CT Head",
                     AbstractionLevel.NORMALIZED, "stroke",
                     synonyms=("ct_head", "head_ct", "non_contrast_ct",
                               "order_imaging_ct_head", "brain_ct",
                               "order_imaging_ct", "stat_ct_head"))
    act_cta = _c("ORDER_CTA", "Order CT Angiography",
                 AbstractionLevel.NORMALIZED, "stroke",
                 synonyms=("cta", "ct_angiography", "ct_angio", "vessel_imaging"))
    act_mri_brain = _c("ORDER_MRI_BRAIN", "Order MRI Brain",
                       AbstractionLevel.NORMALIZED, "stroke",
                       synonyms=("mri_brain", "brain_mri", "dwi_mri"))
    act_alteplase = _c("GIVE_ALTEPLASE", "Give Alteplase 0.9mg/kg",
                       AbstractionLevel.NORMALIZED, "stroke",
                       synonyms=("alteplase", "tpa", "give_tpa",
                                 "give_alteplase_0.9mg_kg", "tissue_plasminogen_activator",
                                 "give_medication_alteplase", "thrombolytic"),
                       system="RxNorm", code="8410")
    act_thrombectomy = _c("PERFORM_THROMBECTOMY", "Perform Mechanical Thrombectomy",
                          AbstractionLevel.NORMALIZED, "stroke",
                          synonyms=("thrombectomy", "mechanical_thrombectomy",
                                    "endovascular_thrombectomy", "evt"))
    act_labetalol = _c("GIVE_LABETALOL", "Give Labetalol",
                       AbstractionLevel.NORMALIZED, "stroke",
                       synonyms=("labetalol", "iv_labetalol"),
                       system="RxNorm", code="6185")
    act_nicardipine = _c("GIVE_NICARDIPINE", "Give Nicardipine",
                         AbstractionLevel.NORMALIZED, "stroke",
                         synonyms=("nicardipine", "cardene"),
                         system="RxNorm", code="7373")
    act_glucose = _c("ORDER_GLUCOSE_STROKE", "Order Blood Glucose",
                     AbstractionLevel.NORMALIZED, "stroke",
                     synonyms=("blood_glucose", "glucose", "finger_stick_glucose"))
    act_coag = _c("ORDER_COAGULATION", "Order Coagulation Studies",
                  AbstractionLevel.NORMALIZED, "stroke",
                  synonyms=("pt_inr", "coagulation", "inr", "ptt"))

    all_concepts = [
        phase_initial, phase_intervention,
        goal_neuro_assess, goal_thrombolysis, goal_thrombectomy, goal_bp_management,
        cat_neuro_exam, cat_brain_imaging, cat_thrombolytic, cat_antihypertensive, cat_labs_stroke,
        act_nihss, act_ct_head, act_cta, act_mri_brain,
        act_alteplase, act_thrombectomy,
        act_labetalol, act_nicardipine,
        act_glucose, act_coag,
    ]
    for c in all_concepts:
        onto.add_concept(c)

    # IS-A
    onto.add_relation(goal_neuro_assess, ConceptRelation.IS_A, phase_initial)
    onto.add_relation(goal_bp_management, ConceptRelation.IS_A, phase_initial)
    onto.add_relation(goal_thrombolysis, ConceptRelation.IS_A, phase_intervention)
    onto.add_relation(goal_thrombectomy, ConceptRelation.IS_A, phase_intervention)

    onto.add_relation(cat_neuro_exam, ConceptRelation.IS_A, goal_neuro_assess)
    onto.add_relation(cat_brain_imaging, ConceptRelation.IS_A, goal_neuro_assess)
    onto.add_relation(cat_labs_stroke, ConceptRelation.IS_A, goal_neuro_assess)
    onto.add_relation(cat_thrombolytic, ConceptRelation.IS_A, goal_thrombolysis)
    onto.add_relation(cat_antihypertensive, ConceptRelation.IS_A, goal_bp_management)

    onto.add_relation(act_nihss, ConceptRelation.IS_A, cat_neuro_exam)
    onto.add_relation(act_ct_head, ConceptRelation.IS_A, cat_brain_imaging)
    onto.add_relation(act_cta, ConceptRelation.IS_A, cat_brain_imaging)
    onto.add_relation(act_mri_brain, ConceptRelation.IS_A, cat_brain_imaging)
    onto.add_relation(act_alteplase, ConceptRelation.IS_A, cat_thrombolytic)
    onto.add_relation(act_thrombectomy, ConceptRelation.IS_A, cat_brain_imaging)  # Located via imaging
    onto.add_relation(act_labetalol, ConceptRelation.IS_A, cat_antihypertensive)
    onto.add_relation(act_nicardipine, ConceptRelation.IS_A, cat_antihypertensive)
    onto.add_relation(act_glucose, ConceptRelation.IS_A, cat_labs_stroke)
    onto.add_relation(act_coag, ConceptRelation.IS_A, cat_labs_stroke)

    # PRECEDES
    onto.add_relation(act_ct_head, ConceptRelation.PRECEDES, act_alteplase)
    onto.add_relation(act_nihss, ConceptRelation.PRECEDES, act_alteplase)
    onto.add_relation(act_coag, ConceptRelation.PRECEDES, act_alteplase)

    return onto


# ======================================================================
# HEART FAILURE Domain (AHA 2022)
# ======================================================================

def build_heart_failure_ontology() -> ClinicalOntology:
    """Build heart failure domain ontology with AHA 2022 hierarchy."""
    onto = ClinicalOntology()

    # --- L4: Phases ---
    phase_acute = _c("ADHF_STABILIZATION", "ADHF Stabilization", AbstractionLevel.PHASE, "heart_failure")
    phase_chronic = _c("HFREF_OPTIMIZATION", "HFrEF Optimization", AbstractionLevel.PHASE, "heart_failure")

    # --- L3: Goals ---
    goal_decongest = _c("DECONGESTION", "Decongestion", AbstractionLevel.GOAL, "heart_failure")
    goal_gdmt = _c("GDMT_INITIATION", "GDMT Initiation", AbstractionLevel.GOAL, "heart_failure")
    goal_hemodynamic_hf = _c("HEMODYNAMIC_SUPPORT_HF", "Hemodynamic Support", AbstractionLevel.GOAL, "heart_failure")
    goal_monitoring_hf = _c("HF_MONITORING", "Heart Failure Monitoring", AbstractionLevel.GOAL, "heart_failure")

    # --- L2: Categories ---
    cat_diuretic = _c("DIURETIC_THERAPY", "Diuretic Therapy", AbstractionLevel.CATEGORY, "heart_failure")
    cat_raas = _c("RAAS_INHIBITORS", "RAAS Inhibitors", AbstractionLevel.CATEGORY, "heart_failure",
                  synonyms=("ace_inhibitors", "arb", "arni"))
    cat_beta_blocker = _c("BETA_BLOCKER_THERAPY", "Beta-Blocker Therapy", AbstractionLevel.CATEGORY, "heart_failure")
    cat_mra = _c("MRA_THERAPY", "Mineralocorticoid Receptor Antagonist", AbstractionLevel.CATEGORY, "heart_failure")
    cat_sglt2 = _c("SGLT2_INHIBITORS", "SGLT2 Inhibitors", AbstractionLevel.CATEGORY, "heart_failure")
    cat_inotrope = _c("INOTROPE_THERAPY", "Inotrope Therapy", AbstractionLevel.CATEGORY, "heart_failure")
    cat_hf_labs = _c("HF_LABORATORY", "Heart Failure Labs", AbstractionLevel.CATEGORY, "heart_failure")

    # --- L1: Normalized Actions ---
    act_furosemide = _c("GIVE_FUROSEMIDE", "Give Furosemide",
                        AbstractionLevel.NORMALIZED, "heart_failure",
                        synonyms=("furosemide", "lasix", "iv_furosemide", "loop_diuretic"),
                        system="RxNorm", code="4603")
    act_sacubitril = _c("GIVE_SACUBITRIL_VALSARTAN", "Give Sacubitril/Valsartan",
                        AbstractionLevel.NORMALIZED, "heart_failure",
                        synonyms=("entresto", "sacubitril_valsartan", "arni",
                                  "initiate_ace_or_arb_or_arni"),
                        system="RxNorm", code="1656328")
    act_carvedilol = _c("GIVE_CARVEDILOL", "Give Carvedilol",
                        AbstractionLevel.NORMALIZED, "heart_failure",
                        synonyms=("carvedilol", "coreg", "initiate_beta_blocker"),
                        system="RxNorm", code="20352")
    act_spironolactone = _c("GIVE_SPIRONOLACTONE", "Give Spironolactone",
                            AbstractionLevel.NORMALIZED, "heart_failure",
                            synonyms=("spironolactone", "aldactone", "mra"),
                            system="RxNorm", code="9997")
    act_dapagliflozin = _c("GIVE_DAPAGLIFLOZIN", "Give Dapagliflozin",
                           AbstractionLevel.NORMALIZED, "heart_failure",
                           synonyms=("dapagliflozin", "farxiga", "sglt2_inhibitor"),
                           system="RxNorm", code="1488564")
    act_dobutamine = _c("GIVE_DOBUTAMINE", "Give Dobutamine",
                        AbstractionLevel.NORMALIZED, "heart_failure",
                        synonyms=("dobutamine", "inotrope"),
                        system="RxNorm", code="3616")
    act_milrinone = _c("GIVE_MILRINONE", "Give Milrinone",
                       AbstractionLevel.NORMALIZED, "heart_failure",
                       synonyms=("milrinone",),
                       system="RxNorm", code="52769")
    act_bnp = _c("ORDER_BNP", "Order BNP/NT-proBNP",
                 AbstractionLevel.NORMALIZED, "heart_failure",
                 synonyms=("bnp", "nt_probnp", "natriuretic_peptide",
                           "order_lab_bnp", "proBNP"))
    act_echo = _c("ORDER_ECHOCARDIOGRAM", "Order Echocardiogram",
                  AbstractionLevel.NORMALIZED, "heart_failure",
                  synonyms=("echocardiogram", "echo", "tte", "transthoracic_echo",
                            "cardiac_ultrasound"))

    all_concepts = [
        phase_acute, phase_chronic,
        goal_decongest, goal_gdmt, goal_hemodynamic_hf, goal_monitoring_hf,
        cat_diuretic, cat_raas, cat_beta_blocker, cat_mra, cat_sglt2, cat_inotrope, cat_hf_labs,
        act_furosemide, act_sacubitril, act_carvedilol, act_spironolactone,
        act_dapagliflozin, act_dobutamine, act_milrinone, act_bnp, act_echo,
    ]
    for c in all_concepts:
        onto.add_concept(c)

    # IS-A
    onto.add_relation(goal_decongest, ConceptRelation.IS_A, phase_acute)
    onto.add_relation(goal_hemodynamic_hf, ConceptRelation.IS_A, phase_acute)
    onto.add_relation(goal_monitoring_hf, ConceptRelation.IS_A, phase_acute)
    onto.add_relation(goal_gdmt, ConceptRelation.IS_A, phase_chronic)

    onto.add_relation(cat_diuretic, ConceptRelation.IS_A, goal_decongest)
    onto.add_relation(cat_raas, ConceptRelation.IS_A, goal_gdmt)
    onto.add_relation(cat_beta_blocker, ConceptRelation.IS_A, goal_gdmt)
    onto.add_relation(cat_mra, ConceptRelation.IS_A, goal_gdmt)
    onto.add_relation(cat_sglt2, ConceptRelation.IS_A, goal_gdmt)
    onto.add_relation(cat_inotrope, ConceptRelation.IS_A, goal_hemodynamic_hf)
    onto.add_relation(cat_hf_labs, ConceptRelation.IS_A, goal_monitoring_hf)

    onto.add_relation(act_furosemide, ConceptRelation.IS_A, cat_diuretic)
    onto.add_relation(act_sacubitril, ConceptRelation.IS_A, cat_raas)
    onto.add_relation(act_carvedilol, ConceptRelation.IS_A, cat_beta_blocker)
    onto.add_relation(act_spironolactone, ConceptRelation.IS_A, cat_mra)
    onto.add_relation(act_dapagliflozin, ConceptRelation.IS_A, cat_sglt2)
    onto.add_relation(act_dobutamine, ConceptRelation.IS_A, cat_inotrope)
    onto.add_relation(act_milrinone, ConceptRelation.IS_A, cat_inotrope)
    onto.add_relation(act_bnp, ConceptRelation.IS_A, cat_hf_labs)
    onto.add_relation(act_echo, ConceptRelation.IS_A, cat_hf_labs)

    return onto


# ======================================================================
# DKA Domain (ADA)
# ======================================================================

def build_dka_ontology() -> ClinicalOntology:
    """Build DKA domain ontology with ADA hierarchy."""
    onto = ClinicalOntology()

    # --- L4: Phases ---
    phase_initial_dka = _c("DKA_INITIAL", "DKA Initial Management", AbstractionLevel.PHASE, "dka")
    phase_correction = _c("DKA_CORRECTION", "DKA Correction", AbstractionLevel.PHASE, "dka")
    phase_transition = _c("DKA_TRANSITION", "DKA Transition to SC Insulin", AbstractionLevel.PHASE, "dka")

    # --- L3: Goals ---
    goal_rehydration = _c("DKA_REHYDRATION", "DKA Rehydration", AbstractionLevel.GOAL, "dka")
    goal_insulin = _c("INSULIN_THERAPY", "Insulin Therapy", AbstractionLevel.GOAL, "dka")
    goal_electrolyte = _c("ELECTROLYTE_CORRECTION", "Electrolyte Correction", AbstractionLevel.GOAL, "dka")
    goal_monitor_dka = _c("DKA_MONITORING", "DKA Monitoring", AbstractionLevel.GOAL, "dka")

    # --- L2: Categories ---
    cat_iv_fluids_dka = _c("DKA_IV_FLUIDS", "DKA IV Fluids", AbstractionLevel.CATEGORY, "dka")
    cat_insulin_agents = _c("INSULIN_AGENTS", "Insulin Agents", AbstractionLevel.CATEGORY, "dka")
    cat_k_replacement = _c("POTASSIUM_REPLACEMENT", "Potassium Replacement", AbstractionLevel.CATEGORY, "dka")
    cat_bicarb = _c("BICARBONATE_THERAPY", "Bicarbonate Therapy", AbstractionLevel.CATEGORY, "dka")
    cat_dka_labs = _c("DKA_LABORATORY", "DKA Laboratory Monitoring", AbstractionLevel.CATEGORY, "dka")

    # --- L1: Normalized Actions ---
    act_ns_dka = _c("GIVE_NS_1L", "Give NS 1L Bolus",
                    AbstractionLevel.NORMALIZED, "dka",
                    synonyms=("ns_bolus", "normal_saline_1l", "iv_ns_1000ml",
                              "give_crystalloid_dka"))
    act_half_ns = _c("GIVE_HALF_NS", "Give 0.45% NS",
                     AbstractionLevel.NORMALIZED, "dka",
                     synonyms=("half_normal_saline", "0.45_ns"))
    act_insulin_drip = _c("START_INSULIN_DRIP", "Start Regular Insulin Drip",
                          AbstractionLevel.NORMALIZED, "dka",
                          synonyms=("insulin_drip", "insulin_infusion", "regular_insulin_iv",
                                    "give_regular_insulin", "insulin_gtt"))
    act_insulin_sc = _c("GIVE_INSULIN_SC", "Give Subcutaneous Insulin",
                        AbstractionLevel.NORMALIZED, "dka",
                        synonyms=("sc_insulin", "subcutaneous_insulin",
                                  "insulin_glargine", "lantus", "basal_insulin"))
    act_kcl = _c("GIVE_KCL", "Give Potassium Chloride",
                 AbstractionLevel.NORMALIZED, "dka",
                 synonyms=("kcl", "potassium_chloride", "iv_potassium",
                           "potassium_replacement", "k_replacement"),
                 system="RxNorm", code="8591")
    act_bicarb = _c("GIVE_SODIUM_BICARBONATE", "Give Sodium Bicarbonate",
                    AbstractionLevel.NORMALIZED, "dka",
                    synonyms=("sodium_bicarbonate", "nahco3", "bicarb",
                              "bicarbonate_infusion"),
                    system="RxNorm", code="9796")
    act_glucose_dka = _c("ORDER_GLUCOSE_DKA", "Order Blood Glucose",
                         AbstractionLevel.NORMALIZED, "dka",
                         synonyms=("blood_glucose", "glucose", "check_glucose",
                                   "fingerstick_glucose", "point_of_care_glucose"))
    act_abg = _c("ORDER_ABG", "Order Arterial Blood Gas",
                 AbstractionLevel.NORMALIZED, "dka",
                 synonyms=("abg", "arterial_blood_gas", "blood_gas",
                           "order_lab_abg", "ph_check"))
    act_bmp_dka = _c("ORDER_BMP_DKA", "Order Basic Metabolic Panel",
                     AbstractionLevel.NORMALIZED, "dka",
                     synonyms=("bmp", "basic_metabolic_panel", "chem7",
                               "electrolytes_dka", "order_lab_bmp"))
    act_anion_gap = _c("CALCULATE_ANION_GAP", "Calculate Anion Gap",
                       AbstractionLevel.NORMALIZED, "dka",
                       synonyms=("anion_gap", "ag", "calculate_ag"))
    act_d5_ns = _c("GIVE_D5_NS", "Give D5 0.45% NS",
                   AbstractionLevel.NORMALIZED, "dka",
                   synonyms=("d5_half_ns", "dextrose_saline", "d5_0.45ns"))

    all_concepts = [
        phase_initial_dka, phase_correction, phase_transition,
        goal_rehydration, goal_insulin, goal_electrolyte, goal_monitor_dka,
        cat_iv_fluids_dka, cat_insulin_agents, cat_k_replacement, cat_bicarb, cat_dka_labs,
        act_ns_dka, act_half_ns, act_insulin_drip, act_insulin_sc,
        act_kcl, act_bicarb, act_glucose_dka, act_abg, act_bmp_dka,
        act_anion_gap, act_d5_ns,
    ]
    for c in all_concepts:
        onto.add_concept(c)

    # IS-A
    onto.add_relation(goal_rehydration, ConceptRelation.IS_A, phase_initial_dka)
    onto.add_relation(goal_monitor_dka, ConceptRelation.IS_A, phase_initial_dka)
    onto.add_relation(goal_insulin, ConceptRelation.IS_A, phase_correction)
    onto.add_relation(goal_electrolyte, ConceptRelation.IS_A, phase_correction)

    onto.add_relation(cat_iv_fluids_dka, ConceptRelation.IS_A, goal_rehydration)
    onto.add_relation(cat_insulin_agents, ConceptRelation.IS_A, goal_insulin)
    onto.add_relation(cat_k_replacement, ConceptRelation.IS_A, goal_electrolyte)
    onto.add_relation(cat_bicarb, ConceptRelation.IS_A, goal_electrolyte)
    onto.add_relation(cat_dka_labs, ConceptRelation.IS_A, goal_monitor_dka)

    onto.add_relation(act_ns_dka, ConceptRelation.IS_A, cat_iv_fluids_dka)
    onto.add_relation(act_half_ns, ConceptRelation.IS_A, cat_iv_fluids_dka)
    onto.add_relation(act_d5_ns, ConceptRelation.IS_A, cat_iv_fluids_dka)
    onto.add_relation(act_insulin_drip, ConceptRelation.IS_A, cat_insulin_agents)
    onto.add_relation(act_insulin_sc, ConceptRelation.IS_A, cat_insulin_agents)
    onto.add_relation(act_kcl, ConceptRelation.IS_A, cat_k_replacement)
    onto.add_relation(act_bicarb, ConceptRelation.IS_A, cat_bicarb)
    onto.add_relation(act_glucose_dka, ConceptRelation.IS_A, cat_dka_labs)
    onto.add_relation(act_abg, ConceptRelation.IS_A, cat_dka_labs)
    onto.add_relation(act_bmp_dka, ConceptRelation.IS_A, cat_dka_labs)
    onto.add_relation(act_anion_gap, ConceptRelation.IS_A, cat_dka_labs)

    # PRECEDES
    onto.add_relation(act_ns_dka, ConceptRelation.PRECEDES, act_insulin_drip)  # Rehydrate before insulin

    return onto


# ======================================================================
# Factory: Build Domain Ontology
# ======================================================================

# Registry of domain builders
DOMAIN_BUILDERS: Dict[str, callable] = {
    "sepsis": build_sepsis_ontology,
    "chest_pain": build_chest_pain_ontology,
    "aki": build_aki_ontology,
    "stroke": build_stroke_ontology,
    "heart_failure": build_heart_failure_ontology,
    "dka": build_dka_ontology,
}


def build_domain_ontology(domain: str) -> ClinicalOntology:
    """Build ontology for a specific clinical domain.

    Args:
        domain: One of "sepsis", "chest_pain", "aki", "stroke",
                "heart_failure", "dka"

    Returns:
        ClinicalOntology populated with domain-specific hierarchy

    Raises:
        ValueError: If domain is not recognized
    """
    builder = DOMAIN_BUILDERS.get(domain)
    if not builder:
        raise ValueError(
            f"Unknown domain: {domain}. "
            f"Available: {list(DOMAIN_BUILDERS.keys())}"
        )
    return builder()


def build_unified_ontology() -> ClinicalOntology:
    """Build a unified ontology combining all clinical domains.

    Merges all domain-specific hierarchies into a single ontology.
    Cross-domain concepts (e.g., IV fluids) maintain domain-specific variants.

    Returns:
        ClinicalOntology with all 6 domains merged
    """
    unified = ClinicalOntology()

    for domain, builder in DOMAIN_BUILDERS.items():
        domain_onto = builder()
        # Merge concepts
        for cid, concept in domain_onto.concepts.items():
            if cid not in unified._concepts:
                unified.add_concept(concept)
        # Merge IS-A relations
        for child_id, parent_ids in domain_onto._parents.items():
            for parent_id in parent_ids:
                child_c = domain_onto.get_concept(child_id)
                parent_c = domain_onto.get_concept(parent_id)
                if child_c and parent_c:
                    unified.add_relation(child_c, ConceptRelation.IS_A, parent_c)
        # Merge other relations
        for src_id, rels in domain_onto._relations.items():
            for rel, tgt_id in rels:
                if rel != ConceptRelation.IS_A:
                    src_c = domain_onto.get_concept(src_id)
                    tgt_c = domain_onto.get_concept(tgt_id)
                    if src_c and tgt_c:
                        unified.add_relation(src_c, rel, tgt_c)

    return unified


def get_ontology_matcher(
    domain: str, config: OntologyConfig = None
) -> OntologyMatcher:
    """Get an OntologyMatcher for a specific domain.

    Convenience function combining ontology building and matcher creation.

    Args:
        domain: Clinical domain name
        config: Optional matcher configuration (defaults to OntologyConfig())

    Returns:
        OntologyMatcher ready for action matching
    """
    ontology = build_domain_ontology(domain)
    return OntologyMatcher(ontology, config or OntologyConfig())


def get_unified_matcher(config: OntologyConfig = None) -> OntologyMatcher:
    """Get an OntologyMatcher combining all domains.

    Args:
        config: Optional matcher configuration

    Returns:
        OntologyMatcher with unified cross-domain ontology
    """
    ontology = build_unified_ontology()
    return OntologyMatcher(ontology, config or OntologyConfig())
