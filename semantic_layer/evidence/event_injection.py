from __future__ import annotations

from collections.abc import Mapping, Sequence
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
import random
from typing import TypedDict, cast


class EventSeverity(str, Enum):
    MINOR = "minor"
    MODERATE = "moderate"
    SEVERE = "severe"
    CRITICAL = "critical"


class InjectedEvent(TypedDict):
    event_id: str
    event_type: str
    severity: str
    description: str
    state_changes: dict[str, object]
    expected_response: str
    timestamp_minutes: float


@dataclass
class EventInjectionConfig:
    enabled: bool = False
    max_events_per_episode: int = 3
    min_interval_minutes: float = 10.0
    severity_distribution: dict[str, float] = field(
        default_factory=lambda: {
            "minor": 0.4,
            "moderate": 0.3,
            "severe": 0.2,
            "critical": 0.1,
        }
    )

    @classmethod
    def default(cls) -> EventInjectionConfig:
        return cls()

    @classmethod
    def stress_test(cls) -> EventInjectionConfig:
        return cls(enabled=True, max_events_per_episode=5, min_interval_minutes=5.0)


_EVENT_LIBRARY: list[InjectedEvent] = [
    {
        "event_id": "allergy_pcn",
        "event_type": "allergy_discovery",
        "severity": "severe",
        "description": "Patient reports severe penicillin allergy (anaphylaxis history)",
        "state_changes": {"allergies": ["penicillin"]},
        "expected_response": "switch_to_alternative_antibiotic",
        "timestamp_minutes": 0,
    },
    {
        "event_id": "equip_fail_lab",
        "event_type": "equipment_failure",
        "severity": "moderate",
        "description": "Blood gas analyzer malfunction - results delayed 30 minutes",
        "state_changes": {"lab_delay_minutes": 30},
        "expected_response": "use_clinical_assessment_pending_labs",
        "timestamp_minutes": 0,
    },
    {
        "event_id": "vital_crash_bp",
        "event_type": "vital_deterioration",
        "severity": "critical",
        "description": "Sudden blood pressure drop: MAP 45 mmHg",
        "state_changes": {"map_mmhg": 45.0},
        "expected_response": "start_vasopressor_norepinephrine",
        "timestamp_minutes": 0,
    },
    {
        "event_id": "new_symptom_chest",
        "event_type": "new_symptom",
        "severity": "severe",
        "description": "Patient develops acute chest pain with ST elevation on monitor",
        "state_changes": {"chest_pain": True, "st_elevation": True},
        "expected_response": "activate_cath_lab",
        "timestamp_minutes": 0,
    },
    {
        "event_id": "drug_interaction",
        "event_type": "drug_interaction",
        "severity": "moderate",
        "description": "Pharmacist alerts: current medication interacts with ordered drug",
        "state_changes": {"drug_interaction_alert": True},
        "expected_response": "review_medication_order",
        "timestamp_minutes": 0,
    },
    {
        "event_id": "family_request",
        "event_type": "family_request",
        "severity": "minor",
        "description": "Family requests second opinion before invasive procedure",
        "state_changes": {"family_concern": True},
        "expected_response": "discuss_with_family_and_document",
        "timestamp_minutes": 0,
    },
]

_VITAL_KEYS = {
    "heart_rate",
    "blood_pressure_systolic",
    "blood_pressure_diastolic",
    "respiratory_rate",
    "temperature",
    "oxygen_saturation",
    "map_mmhg",
}


def _timestamp_from_mapping(payload: Mapping[str, object]) -> float:
    timestamp = payload.get("timestamp_minutes")
    if isinstance(timestamp, (int, float)):
        return float(timestamp)
    return 0.0


def _pick_weighted_event(rng: random.Random, available: list[InjectedEvent], weights: dict[str, float]) -> InjectedEvent:
    weighted = [max(0.0, float(weights.get(e["severity"], 1.0))) for e in available]
    if sum(weighted) == 0:
        return available[rng.randrange(len(available))]
    idx = rng.choices(range(len(available)), weights=weighted, k=1)[0]
    return available[idx]


