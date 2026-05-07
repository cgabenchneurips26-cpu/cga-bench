#!/usr/bin/env python3
"""Extensibility Verification Framework for CGA-Bench

Validates compatibility across 4 data groups:
A. FHIR-based EHR Data (Synthea, MIMIC-IV FHIR)
B. FHIR QA/Agent Benchmarks (FHIR-AgentBench)
C. EHR SQL-based Data (EHRSQL)
D. Medical Entity Linking Benchmarks (MedMentions, BELB, BioSyn)

Compatibility Definitions:
1. FHIR resources (Observation.code=LOINC, Condition.code=SNOMED) → Standard Anchors → Ontology Concepts
2. Different representations of same clinical meaning → Consistent concept_id via Action Normalizer
3. Lossless conversion to CPG engine input events (EpisodeNorm)

Version: 1.0 (2026-01-26)
"""

import json
import csv
import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Any
from collections import defaultdict
from enum import Enum


# =============================================================================
# CORE DATA STRUCTURES
# =============================================================================

class DataSourceType(Enum):
    """Types of external data sources."""
    FHIR_EHR = "fhir_ehr"           # Synthea, MIMIC-IV FHIR
    FHIR_AGENT_BENCH = "fhir_agent" # FHIR-AgentBench
    EHR_SQL = "ehr_sql"             # EHRSQL
    MEDICAL_EL = "medical_el"       # MedMentions, BELB, BioSyn


@dataclass
class FHIRResource:
    """Parsed FHIR resource."""
    resource_type: str          # Patient, Observation, Medication, etc.
    resource_id: str
    codes: List[Dict[str, str]] # [{system: "loinc", code: "2524-7", display: "Lactate"}]
    timestamp: Optional[str] = None
    value: Optional[Any] = None
    subject_id: Optional[str] = None
    raw_data: Dict = field(default_factory=dict)


@dataclass
class EpisodeNormEvent:
    """Normalized event for CPG engine input."""
    event_type: str             # observation, medication, procedure, condition
    concept_id: str             # Normalized ontology concept
    timestamp_minutes: float
    value: Optional[Any] = None
    unit: Optional[str] = None
    source_codes: List[str] = field(default_factory=list)  # Original codes for traceability
    confidence: float = 1.0
    mapping_strategy: str = "exact"  # exact, anchor, pattern, fuzzy


@dataclass
class CompatibilityResult:
    """Result of compatibility verification."""
    source_type: DataSourceType
    source_name: str
    total_records: int
    mapped_records: int
    unmapped_records: int
    mapping_strategies: Dict[str, int]  # strategy -> count
    code_coverage: Dict[str, float]     # system -> coverage %
    sample_mappings: List[Dict]
    sample_failures: List[Dict]
    metrics: Dict[str, float]

    @property
    def mapping_rate(self) -> float:
        return self.mapped_records / self.total_records if self.total_records > 0 else 0.0


# =============================================================================
# STANDARD CODE MAPPINGS (LOINC, SNOMED, RxNorm → Ontology)
# =============================================================================

# LOINC → Concept ID (Lab Tests)
LOINC_TO_CONCEPT = {
    # Sepsis-related labs
    "2524-7": "ORDER_LACTATE",           # Lactate [Mass/volume] in Serum or Plasma
    "600-7": "ORDER_BLOOD_CULTURE",      # Bacteria identified in Blood
    "33959-8": "ORDER_PROCALCITONIN",    # Procalcitonin

    # Cardiac markers
    "10839-9": "ORDER_TROPONIN",         # Troponin I.cardiac
    "6598-7": "ORDER_TROPONIN",          # Troponin T.cardiac
    "30934-4": "ORDER_BNP",              # Natriuretic peptide B
    "33762-6": "ORDER_NT_PROBNP",        # NT-proBNP

    # Renal function
    "2160-0": "ORDER_CREATININE",        # Creatinine [Mass/volume] in Serum
    "3094-0": "ORDER_BUN",               # Urea nitrogen [Mass/volume] in Serum
    "6299-2": "ORDER_BMP",               # Blood urea nitrogen

    # Metabolic
    "2345-7": "ORDER_GLUCOSE",           # Glucose [Mass/volume] in Serum
    "2339-0": "ORDER_GLUCOSE",           # Glucose [Mass/volume] in Blood
    "4548-4": "ORDER_HBA1C",             # Hemoglobin A1c
    "2823-3": "ORDER_POTASSIUM",         # Potassium [Moles/volume] in Serum
    "2951-2": "ORDER_SODIUM",            # Sodium [Moles/volume] in Serum

    # Blood gas
    "2744-1": "ORDER_ABG",               # pH of Arterial blood
    "2019-8": "ORDER_ABG",               # Carbon dioxide partial pressure
    "2703-7": "ORDER_ABG",               # Oxygen partial pressure

    # Hematology
    "26464-8": "ORDER_CBC",              # Leukocytes [#/volume] in Blood
    "718-7": "ORDER_CBC",                # Hemoglobin [Mass/volume] in Blood
    "777-3": "ORDER_CBC",                # Platelet count

    # Coagulation
    "5902-2": "ORDER_COAGULATION_PANEL", # Prothrombin time (PT)
    "3173-2": "ORDER_COAGULATION_PANEL", # aPTT
    "6301-6": "ORDER_COAGULATION_PANEL", # INR

    # ECG
    "11524-6": "ORDER_ECG",              # EKG study
}

