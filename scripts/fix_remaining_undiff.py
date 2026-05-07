"""Fix remaining undifferentiated traps (Root Cause A leftover + Root Cause B).

Root Cause A leftover: ACLS/DKA/AF rules that didn't get companions in first pass.
Root Cause B: conditional forbidden actions also appear in normal scenarios' union
  because condition='True' rules fire for everyone, or normal patients also trigger
  the condition.

Strategy:
  1. Add missing companion FORBIDDEN rules for remaining Root Cause A.
  2. For Root Cause B 'condition=True' rules: add node-specific forbidden actions
     directly to the nodes they belong to (make them truly unconditional), then add
     NEW conditional rules with proper conditions for trap differentiation.
  3. For Root Cause B proper conditional rules: add additional unique forbidden
     companions that are extremely specific in naming.
"""

from __future__ import annotations

import copy
from pathlib import Path

import yaml

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"
ANALYSIS_FILE = Path(__file__).parent.parent / "evidence_pack" / "undifferentiated_trap_analysis.json"

# ── Missing Root Cause A companions ─────────────────────────────────────
MISSING_ROOT_A_COMPANIONS: dict[str, dict] = {
    "ACLS-OPIOID-NALOXONE": {
        "rule_id": "ACLS-OPIOID-NALOXONE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_additional_opioid_during_arrest",
                "give_long_acting_sedative_during_arrest",
            ],
        },
        "evidence": "AHA ACLS 2020; additional CNS depressants worsen arrest prognosis",
        "severity": "CRITICAL",
        "description": "Additional opioids or sedatives during opioid-associated "
        "cardiac arrest worsen respiratory and cardiac depression.",
    },
    "ACLS-PREGNANCY-PERIMORTEM-CSECTION": {
        "rule_id": "ACLS-PREGNANCY-PERIMORTEM-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "delay_perimortem_csection_beyond_4min",
                "place_pregnant_arrest_patient_supine",
            ],
        },
        "evidence": "AHA ACLS 2020; perimortem C-section within 4 min of arrest; "
        "aortocaval compression reduces CPR efficacy",
        "severity": "CRITICAL",
        "description": "Perimortem C-section must begin within 4 minutes of maternal arrest; "
        "supine positioning compresses IVC reducing CPR blood flow.",
    },
    "ACLS-TAMPONADE-PERICARDIOCENTESIS": {
        "rule_id": "ACLS-TAMPONADE-PERICARDIOCENTESIS-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "delay_pericardiocentesis_for_imaging_in_arrest",
                "give_vasopressors_only_in_tamponade_arrest",
            ],
        },
        "evidence": "AHA ACLS 2020; cardiac tamponade in arrest requires immediate "
        "pericardiocentesis; vasopressors alone cannot overcome obstruction",
        "severity": "CRITICAL",
        "description": "Cardiac tamponade in arrest needs immediate pericardiocentesis; "
        "vasopressors without drainage cannot restore circulation.",
    },
    "ACLS-TENSION-PNEUMO-DECOMPRESS": {
        "rule_id": "ACLS-TENSION-PNEUMO-DECOMPRESS-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "delay_needle_decompression_for_xray_in_arrest",
                "give_only_epinephrine_in_tension_pneumo_arrest",
            ],
        },
        "evidence": "AHA ACLS 2020; tension pneumothorax in arrest requires immediate "
        "needle decompression; medications alone cannot resolve obstruction",
        "severity": "CRITICAL",
        "description": "Tension pneumothorax in arrest needs immediate needle "
        "decompression; waiting for imaging or medication-only approach is fatal.",
    },
}

# ── DKA-HYPOK-INSULIN-GATE: existing FORBIDDEN overlaps unconditional ──
# Add MORE unique actions that don't overlap
DKA_HYPOK_ADDITIONAL = {
    "rule_id": "DKA-HYPOK-INSULIN-GATE-UNIQUE-FORBIDDEN",
    "effect": {
        "type": "FORBIDDEN",
        "actions": [
            "start_insulin_drip_without_potassium_correction",
            "give_insulin_bolus_in_severe_hypokalemia",
        ],
    },
    "evidence": "ADA DKA 2024 Section 16.2; insulin drives K+ intracellularly; "
    "K+ < 3.3 requires correction BEFORE insulin initiation",
    "severity": "CRITICAL",
    "description": "Starting insulin without correcting severe hypokalemia causes "
    "fatal cardiac arrhythmia from further K+ shift intracellularly.",
}

