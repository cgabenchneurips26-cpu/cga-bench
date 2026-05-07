"""Universal 4-stage external benchmark pipeline.

Stage 1: raw -> CanonicalCase (dataset-specific parsing)
Stage 2: CanonicalCase -> ExpectedAction[] (action extraction)
Stage 3: ExpectedAction[] -> pseudo-episode or NormalizedEpisode
Stage 4: episode -> CGA scoring (delegated to evaluator/harm_scorer)

This module handles Stages 1-3. Stage 4 uses existing evaluator.py.
"""

from __future__ import annotations

import logging
import re
from typing import Any

try:
    from .healthbench import classify_criterion_enhanced as _classify_criterion_enhanced
except ImportError:
    _classify_criterion_enhanced = None

from ...cpg_model.schemas.base import PatientState, VitalSigns
from .base import ExternalBenchmarkAdapter
from .models import (
    CanonicalCase,
    CriterionKind,
    DatasetManifest,
    EpisodeEvidence,
    ExpectedAction,
    NormalizedEpisode,
    TaskType,
)

logger = logging.getLogger(__name__)


def normalize_action_id(text: str) -> str:
    """Standard action ID normalization."""
    return re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")[:80]


class UniversalExternalAdapter(ExternalBenchmarkAdapter):
    """Concrete adapter implementing ExternalBenchmarkAdapter for the universal pipeline."""

    def __init__(self, manifest: DatasetManifest):
        self._manifest = manifest

    @property
    def dataset_id(self) -> str:
        return self._manifest.dataset_id

    def load_raw_case(self, data: dict[str, Any]) -> dict[str, Any]:
        return data

    def parse_to_scenario(self, raw: dict[str, Any]) -> dict[str, Any]:
        canonical = raw_to_canonical(raw, self._manifest)
        return {
            "case_id": canonical.case_id,
            "domain": canonical.domain,
            "input_text": canonical.input_text,
            "task_type": canonical.task_type.value,
        }

    def parse_to_episode_log(self, raw: dict[str, Any]) -> NormalizedEpisode:
        return process_case(raw, self._manifest)

    def parse_to_normalized(self, raw: dict[str, Any]) -> NormalizedEpisode:
        return process_case(raw, self._manifest)

    def detect_domain(self, raw: dict[str, Any]) -> str:
        canonical = raw_to_canonical(raw, self._manifest)
        return canonical.domain or "general"

    def normalize_actions(self, actions: list[str]) -> list[str]:
        return [normalize_action_id(a) for a in actions]

    def build_observation(self, raw: dict[str, Any]) -> dict[str, Any]:
        canonical = raw_to_canonical(raw, self._manifest)
        return {
            "input_text": canonical.input_text,
            "options": canonical.options,
            "domain": canonical.domain,
            "structured_fields": canonical.structured_fields,
        }

    def parse_agent_output(self, output: Any, raw: dict[str, Any]) -> list[dict[str, Any]]:
        if isinstance(output, str):
            return [{"action": normalize_action_id(output[:80]), "source": "raw_output"}]
        if isinstance(output, list):
            return [{"action": normalize_action_id(str(a)[:80]), "source": "list_output"} for a in output]
        return []

    def native_score(self, raw: dict[str, Any], output: Any) -> dict[str, Any] | None:
        return None


