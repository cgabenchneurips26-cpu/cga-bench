#!/usr/bin/env python3
"""Validate CPGYAMLGenerator v2 output against hand-crafted SSC sepsis graph.

Constructs a ParsedGuideline that mimics what a good LLM extraction would
produce for the SSC 2021 Hour-1 Bundle, then generates via v2 and compares
structural metrics against the hand-crafted gold standard.

Usage:
    PYTHONPATH=. python scripts/validate_v2_vs_handcrafted.py
"""

from __future__ import annotations

from pathlib import Path
import sys

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT.parent))

from semantic_layer.cpg_parser import (
    ActionCategory,
    ExtractedBranch,
    ExtractedConditionalRule,
    ExtractedRecommendation,
    ParsedGuideline,
    RecommendationStrength,
)

RecommendationStrength = RecommendationStrength
from semantic_layer.cpg_yaml_generator import CPGYAMLGenerator

# ---------------------------------------------------------------------------
# Build a realistic ParsedGuideline for SSC 2021 Hour-1 Bundle
# ---------------------------------------------------------------------------


def _rec(
    rid: str,
    text: str,
    action_id: str,
    category: ActionCategory,
    strength: RecommendationStrength = RecommendationStrength.STRONG,
    action_type: str = "procedure",
    deadline_minutes: int | None = None,
    prerequisites: list[str] | None = None,
    evidence_level: str = "B",
    source_guideline: str = "SSC 2021",
    source_section: str = "Initial Resuscitation",
    branch_label: str | None = None,
) -> ExtractedRecommendation:
    """Helper to build recs with correct field names."""
    return ExtractedRecommendation(
        recommendation_id=rid,
        text=text,
        strength=strength,
        category=category,
        action_id=action_id,
        action_type=action_type,
        deadline_minutes=deadline_minutes,
        prerequisites=prerequisites or [],
        evidence_level=evidence_level,
        source_guideline=source_guideline,
        source_section=source_section,
        branch_label=branch_label,
    )


S = RecommendationStrength.STRONG
M = RecommendationStrength.MODERATE
W = RecommendationStrength.WEAK


