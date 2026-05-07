# Rule Coverage Audit Matrix

Auto-generated from CPG graph conditional_rules.

## Summary

- **Total graphs**: 25
- **Total unconditional forbidden**: 212
- **Total sequence rules**: 65
- **Total conditional rules**: 312
- **Total constraints**: 589

## Per-Graph Breakdown

| Graph | Nodes | Uncond. Forbidden | Sequence | Conditional | CRITICAL | HIGH |
|-------|-------|-------------------|----------|-------------|----------|------|
| aabb_transfusion | 4 | 8 | 1 | 7 | 4 | 3 |
| aba_burn_resuscitation | 6 | 8 | 6 | 7 | 4 | 3 |
| acls_cardiac_arrest | 6 | 12 | 5 | 24 | 12 | 12 |
| acog_obstetric_hemorrhage | 4 | 2 | 0 | 4 | 3 | 1 |
| ada_dka_management | 8 | 19 | 12 | 17 | 8 | 9 |
| aha_chest_pain_evaluation | 11 | 13 | 10 | 10 | 6 | 4 |
| aha_heart_failure_2022 | 24 | 9 | 0 | 9 | 3 | 6 |
| aha_stroke_2019 | 25 | 15 | 0 | 7 | 4 | 3 |
| anaphylaxis_management | 5 | 19 | 4 | 13 | 3 | 10 |
| apa_agitation_management | 4 | 5 | 1 | 8 | 8 | 0 |
| atrial_fibrillation | 3 | 1 | 1 | 7 | 3 | 4 |
| cap_pneumonia | 3 | 1 | 2 | 13 | 2 | 10 |
| copd_exacerbation | 2 | 2 | 0 | 8 | 1 | 6 |
| gi_bleeding | 2 | 1 | 0 | 10 | 4 | 6 |
| gina_asthma_exacerbation | 5 | 24 | 0 | 24 | 3 | 18 |
| hypertensive_emergency | 2 | 2 | 0 | 10 | 8 | 2 |
| idsa_meningitis | 5 | 6 | 2 | 20 | 12 | 8 |
| kdigo_aki_full | 13 | 5 | 0 | 24 | 9 | 15 |
| kdigo_contrast_aki | 7 | 10 | 7 | 19 | 2 | 16 |
| pals_pediatric_emergency | 4 | 5 | 4 | 5 | 2 | 3 |
| pulmonary_embolism | 3 | 2 | 0 | 10 | 5 | 5 |
| ssc_sepsis_hour1_bundle | 7 | 10 | 4 | 11 | 2 | 8 |
| status_epilepticus | 5 | 19 | 6 | 11 | 6 | 4 |
| toxicology_management | 6 | 9 | 0 | 25 | 14 | 11 |
| universal_clinical_safety | 3 | 5 | 0 | 9 | 3 | 5 |

## Detailed Rule Inventory

### aabb_transfusion (AABB 2024 RBC Transfusion Guidelines)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| TRANS-CARDIAC-LIBERAL-THRESHOLD | REQUIRED | HIGH | AABB 2024; MINT Trial, NEJM 2023 |
| TRANS-CARDIAC-LIBERAL-THRESHOLD-FORBIDDEN | FORBIDDEN | HIGH | AABB 2024; TRICC trial; restrictive threshold (Hb < 8) is pr... |
| TRANS-STABLE-NO-TRANSFUSE-ABOVE-7 | FORBIDDEN | HIGH | AABB 2024; TRICC Trial, Hebert 1999 NEJM |
| TRANS-TXA-WITHIN-3H | FORBIDDEN | CRITICAL | CRASH-2 Trial, Lancet 2010 - TXA >3h increases mortality |
| TRANS-JEHOVAH-NO-BLOOD | FORBIDDEN | CRITICAL | Patient autonomy; AABB ethical guidelines |
| TRANS-ANAPHYLAXIS-EPI | REQUIRED | CRITICAL | AABB 2024 Transfusion Reaction Management |
| TRANS-ANAPHYLAXIS-EPI-FORBIDDEN | FORBIDDEN | CRITICAL | AABB 2024; transfusion anaphylaxis requires immediate stop a... |

### aba_burn_resuscitation (ABA 2024 Burn Resuscitation Guidelines)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| BURN-PEDIATRIC-DEXTROSE | REQUIRED | HIGH | ABA 2024; ISBI Pediatric Burns Chapter |
| BURN-PEDIATRIC-DEXTROSE-FORBIDDEN | FORBIDDEN | HIGH | ABA Burn Guidelines 2023; pediatric patients have limited gl... |
| BURN-OVERRESUS-LIMIT | FORBIDDEN | HIGH | ABA 2024; Saffle JR, J Burn Care Res 2007 - fluid creep |
| BURN-CYANIDE-HYDROXOCOBALAMIN | REQUIRED | CRITICAL | ABA 2024; Baud FJ, NEJM 1991 |
| BURN-CYANIDE-HYDROXOCOBALAMIN-FORBIDDEN | FORBIDDEN | CRITICAL | ABA Burn Guidelines 2023; sodium nitrite induces methemoglob... |
| BURN-CHEST-ESCHAR-VENTILATION | REQUIRED | CRITICAL | ABA 2024; ISBI 2024 Escharotomy Chapter |
| BURN-CHEST-ESCHAR-VENTILATION-FORBIDDEN | FORBIDDEN | CRITICAL | ABA Burn Guidelines 2023; circumferential chest eschar cause... |

