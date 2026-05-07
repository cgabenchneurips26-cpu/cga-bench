# MIMIC-IV Sepsis-3 Cohort Statistics (from partial download)

**Computed**: 2026-04-29T15:14:21.645603+00:00
**Source**: `physionet.org/files/mimiciv/3.1` (hosp/ only; icu/ not yet available)

## 1. Cohort identification (Sepsis-3)

- **21,646** sepsis admissions
- **17,441** unique sepsis patients
- **32,569** sepsis diagnosis rows

**Top-20 sepsis ICD codes:**

| ICD code | Count |
|---|---|
| A419 | 7,770 |
| R6521 | 5,599 |
| 99592 | 5,257 |
| 78552 | 3,370 |
| 99591 | 2,953 |
| R6520 | 1,948 |
| A4151 | 1,413 |
| A4189 | 1,338 |
| A4101 | 641 |
| A4159 | 558 |
| A4181 | 539 |
| A4102 | 334 |
| A4152 | 249 |
| A411 | 224 |
| A4150 | 178 |
| A414 | 99 |
| A4153 | 65 |
| A413 | 20 |
| A412 | 14 |

## 2. Comorbidity distribution

Among 12,438 sepsis admissions with at least one ICD-10 code:

| Tag | % of admissions |
|---|---|
| type_2_diabetes | 35.3 % |
| essential_hypertension | 32.9 % |
| heart_failure | 31.4 % |
| ckd | 30.8 % |
| mood_disorder | 25.1 % |
| neoplasm_any | 23.9 % |
| substance_use | 19.1 % |
| copd | 14.7 % |
| dialysis_dependence | 12.7 % |
| acute_mi | 10.7 % |
| asthma | 8.4 % |
| alcoholic_liver_disease | 5.7 % |
| fibrosis_cirrhosis | 4.8 % |
| ischemic_stroke | 3.6 % |
| type_1_diabetes | 2.2 % |

## 3. Length of stay (cohort admissions)

- n: 21,646
- mean: 13.56 days
- median: 8.33 days
- IQR: 4.65–16.42 days
- max: 515.56 days

## 4. Admission type

| Type | Count |
|---|---|
| EW EMER. | 11,948 |
| OBSERVATION ADMIT | 5,253 |
| URGENT | 3,400 |
| DIRECT EMER. | 597 |
| SURGICAL SAME DAY ADMISSION | 245 |
| ELECTIVE | 116 |
| EU OBSERVATION | 74 |
| DIRECT OBSERVATION | 11 |
| AMBULATORY OBSERVATION | 2 |

## 5. Discharge location

| Location | Count |
|---|---|
| HOME HEALTH CARE | 4,927 |
| SKILLED NURSING FACILITY | 4,549 |
| DIED | 4,349 |
| HOME | 3,617 |
| CHRONIC/LONG TERM ACUTE CARE | 1,666 |
| REHAB | 1,008 |
| HOSPICE | 896 |
| ACUTE HOSPITAL | 241 |
| AGAINST ADVICE | 135 |
| nan | 95 |

## 6. DRG distribution

- Sepsis-specific DRGs (870/871/872): **11,075**

**Top-15 DRGs in cohort:**

| DRG | Count |
|---|---|
| 720 | 11,046 |
| 871 | 8,130 |
| 710 | 2,660 |
| 853 | 2,200 |
| 872 | 1,883 |
| 870 | 1,062 |
| 721 | 698 |
| 004 | 663 |
| 466 | 573 |
| 314 | 563 |
| 698 | 481 |
| 003 | 441 |
| 862 | 342 |
| 005 | 330 |
| 854 | 326 |

## 7. Lab distributions in cohort

| Lab | n | mean | median | IQR | max |
|---|---|---|---|---|---|
| lactate | 2,256 | 2.383 | 1.8 | 1.2–2.7 | 22.0 |
| wbc | 5,593 | 12.892 | 10.8 | 7.0–15.4 | 132.3 |
| creatinine | 6,240 | 1.654 | 1.2 | 0.8–2.0 | 13.2 |
| procalcitonin | 170 | 116.246 | 104.9 | 59.675–172.125 | 289.6 |
| glucose | 6,216 | 139.167 | 125.0 | 101.0–161.0 | 1252.0 |

## 8. Files used

- `hosp/admissions.csv.gz`
- `hosp/d_hcpcs.csv.gz`
- `hosp/d_icd_diagnoses.csv.gz`
- `hosp/d_icd_procedures.csv.gz`
- `hosp/d_labitems.csv.gz`
- `hosp/diagnoses_icd.csv.gz`
- `hosp/drgcodes.csv.gz`
- `hosp/emar.csv.gz`
- `hosp/emar_detail.csv.gz`
- `hosp/hcpcsevents.csv.gz`
- `hosp/labevents.csv.gz`
- `hosp/microbiologyevents.csv.gz`
- `hosp/omr.csv.gz`
- `hosp/patients.csv.gz`
- `hosp/pharmacy.csv.gz`
- `hosp/poe.csv.gz`
- `hosp/poe_detail.csv.gz`
- `hosp/prescriptions.csv.gz`
- `hosp/procedures_icd.csv.gz`
- `hosp/provider.csv.gz`
- `hosp/services.csv.gz`
- `hosp/transfers.csv.gz`

## Caveats

- ICU module not yet downloaded — vitals, ICU LOS, vasopressor /
  fluid administration timeline missing from this report.
- ICD-10/ICD-9 mapping is conservative (prefix-only match).
- Comorbidity tags use 3-char rollup; finer granularity available
  on full v3.1.
- patients.csv.gz not yet downloaded → no age/sex demographics in
  this report. Add when patients.csv.gz arrives.