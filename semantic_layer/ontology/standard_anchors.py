"""Standard terminology anchors for external KB interoperability.

Rail 1 (NeurIPS D&B Defense): MVP Interoperability via standard anchors.
Enables external KB linkage without full standard system inclusion.

Paper claim: "External KB linkage possible via anchors without full standard system."

References:
- UMLS Metathesaurus: https://www.nlm.nih.gov/research/umls/
- RxNorm: https://www.nlm.nih.gov/research/umls/rxnorm/
- LOINC: https://loinc.org/
- SNOMED CT: https://www.snomed.org/
- ICD-10-CM: https://www.cdc.gov/nchs/icd/icd10cm.htm

Version: 1.0 (2026-01-25)
"""

from typing import Dict, Optional
from dataclasses import dataclass


@dataclass(frozen=True)
class StandardAnchors:
    """External terminology anchors for interoperability.

    Duplicated here to avoid circular imports.
    Canonical definition in concept.py.
    """
    umls_cui: Optional[str] = None
    rxcui: Optional[str] = None
    loinc: Optional[str] = None
    snomed_ct: Optional[str] = None
    icd10: Optional[str] = None

    def has_any_anchor(self) -> bool:
        return any([self.umls_cui, self.rxcui, self.loinc, self.snomed_ct, self.icd10])

    def to_dict(self) -> dict:
        return {k: v for k, v in {
            "UMLS_CUI": self.umls_cui,
            "RxCUI": self.rxcui,
            "LOINC": self.loinc,
            "SNOMED_CT": self.snomed_ct,
            "ICD10": self.icd10,
        }.items() if v is not None}


# =============================================================================
# HIGH-FREQUENCY L1 CONCEPTS - MEDICATIONS (RxNorm/UMLS)
# =============================================================================