def _build_ssc_parsed() -> ParsedGuideline:
    """Construct a ParsedGuideline mimicking good LLM extraction of SSC 2021."""
    all_recs = [
        # -- ASSESSMENT --
        _rec(
            "ssc-r1",
            "Identify sepsis/septic shock",
            "assess_infection_source",
            ActionCategory.ASSESSMENT,
            S,
            "procedure",
            10,
        ),
        _rec(
            "ssc-r2",
            "Assess organ dysfunction (SOFA/qSOFA)",
            "assess_organ_dysfunction",
            ActionCategory.ASSESSMENT,
            S,
            "procedure",
            10,
        ),
        _rec("ssc-r3", "Assess vital signs", "assess_vital_signs", ActionCategory.ASSESSMENT, M, "procedure"),
        # -- DIAGNOSTIC --
        _rec(
            "ssc-r4",
            "Measure serum lactate level",
            "order_lab_lactate",
            ActionCategory.DIAGNOSTIC,
            S,
            "order_lab",
            60,
            source_section="Diagnosis",
        ),
        _rec(
            "ssc-r5",
            "Obtain blood cultures before antibiotics",
            "order_lab_blood_culture",
            ActionCategory.DIAGNOSTIC,
            S,
            "order_lab",
            60,
            prerequisites=["assess_infection_source"],
            source_section="Diagnosis",
        ),
        # -- TREATMENT (branching: sepsis vs septic_shock) --
        _rec(
            "ssc-r6",
            "Give broad-spectrum antibiotics within 1 hour",
            "give_broad_spectrum_antibiotics",
            ActionCategory.TREATMENT,
            S,
            "give_medication",
            60,
            prerequisites=["order_lab_blood_culture"],
            source_section="Antimicrobial Therapy",
            branch_label="shared",
        ),
        _rec(
            "ssc-r7",
            "Give crystalloid 30ml/kg for septic shock",
            "give_crystalloid_30ml_kg",
            ActionCategory.TREATMENT,
            S,
            "give_medication",
            60,
            source_section="Fluid Resuscitation",
            branch_label="septic_shock",
        ),
        _rec(
            "ssc-r8",
            "Start vasopressor (norepinephrine) if MAP < 65",
            "start_vasopressor_norepinephrine",
            ActionCategory.TREATMENT,
            S,
            "give_medication",
            60,
            prerequisites=["give_crystalloid_30ml_kg"],
            source_section="Vasopressors",
            branch_label="septic_shock",
        ),
        _rec(
            "ssc-r9",
            "Vasopressin as second-line vasopressor",
            "start_vasopressor_vasopressin",
            ActionCategory.TREATMENT,
            M,
            "give_medication",
            source_section="Vasopressors",
            branch_label="septic_shock",
        ),
        _rec(
            "ssc-r10",
            "Crystalloid fluid for sepsis without shock",
            "give_crystalloid_fluid",
            ActionCategory.TREATMENT,
            M,
            "give_medication",
            source_section="Fluid Resuscitation",
            branch_label="sepsis",
        ),
        # -- MONITORING --
        _rec(
            "ssc-r11",
            "Remeasure lactate if initially elevated",
            "remeasure_lactate_if_elevated",
            ActionCategory.MONITORING,
            S,
            "order_lab",
            360,
            source_section="Resuscitation Targets",
        ),
        _rec(
            "ssc-r12",
            "Reassess volume status and tissue perfusion",
            "reassess_perfusion",
            ActionCategory.MONITORING,
            S,
            "reassess",
            source_section="Resuscitation Targets",
        ),
        # -- DISPOSITION (branching: icu vs ward) --
        _rec(
            "ssc-r13",
            "Determine appropriate level of care",
            "determine_disposition",
            ActionCategory.DISPOSITION,
            S,
            "disposition",
            source_section="Disposition",
            branch_label="shared",
        ),
        _rec(
            "ssc-r14",
            "Admit to ICU for shock/vasopressor requirement",
            "admit_to_icu",
            ActionCategory.DISPOSITION,
            M,
            "disposition",
            source_section="Disposition",
            branch_label="icu",
        ),
        _rec(
            "ssc-r15",
            "Admit to ward with monitoring plan",
            "admit_to_ward",
            ActionCategory.DISPOSITION,
            W,
            "disposition",
            source_section="Disposition",
            branch_label="ward",
        ),
        # -- CONTRAINDICATIONS (AGAINST = forbidden) --
        _rec(
            "ssc-r16",
            "Do NOT give NSAIDs in sepsis (renal/GI risk)",
            "give_nsaid",
            ActionCategory.TREATMENT,
            RecommendationStrength.AGAINST,
            "give_medication",
            source_section="Antimicrobial Therapy",
        ),
        _rec(
            "ssc-r17",
            "Do NOT give aggressive fluid without reassessment",
            "give_aggressive_fluid_without_reassessment",
            ActionCategory.TREATMENT,
            RecommendationStrength.AGAINST,
            "give_medication",
            source_section="Fluid Resuscitation",
        ),
        _rec(
            "ssc-r18",
            "Do NOT use hydroxyethyl starch",
            "give_hydroxyethyl_starch",
            ActionCategory.TREATMENT,
            RecommendationStrength.AGAINST,
            "give_medication",
            source_section="Fluid Resuscitation",
        ),
    ]

    # -- Branches --
    branches = [
        # Treatment branching: sepsis vs septic_shock
        ExtractedBranch(
            branch_id="treatment-sepsis",
            parent_category=ActionCategory.TREATMENT,
            condition="state.working_diagnosis == 'sepsis'",
            condition_label="sepsis_without_shock",
            node_id="sepsis_bundle",
            node_name="Sepsis Hour-1 Bundle",
            description="Bundle for sepsis without shock",
            precondition="state.working_diagnosis == 'sepsis'",
        ),
        ExtractedBranch(
            branch_id="treatment-shock",
            parent_category=ActionCategory.TREATMENT,
            condition="state.working_diagnosis == 'septic_shock'",
            condition_label="septic_shock",
            node_id="septic_shock_bundle",
            node_name="Septic Shock Hour-1 Bundle",
            description="Bundle for septic shock with vasopressors + aggressive fluid resuscitation",
            precondition="state.working_diagnosis == 'septic_shock'",
        ),
        # Disposition branching: icu vs ward
        ExtractedBranch(
            branch_id="disposition-icu",
            parent_category=ActionCategory.DISPOSITION,
            condition="state.vitals.map_mmhg < 65 or 'vasopressor' in str(state.medications_given)",
            condition_label="icu_admission",
            node_id="admit_to_icu",
            node_name="Admit to ICU",
            description="ICU admission for hemodynamic instability",
            precondition="state.vitals.map_mmhg < 65",
        ),
        ExtractedBranch(
            branch_id="disposition-ward",
            parent_category=ActionCategory.DISPOSITION,
            condition="True",
            condition_label="ward_admission",
            node_id="admit_to_ward",
            node_name="Admit to Ward",
            description="Ward admission for stable sepsis patients",
            precondition=None,
        ),
    ]

    # -- Conditional rules (safety constraints on treatment) --
    conditional_rules = [
        ExtractedConditionalRule(
            rule_id="SSC-CR-01",
            condition="'penicillin_anaphylaxis' in patient.allergies",
            effect_type="FORBIDDEN",
            affected_actions=["give_ampicillin", "give_amoxicillin", "give_piperacillin"],
            evidence="Cross-reactivity risk 1-2%",
            severity="HIGH",
            description="Penicillin allergy cross-reactivity",
            condition_variables=["patient.allergies"],
        ),
        ExtractedConditionalRule(
            rule_id="SSC-CR-02",
            condition="'ckd_stage_4_5' in patient.comorbidities",
            effect_type="FORBIDDEN",
            affected_actions=["give_nsaid", "give_gentamicin_high_dose"],
            evidence="Nephrotoxicity risk",
            severity="HIGH",
            description="Renal-toxic agents in CKD patients",
            condition_variables=["patient.comorbidities"],
        ),
        ExtractedConditionalRule(
            rule_id="SSC-CR-03",
            condition="patient.vitals.map_mmhg < 65",
            effect_type="REQUIRED",
            affected_actions=["start_vasopressor_norepinephrine"],
            evidence="MAP target 65 mmHg per SSC 2021",
            severity="HIGH",
            description="Vasopressor required for persistent hypotension",
            condition_variables=["patient.vitals.map_mmhg"],
            trigger_range={"max": 65},
            normal_range={"min": 65, "max": 90},
        ),
        ExtractedConditionalRule(
            rule_id="SSC-CR-04",
            condition="patient.lactate > 4.0",
            effect_type="REQUIRED",
            affected_actions=["give_crystalloid_30ml_kg", "remeasure_lactate_if_elevated"],
            evidence="Lactate > 4 = tissue hypoperfusion",
            severity="HIGH",
            description="Aggressive resuscitation for high lactate",
            condition_variables=["patient.lactate"],
            trigger_range={"min": 4.0},
            normal_range={"min": 0, "max": 2.0},
        ),
        ExtractedConditionalRule(
            rule_id="SSC-CR-05",
            condition="patient.age < 18",
            effect_type="FORBIDDEN",
            affected_actions=["start_vasopressor_vasopressin"],
            evidence="Pediatric dosing not covered by SSC adult guidelines",
            severity="MODERATE",
            description="Vasopressin contraindicated in pediatric patients",
            condition_variables=["patient.age"],
        ),
        ExtractedConditionalRule(
            rule_id="SSC-CR-06",
            condition="'heart_failure_ef_lt_30' in patient.comorbidities",
            effect_type="FORBIDDEN",
            affected_actions=["give_crystalloid_30ml_kg"],
            evidence="Fluid overload risk in severe HF",
            severity="HIGH",
            description="Aggressive fluids contraindicated in severe HF",
            condition_variables=["patient.comorbidities"],
        ),
        ExtractedConditionalRule(
            rule_id="SSC-CR-07",
            condition="'liver_cirrhosis' in patient.comorbidities",
            effect_type="FORBIDDEN",
            affected_actions=["give_acetaminophen_high_dose"],
            evidence="Hepatotoxicity risk",
            severity="MODERATE",
            description="High-dose acetaminophen in cirrhosis",
            condition_variables=["patient.comorbidities"],
        ),
    ]

    return ParsedGuideline(
        guideline_id="ssc_sepsis_hour1_bundle",
        name="Surviving Sepsis Campaign Hour-1 Bundle",
        version="2021.1",
        domain="sepsis",
        source="SSC 2021",
        recommendations=all_recs,
        branches=branches,
        conditional_rules=conditional_rules,
    )


