# Task: Held-Out CPG 5개로 Derivation Engine 일반화 검증

## 목적

Derivation Engine + PatientGenerator가 **개발에 사용되지 않은 새로운 CPG domain**에서도 
유효한 시나리오를 자동 생성하는지 검증한다.

이 5개 domain은 기존 20개 graph 개발에 전혀 사용되지 않았으므로 **진짜 held-out test**이다.
논문에서: "We validated framework generalizability on 5 held-out CPG domains not used during development."

## 5개 Held-Out CPG

| # | Domain | Source Guideline | 선정 이유 |
|---|---|---|---|
| 1 | Burns | ABA 2024 Burn Resuscitation Guidelines | 수액 계산(Parkland formula), escharotomy, inhalation injury — conditional rules 풍부 |
| 2 | Transfusion | AABB 2024 Red Cell Transfusion Guidelines | Hb threshold가 context별로 다름 (cardiac vs general), massive transfusion protocol |
| 3 | OB Emergency | ACOG 2024 Obstetric Hemorrhage | PPH management, uterotonic selection, 임신 중 약물 금기 — pregnancy conditional 풍부 |
| 4 | Pediatric Emergency | PALS 2025 (AHA Pediatric) | 체중 기반 약물 용량, 성인과 다른 프로토콜, 소아 특유 forbidden |
| 5 | Psychiatric Emergency | APA 2024 Agitation Management | Chemical restraint 약물 선택, 기저질환별 금기, NMS/serotonin syndrome 감별 |

## 검증 프로토콜

**각 CPG에 대해 다음 순서를 따른다:**

### Phase 1: Graph 작성 (CPG당 ~30분)

기존 20개 graph와 동일한 구조로 YAML 작성:
- nodes (4-8개)
- unconditional forbidden_actions
- sequence_rules (BEFORE)
- conditional_rules (5-10개, trigger_range + normal_range 포함)
- evidence links

**핵심: 기존 코드를 전혀 수정하지 않고, YAML만 추가한다.**
Engine/Generator/Loader 코드 변경 = 0이어야 한다. 변경이 필요하면 버그다.

### Phase 2: 자동 생성 (CPG당 ~5분)

```bash
python scripts/generate_all_scenarios.py
# 새 5개 graph에서 시나리오가 자동 생성되는지 확인
```

### Phase 3: 품질 검증 (CPG당 ~15분)

생성된 시나리오에 대해 전체 검증 suite 실행.

---

## Graph 1: Burns (`aba_burn_resuscitation`)

Source: ABA 2024 Burn Resuscitation Practice Guidelines + ISBI 2024

