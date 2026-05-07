from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import TypedDict, cast

logger = logging.getLogger(__name__)


class CounterfactualExplanation(TypedDict):
    condition: dict[str, object]
    original_action: str
    counterfactual_action: str
    reason: str
    sensitivity: float


@dataclass
class CounterfactualConfig:
    perturbation_range: float = 0.2
    max_counterfactuals: int = 5
    min_sensitivity: float = 0.1

    @classmethod
    def default(cls) -> CounterfactualConfig:
        return cls()


@dataclass
class ThresholdRule:
    vital: str
    threshold: float
    operator: str
    action_if_true: str
    action_if_false: str
    guideline_id: str
    source: str


_FALLBACK_THRESHOLD_RULES = [
    ThresholdRule("map_mmhg", 65.0, "lt", "start_vasopressor_norepinephrine", "monitor_map", "ssc_sepsis_hour1", "SSC 2021"),
    ThresholdRule("lactate", 2.0, "gt", "remeasure_lactate_if_elevated", "monitor_lactate", "ssc_sepsis_hour1", "SSC 2021"),
    ThresholdRule("heart_rate", 100.0, "gt", "assess_tachycardia", "monitor_heart_rate", "aha_chest_pain", "AHA 2021"),
    ThresholdRule("oxygen_saturation", 94.0, "lt", "give_supplemental_oxygen", "monitor_spo2", "universal", "General"),
    ThresholdRule("blood_glucose", 250.0, "gt", "start_insulin_drip", "monitor_glucose", "ada_dka", "ADA DKA"),
    ThresholdRule("systolic_bp", 180.0, "gt", "give_antihypertensive", "monitor_bp", "aha_stroke", "AHA 2019"),
    ThresholdRule("gcs", 8.0, "le", "secure_airway", "monitor_neuro", "universal", "General"),
    ThresholdRule("temperature", 38.3, "gt", "assess_fever_source", "monitor_temperature", "ssc_sepsis_hour1", "SSC 2021"),
]

_CPG_GRAPHS_DIR = Path(__file__).resolve().parents[2] / "cpg_model" / "graphs"

_cached_auto_rules: list[ThresholdRule] | None = None


def load_all_threshold_rules(graphs_dir: Path | None = None) -> list[ThresholdRule]:
    """Scan all CPG YAML graphs and auto-extract threshold rules.

    Returns the union of fallback rules (clinically curated baselines) and
    rules extracted from precondition / conditional_next expressions in every
    ``cpg_model/graphs/*.yaml`` file.  Results are cached after the first call.
    """
    global _cached_auto_rules
    if _cached_auto_rules is not None:
        return list(_cached_auto_rules)

    target_dir = graphs_dir or _CPG_GRAPHS_DIR
    if not target_dir.is_dir():
        logger.debug("CPG graphs directory not found at %s; using fallback rules only", target_dir)
        _cached_auto_rules = list(_FALLBACK_THRESHOLD_RULES)
        return list(_cached_auto_rules)

    try:
        import yaml
    except ImportError:
        logger.debug("PyYAML not available; using fallback rules only")
        _cached_auto_rules = list(_FALLBACK_THRESHOLD_RULES)
        return list(_cached_auto_rules)

    rules: list[ThresholdRule] = list(_FALLBACK_THRESHOLD_RULES)
    seen = {
        (r.vital, r.threshold, r.operator, r.action_if_true, r.action_if_false, r.guideline_id)
        for r in rules
    }

    for yaml_path in sorted(target_dir.glob("*.yaml")):
        try:
            with yaml_path.open("r", encoding="utf-8") as fh:
                graph_data = yaml.safe_load(fh)
            if not isinstance(graph_data, dict):
                continue
            extracted = _extract_rules_from_graph(graph_data)
            for rule in extracted:
                key = (rule.vital, rule.threshold, rule.operator, rule.action_if_true, rule.action_if_false, rule.guideline_id)
                if key not in seen:
                    rules.append(rule)
                    seen.add(key)
        except Exception as exc:
            logger.debug("Skipping %s: %s", yaml_path.name, exc)

    _cached_auto_rules = rules
    return list(_cached_auto_rules)


def clear_threshold_rules_cache() -> None:
    global _cached_auto_rules
    _cached_auto_rules = None


_THRESHOLD_EXPR = re.compile(
    r"(?:state(?:\.vitals)?\.)?([a-zA-Z_][a-zA-Z0-9_]*)\s*(<=|>=|<|>)\s*(-?\d+(?:\.\d+)?)"
)


def _normalize_operator(op: str) -> str:
    return {"<": "lt", ">": "gt", "<=": "le", ">=": "ge"}.get(op, op)


def _is_true(value: float, operator: str, threshold: float) -> bool:
    if operator == "lt":
        return value < threshold
    if operator == "le":
        return value <= threshold
    if operator == "gt":
        return value > threshold
    if operator == "ge":
        return value >= threshold
    return False


def _get_vital_value(patient_state: Mapping[str, object], vital: str) -> float | None:
    direct = patient_state.get(vital)
    if isinstance(direct, (int, float)):
        return float(direct)

    vitals = patient_state.get("vitals")
    if isinstance(vitals, dict):
        vitals_map = cast(dict[str, object], vitals)
        nested = vitals_map.get(vital)
        if isinstance(nested, (int, float)):
            return float(nested)

    return None


