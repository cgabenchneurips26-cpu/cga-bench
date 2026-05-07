"""Method A: LLM-Assisted Source-Quote Extraction for C1-C12.

For a target CPG with a rag_corpus parsed.json file, query Qwen3.5-397B (or any
OpenAI-compatible vLLM endpoint) to extract a verbatim source_text quote that
supports each C1-C12 criterion score. Writes a JSON annotation block.

This is the Method A half of the beta-tier promotion pipeline defined in
docs/cpg_expansion_v7/10_annotation_pipeline.md. Pairs with Method B
(dual-LLM agreement) for final beta-authoritative promotion.

Usage:
    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/method_a_extract_quotes.py \
        --graph-id aha_chest_pain_evaluation \
        --rag-corpus-path data_release/v5.0/rag_corpus/AHA-2021-Chest-Pain-Guidelines.parsed.json \
        --endpoint http://localhost:8013/v1 \
        --model Qwen/Qwen3.5-397B-A17B-FP8 \
        --output reports/method_a_outputs/aha_chest_pain_evaluation.json

Design principles:
    - Temperature 0 for determinism.
    - One criterion per LLM call (isolation, smaller context, fewer hallucinations).
    - Response parsed as JSON; malformed responses trigger one retry then record
      an explicit failure.
    - source_text must be verifiable as substring-like against rag_corpus content.
      A strict post-hoc substring check is delegated to
      scripts/cpg_v2_phase_annotation/verify_beta_substring.py.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
import json
import logging
import os
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Criterion mode classification (observed empirically on alpha pilots
# aha_chest_pain_evaluation and ssc_sepsis_hour1_bundle, 2026-04-23):
#
#   "metadata": criterion value comes from publisher/year/DOI/GBD — fields
#       that live OUTSIDE the recommendations body and are often absent
#       from rag_corpus parsed.json. Method A scored these poorly on SSC
#       sepsis (C1-C6 all null). Use scripts/cpg_v2_phase2b/auto_extract_c1_c12.py
#       or existing candidate props instead.
#
#   "llm_semantic": criterion value requires semantic reading of the source
#       text — this is where Method A adds value. Alpha pilot aha_chest_pain
#       scored 4/4 on these after C11 prompt hardening.
#
# The --criteria CLI arg defaults to "llm_semantic" only; pass --criteria all
# to include metadata criteria (noisy — recommended only with parallel
# auto_extract_c1_c12.py + human review).
CRITERIA_MODE: dict[str, str] = {
    "C1": "metadata",
    "C2": "metadata",
    "C3": "metadata",
    "C4": "metadata",
    "C5": "metadata",
    "C6": "metadata",
    "C7": "llm_semantic",
    "C8": "metadata",  # contraindication count — LLM okay but regex is faster
    "C9": "llm_semantic",
    "C10": "metadata",  # time-bound count — LLM gets numbers but regex is faster
    "C11": "llm_semantic",
    "C12": "llm_semantic",
}
LLM_SEMANTIC_CRITERIA: list[str] = [c for c, mode in CRITERIA_MODE.items() if mode == "llm_semantic"]

# Criterion definitions lifted from docs/cpg_expansion_v7/06_selection_criteria_v2.md.
# Kept in-file to avoid cross-file drift; update here if 06_*.md changes.
CRITERIA: dict[str, dict[str, str]] = {
    "C1": {
        "name": "Tier-1 Society",
        "scale": "0/1",
        "rule": (
            "1 if the guideline is issued by a recognized Tier-1 medical society "
            "(AHA, ACC, ESC, WHO, IDSA, KDIGO, ADA, GOLD, GINA, ATS, ACOG, ABA, "
            "APA, AABB, ACMT, AES, WAO, EAACI, ACG, ACLS, PALS, NRP, SCCM, SSC, "
            "EAU, ERC, ESVS, AAO, OR equivalent national/international society). "
            "0 if only a hospital protocol or textbook excerpt."
        ),
    },
    "C2": {
        "name": "Evidence Grading System",
        "scale": "0/1/2",
        "rule": (
            "2 if a formal system is used (GRADE, SIGN, OCEBM, ILCOR evidence, "
            "Cochrane). 1 if a society system (AHA Class/LOE, ESC Class/LOE, ADA "
            "grading, ACOG LOE, GINA, GOLD). 0 if none."
        ),
    },
    "C3": {
        "name": "Systematic Review",
        "scale": "0/1",
        "rule": ("1 if the guideline was based on a systematic literature review (AGREE II Domain 3). 0 otherwise."),
    },
    "C4": {
        "name": "Recency",
        "scale": "0/1/2",
        "rule": "2 if publication year >= 2020; 1 if 2015-2019; 0 if < 2015 or unknown.",
    },
    "C5": {
        "name": "Documented Source",
        "scale": "0/1",
        "rule": "1 if a DOI or persistent URL exists. 0 otherwise.",
    },
    "C6": {
        "name": "Disease Burden",
        "scale": "0/1/2",
        "rule": ("2 if GBD Top-15 cause of death OR Lancet emergency condition. 1 if GBD Top-30. 0 if not ranked."),
    },
    "C7": {
        "name": "Time-to-Harm Severity",
        "scale": "0/1/2",
        "rule": (
            "2 if critical (minutes-to-hours, delay causes death or permanent "
            "disability). 1 if moderate (hours-to-days). 0 if mild (days-to-weeks)."
        ),
    },
    "C8": {
        "name": "Contraindication Rules",
        "scale": "0/1/2",
        "rule": (
            "2 if source document explicitly lists >= 5 contraindication / forbidden-action rules. 1 if 2-4. 0 if <= 1."
        ),
    },
    "C9": {
        "name": "Algorithm Figures",
        "scale": "0/1/2",
        "rule": ("2 if >= 3 algorithm / flowchart figures in source. 1 if 1-2. 0 if none."),
    },
    "C10": {
        "name": "Time Constraints",
        "scale": "0/1/2",
        "rule": ("2 if >= 5 explicit time-bound statements in source text. 1 if 2-4. 0 if <= 1."),
    },
    "C11": {
        "name": "Sequence Dependency",
        "scale": "0/1",
        "rule": (
            "1 if the source states action ordering. Ordering can be stated "
            "explicitly (e.g., 'obtain cultures BEFORE antibiotics') OR "
            "implied by time-bound statements that fix a sequence (e.g., "
            "'ECG within 10 min of arrival' + 'troponin at 0/1/3h' implies "
            "ECG-before-troponin), OR implied by action-prerequisite language "
            "('prior to X', 'after X is confirmed', 'initial evaluation' vs "
            "'subsequent'). If you find any such statement, return score=1 "
            "with that statement as source_text. 0 only if no ordering "
            "signal exists anywhere in the source."
        ),
    },
    "C12": {
        "name": "Conditional Branching",
        "scale": "0/1",
        "rule": (
            "1 if source contains explicit conditional logic (e.g., 'if MAP < 65 "
            "despite fluids, start vasopressor'). 0 otherwise."
        ),
    },
}

DEFAULT_ENDPOINT = os.environ.get("VLLM_ENDPOINT", "http://localhost:8013/v1")
DEFAULT_MODEL = "Qwen/Qwen3.5-397B-A17B-FP8"
DEFAULT_API_KEY = os.environ.get("VLLM_API_KEY", "sk-no-key-required")
DEFAULT_MAX_TOKENS = 2048
DEFAULT_TIMEOUT_SECONDS = 180.0


@dataclass
class CriterionResult:
    """Per-criterion LLM extraction result."""

    criterion: str
    score: int | None
    source_text: str | None
    page_or_section: str | None
    confidence: str | None
    raw_response: str
    error: str | None = None


@dataclass
class ExtractionReport:
    """Full Method A extraction report for one CPG."""

    graph_id: str
    guideline_name: str
    endpoint: str
    model: str
    results: dict[str, CriterionResult] = field(default_factory=dict)

    def to_json(self) -> dict[str, Any]:
        """Serialize for JSON output."""
        return {
            "graph_id": self.graph_id,
            "guideline_name": self.guideline_name,
            "method": "A",
            "endpoint": self.endpoint,
            "model": self.model,
            "results": {
                c: {
                    "criterion": r.criterion,
                    "score": r.score,
                    "source_text": r.source_text,
                    "page_or_section": r.page_or_section,
                    "confidence": r.confidence,
                    "error": r.error,
                }
                for c, r in self.results.items()
            },
        }


def build_prompt(criterion: str, parsed_source: dict[str, Any]) -> list[dict[str, str]]:
    """Build a chat-message list for one criterion.

    Args:
        criterion: One of C1-C12.
        parsed_source: rag_corpus parsed.json dict.

    Returns:
        List of {role, content} messages ready for OpenAI-compat API.
    """
    cdef = CRITERIA[criterion]
    guideline = parsed_source.get("guideline_name", "<unknown>")
    doi = parsed_source.get("doi", "<unknown>")
    recs = json.dumps(parsed_source.get("recommendations", []), indent=2)[:12000]
    keysec = json.dumps(parsed_source.get("key_sections", {}), indent=2)[:4000]

    system = (
        "/no_think\n"
        "You are a clinical-guideline annotator. Extract a verbatim quote from "
        "the source document that supports the criterion score. Respond with a "
        "single JSON object only, no prose, no reasoning. If no supporting "
        "quote exists, set source_text to null and score to the default "
        '"absent" value appropriate to the criterion\'s scale. Your quote '
        "must be an EXACT substring of the source — no paraphrasing, no "
        "summarization. Output the JSON object immediately and stop."
    )
    user = (
        f"Criterion: {criterion} — {cdef['name']} ({cdef['scale']})\n"
        f"Scoring rule: {cdef['rule']}\n\n"
        f"Guideline: {guideline}\n"
        f"DOI: {doi}\n\n"
        f"Source recommendations:\n{recs}\n\n"
        f"Source key sections:\n{keysec}\n\n"
        "Respond now with JSON fields: "
        '{"criterion": "<name>", "score": <int>, "source_text": <str|null>, '
        '"page_or_section": <str|null>, "confidence": "high"|"medium"|"low"}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def call_llm_once(
    messages: list[dict[str, str]],
    endpoint: str,
    model: str,
    api_key: str,
    max_tokens: int = DEFAULT_MAX_TOKENS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Single LLM call returning raw text content."""
    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=endpoint, timeout=timeout)
    response = client.chat.completions.create(
        model=model,
        messages=messages,
        temperature=0,
        max_tokens=max_tokens,
        extra_body={"chat_template_kwargs": {"enable_thinking": False}},
    )
    msg = response.choices[0].message
    content = msg.content
    if content is None:
        content = getattr(msg, "reasoning", None) or ""
    return content or ""


