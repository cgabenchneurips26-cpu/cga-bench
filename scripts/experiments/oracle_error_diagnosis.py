
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  DEPRECATED — v3-era experiment script (180 episodes, 4 models)    ║
# ║  Result directories referenced here have been archived:            ║
# ║    results/clean_slate_rescored/ → _archive/results_old_rag_backup ║
# ║    results/clean_slate_20260331_* → _archive/results/              ║
# ║  Current baseline: results/full_706_v6_* (16,944 ep, 8 models)    ║
# ║  See docs/RESULT_LINEAGE_AUDIT.md for full era mapping.           ║
# ╚══════════════════════════════════════════════════════════════════════╝

"""Oracle Error Diagnosis Script

Analyzes why the Oracle agent doesn't achieve 100% CGA scores
across all 15 clean_slate scenarios.

The Oracle uses agent_rules/ decision tables (NEVER cpg_engine).
This script compares Oracle-recommended actions against scenario
expected_actions to identify gaps.

Error categories:
  1. oracle_gap      - Oracle rules don't cover a required action
  2. naming_mismatch - Oracle produces action with different ID than expected
  3. context_gap     - Oracle conditions don't fire because context lacks data
  4. prereq_block    - Oracle has action but prerequisite blocks it
  5. domain_missing  - No Oracle rules for this domain at all
  6. perfect         - Full coverage

Usage:
    PYTHONPATH=. python scripts/experiments/oracle_error_diagnosis.py
"""

import json
import os
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
SCENARIO_DIR = ROOT / "configs" / "scenarios"
RESULTS_DIR = ROOT / "results"
OUTPUT_PATH = ROOT / "evidence_pack" / "analysis" / "oracle_error_decomposition.json"


# ------------------------------------------------------------------
# 1. Load all 15 clean_slate scenarios
# ------------------------------------------------------------------

CLEAN_SLATE_SCENARIOS = [
    "septic_shock_basic",
    "septic_shock_penicillin_allergy",
    "stemi_inferior_rv_trap",
    "dka_moderate_basic",
    "dka_hypokalemia_trap",
    "stroke_tpa_eligible",
    "contrast_aki_prevention_basic",
    "aki_stage1_basic",
    "af_new_onset_basic",
    "gi_bleeding_upper_basic",
    "htn_emergency_basic",
    "pe_submassive_basic",
    "copd_moderate_exacerbation",
    "adhf_warm_wet",
    "hemorrhagic_stroke",
]

# Map guideline_graph -> Oracle domain key
GRAPH_TO_DOMAIN: dict[str, str] = {
    "ssc_sepsis_hour1": "sepsis",
    "aha_chest_pain": "chest_pain",
    "aha_stroke": "stroke",
    "aha_heart_failure": "heart_failure",
    "kdigo_aki_full": "aki",
    "kdigo_contrast_aki": "kdigo_contrast_aki",
    "ada_dka_management": "dka",
    "atrial_fibrillation": "atrial_fibrillation",
    "copd_exacerbation": "copd",
    "gi_bleeding": "gi_bleeding",
    "hypertensive_emergency": "hypertensive_emergency",
    "pulmonary_embolism": "pulmonary_embolism",
}


def load_scenario_configs() -> dict[str, dict[str, Any]]:
    """Load all scenario YAML files and return matching clean_slate scenarios."""
    scenarios: dict[str, dict[str, Any]] = {}

    for yaml_file in SCENARIO_DIR.glob("*.yaml"):
        with open(yaml_file) as f:
            data = yaml.safe_load(f)
        for sid, sdata in (data.get("scenarios") or {}).items():
            if sid in CLEAN_SLATE_SCENARIOS:
                scenarios[sid] = sdata

    return scenarios