def raw_to_canonical(
    raw: dict[str, Any],
    manifest: DatasetManifest,
) -> CanonicalCase:
    """Convert raw dataset entry to CanonicalCase.

    Routes by task_type to appropriate field extraction.
    """
    case_id = raw.get("case_id") or raw.get("id") or raw.get("task_id") or "unknown"

    input_text = (
        raw.get("input_text")
        or raw.get("narrative")
        or raw.get("case_narrative")
        or raw.get("profile")
        or raw.get("instruction")
        or raw.get("patient_note")
        or raw.get("problem")
        or ""
    )

    options = raw.get("options")
    if options is not None and not isinstance(options, list):
        options = [str(options)]

    gold_answer = raw.get("answer") or raw.get("gold_answer") or raw.get("label") or raw.get("sanswer")
    gold_path = raw.get("path") or raw.get("gold_path")
    checklist = raw.get("checklist") or raw.get("criteria")

    if isinstance(gold_path, str):
        gold_path = [p.strip() for p in gold_path.replace("→", "->").split("->") if p.strip()]
    elif isinstance(gold_path, list):
        gold_path = [str(p) for p in gold_path if str(p).strip()]
    else:
        gold_path = []

    if isinstance(checklist, list):
        checklist = [c.get("text", c.get("criterion", str(c))) if isinstance(c, dict) else str(c) for c in checklist]
    elif checklist is None:
        checklist = None
    else:
        checklist = [str(checklist)]

    structured_fields: dict[str, Any] = {}
    for key in [
        "discharge_note",
        "radiology_note",
        "lab_events",
        "context",
        "target_diagnoses",
        "target_procedures",
        "target_laborders",
        "target_prescriptions",
        "sections",
        "questions",
        "rubrics",
        "rubrics_full",
        "criteria",
    ]:
        if raw.get(key):
            structured_fields[key] = raw[key]

    timeline_events = raw.get("timeline_events") or raw.get("encounters") or []

    domain = _detect_domain(raw, manifest)

    return CanonicalCase(
        case_id=str(case_id),
        dataset_id=manifest.dataset_id,
        split=raw.get("split", ""),
        task_type=manifest.task_type,
        eval_mode=manifest.eval_mode,
        domain=domain,
        input_text=input_text,
        structured_fields=structured_fields,
        timeline_events=timeline_events,
        options=options,
        gold_answer=gold_answer,
        gold_path=gold_path,
        checklist=checklist,
        provenance={
            "dataset": manifest.dataset_id,
            "version": manifest.version,
            "access_level": manifest.access_level,
        },
        sub_score_mask=manifest.sub_score_mask,
    )


def _detect_domain(raw: dict[str, Any], manifest: DatasetManifest) -> str | None:
    """Detect clinical domain from raw data or manifest hint.

    Uses the multilingual domain detector (EN + CN keywords) from domain_detector.py.
    Also incorporates structured fields like MedChain ``tags.病种`` for better coverage.
    """
    if manifest.domain_hint:
        return manifest.domain_hint

    from .domain_detector import DomainDetectorConfig
    from .domain_detector import detect_domain as _multilingual_detect

    disease = raw.get("disease", raw.get("category1", ""))
    tags = raw.get("tags", {})
    tags_text = ""
    if isinstance(tags, dict):
        for val in tags.values():
            if isinstance(val, list):
                tags_text += " ".join(str(v) for v in val) + " "
            elif isinstance(val, str):
                tags_text += val + " "

    text = f"{raw.get('input_text', '')} {raw.get('instruction', '')} {disease} {tags_text}".strip()

    # Use a lower confidence threshold than domain_detector's default (0.3)
    # because the pipeline historically matched on a single keyword.
    config = DomainDetectorConfig(min_confidence=0.15)
    match = _multilingual_detect(text, config=config)
    if match is not None:
        return match.domain
    return None


def build_expected_actions(case: CanonicalCase) -> list[ExpectedAction]:
    """Extract expected actions from CanonicalCase.

    Routes by task_type:
    - open_qa -> classify checklist items as action/assessment/explanation
    - mcq_path -> path nodes -> mandatory decisions + leaf plan
    - multilabel_action -> namespace targets -> mandatory actions
    - structured_ehr -> field-based action extraction
    - triplet_qa -> answer -> single expected action
    - longitudinal_text / multimodal_longitudinal -> timeline -> sequential actions
    """
    handlers = {
        TaskType.OPEN_QA: _actions_from_checklist,
        TaskType.MCQ_PATH: _actions_from_path,
        TaskType.MULTILABEL_ACTION: _actions_from_targets,
        TaskType.STRUCTURED_EHR: _actions_from_structured,
        TaskType.TRIPLET_QA: _actions_from_answer,
        TaskType.LONGITUDINAL_TEXT: _actions_from_timeline,
        TaskType.MULTIMODAL_LONGITUDINAL: _actions_from_timeline,
    }
    handler = handlers.get(case.task_type, _actions_from_checklist)
    return handler(case)


