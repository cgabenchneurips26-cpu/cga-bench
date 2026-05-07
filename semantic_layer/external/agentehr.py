"""AgentEHR adapter.

Paper: arxiv 2601.13918 - "AgentEHR: Advancing Autonomous Clinical Decision-Making
       via Retrospective Summarization"
HuggingFace: BlueZeros/AgentEHR-Bench (Apache 2.0)

AgentEHR uses MIMIC-III/IV data. Each case has:
    - subject_id: int
    - hadm_id: int (may be absent for some tasks)
    - prediction_time: str ISO datetime
    - task: str  (diagnoses_ccs | labevents | microbiologyevents | prescriptions |
                  procedures_ccs | transfers)
    - label: list of dicts, each with a 'name' field and task-specific fields

The pipeline maps each label item to a target action in the appropriate namespace:
    diagnoses_ccs     -> dx/icd9cm:<code> or dx/name:<slug>
    labevents         -> lab/loinc:<itemid> or lab/name:<slug>
    microbiologyevents-> micro/name:<slug>
    prescriptions     -> med/name:<slug>
    procedures_ccs    -> proc/name:<slug>
    transfers         -> transfer/careunit:<slug>
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .models import CanonicalCase, DatasetManifest, NormalizedEpisode
from .pipeline import (
    UniversalExternalAdapter,
    build_expected_actions,
    canonical_to_normalized,
    normalize_action_id,
    raw_to_canonical,
)


# Task -> structured_field namespace for pipeline routing
_TASK_TO_FIELD: Dict[str, str] = {
    "diagnoses_ccs": "target_diagnoses",
    "labevents": "target_laborders",
    "microbiologyevents": "target_laborders",
    "prescriptions": "target_prescriptions",
    "prescriptions3": "target_prescriptions",
    "procedures_ccs": "target_procedures",
    "transfers": "target_procedures",
}


def _label_to_action_id(item: Dict[str, Any], task: str) -> str:
    """Convert an AgentEHR label item to a namespaced action ID."""
    name = item.get("name", "")
    slug = normalize_action_id(name)

    if task == "diagnoses_ccs":
        icd = item.get("icd_code", "")
        if icd:
            return f"dx/icd:{normalize_action_id(icd)}"
        return f"dx/name:{slug}"

    if task in ("labevents", "microbiologyevents"):
        itemid = item.get("itemid")
        if itemid is not None:
            return f"lab/loinc:{itemid}"
        return f"lab/name:{slug}"

    if task in ("prescriptions", "prescriptions3"):
        return f"med/name:{slug}"

    if task == "procedures_ccs":
        icd = item.get("icd_code", "")
        if icd:
            return f"proc/icd:{normalize_action_id(icd)}"
        return f"proc/name:{slug}"

    if task == "transfers":
        care_unit = item.get("careunit", name)
        return f"transfer/careunit:{normalize_action_id(care_unit)}"

    return f"action:{slug}"


def parse_agentehr_case(raw: Dict[str, Any], manifest: DatasetManifest) -> CanonicalCase:
    """Parse a single AgentEHR case dict into CanonicalCase.

    Maps label list to target_* structured fields so the universal pipeline
    _actions_from_targets handler extracts them correctly.
    """
    task = raw.get("task", "")
    labels = raw.get("label") or []

    # Build target action IDs
    action_ids = [_label_to_action_id(lbl, task) for lbl in labels if isinstance(lbl, dict)]

    # Map to the structured_field key the universal pipeline understands
    field_key = _TASK_TO_FIELD.get(task, "target_procedures")

    # Build a description for input_text (no free-text narrative in AgentEHR)
    subject_id = raw.get("subject_id", "")
    hadm_id = raw.get("hadm_id", "")
    pred_time = raw.get("prediction_time", "")
    input_text = (
        f"AgentEHR task: {task}. "
        f"Subject {subject_id}, admission {hadm_id}, prediction time {pred_time}."
    )

    case_id = f"agentehr_{task}_{subject_id}_{hadm_id}" if hadm_id else f"agentehr_{task}_{subject_id}"

    enriched: Dict[str, Any] = {
        "id": case_id,
        "split": raw.get("split", "test"),
        "input_text": input_text,
        field_key: action_ids,
        # Store raw label names for reference
        "context": json.dumps([lbl.get("name", "") for lbl in labels if isinstance(lbl, dict)]),
    }

    canonical = raw_to_canonical(enriched, manifest)
    canonical.provenance["agentehr_task"] = task
    canonical.provenance["subject_id"] = str(subject_id)
    canonical.provenance["prediction_time"] = str(pred_time)
    return canonical


def normalize_agentehr_case(raw: Dict[str, Any], manifest: DatasetManifest) -> NormalizedEpisode:
    """Full pipeline for a single AgentEHR case: raw -> canonical -> expected -> normalized."""
    canonical = parse_agentehr_case(raw, manifest)
    expected = build_expected_actions(canonical)
    return canonical_to_normalized(canonical, expected)


def load_agentehr_file(path: str | Path) -> List[Dict[str, Any]]:
    """Load AgentEHR cases from a JSON file (list format)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"AgentEHR data file not found: {p}")
    with p.open() as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON list, got {type(data).__name__}")
    return data


class AgentEHRAdapter(UniversalExternalAdapter):
    """AgentEHR-specific adapter extending UniversalExternalAdapter.

    Overrides parsing to use AgentEHR label->action mapping.
    """

    def parse_to_episode_log(self, raw: Dict[str, Any]) -> NormalizedEpisode:
        return normalize_agentehr_case(raw, self._manifest)

    def parse_to_normalized(self, raw: Dict[str, Any]) -> NormalizedEpisode:
        return normalize_agentehr_case(raw, self._manifest)

    def native_score(self, raw: Dict[str, Any], output: Any) -> Dict[str, Any] | None:
        """AgentEHR native score: label recall.

        output should be a list of predicted label names or action IDs.
        """
        if not isinstance(output, list):
            return None
        labels = raw.get("label") or []
        if not labels:
            return None

        task = raw.get("task", "")
        gold_names = {normalize_action_id(lbl.get("name", "")) for lbl in labels if isinstance(lbl, dict)}
        pred_names = {normalize_action_id(str(p)) for p in output}

        tp = len(gold_names & pred_names)
        precision = tp / len(pred_names) if pred_names else 0.0
        recall = tp / len(gold_names) if gold_names else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

        return {
            "native_score": f1,
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "tp": tp,
            "gold_count": len(gold_names),
            "pred_count": len(pred_names),
            "task": task,
        }