MEDICATION_ANCHORS: Dict[str, StandardAnchors] = {
    # --- Vasopressors ---
    "START_VASOPRESSOR_NOREPINEPHRINE": StandardAnchors(
        umls_cui="C0028351",
        rxcui="7512",
        snomed_ct="45555007",  # Norepinephrine (substance)
    ),
    "START_VASOPRESSOR_VASOPRESSIN": StandardAnchors(
        umls_cui="C0003779",
        rxcui="11149",
        snomed_ct="77671006",  # Vasopressin (substance)
    ),
    "START_VASOPRESSOR_DOPAMINE": StandardAnchors(
        umls_cui="C0013030",
        rxcui="3628",
        snomed_ct="59187003",  # Dopamine (substance)
    ),
    "START_VASOPRESSOR_EPINEPHRINE": StandardAnchors(
        umls_cui="C0014563",
        rxcui="3992",
        snomed_ct="387362001",  # Epinephrine (substance)
    ),
    "START_VASOPRESSOR_PHENYLEPHRINE": StandardAnchors(
        umls_cui="C0031469",
        rxcui="8163",
        snomed_ct="372771005",  # Phenylephrine (substance)
    ),

    # --- Antibiotics (Sepsis) ---
    "GIVE_PIPERACILLIN_TAZOBACTAM": StandardAnchors(
        umls_cui="C0724466",
        rxcui="139462",
        snomed_ct="412409003",  # Piperacillin/tazobactam
    ),
    "GIVE_MEROPENEM": StandardAnchors(
        umls_cui="C0066005",
        rxcui="29561",
        snomed_ct="387540000",  # Meropenem
    ),
    "GIVE_VANCOMYCIN": StandardAnchors(
        umls_cui="C0042313",
        rxcui="11124",
        snomed_ct="372725003",  # Vancomycin
    ),
    "GIVE_CEFTRIAXONE": StandardAnchors(
        umls_cui="C0007561",
        rxcui="2193",
        snomed_ct="372670001",  # Ceftriaxone
    ),
    "GIVE_AZITHROMYCIN": StandardAnchors(
        umls_cui="C0052796",
        rxcui="18631",
        snomed_ct="387531004",  # Azithromycin
    ),
    "GIVE_LEVOFLOXACIN": StandardAnchors(
        umls_cui="C0282386",
        rxcui="82122",
        snomed_ct="387552007",  # Levofloxacin
    ),

    # --- ACS Medications (Chest Pain) ---
    "GIVE_ASPIRIN_LOADING": StandardAnchors(
        umls_cui="C0004057",
        rxcui="1191",
        snomed_ct="387458008",  # Aspirin
    ),
    "GIVE_CLOPIDOGREL": StandardAnchors(
        umls_cui="C0070166",
        rxcui="32968",
        snomed_ct="386952008",  # Clopidogrel
    ),
    "GIVE_TICAGRELOR": StandardAnchors(
        umls_cui="C2930455",
        rxcui="1116632",
        snomed_ct="698090000",  # Ticagrelor
    ),
    "GIVE_PRASUGREL": StandardAnchors(
        umls_cui="C1620287",
        rxcui="613391",
        snomed_ct="443129001",  # Prasugrel
    ),
    "GIVE_HEPARIN": StandardAnchors(
        umls_cui="C0019134",
        rxcui="5224",
        snomed_ct="372877000",  # Heparin
    ),
    "GIVE_ENOXAPARIN": StandardAnchors(
        umls_cui="C0206460",
        rxcui="67108",
        snomed_ct="372562003",  # Enoxaparin
    ),
    "GIVE_NITROGLYCERIN": StandardAnchors(
        umls_cui="C0017887",
        rxcui="4917",
        snomed_ct="387404004",  # Nitroglycerin
    ),
    "GIVE_MORPHINE": StandardAnchors(
        umls_cui="C0026549",
        rxcui="7052",
        snomed_ct="373529000",  # Morphine
    ),
    "GIVE_BETA_BLOCKER": StandardAnchors(
        umls_cui="C0001645",
        rxcui="None",  # Class level, no single RxCUI
        snomed_ct="33252009",  # Beta-adrenergic receptor blocking agent
    ),
    "GIVE_METOPROLOL": StandardAnchors(
        umls_cui="C0025859",
        rxcui="6918",
        snomed_ct="372826007",  # Metoprolol
    ),

    # --- Heart Failure Medications ---
    "INITIATE_ACE_OR_ARB_OR_ARNI": StandardAnchors(
        umls_cui="C0003015",  # ACE inhibitor class
        rxcui="None",  # Class level
        snomed_ct="372733002",  # ACE inhibitor
    ),
    "GIVE_LISINOPRIL": StandardAnchors(
        umls_cui="C0065374",
        rxcui="29046",
        snomed_ct="386873009",  # Lisinopril
    ),
    "GIVE_LOSARTAN": StandardAnchors(
        umls_cui="C0126174",
        rxcui="52175",
        snomed_ct="373567002",  # Losartan
    ),
    "GIVE_SACUBITRIL_VALSARTAN": StandardAnchors(
        umls_cui="C4042780",
        rxcui="1656340",
        snomed_ct="716078006",  # Sacubitril/valsartan
    ),
    "INITIATE_BETA_BLOCKER": StandardAnchors(
        umls_cui="C0001645",
        rxcui="None",
        snomed_ct="33252009",  # Beta-blocker class
    ),
    "GIVE_CARVEDILOL": StandardAnchors(
        umls_cui="C0071097",
        rxcui="20352",
        snomed_ct="386870006",  # Carvedilol
    ),
    "GIVE_FUROSEMIDE": StandardAnchors(
        umls_cui="C0016860",
        rxcui="4603",
        snomed_ct="387475002",  # Furosemide
    ),
    "GIVE_SPIRONOLACTONE": StandardAnchors(
        umls_cui="C0037982",
        rxcui="9997",
        snomed_ct="387078006",  # Spironolactone
    ),
    "GIVE_DAPAGLIFLOZIN": StandardAnchors(
        umls_cui="C3266414",
        rxcui="1488564",
        snomed_ct="703677008",  # Dapagliflozin
    ),
    "GIVE_EMPAGLIFLOZIN": StandardAnchors(
        umls_cui="C3495287",
        rxcui="1545653",
        snomed_ct="708896004",  # Empagliflozin
    ),

    # --- DKA Medications ---
    "GIVE_INSULIN_REGULAR": StandardAnchors(
        umls_cui="C0021641",
        rxcui="5856",
        snomed_ct="67866001",  # Regular insulin
    ),
    "GIVE_POTASSIUM_CHLORIDE": StandardAnchors(
        umls_cui="C0032825",
        rxcui="8591",
        snomed_ct="387390002",  # Potassium chloride
    ),
    "GIVE_SODIUM_BICARBONATE": StandardAnchors(
        umls_cui="C0037509",
        rxcui="9863",
        snomed_ct="387319002",  # Sodium bicarbonate
    ),

    # --- Stroke Medications ---
    "GIVE_ALTEPLASE": StandardAnchors(
        umls_cui="C0002422",
        rxcui="8410",
        snomed_ct="387152000",  # Alteplase
    ),
    "GIVE_LABETALOL": StandardAnchors(
        umls_cui="C0022860",
        rxcui="6135",
        snomed_ct="372749000",  # Labetalol
    ),
    "GIVE_NICARDIPINE": StandardAnchors(
        umls_cui="C0028005",
        rxcui="7396",
        snomed_ct="372499000",  # Nicardipine
    ),

    # --- Fluids ---
    "GIVE_CRYSTALLOID": StandardAnchors(
        umls_cui="C0022615",
        rxcui="None",  # Class level
        snomed_ct="346437000",  # Crystalloid solution
    ),
    "GIVE_NORMAL_SALINE": StandardAnchors(
        umls_cui="C0445115",
        rxcui="313002",
        snomed_ct="387390002",  # Sodium chloride 0.9%
    ),
    "GIVE_LACTATED_RINGERS": StandardAnchors(
        umls_cui="C0073385",
        rxcui="8537",
        snomed_ct="346463005",  # Lactated Ringer's
    ),
}


