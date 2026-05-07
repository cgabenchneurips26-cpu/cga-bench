import logging
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Set

from cga_bench.cpg_engine.engine import CPGEngineFactory
from cga_bench.cpg_model.schemas.base import PatientState, VitalSigns
from cga_bench.env.adapters.agentclinic_adapter import AgentClinicAdapter
from .agentclinic import (
    normalize_action_id,
    normalize_agentclinic_case,
)
from .models import EvaluableComplianceReport
from .medchain import normalize_medchain_case
from cga_bench.env.adapters.medchain_adapter import MedChainAdapter

logger = logging.getLogger(__name__)

# Guideline path → ontology domain mapping
_GUIDELINE_DOMAIN_MAP: Dict[str, str] = {
    "ssc_sepsis": "sepsis",
    "sepsis": "sepsis",
    "aha_chest_pain": "chest_pain",
    "chest_pain": "chest_pain",
    "aha_stroke": "stroke",
    "stroke": "stroke",
    "aha_heart_failure": "heart_failure",
    "heart_failure": "heart_failure",
    "kdigo_aki": "aki",
    "aki": "aki",
    "ada_dka": "dka",
    "dka": "dka",
}


def _get_ontology_matcher_for_guideline(guideline_id: Optional[str]):
    """Get an OntologyMatcher based on the guideline file path.

    Returns None if ontology is unavailable or domain is unrecognized.
    """
    if not guideline_id:
        return None

    try:
        from ..ontology.domain_hierarchies import (
            get_ontology_matcher,
            get_unified_matcher,
        )
    except ImportError:
        return None

    # Extract domain from guideline path
    stem = Path(guideline_id).stem.lower()
    for key, domain in _GUIDELINE_DOMAIN_MAP.items():
        if key in stem:
            try:
                return get_ontology_matcher(domain)
            except Exception:
                pass

    # Fallback to unified matcher
    try:
        return get_unified_matcher()
    except Exception:
        return None


def _action_satisfies_via_ontology(
    performed_actions: Set[str],
    requirement: str,
    ontology_matcher,
) -> bool:
    """Check if any performed action satisfies a requirement via ontology subsumption.

    Args:
        performed_actions: Set of performed action IDs (normalized)
        requirement: The mandatory/prior action requirement to check
        ontology_matcher: OntologyMatcher instance

    Returns:
        True if any performed action subsumes or equals the requirement
    """
    if ontology_matcher is None:
        return False

    for action in performed_actions:
        if ontology_matcher.satisfies(action, requirement):
            return True
    return False


def _action_is_forbidden_via_ontology(
    action: str,
    forbidden_actions: List[str],
    ontology_matcher,
) -> bool:
    """Check if an action is forbidden via ontology subsumption.

    Args:
        action: The performed action to check
        forbidden_actions: List of forbidden action IDs
        ontology_matcher: OntologyMatcher instance

    Returns:
        True if the action is a descendant of any forbidden action
    """
    if ontology_matcher is None:
        return False

    forbidden_set = set(forbidden_actions)
    return ontology_matcher.is_forbidden(action, forbidden_set)


def _action_category(action_id: str) -> Optional[str]:
    action = normalize_action_id(action_id)
    if "vital" in action:
        return "vitals"
    if action.startswith("order_lab") or "lab" in action or action in ["cbc", "cmp", "bmp"]:
        return "labs"
    if action.startswith("order_imaging") or any(tag in action for tag in ["imaging", "xray", "ct", "mri", "ultrasound", "ecg", "ekg", "echo"]):
        return "imaging"
    if action.startswith(("give_", "administer_")) or "medication" in action or "antibiotic" in action:
        return "medications"
    if "exam" in action:
        return "exam"
    if "history" in action or "chief_complaint" in action:
        return "history"
    if "diagnos" in action:
        return "diagnosis"
    return None


def _required_evidence(action_id: str) -> List[str]:
    category = _action_category(action_id)
    if not category:
        return []
    return [category]


