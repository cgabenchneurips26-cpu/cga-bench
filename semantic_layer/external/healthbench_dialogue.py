from __future__ import annotations

import re
from dataclasses import dataclass, field, replace
from enum import Enum
from typing import TypedDict


class DialogueAct(Enum):
    INFORMATION_PROVIDE = "information_provide"
    QUESTION_ASK = "question_ask"
    EMPATHY_EXPRESS = "empathy_express"
    TRIAGE_RECOMMEND = "triage_recommend"
    INSTRUCTION_GIVE = "instruction_give"
    SAFETY_WARNING = "safety_warning"
    REASSURANCE = "reassurance"
    CLARIFICATION_REQUEST = "clarification_request"


class DialogueTurn(TypedDict):
    role: str
    content: str
    acts: list[DialogueAct]
    turn_index: int


class DialogueTransition(TypedDict):
    from_goal: str
    to_goal: str
    trigger_act: str
    turn_index: int


_DEFAULT_EMPATHY_KEYWORDS = [
    "sorry",
    "understand",
    "must be",
    "i can imagine",
    "appreciate",
    "compassion",
    "worried",
    "concern",
    "thank you for sharing",
]

_DEFAULT_SAFETY_KEYWORDS = [
    "call 911",
    "emergency",
    "danger",
    "avoid",
    "do not",
    "warning",
    "caution",
    "exceeding",
]

_DEFAULT_QUESTION_PATTERNS = [
    r"\?",
    r"\bcan you tell\b",
    r"\bwhat\b",
    r"\bhow\b",
    r"\bwhen\b",
    r"\bdo you\b",
]

_INSTRUCTION_PATTERNS = [
    r"\btake\b",
    r"\bshould\b",
    r"\brecommend\b",
    r"\badvise\b",
    r"\bevery\s+\d+\s*(?:hours?|hrs?)\b",
    r"\bfollow up\b",
]

_TRIAGE_PATTERNS = [
    r"\bsee your doctor\b",
    r"\bemergency room\b",
    r"\bcall 911\b",
    r"\bseek medical\b",
    r"\burgent\b",
]

_INFO_PATTERNS = [
    r"\bresults?\b",
    r"\btest\b",
    r"\bshows?\b",
    r"\bindicates?\b",
    r"\blevels?\b",
]

_REASSURANCE_PATTERNS = [
    r"\bnormal\b",
    r"\bfine\b",
    r"\bdon't worry\b",
    r"\bnothing to worry\b",
    r"\bgood news\b",
]

_CLARIFICATION_PATTERNS = [
    r"\bcould you clarify\b",
    r"\btell me more\b",
    r"\bspecific\b",
    r"\bwhen did\b",
]

_KNOWN_CONDITIONS = [
    "diabetes",
    "hypertension",
    "asthma",
    "heart disease",
    "chronic kidney disease",
    "copd",
    "stroke",
    "migraine",
]


def _to_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _contains_any(text: str, keywords: list[str]) -> bool:
    return any(keyword in text for keyword in keywords)


def _matches_any_pattern(text: str, patterns: list[str]) -> bool:
    return any(re.search(pattern, text) is not None for pattern in patterns)


@dataclass
class DialogueActConfig:
    empathy_keywords: list[str]
    safety_keywords: list[str]
    question_patterns: list[str]

    @classmethod
    def default(cls) -> "DialogueActConfig":
        return cls(
            empathy_keywords=list(_DEFAULT_EMPATHY_KEYWORDS),
            safety_keywords=list(_DEFAULT_SAFETY_KEYWORDS),
            question_patterns=list(_DEFAULT_QUESTION_PATTERNS),
        )


@dataclass
class DialogueState:
    turn_count: int
    patient_info: dict[str, str] = field(default_factory=dict)
    detected_conditions: list[str] = field(default_factory=list)
    current_goal: str = ""
    conversation_summary: str = ""


@dataclass
class DialogueGraph:
    nodes: list[str]
    edges: list[DialogueTransition]
    current_node: str
    visit_counts: dict[str, int]

    @classmethod
    def empty(cls) -> "DialogueGraph":
        return cls(
            nodes=["initial_assessment"],
            edges=[],
            current_node="initial_assessment",
            visit_counts={"initial_assessment": 1},
        )

    def add_transition(self, to_goal: str, trigger_act: str, turn_index: int) -> "DialogueGraph":
        transition: DialogueTransition = {
            "from_goal": self.current_node,
            "to_goal": to_goal,
            "trigger_act": trigger_act,
            "turn_index": turn_index,
        }

        updated_nodes = list(self.nodes)
        if to_goal not in updated_nodes:
            updated_nodes.append(to_goal)

        updated_visit_counts = dict(self.visit_counts)
        updated_visit_counts[to_goal] = updated_visit_counts.get(to_goal, 0) + 1

        return replace(
            self,
            nodes=updated_nodes,
            edges=[*self.edges, transition],
            current_node=to_goal,
            visit_counts=updated_visit_counts,
        )


