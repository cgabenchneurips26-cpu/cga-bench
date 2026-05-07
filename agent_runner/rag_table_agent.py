"""RAG-Table Agent (V3): LLM-based agent with full decision table in context.

CRES-4 experiment variant: isolates the LLM-reasoning factor from the
retrieval factor by stuffing the full decision table into the LLM context
instead of relying on BM25 retrieval from the CPG corpus.

Key differences from V4 (RAG):
- V4 retrieves top-k documents via BM25 from CPG corpus
- V3 stuffs the FULL decision table into context (no retrieval)
- Same LLM reasoning, different information access path

Key differences from V2 (Oracle-RAG):
- V2 uses rule-based reasoning with BM25 retrieval
- V3 uses LLM reasoning with full table access
- V2 vs V3 delta measures rule-based vs LLM reasoning gap

Scoring-Agent separation: NO cpg_engine or assessor_core imports.
The decision table comes from agent_rules/ (agent-side, independent).
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from cga_bench.agent_rules.decision_table import (
    ActionRecommendation,
    ClinicalRuleSet,
    DecisionTableEntry,
    RuleBasedDecisionTable,
)
from cga_bench.agent_runner.llm_provider import BaseLLMProvider
from cga_bench.agent_runner.oracle_agent import OracleAgent
from cga_bench.agent_runner.rag_agent import RAGAgent, RAGConfig, RetrievedDocument
from cga_bench.cpg_model.schemas.base import Action
from cga_bench.scenario_engine.environment import Observation

logger = logging.getLogger(__name__)

# Token budget: 32k context - 4k overhead = 28k tokens ≈ 112k chars
MAX_TABLE_CHARS = 112_000
TRUNCATION_MARKER = "\n... [TABLE TRUNCATED — exceeds 28k token budget]"


@dataclass
class RAGTableConfig(RAGConfig):
    """RAG-Table agent configuration."""

    agent_type: str = "rag_table"
    guideline_domain: str = "sepsis"  # Domain for decision table loading


class RAGTableAgent(RAGAgent):
    """RAG variant that skips BM25 retrieval and stuffs the full decision
    table into the LLM context as per-entry reference documents.

    Purpose: isolate the LLM-reasoning factor from the retrieval factor.
    V3 vs V4 measures the cost of imperfect retrieval on an LLM reasoner.
    V2 vs V3 measures rule-based vs LLM reasoning with matched information.
    """

    def __init__(
        self,
        config: RAGTableConfig,
        llm_provider: BaseLLMProvider | None = None,
    ):
        super().__init__(config, llm_provider=llm_provider)
        self.table_config = config

        # Load decision table for the specified domain
        self._decision_table: RuleBasedDecisionTable | None = None
        self._table_docs: list[RetrievedDocument] = []
        self._init_table(config.guideline_domain)

    def _init_table(self, domain: str) -> None:
        """Load and serialize the decision table for the given domain."""
        domain_key = domain.lower().strip()
        table_cls = OracleAgent._DOMAIN_TABLE_MAP.get(domain_key)

        if table_cls is None:
            logger.warning(
                "RAGTableAgent: no table for domain '%s', will fall back to normal RAG retrieval",
                domain,
            )
            return

        self._decision_table = table_cls()
        self._table_docs = self._build_table_docs()

        total_chars = sum(len(d.content) for d in self._table_docs)
        logger.info(
            "RAGTableAgent: loaded %s domain, %d entries, %d chars total",
            domain,
            len(self._table_docs),
            total_chars,
        )

    def _build_table_docs(self) -> list[RetrievedDocument]:
        """Convert the full decision table into RetrievedDocument objects.

        Each mandatory action, forbidden action, and conditional entry
        becomes a separate document so the parent's _generate_actions_with_llm
        can format them into the LLM context.
        """
        if not self._decision_table:
            return []

        docs: list[RetrievedDocument] = []
        total_chars = 0

        for ruleset_id, ruleset in self._decision_table.rulesets.items():
            # Mandatory actions
            for action in ruleset.always_mandatory:
                content = self._format_mandatory_doc(action, ruleset)
                total_chars += len(content)
                if total_chars > MAX_TABLE_CHARS:
                    break
                docs.append(
                    RetrievedDocument(
                        doc_id=f"table_mandatory_{action.action_id}",
                        source=f"{ruleset_id} (decision table)",
                        content=content,
                        score=1.0,
                        strength="MANDATORY",
                    )
                )

            if total_chars > MAX_TABLE_CHARS:
                logger.warning("Table truncated at mandatory rules")
                break

            # Forbidden actions
            for action in ruleset.always_forbidden:
                content = self._format_forbidden_doc(action, ruleset)
                total_chars += len(content)
                if total_chars > MAX_TABLE_CHARS:
                    break
                docs.append(
                    RetrievedDocument(
                        doc_id=f"table_forbidden_{action.action_id}",
                        source=f"{ruleset_id} (decision table)",
                        content=content,
                        score=1.0,
                        strength="FORBIDDEN",
                    )
                )

            if total_chars > MAX_TABLE_CHARS:
                logger.warning("Table truncated at forbidden rules")
                break

            # Conditional entries
            for entry in ruleset.decision_entries:
                content = self._format_entry_doc(entry, ruleset)
                total_chars += len(content)
                if total_chars > MAX_TABLE_CHARS:
                    break
                docs.append(
                    RetrievedDocument(
                        doc_id=f"table_entry_{entry.entry_id}",
                        source=f"{ruleset_id} (decision table)",
                        content=content,
                        score=1.0,
                        strength="CONDITIONAL",
                    )
                )

            if total_chars > MAX_TABLE_CHARS:
                logger.warning("Table truncated at conditional rules")
                break

            # Allergy contraindications
            if ruleset.allergy_contraindications:
                content = self._format_allergy_doc(ruleset)
                total_chars += len(content)
                if total_chars <= MAX_TABLE_CHARS:
                    docs.append(
                        RetrievedDocument(
                            doc_id=f"table_allergies_{ruleset_id}",
                            source=f"{ruleset_id} (decision table)",
                            content=content,
                            score=1.0,
                            strength="ALLERGY CONTRAINDICATION",
                        )
                    )

            # Comorbidity contraindications
            if ruleset.comorbidity_contraindications:
                content = self._format_comorbidity_doc(ruleset)
                total_chars += len(content)
                if total_chars <= MAX_TABLE_CHARS:
                    docs.append(
                        RetrievedDocument(
                            doc_id=f"table_comorbidities_{ruleset_id}",
                            source=f"{ruleset_id} (decision table)",
                            content=content,
                            score=1.0,
                            strength="COMORBIDITY CONTRAINDICATION",
                        )
                    )

        return docs

    def _format_action_line(self, action: ActionRecommendation) -> str:
        """Format a single ActionRecommendation as a concise text line."""
        parts = [f"{action.action_id} ({action.action_type})"]
        meta: list[str] = []
        if action.source_guideline:
            meta.append(action.source_guideline)
        if action.evidence_level:
            meta.append(f"Evidence: {action.evidence_level}")
        if action.deadline_minutes is not None:
            meta.append(f"Deadline: {action.deadline_minutes}min")
        if action.required_prior_actions:
            meta.append(f"After: {', '.join(action.required_prior_actions)}")
        if meta:
            parts.append(f"[{' | '.join(meta)}]")
        return " ".join(parts)

    def _format_mandatory_doc(self, action: ActionRecommendation, ruleset: ClinicalRuleSet) -> str:
        """Format a mandatory action as a readable document."""
        lines = [
            f"MANDATORY ACTION — {ruleset.name}",
            f"  {self._format_action_line(action)}",
        ]
        if action.source_recommendation:
            lines.append(f"  Source: {action.source_recommendation}")
        return "\n".join(lines)

    def _format_forbidden_doc(self, action: ActionRecommendation, ruleset: ClinicalRuleSet) -> str:
        """Format a forbidden action as a readable document."""
        lines = [
            f"FORBIDDEN ACTION — {ruleset.name}",
            f"  {self._format_action_line(action)}",
        ]
        if action.source_recommendation:
            lines.append(f"  Reason: {action.source_recommendation}")
        return "\n".join(lines)

    def _format_entry_doc(self, entry: DecisionTableEntry, ruleset: ClinicalRuleSet) -> str:
        """Format a conditional entry as a readable document."""
        lines = [
            f"CONDITIONAL RULE — {ruleset.name}",
            f"  {entry.description}",
            "  IF:",
        ]
        for cond in entry.conditions:
            desc = cond.description or f"{cond.variable} {cond.operator.value} {cond.value}"
            lines.append(f"    - {desc}")
        lines.append("  THEN:")
        for action in entry.actions:
            tag = "MANDATORY" if action.is_mandatory else "RECOMMENDED"
            lines.append(f"    - [{tag}] {self._format_action_line(action)}")
        return "\n".join(lines)

    def _format_allergy_doc(self, ruleset: ClinicalRuleSet) -> str:
        """Format allergy contraindications."""
        lines = [f"ALLERGY CONTRAINDICATIONS — {ruleset.name}"]
        for allergy, forbidden in ruleset.allergy_contraindications.items():
            lines.append(f"  If allergic to {allergy}: AVOID {', '.join(forbidden)}")
        return "\n".join(lines)

    def _format_comorbidity_doc(self, ruleset: ClinicalRuleSet) -> str:
        """Format comorbidity contraindications."""
        lines = [f"COMORBIDITY CONTRAINDICATIONS — {ruleset.name}"]
        for comorbidity, forbidden in ruleset.comorbidity_contraindications.items():
            lines.append(f"  If has {comorbidity}: AVOID {', '.join(forbidden)}")
        return "\n".join(lines)

    def reset(self) -> None:
        """Reset agent state."""
        super().reset()
        # Table docs are immutable — no reset needed

    def decide(self, observation: Observation) -> list[Action]:
        """Override: use full decision table instead of BM25 retrieval.

        The decision table entries are passed as RetrievedDocument objects
        to the parent's _generate_actions(), which formats them into the
        LLM prompt and generates actions.
        """
        if self._table_docs:
            # Skip BM25 retrieval — use full decision table as context
            actions = self._generate_actions(observation, self._table_docs)
        else:
            # Fallback to normal RAG retrieval if no table loaded
            query = self._build_query(observation)
            retrieved_docs = self.document_store.retrieve(query, self.rag_config.top_k)
            actions = self._generate_actions(observation, retrieved_docs)

        self.metrics.total_llm_calls += 1
        return actions

    def get_constraint_verification(self) -> dict[str, Any]:
        """Constraint verification for V3."""
        base: dict[str, Any] = {
            "uses_cpg_engine": False,
            "uses_assessor_core": False,
            "variant": "V3_RAGTable",
            "information_access": "full decision table in context",
            "reasoning_modality": "LLM",
            "table_entries": len(self._table_docs),
            "table_domain": self.table_config.guideline_domain,
        }
        return base
