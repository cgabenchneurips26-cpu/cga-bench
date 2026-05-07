from __future__ import annotations

import json
import math
import re
from collections import Counter
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import NotRequired, TypedDict, cast


class EmpathyScoreResult(TypedDict):
    empathy_score: float
    keyword_hits: int
    negative_hits: int
    text_length: int
    method: str
    sentiment: NotRequired[SentimentResult]


class AccuracyScoreResult(TypedDict):
    accuracy_score: float
    criteria_satisfied: int
    criteria_total: int
    weighted_score: float
    method: str


class SentimentResult(TypedDict):
    polarity: float
    intensity: float


class EmpathyScaleResult(TypedDict):
    scale_score: float
    normalized: float
    dimensions: dict[str, float]


class QualityAssessment(TypedDict):
    empathy: EmpathyScoreResult
    accuracy: AccuracyScoreResult
    composite_quality: float


class JudgeEndpoint(TypedDict):
    endpoint: str
    model: str
    weight: float


@dataclass
class MultiJudgeConfig:
    judges: list[JudgeEndpoint]
    aggregation_method: str
    min_agreement: float

    @classmethod
    def default(cls) -> "MultiJudgeConfig":
        return cls(judges=[], aggregation_method="mean", min_agreement=0.5)


class MultiJudgeResult(TypedDict):
    final_score: float
    individual_scores: list[float]
    agreement_ratio: float
    method: str
    n_judges: int


@dataclass
class RAGConfig:
    knowledge_base_path: str | None
    max_context_chunks: int
    chunk_similarity_threshold: float

    @classmethod
    def default(cls) -> "RAGConfig":
        return cls(knowledge_base_path=None, max_context_chunks=5, chunk_similarity_threshold=0.3)


class RAGContext(TypedDict):
    chunks: list[str]
    source_files: list[str]
    retrieval_score: float


class ModelTier(TypedDict):
    tier: str
    endpoint: str
    model: str
    cost_weight: float


@dataclass
class TieringConfig:
    slm_tier: ModelTier | None
    llm_tier: ModelTier | None
    complexity_threshold: float
    always_use_llm_for: list[str]

    @classmethod
    def default(cls) -> "TieringConfig":
        return cls(
            slm_tier=None,
            llm_tier=None,
            complexity_threshold=0.5,
            always_use_llm_for=["empathy_scale"],
        )


_DEFAULT_EMPATHY_KEYWORDS: list[str] = [
    "sorry",
    "understand",
    "frightening",
    "help you",
    "concern",
    "worrying",
    "hear that",
    "appreciate",
]

_DEFAULT_NON_EMPATHY_KEYWORDS: list[str] = [
    "just",
    "simply",
    "obviously",
]

_POSITIVE_SENTIMENT_WORDS: list[str] = [
    "good",
    "great",
    "better",
    "improve",
    "safe",
    "normal",
    "reassure",
    "hope",
    "recover",
]

_NEGATIVE_SENTIMENT_WORDS: list[str] = [
    "danger",
    "risk",
    "severe",
    "fatal",
    "worse",
    "emergency",
    "critical",
    "urgent",
]

_HEART_DIMENSIONS: tuple[str, ...] = (
    "hearing",
    "empathizing",
    "appreciating",
    "recommending",
    "transitioning",
)


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


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def _clamp(value: float, min_value: float, max_value: float) -> float:
    return max(min_value, min(max_value, value))


@dataclass
class QualityScoreConfig:
    empathy_keywords: list[str] = field(default_factory=list)
    non_empathy_keywords: list[str] = field(default_factory=list)
    empathy_weight: float = 0.4
    accuracy_weight: float = 0.6
    min_text_length: int = 10
    llm_endpoint: str | None = None
    llm_model: str | None = None

    @classmethod
    def default(cls) -> "QualityScoreConfig":
        return cls(
            empathy_keywords=list(_DEFAULT_EMPATHY_KEYWORDS),
            non_empathy_keywords=list(_DEFAULT_NON_EMPATHY_KEYWORDS),
            empathy_weight=0.4,
            accuracy_weight=0.6,
            min_text_length=10,
            llm_endpoint=None,
            llm_model=None,
        )


