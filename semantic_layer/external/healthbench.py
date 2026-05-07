from __future__ import annotations

from collections.abc import Mapping, Sequence
import re
from typing import Any, TypedDict, cast

from .healthbench_dialogue import (
    DialogueAct,
    DialogueActConfig,
    DialogueState,
    build_dialogue_graph,
    graph_summary,
    parse_conversation_to_turns,
    update_dialogue_state,
)
from .healthbench_integration import CompositeScoreConfig, build_extended_report
from .healthbench_quality import QualityScoreConfig, compute_quality_assessment
from .models import CanonicalCase, CriterionKind, DatasetManifest
from .pipeline import build_expected_actions, classify_criterion, normalize_action_id, raw_to_canonical


class RubricTrackAResult(TypedDict):
    track_a_score: float
    mandatory_coverage: float
    forbidden_avoidance: float
    mandatory_satisfied: int
    mandatory_total: int
    forbidden_avoided: int
    forbidden_total: int


class SemanticMatchedPair(TypedDict):
    expected: str
    extracted: str
    similarity: float


class SemanticMatchResult(TypedDict):
    match_score: float
    n_matched: int
    n_expected: int
    n_extracted: int
    matched_pairs: list[SemanticMatchedPair]
    unmatched_expected: list[str]
    unmatched_extracted: list[str]


def _to_str(value: object) -> str:
    return value if isinstance(value, str) else ""


def _to_int(value: object, default: int = 0) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        try:
            return int(value.strip())
        except ValueError:
            return default
    return default


def _to_float(value: object, default: float = 0.0) -> float:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value.strip())
        except ValueError:
            return default
    return default


