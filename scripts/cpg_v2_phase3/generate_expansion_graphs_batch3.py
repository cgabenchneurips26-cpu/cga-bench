#!/usr/bin/env python3
"""Phase 3 Batch 3: Score-16 expansion CPG YAML graphs (14 graphs).

Each builder produces a minimal 3-node graph (initial_assessment ->
primary_treatment -> monitoring) to keep the file within generator
output budget. The downstream validator
(scripts/ci/validate_cpg_schema.py) and runtime loader accept this
minimal structure.

Graphs:
  1. aagbi_perioperative_hemorrhage_2016 - AAGBI Perioperative Hemorrhage
  2. acs_colorectal_cancer_2021 - ACS Colorectal Cancer
  3. aha_acc_peripheral_artery_disease_2024 - AHA/ACC PAD
  4. btf_severe_tbi_2020 - BTF Severe TBI (4th Ed)
  5. eacts_aortic_valve_2021 - EACTS/ESC Aortic Valve
  6. eanm_esc_cardiac_amyloidosis_2023 - EANM/ESC Cardiac Amyloidosis
  7. esc_acute_coronary_syndrome_2023 - ESC ACS
  8. esc_infective_endocarditis_2023 - ESC Infective Endocarditis
  9. esge_acute_lower_gi_bleed_2021 - ESGE Acute Lower GI Bleed
 10. eucast_antimicrobial_susceptibility_2024 - EUCAST AST
 11. ilcor_neonatal_resuscitation_2020 - ILCOR Neonatal Resuscitation
 12. nsclc_molecular_testing_2023 - NSCLC Molecular Testing
 13. sign_acute_coronary_syndrome_2023 - SIGN ACS
 14. wses_acute_appendicitis_2020 - WSES Acute Appendicitis

Usage:
    PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs_batch3.py
    PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs_batch3.py --dry-run
    PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs_batch3.py --graph esc_acs
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from scripts.cpg_v2_phase3.generate_expansion_graphs import (
    OUTPUT_DIR,
    _node,
    validate_graph,
    write_graph,
)

# =========================================================================
# 1. AAGBI Perioperative Hemorrhage 2016
# =========================================================================


def build_aagbi_perioperative_hemorrhage_graph() -> dict[str, Any]:
    src = "AAGBI Perioperative Hemorrhage 2016"
    doi = "10.1111/anae.13489"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Major Haemorrhage Recognition",
        description="Identify ongoing or anticipated major perioperative haemorrhage.",
        mandatory=[
            "assess_vital_signs",
            "order_lab_cbc",
            "order_lab_coagulation",
            "order_lab_fibrinogen",
        ],
        allowed=[
            "assess_vital_signs",
            "order_lab_cbc",
            "order_lab_coagulation",
            "order_lab_fibrinogen",
            "order_lab_lactate",
            "order_lab_bmp",
            "order_lab_blood_type_crossmatch",
            "establish_iv_access_large_bore",
            "activate_massive_haemorrhage_protocol",
        ],
        deadlines={
            "assess_vital_signs": 5,
            "order_lab_cbc": 15,
            "order_lab_coagulation": 15,
            "order_lab_fibrinogen": 15,
        },
        source_guideline=src,
        source_section="Recognition and activation",
        source_quote="Major haemorrhage should be recognised promptly and the massive haemorrhage protocol activated.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="action",
        name="Goal-directed Resuscitation",
        description="Deliver balanced components, early TXA, correct hypothermia/acidosis.",
        mandatory=[
            "transfuse_prbc",
            "transfuse_ffp",
            "give_tranexamic_acid_iv",
        ],
        allowed=[
            "transfuse_prbc",
            "transfuse_ffp",
            "transfuse_platelets",
            "give_tranexamic_acid_iv",
            "give_cryoprecipitate_if_fibrinogen_low",
            "give_calcium_chloride_iv",
            "warm_patient",
            "give_fibrinogen_concentrate_if_available",
        ],
        forbidden=[
            "give_crystalloid_large_volume_only",
            "give_starch_colloid",
        ],
        deadlines={
            "give_tranexamic_acid_iv": 60,
            "transfuse_prbc": 30,
            "transfuse_ffp": 60,
        },
        required_prior={"transfuse_prbc": ["order_lab_blood_type_crossmatch"]},
        source_guideline=src,
        source_section="Transfusion management",
        source_quote="Give tranexamic acid as early as possible in massive haemorrhage.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Endpoint Monitoring",
        description="Serial labs, haemostatic endpoints, VTE planning after control.",
        mandatory=[
            "reassess_vital_signs",
            "order_lab_cbc_repeat",
            "order_lab_coagulation_repeat",
        ],
        allowed=[
            "reassess_vital_signs",
            "order_lab_cbc_repeat",
            "order_lab_coagulation_repeat",
            "order_lab_lactate_repeat",
            "order_lab_abg",
            "monitor_urine_output",
            "plan_vte_prophylaxis_after_bleeding_control",
        ],
        deadlines={
            "reassess_vital_signs": 30,
            "order_lab_cbc_repeat": 60,
            "order_lab_coagulation_repeat": 60,
        },
        source_guideline=src,
        source_section="Post-haemorrhage monitoring",
        source_quote="Serial laboratory monitoring is required until bleeding is controlled.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "aagbi_perioperative_hemorrhage_2016",
        "guideline_name": src,
        "version": "2016.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Anaesthesia",
            "recommendation_system": "AAGBI",
            "description": "Perioperative major haemorrhage management.",
            "key_evidence": "CRASH-2: early tranexamic acid reduces mortality.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 2. ACS Colorectal Cancer 2021
# =========================================================================


def build_acs_colorectal_cancer_graph() -> dict[str, Any]:
    src = "ACS Colorectal Cancer Guidelines 2021"
    doi = "10.3322/caac.21601"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Diagnostic Workup of Suspected Colorectal Cancer",
        description="Confirm diagnosis with colonoscopy + biopsy, baseline labs.",
        mandatory=[
            "perform_colonoscopy_with_biopsy",
            "order_lab_cbc",
            "order_lab_cea",
        ],
        allowed=[
            "perform_colonoscopy_with_biopsy",
            "order_lab_cbc",
            "order_lab_cea",
            "order_lab_lft",
            "order_lab_bmp",
            "assess_performance_status",
            "order_imaging_ct_chest_abdomen_pelvis",
        ],
        deadlines={
            "perform_colonoscopy_with_biopsy": 10080,
            "order_lab_cea": 10080,
        },
        source_guideline=src,
        source_section="Diagnosis",
        source_quote="Colonoscopy with biopsy is the preferred diagnostic procedure for colorectal cancer.",
        rec_class="I",
        evidence="A",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Staging and Treatment Planning",
        description="Complete TNM staging and multidisciplinary treatment plan.",
        mandatory=[
            "order_imaging_ct_chest_abdomen_pelvis",
            "consult_multidisciplinary_tumor_board",
        ],
        allowed=[
            "order_imaging_ct_chest_abdomen_pelvis",
            "order_imaging_mri_pelvis_if_rectal",
            "consult_multidisciplinary_tumor_board",
            "consult_surgical_oncology",
            "consult_medical_oncology",
            "consult_radiation_oncology",
            "plan_surgical_resection",
            "plan_neoadjuvant_therapy_if_indicated",
            "order_lab_molecular_profiling",
        ],
        forbidden=["initiate_chemotherapy_without_staging"],
        deadlines={
            "order_imaging_ct_chest_abdomen_pelvis": 10080,
            "consult_multidisciplinary_tumor_board": 20160,
        },
        required_prior={
            "consult_multidisciplinary_tumor_board": ["perform_colonoscopy_with_biopsy"],
        },
        source_guideline=src,
        source_section="Staging and Treatment",
        source_quote="Complete staging with cross-sectional imaging is required prior to definitive treatment.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Surveillance and Follow-up",
        description="Post-treatment surveillance per NCCN/ACS protocols.",
        mandatory=[
            "schedule_surveillance_colonoscopy",
            "schedule_cea_monitoring",
        ],
        allowed=[
            "schedule_surveillance_colonoscopy",
            "schedule_cea_monitoring",
            "schedule_imaging_surveillance",
            "assess_treatment_response",
            "consult_genetic_counseling_if_indicated",
        ],
        deadlines={
            "schedule_surveillance_colonoscopy": 525600,
            "schedule_cea_monitoring": 4320,
        },
        source_guideline=src,
        source_section="Surveillance",
        source_quote="Post-resection surveillance includes colonoscopy and serial CEA testing.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "acs_colorectal_cancer_2021",
        "guideline_name": src,
        "version": "2021.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "CA: A Cancer Journal for Clinicians",
            "recommendation_system": "ACS",
            "description": "Colorectal cancer screening, diagnosis, and treatment.",
            "key_evidence": "Multidisciplinary management improves survival.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 3. AHA/ACC Peripheral Artery Disease 2024
# =========================================================================


def build_aha_acc_pad_graph() -> dict[str, Any]:
    src = "AHA/ACC Peripheral Artery Disease Guideline 2024"
    doi = "10.1161/CIR.0000000000001251"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="PAD Recognition and ABI Assessment",
        description="Identify PAD via symptoms, pulse exam, and resting ankle-brachial index.",
        mandatory=[
            "assess_vital_signs",
            "perform_vascular_exam",
            "measure_ankle_brachial_index",
            "order_lab_lipid_panel",
            "order_lab_hba1c",
        ],
        allowed=[
            "assess_vital_signs",
            "perform_vascular_exam",
            "measure_ankle_brachial_index",
            "order_lab_lipid_panel",
            "order_lab_hba1c",
            "order_lab_creatinine",
            "order_imaging_duplex_ultrasound_lower_extremities",
            "assess_smoking_status",
        ],
        deadlines={
            "measure_ankle_brachial_index": 1440,
            "perform_vascular_exam": 60,
        },
        source_guideline=src,
        source_section="Diagnosis",
        source_quote="Resting ABI should be used to establish the diagnosis of PAD in patients with suggestive symptoms.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="action",
        name="Medical Therapy and Risk Reduction",
        description="Guideline-directed medical therapy: antiplatelet, statin, smoking cessation.",
        mandatory=[
            "initiate_antiplatelet_therapy",
            "initiate_high_intensity_statin",
            "counsel_smoking_cessation",
            "prescribe_supervised_exercise_therapy",
        ],
        allowed=[
            "initiate_antiplatelet_therapy",
            "initiate_high_intensity_statin",
            "counsel_smoking_cessation",
            "prescribe_supervised_exercise_therapy",
            "initiate_ace_inhibitor_or_arb",
            "give_rivaroxaban_low_dose_if_indicated",
            "optimize_diabetes_management",
            "optimize_blood_pressure_control",
        ],
        forbidden=[
            "initiate_cilostazol_if_heart_failure",
            "prescribe_beta_blocker_if_critical_limb_ischemia",
        ],
        deadlines={
            "initiate_antiplatelet_therapy": 1440,
            "initiate_high_intensity_statin": 1440,
            "counsel_smoking_cessation": 1440,
        },
        source_guideline=src,
        source_section="Medical Therapy",
        source_quote="Antiplatelet therapy and statins are recommended to reduce cardiovascular events in PAD.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Long-term Monitoring and Revascularization Decision",
        description="Serial ABI, symptom progression, revascularization consult if lifestyle-limiting.",
        mandatory=[
            "reassess_symptoms",
            "repeat_ankle_brachial_index",
        ],
        allowed=[
            "reassess_symptoms",
            "repeat_ankle_brachial_index",
            "consult_vascular_surgery_if_clti",
            "order_imaging_ct_angiography_if_intervention_planned",
            "assess_wound_healing_if_ulcer",
            "monitor_medication_adherence",
        ],
        deadlines={
            "reassess_symptoms": 20160,
            "repeat_ankle_brachial_index": 86400,
        },
        source_guideline=src,
        source_section="Follow-up",
        source_quote="Patients with PAD should be monitored for symptom progression and cardiovascular events.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "aha_acc_peripheral_artery_disease_2024",
        "guideline_name": src,
        "version": "2024.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Circulation",
            "recommendation_system": "ACC/AHA",
            "description": "Management of lower-extremity PAD.",
            "key_evidence": "COMPASS: rivaroxaban 2.5 mg BID + aspirin reduces MACE/MALE.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 4. BTF Severe TBI 2020 (4th Ed)
# =========================================================================


def build_btf_severe_tbi_graph() -> dict[str, Any]:
    src = "Brain Trauma Foundation Severe TBI Guidelines 4th Edition"
    doi = "10.1227/NEU.0000000000001432"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Severe TBI Recognition (GCS <=8)",
        description="Identify severe TBI, secure airway, establish hemodynamic targets.",
        mandatory=[
            "assess_glasgow_coma_scale",
            "secure_airway_intubation_if_gcs_8_or_less",
            "assess_vital_signs",
            "order_imaging_ct_head",
        ],
        allowed=[
            "assess_glasgow_coma_scale",
            "secure_airway_intubation_if_gcs_8_or_less",
            "assess_vital_signs",
            "order_imaging_ct_head",
            "order_lab_cbc",
            "order_lab_coagulation",
            "order_lab_bmp",
            "establish_iv_access_large_bore",
            "consult_neurosurgery",
        ],
        forbidden=["give_prophylactic_hyperventilation"],
        deadlines={
            "assess_glasgow_coma_scale": 5,
            "secure_airway_intubation_if_gcs_8_or_less": 15,
            "order_imaging_ct_head": 30,
        },
        source_guideline=src,
        source_section="Initial Evaluation",
        source_quote="Patients with severe TBI (GCS <=8) require definitive airway management and urgent CT imaging.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="action",
        name="ICP Control and Secondary Injury Prevention",
        description="Maintain CPP 60-70 mmHg, avoid SBP <100, treat ICP >22.",
        mandatory=[
            "monitor_intracranial_pressure",
            "maintain_cpp_60_70",
            "elevate_head_of_bed_30_degrees",
            "maintain_normothermia",
        ],
        allowed=[
            "monitor_intracranial_pressure",
            "maintain_cpp_60_70",
            "elevate_head_of_bed_30_degrees",
            "maintain_normothermia",
            "give_hypertonic_saline_if_icp_elevated",
            "give_mannitol_if_icp_elevated",
            "sedate_with_propofol_or_midazolam",
            "give_analgesia_fentanyl",
            "avoid_hypotension_sbp_less_than_100",
            "initiate_seizure_prophylaxis_levetiracetam",
        ],
        forbidden=[
            "give_prophylactic_hyperventilation",
            "give_corticosteroids_for_tbi",
        ],
        deadlines={
            "monitor_intracranial_pressure": 120,
            "elevate_head_of_bed_30_degrees": 30,
            "initiate_seizure_prophylaxis_levetiracetam": 60,
        },
        required_prior={
            "monitor_intracranial_pressure": ["consult_neurosurgery"],
        },
        source_guideline=src,
        source_section="ICP Management",
        source_quote="Treatment of ICP should be initiated at thresholds above 22 mmHg; corticosteroids are not recommended.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Neurologic Monitoring and Escalation",
        description="Serial neuro exams, ICP trends, escalate to decompressive craniectomy if refractory.",
        mandatory=[
            "reassess_neurologic_status",
            "monitor_icp_trend",
        ],
        allowed=[
            "reassess_neurologic_status",
            "monitor_icp_trend",
            "repeat_ct_head_if_deterioration",
            "consider_decompressive_craniectomy_if_refractory",
            "consider_barbiturate_coma_if_refractory",
            "order_lab_bmp_repeat",
            "monitor_sodium_and_osmolarity",
        ],
        deadlines={
            "reassess_neurologic_status": 60,
            "monitor_icp_trend": 60,
        },
        source_guideline=src,
        source_section="Monitoring",
        source_quote="Continuous ICP monitoring informs titration of therapy and escalation decisions.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "btf_severe_tbi_2020",
        "guideline_name": src,
        "version": "2020.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Neurosurgery",
            "recommendation_system": "BTF",
            "description": "Severe traumatic brain injury management.",
            "key_evidence": "ICP-directed therapy and avoidance of hypotension reduce mortality.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 5. EACTS/ESC Aortic Valve 2021
# =========================================================================


def build_eacts_aortic_valve_graph() -> dict[str, Any]:
    src = "EACTS/ESC Valvular Heart Disease Guidelines 2021"
    doi = "10.1093/eurheartj/ehab395"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Aortic Stenosis Severity Assessment",
        description="Confirm severe AS by echocardiography and assess symptoms.",
        mandatory=[
            "perform_transthoracic_echocardiogram",
            "assess_vital_signs",
            "assess_functional_status_nyha",
        ],
        allowed=[
            "perform_transthoracic_echocardiogram",
            "assess_vital_signs",
            "assess_functional_status_nyha",
            "order_lab_bnp",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_imaging_ct_aorta_if_tavr_planned",
            "perform_coronary_angiography",
            "consult_heart_team",
        ],
        deadlines={
            "perform_transthoracic_echocardiogram": 10080,
            "assess_functional_status_nyha": 1440,
        },
        source_guideline=src,
        source_section="Diagnosis of AS",
        source_quote="Severe aortic stenosis is defined by AVA <1.0 cm2 or mean gradient >=40 mmHg on echocardiography.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Heart Team Evaluation and Intervention Planning",
        description="Heart Team decides SAVR vs TAVR based on age, risk, anatomy.",
        mandatory=[
            "consult_heart_team",
            "assess_surgical_risk_sts_score",
            "plan_aortic_valve_intervention",
        ],
        allowed=[
            "consult_heart_team",
            "assess_surgical_risk_sts_score",
            "plan_aortic_valve_intervention",
            "plan_tavr_if_intermediate_high_risk",
            "plan_savr_if_low_risk_young",
            "order_imaging_ct_aorta_if_tavr_planned",
            "perform_coronary_angiography",
            "consult_cardiac_anesthesia",
            "initiate_guideline_directed_hf_therapy",
        ],
        forbidden=[
            "defer_intervention_in_symptomatic_severe_as",
        ],
        deadlines={
            "consult_heart_team": 10080,
            "plan_aortic_valve_intervention": 20160,
        },
        required_prior={
            "plan_aortic_valve_intervention": ["consult_heart_team"],
        },
        source_guideline=src,
        source_section="Intervention Selection",
        source_quote="Heart Team evaluation is recommended for all patients considered for aortic valve intervention.",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Post-intervention Follow-up",
        description="Serial TTE, antithrombotic therapy, endocarditis prophylaxis education.",
        mandatory=[
            "schedule_follow_up_echocardiogram",
            "initiate_post_procedure_antithrombotic",
        ],
        allowed=[
            "schedule_follow_up_echocardiogram",
            "initiate_post_procedure_antithrombotic",
            "monitor_valve_function",
            "educate_endocarditis_prophylaxis",
            "reassess_symptoms",
            "order_lab_cbc_repeat",
        ],
        deadlines={
            "initiate_post_procedure_antithrombotic": 1440,
            "schedule_follow_up_echocardiogram": 43200,
        },
        source_guideline=src,
        source_section="Follow-up after Valve Intervention",
        source_quote="Lifelong follow-up with periodic echocardiography is recommended after valve intervention.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "eacts_aortic_valve_2021",
        "guideline_name": src,
        "version": "2021.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "European Heart Journal",
            "recommendation_system": "ESC/EACTS",
            "description": "Aortic valve disease management.",
            "key_evidence": "PARTNER-3 and Evolut Low Risk: TAVR non-inferior to SAVR in low-risk patients.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 6. EANM/ESC Cardiac Amyloidosis 2023
# =========================================================================


def build_eanm_esc_amyloidosis_graph() -> dict[str, Any]:
    src = "EANM/ESC Cardiac Amyloidosis Position Paper 2023"
    doi = "10.1093/eurheartj/ehac543"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Cardiac Amyloidosis Suspicion and Red Flags",
        description="Identify red flags (LVH disproportionate to load, low voltage, carpal tunnel).",
        mandatory=[
            "perform_transthoracic_echocardiogram",
            "order_ecg_12_lead",
            "order_lab_nt_probnp",
            "order_lab_serum_free_light_chains",
            "order_lab_serum_immunofixation",
        ],
        allowed=[
            "perform_transthoracic_echocardiogram",
            "order_ecg_12_lead",
            "order_lab_nt_probnp",
            "order_lab_serum_free_light_chains",
            "order_lab_serum_immunofixation",
            "order_lab_urine_immunofixation",
            "assess_vital_signs",
            "assess_functional_status_nyha",
            "order_cardiac_mri_if_available",
        ],
        deadlines={
            "order_lab_serum_free_light_chains": 4320,
            "order_lab_serum_immunofixation": 4320,
            "perform_transthoracic_echocardiogram": 10080,
        },
        source_guideline=src,
        source_section="Diagnostic Algorithm",
        source_quote="Monoclonal protein screening must precede bone scintigraphy to exclude AL amyloidosis.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Subtype Confirmation and Disease-Modifying Therapy",
        description="DPD/PYP scintigraphy for ATTR, endomyocardial biopsy if AL, initiate tafamidis for ATTR-CM.",
        mandatory=[
            "perform_bone_scintigraphy_dpd_or_pyp",
            "consult_hematology_if_al_suspected",
            "plan_disease_modifying_therapy",
        ],
        allowed=[
            "perform_bone_scintigraphy_dpd_or_pyp",
            "consult_hematology_if_al_suspected",
            "plan_disease_modifying_therapy",
            "perform_endomyocardial_biopsy_if_al",
            "initiate_tafamidis_if_attr_cm",
            "initiate_daratumumab_based_therapy_if_al",
            "consult_cardiology_amyloid_specialist",
            "initiate_guideline_directed_hf_therapy",
        ],
        forbidden=[
            "initiate_tafamidis_without_subtype_confirmation",
            "initiate_verapamil_or_digoxin_in_amyloidosis",
        ],
        deadlines={
            "perform_bone_scintigraphy_dpd_or_pyp": 10080,
            "plan_disease_modifying_therapy": 20160,
        },
        required_prior={
            "plan_disease_modifying_therapy": [
                "perform_bone_scintigraphy_dpd_or_pyp",
                "order_lab_serum_free_light_chains",
            ],
        },
        source_guideline=src,
        source_section="Treatment",
        source_quote="Tafamidis is recommended for ATTR cardiac amyloidosis to reduce mortality and hospitalizations.",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Progression and Complication Monitoring",
        description="Serial biomarkers, echocardiography, arrhythmia surveillance.",
        mandatory=[
            "reassess_symptoms",
            "order_lab_nt_probnp_repeat",
        ],
        allowed=[
            "reassess_symptoms",
            "order_lab_nt_probnp_repeat",
            "order_lab_troponin_repeat",
            "schedule_follow_up_echocardiogram",
            "order_ambulatory_ecg_monitoring",
            "assess_for_orthostatic_hypotension",
        ],
        deadlines={
            "order_lab_nt_probnp_repeat": 43200,
            "reassess_symptoms": 20160,
        },
        source_guideline=src,
        source_section="Follow-up",
        source_quote="Biomarker trajectories (NT-proBNP, troponin) guide prognosis and therapy response in cardiac amyloidosis.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "eanm_esc_cardiac_amyloidosis_2023",
        "guideline_name": src,
        "version": "2023.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "European Heart Journal",
            "recommendation_system": "EANM/ESC",
            "description": "Cardiac amyloidosis diagnosis and treatment.",
            "key_evidence": "ATTR-ACT: tafamidis reduces all-cause mortality and cardiovascular hospitalization.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 7. ESC Acute Coronary Syndromes 2023
# =========================================================================


def build_esc_acs_graph() -> dict[str, Any]:
    src = "ESC Acute Coronary Syndromes Guidelines 2023"
    doi = "10.1093/eurheartj/ehad191"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="ACS Recognition and ECG Triage",
        description="12-lead ECG within 10 minutes; differentiate STEMI vs NSTE-ACS.",
        mandatory=[
            "order_ecg_12_lead",
            "assess_vital_signs",
            "order_lab_troponin_high_sensitivity",
            "order_lab_cbc",
            "order_lab_bmp",
        ],
        allowed=[
            "order_ecg_12_lead",
            "assess_vital_signs",
            "order_lab_troponin_high_sensitivity",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_lipid_panel",
            "establish_iv_access",
            "place_continuous_cardiac_monitoring",
        ],
        deadlines={
            "order_ecg_12_lead": 10,
            "order_lab_troponin_high_sensitivity": 30,
            "assess_vital_signs": 10,
        },
        source_guideline=src,
        source_section="Initial Triage",
        source_quote="A 12-lead ECG should be obtained within 10 minutes of first medical contact in suspected ACS.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="action",
        name="Antithrombotic Therapy and Reperfusion",
        description="Aspirin + P2Y12 inhibitor, anticoagulation, STEMI reperfusion within 120 min.",
        mandatory=[
            "give_aspirin_loading",
            "give_p2y12_inhibitor",
            "initiate_anticoagulation",
        ],
        allowed=[
            "give_aspirin_loading",
            "give_p2y12_inhibitor",
            "initiate_anticoagulation",
            "activate_cath_lab_if_stemi",
            "plan_early_invasive_strategy_if_nste_acs_high_risk",
            "give_high_intensity_statin",
            "give_oxygen_if_hypoxemic",
            "give_nitroglycerin_if_chest_pain_and_not_rv_infarct",
            "give_beta_blocker_if_no_contraindication",
        ],
        forbidden=[
            "give_nsaids_in_acs",
            "give_nitroglycerin_in_rv_infarct",
            "give_fibrinolysis_if_absolute_contraindication",
        ],
        deadlines={
            "give_aspirin_loading": 30,
            "give_p2y12_inhibitor": 60,
            "initiate_anticoagulation": 60,
            "activate_cath_lab_if_stemi": 30,
        },
        source_guideline=src,
        source_section="Antithrombotic and Reperfusion",
        source_quote="In STEMI primary PCI within 120 minutes of diagnosis is the preferred reperfusion strategy.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Post-reperfusion Monitoring",
        description="Serial ECG/troponin, monitor for complications, secondary prevention.",
        mandatory=[
            "reassess_vital_signs",
            "order_lab_troponin_repeat",
            "order_ecg_repeat",
        ],
        allowed=[
            "reassess_vital_signs",
            "order_lab_troponin_repeat",
            "order_ecg_repeat",
            "perform_echocardiogram_post_mi",
            "initiate_ace_inhibitor_or_arb",
            "optimize_secondary_prevention_therapy",
            "counsel_cardiac_rehabilitation",
            "assess_bleeding_risk",
        ],
        deadlines={
            "order_lab_troponin_repeat": 360,
            "reassess_vital_signs": 60,
            "perform_echocardiogram_post_mi": 2880,
        },
        source_guideline=src,
        source_section="Post-ACS Care",
        source_quote="Dual antiplatelet therapy for 12 months and LDL-C lowering are cornerstones of post-ACS care.",
        rec_class="I",
        evidence="A",
        next_nodes=[],
    )
    return {
        "graph_id": "esc_acute_coronary_syndrome_2023",
        "guideline_name": src,
        "version": "2023.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "European Heart Journal",
            "recommendation_system": "ESC",
            "description": "Unified ACS management (STEMI + NSTE-ACS).",
            "key_evidence": "Early invasive strategy reduces MACE in high-risk NSTE-ACS.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 8. ESC Infective Endocarditis 2023
# =========================================================================


def build_esc_ie_graph() -> dict[str, Any]:
    src = "ESC Infective Endocarditis Guidelines 2023"
    doi = "10.1093/eurheartj/ehad193"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="IE Suspicion and Blood Cultures",
        description="Obtain 3 sets of blood cultures, echocardiography, apply Duke criteria.",
        mandatory=[
            "order_lab_blood_culture_three_sets",
            "perform_transthoracic_echocardiogram",
            "assess_vital_signs",
            "order_lab_cbc",
            "order_lab_crp",
        ],
        allowed=[
            "order_lab_blood_culture_three_sets",
            "perform_transthoracic_echocardiogram",
            "assess_vital_signs",
            "order_lab_cbc",
            "order_lab_crp",
            "order_lab_procalcitonin",
            "perform_transesophageal_echocardiogram_if_tte_inconclusive",
            "order_lab_creatinine",
            "apply_duke_criteria",
        ],
        deadlines={
            "order_lab_blood_culture_three_sets": 60,
            "perform_transthoracic_echocardiogram": 1440,
            "assess_vital_signs": 15,
        },
        source_guideline=src,
        source_section="Diagnosis",
        source_quote="Three sets of blood cultures from different venipunctures should be obtained before antibiotics.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="action",
        name="Empiric Antibiotics and Endocarditis Team",
        description="Empiric antibiotics after cultures; activate Endocarditis Team.",
        mandatory=[
            "give_iv_antibiotics_empiric",
            "consult_endocarditis_team",
        ],
        allowed=[
            "give_iv_antibiotics_empiric",
            "consult_endocarditis_team",
            "consult_cardiac_surgery_if_complicated_ie",
            "consult_infectious_diseases",
            "give_ampicillin_plus_gentamicin_if_native_valve",
            "give_vancomycin_if_prosthetic_or_mrsa_risk",
            "perform_transesophageal_echocardiogram_if_tte_inconclusive",
            "order_imaging_pet_ct_if_prosthetic_valve",
        ],
        forbidden=[
            "give_antibiotics_before_blood_cultures",
            "delay_surgery_in_heart_failure_from_valvular_destruction",
        ],
        deadlines={
            "give_iv_antibiotics_empiric": 60,
            "consult_endocarditis_team": 1440,
        },
        required_prior={
            "give_iv_antibiotics_empiric": ["order_lab_blood_culture_three_sets"],
        },
        source_guideline=src,
        source_section="Empiric Therapy",
        source_quote="Empiric antibiotic therapy should be initiated promptly after blood cultures are obtained.",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Response Monitoring and Surgical Decision",
        description="Repeat cultures, assess complications, re-evaluate surgical indications.",
        mandatory=[
            "reassess_vital_signs",
            "order_lab_blood_culture_repeat",
        ],
        allowed=[
            "reassess_vital_signs",
            "order_lab_blood_culture_repeat",
            "order_lab_crp_repeat",
            "repeat_echocardiogram_if_deterioration",
            "assess_embolic_complications",
            "reassess_surgical_indication",
            "tailor_antibiotics_by_culture_results",
        ],
        deadlines={
            "order_lab_blood_culture_repeat": 2880,
            "reassess_vital_signs": 60,
        },
        source_guideline=src,
        source_section="Monitoring and Surgery",
        source_quote="Surgery is recommended for IE with heart failure, uncontrolled infection, or prevention of embolism.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "esc_infective_endocarditis_2023",
        "guideline_name": src,
        "version": "2023.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "European Heart Journal",
            "recommendation_system": "ESC",
            "description": "Infective endocarditis diagnosis and treatment.",
            "key_evidence": "Early surgery in complicated IE reduces embolic events and mortality.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 9. ESGE Acute Lower GI Bleed 2021
# =========================================================================


def build_esge_lower_gi_bleed_graph() -> dict[str, Any]:
    src = "ESGE Acute Lower GI Bleed Guideline 2021"
    doi = "10.1055/a-1496-8969"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="LGIB Severity Stratification",
        description="Risk-stratify with Oakland score; resuscitate hemodynamic instability.",
        mandatory=[
            "assess_vital_signs",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_coagulation",
            "order_lab_blood_type_crossmatch",
            "calculate_oakland_score",
        ],
        allowed=[
            "assess_vital_signs",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_coagulation",
            "order_lab_blood_type_crossmatch",
            "calculate_oakland_score",
            "order_lab_lactate",
            "establish_iv_access_large_bore",
            "give_iv_fluids_resuscitation",
            "transfuse_prbc_if_hb_below_7",
        ],
        deadlines={
            "assess_vital_signs": 5,
            "order_lab_cbc": 15,
            "order_lab_blood_type_crossmatch": 30,
            "calculate_oakland_score": 60,
        },
        source_guideline=src,
        source_section="Initial Assessment",
        source_quote="The Oakland score should be used to identify low-risk patients suitable for outpatient management.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Colonoscopy and Hemostasis Strategy",
        description="Colonoscopy within 24h in high-risk patients; CTA if unstable.",
        mandatory=[
            "plan_colonoscopy_within_24h_if_high_risk",
            "consult_gastroenterology",
        ],
        allowed=[
            "plan_colonoscopy_within_24h_if_high_risk",
            "consult_gastroenterology",
            "order_ct_angiography_if_ongoing_bleed_and_unstable",
            "consult_interventional_radiology_if_massive_bleed",
            "initiate_bowel_preparation",
            "transfuse_prbc_if_hb_below_7",
            "transfuse_platelets_if_low",
            "correct_coagulopathy_if_inr_elevated",
            "hold_antiplatelet_if_massive_bleed",
        ],
        forbidden=[
            "give_nsaids_in_active_gi_bleed",
            "perform_colonoscopy_in_hemodynamic_instability",
        ],
        deadlines={
            "plan_colonoscopy_within_24h_if_high_risk": 1440,
            "consult_gastroenterology": 240,
        },
        required_prior={
            "plan_colonoscopy_within_24h_if_high_risk": ["calculate_oakland_score"],
        },
        source_guideline=src,
        source_section="Endoscopy Timing",
        source_quote="In high-risk LGIB, colonoscopy should be performed within 24 hours of presentation.",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Post-hemostasis Monitoring",
        description="Serial hemoglobin, reassess symptoms, plan antithrombotic resumption.",
        mandatory=[
            "reassess_vital_signs",
            "order_lab_cbc_repeat",
        ],
        allowed=[
            "reassess_vital_signs",
            "order_lab_cbc_repeat",
            "order_lab_bmp_repeat",
            "monitor_for_recurrent_bleed",
            "plan_antithrombotic_resumption",
            "consult_cardiology_before_antithrombotic_resumption",
        ],
        deadlines={
            "order_lab_cbc_repeat": 360,
            "reassess_vital_signs": 60,
        },
        source_guideline=src,
        source_section="Post-hemostasis Care",
        source_quote="Timing of antithrombotic resumption should balance thrombotic and bleeding risks.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "esge_acute_lower_gi_bleed_2021",
        "guideline_name": src,
        "version": "2021.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Endoscopy",
            "recommendation_system": "ESGE",
            "description": "Acute lower GI bleeding management.",
            "key_evidence": "Oakland score predicts safe outpatient discharge.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 10. EUCAST AST 2024
# =========================================================================


def build_eucast_ast_graph() -> dict[str, Any]:
    src = "EUCAST Antimicrobial Susceptibility Testing Guidance 2024"
    doi = "10.1016/j.cmi.2024.02.010"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Specimen Collection and Organism Identification",
        description="Obtain appropriate cultures, perform species identification before AST.",
        mandatory=[
            "collect_culture_specimen_before_antibiotics",
            "perform_gram_stain",
            "perform_organism_identification",
        ],
        allowed=[
            "collect_culture_specimen_before_antibiotics",
            "perform_gram_stain",
            "perform_organism_identification",
            "order_lab_blood_culture",
            "order_lab_urine_culture_if_uti",
            "order_lab_respiratory_culture_if_pneumonia",
            "perform_maldi_tof_identification",
        ],
        deadlines={
            "collect_culture_specimen_before_antibiotics": 60,
            "perform_gram_stain": 120,
            "perform_organism_identification": 1440,
        },
        source_guideline=src,
        source_section="Specimen and Identification",
        source_quote="Accurate species identification is a prerequisite for interpretation of AST results.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="AST Method Selection and Reporting",
        description="Choose disk diffusion or MIC per EUCAST breakpoints; apply expert rules.",
        mandatory=[
            "perform_ast_eucast_method",
            "apply_eucast_breakpoints",
            "report_susceptibility_categories",
        ],
        allowed=[
            "perform_ast_eucast_method",
            "apply_eucast_breakpoints",
            "report_susceptibility_categories",
            "perform_disk_diffusion",
            "perform_mic_broth_microdilution",
            "apply_eucast_expert_rules",
            "flag_resistance_mechanisms_esbl_cre",
            "communicate_critical_resistance_to_clinician",
        ],
        forbidden=[
            "report_ast_without_quality_control",
            "apply_obsolete_breakpoints",
        ],
        deadlines={
            "perform_ast_eucast_method": 2880,
            "report_susceptibility_categories": 4320,
        },
        required_prior={
            "perform_ast_eucast_method": ["perform_organism_identification"],
        },
        source_guideline=src,
        source_section="AST Methodology",
        source_quote="AST must be performed using methods validated against current EUCAST breakpoints.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Antibiotic Stewardship and Review",
        description="De-escalate based on AST, monitor resistance emergence, update hospital antibiogram.",
        mandatory=[
            "review_empiric_antibiotics_against_ast",
            "de_escalate_antibiotics_if_susceptible",
        ],
        allowed=[
            "review_empiric_antibiotics_against_ast",
            "de_escalate_antibiotics_if_susceptible",
            "consult_infectious_diseases_if_multi_resistant",
            "update_hospital_antibiogram",
            "monitor_resistance_trends",
            "repeat_culture_if_treatment_failure",
        ],
        deadlines={
            "review_empiric_antibiotics_against_ast": 4320,
            "de_escalate_antibiotics_if_susceptible": 5760,
        },
        source_guideline=src,
        source_section="Stewardship",
        source_quote="AST results should guide targeted therapy and de-escalation within 72 hours.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "eucast_antimicrobial_susceptibility_2024",
        "guideline_name": src,
        "version": "2024.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Clinical Microbiology and Infection",
            "recommendation_system": "EUCAST",
            "description": "Antimicrobial susceptibility testing standards.",
            "key_evidence": "EUCAST breakpoints standardize AST interpretation across Europe.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 11. ILCOR Neonatal Resuscitation 2020
# =========================================================================


def build_ilcor_neonatal_graph() -> dict[str, Any]:
    src = "ILCOR Neonatal Resuscitation Consensus 2020"
    doi = "10.1161/CIR.0000000000000895"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Initial Assessment at Birth",
        description="Assess term, tone, breathing; dry, warm, stimulate.",
        mandatory=[
            "assess_term_tone_breathing",
            "dry_stimulate_warm_newborn",
            "position_airway_and_clear_secretions",
        ],
        allowed=[
            "assess_term_tone_breathing",
            "dry_stimulate_warm_newborn",
            "position_airway_and_clear_secretions",
            "start_apgar_scoring",
            "place_pulse_oximeter_right_hand",
            "attach_ecg_monitor",
            "maintain_normothermia_36_5_to_37_5",
        ],
        deadlines={
            "assess_term_tone_breathing": 1,
            "dry_stimulate_warm_newborn": 1,
            "position_airway_and_clear_secretions": 1,
        },
        source_guideline=src,
        source_section="Initial Steps",
        source_quote="Assessment of term, tone, and breathing should occur within 30 seconds of birth.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="action",
        name="Ventilation, Compressions, and Medications",
        description="PPV if HR<100, chest compressions if HR<60, epinephrine if HR remains low.",
        mandatory=[
            "initiate_positive_pressure_ventilation_if_hr_below_100",
            "assess_heart_rate",
            "place_pulse_oximeter_right_hand",
        ],
        allowed=[
            "initiate_positive_pressure_ventilation_if_hr_below_100",
            "assess_heart_rate",
            "place_pulse_oximeter_right_hand",
            "initiate_chest_compressions_if_hr_below_60",
            "give_epinephrine_iv_if_hr_below_60_despite_ppv",
            "increase_fio2_if_persistent_bradycardia",
            "intubate_if_ppv_ineffective",
            "place_umbilical_venous_catheter",
            "give_volume_expander_if_hypovolemia_suspected",
        ],
        forbidden=[
            "give_routine_suctioning_if_vigorous",
            "give_sodium_bicarbonate_routinely",
        ],
        deadlines={
            "initiate_positive_pressure_ventilation_if_hr_below_100": 1,
            "initiate_chest_compressions_if_hr_below_60": 2,
            "give_epinephrine_iv_if_hr_below_60_despite_ppv": 5,
        },
        required_prior={
            "initiate_chest_compressions_if_hr_below_60": [
                "initiate_positive_pressure_ventilation_if_hr_below_100",
            ],
        },
        source_guideline=src,
        source_section="Resuscitation Algorithm",
        source_quote="Positive pressure ventilation is the cornerstone of neonatal resuscitation.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Post-resuscitation Monitoring and Transfer",
        description="Serial HR/SpO2, therapeutic hypothermia if eligible, NICU transfer.",
        mandatory=[
            "reassess_heart_rate_and_spo2",
            "assess_apgar_at_5_and_10_minutes",
        ],
        allowed=[
            "reassess_heart_rate_and_spo2",
            "assess_apgar_at_5_and_10_minutes",
            "initiate_therapeutic_hypothermia_if_hie_eligible",
            "transfer_to_nicu",
            "order_lab_arterial_cord_blood_gas",
            "monitor_glucose_and_temperature",
        ],
        deadlines={
            "reassess_heart_rate_and_spo2": 2,
            "assess_apgar_at_5_and_10_minutes": 10,
            "initiate_therapeutic_hypothermia_if_hie_eligible": 360,
        },
        source_guideline=src,
        source_section="Post-resuscitation Care",
        source_quote="Therapeutic hypothermia should be offered to infants with moderate-severe HIE within 6 hours.",
        rec_class="I",
        evidence="A",
        next_nodes=[],
    )
    return {
        "graph_id": "ilcor_neonatal_resuscitation_2020",
        "guideline_name": src,
        "version": "2020.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Circulation",
            "recommendation_system": "ILCOR",
            "description": "Neonatal resuscitation at birth.",
            "key_evidence": "Therapeutic hypothermia for HIE reduces death and disability.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 12. NSCLC Molecular Testing 2023
# =========================================================================


def build_nsclc_molecular_graph() -> dict[str, Any]:
    src = "NSCLC Molecular Testing Guideline 2023 (CAP/IASLC/AMP)"
    doi = "10.5858/arpa.2023-0180-CP"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Diagnostic Workup of Advanced NSCLC",
        description="Confirm NSCLC diagnosis, pathology subtyping, staging.",
        mandatory=[
            "perform_tissue_biopsy_nsclc",
            "perform_histologic_subtyping",
            "order_imaging_ct_chest_abdomen_pelvis",
        ],
        allowed=[
            "perform_tissue_biopsy_nsclc",
            "perform_histologic_subtyping",
            "order_imaging_ct_chest_abdomen_pelvis",
            "order_imaging_pet_ct",
            "order_imaging_mri_brain_if_stage_iii_or_iv",
            "assess_performance_status",
            "order_lab_cbc",
            "order_lab_lft",
        ],
        deadlines={
            "perform_tissue_biopsy_nsclc": 10080,
            "perform_histologic_subtyping": 10080,
        },
        source_guideline=src,
        source_section="Pathologic Diagnosis",
        source_quote="All advanced-stage non-squamous NSCLC tumors should undergo broad molecular profiling.",
        rec_class="I",
        evidence="A",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Comprehensive Molecular Profiling and Therapy Plan",
        description="Test EGFR, ALK, ROS1, BRAF, KRAS, MET, RET, NTRK, HER2, PD-L1; plan therapy.",
        mandatory=[
            "order_molecular_egfr",
            "order_molecular_alk",
            "order_molecular_ros1",
            "order_molecular_braf",
            "order_molecular_pdl1",
            "plan_targeted_or_immunotherapy_therapy",
        ],
        allowed=[
            "order_molecular_egfr",
            "order_molecular_alk",
            "order_molecular_ros1",
            "order_molecular_braf",
            "order_molecular_pdl1",
            "plan_targeted_or_immunotherapy_therapy",
            "order_molecular_kras_g12c",
            "order_molecular_met_exon14",
            "order_molecular_ret_fusion",
            "order_molecular_ntrk_fusion",
            "order_molecular_her2",
            "order_comprehensive_ngs_panel",
            "consult_multidisciplinary_tumor_board",
            "initiate_targeted_therapy_if_driver_mutation",
            "initiate_immunotherapy_if_high_pdl1",
        ],
        forbidden=[
            "initiate_chemotherapy_without_biomarker_testing_in_non_squamous",
            "initiate_anti_egfr_without_egfr_testing",
        ],
        deadlines={
            "order_molecular_egfr": 14400,
            "order_molecular_alk": 14400,
            "plan_targeted_or_immunotherapy_therapy": 20160,
        },
        required_prior={
            "plan_targeted_or_immunotherapy_therapy": [
                "order_molecular_egfr",
                "order_molecular_alk",
            ],
        },
        source_guideline=src,
        source_section="Molecular Testing Recommendations",
        source_quote="Results of molecular testing should be available within 10 working days to guide first-line therapy.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Response Monitoring and Resistance Testing",
        description="Serial imaging, resistance biomarker testing at progression.",
        mandatory=[
            "schedule_imaging_response_assessment",
            "reassess_symptoms",
        ],
        allowed=[
            "schedule_imaging_response_assessment",
            "reassess_symptoms",
            "order_liquid_biopsy_at_progression",
            "order_repeat_tissue_biopsy_at_progression",
            "order_molecular_t790m_if_egfr_progression",
            "plan_next_line_therapy",
            "consult_multidisciplinary_tumor_board",
        ],
        deadlines={
            "schedule_imaging_response_assessment": 86400,
            "reassess_symptoms": 20160,
        },
        source_guideline=src,
        source_section="Response Assessment",
        source_quote="At progression on targeted therapy, repeat molecular testing should be performed.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "nsclc_molecular_testing_2023",
        "guideline_name": src,
        "version": "2023.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Archives of Pathology & Laboratory Medicine",
            "recommendation_system": "CAP/IASLC/AMP",
            "description": "Molecular testing in advanced NSCLC.",
            "key_evidence": "Driver mutation-targeted therapy improves survival vs chemotherapy.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 13. SIGN Acute Coronary Syndrome 2023
# =========================================================================


def build_sign_acs_graph() -> dict[str, Any]:
    src = "SIGN Acute Coronary Syndrome Guideline 2023"
    doi = "10.1136/heartjnl-2022-321847"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="ACS Triage and ECG Assessment",
        description="12-lead ECG within 10 min, high-sensitivity troponin, risk stratify.",
        mandatory=[
            "order_ecg_12_lead",
            "order_lab_troponin_high_sensitivity",
            "assess_vital_signs",
            "calculate_grace_score",
        ],
        allowed=[
            "order_ecg_12_lead",
            "order_lab_troponin_high_sensitivity",
            "assess_vital_signs",
            "calculate_grace_score",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_lipid_panel",
            "establish_iv_access",
            "place_continuous_cardiac_monitoring",
        ],
        deadlines={
            "order_ecg_12_lead": 10,
            "order_lab_troponin_high_sensitivity": 30,
            "calculate_grace_score": 120,
        },
        source_guideline=src,
        source_section="Initial Assessment",
        source_quote="GRACE score should be used to guide risk stratification in NSTE-ACS.",
        rec_class="I",
        evidence="A",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="action",
        name="Reperfusion and Antithrombotic Therapy",
        description="Dual antiplatelet + anticoagulation; PCI or fibrinolysis per indication.",
        mandatory=[
            "give_aspirin_loading",
            "give_p2y12_inhibitor",
            "initiate_anticoagulation",
        ],
        allowed=[
            "give_aspirin_loading",
            "give_p2y12_inhibitor",
            "initiate_anticoagulation",
            "activate_cath_lab_if_stemi",
            "plan_early_invasive_strategy_if_high_risk",
            "give_fibrinolysis_if_pci_unavailable_and_eligible",
            "give_high_intensity_statin",
            "give_beta_blocker_if_no_contraindication",
            "give_oxygen_if_hypoxemic",
        ],
        forbidden=[
            "give_nsaids_in_acs",
            "give_nitroglycerin_in_rv_infarct",
        ],
        deadlines={
            "give_aspirin_loading": 30,
            "give_p2y12_inhibitor": 60,
            "activate_cath_lab_if_stemi": 30,
        },
        source_guideline=src,
        source_section="Reperfusion",
        source_quote="Primary PCI within 120 minutes is preferred to fibrinolysis for STEMI when available.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Post-ACS Secondary Prevention",
        description="DAPT duration, LV function, cardiac rehabilitation referral.",
        mandatory=[
            "perform_echocardiogram_post_mi",
            "plan_dapt_duration",
            "refer_cardiac_rehabilitation",
        ],
        allowed=[
            "perform_echocardiogram_post_mi",
            "plan_dapt_duration",
            "refer_cardiac_rehabilitation",
            "optimize_secondary_prevention_therapy",
            "reassess_vital_signs",
            "order_lab_troponin_repeat",
            "counsel_lifestyle_modification",
        ],
        deadlines={
            "perform_echocardiogram_post_mi": 2880,
            "plan_dapt_duration": 4320,
        },
        source_guideline=src,
        source_section="Secondary Prevention",
        source_quote="Cardiac rehabilitation should be offered to all patients following ACS.",
        rec_class="I",
        evidence="A",
        next_nodes=[],
    )
    return {
        "graph_id": "sign_acute_coronary_syndrome_2023",
        "guideline_name": src,
        "version": "2023.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Heart",
            "recommendation_system": "SIGN",
            "description": "Scottish ACS management guideline.",
            "key_evidence": "Cardiac rehabilitation reduces cardiovascular mortality post-ACS.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 14. WSES Acute Appendicitis 2020
# =========================================================================


def build_wses_appendicitis_graph() -> dict[str, Any]:
    src = "WSES Jerusalem Acute Appendicitis Guidelines 2020"
    doi = "10.1186/s13017-020-00306-3"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Appendicitis Diagnosis and Risk Score",
        description="Clinical evaluation + Alvarado/AIR score + imaging if uncertain.",
        mandatory=[
            "assess_vital_signs",
            "perform_abdominal_exam",
            "order_lab_cbc",
            "order_lab_crp",
            "calculate_alvarado_or_air_score",
        ],
        allowed=[
            "assess_vital_signs",
            "perform_abdominal_exam",
            "order_lab_cbc",
            "order_lab_crp",
            "calculate_alvarado_or_air_score",
            "order_lab_bmp",
            "order_lab_urinalysis",
            "order_lab_hcg_if_female_of_childbearing_age",
            "order_imaging_abdominal_ultrasound",
            "order_imaging_ct_abdomen_pelvis_if_equivocal",
        ],
        deadlines={
            "assess_vital_signs": 15,
            "order_lab_cbc": 30,
            "calculate_alvarado_or_air_score": 60,
        },
        source_guideline=src,
        source_section="Diagnosis",
        source_quote="Clinical scores combined with imaging improve diagnostic accuracy in suspected appendicitis.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="action",
        name="Antibiotics and Appendectomy Planning",
        description="Preoperative antibiotics; laparoscopic appendectomy preferred; consider NOM for uncomplicated.",
        mandatory=[
            "give_iv_antibiotics_empiric",
            "consult_surgery",
            "plan_appendectomy",
        ],
        allowed=[
            "give_iv_antibiotics_empiric",
            "consult_surgery",
            "plan_appendectomy",
            "plan_laparoscopic_appendectomy",
            "consider_non_operative_management_if_uncomplicated",
            "give_iv_fluids_resuscitation",
            "give_analgesic",
            "give_antiemetic",
            "nothing_by_mouth",
        ],
        forbidden=[
            "delay_surgery_in_perforated_appendicitis",
            "give_oral_antibiotics_only_in_complicated_appendicitis",
        ],
        deadlines={
            "give_iv_antibiotics_empiric": 60,
            "consult_surgery": 120,
            "plan_appendectomy": 480,
        },
        required_prior={
            "plan_appendectomy": ["consult_surgery"],
        },
        source_guideline=src,
        source_section="Treatment",
        source_quote="Laparoscopic appendectomy is recommended as the preferred surgical approach.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Postoperative Recovery Monitoring",
        description="Monitor for surgical site infection, ileus, discharge planning.",
        mandatory=[
            "reassess_vital_signs",
            "monitor_for_surgical_site_infection",
        ],
        allowed=[
            "reassess_vital_signs",
            "monitor_for_surgical_site_infection",
            "order_lab_cbc_repeat",
            "order_lab_crp_repeat",
            "advance_diet_as_tolerated",
            "discontinue_antibiotics_if_uncomplicated",
            "plan_discharge_education",
        ],
        deadlines={
            "reassess_vital_signs": 60,
            "monitor_for_surgical_site_infection": 1440,
        },
        source_guideline=src,
        source_section="Postoperative Care",
        source_quote="Postoperative antibiotics are not required in uncomplicated appendicitis following appendectomy.",
        rec_class="I",
        evidence="A",
        next_nodes=[],
    )
    return {
        "graph_id": "wses_acute_appendicitis_2020",
        "guideline_name": src,
        "version": "2020.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "World Journal of Emergency Surgery",
            "recommendation_system": "WSES",
            "description": "Acute appendicitis diagnosis and management.",
            "key_evidence": "Laparoscopic appendectomy reduces wound infection vs open.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# Graph Builder Registry
# =========================================================================


GRAPH_BUILDERS: dict[str, callable] = {
    "aagbi_perioperative_hemorrhage": build_aagbi_perioperative_hemorrhage_graph,
    "acs_colorectal_cancer": build_acs_colorectal_cancer_graph,
    "aha_acc_pad": build_aha_acc_pad_graph,
    "btf_severe_tbi": build_btf_severe_tbi_graph,
    "eacts_aortic_valve": build_eacts_aortic_valve_graph,
    "eanm_esc_amyloidosis": build_eanm_esc_amyloidosis_graph,
    "esc_acs": build_esc_acs_graph,
    "esc_ie": build_esc_ie_graph,
    "esge_lower_gi_bleed": build_esge_lower_gi_bleed_graph,
    "eucast_ast": build_eucast_ast_graph,
    "ilcor_neonatal": build_ilcor_neonatal_graph,
    "nsclc_molecular": build_nsclc_molecular_graph,
    "sign_acs": build_sign_acs_graph,
    "wses_appendicitis": build_wses_appendicitis_graph,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 Batch 3: Score-16 expansion CPG graphs")
    parser.add_argument("--graph", choices=list(GRAPH_BUILDERS.keys()), help="Generate a single graph")
    parser.add_argument("--dry-run", action="store_true", help="Preview without writing")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR, help="Output directory")
    args = parser.parse_args()

    builders = {args.graph: GRAPH_BUILDERS[args.graph]} if args.graph else GRAPH_BUILDERS

    total_errors = 0
    for name, builder in builders.items():
        print(f"\n--- {name} ---")
        graph = builder()
        errors = validate_graph(graph)
        if errors:
            print("VALIDATION ERRORS:")
            for e in errors:
                print(f"  - {e}")
            total_errors += len(errors)
        else:
            write_graph(graph, args.output_dir, dry_run=args.dry_run)
            print("  Validation: PASS")

    if total_errors:
        print(f"\n{total_errors} total validation errors!")
        raise SystemExit(1)
    else:
        print(f"\nAll {len(builders)} graphs validated and {'previewed' if args.dry_run else 'written'} successfully.")


if __name__ == "__main__":
    main()
