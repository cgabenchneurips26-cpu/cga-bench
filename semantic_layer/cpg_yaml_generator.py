"""CPG YAML Generator v2: ParsedGuideline → CPG graph YAML (schema-compliant).

Converts a `ParsedGuideline` (output of `CPGParser`) into a dict that matches
the CGA-Bench CPG graph schema enforced by `scripts/ci/validate_cpg_schema.py`.

v2 enhancements (Phase 2a):
  - Multi-node per category: severity-based branching splits one category
    into a decision node + multiple branch sub-nodes
  - conditional_next: state-based routing between nodes
  - conditional_rules: patient-specific safety rules (allergy, comorbidity)
  - Deadline enforcement: every mandatory action gets a deadline
  - Allowed-actions enrichment: domain-standard clinical actions

Invariants preserved (validator will otherwise reject):
  - Top-level: graph_id, guideline_name, entry_node, nodes are present
  - Per-node: node_id (== dict key), node_type ∈ {decision/plan/action/enquiry},
    name, mandatory_actions, allowed_actions, source_guideline, source_section
    are present and non-empty
  - forbidden_actions ∩ allowed_actions = ∅ (conditional overrides are separate)
  - deadlines.keys() ⊆ mandatory_actions ∪ allowed_actions
  - next_nodes / conditional_next targets exist in nodes

Falls back to v1 linear-chain when no branches are detected.
"""

from __future__ import annotations

from collections.abc import Iterable
import logging
from pathlib import Path
from typing import Any

import yaml