```yaml
# cpg_model/graphs/aba_burn_resuscitation.yaml

graph_id: aba_burn_resuscitation
guideline: "ABA 2024 Practice Guidelines for Burn Resuscitation; ISBI 2024 Burn Care Guidelines"
version: "1.0"
entry_node: burn_initial_assessment

nodes:
  burn_initial_assessment:
    type: assessment
    description: "Primary survey + TBSA estimation + airway assessment"
    expected_actions:
      - assess_airway
      - assess_vital_signs
      - estimate_tbsa
      - assess_burn_depth
      - obtain_patient_weight
      - establish_iv_access
    forbidden_actions:
      - apply_ice_to_burn        # tissue damage
      - apply_butter_to_burn     # infection risk
      - debride_in_field         # do in burn center
    patient_activation_condition: "True"
    
  fluid_resuscitation:
    type: treatment
    description: "Parkland formula: 4ml × kg × %TBSA, half in first 8h"
    expected_actions:
      - calculate_parkland_formula
      - start_lactated_ringers
      - monitor_urine_output_target_0.5_ml_kg_h
      - titrate_fluids_to_urine_output
      - place_foley_catheter
    forbidden_actions:
      - give_colloid_in_first_24h    # Parkland uses crystalloid only first 24h
      - use_normal_saline_only       # hyperchloremic acidosis risk with large volumes
    sequence_rules:
      - [estimate_tbsa, calculate_parkland_formula]
      - [obtain_patient_weight, calculate_parkland_formula]
      - [establish_iv_access, start_lactated_ringers]
    patient_activation_condition: "patient.presentation.tbsa_percent >= 20"
    conditional_rules:
      - rule_id: "BURN-PEDIATRIC-DEXTROSE"
        condition: "patient.age < 5"
        effect:
          type: REQUIRED
          actions: [add_dextrose_to_iv, monitor_glucose_q4h]
        evidence: "ABA 2024; ISBI Pediatric Burns Chapter"
        severity: HIGH
        description: >
          Children <5 have limited glycogen stores. Large fluid resuscitation without 
          dextrose causes hypoglycemia. Add D5 to maintenance fluids.
        condition_variables: [patient.age]
        trigger_range:
          patient.age: {min: 1, max: 4, type: int}
        normal_range:
          patient.age: {min: 18, max: 80, type: int}

      - rule_id: "BURN-OVERRESUS-LIMIT"
        condition: "patient.presentation.tbsa_percent > 40"
        effect:
          type: FORBIDDEN
          actions: [exceed_6ml_kg_tbsa_in_24h]
        evidence: "ABA 2024; Saffle JR, J Burn Care Res 2007 - fluid creep"
        severity: HIGH
        description: >
          >40% TBSA burns risk "fluid creep" (>6ml/kg/%TBSA). Excessive resuscitation 
          causes abdominal compartment syndrome, pulmonary edema. Cap at ~6ml/kg/%TBSA 
          and consider colloid adjunct early.
        condition_variables: [patient.presentation.tbsa_percent]
        trigger_range:
          patient.presentation.tbsa_percent: {min: 41, max: 90, type: int}
        normal_range:
          patient.presentation.tbsa_percent: {min: 20, max: 40, type: int}

  inhalation_injury:
    type: treatment
    description: "Airway management for inhalation injury"
    expected_actions:
      - perform_early_intubation
      - order_chest_xray
      - order_carboxyhemoglobin
      - give_100_percent_oxygen
      - bronchoscopy_if_suspected
    forbidden_actions:
      - delay_intubation_for_imaging    # airway swelling progresses rapidly
    patient_activation_condition: >
      'inhalation_injury' in patient.comorbidities 
      or 'singed_nasal_hairs' in patient.exam_findings
      or 'soot_in_sputum' in patient.exam_findings
    conditional_rules:
      - rule_id: "BURN-CYANIDE-HYDROXOCOBALAMIN"
        condition: "'enclosed_space_fire' in patient.history"
        effect:
          type: REQUIRED
          actions: [give_hydroxocobalamin, order_cyanide_level]
        evidence: "ABA 2024; Baud FJ, NEJM 1991"
        severity: CRITICAL
        description: >
          Enclosed space fire → cyanide poisoning from combustion of synthetic materials.
          Hydroxocobalamin (Cyanokit) is first-line. Do NOT use sodium thiosulfate as 
          sole treatment (too slow onset).
        condition_variables: [patient.history]
        trigger_range:
          patient.history: {contains: "enclosed_space_fire", type: list_contains}
        normal_range:
          patient.history: {not_contains: "enclosed_space_fire", type: list_not_contains}

  escharotomy:
    type: treatment
    description: "Escharotomy for circumferential full-thickness burns"
    expected_actions:
      - assess_compartment_pressures
      - assess_distal_pulses
      - perform_escharotomy
    patient_activation_condition: >
      'circumferential_burn' in patient.exam_findings 
      and 'full_thickness' in patient.presentation.burn_depth
    conditional_rules:
      - rule_id: "BURN-CHEST-ESCHAR-VENTILATION"
        condition: "'circumferential_chest_burn' in patient.exam_findings"
        effect:
          type: REQUIRED
          actions: [perform_chest_escharotomy, monitor_ventilation_pressures]
        evidence: "ABA 2024; ISBI 2024 Escharotomy Chapter"
        severity: CRITICAL
        description: >
          Circumferential chest burns restrict chest wall compliance → ventilatory failure.
          Chest escharotomy restores compliance. Monitor peak airway pressures.
        condition_variables: [patient.exam_findings]
        trigger_range:
          patient.exam_findings: {contains: "circumferential_chest_burn", type: list_contains}
        normal_range:
          patient.exam_findings: {not_contains: "circumferential_chest_burn", type: list_not_contains}

  burn_wound_care:
    type: treatment
    description: "Initial wound management"
    expected_actions:
      - remove_clothing_jewelry
      - cover_with_clean_dry_dressing
      - update_tetanus_if_needed
      - pain_management
    forbidden_actions:
      - apply_topical_antibiotic_before_transfer  # burn center preference
    patient_activation_condition: "True"

  transfer_disposition:
    type: disposition
    description: "Transfer criteria to burn center"
    expected_actions:
      - assess_burn_center_referral_criteria
      - arrange_transfer_if_indicated
    forbidden_actions:
      - discharge_major_burn_home
    patient_activation_condition: "True"

edges:
  - {from: burn_initial_assessment, to: fluid_resuscitation}
  - {from: burn_initial_assessment, to: inhalation_injury}
  - {from: burn_initial_assessment, to: escharotomy}
  - {from: fluid_resuscitation, to: burn_wound_care}
  - {from: inhalation_injury, to: burn_wound_care}
  - {from: escharotomy, to: burn_wound_care}
  - {from: burn_wound_care, to: transfer_disposition}
```

Scenario template:
```yaml
# configs/scenarios/burn_scenarios.yaml
# (PatientGenerator가 자동으로 채울 것이므로 빈 파일 또는 최소 1개 수동 시나리오)
```

---