def _llm_empathy_score(text: str, endpoint: str, model: str) -> float | None:
    """Call LLM endpoint for empathy scoring. Returns None on failure."""
    try:
        import httpx
    except ImportError:
        return None

    prompt = (
        "Rate the empathy level of the following medical response on a scale "
        "of 0.0 to 1.0, where 0.0 is completely cold/dismissive and 1.0 is "
        "deeply empathetic.\n\n"
        f"RESPONSE:\n{text[:2500]}\n\n"
        'Output ONLY a JSON object: {"empathy_score": <float>}'
    )

    try:
        resp = httpx.post(
            f"{endpoint}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 64,
                "temperature": 0.1,
            },
            timeout=30.0,
        )
        _ = resp.raise_for_status()
        payload_obj = cast(object, resp.json())
        if isinstance(payload_obj, Mapping):
            payload = cast(Mapping[str, object], payload_obj)
            choices = payload.get("choices", [])
            if isinstance(choices, Sequence) and choices:
                first = choices[0]
                if isinstance(first, Mapping):
                    first_mapping = cast(Mapping[str, object], first)
                    message = first_mapping.get("message", {})
                    if isinstance(message, Mapping):
                        message_mapping = cast(Mapping[str, object], message)
                        content = message_mapping.get("content", "")
                        if isinstance(content, str):
                            match = re.search(r'"empathy_score"\s*:\s*([\d.]+)', content)
                            if match:
                                return _clamp01(float(match.group(1)))
    except Exception:
        pass
    return None


def _llm_accuracy_score(
    text: str, rubrics: Sequence[Mapping[str, object]], endpoint: str, model: str
) -> float | None:
    try:
        import httpx
    except ImportError:
        return None

    rubric_lines: list[str] = []
    for rubric in rubrics[:10]:
        criterion = str(rubric.get("criterion", "")).strip()
        points = _to_float(rubric.get("points", 0.0))
        if criterion:
            rubric_lines.append(f"- {criterion} (points: {points:g})")
    rubric_text = "\n".join(rubric_lines) if rubric_lines else "- No rubric criteria provided"

    prompt = (
        "Given these medical evaluation criteria, rate the accuracy of this response "
        "on 0.0-1.0 scale.\n\n"
        f"CRITERIA:\n{rubric_text}\n\n"
        f"RESPONSE:\n{text[:2500]}\n\n"
        'Output ONLY a JSON object: {"accuracy_score": <float>}'
    )

    try:
        resp = httpx.post(
            f"{endpoint}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 64,
                "temperature": 0.1,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=30.0,
        )
        _ = resp.raise_for_status()
        payload_obj = cast(object, resp.json())
        if isinstance(payload_obj, Mapping):
            payload = cast(Mapping[str, object], payload_obj)
            choices = payload.get("choices", [])
            if isinstance(choices, Sequence) and choices:
                first = choices[0]
                if isinstance(first, Mapping):
                    first_mapping = cast(Mapping[str, object], first)
                    message = first_mapping.get("message", {})
                    if isinstance(message, Mapping):
                        message_mapping = cast(Mapping[str, object], message)
                        content = message_mapping.get("content", "")
                        if isinstance(content, str):
                            match = re.search(r'"accuracy_score"\s*:\s*([-+]?\d*\.?\d+)', content)
                            if match:
                                return _clamp01(float(match.group(1)))
    except Exception:
        pass
    return None