def classify_criterion(text: str) -> CriterionKind:
    r"""Classify criterion text into action/assessment/explanation.

    Uses word-boundary regex (``\b``) to avoid false positives from substring
    matches such as "give" in "given" or "order" in "disorder".
    """
    lower = text.lower()
    action_kw = [
        "order",
        "prescribe",
        "administer",
        "perform",
        "initiate",
        "start",
        "give",
        "refer",
        "obtain",
        "measure",
        "check",
        "draw",
        "send",
    ]
    explanation_kw = ["explain", "counsel", "educate", "inform", "discuss", "rationale"]
    if any(re.search(r"\b" + kw + r"\b", lower) for kw in action_kw):
        return CriterionKind.ACTION
    if any(re.search(r"\b" + kw + r"\b", lower) for kw in explanation_kw):
        return CriterionKind.EXPLANATION
    return CriterionKind.ASSESSMENT


def _actions_from_checklist(case: CanonicalCase) -> list[ExpectedAction]:
    """Open QA / checklist -> filter ACTION-type criteria only.

    Supports rubric-scored datasets (e.g. HealthBench): negative points → forbidden.
    """
    actions: list[ExpectedAction] = []
    rubrics_full = case.structured_fields.get("rubrics_full") or case.structured_fields.get("rubrics") or []
    rubric_meta = {}
    for r in rubrics_full:
        if isinstance(r, dict):
            text = r.get("text", r.get("criterion", ""))
            rubric_meta[text] = {
                "points": r.get("points", 0),
                "tags": r.get("tags", []),
            }

    for idx, item in enumerate(case.checklist or []):
        snippet = item[:40].replace("\n", " ")
        meta = rubric_meta.get(item, {})
        points = meta.get("points", 0)
        tags = meta.get("tags", [])

        if points < 0:
            actions.append(
                ExpectedAction(
                    action_id=normalize_action_id(item[:80]),
                    kind="forbidden",
                    provenance=f"{case.dataset_id}:rubric_negative:idx={idx}:pts={points}:'{snippet}'",
                )
            )
            continue

        if _is_safety_clause(item) and case.dataset_id == "llmeval_med":
            actions.append(
                ExpectedAction(
                    action_id=normalize_action_id(item[:80]),
                    kind="forbidden",
                    provenance=f"{case.dataset_id}:safety_clause:idx={idx}:'{snippet}'",
                )
            )
            continue

        if (tags or points != 0) and _classify_criterion_enhanced is not None:
            kind_class = _classify_criterion_enhanced(item, tags=tags, points=points)
        else:
            kind_class = classify_criterion(item)
        if kind_class == CriterionKind.ACTION:
            actions.append(
                ExpectedAction(
                    action_id=normalize_action_id(item[:80]),
                    kind="mandatory",
                    provenance=f"{case.dataset_id}:checklist:idx={idx}:pts={points}:'{snippet}'",
                )
            )
    return actions


def _is_safety_clause(text: str) -> bool:
    """Detect safety-related clauses in checklist items."""
    lower = text.lower()
    safety_kw = [
        "avoid",
        "do not",
        "contraindicated",
        "dangerous",
        "forbidden",
        "never",
        "unsafe",
        "warning",
        "caution",
        "risk of harm",
    ]
    return any(kw in lower for kw in safety_kw)


def _actions_from_path(case: CanonicalCase) -> list[ExpectedAction]:
    """MCQ with decision path -> intermediate mandatory steps + leaf plan."""
    actions: list[ExpectedAction] = []
    path = case.gold_path or []
    for i, node in enumerate(path):
        slug = normalize_action_id(node)
        node_snippet = node[:40]
        if i < len(path) - 1:
            actions.append(
                ExpectedAction(
                    action_id=f"decision/{slug}",
                    kind="mandatory",
                    provenance=f"{case.dataset_id}:path:step={i}:'{node_snippet}'",
                )
            )
        else:
            actions.append(
                ExpectedAction(
                    action_id=f"plan/{slug}",
                    kind="mandatory",
                    provenance=f"{case.dataset_id}:leaf:step={i}:'{node_snippet}'",
                )
            )
    return actions


