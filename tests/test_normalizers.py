"""
Action Target Normalizer Tests

액션 target 정규화 테스트
"""
import pytest
from cga_bench.env.adapters.normalizers import ActionTargetNormalizer


class TestLabNormalization:
    """Lab test 정규화"""

    def setup_method(self):
        ActionTargetNormalizer.clear_cache()

    def test_cbc_variants(self):
        """CBC 변형 정규화"""
        assert ActionTargetNormalizer.normalize_lab("CBC") == "cbc"
        assert ActionTargetNormalizer.normalize_lab("cbc") == "cbc"
        assert ActionTargetNormalizer.normalize_lab("Complete Blood Count") == "cbc"
        assert ActionTargetNormalizer.normalize_lab("complete blood count") == "cbc"
        assert ActionTargetNormalizer.normalize_lab("full blood count") == "cbc"
        assert ActionTargetNormalizer.normalize_lab("FBC") == "cbc"

    def test_troponin_variants(self):
        """Troponin 변형 정규화"""
        assert ActionTargetNormalizer.normalize_lab("troponin") == "troponin"
        assert ActionTargetNormalizer.normalize_lab("Troponin I") == "troponin"
        assert ActionTargetNormalizer.normalize_lab("troponin t") == "troponin"
        assert ActionTargetNormalizer.normalize_lab("cardiac troponin") == "troponin"
        assert ActionTargetNormalizer.normalize_lab("TnNI") == "troponin"

    def test_metabolic_panel(self):
        """대사패널 정규화"""
        assert ActionTargetNormalizer.normalize_lab("BMP") == "bmp"
        assert ActionTargetNormalizer.normalize_lab("basic metabolic panel") == "bmp"
        assert ActionTargetNormalizer.normalize_lab("chem 7") == "bmp"
        assert ActionTargetNormalizer.normalize_lab("CMP") == "cmp"
        assert ActionTargetNormalizer.normalize_lab("comprehensive metabolic panel") == "cmp"

    def test_blood_culture(self):
        """Blood culture 정규화"""
        assert ActionTargetNormalizer.normalize_lab("blood culture") == "blood_culture"
        assert ActionTargetNormalizer.normalize_lab("blood_culture") == "blood_culture"
        assert ActionTargetNormalizer.normalize_lab("blood cx") == "blood_culture"

    def test_lactate(self):
        """Lactate 정규화"""
        assert ActionTargetNormalizer.normalize_lab("lactate") == "lactate"
        assert ActionTargetNormalizer.normalize_lab("lactic acid") == "lactate"

    def test_unknown_lab_raises(self):
        """Unknown lab은 ValueError"""
        # 어떤 lab term과도 부분 매칭되지 않는 문자열
        with pytest.raises(ValueError, match="Cannot normalize lab target"):
            ActionTargetNormalizer.normalize_lab("zzqqwwee")

    def test_empty_lab_raises(self):
        """빈 문자열은 ValueError"""
        with pytest.raises(ValueError, match="Lab target cannot be empty"):
            ActionTargetNormalizer.normalize_lab("")

    def test_try_normalize_returns_none(self):
        """try_normalize는 실패 시 None 반환"""
        # 어떤 lab term과도 매칭되지 않는 문자열
        result = ActionTargetNormalizer.try_normalize_lab("zzqqwwee")
        assert result is None

        result = ActionTargetNormalizer.try_normalize_lab("CBC")
        assert result == "cbc"


class TestMedicationNormalization:
    """Medication 정규화"""

    def setup_method(self):
        ActionTargetNormalizer.clear_cache()

    def test_aspirin_variants(self):
        """Aspirin 변형"""
        assert ActionTargetNormalizer.normalize_medication("aspirin") == "aspirin"
        assert ActionTargetNormalizer.normalize_medication("ASA") == "aspirin"
        assert ActionTargetNormalizer.normalize_medication("acetylsalicylic acid") == "aspirin"

    def test_antibiotics_variants(self):
        """Antibiotics 변형"""
        assert ActionTargetNormalizer.normalize_medication("antibiotics") == "antibiotics"
        assert ActionTargetNormalizer.normalize_medication("antibiotic") == "antibiotics"
        assert ActionTargetNormalizer.normalize_medication("broad_spectrum_antibiotics") == "antibiotics"

    def test_vasopressors(self):
        """Vasopressors"""
        assert ActionTargetNormalizer.normalize_medication("norepinephrine") == "norepinephrine"
        assert ActionTargetNormalizer.normalize_medication("levophed") == "norepinephrine"
        assert ActionTargetNormalizer.normalize_medication("epinephrine") == "epinephrine"

    def test_fluids(self):
        """IV fluids"""
        assert ActionTargetNormalizer.normalize_medication("normal saline") == "normal_saline"
        assert ActionTargetNormalizer.normalize_medication("NS") == "normal_saline"
        assert ActionTargetNormalizer.normalize_medication("crystalloid") == "iv_fluids"

    def test_dosage_stripped(self):
        """용량 정보 제거"""
        assert ActionTargetNormalizer.normalize_medication("aspirin 325mg") == "aspirin"
        assert ActionTargetNormalizer.normalize_medication("metoprolol 25 mg") == "metoprolol"

    def test_unknown_medication_raises(self):
        """Unknown medication은 ValueError"""
        with pytest.raises(ValueError, match="Cannot normalize medication target"):
            ActionTargetNormalizer.normalize_medication("completely_unknown_drug_xyz")