def _llm_empathy_scale_score(text: str, endpoint: str, model: str) -> EmpathyScaleResult | None:
    try:
        import httpx
    except ImportError:
        return None

    prompt = (
        "Rate the empathy in this medical response using these dimensions (1-10 each):\n"
        "1. Hearing: Does the response acknowledge the patient's feelings?\n"
        "2. Empathizing: Does it show understanding of emotional impact?\n"
        "3. Appreciating: Does it validate the patient's experience?\n"
        "4. Recommending: Does it offer constructive next steps with warmth?\n"
        "5. Transitioning: Does it smoothly move from empathy to clinical guidance?\n\n"
        f"RESPONSE:\n{text[:2500]}\n\n"
        "Output JSON: "
        '{"hearing": N, "empathizing": N, "appreciating": N, "recommending": N, "transitioning": N}'
    )

    try:
        resp = httpx.post(
            f"{endpoint}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 128,
                "temperature": 0.1,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=30.0,
        )
        _ = resp.raise_for_status()
        payload_obj = cast(object, resp.json())
        if not isinstance(payload_obj, Mapping):
            return None
        payload = cast(Mapping[str, object], payload_obj)

        choices = payload.get("choices", [])
        if not (isinstance(choices, Sequence) and choices):
            return None

        first = choices[0]
        if not isinstance(first, Mapping):
            return None
        first_mapping = cast(Mapping[str, object], first)

        message = first_mapping.get("message", {})
        if not isinstance(message, Mapping):
            return None
        message_mapping = cast(Mapping[str, object], message)

        content = message_mapping.get("content", "")
        if not isinstance(content, str):
            return None

        json_match = re.search(r"\{[\s\S]*\}", content)
        if not json_match:
            return None

        parsed_obj = cast(object, json.loads(json_match.group(0)))
        if not isinstance(parsed_obj, Mapping):
            return None
        parsed = cast(Mapping[str, object], parsed_obj)

        dimensions: dict[str, float] = {}
        for name in _HEART_DIMENSIONS:
            value = _clamp(_to_float(parsed.get(name, 0.0)), 1.0, 10.0)
            dimensions[name] = round(value, 2)

        scale_score = sum(dimensions.values()) / len(dimensions)
        normalized = _clamp01(scale_score / 10.0)
        return {
            "scale_score": round(scale_score, 3),
            "normalized": round(normalized, 4),
            "dimensions": dimensions,
        }
    except Exception:
        return None


def _keyword_empathy_components(text: str, config: QualityScoreConfig) -> tuple[int, int, float]:
    lower_text = text.lower()
    keyword_hits = sum(1 for keyword in config.empathy_keywords if keyword and keyword in lower_text)
    negative_hits = sum(1 for keyword in config.non_empathy_keywords if keyword and keyword in lower_text)

    positive_score = min(1.0, keyword_hits / 3.0)
    negative_penalty = min(0.6, negative_hits * 0.25)
    keyword_score = _clamp01(positive_score - negative_penalty)
    return keyword_hits, negative_hits, keyword_score


def compute_sentiment(text: str) -> SentimentResult:
    if not text:
        return {"polarity": 0.0, "intensity": 0.0}

    tokens: list[str] = re.findall(r"\b[a-zA-Z]+\b", text.lower())
    if not tokens:
        return {"polarity": 0.0, "intensity": 0.0}

    positive_count = sum(1 for token in tokens if token in _POSITIVE_SENTIMENT_WORDS)
    negative_count = sum(1 for token in tokens if token in _NEGATIVE_SENTIMENT_WORDS)
    total = positive_count + negative_count

    if total == 0:
        return {"polarity": 0.0, "intensity": 0.0}

    polarity = (positive_count - negative_count) / max(total, 1)
    intensity = min(1.0, total / 5.0)
    return {"polarity": float(polarity), "intensity": float(intensity)}


def compute_empathy_score(text: str, config: QualityScoreConfig) -> EmpathyScoreResult:
    text_length = len(text)
    method = "keyword"
    sentiment = compute_sentiment(text)

    if text_length < config.min_text_length:
        return {
            "empathy_score": 0.0,
            "keyword_hits": 0,
            "negative_hits": 0,
            "text_length": text_length,
            "method": method,
            "sentiment": sentiment,
        }

    keyword_hits, negative_hits, keyword_score = _keyword_empathy_components(text, config)

    if sentiment["intensity"] > 0.0:
        empathy_score = _clamp01(0.7 * keyword_score + 0.3 * max(0.0, sentiment["polarity"]))
    else:
        empathy_score = keyword_score

    if config.llm_endpoint and config.llm_model:
        llm_score = _llm_empathy_score(text, config.llm_endpoint, config.llm_model)
        if llm_score is not None:
            empathy_score = _clamp01(0.5 * empathy_score + 0.5 * llm_score)
            method = "hybrid"
        else:
            method = "keyword"
    else:
        method = "keyword"

    return {
        "empathy_score": empathy_score,
        "keyword_hits": keyword_hits,
        "negative_hits": negative_hits,
        "text_length": text_length,
        "method": method,
        "sentiment": sentiment,
    }


