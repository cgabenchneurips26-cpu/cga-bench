# Task: Scenario Constraint Derivation Engine 전체 구현

## 목표

"새 CPG graph를 넣으면 시나리오가 자동으로 나오는" 파이프라인을 구축한다.
모든 시나리오의 constraint는 CPG graph + patient context에서 **연역적으로 도출**되며,
각 constraint에 provenance chain(graph:node:rule → guideline evidence)이 붙는다.

결과물:
1. Conditional rule 스키마 + 14개 기존 graph에 rule 추가
2. 6개 신규 graph (anaphylaxis, ACLS, status epilepticus, asthma exacerbation, meningitis, overdose/toxicology)
3. ConstraintDerivationEngine (graph + patient → derived constraints)
4. PatientGenerator (conditional rule → trigger/normal patient 자동 생성)
5. Rule Coverage Audit Matrix (CPG 원문 조항 ↔ graph rule 1:1 매핑)
6. ~140개 시나리오 자동 생성 + validation

## 전체 아키텍처

```
CPG Graph YAML (nodes, edges, conditional_rules, evidence)
       │
       ├──→ ConstraintDerivationEngine
       │         │
       │    Patient Context ──→ Derived Constraints (FORBIDDEN, EXPECTED, BEFORE, WITHIN)
       │                              │
       │                              └──→ provenance chain per constraint
       │
       └──→ PatientGenerator
                  │
             conditional_rules의 condition을 분석
                  │
                  ├──→ trigger patients (condition 만족 → trap scenario)
                  └──→ normal patients (condition 불만족 → baseline scenario)
```

---

## Phase 1: Conditional Rule 스키마 설계 (0.5일)

### Step 1.1: 기존 코드 읽기

다음 파일을 읽어서 현재 graph/scenario 스키마를 파악하라:
- `cpg_model/graphs/*.yaml` (모든 14개)
- `cpg_model/graph_schema.py` 또는 graph를 파싱하는 코드
- `cpg_model/scenario_loader.py` (ScenarioDefinition)
- `cpg_model/engine.py` (CPGEngine — graph traversal, precondition eval)
- `scoring/constraint_checker.py` 또는 constraint 평가 코드

특히 확인할 것:
- 현재 precondition이 어떤 형태로 정의되어 있는지 (string eval? dict?)
- forbidden_actions가 node-level에서 어떻게 정의되는지
- `set_scenario_forbidden_actions()` 가 어디서 호출되는지
- WITHIN constraint가 어디서 정의/평가되는지 (handoff 문서에 92개라고 되어 있지만 graph YAML에서 안 보임)

### Step 1.2: ConditionalRule 스키마 정의

`cpg_model/graph_schema.py` (또는 해당 파일)에 추가:

```python
from dataclasses import dataclass, field
from typing import List, Optional, Literal
from enum import Enum

class ConstraintType(str, Enum):
    FORBIDDEN = "FORBIDDEN"
    REQUIRED = "REQUIRED"  
    BEFORE = "BEFORE"
    WITHIN = "WITHIN"

class Severity(str, Enum):
    CRITICAL = "CRITICAL"   # 위반 시 환자 사망/중대 손상 가능
    HIGH = "HIGH"           # 위반 시 심각한 합병증
    MODERATE = "MODERATE"   # 위반 시 차선 치료
    LOW = "LOW"             # 위반 시 경미한 영향

@dataclass
class ConstraintEffect:
    type: ConstraintType
    actions: List[str]
    # BEFORE일 경우: actions[0] must come before actions[1]
    # WITHIN일 경우: actions[0] must occur within time_limit_minutes
    time_limit_minutes: Optional[int] = None

@dataclass  
class ConditionalRule:
    rule_id: str                    # unique ID: "{GRAPH}-{DOMAIN}-{SHORT_NAME}"
    condition: str                  # Python-evaluable condition string
    effect: ConstraintEffect
    evidence: str                   # "ADA 2024 DKA Guidelines, Section 4.2"
    severity: Severity
    description: str                # 사람이 읽을 수 있는 설명
    
    # condition에 사용되는 변수 목록 (PatientGenerator가 참조)
    condition_variables: List[str] = field(default_factory=list)
    # 예: ["patient.labs.potassium"] → Generator가 이 변수를 조작
    
    # condition이 True일 때 trigger되는 값 범위 (PatientGenerator용)
    trigger_range: Optional[dict] = None
    # 예: {"patient.labs.potassium": {"min": 0.5, "max": 3.2, "type": "float"}}
    
    # condition이 False일 때 정상 값 범위
    normal_range: Optional[dict] = None
    # 예: {"patient.labs.potassium": {"min": 3.5, "max": 5.5, "type": "float"}}
```

### Step 1.3: Graph YAML 스키마 확장

기존 graph YAML의 node에 `conditional_rules` 필드를 추가한다.
기존 필드(forbidden_actions, preconditions 등)는 그대로 유지하고, **추가**한다.

```yaml
# 예: ada_dka_management.yaml의 potassium_replacement_first node
potassium_replacement_first:
  type: decision
  description: "Potassium must be checked and replaced before insulin"
  preconditions:
    - "state.potassium_checked == True"
  
  # 기존 (유지)
  forbidden_actions:
    - start_insulin_infusion
    - give_insulin_bolus
  
  # 신규 추가
  conditional_rules:
    - rule_id: "DKA-HYPOKALEMIA-INSULIN-GATE"
      condition: "patient.labs.potassium < 3.3"
      effect:
        type: FORBIDDEN
        actions: [start_insulin_infusion, give_insulin_bolus]
      evidence: "ADA 2024 Standards of Care, Section 16.2 - DKA Management"
      severity: CRITICAL
      description: >
        Insulin drives potassium intracellularly. Starting insulin with K+ < 3.3 
        can cause life-threatening hypokalemia, cardiac arrhythmias, and arrest.
        Potassium must be repleted to >= 3.3 before insulin initiation.
      condition_variables: ["patient.labs.potassium"]
      trigger_range:
        patient.labs.potassium: {min: 1.5, max: 3.2, type: float, unit: "mEq/L"}
      normal_range:
        patient.labs.potassium: {min: 3.5, max: 5.5, type: float, unit: "mEq/L"}

    - rule_id: "DKA-HYPERKALEMIA-NO-K-REPLACE"
      condition: "patient.labs.potassium > 5.5"
      effect:
        type: FORBIDDEN
        actions: [give_potassium_iv, give_potassium_replacement, give_potassium_oral]
      evidence: "ADA 2024 Standards of Care, Section 16.2"
      severity: CRITICAL
      description: >
        In DKA with K+ > 5.5, additional potassium replacement can cause 
        fatal cardiac arrhythmias. Insulin itself will lower K+ by driving 
        it intracellularly. Monitor ECG for peaked T waves.
      condition_variables: ["patient.labs.potassium"]
      trigger_range:
        patient.labs.potassium: {min: 5.6, max: 8.0, type: float, unit: "mEq/L"}
      normal_range:
        patient.labs.potassium: {min: 3.5, max: 5.5, type: float, unit: "mEq/L"}
```

**Graph YAML 파서를 수정**하여 `conditional_rules`를 읽을 수 있게 한다.
기존 파서가 모르는 필드를 무시하면 하위 호환 유지.

### Step 1.4: 스키마 validation 스크립트

```python
# scripts/validate_conditional_rules.py
"""
모든 graph YAML의 conditional_rules가 스키마를 만족하는지 검증.
"""
def validate():
    for graph_path in Path("cpg_model/graphs/").glob("*.yaml"):
        graph = load_graph(graph_path)
        for node in graph.nodes:
            for rule in node.get("conditional_rules", []):
                assert rule.get("rule_id"), f"Missing rule_id in {graph_path}:{node.id}"
                assert rule.get("condition"), f"Missing condition in rule {rule['rule_id']}"
                assert rule.get("effect", {}).get("type") in ["FORBIDDEN", "REQUIRED", "BEFORE", "WITHIN"]
                assert rule.get("effect", {}).get("actions"), f"Empty actions in {rule['rule_id']}"
                assert rule.get("evidence"), f"Missing evidence in {rule['rule_id']}"
                assert rule.get("severity") in ["CRITICAL", "HIGH", "MODERATE", "LOW"]
                assert rule.get("condition_variables"), f"Missing condition_variables in {rule['rule_id']}"
                assert rule.get("trigger_range"), f"Missing trigger_range in {rule['rule_id']}"
                assert rule.get("normal_range"), f"Missing normal_range in {rule['rule_id']}"
                
                # condition이 문법적으로 올바른지 (compile만, eval은 안 함)
                try:
                    compile(rule["condition"], "<rule>", "eval")
                except SyntaxError as e:
                    raise ValueError(f"Invalid condition in {rule['rule_id']}: {e}")
    print("All conditional rules valid")
```

---

## Phase 2: 기존 14개 Graph에 Conditional Rules 추가 (2일)