## Graph 2: Transfusion (`aabb_transfusion`)

Source: AABB 2024 Clinical Practice Guidelines for Red Cell Transfusion

```yaml
graph_id: aabb_transfusion
guideline: "AABB 2024 RBC Transfusion Guidelines; ASA 2024 Blood Management"
version: "1.0"
entry_node: transfusion_assessment

nodes:
  transfusion_assessment:
    type: assessment
    expected_actions:
      - order_cbc
      - order_type_and_screen
      - assess_hemodynamic_status
      - assess_active_bleeding
      - review_transfusion_history
    forbidden_actions:
      - transfuse_without_consent
      - transfuse_without_type_and_screen
    patient_activation_condition: "True"

  restrictive_threshold:
    type: decision
    description: "Restrictive transfusion: Hb < 7 g/dL for hemodynamically stable"
    expected_actions:
      - apply_restrictive_threshold
      - transfuse_prbc_if_hb_below_7
    forbidden_actions:
      - transfuse_for_hb_above_10    # never indicated (TRICC, TRACS trials)
      - transfuse_without_indication
    patient_activation_condition: >
      patient.labs.hemoglobin < 10 
      and 'hemodynamically_stable' in patient.presentation
      and 'acute_coronary_syndrome' not in patient.comorbidities
    conditional_rules:
      - rule_id: "TRANS-CARDIAC-LIBERAL-THRESHOLD"
        condition: "'acute_coronary_syndrome' in patient.comorbidities or 'symptomatic_cad' in patient.comorbidities"
        effect:
          type: REQUIRED
          actions: [apply_liberal_threshold_hb_8, transfuse_if_hb_below_8]
        evidence: "AABB 2024; MINT Trial, NEJM 2023"
        severity: HIGH
        description: >
          ACS/symptomatic CAD patients benefit from liberal threshold (Hb < 8 vs < 7).
          MINT trial showed worse outcomes with restrictive strategy in cardiac patients.
        condition_variables: [patient.comorbidities]
        trigger_range:
          patient.comorbidities: {contains: "acute_coronary_syndrome", type: list_contains}
        normal_range:
          patient.comorbidities: {not_contains: "acute_coronary_syndrome", type: list_not_contains}

      - rule_id: "TRANS-STABLE-NO-TRANSFUSE-ABOVE-7"
        condition: "patient.labs.hemoglobin >= 7 and 'hemodynamically_stable' in patient.presentation"
        effect:
          type: FORBIDDEN
          actions: [transfuse_prbc, order_transfusion]
        evidence: "AABB 2024; TRICC Trial, Hebert 1999 NEJM"
        severity: HIGH
        description: >
          In hemodynamically stable non-cardiac patients, Hb >= 7 does not require transfusion.
          Transfusing above threshold increases TACO, TRALI, infection risk without benefit.
        condition_variables: [patient.labs.hemoglobin, patient.presentation]
        trigger_range:
          patient.labs.hemoglobin: {min: 7.0, max: 9.9, type: float}
        normal_range:
          patient.labs.hemoglobin: {min: 4.0, max: 6.9, type: float}

  massive_transfusion:
    type: treatment
    description: "Massive transfusion protocol for hemorrhagic shock"
    expected_actions:
      - activate_massive_transfusion_protocol
      - give_prbc_ffp_platelets_1_1_1
      - give_tranexamic_acid
      - monitor_coagulation
      - maintain_temperature
    forbidden_actions:
      - delay_blood_products_for_crossmatch    # use uncrossmatched O-neg
      - give_crystalloid_as_sole_resuscitation  # dilutional coagulopathy
    patient_activation_condition: >
      'hemorrhagic_shock' in patient.presentation
      or patient.vitals.sbp < 70
    conditional_rules:
      - rule_id: "TRANS-TXA-WITHIN-3H"
        condition: "patient.presentation.get('time_since_injury_hours', 0) > 3"
        effect:
          type: FORBIDDEN
          actions: [give_tranexamic_acid]
        evidence: "CRASH-2 Trial, Lancet 2010 — TXA >3h increases mortality"
        severity: CRITICAL
        condition_variables: [patient.presentation.time_since_injury_hours]
        trigger_range:
          patient.presentation.time_since_injury_hours: {min: 3.1, max: 24, type: float}
        normal_range:
          patient.presentation.time_since_injury_hours: {min: 0, max: 3.0, type: float}

      - rule_id: "TRANS-JEHOVAH-NO-BLOOD"
        condition: "'jehovah_witness' in patient.preferences or 'refuses_blood_products' in patient.preferences"
        effect:
          type: FORBIDDEN
          actions: [give_prbc, give_ffp, give_platelets, give_whole_blood]
        evidence: "Patient autonomy; AABB ethical guidelines"
        severity: CRITICAL
        condition_variables: [patient.preferences]
        trigger_range:
          patient.preferences: {contains: "jehovah_witness", type: list_contains}
        normal_range:
          patient.preferences: {not_contains: "jehovah_witness", type: list_not_contains}

  transfusion_reaction:
    type: treatment
    description: "Recognition and management of acute transfusion reactions"
    expected_actions:
      - stop_transfusion_immediately
      - maintain_iv_access
      - send_blood_bank_workup
      - monitor_vitals_q15min
    forbidden_actions:
      - continue_transfusion_during_reaction
      - restart_same_unit
    patient_activation_condition: >
      'transfusion_reaction' in patient.presentation
    conditional_rules:
      - rule_id: "TRANS-ANAPHYLAXIS-EPI"
        condition: "'anaphylactic_transfusion_reaction' in patient.presentation"
        effect:
          type: REQUIRED
          actions: [give_epinephrine_im, stop_transfusion_immediately]
        evidence: "AABB 2024 Transfusion Reaction Management"
        severity: CRITICAL
        condition_variables: [patient.presentation]
        trigger_range:
          patient.presentation: {contains: "anaphylactic_transfusion_reaction", type: list_contains}
        normal_range:
          patient.presentation: {not_contains: "anaphylactic_transfusion_reaction", type: list_not_contains}

edges:
  - {from: transfusion_assessment, to: restrictive_threshold}
  - {from: transfusion_assessment, to: massive_transfusion}
  - {from: restrictive_threshold, to: transfusion_reaction}
  - {from: massive_transfusion, to: transfusion_reaction}
```