### acls_cardiac_arrest (AHA ACLS Cardiac Arrest Management)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| ACLS-SHOCKABLE-NO-ATROPINE | FORBIDDEN | HIGH | AHA ACLS 2025 Section 5.1; AHA removed atropine from ACLS al... |
| ACLS-SHOCKABLE-NO-CALCIUM-WITHOUT-INDICATION | FORBIDDEN | HIGH | AHA ACLS 2025 Section 6.2; calcium indicated only for hyperk... |
| ACLS-SHOCKABLE-NO-BICARB-ROUTINE | FORBIDDEN | HIGH | AHA ACLS 2025 Section 6.2; bicarbonate only for severe acido... |
| ACLS-SHOCKABLE-DEFIB-FIRST | BEFORE | CRITICAL | AHA 2025 Section 5.1; Kudenchuk PJ, NEJM 2016 |
| ACLS-SHOCKABLE-DEFIB-FIRST-FORBIDDEN | FORBIDDEN | CRITICAL | AHA ACLS 2020; defibrillation is the definitive treatment fo... |
| ACLS-HYPERKALEMIA-CALCIUM | REQUIRED | CRITICAL | AHA 2025 Section 6.2: Reversible Causes; Montague BT, Resusc... |
| ACLS-HYPERKALEMIA-CALCIUM-FORBIDDEN | FORBIDDEN | CRITICAL | AHA ACLS 2020; succinylcholine releases K+ from muscle; calc... |
| ACLS-HYPOTHERMIA-NO-DRUGS | FORBIDDEN | HIGH | AHA 2025 Section 6.4: Hypothermic Arrest; Brown DJA, NEJM 20... |
| ACLS-TENSION-PNEUMO-DECOMPRESS | REQUIRED | CRITICAL | AHA 2025 Section 6.2: Hs and Ts; Roberts DJ, Injury 2014 |
| ACLS-TENSION-PNEUMO-DECOMPRESS-FORBIDDEN | FORBIDDEN | CRITICAL | AHA ACLS 2020; tension pneumothorax in arrest requires immed... |
| ACLS-SHOCKABLE-NO-BICARB-ADDITIONAL | FORBIDDEN | HIGH | AHA ACLS 2020; routine sodium bicarbonate is not recommended... |
| ACLS-NONSHOCKABLE-NO-BICARB-ADDITIONAL | FORBIDDEN | HIGH | AHA ACLS 2020; routine bicarbonate not indicated in PEA/asys... |
| ACLS-NONSHOCKABLE-NO-ATROPINE | FORBIDDEN | HIGH | AHA ACLS 2025 Section 5.2; atropine removed from asystole/PE... |
| ACLS-NONSHOCKABLE-NO-DEFIB-ASYSTOLE | FORBIDDEN | HIGH | AHA ACLS 2025 Section 5.2; defibrillation has no role in asy... |
| ACLS-NONSHOCKABLE-NO-AMIODARONE-ASYSTOLE | FORBIDDEN | HIGH | AHA ACLS 2025 Section 5.2; amiodarone is an antiarrhythmic f... |
| ACLS-NONSHOCKABLE-NO-BICARB-ROUTINE | FORBIDDEN | HIGH | AHA ACLS 2025 Section 6.2; bicarbonate only for severe acido... |
| ACLS-NONSHOCKABLE-EPI-IMMEDIATE | REQUIRED | CRITICAL | AHA 2025 Section 5.2; Perkins GD, NEJM 2018 (PARAMEDIC2) |
| ACLS-TAMPONADE-PERICARDIOCENTESIS | REQUIRED | CRITICAL | AHA 2025 Section 6.2: Hs and Ts; Budhram GR, Acad Emerg Med ... |
| ACLS-TAMPONADE-PERICARDIOCENTESIS-FORBIDDEN | FORBIDDEN | CRITICAL | AHA ACLS 2020; cardiac tamponade in arrest requires immediat... |
| ACLS-OPIOID-NALOXONE | REQUIRED | HIGH | AHA 2025 Section 6.5: Opioid-Related Arrest; Panchal AR, Cir... |
| ACLS-OPIOID-NALOXONE-FORBIDDEN | FORBIDDEN | CRITICAL | AHA ACLS 2020; additional CNS depressants worsen arrest prog... |
| ACLS-PREGNANCY-PERIMORTEM-CSECTION | REQUIRED | CRITICAL | AHA 2025 Section 6.6: Cardiac Arrest in Pregnancy; Jeejeebho... |
| ACLS-PREGNANCY-PERIMORTEM-FORBIDDEN | FORBIDDEN | CRITICAL | AHA ACLS 2020; perimortem C-section within 4 min of arrest; ... |
| ACLS-POST-NO-EARLY-NEUROPROG | FORBIDDEN | HIGH | AHA ACLS 2025 Section 7; Sandroni C, Intensive Care Med 2014 |

### acog_obstetric_hemorrhage (ACOG 2024 Postpartum Hemorrhage Guidelines)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| OB-ASTHMA-NO-CARBOPROST | FORBIDDEN | CRITICAL | ACOG 2024; Carboprost package insert - bronchospasm contrain... |
| OB-HYPERTENSION-NO-METHYLERGONOVINE | FORBIDDEN | CRITICAL | ACOG 2024; Methylergonovine package insert - hypertension co... |
| OB-ASTHMA-AND-HTN-MISOPROSTOL-ONLY | REQUIRED | CRITICAL | ACOG 2024 - when carboprost AND methylergonovine both contra... |
| OB-TXA-WITHIN-3H-DELIVERY | FORBIDDEN | HIGH | WOMAN Trial, Lancet 2017 - TXA benefit only within 3h of del... |

### ada_dka_management (ADA Diabetic Ketoacidosis Management)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| DKA-EUGLY-SGLT2-DEXTROSE | REQUIRED | HIGH | ADA 2024, Section 16.2; FDA Safety Communication 2015 |
| DKA-EUGLY-SGLT2-DEXTROSE-FORBIDDEN | FORBIDDEN | HIGH | ADA DKA Guidelines 2024; SGLT2i causes euglycemic DKA; withh... |
| DKA-EUGLY-NO-DISCHARGE-NORMAL-GLU | FORBIDDEN | CRITICAL | ADA 2024; Peters AL et al, J Clin Endocrinol Metab 2015 |
| DKA-METFORMIN-STOP | REQUIRED | HIGH | ADA 2024; DeFronzo RA et al, Metformin-associated lactic aci... |
| DKA-METFORMIN-STOP-FORBIDDEN | FORBIDDEN | HIGH | ADA DKA Guidelines 2024; FDA Label; metformin in metabolic a... |
| DKA-PREGNANCY-MONITORING | REQUIRED | HIGH | ADA 2024; ACOG Practice Bulletin 2018 |
| DKA-PREGNANCY-NO-TERATOGEN | FORBIDDEN | CRITICAL | ADA 2024; ACOG 2018 |
| DKA-CKD-CAUTIOUS | FORBIDDEN | HIGH | ADA 2024; KDIGO AKI 2012 |
| DKA-ALCOHOLIC-KETOACIDOSIS | FORBIDDEN | HIGH | ADA 2024; McGuire LC, Emerg Med Clin 2006 |
| DKA-STEMI-OVERLAP | FORBIDDEN | HIGH | ADA 2024; AHA/ACC 2013 |
| DKA-INSULIN-BEFORE-K-CHECK | FORBIDDEN | CRITICAL | ADA 2024, Section 16.2 |
| DKA-HYPOK-INSULIN-GATE | FORBIDDEN | CRITICAL | ADA 2024, Section 16.2 |
| DKA-HYPERK-NO-K-REPLACE | FORBIDDEN | CRITICAL | ADA 2024, Section 16.2 |
| DKA-HYPOK-INSULIN-GATE-UNIQUE-FORBIDDEN | FORBIDDEN | CRITICAL | ADA DKA 2024 Section 16.2; insulin drives K+ intracellularly... |
| DKA-PEDIATRIC-NO-RAPID-FLUID | FORBIDDEN | CRITICAL | ISPAD 2022, Chapter 11; Glaser 2001 NEJM |
| DKA-PEDIATRIC-NO-BICARB | FORBIDDEN | HIGH | ISPAD 2022, Chapter 11 |
| DKA-PEDIATRIC-HYPOTONIC-FLUID | FORBIDDEN | CRITICAL | ISPAD 2022; Glaser NS, NEJM 2001 |

### aha_chest_pain_evaluation (AHA Chest Pain Evaluation)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| ACS-COCAINE-NO-BB | FORBIDDEN | CRITICAL | AHA/ACC 2014 NSTEMI Guidelines, Section 5.3.1 |
| ACS-LATE-NO-FIBRINOLYTIC | FORBIDDEN | HIGH | ESC 2023 ACS Guidelines; FTT Collaborative, Lancet 1994 |
| ACS-DISSECTION-NO-ANTICOAG | FORBIDDEN | CRITICAL | AHA/ACC 2022 Aortic Disease Guidelines, Section 7.2 |
| ACS-RV-INFARCT-NO-NITRATE | FORBIDDEN | CRITICAL | AHA/ACC 2013 STEMI Guidelines, Section 5.1 |
| ACS-ACTIVE-BLEED-NO-ANTICOAG | FORBIDDEN | CRITICAL | AHA/ACC 2013 STEMI Guidelines, Section 4.4 Bleeding Risk |
| ACS-ICH-NO-ANTICOAG | FORBIDDEN | CRITICAL | AHA/ACC 2013 STEMI Guidelines, Section 4.3 Absolute Contrain... |
| ACS-SILENT-MI-NO-DISCHARGE | FORBIDDEN | HIGH | AHA/ACC 2014; Zellweger MJ, Eur Heart J 2004 |
| ACS-CKD-ENOXAPARIN-ADJUST | FORBIDDEN | HIGH | AHA/ACC 2014; Spinler SA, Pharmacotherapy 2003 |
| ACS-ASPIRIN-ALLERGY-NO-ASPIRIN | FORBIDDEN | CRITICAL | AHA/ACC 2014 NSTEMI Guidelines |
| ACS-TICAGRELOR-CABG-WASHOUT | FORBIDDEN | HIGH | ACC/AHA 2016 Dual Antiplatelet Therapy; PLATO Trial |

