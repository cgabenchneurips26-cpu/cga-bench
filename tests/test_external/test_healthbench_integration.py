from __future__ import annotations

import pytest

evaluator = pytest.importorskip("cga_bench.semantic_layer.external.evaluator")
models = pytest.importorskip("cga_bench.semantic_layer.external.models")
healthbench_integration = pytest.importorskip(
    "cga_bench.semantic_layer.external.healthbench_integration"
)

summarize_reports = evaluator.summarize_reports
EvaluableComplianceReport = models.EvaluableComplianceReport
CompositeScoreConfig = healthbench_integration.CompositeScoreConfig
CompositeScoreResult = healthbench_integration.CompositeScoreResult
ExtendedReportEntry = healthbench_integration.ExtendedReportEntry
compute_composite_score = healthbench_integration.compute_composite_score
build_extended_report = healthbench_integration.build_extended_report
summarize_extended_reports = healthbench_integration.summarize_extended_reports
render_dashboard_report = healthbench_integration.render_dashboard_report
render_dashboard_text = healthbench_integration.render_dashboard_text
HITLConfig = healthbench_integration.HITLConfig
flag_cases_for_review = healthbench_integration.flag_cases_for_review


@pytest.fixture
def default_config() -> CompositeScoreConfig:
    return CompositeScoreConfig.default()


@pytest.fixture
def sample_compliance_report() -> dict[str, object]:
    return {
        "case_id": "test_001",
        "compliance_score": 0.85,
        "violations": [{"type": "OMISSION", "action": "order_ecg"}],
        "mandatory_actions": ["order_ecg", "give_aspirin"],
        "performed_actions": ["give_aspirin"],
        "satisfied_actions": ["give_aspirin"],
        "evaluable_actions": ["order_ecg", "give_aspirin"],
        "observability_index": 1.0,
        "evidence_summary": {},
        "notes": [],
    }


@pytest.fixture
def sample_dialogue_result() -> dict[str, object]:
    return {
        "turns": 4,
        "act_summary": {
            "EMPATHY_EXPRESS": 2,
            "INFORMATION_PROVIDE": 3,
            "QUESTION_ASK": 1,
        },
        "state": {"patient_info": {"symptom": "headache"}, "turn_count": 4},
    }


@pytest.fixture
def sample_quality_result() -> dict[str, object]:
    return {
        "empathy": {
            "empathy_score": 0.75,
            "keyword_hits": 3,
            "negative_hits": 0,
            "text_length": 200,
            "method": "keyword",
        },
        "accuracy": {
            "accuracy_score": 0.9,
            "criteria_satisfied": 9,
            "criteria_total": 10,
            "weighted_score": 0.88,
        },
        "composite_quality": 0.84,
    }


@pytest.fixture
def sample_extended_report() -> ExtendedReportEntry:
    return {
        "case_id": "test_001",
        "compliance_score": 0.85,
        "empathy_score": 0.7,
        "accuracy_score": 0.8,
        "dialogue_quality_score": 0.75,
        "composite_score": 0.8,
        "dialogue_act_summary": {
            "EMPATHY_EXPRESS": 2,
            "INFORMATION_PROVIDE": 3,
        },
        "violations": [{"type": "OMISSION"}],
    }


class TestCompositeScoreConfigContract:
    def test_default_factory_uses_expected_weights(self) -> None:
        config = CompositeScoreConfig.default()
        assert config.task_success_weight == 0.6
        assert config.dialogue_quality_weight == 0.4

    def test_invalid_weight_sum_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            _ = CompositeScoreConfig(task_success_weight=0.7, dialogue_quality_weight=0.4)

    def test_negative_weight_raises_value_error(self) -> None:
        with pytest.raises(ValueError):
            _ = CompositeScoreConfig(task_success_weight=-0.1, dialogue_quality_weight=1.1)


class TestComputeCompositeScoreContract:
    def test_perfect_scores_produce_one(self, default_config: CompositeScoreConfig) -> None:
        result = compute_composite_score(1.0, 1.0, default_config)
        assert result["final_score"] == 1.0
        assert result["task_success_score"] == 1.0
        assert result["dialogue_quality_score"] == 1.0

    def test_zero_quality_uses_task_weight_only(self, default_config: CompositeScoreConfig) -> None:
        result = compute_composite_score(1.0, 0.0, default_config)
        assert result["final_score"] == pytest.approx(0.6, abs=1e-9)

    def test_zero_task_uses_quality_weight_only(self, default_config: CompositeScoreConfig) -> None:
        result = compute_composite_score(0.0, 1.0, default_config)
        assert result["final_score"] == pytest.approx(0.4, abs=1e-9)

    def test_balanced_scores_match_weighted_sum(self, default_config: CompositeScoreConfig) -> None:
        result = compute_composite_score(0.8, 0.6, default_config)
        assert result["final_score"] == pytest.approx(0.72, abs=1e-9)

    def test_score_is_clamped_to_closed_interval(self, default_config: CompositeScoreConfig) -> None:
        result = compute_composite_score(1.5, -0.5, default_config)
        assert 0.0 <= result["final_score"] <= 1.0
        assert 0.0 <= result["task_success_score"] <= 1.0
        assert 0.0 <= result["dialogue_quality_score"] <= 1.0

    def test_result_contains_full_typed_dict_contract(self, default_config: CompositeScoreConfig) -> None:
        result: CompositeScoreResult = compute_composite_score(0.9, 0.8, default_config)
        expected_keys = {
            "final_score",
            "task_success_score",
            "dialogue_quality_score",
            "empathy_score",
            "accuracy_score",
            "component_weights",
        }
        assert expected_keys.issubset(result.keys())


