#!/usr/bin/env python3
"""Build source-grounded corpus JSON for 12 expansion graphs without parsed PDF.

Inputs are summaries from WebSearch on the official guideline sources (publisher
sites + PubMed/PMC). Each entry below is hand-curated from the search results.
Output schema matches data_release/v5.0/rag_corpus/*.parsed.json so the
atom_proposer can ingest the same way.
"""

from __future__ import annotations

import json
from pathlib import Path

OUT_DIR = Path("data_release/v7_websearch_corpus")
OUT_DIR.mkdir(parents=True, exist_ok=True)

CORPUS: dict[str, dict] = {
    # ---------------------------------------------------------------- 1
    "aha_asa_ich_2022": {
        "guideline_name": "2022 AHA/ASA Guideline for the Management of Patients With Spontaneous Intracerebral Hemorrhage",
        "source": "American Heart Association / American Stroke Association",
        "doi": "10.1161/STR.0000000000000407",
        "url": "https://www.ahajournals.org/doi/10.1161/STR.0000000000000407",
        "recommendations": [
            {"id": "rec_1", "section": "Diagnostic Imaging", "text": "Rapid neuroimaging with CT or MRI is recommended to confirm the diagnosis of spontaneous ICH in patients presenting with stroke-like symptoms.", "strength": "I", "evidence_level": "B-NR"},
            {"id": "rec_2", "section": "Hematoma Expansion Monitoring", "text": "Serial head CT can be useful within the first 24 hours after symptom onset to evaluate for hemorrhage expansion. In patients with low GCS score or neurological deterioration, serial head CT can be useful to evaluate for hemorrhage expansion, hydrocephalus, brain swelling, or herniation.", "strength": "IIa", "evidence_level": "B-NR"},
            {"id": "rec_3", "section": "Anticoagulation Reversal — Warfarin", "text": "Patients with ICH whose INR is elevated due to oral anticoagulant therapy should have their warfarin withheld, receive therapy to replace vitamin K dependent factors and correct the INR, and receive intravenous vitamin K.", "strength": "I", "evidence_level": "C-EO"},
            {"id": "rec_4", "section": "Anticoagulation Reversal — PCC vs FFP", "text": "PCCs (prothrombin complex concentrates) have not shown improved outcome compared with FFP but may have fewer complications and are reasonable to consider as an alternative to FFP.", "strength": "IIa", "evidence_level": "B-R"},
            {"id": "rec_5", "section": "Blood Pressure Management", "text": "In patients with spontaneous ICH who present with mild-to-moderately elevated blood pressure (SBP 150-220 mm Hg), acute lowering of SBP to a target of 140 mm Hg with the goal of maintaining in the range 130-150 mm Hg is safe and may be reasonable for improving functional outcome.", "strength": "IIa", "evidence_level": "B-R"},
            {"id": "rec_6", "section": "Stroke Unit Care", "text": "Care for patients with ICH in a dedicated stroke unit or neurocritical care unit is recommended to improve outcomes.", "strength": "I", "evidence_level": "B-NR"},
            {"id": "rec_7", "section": "Surgical Management — Cerebellar ICH", "text": "Cerebellar hemorrhage greater than 3 cm with neurological deterioration, brainstem compression, or hydrocephalus should be evacuated as soon as possible.", "strength": "I", "evidence_level": "B-NR"},
            {"id": "rec_8", "section": "Surgical Management — Supratentorial ICH", "text": "Minimally invasive surgical evacuation of supratentorial ICH may be considered in selected patients to reduce mortality. Routine open craniotomy for supratentorial ICH is not recommended.", "strength": "IIb", "evidence_level": "B-R"},
            {"id": "rec_9", "section": "Seizure Prophylaxis", "text": "Prophylactic antiseizure medication is not recommended for patients with ICH who do not have clinical seizures or epileptiform activity on continuous EEG.", "strength": "III: No Benefit", "evidence_level": "B-NR"},
            {"id": "rec_10", "section": "Venous Thromboembolism Prophylaxis", "text": "Intermittent pneumatic compression should be initiated on the day of admission for prevention of venous thromboembolism. Pharmacological prophylaxis with low-dose unfractionated heparin or low-molecular-weight heparin may be considered 24-48 hours after onset of bleeding once hemorrhage stability has been confirmed.", "strength": "I", "evidence_level": "A"},
            {"id": "rec_11", "section": "Glycemic Control", "text": "Hypoglycemia and large fluctuations in serum glucose should be avoided. Treatment of moderate hyperglycemia is reasonable to avoid worsening outcomes.", "strength": "IIa", "evidence_level": "B-NR"},
            {"id": "rec_12", "section": "Blood Pressure Long-Term", "text": "Long-term BP control with a target SBP <130 mm Hg is recommended for all patients with ICH to reduce risk of recurrence.", "strength": "I", "evidence_level": "A"},
        ],
    },
    # ---------------------------------------------------------------- 2
    "erc_hypothermia_2021": {
        "guideline_name": "European Resuscitation Council Guidelines 2021: Cardiac Arrest in Special Circumstances — Hypothermia",
        "source": "European Resuscitation Council",
        "doi": "10.1016/j.resuscitation.2021.02.011",
        "url": "https://www.resuscitationjournal.com/article/S0300-9572(21)00064-2/fulltext",
        "recommendations": [
            {"id": "rec_1", "section": "Definition", "text": "Initiate the hypothermia algorithm if the core temperature is below 35 °C. Mild (32-35 °C), moderate (28-32 °C), severe (<28 °C).", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_2", "section": "Pre-Arrest Risk Stratification", "text": "Hypothermic patients with risk factors for imminent cardiac arrest (core temperature <30 °C in young or healthy patients and <32 °C in elderly persons or patients with multiple comorbidities), ventricular dysrhythmias, or systolic blood pressure <90 mm Hg should be transferred directly to an extracorporeal life support (ECLS) centre.", "strength": "strong", "evidence_level": "low"},
            {"id": "rec_3", "section": "CPR", "text": "If a hypothermic patient arrests, continuous cardiopulmonary resuscitation (CPR) should be performed. Standard chest compression rate and depth apply.", "strength": "strong", "evidence_level": "low"},
            {"id": "rec_4", "section": "Defibrillation", "text": "Defibrillation should be attempted up to 3 times below 30 °C; if unsuccessful, withhold further shocks until core temperature reaches 30 °C.", "strength": "weak", "evidence_level": "low"},
            {"id": "rec_5", "section": "Drugs", "text": "Withhold adrenaline and other resuscitation drugs below 30 °C. Between 30-35 °C, double the standard interval between drug doses.", "strength": "strong", "evidence_level": "low"},
            {"id": "rec_6", "section": "Rewarming — Stable", "text": "Patients with stable circulation should be rewarmed with passive and active external rewarming techniques.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_7", "section": "Rewarming — Unstable", "text": "Those at risk of cardiac arrest or with unstable circulation require ECLS on standby for rapid initiation if needed. ECMO/CPB is the preferred rewarming method for hypothermic cardiac arrest.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_8", "section": "HOPE Score", "text": "Use the HOPE (Hypothermia Outcome Prediction after ECLS) score to inform decisions about ECLS rewarming for hypothermic cardiac arrest.", "strength": "weak", "evidence_level": "low"},
            {"id": "rec_9", "section": "Termination of Resuscitation", "text": "Do not declare death until rewarming has been attempted (\"not dead until warm and dead\"), unless lethal injuries are obvious or chest compressions cannot be performed safely.", "strength": "strong", "evidence_level": "low"},
            {"id": "rec_10", "section": "Airway Management", "text": "Tracheal intubation should be performed when clinically indicated. Tracheal intubation does not precipitate ventricular fibrillation in cooled patients.", "strength": "strong", "evidence_level": "low"},
            {"id": "rec_11", "section": "Avoidance", "text": "Avoid rough handling of severely hypothermic patients to prevent triggering ventricular fibrillation.", "strength": "strong", "evidence_level": "low"},
        ],
    },
    # ---------------------------------------------------------------- 3
    "esvs_acute_limb_ischemia_2020": {
        "guideline_name": "ESVS 2020 Clinical Practice Guidelines on the Management of Acute Limb Ischaemia",
        "source": "European Society for Vascular Surgery",
        "doi": "10.1016/j.ejvs.2019.09.006",
        "url": "https://www.ejves.com/article/S1078-5884(19)31515-1/fulltext",
        "recommendations": [
            {"id": "rec_1", "section": "Definition", "text": "Acute limb ischaemia (ALI) is a sudden decrease in arterial perfusion of the limb with potential threat to limb survival, with symptom duration less than two weeks.", "strength": "strong", "evidence_level": "C"},
            {"id": "rec_2", "section": "Initial Anticoagulation", "text": "Once the diagnosis of ALI is suspected, intravenous heparin should be initiated immediately to prevent thrombus propagation, unless contraindicated.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_3", "section": "Rutherford Classification", "text": "Ischaemia should be graded clinically using the Rutherford ALI classification: Class I (viable), IIa (marginally threatened — salvageable if promptly treated), IIb (immediately threatened — salvageable with immediate revascularisation), III (irreversible — major tissue loss or permanent nerve damage inevitable).", "strength": "strong", "evidence_level": "C"},
            {"id": "rec_4", "section": "Imaging", "text": "Duplex ultrasound or CT angiography should be performed to confirm the diagnosis and plan revascularisation, but should not delay treatment of immediately threatened (IIb) limbs.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_5", "section": "Revascularisation Urgency", "text": "If there is a neurological deficit in the limb, particularly involving motor loss (Rutherford IIb), urgent revascularisation is mandatory.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_6", "section": "Revascularisation Modality", "text": "Prompt diagnosis and revascularisation by means of catheter-based thrombolysis and/or thromboaspiration or by open surgery reduces the risk of limb loss and death. Modality choice depends on Rutherford class, anatomy, available expertise, and patient comorbidities.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_7", "section": "Primary Amputation", "text": "Primary amputation is recommended in patients with irreversible (Class III) ischaemia.", "strength": "strong", "evidence_level": "C"},
            {"id": "rec_8", "section": "Compartment Syndrome Surveillance", "text": "After revascularisation of severe ischaemia, monitor for compartment syndrome and perform fasciotomy when clinically indicated.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_9", "section": "Reperfusion Injury Management", "text": "Monitor for reperfusion injury including hyperkalaemia, acidosis, myoglobinuria, and acute kidney injury. Initiate appropriate management.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_10", "section": "Aetiology Workup", "text": "Investigate the cause of ALI (embolic, thrombotic, traumatic, dissection-related) post-revascularisation to guide secondary prevention.", "strength": "strong", "evidence_level": "C"},
            {"id": "rec_11", "section": "Long-Term Anticoagulation", "text": "Patients with embolic ALI from atrial fibrillation should receive long-term anticoagulation. Patients with thrombotic ALI on a background of atherosclerosis should receive antiplatelet therapy and risk-factor modification.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_12", "section": "Multidisciplinary Care", "text": "Care of patients with ALI requires multidisciplinary input including vascular surgery, interventional radiology, and critical care.", "strength": "strong", "evidence_level": "C"},
        ],
    },
    # ---------------------------------------------------------------- 4
    "ispad_pediatric_dka_2022": {
        "guideline_name": "ISPAD 2022 Clinical Practice Consensus Guidelines: Diabetic Ketoacidosis and Hyperglycemic Hyperosmolar State",
        "source": "International Society for Pediatric and Adolescent Diabetes",
        "doi": "10.1111/pedi.13406",
        "url": "https://onlinelibrary.wiley.com/doi/abs/10.1111/pedi.13406",
        "recommendations": [
            {"id": "rec_1", "section": "Initial Resuscitation", "text": "Initial isotonic fluid resuscitation is recommended for all patients in the first 20 to 30 minutes after presentation. ISPAD recommends 20 mL/kg as an initial bolus.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_2", "section": "Volume Repletion", "text": "Volume deficit should be replenished over 36 hours in association with an insulin infusion.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_3", "section": "PECARN Findings", "text": "The PECARN DKA Fluid trial showed neither the rate of IV fluid rehydration nor the sodium chloride content significantly changed neurologic outcomes; rapid rehydration was associated with quicker clinical improvement.", "strength": "strong", "evidence_level": "A"},
            {"id": "rec_4", "section": "Insulin Initiation", "text": "Insulin should be started only after the first hour of fluid therapy AND when potassium levels are >3.0 mmol/L. Insulin must never be administered as an IV bolus.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_5", "section": "Insulin Infusion", "text": "Use rapid-acting insulin at 0.05 unit/kg/hour to 0.1 unit/kg/hour without a weight-based maximum. Do not exceed 0.1 unit/kg/hour.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_6", "section": "Insulin Dose Reduction", "text": "If blood glucose has been decreasing >5 mmol/L/hour and IV dextrose has been maximised, reduce insulin infusion to 0.05 unit/kg/hour, with further gradual decrease to no less than 0.025 unit/kg/hour if glucose continues to fall rapidly.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_7", "section": "Cerebral Edema — Recognition", "text": "Children at increased risk for cerebral injury (<5 years of age, pH <7.1, pCO2 <21 mmHg, blood urea nitrogen >20 mg/dL) should be considered for immediate treatment in an intensive care unit.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_8", "section": "Cerebral Edema — Treatment", "text": "If cerebral edema is suspected and hypoglycemia is excluded, prompt treatment with an osmotic diuretic (mannitol 0.5-1 g/kg or hypertonic saline 3% 2.5-5 mL/kg) is indicated, followed by a CT scan and referral to a neurosurgeon. Treatment should start as soon as the diagnosis is suspected.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_9", "section": "Bicarbonate", "text": "Bicarbonate administration is not recommended except in life-threatening hyperkalemia or severe acidosis affecting cardiac contractility.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_10", "section": "Potassium Replacement", "text": "Add potassium to fluids as soon as urine output is documented and the serum potassium is <5.5 mmol/L. Hold insulin until serum potassium is >3.0 mmol/L.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_11", "section": "Phosphate", "text": "Routine phosphate replacement is not recommended. Severe hypophosphatemia (<1 mg/dL) with symptoms may be treated.", "strength": "weak", "evidence_level": "C"},
            {"id": "rec_12", "section": "Transition to Subcutaneous Insulin", "text": "Subcutaneous insulin should be started 15-30 minutes before stopping the IV insulin infusion to prevent rebound hyperglycemia.", "strength": "strong", "evidence_level": "B"},
        ],
    },
    # ---------------------------------------------------------------- 5
    "ukka_hyperkalemia_2023": {
        "guideline_name": "UK Kidney Association Clinical Practice Guideline: Management of Hyperkalaemia in Adults (October 2023)",
        "source": "UK Kidney Association",
        "doi": "",
        "url": "https://www.ukkidney.org/sites/default/files/FINAL%20VERSION%20-%20UKKA%20CLINICAL%20PRACTICE%20GUIDELINE%20-%20MANAGEMENT%20OF%20HYPERKALAEMIA%20IN%20ADULTS%20-%20191223_0.pdf",
        "recommendations": [
            {"id": "rec_1", "section": "ECG Monitoring", "text": "Obtain a 12-lead ECG urgently in any patient with serum potassium >=6.0 mmol/L or with significant ECG changes regardless of potassium level. Continuous cardiac monitoring is recommended for K+ >=6.5 mmol/L or with ECG changes.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_2", "section": "Cardiac Membrane Stabilisation", "text": "Administer 30 mL of 10% calcium gluconate intravenously over 10 minutes when ECG changes are present, to protect the heart and avoid delay in initiating potassium-lowering treatments. Calcium IV may be repeated after 5 minutes if ECG changes persist.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_3", "section": "Insulin/Glucose", "text": "Administer 10 units of soluble insulin with 25 g glucose IV when hyperkalaemia is known or suspected (K+ >=6.5 mmol/L). This is the most effective intracellular potassium shifter.", "strength": "strong", "evidence_level": "A"},
            {"id": "rec_4", "section": "Hypoglycaemia Prevention", "text": "Check baseline blood glucose before insulin/glucose. For patients with pre-treatment blood glucose <7 mmol/L, give a 10% glucose infusion for 5 hours following insulin/glucose to prevent hypoglycaemia.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_5", "section": "Salbutamol", "text": "Nebulised salbutamol 10-20 mg may be used adjunctively to lower potassium. Caution in patients with ischaemic heart disease or tachyarrhythmias.", "strength": "weak", "evidence_level": "B"},
            {"id": "rec_6", "section": "Sodium Bicarbonate", "text": "Sodium bicarbonate is not recommended as a routine first-line treatment for hyperkalaemia but may be considered for severe metabolic acidosis (pH <7.2).", "strength": "weak", "evidence_level": "C"},
            {"id": "rec_7", "section": "Potassium Removal — Diuretics", "text": "Loop diuretics (e.g., furosemide 40-80 mg IV) may be used to enhance renal potassium excretion in volume-replete patients with adequate renal function.", "strength": "weak", "evidence_level": "C"},
            {"id": "rec_8", "section": "Potassium Binders", "text": "Sodium zirconium cyclosilicate (SZC) or patiromer may be used for sustained potassium reduction in patients with chronic hyperkalaemia or those unable to tolerate other measures.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_9", "section": "Dialysis", "text": "Urgent haemodialysis is indicated for refractory hyperkalaemia, particularly in patients with end-stage renal disease, severe ECG changes, or those failing medical management.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_10", "section": "Source Control", "text": "Identify and stop all potassium-elevating medications (RAAS inhibitors, potassium-sparing diuretics, NSAIDs, trimethoprim, heparin) and dietary potassium intake.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_11", "section": "Reassessment", "text": "Recheck serum potassium 1-2 hours after intervention and repeat measures as needed until levels are <5.5 mmol/L and stable.", "strength": "strong", "evidence_level": "C"},
        ],
    },
    # ---------------------------------------------------------------- 6
    "who_severe_malaria_2023": {
        "guideline_name": "WHO 2023 Guidelines for Malaria — Severe Malaria Treatment",
        "source": "World Health Organization",
        "doi": "10.2471/B09146",
        "url": "https://www.who.int/publications/i/item/guidelines-for-malaria",
        "recommendations": [
            {"id": "rec_1", "section": "First-Line Antimalarial", "text": "WHO strongly recommends parenteral artesunate in preference to quinine and artemether for the treatment of severe P. falciparum malaria in adults and children, including infants, pregnant women in all trimesters, and lactating women.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_2", "section": "Dosing", "text": "Artesunate 2.4 mg/kg body weight is administered intravenously (IV) or intramuscularly (IM) at admission (time=0), then at 12 h and 24 h, then once daily until the patient can take oral medication.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_3", "section": "Pediatric Dosing", "text": "Children weighing <20 kg should receive a higher dose of 3 mg/kg artesunate at each administration to ensure equivalent exposure to that of larger children and adults.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_4", "section": "Route", "text": "Intravenous (IV) injection is the preferred route. Intramuscular (IM) injection is acceptable when IV access cannot be obtained quickly.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_5", "section": "Duration", "text": "Continue parenteral artesunate for at least 24 hours and until the patient can tolerate a full course of oral ACT therapy.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_6", "section": "Follow-on Treatment", "text": "After IV artesunate, a full course of the recommended ACT for uncomplicated malaria should be administered.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_7", "section": "Pre-referral", "text": "If parenteral treatment cannot be given, pre-referral with a single rectal dose of artesunate (10 mg/kg) is recommended for children under 6 years pending transfer to a facility able to give parenteral therapy.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_8", "section": "Adjunctive Care — Antibiotics", "text": "Consider broad-spectrum antibiotic coverage in severe malaria patients with shock or proven bacteraemia, given the high prevalence of co-existing bacterial infection.", "strength": "weak", "evidence_level": "moderate"},
            {"id": "rec_9", "section": "Adjunctive Care — Fluids", "text": "Administer cautious fluid resuscitation. Avoid fluid bolus in children with severe malaria and impaired perfusion (FEAST trial showed harm).", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_10", "section": "Glucose Monitoring", "text": "Check blood glucose frequently. Treat hypoglycaemia (<2.2 mmol/L) immediately with IV dextrose.", "strength": "strong", "evidence_level": "high"},
        ],
    },
    # ---------------------------------------------------------------- 7
    "asam_alcohol_withdrawal_2020": {
        "guideline_name": "ASAM 2020 Clinical Practice Guideline on Alcohol Withdrawal Management",
        "source": "American Society of Addiction Medicine",
        "doi": "10.1097/ADM.0000000000000668",
        "url": "https://journals.lww.com/journaladdictionmedicine/fulltext/2020/06001/the_asam_clinical_practice_guideline_on_alcohol.1.aspx",
        "recommendations": [
            {"id": "rec_1", "section": "Severity Assessment", "text": "Use a validated tool such as the CIWA-Ar (Clinical Institute Withdrawal Assessment for Alcohol, revised) to assess the severity of alcohol withdrawal.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_2", "section": "Mild Withdrawal", "text": "For patients experiencing mild alcohol withdrawal (CIWA-Ar <10) at minimal risk of severe or complicated withdrawal, pharmacotherapy or supportive care alone may be provided.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_3", "section": "Moderate Withdrawal", "text": "Patients experiencing moderate alcohol withdrawal (CIWA-Ar 10-18) should receive pharmacotherapy. Benzodiazepines are first-line treatment.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_4", "section": "Severe Withdrawal", "text": "Patients experiencing severe alcohol withdrawal (CIWA-Ar >=19) should receive pharmacotherapy. Benzodiazepines are first-line treatment.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_5", "section": "Symptom-Triggered Dosing", "text": "Symptom-triggered administration of benzodiazepines (via CIWA-Ar) is recommended over fixed-dose administration because the former is associated with shorter length of stay and lower cumulative benzodiazepine administration.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_6", "section": "Benzodiazepine Choice", "text": "Long-acting benzodiazepines (chlordiazepoxide, diazepam) are preferred for most patients. Short-acting benzodiazepines (lorazepam, oxazepam) are preferred in patients with severe liver disease, the elderly, and pregnancy.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_7", "section": "Phenobarbital — Contraindication to Benzo", "text": "For patients with a contraindication for benzodiazepine use, phenobarbital is appropriate for providers experienced with its use.", "strength": "weak", "evidence_level": "moderate"},
            {"id": "rec_8", "section": "Phenobarbital — Resistant Withdrawal", "text": "Phenobarbital may be used as an adjunct to benzodiazepines to control resistant alcohol withdrawal syndrome in settings with close monitoring.", "strength": "weak", "evidence_level": "moderate"},
            {"id": "rec_9", "section": "Thiamine", "text": "Administer thiamine (typically 100 mg IV/IM daily for at least 3 days) before any glucose-containing fluids to prevent Wernicke encephalopathy.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_10", "section": "IV Fluids and Electrolytes", "text": "Correct fluid deficits and electrolyte disturbances (potassium, magnesium, phosphate). Avoid IV fluids containing dextrose before thiamine administration.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_11", "section": "Antipsychotics — Adjunctive", "text": "Antipsychotics may be considered as adjunctive therapy in patients with severe agitation or psychosis not controlled by benzodiazepines, but should not be used as monotherapy.", "strength": "weak", "evidence_level": "moderate"},
            {"id": "rec_12", "section": "Avoid", "text": "Beta-blockers, alpha-2 agonists, and anticonvulsants are not recommended as monotherapy for alcohol withdrawal management.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_13", "section": "Disposition", "text": "Patients with severe withdrawal, history of seizures or DT, significant comorbidities, or inadequate outpatient support should be admitted to inpatient or ICU level care.", "strength": "strong", "evidence_level": "moderate"},
        ],
    },
    # ---------------------------------------------------------------- 8
    "asco_tls_2023": {
        "guideline_name": "Expert Consensus Guidelines for the Prophylaxis and Management of Tumor Lysis Syndrome (2023)",
        "source": "Modified Delphi Panel — Cancer Treatment Reviews",
        "doi": "10.1016/j.ctrv.2023.102603",
        "url": "https://www.sciencedirect.com/science/article/abs/pii/S0305737223000968",
        "recommendations": [
            {"id": "rec_1", "section": "Risk Stratification", "text": "Classify patients as low, intermediate, or high risk based on patient factors (age, kidney function), malignancy type and grade, and chemotherapy agent.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_2", "section": "Low Risk — Hydration", "text": "Low-risk patients should receive intravenous hydration with isotonic fluids (about 2-3 L/m²/day) and oral allopurinol 300 mg/day for the first 7 days of the first cycle of treatment.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_3", "section": "Intermediate Risk", "text": "Intermediate-risk patients should receive aggressive IV hydration plus allopurinol; rasburicase may be considered if uric acid is rising despite allopurinol.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_4", "section": "High Risk — Hydration + Rasburicase", "text": "High-risk patients should receive intravenous hydration and prophylactic rasburicase (typically 0.2 mg/kg or fixed 3 mg dose). Repeat rasburicase if uric acid rises again.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_5", "section": "Allopurinol vs Rasburicase", "text": "Allopurinol blocks xanthine-oxidase, preventing conversion of hypoxanthine and xanthine to uric acid. Rasburicase converts existing uric acid to allantoin. The addition of allopurinol to rasburicase is unnecessary and may reduce rasburicase effectiveness.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_6", "section": "G6PD Screening", "text": "Screen for G6PD deficiency before administering rasburicase. Rasburicase is contraindicated in G6PD-deficient patients due to risk of severe haemolysis and methaemoglobinaemia.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_7", "section": "Electrolyte Monitoring", "text": "Monitor serum uric acid, potassium, phosphate, calcium, LDH, and creatinine every 4-6 hours during the first 24-48 hours of treatment in high-risk patients.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_8", "section": "Hyperkalaemia Management", "text": "Manage hyperkalaemia per standard protocols (calcium gluconate, insulin/glucose, salbutamol, bicarbonate). Avoid potassium-containing fluids.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_9", "section": "Hyperphosphataemia Management", "text": "Treat hyperphosphataemia with phosphate binders. Avoid IV calcium unless symptomatic hypocalcaemia, due to risk of calcium-phosphate precipitation.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_10", "section": "Renal Replacement Therapy", "text": "Initiate renal replacement therapy (haemodialysis or CRRT) for refractory hyperkalaemia, fluid overload, severe hyperphosphataemia, or symptomatic hypocalcaemia not responsive to medical management.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_11", "section": "Avoid Urinary Alkalinisation", "text": "Routine urinary alkalinisation with sodium bicarbonate is no longer recommended as it may precipitate calcium phosphate in renal tubules and worsen acute kidney injury.", "strength": "strong", "evidence_level": "moderate"},
        ],
    },
    # ---------------------------------------------------------------- 9
    "ash_sickle_cell_acs_2020": {
        "guideline_name": "ASH 2020 Guidelines for Sickle Cell Disease — Acute and Chronic Pain & Transfusion Support",
        "source": "American Society of Hematology",
        "doi": "10.1182/bloodadvances.2019001143",
        "url": "https://ashpublications.org/bloodadvances/article/4/2/327/440607",
        "recommendations": [
            {"id": "rec_1", "section": "Acute Pain — Time to Analgesia", "text": "For adults and children with SCD presenting to acute care with acute pain, the panel recommends rapid (within 1 hour of ED arrival) assessment and administration of analgesia.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_2", "section": "Acute Pain — Reassessment", "text": "Frequent reassessments (every 30-60 minutes) are recommended to optimize pain control and titrate analgesia.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_3", "section": "Acute Pain — Opioid First-Line", "text": "Parenteral opioids (typically morphine or hydromorphone) are recommended for moderate-to-severe acute vaso-occlusive pain in SCD when oral analgesia is insufficient.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_4", "section": "Acute Pain — Patient-Controlled Analgesia", "text": "Patient-controlled analgesia (PCA) is suggested for hospitalised patients with severe vaso-occlusive pain.", "strength": "weak", "evidence_level": "low"},
            {"id": "rec_5", "section": "Chronic Pain — Transfusion", "text": "For adults and children with SCD and recurrent acute pain, the panel suggests against chronic monthly transfusion therapy as first-line strategy. A trial of monthly transfusions may be reasonable when other measures (hydroxyurea, etc.) have failed.", "strength": "weak", "evidence_level": "low"},
            {"id": "rec_6", "section": "ACS — Severe Cases", "text": "The panel suggests automated red cell exchange (RCE) or manual RCE over simple transfusions in patients with SCD and severe acute chest syndrome (ACS).", "strength": "weak", "evidence_level": "low"},
            {"id": "rec_7", "section": "ACS — Automated vs Manual RCE", "text": "Automated RCE is preferred over manual RCE to more rapidly reduce HbS levels in severe ACS.", "strength": "weak", "evidence_level": "low"},
            {"id": "rec_8", "section": "ACS — Moderate Cases", "text": "The panel suggests automated RCE, manual RCE, or simple transfusions in patients with moderate ACS. RCE should be considered for rapidly progressive ACS, no response to simple transfusion, or high pretransfusion haemoglobin.", "strength": "weak", "evidence_level": "low"},
            {"id": "rec_9", "section": "Antibiotics", "text": "Broad-spectrum antibiotics covering encapsulated organisms (e.g., third-generation cephalosporin plus macrolide) are recommended for ACS due to the difficulty distinguishing infectious from infarctive aetiology.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_10", "section": "Oxygen", "text": "Supplemental oxygen should be administered to maintain SpO2 >=95% in ACS.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_11", "section": "Bronchodilators", "text": "Inhaled bronchodilators may be used in patients with reactive airway component during ACS.", "strength": "weak", "evidence_level": "low"},
            {"id": "rec_12", "section": "Incentive Spirometry", "text": "Incentive spirometry every 1-2 hours while awake is recommended in hospitalised patients with vaso-occlusive crisis to prevent ACS development.", "strength": "strong", "evidence_level": "moderate"},
        ],
    },
    # ---------------------------------------------------------------- 10
    "eau_obstructive_pyelonephritis_2024": {
        "guideline_name": "EAU 2024 Guidelines on Urological Infections — Obstructive Pyelonephritis Section",
        "source": "European Association of Urology",
        "doi": "10.1016/j.eururo.2024.03.035",
        "url": "https://www.europeanurology.com/article/S0302-2838(24)02263-2/fulltext",
        "recommendations": [
            {"id": "rec_1", "section": "Diagnosis — Imaging", "text": "Prompt differentiation between uncomplicated and obstructive pyelonephritis is essential. Use appropriate imaging (CT urography preferred; ultrasound acceptable as initial screen) to rule out obstruction in any patient with febrile UTI.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_2", "section": "Decompression Urgency", "text": "Mechanical decompression of the obstructed system must be performed emergently, ideally within 24 to 48 hours of presentation, to maximize outcomes. Delays beyond this period are associated with higher mortality, longer sepsis duration, multi-organ failure, and worse renal preservation.", "strength": "strong", "evidence_level": "A"},
            {"id": "rec_3", "section": "Decompression Modality", "text": "Either retrograde ureteral stent placement or percutaneous nephrostomy is acceptable. Choice depends on local expertise, patient stability, and anatomic factors. Percutaneous nephrostomy is often preferred in unstable septic patients.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_4", "section": "Empiric Antibiotics — Sepsis", "text": "Administer parenteral high-dose broad-spectrum antimicrobials within the first hour after clinical assumption of sepsis. Cover gram-negative enteric organisms including Pseudomonas if local epidemiology warrants.", "strength": "strong", "evidence_level": "A"},
            {"id": "rec_5", "section": "Source Control", "text": "Initiate source control (removal of foreign bodies, decompression of obstruction, drainage of abscesses) in addition to antimicrobial therapy.", "strength": "strong", "evidence_level": "A"},
            {"id": "rec_6", "section": "Culture-Guided Therapy", "text": "Obtain blood and urine cultures before antibiotic initiation when feasible. De-escalate to culture-guided therapy as soon as susceptibility data are available.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_7", "section": "Hemodynamic Resuscitation", "text": "Provide fluid resuscitation (30 mL/kg crystalloid in the first 3 hours for septic shock) and vasopressors (norepinephrine first-line) as needed to achieve MAP >=65 mmHg per Surviving Sepsis Campaign.", "strength": "strong", "evidence_level": "A"},
            {"id": "rec_8", "section": "Stone Management — Deferred", "text": "Definitive stone management (ureteroscopy with stone extraction, lithotripsy) should be deferred until sepsis has resolved (typically 1-2 weeks after decompression).", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_9", "section": "Risk-Stratification of Stones", "text": "Pre-existing or new ureteric stones >5 mm in the obstructed system require formal urological follow-up after sepsis resolution; stones <5 mm may pass spontaneously.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_10", "section": "Antibiotic Duration", "text": "Total antibiotic duration is typically 7-14 days (longer for bacteraemia or persistent obstruction). Switch to oral therapy once clinically stable and source control achieved.", "strength": "strong", "evidence_level": "B"},
            {"id": "rec_11", "section": "Special Populations — Pregnancy", "text": "Pregnant patients with obstructive pyelonephritis require multidisciplinary management with obstetrics. Stent or nephrostomy is preferred over surgical decompression. Avoid teratogenic antibiotics.", "strength": "strong", "evidence_level": "B"},
        ],
    },
    # ---------------------------------------------------------------- 11
    "erc_drowning_2021": {
        "guideline_name": "European Resuscitation Council Guidelines 2021: Cardiac Arrest in Special Circumstances — Drowning",
        "source": "European Resuscitation Council",
        "doi": "10.1016/j.resuscitation.2021.02.011",
        "url": "https://www.resuscitationjournal.com/article/S0300-9572(21)00064-2/fulltext",
        "recommendations": [
            {"id": "rec_1", "section": "Initial Rescue", "text": "Resuscitation of drowning victims should start as soon as it is safe and practical, potentially including ventilations while still in the water or on a boat if the rescuer is trained.", "strength": "strong", "evidence_level": "C"},
            {"id": "rec_2", "section": "Rescue Breaths", "text": "Start with 5 rescue breaths/ventilations using 100% inspired oxygen if available, before initiating chest compressions. Drowning is primarily a hypoxic insult.", "strength": "strong", "evidence_level": "C"},
            {"id": "rec_3", "section": "CPR Sequence", "text": "If the person remains unconscious without normal breathing after 5 rescue breaths, start chest compressions and alternate 30 compressions to 2 ventilations.", "strength": "strong", "evidence_level": "C"},
            {"id": "rec_4", "section": "AED Use", "text": "Apply an AED as soon as available. Standard defibrillation algorithms apply.", "strength": "strong", "evidence_level": "C"},
            {"id": "rec_5", "section": "Cervical Spine Precautions", "text": "Routine cervical spine immobilisation is not required unless there is a high-risk mechanism (e.g., diving, high-speed water sports, signs of serious trauma). Spine immobilisation can interfere with airway management.", "strength": "weak", "evidence_level": "C"},
            {"id": "rec_6", "section": "Hypothermia Consideration", "text": "Many drowning victims are also hypothermic; follow the hypothermia algorithm if core temperature is <35 °C, including consideration of ECLS rewarming for hypothermic cardiac arrest.", "strength": "strong", "evidence_level": "C"},
            {"id": "rec_7", "section": "Airway Management", "text": "Tracheal intubation is recommended for any drowning victim with reduced consciousness or cardiac arrest. Avoid the Heimlich manoeuvre as it may cause aspiration of stomach contents.", "strength": "strong", "evidence_level": "C"},
            {"id": "rec_8", "section": "Oxygenation", "text": "Provide 100% oxygen during initial resuscitation. Titrate FiO2 to maintain SpO2 94-98% once stable circulation is established.", "strength": "strong", "evidence_level": "C"},
            {"id": "rec_9", "section": "Hospital Disposition", "text": "All drowning victims with respiratory or neurological symptoms should be observed in hospital for at least 4-6 hours due to risk of delayed pulmonary oedema (\"secondary drowning\" is a misnomer; clinically significant deterioration is rare beyond this window).", "strength": "weak", "evidence_level": "C"},
            {"id": "rec_10", "section": "ECMO Indications", "text": "Consider extracorporeal life support (ECMO/CPB) in drowning victims with refractory cardiac arrest, particularly with hypothermia, witnessed arrest, and short submersion duration.", "strength": "weak", "evidence_level": "C"},
        ],
    },
    # ---------------------------------------------------------------- 12
    "ers_ats_niv_2017": {
        "guideline_name": "Official ERS/ATS 2017 Clinical Practice Guidelines: Noninvasive Ventilation for Acute Respiratory Failure",
        "source": "European Respiratory Society / American Thoracic Society",
        "doi": "10.1183/13993003.02426-2016",
        "url": "https://publications.ersnet.org/content/erj/50/2/1602426",
        "recommendations": [
            {"id": "rec_1", "section": "COPD Exacerbation — Indication", "text": "Bilevel NIV should be considered when pH <=7.35, PaCO2 >45 mmHg and respiratory rate >20-24 breaths/min despite standard medical therapy. Bilevel NIV is the preferred choice for patients with COPD who develop acute respiratory acidosis during hospital admission.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_2", "section": "COPD — Avoid Intubation", "text": "Recommend a trial of bilevel NIV in COPD patients considered to require endotracheal intubation, unless the patient is immediately deteriorating or has a contraindication to NIV.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_3", "section": "Cardiogenic Pulmonary Edema", "text": "Recommend either bilevel NIV or CPAP for patients with acute respiratory failure due to cardiogenic pulmonary edema.", "strength": "strong", "evidence_level": "high"},
            {"id": "rec_4", "section": "De Novo Hypoxemic Respiratory Failure", "text": "No specific recommendation for or against NIV in de novo hypoxemic respiratory failure due to insufficient evidence; if used, monitor closely for failure and proceed to intubation if no improvement within 1-2 hours.", "strength": "weak", "evidence_level": "low"},
            {"id": "rec_5", "section": "Immunocompromised", "text": "Suggest early NIV in immunocompromised patients with acute hypoxemic respiratory failure to avoid intubation and reduce risk of nosocomial infection.", "strength": "weak", "evidence_level": "moderate"},
            {"id": "rec_6", "section": "Post-extubation — High Risk", "text": "Recommend NIV in selected high-risk patients (older age, congestive heart failure, hypercapnic respiratory failure, COPD) to prevent post-extubation respiratory failure.", "strength": "weak", "evidence_level": "moderate"},
            {"id": "rec_7", "section": "Post-extubation — Established Failure", "text": "Suggest against using NIV to treat established post-extubation respiratory failure, as it may delay needed re-intubation.", "strength": "weak", "evidence_level": "moderate"},
            {"id": "rec_8", "section": "Weaning from Mechanical Ventilation", "text": "Suggest using NIV to facilitate weaning from mechanical ventilation in COPD patients with persistent hypercapnia.", "strength": "weak", "evidence_level": "moderate"},
            {"id": "rec_9", "section": "Asthma", "text": "Insufficient evidence to make a recommendation for or against NIV in acute asthma exacerbation.", "strength": "weak", "evidence_level": "very low"},
            {"id": "rec_10", "section": "Palliative Care — Symptomatic", "text": "Suggest NIV for symptomatic relief in patients receiving palliative care for end-stage disease, with clear discussion of goals of care.", "strength": "weak", "evidence_level": "low"},
            {"id": "rec_11", "section": "Failure Criteria — Intubation", "text": "Indicators of NIV failure (after 1-2 hours of trial) include worsening pH, persistent tachypnea >35/min, deteriorating mental status, hemodynamic instability, or failure to improve oxygenation. Proceed to intubation without further delay.", "strength": "strong", "evidence_level": "moderate"},
            {"id": "rec_12", "section": "Contraindications", "text": "Absolute contraindications include cardiac/respiratory arrest, severe encephalopathy, severe upper GI bleeding, hemodynamic instability, facial trauma/burns, and inability to protect the airway.", "strength": "strong", "evidence_level": "moderate"},
        ],
    },
}


def main() -> None:
    for gid, data in CORPUS.items():
        out_path = OUT_DIR / f"{gid}.parsed.json"
        full_text_parts = [
            f"[{r['section']}] {r['text']}" for r in data["recommendations"]
        ]
        out = {
            "guideline_id": gid,
            "guideline_name": data["guideline_name"],
            "source": data["source"],
            "doi": data["doi"],
            "url": data["url"],
            "recommendations": data["recommendations"],
            "full_text": "\n\n".join(full_text_parts),
            "_provenance": "WebSearch synthesis from official guideline summaries — Track-C Option E (2026-05-01)",
            "_corpus_kind": "websearch_synthesis",
        }
        out_path.write_text(json.dumps(out, indent=2, ensure_ascii=False))
        n_recs = len(data["recommendations"])
        n_chars = len(out["full_text"])
        print(f"  {gid:50s} {n_recs:3d} recs, {n_chars:5d} chars  -> {out_path}")
    print(f"\nWrote {len(CORPUS)} corpus files to {OUT_DIR}/")


if __name__ == "__main__":
    main()