def _actions_from_targets(case: CanonicalCase) -> list[ExpectedAction]:
    """Multilabel action targets (CliBench-style) -> namespaced actions."""
    actions: list[ExpectedAction] = []
    namespace_map = {
        "target_diagnoses": ("dx/icd10cm", "track_a_only"),
        "target_procedures": ("proc/icd10pcs", "derived_track_b"),
        "target_laborders": ("lab/loinc", "derived_track_b"),
        "target_prescriptions": ("med/atc", "derived_track_b"),
    }
    for field_name, (ns, task_eval_mode) in namespace_map.items():
        targets = case.structured_fields.get(field_name, [])
        if isinstance(targets, str):
            targets = [t.strip() for t in targets.split(",")]
        for idx, t in enumerate(targets):
            if t:
                actions.append(
                    ExpectedAction(
                        action_id=f"{ns}:{normalize_action_id(t)}",
                        kind="mandatory",
                        provenance=(f"{case.dataset_id}:{field_name}:idx={idx}:'{t[:30]}':eval={task_eval_mode}"),
                        confidence=0.7 if "diagnos" in field_name else 1.0,
                    )
                )
    return actions


def _actions_from_structured(case: CanonicalCase) -> list[ExpectedAction]:
    """Structured EHR (EHRStruct) -> observation/parsing validation only."""
    actions: list[ExpectedAction] = []
    if case.gold_answer:
        actions.append(
            ExpectedAction(
                action_id=normalize_action_id(str(case.gold_answer)[:80]),
                kind="mandatory",
                provenance=f"{case.dataset_id}:gold_answer",
                confidence=0.5,
            )
        )
    return actions


def _actions_from_answer(case: CanonicalCase) -> list[ExpectedAction]:
    """Triplet/single-answer (NICE) -> one expected action."""
    if not case.gold_answer:
        return []
    confidence = 0.8 if case.dataset_id == "nice" else 1.0
    return [
        ExpectedAction(
            action_id=normalize_action_id(str(case.gold_answer)[:80]),
            kind="mandatory",
            provenance=f"{case.dataset_id}:answer",
            confidence=confidence,
        )
    ]


def _actions_from_timeline(case: CanonicalCase) -> list[ExpectedAction]:
    """Longitudinal timeline -> sequential actions with ordering."""
    actions: list[ExpectedAction] = []
    prev_ids: list[str] = []
    for i, event in enumerate(case.timeline_events):
        action_id = normalize_action_id(event.get("action", event.get("event", event.get("treatment", f"step_{i}"))))
        raw_text = event.get("action", event.get("event", ""))[:30]
        ea = ExpectedAction(
            action_id=action_id,
            kind="mandatory",
            provenance=f"{case.dataset_id}:timeline:step={i}:'{raw_text}'",
            required_before=list(prev_ids) if prev_ids else None,
        )
        actions.append(ea)
        prev_ids.append(action_id)
    return actions


def canonical_to_normalized(
    case: CanonicalCase,
    expected_actions: list[ExpectedAction],
) -> NormalizedEpisode:
    """Convert CanonicalCase + expected actions to NormalizedEpisode.

    This bridges the new pipeline to the existing evaluator infrastructure.
    """
    action_ids = [ea.action_id for ea in expected_actions]
    mandatory = [ea.action_id for ea in expected_actions if ea.kind == "mandatory"]
    forbidden = [ea.action_id for ea in expected_actions if ea.kind == "forbidden"]

    patient_state = PatientState(
        state_id=case.case_id,
        age=case.structured_fields.get("age", 0),
        sex=case.structured_fields.get("sex", "U"),
        vitals=VitalSigns(map_mmhg=None),
        chief_complaint=(case.input_text or "")[:200],
        working_diagnosis=case.domain,
    )

    deadlines: dict[str, float] = {}
    required_prior: dict[str, list[str]] = {}
    for ea in expected_actions:
        if ea.deadline_min is not None:
            deadlines[ea.action_id] = float(ea.deadline_min)
        if ea.required_before:
            required_prior[ea.action_id] = ea.required_before

    mask = case.sub_score_mask
    evidence = EpisodeEvidence(
        has_vitals=False,
        has_test_results=bool(case.structured_fields.get("target_laborders")),
        has_imaging_results=False,
        has_medications=bool(case.structured_fields.get("target_prescriptions")),
        has_physical_exam=False,
        has_history=bool(case.input_text),
        has_diagnosis=bool(case.domain),
        has_timestamps=bool(deadlines) or mask.c4_timing_compliance,
        action_catalog=set(action_ids),
        notes=[
            f"eval_mode:{case.eval_mode.value}",
            f"task_type:{case.task_type.value}",
            f"domain:{case.domain or 'unknown'}",
            (
                f"mask:C1={mask.c1_path_selection},C2={mask.c2_mandatory_completion},"
                f"C3={mask.c3_forbidden_avoidance},C4={mask.c4_timing_compliance},"
                f"C5={mask.c5_sequence_integrity}"
            ),
        ],
    )

    if not case.domain:
        evidence.notes.append("fallback:universal_clinical_safety")

    warnings = []
    if not action_ids:
        warnings.append("no_expected_actions")

    return NormalizedEpisode(
        case_id=case.case_id,
        source_benchmark=case.dataset_id,
        patient_state=patient_state,
        actions=action_ids,
        evidence=evidence,
        guideline_id=case.domain,
        required_actions=mandatory,
        warnings=warnings,
    )


