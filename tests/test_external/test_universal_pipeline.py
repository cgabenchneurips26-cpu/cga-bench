"""Tests for the universal external benchmark pipeline.

Covers:
1. Registry: all 8 datasets registered, get_manifest, list_datasets
2. Pipeline: raw_to_canonical, build_expected_actions, process_case for each TaskType
3. C1-C5 masking: SubScoreMask propagation
4. Pseudo-episode: static QA wrapper
5. EvalMode classification: 4 modes correctly assigned
6. Criterion classification: action/assessment/explanation
"""

from typing import cast

import pytest

from cga_bench.semantic_layer.external.models import (
    CanonicalCase,
    CriterionKind,
    EvalMode,
    ExpectedAction,
    NormalizedEpisode,
    SubScoreMask,
    TaskType,
)
from cga_bench.semantic_layer.external.pipeline import (
    build_expected_actions,
    canonical_to_normalized,
    classify_criterion,
    process_case,
    raw_to_canonical,
)
from cga_bench.semantic_layer.external.pseudo_episode import wrap_as_pseudo_episode
from cga_bench.semantic_layer.external.registry import REGISTRY, get_manifest, list_datasets


class TestRegistry:
    """All 8 datasets must be registered with correct config."""

    def test_registry_has_all_entries(self):
        assert len(REGISTRY) >= 8

    def test_list_datasets_returns_all(self):
        datasets = list_datasets()
        assert len(datasets) >= 8
        expected = {
            "amega",
            "clibench",
            "medguide",
            "cancerguide",
            "mtbbench",
            "ehrstruct",
            "llmeval_med",
            "nice",
        }
        assert expected.issubset(set(datasets))

    def test_get_manifest_by_id(self):
        m = get_manifest("amega")
        assert m.dataset_id == "amega"
        assert m.task_type == TaskType.OPEN_QA
        assert m.eval_mode == EvalMode.DERIVED_TRACK_B

    def test_get_manifest_case_insensitive(self):
        m = get_manifest("CliBench")
        assert m.dataset_id == "clibench"

    def test_get_manifest_unknown_raises(self):
        with pytest.raises(KeyError):
            _ = get_manifest("nonexistent_dataset")

    @pytest.mark.parametrize(
        "dataset_id,expected_eval_mode",
        [
            ("amega", EvalMode.DERIVED_TRACK_B),
            ("clibench", EvalMode.DERIVED_TRACK_B),
            ("medguide", EvalMode.DERIVED_TRACK_B),
            ("cancerguide", EvalMode.TRACK_A_ONLY),
            ("mtbbench", EvalMode.TRACK_A_ONLY),
            ("ehrstruct", EvalMode.SAFETY_ONLY),
            ("llmeval_med", EvalMode.TRACK_A_ONLY),
            ("nice", EvalMode.DERIVED_TRACK_B),
        ],
    )
    def test_eval_mode_classification(self, dataset_id: str, expected_eval_mode: EvalMode):
        m = get_manifest(dataset_id)
        assert m.eval_mode == expected_eval_mode

    @pytest.mark.parametrize(
        "dataset_id,expected_access",
        [
            ("amega", "public"),
            ("clibench", "credentialed"),
            ("mtbbench", "credentialed"),
            ("ehrstruct", "public"),
        ],
    )
    def test_access_level(self, dataset_id: str, expected_access: str):
        m = get_manifest(dataset_id)
        assert m.access_level == expected_access


class TestCriterionClassification:
    """Classify criteria into action/assessment/explanation."""

    @pytest.mark.parametrize(
        "text,expected",
        [
            ("Order CBC and BMP", CriterionKind.ACTION),
            ("Prescribe metformin", CriterionKind.ACTION),
            ("Explain the risks of surgery", CriterionKind.EXPLANATION),
            ("Counsel patient on diet", CriterionKind.EXPLANATION),
            ("Recognize signs of shock", CriterionKind.ASSESSMENT),
            ("Differential diagnosis includes PE", CriterionKind.ASSESSMENT),
        ],
    )
    def test_classify(self, text: str, expected: CriterionKind):
        assert classify_criterion(text) == expected