class TestBuildExtendedReportContract:
    def test_full_data_populates_all_fields(
        self,
        sample_compliance_report: dict[str, object],
        sample_dialogue_result: dict[str, object],
        sample_quality_result: dict[str, object],
        default_config: CompositeScoreConfig,
    ) -> None:
        report = build_extended_report(
            sample_compliance_report,
            sample_dialogue_result,
            sample_quality_result,
            default_config,
        )

        assert report["case_id"] == "test_001"
        assert report["compliance_score"] == pytest.approx(0.85, abs=1e-9)
        assert report["empathy_score"] == pytest.approx(0.75, abs=1e-9)
        assert report["accuracy_score"] == pytest.approx(0.9, abs=1e-9)
        assert report["dialogue_quality_score"] == pytest.approx(0.84, abs=1e-9)
        assert report["composite_score"] == pytest.approx(0.846, abs=1e-9)
        assert report["dialogue_act_summary"] == {
            "EMPATHY_EXPRESS": 2,
            "INFORMATION_PROVIDE": 3,
            "QUESTION_ASK": 1,
        }
        assert report["violations"] == [{"type": "OMISSION", "action": "order_ecg"}]

    def test_missing_dialogue_defaults_dialogue_fields_to_zero(
        self,
        sample_compliance_report: dict[str, object],
        sample_quality_result: dict[str, object],
        default_config: CompositeScoreConfig,
    ) -> None:
        report = build_extended_report(
            sample_compliance_report,
            None,
            sample_quality_result,
            default_config,
        )
        assert report["dialogue_act_summary"] == {}
        assert report["dialogue_quality_score"] == pytest.approx(0.84, abs=1e-9)

    def test_missing_quality_defaults_quality_scores_to_zero(
        self,
        sample_compliance_report: dict[str, object],
        sample_dialogue_result: dict[str, object],
        default_config: CompositeScoreConfig,
    ) -> None:
        report = build_extended_report(
            sample_compliance_report,
            sample_dialogue_result,
            None,
            default_config,
        )
        assert report["empathy_score"] == 0.0
        assert report["accuracy_score"] == 0.0
        assert report["dialogue_quality_score"] == 0.0

    def test_both_optional_inputs_missing_keeps_compliance_passthrough(
        self,
        sample_compliance_report: dict[str, object],
        default_config: CompositeScoreConfig,
    ) -> None:
        report = build_extended_report(sample_compliance_report, None, None, default_config)
        assert report["case_id"] == "test_001"
        assert report["compliance_score"] == pytest.approx(0.85, abs=1e-9)
        assert report["empathy_score"] == 0.0
        assert report["accuracy_score"] == 0.0
        assert report["dialogue_quality_score"] == 0.0
        assert report["dialogue_act_summary"] == {}
        assert report["violations"] == [{"type": "OMISSION", "action": "order_ecg"}]

    def test_report_contains_full_typed_dict_contract(
        self,
        sample_compliance_report: dict[str, object],
        sample_dialogue_result: dict[str, object],
        sample_quality_result: dict[str, object],
        default_config: CompositeScoreConfig,
    ) -> None:
        report = build_extended_report(
            sample_compliance_report,
            sample_dialogue_result,
            sample_quality_result,
            default_config,
        )
        expected_keys = {
            "case_id",
            "compliance_score",
            "empathy_score",
            "accuracy_score",
            "dialogue_quality_score",
            "composite_score",
            "dialogue_act_summary",
            "violations",
        }
        assert expected_keys.issubset(report.keys())


