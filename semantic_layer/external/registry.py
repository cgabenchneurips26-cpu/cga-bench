"""Dataset registry - manifests and config for all 8 external benchmarks.

Each manifest defines: dataset_id, task_type, eval_mode, sub_score_mask, access_level.
The pipeline.process_case() uses these to route parsing/evaluation.

Supports two modes:
1. Hardcoded defaults (below) — always available.
2. YAML override via load_from_yaml() — for custom configs without code changes.
"""

from .models import DatasetManifest, EvalMode, ExternalPipelineConfig, SubScoreMask, TaskType


AMEGA = DatasetManifest(
    dataset_id="amega",
    dataset_name="AMEGA",
    license="evaluation-only",
    access_level="public",
    task_type=TaskType.OPEN_QA,
    eval_mode=EvalMode.DERIVED_TRACK_B,
    sub_score_mask=SubScoreMask(
        c1_path_selection=True,
        c2_mandatory_completion=True,
        c3_forbidden_avoidance=True,
        c4_timing_compliance=False,
        c5_sequence_integrity=False,
    ),
    notes=[
        "Question-level granularity",
        "Criteria: action/assessment/explanation",
        "Pin specific artifact/commit",
    ],
)

CLIBENCH = DatasetManifest(
    dataset_id="clibench",
    dataset_name="CliBench",
    license="PhysioNet Credentialed Health Data License",
    access_level="credentialed",
    task_type=TaskType.MULTILABEL_ACTION,
    eval_mode=EvalMode.DERIVED_TRACK_B,
    sub_score_mask=SubScoreMask(
        c1_path_selection=True,
        c2_mandatory_completion=True,
        c3_forbidden_avoidance=False,
        c4_timing_compliance=False,
        c5_sequence_integrity=False,
    ),
    domain_hint=None,
    notes=[
        "MIMIC-IV derived",
        "Local inference only",
        "Namespace: dx/proc/lab/med",
        "Diagnosis tasks: lower confidence",
    ],
)

MEDGUIDE = DatasetManifest(
    dataset_id="medguide",
    dataset_name="MedGUIDE",
    license="Check NCCN permission for verbatim text",
    access_level="public",
    task_type=TaskType.MCQ_PATH,
    eval_mode=EvalMode.DERIVED_TRACK_B,
    sub_score_mask=SubScoreMask(
        c1_path_selection=True,
        c2_mandatory_completion=True,
        c3_forbidden_avoidance=False,
        c4_timing_compliance=False,
        c5_sequence_integrity=False,
    ),
    domain_hint="oncology",
    notes=[
        "55 NCCN decision trees",
        "17 cancer types",
        "7747 samples",
        "No verbatim guideline text",
    ],
)

CANCERGUIDE = DatasetManifest(
    dataset_id="cancerguide",
    dataset_name="CancerGUIDE",
    license="HF synthetic: open, Expert longitudinal: restricted",
    access_level="public",
    task_type=TaskType.LONGITUDINAL_TEXT,
    eval_mode=EvalMode.TRACK_A_ONLY,
    sub_score_mask=SubScoreMask(
        c1_path_selection=True,
        c2_mandatory_completion=True,
        c3_forbidden_avoidance=False,
        c4_timing_compliance=False,
        c5_sequence_integrity=False,
    ),
    domain_hint="oncology",
    notes=[
        "HF synthetic: 165+151 rows",
        "Expert longitudinal: 121 cases (restricted)",
        "Use synthetic for smoke-test only",
    ],
)

MTBBENCH = DatasetManifest(
    dataset_id="mtbbench",
    dataset_name="MTBBench",
    license="Research use",
    access_level="credentialed",
    task_type=TaskType.MULTIMODAL_LONGITUDINAL,
    eval_mode=EvalMode.TRACK_A_ONLY,
    sub_score_mask=SubScoreMask(
        c1_path_selection=True,
        c2_mandatory_completion=True,
        c3_forbidden_avoidance=False,
        c4_timing_compliance=False,
        c5_sequence_integrity=False,
    ),
    domain_hint="oncology",
    notes=[
        "1012 rows",
        "Requires pathology/genomics/drug tools",
        "Most complex - implement last",
    ],
)

