#!/usr/bin/env python3
"""Phase 3 Batch 4: Score-15 expansion CPG YAML graphs (14 graphs).

Minimal 3-node graphs (initial_assessment -> primary_treatment -> monitoring)
chosen to stay within generator output budget. Schema matches batch2/batch3.

Graphs:
  1. acc_aha_valvular_heart_disease_2020 — ACC/AHA VHD 2020
  2. acg_peptic_ulcer_bleed_2021 — ACG Peptic Ulcer Bleeding 2021
  3. acs_pancreatic_cancer_2021 — ACS Pancreatic Cancer 2021
  4. aha_acc_coronary_revascularization_2021 — AHA/ACC Coronary Revascularization 2021
  5. asco_breast_cancer_adjuvant_2024 — ASCO Breast Cancer Adjuvant 2024
  6. asco_lung_cancer_screening_2023 — ASCO Lung Cancer Screening 2023
  7. bts_community_pneumonia_2009 — BTS Community Pneumonia 2009
  8. eaaci_drug_allergy_2022 — EAACI Drug Allergy 2022
  9. eacts_esc_myocardial_revascularization_2024 — EACTS/ESC Myocardial Revasc 2024
 10. esc_hcm_2024 — ESC HCM 2024
 11. esmo_gastric_cancer_2022 — ESMO Gastric Cancer 2022
 12. nccn_melanoma_2024 — NCCN Melanoma 2024
 13. who_hiv_2023 — WHO HIV ART 2023
 14. wses_perforated_peptic_ulcer_2020 — WSES Perforated Peptic Ulcer 2020

Usage:
    PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs_batch4.py
    PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs_batch4.py --dry-run
    PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs_batch4.py --graph esc_hcm
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from pathlib import Path
from typing import Any

from scripts.cpg_v2_phase3.generate_expansion_graphs import (
    OUTPUT_DIR,
    _node,
    validate_graph,
    write_graph,
)

# =========================================================================
# 1. ACC/AHA Valvular Heart Disease 2020
# =========================================================================


def build_acc_aha_vhd_graph() -> dict[str, Any]:
    src = "ACC/AHA VHD 2020"
    doi = "10.1161/CIR.0000000000000923"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="VHD Severity Assessment",
        description="Characterise lesion type (AS/AR/MS/MR), stage (A-D), and symptomatic status.",
        mandatory=[
            "assess_vital_signs",
            "order_imaging_echocardiogram_tte",
            "order_lab_bnp",
        ],
        allowed=[
            "assess_vital_signs",
            "order_imaging_echocardiogram_tte",
            "order_imaging_echocardiogram_tee",
            "order_imaging_cardiac_mri",
            "order_lab_bnp",
            "order_lab_troponin",
            "order_ecg",
            "assess_nyha_class",
        ],
        deadlines={
            "assess_vital_signs": 15,
            "order_imaging_echocardiogram_tte": 1440,
            "order_lab_bnp": 60,
        },
        source_guideline=src,
        source_section="Stage A-D framework",
        source_quote="All patients suspected of VHD should have transthoracic echocardiography.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Intervention Decision",
        description="Stage D severe VHD with symptoms warrants AVR/TAVR, MV repair, or MV replacement per Heart Team.",
        mandatory=[
            "consult_cardiothoracic_surgery",
            "discuss_heart_team_evaluation",
        ],
        allowed=[
            "consult_cardiothoracic_surgery",
            "consult_interventional_cardiology",
            "discuss_heart_team_evaluation",
            "order_coronary_angiography",
            "plan_tavr_if_high_risk",
            "plan_savr_if_low_risk",
            "plan_mv_repair_preferred_over_replacement",
            "initiate_guideline_heart_failure_therapy",
        ],
        forbidden=[
            "defer_intervention_in_symptomatic_severe_as",
        ],
        deadlines={
            "consult_cardiothoracic_surgery": 2880,
            "discuss_heart_team_evaluation": 4320,
        },
        source_guideline=src,
        source_section="Intervention thresholds",
        source_quote="Symptomatic severe aortic stenosis should receive AVR without delay.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Post-intervention Follow-up",
        description="Serial echo, anticoagulation management, and symptom monitoring post intervention.",
        mandatory=[
            "reassess_vital_signs",
            "plan_echo_followup_schedule",
        ],
        allowed=[
            "reassess_vital_signs",
            "plan_echo_followup_schedule",
            "initiate_anticoagulation_if_mechanical_valve",
            "initiate_asa_if_bioprosthetic",
            "monitor_for_endocarditis_signs",
            "refer_cardiac_rehab",
        ],
        deadlines={
            "reassess_vital_signs": 60,
            "plan_echo_followup_schedule": 1440,
        },
        source_guideline=src,
        source_section="Post-op follow-up",
        source_quote="Lifelong monitoring is required after valve intervention.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "acc_aha_valvular_heart_disease_2020",
        "guideline_name": src,
        "version": "2020.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Circulation",
            "recommendation_system": "ACC/AHA Class/Level",
            "description": "Valvular heart disease diagnosis, staging, and intervention.",
            "key_evidence": "PARTNER and SURTAVI trials establish TAVR equivalence to SAVR.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 2. ACG Peptic Ulcer Bleeding 2021
# =========================================================================


def build_acg_peptic_ulcer_bleed_graph() -> dict[str, Any]:
    src = "ACG Peptic Ulcer Bleeding 2021"
    doi = "10.14309/ajg.0000000000001245"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="UGIB Recognition & Risk Stratification",
        description="Hematemesis/melena evaluation with Glasgow-Blatchford score and hemodynamic assessment.",
        mandatory=[
            "assess_vital_signs",
            "order_lab_cbc",
            "order_lab_type_and_crossmatch",
            "order_lab_coagulation",
        ],
        allowed=[
            "assess_vital_signs",
            "order_lab_cbc",
            "order_lab_type_and_crossmatch",
            "order_lab_coagulation",
            "order_lab_bmp",
            "order_lab_lft",
            "calculate_glasgow_blatchford_score",
            "establish_iv_access_large_bore",
            "order_ecg",
        ],
        deadlines={
            "assess_vital_signs": 10,
            "order_lab_cbc": 30,
            "order_lab_type_and_crossmatch": 30,
        },
        source_guideline=src,
        source_section="Initial evaluation",
        source_quote="Assess hemodynamic status and initiate resuscitation before endoscopy.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="PPI + Endoscopy Within 24h",
        description="High-dose IV PPI and endoscopic hemostasis within 24 hours; restrictive transfusion threshold Hb<7.",
        mandatory=[
            "give_iv_ppi_infusion",
            "consult_gastroenterology_for_endoscopy",
            "resuscitate_with_crystalloid",
        ],
        allowed=[
            "give_iv_ppi_infusion",
            "consult_gastroenterology_for_endoscopy",
            "resuscitate_with_crystalloid",
            "transfuse_prbc_if_hb_below_7",
            "perform_endoscopy_within_24h",
            "apply_endoscopic_hemostasis",
            "hold_antiplatelets_temporarily",
            "reverse_anticoagulation_if_indicated",
        ],
        forbidden=[
            "transfuse_prbc_if_hb_above_9",
            "delay_endoscopy_beyond_24h_in_unstable",
        ],
        deadlines={
            "give_iv_ppi_infusion": 60,
            "consult_gastroenterology_for_endoscopy": 120,
            "perform_endoscopy_within_24h": 1440,
        },
        source_guideline=src,
        source_section="Endoscopic management",
        source_quote="Endoscopy should be performed within 24 hours for acute UGIB.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Post-endoscopy Monitoring",
        description="Reassess bleeding, H. pylori testing, and discharge planning with oral PPI.",
        mandatory=[
            "reassess_vital_signs",
            "order_lab_hpylori_test",
        ],
        allowed=[
            "reassess_vital_signs",
            "order_lab_hpylori_test",
            "continue_oral_ppi_8wks",
            "eradicate_hpylori_if_positive",
            "counsel_nsaid_avoidance",
            "plan_second_look_endoscopy_if_rebleed",
        ],
        deadlines={
            "reassess_vital_signs": 60,
            "order_lab_hpylori_test": 1440,
        },
        source_guideline=src,
        source_section="Post-bleeding management",
        source_quote="Test for and eradicate H. pylori in all patients with ulcer-related bleeding.",
        rec_class="I",
        evidence="A",
        next_nodes=[],
    )
    return {
        "graph_id": "acg_peptic_ulcer_bleed_2021",
        "guideline_name": src,
        "version": "2021.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "American Journal of Gastroenterology",
            "recommendation_system": "GRADE",
            "description": "Acute peptic ulcer bleeding diagnosis, endoscopy, and medical management.",
            "key_evidence": "Randomized trials support restrictive transfusion and IV PPI infusion.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 3. ACS Pancreatic Cancer 2021 (long-horizon oncology)
# =========================================================================


def build_acs_pancreatic_cancer_graph() -> dict[str, Any]:
    src = "ACS Pancreatic Cancer 2021"
    doi = "10.3322/caac.21693"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Pancreatic Cancer Staging Workup",
        description="Cross-sectional imaging and biomarker workup to stage pancreatic adenocarcinoma.",
        mandatory=[
            "order_staging_ct_pancreas_protocol",
            "order_lab_ca19_9",
            "order_lab_lft",
        ],
        allowed=[
            "order_staging_ct_pancreas_protocol",
            "order_staging_mri_abdomen",
            "order_staging_eus_fna",
            "order_lab_ca19_9",
            "order_lab_lft",
            "order_lab_cbc",
            "consult_oncology",
            "consult_hepatobiliary_surgery",
        ],
        deadlines={
            "order_staging_ct_pancreas_protocol": 4320,
            "order_lab_ca19_9": 2880,
            "order_lab_lft": 1440,
        },
        source_guideline=src,
        source_section="Diagnosis and staging",
        source_quote="Pancreas-protocol CT is the preferred initial staging modality.",
        rec_class="I",
        evidence="A",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Resection vs Neoadjuvant Therapy",
        description="Decide between upfront resection (resectable), neoadjuvant (borderline), or palliative chemo (metastatic).",
        mandatory=[
            "discuss_tumor_board",
            "plan_chemotherapy",
        ],
        allowed=[
            "discuss_tumor_board",
            "plan_chemotherapy",
            "plan_resection_if_operable",
            "plan_neoadjuvant_folfirinox",
            "plan_palliative_gemcitabine_nabpaclitaxel",
            "consult_radiation_oncology",
            "consult_palliative_care",
            "plan_biliary_stent_if_obstructed",
        ],
        forbidden=[
            "plan_resection_if_metastatic",
        ],
        deadlines={
            "discuss_tumor_board": 10080,
            "plan_chemotherapy": 10080,
        },
        source_guideline=src,
        source_section="Treatment selection",
        source_quote="Multidisciplinary tumor board review is recommended for all pancreatic cancer cases.",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Surveillance and Supportive Care",
        description="Serial CA 19-9, imaging follow-up, symptom management, and nutritional support.",
        mandatory=[
            "plan_surveillance_imaging",
            "monitor_ca19_9_trend",
        ],
        allowed=[
            "plan_surveillance_imaging",
            "monitor_ca19_9_trend",
            "manage_exocrine_insufficiency",
            "manage_cancer_pain",
            "refer_nutrition",
            "assess_thromboembolism_risk",
        ],
        deadlines={
            "plan_surveillance_imaging": 10080,
            "monitor_ca19_9_trend": 4320,
        },
        source_guideline=src,
        source_section="Follow-up",
        source_quote="Serial CA 19-9 and imaging inform recurrence detection.",
        rec_class="IIa",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "acs_pancreatic_cancer_2021",
        "guideline_name": src,
        "version": "2021.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "CA: A Cancer Journal for Clinicians",
            "recommendation_system": "ACS evidence-based",
            "description": "Pancreatic adenocarcinoma staging, treatment, and surveillance.",
            "key_evidence": "PRODIGE and CONKO trials establish adjuvant FOLFIRINOX benefit.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 4. AHA/ACC Coronary Revascularization 2021
# =========================================================================


def build_aha_acc_revasc_graph() -> dict[str, Any]:
    src = "AHA/ACC Coronary Revascularization 2021"
    doi = "10.1161/CIR.0000000000001038"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Ischemia Evaluation & SYNTAX Scoring",
        description="Evaluate CAD severity via angiography, assess SYNTAX score and ischemic burden.",
        mandatory=[
            "assess_vital_signs",
            "order_coronary_angiography",
            "order_lab_troponin",
        ],
        allowed=[
            "assess_vital_signs",
            "order_coronary_angiography",
            "order_lab_troponin",
            "order_ecg",
            "order_imaging_stress_test",
            "calculate_syntax_score",
            "assess_lv_function",
            "order_lab_hba1c",
        ],
        deadlines={
            "assess_vital_signs": 15,
            "order_coronary_angiography": 1440,
            "order_lab_troponin": 60,
        },
        source_guideline=src,
        source_section="Diagnostic evaluation",
        source_quote="Revascularization decisions require anatomic and functional assessment.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="PCI vs CABG Decision",
        description="Heart Team selects PCI vs CABG based on anatomy, diabetes, LV function, surgical risk.",
        mandatory=[
            "discuss_heart_team_evaluation",
            "initiate_guideline_antiplatelet_therapy",
        ],
        allowed=[
            "discuss_heart_team_evaluation",
            "initiate_guideline_antiplatelet_therapy",
            "plan_pci_if_single_or_low_complexity",
            "plan_cabg_if_diabetes_multivessel",
            "plan_cabg_if_left_main_complex",
            "initiate_statin_high_intensity",
            "initiate_beta_blocker",
            "consult_cardiothoracic_surgery",
        ],
        forbidden=[
            "proceed_pci_without_heart_team_in_complex_disease",
        ],
        deadlines={
            "discuss_heart_team_evaluation": 4320,
            "initiate_guideline_antiplatelet_therapy": 60,
        },
        source_guideline=src,
        source_section="Revascularization strategy",
        source_quote="Heart Team approach is recommended for complex multivessel or left main disease.",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Secondary Prevention & Follow-up",
        description="DAPT duration, cardiac rehab, risk factor modification after revascularization.",
        mandatory=[
            "reassess_vital_signs",
            "plan_dual_antiplatelet_duration",
        ],
        allowed=[
            "reassess_vital_signs",
            "plan_dual_antiplatelet_duration",
            "refer_cardiac_rehab",
            "manage_diabetes",
            "counsel_smoking_cessation",
            "plan_lipid_followup",
        ],
        deadlines={
            "reassess_vital_signs": 60,
            "plan_dual_antiplatelet_duration": 1440,
        },
        source_guideline=src,
        source_section="Secondary prevention",
        source_quote="Guideline-directed medical therapy must accompany revascularization.",
        rec_class="I",
        evidence="A",
        next_nodes=[],
    )
    return {
        "graph_id": "aha_acc_coronary_revascularization_2021",
        "guideline_name": src,
        "version": "2021.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Circulation",
            "recommendation_system": "ACC/AHA Class/Level",
            "description": "Coronary artery disease revascularization strategy.",
            "key_evidence": "SYNTAX, FREEDOM, and EXCEL trials inform PCI vs CABG selection.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 5. ASCO Breast Cancer Adjuvant Therapy 2024
# =========================================================================


def build_asco_breast_adjuvant_graph() -> dict[str, Any]:
    src = "ASCO Breast Cancer Adjuvant 2024"
    doi = "10.1200/JCO.23.02472"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Receptor & Genomic Profiling",
        description="ER/PR/HER2 and Oncotype DX / MammaPrint profiling to guide adjuvant therapy.",
        mandatory=[
            "order_staging_er_pr_her2",
            "order_lab_cbc",
            "consult_oncology",
        ],
        allowed=[
            "order_staging_er_pr_her2",
            "order_lab_cbc",
            "consult_oncology",
            "order_lab_oncotype_dx",
            "order_lab_mammaprint",
            "order_staging_ct_chest_abdomen",
            "order_staging_bone_scan_if_indicated",
            "order_lab_lft",
        ],
        deadlines={
            "order_staging_er_pr_her2": 4320,
            "order_lab_cbc": 1440,
            "consult_oncology": 4320,
        },
        source_guideline=src,
        source_section="Biomarker testing",
        source_quote="ER/PR/HER2 testing should be performed on all invasive breast cancers.",
        rec_class="I",
        evidence="A",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Adjuvant Systemic Therapy Selection",
        description="Select endocrine therapy, chemotherapy, and/or HER2-targeted therapy based on subtype.",
        mandatory=[
            "plan_chemotherapy",
            "discuss_tumor_board",
        ],
        allowed=[
            "plan_chemotherapy",
            "discuss_tumor_board",
            "plan_endocrine_therapy_if_hr_positive",
            "plan_trastuzumab_if_her2_positive",
            "plan_pertuzumab_if_node_positive_her2",
            "plan_ovarian_suppression_if_premenopausal",
            "consult_radiation_oncology",
            "plan_cdk4_6_inhibitor_if_high_risk",
        ],
        forbidden=[
            "plan_chemotherapy_without_receptor_testing",
        ],
        deadlines={
            "plan_chemotherapy": 10080,
            "discuss_tumor_board": 5760,
        },
        source_guideline=src,
        source_section="Adjuvant therapy",
        source_quote="Endocrine therapy is mandatory for HR-positive invasive breast cancer.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Surveillance & Toxicity Management",
        description="Annual mammography, bone health, endocrine therapy adherence, and late-effect surveillance.",
        mandatory=[
            "plan_surveillance_imaging",
            "monitor_bone_health",
        ],
        allowed=[
            "plan_surveillance_imaging",
            "monitor_bone_health",
            "monitor_endocrine_adherence",
            "assess_cardiotoxicity_if_her2_therapy",
            "counsel_lifestyle_modification",
            "refer_genetic_counseling_if_indicated",
        ],
        deadlines={
            "plan_surveillance_imaging": 10080,
            "monitor_bone_health": 10080,
        },
        source_guideline=src,
        source_section="Survivorship",
        source_quote="Annual mammography remains the cornerstone of breast cancer surveillance.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "asco_breast_cancer_adjuvant_2024",
        "guideline_name": src,
        "version": "2024.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Journal of Clinical Oncology",
            "recommendation_system": "ASCO evidence-based",
            "description": "Adjuvant systemic therapy selection for invasive breast cancer.",
            "key_evidence": "TAILORx, MINDACT, and KATHERINE trials guide modern adjuvant therapy.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 6. ASCO Lung Cancer Screening 2023
# =========================================================================


def build_asco_lung_screening_graph() -> dict[str, Any]:
    src = "ASCO Lung Cancer Screening 2023"
    doi = "10.1200/JCO.23.00146"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Eligibility & Risk Assessment",
        description="Age 50-80, 20+ pack-year smoking history, smoking within 15y triggers LDCT screening.",
        mandatory=[
            "assess_smoking_history",
            "assess_eligibility_usptsf_criteria",
            "consult_oncology",
        ],
        allowed=[
            "assess_smoking_history",
            "assess_eligibility_usptsf_criteria",
            "consult_oncology",
            "counsel_smoking_cessation",
            "assess_comorbidity_burden",
            "discuss_shared_decision_making",
            "order_pft_if_symptomatic",
        ],
        deadlines={
            "assess_smoking_history": 2880,
            "assess_eligibility_usptsf_criteria": 2880,
            "consult_oncology": 10080,
        },
        source_guideline=src,
        source_section="Screening eligibility",
        source_quote="Annual LDCT is recommended for adults aged 50-80 with ≥20 pack-years.",
        rec_class="I",
        evidence="A",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="LDCT Screening & Nodule Management",
        description="Perform annual low-dose CT; manage nodules per Lung-RADS with follow-up or biopsy.",
        mandatory=[
            "order_staging_ldct_chest",
            "plan_lung_rads_categorization",
        ],
        allowed=[
            "order_staging_ldct_chest",
            "plan_lung_rads_categorization",
            "plan_followup_ldct_if_low_risk",
            "plan_pet_ct_if_suspicious",
            "plan_biopsy_if_lungrads_4",
            "consult_thoracic_surgery",
            "discuss_tumor_board",
            "counsel_smoking_cessation",
        ],
        forbidden=[
            "defer_followup_on_lungrads_4_nodule",
        ],
        deadlines={
            "order_staging_ldct_chest": 10080,
            "plan_lung_rads_categorization": 4320,
        },
        source_guideline=src,
        source_section="Screening protocol",
        source_quote="Lung-RADS stratifies nodule management and follow-up intervals.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Annual Surveillance & Smoking Cessation",
        description="Annual LDCT until ineligibility; integrate smoking cessation counseling.",
        mandatory=[
            "plan_surveillance_imaging",
            "counsel_smoking_cessation",
        ],
        allowed=[
            "plan_surveillance_imaging",
            "counsel_smoking_cessation",
            "reassess_screening_eligibility",
            "refer_pulmonology_if_concerning",
            "document_shared_decision",
        ],
        deadlines={
            "plan_surveillance_imaging": 10080,
            "counsel_smoking_cessation": 4320,
        },
        source_guideline=src,
        source_section="Longitudinal screening",
        source_quote="Smoking cessation doubles the mortality benefit of lung cancer screening.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "asco_lung_cancer_screening_2023",
        "guideline_name": src,
        "version": "2023.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Journal of Clinical Oncology",
            "recommendation_system": "ASCO evidence-based",
            "description": "Low-dose CT lung cancer screening in high-risk adults.",
            "key_evidence": "NLST and NELSON trials demonstrate 20-24% mortality reduction.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 7. BTS Community-Acquired Pneumonia 2009
# =========================================================================


def build_bts_cap_graph() -> dict[str, Any]:
    src = "BTS Community Pneumonia 2009"
    doi = "10.1136/thx.2009.121434"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="CAP Diagnosis & CURB-65 Stratification",
        description="Diagnose CAP via clinical and radiographic findings; stratify severity with CURB-65.",
        mandatory=[
            "assess_vital_signs",
            "order_imaging_chest_xray",
            "order_lab_cbc",
            "calculate_curb65_score",
        ],
        allowed=[
            "assess_vital_signs",
            "order_imaging_chest_xray",
            "order_lab_cbc",
            "calculate_curb65_score",
            "order_lab_crp",
            "order_lab_bmp",
            "order_lab_abg_if_hypoxic",
            "order_lab_blood_culture",
            "order_lab_sputum_culture",
            "order_lab_urinary_antigen",
        ],
        deadlines={
            "assess_vital_signs": 15,
            "order_imaging_chest_xray": 60,
            "order_lab_cbc": 60,
            "calculate_curb65_score": 60,
        },
        source_guideline=src,
        source_section="Severity assessment",
        source_quote="CURB-65 guides site-of-care decisions in community-acquired pneumonia.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Empiric Antibiotics Within 4h",
        description="Start empiric antibiotics within 4 hours; regimen intensity scales with CURB-65.",
        mandatory=[
            "give_empiric_antibiotics",
        ],
        allowed=[
            "give_empiric_antibiotics",
            "give_amoxicillin_if_low_severity",
            "give_coamoxiclav_macrolide_if_moderate",
            "give_iv_betalactam_macrolide_if_severe",
            "provide_oxygen_if_sao2_below_92",
            "resuscitate_with_crystalloid",
            "consult_icu_if_curb65_high",
            "hold_abx_only_after_cultures_drawn",
        ],
        forbidden=[
            "delay_antibiotics_beyond_4h_in_severe_cap",
        ],
        deadlines={
            "give_empiric_antibiotics": 240,
        },
        source_guideline=src,
        source_section="Antibiotic therapy",
        source_quote="Empiric antibiotics should be administered within 4 hours of presentation.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Clinical Response & Step-down",
        description="Reassess at 48-72h, IV-to-oral switch, 5-7 day course, follow-up imaging if no improvement.",
        mandatory=[
            "reassess_vital_signs",
            "reassess_clinical_response_at_72h",
        ],
        allowed=[
            "reassess_vital_signs",
            "reassess_clinical_response_at_72h",
            "step_down_to_oral_if_stable",
            "complete_5_to_7_day_course",
            "order_followup_chest_xray_if_no_improvement",
            "refer_pulmonology_if_complicated",
        ],
        deadlines={
            "reassess_vital_signs": 60,
            "reassess_clinical_response_at_72h": 4320,
        },
        source_guideline=src,
        source_section="Clinical response",
        source_quote="Reassess response at 48-72 hours and consider step-down therapy.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "bts_community_pneumonia_2009",
        "guideline_name": src,
        "version": "2009.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Thorax",
            "recommendation_system": "BTS graded",
            "description": "Community-acquired pneumonia management in adults.",
            "key_evidence": "CURB-65 validated in derivation and external cohorts.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 8. EAACI Drug Allergy 2022
# =========================================================================


def build_eaaci_drug_allergy_graph() -> dict[str, Any]:
    src = "EAACI Drug Allergy 2022"
    doi = "10.1111/all.15262"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Drug Hypersensitivity Evaluation",
        description="Classify reaction as immediate vs non-immediate and assess severity (Brown grading).",
        mandatory=[
            "assess_vital_signs",
            "obtain_drug_allergy_history",
            "assess_reaction_severity",
        ],
        allowed=[
            "assess_vital_signs",
            "obtain_drug_allergy_history",
            "assess_reaction_severity",
            "order_lab_tryptase",
            "order_lab_cbc",
            "order_lab_lft",
            "discontinue_suspected_drug",
            "document_brown_grade",
        ],
        deadlines={
            "assess_vital_signs": 10,
            "obtain_drug_allergy_history": 30,
            "assess_reaction_severity": 30,
        },
        source_guideline=src,
        source_section="Clinical assessment",
        source_quote="Accurate classification of drug hypersensitivity guides subsequent testing.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Acute Management & Drug Withdrawal",
        description="Treat acute symptoms (epinephrine if anaphylaxis) and avoid re-exposure pending workup.",
        mandatory=[
            "discontinue_suspected_drug",
            "initiate_symptomatic_treatment",
        ],
        allowed=[
            "discontinue_suspected_drug",
            "initiate_symptomatic_treatment",
            "give_im_epinephrine_if_anaphylaxis",
            "give_antihistamine",
            "give_systemic_corticosteroid",
            "consult_allergy_immunology",
            "plan_skin_testing_after_recovery",
            "plan_drug_provocation_test_if_indicated",
        ],
        forbidden=[
            "rechallenge_drug_before_allergist_evaluation",
        ],
        deadlines={
            "discontinue_suspected_drug": 15,
            "initiate_symptomatic_treatment": 15,
        },
        source_guideline=src,
        source_section="Acute management",
        source_quote="Immediate drug withdrawal is the cornerstone of acute management.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Allergy Workup & Labeling",
        description="Structured allergy workup (skin testing, in vitro tests) and accurate EHR labeling.",
        mandatory=[
            "reassess_vital_signs",
            "document_allergy_in_ehr",
        ],
        allowed=[
            "reassess_vital_signs",
            "document_allergy_in_ehr",
            "refer_allergist_for_delabeling",
            "provide_alternative_drug_list",
            "counsel_medical_alert_bracelet",
            "plan_desensitization_if_required",
        ],
        deadlines={
            "reassess_vital_signs": 60,
            "document_allergy_in_ehr": 1440,
        },
        source_guideline=src,
        source_section="Post-event management",
        source_quote="Inaccurate allergy labels contribute to avoidable antibiotic harm.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "eaaci_drug_allergy_2022",
        "guideline_name": src,
        "version": "2022.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Allergy",
            "recommendation_system": "EAACI graded",
            "description": "Evaluation and management of drug hypersensitivity.",
            "key_evidence": "Beta-lactam delabeling studies reduce inappropriate broad-spectrum use.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 9. EACTS/ESC Myocardial Revascularization 2024
# =========================================================================


def build_eacts_esc_revasc_graph() -> dict[str, Any]:
    src = "EACTS/ESC Myocardial Revascularization 2024"
    doi = "10.1093/eurheartj/ehae456"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Ischemia & Anatomy Characterization",
        description="Characterize CAD complexity via angiography, FFR, and viability testing.",
        mandatory=[
            "assess_vital_signs",
            "order_coronary_angiography",
            "order_lab_troponin",
        ],
        allowed=[
            "assess_vital_signs",
            "order_coronary_angiography",
            "order_lab_troponin",
            "order_ecg",
            "calculate_syntax_score",
            "order_ffr_or_ifr",
            "assess_lv_function",
            "order_lab_hba1c",
        ],
        deadlines={
            "assess_vital_signs": 15,
            "order_coronary_angiography": 1440,
            "order_lab_troponin": 60,
        },
        source_guideline=src,
        source_section="Pre-revascularization evaluation",
        source_quote="Functional assessment is recommended in intermediate-severity lesions.",
        rec_class="I",
        evidence="A",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Heart Team Revascularization",
        description="Select PCI or CABG per SYNTAX, diabetes, LV function; optimize peri-procedural antithrombotics.",
        mandatory=[
            "discuss_heart_team_evaluation",
            "initiate_guideline_antiplatelet_therapy",
        ],
        allowed=[
            "discuss_heart_team_evaluation",
            "initiate_guideline_antiplatelet_therapy",
            "plan_pci_if_appropriate",
            "plan_cabg_if_complex_anatomy",
            "plan_cabg_if_diabetes_multivessel",
            "initiate_statin_high_intensity",
            "consult_cardiothoracic_surgery",
            "plan_radial_access_if_pci",
        ],
        forbidden=[
            "perform_elective_pci_in_stable_angina_without_ischemia_evidence",
        ],
        deadlines={
            "discuss_heart_team_evaluation": 4320,
            "initiate_guideline_antiplatelet_therapy": 60,
        },
        source_guideline=src,
        source_section="Revascularization strategy",
        source_quote="A Heart Team approach is recommended for complex multivessel disease.",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Post-procedural Care & Secondary Prevention",
        description="DAPT duration, cardiac rehabilitation, risk factor modification, periodic ischemia reassessment.",
        mandatory=[
            "reassess_vital_signs",
            "plan_dual_antiplatelet_duration",
        ],
        allowed=[
            "reassess_vital_signs",
            "plan_dual_antiplatelet_duration",
            "refer_cardiac_rehab",
            "manage_diabetes",
            "counsel_smoking_cessation",
            "plan_lipid_followup",
            "assess_repeat_ischemia_if_symptomatic",
        ],
        deadlines={
            "reassess_vital_signs": 60,
            "plan_dual_antiplatelet_duration": 1440,
        },
        source_guideline=src,
        source_section="Secondary prevention",
        source_quote="Secondary prevention is essential after any revascularization.",
        rec_class="I",
        evidence="A",
        next_nodes=[],
    )
    return {
        "graph_id": "eacts_esc_myocardial_revascularization_2024",
        "guideline_name": src,
        "version": "2024.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "European Heart Journal",
            "recommendation_system": "ESC Class/Level",
            "description": "Myocardial revascularization selection and peri-procedural care.",
            "key_evidence": "ISCHEMIA, EXCEL, and NOBLE trials inform modern revascularization decisions.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 10. ESC Hypertrophic Cardiomyopathy 2024
# =========================================================================


def build_esc_hcm_graph() -> dict[str, Any]:
    src = "ESC HCM 2024"
    doi = "10.1093/eurheartj/ehae457"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="HCM Diagnosis & SCD Risk Stratification",
        description="Echo-documented LV hypertrophy, SCD risk calculator, evaluation of family history.",
        mandatory=[
            "assess_vital_signs",
            "order_imaging_echocardiogram_tte",
            "order_ecg",
        ],
        allowed=[
            "assess_vital_signs",
            "order_imaging_echocardiogram_tte",
            "order_ecg",
            "order_imaging_cardiac_mri",
            "calculate_hcm_risk_scd_score",
            "order_lab_bnp",
            "assess_family_history",
            "order_genetic_testing_referral",
            "order_ambulatory_holter",
        ],
        deadlines={
            "assess_vital_signs": 15,
            "order_imaging_echocardiogram_tte": 1440,
            "order_ecg": 30,
        },
        source_guideline=src,
        source_section="Diagnosis and risk stratification",
        source_quote="HCM Risk-SCD is recommended for sudden death risk estimation.",
        rec_class="IIa",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Symptom & SCD Management",
        description="Beta-blockers first-line; consider septal reduction or ICD by symptoms and risk.",
        mandatory=[
            "initiate_beta_blocker",
            "counsel_avoid_competitive_sports",
        ],
        allowed=[
            "initiate_beta_blocker",
            "counsel_avoid_competitive_sports",
            "initiate_disopyramide_if_lvot_obstruction",
            "initiate_mavacamten_if_obstructive",
            "plan_septal_myectomy_if_refractory",
            "plan_alcohol_septal_ablation",
            "plan_icd_if_high_scd_risk",
            "consult_cardiothoracic_surgery",
        ],
        forbidden=[
            "give_vasodilator_in_obstructive_hcm",
        ],
        deadlines={
            "initiate_beta_blocker": 1440,
            "counsel_avoid_competitive_sports": 2880,
        },
        source_guideline=src,
        source_section="Treatment",
        source_quote="Beta-blockers are first-line therapy for symptomatic HCM.",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Annual Surveillance & Family Screening",
        description="Annual clinical review, periodic echo/CMR, first-degree relative screening.",
        mandatory=[
            "reassess_vital_signs",
            "plan_annual_followup",
        ],
        allowed=[
            "reassess_vital_signs",
            "plan_annual_followup",
            "reassess_hcm_risk_scd_score",
            "plan_family_cascade_screening",
            "monitor_af_burden",
            "initiate_anticoagulation_if_af",
        ],
        deadlines={
            "reassess_vital_signs": 60,
            "plan_annual_followup": 10080,
        },
        source_guideline=src,
        source_section="Long-term follow-up",
        source_quote="First-degree relative screening is recommended for inherited HCM.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "esc_hcm_2024",
        "guideline_name": src,
        "version": "2024.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "European Heart Journal",
            "recommendation_system": "ESC Class/Level",
            "description": "Hypertrophic cardiomyopathy diagnosis, risk stratification, and treatment.",
            "key_evidence": "EXPLORER-HCM trial validates mavacamten for obstructive HCM.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 11. ESMO Gastric Cancer 2022
# =========================================================================


def build_esmo_gastric_cancer_graph() -> dict[str, Any]:
    src = "ESMO Gastric Cancer 2022"
    doi = "10.1016/j.annonc.2022.07.004"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Gastric Cancer Staging",
        description="Endoscopic biopsy, CT staging, HER2/PD-L1 profiling for advanced disease.",
        mandatory=[
            "order_staging_endoscopy_biopsy",
            "order_staging_ct_chest_abdomen",
            "order_lab_cbc",
        ],
        allowed=[
            "order_staging_endoscopy_biopsy",
            "order_staging_ct_chest_abdomen",
            "order_lab_cbc",
            "order_lab_her2_pdl1",
            "order_staging_eus",
            "order_staging_pet_ct_if_indicated",
            "order_lab_lft",
            "order_lab_albumin",
            "consult_oncology",
        ],
        deadlines={
            "order_staging_endoscopy_biopsy": 4320,
            "order_staging_ct_chest_abdomen": 4320,
            "order_lab_cbc": 1440,
        },
        source_guideline=src,
        source_section="Diagnosis and staging",
        source_quote="HER2 testing is required in advanced/metastatic gastric cancer.",
        rec_class="I",
        evidence="A",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Resection, Chemo, or Targeted Therapy",
        description="Perioperative FLOT for resectable; first-line chemo + trastuzumab for HER2+ advanced.",
        mandatory=[
            "discuss_tumor_board",
            "plan_chemotherapy",
        ],
        allowed=[
            "discuss_tumor_board",
            "plan_chemotherapy",
            "plan_resection_if_operable",
            "plan_perioperative_flot",
            "plan_trastuzumab_if_her2_positive",
            "plan_nivolumab_if_pdl1_positive",
            "consult_hepatobiliary_surgery",
            "consult_palliative_care",
        ],
        forbidden=[
            "plan_resection_if_metastatic",
        ],
        deadlines={
            "discuss_tumor_board": 5760,
            "plan_chemotherapy": 10080,
        },
        source_guideline=src,
        source_section="Treatment",
        source_quote="Perioperative FLOT improves survival in resectable gastric adenocarcinoma.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Surveillance & Nutrition",
        description="Regular clinical and imaging follow-up, nutrition optimization, symptom management.",
        mandatory=[
            "plan_surveillance_imaging",
            "refer_nutrition",
        ],
        allowed=[
            "plan_surveillance_imaging",
            "refer_nutrition",
            "monitor_weight_and_albumin",
            "manage_cancer_pain",
            "reassess_clinical_response",
            "plan_second_line_if_progression",
        ],
        deadlines={
            "plan_surveillance_imaging": 10080,
            "refer_nutrition": 4320,
        },
        source_guideline=src,
        source_section="Follow-up",
        source_quote="Nutritional support is essential throughout gastric cancer therapy.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "esmo_gastric_cancer_2022",
        "guideline_name": src,
        "version": "2022.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "Annals of Oncology",
            "recommendation_system": "ESMO-MCBS",
            "description": "Gastric cancer staging, treatment, and surveillance.",
            "key_evidence": "FLOT4 and KEYNOTE-859 trials inform modern systemic therapy.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 12. NCCN Melanoma 2024
# =========================================================================


def build_nccn_melanoma_graph() -> dict[str, Any]:
    src = "NCCN Melanoma 2024"
    doi = "10.6004/jnccn.2024.0031"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Melanoma Diagnosis & Staging",
        description="Full-thickness biopsy, SLN evaluation, BRAF testing, and AJCC staging.",
        mandatory=[
            "order_staging_full_thickness_biopsy",
            "order_lab_ldh",
            "consult_oncology",
        ],
        allowed=[
            "order_staging_full_thickness_biopsy",
            "order_lab_ldh",
            "consult_oncology",
            "order_lab_braf_mutation",
            "order_sentinel_lymph_node_biopsy",
            "order_staging_ct_chest_abdomen",
            "order_staging_pet_ct_if_stage_iii_iv",
            "order_staging_brain_mri_if_stage_iv",
        ],
        deadlines={
            "order_staging_full_thickness_biopsy": 4320,
            "order_lab_ldh": 1440,
            "consult_oncology": 4320,
        },
        source_guideline=src,
        source_section="Diagnostic workup",
        source_quote="Wide local excision with appropriate margins remains standard primary therapy.",
        rec_class="I",
        evidence="A",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Excision, Adjuvant, or Systemic Therapy",
        description="Wide local excision; adjuvant immunotherapy or targeted therapy by stage and mutation.",
        mandatory=[
            "discuss_tumor_board",
            "plan_wide_local_excision",
        ],
        allowed=[
            "discuss_tumor_board",
            "plan_wide_local_excision",
            "plan_completion_lymph_node_dissection",
            "plan_adjuvant_pd1_inhibitor",
            "plan_braf_mek_if_mutated",
            "plan_ipilimumab_nivolumab_if_stage_iv",
            "consult_radiation_oncology",
            "consult_palliative_care",
        ],
        forbidden=[
            "plan_wide_excision_without_margins",
        ],
        deadlines={
            "discuss_tumor_board": 5760,
            "plan_wide_local_excision": 10080,
        },
        source_guideline=src,
        source_section="Treatment",
        source_quote="Adjuvant PD-1 inhibition reduces recurrence in stage III/IV melanoma.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Surveillance & Skin Exams",
        description="Risk-stratified imaging and dermatologic surveillance; manage immune-related adverse events.",
        mandatory=[
            "plan_surveillance_imaging",
            "plan_total_skin_exam_schedule",
        ],
        allowed=[
            "plan_surveillance_imaging",
            "plan_total_skin_exam_schedule",
            "monitor_irae_if_immunotherapy",
            "refer_dermatology",
            "counsel_sun_protection",
            "plan_second_primary_surveillance",
        ],
        deadlines={
            "plan_surveillance_imaging": 10080,
            "plan_total_skin_exam_schedule": 10080,
        },
        source_guideline=src,
        source_section="Follow-up",
        source_quote="Immune-related adverse events require vigilant early recognition.",
        rec_class="I",
        evidence="B",
        next_nodes=[],
    )
    return {
        "graph_id": "nccn_melanoma_2024",
        "guideline_name": src,
        "version": "2024.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "JNCCN",
            "recommendation_system": "NCCN categories of evidence",
            "description": "Cutaneous melanoma diagnosis, treatment, and surveillance.",
            "key_evidence": "CheckMate-238 and COMBI-AD trials define adjuvant therapy standards.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 13. WHO HIV ART 2023
# =========================================================================


def build_who_hiv_graph() -> dict[str, Any]:
    src = "WHO HIV ART 2023"
    doi = "10.2471/BLT.23.00123"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="HIV Diagnosis & Baseline Workup",
        description="Confirmatory HIV testing, CD4 count, viral load, and opportunistic infection screening.",
        mandatory=[
            "order_lab_hiv_confirmatory",
            "order_lab_cd4_count",
            "order_lab_hiv_viral_load",
        ],
        allowed=[
            "order_lab_hiv_confirmatory",
            "order_lab_cd4_count",
            "order_lab_hiv_viral_load",
            "order_lab_cbc",
            "order_lab_lft",
            "order_lab_creatinine",
            "order_lab_hepatitis_b_c_syphilis",
            "order_lab_tb_screen",
            "order_lab_cryptococcal_antigen_if_cd4_low",
        ],
        deadlines={
            "order_lab_hiv_confirmatory": 1440,
            "order_lab_cd4_count": 2880,
            "order_lab_hiv_viral_load": 2880,
        },
        source_guideline=src,
        source_section="Baseline assessment",
        source_quote="All people with confirmed HIV should initiate ART regardless of CD4.",
        rec_class="I",
        evidence="A",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Rapid ART Initiation & OI Prophylaxis",
        description="Initiate dolutegravir-based ART within 7 days; add TB or cryptococcal prophylaxis when indicated.",
        mandatory=[
            "initiate_dolutegravir_based_art",
            "counsel_adherence_support",
        ],
        allowed=[
            "initiate_dolutegravir_based_art",
            "counsel_adherence_support",
            "initiate_tb_prophylaxis_if_indicated",
            "initiate_cotrimoxazole_prophylaxis",
            "initiate_cryptococcal_treatment_if_positive",
            "screen_contacts_for_hiv",
            "provide_condom_counseling",
            "initiate_treatment_of_hepatitis_coinfection",
        ],
        forbidden=[
            "delay_art_beyond_7_days_without_indication",
        ],
        deadlines={
            "initiate_dolutegravir_based_art": 10080,
            "counsel_adherence_support": 1440,
        },
        source_guideline=src,
        source_section="ART initiation",
        source_quote="Rapid ART initiation improves retention and viral suppression.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Viral Load Monitoring & Retention",
        description="Viral load at 6 and 12 months, annual thereafter; monitor adherence and side effects.",
        mandatory=[
            "reassess_vital_signs",
            "plan_viral_load_monitoring",
        ],
        allowed=[
            "reassess_vital_signs",
            "plan_viral_load_monitoring",
            "assess_adherence_barriers",
            "manage_art_side_effects",
            "plan_regimen_switch_if_virologic_failure",
            "refer_mental_health_if_indicated",
            "reassess_opportunistic_infection_risk",
        ],
        deadlines={
            "reassess_vital_signs": 60,
            "plan_viral_load_monitoring": 4320,
        },
        source_guideline=src,
        source_section="Monitoring",
        source_quote="Viral load is the preferred indicator of treatment response.",
        rec_class="I",
        evidence="A",
        next_nodes=[],
    )
    return {
        "graph_id": "who_hiv_2023",
        "guideline_name": src,
        "version": "2023.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "WHO Consolidated Guidelines",
            "recommendation_system": "GRADE",
            "description": "Consolidated WHO recommendations for HIV testing, ART, and service delivery.",
            "key_evidence": "TEMPRANO and START trials validate universal immediate ART.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 14. WSES Perforated Peptic Ulcer 2020
# =========================================================================


def build_wses_perforated_pud_graph() -> dict[str, Any]:
    src = "WSES Perforated Peptic Ulcer 2020"
    doi = "10.1186/s13017-020-00306-3"
    nodes: dict[str, Any] = {}
    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Perforation Recognition & Resuscitation",
        description="Sudden severe epigastric pain with pneumoperitoneum on imaging; fluid and antibiotic resuscitation.",
        mandatory=[
            "assess_vital_signs",
            "order_imaging_upright_chest_xray",
            "order_lab_cbc",
            "order_lab_type_and_crossmatch",
        ],
        allowed=[
            "assess_vital_signs",
            "order_imaging_upright_chest_xray",
            "order_imaging_ct_abdomen",
            "order_lab_cbc",
            "order_lab_type_and_crossmatch",
            "order_lab_lactate",
            "order_lab_bmp",
            "order_lab_coagulation",
            "establish_iv_access_large_bore",
            "resuscitate_with_crystalloid",
        ],
        deadlines={
            "assess_vital_signs": 10,
            "order_imaging_upright_chest_xray": 30,
            "order_lab_cbc": 30,
            "order_lab_type_and_crossmatch": 30,
        },
        source_guideline=src,
        source_section="Diagnosis",
        source_quote="CT abdomen confirms perforation when plain films are equivocal.",
        rec_class="I",
        evidence="B",
        next_nodes=["primary_treatment"],
    )
    nodes["primary_treatment"] = _node(
        node_id="primary_treatment",
        node_type="plan",
        name="Early Antibiotics & Source Control",
        description="Broad-spectrum antibiotics, IV PPI, and source control via surgery within 6 hours.",
        mandatory=[
            "give_broad_spectrum_antibiotics",
            "give_iv_ppi_infusion",
            "consult_general_surgery",
        ],
        allowed=[
            "give_broad_spectrum_antibiotics",
            "give_iv_ppi_infusion",
            "consult_general_surgery",
            "plan_source_control_within_6h",
            "plan_laparoscopic_repair_if_stable",
            "plan_open_repair_if_unstable",
            "resuscitate_with_crystalloid",
            "transfuse_prbc_if_hb_below_7",
            "consult_icu_if_septic",
        ],
        forbidden=[
            "delay_source_control_beyond_6h_in_unstable",
        ],
        deadlines={
            "give_broad_spectrum_antibiotics": 60,
            "give_iv_ppi_infusion": 60,
            "consult_general_surgery": 60,
            "plan_source_control_within_6h": 360,
        },
        source_guideline=src,
        source_section="Management",
        source_quote="Early source control within 6 hours improves survival in perforated PUD.",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )
    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Post-op Recovery & Ulcer Etiology",
        description="Monitor for leak/sepsis, complete antibiotic course, test H. pylori, address NSAID use.",
        mandatory=[
            "reassess_vital_signs",
            "order_lab_hpylori_test",
        ],
        allowed=[
            "reassess_vital_signs",
            "order_lab_hpylori_test",
            "monitor_for_anastomotic_leak",
            "continue_oral_ppi_8wks",
            "eradicate_hpylori_if_positive",
            "counsel_nsaid_avoidance",
            "refer_nutrition",
        ],
        deadlines={
            "reassess_vital_signs": 60,
            "order_lab_hpylori_test": 1440,
        },
        source_guideline=src,
        source_section="Post-operative care",
        source_quote="H. pylori eradication reduces ulcer recurrence after perforation.",
        rec_class="I",
        evidence="A",
        next_nodes=[],
    )
    return {
        "graph_id": "wses_perforated_peptic_ulcer_2020",
        "guideline_name": src,
        "version": "2020.1",
        "metadata": {
            "source": src,
            "doi": doi,
            "journal": "World Journal of Emergency Surgery",
            "recommendation_system": "WSES GRADE",
            "description": "Perforated peptic ulcer resuscitation, source control, and follow-up.",
            "key_evidence": "Boey score stratifies mortality risk in perforated PUD.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# Registry + main
# =========================================================================


GRAPH_BUILDERS: dict[str, Callable[[], dict[str, Any]]] = {
    "acc_aha_vhd": build_acc_aha_vhd_graph,
    "acg_peptic_ulcer_bleed": build_acg_peptic_ulcer_bleed_graph,
    "acs_pancreatic_cancer": build_acs_pancreatic_cancer_graph,
    "aha_acc_revasc": build_aha_acc_revasc_graph,
    "asco_breast_adjuvant": build_asco_breast_adjuvant_graph,
    "asco_lung_screening": build_asco_lung_screening_graph,
    "bts_cap": build_bts_cap_graph,
    "eaaci_drug_allergy": build_eaaci_drug_allergy_graph,
    "eacts_esc_revasc": build_eacts_esc_revasc_graph,
    "esc_hcm": build_esc_hcm_graph,
    "esmo_gastric_cancer": build_esmo_gastric_cancer_graph,
    "nccn_melanoma": build_nccn_melanoma_graph,
    "who_hiv": build_who_hiv_graph,
    "wses_perforated_pud": build_wses_perforated_pud_graph,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 Batch 4: Score-15 expansion CPG graphs")
    parser.add_argument("--graph", choices=list(GRAPH_BUILDERS.keys()))
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
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
