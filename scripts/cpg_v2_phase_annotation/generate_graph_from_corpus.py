"""Option B: Semi-auto graph generation from rag_corpus via LLM.

Takes a rag_corpus parsed.json and uses a 2-step LLM pipeline to produce
a CGA-Bench-compatible graph YAML with verbatim source quotes and page
numbers.

Step 1 — Recommendation Triage:
    LLM reads recommendations and identifies actionable, time-sensitive
    items with CGA-Bench action IDs, deadlines, and forbidden actions.

Step 2 — Graph Structuring:
    LLM organises triaged recommendations into a CPG graph with entry,
    plan, enquiry, and decision nodes.

All source_quote values MUST be verbatim substrings of the input
recommendations.  A post-hoc substring check rejects any hallucinated
quotes and marks them for manual correction.

Usage:
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/generate_graph_from_corpus.py \\
        --corpus data_release/v5.0/rag_corpus/ATS-ESICM-SCCM-2023-ARDS.parsed.json \\
        --graph-id ats_esicm_sccm_ards_2023 \\
        --guideline-name "ATS/ESICM/SCCM ARDS 2023" \\
        --endpoint http://localhost:8013/v1 \\
        --output cpg_model/graphs/auto/ats_esicm_sccm_ards_2023.yaml

    # Dry run
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/generate_graph_from_corpus.py \\
        --corpus ... --dry-run
"""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
import re
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

DEFAULT_ENDPOINT = "http://localhost:8013/v1"
DEFAULT_MODEL = "Qwen/Qwen3.5-397B-A17B-FP8"
DEFAULT_TEMPERATURE = 0.0
DEFAULT_MAX_TOKENS = 4096
REQUEST_TIMEOUT = 180

VALID_NODE_TYPES = {"decision", "plan", "action", "enquiry"}
VALID_REC_CLASSES = {"I", "IIa", "IIb", "III"}

# ---------------------------------------------------------------------------
# LLM call helper
# ---------------------------------------------------------------------------


class LLMUnavailable(Exception):
    """Raised when the LLM endpoint is unreachable or returns an error."""


