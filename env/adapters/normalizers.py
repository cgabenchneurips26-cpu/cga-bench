"""
Action Target Normalizers

액션 target 문자열을 정규화하여 cross-benchmark 호환성 확보
"""
from __future__ import annotations
import re
import logging
from typing import Dict, Optional, Set
from pathlib import Path
import yaml

logger = logging.getLogger(__name__)

_NORMALIZERS_DIR = Path(__file__).parent / "mappings"


class ActionTargetNormalizer:
    """
    액션 target 정규화

    Examples:
        "Complete Blood Count" → "cbc"
        "a CBC lab test" → "cbc"
        "Troponin I" → "troponin"
        "chest CT scan" → "chest_ct"
    """

    _lab_cache: Optional[Dict[str, str]] = None
    _medication_cache: Optional[Dict[str, str]] = None
    _imaging_cache: Optional[Dict[str, str]] = None
    _specialty_cache: Optional[Dict[str, str]] = None
    _unmatched_targets: Set[str] = set()

    # Lab test synonyms
    LAB_SYNONYMS = {
        # CBC variants
        "cbc": ["complete blood count", "cbc", "full blood count", "fbc", "blood count"],
        "hemoglobin": ["hemoglobin", "hgb", "hb"],
        "hematocrit": ["hematocrit", "hct"],
        "wbc": ["white blood cell", "wbc", "leukocyte", "white cell count"],
        "platelet": ["platelet", "plt", "thrombocyte"],

        # Metabolic panel
        "bmp": ["basic metabolic panel", "bmp", "chem 7", "chem7"],
        "cmp": ["comprehensive metabolic panel", "cmp", "chem 14", "chem14"],
        "sodium": ["sodium", "na"],
        "potassium": ["potassium", "k"],
        "chloride": ["chloride", "cl"],
        "bicarbonate": ["bicarbonate", "bicarb", "hco3", "co2"],
        "bun": ["blood urea nitrogen", "bun", "urea"],
        "creatinine": ["creatinine", "cr", "creat"],
        "glucose": ["glucose", "blood sugar", "bs", "blood glucose"],

        # Cardiac markers
        "troponin": ["troponin", "trop", "troponin i", "troponin t", "tnni", "tnnt", "cardiac troponin"],
        "bnp": ["bnp", "brain natriuretic peptide", "nt-probnp", "ntprobnp", "pro-bnp"],
        "ck": ["creatine kinase", "ck", "cpk"],
        "ckmb": ["ck-mb", "ckmb", "creatine kinase mb"],

        # Coagulation
        "pt_inr": ["pt", "inr", "pt/inr", "prothrombin time"],
        "ptt": ["ptt", "aptt", "partial thromboplastin time"],
        "d_dimer": ["d-dimer", "d dimer", "ddimer"],
        "fibrinogen": ["fibrinogen", "fib"],

        # Sepsis / Infection
        "lactate": ["lactate", "lactic acid", "lac"],
        "procalcitonin": ["procalcitonin", "pct"],
        "crp": ["crp", "c-reactive protein", "c reactive protein"],
        "blood_culture": ["blood culture", "bcx", "blood cx", "blood_culture"],

        # ABG
        "abg": ["arterial blood gas", "abg", "blood gas"],

        # Liver
        "lft": ["liver function test", "lft", "hepatic panel", "liver panel"],
        "ast": ["ast", "sgot", "aspartate aminotransferase"],
        "alt": ["alt", "sgpt", "alanine aminotransferase"],
        "bilirubin": ["bilirubin", "bili", "total bilirubin"],
        "albumin": ["albumin", "alb"],

        # Urinalysis
        "urinalysis": ["urinalysis", "ua", "urine analysis"],
        "urine_culture": ["urine culture", "ucx", "urine cx"],

        # Microbiology / Rapid tests
        "rapid_strep": ["rapid strep", "rapid_strep", "strep test", "strep screen", "rapid streptococcal"],
        "throat_culture": ["throat culture", "throat cx"],
        "sputum_culture": ["sputum culture", "sputum cx"],
        "csf_analysis": ["csf", "csf analysis", "lumbar puncture", "spinal tap"],
        "wound_culture": ["wound culture", "wound cx"],
        "stool_culture": ["stool culture", "stool cx"],
        "covid_test": ["covid test", "covid-19", "sars-cov-2", "covid pcr", "rapid covid"],
        "flu_test": ["flu test", "influenza", "rapid flu"],

        # Lipid
        "lipid_panel": ["lipid panel", "lipids", "cholesterol panel"],

        # Thyroid
        "tsh": ["tsh", "thyroid stimulating hormone"],
        "t4": ["t4", "thyroxine", "free t4"],
        "t3": ["t3", "triiodothyronine"],
    }

    # Medication synonyms
    MEDICATION_SYNONYMS = {
        # Cardiac / Antiplatelets
        "aspirin": ["aspirin", "asa", "acetylsalicylic acid"],
        "clopidogrel": ["clopidogrel", "plavix"],
        "ticagrelor": ["ticagrelor", "brilinta"],
        "prasugrel": ["prasugrel", "effient"],
        "heparin": ["heparin", "ufh", "unfractionated heparin"],
        "enoxaparin": ["enoxaparin", "lovenox", "lmwh"],
        "nitroglycerin": ["nitroglycerin", "ntg", "nitro", "glyceryl trinitrate"],
        "metoprolol": ["metoprolol", "lopressor", "toprol"],
        "atenolol": ["atenolol", "tenormin"],
        "lisinopril": ["lisinopril", "prinivil", "zestril"],
        "atorvastatin": ["atorvastatin", "lipitor"],
        "furosemide": ["furosemide", "lasix"],

        # Vasopressors
        "norepinephrine": ["norepinephrine", "levophed", "noradrenaline"],
        "epinephrine": ["epinephrine", "adrenaline", "epi"],
        "vasopressin": ["vasopressin", "pitressin", "adh"],
        "dopamine": ["dopamine"],
        "dobutamine": ["dobutamine"],
        "phenylephrine": ["phenylephrine", "neosynephrine"],

        # Antibiotics (generic and specific)
        "antibiotics": ["antibiotics", "antibiotic", "abx", "broad_spectrum_antibiotics", "broad spectrum antibiotics"],
        "vancomycin": ["vancomycin", "vanc"],
        "piperacillin_tazobactam": ["piperacillin-tazobactam", "piperacillin_tazobactam", "pip-tazo", "zosyn", "tazocin"],
        "ceftriaxone": ["ceftriaxone", "rocephin"],
        "cefepime": ["cefepime", "maxipime"],
        "cefazolin": ["cefazolin", "ancef", "kefzol"],
        "ceftazidime": ["ceftazidime", "fortaz"],
        "meropenem": ["meropenem", "merrem"],
        "imipenem": ["imipenem", "primaxin"],
        "ertapenem": ["ertapenem", "invanz"],
        "azithromycin": ["azithromycin", "zithromax", "z-pack"],
        "levofloxacin": ["levofloxacin", "levaquin"],
        "ciprofloxacin": ["ciprofloxacin", "cipro"],
        "moxifloxacin": ["moxifloxacin", "avelox"],
        "metronidazole": ["metronidazole", "flagyl"],
        "ampicillin": ["ampicillin"],
        "amoxicillin": ["amoxicillin", "amoxil"],
        "ampicillin_sulbactam": ["ampicillin-sulbactam", "unasyn"],
        "gentamicin": ["gentamicin"],
        "tobramycin": ["tobramycin"],
        "amikacin": ["amikacin"],
        "aztreonam": ["aztreonam", "azactam"],
        "daptomycin": ["daptomycin", "cubicin"],
        "linezolid": ["linezolid", "zyvox"],
        "clindamycin": ["clindamycin", "cleocin"],
        "doxycycline": ["doxycycline", "vibramycin"],
        "trimethoprim_sulfamethoxazole": ["trimethoprim-sulfamethoxazole", "tmp-smx", "bactrim", "septra"],

        # Pain / Sedation
        "morphine": ["morphine", "ms contin"],
        "fentanyl": ["fentanyl", "sublimaze"],
        "hydromorphone": ["hydromorphone", "dilaudid"],
        "acetaminophen": ["acetaminophen", "tylenol", "paracetamol", "apap"],
        "ibuprofen": ["ibuprofen", "advil", "motrin"],
        "ketorolac": ["ketorolac", "toradol"],

        # Fluids
        "normal_saline": ["normal saline", "ns", "0.9% saline", "0.9 saline", "saline"],
        "lactated_ringers": ["lactated ringer", "lr", "ringer lactate", "rl"],
        "iv_fluids": ["iv fluid", "intravenous fluid", "crystalloid", "crystalloid_30ml_kg", "crystalloid 30ml/kg"],

        # GI medications
        "omeprazole": ["omeprazole", "prilosec"],
        "pantoprazole": ["pantoprazole", "protonix"],
        "famotidine": ["famotidine", "pepcid"],
        "ondansetron": ["ondansetron", "zofran"],
        "metoclopramide": ["metoclopramide", "reglan"],

        # Anti-inflammatory / Gout
        "colchicine": ["colchicine", "colcrys"],
        "allopurinol": ["allopurinol", "zyloprim"],
        "prednisone": ["prednisone", "deltasone"],
        "methylprednisolone": ["methylprednisolone", "solu-medrol", "medrol"],

        # Other
        "insulin": ["insulin", "regular insulin"],
        "dextrose": ["dextrose", "d50", "d10", "d5"],
        "calcium": ["calcium", "calcium gluconate", "calcium chloride"],
        "magnesium": ["magnesium", "mag", "mg sulfate"],
        "potassium_chloride": ["potassium chloride", "kcl", "k replacement"],
        "sodium_bicarbonate": ["sodium bicarbonate", "bicarb", "nahco3"],
        "tpa": ["tpa", "alteplase", "tissue plasminogen activator", "tenecteplase"],
        "oxygen": ["oxygen", "o2", "supplemental oxygen"],
    }

    # Imaging synonyms
    IMAGING_SYNONYMS = {
        "ecg": ["ecg", "ekg", "electrocardiogram", "12-lead", "12 lead"],
        "chest_xray": ["chest x-ray", "chest xray", "cxr", "chest radiograph", "chest film", "chest_xray"],
        "chest_ct": ["chest ct", "ct chest", "ct thorax", "ct pulmonary"],
        "ct_head": ["ct head", "head ct", "brain ct", "ct brain", "non-contrast head ct"],
        "ct_abdomen": ["ct abdomen", "abdominal ct", "ct abd", "ct abdomen pelvis"],
        "ct_angiography": ["cta", "ct angiography", "ct angio"],
        "mri_brain": ["mri brain", "brain mri", "mri head"],
        "mri_spine": ["mri spine", "spine mri"],
        "echocardiogram": ["echocardiogram", "echo", "transthoracic echo", "tte", "cardiac ultrasound"],
        "tee": ["tee", "transesophageal echo", "transesophageal echocardiogram"],
        "ultrasound_abdomen": ["abdominal ultrasound", "ultrasound abdomen", "abd us", "ruq ultrasound"],
        "doppler": ["doppler", "venous doppler", "arterial doppler", "lower extremity doppler"],
        "v_q_scan": ["v/q scan", "vq scan", "ventilation perfusion scan"],
    }

    # Specialty synonyms
    SPECIALTY_SYNONYMS = {
        "cardiology": ["cardiology", "cards", "cardiac"],
        "pulmonology": ["pulmonology", "pulmonary", "pulm"],
        "nephrology": ["nephrology", "renal", "neph"],
        "neurology": ["neurology", "neuro"],
        "gastroenterology": ["gastroenterology", "gi", "gastro"],
        "infectious_disease": ["infectious disease", "id", "infection"],
        "surgery": ["surgery", "surgical", "general surgery"],
        "orthopedics": ["orthopedics", "ortho", "orthopedic surgery"],
        "icu": ["icu", "intensive care", "critical care", "micu", "sicu", "ccu"],
        "oncology": ["oncology", "onc", "hematology-oncology"],
        "endocrinology": ["endocrinology", "endo"],
        "rheumatology": ["rheumatology", "rheum"],
        "psychiatry": ["psychiatry", "psych"],
        "palliative": ["palliative", "palliative care", "hospice"],
    }

    @classmethod
    def _build_reverse_map(cls, synonyms: Dict[str, list]) -> Dict[str, str]:
        """Build reverse lookup map from synonyms"""
        reverse = {}
        for canonical, variants in synonyms.items():
            for variant in variants:
                reverse[variant.lower()] = canonical
        return reverse

    @classmethod
    def _get_lab_map(cls) -> Dict[str, str]:
        if cls._lab_cache is None:
            cls._lab_cache = cls._build_reverse_map(cls.LAB_SYNONYMS)
        return cls._lab_cache

    @classmethod
    def _get_medication_map(cls) -> Dict[str, str]:
        if cls._medication_cache is None:
            cls._medication_cache = cls._build_reverse_map(cls.MEDICATION_SYNONYMS)
        return cls._medication_cache

    @classmethod
    def _get_imaging_map(cls) -> Dict[str, str]:
        if cls._imaging_cache is None:
            cls._imaging_cache = cls._build_reverse_map(cls.IMAGING_SYNONYMS)
        return cls._imaging_cache

    @classmethod
    def _get_specialty_map(cls) -> Dict[str, str]:
        if cls._specialty_cache is None:
            cls._specialty_cache = cls._build_reverse_map(cls.SPECIALTY_SYNONYMS)
        return cls._specialty_cache

    @classmethod
    def _clean_target(cls, target: str) -> str:
        """Clean target string for matching"""
        if not target:
            return ""
        # Remove common prefixes/suffixes
        cleaned = target.lower().strip()
        # Remove articles
        cleaned = re.sub(r'^(a|an|the)\s+', '', cleaned)
        # Remove common suffixes (but NOT 'culture' - it's meaningful for blood culture, urine culture)
        cleaned = re.sub(r'\s+(test|study|scan|level|panel)$', '', cleaned)
        # Remove dosage info for medications
        cleaned = re.sub(r'\s+\d+\s*(mg|mcg|g|ml|units?|iu).*$', '', cleaned, flags=re.IGNORECASE)
        # Normalize whitespace
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        return cleaned

    @classmethod
    def normalize_lab(cls, target: str) -> str:
        """Normalize lab test target"""
        if not target:
            raise ValueError("Lab target cannot be empty")

        cleaned = cls._clean_target(target)
        lab_map = cls._get_lab_map()

        # Direct match
        if cleaned in lab_map:
            return lab_map[cleaned]

        # Partial match
        for variant, canonical in lab_map.items():
            if variant in cleaned or cleaned in variant:
                return canonical

        # Log unmatched and raise
        if cleaned not in cls._unmatched_targets:
            cls._unmatched_targets.add(cleaned)
            logger.warning(f"Unmatched lab target: '{target}' (cleaned: '{cleaned}')")

        raise ValueError(f"Cannot normalize lab target: '{target}'")

    @classmethod
    def normalize_medication(cls, target: str) -> str:
        """Normalize medication target"""
        if not target:
            raise ValueError("Medication target cannot be empty")

        cleaned = cls._clean_target(target)
        med_map = cls._get_medication_map()

        # Direct match
        if cleaned in med_map:
            return med_map[cleaned]

        # Partial match
        for variant, canonical in med_map.items():
            if variant in cleaned or cleaned in variant:
                return canonical

        # Log unmatched and raise
        if cleaned not in cls._unmatched_targets:
            cls._unmatched_targets.add(cleaned)
            logger.warning(f"Unmatched medication target: '{target}' (cleaned: '{cleaned}')")

        raise ValueError(f"Cannot normalize medication target: '{target}'")

    @classmethod
    def normalize_imaging(cls, target: str) -> str:
        """Normalize imaging study target"""
        if not target:
            raise ValueError("Imaging target cannot be empty")

        cleaned = cls._clean_target(target)
        imaging_map = cls._get_imaging_map()

        # Direct match
        if cleaned in imaging_map:
            return imaging_map[cleaned]

        # Partial match
        for variant, canonical in imaging_map.items():
            if variant in cleaned or cleaned in variant:
                return canonical

        # Log unmatched and raise
        if cleaned not in cls._unmatched_targets:
            cls._unmatched_targets.add(cleaned)
            logger.warning(f"Unmatched imaging target: '{target}' (cleaned: '{cleaned}')")

        raise ValueError(f"Cannot normalize imaging target: '{target}'")

    @classmethod
    def normalize_specialty(cls, target: str) -> str:
        """Normalize specialty/consult target"""
        if not target:
            raise ValueError("Specialty target cannot be empty")

        cleaned = cls._clean_target(target)
        specialty_map = cls._get_specialty_map()

        # Direct match
        if cleaned in specialty_map:
            return specialty_map[cleaned]

        # Partial match
        for variant, canonical in specialty_map.items():
            if variant in cleaned or cleaned in variant:
                return canonical

        # Log unmatched and raise
        if cleaned not in cls._unmatched_targets:
            cls._unmatched_targets.add(cleaned)
            logger.warning(f"Unmatched specialty target: '{target}' (cleaned: '{cleaned}')")

        raise ValueError(f"Cannot normalize specialty target: '{target}'")

    @classmethod
    def try_normalize_lab(cls, target: str) -> Optional[str]:
        """Try to normalize, return None if fails"""
        try:
            return cls.normalize_lab(target)
        except ValueError:
            return None

    @classmethod
    def try_normalize_medication(cls, target: str) -> Optional[str]:
        """Try to normalize, return None if fails"""
        try:
            return cls.normalize_medication(target)
        except ValueError:
            return None

    @classmethod
    def try_normalize_imaging(cls, target: str) -> Optional[str]:
        """Try to normalize, return None if fails"""
        try:
            return cls.normalize_imaging(target)
        except ValueError:
            return None

    @classmethod
    def try_normalize_specialty(cls, target: str) -> Optional[str]:
        """Try to normalize, return None if fails"""
        try:
            return cls.normalize_specialty(target)
        except ValueError:
            return None

    @classmethod
    def get_unmatched_targets(cls) -> Set[str]:
        """Get all unmatched targets encountered"""
        return cls._unmatched_targets.copy()

    @classmethod
    def clear_cache(cls):
        """Clear all caches"""
        cls._lab_cache = None
        cls._medication_cache = None
        cls._imaging_cache = None
        cls._specialty_cache = None
        cls._unmatched_targets.clear()
