"""
EpisodeNarrativeGenerator: Converts episode logs into clinical narratives with timelines.
No LLM dependency — purely template + CPG graph data via ViolationExplainer.
"""

from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

from cga_bench.cpg_model.schemas.base import (
    CGAScore,
    ViolationType,
)
from cga_bench.eval_harness.explainability.violation_explainer import ViolationExplainer

# ---------------------------------------------------------------------------
# Status constants
# ---------------------------------------------------------------------------

_STATUS_COMPLIANT = "COMPLIANT"
_STATUS_TIMING = "TIMING_VIOLATION"
_STATUS_OMISSION = "OMISSION"
_STATUS_SEQUENCE = "SEQUENCE_VIOLATION"
_STATUS_DEVIATION = "DEVIATION"

_VIOLATION_TYPE_TO_STATUS: dict[str, str] = {
    ViolationType.TIMING.value: _STATUS_TIMING,
    ViolationType.OMISSION.value: _STATUS_OMISSION,
    ViolationType.COMMISSION.value: _STATUS_OMISSION,  # treat commission as omission-class
    ViolationType.SEQUENCE.value: _STATUS_SEQUENCE,
    ViolationType.DEVIATION.value: _STATUS_DEVIATION,
}

# Severity order for selecting primary_issue
_STATUS_SEVERITY: dict[str, int] = {
    _STATUS_COMPLIANT: 0,
    _STATUS_DEVIATION: 1,
    _STATUS_TIMING: 2,
    _STATUS_SEQUENCE: 3,
    _STATUS_OMISSION: 4,
}

# Korean labels for violation types
_STATUS_KOREAN: dict[str, str] = {
    _STATUS_COMPLIANT: "가이드라인 준수",
    _STATUS_TIMING: "시간 제한 위반",
    _STATUS_OMISSION: "필수/금기 행동 위반",
    _STATUS_SEQUENCE: "순서 위반",
    _STATUS_DEVIATION: "이탈",
}

# Markdown emoji per status
_STATUS_EMOJI: dict[str, str] = {
    _STATUS_COMPLIANT: "✅",
    _STATUS_TIMING: "⚠️",
    _STATUS_OMISSION: "❌",
    _STATUS_SEQUENCE: "🔄",
    _STATUS_DEVIATION: "⚪",
}


# ---------------------------------------------------------------------------
# Helper: build a short vitals summary string from patient_info
# ---------------------------------------------------------------------------

def _vitals_summary(patient_info: dict[str, Any]) -> str:
    vitals = patient_info.get("vitals") or {}
    if not vitals:
        return ""
    parts: list[str] = []
    hr = vitals.get("heart_rate")
    if hr is not None:
        parts.append(f"HR {hr:.0f}회/분")
    sbp = vitals.get("blood_pressure_systolic")
    dbp = vitals.get("blood_pressure_diastolic")
    if sbp is not None and dbp is not None:
        parts.append(f"BP {sbp:.0f}/{dbp:.0f} mmHg")
    elif sbp is not None:
        parts.append(f"SBP {sbp:.0f} mmHg")
    rr = vitals.get("respiratory_rate")
    if rr is not None:
        parts.append(f"RR {rr:.0f}회/분")
    spo2 = vitals.get("oxygen_saturation")
    if spo2 is not None:
        parts.append(f"SpO2 {spo2:.0f}%")
    temp = vitals.get("temperature")
    if temp is not None:
        parts.append(f"체온 {temp:.1f}°C")
    map_val = vitals.get("map_mmhg")
    if map_val is not None:
        parts.append(f"MAP {map_val:.0f} mmHg")
    return ", ".join(parts)


# ---------------------------------------------------------------------------
# Helper: build patient_summary sentence
# ---------------------------------------------------------------------------

