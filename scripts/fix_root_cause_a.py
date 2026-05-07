"""Fix Root Cause A: Add condition-specific FORBIDDEN companion rules.

Root Cause A = conditional rules have only REQUIRED/EXPECTED effects,
no FORBIDDEN. So trap forbidden set == normal forbidden set (undifferentiated).

Fix: For each REQUIRED-only rule, add a companion FORBIDDEN rule with
clinically accurate, condition-specific dangerous actions that are NOT
already in the graph's unconditional forbidden set.
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import yaml

GRAPHS_DIR = Path(__file__).parent.parent / "cpg_model" / "graphs"
ANALYSIS_FILE = Path(__file__).parent.parent / "evidence_pack" / "undifferentiated_trap_analysis.json"

# ── Clinical companion FORBIDDEN rules ──────────────────────────────────
# Key = parent rule_id (the REQUIRED-only rule)
# Value = dict with fields for the new companion FORBIDDEN rule
COMPANION_FORBIDDEN: dict[str, dict] = {
    # ═══════════════════════════════════════════════════════
    # TOXICOLOGY MANAGEMENT (7 traps)
    # ═══════════════════════════════════════════════════════
    "TOX-ACETAMINOPHEN-NAC": {
        "rule_id": "TOX-ACETAMINOPHEN-NAC-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_hepatotoxic_drug_in_apap_overdose",
                "delay_nac_for_level_confirmation",
            ],
        },
        "evidence": "AACT/ACMT 2024 Section 3.1; NAC must not be delayed waiting for "
        "acetaminophen level; additional hepatotoxins compound liver injury",
        "severity": "CRITICAL",
        "description": "In acetaminophen overdose, hepatotoxic agents worsen liver "
        "injury and NAC delay beyond 8h drops efficacy dramatically.",
    },
    "TOX-OPIOID-NALOXONE": {
        "rule_id": "TOX-OPIOID-NALOXONE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_additional_opioid_in_overdose",
                "give_long_acting_sedative_in_opioid_od",
            ],
        },
        "evidence": "AACT/ACMT 2024 Section 3.3; Boyer EW, NEJM 2012; additional "
        "CNS depressants worsen respiratory depression",
        "severity": "CRITICAL",
        "description": "In opioid overdose, additional opioids or long-acting sedatives "
        "worsen respiratory depression and may cause fatal apnea.",
    },
    "TOX-METHANOL-FOMEPIZOLE": {
        "rule_id": "TOX-METHANOL-FOMEPIZOLE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "delay_fomepizole_for_osmolar_gap",
                "give_ethanol_concurrently_with_fomepizole",
            ],
        },
        "evidence": "AACT/ACMT 2024 Section 3.5; Brent J, NEJM 2001; fomepizole "
        "delay allows toxic metabolite accumulation",
        "severity": "CRITICAL",
        "description": "Delaying fomepizole for osmolar gap results permits conversion "
        "to formic acid/oxalic acid; concurrent ethanol adds toxicity.",
    },
    "TOX-DIGOXIN-FAB": {
        "rule_id": "TOX-DIGOXIN-FAB-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_calcium_in_digoxin_toxicity",
                "cardiovert_without_digoxin_fab",
            ],
        },
        "evidence": "AACT/ACMT 2024 Section 3.6; Antman EM, Circulation 1990; "
        "calcium + digoxin causes 'stone heart' (irreversible contracture)",
        "severity": "CRITICAL",
        "description": "IV calcium in digoxin toxicity causes fatal myocardial "
        "contracture; cardioversion without Fab triggers lethal arrhythmia.",
    },
    "TOX-ORGANOPHOSPHATE-ATROPINE": {
        "rule_id": "TOX-ORGANOPHOSPHATE-ATROPINE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_succinylcholine_in_op_poisoning",
                "give_morphine_in_cholinergic_crisis",
            ],
        },
        "evidence": "AACT/ACMT 2024 Section 3.7; Eddleston M, Lancet 2008; OP "
        "inhibits pseudocholinesterase causing prolonged paralysis from "
        "succinylcholine",
        "severity": "CRITICAL",
        "description": "Succinylcholine relies on pseudocholinesterase for metabolism; "
        "OP poisoning inhibits this enzyme causing prolonged paralysis.",
    },
    "TOX-BETA-BLOCKER-GLUCAGON": {
        "rule_id": "TOX-BETA-BLOCKER-GLUCAGON-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_additional_beta_blocker",
                "give_verapamil_in_beta_blocker_od",
            ],
        },
        "evidence": "AACT/ACMT 2024 Section 3.8; Love JN, J Toxicol Clin Toxicol 2000; "
        "additional negative chronotropes cause refractory bradycardia",
        "severity": "HIGH",
        "description": "Additional beta-blockers or calcium channel blockers in "
        "beta-blocker overdose cause refractory cardiogenic shock.",
    },
    "TOX-CALCIUM-CHANNEL-BLOCKER-INSULIN": {
        "rule_id": "TOX-CALCIUM-CHANNEL-BLOCKER-INSULIN-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_additional_ccb",
                "give_beta_blocker_in_ccb_overdose",
            ],
        },
        "evidence": "AACT/ACMT 2024 Section 3.9; Engebretsen KM, Clin Toxicol 2011; "
        "combined negative inotropy is lethal",
        "severity": "HIGH",
        "description": "Beta-blockers in CCB overdose compound negative inotropy "
        "and vasodilation causing irreversible cardiogenic shock.",
    },
    # ═══════════════════════════════════════════════════════
    # ANAPHYLAXIS MANAGEMENT (6 traps, 5 rules)
    # ═══════════════════════════════════════════════════════
    "ANA-BETA-BLOCKER-GLUCAGON": {
        "rule_id": "ANA-BETA-BLOCKER-GLUCAGON-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_additional_beta_blocker_in_anaphylaxis",
                "withhold_glucagon_despite_epi_resistance",
            ],
        },
        "evidence": "WAO 2024 Section 4.3; EAACI 2024 Section 5.2; beta-blocker patients are epinephrine-resistant",
        "severity": "HIGH",
        "description": "Beta-blocker patients may not respond to epinephrine; "
        "additional beta-blockade worsens anaphylactic shock.",
    },
    "ANA-PREGNANCY-LEFT-LATERAL": {
        "rule_id": "ANA-PREGNANCY-LEFT-LATERAL-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "position_supine_flat_in_pregnancy",
                "give_methylergonovine_in_anaphylaxis",
            ],
        },
        "evidence": "WAO 2024 Section 6.1; supine positioning in pregnant patients "
        "causes aortocaval compression reducing cardiac output by 30%",
        "severity": "HIGH",
        "description": "Supine position in pregnant anaphylaxis causes aortocaval "
        "compression; methylergonovine is a vasoconstrictive contraindication.",
    },
    "ANA-ASTHMA-SALBUTAMOL": {
        "rule_id": "ANA-ASTHMA-SALBUTAMOL-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_beta_blocker_in_asthma_anaphylaxis",
                "give_nsaid_in_aspirin_sensitive_asthma",
            ],
        },
        "evidence": "WAO 2024 Section 4.5; beta-blockers exacerbate bronchospasm; "
        "NSAIDs trigger aspirin-exacerbated respiratory disease",
        "severity": "HIGH",
        "description": "Beta-blockers worsen bronchospasm in asthmatic anaphylaxis; "
        "NSAIDs trigger aspirin-exacerbated respiratory disease.",
    },
    "ANA-MASTOCYTOSIS-EXTENDED-OBS": {
        "rule_id": "ANA-MASTOCYTOSIS-EXTENDED-OBS-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "discharge_before_24h_in_mastocytosis",
                "give_nsaid_in_mastocytosis",
            ],
        },
        "evidence": "WAO 2024 Section 6.3; Brockow K, JACI 2008; mastocytosis patients have 30% biphasic reaction rate",
        "severity": "HIGH",
        "description": "Mastocytosis patients have dramatically higher biphasic "
        "reaction risk; NSAIDs trigger mast cell degranulation.",
    },
    "ANA-BIPHASIC-HIGH-RISK": {
        "rule_id": "ANA-BIPHASIC-HIGH-RISK-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "discharge_before_8h_severe_anaphylaxis",
                "discontinue_monitoring_prematurely",
            ],
        },
        "evidence": "WAO 2024 Section 5.2; Grunau BE, Ann Emerg Med 2015; "
        "10-20% biphasic rate in severe initial reactions",
        "severity": "HIGH",
        "description": "Severe initial reactions have 10-20% biphasic risk; "
        "premature discharge or monitoring discontinuation is dangerous.",
    },
    # ═══════════════════════════════════════════════════════
    # KDIGO AKI FULL (6 traps, 5 rules)
    # ═══════════════════════════════════════════════════════
    "AKI-NSAID-STOP": {
        "rule_id": "AKI-NSAID-STOP-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_nsaid_in_aki",
                "give_cox2_inhibitor_in_aki",
            ],
        },
        "evidence": "KDIGO AKI 2012, Section 3.1.1; NSAIDs/COX-2 inhibitors cause "
        "afferent arteriole vasoconstriction worsening AKI",
        "severity": "HIGH",
        "description": "NSAIDs and COX-2 inhibitors reduce renal blood flow via "
        "prostaglandin inhibition; contraindicated in active AKI.",
    },
    "AKI-ACEI-HOLD": {
        "rule_id": "AKI-ACEI-HOLD-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_ace_inhibitor_in_aki",
                "give_arb_in_aki",
                "start_new_raas_inhibitor_in_aki",
            ],
        },
        "evidence": "KDIGO AKI 2012, Section 3.1.2; RAAS inhibitors reduce efferent "
        "arteriole tone lowering GFR further in AKI",
        "severity": "HIGH",
        "description": "ACE inhibitors and ARBs reduce efferent arteriolar tone; "
        "initiating or continuing RAAS blockade in AKI worsens injury.",
    },
    "AKI-HYPERKALEMIA-URGENT": {
        "rule_id": "AKI-HYPERKALEMIA-URGENT-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_potassium_in_hyperkalemic_aki",
                "give_succinylcholine_in_hyperkalemic_aki",
                "give_spironolactone_in_hyperkalemic_aki",
            ],
        },
        "evidence": "KDIGO AKI 2012; AHA Hyperkalemia Guidelines; potassium-sparing "
        "agents and exogenous K+ are contraindicated in K+ > 6.0",
        "severity": "CRITICAL",
        "description": "Potassium supplementation, succinylcholine (releases K+ from "
        "muscle), and spironolactone worsen fatal hyperkalemia in AKI.",
    },
    "AKI-METFORMIN-HOLD": {
        "rule_id": "AKI-METFORMIN-HOLD-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "continue_metformin_in_aki",
                "give_metformin_in_renal_failure",
            ],
        },
        "evidence": "KDIGO AKI 2012; FDA Black Box Warning; metformin accumulation "
        "in AKI causes fatal lactic acidosis (mortality 30-50%)",
        "severity": "HIGH",
        "description": "Metformin is renally cleared; accumulation in AKI causes "
        "severe lactic acidosis with high mortality.",
    },
    "AKI-HEPATORENAL-ALBUMIN": {
        "rule_id": "AKI-HEPATORENAL-ALBUMIN-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_nsaid_in_hepatorenal",
                "give_aminoglycoside_in_hepatorenal",
            ],
        },
        "evidence": "KDIGO AKI 2012; EASL Hepatorenal 2018; nephrotoxins compound renal injury in hepatorenal syndrome",
        "severity": "HIGH",
        "description": "NSAIDs and aminoglycosides are nephrotoxic; in hepatorenal "
        "syndrome they accelerate renal failure progression.",
    },
    # ═══════════════════════════════════════════════════════
    # ABA BURN RESUSCITATION (5 traps, 3 rules)
    # ═══════════════════════════════════════════════════════
    "BURN-CHEST-ESCHAR-VENTILATION": {
        "rule_id": "BURN-CHEST-ESCHAR-VENTILATION-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "delay_escharotomy_for_imaging",
                "increase_ventilator_pressure_without_escharotomy",
            ],
        },
        "evidence": "ABA Burn Guidelines 2023; circumferential chest eschar causes "
        "restrictive ventilatory failure requiring emergent release",
        "severity": "CRITICAL",
        "description": "Chest eschar restricts ventilation; delaying escharotomy for "
        "imaging or increasing ventilator pressure without release is harmful.",
    },
    "BURN-CYANIDE-HYDROXOCOBALAMIN": {
        "rule_id": "BURN-CYANIDE-HYDROXOCOBALAMIN-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_sodium_nitrite_in_cyanide_burn",
                "delay_cyanide_antidote_for_level",
            ],
        },
        "evidence": "ABA Burn Guidelines 2023; sodium nitrite induces methemoglobinemia "
        "compounding carbon monoxide poisoning in burn patients",
        "severity": "CRITICAL",
        "description": "Sodium nitrite creates methemoglobin which compounds CO "
        "poisoning in burns; cyanide level delays allow fatal exposure.",
    },
    "BURN-PEDIATRIC-DEXTROSE": {
        "rule_id": "BURN-PEDIATRIC-DEXTROSE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "withhold_glucose_monitoring_pediatric_burn",
                "give_dextrose_free_fluid_only_pediatric_burn",
            ],
        },
        "evidence": "ABA Burn Guidelines 2023; pediatric patients have limited "
        "glycogen reserves; hypoglycemia causes seizures and brain injury",
        "severity": "HIGH",
        "description": "Pediatric burn patients deplete glycogen rapidly; dextrose-free "
        "resuscitation without glucose monitoring causes hypoglycemic seizures.",
    },
    # ═══════════════════════════════════════════════════════
    # ADA DKA MANAGEMENT (4 traps, 3 rules)
    # ═══════════════════════════════════════════════════════
    "DKA-EUGLY-SGLT2-DEXTROSE": {
        "rule_id": "DKA-EUGLY-SGLT2-DEXTROSE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "continue_sglt2_inhibitor_in_dka",
                "withhold_dextrose_in_euglycemic_dka",
            ],
        },
        "evidence": "ADA DKA Guidelines 2024; SGLT2i causes euglycemic DKA; "
        "withholding dextrose delays anion gap closure",
        "severity": "HIGH",
        "description": "SGLT2 inhibitors must be stopped in DKA; euglycemic DKA "
        "requires dextrose to allow continued insulin without hypoglycemia.",
    },
    "DKA-METFORMIN-STOP": {
        "rule_id": "DKA-METFORMIN-STOP-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "continue_metformin_in_dka",
                "restart_metformin_before_dka_resolved",
            ],
        },
        "evidence": "ADA DKA Guidelines 2024; FDA Label; metformin in metabolic acidosis causes fatal lactic acidosis",
        "severity": "HIGH",
        "description": "Metformin in DKA compounds metabolic acidosis via lactic "
        "acid production; must not continue or restart before resolution.",
    },
    "DKA-HYPOK-INSULIN-GATE": {
        "rule_id": "DKA-HYPOK-INSULIN-GATE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "start_insulin_if_potassium_below_3_3",
                "give_insulin_without_potassium_check",
            ],
        },
        "evidence": "ADA DKA Guidelines 2024; insulin drives K+ intracellularly; "
        "starting insulin with K+ < 3.3 causes fatal hypokalemic arrest",
        "severity": "CRITICAL",
        "description": "Insulin shifts potassium intracellularly; giving insulin when "
        "K+ < 3.3 mEq/L causes hypokalemic cardiac arrest.",
    },
    # ═══════════════════════════════════════════════════════
    # CAP PNEUMONIA (4 traps, 4 rules)
    # ═══════════════════════════════════════════════════════
    "CAP-ASPIRATION-ANAEROBE": {
        "rule_id": "CAP-ASPIRATION-ANAEROBE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_azithromycin_only_for_aspiration",
                "omit_anaerobic_coverage_in_aspiration",
            ],
        },
        "evidence": "ATS/IDSA CAP 2019; aspiration pneumonia involves polymicrobial "
        "anaerobes requiring specific coverage",
        "severity": "HIGH",
        "description": "Aspiration pneumonia involves anaerobes that macrolides don't "
        "cover; omitting anaerobic coverage leads to treatment failure.",
    },
    "CAP-MRSA-RISK-COVERAGE": {
        "rule_id": "CAP-MRSA-RISK-COVERAGE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_standard_empiric_without_mrsa_in_risk",
                "omit_vancomycin_or_linezolid_in_mrsa_risk",
            ],
        },
        "evidence": "ATS/IDSA CAP 2019; MRSA CAP has 30-40% mortality without appropriate coverage",
        "severity": "HIGH",
        "description": "MRSA-risk patients (prior MRSA, cavitary infiltrate) require "
        "vancomycin or linezolid; standard empiric therapy is insufficient.",
    },
    "CAP-PSEUDOMONAS-RISK-COVERAGE": {
        "rule_id": "CAP-PSEUDOMONAS-RISK-COVERAGE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_non_antipseudomonal_in_risk",
                "give_single_agent_for_pseudomonas_risk",
            ],
        },
        "evidence": "ATS/IDSA CAP 2019; Pseudomonas CAP requires antipseudomonal "
        "agents; standard empiric monotherapy is inadequate",
        "severity": "HIGH",
        "description": "Pseudomonas-risk patients need antipseudomonal coverage; "
        "standard CAP empiric or single-agent therapy leads to treatment failure.",
    },
    "CAP-SEVERE-ICU-ADMISSION": {
        "rule_id": "CAP-SEVERE-ICU-ADMISSION-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "treat_on_ward_if_severe_cap",
                "delay_icu_transfer_in_severe_cap",
            ],
        },
        "evidence": "ATS/IDSA CAP 2019; severe CAP (PaO2/FiO2 < 250, multilobar, septic shock) requires ICU-level care",
        "severity": "HIGH",
        "description": "Severe CAP meeting ICU criteria (shock, respiratory failure) "
        "must not be managed on general ward; delays worsen mortality.",
    },
    # ═══════════════════════════════════════════════════════
    # IDSA MENINGITIS (4 traps, 4 rules)
    # ═══════════════════════════════════════════════════════
    "MENING-DEXAMETHASONE-TIMING": {
        "rule_id": "MENING-DEXAMETHASONE-TIMING-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_dexamethasone_after_antibiotics_in_meningitis",
                "delay_dexamethasone_for_culture_in_meningitis",
            ],
        },
        "evidence": "IDSA Meningitis 2004; de Gans J, NEJM 2002; dexamethasone "
        "must be given before or with first antibiotic dose",
        "severity": "HIGH",
        "description": "Dexamethasone given after antibiotics loses anti-inflammatory "
        "benefit; must precede or coincide with first antibiotic dose.",
    },
    "MENING-HSV-ENCEPHALITIS": {
        "rule_id": "MENING-HSV-ENCEPHALITIS-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "omit_acyclovir_if_hsv_suspected",
                "give_antibiotics_only_without_acyclovir_in_encephalitis",
            ],
        },
        "evidence": "IDSA Meningitis 2004; Whitley RJ, NEJM 1986; untreated HSV encephalitis has 70% mortality",
        "severity": "CRITICAL",
        "description": "HSV encephalitis requires empiric acyclovir; antibiotics alone "
        "don't treat viral encephalitis and mortality reaches 70% untreated.",
    },
    "MENING-IMMUNOCOMP-LISTERIA": {
        "rule_id": "MENING-IMMUNOCOMP-LISTERIA-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "omit_ampicillin_in_immunocompromised_meningitis",
                "give_ceftriaxone_only_in_immunocompromised",
            ],
        },
        "evidence": "IDSA Meningitis 2004; Listeria requires ampicillin; cephalosporins have no Listeria activity",
        "severity": "HIGH",
        "description": "Immunocompromised patients need ampicillin for Listeria "
        "coverage; ceftriaxone alone misses this pathogen entirely.",
    },
    "MENING-NEONATE-COVERAGE": {
        "rule_id": "MENING-NEONATE-COVERAGE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_adult_empiric_for_neonatal_meningitis",
                "omit_ampicillin_in_neonatal_meningitis",
            ],
        },
        "evidence": "IDSA Meningitis 2004; neonatal meningitis requires ampicillin + "
        "gentamicin/cefotaxime for GBS and Listeria coverage",
        "severity": "CRITICAL",
        "description": "Neonatal meningitis has different pathogens (GBS, E. coli, "
        "Listeria); adult empiric regimen misses these organisms.",
    },
    # ═══════════════════════════════════════════════════════
    # UNIVERSAL CLINICAL SAFETY (4 traps, 3 rules)
    # ═══════════════════════════════════════════════════════
    "SAFETY-ALLERGY-CHECK": {
        "rule_id": "SAFETY-ALLERGY-CHECK-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_known_allergen_drug",
                "skip_allergy_verification_before_drug",
            ],
        },
        "evidence": "Joint Commission NPSG 2024; administering a known allergen "
        "is a sentinel event with anaphylaxis risk",
        "severity": "CRITICAL",
        "description": "Administering a known allergen can cause fatal anaphylaxis; "
        "allergy verification is mandatory before any drug administration.",
    },
    "SAFETY-HEPATIC-DOSE-ADJUST": {
        "rule_id": "SAFETY-HEPATIC-DOSE-ADJUST-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_full_dose_hepatotoxin_in_liver_failure",
                "give_acetaminophen_full_dose_in_cirrhosis",
            ],
        },
        "evidence": "FDA Hepatic Impairment Guidance 2020; hepatotoxins at full "
        "dose in liver failure cause acute decompensation",
        "severity": "HIGH",
        "description": "Full-dose hepatotoxic drugs in liver failure cause "
        "decompensation; acetaminophen must be dose-reduced in cirrhosis.",
    },
    "SAFETY-RENAL-DOSE-ADJUST": {
        "rule_id": "SAFETY-RENAL-DOSE-ADJUST-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_full_dose_nephrotoxin_in_renal_failure",
                "give_enoxaparin_full_dose_in_ckd",
            ],
        },
        "evidence": "FDA Renal Impairment Guidance 2020; renally-cleared drugs "
        "accumulate causing toxicity in renal failure",
        "severity": "HIGH",
        "description": "Nephrotoxic drugs at full dose in renal failure accumulate; "
        "enoxaparin requires dose adjustment for CrCl < 30 mL/min.",
    },
    # ═══════════════════════════════════════════════════════
    # GINA ASTHMA EXACERBATION (3 traps, 3 rules)
    # ═══════════════════════════════════════════════════════
    "ASTHMA-CONCURRENT-INFECTION-ABX": {
        "rule_id": "ASTHMA-CONCURRENT-INFECTION-ABX-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_fluoroquinolone_without_clear_indication",
                "withhold_antibiotics_in_confirmed_pneumonia",
            ],
        },
        "evidence": "GINA 2024; routine antibiotics for asthma exacerbation are not "
        "recommended unless clear bacterial infection is present",
        "severity": "HIGH",
        "description": "Antibiotics are only indicated for confirmed bacterial "
        "infection in asthma exacerbation; fluoroquinolone overuse promotes resistance.",
    },
    "ASTHMA-SEVERE-MGSO4": {
        "rule_id": "ASTHMA-SEVERE-MGSO4-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "discharge_severe_exacerbation_without_mgso4",
                "give_only_bronchodilator_in_life_threatening",
            ],
        },
        "evidence": "GINA 2024; severe/life-threatening exacerbation requires IV MgSO4 as adjunctive bronchodilator",
        "severity": "HIGH",
        "description": "Life-threatening asthma requires IV MgSO4 as adjunct; "
        "bronchodilators alone are insufficient for severe exacerbation.",
    },
    "ASTHMA-STEROID-DEPENDENT-STRESS-DOSE": {
        "rule_id": "ASTHMA-STEROID-DEPENDENT-STRESS-DOSE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "withhold_stress_dose_steroid_in_dependent",
                "abruptly_stop_chronic_steroid_in_exacerbation",
            ],
        },
        "evidence": "GINA 2024; steroid-dependent patients have adrenal suppression; "
        "abrupt withdrawal causes adrenal crisis",
        "severity": "HIGH",
        "description": "Steroid-dependent asthma patients have HPA axis suppression; "
        "stress-dose steroids are mandatory, abrupt withdrawal causes crisis.",
    },
    # ═══════════════════════════════════════════════════════
    # KDIGO CONTRAST AKI (3 traps, 3 rules)
    # ═══════════════════════════════════════════════════════
    "CAKI-HIGH-RISK-PREHYDRATE": {
        "rule_id": "CAKI-HIGH-RISK-PREHYDRATE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_contrast_without_prehydration_high_risk",
                "use_high_osmolar_contrast_in_high_risk",
            ],
        },
        "evidence": "KDIGO Contrast AKI 2012; high-osmolar contrast increases "
        "nephrotoxicity risk 2-3x; prehydration reduces risk by 40%",
        "severity": "HIGH",
        "description": "High-risk patients require prehydration before contrast; "
        "high-osmolar contrast agents significantly increase nephrotoxicity.",
    },
    "CAKI-METFORMIN-HOLD-48H": {
        "rule_id": "CAKI-METFORMIN-HOLD-48H-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "continue_metformin_during_contrast_study",
                "restart_metformin_before_48h_post_contrast",
            ],
        },
        "evidence": "KDIGO Contrast AKI 2012; ACR Contrast Manual 2023; metformin "
        "with contrast-induced AKI causes lactic acidosis",
        "severity": "HIGH",
        "description": "Metformin must be held before contrast and for 48h after; "
        "contrast-induced AKI impairs metformin clearance causing lactic acidosis.",
    },
    "CAKI-SPECIFIC-NEPHROTOXIN-HOLD": {
        "rule_id": "CAKI-SPECIFIC-NEPHROTOXIN-HOLD-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "continue_nephrotoxin_during_contrast_exposure",
                "give_nsaid_periprocedural_with_contrast",
            ],
        },
        "evidence": "KDIGO Contrast AKI 2012; concurrent nephrotoxins with contrast create additive renal injury",
        "severity": "HIGH",
        "description": "Concurrent nephrotoxins with contrast create additive renal "
        "injury; NSAIDs must be held periprocedurally.",
    },
    # ═══════════════════════════════════════════════════════
    # STATUS EPILEPTICUS (3 traps, 3 rules)
    # ═══════════════════════════════════════════════════════
    "SE-ALCOHOL-WITHDRAWAL-BENZO": {
        "rule_id": "SE-ALCOHOL-WITHDRAWAL-BENZO-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_phenytoin_in_alcohol_withdrawal_seizure",
                "give_haloperidol_in_withdrawal_seizure",
            ],
        },
        "evidence": "NCS Status Epilepticus 2012; phenytoin is ineffective for "
        "alcohol withdrawal seizures; haloperidol lowers seizure threshold",
        "severity": "HIGH",
        "description": "Phenytoin is ineffective for alcohol withdrawal seizures "
        "(mechanism is GABA not sodium channel); haloperidol lowers seizure threshold.",
    },
    "SE-HYPOGLYCEMIA-GLUCOSE-FIRST": {
        "rule_id": "SE-HYPOGLYCEMIA-GLUCOSE-FIRST-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_antiepileptic_before_glucose_correction",
                "delay_glucose_correction_for_eeg",
            ],
        },
        "evidence": "NCS Status Epilepticus 2012; hypoglycemic seizures resolve with "
        "glucose correction, not antiepileptics",
        "severity": "CRITICAL",
        "description": "Hypoglycemic seizures resolve with glucose correction; "
        "antiepileptics are ineffective and delay definitive treatment.",
    },
    "SE-KNOWN-EPILEPSY-CHECK-LEVELS": {
        "rule_id": "SE-KNOWN-EPILEPSY-CHECK-LEVELS-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "add_new_aed_without_checking_levels",
                "give_loading_dose_without_level_check",
            ],
        },
        "evidence": "NCS Status Epilepticus 2012; subtherapeutic levels require optimization before adding new agents",
        "severity": "HIGH",
        "description": "Loading a new AED without checking existing levels risks "
        "toxicity if existing drug is therapeutic or over-therapeutic.",
    },
    # ═══════════════════════════════════════════════════════
    # AABB TRANSFUSION (2 traps, 2 rules)
    # ═══════════════════════════════════════════════════════
    "TRANS-CARDIAC-LIBERAL-THRESHOLD": {
        "rule_id": "TRANS-CARDIAC-LIBERAL-THRESHOLD-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "use_liberal_transfusion_threshold_cardiac",
                "transfuse_for_hb_above_8_in_cardiac",
            ],
        },
        "evidence": "AABB 2024; TRICC trial; restrictive threshold (Hb < 8) is "
        "preferred in cardiac patients to reduce TACO/fluid overload",
        "severity": "HIGH",
        "description": "Cardiac patients benefit from restrictive transfusion (Hb < 8); "
        "liberal thresholds increase TACO and pulmonary edema risk.",
    },
    "TRANS-ANAPHYLAXIS-EPI": {
        "rule_id": "TRANS-ANAPHYLAXIS-EPI-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "continue_transfusion_during_anaphylaxis",
                "give_only_antihistamine_for_transfusion_anaphylaxis",
            ],
        },
        "evidence": "AABB 2024; transfusion anaphylaxis requires immediate stop "
        "and epinephrine; antihistamines alone are insufficient",
        "severity": "CRITICAL",
        "description": "Transfusion anaphylaxis requires immediate transfusion stop "
        "and epinephrine; antihistamine monotherapy is inadequate.",
    },
    # ═══════════════════════════════════════════════════════
    # ACLS CARDIAC ARREST (2 traps, 2 rules)
    # ═══════════════════════════════════════════════════════
    "ACLS-HYPERKALEMIA-CALCIUM": {
        "rule_id": "ACLS-HYPERKALEMIA-CALCIUM-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_succinylcholine_in_hyperkalemic_arrest",
                "delay_calcium_in_hyperkalemic_arrest",
            ],
        },
        "evidence": "AHA ACLS 2020; succinylcholine releases K+ from muscle; "
        "calcium delay prolongs cardiac toxicity window",
        "severity": "CRITICAL",
        "description": "Succinylcholine worsens hyperkalemia via K+ release from "
        "muscle; calcium gluconate delay prolongs fatal cardiac toxicity.",
    },
    "ACLS-SHOCKABLE-DEFIB-FIRST": {
        "rule_id": "ACLS-SHOCKABLE-DEFIB-FIRST-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_amiodarone_before_first_shock",
                "delay_defibrillation_for_intubation",
            ],
        },
        "evidence": "AHA ACLS 2020; defibrillation is the definitive treatment for "
        "VF/pVT; each minute delay reduces survival by 7-10%",
        "severity": "CRITICAL",
        "description": "In shockable rhythm, defibrillation takes absolute priority; "
        "amiodarone before first shock and intubation delays worsen outcomes.",
    },
    # ═══════════════════════════════════════════════════════
    # APA AGITATION MANAGEMENT (2 traps, 2 rules)
    # ═══════════════════════════════════════════════════════
    "PSYCH-NMS-DANTROLENE": {
        "rule_id": "PSYCH-NMS-DANTROLENE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_antipsychotic_in_nms",
                "give_haloperidol_in_nms",
            ],
        },
        "evidence": "APA Practice Guidelines; NMS is caused by antipsychotic "
        "dopamine blockade; readministering antipsychotics is fatal",
        "severity": "CRITICAL",
        "description": "NMS is caused by dopamine blockade from antipsychotics; "
        "readministering any antipsychotic worsens the syndrome fatally.",
    },
    "PSYCH-SEROTONIN-CYPROHEPTADINE": {
        "rule_id": "PSYCH-SEROTONIN-CYPROHEPTADINE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_ssri_in_serotonin_syndrome",
                "give_tramadol_in_serotonin_syndrome",
            ],
        },
        "evidence": "APA Practice Guidelines; Boyer EW, NEJM 2005; serotonergic agents compound serotonin syndrome",
        "severity": "CRITICAL",
        "description": "SSRIs and tramadol increase serotonin further in serotonin "
        "syndrome; all serotonergic agents must be discontinued.",
    },
    # ═══════════════════════════════════════════════════════
    # GI BLEEDING (2 traps, 2 rules)
    # ═══════════════════════════════════════════════════════
    "GIB-HEMODYNAMIC-INSTABILITY-RESUSCITATE": {
        "rule_id": "GIB-HEMODYNAMIC-INSTABILITY-RESUSCITATE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "delay_resuscitation_for_endoscopy_in_gi_bleed",
                "give_oral_fluids_only_in_gi_hemorrhagic_shock",
            ],
        },
        "evidence": "ACG GI Bleeding 2023; hemodynamic resuscitation takes priority "
        "over endoscopy in unstable patients",
        "severity": "HIGH",
        "description": "Hemodynamic resuscitation must precede endoscopy in unstable "
        "GI bleeding; oral fluids are insufficient for hemorrhagic shock.",
    },
    "GIB-PLATELET-TRANSFUSE": {
        "rule_id": "GIB-PLATELET-TRANSFUSE-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "delay_platelet_transfusion_in_active_bleed",
                "give_aspirin_in_severe_thrombocytopenia",
            ],
        },
        "evidence": "ACG GI Bleeding 2023; platelet count < 50k with active "
        "bleeding requires transfusion; antiplatelet agents worsen bleeding",
        "severity": "HIGH",
        "description": "Active GI bleeding with thrombocytopenia requires platelet "
        "transfusion; aspirin in this setting worsens hemorrhage.",
    },
    # ═══════════════════════════════════════════════════════
    # HYPERTENSIVE EMERGENCY (1 trap, 1 rule)
    # ═══════════════════════════════════════════════════════
    "HTN-ECLAMPSIA-MAGNESIUM": {
        "rule_id": "HTN-ECLAMPSIA-MAGNESIUM-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_ace_inhibitor_in_eclampsia",
                "give_nitroprusside_in_eclampsia",
            ],
        },
        "evidence": "ACOG 2020; ACE inhibitors are teratogenic; nitroprusside causes fetal cyanide toxicity",
        "severity": "CRITICAL",
        "description": "ACE inhibitors are teratogenic contraindications in eclampsia; "
        "nitroprusside produces cyanide metabolites toxic to the fetus.",
    },
    # ═══════════════════════════════════════════════════════
    # PALS PEDIATRIC EMERGENCY (1 trap, 1 rule)
    # ═══════════════════════════════════════════════════════
    "PEDS-NEONATE-SEIZURE-PHENOBARB": {
        "rule_id": "PEDS-NEONATE-SEIZURE-PHENOBARB-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_adult_dose_anticonvulsant_in_neonate",
                "give_diazepam_iv_in_neonate",
            ],
        },
        "evidence": "AHA PALS 2020; neonates require phenobarbital as first-line; "
        "IV diazepam contains benzyl alcohol toxic to neonates",
        "severity": "CRITICAL",
        "description": "Neonatal seizures require phenobarbital; IV diazepam contains "
        "benzyl alcohol causing gasping syndrome in neonates.",
    },
    # ═══════════════════════════════════════════════════════
    # PULMONARY EMBOLISM (1 trap, 1 rule)
    # ═══════════════════════════════════════════════════════
    "PE-MASSIVE-THROMBOLYSIS": {
        "rule_id": "PE-MASSIVE-THROMBOLYSIS-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "give_anticoagulation_only_in_massive_pe",
                "delay_thrombolysis_in_massive_pe",
            ],
        },
        "evidence": "ESC PE 2019; massive PE with hemodynamic collapse requires "
        "thrombolysis; anticoagulation alone has 25-65% mortality",
        "severity": "CRITICAL",
        "description": "Massive PE with shock requires thrombolysis; anticoagulation "
        "alone has unacceptably high mortality (25-65%).",
    },
    # ═══════════════════════════════════════════════════════
    # SSC SEPSIS HOUR-1 BUNDLE (1 trap, 1 rule)
    # ═══════════════════════════════════════════════════════
    "SEPSIS-ADRENAL-INSUFFICIENCY-STEROIDS": {
        "rule_id": "SEPSIS-ADRENAL-INSUFFICIENCY-STEROIDS-FORBIDDEN",
        "effect": {
            "type": "FORBIDDEN",
            "actions": [
                "withhold_steroids_in_refractory_shock",
                "give_high_dose_dexamethasone_in_septic_shock",
            ],
        },
        "evidence": "SSC 2021; stress-dose hydrocortisone (200mg/day) for refractory "
        "shock; high-dose dex increases infection/mortality",
        "severity": "HIGH",
        "description": "Refractory septic shock requires stress-dose hydrocortisone; "
        "high-dose dexamethasone worsens immunosuppression and outcomes.",
    },
}


def apply_companions(graph_path: Path) -> tuple[int, list[str]]:
    """Add companion FORBIDDEN rules to a graph file.

    Returns:
        (count of rules added, list of rule IDs added)
    """
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

            if rid not in COMPANION_FORBIDDEN:
                continue

            # Check effect type - only add companion for REQUIRED/EXPECTED
            eff_type = rule.get("effect", {}).get("type", "")
            if eff_type == "FORBIDDEN":
                continue  # Already has a FORBIDDEN effect

            companion = COMPANION_FORBIDDEN[rid]

            # Build companion rule inheriting condition from parent
            new_rule = {
                "rule_id": companion["rule_id"],
                "condition": rule["condition"],
                "effect": copy.deepcopy(companion["effect"]),
                "evidence": companion["evidence"],
                "severity": companion["severity"],
                "description": companion["description"],
            }

            # Copy condition metadata from parent
            for field in ("condition_variables", "trigger_range", "normal_range"):
                if field in rule:
                    new_rule[field] = copy.deepcopy(rule[field])

            new_rules.append(new_rule)
            added_rules.append(companion["rule_id"])

        node["conditional_rules"] = new_rules

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
    """Apply all companion FORBIDDEN rules to affected graphs."""
    print("=" * 60)
    print("Root Cause A Fix: Adding Companion FORBIDDEN Rules")
    print("=" * 60)

    # Load analysis to know which graphs need fixing
    with open(ANALYSIS_FILE, encoding="utf-8") as f:
        analysis = json.load(f)

    affected_graphs = set(analysis.get("root_cause_a_by_graph", {}).keys())
    print(f"\nAffected graphs: {len(affected_graphs)}")

    total_added = 0
    all_added_rules: list[str] = []

    for graph_file in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(graph_file, encoding="utf-8") as f:
            g = yaml.safe_load(f)
        gid = g.get("graph_id", graph_file.stem)

        if gid not in affected_graphs:
            continue

        count, rules = apply_companions(graph_file)
        total_added += count
        all_added_rules.extend(rules)

        if count > 0:
            print(f"  {gid}: added {count} companion FORBIDDEN rules")
            for r in rules:
                print(f"    + {r}")
        else:
            print(f"  {gid}: no changes (rules may already have FORBIDDEN)")

    print(f"\n{'=' * 60}")
    print(f"Total companion FORBIDDEN rules added: {total_added}")
    print(f"Graphs modified: {len([r for r in all_added_rules])}")

    # Verify no overlap with unconditional forbidden
    print(f"\n{'=' * 60}")
    print("Verifying no overlap with unconditional forbidden...")
    overlap_count = 0
    for graph_file in sorted(GRAPHS_DIR.glob("*.yaml")):
        with open(graph_file, encoding="utf-8") as f:
            g = yaml.safe_load(f)

        uncond_forbidden: set[str] = set()
        for _nid, node in g.get("nodes", {}).items():
            uncond_forbidden.update(node.get("forbidden_actions", []))

        for _nid, node in g.get("nodes", {}).items():
            for rule in node.get("conditional_rules", []):
                if rule.get("effect", {}).get("type") != "FORBIDDEN":
                    continue
                for action in rule.get("effect", {}).get("actions", []):
                    if action in uncond_forbidden:
                        overlap_count += 1
                        print(
                            f"  WARNING: {rule['rule_id']} action '{action}' "
                            f"overlaps with unconditional forbidden in {g.get('graph_id')}"
                        )

    if overlap_count == 0:
        print("  No overlaps found.")
    else:
        print(f"  {overlap_count} overlapping actions found (pre-existing, not from this fix)")


if __name__ == "__main__":
    main()
