"""Gold Set v2: Expanded evaluation set for NeurIPS D&B defense.

Rail 1 Target:
- 300+ queries (vs. 36 in v1)
- 30% hard negatives (sibling/nearby concept confusion)
- 20% OOV (out-of-vocabulary)
- 20% abbreviation/brand/slang
- 30% standard (baseline difficulty)

Paper motivation: "BioSyn and similar benchmarks use large-scale dictionary-based evaluation."

Version: 2.0 (2026-01-25)
"""

from dataclasses import dataclass, field
from enum import Enum
from typing import List, Optional, Dict, Set, Tuple
import random


class Difficulty(Enum):
    """Query difficulty levels for stratified evaluation."""
    EASY = "easy"           # Direct synonym match
    NORMAL = "normal"       # Minor variation (brand name, abbreviation)
    HARD = "hard"           # Sibling/nearby concept confusion (negative)
    OOV = "oov"             # Out-of-vocabulary (no match expected)
    ABBREVIATION = "abbreviation"  # Medical abbreviation/slang


@dataclass
class GoldInstance:
    """A single gold standard query-concept pair.

    Attributes:
        query: The input query string (agent output)
        gold_concept_id: Expected concept ID (or None for OOV)
        difficulty: Difficulty classification
        domain: Clinical domain
        notes: Annotation notes
        hard_negatives: Confusable concepts (for hard instances)
        source: Origin of this instance (manual, generated, etc.)
    """
    query: str
    gold_concept_id: Optional[str]
    difficulty: Difficulty
    domain: str
    notes: str = ""
    hard_negatives: List[str] = field(default_factory=list)
    source: str = "manual"


# =============================================================================
# SEPSIS DOMAIN GOLD INSTANCES
# =============================================================================

SEPSIS_GOLD = [
    # --- EASY: Direct matches ---
    GoldInstance("start_norepinephrine", "START_VASOPRESSOR_NOREPINEPHRINE", Difficulty.EASY, "sepsis"),
    GoldInstance("give norepinephrine", "START_VASOPRESSOR_NOREPINEPHRINE", Difficulty.EASY, "sepsis"),
    GoldInstance("order lactate", "ORDER_LACTATE", Difficulty.EASY, "sepsis"),
    GoldInstance("measure lactate", "ORDER_LACTATE", Difficulty.EASY, "sepsis"),
    GoldInstance("blood culture", "ORDER_BLOOD_CULTURE", Difficulty.EASY, "sepsis"),
    GoldInstance("give piperacillin tazobactam", "GIVE_PIPERACILLIN_TAZOBACTAM", Difficulty.EASY, "sepsis"),
    GoldInstance("give vancomycin", "GIVE_VANCOMYCIN", Difficulty.EASY, "sepsis"),
    GoldInstance("give crystalloid", "GIVE_CRYSTALLOID", Difficulty.EASY, "sepsis"),
    GoldInstance("normal saline bolus", "GIVE_NORMAL_SALINE", Difficulty.EASY, "sepsis"),
    GoldInstance("order procalcitonin", "ORDER_PROCALCITONIN", Difficulty.EASY, "sepsis"),

    # --- NORMAL: Brand names and common variations ---
    GoldInstance("levophed", "START_VASOPRESSOR_NOREPINEPHRINE", Difficulty.NORMAL, "sepsis",
                 notes="Brand name for norepinephrine"),
    GoldInstance("zosyn", "GIVE_PIPERACILLIN_TAZOBACTAM", Difficulty.NORMAL, "sepsis",
                 notes="Brand name for pip/tazo"),
    GoldInstance("vanco", "GIVE_VANCOMYCIN", Difficulty.NORMAL, "sepsis",
                 notes="Common abbreviation"),
    GoldInstance("start pressors", "START_VASOPRESSOR_NOREPINEPHRINE", Difficulty.NORMAL, "sepsis",
                 notes="Colloquial for vasopressors"),
    GoldInstance("fluid resuscitation", "GIVE_CRYSTALLOID", Difficulty.NORMAL, "sepsis"),
    GoldInstance("30 ml/kg crystalloid", "GIVE_CRYSTALLOID", Difficulty.NORMAL, "sepsis",
                 notes="SSC bundle specific dosing"),
    GoldInstance("LR bolus", "GIVE_LACTATED_RINGERS", Difficulty.NORMAL, "sepsis",
                 notes="Lactated Ringer's abbreviation"),
    GoldInstance("NS 1 liter", "GIVE_NORMAL_SALINE", Difficulty.NORMAL, "sepsis"),
    GoldInstance("broad spectrum antibiotics", "GIVE_BROAD_SPECTRUM_ANTIBIOTICS", Difficulty.NORMAL, "sepsis"),
    GoldInstance("empiric antibiotics", "GIVE_BROAD_SPECTRUM_ANTIBIOTICS", Difficulty.NORMAL, "sepsis"),

    # --- ABBREVIATION: Medical abbreviations/slang ---
    GoldInstance("norepi", "START_VASOPRESSOR_NOREPINEPHRINE", Difficulty.ABBREVIATION, "sepsis"),
    GoldInstance("NE", "START_VASOPRESSOR_NOREPINEPHRINE", Difficulty.ABBREVIATION, "sepsis",
                 notes="Standard abbreviation"),
    GoldInstance("pip-tazo", "GIVE_PIPERACILLIN_TAZOBACTAM", Difficulty.ABBREVIATION, "sepsis"),
    GoldInstance("abx", "GIVE_BROAD_SPECTRUM_ANTIBIOTICS", Difficulty.ABBREVIATION, "sepsis",
                 notes="Common abbreviation for antibiotics"),
    GoldInstance("IVF", "GIVE_CRYSTALLOID", Difficulty.ABBREVIATION, "sepsis",
                 notes="IV fluids"),
    GoldInstance("BCx", "ORDER_BLOOD_CULTURE", Difficulty.ABBREVIATION, "sepsis",
                 notes="Blood culture abbreviation"),
    GoldInstance("CBC", "ORDER_CBC", Difficulty.ABBREVIATION, "sepsis"),
    GoldInstance("BMP", "ORDER_BMP", Difficulty.ABBREVIATION, "sepsis"),
    GoldInstance("CMP", "ORDER_CMP", Difficulty.ABBREVIATION, "sepsis"),
    GoldInstance("ABG", "ORDER_ABG", Difficulty.ABBREVIATION, "sepsis"),
    GoldInstance("PCT", "ORDER_PROCALCITONIN", Difficulty.ABBREVIATION, "sepsis",
                 notes="Procalcitonin abbreviation"),

    # --- HARD: Sibling/nearby concept confusion ---
    GoldInstance("lactated ringers", "GIVE_LACTATED_RINGERS", Difficulty.HARD, "sepsis",
                 hard_negatives=["ORDER_LACTATE"],
                 notes="Confusion: lactate vs lactated ringers"),
    GoldInstance("lactic acid level", "ORDER_LACTATE", Difficulty.HARD, "sepsis",
                 hard_negatives=["GIVE_LACTATED_RINGERS"],
                 notes="Confusion: lactate vs lactated ringers"),
    GoldInstance("dopamine", "START_VASOPRESSOR_DOPAMINE", Difficulty.HARD, "sepsis",
                 hard_negatives=["START_VASOPRESSOR_NOREPINEPHRINE", "START_VASOPRESSOR_EPINEPHRINE"],
                 notes="Confusion: different vasopressors"),
    GoldInstance("epinephrine drip", "START_VASOPRESSOR_EPINEPHRINE", Difficulty.HARD, "sepsis",
                 hard_negatives=["START_VASOPRESSOR_NOREPINEPHRINE"],
                 notes="Confusion: epi vs norepi"),
    GoldInstance("vasopressin", "START_VASOPRESSOR_VASOPRESSIN", Difficulty.HARD, "sepsis",
                 hard_negatives=["START_VASOPRESSOR_NOREPINEPHRINE"],
                 notes="Confusion: different vasopressor mechanism"),
    GoldInstance("meropenem", "GIVE_MEROPENEM", Difficulty.HARD, "sepsis",
                 hard_negatives=["GIVE_PIPERACILLIN_TAZOBACTAM"],
                 notes="Confusion: different carbapenems"),
    GoldInstance("ceftriaxone", "GIVE_CEFTRIAXONE", Difficulty.HARD, "sepsis",
                 hard_negatives=["GIVE_PIPERACILLIN_TAZOBACTAM", "GIVE_MEROPENEM"],
                 notes="Confusion: different antibiotics"),

    # --- OOV: Out-of-vocabulary (no match expected) ---
    GoldInstance("plasmapheresis", None, Difficulty.OOV, "sepsis",
                 notes="Rare intervention not in ontology"),
    GoldInstance("ECMO", None, Difficulty.OOV, "sepsis",
                 notes="Extracorporeal membrane oxygenation"),
    GoldInstance("tigecycline", None, Difficulty.OOV, "sepsis",
                 notes="Antibiotic not in ontology"),
    GoldInstance("colistin", None, Difficulty.OOV, "sepsis",
                 notes="Last-resort antibiotic"),
    GoldInstance("polymyxin B hemoperfusion", None, Difficulty.OOV, "sepsis",
                 notes="Experimental treatment"),
]


