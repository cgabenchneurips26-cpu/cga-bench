"""Tests for dataset compatibility checker."""
import pytest
from cga_bench.semantic_layer.external.compatibility_checker import (
    check_compatibility, CompatibilityReport,
)
from cga_bench.semantic_layer.external.models import EvalMode, TaskType


class TestHealthBenchLike:
    """Dataset with rubrics + points (like HealthBench)."""

    @pytest.fixture
    def rows(self):
        return [
            {
                "prompt": [{"role": "user", "content": "I have chest pain"}],
                "rubrics": [
                    {"criterion": "Advises to call 911", "points": 10, "tags": ["axis:accuracy"]},
                    {"criterion": "Order an ECG within 10 minutes", "points": 8, "tags": []},
                    {"criterion": "Gives harmful advice", "points": -10, "tags": []},
                ],
            },
            {
                "prompt": [{"role": "user", "content": "Headache for 3 days"}],
                "rubrics": [
                    {"criterion": "Recommend seeing a doctor", "points": 5, "tags": []},
                    {"criterion": "Do not prescribe opioids", "points": -7, "tags": []},
                ],
            },
        ]

    def test_detects_rubric_checklist(self, rows):
        report = check_compatibility(rows, "healthbench_test")
        assert report.signals["rubric_checklist"].present

    def test_detects_negative_points(self, rows):
        report = check_compatibility(rows, "healthbench_test")
        assert report.signals["negative_points"].present

    def test_recommends_derived_track_b(self, rows):
        report = check_compatibility(rows, "healthbench_test")
        assert report.recommended_eval_mode == EvalMode.DERIVED_TRACK_B

    def test_enables_c3_forbidden(self, rows):
        report = check_compatibility(rows, "healthbench_test")
        assert report.recommended_mask.c3_forbidden_avoidance is True

    def test_track_a_rubric_grounded(self, rows):
        report = check_compatibility(rows, "healthbench_test")
        assert report.recommended_track_a_variant == "rubric_grounded"


class TestCliBenchLike:
    """Dataset with structured action targets."""

    @pytest.fixture
    def rows(self):
        return [
            {"id": "1", "target_laborders": ["CBC", "BMP"], "target_prescriptions": ["Aspirin"], "instruction": "Manage ACS"},
            {"id": "2", "target_procedures": ["PCI"], "instruction": "STEMI pathway"},
        ]

    def test_detects_structured_actions(self, rows):
        report = check_compatibility(rows, "clibench_test")
        assert report.signals["structured_actions"].present

    def test_recommends_multilabel(self, rows):
        report = check_compatibility(rows, "clibench_test")
        assert report.recommended_task_type == TaskType.MULTILABEL_ACTION

    def test_track_a_action_match(self, rows):
        report = check_compatibility(rows, "clibench_test")
        assert report.recommended_track_a_variant == "action_match"


class TestMedGUIDELike:
    """Dataset with path + options."""

    @pytest.fixture
    def rows(self):
        return [
            {"id": "1", "profile": "NSCLC", "path": "Staging → Biopsy → Chemo", "options": ["A", "B", "C"], "disease": "NSCLC"},
            {"id": "2", "profile": "Breast cancer", "path": "Biopsy → Surgery", "options": ["X", "Y"], "disease": "breast"},
        ]

    def test_detects_path(self, rows):
        report = check_compatibility(rows, "medguide_test")
        assert report.signals["path_trajectory"].present

    def test_recommends_mcq_path(self, rows):
        report = check_compatibility(rows, "medguide_test")
        assert report.recommended_task_type == TaskType.MCQ_PATH

    def test_enables_c1(self, rows):
        report = check_compatibility(rows, "medguide_test")
        assert report.recommended_mask.c1_path_selection is True


class TestEHRStructLike:
    """Dataset with structured EHR fields, no clinical actions."""

    @pytest.fixture
    def rows(self):
        return [
            {"id": "1", "lab_events": [{"test": "glucose", "value": 200}], "discharge_note": "Patient discharged"},
            {"id": "2", "lab_events": [{"test": "creatinine", "value": 3.5}], "vitals": {"hr": 90}},
        ]

    def test_detects_structured_ehr(self, rows):
        report = check_compatibility(rows, "ehr_test")
        assert report.signals["structured_ehr"].present

    def test_recommends_structured_ehr_type(self, rows):
        report = check_compatibility(rows, "ehr_test")
        assert report.recommended_task_type == TaskType.STRUCTURED_EHR


class TestTimelineLike:
    """Dataset with longitudinal events."""

    @pytest.fixture
    def rows(self):
        return [
            {"id": "1", "timeline_events": [{"action": "biopsy"}, {"action": "chemo"}], "input_text": "Cancer patient"},
        ]

    def test_detects_timeline(self, rows):
        report = check_compatibility(rows, "timeline_test")
        assert report.signals["timeline_events"].present

    def test_enables_c5(self, rows):
        report = check_compatibility(rows, "timeline_test")
        assert report.recommended_mask.c5_sequence_integrity is True

    def test_recommends_longitudinal(self, rows):
        report = check_compatibility(rows, "timeline_test")
        assert report.recommended_task_type == TaskType.LONGITUDINAL_TEXT


class TestMinimalDataset:
    """Dataset with almost no structure."""

    @pytest.fixture
    def rows(self):
        return [
            {"id": "1", "text": "What is diabetes?"},
            {"id": "2", "text": "How to treat a cold?"},
        ]

    def test_safety_only(self, rows):
        report = check_compatibility(rows, "minimal_test")
        assert report.recommended_eval_mode == EvalMode.SAFETY_ONLY

    def test_warns_no_rubric(self, rows):
        report = check_compatibility(rows, "minimal_test")
        assert any("No rubric" in w for w in report.warnings)


class TestEmptyInput:
    def test_empty_rows(self):
        report = check_compatibility([], "empty")
        assert report.recommended_eval_mode == EvalMode.SAFETY_ONLY
        assert "No sample rows" in report.warnings[0]


class TestReportOutput:
    def test_to_dict(self):
        rows = [{"rubrics": [{"criterion": "Order ECG", "points": 5}]}]
        report = check_compatibility(rows, "dict_test")
        d = report.to_dict()
        assert "recommended_eval_mode" in d
        assert "signals" in d

    def test_str_output(self):
        rows = [{"rubrics": [{"criterion": "Order ECG", "points": 5}]}]
        report = check_compatibility(rows, "str_test")
        text = str(report)
        assert "CGA Compatibility Report" in text