# ---------------------------------------------------------------------------
# Metrics extraction
# ---------------------------------------------------------------------------


def _extract_metrics(graph: dict) -> dict:
    """Extract structural metrics from a CPG graph dict."""
    nodes = graph["nodes"]
    metrics = {
        "n_nodes": len(nodes),
        "node_types": {},
        "total_mandatory": 0,
        "total_allowed": 0,
        "total_forbidden": 0,
        "total_deadlines": 0,
        "total_conditional_next": 0,
        "total_conditional_rules": 0,
        "branching_points": 0,
        "has_preconditions": 0,
    }
    for nid, n in nodes.items():
        nt = n.get("node_type", "unknown")
        metrics["node_types"][nt] = metrics["node_types"].get(nt, 0) + 1
        metrics["total_mandatory"] += len(n.get("mandatory_actions", []))
        metrics["total_allowed"] += len(n.get("allowed_actions", []))
        metrics["total_forbidden"] += len(n.get("forbidden_actions", []))
        metrics["total_deadlines"] += len(n.get("deadlines", {}))
        cn = n.get("conditional_next", {})
        metrics["total_conditional_next"] += len(cn) if isinstance(cn, dict) else 0
        metrics["total_conditional_rules"] += len(n.get("conditional_rules", []))
        if cn:
            metrics["branching_points"] += 1
        if n.get("precondition"):
            metrics["has_preconditions"] += 1
    return metrics