---

## Graph 3: OB Emergency (`acog_obstetric_hemorrhage`)

Source: ACOG 2024 Practice Bulletin — Postpartum Hemorrhage

```yaml
graph_id: acog_obstetric_hemorrhage
guideline: "ACOG 2024 Practice Bulletin #555 — Postpartum Hemorrhage; California CMQCC Toolkit"
version: "1.0"
entry_node: pph_recognition

nodes:
  pph_recognition:
    type: assessment
    expected_actions:
      - quantify_blood_loss
      - assess_vital_signs
      - assess_uterine_tone
      - establish_large_bore_iv
      - order_type_and_crossmatch
      - order_cbc_coagulation
    forbidden_actions:
      - delay_treatment_for_estimated_blood_loss  # quantitative > estimated
    patient_activation_condition: "True"

  uterotonic_therapy:
    type: treatment
    description: "First-line uterotonics for atonic PPH"
    expected_actions:
      - give_oxytocin_iv
      - perform_uterine_massage
    patient_activation_condition: "'uterine_atony' in patient.presentation"
    conditional_rules:
      - rule_id: "OB-ASTHMA-NO-CARBOPROST"
        condition: "'asthma' in patient.comorbidities"
        effect:
          type: FORBIDDEN
          actions: [give_carboprost, give_hemabate]
        evidence: "ACOG 2024; Carboprost package insert — bronchospasm contraindication"
        severity: CRITICAL
        description: >
          Carboprost (15-methyl PGF2α) causes bronchospasm. Contraindicated in asthma.
          Use methylergonovine or misoprostol instead.
        condition_variables: [patient.comorbidities]
        trigger_range:
          patient.comorbidities: {contains: "asthma", type: list_contains}
        normal_range:
          patient.comorbidities: {not_contains: "asthma", type: list_not_contains}

      - rule_id: "OB-HYPERTENSION-NO-METHYLERGONOVINE"
        condition: "'hypertension' in patient.comorbidities or 'preeclampsia' in patient.comorbidities"
        effect:
          type: FORBIDDEN
          actions: [give_methylergonovine, give_methergine]
        evidence: "ACOG 2024; Methylergonovine package insert — hypertension contraindication"
        severity: CRITICAL
        description: >
          Methylergonovine causes vasoconstriction → hypertensive crisis in preeclampsia/HTN.
          Use carboprost (if no asthma) or misoprostol instead.
        condition_variables: [patient.comorbidities]
        trigger_range:
          patient.comorbidities: {contains: "hypertension", type: list_contains}
        normal_range:
          patient.comorbidities: {not_contains: "hypertension", type: list_not_contains}

      - rule_id: "OB-ASTHMA-AND-HTN-MISOPROSTOL-ONLY"
        condition: "'asthma' in patient.comorbidities and 'hypertension' in patient.comorbidities"
        effect:
          type: REQUIRED
          actions: [give_misoprostol]
        evidence: "ACOG 2024 — when carboprost AND methylergonovine both contraindicated"
        severity: CRITICAL
        description: >
          Asthma + hypertension: carboprost contraindicated (bronchospasm), 
          methylergonovine contraindicated (vasoconstriction). Misoprostol is the only 
          safe second-line uterotonic. This is a classic clinical decision trap.
        condition_variables: [patient.comorbidities]
        trigger_range:
          patient.comorbidities: {contains: "asthma", type: list_contains}
        normal_range:
          patient.comorbidities: {not_contains: "asthma", type: list_not_contains}

  surgical_intervention:
    type: treatment
    description: "Surgical management when uterotonics fail"
    expected_actions:
      - perform_balloon_tamponade
      - consult_surgery
      - consider_b_lynch_suture
      - consider_hysterectomy_if_refractory
    patient_activation_condition: >
      'refractory_pph' in patient.presentation
      or patient.labs.estimated_blood_loss > 1500

  massive_transfusion_ob:
    type: treatment
    description: "Massive transfusion in obstetric hemorrhage"
    expected_actions:
      - activate_massive_transfusion_protocol
      - give_prbc_ffp_platelets
      - give_tranexamic_acid_1g
      - monitor_fibrinogen
      - give_cryoprecipitate_if_fibrinogen_low
    forbidden_actions:
      - withhold_txa_in_pph  # WOMAN trial: TXA reduces death from bleeding
    patient_activation_condition: >
      patient.labs.estimated_blood_loss > 1000
      or 'hemorrhagic_shock' in patient.presentation
    conditional_rules:
      - rule_id: "OB-TXA-WITHIN-3H-DELIVERY"
        condition: "patient.presentation.get('hours_since_delivery', 0) > 3"
        effect:
          type: FORBIDDEN
          actions: [give_tranexamic_acid]
        evidence: "WOMAN Trial, Lancet 2017 — TXA benefit only within 3h of delivery"
        severity: HIGH
        condition_variables: [patient.presentation.hours_since_delivery]
        trigger_range:
          patient.presentation.hours_since_delivery: {min: 3.1, max: 24, type: float}
        normal_range:
          patient.presentation.hours_since_delivery: {min: 0, max: 3.0, type: float}

edges:
  - {from: pph_recognition, to: uterotonic_therapy}
  - {from: pph_recognition, to: massive_transfusion_ob}
  - {from: uterotonic_therapy, to: surgical_intervention}
  - {from: massive_transfusion_ob, to: surgical_intervention}
```