def _build_patient_summary(patient_info: dict[str, Any]) -> str:
    age = patient_info.get("age", "")
    sex = patient_info.get("sex", "")
    chief_complaint = patient_info.get("chief_complaint", "주증상 불명")
    vitals_str = _vitals_summary(patient_info)

    parts: list[str] = []
    if age and sex:
        parts.append(f"{age}세 {sex}")
    elif age:
        parts.append(f"{age}세")
    elif sex:
        parts.append(sex)

    parts.append(f"{chief_complaint}으로 내원")

    sentence = ", ".join(parts) if parts else chief_complaint + "으로 내원"
    if vitals_str:
        return f"{sentence}. {vitals_str}."
    return f"{sentence}."


# ---------------------------------------------------------------------------
# Helper: determine status for a set of action IDs at a time point
# ---------------------------------------------------------------------------

def _get_status_for_actions(
    action_ids: list[str],
    violations_by_action: dict[str, list[dict[str, Any]]],
    omission_statuses: list[str],
) -> tuple[str, Optional[str]]:
    """
    Returns (status, violation_id_or_None).
    Checks whether any of the given action_ids have associated violations.
    omission_statuses is list of statuses collected from omission-type violations
    that aren't tied to a specific action.
    """
    worst_status = _STATUS_COMPLIANT
    worst_vid: Optional[str] = None

    for aid in action_ids:
        for vinfo in violations_by_action.get(aid, []):
            status = vinfo["status"]
            if _STATUS_SEVERITY.get(status, 0) > _STATUS_SEVERITY.get(worst_status, 0):
                worst_status = status
                worst_vid = vinfo["violation_id"]

    return worst_status, worst_vid


# ---------------------------------------------------------------------------
# EpisodeNarrativeGenerator
# ---------------------------------------------------------------------------

_DEFAULT_CPG_GRAPHS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "cpg_model" / "graphs"
)


