"""
Conformance schemas for Hard Graph + Soft Constraints evaluation.
"""
from __future__ import annotations

from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field, ConfigDict


class ConstraintTemplate(str, Enum):
    EXISTENCE = "existence"
    RESPONSE = "response"
    RESPONSE_WITHIN = "response_within"
    PRECEDENCE = "precedence"
    NOT_SUCCESSION = "not_succession"
    NOT_COEXISTENCE = "not_coexistence"


class HardPhase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    phase_id: str = Field(..., description="Phase identifier")
    name: str = Field(..., description="Phase display name")
    description: Optional[str] = None


class HardGraph(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpg_id: str
    phases: List[HardPhase]
    edges: List[List[str]] = Field(default_factory=list, description="Ordered edges [from, to]")
    required_phases: List[str] = Field(default_factory=list)
    phase_map: Dict[str, str] = Field(
        default_factory=dict,
        description="Map activity name to phase_id",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)


class DerivedFlagSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    flag_id: str
    source: str = Field(
        "result",
        description="request|result|missing for intent/result/absence signals",
    )
    resource_type: str
    code: Optional[str] = None
    op: str = Field(..., description="Comparison operator: >, >=, <, <=, ==, exists")
    value: Optional[float] = None


class SoftConstraint(BaseModel):
    model_config = ConfigDict(extra="forbid")

    constraint_id: str
    template: ConstraintTemplate
    channel: str = Field(
        "req",
        description="req|res channel for procedural vs evidential compliance",
    )
    A: Optional[str] = None
    B: Optional[str] = None
    window_minutes: Optional[float] = None
    weight: float = 1.0
    guard: Optional[str] = None
    rationale: Optional[str] = None
    description: Optional[str] = None
    evidence_level: Optional[str] = Field(
        None, description="Guideline evidence level (1A, 1B, 2A, 2B, 2C, 3)"
    )


class ErrorPenaltyConfig(BaseModel):
    """Configuration for error penalty classification.

    Specifies which ErrorCategory values are penalized vs exempt.
    When not provided, all errors are penalized (backward-compatible).
    """
    model_config = ConfigDict(extra="forbid")

    penalized_categories: List[str] = Field(
        default_factory=lambda: ["invalid", "unknown"],
        description="ErrorCategory values that incur penalty",
    )
    exempt_categories: List[str] = Field(
        default_factory=lambda: ["auth", "not_found", "rate_limit", "server_error", "timeout"],
        description="ErrorCategory values exempt from penalty (environment constraints)",
    )


class SoftConstraints(BaseModel):
    model_config = ConfigDict(extra="forbid")

    cpg_id: str
    constraints: List[SoftConstraint]
    derived_flags: List[DerivedFlagSpec] = Field(default_factory=list)
    error_weight: float = Field(1.0, description="Penalty weight per error flag")
    error_penalty_config: Optional[ErrorPenaltyConfig] = Field(
        default=None,
        description="Error penalty configuration for environment constraint exemption",
    )
    negative_controls: List[str] = Field(
        default_factory=list,
        description="Flags that should never appear for this CPG",
    )
    activity_aliases: Dict[str, str] = Field(
        default_factory=dict,
        description="Rename activity -> canonical activity",
    )
    metadata: Dict[str, Any] = Field(default_factory=dict)
