"""Tests for CPGYAMLGenerator v2/v3 (Phase 2a + 2b).

Covers:
  - v1 backward compatibility (no branches → linear chain)
  - Multi-node branching (decision + sub-nodes)
  - conditional_next generation
  - conditional_rules rendering
  - Deadline enforcement
  - Allowed-actions enrichment
  - Validator compliance (all invariants)
  - v3: ReassessmentSpec → reassessment + disposition + terminal nodes
"""

from __future__ import annotations

import yaml

from cga_bench.semantic_layer.cpg_parser import (
    ActionCategory,
    ExtractedBranch,
    ExtractedConditionalRule,
    ExtractedRecommendation,
    ParsedGuideline,
    RecommendationStrength,
)
from cga_bench.semantic_layer.cpg_yaml_generator import (
    _DEFAULT_DEADLINE_BY_ACTION,
    _DEFAULT_DEADLINE_BY_CATEGORY,
    CPGYAMLGenerator,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _make_rec(
    rec_id: str,
    action_id: str,
    strength: RecommendationStrength = RecommendationStrength.STRONG,
    category: ActionCategory = ActionCategory.TREATMENT,
    deadline_minutes: int | None = None,
    prerequisites: list[str] | None = None,
    evidence_level: str | None = "B",
    branch_label: str | None = None,
    source_guideline: str = "TEST 2024",
    source_section: str = "Rec 1",
) -> ExtractedRecommendation:
    return ExtractedRecommendation(
        recommendation_id=rec_id,
        text=f"Test recommendation {rec_id}",
        strength=strength,
        category=category,
        action_id=action_id,
        action_type="give_medication",
        deadline_minutes=deadline_minutes,
        prerequisites=prerequisites or [],
        evidence_level=evidence_level,
        branch_label=branch_label,
        source_guideline=source_guideline,
        source_section=source_section,
    )


def _make_branch(
    branch_id: str,
    parent_category: ActionCategory = ActionCategory.TREATMENT,
    condition: str = "state.working_diagnosis == 'severe'",
    node_id: str | None = None,
    node_name: str = "Severe Bundle",
) -> ExtractedBranch:
    return ExtractedBranch(
        branch_id=branch_id,
        parent_category=parent_category,
        condition=condition,
        condition_label=branch_id.replace("_", " ").title(),
        node_id=node_id or f"{branch_id}_bundle",
        node_name=node_name,
        description=f"Branch for {branch_id}",
        precondition=condition,
    )


def _make_conditional_rule(
    rule_id: str = "TEST-ALLERGY-NO-DRUG",
    condition: str = "'penicillin' in patient.allergies",
    effect_type: str = "FORBIDDEN",
    affected_actions: list[str] | None = None,
    severity: str = "HIGH",
) -> ExtractedConditionalRule:
    return ExtractedConditionalRule(
        rule_id=rule_id,
        condition=condition,
        effect_type=effect_type,
        affected_actions=affected_actions or ["give_cephalosporin"],
        evidence="Test Evidence 2024",
        severity=severity,
        description="Test conditional rule",
        condition_variables=["patient.allergies"],
        trigger_range={"patient.allergies": {"contains": "penicillin", "type": "list_contains"}},
        normal_range={"patient.allergies": {"not_contains": "penicillin", "type": "list_not_contains"}},
    )


def _make_parsed(
    recs: list[ExtractedRecommendation],
    branches: list[ExtractedBranch] | None = None,
    conditional_rules: list[ExtractedConditionalRule] | None = None,
    domain: str = "sepsis",
    guideline_id: str = "test_guideline",
) -> ParsedGuideline:
    return ParsedGuideline(
        guideline_id=guideline_id,
        name="Test Guideline",
        source="TEST 2024",
        domain=domain,
        version="1.0",
        recommendations=recs,
        branches=branches or [],
        conditional_rules=conditional_rules or [],
        parse_confidence=0.9,
    )


# ---------------------------------------------------------------------------
# v1 backward compatibility
# ---------------------------------------------------------------------------


class TestV1BackwardCompat:
    """When no branches are present, v2 generator produces v1-equivalent output."""

    def test_linear_chain_no_branches(self) -> None:
        recs = [
            _make_rec("r1", "order_lab_lactate", category=ActionCategory.DIAGNOSTIC),
            _make_rec("r2", "give_antibiotics", category=ActionCategory.TREATMENT),
            _make_rec("r3", "monitor_vitals", category=ActionCategory.MONITORING),
        ]
        parsed = _make_parsed(recs)
        gen = CPGYAMLGenerator()
        result = gen.generate(parsed)

        assert result["entry_node"] == "diagnostic_workup"
        assert "diagnostic_workup" in result["nodes"]
        assert "treatment_plan" in result["nodes"]
        assert "monitoring_reassessment" in result["nodes"]

        # Linear chain
        assert result["nodes"]["diagnostic_workup"]["next_nodes"] == ["treatment_plan"]
        assert result["nodes"]["treatment_plan"]["next_nodes"] == ["monitoring_reassessment"]
        assert result["nodes"]["monitoring_reassessment"]["next_nodes"] == []

    def test_single_category_produces_single_node(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        result = CPGYAMLGenerator().generate(parsed)

        assert len(result["nodes"]) == 1
        assert "treatment_plan" in result["nodes"]

    def test_mandatory_in_allowed(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        result = CPGYAMLGenerator().generate(parsed)

        node = result["nodes"]["treatment_plan"]
        assert "give_antibiotics" in node["mandatory_actions"]
        assert "give_antibiotics" in node["allowed_actions"]

    def test_forbidden_not_in_allowed(self) -> None:
        recs = [
            _make_rec("r1", "give_antibiotics"),
            _make_rec("r2", "give_nsaid", strength=RecommendationStrength.AGAINST),
        ]
        parsed = _make_parsed(recs)
        result = CPGYAMLGenerator().generate(parsed)

        node = result["nodes"]["treatment_plan"]
        assert "give_nsaid" in node["forbidden_actions"]
        assert "give_nsaid" not in node["allowed_actions"]

    def test_metadata_v1_tag(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        result = CPGYAMLGenerator().generate(parsed)

        assert "v1" in result["metadata"]["generated_by"]


# ---------------------------------------------------------------------------
# Multi-node branching
# ---------------------------------------------------------------------------


class TestMultiNodeBranching:
    """v2 branching: categories with branches produce decision + sub-nodes."""

    def test_branching_creates_decision_plus_subnodes(self) -> None:
        recs = [
            _make_rec("r1", "give_antibiotics"),
            _make_rec("r2", "give_fluids"),
            _make_rec("r3", "give_vasopressor", branch_label="severe"),
        ]
        branches = [
            _make_branch(
                "mild", condition="state.working_diagnosis == 'mild'", node_id="mild_bundle", node_name="Mild Bundle"
            ),
            _make_branch(
                "severe",
                condition="state.working_diagnosis == 'severe'",
                node_id="severe_bundle",
                node_name="Severe Bundle",
            ),
        ]
        parsed = _make_parsed(recs, branches=branches)
        result = CPGYAMLGenerator().generate(parsed)

        # Decision node + 2 branch nodes
        assert "treatment_plan" in result["nodes"]
        assert "mild_bundle" in result["nodes"]
        assert "severe_bundle" in result["nodes"]
        assert len(result["nodes"]) >= 3

    def test_decision_node_has_conditional_next(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        branches = [
            _make_branch(
                "sepsis",
                condition="state.working_diagnosis == 'sepsis'",
                node_id="sepsis_bundle",
                node_name="Sepsis Bundle",
            ),
            _make_branch(
                "septic_shock",
                condition="state.working_diagnosis == 'septic_shock'",
                node_id="septic_shock_bundle",
                node_name="Septic Shock Bundle",
            ),
        ]
        parsed = _make_parsed(recs, branches=branches)
        result = CPGYAMLGenerator().generate(parsed)

        decision = result["nodes"]["treatment_plan"]
        assert decision["node_type"] == "decision"
        cond_next = decision["conditional_next"]
        assert "state.working_diagnosis == 'sepsis'" in cond_next
        assert cond_next["state.working_diagnosis == 'sepsis'"] == "sepsis_bundle"
        assert cond_next["state.working_diagnosis == 'septic_shock'"] == "septic_shock_bundle"

    def test_branch_node_inherits_shared_actions(self) -> None:
        recs = [
            _make_rec("r1", "give_antibiotics"),  # shared (no branch_label)
            _make_rec("r2", "give_vasopressor", branch_label="severe"),
        ]
        branches = [
            _make_branch("severe", node_id="severe_bundle"),
        ]
        parsed = _make_parsed(recs, branches=branches)
        result = CPGYAMLGenerator().generate(parsed)

        branch_node = result["nodes"]["severe_bundle"]
        # Shared action inherited
        assert "give_antibiotics" in branch_node["allowed_actions"]

    def test_branch_node_has_precondition(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        branches = [
            _make_branch("severe", condition="state.working_diagnosis == 'severe'", node_id="severe_bundle"),
        ]
        parsed = _make_parsed(recs, branches=branches)
        result = CPGYAMLGenerator().generate(parsed)

        branch = result["nodes"]["severe_bundle"]
        assert branch["precondition"] == "state.working_diagnosis == 'severe'"

    def test_branch_nodes_chain_to_next_category(self) -> None:
        recs = [
            _make_rec("r1", "give_antibiotics", category=ActionCategory.TREATMENT),
            _make_rec("r2", "monitor_vitals", category=ActionCategory.MONITORING),
        ]
        branches = [
            _make_branch("mild", node_id="mild_bundle"),
            _make_branch("severe", node_id="severe_bundle"),
        ]
        parsed = _make_parsed(recs, branches=branches)
        result = CPGYAMLGenerator().generate(parsed)

        # Branch sub-nodes chain to monitoring
        assert result["nodes"]["mild_bundle"]["next_nodes"] == ["monitoring_reassessment"]
        assert result["nodes"]["severe_bundle"]["next_nodes"] == ["monitoring_reassessment"]

    def test_metadata_v2_tag(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        branches = [_make_branch("severe", node_id="severe_bundle")]
        parsed = _make_parsed(recs, branches=branches)
        result = CPGYAMLGenerator().generate(parsed)

        assert "v2" in result["metadata"]["generated_by"]


# ---------------------------------------------------------------------------
# Conditional rules
# ---------------------------------------------------------------------------


class TestConditionalRules:
    """conditional_rules are attached to treatment/plan nodes."""

    def test_rules_attached_to_plan_node(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        rules = [_make_conditional_rule()]
        parsed = _make_parsed(recs, conditional_rules=rules)
        result = CPGYAMLGenerator().generate(parsed)

        # Should have conditional_rules on treatment_plan (plan type)
        node = result["nodes"]["treatment_plan"]
        assert "conditional_rules" in node
        assert len(node["conditional_rules"]) == 1
        assert node["conditional_rules"][0]["rule_id"] == "TEST-ALLERGY-NO-DRUG"

    def test_rule_structure_matches_schema(self) -> None:
        rules = [
            _make_conditional_rule(
                affected_actions=["give_cephalosporin", "give_piperacillin"],
            )
        ]
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs, conditional_rules=rules)
        result = CPGYAMLGenerator().generate(parsed)

        rule = result["nodes"]["treatment_plan"]["conditional_rules"][0]
        assert rule["effect"]["type"] == "FORBIDDEN"
        assert "give_cephalosporin" in rule["effect"]["actions"]
        assert "give_piperacillin" in rule["effect"]["actions"]
        assert rule["severity"] == "HIGH"
        assert "patient.allergies" in rule["condition_variables"]
        assert "trigger_range" in rule
        assert "normal_range" in rule

    def test_rules_attached_to_branch_nodes(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        branches = [
            _make_branch("sepsis", node_id="sepsis_bundle"),
            _make_branch("shock", node_id="shock_bundle"),
        ]
        rules = [_make_conditional_rule()]
        parsed = _make_parsed(recs, branches=branches, conditional_rules=rules)
        result = CPGYAMLGenerator().generate(parsed)

        # Rules should be on branch sub-nodes (plan type), not decision node
        assert "conditional_rules" in result["nodes"]["sepsis_bundle"]
        assert "conditional_rules" in result["nodes"]["shock_bundle"]

    def test_multiple_rules(self) -> None:
        rules = [
            _make_conditional_rule("RULE-1", "'penicillin' in patient.allergies"),
            _make_conditional_rule(
                "RULE-2", "'hf' in patient.comorbidities", affected_actions=["give_aggressive_fluid"]
            ),
            _make_conditional_rule(
                "RULE-3", "patient.age > 70", severity="MODERATE", affected_actions=["delay_antibiotics"]
            ),
        ]
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs, conditional_rules=rules)
        result = CPGYAMLGenerator().generate(parsed)

        node_rules = result["nodes"]["treatment_plan"]["conditional_rules"]
        assert len(node_rules) == 3
        rule_ids = {r["rule_id"] for r in node_rules}
        assert rule_ids == {"RULE-1", "RULE-2", "RULE-3"}


# ---------------------------------------------------------------------------
# Deadline enforcement
# ---------------------------------------------------------------------------


class TestDeadlineEnforcement:
    """Every mandatory action must have a deadline after generation."""

    def test_llm_deadline_preserved(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics", deadline_minutes=45)]
        parsed = _make_parsed(recs)
        result = CPGYAMLGenerator().generate(parsed)

        deadlines = result["nodes"]["treatment_plan"]["deadlines"]
        assert deadlines["give_antibiotics"] == 45

    def test_action_specific_default_applied(self) -> None:
        recs = [_make_rec("r1", "order_lab_lactate", category=ActionCategory.DIAGNOSTIC)]
        parsed = _make_parsed(recs)
        result = CPGYAMLGenerator().generate(parsed)

        deadlines = result["nodes"]["diagnostic_workup"]["deadlines"]
        assert deadlines["order_lab_lactate"] == _DEFAULT_DEADLINE_BY_ACTION["order_lab_lactate"]

    def test_category_default_applied(self) -> None:
        recs = [_make_rec("r1", "custom_assessment_action", category=ActionCategory.ASSESSMENT)]
        parsed = _make_parsed(recs)
        result = CPGYAMLGenerator().generate(parsed)

        deadlines = result["nodes"]["initial_assessment"]["deadlines"]
        assert deadlines["custom_assessment_action"] == _DEFAULT_DEADLINE_BY_CATEGORY[ActionCategory.ASSESSMENT]

    def test_fallback_60min_default(self) -> None:
        recs = [_make_rec("r1", "totally_custom_action_xyz")]
        parsed = _make_parsed(recs, domain="unknown_domain")
        result = CPGYAMLGenerator().generate(parsed)

        deadlines = result["nodes"]["treatment_plan"]["deadlines"]
        assert deadlines["totally_custom_action_xyz"] == 60

    def test_llm_deadline_not_overwritten(self) -> None:
        """LLM-extracted deadline takes priority over defaults."""
        recs = [_make_rec("r1", "order_lab_lactate", category=ActionCategory.DIAGNOSTIC, deadline_minutes=30)]
        parsed = _make_parsed(recs)
        result = CPGYAMLGenerator().generate(parsed)

        deadlines = result["nodes"]["diagnostic_workup"]["deadlines"]
        assert deadlines["order_lab_lactate"] == 30  # NOT the default 60

    def test_all_mandatory_have_deadlines(self) -> None:
        recs = [
            _make_rec("r1", "action_a", category=ActionCategory.DIAGNOSTIC),
            _make_rec("r2", "action_b", category=ActionCategory.TREATMENT),
            _make_rec("r3", "action_c", category=ActionCategory.MONITORING),
        ]
        parsed = _make_parsed(recs)
        result = CPGYAMLGenerator().generate(parsed)

        for node in result["nodes"].values():
            for action_id in node["mandatory_actions"]:
                assert action_id in node["deadlines"], (
                    f"Mandatory action '{action_id}' missing deadline in node '{node['node_id']}'"
                )


# ---------------------------------------------------------------------------
# Allowed-actions enrichment
# ---------------------------------------------------------------------------


class TestAllowedActionsEnrichment:
    """Domain-standard actions are added to allowed_actions."""

    def test_sepsis_enrichment(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs, domain="sepsis")
        result = CPGYAMLGenerator().generate(parsed)

        allowed = result["nodes"]["treatment_plan"]["allowed_actions"]
        # Standard sepsis labs should be present
        assert "order_lab_cbc" in allowed
        assert "order_lab_bmp" in allowed
        assert "order_imaging_chest_xray" in allowed

    def test_enrichment_does_not_add_forbidden(self) -> None:
        recs = [
            _make_rec("r1", "give_antibiotics"),
            _make_rec("r2", "order_lab_cbc", strength=RecommendationStrength.AGAINST),
        ]
        parsed = _make_parsed(recs, domain="sepsis")
        result = CPGYAMLGenerator().generate(parsed)

        node = result["nodes"]["treatment_plan"]
        assert "order_lab_cbc" in node["forbidden_actions"]
        # Enrichment must not re-add forbidden action
        assert "order_lab_cbc" not in node["allowed_actions"]

    def test_unknown_domain_no_enrichment(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs, domain="exotic_rare_disease")
        result = CPGYAMLGenerator().generate(parsed)

        allowed = result["nodes"]["treatment_plan"]["allowed_actions"]
        # Only the extracted action should be present
        assert "give_antibiotics" in allowed
        # No sepsis enrichment
        assert "order_lab_cbc" not in allowed

    def test_enrichment_no_duplicates(self) -> None:
        recs = [
            _make_rec("r1", "give_antibiotics"),
            _make_rec("r2", "order_lab_cbc", strength=RecommendationStrength.MODERATE),
        ]
        parsed = _make_parsed(recs, domain="sepsis")
        result = CPGYAMLGenerator().generate(parsed)

        allowed = result["nodes"]["treatment_plan"]["allowed_actions"]
        assert allowed.count("order_lab_cbc") == 1


# ---------------------------------------------------------------------------
# Validator compliance
# ---------------------------------------------------------------------------


class TestValidatorCompliance:
    """Generated YAML must pass validate_cpg_schema.py invariants."""

    def _validate_graph(self, data: dict[str, Any]) -> list[str]:
        """Inline validator matching scripts/ci/validate_cpg_schema.py logic."""
        errors: list[str] = []

        for field in ("graph_id", "guideline_name", "entry_node", "nodes"):
            if field not in data or data[field] is None:
                errors.append(f"missing top-level '{field}'")

        nodes = data.get("nodes", {})
        if not isinstance(nodes, dict):
            errors.append("'nodes' is not a mapping")
            return errors

        node_ids = set(nodes.keys())
        entry = data.get("entry_node")
        if entry and entry not in node_ids:
            errors.append(f"entry_node '{entry}' not in nodes")

        valid_types = {"decision", "plan", "action", "enquiry"}
        required_fields = {"node_id", "node_type", "name", "mandatory_actions", "source_guideline", "source_section"}

        for nid, node in nodes.items():
            prefix = nid
            for f in required_fields:
                v = node.get(f)
                if v is None or (isinstance(v, str) and not v.strip()):
                    errors.append(f"{prefix}: missing '{f}'")

            if node.get("node_id") != nid:
                errors.append(f"{prefix}: node_id mismatch")

            if node.get("node_type") not in valid_types:
                errors.append(f"{prefix}: invalid node_type '{node.get('node_type')}'")

            # forbidden ∩ allowed = ∅ (strict for non-conditional-rule cases)
            forbidden = set(node.get("forbidden_actions", []))
            allowed = set(node.get("allowed_actions", []))
            # Note: overlap is a WARNING in validator, not error

            # deadlines reference known actions
            deadlines = node.get("deadlines", {})
            all_known = set(node.get("mandatory_actions", [])) | allowed
            for aid in deadlines:
                if aid not in all_known:
                    errors.append(f"{prefix}: deadline for unknown action '{aid}'")

            # next_nodes targets exist
            for next_id in node.get("next_nodes", []):
                if next_id not in node_ids:
                    errors.append(f"{prefix}: next_nodes '{next_id}' not in nodes")

            # conditional_next targets exist
            for _, target in (node.get("conditional_next", {}) or {}).items():
                if target not in node_ids:
                    errors.append(f"{prefix}: conditional_next target '{target}' not in nodes")

        return errors

    def test_v1_basic_valid(self) -> None:
        recs = [
            _make_rec("r1", "order_lab_lactate", category=ActionCategory.DIAGNOSTIC),
            _make_rec("r2", "give_antibiotics"),
        ]
        parsed = _make_parsed(recs)
        result = CPGYAMLGenerator().generate(parsed)
        errors = self._validate_graph(result)
        assert errors == [], f"Validation errors: {errors}"

    def test_v2_branching_valid(self) -> None:
        recs = [
            _make_rec("r1", "give_antibiotics"),
            _make_rec("r2", "give_vasopressor", branch_label="severe"),
            _make_rec("r3", "monitor_vitals", category=ActionCategory.MONITORING),
        ]
        branches = [
            _make_branch("mild", node_id="mild_bundle"),
            _make_branch("severe", node_id="severe_bundle"),
        ]
        rules = [_make_conditional_rule()]
        parsed = _make_parsed(recs, branches=branches, conditional_rules=rules)
        result = CPGYAMLGenerator().generate(parsed)
        errors = self._validate_graph(result)
        assert errors == [], f"Validation errors: {errors}"

    def test_yaml_round_trip(self) -> None:
        """Generated dict survives YAML serialise → deserialise."""
        recs = [
            _make_rec("r1", "give_antibiotics", deadline_minutes=60),
            _make_rec("r2", "monitor_vitals", category=ActionCategory.MONITORING),
        ]
        branches = [_make_branch("severe", node_id="severe_bundle")]
        rules = [_make_conditional_rule()]
        parsed = _make_parsed(recs, branches=branches, conditional_rules=rules)
        original = CPGYAMLGenerator().generate(parsed)

        yaml_str = yaml.safe_dump(original, sort_keys=False, allow_unicode=True)
        restored = yaml.safe_load(yaml_str)

        assert restored["graph_id"] == original["graph_id"]
        assert set(restored["nodes"].keys()) == set(original["nodes"].keys())


# ---------------------------------------------------------------------------
# SSC sepsis-like integration test
# ---------------------------------------------------------------------------


class TestSSCSepsisLikeGraph:
    """Integration test mimicking the hand-crafted SSC graph structure."""

    def test_ssc_like_generation(self) -> None:
        """Build a sepsis-like parsed guideline and verify rich output."""
        recs = [
            # Assessment
            _make_rec("r1", "assess_infection_source", category=ActionCategory.ASSESSMENT, deadline_minutes=10),
            _make_rec("r2", "assess_organ_dysfunction", category=ActionCategory.ASSESSMENT, deadline_minutes=10),
            # Diagnostic
            _make_rec("r3", "order_lab_lactate", category=ActionCategory.DIAGNOSTIC, deadline_minutes=60),
            _make_rec("r4", "order_lab_blood_culture", category=ActionCategory.DIAGNOSTIC, deadline_minutes=60),
            # Treatment — shared
            _make_rec(
                "r5", "give_broad_spectrum_antibiotics", deadline_minutes=60, prerequisites=["order_lab_blood_culture"]
            ),
            # Treatment — septic shock only
            _make_rec("r6", "give_crystalloid_30ml_kg", deadline_minutes=180, branch_label="septic_shock"),
            _make_rec(
                "r7",
                "start_vasopressor_norepinephrine",
                deadline_minutes=60,
                prerequisites=["give_crystalloid_30ml_kg"],
                branch_label="septic_shock",
            ),
            # Monitoring
            _make_rec("r8", "reassess_perfusion", category=ActionCategory.MONITORING),
            _make_rec(
                "r9",
                "remeasure_lactate_if_elevated",
                category=ActionCategory.MONITORING,
                prerequisites=["order_lab_lactate"],
            ),
        ]
        branches = [
            _make_branch(
                "sepsis",
                condition="state.working_diagnosis == 'sepsis'",
                node_id="sepsis_bundle",
                node_name="Sepsis Hour-1 Bundle",
            ),
            _make_branch(
                "septic_shock",
                condition="state.working_diagnosis == 'septic_shock'",
                node_id="septic_shock_bundle",
                node_name="Septic Shock Hour-1 Bundle",
            ),
        ]
        rules = [
            _make_conditional_rule(
                "SEPSIS-PENICILLIN-NO-CEPH",
                "'penicillin_anaphylaxis' in patient.allergies",
                "FORBIDDEN",
                ["give_cephalosporin", "give_ceftriaxone"],
                "CRITICAL",
            ),
            _make_conditional_rule(
                "SEPSIS-HF-CAUTIOUS-FLUID",
                "'heart_failure' in patient.comorbidities",
                "FORBIDDEN",
                ["give_aggressive_fluid_bolus"],
                "HIGH",
            ),
        ]

        parsed = _make_parsed(
            recs, branches=branches, conditional_rules=rules, domain="sepsis", guideline_id="ssc_test"
        )
        result = CPGYAMLGenerator().generate(parsed)

        # Structure checks
        assert result["graph_id"] == "ssc_test"
        assert result["entry_node"] == "initial_assessment"

        # Should have: assessment, diagnostic, treatment_plan (decision),
        # sepsis_bundle, septic_shock_bundle, monitoring
        node_ids = set(result["nodes"].keys())
        assert "initial_assessment" in node_ids
        assert "diagnostic_workup" in node_ids
        assert "treatment_plan" in node_ids
        assert "sepsis_bundle" in node_ids
        assert "septic_shock_bundle" in node_ids
        assert "monitoring_reassessment" in node_ids
        assert len(node_ids) >= 6

        # Decision node has conditional_next
        decision = result["nodes"]["treatment_plan"]
        assert decision["node_type"] == "decision"
        assert len(decision["conditional_next"]) == 2

        # Septic shock bundle has extra mandatory actions
        shock_node = result["nodes"]["septic_shock_bundle"]
        assert "give_broad_spectrum_antibiotics" in shock_node["allowed_actions"]

        # Conditional rules on branch nodes
        assert "conditional_rules" in shock_node
        assert len(shock_node["conditional_rules"]) == 2

        # Enrichment: sepsis domain adds standard labs
        assert "order_lab_cbc" in shock_node["allowed_actions"]
        assert "order_lab_bmp" in shock_node["allowed_actions"]

        # All mandatory actions have deadlines
        for node in result["nodes"].values():
            for aid in node["mandatory_actions"]:
                assert aid in node["deadlines"], f"Missing deadline for '{aid}' in '{node['node_id']}'"

        # Validator compliance
        errors = TestValidatorCompliance()._validate_graph(result)
        assert errors == [], f"Validation errors: {errors}"


# ---------------------------------------------------------------------------
# Write + YAML serialisation
# ---------------------------------------------------------------------------


class TestWriteYAML:
    """Test the write() method produces valid YAML file."""

    def test_write_creates_file(self, tmp_path: Any) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        gen = CPGYAMLGenerator()

        output = tmp_path / "test_graph.yaml"
        result_path = gen.write(parsed, output)

        assert result_path.exists()
        data = yaml.safe_load(result_path.read_text())
        assert data["graph_id"] == "test_guideline"
        assert "treatment_plan" in data["nodes"]


# ---------------------------------------------------------------------------
# v3: Reassessment + Disposition nodes
# ---------------------------------------------------------------------------


def _make_reassessment_spec(
    reassessment_actions: list[str] | None = None,
    reassessment_deadlines: dict[str, int] | None = None,
    reassessment_forbidden: list[str] | None = None,
    disposition_conditions: list[dict[str, str]] | None = None,
    disposition_mandatory: list[str] | None = None,
    disposition_forbidden: list[str] | None = None,
    terminal_nodes: list[dict[str, Any]] | None = None,
) -> ReassessmentSpec:
    from cga_bench.semantic_layer.cpg_parser import ReassessmentSpec

    return ReassessmentSpec(
        reassessment_actions=reassessment_actions or ["reassess_perfusion"],
        reassessment_deadlines=reassessment_deadlines or {"reassess_perfusion": 120},
        reassessment_forbidden=reassessment_forbidden or [],
        disposition_conditions=disposition_conditions
        or [
            {"condition": "state.vitals.map_mmhg < 65", "target": "admit_to_icu"},
            {"condition": "'True'", "target": "admit_to_ward"},
        ],
        disposition_mandatory=disposition_mandatory or ["determine_disposition"],
        disposition_forbidden=disposition_forbidden or ["discharge_home"],
        terminal_nodes=terminal_nodes
        or [
            {
                "node_id": "admit_to_icu",
                "name": "ICU Admission",
                "mandatory": ["admit_to_icu"],
                "allowed": ["admit_to_icu", "continuous_monitoring"],
                "forbidden": ["discharge_home"],
            },
            {
                "node_id": "admit_to_ward",
                "name": "Ward Admission",
                "mandatory": ["admit_to_ward"],
                "allowed": ["admit_to_ward", "schedule_follow_up"],
                "forbidden": [],
            },
        ],
    )


class TestV3ReassessmentDisposition:
    """v3: ReassessmentSpec produces reassessment → disposition → terminal nodes."""

    def test_reassessment_node_created(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        parsed.reassessment_spec = _make_reassessment_spec()
        result = CPGYAMLGenerator().generate(parsed)

        assert "reassessment" in result["nodes"]
        node = result["nodes"]["reassessment"]
        assert node["node_type"] == "enquiry"
        assert "reassess_perfusion" in node["mandatory_actions"]
        assert node["next_nodes"] == ["disposition_decision"]

    def test_disposition_decision_node_created(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        parsed.reassessment_spec = _make_reassessment_spec()
        result = CPGYAMLGenerator().generate(parsed)

        assert "disposition_decision" in result["nodes"]
        node = result["nodes"]["disposition_decision"]
        assert node["node_type"] == "decision"
        assert "determine_disposition" in node["mandatory_actions"]
        assert "state.vitals.map_mmhg < 65" in node["conditional_next"]
        assert node["conditional_next"]["state.vitals.map_mmhg < 65"] == "admit_to_icu"

    def test_terminal_nodes_created(self) -> None:
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        parsed.reassessment_spec = _make_reassessment_spec()
        result = CPGYAMLGenerator().generate(parsed)

        assert "admit_to_icu" in result["nodes"]
        assert "admit_to_ward" in result["nodes"]
        icu = result["nodes"]["admit_to_icu"]
        assert icu["node_type"] == "action"
        assert "admit_to_icu" in icu["mandatory_actions"]
        assert icu["next_nodes"] == []

    def test_leaf_nodes_wired_to_reassessment(self) -> None:
        """Existing leaf nodes (no next_nodes) get wired to reassessment."""
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        parsed.reassessment_spec = _make_reassessment_spec()
        result = CPGYAMLGenerator().generate(parsed)

        # treatment_plan was a leaf → should now point to reassessment
        assert result["nodes"]["treatment_plan"]["next_nodes"] == ["reassessment"]

    def test_non_leaf_nodes_not_rewired(self) -> None:
        """Nodes that already have next_nodes should NOT be rewired."""
        recs = [
            _make_rec("r1", "order_lab_lactate", category=ActionCategory.DIAGNOSTIC),
            _make_rec("r2", "give_antibiotics"),
        ]
        parsed = _make_parsed(recs)
        parsed.reassessment_spec = _make_reassessment_spec()
        result = CPGYAMLGenerator().generate(parsed)

        # diagnostic_workup chains to treatment_plan — should NOT be changed
        assert result["nodes"]["diagnostic_workup"]["next_nodes"] == ["treatment_plan"]
        # treatment_plan (leaf) wired to reassessment
        assert result["nodes"]["treatment_plan"]["next_nodes"] == ["reassessment"]

    def test_skip_if_reassessment_already_exists(self) -> None:
        """If monitoring_reassessment already created a reassessment-like node,
        _append_reassessment_disposition should skip creation.
        """
        recs = [
            _make_rec("r1", "give_antibiotics"),
            _make_rec("r2", "monitor_vitals", category=ActionCategory.MONITORING),
        ]
        parsed = _make_parsed(recs)
        # The monitoring category creates monitoring_reassessment, not "reassessment"
        # so v3 should still add "reassessment" node
        parsed.reassessment_spec = _make_reassessment_spec()
        result = CPGYAMLGenerator().generate(parsed)

        # Both monitoring_reassessment AND reassessment should exist
        assert "monitoring_reassessment" in result["nodes"]
        assert "reassessment" in result["nodes"]

    def test_no_spec_means_no_extra_nodes(self) -> None:
        """Without reassessment_spec, no extra nodes are added."""
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        # parsed.reassessment_spec is None by default
        result = CPGYAMLGenerator().generate(parsed)

        assert "reassessment" not in result["nodes"]
        assert "disposition_decision" not in result["nodes"]

    def test_default_disposition_when_no_conditions(self) -> None:
        """When spec has empty disposition_conditions, default ICU/ward routing applied."""
        spec = _make_reassessment_spec(disposition_conditions=[])
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        parsed.reassessment_spec = spec
        result = CPGYAMLGenerator().generate(parsed)

        disp = result["nodes"]["disposition_decision"]
        assert "state.vitals.map_mmhg < 65" in disp["conditional_next"]
        assert "'True'" in disp["conditional_next"]

    def test_forbidden_not_in_allowed(self) -> None:
        """Forbidden actions on reassessment/disposition nodes should not appear in allowed."""
        spec = _make_reassessment_spec(
            reassessment_forbidden=["discharge_home"],
            disposition_forbidden=["discharge_home"],
        )
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        parsed.reassessment_spec = spec
        result = CPGYAMLGenerator().generate(parsed)

        reassess = result["nodes"]["reassessment"]
        assert "discharge_home" in reassess["forbidden_actions"]

        disp = result["nodes"]["disposition_decision"]
        assert "discharge_home" in disp["forbidden_actions"]

    def test_reassessment_deadlines_preserved(self) -> None:
        spec = _make_reassessment_spec(
            reassessment_actions=["reassess_perfusion", "remeasure_lactate"],
            reassessment_deadlines={"reassess_perfusion": 120, "remeasure_lactate": 360},
        )
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        parsed.reassessment_spec = spec
        result = CPGYAMLGenerator().generate(parsed)

        deadlines = result["nodes"]["reassessment"]["deadlines"]
        assert deadlines["reassess_perfusion"] == 120
        assert deadlines["remeasure_lactate"] == 360

    def test_v3_with_branching_integration(self) -> None:
        """v3 reassessment integrates with v2 branching — branch leaves wire to reassessment."""
        recs = [
            _make_rec("r1", "give_antibiotics"),
            _make_rec("r2", "give_vasopressor", branch_label="shock"),
            _make_rec("r3", "monitor_vitals", category=ActionCategory.MONITORING),
        ]
        branches = [
            _make_branch("mild", node_id="mild_bundle"),
            _make_branch("shock", node_id="shock_bundle"),
        ]
        parsed = _make_parsed(recs, branches=branches)
        parsed.reassessment_spec = _make_reassessment_spec()
        result = CPGYAMLGenerator().generate(parsed)

        # monitoring_reassessment (leaf) → reassessment
        assert result["nodes"]["monitoring_reassessment"]["next_nodes"] == ["reassessment"]
        # reassessment → disposition_decision
        assert result["nodes"]["reassessment"]["next_nodes"] == ["disposition_decision"]
        # terminals exist
        assert "admit_to_icu" in result["nodes"]

    def test_validator_compliance_v3(self) -> None:
        """Full v3 graph passes inline validator."""
        recs = [
            _make_rec("r1", "order_lab_lactate", category=ActionCategory.DIAGNOSTIC),
            _make_rec("r2", "give_antibiotics"),
        ]
        parsed = _make_parsed(recs)
        parsed.reassessment_spec = _make_reassessment_spec()
        result = CPGYAMLGenerator().generate(parsed)

        errors = TestValidatorCompliance()._validate_graph(result)
        assert errors == [], f"Validation errors: {errors}"

    def test_yaml_round_trip_v3(self) -> None:
        """v3 graph survives YAML serialise → deserialise."""
        recs = [_make_rec("r1", "give_antibiotics")]
        parsed = _make_parsed(recs)
        parsed.reassessment_spec = _make_reassessment_spec()
        original = CPGYAMLGenerator().generate(parsed)

        yaml_str = yaml.safe_dump(original, sort_keys=False, allow_unicode=True)
        restored = yaml.safe_load(yaml_str)

        assert set(restored["nodes"].keys()) == set(original["nodes"].keys())
        assert "reassessment" in restored["nodes"]
        assert "disposition_decision" in restored["nodes"]
        assert "admit_to_icu" in restored["nodes"]