---

## Graph 4: Pediatric Emergency (`pals_pediatric_emergency`)

Source: AHA 2025 PALS Guidelines

```yaml
graph_id: pals_pediatric_emergency
guideline: "AHA PALS 2025 Guidelines; AAP Pediatric Emergency Medicine"
version: "1.0"
entry_node: pediatric_assessment

nodes:
  pediatric_assessment:
    type: assessment
    expected_actions:
      - assess_pediatric_triangle  # appearance, breathing, circulation
      - obtain_weight_kg
      - assess_vital_signs_age_appropriate
      - establish_iv_or_io_access
    forbidden_actions:
      - use_adult_vital_sign_norms    # pediatric norms differ by age
      - give_adult_dose_medications   # weight-based dosing required
    patient_activation_condition: "True"

  pediatric_fluid_resuscitation:
    type: treatment
    expected_actions:
      - give_ns_bolus_20ml_kg
      - reassess_after_each_bolus
      - monitor_urine_output
    forbidden_actions:
      - give_bolus_greater_than_20ml_kg  # risk of fluid overload in peds
    patient_activation_condition: >
      'dehydration' in patient.presentation
      or 'shock' in patient.presentation
    conditional_rules:
      - rule_id: "PEDS-DKA-SLOW-FLUID"
        condition: "'dka' in patient.presentation"
        effect:
          type: FORBIDDEN
          actions: [give_rapid_fluid_bolus, give_bolus_greater_than_10ml_kg]
        evidence: "ISPAD 2022; AHA PALS 2025 — cerebral edema risk in pediatric DKA"
        severity: CRITICAL
        description: >
          Pediatric DKA: rapid fluid (>10ml/kg/h) → cerebral edema → herniation.
          Use 10ml/kg over 1h, then slow correction over 48h.
        condition_variables: [patient.presentation]
        trigger_range:
          patient.presentation: {contains: "dka", type: list_contains}
        normal_range:
          patient.presentation: {not_contains: "dka", type: list_not_contains}

      - rule_id: "PEDS-CARDIAC-LIMIT-FLUID"
        condition: "'congenital_heart_disease' in patient.comorbidities"
        effect:
          type: FORBIDDEN
          actions: [give_ns_bolus_20ml_kg, give_rapid_fluid_bolus]
        evidence: "AHA PALS 2025; Pediatric Cardiology Guidelines"
        severity: HIGH
        description: >
          CHD patients have limited cardiac reserve. Standard 20ml/kg bolus 
          can cause pulmonary edema. Use 5-10ml/kg with frequent reassessment.
        condition_variables: [patient.comorbidities]
        trigger_range:
          patient.comorbidities: {contains: "congenital_heart_disease", type: list_contains}
        normal_range:
          patient.comorbidities: {not_contains: "congenital_heart_disease", type: list_not_contains}

  pediatric_seizure:
    type: treatment
    expected_actions:
      - check_glucose
      - give_benzodiazepine_weight_based
      - protect_airway
      - monitor_respiratory_status
    patient_activation_condition: "'seizure' in patient.presentation"
    conditional_rules:
      - rule_id: "PEDS-FEBRILE-SEIZURE-NO-AED"
        condition: "'simple_febrile_seizure' in patient.presentation and patient.age >= 1"
        effect:
          type: FORBIDDEN
          actions: [give_antiepileptic_medication, start_levetiracetam, start_phenytoin]
        evidence: "AAP 2011 Febrile Seizure Practice Parameter (reaffirmed 2023)"
        severity: HIGH
        description: >
          Simple febrile seizures in children ≥1y do NOT require antiepileptic medication.
          Treatment is supportive + antipyretic. Starting AEDs is overtreatment with 
          side effects and no benefit for simple febrile seizures.
        condition_variables: [patient.presentation, patient.age]
        trigger_range:
          patient.presentation: {contains: "simple_febrile_seizure", type: list_contains}
        normal_range:
          patient.presentation: {not_contains: "simple_febrile_seizure", type: list_not_contains}

      - rule_id: "PEDS-NEONATE-SEIZURE-PHENOBARB"
        condition: "patient.age < 1"
        effect:
          type: REQUIRED
          actions: [give_phenobarbital_first_line]
        evidence: "AHA PALS 2025; Neonatal seizure management — phenobarbital preferred over levetiracetam"
        severity: HIGH
        condition_variables: [patient.age]
        trigger_range:
          patient.age: {min: 0, max: 0, type: int}
        normal_range:
          patient.age: {min: 1, max: 17, type: int}

  pediatric_anaphylaxis:
    type: treatment
    expected_actions:
      - give_epinephrine_im_0.01mg_kg
      - establish_iv_access
      - give_fluid_bolus
      - monitor_closely
    forbidden_actions:
      - give_adult_dose_epinephrine    # 0.3-0.5mg adult dose in small child → hypertensive crisis
      - give_epinephrine_iv_push       # IV epi only as infusion in peds
    patient_activation_condition: "'anaphylaxis' in patient.presentation"

edges:
  - {from: pediatric_assessment, to: pediatric_fluid_resuscitation}
  - {from: pediatric_assessment, to: pediatric_seizure}
  - {from: pediatric_assessment, to: pediatric_anaphylaxis}
```