def compute_accuracy_score(
    rubrics: Sequence[Mapping[str, object]],
    satisfied: list[bool],
    config: QualityScoreConfig,
    text: str | None = None,
) -> AccuracyScoreResult:
    if len(rubrics) != len(satisfied):
        raise ValueError("rubrics and satisfied must have same length")

    criteria_total = len(rubrics)
    criteria_satisfied = sum(1 for status in satisfied if status)
    accuracy_score = criteria_satisfied / criteria_total if criteria_total > 0 else 0.0

    positive_points = [max(0.0, _to_float(rubric.get("points", 0.0))) for rubric in rubrics]
    total_positive = sum(positive_points)
    earned_positive = sum(
        points for points, status in zip(positive_points, satisfied) if status
    )
    rubric_weighted = earned_positive / total_positive if total_positive > 0 else 0.0
    weighted_score = rubric_weighted
    method = "rubric"

    if config.llm_endpoint and config.llm_model and text:
        llm_score = _llm_accuracy_score(text, rubrics, config.llm_endpoint, config.llm_model)
        if llm_score is not None:
            weighted_score = _clamp01(0.6 * rubric_weighted + 0.4 * llm_score)
            method = "hybrid"

    return {
        "accuracy_score": _clamp01(accuracy_score),
        "criteria_satisfied": criteria_satisfied,
        "criteria_total": criteria_total,
        "weighted_score": _clamp01(weighted_score),
        "method": method,
    }


def compute_empathy_scale(text: str, config: QualityScoreConfig) -> EmpathyScaleResult:
    if config.llm_endpoint and config.llm_model:
        llm_result = _llm_empathy_scale_score(text, config.llm_endpoint, config.llm_model)
        if llm_result is not None:
            return llm_result

    keyword_hits, negative_hits, keyword_score = _keyword_empathy_components(text, config)
    sentiment = compute_sentiment(text)
    sentiment_pos = max(0.0, sentiment["polarity"])
    base_norm = _clamp01(0.75 * keyword_score + 0.25 * sentiment_pos)
    penalty = min(0.25, 0.05 * negative_hits)

    dimensions = {
        "hearing": round(_clamp(1.0 + 9.0 * _clamp01(base_norm + 0.05 - penalty), 1.0, 10.0), 2),
        "empathizing": round(_clamp(1.0 + 9.0 * _clamp01(base_norm + 0.1 * sentiment_pos - penalty), 1.0, 10.0), 2),
        "appreciating": round(_clamp(1.0 + 9.0 * _clamp01(base_norm - 0.05 - penalty), 1.0, 10.0), 2),
        "recommending": round(_clamp(1.0 + 9.0 * _clamp01(0.7 * base_norm + 0.3 * min(1.0, keyword_hits / 2.0)), 1.0, 10.0), 2),
        "transitioning": round(_clamp(1.0 + 9.0 * _clamp01(0.8 * base_norm + 0.1 - penalty), 1.0, 10.0), 2),
    }
    scale_score = sum(dimensions.values()) / len(dimensions)
    normalized = _clamp01(scale_score / 10.0)
    return {
        "scale_score": round(scale_score, 3),
        "normalized": round(normalized, 4),
        "dimensions": dimensions,
    }


def aggregate_quality_scores(scores: list[float]) -> float:
    if not scores:
        return 0.0
    return sum(scores) / len(scores)


def _normalized_agreement_ratio(scores: Sequence[float]) -> float:
    if len(scores) <= 1:
        return 1.0
    mean = sum(scores) / len(scores)
    variance = sum((score - mean) ** 2 for score in scores) / len(scores)
    std_dev = math.sqrt(variance)
    normalized_std = _clamp01(std_dev / 0.5)
    return _clamp01(1.0 - normalized_std)


