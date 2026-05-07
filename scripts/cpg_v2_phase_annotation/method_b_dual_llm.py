"""Method B: Dual-LLM Score Agreement for C1-C12 Annotation.

For a target CPG, queries two independent vLLM endpoints on every C1-C12
criterion with a scoring-only prompt (no prose) and computes agreement
metrics (Cohen's kappa, exact agreement). Pairs with Method A quote
extraction to produce a beta-authoritative annotation record per
docs/cpg_expansion_v7/10_annotation_pipeline.md §3.

The two endpoints SHOULD be architecturally distinct models (e.g.,
Qwen 397B + GPT-oss 120B). If only one distinct model is available
(e.g., Qwen 397B on two ports) the script still runs and prints a
warning — the kappa number will be near-unity and NOT a valid
inter-architecture agreement measure.

Usage (two distinct models):

    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/method_b_dual_llm.py \
        --graph-id aha_chest_pain_evaluation \
        --rag-corpus-path data_release/v5.0/rag_corpus/AHA-2021-Chest-Pain-Guidelines.parsed.json \
        --endpoint-a http://localhost:8013/v1 --model-a Qwen/Qwen3.5-397B-A17B-FP8 \
        --endpoint-b http://localhost:8013/v1 --model-b gemma4-31b-it \
        --output reports/method_b_outputs/aha_chest_pain_evaluation.json

Usage (same-family fallback with explicit warning):

    PYTHONPATH=. python scripts/cpg_v2_phase_annotation/method_b_dual_llm.py \
        --graph-id aha_chest_pain_evaluation \
        --rag-corpus-path ... \
        --endpoint-a http://localhost:8013/v1 \
        --endpoint-b http://localhost:8013/v1 \
        --model-a Qwen/Qwen3.5-397B-A17B-FP8 --model-b Qwen/Qwen3.5-397B-A17B-FP8 \
        --allow-same-family \
        --output ...
"""

from __future__ import annotations

import argparse
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
import json
import logging
from pathlib import Path
from typing import Any

# Reuse Method A criteria + prompt helpers to keep a single source of truth.
from scripts.cpg_v2_phase_annotation.method_a_extract_quotes import (
    CRITERIA,
    DEFAULT_API_KEY,
    DEFAULT_TIMEOUT_SECONDS,
    call_llm_once,
    parse_response,
)

logger = logging.getLogger(__name__)

DEFAULT_MAX_TOKENS_B = 192  # smaller than Method A: no long quotes needed


@dataclass(frozen=True)
class EndpointSpec:
    """One LLM endpoint configuration."""

    tag: str  # "A" or "B"
    endpoint: str
    model: str
    api_key: str


@dataclass
class RaterScore:
    """Per-criterion score from one rater."""

    criterion: str
    score: int | None
    brief_justification: str | None
    raw_response: str
    error: str | None = None