def parse_response(raw: str, criterion: str) -> dict[str, Any] | None:
    """Parse the LLM response as JSON. Return None on failure."""
    if not raw:
        return None
    # Strip common code-fence wrappers.
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
    # Trim to the outermost JSON braces.
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start : end + 1])
    except json.JSONDecodeError:
        logger.warning("JSON parse failed for %s, raw: %s", criterion, raw[:200])
        return None


def extract_one_criterion(
    criterion: str,
    parsed_source: dict[str, Any],
    endpoint: str,
    model: str,
    api_key: str,
) -> CriterionResult:
    """Run Method A for a single criterion with one retry."""
    messages = build_prompt(criterion, parsed_source)

    for attempt in range(2):
        try:
            raw = call_llm_once(messages, endpoint, model, api_key)
        except Exception as exc:
            raw = ""
            err = f"call error attempt {attempt + 1}: {exc}"
            logger.warning("%s for %s", err, criterion)
            if attempt == 1:
                return CriterionResult(
                    criterion=criterion,
                    score=None,
                    source_text=None,
                    page_or_section=None,
                    confidence=None,
                    raw_response="",
                    error=err,
                )
            continue

        parsed = parse_response(raw, criterion)
        if parsed is None:
            if attempt == 1:
                return CriterionResult(
                    criterion=criterion,
                    score=None,
                    source_text=None,
                    page_or_section=None,
                    confidence=None,
                    raw_response=raw,
                    error="unparseable JSON after 2 attempts",
                )
            continue

        return CriterionResult(
            criterion=criterion,
            score=parsed.get("score"),
            source_text=parsed.get("source_text"),
            page_or_section=parsed.get("page_or_section"),
            confidence=parsed.get("confidence"),
            raw_response=raw,
            error=None,
        )

    return CriterionResult(
        criterion=criterion,
        score=None,
        source_text=None,
        page_or_section=None,
        confidence=None,
        raw_response="",
        error="unreachable fallthrough",
    )