def _majority_aggregate(scores: Sequence[float]) -> float:
    rounded = [round(score * 10.0) / 10.0 for score in scores]
    counts = Counter(rounded)
    best_score, _ = max(counts.items(), key=lambda item: (item[1], item[0]))
    return _clamp01(float(best_score))


def _call_multi_judge_score(prompt: str, endpoint: str, model: str) -> float | None:
    try:
        import httpx
    except ImportError:
        return None

    try:
        resp = httpx.post(
            f"{endpoint}/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": 64,
                "temperature": 0.1,
                "chat_template_kwargs": {"enable_thinking": False},
            },
            timeout=30.0,
        )
        _ = resp.raise_for_status()
        payload_obj = cast(object, resp.json())
        if not isinstance(payload_obj, Mapping):
            return None

        payload = cast(Mapping[str, object], payload_obj)
        choices = payload.get("choices", [])
        if not (isinstance(choices, Sequence) and choices):
            return None

        first = choices[0]
        if not isinstance(first, Mapping):
            return None
        first_mapping = cast(Mapping[str, object], first)
        message = first_mapping.get("message", {})
        if not isinstance(message, Mapping):
            return None

        message_mapping = cast(Mapping[str, object], message)
        content = message_mapping.get("content", "")
        if not isinstance(content, str):
            return None

        explicit = re.search(r'"(?:score|final_score|rating)"\s*:\s*([-+]?\d*\.?\d+)', content)
        if explicit:
            return _clamp01(float(explicit.group(1)))

        fallback = re.search(r"([-+]?\d*\.?\d+)", content)
        if fallback:
            return _clamp01(float(fallback.group(1)))
    except Exception:
        return None

    return None


def evaluate_with_multi_judge(
    text: str,
    judges: list[JudgeEndpoint],
    prompt_builder: Callable[[str], str],
    config: MultiJudgeConfig,
) -> MultiJudgeResult:
    _ = config.min_agreement
    active_judges = judges if judges else config.judges
    if not active_judges:
        return {
            "final_score": 0.0,
            "individual_scores": [],
            "agreement_ratio": 0.0,
            "method": "none",
            "n_judges": 0,
        }

    prompt = prompt_builder(text)
    valid_scores: list[float] = []
    valid_weights: list[float] = []

    for judge in active_judges:
        endpoint = str(judge.get("endpoint", "")).strip()
        model = str(judge.get("model", "")).strip()
        if not endpoint or not model:
            continue
        score = _call_multi_judge_score(prompt, endpoint, model)
        if score is None:
            continue
        valid_scores.append(_clamp01(score))
        weight = _to_float(judge.get("weight", 1.0), 1.0)
        valid_weights.append(weight if weight > 0 else 1.0)

    if not valid_scores:
        return {
            "final_score": 0.0,
            "individual_scores": [],
            "agreement_ratio": 0.0,
            "method": "none",
            "n_judges": 0,
        }

    method = config.aggregation_method
    if method == "weighted_mean":
        total_weight = sum(valid_weights)
        final_score = (
            sum(score * weight for score, weight in zip(valid_scores, valid_weights)) / total_weight
            if total_weight > 0
            else sum(valid_scores) / len(valid_scores)
        )
    elif method == "majority":
        final_score = _majority_aggregate(valid_scores)
    else:
        method = "mean"
        final_score = sum(valid_scores) / len(valid_scores)

    agreement_ratio = _normalized_agreement_ratio(valid_scores)
    if agreement_ratio < _clamp01(config.min_agreement):
        final_score = _clamp01(0.5 * final_score)

    return {
        "final_score": _clamp01(final_score),
        "individual_scores": [float(score) for score in valid_scores],
        "agreement_ratio": agreement_ratio,
        "method": method,
        "n_judges": len(valid_scores),
    }


def _tokenize_for_overlap(text: str) -> set[str]:
    return set(re.findall(r"\b[a-zA-Z0-9_]+\b", text.lower()))