def _is_action_observable(action_id: str, evidence_flags: Dict[str, bool]) -> bool:
    required = _required_evidence(action_id)
    if not required:
        return True
    return all(evidence_flags.get(flag, False) for flag in required)


def _evidence_summary(evidence_flags: Dict[str, bool], performed_count: int) -> Dict[str, Any]:
    return {
        "performed_action_count": performed_count,
        "evidence": evidence_flags,
    }


def _evidence_flags_from_episode(episode: Dict[str, Any]) -> Dict[str, bool]:
    evidence = episode.get("evidence", {})
    return {
        "vitals": bool(evidence.get("has_vitals")),
        "labs": bool(evidence.get("has_test_results")),
        "imaging": bool(evidence.get("has_imaging_results")),
        "medications": bool(evidence.get("has_medications")),
        "exam": bool(evidence.get("has_physical_exam")),
        "history": bool(evidence.get("has_history")),
        "diagnosis": bool(evidence.get("has_diagnosis")),
        "timestamps": bool(evidence.get("has_timestamps")),
    }


def _evaluate_compliance(
    case_id: str,
    guideline_id: Optional[str],
    performed_actions: List[str],
    performed_norm: Set[str],
    mandatory_actions: List[str],
    forbidden_actions: List[str],
    required_prior_actions: Dict[str, List[str]],
    deadlines: Dict[str, Any],
    evidence_flags: Dict[str, bool],
    ontology_matcher=None,
    notes: Optional[List[str]] = None,
    required_actions: Optional[List[str]] = None,
) -> EvaluableComplianceReport:
    """Shared compliance evaluation logic with optional ontology matching.

    When ontology_matcher is provided, subsumption-based matching is used
    as a fallback for string-based matching. This allows, e.g.,
    'give_meropenem' to satisfy 'give_broad_spectrum_antibiotics'.
    """
    evaluable_actions: List[str] = []
    not_observable_actions: List[str] = []
    satisfied_actions: List[str] = []
    violations: List[Dict[str, Any]] = []

    for mandatory in mandatory_actions:
        observable = _is_action_observable(mandatory, evidence_flags)
        if not observable:
            not_observable_actions.append(mandatory)
            continue

        evaluable_actions.append(mandatory)
        if normalize_action_id(mandatory) in performed_norm:
            satisfied_actions.append(mandatory)
        elif _action_satisfies_via_ontology(performed_norm, mandatory, ontology_matcher):
            satisfied_actions.append(mandatory)
        else:
            violations.append(
                {
                    "type": "OMISSION",
                    "action": mandatory,
                    "description": f"evaluable_mandatory_missing:{mandatory}",
                }
            )

    for forbidden in forbidden_actions:
        if normalize_action_id(forbidden) in performed_norm:
            violations.append(
                {
                    "type": "COMMISSION",
                    "action": forbidden,
                    "description": f"forbidden_action_performed:{forbidden}",
                }
            )
        elif ontology_matcher:
            # Check if any performed action is a descendant of forbidden
            for action in performed_norm:
                if _action_is_forbidden_via_ontology(action, [forbidden], ontology_matcher):
                    violations.append(
                        {
                            "type": "COMMISSION",
                            "action": action,
                            "description": f"ontology_forbidden:{forbidden}→{action}",
                        }
                    )
                    break

    for action, priors in required_prior_actions.items():
        action_norm = normalize_action_id(action)
        action_performed = (
            action_norm in performed_norm or
            (ontology_matcher is not None and
             _action_satisfies_via_ontology(performed_norm, action, ontology_matcher))
        )
        if action_performed:
            missing_priors = []
            for prior in priors:
                prior_satisfied = (
                    normalize_action_id(prior) in performed_norm or
                    (ontology_matcher is not None and
                     _action_satisfies_via_ontology(performed_norm, prior, ontology_matcher))
                )
                if not prior_satisfied:
                    missing_priors.append(prior)
            if missing_priors:
                violations.append(
                    {
                        "type": "SEQUENCE",
                        "action": action,
                        "description": f"missing_required_priors:{','.join(missing_priors)}",
                    }
                )

    observability_index = (
        len(evaluable_actions) / len(mandatory_actions) if mandatory_actions else 1.0
    )
    compliance_score = (
        len(satisfied_actions) / len(evaluable_actions) if evaluable_actions else 0.0
    )

    if notes is None:
        notes = []
    if deadlines and not evidence_flags.get("timestamps"):
        notes.append("timing_not_evaluable")
    if ontology_matcher is not None:
        notes.append("ontology_matching_enabled")

    return EvaluableComplianceReport(
        case_id=case_id,
        guideline_id=guideline_id,
        mandatory_actions=mandatory_actions,
        performed_actions=performed_actions,
        required_actions=required_actions,
        evaluable_actions=evaluable_actions,
        not_observable_actions=not_observable_actions,
        satisfied_actions=satisfied_actions,
        required_satisfied_actions=None,
        violations=violations,
        observability_index=observability_index,
        compliance_score=compliance_score,
        required_compliance_score=None,
        forbidden_actions=forbidden_actions,
        required_prior_actions=required_prior_actions,
        deadlines=deadlines,
        evidence_summary=_evidence_summary(evidence_flags, len(performed_actions)),
        notes=notes,
    )