class TestImagingNormalization:
    """Imaging study 정규화"""

    def setup_method(self):
        ActionTargetNormalizer.clear_cache()

    def test_ecg_variants(self):
        """ECG 변형"""
        assert ActionTargetNormalizer.normalize_imaging("ECG") == "ecg"
        assert ActionTargetNormalizer.normalize_imaging("EKG") == "ecg"
        assert ActionTargetNormalizer.normalize_imaging("12-lead") == "ecg"
        assert ActionTargetNormalizer.normalize_imaging("electrocardiogram") == "ecg"

    def test_chest_xray_variants(self):
        """Chest X-ray 변형"""
        assert ActionTargetNormalizer.normalize_imaging("CXR") == "chest_xray"
        assert ActionTargetNormalizer.normalize_imaging("chest x-ray") == "chest_xray"
        assert ActionTargetNormalizer.normalize_imaging("chest xray") == "chest_xray"
        assert ActionTargetNormalizer.normalize_imaging("chest_xray") == "chest_xray"

    def test_ct_scans(self):
        """CT scan 변형"""
        assert ActionTargetNormalizer.normalize_imaging("chest ct") == "chest_ct"
        assert ActionTargetNormalizer.normalize_imaging("CT chest") == "chest_ct"
        assert ActionTargetNormalizer.normalize_imaging("head ct") == "ct_head"
        assert ActionTargetNormalizer.normalize_imaging("CT head") == "ct_head"

    def test_echocardiogram(self):
        """Echo 변형"""
        assert ActionTargetNormalizer.normalize_imaging("echocardiogram") == "echocardiogram"
        assert ActionTargetNormalizer.normalize_imaging("echo") == "echocardiogram"
        assert ActionTargetNormalizer.normalize_imaging("TTE") == "echocardiogram"


class TestSpecialtyNormalization:
    """Specialty 정규화"""

    def setup_method(self):
        ActionTargetNormalizer.clear_cache()

    def test_cardiology_variants(self):
        """Cardiology 변형"""
        assert ActionTargetNormalizer.normalize_specialty("cardiology") == "cardiology"
        assert ActionTargetNormalizer.normalize_specialty("cards") == "cardiology"
        assert ActionTargetNormalizer.normalize_specialty("cardiac") == "cardiology"

    def test_icu_variants(self):
        """ICU 변형"""
        assert ActionTargetNormalizer.normalize_specialty("ICU") == "icu"
        assert ActionTargetNormalizer.normalize_specialty("intensive care") == "icu"
        assert ActionTargetNormalizer.normalize_specialty("critical care") == "icu"
        assert ActionTargetNormalizer.normalize_specialty("MICU") == "icu"
        assert ActionTargetNormalizer.normalize_specialty("CCU") == "icu"

    def test_infectious_disease(self):
        """ID 변형"""
        assert ActionTargetNormalizer.normalize_specialty("infectious disease") == "infectious_disease"
        assert ActionTargetNormalizer.normalize_specialty("ID") == "infectious_disease"


class TestCleaning:
    """Target 문자열 정리"""

    def setup_method(self):
        ActionTargetNormalizer.clear_cache()

    def test_article_removal(self):
        """관사 제거"""
        assert ActionTargetNormalizer.normalize_lab("a CBC") == "cbc"
        assert ActionTargetNormalizer.normalize_lab("an ABG") == "abg"
        assert ActionTargetNormalizer.normalize_lab("the troponin") == "troponin"

    def test_suffix_removal(self):
        """공통 접미사 제거"""
        assert ActionTargetNormalizer.normalize_lab("CBC test") == "cbc"
        assert ActionTargetNormalizer.normalize_lab("troponin level") == "troponin"


class TestUnmatchedTracking:
    """Unmatched target 추적"""

    def setup_method(self):
        ActionTargetNormalizer.clear_cache()

    def test_unmatched_targets_tracked(self):
        """Unmatched target이 추적됨"""
        # 어떤 term과도 매칭되지 않는 문자열 사용
        try:
            ActionTargetNormalizer.normalize_lab("zzqqwwee123")
        except ValueError:
            pass

        unmatched = ActionTargetNormalizer.get_unmatched_targets()
        assert "zzqqwwee123" in unmatched


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