# =============================================================================
# HIGH-FREQUENCY L1 CONCEPTS - LABORATORY TESTS (LOINC/UMLS)
# =============================================================================

LAB_ANCHORS: Dict[str, StandardAnchors] = {
    # --- Sepsis Labs ---
    "ORDER_LACTATE": StandardAnchors(
        umls_cui="C0428548",
        loinc="2524-7",        # Lactate [Moles/volume] in Blood
        snomed_ct="273974008", # Serum lactate measurement
    ),
    "ORDER_BLOOD_CULTURE": StandardAnchors(
        umls_cui="C0200949",
        loinc="600-7",         # Blood culture
        snomed_ct="30088009",  # Blood culture procedure
    ),
    "ORDER_PROCALCITONIN": StandardAnchors(
        umls_cui="C0936971",
        loinc="33959-8",       # Procalcitonin [Mass/volume] in Serum
        snomed_ct="312504002", # Procalcitonin level
    ),
    "ORDER_CBC": StandardAnchors(
        umls_cui="C0009555",
        loinc="58410-2",       # CBC panel
        snomed_ct="26604007",  # Complete blood count
    ),
    "ORDER_BMP": StandardAnchors(
        umls_cui="C0428469",
        loinc="24320-4",       # Basic metabolic panel
        snomed_ct="166312007", # Basic metabolic panel
    ),
    "ORDER_CMP": StandardAnchors(
        umls_cui="C0747524",
        loinc="24323-8",       # Comprehensive metabolic panel
        snomed_ct="166312007", # Comprehensive metabolic panel
    ),

    # --- Cardiac Biomarkers ---
    "ORDER_TROPONIN": StandardAnchors(
        umls_cui="C0523952",
        loinc="6598-7",        # Troponin T cardiac [Mass/volume]
        snomed_ct="105000003", # Troponin T measurement
    ),
    "ORDER_TROPONIN_I": StandardAnchors(
        umls_cui="C0523953",
        loinc="10839-9",       # Troponin I cardiac [Mass/volume]
        snomed_ct="102683006", # Troponin I measurement
    ),
    "ORDER_TROPONIN_T": StandardAnchors(
        umls_cui="C0523952",
        loinc="6598-7",        # Troponin T cardiac [Mass/volume]
        snomed_ct="105000003", # Troponin T measurement
    ),
    "ORDER_BNP": StandardAnchors(
        umls_cui="C0524987",
        loinc="30934-4",       # BNP [Mass/volume]
        snomed_ct="390917001", # BNP level
    ),
    "ORDER_NT_PROBNP": StandardAnchors(
        umls_cui="C1441836",
        loinc="33762-6",       # NT-proBNP [Mass/volume]
        snomed_ct="390925002", # NT-proBNP level
    ),
    "ORDER_CK_MB": StandardAnchors(
        umls_cui="C0201928",
        loinc="13969-1",       # CK-MB [Mass/volume]
        snomed_ct="166603001", # CK-MB measurement
    ),

    # --- Renal Function (AKI) ---
    "ORDER_CREATININE": StandardAnchors(
        umls_cui="C0201975",
        loinc="2160-0",        # Creatinine [Mass/volume] in Serum
        snomed_ct="70901006",  # Serum creatinine
    ),
    "ORDER_BUN": StandardAnchors(
        umls_cui="C0005845",
        loinc="3094-0",        # BUN [Mass/volume]
        snomed_ct="105011006", # Blood urea nitrogen
    ),
    "ORDER_URINALYSIS": StandardAnchors(
        umls_cui="C0042014",
        loinc="24356-8",       # Urinalysis panel
        snomed_ct="27171005",  # Urinalysis
    ),
    "ORDER_URINE_SODIUM": StandardAnchors(
        umls_cui="C0587095",
        loinc="2955-3",        # Sodium [Moles/volume] in Urine
        snomed_ct="271202005", # Urine sodium measurement
    ),
    "ORDER_FENA": StandardAnchors(
        umls_cui="C0428476",
        loinc="2164-2",        # FENa calculation
        snomed_ct="250746008", # Fractional sodium excretion
    ),

    # --- DKA Labs ---
    "ORDER_GLUCOSE": StandardAnchors(
        umls_cui="C0005802",
        loinc="2345-7",        # Glucose [Mass/volume] in Serum
        snomed_ct="36048009",  # Blood glucose
    ),
    "ORDER_ABG": StandardAnchors(
        umls_cui="C0150411",
        loinc="24336-0",       # Arterial blood gas panel
        snomed_ct="278297009", # Arterial blood gas
    ),
    "ORDER_VBG": StandardAnchors(
        umls_cui="C0428165",
        loinc="24337-8",       # Venous blood gas panel
        snomed_ct="278298004", # Venous blood gas
    ),
    "ORDER_BETA_HYDROXYBUTYRATE": StandardAnchors(
        umls_cui="C0020454",
        loinc="53061-8",       # Beta-hydroxybutyrate [Moles/volume]
        snomed_ct="312448003", # Beta-hydroxybutyrate level
    ),
    "ORDER_ANION_GAP": StandardAnchors(
        umls_cui="C0428505",
        loinc="33037-3",       # Anion gap [Moles/volume]
        snomed_ct="250737006", # Anion gap calculation
    ),
    "ORDER_POTASSIUM": StandardAnchors(
        umls_cui="C0302588",
        loinc="2823-3",        # Potassium [Moles/volume] in Serum
        snomed_ct="59573005",  # Serum potassium
    ),
    "ORDER_MAGNESIUM": StandardAnchors(
        umls_cui="C0373663",
        loinc="19123-9",       # Magnesium [Mass/volume] in Serum
        snomed_ct="104866001", # Serum magnesium
    ),
    "ORDER_PHOSPHATE": StandardAnchors(
        umls_cui="C0428535",
        loinc="2777-1",        # Phosphate [Mass/volume] in Serum
        snomed_ct="104868000", # Serum phosphate
    ),

    # --- Coagulation ---
    "ORDER_PT_INR": StandardAnchors(
        umls_cui="C0033707",
        loinc="5902-2",        # PT [Time]
        snomed_ct="165581004", # Prothrombin time
    ),
    "ORDER_PTT": StandardAnchors(
        umls_cui="C0030605",
        loinc="3173-2",        # aPTT [Time]
        snomed_ct="165595005", # Partial thromboplastin time
    ),
    "ORDER_FIBRINOGEN": StandardAnchors(
        umls_cui="C0201648",
        loinc="3255-7",        # Fibrinogen [Mass/volume]
        snomed_ct="250345001", # Fibrinogen level
    ),
    "ORDER_D_DIMER": StandardAnchors(
        umls_cui="C0060323",
        loinc="48065-7",       # D-dimer FEU [Mass/volume]
        snomed_ct="250344002", # D-dimer level
    ),

    # --- Liver Function ---
    "ORDER_LFT": StandardAnchors(
        umls_cui="C0023901",
        loinc="24325-3",       # Hepatic function panel
        snomed_ct="26958001",  # Liver function tests
    ),
    "ORDER_AST": StandardAnchors(
        umls_cui="C0004002",
        loinc="1920-8",        # AST [Enzymatic activity/volume]
        snomed_ct="45896001",  # AST measurement
    ),
    "ORDER_ALT": StandardAnchors(
        umls_cui="C0001899",
        loinc="1742-6",        # ALT [Enzymatic activity/volume]
        snomed_ct="250637003", # ALT measurement
    ),
}