# =============================================================================
# CHEST PAIN / ACS DOMAIN GOLD INSTANCES
# =============================================================================

CHEST_PAIN_GOLD = [
    # --- EASY ---
    GoldInstance("give aspirin", "GIVE_ASPIRIN_LOADING", Difficulty.EASY, "chest_pain"),
    GoldInstance("aspirin 325", "GIVE_ASPIRIN_LOADING", Difficulty.EASY, "chest_pain"),
    GoldInstance("order ECG", "ORDER_ECG", Difficulty.EASY, "chest_pain"),
    GoldInstance("12 lead ECG", "ORDER_ECG", Difficulty.EASY, "chest_pain"),
    GoldInstance("troponin", "ORDER_TROPONIN", Difficulty.EASY, "chest_pain"),
    GoldInstance("heparin drip", "GIVE_HEPARIN", Difficulty.EASY, "chest_pain"),
    GoldInstance("activate cath lab", "ACTIVATE_CATH_LAB", Difficulty.EASY, "chest_pain"),
    GoldInstance("give morphine", "GIVE_MORPHINE", Difficulty.EASY, "chest_pain"),
    GoldInstance("give nitroglycerin", "GIVE_NITROGLYCERIN", Difficulty.EASY, "chest_pain"),
    GoldInstance("clopidogrel", "GIVE_CLOPIDOGREL", Difficulty.EASY, "chest_pain"),

    # --- NORMAL ---
    GoldInstance("plavix", "GIVE_CLOPIDOGREL", Difficulty.NORMAL, "chest_pain",
                 notes="Brand name"),
    GoldInstance("brilinta", "GIVE_TICAGRELOR", Difficulty.NORMAL, "chest_pain",
                 notes="Brand name for ticagrelor"),
    GoldInstance("effient", "GIVE_PRASUGREL", Difficulty.NORMAL, "chest_pain",
                 notes="Brand name for prasugrel"),
    GoldInstance("lovenox", "GIVE_ENOXAPARIN", Difficulty.NORMAL, "chest_pain",
                 notes="Brand name for enoxaparin"),
    GoldInstance("nitro", "GIVE_NITROGLYCERIN", Difficulty.NORMAL, "chest_pain"),
    GoldInstance("NTG", "GIVE_NITROGLYCERIN", Difficulty.NORMAL, "chest_pain"),
    GoldInstance("sublingual nitro", "GIVE_NITROGLYCERIN", Difficulty.NORMAL, "chest_pain"),
    GoldInstance("chest x-ray", "ORDER_CHEST_XRAY", Difficulty.NORMAL, "chest_pain"),
    GoldInstance("CXR", "ORDER_CHEST_XRAY", Difficulty.NORMAL, "chest_pain"),
    GoldInstance("echo", "ORDER_ECHOCARDIOGRAM", Difficulty.NORMAL, "chest_pain"),

    # --- ABBREVIATION ---
    GoldInstance("EKG", "ORDER_ECG", Difficulty.ABBREVIATION, "chest_pain"),
    GoldInstance("ASA", "GIVE_ASPIRIN_LOADING", Difficulty.ABBREVIATION, "chest_pain"),
    GoldInstance("TnI", "ORDER_TROPONIN_I", Difficulty.ABBREVIATION, "chest_pain"),
    GoldInstance("TnT", "ORDER_TROPONIN_T", Difficulty.ABBREVIATION, "chest_pain"),
    GoldInstance("trop", "ORDER_TROPONIN", Difficulty.ABBREVIATION, "chest_pain"),
    GoldInstance("BNP", "ORDER_BNP", Difficulty.ABBREVIATION, "chest_pain"),
    GoldInstance("NT-proBNP", "ORDER_NT_PROBNP", Difficulty.ABBREVIATION, "chest_pain"),
    GoldInstance("LMWH", "GIVE_ENOXAPARIN", Difficulty.ABBREVIATION, "chest_pain",
                 notes="Low molecular weight heparin"),
    GoldInstance("P2Y12", "GIVE_CLOPIDOGREL", Difficulty.ABBREVIATION, "chest_pain",
                 notes="P2Y12 inhibitor class"),
    GoldInstance("DAPT", "GIVE_CLOPIDOGREL", Difficulty.ABBREVIATION, "chest_pain",
                 notes="Dual antiplatelet therapy"),

    # --- HARD ---
    GoldInstance("right-sided ECG", "ORDER_ECG_V4R", Difficulty.HARD, "chest_pain",
                 hard_negatives=["ORDER_ECG"],
                 notes="Confusion: standard vs right-sided ECG"),
    GoldInstance("V4R leads", "ORDER_ECG_V4R", Difficulty.HARD, "chest_pain",
                 hard_negatives=["ORDER_ECG"]),
    GoldInstance("troponin I", "ORDER_TROPONIN_I", Difficulty.HARD, "chest_pain",
                 hard_negatives=["ORDER_TROPONIN_T", "ORDER_TROPONIN"]),
    GoldInstance("troponin T", "ORDER_TROPONIN_T", Difficulty.HARD, "chest_pain",
                 hard_negatives=["ORDER_TROPONIN_I", "ORDER_TROPONIN"]),
    GoldInstance("ticagrelor", "GIVE_TICAGRELOR", Difficulty.HARD, "chest_pain",
                 hard_negatives=["GIVE_CLOPIDOGREL", "GIVE_PRASUGREL"]),
    GoldInstance("prasugrel", "GIVE_PRASUGREL", Difficulty.HARD, "chest_pain",
                 hard_negatives=["GIVE_CLOPIDOGREL", "GIVE_TICAGRELOR"]),
    GoldInstance("unfractionated heparin", "GIVE_HEPARIN", Difficulty.HARD, "chest_pain",
                 hard_negatives=["GIVE_ENOXAPARIN"]),
    GoldInstance("LMWH enoxaparin", "GIVE_ENOXAPARIN", Difficulty.HARD, "chest_pain",
                 hard_negatives=["GIVE_HEPARIN"]),
    GoldInstance("metoprolol", "GIVE_METOPROLOL", Difficulty.HARD, "chest_pain",
                 hard_negatives=["GIVE_CARVEDILOL", "GIVE_BETA_BLOCKER"]),

    # --- OOV ---
    GoldInstance("bivalirudin", None, Difficulty.OOV, "chest_pain",
                 notes="Direct thrombin inhibitor not in ontology"),
    GoldInstance("cangrelor", None, Difficulty.OOV, "chest_pain",
                 notes="IV P2Y12 inhibitor"),
    GoldInstance("fondaparinux", None, Difficulty.OOV, "chest_pain",
                 notes="Factor Xa inhibitor"),
    GoldInstance("eptifibatide", None, Difficulty.OOV, "chest_pain",
                 notes="GP IIb/IIIa inhibitor"),
    GoldInstance("IABP", None, Difficulty.OOV, "chest_pain",
                 notes="Intra-aortic balloon pump"),
]


