"""Tests for enhanced ActionNormalizer: abbreviation, composite, determinism, diagnostics."""

import pytest

from cga_bench.assessor_core.action_normalizer import ActionNormalizer


@pytest.fixture
def normalizer():
    return ActionNormalizer()


class TestAbbreviationExpansion:
    """Abbreviation expansion in normalize pipeline."""

    def test_cbc_expansion(self, normalizer):
        result = normalizer._expand_abbreviations("order_lab_cbc")
        assert "complete_blood_count" in result

    def test_bmp_expansion(self, normalizer):
        result = normalizer._expand_abbreviations("order_lab_bmp")
        assert "basic_metabolic_panel" in result

    def test_abg_expansion(self, normalizer):
        result = normalizer._expand_abbreviations("order_lab_abg")
        assert "arterial_blood_gas" in result

    def test_cxr_expansion(self, normalizer):
        result = normalizer._expand_abbreviations("order_imaging_cxr")
        assert "chest_xray" in result

    def test_ecg_expansion(self, normalizer):
        result = normalizer._expand_abbreviations("ecg")
        assert result == "electrocardiogram"

    def test_no_expansion_for_unknown(self, normalizer):
        result = normalizer._expand_abbreviations("give_aspirin")
        assert result == "give_aspirin"

    def test_tpa_expansion(self, normalizer):
        result = normalizer._expand_abbreviations("give_tpa")
        assert "alteplase" in result


class TestCompositeDecomposition:
    """Composite action decomposition."""

    def test_decompose_single(self, normalizer):
        result = normalizer.decompose_composite("order_lab_lactate")
        assert len(result) == 1

    def test_decompose_two_labs(self, normalizer):
        result = normalizer.decompose_composite("order cbc and bmp")
        assert len(result) == 2

    def test_decompose_preserves_prefix(self, normalizer):
        result = normalizer.decompose_composite("order cbc and bmp")
        # Both should be normalized through the pipeline
        assert len(result) == 2


class TestDeterminismCache:
    """E12: Normalizer determinism — same input always produces same output."""

    def test_determinism_1000x(self, normalizer):
        """Same input 1000 times → always same output."""
        inputs = [
            "blood_culture_before_antibiotics",
            "order_lab_cbc",
            "give_aspirin_loading",
            "start_norepinephrine",
            "assess_vital_signs",
        ]
        for inp in inputs:
            first_result = normalizer.normalize(inp)
            for _ in range(999):
                assert normalizer.normalize(inp) == first_result

    def test_cache_populated(self, normalizer):
        normalizer.normalize("some_action")
        normalizer.normalize("some_action")
        diag = normalizer.get_diagnostics()
        assert diag["cache_hits"] >= 1
        assert diag["cache_size"] >= 1


class TestDiagnostics:
    """Cache diagnostics reporting."""

    def test_diagnostics_initial(self, normalizer):
        diag = normalizer.get_diagnostics()
        assert diag["cache_size"] == 0
        assert diag["cache_hits"] == 0
        assert diag["cache_misses"] == 0
        assert diag["hit_rate"] == 0.0

    def test_diagnostics_after_usage(self, normalizer):
        normalizer.normalize("test_action_a")
        normalizer.normalize("test_action_a")  # cache hit
        normalizer.normalize("test_action_b")  # cache miss
        diag = normalizer.get_diagnostics()
        assert diag["cache_size"] == 2
        assert diag["cache_hits"] == 1
        assert diag["cache_misses"] == 2
        assert diag["hit_rate"] == pytest.approx(1 / 3)

    def test_diagnostics_hit_rate(self, normalizer):
        for _ in range(10):
            normalizer.normalize("same_action")
        diag = normalizer.get_diagnostics()
        assert diag["hit_rate"] == pytest.approx(9 / 10)