각 graph에 conditional rules를 추가한다. 아래는 graph별 추가할 rule의 **사양**이다.
rule_id 명명 규칙: `{GRAPH_SHORT}-{MECHANISM}-{NUMBER}`

### 2.1 ada_dka_management (기존 19 FORBIDDEN + 12 BEFORE)

추가할 conditional rules:

```yaml
# Node: potassium_replacement_first
- rule_id: "DKA-HYPOK-INSULIN-GATE"
  condition: "patient.labs.potassium < 3.3"
  effect: {type: FORBIDDEN, actions: [start_insulin_infusion, give_insulin_bolus]}
  evidence: "ADA 2024, Section 16.2"
  severity: CRITICAL
  condition_variables: [patient.labs.potassium]
  trigger_range: {patient.labs.potassium: {min: 1.5, max: 3.2, type: float}}
  normal_range: {patient.labs.potassium: {min: 3.5, max: 5.5, type: float}}

- rule_id: "DKA-HYPERK-NO-K-REPLACE"
  condition: "patient.labs.potassium > 5.5"
  effect: {type: FORBIDDEN, actions: [give_potassium_iv, give_potassium_replacement]}
  evidence: "ADA 2024, Section 16.2"
  severity: CRITICAL
  condition_variables: [patient.labs.potassium]
  trigger_range: {patient.labs.potassium: {min: 5.6, max: 8.0, type: float}}
  normal_range: {patient.labs.potassium: {min: 3.5, max: 5.5, type: float}}

# Node: insulin_therapy
- rule_id: "DKA-EUGLY-SGLT2-DEXTROSE"
  condition: "'sglt2_inhibitor' in patient.medications"
  effect: {type: REQUIRED, actions: [add_dextrose_to_iv, stop_sglt2_inhibitor]}
  evidence: "ADA 2024, Section 16.2; FDA Safety Communication 2015"
  severity: HIGH
  condition_variables: [patient.medications]
  trigger_range: {patient.medications: {contains: "sglt2_inhibitor", type: list_contains}}
  normal_range: {patient.medications: {not_contains: "sglt2_inhibitor", type: list_not_contains}}

- rule_id: "DKA-EUGLY-NO-DISCHARGE-NORMAL-GLU"
  condition: "'sglt2_inhibitor' in patient.medications and patient.labs.glucose < 250"
  effect: {type: FORBIDDEN, actions: [discharge_based_on_normal_glucose]}
  evidence: "ADA 2024; Peters AL et al, J Clin Endocrinol Metab 2015"
  severity: CRITICAL
  condition_variables: [patient.medications, patient.labs.glucose]
  trigger_range: {patient.medications: {contains: "sglt2_inhibitor"}, patient.labs.glucose: {min: 80, max: 249, type: float}}
  normal_range: {patient.labs.glucose: {min: 250, max: 800, type: float}}

# Node: severe_dka_pathway  
- rule_id: "DKA-PEDIATRIC-NO-RAPID-FLUID"
  condition: "patient.age < 18"
  effect: {type: FORBIDDEN, actions: [give_rapid_fluid_bolus, give_bolus_over_20ml_kg_h]}
  evidence: "ISPAD 2022, Chapter 11; Glaser 2001 NEJM"
  severity: CRITICAL
  condition_variables: [patient.age]
  trigger_range: {patient.age: {min: 1, max: 17, type: int}}
  normal_range: {patient.age: {min: 18, max: 100, type: int}}

- rule_id: "DKA-PEDIATRIC-NO-BICARB"
  condition: "patient.age < 18"
  effect: {type: FORBIDDEN, actions: [give_bicarbonate]}
  evidence: "ISPAD 2022, Chapter 11"
  severity: HIGH
  condition_variables: [patient.age]
  trigger_range: {patient.age: {min: 1, max: 17, type: int}}
  normal_range: {patient.age: {min: 18, max: 100, type: int}}

- rule_id: "DKA-METFORMIN-STOP"
  condition: "'metformin' in patient.medications"
  effect: {type: REQUIRED, actions: [stop_metformin]}
  evidence: "ADA 2024; DeFronzo RA et al, Metformin-associated lactic acidosis"
  severity: HIGH
  condition_variables: [patient.medications]
  trigger_range: {patient.medications: {contains: "metformin", type: list_contains}}
  normal_range: {patient.medications: {not_contains: "metformin", type: list_not_contains}}

- rule_id: "DKA-PREGNANCY-AGGRESSIVE-FLUID"
  condition: "'pregnancy' in patient.comorbidities"
  effect: {type: REQUIRED, actions: [continuous_fetal_monitoring, consult_obstetrics]}
  evidence: "ADA 2024; ACOG Practice Bulletin 2018"
  severity: HIGH
  condition_variables: [patient.comorbidities]
  trigger_range: {patient.comorbidities: {contains: "pregnancy", type: list_contains}}
  normal_range: {patient.comorbidities: {not_contains: "pregnancy", type: list_not_contains}}
```

### 2.2 aha_chest_pain (기존 13 FORBIDDEN + 10 BEFORE)

```yaml
# Node: stemi_pathway
- rule_id: "ACS-COCAINE-NO-BB"
  condition: "'cocaine_use' in patient.comorbidities or 'cocaine' in patient.history"
  effect: {type: FORBIDDEN, actions: [give_beta_blocker, give_metoprolol, give_atenolol, give_propranolol]}
  evidence: "AHA/ACC 2014 NSTEMI Guidelines, Section 5.3.1"
  severity: CRITICAL
  condition_variables: [patient.comorbidities]
  trigger_range: {patient.comorbidities: {contains: "cocaine_use", type: list_contains}}
  normal_range: {patient.comorbidities: {not_contains: "cocaine_use", type: list_not_contains}}

- rule_id: "ACS-LATE-NO-FIBRINOLYTIC"
  condition: "patient.presentation.symptom_onset_hours > 12"
  effect: {type: FORBIDDEN, actions: [give_fibrinolytic, give_tenecteplase, give_alteplase]}
  evidence: "ESC 2023 ACS Guidelines; FTT Collaborative, Lancet 1994"
  severity: HIGH
  condition_variables: [patient.presentation.symptom_onset_hours]
  trigger_range: {patient.presentation.symptom_onset_hours: {min: 13, max: 72, type: float}}
  normal_range: {patient.presentation.symptom_onset_hours: {min: 0, max: 12, type: float}}

- rule_id: "ACS-DISSECTION-NO-ANTICOAG"
  condition: "'aortic_dissection_suspected' in patient.comorbidities or 'widened_mediastinum' in patient.imaging"
  effect: {type: FORBIDDEN, actions: [give_heparin, give_antiplatelet, give_aspirin, give_thrombolytic, give_anticoagulation]}
  evidence: "AHA/ACC 2022 Aortic Disease Guidelines, Section 7.2"
  severity: CRITICAL
  condition_variables: [patient.comorbidities]
  trigger_range: {patient.comorbidities: {contains: "aortic_dissection_suspected", type: list_contains}}
  normal_range: {patient.comorbidities: {not_contains: "aortic_dissection_suspected", type: list_not_contains}}

- rule_id: "ACS-CKD-ENOXAPARIN-ADJUST"
  condition: "patient.labs.egfr < 30"
  effect: {type: FORBIDDEN, actions: [give_enoxaparin_full_dose, give_enoxaparin_1mg_kg_bid]}
  evidence: "AHA/ACC 2014; Spinler SA, Pharmacotherapy 2003"
  severity: HIGH
  condition_variables: [patient.labs.egfr]
  trigger_range: {patient.labs.egfr: {min: 5, max: 29, type: float}}
  normal_range: {patient.labs.egfr: {min: 30, max: 120, type: float}}

- rule_id: "ACS-RV-INFARCT-NO-NITRATE"
  condition: "'rv_infarct' in patient.comorbidities or 'inferior_stemi' in patient.ecg_findings"
  effect: {type: FORBIDDEN, actions: [give_nitroglycerin, give_nitrates, give_morphine]}
  evidence: "AHA/ACC 2013 STEMI Guidelines, Section 5.1"
  severity: CRITICAL
  condition_variables: [patient.comorbidities]
  trigger_range: {patient.comorbidities: {contains: "rv_infarct", type: list_contains}}
  normal_range: {patient.comorbidities: {not_contains: "rv_infarct", type: list_not_contains}}

# Node: nste_acs_pathway
- rule_id: "ACS-ASPIRIN-ALLERGY-NO-ASPIRIN"
  condition: "'aspirin' in patient.allergies"
  effect: {type: FORBIDDEN, actions: [give_aspirin, give_nsaid]}
  evidence: "AHA/ACC 2014 NSTEMI Guidelines"
  severity: CRITICAL
  condition_variables: [patient.allergies]
  trigger_range: {patient.allergies: {contains: "aspirin", type: list_contains}}
  normal_range: {patient.allergies: {not_contains: "aspirin", type: list_not_contains}}

- rule_id: "ACS-TICAGRELOR-CABG-WASHOUT"
  condition: "'ticagrelor_recent' in patient.medications"
  effect: {type: FORBIDDEN, actions: [proceed_to_cabg_within_5_days]}
  evidence: "ACC/AHA 2016 Dual Antiplatelet Therapy Duration; PLATO Trial"
  severity: HIGH
  condition_variables: [patient.medications]
  trigger_range: {patient.medications: {contains: "ticagrelor_recent", type: list_contains}}
  normal_range: {patient.medications: {not_contains: "ticagrelor_recent", type: list_not_contains}}
```

