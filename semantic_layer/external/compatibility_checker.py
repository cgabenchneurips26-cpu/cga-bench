"""Dataset compatibility checker for CGA-Bench evaluation axes.

Given raw sample rows from a new external benchmark, automatically determines:
- Which EvalMode is appropriate (direct_track_b / derived_track_b / track_a_only / safety_only)
- Which C1-C5 sub-scores are computable (SubScoreMask)
- Which Track A variant to use (action_match / rubric_grounded / native_only)
- Whether native scoring correlation is possible

Usage:
    from cga_bench.semantic_layer.external.compatibility_checker import check_compatibility
    report = check_compatibility(sample_rows)
    print(report)
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from .models import EvalMode, SubScoreMask, TaskType


@dataclass
class SignalStrength:
    present: bool = False
    confidence: float = 0.0
    evidence: List[str] = field(default_factory=list)


@dataclass
class CompatibilityReport:
    dataset_name: str
    n_samples: int

    recommended_eval_mode: EvalMode
    recommended_task_type: TaskType
    recommended_mask: SubScoreMask
    recommended_track_a_variant: str

    signals: Dict[str, SignalStrength] = field(default_factory=dict)
    warnings: List[str] = field(default_factory=list)
    summary: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "dataset_name": self.dataset_name,
            "n_samples": self.n_samples,
            "recommended_eval_mode": self.recommended_eval_mode.value,
            "recommended_task_type": self.recommended_task_type.value,
            "recommended_mask": {
                "c1_path_selection": self.recommended_mask.c1_path_selection,
                "c2_mandatory_completion": self.recommended_mask.c2_mandatory_completion,
                "c3_forbidden_avoidance": self.recommended_mask.c3_forbidden_avoidance,
                "c4_timing_compliance": self.recommended_mask.c4_timing_compliance,
                "c5_sequence_integrity": self.recommended_mask.c5_sequence_integrity,
            },
            "recommended_track_a_variant": self.recommended_track_a_variant,
            "signals": {
                k: {"present": v.present, "confidence": round(v.confidence, 2), "evidence": v.evidence[:3]}
                for k, v in self.signals.items()
            },
            "warnings": self.warnings,
            "summary": self.summary,
        }

    def __str__(self) -> str:
        lines = [
            f"=== CGA Compatibility Report: {self.dataset_name} ({self.n_samples} samples) ===",
            f"  Eval Mode:       {self.recommended_eval_mode.value}",
            f"  Task Type:       {self.recommended_task_type.value}",
            f"  Track A Variant: {self.recommended_track_a_variant}",
            f"  C1 Path:    {'ON' if self.recommended_mask.c1_path_selection else 'OFF'}",
            f"  C2 Mandatory: {'ON' if self.recommended_mask.c2_mandatory_completion else 'OFF'}",
            f"  C3 Forbidden: {'ON' if self.recommended_mask.c3_forbidden_avoidance else 'OFF'}",
            f"  C4 Timing:    {'ON' if self.recommended_mask.c4_timing_compliance else 'OFF'}",
            f"  C5 Sequence:  {'ON' if self.recommended_mask.c5_sequence_integrity else 'OFF'}",
            "",
        ]
        for name, sig in self.signals.items():
            status = "DETECTED" if sig.present else "NOT FOUND"
            lines.append(f"  [{status:>9}] {name} (conf={sig.confidence:.0%})")
            for ev in sig.evidence[:2]:
                lines.append(f"             └ {ev}")
        if self.warnings:
            lines.append("")
            for w in self.warnings:
                lines.append(f"  ⚠ {w}")
        lines.append(f"\n  {self.summary}")
        return "\n".join(lines)


# ---------------------------------------------------------------------------
# Signal detectors — each inspects the raw sample rows for a specific property
# ---------------------------------------------------------------------------

_TIMING_KEYWORDS = [
    r"\bwithin\s+\d+", r"\bminute[s]?\b", r"\bhour[s]?\b(?!\s*urine)",
    r"\bdeadline\b", r"\btime\s*limit\b",
    r"\bimmediately\b", r"\bstat\b(?!\w)", r"\bemergent\b", r"\basap\b",
    r"\bdelay\b", r"\burgent\b",
]

_SEQUENCE_KEYWORDS = [
    r"\bbefore\s+(?:starting|giving|administering)",
    r"\bafter\s+(?:completing|obtaining|confirming)",
    r"\bprior\s+to\b", r"\bfollowing\b(?!\s+up)",
    r"\bthen\s+(?:give|order|start|perform)",
    r"\bfirst.*\bthen\b", r"\bstep\s*[12345]\b", r"\bsequential\b",
    r"\bprerequisite\b", r"\brequired\s+before\b",
]

_FORBIDDEN_KEYWORDS = [
    "contraindicated", "forbidden", "do not", "avoid",
    "never", "unsafe", "harmful", "dangerous",
    "should not", "must not", "risk of harm",
]

_ACTION_KEYWORDS = [
    "order", "prescribe", "administer", "perform", "initiate",
    "start", "give", "refer", "obtain", "measure",
    "check", "draw", "send", "inject", "infuse",
]


def _count_keyword_hits(texts: List[str], keywords: List[str]) -> tuple[int, List[str]]:
    hits = 0
    evidence = []
    for text in texts:
        lower = text.lower()
        for kw in keywords:
            if re.search(kw, lower):
                hits += 1
                if len(evidence) < 5:
                    snippet = text[:80].replace("\n", " ")
                    evidence.append(f"'{snippet}' matched '{kw}'")
                break
    return hits, evidence


def _detect_structured_actions(rows: List[Dict[str, Any]]) -> SignalStrength:
    target_keys = {"target_diagnoses", "target_procedures", "target_laborders",
                   "target_prescriptions", "actions", "expected_actions", "gold_actions"}
    hit_count = 0
    evidence = []
    for row in rows:
        found = target_keys & set(row.keys())
        if found:
            hit_count += 1
            for k in found:
                val = row[k]
                if val:
                    evidence.append(f"key='{k}' with {type(val).__name__}")
    ratio = hit_count / max(len(rows), 1)
    return SignalStrength(present=ratio > 0.3, confidence=ratio, evidence=evidence[:3])


def _detect_rubric_checklist(rows: List[Dict[str, Any]]) -> SignalStrength:
    rubric_keys = {"rubrics", "rubric", "checklist", "criteria", "evaluation_criteria"}
    hit_count = 0
    evidence = []
    for row in rows:
        found = rubric_keys & set(row.keys())
        if found:
            hit_count += 1
            for k in found:
                val = row[k]
                if isinstance(val, list):
                    evidence.append(f"'{k}': {len(val)} items")
                elif isinstance(val, str) and len(val) > 20:
                    evidence.append(f"'{k}': text ({len(val)} chars)")
    ratio = hit_count / max(len(rows), 1)
    return SignalStrength(present=ratio > 0.3, confidence=ratio, evidence=evidence[:3])


def _detect_native_scoring(rows: List[Dict[str, Any]]) -> SignalStrength:
    score_indicators = {"points", "score", "weight", "binary_labels", "rating", "grade"}
    evidence = []
    found_rows = 0
    for row in rows:
        for key in score_indicators:
            if key in row:
                found_rows += 1
                evidence.append(f"top-level key '{key}'")
                break
        rubrics = row.get("rubrics", [])
        if isinstance(rubrics, list):
            for r in rubrics[:1]:
                if isinstance(r, dict) and "points" in r:
                    found_rows += 1
                    evidence.append(f"rubrics[].points={r['points']}")
                    break
    ratio = found_rows / max(len(rows), 1)
    return SignalStrength(present=ratio > 0.3, confidence=min(ratio, 1.0), evidence=evidence[:3])


def _detect_path_trajectory(rows: List[Dict[str, Any]]) -> SignalStrength:
    path_keys = {"path", "gold_path", "trajectory", "decision_path", "steps"}
    hit_count = 0
    evidence = []
    for row in rows:
        found = path_keys & set(row.keys())
        if found:
            hit_count += 1
            for k in found:
                val = row[k]
                if isinstance(val, list):
                    evidence.append(f"'{k}': {len(val)} steps")
                elif isinstance(val, str) and ("→" in val or "->" in val):
                    evidence.append(f"'{k}': arrow path")
    ratio = hit_count / max(len(rows), 1)
    return SignalStrength(present=ratio > 0.3, confidence=ratio, evidence=evidence[:3])


def _detect_timeline(rows: List[Dict[str, Any]]) -> SignalStrength:
    timeline_keys = {"timeline_events", "encounters", "events", "timeline", "stages"}
    hit_count = 0
    evidence = []
    for row in rows:
        found = timeline_keys & set(row.keys())
        if found:
            hit_count += 1
            for k in found:
                val = row[k]
                if isinstance(val, list) and len(val) > 0:
                    evidence.append(f"'{k}': {len(val)} events")
    ratio = hit_count / max(len(rows), 1)
    return SignalStrength(present=ratio > 0.3, confidence=ratio, evidence=evidence[:3])


def _detect_keyword_signal(
    rows: List[Dict[str, Any]],
    keywords: List[str],
    name: str,
) -> SignalStrength:
    all_texts = []
    for row in rows:
        for key in ("input_text", "instruction", "narrative", "rubric", "prompt", "context"):
            val = row.get(key)
            if isinstance(val, str):
                all_texts.append(val)
            elif isinstance(val, list):
                for item in val:
                    if isinstance(item, dict):
                        all_texts.append(item.get("content", ""))
                    elif isinstance(item, str):
                        all_texts.append(item)
        for r in row.get("rubrics", row.get("checklist", row.get("criteria", []))):
            if isinstance(r, dict):
                all_texts.append(r.get("criterion", r.get("text", "")))
            elif isinstance(r, str):
                all_texts.append(r)
    hits, evidence = _count_keyword_hits(all_texts, keywords)
    ratio = hits / max(len(all_texts), 1)
    return SignalStrength(present=ratio > 0.1, confidence=min(ratio * 3, 1.0), evidence=evidence[:3])


def _detect_negative_points(rows: List[Dict[str, Any]]) -> SignalStrength:
    neg_count = 0
    total_rubrics = 0
    evidence = []
    for row in rows:
        for r in row.get("rubrics", []):
            if isinstance(r, dict):
                total_rubrics += 1
                pts = r.get("points", 0)
                if isinstance(pts, (int, float)) and pts < 0:
                    neg_count += 1
                    if len(evidence) < 3:
                        evidence.append(f"pts={pts}: {r.get('criterion', r.get('text', ''))[:50]}")
    ratio = neg_count / max(total_rubrics, 1)
    return SignalStrength(present=neg_count > 0, confidence=min(ratio * 5, 1.0), evidence=evidence)


def _detect_options_mcq(rows: List[Dict[str, Any]]) -> SignalStrength:
    hit_count = 0
    evidence = []
    for row in rows:
        opts = row.get("options", row.get("choices", row.get("answer_choices")))
        if isinstance(opts, list) and len(opts) >= 2:
            hit_count += 1
            evidence.append(f"options: {len(opts)} choices")
    ratio = hit_count / max(len(rows), 1)
    return SignalStrength(present=ratio > 0.3, confidence=ratio, evidence=evidence[:3])


def _detect_structured_ehr(rows: List[Dict[str, Any]]) -> SignalStrength:
    ehr_keys = {"lab_events", "discharge_note", "radiology_note", "vitals",
                "medications", "procedures", "diagnoses", "icd_codes"}
    hit_count = 0
    evidence = []
    for row in rows:
        found = ehr_keys & set(row.keys())
        if found:
            hit_count += 1
            evidence.append(f"EHR keys: {found}")
    ratio = hit_count / max(len(rows), 1)
    return SignalStrength(present=ratio > 0.3, confidence=ratio, evidence=evidence[:3])


# ---------------------------------------------------------------------------
# Main checker
# ---------------------------------------------------------------------------

def check_compatibility(
    sample_rows: List[Dict[str, Any]],
    dataset_name: str = "unknown",
) -> CompatibilityReport:
    """Analyze sample rows and produce a CGA compatibility report.

    Args:
        sample_rows: List of raw dicts from the dataset (5-50 rows recommended).
        dataset_name: Human-readable name for the report.

    Returns:
        CompatibilityReport with recommended EvalMode, SubScoreMask, and Track A variant.
    """
    n = len(sample_rows)
    if n == 0:
        return CompatibilityReport(
            dataset_name=dataset_name, n_samples=0,
            recommended_eval_mode=EvalMode.SAFETY_ONLY,
            recommended_task_type=TaskType.OPEN_QA,
            recommended_mask=SubScoreMask(False, False, False, False, False),
            recommended_track_a_variant="none",
            warnings=["No sample rows provided"],
            summary="Cannot assess compatibility without data.",
        )

    # Run all signal detectors
    sig = {
        "structured_actions": _detect_structured_actions(sample_rows),
        "rubric_checklist": _detect_rubric_checklist(sample_rows),
        "native_scoring": _detect_native_scoring(sample_rows),
        "path_trajectory": _detect_path_trajectory(sample_rows),
        "timeline_events": _detect_timeline(sample_rows),
        "timing_keywords": _detect_keyword_signal(sample_rows, _TIMING_KEYWORDS, "timing"),
        "sequence_keywords": _detect_keyword_signal(sample_rows, _SEQUENCE_KEYWORDS, "sequence"),
        "forbidden_keywords": _detect_keyword_signal(sample_rows, _FORBIDDEN_KEYWORDS, "forbidden"),
        "action_keywords": _detect_keyword_signal(sample_rows, _ACTION_KEYWORDS, "action"),
        "negative_points": _detect_negative_points(sample_rows),
        "options_mcq": _detect_options_mcq(sample_rows),
        "structured_ehr": _detect_structured_ehr(sample_rows),
    }

    # Determine Task Type
    task_type = _infer_task_type(sig)

    # Determine SubScoreMask
    mask = SubScoreMask(
        c1_path_selection=sig["path_trajectory"].present or sig["options_mcq"].present,
        c2_mandatory_completion=(
            sig["structured_actions"].present
            or sig["rubric_checklist"].present
            or sig["action_keywords"].present
        ),
        c3_forbidden_avoidance=(
            sig["forbidden_keywords"].present
            or sig["negative_points"].present
        ),
        c4_timing_compliance=(
            sig["timing_keywords"].present
            and sig["timing_keywords"].confidence > 0.5
            and (sig["timeline_events"].present or sig["structured_actions"].present)
        ),
        c5_sequence_integrity=(
            sig["timeline_events"].present
            or (
                sig["sequence_keywords"].present
                and sig["sequence_keywords"].confidence > 0.5
                and sig["path_trajectory"].present
            )
        ),
    )

    # Determine EvalMode
    eval_mode = _infer_eval_mode(sig, mask)

    # Determine Track A variant
    track_a_variant = _infer_track_a_variant(sig)

    # Warnings
    warnings = _generate_warnings(sig, mask, eval_mode)

    # Summary
    active_c = []
    if mask.c1_path_selection: active_c.append("C1")
    if mask.c2_mandatory_completion: active_c.append("C2")
    if mask.c3_forbidden_avoidance: active_c.append("C3")
    if mask.c4_timing_compliance: active_c.append("C4")
    if mask.c5_sequence_integrity: active_c.append("C5")

    summary = (
        f"Recommended: {eval_mode.value} with {track_a_variant} Track A. "
        f"Active sub-scores: {', '.join(active_c) if active_c else 'none'}. "
        f"Native score correlation: {'YES' if sig['native_scoring'].present else 'NO'}."
    )

    return CompatibilityReport(
        dataset_name=dataset_name,
        n_samples=n,
        recommended_eval_mode=eval_mode,
        recommended_task_type=task_type,
        recommended_mask=mask,
        recommended_track_a_variant=track_a_variant,
        signals=sig,
        warnings=warnings,
        summary=summary,
    )


def _infer_task_type(sig: Dict[str, SignalStrength]) -> TaskType:
    if sig["structured_ehr"].present:
        return TaskType.STRUCTURED_EHR
    if sig["timeline_events"].present:
        return TaskType.LONGITUDINAL_TEXT
    if sig["options_mcq"].present and sig["path_trajectory"].present:
        return TaskType.MCQ_PATH
    if sig["structured_actions"].present:
        return TaskType.MULTILABEL_ACTION
    if sig["options_mcq"].present:
        return TaskType.TRIPLET_QA
    return TaskType.OPEN_QA


def _infer_eval_mode(sig: Dict[str, SignalStrength], mask: SubScoreMask) -> EvalMode:
    if sig["path_trajectory"].present and sig["path_trajectory"].confidence > 0.5:
        if sig["timeline_events"].present or (mask.c4_timing_compliance and mask.c5_sequence_integrity):
            return EvalMode.DIRECT_TRACK_B
        return EvalMode.DERIVED_TRACK_B
    if sig["rubric_checklist"].present or sig["structured_actions"].present:
        return EvalMode.DERIVED_TRACK_B
    if sig["action_keywords"].present:
        return EvalMode.TRACK_A_ONLY
    return EvalMode.SAFETY_ONLY


def _infer_track_a_variant(sig: Dict[str, SignalStrength]) -> str:
    if sig["structured_actions"].present and sig["structured_actions"].confidence > 0.5:
        return "action_match"
    if sig["rubric_checklist"].present and sig["native_scoring"].present:
        return "rubric_grounded"
    if sig["rubric_checklist"].present:
        return "rubric_grounded"
    if sig["action_keywords"].present:
        return "llm_extraction"
    return "native_only"


def _generate_warnings(
    sig: Dict[str, SignalStrength],
    mask: SubScoreMask,
    eval_mode: EvalMode,
) -> List[str]:
    warnings = []
    if mask.c4_timing_compliance and sig["timing_keywords"].confidence < 0.5:
        warnings.append("C4 enabled but timing signal is weak — verify explicit deadlines exist")
    if mask.c5_sequence_integrity and not sig["timeline_events"].present:
        warnings.append("C5 enabled from keywords only — verify explicit ordering data exists")
    if eval_mode == EvalMode.SAFETY_ONLY:
        warnings.append("Dataset does not appear to be CPG-adherence focused — consider safety_only evaluation")
    if not sig["rubric_checklist"].present and not sig["structured_actions"].present:
        warnings.append("No rubric or structured actions found — Track A scoring may be unreliable")
    if sig["negative_points"].present and not mask.c3_forbidden_avoidance:
        warnings.append("Negative-point rubrics detected but C3 is OFF — consider enabling")
    return warnings