def evaluate_agentclinic_case(
    case: Dict[str, Any],
    adapter: AgentClinicAdapter,
    project_root: Path,
    enable_ontology: bool = False,
) -> EvaluableComplianceReport:
    normalized = normalize_agentclinic_case(case)

    _, guideline_path = adapter.load_case(case)
    guideline_id = guideline_path or None

    evidence_flags = {
        "vitals": normalized.evidence.has_vitals,
        "labs": normalized.evidence.has_test_results,
        "imaging": normalized.evidence.has_imaging_results,
        "medications": normalized.evidence.has_medications,
        "exam": normalized.evidence.has_physical_exam,
        "history": normalized.evidence.has_history,
        "diagnosis": normalized.evidence.has_diagnosis,
        "timestamps": normalized.evidence.has_timestamps,
    }

    performed_actions = sorted(set(normalized.actions))
    performed_norm = {normalize_action_id(action) for action in performed_actions}

    if not guideline_id:
        return EvaluableComplianceReport(
            case_id=normalized.case_id,
            guideline_id=None,
            mandatory_actions=[],
            performed_actions=performed_actions,
            evaluable_actions=[],
            not_observable_actions=[],
            satisfied_actions=[],
            violations=[],
            observability_index=0.0,
            compliance_score=0.0,
            evidence_summary=_evidence_summary(evidence_flags, len(performed_actions)),
            notes=["no_guideline_mapping"],
        )

    guideline_path = project_root / guideline_id
    if not guideline_path.exists():
        return EvaluableComplianceReport(
            case_id=normalized.case_id,
            guideline_id=guideline_id,
            mandatory_actions=[],
            performed_actions=performed_actions,
            evaluable_actions=[],
            not_observable_actions=[],
            satisfied_actions=[],
            violations=[],
            observability_index=0.0,
            compliance_score=0.0,
            evidence_summary=_evidence_summary(evidence_flags, len(performed_actions)),
            notes=[f"missing_guideline_file:{guideline_id}"],
        )

    try:
        engine = CPGEngineFactory.load_from_file(str(guideline_path))
    except Exception as exc:
        return EvaluableComplianceReport(
            case_id=normalized.case_id,
            guideline_id=guideline_id,
            mandatory_actions=[],
            performed_actions=performed_actions,
            evaluable_actions=[],
            not_observable_actions=[],
            satisfied_actions=[],
            violations=[],
            observability_index=0.0,
            compliance_score=0.0,
            evidence_summary=_evidence_summary(evidence_flags, len(performed_actions)),
            notes=[f"guideline_load_error:{type(exc).__name__}"],
        )

    constraints = engine.evaluate(normalized.patient_state)
    mandatory_actions = list(constraints.mandatory_actions)
    forbidden_actions = list(constraints.forbidden_actions)
    required_prior_actions = constraints.required_prior_actions
    deadlines = constraints.deadlines

    # Initialize ontology matcher if enabled
    ontology_matcher = (
        _get_ontology_matcher_for_guideline(guideline_id)
        if enable_ontology else None
    )

    report = _evaluate_compliance(
        case_id=normalized.case_id,
        guideline_id=guideline_id,
        performed_actions=performed_actions,
        performed_norm=performed_norm,
        mandatory_actions=mandatory_actions,
        forbidden_actions=forbidden_actions,
        required_prior_actions=required_prior_actions,
        deadlines=deadlines,
        evidence_flags=evidence_flags,
        ontology_matcher=ontology_matcher,
        notes=list(normalized.warnings) if normalized.warnings else [],
    )
    return report