class TestSummarizeExtendedReportsContract:
    def test_multiple_reports_average_fields_correctly(self) -> None:
        reports: list[ExtendedReportEntry] = [
            {
                "case_id": "c1",
                "compliance_score": 0.8,
                "empathy_score": 0.6,
                "accuracy_score": 0.9,
                "dialogue_quality_score": 0.7,
                "composite_score": 0.76,
                "dialogue_act_summary": {"EMPATHY_EXPRESS": 1},
                "violations": [],
            },
            {
                "case_id": "c2",
                "compliance_score": 0.6,
                "empathy_score": 0.4,
                "accuracy_score": 0.7,
                "dialogue_quality_score": 0.5,
                "composite_score": 0.56,
                "dialogue_act_summary": {"QUESTION_ASK": 2},
                "violations": [{"type": "OMISSION", "action": "order_ecg"}],
            },
        ]
        summary = summarize_extended_reports(reports)
        assert summary["avg_composite"] == pytest.approx(0.66, abs=1e-9)
        assert summary["avg_empathy"] == pytest.approx(0.5, abs=1e-9)
        assert summary["avg_accuracy"] == pytest.approx(0.8, abs=1e-9)
        assert summary["avg_dialogue_quality"] == pytest.approx(0.6, abs=1e-9)
        assert summary["total_cases"] == 2

    def test_single_report_summary_matches_input_values(self) -> None:
        reports: list[ExtendedReportEntry] = [
            {
                "case_id": "single",
                "compliance_score": 0.9,
                "empathy_score": 0.8,
                "accuracy_score": 0.7,
                "dialogue_quality_score": 0.75,
                "composite_score": 0.84,
                "dialogue_act_summary": {"INFORMATION_PROVIDE": 4},
                "violations": [],
            }
        ]
        summary = summarize_extended_reports(reports)
        assert summary["avg_composite"] == pytest.approx(0.84, abs=1e-9)
        assert summary["avg_empathy"] == pytest.approx(0.8, abs=1e-9)
        assert summary["avg_accuracy"] == pytest.approx(0.7, abs=1e-9)
        assert summary["avg_dialogue_quality"] == pytest.approx(0.75, abs=1e-9)
        assert summary["total_cases"] == 1

    def test_empty_report_list_returns_zero_summary(self) -> None:
        summary = summarize_extended_reports([])
        assert summary["avg_composite"] == 0.0
        assert summary["avg_empathy"] == 0.0
        assert summary["avg_accuracy"] == 0.0
        assert summary["avg_dialogue_quality"] == 0.0
        assert summary["total_cases"] == 0

    def test_summary_output_is_backward_compatible_with_summarize_reports(self) -> None:
        base_reports = [
            EvaluableComplianceReport(
                case_id="c1",
                guideline_id="guideline_1",
                mandatory_actions=["order_ecg"],
                performed_actions=["order_ecg"],
                evaluable_actions=["order_ecg"],
                not_observable_actions=[],
                satisfied_actions=["order_ecg"],
                violations=[],
                observability_index=1.0,
                compliance_score=1.0,
                evidence_summary={"evidence": {"vitals": True}},
                notes=[],
            )
        ]
        base_summary = summarize_reports(base_reports)
        ext_summary = summarize_extended_reports(
            [
                {
                    "case_id": "c1",
                    "compliance_score": 1.0,
                    "empathy_score": 0.7,
                    "accuracy_score": 0.9,
                    "dialogue_quality_score": 0.8,
                    "composite_score": 0.92,
                    "dialogue_act_summary": {"EMPATHY_EXPRESS": 1},
                    "violations": [],
                }
            ]
        )
        merged = {**base_summary, **ext_summary}
        assert "average_evaluable_compliance" in merged
        assert "avg_composite" in merged
        assert merged["total_cases"] == 1


class TestDashboardReport:
    def test_render_returns_correct_structure(
        self,
        default_config: CompositeScoreConfig,
        sample_extended_report: ExtendedReportEntry,
    ) -> None:
        reports = [sample_extended_report]
        result = render_dashboard_report(reports, default_config)
        assert "header" in result
        assert "sections" in result
        assert "summary_table" in result
        assert "footer" in result

    def test_sections_cover_all_metrics(
        self,
        default_config: CompositeScoreConfig,
        sample_extended_report: ExtendedReportEntry,
    ) -> None:
        reports = [sample_extended_report]
        result = render_dashboard_report(reports, default_config)
        section_titles = {s["title"] for s in result["sections"]}
        assert "Compliance Overview" in section_titles
        assert "Empathy Assessment" in section_titles
        assert "Accuracy Assessment" in section_titles
        assert "Dialogue Quality" in section_titles
        assert "Composite Score" in section_titles

    def test_empty_reports_still_renders(self, default_config: CompositeScoreConfig) -> None:
        result = render_dashboard_report([], default_config)
        assert result["header"]
        assert len(result["sections"]) >= 1
        assert result["summary_table"] == []

    def test_render_text_returns_string(
        self,
        default_config: CompositeScoreConfig,
        sample_extended_report: ExtendedReportEntry,
    ) -> None:
        reports = [sample_extended_report]
        dashboard = render_dashboard_report(reports, default_config)
        text = render_dashboard_text(dashboard)
        assert isinstance(text, str)
        assert len(text) > 50

    def test_render_text_contains_sections_and_table(
        self,
        default_config: CompositeScoreConfig,
        sample_extended_report: ExtendedReportEntry,
    ) -> None:
        dashboard = render_dashboard_report(
            [sample_extended_report],
            default_config,
        )
        text = render_dashboard_text(dashboard)
        assert "=== COMPLIANCE OVERVIEW ===" in text
        assert "=== SUMMARY TABLE ===" in text
        assert "Case" in text