# =============================================================================
# AKI DOMAIN GOLD INSTANCES
# =============================================================================

AKI_GOLD = [
    # --- EASY ---
    GoldInstance("creatinine", "ORDER_CREATININE", Difficulty.EASY, "aki"),
    GoldInstance("order creatinine", "ORDER_CREATININE", Difficulty.EASY, "aki"),
    GoldInstance("BUN", "ORDER_BUN", Difficulty.EASY, "aki"),
    GoldInstance("urinalysis", "ORDER_URINALYSIS", Difficulty.EASY, "aki"),
    GoldInstance("renal ultrasound", "ORDER_RENAL_ULTRASOUND", Difficulty.EASY, "aki"),
    GoldInstance("urine sodium", "ORDER_URINE_SODIUM", Difficulty.EASY, "aki"),
    GoldInstance("start dialysis", "INITIATE_HEMODIALYSIS", Difficulty.EASY, "aki"),
    GoldInstance("furosemide", "GIVE_FUROSEMIDE", Difficulty.EASY, "aki"),
    GoldInstance("potassium", "ORDER_POTASSIUM", Difficulty.EASY, "aki"),
    GoldInstance("magnesium", "ORDER_MAGNESIUM", Difficulty.EASY, "aki"),

    # --- NORMAL ---
    GoldInstance("lasix", "GIVE_FUROSEMIDE", Difficulty.NORMAL, "aki",
                 notes="Brand name"),
    GoldInstance("renal US", "ORDER_RENAL_ULTRASOUND", Difficulty.NORMAL, "aki"),
    GoldInstance("kidney ultrasound", "ORDER_RENAL_ULTRASOUND", Difficulty.NORMAL, "aki"),
    GoldInstance("serum creatinine", "ORDER_CREATININE", Difficulty.NORMAL, "aki"),
    GoldInstance("sCr", "ORDER_CREATININE", Difficulty.NORMAL, "aki"),
    GoldInstance("hemodialysis", "INITIATE_HEMODIALYSIS", Difficulty.NORMAL, "aki"),
    GoldInstance("IV fluids", "GIVE_CRYSTALLOID", Difficulty.NORMAL, "aki"),
    GoldInstance("volume resuscitation", "GIVE_CRYSTALLOID", Difficulty.NORMAL, "aki"),
    GoldInstance("stop nephrotoxins", "STOP_NEPHROTOXINS", Difficulty.NORMAL, "aki"),
    GoldInstance("hold NSAIDs", "STOP_NEPHROTOXINS", Difficulty.NORMAL, "aki"),

    # --- ABBREVIATION ---
    GoldInstance("UA", "ORDER_URINALYSIS", Difficulty.ABBREVIATION, "aki"),
    GoldInstance("FENa", "ORDER_FENA", Difficulty.ABBREVIATION, "aki"),
    GoldInstance("CRRT", "INITIATE_CRRT", Difficulty.ABBREVIATION, "aki"),
    GoldInstance("HD", "INITIATE_HEMODIALYSIS", Difficulty.ABBREVIATION, "aki"),
    GoldInstance("K+", "ORDER_POTASSIUM", Difficulty.ABBREVIATION, "aki"),
    GoldInstance("Mg", "ORDER_MAGNESIUM", Difficulty.ABBREVIATION, "aki"),
    GoldInstance("phos", "ORDER_PHOSPHATE", Difficulty.ABBREVIATION, "aki"),
    GoldInstance("RUS", "ORDER_RENAL_ULTRASOUND", Difficulty.ABBREVIATION, "aki"),

    # --- HARD ---
    GoldInstance("CVVH", "INITIATE_CRRT", Difficulty.HARD, "aki",
                 hard_negatives=["INITIATE_HEMODIALYSIS"],
                 notes="Continuous vs intermittent dialysis"),
    GoldInstance("CVVHD", "INITIATE_CRRT", Difficulty.HARD, "aki",
                 hard_negatives=["INITIATE_HEMODIALYSIS"]),
    GoldInstance("intermittent HD", "INITIATE_HEMODIALYSIS", Difficulty.HARD, "aki",
                 hard_negatives=["INITIATE_CRRT"]),
    GoldInstance("fractional excretion sodium", "ORDER_FENA", Difficulty.HARD, "aki",
                 hard_negatives=["ORDER_URINE_SODIUM"]),
    GoldInstance("urine electrolytes", "ORDER_URINE_SODIUM", Difficulty.HARD, "aki",
                 hard_negatives=["ORDER_FENA"]),
    GoldInstance("cystatin C", "ORDER_CYSTATIN_C", Difficulty.HARD, "aki",
                 hard_negatives=["ORDER_CREATININE"],
                 notes="Different renal biomarker"),

    # --- OOV ---
    GoldInstance("NGAL", None, Difficulty.OOV, "aki",
                 notes="Neutrophil gelatinase-associated lipocalin"),
    GoldInstance("KIM-1", None, Difficulty.OOV, "aki",
                 notes="Kidney injury molecule-1"),
    GoldInstance("peritoneal dialysis", None, Difficulty.OOV, "aki",
                 notes="Not in ontology"),
    GoldInstance("renal biopsy", None, Difficulty.OOV, "aki",
                 notes="Diagnostic procedure"),
]


# =============================================================================
# DKA DOMAIN GOLD INSTANCES
# =============================================================================