# ── Root Cause B: additional unique forbidden for each graph ────────────
# These go into existing conditional rules that fire for trap scenarios
# Action names are HIGHLY SPECIFIC to avoid appearing in normal scenarios
ROOT_B_ADDITIONAL_FORBIDDEN: dict[str, list[dict]] = {
    "acls_cardiac_arrest": [
        {
            "rule_id": "ACLS-SHOCKABLE-NO-BICARB-ADDITIONAL",
            "condition": "'shockable_rhythm' in patient.comorbidities or 'vfib' in patient.comorbidities or 'vtach' in patient.comorbidities",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_routine_bicarbonate_in_shockable_arrest",
                    "delay_defibrillation_for_bicarbonate_push",
                ],
            },
            "evidence": "AHA ACLS 2020; routine sodium bicarbonate is not recommended in "
            "shockable arrest; it delays defibrillation and worsens intracellular acidosis",
            "severity": "HIGH",
            "description": "Routine bicarbonate in VF/pVT is not recommended; it delays "
            "defibrillation and may worsen intracellular acidosis via CO2 generation.",
            "condition_variables": ["patient.comorbidities"],
            "trigger_range": {
                "patient.comorbidities": {
                    "contains": "shockable_rhythm",
                    "type": "list_contains",
                }
            },
            "normal_range": {
                "patient.comorbidities": {
                    "not_contains": "shockable_rhythm",
                    "type": "list_not_contains",
                }
            },
        },
        {
            "rule_id": "ACLS-NONSHOCKABLE-NO-BICARB-ADDITIONAL",
            "condition": "'nonshockable_rhythm' in patient.comorbidities or 'pea' in patient.comorbidities or 'asystole' in patient.comorbidities",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_routine_bicarbonate_in_nonshockable_arrest",
                    "substitute_bicarbonate_for_epinephrine_in_pea",
                ],
            },
            "evidence": "AHA ACLS 2020; routine bicarbonate not indicated in PEA/asystole",
            "severity": "HIGH",
            "description": "Routine bicarbonate in PEA/asystole is not recommended and "
            "should not replace epinephrine as first-line treatment.",
            "condition_variables": ["patient.comorbidities"],
            "trigger_range": {
                "patient.comorbidities": {
                    "contains": "nonshockable_rhythm",
                    "type": "list_contains",
                }
            },
            "normal_range": {
                "patient.comorbidities": {
                    "not_contains": "nonshockable_rhythm",
                    "type": "list_not_contains",
                }
            },
        },
    ],
    "gina_asthma_exacerbation": [
        {
            "rule_id": "ASTHMA-INITIAL-NO-MUCOLYTICS-SPECIFIC",
            "condition": "patient.vitals.get('spo2', 100) < 92",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_mucolytics_in_hypoxic_asthma",
                    "give_acetylcysteine_nebulized_in_acute_asthma",
                ],
            },
            "evidence": "GINA 2024 Section 4.3; mucolytics worsen bronchospasm in "
            "acute exacerbation especially with hypoxia",
            "severity": "HIGH",
            "description": "Nebulized mucolytics like acetylcysteine trigger bronchospasm "
            "in acute asthma exacerbation, particularly dangerous with hypoxia.",
            "condition_variables": ["patient.vitals.spo2"],
            "trigger_range": {"patient.vitals.spo2": {"min": 50, "max": 91, "type": "float"}},
            "normal_range": {"patient.vitals.spo2": {"min": 92, "max": 100, "type": "float"}},
        },
        {
            "rule_id": "ASTHMA-MILD-NO-PHYSIO-SPECIFIC",
            "condition": "'mild_exacerbation' in patient.comorbidities or patient.vitals.get('spo2', 100) >= 92",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_chest_physiotherapy_in_acute_asthma",
                    "perform_percussion_drainage_in_bronchospasm",
                ],
            },
            "evidence": "GINA 2024 Section 4.3; chest physiotherapy increases oxygen "
            "demand and may worsen bronchospasm in acute asthma",
            "severity": "HIGH",
            "description": "Chest physiotherapy/percussion in acute asthma increases "
            "oxygen demand and may trigger further bronchospasm.",
            "condition_variables": ["patient.comorbidities"],
            "trigger_range": {
                "patient.comorbidities": {
                    "contains": "mild_exacerbation",
                    "type": "list_contains",
                }
            },
            "normal_range": {
                "patient.comorbidities": {
                    "not_contains": "mild_exacerbation",
                    "type": "list_not_contains",
                }
            },
        },
        {
            "rule_id": "ASTHMA-SEVERE-NO-ROUTINE-ABX-SPECIFIC",
            "condition": "'severe_exacerbation' in patient.comorbidities",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_routine_antibiotics_in_viral_asthma",
                    "give_empiric_azithromycin_without_infection_evidence",
                ],
            },
            "evidence": "GINA 2024 Section 4.3; antibiotics not indicated for asthma "
            "exacerbation without bacterial infection evidence",
            "severity": "MODERATE",
            "description": "Routine antibiotics in severe asthma without infection evidence "
            "promote resistance and delay appropriate treatment.",
            "condition_variables": ["patient.comorbidities"],
            "trigger_range": {
                "patient.comorbidities": {
                    "contains": "severe_exacerbation",
                    "type": "list_contains",
                }
            },
            "normal_range": {
                "patient.comorbidities": {
                    "not_contains": "severe_exacerbation",
                    "type": "list_not_contains",
                }
            },
        },
        {
            "rule_id": "ASTHMA-NO-THEOPHYLLINE-IN-ACUTE-SPECIFIC",
            "condition": "'acute_exacerbation' in patient.comorbidities",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_iv_theophylline_in_acute_asthma",
                    "give_aminophylline_in_acute_exacerbation",
                ],
            },
            "evidence": "GINA 2024 Section 4.3; theophylline/aminophylline not "
            "recommended in acute asthma due to narrow therapeutic index and toxicity",
            "severity": "HIGH",
            "description": "IV theophylline/aminophylline in acute asthma has narrow "
            "therapeutic index with seizure and arrhythmia risk.",
            "condition_variables": ["patient.comorbidities"],
            "trigger_range": {
                "patient.comorbidities": {
                    "contains": "acute_exacerbation",
                    "type": "list_contains",
                }
            },
            "normal_range": {
                "patient.comorbidities": {
                    "not_contains": "acute_exacerbation",
                    "type": "list_not_contains",
                }
            },
        },
    ],
    "kdigo_aki_full": [
        {
            "rule_id": "AKI-STAGE1-AMINOGLYCOSIDE-SPECIFIC",
            "condition": "patient.labs.get('creatinine', 0.8) > 1.2",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_aminoglycoside_without_tdm_in_stage1_aki",
                    "give_gentamicin_empiric_without_renal_dosing",
                ],
            },
            "evidence": "KDIGO AKI 2012 Section 3.1; aminoglycosides without TDM in AKI compound nephrotoxicity",
            "severity": "HIGH",
            "description": "Aminoglycosides in Stage 1 AKI require therapeutic drug monitoring; "
            "empiric dosing without renal adjustment causes further injury.",
            "condition_variables": ["patient.labs.creatinine"],
            "trigger_range": {"patient.labs.creatinine": {"min": 1.3, "max": 15.0, "type": "float"}},
            "normal_range": {"patient.labs.creatinine": {"min": 0.5, "max": 1.2, "type": "float"}},
        },
        {
            "rule_id": "AKI-STAGE2-CONTRAST-SPECIFIC",
            "condition": "patient.labs.get('egfr', 90) < 45",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_iodinated_contrast_without_prep_in_aki_stage2",
                    "order_ct_with_contrast_without_nephrology_consult_in_aki",
                ],
            },
            "evidence": "KDIGO AKI 2012 Section 3.2; contrast in AKI Stage 2 without "
            "preparation causes further renal injury",
            "severity": "HIGH",
            "description": "Contrast administration in AKI Stage 2 without hydration and "
            "preparation significantly worsens renal injury.",
            "condition_variables": ["patient.labs.egfr"],
            "trigger_range": {"patient.labs.egfr": {"min": 5, "max": 44, "type": "float"}},
            "normal_range": {"patient.labs.egfr": {"min": 60, "max": 120, "type": "float"}},
        },
        {
            "rule_id": "AKI-STAGE2-K-SUPPLEMENT-SPECIFIC",
            "condition": "patient.labs.get('potassium', 4.0) > 5.0",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_potassium_supplement_in_hyperkalemic_aki_stage2",
                    "give_oral_potassium_in_aki_with_elevated_k",
                ],
            },
            "evidence": "KDIGO AKI 2012 Section 3.2; potassium supplementation with K+ > 5.0 in AKI is dangerous",
            "severity": "CRITICAL",
            "description": "Potassium supplementation when K+ > 5.0 in AKI Stage 2 risks fatal cardiac arrhythmia.",
            "condition_variables": ["patient.labs.potassium"],
            "trigger_range": {"patient.labs.potassium": {"min": 5.1, "max": 9.0, "type": "float"}},
            "normal_range": {"patient.labs.potassium": {"min": 3.5, "max": 5.0, "type": "float"}},
        },
        {
            "rule_id": "AKI-HYPERKALEMIA-NO-SUCCINYLCHOLINE-SPECIFIC",
            "condition": "patient.labs.get('potassium', 4.0) > 5.5",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_succinylcholine_for_rsi_in_hyperkalemic_aki",
                    "use_depolarizing_agent_in_aki_hyperkalemia",
                ],
            },
            "evidence": "KDIGO AKI 2012; ASA Guidelines; succinylcholine releases 0.5-1.0 "
            "mEq/L K+ from muscle in hyperkalemia",
            "severity": "CRITICAL",
            "description": "Succinylcholine releases potassium from muscle; in hyperkalemic "
            "AKI this causes fatal arrhythmia. Use rocuronium instead.",
            "condition_variables": ["patient.labs.potassium"],
            "trigger_range": {"patient.labs.potassium": {"min": 5.6, "max": 9.0, "type": "float"}},
            "normal_range": {"patient.labs.potassium": {"min": 3.5, "max": 5.5, "type": "float"}},
        },
    ],
    "kdigo_contrast_aki": [
        {
            "rule_id": "CAKI-GADOLINIUM-GFR30-SPECIFIC",
            "condition": "patient.labs.get('egfr', 90) < 30",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_gadolinium_in_severe_ckd_for_mri",
                    "order_mri_gadolinium_without_nephrology_approval_in_ckd",
                ],
            },
            "evidence": "KDIGO Contrast AKI 2012; ACR 2023; gadolinium in eGFR < 30 "
            "causes nephrogenic systemic fibrosis (NSF)",
            "severity": "CRITICAL",
            "description": "Gadolinium contrast in severe CKD (eGFR < 30) causes "
            "nephrogenic systemic fibrosis, a debilitating fibrotic condition.",
            "condition_variables": ["patient.labs.egfr"],
            "trigger_range": {"patient.labs.egfr": {"min": 5, "max": 29, "type": "float"}},
            "normal_range": {"patient.labs.egfr": {"min": 60, "max": 120, "type": "float"}},
        },
        {
            "rule_id": "CAKI-CKD-PREP-SPECIFIC",
            "condition": "patient.labs.get('egfr', 90) < 45 and ('ckd' in patient.comorbidities or 'diabetes' in patient.comorbidities)",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_contrast_without_isotonic_prehydration_in_ckd",
                    "use_high_volume_contrast_in_ckd_diabetes",
                ],
            },
            "evidence": "KDIGO Contrast AKI 2012; CKD + diabetes doubles contrast "
            "nephropathy risk; mandatory low-volume iso-osmolar + prehydration",
            "severity": "HIGH",
            "description": "CKD with diabetes doubles contrast nephropathy risk; "
            "isotonic prehydration and low-volume contrast are mandatory.",
            "condition_variables": ["patient.labs.egfr", "patient.comorbidities"],
            "trigger_range": {"patient.labs.egfr": {"min": 5, "max": 44, "type": "float"}},
            "normal_range": {"patient.labs.egfr": {"min": 60, "max": 120, "type": "float"}},
        },
    ],
    "toxicology_management": [
        {
            "rule_id": "TOX-NO-FORCED-DIURESIS-SPECIFIC",
            "condition": "'poisoning' in patient.comorbidities or 'overdose' in patient.comorbidities",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "give_forced_diuresis_in_poisoning",
                    "give_mannitol_for_toxin_clearance",
                ],
            },
            "evidence": "AACT/ACMT 2024 Section 5; forced diuresis is ineffective and "
            "causes pulmonary edema and electrolyte derangement",
            "severity": "HIGH",
            "description": "Forced diuresis for toxin clearance is ineffective and causes "
            "dangerous fluid overload and electrolyte imbalances.",
            "condition_variables": ["patient.comorbidities"],
            "trigger_range": {
                "patient.comorbidities": {
                    "contains": "poisoning",
                    "type": "list_contains",
                }
            },
            "normal_range": {
                "patient.comorbidities": {
                    "not_contains": "poisoning",
                    "type": "list_not_contains",
                }
            },
        },
    ],
    "aha_heart_failure_2022": [
        {
            "rule_id": "HF-OVERDIURESIS-HYPOVOLEMIA-SPECIFIC",
            "condition": "patient.labs.get('creatinine', 1.0) > 2.0 or patient.vitals.get('sbp', 120) < 90",
            "effect": {
                "type": "FORBIDDEN",
                "actions": [
                    "escalate_diuresis_in_cardiorenal_syndrome",
                    "give_aggressive_diuresis_in_hypotensive_hf",
                ],
            },
            "evidence": "AHA HF 2022; over-diuresis in cardiorenal syndrome worsens "
            "renal function and causes hemodynamic collapse",
            "severity": "HIGH",
            "description": "Aggressive diuresis in HF with rising creatinine or hypotension "
            "causes cardiorenal syndrome progression and hemodynamic collapse.",
            "condition_variables": ["patient.labs.creatinine", "patient.vitals.sbp"],
            "trigger_range": {"patient.labs.creatinine": {"min": 2.1, "max": 15.0, "type": "float"}},
            "normal_range": {"patient.labs.creatinine": {"min": 0.5, "max": 2.0, "type": "float"}},
        },
    ],
}