def evaluate_agentclinic_cases(
    cases: Iterable[Dict[str, Any]],
    adapter: AgentClinicAdapter,
    project_root: Path,
    enable_ontology: bool = False,
) -> List[EvaluableComplianceReport]:
    return [
        evaluate_agentclinic_case(case, adapter, project_root, enable_ontology=enable_ontology)
        for case in cases
    ]


def evaluate_medchain_case(
    case_id: str,
    case: Dict[str, Any],
    project_root: Path,
    enable_ontology: bool = False,
) -> EvaluableComplianceReport:
    adapter = MedChainAdapter()
    normalized = normalize_medchain_case(case_id, case)

    guideline_id = normalized.guideline_id
    if not guideline_id:
        tags = case.get("tags", {})
        depts = tags.get("科室", []) if isinstance(tags, dict) else []
        primary = depts[0] if depts else None
        guideline_id = adapter.DEPARTMENT_GUIDELINE_MAPPING.get(primary) if primary else None

    evidence_flags = {
        "vitals": normalized.evidence.has_vitals,
        "labs": normalized.evidence.has_test_results,
        "imaging": normalized.evidence.has_imaging_results,
        "medications": normalized.evidence.has_medications,
        "exam": normalized.evidence.has_physical_exam,
        "history": normalized.evidence.has_history,
        "diagnosis": normalized.evidence.has_diagnosis,
        "timestamps": normalized.evidence.has_timestamps,
    }

    performed_actions = sorted(set(normalized.actions))
    performed_norm = {normalize_action_id(action) for action in performed_actions}

    if not guideline_id:
        return EvaluableComplianceReport(
            case_id=normalized.case_id,
            guideline_id=None,
            mandatory_actions=[],
            performed_actions=performed_actions,
            evaluable_actions=[],
            not_observable_actions=[],
            satisfied_actions=[],
            violations=[],
            observability_index=0.0,
            compliance_score=0.0,
            evidence_summary=_evidence_summary(evidence_flags, len(performed_actions)),
            notes=["no_guideline_mapping"],
        )

    guideline_path = project_root / guideline_id
    if not guideline_path.exists():
        return EvaluableComplianceReport(
            case_id=normalized.case_id,
            guideline_id=guideline_id,
            mandatory_actions=[],
            performed_actions=performed_actions,
            evaluable_actions=[],
            not_observable_actions=[],
            satisfied_actions=[],
            violations=[],
            observability_index=0.0,
            compliance_score=0.0,
            evidence_summary=_evidence_summary(evidence_flags, len(performed_actions)),
            notes=[f"missing_guideline_file:{guideline_id}"],
        )

    try:
        engine = CPGEngineFactory.load_from_file(str(guideline_path))
    except Exception as exc:
        return EvaluableComplianceReport(
            case_id=normalized.case_id,
            guideline_id=guideline_id,
            mandatory_actions=[],
            performed_actions=performed_actions,
            evaluable_actions=[],
            not_observable_actions=[],
            satisfied_actions=[],
            violations=[],
            observability_index=0.0,
            compliance_score=0.0,
            evidence_summary=_evidence_summary(evidence_flags, len(performed_actions)),
            notes=[f"guideline_load_error:{type(exc).__name__}"],
        )

    constraints = engine.evaluate(normalized.patient_state)
    mandatory_actions = list(constraints.mandatory_actions)
    forbidden_actions = list(constraints.forbidden_actions)
    required_prior_actions = constraints.required_prior_actions
    deadlines = constraints.deadlines

    ontology_matcher = (
        _get_ontology_matcher_for_guideline(guideline_id)
        if enable_ontology else None
    )

    return _evaluate_compliance(
        case_id=normalized.case_id,
        guideline_id=guideline_id,
        performed_actions=performed_actions,
        performed_norm=performed_norm,
        mandatory_actions=mandatory_actions,
        forbidden_actions=forbidden_actions,
        required_prior_actions=required_prior_actions,
        deadlines=deadlines,
        evidence_flags=evidence_flags,
        ontology_matcher=ontology_matcher,
        notes=list(normalized.warnings) if normalized.warnings else [],
    )