---

## Graph 5: Psychiatric Emergency (`apa_agitation_management`)

Source: APA 2024 Practice Guidelines for Agitation Management; BETA Project 2012

```yaml
graph_id: apa_agitation_management
guideline: "APA 2024 Agitation Management; Wilson MP et al., West J Emerg Med 2012 (BETA Project)"
version: "1.0"
entry_node: agitation_assessment

nodes:
  agitation_assessment:
    type: assessment
    expected_actions:
      - assess_safety_of_environment
      - attempt_verbal_deescalation
      - assess_medical_causes  # hypoglycemia, infection, intoxication
      - obtain_vital_signs
      - check_glucose
    forbidden_actions:
      - restrain_without_attempting_deescalation  # verbal first per APA/BETA
      - leave_patient_unsupervised_while_agitated
    patient_activation_condition: "True"

  pharmacologic_intervention:
    type: treatment
    description: "Chemical restraint when verbal deescalation fails"
    expected_actions:
      - choose_appropriate_medication
      - monitor_sedation_level
      - monitor_respiratory_status
    patient_activation_condition: "'deescalation_failed' in patient.presentation"
    conditional_rules:
      - rule_id: "PSYCH-ETOH-NO-BENZO-MONOTHERAPY"
        condition: "'alcohol_intoxication' in patient.presentation"
        effect:
          type: FORBIDDEN
          actions: [give_benzodiazepine_high_dose, give_lorazepam_4mg, give_midazolam_10mg]
        evidence: "BETA Project 2012; Nobay F, Ann Emerg Med 2004"
        severity: CRITICAL
        description: >
          Alcohol + high-dose benzodiazepine → profound respiratory depression.
          Use antipsychotic (haloperidol, olanzapine) instead or low-dose benzo 
          with close monitoring.
        condition_variables: [patient.presentation]
        trigger_range:
          patient.presentation: {contains: "alcohol_intoxication", type: list_contains}
        normal_range:
          patient.presentation: {not_contains: "alcohol_intoxication", type: list_not_contains}

      - rule_id: "PSYCH-QTC-NO-HALOPERIDOL"
        condition: "patient.labs.get('qtc_ms', 0) > 500 or 'prolonged_qtc' in patient.comorbidities"
        effect:
          type: FORBIDDEN
          actions: [give_haloperidol, give_droperidol]
        evidence: "FDA Black Box Warning — haloperidol QT prolongation; APA 2024"
        severity: CRITICAL
        description: >
          QTc > 500ms + haloperidol → Torsades de Pointes → sudden cardiac death.
          Use benzodiazepine (lorazepam) or olanzapine instead.
        condition_variables: [patient.labs.qtc_ms, patient.comorbidities]
        trigger_range:
          patient.labs.qtc_ms: {min: 501, max: 700, type: int}
        normal_range:
          patient.labs.qtc_ms: {min: 350, max: 470, type: int}

      - rule_id: "PSYCH-PARKINSON-NO-TYPICAL-ANTIPSYCHOTIC"
        condition: "'parkinson_disease' in patient.comorbidities or 'lewy_body_dementia' in patient.comorbidities"
        effect:
          type: FORBIDDEN
          actions: [give_haloperidol, give_droperidol, give_chlorpromazine]
        evidence: "APA 2024; McKeith IG, Neurology 2005 — neuroleptic sensitivity in LBD"
        severity: CRITICAL
        description: >
          Typical antipsychotics in Parkinson/LBD → severe neuroleptic sensitivity 
          reaction, irreversible parkinsonism, NMS. Use low-dose quetiapine if needed.
        condition_variables: [patient.comorbidities]
        trigger_range:
          patient.comorbidities: {contains: "parkinson_disease", type: list_contains}
        normal_range:
          patient.comorbidities: {not_contains: "parkinson_disease", type: list_not_contains}

      - rule_id: "PSYCH-OLANZAPINE-NO-BENZO-COMBO"
        condition: "'olanzapine_im_given' in patient.treatment_received"
        effect:
          type: FORBIDDEN
          actions: [give_lorazepam_im, give_benzodiazepine_im]
        evidence: "Olanzapine IM package insert; FDA warning — respiratory depression with IM benzo combo"
        severity: CRITICAL
        description: >
          IM olanzapine + IM benzodiazepine → respiratory arrest (multiple case reports).
          FDA contraindication. Wait adequate time between agents or use different combination.
        condition_variables: [patient.treatment_received]
        trigger_range:
          patient.treatment_received: {contains: "olanzapine_im_given", type: list_contains}
        normal_range:
          patient.treatment_received: {not_contains: "olanzapine_im_given", type: list_not_contains}

  physical_restraint:
    type: treatment
    expected_actions:
      - apply_least_restrictive_restraint
      - monitor_neurovascular_status_q15min
      - document_restraint_indication
      - reassess_need_q1h
    forbidden_actions:
      - prone_restraint      # positional asphyxia risk
      - hobble_restraint     # positional asphyxia risk
      - leave_restrained_patient_unmonitored
    patient_activation_condition: >
      'imminent_danger_to_self_or_others' in patient.presentation
      and 'medication_insufficient' in patient.presentation

  nms_serotonin_syndrome:
    type: treatment
    description: "Neuroleptic malignant syndrome / serotonin syndrome recognition"
    expected_actions:
      - stop_offending_agent
      - aggressive_cooling
      - give_iv_fluids
      - monitor_ck_renal_function
    patient_activation_condition: >
      'hyperthermia' in patient.vitals_findings
      and 'rigidity' in patient.exam_findings
    conditional_rules:
      - rule_id: "PSYCH-NMS-DANTROLENE"
        condition: "'neuroleptic_malignant_syndrome' in patient.presentation"
        effect:
          type: REQUIRED
          actions: [give_dantrolene, stop_all_antipsychotics]
        evidence: "APA 2024 NMS Guidelines; Strawn JR, CNS Drugs 2007"
        severity: CRITICAL
        condition_variables: [patient.presentation]
        trigger_range:
          patient.presentation: {contains: "neuroleptic_malignant_syndrome", type: list_contains}
        normal_range:
          patient.presentation: {not_contains: "neuroleptic_malignant_syndrome", type: list_not_contains}

      - rule_id: "PSYCH-SEROTONIN-CYPROHEPTADINE"
        condition: "'serotonin_syndrome' in patient.presentation"
        effect:
          type: REQUIRED
          actions: [give_cyproheptadine, stop_serotonergic_agents]
        evidence: "Boyer EW, NEJM 2005; APA 2024"
        severity: CRITICAL
        condition_variables: [patient.presentation]
        trigger_range:
          patient.presentation: {contains: "serotonin_syndrome", type: list_contains}
        normal_range:
          patient.presentation: {not_contains: "serotonin_syndrome", type: list_not_contains}

edges:
  - {from: agitation_assessment, to: pharmacologic_intervention}
  - {from: agitation_assessment, to: physical_restraint}
  - {from: pharmacologic_intervention, to: nms_serotonin_syndrome}
```

