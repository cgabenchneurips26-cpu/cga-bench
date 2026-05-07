"""Tests for ClinicalStateExtractor (vignette → PatientState)."""
from __future__ import annotations

import json
import pytest
from unittest.mock import MagicMock

from cga_bench.assessor_core.clinical_state_extractor import (
    ClinicalStateExtractor,
    _STUB_VITALS,
)
from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns


# ============================================================================
# Stub Mode (no LLM)
# ============================================================================

class TestStubExtract:
    def test_returns_default_fields(self):
        ext = ClinicalStateExtractor()
        result = ext.extract("Some vignette about a patient.")
        assert result["state_id"] == "extracted_0"
        assert result["age"] == 50
        assert result["sex"] == "unknown"
        assert isinstance(result["vitals"], dict)
        assert result["lab_results"] == []
        assert result["medications_given"] == []
        assert result["procedures_done"] == []
        assert result["comorbidities"] == []
        assert result["allergies"] == []

    def test_chief_complaint_truncated(self):
        ext = ClinicalStateExtractor()
        long_vignette = "x" * 200
        result = ext.extract(long_vignette)
        assert len(result["chief_complaint"]) == 100

    def test_empty_vignette(self):
        ext = ClinicalStateExtractor()
        result = ext.extract("")
        assert result["chief_complaint"] == ""
        assert result["age"] == 50

    def test_vitals_match_defaults(self):
        ext = ClinicalStateExtractor()
        result = ext.extract("any text")
        for key, default_val in _STUB_VITALS.items():
            assert result["vitals"][key] == default_val


# ============================================================================
# Heuristic Extraction
# ============================================================================

class TestHeuristicExtract:
    def test_age_extraction(self):
        ext = ClinicalStateExtractor()
        result = ext._heuristic_extract("A 72-year-old male presents with chest pain.")
        assert result["age"] == 72

    def test_sex_female(self):
        ext = ClinicalStateExtractor()
        result = ext._heuristic_extract("A 45 year old female with fever.")
        assert result["sex"] == "female"

    def test_sex_male(self):
        ext = ClinicalStateExtractor()
        result = ext._heuristic_extract("A 60-year-old male with dyspnea.")
        assert result["sex"] == "male"

    def test_sex_woman(self):
        ext = ClinicalStateExtractor()
        result = ext._heuristic_extract("A 55-year-old woman presents.")
        assert result["sex"] == "female"

    def test_heart_rate_extracted(self):
        ext = ClinicalStateExtractor()
        result = ext._heuristic_extract("Vitals: HR: 110, RR: 22")
        assert result["vitals"]["heart_rate"] == 110.0

    def test_blood_pressure_extracted(self):
        ext = ClinicalStateExtractor()
        result = ext._heuristic_extract("BP: 90/60, temp 38.5")
        assert result["vitals"]["blood_pressure_systolic"] == 90.0
        assert result["vitals"]["blood_pressure_diastolic"] == 60.0

    def test_temperature_extracted(self):
        ext = ClinicalStateExtractor()
        result = ext._heuristic_extract("Temp: 39.2, SpO2: 92")
        assert result["vitals"]["temperature"] == 39.2

    def test_oxygen_saturation_extracted(self):
        ext = ClinicalStateExtractor()
        result = ext._heuristic_extract("O2 sat: 88%")
        assert result["vitals"]["oxygen_saturation"] == 88.0

    def test_comorbidities_detected(self):
        ext = ClinicalStateExtractor()
        result = ext._heuristic_extract(
            "Patient with diabetes, hypertension, and COPD."
        )
        assert "diabetes" in result["comorbidities"]
        assert "hypertension" in result["comorbidities"]
        assert "copd" in result["comorbidities"]

    def test_allergies_extracted(self):
        ext = ClinicalStateExtractor()
        result = ext._heuristic_extract("Allergies to penicillin, sulfa.")
        assert "penicillin" in result["allergies"]
        assert "sulfa" in result["allergies"]

    def test_out_of_range_vitals_ignored(self):
        ext = ClinicalStateExtractor()
        result = ext._heuristic_extract("HR: 999")
        # 999 > 250 so should not be accepted
        assert result["vitals"]["heart_rate"] == _STUB_VITALS["heart_rate"]

    def test_empty_vignette_returns_defaults(self):
        ext = ClinicalStateExtractor()
        result = ext._heuristic_extract("")
        assert result["age"] == 50
        assert result["sex"] == "unknown"