DKA_GOLD = [
    # --- EASY ---
    GoldInstance("insulin drip", "GIVE_INSULIN_REGULAR", Difficulty.EASY, "dka"),
    GoldInstance("regular insulin", "GIVE_INSULIN_REGULAR", Difficulty.EASY, "dka"),
    GoldInstance("glucose", "ORDER_GLUCOSE", Difficulty.EASY, "dka"),
    GoldInstance("blood glucose", "ORDER_GLUCOSE", Difficulty.EASY, "dka"),
    GoldInstance("potassium chloride", "GIVE_POTASSIUM_CHLORIDE", Difficulty.EASY, "dka"),
    GoldInstance("sodium bicarbonate", "GIVE_SODIUM_BICARBONATE", Difficulty.EASY, "dka"),
    GoldInstance("ABG", "ORDER_ABG", Difficulty.EASY, "dka"),
    GoldInstance("anion gap", "ORDER_ANION_GAP", Difficulty.EASY, "dka"),
    GoldInstance("beta hydroxybutyrate", "ORDER_BETA_HYDROXYBUTYRATE", Difficulty.EASY, "dka"),
    GoldInstance("phosphate", "ORDER_PHOSPHATE", Difficulty.EASY, "dka"),

    # --- NORMAL ---
    GoldInstance("IV insulin", "GIVE_INSULIN_REGULAR", Difficulty.NORMAL, "dka"),
    GoldInstance("insulin infusion", "GIVE_INSULIN_REGULAR", Difficulty.NORMAL, "dka"),
    GoldInstance("fingerstick glucose", "ORDER_GLUCOSE", Difficulty.NORMAL, "dka"),
    GoldInstance("POC glucose", "ORDER_GLUCOSE", Difficulty.NORMAL, "dka"),
    GoldInstance("KCl", "GIVE_POTASSIUM_CHLORIDE", Difficulty.NORMAL, "dka"),
    GoldInstance("bicarb", "GIVE_SODIUM_BICARBONATE", Difficulty.NORMAL, "dka"),
    GoldInstance("NaHCO3", "GIVE_SODIUM_BICARBONATE", Difficulty.NORMAL, "dka"),
    GoldInstance("fluid bolus", "GIVE_CRYSTALLOID", Difficulty.NORMAL, "dka"),
    GoldInstance("aggressive hydration", "GIVE_CRYSTALLOID", Difficulty.NORMAL, "dka"),

    # --- ABBREVIATION ---
    GoldInstance("BG", "ORDER_GLUCOSE", Difficulty.ABBREVIATION, "dka"),
    GoldInstance("FSG", "ORDER_GLUCOSE", Difficulty.ABBREVIATION, "dka"),
    GoldInstance("BOHB", "ORDER_BETA_HYDROXYBUTYRATE", Difficulty.ABBREVIATION, "dka"),
    GoldInstance("AG", "ORDER_ANION_GAP", Difficulty.ABBREVIATION, "dka"),
    GoldInstance("VBG", "ORDER_VBG", Difficulty.ABBREVIATION, "dka"),
    GoldInstance("K", "ORDER_POTASSIUM", Difficulty.ABBREVIATION, "dka"),

    # --- HARD ---
    GoldInstance("venous blood gas", "ORDER_VBG", Difficulty.HARD, "dka",
                 hard_negatives=["ORDER_ABG"],
                 notes="Arterial vs venous blood gas"),
    GoldInstance("arterial blood gas", "ORDER_ABG", Difficulty.HARD, "dka",
                 hard_negatives=["ORDER_VBG"]),
    GoldInstance("ketones", "ORDER_BETA_HYDROXYBUTYRATE", Difficulty.HARD, "dka",
                 hard_negatives=["ORDER_URINE_KETONES"],
                 notes="Serum vs urine ketones"),
    GoldInstance("serum ketones", "ORDER_BETA_HYDROXYBUTYRATE", Difficulty.HARD, "dka",
                 hard_negatives=["ORDER_URINE_KETONES"]),
    GoldInstance("potassium replacement", "GIVE_POTASSIUM_CHLORIDE", Difficulty.HARD, "dka",
                 hard_negatives=["ORDER_POTASSIUM"]),

    # --- OOV ---
    GoldInstance("insulin glargine", None, Difficulty.OOV, "dka",
                 notes="Long-acting insulin, not for DKA acute management"),
    GoldInstance("detemir", None, Difficulty.OOV, "dka"),
    GoldInstance("SGLT2 inhibitor", None, Difficulty.OOV, "dka",
                 notes="Should be held in DKA"),
]


# =============================================================================
# STROKE DOMAIN GOLD INSTANCES
# =============================================================================

STROKE_GOLD = [
    # --- EASY ---
    GoldInstance("CT head", "ORDER_CT_HEAD", Difficulty.EASY, "stroke"),
    GoldInstance("head CT", "ORDER_CT_HEAD", Difficulty.EASY, "stroke"),
    GoldInstance("alteplase", "GIVE_ALTEPLASE", Difficulty.EASY, "stroke"),
    GoldInstance("tPA", "GIVE_ALTEPLASE", Difficulty.EASY, "stroke"),
    GoldInstance("thrombectomy", "PERFORM_MECHANICAL_THROMBECTOMY", Difficulty.EASY, "stroke"),
    GoldInstance("labetalol", "GIVE_LABETALOL", Difficulty.EASY, "stroke"),
    GoldInstance("nicardipine", "GIVE_NICARDIPINE", Difficulty.EASY, "stroke"),
    GoldInstance("MRI brain", "ORDER_MRI_BRAIN", Difficulty.EASY, "stroke"),
    GoldInstance("CTA head neck", "ORDER_CTA_HEAD_NECK", Difficulty.EASY, "stroke"),
    GoldInstance("NIHSS", "ASSESS_NIHSS", Difficulty.EASY, "stroke"),

    # --- NORMAL ---
    GoldInstance("tissue plasminogen activator", "GIVE_ALTEPLASE", Difficulty.NORMAL, "stroke"),
    GoldInstance("thrombolytics", "GIVE_ALTEPLASE", Difficulty.NORMAL, "stroke"),
    GoldInstance("mechanical thrombectomy", "PERFORM_MECHANICAL_THROMBECTOMY", Difficulty.NORMAL, "stroke"),
    GoldInstance("CT angiogram", "ORDER_CTA_HEAD_NECK", Difficulty.NORMAL, "stroke"),
    GoldInstance("CT perfusion", "ORDER_CT_PERFUSION", Difficulty.NORMAL, "stroke"),
    GoldInstance("blood pressure control", "CONTROL_BLOOD_PRESSURE", Difficulty.NORMAL, "stroke"),
    GoldInstance("BP management", "CONTROL_BLOOD_PRESSURE", Difficulty.NORMAL, "stroke"),
    GoldInstance("cardene", "GIVE_NICARDIPINE", Difficulty.NORMAL, "stroke",
                 notes="Brand name"),

    # --- ABBREVIATION ---
    GoldInstance("NCCT", "ORDER_CT_HEAD_NON_CONTRAST", Difficulty.ABBREVIATION, "stroke",
                 notes="Non-contrast CT"),
    GoldInstance("CTP", "ORDER_CT_PERFUSION", Difficulty.ABBREVIATION, "stroke"),
    GoldInstance("MRA", "ORDER_MRA_HEAD", Difficulty.ABBREVIATION, "stroke"),
    GoldInstance("DWI", "ORDER_MRI_BRAIN", Difficulty.ABBREVIATION, "stroke",
                 notes="Diffusion-weighted imaging"),
    GoldInstance("MT", "PERFORM_MECHANICAL_THROMBECTOMY", Difficulty.ABBREVIATION, "stroke"),
    GoldInstance("EVT", "PERFORM_MECHANICAL_THROMBECTOMY", Difficulty.ABBREVIATION, "stroke",
                 notes="Endovascular therapy"),

    # --- HARD ---
    GoldInstance("non-contrast CT head", "ORDER_CT_HEAD_NON_CONTRAST", Difficulty.HARD, "stroke",
                 hard_negatives=["ORDER_CT_HEAD", "ORDER_CTA_HEAD_NECK"]),
    GoldInstance("CT with contrast", "ORDER_CTA_HEAD_NECK", Difficulty.HARD, "stroke",
                 hard_negatives=["ORDER_CT_HEAD_NON_CONTRAST"]),
    GoldInstance("MRI perfusion", "ORDER_MRI_BRAIN_PERFUSION", Difficulty.HARD, "stroke",
                 hard_negatives=["ORDER_MRI_BRAIN", "ORDER_CT_PERFUSION"]),
    GoldInstance("IV tPA", "GIVE_ALTEPLASE", Difficulty.HARD, "stroke",
                 hard_negatives=["GIVE_TENECTEPLASE"],
                 notes="IV vs intra-arterial"),
    GoldInstance("tenecteplase", "GIVE_TENECTEPLASE", Difficulty.HARD, "stroke",
                 hard_negatives=["GIVE_ALTEPLASE"]),

    # --- OOV ---
    GoldInstance("decompressive craniectomy", None, Difficulty.OOV, "stroke",
                 notes="Surgical intervention"),
    GoldInstance("intra-arterial tPA", None, Difficulty.OOV, "stroke",
                 notes="Not in current ontology"),
    GoldInstance("stent retriever", None, Difficulty.OOV, "stroke",
                 notes="Device for thrombectomy"),
    GoldInstance("osmotic therapy", None, Difficulty.OOV, "stroke",
                 notes="Mannitol/hypertonic saline for edema"),
]


