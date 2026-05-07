from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .base import ViolationType


class ConstraintOutput(BaseModel):
    mandatory_actions: list[str] = Field(default_factory=list)
    forbidden_actions: list[str] = Field(default_factory=list)
    deadlines: dict[str, float] = Field(
        default_factory=dict,
        description="action_id -> deadline in minutes",
    )
    required_prior_actions: dict[str, list[str]] = Field(default_factory=dict)


class ActionEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    timestamp: float = Field(..., description="Epoch seconds")
    action_id: str
    normalized_action_id: str | None = None
    tool_call: str | None = None
    observation: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ViolationRecord(BaseModel):
    violation_type: ViolationType
    action_id: str
    timestamp: float | None = None
    severity: int = Field(1, ge=1, le=5)
    source_guideline: str = ""
    source_section: str = ""
    source_page: str = ""
    source_quote: str = ""


class ScoreReport(BaseModel):
    final_score: float = Field(..., ge=0.0, le=1.0)
    action_coverage: float = Field(..., ge=0.0, le=1.0, description="Track A")
    compliance_score: float = Field(..., ge=0.0, le=1.0, description="Track B")
    peak_risk: float = Field(..., ge=0.0)
    aggregate_risk: float = Field(..., ge=0.0)
    violations_by_type: dict[str, int] = Field(default_factory=dict)
    sub_scores: dict[str, float] = Field(default_factory=dict, description="C1~C5")
    safety_gate: bool = True


class EpisodeLog(BaseModel):
    episode_id: str
    events: list[ActionEvent] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExternalParseResult(BaseModel):
    source_benchmark: str
    parsed_scenario: dict[str, Any] = Field(default_factory=dict)
    parsed_episode_log: EpisodeLog | None = None
    domain: str = ""
    parse_warnings: list[str] = Field(default_factory=list)


class ExperimentConfig(BaseModel):
    experiment_name: str
    scenarios: list[str] = Field(default_factory=list)
    agents: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    num_runs: int = Field(1, ge=1)
    seed: int | None = None


__all__ = [
    "ConstraintOutput",
    "ActionEvent",
    "ViolationType",
    "ViolationRecord",
    "ScoreReport",
    "EpisodeLog",
    "ExternalParseResult",
    "ExperimentConfig",
]
