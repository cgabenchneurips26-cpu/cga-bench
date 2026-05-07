"""Phase 3: Batch YAML graph generation for top expansion candidates.

Generates CPG graph YAMLs for the highest-scoring expansion candidates
using domain-specific clinical knowledge templates. Each graph follows
the same schema as existing hand-crafted graphs in cpg_model/graphs/.

Pilot batch: 3 candidates (19/19 C1-C12 scores)
  1. ats_esicm_sccm_ards_2023 — ARDS management
  2. sccm_pediatric_septic_shock_2020 — Pediatric septic shock
  3. ncs_aha_sah_2023 — Aneurysmal subarachnoid hemorrhage

Score-18 batch: 8 candidates
  4. aha_cardiogenic_shock_2017 — AHA/ACC Cardiogenic Shock
  5. aha_ttm_post_arrest_2023 — AHA/ILCOR Post-Arrest TTM
  6. bts_pleural_disease_2023 — BTS Pleural Disease
  7. erc_hypothermia_2021 — ERC Accidental Hypothermia
  8. esvs_acute_limb_ischemia_2020 — ESVS Acute Limb Ischemia
  9. ispad_pediatric_dka_2022 — ISPAD Pediatric DKA
 10. ukka_hyperkalemia_2023 — UK Kidney Association Hyperkalemia
 11. who_severe_malaria_2023 — WHO Severe Malaria

Usage:
    PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs.py
    PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs.py --dry-run
    PYTHONPATH=. python scripts/cpg_v2_phase3/generate_expansion_graphs.py --graph ards
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = REPO_ROOT / "cpg_model" / "graphs" / "auto"


def _node(
    node_id: str,
    node_type: str,
    name: str,
    description: str,
    mandatory: list[str],
    allowed: list[str],
    forbidden: list[str] | None = None,
    deadlines: dict[str, int] | None = None,
    required_prior: dict[str, str | list[str]] | None = None,
    rec_class: str = "I",
    evidence: str = "B",
    source_guideline: str = "",
    source_section: str = "",
    source_quote: str = "",
    next_nodes: list[str] | None = None,
    conditional_next: dict[str, str] | None = None,
    precondition: str | None = None,
    conditional_rules: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Helper to build a schema-compliant node dict."""
    node: dict[str, Any] = {
        "node_id": node_id,
        "node_type": node_type,
        "name": name,
        "description": description,
        "precondition": precondition,
        "mandatory_actions": mandatory,
        "allowed_actions": list(set(mandatory) | set(allowed)),
        "forbidden_actions": forbidden or [],
        "deadlines": deadlines or {},
        "required_prior_actions": {
            k: ([v] if isinstance(v, str) else list(v)) for k, v in (required_prior or {}).items()
        },
        "recommendation_class": rec_class,
        "evidence_level": evidence,
        "source_guideline": source_guideline,
        "source_section": source_section,
        "source_page": None,
        "source_quote": source_quote,
        "next_nodes": next_nodes or [],
        "conditional_next": conditional_next or {},
    }
    if conditional_rules:
        node["conditional_rules"] = conditional_rules
    return node


# =========================================================================
# 1. ARDS (ATS/ESICM/SCCM 2023)
# =========================================================================