def build_context_from_scenario(scenario: dict[str, Any]) -> dict[str, Any]:
    """Build Oracle decision table context from scenario config."""
    patient = scenario.get("patient", {})
    vitals = patient.get("vitals", {})
    ground_truth = scenario.get("ground_truth", {})

    context: dict[str, Any] = {
        "working_diagnosis": patient.get("working_diagnosis", ""),
        "chief_complaint": patient.get("chief_complaint", ""),
        "allergies": patient.get("allergies", []),
        "comorbidities": patient.get("comorbidities", []),
        "timestamp_minutes": 0,
    }

    # Vitals
    if vitals:
        context["heart_rate"] = vitals.get("heart_rate")
        context["sbp_mmhg"] = vitals.get("blood_pressure_systolic")
        context["dbp_mmhg"] = vitals.get("blood_pressure_diastolic")
        context["map_mmhg"] = vitals.get("map_mmhg")
        context["respiratory_rate"] = vitals.get("respiratory_rate")
        context["temperature"] = vitals.get("temperature")
        context["oxygen_saturation"] = vitals.get("oxygen_saturation")

        # Compute MAP if missing
        sbp = context.get("sbp_mmhg")
        dbp = context.get("dbp_mmhg")
        if context.get("map_mmhg") is None and sbp and dbp:
            context["map_mmhg"] = (sbp + 2 * dbp) / 3

    # Ground truth (lab values, imaging)
    for key, val in ground_truth.items():
        # Strip lab_ prefix for context variables
        if key.startswith("lab_"):
            short_key = key[4:]  # e.g., lab_lactate -> lactate
            context[short_key] = val
        context[key] = val

    return context


def get_oracle_actions_for_scenario(domain: str, context: dict[str, Any]) -> tuple[list[str], list[str], str | None]:
    """Instantiate Oracle decision table and get recommended + forbidden actions.

    Returns:
        (recommended_action_ids, forbidden_action_ids, error_message)
    """
    try:
        # Import here to avoid module-level import issues
        from cga_bench.agent_rules.af_rules import AFDecisionTable
        from cga_bench.agent_rules.aki_rules import AKIDecisionTable
        from cga_bench.agent_rules.chest_pain_rules import ChestPainDecisionTable
        from cga_bench.agent_rules.copd_rules import COPDDecisionTable
        from cga_bench.agent_rules.dka_rules import DKADecisionTable
        from cga_bench.agent_rules.gi_bleeding_rules import GIBleedingDecisionTable
        from cga_bench.agent_rules.heart_failure_rules import HeartFailureDecisionTable
        from cga_bench.agent_rules.htn_emergency_rules import HTNEmergencyDecisionTable
        from cga_bench.agent_rules.pe_rules import PEDecisionTable
        from cga_bench.agent_rules.sepsis_rules import SepsisDecisionTable
        from cga_bench.agent_rules.stroke_rules import StrokeDecisionTable

        domain_map: dict[str, type] = {
            "sepsis": SepsisDecisionTable,
            "chest_pain": ChestPainDecisionTable,
            "stroke": StrokeDecisionTable,
            "heart_failure": HeartFailureDecisionTable,
            "aki": AKIDecisionTable,
            "kdigo_contrast_aki": AKIDecisionTable,
            "dka": DKADecisionTable,
            "atrial_fibrillation": AFDecisionTable,
            "copd": COPDDecisionTable,
            "gi_bleeding": GIBleedingDecisionTable,
            "hypertensive_emergency": HTNEmergencyDecisionTable,
            "pulmonary_embolism": PEDecisionTable,
        }

        table_cls = domain_map.get(domain)
        if table_cls is None:
            return [], [], f"No decision table class for domain '{domain}'"

        table = table_cls()
        recommendations = table.get_recommended_actions(context, current_time_minutes=0)
        forbidden = table.get_forbidden_actions(context)

        rec_ids = [r.action_id for r in recommendations]
        return rec_ids, forbidden, None

    except Exception as e:
        return [], [], f"Error instantiating Oracle for domain '{domain}': {e}"