### 2.3 aha_heart_failure (기존 9 FORBIDDEN)

```yaml
- rule_id: "HF-HYPERK-NO-RAAS"
  condition: "patient.labs.potassium > 5.5"
  effect: {type: FORBIDDEN, actions: [initiate_arni, initiate_ace_or_arb_or_arni, initiate_mra, give_potassium_supplement]}
  evidence: "AHA/ACC 2022 HF Guidelines, Section 7.3.2"
  severity: CRITICAL
  condition_variables: [patient.labs.potassium]
  trigger_range: {patient.labs.potassium: {min: 5.6, max: 8.0, type: float}}
  normal_range: {patient.labs.potassium: {min: 3.5, max: 5.0, type: float}}

- rule_id: "HF-BRADYCARDIA-NO-BB-INCREASE"
  condition: "patient.vitals.heart_rate < 50 or 'av_block' in patient.comorbidities"
  effect: {type: FORBIDDEN, actions: [increase_beta_blocker, add_digoxin, add_ivabradine]}
  evidence: "AHA/ACC 2022 HF Guidelines, Section 7.3.1"
  severity: HIGH
  condition_variables: [patient.vitals.heart_rate, patient.comorbidities]
  trigger_range: {patient.vitals.heart_rate: {min: 30, max: 49, type: int}}
  normal_range: {patient.vitals.heart_rate: {min: 60, max: 100, type: int}}

- rule_id: "HF-ACUTE-PULMONARY-EDEMA-NO-BB"
  condition: "patient.vitals.spo2 < 90 and 'bilateral_crackles' in patient.exam_findings"
  effect: {type: FORBIDDEN, actions: [give_high_dose_beta_blocker, give_iv_metoprolol_in_acute_failure]}
  evidence: "AHA/ACC 2022 HF Guidelines, Section 10.1"
  severity: CRITICAL
  condition_variables: [patient.vitals.spo2, patient.exam_findings]
  trigger_range: {patient.vitals.spo2: {min: 60, max: 89, type: int}}
  normal_range: {patient.vitals.spo2: {min: 92, max: 100, type: int}}

- rule_id: "HF-NSAID-FORBIDDEN"
  condition: "'nsaid_use' in patient.medications or 'ibuprofen' in patient.medications"
  effect: {type: REQUIRED, actions: [discontinue_nsaid, give_acetaminophen_alternative]}
  evidence: "AHA/ACC 2022 HF Guidelines, Class III (Harm)"
  severity: HIGH
  condition_variables: [patient.medications]
  trigger_range: {patient.medications: {contains: "nsaid_use", type: list_contains}}
  normal_range: {patient.medications: {not_contains: "nsaid_use", type: list_not_contains}}

- rule_id: "HF-OVERDIURESIS-STOP"
  condition: "patient.labs.bun_cr_ratio > 20 and patient.vitals.sbp_orthostatic_drop > 20"
  effect: {type: FORBIDDEN, actions: [give_high_dose_diuretics, increase_furosemide, add_metolazone]}
  evidence: "AHA/ACC 2022 HF Guidelines, Section 10.2; Testani JM, JACC 2011"
  severity: HIGH
  condition_variables: [patient.labs.bun_cr_ratio, patient.vitals.sbp_orthostatic_drop]
  trigger_range: {patient.labs.bun_cr_ratio: {min: 21, max: 60, type: float}, patient.vitals.sbp_orthostatic_drop: {min: 21, max: 60, type: float}}
  normal_range: {patient.labs.bun_cr_ratio: {min: 10, max: 20, type: float}, patient.vitals.sbp_orthostatic_drop: {min: 0, max: 10, type: float}}
```

### 2.4 aha_stroke (기존 15 FORBIDDEN)

```yaml
- rule_id: "STROKE-BP-UNCONTROLLED-NO-TPA"
  condition: "patient.vitals.sbp > 185 or patient.vitals.dbp > 110"
  effect: {type: FORBIDDEN, actions: [give_alteplase, give_tpa]}
  evidence: "AHA/ASA 2019 Acute Ischemic Stroke Guidelines, Section 3.5"
  severity: CRITICAL
  condition_variables: [patient.vitals.sbp, patient.vitals.dbp]
  trigger_range: {patient.vitals.sbp: {min: 186, max: 260, type: int}}
  normal_range: {patient.vitals.sbp: {min: 100, max: 185, type: int}}

- rule_id: "STROKE-SEIZURE-MIMIC-NO-TPA"
  condition: "'seizure_at_onset' in patient.history or 'todds_paralysis' in patient.comorbidities"
  effect: {type: FORBIDDEN, actions: [give_alteplase_without_ruling_out_mimic, give_tpa_for_todds_paralysis]}
  evidence: "AHA/ASA 2019, Section 3.4 Stroke Mimics"
  severity: HIGH
  condition_variables: [patient.history]
  trigger_range: {patient.history: {contains: "seizure_at_onset", type: list_contains}}
  normal_range: {patient.history: {not_contains: "seizure_at_onset", type: list_not_contains}}

- rule_id: "STROKE-WARFARIN-PCC-PREFERRED"
  condition: "'warfarin' in patient.medications and 'intracerebral_hemorrhage' in patient.imaging"
  effect: {type: FORBIDDEN, actions: [give_ffp_as_sole_reversal, delay_reversal_for_inr_result]}
  evidence: "AHA/ASA 2022 ICH Guidelines, Section 5.2; Steiner T, Stroke 2016"
  severity: HIGH
  condition_variables: [patient.medications, patient.imaging]
  trigger_range: {patient.medications: {contains: "warfarin"}, patient.imaging: {contains: "intracerebral_hemorrhage"}}
  normal_range: {patient.medications: {not_contains: "warfarin"}}

- rule_id: "STROKE-PREGNANCY-NO-ACEI"
  condition: "'pregnancy' in patient.comorbidities"
  effect: {type: FORBIDDEN, actions: [give_ace_inhibitor, give_arb, give_nitroprusside]}
  evidence: "ACOG 2020; AHA/ASA 2019 Secondary Prevention"
  severity: CRITICAL
  condition_variables: [patient.comorbidities]
  trigger_range: {patient.comorbidities: {contains: "pregnancy", type: list_contains}}
  normal_range: {patient.comorbidities: {not_contains: "pregnancy", type: list_not_contains}}
```

### 2.5 atrial_fibrillation (기존 1 FORBIDDEN + 1 BEFORE)

```yaml
- rule_id: "AF-WPW-NO-AV-BLOCKER"
  condition: "'wpw_syndrome' in patient.comorbidities"
  effect: {type: FORBIDDEN, actions: [give_diltiazem, give_verapamil, give_digoxin, give_adenosine, give_beta_blocker_iv]}
  evidence: "AHA/ACC/HRS 2023 AF Guidelines, Section 7.3.4.1"
  severity: CRITICAL
  condition_variables: [patient.comorbidities]
  trigger_range: {patient.comorbidities: {contains: "wpw_syndrome", type: list_contains}}
  normal_range: {patient.comorbidities: {not_contains: "wpw_syndrome", type: list_not_contains}}

- rule_id: "AF-CARDIOVERSION-ANTICOAG-GATE"
  condition: "patient.presentation.af_duration_hours > 48"
  effect: {type: FORBIDDEN, actions: [perform_cardioversion_without_anticoag, perform_cardioversion_without_tee]}
  evidence: "AHA/ACC/HRS 2023 AF Guidelines, Section 6.2"
  severity: CRITICAL
  condition_variables: [patient.presentation.af_duration_hours]
  trigger_range: {patient.presentation.af_duration_hours: {min: 49, max: 720, type: float}}
  normal_range: {patient.presentation.af_duration_hours: {min: 0, max: 48, type: float}}

- rule_id: "AF-AMIODARONE-THYROID-CHECK"
  condition: "'amiodarone_use_chronic' in patient.medications"
  effect: {type: FORBIDDEN, actions: [increase_amiodarone_dose, add_amiodarone_loading, give_amiodarone_iv]}
  evidence: "AHA/ACC/HRS 2023 AF Guidelines; Bogazzi F, Thyroid 2012"
  severity: HIGH
  condition_variables: [patient.medications]
  trigger_range: {patient.medications: {contains: "amiodarone_use_chronic", type: list_contains}}
  normal_range: {patient.medications: {not_contains: "amiodarone_use_chronic", type: list_not_contains}}
```

