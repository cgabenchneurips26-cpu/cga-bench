"""External benchmark models - universal pipeline types.

Backward-compatible: keeps EpisodeEvidence, NormalizedEpisode, EvaluableComplianceReport.
New: CanonicalCase, TaskType, EvalMode (expanded), SubScoreMask, ExpectedAction (enhanced).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Literal, Optional, Set

from cga_bench.cpg_model.schemas.base import PatientState


# --- New: Task & Eval classification ------------------------------------------

class TaskType(str, Enum):
    """External benchmark task type."""

    OPEN_QA = "open_qa"
    MCQ_PATH = "mcq_path"
    MULTILABEL_ACTION = "multilabel_action"
    STRUCTURED_EHR = "structured_ehr"
    LONGITUDINAL_TEXT = "longitudinal_text"
    MULTIMODAL_LONGITUDINAL = "multimodal_longitudinal"
    TRIPLET_QA = "triplet_qa"


class EvalMode(str, Enum):
    """How CGA-Bench evaluates this dataset. 4-mode classification."""

    DIRECT_TRACK_B = "direct_track_b"
    DERIVED_TRACK_B = "derived_track_b"
    TRACK_A_ONLY = "track_a_only"
    SAFETY_ONLY = "safety_only"


class CriterionKind(str, Enum):
    """Classification of evaluation criteria."""

    ACTION = "action"
    ASSESSMENT = "assessment"
    EXPLANATION = "explanation"


@dataclass
class SubScoreMask:
    """C1-C5 masking per dataset - only assess what data supports.

    True = compute this sub-score, False = mark as not_assessed.
    """

    c1_path_selection: bool = True
    c2_mandatory_completion: bool = True
    c3_forbidden_avoidance: bool = True
    c4_timing_compliance: bool = False
    c5_sequence_integrity: bool = False


@dataclass
class ExpectedAction:
    """Expected action from external benchmark."""

    action_id: str
    kind: str = "mandatory"
    deadline_min: Optional[int] = None
    required_before: Optional[List[str]] = None
    confidence: float = 1.0
    provenance: str = ""


@dataclass
class DatasetManifest:
    """Dataset version pinning for reproducibility."""

    dataset_id: str
    dataset_name: str
    version: str = ""
    commit_hash: str = ""
    artifact_url: str = ""
    license: str = ""
    access_level: str = "public"
    task_type: TaskType = TaskType.OPEN_QA
    eval_mode: EvalMode = EvalMode.TRACK_A_ONLY
    sub_score_mask: SubScoreMask = field(default_factory=SubScoreMask)
    domain_hint: Optional[str] = None
    notes: List[str] = field(default_factory=list)


@dataclass
class CanonicalCase:
    """Universal intermediate representation for any external benchmark.

    4-stage pipeline: raw -> CanonicalCase -> ExpectedAction[] -> episode_log
    """

    case_id: str
    dataset_id: str
    split: str = ""
    task_type: TaskType = TaskType.OPEN_QA
    eval_mode: EvalMode = EvalMode.TRACK_A_ONLY
    domain: Optional[str] = None
    input_text: Optional[str] = None
    structured_fields: Dict[str, Any] = field(default_factory=dict)
    timeline_events: List[Dict[str, Any]] = field(default_factory=list)
    options: Optional[List[str]] = None
    gold_answer: Any = None
    gold_path: Optional[List[str]] = None
    checklist: Optional[List[str]] = None
    provenance: Dict[str, Any] = field(default_factory=dict)
    sub_score_mask: SubScoreMask = field(default_factory=SubScoreMask)


@dataclass
class ExternalPipelineConfig:
    """Top-level config for the external benchmark pipeline.

    Allows loading manifests from YAML instead of hardcoding in Python.
    Follows project principle: all config via *Config dataclasses, no hardcoded defaults.
    """

    manifests: Dict[str, DatasetManifest] = field(default_factory=dict)
    default_eval_mode: EvalMode = EvalMode.TRACK_A_ONLY
    default_access_level: str = "public"

    @classmethod
    def from_yaml(cls, path: str) -> "ExternalPipelineConfig":
        """Load pipeline config from YAML file."""
        import yaml
        from pathlib import Path

        data = yaml.safe_load(Path(path).read_text())
        manifests: Dict[str, DatasetManifest] = {}

        for dataset_id, cfg in data.get("datasets", {}).items():
            mask_cfg = cfg.get("sub_score_mask", {})
            mask = SubScoreMask(
                c1_path_selection=mask_cfg.get("c1", True),
                c2_mandatory_completion=mask_cfg.get("c2", True),
                c3_forbidden_avoidance=mask_cfg.get("c3", False),
                c4_timing_compliance=mask_cfg.get("c4", False),
                c5_sequence_integrity=mask_cfg.get("c5", False),
            )
            manifests[dataset_id] = DatasetManifest(
                dataset_id=dataset_id,
                dataset_name=cfg.get("name", dataset_id),
                version=cfg.get("version", ""),
                commit_hash=cfg.get("commit_hash", ""),
                artifact_url=cfg.get("artifact_url", ""),
                license=cfg.get("license", ""),
                access_level=cfg.get("access_level", "public"),
                task_type=TaskType(cfg.get("task_type", "open_qa")),
                eval_mode=EvalMode(cfg.get("eval_mode", "track_a_only")),
                sub_score_mask=mask,
                domain_hint=cfg.get("domain_hint"),
                notes=cfg.get("notes", []),
            )

        return cls(
            manifests=manifests,
            default_eval_mode=EvalMode(data.get("default_eval_mode", "track_a_only")),
            default_access_level=data.get("default_access_level", "public"),
        )


# --- Backward-compatible existing types (DO NOT MODIFY) -----------------------


@dataclass
class EpisodeEvidence:
    has_vitals: bool
    has_test_results: bool
    has_imaging_results: bool
    has_medications: bool
    has_physical_exam: bool
    has_history: bool
    has_diagnosis: bool
    has_timestamps: bool
    action_catalog: Set[str] = field(default_factory=set)
    notes: List[str] = field(default_factory=list)


@dataclass
class NormalizedEpisode:
    case_id: str
    source_benchmark: str
    patient_state: PatientState
    actions: List[str]
    evidence: EpisodeEvidence
    guideline_id: Optional[str] = None
    required_actions: Optional[List[str]] = None
    warnings: List[str] = field(default_factory=list)
    # Terminology grounding (P0) - Optional for backward compatibility
    grounded_labs: Optional[List[Any]] = None       # List[GroundedLabResult]
    grounded_diagnoses: Optional[List[Any]] = None  # List[CodedConcept]
    grounded_medications: Optional[List[Any]] = None  # List[MedicationCoding]


@dataclass
class EvaluableComplianceReport:
    case_id: str
    guideline_id: Optional[str]
    mandatory_actions: List[str]
    performed_actions: List[str]
    evaluable_actions: List[str]
    not_observable_actions: List[str]
    satisfied_actions: List[str]
    violations: List[Dict[str, Any]]
    observability_index: float
    compliance_score: float
    evidence_summary: Dict[str, Any]
    required_actions: Optional[List[str]] = None
    required_satisfied_actions: Optional[List[str]] = None
    required_compliance_score: Optional[float] = None
    forbidden_actions: Optional[List[str]] = None
    required_prior_actions: Optional[Dict[str, List[str]]] = None
    deadlines: Optional[Dict[str, float]] = None
    notes: List[str] = field(default_factory=list)