# =============================================================================
# HEART FAILURE DOMAIN GOLD INSTANCES
# =============================================================================

HEART_FAILURE_GOLD = [
    # --- EASY ---
    GoldInstance("furosemide", "GIVE_FUROSEMIDE", Difficulty.EASY, "heart_failure"),
    GoldInstance("lisinopril", "GIVE_LISINOPRIL", Difficulty.EASY, "heart_failure"),
    GoldInstance("carvedilol", "GIVE_CARVEDILOL", Difficulty.EASY, "heart_failure"),
    GoldInstance("spironolactone", "GIVE_SPIRONOLACTONE", Difficulty.EASY, "heart_failure"),
    GoldInstance("echocardiogram", "ORDER_ECHOCARDIOGRAM", Difficulty.EASY, "heart_failure"),
    GoldInstance("BNP", "ORDER_BNP", Difficulty.EASY, "heart_failure"),
    GoldInstance("chest x-ray", "ORDER_CHEST_XRAY", Difficulty.EASY, "heart_failure"),
    GoldInstance("diuretics", "GIVE_FUROSEMIDE", Difficulty.EASY, "heart_failure"),
    GoldInstance("metoprolol", "GIVE_METOPROLOL", Difficulty.EASY, "heart_failure"),
    GoldInstance("losartan", "GIVE_LOSARTAN", Difficulty.EASY, "heart_failure"),

    # --- NORMAL ---
    GoldInstance("lasix", "GIVE_FUROSEMIDE", Difficulty.NORMAL, "heart_failure"),
    GoldInstance("coreg", "GIVE_CARVEDILOL", Difficulty.NORMAL, "heart_failure",
                 notes="Brand name"),
    GoldInstance("aldactone", "GIVE_SPIRONOLACTONE", Difficulty.NORMAL, "heart_failure"),
    GoldInstance("entresto", "GIVE_SACUBITRIL_VALSARTAN", Difficulty.NORMAL, "heart_failure",
                 notes="Brand name for sacubitril/valsartan"),
    GoldInstance("ARNI", "GIVE_SACUBITRIL_VALSARTAN", Difficulty.NORMAL, "heart_failure"),
    GoldInstance("jardiance", "GIVE_EMPAGLIFLOZIN", Difficulty.NORMAL, "heart_failure"),
    GoldInstance("farxiga", "GIVE_DAPAGLIFLOZIN", Difficulty.NORMAL, "heart_failure"),
    GoldInstance("IV diuresis", "GIVE_FUROSEMIDE", Difficulty.NORMAL, "heart_failure"),
    GoldInstance("lopressor", "GIVE_METOPROLOL", Difficulty.NORMAL, "heart_failure"),
    GoldInstance("cozaar", "GIVE_LOSARTAN", Difficulty.NORMAL, "heart_failure"),

    # --- ABBREVIATION ---
    GoldInstance("ACEi", "GIVE_LISINOPRIL", Difficulty.ABBREVIATION, "heart_failure"),
    GoldInstance("ARB", "GIVE_LOSARTAN", Difficulty.ABBREVIATION, "heart_failure"),
    GoldInstance("BB", "GIVE_CARVEDILOL", Difficulty.ABBREVIATION, "heart_failure"),
    GoldInstance("MRA", "GIVE_SPIRONOLACTONE", Difficulty.ABBREVIATION, "heart_failure",
                 notes="Mineralocorticoid receptor antagonist"),
    GoldInstance("SGLT2i", "GIVE_EMPAGLIFLOZIN", Difficulty.ABBREVIATION, "heart_failure"),
    GoldInstance("TTE", "ORDER_ECHOCARDIOGRAM", Difficulty.ABBREVIATION, "heart_failure",
                 notes="Transthoracic echocardiogram"),
    GoldInstance("TEE", "ORDER_TEE", Difficulty.ABBREVIATION, "heart_failure",
                 notes="Transesophageal echocardiogram"),

    # --- HARD ---
    GoldInstance("sacubitril valsartan", "GIVE_SACUBITRIL_VALSARTAN", Difficulty.HARD, "heart_failure",
                 hard_negatives=["GIVE_LOSARTAN", "GIVE_LISINOPRIL"]),
    GoldInstance("empagliflozin", "GIVE_EMPAGLIFLOZIN", Difficulty.HARD, "heart_failure",
                 hard_negatives=["GIVE_DAPAGLIFLOZIN"]),
    GoldInstance("dapagliflozin", "GIVE_DAPAGLIFLOZIN", Difficulty.HARD, "heart_failure",
                 hard_negatives=["GIVE_EMPAGLIFLOZIN"]),
    GoldInstance("transthoracic echo", "ORDER_ECHOCARDIOGRAM", Difficulty.HARD, "heart_failure",
                 hard_negatives=["ORDER_TEE"]),
    GoldInstance("transesophageal echo", "ORDER_TEE", Difficulty.HARD, "heart_failure",
                 hard_negatives=["ORDER_ECHOCARDIOGRAM"]),
    GoldInstance("metoprolol succinate", "GIVE_METOPROLOL", Difficulty.HARD, "heart_failure",
                 hard_negatives=["GIVE_CARVEDILOL"],
                 notes="Different beta-blocker formulation"),

    # --- OOV ---
    GoldInstance("ivabradine", None, Difficulty.OOV, "heart_failure",
                 notes="If-channel blocker"),
    GoldInstance("hydralazine nitrate", None, Difficulty.OOV, "heart_failure",
                 notes="H-ISDN combination"),
    GoldInstance("milrinone", None, Difficulty.OOV, "heart_failure",
                 notes="Inotrope"),
    GoldInstance("dobutamine", None, Difficulty.OOV, "heart_failure",
                 notes="Inotrope"),
    GoldInstance("LVAD", None, Difficulty.OOV, "heart_failure",
                 notes="Left ventricular assist device"),
]


# =============================================================================
# CROSS-DOMAIN / UNIVERSAL GOLD INSTANCES
# =============================================================================

