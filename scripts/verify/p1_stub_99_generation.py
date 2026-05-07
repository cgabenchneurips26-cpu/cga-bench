"""P1 — Scale robustness: generate 99 stub CPG YAMLs via the rule-based loader
and verify every one passes validator + patient_generator.

Each stub is a minimal but structurally-complete CPG graph: 2 nodes, each with
mandatory action, source provenance, valid transitions. The stubs are NOT
clinically meaningful — their only purpose is to prove the rule-based loader +
downstream tooling survive at 99-scale without crashing or producing
validator-failing YAML.

Usage:
    PYTHONPATH=. python scripts/verify/p1_stub_99_generation.py

Exit code 0 iff 99/99 YAMLs validator-pass AND patient_generator runs on all.
"""

from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
from typing import Any

# Import path shim (PYTHONPATH must be parent of cga_bench/)
# __file__ = .../cga_bench/scripts/verify/p1_stub_99_generation.py
# parents[0]=verify/, parents[1]=scripts/, parents[2]=cga_bench/, parents[3]=AnonProject/
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from cga_bench.cpg_model.constraint_derivation import ConstraintDerivationEngine, load_graph
from cga_bench.cpg_model.patient_generator import PatientGenerator
from cga_bench.semantic_layer.parsed_json_loader import load_and_normalize, write_yaml

