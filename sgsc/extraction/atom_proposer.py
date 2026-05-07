"""LLM-as-proposer: extract RecommendationAtom candidates from corpus text.

Uses an OpenAI-compatible chat endpoint to propose structured atoms
from guideline recommendation text.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Any

from sgsc.schemas.atom import RecommendationAtom

logger = logging.getLogger(__name__)

# ------------------------------------------------------------------
# Configuration
# ------------------------------------------------------------------

DEFAULT_TEMPERATURE = 0.2
DEFAULT_MAX_TOKENS = 8192
# Chunking: split large recommendation sets to avoid output truncation
_CHUNK_SIZE = 5

# Per-pass seeds for deterministic mode (Scenario B design).
# Different seeds per pass prevent sampling-path overlap while each pass
# remains individually reproducible.
PASS_SEEDS: dict[str, int] = {
    "positive": 42,
    "negative": 43,
    "process": 44,
    "default": 42,
}

SYSTEM_PROMPT = """\
You are a clinical guideline analyst. Extract structured RecommendationAtom \
objects from guideline recommendations.

For EACH actionable recommendation, output a JSON object with:
- atom_id: unique identifier (guideline_id + action, snake_case)
- source: {guideline_id, section, page (if known), quote (verbatim substring)}
- population: {inclusion: [...], exclusion: [...]}
- action: {canonical_id (snake_case verb_noun), action_type (see ACTION TYPES below)}
- constraint: {type (FORBIDDEN|REQUIRED|BEFORE|WITHIN|EXPECTED), activation_event (if any), deadline_minutes (if WITHIN)}
- sequence: {before: [...action_ids...], required_prior: [...action_ids...]}
- evidence: {system (AHA|GRADE|etc), recommendation_class, level}
- scenario_hooks: {boundary_variables: [...], counterfactual_pairs: [...]}

ACTION TYPES (14 categories):
  medication          — Administer or prescribe a drug
  lab                 — Order a laboratory test
  imaging             — Order an imaging study
  procedure           — Perform a clinical procedure
  consult             — Request specialist consultation
  reassess            — Re-evaluate patient status
  disposition         — Admission, discharge, or transfer decision
  medication_hold     — Hold or discontinue a specific medication (e.g. hold_ace_inhibitor)
  medication_avoid    — Avoid a medication entirely; use FORBIDDEN constraint (e.g. avoid_nsaid)
  monitoring          — Continuous or serial monitoring of a parameter (e.g. monitor_urine_output)
  dose_adjustment     — Adjust dosage based on clinical criteria (e.g. dose_adjust_renal)
  followup            — Schedule follow-up visit, referral, or recheck
  prevention          — Prophylactic or preventive measure (e.g. pre_hydration)
  discharge           — Discharge-related action or planning