def process_case(
    raw: dict[str, Any],
    manifest: DatasetManifest,
) -> NormalizedEpisode:
    """Full 3-stage pipeline: raw -> canonical -> expected -> normalized.

    For AMEGA with questions, uses split_amega_questions for the first question only
    (callers wanting all questions should call split_amega_questions directly).
    """
    if manifest.dataset_id == "amega" and raw.get("questions"):
        cases = split_amega_questions(raw, manifest)
        if cases:
            expected = build_expected_actions(cases[0])
            return canonical_to_normalized(cases[0], expected)

    canonical = raw_to_canonical(raw, manifest)
    expected = build_expected_actions(canonical)
    return canonical_to_normalized(canonical, expected)


def process_all_cases(
    raw: dict[str, Any],
    manifest: DatasetManifest,
) -> list[NormalizedEpisode]:
    """Process raw data, splitting into multiple cases if appropriate (e.g. AMEGA questions)."""
    if manifest.dataset_id == "amega" and raw.get("questions"):
        cases = split_amega_questions(raw, manifest)
        return [canonical_to_normalized(c, build_expected_actions(c)) for c in cases]

    canonical = raw_to_canonical(raw, manifest)
    expected = build_expected_actions(canonical)
    return [canonical_to_normalized(canonical, expected)]


def split_amega_questions(raw: dict[str, Any], manifest: DatasetManifest) -> list[CanonicalCase]:
    """Split AMEGA case into per-question CanonicalCases.

    One case -> N questions -> N CanonicalCases.
    Each gets: case narrative as input_text, question as task_prompt, question criteria as checklist.
    """
    questions = raw.get("questions", [])
    narrative = raw.get("narrative", raw.get("case_narrative", raw.get("input_text", "")))
    case_id_base = raw.get("case_id", raw.get("id", "unknown"))

    if not questions:
        return [raw_to_canonical(raw, manifest)]

    cases: list[CanonicalCase] = []
    for i, q in enumerate(questions):
        if not isinstance(q, dict):
            q = {"text": str(q)}

        q_id = q.get("id", f"q{i}")
        q_text = q.get("text", q.get("question", q.get("prompt", "")))
        q_criteria = q.get("criteria", q.get("checklist", []))

        normalized_criteria: list[str] = []
        if isinstance(q_criteria, list):
            for c in q_criteria:
                if isinstance(c, dict):
                    normalized_criteria.append(str(c.get("text", c.get("criterion", str(c)))))
                else:
                    normalized_criteria.append(str(c))
        elif q_criteria is not None:
            normalized_criteria.append(str(q_criteria))

        q_raw = {
            "id": f"{case_id_base}:{q_id}",
            "input_text": f"{narrative}\n\nQuestion: {q_text}" if q_text else narrative,
            "checklist": normalized_criteria,
            "guideline": raw.get("guideline", raw.get("guideline_id")),
        }
        cases.append(raw_to_canonical(q_raw, manifest))

    return cases
