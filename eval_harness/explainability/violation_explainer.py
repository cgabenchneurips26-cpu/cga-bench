"""
ViolationExplainer: Template-based clinical explanation generator for violations.
No LLM dependency — purely template + CPG graph data.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Optional

import yaml

logger = logging.getLogger(__name__)

from cga_bench.cpg_model.schemas.base import (
    HarmSeverity,
    ViolationEvent,
    ViolationType,
)

# ---------------------------------------------------------------------------
# Severity classification
# ---------------------------------------------------------------------------

# HarmSeverity -> explainability severity label
_HARM_TO_SEVERITY: dict[str, str] = {
    HarmSeverity.MINOR: "LOW",
    HarmSeverity.MODERATE: "MODERATE",
    HarmSeverity.MAJOR: "HIGH",
    HarmSeverity.SEVERE: "CRITICAL",
    HarmSeverity.CATASTROPHIC: "CRITICAL",
}

# ViolationType overrides for the explainability severity label
# (applied on top of harm_severity when the type forces a higher severity)
_TYPE_MIN_SEVERITY: dict[str, str] = {
    ViolationType.OMISSION: "CRITICAL",
    ViolationType.COMMISSION: "CRITICAL",
    ViolationType.TIMING: None,   # determined by delay ratio below
    ViolationType.SEQUENCE: "MODERATE",
    ViolationType.DEVIATION: "LOW",
}

_SEVERITY_ORDER = ["INFORMATIONAL", "LOW", "MODERATE", "HIGH", "CRITICAL"]


def _max_severity(a: str, b: Optional[str]) -> str:
    if b is None:
        return a
    return a if _SEVERITY_ORDER.index(a) >= _SEVERITY_ORDER.index(b) else b


def _classify_severity(violation: ViolationEvent) -> str:
    """Classify explainability severity from violation metadata."""
    base = _HARM_TO_SEVERITY.get(violation.harm_severity, "MODERATE")

    vtype = violation.violation_type

    if vtype == ViolationType.TIMING:
        # Timing: check delay ratio
        if (
            violation.expected_deadline is not None
            and violation.actual_time is not None
            and violation.expected_deadline > 0
        ):
            delay = violation.actual_time - violation.expected_deadline
            ratio = delay / violation.expected_deadline
            if ratio > 0.5:
                timing_sev = "HIGH"
            else:
                timing_sev = "MODERATE"
        else:
            timing_sev = "MODERATE"
        return _max_severity(base, timing_sev)

    type_min = _TYPE_MIN_SEVERITY.get(vtype)
    return _max_severity(base, type_min)


# ---------------------------------------------------------------------------
# What-happened templates
# ---------------------------------------------------------------------------

def _what_happened(violation: ViolationEvent) -> str:
    vtype = violation.violation_type
    action = violation.action_involved or "unknown action"
    expected = violation.expected_action or "required action"
    deadline = violation.expected_deadline
    actual = violation.actual_time

    if vtype == ViolationType.TIMING:
        if deadline is not None and actual is not None:
            delay = actual - deadline
            return (
                f"Action '{action}' was performed at {actual:.0f}min, "
                f"{delay:.0f}min after the recommended deadline of {deadline:.0f}min."
            )
        return f"Action '{action}' was performed outside the recommended time window."

    if vtype == ViolationType.OMISSION:
        return (
            f"Mandatory action '{expected}' was not performed. "
            f"This action is required by {violation.guideline_reference}."
        )

    if vtype == ViolationType.COMMISSION:
        return (
            f"Forbidden action '{action}' was performed. "
            f"This action is contraindicated per {violation.guideline_reference}."
        )

    if vtype == ViolationType.SEQUENCE:
        desc = violation.description or ""
        return (
            f"Action '{action}' was performed before required prerequisite actions. "
            + (desc if desc else "")
        ).strip()

    if vtype == ViolationType.DEVIATION:
        return (
            f"Action '{action}' is outside the guideline-specified allowed actions "
            f"for this clinical context."
        )

    return violation.description or "A clinical guideline violation occurred."


# ---------------------------------------------------------------------------
# Clinical significance templates (domain hints from guideline_reference)
# ---------------------------------------------------------------------------

_DOMAIN_HINTS_FALLBACK: list[tuple[list[str], str]] = [
    (
        ["sepsis", "ssc", "surviving sepsis"],
        "In sepsis, each hour of delay in antibiotics/vasopressors is associated with "
        "increased mortality (OR 1.09–1.14 per hour).",
    ),
    (
        ["stemi", "chest pain", "aha_chest", "aha chest", "heart"],
        "In STEMI, door-to-balloon time directly correlates with myocardial salvage "
        "and mortality.",
    ),
    (
        ["dka", "diabetic ketoacidosis"],
        "In DKA, starting insulin before potassium correction risks "
        "life-threatening hypokalemia.",
    ),
    (
        ["stroke", "tpa", "alteplase", "aha_stroke"],
        "In acute stroke, tPA efficacy decreases significantly with each minute of delay "
        "(time is brain).",
    ),
    (
        ["aki", "contrast", "kdigo"],
        "In contrast-induced AKI, early identification and volume expansion are key to "
        "preventing progressive renal injury.",
    ),
    (
        ["heart failure", "aha_heart", "chf"],
        "In acute heart failure, optimizing preload and afterload early reduces "
        "end-organ damage and length of stay.",
    ),
    (
        ["pneumonia", "cap"],
        "In community-acquired pneumonia, timely antibiotic administration reduces "
        "in-hospital mortality and length of stay.",
    ),
    (
        ["pulmonary embolism", "pe", "anticoagulation"],
        "In pulmonary embolism, delayed anticoagulation increases risk of clot "
        "propagation and hemodynamic compromise.",
    ),
]

_DOMAIN_HINTS_YAML = Path(__file__).resolve().parent / "domain_hints.yaml"


def _load_domain_hints() -> list[tuple[list[str], str]]:
    """Load domain hints from YAML file, falling back to hardcoded list if not found."""
    if not _DOMAIN_HINTS_YAML.is_file():
        return _DOMAIN_HINTS_FALLBACK
    try:
        with open(_DOMAIN_HINTS_YAML, encoding="utf-8") as f:
            data = yaml.safe_load(f)
        hints = []
        for entry in data.get("hints", []):
            keywords = entry.get("keywords", [])
            significance = entry.get("significance", "")
            if keywords and significance:
                hints.append((keywords, significance.strip()))
        return hints if hints else _DOMAIN_HINTS_FALLBACK
    except Exception:
        return _DOMAIN_HINTS_FALLBACK


_DOMAIN_HINTS: list[tuple[list[str], str]] = _load_domain_hints()


def _clinical_significance(violation: ViolationEvent) -> str:
    ref_lower = (violation.guideline_reference or "").lower()
    desc_lower = (violation.description or "").lower()
    combined = ref_lower + " " + desc_lower

    for keywords, significance in _DOMAIN_HINTS:
        if any(kw in combined for kw in keywords):
            return significance

    # Fallback by violation type
    vtype = violation.violation_type
    if vtype == ViolationType.OMISSION:
        return (
            "Omission of mandatory clinical actions can result in delayed treatment, "
            "worsening patient outcomes, and increased mortality risk."
        )
    if vtype == ViolationType.COMMISSION:
        return (
            "Performance of contraindicated actions may cause direct patient harm "
            "and violates evidence-based safety standards."
        )
    if vtype == ViolationType.TIMING:
        return (
            "Delayed interventions reduce treatment efficacy and may allow "
            "disease progression during the critical treatment window."
        )
    if vtype == ViolationType.SEQUENCE:
        return (
            "Incorrect action sequencing can negate the benefit of individual "
            "interventions and may introduce additional clinical risks."
        )
    return (
        "Deviation from guideline-specified actions may compromise patient safety "
        "and reduce adherence to evidence-based standards of care."
    )


# ---------------------------------------------------------------------------
# Recommendation templates
# ---------------------------------------------------------------------------

def _recommendation(violation: ViolationEvent) -> str:
    vtype = violation.violation_type
    action = violation.action_involved or "the action"
    expected = violation.expected_action or "the required action"
    deadline = violation.expected_deadline

    if vtype == ViolationType.TIMING:
        deadline_str = f"{deadline:.0f}min" if deadline is not None else "the recommended window"
        return (
            f"Ensure '{action}' is initiated within {deadline_str} of patient presentation. "
            f"Use clinical decision support or bundled order sets to reduce delays."
        )
    if vtype == ViolationType.OMISSION:
        return (
            f"Perform '{expected}' as part of the standard protocol. "
            f"Consider checklist-driven order sets to prevent omissions."
        )
    if vtype == ViolationType.COMMISSION:
        return (
            f"Avoid '{action}' in this clinical context. "
            f"Review contraindication criteria per {violation.guideline_reference} before ordering."
        )
    if vtype == ViolationType.SEQUENCE:
        return (
            "Review the required action sequence per the guideline before proceeding. "
            "Ensure prerequisite steps are completed before initiating subsequent interventions."
        )
    if vtype == ViolationType.DEVIATION:
        return (
            f"Substitute '{action}' with guideline-approved alternatives. "
            f"If deviation is clinically justified, document the rationale explicitly."
        )
    return "Review the relevant guideline and adjust clinical decision-making accordingly."


# ---------------------------------------------------------------------------
# CPG graph loader
# ---------------------------------------------------------------------------

_DEFAULT_CPG_GRAPHS_DIR = (
    Path(__file__).resolve().parent.parent.parent / "cpg_model" / "graphs"
)


class _CPGIndex:
    """Lazy-loaded index of CPG nodes keyed by action name -> source_quote."""

    def __init__(self, graphs_dir: str) -> None:
        self._graphs_dir = graphs_dir
        self._index: dict[str, dict[str, Any]] = {}  # action -> {source_quote, source_page, ...}
        self._loaded = False

    def _load(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not os.path.isdir(self._graphs_dir):
            logger.warning(
                "CPG graphs directory not found: %s — source quotes will be unavailable.",
                self._graphs_dir,
            )
            return
        for fname in os.listdir(self._graphs_dir):
            if not fname.endswith(".yaml") and not fname.endswith(".yml"):
                continue
            fpath = os.path.join(self._graphs_dir, fname)
            try:
                with open(fpath, encoding="utf-8") as f:
                    data = yaml.safe_load(f)
            except Exception:
                continue
            nodes = data.get("nodes", {}) if isinstance(data, dict) else {}
            if not isinstance(nodes, dict):
                continue
            for node_id, node in nodes.items():
                if not isinstance(node, dict):
                    continue
                source_quote = node.get("source_quote") or node.get("source_quotes")
                source_page = node.get("source_page")
                source_guideline = node.get("source_guideline")
                # Index by node_id and by each action in mandatory_actions + allowed_actions
                meta = {
                    "source_quote": source_quote,
                    "source_page": source_page,
                    "source_guideline": source_guideline,
                }
                self._index[node_id] = meta
                for key in ("mandatory_actions", "allowed_actions", "forbidden_actions"):
                    actions = node.get(key) or []
                    if isinstance(actions, list):
                        for act in actions:
                            if isinstance(act, str) and act not in self._index:
                                self._index[act] = meta

    def get(self, key: str) -> dict[str, Any]:
        self._load()
        return self._index.get(key, {})


# ---------------------------------------------------------------------------
# ViolationExplainer
# ---------------------------------------------------------------------------

class ViolationExplainer:
    """Template-based clinical explanation for violations. No LLM dependency."""

    def __init__(self, cpg_graphs_dir: str = str(_DEFAULT_CPG_GRAPHS_DIR)) -> None:
        self._cpg = _CPGIndex(cpg_graphs_dir)

    def _lookup_source_quote(self, violation: ViolationEvent) -> Optional[str]:
        """Attempt to find a source_quote from CPG graphs for the relevant action."""
        candidates = [
            violation.action_involved,
            violation.expected_action,
            violation.node_at_violation,
        ]
        for key in candidates:
            if not key:
                continue
            meta = self._cpg.get(key)
            sq = meta.get("source_quote")
            if sq:
                # source_quote may be a list (source_quotes field)
                if isinstance(sq, list):
                    return " / ".join(str(s) for s in sq if s)
                return str(sq)
        return None

    def explain(self, violation: ViolationEvent) -> dict[str, Any]:
        """Generate structured clinical explanation for a single violation."""
        severity = _classify_severity(violation)
        source_quote = self._lookup_source_quote(violation)

        clinical_explanation: dict[str, Any] = {
            "what_happened": _what_happened(violation),
            "clinical_significance": _clinical_significance(violation),
            "guideline_reference": violation.guideline_reference,
            "source_quote": source_quote,
            "severity": severity,
            "recommendation": _recommendation(violation),
        }

        return {
            "violation_id": violation.violation_id,
            "type": violation.violation_type.value.upper()
            if hasattr(violation.violation_type, "value")
            else str(violation.violation_type).upper(),
            "action": violation.action_involved or violation.expected_action,
            "clinical_explanation": clinical_explanation,
        }

    def explain_all(self, violations: list[ViolationEvent]) -> list[dict[str, Any]]:
        """Explain all violations in an episode."""
        return [self.explain(v) for v in violations]