# 99 candidates copied verbatim from docs/cpg_expansion_v7/02_candidate_rescoring_99.md
# Format: (graph_id, guideline_name, source)
CANDIDATES: list[tuple[str, str, str]] = [
    # Trauma (10)
    ("atls_primary_survey", "ATLS Primary Survey", "ACS 2018"),
    ("btf_severe_tbi", "BTF Severe TBI", "BTF 2016/2020"),
    ("aospine_acute_sci", "AOSpine Acute SCI", "AOSpine 2017"),
    ("wses_pelvic_trauma", "WSES Pelvic Trauma REBOA", "WSES 2017"),
    ("east_cervical_spine", "EAST Cervical Spine", "EAST 2009/2023"),
    ("east_blunt_cardiac", "EAST Blunt Cardiac Injury", "EAST 2012"),
    ("east_damage_control_mtp", "EAST Damage Control MTP", "EAST 2019"),
    ("wses_penetrating_abdominal", "WSES Penetrating Abdominal", "WSES 2017"),
    ("bts_tension_pneumothorax", "BTS Pleural Disease", "BTS 2023"),
    ("east_open_fracture", "EAST Open Fracture", "EAST 2012"),
    # CV (10)
    ("aha_acc_aortic_dissection", "AHA/ACC Aortic Dissection", "AHA/ACC 2022"),
    ("aha_cardiogenic_shock", "AHA Cardiogenic Shock", "AHA 2022"),
    ("aha_ttm_post_arrest", "AHA Post-Cardiac Arrest TTM", "AHA 2023"),
    ("hrs_vt_storm", "HRS VT Electrical Storm", "HRS 2022"),
    ("esc_cardiac_tamponade", "ESC Cardiac Tamponade", "ESC 2015"),
    ("esvs_acute_limb_ischemia", "ESVS Acute Limb Ischemia", "ESVS 2020"),
    ("esvs_ruptured_aaa", "ESVS Ruptured AAA", "ESVS 2019/2024"),
    ("acls_bradycardia", "ACLS Bradycardia", "AHA 2020"),
    ("aha_peripartum_cmo", "AHA Peripartum Cardiomyopathy", "AHA 2020"),
    ("hrs_long_qt_brugada", "HRS LQT/Brugada Acute", "HRS 2017"),
    # Pulm (7)
    ("ats_esicm_ards_2023", "ATS/ESICM ARDS", "ATS/ESICM/SCCM 2023"),
    ("ers_ats_niv_arf", "ERS/ATS NIV Acute Respiratory Failure", "ERS/ATS 2017"),
    ("das_rsi", "DAS Difficult Airway RSI", "DAS 2015"),
    ("bts_spontaneous_pneumothorax", "BTS Spontaneous Pneumothorax", "BTS 2023"),
    ("idsa_epiglottitis", "IDSA Epiglottitis Deep Neck Infection", "IDSA"),
    ("bts_massive_hemoptysis", "BTS/ERS Massive Hemoptysis", "BTS/ERS"),
    ("aha_bls_fba", "AHA BLS Foreign Body Aspiration", "AHA BLS"),
    # Neuro (7)
    ("ncs_aha_sah", "NCS/AHA Aneurysmal SAH", "NCS/AHA 2023"),
    ("aha_asa_ich", "AHA/ASA Spontaneous ICH", "AHA/ASA 2022"),
    ("aan_myasthenic_crisis", "AAN Myasthenic Crisis", "AAN 2021"),
    ("ean_guillain_barre", "EAN Guillain-Barre", "EAN 2023"),
    ("asco_nice_spinal_cord_compression", "ASCO/NICE Spinal Cord Compression", "ASCO/NICE"),
    ("asam_ciwa", "ASAM Alcohol Withdrawal CIWA", "ASAM 2020"),
    ("sccm_delirium_padis", "SCCM PADIS Delirium", "SCCM 2018"),
    # Endo/Metabolic (10)
    ("ada_hhs", "ADA HHS", "ADA 2024"),
    ("ata_thyroid_storm", "ATA Thyroid Storm", "ATA 2016"),
    ("endo_soc_adrenal_crisis", "Endocrine Society Adrenal Crisis", "Endo Society 2016"),
    ("aace_myxedema_coma", "AACE Myxedema Coma", "AACE"),
    ("ukka_hyperkalemia", "UKKA Severe Hyperkalemia", "UKKA 2023"),
    ("ese_hyponatremia", "ESE Severe Hyponatremia", "ESE/ESICM 2014"),
    ("aace_sccm_hypernatremia", "AACE/SCCM ICU Hypernatremia", "AACE/SCCM"),
    ("ada_severe_hypoglycemia", "ADA Severe Hypoglycemia", "ADA 2024"),
    ("nsw_rhabdomyolysis", "NSW Rhabdomyolysis", "NSW 2022"),
    ("endo_pheochromocytoma", "Endocrine Society Pheochromocytoma", "Endo Society 2014"),
    # Hepatic/GI (8)
    ("aasld_acute_liver_failure", "AASLD Acute Liver Failure", "AASLD 2023"),
    ("aasld_hepatic_encephalopathy", "AASLD Hepatic Encephalopathy", "AASLD 2014"),
    ("baveno_vii_variceal_hemorrhage", "Baveno VII Variceal Hemorrhage", "Baveno VII 2022"),
    ("acg_aga_pancreatitis", "ACG/AGA Acute Pancreatitis", "ACG/AGA 2013/2024"),
    ("tokyo_cholangitis", "Tokyo Guidelines Cholangitis", "Tokyo 2018"),
    ("wses_mesenteric_ischemia", "WSES Acute Mesenteric Ischemia", "WSES 2017"),
    ("ascrs_diverticulitis", "ASCRS Acute Diverticulitis", "ASCRS 2020"),
    ("idsa_fulminant_cdiff", "IDSA Fulminant C.difficile", "IDSA 2021"),
    # Renal/GU (3)
    ("isth_ash_ttp", "ISTH/ASH TTP", "ISTH/ASH 2020"),
    ("aua_testicular_torsion", "AUA Testicular Torsion", "AUA 2023"),
    ("eau_obstructive_pyelonephritis", "EAU Obstructive Pyelonephritis", "EAU"),
    # OB (5)
    ("acog_preeclampsia_hellp", "ACOG Preeclampsia/HELLP", "ACOG PB 222 2020"),
    ("smfm_afe", "SMFM AFE", "SMFM 2016"),
    ("rcog_cord_prolapse", "RCOG Cord Prolapse", "RCOG 2014"),
    ("smfm_rcog_maternal_sepsis", "SMFM/RCOG Maternal Sepsis", "SMFM/RCOG 2019"),
    ("acog_shoulder_dystocia", "ACOG Shoulder Dystocia", "ACOG 2017"),
    # Peds (8)
    ("ispad_ped_dka", "ISPAD Pediatric DKA", "ISPAD 2022"),
    ("aap_bronchiolitis", "AAP Bronchiolitis", "AAP 2014"),
    ("nrp_aap_neonatal_resus", "NRP/AAP Neonatal Resuscitation", "NRP/AAP 2020"),
    ("aha_kawasaki", "AHA Kawasaki", "AHA 2017"),
    ("sccm_ped_septic_shock", "SCCM Pediatric Septic Shock", "SCCM 2020"),
    ("gina_ped_status_asthma", "GINA Pediatric Status Asthma", "GINA"),
    ("pals_atls_ped_traumatic_arrest", "PALS/ATLS Pediatric Traumatic Arrest", "PALS/ATLS"),
    ("bimdg_iem_crisis", "BIMDG IEM Crisis", "BIMDG 2017"),
    # Infectious (6)
    ("idsa_east_nsti", "IDSA/EAST NSTI", "IDSA/EAST 2014"),
    ("idsa_toxic_shock", "IDSA Toxic Shock Syndrome", "IDSA 2014"),
    ("aha_esc_endocarditis", "AHA/ESC Infective Endocarditis", "AHA/ESC 2023"),
    ("idsa_spinal_epidural_abscess", "IDSA Spinal Epidural Abscess", "IDSA 2020"),
    ("idsa_asco_febrile_neutropenia", "IDSA/ASCO Febrile Neutropenia", "IDSA/ASCO 2018"),
    ("who_cdc_severe_malaria", "WHO/CDC Severe Malaria", "WHO/CDC 2023"),
    # Toxicology (7)
    ("aasld_aact_salicylate", "AASLD/AACT Salicylate Toxicity", "AASLD/AACT 2015"),
    ("uhms_carbon_monoxide", "UHMS Carbon Monoxide HBO", "UHMS 2017"),
    ("aact_iron_overdose", "AACT Iron Overdose", "AACT"),
    ("boyer_shannon_serotonin_syndrome", "Boyer & Shannon Serotonin Syndrome", "Boyer-Shannon 2005"),
    ("ean_nms", "EAN NMS", "EAN consensus"),
    ("extrip_lithium", "EXTRIP Lithium Toxicity", "EXTRIP 2015"),
    ("extrip_valproate", "EXTRIP Valproate Toxicity", "EXTRIP 2015"),
    # Environmental (7)
    ("wms_heat_stroke", "WMS Heat Stroke", "WMS 2024"),
    ("erc_hypothermia", "ERC Hypothermia", "ERC 2021"),
    ("erc_drowning", "ERC Drowning", "ERC 2021"),
    ("acmt_crotaline", "ACMT Crotaline Envenomation", "ACMT 2011"),
    ("wms_elapid", "WMS Elapid Coral Snake", "WMS"),
    ("wms_hace_hape", "WMS HACE/HAPE", "WMS 2024"),
    ("atls_electrical_injury", "ATLS Electrical Injury", "ATLS"),
    # Ophthal/ENT (5)
    ("aao_acute_angle_closure_glaucoma", "AAO Acute Angle-Closure Glaucoma", "AAO 2020"),
    ("aao_aha_crao", "AAO/AHA Central Retinal Artery Occlusion", "AAO/AHA 2021"),
    ("aao_orbital_cellulitis", "AAO Orbital Cellulitis", "AAO 2023"),
    ("ent_uk_epistaxis", "ENT-UK Epistaxis", "ENT-UK 2020"),
    ("ludwig_angina_pta", "Ludwig Angina / Peritonsillar Abscess", "general surgery"),
    # Heme/Onc (5)
    ("asco_tls", "ASCO Tumor Lysis Syndrome", "ASCO 2022"),
    ("asco_hypercalcemia_malignancy", "ASCO Hypercalcemia Malignancy", "ASCO 2014/2023"),
    ("asco_nccn_svc_syndrome", "ASCO/NCCN SVC Syndrome", "ASCO/NCCN"),
    ("isth_dic", "ISTH DIC", "ISTH 2013"),
    ("ash_sickle_cell_acs", "ASH Sickle Cell Acute Chest Syndrome", "ASH 2020"),
    # Other (1)
    ("asa_procedural_sedation", "ASA Procedural Sedation", "ASA 2018"),
]