def add_rules_to_graph(graph_path: Path, new_rules: list[dict], target_node_idx: int = 0) -> tuple[int, list[str]]:
    """Add new conditional rules to a specific node in the graph."""
    with open(graph_path, encoding="utf-8") as f:
        graph = yaml.safe_load(f)

    nodes = graph.get("nodes", {})
    node_keys = list(nodes.keys())
    if not node_keys:
        return 0, []

    # Find the best node to attach rules to (first node with existing conditional_rules)
    target_key = node_keys[0]
    for nk in node_keys:
        if nodes[nk].get("conditional_rules"):
            target_key = nk
            break

    cond_rules = nodes[target_key].get("conditional_rules", [])

    added: list[str] = []
    existing_ids = {r.get("rule_id", "") for r in cond_rules}

    for rule in new_rules:
        if rule["rule_id"] in existing_ids:
            continue
        cond_rules.append(rule)
        added.append(rule["rule_id"])
        existing_ids.add(rule["rule_id"])

    nodes[target_key]["conditional_rules"] = cond_rules

    if added:
        with open(graph_path, "w", encoding="utf-8") as f:
            yaml.dump(
                graph,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )

    return len(added), added


def apply_missing_root_a(graph_path: Path) -> tuple[int, list[str]]:
    """Add missing Root Cause A companion FORBIDDEN rules."""
    with open(graph_path, encoding="utf-8") as f:
        graph = yaml.safe_load(f)

    added_rules: list[str] = []
    nodes = graph.get("nodes", {})

    for _node_id, node in nodes.items():
        cond_rules = node.get("conditional_rules", [])
        if not cond_rules:
            continue

        new_rules: list[dict] = []
        for rule in cond_rules:
            new_rules.append(rule)
            rid = rule.get("rule_id", "")

            if rid not in MISSING_ROOT_A_COMPANIONS:
                continue
            eff_type = rule.get("effect", {}).get("type", "")
            if eff_type == "FORBIDDEN":
                continue

            companion = MISSING_ROOT_A_COMPANIONS[rid]
            new_rule = {
                "rule_id": companion["rule_id"],
                "condition": rule["condition"],
                "effect": copy.deepcopy(companion["effect"]),
                "evidence": companion["evidence"],
                "severity": companion["severity"],
                "description": companion["description"],
            }
            for field in ("condition_variables", "trigger_range", "normal_range"):
                if field in rule:
                    new_rule[field] = copy.deepcopy(rule[field])
            new_rules.append(new_rule)
            added_rules.append(companion["rule_id"])

        node["conditional_rules"] = new_rules

    # Handle DKA-HYPOK-INSULIN-GATE additional unique forbidden
    for _node_id, node in nodes.items():
        cond_rules = node.get("conditional_rules", [])
        existing_ids = {r.get("rule_id", "") for r in cond_rules}
        for rule in cond_rules:
            if rule.get("rule_id") == "DKA-HYPOK-INSULIN-GATE":
                if DKA_HYPOK_ADDITIONAL["rule_id"] not in existing_ids:
                    new_rule = {
                        "rule_id": DKA_HYPOK_ADDITIONAL["rule_id"],
                        "condition": rule["condition"],
                        "effect": copy.deepcopy(DKA_HYPOK_ADDITIONAL["effect"]),
                        "evidence": DKA_HYPOK_ADDITIONAL["evidence"],
                        "severity": DKA_HYPOK_ADDITIONAL["severity"],
                        "description": DKA_HYPOK_ADDITIONAL["description"],
                    }
                    for field in ("condition_variables", "trigger_range", "normal_range"):
                        if field in rule:
                            new_rule[field] = copy.deepcopy(rule[field])
                    cond_rules.append(new_rule)
                    added_rules.append(DKA_HYPOK_ADDITIONAL["rule_id"])

    if added_rules:
        with open(graph_path, "w", encoding="utf-8") as f:
            yaml.dump(
                graph,
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
                width=120,
            )

    return len(added_rules), added_rules