class EpisodeNarrativeGenerator:
    """Generates clinical narrative + timeline from episode results."""

    def __init__(self, cpg_graphs_dir: str = str(_DEFAULT_CPG_GRAPHS_DIR)) -> None:
        self.explainer = ViolationExplainer(cpg_graphs_dir)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def generate(
        self,
        scenario_id: str,
        score: CGAScore,
        actions: list[Any],
        patient_info: dict[str, Any],
    ) -> dict[str, Any]:
        """Generate full narrative JSON.

        Returns a structured dict with:
        - scenario
        - patient_summary
        - timeline[]
        - summary{}
        - clinical_assessment
        """
        patient_summary = _build_patient_summary(patient_info)
        timeline = self._build_timeline(score, actions)
        summary = self._build_summary(score)
        clinical_assessment = self._build_clinical_assessment(score)

        return {
            "scenario": scenario_id,
            "patient_summary": patient_summary,
            "timeline": timeline,
            "summary": summary,
            "clinical_assessment": clinical_assessment,
        }

    def generate_markdown(self, narrative: dict[str, Any]) -> str:
        """Convert narrative JSON to human-readable markdown with emoji."""
        lines: list[str] = []

        lines.append(f"# 임상 내러티브: {narrative.get('scenario', 'N/A')}")
        lines.append("")

        lines.append("## 환자 정보")
        lines.append(narrative.get("patient_summary", ""))
        lines.append("")

        lines.append("## 타임라인")
        for entry in narrative.get("timeline", []):
            status = entry.get("status", _STATUS_COMPLIANT)
            emoji = _STATUS_EMOJI.get(status, "⚪")
            time_min = entry.get("time_offset_min", 0)
            actions_str = ", ".join(entry.get("actions", []))
            note = entry.get("note", "")
            violation_ref = entry.get("violation_ref")

            lines.append(f"### {emoji} T+{time_min}분 — {_STATUS_KOREAN.get(status, status)}")
            if actions_str:
                lines.append(f"- **행동**: {actions_str}")
            if note:
                lines.append(f"- **비고**: {note}")
            if violation_ref:
                lines.append(f"- **위반 ID**: `{violation_ref}`")
            lines.append("")

        summary = narrative.get("summary", {})
        if summary:
            lines.append("## 요약")
            compliance_pct = summary.get("compliance_score_pct", 0)
            total_v = summary.get("total_violations", 0)
            peak_risk = summary.get("peak_risk", 0.0)
            agg_risk = summary.get("aggregate_risk", 0.0)
            lines.append(f"- 준수율: **{compliance_pct:.1f}%**")
            lines.append(f"- 총 위반 수: **{total_v}건**")
            lines.append(f"- 최고 위험도: **{peak_risk:.2f}**")
            lines.append(f"- 누적 위험도: **{agg_risk:.2f}**")

            sub = summary.get("sub_scores", {})
            if sub:
                lines.append("")
                lines.append("### 하위 점수")
                for key, val in sub.items():
                    lines.append(f"- {key}: {val:.3f}")
            lines.append("")

        lines.append("## 임상 평가")
        lines.append(narrative.get("clinical_assessment", ""))
        lines.append("")

        return "\n".join(lines)

    def save(self, narrative: dict[str, Any], output_dir: str) -> None:
        """Save both JSON and markdown versions."""
        os.makedirs(output_dir, exist_ok=True)
        scenario = narrative.get("scenario", "narrative")
        json_path = os.path.join(output_dir, f"{scenario}_narrative.json")
        md_path = os.path.join(output_dir, f"{scenario}_narrative.md")

        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(narrative, f, ensure_ascii=False, indent=2)

        md_content = self.generate_markdown(narrative)
        with open(md_path, "w", encoding="utf-8") as f:
            f.write(md_content)

    # ------------------------------------------------------------------
    # Internal builders
    # ------------------------------------------------------------------

    def _build_timeline(
        self,
        score: CGAScore,
        actions: list[Any],
    ) -> list[dict[str, Any]]:
        """Group actions by rounded minute, annotate with violation status."""
        # Index violations by action_involved and expected_action
        violations_by_action: dict[str, list[dict[str, Any]]] = defaultdict(list)
        omission_violations: list[dict[str, Any]] = []

        for v in score.violation_events:
            vtype_val = (
                v.violation_type.value
                if hasattr(v.violation_type, "value")
                else str(v.violation_type)
            )
            status = _VIOLATION_TYPE_TO_STATUS.get(vtype_val, _STATUS_DEVIATION)
            vinfo = {
                "violation_id": v.violation_id,
                "status": status,
                "timestamp_minutes": v.timestamp_minutes,
                "description": v.description or "",
            }
            if v.action_involved:
                violations_by_action[v.action_involved].append(vinfo)
            if v.expected_action:
                violations_by_action[v.expected_action].append(vinfo)
            if not v.action_involved and vtype_val == ViolationType.OMISSION.value:
                omission_violations.append(vinfo)

        # Group actions by rounded minute
        groups: dict[int, list[Any]] = defaultdict(list)
        for action in actions:
            t = getattr(action, "timestamp_minutes", 0) or 0
            minute = int(round(t))
            groups[minute].append(action)

        # Build timeline entries
        timeline: list[dict[str, Any]] = []

        for minute in sorted(groups.keys()):
            group_actions = groups[minute]
            action_ids = [
                getattr(a, "action_id", str(a)) for a in group_actions
            ]

            worst_status, worst_vid = _get_status_for_actions(
                action_ids, violations_by_action, []
            )

            note = self._make_note(worst_status, action_ids, group_actions)

            timeline.append({
                "time_offset_min": minute,
                "actions": action_ids,
                "status": worst_status,
                "note": note,
                "violation_ref": worst_vid,
            })

        # Append omission-only entries (violations without a corresponding action)
        # grouped by their timestamp
        omission_groups: dict[int, list[dict[str, Any]]] = defaultdict(list)
        for ov in omission_violations:
            minute = int(round(ov["timestamp_minutes"]))
            omission_groups[minute].append(ov)

        for minute, oviols in omission_groups.items():
            if minute in groups:
                # Already captured in actions group; update note if needed
                continue
            worst = max(oviols, key=lambda v: _STATUS_SEVERITY.get(v["status"], 0))
            timeline.append({
                "time_offset_min": minute,
                "actions": [],
                "status": worst["status"],
                "note": worst["description"] or _STATUS_KOREAN.get(worst["status"], worst["status"]),
                "violation_ref": worst["violation_id"],
            })

        # Sort final timeline
        timeline.sort(key=lambda e: e["time_offset_min"])
        return timeline

    def _make_note(
        self,
        status: str,
        action_ids: list[str],
        group_actions: list[Any],
    ) -> str:
        """Generate a brief Korean note for a timeline entry."""
        if status == _STATUS_COMPLIANT:
            if action_ids:
                return f"{'·'.join(action_ids)} 수행 완료"
            return "수행 완료"
        label = _STATUS_KOREAN.get(status, status)
        if action_ids:
            return f"{label}: {'·'.join(action_ids)}"
        return label

    def _build_summary(self, score: CGAScore) -> dict[str, Any]:
        """Build structured summary dict from CGAScore."""
        return {
            "compliance_score_pct": round(score.compliance_score * 100, 1),
            "total_violations": score.total_violations,
            "violations_by_type": dict(score.violations_by_type),
            "peak_risk": round(score.peak_risk, 4),
            "aggregate_risk": round(score.aggregate_risk, 4),
            "justified_deviations": score.justified_deviations,
            "sub_scores": {k: round(v, 4) for k, v in score.sub_scores.items()},
        }

    def _build_clinical_assessment(self, score: CGAScore) -> str:
        """Generate template-based clinical assessment string.

        Format: "전체 준수율 {compliance_pct}%, 필수 행동 완료율 {c2_pct}%, 금기 행동 {c3_status}. {primary_issue}."
        """
        compliance_pct = round(score.compliance_score * 100, 1)

        # C2: mandatory completion sub-score
        c2_raw = score.sub_scores.get("C2_mandatory_completion", None)
        c2_pct = round(c2_raw * 100, 1) if c2_raw is not None else compliance_pct

        # C3: commission / forbidden action violations
        commission_count = score.violations_by_type.get(ViolationType.COMMISSION.value, 0)
        if commission_count == 0:
            c3_status = "없음"
        else:
            c3_status = f"{commission_count}건 발생"

        # Primary issue: most severe violation type
        primary_issue = self._primary_issue(score)

        return f"전체 준수율 {compliance_pct}%, 필수 행동 완료율 {c2_pct}%, 금기 행동 {c3_status}. {primary_issue}."

    def _primary_issue(self, score: CGAScore) -> str:
        """Return Korean description of the most severe violation type found."""
        if score.total_violations == 0:
            return "가이드라인을 완전히 준수함"

        # Map violation types to their statuses
        type_status_map: dict[str, str] = {
            ViolationType.OMISSION.value: _STATUS_OMISSION,
            ViolationType.COMMISSION.value: _STATUS_OMISSION,
            ViolationType.TIMING.value: _STATUS_TIMING,
            ViolationType.SEQUENCE.value: _STATUS_SEQUENCE,
            ViolationType.DEVIATION.value: _STATUS_DEVIATION,
        }

        worst_status = _STATUS_COMPLIANT
        worst_count = 0

        for vtype_str, count in score.violations_by_type.items():
            if count == 0:
                continue
            status = type_status_map.get(vtype_str, _STATUS_DEVIATION)
            if _STATUS_SEVERITY.get(status, 0) > _STATUS_SEVERITY.get(worst_status, 0):
                worst_status = status
                worst_count = count
            elif _STATUS_SEVERITY.get(status, 0) == _STATUS_SEVERITY.get(worst_status, 0):
                worst_count += count

        label = _STATUS_KOREAN.get(worst_status, worst_status)
        return f"주요 문제: {label} {worst_count}건"