def make_stub_graph(graph_id: str, guideline_name: str, source: str) -> dict[str, Any]:
    """Return a minimal but structurally-complete CPG graph dict.

    Two nodes:
      initial_assessment → treatment_plan
    Each has one mandatory action, provenance fields, valid transitions.
    """
    return {
        "graph_id": graph_id,
        "guideline_name": guideline_name,
        "version": "p1-stub-v1",
        "metadata": {
            "source": source,
            "description": f"P1 scale-robustness stub for {guideline_name}",
            "is_stub": True,
        },
        "entry_node": "initial_assessment",
        "nodes": {
            "initial_assessment": {
                "node_id": "initial_assessment",
                "node_type": "enquiry",
                "name": "Initial Assessment",
                "description": f"Placeholder initial assessment for {guideline_name}",
                "mandatory_actions": [f"assess_{graph_id[:40]}"],
                "allowed_actions": [f"assess_{graph_id[:40]}", "assess_vital_signs"],
                "forbidden_actions": [],
                "deadlines": {},
                "required_prior_actions": {},
                "recommendation_class": "I",
                "evidence_level": "B",
                "source_guideline": source,
                "source_section": "Stub: Initial Assessment",
                "source_page": None,
                "source_quote": f"[stub] placeholder for {guideline_name} initial assessment",
                "next_nodes": ["treatment_plan"],
                "conditional_next": {},
            },
            "treatment_plan": {
                "node_id": "treatment_plan",
                "node_type": "plan",
                "name": "Treatment Plan",
                "description": f"Placeholder treatment plan for {guideline_name}",
                "mandatory_actions": [f"treat_{graph_id[:40]}"],
                "allowed_actions": [f"treat_{graph_id[:40]}"],
                "forbidden_actions": [],
                "deadlines": {f"treat_{graph_id[:40]}": 60},
                "required_prior_actions": {},
                "recommendation_class": "I",
                "evidence_level": "B",
                "source_guideline": source,
                "source_section": "Stub: Treatment",
                "source_page": None,
                "source_quote": f"[stub] placeholder for {guideline_name} treatment",
                "next_nodes": [],
                "conditional_next": {},
            },
        },
    }