def _llm_call(
    endpoint: str,
    model: str,
    system_prompt: str,
    user_prompt: str,
    temperature: float = DEFAULT_TEMPERATURE,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    api_key: str = "sk-no-key-required",
) -> str:
    """Call an OpenAI-compatible chat endpoint. Returns assistant content."""
    try:
        import httpx
    except ImportError:
        import urllib.error
        import urllib.request

        url = endpoint.rstrip("/") + "/chat/completions"
        body = json.dumps(
            {
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        ).encode()
        req = urllib.request.Request(
            url,
            data=body,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                data = json.loads(resp.read())
                return data["choices"][0]["message"]["content"]
        except (urllib.error.URLError, TimeoutError, KeyError) as exc:
            raise LLMUnavailable(f"LLM call failed: {exc}") from exc

    url = endpoint.rstrip("/") + "/chat/completions"
    headers = {"Authorization": f"Bearer {api_key}"}
    try:
        resp = httpx.post(
            url,
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "temperature": temperature,
                "max_tokens": max_tokens,
            },
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as exc:
        raise LLMUnavailable(f"LLM call failed: {exc}") from exc


def _extract_json(text: str) -> Any:
    """Extract JSON from LLM response, handling markdown code blocks."""
    # Strip /no_think tags
    text = re.sub(r"<\/?think>", "", text).strip()

    # Try direct parse
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try code block extraction
    match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Try finding first { or [
    for start_char, end_char in [("{", "}"), ("[", "]")]:
        start = text.find(start_char)
        if start >= 0:
            end = text.rfind(end_char)
            if end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    pass

    raise ValueError(f"Cannot extract JSON from LLM response: {text[:200]}")


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------

TRIAGE_SYSTEM = """/no_think
You are a clinical guideline analyst for CGA-Bench, a medical AI benchmark.
Your task: read CPG recommendations and identify which ones are actionable
and time-sensitive enough to become graph nodes.

Output a JSON array. Each element:
{
  "recommendation_id": "rec_N",
  "is_actionable": true/false,
  "summary": "1-line clinical summary",
  "action_ids": ["action_id_1", "action_id_2"],
  "forbidden_actions": ["forbidden_1"],
  "deadline_minutes": null or integer,
  "severity": "critical" | "high" | "moderate" | "low",
  "recommendation_class": "I" | "IIa" | "IIb" | "III",
  "evidence_level": "A" | "B" | "C",
  "source_quote": "EXACT verbatim substring from the recommendation text",
  "source_page": page_number_or_null
}

RULES:
- action_ids must be snake_case (e.g., "give_broad_spectrum_antibiotics", "order_lab_lactate")
- source_quote MUST be a verbatim copy-paste from the input text. Do NOT paraphrase.
- Only mark is_actionable=true if the recommendation has a concrete clinical action
- Skip background/history/methodology paragraphs
- forbidden_actions are contraindications or "do not" instructions
- deadline_minutes: extract from time-bound language (e.g., "within 1 hour" → 60)
"""

STRUCTURE_SYSTEM = """/no_think
You are a clinical workflow graph builder for CGA-Bench.
Build a CPG evaluation graph from triaged recommendations.

Output a JSON object with this EXACT schema:
{
  "graph_id": "string",
  "guideline_name": "string",
  "version": "2024.1",
  "metadata": {
    "source": "string",
    "doi": "string",
    "recommendation_system": "GRADE" or other,
    "description": "1-2 sentence summary"
  },
  "entry_node": "initial_assessment",
  "nodes": {
    "node_id": {
      "node_id": "string",
      "node_type": "decision" | "plan" | "action" | "enquiry",
      "name": "Human-readable name",
      "description": "What this node represents",
      "mandatory_actions": ["action_id_1"],
      "allowed_actions": ["action_id_1", "action_id_2"],
      "forbidden_actions": ["forbidden_1"],
      "deadlines": {"action_id_1": 60},
      "required_prior_actions": {},
      "recommendation_class": "I",
      "evidence_level": "B",
      "source_guideline": "Original guideline name",
      "source_section": "Section name",
      "source_page": page_number_or_null,
      "source_quote": "VERBATIM quote from recommendations",
      "source_recommendation_ids": ["rec_1", "rec_3"],
      "next_nodes": ["next_node_id"],
      "conditional_next": {}
    }
  }
}

RULES:
- entry_node is always "initial_assessment" (a decision node)
- mandatory_actions MUST be a subset of allowed_actions
- forbidden_actions must NOT overlap with allowed_actions
- source_quote MUST be verbatim from the triaged recommendations' source_quote field
- source_recommendation_ids MUST reference the recommendation_id values from the triaged input
- Graph should have 4-10 nodes: assessment → treatment bundles → monitoring → disposition
- Use conditional_next for severity stratification (e.g., {"state.severe": "severe_bundle"})
- Every node must have at least 1 mandatory_action
"""


def _build_triage_prompt(recommendations: list[dict[str, Any]], max_chars: int = 6000) -> str:
    """Build the user prompt for Step 1 (triage) from a single chunk."""
    parts: list[str] = []
    char_count = 0
    for rec in recommendations:
        text = rec.get("text", "")
        if not text or len(text) < 30:
            continue
        entry = json.dumps(
            {
                "recommendation_id": rec.get("recommendation_id", ""),
                "text": text[:2000],
                "strength": rec.get("strength", ""),
                "page": rec.get("page"),
            },
            ensure_ascii=False,
        )
        if char_count + len(entry) > max_chars:
            break
        parts.append(entry)
        char_count += len(entry)

    return "Recommendations to triage:\n[\n" + ",\n".join(parts) + "\n]"


def _chunk_recommendations(
    recommendations: list[dict[str, Any]],
    max_chars: int = 6000,
) -> list[list[dict[str, Any]]]:
    """Split recommendations into chunks that each fit within max_chars."""
    chunks: list[list[dict[str, Any]]] = []
    current_chunk: list[dict[str, Any]] = []
    char_count = 0

    for rec in recommendations:
        text = rec.get("text", "")
        if not text or len(text) < 30:
            continue
        entry_len = len(
            json.dumps(
                {
                    "recommendation_id": rec.get("recommendation_id", ""),
                    "text": text[:2000],
                    "strength": rec.get("strength", ""),
                    "page": rec.get("page"),
                },
                ensure_ascii=False,
            )
        )
        if char_count + entry_len > max_chars and current_chunk:
            chunks.append(current_chunk)
            current_chunk = []
            char_count = 0
        current_chunk.append(rec)
        char_count += entry_len

    if current_chunk:
        chunks.append(current_chunk)
    return chunks


def _slim_triaged(items: list[dict[str, Any]], max_items: int = 15) -> list[dict[str, Any]]:
    """Slim triaged items for Step 2 — keep essential fields, truncate quotes."""
    # Prioritize by severity: critical > high > moderate > low
    severity_order = {"critical": 0, "high": 1, "moderate": 2, "low": 3}
    sorted_items = sorted(items, key=lambda r: severity_order.get(r.get("severity", "low"), 3))

    slimmed: list[dict[str, Any]] = []
    for r in sorted_items[:max_items]:
        slimmed.append(
            {
                "recommendation_id": r.get("recommendation_id", ""),
                "summary": r.get("summary", ""),
                "action_ids": r.get("action_ids", []),
                "forbidden_actions": r.get("forbidden_actions", []),
                "deadline_minutes": r.get("deadline_minutes"),
                "severity": r.get("severity", "moderate"),
                "recommendation_class": r.get("recommendation_class", ""),
                "evidence_level": r.get("evidence_level", ""),
                "source_quote": (r.get("source_quote") or "")[:150],
                "source_page": r.get("source_page"),
            }
        )
    return slimmed


def _build_structure_prompt(
    triaged: list[dict[str, Any]],
    graph_id: str,
    guideline_name: str,
    doi: str,
) -> str:
    """Build the user prompt for Step 2 (graph structuring)."""
    actionable = [r for r in triaged if r.get("is_actionable")]
    if not actionable:
        actionable = triaged[:5]

    slimmed = _slim_triaged(actionable)
    triaged_json = json.dumps(slimmed, indent=2, ensure_ascii=False)

    return f"""Build a CGA-Bench graph from these triaged recommendations.

graph_id: {graph_id}
guideline_name: {guideline_name}
doi: {doi}

Triaged actionable recommendations:
{triaged_json}

Build the graph now. Output ONLY valid JSON."""


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


def validate_generated_graph(graph: dict[str, Any], corpus_text: str) -> list[str]:
    """Validate a generated graph. Returns list of error strings."""
    errors: list[str] = []

    # Top-level fields
    for field in ("graph_id", "entry_node", "nodes"):
        if field not in graph:
            errors.append(f"Missing top-level field: {field}")

    nodes = graph.get("nodes", {})
    if not isinstance(nodes, dict):
        errors.append("nodes must be a dict, not list")
        return errors

    entry = graph.get("entry_node", "")
    if entry and entry not in nodes:
        errors.append(f"entry_node '{entry}' not in nodes")

    norm_corpus = re.sub(r"\s+", " ", corpus_text).strip().lower()

    for node_id, node in nodes.items():
        if not isinstance(node, dict):
            errors.append(f"{node_id}: node is not a dict")
            continue

        # Node type
        ntype = node.get("node_type", "")
        if ntype not in VALID_NODE_TYPES:
            errors.append(f"{node_id}: invalid node_type '{ntype}'")

        # Mandatory actions
        mandatory = node.get("mandatory_actions", [])
        if not mandatory:
            errors.append(f"{node_id}: empty mandatory_actions")

        # mandatory ⊆ allowed
        allowed = set(node.get("allowed_actions", []))
        for m in mandatory:
            if m not in allowed:
                # Auto-fix: add to allowed
                node.setdefault("allowed_actions", [])
                if m not in node["allowed_actions"]:
                    node["allowed_actions"].append(m)

        # forbidden ∩ allowed = ∅
        forbidden = set(node.get("forbidden_actions", []))
        overlap = forbidden & allowed
        if overlap:
            errors.append(f"{node_id}: forbidden/allowed overlap: {overlap}")

        # Source quote verification
        quote = node.get("source_quote", "")
        if quote:
            norm_quote = re.sub(r"\s+", " ", quote).strip().lower()
            if len(norm_quote) > 10 and norm_quote not in norm_corpus:
                errors.append(f"{node_id}: source_quote not found in corpus (possible hallucination)")

        # Source recommendation IDs (warn-only for backwards compat)
        src_rec_ids = node.get("source_recommendation_ids")
        if not src_rec_ids or not isinstance(src_rec_ids, list):
            errors.append(f"{node_id}: missing or empty source_recommendation_ids")
        elif not all(isinstance(r, str) and r for r in src_rec_ids):
            errors.append(f"{node_id}: source_recommendation_ids contains invalid entries")

        # Source guideline
        if not node.get("source_guideline"):
            errors.append(f"{node_id}: missing source_guideline")

    return errors


# ---------------------------------------------------------------------------
# Generation pipeline
# ---------------------------------------------------------------------------


def generate_graph(
    corpus: dict[str, Any],
    graph_id: str,
    guideline_name: str,
    endpoint: str = DEFAULT_ENDPOINT,
    model: str = DEFAULT_MODEL,
    api_key: str = "sk-no-key-required",
) -> dict[str, Any]:
    """Generate a graph from rag_corpus via 2-step LLM pipeline."""
    recommendations = corpus.get("recommendations", []) or []
    doi = corpus.get("doi", "")

    if not recommendations:
        raise ValueError("Corpus has no recommendations")

    # Chunk large corpora to avoid context overflow
    chunks = _chunk_recommendations(recommendations)
    logger.info("Step 1: Triaging %d recommendations in %d chunk(s)...", len(recommendations), len(chunks))

    triaged: list[dict[str, Any]] = []
    for ci, chunk in enumerate(chunks, 1):
        logger.info("  Chunk %d/%d (%d recs)...", ci, len(chunks), len(chunk))
        triage_prompt = _build_triage_prompt(chunk)
        triage_response = _llm_call(endpoint, model, TRIAGE_SYSTEM, triage_prompt, api_key=api_key)
        chunk_triaged = _extract_json(triage_response)
        if isinstance(chunk_triaged, list):
            triaged.extend(chunk_triaged)
        else:
            logger.warning("  Chunk %d returned non-list: %s — skipping", ci, type(chunk_triaged))

    actionable_count = sum(1 for r in triaged if r.get("is_actionable"))
    logger.info("Step 1 complete: %d/%d actionable recommendations", actionable_count, len(triaged))

    logger.info("Step 2: Structuring graph...")
    structure_prompt = _build_structure_prompt(triaged, graph_id, guideline_name, doi)
    structure_response = _llm_call(
        endpoint,
        model,
        STRUCTURE_SYSTEM,
        structure_prompt,
        max_tokens=4096,
        api_key=api_key,
    )
    graph = _extract_json(structure_response)

    if not isinstance(graph, dict):
        raise ValueError(f"Step 2 returned non-dict: {type(graph)}")

    # Ensure graph_id is set
    graph["graph_id"] = graph_id
    graph.setdefault("guideline_name", guideline_name)

    # Build corpus text for validation
    corpus_text = "\n".join(rec.get("text", "") for rec in recommendations if isinstance(rec, dict))
    key_sections = corpus.get("key_sections", {}) or {}
    if isinstance(key_sections, dict):
        corpus_text += "\n" + "\n".join(str(v) for v in key_sections.values())

    # Validate
    errors = validate_generated_graph(graph, corpus_text)
    if errors:
        logger.warning("Generated graph has %d validation issues:", len(errors))
        for err in errors:
            logger.warning("  %s", err)

    # Add generation metadata
    graph["_generation_pipeline"] = {
        "method": "B",
        "version": "v1",
        "endpoint": endpoint,
        "model": model,
        "triaged_count": len(triaged),
        "actionable_count": actionable_count,
        "validation_errors": len(errors),
        "generated_at": datetime.now(UTC).isoformat(),
    }

    return graph


def write_graph(graph: dict[str, Any], output_path: Path, dry_run: bool = False) -> Path:
    """Write graph to YAML file."""
    if dry_run:
        nodes = graph.get("nodes", {})
        actions = set()
        for n in nodes.values():
            if isinstance(n, dict):
                actions.update(n.get("mandatory_actions", []))
        print(f"[DRY RUN] Would write {output_path}")
        print(f"  Nodes: {len(nodes)}, Unique mandatory actions: {len(actions)}")
        print(f"  Entry node: {graph.get('entry_node', 'N/A')}")
        return output_path

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        yaml.dump(
            graph,
            f,
            default_flow_style=False,
            allow_unicode=True,
            sort_keys=False,
            width=120,
        )
    logger.info("Written generated graph: %s (%d nodes)", output_path, len(graph.get("nodes", {})))
    return output_path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--corpus", type=Path, required=True, help="Path to rag_corpus parsed.json")
    parser.add_argument("--graph-id", required=True, help="Graph ID for the output (e.g., ats_esicm_sccm_ards_2023)")
    parser.add_argument("--guideline-name", default="", help="Human-readable guideline name")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="vLLM endpoint URL")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Model name")
    parser.add_argument("--api-key", default="sk-no-key-required", help="API key for vLLM endpoint")
    parser.add_argument("--output", type=Path, help="Output YAML path (default: cpg_model/graphs/auto/<graph_id>.yaml)")
    parser.add_argument("--dry-run", action="store_true", help="Generate but don't write")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if not args.corpus.exists():
        logger.error("Corpus file not found: %s", args.corpus)
        return 1

    corpus = json.loads(args.corpus.read_text(encoding="utf-8"))
    guideline_name = args.guideline_name or corpus.get("guideline_name", args.graph_id)

    try:
        graph = generate_graph(
            corpus=corpus,
            graph_id=args.graph_id,
            guideline_name=guideline_name,
            endpoint=args.endpoint,
            model=args.model,
            api_key=args.api_key,
        )
    except LLMUnavailable as exc:
        logger.error("LLM unavailable: %s", exc)
        return 2
    except ValueError as exc:
        logger.error("Generation failed: %s", exc)
        return 1

    output_path = args.output or Path(f"cpg_model/graphs/auto/{args.graph_id}.yaml")
    write_graph(graph, output_path, dry_run=args.dry_run)

    errors = graph.get("_generation_pipeline", {}).get("validation_errors", 0)
    if errors:
        print(f"\nGenerated with {errors} validation warnings — review recommended")
        return 1

    print(f"\nGraph generated successfully: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