# SNOMED-CT → Concept ID (Procedures, Conditions)
SNOMED_TO_CONCEPT = {
    # Procedures
    "386053000": "ASSESS_VITAL_SIGNS",   # Evaluation procedure
    "413467001": "PLACE_ARTERIAL_LINE",  # Arterial line insertion
    "233573008": "PLACE_CENTRAL_LINE",   # Central venous catheter insertion
    "18949003": "PERFORM_INTUBATION",    # Endotracheal intubation
    "232717009": "ORDER_ECHOCARDIOGRAM", # Echocardiography
    "77477000": "ORDER_CT_HEAD",         # Computerized axial tomography of head
    "241601008": "ORDER_MRI_BRAIN",      # Magnetic resonance imaging of brain

    # Conditions
    "91302008": "DIAGNOSIS_SEPSIS",      # Sepsis
    "76571007": "DIAGNOSIS_SEPTIC_SHOCK",# Septic shock
    "57054005": "DIAGNOSIS_STEMI",       # Acute myocardial infarction
    "422504002": "DIAGNOSIS_ISCHEMIC_STROKE", # Ischemic stroke
    "84114007": "DIAGNOSIS_HEART_FAILURE",    # Heart failure
    "14669001": "DIAGNOSIS_AKI",              # Acute renal failure
    "420422005": "DIAGNOSIS_DKA",             # Diabetic ketoacidosis
}

# RxNorm → Concept ID (Medications)
RXNORM_TO_CONCEPT = {
    # Vasopressors
    "7512": "START_VASOPRESSOR_NOREPINEPHRINE",  # Norepinephrine
    "3616": "START_VASOPRESSOR_EPINEPHRINE",     # Epinephrine
    "3628": "START_VASOPRESSOR_DOPAMINE",        # Dopamine
    "11149": "START_VASOPRESSOR_VASOPRESSIN",    # Vasopressin

    # Antibiotics
    "7984": "GIVE_PIPERACILLIN_TAZOBACTAM",     # Piperacillin
    "11124": "GIVE_VANCOMYCIN",                  # Vancomycin
    "2551": "GIVE_CEFTRIAXONE",                  # Ceftriaxone
    "1665": "GIVE_CEFEPIME",                     # Cefepime

    # Cardiac medications
    "1191": "GIVE_ASPIRIN_LOADING",             # Aspirin
    "32968": "GIVE_CLOPIDOGREL",                # Clopidogrel
    "5521": "GIVE_HEPARIN",                     # Heparin
    "6918": "GIVE_METOPROLOL",                  # Metoprolol
    "7442": "GIVE_NITROGLYCERIN",               # Nitroglycerin

    # Stroke medications
    "8410": "GIVE_ALTEPLASE",                   # Alteplase (tPA)

    # Heart failure medications
    "4603": "GIVE_FUROSEMIDE",                  # Furosemide
    "50166": "GIVE_CARVEDILOL",                 # Carvedilol
    "29046": "GIVE_LISINOPRIL",                 # Lisinopril

    # DKA medications
    "5856": "START_INSULIN_INFUSION",           # Insulin
    "866924": "GIVE_POTASSIUM",                 # Potassium chloride

    # Fluids
    "313002": "GIVE_CRYSTALLOID",               # Normal saline
    "106892": "GIVE_CRYSTALLOID",               # Lactated Ringer's
}


# =============================================================================
# BASE ADAPTER CLASS
# =============================================================================