from .cpg_parser import (
    ActionCategory,
    ExtractedBranch,
    ExtractedConditionalRule,
    ExtractedRecommendation,
    ParsedGuideline,
    RecommendationStrength,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Category → node configuration
# ---------------------------------------------------------------------------

_CATEGORY_ORDER: tuple[ActionCategory, ...] = (
    ActionCategory.ASSESSMENT,
    ActionCategory.DIAGNOSTIC,
    ActionCategory.TREATMENT,
    ActionCategory.MONITORING,
    ActionCategory.CONSULTATION,
    ActionCategory.DISPOSITION,
)

_CATEGORY_NODE_TYPE: dict[ActionCategory, str] = {
    ActionCategory.ASSESSMENT: "enquiry",
    ActionCategory.DIAGNOSTIC: "enquiry",
    ActionCategory.TREATMENT: "plan",
    ActionCategory.MONITORING: "enquiry",
    ActionCategory.CONSULTATION: "action",
    ActionCategory.DISPOSITION: "decision",
}

_CATEGORY_NODE_ID: dict[ActionCategory, str] = {
    ActionCategory.ASSESSMENT: "initial_assessment",
    ActionCategory.DIAGNOSTIC: "diagnostic_workup",
    ActionCategory.TREATMENT: "treatment_plan",
    ActionCategory.MONITORING: "monitoring_reassessment",
    ActionCategory.CONSULTATION: "consultation",
    ActionCategory.DISPOSITION: "disposition",
}

_CATEGORY_NODE_NAME: dict[ActionCategory, str] = {
    ActionCategory.ASSESSMENT: "Initial Assessment",
    ActionCategory.DIAGNOSTIC: "Diagnostic Workup",
    ActionCategory.TREATMENT: "Treatment Plan",
    ActionCategory.MONITORING: "Monitoring & Reassessment",
    ActionCategory.CONSULTATION: "Consultation",
    ActionCategory.DISPOSITION: "Disposition",
}

_STRENGTH_TO_CLASS: dict[RecommendationStrength, str] = {
    RecommendationStrength.STRONG: "I",
    RecommendationStrength.MODERATE: "IIa",
    RecommendationStrength.WEAK: "IIb",
    RecommendationStrength.AGAINST: "III",
}

# ---------------------------------------------------------------------------
# Default deadline rules (Phase 2a: deadline enforcement)
# ---------------------------------------------------------------------------

# Category-level defaults when LLM did not extract a specific deadline.
# Conservative values from major CPG bundles (SSC Hour-1, AHA Door-to-Balloon).
_DEFAULT_DEADLINE_BY_CATEGORY: dict[ActionCategory, int] = {
    ActionCategory.ASSESSMENT: 15,
    ActionCategory.DIAGNOSTIC: 60,
    ActionCategory.TREATMENT: 60,
    ActionCategory.MONITORING: 360,
    ActionCategory.CONSULTATION: 120,
    ActionCategory.DISPOSITION: 480,
}

# Action-id pattern → deadline (minutes). More specific wins over category default.
_DEFAULT_DEADLINE_BY_ACTION: dict[str, int] = {
    "assess_vital_signs": 5,
    "assess_infection_source": 10,
    "assess_organ_dysfunction": 10,
    "order_lab_lactate": 60,
    "order_lab_blood_culture": 60,
    "give_broad_spectrum_antibiotics": 60,
    "give_crystalloid_30ml_kg": 180,
    "start_vasopressor_norepinephrine": 60,
    "give_aspirin_loading": 30,
    "activate_cath_lab": 90,
    "give_alteplase_0.9mg_kg": 60,
    "assess_nihss": 15,
    "give_epinephrine_im": 5,
    "remeasure_lactate_if_elevated": 360,
}

# ---------------------------------------------------------------------------
# Domain-standard allowed actions (Phase 2a: enrichment)
# ---------------------------------------------------------------------------

# Common clinical actions that should appear in allowed_actions for any node
# in these domains, even if the LLM did not explicitly extract them.
_DOMAIN_ENRICHMENT_ACTIONS: dict[str, list[str]] = {
    "sepsis": [
        "assess_vital_signs",
        "order_lab_cbc",
        "order_lab_bmp",
        "order_lab_cmp",
        "order_lab_coagulation",
        "order_lab_procalcitonin",
        "order_lab_blood_gas",
        "order_lab_urine_culture",
        "order_lab_urinalysis",
        "order_lab_liver_function_tests",
        "order_imaging_chest_xray",
        "order_imaging_ct_abdomen",
        "order_imaging_ct_chest",
        "order_imaging_ultrasound_abdomen",
        "place_central_line",
        "place_arterial_line",
        "request_consultation",
    ],
    "chest_pain": [
        "assess_vital_signs",
        "order_lab_troponin",
        "order_lab_cbc",
        "order_lab_bmp",
        "order_imaging_chest_xray",
        "obtain_ecg",
        "order_echocardiogram",
        "request_consultation",
    ],
    "stroke": [
        "assess_vital_signs",
        "assess_nihss",
        "order_lab_cbc",
        "order_lab_bmp",
        "order_lab_coagulation",
        "order_lab_blood_glucose",
        "order_imaging_ct_head",
        "order_imaging_ct_angiography",
        "request_consultation",
    ],
    "aki": [
        "assess_vital_signs",
        "order_lab_creatinine",
        "order_lab_bmp",
        "order_lab_cbc",
        "order_lab_urinalysis",
        "order_imaging_renal_ultrasound",
        "request_consultation",
    ],
}


# ---------------------------------------------------------------------------
# Generator
# ---------------------------------------------------------------------------


class CPGYAMLGenerator:
    """Render a ParsedGuideline into a CGA-Bench CPG graph YAML dict.

    v2: Supports multi-node branching, conditional_rules, deadline enforcement.
    Falls back to v1 linear chain when no branches are present.
    """

    def generate(self, parsed: ParsedGuideline) -> dict[str, Any]:
        """Produce a schema-compliant CPG graph dict.

        Args:
            parsed: Output of `CPGParser.parse_text` or `parse_file`.

        Returns:
            A dict that `yaml.safe_dump` can serialise into a valid CPG YAML.
        """
        grouped = self._group_by_category(parsed.recommendations)
        has_branches = bool(getattr(parsed, "branches", None))

        if has_branches:
            nodes = self._build_nodes_v2(grouped, parsed)
            self._chain_next_nodes_v2(nodes, grouped, parsed)
        else:
            nodes = self._build_nodes_v1(grouped, parsed)
            self._chain_next_nodes_v1(nodes, grouped)

        # v2 enrichments applied to ALL nodes regardless of branching
        self._enforce_deadlines(nodes, grouped)
        self._enrich_allowed_actions(nodes, parsed.domain)
        if parsed.conditional_rules:
            self._attach_conditional_rules(nodes, parsed)

        # v3: Append reassessment + disposition nodes from Pass 3
        reassessment_spec = getattr(parsed, "reassessment_spec", None)
        if reassessment_spec:
            self._append_reassessment_disposition(nodes, reassessment_spec, parsed)

        entry_node = self._select_entry_node(grouped)

        return {
            "graph_id": parsed.guideline_id,
            "guideline_name": parsed.name,
            "version": parsed.version or "1.0",
            "metadata": self._build_metadata(parsed),
            "entry_node": entry_node,
            "nodes": nodes,
        }

    def write(self, parsed: ParsedGuideline, output_path: Path | str) -> Path:
        """Generate YAML and write it to disk. Returns the written path."""
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        data = self.generate(parsed)
        output_path.write_text(
            yaml.safe_dump(data, sort_keys=False, allow_unicode=True, width=120),
            encoding="utf-8",
        )
        return output_path

    # ------------------------------------------------------------------
    # v1 internals (linear chain fallback)
    # ------------------------------------------------------------------

    @staticmethod
    def _group_by_category(
        recommendations: Iterable[ExtractedRecommendation],
    ) -> dict[ActionCategory, list[ExtractedRecommendation]]:
        grouped: dict[ActionCategory, list[ExtractedRecommendation]] = {}
        for rec in recommendations:
            grouped.setdefault(rec.category, []).append(rec)
        return grouped

    def _build_nodes_v1(
        self,
        grouped: dict[ActionCategory, list[ExtractedRecommendation]],
        parsed: ParsedGuideline,
    ) -> dict[str, dict[str, Any]]:
        """v1: one node per category present."""
        nodes: dict[str, dict[str, Any]] = {}
        for category in _CATEGORY_ORDER:
            recs = grouped.get(category)
            if not recs:
                continue
            node_id = _CATEGORY_NODE_ID[category]
            nodes[node_id] = self._build_single_node(node_id, category, recs, parsed)
        return nodes

    def _chain_next_nodes_v1(
        self,
        nodes: dict[str, dict[str, Any]],
        grouped: dict[ActionCategory, list[ExtractedRecommendation]],
    ) -> None:
        """v1: linear chain in _CATEGORY_ORDER."""
        ordered_ids = [_CATEGORY_NODE_ID[cat] for cat in _CATEGORY_ORDER if grouped.get(cat)]
        for current, following in zip(ordered_ids, ordered_ids[1:]):
            nodes[current]["next_nodes"] = [following]

    # ------------------------------------------------------------------
    # v2 internals (multi-node branching)
    # ------------------------------------------------------------------

    def _build_nodes_v2(
        self,
        grouped: dict[ActionCategory, list[ExtractedRecommendation]],
        parsed: ParsedGuideline,
    ) -> dict[str, dict[str, Any]]:
        """v2: categories with branches produce decision + branch sub-nodes."""
        nodes: dict[str, dict[str, Any]] = {}
        branches_by_cat: dict[ActionCategory, list[ExtractedBranch]] = {}
        for branch in parsed.branches:
            branches_by_cat.setdefault(branch.parent_category, []).append(branch)

        for category in _CATEGORY_ORDER:
            recs = grouped.get(category)
            if not recs:
                continue

            cat_branches = branches_by_cat.get(category, [])

            if not cat_branches:
                # No branching: v1-style single node
                node_id = _CATEGORY_NODE_ID[category]
                nodes[node_id] = self._build_single_node(node_id, category, recs, parsed)
            else:
                # Branching: build decision node + branch sub-nodes
                decision_node_id = _CATEGORY_NODE_ID[category]
                decision_node = self._build_decision_node(
                    decision_node_id,
                    category,
                    recs,
                    cat_branches,
                    parsed,
                )
                nodes[decision_node_id] = decision_node

                for branch in cat_branches:
                    branch_node = self._build_branch_node(
                        branch,
                        category,
                        recs,
                        parsed,
                    )
                    nodes[branch.node_id] = branch_node

        return nodes

    def _build_decision_node(
        self,
        node_id: str,
        category: ActionCategory,
        recs: list[ExtractedRecommendation],
        branches: list[ExtractedBranch],
        parsed: ParsedGuideline,
    ) -> dict[str, Any]:
        """Build a decision/routing node that dispatches to branch sub-nodes."""
        # Shared mandatory: actions all branches need (from recs without branch_label)
        shared_recs = [r for r in recs if r.branch_label is None]
        if not shared_recs:
            # All recs are branch-specific; use first two as shared minimum
            shared_recs = recs[:2] if len(recs) >= 2 else recs

        node = self._build_single_node(node_id, category, shared_recs, parsed)
        node["node_type"] = "decision"
        node["name"] = f"{_CATEGORY_NODE_NAME[category]} — Routing"

        # Build conditional_next from branches
        cond_next: dict[str, str] = {}
        for branch in branches:
            cond_next[branch.condition] = branch.node_id
        node["conditional_next"] = cond_next
        # Clear next_nodes — routing is via conditional_next
        node["next_nodes"] = []

        return node

    def _build_branch_node(
        self,
        branch: ExtractedBranch,
        category: ActionCategory,
        all_recs: list[ExtractedRecommendation],
        parsed: ParsedGuideline,
    ) -> dict[str, Any]:
        """Build a branch sub-node with merged shared + branch-specific actions."""
        # Merge shared (no branch_label) + branch-specific recs
        shared_recs = [r for r in all_recs if r.branch_label is None]
        branch_recs = [r for r in all_recs if r.branch_label == branch.branch_id]
        merged_recs = shared_recs + branch_recs

        # If no branch-specific recs found, use all recs (LLM didn't tag them)
        if not branch_recs:
            merged_recs = list(all_recs)

        node = self._build_single_node(branch.node_id, category, merged_recs, parsed)
        node["name"] = branch.node_name
        node["description"] = branch.description or node["description"]
        node["precondition"] = branch.precondition

        return node

    def _chain_next_nodes_v2(
        self,
        nodes: dict[str, dict[str, Any]],
        grouped: dict[ActionCategory, list[ExtractedRecommendation]],
        parsed: ParsedGuideline,
    ) -> None:
        """v2: chain with awareness of branch sub-nodes.

        Decision nodes route via conditional_next (already set).
        Branch sub-nodes chain to the next category's entry node.
        """
        ordered_cats = [cat for cat in _CATEGORY_ORDER if grouped.get(cat)]
        branches_by_cat: dict[ActionCategory, list[ExtractedBranch]] = {}
        for branch in parsed.branches:
            branches_by_cat.setdefault(branch.parent_category, []).append(branch)

        for i, cat in enumerate(ordered_cats):
            if i + 1 >= len(ordered_cats):
                break  # Last category — no next

            next_cat = ordered_cats[i + 1]
            next_entry_id = _CATEGORY_NODE_ID[next_cat]

            cat_branches = branches_by_cat.get(cat, [])
            if not cat_branches:
                # Simple node: chain linearly
                node_id = _CATEGORY_NODE_ID[cat]
                if node_id in nodes:
                    nodes[node_id]["next_nodes"] = [next_entry_id]
            else:
                # Decision node already has conditional_next set.
                # Branch sub-nodes chain to next category's entry.
                for branch in cat_branches:
                    if branch.node_id in nodes:
                        nodes[branch.node_id]["next_nodes"] = [next_entry_id]

    def _attach_conditional_rules(
        self,
        nodes: dict[str, dict[str, Any]],
        parsed: ParsedGuideline,
    ) -> None:
        """Attach conditional_rules to the most relevant node(s).

        Strategy: attach to TREATMENT plan nodes (they have the medications
        that allergies/comorbidities most commonly affect). If multiple
        treatment nodes exist (branches), attach to all of them.
        """
        treatment_node_ids: list[str] = []
        for nid, node in nodes.items():
            if node.get("node_type") in ("plan", "action"):
                treatment_node_ids.append(nid)

        # Fallback: attach to all nodes if no plan/action nodes found
        if not treatment_node_ids:
            treatment_node_ids = list(nodes.keys())

        for nid in treatment_node_ids:
            rules_yaml = self._render_conditional_rules(parsed.conditional_rules)
            if rules_yaml:
                nodes[nid]["conditional_rules"] = rules_yaml

    @staticmethod
    def _render_conditional_rules(
        rules: list[ExtractedConditionalRule],
    ) -> list[dict[str, Any]]:
        """Convert ExtractedConditionalRule list to YAML-serialisable dicts."""
        rendered: list[dict[str, Any]] = []
        for rule in rules:
            rendered.append(
                {
                    "rule_id": rule.rule_id,
                    "condition": rule.condition,
                    "effect": {
                        "type": rule.effect_type,
                        "actions": list(rule.affected_actions),
                    },
                    "evidence": rule.evidence,
                    "severity": rule.severity,
                    "description": rule.description,
                    "condition_variables": list(rule.condition_variables),
                    "trigger_range": dict(rule.trigger_range),
                    "normal_range": dict(rule.normal_range),
                }
            )
        return rendered

    # ------------------------------------------------------------------
    # v3: Reassessment + disposition node generation
    # ------------------------------------------------------------------

    def _append_reassessment_disposition(
        self,
        nodes: dict[str, dict[str, Any]],
        spec: Any,
        parsed: ParsedGuideline,
    ) -> None:
        """Append reassessment and disposition nodes from Pass 3 ReassessmentSpec.

        Wires existing leaf nodes (those with empty next_nodes and no conditional_next)
        to the new reassessment node, then chains reassessment → disposition → terminals.
        """
        # Skip if reassessment/disposition nodes already exist (from category-based extraction)
        existing_ids = set(nodes.keys())
        if "reassessment" in existing_ids or "disposition_decision" in existing_ids:
            return

        source = parsed.source or "unknown"

        # --- Reassessment node ---
        reassess_actions = list(spec.reassessment_actions) if spec.reassessment_actions else ["reassess_perfusion"]
        reassess_node: dict[str, Any] = {
            "node_id": "reassessment",
            "node_type": "enquiry",
            "name": "Reassessment after Initial Treatment",
            "description": "Reassess patient response and determine next steps",
            "precondition": None,
            "mandatory_actions": reassess_actions,
            "allowed_actions": list(reassess_actions)
            + ["adjust_vasopressor", "additional_fluid_bolus", "order_echocardiogram", "escalate_to_icu"],
            "forbidden_actions": list(spec.reassessment_forbidden)
            if spec.reassessment_forbidden
            else ["discharge_home"],
            "deadlines": dict(spec.reassessment_deadlines) if spec.reassessment_deadlines else {},
            "required_prior_actions": {},
            "recommendation_class": "I",
            "evidence_level": "C",
            "source_guideline": source,
            "source_section": "Ongoing Reassessment",
            "next_nodes": ["disposition_decision"],
            "conditional_next": {},
        }
        nodes["reassessment"] = reassess_node

        # --- Disposition decision node ---
        disp_mandatory = list(spec.disposition_mandatory) if spec.disposition_mandatory else ["determine_disposition"]
        disp_cond_next: dict[str, str] = {}
        for cond in spec.disposition_conditions or []:
            disp_cond_next[cond["condition"]] = cond["target"]

        # Ensure at least default routing
        if not disp_cond_next:
            disp_cond_next = {
                "state.vitals.map_mmhg < 65": "admit_to_icu",
                "'True'": "admit_to_ward",
            }

        disp_node: dict[str, Any] = {
            "node_id": "disposition_decision",
            "node_type": "decision",
            "name": "Disposition Decision",
            "description": "Determine appropriate level of care",
            "precondition": None,
            "mandatory_actions": disp_mandatory,
            "allowed_actions": list(disp_mandatory) + ["admit_to_icu", "admit_to_ward", "transfer_to_higher_care"],
            "forbidden_actions": list(spec.disposition_forbidden) if spec.disposition_forbidden else ["discharge_home"],
            "deadlines": {},
            "required_prior_actions": {},
            "recommendation_class": "I",
            "evidence_level": "C",
            "source_guideline": source,
            "source_section": "Disposition",
            "next_nodes": [],
            "conditional_next": disp_cond_next,
        }
        nodes["disposition_decision"] = disp_node

        # --- Terminal nodes ---
        for terminal in spec.terminal_nodes or []:
            tid = terminal["node_id"]
            if tid in existing_ids:
                continue
            nodes[tid] = {
                "node_id": tid,
                "node_type": "action",
                "name": terminal.get("name", tid),
                "description": terminal.get("name", tid),
                "precondition": None,
                "mandatory_actions": list(terminal.get("mandatory") or [tid]),
                "allowed_actions": list(terminal.get("allowed") or [tid]),
                "forbidden_actions": list(terminal.get("forbidden") or []),
                "deadlines": {},
                "required_prior_actions": {},
                "recommendation_class": "I",
                "evidence_level": "C",
                "source_guideline": source,
                "source_section": terminal.get("name", tid),
                "next_nodes": [],
                "conditional_next": {},
            }

        # --- Wire existing leaf nodes to reassessment ---
        for nid, node in nodes.items():
            if nid in ("reassessment", "disposition_decision"):
                continue
            if nid in {t["node_id"] for t in (spec.terminal_nodes or [])}:
                continue
            # Leaf: no next_nodes and no conditional_next targets
            has_next = bool(node.get("next_nodes"))
            has_cond = bool(node.get("conditional_next"))
            if not has_next and not has_cond:
                node["next_nodes"] = ["reassessment"]

    # ------------------------------------------------------------------
    # Shared node builder
    # ------------------------------------------------------------------

    def _build_single_node(
        self,
        node_id: str,
        category: ActionCategory,
        recs: list[ExtractedRecommendation],
        parsed: ParsedGuideline,
    ) -> dict[str, Any]:
        mandatory = self._dedup_preserve_order(
            rec.action_id for rec in recs if rec.strength == RecommendationStrength.STRONG
        )
        forbidden = self._dedup_preserve_order(
            rec.action_id for rec in recs if rec.strength == RecommendationStrength.AGAINST
        )
        allowed_base = self._dedup_preserve_order(
            rec.action_id for rec in recs if rec.strength != RecommendationStrength.AGAINST
        )
        prereq_union: list[str] = []
        for rec in recs:
            if rec.prerequisites:
                prereq_union.extend(rec.prerequisites)
        allowed = self._dedup_preserve_order([*mandatory, *allowed_base, *prereq_union])
        forbidden_set = set(forbidden)
        allowed = [a for a in allowed if a not in forbidden_set]

        deadlines: dict[str, int] = {}
        for rec in recs:
            if rec.deadline_minutes is not None and rec.action_id in set(allowed):
                deadlines[rec.action_id] = rec.deadline_minutes

        required_prior: dict[str, list[str]] = {}
        for rec in recs:
            if rec.prerequisites and rec.action_id in set(allowed):
                required_prior[rec.action_id] = list(rec.prerequisites)

        rep = self._select_representative_rec(recs)

        node: dict[str, Any] = {
            "node_id": node_id,
            "node_type": _CATEGORY_NODE_TYPE[category],
            "name": _CATEGORY_NODE_NAME[category],
            "description": rep.text[:200] if rep and rep.text else _CATEGORY_NODE_NAME[category],
            "precondition": None,
            "mandatory_actions": mandatory,
            "allowed_actions": allowed,
            "forbidden_actions": forbidden,
            "deadlines": deadlines,
            "required_prior_actions": required_prior,
            "recommendation_class": self._infer_class(recs),
            "evidence_level": self._infer_evidence_level(recs),
            "source_guideline": (rep.source_guideline if rep else None) or parsed.source or "unknown",
            "source_section": (rep.source_section if rep else None) or _CATEGORY_NODE_NAME[category],
            "source_page": rep.source_page if rep else None,
            "source_quote": rep.source_quote if rep else None,
            "next_nodes": [],
            "conditional_next": {},
        }
        return node

    # ------------------------------------------------------------------
    # v2: Deadline enforcement
    # ------------------------------------------------------------------

    def _enforce_deadlines(
        self,
        nodes: dict[str, dict[str, Any]],
        grouped: dict[ActionCategory, list[ExtractedRecommendation]],
    ) -> None:
        """Ensure every mandatory action has a deadline.

        Priority: LLM-extracted > action-specific default > category default.
        """
        # Build action → category lookup from recs
        action_category: dict[str, ActionCategory] = {}
        for cat, recs in grouped.items():
            for rec in recs:
                action_category[rec.action_id] = cat

        for node in nodes.values():
            deadlines = node.get("deadlines", {})
            mandatory = node.get("mandatory_actions", [])
            allowed = set(node.get("allowed_actions", []))

            for action_id in mandatory:
                if action_id in deadlines:
                    continue  # Already has a deadline

                # Try action-specific default
                if action_id in _DEFAULT_DEADLINE_BY_ACTION:
                    deadlines[action_id] = _DEFAULT_DEADLINE_BY_ACTION[action_id]
                    continue

                # Try category default
                cat = action_category.get(action_id)
                if cat and cat in _DEFAULT_DEADLINE_BY_CATEGORY:
                    deadlines[action_id] = _DEFAULT_DEADLINE_BY_CATEGORY[cat]
                    continue

                # Last resort: 60 minutes
                deadlines[action_id] = 60

            node["deadlines"] = deadlines

    # ------------------------------------------------------------------
    # v2: Allowed-actions enrichment
    # ------------------------------------------------------------------

    def _enrich_allowed_actions(
        self,
        nodes: dict[str, dict[str, Any]],
        domain: str,
    ) -> None:
        """Add domain-standard clinical actions to allowed_actions.

        These are common orders (labs, imaging, vitals) that any clinician
        would reasonably include but the LLM may not have explicitly extracted.
        """
        enrichment = _DOMAIN_ENRICHMENT_ACTIONS.get(domain, [])
        if not enrichment:
            return

        for node in nodes.values():
            allowed = list(node.get("allowed_actions", []))
            forbidden_set = set(node.get("forbidden_actions", []))
            existing = set(allowed)

            for action_id in enrichment:
                if action_id not in existing and action_id not in forbidden_set:
                    allowed.append(action_id)

            node["allowed_actions"] = allowed

    # ------------------------------------------------------------------
    # Shared utilities
    # ------------------------------------------------------------------

    @staticmethod
    def _select_entry_node(
        grouped: dict[ActionCategory, list[ExtractedRecommendation]],
    ) -> str:
        for cat in _CATEGORY_ORDER:
            if grouped.get(cat):
                return _CATEGORY_NODE_ID[cat]
        return "initial_assessment"

    @staticmethod
    def _build_metadata(parsed: ParsedGuideline) -> dict[str, Any]:
        has_branches = bool(getattr(parsed, "branches", None))
        has_rules = bool(getattr(parsed, "conditional_rules", None))
        version_tag = "v2" if (has_branches or has_rules) else "v1"
        return {
            "source": parsed.source,
            "domain": parsed.domain,
            "description": parsed.name,
            "parse_confidence": round(float(parsed.parse_confidence), 4),
            "generated_by": f"cpg_yaml_generator.CPGYAMLGenerator {version_tag}",
        }

    @staticmethod
    def _dedup_preserve_order(items: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        out: list[str] = []
        for item in items:
            if item and item not in seen:
                seen.add(item)
                out.append(item)
        return out

    @staticmethod
    def _select_representative_rec(
        recs: list[ExtractedRecommendation],
    ) -> ExtractedRecommendation | None:
        if not recs:
            return None
        strong = [r for r in recs if r.strength == RecommendationStrength.STRONG]
        return strong[0] if strong else recs[0]

    @staticmethod
    def _infer_class(recs: list[ExtractedRecommendation]) -> str:
        if any(r.strength == RecommendationStrength.STRONG for r in recs):
            return _STRENGTH_TO_CLASS[RecommendationStrength.STRONG]
        if any(r.strength == RecommendationStrength.MODERATE for r in recs):
            return _STRENGTH_TO_CLASS[RecommendationStrength.MODERATE]
        if any(r.strength == RecommendationStrength.WEAK for r in recs):
            return _STRENGTH_TO_CLASS[RecommendationStrength.WEAK]
        return "IIb"

    @staticmethod
    def _infer_evidence_level(recs: list[ExtractedRecommendation]) -> str:
        levels = [r.evidence_level for r in recs if r.evidence_level]
        if not levels:
            return "C"
        for target in ("1A", "A", "1B", "B", "2A", "2B", "C", "3"):
            if any(lev.upper().startswith(target) for lev in levels):
                if "A" in target:
                    return "A"
                if "B" in target:
                    return "B"
                return "C"
        return "C"