def _print_comparison(gold_metrics: dict, gen_metrics: dict) -> list[str]:
    """Print side-by-side comparison table. Returns list of failures."""
    failures: list[str] = []
    print("\n" + "=" * 70)
    print("  STRUCTURAL COMPARISON: Hand-crafted vs v2-Generated")
    print("=" * 70)
    print(f"  {'Metric':<30} {'Gold':>8} {'v2-Gen':>8} {'Status':>8}")
    print("  " + "-" * 56)

    checks = [
        ("n_nodes", "Nodes", ">=", 5),
        ("total_mandatory", "Mandatory actions", ">=", 5),
        ("total_allowed", "Allowed actions", ">=", 20),
        ("total_forbidden", "Forbidden actions", ">=", 1),
        ("total_deadlines", "Deadlines", ">=", 5),
        ("total_conditional_next", "Conditional-next entries", ">=", 2),
        ("total_conditional_rules", "Conditional rules", ">=", 3),
        ("branching_points", "Branching points", ">=", 2),
        ("has_preconditions", "Nodes with preconditions", ">=", 2),
    ]

    for key, label, op, threshold in checks:
        gold_val = gold_metrics.get(key, 0)
        gen_val = gen_metrics.get(key, 0)
        if op == ">=" and gen_val >= threshold:
            status = "PASS"
        else:
            status = "FAIL"
            failures.append(f"{label}: gold={gold_val}, gen={gen_val}, need>={threshold}")

        print(f"  {label:<30} {gold_val:>8} {gen_val:>8} {status:>8}")

    # Node type distribution
    print("\n  Node type distribution:")
    all_types = sorted(set(list(gold_metrics["node_types"].keys()) + list(gen_metrics["node_types"].keys())))
    for nt in all_types:
        g = gold_metrics["node_types"].get(nt, 0)
        v = gen_metrics["node_types"].get(nt, 0)
        print(f"    {nt:<20} {g:>5} {v:>5}")

    # Ratio metrics (v2/gold)
    print("\n  Coverage ratios (v2/gold):")
    for key, label in [
        ("n_nodes", "Nodes"),
        ("total_mandatory", "Mandatory"),
        ("total_allowed", "Allowed"),
        ("total_conditional_rules", "Cond. rules"),
    ]:
        gold_val = gold_metrics.get(key, 1)
        gen_val = gen_metrics.get(key, 0)
        ratio = gen_val / max(gold_val, 1)
        print(f"    {label:<20} {ratio:>6.1%}")

    print("=" * 70)
    return failures


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    # Load gold standard
    gold_path = REPO_ROOT / "cpg_model" / "graphs" / "ssc_sepsis_hour1_bundle.yaml"
    with open(gold_path) as f:
        gold_graph = yaml.safe_load(f)
    gold_metrics = _extract_metrics(gold_graph)

    # Generate via v2
    parsed = _build_ssc_parsed()
    gen = CPGYAMLGenerator()
    gen_graph = gen.generate(parsed)
    gen_metrics = _extract_metrics(gen_graph)

    # Compare
    failures = _print_comparison(gold_metrics, gen_metrics)

    # Print node list
    print("\n  Generated nodes:")
    for nid, n in gen_graph["nodes"].items():
        cn = len(n.get("conditional_next", {})) if isinstance(n.get("conditional_next"), dict) else 0
        cr = len(n.get("conditional_rules", []))
        print(
            f"    {nid:<30} type={n['node_type']:<10} "
            f"mandatory={len(n.get('mandatory_actions', []))} "
            f"allowed={len(n.get('allowed_actions', []))} "
            f"deadlines={len(n.get('deadlines', {}))} "
            f"cond_next={cn} cond_rules={cr}"
        )

    # Write generated YAML for inspection
    out_path = REPO_ROOT / "cpg_model" / "graphs_llm_smoke" / "ssc_v2_validation.yaml"
    gen.write(parsed, out_path)
    print(f"\n  Written to: {out_path}")

    if failures:
        print(f"\n  FAILURES ({len(failures)}):")
        for f in failures:
            print(f"    - {f}")
        return 1

    print("\n  ALL CHECKS PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
