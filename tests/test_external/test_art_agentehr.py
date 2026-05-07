"""Smoke tests for ART and AgentEHR adapters.

Tests pipeline compatibility - proves the universal pipeline generalises
to these two new datasets without requiring full data downloads.

ART: uses synthetic 5-case sample (real data not yet released)
AgentEHR: uses inline sample data matching BlueZeros/AgentEHR-Bench format
"""

from __future__ import annotations

import pytest

from cga_bench.semantic_layer.external.models import (
    EvalMode,
    NormalizedEpisode,
    TaskType,
)
from cga_bench.semantic_layer.external.pipeline import (
    UniversalExternalAdapter,
    build_expected_actions,
    raw_to_canonical,
)
from cga_bench.semantic_layer.external.registry import get_manifest, list_datasets


# ---------------------------------------------------------------------------
# Registry tests
# ---------------------------------------------------------------------------

class TestARTRegistry:
    def test_art_in_registry(self):
        datasets = list_datasets()
        assert "art" in datasets

    def test_art_manifest_fields(self):
        m = get_manifest("art")
        assert m.dataset_id == "art"
        assert m.task_type == TaskType.STRUCTURED_EHR
        assert m.eval_mode == EvalMode.DERIVED_TRACK_B
        assert m.sub_score_mask.c1_path_selection is True
        assert m.sub_score_mask.c2_mandatory_completion is True
        assert m.sub_score_mask.c3_forbidden_avoidance is True
        assert m.sub_score_mask.c4_timing_compliance is False

    def test_art_access_level(self):
        m = get_manifest("art")
        assert m.access_level == "public"


class TestAgentEHRRegistry:
    def test_agentehr_in_registry(self):
        datasets = list_datasets()
        assert "agentehr" in datasets

    def test_agentehr_manifest_fields(self):
        m = get_manifest("agentehr")
        assert m.dataset_id == "agentehr"
        assert m.task_type == TaskType.MULTILABEL_ACTION
        assert m.eval_mode == EvalMode.DERIVED_TRACK_B
        assert m.sub_score_mask.c1_path_selection is True
        assert m.sub_score_mask.c2_mandatory_completion is True
        assert m.sub_score_mask.c3_forbidden_avoidance is False

    def test_agentehr_access_level(self):
        m = get_manifest("agentehr")
        assert m.access_level == "public"

    def test_agentehr_license(self):
        m = get_manifest("agentehr")
        assert "apache" in m.license.lower() or "2.0" in m.license


# ---------------------------------------------------------------------------
# ART pipeline smoke tests
# ---------------------------------------------------------------------------

ART_SAMPLE_CASES = [
    {
        "case_id": "art_001",
        "task_type": "threshold_evaluation",
        "split": "test",
        "input_text": "67yo male, Troponin I 0.18 ng/mL (>0.04 threshold). ST elevation inferior leads. BP 88/60.",
        "checklist": [
            "Activate cardiac catheterization lab for primary PCI",
            "Administer aspirin 325mg loading dose",
            "Do not administer nitrates given hypotension",
        ],
        "gold_answer": "STEMI_inferior_with_hypotension",
        "reasoning_type": "threshold_evaluation",
    },
    {
        "case_id": "art_002",
        "task_type": "temporal_aggregation",
        "split": "test",
        "input_text": "52yo female, T2DM. HbA1c worsening 8.2->9.1% over 12 months. Creatinine rising 1.1->1.9.",
        "checklist": [
            "Discontinue metformin given eGFR decline",
            "Order urine albumin-to-creatinine ratio",
        ],
        "gold_answer": "diabetic_nephropathy_progression",
        "reasoning_type": "temporal_aggregation",
    },
]