EHRSTRUCT = DatasetManifest(
    dataset_id="ehrstruct",
    dataset_name="EHRStruct",
    license="CC BY-NC 4.0",
    access_level="public",
    task_type=TaskType.STRUCTURED_EHR,
    eval_mode=EvalMode.SAFETY_ONLY,
    sub_score_mask=SubScoreMask(
        c1_path_selection=False,
        c2_mandatory_completion=False,
        c3_forbidden_avoidance=False,
        c4_timing_compliance=False,
        c5_sequence_integrity=False,
    ),
    notes=[
        "Input-generalization test, NOT CPG adherence",
        "Synthea=open, eICU=credentialed",
        "Use as parser/extractor robustness suite",
    ],
)

LLMEVAL_MED = DatasetManifest(
    dataset_id="llmeval_med",
    dataset_name="LLMEval-Med",
    license="Research use",
    access_level="public",
    task_type=TaskType.OPEN_QA,
    eval_mode=EvalMode.TRACK_A_ONLY,
    sub_score_mask=SubScoreMask(
        c1_path_selection=False,
        c2_mandatory_completion=True,
        c3_forbidden_avoidance=True,
        c4_timing_compliance=False,
        c5_sequence_integrity=False,
    ),
    notes=[
        "667 questions (public)",
        "Clinical scene subset only",
        "Checklist clause->action/safety classification",
    ],
)

NICE = DatasetManifest(
    dataset_id="nice",
    dataset_name="NICE Silver-Standard",
    license="UK Open Content Licence (domestic); fee-based (international)",
    access_level="public",
    task_type=TaskType.TRIPLET_QA,
    eval_mode=EvalMode.DERIVED_TRACK_B,
    sub_score_mask=SubScoreMask(
        c1_path_selection=True,
        c2_mandatory_completion=True,
        c3_forbidden_avoidance=False,
        c4_timing_compliance=False,
        c5_sequence_integrity=False,
    ),
    notes=[
        "Silver label: confidence<1.0",
        "Good for graph expansion benchmark",
        "Schema introspection on first import",
    ],
)


HEALTHBENCH = DatasetManifest(
    dataset_id="healthbench",
    dataset_name="OpenAI HealthBench",
    version="2025-05-07",
    license="MIT",
    access_level="public",
    task_type=TaskType.OPEN_QA,
    eval_mode=EvalMode.DERIVED_TRACK_B,
    sub_score_mask=SubScoreMask(
        c1_path_selection=True,
        c2_mandatory_completion=True,
        c3_forbidden_avoidance=True,
        c4_timing_compliance=False,
        c5_sequence_integrity=False,
    ),
    notes=[
        "5000 eval + 3671 consensus + 1000 hard",
        "Rubric points: positive=mandatory, negative=forbidden",
        "Physician-graded criteria with weighted scoring",
        "57237 total rubric criteria across eval split",
    ],
)

ART = DatasetManifest(
    dataset_id="art",
    dataset_name="ART (Action-based Reasoning clinical Task)",
    version="",
    artifact_url="https://arxiv.org/abs/2601.08988",
    license="unknown - data not yet publicly released",
    access_level="public",
    task_type=TaskType.STRUCTURED_EHR,
    eval_mode=EvalMode.DERIVED_TRACK_B,
    sub_score_mask=SubScoreMask(
        c1_path_selection=True,
        c2_mandatory_completion=True,
        c3_forbidden_avoidance=True,
        c4_timing_compliance=False,
        c5_sequence_integrity=False,
    ),
    notes=[
        "Paper: arxiv 2601.08988",
        "Task types: threshold_evaluation, temporal_aggregation, conditional_logic",
        "Mines real-world EHR data for action-based reasoning tasks",
        "Data NOT yet publicly released as of 2026-03-26",
        "Synthetic 5-case sample at data/external_benchmarks/art/synthetic_sample.json",
    ],
)