---

## 검증 프로토콜

### Step 1: Graph 파일 저장 + 파서 확인

5개 graph YAML을 `cpg_model/graphs/`에 저장한다.
**코드 변경 없이** 기존 파서가 읽을 수 있는지 확인:

```bash
python -c "
from pathlib import Path
new_graphs = [
    'aba_burn_resuscitation',
    'aabb_transfusion', 
    'acog_obstetric_hemorrhage',
    'pals_pediatric_emergency',
    'apa_agitation_management'
]
for g in new_graphs:
    path = Path(f'cpg_model/graphs/{g}.yaml')
    assert path.exists(), f'Missing: {path}'
    # 파서로 로드
    from cpg_model.schemas.base import load_graph  # 또는 실제 로드 함수
    graph = load_graph(path)
    print(f'  {g}: {len(graph[\"nodes\"])} nodes, loaded OK')
print('All 5 held-out graphs loaded without code changes')
"
```

**만약 코드 변경이 필요하면, 어떤 변경이 필요한지 보고하라. 이것 자체가 engine의 일반화 한계를 보여주는 유용한 정보.**

### Step 2: 자동 시나리오 생성

```bash
python scripts/generate_all_scenarios.py 2>&1 | grep -E "(aba_burn|aabb_trans|acog_obstet|pals_ped|apa_agit)"
```

