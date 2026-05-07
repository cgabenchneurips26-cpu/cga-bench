"""E2E smoke test: all registered datasets process mock data through universal pipeline."""

from typing import cast

import pytest

from cga_bench.semantic_layer.external.models import NormalizedEpisode
from cga_bench.semantic_layer.external.pipeline import process_case
from cga_bench.semantic_layer.external.registry import REGISTRY, list_datasets


MOCK_DATA: dict[str, dict[str, object]] = {
    "amega": {
        "id": "e2e_amega",
        "narrative": "65yo M with chest pain and diaphoresis",
        "criteria": [
            {"text": "Order 12-lead ECG"},
            {"text": "Administer aspirin 325mg"},
            {"text": "Explain risks of ACS"},
        ],
    },
    "clibench": {
        "id": "e2e_clibench",
        "target_laborders": ["CBC", "BMP", "Troponin"],
        "target_prescriptions": ["Aspirin", "Heparin"],
        "instruction": "Manage suspected ACS patient",
    },
    "medguide": {
        "id": "e2e_medguide",
        "profile": "Stage IIIA NSCLC patient",
        "path": "Staging -> Molecular Testing -> Immunotherapy",
        "disease": "NSCLC",
        "options": ["Chemotherapy", "Immunotherapy", "Surgery"],
        "answer": "B",
    },
    "cancerguide": {
        "id": "e2e_cancerguide",
        "patient_note": "NSCLC patient post-progression on first-line therapy",
        "label": "Second-line pembrolizumab",
    },
    "mtbbench": {
        "id": "e2e_mtbbench",
        "timeline_events": [
            {"action": "biopsy", "event": "Initial biopsy"},
            {"action": "molecular_testing", "event": "NGS panel"},
        ],
        "input_text": "Discuss treatment options for EGFR+ NSCLC",
    },
    "ehrstruct": {
        "id": "e2e_ehrstruct",
        "gold_answer": "elevated creatinine",
        "lab_events": [{"test": "creatinine", "value": 3.5}],
    },
    "llmeval_med": {
        "id": "e2e_llmeval",
        "checklist": [
            "Order blood culture before antibiotics",
            "Do not give NSAIDs in renal failure",
            "Explain the treatment plan",
        ],
        "problem": "Sepsis management",
        "category1": "Medical Reasoning",
    },
    "nice": {
        "id": "e2e_nice",
        "answer": "Start ACE inhibitor for heart failure",
    },
    "healthbench": {
        "id": "e2e_healthbench",
        "prompt_id": "e2e_hb",
        "prompt": [{"role": "user", "content": "I have chest pain"}],
        "rubrics": [
            {"criterion": "Advises calling 911", "points": 10, "tags": []},
            {"criterion": "Provides harmful advice", "points": -8, "tags": []},
        ],
    },
}


@pytest.mark.parametrize("dataset_id", list_datasets())
def test_dataset_e2e_pipeline(dataset_id: str) -> None:
    """Each registered dataset processes mock data without error."""
    manifest = REGISTRY[dataset_id]
    mock = MOCK_DATA.get(dataset_id)
    if mock is None:
        pytest.skip(f"No mock data for {dataset_id}")

    result = process_case(mock, manifest)
    assert isinstance(result, NormalizedEpisode)
    assert result.source_benchmark == dataset_id
    assert result.case_id != "unknown" or dataset_id in ("ehrstruct",)


@pytest.mark.parametrize("dataset_id", list_datasets())
def test_dataset_produces_actions_or_warnings(dataset_id: str) -> None:
    """Each dataset produces either actions or a warning about no actions."""
    manifest = REGISTRY[dataset_id]
    mock = MOCK_DATA.get(dataset_id)
    if mock is None:
        pytest.skip(f"No mock data for {dataset_id}")

    result = process_case(mock, manifest)
    has_actions = len(result.actions) > 0
    has_warning = "no_expected_actions" in result.warnings
    assert has_actions or has_warning, f"{dataset_id}: no actions and no warning"


class TestHealthBenchDispatch:
    """HealthBench native rows through normalize_external_case."""

    def test_eval_row(self):
        from cga_bench.semantic_layer.external.normalize import normalize_external_case

        mock = MOCK_DATA["healthbench"]
        result = cast(NormalizedEpisode, normalize_external_case("healthbench", mock))
        assert isinstance(result, NormalizedEpisode)
        assert len(result.actions) >= 1