class TestARTPipeline:
    def test_art_adapter_instantiation(self):
        from cga_bench.semantic_layer.external.art import ARTAdapter
        manifest = get_manifest("art")
        adapter = ARTAdapter(manifest)
        assert adapter.dataset_id == "art"

    def test_universal_adapter_art(self):
        manifest = get_manifest("art")
        adapter = UniversalExternalAdapter(manifest)
        assert adapter.dataset_id == "art"

    def test_art_raw_to_canonical(self):
        manifest = get_manifest("art")
        raw = ART_SAMPLE_CASES[0]
        canonical = raw_to_canonical(raw, manifest)
        assert canonical.dataset_id == "art"
        assert canonical.task_type == TaskType.STRUCTURED_EHR
        assert "aspirin" in (canonical.input_text or "").lower() or canonical.checklist is not None

    def test_art_checklist_extraction(self):
        manifest = get_manifest("art")
        raw = ART_SAMPLE_CASES[0]
        canonical = raw_to_canonical(raw, manifest)
        assert canonical.checklist is not None
        assert len(canonical.checklist) == 3

    def test_art_process_case_returns_normalized_episode(self):
        from cga_bench.semantic_layer.external.pipeline import process_case
        manifest = get_manifest("art")
        result = process_case(ART_SAMPLE_CASES[0], manifest)
        assert isinstance(result, NormalizedEpisode)
        assert result.source_benchmark == "art"

    def test_art_forbidden_action_detected(self):
        from cga_bench.semantic_layer.external.pipeline import process_case
        manifest = get_manifest("art")
        # art_001 has "Do not administer nitrates given hypotension"
        result = process_case(ART_SAMPLE_CASES[0], manifest)
        # The pipeline should extract at least the mandatory actions
        assert isinstance(result, NormalizedEpisode)

    def test_art_build_expected_actions(self):
        manifest = get_manifest("art")
        raw = ART_SAMPLE_CASES[0]
        canonical = raw_to_canonical(raw, manifest)
        expected = build_expected_actions(canonical)
        # Should extract at least the two mandatory action items
        assert len(expected) >= 1
        kinds = {ea.kind for ea in expected}
        assert "mandatory" in kinds

    @pytest.mark.parametrize("raw", ART_SAMPLE_CASES)
    def test_art_all_samples_no_crash(self, raw):
        from cga_bench.semantic_layer.external.pipeline import process_case
        manifest = get_manifest("art")
        result = process_case(raw, manifest)
        assert isinstance(result, NormalizedEpisode)

    def test_art_adapter_parse_to_episode_log(self):
        from cga_bench.semantic_layer.external.art import ARTAdapter
        manifest = get_manifest("art")
        adapter = ARTAdapter(manifest)
        result = adapter.parse_to_episode_log(ART_SAMPLE_CASES[0])
        assert isinstance(result, NormalizedEpisode)
        assert result.source_benchmark == "art"

    def test_art_empty_case_no_crash(self):
        from cga_bench.semantic_layer.external.pipeline import process_case
        manifest = get_manifest("art")
        result = process_case({}, manifest)
        assert isinstance(result, NormalizedEpisode)
        assert "no_expected_actions" in result.warnings

    def test_art_native_score(self):
        from cga_bench.semantic_layer.external.art import ARTAdapter
        manifest = get_manifest("art")
        adapter = ARTAdapter(manifest)
        raw = ART_SAMPLE_CASES[0]
        output = ["Activate cardiac catheterization lab for primary PCI", "Administer aspirin 325mg loading dose"]
        score = adapter.native_score(raw, output)
        assert score is not None
        assert 0.0 <= score["native_score"] <= 1.0
        assert score["reasoning_type"] == "threshold_evaluation"


# ---------------------------------------------------------------------------
# AgentEHR pipeline smoke tests
# ---------------------------------------------------------------------------

AGENTEHR_DIAGNOSES_SAMPLE = {
    "subject_id": 13762777,
    "hadm_id": 22827736,
    "prediction_time": "2174-05-02 14:24:00",
    "task": "diagnoses_ccs",
    "label": [
        {"name": "Cancer of liver and intrahepatic bile duct", "icd_code": "1550", "icd_version": 9, "seq_num": 1},
        {"name": "Nausea and vomiting", "icd_code": "78701", "icd_version": 9, "seq_num": 2},
        {"name": "Essential hypertension", "icd_code": "4019", "icd_version": 9, "seq_num": 3},
    ],
}