UNIVERSAL_GOLD = [
    # --- Vital signs ---
    GoldInstance("check vitals", "ASSESS_VITAL_SIGNS", Difficulty.EASY, "universal"),
    GoldInstance("vital signs", "ASSESS_VITAL_SIGNS", Difficulty.EASY, "universal"),
    GoldInstance("blood pressure", "MEASURE_BLOOD_PRESSURE", Difficulty.EASY, "universal"),
    GoldInstance("BP check", "MEASURE_BLOOD_PRESSURE", Difficulty.EASY, "universal"),
    GoldInstance("oxygen saturation", "MEASURE_OXYGEN_SATURATION", Difficulty.EASY, "universal"),
    GoldInstance("SpO2", "MEASURE_OXYGEN_SATURATION", Difficulty.ABBREVIATION, "universal"),
    GoldInstance("pulse ox", "MEASURE_OXYGEN_SATURATION", Difficulty.NORMAL, "universal"),
    GoldInstance("temperature", "MEASURE_TEMPERATURE", Difficulty.EASY, "universal"),
    GoldInstance("temp", "MEASURE_TEMPERATURE", Difficulty.ABBREVIATION, "universal"),

    # --- Common procedures ---
    GoldInstance("intubation", "PERFORM_INTUBATION", Difficulty.EASY, "universal"),
    GoldInstance("ETT", "PERFORM_INTUBATION", Difficulty.ABBREVIATION, "universal"),
    GoldInstance("central line", "PLACE_CENTRAL_LINE", Difficulty.EASY, "universal"),
    GoldInstance("arterial line", "PLACE_ARTERIAL_LINE", Difficulty.EASY, "universal"),
    GoldInstance("a-line", "PLACE_ARTERIAL_LINE", Difficulty.ABBREVIATION, "universal"),
    GoldInstance("Foley catheter", "PLACE_FOLEY_CATHETER", Difficulty.EASY, "universal"),
    GoldInstance("NG tube", "PLACE_NG_TUBE", Difficulty.ABBREVIATION, "universal"),

    # --- Pain management ---
    GoldInstance("morphine", "GIVE_MORPHINE", Difficulty.EASY, "universal"),
    GoldInstance("fentanyl", "GIVE_FENTANYL", Difficulty.EASY, "universal"),
    GoldInstance("pain medication", "GIVE_ANALGESIC", Difficulty.NORMAL, "universal"),
    GoldInstance("analgesia", "GIVE_ANALGESIC", Difficulty.NORMAL, "universal"),

    # --- Consults ---
    GoldInstance("cardiology consult", "CONSULT_CARDIOLOGY", Difficulty.EASY, "universal"),
    GoldInstance("nephrology consult", "CONSULT_NEPHROLOGY", Difficulty.EASY, "universal"),
    GoldInstance("neurology consult", "CONSULT_NEUROLOGY", Difficulty.EASY, "universal"),
    GoldInstance("ICU consult", "CONSULT_ICU", Difficulty.EASY, "universal"),
    GoldInstance("call cards", "CONSULT_CARDIOLOGY", Difficulty.ABBREVIATION, "universal"),
    GoldInstance("call renal", "CONSULT_NEPHROLOGY", Difficulty.ABBREVIATION, "universal"),
]


# =============================================================================
# ADDITIONAL HARD NEGATIVES (Sibling/Nearby Concept Confusion)
# Target: Reach 30% of total instances
# =============================================================================