Output a JSON array of atoms. Be exhaustive — extract every actionable recommendation, \
including negative recommendations (avoid/hold/withhold), monitoring requirements, \
dose adjustments, and follow-up plans.\
"""

# E3-b: Multi-pass extraction directives appended to SYSTEM_PROMPT per pass
_PASS_DIRECTIVES: dict[str, str] = {
    "positive": (
        "\n\nFOCUS THIS PASS: Extract only POSITIVE/PERFORMATIVE actions — what the "
        "clinician SHOULD DO. Medications to administer, labs to order, imaging to "
        "request, procedures, consultations, reassessments, dispositions, preventive "
        "measures. Use REQUIRED, WITHIN, or BEFORE constraints."
    ),
    "negative": (
        "\n\nFOCUS THIS PASS: Extract only NEGATIVE/PROHIBITIVE actions — what the "
        "clinician should AVOID, HOLD, or WITHHOLD. Medications to avoid or "
        "discontinue, contraindicated procedures, forbidden interventions. "
        "Use FORBIDDEN constraint and medication_hold/medication_avoid action types."
    ),
    "process": (
        "\n\nFOCUS THIS PASS: Extract only MONITORING and PROCESS actions — clinical "
        "parameters to monitor serially, dose adjustments based on response, "
        "scheduled follow-ups, and discharge planning actions. "
        "Use monitoring, dose_adjustment, followup, discharge action types."
    ),
}


@dataclass(frozen=True)
class AtomProposerConfig:
    """Configuration for the atom proposer."""

    endpoint: str
    model: str = "default"
    temperature: float = DEFAULT_TEMPERATURE
    max_tokens: int = DEFAULT_MAX_TOKENS
    api_key: str = "sk-no-key-required"
    timeout_seconds: float = 300.0
    enable_multi_pass: bool = False
    corpus_context_chars: int = 0
    top_p: float = 1.0
    deterministic: bool = False
    base_seed: int = 42


# ------------------------------------------------------------------
# LLM call helpers (ported from generate_graph_from_corpus.py)
# ------------------------------------------------------------------


def _llm_call(
    config: AtomProposerConfig,
    system_prompt: str,
    user_prompt: str,
    *,
    seed: int | None = None,
) -> str:
    """Call an OpenAI-compatible chat endpoint. Returns assistant content."""
    import httpx

    url = f"{config.endpoint.rstrip('/')}/chat/completions"
    payload: dict[str, Any] = {
        "model": config.model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": config.temperature,
        "top_p": config.top_p,
        "max_tokens": config.max_tokens,
        "chat_template_kwargs": {"enable_thinking": False},
    }
    if seed is not None:
        payload["seed"] = seed

    resp = httpx.post(
        url,
        json=payload,
        headers={"Authorization": f"Bearer {config.api_key}"},
        timeout=config.timeout_seconds,
    )
    resp.raise_for_status()
    data = resp.json()
    return str(data["choices"][0]["message"]["content"])


def _extract_json(text: str) -> Any:
    """Extract JSON from LLM response, handling thinking-model prefixes."""
    # Strip <think>…</think> blocks (content AND tags) for reasoning models
    text = re.sub(r"<think>[\s\S]*?</think>", "", text).strip()

    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    match = re.search(r"```(?:json)?\s*\n(.*?)```", text, re.DOTALL)
    if match:
        try:
            return json.loads(match.group(1))
        except json.JSONDecodeError:
            pass

    # Handle truncated code blocks (opening ```json but no closing ```)
    truncated = re.sub(r"^```(?:json)?\s*\n?", "", text)
    if truncated != text:
        truncated = truncated.rstrip("`").strip()
        try:
            return json.loads(truncated)
        except json.JSONDecodeError:
            pass

    # Find JSON structures using distinctive start patterns to avoid
    # matching brackets in thinking/reasoning text (e.g. "[R1]", "[Step 1]")
    for pattern in [r"\[\s*\{", r"\[\s*\"", r"\{\s*\""]:
        m = re.search(pattern, text)
        if m:
            start = m.start()
            end_char = "]" if text[start] == "[" else "}"
            end = text.rfind(end_char)
            if end > start:
                try:
                    return json.loads(text[start : end + 1])
                except json.JSONDecodeError:
                    continue

    raise ValueError(f"Could not extract JSON from LLM response: {text[:200]}...")


def _sanitize_atom_dict(item: dict[str, Any]) -> dict[str, Any]:
    """Fix common LLM type mismatches before Pydantic validation."""
    # Source: section must be str, page must be str|None
    src = item.get("source")
    if isinstance(src, dict):
        if src.get("section") is None:
            src["section"] = ""
        if src.get("page") is not None and not isinstance(src["page"], str):
            src["page"] = str(src["page"])
        if src.get("quote") is None:
            src["quote"] = ""
    # Evidence: all fields must be str (not None)
    ev = item.get("evidence")
    if isinstance(ev, dict):
        for k in ("recommendation_class", "level", "system"):
            if ev.get(k) is None:
                ev[k] = "unknown"
            elif not isinstance(ev[k], str):
                ev[k] = str(ev[k])
    # Population: default if missing
    if "population" not in item or item["population"] is None:
        item["population"] = {"inclusion": [], "exclusion": []}
    # Action: terminology must be dict, not None
    act = item.get("action")
    if isinstance(act, dict) and act.get("terminology") is None:
        act["terminology"] = {}
    # Sequence: default if missing
    if "sequence" not in item or item["sequence"] is None:
        item["sequence"] = {"before": [], "required_prior": []}
    # Scenario hooks: default if missing, fix nested lists
    hooks = item.get("scenario_hooks")
    if hooks is None or not isinstance(hooks, dict):
        item["scenario_hooks"] = {"boundary_variables": [], "counterfactual_pairs": []}
    else:
        # counterfactual_pairs items must be strings, not lists
        pairs = hooks.get("counterfactual_pairs", [])
        if isinstance(pairs, list):
            hooks["counterfactual_pairs"] = ["_vs_".join(p) if isinstance(p, list) else str(p) for p in pairs]
    return item


# ------------------------------------------------------------------
# Public API
# ------------------------------------------------------------------


def _format_rec_texts(
    recommendations: list[dict[str, Any]],
    offset: int = 0,
) -> list[str]:
    """Format recommendation dicts into text lines for the LLM prompt."""
    rec_texts = []
    for i, rec in enumerate(recommendations):
        text = rec.get("text", "")
        rec_id = rec.get("recommendation_id", f"R{offset + i + 1}")
        section = rec.get("section", "")
        page = rec.get("page", "")
        rec_texts.append(f"[{rec_id}] (Section: {section}, Page: {page})\n{text}")
    return rec_texts


def _parse_llm_atoms(
    raw: str,
    config: AtomProposerConfig,
) -> list[RecommendationAtom]:
    """Parse raw LLM text into validated RecommendationAtom list."""
    try:
        parsed = _extract_json(raw)
    except ValueError:
        logger.warning("Could not extract JSON from LLM response: %s", raw[:200])
        return []

    if isinstance(parsed, dict):
        parsed = [parsed]
    if not isinstance(parsed, list):
        logger.warning("LLM returned non-list: %s", type(parsed))
        return []

    atoms: list[RecommendationAtom] = []
    for item in parsed:
        try:
            if isinstance(item, dict):
                item = _sanitize_atom_dict(item)
            atom = RecommendationAtom.model_validate(item)
            atom.proposed_by = config.model
            atoms.append(atom)
        except Exception:
            logger.warning("Failed to parse atom from LLM output: %s", str(item)[:200])
            continue

    return atoms


_CORPUS_HEAD_RATIO = 0.7


def _build_corpus_context(corpus_text: str, max_chars: int) -> str:
    """Build truncated corpus context block for the user prompt (E3-c).

    Uses head+tail strategy: first 70% of budget from the start (overview,
    definitions) and last 30% from the end (appendices, contraindications).
    """
    if not corpus_text or max_chars <= 0:
        return ""
    if len(corpus_text) <= max_chars:
        return f"=== GUIDELINE CONTEXT ===\n{corpus_text}\n=== END CONTEXT ===\n\n"
    head_chars = int(max_chars * _CORPUS_HEAD_RATIO)
    tail_chars = max_chars - head_chars
    head = corpus_text[:head_chars]
    tail = corpus_text[-tail_chars:]
    omitted = len(corpus_text) - max_chars
    excerpt = f"{head}\n\n[... {omitted} chars omitted ...]\n\n{tail}"
    return f"=== GUIDELINE CONTEXT ===\n{excerpt}\n=== END CONTEXT ===\n\n"


def _extract_single_pass(
    config: AtomProposerConfig,
    guideline_id: str,
    recommendations: list[dict[str, Any]],
    system_prompt: str,
    corpus_context: str,
    *,
    seed: int | None = None,
) -> list[RecommendationAtom]:
    """Run one extraction pass over all recommendations (with chunking)."""
    chunks = [recommendations[i : i + _CHUNK_SIZE] for i in range(0, len(recommendations), _CHUNK_SIZE)]
    all_atoms: list[RecommendationAtom] = []

    for chunk_idx, chunk in enumerate(chunks):
        offset = chunk_idx * _CHUNK_SIZE
        rec_texts = _format_rec_texts(chunk, offset=offset)
        batch_header = f"(Batch {chunk_idx + 1}/{len(chunks)})\n\n" if len(chunks) > 1 else "\n"
        user_prompt = (
            f"Guideline: {guideline_id}\n"
            + batch_header
            + corpus_context
            + "Recommendations:\n\n"
            + "\n\n".join(rec_texts)
        )
        logger.info(
            "Chunk %d/%d: %d recommendations (R%d-R%d)",
            chunk_idx + 1,
            len(chunks),
            len(chunk),
            offset + 1,
            offset + len(chunk),
        )
        raw = _llm_call(config, system_prompt, user_prompt, seed=seed)
        chunk_atoms = _parse_llm_atoms(raw, config)
        logger.info(
            "Chunk %d/%d: %d atoms parsed",
            chunk_idx + 1,
            len(chunks),
            len(chunk_atoms),
        )
        all_atoms.extend(chunk_atoms)

    return all_atoms


def _dedup_atoms(atoms: list[RecommendationAtom]) -> list[RecommendationAtom]:
    """Deduplicate atoms by atom_id, keeping the first occurrence."""
    seen: set[str] = set()
    deduped: list[RecommendationAtom] = []
    for atom in atoms:
        if atom.atom_id not in seen:
            seen.add(atom.atom_id)
            deduped.append(atom)
    if len(deduped) < len(atoms):
        logger.info("Deduped %d -> %d atoms", len(atoms), len(deduped))
    return deduped


def propose_atoms(
    config: AtomProposerConfig,
    guideline_id: str,
    recommendations: list[dict[str, Any]],
    corpus_text: str = "",
) -> list[RecommendationAtom]:
    """Propose RecommendationAtom candidates from guideline recommendations.

    Supports single-pass (default) or multi-pass extraction (E3-b).
    When corpus_text is provided and corpus_context_chars > 0, includes
    guideline context in the prompt for deeper extraction (E3-c).

    Args:
        config: LLM endpoint configuration.
        guideline_id: Identifier for the guideline.
        recommendations: List of recommendation dicts with 'text' keys.
        corpus_text: Full guideline text for context injection (E3-c).

    Returns:
        List of proposed RecommendationAtom instances.
    """
    corpus_context = _build_corpus_context(corpus_text, config.corpus_context_chars)
    passes = list(_PASS_DIRECTIVES.keys()) if config.enable_multi_pass else ["default"]
    all_atoms: list[RecommendationAtom] = []

    for pass_name in passes:
        system_prompt = SYSTEM_PROMPT
        if pass_name in _PASS_DIRECTIVES:
            system_prompt += _PASS_DIRECTIVES[pass_name]

        seed: int | None = None
        if config.deterministic:
            seed = PASS_SEEDS.get(pass_name, config.base_seed)

        logger.info("Step 2 [%s pass]: Extracting atoms... (seed=%s)", pass_name, seed)
        pass_atoms = _extract_single_pass(
            config,
            guideline_id,
            recommendations,
            system_prompt,
            corpus_context,
            seed=seed,
        )
        logger.info("Pass '%s': %d atoms extracted", pass_name, len(pass_atoms))
        all_atoms.extend(pass_atoms)

    return _dedup_atoms(all_atoms)