def build_ards_graph() -> dict[str, Any]:
    """ATS/ESICM/SCCM ARDS 2023 guideline graph."""
    src = "ATS/ESICM/SCCM ARDS 2023"
    doi = "10.1007/s00134-023-07050-7"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="ARDS Recognition & Severity Classification",
        description="Identify ARDS per Berlin Definition, classify severity by PaO2/FiO2 ratio",
        mandatory=["assess_respiratory_status", "order_lab_abg", "order_imaging_chest_xray"],
        allowed=[
            "assess_respiratory_status",
            "order_lab_abg",
            "order_imaging_chest_xray",
            "order_imaging_ct_chest",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_bnp",
            "order_lab_procalcitonin",
            "order_lab_blood_culture",
            "assess_vital_signs",
            "order_lab_lactate",
        ],
        deadlines={
            "assess_respiratory_status": 15,
            "order_lab_abg": 30,
            "order_imaging_chest_xray": 30,
        },
        source_guideline=src,
        source_section="Berlin Definition / Initial Evaluation",
        source_quote="ARDS: acute onset, bilateral opacities on CXR, PaO2/FiO2 ≤300 mmHg with PEEP ≥5 cmH2O",
        conditional_next={
            "state.pf_ratio <= 100": "severe_ards_bundle",
            "state.pf_ratio <= 200": "moderate_ards_bundle",
            "state.pf_ratio <= 300": "mild_ards_bundle",
        },
    )

    nodes["mild_ards_bundle"] = _node(
        node_id="mild_ards_bundle",
        node_type="plan",
        name="Mild ARDS Management (PaO2/FiO2 200-300)",
        description="Low tidal volume ventilation, conservative fluid strategy",
        precondition="state.pf_ratio > 200 and state.pf_ratio <= 300",
        mandatory=[
            "initiate_low_tv_ventilation",
            "set_tidal_volume_6ml_kg_ibw",
            "set_peep_5_to_8",
            "target_plateau_pressure_below_30",
        ],
        allowed=[
            "initiate_low_tv_ventilation",
            "set_tidal_volume_6ml_kg_ibw",
            "set_peep_5_to_8",
            "target_plateau_pressure_below_30",
            "order_lab_abg",
            "reassess_pf_ratio",
            "conservative_fluid_strategy",
            "treat_underlying_cause",
            "order_lab_cbc",
            "order_lab_bmp",
        ],
        forbidden=["set_tidal_volume_above_8ml_kg"],
        deadlines={
            "initiate_low_tv_ventilation": 60,
            "set_tidal_volume_6ml_kg_ibw": 60,
        },
        source_guideline=src,
        source_section="Recommendation 1: Mechanical Ventilation",
        source_quote="We recommend low tidal volume ventilation (Vt 4-8 mL/kg PBW, target 6 mL/kg) in all patients with ARDS (strong recommendation, moderate certainty)",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["moderate_ards_bundle"] = _node(
        node_id="moderate_ards_bundle",
        node_type="plan",
        name="Moderate ARDS Management (PaO2/FiO2 100-200)",
        description="Low TV ventilation + higher PEEP + prone positioning consideration",
        precondition="state.pf_ratio > 100 and state.pf_ratio <= 200",
        mandatory=[
            "initiate_low_tv_ventilation",
            "set_tidal_volume_6ml_kg_ibw",
            "set_peep_10_to_14",
            "target_plateau_pressure_below_30",
            "consider_prone_positioning",
        ],
        allowed=[
            "initiate_low_tv_ventilation",
            "set_tidal_volume_6ml_kg_ibw",
            "set_peep_10_to_14",
            "target_plateau_pressure_below_30",
            "consider_prone_positioning",
            "initiate_prone_positioning_16hr",
            "conservative_fluid_strategy",
            "order_lab_abg",
            "reassess_pf_ratio",
            "place_arterial_line",
            "treat_underlying_cause",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_lactate",
        ],
        forbidden=["set_tidal_volume_above_8ml_kg", "liberal_fluid_strategy"],
        deadlines={
            "initiate_low_tv_ventilation": 60,
            "set_tidal_volume_6ml_kg_ibw": 60,
            "consider_prone_positioning": 120,
        },
        source_guideline=src,
        source_section="Recommendation 2-4: Higher PEEP, Prone Positioning",
        source_quote="We suggest higher PEEP strategy in moderate-to-severe ARDS. We recommend prone positioning for >12 h/day in patients with moderate-to-severe ARDS",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["severe_ards_bundle"] = _node(
        node_id="severe_ards_bundle",
        node_type="plan",
        name="Severe ARDS Management (PaO2/FiO2 ≤100)",
        description="Low TV + high PEEP + mandatory prone positioning + consider ECMO/NMBA",
        precondition="state.pf_ratio <= 100",
        mandatory=[
            "initiate_low_tv_ventilation",
            "set_tidal_volume_6ml_kg_ibw",
            "set_peep_14_or_higher",
            "target_plateau_pressure_below_30",
            "initiate_prone_positioning_16hr",
        ],
        allowed=[
            "initiate_low_tv_ventilation",
            "set_tidal_volume_6ml_kg_ibw",
            "set_peep_14_or_higher",
            "target_plateau_pressure_below_30",
            "initiate_prone_positioning_16hr",
            "give_neuromuscular_blockade",
            "consider_ecmo_referral",
            "conservative_fluid_strategy",
            "place_arterial_line",
            "place_central_line",
            "order_lab_abg",
            "reassess_pf_ratio",
            "order_lab_lactate",
            "treat_underlying_cause",
        ],
        forbidden=["set_tidal_volume_above_8ml_kg", "liberal_fluid_strategy"],
        deadlines={
            "initiate_low_tv_ventilation": 30,
            "set_tidal_volume_6ml_kg_ibw": 30,
            "initiate_prone_positioning_16hr": 60,
        },
        required_prior={"give_neuromuscular_blockade": "initiate_low_tv_ventilation"},
        source_guideline=src,
        source_section="Recommendation 2-6: Severe ARDS Bundle",
        source_quote="We recommend prone positioning for >12 h/day (strong, moderate certainty). We suggest NMBA infusion in early severe ARDS with PaO2/FiO2 <150 (conditional, moderate certainty)",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["monitoring_reassessment"] = _node(
        node_id="monitoring_reassessment",
        node_type="enquiry",
        name="Monitoring & Reassessment",
        description="Serial ABG, plateau pressure monitoring, reassess severity classification",
        mandatory=["reassess_pf_ratio", "monitor_plateau_pressure"],
        allowed=[
            "reassess_pf_ratio",
            "monitor_plateau_pressure",
            "order_lab_abg",
            "assess_respiratory_status",
            "monitor_driving_pressure",
            "assess_fluid_balance",
            "monitor_sedation_level",
        ],
        deadlines={"reassess_pf_ratio": 360, "monitor_plateau_pressure": 120},
        source_guideline=src,
        source_section="Monitoring",
        source_quote="Serial assessment of oxygenation, ventilator parameters, and organ function",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Liberation",
        description="Assess readiness for ventilator weaning, SBT, and ICU transfer",
        mandatory=["assess_weaning_readiness"],
        allowed=[
            "assess_weaning_readiness",
            "perform_sbt",
            "reduce_fio2",
            "reduce_peep",
            "extubate",
            "continue_monitoring",
        ],
        source_guideline=src,
        source_section="Liberation from Mechanical Ventilation",
        source_quote="Daily screening for weaning readiness; SBT when clinically appropriate",
    )

    return {
        "graph_id": "ats_esicm_sccm_ards_2023",
        "guideline_name": "ESICM Guidelines on Acute Respiratory Distress Syndrome (2023)",
        "version": "2023.1",
        "metadata": {
            "source": "ATS/ESICM/SCCM ARDS Clinical Practice Guideline 2023",
            "doi": doi,
            "journal": "Intensive Care Medicine",
            "recommendation_system": "GRADE",
            "description": "Evidence-based guideline for ARDS management including lung-protective ventilation, prone positioning, and adjunctive therapies",
            "key_evidence": "Low tidal volume (6 mL/kg PBW) reduces mortality by 22% vs 12 mL/kg (ARDSNet ARMA trial). Prone positioning >12h reduces 28-day mortality (PROSEVA trial, RR 0.51).",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 2. Pediatric Septic Shock (SCCM 2020)
# =========================================================================


def build_pediatric_sepsis_graph() -> dict[str, Any]:
    """SCCM Pediatric Septic Shock 2020 guideline graph."""
    src = "SCCM Pediatric Septic Shock 2020"
    doi = "10.1097/PCC.0000000000002198"

    nodes: dict[str, Any] = {}

    nodes["initial_recognition"] = _node(
        node_id="initial_recognition",
        node_type="decision",
        name="Pediatric Sepsis Recognition",
        description="Identify sepsis/septic shock in pediatric patient, assess perfusion",
        mandatory=["assess_perfusion_status", "assess_mental_status", "assess_vital_signs"],
        allowed=[
            "assess_perfusion_status",
            "assess_mental_status",
            "assess_vital_signs",
            "order_lab_lactate",
            "order_lab_blood_culture",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_blood_gas",
            "order_lab_coagulation",
            "establish_iv_access",
            "establish_io_access",
        ],
        deadlines={
            "assess_perfusion_status": 5,
            "assess_vital_signs": 5,
        },
        source_guideline=src,
        source_section="Initial Recognition",
        source_quote="Systematic screening for septic shock should be performed in emergency and acute care settings",
        conditional_next={
            "state.shock_type == 'warm_shock'": "warm_shock_bundle",
            "state.shock_type == 'cold_shock'": "cold_shock_bundle",
        },
    )

    nodes["warm_shock_bundle"] = _node(
        node_id="warm_shock_bundle",
        node_type="plan",
        name="Warm Shock Resuscitation (Vasodilatory)",
        description="Fluid resuscitation + norepinephrine for warm/vasodilatory shock",
        precondition="state.shock_type == 'warm_shock'",
        mandatory=[
            "give_crystalloid_bolus_20ml_kg",
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
            "start_vasopressor_norepinephrine",
        ],
        allowed=[
            "give_crystalloid_bolus_20ml_kg",
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
            "start_vasopressor_norepinephrine",
            "start_vasopressor_vasopressin",
            "order_lab_lactate",
            "place_central_line",
            "reassess_perfusion",
            "give_hydrocortisone_stress_dose",
            "order_lab_cortisol",
            "order_lab_glucose",
        ],
        forbidden=["give_dopamine_first_line"],
        deadlines={
            "give_crystalloid_bolus_20ml_kg": 15,
            "give_broad_spectrum_antibiotics": 60,
            "order_lab_blood_culture": 60,
        },
        required_prior={"give_broad_spectrum_antibiotics": "order_lab_blood_culture"},
        source_guideline=src,
        source_section="Recommendation 10-14: Fluid Resuscitation & Vasoactive",
        source_quote="We suggest using epinephrine or norepinephrine as first-line vasoactive agents rather than dopamine (weak, very low quality)",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["cold_shock_bundle"] = _node(
        node_id="cold_shock_bundle",
        node_type="plan",
        name="Cold Shock Resuscitation (Low Cardiac Output)",
        description="Fluid resuscitation + epinephrine for cold/low CO shock",
        precondition="state.shock_type == 'cold_shock'",
        mandatory=[
            "give_crystalloid_bolus_20ml_kg",
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
            "start_vasopressor_epinephrine",
        ],
        allowed=[
            "give_crystalloid_bolus_20ml_kg",
            "order_lab_blood_culture",
            "give_broad_spectrum_antibiotics",
            "start_vasopressor_epinephrine",
            "give_milrinone",
            "order_lab_lactate",
            "place_central_line",
            "reassess_perfusion",
            "give_hydrocortisone_stress_dose",
            "order_lab_cortisol",
            "order_lab_glucose",
        ],
        forbidden=["give_dopamine_first_line"],
        deadlines={
            "give_crystalloid_bolus_20ml_kg": 15,
            "give_broad_spectrum_antibiotics": 60,
            "order_lab_blood_culture": 60,
        },
        required_prior={"give_broad_spectrum_antibiotics": "order_lab_blood_culture"},
        source_guideline=src,
        source_section="Recommendation 10-14: Cold Shock",
        source_quote="For cold shock, we suggest epinephrine as first-line vasoactive agent to improve cardiac output",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["monitoring_reassessment"] = _node(
        node_id="monitoring_reassessment",
        node_type="enquiry",
        name="Monitoring & Reassessment",
        description="Reassess perfusion, lactate clearance, fluid responsiveness",
        mandatory=["reassess_perfusion", "remeasure_lactate_if_elevated"],
        allowed=[
            "reassess_perfusion",
            "remeasure_lactate_if_elevated",
            "order_lab_lactate",
            "order_lab_blood_gas",
            "assess_fluid_responsiveness",
            "monitor_urine_output",
            "assess_mental_status",
            "echocardiography",
        ],
        deadlines={"reassess_perfusion": 60, "remeasure_lactate_if_elevated": 180},
        source_guideline=src,
        source_section="Monitoring & Targets",
        source_quote="Target MAP >5th percentile for age, lactate normalization, capillary refill <2s",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="ICU Disposition",
        description="Assess need for continued ICU care, escalation, or PICU transfer",
        mandatory=["assess_icu_transfer_need"],
        allowed=[
            "assess_icu_transfer_need",
            "escalate_to_picu",
            "continue_monitoring",
            "consider_ecmo_referral",
        ],
        source_guideline=src,
        source_section="Disposition",
        source_quote="Children with fluid-refractory or catecholamine-resistant shock should be managed in PICU",
    )

    return {
        "graph_id": "sccm_pediatric_septic_shock_2020",
        "guideline_name": "Surviving Sepsis Campaign International Guidelines for Management of Septic Shock in Children (2020)",
        "version": "2020.1",
        "metadata": {
            "source": "SCCM/ESICM Pediatric Septic Shock Guidelines 2020",
            "doi": doi,
            "journal": "Pediatric Critical Care Medicine",
            "recommendation_system": "GRADE",
            "description": "Evidence-based guideline for recognition and management of septic shock and sepsis-associated organ dysfunction in children",
            "key_evidence": "Initial fluid bolus 10-20 mL/kg over 5-20 min; epinephrine/norepinephrine preferred over dopamine as first-line vasoactive",
        },
        "entry_node": "initial_recognition",
        "nodes": nodes,
    }


# =========================================================================
# 3. Aneurysmal SAH (NCS/AHA 2023)
# =========================================================================


def build_sah_graph() -> dict[str, Any]:
    """NCS/AHA Aneurysmal SAH 2023 guideline graph."""
    src = "AHA/ASA SAH Guidelines 2023"
    doi = "10.1161/STR.0000000000000436"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="SAH Recognition & Severity Assessment",
        description="Confirm SAH diagnosis, assess Hunt-Hess / WFNS grade, identify aneurysm",
        mandatory=[
            "assess_neurological_status",
            "order_imaging_ct_head",
            "assess_hunt_hess_grade",
        ],
        allowed=[
            "assess_neurological_status",
            "order_imaging_ct_head",
            "assess_hunt_hess_grade",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_coagulation",
            "order_lab_type_and_screen",
            "assess_vital_signs",
            "establish_iv_access",
            "order_imaging_ct_angiography",
        ],
        deadlines={
            "assess_neurological_status": 15,
            "order_imaging_ct_head": 30,
        },
        source_guideline=src,
        source_section="Initial Evaluation",
        source_quote="Non-contrast CT has >95% sensitivity for SAH within 6 hours. CT angiography should be performed urgently to identify source",
        conditional_next={
            "state.hunt_hess_grade >= 4": "high_grade_sah_bundle",
            "state.hunt_hess_grade <= 3": "standard_sah_bundle",
        },
    )

    nodes["standard_sah_bundle"] = _node(
        node_id="standard_sah_bundle",
        node_type="plan",
        name="Standard SAH Management (Hunt-Hess I-III)",
        description="Blood pressure control, nimodipine, aneurysm securing, vasospasm prevention",
        precondition="state.hunt_hess_grade <= 3",
        mandatory=[
            "control_blood_pressure_sbp_below_160",
            "give_nimodipine_60mg_q4h",
            "order_imaging_ct_angiography",
            "request_neurosurgery_consultation",
        ],
        allowed=[
            "control_blood_pressure_sbp_below_160",
            "give_nimodipine_60mg_q4h",
            "order_imaging_ct_angiography",
            "request_neurosurgery_consultation",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_coagulation",
            "place_external_ventricular_drain",
            "give_antiepileptic_prophylaxis",
            "maintain_euvolemia",
            "order_transcranial_doppler",
            "give_tranexamic_acid_short_term",
        ],
        forbidden=[
            "give_antiplatelet_before_securing",
            "give_anticoagulant_before_securing",
            "lumbar_puncture_with_mass_effect",
        ],
        deadlines={
            "control_blood_pressure_sbp_below_160": 30,
            "give_nimodipine_60mg_q4h": 60,
            "order_imaging_ct_angiography": 60,
            "request_neurosurgery_consultation": 60,
        },
        required_prior={
            "give_antiepileptic_prophylaxis": "assess_neurological_status",
        },
        source_guideline=src,
        source_section="Recommendation 3.1-3.4: BP Control, Nimodipine, Securing",
        source_quote="Oral nimodipine 60mg every 4 hours for 21 days (Class I, Level A). Aneurysm should be treated as early as feasible to reduce rebleeding risk",
        rec_class="I",
        evidence="A",
        next_nodes=["vasospasm_monitoring"],
    )

    nodes["high_grade_sah_bundle"] = _node(
        node_id="high_grade_sah_bundle",
        node_type="plan",
        name="High-Grade SAH Management (Hunt-Hess IV-V)",
        description="Aggressive management including EVD, ICP monitoring, early securing",
        precondition="state.hunt_hess_grade >= 4",
        mandatory=[
            "secure_airway_intubation",
            "control_blood_pressure_sbp_below_160",
            "give_nimodipine_60mg_q4h",
            "place_external_ventricular_drain",
            "request_neurosurgery_consultation",
        ],
        allowed=[
            "secure_airway_intubation",
            "control_blood_pressure_sbp_below_160",
            "give_nimodipine_60mg_q4h",
            "place_external_ventricular_drain",
            "request_neurosurgery_consultation",
            "order_imaging_ct_angiography",
            "monitor_icp",
            "give_osmotic_therapy_mannitol",
            "give_hypertonic_saline",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_coagulation",
            "maintain_euvolemia",
            "give_tranexamic_acid_short_term",
        ],
        forbidden=[
            "give_antiplatelet_before_securing",
            "give_anticoagulant_before_securing",
            "lumbar_puncture_with_mass_effect",
        ],
        deadlines={
            "secure_airway_intubation": 15,
            "control_blood_pressure_sbp_below_160": 30,
            "place_external_ventricular_drain": 60,
            "give_nimodipine_60mg_q4h": 60,
            "request_neurosurgery_consultation": 30,
        },
        source_guideline=src,
        source_section="Recommendation 4.1-4.3: High-Grade SAH",
        source_quote="EVD placement is recommended for patients with acute hydrocephalus (Class I, Level B). Early aneurysm treatment reduces rebleeding risk",
        rec_class="I",
        evidence="B",
        next_nodes=["vasospasm_monitoring"],
    )

    nodes["vasospasm_monitoring"] = _node(
        node_id="vasospasm_monitoring",
        node_type="enquiry",
        name="Vasospasm Monitoring (Days 3-14)",
        description="Monitor for delayed cerebral ischemia / vasospasm",
        mandatory=["order_transcranial_doppler", "assess_neurological_status"],
        allowed=[
            "order_transcranial_doppler",
            "assess_neurological_status",
            "order_imaging_ct_perfusion",
            "induced_hypertension_for_dci",
            "order_imaging_ct_angiography",
            "give_nimodipine_60mg_q4h",
            "order_lab_cbc",
            "order_lab_bmp",
            "maintain_euvolemia",
        ],
        forbidden=["prophylactic_hypervolemia", "prophylactic_balloon_angioplasty"],
        deadlines={
            "order_transcranial_doppler": 1440,  # daily
        },
        source_guideline=src,
        source_section="Recommendation 5: DCI / Vasospasm",
        source_quote="TCD monitoring to detect vasospasm. Induced hypertension is reasonable for symptomatic vasospasm. Prophylactic hypervolemia is NOT recommended (Class III, Level B)",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition",
        description="Assess readiness for step-down, rehab, or continued ICU care",
        mandatory=["assess_discharge_readiness"],
        allowed=[
            "assess_discharge_readiness",
            "continue_nimodipine_21days",
            "arrange_rehabilitation",
            "schedule_follow_up_imaging",
        ],
        source_guideline=src,
        source_section="Disposition",
        source_quote="Patients should be cared for in high-volume centers with neurosurgical and endovascular capabilities",
    )

    return {
        "graph_id": "ncs_aha_sah_2023",
        "guideline_name": "2023 Guideline for the Management of Patients With Aneurysmal Subarachnoid Hemorrhage (AHA/ASA)",
        "version": "2023.1",
        "metadata": {
            "source": "AHA/ASA SAH Guidelines 2023",
            "doi": doi,
            "journal": "Stroke",
            "recommendation_system": "AHA Class/Level",
            "description": "Comprehensive guideline for aneurysmal SAH management including acute stabilization, aneurysm securing, vasospasm prevention, and rehabilitation",
            "key_evidence": "Nimodipine reduces poor outcome after SAH (OR 0.67). Early aneurysm treatment (<24h) reduces rebleeding. Prophylactic hypervolemia/triple-H has no benefit (Class III).",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 4. Aortic Dissection (AHA/ACC 2022)
# =========================================================================


def build_aortic_dissection_graph() -> dict[str, Any]:
    """AHA/ACC 2022 Aortic Disease guideline graph."""
    src = "AHA/ACC Aortic Disease 2022"
    doi = "10.1161/CIR.0000000000001106"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Aortic Dissection Recognition",
        description="Identify suspected aortic dissection based on pain characteristics, physical exam, risk factors",
        mandatory=["assess_chest_pain_characteristics", "assess_vital_signs", "bilateral_bp_measurement"],
        allowed=[
            "assess_chest_pain_characteristics",
            "assess_vital_signs",
            "bilateral_bp_measurement",
            "assess_peripheral_pulses",
            "auscultate_for_aortic_regurgitation",
            "order_ecg",
            "order_lab_troponin",
            "order_lab_cbc",
            "order_lab_bmp",
            "establish_iv_access",
        ],
        deadlines={
            "assess_chest_pain_characteristics": 10,
            "assess_vital_signs": 10,
            "bilateral_bp_measurement": 10,
        },
        source_guideline=src,
        source_section="Initial Recognition",
        source_quote="Acute aortic dissection should be suspected in patients with sudden-onset severe chest/back pain with tearing quality",
        next_nodes=["diagnostic_workup"],
    )

    nodes["diagnostic_workup"] = _node(
        node_id="diagnostic_workup",
        node_type="plan",
        name="Diagnostic Imaging & Type Classification",
        description="Emergent CTA aorta to confirm dissection and classify type (Stanford A vs B)",
        mandatory=[
            "order_imaging_cta_aorta",
            "give_iv_pain_control_morphine",
            "initiate_bp_control",
        ],
        allowed=[
            "order_imaging_cta_aorta",
            "give_iv_pain_control_morphine",
            "initiate_bp_control",
            "give_iv_beta_blocker_labetalol",
            "give_iv_beta_blocker_esmolol",
            "order_lab_type_and_crossmatch",
            "order_lab_coagulation",
            "assess_vital_signs",
        ],
        forbidden=["give_thrombolytics"],
        deadlines={
            "order_imaging_cta_aorta": 30,
            "give_iv_pain_control_morphine": 15,
            "initiate_bp_control": 20,
        },
        source_guideline=src,
        source_section="Recommendation 3.1-3.2: Diagnostic Imaging",
        source_quote="CTA is recommended as first-line imaging modality for suspected acute aortic dissection (Class I, Level B). Thrombolytics are contraindicated (Class III)",
        rec_class="I",
        evidence="B",
        conditional_next={
            "state.dissection_type == 'type_a'": "type_a_management",
            "state.dissection_type == 'type_b'": "type_b_management",
        },
    )

    nodes["type_a_management"] = _node(
        node_id="type_a_management",
        node_type="plan",
        name="Type A Dissection - Emergent Surgery",
        description="Stanford Type A (ascending aorta) requires emergent surgical repair",
        precondition="state.dissection_type == 'type_a'",
        mandatory=[
            "control_bp_target_sbp_100_120",
            "control_hr_target_below_60",
            "request_cardiac_surgery_consultation",
            "order_lab_type_and_crossmatch",
        ],
        allowed=[
            "control_bp_target_sbp_100_120",
            "control_hr_target_below_60",
            "request_cardiac_surgery_consultation",
            "order_lab_type_and_crossmatch",
            "give_iv_beta_blocker_labetalol",
            "give_iv_beta_blocker_esmolol",
            "give_iv_vasodilator_nicardipine",
            "give_iv_pain_control_morphine",
            "order_transthoracic_echo",
            "assess_aortic_regurgitation",
            "assess_pericardial_effusion",
            "prepare_or",
        ],
        forbidden=["delay_surgery_for_additional_imaging", "give_thrombolytics"],
        deadlines={
            "control_bp_target_sbp_100_120": 30,
            "request_cardiac_surgery_consultation": 60,
        },
        source_guideline=src,
        source_section="Recommendation 4.1: Type A Management",
        source_quote="Emergent surgical repair is recommended for acute Type A aortic dissection (Class I, Level B). Target SBP <120 mmHg and HR <60 bpm before surgery",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring"],
    )

    nodes["type_b_management"] = _node(
        node_id="type_b_management",
        node_type="plan",
        name="Type B Dissection - Medical Management",
        description="Stanford Type B (descending aorta) typically managed medically unless complicated",
        precondition="state.dissection_type == 'type_b'",
        mandatory=[
            "control_bp_target_sbp_100_120",
            "control_hr_target_below_60",
            "icu_admission",
        ],
        allowed=[
            "control_bp_target_sbp_100_120",
            "control_hr_target_below_60",
            "icu_admission",
            "give_iv_beta_blocker_labetalol",
            "give_iv_beta_blocker_esmolol",
            "give_iv_vasodilator_nicardipine",
            "give_iv_pain_control_morphine",
            "request_vascular_surgery_consultation",
            "order_imaging_cta_follow_up",
            "assess_end_organ_perfusion",
            "monitor_renal_function",
            "monitor_bowel_ischemia_signs",
        ],
        deadlines={
            "control_bp_target_sbp_100_120": 30,
            "icu_admission": 60,
        },
        source_guideline=src,
        source_section="Recommendation 4.2: Type B Management",
        source_quote="Medical management with BP/HR control is recommended for uncomplicated Type B dissection (Class I, Level B). Surgical/endovascular intervention for complications",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring"],
    )

    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Monitoring & Complications",
        description="Serial BP/HR monitoring, assess for complications (malperfusion, rupture)",
        mandatory=["monitor_bp_hr_q15min", "assess_end_organ_perfusion"],
        allowed=[
            "monitor_bp_hr_q15min",
            "assess_end_organ_perfusion",
            "assess_neurological_status",
            "monitor_urine_output",
            "assess_limb_perfusion",
            "order_lab_lactate",
            "order_lab_creatinine",
            "order_imaging_cta_follow_up",
        ],
        deadlines={"monitor_bp_hr_q15min": 15, "assess_end_organ_perfusion": 60},
        source_guideline=src,
        source_section="Monitoring",
        source_quote="Continuous BP/HR monitoring required. Serial assessment for malperfusion syndrome (renal, mesenteric, limb)",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition",
        description="Post-operative care (Type A) or continued medical management (Type B)",
        mandatory=["assess_discharge_readiness"],
        allowed=[
            "assess_discharge_readiness",
            "transition_to_oral_bp_meds",
            "schedule_follow_up_imaging",
            "continue_icu_care",
        ],
        source_guideline=src,
        source_section="Long-term Management",
        source_quote="Lifelong BP control and serial imaging surveillance required",
    )

    return {
        "graph_id": "aha_acc_aortic_dissection_2022",
        "guideline_name": "2022 ACC/AHA Guideline for the Diagnosis and Management of Aortic Disease",
        "version": "2022.1",
        "metadata": {
            "source": "AHA/ACC Aortic Disease Guideline 2022",
            "doi": doi,
            "journal": "Circulation",
            "recommendation_system": "AHA Class/Level",
            "description": "Evidence-based guideline for acute aortic dissection including rapid diagnosis, type classification, and type-specific management",
            "key_evidence": "Type A dissection has 1-2% mortality per hour without surgery. Beta-blocker before vasodilator prevents reflex tachycardia. Thrombolytics are contraindicated (Class III).",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 5. Intracerebral Hemorrhage (AHA/ASA 2022)
# =========================================================================


def build_ich_graph() -> dict[str, Any]:
    """AHA/ASA 2022 Spontaneous ICH guideline graph."""
    src = "AHA/ASA ICH Guidelines 2022"
    doi = "10.1161/STR.0000000000000407"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="ICH Recognition & Severity Assessment",
        description="Confirm ICH via CT, assess GCS, NIHSS, and identify underlying cause",
        mandatory=["assess_neurological_status", "order_imaging_ct_head", "assess_gcs"],
        allowed=[
            "assess_neurological_status",
            "order_imaging_ct_head",
            "assess_gcs",
            "assess_nihss",
            "assess_vital_signs",
            "order_lab_cbc",
            "order_lab_coagulation",
            "order_lab_bmp",
            "order_lab_glucose",
            "establish_iv_access",
        ],
        deadlines={
            "assess_neurological_status": 10,
            "order_imaging_ct_head": 25,
            "assess_gcs": 10,
        },
        source_guideline=src,
        source_section="Initial Evaluation",
        source_quote="Non-contrast CT is the gold standard for acute ICH diagnosis. Immediate neurological assessment including GCS and NIHSS",
        next_nodes=["bp_management"],
    )

    nodes["bp_management"] = _node(
        node_id="bp_management",
        node_type="plan",
        name="Blood Pressure Management",
        description="Rapid BP lowering to target SBP <140 if presenting SBP 150-220 mmHg",
        mandatory=[
            "initiate_iv_antihypertensive",
            "target_sbp_below_140",
        ],
        allowed=[
            "initiate_iv_antihypertensive",
            "target_sbp_below_140",
            "give_iv_nicardipine",
            "give_iv_labetalol",
            "give_iv_esmolol",
            "monitor_bp_q5min",
            "assess_neurological_status",
        ],
        deadlines={
            "initiate_iv_antihypertensive": 60,
            "target_sbp_below_140": 60,
        },
        source_guideline=src,
        source_section="Recommendation 2: Blood Pressure Management",
        source_quote="For patients with ICH presenting with SBP 150-220 mmHg, acute lowering to target SBP 140 mmHg is safe and reasonable (Class IIa, Level A)",
        rec_class="IIa",
        evidence="A",
        next_nodes=["coagulopathy_reversal"],
    )

    nodes["coagulopathy_reversal"] = _node(
        node_id="coagulopathy_reversal",
        node_type="plan",
        name="Coagulopathy Reversal",
        description="Reverse anticoagulation if present (warfarin, DOAC, heparin)",
        mandatory=["assess_anticoagulation_status"],
        allowed=[
            "assess_anticoagulation_status",
            "order_lab_inr",
            "order_lab_ptt",
            "give_pcc_4factor",
            "give_vitamin_k",
            "give_idarucizumab_if_dabigatran",
            "give_andexanet_if_xa_inhibitor",
            "give_protamine_if_heparin",
            "order_lab_coagulation_repeat",
        ],
        deadlines={
            "assess_anticoagulation_status": 30,
        },
        required_prior={
            "give_pcc_4factor": "order_lab_inr",
        },
        conditional_rules=[
            {
                "rule_id": "ICH-WARFARIN-REVERSAL",
                "condition": "state.on_warfarin == True",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["give_pcc_4factor", "give_vitamin_k"],
                    "deadline_minutes": 60,
                },
                "severity": "CRITICAL",
                "description": "Warfarin-associated ICH requires immediate reversal with 4-factor PCC and vitamin K",
            },
            {
                "rule_id": "ICH-DABIGATRAN-REVERSAL",
                "condition": "state.on_dabigatran == True",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["give_idarucizumab_if_dabigatran"],
                    "deadline_minutes": 60,
                },
                "severity": "CRITICAL",
                "description": "Dabigatran-associated ICH requires idarucizumab reversal",
            },
            {
                "rule_id": "ICH-XA-REVERSAL",
                "condition": "state.on_xa_inhibitor == True",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["give_andexanet_if_xa_inhibitor"],
                    "deadline_minutes": 60,
                },
                "severity": "CRITICAL",
                "description": "Factor Xa inhibitor-associated ICH requires andexanet alfa reversal",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 3: Coagulopathy Reversal",
        source_quote="Patients with ICH on warfarin should receive rapid INR reversal with 4-factor PCC and vitamin K (Class I, Level B)",
        rec_class="I",
        evidence="B",
        next_nodes=["neurosurgical_evaluation"],
    )

    nodes["neurosurgical_evaluation"] = _node(
        node_id="neurosurgical_evaluation",
        node_type="decision",
        name="Neurosurgical Consultation",
        description="Assess need for surgical evacuation, EVD, or ICP monitoring",
        mandatory=["request_neurosurgery_consultation"],
        allowed=[
            "request_neurosurgery_consultation",
            "assess_ich_volume",
            "assess_gcs",
            "assess_hydrocephalus",
            "place_external_ventricular_drain",
            "monitor_icp",
            "order_imaging_ct_head_repeat",
        ],
        forbidden=[
            "routine_surgical_evacuation_deep_ich",
        ],
        deadlines={
            "request_neurosurgery_consultation": 120,
        },
        conditional_rules=[
            {
                "rule_id": "ICH-CEREBELLAR-EVD",
                "condition": "state.ich_location == 'cerebellar' and state.ich_volume_ml > 30",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["place_external_ventricular_drain"],
                    "deadline_minutes": 120,
                },
                "severity": "CRITICAL",
                "description": "Large cerebellar hemorrhage >3cm requires EVD to prevent hydrocephalus and brainstem compression",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 4-5: Surgical Management",
        source_quote="Surgical evacuation is reasonable for cerebellar hemorrhage >3cm with neurological deterioration. Routine evacuation of deep ICH is not recommended (Class III)",
        next_nodes=["monitoring"],
    )

    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Monitoring & Complications",
        description="Serial neurological exams, monitor for hematoma expansion, ICP control",
        mandatory=["assess_neurological_status_q1h", "repeat_ct_head_24h"],
        allowed=[
            "assess_neurological_status_q1h",
            "repeat_ct_head_24h",
            "monitor_bp_continuous",
            "monitor_icp",
            "give_osmotic_therapy_if_elevated_icp",
            "assess_seizure_activity",
            "order_lab_cbc",
            "order_lab_bmp",
        ],
        forbidden=[
            "prophylactic_antiepileptics_routine",
        ],
        deadlines={
            "assess_neurological_status_q1h": 60,
            "repeat_ct_head_24h": 1440,
        },
        source_guideline=src,
        source_section="Recommendation 6-7: Monitoring",
        source_quote="Serial neurological assessments recommended. Repeat CT at 24h to assess stability. Prophylactic antiepileptics NOT recommended for routine use (Class III)",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Rehabilitation",
        description="Assess readiness for rehabilitation, step-down, or continued ICU care",
        mandatory=["assess_discharge_readiness"],
        allowed=[
            "assess_discharge_readiness",
            "arrange_rehabilitation",
            "schedule_follow_up_imaging",
            "continue_icu_care",
        ],
        source_guideline=src,
        source_section="Disposition",
        source_quote="Early rehabilitation within 24-48 hours is reasonable for stable patients (Class IIa, Level B)",
    )

    return {
        "graph_id": "aha_asa_ich_2022",
        "guideline_name": "2022 AHA/ASA Guideline for the Management of Patients With Spontaneous Intracerebral Hemorrhage",
        "version": "2022.1",
        "metadata": {
            "source": "AHA/ASA ICH Guidelines 2022",
            "doi": doi,
            "journal": "Stroke",
            "recommendation_system": "AHA Class/Level",
            "description": "Evidence-based guideline for spontaneous ICH including BP control, coagulopathy reversal, and neurosurgical decision-making",
            "key_evidence": "INTERACT2 trial: SBP <140 reduces hematoma expansion. 4-factor PCC reverses warfarin faster than FFP. Routine surgical evacuation of deep ICH not beneficial (STICH trials).",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 6. Ruptured AAA (ESVS 2024)
# =========================================================================


def build_ruptured_aaa_graph() -> dict[str, Any]:
    """ESVS 2024 Abdominal Aortic Aneurysm guideline graph."""
    src = "ESVS AAA Guidelines 2024"
    doi = "10.1093/ejves/zvad368"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Ruptured AAA Recognition",
        description="Identify suspected ruptured AAA based on triad: abdominal/back pain, hypotension, pulsatile mass",
        mandatory=["assess_vital_signs", "assess_abdominal_exam", "assess_shock_index"],
        allowed=[
            "assess_vital_signs",
            "assess_abdominal_exam",
            "assess_shock_index",
            "order_lab_cbc",
            "order_lab_type_and_crossmatch",
            "order_lab_lactate",
            "order_lab_coagulation",
            "establish_large_bore_iv_access",
            "order_imaging_bedside_ultrasound",
        ],
        forbidden=["delay_or_for_imaging_if_unstable"],
        deadlines={
            "assess_vital_signs": 5,
            "assess_abdominal_exam": 10,
            "order_lab_type_and_crossmatch": 15,
        },
        source_guideline=src,
        source_section="Initial Recognition",
        source_quote="Ruptured AAA is a vascular emergency with >80% mortality without surgery. Bedside ultrasound can confirm AAA if CT delayed",
        conditional_next={
            "state.hemodynamically_stable == True": "stable_workup",
            "state.hemodynamically_stable == False": "hemodynamic_resuscitation",
        },
    )

    nodes["stable_workup"] = _node(
        node_id="stable_workup",
        node_type="plan",
        name="Stable Patient - CT Angiography",
        description="Hemodynamically stable patients can undergo CTA for operative planning",
        precondition="state.hemodynamically_stable == True",
        mandatory=[
            "order_imaging_cta_abdomen_pelvis",
            "request_vascular_surgery_consultation",
            "order_lab_type_and_crossmatch",
        ],
        allowed=[
            "order_imaging_cta_abdomen_pelvis",
            "request_vascular_surgery_consultation",
            "order_lab_type_and_crossmatch",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_coagulation",
            "establish_iv_access",
            "permissive_hypotension_target_sbp_80_100",
        ],
        deadlines={
            "order_imaging_cta_abdomen_pelvis": 30,
            "request_vascular_surgery_consultation": 30,
        },
        source_guideline=src,
        source_section="Recommendation 2: Imaging",
        source_quote="CTA is recommended in stable patients to plan operative approach (open vs EVAR)",
        next_nodes=["surgical_decision"],
    )

    nodes["hemodynamic_resuscitation"] = _node(
        node_id="hemodynamic_resuscitation",
        node_type="plan",
        name="Hemodynamic Resuscitation - Permissive Hypotension",
        description="Unstable patients: permissive hypotension, avoid aggressive fluids pre-clamping",
        precondition="state.hemodynamically_stable == False",
        mandatory=[
            "permissive_hypotension_target_sbp_80_100",
            "request_vascular_surgery_consultation",
            "order_lab_type_and_crossmatch",
            "activate_massive_transfusion_protocol",
        ],
        allowed=[
            "permissive_hypotension_target_sbp_80_100",
            "request_vascular_surgery_consultation",
            "order_lab_type_and_crossmatch",
            "activate_massive_transfusion_protocol",
            "give_prbc_if_hgb_below_7",
            "give_txa_tranexamic_acid",
            "order_lab_lactate",
            "order_lab_blood_gas",
            "establish_iv_access",
        ],
        forbidden=[
            "aggressive_crystalloid_pre_clamping",
            "delay_or_for_imaging",
        ],
        deadlines={
            "permissive_hypotension_target_sbp_80_100": 10,
            "request_vascular_surgery_consultation": 30,
            "activate_massive_transfusion_protocol": 15,
        },
        source_guideline=src,
        source_section="Recommendation 3: Hemodynamic Management",
        source_quote="Permissive hypotension (SBP 80-100) recommended to reduce pre-operative bleeding. Aggressive fluid resuscitation pre-clamping increases mortality",
        rec_class="I",
        evidence="B",
        next_nodes=["surgical_decision"],
    )

    nodes["surgical_decision"] = _node(
        node_id="surgical_decision",
        node_type="decision",
        name="Operative Management",
        description="Emergent open repair or EVAR based on anatomy and center capabilities",
        mandatory=["prepare_or_emergent"],
        allowed=[
            "prepare_or_emergent",
            "assess_evar_feasibility",
            "plan_open_repair",
            "plan_evar_repair",
            "order_lab_cbc",
            "order_lab_coagulation",
            "continue_permissive_hypotension",
        ],
        deadlines={
            "prepare_or_emergent": 60,
        },
        source_guideline=src,
        source_section="Recommendation 4: Operative Management",
        source_quote="EVAR has lower 30-day mortality vs open repair in suitable anatomy (OR 0.64). Time to OR <90 min improves survival",
        next_nodes=["postop_monitoring"],
    )

    nodes["postop_monitoring"] = _node(
        node_id="postop_monitoring",
        node_type="enquiry",
        name="Post-Operative Monitoring",
        description="ICU monitoring for bleeding, coagulopathy, renal failure, abdominal compartment syndrome",
        mandatory=["monitor_vital_signs_continuous", "monitor_urine_output", "assess_abdominal_compartment_syndrome"],
        allowed=[
            "monitor_vital_signs_continuous",
            "monitor_urine_output",
            "assess_abdominal_compartment_syndrome",
            "order_lab_cbc",
            "order_lab_lactate",
            "order_lab_creatinine",
            "order_lab_coagulation",
            "transfuse_prbc_if_needed",
            "give_ffp_if_coagulopathy",
        ],
        deadlines={
            "monitor_vital_signs_continuous": 15,
            "assess_abdominal_compartment_syndrome": 120,
        },
        source_guideline=src,
        source_section="Post-Operative Care",
        source_quote="Abdominal compartment syndrome occurs in 10-20% of ruptured AAA repairs. Bladder pressure >20 mmHg requires decompression",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition",
        description="Continued ICU care, assess for complications, rehabilitation",
        mandatory=["assess_discharge_readiness"],
        allowed=[
            "assess_discharge_readiness",
            "continue_icu_care",
            "arrange_rehabilitation",
            "schedule_follow_up_imaging",
        ],
        source_guideline=src,
        source_section="Long-term Management",
        source_quote="Surveillance imaging at 1 month, 1 year, then annually after EVAR",
    )

    return {
        "graph_id": "esvs_aaa_2024",
        "guideline_name": "ESVS 2024 Clinical Practice Guidelines on the Management of Abdominal Aorto-iliac Artery Aneurysms",
        "version": "2024.1",
        "metadata": {
            "source": "ESVS AAA Guidelines 2024",
            "doi": doi,
            "journal": "European Journal of Vascular and Endovascular Surgery",
            "recommendation_system": "GRADE",
            "description": "Evidence-based guideline for ruptured AAA including permissive hypotension, emergent repair strategies, and post-operative management",
            "key_evidence": "Permissive hypotension (SBP 80-100) reduces mortality vs aggressive resuscitation. EVAR has 30-day mortality advantage (24% vs 37%). Time to OR <90 min critical.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 7. Neonatal Resuscitation (AHA/AAP 2020)
# =========================================================================


def build_neonatal_resuscitation_graph() -> dict[str, Any]:
    """AHA/AAP 2020 NRP guideline graph."""
    src = "AHA/AAP NRP 2020"
    doi = "10.1161/CIR.0000000000000901"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Birth Assessment - APGAR Evaluation",
        description="Rapid assessment of term gestation, good tone, breathing/crying",
        mandatory=["assess_term_gestation", "assess_muscle_tone", "assess_breathing"],
        allowed=[
            "assess_term_gestation",
            "assess_muscle_tone",
            "assess_breathing",
            "assess_heart_rate",
            "assess_color",
            "place_pulse_oximetry",
        ],
        deadlines={
            "assess_term_gestation": 10,
            "assess_breathing": 10,
        },
        source_guideline=src,
        source_section="Initial Assessment",
        source_quote="Assessment should occur within first 10 seconds: term? good tone? breathing or crying?",
        conditional_next={
            "state.vigorous == True": "routine_care",
            "state.vigorous == False": "initial_steps",
        },
    )

    nodes["routine_care"] = _node(
        node_id="routine_care",
        node_type="plan",
        name="Routine Care for Vigorous Newborn",
        description="Delayed cord clamping, skin-to-skin, drying/warming",
        precondition="state.vigorous == True",
        mandatory=[
            "delayed_cord_clamping_30_60sec",
            "place_skin_to_skin",
            "dry_and_warm",
        ],
        allowed=[
            "delayed_cord_clamping_30_60sec",
            "place_skin_to_skin",
            "dry_and_warm",
            "assess_heart_rate",
            "assess_breathing",
            "suction_if_needed",
        ],
        forbidden=["routine_suctioning_clear_fluid"],
        deadlines={
            "delayed_cord_clamping_30_60sec": 60,
        },
        source_guideline=src,
        source_section="Recommendation 1: Delayed Cord Clamping",
        source_quote="Delayed cord clamping for at least 30 seconds is recommended for vigorous term and preterm newborns (Class I, Level A). Routine suctioning NOT recommended",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )

    nodes["initial_steps"] = _node(
        node_id="initial_steps",
        node_type="plan",
        name="Initial Steps - Warm, Dry, Stimulate",
        description="Immediate cord clamping if non-vigorous, position airway, dry, stimulate",
        precondition="state.vigorous == False",
        mandatory=[
            "immediate_cord_clamping",
            "place_on_radiant_warmer",
            "position_airway",
            "dry_and_stimulate",
            "place_pulse_oximetry",
        ],
        allowed=[
            "immediate_cord_clamping",
            "place_on_radiant_warmer",
            "position_airway",
            "dry_and_stimulate",
            "place_pulse_oximetry",
            "suction_if_copious_secretions",
            "assess_heart_rate",
            "assess_breathing",
        ],
        forbidden=["routine_suctioning_clear_fluid", "oxygen_100_percent_initial_term"],
        deadlines={
            "immediate_cord_clamping": 10,
            "dry_and_stimulate": 30,
            "place_pulse_oximetry": 60,
        },
        source_guideline=src,
        source_section="Recommendation 2: Initial Steps",
        source_quote="Initial steps (warm, dry, stimulate) should be completed within 30 seconds ('golden minute'). 100% O2 NOT recommended as initial gas for term infants",
        next_nodes=["positive_pressure_ventilation"],
    )

    nodes["positive_pressure_ventilation"] = _node(
        node_id="positive_pressure_ventilation",
        node_type="plan",
        name="Positive Pressure Ventilation",
        description="PPV if HR <100 or apnea despite stimulation",
        mandatory=[
            "initiate_ppv_21_percent_o2_term",
            "monitor_heart_rate_response",
        ],
        allowed=[
            "initiate_ppv_21_percent_o2_term",
            "monitor_heart_rate_response",
            "adjust_fio2_based_on_spo2",
            "assess_chest_rise",
            "reposition_airway_if_poor_rise",
            "increase_pip_if_needed",
            "consider_intubation",
            "place_orogastric_tube",
        ],
        deadlines={
            "initiate_ppv_21_percent_o2_term": 60,
        },
        source_guideline=src,
        source_section="Recommendation 3: PPV",
        source_quote="PPV should be initiated if HR <100 bpm or apnea/gasping after initial steps. Start with 21% O2 for term, 21-30% for preterm",
        rec_class="I",
        evidence="B",
        conditional_next={
            "state.heart_rate < 60": "advanced_interventions",
            "state.heart_rate >= 100": "monitoring",
        },
    )

    nodes["advanced_interventions"] = _node(
        node_id="advanced_interventions",
        node_type="plan",
        name="Advanced Resuscitation - Chest Compressions & Epinephrine",
        description="If HR <60 despite adequate PPV for 30 seconds",
        precondition="state.heart_rate < 60",
        mandatory=[
            "initiate_chest_compressions_3_to_1",
            "ensure_effective_ppv",
            "increase_fio2_to_100_percent",
        ],
        allowed=[
            "initiate_chest_compressions_3_to_1",
            "ensure_effective_ppv",
            "increase_fio2_to_100_percent",
            "intubate_if_not_done",
            "place_umbilical_venous_catheter",
            "give_epinephrine_0.01_0.03_mg_kg_iv",
            "give_normal_saline_bolus_10ml_kg",
            "order_lab_blood_gas",
            "order_lab_glucose",
        ],
        deadlines={
            "initiate_chest_compressions_3_to_1": 90,
            "increase_fio2_to_100_percent": 90,
        },
        required_prior={
            "give_epinephrine_0.01_0.03_mg_kg_iv": "place_umbilical_venous_catheter",
        },
        source_guideline=src,
        source_section="Recommendation 4-5: Chest Compressions & Medications",
        source_quote="Chest compressions if HR <60 despite adequate PPV for 30 sec. Epinephrine 0.01-0.03 mg/kg IV if HR <60 after 60 sec of CC + PPV",
        rec_class="I",
        evidence="C",
        next_nodes=["post_resuscitation"],
    )

    nodes["post_resuscitation"] = _node(
        node_id="post_resuscitation",
        node_type="enquiry",
        name="Post-Resuscitation Care",
        description="Monitor for hypoglycemia, respiratory distress, HIE, therapeutic hypothermia consideration",
        mandatory=["monitor_heart_rate_spo2", "assess_glucose", "assess_hie_criteria"],
        allowed=[
            "monitor_heart_rate_spo2",
            "assess_glucose",
            "assess_hie_criteria",
            "order_lab_blood_gas",
            "order_lab_lactate",
            "consider_therapeutic_hypothermia",
            "nicu_admission",
        ],
        deadlines={
            "assess_glucose": 60,
            "assess_hie_criteria": 120,
        },
        source_guideline=src,
        source_section="Post-Resuscitation Care",
        source_quote="Monitor glucose, consider therapeutic hypothermia if HIE criteria met (moderate-severe encephalopathy within 6 hours)",
        next_nodes=["monitoring"],
    )

    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Ongoing Monitoring",
        description="Continue monitoring vitals, respiratory status, glucose, temperature",
        mandatory=["monitor_vital_signs", "monitor_respiratory_status"],
        allowed=[
            "monitor_vital_signs",
            "monitor_respiratory_status",
            "assess_glucose",
            "maintain_normothermia",
        ],
        source_guideline=src,
        source_section="Monitoring",
        source_quote="Continuous monitoring of HR, SpO2, respiratory effort, temperature",
    )

    return {
        "graph_id": "nrp_neonatal_resuscitation_2020",
        "guideline_name": "2020 AHA/AAP Guidelines for Neonatal Resuscitation (NRP)",
        "version": "2020.1",
        "metadata": {
            "source": "AHA/AAP Neonatal Resuscitation Program 2020",
            "doi": doi,
            "journal": "Circulation",
            "recommendation_system": "AHA Class/Level",
            "description": "Evidence-based guideline for neonatal resuscitation including delayed cord clamping, PPV, chest compressions, and epinephrine",
            "key_evidence": "Delayed cord clamping improves hemoglobin (MD +2.17 g/dL). Room air (21% O2) equivalent to 100% for term. Compressions if HR <60 after 30s of PPV.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 8. Pediatric Traumatic Arrest (PALS 2020)
# =========================================================================


def build_pediatric_traumatic_arrest_graph() -> dict[str, Any]:
    """AHA PALS 2020 Pediatric Traumatic Arrest guideline graph."""
    src = "AHA PALS Pediatric Trauma 2020"
    doi = "10.1161/CIR.0000000000000901"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Pediatric Traumatic Arrest Recognition",
        description="Identify reversible causes: hypovolemia, tension pneumothorax, cardiac tamponade",
        mandatory=["assess_airway_breathing", "assess_circulation", "identify_reversible_causes"],
        allowed=[
            "assess_airway_breathing",
            "assess_circulation",
            "identify_reversible_causes",
            "assess_external_hemorrhage",
            "assess_breath_sounds_bilateral",
            "assess_jugular_venous_distension",
            "establish_io_access",
            "establish_iv_access",
        ],
        deadlines={
            "assess_airway_breathing": 5,
            "assess_circulation": 5,
            "identify_reversible_causes": 10,
        },
        source_guideline=src,
        source_section="Initial Assessment",
        source_quote="Traumatic arrest survival depends on rapid identification and treatment of reversible causes: airway obstruction, tension pneumo, tamponade, hemorrhage",
        next_nodes=["hemorrhage_control"],
    )

    nodes["hemorrhage_control"] = _node(
        node_id="hemorrhage_control",
        node_type="plan",
        name="Hemorrhage Control & Massive Transfusion",
        description="Direct pressure, tourniquets, pelvic binder, massive transfusion protocol",
        mandatory=[
            "apply_direct_pressure_external_bleeding",
            "apply_pelvic_binder_if_pelvic_fracture",
            "activate_massive_transfusion_protocol",
        ],
        allowed=[
            "apply_direct_pressure_external_bleeding",
            "apply_pelvic_binder_if_pelvic_fracture",
            "activate_massive_transfusion_protocol",
            "apply_tourniquet_if_extremity_hemorrhage",
            "order_lab_type_and_crossmatch",
            "give_prbc_o_negative_emergency",
            "give_txa_tranexamic_acid_15mg_kg",
            "order_bedside_fast_exam",
            "establish_io_access",
        ],
        forbidden=["excessive_crystalloid_beyond_20ml_kg"],
        deadlines={
            "apply_direct_pressure_external_bleeding": 5,
            "activate_massive_transfusion_protocol": 15,
            "give_txa_tranexamic_acid_15mg_kg": 20,
        },
        source_guideline=src,
        source_section="Recommendation 1-2: Hemorrhage Control",
        source_quote="Limit crystalloid to 20 mL/kg. Massive transfusion protocol (1:1:1 PRBC:FFP:platelets) for ongoing hemorrhage. TXA within 3h reduces mortality",
        rec_class="I",
        evidence="B",
        next_nodes=["airway_breathing"],
    )

    nodes["airway_breathing"] = _node(
        node_id="airway_breathing",
        node_type="plan",
        name="Airway Management & Needle Decompression",
        description="Secure airway, bilateral needle decompression if tension pneumo suspected",
        mandatory=[
            "secure_airway_intubation",
            "bilateral_needle_decompression_if_suspected_pneumo",
        ],
        allowed=[
            "secure_airway_intubation",
            "bilateral_needle_decompression_if_suspected_pneumo",
            "ventilate_100_percent_o2",
            "order_imaging_chest_xray",
            "place_chest_tube_if_pneumothorax",
            "assess_breath_sounds_bilateral",
        ],
        deadlines={
            "secure_airway_intubation": 10,
            "bilateral_needle_decompression_if_suspected_pneumo": 5,
        },
        source_guideline=src,
        source_section="Recommendation 3: Airway & Breathing",
        source_quote="Bilateral needle decompression recommended if tension pneumothorax suspected in traumatic arrest (Class IIa, Level C). Do not delay for imaging",
        rec_class="IIa",
        evidence="C",
        next_nodes=["circulation"],
    )

    nodes["circulation"] = _node(
        node_id="circulation",
        node_type="plan",
        name="Circulation & Cardiac Tamponade",
        description="Assess for tamponade via FAST, resuscitative thoracotomy consideration",
        mandatory=[
            "order_bedside_fast_exam",
            "give_prbc_o_negative_emergency",
        ],
        allowed=[
            "order_bedside_fast_exam",
            "give_prbc_o_negative_emergency",
            "give_ffp",
            "give_platelets",
            "give_calcium_chloride",
            "correct_hypothermia",
            "correct_acidosis",
            "assess_for_pericardial_effusion",
            "consider_resuscitative_thoracotomy",
        ],
        forbidden=["routine_atropine_traumatic_arrest"],
        deadlines={
            "order_bedside_fast_exam": 10,
            "give_prbc_o_negative_emergency": 15,
        },
        source_guideline=src,
        source_section="Recommendation 4-5: Circulation",
        source_quote="FAST exam to identify cardiac tamponade or intra-abdominal bleeding. Resuscitative thoracotomy reasonable in select cases (penetrating trauma, short transport time)",
        next_nodes=["surgical_decision"],
    )

    nodes["surgical_decision"] = _node(
        node_id="surgical_decision",
        node_type="decision",
        name="Surgical Intervention Decision",
        description="Assess need for emergent OR, resuscitative thoracotomy, or continued resuscitation",
        mandatory=["assess_need_for_emergent_or"],
        allowed=[
            "assess_need_for_emergent_or",
            "proceed_to_or_emergent",
            "perform_resuscitative_thoracotomy",
            "continue_resuscitation",
            "consult_trauma_surgery",
        ],
        source_guideline=src,
        source_section="Surgical Decision",
        source_quote="Resuscitative thoracotomy survival <5% in blunt trauma, up to 10-15% in penetrating with short arrest time",
        next_nodes=["monitoring"],
    )

    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Post-Resuscitation Monitoring",
        description="Monitor for secondary brain injury, coagulopathy, hypothermia, ongoing bleeding",
        mandatory=["monitor_vital_signs_continuous", "assess_neurological_status"],
        allowed=[
            "monitor_vital_signs_continuous",
            "assess_neurological_status",
            "order_lab_blood_gas",
            "order_lab_lactate",
            "order_lab_coagulation",
            "order_imaging_ct_head",
            "order_imaging_ct_chest_abdomen_pelvis",
            "rewarm_if_hypothermic",
        ],
        deadlines={
            "monitor_vital_signs_continuous": 15,
        },
        source_guideline=src,
        source_section="Post-Resuscitation Care",
        source_quote="Prevent secondary brain injury (hypoxia, hypotension, hypoglycemia). Maintain normothermia. Correct coagulopathy",
    )

    return {
        "graph_id": "pals_pediatric_traumatic_arrest_2020",
        "guideline_name": "2020 AHA PALS Guidelines - Pediatric Traumatic Arrest",
        "version": "2020.1",
        "metadata": {
            "source": "AHA PALS 2020 Guidelines",
            "doi": doi,
            "journal": "Circulation",
            "recommendation_system": "AHA Class/Level",
            "description": "Evidence-based guideline for pediatric traumatic arrest focusing on reversible causes: hemorrhage, tension pneumo, tamponade",
            "key_evidence": "Limit crystalloid to 20 mL/kg. TXA within 3h reduces mortality (CRASH-2). Bilateral needle decompression for suspected tension pneumo. Atropine NOT recommended.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 9. Cardiogenic Shock (AHA/ACC 2017)
# =========================================================================


def build_cardiogenic_shock_graph() -> dict[str, Any]:
    """AHA/ACC 2017 Cardiogenic Shock guideline graph."""
    src = "AHA/ACC Cardiogenic Shock 2017"
    doi = "10.1161/CIR.0000000000000525"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Cardiogenic Shock Recognition",
        description="Identify cardiogenic shock: hypotension (SBP<90), signs of end-organ hypoperfusion, assess etiology",
        mandatory=["assess_vital_signs", "assess_perfusion_status", "order_ecg"],
        allowed=[
            "assess_vital_signs",
            "assess_perfusion_status",
            "order_ecg",
            "order_lab_lactate",
            "order_lab_troponin",
            "order_lab_bnp",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_blood_gas",
            "establish_iv_access",
            "place_arterial_line",
        ],
        deadlines={
            "assess_vital_signs": 5,
            "assess_perfusion_status": 10,
            "order_ecg": 10,
        },
        source_guideline=src,
        source_section="Initial Evaluation",
        source_quote="Cardiogenic shock is defined as sustained hypotension (SBP <90 mmHg) with evidence of end-organ hypoperfusion despite adequate filling pressures",
        conditional_next={
            "state.etiology == 'acs'": "acs_cardiogenic_shock",
            "state.etiology == 'non_acs'": "hemodynamic_stabilization",
        },
    )

    nodes["hemodynamic_stabilization"] = _node(
        node_id="hemodynamic_stabilization",
        node_type="plan",
        name="Hemodynamic Stabilization",
        description="Cautious fluid challenge, inotrope initiation (dobutamine first-line), vasopressor if persistent hypotension",
        mandatory=[
            "give_cautious_fluid_challenge_250ml",
            "start_inotrope_dobutamine",
            "order_echocardiography_bedside",
        ],
        allowed=[
            "give_cautious_fluid_challenge_250ml",
            "start_inotrope_dobutamine",
            "order_echocardiography_bedside",
            "start_vasopressor_norepinephrine",
            "place_central_line",
            "place_arterial_line",
            "order_lab_lactate",
            "order_lab_blood_gas",
            "monitor_urine_output",
            "assess_fluid_responsiveness",
        ],
        forbidden=[
            "give_aggressive_fluid_bolus_over_500ml",
            "start_vasopressor_without_volume_assessment",
        ],
        deadlines={
            "give_cautious_fluid_challenge_250ml": 15,
            "start_inotrope_dobutamine": 30,
            "order_echocardiography_bedside": 60,
        },
        source_guideline=src,
        source_section="Recommendation 2: Hemodynamic Stabilization",
        source_quote="Inotropic support with dobutamine is reasonable as first-line therapy (Class IIa). Norepinephrine preferred over dopamine for persistent hypotension (Class IIb)",
        rec_class="IIa",
        evidence="B",
        next_nodes=["mechanical_support_assessment"],
    )

    nodes["acs_cardiogenic_shock"] = _node(
        node_id="acs_cardiogenic_shock",
        node_type="plan",
        name="ACS-Related Cardiogenic Shock",
        description="Urgent revascularization for ACS etiology, hemodynamic support in parallel",
        precondition="state.etiology == 'acs'",
        mandatory=[
            "start_inotrope_dobutamine",
            "activate_cath_lab_emergent",
            "give_aspirin_loading",
            "give_heparin_anticoagulation",
        ],
        allowed=[
            "start_inotrope_dobutamine",
            "activate_cath_lab_emergent",
            "give_aspirin_loading",
            "give_heparin_anticoagulation",
            "start_vasopressor_norepinephrine",
            "give_cautious_fluid_challenge_250ml",
            "order_echocardiography_bedside",
            "place_arterial_line",
            "place_central_line",
            "order_lab_troponin",
            "order_lab_lactate",
        ],
        forbidden=[
            "delay_revascularization_beyond_120min",
            "give_aggressive_fluid_bolus_over_500ml",
        ],
        deadlines={
            "start_inotrope_dobutamine": 30,
            "activate_cath_lab_emergent": 60,
            "give_aspirin_loading": 30,
            "give_heparin_anticoagulation": 60,
        },
        required_prior={
            "activate_cath_lab_emergent": "order_ecg",
        },
        source_guideline=src,
        source_section="Recommendation 3: Revascularization in ACS",
        source_quote="Emergency revascularization is recommended for ACS-related cardiogenic shock (Class I, Level B). SHOCK trial demonstrated survival benefit with early revascularization",
        rec_class="I",
        evidence="B",
        next_nodes=["mechanical_support_assessment"],
    )

    nodes["mechanical_support_assessment"] = _node(
        node_id="mechanical_support_assessment",
        node_type="decision",
        name="Mechanical Circulatory Support Assessment",
        description="Assess need for IABP, Impella, or ECMO based on hemodynamic response",
        mandatory=["assess_hemodynamic_response", "assess_mcs_candidacy"],
        allowed=[
            "assess_hemodynamic_response",
            "assess_mcs_candidacy",
            "place_iabp",
            "place_impella",
            "initiate_va_ecmo",
            "order_lab_lactate",
            "order_echocardiography_bedside",
            "consult_cardiac_surgery",
        ],
        deadlines={
            "assess_hemodynamic_response": 120,
            "assess_mcs_candidacy": 120,
        },
        conditional_rules=[
            {
                "rule_id": "CS-REFRACTORY-MCS",
                "condition": "state.refractory_to_inotropes == True",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["initiate_va_ecmo"],
                    "deadline_minutes": 180,
                },
                "severity": "CRITICAL",
                "description": "Refractory cardiogenic shock despite inotropes/vasopressors warrants VA-ECMO consideration",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 4: Mechanical Circulatory Support",
        source_quote="Mechanical circulatory support is reasonable for patients with refractory cardiogenic shock (Class IIa, Level B). IABP for selected ACS patients, Impella/ECMO for refractory cases",
        next_nodes=["monitoring"],
    )

    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Monitoring & Reassessment",
        description="Serial hemodynamic monitoring, lactate clearance, organ perfusion assessment",
        mandatory=["monitor_hemodynamics_continuous", "remeasure_lactate_q2h"],
        allowed=[
            "monitor_hemodynamics_continuous",
            "remeasure_lactate_q2h",
            "monitor_urine_output",
            "order_lab_bmp",
            "order_lab_blood_gas",
            "assess_mental_status",
            "order_echocardiography_follow_up",
            "titrate_inotrope_vasopressor",
        ],
        deadlines={
            "monitor_hemodynamics_continuous": 15,
            "remeasure_lactate_q2h": 120,
        },
        source_guideline=src,
        source_section="Monitoring",
        source_quote="Serial lactate monitoring to assess response to therapy. Target MAP >65 mmHg, urine output >0.5 mL/kg/h",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Escalation",
        description="Assess for ICU step-down, MCS weaning, or transplant evaluation",
        mandatory=["assess_discharge_readiness"],
        allowed=[
            "assess_discharge_readiness",
            "continue_icu_care",
            "wean_mcs",
            "evaluate_transplant_candidacy",
            "arrange_cardiac_rehabilitation",
        ],
        source_guideline=src,
        source_section="Disposition",
        source_quote="Early referral to advanced heart failure center for MCS-dependent or transplant-eligible patients",
    )

    return {
        "graph_id": "aha_cardiogenic_shock_2017",
        "guideline_name": "AHA/ACC 2017 Clinical Expert Consensus on Cardiogenic Shock",
        "version": "2017.1",
        "metadata": {
            "source": "AHA/ACC Cardiogenic Shock Scientific Statement 2017",
            "doi": doi,
            "journal": "Circulation",
            "recommendation_system": "AHA Class/Level",
            "description": "Expert consensus on cardiogenic shock management including pharmacologic support, mechanical circulatory support, and revascularization",
            "key_evidence": "SHOCK trial: early revascularization reduces 6-month mortality (50% vs 63%). Dobutamine first-line inotrope. Norepinephrine preferred over dopamine (SOAP II trial).",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 10. Post-Arrest TTM (AHA/ILCOR 2023)
# =========================================================================


def build_ttm_post_arrest_graph() -> dict[str, Any]:
    """AHA/ILCOR 2023 Post-Arrest TTM guideline graph."""
    src = "AHA/ILCOR Post-Arrest TTM 2023"
    doi = "10.1161/CIR.0000000000001095"

    nodes: dict[str, Any] = {}

    nodes["rosc_recognition"] = _node(
        node_id="rosc_recognition",
        node_type="decision",
        name="ROSC Recognition & Initial Stabilization",
        description="Confirm sustained ROSC, secure airway, establish monitoring",
        mandatory=["confirm_sustained_rosc", "secure_airway_if_needed", "order_ecg"],
        allowed=[
            "confirm_sustained_rosc",
            "secure_airway_if_needed",
            "order_ecg",
            "assess_vital_signs",
            "establish_iv_access",
            "order_lab_blood_gas",
            "order_lab_lactate",
            "order_lab_troponin",
            "order_lab_bmp",
            "place_arterial_line",
        ],
        deadlines={
            "confirm_sustained_rosc": 5,
            "secure_airway_if_needed": 15,
            "order_ecg": 15,
        },
        source_guideline=src,
        source_section="Post-ROSC Initial Stabilization",
        source_quote="Immediate post-ROSC care includes airway management, hemodynamic optimization, and 12-lead ECG to identify STEMI",
        next_nodes=["ttm_initiation"],
    )

    nodes["ttm_initiation"] = _node(
        node_id="ttm_initiation",
        node_type="plan",
        name="TTM Initiation (Target 32-36°C)",
        description="Initiate targeted temperature management within 6h of ROSC, target 32-36°C",
        mandatory=[
            "initiate_ttm_target_32_36",
            "place_core_temperature_probe",
            "order_lab_blood_gas",
        ],
        allowed=[
            "initiate_ttm_target_32_36",
            "place_core_temperature_probe",
            "order_lab_blood_gas",
            "give_sedation_for_ttm",
            "give_neuromuscular_blockade_for_shivering",
            "apply_surface_cooling_device",
            "apply_intravascular_cooling_device",
            "order_lab_cbc",
            "order_lab_coagulation",
            "order_lab_bmp",
            "monitor_ecg_continuous",
        ],
        forbidden=[
            "give_antipyretic_alone_as_ttm",
            "delay_ttm_beyond_6h_rosc",
        ],
        deadlines={
            "initiate_ttm_target_32_36": 360,
            "place_core_temperature_probe": 60,
        },
        source_guideline=src,
        source_section="Recommendation 1-2: TTM Initiation",
        source_quote="TTM is recommended for comatose adult patients after cardiac arrest (Class I, Level B). Target temperature 32-36°C. Initiate as soon as feasible, ideally within 6h of ROSC",
        rec_class="I",
        evidence="B",
        next_nodes=["ttm_maintenance"],
    )

    nodes["ttm_maintenance"] = _node(
        node_id="ttm_maintenance",
        node_type="plan",
        name="TTM Maintenance (24h at Target)",
        description="Maintain target temperature for at least 24 hours, manage shivering and complications",
        mandatory=[
            "maintain_target_temperature_24h",
            "monitor_core_temperature_q1h",
        ],
        allowed=[
            "maintain_target_temperature_24h",
            "monitor_core_temperature_q1h",
            "manage_shivering",
            "give_sedation_for_ttm",
            "give_neuromuscular_blockade_for_shivering",
            "order_lab_blood_gas",
            "order_lab_bmp",
            "order_lab_glucose",
            "monitor_ecg_continuous",
            "assess_hemodynamic_status",
        ],
        forbidden=["premature_rewarming_before_24h"],
        deadlines={
            "monitor_core_temperature_q1h": 60,
        },
        source_guideline=src,
        source_section="Recommendation 3: TTM Maintenance",
        source_quote="Maintain target temperature for at least 24 hours. Continuously monitor core temperature. Manage shivering to ensure temperature target adherence",
        rec_class="I",
        evidence="B",
        next_nodes=["controlled_rewarming"],
    )

    nodes["controlled_rewarming"] = _node(
        node_id="controlled_rewarming",
        node_type="plan",
        name="Controlled Rewarming (0.25°C/h)",
        description="Slow controlled rewarming at 0.25°C/h, avoid fever for 72h after ROSC",
        mandatory=[
            "initiate_controlled_rewarming_0_25_per_h",
            "prevent_fever_post_rewarming",
        ],
        allowed=[
            "initiate_controlled_rewarming_0_25_per_h",
            "prevent_fever_post_rewarming",
            "monitor_core_temperature_q1h",
            "order_lab_bmp",
            "order_lab_glucose",
            "order_lab_blood_gas",
            "assess_hemodynamic_status",
            "titrate_sedation",
        ],
        forbidden=[
            "rapid_rewarming_above_0_5_per_h",
            "allow_fever_above_37_7",
        ],
        deadlines={
            "initiate_controlled_rewarming_0_25_per_h": 1500,
        },
        source_guideline=src,
        source_section="Recommendation 4: Rewarming",
        source_quote="Controlled rewarming at 0.25°C/h is recommended. Fever prevention for at least 72h after ROSC. Rapid rewarming may worsen neurological outcomes",
        rec_class="I",
        evidence="C",
        next_nodes=["neuroprognostication"],
    )

    nodes["neuroprognostication"] = _node(
        node_id="neuroprognostication",
        node_type="enquiry",
        name="Neuroprognostication (≥72h Post-ROSC)",
        description="Multimodal neuroprognostication no earlier than 72h after ROSC and normothermia",
        mandatory=["perform_neurological_exam_72h", "order_eeg"],
        allowed=[
            "perform_neurological_exam_72h",
            "order_eeg",
            "assess_pupillary_light_reflex",
            "assess_corneal_reflex",
            "order_imaging_mri_brain",
            "order_lab_nse",
            "assess_ssep",
            "assess_gcs_motor",
        ],
        forbidden=["withdraw_care_before_72h_normothermia"],
        deadlines={
            "perform_neurological_exam_72h": 4320,
        },
        source_guideline=src,
        source_section="Recommendation 5: Neuroprognostication",
        source_quote="Neuroprognostication should be performed no earlier than 72h after ROSC and return to normothermia using multimodal approach (Class I, Level B). No single test should be used in isolation",
        rec_class="I",
        evidence="B",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition",
        description="ICU step-down, rehabilitation, or goals-of-care discussion based on neuroprognostication",
        mandatory=["assess_discharge_readiness"],
        allowed=[
            "assess_discharge_readiness",
            "continue_icu_care",
            "arrange_rehabilitation",
            "goals_of_care_discussion",
        ],
        source_guideline=src,
        source_section="Disposition",
        source_quote="Disposition guided by neurological recovery trajectory and multimodal prognostication findings",
    )

    return {
        "graph_id": "aha_ttm_post_arrest_2023",
        "guideline_name": "AHA/ILCOR 2023 Guidelines for Post-Cardiac Arrest Targeted Temperature Management",
        "version": "2023.1",
        "metadata": {
            "source": "AHA/ILCOR Post-Arrest TTM Guidelines 2023",
            "doi": doi,
            "journal": "Circulation",
            "recommendation_system": "AHA Class/Level",
            "description": "Evidence-based guideline for post-cardiac arrest TTM including initiation, maintenance, rewarming, and neuroprognostication",
            "key_evidence": "TTM at 32-36°C improves neurological outcomes (HACA trial, Bernard 2002). Rewarming at 0.25°C/h prevents rebound hyperthermia. Neuroprognostication requires multimodal approach at ≥72h (Sandroni 2022).",
        },
        "entry_node": "rosc_recognition",
        "nodes": nodes,
    }


# =========================================================================
# 11. Pleural Disease (BTS 2023)
# =========================================================================


def build_pleural_disease_graph() -> dict[str, Any]:
    """BTS 2023 Pleural Disease guideline graph."""
    src = "BTS Pleural Disease Guidelines 2023"
    doi = "10.1136/thorax-2022-219784"

    nodes: dict[str, Any] = {}

    nodes["clinical_assessment"] = _node(
        node_id="clinical_assessment",
        node_type="decision",
        name="Pleural Effusion Clinical Assessment",
        description="History, physical exam, imaging to confirm effusion and assess size",
        mandatory=["assess_respiratory_status", "order_imaging_chest_xray", "assess_vital_signs"],
        allowed=[
            "assess_respiratory_status",
            "order_imaging_chest_xray",
            "assess_vital_signs",
            "order_imaging_chest_ultrasound",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_albumin",
            "order_lab_ldh_serum",
            "order_lab_total_protein_serum",
            "assess_clinical_context",
        ],
        deadlines={
            "assess_respiratory_status": 30,
            "order_imaging_chest_xray": 60,
        },
        source_guideline=src,
        source_section="Initial Assessment",
        source_quote="Chest radiograph should be performed in all patients with suspected pleural effusion. Thoracic ultrasound is recommended to guide intervention",
        next_nodes=["diagnostic_thoracentesis"],
    )

    nodes["diagnostic_thoracentesis"] = _node(
        node_id="diagnostic_thoracentesis",
        node_type="plan",
        name="Diagnostic Thoracentesis & Light's Criteria",
        description="Ultrasound-guided thoracentesis for fluid analysis; classify via Light's criteria",
        mandatory=[
            "perform_ultrasound_guided_thoracentesis",
            "send_fluid_protein_ldh_ph",
            "send_fluid_cell_count_differential",
        ],
        allowed=[
            "perform_ultrasound_guided_thoracentesis",
            "send_fluid_protein_ldh_ph",
            "send_fluid_cell_count_differential",
            "send_fluid_glucose",
            "send_fluid_cytology",
            "send_fluid_culture_gram_stain",
            "send_fluid_amylase",
            "order_lab_ldh_serum",
            "order_lab_total_protein_serum",
        ],
        forbidden=["thoracentesis_without_ultrasound_guidance"],
        deadlines={
            "perform_ultrasound_guided_thoracentesis": 240,
            "send_fluid_protein_ldh_ph": 240,
        },
        required_prior={
            "send_fluid_protein_ldh_ph": "perform_ultrasound_guided_thoracentesis",
            "send_fluid_cell_count_differential": "perform_ultrasound_guided_thoracentesis",
        },
        source_guideline=src,
        source_section="Recommendation 1-2: Diagnostic Thoracentesis",
        source_quote="Thoracic ultrasound should be used to guide pleural intervention (Grade A). Light's criteria: exudate if protein ratio >0.5 OR LDH ratio >0.6 OR LDH >2/3 upper limit",
        rec_class="I",
        evidence="A",
        conditional_next={
            "state.fluid_ph < 7.2": "complicated_parapneumonic_empyema",
            "state.effusion_type == 'malignant'": "malignant_effusion_management",
            "state.effusion_type == 'transudative'": "transudative_management",
        },
    )

    nodes["transudative_management"] = _node(
        node_id="transudative_management",
        node_type="plan",
        name="Transudative Effusion Management",
        description="Treat underlying cause (heart failure, cirrhosis); no chest drain unless symptomatic",
        precondition="state.effusion_type == 'transudative'",
        mandatory=["treat_underlying_cause", "reassess_respiratory_status"],
        allowed=[
            "treat_underlying_cause",
            "reassess_respiratory_status",
            "give_diuretics_if_heart_failure",
            "therapeutic_thoracentesis_if_symptomatic",
            "order_imaging_chest_xray_follow_up",
        ],
        deadlines={
            "treat_underlying_cause": 120,
        },
        source_guideline=src,
        source_section="Recommendation 3: Transudative Effusion",
        source_quote="Transudative effusions should be managed by treating the underlying condition. Therapeutic aspiration for symptomatic relief when needed",
        next_nodes=["follow_up"],
    )

    nodes["complicated_parapneumonic_empyema"] = _node(
        node_id="complicated_parapneumonic_empyema",
        node_type="plan",
        name="Complicated Parapneumonic Effusion / Empyema",
        description="pH<7.2 or frank pus requires urgent chest drain + antibiotics + intrapleural fibrinolytics",
        precondition="state.fluid_ph < 7.2",
        mandatory=[
            "insert_chest_drain_urgent",
            "give_broad_spectrum_antibiotics",
            "send_fluid_culture_gram_stain",
        ],
        allowed=[
            "insert_chest_drain_urgent",
            "give_broad_spectrum_antibiotics",
            "send_fluid_culture_gram_stain",
            "give_intrapleural_tpa_dnase",
            "order_imaging_ct_chest_contrast",
            "request_thoracic_surgery_consultation",
            "order_lab_cbc",
            "order_lab_crp",
            "monitor_drain_output",
        ],
        deadlines={
            "insert_chest_drain_urgent": 60,
            "give_broad_spectrum_antibiotics": 60,
        },
        conditional_rules=[
            {
                "rule_id": "PLEURAL-FIBRINOLYTICS",
                "condition": "state.multiloculated == True",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["give_intrapleural_tpa_dnase"],
                    "deadline_minutes": 1440,
                },
                "severity": "HIGH",
                "description": "Multiloculated empyema benefits from intrapleural tPA/DNase (MIST2 trial)",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 4-5: Parapneumonic / Empyema",
        source_quote="Pleural fluid pH <7.2 indicates complicated parapneumonic effusion requiring chest drain (Grade B). Intrapleural tPA/DNase reduces surgical referral (MIST2 trial)",
        rec_class="I",
        evidence="B",
        next_nodes=["follow_up"],
    )

    nodes["malignant_effusion_management"] = _node(
        node_id="malignant_effusion_management",
        node_type="plan",
        name="Malignant Pleural Effusion Management",
        description="Symptom relief via IPC or talc pleurodesis for recurrent malignant effusion",
        precondition="state.effusion_type == 'malignant'",
        mandatory=[
            "discuss_management_options_with_patient",
            "therapeutic_thoracentesis_if_symptomatic",
        ],
        allowed=[
            "discuss_management_options_with_patient",
            "therapeutic_thoracentesis_if_symptomatic",
            "insert_indwelling_pleural_catheter",
            "perform_talc_pleurodesis",
            "request_oncology_consultation",
            "order_imaging_ct_chest_contrast",
            "send_fluid_cytology",
            "assess_performance_status",
        ],
        deadlines={
            "therapeutic_thoracentesis_if_symptomatic": 120,
        },
        source_guideline=src,
        source_section="Recommendation 6: Malignant Effusion",
        source_quote="IPC and talc pleurodesis are both effective for recurrent malignant effusion (TIME2 trial). Patient preference should guide choice",
        next_nodes=["follow_up"],
    )

    nodes["follow_up"] = _node(
        node_id="follow_up",
        node_type="enquiry",
        name="Follow-Up & Reassessment",
        description="Serial imaging, drain assessment, treatment response evaluation",
        mandatory=["order_imaging_chest_xray_follow_up", "reassess_respiratory_status"],
        allowed=[
            "order_imaging_chest_xray_follow_up",
            "reassess_respiratory_status",
            "monitor_drain_output",
            "order_lab_cbc",
            "order_lab_crp",
            "assess_drain_removal_criteria",
        ],
        deadlines={
            "order_imaging_chest_xray_follow_up": 1440,
        },
        source_guideline=src,
        source_section="Follow-Up",
        source_quote="Follow-up CXR recommended after intervention. Drain removal when output <200 mL/day and lung re-expanded",
    )

    return {
        "graph_id": "bts_pleural_disease_2023",
        "guideline_name": "BTS 2023 Guideline for Pleural Disease",
        "version": "2023.1",
        "metadata": {
            "source": "British Thoracic Society Pleural Disease Guideline 2023",
            "doi": doi,
            "journal": "Thorax",
            "recommendation_system": "SIGN Grading",
            "description": "Evidence-based guideline for diagnosis and management of pleural effusions including parapneumonic, empyema, and malignant effusions",
            "key_evidence": "Light's criteria: sensitivity 98% for exudates. pH<7.2 predicts need for drainage. MIST2 trial: intrapleural tPA/DNase reduces surgical referral. TIME2 trial: IPC non-inferior to pleurodesis.",
        },
        "entry_node": "clinical_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 12. Accidental Hypothermia (ERC 2021)
# =========================================================================


def build_hypothermia_graph() -> dict[str, Any]:
    """ERC 2021 Accidental Hypothermia guideline graph."""
    src = "ERC Accidental Hypothermia Guidelines 2021"
    doi = "10.1016/j.resuscitation.2021.02.007"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Hypothermia Classification",
        description="Measure core temperature, classify severity (mild 32-35°C, moderate 28-32°C, severe <28°C)",
        mandatory=["measure_core_temperature", "assess_vital_signs", "assess_level_of_consciousness"],
        allowed=[
            "measure_core_temperature",
            "assess_vital_signs",
            "assess_level_of_consciousness",
            "order_ecg",
            "order_lab_blood_gas",
            "order_lab_glucose",
            "order_lab_bmp",
            "order_lab_cbc",
            "order_lab_coagulation",
            "establish_iv_access",
        ],
        deadlines={
            "measure_core_temperature": 10,
            "assess_vital_signs": 10,
        },
        source_guideline=src,
        source_section="Initial Assessment",
        source_quote="Core temperature measurement with esophageal or bladder probe is recommended. Swiss Staging System: HT I (32-35°C), HT II (28-32°C), HT III (<28°C), HT IV (arrest)",
        conditional_next={
            "state.core_temp_c >= 32": "mild_hypothermia",
            "state.core_temp_c >= 28 and state.core_temp_c < 32": "moderate_hypothermia",
            "state.core_temp_c < 28": "severe_hypothermia",
        },
    )

    nodes["mild_hypothermia"] = _node(
        node_id="mild_hypothermia",
        node_type="plan",
        name="Mild Hypothermia Management (32-35°C)",
        description="Passive external rewarming, warm environment, warm IV fluids",
        precondition="state.core_temp_c >= 32",
        mandatory=[
            "remove_wet_clothing",
            "passive_external_rewarming",
            "give_warm_iv_fluids_38_42c",
        ],
        allowed=[
            "remove_wet_clothing",
            "passive_external_rewarming",
            "give_warm_iv_fluids_38_42c",
            "monitor_ecg_continuous",
            "monitor_core_temperature_q30min",
            "give_warm_beverages_if_conscious",
            "order_lab_glucose",
        ],
        deadlines={
            "remove_wet_clothing": 15,
            "passive_external_rewarming": 30,
        },
        source_guideline=src,
        source_section="Recommendation 1: Mild Hypothermia (HT I)",
        source_quote="Passive external rewarming (warm environment, insulation, removal of wet clothing) is effective for mild hypothermia. Warm IV fluids (38-42°C) prevent further cooling",
        next_nodes=["monitoring"],
    )

    nodes["moderate_hypothermia"] = _node(
        node_id="moderate_hypothermia",
        node_type="plan",
        name="Moderate Hypothermia Management (28-32°C)",
        description="Active external rewarming, minimize handling, monitor for arrhythmias",
        precondition="state.core_temp_c >= 28 and state.core_temp_c < 32",
        mandatory=[
            "active_external_rewarming",
            "give_warm_iv_fluids_38_42c",
            "monitor_ecg_continuous",
            "minimize_patient_movement",
        ],
        allowed=[
            "active_external_rewarming",
            "give_warm_iv_fluids_38_42c",
            "monitor_ecg_continuous",
            "minimize_patient_movement",
            "monitor_core_temperature_q30min",
            "order_lab_blood_gas",
            "order_lab_bmp",
            "order_lab_glucose",
            "assess_hemodynamic_status",
        ],
        forbidden=[
            "rough_handling_or_rapid_movement",
        ],
        deadlines={
            "active_external_rewarming": 30,
            "monitor_ecg_continuous": 15,
        },
        source_guideline=src,
        source_section="Recommendation 2: Moderate Hypothermia (HT II)",
        source_quote="Active external rewarming with forced warm air or chemical heat packs. Handle gently to avoid triggering ventricular fibrillation. Continuous ECG monitoring for arrhythmias",
        next_nodes=["monitoring"],
    )

    nodes["severe_hypothermia"] = _node(
        node_id="severe_hypothermia",
        node_type="plan",
        name="Severe Hypothermia Management (<28°C)",
        description="Active internal rewarming, avoid rough handling, withhold drugs until >30°C, ECLS if cardiac arrest",
        precondition="state.core_temp_c < 28",
        mandatory=[
            "active_internal_rewarming",
            "minimize_patient_movement",
            "monitor_ecg_continuous",
            "give_warm_iv_fluids_38_42c",
        ],
        allowed=[
            "active_internal_rewarming",
            "minimize_patient_movement",
            "monitor_ecg_continuous",
            "give_warm_iv_fluids_38_42c",
            "initiate_ecls_if_cardiac_arrest",
            "warm_peritoneal_lavage",
            "warm_bladder_irrigation",
            "order_lab_blood_gas",
            "order_lab_bmp",
            "order_lab_coagulation",
            "assess_hemodynamic_status",
        ],
        forbidden=[
            "rough_handling_or_rapid_movement",
            "give_iv_medications_below_30c",
            "defibrillate_more_than_3_times_below_30c",
        ],
        deadlines={
            "active_internal_rewarming": 30,
            "monitor_ecg_continuous": 10,
        },
        conditional_rules=[
            {
                "rule_id": "HYPO-CARDIAC-ARREST-ECLS",
                "condition": "state.cardiac_arrest == True and state.core_temp_c < 28",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["initiate_ecls_if_cardiac_arrest"],
                    "deadline_minutes": 60,
                },
                "severity": "CRITICAL",
                "description": "Hypothermic cardiac arrest <28°C should receive ECLS rewarming; do not terminate resuscitation until rewarmed",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 3-4: Severe Hypothermia (HT III/IV)",
        source_quote="Active internal rewarming recommended for severe hypothermia. ECLS (VA-ECMO) for hypothermic cardiac arrest. Withhold IV drugs until core temp >30°C. Limit to 3 defibrillation attempts below 30°C",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring"],
    )

    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Rewarming Monitoring",
        description="Serial core temperature, ECG rhythm, electrolytes, assess for afterdrop phenomenon",
        mandatory=["monitor_core_temperature_q30min", "monitor_ecg_continuous"],
        allowed=[
            "monitor_core_temperature_q30min",
            "monitor_ecg_continuous",
            "order_lab_bmp",
            "order_lab_blood_gas",
            "order_lab_glucose",
            "assess_hemodynamic_status",
            "assess_for_afterdrop",
        ],
        deadlines={
            "monitor_core_temperature_q30min": 30,
        },
        source_guideline=src,
        source_section="Monitoring During Rewarming",
        source_quote="Afterdrop phenomenon: continued temperature decrease despite rewarming due to redistribution of cold peripheral blood. Monitor continuously",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition",
        description="Continue rewarming until normothermic, assess for underlying cause, ICU or discharge",
        mandatory=["assess_discharge_readiness"],
        allowed=[
            "assess_discharge_readiness",
            "continue_icu_care",
            "investigate_underlying_cause",
            "continue_monitoring",
        ],
        source_guideline=src,
        source_section="Disposition",
        source_quote="Do not declare death until rewarmed to >32°C. 'No one is dead until warm and dead'",
    )

    return {
        "graph_id": "erc_hypothermia_2021",
        "guideline_name": "ERC 2021 Guidelines for Accidental Hypothermia",
        "version": "2021.1",
        "metadata": {
            "source": "European Resuscitation Council Hypothermia Guidelines 2021",
            "doi": doi,
            "journal": "Resuscitation",
            "recommendation_system": "GRADE",
            "description": "Evidence-based guideline for accidental hypothermia management including classification, rewarming strategies, and cardiac arrest management",
            "key_evidence": "ECLS survival rate 47-63% for hypothermic cardiac arrest (Monika review). Afterdrop phenomenon. Withhold drugs <30°C. 'No one is dead until warm and dead' principle.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 13. Acute Limb Ischemia (ESVS 2020)
# =========================================================================


def build_acute_limb_ischemia_graph() -> dict[str, Any]:
    """ESVS 2020 Acute Limb Ischemia guideline graph."""
    src = "ESVS Acute Limb Ischemia Guidelines 2020"
    doi = "10.1016/j.ejvs.2019.09.006"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Acute Limb Ischemia Assessment (6Ps)",
        description="Assess 6Ps (Pain, Pallor, Pulselessness, Paresthesia, Paralysis, Poikilothermia), Rutherford classification",
        mandatory=["assess_6ps", "assess_rutherford_classification", "assess_vital_signs"],
        allowed=[
            "assess_6ps",
            "assess_rutherford_classification",
            "assess_vital_signs",
            "assess_ankle_brachial_index",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_coagulation",
            "order_lab_ck",
            "order_lab_lactate",
            "order_ecg",
            "establish_iv_access",
        ],
        deadlines={
            "assess_6ps": 10,
            "assess_rutherford_classification": 15,
        },
        source_guideline=src,
        source_section="Initial Assessment",
        source_quote="Clinical assessment should be immediate using the 6Ps and Rutherford classification: I (viable), IIa (marginally threatened), IIb (immediately threatened), III (irreversible)",
        conditional_next={
            "state.rutherford_class == 'III'": "irreversible_ischemia",
            "state.rutherford_class in ('IIa', 'IIb')": "anticoagulation_imaging",
        },
    )

    nodes["anticoagulation_imaging"] = _node(
        node_id="anticoagulation_imaging",
        node_type="plan",
        name="Immediate Heparin & Vascular Imaging",
        description="Systemic heparin within 30min, CTA or duplex for operative planning",
        mandatory=[
            "give_heparin_bolus_80u_kg",
            "order_imaging_cta_lower_extremity",
            "request_vascular_surgery_consultation",
        ],
        allowed=[
            "give_heparin_bolus_80u_kg",
            "order_imaging_cta_lower_extremity",
            "request_vascular_surgery_consultation",
            "order_imaging_duplex_ultrasound",
            "give_iv_analgesia",
            "start_heparin_infusion",
            "order_lab_ptt",
            "order_lab_ck",
            "order_lab_bmp",
        ],
        forbidden=[
            "delay_heparin_for_imaging",
        ],
        deadlines={
            "give_heparin_bolus_80u_kg": 30,
            "order_imaging_cta_lower_extremity": 60,
            "request_vascular_surgery_consultation": 60,
        },
        source_guideline=src,
        source_section="Recommendation 1-2: Anticoagulation & Imaging",
        source_quote="Immediate systemic heparin is recommended to prevent thrombus propagation (Class I, Level B). CTA provides anatomical roadmap for revascularization planning",
        rec_class="I",
        evidence="B",
        conditional_next={
            "state.rutherford_class == 'IIb'": "emergent_revascularization",
            "state.rutherford_class == 'IIa'": "urgent_revascularization",
        },
    )

    nodes["urgent_revascularization"] = _node(
        node_id="urgent_revascularization",
        node_type="plan",
        name="Urgent Revascularization (Rutherford IIa)",
        description="Surgical embolectomy or catheter-directed thrombolysis within 6-24h",
        precondition="state.rutherford_class == 'IIa'",
        mandatory=[
            "plan_revascularization_strategy",
            "continue_heparin_infusion",
        ],
        allowed=[
            "plan_revascularization_strategy",
            "continue_heparin_infusion",
            "perform_surgical_embolectomy",
            "perform_catheter_directed_thrombolysis",
            "order_lab_ck",
            "order_lab_bmp",
            "monitor_limb_perfusion",
            "give_iv_analgesia",
        ],
        deadlines={
            "plan_revascularization_strategy": 360,
        },
        source_guideline=src,
        source_section="Recommendation 3: Revascularization Strategy",
        source_quote="Rutherford IIa: urgent revascularization recommended. Catheter-directed thrombolysis or surgical embolectomy depending on etiology (embolic vs thrombotic)",
        next_nodes=["post_revascularization"],
    )

    nodes["emergent_revascularization"] = _node(
        node_id="emergent_revascularization",
        node_type="plan",
        name="Emergent Revascularization (Rutherford IIb)",
        description="Emergent surgical revascularization required; thrombolysis contraindicated",
        precondition="state.rutherford_class == 'IIb'",
        mandatory=[
            "perform_emergent_surgical_revascularization",
            "continue_heparin_infusion",
        ],
        allowed=[
            "perform_emergent_surgical_revascularization",
            "continue_heparin_infusion",
            "perform_on_table_angiography",
            "assess_fasciotomy_need",
            "order_lab_ck",
            "order_lab_bmp",
            "order_lab_blood_gas",
        ],
        forbidden=["catheter_directed_thrombolysis_IIb"],
        deadlines={
            "perform_emergent_surgical_revascularization": 120,
        },
        source_guideline=src,
        source_section="Recommendation 4: Emergent Revascularization",
        source_quote="Rutherford IIb requires emergent surgical revascularization. Thrombolysis is contraindicated for immediately threatened limbs due to time delay",
        rec_class="I",
        evidence="B",
        next_nodes=["post_revascularization"],
    )

    nodes["irreversible_ischemia"] = _node(
        node_id="irreversible_ischemia",
        node_type="plan",
        name="Irreversible Ischemia (Rutherford III)",
        description="Amputation planning; revascularization contraindicated due to reperfusion injury risk",
        precondition="state.rutherford_class == 'III'",
        mandatory=[
            "assess_amputation_level",
            "give_iv_analgesia",
        ],
        allowed=[
            "assess_amputation_level",
            "give_iv_analgesia",
            "request_vascular_surgery_consultation",
            "order_lab_ck",
            "order_lab_bmp",
            "give_heparin_bolus_80u_kg",
        ],
        forbidden=[
            "revascularization_irreversible_ischemia",
        ],
        deadlines={
            "assess_amputation_level": 120,
        },
        source_guideline=src,
        source_section="Recommendation 5: Irreversible Ischemia",
        source_quote="Rutherford III: revascularization is contraindicated due to lethal reperfusion injury (rhabdomyolysis, hyperkalemia, MODS). Primary amputation should be considered",
        next_nodes=["post_revascularization"],
    )

    nodes["post_revascularization"] = _node(
        node_id="post_revascularization",
        node_type="enquiry",
        name="Post-Revascularization Monitoring",
        description="Monitor for reperfusion injury, compartment syndrome, serial CK and electrolytes",
        mandatory=["monitor_limb_perfusion", "order_lab_ck_serial", "assess_compartment_syndrome"],
        allowed=[
            "monitor_limb_perfusion",
            "order_lab_ck_serial",
            "assess_compartment_syndrome",
            "perform_fasciotomy_if_compartment_syndrome",
            "order_lab_bmp",
            "order_lab_blood_gas",
            "monitor_urine_output",
            "give_iv_fluids_for_rhabdomyolysis",
            "continue_heparin_infusion",
        ],
        deadlines={
            "monitor_limb_perfusion": 30,
            "assess_compartment_syndrome": 120,
        },
        conditional_rules=[
            {
                "rule_id": "ALI-COMPARTMENT-SYNDROME",
                "condition": "state.compartment_pressure_mmhg > 30",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["perform_fasciotomy_if_compartment_syndrome"],
                    "deadline_minutes": 60,
                },
                "severity": "CRITICAL",
                "description": "Compartment pressure >30 mmHg requires emergent fasciotomy to prevent irreversible muscle necrosis",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 6: Post-Revascularization",
        source_quote="Compartment syndrome occurs in 10-20% after revascularization. CK monitoring for rhabdomyolysis. Fasciotomy if compartment pressure >30 mmHg or clinical signs",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition",
        description="Long-term anticoagulation, investigate etiology (embolic source), vascular follow-up",
        mandatory=["assess_discharge_readiness"],
        allowed=[
            "assess_discharge_readiness",
            "initiate_long_term_anticoagulation",
            "investigate_embolic_source",
            "order_echocardiography",
            "schedule_vascular_follow_up",
        ],
        source_guideline=src,
        source_section="Long-term Management",
        source_quote="Long-term anticoagulation for embolic ALI. Investigate cardiac source (echocardiography, Holter). Duplex surveillance post-revascularization",
    )

    return {
        "graph_id": "esvs_acute_limb_ischemia_2020",
        "guideline_name": "ESVS 2020 Clinical Practice Guidelines on Acute Limb Ischemia",
        "version": "2020.1",
        "metadata": {
            "source": "ESVS Acute Limb Ischemia Guidelines 2020",
            "doi": doi,
            "journal": "European Journal of Vascular and Endovascular Surgery",
            "recommendation_system": "GRADE",
            "description": "Evidence-based guideline for acute limb ischemia including Rutherford classification, anticoagulation, revascularization, and compartment syndrome management",
            "key_evidence": "Immediate heparin prevents thrombus propagation. Rutherford IIb requires emergent surgery (<6h). Compartment syndrome in 10-20%. Revascularization of Rutherford III causes lethal reperfusion injury.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 14. Pediatric DKA (ISPAD 2022)
# =========================================================================


def build_pediatric_dka_graph() -> dict[str, Any]:
    """ISPAD 2022 Pediatric DKA guideline graph."""
    src = "ISPAD Pediatric DKA Guidelines 2022"
    doi = "10.1111/pedi.13406"

    nodes: dict[str, Any] = {}

    nodes["diagnosis"] = _node(
        node_id="diagnosis",
        node_type="decision",
        name="Pediatric DKA Diagnosis",
        description="Confirm DKA criteria: pH<7.3, bicarbonate<15 mmol/L, glucose>200 mg/dL, ketonemia",
        mandatory=["order_lab_blood_gas", "order_lab_bmp", "order_lab_glucose"],
        allowed=[
            "order_lab_blood_gas",
            "order_lab_bmp",
            "order_lab_glucose",
            "order_lab_beta_hydroxybutyrate",
            "order_lab_cbc",
            "order_lab_hba1c",
            "order_lab_phosphate",
            "assess_vital_signs",
            "assess_dehydration_severity",
            "assess_mental_status",
            "establish_iv_access",
            "weigh_patient",
        ],
        deadlines={
            "order_lab_blood_gas": 15,
            "order_lab_bmp": 15,
            "order_lab_glucose": 15,
        },
        source_guideline=src,
        source_section="Diagnosis",
        source_quote="DKA criteria: blood glucose >200 mg/dL (11 mmol/L), venous pH <7.3 OR bicarbonate <15 mmol/L, ketonemia or ketonuria. Classify severity: mild (pH 7.2-7.3), moderate (pH 7.1-7.2), severe (pH <7.1)",
        conditional_next={
            "state.ph < 7.1": "severe_dka_bundle",
            "state.ph >= 7.1": "moderate_mild_dka_bundle",
        },
    )

    nodes["moderate_mild_dka_bundle"] = _node(
        node_id="moderate_mild_dka_bundle",
        node_type="plan",
        name="Mild-Moderate Pediatric DKA (pH ≥7.1)",
        description="IV fluids 0.9% NaCl 10 mL/kg over 1h, then insulin infusion 0.05-0.1 U/kg/h",
        precondition="state.ph >= 7.1",
        mandatory=[
            "give_iv_nacl_10ml_kg_over_1h",
            "start_insulin_infusion_0_05_0_1_u_kg_h",
            "order_lab_glucose_hourly",
            "order_lab_bmp_q2h",
        ],
        allowed=[
            "give_iv_nacl_10ml_kg_over_1h",
            "start_insulin_infusion_0_05_0_1_u_kg_h",
            "order_lab_glucose_hourly",
            "order_lab_bmp_q2h",
            "add_potassium_to_iv_fluids",
            "monitor_vital_signs_q1h",
            "assess_mental_status_q1h",
            "order_lab_blood_gas_q2h",
            "order_lab_phosphate",
        ],
        forbidden=[
            "give_insulin_bolus",
            "give_iv_bicarbonate_routine",
            "give_fluid_rate_exceeding_1_5x_maintenance",
        ],
        deadlines={
            "give_iv_nacl_10ml_kg_over_1h": 30,
            "start_insulin_infusion_0_05_0_1_u_kg_h": 60,
        },
        required_prior={
            "start_insulin_infusion_0_05_0_1_u_kg_h": "give_iv_nacl_10ml_kg_over_1h",
        },
        conditional_rules=[
            {
                "rule_id": "PDKA-POTASSIUM",
                "condition": "state.potassium_meq_l < 5.5",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["add_potassium_to_iv_fluids"],
                    "deadline_minutes": 120,
                },
                "severity": "HIGH",
                "description": "K+ replacement required if serum K+ <5.5 (insulin drives K+ intracellularly). 40 mEq/L KCl in maintenance fluids",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 1-3: Fluid & Insulin",
        source_quote="IV 0.9% NaCl 10-20 mL/kg over first hour. Insulin infusion 0.05-0.1 U/kg/h (NO bolus - cerebral edema risk). Do NOT exceed 1.5x maintenance fluid rate",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )

    nodes["severe_dka_bundle"] = _node(
        node_id="severe_dka_bundle",
        node_type="plan",
        name="Severe Pediatric DKA (pH <7.1)",
        description="ICU-level care, IV fluids 20 mL/kg NaCl, insulin infusion, strict neuro monitoring for cerebral edema",
        precondition="state.ph < 7.1",
        mandatory=[
            "give_iv_nacl_20ml_kg_over_1h",
            "start_insulin_infusion_0_05_0_1_u_kg_h",
            "order_lab_glucose_hourly",
            "order_lab_bmp_q2h",
            "assess_mental_status_q1h",
        ],
        allowed=[
            "give_iv_nacl_20ml_kg_over_1h",
            "start_insulin_infusion_0_05_0_1_u_kg_h",
            "order_lab_glucose_hourly",
            "order_lab_bmp_q2h",
            "assess_mental_status_q1h",
            "add_potassium_to_iv_fluids",
            "monitor_vital_signs_q1h",
            "order_lab_blood_gas_q2h",
            "icu_admission",
            "place_foley_catheter",
            "order_lab_phosphate",
        ],
        forbidden=[
            "give_insulin_bolus",
            "give_iv_bicarbonate_routine",
            "give_fluid_rate_exceeding_1_5x_maintenance",
        ],
        deadlines={
            "give_iv_nacl_20ml_kg_over_1h": 30,
            "start_insulin_infusion_0_05_0_1_u_kg_h": 60,
            "assess_mental_status_q1h": 60,
        },
        required_prior={
            "start_insulin_infusion_0_05_0_1_u_kg_h": "give_iv_nacl_20ml_kg_over_1h",
        },
        conditional_rules=[
            {
                "rule_id": "PDKA-CEREBRAL-EDEMA",
                "condition": "state.gcs < 14 or state.mental_status_declining == True",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["give_mannitol_0_5_1_g_kg"],
                    "deadline_minutes": 15,
                },
                "severity": "CRITICAL",
                "description": "Signs of cerebral edema require immediate mannitol 0.5-1 g/kg or 3% NaCl 2.5-5 mL/kg. Reduce IV fluids by one-third",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 4-5: Severe DKA",
        source_quote="Severe DKA (pH<7.1): ICU admission, 20 mL/kg NaCl initial bolus. NO insulin bolus (increased cerebral edema risk). Cerebral edema occurs in 0.5-1% of pediatric DKA",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )

    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="DKA Monitoring",
        description="Hourly glucose, q2h BMP/blood gas, neurological checks, transition to SubQ insulin",
        mandatory=["order_lab_glucose_hourly", "order_lab_bmp_q2h"],
        allowed=[
            "order_lab_glucose_hourly",
            "order_lab_bmp_q2h",
            "order_lab_blood_gas_q2h",
            "assess_mental_status_q1h",
            "add_dextrose_when_glucose_below_300",
            "adjust_insulin_rate",
            "assess_gap_closure",
            "monitor_fluid_balance",
        ],
        deadlines={
            "order_lab_glucose_hourly": 60,
            "order_lab_bmp_q2h": 120,
        },
        source_guideline=src,
        source_section="Monitoring",
        source_quote="Hourly blood glucose, q2h electrolytes and blood gas. Add dextrose to IV when glucose <300 mg/dL. Transition to SubQ insulin when pH >7.3, bicarb >15, able to eat",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="DKA Resolution & Disposition",
        description="Transition to subcutaneous insulin when DKA resolved, diabetes education",
        mandatory=["assess_dka_resolution"],
        allowed=[
            "assess_dka_resolution",
            "transition_to_subq_insulin",
            "provide_diabetes_education",
            "arrange_endocrine_follow_up",
            "assess_discharge_readiness",
        ],
        source_guideline=src,
        source_section="Resolution & Discharge",
        source_quote="DKA resolved when pH >7.3, bicarbonate >15, beta-hydroxybutyrate <1 mmol/L. Overlap SubQ insulin 30-60min before stopping IV",
    )

    return {
        "graph_id": "ispad_pediatric_dka_2022",
        "guideline_name": "ISPAD 2022 Clinical Practice Consensus Guidelines for Pediatric DKA",
        "version": "2022.1",
        "metadata": {
            "source": "ISPAD Pediatric DKA Guidelines 2022",
            "doi": doi,
            "journal": "Pediatric Diabetes",
            "recommendation_system": "GRADE",
            "description": "Evidence-based guideline for pediatric DKA management emphasizing cerebral edema prevention through controlled fluid and insulin administration",
            "key_evidence": "NO insulin bolus (increased cerebral edema risk, Glaser 2001). Fluid rate <1.5x maintenance. Cerebral edema 0.5-1% incidence, 21-24% mortality. Mannitol for cerebral edema.",
        },
        "entry_node": "diagnosis",
        "nodes": nodes,
    }


# =========================================================================
# 15. Hyperkalemia (UK Kidney Association 2023)
# =========================================================================


def build_hyperkalemia_graph() -> dict[str, Any]:
    """UK Kidney Association 2023 Hyperkalemia guideline graph."""
    src = "UKKA Hyperkalemia Guidelines 2023"
    doi = "10.1186/s12882-023-03340-2"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Hyperkalemia Assessment & ECG",
        description="Confirm true hyperkalemia (exclude hemolysis), assess ECG for changes, classify severity",
        mandatory=["order_ecg_stat", "order_lab_bmp_stat", "assess_vital_signs"],
        allowed=[
            "order_ecg_stat",
            "order_lab_bmp_stat",
            "assess_vital_signs",
            "order_lab_blood_gas",
            "order_lab_cbc",
            "order_lab_glucose",
            "review_medications",
            "assess_renal_function",
            "establish_iv_access",
        ],
        deadlines={
            "order_ecg_stat": 5,
            "order_lab_bmp_stat": 10,
        },
        source_guideline=src,
        source_section="Initial Assessment",
        source_quote="12-lead ECG should be performed immediately when hyperkalemia suspected. Classify: mild (5.5-5.9), moderate (6.0-6.4), severe (≥6.5 mmol/L or ECG changes at any level)",
        conditional_next={
            "state.ecg_changes_present == True": "cardiac_stabilization",
            "state.potassium_meq_l >= 6.5": "cardiac_stabilization",
            "state.potassium_meq_l >= 6.0 and state.ecg_changes_present == False": "potassium_shifting",
        },
    )

    nodes["cardiac_stabilization"] = _node(
        node_id="cardiac_stabilization",
        node_type="plan",
        name="Cardiac Stabilization (Calcium Gluconate)",
        description="IV calcium gluconate within 5 min if ECG changes present; stabilizes cardiac membrane",
        mandatory=[
            "give_calcium_gluconate_10ml_10pct_iv",
            "monitor_ecg_continuous",
        ],
        allowed=[
            "give_calcium_gluconate_10ml_10pct_iv",
            "monitor_ecg_continuous",
            "repeat_calcium_gluconate_if_ecg_persists",
            "assess_vital_signs",
            "establish_iv_access",
        ],
        forbidden=[
            "give_calcium_gluconate_via_peripheral_with_bicarbonate",
        ],
        deadlines={
            "give_calcium_gluconate_10ml_10pct_iv": 5,
            "monitor_ecg_continuous": 5,
        },
        source_guideline=src,
        source_section="Recommendation 1: Cardiac Stabilization",
        source_quote="IV calcium gluconate 10 mL of 10% over 2-5 minutes if ECG changes present (Grade A). Effect within 1-3 min, lasts 30-60 min. May repeat once if ECG changes persist",
        rec_class="I",
        evidence="A",
        next_nodes=["potassium_shifting"],
    )

    nodes["potassium_shifting"] = _node(
        node_id="potassium_shifting",
        node_type="plan",
        name="Potassium Shifting (Insulin+Glucose, Salbutamol)",
        description="Drive potassium intracellularly with insulin+dextrose and nebulized salbutamol",
        mandatory=[
            "give_insulin_10u_with_dextrose_25g",
            "give_salbutamol_nebulized_10_20mg",
        ],
        allowed=[
            "give_insulin_10u_with_dextrose_25g",
            "give_salbutamol_nebulized_10_20mg",
            "monitor_glucose_q15min_for_2h",
            "order_lab_bmp_repeat_1h",
            "monitor_ecg_continuous",
        ],
        deadlines={
            "give_insulin_10u_with_dextrose_25g": 15,
            "give_salbutamol_nebulized_10_20mg": 30,
        },
        required_prior={
            "give_insulin_10u_with_dextrose_25g": "order_lab_bmp_stat",
        },
        source_guideline=src,
        source_section="Recommendation 2: Potassium Shifting",
        source_quote="Insulin 10 units with 25g dextrose IV (lowers K+ by 0.6-1.0 mmol/L in 15-30 min). Nebulized salbutamol 10-20mg (lowers K+ by 0.5-1.0 mmol/L). Monitor glucose for hypoglycemia",
        rec_class="I",
        evidence="A",
        next_nodes=["potassium_removal"],
    )

    nodes["potassium_removal"] = _node(
        node_id="potassium_removal",
        node_type="plan",
        name="Potassium Removal",
        description="Remove total body potassium via sodium bicarbonate (if acidotic), sodium zirconium cyclosilicate, or dialysis",
        mandatory=["assess_need_for_dialysis"],
        allowed=[
            "assess_need_for_dialysis",
            "give_sodium_bicarbonate_if_acidotic",
            "give_sodium_zirconium_cyclosilicate",
            "give_calcium_polystyrene_sulfonate",
            "initiate_hemodialysis",
            "order_lab_bmp_repeat",
            "monitor_ecg_continuous",
            "assess_fluid_status",
        ],
        deadlines={
            "assess_need_for_dialysis": 60,
        },
        conditional_rules=[
            {
                "rule_id": "HYPER-K-DIALYSIS",
                "condition": "state.potassium_meq_l >= 7.0 or state.refractory_to_medical == True",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["initiate_hemodialysis"],
                    "deadline_minutes": 120,
                },
                "severity": "CRITICAL",
                "description": "K+ ≥7.0 or refractory hyperkalemia requires emergent hemodialysis",
            },
            {
                "rule_id": "HYPER-K-BICARB",
                "condition": "state.ph < 7.2",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["give_sodium_bicarbonate_if_acidotic"],
                    "deadline_minutes": 60,
                },
                "severity": "HIGH",
                "description": "Sodium bicarbonate for metabolic acidosis (pH<7.2) helps shift K+ intracellularly",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 3: Potassium Removal",
        source_quote="Sodium bicarbonate 50 mmol IV if acidotic (pH<7.2). Sodium zirconium cyclosilicate (SZC) 10g PO for ongoing removal. Hemodialysis for refractory or K+ ≥7.0 mmol/L",
        next_nodes=["monitoring"],
    )

    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Monitoring & Reassessment",
        description="Serial K+ at 1h, 2h, 4h, 6h; continuous ECG; glucose monitoring post-insulin",
        mandatory=["order_lab_bmp_repeat_1h", "monitor_glucose_q15min_for_2h"],
        allowed=[
            "order_lab_bmp_repeat_1h",
            "monitor_glucose_q15min_for_2h",
            "monitor_ecg_continuous",
            "order_lab_blood_gas",
            "review_medications_causing_hyperkalemia",
            "assess_renal_function",
        ],
        deadlines={
            "order_lab_bmp_repeat_1h": 60,
            "monitor_glucose_q15min_for_2h": 15,
        },
        source_guideline=src,
        source_section="Monitoring",
        source_quote="Repeat K+ at 1, 2, 4, 6 hours. Monitor blood glucose every 15 min for 2 hours after insulin (hypoglycemia risk 10-75%). Continuous ECG until K+ normalized",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Prevention",
        description="Address underlying cause, medication review, dietary counseling, outpatient follow-up",
        mandatory=["assess_discharge_readiness"],
        allowed=[
            "assess_discharge_readiness",
            "review_medications_causing_hyperkalemia",
            "dietary_potassium_counseling",
            "arrange_nephrology_follow_up",
            "continue_monitoring",
        ],
        source_guideline=src,
        source_section="Prevention & Long-term Management",
        source_quote="Review and adjust contributing medications (ACEi, ARB, MRA, NSAIDs, trimethoprim). Low-potassium diet counseling. Consider chronic K+ binder if recurrent",
    )

    return {
        "graph_id": "ukka_hyperkalemia_2023",
        "guideline_name": "UK Kidney Association 2023 Clinical Practice Guidelines for Acute Hyperkalemia in Adults",
        "version": "2023.1",
        "metadata": {
            "source": "UK Kidney Association Hyperkalemia Guidelines 2023",
            "doi": doi,
            "journal": "BMC Nephrology",
            "recommendation_system": "GRADE",
            "description": "Evidence-based guideline for acute hyperkalemia management including cardiac stabilization, potassium shifting, removal, and monitoring",
            "key_evidence": "Calcium gluconate onset 1-3 min (membrane stabilization). Insulin+dextrose lowers K+ 0.6-1.0 mmol/L in 15-30 min. Hypoglycemia risk 10-75% post-insulin. SZC onset 1h.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 16. Severe Malaria (WHO 2023)
# =========================================================================


def build_severe_malaria_graph() -> dict[str, Any]:
    """WHO 2023 Severe Malaria guideline graph."""
    src = "WHO Severe Malaria Guidelines 2023"
    doi = "10.1016/S1473-3099(23)00553-1"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Severe Malaria Recognition",
        description="Confirm parasitemia (RDT/microscopy), assess severity criteria (cerebral, severe anemia, ARDS, renal failure, shock)",
        mandatory=["confirm_parasitemia_rdt_or_smear", "assess_vital_signs", "assess_severity_criteria"],
        allowed=[
            "confirm_parasitemia_rdt_or_smear",
            "assess_vital_signs",
            "assess_severity_criteria",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_glucose",
            "order_lab_lactate",
            "order_lab_blood_gas",
            "order_lab_coagulation",
            "assess_mental_status",
            "establish_iv_access",
        ],
        deadlines={
            "confirm_parasitemia_rdt_or_smear": 15,
            "assess_vital_signs": 10,
            "assess_severity_criteria": 30,
        },
        source_guideline=src,
        source_section="Diagnosis & Severity Assessment",
        source_quote="Severe malaria defined by: parasitemia + one or more severity criteria (cerebral malaria, severe anemia Hb<5, respiratory distress, shock, renal failure, hypoglycemia, acidosis)",
        next_nodes=["artesunate_initiation"],
    )

    nodes["artesunate_initiation"] = _node(
        node_id="artesunate_initiation",
        node_type="plan",
        name="IV Artesunate Initiation (FIRST LINE)",
        description="IV artesunate 2.4 mg/kg at 0, 12, 24h then daily - NOT quinine as first line",
        mandatory=[
            "give_iv_artesunate_2_4mg_kg",
            "check_glucose_immediately",
            "order_lab_cbc",
        ],
        allowed=[
            "give_iv_artesunate_2_4mg_kg",
            "check_glucose_immediately",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_blood_gas",
            "order_lab_lactate",
            "monitor_vital_signs_q1h",
            "assess_mental_status",
            "establish_iv_access",
        ],
        forbidden=[
            "give_quinine_as_first_line",
            "give_oral_act_for_severe_malaria",
            "give_aggressive_iv_fluid_bolus",
        ],
        deadlines={
            "give_iv_artesunate_2_4mg_kg": 60,
            "check_glucose_immediately": 30,
        },
        source_guideline=src,
        source_section="Recommendation 1: Antimalarial Treatment",
        source_quote="IV artesunate (2.4 mg/kg at 0, 12, 24h then daily) is the treatment of choice for severe malaria (strong recommendation). AQUAMAT/SEAQUAMAT trials: 35% mortality reduction vs quinine",
        rec_class="I",
        evidence="A",
        next_nodes=["supportive_management"],
    )

    nodes["supportive_management"] = _node(
        node_id="supportive_management",
        node_type="plan",
        name="Supportive Management",
        description="Correct hypoglycemia, manage fluids cautiously, treat complications",
        mandatory=[
            "monitor_glucose_q4h",
            "give_maintenance_iv_fluids_cautious",
        ],
        allowed=[
            "monitor_glucose_q4h",
            "give_maintenance_iv_fluids_cautious",
            "give_dextrose_bolus_if_hypoglycemic",
            "order_lab_bmp_q12h",
            "order_lab_cbc_q12h",
            "assess_mental_status",
            "order_lab_lactate",
            "give_transfusion_if_hb_below_5",
            "manage_seizures_if_present",
            "initiate_rrt_if_renal_failure",
        ],
        forbidden=[
            "give_aggressive_iv_fluid_bolus",
            "give_steroids_for_cerebral_malaria",
        ],
        deadlines={
            "monitor_glucose_q4h": 240,
        },
        conditional_rules=[
            {
                "rule_id": "MALARIA-HYPOGLYCEMIA",
                "condition": "state.glucose_mg_dl < 60",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["give_dextrose_bolus_if_hypoglycemic"],
                    "deadline_minutes": 15,
                },
                "severity": "CRITICAL",
                "description": "Hypoglycemia (<60 mg/dL) is common in severe malaria (quinine/falciparum-induced). Give 25% dextrose 2 mL/kg IV",
            },
            {
                "rule_id": "MALARIA-SEVERE-ANEMIA",
                "condition": "state.hemoglobin_g_dl < 5",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["give_transfusion_if_hb_below_5"],
                    "deadline_minutes": 120,
                },
                "severity": "CRITICAL",
                "description": "Severe anemia (Hb<5) requires blood transfusion",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 2-4: Supportive Care",
        source_quote="Avoid aggressive IV fluids (increases pulmonary edema risk in severe malaria, FEAST trial). Monitor glucose q4h. Steroids NOT recommended for cerebral malaria (no benefit, increased harm)",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring"],
    )

    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Parasitemia Monitoring & Follow-Up",
        description="Serial parasitemia (q12h until cleared), organ function monitoring, post-artesunate hemolysis watch",
        mandatory=["order_parasite_count_q12h", "monitor_glucose_q4h"],
        allowed=[
            "order_parasite_count_q12h",
            "monitor_glucose_q4h",
            "order_lab_cbc_daily",
            "order_lab_bmp_daily",
            "order_lab_ldh_haptoglobin_for_hemolysis",
            "assess_mental_status",
            "monitor_urine_output",
            "monitor_vital_signs_q4h",
        ],
        deadlines={
            "order_parasite_count_q12h": 720,
            "monitor_glucose_q4h": 240,
        },
        source_guideline=src,
        source_section="Monitoring",
        source_quote="Serial parasite counts q12h until negative. Post-artesunate delayed hemolysis (PADH) may occur 7-14 days post-treatment; monitor Hb weekly for 4 weeks",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Transition to Oral ACT",
        description="Transition to oral ACT after ≥24h IV artesunate and parasite clearance, PADH surveillance",
        mandatory=["assess_transition_to_oral_act"],
        allowed=[
            "assess_transition_to_oral_act",
            "give_oral_act_3day_course",
            "schedule_hemolysis_surveillance_weekly",
            "provide_malaria_prevention_counseling",
            "assess_discharge_readiness",
        ],
        source_guideline=src,
        source_section="Transition & Discharge",
        source_quote="Transition to oral ACT after ≥24h IV artesunate, when patient can tolerate oral medication. Complete 3-day oral ACT course. Monitor for PADH at day 7, 14, 21, 28",
    )

    return {
        "graph_id": "who_severe_malaria_2023",
        "guideline_name": "WHO 2023 Guidelines for the Treatment of Severe Malaria",
        "version": "2023.1",
        "metadata": {
            "source": "WHO Severe Malaria Treatment Guidelines 2023",
            "doi": doi,
            "journal": "The Lancet Infectious Diseases",
            "recommendation_system": "WHO GRADE",
            "description": "Evidence-based guideline for severe malaria treatment emphasizing IV artesunate as first-line, cautious fluid management, and hypoglycemia prevention",
            "key_evidence": "AQUAMAT trial: artesunate reduces mortality 22.5% vs 30.5% quinine in African children. SEAQUAMAT: 15% vs 22% in Asian adults. FEAST trial: fluid bolus harmful in severe malaria. Steroids harmful in cerebral malaria.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 17. Alcohol Withdrawal (ASAM 2020)
# =========================================================================


def build_alcohol_withdrawal_graph() -> dict[str, Any]:
    """ASAM 2020 Alcohol Withdrawal Management guideline graph."""
    src = "ASAM Alcohol Withdrawal Management 2020"
    doi = "10.1097/ADM.0000000000000668"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Alcohol Withdrawal Recognition & CIWA-Ar Scoring",
        description="Assess withdrawal severity using CIWA-Ar scale, identify seizure/DT risk factors",
        mandatory=["perform_ciwa_ar_assessment", "assess_vital_signs", "obtain_alcohol_use_history"],
        allowed=[
            "perform_ciwa_ar_assessment",
            "assess_vital_signs",
            "obtain_alcohol_use_history",
            "order_lab_cbc",
            "order_lab_bmp",
            "order_lab_magnesium",
            "order_lab_phosphate",
            "order_lab_liver_function",
            "order_lab_blood_alcohol_level",
            "order_lab_coagulation",
            "order_lab_glucose",
            "establish_iv_access",
        ],
        deadlines={
            "perform_ciwa_ar_assessment": 15,
            "assess_vital_signs": 10,
            "obtain_alcohol_use_history": 30,
        },
        source_guideline=src,
        source_section="Initial Assessment",
        source_quote="CIWA-Ar score guides management intensity: <10 mild, 10-18 moderate, >18 severe withdrawal. Assess for prior seizures, prior DT, comorbidities",
        conditional_next={
            "state.ciwa_score >= 20": "severe_withdrawal_bundle",
            "state.ciwa_score >= 10": "moderate_withdrawal_bundle",
            "state.ciwa_score < 10": "mild_withdrawal_monitoring",
        },
    )

    nodes["mild_withdrawal_monitoring"] = _node(
        node_id="mild_withdrawal_monitoring",
        node_type="plan",
        name="Mild Withdrawal (CIWA-Ar <10)",
        description="Supportive care, symptom-triggered benzodiazepine protocol, serial CIWA-Ar q4-8h",
        precondition="state.ciwa_score < 10",
        mandatory=[
            "initiate_symptom_triggered_protocol",
            "give_thiamine_before_glucose",
            "give_folate_supplementation",
        ],
        allowed=[
            "initiate_symptom_triggered_protocol",
            "give_thiamine_before_glucose",
            "give_folate_supplementation",
            "give_iv_fluids_maintenance",
            "correct_electrolyte_abnormalities",
            "reassess_ciwa_q4h",
            "order_lab_magnesium",
            "order_lab_bmp",
        ],
        deadlines={
            "give_thiamine_before_glucose": 60,
            "initiate_symptom_triggered_protocol": 60,
        },
        required_prior={"give_folate_supplementation": "obtain_alcohol_use_history"},
        source_guideline=src,
        source_section="Recommendation 1: Mild Withdrawal",
        source_quote="Symptom-triggered therapy is preferred over fixed-dose regimens; associated with less benzodiazepine use and shorter treatment duration (Saitz et al.)",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["moderate_withdrawal_bundle"] = _node(
        node_id="moderate_withdrawal_bundle",
        node_type="plan",
        name="Moderate Withdrawal (CIWA-Ar 10-18)",
        description="Scheduled benzodiazepines with symptom-triggered supplemental dosing, seizure prophylaxis",
        precondition="state.ciwa_score >= 10 and state.ciwa_score < 20",
        mandatory=[
            "give_benzodiazepine_chlordiazepoxide",
            "give_thiamine_before_glucose",
            "reassess_ciwa_q2h",
        ],
        allowed=[
            "give_benzodiazepine_chlordiazepoxide",
            "give_thiamine_before_glucose",
            "reassess_ciwa_q2h",
            "give_folate_supplementation",
            "give_iv_fluids_maintenance",
            "correct_electrolyte_abnormalities",
            "give_magnesium_supplementation",
            "give_multivitamin",
            "order_lab_bmp",
            "order_lab_magnesium",
        ],
        forbidden=["give_beta_blocker_monotherapy", "give_alcohol_to_prevent_withdrawal"],
        deadlines={
            "give_benzodiazepine_chlordiazepoxide": 30,
            "give_thiamine_before_glucose": 60,
            "reassess_ciwa_q2h": 120,
        },
        source_guideline=src,
        source_section="Recommendation 2: Moderate Withdrawal",
        source_quote="Benzodiazepines are the first-line treatment for alcohol withdrawal (strong recommendation, high quality evidence). Long-acting agents preferred (chlordiazepoxide, diazepam)",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["severe_withdrawal_bundle"] = _node(
        node_id="severe_withdrawal_bundle",
        node_type="plan",
        name="Severe Withdrawal / Delirium Tremens (CIWA-Ar ≥20)",
        description="High-dose benzodiazepines, ICU monitoring, seizure management, phenobarbital if refractory",
        precondition="state.ciwa_score >= 20",
        mandatory=[
            "give_iv_diazepam_loading",
            "give_thiamine_iv_500mg",
            "reassess_ciwa_q1h",
            "continuous_cardiac_monitoring",
        ],
        allowed=[
            "give_iv_diazepam_loading",
            "give_thiamine_iv_500mg",
            "reassess_ciwa_q1h",
            "continuous_cardiac_monitoring",
            "give_phenobarbital_if_refractory",
            "give_propofol_if_refractory_dt",
            "give_dexmedetomidine_adjunct",
            "give_iv_fluids_resuscitation",
            "correct_electrolyte_abnormalities",
            "order_lab_blood_gas",
            "order_lab_bmp_q6h",
            "order_imaging_ct_head_if_altered",
        ],
        forbidden=[
            "give_alcohol_to_prevent_withdrawal",
            "give_beta_blocker_monotherapy",
            "give_haloperidol_without_benzodiazepine",
        ],
        deadlines={
            "give_iv_diazepam_loading": 15,
            "give_thiamine_iv_500mg": 30,
            "continuous_cardiac_monitoring": 15,
        },
        conditional_rules=[
            {
                "rule_id": "AWS-SEIZURE",
                "condition": "state.seizure_activity == True",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["give_iv_diazepam_loading"],
                    "deadline_minutes": 5,
                },
                "severity": "CRITICAL",
                "description": "Withdrawal seizures require immediate IV benzodiazepine; recurrent seizures suggest progression to DT",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 3-4: Severe Withdrawal & DT",
        source_quote="Severe withdrawal (CIWA-Ar ≥20) requires ICU-level care with IV benzodiazepines. Phenobarbital is recommended for benzodiazepine-resistant withdrawal. Avoid haloperidol monotherapy (lowers seizure threshold)",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["monitoring_reassessment"] = _node(
        node_id="monitoring_reassessment",
        node_type="enquiry",
        name="Monitoring & CIWA-Ar Reassessment",
        description="Serial CIWA-Ar scoring, vital signs, electrolyte monitoring, assess for complications",
        mandatory=["reassess_ciwa_serial", "monitor_vital_signs"],
        allowed=[
            "reassess_ciwa_serial",
            "monitor_vital_signs",
            "order_lab_bmp",
            "order_lab_magnesium",
            "assess_mental_status",
            "monitor_fluid_balance",
            "adjust_benzodiazepine_dose",
        ],
        deadlines={"reassess_ciwa_serial": 240, "monitor_vital_signs": 60},
        source_guideline=src,
        source_section="Monitoring",
        source_quote="Serial CIWA-Ar assessments guide titration. Most withdrawal symptoms peak 24-72h after last drink; DT risk greatest at 48-96h",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Relapse Prevention",
        description="Assess stability for discharge, initiate relapse prevention pharmacotherapy",
        mandatory=["assess_discharge_readiness"],
        allowed=[
            "assess_discharge_readiness",
            "initiate_naltrexone_or_acamprosate",
            "refer_addiction_medicine",
            "provide_withdrawal_education",
            "arrange_outpatient_followup",
        ],
        source_guideline=src,
        source_section="Disposition & Relapse Prevention",
        source_quote="Pharmacotherapy for relapse prevention (naltrexone, acamprosate) should be initiated before or at discharge. Referral to addiction treatment is recommended",
    )

    return {
        "graph_id": "asam_alcohol_withdrawal_2020",
        "guideline_name": "ASAM 2020 Clinical Practice Guideline on Alcohol Withdrawal Management",
        "version": "2020.1",
        "metadata": {
            "source": "ASAM Clinical Practice Guideline on Alcohol Withdrawal Management 2020",
            "doi": doi,
            "journal": "Journal of Addiction Medicine",
            "recommendation_system": "GRADE",
            "description": "Evidence-based guideline for alcohol withdrawal management using CIWA-Ar scoring, symptom-triggered benzodiazepine therapy, and prevention of seizures and delirium tremens",
            "key_evidence": "Symptom-triggered therapy reduces benzodiazepine use and treatment duration vs fixed-dose. Phenobarbital is effective for benzodiazepine-resistant withdrawal. DT mortality reduced from 35% to <5% with early aggressive treatment.",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 18. Tumor Lysis Syndrome (ASCO 2023)
# =========================================================================


def build_tls_graph() -> dict[str, Any]:
    """ASCO 2023 Tumor Lysis Syndrome guideline graph."""
    src = "ASCO Tumor Lysis Syndrome Guidelines 2023"
    doi = "10.1200/JCO.22.02592"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="TLS Risk Stratification (Cairo-Bishop Criteria)",
        description="Stratify TLS risk (low/intermediate/high) based on tumor type, burden, renal function, and baseline labs",
        mandatory=["assess_tls_risk_cairo_bishop", "order_lab_uric_acid", "order_lab_bmp"],
        allowed=[
            "assess_tls_risk_cairo_bishop",
            "order_lab_uric_acid",
            "order_lab_bmp",
            "order_lab_phosphate",
            "order_lab_calcium",
            "order_lab_potassium",
            "order_lab_ldh",
            "order_lab_cbc",
            "order_lab_creatinine",
            "assess_vital_signs",
            "establish_iv_access",
        ],
        deadlines={
            "assess_tls_risk_cairo_bishop": 30,
            "order_lab_uric_acid": 30,
            "order_lab_bmp": 30,
        },
        source_guideline=src,
        source_section="Risk Stratification",
        source_quote="Cairo-Bishop criteria: laboratory TLS = ≥2 of: uric acid ≥8, potassium ≥6, phosphate ≥4.5 (mg/dL), calcium ≤7, within 3 days before or 7 days after chemotherapy",
        conditional_next={
            "state.tls_risk == 'high'": "high_risk_prophylaxis",
            "state.tls_risk == 'intermediate'": "intermediate_risk_prophylaxis",
            "state.tls_risk == 'low'": "low_risk_monitoring",
        },
    )

    nodes["low_risk_monitoring"] = _node(
        node_id="low_risk_monitoring",
        node_type="plan",
        name="Low-Risk TLS Monitoring",
        description="Adequate hydration, allopurinol prophylaxis, labs q12-24h",
        precondition="state.tls_risk == 'low'",
        mandatory=[
            "initiate_iv_hydration_2L_m2_day",
            "give_allopurinol_prophylaxis",
        ],
        allowed=[
            "initiate_iv_hydration_2L_m2_day",
            "give_allopurinol_prophylaxis",
            "order_lab_bmp_q24h",
            "order_lab_uric_acid_q24h",
            "monitor_urine_output",
            "monitor_fluid_balance",
        ],
        deadlines={
            "initiate_iv_hydration_2L_m2_day": 120,
            "give_allopurinol_prophylaxis": 120,
        },
        source_guideline=src,
        source_section="Recommendation 1: Low-Risk Management",
        source_quote="Low-risk patients: oral hydration and allopurinol prophylaxis with monitoring q12-24h",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["intermediate_risk_prophylaxis"] = _node(
        node_id="intermediate_risk_prophylaxis",
        node_type="plan",
        name="Intermediate-Risk TLS Prophylaxis",
        description="Aggressive IV hydration 3L/m2/day, allopurinol, serial labs q8-12h",
        precondition="state.tls_risk == 'intermediate'",
        mandatory=[
            "initiate_iv_hydration_3L_m2_day",
            "give_allopurinol_prophylaxis",
            "order_lab_bmp_q8h",
            "order_lab_uric_acid_q8h",
        ],
        allowed=[
            "initiate_iv_hydration_3L_m2_day",
            "give_allopurinol_prophylaxis",
            "order_lab_bmp_q8h",
            "order_lab_uric_acid_q8h",
            "monitor_urine_output_hourly",
            "order_lab_phosphate_q8h",
            "give_rasburicase_if_uric_acid_rising",
            "monitor_fluid_balance",
            "order_lab_calcium_q8h",
        ],
        forbidden=["give_rasburicase_with_g6pd_deficiency"],
        deadlines={
            "initiate_iv_hydration_3L_m2_day": 60,
            "give_allopurinol_prophylaxis": 60,
            "order_lab_bmp_q8h": 480,
        },
        source_guideline=src,
        source_section="Recommendation 2: Intermediate-Risk",
        source_quote="Intermediate-risk: aggressive IV hydration (3 L/m2/day), allopurinol prophylaxis, labs q8-12h. Consider rasburicase if uric acid rises despite allopurinol",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["high_risk_prophylaxis"] = _node(
        node_id="high_risk_prophylaxis",
        node_type="plan",
        name="High-Risk TLS Prophylaxis & Treatment",
        description="Rasburicase, aggressive hydration 3L/m2/day, electrolyte management q6h, ICU monitoring",
        precondition="state.tls_risk == 'high'",
        mandatory=[
            "give_rasburicase_0_2mg_kg",
            "initiate_iv_hydration_3L_m2_day",
            "order_lab_bmp_q6h",
            "order_lab_uric_acid_q6h",
            "continuous_cardiac_monitoring",
        ],
        allowed=[
            "give_rasburicase_0_2mg_kg",
            "initiate_iv_hydration_3L_m2_day",
            "order_lab_bmp_q6h",
            "order_lab_uric_acid_q6h",
            "continuous_cardiac_monitoring",
            "monitor_urine_output_hourly",
            "give_calcium_gluconate_if_symptomatic",
            "give_kayexalate_for_hyperkalemia",
            "give_insulin_dextrose_for_hyperkalemia",
            "give_phosphate_binder",
            "consult_nephrology",
            "initiate_rrt_if_refractory",
        ],
        forbidden=[
            "give_rasburicase_with_g6pd_deficiency",
            "give_allopurinol_with_rasburicase",
            "alkalinize_urine",
        ],
        deadlines={
            "give_rasburicase_0_2mg_kg": 30,
            "initiate_iv_hydration_3L_m2_day": 60,
            "continuous_cardiac_monitoring": 30,
        },
        conditional_rules=[
            {
                "rule_id": "TLS-HYPERKALEMIA-CRITICAL",
                "condition": "state.potassium_meq_l >= 6.5",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["give_calcium_gluconate_if_symptomatic", "give_insulin_dextrose_for_hyperkalemia"],
                    "deadline_minutes": 15,
                },
                "severity": "CRITICAL",
                "description": "K+ ≥6.5 mEq/L: cardiac arrest risk; immediate calcium gluconate for membrane stabilization + insulin/dextrose for intracellular shift",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 3-4: High-Risk / Established TLS",
        source_quote="Rasburicase (0.2 mg/kg IV) is recommended for high-risk patients and established TLS (strong recommendation). Do NOT use with G6PD deficiency (hemolytic anemia). Do NOT alkalinize urine (promotes calcium phosphate precipitation)",
        rec_class="I",
        evidence="A",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["monitoring_reassessment"] = _node(
        node_id="monitoring_reassessment",
        node_type="enquiry",
        name="Serial Monitoring & Electrolyte Correction",
        description="Monitor labs q6-8h, manage electrolyte derangements, assess renal function",
        mandatory=["monitor_labs_serial", "assess_renal_function"],
        allowed=[
            "monitor_labs_serial",
            "assess_renal_function",
            "order_lab_bmp",
            "order_lab_uric_acid",
            "order_lab_phosphate",
            "monitor_urine_output",
            "adjust_hydration_rate",
            "consult_nephrology_for_rrt",
        ],
        deadlines={"monitor_labs_serial": 480, "assess_renal_function": 360},
        source_guideline=src,
        source_section="Monitoring",
        source_quote="Serial metabolic panels q6-8h during high-risk period (typically 24-72h post-chemotherapy). Renal replacement therapy for refractory hyperkalemia, hyperphosphatemia, or oliguric renal failure",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Follow-Up",
        description="Step down monitoring, transition to oral hydration, plan subsequent chemotherapy cycles",
        mandatory=["assess_metabolic_stability"],
        allowed=[
            "assess_metabolic_stability",
            "transition_to_oral_hydration",
            "resume_allopurinol_maintenance",
            "plan_tls_prevention_next_cycle",
            "arrange_lab_follow_up",
        ],
        source_guideline=src,
        source_section="Disposition",
        source_quote="Labs should normalize within 3-7 days. Continue TLS prophylaxis for subsequent cycles if high-risk persists",
    )

    return {
        "graph_id": "asco_tls_2023",
        "guideline_name": "ASCO 2023 Guidelines on Tumor Lysis Syndrome Prevention and Treatment",
        "version": "2023.1",
        "metadata": {
            "source": "ASCO TLS Clinical Practice Guidelines 2023",
            "doi": doi,
            "journal": "Journal of Clinical Oncology",
            "recommendation_system": "GRADE",
            "description": "Evidence-based guideline for tumor lysis syndrome risk stratification, prophylaxis, and treatment emphasizing rasburicase for high-risk and aggressive hydration",
            "key_evidence": "Rasburicase reduces uric acid faster than allopurinol (4h vs 24-48h). Cairo-Bishop grading system standardizes TLS definition. Urine alkalinization no longer recommended (promotes calcium phosphate precipitation).",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 19. Sickle Cell Acute Chest Syndrome (ASH 2020)
# =========================================================================


def build_sickle_cell_acs_graph() -> dict[str, Any]:
    """ASH 2020 Sickle Cell Acute Chest Syndrome guideline graph."""
    src = "ASH Sickle Cell Disease Guidelines 2020"
    doi = "10.1182/bloodadvances.2019001999"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Acute Chest Syndrome Recognition",
        description="New pulmonary infiltrate + respiratory symptoms in SCD patient; assess severity and O2 status",
        mandatory=["assess_respiratory_status", "order_imaging_chest_xray", "assess_vital_signs"],
        allowed=[
            "assess_respiratory_status",
            "order_imaging_chest_xray",
            "assess_vital_signs",
            "order_lab_cbc_with_retic",
            "order_lab_bmp",
            "order_lab_blood_gas",
            "order_lab_blood_culture",
            "order_lab_type_and_screen",
            "order_lab_hemoglobin_s_level",
            "establish_iv_access",
            "order_lab_lactate",
        ],
        deadlines={
            "assess_respiratory_status": 15,
            "order_imaging_chest_xray": 30,
            "assess_vital_signs": 10,
        },
        source_guideline=src,
        source_section="Diagnosis of ACS",
        source_quote="ACS defined as new pulmonary infiltrate on CXR involving at least one complete lung segment + one of: chest pain, temperature >38.5C, tachypnea, wheezing, cough, or new-onset hypoxia",
        conditional_next={
            "state.acs_severity == 'severe'": "severe_acs_bundle",
            "state.acs_severity == 'mild_moderate'": "standard_acs_bundle",
        },
    )

    nodes["standard_acs_bundle"] = _node(
        node_id="standard_acs_bundle",
        node_type="plan",
        name="Standard ACS Management",
        description="Supplemental O2, broad-spectrum antibiotics, incentive spirometry, pain management, VTE prophylaxis",
        precondition="state.acs_severity == 'mild_moderate'",
        mandatory=[
            "give_supplemental_oxygen_target_spo2_95",
            "give_antibiotics_cephalosporin_plus_macrolide",
            "initiate_incentive_spirometry_q2h",
            "give_pain_management_avoid_oversedation",
        ],
        allowed=[
            "give_supplemental_oxygen_target_spo2_95",
            "give_antibiotics_cephalosporin_plus_macrolide",
            "initiate_incentive_spirometry_q2h",
            "give_pain_management_avoid_oversedation",
            "give_vte_prophylaxis",
            "give_iv_fluids_maintenance_cautious",
            "order_lab_cbc_q12h",
            "order_lab_hemoglobin_s_level",
            "transfuse_simple_if_hb_below_7",
            "monitor_respiratory_status_q4h",
        ],
        forbidden=[
            "give_aggressive_iv_fluids",
            "give_meperidine",
        ],
        deadlines={
            "give_supplemental_oxygen_target_spo2_95": 15,
            "give_antibiotics_cephalosporin_plus_macrolide": 60,
            "initiate_incentive_spirometry_q2h": 60,
            "give_pain_management_avoid_oversedation": 30,
        },
        source_guideline=src,
        source_section="Recommendation 1-3: ACS Standard Management",
        source_quote="Empiric antibiotics covering atypical organisms (cephalosporin + macrolide). Incentive spirometry q2h while awake reduces ACS progression. Avoid meperidine (seizure risk in SCD). Cautious fluids (avoid pulmonary edema)",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["severe_acs_bundle"] = _node(
        node_id="severe_acs_bundle",
        node_type="plan",
        name="Severe ACS: Exchange Transfusion",
        description="Exchange transfusion to reduce HbS <30%, respiratory support, antibiotics, ICU monitoring",
        precondition="state.acs_severity == 'severe'",
        mandatory=[
            "initiate_exchange_transfusion",
            "give_supplemental_oxygen_or_hfnc",
            "give_antibiotics_cephalosporin_plus_macrolide",
            "continuous_pulse_oximetry",
        ],
        allowed=[
            "initiate_exchange_transfusion",
            "give_supplemental_oxygen_or_hfnc",
            "give_antibiotics_cephalosporin_plus_macrolide",
            "continuous_pulse_oximetry",
            "give_pain_management_avoid_oversedation",
            "give_vte_prophylaxis",
            "order_lab_hemoglobin_s_level_post_transfusion",
            "order_lab_blood_gas",
            "initiate_incentive_spirometry_q2h",
            "consult_hematology",
            "order_lab_cbc_q8h",
        ],
        forbidden=[
            "give_aggressive_iv_fluids",
            "give_meperidine",
            "simple_transfusion_if_hb_above_10",
        ],
        deadlines={
            "initiate_exchange_transfusion": 120,
            "give_supplemental_oxygen_or_hfnc": 15,
            "give_antibiotics_cephalosporin_plus_macrolide": 60,
            "continuous_pulse_oximetry": 15,
        },
        conditional_rules=[
            {
                "rule_id": "ACS-RESP-FAILURE",
                "condition": "state.spo2 < 90 or state.pao2 < 60",
                "effect": {
                    "type": "REQUIRED",
                    "actions": ["initiate_exchange_transfusion"],
                    "deadline_minutes": 60,
                },
                "severity": "CRITICAL",
                "description": "Severe hypoxemia (SpO2<90% or PaO2<60) in ACS warrants urgent exchange transfusion to reduce HbS to <30%",
            },
        ],
        source_guideline=src,
        source_section="Recommendation 4-5: Severe ACS / Exchange Transfusion",
        source_quote="Exchange transfusion is recommended for severe ACS (PaO2 <60, multilobar disease, rapid deterioration). Target HbS <30% post-exchange. Simple transfusion if Hb <7; avoid if Hb >10 (hyperviscosity risk)",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring_reassessment"],
    )

    nodes["monitoring_reassessment"] = _node(
        node_id="monitoring_reassessment",
        node_type="enquiry",
        name="Respiratory Monitoring & HbS Trending",
        description="Serial respiratory assessments, HbS levels, CXR follow-up, watch for multi-organ failure",
        mandatory=["monitor_respiratory_status_serial", "order_lab_cbc_serial"],
        allowed=[
            "monitor_respiratory_status_serial",
            "order_lab_cbc_serial",
            "order_lab_hemoglobin_s_level",
            "order_imaging_chest_xray_followup",
            "order_lab_blood_gas",
            "assess_pain_control",
            "continue_incentive_spirometry",
        ],
        deadlines={"monitor_respiratory_status_serial": 240, "order_lab_cbc_serial": 480},
        source_guideline=src,
        source_section="Monitoring",
        source_quote="Monitor respiratory status q4h, repeat CXR if worsening. ACS can progress rapidly to multi-organ failure. Ensure HbS trending toward <30% after exchange",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Hydroxyurea Initiation",
        description="Assess for discharge, initiate hydroxyurea for secondary prevention, hematology follow-up",
        mandatory=["assess_discharge_readiness"],
        allowed=[
            "assess_discharge_readiness",
            "initiate_hydroxyurea_if_not_on",
            "arrange_hematology_followup",
            "provide_acs_prevention_education",
            "arrange_pulmonary_followup",
        ],
        source_guideline=src,
        source_section="Discharge & Secondary Prevention",
        source_quote="Hydroxyurea reduces ACS recurrence by ~50% (MSH trial). All patients with ACS should be considered for chronic transfusion or hydroxyurea therapy",
    )

    return {
        "graph_id": "ash_sickle_cell_acs_2020",
        "guideline_name": "ASH 2020 Sickle Cell Disease Guidelines: Acute Chest Syndrome",
        "version": "2020.1",
        "metadata": {
            "source": "ASH Sickle Cell Disease Evidence-Based Guidelines 2020",
            "doi": doi,
            "journal": "Blood Advances",
            "recommendation_system": "GRADE",
            "description": "Evidence-based management of acute chest syndrome in sickle cell disease including exchange transfusion, antibiotic therapy, and respiratory support",
            "key_evidence": "Exchange transfusion reduces HbS to <30% and improves oxygenation within hours. STOP trial: chronic transfusion reduces stroke and ACS. Incentive spirometry prevents ACS progression. Meperidine contraindicated (normeperidine accumulation).",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# 20. Variceal Hemorrhage (Baveno VII 2022)
# =========================================================================


def build_variceal_hemorrhage_graph() -> dict[str, Any]:
    """Baveno VII 2022 Variceal Hemorrhage guideline graph."""
    src = "Baveno VII Consensus on Portal Hypertension 2022"
    doi = "10.1016/j.jhep.2022.10.003"

    nodes: dict[str, Any] = {}

    nodes["initial_resuscitation"] = _node(
        node_id="initial_resuscitation",
        node_type="decision",
        name="Initial Resuscitation & Stabilization",
        description="Airway protection, volume resuscitation (restrictive), target Hb 7-8 g/dL, assess hemodynamic stability",
        mandatory=[
            "assess_airway_and_hemodynamics",
            "establish_large_bore_iv_access",
            "order_lab_cbc_coag_type_screen",
        ],
        allowed=[
            "assess_airway_and_hemodynamics",
            "establish_large_bore_iv_access",
            "order_lab_cbc_coag_type_screen",
            "give_crystalloid_resuscitation_restrictive",
            "transfuse_prbc_target_hb_7_to_8",
            "order_lab_bmp",
            "order_lab_liver_function",
            "order_lab_lactate",
            "intubate_for_airway_protection",
            "place_nasogastric_tube",
        ],
        deadlines={
            "assess_airway_and_hemodynamics": 5,
            "establish_large_bore_iv_access": 10,
            "order_lab_cbc_coag_type_screen": 15,
        },
        source_guideline=src,
        source_section="Initial Resuscitation",
        source_quote="Restrictive transfusion strategy (target Hb 7-8 g/dL) is recommended. Over-transfusion increases portal pressure and rebleeding risk. Airway protection before endoscopy if massive hemorrhage or encephalopathy",
        next_nodes=["pharmacologic_therapy"],
    )

    nodes["pharmacologic_therapy"] = _node(
        node_id="pharmacologic_therapy",
        node_type="plan",
        name="Vasoactive Drug + Antibiotic Prophylaxis",
        description="Start octreotide/terlipressin BEFORE endoscopy, IV ceftriaxone for SBP prophylaxis",
        mandatory=[
            "give_vasoactive_octreotide_or_terlipressin",
            "give_ceftriaxone_1g_iv_prophylaxis",
        ],
        allowed=[
            "give_vasoactive_octreotide_or_terlipressin",
            "give_ceftriaxone_1g_iv_prophylaxis",
            "give_ppi_iv_if_uncertain_source",
            "correct_coagulopathy_if_inr_above_2_5",
            "monitor_hemodynamics",
            "order_lab_cbc_q6h",
        ],
        forbidden=[
            "give_norfloxacin_in_high_risk",
            "delay_vasoactive_for_endoscopy",
        ],
        deadlines={
            "give_vasoactive_octreotide_or_terlipressin": 30,
            "give_ceftriaxone_1g_iv_prophylaxis": 60,
        },
        source_guideline=src,
        source_section="Recommendation 1-2: Pharmacologic Therapy",
        source_quote="Vasoactive drugs (terlipressin or octreotide) should be started as soon as variceal hemorrhage is suspected, BEFORE endoscopy. Short-term antibiotic prophylaxis (ceftriaxone 1g/day IV) is recommended for all cirrhotic patients with GI bleeding",
        rec_class="I",
        evidence="A",
        next_nodes=["emergent_endoscopy"],
    )

    nodes["emergent_endoscopy"] = _node(
        node_id="emergent_endoscopy",
        node_type="plan",
        name="Emergent EGD Within 12 Hours",
        description="Upper endoscopy with band ligation (preferred) or sclerotherapy within 12h of presentation",
        mandatory=[
            "perform_egd_within_12h",
            "perform_band_ligation_if_esophageal",
        ],
        allowed=[
            "perform_egd_within_12h",
            "perform_band_ligation_if_esophageal",
            "perform_cyanoanonymous-orgate_if_gastric",
            "place_sengstaken_blakemore_if_uncontrolled",
            "consult_gi",
            "continue_vasoactive_therapy",
        ],
        forbidden=[
            "delay_endoscopy_beyond_12h",
            "perform_sclerotherapy_over_banding",
        ],
        deadlines={
            "perform_egd_within_12h": 720,
            "perform_band_ligation_if_esophageal": 720,
        },
        required_prior={"perform_band_ligation_if_esophageal": "perform_egd_within_12h"},
        source_guideline=src,
        source_section="Recommendation 3: Endoscopic Therapy",
        source_quote="EGD should be performed within 12h of presentation. Endoscopic band ligation (EBL) is preferred over sclerotherapy for esophageal varices. Cyanoanonymous-orgate injection for gastric varices",
        rec_class="I",
        evidence="A",
        next_nodes=["post_endoscopy_assessment"],
    )

    nodes["post_endoscopy_assessment"] = _node(
        node_id="post_endoscopy_assessment",
        node_type="decision",
        name="Post-Endoscopy Assessment & Rebleeding Risk",
        description="Assess for rebleeding risk, TIPS candidacy (Child-Pugh B with active bleeding or C ≤13)",
        mandatory=["assess_rebleeding_risk", "continue_vasoactive_3_to_5_days"],
        allowed=[
            "assess_rebleeding_risk",
            "continue_vasoactive_3_to_5_days",
            "assess_tips_candidacy",
            "perform_preemptive_tips_if_high_risk",
            "monitor_hemodynamics",
            "order_lab_cbc_q8h",
            "initiate_lactulose_for_encephalopathy",
        ],
        deadlines={
            "assess_rebleeding_risk": 120,
        },
        conditional_next={
            "state.rebleeding == True": "rescue_tips",
            "state.rebleeding == False": "monitoring",
        },
        source_guideline=src,
        source_section="Recommendation 4: Post-Endoscopy & TIPS",
        source_quote="Preemptive TIPS (within 72h, ideally 24h) is recommended for high-risk patients (Child-Pugh C 10-13 or B with active bleeding at EGD). Continue vasoactive drugs for 3-5 days",
        next_nodes=["monitoring"],
    )

    nodes["rescue_tips"] = _node(
        node_id="rescue_tips",
        node_type="plan",
        name="Rescue TIPS for Rebleeding",
        description="TIPS placement for rebleeding despite endoscopic + pharmacologic therapy",
        precondition="state.rebleeding == True",
        mandatory=[
            "perform_tips_procedure",
            "continue_hemodynamic_support",
        ],
        allowed=[
            "perform_tips_procedure",
            "continue_hemodynamic_support",
            "transfuse_as_needed",
            "place_sengstaken_blakemore_bridge_to_tips",
            "consult_interventional_radiology",
        ],
        deadlines={
            "perform_tips_procedure": 360,
        },
        source_guideline=src,
        source_section="Recommendation 5: Rescue TIPS",
        source_quote="TIPS is the rescue therapy of choice for refractory variceal bleeding. Balloon tamponade or self-expandable metal stent can be used as a bridge to TIPS (max 24h)",
        rec_class="I",
        evidence="B",
        next_nodes=["monitoring"],
    )

    nodes["monitoring"] = _node(
        node_id="monitoring",
        node_type="enquiry",
        name="Monitoring & Secondary Prophylaxis Planning",
        description="Serial hemodynamics, Hb trending, NSBB initiation for secondary prophylaxis",
        mandatory=["monitor_hemodynamics_serial", "assess_for_secondary_prophylaxis"],
        allowed=[
            "monitor_hemodynamics_serial",
            "assess_for_secondary_prophylaxis",
            "initiate_nsbb_carvedilol_or_propranolol",
            "schedule_repeat_egd_for_banding",
            "order_lab_cbc",
            "monitor_renal_function",
        ],
        deadlines={"monitor_hemodynamics_serial": 360},
        source_guideline=src,
        source_section="Secondary Prophylaxis",
        source_quote="Combination of NSBB (carvedilol preferred) + EBL is recommended for secondary prophylaxis. NSBB reduces portal pressure and rebleeding risk by ~40%",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Long-term Management",
        description="Discharge planning, NSBB + EBL program, assess for liver transplant if decompensated",
        mandatory=["assess_discharge_readiness"],
        allowed=[
            "assess_discharge_readiness",
            "initiate_nsbb_secondary_prophylaxis",
            "schedule_egd_surveillance",
            "refer_transplant_evaluation",
            "provide_alcohol_cessation_counseling",
        ],
        source_guideline=src,
        source_section="Disposition",
        source_quote="All patients with variceal bleeding should receive secondary prophylaxis (NSBB + EBL). Consider liver transplant evaluation for decompensated cirrhosis",
    )

    return {
        "graph_id": "baveno_vii_varices_2022",
        "guideline_name": "Baveno VII Consensus on Portal Hypertension: Variceal Hemorrhage 2022",
        "version": "2022.1",
        "metadata": {
            "source": "Baveno VII Consensus Workshop on Portal Hypertension 2022",
            "doi": doi,
            "journal": "Journal of Hepatology",
            "recommendation_system": "GRADE",
            "description": "Evidence-based consensus on variceal hemorrhage management including vasoactive therapy, endoscopic band ligation, TIPS, and secondary prophylaxis",
            "key_evidence": "Restrictive transfusion (Hb 7-8) reduces mortality vs liberal (Villanueva et al., NEJM 2013). Preemptive TIPS reduces treatment failure and mortality in high-risk patients (Garcia-Pagan et al., NEJM 2010). Ceftriaxone superior to norfloxacin for SBP prophylaxis.",
        },
        "entry_node": "initial_resuscitation",
        "nodes": nodes,
    }


# =========================================================================
# 21. Damage Control / Massive Transfusion (EAST 2017)
# =========================================================================


def build_damage_control_mtp_graph() -> dict[str, Any]:
    """EAST 2017 Damage Control / Massive Transfusion Protocol guideline graph."""
    src = "EAST Damage Control Resuscitation 2017"
    doi = "10.1097/TA.0000000000001333"

    nodes: dict[str, Any] = {}

    nodes["initial_assessment"] = _node(
        node_id="initial_assessment",
        node_type="decision",
        name="Hemorrhagic Shock Recognition & MTP Activation",
        description="Identify massive hemorrhage (ABC score ≥2, shock index >1), activate MTP, permissive hypotension",
        mandatory=["assess_hemorrhagic_shock", "activate_massive_transfusion_protocol", "assess_vital_signs"],
        allowed=[
            "assess_hemorrhagic_shock",
            "activate_massive_transfusion_protocol",
            "assess_vital_signs",
            "establish_large_bore_iv_access",
            "order_lab_type_and_crossmatch",
            "order_lab_cbc",
            "order_lab_coagulation",
            "order_lab_blood_gas",
            "order_lab_lactate",
            "order_lab_fibrinogen",
            "order_lab_teg_or_rotem",
        ],
        deadlines={
            "assess_hemorrhagic_shock": 5,
            "activate_massive_transfusion_protocol": 10,
            "assess_vital_signs": 5,
        },
        source_guideline=src,
        source_section="MTP Activation Criteria",
        source_quote="Activate MTP when: ABC score ≥2, shock index >1.0, anticipated need for >10 units PRBC in 24h, or hemodynamic instability despite 2L crystalloid",
        next_nodes=["balanced_resuscitation"],
    )

    nodes["balanced_resuscitation"] = _node(
        node_id="balanced_resuscitation",
        node_type="plan",
        name="Balanced 1:1:1 Resuscitation + TXA",
        description="1:1:1 ratio PRBC:FFP:Platelets, TXA within 3h of injury, limit crystalloid, permissive hypotension",
        mandatory=[
            "transfuse_1_1_1_prbc_ffp_platelets",
            "give_txa_1g_within_3h",
            "target_permissive_hypotension_sbp_80_90",
        ],
        allowed=[
            "transfuse_1_1_1_prbc_ffp_platelets",
            "give_txa_1g_within_3h",
            "target_permissive_hypotension_sbp_80_90",
            "give_calcium_gluconate_for_citrate_toxicity",
            "give_cryoprecipitate_if_fibrinogen_below_150",
            "order_lab_teg_or_rotem_guided",
            "monitor_temperature_prevent_hypothermia",
            "order_lab_ionized_calcium",
            "order_lab_blood_gas_serial",
        ],
        forbidden=[
            "give_excessive_crystalloid_over_2L",
            "target_normal_sbp_in_uncontrolled_hemorrhage",
            "give_txa_after_3h_of_injury",
        ],
        deadlines={
            "transfuse_1_1_1_prbc_ffp_platelets": 15,
            "give_txa_1g_within_3h": 180,
            "target_permissive_hypotension_sbp_80_90": 10,
        },
        source_guideline=src,
        source_section="Recommendation 1-3: Balanced Resuscitation",
        source_quote="1:1:1 PRBC:FFP:Platelet ratio is recommended (PROPPR trial: reduced 24h mortality). TXA within 3h of injury reduces mortality (CRASH-2 trial). Permissive hypotension (SBP 80-90) until surgical hemorrhage control",
        rec_class="I",
        evidence="A",
        next_nodes=["hemorrhage_control"],
    )

    nodes["hemorrhage_control"] = _node(
        node_id="hemorrhage_control",
        node_type="decision",
        name="Hemorrhage Source Control",
        description="Damage control surgery vs IR embolization based on injury pattern, correct lethal triad",
        mandatory=["identify_hemorrhage_source", "plan_hemorrhage_control_procedure"],
        allowed=[
            "identify_hemorrhage_source",
            "plan_hemorrhage_control_procedure",
            "perform_damage_control_surgery",
            "perform_angioembolization",
            "apply_direct_pressure_or_tourniquet",
            "apply_pelvic_binder",
            "order_imaging_ct_trauma",
            "order_imaging_fast_ultrasound",
        ],
        deadlines={
            "identify_hemorrhage_source": 30,
            "plan_hemorrhage_control_procedure": 60,
        },
        conditional_next={
            "state.requires_surgery == True": "damage_control_surgery",
            "state.requires_surgery == False": "icu_resuscitation",
        },
        source_guideline=src,
        source_section="Recommendation 4: Source Control",
        source_quote="Damage control surgery: abbreviated operation to control hemorrhage and contamination, temporary closure, ICU resuscitation, then definitive repair (staged approach)",
        next_nodes=["icu_resuscitation"],
    )

    nodes["damage_control_surgery"] = _node(
        node_id="damage_control_surgery",
        node_type="plan",
        name="Damage Control Surgery (Abbreviated Laparotomy)",
        description="Hemorrhage control, contamination control, temporary abdominal closure, correct lethal triad in ICU",
        precondition="state.requires_surgery == True",
        mandatory=[
            "perform_damage_control_laparotomy",
            "control_hemorrhage_surgical",
            "apply_temporary_abdominal_closure",
        ],
        allowed=[
            "perform_damage_control_laparotomy",
            "control_hemorrhage_surgical",
            "apply_temporary_abdominal_closure",
            "pack_abdomen",
            "ligate_damaged_vessels",
            "resect_damaged_bowel_no_anastomosis",
            "continue_mtp_intraoperatively",
        ],
        forbidden=[
            "perform_definitive_repair_in_unstable_patient",
            "perform_bowel_anastomosis_in_dc_setting",
        ],
        deadlines={
            "perform_damage_control_laparotomy": 60,
        },
        source_guideline=src,
        source_section="Recommendation 5: Damage Control Surgery",
        source_quote="Damage control surgery is indicated for the lethal triad (hypothermia <35C, acidosis pH<7.2, coagulopathy). Goal: <60 min OR time. Pack, ligate, staple; NO definitive repair until physiologically normalized",
        rec_class="I",
        evidence="B",
        next_nodes=["icu_resuscitation"],
    )

    nodes["icu_resuscitation"] = _node(
        node_id="icu_resuscitation",
        node_type="plan",
        name="ICU Resuscitation & Lethal Triad Correction",
        description="Rewarm, correct acidosis and coagulopathy, goal-directed resuscitation, reassess for definitive repair",
        mandatory=[
            "rewarm_to_normothermia",
            "correct_coagulopathy_teg_guided",
            "monitor_lactate_clearance",
        ],
        allowed=[
            "rewarm_to_normothermia",
            "correct_coagulopathy_teg_guided",
            "monitor_lactate_clearance",
            "continue_balanced_transfusion",
            "give_calcium_supplementation",
            "order_lab_blood_gas_q2h",
            "order_lab_coagulation_q4h",
            "assess_abdominal_compartment_pressure",
            "plan_definitive_surgery_24_48h",
        ],
        deadlines={
            "rewarm_to_normothermia": 360,
            "correct_coagulopathy_teg_guided": 240,
            "monitor_lactate_clearance": 120,
        },
        source_guideline=src,
        source_section="Recommendation 6: ICU Resuscitation Phase",
        source_quote="ICU resuscitation targets: temp >36C, pH >7.25, INR <1.5, platelets >100K, fibrinogen >200, lactate clearance. Return to OR for definitive repair at 24-48h when physiologically stable",
        next_nodes=["disposition"],
    )

    nodes["disposition"] = _node(
        node_id="disposition",
        node_type="decision",
        name="Disposition & Definitive Repair Planning",
        description="Assess readiness for definitive surgery, MTP deactivation, step-down planning",
        mandatory=["assess_readiness_for_definitive_repair"],
        allowed=[
            "assess_readiness_for_definitive_repair",
            "deactivate_mtp",
            "plan_definitive_surgery",
            "continue_icu_monitoring",
            "assess_for_abdominal_compartment_syndrome",
        ],
        source_guideline=src,
        source_section="Disposition",
        source_quote="Definitive surgery at 24-48h when lethal triad corrected. Monitor for abdominal compartment syndrome (IAP >20 mmHg with organ dysfunction)",
    )

    return {
        "graph_id": "east_damage_control_mtp_2017",
        "guideline_name": "EAST 2017 Practice Management Guidelines: Damage Control Resuscitation",
        "version": "2017.1",
        "metadata": {
            "source": "EAST Damage Control Resuscitation Practice Management Guidelines 2017",
            "doi": doi,
            "journal": "Journal of Trauma and Acute Care Surgery",
            "recommendation_system": "GRADE",
            "description": "Evidence-based guidelines for damage control resuscitation including 1:1:1 balanced transfusion, TXA, permissive hypotension, and staged surgical repair",
            "key_evidence": "PROPPR trial: 1:1:1 ratio reduces 24h mortality (9.2% vs 14.6%) and improves hemostasis. CRASH-2 trial: TXA within 3h reduces mortality by 1.5%. Permissive hypotension improves survival in penetrating trauma (Bickell et al.).",
        },
        "entry_node": "initial_assessment",
        "nodes": nodes,
    }


# =========================================================================
# Registry & CLI
# =========================================================================

GRAPH_BUILDERS: dict[str, callable] = {
    "ards": build_ards_graph,
    "pediatric_sepsis": build_pediatric_sepsis_graph,
    "sah": build_sah_graph,
    "aortic_dissection": build_aortic_dissection_graph,
    "ich": build_ich_graph,
    "ruptured_aaa": build_ruptured_aaa_graph,
    "neonatal_resuscitation": build_neonatal_resuscitation_graph,
    "pediatric_traumatic_arrest": build_pediatric_traumatic_arrest_graph,
    "cardiogenic_shock": build_cardiogenic_shock_graph,
    "ttm_post_arrest": build_ttm_post_arrest_graph,
    "pleural_disease": build_pleural_disease_graph,
    "hypothermia": build_hypothermia_graph,
    "acute_limb_ischemia": build_acute_limb_ischemia_graph,
    "pediatric_dka": build_pediatric_dka_graph,
    "hyperkalemia": build_hyperkalemia_graph,
    "severe_malaria": build_severe_malaria_graph,
    # Score-17 batch
    "alcohol_withdrawal": build_alcohol_withdrawal_graph,
    "tls": build_tls_graph,
    "sickle_cell_acs": build_sickle_cell_acs_graph,
    "variceal_hemorrhage": build_variceal_hemorrhage_graph,
    "damage_control_mtp": build_damage_control_mtp_graph,
}


def validate_graph(graph: dict[str, Any]) -> list[str]:
    """Basic schema validation. Returns list of errors."""
    errors: list[str] = []
    if "graph_id" not in graph:
        errors.append("Missing graph_id")
    if "entry_node" not in graph:
        errors.append("Missing entry_node")
    if "nodes" not in graph or not graph["nodes"]:
        errors.append("Missing or empty nodes")
        return errors

    node_ids = set(graph["nodes"].keys())
    if graph["entry_node"] not in node_ids:
        errors.append(f"entry_node '{graph['entry_node']}' not in nodes")

    for nid, node in graph["nodes"].items():
        if nid != node.get("node_id"):
            errors.append(f"Node key '{nid}' != node_id '{node.get('node_id')}'")
        if node.get("node_type") not in ("decision", "plan", "action", "enquiry"):
            errors.append(f"Node '{nid}': invalid node_type '{node.get('node_type')}'")
        if not node.get("mandatory_actions"):
            errors.append(f"Node '{nid}': empty mandatory_actions")
        if not node.get("allowed_actions"):
            errors.append(f"Node '{nid}': empty allowed_actions")
        if not node.get("source_guideline"):
            errors.append(f"Node '{nid}': missing source_guideline")

        # forbidden ∩ allowed = ∅
        forbidden = set(node.get("forbidden_actions", []))
        allowed = set(node.get("allowed_actions", []))
        overlap = forbidden & allowed
        if overlap:
            errors.append(f"Node '{nid}': forbidden ∩ allowed = {overlap}")

        # mandatory ⊆ allowed
        mandatory = set(node.get("mandatory_actions", []))
        if not mandatory.issubset(allowed):
            errors.append(f"Node '{nid}': mandatory not subset of allowed: {mandatory - allowed}")

        # deadline keys ⊆ allowed
        deadline_keys = set(node.get("deadlines", {}).keys())
        if not deadline_keys.issubset(allowed):
            errors.append(f"Node '{nid}': deadline actions not in allowed: {deadline_keys - allowed}")

        # next_nodes / conditional_next targets exist
        for target in node.get("next_nodes", []):
            if target not in node_ids:
                errors.append(f"Node '{nid}': next_node '{target}' not found")
        for cond, target in node.get("conditional_next", {}).items():
            if target not in node_ids:
                errors.append(f"Node '{nid}': conditional_next target '{target}' not found")

    return errors


def write_graph(graph: dict[str, Any], output_dir: Path, dry_run: bool = False) -> Path:
    """Write graph to YAML file."""
    path = output_dir / f"{graph['graph_id']}.yaml"

    errors = validate_graph(graph)
    if errors:
        raise ValueError(f"Validation failed for {graph['graph_id']}:\n" + "\n".join(f"  - {e}" for e in errors))

    if dry_run:
        print(f"[DRY RUN] Would write {path}")
        node_count = len(graph["nodes"])
        actions = set()
        for n in graph["nodes"].values():
            actions.update(n.get("mandatory_actions", []))
        print(f"  Nodes: {node_count}, Unique mandatory actions: {len(actions)}")
        return path

    output_dir.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        yaml.dump(graph, f, default_flow_style=False, allow_unicode=True, sort_keys=False, width=120)

    print(f"Written: {path} ({len(graph['nodes'])} nodes)")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description="Phase 3: Generate expansion CPG YAML graphs")
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
            path = write_graph(graph, args.output_dir, dry_run=args.dry_run)
            print("  Validation: PASS")

    if total_errors:
        print(f"\n{total_errors} total validation errors!")
        raise SystemExit(1)
    else:
        print(f"\nAll {len(builders)} graphs validated and {'previewed' if args.dry_run else 'written'} successfully.")


if __name__ == "__main__":
    main()