### 2.6-2.14: 나머지 9개 graph

나머지 graph (ssc_sepsis_hour1, kdigo_aki_full, kdigo_contrast_aki, pulmonary_embolism, cap_pneumonia, copd_exacerbation, gi_bleeding, hypertensive_emergency, universal_clinical_safety)에도 동일한 패턴으로 conditional rules를 추가한다.

**각 graph에 추가할 rule 사양은 이전 세션의 시나리오 설계서 (artifact: scenario-expansion-100)의 Category A/C/D 시나리오의 forbidden_actions + trap_description을 참조하라.** 각 시나리오의 trap이 작동하려면 해당 rule이 graph에 있어야 한다.

예를 들어:
- `sepsis_anaphylaxis_cross_reactivity_trap`의 forbidden [give_cephalosporin] → ssc_sepsis_hour1에 "SEPSIS-PENICILLIN-ANAPHYLAXIS-NO-CEPH" rule 추가
- `pe_doac_obesity_trap`의 forbidden [give_doac] → pulmonary_embolism에 "PE-OBESITY-NO-DOAC" rule 추가
- `copd_pneumothorax_niv_trap`의 forbidden [initiate_niv] → copd_exacerbation에 "COPD-PNEUMOTHORAX-NO-NIV" rule 추가

**핵심 원칙: 시나리오에 수동으로 forbidden을 넣는 대신, graph에 conditional rule을 넣고 시나리오는 patient context만 정의한다.**

각 graph에 최소 5개, 최대 15개 conditional rule을 목표로 한다. 14 graphs × 평균 8 rules = ~112 rules 총.

---

## Phase 3: 6개 신규 Graph 작성 (4일)

각 graph는 다음을 포함:
- nodes (decision/action nodes with edges)
- unconditional forbidden_actions (graph-level)
- unconditional sequence_rules (BEFORE)
- **conditional_rules** (patient context 기반)
- evidence links (guideline 원문 참조)

### 3.1 Anaphylaxis (`anaphylaxis_management`)

Source guideline: WAO 2024 Anaphylaxis Guidelines + EAACI 2024

```yaml
# cpg_model/graphs/anaphylaxis_management.yaml

graph_id: anaphylaxis_management
guideline: "WAO 2024 Anaphylaxis Guidelines; EAACI Anaphylaxis Guidelines 2024"
version: "1.0"
entry_node: initial_recognition

nodes:
  initial_recognition:
    type: assessment
    description: "Recognize anaphylaxis: acute onset skin/mucosal + respiratory/cardiovascular compromise"
    expected_actions: [assess_vital_signs, assess_airway, assess_breathing, identify_trigger]
    forbidden_actions: [discharge_without_observation]
    
  epinephrine_administration:
    type: treatment
    description: "Epinephrine IM 0.01 mg/kg (max 0.5mg adults) into anterolateral thigh"
    expected_actions: [give_epinephrine_im, document_time_of_epinephrine]
    forbidden_actions:
      - give_epinephrine_iv_bolus        # IV bolus → cardiac arrest
      - give_epinephrine_subcutaneous    # SC too slow absorption
      - give_antihistamine_as_first_line # Antihistamine does NOT treat anaphylaxis
      - give_corticosteroid_as_first_line
      - withhold_epinephrine
      - delay_epinephrine_for_antihistamine
    sequence_rules:
      - [give_epinephrine_im, give_antihistamine]  # epi BEFORE antihistamine
      - [give_epinephrine_im, give_corticosteroid]  # epi BEFORE steroid
    conditional_rules:
      - rule_id: "ANA-BETA-BLOCKER-GLUCAGON"
        condition: "'beta_blocker' in patient.medications"
        effect: {type: REQUIRED, actions: [give_glucagon]}
        evidence: "WAO 2024, Section 5.3; Brown SGA, JACI 2004"
        severity: HIGH
        description: "Beta-blocker patients may not respond to epinephrine. Glucagon bypasses beta-blockade."
        condition_variables: [patient.medications]
        trigger_range: {patient.medications: {contains: "beta_blocker", type: list_contains}}
        normal_range: {patient.medications: {not_contains: "beta_blocker", type: list_not_contains}}
        
      - rule_id: "ANA-PREGNANCY-LEFT-LATERAL"
        condition: "'pregnancy' in patient.comorbidities"
        effect: {type: REQUIRED, actions: [position_left_lateral_decubitus]}
        evidence: "WAO 2024; ACOG 2020"
        severity: HIGH
        condition_variables: [patient.comorbidities]
        trigger_range: {patient.comorbidities: {contains: "pregnancy", type: list_contains}}
        normal_range: {patient.comorbidities: {not_contains: "pregnancy", type: list_not_contains}}

  fluid_resuscitation:
    type: treatment
    description: "IV crystalloid 20ml/kg bolus for hypotension unresponsive to epinephrine"
    expected_actions: [establish_iv_access, give_crystalloid_bolus]
    
  monitoring_and_disposition:
    type: disposition
    description: "Observe minimum 4-6 hours (biphasic reactions in up to 20%)"
    expected_actions: [observe_minimum_4_hours, prescribe_epinephrine_autoinjector, allergy_referral]
    forbidden_actions:
      - discharge_before_4_hours
      - discharge_without_autoinjector_prescription

edges:
  - {from: initial_recognition, to: epinephrine_administration}
  - {from: epinephrine_administration, to: fluid_resuscitation, condition: "hypotension_persistent"}
  - {from: epinephrine_administration, to: monitoring_and_disposition}
  - {from: fluid_resuscitation, to: monitoring_and_disposition}
```

시나리오 YAML 파일도 생성: `configs/scenarios/anaphylaxis_scenarios.yaml`

### 3.2 ACLS (`acls_cardiac_arrest`)

Source: AHA 2025 ACLS Guidelines

핵심 구조:
- assess_rhythm node → shockable (VF/pVT) vs non-shockable (asystole/PEA) 분기
- shockable pathway: defibrillation → CPR 2min → rhythm check → epinephrine q3-5min → amiodarone
- non-shockable pathway: CPR → epinephrine immediately → rhythm check q2min
- reversible causes: Hs and Ts checklist

핵심 conditional rules:
```yaml
- rule_id: "ACLS-SHOCKABLE-DEFIB-FIRST"
  condition: "'vf' in patient.rhythm or 'pvt' in patient.rhythm"
  effect: {type: BEFORE, actions: [defibrillate, give_epinephrine]}
  # VF/pVT에서는 제세동이 epinephrine보다 먼저
  
- rule_id: "ACLS-NONSHOCKABLE-EPI-IMMEDIATE"
  condition: "'asystole' in patient.rhythm or 'pea' in patient.rhythm"
  effect: {type: REQUIRED, actions: [give_epinephrine_immediately]}
  # Asystole/PEA에서는 epinephrine 즉시

- rule_id: "ACLS-HYPERKALEMIA-CALCIUM"
  condition: "patient.labs.potassium > 6.5"
  effect: {type: REQUIRED, actions: [give_calcium_chloride, give_sodium_bicarbonate]}
  
- rule_id: "ACLS-HYPOTHERMIA-NO-DRUGS-UNTIL-WARM"
  condition: "patient.vitals.temperature < 30"
  effect: {type: FORBIDDEN, actions: [give_epinephrine, give_amiodarone]}
  # Core temp <30°C: 약물 대사 안 됨, 축적 위험
  
- rule_id: "ACLS-TENSION-PNEUMO-DECOMPRESS"
  condition: "'tension_pneumothorax' in patient.exam_findings"
  effect: {type: REQUIRED, actions: [perform_needle_decompression]}
  
- rule_id: "ACLS-TAMPONADE-PERICARDIOCENTESIS"
  condition: "'cardiac_tamponade' in patient.exam_findings"
  effect: {type: REQUIRED, actions: [perform_pericardiocentesis]}
```

**전체 graph YAML을 위와 동일한 상세도로 작성하라.**

### 3.3 Status Epilepticus (`status_epilepticus`)

Source: AES 2024 Guidelines

핵심 구조:
- stabilization (0-5min): ABCs, glucose check
- first_line (5-20min): benzodiazepine (lorazepam/midazolam)
- second_line (20-40min): levetiracetam, fosphenytoin, or valproate
- third_line (>40min): propofol, midazolam infusion, or pentobarbital
- 순서가 엄격한 BEFORE constraints

핵심 conditional rules:
```yaml
- rule_id: "SE-PREGNANCY-NO-VALPROATE"
  condition: "'pregnancy' in patient.comorbidities"
  effect: {type: FORBIDDEN, actions: [give_valproate, give_valproic_acid]}
  evidence: "AES 2024; FDA Black Box Warning"

- rule_id: "SE-HEPATIC-NO-VALPROATE"  
  condition: "'liver_disease' in patient.comorbidities"
  effect: {type: FORBIDDEN, actions: [give_valproate]}

- rule_id: "SE-ALCOHOL-WITHDRAWAL-BENZO-PREFERRED"
  condition: "'alcohol_withdrawal' in patient.history"
  effect: {type: REQUIRED, actions: [give_benzodiazepine_high_dose]}

- rule_id: "SE-HYPOGLYCEMIA-GLUCOSE-FIRST"
  condition: "patient.labs.glucose < 60"
  effect: {type: BEFORE, actions: [give_dextrose, give_antiepileptic]}
```