ADDITIONAL_HARD = [
    # --- Medication Confusion (similar drug classes) ---
    GoldInstance("phenylephrine", "START_VASOPRESSOR_PHENYLEPHRINE", Difficulty.HARD, "sepsis",
                 hard_negatives=["START_VASOPRESSOR_NOREPINEPHRINE", "START_VASOPRESSOR_EPINEPHRINE"]),
    GoldInstance("neo", "START_VASOPRESSOR_PHENYLEPHRINE", Difficulty.HARD, "sepsis",
                 hard_negatives=["START_VASOPRESSOR_NOREPINEPHRINE"],
                 notes="Neo-Synephrine brand name"),
    GoldInstance("azithromycin", "GIVE_AZITHROMYCIN", Difficulty.HARD, "sepsis",
                 hard_negatives=["GIVE_LEVOFLOXACIN", "GIVE_CEFTRIAXONE"]),
    GoldInstance("levofloxacin", "GIVE_LEVOFLOXACIN", Difficulty.HARD, "sepsis",
                 hard_negatives=["GIVE_AZITHROMYCIN", "GIVE_MEROPENEM"]),
    GoldInstance("levaquin", "GIVE_LEVOFLOXACIN", Difficulty.HARD, "sepsis",
                 hard_negatives=["GIVE_AZITHROMYCIN"],
                 notes="Brand name"),

    # --- Lab Test Confusion ---
    GoldInstance("serum osmolality", "ORDER_SERUM_OSMOLALITY", Difficulty.HARD, "dka",
                 hard_negatives=["ORDER_URINE_OSMOLALITY"]),
    GoldInstance("urine osmolality", "ORDER_URINE_OSMOLALITY", Difficulty.HARD, "aki",
                 hard_negatives=["ORDER_SERUM_OSMOLALITY"]),
    GoldInstance("serum sodium", "ORDER_SODIUM", Difficulty.HARD, "dka",
                 hard_negatives=["ORDER_URINE_SODIUM"]),
    GoldInstance("urine protein", "ORDER_URINE_PROTEIN", Difficulty.HARD, "aki",
                 hard_negatives=["ORDER_URINALYSIS"]),
    GoldInstance("blood gas arterial", "ORDER_ABG", Difficulty.HARD, "dka",
                 hard_negatives=["ORDER_VBG"]),
    GoldInstance("blood gas venous", "ORDER_VBG", Difficulty.HARD, "dka",
                 hard_negatives=["ORDER_ABG"]),
    GoldInstance("hemoglobin", "ORDER_HEMOGLOBIN", Difficulty.HARD, "universal",
                 hard_negatives=["ORDER_HEMATOCRIT", "ORDER_CBC"]),
    GoldInstance("hematocrit", "ORDER_HEMATOCRIT", Difficulty.HARD, "universal",
                 hard_negatives=["ORDER_HEMOGLOBIN", "ORDER_CBC"]),

    # --- Imaging Confusion ---
    GoldInstance("CT angiography chest", "ORDER_CT_CHEST_PE_PROTOCOL", Difficulty.HARD, "chest_pain",
                 hard_negatives=["ORDER_CT_CHEST", "ORDER_CTA_HEAD_NECK"]),
    GoldInstance("CT pulmonary angiogram", "ORDER_CT_CHEST_PE_PROTOCOL", Difficulty.HARD, "chest_pain",
                 hard_negatives=["ORDER_CT_CHEST"]),
    GoldInstance("portable chest xray", "ORDER_CHEST_XRAY", Difficulty.HARD, "universal",
                 hard_negatives=["ORDER_CT_CHEST"]),
    GoldInstance("CT without contrast", "ORDER_CT_HEAD_NON_CONTRAST", Difficulty.HARD, "stroke",
                 hard_negatives=["ORDER_CTA_HEAD_NECK"]),
    GoldInstance("MR angiography", "ORDER_MRA_HEAD", Difficulty.HARD, "stroke",
                 hard_negatives=["ORDER_MRI_BRAIN", "ORDER_CTA_HEAD_NECK"]),
    GoldInstance("MR perfusion", "ORDER_MRI_BRAIN_PERFUSION", Difficulty.HARD, "stroke",
                 hard_negatives=["ORDER_MRI_BRAIN", "ORDER_CT_PERFUSION"]),

    # --- Procedure Confusion ---
    GoldInstance("emergent dialysis", "INITIATE_HEMODIALYSIS", Difficulty.HARD, "aki",
                 hard_negatives=["INITIATE_CRRT"]),
    GoldInstance("continuous dialysis", "INITIATE_CRRT", Difficulty.HARD, "aki",
                 hard_negatives=["INITIATE_HEMODIALYSIS"]),
    GoldInstance("endovascular intervention", "PERFORM_MECHANICAL_THROMBECTOMY", Difficulty.HARD, "stroke",
                 hard_negatives=["ACTIVATE_CATH_LAB"]),
    GoldInstance("coronary angiography", "ORDER_CARDIAC_CATH", Difficulty.HARD, "chest_pain",
                 hard_negatives=["ACTIVATE_CATH_LAB", "ORDER_CTA_HEAD_NECK"]),
    GoldInstance("PCI", "ACTIVATE_CATH_LAB", Difficulty.HARD, "chest_pain",
                 hard_negatives=["ORDER_CARDIAC_CATH"],
                 notes="Percutaneous coronary intervention"),

    # --- Heart Failure Medication Confusion ---
    GoldInstance("enalapril", "GIVE_ENALAPRIL", Difficulty.HARD, "heart_failure",
                 hard_negatives=["GIVE_LISINOPRIL", "GIVE_LOSARTAN"]),
    GoldInstance("valsartan", "GIVE_VALSARTAN", Difficulty.HARD, "heart_failure",
                 hard_negatives=["GIVE_LOSARTAN", "GIVE_SACUBITRIL_VALSARTAN"]),
    GoldInstance("bisoprolol", "GIVE_BISOPROLOL", Difficulty.HARD, "heart_failure",
                 hard_negatives=["GIVE_METOPROLOL", "GIVE_CARVEDILOL"]),
    GoldInstance("eplerenone", "GIVE_EPLERENONE", Difficulty.HARD, "heart_failure",
                 hard_negatives=["GIVE_SPIRONOLACTONE"]),
    GoldInstance("bumetanide", "GIVE_BUMETANIDE", Difficulty.HARD, "heart_failure",
                 hard_negatives=["GIVE_FUROSEMIDE"]),
    GoldInstance("bumex", "GIVE_BUMETANIDE", Difficulty.HARD, "heart_failure",
                 hard_negatives=["GIVE_FUROSEMIDE"],
                 notes="Brand name"),
    GoldInstance("torsemide", "GIVE_TORSEMIDE", Difficulty.HARD, "heart_failure",
                 hard_negatives=["GIVE_FUROSEMIDE", "GIVE_BUMETANIDE"]),

    # --- Anticoagulant Confusion ---
    GoldInstance("warfarin", "GIVE_WARFARIN", Difficulty.HARD, "chest_pain",
                 hard_negatives=["GIVE_HEPARIN", "GIVE_ENOXAPARIN"]),
    GoldInstance("coumadin", "GIVE_WARFARIN", Difficulty.HARD, "chest_pain",
                 hard_negatives=["GIVE_HEPARIN"],
                 notes="Brand name"),
    GoldInstance("apixaban", "GIVE_APIXABAN", Difficulty.HARD, "stroke",
                 hard_negatives=["GIVE_RIVAROXABAN", "GIVE_WARFARIN"]),
    GoldInstance("eliquis", "GIVE_APIXABAN", Difficulty.HARD, "stroke",
                 hard_negatives=["GIVE_RIVAROXABAN"],
                 notes="Brand name"),
    GoldInstance("rivaroxaban", "GIVE_RIVAROXABAN", Difficulty.HARD, "stroke",
                 hard_negatives=["GIVE_APIXABAN", "GIVE_WARFARIN"]),
    GoldInstance("xarelto", "GIVE_RIVAROXABAN", Difficulty.HARD, "stroke",
                 hard_negatives=["GIVE_APIXABAN"],
                 notes="Brand name"),
    GoldInstance("dabigatran", "GIVE_DABIGATRAN", Difficulty.HARD, "stroke",
                 hard_negatives=["GIVE_APIXABAN", "GIVE_RIVAROXABAN"]),
    GoldInstance("pradaxa", "GIVE_DABIGATRAN", Difficulty.HARD, "stroke",
                 hard_negatives=["GIVE_APIXABAN"],
                 notes="Brand name"),

    # --- Insulin Confusion ---
    GoldInstance("insulin lispro", "GIVE_INSULIN_LISPRO", Difficulty.HARD, "dka",
                 hard_negatives=["GIVE_INSULIN_REGULAR", "GIVE_INSULIN_ASPART"]),
    GoldInstance("humalog", "GIVE_INSULIN_LISPRO", Difficulty.HARD, "dka",
                 hard_negatives=["GIVE_INSULIN_REGULAR"],
                 notes="Brand name"),
    GoldInstance("insulin aspart", "GIVE_INSULIN_ASPART", Difficulty.HARD, "dka",
                 hard_negatives=["GIVE_INSULIN_REGULAR", "GIVE_INSULIN_LISPRO"]),
    GoldInstance("novolog", "GIVE_INSULIN_ASPART", Difficulty.HARD, "dka",
                 hard_negatives=["GIVE_INSULIN_LISPRO"],
                 notes="Brand name"),

    # --- Sedation/Analgesia Confusion ---
    GoldInstance("propofol", "GIVE_PROPOFOL", Difficulty.HARD, "universal",
                 hard_negatives=["GIVE_MIDAZOLAM", "GIVE_FENTANYL"]),
    GoldInstance("midazolam", "GIVE_MIDAZOLAM", Difficulty.HARD, "universal",
                 hard_negatives=["GIVE_PROPOFOL", "GIVE_LORAZEPAM"]),
    GoldInstance("versed", "GIVE_MIDAZOLAM", Difficulty.HARD, "universal",
                 hard_negatives=["GIVE_PROPOFOL"],
                 notes="Brand name"),
    GoldInstance("lorazepam", "GIVE_LORAZEPAM", Difficulty.HARD, "universal",
                 hard_negatives=["GIVE_MIDAZOLAM", "GIVE_DIAZEPAM"]),
    GoldInstance("ativan", "GIVE_LORAZEPAM", Difficulty.HARD, "universal",
                 hard_negatives=["GIVE_MIDAZOLAM"],
                 notes="Brand name"),
    GoldInstance("hydromorphone", "GIVE_HYDROMORPHONE", Difficulty.HARD, "universal",
                 hard_negatives=["GIVE_MORPHINE", "GIVE_FENTANYL"]),
    GoldInstance("dilaudid", "GIVE_HYDROMORPHONE", Difficulty.HARD, "universal",
                 hard_negatives=["GIVE_MORPHINE"],
                 notes="Brand name"),
]


# =============================================================================
# ADDITIONAL OOV INSTANCES (Out-of-Vocabulary)
# Target: Reach 20% of total instances
# =============================================================================

