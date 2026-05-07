# Task: 신규 43개 시나리오 YAML 작성 + 전체 검증

Cross-domain 10개(#26-35)는 완료되어 커밋 대기 중이다. 나머지 43개를 작성하고 전체 100개를 검증한다.

## Context

- 기존 시나리오: 47개 유지 (5개 제거됨: septic_shock_e2e_001, septic_shock_e2e_002, aki_recovery, advanced_hf_evaluation, hfref_device_candidate)
- Cross-domain 신규: 10개 완료 (#26-35)
- **이번 작업: 43개 신규 작성 (#1-25 Category A, #36-43 Category C, #44-53 Category D)**
- 목표: 전체 100개 시나리오, regression test 통과

## Step 1: 기존 YAML 구조 학습

아래 파일들을 읽어서 YAML 스키마를 파악하라:
- `configs/scenarios/sepsis_scenarios.yaml` (basic + trap + cross-domain 완료 예시)
- `configs/scenarios/dka_scenarios.yaml` (다수 variant 예시)
- `configs/scenarios/aha_chest_pain_scenarios.yaml` (cross-domain 완료 예시 포함)
- `cpg_model/scenario_loader.py` (ScenarioDefinition 스키마, 필수 필드)

필수 필드 확인:
- scenario_id (unique)
- guideline_graph (반드시 기존 graph ID 중 하나)
- patient (age, sex, chief_complaint, history, medications, vitals 포함)
- vitals: map_mmhg 필드 필수
- expected_actions (리스트)
- forbidden_actions (리스트, trap이면 1개 이상)
- optional_actions (리스트, 비어도 됨)
- trap_scenario (Y/N)
- trap_description (trap_scenario=Y이면 필수, 상세 설명)
- max_duration_minutes
- passing_compliance_threshold
- working_diagnosis
- comorbidities, allergies, contraindications

## Step 2: 43개 시나리오 작성

아래 시나리오 정의를 참고하여 각 domain의 기존 YAML 파일에 append한다.
**새 YAML 파일을 만들지 말 것** — 기존 domain별 파일에 추가한다.

### Category A: 기존 graph trap variant (25개)

#### aha_chest_pain_scenarios.yaml에 추가 (4개)

**#1 `nstemi_cocaine_use_trap`**
- graph: `aha_chest_pain`
- trap: Y
- 환자: 32M, 코카인 사용 후 흉통, ST depression V1-V4
- expected: assess_vital_signs, obtain_12_lead_ecg, order_lab_troponin, order_lab_urine_drug_screen, give_aspirin, give_benzodiazepine, give_nitroglycerin, consult_cardiology
- forbidden: give_beta_blocker, give_metoprolol, give_atenolol, give_propranolol
- trap_description: 코카인 유발 ACS에서 beta-blocker → unopposed alpha-adrenergic stimulation → 관상동맥 수축 + 고혈압 악화. Benzodiazepine + NTG + CCB가 올바른 치료.
- comorbidities: cocaine_use, anxiety
- contraindications: beta_blockers_due_to_cocaine

**#2 `stemi_late_presenter_trap`**
- graph: `aha_chest_pain`
- trap: Y
- 환자: 68M, 흉통 onset 18시간 전, 지속적 ST elevation, ongoing chest pain
- expected: obtain_12_lead_ecg, order_lab_troponin, give_aspirin, give_heparin, consult_cardiology, assess_ongoing_ischemia
- forbidden: give_fibrinolytic, give_tenecteplase, give_alteplase
- trap_description: Onset >12h에서 fibrinolysis 금기 (효과 없고 출혈 위험만 증가). 지속적 허혈 시 PCI는 고려 가능하지만 fibrinolytic은 안 됨.
- max_duration_minutes: 120

**#3 `chest_pain_aortic_dissection_mimic`**
- graph: `aha_chest_pain`
- trap: Y
- 환자: 55M, 찢어지는 듯한 흉통, 등으로 방사, BP 좌우 차이 30mmHg, widened mediastinum on CXR
- expected: assess_vital_signs, obtain_12_lead_ecg, order_lab_troponin, order_lab_d_dimer, order_imaging_ct_angiography, give_iv_beta_blocker_for_rate_control, consult_cardiothoracic_surgery
- forbidden: give_heparin, give_antiplatelet, give_aspirin, give_thrombolytic, give_anticoagulation
- trap_description: ACS로 보이지만 실제 Stanford Type A aortic dissection. 항응고제/항혈소판제 투여 → 치명적 출혈. CT angiography로 확진 후 emergent surgery.
- comorbidities: hypertension, marfan_syndrome_suspected
- contraindications: anticoagulation_until_dissection_ruled_out

**#4 `nstemi_ckd_anticoag_trap`**
- graph: `aha_chest_pain`
- trap: Y
- 환자: 72F, NSTEMI, eGFR 18, CKD stage 4
- expected: obtain_12_lead_ecg, order_lab_troponin, give_aspirin, assess_renal_function, adjust_anticoagulant_dose, consult_cardiology, consult_nephrology
- forbidden: give_enoxaparin_full_dose, give_enoxaparin_1mg_kg, give_fondaparinux_without_adjustment
- trap_description: CKD stage 4 (eGFR <30)에서 enoxaparin 표준 용량 → 약물 축적 → 출혈. UFH 또는 enoxaparin 1mg/kg q24h (50% 감량) 필요.
- comorbidities: ckd_stage_4, diabetes_type_2, hypertension

#### aha_heart_failure_scenarios.yaml에 추가 (4개)

**#5 `hfref_hyperkalemia_arni_trap`**
- graph: `aha_heart_failure`
- trap: Y
- 환자: 65M, 새 HFrEF 진단, EF 30%, K+ 5.8 mEq/L
- expected: order_bnp_or_ntprobnp, order_echocardiogram, order_lab_bmp, check_potassium_before_gdmt, treat_hyperkalemia_first, initiate_beta_blocker, initiate_sglt2i
- forbidden: initiate_arni_with_hyperkalemia, initiate_mra_with_hyperkalemia, initiate_ace_with_hyperkalemia, give_potassium_supplement
- trap_description: K+ 5.8에서 ARNI + MRA 동시 시작 → K+ >7.0 → 치명적 부정맥. RAAS inhibitor는 K+ <5.0 확인 후 시작. SGLT2i와 BB는 K+ 영향 적어 먼저 시작 가능.
- comorbidities: hfref, hypertension, ckd_stage_3

**#6 `adhf_flash_pulmonary_edema`**
- graph: `aha_heart_failure`
- trap: Y
- 환자: 58F, 급성 호흡곤란, orthopnea, SpO2 82%, bilateral crackles, BP 180/110
- expected: assess_hemodynamic_profile, give_iv_furosemide, give_iv_nitroglycerin, apply_nippv, supplemental_oxygen, monitor_urine_output
- forbidden: give_high_dose_beta_blocker, give_iv_metoprolol_in_acute_failure, give_iv_inotropes
- trap_description: Flash pulmonary edema (warm-wet, hypertensive)에서 IV BB → 심박출량 급감 → cardiogenic shock. IV NTG + IV furosemide + NIPPV가 정석. Inotrope도 warm-wet에서 불필요.
- comorbidities: hfref, hypertension_poorly_controlled, atrial_fibrillation

**#7 `hfref_bradycardia_bb_trap`**
- graph: `aha_heart_failure`
- trap: Y
- 환자: 70M, HFrEF, routine follow-up, HR 42 bpm, 2nd degree AV block Mobitz type I
- expected: assess_vital_signs, obtain_12_lead_ecg, assess_current_medications, reduce_or_hold_beta_blocker, consider_pacemaker_evaluation
- forbidden: increase_beta_blocker, add_digoxin, add_ivabradine
- trap_description: Symptomatic bradycardia + AV block에서 BB 증량 → complete heart block → asystole. BB 감량 또는 중단 + pacemaker 평가. Digoxin/ivabradine도 AV conduction 추가 억제.
- comorbidities: hfref, 2nd_degree_av_block

**#8 `hfpef_overdiuresis_trap`**
- graph: `aha_heart_failure`
- trap: Y
- 환자: 78F, HFpEF, 입원 3일차, aggressive diuresis 중, BUN/Cr 상승, 기립성 저혈압
- expected: assess_volume_status, reduce_diuretic_dose, hold_diuretics_if_prerenal, check_bmp, assess_orthostatic_vitals
- forbidden: give_high_dose_diuretics, increase_furosemide, add_metolazone
- trap_description: HFpEF는 preload 의존적. 과도한 이뇨 → LV filling 부족 → CO 저하 + prerenal AKI. "euvolemia"를 넘어선 이뇨가 해로움.
- comorbidities: hfpef, hypertension, diabetes_type_2, obesity

#### aha_stroke_scenarios.yaml에 추가 (3개)

**#9 `stroke_posterior_circulation_trap`**
- graph: `aha_stroke`
- trap: Y
- 환자: 52M, 갑작스런 어지럼증, 복시, 구음장애, NIHSS 4
- expected: activate_stroke_team, perform_nihss, order_stat_ct_head, order_ct_angiography_head_neck, confirm_lvo_on_imaging, activate_neurointerventional_team
- forbidden: withhold_treatment_based_on_low_nihss, discharge_with_low_nihss
- trap_description: Posterior circulation stroke (basilar artery)는 NIHSS가 과소평가 (NIHSS가 anterior circulation 편향). NIHSS 4여도 basilar occlusion은 mortality >85%. CTA로 LVO 확인 후 thrombectomy 필요.
- comorbidities: hypertension, hyperlipidemia

**#10 `stroke_tpa_bp_uncontrolled_trap`**
- graph: `aha_stroke`
- trap: Y
- 환자: 66F, acute onset R hemiparesis, NIHSS 14, SBP 210/120 지속
- expected: activate_stroke_team, perform_nihss, order_stat_ct_head, attempt_bp_reduction, administer_iv_labetalol_or_nicardipine, reassess_bp_after_treatment
- forbidden: give_tpa_if_bp_uncontrolled, give_alteplase_with_sbp_above_185
- trap_description: tPA 적응증이지만 SBP >185 or DBP >110이면 tPA 금기. BP 조절 시도 → 185/110 이하로 떨어지면 tPA. 조절 불가 시 thrombectomy만 고려.
- comorbidities: hypertension_poorly_controlled, diabetes_type_2

**#11 `stroke_mimicker_seizure`**
- graph: `aha_stroke`
- trap: Y
- 환자: 45M, witnessed seizure 20분 전, R hemiparesis (Todd's paralysis), witnessed 신경학적 결손
- expected: activate_stroke_team, perform_nihss, order_stat_ct_head, obtain_history_of_seizure, order_lab_glucose, order_lab_bmp, observe_for_improvement, order_eeg_if_available
- forbidden: give_alteplase_without_ruling_out_mimic, give_tpa_for_todds_paralysis
- trap_description: Todd's paralysis (postictal focal deficit)는 stroke mimic. tPA 투여 → 불필요한 출혈 위험. 목격자 병력 + seizure history + 시간 경과 관찰로 감별.
- comorbidities: epilepsy

#### atrial_fibrillation_scenarios.yaml에 추가 (3개)

**#12 `af_wpw_av_nodal_blocker_trap`**
- graph: `atrial_fibrillation`
- trap: Y
- 환자: 28M, wide-complex irregular tachycardia, HR 180, delta waves on prior ECG
- expected: assess_vital_signs, obtain_12_lead_ecg, identify_wpw_pattern, give_procainamide_or_ibutilide, prepare_for_cardioversion
- forbidden: give_diltiazem, give_verapamil, give_digoxin, give_adenosine, give_beta_blocker_iv
- trap_description: WPW + AF에서 AV nodal blocker (diltiazem, verapamil, digoxin, adenosine) → AV node block + accessory pathway 우회 → 1:1 conduction → VF → cardiac arrest. Procainamide 또는 DC cardioversion이 정석.
- comorbidities: wpw_syndrome
- contraindications: av_nodal_blockers_due_to_wpw

**#13 `af_new_onset_thyrotoxicosis`**
- graph: `atrial_fibrillation`
- trap: N
- 환자: 42F, palpitations, weight loss, tremor, exophthalmos, AF on ECG, TSH <0.01
- expected: assess_vital_signs, obtain_12_lead_ecg, order_lab_tsh, order_lab_free_t4, order_lab_free_t3, assess_chadsvasc_score, give_rate_control, consult_endocrinology
- forbidden: give_amiodarone_without_thyroid_evaluation
- optional: order_imaging_thyroid_ultrasound
- comorbidities: graves_disease_suspected

**#14 `af_cardioversion_no_anticoag_trap`**
- graph: `atrial_fibrillation`
- trap: Y
- 환자: 60M, AF onset 3일 전, hemodynamically stable, wants rhythm control
- expected: assess_vital_signs, obtain_12_lead_ecg, confirm_af_duration_over_48h, initiate_anticoagulation, order_transesophageal_echo_or_anticoag_3weeks
- forbidden: perform_cardioversion_without_anticoag, perform_cardioversion_without_tee
- trap_description: AF >48h에서 항응고 없이 cardioversion → LA appendage thrombus 색전 → stroke. TEE로 thrombus 배제 후 cardioversion, 또는 3주 항응고 후 cardioversion.
- comorbidities: hypertension

#### cap_pneumonia_scenarios.yaml에 추가 (2개)

**#15 `cap_immunocompromised_trap`**
- graph: `cap_pneumonia`
- trap: Y
- 환자: 38M, HIV+ (CD4 85), fever, dry cough, bilateral ground-glass opacities, LDH elevated
- expected: assess_vital_signs, order_imaging_chest_xray, order_lab_cbc, order_lab_bmp, order_lab_ldh, order_lab_hiv_cd4, order_lab_beta_d_glucan, give_tmp_smx, give_prednisone_if_pao2_low, order_lab_blood_gas
- forbidden: give_standard_cap_antibiotics_only, discharge_without_pjp_workup
- trap_description: HIV + CD4 <200 + bilateral GGO + elevated LDH → PJP (Pneumocystis jirovecii) 강력 의심. 표준 CAP 항생제(amoxicillin, azithromycin)만으로 불충분. TMP-SMX + adjunctive steroid (PaO2 <70).
- comorbidities: hiv_aids, cd4_below_200
- contraindications: none

**#16 `cap_aspiration_anaerobe_trap`**
- graph: `cap_pneumonia`
- trap: Y
- 환자: 62M, 알코올 중독, found down, RLL consolidation, foul-smelling sputum
- expected: assess_vital_signs, order_imaging_chest_xray, order_lab_cbc, order_lab_bmp, give_antibiotics_with_anaerobic_coverage, consider_chest_ct_for_abscess
- forbidden: give_azithromycin_only, give_fluoroquinolone_only_without_anaerobic
- trap_description: 흡인 폐렴 + 혐기균 감염 의심 (foul sputum, alcohol, found down). 표준 CAP 항생제 단독 → 혐기균 미커버 → 폐농양 진행. Ampicillin-sulbactam 또는 clindamycin 추가 필요.
- comorbidities: chronic_alcohol_use, poor_dentition

#### copd_exacerbation_scenarios.yaml에 추가 (2개)

**#17 `copd_pneumothorax_niv_trap`**
- graph: `copd_exacerbation`
- trap: Y
- 환자: 58M, COPD GOLD 4, acute dyspnea, absent breath sounds on R, tracheal deviation to L
- expected: assess_vital_signs, order_imaging_chest_xray, diagnose_pneumothorax, perform_needle_decompression_or_chest_tube, do_not_start_niv_until_pneumothorax_treated
- forbidden: initiate_niv_with_pneumothorax, initiate_bipap_with_pneumothorax
- trap_description: COPD exacerbation처럼 보이지만 tension pneumothorax 동반. NIV/BiPAP → positive pressure → tension pneumothorax 악화 → cardiac arrest. CXR 먼저 확인, pneumothorax 치료 후에만 NIV 가능.
- comorbidities: copd_gold_stage_4, emphysema_bullous

**#18 `copd_cor_pulmonale_fluid_trap`**
- graph: `copd_exacerbation`
- trap: Y
- 환자: 65F, COPD exacerbation, JVP elevated, peripheral edema, RV heave, hepatomegaly
- expected: assess_vital_signs, order_lab_blood_gas, order_imaging_chest_xray, give_short_acting_bronchodilator, give_systemic_corticosteroid, give_cautious_diuretic, apply_controlled_oxygen_therapy
- forbidden: give_aggressive_iv_fluid, give_crystalloid_bolus, give_ns_1l_bolus
- trap_description: Cor pulmonale (RV failure) + COPD에서 "탈수 교정" 명목 IV fluid bolus → RV overload → 급성 악화. 이 환자는 volume overloaded이므로 이뇨제가 필요하지, 수액이 아님.
- comorbidities: copd_gold_stage_4, cor_pulmonale, pulmonary_hypertension

#### dka_scenarios.yaml에 추가 (1개)

**#19 `dka_cerebral_edema_pediatric_trap`**
- graph: `ada_dka_management`
- trap: Y
- 환자: 14M, new-onset T1DM, DKA (pH 7.05, glucose 580), GCS 15 → 12 (급격 악화)
- expected: assess_vital_signs, assess_mental_status, establish_iv_access, start_iv_fluid_ns, start_insulin_infusion, monitor_neurological_status_hourly, give_mannitol_or_hypertonic_saline_if_herniation, elevate_head_of_bed
- forbidden: give_rapid_fluid_bolus, give_bolus_over_20ml_kg_h, give_bicarbonate, give_hypotonic_fluid_early
- trap_description: 소아/청소년 DKA에서 급속 수액 투여(>20ml/kg/h) + 급격한 osmolality 변화 → 뇌부종 → herniation. Bicarbonate도 paradoxical CSF acidosis로 뇌부종 악화. 느린 수액 교정 (48h에 걸쳐) + 신경학적 모니터링.
- comorbidities: none (new-onset)

#### gi_bleeding_scenarios.yaml에 추가 (2개)

**#20 `gi_bleed_anticoag_valve_trap`**
- graph: `gi_bleeding`
- trap: Y
- 환자: 58M, mechanical mitral valve on warfarin, melena, Hb 8.2, INR 4.5
- expected: assess_vital_signs, establish_iv_access, order_lab_cbc, order_lab_coagulation, give_vitamin_k_low_dose, give_pcc_or_ffp, consult_gastroenterology, plan_anticoag_restart_strategy
- forbidden: stop_anticoagulation_permanently, withhold_anticoagulation_indefinitely
- trap_description: Mechanical valve + GI bleed. 항응고 영구 중단 → valve thrombosis → stroke/사망. INR 역전은 최소한으로 (저용량 vitamin K), GI bleed 안정화 후 항응고 재개 계획 필수. 중단 기간 bridging 고려.
- comorbidities: mechanical_mitral_valve, atrial_fibrillation
- contraindications: permanent_anticoagulation_cessation

**#21 `gi_bleed_variceal_terlipressin`**
- graph: `gi_bleeding`
- trap: N
- 환자: 52M, liver cirrhosis Child-Pugh C, hematemesis, known esophageal varices
- expected: assess_vital_signs, establish_large_bore_iv_access, give_crystalloid_fluid, order_lab_cbc, order_lab_coagulation, give_octreotide_or_terlipressin, give_antibiotic_prophylaxis, consult_gastroenterology, arrange_emergent_egd
- forbidden: delay_resuscitation_for_endoscopy, withhold_antibiotic_prophylaxis
- optional: activate_massive_transfusion_protocol, consider_balloon_tamponade_if_refractory
- comorbidities: liver_cirrhosis_child_c, portal_hypertension, esophageal_varices

#### hypertensive_emergency_scenarios.yaml에 추가 (2개)

**#22 `htn_pheochromocytoma_bb_trap`**
- graph: `hypertensive_emergency`
- trap: Y
- 환자: 38F, episodic headache/palpitations/diaphoresis triad, BP 260/150, HR 130, adrenal mass on prior imaging
- expected: assess_vital_signs, obtain_iv_access, give_phentolamine_or_alpha_blocker, order_lab_plasma_metanephrines, continuous_bp_monitoring, consult_endocrinology
- forbidden: give_beta_blocker_first, give_metoprolol, give_labetalol, give_propranolol
- trap_description: Pheochromocytoma crisis에서 BB 단독 투여 → alpha receptor unopposed → paradoxical BP 급등 → hypertensive crisis 악화 → stroke/MI. Alpha-blocker (phentolamine) 먼저 → BP 안정 후에만 BB 추가 가능. Labetalol도 금기 (alpha:beta = 1:3으로 beta 우세).
- comorbidities: pheochromocytoma_suspected
- contraindications: beta_blockers_before_alpha_blockade

**#23 `htn_eclampsia_trap`**
- graph: `hypertensive_emergency`
- trap: Y
- 환자: 28F, 34주 임산부, BP 190/120, seizure, proteinuria 3+, headache, visual changes
- expected: assess_vital_signs, obtain_iv_access, give_magnesium_sulfate, give_iv_hydralazine_or_labetalol, continuous_fetal_monitoring, consult_obstetrics, plan_delivery
- forbidden: give_ace_inhibitor, give_arb, give_nitroprusside, give_enalapril, give_losartan
- trap_description: Eclampsia에서 ACEi/ARB → 태아 기형 (renal agenesis, oligohydramnios). Nitroprusside → cyanide 태아 독성. MgSO4 (seizure 예방/치료) + IV hydralazine/labetalol (BP 조절) + emergent delivery planning.
- comorbidities: pregnancy_34weeks, preeclampsia_severe
- contraindications: ace_inhibitors_in_pregnancy, arbs_in_pregnancy, nitroprusside_in_pregnancy

#### kdigo_aki_full_scenarios.yaml에 추가 (1개)

**#24 `aki_hepatorenal_albumin_trap`**
- graph: `kdigo_aki_full`
- trap: Y
- 환자: 55M, liver cirrhosis, ascites, Cr 3.2 (baseline 1.0), oliguric, Na 125
- expected: order_creatinine, monitor_urine_output, discontinue_diuretics, give_albumin_1g_kg, consult_nephrology, consult_hepatology, evaluate_for_hepatorenal_syndrome
- forbidden: give_ns_bolus, give_aggressive_crystalloid, give_nsaid
- trap_description: Hepatorenal syndrome에서 NS bolus → 복수만 악화, 신기능 개선 안 됨. Albumin (1g/kg/day, max 100g) + terlipressin/midodrine+octreotide가 HRS-AKI 치료. Splanchnic vasoconstriction이 필요하지 crystalloid가 아님.
- comorbidities: liver_cirrhosis, ascites, portal_hypertension

#### sepsis_scenarios.yaml에 추가 (1개)

**#25 `sepsis_neutropenic_fever_trap`**
- graph: `ssc_sepsis_hour1`
- trap: Y
- 환자: 45F, ANC 200 (post-chemo day 10), fever 39.2°C, no localizing source, BP 100/60
- expected: order_lab_lactate, order_lab_blood_culture, give_anti_pseudomonal_antibiotic, give_crystalloid_30ml_kg, assess_need_for_vasopressor, order_lab_cbc_with_diff
- forbidden: delay_antibiotics_until_culture, delay_antibiotics_for_source, give_standard_cap_antibiotics_only
- trap_description: 호중구감소 발열은 sepsis equivalent. "Source 없으니 기다리자" → 급속 악화. ANC <500 + fever = 즉시 anti-pseudomonal 광범위 항생제 (cefepime/piperacillin-tazobactam/meropenem). 배양 결과 기다리지 않음.
- comorbidities: acute_myeloid_leukemia, chemotherapy_recent
- contraindications: none

### Category C: Allergy/interaction adversarial (8개)

#### sepsis_scenarios.yaml에 추가

**#36 `sepsis_vancomycin_red_man_trap`**
- graph: `ssc_sepsis_hour1`
- trap: Y
- 환자: 60M, MRSA bacteremia 의심, history of vancomycin red man syndrome
- expected: order_lab_lactate, order_lab_blood_culture, give_broad_spectrum_antibiotics, give_alternative_mrsa_coverage, give_crystalloid_30ml_kg
- forbidden: give_vancomycin_rapid_infusion, give_vancomycin_without_premedication
- trap_description: Red man syndrome history에서 rapid vancomycin → histamine release → hypotension 악화 (이미 septic). Linezolid 또는 daptomycin 대안, 또는 slow infusion (>2h) + antihistamine premedication.
- allergies: vancomycin_red_man_syndrome

#### dka_scenarios.yaml에 추가

**#37 `dka_metformin_lactic_acidosis_trap`**
- graph: `ada_dka_management`
- trap: Y
- 환자: 55M, T2DM on metformin + empagliflozin, AMS, pH 7.10, glucose 250, lactate 12, ketones mildly positive
- expected: assess_vital_signs, establish_iv_access, order_lab_bmp, order_lab_abg, order_lab_lactate, stop_metformin, stop_sglt2_inhibitor, start_iv_fluid_ns, start_insulin_infusion, consider_hemodialysis
- forbidden: continue_metformin, attribute_acidosis_to_dka_only, discharge_based_on_normal_glucose
- trap_description: Metformin-associated lactic acidosis (MALA) + euglycemic DKA (SGLT2i) 동시. 높은 lactate가 DKA의 typical finding이 아님 (DKA는 ketoacid 우세). MALA는 hemodialysis가 치료. 두 원인을 동시에 치료해야 함.
- comorbidities: type_2_diabetes, ckd_stage_3

#### pulmonary_embolism_scenarios.yaml에 추가

**#38 `pe_doac_obesity_trap`**
- graph: `pulmonary_embolism`
- trap: Y
- 환자: 42F, confirmed PE, BMI 58, weight 160kg
- expected: assess_vital_signs, start_anticoagulation_heparin, discuss_weight_based_dosing, consult_pharmacy, plan_transition_to_warfarin_with_inr_monitoring
- forbidden: give_rivaroxaban, give_apixaban, give_edoxaban, give_doac_standard_dose
- trap_description: BMI >40 또는 체중 >120kg에서 DOAC → sub-therapeutic drug level (Vd 증가, 임상시험에서 이 체중 제외). ISTH 2021 guidance: UFH → warfarin (INR monitoring) 또는 anti-Xa level monitored LMWH.
- comorbidities: morbid_obesity, immobilization

#### atrial_fibrillation_scenarios.yaml에 추가

**#39 `af_amiodarone_thyroid_trap`**
- graph: `atrial_fibrillation`
- trap: Y
- 환자: 68M, persistent AF on amiodarone x 2 years, new-onset weight loss, tremor, HR 140
- expected: assess_vital_signs, obtain_12_lead_ecg, order_lab_tsh, order_lab_free_t4, order_lab_free_t3, diagnose_amiodarone_induced_thyrotoxicosis, consider_stopping_amiodarone, consult_endocrinology
- forbidden: increase_amiodarone_dose, add_amiodarone_loading, give_amiodarone_iv
- trap_description: Amiodarone-induced thyrotoxicosis (AIT)에서 amiodarone 증량 → 갑상선 중독 악화 → thyroid storm. Amiodarone 중단 + AIT type 구분 (Type 1: thionamides, Type 2: steroids).
- comorbidities: persistent_atrial_fibrillation, amiodarone_use_chronic

#### aha_chest_pain_scenarios.yaml에 추가

**#40 `stemi_ticagrelor_cabg_trap`**
- graph: `aha_chest_pain`
- trap: Y
- 환자: 62M, STEMI, post-PCI 2시간, angiography shows 3-vessel disease → CABG needed
- expected: consult_cardiothoracic_surgery, assess_antiplatelet_status, document_ticagrelor_timing, plan_cabg_timing_with_washout, continue_aspirin
- forbidden: proceed_to_cabg_within_5_days_of_ticagrelor, perform_cabg_without_antiplatelet_washout
- trap_description: Ticagrelor 투여 후 5일 이내 CABG → 과도한 수술 출혈 (PLATO trial: major bleed 2x). Clopidogrel은 5일, ticagrelor도 5일, prasugrel은 7일 washout 필요. 긴급 CABG 시 platelet transfusion 고려.
- comorbidities: three_vessel_cad, diabetes_type_2

#### aha_heart_failure_scenarios.yaml에 추가

**#41 `hf_nsaid_otc_trap`**
- graph: `aha_heart_failure`
- trap: Y
- 환자: 72F, HFrEF EF 25%, knee pain으로 OTC ibuprofen 1200mg/day 자가 복용 중, 부종 악화
- expected: assess_vital_signs, review_current_medications, identify_nsaid_use, discontinue_nsaid, give_acetaminophen_alternative, optimize_gdmt
- forbidden: continue_nsaid, give_nsaid, give_ibuprofen, give_naproxen, give_celecoxib
- trap_description: NSAID in HFrEF → Na/water retention + prostaglandin inhibition → GFR 감소 + 부종 악화 + diuretic 저항성. AHA class III (harm) recommendation. NSAID 즉시 중단 + 대안 진통제.
- comorbidities: hfref, osteoarthritis, ckd_stage_3

#### kdigo_aki_full_scenarios.yaml에 추가

**#42 `aki_ace_hyperkalemia_trap`**
- graph: `kdigo_aki_full`
- trap: Y
- 환자: 68M, AKI stage 2, K+ 5.5, on lisinopril + spironolactone, Cr 3.8 (baseline 1.2)
- expected: order_creatinine, monitor_potassium, discontinue_ace_inhibitor, discontinue_spironolactone, discontinue_nephrotoxins, treat_hyperkalemia, consult_nephrology
- forbidden: continue_ace_inhibitor, continue_mra, give_potassium_supplement, increase_ace_dose
- trap_description: AKI + hyperkalemia에서 ACEi/ARB + MRA 지속 → K+ 추가 상승 → 치명적 부정맥. AKI 동안 RAAS inhibitor 일시 중단 필수. 신기능 회복 후 재시작 고려.
- comorbidities: hypertension, heart_failure, ckd_stage_3_baseline

#### aha_stroke_scenarios.yaml에 추가

**#43 `stroke_warfarin_reversal_choice_trap`**
- graph: `aha_stroke`
- trap: Y
- 환자: 75M, on warfarin (INR 3.8), acute ICH on CT, GCS 12
- expected: activate_stroke_team, order_stat_ct_head, order_lab_coagulation, give_4_factor_pcc, give_vitamin_k_iv, neurosurgery_consult, icu_admission
- forbidden: give_ffp_as_sole_reversal, delay_reversal_for_inr_result, give_tpa
- trap_description: Warfarin-related ICH에서 FFP 단독 역전 → 대용량 필요 (15ml/kg, ~4-6 units) → 수 시간 소요 + volume overload. 4-factor PCC가 즉시(15-30분) INR 역전 + 적은 volume. AHA/ASA guideline: PCC preferred over FFP.
- allergies: none

### Category D: Edge case / atypical presentation (10개)

#### aha_chest_pain_scenarios.yaml에 추가

**#44 `stemi_silent_diabetic_trap`**
- graph: `aha_chest_pain`
- trap: Y
- 환자: 70F, T2DM x 20y, 내원 사유 "그냥 기분이 안 좋아요", nausea, diaphoresis, no chest pain, ECG: ST elevation V1-V4
- expected: assess_vital_signs, obtain_12_lead_ecg, order_lab_troponin, recognize_silent_mi, give_aspirin, give_heparin, activate_cath_lab
- forbidden: discharge_without_ecg, discharge_with_vague_complaints
- trap_description: 당뇨 환자의 Silent MI — autonomic neuropathy로 흉통 없음. 비전형 증상(nausea, malaise, diaphoresis)만 present. ECG 없이 discharge → 사망. 고령 + 당뇨 + 비전형 증상 = 반드시 ECG.
- comorbidities: diabetes_type_2_longstanding, diabetic_neuropathy, hypertension, ckd_stage_3

#### sepsis_scenarios.yaml에 추가

**#45 `sepsis_elderly_afebrile_trap`**
- graph: `ssc_sepsis_hour1`
- trap: Y
- 환자: 85F, nursing home, AMS (GCS 13, baseline 15), HR 105, BP 95/55, T 36.2°C, WBC 3.2
- expected: order_lab_lactate, order_lab_blood_culture, give_broad_spectrum_antibiotics, give_crystalloid_30ml_kg, order_lab_cbc, order_urinalysis
- forbidden: discharge_without_sepsis_workup, attribute_ams_to_dementia, delay_antibiotics_due_to_no_fever
- trap_description: 고령 환자 afebrile sepsis — 면역 노화로 발열 반응 없음. 오히려 hypothermia/normothermia + leukopenia가 중증 지표. "열 없으니 감염 아님" 판단은 치명적. AMS + tachycardia + hypotension = sepsis until proven otherwise.
- comorbidities: dementia_mild, urinary_tract_infection_recurrent, diabetes_type_2

#### pulmonary_embolism_scenarios.yaml에 추가

**#46 `pe_pregnancy_imaging_trap`**
- graph: `pulmonary_embolism`
- trap: Y
- 환자: 30F, 28주 임산부, acute dyspnea, HR 110, SpO2 93%, calf swelling
- expected: assess_vital_signs, assess_wells_score, order_lower_extremity_doppler, start_anticoagulation_lmwh, order_imaging_vq_scan_preferred
- forbidden: order_ct_with_contrast_as_first_line, give_warfarin, give_doac, withhold_anticoagulation
- trap_description: 임산부 PE에서 CTPA가 gold standard이지만 radiation + iodinated contrast → 태아 갑상선 억제 우려. V/Q scan이 preferred (RCOG guideline). D-dimer는 임신 중 상승하여 비특이적. LMWH이 선호 항응고제 (warfarin, DOAC 금기).
- comorbidities: pregnancy_28weeks
- contraindications: warfarin_in_pregnancy, doac_in_pregnancy

#### dka_scenarios.yaml에 추가

**#47 `dka_alcoholic_ketoacidosis_mimic`**
- graph: `ada_dka_management`
- trap: Y
- 환자: 45M, chronic alcoholic, found confused, AG metabolic acidosis, ketones positive, glucose 95
- expected: assess_vital_signs, establish_iv_access, order_lab_bmp, order_lab_abg, order_lab_ethanol_level, order_lab_lactate, give_dextrose_containing_iv, give_thiamine_before_glucose, assess_for_alcoholic_ketoacidosis
- forbidden: start_insulin_infusion, give_insulin_for_normal_glucose, give_glucose_without_thiamine
- trap_description: Alcoholic ketoacidosis(AKA) ≠ DKA. Insulin 불필요하고 해로울 수 있음 (이미 정상 glucose). Glucose + thiamine (Wernicke 예방)이 치료. Glucose 전 thiamine 미투여 → Wernicke encephalopathy 촉발.
- comorbidities: chronic_alcohol_use, malnutrition

#### aha_stroke_scenarios.yaml에 추가

**#48 `stroke_cervical_dissection_young`**
- graph: `aha_stroke`
- trap: N
- 환자: 32M, chiropractic manipulation 후 갑작스런 neck pain + L hemiparesis, NIHSS 8
- expected: activate_stroke_team, perform_nihss, order_stat_ct_head, order_ct_angiography_head_neck, identify_cervical_artery_dissection, start_anticoagulation_or_antiplatelet, consult_neurology
- forbidden: delay_vascular_imaging
- comorbidities: none

#### kdigo_aki_full_scenarios.yaml에 추가

**#49 `aki_rhabdomyolysis_aggressive_fluid`**
- graph: `kdigo_aki_full`
- trap: Y
- 환자: 25M, crush injury, CK 45000, Cr 4.2, dark urine, K+ 6.1
- expected: order_creatinine, establish_iv_access, give_aggressive_ns_200_300ml_h, monitor_urine_output_target_200ml_h, treat_hyperkalemia, monitor_ck_serial, monitor_potassium_q4h, consult_nephrology
- forbidden: give_ns_maintenance_rate_only, restrict_fluid, give_lactated_ringers
- trap_description: Rhabdomyolysis + AKI에서 표준 AKI 수액(유지 속도) → myoglobin 미배출 → tubular necrosis 악화. 200-300ml/h NS로 공격적 hydration (UO target 200ml/h). LR은 K+ 함유하여 hyperkalemia 악화. Mannitol/bicarb은 논란 있지만 NS가 핵심.
- comorbidities: none

#### gi_bleeding_scenarios.yaml에 추가

**#50 `gi_bleed_nsaid_ppi_failure`**
- graph: `gi_bleeding`
- trap: Y
- 환자: 60M, already on PPI (omeprazole 20mg bid), melena, Hb 7.5, chronic NSAID use for arthritis
- expected: assess_vital_signs, establish_iv_access, order_lab_cbc, order_lab_bmp, order_lab_coagulation, discontinue_nsaid, give_iv_ppi_high_dose, consult_gastroenterology, arrange_upper_endoscopy
- forbidden: continue_nsaid, assume_ppi_failure_means_non_ulcer, discharge_without_endoscopy
- trap_description: PPI 복용 중 UGIB → "PPI 쓰고 있으니 ulcer 아닐 것" 판단 오류. PPI는 NSAID ulcer를 줄이지만 제거하지 않음. 내시경 필수. NSAID 즉시 중단. 대안 진통제로 전환.
- comorbidities: osteoarthritis, chronic_nsaid_use

#### hypertensive_emergency_scenarios.yaml에 추가

**#51 `htn_emergency_ischemic_stroke_window`**
- graph: `hypertensive_emergency`
- trap: Y
- 환자: 72F, acute R hemiparesis (onset 2h), NIHSS 12, SBP 200/110
- expected: assess_vital_signs, obtain_iv_access, administer_iv_antihypertensive_to_target_185_110, order_stat_ct_head, activate_stroke_team, reassess_bp_before_tpa
- forbidden: reduce_bp_more_than_25pct_in_1h, reduce_bp_below_140_in_tpa_candidate, give_oral_antihypertensive_only
- trap_description: HTN emergency + acute ischemic stroke tPA candidate → BP target가 다름. 일반 HTN emergency는 "25% in 1h"이지만, tPA candidate는 185/110 이하로 정밀 조절. 과도한 강하(140 이하) → cerebral hypoperfusion → infarct 확장.
- comorbidities: hypertension, atrial_fibrillation

#### copd_exacerbation_scenarios.yaml에 추가

**#52 `copd_exacerbation_chf_overlap`**
- graph: `copd_exacerbation`
- trap: Y
- 환자: 70M, dyspnea, wheeze + bilateral crackles, BNP 1200, ABG: pH 7.32, pCO2 55
- expected: assess_vital_signs, order_lab_blood_gas, order_lab_bnp, order_imaging_chest_xray, give_short_acting_bronchodilator, give_systemic_corticosteroid, give_iv_diuretic, apply_nippv
- forbidden: treat_as_copd_only, withhold_diuretic, withhold_bnp_testing
- trap_description: COPD exacerbation + acute decompensated HF 동시. "Wheeze = COPD"로만 치료하면 HF component 놓침 → 부종 지속. BNP 확인 + 이뇨제 + bronchodilator 동시 필요. BNP 미확인이 가장 흔한 실수.
- comorbidities: copd_gold_stage_3, hfref

#### cap_pneumonia_scenarios.yaml에 추가

**#53 `cap_covid_steroid_timing_trap`**
- graph: `cap_pneumonia`
- trap: Y
- 환자: 55M, COVID-19 confirmed, day 3 illness, SpO2 96% on RA, mild cough, no hypoxia
- expected: assess_vital_signs, order_imaging_chest_xray, order_lab_cbc, order_lab_crp, monitor_oxygen_saturation, give_supportive_care, plan_reassessment
- forbidden: give_dexamethasone_without_hypoxia, give_systemic_steroid_in_mild_covid, give_remdesivir_without_indication
- trap_description: COVID pneumonia에서 steroid timing이 핵심. RECOVERY trial: dexamethasone은 supplemental O2 필요한 환자에서만 사망률 감소. 비저산소 환자에서 조기 steroid → 바이러스 증식 + 면역 억제 → 악화. Hypoxia 발생 시에만 dexamethasone 시작.
- comorbidities: hypertension, diabetes_type_2

---

## Step 3: YAML validation

모든 시나리오 작성 후 다음을 실행:

```bash
# 1. Schema validation — 모든 scenario YAML이 ScenarioDefinition 스키마를 만족하는지
python -c "
from cpg_model.scenario_loader import ScenarioLoader
loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()
print(f'Total scenarios loaded: {len(scenarios)}')
assert len(scenarios) >= 100, f'Expected >=100, got {len(scenarios)}'
for s in scenarios:
    assert s.scenario_id, f'Missing scenario_id'
    assert s.guideline_graph, f'Missing guideline_graph for {s.scenario_id}'
    assert s.patient, f'Missing patient for {s.scenario_id}'
    if hasattr(s.patient, 'vitals') and s.patient.vitals:
        assert hasattr(s.patient.vitals, 'map_mmhg'), f'Missing map_mmhg for {s.scenario_id}'
    assert s.expected_actions is not None, f'Missing expected_actions for {s.scenario_id}'
    assert s.forbidden_actions is not None, f'Missing forbidden_actions for {s.scenario_id}'
    if s.trap_scenario:
        assert s.trap_description, f'Trap {s.scenario_id} missing trap_description'
        assert len(s.forbidden_actions) > 0, f'Trap {s.scenario_id} has no forbidden_actions'
print('All schema checks passed')
"

# 2. Graph resolution — 모든 guideline_graph가 유효한 graph 파일을 가리키는지
python -c "
from cpg_model.scenario_loader import ScenarioLoader, get_cpg_graph_path
loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()
valid_graphs = set()
for s in scenarios:
    path = get_cpg_graph_path(s.scenario_id)
    assert path.exists(), f'Graph not found for {s.scenario_id}: {path}'
    valid_graphs.add(s.guideline_graph)
print(f'All {len(scenarios)} scenarios resolve to valid graphs')
print(f'Unique graphs: {len(valid_graphs)} — {sorted(valid_graphs)}')
"

# 3. Unique ID check
python -c "
from cpg_model.scenario_loader import ScenarioLoader
loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()
ids = [s.scenario_id for s in scenarios]
dupes = [x for x in ids if ids.count(x) > 1]
assert not dupes, f'Duplicate scenario_ids: {set(dupes)}'
print(f'All {len(ids)} scenario_ids are unique')
"

# 4. Regression test
python -m pytest tests/ -x -q 2>&1 | tail -20

# 5. Summary report
python -c "
from cpg_model.scenario_loader import ScenarioLoader
loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()
from collections import Counter
graph_counts = Counter(s.guideline_graph for s in scenarios)
trap_count = sum(1 for s in scenarios if s.trap_scenario)
print(f'=== Final Summary ===')
print(f'Total scenarios: {len(scenarios)}')
print(f'Trap scenarios: {trap_count} ({trap_count/len(scenarios)*100:.0f}%)')
print(f'Domain distribution:')
for g, c in graph_counts.most_common():
    print(f'  {g}: {c}')
"
```

## Step 4: 제거 대상 시나리오 처리

다음 5개 시나리오를 YAML에서 제거하거나 `_disabled: true` 플래그를 추가하라:
- `septic_shock_e2e_001` (septic_shock_e2e_test.yaml)
- `septic_shock_e2e_002` (septic_shock_e2e_test.yaml)  
- `aki_recovery` (kdigo_aki_full_scenarios.yaml)
- `advanced_hf_evaluation` (aha_heart_failure_scenarios.yaml)
- `hfref_device_candidate` (aha_heart_failure_scenarios.yaml)

_disabled 플래그가 코드에 없으면, YAML 파일을 `_archive/disabled_scenarios/`로 이동하거나, scenario_id 앞에 `_disabled_` prefix를 붙여서 loader가 무시하도록 하라. 가장 깔끔한 방법을 코드에서 확인 후 결정하라.

## Step 5: hemorrhagic_stroke ActionNormalizer 수정

`cpg_model/action_normalizer.py` (또는 해당 매핑 파일)에 다음 매핑을 추가:

```python
# hemorrhagic_stroke — agent output → expected action 매핑
"order_imaging_ct_head": "order_stat_ct_head",
"order_imaging_head_ct": "order_stat_ct_head",
"consult_neurosurgery": "neurosurgery_consult",
"admit_to_icu": "icu_admission",
"give_medication_antihypertensive": "bp_reduction_target_140",
"give_medication_bp_control": "bp_reduction_target_140",
"give_medication_labetalol": "bp_reduction_target_140",
"give_medication_nicardipine": "bp_reduction_target_140",
"give_medication_tranexamic_acid": "reverse_anticoagulation_if_applicable",
```

또한 `hemorrhagic_stroke`의 expected_actions에서 `activate_stroke_team`을 optional_actions로 이동하라 (agent가 이 meta-action을 수행하지 않는 것이 확인됨).

## Completion Criteria

- [ ] 100개 이상 시나리오가 ScenarioLoader로 로드됨
- [ ] 모든 scenario_id가 unique
- [ ] 모든 guideline_graph가 유효한 graph 파일로 resolve
- [ ] 모든 trap 시나리오가 trap_description + forbidden_actions 1개 이상
- [ ] 모든 patient에 vitals.map_mmhg 존재
- [ ] 제거 대상 5개가 비활성화됨
- [ ] hemorrhagic_stroke normalizer 매핑 추가됨
- [ ] regression test: 이전과 동일한 pass/fail (97 passed, 1 pre-existing fail)
- [ ] Summary: domain 분포 + trap 비율 출력