### 3.4 Asthma Exacerbation (`gina_asthma_exacerbation`)

Source: GINA 2024

핵심 conditional rules:
```yaml
- rule_id: "ASTHMA-SEVERE-MGSO4"
  condition: "patient.vitals.pef_percent < 25 or patient.vitals.spo2 < 92"
  effect: {type: REQUIRED, actions: [give_magnesium_sulfate_iv]}

- rule_id: "ASTHMA-NEAR-FATAL-EPINEPHRINE"
  condition: "'near_fatal_asthma' in patient.history or patient.vitals.spo2 < 85"
  effect: {type: REQUIRED, actions: [give_epinephrine_im, prepare_intubation]}

- rule_id: "ASTHMA-NO-SEDATIVES"
  condition: True  # 무조건 (asthma exacerbation에서)
  effect: {type: FORBIDDEN, actions: [give_sedative, give_benzodiazepine, give_morphine]}
  # 호흡 억제 위험

- rule_id: "ASTHMA-BB-CONTRAINDICATED"
  condition: True
  effect: {type: FORBIDDEN, actions: [give_beta_blocker, give_propranolol]}
```

### 3.5 Meningitis (`idsa_meningitis`)

Source: IDSA 2024 Bacterial Meningitis Guidelines

핵심 conditional rules:
```yaml
- rule_id: "MENING-ABX-BEFORE-LP"
  condition: "patient.presentation.delay_to_lp_minutes > 30"
  effect: {type: FORBIDDEN, actions: [delay_antibiotics_for_lp]}
  # LP 지연되면 항생제 먼저

- rule_id: "MENING-DEXA-BEFORE-OR-WITH-ABX"
  condition: "'suspected_pneumococcal' in patient.presentation"
  effect: {type: BEFORE, actions: [give_dexamethasone, give_antibiotics]}
  # 폐렴구균 의심 시 dexamethasone은 항생제 직전 또는 동시

- rule_id: "MENING-IMMUNOCOMP-LISTERIA"
  condition: "patient.age > 50 or 'immunocompromised' in patient.comorbidities or 'pregnancy' in patient.comorbidities"
  effect: {type: REQUIRED, actions: [add_ampicillin_for_listeria]}
  
- rule_id: "MENING-PENICILLIN-ALLERGY-ALT"
  condition: "'penicillin_anaphylaxis' in patient.allergies"
  effect: {type: FORBIDDEN, actions: [give_ampicillin, give_penicillin]}
```

### 3.6 Overdose / Toxicology (`toxicology_management`)

Source: AACT Guidelines + UpToDate Toxicology

이 graph는 구조가 다름 — agent별이 아니라 **toxin class별 분기**.

핵심 conditional rules:
```yaml
- rule_id: "TOX-ACETAMINOPHEN-NAC"
  condition: "'acetaminophen_overdose' in patient.presentation"
  effect: {type: REQUIRED, actions: [give_n_acetylcysteine, order_acetaminophen_level, order_liver_function]}

- rule_id: "TOX-BENZO-OD-NO-FLUMAZENIL-CHRONIC"
  condition: "'chronic_benzodiazepine_use' in patient.medications and 'benzodiazepine_overdose' in patient.presentation"
  effect: {type: FORBIDDEN, actions: [give_flumazenil]}
  # Chronic user에게 flumazenil → withdrawal seizure

- rule_id: "TOX-OPIOID-NALOXONE"
  condition: "'opioid_overdose' in patient.presentation"
  effect: {type: REQUIRED, actions: [give_naloxone]}

- rule_id: "TOX-TCA-NO-PHYSOSTIGMINE"
  condition: "'tca_overdose' in patient.presentation"
  effect: {type: FORBIDDEN, actions: [give_physostigmine]}
  # TCA + physostigmine → asystole

- rule_id: "TOX-TCA-BICARB"
  condition: "'tca_overdose' in patient.presentation and patient.vitals.qrs_ms > 100"
  effect: {type: REQUIRED, actions: [give_sodium_bicarbonate]}

- rule_id: "TOX-METHANOL-FOMEPIZOLE"
  condition: "'methanol_ingestion' in patient.presentation or 'ethylene_glycol_ingestion' in patient.presentation"
  effect: {type: REQUIRED, actions: [give_fomepizole_or_ethanol, consult_nephrology_for_dialysis]}

- rule_id: "TOX-DIGOXIN-FAB"
  condition: "'digoxin_toxicity' in patient.presentation"
  effect: {type: REQUIRED, actions: [give_digoxin_fab_fragments]}
  
- rule_id: "TOX-ORGANOPHOSPHATE-ATROPINE"
  condition: "'organophosphate_poisoning' in patient.presentation"
  effect: {type: REQUIRED, actions: [give_atropine, give_pralidoxime]}
```

**위 6개 graph를 모두 전체 YAML로 작성하라.** 각 graph에:
- 최소 4개 node
- 최소 8개 conditional rule (trigger_range + normal_range 포함)
- 모든 rule에 evidence 명시
- edge 정의

시나리오 YAML 파일도 각 graph당 1개씩 생성 (PatientGenerator가 채울 것이므로 일단 빈 template):
- `configs/scenarios/anaphylaxis_scenarios.yaml`
- `configs/scenarios/acls_scenarios.yaml`
- `configs/scenarios/status_epilepticus_scenarios.yaml`
- `configs/scenarios/asthma_exacerbation_scenarios.yaml`
- `configs/scenarios/meningitis_scenarios.yaml`
- `configs/scenarios/toxicology_scenarios.yaml`

---

## Phase 4: ConstraintDerivationEngine 구현 (1일)

### 파일: `cpg_model/constraint_derivation.py`

