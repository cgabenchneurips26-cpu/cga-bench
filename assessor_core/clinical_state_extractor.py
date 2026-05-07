"""
ClinicalStateExtractor: Extract clinical state from vignette text.

In stub mode (no LLM provider), returns sensible defaults.
When an LLM provider is available, can parse vignettes into structured data.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns

logger = logging.getLogger(__name__)

# Default vital signs for stub mode
_STUB_VITALS = {
    "heart_rate": 80.0,
    "blood_pressure_systolic": 120.0,
    "blood_pressure_diastolic": 80.0,
    "respiratory_rate": 16.0,
    "temperature": 37.0,
    "oxygen_saturation": 98.0,
}


class ClinicalStateExtractor:
    """Extracts structured clinical state from vignette text.

    In stub mode (default, no LLM), returns conservative defaults.
    """

    def __init__(self, llm_provider: Any = None):
        self.llm_provider = llm_provider

    def extract(self, vignette: str) -> Dict[str, Any]:
        """Extract clinical state from a vignette.

        Args:
            vignette: Free-text clinical scenario description.

        Returns:
            dict with keys: state_id, age, sex, chief_complaint,
            vitals, lab_results, medications_given, procedures_done,
            comorbidities, allergies, working_diagnosis.
        """
        if self.llm_provider is None:
            return self._stub_extract(vignette)

        return self._llm_extract(vignette)

    def _stub_extract(self, vignette: str) -> Dict[str, Any]:
        """Stub mode: parse basic info heuristically, fill defaults."""
        chief_complaint = vignette[:100] if vignette else ""

        return {
            "state_id": "extracted_0",
            "age": 50,
            "sex": "unknown",
            "chief_complaint": chief_complaint,
            "vitals": _STUB_VITALS.copy(),
            "lab_results": [],
            "medications_given": [],
            "procedures_done": [],
            "comorbidities": [],
            "allergies": [],
            "working_diagnosis": "",
        }

    def _llm_extract(self, vignette: str) -> Dict[str, Any]:
        prompt = (
            "Extract structured clinical data from this patient vignette.\n\n"
            f"VIGNETTE:\n{vignette[:3000]}\n\n"
            "Output ONLY a JSON object with these fields:\n"
            '{"age": <int>, "sex": "<male|female|unknown>", '
            '"chief_complaint": "<brief>", '
            '"vitals": {"heart_rate": <float>, "blood_pressure_systolic": <float>, '
            '"blood_pressure_diastolic": <float>, "respiratory_rate": <float>, '
            '"temperature": <float>, "oxygen_saturation": <float>}, '
            '"comorbidities": [<strings>], "allergies": [<strings>], '
            '"working_diagnosis": "<string>"}'
        )

        try:
            response = self.llm_provider.complete(prompt)
            content = response if isinstance(response, str) else str(response)
            match = re.search(r"\{[\s\S]*\}", content)
            if match:
                parsed = json.loads(match.group())
                base = self._stub_extract(vignette)
                if isinstance(parsed.get("age"), (int, float)):
                    base["age"] = int(parsed["age"])
                if isinstance(parsed.get("sex"), str) and parsed["sex"] in ("male", "female", "unknown"):
                    base["sex"] = parsed["sex"]
                if isinstance(parsed.get("chief_complaint"), str) and parsed["chief_complaint"]:
                    base["chief_complaint"] = parsed["chief_complaint"]
                if isinstance(parsed.get("vitals"), dict):
                    for key in _STUB_VITALS:
                        val = parsed["vitals"].get(key)
                        if isinstance(val, (int, float)) and val > 0:
                            base["vitals"][key] = float(val)
                if isinstance(parsed.get("comorbidities"), list):
                    base["comorbidities"] = [str(c) for c in parsed["comorbidities"] if c]
                if isinstance(parsed.get("allergies"), list):
                    base["allergies"] = [str(a) for a in parsed["allergies"] if a]
                if isinstance(parsed.get("working_diagnosis"), str):
                    base["working_diagnosis"] = parsed["working_diagnosis"]
                return base
        except Exception as exc:
            logger.warning("ClinicalStateExtractor: LLM extraction failed (%s), falling back to heuristic", exc)

        return self._heuristic_extract(vignette)

    def _heuristic_extract(self, vignette: str) -> Dict[str, Any]:
        base = self._stub_extract(vignette)
        if not vignette:
            return base

        lower = vignette.lower()

        age_match = re.search(r"(\d{1,3})\s*[-–]?\s*year\s*[-–]?\s*old", lower)
        if age_match:
            age_val = int(age_match.group(1))
            if 0 < age_val < 120:
                base["age"] = age_val

        if "female" in lower or "woman" in lower:
            base["sex"] = "female"
        elif "male" in lower or " man " in lower or lower.startswith("man "):
            base["sex"] = "male"

        vital_patterns = {
            "heart_rate": (r"(?:hr|heart\s*rate)[:\s]*(\d{2,3})", 30, 250),
            "blood_pressure_systolic": (r"(?:bp|blood\s*pressure)[:\s]*(\d{2,3})\s*/", 50, 300),
            "blood_pressure_diastolic": (r"(?:bp|blood\s*pressure)[:\s]*\d{2,3}\s*/\s*(\d{2,3})", 20, 200),
            "respiratory_rate": (r"(?:rr|resp(?:iratory)?\s*rate)[:\s]*(\d{1,2})", 4, 60),
            "temperature": (r"(?:temp(?:erature)?)[:\s]*([\d.]+)", 34, 43),
            "oxygen_saturation": (r"(?:spo2|o2\s*sat|oxygen\s*sat(?:uration)?)[:\s]*([\d.]+)", 50, 100),
        }
        for key, (pattern, lo, hi) in vital_patterns.items():
            m = re.search(pattern, lower)
            if m:
                val = float(m.group(1))
                if lo <= val <= hi:
                    base["vitals"][key] = val

        known = [
            "diabetes", "hypertension", "copd", "asthma", "heart failure",
            "ckd", "chronic kidney disease", "atrial fibrillation", "cad",
            "coronary artery disease", "stroke", "obesity",
        ]
        base["comorbidities"] = [c for c in known if c in lower]

        allergy_match = re.search(r"allerg(?:y|ies)\s*(?:to|:)\s*([^.;]+)", lower)
        if allergy_match:
            base["allergies"] = [a.strip() for a in allergy_match.group(1).split(",") if a.strip()]

        return base

    @staticmethod
    def to_patient_state(extracted: Dict[str, Any]) -> PatientState:
        """Convert extraction result to PatientState.

        Args:
            extracted: dict from extract().

        Returns:
            PatientState instance.
        """
        vitals_data = extracted.get("vitals", _STUB_VITALS)
        vitals = VitalSigns(
            heart_rate=vitals_data.get("heart_rate"),
            blood_pressure_systolic=vitals_data.get("blood_pressure_systolic"),
            blood_pressure_diastolic=vitals_data.get("blood_pressure_diastolic"),
            respiratory_rate=vitals_data.get("respiratory_rate"),
            temperature=vitals_data.get("temperature"),
            oxygen_saturation=vitals_data.get("oxygen_saturation"),
        )

        return PatientState(
            state_id=extracted.get("state_id", "extracted_0"),
            age=extracted.get("age", 50),
            sex=extracted.get("sex", "unknown"),
            chief_complaint=extracted.get("chief_complaint", ""),
            vitals=vitals,
            lab_results=extracted.get("lab_results", []),
            medications_given=extracted.get("medications_given", []),
            procedures_done=extracted.get("procedures_done", []),
        )
