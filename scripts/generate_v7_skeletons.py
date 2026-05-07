"""Generate v7 expansion skeleton parsed.json files for the 54 6-point candidates.

Reads the candidate registry and produces structurally valid extended
parsed.json skeletons for each candidate.  These are batch-ready for
``auto_generate_cpg.py --batch-dir`` and can be enriched later when
actual guideline texts become available.

Usage:
    PYTHONPATH=.. python scripts/generate_v7_skeletons.py
    PYTHONPATH=.. python scripts/generate_v7_skeletons.py --output-dir /tmp/v7_skeletons --dry-run
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

logger = logging.getLogger("generate_v7_skeletons")

BASE_DIR = Path(__file__).resolve().parent.parent
DEFAULT_OUTPUT_DIR = BASE_DIR / "cpg_model" / "graphs_v7_skeletons"

# ---------------------------------------------------------------------------
# 54 six-point candidates from 02_candidate_rescoring_99.md
# Each entry: (graph_id, guideline_name, source, domain, year)
# ---------------------------------------------------------------------------

CANDIDATES_6PT: list[dict[str, str]] = [
    # --- 1. Trauma (6) ---
    {
        "graph_id": "atls_primary_survey",
        "name": "ATLS Primary Survey",
        "source": "ACS 2018 10th ed",
        "domain": "trauma",
        "nodes_hint": "primary_survey,secondary_survey,resuscitation,disposition",
    },
    {
        "graph_id": "btf_severe_tbi",
        "name": "BTF Severe TBI Management",
        "source": "BTF 2016/2020 4th ed",
        "domain": "trauma",
        "nodes_hint": "initial_assessment,icp_management,surgical_decision,monitoring",
    },
    {
        "graph_id": "wses_pelvic_reboa",
        "name": "WSES Pelvic Trauma and REBOA",
        "source": "WSES 2017",
        "domain": "trauma",
        "nodes_hint": "hemodynamic_assessment,pelvic_stabilization,reboa_decision,surgical_control",
    },
    {
        "graph_id": "east_mtp",
        "name": "EAST Damage Control / Massive Transfusion Protocol",
        "source": "EAST 2019",
        "domain": "trauma",
        "nodes_hint": "hemorrhage_recognition,mtp_activation,damage_control_surgery,reassessment",
    },
    {
        "graph_id": "wses_penetrating_abdominal",
        "name": "WSES Penetrating Abdominal Trauma",
        "source": "WSES 2017",
        "domain": "trauma",
        "nodes_hint": "initial_assessment,hemodynamic_evaluation,operative_decision,non_operative_management",
    },
    {
        "graph_id": "bts_tension_ptx",
        "name": "BTS Pleural Disease / Tension Pneumothorax",
        "source": "BTS 2023",
        "domain": "trauma",
        "nodes_hint": "recognition,needle_decompression,chest_drain,post_procedure",
    },
    # --- 2. CV (7) ---
    {
        "graph_id": "aha_aortic_dissection",
        "name": "AHA/ACC Aortic Dissection",
        "source": "AHA/ACC 2022",
        "domain": "cardiovascular",
        "nodes_hint": "recognition,type_classification,medical_management,surgical_decision",
    },
    {
        "graph_id": "aha_cardiogenic_shock",
        "name": "AHA Cardiogenic Shock + SCAI",
        "source": "AHA/SCAI 2022",
        "domain": "cardiovascular",
        "nodes_hint": "shock_recognition,hemodynamic_support,mcs_decision,monitoring",
    },
    {
        "graph_id": "aha_ttm_post_arrest",
        "name": "AHA Post-Cardiac Arrest / TTM",
        "source": "AHA 2023",
        "domain": "cardiovascular",
        "nodes_hint": "rosc_management,ttm_initiation,hemodynamic_optimization,neuroprognostication",
    },
    {
        "graph_id": "hrs_vt_storm",
        "name": "HRS VT / Electrical Storm",
        "source": "HRS 2022",
        "domain": "cardiovascular",
        "nodes_hint": "vt_recognition,acute_termination,antiarrhythmic_therapy,catheter_ablation_decision",
    },
    {
        "graph_id": "esc_cardiac_tamponade",
        "name": "ESC Cardiac Tamponade",
        "source": "ESC 2015",
        "domain": "cardiovascular",
        "nodes_hint": "recognition,hemodynamic_assessment,pericardiocentesis,post_procedure",
    },
    {
        "graph_id": "esvs_acute_limb_ischemia",
        "name": "ESVS Acute Limb Ischemia",
        "source": "ESVS 2020",
        "domain": "cardiovascular",
        "nodes_hint": "clinical_assessment,anticoagulation,revascularization_decision,post_revascularization",
    },
    {
        "graph_id": "esvs_ruptured_aaa",
        "name": "ESVS/SVS Ruptured AAA",
        "source": "ESVS/SVS 2019/2024",
        "domain": "cardiovascular",
        "nodes_hint": "recognition,hemodynamic_resuscitation,surgical_decision,post_operative",
    },
    # --- 3. Pulm (4) ---
    {
        "graph_id": "ats_ards",
        "name": "ATS/ESICM/SCCM ARDS Management",
        "source": "ATS/ESICM/SCCM 2023",
        "domain": "pulmonary",
        "nodes_hint": "ards_recognition,lung_protective_ventilation,prone_positioning,rescue_therapies",
    },
    {
        "graph_id": "ers_niv_arf",
        "name": "ERS/ATS NIV Acute Respiratory Failure",
        "source": "ERS/ATS 2017",
        "domain": "pulmonary",
        "nodes_hint": "arf_assessment,niv_initiation,monitoring,escalation_decision",
    },
    {
        "graph_id": "das_difficult_airway",
        "name": "DAS Difficult Airway / RSI",
        "source": "DAS 2015",
        "domain": "pulmonary",
        "nodes_hint": "airway_assessment,plan_a_intubation,plan_b_supraglottic,plan_c_cricothyroidotomy",
    },
    {
        "graph_id": "bts_spontaneous_ptx",
        "name": "BTS Spontaneous Pneumothorax",
        "source": "BTS 2023",
        "domain": "pulmonary",
        "nodes_hint": "size_assessment,aspiration_decision,chest_drain,discharge_criteria",
    },
    # --- 4. Neuro (3) ---
    {
        "graph_id": "ncs_aneurysmal_sah",
        "name": "NCS/AHA Aneurysmal SAH",
        "source": "NCS/AHA 2023",
        "domain": "stroke",
        "nodes_hint": "initial_stabilization,aneurysm_securing,vasospasm_prevention,monitoring",
    },
    {
        "graph_id": "aha_spontaneous_ich",
        "name": "AHA/ASA Spontaneous ICH",
        "source": "AHA/ASA 2022",
        "domain": "stroke",
        "nodes_hint": "initial_assessment,blood_pressure_management,reversal_anticoagulation,surgical_decision",
    },
    {
        "graph_id": "asam_alcohol_withdrawal",
        "name": "ASAM Alcohol Withdrawal / CIWA",
        "source": "ASAM 2020",
        "domain": "neurological",
        "nodes_hint": "severity_assessment,benzodiazepine_protocol,monitoring,complication_management",
    },
    # --- 5. Endo/Metabolic (4) ---
    {
        "graph_id": "ada_hhs",
        "name": "ADA Hyperglycemic Hyperosmolar State",
        "source": "ADA 2024",
        "domain": "dka",
        "nodes_hint": "initial_assessment,fluid_resuscitation,insulin_therapy,electrolyte_correction",
    },
    {
        "graph_id": "ata_thyroid_storm",
        "name": "ATA Thyroid Storm",
        "source": "ATA 2016",
        "domain": "endocrine",
        "nodes_hint": "recognition,beta_blockade,antithyroid_therapy,supportive_care",
    },
    {
        "graph_id": "ukka_hyperkalemia",
        "name": "UKKA Severe Hyperkalemia",
        "source": "UKKA 2023",
        "domain": "renal",
        "nodes_hint": "ecg_assessment,cardiac_protection,potassium_shifting,potassium_removal",
    },
    {
        "graph_id": "ese_hyponatremia",
        "name": "ESE/ESICM Severe Hyponatremia",
        "source": "ESE/ESICM 2014",
        "domain": "renal",
        "nodes_hint": "severity_assessment,hypertonic_saline,monitoring,overcorrection_prevention",
    },
    # --- 6. Hepatic/GI (6) ---
    {
        "graph_id": "aasld_acute_liver_failure",
        "name": "AASLD Acute Liver Failure",
        "source": "AASLD 2023",
        "domain": "hepatic",
        "nodes_hint": "initial_assessment,etiology_workup,nac_protocol,transplant_evaluation",
    },
    {
        "graph_id": "baveno_variceal_hemorrhage",
        "name": "Baveno VII Variceal Hemorrhage",
        "source": "Baveno VII 2022",
        "domain": "gi_bleeding",
        "nodes_hint": "resuscitation,vasoactive_drugs,endoscopy,secondary_prophylaxis",
    },
    {
        "graph_id": "acg_acute_pancreatitis",
        "name": "ACG/AGA Acute Pancreatitis",
        "source": "ACG/AGA 2013/2024",
        "domain": "gi_bleeding",
        "nodes_hint": "initial_assessment,fluid_resuscitation,pain_management,severity_stratification",
    },
    {
        "graph_id": "tokyo_cholangitis",
        "name": "Tokyo Guidelines Acute Cholangitis",
        "source": "Tokyo 2018",
        "domain": "hepatic",
        "nodes_hint": "severity_grading,initial_treatment,biliary_drainage_decision,antibiotic_therapy",
    },
    {
        "graph_id": "wses_mesenteric_ischemia",
        "name": "WSES Acute Mesenteric Ischemia",
        "source": "WSES 2017",
        "domain": "gi_bleeding",
        "nodes_hint": "recognition,ct_angiography,anticoagulation,surgical_decision",
    },
    {
        "graph_id": "idsa_fulminant_cdiff",
        "name": "IDSA Fulminant C.difficile",
        "source": "IDSA 2021",
        "domain": "infectious",
        "nodes_hint": "severity_assessment,antibiotic_therapy,surgical_consultation,monitoring",
    },
    # --- 7. Renal/GU (2) ---
    {
        "graph_id": "isth_ttp",
        "name": "ISTH/ASH Thrombotic Thrombocytopenic Purpura",
        "source": "ISTH/ASH 2020",
        "domain": "hematologic",
        "nodes_hint": "recognition,plasma_exchange,caplacizumab,monitoring",
    },
    {
        "graph_id": "eau_obstructive_pyelo",
        "name": "EAU Obstructive Pyelonephritis",
        "source": "EAU Guidelines",
        "domain": "renal",
        "nodes_hint": "initial_assessment,antibiotic_therapy,decompression_decision,follow_up",
    },
    # --- 8. OB (2) ---
    {
        "graph_id": "acog_preeclampsia_hellp",
        "name": "ACOG Preeclampsia / HELLP Syndrome",
        "source": "ACOG PB 222 2020",
        "domain": "obstetric",
        "nodes_hint": "severity_assessment,magnesium_sulfate,blood_pressure_control,delivery_decision",
    },
    {
        "graph_id": "smfm_maternal_sepsis",
        "name": "SMFM/RCOG Maternal Sepsis",
        "source": "SMFM/RCOG 2019",
        "domain": "obstetric",
        "nodes_hint": "sepsis_recognition,bundle_initiation,source_control,fetal_monitoring",
    },
    # --- 9. Peds (5) ---
    {
        "graph_id": "ispad_pediatric_dka",
        "name": "ISPAD Pediatric DKA",
        "source": "ISPAD 2022",
        "domain": "dka",
        "nodes_hint": "severity_assessment,fluid_resuscitation,insulin_infusion,cerebral_edema_watch",
    },
    {
        "graph_id": "nrp_neonatal_resuscitation",
        "name": "NRP/AAP Neonatal Resuscitation",
        "source": "NRP/AAP 2020",
        "domain": "pediatric",
        "nodes_hint": "initial_steps,positive_pressure_ventilation,chest_compressions,epinephrine",
    },
    {
        "graph_id": "sccm_pediatric_septic_shock",
        "name": "SCCM Pediatric Septic Shock",
        "source": "SCCM 2020",
        "domain": "sepsis",
        "nodes_hint": "recognition,fluid_resuscitation,vasoactive_therapy,refractory_shock",
    },
    {
        "graph_id": "gina_pediatric_status_asthma",
        "name": "GINA Pediatric Status Asthmaticus",
        "source": "GINA 2024",
        "domain": "asthma",
        "nodes_hint": "severity_assessment,bronchodilator_therapy,systemic_corticosteroids,escalation",
    },
    {
        "graph_id": "pals_pediatric_traumatic_arrest",
        "name": "PALS/ATLS Pediatric Traumatic Arrest",
        "source": "PALS/ATLS 2020",
        "domain": "pediatric",
        "nodes_hint": "primary_survey,resuscitation,reversible_causes,surgical_decision",
    },
    # --- 10. Infectious (4) ---
    {
        "graph_id": "idsa_nsti",
        "name": "IDSA/EAST Necrotizing Soft Tissue Infection",
        "source": "IDSA/EAST 2014",
        "domain": "infectious",
        "nodes_hint": "recognition,empiric_antibiotics,surgical_debridement,monitoring",
    },
    {
        "graph_id": "idsa_tss",
        "name": "IDSA Toxic Shock Syndrome",
        "source": "IDSA 2014",
        "domain": "infectious",
        "nodes_hint": "recognition,aggressive_resuscitation,antibiotic_therapy,source_control",
    },
    {
        "graph_id": "idsa_febrile_neutropenia",
        "name": "IDSA/ASCO Febrile Neutropenia",
        "source": "IDSA/ASCO 2018",
        "domain": "infectious",
        "nodes_hint": "risk_stratification,empiric_antibiotics,monitoring,escalation",
    },
    {
        "graph_id": "who_severe_malaria",
        "name": "WHO/CDC Severe Malaria",
        "source": "WHO/CDC 2023",
        "domain": "infectious",
        "nodes_hint": "diagnosis,artesunate_iv,supportive_care,monitoring",
    },
    # --- 11. Toxicology (3) ---
    {
        "graph_id": "aasld_salicylate_toxicity",
        "name": "AASLD/AACT Salicylate Toxicity",
        "source": "AASLD/AACT 2015",
        "domain": "toxicology",
        "nodes_hint": "initial_assessment,decontamination,alkalinization,hemodialysis_decision",
    },
    {
        "graph_id": "uhms_carbon_monoxide",
        "name": "UHMS Carbon Monoxide / HBO",
        "source": "UHMS 2017",
        "domain": "toxicology",
        "nodes_hint": "recognition,high_flow_oxygen,hbo_decision,monitoring",
    },
    {
        "graph_id": "extrip_lithium_toxicity",
        "name": "EXTRIP Lithium Toxicity",
        "source": "EXTRIP 2015",
        "domain": "toxicology",
        "nodes_hint": "severity_assessment,volume_resuscitation,hemodialysis_decision,monitoring",
    },
    # --- 12. Environmental (4) ---
    {
        "graph_id": "wms_heat_stroke",
        "name": "WMS Heat Stroke",
        "source": "WMS 2024",
        "domain": "environmental",
        "nodes_hint": "recognition,rapid_cooling,fluid_resuscitation,monitoring",
    },
    {
        "graph_id": "erc_hypothermia",
        "name": "ERC Accidental Hypothermia",
        "source": "ERC 2021",
        "domain": "environmental",
        "nodes_hint": "core_temp_assessment,rewarming_strategy,cardiac_monitoring,ecmo_decision",
    },
    {
        "graph_id": "erc_drowning",
        "name": "ERC Drowning Resuscitation",
        "source": "ERC 2021",
        "domain": "environmental",
        "nodes_hint": "rescue_ventilation,cpr_decision,rewarming,post_resuscitation",
    },
    {
        "graph_id": "wms_hace_hape",
        "name": "WMS HACE / HAPE",
        "source": "WMS 2024",
        "domain": "environmental",
        "nodes_hint": "recognition,descent_decision,pharmacotherapy,oxygen_therapy",
    },
    # --- 13. Ophthal (1) ---
    {
        "graph_id": "aao_acute_angle_closure",
        "name": "AAO Acute Angle-Closure Glaucoma",
        "source": "AAO 2020",
        "domain": "ophthalmologic",
        "nodes_hint": "recognition,iop_lowering,definitive_treatment,monitoring",
    },
    # --- 14. Heme/Onc (2) ---
    {
        "graph_id": "asco_tumor_lysis",
        "name": "ASCO Tumor Lysis Syndrome",
        "source": "ASCO 2008/2022",
        "domain": "hematologic",
        "nodes_hint": "risk_stratification,prophylaxis,rasburicase_decision,monitoring",
    },
    {
        "graph_id": "ash_sickle_cell_acs",
        "name": "ASH Sickle Cell Acute Chest Syndrome",
        "source": "ASH 2020",
        "domain": "hematologic",
        "nodes_hint": "recognition,transfusion_decision,antibiotic_therapy,supportive_care",
    },
    # --- 15. Other (1) ---
    {
        "graph_id": "asa_procedural_sedation",
        "name": "ASA Procedural Sedation",
        "source": "ASA 2018",
        "domain": "procedural",
        "nodes_hint": "pre_assessment,medication_selection,monitoring,recovery",
    },
]

if len(CANDIDATES_6PT) != 54:
    raise ValueError(f"Expected 54 candidates, got {len(CANDIDATES_6PT)}")


# ---------------------------------------------------------------------------
# Skeleton generator
# ---------------------------------------------------------------------------

# Domain-specific action templates for realistic skeletons
DOMAIN_ACTION_TEMPLATES: dict[str, dict[str, list[str]]] = {
    "default": {
        "assessment": ["assess_vital_signs", "obtain_focused_history", "perform_physical_exam"],
        "diagnostics": ["order_lab_cbc", "order_lab_bmp", "order_lab_coagulation"],
        "treatment": ["establish_iv_access", "initiate_fluid_resuscitation"],
        "monitoring": ["continuous_cardiac_monitoring", "reassess_vital_signs"],
    },
    "trauma": {
        "assessment": ["primary_survey_abcde", "assess_hemorrhage_class", "assess_gcs"],
        "diagnostics": ["order_lab_type_and_screen", "order_imaging_fast", "order_lab_blood_gas"],
        "treatment": ["establish_large_bore_iv", "initiate_massive_transfusion_protocol", "apply_pelvic_binder"],
        "monitoring": ["serial_vital_signs", "reassess_hemorrhage", "monitor_urine_output"],
    },
    "cardiovascular": {
        "assessment": ["obtain_12_lead_ecg", "assess_hemodynamic_status", "calculate_shock_index"],
        "diagnostics": ["order_lab_troponin", "order_lab_bnp", "order_imaging_echocardiogram"],
        "treatment": ["establish_iv_access", "initiate_vasopressor", "consider_mechanical_support"],
        "monitoring": ["continuous_telemetry", "arterial_line_monitoring", "serial_ecg"],
    },
    "pulmonary": {
        "assessment": ["assess_respiratory_status", "calculate_pf_ratio", "assess_work_of_breathing"],
        "diagnostics": ["order_lab_blood_gas", "order_imaging_chest_xray", "order_imaging_ct_chest"],
        "treatment": ["initiate_oxygen_therapy", "initiate_niv", "prepare_for_intubation"],
        "monitoring": ["continuous_spo2", "serial_blood_gas", "ventilator_monitoring"],
    },
    "infectious": {
        "assessment": ["assess_infection_source", "calculate_sofa_score", "assess_organ_dysfunction"],
        "diagnostics": ["order_lab_blood_culture", "order_lab_lactate", "order_lab_procalcitonin"],
        "treatment": ["give_broad_spectrum_antibiotics", "initiate_fluid_resuscitation", "source_control"],
        "monitoring": ["serial_lactate", "reassess_hemodynamics", "monitor_organ_function"],
    },
}


def _get_actions_for_domain(domain: str, category: str) -> list[str]:
    """Return action list for domain+category, falling back to default."""
    templates = DOMAIN_ACTION_TEMPLATES.get(domain, DOMAIN_ACTION_TEMPLATES["default"])
    return templates.get(category, DOMAIN_ACTION_TEMPLATES["default"].get(category, []))


def generate_skeleton(candidate: dict[str, str]) -> dict:
    """Generate a structurally valid extended parsed.json skeleton."""
    graph_id = candidate["graph_id"]
    domain = candidate["domain"]
    node_hints = candidate["nodes_hint"].split(",")

    nodes: dict[str, dict] = {}
    node_ids = [nh.strip() for nh in node_hints]

    for i, nid in enumerate(node_ids):
        is_first = i == 0
        is_last = i == len(node_ids) - 1

        # Choose action category based on position
        if is_first:
            category = "assessment"
        elif i == 1:
            category = "diagnostics"
        elif is_last:
            category = "monitoring"
        else:
            category = "treatment"

        actions = _get_actions_for_domain(domain, category)
        mandatory = actions[:2] if actions else [f"placeholder_{nid}_action_1"]
        allowed = [*actions, f"additional_{nid}_action"]

        # Deadlines: tighter for first nodes, relaxed for later
        deadline_min = 30 if is_first else 60
        deadlines = dict.fromkeys(mandatory, deadline_min)

        node = {
            "node_id": nid,
            "node_type": "decision" if is_first else "action",
            "name": nid.replace("_", " ").title(),
            "mandatory_actions": mandatory,
            "allowed_actions": allowed,
            "forbidden_actions": [],
            "deadlines": deadlines,
            "next_nodes": [node_ids[i + 1]] if not is_last else [],
            "source_guideline": candidate["source"],
            "source_section": f"Section {i + 1}",
            "description": f"[SKELETON] {nid.replace('_', ' ').title()} — requires clinical content enrichment",
        }
        nodes[nid] = node

    skeleton = {
        "graph_id": graph_id,
        "guideline_name": candidate["name"],
        "source_guideline": candidate["source"],
        "version": "0.1-skeleton",
        "domain": domain,
        "entry_node": node_ids[0],
        "nodes": nodes,
        "metadata": {
            "status": "skeleton",
            "requires_enrichment": True,
            "candidate_score": "6/6",
            "notes": "Auto-generated skeleton for v7 expansion. Requires LLM extraction or manual clinical content.",
        },
    }
    return skeleton


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def build_argparser() -> argparse.ArgumentParser:
    """Build CLI argument parser."""
    p = argparse.ArgumentParser(
        description="Generate v7 expansion skeleton parsed.json files.",
    )
    p.add_argument("--output-dir", type=Path, default=None, help=f"Output directory (default: {DEFAULT_OUTPUT_DIR})")
    p.add_argument("--dry-run", action="store_true", help="Print summary, do not write files")
    p.add_argument(
        "--manifest-only", action="store_true", help="Only write the manifest JSON, skip individual skeletons"
    )
    p.add_argument("--verbose", "-v", action="store_true")
    return p


def main(argv: list[str] | None = None) -> int:
    """Generate skeleton files for all 54 six-point candidates."""
    args = build_argparser().parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(name)s %(levelname)s %(message)s",
    )

    output_dir = args.output_dir or DEFAULT_OUTPUT_DIR

    logger.info("Generating skeletons for %d candidates", len(CANDIDATES_6PT))

    # Generate manifest
    manifest = {
        "version": "v7-skeleton-v1",
        "total_candidates": len(CANDIDATES_6PT),
        "candidates": [],
    }

    total_nodes = 0
    total_mandatory = 0

    for candidate in CANDIDATES_6PT:
        skeleton = generate_skeleton(candidate)
        n_nodes = len(skeleton["nodes"])
        n_mandatory = sum(len(n["mandatory_actions"]) for n in skeleton["nodes"].values())
        total_nodes += n_nodes
        total_mandatory += n_mandatory

        manifest["candidates"].append(
            {
                "graph_id": candidate["graph_id"],
                "name": candidate["name"],
                "source": candidate["source"],
                "domain": candidate["domain"],
                "nodes": n_nodes,
                "mandatory_actions": n_mandatory,
            }
        )

        if not args.dry_run and not args.manifest_only:
            output_dir.mkdir(parents=True, exist_ok=True)
            out_path = output_dir / f"{candidate['graph_id']}.parsed.json"
            out_path.write_text(
                json.dumps(skeleton, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )

    if args.dry_run:
        logger.info("DRY RUN — no files written")
    else:
        output_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = output_dir / "manifest.json"
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        logger.info("Manifest: %s", manifest_path)

    logger.info(
        "Summary: %d candidates, %d total nodes, %d total mandatory actions",
        len(CANDIDATES_6PT),
        total_nodes,
        total_mandatory,
    )

    # Domain breakdown
    domain_counts: dict[str, int] = {}
    for c in CANDIDATES_6PT:
        domain_counts[c["domain"]] = domain_counts.get(c["domain"], 0) + 1
    for domain, count in sorted(domain_counts.items(), key=lambda x: -x[1]):
        logger.info("  %-20s %d graphs", domain, count)

    return 0


if __name__ == "__main__":
    import sys

    sys.exit(main())
