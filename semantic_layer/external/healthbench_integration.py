from __future__ import annotations

from dataclasses import dataclass
from typing import NotRequired, TypedDict, cast

from .models import EvaluableComplianceReport


class CompositeScoreResult(TypedDict):
    final_score: float
    task_success_score: float
    dialogue_quality_score: float
    empathy_score: float
    accuracy_score: float
    component_weights: dict[str, float]


class ExtendedReportEntry(TypedDict):
    case_id: str
    compliance_score: float
    empathy_score: float
    accuracy_score: float
    dialogue_quality_score: float
    composite_score: float
    dialogue_act_summary: dict[str, int]
    violations: list[dict[str, object]]
    empathy_method: NotRequired[str]
    accuracy_weighted_score: NotRequired[float]


class DashboardReport(TypedDict):
    header: str
    sections: list[dict[str, str]]
    summary_table: list[dict[str, object]]
    footer: str


class HITLFlag(TypedDict):
    case_id: str
    reason: str
    confidence: float
    suggested_action: str


@dataclass
class HITLConfig:
    low_confidence_threshold: float = 0.3
    high_divergence_threshold: float = 0.4
    flag_low_empathy: bool = True
    flag_high_violations: bool = True


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _to_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return default
    return default


def _to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(float(value))
        except ValueError:
            return default
    return default


def _as_dict(value: object) -> dict[str, object]:
    if not isinstance(value, dict):
        return {}
    value_dict = cast(dict[object, object], value)
    out: dict[str, object] = {}
    for key, item in value_dict.items():
        if isinstance(key, str):
            out[key] = item
    return out


@dataclass
class CompositeScoreConfig:
    task_success_weight: float
    dialogue_quality_weight: float

    def __post_init__(self) -> None:
        if self.task_success_weight < 0 or self.dialogue_quality_weight < 0:
            raise ValueError("Weights must not be negative")
        if abs((self.task_success_weight + self.dialogue_quality_weight) - 1.0) > 1e-9:
            raise ValueError("Weights must sum to 1.0")

    @classmethod
    def default(cls) -> "CompositeScoreConfig":
        return cls(task_success_weight=0.6, dialogue_quality_weight=0.4)


def compute_composite_score(
    task_score: float,
    dialogue_quality: float,
    config: CompositeScoreConfig,
    *,
    empathy_score: float = 0.0,
    accuracy_score: float = 0.0,
) -> CompositeScoreResult:
    task_success_score = _clamp01(_to_float(task_score))
    dialogue_quality_score = _clamp01(_to_float(dialogue_quality))
    final_score = _clamp01(
        config.task_success_weight * task_success_score
        + config.dialogue_quality_weight * dialogue_quality_score
    )

    return {
        "final_score": final_score,
        "task_success_score": task_success_score,
        "dialogue_quality_score": dialogue_quality_score,
        "empathy_score": _clamp01(_to_float(empathy_score)),
        "accuracy_score": _clamp01(_to_float(accuracy_score)),
        "component_weights": {
            "task_success": config.task_success_weight,
            "dialogue_quality": config.dialogue_quality_weight,
        },
    }


def _report_to_dict(
    report: dict[str, object] | EvaluableComplianceReport,
) -> dict[str, object]:
    if isinstance(report, EvaluableComplianceReport):
        return {
            "case_id": report.case_id,
            "compliance_score": report.compliance_score,
            "violations": report.violations,
            "mandatory_actions": report.mandatory_actions,
            "performed_actions": report.performed_actions,
            "satisfied_actions": report.satisfied_actions,
            "evaluable_actions": report.evaluable_actions,
            "observability_index": report.observability_index,
            "evidence_summary": report.evidence_summary,
            "notes": report.notes,
        }
    return report