class TestHITLFlagging:
    def test_low_composite_flagged(self) -> None:
        reports: list[ExtendedReportEntry] = [
            {
                "case_id": "c1",
                "compliance_score": 0.1,
                "empathy_score": 0.1,
                "accuracy_score": 0.1,
                "dialogue_quality_score": 0.1,
                "composite_score": 0.1,
                "dialogue_act_summary": {},
                "violations": [],
            }
        ]
        flags = flag_cases_for_review(reports)
        assert any(f["case_id"] == "c1" and f["reason"] == "low_confidence" for f in flags)

    def test_high_quality_not_flagged(self) -> None:
        reports: list[ExtendedReportEntry] = [
            {
                "case_id": "c1",
                "compliance_score": 0.9,
                "empathy_score": 0.8,
                "accuracy_score": 0.85,
                "dialogue_quality_score": 0.8,
                "composite_score": 0.9,
                "dialogue_act_summary": {},
                "violations": [],
            }
        ]
        flags = flag_cases_for_review(reports)
        assert len(flags) == 0

    def test_empathy_gap_detected(self) -> None:
        reports: list[ExtendedReportEntry] = [
            {
                "case_id": "c1",
                "compliance_score": 0.8,
                "empathy_score": 0.1,
                "accuracy_score": 0.9,
                "dialogue_quality_score": 0.5,
                "composite_score": 0.7,
                "dialogue_act_summary": {},
                "violations": [],
            }
        ]
        flags = flag_cases_for_review(reports)
        reasons = [f["reason"] for f in flags]
        assert any("empathy" in r.lower() for r in reasons)

    def test_empty_reports_no_flags(self) -> None:
        assert flag_cases_for_review([]) == []

    def test_high_divergence_flagged(self) -> None:
        reports: list[ExtendedReportEntry] = [
            {
                "case_id": "c-div",
                "compliance_score": 0.6,
                "empathy_score": 0.1,
                "accuracy_score": 0.7,
                "dialogue_quality_score": 0.6,
                "composite_score": 0.6,
                "dialogue_act_summary": {},
                "violations": [],
            }
        ]
        flags = flag_cases_for_review(reports)
        assert any(f["reason"] == "metric_divergence" for f in flags)

    def test_high_violations_flagged(self) -> None:
        reports: list[ExtendedReportEntry] = [
            {
                "case_id": "c-viol",
                "compliance_score": 0.5,
                "empathy_score": 0.5,
                "accuracy_score": 0.5,
                "dialogue_quality_score": 0.5,
                "composite_score": 0.5,
                "dialogue_act_summary": {},
                "violations": [{"type": "OMISSION"}, {"type": "TIMING"}, {"type": "SEQUENCE"}],
            }
        ]
        flags = flag_cases_for_review(reports)
        assert any(f["reason"] == "high_violations" for f in flags)

    def test_config_can_disable_high_violations_flag(self) -> None:
        reports: list[ExtendedReportEntry] = [
            {
                "case_id": "c-viol",
                "compliance_score": 0.5,
                "empathy_score": 0.5,
                "accuracy_score": 0.5,
                "dialogue_quality_score": 0.5,
                "composite_score": 0.5,
                "dialogue_act_summary": {},
                "violations": [{"type": "OMISSION"}, {"type": "TIMING"}, {"type": "SEQUENCE"}],
            }
        ]
        flags = flag_cases_for_review(reports, HITLConfig(flag_high_violations=False))
        assert not any(f["reason"] == "high_violations" for f in flags)

    def test_config_can_disable_empathy_gap_flag(self) -> None:
        reports: list[ExtendedReportEntry] = [
            {
                "case_id": "c-empathy",
                "compliance_score": 0.7,
                "empathy_score": 0.1,
                "accuracy_score": 0.95,
                "dialogue_quality_score": 0.7,
                "composite_score": 0.7,
                "dialogue_act_summary": {},
                "violations": [],
            }
        ]
        flags = flag_cases_for_review(reports, HITLConfig(flag_low_empathy=False))
        assert not any(f["reason"] == "empathy_gap" for f in flags)