AGENTEHR = DatasetManifest(
    dataset_id="agentehr",
    dataset_name="AgentEHR",
    version="",
    artifact_url="https://huggingface.co/datasets/BlueZeros/AgentEHR-Bench",
    license="Apache 2.0",
    access_level="public",
    task_type=TaskType.MULTILABEL_ACTION,
    eval_mode=EvalMode.DERIVED_TRACK_B,
    sub_score_mask=SubScoreMask(
        c1_path_selection=True,
        c2_mandatory_completion=True,
        c3_forbidden_avoidance=False,
        c4_timing_compliance=False,
        c5_sequence_integrity=False,
    ),
    notes=[
        "Paper: arxiv 2601.13918",
        "HuggingFace: BlueZeros/AgentEHR-Bench",
        "MIMIC-III and MIMIC-IV derived (requires PhysioNet credentialing for full data)",
        "Tasks: diagnoses_ccs, labevents, microbiologyevents, prescriptions, procedures, transfers",
        "Sample data at data/external_benchmarks/agentehr/",
        "Each case: subject_id, hadm_id, prediction_time, task, label (list of target items)",
    ],
)

MIMIC_SEPSIS = DatasetManifest(
    dataset_id="mimic_sepsis",
    dataset_name="MIMIC-IV Sepsis-3 Cohort",
    license="PhysioNet Credentialed Health Data License v1.5",
    access_level="credentialed",
    task_type=TaskType.STRUCTURED_EHR,
    eval_mode=EvalMode.DIRECT_TRACK_B,
    sub_score_mask=SubScoreMask(
        c1_path_selection=True,
        c2_mandatory_completion=True,
        c3_forbidden_avoidance=True,
        c4_timing_compliance=True,    # MIMIC has minute-grade timestamps
        c5_sequence_integrity=True,   # blood-culture-before-antibiotic verifiable
    ),
    domain_hint="sepsis",
    notes=[
        "Real-patient ICU sepsis cohort from MIMIC-IV v3.1",
        "Sepsis-3 inclusion: ICD-10 A41.*/R65.2*; ICD-9 995.91/92, 785.52",
        "PhysioNet credentialing + DUA + CITI training required",
        "Scored by ssc_sepsis_hour1_bundle.yaml (SSC 2021 Hour-1 Bundle)",
        "Patient state from chartevents/labevents/microbiologyevents at t0",
        "Native score: 5/5 hour-1 bundle compliance (antibiotic within 60 min,"
        " lactate within 60 min, blood culture before antibiotic, fluid 30 ml/kg"
        " for septic shock, vasopressor for MAP<65 within 60 min)",
        "Reference: arXiv:2510.24500 (35,239-patient cohort), and full v3.1",
    ],
)

REGISTRY: dict[str, DatasetManifest] = {
    m.dataset_id: m
    for m in [AMEGA, CLIBENCH, MEDGUIDE, CANCERGUIDE, MTBBENCH, EHRSTRUCT,
              LLMEVAL_MED, NICE, HEALTHBENCH, ART, AGENTEHR, MIMIC_SEPSIS]
}


def get_manifest(dataset_id: str) -> DatasetManifest:
    """Get manifest by dataset_id. Raises KeyError if not found."""
    dataset_id_lower = dataset_id.lower()
    if dataset_id_lower in REGISTRY:
        return REGISTRY[dataset_id_lower]
    raise KeyError(f"Unknown dataset: {dataset_id}. Available: {list(REGISTRY.keys())}")


def list_datasets() -> list[str]:
    return list(REGISTRY.keys())


def load_from_yaml(path: str) -> ExternalPipelineConfig:
    config = ExternalPipelineConfig.from_yaml(path)
    return config


def override_registry(config: ExternalPipelineConfig) -> None:
    for dataset_id, manifest in config.manifests.items():
        REGISTRY[dataset_id] = manifest
