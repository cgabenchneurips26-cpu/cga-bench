"""TCC-Free Evaluator (CRES-1A): catalogue-free LLM-judge evaluator.

Purpose
-------
Defends against the "circularity" attack on TCC: if a completely separate
evaluator that never sees the CPG catalogue (cpg_model/graphs/*.yaml)
agrees with TCC on violation patterns, then TCC's verdicts reflect a
structural property of the trace, not the catalogue itself.

Design
------
- Inputs: EpisodeLog-like dict (or cached verdict record) + raw guideline text.
- Uses BM25 retrieval over parsed guideline JSONs to surface the top-k
  recommendations relevant to the trace's scenario, then asks an LLM
  (GPT-4o by default) to judge the trace against the retrieved guideline
  excerpts.
- Returns a list of TCCFreeViolation records plus a binary verdict.

This module has **zero imports** from cpg_engine or assessor_core. Its only
dependencies are the LLM provider abstraction (agent_runner.llm_provider)
and the BM25 index (agent_runner.rag_agent.BM25Index) — both of which are
also used by the regular RAG agent and carry no TCC-specific knowledge.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
import json
import math
from pathlib import Path
import re
from typing import Any

from cga_bench.agent_runner.llm_provider import (
    BaseLLMProvider,
    LLMBackend,
    LLMConfig,
    LLMMessage,
    LLMProviderFactory,
    safe_json_parse,
)

# ---------------------------------------------------------------------------
# Local BM25 index
# ---------------------------------------------------------------------------
#
# Deliberately inlined rather than imported from agent_runner.rag_agent to
# keep the module's transitive import graph free of cpg_model / cpg_engine /
# scenario_engine. The CRES-1A circularity defense requires the evaluator
# to share no loaded code with the TCC scoring pipeline — even indirectly.
# (The algorithm is equivalent to rag_agent.BM25Index.)


class BM25Index:
    """Minimal BM25 index over documents with a `content` string field."""

    def __init__(self, k1: float = 1.5, b: float = 0.75) -> None:
        self.k1 = k1
        self.b = b
        self.documents: list[dict[str, Any]] = []
        self.doc_freqs: dict[str, int] = defaultdict(int)
        self.doc_lengths: list[int] = []
        self.avg_doc_length: float = 0.0
        self.term_docs: dict[str, list[int]] = defaultdict(list)

    def _tokenize(self, text: str) -> list[str]:
        return re.findall(r"\b[a-z0-9]+\b", text.lower())

    def add_documents(self, documents: list[dict[str, Any]]) -> None:
        for doc in documents:
            doc_idx = len(self.documents)
            self.documents.append(doc)
            tokens = self._tokenize(doc.get("content", ""))
            self.doc_lengths.append(len(tokens))
            seen: set[str] = set()
            for token in tokens:
                if token not in seen:
                    self.doc_freqs[token] += 1
                    self.term_docs[token].append(doc_idx)
                    seen.add(token)
        if self.doc_lengths:
            self.avg_doc_length = sum(self.doc_lengths) / len(self.doc_lengths)

    def search(self, query: str, top_k: int = 5) -> list[tuple[int, float]]:
        scores: dict[int, float] = defaultdict(float)
        n_docs = len(self.documents)
        for token in self._tokenize(query):
            if token not in self.doc_freqs:
                continue
            df = self.doc_freqs[token]
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1)
            for doc_idx in self.term_docs[token]:
                doc_tokens = self._tokenize(self.documents[doc_idx].get("content", ""))
                tf = doc_tokens.count(token)
                doc_len = self.doc_lengths[doc_idx] or 1
                num = tf * (self.k1 + 1)
                denom = tf + self.k1 * (1 - self.b + self.b * doc_len / max(self.avg_doc_length, 1.0))
                scores[doc_idx] += idf * (num / denom)
        return sorted(scores.items(), key=lambda x: x[1], reverse=True)[:top_k]


# ---------------------------------------------------------------------------
# Domain → guideline corpus mapping
# ---------------------------------------------------------------------------

# Maps scenario_id prefix tokens to the `.parsed.json` filename in the
# guideline corpus. 25 CPG graphs collapse to 24 distinct corpus files
# (Universal-Clinical-Safety covers multi-domain fallback). Unknown prefixes
# fall back to Universal-Clinical-Safety.
_DEFAULT_CORPUS_DIR = Path(__file__).resolve().parents[1] / "data_release" / "v5.0" / "rag_corpus"

_PREFIX_TO_CORPUS: dict[str, str] = {
    "aabb": "AABB-2016-Transfusion-Guidelines.parsed.json",
    "aba": "ABA-2018-Burn-Resuscitation.parsed.json",
    "acls": "AHA-2020-ACLS-Guidelines.parsed.json",
    "acog": "ACOG-2017-Obstetric-Hemorrhage.parsed.json",
    "adhf": "AHA-2022-Heart-Failure-Guidelines.parsed.json",
    "af": "ESC-2020-AF-Guidelines.parsed.json",
    "aha": "AHA-2021-Chest-Pain-Guidelines.parsed.json",
    "aki": "KDIGO-2012-AKI-Guidelines.parsed.json",
    "anaph": "WAO-2020-Anaphylaxis-Guidelines.parsed.json",
    "apa": "APA-2024-Agitation-Management.parsed.json",
    "asthma": "GINA-2024-Asthma-Exacerbation.parsed.json",
    "caki": "KDIGO-2012-Contrast-AKI.parsed.json",
    "cap": "ATS-IDSA-2019-CAP-Guidelines.parsed.json",
    "cardiogenic": "AHA-2022-Heart-Failure-Guidelines.parsed.json",
    "chest": "AHA-2021-Chest-Pain-Guidelines.parsed.json",
    "ckd": "KDIGO-2012-AKI-Guidelines.parsed.json",
    "contrast": "KDIGO-2012-Contrast-AKI.parsed.json",
    "copd": "GOLD-2024-COPD-Report.parsed.json",
    "dka": "ADA-2009-DKA-Management.parsed.json",
    "emergency": "AHA-2017-Hypertensive-Emergency.parsed.json",
    "gi": "ACG-2021-GI-Bleeding-Guidelines.parsed.json",
    "gib": "ACG-2021-GI-Bleeding-Guidelines.parsed.json",
    "hemorrhagic": "ACOG-2017-Obstetric-Hemorrhage.parsed.json",
    "hf": "AHA-2022-Heart-Failure-Guidelines.parsed.json",
    "hfpef": "AHA-2022-Heart-Failure-Guidelines.parsed.json",
    "hfref": "AHA-2022-Heart-Failure-Guidelines.parsed.json",
    "htn": "AHA-2017-Hypertensive-Emergency.parsed.json",
    "kdigo": "KDIGO-2012-AKI-Guidelines.parsed.json",
    "mening": "IDSA-2004-Meningitis-Guidelines.parsed.json",
    "nstemi": "AHA-2021-Chest-Pain-Guidelines.parsed.json",
    "pals": "AHA-2020-PALS-Guidelines.parsed.json",
    "pe": "ESC-2019-PE-Guidelines.parsed.json",
    "safety": "Universal-Clinical-Safety.parsed.json",
    "se": "AES-2016-Status-Epilepticus.parsed.json",
    "sepsis": "SSC-2021-Sepsis-Hour1-Bundle.parsed.json",
    "septic": "SSC-2021-Sepsis-Hour1-Bundle.parsed.json",
    "ssc": "SSC-2021-Sepsis-Hour1-Bundle.parsed.json",
    "stemi": "AHA-2021-Chest-Pain-Guidelines.parsed.json",
    "stroke": "AHA-2019-Stroke-Guidelines.parsed.json",
    "tox": "AACT-Toxicology-Management.parsed.json",
    "toxicology": "AACT-Toxicology-Management.parsed.json",
    "unstable": "AHA-2021-Chest-Pain-Guidelines.parsed.json",
    "warfarin": "ACG-2021-GI-Bleeding-Guidelines.parsed.json",
}

_FALLBACK_CORPUS = "Universal-Clinical-Safety.parsed.json"


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TCCFreeViolation:
    """A violation reported by the catalogue-free evaluator."""

    violation_type: str  # one of: omission commission timing sequence deviation
    action_involved: str | None
    expected_action: str | None
    description: str
    source_recommendation: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "violation_type": self.violation_type,
            "action_involved": self.action_involved,
            "expected_action": self.expected_action,
            "description": self.description,
            "source_recommendation": self.source_recommendation,
        }


@dataclass
class TCCFreeVerdict:
    """The full output of TCCFreeEvaluator.evaluate()."""

    scenario_id: str
    run_index: int
    model: str
    verdict_binary: str  # "pass" | "fail"
    violations: list[TCCFreeViolation] = field(default_factory=list)
    reasoning: str = ""
    tokens_used: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "run_index": self.run_index,
            "model": self.model,
            "verdict_binary": self.verdict_binary,
            "violations": [v.to_dict() for v in self.violations],
            "reasoning": self.reasoning,
            "tokens_used": self.tokens_used,
        }


@dataclass
class TCCFreeConfig:
    """Configuration for TCCFreeEvaluator. All values must be explicitly set."""

    corpus_dir: Path
    prompt_template_path: Path
    llm_config: LLMConfig
    top_k_retrieval: int = 10
    max_excerpts_per_domain: int = 5

    def __post_init__(self) -> None:
        if not self.corpus_dir.exists():
            raise FileNotFoundError(f"Guideline corpus dir not found: {self.corpus_dir}")
        if not self.prompt_template_path.exists():
            raise FileNotFoundError(f"Prompt template not found: {self.prompt_template_path}")


# ---------------------------------------------------------------------------
# Main evaluator
# ---------------------------------------------------------------------------


class TCCFreeEvaluator:
    """Catalogue-free LLM-judge evaluator for CRES-1A.

    Usage:
        cfg = TCCFreeConfig(
            corpus_dir=Path("data_release/v5.0/rag_corpus"),
            prompt_template_path=Path("evaluators/prompts/tcc_free_v1.txt"),
            llm_config=LLMConfig(backend=LLMBackend.OPENAI, model="gpt-4o"),
        )
        evaluator = TCCFreeEvaluator(cfg)
        verdict = evaluator.evaluate(cached_record)
    """

    def __init__(self, config: TCCFreeConfig) -> None:
        self.config = config
        self.llm: BaseLLMProvider = LLMProviderFactory.create(config.llm_config)
        self._prompt_template: str = config.prompt_template_path.read_text()
        self._corpus_cache: dict[str, list[dict[str, Any]]] = {}
        self._bm25_cache: dict[str, BM25Index] = {}

    # ------------------------------------------------------------------
    # Corpus loading + retrieval
    # ------------------------------------------------------------------

    def _resolve_corpus_filename(self, scenario_id: str) -> str:
        """Pick the parsed guideline filename for this scenario prefix."""
        prefix = scenario_id.split("_", 1)[0].lower()
        return _PREFIX_TO_CORPUS.get(prefix, _FALLBACK_CORPUS)

    def _load_corpus_docs(self, corpus_filename: str) -> list[dict[str, Any]]:
        """Load a parsed guideline JSON and flatten to BM25-ready chunks."""
        if corpus_filename in self._corpus_cache:
            return self._corpus_cache[corpus_filename]

        corpus_path = self.config.corpus_dir / corpus_filename
        if not corpus_path.exists():
            # Fall back to universal safety if the specific file is missing.
            corpus_path = self.config.corpus_dir / _FALLBACK_CORPUS
        with open(corpus_path) as f:
            raw = json.load(f)

        docs: list[dict[str, Any]] = []
        for rec in raw.get("recommendations", []):
            docs.append(
                {
                    "id": rec.get("recommendation_id", f"rec_{len(docs)}"),
                    "content": rec.get("text", ""),
                    "strength": rec.get("strength", ""),
                    "type": "recommendation",
                }
            )
        for section_name, section_content in (raw.get("key_sections") or {}).items():
            if isinstance(section_content, str) and section_content.strip():
                docs.append(
                    {
                        "id": f"section_{section_name}",
                        "content": section_content,
                        "strength": "",
                        "type": "section",
                    }
                )

        self._corpus_cache[corpus_filename] = docs
        return docs

    def _get_bm25(self, corpus_filename: str) -> BM25Index:
        """Lazily build BM25 index per corpus file."""
        if corpus_filename in self._bm25_cache:
            return self._bm25_cache[corpus_filename]
        docs = self._load_corpus_docs(corpus_filename)
        index = BM25Index()
        index.add_documents(docs)
        self._bm25_cache[corpus_filename] = index
        return index

    def _retrieve_excerpts(
        self,
        corpus_filename: str,
        query: str,
        top_k: int,
    ) -> list[dict[str, Any]]:
        """Retrieve top-k relevant guideline chunks for a trace query."""
        index = self._get_bm25(corpus_filename)
        hits = index.search(query, top_k=top_k)
        docs = self._load_corpus_docs(corpus_filename)
        return [docs[doc_idx] for doc_idx, _score in hits if 0 <= doc_idx < len(docs)]

    # ------------------------------------------------------------------
    # Trace serialization
    # ------------------------------------------------------------------

    def _serialize_trace(self, record: dict[str, Any]) -> str:
        """Render a cached verdict record as a human-readable narrative.

        Deliberately omits ALL TCC-derived fields — including expected_actions,
        n_violations, violation_types, cga_pass — from the prompt.  Leaking
        any upstream signal into the "catalogue-free" judge would bias it
        toward agreement and break the CRES-1A defense claim.
        """
        performed = record.get("performed_actions") or []
        lines = [
            f"Scenario: {record.get('scenario_id', '?')}",
            f"Model: {record.get('model', '?')}",
            f"Number of actions performed: {len(performed)}",
            "",
            "Actions performed (chronological order unknown; treat as unordered set):",
        ]
        for a in performed:
            lines.append(f"  - {a}")
        return "\n".join(lines)

    def _format_excerpts(self, excerpts: list[dict[str, Any]]) -> str:
        if not excerpts:
            return "(no relevant guideline excerpts retrieved)"
        lines = []
        for e in excerpts[: self.config.max_excerpts_per_domain * 2]:
            lines.append(f"[{e['id']}] ({e.get('strength', 'n/a')}) {e['content']}")
        return "\n\n".join(lines)

    # ------------------------------------------------------------------
    # LLM call + parse
    # ------------------------------------------------------------------

    def _build_query(self, record: dict[str, Any]) -> str:
        """Build a BM25 query from performed actions only.

        Must NOT include expected_actions — those are TCC-derived ground
        truth and would bias retrieval toward the answer key.
        """
        performed = record.get("performed_actions") or []
        tokens = set(performed)
        return " ".join(str(t).replace("_", " ") for t in tokens)

    def _render_prompt(
        self,
        domain: str,
        guideline_excerpts: str,
        trace_text: str,
    ) -> list[LLMMessage]:
        """Split the template into SYSTEM / USER messages."""
        template = self._prompt_template
        try:
            _, after_system = template.split("SYSTEM:", 1)
            system_body, user_template = after_system.split("USER:", 1)
        except ValueError as e:
            raise ValueError("Prompt template must contain 'SYSTEM:' and 'USER:' markers") from e
        # NOTE: use str.replace (not str.format) so guideline excerpts or
        # action IDs containing literal '{' / '}' (e.g. dosing ranges like
        # "{0.9 mg/kg}") don't crash with KeyError. The placeholders in the
        # template file are fixed tokens we control.
        user_body = (
            user_template.replace("{domain}", domain)
            .replace("{guideline_excerpts}", guideline_excerpts)
            .replace("{trace_text}", trace_text)
        )
        return [
            LLMMessage(role="system", content=system_body.strip()),
            LLMMessage(role="user", content=user_body.strip()),
        ]

    def _parse_verdict(
        self,
        response_text: str,
        record: dict[str, Any],
        tokens_used: int,
    ) -> TCCFreeVerdict:
        """Parse the LLM response into a TCCFreeVerdict.

        If the response cannot be coerced into JSON we return a fail
        verdict with the truncated raw text captured in `reasoning` so the
        runner can surface it for manual inspection.
        """
        try:
            obj = safe_json_parse(response_text)
        except (json.JSONDecodeError, ValueError):
            return TCCFreeVerdict(
                scenario_id=record.get("scenario_id", ""),
                run_index=int(record.get("run_index", 0) or 0),
                model=record.get("model", ""),
                verdict_binary="fail",
                reasoning=f"LLM output did not parse as JSON: {response_text[:200]!r}",
                tokens_used=tokens_used,
            )
        if not isinstance(obj, dict):
            return TCCFreeVerdict(
                scenario_id=record.get("scenario_id", ""),
                run_index=int(record.get("run_index", 0) or 0),
                model=record.get("model", ""),
                verdict_binary="fail",
                reasoning=f"LLM output did not parse as JSON: {response_text[:200]!r}",
                tokens_used=tokens_used,
            )
        violations_raw = obj.get("violations") or []
        violations: list[TCCFreeViolation] = []
        for v in violations_raw:
            if not isinstance(v, dict):
                continue
            violations.append(
                TCCFreeViolation(
                    violation_type=str(v.get("violation_type", "deviation")).lower(),
                    action_involved=v.get("action_involved"),
                    expected_action=v.get("expected_action"),
                    description=str(v.get("description", "")),
                    source_recommendation=v.get("source_recommendation"),
                )
            )
        verdict_binary = str(obj.get("verdict_binary", "fail")).lower().strip()
        if verdict_binary not in ("pass", "fail"):
            verdict_binary = "fail"
        return TCCFreeVerdict(
            scenario_id=record.get("scenario_id", ""),
            run_index=int(record.get("run_index", 0) or 0),
            model=record.get("model", ""),
            verdict_binary=verdict_binary,
            violations=violations,
            reasoning=str(obj.get("reasoning", "")),
            tokens_used=tokens_used,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def evaluate(self, record: dict[str, Any]) -> TCCFreeVerdict:
        """Judge a single cached verdict record catalogue-free."""
        scenario_id = record.get("scenario_id", "")
        if not scenario_id:
            raise ValueError("record missing scenario_id")

        corpus_filename = self._resolve_corpus_filename(scenario_id)
        query = self._build_query(record)
        excerpts = self._retrieve_excerpts(corpus_filename, query, self.config.top_k_retrieval)
        trace_text = self._serialize_trace(record)
        excerpts_text = self._format_excerpts(excerpts)
        domain_label = re.sub(r"\.parsed\.json$", "", corpus_filename)

        messages = self._render_prompt(domain_label, excerpts_text, trace_text)
        response = self.llm.complete(messages)
        tokens = int(response.usage.get("total_tokens", 0) or 0)
        return self._parse_verdict(response.content, record, tokens)

    def evaluate_batch(self, records: list[dict[str, Any]]) -> list[TCCFreeVerdict]:
        """Evaluate multiple records sequentially."""
        return [self.evaluate(r) for r in records]


# ---------------------------------------------------------------------------
# Convenience factory for the runner
# ---------------------------------------------------------------------------


def build_default_evaluator(
    *,
    use_mock: bool = False,
    model: str = "gpt-4o",
    corpus_dir: Path | None = None,
    prompt_path: Path | None = None,
    vllm_endpoint: str | None = None,
) -> TCCFreeEvaluator:
    """Build a TCCFreeEvaluator with default paths.

    Args:
        vllm_endpoint: If provided, use vLLM backend at this base URL.

    Callers who need non-default paths should build TCCFreeConfig manually.
    """
    corpus_dir = corpus_dir or _DEFAULT_CORPUS_DIR
    prompt_path = prompt_path or (Path(__file__).parent / "prompts" / "tcc_free_v1.txt")
    if use_mock:
        backend = LLMBackend.MOCK
    elif vllm_endpoint:
        backend = LLMBackend.VLLM
    else:
        backend = LLMBackend.OPENAI
    # vLLM with Qwen3.5 thinking mode: "Thinking Process:" preamble consumes
    # tokens before actual JSON output. Increase budget so JSON isn't truncated.
    # Self-hosted, so extra tokens are free.
    tok_limit = 8192 if vllm_endpoint else 1500
    llm_cfg = LLMConfig(
        backend=backend,
        model=model,
        temperature=0.0,
        max_tokens=tok_limit,
        base_url=vllm_endpoint if vllm_endpoint else None,
        api_key="sk-no-key-required" if vllm_endpoint else None,
    )
    cfg = TCCFreeConfig(
        corpus_dir=corpus_dir,
        prompt_template_path=prompt_path,
        llm_config=llm_cfg,
    )
    return TCCFreeEvaluator(cfg)