def select_events(
    config: EventInjectionConfig,
    episode_duration_minutes: float,
    seed: int | None = None,
) -> list[InjectedEvent]:
    if not config.enabled:
        return []
    if episode_duration_minutes <= 0 or config.max_events_per_episode <= 0:
        return []

    rng = random.Random(seed)
    min_interval = max(0.0, config.min_interval_minutes)
    max_by_time = int(episode_duration_minutes // min_interval) + 1 if min_interval > 0 else config.max_events_per_episode
    target_count = min(config.max_events_per_episode, len(_EVENT_LIBRARY), max_by_time)
    if target_count <= 0:
        return []

    available: list[InjectedEvent] = [deepcopy(e) for e in _EVENT_LIBRARY]
    selected: list[InjectedEvent] = []
    for _ in range(target_count):
        event = _pick_weighted_event(rng, available, config.severity_distribution)
        selected.append(event)
        available = [e for e in available if e["event_id"] != event["event_id"]]
        if not available:
            break

    n = len(selected)
    if n == 0:
        return []

    if min_interval > 0:
        slack = max(0.0, episode_duration_minutes - ((n - 1) * min_interval))
        start = rng.uniform(0.0, slack) if slack > 0 else 0.0
        timestamps = [min(episode_duration_minutes, start + i * min_interval) for i in range(n)]
    else:
        timestamps = sorted(rng.uniform(0.0, episode_duration_minutes) for _ in range(n))

    out: list[InjectedEvent] = []
    for event, ts in zip(selected, timestamps):
        event_copy = deepcopy(event)
        event_copy["timestamp_minutes"] = float(round(ts, 4))
        out.append(event_copy)
    out.sort(key=lambda e: e["timestamp_minutes"])
    return out


def apply_event_to_state(
    patient_state: Mapping[str, object],
    event: InjectedEvent,
    current_time_minutes: float,
) -> dict[str, object]:
    new_state: dict[str, object] = dict(deepcopy(patient_state))
    changes = event.get("state_changes", {})
    vitals_obj = new_state.get("vitals")
    vitals = cast(dict[str, object], vitals_obj) if isinstance(vitals_obj, dict) else None

    for key, value in changes.items():
        if key == "allergies" and isinstance(value, list):
            existing = new_state.get("allergies")
            existing_list = cast(list[object], existing) if isinstance(existing, list) else []
            value_list = cast(list[object], value)
            for allergy in value_list:
                if allergy not in existing_list:
                    existing_list.append(allergy)
            new_state["allergies"] = existing_list
            continue

        if key in _VITAL_KEYS and vitals is not None:
            vitals[key] = value
            continue

        new_state[key] = value

    new_state["last_injected_event_id"] = event["event_id"]
    new_state["last_injected_event_time_minutes"] = float(current_time_minutes)
    return new_state


@dataclass
class PlanRepairMetrics:
    total_events: int = 0
    correct_responses: int = 0
    response_time_minutes: list[float] = field(default_factory=list)
    safety_violations_post_event: int = 0

    @property
    def repair_success_rate(self) -> float:
        return self.correct_responses / max(self.total_events, 1)

    @property
    def avg_response_time(self) -> float:
        return sum(self.response_time_minutes) / max(len(self.response_time_minutes), 1)

    def summary(self) -> dict[str, float | int]:
        return {
            "total_events": self.total_events,
            "correct_responses": self.correct_responses,
            "repair_success_rate": round(self.repair_success_rate, 4),
            "avg_response_time_minutes": round(self.avg_response_time, 4),
            "safety_violations_post_event": self.safety_violations_post_event,
        }


def _extract_actions(response: Mapping[str, object]) -> list[str]:
    actions: list[str] = []
    action_id = response.get("action_id")
    if isinstance(action_id, str):
        actions.append(action_id)

    payload = response.get("actions")
    if isinstance(payload, list):
        payload_list = cast(list[object], payload)
        for item_obj in payload_list:
            item = item_obj
            if isinstance(item, str):
                actions.append(item)
            elif isinstance(item, dict):
                nested_action_id = cast(dict[str, object], item).get("action_id")
                if isinstance(nested_action_id, str):
                    actions.append(nested_action_id)

    return actions


def evaluate_plan_repair(
    events: Sequence[InjectedEvent],
    agent_responses: Sequence[Mapping[str, object]],
) -> PlanRepairMetrics:
    metrics = PlanRepairMetrics(total_events=len(events))
    if not events:
        return metrics

    timed_responses: list[Mapping[str, object]] = []
    for response in agent_responses:
        timestamp = response.get("timestamp_minutes")
        if isinstance(timestamp, (int, float)):
            timed_responses.append(response)

    ordered_responses = sorted(
        timed_responses,
        key=_timestamp_from_mapping,
    )

    for event in events:
        event_time = float(event["timestamp_minutes"])
        expected = event.get("expected_response", "")
        post: list[Mapping[str, object]] = []
        for response in ordered_responses:
            ts = cast(int | float, response.get("timestamp_minutes"))
            if float(ts) >= event_time:
                post.append(response)
        if not post:
            continue

        first_response = post[0]
        metrics.response_time_minutes.append(
            float(cast(int | float, first_response.get("timestamp_minutes"))) - event_time
        )
        actions = _extract_actions(first_response)
        if expected and expected in actions:
            metrics.correct_responses += 1

        if bool(first_response.get("safety_violation", False)):
            metrics.safety_violations_post_event += 1

    return metrics