def retrieve_context(query: str, config: RAGConfig) -> RAGContext:
    if not config.knowledge_base_path:
        return {"chunks": [], "source_files": [], "retrieval_score": 0.0}

    kb_path = Path(config.knowledge_base_path)
    if not kb_path.exists() or not kb_path.is_dir():
        return {"chunks": [], "source_files": [], "retrieval_score": 0.0}

    query_tokens = _tokenize_for_overlap(query)
    if not query_tokens:
        return {"chunks": [], "source_files": [], "retrieval_score": 0.0}

    candidates: list[tuple[float, str, str]] = []
    for file_path in kb_path.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in {".txt", ".md"}:
            continue
        try:
            content = file_path.read_text(encoding="utf-8")
        except Exception:
            continue

        segments = [segment.strip() for segment in re.split(r"\n\s*\n", content) if segment.strip()]
        if not segments:
            continue

        for segment in segments:
            segment_tokens = _tokenize_for_overlap(segment)
            if not segment_tokens:
                continue
            overlap = len(query_tokens & segment_tokens)
            score = overlap / len(query_tokens)
            if score >= _clamp01(config.chunk_similarity_threshold):
                candidates.append((score, segment[:1200], str(file_path)))

    if not candidates:
        return {"chunks": [], "source_files": [], "retrieval_score": 0.0}

    candidates.sort(key=lambda item: item[0], reverse=True)
    top_k = max(1, int(config.max_context_chunks))
    selected = candidates[:top_k]
    avg_score = sum(item[0] for item in selected) / len(selected)

    return {
        "chunks": [item[1] for item in selected],
        "source_files": [item[2] for item in selected],
        "retrieval_score": _clamp01(avg_score),
    }


def estimate_complexity(text: str) -> float:
    words = re.findall(r"\b[a-zA-Z]+\b", text.lower())
    total_words = len(words)
    if total_words == 0:
        return 0.0

    unique_words = len(set(words))
    sentences = [s for s in re.split(r"[.!?]+", text) if s.strip()]
    sentence_count = max(1, len(sentences))
    question_marks = text.count("?")

    length_factor = min(1.0, total_words / 200.0)
    raw_vocab_diversity = unique_words / total_words
    vocab_diversity = raw_vocab_diversity * min(1.0, total_words / 20.0)
    question_density = min(1.0, question_marks / max(1, sentence_count))
    sentence_factor = min(1.0, sentence_count / 8.0 + 0.2 * question_density)
    score = 0.4 * length_factor + 0.3 * vocab_diversity + 0.3 * sentence_factor
    return _clamp01(score)


def select_model_tier(text: str, task_type: str, config: TieringConfig) -> ModelTier | None:
    if task_type in config.always_use_llm_for:
        return config.llm_tier

    complexity = estimate_complexity(text)
    if complexity > config.complexity_threshold:
        return config.llm_tier
    return config.slm_tier


def compute_quality_assessment(
    text: str,
    rubrics: Sequence[Mapping[str, object]],
    satisfied: list[bool],
    config: QualityScoreConfig,
    *,
    rag_config: RAGConfig | None = None,
    tiering_config: TieringConfig | None = None,
) -> QualityAssessment:
    effective_config = config

    if tiering_config is not None:
        tier = select_model_tier(text, "quality_assessment", tiering_config)
        if tier is not None:
            effective_config = QualityScoreConfig(
                empathy_keywords=config.empathy_keywords,
                non_empathy_keywords=config.non_empathy_keywords,
                empathy_weight=config.empathy_weight,
                accuracy_weight=config.accuracy_weight,
                min_text_length=config.min_text_length,
                llm_endpoint=tier["endpoint"],
                llm_model=tier["model"],
            )

    rag_context: RAGContext | None = None
    if rag_config is not None:
        rag_context = retrieve_context(text, rag_config)

    empathy = compute_empathy_score(text, effective_config)

    accuracy_text = text
    if rag_context and rag_context["chunks"]:
        accuracy_text = text + "\n\n[RAG Context]\n" + "\n".join(rag_context["chunks"][:3])

    accuracy = compute_accuracy_score(rubrics, satisfied, effective_config, text=accuracy_text)
    composite_quality = (
        effective_config.empathy_weight * empathy["empathy_score"]
        + effective_config.accuracy_weight * accuracy["weighted_score"]
    )

    return {
        "empathy": empathy,
        "accuracy": accuracy,
        "composite_quality": composite_quality,
    }
