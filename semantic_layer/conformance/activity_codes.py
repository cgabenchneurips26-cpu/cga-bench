"""
Extended LOINC/clinical code vocabulary for activity extraction.

Provides CodeVocabulary with clinical code families that map
LOINC codes and common synonyms to standardized activity names.
The original hardcoded sets (ECG_CODES, TROPONIN_CODES, etc.) remain
in activity.py as the primary match path; this module provides
a secondary fallback with broader coverage.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class CodeFamily:
    """A group of related clinical codes that map to the same activity type.

    Each family covers a clinical test panel or category,
    with LOINC codes and common textual synonyms.
    """
    family_id: str
    codes: Set[str]         # LOINC codes + uppercase synonyms
    activity_get: str       # Activity name for GET requests
    activity_post: str      # Activity name for POST requests
    domain: str = "general"


# --- Code Family Definitions ---

_CBC_CODES = {
    # LOINC codes
    "6690-2", "789-8", "718-7", "4544-3", "785-6", "786-4",
    "787-2", "32623-1", "26515-7", "777-3",
    # Synonyms
    "WBC", "RBC", "HEMOGLOBIN", "HGB", "HCT", "HEMATOCRIT",
    "PLATELET", "PLT", "PLATELET_COUNT", "MCV", "MCH", "MCHC",
    "RDW", "MPV", "CBC", "COMPLETE_BLOOD_COUNT",
}

_BMP_CODES = {
    # LOINC codes
    "2951-2", "2823-3", "3094-0", "2160-0", "2345-7",
    "2028-9", "17861-6", "2075-0",
    # Synonyms
    "SODIUM", "NA", "POTASSIUM", "K", "BUN", "CREATININE",
    "GLUCOSE", "CO2", "BICARBONATE", "CALCIUM", "CA",
    "CHLORIDE", "CL", "BMP", "BASIC_METABOLIC_PANEL",
}

_CMP_CODES = _BMP_CODES | {
    # Additional LOINC codes for CMP
    "1751-7", "1975-2", "6768-6", "1742-6", "1920-8",
    # Synonyms
    "ALBUMIN", "TOTAL_PROTEIN", "BILIRUBIN", "ALP",
    "ALT", "AST", "SGOT", "SGPT", "CMP", "COMPREHENSIVE_METABOLIC_PANEL",
}

_CARDIAC_CODES = {
    # LOINC codes
    "6598-7", "49563-0", "10839-9", "42757-5", "30522-7",
    "33762-6", "48066-5", "2157-6",
    # Synonyms
    "TROPONIN", "TROPONIN-I", "TROPONIN-T", "TNI", "TNT",
    "BNP", "NT-PROBNP", "PRBNP", "CK-MB", "CKMB",
    "D-DIMER", "DDIMER",
}

_COAGULATION_CODES = {
    # LOINC codes
    "5902-2", "6301-6", "3173-2", "3255-7", "48065-7",
    "46418-0",
    # Synonyms
    "PT", "PROTHROMBIN", "INR", "PTT", "APTT",
    "FIBRINOGEN", "COAGULATION", "COAG",
}

_SEPSIS_CODES = {
    # LOINC codes
    "2524-7", "32693-4", "33959-8", "75241-0",
    "600-7", "17928-3",
    # Synonyms
    "LACTATE", "LACTIC_ACID", "PROCALCITONIN", "PCT",
    "CRP", "C-REACTIVE_PROTEIN", "BLOOD_CULTURE",
    "BLOOD_CX", "BCX",
}

_ABG_CODES = {
    # LOINC codes
    "2744-1", "2019-8", "2703-7", "1959-6", "1960-4",
    "2708-6",
    # Synonyms
    "PH", "PCO2", "PO2", "HCO3", "BICARBONATE",
    "BASE_EXCESS", "BE", "ABG", "ARTERIAL_BLOOD_GAS",
    "VBG", "VENOUS_BLOOD_GAS",
}

_THYROID_CODES = {
    # LOINC codes
    "3016-3", "3053-6", "3024-7", "3026-2",
    # Synonyms
    "TSH", "T3", "T4", "FREE_T4", "FT4", "FREE_T3", "FT3",
    "THYROID",
}

_RENAL_CODES = {
    # LOINC codes
    "2160-0", "3094-0", "33914-3", "62238-1", "82565-2",
    # Synonyms
    "CREATININE", "CR", "BUN", "GFR", "EGFR",
    "CYSTATIN_C", "CYSTATIN", "RENAL_FUNCTION",
}

_LIVER_CODES = {
    # LOINC codes
    "1742-6", "1920-8", "1975-2", "6768-6", "1751-7",
    "1968-7", "2324-2",
    # Synonyms
    "ALT", "AST", "SGPT", "SGOT", "ALP",
    "ALKALINE_PHOSPHATASE", "BILIRUBIN", "TBILI",
    "GGT", "ALBUMIN", "LFT", "LIVER_FUNCTION",
}

_URINALYSIS_CODES = {
    # LOINC codes
    "2888-6", "5811-5", "5803-2", "5767-9", "5770-3",
    "5799-2", "5794-3", "5778-6",
    # Synonyms
    "URINE_PROTEIN", "URINE_GLUCOSE", "URINE_PH",
    "URINE_BLOOD", "URINE_KETONES", "URINE_LEUKOCYTES",
    "URINALYSIS", "UA", "URINE_SPECIFIC_GRAVITY",
}

_LIPID_CODES = {
    # LOINC codes
    "2093-3", "2571-8", "2085-9", "13457-7", "2089-1",
    # Synonyms
    "CHOLESTEROL", "TOTAL_CHOLESTEROL", "TRIGLYCERIDES", "TG",
    "HDL", "LDL", "VLDL", "LIPID_PANEL",
}

_ELECTROLYTE_CODES = {
    # LOINC codes
    "2951-2", "2823-3", "2075-0", "17861-6",
    "24321-2", "2601-3",
    # Synonyms
    "SODIUM", "NA", "POTASSIUM", "K", "CALCIUM", "CA",
    "MAGNESIUM", "MG", "PHOSPHATE", "PHOSPHORUS", "PO4",
    "CHLORIDE", "CL", "ELECTROLYTES",
}

_IMAGING_CODES = {
    # Common imaging order codes (RadLex/LOINC)
    "24627-2", "24628-0", "36643-5", "30746-2",
    "46335-6", "24566-2",
    # Synonyms
    "CT", "CT_SCAN", "CAT_SCAN", "MRI", "X-RAY", "XRAY",
    "CHEST_XRAY", "CXR", "ECHO", "ECHOCARDIOGRAM",
    "ULTRASOUND", "US", "ANGIOGRAPHY", "ANGIOGRAM",
    "CT_ANGIOGRAPHY", "CTA", "MRA",
}

_ECG_EXTENDED_CODES = {
    "11524-6", "34534-8", "28009-9", "89196-2",
    "ECG", "EKG", "ELECTROCARDIOGRAM", "12-LEAD",
    "12_LEAD_ECG", "RHYTHM_STRIP",
}

_DRUG_LEVEL_CODES = {
    # LOINC codes for therapeutic drug monitoring
    "3968-5", "4092-3", "4049-3", "14836-7",
    # Synonyms
    "VANCOMYCIN_LEVEL", "DIGOXIN_LEVEL", "PHENYTOIN_LEVEL",
    "GENTAMICIN_LEVEL", "DRUG_LEVEL", "TDM",
}

_BLOOD_GAS_VENOUS_CODES = {
    "2744-1", "2019-8", "2703-7",
    "VBG", "VENOUS_BLOOD_GAS", "VENOUS_PH",
}

_INFLAMMATORY_CODES = {
    "1988-5", "4537-7", "30341-2", "26881-3",
    "ESR", "SED_RATE", "CRP", "C-REACTIVE_PROTEIN",
    "FERRITIN", "IL-6", "INTERLEUKIN_6",
}

_TOXICOLOGY_CODES = {
    "19295-5", "43006-3", "3426-4",
    "URINE_DRUG_SCREEN", "UDS", "DRUG_SCREEN",
    "ALCOHOL_LEVEL", "ETHANOL", "ACETAMINOPHEN_LEVEL",
    "SALICYLATE_LEVEL", "TOX_SCREEN",
}


# --- Default Code Families ---

DEFAULT_CODE_FAMILIES: List[CodeFamily] = [
    CodeFamily("cbc", _CBC_CODES, "QUERY_CBC", "ORDER_CBC", "hematology"),
    CodeFamily("bmp", _BMP_CODES, "QUERY_BMP", "ORDER_BMP", "chemistry"),
    CodeFamily("cmp", _CMP_CODES, "QUERY_CMP", "ORDER_CMP", "chemistry"),
    CodeFamily("cardiac", _CARDIAC_CODES, "QUERY_CARDIAC_MARKERS", "ORDER_CARDIAC_MARKERS", "cardiology"),
    CodeFamily("coagulation", _COAGULATION_CODES, "QUERY_COAGULATION", "ORDER_COAGULATION", "hematology"),
    CodeFamily("sepsis", _SEPSIS_CODES, "QUERY_SEPSIS_MARKERS", "ORDER_SEPSIS_MARKERS", "sepsis"),
    CodeFamily("abg", _ABG_CODES, "QUERY_ABG", "ORDER_ABG", "respiratory"),
    CodeFamily("thyroid", _THYROID_CODES, "QUERY_THYROID", "ORDER_THYROID", "endocrine"),
    CodeFamily("renal", _RENAL_CODES, "QUERY_RENAL", "ORDER_RENAL", "nephrology"),
    CodeFamily("liver", _LIVER_CODES, "QUERY_LIVER", "ORDER_LIVER", "gastroenterology"),
    CodeFamily("urinalysis", _URINALYSIS_CODES, "QUERY_URINALYSIS", "ORDER_URINALYSIS", "nephrology"),
    CodeFamily("lipid", _LIPID_CODES, "QUERY_LIPID", "ORDER_LIPID", "cardiology"),
    CodeFamily("electrolytes", _ELECTROLYTE_CODES, "QUERY_ELECTROLYTES", "ORDER_ELECTROLYTES", "chemistry"),
    CodeFamily("imaging", _IMAGING_CODES, "QUERY_IMAGING", "ORDER_IMAGING", "radiology"),
    CodeFamily("ecg", _ECG_EXTENDED_CODES, "QUERY_ECG", "ORDER_ECG", "cardiology"),
    CodeFamily("drug_levels", _DRUG_LEVEL_CODES, "QUERY_DRUG_LEVEL", "ORDER_DRUG_LEVEL", "pharmacology"),
    CodeFamily("inflammatory", _INFLAMMATORY_CODES, "QUERY_INFLAMMATORY", "ORDER_INFLAMMATORY", "immunology"),
    CodeFamily("toxicology", _TOXICOLOGY_CODES, "QUERY_TOXICOLOGY", "ORDER_TOXICOLOGY", "emergency"),
]


class CodeVocabulary:
    """Extensible code vocabulary for matching FHIR codes to clinical activities.

    Uses code families to map groups of related LOINC codes and synonyms
    to standardized activity names. More specific families (fewer codes)
    are matched first to avoid overly broad matches.
    """

    def __init__(self, extra_families: Optional[List[CodeFamily]] = None):
        self._families: List[CodeFamily] = list(DEFAULT_CODE_FAMILIES)
        if extra_families:
            self._families.extend(extra_families)
        # Sort by specificity (smaller code sets first → more precise matches)
        self._families.sort(key=lambda f: len(f.codes))

    def match(
        self,
        codes: Set[str],
        method: str,
        resource_type: Optional[str] = None,
    ) -> Optional[Tuple[str, float, str]]:
        """Match codes against code families.

        Args:
            codes: Set of code strings (case-insensitive matching applied)
            method: HTTP method (GET/POST)
            resource_type: Optional FHIR resource type for context

        Returns:
            Tuple of (activity_name, confidence, family_id) or None
        """
        if not codes:
            return None

        codes_upper = {c.upper() for c in codes}
        best_match: Optional[Tuple[str, float, str]] = None
        best_overlap = 0

        for family in self._families:
            overlap = codes_upper & family.codes
            if not overlap:
                continue

            # Confidence based on overlap ratio relative to query codes
            confidence = min(len(overlap) / len(codes_upper), 1.0)
            # Boost confidence for specific matches (more overlap = better)
            confidence = max(confidence, 0.9)

            if len(overlap) > best_overlap:
                best_overlap = len(overlap)
                activity = family.activity_get if method == "GET" else family.activity_post
                best_match = (activity, confidence, family.family_id)

        return best_match

    @property
    def families(self) -> List[CodeFamily]:
        """Access registered code families."""
        return list(self._families)