# =============================================================================
# HIGH-FREQUENCY L1 CONCEPTS - IMAGING (SNOMED/LOINC)
# =============================================================================

IMAGING_ANCHORS: Dict[str, StandardAnchors] = {
    # --- ECG ---
    "ORDER_ECG": StandardAnchors(
        umls_cui="C0013798",
        loinc="11524-6",       # ECG 12-lead
        snomed_ct="29303009",  # Electrocardiogram
    ),
    "ORDER_ECG_V4R": StandardAnchors(
        umls_cui="C0013798",
        loinc="11524-6",       # ECG (with right-sided leads)
        snomed_ct="428569007", # Right-sided ECG
    ),

    # --- Chest Imaging ---
    "ORDER_CHEST_XRAY": StandardAnchors(
        umls_cui="C0039985",
        loinc="36643-5",       # Chest X-ray
        snomed_ct="399208008", # Chest radiograph
    ),
    "ORDER_CT_CHEST": StandardAnchors(
        umls_cui="C0202823",
        loinc="30746-2",       # CT Chest
        snomed_ct="169069000", # CT of chest
    ),
    "ORDER_CT_CHEST_PE_PROTOCOL": StandardAnchors(
        umls_cui="C0412615",
        loinc="36813-4",       # CT Chest PE protocol
        snomed_ct="418891003", # CT pulmonary angiography
    ),

    # --- Cardiac Imaging ---
    "ORDER_ECHOCARDIOGRAM": StandardAnchors(
        umls_cui="C0013516",
        loinc="42148-7",       # Echocardiogram
        snomed_ct="40701008",  # Echocardiography
    ),
    "ORDER_CARDIAC_CATH": StandardAnchors(
        umls_cui="C0018795",
        loinc="None",
        snomed_ct="41976001",  # Cardiac catheterization
    ),

    # --- Neuroimaging (Stroke) ---
    "ORDER_CT_HEAD": StandardAnchors(
        umls_cui="C0202691",
        loinc="24725-4",       # CT Head
        snomed_ct="77477000",  # CT of head
    ),
    "ORDER_CT_HEAD_NON_CONTRAST": StandardAnchors(
        umls_cui="C0202691",
        loinc="24725-4",
        snomed_ct="34227000",  # CT Head without contrast
    ),
    "ORDER_CTA_HEAD_NECK": StandardAnchors(
        umls_cui="C0861850",
        loinc="72246-5",       # CTA Head and Neck
        snomed_ct="432519001", # CT angiography of head and neck
    ),
    "ORDER_MRI_BRAIN": StandardAnchors(
        umls_cui="C0412675",
        loinc="24590-2",       # MRI Brain
        snomed_ct="241601008", # MRI of brain
    ),
    "ORDER_MRI_BRAIN_PERFUSION": StandardAnchors(
        umls_cui="C4274111",
        loinc="None",
        snomed_ct="431553007", # MRI perfusion of brain
    ),

    # --- Renal Imaging (AKI) ---
    "ORDER_RENAL_ULTRASOUND": StandardAnchors(
        umls_cui="C0203393",
        loinc="38078-1",       # US Kidneys
        snomed_ct="268441008", # Ultrasound of kidneys
    ),
}