### aha_heart_failure_2022 (AHA/ACC/HFSA Heart Failure Guideline)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| HF-HYPERK-NO-RAAS | FORBIDDEN | CRITICAL | AHA/ACC 2022 HF Guidelines, Section 7.3.2 |
| HF-NSAID-FORBIDDEN | REQUIRED | HIGH | AHA/ACC 2022 HF Guidelines, Class III (Harm) |
| HF-HYPERKALEMIA-NO-RAAS-VARIANT | FORBIDDEN | CRITICAL | AHA/ACC 2022 HF Guidelines, Section 7.3.2 |
| HF-NSAID-SPECIFIC-DRUGS | FORBIDDEN | HIGH | AHA/ACC 2022 HF Guidelines, Class III (Harm) |
| HF-OVERDIURESIS-VARIANT | FORBIDDEN | HIGH | AHA/ACC 2022 HF Guidelines, Section 10.2 |
| HF-OVERDIURESIS-HYPOVOLEMIA-SPECIFIC | FORBIDDEN | HIGH | AHA HF 2022; over-diuresis in cardiorenal syndrome worsens r... |
| HF-BRADYCARDIA-NO-BB-INCREASE | FORBIDDEN | HIGH | AHA/ACC 2022 HF Guidelines, Section 7.3.1 |
| HF-ACUTE-PULMONARY-EDEMA-NO-BB | FORBIDDEN | CRITICAL | AHA/ACC 2022 HF Guidelines, Section 10.1 |
| HF-OVERDIURESIS-STOP | FORBIDDEN | HIGH | AHA/ACC 2022 HF Guidelines, Section 10.2; Testani JM, JACC 2... |

### aha_stroke_2019 (AHA/ASA Acute Ischemic Stroke Guideline)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| STROKE-BP-UNCONTROLLED-NO-TPA | FORBIDDEN | CRITICAL | AHA/ASA 2019 Acute Ischemic Stroke Guidelines, Section 3.5 |
| STROKE-SEIZURE-MIMIC-NO-TPA | FORBIDDEN | HIGH | AHA/ASA 2019, Section 3.4 Stroke Mimics |
| STROKE-POSTERIOR-NO-DISCHARGE-LOW-NIHSS | FORBIDDEN | HIGH | AHA/ASA 2019, Section 3.6 Posterior Circulation Stroke |
| STROKE-TPA-HEPARIN-TIMING | FORBIDDEN | CRITICAL | AHA/ASA 2019, Section 3.5; NINDS tPA Protocol |
| STROKE-EXTENDED-WINDOW-NO-TPA | FORBIDDEN | CRITICAL | AHA/ASA 2019, Section 3.3 |
| STROKE-WARFARIN-PCC-PREFERRED | FORBIDDEN | HIGH | AHA/ASA 2022 ICH Guidelines, Section 5.2; Steiner T, Stroke ... |
| STROKE-PREGNANCY-NO-ACEI | FORBIDDEN | CRITICAL | ACOG 2020; AHA/ASA 2019 Secondary Prevention |

### anaphylaxis_management (WAO/EAACI Anaphylaxis Management)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| ANA-BETA-BLOCKER-GLUCAGON | REQUIRED | HIGH | WAO 2024 Section 4.3; EAACI 2024 Section 5.2 |
| ANA-BETA-BLOCKER-GLUCAGON-FORBIDDEN | FORBIDDEN | HIGH | WAO 2024 Section 4.3; EAACI 2024 Section 5.2; beta-blocker p... |
| ANA-PREGNANCY-LEFT-LATERAL | REQUIRED | HIGH | WAO 2024 Section 6.1; EAACI 2024 Special Populations |
| ANA-PREGNANCY-LEFT-LATERAL-FORBIDDEN | FORBIDDEN | HIGH | WAO 2024 Section 6.1; supine positioning in pregnant patient... |
| ANA-ACE-INHIBITOR-ANGIOEDEMA | FORBIDDEN | CRITICAL | EAACI 2024 Section 5.4; Brown SGA, JACI 2004 |
| ANA-ASTHMA-SALBUTAMOL | REQUIRED | HIGH | WAO 2024 Section 4.5; EAACI 2024 Section 5.3 |
| ANA-ASTHMA-SALBUTAMOL-FORBIDDEN | FORBIDDEN | HIGH | WAO 2024 Section 4.5; beta-blockers exacerbate bronchospasm;... |
| ANA-PEDIATRIC-DOSE | FORBIDDEN | CRITICAL | WAO 2024 Table 3; EAACI 2024 Pediatric Dosing |
| ANA-MASTOCYTOSIS-EXTENDED-OBS | REQUIRED | HIGH | WAO 2024 Section 6.3; Brockow K, JACI 2008 |
| ANA-MASTOCYTOSIS-EXTENDED-OBS-FORBIDDEN | FORBIDDEN | HIGH | WAO 2024 Section 6.3; Brockow K, JACI 2008; mastocytosis pat... |
| ANA-LATEX-ALLERGY-NO-LATEX | FORBIDDEN | CRITICAL | WAO 2024 Section 3.1; EAACI 2024 Allergen Avoidance |
| ANA-BIPHASIC-HIGH-RISK | REQUIRED | HIGH | WAO 2024 Section 5.2; Grunau BE, Ann Emerg Med 2015 |
| ANA-BIPHASIC-HIGH-RISK-FORBIDDEN | FORBIDDEN | HIGH | WAO 2024 Section 5.2; Grunau BE, Ann Emerg Med 2015; 10-20% ... |

### apa_agitation_management (APA 2024 Agitation Management Guidelines)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| PSYCH-ETOH-NO-BENZO-MONOTHERAPY | FORBIDDEN | CRITICAL | BETA Project 2012; Nobay F, Ann Emerg Med 2004 |
| PSYCH-QTC-NO-HALOPERIDOL | FORBIDDEN | CRITICAL | FDA Black Box Warning - haloperidol QT prolongation; APA 202... |
| PSYCH-PARKINSON-NO-TYPICAL-ANTIPSYCHOTIC | FORBIDDEN | CRITICAL | APA 2024; McKeith IG, Neurology 2005 - neuroleptic sensitivi... |
| PSYCH-OLANZAPINE-NO-BENZO-COMBO | FORBIDDEN | CRITICAL | Olanzapine IM package insert; FDA warning - respiratory depr... |
| PSYCH-NMS-DANTROLENE | REQUIRED | CRITICAL | APA 2024 NMS Guidelines; Strawn JR, CNS Drugs 2007 |
| PSYCH-NMS-DANTROLENE-FORBIDDEN | FORBIDDEN | CRITICAL | APA Practice Guidelines; NMS is caused by antipsychotic dopa... |
| PSYCH-SEROTONIN-CYPROHEPTADINE | REQUIRED | CRITICAL | Boyer EW, NEJM 2005; APA 2024 |
| PSYCH-SEROTONIN-CYPROHEPTADINE-FORBIDDEN | FORBIDDEN | CRITICAL | APA Practice Guidelines; Boyer EW, NEJM 2005; serotonergic a... |