def evaluate_medchain_cases(
    cases: Dict[str, Any],
    project_root: Path,
    enable_ontology: bool = False,
) -> List[EvaluableComplianceReport]:
    return [
        evaluate_medchain_case(case_id, case, project_root, enable_ontology=enable_ontology)
        for case_id, case in cases.items()
    ]


def evaluate_normalized_episode(
    episode: Dict[str, Any],
    project_root: Path,
    enable_ontology: bool = False,
) -> EvaluableComplianceReport:
    case_id = episode.get("case_id", "unknown")
    guideline_id = episode.get("guideline_id")
    performed_actions = sorted(set(episode.get("actions", []) or []))
    performed_norm = {normalize_action_id(action) for action in performed_actions}
    evidence_flags = _evidence_flags_from_episode(episode)

    if not guideline_id:
        return EvaluableComplianceReport(
            case_id=case_id,
            guideline_id=None,
            mandatory_actions=[],
            performed_actions=performed_actions,
            evaluable_actions=[],
            not_observable_actions=[],
            satisfied_actions=[],
            violations=[],
            observability_index=0.0,
            compliance_score=0.0,
            evidence_summary=_evidence_summary(evidence_flags, len(performed_actions)),
            notes=["no_guideline_mapping"],
        )

    guideline_path = project_root / guideline_id
    if not guideline_path.exists():
        return EvaluableComplianceReport(
            case_id=case_id,
            guideline_id=guideline_id,
            mandatory_actions=[],
            performed_actions=performed_actions,
            evaluable_actions=[],
            not_observable_actions=[],
            satisfied_actions=[],
            violations=[],
            observability_index=0.0,
            compliance_score=0.0,
            evidence_summary=_evidence_summary(evidence_flags, len(performed_actions)),
            notes=[f"missing_guideline_file:{guideline_id}"],
        )

    try:
        engine = CPGEngineFactory.load_from_file(str(guideline_path))
    except Exception as exc:
        return EvaluableComplianceReport(
            case_id=case_id,
            guideline_id=guideline_id,
            mandatory_actions=[],
            performed_actions=performed_actions,
            evaluable_actions=[],
            not_observable_actions=[],
            satisfied_actions=[],
            violations=[],
            observability_index=0.0,
            compliance_score=0.0,
            evidence_summary=_evidence_summary(evidence_flags, len(performed_actions)),
            notes=[f"guideline_load_error:{type(exc).__name__}"],
        )

    patient_state = episode.get("patient_state")
    if isinstance(patient_state, dict):
        patient_state = PatientState.model_validate(patient_state)
    if patient_state is None:
        patient_state = PatientState(
            state_id=case_id,
            age=0,
            sex="U",
            vitals=VitalSigns(),
            chief_complaint="",
        )
    constraints = engine.evaluate(patient_state)
    mandatory_actions = list(constraints.mandatory_actions)
    forbidden_actions = list(constraints.forbidden_actions)
    required_prior_actions = constraints.required_prior_actions
    deadlines = constraints.deadlines

    ontology_matcher = (
        _get_ontology_matcher_for_guideline(guideline_id)
        if enable_ontology else None
    )

    return _evaluate_compliance(
        case_id=case_id,
        guideline_id=guideline_id,
        performed_actions=performed_actions,
        performed_norm=performed_norm,
        mandatory_actions=mandatory_actions,
        forbidden_actions=forbidden_actions,
        required_prior_actions=required_prior_actions,
        deadlines=deadlines,
        evidence_flags=evidence_flags,
        ontology_matcher=ontology_matcher,
        notes=list(episode.get("warnings", []) or []),
        required_actions=episode.get("required_actions"),
    )