def build_extended_report(
    compliance_report: dict[str, object] | EvaluableComplianceReport,
    dialogue_result: dict[str, object] | None,
    quality_result: dict[str, object] | None,
    config: CompositeScoreConfig,
) -> ExtendedReportEntry:
    compliance_report = _report_to_dict(compliance_report)
    compliance_score = _clamp01(_to_float(compliance_report.get("compliance_score", 0.0)))

    empathy_score = 0.0
    accuracy_score = 0.0
    dialogue_quality_score = 0.0

    if isinstance(quality_result, dict):
        empathy = _as_dict(quality_result.get("empathy", {}))
        if empathy:
            empathy_score = _clamp01(_to_float(empathy.get("empathy_score", 0.0)))

        accuracy = _as_dict(quality_result.get("accuracy", {}))
        if accuracy:
            accuracy_score = _clamp01(_to_float(accuracy.get("accuracy_score", 0.0)))

        dialogue_quality_score = _clamp01(
            _to_float(quality_result.get("composite_quality", 0.0))
        )

    dialogue_act_summary: dict[str, int] = {}
    empathy_method = "unknown"
    accuracy_weighted_score = accuracy_score
    if isinstance(dialogue_result, dict):
        raw_summary = _as_dict(dialogue_result.get("act_summary", {}))
        if raw_summary:
            dialogue_act_summary = {
                str(key): _to_int(value)
                for key, value in raw_summary.items()
            }

    if isinstance(quality_result, dict):
        empathy = _as_dict(quality_result.get("empathy", {}))
        if empathy:
            method = empathy.get("method")
            if isinstance(method, str) and method.strip():
                empathy_method = method.strip().lower()
        accuracy = _as_dict(quality_result.get("accuracy", {}))
        if accuracy:
            accuracy_weighted_score = _clamp01(
                _to_float(accuracy.get("weighted_score", accuracy_score), accuracy_score)
            )

    composite_score = _clamp01(
        config.task_success_weight * compliance_score
        + config.dialogue_quality_weight * dialogue_quality_score
    )

    case_id = compliance_report.get("case_id", "unknown")
    case_id_str = str(case_id) if case_id is not None else "unknown"

    raw_violations = compliance_report.get("violations", [])
    violations: list[dict[str, object]] = []
    if isinstance(raw_violations, list):
        for item in cast(list[object], raw_violations):
            normalized = _as_dict(item)
            if normalized:
                violations.append(normalized)

    return {
        "case_id": case_id_str,
        "compliance_score": compliance_score,
        "empathy_score": empathy_score,
        "accuracy_score": accuracy_score,
        "dialogue_quality_score": dialogue_quality_score,
        "composite_score": composite_score,
        "dialogue_act_summary": dialogue_act_summary,
        "violations": violations,
        "empathy_method": empathy_method,
        "accuracy_weighted_score": accuracy_weighted_score,
    }


def summarize_extended_reports(reports: list[ExtendedReportEntry]) -> dict[str, float | int]:
    total_cases = len(reports)
    if total_cases == 0:
        return {
            "avg_composite": 0.0,
            "avg_empathy": 0.0,
            "avg_accuracy": 0.0,
            "avg_dialogue_quality": 0.0,
            "total_cases": 0,
        }

    avg_composite = sum(report["composite_score"] for report in reports) / total_cases
    avg_empathy = sum(report["empathy_score"] for report in reports) / total_cases
    avg_accuracy = sum(report["accuracy_score"] for report in reports) / total_cases
    avg_dialogue_quality = (
        sum(report["dialogue_quality_score"] for report in reports)
        / total_cases
    )

    return {
        "avg_composite": avg_composite,
        "avg_empathy": avg_empathy,
        "avg_accuracy": avg_accuracy,
        "avg_dialogue_quality": avg_dialogue_quality,
        "total_cases": total_cases,
    }