class TestPipelineOpenQA:
    """AMEGA-style: open_qa with criteria -> filter ACTION only."""

    def test_amega_filters_action_criteria(self):
        manifest = get_manifest("amega")
        raw = {
            "id": "amega_1",
            "narrative": "Patient with chest pain",
            "criteria": [
                {"text": "Order 12-lead ECG"},
                {"text": "Explain risks to patient"},
                {"text": "Recognize STEMI pattern"},
                {"text": "Administer aspirin 325mg"},
            ],
        }
        result = process_case(raw, manifest)
        assert isinstance(result, NormalizedEpisode)
        assert len(result.actions) == 2
        assert any("order" in action for action in result.actions)
        assert any("administer" in action or "aspirin" in action for action in result.actions)


class TestPipelineMCQPath:
    """MedGUIDE-style: mcq_path with decision path -> intermediate + leaf."""

    def test_medguide_path_extraction(self):
        manifest = get_manifest("medguide")
        raw = {
            "id": "mg_1",
            "profile": "NSCLC Stage IIIA",
            "path": "Staging -> Molecular Testing -> Pembrolizumab",
            "disease": "NSCLC",
        }
        result = process_case(raw, manifest)
        assert len(result.actions) == 3
        assert result.actions[0].startswith("decision/")
        assert result.actions[1].startswith("decision/")
        assert result.actions[2].startswith("plan/")
        assert result.guideline_id == "oncology"


class TestPipelineMultilabelAction:
    """CliBench-style: multilabel targets with namespace."""

    def test_clibench_namespace_actions(self):
        manifest = get_manifest("clibench")
        raw = {
            "id": "cb_1",
            "target_laborders": ["CBC", "BMP", "Troponin"],
            "target_prescriptions": ["Aspirin", "Heparin"],
            "instruction": "Order labs and meds for ACS",
        }
        result = process_case(raw, manifest)
        lab_actions = [action for action in result.actions if action.startswith("lab/")]
        med_actions = [action for action in result.actions if action.startswith("med/")]
        assert len(lab_actions) == 3
        assert len(med_actions) == 2

    def test_clibench_diagnosis_lower_confidence(self):
        manifest = get_manifest("clibench")
        raw = {
            "id": "cb_2",
            "target_diagnoses": ["Sepsis"],
        }
        canonical = raw_to_canonical(raw, manifest)
        expected = build_expected_actions(canonical)
        dx_actions = [ea for ea in expected if ea.action_id.startswith("dx/")]
        assert len(dx_actions) == 1
        assert dx_actions[0].confidence < 1.0


class TestCliBenchTaskLevelEvalMode:
    """CliBench diagnosis vs procedure eval_mode separation."""

    def test_diagnosis_actions_tagged_track_a_only(self):
        manifest = get_manifest("clibench")
        raw = {"id": "cb_eval", "target_diagnoses": ["Sepsis"]}
        canonical = raw_to_canonical(raw, manifest)
        expected = build_expected_actions(canonical)
        assert len(expected) == 1
        assert "eval=track_a_only" in expected[0].provenance

    def test_procedure_actions_tagged_derived_track_b(self):
        manifest = get_manifest("clibench")
        raw = {"id": "cb_eval2", "target_procedures": ["PCI"]}
        canonical = raw_to_canonical(raw, manifest)
        expected = build_expected_actions(canonical)
        assert len(expected) == 1
        assert "eval=derived_track_b" in expected[0].provenance


class TestPipelineStructuredEHR:
    """EHRStruct-style: safety_only, minimal actions."""

    def test_ehrstruct_safety_only(self):
        manifest = get_manifest("ehrstruct")
        raw = {"id": "ehr_1", "gold_answer": "elevated creatinine"}
        result = process_case(raw, manifest)
        assert "eval_mode:safety_only" in result.evidence.notes[0]
        mask_notes = [note for note in result.evidence.notes if note.startswith("mask:")]
        assert len(mask_notes) == 1
        assert "C1=False" in mask_notes[0]


class TestPipelineTripletQA:
    """NICE-style: single answer -> one expected action."""

    def test_nice_single_answer(self):
        manifest = get_manifest("nice")
        raw = {"id": "nice_1", "answer": "Start ACE inhibitor"}
        result = process_case(raw, manifest)
        assert len(result.actions) == 1
        assert "ace_inhibitor" in result.actions[0] or "start" in result.actions[0]