# =============================================================================
# HIGH-FREQUENCY L1 CONCEPTS - PROCEDURES (SNOMED)
# =============================================================================

PROCEDURE_ANCHORS: Dict[str, StandardAnchors] = {
    # --- Resuscitation ---
    "ACTIVATE_CATH_LAB": StandardAnchors(
        umls_cui="C0018795",
        snomed_ct="41976001",  # Cardiac catheterization
    ),
    "INITIATE_CPR": StandardAnchors(
        umls_cui="C0007203",
        snomed_ct="89666000",  # Cardiopulmonary resuscitation
    ),
    "PERFORM_DEFIBRILLATION": StandardAnchors(
        umls_cui="C0011660",
        snomed_ct="308842006", # Defibrillation
    ),

    # --- Airway ---
    "PERFORM_INTUBATION": StandardAnchors(
        umls_cui="C0021932",
        snomed_ct="112798008", # Endotracheal intubation
    ),
    "START_MECHANICAL_VENTILATION": StandardAnchors(
        umls_cui="C0199470",
        snomed_ct="40617009",  # Mechanical ventilation
    ),

    # --- Vascular Access ---
    "PLACE_CENTRAL_LINE": StandardAnchors(
        umls_cui="C0007431",
        snomed_ct="233527006", # Central venous catheterization
    ),
    "PLACE_ARTERIAL_LINE": StandardAnchors(
        umls_cui="C0189863",
        snomed_ct="233515003", # Arterial line insertion
    ),

    # --- Stroke Procedures ---
    "PERFORM_MECHANICAL_THROMBECTOMY": StandardAnchors(
        umls_cui="C0872367",
        snomed_ct="433112001", # Mechanical thrombectomy
    ),
    "CONSULT_INTERVENTIONAL_RADIOLOGY": StandardAnchors(
        umls_cui="C0454475",
        snomed_ct="183516009", # Referral to interventional radiologist
    ),

    # --- Dialysis (AKI) ---
    "INITIATE_HEMODIALYSIS": StandardAnchors(
        umls_cui="C0019004",
        snomed_ct="302497006", # Hemodialysis
    ),
    "INITIATE_CRRT": StandardAnchors(
        umls_cui="C0206074",
        snomed_ct="714749008", # Continuous renal replacement therapy
    ),
}