```python
"""
Constraint Derivation Engine

CPG graph + patient context → derived constraint set with provenance.
"""
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple, Any
from pathlib import Path
import yaml

@dataclass
class DerivedConstraint:
    """단일 도출된 constraint"""
    constraint_type: str    # FORBIDDEN, REQUIRED, BEFORE, WITHIN
    actions: List[str]      # 관련 action(s)
    provenance: str         # "graph:{graph_id}:node:{node_id}:rule:{rule_id}"
    evidence: str           # guideline 원문 참조
    severity: str           # CRITICAL, HIGH, MODERATE, LOW
    description: str        # 사람이 읽을 수 있는 설명
    condition_met: str      # 어떤 조건이 만족되었는지 ("patient.labs.potassium=2.9 < 3.3")
    is_conditional: bool    # True=conditional rule에서 도출, False=unconditional

@dataclass
class DerivedConstraintSet:
    """한 시나리오에 대한 전체 도출 constraint 집합"""
    scenario_id: str
    graph_id: str
    forbidden: List[DerivedConstraint] = field(default_factory=list)
    required: List[DerivedConstraint] = field(default_factory=list)
    before: List[DerivedConstraint] = field(default_factory=list)
    within: List[DerivedConstraint] = field(default_factory=list)
    
    # 통계
    total_rules_evaluated: int = 0
    total_rules_triggered: int = 0
    
    def add(self, constraint: DerivedConstraint):
        getattr(self, constraint.constraint_type.lower()).append(constraint)
    
    def to_yaml(self) -> dict:
        """YAML로 직렬화 (시나리오 YAML에 _derived_constraints로 기록)"""
        ...
    
    def to_audit_row(self) -> dict:
        """Rule Coverage Audit Matrix 한 줄"""
        ...

class ConstraintDerivationEngine:
    """
    메인 엔진: graph + patient → DerivedConstraintSet
    """
    
    def __init__(self):
        self.allergy_drug_map = self._load_allergy_drug_map()
    
    def derive(self, graph: dict, patient: dict, scenario_id: str = "") -> DerivedConstraintSet:
        """
        Args:
            graph: loaded graph YAML (dict)
            patient: patient context (dict with labs, medications, comorbidities, allergies, vitals, etc.)
            scenario_id: for logging
        
        Returns:
            DerivedConstraintSet with full provenance
        """
        result = DerivedConstraintSet(scenario_id=scenario_id, graph_id=graph.get("graph_id", ""))
        
        for node_id, node in graph.get("nodes", {}).items():
            # 1. Unconditional forbidden (graph-level)
            for action in node.get("forbidden_actions", []):
                result.add(DerivedConstraint(
                    constraint_type="FORBIDDEN",
                    actions=[action],
                    provenance=f"graph:{graph['graph_id']}:node:{node_id}:unconditional",
                    evidence=node.get("guideline_reference", ""),
                    severity="HARD",
                    description=f"Unconditionally forbidden in {node_id}",
                    condition_met="always",
                    is_conditional=False
                ))
            
            # 2. Unconditional sequence rules (BEFORE)
            for seq in node.get("sequence_rules", []):
                result.add(DerivedConstraint(
                    constraint_type="BEFORE",
                    actions=seq,  # [before_action, after_action]
                    provenance=f"graph:{graph['graph_id']}:node:{node_id}:sequence",
                    evidence=node.get("guideline_reference", ""),
                    severity="HARD",
                    description=f"{seq[0]} must precede {seq[1]}",
                    condition_met="always",
                    is_conditional=False
                ))
            
            # 3. Conditional rules — patient context 대입
            for rule in node.get("conditional_rules", []):
                result.total_rules_evaluated += 1
                
                if self._evaluate_condition(rule["condition"], patient):
                    result.total_rules_triggered += 1
                    
                    effect = rule["effect"]
                    condition_met_str = self._format_condition_met(rule["condition"], patient)
                    
                    result.add(DerivedConstraint(
                        constraint_type=effect["type"],
                        actions=effect["actions"],
                        provenance=f"graph:{graph['graph_id']}:node:{node_id}:rule:{rule['rule_id']}",
                        evidence=rule.get("evidence", ""),
                        severity=rule.get("severity", "HIGH"),
                        description=rule.get("description", ""),
                        condition_met=condition_met_str,
                        is_conditional=True
                    ))
        
        # 4. Allergy-based forbidden (generic)
        for allergy in patient.get("allergies", []):
            for drug in self.allergy_drug_map.get(allergy, []):
                result.add(DerivedConstraint(
                    constraint_type="FORBIDDEN",
                    actions=[f"give_{drug}"],
                    provenance=f"allergy_map:{allergy}",
                    evidence="Standard drug allergy cross-reactivity",
                    severity="CRITICAL",
                    description=f"Patient allergic to {allergy}, {drug} contraindicated",
                    condition_met=f"'{allergy}' in patient.allergies",
                    is_conditional=True
                ))
        
        return result
    
    def _evaluate_condition(self, condition: str, patient: dict) -> bool:
        """
        Safe evaluation of condition string.
        
        Supported patterns:
        - "patient.labs.potassium < 3.3"
        - "'cocaine_use' in patient.comorbidities"
        - "'sglt2_inhibitor' in patient.medications and patient.labs.glucose < 250"
        - "patient.age < 18"
        - "patient.vitals.sbp > 185 or patient.vitals.dbp > 110"
        """
        # PatientContext를 dot-accessible object로 변환
        namespace = {"patient": DotDict(patient)}
        try:
            return bool(eval(condition, {"__builtins__": {}}, namespace))
        except (KeyError, AttributeError, TypeError):
            return False
    
    def _format_condition_met(self, condition: str, patient: dict) -> str:
        """조건 만족 내역을 사람이 읽을 수 있게 포맷"""
        # 예: "patient.labs.potassium < 3.3" → "patient.labs.potassium=2.9 < 3.3"
        ...
    
    def _load_allergy_drug_map(self) -> Dict[str, List[str]]:
        """
        Allergy → contraindicated drug 매핑.
        
        이 매핑은 별도 YAML로 관리: cpg_model/allergy_drug_map.yaml
        """
        return {
            "penicillin": ["penicillin", "amoxicillin", "ampicillin"],
            "penicillin_anaphylaxis": ["penicillin", "amoxicillin", "ampicillin", 
                                       "cephalosporin", "ceftriaxone", "cefepime",
                                       "cefazolin", "ceftazidime"],
            "aspirin": ["aspirin"],
            "nsaids": ["ibuprofen", "naproxen", "ketorolac", "celecoxib"],
            "sulfa": ["trimethoprim_sulfamethoxazole", "sulfasalazine"],
            "ace_inhibitor_angioedema": ["enalapril", "lisinopril", "ramipril", "captopril"],
            "heparin_hit": ["heparin", "enoxaparin"],
            "vancomycin_red_man_syndrome": ["vancomycin_rapid_infusion"],
            # ... 확장
        }


class DotDict(dict):
    """dot notation으로 nested dict 접근 가능하게 하는 wrapper"""
    def __getattr__(self, key):
        val = self.get(key, None)
        if isinstance(val, dict):
            return DotDict(val)
        if isinstance(val, list):
            return val
        return val
    def __contains__(self, item):
        # list에서 'in' 연산 지원
        if isinstance(self, list):
            return item in list(self)
        return dict.__contains__(self, item)
```

### 테스트

```python
# tests/test_constraint_derivation.py

def test_dka_hypokalemia_insulin_gate():
    engine = ConstraintDerivationEngine()
    graph = load_graph("cpg_model/graphs/ada_dka_management.yaml")
    patient = {
        "age": 28, "sex": "M",
        "labs": {"potassium": 2.9, "glucose": 450, "ph": 7.15},
        "comorbidities": ["type_1_diabetes"],
        "allergies": [],
        "medications": []
    }
    result = engine.derive(graph, patient, "test_hypokalemia")
    
    # insulin이 forbidden으로 도출되어야 함
    forbidden_actions = [a for c in result.forbidden for a in c.actions]
    assert "start_insulin_infusion" in forbidden_actions
    assert "give_insulin_bolus" in forbidden_actions
    
    # provenance 확인
    insulin_constraint = [c for c in result.forbidden if "start_insulin_infusion" in c.actions][0]
    assert "DKA-HYPOK-INSULIN-GATE" in insulin_constraint.provenance
    assert "ADA 2024" in insulin_constraint.evidence

def test_dka_normal_potassium_no_gate():
    engine = ConstraintDerivationEngine()
    graph = load_graph("cpg_model/graphs/ada_dka_management.yaml")
    patient = {
        "age": 28, "sex": "M",
        "labs": {"potassium": 4.2, "glucose": 450, "ph": 7.15},
        "comorbidities": ["type_1_diabetes"],
        "allergies": [],
        "medications": []
    }
    result = engine.derive(graph, patient, "test_normal_k")
    
    # conditional insulin gate는 trigger 안 됨
    conditional_forbidden = [c for c in result.forbidden if c.is_conditional and "start_insulin_infusion" in c.actions]
    assert len(conditional_forbidden) == 0

def test_cocaine_acs_no_beta_blocker():
    engine = ConstraintDerivationEngine()
    graph = load_graph("cpg_model/graphs/aha_chest_pain.yaml")
    patient = {
        "age": 32, "sex": "M",
        "comorbidities": ["cocaine_use"],
        "allergies": [],
        "medications": []
    }
    result = engine.derive(graph, patient, "test_cocaine_acs")
    
    forbidden_actions = [a for c in result.forbidden for a in c.actions]
    assert "give_beta_blocker" in forbidden_actions
    assert "give_metoprolol" in forbidden_actions

def test_provenance_chain_complete():
    """모든 derived constraint에 provenance, evidence, severity가 있는지"""
    engine = ConstraintDerivationEngine()
    for graph_path in Path("cpg_model/graphs/").glob("*.yaml"):
        graph = load_graph(graph_path)
        # 최소한의 patient context
        patient = {"age": 50, "sex": "M", "labs": {}, "comorbidities": [], "allergies": [], "medications": []}
        result = engine.derive(graph, patient)
        for constraint in result.forbidden + result.required + result.before + result.within:
            assert constraint.provenance, f"Missing provenance: {constraint}"
            assert constraint.severity, f"Missing severity: {constraint}"
```

---

## Phase 5: PatientGenerator 구현 (2일)

### 파일: `cpg_model/patient_generator.py`