# ============================================================================
# LLM Extract Mode (mocked)
# ============================================================================

class TestLLMExtract:
    def test_llm_parses_json_response(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = json.dumps({
            "age": 65,
            "sex": "male",
            "chief_complaint": "chest pain",
            "vitals": {"heart_rate": 110, "blood_pressure_systolic": 85},
            "comorbidities": ["diabetes"],
            "allergies": ["penicillin"],
            "working_diagnosis": "sepsis",
        })
        ext = ClinicalStateExtractor(llm_provider=mock_llm)
        result = ext.extract("Patient vignette text")
        assert result["age"] == 65
        assert result["sex"] == "male"
        assert result["vitals"]["heart_rate"] == 110.0
        assert "diabetes" in result["comorbidities"]
        assert "penicillin" in result["allergies"]
        assert result["working_diagnosis"] == "sepsis"

    def test_llm_invalid_json_falls_back(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = "I'm not valid JSON at all"
        ext = ClinicalStateExtractor(llm_provider=mock_llm)
        result = ext.extract("A 70-year-old female with fever.")
        # Should fall back to heuristic
        assert result["age"] == 70
        assert result["sex"] == "female"

    def test_llm_exception_falls_back(self):
        mock_llm = MagicMock()
        mock_llm.complete.side_effect = RuntimeError("LLM down")
        ext = ClinicalStateExtractor(llm_provider=mock_llm)
        result = ext.extract("A 55-year-old male with dyspnea.")
        # Should fall back to heuristic
        assert result["age"] == 55
        assert result["sex"] == "male"

    def test_llm_partial_override(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = json.dumps({
            "age": 80,
            # sex missing → stays "unknown" from stub
            "vitals": {"heart_rate": 95},
        })
        ext = ClinicalStateExtractor(llm_provider=mock_llm)
        result = ext.extract("Vignette")
        assert result["age"] == 80
        assert result["vitals"]["heart_rate"] == 95.0
        # Other vitals should remain at stub defaults
        assert result["vitals"]["temperature"] == _STUB_VITALS["temperature"]

    def test_llm_ignores_invalid_sex(self):
        mock_llm = MagicMock()
        mock_llm.complete.return_value = json.dumps({"sex": "other"})
        ext = ClinicalStateExtractor(llm_provider=mock_llm)
        result = ext.extract("Vignette")
        assert result["sex"] == "unknown"


# ============================================================================
# to_patient_state Conversion
# ============================================================================

class TestToPatientState:
    def test_basic_conversion(self):
        ext = ClinicalStateExtractor()
        extracted = ext.extract("A 70-year-old male with chest pain.")
        ps = ClinicalStateExtractor.to_patient_state(extracted)
        assert isinstance(ps, PatientState)
        assert isinstance(ps.vitals, VitalSigns)
        assert ps.age == extracted["age"]

    def test_vitals_populated(self):
        extracted = {
            "state_id": "test_1",
            "age": 60,
            "sex": "female",
            "chief_complaint": "fever",
            "vitals": {"heart_rate": 100, "temperature": 39.0},
        }
        ps = ClinicalStateExtractor.to_patient_state(extracted)
        assert ps.vitals.heart_rate == 100
        assert ps.vitals.temperature == 39.0

    def test_defaults_when_missing(self):
        ps = ClinicalStateExtractor.to_patient_state({})
        assert ps.state_id == "extracted_0"
        assert ps.age == 50
        assert ps.chief_complaint == ""