def run_method_a(
    graph_id: str,
    rag_corpus_path: Path,
    endpoint: str,
    model: str,
    api_key: str,
    criteria: list[str] | None = None,
) -> ExtractionReport:
    """Run Method A over a list of criteria for one CPG."""
    parsed_source = json.loads(rag_corpus_path.read_text(encoding="utf-8"))
    actual_graph_id = parsed_source.get("graph_id", graph_id)
    if actual_graph_id != graph_id:
        logger.warning(
            "rag_corpus graph_id %s mismatches requested %s",
            actual_graph_id,
            graph_id,
        )
    report = ExtractionReport(
        graph_id=graph_id,
        guideline_name=parsed_source.get("guideline_name", "<unknown>"),
        endpoint=endpoint,
        model=model,
    )
    targets = criteria or list(CRITERIA.keys())
    for c in targets:
        logger.info("Extracting %s for %s ...", c, graph_id)
        report.results[c] = extract_one_criterion(c, parsed_source, endpoint, model, api_key)
    return report


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-id", required=True, help="CPG graph_id (e.g., aha_chest_pain_evaluation)")
    parser.add_argument(
        "--rag-corpus-path",
        required=True,
        type=Path,
        help="Path to rag_corpus parsed.json for this CPG",
    )
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT)
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument(
        "--criteria",
        default="llm_semantic",
        help=(
            "Comma-separated criterion IDs (C1..C12), 'all' for every C1-C12, "
            "or 'llm_semantic' (default, C7/C9/C11/C12 only) — the criteria "
            "where Method A is reliable. Metadata criteria (C1-C6/C8/C10) "
            "produced poor results on SSC sepsis pilot (2026-04-23) because "
            "their signals live outside the recommendations body; use "
            "scripts/cpg_v2_phase2b/auto_extract_c1_c12.py for those."
        ),
    )
    parser.add_argument(
        "--output",
        required=True,
        type=Path,
        help="Output JSON path (parent dir created if missing)",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.criteria == "all":
        criteria = list(CRITERIA.keys())
    elif args.criteria == "llm_semantic":
        criteria = LLM_SEMANTIC_CRITERIA[:]
    else:
        criteria = [c.strip() for c in args.criteria.split(",") if c.strip()]
    invalid = [c for c in criteria if c not in CRITERIA]
    if invalid:
        raise SystemExit(f"Unknown criteria: {invalid}. Valid: {list(CRITERIA.keys())}")

    report = run_method_a(
        graph_id=args.graph_id,
        rag_corpus_path=args.rag_corpus_path,
        endpoint=args.endpoint,
        model=args.model,
        api_key=args.api_key,
        criteria=criteria,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report.to_json(), indent=2), encoding="utf-8")
    logger.info("Wrote %s", args.output)

    # Brief console summary.
    print(f"\nMethod A extraction complete for {args.graph_id}")
    print(f"Criteria covered: {len(report.results)}")
    errors = [c for c, r in report.results.items() if r.error]
    if errors:
        print(f"  errors: {errors}")
    for c in criteria:
        r = report.results[c]
        preview = (r.source_text or "")[:60].replace("\n", " ")
        print(
            f"  {c}: score={r.score:<4} quote='{preview}...'" if r.score is not None else f"  {c}: FAILED ({r.error})"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
