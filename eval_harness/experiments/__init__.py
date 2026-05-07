"""
Evaluation Science Experiments for CGA-Bench

Experiment A: Outcome-Preserving Perturbation
Experiment B: Clinician Pairwise Preference Protocol
Experiment C: Disagreement Audit (4-Quadrant)
Experiment D: Evaluator Actionability
"""

from cga_bench.eval_harness.experiments.perturbation import (
    EpisodePerturbator,
    PerturbationType,
    PerturbationResult,
    TaskCompletionMetric,
    PerturbationExperiment,
)
from cga_bench.eval_harness.experiments.disagreement_audit import (
    Quadrant,
    FailureMode,
    QuadrantResult,
    DisagreementAudit,
)
from cga_bench.eval_harness.experiments.actionability import (
    PromptPatchType,
    ActionabilityResult,
    ActionabilityExperiment,
)
from cga_bench.eval_harness.experiments.clinician_protocol import (
    TracePair,
    ClinicianProtocolDesigner,
)

__all__ = [
    # Experiment A
    "EpisodePerturbator",
    "PerturbationType",
    "PerturbationResult",
    "TaskCompletionMetric",
    "PerturbationExperiment",
    # Experiment C
    "Quadrant",
    "FailureMode",
    "QuadrantResult",
    "DisagreementAudit",
    # Experiment D
    "PromptPatchType",
    "ActionabilityResult",
    "ActionabilityExperiment",
    # Experiment B
    "TracePair",
    "ClinicianProtocolDesigner",
]