def render_dashboard_report(
    reports: list[ExtendedReportEntry],
    config: CompositeScoreConfig,
) -> DashboardReport:
    total_cases = len(reports)
    header = f"HealthBench Extended Evaluation — {total_cases} cases"

    avg_compliance = (
        sum(_to_float(report.get("compliance_score", 0.0)) for report in reports) / total_cases
        if total_cases
        else 0.0
    )
    avg_empathy = (
        sum(_to_float(report.get("empathy_score", 0.0)) for report in reports) / total_cases
        if total_cases
        else 0.0
    )
    avg_accuracy = (
        sum(_to_float(report.get("accuracy_score", 0.0)) for report in reports) / total_cases
        if total_cases
        else 0.0
    )
    avg_weighted_accuracy = (
        sum(
            _to_float(report.get("accuracy_weighted_score", report.get("accuracy_score", 0.0)))
            for report in reports
        )
        / total_cases
        if total_cases
        else 0.0
    )
    avg_dialogue_quality = (
        sum(_to_float(report.get("dialogue_quality_score", 0.0)) for report in reports) / total_cases
        if total_cases
        else 0.0
    )
    avg_composite = (
        sum(_to_float(report.get("composite_score", 0.0)) for report in reports) / total_cases
        if total_cases
        else 0.0
    )
    total_violations = sum(len(cast(list[object], report.get("violations", []))) for report in reports)

    empathy_method_counts = {"keyword": 0, "hybrid": 0, "other": 0}
    for report in reports:
        method_raw = report.get("empathy_method", "unknown")
        method = str(method_raw).strip().lower()
        if method == "keyword":
            empathy_method_counts["keyword"] += 1
        elif method == "hybrid":
            empathy_method_counts["hybrid"] += 1
        else:
            empathy_method_counts["other"] += 1

    dialogue_act_counts: dict[str, int] = {}
    for report in reports:
        for act, count in report.get("dialogue_act_summary", {}).items():
            dialogue_act_counts[act] = dialogue_act_counts.get(act, 0) + _to_int(count)
    act_distribution = ", ".join(
        f"{act}:{count}" for act, count in sorted(dialogue_act_counts.items())
    ) or "none"

    sections = [
        {
            "title": "Compliance Overview",
            "content": (
                f"Average compliance: {avg_compliance:.3f}\n"
                f"Total violations: {total_violations}"
            ),
        },
        {
            "title": "Empathy Assessment",
            "content": (
                f"Average empathy: {avg_empathy:.3f}\n"
                f"Method distribution - keyword: {empathy_method_counts['keyword']}, "
                f"hybrid: {empathy_method_counts['hybrid']}, other: {empathy_method_counts['other']}"
            ),
        },
        {
            "title": "Accuracy Assessment",
            "content": (
                f"Average rubric accuracy: {avg_accuracy:.3f}\n"
                f"Average weighted accuracy: {avg_weighted_accuracy:.3f}"
            ),
        },
        {
            "title": "Dialogue Quality",
            "content": (
                f"Average dialogue quality: {avg_dialogue_quality:.3f}\n"
                f"Dialogue act distribution: {act_distribution}"
            ),
        },
        {
            "title": "Composite Score",
            "content": (
                "Weighted formula: "
                f"{config.task_success_weight:.2f}*compliance + "
                f"{config.dialogue_quality_weight:.2f}*dialogue_quality\n"
                f"Average final composite: {avg_composite:.3f}"
            ),
        },
    ]

    summary_table: list[dict[str, object]] = [
        {
            "case_id": report.get("case_id", "unknown"),
            "compliance": _to_float(report.get("compliance_score", 0.0)),
            "empathy": _to_float(report.get("empathy_score", 0.0)),
            "accuracy": _to_float(report.get("accuracy_score", 0.0)),
            "dialogue_quality": _to_float(report.get("dialogue_quality_score", 0.0)),
            "composite": _to_float(report.get("composite_score", 0.0)),
            "violations": len(cast(list[object], report.get("violations", []))),
        }
        for report in reports
    ]

    footer = (
        "Notes: Composite score uses configured weights "
        f"(task_success={config.task_success_weight:.2f}, "
        f"dialogue_quality={config.dialogue_quality_weight:.2f})."
    )

    return {
        "header": header,
        "sections": sections,
        "summary_table": summary_table,
        "footer": footer,
    }