# =============================================================================
# DIAGNOSES / CONDITIONS (ICD-10/SNOMED)
# =============================================================================

DIAGNOSIS_ANCHORS: Dict[str, StandardAnchors] = {
    # --- Cardiac ---
    "STEMI": StandardAnchors(
        umls_cui="C1536220",
        icd10="I21.3",
        snomed_ct="401303003",  # STEMI
    ),
    "NSTEMI": StandardAnchors(
        umls_cui="C1536221",
        icd10="I21.4",
        snomed_ct="401314000",  # NSTEMI
    ),
    "RV_INFARCTION": StandardAnchors(
        umls_cui="C0340299",
        icd10="I21.11",
        snomed_ct="233825009",  # Right ventricular infarction
    ),
    "ACUTE_HEART_FAILURE": StandardAnchors(
        umls_cui="C0264716",
        icd10="I50.9",
        snomed_ct="84114007",   # Acute heart failure
    ),
    "CARDIOGENIC_SHOCK": StandardAnchors(
        umls_cui="C0036980",
        icd10="R57.0",
        snomed_ct="89138009",   # Cardiogenic shock
    ),

    # --- Sepsis ---
    "SEPSIS": StandardAnchors(
        umls_cui="C0243026",
        icd10="A41.9",
        snomed_ct="91302008",   # Sepsis
    ),
    "SEPTIC_SHOCK": StandardAnchors(
        umls_cui="C0036983",
        icd10="R65.21",
        snomed_ct="76571007",   # Septic shock
    ),

    # --- Neurologic ---
    "ISCHEMIC_STROKE": StandardAnchors(
        umls_cui="C0948008",
        icd10="I63.9",
        snomed_ct="422504002",  # Ischemic stroke
    ),
    "HEMORRHAGIC_STROKE": StandardAnchors(
        umls_cui="C0553692",
        icd10="I61.9",
        snomed_ct="274100004",  # Hemorrhagic stroke
    ),

    # --- Metabolic ---
    "DKA": StandardAnchors(
        umls_cui="C0011880",
        icd10="E10.10",
        snomed_ct="420422005",  # Diabetic ketoacidosis
    ),
    "HHS": StandardAnchors(
        umls_cui="C0020619",
        icd10="E11.00",
        snomed_ct="359642000",  # Hyperosmolar hyperglycemic state
    ),

    # --- Renal ---
    "AKI": StandardAnchors(
        umls_cui="C2609414",
        icd10="N17.9",
        snomed_ct="14669001",   # Acute kidney injury
    ),
    "CONTRAST_INDUCED_AKI": StandardAnchors(
        umls_cui="C2919500",
        icd10="N14.1",
        snomed_ct="371035001",  # Contrast-induced nephropathy
    ),
}