```python
"""
Patient Generator

Conditional rule의 condition을 분석하여:
1. trigger patient: condition이 True가 되는 patient context (→ trap scenario)
2. normal patient: condition이 False인 patient context (→ baseline scenario)

한 graph에서 자동으로 여러 시나리오를 생성한다.
"""
import random
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass, field

@dataclass
class GeneratedScenario:
    """자동 생성된 시나리오"""
    scenario_id: str
    guideline_graph: str
    patient: dict
    derived_constraints: dict  # from ConstraintDerivationEngine
    trap_scenario: bool
    trap_description: str
    triggered_rules: List[str]  # rule_ids that fire
    generation_method: str  # "auto:condition_inversion" or "auto:combinatorial"

class PatientGenerator:
    """
    CPG graph의 conditional rules로부터 시나리오를 자동 생성.
    
    전략:
    1. Single-rule trigger: 각 conditional rule에 대해 trigger/normal patient 쌍 생성
    2. Combinatorial: 여러 rule이 동시에 trigger되는 complex patient 생성
    3. Allergy variants: 각 allergy에 대해 해당 allergy를 가진 patient 생성
    """
    
    def __init__(self, engine: 'ConstraintDerivationEngine'):
        self.engine = engine
        self.base_patient_templates = self._load_base_templates()
    
    def generate_from_graph(self, graph: dict) -> List[GeneratedScenario]:
        """
        한 graph에서 시나리오들을 자동 생성.
        
        Returns: list of GeneratedScenario
        """
        scenarios = []
        graph_id = graph["graph_id"]
        
        # 1. 각 conditional rule에 대해 trigger/normal 쌍
        all_rules = self._collect_all_rules(graph)
        
        for rule in all_rules:
            # Trigger patient
            trigger_patient = self._generate_trigger_patient(rule, graph)
            if trigger_patient:
                derived = self.engine.derive(graph, trigger_patient, f"{graph_id}_auto_trigger_{rule['rule_id']}")
                scenarios.append(GeneratedScenario(
                    scenario_id=f"{self._graph_to_prefix(graph_id)}_trap_{self._rule_to_suffix(rule['rule_id'])}",
                    guideline_graph=graph_id,
                    patient=trigger_patient,
                    derived_constraints=derived.to_yaml(),
                    trap_scenario=True,
                    trap_description=rule.get("description", ""),
                    triggered_rules=[rule["rule_id"]],
                    generation_method="auto:single_rule_trigger"
                ))
            
            # Normal patient (same context but condition NOT met)
            normal_patient = self._generate_normal_patient(rule, graph)
            if normal_patient:
                derived = self.engine.derive(graph, normal_patient, f"{graph_id}_auto_normal_{rule['rule_id']}")
                scenarios.append(GeneratedScenario(
                    scenario_id=f"{self._graph_to_prefix(graph_id)}_basic_{self._rule_to_suffix(rule['rule_id'])}",
                    guideline_graph=graph_id,
                    patient=normal_patient,
                    derived_constraints=derived.to_yaml(),
                    trap_scenario=False,
                    trap_description="",
                    triggered_rules=[],
                    generation_method="auto:single_rule_normal"
                ))
        
        # 2. Combinatorial (2-3 rules 동시 trigger)
        combos = self._generate_combinatorial_patients(all_rules, graph)
        scenarios.extend(combos)
        
        # 3. Deduplication: 동일한 derived constraint set이면 하나만 유지
        scenarios = self._deduplicate(scenarios)
        
        return scenarios
    
    def _generate_trigger_patient(self, rule: dict, graph: dict) -> Optional[dict]:
        """
        rule의 trigger_range를 사용하여 condition을 만족하는 patient 생성.
        
        예: trigger_range: {patient.labs.potassium: {min: 1.5, max: 3.2, type: float}}
        → patient = {..., labs: {potassium: 2.9}, ...}
        """
        base = self._get_base_patient(graph["graph_id"])
        trigger_range = rule.get("trigger_range", {})
        
        for var_path, range_spec in trigger_range.items():
            value = self._sample_value(range_spec)
            self._set_nested(base, var_path.replace("patient.", ""), value)
        
        return base
    
    def _generate_normal_patient(self, rule: dict, graph: dict) -> Optional[dict]:
        """
        rule의 normal_range를 사용하여 condition을 만족하지 않는 patient 생성.
        """
        base = self._get_base_patient(graph["graph_id"])
        normal_range = rule.get("normal_range", {})
        
        for var_path, range_spec in normal_range.items():
            value = self._sample_value(range_spec)
            self._set_nested(base, var_path.replace("patient.", ""), value)
        
        return base
    
    def _sample_value(self, range_spec: dict):
        """range_spec에서 값 샘플링"""
        rtype = range_spec.get("type", "float")
        if rtype == "float":
            return round(random.uniform(range_spec["min"], range_spec["max"]), 1)
        elif rtype == "int":
            return random.randint(range_spec["min"], range_spec["max"])
        elif rtype == "list_contains":
            return range_spec["contains"]  # 이 값을 list에 추가
        elif rtype == "list_not_contains":
            return None  # list에서 제거
    
    def _set_nested(self, d: dict, path: str, value):
        """
        "labs.potassium" → d["labs"]["potassium"] = value
        "comorbidities" + list_contains "cocaine_use" → d["comorbidities"].append("cocaine_use")
        """
        keys = path.split(".")
        for key in keys[:-1]:
            d = d.setdefault(key, {})
        
        if isinstance(value, str) and isinstance(d.get(keys[-1]), list):
            if value not in d[keys[-1]]:
                d[keys[-1]].append(value)
        elif value is None and isinstance(d.get(keys[-1]), list):
            pass  # list에서 제거할 필요 없으면 무시
        else:
            d[keys[-1]] = value
    
    def _get_base_patient(self, graph_id: str) -> dict:
        """graph domain에 맞는 base patient template 반환"""
        template = self.base_patient_templates.get(graph_id, self.base_patient_templates["default"])
        import copy
        return copy.deepcopy(template)
    
    def _load_base_templates(self) -> Dict[str, dict]:
        """
        각 domain에 맞는 기본 patient template.
        나이, 성별, 기본 vitals 등.
        """
        return {
            "ada_dka_management": {
                "age": 35, "sex": "M",
                "chief_complaint": "nausea, vomiting, abdominal pain",
                "labs": {"glucose": 450, "ph": 7.15, "potassium": 4.0, "bicarbonate": 10, "anion_gap": 24},
                "vitals": {"hr": 110, "sbp": 100, "dbp": 60, "rr": 28, "spo2": 97, "temp": 37.2, "map_mmhg": 73},
                "comorbidities": ["type_1_diabetes"],
                "allergies": [],
                "medications": [],
                "history": []
            },
            "aha_chest_pain": {
                "age": 62, "sex": "M",
                "chief_complaint": "chest pain",
                "labs": {"troponin": 0.5, "egfr": 85},
                "vitals": {"hr": 88, "sbp": 145, "dbp": 90, "rr": 20, "spo2": 96, "temp": 37.0, "map_mmhg": 108},
                "comorbidities": ["hypertension"],
                "allergies": [],
                "medications": [],
                "history": [],
                "ecg_findings": [],
                "presentation": {"symptom_onset_hours": 2}
            },
            # ... 20개 graph 각각에 대한 template
            "default": {
                "age": 55, "sex": "M",
                "chief_complaint": "",
                "labs": {},
                "vitals": {"hr": 80, "sbp": 130, "dbp": 80, "rr": 16, "spo2": 98, "temp": 37.0, "map_mmhg": 97},
                "comorbidities": [],
                "allergies": [],
                "medications": [],
                "history": []
            }
        }
    
    def _collect_all_rules(self, graph: dict) -> List[dict]:
        """graph의 모든 node에서 conditional_rules 수집"""
        rules = []
        for node_id, node in graph.get("nodes", {}).items():
            for rule in node.get("conditional_rules", []):
                rule["_node_id"] = node_id  # 추적용
                rules.append(rule)
        return rules
    
    def _generate_combinatorial_patients(self, rules: List[dict], graph: dict) -> List[GeneratedScenario]:
        """
        2-3개 rule이 동시에 trigger되는 complex patient 생성.
        
        예: DKA + hypokalemia + SGLT2 inhibitor + pregnancy
        → 4개 rule 동시 trigger → complex cross-domain trap
        """
        # condition_variables가 독립적인 rule들을 조합
        # 예: potassium < 3.3 (lab) + pregnancy (comorbidity) → 변수가 안 겹치면 조합 가능
        ...
    
    def _deduplicate(self, scenarios: List[GeneratedScenario]) -> List[GeneratedScenario]:
        """동일한 triggered_rules set이면 하나만 유지"""
        seen = set()
        unique = []
        for s in scenarios:
            key = frozenset(s.triggered_rules)
            if key not in seen:
                seen.add(key)
                unique.append(s)
        return unique
    
    def _graph_to_prefix(self, graph_id: str) -> str:
        """graph_id를 시나리오 prefix로 변환"""
        prefix_map = {
            "ada_dka_management": "dka",
            "aha_chest_pain": "acs",
            "aha_heart_failure": "hf",
            "aha_stroke": "stroke",
            "ssc_sepsis_hour1": "sepsis",
            "atrial_fibrillation": "af",
            "anaphylaxis_management": "anaph",
            "acls_cardiac_arrest": "acls",
            "status_epilepticus": "se",
            "gina_asthma_exacerbation": "asthma",
            "idsa_meningitis": "mening",
            "toxicology_management": "tox",
            # ...
        }
        return prefix_map.get(graph_id, graph_id[:6])
    
    def _rule_to_suffix(self, rule_id: str) -> str:
        """rule_id를 짧은 suffix로"""
        # "DKA-HYPOK-INSULIN-GATE" → "hypok_insulin"
        parts = rule_id.lower().split("-")[1:]
        return "_".join(parts[:2])
```

### 전체 생성 스크립트

