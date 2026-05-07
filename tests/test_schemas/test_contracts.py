from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from cga_bench.cpg_model.schemas.contracts import (
    ActionEvent,
    ConstraintOutput,
    EpisodeLog,
    ExperimentConfig,
    ExternalParseResult,
    ScoreReport,
    ViolationRecord,
)


FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "schema_samples"


def _load_fixture(name: str) -> dict:
    return json.loads((FIXTURES_DIR / name).read_text(encoding="utf-8"))


def test_constraint_output_round_trip() -> None:
    payload = _load_fixture("constraint_output.json")
    first = ConstraintOutput.model_validate(payload)
    second = ConstraintOutput.model_validate_json(first.model_dump_json())
    assert second == first


def test_constraint_output_validation_error() -> None:
    with pytest.raises(ValidationError):
        ConstraintOutput.model_validate({"deadlines": ["not-a-dict"]})


def test_action_event_round_trip() -> None:
    payload = _load_fixture("action_event.json")
    first = ActionEvent.model_validate(payload)
    second = ActionEvent.model_validate_json(first.model_dump_json())
    assert second == first


def test_action_event_validation_error() -> None:
    with pytest.raises(ValidationError):
        ActionEvent.model_validate({"action_id": "order_lab_lactate"})


def test_violation_record_round_trip() -> None:
    payload = _load_fixture("violation_record.json")
    first = ViolationRecord.model_validate(payload)
    second = ViolationRecord.model_validate_json(first.model_dump_json())
    assert second == first


@pytest.mark.parametrize("invalid_severity", [0, 6])
def test_violation_record_validation_error(invalid_severity: int) -> None:
    with pytest.raises(ValidationError):
        ViolationRecord.model_validate(
            {
                "violation_type": "omission",
                "action_id": "order_lab_blood_culture",
                "severity": invalid_severity,
            }
        )


def test_score_report_round_trip() -> None:
    payload = _load_fixture("score_report.json")
    first = ScoreReport.model_validate(payload)
    second = ScoreReport.model_validate_json(first.model_dump_json())
    assert second == first


def test_score_report_validation_error() -> None:
    with pytest.raises(ValidationError):
        ScoreReport.model_validate(
            {
                "final_score": -0.1,
                "action_coverage": 0.9,
                "compliance_score": 0.8,
                "peak_risk": 0.2,
                "aggregate_risk": 0.3,
            }
        )


def test_episode_log_round_trip() -> None:
    payload = _load_fixture("episode_log.json")
    first = EpisodeLog.model_validate(payload)
    second = EpisodeLog.model_validate_json(first.model_dump_json())
    assert second == first


def test_episode_log_validation_error() -> None:
    with pytest.raises(ValidationError):
        EpisodeLog.model_validate({"events": []})


def test_external_parse_result_round_trip() -> None:
    payload = _load_fixture("external_parse_result.json")
    first = ExternalParseResult.model_validate(payload)
    second = ExternalParseResult.model_validate_json(first.model_dump_json())
    assert second == first


def test_external_parse_result_validation_error() -> None:
    with pytest.raises(ValidationError):
        ExternalParseResult.model_validate({"domain": "sepsis"})


def test_experiment_config_round_trip() -> None:
    payload = _load_fixture("experiment_config.json")
    first = ExperimentConfig.model_validate(payload)
    second = ExperimentConfig.model_validate_json(first.model_dump_json())
    assert second == first


def test_experiment_config_validation_error() -> None:
    with pytest.raises(ValidationError):
        ExperimentConfig.model_validate({"experiment_name": "neurips_main", "num_runs": 0})