def main() -> int:
    here = Path(__file__).resolve().parent
    # here = .../cga_bench/scripts/verify, so parents[1] = cga_bench/
    repo_root = here.parents[1]
    out_dir = repo_root / "cpg_model" / "graphs_stub_99"
    out_dir.mkdir(parents=True, exist_ok=True)

    json_dir = repo_root / "evidence_pack" / "round_trip_v1" / "stub_99_src_json"
    json_dir.mkdir(parents=True, exist_ok=True)

    loader_fails: list[tuple[str, str]] = []
    yaml_paths: list[Path] = []

    print("[1/3] Generating 99 stub YAMLs via parsed_json_loader...", flush=True)
    for graph_id, gname, source in CANDIDATES:
        stub = make_stub_graph(graph_id, gname, source)
        js_path = json_dir / f"{graph_id}.json"
        js_path.write_text(json.dumps(stub, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            result = load_and_normalize(js_path)
            yaml_path = out_dir / f"{graph_id}.yaml"
            write_yaml(result, yaml_path)
            yaml_paths.append(yaml_path)
        except Exception as exc:
            loader_fails.append((graph_id, str(exc)))
    print(f"      → {len(yaml_paths)}/{len(CANDIDATES)} YAMLs written; loader fails: {len(loader_fails)}")

    # Validator pass
    print(f"[2/3] Running validate_cpg_schema.py on {out_dir} ...", flush=True)
    validator = repo_root / "scripts" / "ci" / "validate_cpg_schema.py"
    rc = subprocess.run(
        [sys.executable, str(validator), "--graphs-dir", str(out_dir), "--skip-scenarios"],
        capture_output=True,
        text=True,
        env={**__import__("os").environ, "PYTHONPATH": str(repo_root.parent)},
        # NB: validate_cpg_schema.py is self-contained (yaml + argparse only),
        # no cga_bench.* imports, so PYTHONPATH isn't strictly required.
    )
    validator_pass = rc.returncode == 0
    validator_err_count = rc.stdout.count("ERROR") + rc.stderr.count("ERROR")
    print(f"      → rc={rc.returncode} (validator_pass={validator_pass}, errors={validator_err_count})")

    # Scenario derivation per stub
    print("[3/3] Running patient_generator on each stub...", flush=True)
    engine = ConstraintDerivationEngine()
    generator = PatientGenerator(engine, seed=42)
    scen_fails: list[tuple[str, str]] = []
    scen_counts: list[tuple[str, int]] = []
    for yp in yaml_paths:
        try:
            graph = load_graph(yp)
            scens = generator.generate_from_graph(graph)
            scen_counts.append((yp.stem, len(scens)))
        except Exception as exc:
            scen_fails.append((yp.stem, str(exc)))
    total_scenarios = sum(c for _, c in scen_counts)
    print(
        f"      → {len(scen_counts)}/{len(yaml_paths)} stubs generated scenarios; "
        f"total_scenarios={total_scenarios}; scen_fails={len(scen_fails)}"
    )

    # Evidence dump
    evidence_path = repo_root / "evidence_pack" / "round_trip_v1" / "p1_stub_99_results.json"
    evidence_path.write_text(
        json.dumps(
            {
                "candidate_count": len(CANDIDATES),
                "yaml_written": len(yaml_paths),
                "loader_fails": loader_fails,
                "validator_rc": rc.returncode,
                "validator_error_count": validator_err_count,
                "scenario_generation_fails": scen_fails,
                "scenario_counts": scen_counts,
                "total_scenarios": total_scenarios,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    # Verdict
    ok = len(loader_fails) == 0 and validator_pass and len(scen_fails) == 0 and len(yaml_paths) == len(CANDIDATES)
    verdict = "PASS" if ok else "FAIL"
    print(
        f"\n{verdict}: loader={len(yaml_paths)}/{len(CANDIDATES)} "
        f"validator_rc={rc.returncode} scen_ok={len(scen_counts)}/{len(yaml_paths)} "
        f"total_scenarios={total_scenarios}"
    )
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