def _extract_rules_from_graph(graph_data: Mapping[str, object]) -> list[ThresholdRule]:
    rules: list[ThresholdRule] = []

    nodes_obj = graph_data.get("nodes")
    if not isinstance(nodes_obj, dict):
        return rules
    nodes = cast(dict[str, object], nodes_obj)

    guideline_id = str(graph_data.get("graph_id", "unknown"))

    for node_obj in nodes.values():
        if not isinstance(node_obj, dict):
            continue
        node = cast(dict[str, object], node_obj)

        source = str(node.get("source_guideline", graph_data.get("guideline_name", "unknown")))
        action_true = ""
        mandatory_actions_obj = node.get("mandatory_actions")
        if isinstance(mandatory_actions_obj, list) and mandatory_actions_obj:
            mandatory_actions = cast(list[object], mandatory_actions_obj)
            action_true = str(mandatory_actions[0])
        else:
            allowed_actions_obj = node.get("allowed_actions")
            if isinstance(allowed_actions_obj, list) and allowed_actions_obj:
                allowed_actions = cast(list[object], allowed_actions_obj)
                action_true = str(allowed_actions[0])
        if not action_true:
            action_true = "take_guideline_action"

        precondition = node.get("precondition")
        if isinstance(precondition, str):
            for match in _THRESHOLD_EXPR.finditer(precondition):
                vital, op, threshold = match.groups()
                rules.append(ThresholdRule(
                    vital=vital,
                    threshold=float(threshold),
                    operator=_normalize_operator(op),
                    action_if_true=action_true,
                    action_if_false=f"monitor_{vital}",
                    guideline_id=guideline_id,
                    source=source,
                ))

        conditional_next_obj = node.get("conditional_next")
        if isinstance(conditional_next_obj, dict):
            conditional_next = cast(dict[str, object], conditional_next_obj)
            for expr in conditional_next:
                for match in _THRESHOLD_EXPR.finditer(expr):
                    vital, op, threshold = match.groups()
                    rules.append(ThresholdRule(
                        vital=vital,
                        threshold=float(threshold),
                        operator=_normalize_operator(op),
                        action_if_true=action_true,
                        action_if_false=f"monitor_{vital}",
                        guideline_id=guideline_id,
                        source=source,
                    ))

    return rules


def extract_threshold_rules(graph_data: Mapping[str, object]) -> list[ThresholdRule]:
    rules: list[ThresholdRule] = list(_FALLBACK_THRESHOLD_RULES)
    seen = {(r.vital, r.threshold, r.operator, r.action_if_true, r.action_if_false, r.guideline_id) for r in rules}

    for rule in _extract_rules_from_graph(graph_data):
        key = (rule.vital, rule.threshold, rule.operator, rule.action_if_true, rule.action_if_false, rule.guideline_id)
        if key not in seen:
            rules.append(rule)
            seen.add(key)

    return rules


def generate_counterfactuals(
    patient_state: Mapping[str, object],
    current_actions: list[str],
    rules: list[ThresholdRule],
    config: CounterfactualConfig | None = None,
) -> list[CounterfactualExplanation]:
    if not rules:
        return []

    cfg = config or CounterfactualConfig.default()
    counterfactuals: list[CounterfactualExplanation] = []

    for rule in rules:
        current_value = _get_vital_value(patient_state, rule.vital)
        if current_value is None:
            continue

        distance = abs(current_value - rule.threshold)
        window = abs(rule.threshold) * cfg.perturbation_range
        if window == 0:
            window = cfg.perturbation_range
        if distance > window:
            continue

        sensitivity = max(0.0, min(1.0, 1.0 - (distance / max(window, 1e-9))))
        if sensitivity < cfg.min_sensitivity:
            continue

        currently_true = _is_true(current_value, rule.operator, rule.threshold)
        expected_original = rule.action_if_true if currently_true else rule.action_if_false
        original_action = expected_original
        if current_actions:
            if expected_original in current_actions:
                original_action = expected_original
            elif rule.action_if_true in current_actions:
                original_action = rule.action_if_true
            elif rule.action_if_false in current_actions:
                original_action = rule.action_if_false

        counterfactual_action = rule.action_if_false if currently_true else rule.action_if_true
        epsilon = max(abs(rule.threshold) * 0.01, 0.1)
        if rule.operator in {"lt", "le"}:
            perturbed_value = rule.threshold + epsilon if currently_true else rule.threshold - epsilon
        else:
            perturbed_value = rule.threshold - epsilon if currently_true else rule.threshold + epsilon

        reason = (
            f"{rule.source}: {rule.vital} {rule.operator} {rule.threshold:g} threshold changes "
            f"recommended action from {original_action} to {counterfactual_action}."
        )
        counterfactuals.append(
            {
                "condition": {"vital": rule.vital, "value": round(perturbed_value, 2)},
                "original_action": original_action,
                "counterfactual_action": counterfactual_action,
                "reason": reason,
                "sensitivity": round(sensitivity, 4),
            }
        )

    counterfactuals.sort(key=lambda x: x["sensitivity"], reverse=True)
    return counterfactuals[: cfg.max_counterfactuals]


def format_counterfactual_text(cf: CounterfactualExplanation) -> str:
    cond = cf["condition"]
    vital_obj = cond.get("vital", "unknown_vital")
    value_obj = cond.get("value", "?")
    vital = str(vital_obj)
    value = str(value_obj)
    return (
        f"If {vital} were {value}, action would change from "
        f"{cf['original_action']} to {cf['counterfactual_action']} "
        f"(sensitivity={cf['sensitivity']:.2f})."
    )