class TestPipelineLongitudinal:
    """CancerGUIDE/MTBBench-style: timeline -> sequential actions."""

    def test_cancerguide_timeline(self):
        manifest = get_manifest("cancerguide")
        raw = {
            "id": "cg_1",
            "timeline_events": [
                {"action": "biopsy"},
                {"action": "staging_ct"},
                {"action": "chemotherapy"},
            ],
        }
        canonical = raw_to_canonical(raw, manifest)
        expected = build_expected_actions(canonical)
        assert len(expected) == 3
        assert expected[2].required_before is not None
        assert len(expected[2].required_before) == 2


class TestSubScoreMask:
    """C1-C5 masking propagates through pipeline."""

    def test_amega_c4_c5_off(self):
        manifest = get_manifest("amega")
        assert manifest.sub_score_mask.c4_timing_compliance is False
        assert manifest.sub_score_mask.c5_sequence_integrity is False

    def test_ehrstruct_all_off(self):
        manifest = get_manifest("ehrstruct")
        mask = manifest.sub_score_mask
        assert mask.c1_path_selection is False
        assert mask.c2_mandatory_completion is False
        assert mask.c3_forbidden_avoidance is False
        assert mask.c4_timing_compliance is False
        assert mask.c5_sequence_integrity is False

    def test_mask_in_normalized_output(self):
        manifest = get_manifest("amega")
        raw = {"id": "mask_test", "criteria": [{"text": "Order CBC"}]}
        result = process_case(raw, manifest)
        mask_notes = [note for note in result.evidence.notes if note.startswith("mask:")]
        assert len(mask_notes) == 1
        assert "C4=False" in mask_notes[0]
        assert "C5=False" in mask_notes[0]


class TestPseudoEpisode:
    """Static QA -> pseudo-episode wrapper."""

    def test_wrap_creates_3_events(self):
        case = CanonicalCase(
            case_id="pseudo_1",
            dataset_id="amega",
            input_text="Patient with fever",
            task_type=TaskType.OPEN_QA,
            eval_mode=EvalMode.TRACK_A_ONLY,
        )
        actions = [ExpectedAction(action_id="order_cbc", kind="mandatory")]
        episode = wrap_as_pseudo_episode(case, actions)
        events = cast(list[dict[str, object]], episode["events"])
        assert len(events) == 3
        assert episode["events"][0]["event_type"] == "observation"
        assert episode["events"][1]["event_type"] == "agent_output"
        assert episode["events"][2]["event_type"] == "score_comparison"

    def test_wrap_includes_eval_mode(self):
        case = CanonicalCase(
            case_id="p2",
            dataset_id="medguide",
            eval_mode=EvalMode.DERIVED_TRACK_B,
        )
        episode = wrap_as_pseudo_episode(case, [])
        assert episode["eval_mode"] == "derived_track_b"

    def test_wrap_includes_mask(self):
        mask = SubScoreMask(c1_path_selection=True, c4_timing_compliance=False)
        case = CanonicalCase(case_id="p3", dataset_id="nice", sub_score_mask=mask)
        episode = wrap_as_pseudo_episode(case, [])
        assert episode["sub_score_mask"]["c1"] is True
        assert episode["sub_score_mask"]["c4"] is False


class TestDomainDetection:
    """Domain auto-detection from input text."""

    @pytest.mark.parametrize(
        "instruction,expected_domain",
        [
            ("Patient with chest pain and elevated troponin", "chest_pain"),
            ("Sepsis protocol for ICU admission", "sepsis"),
            ("AKI with rising creatinine", "aki"),
            pytest.param(
                "NSCLC staging",
                "oncology",
                marks=pytest.mark.xfail(reason="NSCLC/oncology domain not yet in CPG registry"),
            ),
            ("Generic wellness check", None),
        ],
    )
    def test_domain_detection(self, instruction: str, expected_domain: str | None):
        manifest = get_manifest("clibench")
        raw: dict[str, str] = {"id": "domain_test", "instruction": instruction}
        canonical = raw_to_canonical(raw, manifest)
        assert canonical.domain == expected_domain


class TestUniversalSafetyFallback:
    def test_no_domain_gets_fallback_tag(self):
        manifest = get_manifest("clibench")
        raw = {"id": "no_domain", "instruction": "generic wellness check"}
        result = process_case(raw, manifest)
        assert any("fallback:universal_clinical_safety" in n for n in result.evidence.notes)

    def test_with_domain_no_fallback(self):
        manifest = get_manifest("clibench")
        raw = {"id": "has_domain", "instruction": "chest pain and elevated troponin"}
        result = process_case(raw, manifest)
        assert not any("fallback" in n for n in result.evidence.notes)