def _format_cell(value: object) -> str:
    if isinstance(value, float):
        return f"{value:.3f}"
    return str(value)


def render_dashboard_text(report: DashboardReport) -> str:
    lines: list[str] = [report["header"], ""]

    for section in report["sections"]:
        title = str(section.get("title", "")).upper()
        content = str(section.get("content", ""))
        lines.append(f"=== {title} ===")
        lines.append(content)
        lines.append("")

    lines.append("=== SUMMARY TABLE ===")
    rows = report["summary_table"]
    if not rows:
        lines.append("(no cases)")
    else:
        column_order = [
            "case_id",
            "compliance",
            "empathy",
            "accuracy",
            "dialogue_quality",
            "composite",
            "violations",
        ]
        headers = {
            "case_id": "Case",
            "compliance": "Compliance",
            "empathy": "Empathy",
            "accuracy": "Accuracy",
            "dialogue_quality": "DialogueQ",
            "composite": "Composite",
            "violations": "Violations",
        }
        widths = {
            col: max(
                len(headers[col]),
                *(len(_format_cell(row.get(col, ""))) for row in rows),
            )
            for col in column_order
        }

        header_row = " | ".join(headers[col].ljust(widths[col]) for col in column_order)
        separator_row = "-+-".join("-" * widths[col] for col in column_order)
        lines.append(header_row)
        lines.append(separator_row)
        for row in rows:
            lines.append(
                " | ".join(
                    _format_cell(row.get(col, "")).ljust(widths[col])
                    for col in column_order
                )
            )

    lines.append("")
    lines.append(report["footer"])
    return "\n".join(lines)


def flag_cases_for_review(
    reports: list[ExtendedReportEntry],
    config: HITLConfig | None = None,
) -> list[HITLFlag]:
    if config is None:
        config = HITLConfig()

    flags: list[HITLFlag] = []
    for report in reports:
        case_id = str(report.get("case_id", "unknown"))
        composite_score = _clamp01(_to_float(report.get("composite_score", 0.0)))
        empathy_score = _clamp01(_to_float(report.get("empathy_score", 0.0)))
        accuracy_score = _clamp01(_to_float(report.get("accuracy_score", 0.0)))
        violations = cast(list[object], report.get("violations", []))

        if composite_score < config.low_confidence_threshold:
            flags.append(
                {
                    "case_id": case_id,
                    "reason": "low_confidence",
                    "confidence": _clamp01(1.0 - composite_score),
                    "suggested_action": "Perform full manual review of clinical reasoning and safety.",
                }
            )

        divergence = abs(empathy_score - accuracy_score)
        if divergence > config.high_divergence_threshold:
            flags.append(
                {
                    "case_id": case_id,
                    "reason": "metric_divergence",
                    "confidence": _clamp01(divergence),
                    "suggested_action": "Audit communication-quality mismatch and recalibrate scoring.",
                }
            )

        if config.flag_low_empathy and empathy_score < 0.2 and accuracy_score > 0.7:
            flags.append(
                {
                    "case_id": case_id,
                    "reason": "empathy_gap",
                    "confidence": _clamp01(accuracy_score - empathy_score),
                    "suggested_action": "Request human review for bedside manner and patient communication.",
                }
            )

        if config.flag_high_violations and len(violations) >= 3:
            flags.append(
                {
                    "case_id": case_id,
                    "reason": "high_violations",
                    "confidence": _clamp01(len(violations) / 5.0),
                    "suggested_action": "Escalate to clinical safety reviewer for protocol adherence checks.",
                }
            )

    return flags