# =============================================================================
# UNIFIED ANCHOR REGISTRY
# =============================================================================

def get_all_anchors() -> Dict[str, StandardAnchors]:
    """Get unified dictionary of all standard anchors."""
    all_anchors = {}
    all_anchors.update(MEDICATION_ANCHORS)
    all_anchors.update(LAB_ANCHORS)
    all_anchors.update(IMAGING_ANCHORS)
    all_anchors.update(PROCEDURE_ANCHORS)
    all_anchors.update(DIAGNOSIS_ANCHORS)
    return all_anchors


def get_anchor(concept_id: str) -> Optional[StandardAnchors]:
    """Get standard anchors for a concept ID.

    Args:
        concept_id: The concept identifier (e.g., "ORDER_LACTATE")

    Returns:
        StandardAnchors if mapped, None otherwise
    """
    all_anchors = get_all_anchors()
    return all_anchors.get(concept_id) or all_anchors.get(concept_id.upper())


def get_coverage_stats() -> dict:
    """Calculate anchor coverage statistics."""
    all_anchors = get_all_anchors()

    umls_count = sum(1 for a in all_anchors.values() if a.umls_cui)
    rxcui_count = sum(1 for a in all_anchors.values() if a.rxcui and a.rxcui != "None")
    loinc_count = sum(1 for a in all_anchors.values() if a.loinc and a.loinc != "None")
    snomed_count = sum(1 for a in all_anchors.values() if a.snomed_ct)
    icd10_count = sum(1 for a in all_anchors.values() if a.icd10)

    total = len(all_anchors)

    return {
        "total_concepts": total,
        "umls_cui": {"count": umls_count, "coverage": umls_count / total * 100},
        "rxcui": {"count": rxcui_count, "coverage": rxcui_count / total * 100},
        "loinc": {"count": loinc_count, "coverage": loinc_count / total * 100},
        "snomed_ct": {"count": snomed_count, "coverage": snomed_count / total * 100},
        "icd10": {"count": icd10_count, "coverage": icd10_count / total * 100},
    }


if __name__ == "__main__":
    # Print coverage statistics
    stats = get_coverage_stats()
    print("=" * 60)
    print("STANDARD ANCHOR COVERAGE STATISTICS")
    print("=" * 60)
    print(f"Total Concepts Mapped: {stats['total_concepts']}")
    print("-" * 60)
    print(f"UMLS CUI:   {stats['umls_cui']['count']:3d} ({stats['umls_cui']['coverage']:.1f}%)")
    print(f"RxCUI:      {stats['rxcui']['count']:3d} ({stats['rxcui']['coverage']:.1f}%)")
    print(f"LOINC:      {stats['loinc']['count']:3d} ({stats['loinc']['coverage']:.1f}%)")
    print(f"SNOMED-CT:  {stats['snomed_ct']['count']:3d} ({stats['snomed_ct']['coverage']:.1f}%)")
    print(f"ICD-10:     {stats['icd10']['count']:3d} ({stats['icd10']['coverage']:.1f}%)")
    print("=" * 60)