class TestCanonicalToNormalizedBridge:
    """Bridge conversion retains expected action semantics."""

    def test_canonical_to_normalized_sets_required_actions(self):
        case = CanonicalCase(
            case_id="bridge_1",
            dataset_id="testbench",
            task_type=TaskType.OPEN_QA,
            eval_mode=EvalMode.TRACK_A_ONLY,
            input_text="test",
        )
        expected_actions = [
            ExpectedAction(action_id="a1", kind="mandatory"),
            ExpectedAction(action_id="a2", kind="forbidden"),
        ]

        result = canonical_to_normalized(case, expected_actions)

        assert isinstance(result, NormalizedEpisode)
        assert result.actions == ["a1", "a2"]
        assert result.required_actions == ["a1"]


class TestMalformedInput:
    """Pipeline handles malformed/empty input gracefully."""

    def test_empty_dict_no_crash(self):
        manifest = get_manifest("amega")
        result = process_case({}, manifest)
        assert isinstance(result, NormalizedEpisode)
        assert result.case_id == "unknown"

    def test_none_fields_no_crash(self):
        manifest = get_manifest("clibench")
        result = process_case({"id": None, "instruction": None}, manifest)
        assert isinstance(result, NormalizedEpisode)

    def test_wrong_types_no_crash(self):
        manifest = get_manifest("medguide")
        result = process_case({"path": 12345, "disease": ["not_a_string"]}, manifest)
        assert isinstance(result, NormalizedEpisode)

    def test_missing_all_targets_warns(self):
        manifest = get_manifest("clibench")
        result = process_case({"id": "empty_cb"}, manifest)
        assert "no_expected_actions" in result.warnings


class TestEndToEndFlow:
    """Full pipeline flow: raw -> canonical -> expected -> normalized -> pseudo_episode."""

    def test_amega_full_flow(self):
        from cga_bench.semantic_layer.external.pipeline import build_expected_actions, raw_to_canonical
        from cga_bench.semantic_layer.external.pseudo_episode import wrap_as_pseudo_episode

        manifest = get_manifest("amega")
        raw = {
            "id": "e2e_amega",
            "narrative": "55yo M with chest pain",
            "criteria": [
                {"text": "Order 12-lead ECG"},
                {"text": "Administer aspirin"},
                {"text": "Explain procedure to patient"},
            ],
        }
        canonical = raw_to_canonical(raw, manifest)
        expected = build_expected_actions(canonical)
        normalized = process_case(raw, manifest)
        episode = wrap_as_pseudo_episode(canonical, expected, agent_actions=["order_ecg"])

        assert canonical.dataset_id == "amega"
        assert len(expected) == 2
        assert normalized.source_benchmark == "amega"
        assert len(episode["events"]) == 3
        assert episode["eval_mode"] == "derived_track_b"
        assert episode["sub_score_mask"]["c4"] is False

    def test_clibench_full_flow(self):
        from cga_bench.semantic_layer.external.pipeline import build_expected_actions, raw_to_canonical
        from cga_bench.semantic_layer.external.pseudo_episode import wrap_as_pseudo_episode

        manifest = get_manifest("clibench")
        raw = {
            "id": "e2e_cb",
            "target_laborders": ["CBC"],
            "target_prescriptions": ["Aspirin"],
            "instruction": "Manage ACS patient",
        }
        canonical = raw_to_canonical(raw, manifest)
        expected = build_expected_actions(canonical)
        _normalized = process_case(raw, manifest)
        episode = wrap_as_pseudo_episode(canonical, expected)

        assert len(expected) == 2
        assert any(ea.action_id.startswith("lab/") for ea in expected)
        assert any(ea.action_id.startswith("med/") for ea in expected)
        assert episode["metadata"]["dataset_id"] == "clibench"