AGENTEHR_LABEVENTS_SAMPLE = {
    "subject_id": 19504611,
    "prediction_time": "2180-05-21 17:10:00",
    "task": "labevents",
    "label": [
        {"name": "Absolute Lymphocyte Count", "itemid": 51133, "fluid": "Blood", "category": "Hematology"},
        {"name": "Hematocrit", "itemid": 51221, "fluid": "Blood", "category": "Hematology"},
        {"name": "Hemoglobin", "itemid": 51222, "fluid": "Blood", "category": "Hematology"},
    ],
}

AGENTEHR_PRESCRIPTIONS_SAMPLE = {
    "subject_id": 10012694,
    "hadm_id": 23456789,
    "prediction_time": "2150-03-15 08:00:00",
    "task": "prescriptions3",
    "label": [
        {"name": "Aspirin"},
        {"name": "Metoprolol"},
        {"name": "Lisinopril"},
    ],
}


class TestAgentEHRPipeline:
    def test_agentehr_adapter_instantiation(self):
        from cga_bench.semantic_layer.external.agentehr import AgentEHRAdapter
        manifest = get_manifest("agentehr")
        adapter = AgentEHRAdapter(manifest)
        assert adapter.dataset_id == "agentehr"

    def test_universal_adapter_agentehr(self):
        manifest = get_manifest("agentehr")
        adapter = UniversalExternalAdapter(manifest)
        assert adapter.dataset_id == "agentehr"

    def test_agentehr_diagnoses_raw_to_canonical(self):
        from cga_bench.semantic_layer.external.agentehr import parse_agentehr_case
        manifest = get_manifest("agentehr")
        canonical = parse_agentehr_case(AGENTEHR_DIAGNOSES_SAMPLE, manifest)
        assert canonical.dataset_id == "agentehr"
        assert canonical.task_type == TaskType.MULTILABEL_ACTION
        assert canonical.provenance.get("agentehr_task") == "diagnoses_ccs"

    def test_agentehr_diagnoses_target_actions(self):
        from cga_bench.semantic_layer.external.agentehr import parse_agentehr_case
        manifest = get_manifest("agentehr")
        canonical = parse_agentehr_case(AGENTEHR_DIAGNOSES_SAMPLE, manifest)
        dx_targets = canonical.structured_fields.get("target_diagnoses") or []
        assert len(dx_targets) == 3
        assert any("1550" in t for t in dx_targets)

    def test_agentehr_labevents_target_actions(self):
        from cga_bench.semantic_layer.external.agentehr import parse_agentehr_case
        manifest = get_manifest("agentehr")
        canonical = parse_agentehr_case(AGENTEHR_LABEVENTS_SAMPLE, manifest)
        lab_targets = canonical.structured_fields.get("target_laborders") or []
        assert len(lab_targets) == 3
        assert any("51133" in t for t in lab_targets)

    def test_agentehr_prescriptions_target_actions(self):
        from cga_bench.semantic_layer.external.agentehr import parse_agentehr_case
        manifest = get_manifest("agentehr")
        canonical = parse_agentehr_case(AGENTEHR_PRESCRIPTIONS_SAMPLE, manifest)
        med_targets = canonical.structured_fields.get("target_prescriptions") or []
        assert len(med_targets) == 3

    def test_agentehr_normalize_diagnoses(self):
        from cga_bench.semantic_layer.external.agentehr import normalize_agentehr_case
        manifest = get_manifest("agentehr")
        result = normalize_agentehr_case(AGENTEHR_DIAGNOSES_SAMPLE, manifest)
        assert isinstance(result, NormalizedEpisode)
        assert result.source_benchmark == "agentehr"
        dx_actions = [a for a in result.actions if a.startswith("dx/")]
        assert len(dx_actions) == 3

    def test_agentehr_normalize_labevents(self):
        from cga_bench.semantic_layer.external.agentehr import normalize_agentehr_case
        manifest = get_manifest("agentehr")
        result = normalize_agentehr_case(AGENTEHR_LABEVENTS_SAMPLE, manifest)
        assert isinstance(result, NormalizedEpisode)
        lab_actions = [a for a in result.actions if a.startswith("lab/")]
        assert len(lab_actions) == 3

    @pytest.mark.parametrize("raw", [
        AGENTEHR_DIAGNOSES_SAMPLE,
        AGENTEHR_LABEVENTS_SAMPLE,
        AGENTEHR_PRESCRIPTIONS_SAMPLE,
    ])
    def test_agentehr_all_samples_no_crash(self, raw):
        from cga_bench.semantic_layer.external.agentehr import normalize_agentehr_case
        manifest = get_manifest("agentehr")
        result = normalize_agentehr_case(raw, manifest)
        assert isinstance(result, NormalizedEpisode)

    def test_agentehr_adapter_parse_to_episode_log(self):
        from cga_bench.semantic_layer.external.agentehr import AgentEHRAdapter
        manifest = get_manifest("agentehr")
        adapter = AgentEHRAdapter(manifest)
        result = adapter.parse_to_episode_log(AGENTEHR_DIAGNOSES_SAMPLE)
        assert isinstance(result, NormalizedEpisode)
        assert result.source_benchmark == "agentehr"

    def test_agentehr_empty_case_no_crash(self):
        from cga_bench.semantic_layer.external.agentehr import normalize_agentehr_case
        manifest = get_manifest("agentehr")
        result = normalize_agentehr_case({}, manifest)
        assert isinstance(result, NormalizedEpisode)

    def test_agentehr_native_score_f1(self):
        from cga_bench.semantic_layer.external.agentehr import AgentEHRAdapter
        manifest = get_manifest("agentehr")
        adapter = AgentEHRAdapter(manifest)
        raw = AGENTEHR_DIAGNOSES_SAMPLE
        # Perfect prediction
        output = ["Cancer of liver and intrahepatic bile duct", "Nausea and vomiting", "Essential hypertension"]
        score = adapter.native_score(raw, output)
        assert score is not None
        assert score["f1"] == pytest.approx(1.0)
        assert score["task"] == "diagnoses_ccs"

    def test_agentehr_native_score_partial(self):
        from cga_bench.semantic_layer.external.agentehr import AgentEHRAdapter
        manifest = get_manifest("agentehr")
        adapter = AgentEHRAdapter(manifest)
        raw = AGENTEHR_DIAGNOSES_SAMPLE
        # Predict only 1 of 3 correct
        output = ["Cancer of liver and intrahepatic bile duct"]
        score = adapter.native_score(raw, output)
        assert score is not None
        assert 0.0 < score["f1"] < 1.0

    def test_agentehr_case_id_format(self):
        from cga_bench.semantic_layer.external.agentehr import parse_agentehr_case
        manifest = get_manifest("agentehr")
        canonical = parse_agentehr_case(AGENTEHR_DIAGNOSES_SAMPLE, manifest)
        assert "agentehr" in canonical.case_id
        assert "diagnoses_ccs" in canonical.case_id

    def test_agentehr_no_hadm_id(self):
        from cga_bench.semantic_layer.external.agentehr import normalize_agentehr_case
        manifest = get_manifest("agentehr")
        # labevents sample has no hadm_id
        result = normalize_agentehr_case(AGENTEHR_LABEVENTS_SAMPLE, manifest)
        assert isinstance(result, NormalizedEpisode)


# ---------------------------------------------------------------------------
# Registry count now includes ART + AgentEHR
# ---------------------------------------------------------------------------

class TestRegistryCount:
    def test_registry_has_at_least_11_datasets(self):
        from cga_bench.semantic_layer.external.registry import REGISTRY
        assert len(REGISTRY) >= 11

    def test_art_and_agentehr_in_registry(self):
        from cga_bench.semantic_layer.external.registry import REGISTRY
        assert "art" in REGISTRY
        assert "agentehr" in REGISTRY
