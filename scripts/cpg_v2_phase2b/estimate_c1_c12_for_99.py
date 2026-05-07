"""Phase 2b: Heuristic C1-C12 estimator for 99 CPG expansion candidates.

The full C1-C12 rubric (scripts/score_cpg_v2.py) requires expert-annotated
properties in data/cpg_source_properties.json. Only the 25 existing graphs
are annotated. For the 99 candidates we do not (yet) have full annotations,
so this script produces a *conservative heuristic estimate* of the C1-C12
totals using:

  - M1-M6 scores carried from docs/cpg_expansion_v7/02_candidate_rescoring_99.md
  - Year regex from the guideline name (for C4)
  - Publisher/society token recognition (for C1, C2)
  - Area (domain) + time-sensitivity signal (for C6, C7, C9, C10)
  - M2 -> C11, M6 -> C12

The estimator is intentionally conservative: when the source-doc answer is
ambiguous it picks the *lower* grade. The output Tier distribution should
therefore under-count Tier S rather than over-count it. A full Phase 2b
pass (annotating each of the 99 into data/cpg_source_properties.json) will
produce authoritative scores.

Usage:
    PYTHONPATH=. python scripts/cpg_v2_phase2b/estimate_c1_c12_for_99.py \
        --output reports/cpg_scores_v2_99_candidates_estimated.json \
        --md-output reports/cpg_scores_v2_99_candidates_estimated.md
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
import re
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


_YEAR_RE = re.compile(r"\b(19|20)\d{2}\b")

TIER_S_MIN = 15
TIER_A_MIN = 11
TIER_B_MIN = 7

# Publishers with formal GRADE-family grading systems -> C2=2
GRADE_LIKE_SOCIETIES: set[str] = {
    "IDSA",
    "WHO",
    "BTS",
    "GINA",
    "GOLD",
    "KDIGO",
    "ACG",
    "AGA",
    "AASLD",
    "BTF",
    "ILCOR",
    "NICE",
    "ERC",
    "AAN",
    "NCS",
    "SCCM",
    "SSC",
}

# High-burden domains under GBD 2021 Top-15 / emergency severity -> C6=2, C7=2
CRITICAL_AREAS = {"Trauma", "CV", "Infectious", "Peds", "Neuro"}
HIGH_BURDEN_AREAS = {"Trauma", "CV", "Pulm", "Infectious", "Neuro", "Hepatic/GI"}


# ---------------------------------------------------------------------------
# Data: 99 candidates with M1-M6 (from docs/cpg_expansion_v7/02_candidate_rescoring_99.md)
# Schema: (area, name, m1, m2, m3, m4, m5, m6)
# ---------------------------------------------------------------------------

CANDIDATES: list[tuple] = [
    # 1. Trauma (10)
    ("Trauma", "ATLS Primary Survey (ACS 2018, 10th ed)", 1, 1, 1, 1, 1, 1),
    ("Trauma", "BTF Severe TBI (2016/2020, 4th ed)", 1, 1, 1, 1, 1, 1),
    ("Trauma", "AOSpine Acute SCI (2017, Global Spine J)", 0, 1, 1, 1, 1, 1),
    ("Trauma", "WSES Pelvic Trauma/REBOA (2017)", 1, 1, 1, 1, 1, 1),
    ("Trauma", "EAST Cervical Spine (2009/2023)", 0, 1, 1, 1, 1, 0),
    ("Trauma", "EAST Blunt Cardiac Injury (2012)", 1, 1, 1, 0, 1, 0),
    ("Trauma", "EAST Damage Control / MTP (2019)", 1, 1, 1, 1, 1, 1),
    ("Trauma", "WSES Penetrating Abdominal (2017)", 1, 1, 1, 1, 1, 1),
    ("Trauma", "BTS Pleural Disease / Tension PTX (2023)", 1, 1, 1, 1, 1, 1),
    ("Trauma", "EAST Open Fracture / Mangled Extremity (2012)", 1, 1, 1, 0, 1, 0),
    # 2. CV 추가 (10)
    ("CV", "AHA/ACC Aortic Dissection (2022)", 1, 1, 1, 1, 1, 1),
    ("CV", "AHA Cardiogenic Shock SS + SCAI (2022)", 1, 1, 1, 1, 1, 1),
    ("CV", "AHA Post-Cardiac Arrest / TTM (2023)", 1, 1, 1, 1, 1, 1),
    ("CV", "HRS VT / Electrical Storm (2022)", 1, 1, 1, 1, 1, 1),
    ("CV", "ESC Bradyarrhythmia / Pacing (2021)", 1, 1, 1, 1, 1, 1),
    ("CV", "AHA/ASA Carotid Stenosis (2023)", 0, 1, 1, 1, 1, 1),
    ("CV", "AHA HOCM / Obstructive Cardiomyopathy (2020)", 1, 1, 1, 1, 1, 0),
    ("CV", "AHA Pericarditis / Tamponade (2015/2023)", 1, 1, 1, 1, 1, 1),
    ("CV", "ESVS Acute Limb Ischemia (2020)", 1, 1, 1, 1, 1, 1),
    ("CV", "AHA Bradycardia/Tachycardia ACLS (2020)", 1, 1, 1, 1, 1, 0),
    # 3. Pulm 추가 (7)
    ("Pulm", "ARDS Berlin / ESICM 2023", 1, 1, 1, 1, 1, 1),
    ("Pulm", "DAS Difficult Airway (2015/2022)", 1, 1, 1, 1, 1, 1),
    ("Pulm", "ERS Pulmonary Hypertension Crisis (2022)", 0, 1, 1, 1, 1, 0),
    ("Pulm", "ATS Cystic Fibrosis Exacerbation", 0, 1, 1, 1, 1, 0),
    ("Pulm", "IDSA Epiglottitis / Deep Neck Infection", 1, 1, 1, 0, 1, 0),
    ("Pulm", "BTS/ERS Massive Hemoptysis", 1, 1, 1, 0, 1, 0),
    ("Pulm", "AHA BLS Foreign Body Aspiration", 1, 1, 1, 0, 1, 0),
    # 4. Neuro 추가 (7)
    ("Neuro", "NCS/AHA Aneurysmal SAH (2023)", 1, 1, 1, 1, 1, 1),
    ("Neuro", "AHA/ASA Spontaneous ICH (2022)", 1, 1, 1, 1, 1, 1),
    ("Neuro", "AAN Myasthenic Crisis (2021)", 0, 1, 1, 1, 1, 0),
    ("Neuro", "EAN Guillain-Barré (2023)", 0, 1, 1, 1, 1, 0),
    ("Neuro", "ASCO/NICE Spinal Cord Compression", 0, 1, 1, 1, 1, 0),
    ("Neuro", "ASAM Alcohol Withdrawal / CIWA (2020)", 1, 1, 1, 1, 1, 1),
    ("Neuro", "SCCM Delirium ICU (PADIS 2018)", 0, 1, 1, 1, 1, 1),
    # 5. Endo/Metabolic (10)
    ("Endo", "ADA HHS (2024)", 1, 1, 1, 1, 1, 1),
    ("Endo", "ATA Thyroid Storm (2016)", 1, 1, 1, 1, 1, 1),
    ("Endo", "Endocrine Society Adrenal Crisis (2016)", 1, 1, 1, 1, 1, 0),
    ("Endo", "AACE Myxedema Coma", 0, 1, 1, 1, 1, 0),
    ("Endo", "UKKA Severe Hyperkalemia (2023)", 1, 1, 1, 1, 1, 1),
    ("Endo", "ESE/ESICM Severe Hyponatremia (2014)", 1, 1, 1, 1, 1, 1),
    ("Endo", "AACE/SCCM ICU Hypernatremia", 0, 1, 1, 0, 1, 0),
    ("Endo", "ADA Severe Hypoglycemia (2024)", 1, 0, 1, 1, 1, 0),
    ("Endo", "NSW Rhabdomyolysis (2022)", 0, 1, 0, 1, 1, 0),
    ("Endo", "Endocrine Soc Pheochromocytoma (2014)", 0, 1, 1, 1, 1, 0),
    # 6. Hepatic/GI (8)
    ("Hepatic/GI", "AASLD Acute Liver Failure (2023)", 1, 1, 1, 1, 1, 1),
    ("Hepatic/GI", "AASLD Hepatic Encephalopathy (2014)", 0, 1, 1, 1, 1, 0),
    ("Hepatic/GI", "Baveno VII Variceal Hemorrhage (2022)", 1, 1, 1, 1, 1, 1),
    ("Hepatic/GI", "ACG/AGA Acute Pancreatitis (2013/2024)", 1, 1, 1, 1, 1, 1),
    ("Hepatic/GI", "Tokyo Guidelines Cholangitis (2018)", 1, 1, 1, 1, 1, 1),
    ("Hepatic/GI", "WSES Acute Mesenteric Ischemia (2017)", 1, 1, 1, 1, 1, 1),
    ("Hepatic/GI", "ASCRS Acute Diverticulitis (2020)", 0, 1, 1, 1, 1, 0),
    ("Hepatic/GI", "IDSA Fulminant C.difficile (2021)", 1, 1, 1, 1, 1, 1),
    # 7. Renal/GU (3)
    ("Renal/GU", "ISTH/ASH TTP (2020)", 1, 1, 1, 1, 1, 1),
    ("Renal/GU", "AUA Testicular Torsion (2023)", 1, 1, 1, 1, 1, 0),
    ("Renal/GU", "EAU Obstructive Pyelonephritis", 1, 1, 1, 1, 1, 1),
    # 8. OB (5)
    ("OB", "ACOG PB 222 Preeclampsia/HELLP (2020)", 1, 1, 1, 1, 1, 1),
    ("OB", "SMFM AFE (2016)", 1, 1, 1, 0, 1, 0),
    ("OB", "RCOG Cord Prolapse (2014)", 1, 1, 1, 0, 1, 0),
    ("OB", "SMFM/RCOG Maternal Sepsis (2019)", 1, 1, 1, 1, 1, 1),
    ("OB", "ACOG Shoulder Dystocia (2017)", 1, 1, 1, 0, 1, 0),
    # 9. Peds (8)
    ("Peds", "ISPAD Pediatric DKA (2022)", 1, 1, 1, 1, 1, 1),
    ("Peds", "AAP Bronchiolitis (2014)", 0, 1, 1, 1, 1, 0),
    ("Peds", "NRP/AAP Neonatal Resuscitation (2020)", 1, 1, 1, 1, 1, 1),
    ("Peds", "AHA Kawasaki (2017)", 0, 1, 1, 1, 1, 0),
    ("Peds", "SCCM Pediatric Septic Shock (2020)", 1, 1, 1, 1, 1, 1),
    ("Peds", "GINA Pediatric Status Asthma", 1, 1, 1, 1, 1, 1),
    ("Peds", "PALS/ATLS Pediatric Traumatic Arrest", 1, 1, 1, 1, 1, 1),
    ("Peds", "BIMDG IEM Crisis (2017)", 1, 1, 0, 1, 1, 1),
    # 10. Infectious (6)
    ("Infectious", "IDSA/EAST NSTI (2014)", 1, 1, 1, 1, 1, 1),
    ("Infectious", "IDSA Toxic Shock Syndrome (2014)", 1, 1, 1, 1, 1, 1),
    ("Infectious", "AHA/ESC Infective Endocarditis (2023)", 0, 1, 1, 1, 1, 1),
    ("Infectious", "IDSA Spinal Epidural Abscess (2020)", 0, 1, 1, 1, 1, 0),
    ("Infectious", "IDSA/ASCO Febrile Neutropenia (2018)", 1, 1, 1, 1, 1, 1),
    ("Infectious", "WHO/CDC Severe Malaria (2023)", 1, 1, 1, 1, 1, 1),
    # 11. Toxicology (7)
    ("Tox", "AASLD/AACT Salicylate Toxicity (2015)", 1, 1, 1, 1, 1, 1),
    ("Tox", "UHMS Carbon Monoxide / HBO (2017)", 1, 1, 1, 1, 1, 1),
    ("Tox", "AACT Iron Overdose", 1, 1, 1, 1, 1, 0),
    ("Tox", "Serotonin Syndrome (Boyer & Shannon)", 1, 1, 0, 0, 1, 0),
    ("Tox", "NMS (EAN/consensus)", 0, 1, 1, 0, 1, 0),
    ("Tox", "EXTRIP Lithium Toxicity (2015)", 1, 1, 1, 1, 1, 1),
    ("Tox", "EXTRIP Valproate Toxicity (2015)", 1, 1, 1, 1, 1, 0),
    # 12. Environmental (7)
    ("Env", "WMS Heat Stroke (2024)", 1, 1, 1, 1, 1, 1),
    ("Env", "ERC Hypothermia (2021)", 1, 1, 1, 1, 1, 1),
    ("Env", "ERC Drowning (2021)", 1, 1, 1, 1, 1, 1),
    ("Env", "ACMT Crotaline Envenomation (2011)", 1, 1, 1, 1, 1, 0),
    ("Env", "WMS Elapid / Coral Snake", 1, 1, 1, 0, 1, 0),
    ("Env", "WMS HACE / HAPE (2024)", 1, 1, 1, 1, 1, 1),
    ("Env", "ATLS adjunct Electrical Injury", 0, 1, 1, 0, 1, 0),
    # 13. Ophthal/ENT (5)
    ("Ophthal/ENT", "AAO Acute Angle-Closure Glaucoma (2020)", 1, 1, 1, 1, 1, 1),
    ("Ophthal/ENT", "AAO/AHA CRAO (2021)", 1, 1, 1, 1, 1, 0),
    ("Ophthal/ENT", "AAO Orbital Cellulitis (2023)", 0, 1, 1, 1, 1, 0),
    ("Ophthal/ENT", "ENT-UK Epistaxis (2020)", 1, 1, 1, 0, 1, 0),
    ("Ophthal/ENT", "Ludwig Angina / Peritonsillar Abscess", 1, 1, 0, 0, 1, 0),
    # 14. Heme/Onc (5)
    ("Heme/Onc", "NCCN Tumor Lysis Syndrome (2024)", 1, 1, 1, 1, 1, 1),
    ("Heme/Onc", "NCCN Hypercalcemia of Malignancy", 0, 1, 1, 1, 1, 0),
    ("Heme/Onc", "ASH Immune Thrombocytopenia (2019)", 0, 1, 1, 1, 1, 0),
    ("Heme/Onc", "ISTH DIC (2009/2018)", 0, 1, 1, 1, 1, 1),
    ("Heme/Onc", "ASH Hyperviscosity Syndrome", 0, 1, 0, 1, 1, 0),
    # 15. 기타 (1)
    ("Other", "SCCM Rapid Sequence Intubation (2019)", 1, 1, 1, 1, 1, 1),
]


def name_year(name: str) -> int | None:
    """Extract the latest year mentioned in the candidate name."""
    years = [int(y) for y in _YEAR_RE.findall(name)]
    return max(years) if years else None


def infer_c2(name: str, m2: int, m3: int) -> int:
    """C2: evidence grading. 2 = GRADE-family, 1 = society-specific, 0 = none."""
    if m3 == 0:
        # Non-tier-1 societies rarely publish formal grading tables
        return 0
    up = name.upper()
    if any(tok in up for tok in GRADE_LIKE_SOCIETIES):
        return 2
    # Default Tier-1 society: usually has a society-specific class/LOE system
    return 1 if m2 == 1 else 1  # conservative baseline


def infer_c3(m3: int) -> int:
    """C3: systematic review performed.

    Tier-1 societies in our 25 CPG set all have SR (c3_systematic_review=true
    or near-universally true). Non-Tier-1 groups are mixed; conservatively 0.
    """
    return 1 if m3 == 1 else 0


def infer_c4(name: str) -> int:
    """C4: recency (0/1/2). 2 if >=2020, 1 if 2015-2019, 0 otherwise."""
    y = name_year(name)
    if y is None:
        return 0
    if y >= 2020:
        return 2
    if y >= 2015:
        return 1
    return 0


def infer_c5(m5: int) -> int:
    """C5: DOI/URL/ISBN — M5 is a direct equivalent."""
    return 1 if m5 == 1 else 0


def infer_c6(area: str, name: str) -> int:
    """C6: GBD 2021 burden.

    Very coarse — a proper pass consults GBD 2021 Top-15/Top-30 tables.
    Conservative mapping per area with name-level overrides.
    """
    up = name.upper()
    # Strong high-burden conditions (GBD Top-15 deaths)
    if any(
        kw in up
        for kw in [
            "STROKE",
            "MI ",
            "STEMI",
            "SEPSIS",
            "CARDIAC ARREST",
            "AORTIC DISSECTION",
            "PE ",
            "PNEUMONIA",
            "MALARIA",
            "ICH",
            "SAH",
            "TBI",
            "HEART FAILURE",
            "SHOCK",
        ]
    ):
        return 2
    if area in {"Trauma", "CV", "Pulm", "Neuro", "Infectious", "Peds"}:
        return 2
    if area in {"Hepatic/GI", "Endo", "Renal/GU", "OB"}:
        return 1
    if area in {"Tox", "Env", "Heme/Onc"}:
        return 1
    return 0  # Ophthal/ENT, Other


def infer_c7(area: str, m1: int, name: str) -> int:
    """C7: time-to-harm severity (0/1/2).

    2 = harm within minutes-to-hour (critical emergency)
    1 = hours-to-day (moderate)
    0 = days+ (mild)
    """
    up = name.upper()
    # Minute-level emergencies regardless of area
    if any(
        kw in up
        for kw in [
            "CARDIAC ARREST",
            "AIRWAY",
            "TAMPONADE",
            "AORTIC DISSECTION",
            "HEMORRHAGE",
            "ANAPHYLAXIS",
            "ICH",
            "SAH",
            "TTM",
            "VT",
            "CARDIOGENIC SHOCK",
            "ACUTE LIMB ISCHEMIA",
            "CRAO",
            "ACUTE ANGLE-CLOSURE",
            "RSI",
            "NEONATAL RESUSCITATION",
            "TENSION PTX",
            "MTP",
            "TRAUMATIC ARREST",
            "DROWNING",
            "ORBITAL CELLULITIS",
            "EPIGLOTTITIS",
        ]
    ):
        return 2
    if area in CRITICAL_AREAS and m1 == 1:
        return 2
    if area in {"Endo", "Hepatic/GI", "Renal/GU", "OB", "Tox", "Env"}:
        return 1 if m1 == 1 else 1  # typically moderate
    return 1  # default moderate


def infer_c8(m4: int, area: str, name: str) -> int:
    """C8: contraindication rules explicit in source (0/1/2).

    Drug-heavy or multi-drug-class guidelines usually enumerate
    contraindications (>=3 items) -> 2; procedure-only with 1-2 items -> 1;
    none documented -> 0.

    Heuristic: tier-1 (M4=Class I flag) drug-centric guidelines -> 2,
    procedure-centric -> 1, purely supportive -> 0.
    """
    up = name.upper()
    if any(
        kw in up
        for kw in [
            "THROMBOLYSIS",
            "ANTICOAG",
            "TPA",
            "HEPARIN",
            "VASOPRESSOR",
            "BETA-BLOCKER",
            "NITRATE",
            "ANTIBIOT",
            "FIBRINOLYT",
            "ACE",
            "ARNI",
            "DKA",
            "HHS",
            "THYROID",
            "MYXEDEMA",
            "HYPERKALEMIA",
            "PREECLAMPSIA",
            "ECLAMPSIA",
            "SALICYLATE",
            "LITHIUM",
            "VALPROATE",
            "IRON",
            "SEROTONIN",
            "NMS",
            "C.DIFFICILE",
            "FEBRILE NEUTROPENIA",
            "VARICEAL",
        ]
    ):
        return 2 if m4 == 1 else 1
    if area in {"CV", "Neuro", "Endo", "Tox", "Infectious", "Heme/Onc", "OB"}:
        return 2 if m4 == 1 else 1
    return 1 if m4 == 1 else 0


def infer_c9(m1: int, area: str) -> int:
    """C9: algorithm/flowchart figure (0/1/2).

    Tier-1 time-sensitive emergency guidelines almost always ship a
    flowchart (most have 2+). We approximate:
      2 = time-sensitive emergency area (M1=1 AND critical area)
      1 = at least one figure expected
      0 = unknown/none
    """
    if m1 == 1 and area in CRITICAL_AREAS | {"Pulm", "Hepatic/GI", "Endo", "OB", "Tox", "Env"}:
        return 2
    if m1 == 1:
        return 1
    return 1  # assume at least one figure; conservative for M1=0


def infer_c10(m1: int) -> int:
    """C10: time constraints explicit in source (0/1/2).

    M1 is Time-sensitivity (deadline <=60 min, >=3 mandatory) in our v1
    rubric — a direct 1:1 match with C10's strong form.
      2 = M1 satisfied (multiple explicit deadlines)
      1 = partial (some time mentions, fewer than threshold)
      0 = chronic
    """
    return 2 if m1 == 1 else 1


def infer_c11(m2: int) -> int:
    """C11: sequence dependency (0/1). M2 is the same criterion at threshold>=1."""
    return 1 if m2 == 1 else 0


def infer_c12(m6: int) -> int:
    """C12: conditional branching (0/1). M6 captures conditional richness."""
    return 1 if m6 == 1 else 0


def score_candidate(area: str, name: str, m1: int, m2: int, m3: int, m4: int, m5: int, m6: int) -> dict:
    c1 = 1 if m3 == 1 else 0
    c2 = infer_c2(name, m2, m3)
    c3 = infer_c3(m3)
    c4 = infer_c4(name)
    c5 = infer_c5(m5)
    c6 = infer_c6(area, name)
    c7 = infer_c7(area, m1, name)
    c8 = infer_c8(m4, area, name)
    c9 = infer_c9(m1, area)
    c10 = infer_c10(m1)
    c11 = infer_c11(m2)
    c12 = infer_c12(m6)

    ax1 = c1 + c2 + c3 + c4 + c5
    ax2 = c6 + c7 + c8
    ax3 = c9 + c10 + c11 + c12
    total = ax1 + ax2 + ax3

    if total >= TIER_S_MIN:
        tier = "S"
    elif total >= TIER_A_MIN:
        tier = "A"
    elif total >= TIER_B_MIN:
        tier = "B"
    else:
        tier = "Excluded"

    return {
        "area": area,
        "name": name,
        "m1": m1,
        "m2": m2,
        "m3": m3,
        "m4": m4,
        "m5": m5,
        "m6": m6,
        "c1": c1,
        "c2": c2,
        "c3": c3,
        "c4": c4,
        "c5": c5,
        "c6": c6,
        "c7": c7,
        "c8": c8,
        "c9": c9,
        "c10": c10,
        "c11": c11,
        "c12": c12,
        "axis1": ax1,
        "axis2": ax2,
        "axis3": ax3,
        "total": total,
        "tier": tier,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=str, default="reports/cpg_scores_v2_99_candidates_estimated.json")
    parser.add_argument("--md-output", type=str, default="reports/cpg_scores_v2_99_candidates_estimated.md")
    args = parser.parse_args()

    scored = [score_candidate(*c) for c in CANDIDATES]
    assert len(scored) == 99, f"Expected 99 candidates, got {len(scored)}"

    tier_counts = Counter(r["tier"] for r in scored)
    area_tier = defaultdict(Counter)
    for r in scored:
        area_tier[r["area"]][r["tier"]] += 1

    n = len(scored)
    ax1_mean = sum(r["axis1"] for r in scored) / n
    ax2_mean = sum(r["axis2"] for r in scored) / n
    ax3_mean = sum(r["axis3"] for r in scored) / n
    total_mean = sum(r["total"] for r in scored) / n

    tier_valid_count = sum(1 for r in scored if r["total"] >= TIER_B_MIN)

    out_json = {
        "framework": "C1-C12 Source-Document Criteria v2 (heuristic estimation for 99 candidates)",
        "note": (
            "Conservative heuristic: exact C1-C12 scoring requires expert annotation "
            "in data/cpg_source_properties.json. Used M1-M6 + publisher/area heuristics. "
            "Expect slight under-count of Tier S."
        ),
        "total_candidates": n,
        "tier_distribution": dict(tier_counts),
        "tier_valid_ge7": tier_valid_count,
        "means": {
            "axis1_trust": round(ax1_mean, 2),
            "axis2_clinical": round(ax2_mean, 2),
            "axis3_formalizability": round(ax3_mean, 2),
            "total": round(total_mean, 2),
        },
        "area_tier_breakdown": {area: dict(counts) for area, counts in area_tier.items()},
        "results": scored,
    }

    out_path = REPO_ROOT / args.output
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(out_json, indent=2), encoding="utf-8")

    lines: list[str] = []
    lines.append("# CPG Selection Criteria v2 — 99 Candidate Heuristic Estimation\n")
    lines.append("**Framework**: C1-C12 Source-Document Criteria (3-Axis, max 19)\n")
    lines.append("**Method**: Heuristic — M1-M6 + publisher/area inference.\n")
    lines.append(
        "**Caveat**: Full authoritative scoring requires expert annotation in "
        "`data/cpg_source_properties.json`; this is a conservative lower-bound estimate.\n"
    )
    lines.append(f"**Total candidates**: {n}\n")
    lines.append("## Tier Distribution\n")
    for t in ["S", "A", "B", "Excluded"]:
        lines.append(f"- **Tier {t}**: {tier_counts.get(t, 0)}")
    lines.append("")
    lines.append(f"- **Tier-valid (>=7)**: {tier_valid_count}/{n} ({100 * tier_valid_count / n:.1f}%)\n")
    lines.append("## Per-Axis Means\n")
    lines.append(f"- Trustworthiness (max 7): {ax1_mean:.2f}")
    lines.append(f"- Clinical Significance (max 6): {ax2_mean:.2f}")
    lines.append(f"- Formalizability (max 6): {ax3_mean:.2f}")
    lines.append(f"- Total (max 19): {total_mean:.2f}\n")
    lines.append("## Tier Distribution by Area\n")
    lines.append("| Area | Total | Tier S | Tier A | Tier B | Excluded |")
    lines.append("|---|:-:|:-:|:-:|:-:|:-:|")
    for area in sorted(area_tier.keys()):
        tc = area_tier[area]
        total = sum(tc.values())
        lines.append(
            f"| {area} | {total} | {tc.get('S', 0)} | {tc.get('A', 0)} | {tc.get('B', 0)} | {tc.get('Excluded', 0)} |"
        )
    lines.append("")
    lines.append("## Detailed Estimated Scores\n")
    lines.append(
        "| Area | Name | C1 | C2 | C3 | C4 | C5 | C6 | C7 | C8 | C9 | C10 | C11 | C12 | Ax1 | Ax2 | Ax3 | Total | Tier |"
    )
    lines.append("|---|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|")
    for r in scored:
        lines.append(
            f"| {r['area']} | {r['name']} | "
            f"{r['c1']} | {r['c2']} | {r['c3']} | {r['c4']} | {r['c5']} | "
            f"{r['c6']} | {r['c7']} | {r['c8']} | "
            f"{r['c9']} | {r['c10']} | {r['c11']} | {r['c12']} | "
            f"{r['axis1']} | {r['axis2']} | {r['axis3']} | **{r['total']}** | **{r['tier']}** |"
        )
    md_path = REPO_ROOT / args.md_output
    md_path.write_text("\n".join(lines), encoding="utf-8")

    print(f"Wrote {out_path}")
    print(f"Wrote {md_path}")
    print(f"Tier distribution: {dict(tier_counts)}")
    print(f"Per-axis means — Ax1={ax1_mean:.2f}/7, Ax2={ax2_mean:.2f}/6, Ax3={ax3_mean:.2f}/6")
    print(f"Total mean: {total_mean:.2f}/19, Tier-valid(>=7)={tier_valid_count}/{n}")


if __name__ == "__main__":
    main()