class TestNormalizeDispatcherIntegration:
    """normalize_external_case routes new datasets through universal pipeline."""

    def test_amega_via_dispatcher(self):
        from cga_bench.semantic_layer.external.normalize import normalize_external_case

        raw = {"id": "disp_amega", "criteria": [{"text": "Order ECG"}]}
        result = normalize_external_case("amega", raw)
        assert isinstance(result, NormalizedEpisode)
        assert result.source_benchmark == "amega"

    def test_nice_via_dispatcher(self):
        from cga_bench.semantic_layer.external.normalize import normalize_external_case

        raw = {"id": "disp_nice", "answer": "Start metformin"}
        result = normalize_external_case("nice", raw)
        assert isinstance(result, NormalizedEpisode)
        assert result.source_benchmark == "nice"

    def test_unknown_still_raises(self):
        from cga_bench.semantic_layer.external.normalize import normalize_external_case

        with pytest.raises((ValueError, KeyError)):
            normalize_external_case("totally_unknown", {})


class TestHealthBenchNativeDispatch:
    def test_eval_row_via_dispatcher(self):
        from cga_bench.semantic_layer.external.normalize import normalize_external_case

        native_row = {
            "prompt_id": "test_hb_001",
            "prompt": [{"role": "user", "content": "I have chest pain"}],
            "rubrics": [
                {"criterion": "Advise calling 911", "points": 10, "tags": ["axis:accuracy"]},
                {"criterion": "Harmful advice", "points": -8, "tags": []},
            ],
            "example_tags": ["theme:emergency"],
        }
        result = normalize_external_case("healthbench", native_row)
        assert result.case_id != "unknown"
        assert len(result.actions) >= 1
        assert result.source_benchmark == "healthbench"

    def test_meta_eval_row_via_dispatcher(self):
        from cga_bench.semantic_layer.external.normalize import normalize_external_case

        native_row = {
            "prompt_id": "test_meta_001",
            "prompt": [{"role": "user", "content": "Allergic reaction symptoms"}],
            "rubric": "- Suggests calling 911\n- Does not provide false reassurance",
            "completion": "You should call 911 immediately.",
            "binary_labels": [True, True],
            "completion_id": "comp_001",
            "category": "cluster:emergency",
        }
        result = normalize_external_case("healthbench", native_row)
        assert result.case_id != "unknown"


class TestNICEConfidence:
    """NICE silver-standard actions should have confidence < 1.0."""

    def test_nice_answer_confidence_below_one(self):
        from cga_bench.semantic_layer.external.pipeline import build_expected_actions, raw_to_canonical

        manifest = get_manifest("nice")
        raw = {"id": "nice_conf", "answer": "Prescribe ACE inhibitor"}
        canonical = raw_to_canonical(raw, manifest)
        expected = build_expected_actions(canonical)
        assert len(expected) == 1
        assert expected[0].confidence < 1.0


class TestLLMEvalMedSafetyClauses:
    """LLMEval-Med safety clauses should map to forbidden actions."""

    def test_safety_clause_becomes_forbidden(self):
        from cga_bench.semantic_layer.external.pipeline import build_expected_actions, raw_to_canonical

        manifest = get_manifest("llmeval_med")
        raw = {
            "id": "llm_safety",
            "checklist": [
                "Order blood culture",
                "Do not give NSAIDs in renal failure",
                "Explain treatment plan",
            ],
        }
        canonical = raw_to_canonical(raw, manifest)
        expected = build_expected_actions(canonical)
        mandatory = [ea for ea in expected if ea.kind == "mandatory"]
        forbidden = [ea for ea in expected if ea.kind == "forbidden"]
        assert len(mandatory) >= 1
        assert len(forbidden) >= 1
        assert any("nsaid" in ea.action_id for ea in forbidden)


class TestAMEGAQuestionSplit:
    """AMEGA question-level splitting."""

    def test_split_produces_multiple_cases(self):
        from cga_bench.semantic_layer.external.pipeline import split_amega_questions

        manifest = get_manifest("amega")
        raw = {
            "id": "case_001",
            "narrative": "Patient with fever",
            "questions": [
                {"id": "q1", "text": "Initial workup?", "criteria": [{"text": "Order CBC"}]},
                {"id": "q2", "text": "Treatment?", "criteria": [{"text": "Prescribe antibiotics"}]},
            ],
        }
        cases = split_amega_questions(raw, manifest)
        assert len(cases) == 2
        assert cases[0].case_id == "case_001:q1"
        assert cases[1].case_id == "case_001:q2"

    def test_no_questions_fallback(self):
        from cga_bench.semantic_layer.external.pipeline import split_amega_questions

        manifest = get_manifest("amega")
        raw = {"id": "single", "criteria": [{"text": "Order ECG"}]}
        cases = split_amega_questions(raw, manifest)
        assert len(cases) == 1