def _to_prompt_turns(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    turns: list[Mapping[str, object]] = []
    for item in value:
        if isinstance(item, Mapping):
            mapping_item = cast("Mapping[object, object]", item)
            turns.append({str(key): val for key, val in mapping_item.items()})
    return turns


def _to_bool_list(value: object) -> list[bool]:
    if not isinstance(value, Sequence) or isinstance(value, (str, bytes, bytearray)):
        return []
    labels: list[bool] = []
    for item in value:
        if isinstance(item, bool):
            labels.append(item)
    return labels


def parse_meta_eval_row(row: Mapping[str, object]) -> dict[str, object]:
    prompt_turns = _to_prompt_turns(row.get("prompt", []))
    prompt_text = "\n".join(
        f"[{_to_str(turn.get('role', 'unknown'))}]: {_to_str(turn.get('content', ''))}" for turn in prompt_turns
    )

    completion = _to_str(row.get("completion", ""))
    rubric_text = _to_str(row.get("rubric", ""))
    binary_labels = _to_bool_list(row.get("binary_labels", []))
    checklist = _parse_rubric_text(rubric_text)

    n_physicians = len(binary_labels)
    n_pass = sum(1 for lbl in binary_labels if lbl)
    agreement_ratio = n_pass / max(n_physicians, 1)

    completion_id = _to_str(row.get("completion_id", ""))
    prompt_id = _to_str(row.get("prompt_id", ""))
    row_id = completion_id or prompt_id or "unknown"

    return {
        "id": row_id,
        "input_text": prompt_text,
        "checklist": checklist,
        "completion": completion,
        "category": _to_str(row.get("category", "")),
        "binary_labels": binary_labels,
        "physician_agreement": agreement_ratio,
        "n_physicians": n_physicians,
        "prompt_id": prompt_id,
    }


def parse_eval_row(row: dict[str, Any]) -> dict[str, Any]:
    prompt = row.get("prompt", [])
    prompt_text = "\n".join(
        f"[{_to_str(t.get('role', ''))}]: {_to_str(t.get('content', ''))}" for t in prompt if isinstance(t, dict)
    )

    rubrics_full = []
    checklist = []
    for r in row.get("rubrics", []):
        if isinstance(r, dict):
            text = _to_str(r.get("criterion", r.get("text", "")))
            rubrics_full.append(
                {
                    "text": text,
                    "points": _to_int(r.get("points", 0)),
                    "tags": r.get("tags", []),
                }
            )
            checklist.append(text)

    return {
        "id": _to_str(row.get("prompt_id", "unknown")),
        "input_text": prompt_text,
        "checklist": checklist,
        "rubrics_full": rubrics_full,
        "example_tags": row.get("example_tags", []),
    }


def _parse_rubric_text(rubric: str) -> list[str]:
    lines = rubric.strip().split("\n") if rubric else []
    criteria: list[str] = []

    has_list_markers = any(bool(re.match(r"^([-*•]\s+|\d+[.)]\s+)", line.strip())) for line in lines if line.strip())

    if has_list_markers:
        for line in lines:
            stripped = line.strip()
            if not stripped or not re.match(r"^([-*•]\s+|\d+[.)]\s+)", stripped):
                continue
            cleaned = re.sub(r"^[-*•]\s*", "", stripped)
            cleaned = re.sub(r"^\d+[.)]\s*", "", cleaned)
            if len(cleaned) >= 4:
                criteria.append(cleaned)
    elif rubric:
        sentences = re.split(r"(?<=[.!?])\s+", rubric.strip())
        criteria = [sentence for sentence in sentences if len(sentence) >= 16]

    return criteria


def build_meta_eval_episode(row: Mapping[str, object], manifest: DatasetManifest) -> dict[str, object]:
    raw = parse_meta_eval_row(row)
    canonical: CanonicalCase = raw_to_canonical(raw, manifest)
    expected = build_expected_actions(canonical)
    completion = _to_str(raw.get("completion", ""))
    agent_actions = _extract_actions_from_completion(completion)

    return {
        "case_id": _to_str(raw.get("id", "unknown")),
        "prompt_id": _to_str(raw.get("prompt_id", "")),
        "canonical": canonical,
        "expected_actions": expected,
        "agent_actions": agent_actions,
        "binary_labels": _to_bool_list(raw.get("binary_labels", [])),
        "physician_agreement": _to_float(raw.get("physician_agreement", 0.0)),
        "category": _to_str(raw.get("category", "")),
    }


def build_extended_meta_eval_episode(
    row: Mapping[str, object],
    manifest: DatasetManifest,
) -> dict[str, object]:
    episode = build_meta_eval_episode(row, manifest)
    raw = parse_meta_eval_row(row)

    prompt_turns = _to_prompt_turns(row.get("prompt", []))
    dialogue_config = DialogueActConfig.default()
    quality_config = QualityScoreConfig.default()

    turns = parse_conversation_to_turns([dict(turn) for turn in prompt_turns], dialogue_config)
    graph = build_dialogue_graph(turns, dialogue_config)
    graph_info = graph_summary(graph)

    state = DialogueState(turn_count=0)
    for turn in turns:
        state = update_dialogue_state(state, turn)

    checklist = cast("list[str]", raw.get("checklist", []))
    binary_labels = cast("list[bool]", raw.get("binary_labels", []))
    rubric_items: list[dict[str, object]] = [{"criterion": criterion, "points": 1} for criterion in checklist]
    if not rubric_items and binary_labels:
        rubric_items = [{"criterion": f"criterion_{index + 1}", "points": 1} for index in range(len(binary_labels))]

    if len(binary_labels) >= len(rubric_items):
        satisfied = binary_labels[: len(rubric_items)]
    else:
        satisfied = [*binary_labels, *([False] * (len(rubric_items) - len(binary_labels)))]

    completion = _to_str(raw.get("completion", ""))
    quality = compute_quality_assessment(completion, rubric_items, satisfied, quality_config)

    dialogue_state = {
        "turn_count": state.turn_count,
        "patient_info": state.patient_info,
        "detected_conditions": state.detected_conditions,
        "current_goal": state.current_goal,
        "conversation_summary": state.conversation_summary,
    }

    return {
        **episode,
        "completion": completion,
        "dialogue_turns": turns,
        "dialogue_graph_summary": graph_info,
        "quality_assessment": quality,
        "dialogue_state": dialogue_state,
    }


def run_extended_evaluation(
    episode: dict[str, object],
    rubrics: list[dict[str, object]],
    satisfied: list[bool],
) -> dict[str, object]:
    quality_config = QualityScoreConfig.default()
    composite_config = CompositeScoreConfig.default()

    completion = _to_str(episode.get("completion", ""))
    quality_assessment_obj = episode.get("quality_assessment")
    quality_assessment: Mapping[str, object]
    if isinstance(quality_assessment_obj, Mapping):
        quality_assessment = quality_assessment_obj
    else:
        quality_assessment = compute_quality_assessment(completion, rubrics, satisfied, quality_config)

    track_a = compute_rubric_grounded_track_a(rubrics, satisfied)
    dialogue_summary_obj = episode.get("dialogue_graph_summary")
    dialogue_summary = dict(dialogue_summary_obj) if isinstance(dialogue_summary_obj, Mapping) else {}
    dialogue_state_obj = episode.get("dialogue_state")
    dialogue_state = dialogue_state_obj if isinstance(dialogue_state_obj, Mapping) else {}
    act_summary: dict[str, int] = {}
    turns_data = episode.get("dialogue_turns")
    if isinstance(turns_data, list):
        for act in DialogueAct:
            count = 0
            for turn in turns_data:
                if not isinstance(turn, Mapping):
                    continue
                turn_acts = turn.get("acts")
                if isinstance(turn_acts, list) and act in cast("list[object]", turn_acts):
                    count += 1
            if count > 0:
                act_summary[act.value] = count

    dialogue_result: dict[str, object] = {
        "turns": _to_int(dialogue_state.get("turn_count", 0), 0),
        "act_summary": act_summary,
        "state": {
            "current": dialogue_summary.get("current_state", ""),
            "nodes": dialogue_summary.get("total_nodes", 0),
            "edges": dialogue_summary.get("total_edges", 0),
        },
    }

    report = build_extended_report(
        {
            "case_id": _to_str(episode.get("case_id", "unknown")),
            "compliance_score": track_a["track_a_score"],
            "violations": [],
        },
        dialogue_result,
        cast("dict[str, object]", dict(quality_assessment)),
        composite_config,
    )

    return {
        "case_id": report["case_id"],
        "track_a_score": track_a["track_a_score"],
        "mandatory_coverage": track_a["mandatory_coverage"],
        "forbidden_avoidance": track_a["forbidden_avoidance"],
        "quality_assessment": cast("dict[str, object]", dict(quality_assessment)),
        "empathy_score": report["empathy_score"],
        "accuracy_score": report["accuracy_score"],
        "dialogue_quality": report["dialogue_quality_score"],
        "composite_score": report["composite_score"],
        "extended_report": report,
    }


def extract_actions_via_llm(
    completion: str,
    endpoint: str,
    model: str,
) -> list[dict[str, str]]:
    import json

    import httpx

    prompt = f"""Extract all clinical actions/recommendations from this medical AI response.
For each action, classify it into one of these categories:
- referral: suggesting the patient see a specific provider
- medication: recommending/prescribing medication
- test_order: ordering labs, imaging, or diagnostic tests
- procedure: recommending a medical procedure
- lifestyle: diet, exercise, behavioral changes
- monitoring: follow-up, self-monitoring instructions
- emergency: calling 911, going to ER

RESPONSE:
{completion[:2500]}

Output a JSON array. Each element: {{"action": "brief action description", "category": "category_name"}}
If no actions found, output: []
Output ONLY the JSON array."""

    try:
        import os

        api_key = os.environ.get("OPENAI_API_KEY", "")
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        resp = httpx.post(
            f"{endpoint}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 512,
                "temperature": 0.1,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            headers=headers,
            timeout=30.0,
        )
        _ = resp.raise_for_status()

        payload = resp.json()
        text = ""
        if isinstance(payload, Mapping):
            choices = payload.get("choices", [])
            if isinstance(choices, Sequence) and choices:
                first = choices[0]
                if isinstance(first, Mapping):
                    message = first.get("message", {})
                    if isinstance(message, Mapping):
                        text = _to_str(message.get("content", ""))

        match = re.search(r"\[[\s\S]*\]", text)
        if match:
            actions = json.loads(match.group())
            if isinstance(actions, list):
                return [
                    {
                        "action": normalize_action_id(_to_str(a.get("action", ""))[:80]),
                        "category": _to_str(a.get("category", "unknown")) or "unknown",
                        "detail": _to_str(a.get("action", "")),
                    }
                    for a in actions
                    if isinstance(a, Mapping) and _to_str(a.get("action", ""))
                ]
    except Exception:
        pass
    return []


_CATEGORY_TO_ACTION_TYPE = {
    "referral": "consult",
    "medication": "give_medication",
    "test_order": "order_lab",
    "procedure": "procedure",
    "lifestyle": "reassess",
    "monitoring": "reassess",
    "emergency": "disposition",
}


def normalize_extracted_actions(
    extracted: list[dict[str, str]],
) -> list[str]:
    action_ids: list[str] = []
    for item in extracted:
        category = _to_str(item.get("category", "unknown")) or "unknown"
        action_slug = _to_str(item.get("action", ""))
        prefix = _CATEGORY_TO_ACTION_TYPE.get(category, "action")
        if action_slug:
            action_ids.append(f"{prefix}_{action_slug}")
    return action_ids


def compute_rubric_grounded_track_a(
    rubrics: Sequence[Mapping[str, object]],
    satisfied: list[bool],
) -> RubricTrackAResult:
    if len(rubrics) != len(satisfied):
        raise ValueError("rubrics and satisfied must have same length")

    mandatory_total = 0
    mandatory_satisfied = 0
    mandatory_weight = 0.0

    forbidden_total = 0
    forbidden_avoided = 0
    forbidden_weight = 0.0

    for rubric, sat in zip(rubrics, satisfied):
        points = _to_int(rubric.get("points", 0), 0)

        if points > 0:
            mandatory_total += 1
            mandatory_weight += abs(points)
            if sat:
                mandatory_satisfied += 1
        elif points < 0:
            forbidden_total += 1
            forbidden_weight += abs(points)
            if not sat:
                forbidden_avoided += 1

    mandatory_coverage = mandatory_satisfied / max(mandatory_total, 1)
    forbidden_avoidance = forbidden_avoided / max(forbidden_total, 1)

    w_pos = mandatory_weight if mandatory_weight > 0 else 1.0
    w_neg = forbidden_weight if forbidden_weight > 0 else 0.0
    total_weight = w_pos + w_neg

    if total_weight > 0:
        track_a = (mandatory_coverage * w_pos + forbidden_avoidance * w_neg) / total_weight
    else:
        track_a = 0.0

    return {
        "track_a_score": round(max(0.0, min(1.0, track_a)), 4),
        "mandatory_coverage": round(mandatory_coverage, 4),
        "forbidden_avoidance": round(forbidden_avoidance, 4),
        "mandatory_satisfied": mandatory_satisfied,
        "mandatory_total": mandatory_total,
        "forbidden_avoided": forbidden_avoided,
        "forbidden_total": forbidden_total,
    }


def semantic_action_match(
    expected_ids: list[str],
    extracted_ids: list[str],
    threshold: float = 0.4,
) -> SemanticMatchResult:
    def _tokenize(action_id: str) -> set[str]:
        return set(action_id.replace("/", "_").replace(":", "_").split("_"))

    def _jaccard(a: set[str], b: set[str]) -> float:
        if not a and not b:
            return 0.0
        intersection = a & b
        union = a | b
        return len(intersection) / len(union) if union else 0.0

    matched_pairs: list[SemanticMatchedPair] = []
    used_extracted: set[int] = set()

    for exp_id in expected_ids:
        exp_tokens = _tokenize(exp_id)
        best_match: tuple[int, str, float] | None = None
        best_score = threshold

        for j, ext_id in enumerate(extracted_ids):
            if j in used_extracted:
                continue
            ext_tokens = _tokenize(ext_id)
            score = _jaccard(exp_tokens, ext_tokens)
            if score > best_score:
                best_score = score
                best_match = (j, ext_id, score)

        if best_match:
            j, ext_id, score = best_match
            matched_pairs.append(
                {
                    "expected": exp_id,
                    "extracted": ext_id,
                    "similarity": round(score, 3),
                }
            )
            used_extracted.add(j)

    unmatched_expected = [e for e in expected_ids if not any(m["expected"] == e for m in matched_pairs)]
    unmatched_extracted = [e for j, e in enumerate(extracted_ids) if j not in used_extracted]

    match_score = len(matched_pairs) / max(len(expected_ids), 1)

    return {
        "match_score": round(match_score, 4),
        "n_matched": len(matched_pairs),
        "n_expected": len(expected_ids),
        "n_extracted": len(extracted_ids),
        "matched_pairs": matched_pairs,
        "unmatched_expected": unmatched_expected,
        "unmatched_extracted": unmatched_extracted,
    }


def _extract_actions_from_completion(completion: str) -> list[str]:
    if not completion:
        return []

    actions: list[str] = []
    lower = completion.lower()
    action_patterns = [
        r"(?:should|recommend|suggest|advise)\s+(?:to\s+)?(\w[\w\s]{5,40}?)(?:[.,;!]|$)",
        r"(?:call|contact|visit|go to)\s+([\w\s]{5,30}?)(?:[.,;!]|$)",
        r"(?:take|use|apply|start)\s+([\w\s]{5,30}?)(?:[.,;!]|$)",
        r"(?:seek|get)\s+(?:immediate\s+)?(?:medical|emergency)\s+([\w\s]{3,20})",
    ]
    for pattern in action_patterns:
        found_count = 0
        for found in re.finditer(pattern, lower):
            if found_count >= 3:
                break
            match = found.group(1)
            normalized = normalize_action_id(match.strip())
            if len(normalized) > 3:
                actions.append(normalized)
                found_count += 1

    deduped = sorted(set(actions))
    return deduped[:10]


parse_rubric_text = _parse_rubric_text
extract_actions_from_completion = _extract_actions_from_completion


# Axes that are NEVER clinical actions regardless of text content.
_AXIS_ALWAYS_ASSESSMENT: set[str] = {"accuracy", "context_awareness"}

# Axes that MAY be actions — defer to word-boundary keyword classifier.
_AXIS_MAYBE_ACTION: set[str] = {"completeness", "safety"}

_AXIS_TO_KIND: dict[str, CriterionKind] = {
    "accuracy": CriterionKind.ASSESSMENT,
    "completeness": CriterionKind.ACTION,
    "communication_quality": CriterionKind.EXPLANATION,
    "context_awareness": CriterionKind.ASSESSMENT,
    "safety": CriterionKind.ACTION,
}


def classify_criterion_enhanced(
    text: str,
    tags: list[str] | None = None,
    points: int | None = None,
) -> CriterionKind:
    """Classify a HealthBench rubric criterion with axis-first logic.

    Routing rules:
    - ``axis:accuracy`` / ``axis:context_awareness`` → always ASSESSMENT
      (these describe factual correctness, not clinical actions)
    - ``axis:communication_quality`` → always EXPLANATION
    - ``axis:completeness`` / ``axis:safety`` → defer to word-boundary
      keyword classifier (may or may not describe a clinical action)
    - Negative points → ACTION (forbidden)
    - No axis tag → word-boundary keyword classifier
    """
    if tags:
        for tag in tags:
            if tag.startswith("axis:"):
                axis = tag.split(":", 1)[1]
                if axis in _AXIS_ALWAYS_ASSESSMENT:
                    return CriterionKind.ASSESSMENT
                if axis == "communication_quality":
                    return CriterionKind.EXPLANATION
                if axis in _AXIS_MAYBE_ACTION:
                    # Defer to keyword classifier — only ACTION if text
                    # contains imperative clinical verbs.
                    break

    if points is not None and points < 0:
        return CriterionKind.ACTION

    return classify_criterion(text)


def compute_native_score(
    rubrics: Sequence[Mapping[str, object]],
    satisfied_criteria: Sequence[bool],
) -> dict[str, object]:
    if len(rubrics) != len(satisfied_criteria):
        raise ValueError(f"Rubric count ({len(rubrics)}) != satisfied count ({len(satisfied_criteria)})")

    rubric_points = [_to_int(rubric.get("points", 0)) for rubric in rubrics]
    max_possible = sum(point for point in rubric_points if point > 0)
    min_possible = sum(point for point in rubric_points if point < 0)

    raw_score = 0.0
    positive_earned = 0.0
    negative_incurred = 0.0
    breakdown: list[dict[str, object]] = []

    for rubric, points, satisfied in zip(rubrics, rubric_points, satisfied_criteria):
        contribution = float(points) if satisfied else 0.0
        if points > 0 and satisfied:
            positive_earned += float(points)
        if points < 0 and satisfied:
            negative_incurred += float(abs(points))

        raw_score += contribution
        criterion_text = _to_str(rubric.get("criterion", ""))[:60]
        breakdown.append(
            {
                "criterion": criterion_text,
                "points": points,
                "satisfied": satisfied,
                "contribution": contribution,
            }
        )

    score_range = max_possible - min_possible
    normalized = (raw_score - min_possible) / score_range if score_range > 0 else 0.5
    normalized = max(0.0, min(1.0, normalized))

    return {
        "raw_score": raw_score,
        "max_possible": max_possible,
        "min_possible": min_possible,
        "normalized_score": round(normalized, 4),
        "positive_earned": positive_earned,
        "negative_incurred": negative_incurred,
        "criteria_breakdown": breakdown,
    }


def compute_cga_native_correlation(cga_score: float, native_score: float) -> dict[str, object]:
    diff = abs(cga_score - native_score)
    return {
        "cga_score": round(cga_score, 4),
        "native_score": round(native_score, 4),
        "absolute_diff": round(diff, 4),
        "agreement": "aligned" if diff < 0.1 else "moderate" if diff < 0.25 else "divergent",
    }