```python
# scripts/generate_all_scenarios.py
"""
모든 graph에서 시나리오를 자동 생성하고, 기존 수동 시나리오와 병합.
"""

def main():
    engine = ConstraintDerivationEngine()
    generator = PatientGenerator(engine)
    
    all_generated = []
    
    for graph_path in sorted(Path("cpg_model/graphs/").glob("*.yaml")):
        graph = load_graph(graph_path)
        scenarios = generator.generate_from_graph(graph)
        all_generated.extend(scenarios)
        print(f"  {graph['graph_id']}: {len(scenarios)} scenarios generated")
    
    # 기존 수동 시나리오와 병합
    manual_scenarios = load_all_manual_scenarios()
    
    # 충돌 체크: 같은 triggered_rules를 가진 수동/자동 시나리오가 있으면 수동 우선
    manual_ids = {s.scenario_id for s in manual_scenarios}
    new_auto = [s for s in all_generated if s.scenario_id not in manual_ids]
    
    # 자동 생성 시나리오를 YAML로 저장
    for scenario in new_auto:
        save_scenario_yaml(scenario)
    
    # 기존 수동 시나리오의 forbidden을 derived로 교체 (cross-reference)
    for manual_s in manual_scenarios:
        graph = load_graph_for_scenario(manual_s)
        derived = engine.derive(graph, manual_s.patient.__dict__, manual_s.scenario_id)
        
        # 수동 forbidden ⊆ derived forbidden 인지 확인
        manual_forbidden = set(manual_s.forbidden_actions)
        derived_forbidden = set(a for c in derived.forbidden for a in c.actions)
        
        missing = manual_forbidden - derived_forbidden
        extra = derived_forbidden - manual_forbidden  # derived에는 있지만 수동에는 없던 것
        
        if missing:
            print(f"  WARNING: {manual_s.scenario_id} has manual forbidden not in derived: {missing}")
            print(f"    → Graph에 conditional rule 추가 필요")
        if extra:
            print(f"  INFO: {manual_s.scenario_id} derived has extra forbidden: {extra}")
            print(f"    → 수동 시나리오에 누락되었던 constraint 발견")
    
    # Summary
    total = len(manual_scenarios) + len(new_auto)
    trap_count = sum(1 for s in new_auto if s.trap_scenario) + sum(1 for s in manual_scenarios if s.trap_scenario)
    print(f"\n=== TOTAL: {total} scenarios ({trap_count} traps, {total-trap_count} baselines) ===")

if __name__ == "__main__":
    main()
```

---

## Phase 6: Rule Coverage Audit Matrix (2일)

### 파일: `evidence_pack/rule_coverage_audit.yaml`

각 CPG guideline의 "contraindication/do not/avoid" 조항을 열거하고,
graph의 conditional rule과 1:1 매핑.

```yaml
# 예: ADA 2024 DKA Guidelines
ada_2024_dka:
  source: "ADA Standards of Care 2024, Section 16.2 - DKA Management"
  
  contraindications:
    - guideline_clause: "Do not administer insulin if serum potassium < 3.3 mEq/L"
      section: "16.2.3"
      mapped_rule: "DKA-HYPOK-INSULIN-GATE"
      status: COVERED
      
    - guideline_clause: "Do not give potassium replacement if K+ > 5.5 mEq/L"
      section: "16.2.4"
      mapped_rule: "DKA-HYPERK-NO-K-REPLACE"
      status: COVERED
      
    - guideline_clause: "Avoid bicarbonate unless pH < 6.9 in adults"
      section: "16.2.6"
      mapped_rule: "DKA-BICARB-PH-GATE"
      status: COVERED
      
    - guideline_clause: "In pediatric DKA, avoid rapid fluid correction"
      section: "16.2.7"
      mapped_rule: "DKA-PEDIATRIC-NO-RAPID-FLUID"
      status: COVERED
      
    - guideline_clause: "Discontinue SGLT2 inhibitors immediately"
      section: "16.2.8"  
      mapped_rule: "DKA-EUGLY-SGLT2-DEXTROSE"
      status: COVERED
      
    - guideline_clause: "Do not discharge based on glucose alone if SGLT2 use"
      section: "16.2.8"
      mapped_rule: "DKA-EUGLY-NO-DISCHARGE-NORMAL-GLU"
      status: COVERED
  
  total_clauses: 12
  covered: 12
  not_covered: 0
  coverage_percent: 100
```

### 생성 스크립트

```python
# scripts/generate_audit_matrix.py
"""
각 graph의 conditional rules와 guideline 원문 조항을 대조하여
Rule Coverage Audit Matrix를 생성.
"""

def generate_audit():
    audit = {}
    
    for graph_path in Path("cpg_model/graphs/").glob("*.yaml"):
        graph = load_graph(graph_path)
        rules = collect_all_rules(graph)
        
        # rule_id → evidence 매핑
        rule_evidence = {r["rule_id"]: r.get("evidence", "") for r in rules}
        
        audit[graph["graph_id"]] = {
            "total_unconditional_forbidden": count_unconditional_forbidden(graph),
            "total_conditional_rules": len(rules),
            "rules": [
                {
                    "rule_id": r["rule_id"],
                    "condition": r["condition"],
                    "effect_type": r["effect"]["type"],
                    "actions": r["effect"]["actions"],
                    "evidence": r.get("evidence", ""),
                    "severity": r.get("severity", ""),
                    "has_trigger_range": bool(r.get("trigger_range")),
                    "has_normal_range": bool(r.get("normal_range")),
                }
                for r in rules
            ]
        }
    
    # YAML + markdown 출력
    save_yaml(audit, "evidence_pack/rule_coverage_audit.yaml")
    save_markdown_table(audit, "evidence_pack/rule_coverage_audit.md")
    
    # 통계
    total_rules = sum(a["total_conditional_rules"] for a in audit.values())
    total_uncond = sum(a["total_unconditional_forbidden"] for a in audit.values())
    print(f"Total graphs: {len(audit)}")
    print(f"Total unconditional forbidden: {total_uncond}")
    print(f"Total conditional rules: {total_rules}")
    print(f"Total constraints: {total_uncond + total_rules}")
```

---

## Phase 7: 전체 Validation (1일)

```bash
# 1. Schema validation
python scripts/validate_conditional_rules.py

# 2. Derivation Engine unit tests
python -m pytest tests/test_constraint_derivation.py -v

# 3. Patient Generator test
python -m pytest tests/test_patient_generator.py -v

# 4. Generate all scenarios
python scripts/generate_all_scenarios.py

# 5. Scenario count + distribution
python -c "
from cpg_model.scenario_loader import ScenarioLoader
loader = ScenarioLoader()
scenarios = loader.load_all_scenarios()
from collections import Counter
gc = Counter(s.guideline_graph for s in scenarios)
tc = sum(1 for s in scenarios if s.trap_scenario)
print(f'Total: {len(scenarios)} scenarios, {tc} traps ({tc/len(scenarios)*100:.0f}%)')
print(f'Graphs: {len(gc)}')
for g, c in gc.most_common():
    print(f'  {g}: {c}')
assert len(scenarios) >= 130, f'Expected >=130, got {len(scenarios)}'
"

# 6. Cross-reference: 모든 수동 forbidden이 derived에 포함되는지
python scripts/cross_reference_manual_vs_derived.py

# 7. Rule Coverage Audit
python scripts/generate_audit_matrix.py

# 8. Regression tests
python -m pytest tests/ -x -q 2>&1 | tail -20

# 9. Provenance completeness check
python -c "
from cpg_model.constraint_derivation import ConstraintDerivationEngine
from cpg_model.scenario_loader import ScenarioLoader
engine = ConstraintDerivationEngine()
loader = ScenarioLoader()
for s in loader.load_all_scenarios():
    graph = load_graph_for_scenario(s)
    derived = engine.derive(graph, s.patient.__dict__, s.scenario_id)
    for c in derived.forbidden + derived.required + derived.before + derived.within:
        assert c.provenance, f'{s.scenario_id}: constraint without provenance'
        assert c.evidence or not c.is_conditional, f'{s.scenario_id}: conditional without evidence'
print('All constraints have provenance')
"
```

## Completion Criteria

- [ ] ConditionalRule 스키마 정의 + 파서 확장
- [ ] 14개 기존 graph에 conditional rules 추가 (graph당 5-15개, 총 ~112)
- [ ] 6개 신규 graph 완성 (각 4+ nodes, 8+ conditional rules)
- [ ] ConstraintDerivationEngine 구현 + 테스트 통과
- [ ] PatientGenerator 구현 + 테스트 통과
- [ ] 전체 시나리오 자동 생성: ≥130개
- [ ] 모든 시나리오의 constraint에 provenance chain 존재
- [ ] 수동 시나리오의 forbidden ⊆ derived forbidden (cross-reference 통과)
- [ ] Rule Coverage Audit Matrix 생성 (evidence_pack/)
- [ ] Allergy drug map 완성 (cpg_model/allergy_drug_map.yaml)
- [ ] Regression test: 기존 pass 유지
- [ ] Summary 출력: 총 시나리오 수, trap 비율, graph 수, domain 분포