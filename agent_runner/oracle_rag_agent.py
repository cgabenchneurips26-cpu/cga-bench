"""Oracle-RAG Agent (V2): Rule-based Oracle with BM25 retrieval.

CRES-4 experiment variant: factors out the information-access confound by
making the Oracle retrieve rules via BM25 instead of scanning the full table.

Key differences from V1 (Oracle):
- V1 scans ALL rules in the decision table directly
- V2 queries BM25 index over rule commentary, only applies top-k results
- Same rule-based reasoning (no LLM), different information access path

Key differences from V4 (RAG):
- V2 uses rule-based reasoning (no LLM)
- V4 uses LLM reasoning with BM25 retrieval from CPG corpus
- Both share the same BM25 retrieval budget (top_k=5)

Scoring-Agent separation: NO cpg_engine or assessor_core imports.
"""

from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any

from cga_bench.agent_rules.decision_table import (
    ActionRecommendation,
    DecisionTableEntry,
)
from cga_bench.agent_runner.oracle_agent import OracleAgent, OracleConfig
from cga_bench.agent_runner.rag_agent import BM25Index
from cga_bench.cpg_model.schemas.base import Action
from cga_bench.scenario_engine.environment import Observation

logger = logging.getLogger(__name__)


@dataclass
class OracleRAGConfig(OracleConfig):
    """Oracle-RAG agent configuration."""

    agent_type: str = "oracle_rag"
    top_k: int = 5  # Must match V4's RAGConfig.top_k for factorial design


@dataclass
class _IndexedRule:
    """A rule entry in the BM25 index with its provenance."""

    action: ActionRecommendation
    is_mandatory: bool
    parent_entry: DecisionTableEntry | None  # None for mandatory/forbidden


