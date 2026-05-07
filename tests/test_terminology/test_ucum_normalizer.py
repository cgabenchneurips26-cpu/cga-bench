"""Tests for UCUM unit normalizer."""
import pytest

from cga_bench.semantic_layer.terminology.ucum_normalizer import normalize_ucum, clear_cache


@pytest.fixture(autouse=True)
def reset_cache():
    """Reset UCUM cache before each test."""
    clear_cache()
    yield
    clear_cache()


class TestNormalizeUCUM:
    """Test UCUM normalization for various unit strings."""

    def test_concentration_mg_dl(self):
        assert normalize_ucum("mg/dl") == "mg/dL"
        assert normalize_ucum("mg/dL") == "mg/dL"

    def test_concentration_mmol_l(self):
        assert normalize_ucum("mmol/l") == "mmol/L"
        assert normalize_ucum("mmol/L") == "mmol/L"

    def test_meq_l_variants(self):
        assert normalize_ucum("meq/l") == "meq/L"
        assert normalize_ucum("mEq/l") == "meq/L"
        assert normalize_ucum("mEq/L") == "meq/L"
        assert normalize_ucum("meq/L") == "meq/L"

    def test_enzyme_units(self):
        assert normalize_ucum("u/l") == "U/L"
        assert normalize_ucum("iu/l") == "U/L"

    def test_cell_counts(self):
        assert normalize_ucum("10^3/ul") == "10*3/uL"
        assert normalize_ucum("k/ul") == "10*3/uL"
        assert normalize_ucum("cells/ul") == "10*3/uL"

    def test_temperature(self):
        assert normalize_ucum("degC") == "Cel"
        assert normalize_ucum("celsius") == "Cel"
        assert normalize_ucum("degF") == "[degF]"

    def test_pressure(self):
        assert normalize_ucum("mmHg") == "mm[Hg]"
        assert normalize_ucum("mm hg") == "mm[Hg]"
        assert normalize_ucum("cmH2O") == "cm[H2O]"

    def test_time(self):
        assert normalize_ucum("sec") == "s"
        assert normalize_ucum("min") == "min"
        assert normalize_ucum("hr") == "h"
        assert normalize_ucum("hours") == "h"

    def test_rate(self):
        assert normalize_ucum("ml/hr") == "mL/h"
        assert normalize_ucum("mcg/kg/min") == "ug/kg/min"
        assert normalize_ucum("l/min") == "L/min"

    def test_volume(self):
        assert normalize_ucum("ml") == "mL"
        assert normalize_ucum("dl") == "dL"
        assert normalize_ucum("mcl") == "uL"

    def test_mass(self):
        assert normalize_ucum("mcg") == "ug"
        assert normalize_ucum("mg") == "mg"
        assert normalize_ucum("kg") == "kg"

    def test_percentage(self):
        assert normalize_ucum("%") == "%"
        assert normalize_ucum("percent") == "%"

    def test_special_units(self):
        assert normalize_ucum("pH") == "[pH]"
        assert normalize_ucum("bpm") == "/min"
        assert normalize_ucum("beats/min") == "/min"
        assert normalize_ucum("INR") == "{INR}"

    def test_empty_string(self):
        assert normalize_ucum("") == ""

    def test_unknown_unit_passthrough(self):
        assert normalize_ucum("some_unknown_unit") == "some_unknown_unit"

    def test_case_insensitive(self):
        assert normalize_ucum("MG/DL") == "mg/dL"
        assert normalize_ucum("MMOL/L") == "mmol/L"

    def test_whitespace_handling(self):
        assert normalize_ucum("  mg/dl  ") == "mg/dL"
        assert normalize_ucum("mm hg") == "mm[Hg]"

    def test_ng_ml(self):
        assert normalize_ucum("ng/ml") == "ng/mL"
        assert normalize_ucum("pg/ml") == "pg/mL"

    def test_osmolality(self):
        assert normalize_ucum("mosm/kg") == "mosm/kg"
        assert normalize_ucum("mosm/l") == "mosm/L"