def _goal_and_trigger_from_acts(acts: list[DialogueAct], current_goal: str) -> tuple[str, str | None]:
    if DialogueAct.TRIAGE_RECOMMEND in acts:
        return "triage", DialogueAct.TRIAGE_RECOMMEND.value
    if DialogueAct.SAFETY_WARNING in acts:
        return "safety_assessment", DialogueAct.SAFETY_WARNING.value
    if DialogueAct.INSTRUCTION_GIVE in acts:
        return "treatment_plan", DialogueAct.INSTRUCTION_GIVE.value
    if DialogueAct.QUESTION_ASK in acts:
        return "information_gathering", DialogueAct.QUESTION_ASK.value
    if DialogueAct.CLARIFICATION_REQUEST in acts:
        return "information_gathering", DialogueAct.CLARIFICATION_REQUEST.value
    if DialogueAct.EMPATHY_EXPRESS in acts:
        return "rapport_building", DialogueAct.EMPATHY_EXPRESS.value
    if DialogueAct.REASSURANCE in acts:
        return "rapport_building", DialogueAct.REASSURANCE.value
    if DialogueAct.INFORMATION_PROVIDE in acts:
        return "information_delivery", DialogueAct.INFORMATION_PROVIDE.value
    return current_goal, None


def classify_dialogue_acts(utterance: str, config: DialogueActConfig) -> list[DialogueAct]:
    content = utterance.strip()
    if len(content) < 4:
        return []

    lowered = content.lower()
    acts: list[DialogueAct] = []

    if _contains_any(lowered, [keyword.lower() for keyword in config.empathy_keywords]):
        acts.append(DialogueAct.EMPATHY_EXPRESS)

    if _contains_any(lowered, [keyword.lower() for keyword in config.safety_keywords]):
        acts.append(DialogueAct.SAFETY_WARNING)

    if _matches_any_pattern(lowered, [pattern.lower() for pattern in config.question_patterns]):
        acts.append(DialogueAct.QUESTION_ASK)

    if _matches_any_pattern(lowered, _INSTRUCTION_PATTERNS):
        acts.append(DialogueAct.INSTRUCTION_GIVE)

    if _matches_any_pattern(lowered, _TRIAGE_PATTERNS):
        acts.append(DialogueAct.TRIAGE_RECOMMEND)

    if _matches_any_pattern(lowered, _INFO_PATTERNS):
        acts.append(DialogueAct.INFORMATION_PROVIDE)

    if _matches_any_pattern(lowered, _REASSURANCE_PATTERNS):
        acts.append(DialogueAct.REASSURANCE)

    if _matches_any_pattern(lowered, _CLARIFICATION_PATTERNS):
        acts.append(DialogueAct.CLARIFICATION_REQUEST)

    if not acts and "?" not in lowered and len(content.split()) >= 3:
        acts.append(DialogueAct.INFORMATION_PROVIDE)

    return acts


def _extract_conditions(text: str) -> list[str]:
    lowered = text.lower()
    found: list[str] = []
    for condition in _KNOWN_CONDITIONS:
        if condition in lowered:
            found.append(condition)
    return found


def _extract_patient_info(text: str) -> dict[str, str]:
    extracted: dict[str, str] = {}
    for match in re.finditer(r"\b([a-zA-Z_][\w\s-]{1,30})\s*:\s*([^,.;\n]{1,80})", text):
        key = match.group(1).strip().lower().replace(" ", "_")
        value = match.group(2).strip()
        if key and value:
            extracted[key] = value
    return extracted


def update_dialogue_state(state: DialogueState, turn: DialogueTurn) -> DialogueState:
    content = _to_str(turn.get("content", ""))

    updated_conditions = list(state.detected_conditions)
    existing_lower = {condition.lower() for condition in updated_conditions}
    for condition in _extract_conditions(content):
        if condition.lower() not in existing_lower:
            updated_conditions.append(condition)
            existing_lower.add(condition.lower())

    updated_patient_info = dict(state.patient_info)
    updated_patient_info.update(_extract_patient_info(content))

    summary_piece = content.strip()
    if state.conversation_summary and summary_piece:
        summary = f"{state.conversation_summary} {summary_piece}"
    else:
        summary = state.conversation_summary or summary_piece

    acts = turn.get("acts", [])
    new_goal, _ = _goal_and_trigger_from_acts(acts, state.current_goal)

    return replace(
        state,
        turn_count=state.turn_count + 1,
        patient_info=updated_patient_info,
        detected_conditions=updated_conditions,
        current_goal=new_goal,
        conversation_summary=summary,
    )


def parse_conversation_to_turns(
    prompt_turns: list[dict[str, object]], config: DialogueActConfig
) -> list[DialogueTurn]:
    turns: list[DialogueTurn] = []
    for index, prompt_turn in enumerate(prompt_turns):
        role = _to_str(prompt_turn.get("role", "")) or "unknown"
        content = _to_str(prompt_turn.get("content", ""))
        turns.append(
            {
                "role": role,
                "content": content,
                "acts": classify_dialogue_acts(content, config),
                "turn_index": index,
            }
        )
    return turns


def build_dialogue_graph(turns: list[DialogueTurn], config: DialogueActConfig) -> DialogueGraph:
    graph = DialogueGraph.empty()
    for turn in turns:
        acts = turn.get("acts") or classify_dialogue_acts(_to_str(turn.get("content", "")), config)
        to_goal, trigger_act = _goal_and_trigger_from_acts(acts, graph.current_node)
        if trigger_act is not None and to_goal != graph.current_node:
            graph = graph.add_transition(to_goal, trigger_act, int(turn.get("turn_index", 0)))
    return graph


def graph_summary(graph: DialogueGraph) -> dict[str, object]:
    return {
        "total_nodes": len(graph.nodes),
        "total_edges": len(graph.edges),
        "visit_counts": dict(graph.visit_counts),
        "current_state": graph.current_node,
        "transition_sequence": [edge["to_goal"] for edge in graph.edges],
    }