def evaluate_normalized_episodes(
    episodes: Iterable[Dict[str, Any]],
    project_root: Path,
    enable_ontology: bool = False,
) -> List[EvaluableComplianceReport]:
    return [
        evaluate_normalized_episode(episode, project_root, enable_ontology=enable_ontology)
        for episode in episodes
    ]


def summarize_reports(reports: List[EvaluableComplianceReport]) -> Dict[str, Any]:
    total = len(reports)
    with_guideline = [r for r in reports if r.guideline_id]
    evaluable_cases = [r for r in with_guideline if r.evaluable_actions]

    avg_observability = (
        sum(r.observability_index for r in with_guideline) / len(with_guideline)
        if with_guideline
        else 0.0
    )
    avg_compliance = (
        sum(r.compliance_score for r in evaluable_cases) / len(evaluable_cases)
        if evaluable_cases
        else 0.0
    )
    required_cases = [r for r in reports if r.required_compliance_score is not None]
    avg_required_compliance = (
        sum(r.required_compliance_score for r in required_cases) / len(required_cases)
        if required_cases
        else 0.0
    )

    def observed_evidence(report: EvaluableComplianceReport) -> Dict[str, bool]:
        summary = report.evidence_summary
        if "observed" in summary:
            return summary["observed"]
        return summary.get("evidence", {})

    evidence_coverage = {
        "vitals": sum(1 for r in reports if observed_evidence(r).get("vitals")),
        "labs": sum(1 for r in reports if observed_evidence(r).get("labs")),
        "imaging": sum(1 for r in reports if observed_evidence(r).get("imaging")),
        "medications": sum(1 for r in reports if observed_evidence(r).get("medications")),
        "exam": sum(1 for r in reports if observed_evidence(r).get("exam")),
        "history": sum(1 for r in reports if observed_evidence(r).get("history")),
        "diagnosis": sum(1 for r in reports if observed_evidence(r).get("diagnosis")),
        "timestamps": sum(1 for r in reports if observed_evidence(r).get("timestamps")),
        "state_delta": sum(1 for r in reports if observed_evidence(r).get("state_delta")),
    }

    return {
        "total_cases": total,
        "cases_with_guideline": len(with_guideline),
        "cases_with_evaluable_actions": len(evaluable_cases),
        "average_observability_index": avg_observability,
        "average_evaluable_compliance": avg_compliance,
        "average_required_compliance": avg_required_compliance,
        "evidence_coverage_counts": evidence_coverage,
    }


def reports_to_json(reports: List[EvaluableComplianceReport], summary: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "summary": summary,
        "cases": [
            {
                "case_id": r.case_id,
                "guideline_id": r.guideline_id,
                "observability_index": r.observability_index,
                "compliance_score": r.compliance_score,
                "required_compliance_score": r.required_compliance_score,
                "mandatory_actions": r.mandatory_actions,
                "required_actions": r.required_actions,
                "evaluable_actions": r.evaluable_actions,
                "not_observable_actions": r.not_observable_actions,
                "satisfied_actions": r.satisfied_actions,
                "required_satisfied_actions": r.required_satisfied_actions,
                "violations": r.violations,
                "forbidden_actions": r.forbidden_actions,
                "required_prior_actions": r.required_prior_actions,
                "deadlines": r.deadlines,
                "performed_actions": r.performed_actions,
                "evidence_summary": r.evidence_summary,
                "notes": r.notes,
            }
            for r in reports
        ],
    }