ADDITIONAL_OOV = [
    # --- Rare/Experimental Treatments ---
    GoldInstance("levosimendan", None, Difficulty.OOV, "heart_failure",
                 notes="Inodilator not available in US"),
    GoldInstance("tolvaptan", None, Difficulty.OOV, "heart_failure",
                 notes="Vasopressin antagonist"),
    GoldInstance("angiotensin II", None, Difficulty.OOV, "sepsis",
                 notes="Giapreza - vasopressor"),
    GoldInstance("methylene blue", None, Difficulty.OOV, "sepsis",
                 notes="Refractory vasodilatory shock"),
    GoldInstance("vitamin C protocol", None, Difficulty.OOV, "sepsis",
                 notes="HAT therapy - controversial"),
    GoldInstance("thiamine", None, Difficulty.OOV, "sepsis",
                 notes="Part of metabolic resuscitation"),
    GoldInstance("hydrocortisone", None, Difficulty.OOV, "sepsis",
                 notes="Stress-dose steroids"),
    GoldInstance("antithrombin III", None, Difficulty.OOV, "sepsis",
                 notes="Experimental for DIC"),

    # --- Specialized Procedures ---
    GoldInstance("Impella", None, Difficulty.OOV, "chest_pain",
                 notes="Mechanical circulatory support"),
    GoldInstance("TandemHeart", None, Difficulty.OOV, "chest_pain",
                 notes="Percutaneous VAD"),
    GoldInstance("VA-ECMO", None, Difficulty.OOV, "chest_pain",
                 notes="Veno-arterial ECMO"),
    GoldInstance("VV-ECMO", None, Difficulty.OOV, "sepsis",
                 notes="Veno-venous ECMO for ARDS"),
    GoldInstance("proning", None, Difficulty.OOV, "sepsis",
                 notes="Prone positioning for ARDS"),
    GoldInstance("neuromuscular blockade", None, Difficulty.OOV, "sepsis",
                 notes="Paralysis for ARDS"),
    GoldInstance("inhaled nitric oxide", None, Difficulty.OOV, "sepsis",
                 notes="Pulmonary vasodilator"),
    GoldInstance("inhaled epoprostenol", None, Difficulty.OOV, "sepsis",
                 notes="Inhaled prostacyclin"),

    # --- Rare Labs/Tests ---
    GoldInstance("presepsin", None, Difficulty.OOV, "sepsis",
                 notes="Novel sepsis biomarker"),
    GoldInstance("mid-regional pro-adrenomedullin", None, Difficulty.OOV, "sepsis",
                 notes="MR-proADM biomarker"),
    GoldInstance("sTREM-1", None, Difficulty.OOV, "sepsis",
                 notes="Soluble triggering receptor"),
    GoldInstance("suPAR", None, Difficulty.OOV, "sepsis",
                 notes="Soluble urokinase plasminogen activator receptor"),
    GoldInstance("GDF-15", None, Difficulty.OOV, "heart_failure",
                 notes="Growth differentiation factor 15"),
    GoldInstance("sST2", None, Difficulty.OOV, "heart_failure",
                 notes="Soluble ST2 biomarker"),
    GoldInstance("galectin-3", None, Difficulty.OOV, "heart_failure",
                 notes="Fibrosis biomarker"),

    # --- Specialty Consults Not in Ontology ---
    GoldInstance("ECMO consult", None, Difficulty.OOV, "universal",
                 notes="Specialized ECMO team"),
    GoldInstance("palliative care consult", None, Difficulty.OOV, "universal",
                 notes="Goals of care discussion"),
    GoldInstance("ethics consult", None, Difficulty.OOV, "universal",
                 notes="Medical ethics consultation"),
    GoldInstance("toxicology consult", None, Difficulty.OOV, "universal",
                 notes="Poison control"),
    GoldInstance("infectious disease consult", None, Difficulty.OOV, "sepsis",
                 notes="ID specialist"),
    GoldInstance("transplant evaluation", None, Difficulty.OOV, "heart_failure",
                 notes="Heart transplant workup"),

    # --- Miscellaneous ---
    GoldInstance("recombinant activated protein C", None, Difficulty.OOV, "sepsis",
                 notes="Xigris - withdrawn from market"),
    GoldInstance("polymyxin E", None, Difficulty.OOV, "sepsis",
                 notes="Colistin - last-resort antibiotic"),
    GoldInstance("drotrecogin alfa", None, Difficulty.OOV, "sepsis",
                 notes="Former sepsis treatment"),
    GoldInstance("vasoplegic syndrome treatment", None, Difficulty.OOV, "chest_pain",
                 notes="Post-cardiac surgery complication"),
]


# =============================================================================
# GOLD SET V2 AGGREGATION
# =============================================================================

def get_all_gold_instances() -> List[GoldInstance]:
    """Get complete Gold Set v2 with all domains."""
    all_instances = []
    all_instances.extend(SEPSIS_GOLD)
    all_instances.extend(CHEST_PAIN_GOLD)
    all_instances.extend(AKI_GOLD)
    all_instances.extend(DKA_GOLD)
    all_instances.extend(STROKE_GOLD)
    all_instances.extend(HEART_FAILURE_GOLD)
    all_instances.extend(UNIVERSAL_GOLD)
    all_instances.extend(ADDITIONAL_HARD)
    all_instances.extend(ADDITIONAL_OOV)
    return all_instances


def get_difficulty_distribution() -> Dict[str, int]:
    """Get distribution of instances by difficulty."""
    all_instances = get_all_gold_instances()
    distribution = {}
    for difficulty in Difficulty:
        count = sum(1 for i in all_instances if i.difficulty == difficulty)
        distribution[difficulty.value] = count
    distribution["total"] = len(all_instances)
    return distribution


def get_domain_distribution() -> Dict[str, int]:
    """Get distribution of instances by domain."""
    all_instances = get_all_gold_instances()
    distribution = {}
    for instance in all_instances:
        domain = instance.domain
        distribution[domain] = distribution.get(domain, 0) + 1
    distribution["total"] = len(all_instances)
    return distribution


def get_gold_set_stats() -> dict:
    """Get comprehensive statistics for Gold Set v2."""
    all_instances = get_all_gold_instances()
    difficulty_dist = get_difficulty_distribution()
    domain_dist = get_domain_distribution()

    total = len(all_instances)
    hard_count = difficulty_dist.get("hard", 0)
    oov_count = difficulty_dist.get("oov", 0)
    abbrev_count = difficulty_dist.get("abbreviation", 0)

    return {
        "version": "2.0",
        "total_instances": total,
        "difficulty_distribution": difficulty_dist,
        "domain_distribution": domain_dist,
        "target_metrics": {
            "hard_percentage": hard_count / total * 100,
            "oov_percentage": oov_count / total * 100,
            "abbreviation_percentage": abbrev_count / total * 100,
        },
        "hard_negative_count": sum(len(i.hard_negatives) for i in all_instances),
        "domains_covered": len(set(i.domain for i in all_instances)),
    }


def validate_gold_set() -> List[str]:
    """Validate gold set for common issues."""
    issues = []
    all_instances = get_all_gold_instances()

    # Check for duplicates
    queries = [i.query.lower() for i in all_instances]
    duplicates = [q for q in queries if queries.count(q) > 1]
    if duplicates:
        issues.append(f"Duplicate queries found: {set(duplicates)}")

    # Check hard instances have hard_negatives
    for i in all_instances:
        if i.difficulty == Difficulty.HARD and not i.hard_negatives:
            issues.append(f"HARD instance missing hard_negatives: {i.query}")

    # Check OOV instances have None gold_concept_id
    for i in all_instances:
        if i.difficulty == Difficulty.OOV and i.gold_concept_id is not None:
            issues.append(f"OOV instance should have None gold_concept_id: {i.query}")

    return issues


if __name__ == "__main__":
    stats = get_gold_set_stats()
    print("=" * 60)
    print("GOLD SET V2 STATISTICS")
    print("=" * 60)
    print(f"Version: {stats['version']}")
    print(f"Total Instances: {stats['total_instances']}")
    print("-" * 60)
    print("DIFFICULTY DISTRIBUTION:")
    for diff, count in stats['difficulty_distribution'].items():
        if diff != "total":
            pct = count / stats['total_instances'] * 100
            print(f"  {diff:15s}: {count:3d} ({pct:5.1f}%)")
    print("-" * 60)
    print("DOMAIN DISTRIBUTION:")
    for domain, count in stats['domain_distribution'].items():
        if domain != "total":
            pct = count / stats['total_instances'] * 100
            print(f"  {domain:15s}: {count:3d} ({pct:5.1f}%)")
    print("-" * 60)
    print("TARGET METRICS:")
    print(f"  Hard %:         {stats['target_metrics']['hard_percentage']:.1f}% (target: 30%)")
    print(f"  OOV %:          {stats['target_metrics']['oov_percentage']:.1f}% (target: 20%)")
    print(f"  Abbreviation %: {stats['target_metrics']['abbreviation_percentage']:.1f}% (target: 20%)")
    print(f"  Hard Negatives: {stats['hard_negative_count']} total")
    print("=" * 60)

    # Validate
    issues = validate_gold_set()
    if issues:
        print("\nVALIDATION ISSUES:")
        for issue in issues:
            print(f"  - {issue}")
    else:
        print("\nValidation: PASSED")