def classify_error(
    expected: list[str],
    oracle_recommended: list[str],
    missing: list[str],
    extra: list[str],
    oracle_error: str | None,
) -> tuple[str, str]:
    """Classify the type of Oracle error and provide notes."""
    if oracle_error:
        if "No decision table" in oracle_error:
            return "domain_missing", oracle_error
        return "instantiation_error", oracle_error

    if not missing:
        return "perfect", "Oracle covers all expected actions"

    # Check for naming mismatch patterns
    naming_clues = []
    for m in missing:
        # Look for similar action IDs in oracle_recommended
        m_tokens = set(m.replace("_", " ").split())
        for o in oracle_recommended:
            o_tokens = set(o.replace("_", " ").split())
            overlap = m_tokens & o_tokens
            if len(overlap) >= max(1, len(m_tokens) // 2):
                naming_clues.append(f"'{m}' may match Oracle's '{o}'")

    if naming_clues:
        notes = "Potential naming mismatches: " + "; ".join(naming_clues)
        if len(naming_clues) >= len(missing):
            return "naming_mismatch", notes
        return "mixed_gap_and_naming", notes

    # Check if the missing actions are conditional
    conditional_keywords = [
        "if_",
        "_if_",
        "recheck",
        "continuous",
        "monitor_",
        "hold_",
        "consider_",
    ]
    conditional_missing = [m for m in missing if any(kw in m for kw in conditional_keywords)]

    if conditional_missing and len(conditional_missing) == len(missing):
        return (
            "context_gap",
            f"All missing actions are conditional: {conditional_missing}. "
            "Oracle conditions may not fire without full patient simulation.",
        )

    if conditional_missing:
        return (
            "mixed_oracle_and_context_gap",
            f"Some missing actions are conditional ({conditional_missing}), "
            f"others are unconditional ({[m for m in missing if m not in conditional_missing]})",
        )

    return (
        "oracle_gap",
        f"Oracle rules do not recommend these expected actions: {missing}",
    )


def load_existing_oracle_scores() -> dict[str, dict[str, Any]]:
    """Load actual Oracle scores from oss120b_exp results."""
    scores: dict[str, dict[str, Any]] = {}

    # Core scenarios from oss120b_exp
    exp_dir = RESULTS_DIR / "oss120b_exp"
    if exp_dir.exists():
        for f in exp_dir.glob("*oracle*.json"):
            with open(f) as fp:
                data = json.load(fp)
            sid = data.get("scenario_id", "")
            if sid and sid not in scores:
                scores[sid] = {
                    "compliance_score": data.get("compliance_score"),
                    "sub_scores": data.get("sub_scores", {}),
                    "violations_by_type": data.get("violations_by_type", {}),
                    "actions_count": data.get("actions_count"),
                    "total_violations": data.get("total_violations"),
                }

    # Expansion scenarios from oracle_expansion
    exp2_dir = RESULTS_DIR / "oracle_expansion"
    if exp2_dir.exists():
        for f in exp2_dir.glob("*oracle*.json"):
            if f.name == "oracle_summary.json":
                continue
            with open(f) as fp:
                data = json.load(fp)
            sid = data.get("scenario_id", "")
            if sid:
                scores[sid] = {
                    "compliance_score": data.get("compliance_score"),
                    "sub_scores": data.get("sub_scores", {}),
                    "violations_by_type": data.get("violations_by_type", {}),
                    "actions_count": data.get("actions_count"),
                    "total_violations": data.get("total_violations"),
                }

    return scores


def main() -> None:
    print("=" * 70)
    print("Oracle Error Diagnosis")
    print("=" * 70)

    # Load scenario configs
    scenarios = load_scenario_configs()
    missing_scenarios = [s for s in CLEAN_SLATE_SCENARIOS if s not in scenarios]
    if missing_scenarios:
        print(f"WARNING: Could not find configs for: {missing_scenarios}")

    # Load existing Oracle scores
    existing_scores = load_existing_oracle_scores()

    # Analyze each scenario
    results: dict[str, Any] = {}
    perfect_count = 0
    partial_count = 0
    no_coverage_count = 0

    for sid in CLEAN_SLATE_SCENARIOS:
        scenario = scenarios.get(sid)
        if not scenario:
            results[sid] = {
                "domain": "unknown",
                "error": "Scenario config not found",
                "error_classification": "config_missing",
            }
            no_coverage_count += 1
            continue

        graph = scenario.get("guideline_graph", "")
        domain = GRAPH_TO_DOMAIN.get(graph, graph)
        expected = scenario.get("expected_actions", [])
        forbidden = scenario.get("forbidden_actions", [])

        # Build context from scenario
        context = build_context_from_scenario(scenario)

        # Get Oracle recommendations
        oracle_rec, oracle_forbidden, oracle_error = get_oracle_actions_for_scenario(domain, context)

        # Compare
        expected_set = set(expected)
        oracle_set = set(oracle_rec)

        matched = sorted(expected_set & oracle_set)
        missing_from_oracle = sorted(expected_set - oracle_set)
        extra_in_oracle = sorted(oracle_set - expected_set)

        # Classify error
        classification, notes = classify_error(expected, oracle_rec, missing_from_oracle, extra_in_oracle, oracle_error)

        # Get existing score if available
        existing = existing_scores.get(sid, {})

        entry: dict[str, Any] = {
            "domain": domain,
            "guideline_graph": graph,
            "expected_actions": expected,
            "expected_count": len(expected),
            "oracle_recommended": oracle_rec,
            "oracle_recommended_count": len(oracle_rec),
            "oracle_forbidden": oracle_forbidden,
            "matched": matched,
            "matched_count": len(matched),
            "missing_from_oracle": missing_from_oracle,
            "extra_in_oracle": extra_in_oracle,
            "coverage_ratio": (len(matched) / len(expected) if expected else 1.0),
            "error_classification": classification,
            "notes": notes,
        }

        if existing:
            entry["actual_compliance_score"] = existing.get("compliance_score")
            entry["actual_sub_scores"] = existing.get("sub_scores")
            entry["actual_violations_by_type"] = existing.get("violations_by_type")
            entry["actual_total_violations"] = existing.get("total_violations")

        results[sid] = entry

        # Categorize
        if classification == "perfect":
            perfect_count += 1
        elif classification in ("domain_missing", "instantiation_error"):
            no_coverage_count += 1
        else:
            partial_count += 1

        # Print summary
        icon = {
            "perfect": "OK",
            "domain_missing": "FAIL",
            "instantiation_error": "FAIL",
        }.get(classification, "PARTIAL")

        cov = entry["coverage_ratio"]
        actual = existing.get("compliance_score", "N/A")
        print(f"  [{icon:7s}] {sid:40s} coverage={cov:.0%} actual_score={actual} classification={classification}")
        if missing_from_oracle:
            print(f"           missing: {missing_from_oracle}")
        if extra_in_oracle and len(extra_in_oracle) <= 10:
            print(f"           extra:   {extra_in_oracle}")
        elif extra_in_oracle:
            print(f"           extra:   {len(extra_in_oracle)} actions not in expected")

    print()
    print("=" * 70)
    print("SUMMARY")
    print("=" * 70)
    print(f"  Total scenarios:    {len(CLEAN_SLATE_SCENARIOS)}")
    print(f"  Perfect coverage:   {perfect_count}")
    print(f"  Partial coverage:   {partial_count}")
    print(f"  No coverage:        {no_coverage_count}")

    # Build output
    output = {
        "summary": {
            "total_scenarios": len(CLEAN_SLATE_SCENARIOS),
            "perfect_coverage": perfect_count,
            "partial_coverage": partial_count,
            "no_coverage": no_coverage_count,
            "analysis_note": (
                "Oracle uses agent_rules/ decision tables (NEVER cpg_engine). "
                "Coverage ratio = |matched| / |expected_actions|. "
                "Missing actions are expected by the scenario but not "
                "recommended by Oracle rules. "
                "Extra actions are recommended by Oracle but not in "
                "the scenario's expected_actions list."
            ),
        },
        "error_taxonomy": {
            "perfect": "Oracle covers all expected actions",
            "oracle_gap": "Oracle rules simply don't include required actions",
            "naming_mismatch": ("Oracle produces semantically equivalent actions with different action_ids"),
            "context_gap": (
                "Oracle has conditional rules but context data doesn't trigger them (missing lab values, vitals, etc.)"
            ),
            "prereq_block": ("Oracle has the action but prerequisite constraints block it"),
            "mixed_gap_and_naming": ("Combination of naming mismatches and genuine oracle gaps"),
            "mixed_oracle_and_context_gap": (
                "Some actions missing due to oracle gaps, others due to context/conditional issues"
            ),
            "domain_missing": "No Oracle decision table exists for this domain",
        },
        "scenarios": results,
    }

    # Save
    os.makedirs(OUTPUT_PATH.parent, exist_ok=True)
    with open(OUTPUT_PATH, "w") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    print(f"\nOutput saved to: {OUTPUT_PATH}")

    # Print detailed error analysis
    print()
    print("=" * 70)
    print("DETAILED ERROR ANALYSIS")
    print("=" * 70)

    for sid, entry in results.items():
        if entry.get("error_classification") == "perfect":
            continue
        print(f"\n--- {sid} (domain={entry.get('domain')}) ---")
        print(f"  Classification: {entry.get('error_classification')}")
        print(f"  Coverage: {entry.get('coverage_ratio', 0):.0%}")
        if entry.get("actual_compliance_score") is not None:
            print(f"  Actual CGA Score: {entry['actual_compliance_score']}")
        print(f"  Notes: {entry.get('notes', '')}")
        missing = entry.get("missing_from_oracle", [])
        if missing:
            print(f"  Missing from Oracle ({len(missing)}):")
            for m in missing:
                print(f"    - {m}")
        extra = entry.get("extra_in_oracle", [])
        if extra:
            print(f"  Extra in Oracle ({len(extra)}):")
            for e in extra[:15]:
                print(f"    + {e}")
            if len(extra) > 15:
                print(f"    ... and {len(extra) - 15} more")


if __name__ == "__main__":
    main()