### atrial_fibrillation (AHA/ACC/HRS 2023 Atrial Fibrillation)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| AF-WPW-NO-AV-BLOCKER | FORBIDDEN | CRITICAL | AHA/ACC/HRS 2023 AF Guidelines, Section 7.3.4.1 |
| AF-SEVERE-CKD-NO-DOAC | FORBIDDEN | HIGH | AHA/ACC/HRS 2023 AF Guidelines, Section 5.1.3 |
| AF-MECHANICAL-VALVE-NO-DOAC | FORBIDDEN | CRITICAL | AHA/ACC/HRS 2023 AF Guidelines; RE-ALIGN Trial |
| AF-ANTICOAG-REQUIRES-CHADSVASC | FORBIDDEN | HIGH | AHA/ACC/HRS 2023 AF Guidelines, Section 5.1 |
| AF-AMIODARONE-THYROID-VARIANT | FORBIDDEN | HIGH | AHA/ACC/HRS 2023; Bogazzi F, Thyroid 2012 |
| AF-CARDIOVERSION-ANTICOAG-GATE | FORBIDDEN | CRITICAL | AHA/ACC/HRS 2023 AF Guidelines, Section 6.2 |
| AF-AMIODARONE-THYROID-CHECK | FORBIDDEN | HIGH | AHA/ACC/HRS 2023 AF Guidelines; Bogazzi F, Thyroid 2012 |