각 held-out graph에서 최소 5개 시나리오가 생성되어야 한다.

### Step 3: 생성된 시나리오 품질 검증

```python
# scripts/verify_holdout_scenarios.py
from cpg_model.scenario_loader import ScenarioLoader
from cpg_model.constraint_derivation import ConstraintDerivationEngine

loader = ScenarioLoader()
engine = ConstraintDerivationEngine()

holdout_graphs = [
    'aba_burn_resuscitation', 'aabb_transfusion', 
    'acog_obstetric_hemorrhage', 'pals_pediatric_emergency', 
    'apa_agitation_management'
]

scenarios = loader.load_all_scenarios()
holdout = [s for s in scenarios if s.guideline_graph in holdout_graphs]

print(f"Held-out scenarios generated: {len(holdout)}")

for g in holdout_graphs:
    g_scenarios = [s for s in holdout if s.guideline_graph == g]
    traps = [s for s in g_scenarios if s.trap_scenario]
    normals = [s for s in g_scenarios if not s.trap_scenario]
    
    ea_mean = sum(len(s.expected_actions) for s in g_scenarios) / len(g_scenarios) if g_scenarios else 0
    fa_mean = sum(len(s.forbidden_actions) for s in g_scenarios) / len(g_scenarios) if g_scenarios else 0
    
    print(f"\n{g}:")
    print(f"  Total: {len(g_scenarios)} ({len(traps)} traps, {len(normals)} normals)")
    print(f"  Expected mean: {ea_mean:.1f}")
    print(f"  Forbidden mean: {fa_mean:.1f}")
    
    # 품질 체크
    for s in g_scenarios:
        assert len(s.expected_actions) > 0, f"{s.scenario_id}: no expected actions"
        assert len(s.forbidden_actions) > 0, f"{s.scenario_id}: no forbidden actions"
        if s.trap_scenario:
            assert s.trap_description, f"{s.scenario_id}: trap without description"
    
    # 샘플 출력 (trap 1개)
    if traps:
        t = traps[0]
        print(f"  Sample trap: {t.scenario_id}")
        print(f"    Patient: age={t.patient.get('age')}, comorb={t.patient.get('comorbidities', [])[:3]}")
        print(f"    Expected: {t.expected_actions[:5]}...")
        print(f"    Forbidden: {t.forbidden_actions[:5]}...")
        print(f"    Trap: {t.trap_description[:100]}...")

print(f"\n=== Held-out validation {'PASSED' if len(holdout) >= 25 else 'NEEDS REVIEW'} ===")
```

### Step 4: Contradiction + realism 검증

기존 검증 스크립트를 held-out에도 적용:

```bash
python scripts/detect_contradictions.py  # 전체에 대해 실행, held-out 포함
python scripts/generate_patient_realism_report.py
```

### Step 5: 결과 보고

최종 보고에 포함할 것:
1. **코드 변경 필요 여부**: 0이면 "engine is generalizable", >0이면 어떤 변경이 필요했는지
2. **graph당 생성된 시나리오 수 + trap 비율**
3. **expected/forbidden 분포가 기존 20개 graph와 유사한지**
4. **임상적 유효성**: sample scenario가 말이 되는지
5. **에러 0 확인**

---

## Completion Criteria

- [ ] 5개 graph YAML 저장됨
- [ ] **코드 변경 0으로** 파서가 읽음 (또는 필요한 변경 보고)
- [ ] 각 graph에서 최소 5개 시나리오 자동 생성
- [ ] 각 graph에서 최소 2개 trap 시나리오
- [ ] Expected actions mean 8-20 (held-out graph들)
- [ ] Contradiction 0
- [ ] 비현실적 환자 0 (또는 justified)
- [ ] 전체 테스트 194+ 통과 유지