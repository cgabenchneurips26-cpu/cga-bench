#!/usr/bin/env python3
"""Phase 3 Batch 2: Score-17 expansion CPG YAML graphs (10 graphs).

Graphs:
  1. eau_obstructive_pyelonephritis_2024 — EAU Obstructive Pyelonephritis
  2. erc_drowning_2021 — ERC Drowning Resuscitation
  3. ers_ats_niv_2017 — ERS/ATS NIV in Acute Respiratory Failure
  4. gina_pediatric_status_asthma_2024 — GINA Severe Pediatric Asthma
  5. hrs_vt_sd_2017 — HRS Ventricular Arrhythmias & Sudden Death
  6. idsa_cdi_2021 — IDSA/SHEA C. difficile Infection
  7. isth_ash_ttp_2020 — ISTH/ASH Thrombotic Thrombocytopenic Purpura
  8. sccm_rsi_2019 — SCCM Rapid Sequence Intubation
  9. smfm_maternal_sepsis_2019 — SMFM/ACOG Maternal Sepsis
 10. wses_pelvic_trauma_reboa_2017 — WSES Pelvic Trauma & REBOA

Usage:
    PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs_batch2.py
    PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs_batch2.py --dry-run
    PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs_batch2.py --graph ttp
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
# 1. Obstructive Pyelonephritis (EAU 2024)
# =========================================================================


def build_obstructive_pyelonephritis_graph() -> dict[str, Any]:
    """EAU 2024 Urological Infections — Obstructive Pyelonephritis graph."""
    src = "EAU Urological Infections Guidelines 2024"
    doi = "10.1016/j.eururo.2024.02.005"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Obstructive Pyelonephritis Recognition & Sepsis Screen",
        description=(
            "Identify obstructive pyelonephritis: flank pain, fever, pyuria "
            "with hydronephrosis on imaging. Screen for urosepsis using qSOFA/SIRS."
        ),
        mandatory=[
            "assess_vital_signs",
            "order_lab_urinalysis_culture",
            "order_lab_blood_culture",
            "order_lab_cbc",
            "order_lab_creatinine",
        ],
        allowed=[
            "assess_vital_signs",
            "order_lab_urinalysis_culture",
            "order_lab_blood_culture",
            "order_lab_cbc",
            "order_lab_creatinine",
            "order_lab_lactate",
            "order_lab_bmp",
            "order_lab_procalcitonin",
            "order_lab_coagulation",
            "establish_iv_access",
        ],
        deadlines={
            "assess_vital_signs": 10,
            "order_lab_urinalysis_culture": 30,
            "order_lab_blood_culture": 30,
        },
        source_guideline=src,
        source_section="3.4.3 Complicated UTI / Obstructive Pyelonephritis",
        source_quote=(
            "Obstructive pyelonephritis is a urological emergency. "
            "Blood cultures and urine cultures should be obtained before antibiotics."
        ),
        next_nodes=["empiric_antibiotics"],
    )

    nodes["empiric_antibiotics"] = _node(
        node_id="empiric_antibiotics",
        node_type="action",
        name="Empiric IV Antibiotics Within 1 Hour",
        description=(
            "Administer broad-spectrum IV antibiotics within 1 hour of recognition "
            "for suspected urosepsis. Ceftriaxone or piperacillin-tazobactam are first-line."
        ),
        mandatory=[
            "give_iv_antibiotics_empiric",
        ],
        allowed=[
            "give_iv_antibiotics_empiric",
            "give_ceftriaxone_iv",
            "give_piperacillin_tazobactam_iv",
            "give_meropenem_iv_if_esbl",
            "give_iv_fluids_resuscitation",
            "give_analgesic",
        ],
        forbidden=["give_oral_antibiotics_only"],
        deadlines={
            "give_iv_antibiotics_empiric": 60,
        },
        required_prior={"give_iv_antibiotics_empiric": "order_lab_blood_culture"},
        source_guideline=src,
        source_section="3.4.7 Antimicrobial Therapy",
        source_quote=(
            "Empiric parenteral therapy should be initiated immediately in patients "
            "with suspected urosepsis. Cultures must be obtained prior to antibiotics."
        ),
        rec_class="I",
        evidence="A",
        next_nodes=["imaging_assessment"],
    )

    nodes["imaging_assessment"] = _node(
        node_id="imaging_assessment",
        node_type="enquiry",
        name="Imaging to Confirm Obstruction",
        description=(
            "CT abdomen/pelvis (preferred) or renal ultrasound to identify obstruction "
            "site and cause (stone, tumor, stricture)."
        ),
        mandatory=[
            "order_imaging_ct_abdomen_pelvis",
        ],
        allowed=[
            "order_imaging_ct_abdomen_pelvis",
            "order_imaging_renal_ultrasound",
            "order_imaging_kub_xray",
            "reassess_vital_signs",
        ],
        deadlines={
            "order_imaging_ct_abdomen_pelvis": 120,
        },
        source_guideline=src,
        source_section="3.4.4 Diagnostic Imaging",
        source_quote=(
            "CT without contrast is the gold standard for detecting urinary obstruction. "
            "Ultrasound is an alternative if CT is contraindicated."
        ),
        conditional_next={
            "state.obstruction_confirmed == True": "urgent_decompression",
            "state.obstruction_confirmed == False": "monitoring_reassessment",
        },
    )

    nodes["urgent_decompression"] = _node(
        node_id="urgent_decompression",
        node_type="action",
        name="Urgent Urinary Tract Decompression",
        description=(
            "Emergent decompression via percutaneous nephrostomy or ureteral stent. "
            "Definitive stone treatment should be deferred until sepsis resolves."
        ),
        mandatory=[
            "perform_urinary_decompression",
        ],
        allowed=[
            "perform_urinary_decompression",
            "perform_percutaneous_nephrostomy",
            "perform_ureteral_stent_placement",
            "consult_urology",
            "consult_interventional_radiology",
            "give_iv_fluids_resuscitation",
            "reassess_vital_signs",
        ],
        forbidden=[
            "perform_definitive_stone_surgery_during_sepsis",
            "perform_lithotripsy_during_sepsis",
        ],
        deadlines={
            "perform_urinary_decompression": 360,
        },
        source_guideline=src,
        source_section="3.4.5 Drainage of Obstructed Kidney",
        source_quote=(
            "Urgent decompression of the obstructed collecting system is mandatory "
            "in patients with obstructive pyelonephritis/urosepsis. Definitive stone "
            "treatment should be delayed until the patient has recovered."
        ),
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["monitoring_reassessment"] = _node(
        node_id="monitoring_reassessment",
        node_type="enquiry",
        name="Clinical Monitoring & Culture-Directed Therapy",
        description=(
            "Monitor clinical response at 48-72h, de-escalate to culture-directed "
            "antibiotics when susceptibilities available."
        ),
        mandatory=[
            "reassess_clinical_response",
            "review_culture_susceptibilities",
        ],
        allowed=[
            "reassess_clinical_response",
            "review_culture_susceptibilities",
            "de_escalate_antibiotics",
            "order_lab_creatinine",
            "order_lab_cbc",
            "reassess_vital_signs",
            "monitor_urine_output",
        ],
        deadlines={
            "reassess_clinical_response": 4320,
            "review_culture_susceptibilities": 4320,
        },
        source_guideline=src,
        source_section="3.4.7.2 De-escalation",
        source_quote=(
            "Antimicrobial therapy should be adjusted according to culture results. "
            "Clinical improvement expected within 48-72 hours of decompression."
        ),
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Follow-Up Planning",
        description=(
            "Assess resolution of sepsis, plan definitive treatment "
            "(stone removal, stent exchange), schedule follow-up imaging."
        ),
        mandatory=["assess_sepsis_resolution"],
        allowed=[
            "assess_sepsis_resolution",
            "plan_definitive_stone_treatment",
            "schedule_followup_imaging",
            "transition_to_oral_antibiotics",
            "arrange_outpatient_urology_followup",
        ],
        source_guideline=src,
        source_section="3.4.8 Follow-Up",
        source_quote=(
            "Patients should be followed up with imaging to ensure stone clearance "
            "and resolution of obstruction after definitive treatment."
        ),
    )

    return {
        "graph_id": "eau_obstructive_pyelonephritis_2024",
        "guideline_name": "EAU 2024 Guidelines on Urological Infections — Obstructive Pyelonephritis",
        "version": "2024.1",
        "metadata": {
            "source": "European Association of Urology Urological Infections Guidelines 2024",
            "doi": doi,
            "journal": "European Urology",
            "recommendation_system": "GRADE",
            "description": (
                "Management of obstructive pyelonephritis including empiric "
                "antibiotics, urgent decompression, and culture-directed therapy"
            ),
            "key_evidence": (
                "Urgent decompression reduces mortality in obstructive "
                "pyelonephritis with urosepsis. Percutaneous nephrostomy and "
                "ureteral stenting have equivalent decompression efficacy "
                "(Pearle et al., J Urol 1998)."
            ),
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 2. Drowning Resuscitation (ERC 2021)
# =========================================================================


def build_drowning_graph() -> dict[str, Any]:
    """ERC 2021 Drowning Resuscitation guideline graph."""
    src = "ERC 2021 Drowning Resuscitation Guidelines"
    doi = "10.1016/j.resuscitation.2021.02.016"

    nodes: dict[str, Any] = {}

    nodes["initial_rescue_assessment"] = _node(
        node_id="initial_rescue_assessment",
        node_type="decision",
        name="Scene Safety & Initial Assessment",
        description=(
            "Ensure rescuer safety, remove victim from water, "
            "assess consciousness and breathing. Begin rescue breaths in water if trained."
        ),
        mandatory=[
            "ensure_scene_safety",
            "assess_consciousness",
            "assess_breathing",
        ],
        allowed=[
            "ensure_scene_safety",
            "assess_consciousness",
            "assess_breathing",
            "remove_from_water",
            "call_emergency_services",
            "log_submersion_duration",
        ],
        deadlines={
            "ensure_scene_safety": 1,
            "assess_consciousness": 2,
            "assess_breathing": 2,
        },
        source_guideline=src,
        source_section="Section 4: Drowning — Initial Management",
        source_quote=(
            "Remove the victim from the water as quickly as possible. "
            "Open the airway and check for normal breathing."
        ),
        conditional_next={
            "state.has_pulse == False": "cpr_ventilation_priority",
            "state.has_pulse == True and state.breathing == False": "rescue_breathing",
            "state.has_pulse == True and state.breathing == True": "post_rescue_care",
        },
    )

    nodes["rescue_breathing"] = _node(
        node_id="rescue_breathing",
        node_type="action",
        name="Rescue Breathing (Ventilation Priority)",
        description=(
            "Drowning is an asphyxial arrest — ventilation takes priority. "
            "Give 5 initial rescue breaths, then reassess."
        ),
        mandatory=[
            "give_5_initial_rescue_breaths",
            "open_airway_head_tilt_chin_lift",
        ],
        allowed=[
            "give_5_initial_rescue_breaths",
            "open_airway_head_tilt_chin_lift",
            "apply_jaw_thrust_if_cspine",
            "suction_airway_if_debris",
            "apply_supplemental_oxygen",
        ],
        forbidden=[
            "perform_abdominal_thrusts_to_expel_water",
            "attempt_heimlich_for_water_removal",
        ],
        deadlines={
            "give_5_initial_rescue_breaths": 3,
            "open_airway_head_tilt_chin_lift": 2,
        },
        source_guideline=src,
        source_section="Section 4.2: Initial Ventilation",
        source_quote=(
            "Begin with 5 rescue breaths as hypoxia is the primary cause of cardiac arrest "
            "in drowning. Do NOT attempt to drain water from the lungs — "
            "abdominal thrusts are ineffective and delay resuscitation."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["cpr_ventilation_priority"],
    )

    nodes["cpr_ventilation_priority"] = _node(
        node_id="cpr_ventilation_priority",
        node_type="action",
        name="CPR with Ventilation-First Approach",
        description=(
            "Begin CPR with 30:2 ratio. In drowning, ventilation is critical — "
            "provide high-quality ventilations. Attach AED when available."
        ),
        mandatory=[
            "begin_cpr_30_2",
            "provide_high_quality_ventilations",
            "attach_aed_when_available",
        ],
        allowed=[
            "begin_cpr_30_2",
            "provide_high_quality_ventilations",
            "attach_aed_when_available",
            "establish_iv_io_access",
            "give_epinephrine_1mg_iv",
            "perform_advanced_airway_management",
            "apply_supplemental_oxygen",
        ],
        forbidden=[
            "compression_only_cpr",
        ],
        deadlines={
            "begin_cpr_30_2": 5,
            "provide_high_quality_ventilations": 5,
        },
        conditional_rules=[
            {
                "rule_id": "DROWNING-SHOCKABLE",
                "condition": "state.aed_rhythm == 'shockable'",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["deliver_defibrillation"],
                    "deadline_minutes": 2,
                },
                "severity": "CRITICAL",
                "description": (
                    "Shockable rhythm in drowning is uncommon but should "
                    "be defibrillated per standard ALS protocol"
                ),
            },
        ],
        source_guideline=src,
        source_section="Section 4.3: CPR in Drowning",
        source_quote=(
            "In drowning, ventilation is as important as compressions — "
            "compression-only CPR is NOT appropriate. Use standard 30:2 ratio. "
            "VF/pVT occurs in <10% of drowning arrests."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["hypothermia_management"],
    )

    nodes["hypothermia_management"] = _node(
        node_id="hypothermia_management",
        node_type="plan",
        name="Hypothermia Assessment & Treatment",
        description=(
            "Measure core temperature, initiate rewarming. "
            "Hypothermic drowning victims may have better neurological outcomes — "
            "continue resuscitation until rewarmed to 32 deg C."
        ),
        mandatory=[
            "measure_core_temperature",
            "initiate_active_rewarming",
        ],
        allowed=[
            "measure_core_temperature",
            "initiate_active_rewarming",
            "remove_wet_clothing",
            "apply_warm_blankets",
            "give_warm_iv_fluids",
            "consider_ecmo_rewarming",
            "avoid_rough_handling_if_hypothermic",
        ],
        forbidden=[
            "terminate_resuscitation_if_hypothermic",
        ],
        deadlines={
            "measure_core_temperature": 15,
            "initiate_active_rewarming": 30,
        },
        source_guideline=src,
        source_section="Section 4.4: Hypothermia in Drowning",
        source_quote=(
            "Hypothermia may be neuroprotective. Do not declare death until "
            "the patient is rewarmed to at least 32 deg C or rewarming efforts "
            "have failed. Consider ECLS/ECMO for refractory hypothermic arrest."
        ),
        rec_class="I",
        evidence="C",
        next_nodes=["post_rescue_care"],
    )

    nodes["post_rescue_care"] = _node(
        node_id="post_rescue_care",
        node_type="plan",
        name="Post-Rescue Hospital Care",
        description=(
            "Oxygenation, monitor for delayed pulmonary edema, "
            "avoid gastric distension, neuroprognostication."
        ),
        mandatory=[
            "provide_supplemental_oxygen",
            "monitor_for_pulmonary_edema",
        ],
        allowed=[
            "provide_supplemental_oxygen",
            "monitor_for_pulmonary_edema",
            "order_imaging_chest_xray",
            "order_lab_abg",
            "order_lab_bmp",
            "decompress_stomach_if_distended",
            "consider_intubation_if_hypoxic",
            "continuous_cardiac_monitoring",
            "assess_neurological_status",
        ],
        forbidden=[
            "prophylactic_antibiotics_routine",
            "prophylactic_corticosteroids",
        ],
        deadlines={
            "provide_supplemental_oxygen": 10,
            "monitor_for_pulmonary_edema": 60,
        },
        source_guideline=src,
        source_section="Section 4.5: In-Hospital Management",
        source_quote=(
            "All submersion victims with any respiratory symptoms should be "
            "observed for at least 6-8 hours for delayed pulmonary edema. "
            "Prophylactic antibiotics and corticosteroids are NOT recommended."
        ),
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Neuroprognostication",
        description=(
            "Assess neurological outcome, determine ICU vs ward admission, "
            "plan follow-up for pulmonary complications."
        ),
        mandatory=["assess_neurological_outcome"],
        allowed=[
            "assess_neurological_outcome",
            "admit_icu_if_intubated",
            "observe_6_to_8_hours",
            "arrange_followup",
            "social_work_referral",
        ],
        source_guideline=src,
        source_section="Section 4.6: Outcome & Follow-Up",
        source_quote=(
            "Neuroprognostication should follow standard post-cardiac-arrest "
            "protocols. Observe asymptomatic patients for minimum 6 hours."
        ),
    )

    return {
        "graph_id": "erc_drowning_2021",
        "guideline_name": "ERC 2021 Guidelines on Drowning Resuscitation",
        "version": "2021.1",
        "metadata": {
            "source": "European Resuscitation Council Guidelines 2021: Special Circumstances — Drowning",
            "doi": doi,
            "journal": "Resuscitation",
            "recommendation_system": "GRADE/ILCOR",
            "description": (
                "Evidence-based guideline for drowning resuscitation emphasizing "
                "ventilation-first CPR, hypothermia management, and avoidance of "
                "gastric drainage maneuvers"
            ),
            "key_evidence": (
                "Ventilation-first approach improves survival in drowning vs "
                "compression-only CPR. Hypothermic drowning victims have survived "
                "with good neurological outcomes after >60 min submersion "
                "(Tipton & Golden, 2011)."
            ),
        },
        "entry_node": "initial_rescue_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 3. NIV in Acute Respiratory Failure (ERS/ATS 2017)
# =========================================================================


def build_niv_graph() -> dict[str, Any]:
    """ERS/ATS 2017 NIV in Acute Respiratory Failure guideline graph."""
    src = "ERS/ATS Clinical Practice Guidelines: NIV for Acute Respiratory Failure 2017"
    doi = "10.1183/13993003.02426-2016"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Acute Respiratory Failure Recognition & NIV Indication",
        description=(
            "Identify type of acute respiratory failure and assess NIV eligibility. "
            "Strong indications: COPD exacerbation, cardiogenic pulmonary edema, "
            "immunocompromised with acute hypoxemia."
        ),
        mandatory=[
            "assess_respiratory_status",
            "order_lab_abg",
            "assess_niv_indication",
        ],
        allowed=[
            "assess_respiratory_status",
            "order_lab_abg",
            "assess_niv_indication",
            "order_imaging_chest_xray",
            "order_lab_bnp",
            "order_lab_cbc",
            "order_lab_bmp",
            "assess_vital_signs",
            "apply_supplemental_oxygen",
        ],
        deadlines={
            "assess_respiratory_status": 10,
            "order_lab_abg": 30,
            "assess_niv_indication": 30,
        },
        source_guideline=src,
        source_section="Recommendation 1-3: Indications for NIV",
        source_quote=(
            "We recommend NIV for COPD exacerbation with acute respiratory acidosis "
            "(strong, moderate certainty). We recommend NIV for acute cardiogenic "
            "pulmonary edema (strong, low certainty)."
        ),
        conditional_next={
            "state.diagnosis == 'copd_exacerbation'": "niv_copd_initiation",
            "state.diagnosis == 'cardiogenic_pulmonary_edema'": "niv_cpe_initiation",
            "state.diagnosis == 'immunocompromised_arf'": "niv_immunocompromised",
            "state.niv_contraindicated == True": "intubation_decision",
        },
    )

    nodes["niv_copd_initiation"] = _node(
        node_id="niv_copd_initiation",
        node_type="action",
        name="NIV for COPD Exacerbation (Strong Recommendation)",
        description=(
            "Initiate bilevel NIV (IPAP/EPAP) for acute hypercapnic respiratory failure "
            "due to COPD exacerbation. Target pH improvement within 1-2 hours."
        ),
        precondition="state.diagnosis == 'copd_exacerbation' and state.ph < 7.35",
        mandatory=[
            "initiate_bilevel_niv",
            "set_ipap_10_to_20_cmh2o",
            "set_epap_4_to_6_cmh2o",
        ],
        allowed=[
            "initiate_bilevel_niv",
            "set_ipap_10_to_20_cmh2o",
            "set_epap_4_to_6_cmh2o",
            "titrate_fio2_to_spo2_88_92",
            "give_bronchodilator_nebulized",
            "give_systemic_corticosteroids",
            "order_lab_abg",
            "reassess_respiratory_status",
        ],
        forbidden=[
            "initiate_high_flow_o2_above_spo2_92",
        ],
        deadlines={
            "initiate_bilevel_niv": 60,
            "set_ipap_10_to_20_cmh2o": 60,
        },
        source_guideline=src,
        source_section="Recommendation 1: COPD",
        source_quote=(
            "Bilevel NIV reduces mortality (RR 0.54), intubation (RR 0.36), and "
            "hospital LOS in COPD with acute respiratory acidosis (pH <7.35). "
            "NNT=5 for mortality reduction (Lightowler et al. BMJ 2003)."
        ),
        rec_class="I",
        evidence="A",
        next_nodes=["niv_monitoring"],
    )

    nodes["niv_cpe_initiation"] = _node(
        node_id="niv_cpe_initiation",
        node_type="action",
        name="NIV for Cardiogenic Pulmonary Edema",
        description=(
            "Initiate CPAP or bilevel NIV for acute cardiogenic pulmonary edema. "
            "CPAP 5-10 cmH2O is first-line."
        ),
        precondition="state.diagnosis == 'cardiogenic_pulmonary_edema'",
        mandatory=[
            "initiate_cpap_or_bilevel",
            "set_cpap_5_to_10_cmh2o",
        ],
        allowed=[
            "initiate_cpap_or_bilevel",
            "set_cpap_5_to_10_cmh2o",
            "give_iv_furosemide",
            "give_iv_nitroglycerin",
            "order_lab_bnp",
            "order_imaging_chest_xray",
            "reassess_respiratory_status",
            "order_lab_abg",
        ],
        deadlines={
            "initiate_cpap_or_bilevel": 30,
        },
        source_guideline=src,
        source_section="Recommendation 2: Cardiogenic Pulmonary Edema",
        source_quote=(
            "NIV (CPAP or bilevel) reduces mortality and intubation rate in "
            "acute cardiogenic pulmonary edema (3CPO trial, Gray et al. NEJM 2008)."
        ),
        rec_class="I",
        evidence="A",
        next_nodes=["niv_monitoring"],
    )

    nodes["niv_immunocompromised"] = _node(
        node_id="niv_immunocompromised",
        node_type="action",
        name="NIV for Immunocompromised Patients with ARF",
        description=(
            "Early NIV in immunocompromised patients with acute hypoxemic "
            "respiratory failure to avoid intubation-associated complications."
        ),
        precondition="state.diagnosis == 'immunocompromised_arf'",
        mandatory=[
            "initiate_niv_early",
            "monitor_closely_for_niv_failure",
        ],
        allowed=[
            "initiate_niv_early",
            "monitor_closely_for_niv_failure",
            "set_pressure_support_ventilation",
            "titrate_fio2_to_target_spo2",
            "order_lab_abg",
            "order_imaging_chest_xray",
            "reassess_respiratory_status",
        ],
        deadlines={
            "initiate_niv_early": 60,
        },
        source_guideline=src,
        source_section="Recommendation 3: Immunocompromised",
        source_quote=(
            "We suggest NIV for early acute respiratory failure in immunocompromised "
            "patients (conditional, low certainty). Close monitoring is essential "
            "as delayed intubation increases mortality (Hilbert et al. NEJM 2001)."
        ),
        rec_class="IIa",
        evidence="B",
        next_nodes=["niv_monitoring"],
    )

    nodes["niv_monitoring"] = _node(
        node_id="niv_monitoring",
        node_type="enquiry",
        name="NIV Response Monitoring (1-2 Hour Check)",
        description=(
            "Assess NIV response at 1-2 hours. Key targets: pH improvement, "
            "RR reduction, patient comfort, air leak minimization."
        ),
        mandatory=[
            "reassess_abg_at_1_to_2_hours",
            "evaluate_niv_tolerance",
        ],
        allowed=[
            "reassess_abg_at_1_to_2_hours",
            "evaluate_niv_tolerance",
            "adjust_niv_settings",
            "assess_mask_fit",
            "monitor_vital_signs",
            "assess_patient_ventilator_synchrony",
        ],
        deadlines={
            "reassess_abg_at_1_to_2_hours": 120,
            "evaluate_niv_tolerance": 120,
        },
        source_guideline=src,
        source_section="Monitoring & Failure Criteria",
        source_quote=(
            "Failure to improve pH within 1-2 hours predicts NIV failure. "
            "Predictors of failure include high severity score, "
            "pH <7.25, and excessive air leak."
        ),
        conditional_next={
            "state.niv_failed == True": "intubation_decision",
            "state.niv_improving == True": "disposition",
        },
    )

    nodes["intubation_decision"] = _node(
        node_id="intubation_decision",
        node_type="decision",
        name="Escalation to Invasive Mechanical Ventilation",
        description=(
            "NIV failure or contraindication — proceed to endotracheal intubation. "
            "Do not delay intubation in deteriorating patients."
        ),
        mandatory=[
            "proceed_to_intubation",
        ],
        allowed=[
            "proceed_to_intubation",
            "prepare_rsi_medications",
            "preoxygenate",
            "confirm_tube_placement_etco2",
            "initiate_mechanical_ventilation",
        ],
        forbidden=[
            "continue_niv_if_failing",
        ],
        deadlines={
            "proceed_to_intubation": 30,
        },
        source_guideline=src,
        source_section="NIV Failure & Escalation",
        source_quote=(
            "Delayed intubation after NIV failure is associated with increased "
            "mortality. NIV should not be used as a substitute for needed intubation."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Weaning",
        description="Assess NIV weaning readiness, plan ICU vs step-down disposition.",
        mandatory=["assess_weaning_readiness"],
        allowed=[
            "assess_weaning_readiness",
            "trial_niv_discontinuation",
            "transition_to_standard_oxygen",
            "continue_niv_intermittent",
            "arrange_icu_or_stepdown",
        ],
        source_guideline=src,
        source_section="Weaning & Disposition",
        source_quote=(
            "NIV can be weaned as clinical condition improves, "
            "guided by ABG and respiratory rate improvement."
        ),
    )

    return {
        "graph_id": "ers_ats_niv_2017",
        "guideline_name": "ERS/ATS Clinical Practice Guidelines: NIV for Acute Respiratory Failure (2017)",
        "version": "2017.1",
        "metadata": {
            "source": "ERS/ATS Clinical Practice Guidelines: Noninvasive Ventilation for Acute Respiratory Failure",
            "doi": doi,
            "journal": "European Respiratory Journal",
            "recommendation_system": "GRADE",
            "description": (
                "Evidence-based guideline for NIV in acute respiratory failure "
                "covering COPD, cardiogenic pulmonary edema, and immunocompromised patients"
            ),
            "key_evidence": (
                "NIV reduces mortality by 46% and intubation by 64% in COPD exacerbation "
                "(Lightowler meta-analysis). CPAP reduces mortality in cardiogenic pulmonary "
                "edema (3CPO trial). NNT=5 for COPD mortality prevention."
            ),
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 4. Severe Pediatric Asthma Exacerbation (GINA 2024)
# =========================================================================


def build_pediatric_asthma_graph() -> dict[str, Any]:
    """GINA 2024 Severe Pediatric Asthma Exacerbation guideline graph."""
    src = "GINA 2024 — Management of Asthma Exacerbations"
    doi = "10.1183/13993003.00735-2024"

    nodes: dict[str, Any] = {}

    nodes["severity_assessment"] = _node(
        node_id="severity_assessment",
        node_type="decision",
        name="Asthma Exacerbation Severity Assessment",
        description=(
            "Classify severity: mild-moderate vs severe vs life-threatening. "
            "Assess accessory muscle use, SpO2, ability to speak, mental status."
        ),
        mandatory=[
            "assess_exacerbation_severity",
            "measure_spo2",
            "assess_vital_signs",
        ],
        allowed=[
            "assess_exacerbation_severity",
            "measure_spo2",
            "assess_vital_signs",
            "measure_peak_flow",
            "order_lab_abg_if_severe",
            "assess_accessory_muscle_use",
            "assess_mental_status",
            "assess_ability_to_speak",
        ],
        deadlines={
            "assess_exacerbation_severity": 5,
            "measure_spo2": 5,
            "assess_vital_signs": 10,
        },
        source_guideline=src,
        source_section="Box 4-3: Management of Asthma Exacerbations in Acute Care",
        source_quote=(
            "Severity assessment: Mild-moderate (talks in phrases, SpO2 >=90%), "
            "Severe (talks in words, accessory muscles, SpO2 <90%), "
            "Life-threatening (drowsy, confused, silent chest)."
        ),
        conditional_next={
            "state.severity == 'life_threatening'": "life_threatening_bundle",
            "state.severity == 'severe'": "severe_asthma_bundle",
            "state.severity == 'mild_moderate'": "initial_bronchodilator_therapy",
        },
    )

    nodes["initial_bronchodilator_therapy"] = _node(
        node_id="initial_bronchodilator_therapy",
        node_type="action",
        name="Initial Bronchodilator Therapy (Mild-Moderate)",
        description=(
            "pMDI + spacer SABA (4-10 puffs q20min x3), oral prednisolone, "
            "controlled oxygen to target SpO2 94-98%."
        ),
        precondition="state.severity == 'mild_moderate'",
        mandatory=[
            "give_saba_inhaled_q20min",
            "give_oral_corticosteroid",
            "apply_controlled_oxygen",
        ],
        allowed=[
            "give_saba_inhaled_q20min",
            "give_oral_corticosteroid",
            "apply_controlled_oxygen",
            "give_ipratropium_if_poor_response",
            "reassess_at_1_hour",
            "measure_peak_flow",
        ],
        deadlines={
            "give_saba_inhaled_q20min": 15,
            "give_oral_corticosteroid": 60,
            "apply_controlled_oxygen": 10,
        },
        source_guideline=src,
        source_section="Box 4-3: Initial Treatment",
        source_quote=(
            "Inhaled SABA: 4-10 puffs via pMDI + spacer, repeat every 20 minutes "
            "for 1 hour. Give oral prednisolone 1-2 mg/kg (max 40 mg)."
        ),
        rec_class="I",
        evidence="A",
        next_nodes=["reassessment"],
    )

    nodes["severe_asthma_bundle"] = _node(
        node_id="severe_asthma_bundle",
        node_type="plan",
        name="Severe Asthma Exacerbation Bundle",
        description=(
            "Continuous nebulized albuterol, ipratropium bromide q20min x3, "
            "systemic corticosteroids, IV magnesium sulfate."
        ),
        precondition="state.severity == 'severe'",
        mandatory=[
            "give_continuous_nebulized_albuterol",
            "give_ipratropium_bromide_q20min",
            "give_systemic_corticosteroids_iv",
            "apply_high_flow_oxygen",
        ],
        allowed=[
            "give_continuous_nebulized_albuterol",
            "give_ipratropium_bromide_q20min",
            "give_systemic_corticosteroids_iv",
            "apply_high_flow_oxygen",
            "give_iv_magnesium_sulfate",
            "establish_iv_access",
            "order_lab_abg",
            "order_imaging_chest_xray",
            "continuous_spo2_monitoring",
        ],
        forbidden=[
            "give_sedatives",
            "give_mucolytics_during_acute",
        ],
        deadlines={
            "give_continuous_nebulized_albuterol": 15,
            "give_ipratropium_bromide_q20min": 20,
            "give_systemic_corticosteroids_iv": 60,
            "apply_high_flow_oxygen": 5,
        },
        source_guideline=src,
        source_section="Box 4-3: Severe Exacerbation",
        source_quote=(
            "Severe exacerbation: continuous nebulized SABA + ipratropium, "
            "systemic corticosteroids. Add IV MgSO4 (single dose 40-50 mg/kg, max 2g) "
            "if poor response. Do NOT sedate the child."
        ),
        rec_class="I",
        evidence="A",
        next_nodes=["reassessment"],
    )

    nodes["life_threatening_bundle"] = _node(
        node_id="life_threatening_bundle",
        node_type="plan",
        name="Life-Threatening Asthma / Status Asthmaticus",
        description=(
            "ICU-level care: continuous nebulized SABA, IV corticosteroids, "
            "IV magnesium, consider IV aminophylline, heliox, or intubation."
        ),
        precondition="state.severity == 'life_threatening'",
        mandatory=[
            "give_continuous_nebulized_albuterol",
            "give_iv_methylprednisolone",
            "give_iv_magnesium_sulfate",
            "apply_high_flow_oxygen",
            "continuous_cardiorespiratory_monitoring",
        ],
        allowed=[
            "give_continuous_nebulized_albuterol",
            "give_iv_methylprednisolone",
            "give_iv_magnesium_sulfate",
            "apply_high_flow_oxygen",
            "continuous_cardiorespiratory_monitoring",
            "give_ipratropium_bromide_q20min",
            "give_iv_aminophylline",
            "consider_heliox",
            "prepare_for_intubation",
            "perform_intubation",
            "order_lab_abg",
            "order_lab_bmp",
            "establish_iv_access",
        ],
        forbidden=[
            "give_sedatives",
            "give_mucolytics_during_acute",
        ],
        deadlines={
            "give_continuous_nebulized_albuterol": 10,
            "give_iv_methylprednisolone": 30,
            "give_iv_magnesium_sulfate": 60,
            "apply_high_flow_oxygen": 5,
            "continuous_cardiorespiratory_monitoring": 5,
        },
        conditional_rules=[
            {
                "rule_id": "ASTHMA-INTUBATION",
                "condition": "state.respiratory_failure_imminent == True",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["perform_intubation"],
                    "deadline_minutes": 15,
                },
                "severity": "CRITICAL",
                "description": (
                    "Intubation is indicated for impending respiratory arrest: "
                    "drowsy, silent chest, bradycardia, cyanosis"
                ),
            },
        ],
        source_guideline=src,
        source_section="Box 4-3: Life-Threatening Exacerbation",
        source_quote=(
            "Life-threatening features: drowsy, confused, silent chest, cyanosis, "
            "SpO2 <90%, peak flow <33% predicted. Requires ICU admission. "
            "IV MgSO4 recommended if poor response to initial therapy."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["reassessment"],
    )

    nodes["reassessment"] = _node(
        node_id="reassessment",
        node_type="enquiry",
        name="Clinical Reassessment at 1 Hour",
        description=(
            "Reassess severity at 1 hour, determine response to therapy, "
            "decide on disposition."
        ),
        mandatory=[
            "reassess_severity_at_1_hour",
            "reassess_spo2",
        ],
        allowed=[
            "reassess_severity_at_1_hour",
            "reassess_spo2",
            "measure_peak_flow",
            "order_lab_abg_repeat",
            "adjust_bronchodilator_frequency",
            "reassess_mental_status",
        ],
        deadlines={
            "reassess_severity_at_1_hour": 60,
            "reassess_spo2": 60,
        },
        source_guideline=src,
        source_section="Box 4-3: Reassessment",
        source_quote=(
            "Reassess at 1 hour (or earlier if worsening). Good response: "
            "SpO2 >=94%, talks in sentences. Poor response: escalate to "
            "severe/life-threatening pathway."
        ),
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition Decision",
        description=(
            "Discharge vs continued observation vs ICU admission based on response."
        ),
        mandatory=["determine_disposition"],
        allowed=[
            "determine_disposition",
            "provide_discharge_action_plan",
            "prescribe_oral_corticosteroid_course",
            "review_inhaler_technique",
            "schedule_followup_48_hours",
            "admit_to_icu",
        ],
        source_guideline=src,
        source_section="Box 4-3: Disposition",
        source_quote=(
            "Discharge criteria: improved symptoms, SpO2 >=94% on room air, "
            "PEF >60% predicted. All discharged patients need a written action plan "
            "and 48-hour follow-up."
        ),
    )

    return {
        "graph_id": "gina_pediatric_status_asthma_2024",
        "guideline_name": "GINA 2024 Severe Pediatric Asthma Exacerbation",
        "version": "2024.1",
        "metadata": {
            "source": "Global Initiative for Asthma (GINA) 2024 Report",
            "doi": doi,
            "journal": "European Respiratory Journal",
            "recommendation_system": "GINA Evidence Levels",
            "description": (
                "Management of severe pediatric asthma exacerbation including "
                "status asthmaticus requiring continuous nebulized SABA, "
                "IV corticosteroids, IV magnesium, and intubation criteria"
            ),
            "key_evidence": (
                "IV MgSO4 reduces hospital admission in severe asthma "
                "(OR 0.75, 95% CI 0.60-0.92, Rowe meta-analysis). "
                "Ipratropium added to SABA reduces hospitalization in severe exacerbation "
                "(Plotnick & Ducharme, Cochrane 2000)."
            ),
        },
        "entry_node": "severity_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 5. Ventricular Arrhythmias & Sudden Death (HRS 2017)
# =========================================================================


def build_vt_sd_graph() -> dict[str, Any]:
    """HRS/EHRA/APHRS/LAHRS 2017 Ventricular Arrhythmias guideline graph."""
    src = "HRS/EHRA/APHRS/LAHRS Expert Consensus on Ventricular Arrhythmias 2017"
    doi = "10.1016/j.hrthm.2017.10.036"

    nodes: dict[str, Any] = {}

    nodes["hemodynamic_assessment"] = _node(
        node_id="hemodynamic_assessment",
        node_type="decision",
        name="Hemodynamic Assessment & 12-Lead ECG",
        description=(
            "Determine hemodynamic stability. Obtain 12-lead ECG during tachycardia "
            "to classify VT morphology (monomorphic vs polymorphic)."
        ),
        mandatory=[
            "assess_hemodynamic_status",
            "obtain_12_lead_ecg",
            "assess_vital_signs",
        ],
        allowed=[
            "assess_hemodynamic_status",
            "obtain_12_lead_ecg",
            "assess_vital_signs",
            "establish_iv_access",
            "continuous_cardiac_monitoring",
            "order_lab_electrolytes",
            "order_lab_magnesium",
            "order_lab_troponin",
            "order_lab_bmp",
        ],
        deadlines={
            "assess_hemodynamic_status": 2,
            "obtain_12_lead_ecg": 5,
            "assess_vital_signs": 5,
        },
        source_guideline=src,
        source_section="Section 5: Acute Management of VA",
        source_quote=(
            "12-lead ECG during tachycardia is essential for diagnosis. "
            "Hemodynamic instability (hypotension, syncope, chest pain, heart failure) "
            "mandates immediate electrical cardioversion."
        ),
        conditional_next={
            "state.hemodynamically_unstable == True": "cardioversion_unstable_vt",
            "state.hemodynamically_stable == True": "stable_vt_pharmacotherapy",
        },
    )

    nodes["cardioversion_unstable_vt"] = _node(
        node_id="cardioversion_unstable_vt",
        node_type="action",
        name="Synchronized Cardioversion (Unstable VT)",
        description=(
            "Immediate synchronized cardioversion for hemodynamically unstable VT. "
            "Start at 100J biphasic, escalate if unsuccessful."
        ),
        precondition="state.hemodynamically_unstable == True",
        mandatory=[
            "perform_synchronized_cardioversion",
            "continuous_cardiac_monitoring",
        ],
        allowed=[
            "perform_synchronized_cardioversion",
            "continuous_cardiac_monitoring",
            "give_sedation_for_cardioversion",
            "establish_iv_access",
            "prepare_defibrillator",
            "give_iv_amiodarone_post_cardioversion",
        ],
        forbidden=[
            "delay_cardioversion_for_drug_trial",
        ],
        deadlines={
            "perform_synchronized_cardioversion": 5,
            "continuous_cardiac_monitoring": 2,
        },
        source_guideline=src,
        source_section="Section 5.1: Unstable VT Management",
        source_quote=(
            "Synchronized cardioversion is the treatment of choice for unstable "
            "monomorphic VT. Do not delay cardioversion to attempt pharmacological "
            "conversion in hemodynamically compromised patients."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["electrolyte_correction"],
    )

    nodes["stable_vt_pharmacotherapy"] = _node(
        node_id="stable_vt_pharmacotherapy",
        node_type="action",
        name="Pharmacotherapy for Stable Monomorphic VT",
        description=(
            "IV amiodarone (150 mg over 10 min) is first-line for stable monomorphic VT. "
            "IV procainamide is an alternative. IV lidocaine for ischemic VT."
        ),
        precondition="state.hemodynamically_stable == True",
        mandatory=[
            "give_iv_amiodarone_150mg",
        ],
        allowed=[
            "give_iv_amiodarone_150mg",
            "give_iv_procainamide",
            "give_iv_lidocaine_if_ischemic",
            "continuous_cardiac_monitoring",
            "obtain_12_lead_ecg_post_treatment",
            "order_lab_electrolytes",
        ],
        forbidden=[
            "give_iv_verapamil_for_wide_complex",
            "give_iv_diltiazem_for_wide_complex",
        ],
        deadlines={
            "give_iv_amiodarone_150mg": 30,
        },
        source_guideline=src,
        source_section="Section 5.2: Stable VT Pharmacotherapy",
        source_quote=(
            "IV amiodarone is recommended for acute termination of hemodynamically "
            "stable monomorphic VT (Class I). IV calcium channel blockers "
            "(verapamil, diltiazem) are contraindicated in wide-complex tachycardia "
            "of uncertain origin — risk of hemodynamic collapse."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["electrolyte_correction"],
    )

    nodes["electrolyte_correction"] = _node(
        node_id="electrolyte_correction",
        node_type="action",
        name="Electrolyte Correction",
        description=(
            "Correct hypokalemia (target K+ >4.0 mEq/L) and hypomagnesemia "
            "(target Mg2+ >2.0 mg/dL) — both lower VT/VF threshold."
        ),
        mandatory=[
            "correct_potassium_if_low",
            "correct_magnesium_if_low",
        ],
        allowed=[
            "correct_potassium_if_low",
            "correct_magnesium_if_low",
            "order_lab_electrolytes_repeat",
            "order_lab_magnesium_repeat",
            "reassess_cardiac_rhythm",
            "continuous_cardiac_monitoring",
        ],
        deadlines={
            "correct_potassium_if_low": 60,
            "correct_magnesium_if_low": 60,
        },
        source_guideline=src,
        source_section="Section 5.3: Electrolyte Management",
        source_quote=(
            "Electrolyte abnormalities (hypokalemia, hypomagnesemia) lower the "
            "fibrillation threshold. Maintain K+ >4.0 mEq/L and Mg2+ >2.0 mg/dL "
            "in patients with ventricular arrhythmias."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["cardiac_evaluation"],
    )

    nodes["cardiac_evaluation"] = _node(
        node_id="cardiac_evaluation",
        node_type="enquiry",
        name="Cardiac Structural Evaluation",
        description=(
            "Echocardiography to assess LVEF, wall motion, structural heart disease. "
            "Coronary angiography if ischemic etiology suspected."
        ),
        mandatory=[
            "perform_echocardiography",
            "assess_lvef",
        ],
        allowed=[
            "perform_echocardiography",
            "assess_lvef",
            "consider_coronary_angiography",
            "order_cardiac_mri",
            "obtain_12_lead_ecg_sinus",
            "order_lab_troponin_serial",
            "consult_electrophysiology",
        ],
        deadlines={
            "perform_echocardiography": 1440,
            "assess_lvef": 1440,
        },
        source_guideline=src,
        source_section="Section 6: Evaluation of VT",
        source_quote=(
            "Echocardiography is recommended in all patients presenting with VT "
            "to evaluate for structural heart disease (Class I). Coronary angiography "
            "indicated if ischemia is suspected."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["icd_evaluation"],
    )

    nodes["icd_evaluation"] = _node(
        node_id="icd_evaluation",
        node_type="decision",
        name="ICD Evaluation & Long-Term Management",
        description=(
            "Assess ICD indication (secondary prevention for survived VT/VF arrest, "
            "primary prevention for LVEF <=35%). Plan antiarrhythmic therapy."
        ),
        mandatory=["evaluate_icd_indication"],
        allowed=[
            "evaluate_icd_indication",
            "refer_for_icd_implantation",
            "initiate_oral_amiodarone",
            "initiate_oral_sotalol",
            "initiate_beta_blocker_therapy",
            "refer_catheter_ablation",
            "arrange_electrophysiology_followup",
        ],
        source_guideline=src,
        source_section="Section 7: ICD Therapy",
        source_quote=(
            "ICD is recommended for secondary prevention in survivors of VT/VF "
            "cardiac arrest not due to reversible causes (Class I, Level A). "
            "Primary prevention ICD for LVEF <=35% with NYHA II-III "
            "(SCD-HeFT trial)."
        ),
        rec_class="I",
        evidence="A",
    )

    return {
        "graph_id": "hrs_vt_sd_2017",
        "guideline_name": (
            "HRS/EHRA/APHRS/LAHRS 2017 Expert Consensus Statement on "
            "Ventricular Arrhythmias"
        ),
        "version": "2017.1",
        "metadata": {
            "source": (
                "2017 AHA/ACC/HRS Guideline for Management of Patients "
                "with Ventricular Arrhythmias and the Prevention of Sudden Cardiac Death"
            ),
            "doi": doi,
            "journal": "Heart Rhythm",
            "recommendation_system": "ACC/AHA Classification",
            "description": (
                "Expert consensus for acute and long-term management of ventricular "
                "arrhythmias including synchronized cardioversion, antiarrhythmic "
                "therapy, electrolyte correction, and ICD evaluation"
            ),
            "key_evidence": (
                "Amiodarone terminates stable VT in ~30% of cases (Levine meta-analysis). "
                "SCD-HeFT trial: ICD reduces mortality by 23% in LVEF <=35% (HR 0.77). "
                "Calcium channel blockers in wide-complex tachycardia cause hemodynamic collapse "
                "in up to 44% (Stewart et al.)."
            ),
        },
        "entry_node": "hemodynamic_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 6. C. difficile Infection (IDSA/SHEA 2021)
# =========================================================================


def build_cdi_graph() -> dict[str, Any]:
    """IDSA/SHEA 2021 C. difficile Infection guideline graph."""
    src = "IDSA/SHEA 2021 Focused Update: CDI in Adults"
    doi = "10.1093/cid/ciab549"

    nodes: dict[str, Any] = {}

    nodes["diagnostic_assessment"] = _node(
        node_id="diagnostic_assessment",
        node_type="decision",
        name="CDI Diagnostic Testing",
        description=(
            "Stool testing for C. difficile: preferred two-step algorithm "
            "(GDH + toxin EIA), or NAAT alone. Test only diarrheal stool "
            "(>=3 unformed stools in 24h)."
        ),
        mandatory=[
            "order_stool_cdi_testing",
            "assess_diarrhea_severity",
            "review_antibiotic_exposure",
        ],
        allowed=[
            "order_stool_cdi_testing",
            "assess_diarrhea_severity",
            "review_antibiotic_exposure",
            "order_stool_gdh_plus_toxin",
            "order_stool_naat",
            "order_lab_cbc",
            "order_lab_creatinine",
            "order_lab_lactate",
            "order_lab_albumin",
            "assess_vital_signs",
        ],
        forbidden=[
            "order_stool_test_on_formed_stool",
            "order_test_of_cure",
        ],
        deadlines={
            "order_stool_cdi_testing": 60,
            "assess_diarrhea_severity": 30,
        },
        source_guideline=src,
        source_section="Recommendation 1: Diagnosis",
        source_quote=(
            "Test only patients with unexplained, new-onset >=3 unformed stools "
            "in 24 hours. Preferred: multi-step algorithm (GDH + toxin EIA, "
            "NAAT arbitration). Do NOT test formed stool or perform test-of-cure."
        ),
        conditional_next={
            "state.cdi_severity == 'fulminant'": "fulminant_cdi_management",
            "state.cdi_severity == 'severe'": "non_severe_cdi_treatment",
            "state.cdi_severity == 'non_severe'": "non_severe_cdi_treatment",
        },
    )

    nodes["non_severe_cdi_treatment"] = _node(
        node_id="non_severe_cdi_treatment",
        node_type="action",
        name="Initial CDI Treatment (Non-Severe & Severe)",
        description=(
            "2021 update: fidaxomicin is preferred over vancomycin for initial "
            "non-severe and severe CDI. Oral vancomycin 125 mg QID x10 days "
            "is an acceptable alternative."
        ),
        mandatory=[
            "discontinue_offending_antibiotic",
            "give_fidaxomicin_or_oral_vancomycin",
        ],
        allowed=[
            "discontinue_offending_antibiotic",
            "give_fidaxomicin_or_oral_vancomycin",
            "give_fidaxomicin_200mg_bid",
            "give_oral_vancomycin_125mg_qid",
            "initiate_contact_precautions",
            "give_iv_fluids_if_dehydrated",
            "order_lab_bmp",
        ],
        forbidden=[
            "give_metronidazole_for_initial_episode",
            "give_antidiarrheal_loperamide",
        ],
        deadlines={
            "discontinue_offending_antibiotic": 60,
            "give_fidaxomicin_or_oral_vancomycin": 120,
        },
        source_guideline=src,
        source_section="Recommendation 2-3: Initial Episode Treatment",
        source_quote=(
            "Fidaxomicin is preferred over vancomycin for initial CDI (conditional, "
            "moderate certainty) due to lower recurrence rates (13% vs 27%, Louie et al. "
            "NEJM 2011). Metronidazole should NOT be used for initial episode."
        ),
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring_response"],
    )

    nodes["fulminant_cdi_management"] = _node(
        node_id="fulminant_cdi_management",
        node_type="plan",
        name="Fulminant CDI Management",
        description=(
            "Fulminant CDI (hypotension, ileus, megacolon, or organ failure): "
            "high-dose oral vancomycin + IV metronidazole. Surgical consult mandatory."
        ),
        precondition="state.cdi_severity == 'fulminant'",
        mandatory=[
            "give_oral_vancomycin_500mg_qid",
            "give_iv_metronidazole_500mg_q8h",
            "consult_surgery",
        ],
        allowed=[
            "give_oral_vancomycin_500mg_qid",
            "give_iv_metronidazole_500mg_q8h",
            "consult_surgery",
            "give_rectal_vancomycin_enema_if_ileus",
            "order_imaging_ct_abdomen",
            "order_lab_lactate",
            "order_lab_cbc",
            "give_iv_fluids_resuscitation",
            "continuous_hemodynamic_monitoring",
            "consult_gastroenterology",
        ],
        forbidden=[
            "give_antidiarrheal_loperamide",
            "delay_surgical_consult",
        ],
        deadlines={
            "give_oral_vancomycin_500mg_qid": 60,
            "give_iv_metronidazole_500mg_q8h": 60,
            "consult_surgery": 120,
        },
        conditional_rules=[
            {
                "rule_id": "CDI-TOXIC-MEGACOLON",
                "condition": "state.toxic_megacolon == True or state.perforation == True",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["perform_emergency_colectomy"],
                    "deadline_minutes": 120,
                },
                "severity": "CRITICAL",
                "description": (
                    "Toxic megacolon or perforation requires emergent subtotal "
                    "colectomy. Mortality increases with surgical delay."
                ),
            },
        ],
        source_guideline=src,
        source_section="Recommendation 4: Fulminant CDI",
        source_quote=(
            "Fulminant CDI: oral vancomycin 500 mg QID (consider rectal vancomycin "
            "if ileus) + IV metronidazole 500 mg q8h. Early surgical consultation "
            "is recommended — subtotal colectomy for toxic megacolon or perforation."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring_response"],
    )

    nodes["monitoring_response"] = _node(
        node_id="monitoring_response",
        node_type="enquiry",
        name="Treatment Response Monitoring",
        description=(
            "Monitor clinical response (stool frequency, WBC, creatinine). "
            "Expect improvement within 3-5 days."
        ),
        mandatory=[
            "monitor_diarrhea_frequency",
            "reassess_clinical_status",
        ],
        allowed=[
            "monitor_diarrhea_frequency",
            "reassess_clinical_status",
            "order_lab_cbc",
            "order_lab_creatinine",
            "assess_for_recurrence_risk",
            "assess_vital_signs",
        ],
        forbidden=[
            "repeat_cdi_testing_during_treatment",
        ],
        deadlines={
            "monitor_diarrhea_frequency": 4320,
            "reassess_clinical_status": 4320,
        },
        source_guideline=src,
        source_section="Monitoring",
        source_quote=(
            "Do NOT repeat C. difficile testing during or shortly after treatment. "
            "Clinical response (not microbiological cure) defines treatment success."
        ),
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Recurrence Prevention",
        description=(
            "Assess for recurrence risk factors, consider bezlotoxumab "
            "for high-risk recurrence, plan antimicrobial stewardship."
        ),
        mandatory=["assess_recurrence_risk"],
        allowed=[
            "assess_recurrence_risk",
            "give_bezlotoxumab_if_high_recurrence_risk",
            "consider_fecal_microbiota_transplant",
            "initiate_antimicrobial_stewardship",
            "arrange_followup",
        ],
        source_guideline=src,
        source_section="Recommendation 5-6: Recurrence Prevention",
        source_quote=(
            "Bezlotoxumab (monoclonal antibody to toxin B) reduces CDI recurrence "
            "(MODIFY I/II trials, Wilcox et al. NEJM 2017). FMT recommended after "
            "2+ recurrences of CDI."
        ),
    )

    return {
        "graph_id": "idsa_cdi_2021",
        "guideline_name": "IDSA/SHEA 2021 Focused Update: C. difficile Infection in Adults",
        "version": "2021.1",
        "metadata": {
            "source": "IDSA/SHEA 2021 Focused Update Guidelines on Management of CDI in Adults",
            "doi": doi,
            "journal": "Clinical Infectious Diseases",
            "recommendation_system": "GRADE",
            "description": (
                "Updated guideline for C. difficile infection management "
                "emphasizing fidaxomicin preference, fulminant CDI bundle, "
                "and recurrence prevention strategies"
            ),
            "key_evidence": (
                "Fidaxomicin reduces CDI recurrence vs vancomycin (13% vs 27%, "
                "Louie et al. NEJM 2011). Fulminant CDI mortality is 30-50% without "
                "surgery. Bezlotoxumab reduces recurrence by 38% (MODIFY trials)."
            ),
        },
        "entry_node": "diagnostic_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 7. Thrombotic Thrombocytopenic Purpura (ISTH/ASH 2020)
# =========================================================================


def build_ttp_graph() -> dict[str, Any]:
    """ISTH/ASH 2020 TTP guideline graph."""
    src = "ISTH 2020 Guidelines for TTP"
    doi = "10.1182/bloodadvances.2020002474"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="TTP Suspicion & PLASMIC Score",
        description=(
            "Calculate PLASMIC score for TTP probability. Thrombocytopenia + MAHA "
            "(schistocytes on smear) with no alternative explanation."
        ),
        mandatory=[
            "calculate_plasmic_score",
            "order_lab_cbc_with_smear",
            "order_lab_ldh",
            "order_lab_haptoglobin",
            "order_lab_creatinine",
        ],
        allowed=[
            "calculate_plasmic_score",
            "order_lab_cbc_with_smear",
            "order_lab_ldh",
            "order_lab_haptoglobin",
            "order_lab_creatinine",
            "order_lab_reticulocyte_count",
            "order_lab_coagulation",
            "order_lab_direct_bilirubin",
            "order_lab_adamts13_activity",
            "assess_vital_signs",
            "establish_iv_access",
        ],
        deadlines={
            "calculate_plasmic_score": 60,
            "order_lab_cbc_with_smear": 30,
            "order_lab_ldh": 30,
            "order_lab_haptoglobin": 30,
        },
        source_guideline=src,
        source_section="Section 2: Diagnosis",
        source_quote=(
            "PLASMIC score >=6 indicates high probability of ADAMTS13 deficiency. "
            "Hallmark: thrombocytopenia + microangiopathic hemolytic anemia "
            "(schistocytes, elevated LDH, low haptoglobin). "
            "Do NOT wait for ADAMTS13 results to initiate treatment."
        ),
        next_nodes=["urgent_tpe"],
    )

    nodes["urgent_tpe"] = _node(
        node_id="urgent_tpe",
        node_type="action",
        name="Urgent Therapeutic Plasma Exchange (TPE)",
        description=(
            "Initiate TPE as soon as TTP is suspected — do not delay for ADAMTS13 results. "
            "Exchange 1-1.5 plasma volumes daily with FFP replacement."
        ),
        mandatory=[
            "initiate_therapeutic_plasma_exchange",
            "give_corticosteroids",
        ],
        allowed=[
            "initiate_therapeutic_plasma_exchange",
            "give_corticosteroids",
            "give_methylprednisolone_iv",
            "give_prednisone_1mg_kg",
            "place_central_venous_catheter_for_tpe",
            "give_folic_acid",
            "give_rbc_transfusion_if_symptomatic_anemia",
        ],
        forbidden=[
            "transfuse_platelets",
        ],
        deadlines={
            "initiate_therapeutic_plasma_exchange": 240,
            "give_corticosteroids": 120,
        },
        source_guideline=src,
        source_section="Section 3: Initial Treatment",
        source_quote=(
            "TPE should be initiated urgently (within 4-8 hours of diagnosis). "
            "Platelet transfusion is CONTRAINDICATED — associated with clinical "
            "deterioration and thrombosis ('fuel on the fire'). "
            "Corticosteroids (methylprednisolone 1g/day x3 or prednisone 1 mg/kg) "
            "should be started concurrently."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["caplacizumab_consideration"],
    )

    nodes["caplacizumab_consideration"] = _node(
        node_id="caplacizumab_consideration",
        node_type="action",
        name="Caplacizumab Initiation",
        description=(
            "Anti-vWF nanobody that accelerates platelet recovery and reduces "
            "thrombotic events. Administer before first TPE session."
        ),
        mandatory=[
            "give_caplacizumab",
        ],
        allowed=[
            "give_caplacizumab",
            "give_caplacizumab_11mg_iv_pre_tpe",
            "continue_caplacizumab_11mg_sc_daily",
            "monitor_for_bleeding",
        ],
        forbidden=[
            "transfuse_platelets",
        ],
        deadlines={
            "give_caplacizumab": 480,
        },
        required_prior={"give_caplacizumab": "initiate_therapeutic_plasma_exchange"},
        source_guideline=src,
        source_section="Section 3.2: Caplacizumab",
        source_quote=(
            "Caplacizumab (anti-vWF nanobody): HERCULES trial showed faster platelet "
            "normalization (2.69 vs 2.88 days), 74% reduction in composite of "
            "TTP-related death, recurrence, or thromboembolic event "
            "(Scully et al. NEJM 2019)."
        ),
        rec_class="IIa",
        evidence="B",
        next_nodes=["monitoring_response"],
    )

    nodes["monitoring_response"] = _node(
        node_id="monitoring_response",
        node_type="enquiry",
        name="Daily Monitoring & TPE Response",
        description=(
            "Daily platelet count, LDH, hemolysis markers. Continue daily TPE "
            "until platelets >150,000 for 2 consecutive days."
        ),
        mandatory=[
            "monitor_platelet_count_daily",
            "monitor_ldh_daily",
        ],
        allowed=[
            "monitor_platelet_count_daily",
            "monitor_ldh_daily",
            "monitor_haptoglobin",
            "review_adamts13_result",
            "adjust_tpe_frequency",
            "assess_neurological_status",
            "monitor_for_bleeding",
        ],
        forbidden=[
            "transfuse_platelets",
        ],
        deadlines={
            "monitor_platelet_count_daily": 1440,
            "monitor_ldh_daily": 1440,
        },
        source_guideline=src,
        source_section="Section 4: Monitoring",
        source_quote=(
            "Continue daily TPE until platelets >150,000/uL for 2 consecutive days. "
            "Rising platelet count and declining LDH indicate response. "
            "ADAMTS13 activity <10% confirms acquired TTP."
        ),
        conditional_next={
            "state.refractory_ttp == True": "refractory_management",
            "state.ttp_responding == True": "disposition",
        },
    )

    nodes["refractory_management"] = _node(
        node_id="refractory_management",
        node_type="plan",
        name="Refractory TTP Management",
        description=(
            "Refractory TTP (platelet count does not recover after 5-7 days of TPE): "
            "add rituximab, consider twice-daily TPE."
        ),
        precondition="state.refractory_ttp == True",
        mandatory=[
            "give_rituximab_375mg_m2",
            "increase_tpe_to_twice_daily",
        ],
        allowed=[
            "give_rituximab_375mg_m2",
            "increase_tpe_to_twice_daily",
            "consult_hematology",
            "consider_cyclosporine",
            "consider_bortezomib",
            "monitor_platelet_count_daily",
        ],
        forbidden=[
            "transfuse_platelets",
        ],
        deadlines={
            "give_rituximab_375mg_m2": 1440,
        },
        source_guideline=src,
        source_section="Section 5: Refractory TTP",
        source_quote=(
            "Rituximab (375 mg/m2 weekly x4) is recommended for refractory or "
            "relapsing TTP. Reduces ADAMTS13 autoantibody production. "
            "Response rate ~80-90% (Scully et al. Blood 2011)."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Long-Term ADAMTS13 Monitoring",
        description=(
            "Continue caplacizumab for 30 days after last TPE. "
            "Monitor ADAMTS13 activity monthly for relapse prediction."
        ),
        mandatory=["plan_adamts13_monitoring"],
        allowed=[
            "plan_adamts13_monitoring",
            "continue_caplacizumab_post_tpe",
            "taper_corticosteroids",
            "schedule_hematology_followup",
            "assess_organ_recovery",
        ],
        source_guideline=src,
        source_section="Section 6: Follow-Up",
        source_quote=(
            "ADAMTS13 monitoring is essential post-remission — declining activity "
            "predicts relapse. Preemptive rituximab for ADAMTS13 <20% reduces "
            "relapse (Hie et al. Blood 2014)."
        ),
    )

    return {
        "graph_id": "isth_ash_ttp_2020",
        "guideline_name": "ISTH 2020 Guidelines for Thrombotic Thrombocytopenic Purpura",
        "version": "2020.1",
        "metadata": {
            "source": "ISTH Guidelines for the Investigation and Management of TTP",
            "doi": doi,
            "journal": "Blood Advances",
            "recommendation_system": "GRADE",
            "description": (
                "Evidence-based guideline for TTP management including urgent TPE, "
                "caplacizumab, platelet transfusion prohibition, and ADAMTS13 monitoring"
            ),
            "key_evidence": (
                "TPE reduces TTP mortality from ~90% to ~10-20%. "
                "HERCULES trial: caplacizumab reduces composite endpoint by 74%. "
                "Platelet transfusion in TTP is associated with clinical deterioration "
                "(Swisher et al. Transfusion 2009). "
                "PLASMIC score has 91% sensitivity for ADAMTS13 <10% (Bendapudi et al. Blood 2017)."
            ),
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 8. Rapid Sequence Intubation (SCCM/ACS 2019)
# =========================================================================


def build_rsi_graph() -> dict[str, Any]:
    """SCCM 2019 Rapid Sequence Intubation guideline graph."""
    src = "SCCM Guidelines for RSI in Critically Ill Adults 2019"
    doi = "10.1097/CCM.0000000000003562"

    nodes: dict[str, Any] = {}

    nodes["preparation"] = _node(
        node_id="preparation",
        node_type="plan",
        name="RSI Preparation & Equipment Check",
        description=(
            "Prepare equipment (laryngoscope, ETT, suction, BVM, video laryngoscope), "
            "establish IV access, position patient, assign team roles."
        ),
        mandatory=[
            "verify_equipment_availability",
            "establish_iv_access",
            "position_patient_sniffing",
        ],
        allowed=[
            "verify_equipment_availability",
            "establish_iv_access",
            "position_patient_sniffing",
            "prepare_backup_airway",
            "apply_standard_monitors",
            "prepare_medications",
            "brief_team_roles",
            "assess_airway_anatomy",
        ],
        deadlines={
            "verify_equipment_availability": 5,
            "establish_iv_access": 5,
            "position_patient_sniffing": 5,
        },
        source_guideline=src,
        source_section="Section 1: Preparation",
        source_quote=(
            "Systematic preparation reduces first-pass failure rate. "
            "Checklist use improves outcomes in emergency intubation (Jaber et al. ICM 2010)."
        ),
        next_nodes=["preoxygenation"],
    )

    nodes["preoxygenation"] = _node(
        node_id="preoxygenation",
        node_type="action",
        name="Preoxygenation (3-5 Minutes)",
        description=(
            "Preoxygenate with high-flow oxygen or NIV for 3-5 minutes to maximize "
            "oxygen reserve. Apneic oxygenation during intubation attempt."
        ),
        mandatory=[
            "preoxygenate_3_to_5_minutes",
            "apply_nasal_cannula_for_apneic_oxygenation",
        ],
        allowed=[
            "preoxygenate_3_to_5_minutes",
            "apply_nasal_cannula_for_apneic_oxygenation",
            "preoxygenate_with_niv",
            "preoxygenate_with_hfnc",
            "elevate_head_of_bed_25_degrees",
            "monitor_spo2_continuously",
        ],
        forbidden=[
            "skip_preoxygenation",
        ],
        deadlines={
            "preoxygenate_3_to_5_minutes": 10,
            "apply_nasal_cannula_for_apneic_oxygenation": 10,
        },
        source_guideline=src,
        source_section="Section 2: Preoxygenation",
        source_quote=(
            "Preoxygenation extends safe apnea time from ~1 min (room air) to "
            "~8 min (100% O2). Apneic oxygenation with nasal cannula 15 L/min "
            "during laryngoscopy extends safe apnea time further "
            "(Weingart & Levitan, Ann Emerg Med 2012)."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["induction_paralysis"],
    )

    nodes["induction_paralysis"] = _node(
        node_id="induction_paralysis",
        node_type="action",
        name="Induction & Neuromuscular Blockade",
        description=(
            "Administer induction agent (etomidate, ketamine, or propofol) "
            "immediately followed by paralytic (succinylcholine or rocuronium). "
            "No bag-mask ventilation between induction and intubation (RSI principle)."
        ),
        mandatory=[
            "give_induction_agent",
            "give_neuromuscular_blocker",
        ],
        allowed=[
            "give_induction_agent",
            "give_neuromuscular_blocker",
            "give_etomidate_0_3mg_kg",
            "give_ketamine_1_5mg_kg",
            "give_propofol_1_5mg_kg",
            "give_succinylcholine_1_5mg_kg",
            "give_rocuronium_1_2mg_kg",
            "wait_45_to_60_seconds_for_onset",
        ],
        forbidden=[
            "give_bmv_between_induction_and_intubation",
        ],
        deadlines={
            "give_induction_agent": 2,
            "give_neuromuscular_blocker": 2,
        },
        required_prior={"give_neuromuscular_blocker": "give_induction_agent"},
        source_guideline=src,
        source_section="Section 3: Induction & Paralysis",
        source_quote=(
            "RSI: induction and paralytic given in rapid succession without "
            "intervening bag-mask ventilation to minimize aspiration risk. "
            "Etomidate and ketamine have the most favorable hemodynamic profiles "
            "in critically ill patients (Jabre et al. Lancet 2009)."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["laryngoscopy_intubation"],
    )

    nodes["laryngoscopy_intubation"] = _node(
        node_id="laryngoscopy_intubation",
        node_type="action",
        name="Laryngoscopy & Tube Placement",
        description=(
            "Perform laryngoscopy (video preferred in ICU). Place ETT and "
            "confirm position with continuous waveform capnography (ETCO2)."
        ),
        mandatory=[
            "perform_laryngoscopy",
            "place_endotracheal_tube",
            "confirm_placement_with_etco2",
        ],
        allowed=[
            "perform_laryngoscopy",
            "place_endotracheal_tube",
            "confirm_placement_with_etco2",
            "use_video_laryngoscopy",
            "apply_external_laryngeal_manipulation",
            "use_bougie",
            "auscultate_bilateral_breath_sounds",
        ],
        forbidden=[
            "confirm_placement_by_auscultation_alone",
        ],
        deadlines={
            "perform_laryngoscopy": 2,
            "confirm_placement_with_etco2": 5,
        },
        source_guideline=src,
        source_section="Section 4: Laryngoscopy & Confirmation",
        source_quote=(
            "Continuous waveform capnography is the gold standard for confirming "
            "endotracheal tube placement (Class I, Level A). Video laryngoscopy "
            "improves first-pass success rate in ICU patients "
            "(Lascarrou et al. JAMA 2017)."
        ),
        rec_class="I",
        evidence="A",
        next_nodes=["post_intubation_care"],
    )

    nodes["post_intubation_care"] = _node(
        node_id="post_intubation_care",
        node_type="plan",
        name="Post-Intubation Care",
        description=(
            "Initiate mechanical ventilation, confirm CXR, initiate sedation, "
            "secure tube, prevent VAP bundle."
        ),
        mandatory=[
            "initiate_mechanical_ventilation",
            "order_imaging_chest_xray_post_intubation",
            "initiate_sedation",
        ],
        allowed=[
            "initiate_mechanical_ventilation",
            "order_imaging_chest_xray_post_intubation",
            "initiate_sedation",
            "set_initial_ventilator_settings",
            "order_lab_abg",
            "secure_endotracheal_tube",
            "initiate_vap_prevention_bundle",
            "place_orogastric_tube",
            "document_intubation_details",
        ],
        deadlines={
            "initiate_mechanical_ventilation": 5,
            "order_imaging_chest_xray_post_intubation": 30,
            "initiate_sedation": 15,
        },
        source_guideline=src,
        source_section="Section 5: Post-Intubation Management",
        source_quote=(
            "Post-intubation hypotension occurs in ~25% of critically ill patients. "
            "Lung-protective ventilation should be initiated immediately. "
            "CXR confirms tube depth (2-6 cm above carina)."
        ),
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Ongoing Ventilator Management",
        description=(
            "Titrate ventilator settings to lung-protective targets, "
            "initiate daily SBT screening, plan for extubation."
        ),
        mandatory=["assess_ventilator_settings"],
        allowed=[
            "assess_ventilator_settings",
            "set_tidal_volume_6ml_kg_ibw",
            "target_plateau_pressure_below_30",
            "initiate_daily_sedation_vacation",
            "screen_for_sbt_readiness",
        ],
        source_guideline=src,
        source_section="Section 6: Ventilator Management",
        source_quote=(
            "Lung-protective ventilation (Vt 6 mL/kg IBW, Pplat <30 cmH2O) "
            "should be initiated in all intubated ICU patients."
        ),
    )

    return {
        "graph_id": "sccm_rsi_2019",
        "guideline_name": "SCCM 2019 Guidelines for Rapid Sequence Intubation in Critically Ill Adults",
        "version": "2019.1",
        "metadata": {
            "source": "SCCM Clinical Practice Guidelines for RSI in Critically Ill Adults",
            "doi": doi,
            "journal": "Critical Care Medicine",
            "recommendation_system": "GRADE",
            "description": (
                "Evidence-based guideline for RSI in critically ill adults "
                "including preoxygenation, induction/paralysis, video laryngoscopy, "
                "ETCO2 confirmation, and post-intubation management"
            ),
            "key_evidence": (
                "Video laryngoscopy increases first-pass success from 71% to 82% "
                "in ICU (Lascarrou JAMA 2017). Apneic oxygenation extends safe apnea "
                "time by 2-4 minutes (Weingart & Levitan). Post-intubation hypotension "
                "occurs in 25% of critically ill patients."
            ),
        },
        "entry_node": "preparation",
        "nodes": nodes,
    }


# =========================================================================
# 9. Maternal Sepsis (SMFM/ACOG 2019)
# =========================================================================


def build_maternal_sepsis_graph() -> dict[str, Any]:
    """SMFM/ACOG 2019 Maternal Sepsis guideline graph."""
    src = "SMFM/ACOG 2019 Guidelines for Maternal Sepsis"
    doi = "10.1097/AOG.0000000000003467"

    nodes: dict[str, Any] = {}

    nodes["sepsis_screening"] = _node(
        node_id="sepsis_screening",
        node_type="decision",
        name="Maternal Sepsis Screening (Modified qSOFA/SIRS)",
        description=(
            "Screen for sepsis using pregnancy-modified criteria. "
            "Normal pregnancy values differ: HR up to 100, WBC up to 16,000, "
            "RR up to 20 may be physiological."
        ),
        mandatory=[
            "screen_maternal_sepsis_criteria",
            "assess_vital_signs",
            "order_lab_lactate",
        ],
        allowed=[
            "screen_maternal_sepsis_criteria",
            "assess_vital_signs",
            "order_lab_lactate",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_blood_culture",
            "order_lab_urinalysis",
            "order_lab_procalcitonin",
            "assess_fetal_heart_rate",
            "establish_iv_access",
        ],
        deadlines={
            "screen_maternal_sepsis_criteria": 15,
            "assess_vital_signs": 10,
            "order_lab_lactate": 30,
        },
        source_guideline=src,
        source_section="Section 1: Recognition in Pregnancy",
        source_quote=(
            "Sepsis criteria must be modified for pregnancy. Normal physiological "
            "changes (increased HR, WBC, decreased BP) can mask sepsis. "
            "Maternal early warning criteria: HR >110, RR >24, SBP <90, "
            "T >38C or <36C, WBC >17,000."
        ),
        next_nodes=["initial_resuscitation"],
    )

    nodes["initial_resuscitation"] = _node(
        node_id="initial_resuscitation",
        node_type="action",
        name="Hour-1 Sepsis Bundle (Adapted for Pregnancy)",
        description=(
            "Blood cultures before antibiotics, empiric IV antibiotics within 1 hour, "
            "crystalloid 30 mL/kg. In pregnancy, consider left lateral tilt and "
            "modified fluid targets."
        ),
        mandatory=[
            "order_lab_blood_culture",
            "give_iv_antibiotics_within_1_hour",
            "give_crystalloid_30ml_kg",
        ],
        allowed=[
            "order_lab_blood_culture",
            "give_iv_antibiotics_within_1_hour",
            "give_crystalloid_30ml_kg",
            "give_ampicillin_sulbactam_iv",
            "give_piperacillin_tazobactam_iv",
            "give_ceftriaxone_plus_metronidazole",
            "position_left_lateral_tilt",
            "reassess_lactate_at_6_hours",
            "monitor_urine_output",
        ],
        forbidden=[
            "delay_antibiotics_for_culture_results",
        ],
        deadlines={
            "order_lab_blood_culture": 30,
            "give_iv_antibiotics_within_1_hour": 60,
            "give_crystalloid_30ml_kg": 180,
        },
        required_prior={"give_iv_antibiotics_within_1_hour": "order_lab_blood_culture"},
        source_guideline=src,
        source_section="Section 2: Initial Resuscitation",
        source_quote=(
            "Hour-1 bundle: blood cultures, broad-spectrum antibiotics within 1 hour, "
            "crystalloid 30 mL/kg. Each hour of delay in antibiotics increases "
            "mortality by ~4% (Kumar et al. Crit Care Med 2006). "
            "Consider chorioamnionitis, endometritis, pyelonephritis as sources."
        ),
        rec_class="I",
        evidence="A",
        next_nodes=["hemodynamic_management"],
    )

    nodes["hemodynamic_management"] = _node(
        node_id="hemodynamic_management",
        node_type="plan",
        name="Hemodynamic Management & Vasopressors",
        description=(
            "If MAP <65 mmHg despite fluids, start norepinephrine. "
            "In pregnancy, maintain MAP >=65 to ensure uteroplacental perfusion."
        ),
        mandatory=[
            "assess_map_after_fluids",
            "initiate_fetal_monitoring",
        ],
        allowed=[
            "assess_map_after_fluids",
            "initiate_fetal_monitoring",
            "start_vasopressor_norepinephrine",
            "place_central_line",
            "place_arterial_line",
            "order_lab_lactate_repeat",
            "reassess_fluid_responsiveness",
            "position_left_lateral_tilt",
        ],
        deadlines={
            "assess_map_after_fluids": 180,
            "initiate_fetal_monitoring": 30,
        },
        conditional_rules=[
            {
                "rule_id": "MATSEP-VASOPRESSOR",
                "condition": "state.map_mmhg < 65",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["start_vasopressor_norepinephrine"],
                    "deadline_minutes": 30,
                },
                "severity": "CRITICAL",
                "description": (
                    "MAP <65 mmHg despite 30 mL/kg crystalloid requires vasopressor. "
                    "Norepinephrine preferred — least impact on uteroplacental flow."
                ),
            },
        ],
        source_guideline=src,
        source_section="Section 3: Hemodynamic Support",
        source_quote=(
            "Norepinephrine is the first-line vasopressor in maternal sepsis. "
            "Phenylephrine should be avoided (reduces uterine blood flow). "
            "Maintain MAP >=65 mmHg to ensure adequate uteroplacental perfusion."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["source_control"],
    )

    nodes["source_control"] = _node(
        node_id="source_control",
        node_type="action",
        name="Source Control & Delivery Consideration",
        description=(
            "Identify and control infection source (chorioamnionitis, endometritis, "
            "pyelonephritis, wound infection). Consider delivery if chorioamnionitis "
            "is the source or if fetal status is non-reassuring."
        ),
        mandatory=[
            "identify_infection_source",
            "assess_delivery_indication",
        ],
        allowed=[
            "identify_infection_source",
            "assess_delivery_indication",
            "consider_delivery_for_source_control",
            "order_imaging_ultrasound",
            "consult_maternal_fetal_medicine",
            "consult_surgery_if_abscess",
            "drain_abscess_if_identified",
        ],
        deadlines={
            "identify_infection_source": 360,
            "assess_delivery_indication": 360,
        },
        conditional_rules=[
            {
                "rule_id": "MATSEP-DELIVERY",
                "condition": "state.chorioamnionitis == True or state.fetal_distress == True",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["consider_delivery_for_source_control"],
                    "deadline_minutes": 120,
                },
                "severity": "CRITICAL",
                "description": (
                    "Chorioamnionitis with maternal sepsis: delivery is part of "
                    "source control. Non-reassuring fetal status may also mandate delivery."
                ),
            },
        ],
        source_guideline=src,
        source_section="Section 4: Source Control",
        source_quote=(
            "Source control is critical in maternal sepsis. Delivery should be "
            "considered as source control for chorioamnionitis-related sepsis. "
            "Gestational age and fetal status guide timing."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["monitoring_reassessment"] = _node(
        node_id="monitoring_reassessment",
        node_type="enquiry",
        name="Maternal & Fetal Monitoring",
        description=(
            "Serial lactate, vital signs, fetal heart rate monitoring. "
            "Reassess antibiotic adequacy and organ function."
        ),
        mandatory=[
            "monitor_lactate_serial",
            "continue_fetal_monitoring",
        ],
        allowed=[
            "monitor_lactate_serial",
            "continue_fetal_monitoring",
            "order_lab_cbc",
            "order_lab_bmp",
            "reassess_vital_signs",
            "monitor_urine_output",
            "assess_organ_function",
        ],
        deadlines={
            "monitor_lactate_serial": 360,
            "continue_fetal_monitoring": 60,
        },
        source_guideline=src,
        source_section="Section 5: Monitoring",
        source_quote=(
            "Lactate clearance >10% within 6 hours is a marker of adequate "
            "resuscitation. Continuous fetal monitoring is recommended in "
            "viable gestations with maternal sepsis."
        ),
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Postpartum Care",
        description=(
            "Assess organ recovery, de-escalate antibiotics, "
            "plan postpartum follow-up."
        ),
        mandatory=["assess_clinical_improvement"],
        allowed=[
            "assess_clinical_improvement",
            "de_escalate_antibiotics",
            "plan_postpartum_followup",
            "provide_sepsis_survivorship_counseling",
            "assess_neonatal_status",
        ],
        source_guideline=src,
        source_section="Section 6: Disposition",
        source_quote=(
            "Maternal sepsis survivors have increased risk of postpartum "
            "depression, PTSD, and long-term organ dysfunction. "
            "Follow-up should address both physical and psychological recovery."
        ),
    )

    return {
        "graph_id": "smfm_maternal_sepsis_2019",
        "guideline_name": "SMFM/ACOG 2019 Guidelines for Maternal Sepsis",
        "version": "2019.1",
        "metadata": {
            "source": "SMFM Consult Series: Sepsis During Pregnancy and the Puerperium",
            "doi": doi,
            "journal": "Obstetrics & Gynecology",
            "recommendation_system": "ACOG Level of Evidence",
            "description": (
                "Guideline for maternal sepsis including pregnancy-modified screening "
                "criteria, hour-1 bundle, vasopressor selection, fetal monitoring, "
                "and delivery as source control"
            ),
            "key_evidence": (
                "Maternal sepsis mortality is 4-10% in developed countries. "
                "Each hour of antibiotic delay increases mortality ~4% (Kumar et al.). "
                "Norepinephrine has least impact on uteroplacental flow vs other vasopressors "
                "(Sligl et al. Obstet Gynecol 2014). "
                "Chorioamnionitis is the leading cause of maternal sepsis."
            ),
        },
        "entry_node": "sepsis_screening",
        "nodes": nodes,
    }


# =========================================================================
# 10. Pelvic Trauma & REBOA (WSES 2017)
# =========================================================================


def build_pelvic_trauma_reboa_graph() -> dict[str, Any]:
    """WSES 2017 Pelvic Trauma & REBOA guideline graph."""
    src = "WSES 2017 Guidelines for Pelvic Trauma Management"
    doi = "10.1186/s13017-017-0149-0"

    nodes: dict[str, Any] = {}

    nodes["hemodynamic_assessment"] = _node(
        node_id="hemodynamic_assessment",
        node_type="decision",
        name="Hemodynamic Assessment & Pelvic Binder",
        description=(
            "Assess hemodynamic stability in pelvic trauma. Apply pelvic binder "
            "immediately for suspected unstable pelvic fracture. FAST exam."
        ),
        mandatory=[
            "assess_hemodynamic_status",
            "apply_pelvic_binder",
            "perform_fast_exam",
        ],
        allowed=[
            "assess_hemodynamic_status",
            "apply_pelvic_binder",
            "perform_fast_exam",
            "assess_vital_signs",
            "order_lab_cbc",
            "order_lab_coagulation",
            "order_lab_blood_type_crossmatch",
            "establish_large_bore_iv_access",
            "order_lab_lactate",
            "order_lab_base_deficit",
        ],
        deadlines={
            "assess_hemodynamic_status": 5,
            "apply_pelvic_binder": 10,
            "perform_fast_exam": 15,
        },
        source_guideline=src,
        source_section="Section 2: Initial Assessment",
        source_quote=(
            "Pelvic binder application is the first step in hemorrhage control "
            "for suspected unstable pelvic ring injury. FAST exam assesses "
            "for free intraperitoneal fluid."
        ),
        rec_class="I",
        evidence="B",
        conditional_next={
            "state.hemodynamically_unstable == True": "hemorrhage_control",
            "state.hemodynamically_stable == True": "ct_evaluation",
        },
    )

    nodes["hemorrhage_control"] = _node(
        node_id="hemorrhage_control",
        node_type="action",
        name="Massive Transfusion & REBOA Consideration",
        description=(
            "Activate massive transfusion protocol (1:1:1 ratio). "
            "Consider REBOA (Zone 3) as temporizing measure in hemodynamically "
            "unstable patients not responding to initial resuscitation."
        ),
        precondition="state.hemodynamically_unstable == True",
        mandatory=[
            "activate_massive_transfusion_protocol",
            "give_tranexamic_acid_1g",
        ],
        allowed=[
            "activate_massive_transfusion_protocol",
            "give_tranexamic_acid_1g",
            "transfuse_prbc_ffp_platelets_1_1_1",
            "consider_reboa_zone_3",
            "perform_reboa_zone_3",
            "give_calcium_chloride_for_transfusion",
            "reassess_hemodynamic_status",
            "order_lab_fibrinogen",
            "give_cryoprecipitate_if_fibrinogen_low",
        ],
        forbidden=[
            "perform_reboa_zone_1_for_pelvic_injury",
        ],
        deadlines={
            "activate_massive_transfusion_protocol": 15,
            "give_tranexamic_acid_1g": 60,
        },
        conditional_rules=[
            {
                "rule_id": "PELVIS-REBOA",
                "condition": "state.sbp < 70 and state.pelvic_hemorrhage == True",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["perform_reboa_zone_3"],
                    "deadline_minutes": 30,
                },
                "severity": "CRITICAL",
                "description": (
                    "REBOA in Zone 3 (infrarenal aorta) provides temporary "
                    "hemorrhage control in exsanguinating pelvic trauma. "
                    "Do NOT place in Zone 1 for pelvic hemorrhage alone."
                ),
            },
        ],
        source_guideline=src,
        source_section="Section 3: Hemorrhage Control",
        source_quote=(
            "Massive transfusion with 1:1:1 ratio (PRBC:FFP:PLT). TXA within "
            "3 hours of injury (CRASH-2 trial). REBOA Zone 3 is a bridge to "
            "definitive hemorrhage control — not a definitive treatment."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["surgical_intervention"],
    )

    nodes["ct_evaluation"] = _node(
        node_id="ct_evaluation",
        node_type="enquiry",
        name="CT with Contrast & Fracture Classification",
        description=(
            "CT abdomen/pelvis with IV contrast for hemodynamically stable patients. "
            "Identify active arterial extravasation, fracture pattern (Tile/Young-Burgess)."
        ),
        precondition="state.hemodynamically_stable == True",
        mandatory=[
            "order_imaging_ct_pelvis_with_contrast",
            "classify_fracture_pattern",
        ],
        allowed=[
            "order_imaging_ct_pelvis_with_contrast",
            "classify_fracture_pattern",
            "order_imaging_ct_abdomen",
            "identify_active_extravasation",
            "assess_bladder_injury",
            "assess_urethral_injury",
            "consult_orthopedic_surgery",
        ],
        deadlines={
            "order_imaging_ct_pelvis_with_contrast": 60,
        },
        source_guideline=src,
        source_section="Section 4: Imaging",
        source_quote=(
            "CT with IV contrast is the gold standard for assessing pelvic fracture "
            "severity, vascular injury, and concomitant intra-abdominal injury. "
            "Active extravasation on CT indicates need for angioembolization."
        ),
        conditional_next={
            "state.active_extravasation == True": "surgical_intervention",
            "state.active_extravasation == False": "monitoring_reassessment",
        },
    )

    nodes["surgical_intervention"] = _node(
        node_id="surgical_intervention",
        node_type="action",
        name="Angioembolization or Preperitoneal Packing",
        description=(
            "Angioembolization for arterial bleeding identified on CT/angiography. "
            "Preperitoneal pelvic packing (PPP) for diffuse venous bleeding or "
            "when angioembolization is not available."
        ),
        mandatory=[
            "perform_definitive_hemorrhage_control",
        ],
        allowed=[
            "perform_definitive_hemorrhage_control",
            "perform_angioembolization",
            "perform_preperitoneal_packing",
            "perform_external_fixation",
            "consult_interventional_radiology",
            "consult_orthopedic_surgery",
            "reassess_hemodynamic_status",
            "continue_transfusion_support",
        ],
        deadlines={
            "perform_definitive_hemorrhage_control": 120,
        },
        source_guideline=src,
        source_section="Section 5: Surgical Management",
        source_quote=(
            "Angioembolization controls arterial bleeding in 80-100% of cases. "
            "Preperitoneal packing is faster, does not require specialized "
            "equipment, and controls venous bleeding more effectively. "
            "Combined approach may be needed for mixed arteriovenous injury."
        ),
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["monitoring_reassessment"] = _node(
        node_id="monitoring_reassessment",
        node_type="enquiry",
        name="ICU Monitoring & Coagulopathy Correction",
        description=(
            "Monitor for ongoing hemorrhage, correct coagulopathy (lethal triad: "
            "hypothermia, acidosis, coagulopathy). Serial labs."
        ),
        mandatory=[
            "monitor_hemodynamic_status",
            "correct_coagulopathy",
        ],
        allowed=[
            "monitor_hemodynamic_status",
            "correct_coagulopathy",
            "order_lab_cbc_serial",
            "order_lab_coagulation_serial",
            "order_lab_lactate_serial",
            "reassess_pelvic_binder",
            "monitor_compartment_pressures",
            "rewarm_patient",
        ],
        deadlines={
            "monitor_hemodynamic_status": 60,
            "correct_coagulopathy": 120,
        },
        source_guideline=src,
        source_section="Section 6: ICU Management",
        source_quote=(
            "Resuscitation targets: pH >7.2, temperature >35C, fibrinogen >1.5 g/L, "
            "platelets >50,000. The lethal triad (hypothermia, acidosis, coagulopathy) "
            "is the primary driver of non-surgical mortality in pelvic trauma."
        ),
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Definitive Fracture Management",
        description=(
            "Plan definitive fracture fixation once hemodynamically stable. "
            "VTE prophylaxis, rehabilitation planning."
        ),
        mandatory=["plan_definitive_fixation"],
        allowed=[
            "plan_definitive_fixation",
            "initiate_vte_prophylaxis",
            "consult_rehabilitation",
            "remove_pelvic_binder_when_stable",
            "schedule_follow_up_imaging",
        ],
        source_guideline=src,
        source_section="Section 7: Definitive Management",
        source_quote=(
            "Definitive internal fixation is typically performed within 5-7 days "
            "once the patient is hemodynamically stable. Early VTE prophylaxis "
            "is recommended given high DVT/PE risk in pelvic fractures."
        ),
    )

    return {
        "graph_id": "wses_pelvic_trauma_reboa_2017",
        "guideline_name": "WSES 2017 Classification and Guidelines for Pelvic Trauma",
        "version": "2017.1",
        "metadata": {
            "source": "World Society of Emergency Surgery Classification and Guidelines for Pelvic Trauma",
            "doi": doi,
            "journal": "World Journal of Emergency Surgery",
            "recommendation_system": "GRADE",
            "description": (
                "Evidence-based guideline for hemodynamically unstable pelvic trauma "
                "including pelvic binder, massive transfusion, REBOA Zone 3, "
                "angioembolization, and preperitoneal packing"
            ),
            "key_evidence": (
                "Pelvic binder reduces pelvic volume and tamponades venous bleeding. "
                "REBOA Zone 3 provides 60-90 min bridge to definitive hemostasis. "
                "TXA within 3 hours reduces mortality (CRASH-2: OR 0.72). "
                "Angioembolization success rate 80-100% for arterial pelvic hemorrhage."
            ),
        },
        "entry_node": "hemodynamic_assessment",
        "nodes": nodes,
    }


# =========================================================================
# Graph Builder Registry
# =========================================================================

GRAPH_BUILDERS: dict[str, callable] = {
    "obstructive_pyelonephritis": build_obstructive_pyelonephritis_graph,
    "drowning": build_drowning_graph,
    "niv": build_niv_graph,
    "pediatric_asthma": build_pediatric_asthma_graph,
    "vt_sd": build_vt_sd_graph,
    "cdi": build_cdi_graph,
    "ttp": build_ttp_graph,
    "rsi": build_rsi_graph,
    "maternal_sepsis": build_maternal_sepsis_graph,
    "pelvic_trauma_reboa": build_pelvic_trauma_reboa_graph,
}


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3 Batch 2: Score-17 expansion graphs")
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