class OracleRAGAgent(OracleAgent):
    """Oracle that accesses its decision table via BM25 retrieval.

    Inherits all rule-to-action conversion from OracleAgent but overrides
    the rule lookup: each step issues a BM25 query against an index
    built over the decision table's rule commentary strings.
    Only the top-k retrieved rules are applied.

    This isolates the information-access factor: V1 vs V2 measures
    the cost of imperfect retrieval on a rule-based reasoner.
    """

    def __init__(self, config: OracleRAGConfig):
        super().__init__(config)
        self.top_k = config.top_k

        # Build BM25 index over all rules in the decision table
        self._indexed_rules: list[_IndexedRule] = []
        self._bm25_index = BM25Index()
        self._build_rule_index()

    def _build_rule_index(self) -> None:
        """Build BM25 index from all decision table rules."""
        if not self.decision_table:
            return

        docs: list[dict[str, Any]] = []

        for ruleset_id, ruleset in self.decision_table.rulesets.items():
            # Index always_mandatory rules
            for action in ruleset.always_mandatory:
                self._indexed_rules.append(_IndexedRule(action=action, is_mandatory=True, parent_entry=None))
                docs.append(
                    {
                        "content": self._serialize_rule(
                            action,
                            ruleset_id,
                            "mandatory",
                            description=ruleset.name,
                        )
                    }
                )

            # Index always_forbidden rules
            for action in ruleset.always_forbidden:
                self._indexed_rules.append(_IndexedRule(action=action, is_mandatory=False, parent_entry=None))
                docs.append(
                    {
                        "content": self._serialize_rule(
                            action,
                            ruleset_id,
                            "forbidden",
                            description="forbidden action",
                        )
                    }
                )

            # Index conditional decision entries
            for entry in ruleset.decision_entries:
                for action in entry.actions:
                    self._indexed_rules.append(
                        _IndexedRule(
                            action=action,
                            is_mandatory=False,
                            parent_entry=entry,
                        )
                    )
                    docs.append(
                        {
                            "content": self._serialize_rule(
                                action,
                                ruleset_id,
                                "conditional",
                                description=entry.description,
                                conditions=[f"{c.variable} {c.operator.value} {c.value}" for c in entry.conditions],
                            )
                        }
                    )

        self._bm25_index.add_documents(docs)
        logger.info(
            "OracleRAGAgent: indexed %d rules from %d rulesets",
            len(self._indexed_rules),
            len(self.decision_table.rulesets),
        )

    def _serialize_rule(
        self,
        action: ActionRecommendation,
        ruleset_id: str,
        rule_type: str,
        description: str = "",
        conditions: list[str] | None = None,
    ) -> str:
        """Serialize a rule into a BM25-searchable document string."""
        parts = [
            f"ruleset {ruleset_id}",
            f"type {rule_type}",
            f"action {action.action_id}",
            f"action_type {action.action_type}",
        ]
        if description:
            parts.append(description)
        if action.source_guideline:
            parts.append(f"guideline {action.source_guideline}")
        if action.source_recommendation:
            parts.append(f"recommendation {action.source_recommendation}")
        if action.evidence_level:
            parts.append(f"evidence {action.evidence_level}")
        if action.deadline_minutes is not None:
            parts.append(f"deadline {action.deadline_minutes} minutes")
        if action.is_mandatory:
            parts.append("mandatory urgent required")
        if action.is_forbidden:
            parts.append("forbidden contraindicated avoid")
        if conditions:
            parts.extend(conditions)
        # Include parameter keywords for richer BM25 matching
        for k, v in action.parameters.items():
            parts.append(f"{k} {v}")
        return " ".join(parts)

    def _build_query(self, context: dict[str, Any]) -> str:
        """Build BM25 query from patient context."""
        parts: list[str] = []

        diagnosis = context.get("working_diagnosis") or ""
        if diagnosis:
            parts.append(diagnosis)

        complaint = context.get("chief_complaint") or ""
        if complaint:
            parts.append(complaint)

        # Vitals-based keywords
        map_mmhg = context.get("map_mmhg")
        if map_mmhg is not None and map_mmhg < 65:
            parts.append("hypotension shock vasopressor fluid resuscitation")

        sbp = context.get("sbp_mmhg")
        if sbp is not None and sbp < 90:
            parts.append("hypotension shock")

        lactate = context.get("lactate")
        if lactate is not None and lactate > 2:
            parts.append("elevated lactate sepsis")

        if context.get("troponin_elevated"):
            parts.append("troponin STEMI myocardial infarction cath lab")

        if context.get("ecg_stemi"):
            parts.append("STEMI ECG ST elevation")
        if context.get("rv_involvement"):
            parts.append("right ventricle RV V4R nitroglycerin avoid")

        creatinine = context.get("creatinine")
        if creatinine is not None and creatinine > 1.5:
            parts.append("kidney injury creatinine AKI")

        potassium = context.get("potassium")
        if potassium is not None and potassium > 5.5:
            parts.append("hyperkalemia potassium")

        if context.get("fluid_resuscitation_complete"):
            parts.append("fluid resuscitation complete vasopressor")
        if context.get("vasopressor_started"):
            parts.append("vasopressor norepinephrine MAP target")

        # Generic clinical keywords for recall
        parts.append("clinical guideline bundle recommendation mandatory")

        return " ".join(parts)

    def decide(self, observation: Observation) -> list[Action]:
        """BM25-retrieved rule-based decision (no LLM).

        Algorithm:
        1. Build query from patient state
        2. Retrieve top-k rules via BM25
        3. Filter: skip completed, forbidden, and condition-unmet rules
        4. Convert to Actions, respecting prerequisites and max_actions_per_step
        """
        context = self._observation_to_context(observation)
        current_time = observation.timestamp_minutes

        if not self.decision_table or not self._indexed_rules:
            return []

        # BM25 retrieval
        query = self._build_query(context)
        hits = self._bm25_index.search(query, top_k=self.top_k)

        # Forbidden actions — full table scan (safety-critical, small set)
        forbidden_set = set(self.decision_table.get_forbidden_actions(context))

        actions: list[Action] = []
        for doc_idx, _score in hits:
            if doc_idx < 0 or doc_idx >= len(self._indexed_rules):
                continue

            rule = self._indexed_rules[doc_idx]
            rec = rule.action

            # Skip completed
            if rec.action_id in self._completed_action_ids:
                continue

            # Skip forbidden
            if rec.action_id in forbidden_set or rec.is_forbidden:
                continue

            # For conditional rules, verify entry conditions match
            if rule.parent_entry is not None and not rule.parent_entry.matches(context):
                continue

            # Check prerequisites
            if not all(p in self._completed_action_ids for p in rec.required_prior_actions):
                continue

            action = self._recommendation_to_action(rec, current_time)
            if action:
                actions.append(action)
                self._completed_action_ids.add(action.action_id)
                self.decision_table.record_action(action.action_id, int(current_time))

                if len(actions) >= self.config.max_actions_per_step:
                    break

        self._action_history.extend(actions)
        return actions

    def get_oracle_status(self) -> dict[str, Any]:
        """Oracle-RAG status with retrieval metadata."""
        status = super().get_oracle_status()
        status["agent_type"] = "oracle_rag_bm25_retrieval"
        status["bm25_index_size"] = len(self._indexed_rules)
        status["top_k"] = self.top_k
        return status

    def get_independence_verification(self) -> dict[str, Any]:
        """Independence verification for V2."""
        base = super().get_independence_verification()
        base["variant"] = "V2_OracleRAG"
        base["information_access"] = "BM25 retrieval over decision table"
        base["reasoning_modality"] = "rule-based (no LLM)"
        return base