def build_method_b_prompt(criterion: str, parsed_source: dict[str, Any]) -> list[dict[str, str]]:
    """Score-only prompt (no verbatim quote, shorter).

    Keeping the quote-free prompt prevents LLM B from conditioning on LLM A's
    quote (the two calls are independent) and keeps the token budget small.
    """
    cdef = CRITERIA[criterion]
    guideline = parsed_source.get("guideline_name", "<unknown>")
    doi = parsed_source.get("doi", "<unknown>")
    recs = json.dumps(parsed_source.get("recommendations", []), indent=2)[:12000]
    keysec = json.dumps(parsed_source.get("key_sections", {}), indent=2)[:4000]

    system = (
        "You are a clinical-guideline annotator. Score the criterion below "
        "against the source document. Respond ONLY with a single JSON object. "
        "Do not include quotes, prose, or paraphrase. Be strict against the "
        "scoring rule."
    )
    user = (
        f"Criterion: {criterion} — {cdef['name']} ({cdef['scale']})\n"
        f"Scoring rule: {cdef['rule']}\n\n"
        f"Guideline: {guideline}\n"
        f"DOI: {doi}\n\n"
        f"Source recommendations:\n{recs}\n\n"
        f"Source key sections:\n{keysec}\n\n"
        'Respond now: {"criterion": "<name>", "score": <int>, '
        '"brief_justification": "<short string, max 20 words>"}'
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def score_one_rater_one_criterion(rater: EndpointSpec, criterion: str, parsed_source: dict[str, Any]) -> RaterScore:
    """Single (rater, criterion) LLM call with one retry."""
    messages = build_method_b_prompt(criterion, parsed_source)
    for attempt in range(2):
        try:
            raw = call_llm_once(
                messages,
                rater.endpoint,
                rater.model,
                rater.api_key,
                max_tokens=DEFAULT_MAX_TOKENS_B,
                timeout=DEFAULT_TIMEOUT_SECONDS,
            )
        except Exception as exc:
            if attempt == 1:
                return RaterScore(
                    criterion=criterion,
                    score=None,
                    brief_justification=None,
                    raw_response="",
                    error=f"call error: {exc}",
                )
            continue
        parsed = parse_response(raw, criterion)
        if parsed is None:
            if attempt == 1:
                return RaterScore(
                    criterion=criterion,
                    score=None,
                    brief_justification=None,
                    raw_response=raw,
                    error="unparseable JSON",
                )
            continue
        return RaterScore(
            criterion=criterion,
            score=parsed.get("score"),
            brief_justification=parsed.get("brief_justification"),
            raw_response=raw,
        )
    return RaterScore(criterion, None, None, "", error="unreachable")


def run_method_b_single(
    rater: EndpointSpec, parsed_source: dict[str, Any], criteria: list[str]
) -> dict[str, RaterScore]:
    """Run one rater over the full criteria list."""
    results: dict[str, RaterScore] = {}
    for c in criteria:
        logger.info("[%s] scoring %s ...", rater.tag, c)
        results[c] = score_one_rater_one_criterion(rater, c, parsed_source)
    return results


def cohen_kappa(labels_a: list[int | None], labels_b: list[int | None]) -> float | None:
    """Cohen's kappa for categorical labels (scores treated as categories).

    Returns None if any pair has a missing score or fewer than 2 valid pairs.
    """
    pairs = [(a, b) for a, b in zip(labels_a, labels_b) if a is not None and b is not None]
    if len(pairs) < 2:
        return None
    categories = sorted({v for pair in pairs for v in pair})
    n = len(pairs)
    if n == 0:
        return None
    p_o = sum(1 for a, b in pairs if a == b) / n
    # Marginals
    marg_a = {c: sum(1 for a, _ in pairs if a == c) / n for c in categories}
    marg_b = {c: sum(1 for _, b in pairs if b == c) / n for c in categories}
    p_e = sum(marg_a[c] * marg_b[c] for c in categories)
    if p_e >= 1.0:
        # All-equal marginals — kappa undefined; return observed agreement as proxy.
        return 1.0 if p_o == 1.0 else 0.0
    return (p_o - p_e) / (1.0 - p_e)


def run_method_b(
    graph_id: str,
    rag_corpus_path: Path,
    rater_a: EndpointSpec,
    rater_b: EndpointSpec,
    criteria: list[str],
    parallel: bool = True,
) -> dict[str, Any]:
    """Run both raters over criteria, compute agreement metrics."""
    parsed_source = json.loads(rag_corpus_path.read_text(encoding="utf-8"))

    if parallel:
        with ThreadPoolExecutor(max_workers=2) as pool:
            fut_a = pool.submit(run_method_b_single, rater_a, parsed_source, criteria)
            fut_b = pool.submit(run_method_b_single, rater_b, parsed_source, criteria)
            scores_a = fut_a.result()
            scores_b = fut_b.result()
    else:
        scores_a = run_method_b_single(rater_a, parsed_source, criteria)
        scores_b = run_method_b_single(rater_b, parsed_source, criteria)

    labels_a = [scores_a[c].score for c in criteria]
    labels_b = [scores_b[c].score for c in criteria]
    kappa = cohen_kappa(labels_a, labels_b)
    disagreements = [
        {
            "criterion": c,
            "score_a": scores_a[c].score,
            "score_b": scores_b[c].score,
            "delta": (
                abs(scores_a[c].score - scores_b[c].score)
                if scores_a[c].score is not None and scores_b[c].score is not None
                else None
            ),
            "justification_a": scores_a[c].brief_justification,
            "justification_b": scores_b[c].brief_justification,
        }
        for c in criteria
        if scores_a[c].score != scores_b[c].score
    ]

    return {
        "graph_id": graph_id,
        "guideline_name": parsed_source.get("guideline_name"),
        "method": "B",
        "rater_a": {"tag": rater_a.tag, "endpoint": rater_a.endpoint, "model": rater_a.model},
        "rater_b": {"tag": rater_b.tag, "endpoint": rater_b.endpoint, "model": rater_b.model},
        "criteria": criteria,
        "per_criterion": {
            c: {
                "score_a": scores_a[c].score,
                "score_b": scores_b[c].score,
                "justification_a": scores_a[c].brief_justification,
                "justification_b": scores_b[c].brief_justification,
                "error_a": scores_a[c].error,
                "error_b": scores_b[c].error,
            }
            for c in criteria
        },
        "agreement": {
            "cohen_kappa": kappa,
            "exact_agreement_rate": (
                sum(1 for c in criteria if scores_a[c].score == scores_b[c].score) / len(criteria) if criteria else 0.0
            ),
            "disagreements": disagreements,
        },
    }


def main() -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--graph-id", required=True)
    parser.add_argument("--rag-corpus-path", required=True, type=Path)
    parser.add_argument("--endpoint-a", required=True)
    parser.add_argument("--model-a", required=True)
    parser.add_argument("--endpoint-b", required=True)
    parser.add_argument("--model-b", required=True)
    parser.add_argument("--api-key", default=DEFAULT_API_KEY)
    parser.add_argument("--criteria", default="all")
    parser.add_argument(
        "--allow-same-family",
        action="store_true",
        help="Suppress the warning when both models are the same family (use for sanity only)",
    )
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--no-parallel", action="store_true")
    parser.add_argument("--log-level", default="INFO", choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    criteria = (
        list(CRITERIA.keys()) if args.criteria == "all" else [c.strip() for c in args.criteria.split(",") if c.strip()]
    )
    invalid = [c for c in criteria if c not in CRITERIA]
    if invalid:
        raise SystemExit(f"Unknown criteria: {invalid}")

    rater_a = EndpointSpec(tag="A", endpoint=args.endpoint_a, model=args.model_a, api_key=args.api_key)
    rater_b = EndpointSpec(tag="B", endpoint=args.endpoint_b, model=args.model_b, api_key=args.api_key)

    # Same-family guard.
    def family(model: str) -> str:
        m = model.lower()
        if "qwen" in m:
            return "qwen"
        if "gpt" in m or "oss" in m:
            return "gpt-oss"
        if "gemma" in m:
            return "gemma"
        if "nemotron" in m:
            return "nemotron"
        if "llama" in m:
            return "llama"
        return "unknown"

    fam_a, fam_b = family(rater_a.model), family(rater_b.model)
    if fam_a == fam_b and fam_a != "unknown" and not args.allow_same_family:
        raise SystemExit(
            f"Refusing to run: both models in the same family ({fam_a}). "
            "Pass --allow-same-family to override (sanity check only)."
        )
    if fam_a == fam_b:
        logger.warning(
            "Both raters are in family '%s' — inter-rater agreement number will NOT be "
            "a valid inter-architecture measure. Use for sanity check only.",
            fam_a,
        )

    report = run_method_b(
        graph_id=args.graph_id,
        rag_corpus_path=args.rag_corpus_path,
        rater_a=rater_a,
        rater_b=rater_b,
        criteria=criteria,
        parallel=not args.no_parallel,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, indent=2), encoding="utf-8")
    logger.info("Wrote %s", args.output)

    print(f"\nMethod B dual-LLM scoring complete for {args.graph_id}")
    print(f"Cohen's kappa: {report['agreement']['cohen_kappa']}")
    print(f"Exact agreement rate: {report['agreement']['exact_agreement_rate']:.2%}")
    for d in report["agreement"]["disagreements"]:
        print(f"  DISAGREE {d['criterion']}: A={d['score_a']} B={d['score_b']} (delta={d['delta']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
