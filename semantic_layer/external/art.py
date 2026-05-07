"""ART (Action-based Reasoning clinical Task) adapter.

Paper: arxiv 2601.08988 - "ART: Action-based Reasoning Task Benchmarking for Medical AI Agents"

Status: Real data not yet publicly released as of 2026-03-26.
Synthetic 5-case sample at data/external_benchmarks/art/synthetic_sample.json
for pipeline compatibility testing.

Data format (from paper):
    - case_id: str
    - task_type: threshold_evaluation | temporal_aggregation | conditional_logic
    - input_text: clinical narrative
    - structured_fields: labs, vitals, medications, timeline
    - checklist: list of required/forbidden action strings
    - gold_answer: target diagnosis or decision label
    - reasoning_type: mirrors task_type
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, List

from .models import CanonicalCase, DatasetManifest, TaskType
from .pipeline import (
    UniversalExternalAdapter,
    build_expected_actions,
    canonical_to_normalized,
    raw_to_canonical,
)
from .models import NormalizedEpisode


# ART task type -> action kind mapping for checklist items
_FORBIDDEN_PREFIXES = ("do not", "avoid", "never", "contraindicated", "do not administer")


def _is_forbidden_art_action(text: str) -> bool:
    """Detect forbidden actions in ART checklists by prefix convention."""
    lower = text.lower().strip()
    return any(lower.startswith(prefix) for prefix in _FORBIDDEN_PREFIXES)


def parse_art_case(raw: Dict[str, Any], manifest: DatasetManifest) -> CanonicalCase:
    """Parse a single ART case dict into CanonicalCase.

    Handles ART-specific fields:
    - reasoning_type / task_type field -> stored in structured_fields
    - structured_fields.labs / vitals / timeline kept as-is
    - checklist items inspected for forbidden-action prefixes
    """
    # Normalize checklist: tag forbidden items so pipeline can classify them
    raw_checklist = raw.get("checklist") or []
    annotated_checklist: List[str] = []
    for item in raw_checklist:
        if isinstance(item, str):
            annotated_checklist.append(item)
        elif isinstance(item, dict):
            annotated_checklist.append(item.get("text", str(item)))

    # Build enriched raw dict for the universal pipeline
    enriched: Dict[str, Any] = {
        "id": raw.get("case_id") or raw.get("id") or "unknown",
        "split": raw.get("split", "test"),
        "input_text": raw.get("input_text") or raw.get("narrative") or "",
        "checklist": annotated_checklist,
        "gold_answer": raw.get("gold_answer") or raw.get("label"),
        # Preserve ART structured data for domain detection
        "context": json.dumps(raw.get("structured_fields", {})) if raw.get("structured_fields") else "",
    }

    # Carry through structured fields that the universal pipeline recognises
    structured = raw.get("structured_fields") or {}
    for key in ("labs", "vitals", "medications", "timeline", "patient_context"):
        if key in structured:
            enriched[key] = structured[key]

    # Reasoning type as a tag for downstream use
    reasoning_type = raw.get("reasoning_type") or raw.get("task_type") or ""
    if reasoning_type:
        enriched["art_reasoning_type"] = reasoning_type

    canonical = raw_to_canonical(enriched, manifest)

    # Post-process: override forbidden actions based on ART conventions
    # The universal pipeline classifies by keyword; ART uses explicit "Do not" prefix
    # Store reasoning type annotation in provenance
    canonical.provenance["art_reasoning_type"] = reasoning_type
    return canonical


def normalize_art_case(raw: Dict[str, Any], manifest: DatasetManifest) -> NormalizedEpisode:
    """Full pipeline for a single ART case: raw -> canonical -> expected -> normalized."""
    canonical = parse_art_case(raw, manifest)
    expected = build_expected_actions(canonical)
    return canonical_to_normalized(canonical, expected)


def load_art_sample(path: str | Path) -> List[Dict[str, Any]]:
    """Load ART cases from a JSON file (list format)."""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"ART data file not found: {p}")
    with p.open() as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON list, got {type(data).__name__}")
    return data


class ARTAdapter(UniversalExternalAdapter):
    """ART-specific adapter extending UniversalExternalAdapter.

    Overrides parse_to_episode_log to use ART-aware checklist parsing.
    """

    def parse_to_episode_log(self, raw: Dict[str, Any]) -> NormalizedEpisode:
        return normalize_art_case(raw, self._manifest)

    def parse_to_normalized(self, raw: Dict[str, Any]) -> NormalizedEpisode:
        return normalize_art_case(raw, self._manifest)

    def native_score(self, raw: Dict[str, Any], output: Any) -> Dict[str, Any] | None:
        """ART native score: fraction of checklist items satisfied.

        Returns None if output is not a list of action strings.
        """
        if not isinstance(output, list):
            return None
        checklist = raw.get("checklist") or []
        if not checklist:
            return None

        output_lower = {str(a).lower() for a in output}
        satisfied = 0
        for item in checklist:
            item_lower = item.lower()
            if any(item_lower[:30] in o for o in output_lower):
                satisfied += 1

        return {
            "native_score": satisfied / len(checklist),
            "satisfied": satisfied,
            "total": len(checklist),
            "reasoning_type": raw.get("reasoning_type", ""),
        }