### cap_pneumonia (IDSA/ATS Community-Acquired Pneumonia 2019)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| CAP-PENICILLIN-ALLERGY-ALT | FORBIDDEN | CRITICAL | ATS/IDSA CAP 2019, Section 4.2 |
| CAP-QT-NO-FLUOROQUINOLONE | FORBIDDEN | HIGH | ATS/IDSA CAP 2019; FDA Black Box Warning |
| CAP-SEVERE-ICU-DUAL-THERAPY | REQUIRED | HIGH | ATS/IDSA CAP 2019, Section 5.1 |
| CAP-MRSA-RISK-COVERAGE | REQUIRED | HIGH | ATS/IDSA CAP 2019, Section 5.3 |
| CAP-MRSA-RISK-COVERAGE-FORBIDDEN | FORBIDDEN | HIGH | ATS/IDSA CAP 2019; MRSA CAP has 30-40% mortality without app... |
| CAP-PSEUDOMONAS-RISK-COVERAGE | REQUIRED | HIGH | ATS/IDSA CAP 2019, Section 5.2 |
| CAP-PSEUDOMONAS-RISK-COVERAGE-FORBIDDEN | FORBIDDEN | HIGH | ATS/IDSA CAP 2019; Pseudomonas CAP requires antipseudomonal ... |
| CAP-IMMUNOCOMPROMISED-BROAD | FORBIDDEN | HIGH | ATS/IDSA CAP 2019, Section 6; IDSA Immunocompromised Host 20... |
| CAP-ASPIRATION-ANAEROBE | REQUIRED | MODERATE | ATS/IDSA CAP 2019, Section 5.4 |
| CAP-ASPIRATION-ANAEROBE-FORBIDDEN | FORBIDDEN | HIGH | ATS/IDSA CAP 2019; aspiration pneumonia involves polymicrobi... |
| CAP-COVID-STEROID-TIMING | FORBIDDEN | HIGH | RECOVERY Trial; WHO COVID-19 Therapeutics 2022 |
| CAP-SEVERE-ICU-ADMISSION | REQUIRED | CRITICAL | ATS/IDSA CAP 2019, Section 5.1 |
| CAP-SEVERE-ICU-ADMISSION-FORBIDDEN | FORBIDDEN | HIGH | ATS/IDSA CAP 2019; severe CAP (PaO2/FiO2 < 250, multilobar, ... |

### copd_exacerbation (GOLD 2024 COPD Exacerbation Management)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| COPD-PNEUMOTHORAX-NO-NIV | FORBIDDEN | CRITICAL | GOLD COPD 2024, Section 5.3 |
| COPD-CO2-NARCOSIS-NO-HIGH-O2 | FORBIDDEN | HIGH | GOLD COPD 2024; Austin MA, BMJ 2010 |
| COPD-FACIAL-TRAUMA-NO-NIV | FORBIDDEN | HIGH | GOLD COPD 2024; BTS NIV Guidelines |
| COPD-BB-CONTRAINDICATED | FORBIDDEN | HIGH | GOLD COPD 2024; Salpeter SR, Cochrane 2005 |
| COPD-THEOPHYLLINE-CAUTION | FORBIDDEN | MODERATE | GOLD COPD 2024; Drug interaction databases |
| COPD-COR-PULMONALE-FLUID-RESTRICT | FORBIDDEN | HIGH | GOLD COPD 2024; AHA HF Guidelines 2022 |
| COPD-CHF-OVERLAP-NO-BB-INCREASE | FORBIDDEN | HIGH | GOLD COPD 2024; Bhatt SP, NEJM 2023 |
| COPD-AKI-STEROID-CAUTION | FORBIDDEN | HIGH | GOLD COPD 2024; KDIGO AKI 2012 |

### gi_bleeding (ACG 2021 GI Bleeding Management)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| GIB-VARICEAL-NO-NSAID | FORBIDDEN | CRITICAL | ACG GI Bleeding 2023; Baveno VII 2022 |
| GIB-HEMODYNAMIC-INSTABILITY-RESUSCITATE | REQUIRED | CRITICAL | ACG GI Bleeding 2023, Section 3.1 |
| GIB-HEMODYNAMIC-INSTABILITY-RESUSCITATE-FORBIDDEN | FORBIDDEN | HIGH | ACG GI Bleeding 2023; hemodynamic resuscitation takes priori... |
| GIB-ANTICOAG-REVERSAL | REQUIRED | HIGH | ACG GI Bleeding 2023; AGA 2020 |
| GIB-VARICEAL-OCTREOTIDE | REQUIRED | HIGH | Baveno VII 2022; ACG GI Bleeding 2023 |
| GIB-PLATELET-TRANSFUSE | REQUIRED | HIGH | ACG GI Bleeding 2023 |
| GIB-PLATELET-TRANSFUSE-FORBIDDEN | FORBIDDEN | HIGH | ACG GI Bleeding 2023; platelet count < 50k with active bleed... |
| GIB-MECHANICAL-VALVE-ANTICOAG | FORBIDDEN | CRITICAL | ACG GI Bleeding 2023; AHA/ACC Valve 2020 |
| GIB-NSAID-PPI-FAILURE | FORBIDDEN | HIGH | ACG GI Bleeding 2023; Lanza FL, Am J Gastroenterol 2009 |
| GIB-UNSTABLE-RESUSCITATE-FIRST | FORBIDDEN | CRITICAL | ACG GI Bleeding 2023, Section 3.1 |

### gina_asthma_exacerbation (GINA Asthma Exacerbation Management)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| ASTHMA-INITIAL-NO-MUCOLYTICS | FORBIDDEN | HIGH | GINA 2024 Section 4.3; mucolytics may worsen bronchospasm in... |
| ASTHMA-INITIAL-NO-MUCOLYTICS-SPECIFIC | FORBIDDEN | HIGH | GINA 2024 Section 4.3; mucolytics worsen bronchospasm in acu... |
| ASTHMA-MILD-NO-PHYSIO-SPECIFIC | FORBIDDEN | HIGH | GINA 2024 Section 4.3; chest physiotherapy increases oxygen ... |
| ASTHMA-SEVERE-NO-ROUTINE-ABX-SPECIFIC | FORBIDDEN | MODERATE | GINA 2024 Section 4.3; antibiotics not indicated for asthma ... |
| ASTHMA-NO-THEOPHYLLINE-IN-ACUTE-SPECIFIC | FORBIDDEN | HIGH | GINA 2024 Section 4.3; theophylline/aminophylline not recomm... |
| ASTHMA-MILD-NO-MUCOLYTICS | FORBIDDEN | HIGH | GINA 2024 Section 4.3; mucolytics not recommended in acute a... |
| ASTHMA-MILD-NO-CHEST-PHYSIO | FORBIDDEN | HIGH | GINA 2024 Section 4.3; chest physiotherapy not recommended i... |
| ASTHMA-ASPIRIN-SENSITIVE-NO-NSAID | FORBIDDEN | CRITICAL | GINA 2024 Section 2.4; Stevenson DD, JACI 2003 |
| ASTHMA-STEROID-DEPENDENT-STRESS-DOSE | REQUIRED | HIGH | GINA 2024 Section 3.5; Chrousos GP, NEJM 1995 |
| ASTHMA-STEROID-DEPENDENT-STRESS-DOSE-FORBIDDEN | FORBIDDEN | HIGH | GINA 2024; steroid-dependent patients have adrenal suppressi... |
| ASTHMA-SEVERE-NO-MUCOLYTICS | FORBIDDEN | HIGH | GINA 2024 Section 4.3; mucolytics contraindicated in severe ... |
| ASTHMA-SEVERE-NO-CHEST-PHYSIO | FORBIDDEN | HIGH | GINA 2024 Section 4.3; chest physiotherapy contraindicated i... |
| ASTHMA-SEVERE-NO-THEOPHYLLINE | FORBIDDEN | HIGH | GINA 2024 Section 4.3; theophylline not recommended in acute... |
| ASTHMA-SEVERE-NO-ANTIBIOTICS-ROUTINE | FORBIDDEN | MODERATE | GINA 2024 Section 4.3; antibiotics not routinely indicated f... |
| ASTHMA-SEVERE-MGSO4 | REQUIRED | HIGH | GINA 2024 Section 4.3; Kew KM, Cochrane 2014 |
| ASTHMA-SEVERE-MGSO4-FORBIDDEN | FORBIDDEN | HIGH | GINA 2024; severe/life-threatening exacerbation requires IV ... |
| ASTHMA-PNEUMOTHORAX-NO-POSITIVE-PRESSURE | FORBIDDEN | CRITICAL | GINA 2024 Section 4.3; BTS 2015 Spontaneous Pneumothorax Gui... |
| ASTHMA-CONCURRENT-INFECTION-ABX | REQUIRED | MODERATE | GINA 2024 Section 4.3; NICE NG80 2017 |
| ASTHMA-CONCURRENT-INFECTION-ABX-FORBIDDEN | FORBIDDEN | HIGH | GINA 2024; routine antibiotics for asthma exacerbation are n... |
| ASTHMA-NEARFATAL-NO-MUCOLYTICS | FORBIDDEN | HIGH | GINA 2024 Section 4.3; mucolytics contraindicated in near-fa... |
| ASTHMA-NEARFATAL-NO-SUCCINYLCHOLINE-HYPERKALEMIC | FORBIDDEN | HIGH | GINA 2024 Section 4.3; succinylcholine may worsen hyperkalem... |
| ASTHMA-NEAR-FATAL-EPINEPHRINE | REQUIRED | CRITICAL | GINA 2024 Section 4.3; BTS/SIGN 2019 Asthma Guidelines |
| ASTHMA-INTUBATED-KETAMINE-PREFERRED | REQUIRED | HIGH | GINA 2024 Section 4.3; Goyal S, Indian J Crit Care Med 2014 |
| ASTHMA-PREGNANCY-NO-DEHYDRATION | FORBIDDEN | HIGH | GINA 2024 Section 5.6; Murphy VE, Respirology 2015 |

### hypertensive_emergency (AHA/ACC 2017 Hypertension - Emergency Management)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| HTN-AORTIC-DISSECTION-BB-FIRST | BEFORE | CRITICAL | AHA 2017 Hypertensive Crisis; ESC Aortic Disease 2014 |
| HTN-ECLAMPSIA-MAGNESIUM | REQUIRED | CRITICAL | ACOG 2020; AHA 2017 Hypertensive Crisis |
| HTN-ECLAMPSIA-MAGNESIUM-FORBIDDEN | FORBIDDEN | CRITICAL | ACOG 2020; ACE inhibitors are teratogenic; nitroprusside cau... |
| HTN-ECLAMPSIA-NO-ACEI | FORBIDDEN | CRITICAL | ACOG 2020; FDA Pregnancy Category X |
| HTN-PHEOCHROMOCYTOMA-NO-BB-ALONE | FORBIDDEN | CRITICAL | Endocrine Society 2014; AHA 2017 |
| HTN-ACS-NO-RAPID-DROP | FORBIDDEN | HIGH | AHA 2017; ESC ACS Guidelines |
| HTN-ECLAMPSIA-NO-ACEI-EXPANDED | FORBIDDEN | CRITICAL | ACOG 2020; FDA Pregnancy Category X |
| HTN-PHEOCHROMOCYTOMA-NO-BB-EXPANDED | FORBIDDEN | CRITICAL | Endocrine Society 2014; AHA 2017 |
| HTN-AORTIC-DISSECTION-NO-THROMBOLYSIS | FORBIDDEN | CRITICAL | AHA 2017; ESC Aortic Disease 2014 |
| HTN-AKI-NO-AGGRESSIVE-BP | FORBIDDEN | HIGH | AHA 2017; JNC 8 |

### idsa_meningitis (IDSA Bacterial Meningitis Management)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| MENING-INITIAL-NO-DELAY-ABX-FOR-LP | FORBIDDEN | CRITICAL | IDSA 2024 Section 2; Proulx N, QJM 2005 |
| MENING-INITIAL-NO-DELAY-ABX-FOR-CT | FORBIDDEN | CRITICAL | IDSA 2024 Section 2; Hasbun R, NEJM 2001 |
| MENING-EMPIRIC-NO-DELAY-FOR-LP | FORBIDDEN | CRITICAL | IDSA 2024 Section 3; Proulx N, QJM 2005 |
| MENING-EMPIRIC-NO-DELAY-FOR-CT | FORBIDDEN | CRITICAL | IDSA 2024 Section 3; Hasbun R, NEJM 2001 |
| MENING-EMPIRIC-NO-ORAL-ONLY | FORBIDDEN | HIGH | IDSA 2024 Section 3; IV antibiotics required for CNS penetra... |
| MENING-ABX-BEFORE-LP | FORBIDDEN | CRITICAL | IDSA 2024 Section 3.1; Proulx N, QJM 2005 |
| MENING-IMMUNOCOMP-LISTERIA | REQUIRED | HIGH | IDSA 2024 Table 3; Brouwer MC, NEJM 2006 |
| MENING-IMMUNOCOMP-LISTERIA-FORBIDDEN | FORBIDDEN | HIGH | IDSA Meningitis 2004; Listeria requires ampicillin; cephalos... |
| MENING-PENICILLIN-ALLERGY | FORBIDDEN | CRITICAL | IDSA 2024 Table 4; Tunkel AR, CID 2004 |
| MENING-NEONATE-COVERAGE | REQUIRED | CRITICAL | IDSA 2024 Table 3; AAP Red Book 2024 |
| MENING-NEONATE-COVERAGE-FORBIDDEN | FORBIDDEN | CRITICAL | IDSA Meningitis 2004; neonatal meningitis requires ampicilli... |
| MENING-HSV-ENCEPHALITIS | REQUIRED | CRITICAL | IDSA 2024 Section 3.4; Whitley RJ, NEJM 1986 |
| MENING-HSV-ENCEPHALITIS-FORBIDDEN | FORBIDDEN | CRITICAL | IDSA Meningitis 2004; Whitley RJ, NEJM 1986; untreated HSV e... |
| MENING-DEXA-NO-AFTER-ABX | FORBIDDEN | HIGH | IDSA 2024 Section 4; de Gans J, NEJM 2002 |
| MENING-DEXA-NO-ORAL | FORBIDDEN | HIGH | IDSA 2024 Section 4; IV route required for meningitis dosing |
| MENING-DEXA-BEFORE-ABX | BEFORE | HIGH | IDSA 2024 Section 4.1; de Gans J, NEJM 2002 |
| MENING-DEXAMETHASONE-TIMING | REQUIRED | HIGH | IDSA 2024 Section 4.1; van de Beek D, Lancet Neurol 2012 |
| MENING-DEXAMETHASONE-TIMING-FORBIDDEN | FORBIDDEN | HIGH | IDSA Meningitis 2004; de Gans J, NEJM 2002; dexamethasone mu... |
| MENING-LP-NO-WITHOUT-CT-CONTRAINDICATED | FORBIDDEN | CRITICAL | IDSA 2024 Section 5; Hasbun R, NEJM 2001 |
| MENING-INCREASED-ICP-NO-LP | FORBIDDEN | CRITICAL | IDSA 2024 Section 5.2; Hasbun R, NEJM 2001 |

### kdigo_aki_full (KDIGO AKI 2012 Full)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| AKI-NSAID-STOP | REQUIRED | HIGH | KDIGO AKI 2012, Section 3.1.1 |
| AKI-NSAID-STOP-FORBIDDEN | FORBIDDEN | HIGH | KDIGO AKI 2012, Section 3.1.1; NSAIDs/COX-2 inhibitors cause... |
| AKI-ACEI-HOLD | REQUIRED | HIGH | KDIGO AKI 2012, Section 3.1.2 |
| AKI-ACEI-HOLD-FORBIDDEN | FORBIDDEN | HIGH | KDIGO AKI 2012, Section 3.1.2; RAAS inhibitors reduce effere... |
| AKI-HYPERKALEMIA-URGENT | REQUIRED | CRITICAL | KDIGO AKI 2012; AHA Hyperkalemia Guidelines |
| AKI-HYPERKALEMIA-URGENT-FORBIDDEN | FORBIDDEN | CRITICAL | KDIGO AKI 2012; AHA Hyperkalemia Guidelines; potassium-spari... |
| AKI-METFORMIN-HOLD | REQUIRED | HIGH | KDIGO AKI 2012; FDA Label |
| AKI-METFORMIN-HOLD-FORBIDDEN | FORBIDDEN | HIGH | KDIGO AKI 2012; FDA Black Box Warning; metformin accumulatio... |
| AKI-RHABDO-BICARB-FLUID | REQUIRED | HIGH | KDIGO AKI 2012; Bosch X, NEJM 2009 |
| AKI-HEPATORENAL-ALBUMIN | REQUIRED | HIGH | KDIGO AKI 2012; EASL Hepatorenal 2018 |
| AKI-HEPATORENAL-ALBUMIN-FORBIDDEN | FORBIDDEN | HIGH | KDIGO AKI 2012; EASL Hepatorenal 2018; nephrotoxins compound... |
| AKI-RHABDO-NO-LR | FORBIDDEN | HIGH | KDIGO AKI 2012; Bosch X, NEJM 2009 |
| AKI-HYPERKALEMIA-NO-ACE-MRA | FORBIDDEN | CRITICAL | KDIGO AKI 2012; AHA Hyperkalemia Guidelines |
| AKI-HYPERKALEMIA-NO-SUCCINYLCHOLINE | FORBIDDEN | CRITICAL | KDIGO AKI 2012; ASA Anesthesia Guidelines |
| AKI-STAGE1-AMINOGLYCOSIDE-SPECIFIC | FORBIDDEN | HIGH | KDIGO AKI 2012 Section 3.1; aminoglycosides without TDM in A... |
| AKI-STAGE2-CONTRAST-SPECIFIC | FORBIDDEN | HIGH | KDIGO AKI 2012 Section 3.2; contrast in AKI Stage 2 without ... |
| AKI-STAGE2-K-SUPPLEMENT-SPECIFIC | FORBIDDEN | CRITICAL | KDIGO AKI 2012 Section 3.2; potassium supplementation with K... |
| AKI-HYPERKALEMIA-NO-SUCCINYLCHOLINE-SPECIFIC | FORBIDDEN | CRITICAL | KDIGO AKI 2012; ASA Guidelines; succinylcholine releases 0.5... |
| AKI-STAGE1-NO-AMINOGLYCOSIDE-UNMONITORED | FORBIDDEN | HIGH | KDIGO AKI 2012 Section 3.1; aminoglycosides are nephrotoxic ... |
| AKI-STAGE2-NO-CONTRAST-UNPREPPED | FORBIDDEN | HIGH | KDIGO AKI 2012 Section 3.2; contrast without preparation in ... |
| AKI-STAGE2-NO-POTASSIUM-IF-HYPERKALEMIA | FORBIDDEN | CRITICAL | KDIGO AKI 2012 Section 3.2; potassium supplementation in hyp... |
| AKI-STAGE3-NO-CONTRAST | FORBIDDEN | CRITICAL | KDIGO AKI 2012 Section 3.3; contrast is nephrotoxic in sever... |
| AKI-STAGE3-NO-POTASSIUM | FORBIDDEN | CRITICAL | KDIGO AKI 2012 Section 3.3; potassium supplementation in hyp... |
| AKI-STAGE3-NO-MAGNESIUM-ANTACIDS | FORBIDDEN | HIGH | KDIGO AKI 2012 Section 3.3; magnesium accumulates in severe ... |

### kdigo_contrast_aki (KDIGO Contrast-Associated AKI Prevention)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| CAKI-METFORMIN-HOLD-48H | REQUIRED | HIGH | KDIGO Contrast AKI; ACR Manual on Contrast Media 2024 |
| CAKI-METFORMIN-HOLD-48H-FORBIDDEN | FORBIDDEN | HIGH | KDIGO Contrast AKI 2012; ACR Contrast Manual 2023; metformin... |
| CAKI-HIGH-RISK-PREHYDRATE | REQUIRED | HIGH | KDIGO Contrast AKI; Mehran R, JACC 2004 |
| CAKI-HIGH-RISK-PREHYDRATE-FORBIDDEN | FORBIDDEN | HIGH | KDIGO Contrast AKI 2012; high-osmolar contrast increases nep... |
| CAKI-GADOLINIUM-NO-IN-CKD | FORBIDDEN | CRITICAL | ACR Manual on Contrast Media 2024; FDA NSF Warning |
| CAKI-DIALYSIS-NO-DELAY | REQUIRED | MODERATE | KDIGO Contrast AKI 2012 |
| CAKI-NSAID-AVOID | FORBIDDEN | HIGH | KDIGO Contrast AKI 2012 |
| CAKI-CKD-PREP-REQUIRED | FORBIDDEN | HIGH | KDIGO Contrast AKI 2024; ACR Manual on Contrast Media |
| CAKI-AMINOGLYCOSIDE-AVOID | FORBIDDEN | HIGH | KDIGO Contrast AKI 2012; Lopez-Novoa JM, Kidney Int 2011 |
| CAKI-SPECIFIC-NEPHROTOXIN-HOLD | REQUIRED | HIGH | KDIGO Contrast AKI 2012; ACR Manual on Contrast Media 2024 |
| CAKI-SPECIFIC-NEPHROTOXIN-HOLD-FORBIDDEN | FORBIDDEN | HIGH | KDIGO Contrast AKI 2012; concurrent nephrotoxins with contra... |
| CAKI-GADOLINIUM-GFR30-SPECIFIC | FORBIDDEN | CRITICAL | KDIGO Contrast AKI 2012; ACR 2023; gadolinium in eGFR < 30 c... |
| CAKI-CKD-PREP-SPECIFIC | FORBIDDEN | HIGH | KDIGO Contrast AKI 2012; CKD + diabetes doubles contrast nep... |
| CAKI-HIGH-NO-CONTRAST-WITHOUT-HYDRATION | FORBIDDEN | HIGH | KDIGO 2024 CKD Section 4.3.2; pre-hydration mandatory in eGF... |
| CAKI-HIGH-NO-REPEAT-CONTRAST | FORBIDDEN | HIGH | KDIGO 2024 CKD Section 4.3.2; repeated contrast within 48h m... |
| CAKI-HIGH-NO-NSAIDS | FORBIDDEN | HIGH | KDIGO 2024 CKD; NSAIDs synergize with contrast nephrotoxicit... |
| CAKI-HIGH-NO-AMINOGLYCOSIDES | FORBIDDEN | HIGH | KDIGO 2024 CKD; aminoglycosides synergize with contrast neph... |
| CAKI-MOD-NO-CONTRAST-WITHOUT-HYDRATION | FORBIDDEN | HIGH | KDIGO 2024 CKD Section 4.3.2; hydration required in CKD G3 |
| CAKI-MOD-NO-REPEAT-CONTRAST | FORBIDDEN | HIGH | KDIGO 2024 CKD Section 4.3.2; repeated contrast in CKD G3 mu... |

### pals_pediatric_emergency (AHA PALS 2025 Pediatric Emergency Guidelines)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| PEDS-DKA-SLOW-FLUID | FORBIDDEN | CRITICAL | ISPAD 2022; AHA PALS 2025 - cerebral edema risk in pediatric... |
| PEDS-CARDIAC-LIMIT-FLUID | FORBIDDEN | HIGH | AHA PALS 2025; Pediatric Cardiology Guidelines |
| PEDS-FEBRILE-SEIZURE-NO-AED | FORBIDDEN | HIGH | AAP 2011 Febrile Seizure Practice Parameter (reaffirmed 2023... |
| PEDS-NEONATE-SEIZURE-PHENOBARB | REQUIRED | HIGH | AHA PALS 2025; Neonatal seizure management - phenobarbital p... |
| PEDS-NEONATE-SEIZURE-PHENOBARB-FORBIDDEN | FORBIDDEN | CRITICAL | AHA PALS 2020; neonates require phenobarbital as first-line;... |

### pulmonary_embolism (ESC 2019 Pulmonary Embolism)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| PE-MASSIVE-THROMBOLYSIS | REQUIRED | CRITICAL | ESC PE 2019, Section 6.2 |
| PE-MASSIVE-THROMBOLYSIS-FORBIDDEN | FORBIDDEN | CRITICAL | ESC PE 2019; massive PE with hemodynamic collapse requires t... |
| PE-HIT-NO-HEPARIN | FORBIDDEN | CRITICAL | ESC PE 2019; ASH HIT Guidelines 2018 |
| PE-OBESITY-NO-STANDARD-DOAC | FORBIDDEN | HIGH | ISTH 2021; Martin KA, J Thromb Haemost 2021 |
| PE-PREGNANCY-NO-WARFARIN | FORBIDDEN | CRITICAL | ESC PE 2019; ACOG Practice Bulletin |
| PE-RENAL-ENOXAPARIN-ADJUST | FORBIDDEN | HIGH | ESC PE 2019; Lim W, CHEST 2006 |
| PE-ACTIVE-BLEED-NO-THROMBOLYSIS | FORBIDDEN | CRITICAL | ESC PE 2019, Section 6.2 Absolute Contraindications |
| PE-PREGNANCY-IMAGING | FORBIDDEN | HIGH | ESC PE 2019; ACOG Practice Bulletin 2018 |
| PE-MORBID-OBESITY-DOAC-CAUTION | FORBIDDEN | HIGH | ISTH 2021; Martin KA, J Thromb Haemost 2021 |
| PE-RECENT-SURGERY-NO-THROMBOLYSIS | FORBIDDEN | HIGH | ESC PE 2019, Section 6.2 Relative Contraindications |

### ssc_sepsis_hour1_bundle (Surviving Sepsis Campaign Hour-1 Bundle)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| SEPSIS-PENICILLIN-ANAPHYLAXIS-NO-CEPH | FORBIDDEN | CRITICAL | SSC 2021; IDSA Cross-Reactivity Guidance |
| SEPSIS-HF-CAUTIOUS-FLUID | FORBIDDEN | HIGH | SSC 2021; Maitland et al, FEAST Trial 2011 |
| SEPSIS-CIRRHOSIS-NO-LACTATED-RINGER | FORBIDDEN | MODERATE | SSC 2021; Myburgh JA, Finfer S, SAFE Study Investigators |
| SEPSIS-ADRENAL-INSUFFICIENCY-STEROIDS | REQUIRED | HIGH | SSC 2021, Section: Corticosteroids |
| SEPSIS-ADRENAL-INSUFFICIENCY-STEROIDS-FORBIDDEN | FORBIDDEN | HIGH | SSC 2021; stress-dose hydrocortisone (200mg/day) for refract... |
| SEPSIS-ESRD-NO-FLUID-BOLUS | FORBIDDEN | HIGH | SSC 2021; Silversides JA, Intensive Care Med 2017 |
| SEPSIS-NEUTROPENIC-BROAD-SPECTRUM | FORBIDDEN | CRITICAL | IDSA Febrile Neutropenia 2010; SSC 2021 |
| SEPSIS-ELDERLY-AFEBRILE-NO-DISMISS | FORBIDDEN | HIGH | SSC 2021; Nasa P, Crit Care 2012 |
| SEPSIS-HF-NO-AGGRESSIVE-FLUID-VARIANT | FORBIDDEN | HIGH | SSC 2021; Boyd JH, Chest 2011 |
| SEPSIS-CKD-NO-NEPHROTOXINS | FORBIDDEN | HIGH | KDIGO AKI 2012; SSC 2021 |
| SEPSIS-VANCOMYCIN-RED-MAN | FORBIDDEN | HIGH | Red Man Syndrome; Sivagnanam S, Crit Care 2003 |

### status_epilepticus (AES Status Epilepticus Management)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| SE-HYPOGLYCEMIA-GLUCOSE-FIRST | BEFORE | CRITICAL | AES 2024 Section 2.2; Alldredge BK, NEJM 2001 |
| SE-HYPOGLYCEMIA-GLUCOSE-FIRST-FORBIDDEN | FORBIDDEN | CRITICAL | NCS Status Epilepticus 2012; hypoglycemic seizures resolve w... |
| SE-KNOWN-EPILEPSY-CHECK-LEVELS | REQUIRED | MODERATE | AES 2024 Section 2.3; Trinka E, Epilepsia 2015 |
| SE-KNOWN-EPILEPSY-CHECK-LEVELS-FORBIDDEN | FORBIDDEN | HIGH | NCS Status Epilepticus 2012; subtherapeutic levels require o... |
| SE-ALCOHOL-WITHDRAWAL-BENZO | REQUIRED | HIGH | AES 2024 Section 3.3; Schuckit MA, NEJM 2014 |
| SE-ALCOHOL-WITHDRAWAL-BENZO-FORBIDDEN | FORBIDDEN | HIGH | NCS Status Epilepticus 2012; phenytoin is ineffective for al... |
| SE-PREGNANCY-NO-VALPROATE | FORBIDDEN | CRITICAL | AES 2024 Section 4.3; FDA Black Box Warning; Meador KJ, NEJM... |
| SE-HEPATIC-NO-VALPROATE | FORBIDDEN | CRITICAL | AES 2024 Section 4.3; FDA Black Box Warning |
| SE-ELDERLY-DOSE-REDUCE | FORBIDDEN | HIGH | AES 2024 Section 4.4; Treiman DM, NEJM 1998 |
| SE-CARDIAC-HISTORY-NO-PHENYTOIN | FORBIDDEN | CRITICAL | AES 2024 Section 4.5; Cranford RE, Neurology 1979 |
| SE-PORPHYRIA-NO-PHENYTOIN | FORBIDDEN | CRITICAL | AES 2024 Section 4.6; Anderson KE, Ann Intern Med 2005 |

### toxicology_management (AACT/ACMT Toxicology Management)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| TOX-IDENT-NO-DELAY-ANTIDOTE | FORBIDDEN | HIGH | AACT/ACMT 2024 Section 2; empiric antidote should not be wit... |
| TOX-NO-FORCED-DIURESIS-SPECIFIC | FORBIDDEN | HIGH | AACT/ACMT 2024 Section 5; forced diuresis is ineffective and... |
| TOX-ANTIDOTE-NO-DELAY | FORBIDDEN | HIGH | AACT/ACMT 2024 Section 3; antidote delay increases morbidity... |
| TOX-CHARCOAL-AFTER-ENDOSCOPY | FORBIDDEN | HIGH | AACT/ACMT 2024 Section 4; charcoal after endoscopy impairs v... |
| TOX-ACETAMINOPHEN-NAC | REQUIRED | CRITICAL | AACT/ACMT 2024 Section 3.1; Smilkstein MJ, NEJM 1988 |
| TOX-ACETAMINOPHEN-NAC-FORBIDDEN | FORBIDDEN | CRITICAL | AACT/ACMT 2024 Section 3.1; NAC must not be delayed waiting ... |
| TOX-BENZO-NO-FLUMAZENIL-CHRONIC | FORBIDDEN | CRITICAL | AACT/ACMT 2024 Section 3.2; Haverkos GP, Clin Pharm 1994 |
| TOX-OPIOID-NALOXONE | REQUIRED | CRITICAL | AACT/ACMT 2024 Section 3.3; Boyer EW, NEJM 2012 |
| TOX-OPIOID-NALOXONE-FORBIDDEN | FORBIDDEN | CRITICAL | AACT/ACMT 2024 Section 3.3; Boyer EW, NEJM 2012; additional ... |
| TOX-TCA-NO-PHYSOSTIGMINE | FORBIDDEN | CRITICAL | AACT/ACMT 2024 Section 3.4; Pentel P, Ann Emerg Med 1980 |
| TOX-TCA-BICARB | REQUIRED | CRITICAL | AACT/ACMT 2024 Section 3.4; Liebelt EL, J Toxicol Clin Toxic... |
| TOX-METHANOL-FOMEPIZOLE | REQUIRED | CRITICAL | AACT/ACMT 2024 Section 3.5; Brent J, NEJM 2001 |
| TOX-METHANOL-FOMEPIZOLE-FORBIDDEN | FORBIDDEN | CRITICAL | AACT/ACMT 2024 Section 3.5; Brent J, NEJM 2001; fomepizole d... |
| TOX-DIGOXIN-FAB | REQUIRED | CRITICAL | AACT/ACMT 2024 Section 3.6; Antman EM, Circulation 1990 |
| TOX-DIGOXIN-FAB-FORBIDDEN | FORBIDDEN | CRITICAL | AACT/ACMT 2024 Section 3.6; Antman EM, Circulation 1990; cal... |
| TOX-ORGANOPHOSPHATE-ATROPINE | REQUIRED | CRITICAL | AACT/ACMT 2024 Section 3.7; Eddleston M, Lancet 2008 |
| TOX-ORGANOPHOSPHATE-ATROPINE-FORBIDDEN | FORBIDDEN | CRITICAL | AACT/ACMT 2024 Section 3.7; Eddleston M, Lancet 2008; OP inh... |
| TOX-BETA-BLOCKER-GLUCAGON | REQUIRED | HIGH | AACT/ACMT 2024 Section 3.8; Love JN, J Toxicol Clin Toxicol ... |
| TOX-BETA-BLOCKER-GLUCAGON-FORBIDDEN | FORBIDDEN | HIGH | AACT/ACMT 2024 Section 3.8; Love JN, J Toxicol Clin Toxicol ... |
| TOX-CALCIUM-CHANNEL-BLOCKER-INSULIN | REQUIRED | HIGH | AACT/ACMT 2024 Section 3.9; Engebretsen KM, Clin Toxicol 201... |
| TOX-CALCIUM-CHANNEL-BLOCKER-INSULIN-FORBIDDEN | FORBIDDEN | HIGH | AACT/ACMT 2024 Section 3.9; Engebretsen KM, Clin Toxicol 201... |
| TOX-CAUSTIC-NO-CHARCOAL | FORBIDDEN | CRITICAL | AACT Position Statement; Hojer J, Clin Toxicol 2013 |
| TOX-HYDROCARBON-NO-CHARCOAL | FORBIDDEN | HIGH | AACT Position Statement; Isbister GK, Med J Aust 2004 |
| TOX-OBSTRUCTION-NO-WBI | FORBIDDEN | HIGH | AACT Position Statement on WBI 2004 |
| TOX-NO-FORCED-DIURESIS | FORBIDDEN | HIGH | AACT Guidelines; Shannon MW, Clin Toxicol 2007 |

### universal_clinical_safety (Universal Clinical Safety Principles)

| Rule ID | Type | Severity | Evidence |
|---------|------|----------|----------|
| SAFETY-ALLERGY-CHECK | REQUIRED | HIGH | Joint Commission NPSG 2024; WHO Patient Safety |
| SAFETY-ALLERGY-CHECK-FORBIDDEN | FORBIDDEN | CRITICAL | Joint Commission NPSG 2024; administering a known allergen i... |
| SAFETY-PREGNANCY-TERATOGEN-SCREEN | FORBIDDEN | CRITICAL | FDA Pregnancy Category X; ACOG 2020 |
| SAFETY-RENAL-DOSE-ADJUST | REQUIRED | HIGH | CKD-EPI 2021; FDA Renal Dosing Guidelines |
| SAFETY-RENAL-DOSE-ADJUST-FORBIDDEN | FORBIDDEN | HIGH | FDA Renal Impairment Guidance 2020; renally-cleared drugs ac... |
| SAFETY-HEPATIC-DOSE-ADJUST | REQUIRED | HIGH | Child-Pugh Classification; FDA Hepatic Dosing |
| SAFETY-HEPATIC-DOSE-ADJUST-FORBIDDEN | FORBIDDEN | HIGH | FDA Hepatic Impairment Guidance 2020; hepatotoxins at full d... |
| SAFETY-ELDERLY-BEERS-CRITERIA | FORBIDDEN | MODERATE | AGS Beers Criteria 2023 |
| SAFETY-WARFARIN-NSAID-INTERACTION | FORBIDDEN | CRITICAL | Joint Commission NPSG 2024; Delaney JA, Arch Intern Med 2007 |

