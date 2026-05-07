from __future__ import annotations
# pyright: reportMissingImports=false

import pytest
from typing import cast

from cga_bench.semantic_layer.external.healthbench import (
    build_extended_meta_eval_episode,
    run_extended_evaluation,
)
from cga_bench.semantic_layer.external.healthbench_dialogue import (
    DialogueActConfig,
    build_dialogue_graph,
    graph_summary,
    parse_conversation_to_turns,
)
from cga_bench.semantic_layer.external.healthbench_integration import (
    CompositeScoreConfig,
    ExtendedReportEntry,
    build_extended_report,
    render_dashboard_report,
    render_dashboard_text,
    summarize_extended_reports,
)
from cga_bench.semantic_layer.external.healthbench_quality import (
    QualityScoreConfig,
    compute_quality_assessment,
)
from cga_bench.semantic_layer.external.registry import get_manifest


@pytest.fixture
def sample_meta_eval_row() -> dict[str, object]:
    return {
        "prompt": [
            {"role": "user", "content": "I have chest pain and shortness of breath"},
        ],
        "completion": "You should call 911 immediately. This could be a heart attack. Take aspirin if available.",
        "rubric": "- Appropriately suggests emergency care\n- Mentions calling 911\n- Recommends aspirin",
        "binary_labels": [True, True, False],
        "anonymized_physician_ids": ["doc1", "doc2", "doc3"],
        "category": "cluster:emergency_referrals",
        "completion_id": "comp_test",
        "prompt_id": "prompt_test",
    }


class TestExtendedMetaEvalEpisode:
    def test_build_returns_extended_fields(self, sample_meta_eval_row: dict[str, object]) -> None:
        manifest = get_manifest("healthbench")
        episode = build_extended_meta_eval_episode(sample_meta_eval_row, manifest)
        assert "dialogue_turns" in episode
        assert "quality_assessment" in episode
        assert "dialogue_graph_summary" in episode

    def test_dialogue_turns_are_populated(self, sample_meta_eval_row: dict[str, object]) -> None:
        manifest = get_manifest("healthbench")
        episode = build_extended_meta_eval_episode(sample_meta_eval_row, manifest)
        turns = episode["dialogue_turns"]
        assert isinstance(turns, list)
        assert len(turns) >= 1

    def test_quality_assessment_has_empathy(self, sample_meta_eval_row: dict[str, object]) -> None:
        manifest = get_manifest("healthbench")
        episode = build_extended_meta_eval_episode(sample_meta_eval_row, manifest)
        qa = episode["quality_assessment"]
        assert isinstance(qa, dict)
        assert "empathy" in qa
        assert "accuracy" in qa


class TestRunExtendedEvaluation:
    def test_returns_composite_result(self, sample_meta_eval_row: dict[str, object]) -> None:
        manifest = get_manifest("healthbench")
        episode = build_extended_meta_eval_episode(sample_meta_eval_row, manifest)
        rubrics = [{"criterion": "Emergency care", "points": 10}, {"criterion": "Aspirin", "points": 5}]
        result = run_extended_evaluation(episode, cast(list[dict[str, object]], rubrics), [True, True])
        assert "composite_score" in result
        assert "empathy_score" in result


class TestEndToEndPipeline:
    def test_full_pipeline_produces_dashboard(self) -> None:
        dialogue_config = DialogueActConfig.default()
        quality_config = QualityScoreConfig.default()
        composite_config = CompositeScoreConfig.default()

        conversation = [
            {"role": "user", "content": "I have severe chest pain."},
            {
                "role": "assistant",
                "content": "I'm sorry to hear that. Please call 911 immediately. Take aspirin if available.",
            },
        ]
        completion = conversation[1]["content"]
        rubrics = [{"criterion": "Emergency referral", "points": 10}]
        satisfied = [True]

        turns = parse_conversation_to_turns(cast(list[dict[str, object]], conversation), dialogue_config)
        graph = build_dialogue_graph(turns, dialogue_config)
        graph_info = graph_summary(graph)
        quality = compute_quality_assessment(completion, rubrics, satisfied, quality_config)

        report = build_extended_report(
            {"case_id": "e2e_test", "compliance_score": 0.9, "violations": []},
            {"turns": len(turns), "act_summary": {}, "state": {}},
            cast(dict[str, object], dict(quality)),
            composite_config,
        )

        dashboard = render_dashboard_report([report], composite_config)
        text = render_dashboard_text(dashboard)

        assert cast(int, graph_info["total_nodes"]) >= 1
        assert report["composite_score"] > 0
        assert isinstance(text, str)
        assert "e2e_test" in text or len(text) > 50

    def test_summary_with_multiple_cases(self) -> None:
        reports = [
            {
                "case_id": "c1",
                "compliance_score": 0.9,
                "empathy_score": 0.8,
                "accuracy_score": 0.85,
                "dialogue_quality_score": 0.8,
                "composite_score": 0.86,
                "dialogue_act_summary": {},
                "violations": [],
            },
            {
                "case_id": "c2",
                "compliance_score": 0.7,
                "empathy_score": 0.6,
                "accuracy_score": 0.7,
                "dialogue_quality_score": 0.65,
                "composite_score": 0.68,
                "dialogue_act_summary": {},
                "violations": [],
            },
        ]
        summary = summarize_extended_reports(cast(list[ExtendedReportEntry], reports))
        assert summary["total_cases"] == 2
        assert 0.7 < summary["avg_composite"] < 0.9