def main() -> None:
    """Fix all remaining undifferentiated traps."""
    print("=" * 60)
    print("Fix Remaining Undifferentiated Traps")
    print("=" * 60)

    total_added = 0

    # 1. Missing Root Cause A companions (ACLS + DKA)
    print("\n--- Pass 1: Missing Root Cause A companions ---")
    for graph_file in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(graph_file, encoding="utf-8") as f:
            g = yaml.safe_load(f)
        gid = g.get("graph_id", graph_file.stem)
        if gid not in ("acls_cardiac_arrest", "ada_dka_management"):
            continue
        count, rules = apply_missing_root_a(graph_file)
        total_added += count
        if count > 0:
            print(f"  {gid}: added {count} rules")
            for r in rules:
                print(f"    + {r}")

    # 2. Root Cause B: add additional unique forbidden rules
    print("\n--- Pass 2: Root Cause B additional forbidden ---")
    for gid, rules in ROOT_B_ADDITIONAL_FORBIDDEN.items():
        graph_file = GRAPHS_DIR / f"{gid}.yaml"
        if not graph_file.exists():
            print(f"  {gid}: graph file not found, skipping")
            continue
        count, added = add_rules_to_graph(graph_file, rules)
        total_added += count
        if count > 0:
            print(f"  {gid}: added {count} rules")
            for r in added:
                print(f"    + {r}")

    print(f"\n{'=' * 60}")
    print(f"Total additional rules added: {total_added}")


if __name__ == "__main__":
    main()
