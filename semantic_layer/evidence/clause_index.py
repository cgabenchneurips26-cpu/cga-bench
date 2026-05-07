from __future__ import annotations

import re
from collections.abc import Mapping
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import cast

import yaml


_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NON_ALNUM_RE = re.compile(r"[^A-Z0-9]+")

_GRAPH_PREFIX_MAP: dict[str, str] = {
    "ssc_sepsis_hour1_bundle": "SSC_SEPSIS_H1",
    "aha_chest_pain": "AHA_CP",
    "aha_chest_pain_evaluation": "AHA_CP",
    "aha_stroke": "AHA_STROKE",
    "aha_heart_failure": "AHA_HF",
    "kdigo_aki_full": "KDIGO_AKI",
    "kdigo_contrast_aki": "KDIGO_CAKI",
    "ada_dka_management": "ADA_DKA",
    "universal_clinical_safety": "UCS",
}


@dataclass
class CanonicalClause:
    clause_id: str
    text: str
    heading: str
    keywords: list[str]
    guideline_id: str
    section: str
    evidence_level: str
    recommendation_class: str
    source_quote: str
    deadline_minutes: int | None


class ClauseIndex:
    def __init__(self) -> None:
        self._clauses: dict[str, CanonicalClause] = {}
        self._inverted: dict[str, set[str]] = {}

    def add_clause(self, clause: CanonicalClause) -> None:
        self._clauses[clause.clause_id] = clause
        tokens = set(_tokenize(clause.text))
        tokens.update(_tokenize(" ".join(clause.keywords)))
        for token in tokens:
            self._inverted.setdefault(token, set()).add(clause.clause_id)

    def get_by_clause_id(self, clause_id: str) -> CanonicalClause | None:
        return self._clauses.get(clause_id)

    def all_clause_ids(self) -> set[str]:
        return set(self._clauses.keys())

    def search_by_keyword(self, query: str, top_k: int = 10) -> list[CanonicalClause]:
        query_tokens = _tokenize(query)
        if not query_tokens or top_k <= 0:
            return []

        query_counter = Counter(query_tokens)
        candidate_ids: set[str] = set()
        for token in query_counter:
            candidate_ids.update(self._inverted.get(token, set()))

        scored: list[tuple[int, CanonicalClause]] = []
        for clause_id in candidate_ids:
            clause = self._clauses[clause_id]
            clause_tokens = set(_tokenize(clause.text))
            clause_tokens.update(_tokenize(" ".join(clause.keywords)))
            score = sum(freq for token, freq in query_counter.items() if token in clause_tokens)
            if score > 0:
                scored.append((score, clause))

        scored.sort(key=lambda item: (-item[0], item[1].clause_id))
        return [clause for _, clause in scored[:top_k]]

    def __len__(self) -> int:
        return len(self._clauses)


def build_clause_index_from_cpg(graphs_dir: str | Path) -> ClauseIndex:
    directory = Path(graphs_dir)
    index = ClauseIndex()

    for path in sorted(directory.glob("*.yaml")):
        payload_raw = cast(object, yaml.safe_load(path.read_text(encoding="utf-8")))
        if not isinstance(payload_raw, Mapping):
            continue

        payload = _normalize_mapping(cast(Mapping[object, object], payload_raw))
        graph_id = _to_string(payload.get("graph_id"))
        if not graph_id:
            continue

        graph_prefix = _graph_prefix(graph_id)
        nodes_raw = payload.get("nodes")
        if not isinstance(nodes_raw, Mapping):
            continue
        nodes = _normalize_mapping(cast(Mapping[object, object], nodes_raw))

        for node_key, node in nodes.items():
            if not isinstance(node, Mapping):
                continue
            node_map = _normalize_mapping(cast(Mapping[object, object], node))

            mandatory_actions = _to_string_list(node_map.get("mandatory_actions"))
            if not mandatory_actions:
                continue

            deadlines_raw = node_map.get("deadlines")
            deadlines = (
                _normalize_mapping(cast(Mapping[object, object], deadlines_raw))
                if isinstance(deadlines_raw, Mapping)
                else {}
            )

            node_name = _to_string(node_map.get("name"), default=node_key)
            node_description = _to_string(node_map.get("description"))
            section = _to_string(node_map.get("source_section"), default=node_name)
            evidence_level = _to_string(node_map.get("evidence_level"))
            recommendation_class = _to_string(node_map.get("recommendation_class"))
            source_quote = _extract_source_quote(node_map)

            for action in mandatory_actions:
                action_id = _to_string(action)
                if not action_id:
                    continue

                normalized_action = _normalize_action_for_id(action_id)
                base_clause_id = f"{graph_prefix}_{normalized_action}"
                clause_id = _dedupe_clause_id(base_clause_id, index)

                action_text = _action_to_text(action_id)
                text_parts = [part for part in [node_description, action_text] if part]
                clause_text = " ".join(text_parts)

                keywords = sorted(
                    set(_tokenize(node_name))
                    | set(_tokenize(action_id))
                    | set(_tokenize(action_text))
                )

                deadline_minutes = _to_int(deadlines.get(action_id))

                clause = CanonicalClause(
                    clause_id=clause_id,
                    text=clause_text,
                    heading=node_name,
                    keywords=keywords,
                    guideline_id=graph_id,
                    section=section,
                    evidence_level=evidence_level,
                    recommendation_class=recommendation_class,
                    source_quote=source_quote,
                    deadline_minutes=deadline_minutes,
                )
                index.add_clause(clause)

    return index


def _tokenize(text: str) -> list[str]:
    return _TOKEN_RE.findall(text.lower())


def _normalize_mapping(value: Mapping[object, object]) -> dict[str, object]:
    return {str(key): mapped_value for key, mapped_value in value.items()}


def _to_string(value: object, default: str = "") -> str:
    if isinstance(value, str):
        return value.strip()
    if value is None:
        return default
    return str(value).strip()


def _to_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    values = cast(list[object], value)
    return [item.strip() for item in (_to_string(v) for v in values) if item]


def _to_int(value: object) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return None


def _graph_prefix(graph_id: str) -> str:
    mapped = _GRAPH_PREFIX_MAP.get(graph_id)
    if mapped:
        return mapped

    tokens = [token for token in graph_id.upper().split("_") if token]
    if not tokens:
        return "GRAPH"
    return "_".join(tokens)


def _normalize_action_for_id(action: str) -> str:
    upper = action.upper()
    normalized = _NON_ALNUM_RE.sub("_", upper).strip("_")
    return normalized or "ACTION"


def _action_to_text(action_id: str) -> str:
    return action_id.replace("_", " ")


def _dedupe_clause_id(base_clause_id: str, index: ClauseIndex) -> str:
    if index.get_by_clause_id(base_clause_id) is None:
        return base_clause_id

    suffix = 2
    candidate = f"{base_clause_id}_{suffix}"
    while index.get_by_clause_id(candidate) is not None:
        suffix += 1
        candidate = f"{base_clause_id}_{suffix}"
    return candidate


def _extract_source_quote(node: dict[str, object]) -> str:
    source_quote = node.get("source_quote")
    if isinstance(source_quote, str) and source_quote.strip():
        return source_quote.strip()

    source_quotes = node.get("source_quotes")
    if isinstance(source_quotes, dict):
        quote_values = [
            str(value).strip()
            for value in cast(dict[object, object], source_quotes).values()
            if str(value).strip()
        ]
        if quote_values:
            return " | ".join(quote_values)

    source_guideline = node.get("source_guideline")
    if isinstance(source_guideline, str):
        return source_guideline.strip()

    return ""