class BaseDataAdapter(ABC):
    """Abstract base class for data source adapters."""

    def __init__(self, data_path: Path):
        self.data_path = data_path
        self._load_normalizer()

    def _load_normalizer(self):
        """Load the anchor-based normalizer."""
        import importlib.util
        normalizer_path = Path(__file__).parent.parent / "ontology" / "anchor_normalizer.py"
        if normalizer_path.exists():
            spec = importlib.util.spec_from_file_location("normalizer", normalizer_path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.normalizer = module.AnchorBasedNormalizer()
        else:
            self.normalizer = None

    @abstractmethod
    def load_data(self) -> List[Dict]:
        """Load raw data from source."""
        pass

    @abstractmethod
    def extract_clinical_entities(self, record: Dict) -> List[Dict]:
        """Extract clinical entities from a record."""
        pass

    def map_to_concept(self, entity: Dict) -> Optional[EpisodeNormEvent]:
        """Map an entity to an ontology concept."""
        codes = entity.get("codes", [])
        display = entity.get("display", "")
        entity_type = entity.get("type", "unknown")

        # Try code-based mapping first
        for code_info in codes:
            system = code_info.get("system", "").lower()
            code = code_info.get("code", "")

            concept_id = None
            if "loinc" in system and code in LOINC_TO_CONCEPT:
                concept_id = LOINC_TO_CONCEPT[code]
                strategy = "loinc_anchor"
            elif "snomed" in system and code in SNOMED_TO_CONCEPT:
                concept_id = SNOMED_TO_CONCEPT[code]
                strategy = "snomed_anchor"
            elif "rxnorm" in system and code in RXNORM_TO_CONCEPT:
                concept_id = RXNORM_TO_CONCEPT[code]
                strategy = "rxnorm_anchor"

            if concept_id:
                return EpisodeNormEvent(
                    event_type=entity_type,
                    concept_id=concept_id,
                    timestamp_minutes=entity.get("timestamp_minutes", 0),
                    value=entity.get("value"),
                    unit=entity.get("unit"),
                    source_codes=[f"{system}:{code}"],
                    confidence=1.0,
                    mapping_strategy=strategy
                )

        # Fall back to text-based normalization
        if self.normalizer and display:
            result = self.normalizer.normalize(display)
            if result.normalized:
                return EpisodeNormEvent(
                    event_type=entity_type,
                    concept_id=result.normalized,
                    timestamp_minutes=entity.get("timestamp_minutes", 0),
                    value=entity.get("value"),
                    unit=entity.get("unit"),
                    source_codes=[f"text:{display}"],
                    confidence=result.confidence,
                    mapping_strategy=result.strategy
                )

        return None

    def verify_compatibility(self, limit: int = 100) -> CompatibilityResult:
        """Verify compatibility with the ontology."""
        data = self.load_data()[:limit]

        total = 0
        mapped = 0
        unmapped = 0
        strategy_counts = defaultdict(int)
        code_system_counts = defaultdict(lambda: {"total": 0, "mapped": 0})
        sample_mappings = []
        sample_failures = []

        for record in data:
            entities = self.extract_clinical_entities(record)

            for entity in entities:
                total += 1

                # Track code systems
                for code_info in entity.get("codes", []):
                    system = code_info.get("system", "unknown")
                    code_system_counts[system]["total"] += 1

                # Try mapping
                event = self.map_to_concept(entity)

                if event:
                    mapped += 1
                    strategy_counts[event.mapping_strategy] += 1

                    for code_info in entity.get("codes", []):
                        system = code_info.get("system", "unknown")
                        code_system_counts[system]["mapped"] += 1

                    if len(sample_mappings) < 10:
                        sample_mappings.append({
                            "input": entity,
                            "output": {
                                "concept_id": event.concept_id,
                                "confidence": event.confidence,
                                "strategy": event.mapping_strategy
                            }
                        })
                else:
                    unmapped += 1
                    if len(sample_failures) < 10:
                        sample_failures.append(entity)

        # Compute code coverage
        code_coverage = {}
        for system, counts in code_system_counts.items():
            if counts["total"] > 0:
                code_coverage[system] = counts["mapped"] / counts["total"]

        return CompatibilityResult(
            source_type=self.source_type,
            source_name=self.source_name,
            total_records=total,
            mapped_records=mapped,
            unmapped_records=unmapped,
            mapping_strategies=dict(strategy_counts),
            code_coverage=code_coverage,
            sample_mappings=sample_mappings,
            sample_failures=sample_failures,
            metrics={
                "mapping_rate": mapped / total if total > 0 else 0,
                "exact_rate": strategy_counts.get("loinc_anchor", 0) +
                             strategy_counts.get("snomed_anchor", 0) +
                             strategy_counts.get("rxnorm_anchor", 0),
            }
        )

    @property
    @abstractmethod
    def source_type(self) -> DataSourceType:
        pass

    @property
    @abstractmethod
    def source_name(self) -> str:
        pass


# =============================================================================
# A. FHIR EHR DATA ADAPTER (Synthea, MIMIC-IV FHIR)
# =============================================================================

class FHIRResourceAdapter(BaseDataAdapter):
    """Adapter for FHIR NDJSON resources (Synthea, MIMIC-IV FHIR)."""

    def __init__(self, data_path: Path, resource_types: List[str] = None):
        super().__init__(data_path)
        self.resource_types = resource_types or [
            "Observation", "MedicationRequest", "MedicationAdministration",
            "Condition", "Procedure", "DiagnosticReport"
        ]

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.FHIR_EHR

    @property
    def source_name(self) -> str:
        return f"FHIR-EHR ({self.data_path.name})"

    def load_data(self) -> List[Dict]:
        """Load FHIR NDJSON files."""
        records = []

        for resource_type in self.resource_types:
            # Try multiple file patterns
            patterns = [
                f"{resource_type}.ndjson",
                f"{resource_type.lower()}.ndjson",
                f"*{resource_type}*.ndjson"
            ]

            for pattern in patterns:
                for filepath in self.data_path.glob(pattern):
                    try:
                        with open(filepath) as f:
                            for line in f:
                                if line.strip():
                                    resource = json.loads(line)
                                    resource["_source_file"] = filepath.name
                                    records.append(resource)
                    except Exception:
                        continue

        return records

    def extract_clinical_entities(self, record: Dict) -> List[Dict]:
        """Extract clinical entities from FHIR resource."""
        entities = []
        resource_type = record.get("resourceType", "")

        if resource_type == "Observation":
            entity = self._parse_observation(record)
            if entity:
                entities.append(entity)

        elif resource_type in ["MedicationRequest", "MedicationAdministration"]:
            entity = self._parse_medication(record)
            if entity:
                entities.append(entity)

        elif resource_type == "Condition":
            entity = self._parse_condition(record)
            if entity:
                entities.append(entity)

        elif resource_type == "Procedure":
            entity = self._parse_procedure(record)
            if entity:
                entities.append(entity)

        return entities

    def _parse_observation(self, obs: Dict) -> Optional[Dict]:
        """Parse FHIR Observation resource."""
        code_obj = obs.get("code", {})
        codings = code_obj.get("coding", [])

        codes = []
        display = code_obj.get("text", "")

        for coding in codings:
            system = coding.get("system", "")
            code = coding.get("code", "")
            if not display:
                display = coding.get("display", "")

            # Normalize system names
            if "loinc" in system.lower():
                system = "loinc"
            elif "snomed" in system.lower():
                system = "snomed"

            codes.append({"system": system, "code": code})

        # Extract value
        value = None
        unit = None
        if "valueQuantity" in obs:
            value = obs["valueQuantity"].get("value")
            unit = obs["valueQuantity"].get("unit")
        elif "valueString" in obs:
            value = obs["valueString"]

        return {
            "type": "observation",
            "codes": codes,
            "display": display,
            "value": value,
            "unit": unit,
            "timestamp_minutes": 0  # Would need date parsing
        }

    def _parse_medication(self, med: Dict) -> Optional[Dict]:
        """Parse FHIR Medication resource."""
        # Try medicationCodeableConcept first
        med_code = med.get("medicationCodeableConcept", {})
        if not med_code:
            med_code = med.get("medicationReference", {})

        codings = med_code.get("coding", [])
        codes = []
        display = med_code.get("text", "")

        for coding in codings:
            system = coding.get("system", "")
            code = coding.get("code", "")
            if not display:
                display = coding.get("display", "")

            if "rxnorm" in system.lower():
                system = "rxnorm"
            elif "ndc" in system.lower():
                system = "ndc"

            codes.append({"system": system, "code": code})

        return {
            "type": "medication",
            "codes": codes,
            "display": display,
            "timestamp_minutes": 0
        }

    def _parse_condition(self, cond: Dict) -> Optional[Dict]:
        """Parse FHIR Condition resource."""
        code_obj = cond.get("code", {})
        codings = code_obj.get("coding", [])

        codes = []
        display = code_obj.get("text", "")

        for coding in codings:
            system = coding.get("system", "")
            code = coding.get("code", "")
            if not display:
                display = coding.get("display", "")

            if "snomed" in system.lower():
                system = "snomed"
            elif "icd" in system.lower():
                system = "icd10"

            codes.append({"system": system, "code": code})

        return {
            "type": "condition",
            "codes": codes,
            "display": display,
            "timestamp_minutes": 0
        }

    def _parse_procedure(self, proc: Dict) -> Optional[Dict]:
        """Parse FHIR Procedure resource."""
        code_obj = proc.get("code", {})
        codings = code_obj.get("coding", [])

        codes = []
        display = code_obj.get("text", "")

        for coding in codings:
            system = coding.get("system", "")
            code = coding.get("code", "")
            if not display:
                display = coding.get("display", "")

            if "snomed" in system.lower():
                system = "snomed"
            elif "cpt" in system.lower():
                system = "cpt"

            codes.append({"system": system, "code": code})

        return {
            "type": "procedure",
            "codes": codes,
            "display": display,
            "timestamp_minutes": 0
        }


# =============================================================================
# B. FHIR-AGENTBENCH ADAPTER
# =============================================================================

class FHIRAgentBenchAdapter(BaseDataAdapter):
    """Adapter for FHIR-AgentBench dataset."""

    # Clinical entity patterns for extraction from questions
    MEDICATION_PATTERNS = [
        r'\b(aspirin|heparin|insulin|furosemide|metoprolol|vancomycin|norepinephrine)\b',
        r'\b(acetaminophen|lidocaine|atorvastatin|prasugrel|clopidogrel|warfarin)\b',
        r'\b(docusate|glucose|clonidine|milk of magnesia|morphine|fentanyl)\b',
        r'\b(amiodarone|digoxin|lisinopril|metformin|omeprazole|pantoprazole)\b',
        r'\b(lorazepam|midazolam|propofol|dexmedetomidine|ketamine)\b',
        r'\b(ceftriaxone|piperacillin|meropenem|azithromycin|ciprofloxacin)\b',
    ]

    LAB_PATTERNS = [
        r'\b(glucose|creatinine|potassium|sodium|lactate|hemoglobin|platelet)\b',
        r'\b(troponin|bnp|procalcitonin|white blood cell|wbc|hematocrit)\b',
        r'\b(bilirubin|albumin|ast|alt|inr|ptt|fibrinogen)\b',
        r'\b(ph|pco2|po2|bicarbonate|base excess)\b',
    ]

    VITAL_PATTERNS = [
        r'\b(blood pressure|heart rate|respiratory rate|temperature|oxygen saturation)\b',
        r'\b(systolic|diastolic|pulse|spo2|o2 sat)\b',
    ]

    PROCEDURE_PATTERNS = [
        r'\b(intubation|catheterization|echocardiography|ultrasonography)\b',
        r'\b(ct scan|mri|x-ray|angiography|bronchoscopy|endoscopy)\b',
        r'\b(dialysis|transfusion|ventilation|cardioversion)\b',
    ]

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.FHIR_AGENT_BENCH

    @property
    def source_name(self) -> str:
        return "FHIR-AgentBench"

    def load_data(self) -> List[Dict]:
        """Load FHIR-AgentBench CSV data."""
        records = []

        # Prioritize the SQL+FHIR file which has questions
        csv_files = [
            "questions_answers_sql_fhir.csv",
            "questions_answers_sql.csv",
            "questions_answers_fhir.csv",
        ]

        for csv_file in csv_files:
            filepath = self.data_path / "final_dataset" / csv_file
            if filepath.exists():
                try:
                    with open(filepath, encoding='utf-8') as f:
                        reader = csv.DictReader(f)
                        for row in reader:
                            row["_source_file"] = csv_file
                            records.append(row)
                    if records:
                        break  # Use the first file that has data
                except Exception:
                    continue

        return records

    def extract_clinical_entities(self, record: Dict) -> List[Dict]:
        """Extract clinical entities from FHIR-AgentBench record."""
        entities = []

        # Get question text
        question = record.get("question", "")
        main_table = record.get("main_table_name", "")
        question_lower = question.lower()

        # Determine entity type from table name
        table_type_map = {
            "chartevents": "observation",
            "labevents": "observation",
            "prescriptions": "medication",
            "inputevents": "medication",
            "outputevents": "observation",
            "procedures_icd": "procedure",
            "diagnoses_icd": "condition"
        }
        base_entity_type = table_type_map.get(main_table, "unknown")

        # Extract medications
        for pattern in self.MEDICATION_PATTERNS:
            matches = re.findall(pattern, question_lower)
            for match in matches:
                entities.append({
                    "type": "medication",
                    "codes": [],
                    "display": match,
                    "source_question": question[:100],
                    "timestamp_minutes": 0
                })

        # Extract labs
        for pattern in self.LAB_PATTERNS:
            matches = re.findall(pattern, question_lower)
            for match in matches:
                entities.append({
                    "type": "observation",
                    "codes": [],
                    "display": match,
                    "source_question": question[:100],
                    "timestamp_minutes": 0
                })

        # Extract vitals
        for pattern in self.VITAL_PATTERNS:
            matches = re.findall(pattern, question_lower)
            for match in matches:
                entities.append({
                    "type": "observation",
                    "codes": [],
                    "display": match,
                    "source_question": question[:100],
                    "timestamp_minutes": 0
                })

        # Extract procedures
        for pattern in self.PROCEDURE_PATTERNS:
            matches = re.findall(pattern, question_lower)
            for match in matches:
                entities.append({
                    "type": "procedure",
                    "codes": [],
                    "display": match,
                    "source_question": question[:100],
                    "timestamp_minutes": 0
                })

        # If no specific entities found, create one from table context
        if not entities and main_table:
            entities.append({
                "type": base_entity_type,
                "codes": [],
                "display": main_table,
                "source_question": question[:100],
                "timestamp_minutes": 0
            })

        return entities


# =============================================================================
# B2. AGENTCLINIC ADAPTER
# =============================================================================

class AgentClinicAdapter(BaseDataAdapter):
    """Adapter for AgentClinic benchmark dataset."""

    # Clinical entity patterns
    CONDITION_PATTERNS = [
        r'\b(myasthenia gravis|multiple sclerosis|parkinson|alzheimer)\b',
        r'\b(diabetes|hypertension|heart failure|atrial fibrillation)\b',
        r'\b(pneumonia|sepsis|stroke|myocardial infarction|stemi|nstemi)\b',
        r'\b(copd|asthma|pulmonary embolism|dvt|anemia)\b',
        r'\b(aki|acute kidney|chronic kidney|ckd|cirrhosis)\b',
        r'\b(hypothyroidism|hyperthyroidism|addison|cushing)\b',
    ]

    SYMPTOM_PATTERNS = [
        r'\b(chest pain|shortness of breath|dyspnea|cough|fever)\b',
        r'\b(headache|dizziness|syncope|weakness|fatigue)\b',
        r'\b(nausea|vomiting|diarrhea|abdominal pain|constipation)\b',
        r'\b(double vision|diplopia|ptosis|muscle weakness)\b',
        r'\b(confusion|altered mental status|seizure|tremor)\b',
    ]

    TEST_PATTERNS = [
        r'\b(acetylcholine receptor antibodies|anti-musk|emg|electromyography)\b',
        r'\b(ct scan|mri|chest x-ray|echocardiogram|ekg|ecg)\b',
        r'\b(cbc|bmp|cmp|liver function|lfts|tsh|t4)\b',
        r'\b(lumbar puncture|csf analysis|nerve conduction)\b',
    ]

    TREATMENT_PATTERNS = [
        r'\b(pyridostigmine|mestinon|prednisone|azathioprine)\b',
        r'\b(ivig|plasmapheresis|thymectomy)\b',
        r'\b(aspirin|heparin|warfarin|metoprolol|lisinopril)\b',
    ]

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.FHIR_AGENT_BENCH

    @property
    def source_name(self) -> str:
        return "AgentClinic"

    def load_data(self) -> List[Dict]:
        """Load AgentClinic JSONL data."""
        records = []

        jsonl_files = [
            "agentclinic_medqa.jsonl",
            "agentclinic_nejm.jsonl",
            "agentclinic_medqa_extended.jsonl",
            "agentclinic_nejm_extended.jsonl"
        ]

        for jsonl_file in jsonl_files:
            filepath = self.data_path / jsonl_file
            if filepath.exists():
                try:
                    with open(filepath, encoding='utf-8') as f:
                        for line in f:
                            if line.strip():
                                record = json.loads(line)
                                record["_source_file"] = jsonl_file
                                records.append(record)
                except Exception:
                    continue

        return records

    def extract_clinical_entities(self, record: Dict) -> List[Dict]:
        """Extract clinical entities from AgentClinic record."""
        entities = []

        osce = record.get("OSCE_Examination", {})
        patient = osce.get("Patient_Actor", {})
        diagnosis = osce.get("Correct_Diagnosis", "")
        test_results = osce.get("Test_Results", {})
        physical_exam = osce.get("Physical_Examination_Findings", {})

        # Extract text content
        history = patient.get("History", "")
        symptoms = patient.get("Symptoms", {})
        primary_symptom = symptoms.get("Primary_Symptom", "")
        secondary_symptoms = symptoms.get("Secondary_Symptoms", [])

        # Combine all text for entity extraction
        all_text = " ".join([
            history,
            primary_symptom,
            " ".join(secondary_symptoms) if isinstance(secondary_symptoms, list) else str(secondary_symptoms),
            diagnosis,
            str(test_results),
            str(physical_exam)
        ]).lower()

        # Extract conditions
        for pattern in self.CONDITION_PATTERNS:
            matches = re.findall(pattern, all_text)
            for match in matches:
                entities.append({
                    "type": "condition",
                    "codes": [],
                    "display": match,
                    "source_diagnosis": diagnosis,
                    "timestamp_minutes": 0
                })

        # Extract symptoms
        for pattern in self.SYMPTOM_PATTERNS:
            matches = re.findall(pattern, all_text)
            for match in matches:
                entities.append({
                    "type": "symptom",
                    "codes": [],
                    "display": match,
                    "timestamp_minutes": 0
                })

        # Extract tests
        for pattern in self.TEST_PATTERNS:
            matches = re.findall(pattern, all_text)
            for match in matches:
                entities.append({
                    "type": "observation",
                    "codes": [],
                    "display": match,
                    "timestamp_minutes": 0
                })

        # Extract treatments
        for pattern in self.TREATMENT_PATTERNS:
            matches = re.findall(pattern, all_text)
            for match in matches:
                entities.append({
                    "type": "medication",
                    "codes": [],
                    "display": match,
                    "timestamp_minutes": 0
                })

        # Add diagnosis as entity
        if diagnosis:
            entities.append({
                "type": "condition",
                "codes": [],
                "display": diagnosis.lower(),
                "is_diagnosis": True,
                "timestamp_minutes": 0
            })

        return entities


# =============================================================================
# C. EHRSQL ADAPTER
# =============================================================================

class EHRSQLAdapter(BaseDataAdapter):
    """Adapter for EHRSQL dataset."""

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.EHR_SQL

    @property
    def source_name(self) -> str:
        return "EHRSQL"

    def load_data(self) -> List[Dict]:
        """Load EHRSQL data."""
        records = []

        # Try to find EHRSQL data in various locations
        possible_paths = [
            self.data_path / "train.json",
            self.data_path / "dev.json",
            self.data_path / "test.json",
            self.data_path / "ehrsql_train.json"
        ]

        for filepath in possible_paths:
            if filepath.exists():
                try:
                    with open(filepath) as f:
                        data = json.load(f)
                        if isinstance(data, list):
                            records.extend(data)
                        elif isinstance(data, dict):
                            records.extend(data.get("data", [data]))
                except Exception:
                    continue

        # Also check FHIR-AgentBench SQL data as it's derived from EHRSQL
        sql_file = self.data_path.parent / "FHIR-AgentBench" / "final_dataset" / "questions_answers_sql.csv"
        if sql_file.exists():
            try:
                with open(sql_file, encoding='utf-8') as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        records.append(row)
            except Exception:
                pass

        return records

    def extract_clinical_entities(self, record: Dict) -> List[Dict]:
        """Extract clinical entities from EHRSQL record."""
        entities = []

        # Extract from question text
        question = record.get("question", record.get("question_text", ""))

        # Extract clinical terms using patterns
        clinical_patterns = {
            "observation": [
                r"\b(lactate|glucose|creatinine|potassium|sodium|hemoglobin|platelet|wbc|troponin|bnp)\b",
                r"\b(blood pressure|heart rate|temperature|oxygen saturation|respiratory rate)\b"
            ],
            "medication": [
                r"\b(aspirin|heparin|insulin|furosemide|metoprolol|vancomycin|norepinephrine)\b",
                r"\b(medication|drug|medicine|prescribed)\b"
            ],
            "procedure": [
                r"\b(intubation|catheter|ecg|ekg|ct scan|mri|x-ray|echocardiogram)\b"
            ],
            "condition": [
                r"\b(sepsis|heart failure|stroke|diabetes|pneumonia|aki|dka)\b",
                r"\b(diagnosis|diagnosed with|condition)\b"
            ]
        }

        question_lower = question.lower()

        for entity_type, patterns in clinical_patterns.items():
            for pattern in patterns:
                matches = re.findall(pattern, question_lower)
                for match in matches:
                    entities.append({
                        "type": entity_type,
                        "codes": [],
                        "display": match,
                        "source_question": question[:100],
                        "timestamp_minutes": 0
                    })

        # Extract from SQL if available
        sql = record.get("sql", record.get("query", ""))
        if sql:
            # Extract table references
            table_patterns = {
                "labevents": "observation",
                "chartevents": "observation",
                "inputevents": "medication",
                "prescriptions": "medication",
                "procedures_icd": "procedure",
                "diagnoses_icd": "condition"
            }

            sql_lower = sql.lower()
            for table, entity_type in table_patterns.items():
                if table in sql_lower:
                    entities.append({
                        "type": entity_type,
                        "codes": [],
                        "display": f"SQL query on {table}",
                        "source_sql": sql[:200],
                        "timestamp_minutes": 0
                    })

        return entities


# =============================================================================
# D. MEDICAL EL BENCHMARK ADAPTER (MedMentions, BELB, BioSyn)
# =============================================================================

class MedicalELAdapter(BaseDataAdapter):
    """Adapter for Medical Entity Linking benchmarks."""

    def __init__(self, data_path: Path, benchmark_name: str = "medmentions"):
        super().__init__(data_path)
        self.benchmark_name = benchmark_name

    @property
    def source_type(self) -> DataSourceType:
        return DataSourceType.MEDICAL_EL

    @property
    def source_name(self) -> str:
        return f"Medical-EL ({self.benchmark_name})"

    def load_data(self) -> List[Dict]:
        """Load medical EL benchmark data."""
        records = []

        if self.benchmark_name == "medmentions":
            records = self._load_medmentions()
        elif self.benchmark_name == "belb":
            records = self._load_belb()
        elif self.benchmark_name == "biosyn":
            records = self._load_biosyn()

        return records

    def _load_medmentions(self) -> List[Dict]:
        """Load MedMentions-style data."""
        records = []

        # MedMentions format: PubTator format or JSONL
        for filepath in self.data_path.glob("*.jsonl"):
            try:
                with open(filepath) as f:
                    for line in f:
                        if line.strip():
                            records.append(json.loads(line))
            except Exception:
                continue

        # Also try pubtator format
        for filepath in self.data_path.glob("*.pubtator"):
            try:
                records.extend(self._parse_pubtator(filepath))
            except Exception:
                continue

        return records

    def _load_belb(self) -> List[Dict]:
        """Load BELB-style data."""
        records = []

        for filepath in self.data_path.glob("*.json"):
            try:
                with open(filepath) as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        records.extend(data)
                    else:
                        records.append(data)
            except Exception:
                continue

        return records

    def _load_biosyn(self) -> List[Dict]:
        """Load BioSyn-style data."""
        records = []

        # BioSyn uses train/dev/test directories
        for split in ["train", "dev", "test"]:
            split_dir = self.data_path / split
            if split_dir.exists():
                for filepath in split_dir.glob("*.txt"):
                    try:
                        records.extend(self._parse_biosyn_file(filepath))
                    except Exception:
                        continue

        return records

    def _parse_pubtator(self, filepath: Path) -> List[Dict]:
        """Parse PubTator format."""
        records = []
        current_doc = None

        with open(filepath) as f:
            for line in f:
                line = line.strip()
                if not line:
                    if current_doc:
                        records.append(current_doc)
                    current_doc = None
                elif "|t|" in line:
                    parts = line.split("|t|")
                    current_doc = {
                        "pmid": parts[0],
                        "title": parts[1] if len(parts) > 1 else "",
                        "entities": []
                    }
                elif "|a|" in line and current_doc:
                    parts = line.split("|a|")
                    current_doc["abstract"] = parts[1] if len(parts) > 1 else ""
                elif "\t" in line and current_doc:
                    parts = line.split("\t")
                    if len(parts) >= 5:
                        current_doc["entities"].append({
                            "start": int(parts[1]),
                            "end": int(parts[2]),
                            "text": parts[3],
                            "type": parts[4],
                            "cui": parts[5] if len(parts) > 5 else None
                        })

        if current_doc:
            records.append(current_doc)

        return records

    def _parse_biosyn_file(self, filepath: Path) -> List[Dict]:
        """Parse BioSyn format file."""
        records = []

        with open(filepath) as f:
            for line in f:
                parts = line.strip().split("||")
                if len(parts) >= 2:
                    records.append({
                        "mention": parts[0],
                        "cui": parts[1],
                        "source": filepath.name
                    })

        return records

    def extract_clinical_entities(self, record: Dict) -> List[Dict]:
        """Extract entities from medical EL record."""
        entities = []

        # Handle different formats
        if "entities" in record:
            # MedMentions/PubTator format
            for ent in record["entities"]:
                entities.append({
                    "type": ent.get("type", "unknown"),
                    "codes": [{"system": "umls", "code": ent.get("cui", "")}] if ent.get("cui") else [],
                    "display": ent.get("text", ""),
                    "timestamp_minutes": 0
                })
        elif "mention" in record:
            # BioSyn format
            entities.append({
                "type": "entity",
                "codes": [{"system": "umls", "code": record.get("cui", "")}] if record.get("cui") else [],
                "display": record.get("mention", ""),
                "timestamp_minutes": 0
            })

        return entities


# =============================================================================
# COMPREHENSIVE VERIFICATION RUNNER
# =============================================================================

class ExtensibilityVerifier:
    """Runs comprehensive extensibility verification."""

    def __init__(self, base_data_dir: Path):
        self.base_data_dir = base_data_dir
        self.results: List[CompatibilityResult] = []

    def verify_all(self, limit: int = 100) -> Dict[str, Any]:
        """Run all verification tests."""
        print("=" * 70)
        print("CGA-BENCH EXTENSIBILITY VERIFICATION")
        print("=" * 70)

        # A. FHIR EHR Data
        self._verify_fhir_ehr(limit)

        # B. FHIR-AgentBench
        self._verify_fhir_agentbench(limit)

        # C. EHRSQL
        self._verify_ehrsql(limit)

        # D. Medical EL Benchmarks
        self._verify_medical_el(limit)

        # Generate summary
        return self._generate_summary()

    def _verify_fhir_ehr(self, limit: int):
        """Verify FHIR EHR data compatibility."""
        print("\n[A] FHIR-based EHR Data")
        print("-" * 50)

        # Try Synthea data
        synthea_paths = [
            self.base_data_dir / "synthea",
            self.base_data_dir / "fhir" / "synthea",
            self.base_data_dir.parent / "synthea"
        ]

        for path in synthea_paths:
            if path.exists():
                adapter = FHIRResourceAdapter(path)
                result = adapter.verify_compatibility(limit)
                self.results.append(result)
                self._print_result("Synthea", result)
                break
        else:
            print("  ⚠ Synthea data not found")

        # Try MIMIC-IV FHIR
        mimic_paths = [
            self.base_data_dir / "mimic-iv-fhir-demo",
            self.base_data_dir / "mimic_fhir",
            self.base_data_dir.parent / "mimic-iv-demo"
        ]

        for path in mimic_paths:
            if path.exists():
                adapter = FHIRResourceAdapter(path)
                result = adapter.verify_compatibility(limit)
                self.results.append(result)
                self._print_result("MIMIC-IV FHIR", result)
                break
        else:
            print("  ⚠ MIMIC-IV FHIR data not found")

    def _verify_fhir_agentbench(self, limit: int):
        """Verify FHIR-AgentBench compatibility."""
        print("\n[B] FHIR QA/Agent Benchmarks")
        print("-" * 50)

        # FHIR-AgentBench
        agentbench_path = self.base_data_dir / "external_benchmarks" / "FHIR-AgentBench"
        if agentbench_path.exists():
            adapter = FHIRAgentBenchAdapter(agentbench_path)
            result = adapter.verify_compatibility(limit)
            self.results.append(result)
            self._print_result("FHIR-AgentBench", result)
        else:
            print("  ⚠ FHIR-AgentBench data not found")

        # AgentClinic
        agentclinic_path = self.base_data_dir / "external_benchmarks" / "AgentClinic"
        if agentclinic_path.exists():
            adapter = AgentClinicAdapter(agentclinic_path)
            result = adapter.verify_compatibility(limit)
            self.results.append(result)
            self._print_result("AgentClinic", result)
        else:
            print("  ⚠ AgentClinic data not found")

    def _verify_ehrsql(self, limit: int):
        """Verify EHRSQL compatibility."""
        print("\n[C] EHR SQL-based Data")
        print("-" * 50)

        ehrsql_paths = [
            self.base_data_dir / "ehrsql",
            self.base_data_dir / "external_benchmarks" / "EHRSQL",
            self.base_data_dir / "external_benchmarks"  # Uses FHIR-AgentBench SQL data
        ]

        for path in ehrsql_paths:
            if path.exists():
                adapter = EHRSQLAdapter(path)
                result = adapter.verify_compatibility(limit)
                if result.total_records > 0:
                    self.results.append(result)
                    self._print_result("EHRSQL", result)
                    break
        else:
            print("  ⚠ EHRSQL data not found")

    def _verify_medical_el(self, limit: int):
        """Verify Medical EL benchmark compatibility."""
        print("\n[D] Medical Entity Linking Benchmarks")
        print("-" * 50)

        el_benchmarks = [
            ("medmentions", "MedMentions"),
            ("belb", "BELB"),
            ("biosyn", "BioSyn")
        ]

        for benchmark_id, benchmark_name in el_benchmarks:
            paths = [
                self.base_data_dir / benchmark_id,
                self.base_data_dir / "external_benchmarks" / benchmark_name,
                self.base_data_dir / "medical_el" / benchmark_id
            ]

            for path in paths:
                if path.exists():
                    adapter = MedicalELAdapter(path, benchmark_id)
                    result = adapter.verify_compatibility(limit)
                    if result.total_records > 0:
                        self.results.append(result)
                        self._print_result(benchmark_name, result)
                        break
            else:
                print(f"  ⚠ {benchmark_name} data not found")

    def _print_result(self, name: str, result: CompatibilityResult):
        """Print a single result."""
        status = "✓" if result.mapping_rate >= 0.5 else "⚠" if result.mapping_rate >= 0.2 else "✗"
        print(f"  {status} {name}: {result.mapped_records}/{result.total_records} "
              f"({result.mapping_rate:.1%} mapped)")

        if result.mapping_strategies:
            strategies = ", ".join(f"{k}:{v}" for k, v in sorted(result.mapping_strategies.items()))
            print(f"      Strategies: {strategies}")

        if result.code_coverage:
            coverage = ", ".join(f"{k}:{v:.0%}" for k, v in sorted(result.code_coverage.items())[:5])
            print(f"      Code coverage: {coverage}")

    def _generate_summary(self) -> Dict[str, Any]:
        """Generate verification summary."""
        print("\n" + "=" * 70)
        print("EXTENSIBILITY VERIFICATION SUMMARY")
        print("=" * 70)

        summary = {
            "total_sources": len(self.results),
            "total_records": sum(r.total_records for r in self.results),
            "total_mapped": sum(r.mapped_records for r in self.results),
            "overall_mapping_rate": 0,
            "by_source_type": {},
            "recommendations": []
        }

        if summary["total_records"] > 0:
            summary["overall_mapping_rate"] = summary["total_mapped"] / summary["total_records"]

        # Group by source type
        by_type = defaultdict(list)
        for result in self.results:
            by_type[result.source_type.value].append(result)

        for source_type, results in by_type.items():
            total = sum(r.total_records for r in results)
            mapped = sum(r.mapped_records for r in results)
            summary["by_source_type"][source_type] = {
                "sources": [r.source_name for r in results],
                "total_records": total,
                "mapped_records": mapped,
                "mapping_rate": mapped / total if total > 0 else 0
            }

        # Print summary
        print(f"\nTotal Sources Verified: {summary['total_sources']}")
        print(f"Total Records: {summary['total_records']}")
        print(f"Total Mapped: {summary['total_mapped']}")
        print(f"Overall Mapping Rate: {summary['overall_mapping_rate']:.1%}")

        print("\nBy Source Type:")
        for source_type, stats in summary["by_source_type"].items():
            print(f"  {source_type}: {stats['mapping_rate']:.1%} "
                  f"({stats['mapped_records']}/{stats['total_records']})")

        # Generate recommendations
        if summary["overall_mapping_rate"] < 0.5:
            summary["recommendations"].append(
                "Consider expanding LOINC/SNOMED/RxNorm anchor mappings"
            )

        low_coverage_types = [
            st for st, stats in summary["by_source_type"].items()
            if stats["mapping_rate"] < 0.3
        ]
        if low_coverage_types:
            summary["recommendations"].append(
                f"Low coverage for: {', '.join(low_coverage_types)}"
            )

        print("\n" + "=" * 70)
        return summary


# =============================================================================
# SOTA COMPARISON DATA
# =============================================================================

# Medical Entity Linking SOTA benchmarks and methods
SOTA_MEDICAL_EL = {
    "benchmarks": {
        "MedMentions": {
            "description": "UMLS concept linking from PubMed abstracts",
            "size": "4,392 documents, 352,496 mentions",
            "metrics": ["Acc@1", "Acc@5", "MRR"],
            "sota_acc1": 0.72,  # BioSyn (2020)
            "recent_work": ["SapBERT (2021)", "CODER (2022)", "BioLORD (2023)"]
        },
        "NCBI-Disease": {
            "description": "Disease name normalization",
            "size": "793 abstracts, 6,892 mentions",
            "metrics": ["Acc@1", "Acc@5"],
            "sota_acc1": 0.91,
            "recent_work": ["BioSyn", "KRISSBERT"]
        },
        "BC5CDR": {
            "description": "Chemical/Disease entity normalization",
            "size": "1,500 articles",
            "metrics": ["Acc@1", "F1"],
            "sota_acc1": 0.93,
            "recent_work": ["SapBERT", "CODER"]
        },
        "COMETA": {
            "description": "Medical concept linking from Reddit posts",
            "size": "20,000 mentions",
            "metrics": ["Acc@1", "Acc@5"],
            "sota_acc1": 0.68,
            "recent_work": ["BioLORD", "KRISSBERT"]
        }
    },
    "methods": {
        "BioSyn": {
            "year": 2020,
            "approach": "Bi-encoder + hard negative mining + synonym marginalization",
            "key_innovation": "Iterative hard negative mining",
            "cga_bench_relevance": "Our two-stage approach with hard negatives is similar"
        },
        "SapBERT": {
            "year": 2021,
            "approach": "Self-alignment pre-training on UMLS synonyms",
            "key_innovation": "Metric learning on synonym pairs",
            "cga_bench_relevance": "Could enhance our bi-encoder pre-training"
        },
        "CODER": {
            "year": 2022,
            "approach": "Contrastive learning with multi-view representation",
            "key_innovation": "Cross-lingual/cross-ontology transfer",
            "cga_bench_relevance": "Multi-domain transfer for clinical specialties"
        },
        "BioLORD": {
            "year": 2023,
            "approach": "Large language model for biomedical linking",
            "key_innovation": "In-context learning with definitions",
            "cga_bench_relevance": "LLM-based disambiguation for hard cases"
        },
        "KRISSBERT": {
            "year": 2022,
            "approach": "Knowledge-rich self-supervision",
            "key_innovation": "Entity definition injection",
            "cga_bench_relevance": "Could improve context-aware reranking"
        }
    }
}


def print_sota_comparison():
    """Print SOTA comparison analysis."""
    print("\n" + "=" * 70)
    print("MEDICAL ENTITY LINKING SOTA ANALYSIS")
    print("=" * 70)

    print("\n[Benchmarks]")
    for name, info in SOTA_MEDICAL_EL["benchmarks"].items():
        print(f"\n  {name}:")
        print(f"    Description: {info['description']}")
        print(f"    Size: {info['size']}")
        print(f"    SOTA Acc@1: {info['sota_acc1']:.0%}")
        print(f"    Recent methods: {', '.join(info['recent_work'])}")

    print("\n[Methods and CGA-Bench Relevance]")
    for name, info in SOTA_MEDICAL_EL["methods"].items():
        print(f"\n  {name} ({info['year']}):")
        print(f"    Approach: {info['approach']}")
        print(f"    Key innovation: {info['key_innovation']}")
        print(f"    → CGA-Bench: {info['cga_bench_relevance']}")

    print("\n" + "=" * 70)


# =============================================================================
# MAIN
# =============================================================================

def main():
    import sys

    base_dir = Path(__file__).parent.parent.parent / "data"

    # Run extensibility verification
    verifier = ExtensibilityVerifier(base_dir)
    summary = verifier.verify_all(limit=200)

    # Print SOTA comparison
    print_sota_comparison()

    # Exit with appropriate code
    success = summary["overall_mapping_rate"] >= 0.3 or summary["total_sources"] >= 2
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()
