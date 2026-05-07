"""Tests for terminology grounding."""
import pytest

from cga_bench.semantic_layer.terminology.grounding import (
    GroundingConfig,
    GroundingResult,
    TerminologyGrounder,
)
from cga_bench.semantic_layer.terminology.coding import (
    CodedConcept,
    GroundedLabResult,
    MedicationCoding,
    QuantityWithUnit,
)


@pytest.fixture
def grounder():
    """Create a TerminologyGrounder with default config."""
    return TerminologyGrounder(GroundingConfig())


class TestLabResultGrounding:
    """Test lab result grounding to LOINC + UCUM."""

    def test_lactate_grounding(self, grounder):
        result = grounder.ground_lab_result("lactate", 3.2, "mmol/L")
        assert result.internal_code == "lactate"
        assert result.concept is not None
        assert result.concept.system == "http://loinc.org"
        assert result.concept.code == "32693-4"
        assert result.quantity is not None
        assert result.quantity.value == 3.2
        assert result.quantity.unit_ucum == "mmol/L"

    def test_potassium_grounding(self, grounder):
        result = grounder.ground_lab_result("potassium", 5.8, "meq/l")
        assert result.concept is not None
        assert result.concept.system == "http://loinc.org"
        assert result.concept.code == "2823-3"
        assert result.quantity is not None
        assert result.quantity.unit_raw == "meq/l"
        assert result.quantity.unit_ucum == "meq/L"

    def test_creatinine_grounding(self, grounder):
        result = grounder.ground_lab_result("creatinine", 2.1, "mg/dl")
        assert result.concept is not None
        assert result.concept.system == "http://loinc.org"
        assert result.concept.code == "2160-0"
        assert result.quantity.unit_ucum == "mg/dL"

    def test_troponin_grounding(self, grounder):
        result = grounder.ground_lab_result("troponin", 0.5, "ng/ml")
        assert result.concept is not None
        assert result.concept.system == "http://loinc.org"
        assert result.concept.code == "6598-7"

    def test_glucose_grounding(self, grounder):
        result = grounder.ground_lab_result("glucose", 450, "mg/dl")
        assert result.concept is not None
        assert result.concept.system == "http://loinc.org"
        assert result.concept.code == "2345-7"

    def test_unknown_lab(self, grounder):
        result = grounder.ground_lab_result("unknown_test_xyz", 1.0, "mg/dL")
        assert result.concept is None
        assert result.quantity is not None
        assert result.quantity.unit_ucum == "mg/dL"

    def test_no_value_no_unit(self, grounder):
        result = grounder.ground_lab_result("lactate")
        assert result.concept is not None
        assert result.quantity is None

    def test_heart_rate_grounding(self, grounder):
        result = grounder.ground_lab_result("heart_rate", 88, "bpm")
        assert result.concept is not None
        assert result.concept.code == "8867-4"
        assert result.quantity.unit_ucum == "/min"


class TestDiagnosisGrounding:
    """Test diagnosis grounding to SNOMED CT."""

    def test_sepsis_grounding(self, grounder):
        result = grounder.ground_diagnosis("sepsis")
        assert result is not None
        assert result.system == "http://snomed.info/sct"
        assert result.code == "91302008"

    def test_aki_grounding(self, grounder):
        result = grounder.ground_diagnosis("aki")
        assert result is not None
        assert result.system == "http://snomed.info/sct"
        assert result.code == "14669001"

    def test_stemi_grounding(self, grounder):
        result = grounder.ground_diagnosis("stemi")
        assert result is not None
        assert result.system == "http://snomed.info/sct"
        assert result.code == "401303003"

    def test_dka_grounding(self, grounder):
        result = grounder.ground_diagnosis("dka")
        assert result is not None
        assert result.code == "420422005"

    def test_unknown_diagnosis(self, grounder):
        result = grounder.ground_diagnosis("nonexistent_disease_xyz")
        assert result is None


class TestMedicationGrounding:
    """Test medication grounding to RxNorm."""

    def test_norepinephrine(self, grounder):
        result = grounder.ground_medication("norepinephrine")
        assert result.name == "norepinephrine"
        assert result.rxnorm_code == "7512"
        assert result.rxnorm_display == "Norepinephrine"

    def test_aspirin(self, grounder):
        result = grounder.ground_medication("aspirin")
        assert result.rxnorm_code == "1191"

    def test_vancomycin(self, grounder):
        result = grounder.ground_medication("vancomycin")
        assert result.rxnorm_code == "11124"

    def test_alteplase(self, grounder):
        result = grounder.ground_medication("alteplase")
        assert result.rxnorm_code == "8410"

    def test_unknown_medication(self, grounder):
        result = grounder.ground_medication("unknown_drug_xyz")
        assert result.name == "unknown_drug_xyz"
        assert result.rxnorm_code is None


class TestFullGrounding:
    """Test combined grounding across terminology systems."""

    def test_lab_takes_priority(self, grounder):
        result = grounder.ground_full("lactate", 3.5, "mmol/L")
        assert result.grounded is True
        assert result.concept.system == "http://loinc.org"

    def test_diagnosis_fallback(self, grounder):
        result = grounder.ground_full("sepsis")
        assert result.grounded is True
        assert result.concept.system == "http://snomed.info/sct"

    def test_nothing_found(self, grounder):
        result = grounder.ground_full("completely_unknown_thing")
        assert result.grounded is False
        assert len(result.warnings) > 0


class TestGroundingConfig:
    """Test grounding with disabled systems."""

    def test_disable_loinc(self):
        config = GroundingConfig(enable_loinc=False)
        grounder = TerminologyGrounder(config)
        result = grounder.ground_lab_result("lactate", 3.0, "mmol/L")
        assert result.concept is None
        assert result.quantity is not None

    def test_disable_snomed(self):
        config = GroundingConfig(enable_snomed=False)
        grounder = TerminologyGrounder(config)
        result = grounder.ground_diagnosis("sepsis")
        assert result is None

    def test_disable_rxnorm(self):
        config = GroundingConfig(enable_rxnorm=False)
        grounder = TerminologyGrounder(config)
        result = grounder.ground_medication("aspirin")
        assert result.rxnorm_code is None

    def test_disable_ucum(self):
        config = GroundingConfig(enable_ucum=False)
        grounder = TerminologyGrounder(config)
        result = grounder.ground_lab_result("lactate", 3.0, "meq/l")
        assert result.quantity is None
